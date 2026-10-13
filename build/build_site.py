# -*- coding: utf-8 -*-
"""Rebuild index.html for the java-interview knowledge base.

The UI shell (CSS + app JS) is taken verbatim from the existing index.html, so
only the chapter payload is regenerated. Run:

    python3 build/build_site.py [--out path/to/index.html] [--check]
"""
import argparse
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ji_md  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
HEAD = os.path.join(ROOT, "build", "shell_head.html")
MID = os.path.join(ROOT, "build", "shell_mid.js")
TAIL = os.path.join(ROOT, "build", "shell_tail.js")
INDEX = os.path.join(ROOT, "index.html")

GROUP = {
    "01-java-core": "01 Java 核心",
    "02-concurrency": "02 并发编程",
    "03-jvm": "03 JVM",
    "04-spring": "04 框架",
    "05-database": "05 数据库与缓存",
    "06-distributed": "06 分布式与中间件",
    "07-cs-fundamentals": "07 计算机基础",
}
SPECIAL = {
    "README.md": ("开始", "总览与复习计划"),
    "_STYLE.md": ("附录", "写作规范（附录）"),
}


def chapter_id(rel):
    return "ch-" + rel.replace("/", "-").replace(".", "-")


def collect():
    files = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in (".git", "build", "assets", "node_modules")]
        for fn in filenames:
            if fn.endswith(".md"):
                rel = os.path.relpath(os.path.join(dirpath, fn), ROOT)
                files.append(rel.replace(os.sep, "/"))
    # README first, then chapter dirs in order, then the appendix
    def key(rel):
        if rel == "README.md":
            return (0, "")
        if rel == "_STYLE.md":
            return (2, "")
        return (1, rel)
    return sorted(files, key=key)


def build():
    head = io.open(HEAD, encoding="utf-8").read()
    mid = io.open(MID, encoding="utf-8").read()   # 章节 DOM + 侧栏导航的构建代码
    tail = io.open(TAIL, encoding="utf-8").read()

    chapters = []
    for rel in collect():
        body = io.open(os.path.join(ROOT, rel), encoding="utf-8").read()
        d = os.path.dirname(rel)
        if rel in SPECIAL:
            group, title = SPECIAL[rel]
        else:
            group = GROUP.get(d, d or "其他")
            title, _ = ji_md.extract_meta(body)
            title = title or os.path.splitext(os.path.basename(rel))[0]
        _, subtitle = ji_md.extract_meta(body)
        chapters.append({
            "id": chapter_id(rel),
            "rel": rel,
            "group": group,
            "dir": d,
            "title": title,
            "subtitle": subtitle,
            "html": ji_md.to_html(body),
            "diagrams": ji_md.count_diagrams(body),
            "lines": len(body.splitlines()),
        })

    # 顶栏统计改为自动计算，避免手写数字与实际内容脱节
    content = [c for c in chapters if c["rel"] not in ("README.md", "_STYLE.md")]
    stat = "%d 章 · %s 行 · %d 张 Mermaid 原理图" % (
        len(content), format(sum(c["lines"] for c in content), ","),
        sum(c["diagrams"] for c in content))
    head = re.sub(r'(<div class="stat">)[^<]*(</div>)',
                  lambda m: m.group(1) + stat + m.group(2), head, count=1)

    payload = json.dumps(chapters, ensure_ascii=False).replace("</", "<\\/")
    return head + "const CHAPTERS = " + payload + ";\n" + mid + tail, chapters


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=INDEX)
    ap.add_argument("--check", action="store_true",
                    help="compare the regenerated metadata against the current index.html")
    args = ap.parse_args()

    page, chapters = build()

    if args.check:
        cur = io.open(INDEX, encoding="utf-8").read()
        import re
        old = json.loads(re.search(r"const CHAPTERS = (\[.*?\]);\n", cur, re.S)
                         .group(1).replace("<\\/", "</"))
        o = {c["rel"]: c for c in old}
        n = {c["rel"]: c for c in chapters}
        print("章节数：现有 %d，重新生成 %d" % (len(old), len(chapters)))
        only_old = sorted(set(o) - set(n))
        only_new = sorted(set(n) - set(o))
        if only_old:
            print("仅现有有：", only_old)
        if only_new:
            print("仅新生成有：", only_new)
        diff = 0
        for rel in sorted(set(o) & set(n)):
            for field in ("id", "group", "title", "subtitle", "diagrams", "lines"):
                a, b = o[rel].get(field), n[rel].get(field)
                if a != b:
                    diff += 1
                    if diff <= 15:
                        print("  差异 %s [%s]\n    现有: %r\n    新生成: %r"
                              % (rel, field, str(a)[:90], str(b)[:90]))
        print("元数据差异总数：%d" % diff)
        # heading ids must match exactly
        import re as _re
        ids_old = set(_re.findall(r'<h[1-6] id="([^"]+)"', "".join(c["html"] for c in old)))
        ids_new = set(_re.findall(r'<h[1-6] id="([^"]+)"', "".join(c["html"] for c in chapters)))
        print("标题锚点：现有 %d，新生成 %d，仅现有有 %d，仅新有 %d"
              % (len(ids_old), len(ids_new), len(ids_old - ids_new), len(ids_new - ids_old)))
        for x in sorted(ids_old - ids_new)[:6]:
            print("   仅现有:", x)
        for x in sorted(ids_new - ids_old)[:6]:
            print("   仅新有:", x)

    io.open(args.out, "w", encoding="utf-8").write(page)
    print("写出: %s (%.2f MB, %d 章)" % (args.out, len(page.encode()) / 1024 / 1024, len(chapters)))


if __name__ == "__main__":
    main()
