# --- Imports ---
from __future__ import unicode_literals

import datetime
import mimetypes
import os
import random
import re
import string
from collections import Counter
from urllib.parse import urlencode

import boto3
import magic
from botocore.client import Config
from botocore.exceptions import ClientError

import frappe
from frappe import _
from frappe.utils import create_batch


# --- Constants ---
URL_LOOKUP_BATCH_SIZE = 500
LOGGER_NAME = "s3_file_storage"
SUMMARY_SAMPLE_SIZE = 50

SKIP_REASONS = {
    "already_on_s3": "already stored on S3",
    "doctype_excluded": "excluded by the S3 Doctype Mapping table",
    "missing_local_file": "local file missing on disk",
    "no_file_url": "no file attached",
    "file_not_found": "File record no longer exists",
    "s3_upload_disabled": "S3 upload is disabled in S3 File Settings",
}


# --- Controllers ---
def file_upload_to_s3(doc, method):
    """File.after_insert — push the attached file to S3 and repoint every field at it."""
    if not doc or not doc.file_url or doc.get("is_folder"):
        return set_skip_reason(doc, "no_file_url")

    if s3_file_regex_match(doc.file_url):
        return set_skip_reason(doc, "already_on_s3")

    old_file_url = doc.file_url

    s3_upload = S3Operations()
    if not s3_upload.upload_enabled:
        return set_skip_reason(doc, "s3_upload_disabled")

    parent_doctype = doc.attached_to_doctype or "File"
    parent_name = doc.attached_to_name

    if is_doctype_excluded(s3_upload.s3_settings_doc, parent_doctype):
        return set_skip_reason(doc, "doctype_excluded")

    s3_upload.validate_site_name()

    file_path = get_local_file_path(doc)

    if not os.path.exists(file_path):
        return set_skip_reason(doc, "missing_local_file")

    doc.file_name = s3_upload.file_name_generator(
        doc.file_name or os.path.basename(old_file_url),
        parent_doctype,
        parent_name,
    )

    key = s3_upload.upload_files_to_s3_with_key(
        file_path,
        doc.file_name,
        doc.is_private,
        parent_doctype,
        parent_name,
    )

    doc.file_url = build_file_url(s3_upload, key, doc.file_name, doc.is_private)

    frappe.db.set_value(
        "File",
        doc.name,
        {
            "file_name": doc.file_name,
            "file_url": doc.file_url,
            "folder": "Home/Attachments",
            "old_parent": "Home/Attachments",
            "content_hash": key,
        },
        update_modified=False,
    )

    if parent_doctype and parent_name:
        parent_meta = frappe.get_meta(parent_doctype)

        image_field = parent_meta.get("image_field")
        if image_field:
            replace_file_url(parent_meta, parent_name, image_field, old_file_url, doc.file_url)

        if not method:
            update_attached_to_field(doc, parent_meta, parent_name, old_file_url)

    delete_local_file(file_path, old_file_url, doc.name)

    return doc.file_url


def delete_from_cloud(doc, method):
    """File.on_change — drop the S3 object when the record that owns it is deleted."""
    if not doc.flags.in_delete or not doc.content_hash:
        return

    if not s3_file_regex_match(doc.file_url):
        return

    # A custom build_s3_object_key hook can map several records onto one object;
    # drop it only with the last record that still references it.
    if frappe.db.exists("File", {"content_hash": doc.content_hash, "name": ("!=", doc.name)}):
        return

    S3Operations().delete_from_s3(doc.content_hash)


# --- File Upload To S3 Helpers ---
def s3_file_regex_match(file_url):
    """Tell an S3-backed URL (direct link or private download endpoint) from a local path."""
    if not file_url:
        return None

    return re.match(
        r"^(https:|/api/method/s3_file_storage\.controller\.generate_file)",
        file_url,
    )


def set_skip_reason(doc, reason):
    if not doc:
        return

    doc.flags.s3_skip_reason = reason
    log_skipped_file(doc.name, doc.file_url, reason)

    return doc.file_url


def log_skipped_file(name, file_url, reason):
    """Record why a file did not reach S3, in sites/<site>/logs/s3_file_storage.log."""
    if reason == "already_on_s3":
        return

    frappe.logger(LOGGER_NAME).info(
        f"Skipped File {name} ({file_url}): {SKIP_REASONS.get(reason, reason)}"
    )


