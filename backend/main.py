"""Reconstructed Attendance Eye backend, exposing the HTTP interface that the deployed frontend calls."""
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from fastapi import FastAPI, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .analysis import summarise
from .database import Database
from .recognition import FaceEngine, FaceError, best_match, decode_image

ROOT = Path(__file__).resolve().parent.parent
THRESHOLD = float(os.environ.get("AE_THRESHOLD", "0.363"))   # OpenCV's published cosine threshold for SFace
ENROL_MIN_FACE_PX = 60    # enrolment needs a larger, clearer face than attendance
ATTEND_MIN_FACE_PX = 40
LEVELS = {"100", "200", "300", "400", "500"}

db = Database(Path(os.environ.get("AE_DB", ROOT / "data" / "attendance.db")))
engine = FaceEngine(ROOT / "models")

app = FastAPI(title="Attendance Eye: reconstructed backend")
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("AE_CORS_ORIGINS", "*").split(","),
                   allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def record_processing_time(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Process-Time-Ms"] = f"{(time.perf_counter() - start) * 1000:.1f}"
    return response


def fail(status: int, message: str) -> JSONResponse:
    # The frontend shows `message` for attendance errors and `detail || message` for registration errors.
    return JSONResponse(status_code=status, content={"success": False, "message": message})


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def today() -> str:
    return datetime.now().astimezone().date().isoformat()


def local_time(timestamp: str) -> str:
    return datetime.fromisoformat(timestamp).astimezone().strftime("%H:%M")


@app.get("/")
def root():
    return {"service": "Attendance Eye reconstructed backend", "docs": "/docs"}


@app.post("/register")
def register(name: str = Form(...), mat_no: str = Form(...), level: str = Form(...), image: str = Form(...)):
    name, mat_no, level = " ".join(name.split()), mat_no.strip().upper(), level.strip()
    if not name or not mat_no:
        return fail(400, "Name and matriculation number are required.")
    if level not in LEVELS:
        return fail(400, "Level must be 100, 200, 300, 400 or 500.")
    with db.connect() as conn:
        if conn.execute("SELECT 1 FROM students WHERE mat_no = ?", (mat_no,)).fetchone():
            return fail(409, f"A student with matriculation number {mat_no} is already registered.")
    try:
        template = engine.template(decode_image(image), ENROL_MIN_FACE_PX)
    except FaceError as e:
        return fail(400, str(e))

    student_id = uuid.uuid4().hex
    try:
        with db.connect() as conn:
            conn.execute("INSERT INTO students (id, name, mat_no, level, face_template, created_at) "
                         "VALUES (?, ?, ?, ?, ?, ?)",
                         (student_id, name, mat_no, level, template.tobytes(), now_utc()))
    except sqlite3.IntegrityError:   # another request registered the same number in the meantime
        return fail(409, f"A student with matriculation number {mat_no} is already registered.")
    return {"success": True, "message": f"{name} ({mat_no}) registered successfully.", "user_id": student_id}


@app.post("/mark-attendance")
def mark_attendance(image: str = Form(...)):
    try:
        probe = engine.template(decode_image(image), ATTEND_MIN_FACE_PX)
    except FaceError as e:
        return fail(400, str(e))

    with db.connect() as conn:
        rows = conn.execute("SELECT id, name, mat_no, level, face_template FROM students").fetchall()
        if not rows:
            return fail(404, "No students are registered yet.")
        templates = np.stack([np.frombuffer(r["face_template"], np.float32) for r in rows])
        index, similarity = best_match(probe, templates)
        if similarity < THRESHOLD:
            return {"success": False, "recognised": False, "similarity": round(similarity, 4),
                    "message": "Face not recognised. Please register first or try again."}

        student = rows[index]
        found = {"_id": student["id"], "name": student["name"], "mat_no": student["mat_no"]}
        try:
            conn.execute("INSERT INTO attendance (id, student_id, date, timestamp, similarity) VALUES (?, ?, ?, ?, ?)",
                         (uuid.uuid4().hex, student["id"], today(), now_utc(), similarity))
        except sqlite3.IntegrityError:   # UNIQUE (student_id, date): already marked today
            earlier = conn.execute("SELECT timestamp FROM attendance WHERE student_id = ? AND date = ?",
                                   (student["id"], today())).fetchone()
            return {"success": False, "recognised": True, "already_marked": True, "student": found,
                    "similarity": round(similarity, 4),
                    "message": f"Attendance already marked today for {student['name']} "
                               f"at {local_time(earlier['timestamp'])}."}
    return {"success": True, "recognised": True, "student": found, "similarity": round(similarity, 4),
            "message": f"Attendance marked for {student['name']} ({student['mat_no']})."}


@app.get("/users")
def users():
    with db.connect() as conn:
        rows = conn.execute("SELECT id, name, mat_no, level, created_at FROM students "
                            "ORDER BY created_at DESC, rowid DESC").fetchall()
    return [{"_id": r["id"], "name": r["name"], "mat_no": r["mat_no"], "level": r["level"],
             "created_at": r["created_at"]} for r in rows]


@app.delete("/users/{user_id}")
def delete_user(user_id: str):
    with db.connect() as conn:
        student = conn.execute("SELECT name FROM students WHERE id = ?", (user_id,)).fetchone()
        if student is None:
            return fail(404, "Student not found.")
        conn.execute("DELETE FROM students WHERE id = ?", (user_id,))   # attendance rows go with it (CASCADE)
    return {"success": True, "message": f"{student['name']} deleted successfully."}


@app.get("/attendance")
def attendance():
    with db.connect() as conn:
        rows = conn.execute("SELECT a.id, a.student_id, s.name, s.mat_no, s.level, a.timestamp, a.status, a.similarity "
                            "FROM attendance a JOIN students s ON s.id = a.student_id "
                            "WHERE a.date = ? ORDER BY a.timestamp DESC, a.rowid DESC", (today(),)).fetchall()
    return [{"_id": r["id"], "student_id": r["student_id"], "name": r["name"], "mat_no": r["mat_no"],
             "level": r["level"], "timestamp": r["timestamp"], "status": r["status"],
             "similarity": round(r["similarity"], 4)} for r in rows]


@app.get("/attendance-summary")
def attendance_summary():
    with db.connect() as conn:
        levels = conn.execute("SELECT s.level, COUNT(*) AS registered, COUNT(a.id) AS present "
                              "FROM students s LEFT JOIN attendance a ON a.student_id = s.id AND a.date = ? "
                              "GROUP BY s.level", (today(),)).fetchall()
        times = conn.execute("SELECT MIN(timestamp), MAX(timestamp) FROM attendance WHERE date = ?",
                             (today(),)).fetchone()
    total = sum(r["registered"] for r in levels)
    present = sum(r["present"] for r in levels)
    by_level = {r["level"]: (r["present"], r["registered"]) for r in levels}
    first, last = (local_time(t) if t else None for t in times)
    return {"date": today(),
            "summary": {"total_registered": total, "total_present": present, "total_absent": total - present,
                        "attendance_rate": round(present / total * 100, 1) if total else 0.0},
            "ai_analysis": summarise(total, present, by_level, first, last)}
