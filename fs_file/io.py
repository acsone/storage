# Copyright 2023 ACSONE SA/NV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
# pylint: disable=method-required-super
import io

from odoo.addons.fs_attachment.models.ir_attachment import IrAttachment


class FSFileBytesIO(io.RawIOBase):
    def __init__(
        self,
        attachment: IrAttachment = None,
        name: str = None,
        value: bytes | io.IOBase = None,
    ) -> None:
        self._is_new: bool = attachment is None
        self._buffer: io.IOBase = None
        self._attachment: IrAttachment = attachment
        self.dirty: bool = False
        if name and attachment:
            raise ValueError("Cannot set name and attachment at the same time")
        if value:
            if isinstance(value, io.IOBase):
                self._buffer = value
                if not hasattr(value, "name") and name:
                    self._buffer.name = name
                elif not name:
                    raise ValueError(
                        "name must be set when value is an io.IOBase "
                        "and is not provided by the io.IOBase"
                    )
            elif isinstance(value, bytes):
                self._buffer = io.BytesIO(value)
                if not name:
                    raise ValueError("name must be set when value is bytes")
                self._buffer.name = name
            else:
                raise ValueError("value must be bytes or io.BytesIO")

    @property
    def write_buffer(self) -> io.BytesIO:
        if self._buffer is None:
            name = self._attachment.name if self._attachment else None
            self._buffer = io.BytesIO()
            self._buffer.name = name
        return self._buffer

    @property
    def read_buffer(self) -> io.BytesIO:
        if self._buffer is None:
            content = b""
            name = None
            if self._attachment:
                content = self._attachment.raw
                name = self._attachment.name
            self._buffer = io.BytesIO(content)
            self._buffer.name = name
        return self._buffer

    def read(self, size: int = -1) -> bytes:
        return self.read_buffer.read(size)

    def write(self, b: bytes) -> int:
        self.dirty = True
        return self.write_buffer.write(b)

    def readinto(self, b: bytearray) -> int:
        return self.read_buffer.readinto(b)

    def getvalue(self) -> bytes:
        buffer = self.read_buffer
        current_pos = buffer.tell()
        buffer.seek(0)
        value = buffer.read()
        buffer.seek(current_pos)
        return value

    @property
    def name(self) -> str | None:
        return (
            self._attachment.name
            if self._attachment
            else self._buffer.name
            if self._buffer
            else None
        )

    @name.setter
    def name(self, value: str) -> None:
        # the name should only be updatable while the file is not yet stored
        # TODO, we could also allow to update the name of the file and rename
        # the file in the external file system
        if self._is_new:
            self.write_buffer.name = value
        else:
            raise ValueError(
                "The name of the file can only be updated while the file is not "
                "yet stored"
            )

    @property
    def mimetype(self) -> str | None:
        return self._attachment.mimetype if self._attachment else None

    @property
    def size(self) -> int:
        return self._attachment.size if self._attachment else len(self._buffer)

    @property
    def url(self) -> str | None:
        return self._attachment.url if self._attachment else None

    @property
    def internal_url(self) -> str | None:
        return self._attachment.internal_url if self._attachment else None

    @property
    def attachment(self) -> IrAttachment | None:
        return self._attachment

    @attachment.setter
    def attachment(self, value: IrAttachment) -> None:
        self._attachment = value
        self._buffer = None

    def __getattr__(self, attr: str):
        return getattr(self.buffer, attr)

    def __setitem__(self, key: int, value: bytes) -> None:
        self.dirty = True
        buffer = self.write_buffer
        buffer.seek(key)
        buffer.write(value)
