# linlink — uuid-anchored references that survive renames

`linlink` is a link and citation tool for markdown knowledge corpora. One
identity layer, one tool: every reference — in-tree link or cross-corpus
citation — is anchored to the **target's hidden uuid**, so a rename or move
anywhere in the knowledge graph never silently breaks a reference.

## The one idea

darnlink proved the trick inside one tree: anchor a link to its target's
**uuid** (kept in the target's YAML frontmatter, echoed as an invisible
`<!-- uuid: … -->` comment by the link). When the target moves, the link
finds it by uuid and rewrites the path. The link survives the refactor
because it points at *identity*, not *path*.

`linlink` makes that one mechanism universal:

- **In-tree links** — the darnlink behavior, absorbed: `[x](note.md)` is
  anchored by a hidden uuid and heals on rename.
- **Cross-corpus citations** — the `lin:` scheme, now uuid-anchored too:

      lin:<corpus>:<path>[#frag][@pin] <!-- uuid: <target-uuid> -->

  The uuid *is* the reference. `<corpus>:<path>` is just the human-readable
  locator — *which* tree currently holds the target. When the target moves
  within its corpus, linlink finds it by uuid and rewrites the path, the
  same way an in-tree link heals.

Two cases, one mechanism: the hidden uuid is the identity of every target.

## Why this matters

- **Renames stop being breaking changes.** Move a note, a spec, a whole
  corpus — references that point at uuids find it again.
- **The cross-corpus boundary disappears.** A `lin:` citation survives a
  rename in another repo, because linlink resolves it by uuid across the
  corpus index — not by a path that went stale.
- **Attribution is in the identity, not the string.** The flat
  `lin:<corpus>:<path>` carries the locator; the uuid carries the "whose."

## Commands

```bash
linlink index          # build the corpus index (uuid -> corpus:path)
linlink mint           # report uuids to mint (dry-run)
linlink mint --write   # mint uuids into frontmatter where missing
linlink check          # verify every reference resolves (exit 0/2/3)
linlink repair         # report stale paths to heal (dry-run)
linlink repair --write # rewrite stale paths by uuid (self-heal)
linlink robustify      # report references to anchor (dry-run)
linlink robustify --write  # anchor plain references with hidden uuids
```

**Safe by default.** `mint`, `repair`, and `robustify` are dry-runs
unless `--write` is given — they report what they would change and
mutate nothing. A dry run never writes, including minting a target uuid
as a side effect of anchoring (it reports "need mint first" instead).
`check` and `index` are read-only always.

Configuration via a `linlink.toml` (or `[tool.linlink]` in pyproject):

```toml
[corpora]
genesis = "~/src/augur/genesis"
rung    = "~/src/witt3rd/rung"
lares   = "~/src/augur/lares"
```

## Status

Fresh build (0.1.0). Replaces darnlink's in-tree role and adds the
uuid-anchored `lin:` citation layer, as one tool.

## License

MIT — this is lineage-owned tooling, clean to use anywhere.
