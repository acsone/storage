# Copyright 2021 ACSONE SA/NV (<http://acsone.eu>)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo import fields, models


class StorageBackend(models.Model):
    _inherit = "storage.backend"

    backend_type = fields.Selection(selection_add=[("ftp", "FTP")])
    ftp_server = fields.Char(string="FTP Host")
    ftp_port = fields.Integer(string="FTP Port", default=21)
    ftp_encryption = fields.Selection(
        string="FTP Encryption method",
        selection=[("none", "None"), ("tls", "FTP over TLS")],
        default="none",
        required=True,
    )
    ftp_login = fields.Char(string="FTP Login", help="Login to connect to ftp server")
    ftp_password = fields.Char(string="FTP Password")

    @property
    def _server_env_fields(self):
        env_fields = super()._server_env_fields
        env_fields.update(
            {
                "ftp_password": {},
                "ftp_login": {},
                "ftp_server": {},
                "ftp_port": {},
                "ftp_encryption": {},
            }
        )
        return env_fields
