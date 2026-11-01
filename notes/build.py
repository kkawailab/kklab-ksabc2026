#!/usr/bin/env python3
"""markdown/noteNN.md を原稿として、講義ノートの Word 版と PDF 版を作る。

  python3 notes/build.py            5回分すべて
  python3 notes/build.py 06 09      指定した回だけ

PDF は日本語 LuaLaTeX（jlreq、luatexja）で組み、組版に使った LaTeX の原稿を tex/ に残す。
各回は、講義ページの「講義の流れ」の4つのトピックからなり、1トピックを1ページに収める。
収まらなければ、どのトピックがあふれたかを示して止まる。Word 版は LibreOffice で PDF にして
同じ検査をする（Word 本体とはフォントが違うので、目安）。

原稿の解釈と組版の部品は worksheets/build.py のものを使う。原稿の Markdown は次の書き方だけを解釈する。

  # 第6回講義ノート　題名             表題（全角スペースの前が回、後ろが題名）
  （次の段落）                        科目名と日付の行
  ## 1｜トピック名                   トピック。名前は講義ページの「講義の流れ」と同じにする
  ### 小見出し
  - 箇条書き、1. 番号、| 表 |、**太字**、[リンク](URL)
  > **ポイント**　…                  囲み。**確認** で始めると、確認の問いの囲みになる
  出典：… / 参考：…                  小さい注記
"""
import html
import importlib.util
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from docx.enum.text import WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def load_worksheets_build():
    """worksheets/build.py を、名前が同じこのファイルと混同しないように、パスで読み込む。"""
    spec = importlib.util.spec_from_file_location("worksheets_build", ROOT / "worksheets" / "build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ws = load_worksheets_build()

MD_DIR, WORD_DIR, PDF_DIR, TEX_DIR = HERE / "markdown", HERE / "word", HERE / "pdf", HERE / "tex"
NUMS = ws.NUMS
COURSE = ws.COURSE


# ------------------------------------------------------------
# 原稿
# ------------------------------------------------------------
def load(num):
    blocks = ws.parse((MD_DIR / f"note{num}.md").read_text(encoding="utf-8"))
    title = next(b["text"] for b in blocks if b["type"] == "h1")
    label, name = title.split("　", 1)
    h1 = next(k for k, b in enumerate(blocks) if b["type"] == "h1")
    sub = blocks[h1 + 1]["text"]
    topics, cur = [], None
    for b in blocks[h1 + 2:]:
        if b["type"] == "h2":
            no, _, heading = b["text"].partition("｜")
            cur = {"no": int(no), "title": heading, "blocks": []}
            topics.append(cur)
        elif cur is None:
            sys.exit(f"{label}: 最初のトピックより前に本文があります: {b}")
        else:
            cur["blocks"].append(b)
    return {"num": num, "title": title, "label": label, "name": name, "sub": sub, "topics": topics}


def check_against_page(doc):
    """トピック名と題名が講義ページと同じかを確かめる。"""
    page = html.unescape((ROOT / "lectures" / f"lecture{doc['num']}.html").read_text(encoding="utf-8"))
    flow = re.search(r'<ol class="flow-list">(.*?)</ol>', page, re.S).group(1)
    parts = re.findall(r"<h3>(.*?)</h3>", flow)
    titles = [t["title"] for t in doc["topics"]]
    errors = []
    if parts != titles:
        errors.append(f"トピックが講義ページと違います: {parts} / {titles}")
    if [t["no"] for t in doc["topics"]] != list(range(1, len(parts) + 1)):
        errors.append("トピックの番号が1からの連番になっていません")
    if f"第{int(doc['num'])}回 {doc['name']}" not in page:
        errors.append(f"題名が講義ページにありません: {doc['name']}")
    if errors:
        sys.exit(f"{doc['label']}: " + "\n  ".join(errors))


def quote_kind(paras):
    return "check" if paras and paras[0].startswith("**確認**") else "note"


# ------------------------------------------------------------
# PDF（LuaLaTeX）
# ------------------------------------------------------------
NOTE_PREAMBLE = r"""
\usepackage{array}
\newcommand\topichead[4]{% 回の表示、トピック番号、全トピック数、題
  {\sffamily\footnotesize\color{grayt}#1\par}\vspace{1.5mm}
  {\sffamily\bfseries\LARGE #4}\hfill\colorbox{accent}{\sffamily\footnotesize\bfseries トピック #2 / #3}\par
  \vspace{1.2mm}{\color{ink}\hrule height 0.6pt}\vspace{3mm}}
\newcommand\subhead[1]{\par\vspace{2.6mm}{\sffamily\bfseries\large #1}\par\vspace{1.3mm}}
\newtcolorbox{checkbox}{enhanced,colback=white,colframe=coral,boxrule=0.5pt,arc=1mm,
  left=2.5mm,right=2.5mm,top=1.2mm,bottom=1.2mm,before skip=2mm,after skip=1mm,fontupper=\small}
"""


def table_widths(ncols):
    """列幅（mm）。列の内側の余白（左右 1.5mm ずつ）を引いた幅で、先頭の列は見出しになりやすいので狭くする。"""
    total = 169 - 3 * ncols
    if ncols == 1:
        return [total]
    if ncols == 2:
        return [38, total - 38]
    first = 24
    rest = (total - first) / (ncols - 1)
    return [first] + [rest] * (ncols - 1)


def tex_table(rows):
    widths = table_widths(len(rows[0]))
    spec = "|" + "|".join(f"p{{{w:.1f}mm}}" for w in widths) + "|"
    out = [r"\begin{center}\small\renewcommand{\arraystretch}{1.15}\setlength{\tabcolsep}{1.5mm}",
           rf"\begin{{tabular}}{{{spec}}}\arrayrulecolor{{rulec}}\hline"]
    for r, cells in enumerate(rows):
        cells = cells + [""] * (len(widths) - len(cells))
        if r == 0:
            out.append(r"\rowcolor{papertwo}" + " & ".join(r"\sffamily\bfseries " + ws.tex_escape(c) for c in cells) + r"\\\hline")
        else:
            out.append(" & ".join(ws.tex_inline(c) for c in cells) + r"\\\hline")
    out.append(r"\end{tabular}\end{center}\vspace{0.5mm}")
    return "\n".join(out)


def tex_blocks(blocks):
    out = []
    for b in blocks:
        t = b["type"]
        if t == "h3":
            out.append(r"\subhead{" + ws.tex_inline(b["text"]) + "}")
        elif t == "p":
            text = b["text"]
            if text.startswith("※"):
                out.append(r"{\footnotesize\color{grayt}" + ws.tex_inline(text) + r"\par}")
            elif text.startswith(("出典", "参考")):
                out.append(r"\vspace{1.5mm}{\sffamily\footnotesize\color{grayt}" + ws.tex_inline(text) + r"\par}")
            else:
                out.append(ws.tex_inline(text) + r"\par\vspace{1.2mm}")
        elif t in ("ul", "ol"):
            env = "itemize" if t == "ul" else "enumerate"
            out.append(rf"\begin{{{env}}}[leftmargin=1.5em,itemsep=0.6mm,topsep=0.3mm]")
            out.extend(r"\item " + ws.tex_inline(i) for i in b["items"])
            out.append(rf"\end{{{env}}}\vspace{{0.8mm}}")
        elif t == "quote":
            env = "checkbox" if quote_kind(b["paras"]) == "check" else "hintbox"
            out.append(rf"\begin{{{env}}}")
            out.extend(ws.tex_inline(p) + r"\par" for p in b["paras"])
            out.append(rf"\end{{{env}}}")
        elif t == "table":
            out.append(tex_table(b["rows"]))
        else:
            sys.exit(f"講義ノートでは使えない書き方です: {t}")
    return out


def build_tex(doc):
    out = [ws.tex_preamble(), NOTE_PREAMBLE]
    out.append(r"\newcommand*\wslabel{" + ws.tex_escape(doc["label"]) + "}")
    out.append(r"\hypersetup{pdftitle={" + ws.tex_escape(doc["title"]) + r"},pdfauthor={河合 勝彦},pdfsubject={" + COURSE + "}}")
    out.append(r"\begin{document}")
    head = ws.tex_escape(f"{doc['label']}｜{doc['name']}｜{doc['sub'].split('｜', 1)[-1]}")
    n = len(doc["topics"])
    for k, topic in enumerate(doc["topics"]):
        if k:
            out.append(r"\clearpage")
        out.append(rf"\topichead{{{head}}}{{{topic['no']}}}{{{n}}}{{{ws.tex_escape(topic['title'])}}}")
        out.extend(tex_blocks(topic["blocks"]))
    out.append(r"\end{document}")
    return "\n".join(out)


# ------------------------------------------------------------
# Word
# ------------------------------------------------------------
def docx_table(doc_, rows):
    widths = table_widths(len(rows[0]))
    table = ws.make_table(doc_, len(rows), widths)
    for r, (row, cells) in enumerate(zip(table.rows, rows)):
        ws.no_split(row)
        cells = cells + [""] * (len(widths) - len(cells))
        for cell, text in zip(row.cells, cells):
            ws.set_cell_borders(cell)
            if r == 0:
                ws.shade_cell(cell, ws.PAPER2)
            par = cell.paragraphs[0]
            ws.fmt(par, 1, 1, 13)
            if r == 0:
                run = par.add_run(text)
                run.font.size = Pt(9)
                run.bold = True
                ws.set_fonts(run, ws.GOTHIC)
            else:
                ws.add_inlines(par, text, size=9)
    table.rows[0]._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))
    ws.fmt(doc_.add_paragraph(), 0, 1, 5)


