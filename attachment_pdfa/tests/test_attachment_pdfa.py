# Copyright 2026 ACSONE SA/NV
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import base64
import os

from odoo_test_helper import FakeModelLoader

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger


class TestIrAttachmentPdfa(TransactionCase):
    def setUp(self):
        super().setUp()
        self.loader = FakeModelLoader(self.env, self.__module__)
        self.loader.backup_registry()
        from .pdfa_test_model import PdfaTestModel

        self.loader.update_registry((PdfaTestModel,))
        self.test_record = self.env["pdfa.test.model"].create(
            {
                "must_convert": True,
            }
        )
        self.dir_path = os.path.dirname(os.path.realpath(__file__))
        self.dummy_pdf_path = os.path.join(self.dir_path, "dummy.pdf")

    def tearDown(self):
        self.loader.restore_registry()
        super().tearDown()

    def _get_dummy_pdf_bytes(self):
        with open(self.dummy_pdf_path, "rb") as pdf_file:
            return pdf_file.read()

    def _set_conversion_method(self, method):
        self.env["ir.config_parameter"].sudo().set_param(
            "attachment_pdfa.method", method
        )

    def _set_storage_mode(self, mode):
        self.env["ir.config_parameter"].sudo().set_param("attachment_pdfa.mode", mode)

    def test_convert_pdf_ghostscript(self):
        """Test real conversion using Ghostscript engine via cron in replace mode."""
        self._set_conversion_method("ghostscript")
        self._set_storage_mode("replace")
        raw_pdf = self._get_dummy_pdf_bytes()
        attachment = self.env["ir.attachment"].create(
            {
                "name": "dummy_gs.pdf",
                "raw": raw_pdf,
                "mimetype": "application/pdf",
                "res_model": "pdfa.test.model",
                "res_id": self.test_record.id,
            }
        )
        self.assertTrue(attachment.is_pdfa_needed)
        self.assertEqual(attachment.raw, raw_pdf)
        self.env["ir.attachment"]._cron_convert_pdfa()
        self.assertFalse(attachment.is_pdfa_needed)
        self.assertNotEqual(attachment.raw, raw_pdf)
        self.assertTrue(
            b"pdfaid" in attachment.raw or b"GTS_PDFA" in attachment.raw,
            "Ghostscript output does not contain expected PDF/A metadata",
        )

    @mute_logger("odoo.tools.pdf")
    def test_convert_pdf_odoo_native(self):
        """Test real conversion using Odoo native engine via cron in replace mode."""
        self._set_conversion_method("odoo")
        self._set_storage_mode("replace")
        raw_pdf = self._get_dummy_pdf_bytes()
        attachment = self.env["ir.attachment"].create(
            {
                "name": "dummy_odoo.pdf",
                "raw": raw_pdf,
                "mimetype": "application/pdf",
                "res_model": "pdfa.test.model",
                "res_id": self.test_record.id,
            }
        )
        self.assertTrue(attachment.is_pdfa_needed)
        self.assertEqual(attachment.raw, raw_pdf)
        self.env["ir.attachment"]._cron_convert_pdfa()
        self.assertFalse(attachment.is_pdfa_needed)
        self.assertNotEqual(attachment.raw, raw_pdf)
        self.assertIn(
            b"<pdfaid:part>3</pdfaid:part>",
            attachment.raw,
            "Odoo native output does not contain PDF/A-3 XMP metadata",
        )

    @mute_logger("odoo.tools.pdf")
    def test_storage_mode_beside(self):
        """Test PDF/A conversion creating a new file beside original."""
        self._set_conversion_method("odoo")
        self._set_storage_mode("beside")
        raw_pdf = self._get_dummy_pdf_bytes()
        attachment = self.env["ir.attachment"].create(
            {
                "name": "original_doc.pdf",
                "raw": raw_pdf,
                "mimetype": "application/pdf",
                "res_model": "pdfa.test.model",
                "res_id": self.test_record.id,
            }
        )
        self.assertTrue(attachment.is_pdfa_needed)
        self.env["ir.attachment"]._cron_convert_pdfa()
        # Original attachment remains unchanged and flag is cleared
        self.assertFalse(attachment.is_pdfa_needed)
        self.assertEqual(attachment.raw, raw_pdf)
        # Verify new PDF/A attachment was created beside original
        new_attachment = self.env["ir.attachment"].search(
            [
                ("res_model", "=", "pdfa.test.model"),
                ("res_id", "=", self.test_record.id),
                ("id", "!=", attachment.id),
            ]
        )
        self.assertEqual(len(new_attachment), 1)
        self.assertEqual(new_attachment.name, "original_doc_PDFA.pdf")
        self.assertNotEqual(new_attachment.raw, raw_pdf)
        self.assertIn(b"<pdfaid:part>3</pdfaid:part>", new_attachment.raw)
        self.assertFalse(new_attachment.is_pdfa_needed)

    @mute_logger("odoo.tools.pdf")
    def test_write_delayed_record_linking(self):
        """Test recomputing is_pdfa_needed and converting when linked late via write."""
        self._set_conversion_method("odoo")
        self._set_storage_mode("replace")
        raw_pdf = self._get_dummy_pdf_bytes()
        attachment = self.env["ir.attachment"].create(
            {
                "name": "unlinked.pdf",
                "raw": raw_pdf,
                "mimetype": "application/pdf",
            }
        )
        self.assertFalse(attachment.is_pdfa_needed)
        # Link model and record via write
        attachment.write(
            {
                "res_model": "pdfa.test.model",
                "res_id": self.test_record.id,
            }
        )
        self.assertTrue(attachment.is_pdfa_needed)
        self.env["ir.attachment"]._cron_convert_pdfa()
        self.assertFalse(attachment.is_pdfa_needed)
        self.assertNotEqual(attachment.raw, raw_pdf)
        self.assertIn(b"<pdfaid:part>3</pdfaid:part>", attachment.raw)

    @mute_logger("odoo.tools.pdf")
    def test_write_update_binary_content(self):
        """Test manually re-flagging is_pdfa_needed on content update."""
        self._set_conversion_method("odoo")
        self._set_storage_mode("replace")
        raw_pdf = self._get_dummy_pdf_bytes()
        attachment = self.env["ir.attachment"].create(
            {
                "name": "initial.pdf",
                "raw": raw_pdf,
                "mimetype": "application/pdf",
                "res_model": "pdfa.test.model",
                "res_id": self.test_record.id,
            }
        )
        self.env["ir.attachment"]._cron_convert_pdfa()
        self.assertFalse(attachment.is_pdfa_needed)
        # Update binary datas and set is_pdfa_needed manually (readonly=False)
        encoded_datas = base64.b64encode(raw_pdf).decode("utf-8")
        attachment.write({"datas": encoded_datas, "is_pdfa_needed": True})
        self.assertTrue(attachment.is_pdfa_needed)
        self.env["ir.attachment"]._cron_convert_pdfa()
        self.assertFalse(attachment.is_pdfa_needed)
        self.assertIn(b"<pdfaid:part>3</pdfaid:part>", attachment.raw)

    @mute_logger("odoo.addons.attachment_pdfa.models.ir_attachment")
    def test_conversion_failure_raises(self):
        """Test that failure raises."""
        self._set_conversion_method("odoo")
        corrupt_pdf_raw = b"INVALID_CORRUPT_PDF_DATA"
        attachment = self.env["ir.attachment"].create(
            {
                "name": "corrupt_document.pdf",
                "raw": corrupt_pdf_raw,
                "mimetype": "application/pdf",
                "res_model": "pdfa.test.model",
                "res_id": self.test_record.id,
            }
        )
        self.assertTrue(attachment.is_pdfa_needed)
        with self.assertRaises(UserError):
            self.env["ir.attachment"]._cron_convert_pdfa()

    def test_conversion_disabled(self):
        """Test that method 'disable' leaves attachments untreated in cron."""
        self._set_conversion_method("disable")
        raw_pdf = self._get_dummy_pdf_bytes()
        attachment = self.env["ir.attachment"].create(
            {
                "name": "dummy_disabled.pdf",
                "raw": raw_pdf,
                "mimetype": "application/pdf",
                "res_model": "pdfa.test.model",
                "res_id": self.test_record.id,
            }
        )
        self.assertTrue(attachment.is_pdfa_needed)
        self.env["ir.attachment"]._cron_convert_pdfa()
        self.assertTrue(attachment.is_pdfa_needed)
        self.assertEqual(attachment.raw, raw_pdf)

    def test_mixin_condition_false(self):
        """Test that is_pdfa_needed computes to False when mixin returns False."""
        self._set_conversion_method("ghostscript")
        self.test_record.must_convert = False
        raw_pdf = self._get_dummy_pdf_bytes()
        attachment = self.env["ir.attachment"].create(
            {
                "name": "dummy_skipped.pdf",
                "raw": raw_pdf,
                "mimetype": "application/pdf",
                "res_model": "pdfa.test.model",
                "res_id": self.test_record.id,
            }
        )
        self.assertFalse(attachment.is_pdfa_needed)

    def test_unsupported_model_ignored(self):
        """Test that models without attachment.pdfa.mixin compute is_pdfa_needed as
        False."""
        self._set_conversion_method("ghostscript")
        raw_pdf = self._get_dummy_pdf_bytes()
        attachment = self.env["ir.attachment"].create(
            {
                "name": "res_partner.pdf",
                "raw": raw_pdf,
                "mimetype": "application/pdf",
                "res_model": "res.partner",
                "res_id": self.env.user.partner_id.id,
            }
        )
        self.assertFalse(attachment.is_pdfa_needed)

    def test_non_pdf_attachment_ignored(self):
        """Test non-PDF attachments compute is_pdfa_needed as False."""
        self._set_conversion_method("ghostscript")
        image_raw = b"FAKE_PNG_DATA"
        attachment = self.env["ir.attachment"].create(
            {
                "name": "test_image.png",
                "raw": image_raw,
                "mimetype": "image/png",
                "res_model": "pdfa.test.model",
                "res_id": self.test_record.id,
            }
        )
        self.assertFalse(attachment.is_pdfa_needed)
