# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Lecture site for 企業診断ＡＢＣ 2026 (Nagoya City University, 後期, 月曜2限). The course is shared by three instructors; this site covers **only Kawai's sessions (第6〜10回)**. Do not add content for the other instructors' sessions (第1〜5回 坂和, 第11〜15回 高橋) beyond the course-structure overview on the top page.

Plain static HTML/CSS/JS — no build system, no package manager, no tests, no framework. All site content is in Japanese.

Deployment: GitHub Actions (`.github/workflows/pages.yml`) publishes the repo root to GitHub Pages on every push to `main`. Public URL: https://kklab.mobi/kklab-ksabc2026/ — treat pushes to `main` as production deploys.

## Local preview

```bash
python3 -m http.server 8000
```

## Layout

- `index.html` — top page. Sections: `#overview`, `#news`, `#schedule`, `#materials`, `#guide`, `#contact`.
- `lectures/index.html` — lecture list; `lectures/lecture06.html`…`lecture10.html` — one page per session. Sub-pages reference root assets with `../`.
- `attendance/index.html` — attendance-quiz list; `attendance/attendance06.html`…`attendance10.html` — one AI-basics quiz (5 four-choice questions) per session. In each quiz the first `.choice` of every question is the correct answer (`value="a"`); `assets/js/attendance.js` shuffles choices, checks answers, fetches server time (timeapi.io, fallback worldtimeapi.org) and computes the SHA-256 confirmation code. Do not change the code computation or time format, or previously issued codes can no longer be verified.
- `survey/index.html` — lecture-survey list; `survey/survey06.html`…`survey10.html` — one anonymous 5-question survey per session (questions designed to surface biases/misconceptions tied to that session's content); `survey/results.html` — aggregated results with per-session tabs, auto-refresh, and an instructor panel (reveal/hide, open/close, CSV, reset). Questions live only in `assets/js/survey-data.js` (`window.KSABC_SURVEY`, with `apiBase`); both the survey pages and the results page render from it, so edit questions there, never in the HTML. `assets/js/survey.js` holds `initSurveyPage` / `initResultsPage`. Responses are stored via the API in `api/` (Cloudflare Worker + D1 `kklab-ksabc2026-survey`, deployed with `npx wrangler deploy --config api/wrangler.jsonc`; admin key is the Worker secret `SURVEY_ADMIN_KEY`; `api/.dev.vars` is local-only and gitignored). The survey is separate from the attendance quiz and is not graded.
- `worksheets/` — student worksheets for 第6〜10回, each with a recent-news intro and a story-based exercise whose answers are posted to Teams. `worksheets/markdown/worksheetNN.md` is the source; `python3 worksheets/build.py [NN]` regenerates `word/` and `pdf/` (needs python-docx and LuaLaTeX; the site does not depend on it). 問3 onward mirror each lecture page's Teams投稿のテーマ, so keep them in step. Each lecture page's 考えてみよう block links to its worksheet in all three formats. See `worksheets/README.md`. The instructor edition lives in `worksheets/teacher/`, which is gitignored and local only: `answers.md` holds the model answers and `python3 worksheets/build_teacher.py` builds `worksheets_teacher.pdf` (all five sessions in one file). The repo is public and its root is deployed, so never commit, force-add or publish anything from that folder.
- `notes/` — lecture notes for 第6〜10回, one page per topic of each lecture page's 講義の流れ (4 pages per session). `notes/markdown/noteNN.md` is the source; `python3 notes/build.py [NN]` regenerates `tex/` (the LaTeX actually compiled), `pdf/` (Japanese LuaLaTeX: jlreq + luatexja, HaranoAji fonts) and `word/` (reuses `worksheets/build.py`; needs LibreOffice for the Word page check only). The build refuses a PDF whose producer is not LuaTeX. It stops if topic names differ from the lecture page or a topic overflows its page. Notes are handed out on Teams and are not linked from the site. See `notes/README.md`.
- `videos/` — narrated slide videos of each lecture page's 講義の流れ. `videos/script/lectureNN.md` is the source; `python3 videos/build.py [NN]` regenerates `mp4/` and `vtt/` (needs LuaLaTeX, ffmpeg, websocket-client, and a paid OpenAI key; speech uses the Realtime API model `gpt-realtime-2.1-mini`). It stops if part names, the title, or the Teams theme differ from the lecture page, so rebuild after changing those. The model sometimes misspeaks, so the build re-synthesizes until its transcript matches the script; only add same-reading spellings to `SPELLING_VARIANTS`. The AI-voice disclosure in the narration and on the slides is required by OpenAI's terms; keep it. See `videos/README.md`.
- `assets/css/style.css` — shared styles (header, hero, top-page sections, footer). `assets/css/pages.css` — sub-page styles (page hero, lecture layout, blocks, pager); load it after `style.css`.
- `assets/js/main.js` — mobile menu toggle, scrolled-header state, active nav link.
- `assets/favicon.svg` is the icon source; `favicon.ico` (16/32/48), `favicon-16x16.png`, `favicon-32x32.png`, `apple-touch-icon.png` (180, square background) are exported from it (ImageMagick `-density` = px × 1.5 at 96 dpi, ICO via Pillow). Every page's `<head>` links ico + svg + apple-touch-icon; regenerate all of them together if the mark changes.
- The official syllabus PDF is not kept in the repo. Course facts (session titles, evaluation, office hours) as reflected in `index.html` and `README.md` were taken from the 2026 syllabus; if the user provides a new syllabus, update all of them together.

## Conventions

- Course facts (session titles, evaluation, contact, office hours) must match the syllabus. Kawai's evaluation: 授業への参加度（Teamsへの記事投稿）および小テスト. All communication with students is via Microsoft Teams; lecture notes are posted on Teams, not on this site.
- Kawai's sessions are on five consecutive Mondays, 2限 10:40–12:10, room 2-403: 第6回 11/2, 第7回 11/9, 第8回 11/16, 第9回 11/23, 第10回 11/30 (2026). Dates appear on the top page (course card, news, schedule), `lectures/index.html`, each lecture page's meta chips, the header line of each `worksheets/markdown/worksheetNN.md` and `notes/markdown/noteNN.md`, and the schedule table in `notes/markdown/note06.md`; update all of them together if the schedule changes (the videos deliberately carry no dates). Note 11/23 is a national holiday (勤労感謝の日); the user confirmed the weekly schedule as-is.
- Each lecture page has the same six blocks: ねらい / キーワード / 講義の流れ / 考えてみよう（Teams投稿のテーマ） / 読んでみよう / 復習のポイント, plus prev/next pager. Keep new pages consistent with that structure.
- Survey facts/sources in `assets/js/survey-data.js` cite white papers and statistics; when the user asks to update a session's survey, verify the numbers against the cited source and keep 5 questions per session with `kind`, `answer`, `summary`, `fact`, `bias` fields. The API accepts only sessions 06–10, keys `q1`–`q10`, and choice values `a`–`h`; one response per `client_id` per session (upsert).
- Bump the `?v=YYYYMMDD` query on CSS/JS links when changing those files, so browsers pick up the new version.
- When making a user-visible change, add a dated entry (Japanese, newest first) to the 更新履歴 section of `README.md`.