def docx_quote(doc_, paras, kind):
    for text in paras:
        par = doc_.add_paragraph()
        ws.fmt(par, 1, 0, 15, indent=3)
        ws.add_inlines(par, text, size=9.5, gothic=True)
        if kind == "check":
            ws.shade_par(par, "FFFDF9", left=ws.CORAL)
        else:
            ws.shade_par(par, ws.PAPER2)
    doc_.paragraphs[-1].paragraph_format.space_after = Pt(4)


def build_docx(doc):
    d = ws.setup_doc(doc["title"], doc["label"])
    head = f"{doc['label']}｜{doc['name']}｜{doc['sub'].split('｜', 1)[-1]}"
    n = len(doc["topics"])
    for k, topic in enumerate(doc["topics"]):
        if k:
            d.add_page_break()
        top = d.add_paragraph()
        ws.fmt(top, 0, 2, 12)
        ws.add_inlines(top, head, size=8, color=ws.GRAY, gothic=True)
        h2 = d.add_paragraph(style="Heading 2")
        ws.fmt(h2, 0, 4, 20, keep_next=True)
        h2.paragraph_format.tab_stops.add_tab_stop(Mm(ws.TEXT_W_MM), WD_TAB_ALIGNMENT.RIGHT)
        run = h2.add_run(topic["title"] + "\t")
        run.font.size = Pt(15)
        chip = h2.add_run(f" トピック {topic['no']} / {n} ")
        chip.font.size = Pt(9)
        shd = OxmlElement("w:shd")
        for key, val in (("w:val", "clear"), ("w:color", "auto"), ("w:fill", ws.ACCENT)):
            shd.set(qn(key), val)
        chip._r.get_or_add_rPr().append(shd)
        ppr = h2._p.get_or_add_pPr()
        bdr = OxmlElement("w:pBdr")
        el = OxmlElement("w:bottom")
        for key, val in (("w:val", "single"), ("w:sz", "8"), ("w:space", "2"), ("w:color", ws.INK)):
            el.set(qn(key), val)
        bdr.append(el)
        ppr.append(bdr)
        for b in topic["blocks"]:
            t = b["type"]
            if t == "h3":
                par = d.add_paragraph(style="Heading 3")
                ws.fmt(par, 6, 2, 16, keep_next=True)
                par.add_run(b["text"])
            elif t == "p":
                text = b["text"]
                if text.startswith(("※", "出典", "参考")):
                    ws.fmt(ws.add_inlines(d.add_paragraph(), text, size=8, color=ws.GRAY, gothic=True), 3, 1, 12)
                else:
                    ws.fmt(ws.add_inlines(d.add_paragraph(), text), 0, 3, 15.5)
            elif t in ("ul", "ol"):
                for item in b["items"]:
                    par = d.add_paragraph(style="List Bullet" if t == "ul" else "List Number")
                    ws.fmt(par, 0, 1, 15)
                    ws.add_inlines(par, item, size=9.5)
            elif t == "quote":
                docx_quote(d, b["paras"], quote_kind(b["paras"]))
            elif t == "table":
                docx_table(d, b["rows"])
    ws.reorder(d.element)
    for sec in d.sections:
        ws.reorder(sec.footer._element)
    return d