def is_doctype_excluded(settings_doc, parent_doctype):
    """Decide whether the mapping table keeps this doctype out of S3.

    The mapping table is a blacklist when `ignore_mapped_doctypes` is checked and a
    whitelist when it is not. An empty table means "no restriction" in both modes,
    so an unsaved/unconfigured setting never silently blocks every upload.
    """
    mapped_doctypes = {
        d.mapped_doctype
        for d in settings_doc.get("s3_doctype_mapping", [])
    }
    if not mapped_doctypes:
        return False

    return (parent_doctype in mapped_doctypes) == bool(
        settings_doc.get("ignore_mapped_doctypes")
    )


def is_configured_site(settings_doc):
    """True when these settings were saved for the site that is running now."""
    return (settings_doc.site_name or "").strip() == frappe.local.site


def get_local_file_path(doc):
    site_path = frappe.utils.get_site_path()

    if doc.is_private:
        return f"{site_path}{doc.file_url}"

    return f"{site_path}/public{doc.file_url}"


def build_file_url(s3_upload, key, file_name, is_private):
    """A private file is served through the site so permissions still apply."""
    if is_private:
        query = urlencode({"key": key, "file_name": file_name})
        return f"/api/method/s3_file_storage.controller.generate_file?{query}"

    return f"{s3_upload.S3_CLIENT.meta.endpoint_url}/{s3_upload.BUCKET}/{key}"


def update_attached_to_field(doc, parent_meta, parent_name, old_url):
    fieldname = doc.get("attached_to_field")
    if not fieldname:
        return

    if parent_meta.has_field(fieldname):
        replace_file_url(parent_meta, parent_name, fieldname, old_url, doc.file_url)
        return

    # The field lives on a child row: Frappe only records the parent on the File, so
    # the old path is the only way back to the row that holds it.
    for table_field in parent_meta.get_table_fields():
        child_doctype = table_field.options
        if not frappe.get_meta(child_doctype).has_field(fieldname):
            continue

        rows = frappe.get_all(
            child_doctype,
            filters={
                "parent": parent_name,
                "parenttype": parent_meta.name,
                fieldname: old_url,
            },
            pluck="name",
        )
        for row in rows:
            frappe.db.set_value(
                child_doctype, row, fieldname, doc.file_url, update_modified=False
            )


def replace_file_url(meta, name, fieldname, old_url, new_url):
    """Repoint a field only when it still holds this file, never another one."""
    if meta.issingle:
        if frappe.db.get_single_value(meta.name, fieldname) == old_url:
            frappe.db.set_single_value(meta.name, fieldname, new_url)
        return

    if not frappe.db.has_column(meta.name, fieldname):
        return

    if frappe.db.get_value(meta.name, name, fieldname) == old_url:
        frappe.db.set_value(meta.name, name, fieldname, new_url, update_modified=False)


def delete_local_file(file_path, file_url, name):
    """Drop the on-disk copy once no other File record still points at it.

    Frappe stores one copy per unique content, so several File records can share one
    path. Whichever of them migrates last is the one that finds no sibling left on the
    old URL and removes the file. If a sibling was skipped (excluded doctype, failure),
    the file stays and that record keeps working.
    """
    if not os.path.exists(file_path):
        return

    if frappe.db.exists("File", {"file_url": file_url, "name": ("!=", name)}):
        return

    os.remove(file_path)


# --- Whitelisted Methods ---
@frappe.whitelist()
def generate_file(key=None, file_name=None):
    """Serve a private S3 file to a user allowed to read the File record."""
    if not key:
        frappe.local.response["body"] = "Key not found."
        return

    validate_file_access(key)
    s3_upload = S3Operations()
    s3_upload.validate_bucket()

    if s3_upload.s3_settings_doc.get("download_file_without_signed_url"):
        stream_file_from_s3(s3_upload, key, file_name)
        return

    frappe.local.response["type"] = "redirect"
    frappe.local.response["location"] = s3_upload.get_url(key, file_name)


@frappe.whitelist()
def migrate_existing_files():
    """Push every file still on local disk to S3, one record at a time."""
    frappe.only_for("System Manager")
    S3Operations().validate_bucket()

    files_list = frappe.get_all(
        "File",
        filters={"is_folder": 0},
        fields=["name", "file_url"],
    )

    total_files = len(files_list)
    url_map = {}
    skipped_files = []
    failed_files = []

    frappe.logger(LOGGER_NAME).info(f"S3 migration started for {total_files} file(s)")

    for idx, file in enumerate(files_list, 1):
        old_url = file["file_url"]
        new_url, skip_reason, failed = migrate_one_file(file["name"], old_url)

        if failed:
            failed_files.append(file)
        elif skip_reason:
            skipped_files.append({**file, "reason": skip_reason})
        elif new_url and new_url != old_url:
            url_map[old_url] = new_url

        publish_migration_progress(idx, total_files)

    if url_map:
        frappe.enqueue(
            "s3_file_storage.controller.update_attach_fields_after_migration",
            queue="long",
            timeout=6000,
            url_map=url_map,
        )

    log_migration_summary(total_files, len(url_map), skipped_files, failed_files)

    frappe.db.commit()

    return {
        "migrated": len(url_map),
        "failed": len(failed_files),
        "total": total_files,
        "skipped": dict(Counter(file["reason"] for file in skipped_files)),
    }


@frappe.whitelist()
def ping():
    return "pong"


# --- Generate File Helpers ---
def validate_file_access(key):
    """Allow the download only if the user can read one of the records holding this key."""
    if frappe.session.user == "Guest":
        raise frappe.PermissionError

    names = frappe.get_all("File", filters={"content_hash": key}, pluck="name")
    for name in names:
        if frappe.get_doc("File", name).is_downloadable():
            return

    raise frappe.PermissionError


def stream_file_from_s3(s3_upload, key, file_name):
    """Send the bytes through the site instead of handing out a signed S3 URL."""
    file_data = s3_upload.read_file_from_s3(key)

    if not isinstance(file_data, (bytes, bytearray)):
        file_data = bytes(file_data, "utf-8")

    mimetype = mimetypes.guess_type(file_name or key)[0] or "application/octet-stream"

    frappe.local.response.filename = file_name or key.split("/")[-1]
    frappe.local.response.type = "download"
    frappe.local.response.filecontent = file_data
    frappe.local.response["Content-Type"] = mimetype
    frappe.local.response["Content-Disposition"] = (
        f'attachment; filename="{frappe.local.response.filename}"'
    )


# --- Migrate Existing Files Helpers ---
def migrate_one_file(name, old_url):
    """Migrate one File in its own transaction. Returns (new_url, skip_reason, failed)."""
    if not old_url or s3_file_regex_match(old_url):
        reason = "already_on_s3" if old_url else "no_file_url"
        log_skipped_file(name, old_url, reason)
        return None, reason, False

    try:
        new_url, skip_reason = upload_existing_file_to_s3(name)
        frappe.db.commit()
        return new_url, skip_reason, False
    except Exception:
        frappe.db.rollback()
        log_failed_file(name, old_url)
        return None, None, True


def upload_existing_file_to_s3(name):
    """Migrate one File. Returns (new_file_url, skip_reason)."""
    try:
        doc = frappe.get_doc("File", name)
    except frappe.DoesNotExistError:
        return None, "file_not_found"

    file_url = file_upload_to_s3(doc, None)

    return file_url, doc.flags.get("s3_skip_reason")


def log_failed_file(name, file_url):
    frappe.logger(LOGGER_NAME).error(f"Failed File {name} ({file_url})", exc_info=True)
    frappe.log_error(
        title=f"S3 migration failed for File {name}",
        message=frappe.get_traceback(),
    )


def publish_migration_progress(current_file, total_files):
    frappe.publish_realtime(
        "file_migration_progress",
        {
            "current_file": current_file,
            "total_files": total_files,
            "progress": (current_file * 100) / total_files,
        },
    )


def update_attach_fields_after_migration(url_map):
    """Repoint Attach fields left holding a local path. Enqueued once the loop is done."""
    if not url_map:
        return

    old_urls = list(url_map.keys())

    for doctype, fieldname in get_attach_fields():
        try:
            meta = frappe.get_meta(doctype)
        except Exception:
            continue

        if meta.issingle:
            update_single_attach_field(doctype, fieldname, url_map)
            continue

        try:
            if not frappe.db.has_column(doctype, fieldname):
                continue
        except Exception:
            continue

        update_attach_field(doctype, fieldname, old_urls, url_map)

    frappe.db.commit()


