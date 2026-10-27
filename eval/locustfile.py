"""Load test: each simulated user opens the dashboard, marks attendance and checks the reports.

The backend should hold the enrolled students from the recognition evaluation, and LOAD_IMAGES should
point to a folder of face images of those students (one JPEG per student) that the backend recognises
correctly, so that every failure counted by Locust is a server failure rather than a rejected photo.

Usage: locust -f locustfile.py --headless -u 50 -r 10 -t 120s --host http://127.0.0.1:8000 --csv out/50
"""
import base64
import os
import random
from pathlib import Path

from locust import HttpUser, between, task

IMAGES = [("data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode())
          for p in sorted(Path(os.environ["LOAD_IMAGES"]).glob("*.jpg"))]


class Student(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        # The frontend requests these three lists when the page first loads.
        self.client.get("/users")
        self.client.get("/attendance")
        self.client.get("/attendance-summary")

    @task(1)
    def mark_attendance(self):
        self.client.post("/mark-attendance", files={"image": (None, random.choice(IMAGES))})

    @task(2)
    def todays_attendance(self):
        self.client.get("/attendance")

    @task(2)
    def summary(self):
        self.client.get("/attendance-summary")

    @task(1)
    def registered_students(self):
        self.client.get("/users")
