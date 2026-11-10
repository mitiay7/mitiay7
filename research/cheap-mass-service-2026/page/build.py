#!/usr/bin/env python3
"""Build the reading page from the Markdown report and its appendices.

Usage: python3 build.py [preview_dir]
Writes page/index.html (page content, wrapped in a document skeleton at publish
time) and page/data/*.json (appendix fragments fetched on demand). With
preview_dir, also writes a self-contained local copy for checking in a browser.
Requires: pip install markdown
"""
import html
import json
import pathlib
import re
import sys

import markdown

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE.parent

MARKS = {
    "✅": ("v", "найдено поиском в надёжном источнике"),
    "◐": ("h", "вторичный или вендорский источник"),
    "○": ("e", "память модели или оценка"),
}
# Finalist ids used in FINALISTS.md -> letters used in the report.
LETTER = {"F1": "A", "F2": "B", "F3": "C", "F4": "D", "HF1": "E", "HF2": "F",
          "HF3": "G", "HF4": "H", "HF5": "I", "F5": "J"}
LIST_RE = re.compile(r"^\s*(?:[-*]|\d+\.)\s")


def prep(md):
    """Escape stray HTML and add the blank lines Python-Markdown needs before lists."""
    md = html.unescape(md).replace("&", "&amp;").replace("<", "&lt;")
    out = []
    for line in md.split("\n"):
        prev = out[-1] if out else ""
        if LIST_RE.match(line) and prev.strip() and not LIST_RE.match(prev) and not prev.startswith("  "):
            out.append("")
        out.append(line)
    return "\n".join(out)


def outside_tags(fragment, fn):
    parts = re.split(r"(<[^>]+>)", fragment)
    return "".join(p if p.startswith("<") else fn(p) for p in parts)


def marks(fragment):
    """Turn the three mark characters into styled dots that stay attached to the neighbouring text."""
    def one(text):
        def dot(m):
            cls, label = MARKS[m.group(2)]
            glue = "\u00a0" if m.group(1) else ""
            return (f'{glue}<span class="nb"><span class="mk mk-{cls}" role="img" aria-label="{label}" '
                    f'title="{label}"></span>{m.group(3)}</span>')
        return re.sub(r"( ?)([✅◐○])([.,;:)]?)", dot, text)
    return outside_tags(fragment, one)


def nbsp(fragment):
    """Keep digit groups and a number with its unit on one line."""
    def one(text):
        text = re.sub(r"(?<=\d) (?=\d{3}(?!\d))", "\u202f", text)
        return re.sub(r"(?<=\d) (?=(?:₽|%|тыс\.|млн|млрд|руб\.))", "\u00a0", text)
    return outside_tags(fragment, one)


def autolink(fragment):
    def one(text):
        def link(m):
            url = m.group(0).rstrip(".,;)")
            tail = m.group(0)[len(url):]
            shown = re.sub(r"^https?://(www\.)?", "", url)
            shown = shown if len(shown) <= 60 else shown[:57] + "…"
            return f'<a class="src" href="{url}" target="_blank" rel="noopener">{shown}</a>{tail}'
        return re.sub(r"https?://[^\s<>\"]+", link, text)
    return outside_tags(fragment, one)


def tables(fragment):
    return fragment.replace("<table>", '<div class="tw"><table>').replace("</table>", "</table></div>")


def convert(md):
    body = markdown.markdown(prep(md), extensions=["tables", "sane_lists"])
    return tables(nbsp(marks(body))).replace("<hr />", "")


def plain(fragment):
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


# ---------- the report ----------
def build_report():
    md = (SRC / "REPORT.md").read_text()
    body = convert(md)
    # Title block: h1 and the paragraphs before the first h2.
    m = re.match(r"\s*<h1>(.*?)</h1>(.*?)(?=<h2>)", body, re.S)
    title, lead = m.group(1), re.findall(r"<p>(.*?)</p>", m.group(2), re.S)
    body = body[m.end():]
    dek = lead[0] if lead else ""
    date = plain(lead[1]).replace("Дата:", "").strip().rstrip(".") if len(lead) > 1 else ""

    # Appendix file names -> tab links.
    tabs = {"FINALISTS.md": ("finalists", "«Финалисты»"), "SOURCES.md": ("sources", "«Источники»"),
            "CANDIDATES.md": ("candidates", "«Кандидаты»")}
    body = re.sub(r"<p><strong>Файлы рядом:</strong>.*?</p>",
                  '<p><strong>Приложения во вкладках:</strong> <a href="#finalists">«Финалисты»</a> — полные карточки '
                  'десяти финалистов; <a href="#sources">«Источники»</a> — факты со ссылками; '
                  '<a href="#candidates">«Кандидаты»</a> — все 36 кандидатов первой волны с оценками жюри '
                  '(рабочие материалы, на английском).</p>', body, flags=re.S)
    for name, (view, label) in tabs.items():
        body = body.replace(f"в <code>{name}</code>", f'во вкладке <a href="#{view}">{label}</a>')
        body = body.replace(f"<code>{name}</code>", f'<a href="#{view}">{label}</a>')

    # Heading ids, table-of-contents flags, finalist badges.
    state = {"h2": 0, "h3": 0, "sec": ""}

    def heading(m):
        level, inner = m.group(1), m.group(2)
        text = plain(inner)
        if level == "2":
            state["h2"] += 1
            state["h3"] = 0
            state["sec"] = text
            hid = f"s{state['h2']}"
            return f'<h2 id="{hid}" data-toc="1">{inner}</h2>'
        state["h3"] += 1
        hid = f"s{state['h2']}-{state['h3']}"
        fin = re.match(r"^([A-J])\. (.+)$", text) if state["sec"].startswith("8.") else None
        if fin:
            letter = fin.group(1)
            rest = inner.split(". ", 1)[1]
            more = (f'<p class="more"><a href="#finalists" data-view="finalists" data-target="fin-{letter}">'
                    f'Полная карточка во вкладке «Финалисты»</a></p>')
            return (f'<h3 id="{hid}" class="fin" data-toc="2" data-label="{letter}. {html.escape(plain(rest).split(" — ")[0])}">'
                    f'<span class="fin-l">{letter}</span><span>{rest}</span></h3>{more}')
        in_toc = ' data-toc="2"' if state["sec"].startswith(("8.", "9.")) else ""
        return f'<h3 id="{hid}"{in_toc}>{inner}</h3>'

    body = re.sub(r"<h([23])>(.*?)</h\1>", heading, body, flags=re.S)

    # Red-team verdict callouts.
    def verdict(m):
        text = plain(m.group(0))
        tone = "risk" if "рискованно" in text.split(".")[0] else "kill"
        return m.group(0).replace("<p>", f'<p class="verdict {tone}">', 1)
    body = re.sub(r"<p><strong>Красная команда:.*?</p>", verdict, body, flags=re.S)

    # The summary becomes its own block.
    m = re.search(r'<h2 id="s1" data-toc="1">Коротко</h2>(.*?)(?=<h2 )', body, re.S)
    brief = f'<section class="brief"><h2 id="s1" data-toc="1">Коротко</h2>{m.group(1)}</section>'
    body = body[:m.start()] + brief + body[m.end():]
    return title, dek, date, body


