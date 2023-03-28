This RFC proposes a refactoring of the storage backend addons to make them based on Odoo
standard model (`ir.attachment`) instead of custom model.

In the following, the `storage_backend` addon will be renamed in `fs_storage` and
`storage.backend` will be renamed in `fs.storage`.

## Motivation

In the `storage_file` mainly provides a custom model `storage.file` which is used to
store the file content and metadata into a external file system.

Both share a lot of same fields. The not shared fields are mainly related to specific
functionality provided by either `storage.file` or `ir.attachment`.

Here it's a table with the fields of the `storage.file` model and the corresponding
field in the `ir.attachment` model:

| storage.file            | ir.attachment                              |
| ----------------------- | ------------------------------------------ |
| name                    | name                                       |
| url (computed)          | url                                        |
| url_path (computed)     |                                            |
| internal_url (computed) |                                            |
| slug (computed)         |                                            |
| relative_path           |                                            |
| file_size               | file_size                                  |
| human_file_size         | file_size (computed)                       |
| checksum                | checksum                                   |
| filename (computed)     |                                            |
| extension (computed)    |                                            |
| mimetype                | mimetype                                   |
| data                    | db_datas, raw (computed), datas (computed) |
| to_delete               |                                            |
| active                  |                                            |
| company_id              | company_id                                 |
| file_type               |                                            |
|                         | description                                |
|                         | res_name                                   |
|                         | res_model                                  |
|                         | res_field                                  |
|                         | res_id                                     |
|                         | type                                       |
|                         | public                                     |
|                         | access_token                               |
|                         | store_fname                                |
|                         | index_content                              |

The functional differences are:

- `storage.file` allows to access to the file content via 2 URLs stored into the
  database: `internal_url` and `url`. The `url` is the public URL to access to the file
  content. The `internal_url` is the URL to access to the file content from the same
  0doo's server. The `url` refers to the file into the external file system.
- `storage.file` is used to transparently store the file content into an external file
  system. When you manually create a record in the `storage.file` you can choose the
  external file system where the file content will be stored.
- `storage.file` is not transactional. (If a file is stored withing a transaction and
  the transaction is rolled back, the file will not be deleted from the external file
  system).
- `ir.attachment` allows to store the file content into the Odoo's filestore.
- `ir.attachment` is transactional. (If a file is stored withing a transaction and the
  transaction is rolled back, the file will be deleted from the filestore by a GC
  mechanism).
- `ir.attachment` can be transparently used to store content from fields of type
  `Binary`. This field type comes with a specific UI to upload/download.

## How can we reconcile both models?

### fs_attachment

Since the main difference between both models is the place where the file content is
stored, the idea is to extend the `ir.attachment` model to allow to store the file
content into an external file system. With the last changes in the `ir.attachment`
model, odoo provides now 3 methods that can be used to hook into the process of storing,
retrieving and deleting the file content. This methods are:

- `_file_read`
- `_file_write`
- `_file_delete`

Such an approach has already been implemented in addons from the camptocamp
odoo-clout-platform repository: https://github.com/camptocamp/odoo-cloud-platform

The idea is to use the same approach here but using the api provided by the fsspec
library through the new implementation of the `storage_backend` addon proposed in the
pull request: https://github.com/OCA/storage/pull/250

A new addon `fs_attachment` will be created to provide the glue between the
`ir.attachment` model and the `fs_storage` addon. A new field `code` will be added to
the `fs.storage` model to allow to choose the file system where the file content will be
stored. As it's done into the `base_attachment_object_storage` addon from C2C, it will
be possible to globally configure the default file system where the file content will be
stored for all the attachments.

### fs_file

The `storage.file` addon will be replaced by the new `fs_file` addon. This addon will
provide 1 new specialized field type: `FSFile()` This new field will be bases on the
`Binary` field type and enforce the use of the `ir.attachment` model to store the file
content.

The value of the field will be an object implementing the `io.RawIOBase` interface. This
object will also provides additional properties to access to access to the name (rw),
mimetype(r), size(r), url(r), internal_url(r) and the attachment record(r). It will also
implements the `__set_item__` method to allow to makes the following syntax possible:

```python
my_file = record.fs_file
my_file = b"content"
my_file.name = "new_name.txt"
```

The implementation of this class will use an `io.BytesIO` object as buffer to store
content in memory and act as a wrapper around this buffer to detect when the content is
modified and let know the field implementation that the content has been modified.

