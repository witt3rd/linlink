"""linlink — uuid-anchored references that survive renames.

Identity layer: every named target carries a uuid in its YAML frontmatter,
and every reference to it — in-tree markdown link or cross-corpus lin:
citation — carries that same uuid as an invisible comment next to the
reference. Repairing is then a uuid lookup across the corpus index, not a
path path. Details in README.md.

Modules:
    frontmatter — read/write the uuid in a markdown file's frontmatter
    grammar     — the reference forms linlink understands
    index       — the corpus index (uuid -> corpus:path location)
"""

__version__ = "0.2.0"