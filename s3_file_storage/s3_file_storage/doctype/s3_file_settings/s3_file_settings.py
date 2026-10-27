# Copyright (c) 2025, rohit.g@promatia.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class S3FileSettings(Document):
	# --- Controller Methods ---
	def validate(self):
		self.site_name = (self.site_name or "").strip()
		self._clear_bucket_for_other_site()

	# --- Validate Helpers ---
	def _clear_bucket_for_other_site(self):
		"""Settings saved for another site must not point at that site's bucket or credentials."""
		if self.site_name == frappe.local.site:
			return

		self.bucket_name = ""
		self.aws_secret = ""
		frappe.msgprint(
			_(
				"The configured Site Name ({0}) does not match the actual site name ({1}). "
				"Bucket Name and AWS Secret have been cleared."
			).format(self.site_name, frappe.local.site),
			title=_("S3 Site Name Mismatch"),
			indicator="orange",
		)
