# Copyright 2023 ACSONE SA/NV (https://www.acsone.eu).
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import ntpath
import posixpath
from pathlib import PurePosixPath, PureWindowsPath

from fsspec.implementations.dirfs import DirFileSystem
from fsspec.registry import register_implementation


class RootedDirFileSystem(DirFileSystem):
    """A directory-based filesystem that uses path as a root.

    The main purpose of this filesystem is to ensure that paths are always
    a sub path of the initial path. IOW, it is not possible to go outside
    the initial path. That's the only difference with the DirFileSystem provided
    by fsspec.

    This one should be provided by fsspec itself. We should propose a PR.
    """

    def _posix_normpath_shadow_traversal(self, path: str) -> str:
        """Normalize posix path that contains '..\\' which
        are not taken into account by the standard lib posixpath.normpath
        but are resolved by os and therefore could lead to shadow path
        traversal"""

        current = path

        # current root/storate/test/..\\toto/file.txt
        while "..\\" in current:
            idx = current.find("..\\")

            # bedore '..\\' root/storate/test/
            before = current[:idx]
            # after '..\\' 'toto/file.txt'
            after = current[idx + 3 :]

            # We normalize the before part by adding  '..' to neutralize its effect
            if before:
                resolved_before = posixpath.normpath(posixpath.join(before, ".."))
                if resolved_before == ".":
                    resolved_before = ""
            else:
                resolved_before = ".."

            # We rebuild the expectd path
            current = posixpath.join(resolved_before, "\\" + after)

            # removes superfuleus slashes
            current = posixpath.normpath(current)

        return current

    def _join(self, path):
        joined = super()._join(path)
        if not isinstance(joined, str):
            return joined
        # Uses the rigth path abstraction according to the
        # path separator
        if self.sep == "/":
            PathClass = PurePosixPath
            normpath = posixpath.normpath
        elif self.sep == "\\":
            PathClass = PureWindowsPath
            normpath = ntpath.normpath
        else:
            raise ValueError(f"Unknown path separator: {self.sep!r}")

        root = PathClass(self.path)
        joined_path = PathClass(joined)

        rnorm = normpath(str(root))
        jnorm = normpath(str(joined_path))

        if self.sep == "/":
            jnorm = self._posix_normpath_shadow_traversal(jnorm)

        prefix = rnorm if rnorm.endswith(self.sep) else rnorm + self.sep
        if not (jnorm == rnorm or jnorm.startswith(prefix)):
            raise PermissionError(
                f"Path {path!r} resolves to {jnorm!r} which is outside "
                f"the root path {rnorm!r}"
            )

        return joined


register_implementation("rooted_dir", RootedDirFileSystem)
