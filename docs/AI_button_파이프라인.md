# AI button 파이프라인

화면설계(UI 디자인 되어 있어야 합니다.)

AI 분석버튼

## 흐름

AI 분석버튼 -> javascript -> http fetch -> django -> 프로젝트 주소(엔드포인트) urls.py -> 앱 주소(엔드포인트) urls.py -> views.py -> 동기 비동기(ai) -> celery 작업등록 -> tasks.py -> services.py -> FastAPI -> 추론 random forest -> PostgreSQL -> javascript

| # | 단계 | 파일 | 함수 |
|---|---|---|---|
| 1 | 화면설계 | analyses/page_views.py · templates/analyses/index.html | analyses_index |
| 2 | AI 분석버튼 | templates/analyses/index.html | `<button type="submit">` |
| 3 | javascript | static/js/analyses.js | submit 핸들러 |
| 4 | http fetch | static/js/analyses.js | api() → fetch POST |
| 5 | django | config/settings.py | ROOT_URLCONF |
| 6 | 프로젝트 urls.py | config/urls.py | include("analyses.urls") |
| 7 | 앱 urls.py | analyses/urls.py | router.register |
| 8 | views.py | analyses/views.py | AnalysisJobViewSet.create |
| 9 | 동기 비동기 | analyses/views.py | on_commit + 201 |
| 10 | celery 작업등록 | analyses/views.py · config/celery.py | enqueue_analysis → delay |
| 11 | tasks.py | analyses/tasks.py | run_analysis |
| 12 | services.py | analyses/services.py | predict_video → _post |
| 13 | FastAPI | ai_service/routers/predictions.py | predict → _analyze |
| 14 | 추론 random forest | ai_service/services/action_inference.py | predict_track |
| 15 | PostgreSQL | analyses/tasks.py | _save_predictions → _complete |
| 16 | javascript | static/js/analyses.js | startPolling → showJob |

### 1. 화면설계 (UI 디자인)
`analyses/page_views.py` · 21번째 줄

화면 주소 `/analyses/` 로 들어오면 `analyses_index` 가 선택지(동작·카메라·업로드 제한)를 넣어 `index.html` 을 그립니다. `@ensure_csrf_cookie` 로 뒤에서 fetch(POST)에 쓸 CSRF 쿠키도 미리 줍니다.

```python
@login_required
@ensure_csrf_cookie                              # fetch(POST)에 쓸 CSRF 쿠키 보장
def analyses_index(request):
    return render(request, "analyses/index.html", {
        "actions": Action.choices,
        "exercises": Exercise.choices,
        "views": AnalysisJob.CameraView.choices,
        "form_max_seconds": settings.FORM_CAPTURE_MAX_SECONDS,
        "cameras": [(url, _camera_label(i, url)) for i, url in enumerate(settings.ALLOWED_CAMERA_URLS)],
        "capture_seconds": settings.CAMERA_CAPTURE_SECONDS,
        "max_upload_mb": settings.MAX_UPLOAD_MB,
        "allowed_ext": ", ".join(settings.ALLOWED_VIDEO_EXTENSIONS),
    })
```

➡️ **타고 가는 줄:** `render(request, "analyses/index.html", …)` → 화면의 버튼

### 2. AI 분석버튼
`templates/analyses/index.html` · 19번째 줄

버튼은 `type="submit"` 이라 누르면 폼의 **submit 이벤트**가 일어납니다. 숨은 값 `input_type`(UPLOAD/IPCAM) · `task_type`(ACTION/FORM) 이 같이 실립니다.

```html
<form id="analyze-form" class="form" enctype="multipart/form-data">
  {% csrf_token %}
  <input type="hidden" name="input_type" id="input_type" value="UPLOAD">
  <input type="hidden" name="task_type" id="task_type" value="ACTION">
  …
  <button type="submit" id="start-btn" class="btn-lg">AI 분석 시작</button>
</form>
```

➡️ **타고 가는 줄:** `<button type="submit" id="start-btn">` → analyses.js 의 `form.addEventListener("submit", …)`

### 3. javascript (관련 코드 js)
`static/js/analyses.js` · 12번째 줄

