# Copyright 2026 ACSONE SA/NV
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models


class AttachmentPdfaMixin(models.AbstractModel):
    _name = "attachment.pdfa.mixin"
    _description = "Attachment PDF/A Mixin"

    def _attachment_must_be_pdfa(self):
        return False