# ------------------------------------------------------------
# 検査
# ------------------------------------------------------------
def page_texts(pdf):
    info = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout
    pages = int(re.search(r"Pages:\s+(\d+)", info).group(1))
    out = []
    for p in range(1, pages + 1):
        text = subprocess.run(["pdftotext", "-f", str(p), "-l", str(p), "-layout", str(pdf), "-"],
                              capture_output=True, text=True).stdout
        out.append(text)
    return out


def check_pages(doc, pdf, what):
    """トピックの数とページ数が同じで、各ページがそのトピックで始まることを確かめる。"""
    squeeze = lambda text: re.sub(r"\s", "", text)
    titles = [t["title"] for t in doc["topics"]]
    # 見出し行は「題　トピック k / n」なので、題と番号の組で探す（ページ上部の回の題名と混同しないため）
    marks = {squeeze(f"{t['title']}トピック{t['no']}/"): t["title"] for t in doc["topics"]}
    starts = []  # 各ページの先頭にあるトピック名。なければ前のトピックの続き
    for page in page_texts(pdf):
        head = squeeze(page[:500])
        starts.append(next((title for mark, title in marks.items() if mark in head), None))
    if starts != titles:
        over, last = [], None
        for start in starts:
            if start is None and last and last not in over:
                over.append(last)
            last = start or last
        sys.exit(f"{doc['label']} の{what}: {len(titles)} トピックに対して {len(starts)} ページになりました。"
                 f"あふれているトピック: {over or '不明'}")


