# -*- coding: utf-8 -*-
"""Markdown -> HTML renderer for the java-interview knowledge base.

Reproduces the exact conventions of the existing index.html:
  * heading ids are slugs capped at 80 chars, entities are NOT unescaped first
  * the per-page TOC is built from h2 only
  * fenced ```mermaid blocks become <pre class="mermaid"> for client-side rendering
  * fenced code blocks become .code-block with highlight.js class names
"""
import html
import re

# ------------------------------------------------------------------ highlighting
KW = {
    "java": r"public|private|protected|static|final|abstract|class|interface|enum|record"
            r"|extends|implements|return|new|void|int|long|double|float|boolean|char|byte"
            r"|short|if|else|for|while|do|switch|case|default|try|catch|finally|throw"
            r"|throws|import|package|this|super|null|true|false|var|instanceof"
            r"|synchronized|volatile|transient|native|assert|strictfp",
    "python": r"def|class|return|if|elif|else|for|while|import|from|as|with|try|except"
              r"|finally|raise|lambda|yield|await|async|pass|break|continue|in|is|not"
              r"|and|or|None|True|False|self|global|nonlocal|assert|del",
}
BUILTIN = {
    "java": r"String|Integer|Long|Double|Float|Boolean|Character|Object|Class|System"
            r"|Thread|Runnable|Exception|RuntimeException|Error|Throwable|List|Map|Set"
            r"|ArrayList|HashMap|HashSet|Collections|Arrays|Objects|Optional|Stream",
}
RULES = {
    "java": [
        ("comment", r"//[^\n]*|/\*[\s\S]*?\*/"),
        ("string", r'"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\''),
        ("meta", r"@[A-Za-z_][\w.]*"),
        ("keyword", r"\b(?:" + KW["java"] + r")\b"),
        ("number", r"\b\d[\d_]*(?:\.\d+)?[LlFfDd]?\b"),
        ("built_in", r"\b(?:" + BUILTIN["java"] + r")\b"),
        ("type", r"\b[A-Z][A-Za-z0-9_]*\b"),
        ("title", r"\b[a-z_]\w*(?=\s*\()"),
        ("operator", r"[+\-*/%=<>!&|^~?:]+"),
        ("punctuation", r"[{}()\[\];,.]"),
    ],
    "python": [
        ("comment", r"#[^\n]*"),
        ("string", r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'|f"(?:\\.|[^"\\\n])*"'),
        ("meta", r"@[A-Za-z_][\w.]*"),
        ("keyword", r"\b(?:" + KW["python"] + r")\b"),
        ("number", r"\b\d[\d_]*(?:\.\d+)?\b"),
        ("title", r"\b[A-Za-z_]\w*(?=\s*\()"),
        ("operator", r"[+\-*/%=<>!&|^~]+"),
        ("punctuation", r"[{}()\[\];,.:]"),
    ],
    "bash": [
        ("comment", r"#[^\n]*"),
        ("string", r'"(?:\\.|[^"\\\n])*"|\'[^\'\n]*\''),
        ("built_in", r"(?m:^\s*(?:curl|uv|java|javac|jps|jmap|jstack|jstat|jcmd|jinfo|docker|kubectl|git|mvn|gradle|export|cd|echo|grep|awk|sed|sysctl|ulimit|printf|top|free|vmstat|iostat|netstat|ss|tcpdump)\b)"),
        ("attr", r"(?<=\s)--?[A-Za-z][\w.-]*"),
        ("number", r"\b\d+(?:\.\d+)?\b"),
    ],
    "sql": [
        ("comment", r"--[^\n]*"),
        ("string", r"'[^'\n]*'"),
        ("keyword", r"(?i:\b(?:SELECT|FROM|WHERE|JOIN|LEFT|RIGHT|INNER|OUTER|ON|GROUP|BY|ORDER|HAVING|LIMIT|OFFSET|INSERT|INTO|VALUES|UPDATE|SET|DELETE|CREATE|TABLE|INDEX|ALTER|DROP|EXPLAIN|ANALYZE|AND|OR|NOT|NULL|IS|AS|DESC|ASC|UNION|ALL|DISTINCT|COUNT|SUM|AVG|MIN|MAX|BEGIN|COMMIT|ROLLBACK|FOR|UPDATE)\b)"),
        ("number", r"\b\d+(?:\.\d+)?\b"),
    ],
    "xml": [
        ("comment", r"<!--[\s\S]*?-->"),
        ("string", r'"[^"\n]*"'),
        ("tag", r"</?[\w:.-]+|/?>"),
        ("attr", r"\b[a-zA-Z_:][\w:.-]*(?=\s*=)"),
    ],
    "properties": [
        ("comment", r"#[^\n]*"),
        ("attr", r"^[A-Za-z_][\w.\-]*(?==)"),
        ("number", r"\b\d+(?:\.\d+)?\b"),
    ],
    "yaml": [
        ("comment", r"#[^\n]*"),
        ("attr", r"^\s*[\w.\-]+(?=:)"),
        ("string", r'"[^"\n]*"|\'[^\'\n]*\''),
        ("number", r"\b\d+(?:\.\d+)?\b"),
    ],
    "text": [], "plaintext": [], "bash-session": [], "json": [
        ("string", r'"(?:\\.|[^"\\\n])*"'),
        ("keyword", r"\b(?:true|false|null)\b"),
        ("number", r"-?\b\d+(?:\.\d+)?\b"),
    ],
}
ALIAS = {"sh": "bash", "shell": "bash", "py": "python", "text": "text", "plain": "text",
         "plaintext": "text", "yml": "yaml", "dockerfile": "bash", "ini": "properties",
         "conf": "properties", "md": "text", "markdown": "text"}


