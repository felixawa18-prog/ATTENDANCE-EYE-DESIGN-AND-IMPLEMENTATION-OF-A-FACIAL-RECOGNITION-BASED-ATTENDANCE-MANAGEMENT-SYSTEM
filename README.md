# Attendance Eye

A facial recognition attendance management system. A student looks at the camera, the system recognises
the face and records the student as present, and the lecturer sees the day's attendance and a summary.

Final-year project, Department of Computer Science, Faculty of Computing, University of Port Harcourt:
*Attendance Eye: Design and Implementation of a Facial Recognition-Based Attendance Management System*,
by Felix Emmanuel Awa (U2022/5570116), supervised by Dr Laud Charles Ochei.

## About this repository

The original backend (`https://ai-attendance-backend-vx4s.onrender.com`) was suspended, and its source code
could not be recovered. This repository holds a **reconstruction** of it, built to the same HTTP interface
that the deployed frontend calls, so the system can be tested end to end. It follows the design proposed
in Chapter 3 of the report: Python, FastAPI, OpenCV with a pre-trained face model, and SQLite for the
prototype. The report refers to this repository as the *replica folder*.

It is **not** the original backend. Results obtained with it describe this reconstruction, and the report
says so wherever they are used.

| Path | Contents |
|---|---|
| `backend/main.py` | FastAPI application: the six endpoints the frontend uses |
| `backend/recognition.py` | Face detection (YuNet) and recognition (SFace), from OpenCV |
| `backend/database.py` | SQLite tables for students and attendance |
| `backend/analysis.py` | Rule-based text for the "AI Analysis" panel (no outside AI service) |
| `models/` | `face_detection_yunet_2023mar.onnx` (MIT licence) and `face_recognition_sface_2021dec.onnx` (Apache 2.0 licence) from the [OpenCV model zoo](https://github.com/opencv/opencv_zoo); the licence texts are in the same folder |
| `frontend/` | The compiled frontend (Next.js, written in TypeScript), copied from the deployed Netlify site; the only change is the backend address, now `http://localhost:8000`. Its TypeScript source is not in this repository |
| `serve_frontend.py`, `run.sh` | Serve the frontend at port 3000 and start the backend at port 8000 |
| `eval/` | Recognition evaluation, threshold sweep, load test and the simulated camera used for browser tests |

## Running it

Requires Python 3.12 (tested on Linux).

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
./run.sh
```

Then open <http://localhost:3000> in Chrome or Firefox on the same computer and allow camera access.
Data is stored in `data/attendance.db`, which is created on first use; delete that file to start with an
empty system. It holds the students' face templates, so it is kept out of Git.

## Interface

| Method and path | Form fields | Response |
|---|---|---|
| `POST /register` | `name`, `mat_no`, `level`, `image` (JPEG data URL) | `{success, message, user_id}` |
| `POST /mark-attendance` | `image` | `{success, recognised, message, student, similarity}` |
| `GET /users` | | list of `{_id, name, mat_no, level, created_at}` |
| `DELETE /users/{id}` | | `{success, message}` |
| `GET /attendance` | | today's records: `{_id, name, mat_no, level, timestamp, status, similarity}` |
| `GET /attendance-summary` | | `{summary: {total_registered, total_present, total_absent, attendance_rate}, ai_analysis}` |

## Recognition rules

* A face is accepted when YuNet detects it with a score of at least 0.9.
* If a second face is at least half the size of the largest, the image is rejected as ambiguous.
* Enrolment needs a face at least 60 px wide; attendance needs at least 40 px.
* The face is aligned to 112 × 112 px and SFace turns it into 128 numbers, stored without the photo.
* A probe is matched to the enrolled student with the highest cosine similarity, if that similarity is at
  least 0.363 (OpenCV's published threshold for SFace; change it with the `AE_THRESHOLD` environment variable).
* A student can be marked present once per day.

## Results used in Chapter Four (26 October 2026)

All results are in `eval/results/`. They were produced on the test laptop (Intel Core i3-10110U, 16 GB RAM,
Linux Mint 22.1), on battery in power-saver mode.

| File | Contents | Report |
|---|---|---|
| `summary.json`, `attempts.csv`, `enrolment.csv`, `eval_stdout.txt` | Recognition evaluation: 195 enrolled LFW identities, 1,731 attempts under three conditions | Table 4.15 |
| `threshold_sweep.json` | The same attempts re-scored at thresholds from 0.25 to 0.55 | Table 4.16 |
| `load/u50_*.csv`, `load/u100_*.csv`, `load/u200_*.csv` | Locust results; `load/first_attempt_with_rejected_images/` holds the abandoned first run | Table 4.13 |
| `e2e_results.json`, `e2e_identities.json`, `e2e_timing.json` | Browser tests TC15 to TC23, the photos used, and the 24 timed attempts | Table 4.11, Section 4.5.5 |
| `server_timing_check.json` | Server time for new records versus refused duplicates | Section 4.5.5 |

## Reproducing the evaluation

The face photos come from Labeled Faces in the Wild (LFW), which is not included in this repository
(about 360 MB). The test databases and the photo files derived from LFW are not included either; the
commands below re-create them.

```bash
cd eval
# 1. Labeled Faces in the Wild (the official site was down; this is the mirror scikit-learn uses)
mkdir -p data && curl -L -o data/lfw.tgz https://ndownloader.figshare.com/files/5976018 && tar xzf data/lfw.tgz -C data
# 2. Start a backend with an empty database (in another terminal, from the repository folder)
AE_DB=eval/results/eval.db .venv/bin/uvicorn backend.main:app --port 8000
# 3. Recognition evaluation, then the threshold sweep
../.venv/bin/python evaluate_recognition.py data/lfw results
../.venv/bin/python threshold_sweep.py data/lfw results
# 4. Load test: one correctly recognised photo per enrolled person, then Locust at 50, 100 and 200 users
../.venv/bin/python make_load_images.py data/lfw results
LOAD_IMAGES=results/load_images ../.venv/bin/locust -f locustfile.py --headless -u 50 -r 10 -t 120s \
    --host http://127.0.0.1:8000 --csv results/load/u50 --only-summary
# 5. Photos for the browser tests
../.venv/bin/python make_e2e_faces.py data/lfw results results/e2e_faces.js
```

The browser tests used `e2e_camera_mock.js` (passed to the page as an init script), `results/e2e_faces.js`
and `e2e_helpers.js`, run in Chrome against `http://localhost:3000`.

`eval/data/` can be deleted once the evaluation is no longer needed.
