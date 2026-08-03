# Copyright 2026 ACSONE SA/NV
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import base64
import io
import logging
import subprocess
import tempfile
from pathlib import Path

from markupsafe import Markup

from odoo import api, fields, models
from odoo.tools import html_escape
from odoo.tools.pdf import OdooPdfFileReader, OdooPdfFileWriter

_logger = logging.getLogger(__name__)

TIMEOUT_CONVERSION = 60

DATA_DIR = Path(__file__).parent.parent / "data"
ICC_PROFILE_PS = DATA_DIR / "pdfa_def.ps"
RGB_PROFILE = DATA_DIR / "iccprofiles_default_rgb.icc"

_MISSING_PROFILE_MSG = "Ghostscript ICC Profile or PDF/A definition file not found."

if not ICC_PROFILE_PS.is_file() or not RGB_PROFILE.is_file():
    _logger.error(_MISSING_PROFILE_MSG)
    _PROFILES_AVAILABLE = False
else:
    _PROFILES_AVAILABLE = True


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    @api.model
    def _gs_convert_pdf_to_pdfa(self, raw_content):
        """Convert PDF raw bytes using Ghostscript."""
        if not _PROFILES_AVAILABLE:
            return raw_content, False, _MISSING_PROFILE_MSG
        try:
            with (
                tempfile.NamedTemporaryFile(suffix=".pdf") as temp_in,
                tempfile.NamedTemporaryFile(suffix=".pdf") as temp_out,
            ):
                temp_in.write(raw_content)
                temp_in.flush()
                args = [
                    "gs",
                    f"--permit-file-read={RGB_PROFILE}",
                    "-dPDFACompatibilityPolicy=1",
                    "-sDEVICE=pdfwrite",
                    "-dPDFA=3",
                    "-sColorConversionStrategy=RGB",
                    "-o",
                    temp_out.name,
                    "-c",
                    f"/ICCProfile ({RGB_PROFILE}) def",
                    "-f",
                    str(ICC_PROFILE_PS),
                    str(temp_in.name),
                ]
                result = subprocess.run(
                    args,
                    capture_output=True,
                    text=True,
                    errors="replace",
                    timeout=TIMEOUT_CONVERSION,
                    check=False,
                )
                log_output = (result.stdout or "") + "\n" + (result.stderr or "")
                temp_out.seek(0, 2)
                if result.returncode == 0 and temp_out.tell() > 0:
                    temp_out.seek(0)
                    return temp_out.read(), True, log_output
                return raw_content, False, log_output
        except Exception as e:
            msg = f"Ghostscript conversion exception: {e}"
            _logger.exception(msg)
            return raw_content, False, msg

    @api.model
    def _odoo_convert_pdf_to_pdfa(self, raw_content, title):
        """Convert PDF raw bytes using Odoo native PyPDF writer."""
        try:
            with io.BytesIO(raw_content) as pdf_stream:
                reader = OdooPdfFileReader(pdf_stream, strict=False)
                writer = OdooPdfFileWriter()
                writer.cloneReaderDocumentRoot(reader)
                writer.convert_to_pdfa()

                metadata_template = self.env.ref(
                    "attachment_pdfa.pdfa3_metadata", raise_if_not_found=False
                )
                if metadata_template:
                    content = self.env["ir.qweb"]._render(
                        "attachment_pdfa.pdfa3_metadata",
                        {
                            "title": title or "Document",
                            "date": fields.Date.context_today(self),
                        },
                    )
                    writer.add_file_metadata(content.encode("utf-8"))
                with io.BytesIO() as new_pdf_stream:
                    writer.write(new_pdf_stream)
                    return (
                        new_pdf_stream.getvalue(),
                        True,
                        "Odoo conversion successful.",
                    )
        except Exception as e:
            msg = f"Odoo PDF/A conversion failed: {str(e)}"
            _logger.exception(msg)
            return raw_content, False, msg

    @api.model
    def _check_record_requires_pdfa(self, res_model, res_id):
        """Check if target model and record require PDF/A conversion."""
        if not (res_model and res_id):
            return False
        model_obj = self.env.get(res_model)
        if model_obj is None or not hasattr(model_obj, "_attachment_must_be_pdfa"):
            return False
        record = model_obj.browse(int(res_id))
        return record.exists() and record._attachment_must_be_pdfa()

    @api.model
    def _should_convert_to_pdfa(self, vals):
        """Check if attachment payload qualifies for conversion."""
        mimetype = vals.get("mimetype", "")
        name = vals.get("name", "")
        is_pdf_mimetype = mimetype == "application/pdf"
        is_pdf_extension = name.lower().endswith(".pdf")
        if not (is_pdf_mimetype or is_pdf_extension):
            return False
        res_model = vals.get("res_model") or self.env.context.get("default_res_model")
        res_id = vals.get("res_id") or self.env.context.get("default_res_id")
        return self._check_record_requires_pdfa(res_model, res_id)

    @api.model
    def _process_pdfa_vals(self, vals, method):
        """Mutate creation/update dictionary to replace binary with PDF/A output."""
        raw_data = vals.get("raw")
        if not raw_data and vals.get("datas"):
            raw_data = base64.b64decode(vals["datas"])
        if not raw_data:
            return None
        filename = vals.get("name", "Document.pdf")
        if method == "odoo":
            new_raw, success, log_msg = self._odoo_convert_pdf_to_pdfa(
                raw_data, filename
            )
        elif method == "ghostscript":
            new_raw, success, log_msg = self._gs_convert_pdf_to_pdfa(raw_data)
        else:
            return None
        if success:
            vals["raw"] = new_raw
            if "datas" in vals:
                vals["datas"] = base64.b64encode(new_raw)
            vals["mimetype"] = "application/pdf"
        return {
            "filename": filename,
            "success": success,
            "log_msg": log_msg,
            "res_model": (
                vals.get("res_model") or self.env.context.get("default_res_model")
            ),
            "res_id": (vals.get("res_id") or self.env.context.get("default_res_id")),
        }

    def _post_pdfa_conversion_log(self, log_info):
        """Post conversion errors or warnings to target record chatter."""
        log_msg = log_info["log_msg"]
        success = log_info["success"]
        is_warning_or_error = (
            not success or "warning" in log_msg.lower() or "error" in log_msg.lower()
        )
        if not (
            is_warning_or_error
            and log_msg.strip()
            and log_info["res_model"]
            and log_info["res_id"]
        ):
            return
        target_record = self.env[log_info["res_model"]].browse(int(log_info["res_id"]))
        if not hasattr(target_record, "message_post"):
            return
        escaped_name = html_escape(log_info["filename"])
        status_type = "Error" if not success else "Warning"
        status_title = (
            f"PDF/A-3 Conversion {status_type} for attachment <b>{escaped_name}</b>"
        )
        style = "background-color: #f8f9fa; padding: 8px; border-radius: 4px;"
        formatted_body = (
            f"<p>{status_title}</p>"
            f"<pre style='{style}'>{html_escape(log_msg)}</pre>"
        )
        target_record.message_post(
            body=Markup(formatted_body),
            message_type="notification",
            subtype_xmlid="mail.mt_note",
        )

    @api.model_create_multi
    def create(self, vals_list):
        method = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("attachment_pdfa.method", "ghostscript")
        )
        logs_to_post = []
        if method != "disable":
            for vals in vals_list:
                if self._should_convert_to_pdfa(vals):
                    log_info = self._process_pdfa_vals(vals, method)
                    if log_info:
                        logs_to_post.append(log_info)
        attachments = super().create(vals_list)
        for log_info in logs_to_post:
            self._post_pdfa_conversion_log(log_info)
        return attachments

    def write(self, vals):
        method = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("attachment_pdfa.method", "ghostscript")
        )
        if method == "disable" or not (
            "raw" in vals or "datas" in vals or "res_model" in vals or "res_id" in vals
        ):
            return super().write(vals)
        new_raw_from_datas = (
            base64.b64decode(vals["datas"]) if "datas" in vals else None
        )
        logs_to_post = []
        for attachment in self:
            combined_vals = {
                "name": vals.get("name", attachment.name),
                "mimetype": vals.get("mimetype", attachment.mimetype),
                "res_model": vals.get("res_model", attachment.res_model),
                "res_id": vals.get("res_id", attachment.res_id),
                "raw": vals.get("raw")
                or (
                    new_raw_from_datas
                    if new_raw_from_datas is not None
                    else attachment.raw
                ),
            }
            record_vals = dict(vals)
            if self._should_convert_to_pdfa(combined_vals):
                log_info = self._process_pdfa_vals(combined_vals, method)
                if log_info:
                    if log_info["success"]:
                        record_vals["raw"] = combined_vals["raw"]
                        record_vals["mimetype"] = combined_vals["mimetype"]
                        record_vals.pop("datas", None)
                    logs_to_post.append(log_info)
            super(IrAttachment, attachment).write(record_vals)
        for log_info in logs_to_post:
            self._post_pdfa_conversion_log(log_info)
        return True
