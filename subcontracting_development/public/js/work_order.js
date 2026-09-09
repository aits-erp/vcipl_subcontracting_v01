// frappe.ui.form.on("Work Order", {

//     // ============================================================
//     // SETUP
//     // ============================================================

//     setup: function (frm) {

//         // Allow BOM selection without Production Item
//         frm.set_query("bom_no", function () {
//             return {
//                 query: "erpnext.controllers.queries.bom"
//             };
//         });
//     },


//     // ============================================================
//     // BOM SELECTED
//     // BOM -> Production Item
//     // ============================================================

//     bom_no: function (frm) {

//         if (!frm.doc.bom_no) {
//             return;
//         }

//         frappe.call({
//             method: "frappe.client.get",
//             args: {
//                 doctype: "BOM",
//                 name: frm.doc.bom_no
//             },

//             callback: function (r) {

//                 if (!r.message) {
//                     return;
//                 }

//                 const bom = r.message;

//                 if (bom.item) {

//                     // Automatically set Production Item
//                     frm.set_value(
//                         "production_item",
//                         bom.item
//                     );

//                 }
//             }
//         });
//     },


//     // ============================================================
//     // REFRESH
//     // Replace START with CREATE
//     // ============================================================

//     refresh: function (frm) {

//         // Only for submitted Work Orders
//         if (frm.doc.docstatus !== 1) {
//             return;
//         }

//         // Do not show for Completed / Closed
//         if (["Completed", "Closed"].includes(frm.doc.status)) {
//             return;
//         }

//         // Do not show if transfer is skipped
//         if (frm.doc.skip_transfer) {
//             return;
//         }

//         // Do not show if material transfer is against Job Card
//         if (frm.doc.transfer_material_against === "Job Card") {
//             return;
//         }


//         // ========================================================
//         // CHECK WHETHER MATERIAL IS STILL PENDING
//         // ========================================================

//         const pending_to_transfer = (frm.doc.required_items || []).some(
//             item => flt(item.transferred_qty) < flt(item.required_qty)
//         );

//         if (!pending_to_transfer) {
//             return;
//         }


//         // ========================================================
//         // REMOVE STANDARD START BUTTON
//         // ========================================================

//         frm.remove_custom_button(__("Start"));


//         // Remove our Create button first to avoid duplicates
//         frm.remove_custom_button(__("Create"));


//         // ========================================================
//         // ADD CREATE BUTTON
//         // ========================================================

//         const create_btn = frm.add_custom_button(
//             __("Create"),
//             function () {

//                 // ------------------------------------------------
//                 // Get the pending quantity using ERPNext logic
//                 // ------------------------------------------------

//                 const qty = erpnext.work_order.get_max_transferable_qty(
//                     frm,
//                     "Material Transfer for Manufacture"
//                 );

//                 if (!qty || qty <= 0) {

//                     frappe.msgprint({
//                         title: __("Nothing to Transfer"),
//                         message: __(
//                             "There is no pending quantity to transfer for manufacture."
//                         ),
//                         indicator: "orange"
//                     });

//                     return;
//                 }


//                 // ------------------------------------------------
//                 // Use ERPNext's STANDARD Stock Entry method
//                 // ------------------------------------------------

//                 frappe.xcall(
//                     "erpnext.manufacturing.doctype.work_order.work_order.make_stock_entry",
//                     {
//                         work_order_id: frm.doc.name,
//                         purpose: "Material Transfer for Manufacture",
//                         qty: qty
//                     }
//                 ).then(function (stock_entry) {

//                     if (!stock_entry) {
//                         return;
//                     }

//                     // Sync generated Stock Entry
//                     frappe.model.sync(stock_entry);

//                     // Open the generated Stock Entry
//                     frappe.set_route(
//                         "Form",
//                         stock_entry.doctype,
//                         stock_entry.name
//                     );

//                 }).catch(function (error) {

//                     console.error(
//                         "Work Order Stock Entry Error:",
//                         error
//                     );

