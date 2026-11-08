#!/usr/bin/env python3
"""Check every HTML page has one good title, fail CI on a missing or bad title.

Run: python3 src/html_title_checker.py examples/good.html
     python3 src/html_title_checker.py examples/missing-title.html
     python3 src/html_title_checker.py examples/pages/
     python3 src/html_title_checker.py --min 10 --max 70 examples/good.html

The problem is quiet: a page with no title shows as "Untitled"
in browser tabs, and a page with a one-word title tells a
search engine nothing — so the page ranks badly and nobody
clicks it in the results. Site owners ship pages like that
for years without noticing, because the page itself looks
fine on screen. This tool reads local HTML files, checks each
one has exactly one <title> inside <head>, that the title is
not empty, and that its length sits between 30 and 60
characters by default (change the range with --min and
--max). Every problem is reported with its file and line
number, and the tool exits 1 when any problem is found, so
it can fail a CI run. A clean page exits 0.

A title outside <head> — in the body, or after </head> — is
a problem: browsers may still show it, but it is not where
a title belongs. A second <title> is a problem too: only the
first one is used, the other is dead weight. A file that is
not valid UTF-8 is reported, not skipped, because a page
that cannot be read cannot be checked. A binary file (a null
byte in the first 8 KB) is skipped and named on standard
error, not failed and not counted.

It never rewrites a file. It is report-only and runs fully
offline: it sends nothing anywhere and needs no API key.

Exit codes: 0 when every checked page has one good title,
1 when any title is missing or bad, 2 for a usage or input
problem (a missing path, a bad flag, no files to check).

Python standard library only. HTML is read with
html.parser — never with a regular expression alone.
"""

import argparse
import fnmatch
import json
import os
import sys
from html.parser import HTMLParser
from pathlib import Path

VERSION = "1.0.0"

BINARY_PROBE = 8192
DEFAULT_MIN = 30
DEFAULT_MAX = 60


