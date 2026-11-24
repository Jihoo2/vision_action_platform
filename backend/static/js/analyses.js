// 분석 화면: ① 분석 POST → 작업 ID 즉시 받음 → ② 1초마다 상태 조회 → ③ 완료 시 결과 표시
(() => {
  const API = "/api/v1/analyses/";
  const POLL_MS = 1000;
  const ACTION_LABELS = Object.fromEntries(JSON.parse(document.getElementById("action-labels").textContent));
  const STATUS_KO = { PENDING: "대기", PROCESSING: "처리 중", COMPLETED: "완료", FAILED: "실패" };
  const INPUT_KO = { UPLOAD: "영상 업로드", IPCAM: "IP Webcam" };

  const $ = (sel) => document.querySelector(sel);
  const form = $("#analyze-form"), startBtn = $("#start-btn");
  let pollTimer = null, currentId = null;

  // ---------- 공통 ----------
  function csrf() {
    const m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : form.querySelector("[name=csrfmiddlewaretoken]").value;
  }
  async function api(url, opts = {}) {
    const res = await fetch(url, { credentials: "same-origin", ...opts,
      headers: { "X-CSRFToken": csrf(), Accept: "application/json", ...(opts.headers || {}) } });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw Object.assign(new Error("API 오류"), { status: res.status, data });
    return data;
  }
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const actionName = (v) => (v ? ACTION_LABELS[v] || v : "-");
  const pct = (v) => (v == null ? "-" : `${(v * 100).toFixed(1)}%`);
  const sec = (v) => (v == null ? "-" : `${Number(v).toFixed(1)}초`);
  const time = (iso) => (iso ? new Date(iso).toLocaleString("ko-KR", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "-");
  function errText(err) {
    const d = err.data || {};
    if (typeof d === "object") {
      const msgs = Object.entries(d).map(([k, v]) => (Array.isArray(v) ? v.join(" ") : String(v)));
      if (msgs.length) return msgs.join(" / ");
    }
    return `요청 실패 (HTTP ${err.status || "?"})`;
  }

  // ---------- ① 입력 방식 탭 ----------
  document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => {
    const kind = tab.dataset.tab;
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t === tab));
    document.querySelectorAll(".pane").forEach((p) => p.classList.toggle("active", p.dataset.pane === kind));
    $("#input_type").value = kind;
    $("#step-processing").textContent = kind === "IPCAM" ? "영상 수집·AI 분석" : "처리 중";
  }));

  // ---------- ① 분석 시작 (POST) ----------
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const kind = $("#input_type").value;
    const fd = new FormData();
    fd.append("input_type", kind);
    ["expected_action", "title"].forEach((k) => fd.append(k, form.elements[k].value));
    if (kind === "UPLOAD") {
      const file = $("#video").files[0];
      if (!file) return showMessage("영상 파일을 선택하세요.", true);
      fd.append("video", file);
    } else {
      if (!form.elements.camera_url) return showMessage("허용된 카메라가 없습니다.", true);
      fd.append("camera_url", form.elements.camera_url.value);
      fd.append("capture_seconds", form.elements.capture_seconds.value);
    }
    startBtn.disabled = true;
    startBtn.textContent = kind === "UPLOAD" ? "업로드 중…" : "작업 등록 중…";
    try {
      const job = await api(API, { method: "POST", body: fd });       // 서버는 분석을 기다리지 않고 즉시 응답
      showJob(job);
      startPolling(job.id);
      form.reset(); $("#input_type").value = kind;
    } catch (err) {
      showMessage(errText(err), true);
    } finally {
      startBtn.disabled = false;
      startBtn.textContent = "AI 분석 시작";
    }
  });

  // ---------- ② 상태 주기 조회 ----------
  function startPolling(id) {
    clearInterval(pollTimer);
    currentId = id;
    pollTimer = setInterval(async () => {
      try {
        const st = await api(`${API}${id}/status/`);
        setSteps(st.status);
        if (st.status === "PROCESSING") showMessage(processingText());
        if (st.done) {
          clearInterval(pollTimer);
          showJob(await api(`${API}${id}/`));
          loadHistory();
        }
      } catch (err) {
        clearInterval(pollTimer);
        showMessage(errText(err), true);
      }
    }, POLL_MS);
  }
  const processingText = () => ($("#input_type").value === "IPCAM"
    ? "카메라에서 영상을 수집한 뒤 AI가 분석하고 있습니다. 카메라 앞에서 동작을 수행하세요."
    : "AI가 영상을 분석하고 있습니다…");

  function setSteps(status) {
    const order = ["PENDING", "PROCESSING", "COMPLETED"];
    document.querySelectorAll(".step").forEach((el) => {
      const s = el.dataset.step;
      el.className = "step";
      if (status === "FAILED") {
        if (s === "FAILED") el.classList.add("fail");
        else if (s !== "COMPLETED") el.classList.add("done");
      } else if (s === status) el.classList.add(status === "COMPLETED" ? "done" : "on");
      else if (order.indexOf(s) > -1 && order.indexOf(s) < order.indexOf(status)) el.classList.add("done");
    });
  }
  function showMessage(text, isError = false) {
    const el = $("#status-msg");
    el.textContent = text;
    el.className = isError ? "msg error" : "muted";
  }

  // ---------- ③ 결과 표시 ----------
  function showJob(job) {
    currentId = job.id;
    $("#job-label").textContent = `#${job.id} · ${INPUT_KO[job.input_type] || job.input_type}`;
    setSteps(job.status);
    const body = $("#result-body");
    if (job.status === "FAILED") {
      showMessage(job.error_message || "분석에 실패했습니다.", true);
      body.innerHTML = "";
      return;
    }
    if (job.status !== "COMPLETED") {
      showMessage(job.status === "PENDING" ? "작업이 등록되었습니다. 곧 처리를 시작합니다." : processingText());
      body.innerHTML = "";
      return;
    }
    showMessage(job.result_message || `분석 완료 · 영상 ${sec(job.video_duration_sec)} · AI 처리 ${sec(job.processing_time_sec)}`);
    const preds = job.predictions || [];
    const skipped = (job.extra && job.extra.skipped_tracks) || [];
    const rows = preds.map((p) => `
      <tr>
        <td>${p.track_id}</td>
        <td><b>${esc(actionName(p.action_label))}</b></td>
        <td><div class="bar"><span style="width:${(p.confidence * 100).toFixed(0)}%"></span></div>${pct(p.confidence)}</td>
        <td class="muted">${esc(actionName(p.second_label))} ${pct(p.second_confidence)}</td>
        <td>${p.uncertain ? '<span class="badge warn">판단 불확실</span>' : '<span class="badge ok">확실</span>'}</td>
        <td class="muted">${pct(p.mean_keypoint_conf)} · ${p.frames_seen}f</td>
      </tr>`).join("");
    body.innerHTML = `
      ${preds.length ? `
      <table class="data">
        <thead><tr><th>Track ID</th><th>예측 동작</th><th>Confidence</th><th>2순위</th><th>판단</th><th>입력 품질(관절·Frame)</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>` : '<p class="empty">사람별 예측 결과가 없습니다.</p>'}
      ${job.expected_action ? `<p class="muted">수행하려던 동작: ${esc(actionName(job.expected_action))} (정답으로 검증된 값이 아님)</p>` : ""}
      ${skipped.length ? `<p class="muted">제외된 Track: ${skipped.map((s) => `#${s.track_id} (${esc(s.reason)})`).join(", ")}</p>` : ""}
      <p class="hint">Confidence는 6개 동작 중 상대적인 점수입니다. 학습하지 않은 동작도 6개 중 하나로 나올 수 있습니다.</p>
      ${job.video ? `<video class="preview" src="${esc(job.video)}" controls muted></video>` : ""}`;
  }

  // ---------- 최근 이력 ----------
  async function loadHistory() {
    const tbody = $("#history");
    try {
      const data = await api(`${API}?page=1`);
      const jobs = data.results || data;
      if (!jobs.length) { tbody.innerHTML = '<tr><td colspan="9" class="empty">아직 분석 기록이 없습니다.</td></tr>'; return; }
      tbody.innerHTML = jobs.slice(0, 10).map((j) => {
        const top = (j.predictions || []).slice().sort((a, b) => b.confidence - a.confidence)[0];
        const badge = { COMPLETED: "ok", FAILED: "err", PROCESSING: "run", PENDING: "" }[j.status];
        return `<tr class="clickable ${j.id === currentId ? "sel" : ""}" data-id="${j.id}">
          <td>${j.id}</td><td>${INPUT_KO[j.input_type] || j.input_type}</td>
          <td><span class="badge ${badge}">${STATUS_KO[j.status] || j.status}</span></td>
          <td>${esc(actionName(j.expected_action))}</td>
          <td>${top ? `${esc(actionName(top.action_label))} (${j.prediction_count}명)` : "-"}</td>
          <td>${top ? pct(top.confidence) : "-"}</td>
          <td>${sec(j.video_duration_sec)}</td><td>${sec(j.processing_time_sec)}</td>
          <td class="muted">${time(j.created_at)}</td></tr>`;
      }).join("");
      tbody.querySelectorAll("tr.clickable").forEach((tr) => tr.addEventListener("click", async () => {
        const job = await api(`${API}${tr.dataset.id}/`);
        showJob(job);
        if (!["COMPLETED", "FAILED"].includes(job.status)) startPolling(job.id);
        tbody.querySelectorAll("tr").forEach((r) => r.classList.toggle("sel", r === tr));
      }));
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="9" class="msg error">${esc(errText(err))}</td></tr>`;
    }
  }

  loadHistory();
})();
