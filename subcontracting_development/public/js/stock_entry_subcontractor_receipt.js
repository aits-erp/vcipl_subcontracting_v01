frappe.ui.form.on("Stock Entry", {
    refresh(frm) {
        if (
            frm.doc.stock_entry_type !== "Subcontractor Receipt" ||
            frm.doc.purpose !== "Repack"
        ) {
            return;
        }

        // Finished Good filter
        frm.set_query("custom_finished_good", function () {
            return {
                filters: {
                    item_group: "Finished Goods",
                    disabled: 0,
                    is_stock_item: 1
                }
            };
        });

        if (frm.doc.docstatus === 0) {
            frm.add_custom_button(
                __("Get Available Challans"),
                () => {
                    get_available_challans(frm);
                }
            );

            frm.add_custom_button(
                __("Get Challan Materials"),
                () => {
                    get_challan_materials(frm);
                }
            );
        }
    },

    stock_entry_type(frm) {
        frm.refresh();
    },

    purpose(frm) {
        frm.refresh();
    }
});


function get_available_challans(frm) {

    frappe.call({
        method:
            "subcontracting_development.manufacturing.subcontractor_receipt.get_available_challans",

        args: {
            subcontractor:
                frm.doc.custom_subcontractor || null,

            work_order:
                frm.doc.work_order || null
        },

        freeze: true,

        freeze_message:
            __("Loading available challans..."),

        callback: function (r) {

            if (!r.message) {
                return;
            }

            frm.clear_table(
                "custom_contractor_challans"
            );

            r.message.forEach(function (challan) {

                let row = frm.add_child(
                    "custom_contractor_challans"
                );

                row.select = 0;

                row.challan_no =
                    challan.challan_no;

                row.posting_date =
                    challan.posting_date;

                row.work_order =
                    challan.work_order;

                /*
                 * Subcontractor belongs to the
                 * parent Stock Entry.
                 *
                 * We do not depend on a child
                 * table subcontractor field.
                 */
                if (
                    row.subcontractor !== undefined
                ) {
                    row.subcontractor =
                        challan.subcontractor;
                }

                row.pending_qty =
                    challan.pending_qty;
            });

            frm.refresh_field(
                "custom_contractor_challans"
            );

            frappe.show_alert({
                message: __(
                    "{0} available challan(s) loaded",
                    [r.message.length]
                ),
                indicator: "green"
            });
        }
    });
}


function get_challan_materials(frm) {

    let selected_challans = [];

    (
        frm.doc.custom_contractor_challans || []
    ).forEach(function (row) {

        if (
            row.select &&
            row.challan_no
        ) {
            selected_challans.push(
                row.challan_no
            );
        }
    });

    if (!selected_challans.length) {

        frappe.msgprint({
            title:
                __("No Challan Selected"),

            message:
                __("Please select at least one challan."),

            indicator: "orange"
        });

        return;
    }

    frappe.call({
        method:
            "subcontracting_development.manufacturing.subcontractor_receipt.get_selected_challan_items",

        args: {
            challans: selected_challans
        },

        freeze: true,

        freeze_message:
            __("Loading pending materials..."),

        callback: function (r) {

            if (!r.message) {
                return;
            }

            /*
             * Keep items that were manually added
             * and do not belong to a challan.
             */
            let existing_items =
                frm.doc.items || [];

            frm.clear_table("items");

            existing_items.forEach(
                function (item) {

                    if (
                        !item.custom_challan_no
                    ) {

                        let row =
                            frm.add_child(
                                "items"
                            );

                        Object.keys(item)
                            .forEach(
                                function (key) {

                                    if (
                                        ![
                                            "name",
                                            "parent",
                                            "parentfield",
                                            "parenttype",
                                            "idx",
                                            "docstatus"
                                        ].includes(key)
                                    ) {
                                        row[key] =
                                            item[key];
                                    }
                                }
                            );
                    }
                }
            );

            /*
             * Add pending material rows.
             */
            r.message.forEach(
                function (item) {

                    let row =
                        frm.add_child(
                            "items"
                        );

                    row.item_code =
                        item.item_code;

                    row.item_name =
                        item.item_name;

                    row.qty =
                        item.qty;

                    row.transfer_qty =
                        item.transfer_qty;

                    /*
                     * Original Material Transfer:
                     *
                     * Source → Target
                     *
                     * Receipt consumes from
                     * original Target Warehouse.
                     */
                    row.s_warehouse =
                        item.source_warehouse;

                    row.t_warehouse = null;

                    /*
                     * Remember the original
                     * contractor challan.
                     */
                    row.custom_challan_no =
                        item.challan_no;

                    /*
                     * These are consumption rows,
                     * not finished item rows.
                     */
                    row.is_finished_item = 0;

                    if (item.uom) {
                        row.uom = item.uom;
                    }

                    if (
                        item.conversion_factor
                    ) {
                        row.conversion_factor =
                            item.conversion_factor;
                    }
                }
            );

            frm.refresh_field("items");

            frappe.show_alert({
                message: __(
                    "{0} pending material row(s) loaded",
                    [r.message.length]
                ),
                indicator: "green"
            });
        }
    });
}