# ---------- appendices ----------
def build_finalists():
    md = (SRC / "FINALISTS.md").read_text()
    head, *blocks = re.split(r"\n(?=## )", md)
    cards = {}
    for b in blocks:
        m = re.match(r"## (H?F\d)\. (.*)", b)
        if not m:
            continue
        letter = LETTER[m.group(1)]
        b = b.replace(m.group(0), f"## {letter}. {m.group(2)}", 1)
        cards[letter] = re.sub(r"\n---\s*$", "", b.strip())
    intro = convert(re.sub(r"^# .*\n", "", head))
    out = [intro]
    for letter in sorted(cards):
        frag = autolink(convert(cards[letter]))
        frag = re.sub(r"<h2>(.*?)</h2>",
                      lambda m, l=letter: (f'<h2 id="fin-{l}" data-toc="1" data-label="{html.escape(plain(m.group(1)).split(" — ")[0])}">'
                                           f'{m.group(1)}</h2>'), frag, count=1, flags=re.S)
        out.append(f'<article class="card">{frag}</article>')
    return "".join(out)


def build_plain(name, prefix):
    md = (SRC / name).read_text()
    md = re.sub(r"^# .*\n", "", md)
    frag = autolink(convert(md))
    n = {"h2": 0, "h3": 0}

    def head(m):
        level, inner = m.group(1), m.group(2)
        if level == "2":
            n["h2"] += 1
            n["h3"] = 0
            return f'<h2 id="{prefix}-{n["h2"]}" data-toc="1">{inner}</h2>'
        n["h3"] += 1
        label = re.split(r" — | - ", plain(inner))[0]
        return f'<h3 id="{prefix}-{n["h2"]}-{n["h3"]}" data-toc="2" data-label="{html.escape(label)}">{inner}</h3>'
    return re.sub(r"<h([23])>(.*?)</h\1>", head, frag, flags=re.S)


TEMPLATE = (HERE / "template.html").read_text()
SKELETON = ('<!doctype html><html><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
            '<style>:root{color-scheme:light;padding:env(safe-area-inset-top,0px) 0 env(safe-area-inset-bottom,0px)}'
            'body{margin:0;font:14px system-ui,sans-serif}img{max-width:100%}[hidden]{display:none!important}</style>'
            '</head><body>@@PAGE@@</body></html>')


def main():
    title, dek, date, report = build_report()
    page = (TEMPLATE.replace("{{TITLE}}", title).replace("{{DEK}}", dek)
            .replace("{{DATE}}", date).replace("{{REPORT}}", report))
    (HERE / "index.html").write_text(page)
    data = HERE / "data"
    data.mkdir(exist_ok=True)
    fragments = {"finalists": build_finalists(), "sources": build_plain("SOURCES.md", "src"),
                 "candidates": build_plain("CANDIDATES.md", "cand")}
    for name, frag in fragments.items():
        (data / f"{name}.json").write_text(json.dumps({"html": frag}, ensure_ascii=False))
    print("index.html", len(page) // 1024, "KB;", {k: len(v) // 1024 for k, v in fragments.items()}, "KB")
    if len(sys.argv) > 1:
        prev = pathlib.Path(sys.argv[1])
        (prev / "data").mkdir(parents=True, exist_ok=True)
        (prev / "index.html").write_text(SKELETON.replace("@@PAGE@@", page))
        for name, frag in fragments.items():
            (prev / "data" / f"{name}.json").write_text(json.dumps({"html": frag}, ensure_ascii=False))
        print("preview written to", prev)


if __name__ == "__main__":
    main()