def get_attach_fields():
    standard_fields = frappe.get_all(
        "DocField",
        filters={"fieldtype": ["in", ["Attach", "Attach Image"]]},
        fields=["parent as doctype", "fieldname"],
    )
    custom_fields = frappe.get_all(
        "Custom Field",
        filters={"fieldtype": ["in", ["Attach", "Attach Image"]]},
        fields=["dt as doctype", "fieldname"],
    )
    return [(d.doctype, d.fieldname) for d in standard_fields + custom_fields]


def update_attach_field(doctype, fieldname, old_urls, url_map):
    for batch in create_batch(old_urls, URL_LOOKUP_BATCH_SIZE):
        try:
            rows = frappe.db.sql(
                f"""SELECT `name`, `{fieldname}` AS value
                    FROM `tab{doctype}`
                    WHERE `{fieldname}` IN %(urls)s""",
                {"urls": tuple(batch)},
                as_dict=True,
            )
        except Exception:
            frappe.log_error(
                title=f"S3 migration: attach field scan failed ({doctype}.{fieldname})",
                message=frappe.get_traceback(),
            )
            return

        for row in rows:
            new_url = url_map.get(row.value)
            if new_url:
                frappe.db.set_value(
                    doctype, row.name, fieldname, new_url, update_modified=False
                )


def update_single_attach_field(doctype, fieldname, url_map):
    new_url = url_map.get(frappe.db.get_single_value(doctype, fieldname))
    if new_url:
        frappe.db.set_single_value(doctype, fieldname, new_url)


def log_migration_summary(total_files, migrated, skipped_files, failed_files):
    """Write one Error Log entry naming the files that were skipped or failed."""
    summary = (
        f"Total: {total_files}, migrated: {migrated}, "
        f"skipped: {len(skipped_files)}, failed: {len(failed_files)}"
    )
    frappe.logger(LOGGER_NAME).info(f"S3 migration finished. {summary}")

    reported = [file for file in skipped_files if file["reason"] != "already_on_s3"]
    if not reported and not failed_files:
        return

    lines = [summary]

    for reason in {file["reason"] for file in reported}:
        names = [file["name"] for file in reported if file["reason"] == reason]
        lines.append(f"\nSkipped ({SKIP_REASONS.get(reason, reason)}): {len(names)}")
        lines.append(format_file_sample(names))

    if failed_files:
        lines.append(f"\nFailed: {len(failed_files)} (see the per-file Error Log entries)")
        lines.append(format_file_sample([file["name"] for file in failed_files]))

    frappe.log_error(title="S3 migration summary", message="\n".join(lines))


def format_file_sample(names):
    sample = ", ".join(names[:SUMMARY_SAMPLE_SIZE])
    if len(names) > SUMMARY_SAMPLE_SIZE:
        sample += f", ... and {len(names) - SUMMARY_SAMPLE_SIZE} more"

    return sample


