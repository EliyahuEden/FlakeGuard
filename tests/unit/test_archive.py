import io
import stat
import zipfile

import pytest

from flakeguard.config import Settings
from flakeguard.github import GitHubError, archive_reports


def test_symlink_rejected():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        member = zipfile.ZipInfo("link.json")
        member.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(member, "../private.json")
    with pytest.raises(GitHubError, match="Unsafe"):
        archive_reports(buffer.getvalue(), Settings())


def test_decompression_bomb_rejected():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("bomb.json", "a" * 100_000)
    with pytest.raises(GitHubError, match="decompression"):
        archive_reports(buffer.getvalue(), Settings())
