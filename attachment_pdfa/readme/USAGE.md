To use this module:

1. Create or generate a PDF attachment on a record whose model implements ``attachment.pdfa.mixin`` (and where ``_attachment_must_be_pdfa()`` evaluates to ``True``).
2. The created PDF is automatically converted to PDF/A-3.
3. If the conversion encounters any non-fatal warnings or fails to convert the file, a log note is automatically posted to the record's **Chatter**, allowing administrators and users to review the conversion output.
