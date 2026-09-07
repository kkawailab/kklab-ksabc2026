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
- `assets/css/style.css` — shared styles (header, hero, top-page sections, footer). `assets/css/pages.css` — sub-page styles (page hero, lecture layout, blocks, pager); load it after `style.css`.
- `assets/js/main.js` — mobile menu toggle, scrolled-header state, active nav link.
- The official syllabus PDF is not kept in the repo. Course facts (session titles, evaluation, office hours) as reflected in `index.html` and `README.md` were taken from the 2026 syllabus; if the user provides a new syllabus, update all of them together.

## Conventions

- Course facts (session titles, evaluation, contact, office hours) must match the syllabus. Kawai's evaluation: 授業への参加度（Teamsへの記事投稿）および小テスト. All communication with students is via Microsoft Teams; lecture notes are posted on Teams, not on this site.
- Kawai's sessions are on five consecutive Mondays, 2限 10:40–12:10, room 2-403: 第6回 11/2, 第7回 11/9, 第8回 11/16, 第9回 11/23, 第10回 11/30 (2026). Dates appear on the top page (course card, news, schedule), `lectures/index.html`, and each lecture page's meta chips; update all of them together if the schedule changes. Note 11/23 is a national holiday (勤労感謝の日); the user confirmed the weekly schedule as-is.
- Each lecture page has the same six blocks: ねらい / キーワード / 講義の流れ / 考えてみよう（Teams投稿のテーマ） / 読んでみよう / 復習のポイント, plus prev/next pager. Keep new pages consistent with that structure.
- Bump the `?v=YYYYMMDD` query on CSS/JS links when changing those files, so browsers pick up the new version.
- When making a user-visible change, add a dated entry (Japanese, newest first) to the 更新履歴 section of `README.md`.
