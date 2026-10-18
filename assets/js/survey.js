// 講義アンケート（survey/ 配下の各ページで共用）。設問データは survey-data.js（window.KSABC_SURVEY）。
// 回答は匿名。端末ごとの client_id（UUID、localStorage に保存）で、同じ回の再送信は上書きされる。
(function () {
  "use strict";

  var CFG = window.KSABC_SURVEY;
  var KEY_CLIENT = "ksabc2026-survey-client";
  var KEY_ADMIN = "ksabc2026-survey-admin";
  var KEY_API = "ksabc2026-survey-api";
  var KEY_ANSWERS = "ksabc2026-survey-answers-"; // + 回（"06" など）

  // ---------- 共通ユーティリティ ----------
  function storeGet(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }
  function storeSet(key, value) { try { localStorage.setItem(key, value); } catch (e) { /* 保存できなくても動作する */ } }
  function storeRemove(key) { try { localStorage.removeItem(key); } catch (e) { /* 無視 */ } }
  function storeJson(key) { try { return JSON.parse(storeGet(key) || "null"); } catch (e) { return null; } }

  function apiBase() {
    var override = storeGet(KEY_API);
    return (override || CFG.apiBase).replace(/\/+$/, "");
  }

  function uuid() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    var b = new Uint8Array(16);
    (window.crypto || window.msCrypto).getRandomValues(b);
    b[6] = (b[6] & 0x0f) | 0x40;
    b[8] = (b[8] & 0x3f) | 0x80;
    var h = Array.prototype.map.call(b, function (x) { return x.toString(16).padStart(2, "0"); }).join("");
    return h.slice(0, 8) + "-" + h.slice(8, 12) + "-" + h.slice(12, 16) + "-" + h.slice(16, 20) + "-" + h.slice(20);
  }

  function clientId() {
    var id = storeGet(KEY_CLIENT);
    if (!id || !/^[0-9a-f-]{36}$/i.test(id)) {
      id = uuid();
      storeSet(KEY_CLIENT, id);
    }
    return id;
  }

  function letter(i) { return String.fromCharCode(97 + i); }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function formatNow() {
    var d = new Date();
    var pad = function (n) { return String(n).padStart(2, "0"); };
    return (d.getMonth() + 1) + "/" + d.getDate() + " " + pad(d.getHours()) + ":" + pad(d.getMinutes());
  }

  async function api(path, opts) {
    opts = opts || {};
    var headers = { Accept: "application/json" };
    if (opts.body) headers["Content-Type"] = "application/json";
    if (opts.admin) headers.Authorization = "Bearer " + opts.admin;
    var res;
    try {
      res = await fetch(apiBase() + path, {
        method: opts.method || "GET",
        headers: headers,
        body: opts.body ? JSON.stringify(opts.body) : undefined,
        cache: "no-store",
      });
    } catch (e) {
      var ne = new Error("network");
      ne.status = 0;
      throw ne;
    }
    if (opts.raw) return res;
    var data = null;
    try { data = await res.json(); } catch (e) { /* JSON でない応答 */ }
    if (!res.ok || !data || data.ok === false) {
      var err = new Error((data && data.error) || "http " + res.status);
      err.status = res.status;
      throw err;
    }
    return data;
  }

  function messageFor(err) {
    if (!err) return "エラーが発生しました。";
    if (err.status === 0) return "サーバーに接続できませんでした。通信環境を確認して、もう一度お試しください。";
    if (err.status === 409) return "この回のアンケートは受付を終了しています。";
    if (err.status === 429) return "アクセスが集中しています。少し待ってから、もう一度お試しください。";
    if (err.status === 401) return "教員用キーが無効です。";
    if (err.status === 403) return "このページの URL からは送信できません（https://kklab.mobi/ で開いてください）。";
    return "エラーが発生しました（" + err.message + "）。";
  }

  // ---------- アンケートページ（survey06.html など） ----------
  window.initSurveyPage = function (opts) {
    var sid = opts.session;
    var S = CFG.sessions[sid];
    var root = document.getElementById("survey-questions");
    var form = document.getElementById("survey-form");
    var status = document.getElementById("survey-status");
    var errorBox = document.getElementById("error-box");
    var submitBtn = document.getElementById("submit-btn");
    var formPage = document.getElementById("form-page");
    var done = document.getElementById("done");
    var doneCount = document.getElementById("done-count");
    var doneResults = document.getElementById("done-results");
    var editBtn = document.getElementById("edit-btn");

    root.innerHTML = S.questions
      .map(function (q, i) {
        return (
          '<div class="question" id="' + q.id + '">' +
          '<p><span class="qno">Q' + (i + 1) + ".</span>" +
          '<span class="qkind">' + esc(CFG.kinds[q.kind] || "") + "</span>" +
          esc(q.text) + "</p>" +
          q.choices
            .map(function (c, k) {
              return '<label class="choice"><input type="radio" name="' + q.id + '" value="' + letter(k) + '" />' + esc(c) + "</label>";
            })
            .join("") +
          "</div>"
        );
      })
      .join("");

    function showError(message) {
      errorBox.textContent = message;
      errorBox.style.display = "block";
      errorBox.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    function hideError() { errorBox.style.display = "none"; }
    function setBusy(busy) {
      submitBtn.disabled = busy;
      submitBtn.textContent = busy ? "送信中…" : "回答を送信する";
    }
    function setStatus(text, closed) {
      status.textContent = text || "";
      status.classList.toggle("is-closed", Boolean(closed));
    }

    // この端末からの回答済みデータがあれば復元する
    var saved = storeJson(KEY_ANSWERS + sid);
    if (saved && saved.answers) {
      Object.keys(saved.answers).forEach(function (q) {
        var input = form.querySelector('input[name="' + q + '"][value="' + saved.answers[q] + '"]');
        if (input) input.checked = true;
      });
      setStatus("この端末からは " + saved.at + " に回答済みです。回答を修正して、もう一度送信することもできます。");
    }

    // 受付状況の確認（取得できなくても回答は試みられる）
    api("/api/sessions/" + sid)
      .then(function (d) {
        if (!d.open) {
          setStatus("この回のアンケートは受付を終了しました。", true);
          submitBtn.disabled = true;
        }
      })
      .catch(function () { /* 無視 */ });

    form.addEventListener("submit", async function (ev) {
      ev.preventDefault();
      hideError();
      var answers = {};
      var missing = [];
      S.questions.forEach(function (q, i) {
        var checked = form.querySelector('input[name="' + q.id + '"]:checked');
        if (!checked) missing.push(i + 1);
        else answers[q.id] = checked.value;
      });
      if (missing.length) {
        showError("Q" + missing.join("・Q") + " に回答してください。");
        return;
      }
      setBusy(true);
      try {
        var d = await api("/api/sessions/" + sid + "/responses", {
          method: "POST",
          body: { client_id: clientId(), answers: answers },
        });
        storeSet(KEY_ANSWERS + sid, JSON.stringify({ answers: answers, at: formatNow() }));
        doneCount.textContent = "あなたを含めて " + d.count + " 人が回答しています。";
        doneResults.textContent = d.revealed ? "集計結果を見る（公開中） →" : "集計結果ページへ（講義内で公開） →";
        formPage.hidden = true;
        done.hidden = false;
        window.scrollTo(0, 0);
      } catch (e) {
        showError(messageFor(e));
      } finally {
        setBusy(false);
      }
    });

    editBtn.addEventListener("click", function () {
      done.hidden = true;
      formPage.hidden = false;
      setStatus("回答を修正して、もう一度「回答を送信する」を押してください。前の回答は上書きされます。");
      window.scrollTo(0, 0);
    });
  };

  // ---------- 集計ページ（results.html） ----------
  window.initResultsPage = function () {
    var el = function (id) { return document.getElementById(id); };
    var tabs = el("results-tabs");
    var eyebrow = el("results-eyebrow");
    var title = el("results-title");
    var lectureEl = el("results-lecture");
    var countEl = el("results-count");
    var stateEl = el("results-state");
    var note = el("results-note");
    var body = el("results-body");
    var autoRefresh = el("auto-refresh");
    var adminPanel = el("admin-panel");
    var adminLogin = el("admin-login");
    var adminTools = el("admin-tools");
    var adminForm = el("admin-form");
    var adminKeyInput = el("admin-key");
    var adminMsg = el("admin-msg");
    var overview = el("admin-sessions");
    var btnReveal = document.querySelector('[data-admin="reveal"]');
    var btnOpen = document.querySelector('[data-admin="open"]');

    var admin = storeGet(KEY_ADMIN) || "";
    var current = pickSession();
    var last = null;

    function localToday() {
      var d = new Date();
      var pad = function (n) { return String(n).padStart(2, "0"); };
      return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
    }

    // ?s=07 か #07 があればその回。なければ、今日までに実施済みの最新の回（初回前なら第6回）
    function pickSession() {
      var p = new URLSearchParams(location.search).get("s") || (location.hash || "").replace("#", "");
      if (CFG.order.indexOf(p) !== -1) return p;
      var today = localToday();
      var pick = CFG.order[0];
      CFG.order.forEach(function (id) { if (CFG.sessions[id].iso <= today) pick = id; });
      return pick;
    }

    function setNote(text, isError) {
      note.textContent = text || "";
      note.classList.toggle("is-error", Boolean(isError));
    }

    function renderTabs() {
      tabs.innerHTML = CFG.order
        .map(function (id) {
          var s = CFG.sessions[id];
          return '<button type="button" role="tab" data-session="' + id + '" aria-selected="' + (id === current) + '">第' + s.no + "回<small>" + esc(s.date) + "</small></button>";
        })
        .join("");
    }

    tabs.addEventListener("click", function (ev) {
      var btn = ev.target.closest("button[data-session]");
      if (!btn) return;
      current = btn.getAttribute("data-session");
      history.replaceState(null, "", "?s=" + current);
      renderTabs();
      body.innerHTML = "";
      load();
    });

    function renderQuestion(q, index, tally, total) {
      var head =
        '<div class="result-q-head"><div class="qmeta"><span class="qno">Q' + (index + 1) + "</span>" +
        '<span class="qkind">' + esc(CFG.kinds[q.kind] || "") + "</span>";
      if (!tally) {
        return (
          '<article class="result-q">' + head + "</div><h3>" + esc(q.text) + "</h3></div>" +
          '<p class="result-hidden">集計結果は講義のなかで公開します（現在の回答数: ' + total + "）。</p></article>"
        );
      }
      var letters = q.choices.map(function (_, k) { return letter(k); });
      var n = letters.reduce(function (a, L) { return a + (tally[L] || 0); }, 0);
      head += '<span class="qn">n = ' + n + "</span></div><h3>" + esc(q.text) + "</h3></div>";

      var bars =
        '<ol class="bars">' +
        q.choices
          .map(function (c, k) {
            var L = letters[k];
            var v = tally[L] || 0;
            var pct = n ? Math.round((v / n) * 100) : 0;
            var isAnswer = q.answer === L;
            return (
              "<li" + (isAnswer ? ' class="is-answer"' : "") + ">" +
              '<span class="bar-label"><span class="letter">' + L + ".</span><span>" + esc(c) + "</span>" +
              (isAnswer ? '<span class="answer-tag">事実</span>' : "") + "</span>" +
              '<span class="bar-row"><span class="bar-track"><span class="bar-fill" style="width:' + pct + '%"></span></span>' +
              '<span class="bar-value">' + pct + "%<small>" + v + "人</small></span></span></li>"
            );
          })
          .join("") +
        "</ol>";

      var summary = "";
      if (q.summary) {
        var sv = q.summary.choices.reduce(function (a, L) { return a + (tally[L] || 0); }, 0);
        var sp = n ? Math.round((sv / n) * 100) : 0;
        summary = '<p class="result-summary"><span>' + esc(q.summary.label) + "</span><b>" + sp + "%</b></p>";
      }
      var fact = q.fact ? '<p class="result-fact"><b>事実・出典</b>' + esc(q.fact) + "</p>" : "";
      var bias = q.bias ? '<p class="result-bias"><b>表れやすいバイアス・誤解</b>' + esc(q.bias) + "</p>" : "";
      return '<article class="result-q">' + head + bars + summary + fact + bias + "</article>";
    }

    function render(d) {
      var S = CFG.sessions[current];
      eyebrow.textContent = "Survey " + current + " — " + S.date;
      title.textContent = S.title;
      lectureEl.textContent = "第" + S.no + "回　" + S.lecture;
      countEl.textContent = d.count;
      stateEl.textContent = (d.open ? "受付中" : "締切") + " ／ " + (d.revealed ? "公開中" : "非公開");
      stateEl.classList.toggle("is-revealed", Boolean(d.revealed));
      document.title = "第" + S.no + "回 集計結果：" + S.title + "｜企業診断ＡＢＣ 2026";

      body.innerHTML = S.questions
        .map(function (q, i) { return renderQuestion(q, i, d.tallies ? d.tallies[q.id] || {} : null, d.count); })
        .join("");

      if (d.tallies && !d.revealed) setNote("教員ログイン中：この回の集計はまだ非公開です。学生には回答数だけが表示されています。");
      else if (!d.tallies) setNote("集計結果は講義のなかで公開します。公開されると、このページに自動で表示されます。");
      else setNote("");

      if (btnReveal) btnReveal.textContent = d.revealed ? "集計を非公開にする" : "集計を公開する";
      if (btnOpen) btnOpen.textContent = d.open ? "受付を締め切る" : "受付を再開する";
    }

    async function load() {
      try {
        var d = await api("/api/sessions/" + current + "/results", { admin: admin || undefined });
        last = d;
        render(d);
      } catch (e) {
        if (e.status === 401 && admin) {
          admin = "";
          storeRemove(KEY_ADMIN);
          setAdminUi();
          return load();
        }
        setNote(messageFor(e), true);
      }
    }

    // ---- 教員用 ----
    function setAdminUi() {
      adminLogin.hidden = Boolean(admin);
      adminTools.hidden = !admin;
      adminMsg.textContent = "";
    }

    async function loadOverview() {
      if (!admin) return;
      try {
        var d = await api("/api/admin/sessions", { admin: admin });
        overview.innerHTML =
          "<thead><tr><th>回</th><th>回答数</th><th>受付</th><th>集計</th></tr></thead><tbody>" +
          d.sessions
            .map(function (s) {
              var S = CFG.sessions[s.session];
              return (
                "<tr" + (s.session === current ? ' class="is-current"' : "") + "><td>第" + S.no + "回（" + esc(S.date) + "）</td><td>" + s.count + "</td>" +
                '<td><span class="state-pill ' + (s.open ? "is-on" : "is-off") + '">' + (s.open ? "受付中" : "締切") + "</span></td>" +
                '<td><span class="state-pill ' + (s.revealed ? "is-on" : "is-off") + '">' + (s.revealed ? "公開中" : "非公開") + "</span></td></tr>"
              );
            })
            .join("") +
          "</tbody>";
      } catch (e) {
        adminMsg.textContent = messageFor(e);
      }
    }

    adminForm.addEventListener("submit", async function (ev) {
      ev.preventDefault();
      var key = adminKeyInput.value.trim();
      if (!key) return;
      adminMsg.textContent = "確認中…";
      try {
        await api("/api/admin/ping", { admin: key });
        admin = key;
        storeSet(KEY_ADMIN, key);
        adminKeyInput.value = "";
        setAdminUi();
        await load();
        await loadOverview();
      } catch (e) {
        adminMsg.textContent = e.status === 401 ? "キーが違います。" : messageFor(e);
      }
    });

    async function adminAction(kind) {
      if (!admin) return;
      var S = CFG.sessions[current];
      adminMsg.textContent = "";
      try {
        if (kind === "logout") {
          admin = "";
          storeRemove(KEY_ADMIN);
          setAdminUi();
          await load();
          return;
        }
        if (!last) await load();
        if (kind === "reveal") {
          await api("/api/admin/sessions/" + current, { method: "PATCH", admin: admin, body: { revealed: !last.revealed } });
        } else if (kind === "open") {
          await api("/api/admin/sessions/" + current, { method: "PATCH", admin: admin, body: { open: !last.open } });
        } else if (kind === "reset") {
          if (!window.confirm("第" + S.no + "回の回答 " + last.count + " 件をすべて削除します。元に戻せません。よろしいですか？")) return;
          await api("/api/admin/sessions/" + current + "/responses", { method: "DELETE", admin: admin });
        } else if (kind === "export") {
          var res = await api("/api/admin/sessions/" + current + "/export", { admin: admin, raw: true });
          if (!res.ok) { var err = new Error("http " + res.status); err.status = res.status; throw err; }
          var blob = await res.blob();
          var a = document.createElement("a");
          a.href = URL.createObjectURL(blob);
          a.download = "ksabc2026-survey" + current + ".csv";
          document.body.appendChild(a);
          a.click();
          a.remove();
          setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
        }
        await load();
        await loadOverview();
      } catch (e) {
        adminMsg.textContent = messageFor(e);
        if (e.status === 401) {
          admin = "";
          storeRemove(KEY_ADMIN);
          setAdminUi();
        }
      }
    }

    document.querySelectorAll("[data-admin]").forEach(function (btn) {
      btn.addEventListener("click", function () { adminAction(btn.getAttribute("data-admin")); });
    });

    // ---- 自動更新（講義中の投影用。タブが見えているときだけ） ----
    setInterval(function () {
      if (autoRefresh.checked && document.visibilityState === "visible") load();
    }, 10000);
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "visible") load();
    });

    renderTabs();
    setAdminUi();
    if (admin) adminPanel.open = true;
    load();
    loadOverview();
  };
})();
