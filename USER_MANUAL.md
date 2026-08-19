# S3 File Storage — User Manual

A guide for functional consultants and system administrators. No coding knowledge needed.

**Contents**

1. [What this app does](#1-what-this-app-does)
2. [Installation](#2-installation)
3. [What to collect from your AWS team](#3-what-to-collect-from-your-aws-team)
4. [Configuring S3 File Settings](#4-configuring-the-s3-file-settings-doctype)
5. [What changes in the File DocType](#5-what-changes-in-the-file-doctype)
6. [Public vs Private files](#6-public-vs-private-files--the-key-decision)
7. [AWS permissions required](#7-aws-permissions-required)
8. [Migrating files already on the server](#8-migrating-files-already-on-the-server)
9. [Day-to-day behaviour](#9-day-to-day-behaviour)
10. [Troubleshooting](#10-troubleshooting)
11. [Things to plan for](#11-things-to-plan-for)
12. [Go-live checklist](#12-go-live-checklist)

---

## 1. What this app does

Normally every file attached in Frappe/ERPNext is saved on the server's own disk. As attachments pile up, the disk fills and backups get heavy and slow.

This app moves those files to an **Amazon S3 bucket** instead.

**When a user uploads a file:**

1. The user attaches it the usual way — Attach button, Attach field, image field, or drag & drop.
2. The app copies the file to your S3 bucket.
3. The app updates the File record to point at S3.
4. **The local copy on the server is deleted.**

To the end user nothing looks different: they click the attachment and it opens. Only the storage location changes.

> **Important:** step 4 is permanent. Once a file is on S3 the server has no copy of it. Your S3 bucket becomes the single source of truth for attachments, so bucket backup and versioning become your responsibility. Turn on **S3 Versioning** before go-live.

---

## 2. Installation

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO
bench --site your-site install-app s3_file_storage
```

After install, search the awesome bar for **S3 File Settings**.

---

## 3. What to collect from your AWS team

| What you need | Example |
|---|---|
| S3 bucket name | `mycompany-erp-files` |
| Bucket region code | `ap-south-1` |
| Access Key ID of an IAM user | `AKIA...` |
| Secret Access Key of that IAM user | `wJalr...` |

[Section 7](#7-aws-permissions-required) lists exactly which permissions that IAM user needs — share it with your cloud team.

---

## 4. Configuring the "S3 File Settings" DocType

Open **S3 File Settings**. Only users with the **System Manager** role can view or edit it. It is a Single DocType — one settings record for the whole site.

### 4.1 General Configuration

| Field | What it does |
|---|---|
| **Delete file from cloud** | What happens on S3 when someone deletes an attachment in Frappe.<br>**Unchecked (default)** — the Frappe File record goes, the S3 object stays forever. Safer, but S3 storage keeps growing.<br>**Checked** — the S3 object is deleted too. Cleaner, but the file is gone for good. |

> If you enable **Delete file from cloud**, enable S3 Versioning as well. Versioning means a deleted object can still be recovered by your cloud team.

### 4.2 AWS credentials

| Field | What to enter |
|---|---|
| **Bucket Name** | The bucket name exactly as it appears in AWS. |
| **AWS Key** | Access Key ID of the IAM user. Stored encrypted. |
| **AWS Secret** | Secret Access Key. Stored encrypted. |
| **S3 Bucket Region Name** | The bucket's region code, e.g. `ap-south-1`. Must match the bucket or uploads fail. |
| **Folder Name** | Optional prefix inside the bucket where all files go, e.g. `erp-prod`. Useful when one bucket serves several sites (`erp-prod`, `erp-uat`). Leave blank to store at the bucket root. |

> **Tip:** leave AWS Key and Secret blank only if your infra team has attached an AWS role to the server (EC2 instance profile / IRSA). The app will then use that role automatically.

### 4.3 Private file access

These two fields apply to **private** files only (see [Section 6](#6-public-vs-private-files--the-key-decision)).

| Field | What it does |
|---|---|
| **Download File without Signed URL** | **Unchecked (recommended)** — clicking a private attachment redirects the browser to a temporary S3 link. Fast, and the file never passes through your server.<br>**Checked** — your Frappe server fetches the file from S3 and streams it to the user. The bucket is never exposed to the browser, but every download consumes server bandwidth and memory. Choose this only if policy forbids handing out S3 links. |
| **Signed URL expiry time** | Shown only when the above is unchecked. How many **seconds** the temporary S3 link stays valid. Default `300` (5 minutes). Shorter is safer; keep it long enough for large files to finish downloading. |

Either way, the user must be logged in and must have permission to read the document the file is attached to.

### 4.4 Migrate Existing Files

A button that pushes files already sitting on the server disk up to S3. Used once, at go-live. See [Section 8](#8-migrating-files-already-on-the-server).

### 4.5 Doctype Configuration — choosing which documents use S3

The most important functional decision. Two fields work together:

- **Ignore Mapped Doctypes** (checkbox)
- **S3 Doctype Mapping** (table with one column, *Mapped Doctype*)

| Ignore Mapped Doctypes | The table means |
|---|---|
| **Checked (default)** | **Blocklist** — everything goes to S3 **except** the DocTypes listed. |
| **Unchecked** | **Allowlist** — **only** attachments on the listed DocTypes go to S3. Everything else stays on the local disk exactly as before. |

**Example A — everything to S3 except HR documents**

- Ignore Mapped Doctypes: ✔ checked
- S3 Doctype Mapping: `Employee`, `Employee Onboarding`

**Example B — pilot with sales documents only**

- Ignore Mapped Doctypes: ☐ unchecked
- S3 Doctype Mapping: `Sales Invoice`, `Delivery Note`, `Quotation`

**How matching works:**

- The DocType checked is the document the file is **attached to**, not the file itself. A PDF on `SINV-0001` is matched against `Sales Invoice`.
- Files uploaded from the **File Manager**, not attached to any document, are matched against the DocType **`File`**. If you use an allowlist and want those on S3 too, add `File` to the table.
- Changing these settings never moves files already uploaded. It only affects future uploads and future migration runs.
- Excluded DocTypes keep their attachments on the server disk, behaving exactly as before the app was installed.

---

## 5. What changes in the File DocType

The app adds **no new fields** to File. It rewrites the values of existing fields after upload. This matters for reports, print formats, and integrations that read File records.

| File field | Before (local disk) | After (on S3) |
|---|---|---|
| **file_url** — public file | `/files/invoice.pdf` | A direct S3 URL:<br>`https://s3.ap-south-1.amazonaws.com/mybucket/erp/2026/07/31/Sales Invoice/AB12CD34_invoice.pdf` |
| **file_url** — private file | `/private/files/invoice.pdf` | A Frappe API link:<br>`/api/method/s3_file_storage.controller.generate_file?key=...&file_name=invoice.pdf` |
| **file_name** | As uploaded, e.g. `My Invoice (final).pdf` | Cleaned: spaces become `_`, and anything other than letters, digits, `.`, `_`, `-` is removed → `My_Invoicefinal.pdf` |
| **folder** | Wherever the user put it | Forced to `Home/Attachments` |
| **content_hash** | A checksum of the file contents | **Reused to hold the S3 object key** — the file's path inside the bucket |
| **is_private** | Set at upload | Unchanged — this is what decides public vs private handling |
| **file_size** | Actual size | Unchanged |

**Also updated automatically:**

- If the file went into an **Attach** or **Attach Image** field, that field is repointed to the S3 URL — whether the field sits on the document itself, on a **row of one of its child tables**, or on a Settings (Single) page.
- If the parent DocType has an **image field** (the document's picture, e.g. Item Image), it is repointed too.

Only fields that still hold the file's old local path are touched, so attaching one file never overwrites a field pointing at a different one.

> **Note on child tables:** when a file is attached to a field inside a grid row, Frappe records the **parent** document on the File record (e.g. `Sales Invoice` / `SINV-0001`), not the child row. On a normal upload the browser writes the new URL into the row itself. During **migration** there is no browser involved, so the app locates the correct row by the old path it still holds and updates it there — the same applies to fields on Settings (Single) pages.

**Two consequences to remember:**

1. **`content_hash` is no longer a checksum** on S3-stored files. Don't use it for duplicate detection or integrity checks on those records, and never clear or edit it — the app cannot locate or delete the file in S3 without it.
2. **Public file URLs are permanent and need no login.** Anyone with the link can open the file. See [Section 6](#6-public-vs-private-files--the-key-decision).

**Where files land in the bucket (default layout):**

```
<Folder Name>/<YYYY>/<MM>/<DD>/<Parent DocType>/<8-char random>_<file name>
```

Example: `erp-prod/2026/07/31/Sales Invoice/AB12CD34_invoice.pdf`

The random prefix stops two files with the same name from overwriting each other. A developer can change this layout with the `build_s3_object_key` hook — see the README.

---

## 6. Public vs Private files — the key decision

Frappe already has this concept: every attachment is either **public** or **private** (the `is_private` flag). This app honours that flag and treats the two very differently.

| | **Public file** | **Private file** |
|---|---|---|
| Link points to | S3 directly | A Frappe endpoint |
| Who can open it | **Anyone on the internet** with the URL, no login | Only a logged-in user **who can read the attached document** |
| How it is served | S3 serves it | Frappe checks permission, then issues a short-lived S3 link (or streams the file itself) |
| Link lifetime | Permanent | Expires after *Signed URL expiry time* |
| Bucket must allow public reads | **Yes** | **No** — bucket stays fully locked down |
| Use for | Website images, logos, brochures, product photos, public catalogues | Invoices, contracts, salary slips, KYC documents, ID proofs — anything confidential |

**Recommendation: keep everything private** unless a file genuinely has to be readable from a public website. Private costs you nothing functionally, and the bucket can stay completely closed to the internet.

**How the private permission check works:** when someone opens a private attachment, the app finds the File record for that S3 key and applies Frappe's standard File permission rules — which check read access on the document the file is attached to. So a Sales User who cannot open a particular Salary Slip cannot download its attachment either, even if someone forwards them the link. Requests without a login, or for a key that has no matching File record, are refused.

---

## 7. AWS permissions required

AWS does not use "roles" the way Frappe does. You need an **IAM user** (or an AWS role) carrying a **policy**, plus the right **bucket-level settings**. What's needed depends on whether you will store public files.

### 7.1 Private files only — recommended

**Bucket settings in AWS:**

- **Block all public access:** leave **ON** (fully blocked). This is the AWS default.
- **Object Ownership:** `Bucket owner enforced` (ACLs disabled). Also the AWS default.
- No public bucket policy needed.

**IAM policy** for the user whose key you paste into S3 File Settings:

| Permission | Why |
|---|---|
| `s3:PutObject` | Upload attachments |
| `s3:GetObject` | Read files back and sign download links |
| `s3:DeleteObject` | Only if you tick **Delete file from cloud** |

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::YOUR-BUCKET-NAME/*"
    }
  ]
}
```

### 7.2 If you also need public files

The app marks public files with the S3 ACL `public-read`. Modern AWS defaults reject ACLs outright, so your cloud team must change **three** things:

**Bucket settings:**

1. **Object Ownership** → `Bucket owner preferred` (**ACLs enabled**).
2. **Block Public Access** → switch **off** at least *Block public access to buckets and objects granted through new access control lists (ACLs)*.
3. Leave the remaining Block Public Access toggles on wherever you can.

**IAM policy** — as above **plus one extra permission:**

| Permission | Why |
|---|---|
| `s3:PutObjectAcl` | Mark the uploaded object publicly readable |

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:PutObjectAcl",
        "s3:GetObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::YOUR-BUCKET-NAME/*"
    }
  ]
}
```

**A safer alternative worth raising with your cloud team:** keep the bucket fully private and serve public files through **CloudFront** with an Origin Access Control. This needs a small code change to the URL the app writes, so treat it as a technical enhancement rather than a configuration option.

### 7.3 Mixed setup — the common case

Most implementations land here: the bucket is configured as in 7.2 so it *can* serve public content, but only a handful of files — website images — are actually uploaded as public. Everything else is private. That is fine and is the intended design.

### 7.4 Frappe-side roles (not AWS)

| Task | Role needed in Frappe |
|---|---|
| View or edit **S3 File Settings** | **System Manager** |
| Run **Migrate Existing Files** | **System Manager** |
| Upload attachments | None special — normal write access to the document |
| Open a private attachment | Logged in **and** read access to the attached document |
| Open a public attachment | None — the S3 link works for anyone |

---

## 8. Migrating files already on the server

Run this once, after you have configured and tested the settings. It finds files still on the local disk and pushes them to S3.

### Before you start

1. **Take a full backup including files:**
   ```bash
   bench --site your-site backup --with-files
   ```
   Migration deletes local files and cannot be undone.
2. **Test on a staging copy of your site first.** Confirm a sample of documents still open correctly there.
3. **Verify your settings** by attaching one test file and checking that it appears in the bucket.
4. **Set your Doctype Configuration first** — migration respects the same include/exclude rules as normal uploads.
5. **Schedule a maintenance window.** On a site with many attachments this runs for a long time.

### Running it

1. Open **S3 File Settings**.
2. Click **Migrate Existing Files**.
3. Confirm the warning ("Existing files from this instance will be deleted once pushed to S3").
4. A progress bar appears at the top of the form. Leave the tab open.
5. When it finishes you get either a green "*N* file(s) migrated to S3", or an orange summary showing how many failed.
6. A background job then repairs Attach and Attach Image field values that still pointed at the old local paths — on regular documents, child table rows, and Settings pages alike.

### For large sites

The button runs inside a browser request and can hit a gateway timeout on sites with many thousands of files. If that happens, or if you know the volume is large, run it from the server instead:

```bash
bench --site your-site console
```
```python
from s3_file_storage.controller import migrate_existing_files
migrate_existing_files()
```

This has no timeout. It prints a summary like `{'migrated': 4821, 'failed': 2, 'total': 4900}` when done.

### After migration

- **Check the counts.** If `failed` is not zero, open **Error Log** and filter for titles starting with *"S3 migration failed for File"*. Each entry names the File record and the reason. Individual failures do not stop the run — the remaining files still migrate.
- **Spot-check documents** of different types: an image field, an Attach field, a plain attachment, a child-table attachment, and a private document.
- **Re-running is safe.** Files already on S3 are detected and skipped, so you can fix the cause of a failure and run migration again to pick up only the stragglers.

---

## 9. Day-to-day behaviour

Once configured, nobody needs to do anything differently.

| Action | What happens |
|---|---|
| User attaches a file | Uploaded to S3 automatically; local copy removed |
| User opens a public attachment | Opens straight from S3 |
| User opens a private attachment | Frappe checks their permission, then serves the file |
| User deletes an attachment | File record removed; S3 object removed too **only if** *Delete file from cloud* is ticked |
| Attachment on an excluded DocType | Stays on the local server disk, as before |
| Backup (`bench backup --with-files`) | Captures only files still on local disk. **S3-stored files are not in the Frappe backup** — they are protected by S3 versioning and your bucket's own backup policy |

---

## 10. Troubleshooting

| Symptom | Likely cause / what to check |
|---|---|
| *"File Upload Failed because you don't have permission to upload public files"* | You are uploading a **public** file but the bucket blocks ACLs. Either upload it as private, or apply the [Section 7.2](#72-if-you-also-need-public-files) bucket settings and add `s3:PutObjectAcl`. |
| *"File Upload Failed. Please try again."* with an AWS error | Wrong bucket name, wrong region, wrong or expired access key, or the IAM policy is missing `s3:PutObject`. |
| Public attachment gives *Access Denied* from S3 | The object was not marked publicly readable — usually a missing `s3:PutObjectAcl`, or ACLs disabled on the bucket. |
| Private attachment gives *Access Denied* / *Not Permitted* in Frappe | Expected if the user cannot read the attached document. If it happens to someone who *should* have access, check their role permissions on the parent DocType. |
| Private attachment link stops working after a while | The signed URL expired. Reopen the document to get a fresh link, or raise *Signed URL expiry time*. |
| *"Access denied: Could not delete file"* when deleting an attachment | IAM policy is missing `s3:DeleteObject` while **Delete file from cloud** is ticked. |
| Files still landing on the local disk | Check **Doctype Configuration** — the parent DocType is excluded, or missing from your allowlist. |
| An old attachment shows a broken link | It predates the app and was never migrated. Run migration, or re-upload it. |
| Migration reported failures | **Error Log** → filter for *"S3 migration failed for File"*. Fix the cause and re-run; already-migrated files are skipped. |
| File name differs from what the user uploaded | Expected. Spaces become underscores and special characters are stripped — see [Section 5](#5-what-changes-in-the-file-doctype). |

---

## 11. Things to plan for

Not defects — design consequences worth deciding on before go-live.

1. **Your Frappe backup no longer contains attachments.** `bench backup --with-files` only captures what's on local disk. Protect the bucket separately: enable **S3 Versioning**, and consider a lifecycle or replication policy.
2. **Public files are public forever.** There is no expiry and no login on those URLs. Once a link leaks, it works until the object is deleted. Only upload as public what could safely sit on your website.
3. **`content_hash` no longer means "checksum"** on S3-stored files. Tell anyone writing reports or integrations against the File DocType.
4. **Deletion is one-way when *Delete file from cloud* is on.** Pair it with S3 Versioning so recovery stays possible.
5. **Region and bucket cannot be changed casually.** Existing File records store keys relative to the configured bucket. Changing the bucket later orphans every existing attachment unless the objects are copied across first.
6. **Egress costs.** Every download pulls data out of S3. With *Download File without Signed URL* ticked, it flows through your server too — doubling bandwidth usage. The signed-URL mode (default) is cheaper and faster.

---

## 12. Go-live checklist

- [ ] Bucket created; name and region noted
- [ ] **S3 Versioning enabled** on the bucket
- [ ] IAM user created with the correct policy ([Section 7](#7-aws-permissions-required))
- [ ] Decided: private only, or public files needed too?
- [ ] Bucket public-access settings adjusted if public files are needed
- [ ] App installed on the site
- [ ] **S3 File Settings** filled in: bucket, key, secret, region, folder
- [ ] **Doctype Configuration** decided — blocklist or allowlist
- [ ] **Delete file from cloud** decision made
- [ ] **Signed URL expiry time** set (default 300s is fine)
- [ ] Test private upload — attaches and opens correctly
- [ ] Test private upload — a user *without* document access is correctly refused
- [ ] Test public upload — opens correctly (if using public files)
- [ ] Full backup taken (`bench backup --with-files`)
- [ ] Migration rehearsed on a staging copy, results spot-checked
- [ ] Maintenance window booked for production migration
