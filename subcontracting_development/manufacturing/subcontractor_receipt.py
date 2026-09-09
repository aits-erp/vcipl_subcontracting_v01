import frappe
from frappe import _


SUBCONTRACTOR_RECEIPT_TYPE = "Subcontractor Receipt"
MATERIAL_TRANSFER_PURPOSE = "Material Transfer for Manufacture"
REPACK_PURPOSE = "Repack"

# Confirmed custom field on Stock Entry
SUBCONTRACTOR_FIELD = "custom_subcontractor"

# Confirmed custom field on Stock Entry Detail
CHALLAN_FIELD = "custom_challan_no"


def is_subcontractor_receipt(doc):
    """
    Check whether this Stock Entry is a Subcontractor Receipt.
    """

    return (
        doc.doctype == "Stock Entry"
        and doc.stock_entry_type == SUBCONTRACTOR_RECEIPT_TYPE
        and doc.purpose == REPACK_PURPOSE
    )


def get_stock_entry_subcontractor(doc):
    """
    Get Subcontractor from the Stock Entry parent.

    Confirmed field:
        custom_subcontractor
    """

    return doc.get(SUBCONTRACTOR_FIELD)


def get_stock_entry_work_order(doc):
    """
    Work Order is the standard parent field of Stock Entry.
    """

    return doc.get("work_order")


def get_challan_header(challan_no):
    """
    Load and validate the original Material Transfer
    for Manufacture Stock Entry.
    """

    challan = frappe.get_doc(
        "Stock Entry",
        challan_no
    )

    if challan.docstatus != 1:
        frappe.throw(
            _("Stock Entry {0} is not submitted.")
            .format(challan_no)
        )

    if challan.purpose != MATERIAL_TRANSFER_PURPOSE:
        frappe.throw(
            _(
                "Stock Entry {0} is not a Material Transfer for Manufacture."
            ).format(challan_no)
        )

    return challan


@frappe.whitelist()
def get_available_challans(
    subcontractor=None,
    work_order=None
):
    """
    Return submitted Material Transfer for Manufacture
    Stock Entries that still have pending material.

    Filters:
        subcontractor = Stock Entry.custom_subcontractor
        work_order = Stock Entry.work_order
    """

    stock_entries = frappe.get_all(
        "Stock Entry",
        filters={
            "docstatus": 1,
            "purpose": MATERIAL_TRANSFER_PURPOSE,
        },
        fields=[
            "name",
            "posting_date",
            "work_order",
            "custom_subcontractor",
        ],
        order_by="posting_date desc, name desc",
    )

    result = []

    for se in stock_entries:

        # ---------------------------------------------------------
        # Get actual submitted challan
        # ---------------------------------------------------------

        challan = get_challan_header(
            se.name
        )

        # ---------------------------------------------------------
        # Parent fields
        # ---------------------------------------------------------

        challan_subcontractor = (
            challan.get(SUBCONTRACTOR_FIELD)
        )

        challan_work_order = (
            challan.get("work_order")
        )

        # ---------------------------------------------------------
        # Filter by selected subcontractor
        # ---------------------------------------------------------

        if subcontractor:

            if challan_subcontractor != subcontractor:
                continue

        # ---------------------------------------------------------
        # Filter by selected Work Order
        # ---------------------------------------------------------

        if work_order:

            if challan_work_order != work_order:
                continue

        # ---------------------------------------------------------
        # Calculate pending material
        # ---------------------------------------------------------

        pending_items = get_pending_items(
            challan.name
        )

        # Fully consumed challans are excluded.
        if not pending_items:
            continue

        # ---------------------------------------------------------
        # Total pending quantity
        # ---------------------------------------------------------

        pending_qty = sum(
            frappe.utils.flt(
                item["qty"]
            )
            for item in pending_items
        )

        result.append(
            {
                "challan_no": challan.name,
                "posting_date": challan.posting_date,
                "work_order": challan_work_order,
                "subcontractor": challan_subcontractor,
                "pending_qty": pending_qty,
            }
        )

    return result


