#!/usr/bin/env python3
"""教員用ワークシート（模範解答入り、全5回を1冊にまとめた PDF）を作る。

  python3 worksheets/build_teacher.py

本文は markdown/worksheetNN.md、模範解答は teacher/answers.md から取り、
学生用の回答欄を模範解答に置き換えて teacher/worksheets_teacher.pdf に組む。

teacher/ は Git の管理外（.gitignore）。このリポジトリは公開で、main に push すると
ルートがそのままサイトになるため、模範解答と PDF をコミットしてはいけない。
"""
import re
import sys
from pathlib import Path

import build
from build import COURSE, MD_DIR, NUMS, header_parts, parse, tex_escape, tex_inline, tex_preamble, tex_session

TEACHER_DIR = Path(__file__).resolve().parent / "teacher"
ANSWERS = TEACHER_DIR / "answers.md"
OUTPUT = TEACHER_DIR / "worksheets_teacher.pdf"
DOC_TITLE = "ワークシート 教員用（模範解答入り）"
FACT_CHECKED = "2026年10月31日"

TEACHER_PREAMBLE = r"""
\definecolor{answerbg}{HTML}{FCF0EB}
\definecolor{coraldark}{HTML}{A93E25}
\hypersetup{bookmarksopen=true,bookmarksopenlevel=0,pdfdisplaydoctitle=true}
\fancyhead[R]{\sffamily\scriptsize\bfseries\color{coraldark}教員用・模範解答入り｜学生に配布・共有しないこと}
\newtcolorbox{modelanswer}{enhanced,colback=answerbg,colframe=coral,boxrule=0.6pt,arc=1mm,
  left=2.5mm,right=2.5mm,top=1.2mm,bottom=1.5mm,before skip=1mm,after skip=1.5mm,parbox=false,
  before upper={\setlength{\parskip}{0.8mm}},fontlower=\footnotesize\color{inktwo},
  segmentation style={draw=coral,dashed,line width=0.4pt},middle=1.2mm}
\newcommand\answerlabel[2]{{\sffamily\scriptsize\bfseries\color{coraldark}#1}\hfill{\sffamily\scriptsize\color{grayt}#2}\par}
\newcommand\memolabel{{\sffamily\bfseries\color{coraldark}教員メモ}\quad}
"""


def parse_answers(text):
    """answers.md を {"06": {"問1": {"answer", "links", "memo"}}} にする。"""
    data, num, cur = {}, None, None
    for line in text.split("\n"):
        if m := re.fullmatch(r"## 第(\d+)回", line):
            num, cur = f"{int(m.group(1)):02d}", None
            data[num] = {}
        elif m := re.fullmatch(r"### (問\d+)", line):
            cur = {"answer": "", "links": [], "memo": ""}
            data[num][m.group(1)] = cur
        elif cur is not None and line.startswith("回答："):
            cur["answer"] = line[3:].strip()
        elif cur is not None and line.startswith("リンク："):
            cur["links"].append(line[4:].strip())
        elif cur is not None and line.startswith("メモ："):
            cur["memo"] = line[3:].strip()
    return data


def count_chars(text):
    """Word の「スペースを含めない文字数」と同じ数え方にする。"""
    return len(re.sub(r"\s", "", text))


def within_limit(n, limit):
    """「50〜80字」は範囲どおり、「100字程度」は±15%まで認める。

    「30字程度」までの問は回答の形が決まった穴埋めで、短くなるのは正しいので上限だけ見る。
    """
    nums = [int(x) for x in re.findall(r"\d+", limit)]
    if "〜" in limit:
        return nums[0] <= n <= nums[1]
    if nums[0] <= 30:
        return n <= nums[0] * 1.3
    return nums[0] * 0.85 <= n <= nums[0] * 1.15


def check_answers(answers, sessions):
    """問の過不足と字数を確かめる。問題があれば止める。"""
    errors = []
    for num, blocks in sessions.items():
        questions = {}
        for b in blocks:
            if b["type"] == "h3":
                head, limit = build.split_question(b["text"])
                questions[head.split("　")[0]] = limit
        have = answers.get(num, {})
        for q in sorted(questions.keys() - have.keys()):
            errors.append(f"第{int(num)}回 {q}: 模範解答がありません")
        for q in sorted(have.keys() - questions.keys()):
            errors.append(f"第{int(num)}回 {q}: ワークシートにない問です")
        for q, limit in questions.items():
            if q not in have:
                continue
            n = count_chars(have[q]["answer"])
            if not have[q]["memo"]:
                errors.append(f"第{int(num)}回 {q}: メモがありません")
            if not within_limit(n, limit):
                errors.append(f"第{int(num)}回 {q}: {n}字（目安 {limit}）")
    if errors:
        sys.exit("模範解答を確認してください:\n  " + "\n  ".join(errors))


def answer_tex(num, label, question, limit, entry):
    """回答欄の代わりに置く模範解答の囲み。"""
    key = question.split("　")[0]
    kind = "模範解答" if key == "問1" else "模範解答（例）"
    n = count_chars(entry["answer"])
    out = [rf"\pdfbookmark[1]{{{tex_escape(key)}}}{{s{num}{key}}}",
           r"\begin{modelanswer}",
           rf"\answerlabel{{{kind}}}{{{n}字／目安 {tex_escape(limit)}}}",
           tex_inline(entry["answer"]) + r"\par"]
    out.extend(r"{\footnotesize リンク：" + tex_inline(link) + r"\par}" for link in entry["links"])
    out.append(r"\tcblower")
    out.append(r"\memolabel " + tex_inline(entry["memo"]))
    out.append(r"\end{modelanswer}")
    return "\n".join(out)


