# 企業診断ＡＢＣ 2026（河合担当分）

2026年度「企業診断ＡＢＣ」（名古屋市立大学・後期・月曜2限 10:40–12:10）のうち、河合勝彦が担当する第6〜10回（2026年11月2日〜11月30日、毎週月曜）の講義サイトです。科目は3名の教員（坂和・河合・高橋）で分担しており、このサイトは河合担当分のみを対象としています。

## 公開サイト

<https://kklab.mobi/kklab-ksabc2026/>

## 構成

- `index.html` — トップページ（授業概要、お知らせ、講義予定、資料、評価・受講のしかた、問い合わせ）
- `lectures/index.html` — 講義一覧（第6〜10回）
- `lectures/lecture06.html` 〜 `lecture10.html` — 各回の講義ページ（ねらい・キーワード・講義の流れ・考えてみよう（Teams投稿のテーマ）・読んでみよう・復習のポイント）
- `attendance/index.html`, `attendance/attendance06.html` 〜 `attendance10.html` — 出席確認クイズ（各回5問）
- `survey/index.html`, `survey/survey06.html` 〜 `survey10.html` — 講義アンケート（各回5問・匿名）。設問は `assets/js/survey-data.js` に一元化
- `survey/results.html` — 集計結果ページ（回答分布・事実・出典・バイアスの解説。教員用パネルで公開／締切／CSV／リセット）
- `assets/js/survey-data.js` — アンケートの設問データ（アンケートページと集計ページの両方が参照）、`assets/js/survey.js` — 回答送信・集計表示のスクリプト
- `api/` — 集計 API（Cloudflare Workers + D1）。`api/src/index.js` 本体、`api/schema.sql` スキーマ、`api/wrangler.jsonc` 設定
- `assets/css/style.css` — 共通スタイル（トップページ・ヘッダー・フッター）
- `assets/js/attendance.js` — 出席確認クイズのスクリプト（確認コードの計算を含む）
- `assets/css/pages.css` — 下層ページ用スタイル（`style.css` の後に読み込む）
- `assets/js/main.js` — ヘッダーのメニュー開閉・スクロール時のナビ強調
- `assets/favicon.svg` / `favicon.ico` / `favicon-16x16.png` / `favicon-32x32.png` / `apple-touch-icon.png` — サイトアイコン（元は `favicon.svg`。PNG/ICO は ImageMagick と Pillow で書き出し）
- `.github/workflows/pages.yml` — GitHub Pages への自動デプロイ

河合担当回の内容（シラバスより）:

| 回 | 日程 | テーマ |
| --- | --- | --- |
| 第6回 | 11/2（月） | 経営情報の基礎：企業（組織）とソーシャルメディア |
| 第7回 | 11/9（月） | 人工知能：企業における生成AI |
| 第8回 | 11/16（月） | つながり：ネットワークがもたらす企業の変化 |
| 第9回 | 11/23（月・祝、祝日授業日） | XテックとDX：企業のデジタル戦略 |
| 第10回 | 11/30（月） | あたらしい社会像：Society 5.0 と スマートシティ |

## 講義アンケートの運用（教員用メモ）

- 学生は `survey/survey06.html` などから匿名で回答し、回答は Cloudflare Workers の API（`api/`）経由で D1 に保存される。
- 集計結果ページ（`survey/results.html`）の下部「Instructor — 教員用」に教員用キー（Worker のシークレット `SURVEY_ADMIN_KEY`）を入力すると、表示中の回について「集計を公開／非公開」「受付を締め切る／再開」「CSV をダウンロード」「回答をリセット」ができる。キーはその端末の localStorage に保存される。
- 公開前は、学生の画面には回答数だけが表示される。講義の冒頭で回答させ、教員が「集計を公開する」を押してから投影して解説する想定。公開後の結果ページは10秒ごとに自動更新される。
- 講義前にリハーサルで回答した場合は「回答をリセット」で消去する。各回の「事実・出典」の数値（白書・統計など）は講義前に最新のものを確認し、`assets/js/survey-data.js` を更新する。
- API のデプロイと設定（wrangler がログイン済みであること）:

```bash
npx wrangler d1 execute kklab-ksabc2026-survey --remote --config api/wrangler.jsonc --file api/schema.sql -y   # 初回のみ（スキーマ適用）
npx wrangler deploy --config api/wrangler.jsonc                                                                 # Worker のデプロイ
npx wrangler secret put SURVEY_ADMIN_KEY --config api/wrangler.jsonc                                            # 教員用キーの設定（対話入力）
curl https://kklab-ksabc2026-survey.katzkawai.workers.dev/api/health                                            # 動作確認
```

- ローカル検証: `npx wrangler dev --config api/wrangler.jsonc --port 8787 --local`（教員用キーは `api/.dev.vars` の `SURVEY_ADMIN_KEY`。このファイルはコミットしない）。サイト側はブラウザのコンソールで `localStorage.setItem("ksabc2026-survey-api", "http://127.0.0.1:8787")` とすると、ローカルの API に接続する。

## ローカルでの確認

ビルド工程はありません。

```bash
python3 -m http.server 8000
```

ブラウザで <http://localhost:8000> を開いてください。

## 更新方法

`main` ブランチへのプッシュを契機に、GitHub Actions が GitHub Pages へ自動デプロイします。ユーザーに見える変更をしたときは、下の更新履歴に日付つきで追記してください。

## 更新履歴

- 2026-10-18: 講義アンケートのページを追加（`survey/`。第6〜10回それぞれに学習内容に直結し、バイアスや誤解が見えてくる5問を匿名で回答。集計結果ページ `survey/results.html` に回答分布・事実・出典・バイアスの解説を表示、教員用パネルで公開／締切／CSV／リセット）。集計 API（Cloudflare Workers + D1、`api/`）を追加。全ページのナビとトップページのお知らせ・資料セクションにリンクを追加
- 2026-09-10: 出席確認クイズのページを追加（`attendance/`。第6〜10回それぞれにAIの基礎知識を問う4択5問、全問正解で確認コード付きの出席カードを表示）。全ページのナビとトップページの資料セクションにリンクを追加
- 2026-09-07: favicon を追加（SVG / ICO / PNG / Apple Touch Icon。ネイビー地にアンバーの棒グラフ）
- 2026-09-07: 11月23日（月・祝）が祝日授業日である旨をトップページ・講義一覧・第9回ページに明記
- 2026-09-07: 河合担当回の日程（11月2日〜11月30日、毎週月曜2限 10:40–12:10）をトップページ・講義一覧・各講義ページに掲載
- 2026-09-07: サイトを新規作成し、GitHub Pages で公開（トップページ、講義一覧、第6〜10回の講義ページ）
