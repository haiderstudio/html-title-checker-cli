#!/usr/bin/env python3
"""Tests for html-title-checker-cli. Standard library unittest only.

Run from the repo root: python3 tests/test_html_title_checker.py
"""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import html_title_checker as htc  # noqa: E402

ALLOWED_STDLIB = {
    "argparse",
    "fnmatch",
    "json",
    "os",
    "sys",
    "pathlib",
    "html",
}


def run_cli(argv, stdin_bytes=None):
    """Run main() in-process and capture (exit code, stdout, stderr)."""
    out = io.StringIO()
    err = io.StringIO()
    old_stdin = sys.stdin
    if stdin_bytes is not None:
        sys.stdin = _FakeStdin(stdin_bytes)
    try:
        with redirect_stdout(out), redirect_stderr(err):
            code = htc.main(argv)
    finally:
        sys.stdin = old_stdin
    return code, out.getvalue(), err.getvalue()


class _FakeStdin:
    """Minimal stdin with a .buffer, for --stdin tests."""

    def __init__(self, data):
        self.buffer = io.BytesIO(data)


def page(title, head_extra="", body=""):
    """A minimal page with one title in the head."""
    return (
        "<!DOCTYPE html>\n<html>\n<head>\n"
        f"{head_extra}<title>{title}</title>\n"
        "</head>\n<body>\n"
        f"{body}</body>\n</html>\n"
    )


GOOD_TITLE = "A guide to checking HTML titles the simple way"
EXACT_30 = "A title of thirty characters!!"
EXACT_60 = "A title that is exactly sixty characters long for this test."


class CheckTextTests(unittest.TestCase):
    def test_good_title_passes(self):
        self.assertEqual(check_text_ok(page(GOOD_TITLE)), [])

    def test_exact_boundaries_pass(self):
        self.assertEqual(check_text_ok(page(EXACT_30)), [])
        self.assertEqual(check_text_ok(page(EXACT_60)), [])

    def test_one_shorter_than_minimum_fails(self):
        problems = htc.check_text(page("A title of twenty-nine chars!"), 30, 60)
        self.assertEqual(len(problems), 1)
        self.assertIn("too short (29 characters, minimum 30)", problems[0]["reason"])
        self.assertEqual(problems[0]["line"], 4)

    def test_one_longer_than_maximum_fails(self):
        long_title = EXACT_60 + "x"
        problems = htc.check_text(page(long_title), 30, 60)
        self.assertEqual(len(problems), 1)
        self.assertIn("too long (61 characters, maximum 60)", problems[0]["reason"])

    def test_missing_title_reported_at_line_zero(self):
        html = "<!DOCTYPE html>\n<html>\n<head>\n</head>\n<body>\n</body>\n</html>\n"
        problems = htc.check_text(html, 30, 60)
        self.assertEqual(
            problems, [{"line": 0, "reason": "missing <title> element"}]
        )

    def test_empty_title_fails(self):
        problems = htc.check_text(page(""), 30, 60)
        self.assertEqual(problems, [{"line": 4, "reason": "empty <title>"}])

    def test_whitespace_only_title_is_empty(self):
        problems = htc.check_text(page("   \n  "), 30, 60)
        self.assertEqual(problems, [{"line": 4, "reason": "empty <title>"}])

    def test_two_titles_second_is_duplicate(self):
        html = page(GOOD_TITLE) + ""
        html = html.replace(
            "</head>",
            f"<title>{GOOD_TITLE}</title>\n</head>",
        )
        problems = htc.check_text(html, 30, 60)
        self.assertEqual(
            problems, [{"line": 5, "reason": "duplicate <title> element"}]
        )

    def test_second_title_with_its_own_fault_reports_both(self):
        html = page(GOOD_TITLE).replace(
            "</head>", "<title>Hi</title>\n</head>"
        )
        problems = htc.check_text(html, 30, 60)
        self.assertEqual(len(problems), 2)
        reasons = [p["reason"] for p in problems]
        self.assertIn("duplicate <title> element", reasons)
        self.assertIn("title too short (2 characters, minimum 30)", reasons)

    def test_title_after_head_close_is_outside_head(self):
        html = (
            "<!DOCTYPE html>\n<html>\n<head>\n</head>\n"
            f"<title>{GOOD_TITLE}</title>\n<body>\n</body>\n</html>\n"
        )
        problems = htc.check_text(html, 30, 60)
        self.assertEqual(
            problems, [{"line": 5, "reason": "<title> outside <head>"}]
        )

    def test_title_in_body_is_outside_head(self):
        html = page("", body=f"<title>{GOOD_TITLE}</title>\n").replace(
            "<title></title>\n", ""
        )
        problems = htc.check_text(html, 30, 60)
        self.assertEqual(
            problems, [{"line": 6, "reason": "<title> outside <head>"}]
        )

    def test_title_before_body_with_no_head_tag_passes(self):
        html = (
            "<!DOCTYPE html>\n<html>\n"
            f"<title>{GOOD_TITLE}</title>\n"
            "<body>\n</body>\n</html>\n"
        )
        self.assertEqual(check_text_ok(html), [])

    def test_uppercase_tags_work(self):
        html = (
            "<!DOCTYPE html>\n<HTML>\n<HEAD>\n"
            f"<TITLE>{GOOD_TITLE}</TITLE>\n"
            "</HEAD>\n<BODY>\n</BODY>\n</HTML>\n"
        )
        self.assertEqual(check_text_ok(html), [])

    def test_entities_are_decoded_before_measuring(self):
        # Decoded: "A & B of thirty chars now!" is 26 characters,
        # too short for a minimum of 30. Measured raw, "&amp;"
        # would make it 30 and it would wrongly pass.
        html = page("A &amp; B of thirty chars now!", 30, 60)
        problems = htc.check_text(html, 30, 60)
        self.assertEqual(len(problems), 1)
        self.assertIn("too short (26 characters, minimum 30)", problems[0]["reason"])

    def test_markup_inside_title_is_still_text(self):
        html = page("A <b>bold</b> guide to checking HTML titles here", 30, 60)
        self.assertEqual(check_text_ok(html), [])

    def test_custom_min_max(self):
        self.assertEqual(htc.check_text(page("Hi"), 2, 5), [])
        problems = htc.check_text(page(GOOD_TITLE), 50, 60)
        self.assertEqual(len(problems), 1)
        self.assertIn("too short (46 characters, minimum 50)", problems[0]["reason"])

    def test_title_text_is_stripped_before_measuring(self):
        html = page(f"  {GOOD_TITLE}  \n", 30, 60)
        self.assertEqual(check_text_ok(html), [])