def _tok_html(code, lang):
    lang = ALIAS.get(lang, lang)
    rules = RULES.get(lang)
    if not rules:
        return html.escape(code)
    # group names get an index so duplicate rule kinds never collide in the master pattern
    named = [("g%d" % k, kind, pat) for k, (kind, pat) in enumerate(rules)]
    master = re.compile("|".join("(?P<%s>%s)" % (g, p) for g, _, p in named))
    kind_of = {g: kind for g, kind, _ in named}
    out, pos = [], 0
    for m in master.finditer(code):
        if m.start() > pos:
            out.append(html.escape(code[pos:m.start()]))
        kind = kind_of[m.lastgroup]
        extra = " function_" if kind == "title" else ""
        out.append('<span class="hljs-%s%s">%s</span>'
                   % (kind, extra, html.escape(m.group(0))))
        pos = m.end()
    out.append(html.escape(code[pos:]))
    return "".join(out)


# ----------------------------------------------------------------------- inline
_IMG = r"!\[([^\]]*)\]\(([^)\s]+)\)"
_LINK = r"\[([^\]]+)\]\(([^)\s]+)\)"
_CODE = r"`([^`]+)`"
_BOLD = r"\*\*([^*]+)\*\*"
_ITAL = r"(?<!\*)\*([^*]+)\*(?!\*)"
_INLINE = re.compile("|".join([_IMG, _LINK, _CODE, _BOLD, _ITAL]))


def inline(text):
    out, pos = [], 0
    for m in _INLINE.finditer(text):
        out.append(html.escape(text[pos:m.start()]))
        if m.group(1) is not None:
            out.append('<img src="%s" alt="%s">' % (html.escape(m.group(2)), html.escape(m.group(1))))
        elif m.group(3) is not None:
            out.append('<a href="%s">%s</a>' % (html.escape(m.group(4)), inline(m.group(3))))
        elif m.group(5) is not None:
            out.append("<code>%s</code>" % html.escape(m.group(5)))
        elif m.group(6) is not None:
            out.append("<strong>%s</strong>" % inline(m.group(6)))
        else:
            out.append("<em>%s</em>" % inline(m.group(7)))
        pos = m.end()
    out.append(html.escape(text[pos:]))
    return "".join(out)


# ----------------------------------------------------------------------- blocks
_FENCE = re.compile(r"^\s*```+\s*([\w+#.-]*)\s*$")
_HEAD = re.compile(r"^(#{1,6})\s+(.*)$")
_HR = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
_UL = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_OL = re.compile(r"^(\s*)(\d+)[.)]\s+(.*)$")
_TSEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$")


def slug(t):
    t = re.sub(r"<[^>]+>", "", t)
    t = t.lower()
    t = re.sub(r"[^\w\u4e00-\u9fff\s-]", "", t)
    return re.sub(r"\s+", "-", t.strip())[:80]


def _row(line):
    """Split a table row on UNESCAPED pipes; `\\|` becomes a literal `|`.

    GFM requires cell-internal pipes to be escaped, and this repo follows that
    convention (e.g. `tagA \\|\\| tagB`). A naive split("|") would break those
    rows into extra columns.
    """
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    cells, cur, i = [], "", 0
    while i < len(line):
        c = line[i]
        if c == "\\" and i + 1 < len(line) and line[i + 1] == "|":
            cur += "|"
            i += 2
            continue
        if c == "|":
            cells.append(cur.strip())
            cur = ""
            i += 1
            continue
        cur += c
        i += 1
    cells.append(cur.strip())
    return cells


