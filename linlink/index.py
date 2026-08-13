"""Index — the uuid -> corpus:path location map across all corpora.

The corpus index is the heart of cross-corpus repair. It scans every
configured corpus for markdown files with a frontmatter uuid, and records
where each uuid currently lives: which corpus, what repo-relative path.
Repair is then a uuid lookup: find the target's new home and rewrite the
reference's locator.

Configuration is a corpora map (corpus name -> filesystem root), supplied
by the CLI from linlink.toml / [tool.linlink] in pyproject, or inline.
"""

from __future__ import annotations

import pathlib
from typing import Dict, List, Optional, Tuple

from . import frontmatter

# corpus -> path
CorporaMap = Dict[str, pathlib.Path]

# uuid -> (corpus, repo-relative-path, absolute-path)
IndexEntry = Tuple[str, str, pathlib.Path]
Index = Dict[str, IndexEntry]


def scan_corpus(name: str, root: pathlib.Path) -> List[IndexEntry]:
    """Scan one corpus root for markdown files with a frontmatter uuid.

    Returns (corpus, repo-relative-path, absolute-path) for each file that
    has a uuid. Files without uuids are skipped (they are mint targets,
    not index entries).
    """
    entries: List[IndexEntry] = []
    root = root.expanduser()
    if not root.is_dir():
        return entries
    for md in sorted(root.rglob("*.md")):
        if any(part.startswith(".") or part == "node_modules" or part == "target"
               for part in md.parts):
            continue  # skip hidden/vendored/build dirs
        uid = frontmatter.read_uuid(md)
        if uid is None:
            continue
        rel = md.relative_to(root).as_posix()
        entries.append((name, rel, md))
    return entries


def build_index(corpora: CorporaMap) -> Index:
    """Build the uuid -> (corpus, rel-path, abs-path) index."""
    index: Index = {}
    for name, root in corpora.items():
        for entry in scan_corpus(name, root):
            uid = frontmatter.read_uuid(entry[2])  # re-read (authoritative)
            if uid:
                index[uid] = entry
    return index


def find_by_uuid(index: Index, uid: str) -> Optional[IndexEntry]:
    """Resolve a uuid to its current location in the index."""
    return index.get(uid)


def resolve_target(corpora: CorporaMap, corpus: str, rel_path: str) -> Optional[pathlib.Path]:
    """Resolve a (corpus, repo-relative-path) locator to an absolute path."""
    root = corpora.get(corpus)
    if root is None:
        return None
    return root.expanduser() / rel_path
