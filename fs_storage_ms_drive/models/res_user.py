# Copyright 2024 ACSONE SA/NV
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).


from odoo import models


class ResUsers(models.Model):
    _inherit = "res.users"

    def _get_oauth2_client_params(self):
        self.ensure_one()
        get_param = self.env["ir.config_parameter"].sudo().get_param
        return {
            "client_id": get_param("microsoft_sharepoint_client_id"),
            "client_secret": get_param("microsoft_sharepoint_client_secret"),
            "scope": get_param("sharepoint_microsoft_client_scope"),
            "token_endpoint": get_param("microsoft_account.token_endpoint"),
        }

    def _get_oauth2_params(self):
        self.ensure_one()
        access_token = self.microsoft_sharepoint_token
        rtoken = self.microsoft_sharepoint_rtoken
        expires_at = int(self.microsoft_sharepoint_token_validity.timestamp())
        token = {
            "access_token": access_token,
            "refresh_token": rtoken,
            "expires_at": expires_at,
        }
        params = self._get_oauth2_client_params()
        params.update(token=token)
        return params
