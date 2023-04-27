The new field **FSFile** has been developed to allows you to store files
in an external filesystem storage. Its design is based on the following
principles:

* The content of the file must be read from the filesystem only when
  needed.
* It must be possible to manipulate the file content as a stream by default.
* Unlike Odoo's Binary field, the content is the raw file content by default
  (no base64 encoding).
* To allows to exchange the file content with other systems, writing the
  content as base64 is possible. The read operation will return a json
  structure with the filename, the mimetype and a url to download the file.

This design allows to minimize the memory consumption of the server when
manipulating large files and exchanging them with other systems through
the default jsonrpc interface.

Concretely, this design allows you to write code like this:

.. code-block:: python

  from IO import BytesIO
  from odoo import models, fields
  from odoo.addons.fs_file.fields import FSFile

  class MyModel(models.Model):
      _name = 'my.model'

      name = fields.Char()
      filename = fields.Char()
      file = FSFile(field_name='filename', storage_code="my_storage")

  # Create a new record with a raw content
  my_model = MyModel.create({
      'name': 'My File',
      'filename': 'my_file.txt',
      'file': BytesIO(b"content"),
  })

  assert(my_model.file.read() == b"content")
  assert(my_model.file.name == "my_file.txt")

  # Create a new record with a base64 encoded content
  my_model = MyModel.create({
      'name': 'My File',
      'filename': 'my_file.txt',
      'file': b"content".encode('base64'),
  })
  assert(my_model.file.read() == b"content")
  assert(my_model.file.name == "my_file.txt")

  # Create a new record with a file content
  with open('my_file.txt', 'rb') as f:
      f.write(b"content")

  my_model = MyModel.create({
      'name': 'My File',
      'file': open('my_file.txt', 'rb'),
  })
  assert(my_model.file.read() == b"content")
  assert(my_model.file.name == "my_file.txt")

  with open(my_model.file, 'wb') as f:
      f.write(b"new content")

  # the call to read() will return a json structure with the filename,
  # the mimetype and a url to download the file.
  info = my_model.file.read()
  assert(info["file"] == {
      "filename": "my_file.txt",
      "mimetype": "text/plain",
      "url": "/web/content/1234/my_file.txt",
  })