//                 });

//             }
//         );

//         // Make Create button primary
//         create_btn.addClass("btn-primary");
//     }

// });



frappe.ui.form.on("Work Order", {

    // ============================================================
    // SETUP
    // ============================================================

    setup: function (frm) {

        // Allow BOM selection without Production Item
        frm.set_query("bom_no", function () {
            return {
                query: "erpnext.controllers.queries.bom"
            };
        });
    },


    // ============================================================
    // BOM SELECTED
    // BOM -> Production Item
    // ============================================================

    bom_no: function (frm) {

        if (!frm.doc.bom_no) {
            return;
        }

        frappe.call({
            method: "frappe.client.get",
            args: {
                doctype: "BOM",
                name: frm.doc.bom_no
            },

            callback: function (r) {

                if (!r.message) {
                    return;
                }

                const bom = r.message;

                if (bom.item) {

                    frm.set_value(
                        "production_item",
                        bom.item
                    );

                }
            }
        });
    },


    // ============================================================
    // REFRESH
    // START -> CREATE
    // ============================================================

    refresh: function (frm) {

        // Only submitted Work Orders
        if (frm.doc.docstatus !== 1) {
            return;
        }

        // Don't show on Completed / Closed
        if (["Completed", "Closed"].includes(frm.doc.status)) {
            return;
        }

        // Don't show when transfer is skipped
        if (frm.doc.skip_transfer) {
            return;
        }

        // Don't show if transfer is against Job Card
        if (frm.doc.transfer_material_against === "Job Card") {
            return;
        }


        // ========================================================
        // CHECK PENDING RAW MATERIALS
        // ========================================================

        const pending_items = (frm.doc.required_items || []).filter(
            row => {
                return flt(row.required_qty) > flt(row.transferred_qty);
            }
        );

        // If all raw materials are transferred,
        // don't show Create button
        if (!pending_items.length) {
            return;
        }


        // ========================================================
        // REMOVE STANDARD START BUTTON
        // ========================================================

        frm.remove_custom_button(__("Start"));

        // Prevent duplicate Create button
        frm.remove_custom_button(__("Create"));


        // ========================================================
        // CREATE BUTTON
        // ========================================================

        const create_btn = frm.add_custom_button(
            __("Create"),
            function () {

                /*
                 * IMPORTANT
                 *
                 * Do NOT use:
                 *
                 * erpnext.work_order.get_max_transferable_qty()
                 *
                 * That function checks Work Order level quantity.
                 *
                 * We want ERPNext to calculate pending quantity
                 * for each raw material.
                 */


                // Work Order quantity
                const qty = flt(frm.doc.qty);

                if (!qty || qty <= 0) {

                    frappe.msgprint({
                        title: __("Invalid Quantity"),
                        message: __(
                            "Work Order quantity must be greater than zero."
                        ),
                        indicator: "red"
                    });

                    return;
                }


                // =================================================
                // CALL STANDARD ERPNext STOCK ENTRY METHOD
                // =================================================

                frappe.xcall(
                    "erpnext.manufacturing.doctype.work_order.work_order.make_stock_entry",
                    {
                        work_order_id: frm.doc.name,
                        purpose: "Material Transfer for Manufacture",
                        qty: qty
                    }
                ).then(function (stock_entry) {

                    if (!stock_entry) {
                        return;
                    }


                    // Sync generated Stock Entry
                    frappe.model.sync(stock_entry);


                    // Open generated Stock Entry
                    frappe.set_route(
                        "Form",
                        "Stock Entry",
                        stock_entry.name
                    );

                }).catch(function (error) {

                    console.error(
                        "Material Transfer Stock Entry Error:",
                        error
                    );

                    frappe.msgprint({
                        title: __("Error"),
                        message: __(
                            "Unable to create Material Transfer Stock Entry."
                        ),
                        indicator: "red"
                    });

                });

            }
        );


        // Make Create button primary
        create_btn.addClass("btn-primary");
    }

});