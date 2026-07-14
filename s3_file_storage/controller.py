from __future__ import unicode_literals

import datetime
import os
import random
import re
import string
import boto3
import magic
import mimetypes

from botocore.client import Config
from botocore.exceptions import ClientError

import frappe




class S3Operations(object):

    def __init__(self):
        """
        Function to initialise the aws settings from frappe S3 File Settings
        doctype.
        """
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
                's3',
                aws_access_key_id=aws_key,
                aws_secret_access_key=aws_secret,
                region_name=self.s3_settings_doc.region_name,
                config=Config(signature_version='s3v4')
            )
        else:
            self.S3_CLIENT = boto3.client(
                's3',
                region_name=self.s3_settings_doc.region_name,
                config=Config(signature_version='s3v4')
            )
        self.BUCKET = self.s3_settings_doc.bucket_name
        self.folder_name = self.s3_settings_doc.folder_name

    def upload_files_to_s3_with_key(
        self, file_path, file_name, is_private, parent_doctype, parent_name
    ):
        """
        Uploads a new file to S3.
        Strips the file extension to set the content_type in metadata.
        """
        mime_type = magic.from_file(file_path, mime=True)
        key = self.key_generator(file_name, file_path, parent_doctype, parent_name)
        content_type = mime_type
        try:
            extra_args = {
                "ContentType": content_type,
                "Metadata": {
                    "ContentType": content_type,
                    "file_name": file_name
                }
            }

            if not is_private:
                extra_args["ACL"] = 'public-read'

            self.S3_CLIENT.upload_file(file_path, self.BUCKET, key, ExtraArgs=extra_args)

        except boto3.exceptions.S3UploadFailedError as e:
            error_message = str(e)
            # Check for specific words in the error
            if re.search(r'accessdenied|blockpublicacls', error_message, re.IGNORECASE):
                frappe.throw(frappe._(
                    "File Upload Failed because you don't have permission to upload public files. "
                    f"Please check your S3 bucket settings. <br>Error: {error_message}"
                ))
            else:
                frappe.throw(frappe._(f"File Upload Failed. Please try again. <br>Error: {error_message}"))

        return key
    

    def key_generator(self, file_name, file_path, parent_doctype, parent_name):
        """
        Generate keys for s3 objects uploaded with file name attached.
        """
        hook_cmd = frappe.get_hooks().get("build_s3_object_key")
        if hook_cmd:
            try:
                k = frappe.get_attr(hook_cmd[0])(
                    self.folder_name,
                    file_path=file_path,
                    file_name=file_name,
                    parent_doctype=parent_doctype,
                    parent_name=parent_name
                )
                if k:
                    return k
            except:
                pass

        key = ''.join(
            random.choice(
                string.ascii_uppercase + string.digits) for _ in range(8)
        )

        today = datetime.datetime.now()
        year = today.strftime("%Y")
        month = today.strftime("%m")
        day = today.strftime("%d")

        final_key = ""
        doc_path = None

        if not doc_path:
            if self.folder_name:
                final_key = self.folder_name + "/" + year + "/" + month + \
                    "/" + day + "/" + parent_doctype + "/" + key + "_" + \
                    file_name
            else:
                final_key = year + "/" + month + "/" + day + "/" + \
                    parent_doctype + "/" + key + "_" + file_name
        else:
            final_key = doc_path + '/' + key + "_" + file_name
        
        return final_key
    

    def file_name_generator(self, file_name, parent_doctype, parent_name):
        """
        Generate file name for s3 object.
        """
        hook_cmd = frappe.get_hooks().get("file_name_generator")
        if hook_cmd:
            try:
                k = frappe.get_attr(hook_cmd[0])(
                    file_name=file_name,
                    parent_doctype=parent_doctype,
                    parent_name=parent_name
                )
                if k:
                    return k
            except:
                pass

        file_name = file_name.replace(' ', '_')
        file_name = self.strip_special_chars(file_name)
        
        return file_name
    
    def strip_special_chars(self, file_name):
        """
        Strips file charachters which doesnt match the regex.
        """
        regex = re.compile('[^0-9a-zA-Z._-]')
        file_name = regex.sub('', file_name)
        return file_name


    def delete_from_s3(self, key):
        """ Delete file from s3"""
        if self.s3_settings_doc.delete_file_from_cloud:
            try:
                self.S3_CLIENT.delete_object(
                    Bucket=self.s3_settings_doc.bucket_name,
                    Key=key
                )
            except ClientError:
                frappe.throw(frappe._("Access denied: Could not delete file"))

    def read_file_from_s3(self, key):
        """
        Function to read file from a s3 file.
        """

        obj = self.S3_CLIENT.get_object(Bucket=self.BUCKET, Key=key)
        file_data = obj["Body"].read()
        
        return file_data

    def get_url(self, key, file_name=None):
        """
        Return url.

        :param bucket: s3 bucket name
        :param key: s3 object key
        """
        if self.s3_settings_doc.signed_url_expiry_time:
            self.signed_url_expiry_time = self.s3_settings_doc.signed_url_expiry_time # noqa
        else:
            self.signed_url_expiry_time = 120
            
        params = { 'Bucket': self.BUCKET, 'Key': key, }
        
        if file_name:
            params['ResponseContentDisposition'] = 'filename={}'.format(file_name)

        url = self.S3_CLIENT.generate_presigned_url(
            'get_object',
            Params=params,
            ExpiresIn=self.signed_url_expiry_time,
        )

        return url