def check_text_ok(html):
    return htc.check_text(html, 30, 60)


class CollectFromFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, str):
            path.write_text(data, encoding="utf-8")
        else:
            path.write_bytes(data)
        return path

    def test_good_file_passes(self):
        path = self.write("good.html", page(GOOD_TITLE))
        problems, skipped = htc.collect_from_file(path, 30, 60)
        self.assertEqual((problems, skipped), ([], False))

    def test_missing_file_reports_read_error(self):
        problems, skipped = htc.collect_from_file(
            self.root / "nope.html", 30, 60
        )
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0]["line"], 0)
        self.assertTrue(problems[0]["reason"].startswith("cannot read file:"))
        self.assertFalse(skipped)

    def test_binary_file_is_skipped(self):
        path = self.write("bin.html", b"<html>\x00<title>x</title>")
        problems, skipped = htc.collect_from_file(path, 30, 60)
        self.assertEqual((problems, skipped), ([], True))

    def test_non_utf8_file_is_reported_not_skipped(self):
        path = self.write("bad.html", b"<title>\xff\xfe bad bytes</title>")
        problems, skipped = htc.collect_from_file(path, 30, 60)
        self.assertEqual(problems, [{"line": 0, "reason": "not valid UTF-8"}])
        self.assertFalse(skipped)


class GatherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data, encoding="utf-8")
        return path

    def test_folder_walk_only_checks_html_files(self):
        self.write("good.html", page(GOOD_TITLE))
        self.write("notes.txt", "no title here at all")
        self.write("sub/bad.html", "<html><head></head><body></body></html>")
        entries, checked, skipped = htc.gather(
            [str(self.root)], [], True, 30, 60
        )
        self.assertEqual(len(checked), 2)
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0][0].endswith("sub/bad.html"))
        self.assertEqual(skipped, [])

    def test_no_recursive_stays_at_top_level(self):
        self.write("good.html", page(GOOD_TITLE))
        self.write("sub/bad.html", "<html><head></head><body></body></html>")
        entries, checked, skipped = htc.gather(
            [str(self.root)], [], False, 30, 60
        )
        self.assertEqual(len(checked), 1)
        self.assertEqual(entries, [])

    def test_git_folder_is_never_walked(self):
        git = self.root / ".git"
        git.mkdir()
        (git / "bad.html").write_text(
            "<html><head></head><body></body></html>", encoding="utf-8"
        )
        self.write("good.html", page(GOOD_TITLE))
        entries, checked, skipped = htc.gather(
            [str(self.root)], [], True, 30, 60
        )
        self.assertEqual(len(checked), 1)
        self.assertEqual(entries, [])

    def test_exclude_skips_matching_files(self):
        self.write("good.html", page(GOOD_TITLE))
        self.write("draft.html", "<html><head></head><body></body></html>")
        entries, checked, skipped = htc.gather(
            [str(self.root)], ["draft*"], True, 30, 60
        )
        self.assertEqual(len(checked), 1)
        self.assertEqual(entries, [])

    def test_direct_file_is_checked_even_without_html_extension(self):
        path = self.write("page.txt", page(GOOD_TITLE))
        entries, checked, skipped = htc.gather([str(path)], [], True, 30, 60)
        self.assertEqual(checked, [str(path)])
        self.assertEqual(entries, [])

    def test_direct_file_is_checked_even_if_excluded(self):
        path = self.write("draft.html", "<html><head></head><body></body></html>")
        entries, checked, skipped = htc.gather(
            [str(path)], ["draft*"], True, 30, 60
        )
        self.assertEqual(len(entries), 1)

    def test_missing_path_raises(self):
        with self.assertRaises(FileNotFoundError):
            htc.gather([str(self.root / "nope")], [], True, 30, 60)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data, encoding="utf-8")
        return path

    def test_exit_zero_on_clean_file(self):
        path = self.write("good.html", page(GOOD_TITLE))
        code, out, err = run_cli([str(path)])
        self.assertEqual(code, 0)
        self.assertEqual(
            out, "OK — 1 file(s) checked, all titles are good.\n"
        )
        self.assertEqual(err, "")

    def test_exit_one_on_bad_file(self):
        path = self.write("bad.html", "<html><head></head><body></body></html>")
        code, out, err = run_cli([str(path)])
        self.assertEqual(code, 1)
        self.assertIn(f"FAIL {path}: missing <title> element", out)
        self.assertIn("Checked 1 file(s), 1 problem(s) in 1 file(s).", out)

    def test_exit_two_on_missing_path(self):
        code, out, err = run_cli([str(self.root / "nope.html")])
        self.assertEqual(code, 2)
        self.assertIn("no such file or folder", err)

    def test_exit_two_with_no_input(self):
        code, out, err = run_cli([])
        self.assertEqual(code, 2)
        self.assertIn("no HTML files to check", err)

    def test_exit_two_on_empty_folder(self):
        code, out, err = run_cli([str(self.root)])
        self.assertEqual(code, 2)
        self.assertIn("no HTML files to check", err)

    def test_exit_two_when_min_beats_max(self):
        path = self.write("good.html", page(GOOD_TITLE))
        code, out, err = run_cli(["--min", "60", "--max", "30", str(path)])
        self.assertEqual(code, 2)
        self.assertIn("--min must not be bigger than --max", err)

    def test_exit_two_on_negative_length(self):
        path = self.write("good.html", page(GOOD_TITLE))
        code, out, err = run_cli(["--min", "-1", str(path)])
        self.assertEqual(code, 2)

    def test_bad_flag_exits_two(self):
        with self.assertRaises(SystemExit) as caught:
            run_cli(["--nope"])
        self.assertEqual(caught.exception.code, 2)

    def test_version(self):
        code, out, err = run_cli(["--version"])
        self.assertEqual(code, 0)
        self.assertEqual(out, "html-title-checker-cli 1.0.0\n")

    def test_stdin_good_and_bad(self):
        code, out, err = run_cli(["--stdin"], page(GOOD_TITLE).encode())
        self.assertEqual(code, 0)
        self.assertIn("all titles are good", out)
        code, out, err = run_cli(["--stdin"], b"<html><head></head></html>")
        self.assertEqual(code, 1)
        self.assertIn("FAIL <stdin>: missing <title> element", out)

    def test_stdin_non_utf8(self):
        code, out, err = run_cli(["--stdin"], b"<title>\xff</title>")
        self.assertEqual(code, 1)
        self.assertIn("FAIL <stdin>: not valid UTF-8", out)

    def test_json_output_parses_and_summary_goes_to_stderr(self):
        path = self.write("bad.html", "<html><head></head><body></body></html>")
        code, out, err = run_cli(["--json", str(path)])
        self.assertEqual(code, 1)
        result = json.loads(out)
        self.assertEqual(result["summary"]["checked"], 1)
        self.assertEqual(result["summary"]["problems"], 1)
        self.assertEqual(result["summary"]["files_with_problems"], 1)
        self.assertEqual(result["files"][0]["file"], str(path))
        self.assertEqual(
            result["files"][0]["problems"],
            [{"line": 0, "reason": "missing <title> element"}],
        )
        self.assertIn("Checked 1 file(s), 1 problem(s) in 1 file(s).", err)
        self.assertNotIn("Checked", out)

    def test_min_max_flags_change_the_range(self):
        path = self.write("short.html", page("Hi"))
        code, out, err = run_cli(["--min", "2", "--max", "5", str(path)])
        self.assertEqual(code, 0)
        self.assertIn("all titles are good", out)

    def test_input_files_are_left_unchanged(self):
        path = self.write("bad.html", "<html><head></head><body></body></html>")
        before = path.read_bytes()
        run_cli([str(path)])
        self.assertEqual(path.read_bytes(), before)

    def test_binary_file_skipped_and_named_on_stderr(self):
        path = self.root / "bin.html"
        path.write_bytes(b"<html>\x00<title>x</title>")
        code, out, err = run_cli([str(path)])
        self.assertEqual(code, 2)
        self.assertIn(f"SKIP {path}: binary file, not checked", err)
        self.assertIn("no HTML files to check", err)


