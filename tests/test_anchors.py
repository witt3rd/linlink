"""linlink in-tree anchor resolution — regression test (run: python3 tests/test_anchors.py)."""
import pathlib, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from linlink.engine import check_text


def check(link, target_text, expected_ok=True, frag=None):
    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        (root / "target.md").write_text(target_text, encoding="utf-8")
        (root / "src.md").write_text(link, encoding="utf-8")
        fs = check_text(link, root / "src.md", {}, {})
        v = fs[0].verdict
        assert (v == "OK") == expected_ok, f"expected OK={expected_ok}, got {v}: {fs[0].detail}"
        print(f"  ok: {link!r} -> {v}" + (f" ({fs[0].detail})" if fs[0].detail else ""))

print("matching anchor:")
check("[ownership principle](target.md#05-the-ownership-principle)",
      "## 0.5 THE OWNERSHIP PRINCIPLE\n\nbody\n")
print("mismatched anchor (should be BROKEN):")
check("[x](target.md#nope)",
      "## 0.5 THE OWNERSHIP PRINCIPLE\n\nbody\n", expected_ok=False)
print("no anchor, plain file link:")
check("[x](target.md)", "## anything\n", expected_ok=True)
print("anchor on missing file (should be BROKEN):")
check("[x](absent.md#frag)", "## anything\n", expected_ok=False)
print("\nALL PASS")