def cover_tex(sessions):
    rows = []
    for num, blocks in sessions.items():
        _, label, name, sub, *_ = header_parts(blocks)
        date = sub.split("｜")[-1]
        date = re.sub(r"^2026年", "", re.sub(r"2限.*$", "", date))
        rows.append(rf"\hyperref[s{num}]{{第{int(num)}回}} & {tex_escape(date)} & {tex_escape(name)} & \pageref{{s{num}}}\\\hline")
    return "\n".join([
        r"\begin{tcolorbox}[enhanced,colback=ink,colframe=ink,arc=1.5mm,boxrule=0pt,left=5mm,right=5mm,top=5mm,bottom=5mm,"
        r"before skip=0mm,after skip=4mm,fontupper=\color{white}\sffamily]",
        r"{\small " + COURSE + r"｜第6〜10回}\par\vspace{1.5mm}{\LARGE\bfseries " + DOC_TITLE + "}",
        r"\end{tcolorbox}",
        r"\begin{tcolorbox}[enhanced,colback=answerbg,colframe=coral,boxrule=0.8pt,arc=1mm,left=3.5mm,right=3.5mm,"
        r"top=2mm,bottom=2mm,before skip=0mm,after skip=5mm,parbox=false]",
        r"{\sffamily\bfseries\color{coraldark}学生に配布・共有しないでください。}"
        r"Teams や公開サイトには載せません。この PDF と原稿は、公開リポジトリに入らないよう Git の管理外に置いています。",
        r"\end{tcolorbox}",
        r"\sectionhead{目次}{}",
        r"\begin{center}\small\renewcommand{\arraystretch}{1.3}",
        r"\begin{tabular}{|p{13mm}|p{32mm}|p{102mm}|r|}\arrayrulecolor{rulec}\hline",
        r"\rowcolor{papertwo}\sffamily\bfseries 回 & \sffamily\bfseries 日程 & \sffamily\bfseries テーマ & \sffamily\bfseries 頁\\\hline",
        *rows,
        r"\end{tabular}\end{center}",
        r"\sectionhead{この版の読み方}{}",
        r"\begin{itemize}[leftmargin=1.2em,itemsep=1mm]",
        r"\item 本文は学生用ワークシートと同じです。回答欄だけを模範解答に置き換えています。",
        r"\item 問1は答えが決まる問なので「模範解答」、問2以降は書き方や題材で答えが変わるので「模範解答（例）」としています。",
        r"\item 囲みの右上の字数は、スペースを除いて数えた値です。問2以降は各問の目安に収めています。問1は回答の形どおりに書いたもので、目安より短い場合があります。",
        r"\item 教員メモは、回答を読むときの着眼点の案です。Teams 投稿は参加度として評価するので、例との一致を求めるものではありません。",
        rf"\item 第6回・第7回・第9回の問3に挙げた企業やサービスの事実は、{FACT_CHECKED}に各リンク先で確認しました。"
        r"数字や投稿は変わることがあるので、教室で示すときは確かめ直してください。",
        r"\item 第10回の問3は、説明のために想定した例です。",
        r"\end{itemize}",
    ])


def build_teacher_tex(answers, sessions):
    out = [tex_preamble(), TEACHER_PREAMBLE]
    out.append(r"\newcommand*\wslabel{教員用}")
    out.append(r"\hypersetup{pdftitle={" + COURSE + "　" + DOC_TITLE + r"},pdfauthor={河合 勝彦},pdfsubject={" + COURSE + "}}")
    out.append(r"\begin{document}")
    out.append(r"\pdfbookmark[0]{表紙と目次}{cover}")
    out.append(cover_tex(sessions))
    for num, blocks in sessions.items():
        _, label, name, *_ = header_parts(blocks)
        out.append(r"\clearpage")
        out.append(r"\renewcommand*\wslabel{" + tex_escape(label) + "}")
        out.append(rf"\pdfbookmark[0]{{第{int(num)}回　{tex_escape(name)}}}{{s{num}}}\label{{s{num}}}")

        def on_answer(question, limit, num=num, label=label):
            return answer_tex(num, label, question, limit, answers[num][question.split("　")[0]])

        out.extend(tex_session(blocks, on_answer))
    out.append(r"\end{document}")
    return "\n".join(out)


def main():
    if not ANSWERS.exists():
        sys.exit(f"{ANSWERS} がありません。模範解答の原稿は Git の管理外なので、この端末に置いてください。")
    answers = parse_answers(ANSWERS.read_text(encoding="utf-8"))
    sessions = {n: parse((MD_DIR / f"worksheet{n}.md").read_text(encoding="utf-8")) for n in NUMS}
    check_answers(answers, sessions)
    build.compile_tex(build_teacher_tex(answers, sessions), "worksheets_teacher", OUTPUT, "教員用", passes=3)
    print(f"{OUTPUT.relative_to(Path.cwd()) if OUTPUT.is_relative_to(Path.cwd()) else OUTPUT}")


if __name__ == "__main__":
    main()
