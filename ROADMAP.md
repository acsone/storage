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
provide 2 new specialized field types: `FSFile()` and `FSFileName`. These new field
types will allow you to add fields on your models to store a file content into an
external file system. Compared to the `Binary` field type, the `FSFile()` field will
require 2 additional parameters:

- `storage_code`: the code of the file system where the file content will be stored.
- `field_filename`: the name of the `FSFileName` field.

The `FSFileName` field will be used to store the name of the file. It will be act as a
related field on the `name` field of the `ir.attachment` record behind the `FSFile()`
field.

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

The implementation of the `FSFile` field will be base on the `Binary` field but will
always put into the context the `storage_code` and `field_filename` to allows. Theses 2
parameters will be used by the `fs_attachment` addon to select the file system where the
file content will be stored and to set the name of the file.

### fs_image

The `storage.image` addon will be replaced by the new `fs_image` addon. It will at least
provides a new widget to allow the display of the image content from the url provided by
the `FSFile` field. If it were not for the automatic thumbnail creation mechanism, this
module could be summarised as the creation of 2 new fields type: `FSImage()` and
`FSImageAltName`. The `alt_name` would be a related field to a new the `alt_name` field
of the `ir.attachment` record behind. The `FSImage` field would be an extension of the
`FSFile` field with 1 optional parameter: `alt_name_field`.

TO BE REFINED
