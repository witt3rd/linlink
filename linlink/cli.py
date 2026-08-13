"""linlink CLI — uuid-anchored references that survive renames.

Usage:
    linlink index [PATH...]            build the corpus index
    linlink mint [PATH...]             mint uuids into frontmatter where missing
    linlink check [PATH]               verify references resolve (exit 0/2/3)
    linlink repair [PATH]              rewrite stale locators by uuid (self-heal)
    linlink robustify [PATH]           anchor plain references with hidden uuids

Corpora come from a linlink.toml (or [tool.linlink] in pyproject.toml)
in the scan root, or from --corpus name=path flags.
"""

from __future__ import annotations

import argparse
import configparser
import pathlib
import sys
from typing import Dict, List, Optional

from . import engine, frontmatter, grammar, index as index_mod, __version__
from .index import CorporaMap


def load_corpora(root: pathlib.Path, overrides: Optional[List[str]] = None) -> CorporaMap:
    """Load the corpora map from config; --corpus name=path overrides win."""
    corpora: CorporaMap = {}
    # look for linlink.toml or pyproject.toml [tool.linlink] in the root
    for cand in (root / "linlink.toml", root / "pyproject.toml"):
        if not cand.exists():
            continue
        cp = configparser.ConfigParser()
        try:
            cp.read(cand)
        except configparser.Error:
            continue
        section = cp["linlink"] if "linlink" in cp else cp["tool.linlink"] if "tool.linlink" in cp else None
        if section is not None:
            for key, val in section.items():
                corpora[key] = pathlib.Path(val).expanduser()
    # CLI overrides
    if overrides:
        for spec in overrides:
            if "=" in spec:
                name, _, path = spec.partition("=")
                corpora[name.strip()] = pathlib.Path(path.strip()).expanduser()
    return corpora


def _scan_roots(paths: List[str], corpora: CorporaMap) -> List[pathlib.Path]:
    """Determine which directories to scan from CLI paths or corpora roots."""
    if paths:
        return [pathlib.Path(p).expanduser() for p in paths]
    return [p.expanduser() for p in corpora.values()]


def cmd_index(args, corpora: CorporaMap) -> int:
    idx = index_mod.build_index(corpora)
    print(f"index: {len(idx)} uuids across {len(corpora)} corpora")
    for uid in sorted(idx)[:args.limit]:
        corpus, rel, _ = idx[uid]
        print(f"  {uid} -> {corpus}:{rel}")
    return 0


def cmd_mint(args, corpora: CorporaMap) -> int:
    """Mint uuids into frontmatter where missing. Safe-by-default: dry-run
    unless --write. A dry run never writes anything."""
    roots = _scan_roots(args.paths, corpora)
    minted = 0
    for root in roots:
        for md in sorted(root.rglob("*.md")):
            if any(part.startswith(".") or part in ("node_modules", "target")
                   for part in md.parts):
                continue
            if frontmatter.read_uuid(md) is None:
                if args.write:
                    uid = frontmatter.ensure_uuid(md)
                    print(f"  mint {uid} -> {md}")
                else:
                    print(f"  would mint -> {md}  (use --write)")
                minted += 1
    verb = "minted" if args.write else "would mint (dry-run)"
    print(f"{verb}: {minted}")
    return 0


def cmd_check(args, corpora: CorporaMap) -> int:
    roots = _scan_roots(args.paths, corpora)
    idx = index_mod.build_index(corpora)
    problems: List[engine.Finding] = []
    scanned = 0
    for root in roots:
        for md in sorted(root.rglob("*.md")):
            if any(part.startswith(".") or part in ("node_modules", "target")
                   for part in md.parts):
                continue
            text = md.read_text(encoding="utf-8")
            scanned += 1
            for f in engine.check_text(text, md, corpora, idx):
                if f.verdict != "OK":
                    problems.append(f)
    # report
    if args.json:
        import json
        print(json.dumps([{
            "file": f.file, "verdict": f.verdict,
            "reference": f.label, "detail": f.detail,
        } for f in problems], indent=2))
    else:
        for f in problems:
            print(f"  [{f.verdict}] {f.file}: {f.label} — {f.detail}")
        print(f"checked: {scanned} files | problems: {len(problems)}")
    n_broken = sum(1 for f in problems if f.verdict == "BROKEN")
    n_stale = sum(1 for f in problems if f.verdict == "STALE")
    if n_broken:
        return 2   # broken references (darnlink-compatible integrity)
    if n_stale:
        return 2   # healable but not yet healed
    if any(f.verdict == "UNANCHORED" for f in problems):
        return 3   # strict: unanchored plain references
    return 0


