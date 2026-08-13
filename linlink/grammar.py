"""Grammar — the reference forms linlink understands, unified on the uuid.

Two kinds of reference, one identity layer:

1. In-tree markdown link:  [text](path.md) <!-- uuid: <u> -->
   (optionally also [text](dir/) for a directory link)

2. Cross-corpus lin: citation:
       lin:<corpus>:<path>[#frag][@pin] <!-- uuid: <u> -->
   - corpus: the owning repo name (genesis, rung, lares, ...)
   - path: repo-relative path to the target (as committed)
   - #frag / @pin: optional section anchor / version pin
   - the hidden uuid comment is the identity; corpus:path is the locator

The hidden-uuid comment is what makes repair possible: resolve by uuid,
rewrite the path. A plain reference with no uuid comment is 'unanchored'
— valid but not self-healing until robustified.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

# A hidden-uuid comment immediately after a reference. Must be adjacent
# (only whitespace between the reference and the comment).
UUID_COMMENT_RE = re.compile(r"<!--\s*uuid:\s*([0-9a-fA-F-]+)\s*-->")

# In-tree markdown link: [text](path) with optional adjacent uuid comment.
# Captures full link + trailing uuid comment so we can rewrite path.
LINK_RE = re.compile(
    r"\[[^\]]*\]\(([^)\s]+)\)(\s*<!--\s*uuid:\s*([0-9a-fA-F-]+)\s*-->)?"
)

# Cross-corpus lin: citation. Path is greedy up to #, @, whitespace, or a
# closing * (italic footer convention); the character class excludes the
# terminators so greediness cannot overrun. Optional #frag and @pin.
LIN_RE = re.compile(
    r"lin:([a-z0-9-]+):([^#@\s*]+)(?:#([^\s@]+))?(?:@([^\s]+))?"
    r"(\s*<!--\s*uuid:\s*([0-9a-fA-F-]+)\s*-->)?"
)


@dataclass
class Reference:
    """One parsed reference (link or citation) found in a file."""

    kind: str            # "link" | "lin"
    corpus: Optional[str]  # for lin: citations; None for links
    target_path: str     # link: the path; lin: the repo-relative path
    fragment: Optional[str]  # #frag (lin: only)
    pin: Optional[str]       # @pin (lin: only)
    uuid: Optional[str]      # hidden uuid comment, if present
    full: str            # the exact source text matched (for rewrite)
    start: int           # char offset of the match in the file


def _matches(text: str):
    """Yield References for both link and lin forms, in file order.

    Skips fenced code blocks (``` ... ```) — links there are examples,
    not navigation — and external http(s) URLs are never in-tree links.
    """
    # Strip code before scanning: fenced blocks (```/~~~ ... ) and inline
    # code spans (`...`). Links inside code are examples, not navigation —
    # the same rule darnlink enforces (its gotcha #4). A link that survives
    # the strip is a real reference.
    scan_text = re.sub(
        r"(`{3,}|~{3,})[^`]*?\1", "", text, flags=re.DOTALL)  # fenced blocks
    scan_text = re.sub(r"`[^`]*`", "", scan_text)              # inline code

    out: List[Reference] = []
    for m in LINK_RE.finditer(scan_text):
        # skip lin: citations and external URLs matched by the link pattern
        tgt = m.group(1)
        if tgt.startswith("lin:") or tgt.startswith(("http://", "https://", "mailto:", "ftp://")):
            continue
        out.append(Reference(
            kind="link", corpus=None,
            target_path=tgt,
            fragment=None, pin=None,
            uuid=m.group(3),
            full=m.group(0), start=m.start(),
        ))
    for m in LIN_RE.finditer(scan_text):
        out.append(Reference(
            kind="lin", corpus=m.group(1),
            target_path=m.group(2).rstrip("."),
            fragment=m.group(3), pin=m.group(4),
            uuid=m.group(6),
            full=m.group(0), start=m.start(),
        ))
    out.sort(key=lambda r: r.start)
    return out


def find_references(text: str) -> List[Reference]:
    """Return all references (links + lin: citations) in a file's text."""
    return _matches(text)


def anchor_comment(uid: str) -> str:
    """The hidden-uuid comment appended to a reference."""
    return f" <!-- uuid: {uid} -->"