def render(body):
    """Return (html, toc) where toc is a list of (anchor, text) for h2 headings."""
    lines = body.replace("\r\n", "\n").split("\n")
    out, toc, i, n = [], [], 0, len(lines)

    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1
            continue

        m = _FENCE.match(line)
        if m:
            ticks = len(re.match(r"^\s*(`+)", line).group(1))
            lang = (m.group(1) or "text").lower()
            i += 1
            buf = []
            # 只有「不短于开启围栏」且不带语言标记的围栏才能闭合它，
            # 这样 _STYLE.md 里 ````markdown 中嵌套的 ```mermaid 才不会被误判为结束。
            close = re.compile(r"^\s*`{%d,}\s*$" % ticks)
            while i < n and not close.match(lines[i]):
                buf.append(lines[i])
                i += 1
            i += 1
            code = "\n".join(buf)
            if lang == "mermaid":
                out.append('<div class="diagram"><pre class="mermaid">%s</pre></div>'
                           % html.escape(code, quote=True))
            else:
                out.append('<div class="code-block"><span class="code-lang">%s</span>'
                           '<pre><code class="hljs">%s</code></pre></div>'
                           % (html.escape(lang), _tok_html(code, lang)))
            continue

        m = _HEAD.match(line)
        if m:
            lv = len(m.group(1))
            inner = inline(m.group(2).strip())
            # 锚点基于**渲染后的 HTML** 计算（剥标签、不解实体），而不是原始 Markdown；
            # 否则标题里的 [文字](链接) 会把 URL 也搅进 slug。
            sid = slug(inner)
            out.append('<h%d id="%s">%s</h%d>' % (lv, sid, inner, lv))
            if lv == 2:
                toc.append((sid, re.sub(r"<[^>]+>", "", inner)))
            i += 1
            continue

        if _HR.match(line):
            out.append("<hr>")
            i += 1
            continue

        if "|" in line and i + 1 < n and _TSEP.match(lines[i + 1]):
            head = _row(line)
            i += 2
            rows = []
            while i < n and "|" in lines[i] and lines[i].strip():
                r = _row(lines[i])
                rows.append((r + [""] * len(head))[:len(head)])
                i += 1
            out.append('<div class="table-wrap"><table><thead><tr>\n')
            out.append("\n".join("<th>%s</th>" % inline(h) for h in head))
            out.append("\n</tr>\n</thead><tbody>")
            for r in rows:
                out.append("<tr>\n" + "\n".join("<td>%s</td>" % inline(c) for c in r) + "\n</tr>")
            out.append("</tbody></table></div>")
            continue

        if line.lstrip().startswith(">"):
            buf = []
            while i < n and lines[i].lstrip().startswith(">"):
                buf.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            paras = [p for p in re.split(r"\n\s*\n", "\n".join(buf).strip()) if p.strip()]
            out.append("<blockquote>\n" + "\n".join("<p>%s</p>" % inline(p.replace("\n", " "))
                                                     for p in paras) + "\n</blockquote>")
            continue

        mu, mo = _UL.match(line), _OL.match(line)
        if mu or mo:
            ordered = bool(mo)
            items, base = [], None
            while i < n:
                cur = lines[i]
                if cur.strip():
                    a, b = _UL.match(cur), _OL.match(cur)
                    if not (a or b):
                        break
                    ind = len((a or b).group(1))
                    if base is None:
                        base = ind
                    if ind < base:
                        break
                    if ind - base >= 2 and items:
                        items[-1][1].append(cur.strip())
                        i += 1
                        continue
                    if b:
                        ordered = True
                    items.append([(a.group(2) if a else b.group(3)), []])
                    i += 1
                elif i + 1 < n and lines[i + 1].strip() and \
                        (len(lines[i + 1]) - len(lines[i + 1].lstrip())) > (base or 0):
                    i += 1
                else:
                    break
            tag = "ol" if ordered else "ul"
            out.append("<%s>\n" % tag)
            for txt, sub in items:
                out.append("<li>%s" % inline(txt))
                if sub:
                    out.append("<ul>\n" + "\n".join("<li>%s</li>" % inline(s.lstrip("-*+ "))
                                                    for s in sub) + "\n</ul>")
                out.append("</li>")
            out.append("\n</%s>" % tag)
            continue

        buf = [line]
        i += 1
        while i < n and lines[i].strip() and not (
                _FENCE.match(lines[i]) or _HEAD.match(lines[i]) or _HR.match(lines[i])
                or lines[i].lstrip().startswith(">") or _UL.match(lines[i])
                or _OL.match(lines[i]) or "|" in lines[i]):
            buf.append(lines[i])
            i += 1
        out.append("<p>%s</p>" % inline(" ".join(buf).strip()))

    return "\n".join(out), toc


def page_toc(toc):
    if not toc:
        return ""
    items = "".join('<li><a href="#%s">%s</a></li>' % (a, t) for a, t in toc)
    return ('<details class="page-toc"><summary>本页大纲（%d 节）</summary><ul>%s</ul></details>'
            % (len(toc), items))


def to_html(body):
    h, toc = render(body)
    return page_toc(toc) + h


def extract_meta(body):
    """Return (title, subtitle) taken from the H1 and the first blockquote."""
    lines = body.split("\n")
    title = ""
    subtitle = ""
    for idx, ln in enumerate(lines):
        if not title and ln.startswith("# "):
            title = ln[2:].strip()
        if title and ln.lstrip().startswith(">"):
            subtitle = ln.lstrip().lstrip(">").strip()
            break
    return title, subtitle


def count_diagrams(body):
    """Count top-level mermaid fences only — a ```mermaid nested inside a longer
    fence (````markdown) is an example, not a diagram."""
    n, open_len = 0, 0
    for ln in body.split("\n"):
        m = re.match(r"^\s*(`+)\s*([\w+#.-]*)\s*$", ln)
        if not m:
            continue
        ticks, info = len(m.group(1)), m.group(2).lower()
        if open_len == 0:
            open_len = ticks
            if info == "mermaid":
                n += 1
        elif ticks >= open_len and not info:
            open_len = 0
    return n
