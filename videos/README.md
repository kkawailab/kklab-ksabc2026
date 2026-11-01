# 講義の流れの動画（第6〜10回）

各回の講義ページにある「講義の流れ」を、解説音声付きのスライド動画にしたものです。1本3〜4分で、字幕は動画に入っているほか、`vtt/` にも置いています。

| 回 | 原稿 | 動画 | 字幕 |
|---|---|---|---|
| 第6回 | [script/lecture06.md](script/lecture06.md) | `mp4/lecture06.mp4` | `vtt/lecture06.vtt` |
| 第7回 | [script/lecture07.md](script/lecture07.md) | `mp4/lecture07.mp4` | `vtt/lecture07.vtt` |
| 第8回 | [script/lecture08.md](script/lecture08.md) | `mp4/lecture08.mp4` | `vtt/lecture08.vtt` |
| 第9回 | [script/lecture09.md](script/lecture09.md) | `mp4/lecture09.mp4` | `vtt/lecture09.vtt` |
| 第10回 | [script/lecture10.md](script/lecture10.md) | `mp4/lecture10.mp4` | `vtt/lecture10.vtt` |

## 組み立て

- 各回は、表紙、この回の流れ、パートごとのスライド、Teams 投稿のテーマの順です。
- パート名、題名、Teams 投稿のテーマは、講義ページと同じにしています。講義ページとずれると `build.py` が止まります。
- 各講義ページの「講義の流れ」の下に、動画のプレーヤー（字幕は `vtt/` を読み込む）と、MP4・VTT へのリンクを置いています。ページの文には動画の長さを書いているので、動画を作り直して長さが変わったら、そこも直します。
- 日付と教室は入れていません。日程が変わっても、動画を作り直さずに済むようにするためです。
- 音声は AI による合成音声で、教員本人の声ではありません。OpenAI の利用条件により、その旨を動画の冒頭のナレーション、表紙と最後のスライド、メタ情報で明示しています。この明示は消さないでください。

## 作り直すとき

原稿は `script/lectureNN.md` です。書き方は `build.py` の冒頭にまとめてあります。読みを間違えやすい語は `{表示|読み}` と書くと、字幕は表示のまま、音声は読みのとおりになります。全回に共通する語は `build.py` の `SPEECH_WORDS` に足します。

作り直すには、LuaLaTeX、ffmpeg、poppler-utils、フォントの BIZ UDPGothic、Python の `websocket-client` と、OpenAI の API キーが必要です。キーは `~/.config/openai/api_key`（リポジトリの外。1行だけ書き、`chmod 600` にする）か、環境変数 `OPENAI_API_KEY` に設定します。

```bash
python3 videos/build.py        # 5回分すべて
python3 videos/build.py 08     # 第8回だけ
```

音声の合成は有料です。合成した音声は `.cache/` に残すので、直した文だけが合成し直されます。字幕の文、送った文、モデルの文字起こしは `.cache/lectureNN.readings.txt` に出ます。

## 音声の確認

音声は OpenAI の Realtime API の `gpt-realtime-2.1-mini`（音声は `marin`）で作ります。会話用のモデルなので、原稿と違うことを言うことがあります。実際に、「デジタイゼーション」を「デジタライゼーション」と言う、「2018年」を「二千二十八年」と言う、といった誤りが出ました。

そこで `build.py` は、モデルが返す文字起こしを原稿と照合し、完全に一致するまで合成し直します。読みが同じ表記の違いだけは、`SPELLING_VARIANTS` で同じとみなします。読みが違うものはここに足さないでください。

この文字起こしはモデル自身の報告で、音声を別に聞き取った結果ではありません。原稿と一致していても、音声が正しいとは限らないので、配布の前に人が聴いて確かめてください。
