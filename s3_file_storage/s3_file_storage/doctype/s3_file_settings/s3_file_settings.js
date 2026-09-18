// Copyright (c) 2025, rohit.g@promatia.com and contributors
// For license information, please see license.txt

frappe.provide("frappe.s3_file_storage");

frappe.s3_file_storage.SKIP_REASONS = {
    already_on_s3: __("already stored on S3"),
    doctype_excluded: __("excluded by the S3 Doctype Mapping table"),
    missing_local_file: __("local file missing on disk"),
    no_file_url: __("no file attached"),
    file_not_found: __("File record no longer exists"),
};

frappe.s3_file_storage.describe_skipped = function (skipped) {
    let reasons = Object.keys(skipped || {});
    if (!reasons.length) {
        return "";
    }

    let lines = reasons.map((reason) => {
        let label = frappe.s3_file_storage.SKIP_REASONS[reason] || reason;
        return `<li>${skipped[reason]} &mdash; ${label}</li>`;
    });

    return `<br><br>${__("Skipped:")}<ul>${lines.join("")}</ul>`;
};

frappe.ui.form.on("S3 File Settings", {
    setup: function (frm) {
        frappe.realtime.on("file_migration_progress", (data) => {
            if (data.progress) {
                let message = `Migrating Files: ${data.current_file} of ${data.total_files}`;

                frm.dashboard.show_progress(__("Migration Progress"), data.progress, message);

                if (data.progress >= 100) {
                    setTimeout(() => {
                        frm.reload_doc(); 
                    }, 1000);
                }
            }
        });
    },

	migrate_existing_files: function (frm) {
        frappe.confirm(
            __("Existing files from this instance will be deleted once pushed to S3. Are you sure you want to continue?"),
            function() {
                frappe.show_alert({
                    message: __("Local files getting migrated"),
                    indicator: "blue"
                });
                frappe.call({
                    method: "s3_file_storage.controller.migrate_existing_files",
                    callback: function (data) {
                        let result = data.message;
                        if (!result) {
                            frappe.show_alert({
                                message: __("Retry"),
                                indicator: "red"
                            });
                            return;
                        }

                        let skipped = frappe.s3_file_storage.describe_skipped(result.skipped);

                        if (result.failed) {
                            frappe.msgprint({
                                title: __("Migration Finished with Errors"),
                                message: __(
                                    "{0} file(s) migrated, {1} failed. See the Error Log for details.",
                                    [result.migrated, result.failed]
                                ) + skipped,
                                indicator: "orange"
                            });
                        } else if (!result.migrated) {
                            frappe.msgprint({
                                title: __("Nothing Migrated"),
                                message: __(
                                    "No file out of {0} was uploaded to S3.",
                                    [result.total]
                                ) + skipped,
                                indicator: "orange"
                            });
                        } else {
                            frappe.show_alert({
                                message: __("{0} file(s) migrated to S3", [result.migrated]),
                                indicator: "green"
                            });
                        }
                    }
                });
            },
            function() {
                frappe.show_alert({
                    message: __("Migration cancelled"),
                    indicator: "orange"
                });
            }
        );
    },
});