class _TitleParser(HTMLParser):
    """Collect every <title> element, with its line and position.

    in_head starts True: a title before any <body> tag, with no
    explicit <head>, sits in the page's implicit head. </head>
    or <body> ends the head, so a title after either one is
    outside <head>. Tag names come back lowercased, so <TITLE>
    and <HEAD> work the same as lowercase.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_head = True
        self.body_seen = False
        self.titles = []
        self._current = None

    def handle_starttag(self, tag, attrs):
        if tag == "head":
            self.in_head = True
        elif tag == "body":
            self.in_head = False
            self.body_seen = True
        elif tag == "title":
            line, _col = self.getpos()
            self._current = {
                "line": line,
                "in_head": self.in_head,
                "text": "",
            }
            self.titles.append(self._current)

    def handle_endtag(self, tag):
        if tag == "head":
            self.in_head = False
        elif tag == "title":
            self._current = None

    def handle_data(self, data):
        if self._current is not None:
            self._current["text"] += data


def check_text(text, min_len, max_len):
    """Return the problems in one page's HTML text.

    Each problem is a dict with `line` and `reason`. A missing
    title is reported at line 0, because there is no line to
    point at.
    """
    parser = _TitleParser()
    parser.feed(text)
    parser.close()
    titles = parser.titles
    problems = []
    if not titles:
        return [{"line": 0, "reason": "missing <title> element"}]
    for index, title in enumerate(titles):
        line = title["line"]
        if index > 0:
            problems.append(
                {"line": line, "reason": "duplicate <title> element"}
            )
        if not title["in_head"]:
            problems.append(
                {"line": line, "reason": "<title> outside <head>"}
            )
        clean = title["text"].strip()
        if not clean:
            problems.append({"line": line, "reason": "empty <title>"})
        elif len(clean) < min_len:
            problems.append(
                {
                    "line": line,
                    "reason": (
                        f"title too short "
                        f"({len(clean)} characters, "
                        f"minimum {min_len})"
                    ),
                }
            )
        elif len(clean) > max_len:
            problems.append(
                {
                    "line": line,
                    "reason": (
                        f"title too long "
                        f"({len(clean)} characters, "
                        f"maximum {max_len})"
                    ),
                }
            )
    return problems


def is_binary(data):
    """True when the data looks binary: a null byte early on."""
    return b"\x00" in data[:BINARY_PROBE]


def collect_from_file(path, min_len, max_len):
    """Return (problems, skipped) for one file.

    problems is a list of dicts; skipped is True when the file
    is binary and was not checked.
    """
    try:
        data = path.read_bytes()
    except OSError as exc:
        return (
            [
                {
                    "line": 0,
                    "reason": f"cannot read file: {exc.strerror}",
                }
            ],
            False,
        )
    if is_binary(data):
        return [], True
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return (
            [{"line": 0, "reason": "not valid UTF-8"}],
            False,
        )
    return check_text(text, min_len, max_len), False


def _is_html(name):
    return name.lower().endswith((".html", ".htm"))


def gather(paths, exclude, recursive, min_len, max_len):
    """Walk the given paths and return (entries, checked, skipped).

    entries is a list of (file, problem); checked is a list of
    every HTML file read, clean or not; skipped is a list of
    binary files named but not checked. A file passed on the
    command line is always checked, even if it matches --exclude
    and even if it has no .html extension. Inside a folder, only
    .html and .htm files are checked.
    """
    entries = []
    checked = []
    skipped = []
    for raw in paths:
        path = Path(raw)
        if not path.exists():
            raise FileNotFoundError(raw)
        if path.is_file():
            problems, was_skipped = collect_from_file(
                path, min_len, max_len
            )
            if was_skipped:
                skipped.append(str(path))
            else:
                checked.append(str(path))
            for problem in problems:
                entries.append((str(path), problem))
            continue
        if recursive:
            for dirpath, dirnames, filenames in _walk(path):
                for name in filenames:
                    if not _is_html(name):
                        continue
                    candidate = Path(dirpath) / name
                    if _excluded(candidate, path, exclude):
                        continue
                    problems, was_skipped = collect_from_file(
                        candidate, min_len, max_len
                    )
                    if was_skipped:
                        skipped.append(str(candidate))
                    else:
                        checked.append(str(candidate))
                    for problem in problems:
                        entries.append((str(candidate), problem))
        else:
            for candidate in sorted(path.iterdir()):
                if not candidate.is_file():
                    continue
                if not _is_html(candidate.name):
                    continue
                if _excluded(candidate, path, exclude):
                    continue
                problems, was_skipped = collect_from_file(
                    candidate, min_len, max_len
                )
                if was_skipped:
                    skipped.append(str(candidate))
                else:
                    checked.append(str(candidate))
                for problem in problems:
                    entries.append((str(candidate), problem))
    return entries, checked, skipped


def _walk(root):
    """os.walk that never enters .git and never follows links."""
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d != ".git")
        yield dirpath, dirnames, sorted(filenames)


def _excluded(candidate, root, patterns):
    name = candidate.name
    try:
        rel = str(candidate.relative_to(root))
    except ValueError:
        rel = name
    return any(
        fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(rel, pattern)
        for pattern in patterns
    )


def _format_problem(location, problem):
    if problem["line"]:
        return f"FAIL {location}:{problem['line']}: {problem['reason']}"
    return f"FAIL {location}: {problem['reason']}"


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="html-title-checker-cli",
        description="Check every HTML page has one good title.",
    )
    parser.add_argument("paths", nargs="*", help="files or folders to check")
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="read one page from standard input",
    )
    parser.add_argument(
        "--min",
        type=int,
        default=DEFAULT_MIN,
        metavar="N",
        help="minimum title length in characters (default: 30)",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=DEFAULT_MAX,
        metavar="N",
        help="maximum title length in characters (default: 60)",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="PATTERN",
        help="skip files matching this glob (repeatable)",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="do not walk into subfolders",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the result as JSON (summary goes to stderr)",
    )
    parser.add_argument("--version", action="store_true", help="print the version")
    args = parser.parse_args(argv)

    if args.version:
        print(f"html-title-checker-cli {VERSION}")
        return 0

    if args.min < 0 or args.max < 0 or args.min > args.max:
        print(
            "error: --min must not be bigger than --max, "
            "and both must be 0 or more",
            file=sys.stderr,
        )
        return 2

    entries = []
    checked_files = set()
    skipped_files = []
    try:
        if args.paths:
            found, checked, skipped = gather(
                args.paths,
                args.exclude,
                not args.no_recursive,
                args.min,
                args.max,
            )
            entries.extend(found)
            checked_files.update(checked)
            skipped_files.extend(skipped)
    except FileNotFoundError as exc:
        print(f"error: no such file or folder: {exc}", file=sys.stderr)
        return 2

    if args.stdin:
        data = sys.stdin.buffer.read()
        if is_binary(data):
            skipped_files.append("<stdin>")
        else:
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                entries.append(
                    ("<stdin>", {"line": 0, "reason": "not valid UTF-8"})
                )
                checked_files.add("<stdin>")
                text = None
            if text is not None:
                for problem in check_text(text, args.min, args.max):
                    entries.append(("<stdin>", problem))
                checked_files.add("<stdin>")

    for name in skipped_files:
        print(f"SKIP {name}: binary file, not checked", file=sys.stderr)

    if not checked_files:
        print("error: no HTML files to check", file=sys.stderr)
        return 2

    problems = entries
    bad_files = len({f for f, _p in problems})
    total = len(problems)

    if args.json:
        files = []
        for name in sorted(checked_files):
            file_problems = [p for f, p in problems if f == name]
            files.append({"file": name, "problems": file_problems})
        result = {
            "files": files,
            "summary": {
                "checked": len(checked_files),
                "files_with_problems": bad_files,
                "problems": total,
                "skipped": len(skipped_files),
                "min_length": args.min,
                "max_length": args.max,
            },
        }
        print(json.dumps(result, indent=2))
        if problems:
            print(
                f"Checked {len(checked_files)} file(s), {total} "
                f"problem(s) in {bad_files} file(s).",
                file=sys.stderr,
            )
        else:
            print(
                f"OK — {len(checked_files)} file(s) checked, "
                f"all titles are good.",
                file=sys.stderr,
            )
        return 1 if problems else 0

    for location, problem in problems:
        print(_format_problem(location, problem))
    if problems:
        print(
            f"Checked {len(checked_files)} file(s), {total} "
            f"problem(s) in {bad_files} file(s)."
        )
        return 1
    print(
        f"OK — {len(checked_files)} file(s) checked, "
        f"all titles are good."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
