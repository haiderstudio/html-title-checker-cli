# html-title-checker-cli

Check every HTML page has one good title, fail CI on a missing or bad title.

[![CI](https://github.com/haiderstudio/html-title-checker-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/haiderstudio/html-title-checker-cli/actions/workflows/ci.yml) [![Licence: MIT](https://img.shields.io/badge/Licence-MIT-yellow.svg)](LICENSE)

## What it does

`html_title_checker` reads local HTML files and checks each
one has exactly one `<title>` inside `<head>`:

- A page with no title shows as "Untitled" in browser tabs,
  and a page with a one-word title tells a search engine
  nothing — so the page ranks badly and nobody clicks it in
  the results. Site owners ship pages like that for years
  without noticing, because the page itself looks fine on
  screen. This tool reports every page whose title is
  missing, empty, duplicated, outside `<head>`, too short,
  or too long, with its file and line number, and exits 1
  when any problem is found — so it can fail a CI run. A
  clean page exits 0.
- A title must sit between 30 and 60 characters by default
  — long enough to say something, short enough to fit a
  search result. `--min` and `--max` change the range.
- A title outside `<head>` — in the body, or after
  `</head>` — is a problem: browsers may still show it, but
  it is not where a title belongs. A second `<title>` is a
  problem too: only the first one is used, the other is dead
  weight. A title before any `<body>` tag, with no explicit
  `<head>`, passes — that is the page's implicit head.
- Uppercase tags work the same as lowercase (`<TITLE>` and
  `<HEAD>` are read the same way), and entities in a title
  are decoded before the length is measured, so `&amp;`
  counts as one character, not five.
- A file that is not valid UTF-8 is reported, not skipped,
  because a page that cannot be read cannot be checked. A
  binary file (a null byte in the first 8 KB) is skipped and
  named on standard error, not failed and not counted.
- Pages come from the command line (one or more), or from a
  folder walk: every `.html` and `.htm` file under a folder,
  recursively by default (`--no-recursive` stops at the top
  level). `.git` folders are never walked, and directory
  links are never followed, so a link cycle cannot loop the
  check.
- `--exclude PATTERN` skips files by glob, for example
  `--exclude 'draft-*'`. It can be repeated. A file passed
  directly on the command line is always checked, even if it
  matches an exclude pattern and even if it has no `.html`
  extension.
- `--stdin` reads one page from standard input.
- `--json` prints the result as machine-readable JSON (the
  summary goes to standard error, so standard output stays
  clean JSON).
- It is report-only and runs fully offline: it never rewrites
  a file, sends nothing anywhere, and needs no API key.

## What it does NOT do

- It does not rewrite a file or fix a title. A bad title is
  reported; fixing it is your job.
- It does not fetch a live site. Every input is a local file
  or standard input — a page that only exists on the web is
  not this tool's job.
- It does not check meta descriptions, headings, or alt text
  — those are other tools' jobs. This tool's one job is the
  title.
- It does not check line endings, whitespace, or encoding
  beyond "is this valid UTF-8" — that is Day 42's
  `whitespace-checker-cli`, Day 49's
  `line-ending-checker-cli`, and Day 56's
  `file-encoding-checker-cli` territory.

## Who it is for

Anyone who owns a site and wants every page to show up
properly in search results and browser tabs: a blogger
checking a batch of posts, a developer adding a CI step
that fails the build when a page ships without a title, or
anyone tidying a folder of old HTML pages. A missing title
is invisible on the page itself — this catches it before
the page goes live.

## How this differs from similar tools

The exact name `html-title-checker-cli` matches 0
repositories on GitHub (checked Nov 8, 2026), and `title
tag checker` and `html title validator` match 0 too. The
wider field is small: `html title checker` matches 19
repositories. The top one, UNC-Libraries/Access-Checker,
34 stars, is a JRuby script about ebook titles — noise. The
only repo with a matching name, Gai-Git/html_title_checker,
0 stars, has no description, no tests, and no CI claim.
The rest are bookmark tools, live-site health checkers,
and broad accessibility or SEO checkers that look at
titles as one item among many, usually by fetching live
URLs. None of them is a tested CLI that walks a folder of
local HTML files, reports every missing or bad title with a
file and line, and exits 1 for CI. This tool does that one
job: a Python standard-library-only CLI that reads local
files, parses them with `html.parser`, and exits 1 on a
bad title — no install beyond Python, no website, no
network.

## Install

Python standard library only — no packages to download. You need
Python 3.8 or newer. Clone the repo and run it in place:

```
git clone https://github.com/haiderstudio/html-title-checker-cli.git
cd html-title-checker-cli
python3 src/html_title_checker.py examples/good.html
```

```
OK — 1 file(s) checked, all titles are good.
```

## Usage

Check one good page:

```
python3 src/html_title_checker.py examples/good.html
```

```
OK — 1 file(s) checked, all titles are good.
```

Check a page with no title:

```
python3 src/html_title_checker.py examples/missing-title.html
```

```
FAIL examples/missing-title.html: missing <title> element
Checked 1 file(s), 1 problem(s) in 1 file(s).
```

Check a page with an empty title:

```
python3 src/html_title_checker.py examples/empty-title.html
```

```
FAIL examples/empty-title.html:5: empty <title>
Checked 1 file(s), 1 problem(s) in 1 file(s).
```

Check a page with two titles:

```
python3 src/html_title_checker.py examples/two-titles.html
```

```
FAIL examples/two-titles.html:6: duplicate <title> element
Checked 1 file(s), 1 problem(s) in 1 file(s).
```

Check a page whose title sits in the body:

```
python3 src/html_title_checker.py examples/title-in-body.html
```

```
FAIL examples/title-in-body.html:7: <title> outside <head>
Checked 1 file(s), 1 problem(s) in 1 file(s).
```

Check a page with a two-letter title:

```
python3 src/html_title_checker.py examples/short-title.html
```

```
FAIL examples/short-title.html:5: title too short (2 characters, minimum 30)
Checked 1 file(s), 1 problem(s) in 1 file(s).
```

Check a page with a title that runs on too long:

```
python3 src/html_title_checker.py examples/long-title.html
```

```
FAIL examples/long-title.html:5: title too long (77 characters, maximum 60)
Checked 1 file(s), 1 problem(s) in 1 file(s).
```

Check a whole folder:

```
python3 src/html_title_checker.py examples/pages/
```

```
FAIL examples/pages/bad.html: missing <title> element
Checked 2 file(s), 1 problem(s) in 1 file(s).
```

Change the length range:

```
python3 src/html_title_checker.py --min 2 --max 5 examples/short-title.html
```

```
OK — 1 file(s) checked, all titles are good.
```

Check one page from standard input:

```
printf '<!DOCTYPE html>\n<html>\n<head>\n<title>A guide to checking HTML titles the simple way</title>\n</head>\n<body>\n</body>\n</html>\n' | python3 src/html_title_checker.py --stdin
```

```
OK — 1 file(s) checked, all titles are good.
```

Machine-readable output with `--json` (the summary goes to
standard error, so standard output stays clean JSON):

```
python3 src/html_title_checker.py examples/short-title.html --json
```

```
{
  "files": [
    {
      "file": "examples/short-title.html",
      "problems": [
        {
          "line": 5,
          "reason": "title too short (2 characters, minimum 30)"
        }
      ]
    }
  ],
  "summary": {
    "checked": 1,
    "files_with_problems": 1,
    "problems": 1,
    "skipped": 0,
    "min_length": 30,
    "max_length": 60
  }
}
```

Exit codes: 0 when every checked page has one good title,
1 when any title is missing or bad, 2 for a usage problem (no
HTML files given, a bad flag, a missing file or folder, or
`--min` bigger than `--max`).

## Examples

### 1. A page with no title at all

`examples/missing-title.html` has a head with no title
element, so the report points at the file itself — there is
no line to point at:

```
python3 src/html_title_checker.py examples/missing-title.html
```

```
FAIL examples/missing-title.html: missing <title> element
Checked 1 file(s), 1 problem(s) in 1 file(s).
```

### 2. A page with two titles — and one of them too short

A second title is a problem on its own, and if it is also
too short, both reasons are reported:

```
python3 -c "
import sys; sys.path.insert(0, 'src')
import html_title_checker as htc
html = '<html><head><title>A guide to checking HTML titles the simple way</title><title>Hi</title></head><body></body></html>'
print(htc.check_text(html, 30, 60))
"
```

```
[{'line': 1, 'reason': 'duplicate <title> element'}, {'line': 1, 'reason': 'title too short (2 characters, minimum 30)'}]
```

### 3. The bundled examples, all at once

```
sh examples/run-example.sh
```

The script checks the good page (pass), then the missing
title (fail, on purpose), then the short title (fail, on
purpose), then the long title (fail, on purpose), then the
whole `examples/pages/` folder (fail, on purpose — it
picks up `pages/bad.html`). Its full output is in
`examples/sample-output.md`, ending with `Checked 2
file(s), 1 problem(s) in 1 file(s).` The failing runs exit
1, which is the expected result — the script ends with
exit 0 so it can be run as a demo.

## How it is tested

51 tests, standard library `unittest` only, no packages to install:

```
python3 tests/test_html_title_checker.py
```

The tests cover: the title check (good title, exact 30- and
60-character boundaries, one character too short, one too
long, missing title, empty and whitespace-only titles, two
titles, a second title with its own fault, title after
`</head>`, title in the body, title with no `<head>` tag,
uppercase tags, entities decoded before measuring, markup
inside a title, custom `--min`/`--max`, title text stripped
before measuring), file collection (good file, missing
file, binary skipped, non-UTF-8 reported), folder walking
(only `.html`/`.htm` files, `--no-recursive`, `.git`
skipped, `--exclude`, a direct file checked even without
an `.html` extension and even if excluded, missing path),
the CLI (exit 0/1/2, `--min`/`--max`, `--stdin` good and
bad and non-UTF-8, `--json` output, `--version`, bad flags,
missing paths, empty folders, input files left unchanged,
binary files skipped), the bundled examples (sample output
compared byte-for-byte against a fresh run, and the
README-quoted outputs checked against it), and hygiene
checks (no placeholder text, no absolute paths, stdlib
imports only, `.env` first in `.gitignore`, CI file runs
the test file).

## Contributing

Small, focused improvements are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT — see [LICENSE](LICENSE).

## Original work

This tool was written from scratch for this repo. The idea of
checking page titles is not new — the similar tools named
above (the 0-star name match, the bookmark and live-site
checkers, the broad accessibility and SEO checkers) are
listed in "How this differs" — but every line of code here
is original, and the tool builds on nothing but Python's
standard library.
