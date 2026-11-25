# Vision Action Platform — 버튼별 파이프라인 코드 따라가기

> 버튼 하나를 누르면 **어느 파일의 어느 함수로 넘어가는지** 순서대로, 실제 코드(파일 경로 · 줄 번호)로 따라갑니다.  
> 줄 번호는 GitHub `Jihoo2/vision_action_platform` main 기준. VS Code에서 `Ctrl+P` → 파일, `Ctrl+G` → 줄 번호.

## 목차

- [분석 · AI 분석 시작 (업로드)](#ai)
- [분석 · IP Webcam 분석](#ipcam)
- [분석 · 자세 판정 (팀 모델)](#form)
- [분석 · 분석 이력 · 행 클릭](#history)
- [관리 · 대시보드](#dash)
- [관리 · Admin](#admin)
- [계정 · 로그인](#login)
- [계정 · 회원가입](#signup)
- [계정 · 내 정보](#me)
- [계정 · 로그아웃](#logout)


---

<a id="ai"></a>
## 분석 · AI 분석 시작 (업로드)

**흐름:** 화면설계 (UI) → AI 분석 버튼 → JavaScript 요청 → HTTP fetch → Django 요청 받기 → 프로젝트 urls.py → 앱 urls.py → views.py 저장 → 동기 / 비동기 → Celery 작업 등록 → tasks.py 실행 → services.py 호출 → FastAPI 받기 → 추론 (Random Forest) → PostgreSQL 저장 → JavaScript 결과 표시

### ① 화면설계 (UI)

📄 `backend/templates/analyses/index.html` · **analyses/index.html 화면** · 10번째 줄  
🔁 넘기는 방식: Django 템플릿 → HTML 화면

사용자가 무엇을 누르고 어디서 결과를 보는지 먼저 화면을 설계했습니다. 분석 종류(동작 인식·자세 판정), 입력(업로드·웹캠), AI 분석 버튼, 진행 단계, 결과 표, 이력 표로 나눴습니다.

```html
  <div class="tabs task-tabs">
    <button type="button" class="tab active" data-task="ACTION">동작 인식 (6개 동작)</button>
    <button type="button" class="tab" data-task="FORM">자세 판정 (팀 모델)</button>
  </div>
  <div class="tabs">
    <button type="button" class="tab active" data-tab="UPLOAD">영상 업로드</button>
    <button type="button" class="tab" data-tab="IPCAM">IP Webcam</button>
  </div>

  <form id="analyze-form" class="form" enctype="multipart/form-data">
    {% csrf_token %}
    <input type="hidden" name="input_type" id="input_type" value="UPLOAD">
    <input type="hidden" name="task_type" id="task_type" value="ACTION">
…
    <button type="submit" id="start-btn" class="btn-lg">AI 분석 시작</button>
  </form>
…
<section class="card" id="result-card">
  <h1>분석 결과 <span id="job-label" class="muted"></span></h1>
  <div class="steps" id="steps">
    <div class="step" data-step="PENDING">대기</div>
    <div class="step" data-step="PROCESSING" id="step-processing">처리 중</div>
    <div class="step" data-step="COMPLETED">완료</div>
    <div class="step" data-step="FAILED">실패</div>
  </div>
  <div id="status-msg" class="muted">분석을 시작하면 여기에 진행 상태와 결과가 표시됩니다.</div>
  <div id="result-body"></div>
…
  <tbody id="history"><tr><td colspan="10" class="empty">불러오는 중…</td></tr></tbody>
```

➡️ 여기서 부르는 것: `AI 분석 시작 버튼` (index.html:19) · `분석 종류 탭 (동작 인식 / 자세 판정)` (analyses.js:43) · `입력 방식 탭 (업로드 / IP Webcam)` (analyses.js:60)

### ② AI 분석 버튼

📄 `backend/templates/analyses/index.html` · **AI 분석 시작 버튼** · 19번째 줄  
🔁 넘기는 방식: 클릭 → 폼 submit 이벤트

사용자가 [AI 분석 시작] 버튼을 누릅니다.

```html
<form id="analyze-form" class="form" enctype="multipart/form-data">
  {% csrf_token %}
  <input type="hidden" name="input_type" id="input_type" value="UPLOAD">
  <input type="hidden" name="task_type" id="task_type" value="ACTION">
  …
  <button type="submit" id="start-btn" class="btn-lg">AI 분석 시작</button>
</form>
```

➡️ 여기서 부르는 것: `form submit 핸들러` (analyses.js:69)

### ③ JavaScript 요청

📄 `backend/static/js/analyses.js` · **form submit 핸들러** · 69번째 줄  
🔁 넘기는 방식: 함수 호출 api(API, {method:"POST"})

버튼을 누르면 JavaScript 가 기본 새로고침을 막고 영상과 선택값을 FormData 로 묶어 api() 에 넘깁니다. 요청 중에는 버튼을 잠급니다.

```javascript
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const kind = $("#input_type").value;
  const task = $("#task_type").value;
  const fd = new FormData();
  fd.append("input_type", kind);
  fd.append("task_type", task);
  ["expected_action", "title"].forEach((k) => fd.append(k, form.elements[k].value));
  if (task === "FORM") {
    fd.append("exercise", form.elements.exercise.value);
    fd.append("camera_view", form.elements.camera_view.value);
  }
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
    $("#video").value = ""; $("#title").value = "";        // 분석 종류·동작 선택은 그대로 둠
  } catch (err) {
    showMessage(errText(err), true);
  } finally {
    startBtn.disabled = false;
    startBtn.textContent = $("#task_type").value === "FORM" ? "자세 판정 시작" : "AI 분석 시작";
  }
});
```

➡️ 여기서 부르는 것: `api()` (analyses.js:21) · `showMessage()` (analyses.js:142) · `errText()` (analyses.js:33) · `showJob()` (analyses.js:149) · `startPolling()` (analyses.js:106)

### ④ HTTP fetch

📄 `backend/static/js/analyses.js` · **api()** · 21번째 줄  
🔁 넘기는 방식: HTTP POST /api/v1/analyses/ + X-CSRFToken

모든 요청이 지나는 공통 통로 api() 가 fetch 로 Django 서버에 POST 를 보냅니다. 쿠키의 CSRF 토큰을 헤더에 넣고, 오류(400 등)면 throw 합니다.

```javascript
async function api(url, opts = {}) {
  const res = await fetch(url, { credentials: "same-origin", ...opts,
    headers: { "X-CSRFToken": csrf(), Accept: "application/json", ...(opts.headers || {}) } });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error("API 오류"), { status: res.status, data });
  return data;
}
```

➡️ 여기서 부르는 것: `csrf()` (analyses.js:17) · `ROOT_URLCONF · MIDDLEWARE` (settings.py:36)

### ⑤ Django 요청 받기

📄 `backend/config/settings.py` · **ROOT_URLCONF · MIDDLEWARE** · 36번째 줄  
🔁 넘기는 방식: 세션 로그인 · CSRF 검사 → 주소 찾기 시작

Django 가 요청을 받으면 미들웨어가 로그인 세션과 CSRF 토큰을 확인하고, ROOT_URLCONF 에 적힌 config/urls.py 부터 주소를 찾습니다.

```python
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
```

➡️ 여기서 부르는 것: `프로젝트 urls.py` (urls.py:7)

### ⑥ 프로젝트 urls.py

📄 `backend/config/urls.py` · **프로젝트 urls.py** · 7번째 줄  
🔁 넘기는 방식: 주소 → 앱 urls.py 로 넘김

Django 가 받은 주소를 프로젝트 urls.py 에서 보고, analyses 앱의 urls.py 로 넘깁니다.

```python
urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),                  # signup/, me/
    path("accounts/", include("django.contrib.auth.urls")),       # login/, logout/ ...
    path("", include("analyses.urls")),                           # api/v1/analyses/, analyses/, dashboard/
    path("api-auth/", include("rest_framework.urls")),            # Browsable API 로그인
    path("", RedirectView.as_view(pattern_name="analyses_index", permanent=False), name="home"),
]
```

➡️ 여기서 부르는 것: `앱 urls.py (analyses)` (urls.py:7) · `앱 urls.py (accounts)` (urls.py:5) · `admin.site.urls (Django 기본)` (urls.py:8) · `LoginView (Django 기본)` (urls.py:10)

### ⑦ 앱 urls.py

📄 `backend/analyses/urls.py` · **앱 urls.py (analyses)** · 7번째 줄  
🔁 넘기는 방식: 주소 → views.py 로 연결

앱 urls.py 가 api/v1/analyses/ 주소를 views.py 의 AnalysisJobViewSet 에 연결합니다. POST 요청이면 create 함수가 실행됩니다.

```python
router = DefaultRouter()
router.register("analyses", AnalysisJobViewSet, basename="analysis")

urlpatterns = [
    path("api/v1/", include(router.urls)),
    path("analyses/", page_views.analyses_index, name="analyses_index"),
    path("dashboard/", page_views.dashboard, name="dashboard"),
]
```

➡️ 여기서 부르는 것: `AnalysisJobViewSet.create` (views.py:48) · `job_status (@action)` (views.py:70) · `list / retrieve (DRF 기본)` (views.py:33) · `analyses_index (화면 뷰)` (page_views.py:21) · `dashboard 뷰` (page_views.py:43)

### ⑧ views.py 저장

📄 `backend/analyses/views.py` · **AnalysisJobViewSet.create** · 48번째 줄  
🔁 넘기는 방식: DB 에 PENDING 저장

입력을 검사하고, 분석 작업을 DB 에 '대기(PENDING)' 상태로 저장합니다.

```python
def create(self, request, *args, **kwargs):
    serializer = self.get_serializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    job = serializer.save(user=request.user)            # status = PENDING
    # DB 커밋이 끝난 뒤에 Celery 작업 등록 → Worker가 아직 없는 Job을 찾는 일이 없음
    transaction.on_commit(lambda: enqueue_analysis(job.pk))
    return Response(AnalysisJobSerializer(job, context={"request": request}).data,
                    status=http_status.HTTP_201_CREATED)
```

➡️ 여기서 부르는 것: `AnalysisJobCreateSerializer.validate` (serializers.py:80) · `enqueue_analysis` (views.py:90)

### ⑨ 동기 / 비동기

📄 `backend/analyses/views.py` · **AnalysisJobViewSet.create** · 48번째 줄  
🔁 넘기는 방식: 사용자에게는 바로 응답 (동기) · AI 는 뒤에서 (비동기)

AI 분석은 몇 초 걸리므로 기다리게 하지 않습니다. 사용자에게는 '접수됐다'고 바로 응답(동기)하고, AI 분석은 Celery 에 맡깁니다(비동기).

```python
job = serializer.save(user=request.user)            # status = PENDING
# DB 커밋이 끝난 뒤에 Celery 작업 등록 → Worker가 아직 없는 Job을 찾는 일이 없음
transaction.on_commit(lambda: enqueue_analysis(job.pk))
return Response(AnalysisJobSerializer(job, context={"request": request}).data,
                status=http_status.HTTP_201_CREATED)
```

### ⑩ Celery 작업 등록

📄 `backend/analyses/views.py` · **enqueue_analysis** · 90번째 줄  
🔁 넘기는 방식: Redis 대기열에 job_id 넣기

작업 번호(job_id)만 Redis 대기열에 넣습니다. 영상은 보내지 않고 파일로 저장돼 있습니다.

```python
def enqueue_analysis(job_id: int) -> None:
    """Redis 대기열에 작업 등록. Redis가 꺼져 있으면 FAILED 로 남겨 사용자가 알 수 있게 함"""
    try:
        result = run_analysis.delay(job_id)
        AnalysisJob.objects.filter(pk=job_id).update(celery_task_id=str(result.id))
    except Exception as e:  # noqa: BLE001
        log.exception("작업 등록 실패 job=%s", job_id)
        AnalysisJob.objects.filter(pk=job_id).update(
            status=AnalysisJob.Status.FAILED, finished_at=timezone.now(),
            error_message=f"작업 대기열(Redis)에 연결할 수 없습니다: {e.__class__.__name__}")
```

➡️ 여기서 부르는 것: `run_analysis` (tasks.py:41)

### ⑪ tasks.py 실행

📄 `backend/analyses/tasks.py` · **run_analysis** · 41번째 줄  
🔁 넘기는 방식: Celery Worker 가 꺼내서 실행

Celery Worker 가 대기열에서 작업을 꺼내 상태를 '처리 중'으로 바꾸고, 분석할 영상 경로를 준비합니다.

```python
@shared_task(bind=True)
def run_analysis(self, job_id: int):
    # ① 같은 작업이 두 번 실행되지 않도록 PENDING 일 때만 PROCESSING 으로 바꿈
    updated = AnalysisJob.objects.filter(pk=job_id, status=AnalysisJob.Status.PENDING).update(
        status=AnalysisJob.Status.PROCESSING, started_at=timezone.now(),
        celery_task_id=self.request.id or "")
    if not updated:
        log.warning("Job %s: PENDING 상태가 아니어서 건너뜀", job_id)
        return {"job_id": job_id, "skipped": True}

    job = AnalysisJob.objects.get(pk=job_id)
    log.info("Job %s 처리 시작 (%s · %s)", job_id, job.task_type, job.input_type)
    try:
        video_path = _acquire_video(job)                # ② 영상 확보
        # ③ 어느 AI 서버로 보낼지 — 분석 종류(task_type) 하나로 결정
        if job.task_type == AnalysisJob.TaskType.FORM:      # 팀 자세 판정 (form_service)
            result = judge_form(video_path, job.exercise, job.camera_view)
        else:                                               # 6개 동작 인식 (ai_service)
            result = predict_video(video_path)
    except (CameraError, AIInputError, AIServiceError) as e:
        return _fail(job, str(e))
    except Exception as e:  # noqa: BLE001  예상 못 한 오류도 FAILED 로 남김
        log.exception("Job %s 예외", job_id)
        return _fail(job, f"처리 중 오류: {e.__class__.__name__}: {e}")

    # ③ 결과 저장 — 저장 모양만 다르고, 완료 처리는 _complete() 한 곳
    if job.task_type == AnalysisJob.TaskType.FORM:
        return _save_reps(job, result)
    return _save_predictions(job, result)
```

➡️ 여기서 부르는 것: `_acquire_video` (tasks.py:31) · `predict_video (services)` (services.py:24) · `judge_form (services)` (services.py:30) · `_save_predictions` (tasks.py:72) · `_save_reps` (tasks.py:92) · `_fail` (tasks.py:130)

### ⑫ services.py 호출

📄 `backend/analyses/services.py` · **predict_video (services)** · 24번째 줄  
🔁 넘기는 방식: HTTP POST → FastAPI :8001

영상을 AI 서버(FastAPI)로 보내고 결과(JSON)를 받습니다.

```python
def predict_video(video_path: str) -> dict:
    """6개 동작 인식 (ai_service)"""
    url = f"{settings.FASTAPI_URL.rstrip('/')}/api/v1/predict/"
    return _post(url, video_path, settings.FASTAPI_TIMEOUT_SEC, "AI 서버")
```

➡️ 여기서 부르는 것: `_post` (services.py:37)

### ⑬ FastAPI 받기

📄 `ai_service/routers/predictions.py` · **predict (POST /api/v1/predict/)** · 42번째 줄  
🔁 넘기는 방식: 영상 받기 → AI 분석 함수 호출

AI 서버가 영상을 받아 분석 함수를 실행합니다. 모델은 서버가 켜질 때 한 번만 불러 둡니다.

```python
@router.post("/predict/")
async def predict(file: UploadFile = File(..., description="분석할 영상 (mp4 권장)")):
    bundle = get_bundle()
    if bundle is None or not bundle.ready:
        raise HTTPException(503, "모델이 준비되지 않았습니다.")

    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"지원하지 않는 형식입니다: {ext or '(확장자 없음)'} — {sorted(ALLOWED_EXT)}")

    started = time.perf_counter()
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
    try:
        video, result = await run_in_threadpool(_analyze, tmp_path)
    # …
    return {
        "ok": True,
        "filename": file.filename,
        "video": {"frames": video.frames, "fps": round(video.fps, 2),
                  "duration_sec": round(video.duration_sec, 2),
                  "width": video.width, "height": video.height},
        "model": {"name": "rf_action_baseline", "classes": bundle.classes,
                  "sequence_steps": bundle.sequence_steps, "method": "clip"},
        **result,
        "processing_time_sec": round(time.perf_counter() - started, 2),
    }
```

➡️ 여기서 부르는 것: `_analyze` (predictions.py:36)

### ⑭ 추론 (Random Forest)

📄 `ai_service/services/action_inference.py` · **predict_track (Random Forest)** · 35번째 줄  
🔁 넘기는 방식: 함수 호출

먼저 YOLO Pose 로 사람마다 관절을 찾고(전처리), 30 Step × 38 특징 = 1140 개로 만들어 Random Forest 가 6개 동작 중 하나를 추론합니다. 1·2위 차이가 5% 미만이면 '판단 불확실'입니다.

```python
def predict_track(series: TrackSeries, bundle: ModelBundle) -> dict | None:
    valid = [(t, f) for t, f in zip(series.times, series.features) if f is not None]
    min_valid_frames = int(bundle.training_info.get("min_valid_frames", 10))
    if len(valid) < min_valid_frames:
        return None

    span = valid[-1][0] - valid[0][0] + 1.0
    buf = TimedFeatureBuffer(window_seconds=span)
    for t, f in valid:
        buf.append(t, f)

    # 7일차 함수 재사용 — 첫 반환값(0.55 기준 라벨)은 쓰지 않고, 불확실 판단은 아래 margin 하나로 함
    _, raw_label, conf, probs = predict_from_window(
        bundle.rf, buf, bundle.sequence_steps,
        bundle.realtime.get("confidence_threshold", 0.55),
    )
    probs = np.asarray(probs, dtype=float)
    order = np.argsort(-probs, kind="stable")
    second = int(order[1]) if order[0] == int(np.argmax(probs)) else int(order[0])
    margin = float(conf - probs[second])
    classes = bundle.classes
    return {
        "track_id": series.track_id,
        "action_label": raw_label,
        "confidence": round(float(conf), 4),
        "second_label": classes[second],
        "second_confidence": round(float(probs[second]), 4),
        "margin": round(margin, 4),
        "uncertain": margin < UNCERTAIN_MARGIN,
```

➡️ 여기서 부르는 것: `predict_from_window` (realtime_utils.py:436)

### ⑮ PostgreSQL 저장

📄 `backend/analyses/tasks.py` · **_save_predictions** · 72번째 줄  
🔁 넘기는 방식: DB 저장 · COMPLETED

Celery 가 받은 결과를 Django ORM 으로 PostgreSQL 에 저장하고 상태를 '완료(COMPLETED)'로 바꿉니다. FastAPI 는 DB 에 직접 저장하지 않습니다.

```python
def _save_predictions(job: AnalysisJob, result: dict) -> dict:
    """동작 인식(ai_service) 결과 → 사람별 PersonPrediction"""
    with transaction.atomic():
        job.predictions.all().delete()                  # 재실행돼도 중복 없음
        PersonPrediction.objects.bulk_create([
            PersonPrediction(
                job=job,
                extra={k: v for k, v in p.items() if k not in PRED_FIELDS},   # probabilities 등
                **{k: p.get(k) for k in PRED_FIELDS if p.get(k) is not None})
            for p in result.get("predictions", [])
        ])
        _complete(job, result,
                  extra={"schema": "action.v1", "video": result.get("video"),
                         "skipped_tracks": result.get("skipped_tracks", []), "model": result.get("model")},
                  duration=(result.get("video") or {}).get("duration_sec"))
    n = job.predictions.count()
    log.info("Job %s 완료: 예측 %d건", job.pk, n)
    return {"job_id": job.pk, "status": job.status, "predictions": n}
```

➡️ 여기서 부르는 것: `_complete` (tasks.py:117)

### ⑯ JavaScript 결과 표시

📄 `backend/static/js/analyses.js` · **startPolling()** · 106번째 줄  
🔁 넘기는 방식: 1초마다 GET → 결과 그리기

화면은 1초마다 상태를 물어보다가, 완료되면 결과 표와 영상을 보여 줍니다.

```javascript
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
```

➡️ 여기서 부르는 것: `api()` (analyses.js:21) · `setSteps()` (analyses.js:130) · `showMessage()` (analyses.js:142) · `showJob()` (analyses.js:149)

#### 🌳 호출 따라가기 (함수 → 부르는 함수 → 또 부르는 함수)

```text
form submit 핸들러  (backend/static/js/analyses.js:69)
    └─ api()  (backend/static/js/analyses.js:21)
        └─ csrf()  (backend/static/js/analyses.js:17)
        └─ ROOT_URLCONF · MIDDLEWARE  (backend/config/settings.py:36)
            └─ 프로젝트 urls.py  (backend/config/urls.py:7)
                └─ 앱 urls.py (analyses)  (backend/analyses/urls.py:7)
                    └─ AnalysisJobViewSet.create  (backend/analyses/views.py:48)
                        └─ AnalysisJobCreateSerializer.validate  (backend/analyses/serializers.py:80)
                            └─ validate_video  (backend/analyses/serializers.py:69)
                        └─ enqueue_analysis  (backend/analyses/views.py:90)
                            └─ run_analysis  (backend/analyses/tasks.py:41)
                                └─ _acquire_video  (backend/analyses/tasks.py:31)
                                    └─ capture_clip  (backend/analyses/camera_capture.py:36)
                                        └─ _retime  (backend/analyses/camera_capture.py:101)
                                        └─ to_h264  (backend/analyses/camera_capture.py:135)
                                └─ predict_video (services)  (backend/analyses/services.py:24)
                                    └─ _post  (backend/analyses/services.py:37)
                                        └─ predict (POST /api/v1/predict/)  (ai_service/routers/predictions.py:42)
                                            └─ _analyze  (ai_service/routers/predictions.py:36)
                                                └─ extract_tracks (YOLO Pose + ByteTrack)  (ai_service/services/pose_pipeline.py:61)
                                                    └─ feature_from_keypoints  (ai_service/src/multi_person_utils.py:126)
                                                └─ predict_video (사람별 거르기)  (ai_service/services/action_inference.py:72)
                                                    └─ predict_track (Random Forest)  (ai_service/services/action_inference.py:35)
                                                        └─ predict_from_window  (ai_service/src/realtime_utils.py:436)
                                        └─ judge (POST /api/v1/judge/)  (form_service/main.py:40)
                                            └─ TeamEngine.judge_video  (form_service/engine.py:96)
                                                └─ predict_pose  (form_service/engine.py:85)
                                └─ judge_form (services)  (backend/analyses/services.py:30)
                                    └─ _post  (backend/analyses/services.py:37)  ↑위에 나옴
                                └─ _save_predictions  (backend/analyses/tasks.py:72)
                                    └─ _complete  (backend/analyses/tasks.py:117)
                                └─ _save_reps  (backend/analyses/tasks.py:92)
                                    └─ _complete  (backend/analyses/tasks.py:117)  ↑위에 나옴
                                └─ _fail  (backend/analyses/tasks.py:130)
    └─ showMessage()  (backend/static/js/analyses.js:142)
    └─ errText()  (backend/static/js/analyses.js:33)
    └─ showJob()  (backend/static/js/analyses.js:149)
        └─ setSteps()  (backend/static/js/analyses.js:130)
        └─ showMessage()  (backend/static/js/analyses.js:142)  ↑위에 나옴
        └─ formResult()  (backend/static/js/analyses.js:198)
    └─ startPolling()  (backend/static/js/analyses.js:106)
        └─ api()  (backend/static/js/analyses.js:21)  ↑위에 나옴
        └─ setSteps()  (backend/static/js/analyses.js:130)  ↑위에 나옴
        └─ showMessage()  (backend/static/js/analyses.js:142)  ↑위에 나옴
        └─ showJob()  (backend/static/js/analyses.js:149)  ↑위에 나옴
```

#### 🔎 호출의 호출 — 위 단계에서 부르는 함수들의 코드

<details><summary><b>csrf()</b> — <code>backend/static/js/analyses.js:17</code> · 쿠키(csrftoken)에서 CSRF 토큰을 꺼냄 → X-CSRFToken 헤더</summary>

```javascript
function csrf() {
  const m = document.cookie.match(/csrftoken=([^;]+)/);
  return m ? m[1] : form.querySelector("[name=csrfmiddlewaretoken]").value;
}
```
</details>

<details><summary><b>AnalysisJobCreateSerializer.validate</b> — <code>backend/analyses/serializers.py:80</code> · 분석 종류·입력 방식별 검사: 자세 판정 동작, 영상 필수, 카메라 허용 목록(SSRF 방지), 수집 시간</summary>

```python
def validate(self, attrs):
    task = attrs.get("task_type") or AnalysisJob.TaskType.ACTION
    attrs["task_type"] = task
    if task == AnalysisJob.TaskType.FORM:      # 팀 자세 판정: 판정할 동작이 꼭 필요
        if attrs.get("exercise") not in Exercise.values:
            raise serializers.ValidationError({"exercise": "자세 판정할 동작(버피·런지·스쿼트 점프)을 선택하세요."})
        attrs["expected_action"] = ""
    else:
        attrs["exercise"] = ""
        attrs["camera_view"] = AnalysisJob.CameraView.AUTO
    max_sec = settings.FORM_CAPTURE_MAX_SECONDS if task == AnalysisJob.TaskType.FORM else 15
    kind = attrs.get("input_type")
    if kind == AnalysisJob.InputType.UPLOAD:
        if not attrs.get("video"):
            raise serializers.ValidationError({"video": "영상 업로드 방식은 영상 파일이 필요합니다."})
        attrs["camera_url"] = ""
        attrs["capture_seconds"] = None
    elif kind == AnalysisJob.InputType.IPCAM:
        if attrs.get("video"):
            raise serializers.ValidationError({"video": "IP Webcam 방식에서는 파일을 올리지 않습니다."})
        allowed = settings.ALLOWED_CAMERA_URLS
        url = (attrs.get("camera_url") or "").strip() or (allowed[0] if len(allowed) == 1 else "")
        if url not in allowed:   # 임의의 외부 URL을 서버가 호출하지 않도록 허용 목록만 통과
            raise serializers.ValidationError({"camera_url": "허용되지 않은 카메라 주소입니다."})
        attrs["camera_url"] = url
        sec = attrs.get("capture_seconds") or settings.CAMERA_CAPTURE_SECONDS
        if not 3 <= sec <= max_sec:    # 자세 판정은 여러 회차를 봐야 해서 더 길게 허용
            raise serializers.ValidationError({"capture_seconds": f"수집 시간은 3~{max_sec}초입니다."})
        attrs["capture_seconds"] = sec
    return attrs
```
</details>

<details><summary><b>validate_video</b> — <code>backend/analyses/serializers.py:69</code> · 확장자·용량 검사</summary>

```python
def validate_video(self, f):
    if f is None:
        return f
    ext = Path(f.name).suffix.lower()
    if ext not in settings.ALLOWED_VIDEO_EXTENSIONS:
        raise serializers.ValidationError(
            f"지원하지 않는 형식입니다({ext or '확장자 없음'}). 허용: {', '.join(settings.ALLOWED_VIDEO_EXTENSIONS)}")
    if f.size > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise serializers.ValidationError(f"파일이 너무 큽니다. 최대 {settings.MAX_UPLOAD_MB}MB")
    return f
```
</details>

<details><summary><b>_acquire_video</b> — <code>backend/analyses/tasks.py:31</code> · 업로드면 파일 경로, IP Webcam 이면 여기서 N초 수집</summary>

```python
def _acquire_video(job: AnalysisJob) -> str:
    """분석할 영상의 실제 경로. IP Webcam이면 여기서 N초 수집 후 job.video 에 저장"""
    if job.input_type == AnalysisJob.InputType.IPCAM:
        rel_path, info = capture_clip(job.camera_url, job.capture_seconds or 8, job.pk)
        job.video.name = rel_path                       # 수집 영상도 업로드 영상처럼 경로를 DB에 기록
        job.save(update_fields=["video"])
        log.info("Job %s 카메라 수집 완료: %s", job.pk, info)
    return job.video.path
```
</details>

<details><summary><b>capture_clip</b> — <code>backend/analyses/camera_capture.py:36</code> · 허용 카메라에 연결 → N초 Frame 수집 → MP4 → 길이 보정 → H.264</summary>

```python
def capture_clip(camera_url: str, seconds: int, job_id: int) -> tuple[str, dict]:
    """카메라에서 seconds 초 동안 수집 → (media 기준 상대경로, 수집 정보)"""
    if camera_url not in settings.ALLOWED_CAMERA_URLS:
        raise CameraError("허용되지 않은 카메라 주소입니다.")

    cap = cv2.VideoCapture(camera_url, cv2.CAP_FFMPEG,
                           [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, OPEN_TIMEOUT_MS,
                            cv2.CAP_PROP_READ_TIMEOUT_MSEC, OPEN_TIMEOUT_MS])
    if not cap.isOpened():
        raise CameraError("IP Webcam에 연결할 수 없습니다. 휴대폰 앱의 서버 실행·같은 Wi-Fi·주소를 확인하세요.")

    rel = Path("captures") / datetime.now().strftime("%Y/%m/%d") / f"job{job_id}_{datetime.now():%H%M%S}.mp4"
    out_path = Path(settings.MEDIA_ROOT) / rel
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # stream_fps : 카메라가 알려 준 값 그대로 (MJPEG 스트림은 0 을 주는 경우가 많음)
    # write_fps  : 파일을 처음 쓸 때 쓰는 값 — 알려 주지 않으면 임시로 15
    stream_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    write_fps = stream_fps if 1 <= stream_fps <= 60 else 15.0
    writer = None
    frames, fails = 0, 0
    started = time.monotonic()
    try:
        while time.monotonic() - started < seconds:
            ok, frame = cap.read()
    # …
    elapsed = time.monotonic() - started
    if frames < MIN_FRAMES:
        out_path.unlink(missing_ok=True)
        raise CameraError(f"수집된 Frame이 너무 적습니다 ({frames}개 / {elapsed:.1f}초).")

    # 처음 쓴 FPS(write_fps)와 실제 수신 속도(measured_fps)가 다르면 영상 길이가 틀어짐
    # (예: 8초 수집인데 19초짜리 파일) → 실제 측정 FPS로 다시 기록
    measured_fps = frames / elapsed if elapsed else write_fps
    measured_fps = min(max(measured_fps, 1.0), 120.0)   # 비정상 값 방지
    if abs(measured_fps - write_fps) > 1.0:
        _retime(out_path, measured_fps, max_frames=frames)
    codec = "h264" if to_h264(out_path) else "mp4v"
    return str(rel), {"frames": frames, "seconds": round(elapsed, 2),
                      "measured_fps": round(measured_fps, 2), "stream_fps": stream_fps,
                      "write_fps": write_fps,
                      "codec": codec}
```
</details>

<details><summary><b>_retime</b> — <code>backend/analyses/camera_capture.py:101</code> · 실제 받은 FPS 로 다시 기록 (max_frames 로 무한 루프 방지)</summary>

```python
def _retime(path: Path, fps: float, max_frames: int) -> None:
    """같은 Frame을 올바른 FPS로 다시 써서 영상 길이를 실제 수집 시간과 맞춤

    max_frames: 방금 저장한 Frame 수. 이만큼만 다시 읽어 무한 루프를 막음
    """
    tmp = path.with_suffix(".retime.mp4")
    src = cv2.VideoCapture(str(path))
    w = int(src.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(src.get(cv2.CAP_PROP_FRAME_HEIGHT))
    dst = cv2.VideoWriter(str(tmp), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    try:
        for _ in range(max_frames):
            ok, frame = src.read()
            if not ok:
                break
            dst.write(frame)
    finally:
        src.release()
        dst.release()
    tmp.replace(path)
```
</details>

<details><summary><b>to_h264</b> — <code>backend/analyses/camera_capture.py:135</code> · ffmpeg 로 브라우저 재생 가능한 H.264 변환</summary>

```python
def to_h264(path: Path) -> bool:
    """OpenCV 가 쓴 mp4v(MPEG-4 Part 2) 영상을 브라우저가 재생하는 H.264 로 변환

    - Chrome/Edge 의 <video> 는 mp4v 를 재생하지 못함 (0:00 에서 멈춤)
    - pip 의 opencv-python-headless 에는 H.264 인코더가 없어서 ffmpeg 로 변환
    - +faststart: 파일 앞쪽에 색인을 두어 내려받는 중에도 바로 재생
    - ffmpeg 가 없거나 실패하면 원본(mp4v)을 그대로 둠 → 분석에는 영향 없음
    """
    if not shutil.which("ffmpeg"):
        logger.warning("ffmpeg 가 없어 H.264 변환을 건너뜀: %s", path)
        return False
    tmp = path.with_suffix(".h264.mp4")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(path),
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
             "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", str(tmp)],
            check=True, capture_output=True, timeout=120,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        logger.warning("H.264 변환 실패 (%s): %s", path, exc)
```
</details>

<details><summary><b>_post</b> — <code>backend/analyses/services.py:37</code> · httpx 로 영상 전송, 오류 코드를 입력 오류 / 서버 오류로 나눔</summary>

```python
def _post(url: str, video_path: str, timeout: float, who: str, data: dict | None = None) -> dict:
    path = Path(video_path)
    try:
        with path.open("rb") as f:
            res = httpx.post(url, files={"file": (path.name, f, "video/mp4")}, data=data or {},
                             timeout=timeout)
    except FileNotFoundError as e:
        raise AIInputError("분석할 영상 파일을 찾을 수 없습니다.") from e
    except httpx.TimeoutException as e:
        raise AIServiceError(f"{who} 응답 시간 초과 ({timeout:.0f}초)") from e
    except httpx.HTTPError as e:
        raise AIServiceError(f"{who}에 연결할 수 없습니다: {e.__class__.__name__}") from e

    if res.status_code in (400, 422):
        raise AIInputError(_detail(res))
    if res.status_code >= 400:
        raise AIServiceError(f"{who} 오류 {res.status_code}: {_detail(res)}")
    return res.json()
```
</details>

<details><summary><b>_analyze</b> — <code>ai_service/routers/predictions.py:36</code> · 모델 묶음 → 관절 추출 → 사람별 추론</summary>

```python
def _analyze(path: str):
    bundle = get_bundle()
    video = extract_tracks(path, bundle, max_seconds=MAX_DURATION_SEC)
    return video, predict_video(video, bundle)
```
</details>

<details><summary><b>extract_tracks (YOLO Pose + ByteTrack)</b> — <code>ai_service/services/pose_pipeline.py:61</code> · Frame 마다 사람 추적 → Track ID 별 관절 → 38 특징</summary>

```python
def extract_tracks(video_path: str, bundle: ModelBundle, max_seconds: float | None = None) -> VideoResult:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise VideoReadError("영상을 열 수 없습니다. 손상되었거나 지원하지 않는 형식입니다.")
    fps = float(cap.get(cv2.CAP_PROP_FPS)) or 0.0
    # …
    with _track_lock:
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                now = frame_id / fps
                if max_seconds and now > max_seconds:
                    break
                # 첫 Frame은 persist=False 로 추적기를 새로 만들어 이전 영상의 ID가 이어지지 않게 함
                res = bundle.pose.track(
                    source=frame, persist=frame_id > 0,
                    tracker=bundle.multi_person.get("tracker", "bytetrack.yaml"),
                    imgsz=int(cfg.get("image_size", 640)),
                    conf=float(cfg.get("person_confidence", 0.25)),
                    device=bundle.device, verbose=False,
                )[0]
                boxes, kps = res.boxes, res.keypoints
                if boxes is not None and len(boxes) and boxes.id is not None and kps is not None:
                    ids = boxes.id.detach().cpu().numpy().astype(int)
                    bconf = boxes.conf.detach().cpu().numpy()
                    xy = kps.xy.detach().cpu().numpy()
                    kconf = kps.conf.detach().cpu().numpy() if kps.conf is not None else None
                    for i in range(min(len(ids), len(xy))):
                        tid = int(ids[i])
                        s = tracks.setdefault(tid, TrackSeries(tid))
                        s.times.append(now)
                        s.features.append(feature_from_keypoints(xy[i]))
                        s.box_conf.append(float(bconf[i]))
                        if kconf is not None and i < len(kconf):
                            s.keypoint_conf.append(float(np.mean(kconf[i])))
                frame_id += 1
```
</details>

<details><summary><b>predict_video (사람별 거르기)</b> — <code>ai_service/services/action_inference.py:72</code> · 잠깐 잡힌 Track·관절 신뢰도 낮은 Track 제외 → predict_track</summary>

```python
def predict_video(result: VideoResult, bundle: ModelBundle) -> dict:
    predictions, skipped = [], []
    for tid, s in sorted(result.tracks.items()):
        if s.frames_seen < MIN_SEEN_FRAMES:
            skipped.append({"track_id": tid, "frames_seen": s.frames_seen,
                            "reason": f"{MIN_SEEN_FRAMES} Frame 미만으로 잠깐 잡힌 Track (오검출 가능)"})
            continue
        kconf = float(np.mean(s.keypoint_conf)) if s.keypoint_conf else 0.0
        if kconf < MIN_KEYPOINT_CONF:
            skipped.append({"track_id": tid, "frames_seen": s.frames_seen,
                            "mean_keypoint_conf": round(kconf, 3),
                            "reason": f"관절 신뢰도 평균 {kconf:.2f} < {MIN_KEYPOINT_CONF} (입력 품질 낮음)"})
            continue
        p = predict_track(s, bundle)
        if p is None:
            skipped.append({"track_id": tid, "frames_seen": s.frames_seen,
                            "reason": "유효한 관절 Feature가 부족함"})
        else:
            predictions.append(p)
```
</details>

<details><summary><b>judge (POST /api/v1/judge/)</b> — <code>form_service/main.py:40</code> · 동작·각도·확장자 검사 → 스레드에서 engine.judge_video</summary>

```python
@app.post("/api/v1/judge/")
async def judge(file: UploadFile = File(...), action: str = Form(...), view: str = Form("auto")):
    if not engine.ready:
        raise HTTPException(503, f"판정 엔진이 준비되지 않았습니다: {engine.error}")
    if action not in ACTIONS:
        raise HTTPException(400, f"판정할 수 없는 동작입니다: {action} (가능: {', '.join(ACTIONS)})")
    if view not in VIEWS:
        raise HTTPException(400, f"촬영 각도 값 오류: {view}")
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"지원하지 않는 형식입니다: {ext or '확장자 없음'}")
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        result = await run_in_threadpool(engine.judge_video, tmp_path, action, view, MAX_SECONDS)
    except VideoReadError as e:
        raise HTTPException(422, str(e)) from e
    finally:
        os.unlink(tmp_path)
    return {"ok": True, "filename": file.filename,
            "model": {"name": MODEL_NAME, "kind": "rules+form_model", "action": action},
            **result}
```
</details>

<details><summary><b>TeamEngine.judge_video</b> — <code>form_service/engine.py:96</code> · Frame 마다 한 사람 Pose → 팀 OnlineJudge.push → 회차별 OK/NG/CHECK</summary>

```python
def judge_video(self, path: str, action: str, view: str = "auto", max_seconds: float = 120.0) -> dict:
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise VideoReadError("영상을 열 수 없습니다. 손상되었거나 지원하지 않는 형식입니다.")
    fps = cap.get(cv2.CAP_PROP_FPS)
    fps = fps if fps and 5 < fps < 121 else 30.0
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    judge = self.OnlineJudge(self.cfg, action, view, self.paths, fps, "team", use_model=True)
    events, n, seen, t0 = [], 0, 0, time.time()
    with self.lock:                                       # YOLO 는 한 번에 하나씩
        while n < int(max_seconds * fps):
            ok, frame = cap.read()
            if not ok:
                break
            n += 1
            xy, conf = self.predict_pose(frame)
            seen += int(np.isfinite(xy).any())
            events += judge.push(n, (n - 1) / fps, xy, conf)
        cap.release()
        events += judge.flush()
    if n == 0:
        raise VideoReadError("영상에서 Frame을 읽지 못했습니다.")
    return finalize(judge, events, action, view, fps, n, seen, w, h, time.time() - t0)
```
</details>

<details><summary><b>predict_pose</b> — <code>form_service/engine.py:85</code> · 가장 확실한 한 사람의 17개 관절만</summary>

```python
def predict_pose(self, frame) -> tuple[np.ndarray, np.ndarray]:
    r = self.pose.predict(source=frame, imgsz=self.pose_cfg.get("image_size", 640),
                          conf=self.pose_cfg.get("person_confidence", 0.25),
                          device=self.device, verbose=False)[0]
    xy, conf = np.full((17, 2), np.nan), np.zeros(17)
    if r.boxes is not None and len(r.boxes) and r.keypoints is not None and r.keypoints.conf is not None:
        i = int(np.argmax(r.boxes.conf.cpu().numpy()))
        xy, conf = r.keypoints.xy.cpu().numpy()[i], r.keypoints.conf.cpu().numpy()[i]
    return xy, conf
```
</details>

<details><summary><b>judge_form (services)</b> — <code>backend/analyses/services.py:30</code> · 자세 판정 AI 서버 주소 + 동작·각도로 _post</summary>

```python
def judge_form(video_path: str, exercise: str, view: str = "auto") -> dict:
    """팀 자세 판정 (form_service) — 응답 코드 규칙은 predict_video 와 같음"""
    url = f"{settings.FORM_SERVICE_URL.rstrip('/')}/api/v1/judge/"
    return _post(url, video_path, settings.FORM_TIMEOUT_SEC, "자세 판정 AI 서버",
                 data={"action": exercise, "view": view or "auto"})
```
</details>

<details><summary><b>_complete</b> — <code>backend/analyses/tasks.py:117</code> · 두 AI 공통 완료 처리 → COMPLETED</summary>

```python
def _complete(job: AnalysisJob, result: dict, *, extra: dict, duration) -> None:
    """두 AI 서버 공통 완료 처리 — 모델 이름·요약·시간·COMPLETED (호출하는 쪽 트랜잭션 안에서)"""
    job.model_name = (result.get("model") or {}).get("name", "")[:50]
    job.extra = extra
    job.status = AnalysisJob.Status.COMPLETED
    job.result_message = (result.get("message") or "")[:255]
    job.error_message = ""
    job.video_duration_sec = duration
    job.processing_time_sec = result.get("processing_time_sec")
    job.finished_at = timezone.now()
    job.save()
```
</details>

<details><summary><b>_save_reps</b> — <code>backend/analyses/tasks.py:92</code> · 회차별 RepJudgment bulk_create (트랜잭션)</summary>

```python
def _save_reps(job: AnalysisJob, result: dict) -> dict:
    """자세 판정(form_service) 결과 → 회차별 RepJudgment"""
    meta, summary = result.get("meta") or {}, result.get("summary") or {}
    with transaction.atomic():
        job.reps.all().delete()
        RepJudgment.objects.bulk_create([
            RepJudgment(
                job=job, seq=i, rep_label=str(e.get("rep", i))[:12], kind=e.get("kind") or "rep",
                verdict=e.get("verdict") or "CHECK",
                start_sec=e.get("start_s"), end_sec=e.get("end_s"),
                message=(e.get("message") or "")[:255],
                out_of_range=(e.get("out_of_range") or "")[:255],
                boundary=(e.get("boundary") or "")[:255],
                model_flag=bool(e.get("model_flag")), model_score=e.get("model_score"),
                extra={k: e.get(k) for k in REP_EXTRA_FIELDS if e.get(k) is not None})
            for i, e in enumerate(result.get("reps", []), start=1)
        ])
        _complete(job, result,
                  extra={"schema": "form.v1", "meta": meta, "summary": summary, "model": result.get("model")},
                  duration=meta.get("duration_sec"))
    n = job.reps.count()
    log.info("Job %s 자세 판정 완료: %d건 %s", job.pk, n, summary)
    return {"job_id": job.pk, "status": job.status, "reps": n}
```
</details>

<details><summary><b>_fail</b> — <code>backend/analyses/tasks.py:130</code> · 오류 메시지 남기고 FAILED</summary>

```python
def _fail(job: AnalysisJob, message: str):
    job.status = AnalysisJob.Status.FAILED
    job.error_message = message[:1000]
    job.finished_at = timezone.now()
    job.save(update_fields=["status", "error_message", "finished_at"])
    log.warning("Job %s 실패: %s", job.pk, message)
    return {"job_id": job.pk, "status": job.status, "error": message}
```
</details>

<details><summary><b>showMessage()</b> — <code>backend/static/js/analyses.js:142</code> · 상태 문구 / 오류 문구 한 줄 표시</summary>

```javascript
function showMessage(text, isError = false) {
  const el = $("#status-msg");
  el.textContent = text;
  el.className = isError ? "msg error" : "muted";
}
```
</details>

<details><summary><b>errText()</b> — <code>backend/static/js/analyses.js:33</code> · 서버가 준 검증 오류(400)를 한 줄 메시지로</summary>

```javascript
function errText(err) {
  const d = err.data || {};
  if (typeof d === "object") {
    const msgs = Object.entries(d).map(([k, v]) => (Array.isArray(v) ? v.join(" ") : String(v)));
    if (msgs.length) return msgs.join(" / ");
  }
  return `요청 실패 (HTTP ${err.status || "?"})`;
}
```
</details>

<details><summary><b>showJob()</b> — <code>backend/static/js/analyses.js:149</code> · 완료된 작업을 표로: 동작 인식은 사람별, 자세 판정은 formResult()</summary>

```javascript
function showJob(job) {
  currentId = job.id;
  const what = job.task_type === "FORM" ? `자세 판정 · ${EXERCISE_LABELS[job.exercise] || job.exercise}` : "동작 인식";
  $("#job-label").textContent = `#${job.id} · ${what} · ${INPUT_KO[job.input_type] || job.input_type}`;
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
  if (job.task_type === "FORM") { body.innerHTML = formResult(job); return; }
    // … predictions → Track · 예측 동작 · Confidence · 2순위 · 판단 표를 body.innerHTML 에 그림
  }
```
</details>

<details><summary><b>setSteps()</b> — <code>backend/static/js/analyses.js:130</code> · 대기 → 처리 중 → 완료/실패 단계 표시 색칠</summary>

```javascript
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
```
</details>

<details><summary><b>formResult()</b> — <code>backend/static/js/analyses.js:198</code> · 팀 모델 결과: 회차별 OK / NG / CHECK 표</summary>

```javascript
function formResult(job) {
  const s = (job.extra && job.extra.summary) || {};
  const meta = (job.extra && job.extra.meta) || {};
  const reps = job.reps || [];
  const rows = reps.map((r) => `
    <tr>
      <td>${esc(r.rep_label)}</td>
      <td><span class="badge ${VERDICT_BADGE[r.verdict] || ""}">${esc(r.verdict)}</span>
          ${r.model_flag ? '<span class="badge warn" title="이상 탐지 모델 보조 표시 (판정에는 반영 안 함)">주의</span>' : ""}</td>
    // … reps → 회차 · 판정 · 근거(checksText) 표
  }
```
</details>


---

<a id="ipcam"></a>
## 분석 · IP Webcam 분석

**흐름:** IP Webcam 탭 → 시작 → 허용 목록 검사 · PENDING → 카메라 연결 · N초 수집 → 길이 보정 · H.264 변환 → 경로 저장 → 업로드와 같은 길 → 추론 → 저장 → 화면

### W1 IP Webcam 탭 → 시작

📄 `backend/static/js/analyses.js` · **입력 방식 탭 (업로드 / IP Webcam)** · 60번째 줄  
🔁 넘기는 방식: HTTP POST · camera_url · capture_seconds

탭을 바꾸면 input_type=IPCAM 이 되고, 영상 파일 대신 허용 카메라 주소와 수집 시간(초)을 보냅니다.

```javascript
document.querySelectorAll(".tab[data-tab]").forEach((tab) => tab.addEventListener("click", () => {
  const kind = tab.dataset.tab;
  document.querySelectorAll(".tab[data-tab]").forEach((t) => t.classList.toggle("active", t === tab));
  document.querySelectorAll(".pane").forEach((p) => p.classList.toggle("active", p.dataset.pane === kind));
  $("#input_type").value = kind;
  $("#step-processing").textContent = kind === "IPCAM" ? "영상 수집·AI 분석" : "처리 중";
}));
```

### W2 허용 목록 검사 · PENDING

📄 `backend/analyses/serializers.py` · **AnalysisJobCreateSerializer.validate** · 80번째 줄  
🔁 넘기는 방식: ORM INSERT → on_commit → Redis

서버가 아무 주소나 부르지 않도록(SSRF 방지) .env 허용 목록에 있는 주소만 받고, 수집 시간은 3~15초(자세 판정 30초)만 허용합니다.

```python
def validate(self, attrs):
    task = attrs.get("task_type") or AnalysisJob.TaskType.ACTION
    attrs["task_type"] = task
    if task == AnalysisJob.TaskType.FORM:      # 팀 자세 판정: 판정할 동작이 꼭 필요
        if attrs.get("exercise") not in Exercise.values:
            raise serializers.ValidationError({"exercise": "자세 판정할 동작(버피·런지·스쿼트 점프)을 선택하세요."})
        attrs["expected_action"] = ""
    else:
        attrs["exercise"] = ""
        attrs["camera_view"] = AnalysisJob.CameraView.AUTO
    max_sec = settings.FORM_CAPTURE_MAX_SECONDS if task == AnalysisJob.TaskType.FORM else 15
    kind = attrs.get("input_type")
    if kind == AnalysisJob.InputType.UPLOAD:
        if not attrs.get("video"):
            raise serializers.ValidationError({"video": "영상 업로드 방식은 영상 파일이 필요합니다."})
        attrs["camera_url"] = ""
        attrs["capture_seconds"] = None
    elif kind == AnalysisJob.InputType.IPCAM:
        if attrs.get("video"):
            raise serializers.ValidationError({"video": "IP Webcam 방식에서는 파일을 올리지 않습니다."})
        allowed = settings.ALLOWED_CAMERA_URLS
        url = (attrs.get("camera_url") or "").strip() or (allowed[0] if len(allowed) == 1 else "")
        if url not in allowed:   # 임의의 외부 URL을 서버가 호출하지 않도록 허용 목록만 통과
            raise serializers.ValidationError({"camera_url": "허용되지 않은 카메라 주소입니다."})
        attrs["camera_url"] = url
        sec = attrs.get("capture_seconds") or settings.CAMERA_CAPTURE_SECONDS
        if not 3 <= sec <= max_sec:    # 자세 판정은 여러 회차를 봐야 해서 더 길게 허용
            raise serializers.ValidationError({"capture_seconds": f"수집 시간은 3~{max_sec}초입니다."})
        attrs["capture_seconds"] = sec
    return attrs
```

➡️ 여기서 부르는 것: `validate_video` (serializers.py:69)

### W3 카메라 연결 · N초 수집

📄 `backend/analyses/camera_capture.py` · **capture_clip** · 36번째 줄  
🔁 넘기는 방식: OpenCV VideoCapture (HTTP MJPEG 스트림)

Celery Worker 가 휴대폰 IP Webcam 에 연결해 정해진 시간 동안 Frame 을 읽어 MP4 로 씁니다. 연결 실패·끊김·Frame 부족이면 CameraError 로 FAILED.

```python
def capture_clip(camera_url: str, seconds: int, job_id: int) -> tuple[str, dict]:
    """카메라에서 seconds 초 동안 수집 → (media 기준 상대경로, 수집 정보)"""
    if camera_url not in settings.ALLOWED_CAMERA_URLS:
        raise CameraError("허용되지 않은 카메라 주소입니다.")

    cap = cv2.VideoCapture(camera_url, cv2.CAP_FFMPEG,
                           [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, OPEN_TIMEOUT_MS,
                            cv2.CAP_PROP_READ_TIMEOUT_MSEC, OPEN_TIMEOUT_MS])
    if not cap.isOpened():
        raise CameraError("IP Webcam에 연결할 수 없습니다. 휴대폰 앱의 서버 실행·같은 Wi-Fi·주소를 확인하세요.")

    rel = Path("captures") / datetime.now().strftime("%Y/%m/%d") / f"job{job_id}_{datetime.now():%H%M%S}.mp4"
    out_path = Path(settings.MEDIA_ROOT) / rel
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # stream_fps : 카메라가 알려 준 값 그대로 (MJPEG 스트림은 0 을 주는 경우가 많음)
    # write_fps  : 파일을 처음 쓸 때 쓰는 값 — 알려 주지 않으면 임시로 15
    stream_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    write_fps = stream_fps if 1 <= stream_fps <= 60 else 15.0
    writer = None
    frames, fails = 0, 0
    started = time.monotonic()
    try:
        while time.monotonic() - started < seconds:
            ok, frame = cap.read()
    # …
    elapsed = time.monotonic() - started
    if frames < MIN_FRAMES:
        out_path.unlink(missing_ok=True)
        raise CameraError(f"수집된 Frame이 너무 적습니다 ({frames}개 / {elapsed:.1f}초).")

    # 처음 쓴 FPS(write_fps)와 실제 수신 속도(measured_fps)가 다르면 영상 길이가 틀어짐
    # (예: 8초 수집인데 19초짜리 파일) → 실제 측정 FPS로 다시 기록
    measured_fps = frames / elapsed if elapsed else write_fps
    measured_fps = min(max(measured_fps, 1.0), 120.0)   # 비정상 값 방지
    if abs(measured_fps - write_fps) > 1.0:
        _retime(out_path, measured_fps, max_frames=frames)
    codec = "h264" if to_h264(out_path) else "mp4v"
    return str(rel), {"frames": frames, "seconds": round(elapsed, 2),
                      "measured_fps": round(measured_fps, 2), "stream_fps": stream_fps,
                      "write_fps": write_fps,
                      "codec": codec}
```

➡️ 여기서 부르는 것: `_retime` (camera_capture.py:101) · `to_h264` (camera_capture.py:135)

### W4 길이 보정 · H.264 변환

📄 `backend/analyses/camera_capture.py` · **_retime** · 101번째 줄  
🔁 넘기는 방식: 파일 다시 쓰기 · ffmpeg

실제 받은 속도(measured_fps)로 다시 기록해 8초가 19초로 늘어나지 않게 하고, 브라우저가 재생할 수 있게 H.264 로 바꿉니다.

```python
def _retime(path: Path, fps: float, max_frames: int) -> None:
    """같은 Frame을 올바른 FPS로 다시 써서 영상 길이를 실제 수집 시간과 맞춤

    max_frames: 방금 저장한 Frame 수. 이만큼만 다시 읽어 무한 루프를 막음
    """
    tmp = path.with_suffix(".retime.mp4")
    src = cv2.VideoCapture(str(path))
    w = int(src.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(src.get(cv2.CAP_PROP_FRAME_HEIGHT))
    dst = cv2.VideoWriter(str(tmp), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    try:
        for _ in range(max_frames):
            ok, frame = src.read()
            if not ok:
                break
            dst.write(frame)
    finally:
        src.release()
        dst.release()
    tmp.replace(path)
```

### W5 경로 저장 → 업로드와 같은 길

📄 `backend/analyses/tasks.py` · **_acquire_video** · 31번째 줄  
🔁 넘기는 방식: job.video.name 저장 → services.predict_video

수집한 파일 경로를 작업에 저장하고, 이후는 업로드 영상과 똑같이 AI 서버로 보냅니다. 추론 코드를 따로 만들지 않고 재사용합니다.

```python
def _acquire_video(job: AnalysisJob) -> str:
    """분석할 영상의 실제 경로. IP Webcam이면 여기서 N초 수집 후 job.video 에 저장"""
    if job.input_type == AnalysisJob.InputType.IPCAM:
        rel_path, info = capture_clip(job.camera_url, job.capture_seconds or 8, job.pk)
        job.video.name = rel_path                       # 수집 영상도 업로드 영상처럼 경로를 DB에 기록
        job.save(update_fields=["video"])
        log.info("Job %s 카메라 수집 완료: %s", job.pk, info)
    return job.video.path
```

➡️ 여기서 부르는 것: `capture_clip` (camera_capture.py:36)

### W6 추론 → 저장 → 화면

📄 `backend/analyses/tasks.py` · **_save_predictions** · 72번째 줄  
🔁 넘기는 방식: HTTP JSON → ORM

AI 분석(업로드) 파이프라인의 5~8단계와 같습니다. 결과 화면에서는 H.264 로 바뀐 수집 영상이 바로 재생됩니다.

```python
def _save_predictions(job: AnalysisJob, result: dict) -> dict:
    """동작 인식(ai_service) 결과 → 사람별 PersonPrediction"""
    with transaction.atomic():
        job.predictions.all().delete()                  # 재실행돼도 중복 없음
        PersonPrediction.objects.bulk_create([
            PersonPrediction(
                job=job,
                extra={k: v for k, v in p.items() if k not in PRED_FIELDS},   # probabilities 등
                **{k: p.get(k) for k in PRED_FIELDS if p.get(k) is not None})
            for p in result.get("predictions", [])
        ])
        _complete(job, result,
                  extra={"schema": "action.v1", "video": result.get("video"),
                         "skipped_tracks": result.get("skipped_tracks", []), "model": result.get("model")},
                  duration=(result.get("video") or {}).get("duration_sec"))
    n = job.predictions.count()
    log.info("Job %s 완료: 예측 %d건", job.pk, n)
    return {"job_id": job.pk, "status": job.status, "predictions": n}
```

➡️ 여기서 부르는 것: `_complete` (tasks.py:117)

#### 🌳 호출 따라가기 (함수 → 부르는 함수 → 또 부르는 함수)

```text
form submit 핸들러  (backend/static/js/analyses.js:69)
    └─ api()  (backend/static/js/analyses.js:21)
        └─ csrf()  (backend/static/js/analyses.js:17)
        └─ ROOT_URLCONF · MIDDLEWARE  (backend/config/settings.py:36)
            └─ 프로젝트 urls.py  (backend/config/urls.py:7)
    └─ showMessage()  (backend/static/js/analyses.js:142)
    └─ errText()  (backend/static/js/analyses.js:33)
    └─ showJob()  (backend/static/js/analyses.js:149)
        └─ setSteps()  (backend/static/js/analyses.js:130)
        └─ showMessage()  (backend/static/js/analyses.js:142)  ↑위에 나옴
        └─ formResult()  (backend/static/js/analyses.js:198)
    └─ startPolling()  (backend/static/js/analyses.js:106)
        └─ api()  (backend/static/js/analyses.js:21)  ↑위에 나옴
        └─ setSteps()  (backend/static/js/analyses.js:130)  ↑위에 나옴
        └─ showMessage()  (backend/static/js/analyses.js:142)  ↑위에 나옴
        └─ showJob()  (backend/static/js/analyses.js:149)  ↑위에 나옴
```

#### 🔎 호출의 호출 — 위 단계에서 부르는 함수들의 코드

<details><summary><b>form submit 핸들러</b> — <code>backend/static/js/analyses.js:69</code> · 버튼을 누르면 FormData 로 묶어 api() 로 POST → 받은 job 으로 showJob · startPolling</summary>

```javascript
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const kind = $("#input_type").value;
  const task = $("#task_type").value;
  const fd = new FormData();
  fd.append("input_type", kind);
  fd.append("task_type", task);
  ["expected_action", "title"].forEach((k) => fd.append(k, form.elements[k].value));
  if (task === "FORM") {
    fd.append("exercise", form.elements.exercise.value);
    fd.append("camera_view", form.elements.camera_view.value);
  }
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
    $("#video").value = ""; $("#title").value = "";        // 분석 종류·동작 선택은 그대로 둠
  } catch (err) {
    showMessage(errText(err), true);
  } finally {
    startBtn.disabled = false;
    startBtn.textContent = $("#task_type").value === "FORM" ? "자세 판정 시작" : "AI 분석 시작";
  }
});
```
</details>

<details><summary><b>api()</b> — <code>backend/static/js/analyses.js:21</code> · 모든 요청의 공통 통로: fetch + CSRF 토큰 + JSON, 실패면 throw</summary>

```javascript
async function api(url, opts = {}) {
  const res = await fetch(url, { credentials: "same-origin", ...opts,
    headers: { "X-CSRFToken": csrf(), Accept: "application/json", ...(opts.headers || {}) } });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error("API 오류"), { status: res.status, data });
  return data;
}
```
</details>

<details><summary><b>csrf()</b> — <code>backend/static/js/analyses.js:17</code> · 쿠키(csrftoken)에서 CSRF 토큰을 꺼냄 → X-CSRFToken 헤더</summary>

```javascript
function csrf() {
  const m = document.cookie.match(/csrftoken=([^;]+)/);
  return m ? m[1] : form.querySelector("[name=csrfmiddlewaretoken]").value;
}
```
</details>

<details><summary><b>ROOT_URLCONF · MIDDLEWARE</b> — <code>backend/config/settings.py:36</code> · 요청이 들어오면 미들웨어(세션·CSRF·로그인) → config/urls.py 부터 주소 찾기</summary>

```python
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
```
</details>

<details><summary><b>프로젝트 urls.py</b> — <code>backend/config/urls.py:7</code> · 주소의 첫 갈림길: admin/ · accounts/ · 나머지는 analyses 앱으로</summary>

```python
urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),                  # signup/, me/
    path("accounts/", include("django.contrib.auth.urls")),       # login/, logout/ ...
    path("", include("analyses.urls")),                           # api/v1/analyses/, analyses/, dashboard/
    path("api-auth/", include("rest_framework.urls")),            # Browsable API 로그인
    path("", RedirectView.as_view(pattern_name="analyses_index", permanent=False), name="home"),
]
```
</details>

<details><summary><b>showMessage()</b> — <code>backend/static/js/analyses.js:142</code> · 상태 문구 / 오류 문구 한 줄 표시</summary>

```javascript
function showMessage(text, isError = false) {
  const el = $("#status-msg");
  el.textContent = text;
  el.className = isError ? "msg error" : "muted";
}
```
</details>

<details><summary><b>errText()</b> — <code>backend/static/js/analyses.js:33</code> · 서버가 준 검증 오류(400)를 한 줄 메시지로</summary>

```javascript
function errText(err) {
  const d = err.data || {};
  if (typeof d === "object") {
    const msgs = Object.entries(d).map(([k, v]) => (Array.isArray(v) ? v.join(" ") : String(v)));
    if (msgs.length) return msgs.join(" / ");
  }
  return `요청 실패 (HTTP ${err.status || "?"})`;
}
```
</details>

<details><summary><b>showJob()</b> — <code>backend/static/js/analyses.js:149</code> · 완료된 작업을 표로: 동작 인식은 사람별, 자세 판정은 formResult()</summary>

```javascript
function showJob(job) {
  currentId = job.id;
  const what = job.task_type === "FORM" ? `자세 판정 · ${EXERCISE_LABELS[job.exercise] || job.exercise}` : "동작 인식";
  $("#job-label").textContent = `#${job.id} · ${what} · ${INPUT_KO[job.input_type] || job.input_type}`;
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
  if (job.task_type === "FORM") { body.innerHTML = formResult(job); return; }
    // … predictions → Track · 예측 동작 · Confidence · 2순위 · 판단 표를 body.innerHTML 에 그림
  }
```
</details>

<details><summary><b>setSteps()</b> — <code>backend/static/js/analyses.js:130</code> · 대기 → 처리 중 → 완료/실패 단계 표시 색칠</summary>

```javascript
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
```
</details>

<details><summary><b>formResult()</b> — <code>backend/static/js/analyses.js:198</code> · 팀 모델 결과: 회차별 OK / NG / CHECK 표</summary>

```javascript
function formResult(job) {
  const s = (job.extra && job.extra.summary) || {};
  const meta = (job.extra && job.extra.meta) || {};
  const reps = job.reps || [];
  const rows = reps.map((r) => `
    <tr>
      <td>${esc(r.rep_label)}</td>
      <td><span class="badge ${VERDICT_BADGE[r.verdict] || ""}">${esc(r.verdict)}</span>
          ${r.model_flag ? '<span class="badge warn" title="이상 탐지 모델 보조 표시 (판정에는 반영 안 함)">주의</span>' : ""}</td>
    // … reps → 회차 · 판정 · 근거(checksText) 표
  }
```
</details>

<details><summary><b>startPolling()</b> — <code>backend/static/js/analyses.js:106</code> · 1초마다 status API → 단계 표시 → done 이면 상세 조회 후 showJob</summary>

```javascript
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
```
</details>


---

<a id="form"></a>
## 분석 · 자세 판정 (팀 모델)

**흐름:** 자세 판정 탭 · 동작·각도 선택 → 검증 · PENDING → task_type 분기 → 한 사람 Pose → 팀 엔진 → 회차 판정 OK · NG · CHECK → 회차별 저장 → 화면

### F1 자세 판정 탭 · 동작·각도 선택

📄 `backend/static/js/analyses.js` · **분석 종류 탭 (동작 인식 / 자세 판정)** · 43번째 줄  
🔁 넘기는 방식: HTTP POST · task_type=FORM · exercise · camera_view

탭을 바꾸면 동작(버피·런지·스쿼트 점프)과 촬영 각도를 고르는 칸이 나오고, 같은 API 로 보냅니다.

```javascript
document.querySelectorAll(".tab[data-task]").forEach((tab) => tab.addEventListener("click", () => {
  const task = tab.dataset.task;
  document.querySelectorAll(".tab[data-task]").forEach((t) => t.classList.toggle("active", t === tab));
  $("#task_type").value = task;
  document.querySelectorAll(".form-only").forEach((el) => { el.hidden = task !== "FORM"; });
  document.querySelectorAll(".action-only").forEach((el) => { el.hidden = task === "FORM"; });
  const cap = $("#capture_seconds");
  if (cap) {
    const max = task === "FORM" ? cap.dataset.maxForm : cap.dataset.maxAction;
    cap.max = max; $("#cap-max").textContent = max;
    if (task === "FORM" && Number(cap.value) < 15) cap.value = 15;     // 여러 회차를 보도록 기본 15초
    if (task !== "FORM" && Number(cap.value) > Number(max)) cap.value = max;
  }
  $("#start-btn").textContent = task === "FORM" ? "자세 판정 시작" : "AI 분석 시작";
}));
```

### F2 검증 · PENDING

📄 `backend/analyses/serializers.py` · **AnalysisJobCreateSerializer.validate** · 80번째 줄  
🔁 넘기는 방식: ORM INSERT → on_commit → Redis

FORM 이면 동작 선택이 필수이고, 6개 동작용 값은 비웁니다. 저장·등록 과정은 동작 인식과 같습니다.

```python
def validate(self, attrs):
    task = attrs.get("task_type") or AnalysisJob.TaskType.ACTION
    attrs["task_type"] = task
    if task == AnalysisJob.TaskType.FORM:      # 팀 자세 판정: 판정할 동작이 꼭 필요
        if attrs.get("exercise") not in Exercise.values:
            raise serializers.ValidationError({"exercise": "자세 판정할 동작(버피·런지·스쿼트 점프)을 선택하세요."})
        attrs["expected_action"] = ""
    else:
        attrs["exercise"] = ""
        attrs["camera_view"] = AnalysisJob.CameraView.AUTO
    max_sec = settings.FORM_CAPTURE_MAX_SECONDS if task == AnalysisJob.TaskType.FORM else 15
    kind = attrs.get("input_type")
    if kind == AnalysisJob.InputType.UPLOAD:
        if not attrs.get("video"):
            raise serializers.ValidationError({"video": "영상 업로드 방식은 영상 파일이 필요합니다."})
        attrs["camera_url"] = ""
        attrs["capture_seconds"] = None
    elif kind == AnalysisJob.InputType.IPCAM:
        if attrs.get("video"):
            raise serializers.ValidationError({"video": "IP Webcam 방식에서는 파일을 올리지 않습니다."})
        allowed = settings.ALLOWED_CAMERA_URLS
        url = (attrs.get("camera_url") or "").strip() or (allowed[0] if len(allowed) == 1 else "")
        if url not in allowed:   # 임의의 외부 URL을 서버가 호출하지 않도록 허용 목록만 통과
            raise serializers.ValidationError({"camera_url": "허용되지 않은 카메라 주소입니다."})
        attrs["camera_url"] = url
        sec = attrs.get("capture_seconds") or settings.CAMERA_CAPTURE_SECONDS
        if not 3 <= sec <= max_sec:    # 자세 판정은 여러 회차를 봐야 해서 더 길게 허용
            raise serializers.ValidationError({"capture_seconds": f"수집 시간은 3~{max_sec}초입니다."})
        attrs["capture_seconds"] = sec
    return attrs
```

➡️ 여기서 부르는 것: `validate_video` (serializers.py:69)

### F3 task_type 분기

📄 `backend/analyses/services.py` · **judge_form (services)** · 30번째 줄  
🔁 넘기는 방식: HTTP POST · 영상 + action · view

같은 run_analysis 안에서 task_type 하나로 팀 판정 서버를 고릅니다. 응답 코드 규칙이 같아서 오류 처리도 그대로 재사용합니다.

```python
def judge_form(video_path: str, exercise: str, view: str = "auto") -> dict:
    """팀 자세 판정 (form_service) — 응답 코드 규칙은 predict_video 와 같음"""
    url = f"{settings.FORM_SERVICE_URL.rstrip('/')}/api/v1/judge/"
    return _post(url, video_path, settings.FORM_TIMEOUT_SEC, "자세 판정 AI 서버",
                 data={"action": exercise, "view": view or "auto"})
```

➡️ 여기서 부르는 것: `_post` (services.py:37)

### F4 한 사람 Pose → 팀 엔진

📄 `form_service/main.py` · **judge (POST /api/v1/judge/)** · 40번째 줄  
🔁 넘기는 방식: 함수 호출 (Frame마다)

Frame 마다 점수 1위 한 사람의 관절을 팀 OnlineJudge 에 넣습니다. 팀 코드를 복사하지 않고 /team 볼륨에서 불러와 팀 웹과 같은 엔진·기준을 씁니다.

```python
@app.post("/api/v1/judge/")
async def judge(file: UploadFile = File(...), action: str = Form(...), view: str = Form("auto")):
    if not engine.ready:
        raise HTTPException(503, f"판정 엔진이 준비되지 않았습니다: {engine.error}")
    if action not in ACTIONS:
        raise HTTPException(400, f"판정할 수 없는 동작입니다: {action} (가능: {', '.join(ACTIONS)})")
    if view not in VIEWS:
        raise HTTPException(400, f"촬영 각도 값 오류: {view}")
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"지원하지 않는 형식입니다: {ext or '확장자 없음'}")
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        result = await run_in_threadpool(engine.judge_video, tmp_path, action, view, MAX_SECONDS)
    except VideoReadError as e:
        raise HTTPException(422, str(e)) from e
    finally:
        os.unlink(tmp_path)
    return {"ok": True, "filename": file.filename,
            "model": {"name": MODEL_NAME, "kind": "rules+form_model", "action": action},
            **result}
```

➡️ 여기서 부르는 것: `TeamEngine.judge_video` (engine.py:96)

### F5 회차 판정 OK · NG · CHECK

📄 `form_service/engine.py` · **TeamEngine.judge_video** · 96번째 줄  
🔁 넘기는 방식: 팀 엔진 내부

내려갔다 올라오면 1회. 회차마다 depth·무릎·고관절 각도를 재서 그 동작·각도 기준과 비교합니다. 벗어나면 NG, 관절이 안 보이거나 기준이 없으면 CHECK.

```python
def judge_video(self, path: str, action: str, view: str = "auto", max_seconds: float = 120.0) -> dict:
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise VideoReadError("영상을 열 수 없습니다. 손상되었거나 지원하지 않는 형식입니다.")
    fps = cap.get(cv2.CAP_PROP_FPS)
    fps = fps if fps and 5 < fps < 121 else 30.0
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    judge = self.OnlineJudge(self.cfg, action, view, self.paths, fps, "team", use_model=True)
    events, n, seen, t0 = [], 0, 0, time.time()
    with self.lock:                                       # YOLO 는 한 번에 하나씩
        while n < int(max_seconds * fps):
            ok, frame = cap.read()
            if not ok:
                break
            n += 1
            xy, conf = self.predict_pose(frame)
            seen += int(np.isfinite(xy).any())
            events += judge.push(n, (n - 1) / fps, xy, conf)
        cap.release()
        events += judge.flush()
    if n == 0:
        raise VideoReadError("영상에서 Frame을 읽지 못했습니다.")
    return finalize(judge, events, action, view, fps, n, seen, w, h, time.time() - t0)
```

➡️ 여기서 부르는 것: `predict_pose` (engine.py:85)

### F6 회차별 저장 → 화면

📄 `backend/analyses/tasks.py` · **_save_reps** · 92번째 줄  
🔁 넘기는 방식: ORM bulk_create → Polling

회차마다 RepJudgment 한 행으로 저장하고 COMPLETED 로 바꿉니다. 화면은 회차·판정 배지·구간·교정 메시지·측정값[기준] 표를 그립니다.

```python
def _save_reps(job: AnalysisJob, result: dict) -> dict:
    """자세 판정(form_service) 결과 → 회차별 RepJudgment"""
    meta, summary = result.get("meta") or {}, result.get("summary") or {}
    with transaction.atomic():
        job.reps.all().delete()
        RepJudgment.objects.bulk_create([
            RepJudgment(
                job=job, seq=i, rep_label=str(e.get("rep", i))[:12], kind=e.get("kind") or "rep",
                verdict=e.get("verdict") or "CHECK",
                start_sec=e.get("start_s"), end_sec=e.get("end_s"),
                message=(e.get("message") or "")[:255],
                out_of_range=(e.get("out_of_range") or "")[:255],
                boundary=(e.get("boundary") or "")[:255],
                model_flag=bool(e.get("model_flag")), model_score=e.get("model_score"),
                extra={k: e.get(k) for k in REP_EXTRA_FIELDS if e.get(k) is not None})
            for i, e in enumerate(result.get("reps", []), start=1)
        ])
        _complete(job, result,
                  extra={"schema": "form.v1", "meta": meta, "summary": summary, "model": result.get("model")},
                  duration=meta.get("duration_sec"))
    n = job.reps.count()
    log.info("Job %s 자세 판정 완료: %d건 %s", job.pk, n, summary)
    return {"job_id": job.pk, "status": job.status, "reps": n}
```

➡️ 여기서 부르는 것: `_complete` (tasks.py:117)

#### 🌳 호출 따라가기 (함수 → 부르는 함수 → 또 부르는 함수)

```text
form submit 핸들러  (backend/static/js/analyses.js:69)
    └─ api()  (backend/static/js/analyses.js:21)
        └─ csrf()  (backend/static/js/analyses.js:17)
        └─ ROOT_URLCONF · MIDDLEWARE  (backend/config/settings.py:36)
            └─ 프로젝트 urls.py  (backend/config/urls.py:7)
    └─ showMessage()  (backend/static/js/analyses.js:142)
    └─ errText()  (backend/static/js/analyses.js:33)
    └─ showJob()  (backend/static/js/analyses.js:149)
        └─ setSteps()  (backend/static/js/analyses.js:130)
        └─ showMessage()  (backend/static/js/analyses.js:142)  ↑위에 나옴
        └─ formResult()  (backend/static/js/analyses.js:198)
    └─ startPolling()  (backend/static/js/analyses.js:106)
        └─ api()  (backend/static/js/analyses.js:21)  ↑위에 나옴
        └─ setSteps()  (backend/static/js/analyses.js:130)  ↑위에 나옴
        └─ showMessage()  (backend/static/js/analyses.js:142)  ↑위에 나옴
        └─ showJob()  (backend/static/js/analyses.js:149)  ↑위에 나옴
```

#### 🔎 호출의 호출 — 위 단계에서 부르는 함수들의 코드

<details><summary><b>form submit 핸들러</b> — <code>backend/static/js/analyses.js:69</code> · 버튼을 누르면 FormData 로 묶어 api() 로 POST → 받은 job 으로 showJob · startPolling</summary>

```javascript
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const kind = $("#input_type").value;
  const task = $("#task_type").value;
  const fd = new FormData();
  fd.append("input_type", kind);
  fd.append("task_type", task);
  ["expected_action", "title"].forEach((k) => fd.append(k, form.elements[k].value));
  if (task === "FORM") {
    fd.append("exercise", form.elements.exercise.value);
    fd.append("camera_view", form.elements.camera_view.value);
  }
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
    $("#video").value = ""; $("#title").value = "";        // 분석 종류·동작 선택은 그대로 둠
  } catch (err) {
    showMessage(errText(err), true);
  } finally {
    startBtn.disabled = false;
    startBtn.textContent = $("#task_type").value === "FORM" ? "자세 판정 시작" : "AI 분석 시작";
  }
});
```
</details>

<details><summary><b>api()</b> — <code>backend/static/js/analyses.js:21</code> · 모든 요청의 공통 통로: fetch + CSRF 토큰 + JSON, 실패면 throw</summary>

```javascript
async function api(url, opts = {}) {
  const res = await fetch(url, { credentials: "same-origin", ...opts,
    headers: { "X-CSRFToken": csrf(), Accept: "application/json", ...(opts.headers || {}) } });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error("API 오류"), { status: res.status, data });
  return data;
}
```
</details>

<details><summary><b>csrf()</b> — <code>backend/static/js/analyses.js:17</code> · 쿠키(csrftoken)에서 CSRF 토큰을 꺼냄 → X-CSRFToken 헤더</summary>

```javascript
function csrf() {
  const m = document.cookie.match(/csrftoken=([^;]+)/);
  return m ? m[1] : form.querySelector("[name=csrfmiddlewaretoken]").value;
}
```
</details>

<details><summary><b>ROOT_URLCONF · MIDDLEWARE</b> — <code>backend/config/settings.py:36</code> · 요청이 들어오면 미들웨어(세션·CSRF·로그인) → config/urls.py 부터 주소 찾기</summary>

```python
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
```
</details>

<details><summary><b>프로젝트 urls.py</b> — <code>backend/config/urls.py:7</code> · 주소의 첫 갈림길: admin/ · accounts/ · 나머지는 analyses 앱으로</summary>

```python
urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),                  # signup/, me/
    path("accounts/", include("django.contrib.auth.urls")),       # login/, logout/ ...
    path("", include("analyses.urls")),                           # api/v1/analyses/, analyses/, dashboard/
    path("api-auth/", include("rest_framework.urls")),            # Browsable API 로그인
    path("", RedirectView.as_view(pattern_name="analyses_index", permanent=False), name="home"),
]
```
</details>

<details><summary><b>showMessage()</b> — <code>backend/static/js/analyses.js:142</code> · 상태 문구 / 오류 문구 한 줄 표시</summary>

```javascript
function showMessage(text, isError = false) {
  const el = $("#status-msg");
  el.textContent = text;
  el.className = isError ? "msg error" : "muted";
}
```
</details>

<details><summary><b>errText()</b> — <code>backend/static/js/analyses.js:33</code> · 서버가 준 검증 오류(400)를 한 줄 메시지로</summary>

```javascript
function errText(err) {
  const d = err.data || {};
  if (typeof d === "object") {
    const msgs = Object.entries(d).map(([k, v]) => (Array.isArray(v) ? v.join(" ") : String(v)));
    if (msgs.length) return msgs.join(" / ");
  }
  return `요청 실패 (HTTP ${err.status || "?"})`;
}
```
</details>

<details><summary><b>showJob()</b> — <code>backend/static/js/analyses.js:149</code> · 완료된 작업을 표로: 동작 인식은 사람별, 자세 판정은 formResult()</summary>

```javascript
function showJob(job) {
  currentId = job.id;
  const what = job.task_type === "FORM" ? `자세 판정 · ${EXERCISE_LABELS[job.exercise] || job.exercise}` : "동작 인식";
  $("#job-label").textContent = `#${job.id} · ${what} · ${INPUT_KO[job.input_type] || job.input_type}`;
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
  if (job.task_type === "FORM") { body.innerHTML = formResult(job); return; }
    // … predictions → Track · 예측 동작 · Confidence · 2순위 · 판단 표를 body.innerHTML 에 그림
  }
```
</details>

<details><summary><b>setSteps()</b> — <code>backend/static/js/analyses.js:130</code> · 대기 → 처리 중 → 완료/실패 단계 표시 색칠</summary>

```javascript
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
```
</details>

<details><summary><b>formResult()</b> — <code>backend/static/js/analyses.js:198</code> · 팀 모델 결과: 회차별 OK / NG / CHECK 표</summary>

```javascript
function formResult(job) {
  const s = (job.extra && job.extra.summary) || {};
  const meta = (job.extra && job.extra.meta) || {};
  const reps = job.reps || [];
  const rows = reps.map((r) => `
    <tr>
      <td>${esc(r.rep_label)}</td>
      <td><span class="badge ${VERDICT_BADGE[r.verdict] || ""}">${esc(r.verdict)}</span>
          ${r.model_flag ? '<span class="badge warn" title="이상 탐지 모델 보조 표시 (판정에는 반영 안 함)">주의</span>' : ""}</td>
    // … reps → 회차 · 판정 · 근거(checksText) 표
  }
```
</details>

<details><summary><b>startPolling()</b> — <code>backend/static/js/analyses.js:106</code> · 1초마다 status API → 단계 표시 → done 이면 상세 조회 후 showJob</summary>

```javascript
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
```
</details>


---

<a id="history"></a>
## 분석 · 분석 이력 · 행 클릭

**흐름:** 페이지 열면 이력 불러오기 → 내 작업만 고르기 → 목록 조회 → 행 클릭 → 상세 → 남의 작업이면 404 → 상세 JSON 만들기

### H1 페이지 열면 이력 불러오기

📄 `backend/static/js/analyses.js` · **loadHistory()** · 227번째 줄  
🔁 넘기는 방식: HTTP GET /api/v1/analyses/?page=1

분석 화면이 열리거나 작업이 끝나면 최근 이력을 API 로 받아 표를 그립니다.

```javascript
async function loadHistory() {
  const tbody = $("#history");
  try {
    const data = await api(`${API}?page=1`);
    const jobs = data.results || data;
    if (!jobs.length) { tbody.innerHTML = '<tr><td colspan="10" class="empty">아직 분석 기록이 없습니다.</td></tr>'; return; }
    tbody.innerHTML = jobs.slice(0, 10).map((j) => {
      const top = (j.predictions || []).slice().sort((a, b) => b.confidence - a.confidence)[0];
      const badge = { COMPLETED: "ok", FAILED: "err", PROCESSING: "run", PENDING: "" }[j.status];
      const isForm = j.task_type === "FORM";
      const fs = (j.extra && j.extra.summary) || {};
      const resultCell = isForm
        ? (j.status === "COMPLETED" ? `${fs.reps ?? 0}회 · OK ${fs.ok ?? 0} / NG ${fs.ng ?? 0} / CHECK ${fs.check ?? 0}` : "-")
        : (top ? `${esc(actionName(top.action_label))} (${j.prediction_count}명)` : "-");
      return `<tr class="clickable ${j.id === currentId ? "sel" : ""}" data-id="${j.id}">
        <td>${j.id}</td><td>${isForm ? "자세 판정" : "동작 인식"}</td><td>${INPUT_KO[j.input_type] || j.input_type}</td>
        <td><span class="badge ${badge}">${STATUS_KO[j.status] || j.status}</span></td>
        <td>${esc(isForm ? (EXERCISE_LABELS[j.exercise] || j.exercise) : actionName(j.expected_action))}</td>
        <td>${resultCell}</td>
        <td>${!isForm && top ? pct(top.confidence) : "-"}</td>
        <td>${sec(j.video_duration_sec)}</td><td>${sec(j.processing_time_sec)}</td>
        <td class="muted">${time(j.created_at)}</td></tr>`;
    }).join("");
// …
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="10" class="msg error">${esc(errText(err))}</td></tr>`;
  }
}
```

➡️ 여기서 부르는 것: `api()` (analyses.js:21) · `이력 행 클릭` (analyses.js:250)

### H2 내 작업만 고르기

📄 `backend/analyses/views.py` · **get_queryset** · 36번째 줄  
🔁 넘기는 방식: ORM filter(user=...)

일반 사용자는 자기 작업만, 관리자는 전체를 봅니다. 예측·회차는 미리 함께 가져와 쿼리 수를 줄입니다.

```python
def get_queryset(self):
    qs = AnalysisJob.objects.select_related("user")
    qs = qs.prefetch_related("predictions", "reps") if self.action in ("list", "retrieve") else qs   # 결과 표가 필요한 API만
    return qs if self.request.user.is_staff else qs.filter(user=self.request.user)
```

### H3 목록 조회

📄 `backend/analyses/views.py` · **list / retrieve (DRF 기본)** · 33번째 줄  
🔁 넘기는 방식: SQL

최신순으로 20개씩 페이지를 나눠 가져옵니다.

```python
class AnalysisJobViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]   # PUT 전체 수정 금지

    def get_queryset(self):
        qs = AnalysisJob.objects.select_related("user")
        qs = qs.prefetch_related("predictions", "reps") if self.action in ("list", "retrieve") else qs   # 결과 표가 필요한 API만
        return qs if self.request.user.is_staff else qs.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.action == "create":
            return AnalysisJobCreateSerializer
        if self.action == "partial_update":
            return AnalysisJobUpdateSerializer
        return AnalysisJobSerializer
```

➡️ 여기서 부르는 것: `get_queryset` (views.py:36) · `AnalysisJobSerializer` (serializers.py:35)

### H4 행 클릭 → 상세

📄 `backend/static/js/analyses.js` · **이력 행 클릭** · 250번째 줄  
🔁 넘기는 방식: HTTP GET /api/v1/analyses/{id}/

행을 누르면 그 작업 상세를 받아 결과 영역에 다시 그립니다. 아직 처리 중이면 Polling 을 다시 시작합니다.

```javascript
tbody.querySelectorAll("tr.clickable").forEach((tr) => tr.addEventListener("click", async () => {
  const job = await api(`${API}${tr.dataset.id}/`);
  showJob(job);
  if (!["COMPLETED", "FAILED"].includes(job.status)) startPolling(job.id);
  tbody.querySelectorAll("tr").forEach((r) => r.classList.toggle("sel", r === tr));
}));
```

➡️ 여기서 부르는 것: `api()` (analyses.js:21) · `showJob()` (analyses.js:149) · `startPolling()` (analyses.js:106)

### H5 남의 작업이면 404

📄 `backend/analyses/views.py` · **get_queryset** · 36번째 줄  
🔁 넘기는 방식: 404 Not Found

상세도 같은 get_queryset 을 거치므로 다른 사람의 작업 번호를 넣으면 '없음(404)'이 됩니다. 존재 여부도 드러내지 않습니다 (T07).

```python
def get_queryset(self):
    qs = AnalysisJob.objects.select_related("user")
    qs = qs.prefetch_related("predictions", "reps") if self.action in ("list", "retrieve") else qs   # 결과 표가 필요한 API만
    return qs if self.request.user.is_staff else qs.filter(user=self.request.user)
```

### H6 상세 JSON 만들기

📄 `backend/analyses/serializers.py` · **AnalysisJobSerializer** · 35번째 줄  
🔁 넘기는 방식: JSON (predictions · reps · video URL)

작업 정보에 사람별 예측과 회차별 판정을 함께 담아 보냅니다. 화면은 이 JSON 하나로 표와 영상을 그립니다.

```python
class AnalysisJobSerializer(serializers.ModelSerializer):
    user = serializers.CharField(source="user.username", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    input_type_display = serializers.CharField(source="get_input_type_display", read_only=True)
    predictions = PersonPredictionSerializer(many=True, read_only=True)
    prediction_count = serializers.IntegerField(source="predictions.count", read_only=True)
    task_type_display = serializers.CharField(source="get_task_type_display", read_only=True)
    exercise_display = serializers.CharField(source="get_exercise_display", read_only=True)
    camera_view_display = serializers.CharField(source="get_camera_view_display", read_only=True)
    reps = RepJudgmentSerializer(many=True, read_only=True)

    class Meta:
```

#### 🌳 호출 따라가기 (함수 → 부르는 함수 → 또 부르는 함수)

```text
loadHistory()  (backend/static/js/analyses.js:227)
    └─ api()  (backend/static/js/analyses.js:21)
        └─ csrf()  (backend/static/js/analyses.js:17)
        └─ ROOT_URLCONF · MIDDLEWARE  (backend/config/settings.py:36)
            └─ 프로젝트 urls.py  (backend/config/urls.py:7)
    └─ 이력 행 클릭  (backend/static/js/analyses.js:250)
        └─ api()  (backend/static/js/analyses.js:21)  ↑위에 나옴
        └─ showJob()  (backend/static/js/analyses.js:149)
            └─ setSteps()  (backend/static/js/analyses.js:130)
            └─ showMessage()  (backend/static/js/analyses.js:142)
            └─ formResult()  (backend/static/js/analyses.js:198)
        └─ startPolling()  (backend/static/js/analyses.js:106)
            └─ api()  (backend/static/js/analyses.js:21)  ↑위에 나옴
            └─ setSteps()  (backend/static/js/analyses.js:130)  ↑위에 나옴
            └─ showMessage()  (backend/static/js/analyses.js:142)  ↑위에 나옴
            └─ showJob()  (backend/static/js/analyses.js:149)  ↑위에 나옴
```

#### 🔎 호출의 호출 — 위 단계에서 부르는 함수들의 코드

<details><summary><b>api()</b> — <code>backend/static/js/analyses.js:21</code> · 모든 요청의 공통 통로: fetch + CSRF 토큰 + JSON, 실패면 throw</summary>

```javascript
async function api(url, opts = {}) {
  const res = await fetch(url, { credentials: "same-origin", ...opts,
    headers: { "X-CSRFToken": csrf(), Accept: "application/json", ...(opts.headers || {}) } });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error("API 오류"), { status: res.status, data });
  return data;
}
```
</details>

<details><summary><b>csrf()</b> — <code>backend/static/js/analyses.js:17</code> · 쿠키(csrftoken)에서 CSRF 토큰을 꺼냄 → X-CSRFToken 헤더</summary>

```javascript
function csrf() {
  const m = document.cookie.match(/csrftoken=([^;]+)/);
  return m ? m[1] : form.querySelector("[name=csrfmiddlewaretoken]").value;
}
```
</details>

<details><summary><b>ROOT_URLCONF · MIDDLEWARE</b> — <code>backend/config/settings.py:36</code> · 요청이 들어오면 미들웨어(세션·CSRF·로그인) → config/urls.py 부터 주소 찾기</summary>

```python
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
```
</details>

<details><summary><b>프로젝트 urls.py</b> — <code>backend/config/urls.py:7</code> · 주소의 첫 갈림길: admin/ · accounts/ · 나머지는 analyses 앱으로</summary>

```python
urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),                  # signup/, me/
    path("accounts/", include("django.contrib.auth.urls")),       # login/, logout/ ...
    path("", include("analyses.urls")),                           # api/v1/analyses/, analyses/, dashboard/
    path("api-auth/", include("rest_framework.urls")),            # Browsable API 로그인
    path("", RedirectView.as_view(pattern_name="analyses_index", permanent=False), name="home"),
]
```
</details>

<details><summary><b>showJob()</b> — <code>backend/static/js/analyses.js:149</code> · 완료된 작업을 표로: 동작 인식은 사람별, 자세 판정은 formResult()</summary>

```javascript
function showJob(job) {
  currentId = job.id;
  const what = job.task_type === "FORM" ? `자세 판정 · ${EXERCISE_LABELS[job.exercise] || job.exercise}` : "동작 인식";
  $("#job-label").textContent = `#${job.id} · ${what} · ${INPUT_KO[job.input_type] || job.input_type}`;
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
  if (job.task_type === "FORM") { body.innerHTML = formResult(job); return; }
    // … predictions → Track · 예측 동작 · Confidence · 2순위 · 판단 표를 body.innerHTML 에 그림
  }
```
</details>

<details><summary><b>setSteps()</b> — <code>backend/static/js/analyses.js:130</code> · 대기 → 처리 중 → 완료/실패 단계 표시 색칠</summary>

```javascript
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
```
</details>

<details><summary><b>showMessage()</b> — <code>backend/static/js/analyses.js:142</code> · 상태 문구 / 오류 문구 한 줄 표시</summary>

```javascript
function showMessage(text, isError = false) {
  const el = $("#status-msg");
  el.textContent = text;
  el.className = isError ? "msg error" : "muted";
}
```
</details>

<details><summary><b>formResult()</b> — <code>backend/static/js/analyses.js:198</code> · 팀 모델 결과: 회차별 OK / NG / CHECK 표</summary>

```javascript
function formResult(job) {
  const s = (job.extra && job.extra.summary) || {};
  const meta = (job.extra && job.extra.meta) || {};
  const reps = job.reps || [];
  const rows = reps.map((r) => `
    <tr>
      <td>${esc(r.rep_label)}</td>
      <td><span class="badge ${VERDICT_BADGE[r.verdict] || ""}">${esc(r.verdict)}</span>
          ${r.model_flag ? '<span class="badge warn" title="이상 탐지 모델 보조 표시 (판정에는 반영 안 함)">주의</span>' : ""}</td>
    // … reps → 회차 · 판정 · 근거(checksText) 표
  }
```
</details>

<details><summary><b>startPolling()</b> — <code>backend/static/js/analyses.js:106</code> · 1초마다 status API → 단계 표시 → done 이면 상세 조회 후 showJob</summary>

```javascript
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
```
</details>


---

<a id="dash"></a>
## 관리 · 대시보드

**흐름:** 메뉴 [대시보드] 클릭 → URL → 뷰 연결 → 로그인 · 관리자 확인 → 차트 데이터 집계 → 요약 숫자 · 최근 작업 → HTML + 차트 데이터 전달 → Chart.js 로 그래프 그리기

### D1 메뉴 [대시보드] 클릭

📄 `backend/templates/base.html` · **상단 메뉴 (base.html)** · 14번째 줄  
🔁 넘기는 방식: HTTP GET /dashboard/ (페이지 요청)

관리자에게만 메뉴가 보입니다. 누르면 일반 페이지 요청(GET)이 갑니다. AI 분석과 달리 Celery·AI 서버를 거치지 않는 동기 처리입니다.

```html
<nav>
  {% if user.is_authenticated %}
    <a href="{% url 'analyses_index' %}">AI 분석</a>
    {% if user.is_staff %}<a href="{% url 'dashboard' %}">대시보드</a>{% endif %}
    <a href="{% url 'me' %}">내 정보</a>
    {% if user.is_staff %}<a href="{% url 'admin:index' %}">Admin</a>{% endif %}
    <span class="who">{{ user.username }}{% if user.is_staff %} · 관리자{% endif %}</span>
    <form method="post" action="{% url 'logout' %}" class="inline">
      {% csrf_token %}<button type="submit" class="link">로그아웃</button>
    </form>
  {% else %}
    <a href="{% url 'login' %}">로그인</a>
    <a href="{% url 'signup' %}">회원가입</a>
  {% endif %}
</nav>
```

➡️ 여기서 부르는 것: `dashboard 뷰` (page_views.py:43) · `me()` (views.py:22) · `admin.site.urls (Django 기본)` (urls.py:8) · `로그아웃 버튼 (POST 폼)` (base.html:21) · `login.html 폼` (login.html:6) · `signup.html 폼` (signup.html:6)

### D2 URL → 뷰 연결

📄 `backend/analyses/urls.py` · **앱 urls.py (analyses)** · 7번째 줄  
🔁 넘기는 방식: URL 라우팅 → 함수 호출

주소 /dashboard/ 를 page_views.dashboard 함수에 연결합니다.

```python
router = DefaultRouter()
router.register("analyses", AnalysisJobViewSet, basename="analysis")

urlpatterns = [
    path("api/v1/", include(router.urls)),
    path("analyses/", page_views.analyses_index, name="analyses_index"),
    path("dashboard/", page_views.dashboard, name="dashboard"),
]
```

➡️ 여기서 부르는 것: `AnalysisJobViewSet.create` (views.py:48) · `job_status (@action)` (views.py:70) · `list / retrieve (DRF 기본)` (views.py:33) · `analyses_index (화면 뷰)` (page_views.py:21) · `dashboard 뷰` (page_views.py:43)

### D3 로그인 · 관리자 확인

📄 `backend/analyses/page_views.py` · **dashboard 뷰** · 43번째 줄  
🔁 넘기는 방식: 세션 확인 → 통과 / 302 / 403

로그인 안 했으면 로그인 페이지로, 관리자가 아니면 403 으로 막습니다. 개별 작업과 달리 주소가 공개돼 있어 '권한 없음'을 알려 줍니다.

```python
@login_required
def dashboard(request):
    """관리자 전용. 숫자는 모두 PostgreSQL을 Django ORM으로 집계 (FastAPI는 DB에 접근하지 않음)"""
    if not request.user.is_staff:
        raise PermissionDenied("관리자만 접근할 수 있습니다.")
    # …
    return render(request, "analyses/dashboard.html",
                  {"chart": chart, "summary": summary, "recent": recent})
```

➡️ 여기서 부르는 것: `차트·요약 집계 (ORM)` (page_views.py:53) · `_form_chart` (page_views.py:87) · `dashboard.js (Chart.js)` (dashboard.js:1)

### D4 차트 데이터 집계

📄 `backend/analyses/page_views.py` · **차트·요약 집계 (ORM)** · 53번째 줄  
🔁 넘기는 방식: ORM → SQL GROUP BY (PostgreSQL)

동작별·상태별·입력 방식별 개수를 파이썬으로 세지 않고 DB 가 GROUP BY 로 바로 셉니다. 0건인 동작도 표시하고, 모델이 바뀌어 새 라벨이 생기면 자동으로 추가됩니다.

```python
# 차트 1: 동작별 예측 건수 — 6개 동작은 0건이어도 표시, 모델 교체로 새 라벨이 생기면 자동 추가
by_action = dict(PersonPrediction.objects.values_list("action_label").annotate(n=Count("id")))
action_keys = list(action_names) + sorted(k for k in by_action if k not in action_names)
# 차트 2: 작업 상태별 건수
by_status = dict(AnalysisJob.objects.values_list("status").annotate(n=Count("id")))
# 선택: 입력 방식별 건수
by_input = dict(AnalysisJob.objects.values_list("input_type").annotate(n=Count("id")))

# …
summary = {
    "jobs": AnalysisJob.objects.count(),
    "form_jobs": AnalysisJob.objects.filter(task_type=AnalysisJob.TaskType.FORM).count(),
    "reps": RepJudgment.objects.count(),
    "predictions": PersonPrediction.objects.count(),
    "users": AnalysisJob.objects.values("user").distinct().count(),
    "uncertain": PersonPrediction.objects.filter(uncertain=True).count(),
    "avg_processing": AnalysisJob.objects.filter(status=AnalysisJob.Status.COMPLETED)
                                         .aggregate(v=Avg("processing_time_sec"))["v"],
}
recent = (AnalysisJob.objects.select_related("user")
          .annotate(pred_count=Count("predictions")).order_by("-created_at")[:10])
```

### D5 요약 숫자 · 최근 작업

📄 `backend/analyses/page_views.py` · **차트·요약 집계 (ORM)** · 53번째 줄  
🔁 넘기는 방식: ORM → SQL COUNT · AVG

전체 작업 수, 예측 수, 불확실 수, 사용자 수, 평균 처리 시간을 DB 에서 계산하고, 최근 10개 작업을 예측 개수와 함께 가져옵니다.

*(바로 위 단계와 같은 함수 — 위 코드에서 이어서 설명)*

### D6 HTML + 차트 데이터 전달

📄 `backend/analyses/page_views.py` · **dashboard 뷰** · 43번째 줄  
🔁 넘기는 방식: 템플릿 렌더링 → HTML 응답 (JSON 포함)

요약 숫자와 최근 작업은 템플릿이 HTML 로 그리고, 차트 데이터는 json_script 로 페이지 안에 안전하게 넣어 보냅니다. 별도 API 호출이 없습니다.

```python
@login_required
def dashboard(request):
    """관리자 전용. 숫자는 모두 PostgreSQL을 Django ORM으로 집계 (FastAPI는 DB에 접근하지 않음)"""
    if not request.user.is_staff:
        raise PermissionDenied("관리자만 접근할 수 있습니다.")
    # …
    return render(request, "analyses/dashboard.html",
                  {"chart": chart, "summary": summary, "recent": recent})
```

➡️ 여기서 부르는 것: `차트·요약 집계 (ORM)` (page_views.py:53) · `_form_chart` (page_views.py:87) · `dashboard.js (Chart.js)` (dashboard.js:1)

### D7 Chart.js 로 그래프 그리기

📄 `backend/static/js/dashboard.js` · **dashboard.js (Chart.js)** · 1번째 줄  
🔁 넘기는 방식: 함수 호출 (브라우저) · 서버 요청 없음

페이지에 들어 있는 JSON 을 읽어 막대(동작), 도넛(상태), 누적 막대(자세 판정 OK·NG·CHECK) 그래프를 그립니다.

```javascript
// Django가 ORM으로 집계해 json_script 로 넘긴 값으로 Chart.js 차트를 그림 (API 호출 없음)
(() => {
  const data = JSON.parse(document.getElementById("chart-data").textContent);
  if (typeof Chart === "undefined") {
    document.querySelectorAll("canvas").forEach((c) => c.replaceWith(Object.assign(
      document.createElement("p"), { className: "msg error", textContent: "Chart.js를 불러오지 못했습니다 (인터넷 연결 확인)." })));
    return;
  }
  const intAxis = { beginAtZero: true, ticks: { precision: 0 } };

  new Chart(document.getElementById("chart-actions"), {
    type: "bar",
    data: { labels: data.actions.labels, datasets: [{ label: "예측 건수", data: data.actions.values, backgroundColor: "#2f5bea" }] },
    options: { plugins: { legend: { display: false } }, scales: { y: intAxis } },
  });
  // …
  const formColors = { OK: "#16a34a", NG: "#dc2626", CHECK: "#f59e0b" };
  new Chart(document.getElementById("chart-form"), {
    type: "bar",
    data: { labels: data.form.labels,
            datasets: data.form.datasets.map((d) => ({ label: d.label, data: d.values, backgroundColor: formColors[d.label] })) },
    options: { plugins: { legend: { position: "right" } }, scales: { x: { stacked: true }, y: { ...intAxis, stacked: true } } },
  });
```

#### 🌳 호출 따라가기 (함수 → 부르는 함수 → 또 부르는 함수)

```text
상단 메뉴 (base.html)  (backend/templates/base.html:14)
    └─ dashboard 뷰  (backend/analyses/page_views.py:43)
        └─ 차트·요약 집계 (ORM)  (backend/analyses/page_views.py:53)
        └─ _form_chart  (backend/analyses/page_views.py:87)
        └─ dashboard.js (Chart.js)  (backend/static/js/dashboard.js:1)
```

#### 🔎 호출의 호출 — 위 단계에서 부르는 함수들의 코드

<details><summary><b>_form_chart</b> — <code>backend/analyses/page_views.py:87</code> · 동작별 OK/NG/CHECK 회차 수</summary>

```python
def _form_chart() -> dict:
    """동작(버피·런지·스쿼트 점프)별 OK/NG/CHECK 회차 수 — RepJudgment ORM 집계"""
    rows = RepJudgment.objects.values_list("job__exercise", "verdict").annotate(n=Count("id"))
    table = {(ex, v): n for ex, v, n in rows}
    verdicts = RepJudgment.Verdict.values
    return {"labels": [label for _, label in Exercise.choices],
            "datasets": [{"label": v, "values": [table.get((ex, v), 0) for ex, _ in Exercise.choices]}
                         for v in verdicts]}
```
</details>


---

<a id="admin"></a>
## 관리 · Admin

**흐름:** 메뉴 [Admin] → staff 확인 → 작업 목록 · 필터 → 작업 상세 · 결과는 읽기 전용

### A1 메뉴 [Admin]

📄 `backend/templates/base.html` · **상단 메뉴 (base.html)** · 14번째 줄  
🔁 넘기는 방식: HTTP GET /admin/

관리자에게만 보이는 메뉴입니다. Django 가 기본으로 주는 관리 화면으로 갑니다.

```html
<nav>
  {% if user.is_authenticated %}
    <a href="{% url 'analyses_index' %}">AI 분석</a>
    {% if user.is_staff %}<a href="{% url 'dashboard' %}">대시보드</a>{% endif %}
    <a href="{% url 'me' %}">내 정보</a>
    {% if user.is_staff %}<a href="{% url 'admin:index' %}">Admin</a>{% endif %}
    <span class="who">{{ user.username }}{% if user.is_staff %} · 관리자{% endif %}</span>
    <form method="post" action="{% url 'logout' %}" class="inline">
      {% csrf_token %}<button type="submit" class="link">로그아웃</button>
    </form>
  {% else %}
    <a href="{% url 'login' %}">로그인</a>
    <a href="{% url 'signup' %}">회원가입</a>
  {% endif %}
</nav>
```

➡️ 여기서 부르는 것: `dashboard 뷰` (page_views.py:43) · `me()` (views.py:22) · `admin.site.urls (Django 기본)` (urls.py:8) · `로그아웃 버튼 (POST 폼)` (base.html:21) · `login.html 폼` (login.html:6) · `signup.html 폼` (signup.html:6)

### A2 staff 확인

📄 `backend/config/urls.py` · **admin.site.urls (Django 기본)** · 8번째 줄  
🔁 넘기는 방식: 세션 · is_staff

로그인한 staff 만 들어갈 수 있고, 아니면 Admin 로그인 화면으로 보냅니다.

```python
path("admin/", admin.site.urls),
```

➡️ 여기서 부르는 것: `AnalysisJobAdmin` (admin.py:24)

### A3 작업 목록 · 필터

📄 `backend/analyses/admin.py` · **AnalysisJobAdmin** · 24번째 줄  
🔁 넘기는 방식: ORM annotate(Count)

분석 종류·상태·입력 방식으로 걸러 보고, 사용자 이름으로 검색합니다. 예측 개수는 DB 에서 미리 셉니다.

```python
@admin.register(AnalysisJob)
class AnalysisJobAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "task_type", "exercise", "input_type", "status", "prediction_count",
                    "expected_action", "video_duration_sec", "created_at", "finished_at"]
    list_filter = ["task_type", "status", "input_type", "exercise", "created_at"]
    search_fields = ["user__username", "title", "memo"]
    list_select_related = ["user"]
    date_hierarchy = "created_at"
    readonly_fields = ["status", "celery_task_id", "error_message", "result_message",
                       "video_duration_sec", "processing_time_sec",
                       "created_at", "started_at", "finished_at"]
    fieldsets = [
        ("요청", {"fields": ["user", "title", "memo", "task_type", "exercise", "camera_view", "input_type", "video",
                            "camera_url", "capture_seconds", "expected_action"]}),
        ("처리 상태", {"fields": ["status", "celery_task_id", "model_name", "result_message", "error_message"]}),
        ("시간", {"fields": ["video_duration_sec", "processing_time_sec",
                            "created_at", "started_at", "finished_at"],
                 "classes": ["collapse"]}),
    ]
    inlines = [PersonPredictionInline, RepJudgmentInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_pred_count=Count("predictions"))

    @admin.display(description="예측 수", ordering="_pred_count")
    def prediction_count(self, obj):
        return obj._pred_count
```

➡️ 여기서 부르는 것: `PersonPrediction · RepJudgment Inline` (admin.py:7)

### A4 작업 상세 · 결과는 읽기 전용

📄 `backend/analyses/admin.py` · **PersonPrediction · RepJudgment Inline** · 7번째 줄  
🔁 넘기는 방식: ORM SELECT

작업 안에 사람별 예측과 회차별 판정이 함께 보입니다. AI 결과는 관리자도 고칠 수 없게 읽기 전용입니다.

```python
class PersonPredictionInline(admin.TabularInline):
    model = PersonPrediction
    extra = 0
    fields = ["track_id", "action_label", "confidence", "second_label", "margin",
              "uncertain", "frames_seen", "mean_keypoint_conf"]
    readonly_fields = fields          # AI 결과는 관리자 화면에서도 수정하지 않음
    can_delete = False


class RepJudgmentInline(admin.TabularInline):
    model = RepJudgment
    extra = 0
    fields = ["rep_label", "verdict", "start_sec", "end_sec", "message", "out_of_range", "model_flag"]
    readonly_fields = fields
    can_delete = False
```

#### 🌳 호출 따라가기 (함수 → 부르는 함수 → 또 부르는 함수)

```text
상단 메뉴 (base.html)  (backend/templates/base.html:14)
    └─ admin.site.urls (Django 기본)  (backend/config/urls.py:8)
        └─ AnalysisJobAdmin  (backend/analyses/admin.py:24)
            └─ PersonPrediction · RepJudgment Inline  (backend/analyses/admin.py:7)
```


---

<a id="login"></a>
## 계정 · 로그인

**흐름:** 아이디·비밀번호 입력 → 비밀번호 확인 → 세션 만들기 → 분석 화면으로 이동

### L1 아이디·비밀번호 입력

📄 `backend/templates/registration/login.html` · **login.html 폼** · 6번째 줄  
🔁 넘기는 방식: HTTP POST /accounts/login/

일반 HTML 폼으로 보냅니다. CSRF 토큰이 함께 가서 다른 사이트의 위조 요청을 막습니다.

```html
{% if form.errors %}<div class="msg error">아이디 또는 비밀번호가 올바르지 않습니다.</div>{% endif %}
{% if next and not user.is_authenticated %}<p class="hint">로그인이 필요한 페이지입니다.</p>{% endif %}
<form method="post" class="form">
  {% csrf_token %}
  {{ form.as_p }}
  <input type="hidden" name="next" value="{{ next }}">
  <button type="submit">로그인</button>
</form>
```

➡️ 여기서 부르는 것: `LoginView (Django 기본)` (urls.py:10)

### L2 비밀번호 확인

📄 `backend/config/urls.py` · **LoginView (Django 기본)** · 10번째 줄  
🔁 넘기는 방식: ORM SELECT auth_user

Django 기본 로그인 뷰가 사용자를 찾고, 저장된 해시와 비밀번호를 비교합니다. 비밀번호 원문은 저장하지 않습니다.

```python
path("accounts/", include("django.contrib.auth.urls")),       # login/, logout/ ...

# Django 내부 (직접 작성 안 함)
# LoginView.post → form.is_valid() → authenticate(username, password)
#               → login(request, user)   # 세션 생성, sessionid 쿠키
#               → redirect(LOGIN_REDIRECT_URL)
```

➡️ 여기서 부르는 것: `로그인·로그아웃 후 이동` (settings.py:99)

### L3 세션 만들기

📄 `backend/config/urls.py` · **LoginView (Django 기본)** · 10번째 줄  
🔁 넘기는 방식: DB django_session 저장 + 쿠키 sessionid

로그인 상태를 DB 세션 테이블에 저장하고 브라우저에는 sessionid 쿠키만 줍니다. 그래서 컨테이너를 지웠다 다시 만들어도 로그인이 유지됐습니다 (T10).

*(바로 위 단계와 같은 함수 — 위 코드에서 이어서 설명)*

### L4 분석 화면으로 이동

📄 `backend/config/settings.py` · **로그인·로그아웃 후 이동** · 99번째 줄  
🔁 넘기는 방식: 302 → / → /analyses/

로그인 후 home 으로 보내고, home 은 분석 화면으로 다시 보냅니다.

```python
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"
```

#### 🌳 호출 따라가기 (함수 → 부르는 함수 → 또 부르는 함수)

```text
login.html 폼  (backend/templates/registration/login.html:6)
    └─ LoginView (Django 기본)  (backend/config/urls.py:10)
        └─ 로그인·로그아웃 후 이동  (backend/config/settings.py:99)
```


---

<a id="signup"></a>
## 계정 · 회원가입

**흐름:** 가입 폼 제출 → 가입 뷰 → 검증 → 일반 회원 저장 → 로그인 화면

### S1 가입 폼 제출

📄 `backend/templates/accounts/signup.html` · **signup.html 폼** · 6번째 줄  
🔁 넘기는 방식: HTTP POST /accounts/signup/

아이디와 비밀번호 두 번을 입력해 보냅니다.

```html
<form method="post" class="form">
  {% csrf_token %}
  {{ form.as_p }}
  <button type="submit">가입하기</button>
</form>
```

➡️ 여기서 부르는 것: `signup()` (views.py:8)

### S2 가입 뷰

📄 `backend/accounts/views.py` · **signup()** · 8번째 줄  
🔁 넘기는 방식: 함수 호출

이미 로그인했으면 home 으로 보내고, 아니면 Django 기본 가입 폼으로 검사합니다.

```python
def signup(request):
    if request.user.is_authenticated:
        return redirect("home")
    if request.method == "POST":
        form = UserCreationForm(request.POST)       # 중복 아이디·비밀번호 불일치·약한 비밀번호 검사
        if form.is_valid():
            user = form.save()                       # 일반 회원으로 생성 (is_staff=False)
            messages.success(request, f"{user.username}님, 가입이 완료되었습니다. 로그인해 주세요.")
            return redirect("login")
    else:
        form = UserCreationForm()
    return render(request, "accounts/signup.html", {"form": form})
```

### S3 검증

📄 `backend/accounts/views.py` · **signup()** · 8번째 줄  
🔁 넘기는 방식: 검증 오류 → 폼 다시 표시

중복 아이디, 비밀번호 불일치, 너무 약한 비밀번호(AUTH_PASSWORD_VALIDATORS)를 검사합니다.

*(바로 위 단계와 같은 함수 — 위 코드에서 이어서 설명)*

### S4 일반 회원 저장 → 로그인 화면

📄 `backend/accounts/views.py` · **signup()** · 8번째 줄  
🔁 넘기는 방식: ORM INSERT auth_user (is_staff=False)

일반 회원으로 저장(관리자 아님)하고 안내 메시지와 함께 로그인 화면으로 보냅니다.

*(바로 위 단계와 같은 함수 — 위 코드에서 이어서 설명)*

#### 🌳 호출 따라가기 (함수 → 부르는 함수 → 또 부르는 함수)

```text
signup.html 폼  (backend/templates/accounts/signup.html:6)
    └─ signup()  (backend/accounts/views.py:8)
```


---

<a id="me"></a>
## 계정 · 내 정보

**흐름:** 메뉴 [내 정보] → 로그인 확인 → 내 작업 수 · 최근 5개

### M1 메뉴 [내 정보]

📄 `backend/templates/base.html` · **상단 메뉴 (base.html)** · 14번째 줄  
🔁 넘기는 방식: HTTP GET /accounts/me/

로그인한 사용자 누구나 볼 수 있는 페이지입니다.

```html
<nav>
  {% if user.is_authenticated %}
    <a href="{% url 'analyses_index' %}">AI 분석</a>
    {% if user.is_staff %}<a href="{% url 'dashboard' %}">대시보드</a>{% endif %}
    <a href="{% url 'me' %}">내 정보</a>
    {% if user.is_staff %}<a href="{% url 'admin:index' %}">Admin</a>{% endif %}
    <span class="who">{{ user.username }}{% if user.is_staff %} · 관리자{% endif %}</span>
    <form method="post" action="{% url 'logout' %}" class="inline">
      {% csrf_token %}<button type="submit" class="link">로그아웃</button>
    </form>
  {% else %}
    <a href="{% url 'login' %}">로그인</a>
    <a href="{% url 'signup' %}">회원가입</a>
  {% endif %}
</nav>
```

➡️ 여기서 부르는 것: `dashboard 뷰` (page_views.py:43) · `me()` (views.py:22) · `admin.site.urls (Django 기본)` (urls.py:8) · `로그아웃 버튼 (POST 폼)` (base.html:21) · `login.html 폼` (login.html:6) · `signup.html 폼` (signup.html:6)

### M2 로그인 확인

📄 `backend/accounts/views.py` · **me()** · 22번째 줄  
🔁 넘기는 방식: 비로그인 → 302 /accounts/login/?next=/accounts/me/

로그인하지 않았으면 로그인 화면으로 보내고, 로그인 후 다시 이 페이지로 돌아오게 next 를 붙입니다.

```python
@login_required                                     # 비로그인 → /accounts/login/?next=/accounts/me/
def me(request):
    jobs = request.user.analysis_jobs.all()          # 본인 작업만 (관리자도 여기서는 본인 것만)
    return render(request, "accounts/me.html", {
        "job_count": jobs.count(),
        "recent_jobs": jobs[:5],
    })
```

### M3 내 작업 수 · 최근 5개

📄 `backend/accounts/views.py` · **me()** · 22번째 줄  
🔁 넘기는 방식: ORM (related_name)

관리자라도 이 페이지에서는 본인 작업만 셉니다. 모델의 related_name 덕분에 user.analysis_jobs 로 바로 접근합니다.

*(바로 위 단계와 같은 함수 — 위 코드에서 이어서 설명)*

#### 🌳 호출 따라가기 (함수 → 부르는 함수 → 또 부르는 함수)

```text
상단 메뉴 (base.html)  (backend/templates/base.html:14)
    └─ me()  (backend/accounts/views.py:22)
```


---

<a id="logout"></a>
## 계정 · 로그아웃

**흐름:** [로그아웃] 버튼 → 세션 삭제 → 로그인 화면으로

### O1 [로그아웃] 버튼

📄 `backend/templates/base.html` · **로그아웃 버튼 (POST 폼)** · 21번째 줄  
🔁 넘기는 방식: HTTP POST /accounts/logout/

링크(GET)가 아니라 POST 폼입니다. 다른 사이트가 이미지 태그 등으로 몰래 로그아웃시키는 것을 막습니다 (Django 5 부터 POST 만 허용).

```html
<form method="post" action="{% url 'logout' %}" class="inline">
  {% csrf_token %}<button type="submit" class="link">로그아웃</button>
</form>
```

➡️ 여기서 부르는 것: `LogoutView (Django 기본)` (urls.py:10)

### O2 세션 삭제

📄 `backend/config/urls.py` · **LogoutView (Django 기본)** · 10번째 줄  
🔁 넘기는 방식: DB django_session DELETE

서버의 세션 행을 지우고 쿠키도 무효로 만듭니다.

```python
path("accounts/", include("django.contrib.auth.urls")),       # logout/

# Django 내부 (직접 작성 안 함)
# LogoutView.post → logout(request)   # 세션 삭제
#                → redirect(LOGOUT_REDIRECT_URL)   # = "login"
```

➡️ 여기서 부르는 것: `로그인·로그아웃 후 이동` (settings.py:99)

### O3 로그인 화면으로

📄 `backend/config/settings.py` · **로그인·로그아웃 후 이동** · 99번째 줄  
🔁 넘기는 방식: 302 → /accounts/login/

로그아웃 후 로그인 화면으로 보냅니다. 이후 분석 화면·API 는 로그인이 필요합니다.

```python
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"
```

#### 🌳 호출 따라가기 (함수 → 부르는 함수 → 또 부르는 함수)

```text
로그아웃 버튼 (POST 폼)  (backend/templates/base.html:21)
    └─ LogoutView (Django 기본)  (backend/config/urls.py:10)
        └─ 로그인·로그아웃 후 이동  (backend/config/settings.py:99)
```