기본 새로고침을 막고(`preventDefault`) FormData 로 영상·선택값을 묶습니다. 요청 중에는 버튼을 잠가(`startBtn.disabled = true`) 두 번 눌러도 중복 요청이 가지 않습니다.

```js
const $ = (sel) => document.querySelector(sel);
const form = $("#analyze-form"), startBtn = $("#start-btn");
let pollTimer = null, currentId = null;
// …
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

➡️ **타고 가는 줄:** `const job = await api(API, { method: "POST", body: fd });` (93번째 줄) → `api()`

### 4. http fetch
`static/js/analyses.js` · 3번째 줄

모든 요청이 지나는 공통 통로입니다. `fetch` 로 **POST `/api/v1/analyses/`** 를 보내고, 쿠키의 `csrftoken` 을 `X-CSRFToken` 헤더에 넣습니다. 응답이 400 등이면 throw → submit 의 catch 가 오류 문구를 보여 줍니다.

```js
const API = "/api/v1/analyses/";
// …
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
```

➡️ **타고 가는 줄:** `fetch(url, { method: "POST", … })` → 네트워크 → **Django 서버**

### 5. django
`config/settings.py` · 36번째 줄

Django 가 HTTP 요청을 받으면 미들웨어(세션 로그인 확인·CSRF 검사)를 지난 뒤 `ROOT_URLCONF` 에 적힌 `config/urls.py` 부터 주소를 찾습니다.

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

➡️ **타고 가는 줄:** `ROOT_URLCONF = "config.urls"` → `config/urls.py`

### 6. 프로젝트 주소(엔드포인트) urls.py
`config/urls.py` · 7번째 줄

`/api/v1/analyses/` 는 앞의 `admin/`, `accounts/` 와 맞지 않으므로 `path("", include("analyses.urls"))` 를 타고 analyses 앱으로 넘어갑니다.

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

➡️ **타고 가는 줄:** `path("", include("analyses.urls"))` → `analyses/urls.py`

### 7. 앱 주소(엔드포인트) urls.py
`analyses/urls.py` · 7번째 줄

Router 가 `analyses` 를 `AnalysisJobViewSet` 에 연결합니다. 이 프로젝트는 `api_urls.py` 를 따로 두지 않고 **한 파일**에서 API 주소(`api/v1/`)와 화면 주소(`analyses/`, `dashboard/`)를 같이 관리합니다.

| 요청 | ViewSet 함수 |
|---|---|
| POST `/api/v1/analyses/` | `create` |
| GET `/api/v1/analyses/` | `list` |
| GET `/api/v1/analyses/{id}/` | `retrieve` |
| GET `/api/v1/analyses/{id}/status/` | `job_status` |

```python
router = DefaultRouter()
router.register("analyses", AnalysisJobViewSet, basename="analysis")

urlpatterns = [
    path("api/v1/", include(router.urls)),
    path("analyses/", page_views.analyses_index, name="analyses_index"),
    path("dashboard/", page_views.dashboard, name="dashboard"),
]
```

➡️ **타고 가는 줄:** POST 이므로 `router.register("analyses", AnalysisJobViewSet)` → `views.py` 의 `create()`

### 8. views.py
`analyses/views.py` · 33번째 줄

`get_serializer_class` 가 create 일 때 `AnalysisJobCreateSerializer` 를 골라 입력을 검사하고(`is_valid`), 통과하면 작업을 **PENDING** 으로 DB 에 저장합니다. 남의 작업은 `get_queryset` 에서 걸러져 404.

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

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = serializer.save(user=request.user)            # status = PENDING
        # DB 커밋이 끝난 뒤에 Celery 작업 등록 → Worker가 아직 없는 Job을 찾는 일이 없음
        transaction.on_commit(lambda: enqueue_analysis(job.pk))
        return Response(AnalysisJobSerializer(job, context={"request": request}).data,
                        status=http_status.HTTP_201_CREATED)
```

➡️ **타고 가는 줄:** `serializer.is_valid(raise_exception=True)` → `serializers.py validate()` / `transaction.on_commit(lambda: enqueue_analysis(job.pk))` → 9, 10

### 9. 동기 비동기 (ai)
`analyses/views.py` · 51번째 줄

