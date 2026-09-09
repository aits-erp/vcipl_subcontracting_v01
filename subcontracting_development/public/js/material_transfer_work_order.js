frappe.listview_settings["Stock Entry"] = {

    onload: function (listview) {

        listview.page.add_inner_button(
            __("Create Work Order"),
            function () {

                const selected = listview.get_checked_items();

                if (!selected.length) {
                    frappe.msgprint({
                        title: __("No Stock Entries Selected"),
                        message: __(
                            "Please select one or more Material Transfer entries."
                        ),
                        indicator: "orange"
                    });
                    return;
                }

                const stock_entries = selected.map(
                    row => row.name
                );

                // Get Production Items from selected entries
                frappe.call({
                    method:
                        "subcontracting_development.manufacturing.material_transfer_work_order.get_transfer_details",

                    args: {
                        stock_entries: stock_entries
                    },

                    freeze: true,
                    freeze_message: __("Reading Material Transfers..."),

                    callback: function (r) {

                        if (!r.message) {
                            return;
                        }

                        show_work_order_dialog(
                            r.message,
                            stock_entries
                        );
                    }
                });

            }
        );
    }
};


function show_work_order_dialog(data, stock_entries) {

    let dialog = new frappe.ui.Dialog({

        title: __("Create Work Order From Material Transfers"),

        fields: [

            {
                fieldname: "production_item",
                label: __("Item To Manufacture"),
                fieldtype: "Link",
                options: "Item",
                reqd: 1,

                get_query: function () {
                    return {
                        filters: {
                            is_stock_item: 1
                        }
                    };
                }
            },

            {
                fieldname: "bom_no",
                label: __("BOM"),
                fieldtype: "Link",
                options: "BOM",
                reqd: 1,

                get_query: function () {

                    let item =
                        dialog.get_value("production_item");

                    return {
                        filters: {
                            item: item,
                            is_active: 1
                        }
                    };
                }
            },

            {
                fieldname: "qty",
                label: __("Qty To Manufacture"),
                fieldtype: "Float",
                reqd: 1,
                default: 1
            },

            {
                fieldname: "section_materials",
                fieldtype: "Section Break",
                label: __("Selected Material Transfers")
            },

            {
                fieldname: "materials_html",
                fieldtype: "HTML"
            }
        ],

        primary_action_label: __("Create Work Order"),

        primary_action: function () {

            let values = dialog.get_values();

            if (!values) {
                return;
            }

            frappe.call({

                method:
                    "subcontracting_development.manufacturing.material_transfer_work_order.create_work_order",

                args: {
                    stock_entries: stock_entries,
                    production_item: values.production_item,
                    bom_no: values.bom_no,
                    qty: values.qty
                },

                freeze: true,

                freeze_message:
                    __("Creating Work Order..."),

                callback: function (r) {

                    if (!r.message) {
                        return;
                    }

                    dialog.hide();

                    frappe.show_alert({
                        message: __(
                            "Work Order {0} created successfully",
                            [
                                `<a href="/app/work-order/${r.message.name}">
                                    ${r.message.name}
                                </a>`
                            ]
                        ),
                        indicator: "green"
                    });

                    // Open newly created Work Order
                    frappe.set_route(
                        "Form",
                        "Work Order",
                        r.message.name
                    );
                }
            });
        }
    });


    // Show selected Material Transfers
    let html = `
        <table class="table table-bordered">
            <thead>
                <tr>
                    <th>Stock Entry</th>
                    <th>Item</th>
                    <th>Qty</th>
                    <th>Warehouse</th>
                </tr>
            </thead>
            <tbody>
    `;

    (data.items || []).forEach(function (row) {

        html += `
            <tr>
                <td>${row.stock_entry}</td>
                <td>${row.item_code}</td>
                <td>${row.qty}</td>
                <td>${row.s_warehouse || ""}</td>
            </tr>
        `;
    });

    html += `
            </tbody>
        </table>
    `;

    dialog.fields_dict.materials_html.$wrapper.html(html);

    dialog.show();
}