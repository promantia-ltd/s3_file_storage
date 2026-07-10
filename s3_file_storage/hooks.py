app_name = "s3_file_storage"
app_title = "S3 File Storage"
app_publisher = "Promantia Business Solutions Private Limited"
app_description = "This app helps you store files from Frappe into an S3 bucket easily and securely."
app_email = "rohit.g@promantia.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "s3_file_storage",
# 		"logo": "/assets/s3_file_storage/logo.png",
# 		"title": "S3 File Storage",
# 		"route": "/s3_file_storage",
# 		"has_permission": "s3_file_storage.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/s3_file_storage/css/s3_file_storage.css"
# app_include_js = "/assets/s3_file_storage/js/s3_file_storage.js"

# include js, css files in header of web template
# web_include_css = "/assets/s3_file_storage/css/s3_file_storage.css"
# web_include_js = "/assets/s3_file_storage/js/s3_file_storage.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "s3_file_storage/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "s3_file_storage/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "s3_file_storage.utils.jinja_methods",
# 	"filters": "s3_file_storage.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "s3_file_storage.install.before_install"
# after_install = "s3_file_storage.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "s3_file_storage.uninstall.before_uninstall"
# after_uninstall = "s3_file_storage.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "s3_file_storage.utils.before_app_install"
# after_app_install = "s3_file_storage.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "s3_file_storage.utils.before_app_uninstall"
# after_app_uninstall = "s3_file_storage.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "s3_file_storage.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
    "File": {
        "after_insert": "s3_file_storage.controller.file_upload_to_s3",
        "on_change": "s3_file_storage.controller.delete_from_cloud"
    }
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"s3_file_storage.tasks.all"
# 	],
# 	"daily": [
# 		"s3_file_storage.tasks.daily"
# 	],
# 	"hourly": [
# 		"s3_file_storage.tasks.hourly"
# 	],
# 	"weekly": [
# 		"s3_file_storage.tasks.weekly"
# 	],
# 	"monthly": [
# 		"s3_file_storage.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "s3_file_storage.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "s3_file_storage.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "s3_file_storage.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["s3_file_storage.utils.before_request"]
# after_request = ["s3_file_storage.utils.after_request"]

# Job Events
# ----------
# before_job = ["s3_file_storage.utils.before_job"]
# after_job = ["s3_file_storage.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"s3_file_storage.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