def get_pending_items(challan_no):
    """
    Calculate pending material quantity for one
    Material Transfer for Manufacture challan.

    Original Material Transfer:

        Source Warehouse
              |
              v
        Target Warehouse


    Subcontractor Receipt:

        Target Warehouse
              |
              v
        Repack Consumption
    """

    challan = get_challan_header(
        challan_no
    )

    # =============================================================
    # 1. ORIGINAL TRANSFER QUANTITY
    # =============================================================

    transferred = {}

    for item in challan.items:

        if not item.item_code:
            continue

        qty = frappe.utils.flt(
            item.transfer_qty or item.qty
        )

        if qty <= 0:
            continue

        key = (
            item.item_code,
            item.t_warehouse,
            item.uom,
        )

        if key not in transferred:

            transferred[key] = {
                "item_code": item.item_code,
                "item_name": item.item_name,
                "qty": 0,
                "source_warehouse": item.t_warehouse,
                "uom": item.uom,
                "conversion_factor": (
                    item.conversion_factor or 1
                ),
            }

        transferred[key]["qty"] += qty

    if not transferred:
        return []

    # =============================================================
    # 2. ALREADY CONSUMED QUANTITY
    #
    # Only submitted Subcontractor Receipt entries are counted.
    #
    # custom_challan_no tells us which original challan was used.
    # =============================================================

    consumed = frappe.db.sql(
        """
        SELECT
            sed.item_code,
            sed.s_warehouse,
            sed.uom,

            SUM(
                COALESCE(
                    sed.transfer_qty,
                    sed.qty
                )
            ) AS consumed_qty

        FROM `tabStock Entry Detail` sed

        INNER JOIN `tabStock Entry` se
            ON se.name = sed.parent

        WHERE
            se.docstatus = 1

            AND se.stock_entry_type = %(stock_entry_type)s

            AND se.purpose = %(purpose)s

            AND sed.custom_challan_no = %(challan_no)s

            AND sed.s_warehouse IS NOT NULL

            AND sed.s_warehouse != ''

        GROUP BY
            sed.item_code,
            sed.s_warehouse,
            sed.uom
        """,
        {
            "stock_entry_type": SUBCONTRACTOR_RECEIPT_TYPE,
            "purpose": REPACK_PURPOSE,
            "challan_no": challan_no,
        },
        as_dict=True,
    )

    # =============================================================
    # 3. BUILD CONSUMED MAP
    # =============================================================

    consumed_map = {}

    for row in consumed:

        key = (
            row.item_code,
            row.s_warehouse,
            row.uom,
        )

        consumed_map[key] = frappe.utils.flt(
            row.consumed_qty
        )

    # =============================================================
    # 4. CALCULATE REMAINING QUANTITY
    # =============================================================

    pending = []

    for key, item in transferred.items():

        already_consumed = frappe.utils.flt(
            consumed_map.get(
                key,
                0
            )
        )

        remaining = (
            frappe.utils.flt(
                item["qty"]
            )
            - already_consumed
        )

        # Fully consumed.
        if remaining <= 0.000001:
            continue

        pending.append(
            {
                "item_code": item["item_code"],
                "item_name": item["item_name"],
                "qty": remaining,
                "transfer_qty": remaining,
                "source_warehouse": item[
                    "source_warehouse"
                ],
                "uom": item["uom"],
                "conversion_factor": item[
                    "conversion_factor"
                ],
                "challan_no": challan_no,
            }
        )

    return pending


@frappe.whitelist()
def get_challan_details(challan_no):
    """
    Return header information and pending materials
    for one challan.
    """

    challan = get_challan_header(
        challan_no
    )

    return {
        "challan_no": challan.name,

        "posting_date": challan.posting_date,

        "work_order": get_stock_entry_work_order(
            challan
        ),

        "subcontractor": get_stock_entry_subcontractor(
            challan
        ),

        "items": get_pending_items(
            challan_no
        ),
    }


@frappe.whitelist()
def get_selected_challan_items(challans):
    """
    Return pending materials for all selected challans.

    Every item keeps its original challan number.
    """

    if isinstance(challans, str):
        challans = frappe.parse_json(
            challans
        )

    if not challans:
        return []

    result = []

    # Remove duplicate challans.
    unique_challans = list(
        dict.fromkeys(challans)
    )

    for challan_no in unique_challans:

        pending_items = get_pending_items(
            challan_no
        )

        for item in pending_items:

            result.append(item)

    return result