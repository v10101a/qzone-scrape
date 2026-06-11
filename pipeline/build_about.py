#!/usr/bin/env python3
"""Bake web/about.{zh,en}.md into web/about.html.

The about page is bilingual; editing interlaced zh/en HTML was painful, so the
prose lives in two plain-markdown files and this script renders them into the
marked regions of web/about.html:

    <!-- ABOUT:zh --> ... <!-- /ABOUT:zh -->
    <!-- ABOUT:en --> ... <!-- /ABOUT:en -->

Everything outside the markers (head, topbar, lang-toggle script) is
hand-edited HTML and left untouched.

Supported markdown: ## headings, paragraphs, - lists (wrapped lines ok),
[links](url), **bold**, *em*, `code`, raw-HTML passthrough (block starting
with <), HTML comments (dropped). A paragraph may start with {.lead} or
{.fine} to get that class. Two directives:

    ::: stats          ::: go
    5,863 | 藏品        ← 浏览藏品 | index.html
    :::                :::

Run from anywhere:  python3 pipeline/build_about.py
"""
import re
from pathlib import Path

MUSEUM = Path(__file__).resolve().parent.parent / "web"


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def inline(s):
    s = esc(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", s)

    def link(m):
        text, url = m.group(1), m.group(2)
        ext = ' target="_blank" rel="noopener"' if url.startswith("http") else ""
        return f'<a href="{url}"{ext}>{text}</a>'

    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, s)


def directive_rows(lines):
    """'a | b' rows between '::: name' and ':::'."""
    rows = [l.strip() for l in lines[1:] if l.strip() and l.strip() != ":::"]
    return [tuple(p.strip() for p in r.split("|", 1)) for r in rows]


def split_blocks(md):
    """Blank-line-separated blocks; a paragraph butted directly against a
    list ("Credits\n- ...") is split into two blocks."""
    blocks = []
    for block in re.split(r"\n\s*\n", md.strip()):
        lines = [l.rstrip() for l in block.strip().splitlines()]
        if not lines:
            continue
        if not lines[0].startswith(("#", ":::", "<", "- ")):
            for i, l in enumerate(lines):
                if l.lstrip().startswith("- "):
                    if i:
                        blocks.append(lines[:i])
                    blocks.append(lines[i:])
                    break
            else:
                blocks.append(lines)
        else:
            blocks.append(lines)
    return blocks


def render(md):
    out = []
    for lines in split_blocks(md):
        first = lines[0]
        if first.startswith("<!--"):
            continue  # source-file notes stay out of the page
        if first.startswith("<"):
            out.append("\n".join(lines))  # raw HTML passthrough
        elif first.startswith("## "):
            out.append(f"<h2>{inline(first[3:])}</h2>")
            rest = " ".join(lines[1:]).strip()
            if rest:
                out.append(f"<p>{inline(rest)}</p>")
        elif first.startswith("::: stats"):
            stats = "".join(
                f'<div class="stat"><span class="num">{inline(num)}</span>'
                f'<span class="lab">{inline(lab)}</span></div>'
                for num, lab in directive_rows(lines)
            )
            out.append(f'<div class="about-stats">{stats}</div>')
        elif first.startswith("::: go"):
            links = "".join(
                f'<a class="go" href="{href}">{inline(text)}</a>'
                for text, href in directive_rows(lines)
            )
            out.append(f'<p class="about-go">{links}</p>')
        elif first.lstrip().startswith("- "):
            items, cur = [], None
            for l in lines:
                ls = l.strip()
                if ls.startswith("- "):
                    if cur is not None:
                        items.append(cur)
                    cur = ls[2:]
                else:
                    cur += " " + ls
            items.append(cur)
            out.append("<ul>" + "".join(f"<li>{inline(i)}</li>" for i in items) + "</ul>")
        else:
            text = " ".join(lines).strip()
            cls = ""
            m = re.match(r"\{\.(\w+)\}\s*", text)
            if m:
                cls, text = f' class="{m.group(1)}"', text[m.end():]
            out.append(f"<p{cls}>{inline(text)}</p>")
    return "\n".join(out)


def main():
    page = MUSEUM / "about.html"
    html = page.read_text(encoding="utf-8")
    for lang in ("zh", "en"):
        body = render((MUSEUM / f"about.{lang}.md").read_text(encoding="utf-8"))
        block = (
            f"<!-- ABOUT:{lang} -->\n"
            f'<div class="{lang}">\n{body}\n</div>\n'
            f"      <!-- /ABOUT:{lang} -->"
        )
        pat = re.compile(f"<!-- ABOUT:{lang} -->.*?<!-- /ABOUT:{lang} -->", re.S)
        if not pat.search(html):
            raise SystemExit(f"marker <!-- ABOUT:{lang} --> not found in {page}")
        html = pat.sub(lambda m: block, html)
    page.write_text(html, encoding="utf-8")
    print(f"rebuilt {page} from about.zh.md + about.en.md")


if __name__ == "__main__":
    main()