# --- S3 Operations ---
class S3Operations(object):

    def __init__(self):
        self.s3_settings_doc = frappe.get_doc(
            "S3 File Settings",
            "S3 File Settings",
        )
        aws_key = self.s3_settings_doc.get_password(
            "aws_key", raise_exception=False
        )
        aws_secret = self.s3_settings_doc.get_password(
            "aws_secret", raise_exception=False
        )
        if aws_key and aws_secret:
            self.S3_CLIENT = boto3.client(
                "s3",
                aws_access_key_id=aws_key,
                aws_secret_access_key=aws_secret,
                region_name=self.s3_settings_doc.region_name,
                config=Config(signature_version="s3v4"),
            )
        else:
            self.S3_CLIENT = boto3.client(
                "s3",
                region_name=self.s3_settings_doc.region_name,
                config=Config(signature_version="s3v4"),
            )
        self.upload_enabled = bool(self.s3_settings_doc.enable_s3_upload)
        self.site_matches = is_configured_site(self.s3_settings_doc)
        # A restored copy of another site must never read, write or delete in its bucket.
        self.BUCKET = (
            self.s3_settings_doc.bucket_name
            if self.upload_enabled and self.site_matches
            else ""
        )
        self.folder_name = self.s3_settings_doc.folder_name

    def validate_site_name(self):
        """Block S3 work on a site other than the one these settings were made for."""
        if not self.upload_enabled or self.site_matches:
            return

        frappe.throw(
            _(
                "The Site Name configured in S3 File Settings ({0}) does not match "
                "the actual site name ({1}). Update S3 File Settings before uploading."
            ).format(self.s3_settings_doc.site_name or _("not set"), frappe.local.site),
            title=_("S3 Site Name Mismatch"),
        )

    def validate_bucket(self):
        if not self.upload_enabled:
            frappe.throw(_("S3 upload is disabled in S3 File Settings."))

        self.validate_site_name()

    def file_name_generator(self, file_name, parent_doctype, parent_name):
        hook_cmd = frappe.get_hooks().get("file_name_generator")
        if hook_cmd:
            try:
                k = frappe.get_attr(hook_cmd[0])(
                    file_name=file_name,
                    parent_doctype=parent_doctype,
                    parent_name=parent_name,
                )
                if k:
                    return k
            except Exception:
                pass

        file_name = file_name.replace(" ", "_")
        file_name = self.strip_special_chars(file_name)

        return file_name

    def strip_special_chars(self, file_name):
        regex = re.compile("[^0-9a-zA-Z._-]")
        file_name = regex.sub("", file_name)
        return file_name

    def upload_files_to_s3_with_key(
        self, file_path, file_name, is_private, parent_doctype, parent_name
    ):
        mime_type = magic.from_file(file_path, mime=True)
        key = self.key_generator(file_name, file_path, parent_doctype, parent_name)
        content_type = mime_type
        try:
            extra_args = {
                "ContentType": content_type,
                "Metadata": {
                    "ContentType": content_type,
                    "file_name": file_name,
                },
            }

            if not is_private:
                extra_args["ACL"] = "public-read"

            self.S3_CLIENT.upload_file(file_path, self.BUCKET, key, ExtraArgs=extra_args)

        except boto3.exceptions.S3UploadFailedError as e:
            error_message = str(e)
            if re.search(r"accessdenied|blockpublicacls", error_message, re.IGNORECASE):
                frappe.throw(
                    _(
                        "File Upload Failed because you don't have permission to upload "
                        "public files. Please check your S3 bucket settings. <br>Error: {0}"
                    ).format(error_message)
                )
            else:
                frappe.throw(
                    _("File Upload Failed. Please try again. <br>Error: {0}").format(
                        error_message
                    )
                )

        return key

    def key_generator(self, file_name, file_path, parent_doctype, parent_name):
        hook_cmd = frappe.get_hooks().get("build_s3_object_key")
        if hook_cmd:
            try:
                k = frappe.get_attr(hook_cmd[0])(
                    self.folder_name,
                    file_path=file_path,
                    file_name=file_name,
                    parent_doctype=parent_doctype,
                    parent_name=parent_name,
                )
                if k:
                    return k
            except Exception:
                pass

        # The random prefix keeps two files of the same name from overwriting each other.
        key = "".join(
            random.choice(
                string.ascii_uppercase + string.digits) for _ in range(8)
        )

        today = datetime.datetime.now()
        year = today.strftime("%Y")
        month = today.strftime("%m")
        day = today.strftime("%d")

        parts = [year, month, day, parent_doctype, key + "_" + file_name]
        if self.folder_name:
            parts.insert(0, self.folder_name)

        return "/".join(parts)

    def get_url(self, key, file_name=None):
        if self.s3_settings_doc.signed_url_expiry_time:
            self.signed_url_expiry_time = self.s3_settings_doc.signed_url_expiry_time
        else:
            self.signed_url_expiry_time = 120

        params = {"Bucket": self.BUCKET, "Key": key}

        if file_name:
            params["ResponseContentDisposition"] = "filename={}".format(file_name)

        url = self.S3_CLIENT.generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=self.signed_url_expiry_time,
        )

        return url

    def read_file_from_s3(self, key):
        obj = self.S3_CLIENT.get_object(Bucket=self.BUCKET, Key=key)
        file_data = obj["Body"].read()

        return file_data

    def delete_from_s3(self, key):
        if self.BUCKET and self.s3_settings_doc.delete_file_from_cloud:
            try:
                self.S3_CLIENT.delete_object(
                    Bucket=self.BUCKET,
                    Key=key,
                )
            except ClientError:
                frappe.throw(_("Access denied: Could not delete file"))
