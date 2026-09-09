import frappe
from frappe import _
from frappe.utils import flt


@frappe.whitelist()
def get_transfer_details(stock_entries):

    if isinstance(stock_entries, str):
        stock_entries = frappe.parse_json(stock_entries)

    if not stock_entries:
        frappe.throw(_("Please select at least one Stock Entry."))

    items = []

    for stock_entry_name in stock_entries:

        se = frappe.get_doc(
            "Stock Entry",
            stock_entry_name
        )

        # Only Material Transfer for Manufacture
        if se.purpose != "Material Transfer for Manufacture":
            frappe.throw(
                _(
                    "Stock Entry {0} is not a Material Transfer for Manufacture."
                ).format(stock_entry_name)
            )

        # Only submitted entries
        if se.docstatus != 1:
            frappe.throw(
                _(
                    "Stock Entry {0} must be submitted."
                ).format(stock_entry_name)
            )

        for row in se.items:

            # Material being transferred FROM warehouse
            if not row.s_warehouse:
                continue

            items.append({
                "stock_entry": se.name,
                "item_code": row.item_code,
                "qty": flt(row.qty),
                "s_warehouse": row.s_warehouse,
                "t_warehouse": row.t_warehouse
            })

    return {
        "items": items
    }


@frappe.whitelist()
def create_work_order(
    stock_entries,
    production_item,
    bom_no,
    qty
):

    if isinstance(stock_entries, str):
        stock_entries = frappe.parse_json(stock_entries)

    if not stock_entries:
        frappe.throw(
            _("Please select at least one Material Transfer.")
        )

    if not production_item:
        frappe.throw(
            _("Please select Item To Manufacture.")
        )

    if not bom_no:
        frappe.throw(
            _("Please select BOM.")
        )

    qty = flt(qty)

    if qty <= 0:
        frappe.throw(
            _("Quantity must be greater than zero.")
        )

    # ---------------------------------------------------------
    # Validate BOM
    # ---------------------------------------------------------

    bom = frappe.get_doc(
        "BOM",
        bom_no
    )

    if bom.docstatus != 1:
        frappe.throw(
            _("BOM {0} must be submitted.").format(bom_no)
        )

    if bom.item != production_item:
        frappe.throw(
            _(
                "BOM {0} belongs to Item {1}, not {2}."
            ).format(
                bom_no,
                bom.item,
                production_item
            )
        )

    # ---------------------------------------------------------
    # Get first Stock Entry
    # ---------------------------------------------------------

    first_se = frappe.get_doc(
        "Stock Entry",
        stock_entries[0]
    )

    # ---------------------------------------------------------
    # Create Work Order
    # ---------------------------------------------------------

    wo = frappe.new_doc("Work Order")

    wo.production_item = production_item
    wo.bom_no = bom_no
    wo.qty = qty
    wo.company = first_se.company

    if first_se.project:
        wo.project = first_se.project

    # ---------------------------------------------------------
    # Get BOM Items
    # ---------------------------------------------------------

    bom_items = {}

    for row in bom.items:

        bom_items[row.item_code] = {
            "required_qty": flt(row.qty),
            "source_warehouse": row.source_warehouse
        }

    # ---------------------------------------------------------
    # Aggregate selected Material Transfers
    # ---------------------------------------------------------

    transferred_items = {}

    for stock_entry_name in stock_entries:

        se = frappe.get_doc(
            "Stock Entry",
            stock_entry_name
        )

        if se.docstatus != 1:
            frappe.throw(
                _("Stock Entry {0} is not submitted.").format(
                    stock_entry_name
                )
            )

        if se.purpose != "Material Transfer for Manufacture":
            frappe.throw(
                _(
                    "Stock Entry {0} is not a Material Transfer for Manufacture."
                ).format(stock_entry_name)
            )

        for row in se.items:

            if not row.s_warehouse:
                continue

            if row.item_code not in transferred_items:
                transferred_items[row.item_code] = {
                    "qty": 0,
                    "warehouse": row.s_warehouse
                }

            transferred_items[row.item_code]["qty"] += flt(
                row.qty
            )

    # ---------------------------------------------------------
    # Add required items to Work Order
    # ---------------------------------------------------------

    for item_code, transfer_data in transferred_items.items():

        item_data = bom_items.get(item_code)

        required_qty = 0

        if item_data:
            required_qty = item_data["required_qty"] * qty

        wo.append(
            "required_items",
            {
                "item_code": item_code,
                "required_qty": required_qty,
                "source_warehouse":
                    transfer_data["warehouse"],
                "transferred_qty":
                    transfer_data["qty"]
            }
        )

    # ---------------------------------------------------------
    # Save Work Order
    # ---------------------------------------------------------

    wo.insert()

    # ---------------------------------------------------------
    # Link Stock Entries to Work Order
    #
    # IMPORTANT:
    # This requires a custom Link field on Stock Entry:
    #
    # Fieldname: custom_work_order
    # Fieldtype: Link
    # Options: Work Order
    # ---------------------------------------------------------

    for stock_entry_name in stock_entries:

        frappe.db.set_value(
            "Stock Entry",
            stock_entry_name,
            "custom_work_order",
            wo.name
        )

    frappe.db.commit()

    return wo