**동기:** 사용자에게는 분석 결과를 기다리지 않고 바로 `201` 응답(작업 번호)을 돌려줍니다.  
**비동기:** 몇 초~수십 초 걸리는 AI 분석은 Celery 에 넘깁니다. `on_commit` 으로 **DB 저장이 끝난 뒤** 등록해서 Worker 가 아직 없는 작업을 찾는 일이 없습니다.

```python
job = serializer.save(user=request.user)            # status = PENDING
# DB 커밋이 끝난 뒤에 Celery 작업 등록 → Worker가 아직 없는 Job을 찾는 일이 없음
transaction.on_commit(lambda: enqueue_analysis(job.pk))
return Response(AnalysisJobSerializer(job, context={"request": request}).data,
                status=http_status.HTTP_201_CREATED)
```

➡️ **타고 가는 줄:** `enqueue_analysis(job.pk)` → 10

### 10. celery 작업등록
`analyses/views.py` · 90번째 줄

`run_analysis.delay(job_id)` 로 **job_id 만** Redis 대기열에 넣습니다 (영상은 media 폴더에 파일로 있음). Redis 가 꺼져 있으면 바로 FAILED 로 남겨 화면에서 알 수 있습니다.

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

Celery 앱 설정 (`config/celery.py`) — tasks.py 를 자동으로 찾는 곳

```python
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
```

➡️ **타고 가는 줄:** `run_analysis.delay(job_id)` → Redis → Celery Worker 가 꺼내서 `tasks.py run_analysis()`

### 11. tasks.py
`analyses/tasks.py` · 41번째 줄

① PENDING 일 때만 PROCESSING 으로 바꿔 같은 작업이 두 번 실행되지 않게 하고(조건부 UPDATE) ② 영상 경로를 확보한 뒤 ③ `task_type` 으로 AI 서버를 고릅니다. 동작 인식이면 `predict_video`.

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

➡️ **타고 가는 줄:** `result = predict_video(video_path)` → `services.py`

### 12. services.py
`analyses/services.py` · 24번째 줄

httpx 로 영상을 **FastAPI** 에 보냅니다. 400/422 는 입력 문제(AIInputError), 그 밖의 오류·시간 초과는 서버 문제(AIServiceError)로 나눠 tasks.py 가 FAILED 메시지를 남깁니다.

```python
def predict_video(video_path: str) -> dict:
    """6개 동작 인식 (ai_service)"""
    url = f"{settings.FASTAPI_URL.rstrip('/')}/api/v1/predict/"
    return _post(url, video_path, settings.FASTAPI_TIMEOUT_SEC, "AI 서버")
    # …
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

➡️ **타고 가는 줄:** `httpx.post(url, files={"file": …})` — url = `FASTAPI_URL` + `/api/v1/predict/` (Docker 에서는 `http://fastapi:8001`) → FastAPI `predict()`

### 13. FastAPI
`ai_service/routers/predictions.py` · 29번째 줄

영상을 임시 파일로 받고, 무거운 추론은 `run_in_threadpool` 로 돌려 서버가 멈추지 않게 합니다. 모델은 서버 시작 때 한 번만 불러 둔 것(`get_bundle()`)을 씁니다.

```python
router = APIRouter(prefix="/api/v1", tags=["predict"])
    # …
def _analyze(path: str):
    bundle = get_bundle()
    video = extract_tracks(path, bundle, max_seconds=MAX_DURATION_SEC)
    return video, predict_video(video, bundle)
    # …
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
```

➡️ **타고 가는 줄:** `_analyze()` → `extract_tracks()`(YOLO Pose) → `predict_video()` → `predict_track()`

### 14. 추론 random forest
`ai_service/services/action_inference.py` · 35번째 줄

