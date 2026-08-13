"""Frontmatter uuid — read, write, and mint the identity layer."""

from __future__ import annotations

import pathlib
import re
import uuid
from typing import Optional

UUID_RE = re.compile(r"^-{3}\s*\n(.*?)\n-{3}\s*\n", re.DOTALL)
UUID_LINE_RE = re.compile(r"^uuid:\s*([0-9a-fA-F-]+)\s*$", re.MULTILINE)


def read_uuid(path: pathlib.Path) -> Optional[str]:
    """Return the uuid in the file's frontmatter, or None if absent.

    Works on any markdown file regardless of whether it has a frontmatter.
    """
    text = path.read_text(encoding="utf-8")
    m = UUID_LINE_RE.search(text)
    return m.group(1).strip() if m else None


def mint_uuid() -> str:
    """Generate a fresh uuid for a target. str(uuid.uuid4())."""
    return str(uuid.uuid4())


def write_uuid(path: pathlib.Path, uid: str) -> None:
    """Create or update the file's frontmatter uuid. Never destroys body."""
    text = path.read_text(encoding="utf-8")

    m = UUID_RE.match(text)
    if m:  # existing frontmatter — insert or replace the uuid line
        fm = m.group(1)
        if UUID_LINE_RE.search(fm):
            # uuid line already present — update it in place
            fm2 = re.sub(r"(?m)^uuid:.*$", f"uuid: {uid}", fm, count=1)
            text = text[: m.start(1)] + fm2 + text[m.end(1):]
        else:
            # no uuid line yet — add it right after the opening ---
            new_fm = f"uuid: {uid}\n" + fm
            text = text[: m.start(1)] + new_fm + text[m.end(1):]
    else:  # no frontmatter — create one at the top
        text = f"---\nuuid: {uid}\n---\n\n{text}"

    path.write_text(text, encoding="utf-8")


def ensure_uuid(path: pathlib.Path) -> str:
    """Return the file's uuid, minting one into the frontmatter if absent."""
    existing = read_uuid(path)
    if existing:
        return existing
    uid = mint_uuid()
    write_uuid(path, uid)
    return uid