@frappe.whitelist()
def prepare_material_transfer_for_manufacture(doc, method=None):
    """
    Custom handling for Material Transfer for Manufacture.

    The standard ERPNext Work Order logic uses fg_completed_qty
    as the aggregate material-transfer quantity. That does not
    work when different raw materials are transferred in separate
    Stock Entries.

    For our workflow:
    - fg_completed_qty is not used as the transfer quantity.
    - Per-item quantities are tracked through Work Order Required Items.
    """

    if doc.purpose != "Material Transfer for Manufacture":
        return

    if not doc.work_order:
        return

    # Do not let ERPNext aggregate this Stock Entry as a
    # finished-production quantity.
    doc.from_bom = 0
    doc.fg_completed_qty = 0


def update_work_order_material_transfer_qty(doc, method=None):
    """
    Recalculate Work Order Required Item transferred quantities
    from actual submitted Material Transfer for Manufacture
    Stock Entries.

    This makes the transfer quantity item-wise instead of
    using the Work Order-level fg_completed_qty total.
    """

    if doc.purpose != "Material Transfer for Manufacture":
        return

    if not doc.work_order:
        return

    work_order = frappe.get_doc(
        "Work Order",
        doc.work_order
    )

    # ---------------------------------------------------------
    # Get actual submitted Material Transfer quantities
    # ---------------------------------------------------------

    rows = frappe.db.sql(
        """
        SELECT
            sed.item_code,
            SUM(sed.qty) AS transferred_qty
        FROM
            `tabStock Entry Detail` sed
        INNER JOIN
            `tabStock Entry` se
            ON se.name = sed.parent
        WHERE
            se.work_order = %s
            AND se.purpose = 'Material Transfer for Manufacture'
            AND se.docstatus = 1
            AND se.is_return = 0
            AND sed.s_warehouse IS NOT NULL
            AND sed.s_warehouse != ''
        GROUP BY
            sed.item_code
        """,
        work_order.name,
        as_dict=True
    )

    transferred_by_item = {
        row.item_code: flt(row.transferred_qty)
        for row in rows
    }

    # ---------------------------------------------------------
    # Update Work Order Required Items
    # ---------------------------------------------------------

    for item in work_order.required_items:

        transferred_qty = transferred_by_item.get(
            item.item_code,
            0
        )

        item.transferred_qty = transferred_qty

        item.db_update()

    # ---------------------------------------------------------
    # Calculate production-equivalent transferred quantity
    #
    # Example:
    #
    # BOM:
    # LT PANEL = 1 per FG
    # LED      = 1 per FG
    # COPPER   = 2 per FG
    #
    # WO Qty = 100
    #
    # LT PANEL transferred = 50
    # LED transferred      = 50
    # COPPER transferred   = 100
    #
    # Equivalent completed transfer = 50
    # ---------------------------------------------------------

    completion_qty = None

    for item in work_order.required_items:

        required_qty = flt(item.required_qty)
        transferred_qty = flt(item.transferred_qty)

        if required_qty <= 0:
            continue

        item_completion_qty = (
            transferred_qty / required_qty
        ) * flt(work_order.qty)

        if completion_qty is None:
            completion_qty = item_completion_qty
        else:
            completion_qty = min(
                completion_qty,
                item_completion_qty
            )

    if completion_qty is None:
        completion_qty = 0

    completion_qty = min(
        completion_qty,
        flt(work_order.qty)
    )

    # ---------------------------------------------------------
    # Update Work Order aggregate field
    # ---------------------------------------------------------

    frappe.db.set_value(
        "Work Order",
        work_order.name,
        "material_transferred_for_manufacturing",
        completion_qty
    )

    # Update status after required item quantities change.
    work_order.reload()
    work_order.update_status()


def prepare_subcontractor_receipt_finished_good(doc, method=None):
    """
    Automatically create/update the Finished Good row
    in Stock Entry Items from the custom parent fields.

    Applies only to:
        Stock Entry Type = Subcontractor Receipt
        Purpose = Repack
    """

    if doc.stock_entry_type != "Subcontractor Receipt":
        return

    if doc.purpose != "Repack":
        return

    if not doc.custom_finished_good:
        return

    if not doc.custom_finished_good_warehouse:
        frappe.throw(
            _("Please select Finished Good Warehouse.")
        )

    if flt(doc.custom_finished_good_qty) <= 0:
        frappe.throw(
            _("Finished Good Qty must be greater than zero.")
        )

    finished_good = None

    # ---------------------------------------------------------
    # Find existing finished-good row
    # ---------------------------------------------------------

    for row in doc.items:

        if row.is_finished_item:
            finished_good = row
            break

        if (
            row.item_code == doc.custom_finished_good
            and row.t_warehouse == doc.custom_finished_good_warehouse
        ):
            finished_good = row
            break

    # ---------------------------------------------------------
    # Create finished-good row if it doesn't exist
    # ---------------------------------------------------------

    if not finished_good:

        finished_good = doc.append(
            "items",
            {}
        )

    # ---------------------------------------------------------
    # Set Finished Good row
    # ---------------------------------------------------------

    finished_good.item_code = doc.custom_finished_good

    finished_good.qty = flt(
        doc.custom_finished_good_qty
    )

    finished_good.t_warehouse = (
        doc.custom_finished_good_warehouse
    )

    finished_good.s_warehouse = None

    finished_good.is_finished_item = 1

    finished_good.is_scrap_item = 0

    # Finished Good should not carry challan number
    finished_good.custom_challan_no = None