@frappe.whitelist()
def file_upload_to_s3(doc, method, s3_key_cache=None):
    """Check and upload files to S3, then update File and parent records.

    `s3_key_cache` is an optional dict shared across calls (used during
    bulk migration) that maps a physical file's dedup key — (content_hash,
    is_private), falling back to file_url — to its already-uploaded S3 key.
    Duplicate File records pointing at the same physical file reuse the
    cached key instead of re-uploading, since the local file may already
    have been removed by the first record's processing.
    """
    if not doc or not doc.file_url:
        return

    if s3_file_regex_match(doc.file_url):
        return

    # Scope by is_private too: Frappe's own dedup (File.save_file /
    # validate_duplicate_entry) never matches a public and a private file
    # against each other even if their content_hash is identical, since
    # they live on disk in separate directories with different ACL needs.
    dedup_key = (doc.content_hash, doc.is_private) if doc.content_hash else doc.file_url

    s3_upload = S3Operations()
    parent_doctype = doc.attached_to_doctype or "File"
    parent_name = doc.attached_to_name
    ignore_mapped_doctypes = bool(s3_upload.s3_settings_doc.get("ignore_mapped_doctypes"))
    mapped_doctypes = {
        d.mapped_doctype
        for d in s3_upload.s3_settings_doc.get("s3_doctype_mapping", [])
    }

    if (parent_doctype in mapped_doctypes) == ignore_mapped_doctypes:
        return

    site_path = frappe.utils.get_site_path()
    file_path = (
        f"{site_path}/public{doc.file_url}"
        if not doc.is_private
        else f"{site_path}{doc.file_url}"
    )

    # Generate new file name
    doc.file_name = s3_upload.file_name_generator(
        doc.file_name, parent_doctype, parent_name
    )

    cached_key = s3_key_cache.get(dedup_key) if s3_key_cache is not None else None
    if cached_key:
        key = cached_key
    else:
        key = s3_upload.upload_files_to_s3_with_key(
            file_path,
            doc.file_name,
            doc.is_private,
            parent_doctype,
            parent_name,
        )
        if s3_key_cache is not None:
            s3_key_cache[dedup_key] = key

    # Build S3 file URL
    if doc.is_private:
        api_method = "s3_file_storage.controller.generate_file"
        doc.file_url = f"/api/method/{api_method}?key={key}&file_name={doc.file_name}"
    else:
        doc.file_url = f"{s3_upload.S3_CLIENT.meta.endpoint_url}/{s3_upload.BUCKET}/{key}"

    # Update File record in one query
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

    # Update image field if exists
    if parent_doctype and parent_name:
        meta = frappe.get_meta(parent_doctype)
        image_field = meta.get("image_field")
        if image_field:
            frappe.db.set_value(parent_doctype, parent_name, image_field, doc.file_url, update_modified=False)

        # Update attached field if applicable
        attached_field = doc.get("attached_to_field")
        if not method and attached_field and frappe.db.has_column(parent_doctype, attached_field):
            frappe.db.set_value(parent_doctype, parent_name, attached_field, doc.file_url, update_modified=False)
    
    # Remove local file
    if os.path.exists(file_path):
        os.remove(file_path)

    frappe.db.commit()

    return doc.file_url


