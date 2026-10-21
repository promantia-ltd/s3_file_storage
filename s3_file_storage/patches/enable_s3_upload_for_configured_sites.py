import frappe


def execute():
	"""Keep S3 on for sites that already had a bucket before the Enable S3 Upload toggle.

	Site Name is left blank on purpose: uploads stay blocked with a site-name mismatch
	error until an admin confirms which site the settings belong to. A restored copy of
	a production site therefore cannot write into the production bucket after migrate.
	"""
	if not frappe.db.get_single_value("S3 File Settings", "bucket_name"):
		return

	frappe.db.set_single_value("S3 File Settings", "enable_s3_upload", 1)