def cmd_repair(args, corpora: CorporaMap) -> int:
    """Rewrite stale locators by uuid. Safe-by-default: dry-run unless
    --write. A dry run reports what would heal, writes nothing."""
    roots = _scan_roots(args.paths, corpora)
    idx = index_mod.build_index(corpora)
    repaired = 0
    for root in roots:
        for md in sorted(root.rglob("*.md")):
            if any(part.startswith(".") or part in ("node_modules", "target")
                   for part in md.parts):
                continue
            text = md.read_text(encoding="utf-8")
            new_text, repairs = engine.repair_text(text, md, corpora, idx)
            if new_text != text:
                if args.write:
                    md.write_text(new_text, encoding="utf-8")
                for r in repairs:
                    tag = "repaired" if args.write else "would repair"
                    print(f"  [{tag}] {md}: {r.label} — {r.detail}")
                    repaired += 1
    verb = "repaired" if args.write else "would repair (dry-run)"
    print(f"{verb}: {repaired}")
    return 0


def cmd_robustify(args, corpora: CorporaMap) -> int:
    """Anchor plain references with hidden uuids (needs targets minted).

    Anchors both in-tree markdown links and lin: citations. For a link,
    the uuid is the target's; for a lin: citation, it is the cited file's.
    Safe-by-default: dry-run unless --write. A dry run never writes — it
    reports what would be anchored and which targets need minting first.
    """
    roots = _scan_roots(args.paths, corpora)
    anchored = 0
    need_mint = 0
    for root in roots:
        for md in sorted(root.rglob("*.md")):
            if any(part.startswith(".") or part in ("node_modules", "target")
                   for part in md.parts):
                continue
            text = md.read_text(encoding="utf-8")
            changed = text
            for ref in grammar.find_references(text):
                if ref.uuid is not None:
                    continue  # already anchored
                uid = _anchor_uuid_for(ref, md, corpora, write=args.write)
                if uid is None:
                    need_mint += 1  # target has no uuid yet (or unresolvable)
                    continue
                new_ref = ref.full + grammar.anchor_comment(uid)
                changed = changed.replace(ref.full, new_ref, 1)
                anchored += 1
            if changed != text:
                if args.write:
                    md.write_text(changed, encoding="utf-8")
                tag = "anchored" if args.write else "would anchor"
                print(f"  [{tag}] {md}")
    verb = "anchored" if args.write else "would anchor (dry-run)"
    print(f"{verb}: {anchored}"
          + (f" | need mint first: {need_mint}" if not args.write else ""))
    return 0


def _anchor_uuid_for(ref, md: pathlib.Path, corpora: CorporaMap, write: bool):
    """Get the uuid to anchor a reference with — target's, minting if absent.

    write=False (dry-run) reads the existing uuid but NEVER mints — minting
    is a write. Returns None if the target has no uuid yet, so the dry-run
    can report 'need mint first' instead of silently writing.
    """
    if ref.kind == "lin":
        if ref.corpus is None:
            return None
        root = corpora.get(ref.corpus)
        if root is None:
            return None
        target = root.expanduser() / ref.target_path
    else:  # in-tree link
        target = (md.parent / ref.target_path).resolve()
    if not target.exists() and not target.is_dir():
        return None
    if write:
        return frontmatter.ensure_uuid(target)
    return frontmatter.read_uuid(target)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="linlink", description=__doc__)
    p.add_argument("--version", action="version", version=f"linlink {__version__}")
    p.add_argument("--corpus", action="append", default=None,
                   help="corpus map override: name=path (repeatable)")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("index", help="build the corpus index")
    pi.add_argument("--limit", type=int, default=20)

    pm = sub.add_parser("mint", help="mint uuids where missing (dry-run unless --write)")

    pc = sub.add_parser("check", help="verify references resolve")
    pc.add_argument("--json", action="store_true")

    pr = sub.add_parser("repair", help="rewrite stale locators by uuid (dry-run unless --write)")

    pb = sub.add_parser("robustify", help="anchor plain citations with uuids (dry-run unless --write)")

    # the three mutating commands are safe-by-default: dry-run unless --write
    for subp in (pm, pr, pb):
        subp.add_argument("--write", action="store_true",
                          help="apply the changes (default is a dry run)")
        subp.add_argument("paths", nargs="*", help="dirs to scan (default: all corpora)")
    pc.add_argument("paths", nargs="*", help="dirs to scan (default: all corpora)")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    cwd = pathlib.Path.cwd()
    corpora = load_corpora(cwd, args.corpus)
    dispatch = {
        "index": cmd_index, "mint": cmd_mint, "check": cmd_check,
        "repair": cmd_repair, "robustify": cmd_robustify,
    }
    return dispatch[args.cmd](args, corpora)


if __name__ == "__main__":
    sys.exit(main())