먼저 `extract_tracks` 가 YOLO11n-Pose + ByteTrack 으로 사람마다 관절 17개를 찾아 Frame 마다 38개 특징을 만듭니다. 여기서는 그 시계열을 30 Step 으로 맞춰(30×38=1140) **Random Forest `predict_proba`** 로 6개 동작 확률을 구하고, 1·2위 차이(margin)가 0.05 미만이면 '판단 불확실'로 표시합니다.

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
```

관절 추출 (YOLO Pose + ByteTrack) — `ai_service/services/pose_pipeline.py`

```python
res = bundle.pose.track(
    source=frame, persist=frame_id > 0,
    tracker=bundle.multi_person.get("tracker", "bytetrack.yaml"),
    imgsz=int(cfg.get("image_size", 640)),
    conf=float(cfg.get("person_confidence", 0.25)),
    device=bundle.device, verbose=False,
)[0]
    # …
    for i in range(min(len(ids), len(xy))):
        tid = int(ids[i])
        s = tracks.setdefault(tid, TrackSeries(tid))
        s.times.append(now)
        s.features.append(feature_from_keypoints(xy[i]))
```

➡️ **타고 가는 줄:** JSON 으로 응답 → services.py 의 `res.json()` → tasks.py 로 돌아와 `_save_predictions(job, result)`

### 15. PostgreSQL
`analyses/tasks.py` · 72번째 줄

**FastAPI 가 아니라 Celery(tasks.py)가 Django ORM 으로** 저장합니다. 사람별 결과를 `bulk_create` 로 한 번에 넣고, `_complete` 에서 상태를 **COMPLETED** 로 바꿉니다. 트랜잭션이라 결과 일부만 저장되는 일이 없습니다.

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
    # …
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

저장되는 테이블 (`analyses/models.py`)

```python
class PersonPrediction(models.Model):
    job = models.ForeignKey(
        AnalysisJob, on_delete=models.CASCADE,
        related_name="predictions", verbose_name="분석 작업",
    )
    track_id = models.IntegerField("Track ID(영상 내 추적 번호)")
    action_label = models.CharField("예측 동작", max_length=30, choices=Action.choices)
    confidence = models.FloatField("Confidence")
    second_label = models.CharField("2순위 동작", max_length=30, blank=True)
    second_confidence = models.FloatField("2순위 Confidence", null=True, blank=True)
    margin = models.FloatField("1·2순위 차이", null=True, blank=True)
    uncertain = models.BooleanField("판단 불확실", default=False)
```

➡️ **타고 가는 줄:** 화면은 1초마다 상태를 묻고 있음 → 16

### 16. javascript (결과 표시)
`static/js/analyses.js` · 106번째 줄

1초마다 GET `/api/v1/analyses/{id}/status/` 로 상태만 가볍게 묻고(`job_status`), `done` 이면 상세 GET 으로 결과를 받아 `showJob()` 이 사람별 예측 표·영상을 그립니다.

```js
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

상태 API (`analyses/views.py`)

```python
@action(detail=True, methods=["get"], url_path="status", url_name="status")
def job_status(self, request, pk=None):
    job = self.get_object()
    is_form = job.task_type == AnalysisJob.TaskType.FORM
    return Response({
        "id": job.id,
        "status": job.status,
        "status_display": job.get_status_display(),
        "done": job.status in (AnalysisJob.Status.COMPLETED, AnalysisJob.Status.FAILED),
        # 1초마다 불리는 API → 작업 종류에 맞는 개수만 셈 (COUNT 쿼리 2번 → 1번)
        "prediction_count": 0 if is_form else job.predictions.count(),
        "rep_count": job.reps.count() if is_form else 0,
        "result_message": job.result_message,
        "error_message": job.error_message,
    })
```

결과 그리기 (`analyses.js`)

```js
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
```

➡️ **타고 가는 줄:** `` api(`${API}${id}/status/`) `` → `views.py job_status()` → `done` 이면 `showJob(...)`

---

## 메모

- **POST → 데이터 저장** : 분석 요청 `POST /api/v1/analyses/` → `create()` → DB 에 작업 저장
- **GET → 데이터 가져오기** : 상태 `GET /api/v1/analyses/{id}/status/`, 결과 `GET /api/v1/analyses/{id}/`
- 버튼은 POST 한 번, 그 뒤 화면은 GET 을 1초마다 → "메서드로 어떤 요청인지" 질문이 나올 확률이 높다.
- 동기 = 사용자 응답(201)은 바로, 비동기 = AI 분석은 Celery 가 뒤에서.
- DB 저장은 FastAPI 가 아니라 Celery(tasks.py)가 Django ORM 으로.
