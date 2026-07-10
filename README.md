## S3 File Storage

This app helps you store files from Frappe into an S3 bucket easily and securely.


## Generating Custom File Name and Path Structure for S3

This guide explains how to use the **`s3_key_generator` hook** in a custom Frappe/ERPNext app to define your own **file name and folder path structure** when uploading files to Amazon S3.

---

## 📌 Why Use `s3_key_generator`?
By default, file paths in S3 are auto-generated. However, in some cases, you may want to:
- Organize files under specific folders per **Doctype** or **record**.
- Generate file names dynamically (e.g., timestamp-based, UUID-based, or Doctype-based).
- Implement custom naming conventions for better file management.

The `s3_key_generator` hook gives you full control over **how file paths are structured**.

---

## ⚙️ How It Works
When a file is uploaded, the S3 storage handler looks for the hook:

```python
hook_cmd = frappe.get_hooks().get("s3_key_generator")
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
            return k.rstrip('/').lstrip('/')
    except:
        pass
```

If the hook is present, it calls your **custom function** which must return the **final S3 key (path + filename)**.

---

## 🛠️ Implementation Steps

### 1. Define Hook in `hooks.py`
In your custom app, add the following entry inside `hooks.py`:

```python
# hooks.py
s3_key_generator = ["my_app.s3_utils.custom_s3_key"]
```

---

### 2. Create Custom S3 Key Generator Function
Inside your app, create a utility function that will generate the **custom file path**.

Example (`s3_utils.py`):

```python
import os
import frappe
from datetime import datetime

def custom_s3_key(folder_name, file_path=None, file_name=None, parent_doctype=None, parent_name=None):
    """
    Generate a custom S3 file path.

    Args:
        folder_name (str): Default folder name (from system config).
        file_path (str): Local file path before upload.
        file_name (str): Original file name.
        parent_doctype (str): Doctype where the file is attached.
        parent_name (str): Document name where the file is attached.

    Returns:
        str: Custom S3 key (path + filename).
    """

    # Example: organize files by doctype, record, and timestamp
    date_str = datetime.now().strftime("%Y/%m/%d")

    # Sanitize file name
    base_name, ext = os.path.splitext(file_name or "file")
    safe_name = frappe.scrub(base_name)

    return f"{parent_doctype}/{parent_name}/{date_str}/{safe_name}{ext}"
```

This will store files in a structure like:

```
Item/ITEM-0001/2025/08/28/manual_file.pdf
```

---

### 3. Upload Files
When a file is uploaded in Frappe, the above hook will be triggered and the file will be saved in S3 using the **custom path**.

---

## ✅ Example Use Cases
- **Per Doctype & Record**  
  Store files under their Doctype → Record name.  
  `Sales Invoice/SINV-0001/attachments/invoice.pdf`

- **Timestamped Storage**  
  Store files by date for easy archival.  
  `2025/08/28/file_12345.pdf`

- **Randomized / UUID Naming**  
  Useful for avoiding collisions.  
  `uploads/uuid/9d2c4e38-7e21-44d8.pdf`

---

## 🚨 Notes
- Your custom function **must return a string** (the S3 key).
- The system automatically ensures no leading/trailing `/`.
- If the hook fails or is not defined, the **default key generator** will be used.
- You can log/debug your function with `frappe.logger()`.

---

## 📖 Summary
By using the `s3_key_generator` hook, you can **fully customize how files are organized in S3**.  
This helps in better structuring, easier search, and avoids conflicts in naming.

---


## Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app s3_file_storage
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/s3_file_storage
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit
