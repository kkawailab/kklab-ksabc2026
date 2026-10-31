#!/usr/bin/env python3
"""markdown/worksheetNN.md を原稿として、Word 版と PDF 版を作る。

  python3 worksheets/build.py            5回分すべて
  python3 worksheets/build.py 06 09      指定した回だけ

Word は python-docx、PDF は LuaLaTeX（jlreq、tcolorbox）で組む。
原稿の Markdown は、次の書き方だけを解釈する。

  # 第N回ワークシート　題名         表題（全角スペースの前が回、後ろが題名）
  ## 見出し                        節。「物語」「つづく」「結末」は物語の囲み、
                                   「この回のねらい」「この回の用語」は色付きの囲みになる
  ### 問1　題名（目安：50〜80字）    問の見出し。（目安：…）は右端の札になる
  **回答：**                       回答欄。大きさは目安の文字数から決まる
  > **書き出し**　…                書き出しやヒントの囲み
  ```text                          Teams に貼り付ける形式の枠
  - 箇条書き、1. 番号、| 表 |、**太字**、[リンク](URL)
  ※で始まる段落                    小さい注記
"""
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from docx import Document
from docx.enum.table import WD_ROW_HEIGHT_RULE, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor

HERE = Path(__file__).resolve().parent
MD_DIR, WORD_DIR, PDF_DIR = HERE / "markdown", HERE / "word", HERE / "pdf"
NUMS = ["06", "07", "08", "09", "10"]

# サイトの配色（assets/css/style.css）に合わせる
INK, INK2, GRAY = "0F1D33", "3D4A63", "6B7280"
PAPER, PAPER2, RULE = "F4F2EC", "E8E4D9", "C9C5B9"
ACCENT, CORAL = "FFC857", "D9593A"
MINCHO, GOTHIC = "游明朝", "游ゴシック"
COURSE = "企業診断ＡＢＣ 2026（河合担当分）"
TEXT_W_MM = 170
STORY_SECTIONS = ("物語", "つづく", "結末")


# ------------------------------------------------------------
# Markdown の解釈
# ------------------------------------------------------------
INLINE = re.compile(r"(\*\*.+?\*\*|\[[^\]]+\]\([^)\s]+\))")


def inlines(text):
    """文字列を (種類, 本文, URL) の並びにする。"""
    out = []
    for part in INLINE.split(text):
        if not part:
            continue
        if part.startswith("**"):
            out.append(("bold", part[2:-2], None))
        elif part.startswith("["):
            m = re.match(r"\[([^\]]+)\]\(([^)\s]+)\)", part)
            out.append(("link", m.group(1), m.group(2)))
        else:
            out.append(("text", part, None))
    return out


def parse(md):
    blocks, lines, i = [], md.split("\n"), 0

    def starts_block(s):
        return (not s.strip() or s.startswith(("#", ">", "- ", "|", "```"))
                or re.match(r"\d+\. ", s))

    while i < len(lines):
        s = lines[i]
        if not s.strip():
            i += 1
        elif s.startswith("```"):
            i += 1
            code = []
            while not lines[i].startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1
            blocks.append({"type": "code", "lines": code})
        elif m := re.match(r"(#{1,3}) (.+)", s):
            blocks.append({"type": f"h{len(m.group(1))}", "text": m.group(2).strip()})
            i += 1
        elif s.startswith(">"):
            paras, cur = [], []
            while i < len(lines) and lines[i].startswith(">"):
                body = lines[i][1:].strip()
                if body:
                    cur.append(body)
                elif cur:
                    paras.append("".join(cur))
                    cur = []
                i += 1
            if cur:
                paras.append("".join(cur))
            blocks.append({"type": "quote", "paras": paras})
        elif s.startswith("- "):
            items = []
            while i < len(lines) and lines[i].startswith("- "):
                items.append(lines[i][2:].strip())
                i += 1
            blocks.append({"type": "ul", "items": items})
        elif re.match(r"\d+\. ", s):
            items = []
            while i < len(lines) and re.match(r"\d+\. ", lines[i]):
                items.append(re.sub(r"^\d+\. ", "", lines[i]).strip())
                i += 1
            blocks.append({"type": "ol", "items": items})
        elif s.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            blocks.append({"type": "table", "rows": rows})
        elif s.strip() == "**回答：**":
            blocks.append({"type": "answer"})
            i += 1
        else:
            para = []
            while i < len(lines) and not starts_block(lines[i]):
                para.append(lines[i].strip())
                i += 1
            blocks.append({"type": "p", "text": "".join(para)})
    return blocks


def split_question(text):
    """「問1　題名（目安：50〜80字）」を (問1　題名, 50〜80字) に分ける。"""
    m = re.match(r"(.+)（目安：(.+)）$", text)
    return (m.group(1), m.group(2)) if m else (text, "")


def limit_chars(limit):
    nums = re.findall(r"\d+", limit)
    return int(nums[-1]) if nums else 50


def answer_lines(limit):
    """回答欄の行数。1行およそ40字とみて、1行の余裕を持たせる。"""
    return max(2, math.ceil(limit_chars(limit) / 40) + 1)


def header_parts(blocks):
    """表題、回、題名、日付の行、使い方の段落を取り出す。"""
    title = next(b["text"] for b in blocks if b["type"] == "h1")
    label, name = title.split("　", 1)
    h1 = next(k for k, b in enumerate(blocks) if b["type"] == "h1")
    sub, lead = blocks[h1 + 1]["text"], blocks[h1 + 2]["text"]
    return title, label, name, sub, lead, blocks[h1 + 3:]


def section_kind(heading):
    if heading in ("この回のねらい", "この回の用語"):
        return "goals"
    if heading.startswith(STORY_SECTIONS):
        return "story"
    if heading.startswith("Teams"):
        return "teams"
    return "plain"


def split_heading(text):
    """「最近の話題　題」を (最近の話題, 題) に分ける。"""
    return tuple(text.split("　", 1)) if "　" in text else (text, "")


# ------------------------------------------------------------
# Word
# ------------------------------------------------------------
def set_fonts(obj, east, latin=None):
    rpr = obj.element.get_or_add_rPr() if hasattr(obj.element, "get_or_add_rPr") else obj._element.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.insert(0, fonts)
    latin = latin or east
    for attr, val in (("w:ascii", latin), ("w:hAnsi", latin), ("w:eastAsia", east), ("w:cs", latin)):
        fonts.set(qn(attr), val)


def shade_par(par, fill, left=None):
    ppr = par._p.get_or_add_pPr()
    if left:
        bdr = OxmlElement("w:pBdr")
        el = OxmlElement("w:left")
        for k, v in (("w:val", "single"), ("w:sz", "24"), ("w:space", "8"), ("w:color", left)):
            el.set(qn(k), v)
        bdr.append(el)
        ppr.append(bdr)
    shd = OxmlElement("w:shd")
    for k, v in (("w:val", "clear"), ("w:color", "auto"), ("w:fill", fill)):
        shd.set(qn(k), v)
    ppr.append(shd)


PPR_ORDER = ("pStyle keepNext keepLines pageBreakBefore framePr widowControl numPr suppressLineNumbers pBdr shd tabs "
             "suppressAutoHyphens kinsoku wordWrap overflowPunct topLinePunct autoSpaceDE autoSpaceDN bidi adjustRightInd "
             "snapToGrid spacing ind contextualSpacing mirrorIndents suppressOverlap jc textDirection textAlignment "
             "textboxTightWrap outlineLvl divId cnfStyle rPr sectPr pPrChange").split()
RPR_ORDER = ("rStyle rFonts b bCs i iCs caps smallCaps strike dstrike outline shadow emboss imprint noProof snapToGrid "
             "vanish webHidden color spacing w kern position sz szCs highlight u effect bdr shd fitText vertAlign rtl cs "
             "em lang eastAsianLayout specVanish oMath").split()
TCPR_ORDER = "cnfStyle tcW gridSpan hMerge vMerge tcBorders shd noWrap tcMar textDirection tcFitText vAlign hideMark".split()


def reorder(root):
    """後から足した要素を、スキーマの定める順に並べ直す。"""
    for tag, order in (("w:pPr", PPR_ORDER), ("w:rPr", RPR_ORDER), ("w:tcPr", TCPR_ORDER)):
        rank = {qn(f"w:{name}"): k for k, name in enumerate(order)}
        for el in root.iter(qn(tag)):
            kids = sorted(el, key=lambda c: rank.get(c.tag, len(rank)))
            for kid in list(el):
                el.remove(kid)
            el.extend(kids)


def band_par(par):
    """表題の帯。余白ぶんの枠を地の色で引く。"""
    ppr = par._p.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr")
    for edge in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{edge}")
        for k, v in (("w:val", "single"), ("w:sz", "4"), ("w:space", "4"), ("w:color", INK)):
            el.set(qn(k), v)
        bdr.append(el)
    ppr.append(bdr)
    shade_par(par, INK)
    par.paragraph_format.left_indent = Mm(2)
    par.paragraph_format.right_indent = Mm(2)


def add_link(par, text, url, size=None):
    rid = par.part.relate_to(
        url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
        is_external=True)
    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), rid)
    run = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), "1F4E9E")
    under = OxmlElement("w:u")
    under.set(qn("w:val"), "single")
    rpr.extend([color, under])
    if size:
        for tag in ("w:sz", "w:szCs"):
            sz = OxmlElement(tag)
            sz.set(qn("w:val"), str(int(size * 2)))
            rpr.append(sz)
    run.append(rpr)
    t = OxmlElement("w:t")
    t.text = text
    run.append(t)
    link.append(run)
    par._p.append(link)


def add_inlines(par, text, size=None, color=None, gothic=False):
    for kind, body, url in inlines(text):
        if kind == "link":
            add_link(par, body, url, size)
            continue
        run = par.add_run(body)
        if kind == "bold":
            run.bold = True
            set_fonts(run, GOTHIC)
        elif gothic:
            set_fonts(run, GOTHIC)
        if size:
            run.font.size = Pt(size)
        if color:
            run.font.color.rgb = RGBColor.from_string(color)
    return par


def fmt(par, before=0, after=0, line=None, keep_next=False, indent=None):
    pf = par.paragraph_format
    pf.space_before, pf.space_after = Pt(before), Pt(after)
    if line:
        pf.line_spacing = Pt(line)
    if keep_next:
        pf.keep_with_next = True
    if indent is not None:
        pf.left_indent = Mm(indent)
    return par


def add_page_field(par, size):
    run = par.add_run()
    run.font.size = Pt(size)
    run.font.color.rgb = RGBColor.from_string(GRAY)
    for typ, instr in (("begin", None), (None, "PAGE"), ("end", None)):
        if typ:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), typ)
        else:
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = instr
        run._r.append(el)


def set_cell_borders(cell, color=RULE, sz="6"):
    tcpr = cell._tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{edge}")
        for k, v in (("w:val", "single"), ("w:sz", sz), ("w:space", "0"), ("w:color", color)):
            el.set(qn(k), v)
        borders.append(el)
    tcpr.append(borders)


def shade_cell(cell, fill):
    shd = OxmlElement("w:shd")
    for k, v in (("w:val", "clear"), ("w:color", "auto"), ("w:fill", fill)):
        shd.set(qn(k), v)
    cell._tc.get_or_add_tcPr().append(shd)


def make_table(doc, rows, widths_mm):
    table = doc.add_table(rows=rows, cols=len(widths_mm))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    tblpr = table._tbl.tblPr
    tblw = tblpr.find(qn("w:tblW"))
    if tblw is None:
        tblw = OxmlElement("w:tblW")
        tblpr.append(tblw)
    tblw.set(qn("w:type"), "dxa")
    tblw.set(qn("w:w"), str(round(sum(widths_mm) * 56.7)))
    for gc, w in zip(table._tbl.tblGrid.findall(qn("w:gridCol")), widths_mm):
        gc.set(qn("w:w"), str(round(w * 56.7)))
    for row in table.rows:
        for cell, w in zip(row.cells, widths_mm):
            cell.width = Mm(w)
    return table


def no_split(row):
    trpr = row._tr.get_or_add_trPr()
    trpr.append(OxmlElement("w:cantSplit"))


def setup_doc(title, label):
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Mm(210), Mm(297)
    sec.left_margin = sec.right_margin = Mm(20)
    sec.top_margin, sec.bottom_margin = Mm(18), Mm(18)
    sec.footer_distance = Mm(9)

    normal = doc.styles["Normal"]
    normal.font.size = Pt(10)
    normal.font.color.rgb = RGBColor.from_string(INK)
    set_fonts(normal, MINCHO, "Century")
    normal.paragraph_format.line_spacing = Pt(16)
    normal.paragraph_format.space_after = Pt(4)
    for name, size, color in (("Heading 1", 17, "FFFFFF"), ("Heading 2", 12.5, INK), ("Heading 3", 11, INK)):
        st = doc.styles[name]
        st.font.size, st.font.bold = Pt(size), True
        st.font.italic = False
        st.font.color.rgb = RGBColor.from_string(color)
        set_fonts(st, GOTHIC, "Arial")
    for name in ("List Bullet", "List Number"):
        doc.styles[name].font.size = Pt(10)
        doc.styles[name].paragraph_format.line_spacing = Pt(16)

    # 日本語の文書として扱い、互換モードで開かないようにする
    rpr_default = doc.styles.element.find(qn("w:docDefaults")).find(qn("w:rPrDefault")).find(qn("w:rPr"))
    lang = rpr_default.find(qn("w:lang"))
    if lang is None:
        lang = OxmlElement("w:lang")
        rpr_default.append(lang)
    lang.set(qn("w:val"), "ja-JP")
    lang.set(qn("w:eastAsia"), "ja-JP")
    settings = doc.settings.element
    compat = settings.find(qn("w:compat"))
    if compat is None:
        compat = OxmlElement("w:compat")
        settings.append(compat)
    setting = OxmlElement("w:compatSetting")
    for k, v in (("w:name", "compatibilityMode"), ("w:uri", "http://schemas.microsoft.com/office/word"), ("w:val", "15")):
        setting.set(qn(k), v)
    compat.append(setting)

    props = doc.core_properties
    props.title, props.author, props.subject = title, "河合 勝彦", COURSE
    props.language = "ja-JP"

    foot = sec.footer.paragraphs[0]
    foot.paragraph_format.tab_stops.add_tab_stop(Mm(TEXT_W_MM), WD_TAB_ALIGNMENT.RIGHT)
    run = foot.add_run(f"{COURSE}　{label}\t")
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor.from_string(GRAY)
    set_fonts(run, GOTHIC)
    add_page_field(foot, 8)
    return doc


def story_par(doc, text):
    small = text.startswith("※")
    par = doc.add_paragraph()
    fmt(par, 0, 2, 13 if small else 16)
    add_inlines(par, text, size=8.5 if small else None, color=GRAY if small else None)
    shade_par(par, PAPER, left=ACCENT)
    return par


def write_quote(doc, paras):
    for text in paras:
        par = doc.add_paragraph()
        fmt(par, 0, 0, 15.5, keep_next=True, indent=3)
        add_inlines(par, text, size=9.5, gothic=True)
        shade_par(par, PAPER2)
    doc.paragraphs[-1].paragraph_format.space_after = Pt(4)


def write_answer(doc, limit):
    lines = answer_lines(limit)
    table = make_table(doc, 1, [TEXT_W_MM])
    row = table.rows[0]
    row.height = Mm(lines * 6 + 5)
    row.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST
    no_split(row)
    cell = row.cells[0]
    set_cell_borders(cell)
    par = cell.paragraphs[0]
    fmt(par, 2, 0, 13)
    run = par.add_run("回答欄")
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor.from_string(GRAY)
    set_fonts(run, GOTHIC)
    typing = cell.add_paragraph()
    fmt(typing, 0, 0, 16)
    fmt(doc.add_paragraph(), 0, 2, 6)


def write_limit_table(doc, rows):
    table = make_table(doc, len(rows), [20, 110, 40])
    for r, (row, cells) in enumerate(zip(table.rows, rows)):
        no_split(row)
        total = r == len(rows) - 1
        for c, (cell, text) in enumerate(zip(row.cells, cells)):
            set_cell_borders(cell)
            if r == 0 or total:
                shade_cell(cell, PAPER2)
            par = cell.paragraphs[0]
            fmt(par, 1, 1, 14)
            run = par.add_run(text)
            run.font.size = Pt(9.5)
            set_fonts(run, GOTHIC)
            run.bold = r == 0 or total
    hdr = table.rows[0]._tr.get_or_add_trPr()
    hdr.append(OxmlElement("w:tblHeader"))
    fmt(doc.add_paragraph(), 0, 2, 6)


def build_docx(num, blocks):
    title, label, name, sub, lead, body = header_parts(blocks)
    doc = setup_doc(title, label)

    band = doc.add_paragraph()
    fmt(band, 0, 0, 15)
    run = band.add_run(f"{label}｜{sub}")
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor.from_string("FFFFFF")
    set_fonts(run, GOTHIC)
    band_par(band)
    h1 = doc.add_paragraph(style="Heading 1")
    h1.add_run(name)
    fmt(h1, 0, 8, 26)
    band_par(h1)
    fmt(add_inlines(doc.add_paragraph(), lead, size=9.5, color=INK2), 0, 4, 15)

    kind, in_question = "plain", False
    for b in body:
        t = b["type"]
        if t == "h2":
            in_question = False
            head, sub_head = split_heading(b["text"])
            kind = section_kind(head)
            par = doc.add_paragraph(style="Heading 2")
            fmt(par, 10, 4, 18, keep_next=True)
            run = par.add_run(head)
            if sub_head:
                run2 = par.add_run("　" + sub_head)
                run2.font.color.rgb = RGBColor.from_string(CORAL)
            ppr = par._p.get_or_add_pPr()
            bdr = OxmlElement("w:pBdr")
            el = OxmlElement("w:bottom")
            for k, v in (("w:val", "single"), ("w:sz", "8"), ("w:space", "2"), ("w:color", INK)):
                el.set(qn(k), v)
            bdr.append(el)
            ppr.append(bdr)
        elif t == "h3":
            head, limit = split_question(b["text"])
            current_limit, in_question = limit, True
            par = doc.add_paragraph(style="Heading 3")
            fmt(par, 8, 3, 17, keep_next=True)
            par.paragraph_format.tab_stops.add_tab_stop(Mm(TEXT_W_MM), WD_TAB_ALIGNMENT.RIGHT)
            par.add_run(head + "\t")
            chip = par.add_run(f" 目安：{limit} ")
            chip.font.size = Pt(9.5)
            shd = OxmlElement("w:shd")
            for k, v in (("w:val", "clear"), ("w:color", "auto"), ("w:fill", ACCENT)):
                shd.set(qn(k), v)
            chip._r.get_or_add_rPr().append(shd)
        elif t == "p":
            text = b["text"]
            if kind == "story":
                story_par(doc, text)
            elif text.startswith("出典"):
                fmt(add_inlines(doc.add_paragraph(), text, size=8.5, color=GRAY, gothic=True), 4, 1, 13, keep_next=True)
            else:
                fmt(add_inlines(doc.add_paragraph(), text), 0, 3, 16, keep_next=in_question)
        elif t == "ul":
            sources = all(i.startswith("[") for i in b["items"])
            for item in b["items"]:
                par = doc.add_paragraph(style="List Bullet")
                size = 8.5 if sources else (9.5 if kind == "teams" else None)
                last = kind == "teams" and item == b["items"][-1]
                fmt(par, 0, 1, 13 if sources else 15.5, keep_next=in_question or (kind == "teams" and not last))
                add_inlines(par, item, size=size)
        elif t == "ol":
            for item in b["items"]:
                par = doc.add_paragraph(style="List Number")
                fmt(par, 0, 1, 16, keep_next=True)
                add_inlines(par, item, size=9.5)
        elif t == "quote":
            write_quote(doc, b["paras"])
        elif t == "answer":
            write_answer(doc, current_limit)
            in_question = False
        elif t == "table":
            write_limit_table(doc, b["rows"])
        elif t == "code":
            for k, line in enumerate(b["lines"]):
                par = doc.add_paragraph()
                fmt(par, 4 if k == 0 else 0, 0, 16, keep_next=True, indent=3)
                run = par.add_run(line)
                set_fonts(run, GOTHIC)
                shade_par(par, PAPER2)
            fmt(doc.add_paragraph(), 0, 2, 6, keep_next=True)

    reorder(doc.element)
    for sec in doc.sections:
        reorder(sec.footer._element)
    zoom = doc.settings.element.find(qn("w:zoom"))
    if zoom is not None:
        zoom.set(qn("w:percent"), "100")
    return doc


# ------------------------------------------------------------
# PDF（LuaLaTeX）
# ------------------------------------------------------------
TEX_PREAMBLE = r"""
\documentclass[paper=a4paper,fontsize=10pt,line_length=170mm,number_of_lines=46,baselineskip=1.6zw]{jlreq}
\usepackage[table]{xcolor}
\usepackage[most]{tcolorbox}
\usepackage{enumitem}
\usepackage{needspace}
\usepackage{array}
\usepackage{fancyhdr}
\usepackage[colorlinks=true,linkcolor=linkblue,urlcolor=linkblue]{hyperref}
\ltjsetparameter{jacharrange={-1,+2,+3,+4,-5,+6,+7,+8}}
\definecolor{ink}{HTML}{%(INK)s}
\definecolor{inktwo}{HTML}{%(INK2)s}
\definecolor{grayt}{HTML}{%(GRAY)s}
\definecolor{paper}{HTML}{%(PAPER)s}
\definecolor{papertwo}{HTML}{%(PAPER2)s}
\definecolor{rulec}{HTML}{%(RULE)s}
\definecolor{accent}{HTML}{%(ACCENT)s}
\definecolor{coral}{HTML}{%(CORAL)s}
\definecolor{linkblue}{HTML}{1F4E9E}
\setlength{\parindent}{0pt}
\setlength{\parskip}{0pt}
\setlist{nosep,leftmargin=1.5em}
\pagestyle{fancy}\fancyhf{}\renewcommand{\headrulewidth}{0pt}
\fancyfoot[L]{\sffamily\scriptsize\color{grayt}%(COURSE)s　\wslabel}
\fancyfoot[R]{\sffamily\scriptsize\color{grayt}\thepage}
\newcommand\sectionhead[2]{\par\needspace{24mm}\vspace{3mm}%%
  {\sffamily\bfseries\large #1\if\relax\detokenize{#2}\relax\else\textcolor{coral}{　#2}\fi}\par
  \vspace{0.8mm}{\color{ink}\hrule height 0.5pt}\vspace{1.5mm}}
\newcommand\question[2]{\par\needspace{34mm}\vspace{3mm}%%
  {\sffamily\bfseries #1}\hfill\colorbox{accent}{\sffamily\footnotesize\bfseries 目安：#2}\par\vspace{1mm}}
\newtcolorbox{goalbox}{enhanced,colback=paper,colframe=paper,boxrule=0pt,arc=1mm,
  left=3mm,right=3mm,top=1.5mm,bottom=1.5mm,before skip=1mm,after skip=1mm,fontupper=\small}
\newtcolorbox{storybox}{enhanced,breakable,colback=paper,colframe=paper,boxrule=0pt,arc=0mm,
  borderline west={1.1mm}{0pt}{accent},left=3.5mm,right=3mm,top=2mm,bottom=2mm,
  before skip=1mm,after skip=1.5mm,parbox=false,before upper={\setlength{\parskip}{1.2mm}}}
\newtcolorbox{closingbox}{enhanced,colback=paper,colframe=paper,boxrule=0pt,arc=0mm,
  borderline west={1.1mm}{0pt}{accent},left=3.5mm,right=3mm,top=2mm,bottom=2mm,
  before skip=1mm,after skip=1.5mm,parbox=false,before upper={\setlength{\parskip}{1.2mm}}}
\newtcolorbox{hintbox}{enhanced,colback=papertwo,colframe=papertwo,boxrule=0pt,arc=1mm,
  left=2.5mm,right=2.5mm,top=1.2mm,bottom=1.2mm,before skip=1.2mm,after skip=1.5mm,
  parbox=false,before upper={\setlength{\parskip}{1mm}},fontupper=\footnotesize}
\newtcolorbox{codebox}{enhanced,colback=white,colframe=ink,boxrule=0.5pt,arc=1mm,
  left=3mm,right=3mm,top=1.5mm,bottom=1.5mm,before skip=2mm,after skip=2mm,fontupper=\sffamily\small}
\newcommand\answerlines[1]{%%
  \begin{tcolorbox}[enhanced,colback=white,colframe=rulec,boxrule=0.5pt,arc=1mm,
    left=2mm,right=2mm,top=1mm,bottom=1.5mm,before skip=1mm,after skip=1.5mm]
  {\sffamily\scriptsize\color{grayt}回答（下書き）}\par
  \foreach\n in {1,...,#1}{\nointerlineskip\noindent{\color{rulec}\vbox to 6.2mm{\vfil\hrule width\linewidth}}\par}
  \end{tcolorbox}}
"""


def tex_escape(s):
    table = {"\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "%": r"\%", "&": r"\&", "#": r"\#",
             "_": r"\_", "$": r"\$", "^": r"\^{}", "~": r"\~{}"}
    return "".join(table.get(c, c) for c in s)


def tex_url(url):
    return re.sub(r"([%#&_~])", r"\\\1", url)


def tex_inline(text):
    out = []
    for kind, body, url in inlines(text):
        if kind == "bold":
            out.append(r"{\sffamily\bfseries " + tex_escape(body) + "}")
        elif kind == "link":
            out.append(r"\href{" + tex_url(url) + "}{" + tex_escape(body) + "}")
        else:
            out.append(tex_escape(body))
    return "".join(out)


def tex_preamble():
    colors = dict(INK=INK, INK2=INK2, GRAY=GRAY, PAPER=PAPER, PAPER2=PAPER2, RULE=RULE,
                  ACCENT=ACCENT, CORAL=CORAL, COURSE=COURSE)
    return TEX_PREAMBLE % colors


def tex_session(blocks, on_answer=None):
    """1回分の本文を TeX の行の並びで返す。

    on_answer(問の見出し, 目安) を渡すと、回答欄の代わりにその戻り値を置く（教員用）。
    """
    title, label, name, sub, lead, body = header_parts(blocks)
    out = []
    out.append(
        r"\begin{tcolorbox}[enhanced,colback=ink,colframe=ink,arc=1.5mm,boxrule=0pt,left=4mm,right=4mm,top=2.5mm,bottom=2.5mm,"
        r"before skip=0mm,after skip=2mm,fontupper=\color{white}\sffamily]"
        + r"{\footnotesize " + tex_escape(f"{label}｜{sub}") + r"}\par\vspace{0.8mm}{\LARGE\bfseries " + tex_escape(name) + "}"
        + r"\end{tcolorbox}")
    out.append(r"{\small\color{inktwo}" + tex_inline(lead) + r"}\par")

    kind, story_env, limit, question = "plain", None, "", ""

    def close_story():
        nonlocal story_env
        if story_env:
            out.append(r"\end{" + story_env + "}")
            story_env = None

    for b in body:
        t = b["type"]
        if t == "h2":
            close_story()
            head, sub_head = split_heading(b["text"])
            kind = section_kind(head)
            if kind == "teams":
                out.append(r"\needspace{72mm}")
            elif kind == "story" and not head.startswith("物語"):
                out.append(r"\needspace{40mm}")
            out.append(r"\sectionhead{" + tex_escape(head) + "}{" + tex_escape(sub_head) + "}")
            if kind == "story":
                story_env = "storybox" if head.startswith("物語") else "closingbox"
                out.append(r"\begin{" + story_env + "}")
        elif t == "h3":
            question, limit = split_question(b["text"])
            out.append(r"\question{" + tex_escape(question) + "}{" + tex_escape(limit) + "}")
        elif t == "p":
            text = b["text"]
            if text.startswith("※"):
                out.append(r"{\footnotesize\color{grayt}" + tex_inline(text) + r"\par}")
            elif text.startswith("出典"):
                out.append(r"\vspace{1mm}{\sffamily\footnotesize\color{grayt}" + tex_inline(text) + r"\par}")
            elif kind == "story":
                out.append(tex_inline(text) + r"\par")
            else:
                out.append(tex_inline(text) + r"\par\vspace{1mm}")
        elif t == "ul":
            sources = all(i.startswith("[") for i in b["items"])
            style = r"\footnotesize" if sources or kind == "teams" else ""
            wrap = kind == "goals"
            if wrap:
                out.append(r"\begin{goalbox}")
            out.append(r"{" + style + r"\begin{itemize}[leftmargin=1.2em,itemsep=0.5mm]")
            out.extend(r"\item " + tex_inline(i) for i in b["items"])
            out.append(r"\end{itemize}}")
            if wrap:
                out.append(r"\end{goalbox}")
            else:
                out.append(r"\vspace{1mm}")
        elif t == "ol":
            out.append(r"{\footnotesize\begin{enumerate}[leftmargin=1.5em,itemsep=0.5mm]")
            out.extend(r"\item " + tex_inline(i) for i in b["items"])
            out.append(r"\end{enumerate}}")
        elif t == "quote":
            out.append(r"\begin{hintbox}")
            out.extend(tex_inline(p) + r"\par" for p in b["paras"])
            out.append(r"\end{hintbox}")
        elif t == "answer":
            out.append(on_answer(question, limit) if on_answer else r"\answerlines{" + str(answer_lines(limit)) + "}")
        elif t == "table":
            rows = b["rows"]
            out.append(r"\begin{center}\small\renewcommand{\arraystretch}{1.15}")
            out.append(r"\begin{tabular}{|p{18mm}|p{105mm}|p{35mm}|}\arrayrulecolor{rulec}\hline")
            for r, cells in enumerate(rows):
                bold = r == 0 or r == len(rows) - 1
                prefix = r"\rowcolor{papertwo}" if bold else ""
                cols = [(r"\sffamily\bfseries " if bold else "") + tex_escape(c) for c in cells]
                out.append(prefix + " & ".join(cols) + r"\\\hline")
            out.append(r"\end{tabular}\end{center}")
        elif t == "code":
            out.append(r"\begin{codebox}")
            out.append(r"\\".join(tex_escape(l) for l in b["lines"]))
            out.append(r"\end{codebox}")
    close_story()
    return out


def build_tex(blocks):
    title, label, *_ = header_parts(blocks)
    out = [tex_preamble()]
    out.append(r"\newcommand*\wslabel{" + tex_escape(label) + "}")
    out.append(r"\hypersetup{pdftitle={" + tex_escape(title) + r"},pdfauthor={河合 勝彦},pdfsubject={" + COURSE + "}}")
    out.append(r"\begin{document}")
    out.extend(tex_session(blocks))
    out.append(r"\end{document}")
    return "\n".join(out)


def compile_tex(tex, job, dest, who, passes=2):
    """tex を LuaLaTeX で組み、dest に PDF を置く。who はメッセージに出す名前。"""
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / f"{job}.tex").write_text(tex, encoding="utf-8")
        for _ in range(passes):
            run = subprocess.run(
                ["lualatex", "-interaction=nonstopmode", "-halt-on-error", f"{job}.tex"],
                cwd=tmp, capture_output=True, text=True, errors="replace")
            if run.returncode:
                sys.exit(f"{who}の PDF を組めませんでした:\n" + run.stdout[-2500:])
        log = (Path(tmp) / f"{job}.log").read_text(encoding="utf-8", errors="replace")
        missing = sorted(set(re.findall(r"Missing character: There is no (.)", log)))
        if missing:
            print(f"  警告: {who} PDF に出ない文字 {missing}")
        shutil.copy(Path(tmp) / f"{job}.pdf", dest)


def build_pdf(num, blocks):
    job = f"worksheet{num}"
    compile_tex(build_tex(blocks), job, PDF_DIR / f"{job}.pdf", f"第{num}回")


def main():
    nums = sys.argv[1:] or NUMS
    WORD_DIR.mkdir(exist_ok=True)
    PDF_DIR.mkdir(exist_ok=True)
    for num in nums:
        blocks = parse((MD_DIR / f"worksheet{num}.md").read_text(encoding="utf-8"))
        build_docx(num, blocks).save(WORD_DIR / f"worksheet{num}.docx")
        build_pdf(num, blocks)
        print(f"第{int(num)}回: word/worksheet{num}.docx, pdf/worksheet{num}.pdf")


if __name__ == "__main__":
    main()
