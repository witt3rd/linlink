"""Check and repair — resolve references by uuid, self-heal on rename.

The engine that makes the hidden uuid the ONE identity: a reference
(link or lin: citation) that carries a uuid comment is checked and
repaired by looking the uuid up in the corpus index, not by trusting the
locator string. If the locator is stale (target moved) but the uuid
resolves, the reference is rewritten to the target's current home.

Verdicts, in the darnlink-compatible exit-code family:
    OK          reference resolves (locator current)
    STALE       locator points at the right uuid but the path is wrong —
                HEALABLE: rewrite the locator from the index
    BROKEN      uuid comment present but the uuid does not resolve —
                not healable (the target is gone or never indexed)
    UNANCHORED  plain reference with no uuid comment — valid but not
                self-healing; candidate for robustify/mint
    UNRESOLVABLE  lin: citation to an unknown corpus (not in the map)
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import frontmatter, grammar, index as index_mod
from .grammar import Reference


@dataclass
class Finding:
    file: str                 # absolute path of the file holding the reference
    reference: Reference
    verdict: str              # OK | STALE | BROKEN | UNANCHORED | UNRESOLVABLE
    detail: str = ""

    @property
    def label(self) -> str:
        if self.reference.kind == "lin":
            base = f"lin:{self.reference.corpus}:{self.reference.target_path}"
            if self.reference.fragment:
                base += f"#{self.reference.fragment}"
            if self.reference.pin:
                base += f"@{self.reference.pin}"
            return base
        return f"[..]({self.reference.target_path})"


def check_text(text: str, file_abs: pathlib.Path, corpora: index_mod.CorporaMap,
               index: index_mod.Index, mint: bool = False) -> List[Finding]:
    """Check all references in one file's text. Returns findings."""
    findings: List[Finding] = []
    for ref in grammar.find_references(text):
        findings.append(_check_one(ref, file_abs, corpora, index, mint))
    return findings


def _check_one(ref: Reference, file_abs: pathlib.Path,
               corpora: index_mod.CorporaMap, index: index_mod.Index,
               mint: bool) -> Finding:
    if ref.kind == "link":
        return _check_link(ref, file_abs)
    return _check_lin(ref, corpora, index, mint)


def _check_link(ref: Reference, file_abs: pathlib.Path) -> Finding:
    # In-tree link: resolve against the file's own directory.
    target = (file_abs.parent / ref.target_path).resolve()
    if target.exists() or target.is_dir():
        # locator is current; check the uuid comment matches, if present
        if ref.uuid:
            actual = frontmatter.read_uuid(target)
            if actual and actual != ref.uuid:
                return Finding(str(file_abs), ref, "BROKEN",
                               f"uuid mismatch: locator resolves to {actual}, comment says {ref.uuid}")
        return Finding(str(file_abs), ref, "OK")
    if ref.uuid:
        # locator stale but has a uuid — the index (or a sibling scan) could
        # heal it; without a per-tree index we flag it as STALE (healable).
        return Finding(str(file_abs), ref, "STALE",
                       f"locator {ref.target_path} missing")
    return Finding(str(file_abs), ref, "BROKEN",
                   f"locator {ref.target_path} missing (no uuid to heal with)")


def _check_lin(ref: Reference, corpora: index_mod.CorporaMap,
               index: index_mod.Index, mint: bool) -> Finding:
    assert ref.corpus is not None  # lin: citations always name a corpus
    root = corpora.get(ref.corpus)
    if root is None:
        return Finding("<file>", ref, "UNRESOLVABLE", f"unknown corpus {ref.corpus}")
    target = root.expanduser() / ref.target_path

    if ref.uuid:
        # The identity is the uuid. Resolve by uuid first.
        entry = index_mod.find_by_uuid(index, ref.uuid)
        if entry is None:
            return Finding("<file>", ref, "BROKEN",
                           f"uuid {ref.uuid} not in index (target gone or unindexed)")
        entry_corpus, entry_rel, _ = entry
        if entry_corpus == ref.corpus and entry_rel == ref.target_path:
            return Finding("<file>", ref, "OK")
        # locator stale, uuid resolves -> HEALABLE (repair rewrites)
        return Finding("<file>", ref, "STALE",
                       f"uuid {ref.uuid} now at {entry_corpus}:{entry_rel}")
    else:
        # No uuid comment — path-only citation. Check the path exists.
        if target.exists():
            return Finding("<file>", ref, "OK")
        return Finding("<file>", ref, "BROKEN",
                       f"target not found at {target} (no uuid to heal with)")


def repair_text(text: str, file_abs: pathlib.Path, corpora: index_mod.CorporaMap,
                index: index_mod.Index) -> tuple[str, List[Finding]]:
    """Rewrite stale locators by uuid. Returns (new_text, heal-findings)."""
    repairs: List[Finding] = []
    new_text = text

    for ref in grammar.find_references(text):
        if ref.kind == "lin" and ref.uuid:
            entry = index_mod.find_by_uuid(index, ref.uuid)
            if entry is None:
                continue
            entry_corpus, entry_rel, _ = entry
            if entry_corpus == ref.corpus and entry_rel == ref.target_path:
                continue  # already correct
            # Build the new citation text preserving fragment/pin.
            new = f"lin:{entry_corpus}:{entry_rel}"
            if ref.fragment:
                new += f"#{ref.fragment}"
            if ref.pin:
                new += f"@{ref.pin}"
            new += grammar.anchor_comment(ref.uuid)
            new_text = new_text.replace(ref.full, new, 1)
            repairs.append(Finding(str(file_abs), ref, "STALE",
                                   f"healed: lin:{entry_corpus}:{entry_rel}"))
        elif ref.kind == "link" and ref.uuid:
            # In-tree: resolve by re-scanning siblings for the uuid.
            healed = _heal_link(ref, file_abs)
            if healed is not None:
                new_text = new_text.replace(ref.full, healed, 1)
                repairs.append(Finding(str(file_abs), ref, "STALE",
                                       f"healed: {healed}"))

    return new_text, repairs


def _heal_link(ref: Reference, file_abs: pathlib.Path) -> Optional[str]:
    """Find an in-tree link's target by uuid among siblings."""
    uid = ref.uuid
    if not uid:
        return None
    for sibling in file_abs.parent.rglob("*.md"):
        if frontmatter.read_uuid(sibling) == uid:
            rel = sibling.relative_to(file_abs.parent).as_posix()
            return f"[..]({rel}){grammar.anchor_comment(uid)}"
    return None
