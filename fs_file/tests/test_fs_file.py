# Copyright 2023 ACSONE SA/NV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import base64
import io
import os
import tempfile

from odoo_test_helper import FakeModelLoader

from odoo.tests.common import TransactionCase


class TestFsFile(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.loader = FakeModelLoader(cls.env, cls.__module__)
        cls.loader.backup_registry()
        from .models import TestModel

        cls.loader.update_registry((TestModel,))
        cls.temp_dir = cls.env["fs.storage"].create(
            {
                "name": "Temp FS Storage",
                "protocol": "memory",
                "code": "mem_dir",
                "directory_path": "tmp",
            }
        )
        cls.filename = tempfile.mktemp()
        with open(cls.filename, "wb") as f:
            f.write(b"file content")

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.filename):
            os.remove(cls.filename)
        cls.loader.restore_registry()
        return super().tearDownClass()

    def test_read(self):
        model = self.env["test.model"].create(
            {"fs_file": b"test", "fs_filename": "test.txt"}
        )
        info = model.read(["fs_file"])[0]
        self.assertDictEqual(
            info["fs_file"],
            {
                "filename": "test.txt",
                "mimetype": "text/plain",
                "url": model.fs_file.internal_url,
            },
        )

    def test_create_with_dict(self):
        model = self.env["test.model"].create(
            {
                "fs_file": {
                    "filename": "test.txt",
                    "content": base64.b64encode(b"content"),
                }
            }
        )
        self.assertTrue(isinstance(model.fs_file, io.IOBase))
        self.assertEqual(model.fs_file.getvalue(), b"content")
        self.assertEqual(model.fs_file.name, "test.txt")

    def test_write_with_dict(self):
        model = self.env["test.model"].create({})
        model.write(
            {
                "fs_file": {
                    "filename": "test.txt",
                    "content": base64.b64encode(b"content"),
                }
            }
        )
        self.assertTrue(isinstance(model.fs_file, io.IOBase))
        self.assertEqual(model.fs_file.getvalue(), b"content")
        self.assertEqual(model.fs_file.name, "test.txt")

    def test_create_in_b64(self):
        model = self.env["test.model"].create(
            {"fs_file": base64.b64encode(b"content"), "fs_filename": "test.txt"}
        )
        self.assertTrue(isinstance(model.fs_file, io.IOBase))
        self.assertEqual(model.fs_file.getvalue(), b"content")

    def test_write_in_b64(self):
        model = self.env["test.model"].create(
            {"fs_file": b"test", "fs_filename": "test.txt"}
        )
        model.write({"fs_file": base64.b64encode(b"content")})
        self.assertTrue(isinstance(model.fs_file, io.IOBase))
        self.assertEqual(model.fs_file.getvalue(), b"content")

    def test_create_with_io(self):
        model = self.env["test.model"].create(
            {"fs_file": io.BytesIO(b"content"), "fs_filename": "test.txt"}
        )
        self.assertTrue(isinstance(model.fs_file, io.IOBase))
        self.assertEqual(model.fs_file.getvalue(), b"content")

    def test_write_with_io(self):
        model = self.env["test.model"].create(
            {"fs_file": io.BytesIO(b"content"), "fs_filename": "test.txt"}
        )
        model.write({"fs_file": io.BytesIO(b"test3")})
        self.assertTrue(isinstance(model.fs_file, io.IOBase))
        self.assertEqual(model.fs_file.getvalue(), b"test3")

    def test_create_with_file_like(self):
        with open(self.filename, "rb") as f:
            model = self.env["test.model"].create({"fs_file": f})
        self.assertTrue(isinstance(model.fs_file, io.IOBase))
        self.assertEqual(model.fs_file.getvalue(), b"file content")
        self.assertEqual(model.fs_file.name, self.filename)