```python
import io
from odoo.addons.base.models.ir_attachment import IrAttachment

class FSFileBytesIO(io.RawIOBase):
    def __init__(self, attachment: IrAttachment = None) -> None:
        self._is_new = attachment is None
        self.buffer = io.BytesIO(attachment.raw if attachment else b"")
        self.dirty = False
        self._attachment = attachment

    def read(self, size: int = -1) -> bytes:
        return self.buffer.read(size)

    def write(self, b: bytes) -> int:
        self.dirty = True
        return self.buffer.write(b)

    def readinto(self, b: bytearray) -> int:
        return self.buffer.readinto(b)

    def getvalue(self) -> bytes:
        current_pos = self.buffer.tell()
        self.buffer.seek(0)
        value = self.buffer.read()
        self.buffer.seek(current_pos)
        return value

    @property
    def name(self) -> str | None:
        return self.buffer.name

    @name.setter
    def name(self, value: str) -> None:
        # the name should only be updatable while the file is not yet stored
        # TODO, we could also allow to update the name of the file and rename
        # the file in the external file system
        if self._is_new:
          self.buffer.name = value
        else:
          raise ValueError(
              "The name of the file can only be updated while the file is not "
              "yet stored")
    @property
    def mimetype(self) -> str | None:
        return self._attachment.mimetype if self._attachment else None

    @property
    def size(self) -> int:
        return self._attachment.size if self._attachment else 0

    @property
    def url(self) -> str | None:
        return self._attachment.url if self._attachment else None

    @property
    def internal_url(self) -> str | None:
        return self._attachment.internal_url if self._attachment else None

    @property
    def attachment(self) -> IrAttachment | None:
        return self._attachment

    def __getattr__(self, attr: str):
        return getattr(self.buffer, attr)

    def __setitem__(self, key: int, value: bytes) -> None:
        self.dirty = True
        self.buffer.seek(key)
        self.buffer.write(value)

```

Such an approach will allow to use the `FSFile()` field type in the same way as the any
other io stream and ease its usage with any library that can work with io streams. But
it will also support a naive usage like the following:

```python
# fs_file = FSFile(string="File", storage_code="fs_s3")
my_file = record.fs_file
my_file = b"content"
```

To initialize a not yet initialized `FSFile()` field with a new file the following
syntax can be used:

```python
record.fs_file = b"content"
```

Compared to the `Binary` field type, the `FSFile()` field will require 1 additional
parameter:

- `storage_code`: the code of the file system where the file content will be stored.

To avoid useless resources consumption when the field content is retrieved to be
displayed into the UI, the method `convert_to_read` will be overridden to return a url
to use to download the file content.

A new JS Widget will be created to allow to upload/download the file content as an url.
In the same spirit of minimizing the resource's consumption, this widget will not encode
into base64 the file content when a new content is uploaded and put this content into
the json document posted to odoo. Instead, it will call a new controller to upload the
file content and set as value of the field the new url when the form is saved prior to
the submission of the form.

To avoid to pollute our file system with files uploaded but not linked to any record in
the database due to a transaction rollback or some troubles when a form is submitted, a
GC mechanism will be implemented to delete orphan files.

The implementation of the `FSFile` field will be based on the `Binary` field but will
always put into the context the `storage_code`. This parameter will be used by the
`fs_attachment` addon to select the file system where the file content will be stored.
Since the fields.Binary field doesn't provide hooks to enrich the value dict used to
create or update the `ir.attachment` record, the context could be used to provide the
file name or any other information that should be stored into the `ir.attachment`
record.

(TODO explain how `FSFile()` field implementation will extend the `Binary` field
implementation to allow to deal transparently with `FSFileIByesIO` objects. Not sure if
it's possible by extending the `Binary` field implementation or if we will have to
create a new field type from scratch.)

### fs_image

The `storage.image` addon will be replaced by the new `fs_image` addon. It will at least
provides a new widget to allow the display of the image content from the url provided by
the `FSFile` field. If it were not for the automatic thumbnail creation mechanism, this
module could be summarised as the creation of 1 new field type: `FSImage()` and the
creation of new `FSImageBytesIO(FSFileBytesIO)` with an additional `alt_name` property.

```python

class FSImageBytesIO(FSFileBytesIO):
    def __init__(self, ir_attachment: IrAttachment = None) -> None:
        super().__init__(ir_attachment)
        self._alt_name = ir_attachment.alt_name if ir_attachment else None

    @property
    def alt_name(self) -> str:
        return self._alt_name

    @alt_name.setter
    def alt_name(self, value: str) -> None:
        self.dirty = True
        self._alt_name = value

```

TO BE REFINED
