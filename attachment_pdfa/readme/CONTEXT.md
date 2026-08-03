In many legal frameworks and corporate archiving policies, business documents must be stored in a compliant, long-term preservation format like **PDF/A-3**.

This module provides a flexible framework to automate PDF to PDF/A-3 conversion upon attachment creation:

* **Opt-in via Mixin**: Rather than blindly converting all system PDFs, models must opt-in by inheriting ``attachment.pdfa.mixin`` and defining conditional rules.
* **Pluggable Engine**: Offers conversion via **Ghostscript** or **Odoo**.
* **Chatter Integration**: Non-blocking conversion pipeline — if the conversion generates warnings or errors during conversion, details are posted directly as internal notes in the record's Chatter.
