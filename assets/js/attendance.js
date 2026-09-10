// 出席確認クイズ（attendance/ 配下の各ページで共用）
// 注意: 確認コードの計算方法や時刻の書式を変更すると、すでに提出された確認コードの照合ができなくなります。

function fieldNormalize(s) {
  return s.normalize("NFKC").replace(/[\s　]+/g, " ").trim();
}

function codeKey() {
  var p = ["7qLz", "hR", "26", "kkKSABC"];
  return p[3] + p[2] + "-" + p[1] + p[0];
}

async function computeCode(pageId, studentId, studentName, timeText) {
  var input = [pageId, fieldNormalize(studentId), fieldNormalize(studentName), timeText.trim(), codeKey()].join("|");
  var buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(input));
  var hex = Array.from(new Uint8Array(buf))
    .map(function (b) { return b.toString(16).padStart(2, "0"); })
    .join("")
    .toUpperCase();
  return hex.slice(0, 4) + "-" + hex.slice(4, 8);
}

function formatJst(y, mo, d, h, mi, s) {
  var pad = function (n) { return String(n).padStart(2, "0"); };
  return y + "年" + mo + "月" + d + "日 " + pad(h) + ":" + pad(mi) + ":" + pad(s);
}

// サーバー時刻（日本時間）の取得。端末の時計・タイムゾーン設定には依存しない。
// 取得できなかった場合は null を返す（端末時計へのフォールバックはしない）。
async function fetchServerTime() {
  try {
    var r = await fetch("https://timeapi.io/api/Time/current/zone?timeZone=Asia/Tokyo", { cache: "no-store" });
    if (r.ok) {
      var d = await r.json();
      if (d && d.year) return formatJst(d.year, d.month, d.day, d.hour, d.minute, d.seconds);
    }
  } catch (e) { /* 次の候補へ */ }
  try {
    var r2 = await fetch("https://worldtimeapi.org/api/timezone/Asia/Tokyo", { cache: "no-store" });
    if (r2.ok) {
      var d2 = await r2.json();
      var m = String(d2.datetime).match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})/);
      if (m) return formatJst(+m[1], +m[2], +m[3], +m[4], +m[5], +m[6]);
    }
  } catch (e) { /* 取得失敗 */ }
  return null;
}

function initAttendanceQuiz(config) {
  var ANSWERS = config.answers;
  var PAGE_ID = config.pageId;
  var QUESTION_COUNT = config.questionCount;
  var STORAGE_ID = "ksabc2026-student-id";
  var STORAGE_NAME = "ksabc2026-student-name";

  // 選択肢の表示順をページ読み込みごとに入れ替える
  document.querySelectorAll(".question").forEach(function (block) {
    var labels = Array.prototype.slice.call(block.querySelectorAll(".choice"));
    var anchor = block.querySelector(".explain");
    for (var i = labels.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1));
      var t = labels[i]; labels[i] = labels[j]; labels[j] = t;
    }
    labels.forEach(function (label) { block.insertBefore(label, anchor); });
  });

  // 学籍番号・氏名は端末内に記憶（入力の手間を減らすため）
  try {
    var savedId = localStorage.getItem(STORAGE_ID);
    var savedName = localStorage.getItem(STORAGE_NAME);
    if (savedId) document.getElementById("student-id").value = savedId;
    if (savedName) document.getElementById("student-name").value = savedName;
  } catch (e) { /* 記憶できなくても動作に支障なし */ }

  function getChecked(name) {
    var checked = document.querySelector('input[name="' + name + '"]:checked');
    return checked ? checked.value : null;
  }

  function showError(message) {
    var box = document.getElementById("error-box");
    box.textContent = message;
    box.style.display = "block";
    box.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function hideError() {
    document.getElementById("error-box").style.display = "none";
  }

  function clearQuestion(i) {
    document.querySelectorAll('input[name="q' + i + '"]').forEach(function (r) { r.checked = false; });
  }

  function setSubmitting(busy) {
    var btn = document.getElementById("submit-btn");
    btn.disabled = busy;
    btn.textContent = busy ? "提出処理中…" : "提出する";
  }

  async function submitQuiz() {
    hideError();

    var id = document.getElementById("student-id").value.trim();
    var name = document.getElementById("student-name").value.trim();

    if (!id || !name) {
      showError("学籍番号と氏名を入力してください。");
      return;
    }

    var unanswered = [], wrong = [];
    for (var i = 1; i <= QUESTION_COUNT; i++) {
      var v = getChecked("q" + i);
      var block = document.getElementById("q" + i);
      block.classList.remove("wrong");
      if (!v) unanswered.push(i);
      else if (v !== ANSWERS["q" + i]) wrong.push(i);
    }

    if (unanswered.length) {
      showError("Q" + unanswered.join("・Q") + " に回答してください。");
      return;
    }

    if (wrong.length) {
      wrong.forEach(function (w) {
        document.getElementById("q" + w).classList.add("wrong");
        clearQuestion(w);
      });
      showError(wrong.length + "問が不正解です（Q" + wrong.join("・Q") + "）。解説を読んで、もう一度回答してください。");
      return;
    }

    if (!window.crypto || !crypto.subtle) {
      showError("このページは https:// で開く必要があります。URLを確認してください。");
      return;
    }

    try {
      localStorage.setItem(STORAGE_ID, id);
      localStorage.setItem(STORAGE_NAME, name);
    } catch (e) { /* 無視 */ }

    setSubmitting(true);
    var timeText = await fetchServerTime();
    if (!timeText) {
      setSubmitting(false);
      showError("時刻サーバーに接続できませんでした。通信環境を確認して、もう一度「提出する」を押してください。");
      return;
    }

    var code = await computeCode(PAGE_ID, id, name, timeText);

    document.getElementById("result-id").textContent = id;
    document.getElementById("result-name").textContent = name;
    document.getElementById("result-time").textContent = timeText;
    document.getElementById("result-code").textContent = code;
    document.getElementById("form-page").hidden = true;
    document.getElementById("result").hidden = false;
    window.scrollTo(0, 0);
  }

  document.getElementById("submit-btn").addEventListener("click", submitQuiz);
}