@frappe.whitelist()
def generate_file(key=None, file_name=None):
    """
    Function to download file from s3.
    """
    if key:
        s3_upload = S3Operations()
        if s3_upload.s3_settings_doc.get("download_file_without_signed_url"):
            file_data = s3_upload.read_file_from_s3(key)

            # Ensure it's bytes (safety net)
            if not isinstance(file_data, (bytes, bytearray)):
                file_data = bytes(file_data, "utf-8")

            # Guess mimetype from filename
            guessed_mimetype, _ = mimetypes.guess_type(file_name or key)
            mimetype = guessed_mimetype or "application/octet-stream"

            frappe.local.response.filename = file_name or key.split("/")[-1]
            frappe.local.response.type = "download"
            frappe.local.response.filecontent = file_data
            frappe.local.response["Content-Type"] = mimetype
            frappe.local.response["Content-Disposition"] = (
                f'attachment; filename="{frappe.local.response.filename}"'
            )
        else:
            signed_url = s3_upload.get_url(key, file_name)
            frappe.local.response["type"] = "redirect"
            frappe.local.response["location"] = signed_url
    else:
        frappe.local.response['body'] = "Key not found."
    return


def upload_existing_files_s3(name):
    """
    Function to upload all existing files.
    """
    try:
        doc = frappe.get_doc("File", name)
        return file_upload_to_s3(doc, None, s3_key_cache)
    except frappe.DoesNotExistError:
        return


def s3_file_regex_match(file_url):
    """
    Match the public file regex match.
    """
    return re.match(
        r'^(https:|/api/method/frappe_s3_attachment.controller.generate_file)',
        file_url
    )


@frappe.whitelist()
def migrate_existing_files():
    """
    Function to migrate the existing files to s3.
    """

    files_list = frappe.get_all(
        'File',
        fields=['name', 'file_url']
    )

    total_files = len(files_list)
    s3_key_cache = {}
    url_map = {}

    for idx, file in enumerate(files_list, 1):
        old_url = file['file_url']
        if old_url:
            if not s3_file_regex_match(old_url):
                new_url = upload_existing_files_s3(file['name'], s3_key_cache)
                if new_url and new_url != old_url:
                    url_map[old_url] = new_url

        frappe.publish_realtime(
            "file_migration_progress",
            {
                "current_file": idx,
                "total_files": total_files,
                "progress": (idx * 100) / total_files
            },
        )

    if url_map:
        frappe.enqueue(
            "s3_file_storage.controller.update_attach_fields_after_migration",
            queue="long",
            timeout=6000,
            url_map=url_map,
        )

    return True


def get_attach_fields():
    """All (doctype, fieldname) pairs for Attach / Attach Image fields,
    across standard doctypes (including child tables) and Custom Fields.
    """
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


def update_attach_fields_after_migration(url_map):
    """Background job: fix Attach/Attach Image values left pointing at the
    pre-migration local file path.
    """
    if not url_map:
        return

    old_urls = list(url_map.keys())

    for doctype, fieldname in get_attach_fields():
        meta = frappe.get_meta(doctype)
        if not meta.istable:
            continue
        if not frappe.db.has_column(doctype, fieldname):
            continue

        try:
            rows = frappe.db.sql(
                f"""SELECT `name`, `{fieldname}` AS value
                    FROM `tab{doctype}`
                    WHERE `{fieldname}` IN %(urls)s""",
                {"urls": old_urls},
                as_dict=True,
            )
        except Exception:
            frappe.log_error(
                title="S3 migration: attach field scan failed",
                message=frappe.get_traceback(),
            )
            continue

        for row in rows:
            new_url = url_map.get(row.value)
            if new_url:
                frappe.db.set_value(
                    doctype, row.name, fieldname, new_url, update_modified=False
                )

    frappe.db.commit()


def delete_from_cloud(doc, method):
    """Delete file from s3"""
    if not doc.flags.in_delete:
        return
    
    s3 = S3Operations()
    s3.delete_from_s3(doc.content_hash)


@frappe.whitelist()
def ping():
    """
    Test function to check if api function work.
    """
    return "pong"