class ExamplesTests(unittest.TestCase):
    def test_sample_output_matches_a_fresh_run(self):
        result = subprocess.run(
            ["sh", "examples/run-example.sh"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        expected = (REPO_ROOT / "examples" / "sample-output.md").read_text(
            encoding="utf-8"
        )
        self.assertEqual(result.stdout, expected)

    def test_readme_quoted_outputs_are_real(self):
        cases = [
            (
                ["examples/good.html"],
                "OK — 1 file(s) checked, all titles are good.",
            ),
            (
                ["examples/missing-title.html"],
                "FAIL examples/missing-title.html: missing <title> element",
            ),
            (
                ["examples/empty-title.html"],
                "FAIL examples/empty-title.html:5: empty <title>",
            ),
            (
                ["examples/two-titles.html"],
                "FAIL examples/two-titles.html:6: duplicate <title> element",
            ),
            (
                ["examples/title-in-body.html"],
                "FAIL examples/title-in-body.html:7: <title> outside <head>",
            ),
            (
                ["examples/short-title.html"],
                "FAIL examples/short-title.html:5: title too short "
                "(2 characters, minimum 30)",
            ),
            (
                ["examples/long-title.html"],
                "FAIL examples/long-title.html:5: title too long "
                "(77 characters, maximum 60)",
            ),
            (
                ["examples/pages/"],
                "FAIL examples/pages/bad.html: missing <title> element",
            ),
        ]
        for argv, expected_line in cases:
            code, out, err = run_cli(argv)
            self.assertIn(expected_line, out, f"argv={argv}")

    def test_example_files_are_checked_by_the_tests(self):
        examples = REPO_ROOT / "examples"
        html_files = sorted(examples.rglob("*.html"))
        self.assertGreaterEqual(len(html_files), 9)


class HygieneTests(unittest.TestCase):
    def _repo_files(self):
        for path in REPO_ROOT.rglob("*"):
            if not path.is_file():
                continue
            parts = path.relative_to(REPO_ROOT).parts
            if ".git" in parts or "__pycache__" in parts:
                continue
            if parts[0] == "tests":
                continue
            yield path

    def test_no_placeholder_text(self):
        banned = ["TODO", "FIXME", "XXX", "coming soon", "lorem"]
        hits = []
        for path in self._repo_files():
            text = path.read_text(errors="ignore")
            for word in banned:
                if word in text:
                    hits.append(f"{path.relative_to(REPO_ROOT)}: {word}")
        self.assertEqual(hits, [])

    def test_no_absolute_paths(self):
        hits = []
        for path in self._repo_files():
            text = path.read_text(errors="ignore")
            for needle in ("/home/", "/Users/", "C:\\"):
                if needle in text:
                    hits.append(str(path.relative_to(REPO_ROOT)))
        self.assertEqual(hits, [])

    def test_stdlib_imports_only(self):
        allowed = ALLOWED_STDLIB | {
            "io",
            "subprocess",
            "tempfile",
            "unittest",
            "html_title_checker",
        }
        hits = []
        for path in list((REPO_ROOT / "src").glob("*.py")) + list(
            (REPO_ROOT / "tests").glob("*.py")
        ):
            text = path.read_text(encoding="utf-8")
            for line in text.splitlines():
                line = line.strip()
                for prefix in ("import ", "from "):
                    if line.startswith(prefix):
                        name = line[len(prefix):].split()[0].split(".")[0]
                        if name not in allowed and name != "contextlib":
                            hits.append(f"{path.name}: {line}")
        self.assertEqual(hits, [])

    def test_env_is_first_line_of_gitignore(self):
        lines = (REPO_ROOT / ".gitignore").read_text(
            encoding="utf-8"
        ).splitlines()
        self.assertTrue(lines)
        self.assertEqual(lines[0], ".env")

    def test_ci_file_runs_the_test_file(self):
        ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("python3 tests/test_html_title_checker.py", ci)
        self.assertIn("actions/checkout@v4", ci)
        self.assertIn("actions/setup-python@v5", ci)
        self.assertIn('python-version: "3.12"', ci)


if __name__ == "__main__":
    unittest.main()