def docx_pages(doc, docx_path, work):
    """Word 版を LibreOffice で PDF にして検査する。LuaLaTeX の PDF と名前が同じなので、別のフォルダに出す。"""
    out = work / "libreoffice"
    out.mkdir(exist_ok=True)
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(out), str(docx_path)],
                   capture_output=True, check=True)
    check_pages(doc, out / (docx_path.stem + ".pdf"), "Word 版（LibreOffice で確認）")


def fill_ratio(pdf, pages):
    """各ページの本文の高さが、本文の領域（46行）に占める割合。あふれるまでの余裕を見るための目安。"""
    ratios = []
    for p in range(1, pages + 1):
        bbox = subprocess.run(["pdftotext", "-f", str(p), "-l", str(p), "-bbox", str(pdf), "-"],
                              capture_output=True, text=True).stdout
        ys = [(float(a), float(b)) for a, b in re.findall(r'yMin="([\d.]+)" xMax="[\d.]+" yMax="([\d.]+)"', bbox)]
        body = [y for y in ys if y[1] < 790]  # フッターを除く
        ratios.append((max(y[1] for y in body) - min(y[0] for y in body)) / 736 if body else 0)
    return ratios


def main():
    nums = sys.argv[1:] or NUMS
    for d in (WORD_DIR, PDF_DIR, TEX_DIR):
        d.mkdir(exist_ok=True)
    for num in nums:
        doc = load(num)
        check_against_page(doc)
        tex = build_tex(doc)
        (TEX_DIR / f"note{num}.tex").write_text(tex, encoding="utf-8")  # lualatex で直接組める原稿
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            pdf = work / f"note{num}.pdf"
            ws.compile_tex(tex, f"note{num}", pdf, doc["label"])
            check_pages(doc, pdf, "PDF")
            ratios = fill_ratio(pdf, len(doc["topics"]))
            docx_path = WORD_DIR / f"note{num}.docx"
            build_docx(doc).save(docx_path)
            docx_pages(doc, docx_path, work)
            producer = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout
            if "LuaTeX" not in producer:
                sys.exit(f"{doc['label']}: PDF が LuaLaTeX の出力ではありません。")
            (PDF_DIR / f"note{num}.pdf").write_bytes(pdf.read_bytes())
        print(f"{doc['label']}: tex/note{num}.tex, pdf/note{num}.pdf, word/note{num}.docx（{len(doc['topics'])} ページ、"
              f"ページの使用率 {'・'.join(f'{r:.0%}' for r in ratios)}）")


if __name__ == "__main__":
    main()
