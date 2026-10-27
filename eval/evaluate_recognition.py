"""Measure recognition accuracy, false matches and missed recognitions of the reconstructed backend.

Identities are drawn from Labeled Faces in the Wild (LFW). Each enrolled identity is registered with one
image through POST /register; its other images are then sent to POST /mark-attendance under three capture
conditions, together with images of people who were never enrolled. The backend must be running with an
empty database (set AE_DB to a new file).

Usage: python evaluate_recognition.py LFW_DIR RESULTS_DIR [BACKEND_URL]
"""
import base64
import csv
import io
import json
import random
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import requests
from PIL import Image

SEED = 2026
N_ENROLLED = 200          # roughly the size of a large lecture class
N_IMPOSTORS = 200
PROBES_PER_PERSON = 3
LEVELS = ["100", "200", "300", "400", "500"]


def as_data_url(image: Image.Image) -> str:
    """Encode like the frontend does: JPEG at quality 0.8, sent as a data URL."""
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()


def normal(image: Image.Image, rng) -> Image.Image:
    return image


def dim(image: Image.Image, rng) -> Image.Image:
    """Underexposed capture: 30% of the original brightness plus camera sensor noise."""
    pixels = np.asarray(image, np.float32) * 0.30 + rng.normal(0, 4, (image.height, image.width, 3))
    return Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8))


def low_resolution(image: Image.Image, rng) -> Image.Image:
    """Loss of detail, as when a student stands far from the camera: shrink to 35% and enlarge again."""
    small = image.resize((round(image.width * 0.35), round(image.height * 0.35)), Image.BILINEAR)
    return small.resize(image.size, Image.BILINEAR)


CONDITIONS = {"normal": normal, "dim": dim, "low_resolution": low_resolution}


def choose_identities(lfw: Path):
    people = {d.name: sorted(d.glob("*.jpg")) for d in sorted(lfw.iterdir()) if d.is_dir()}
    rng = random.Random(SEED)
    with_several = sorted(name for name, images in people.items() if len(images) >= 2)
    enrolled = rng.sample(with_several, N_ENROLLED)
    others = sorted(set(people) - set(enrolled))
    impostors = rng.sample(others, N_IMPOSTORS)
    return people, enrolled, impostors


def post(url: str, fields: dict) -> tuple[dict, float, float]:
    """Send the fields as multipart form data, as the browser's FormData does; return JSON and timings in ms."""
    start = time.perf_counter()
    response = requests.post(url, files={k: (None, v) for k, v in fields.items()}, timeout=60)
    elapsed = (time.perf_counter() - start) * 1000
    return response.json(), elapsed, float(response.headers.get("X-Process-Time-Ms", "nan"))


def main(lfw: Path, results: Path, backend: str):
    results.mkdir(parents=True, exist_ok=True)
    people, enrolled, impostors = choose_identities(lfw)

    # Enrolment: if an image is rejected, try the person's next image, as an operator would recapture.
    student_of, probes, enrolment_log = {}, {}, []
    for number, name in enumerate(enrolled, start=1):
        images = people[name]
        for attempt, path in enumerate(images[:-1]):   # keep at least one image for testing
            body, _, _ = post(f"{backend}/register", {
                "name": f"Test Student {number:03d}", "mat_no": f"TEST/{number:03d}",
                "level": LEVELS[(number - 1) % len(LEVELS)], "image": as_data_url(Image.open(path).convert("RGB"))})
            enrolment_log.append({"identity": name, "image": path.name, "accepted": body["success"],
                                  "message": body["message"]})
            if body["success"]:
                student_of[name] = body["user_id"]
                probes[name] = images[attempt + 1:][:PROBES_PER_PERSON]
                break

    rng = np.random.default_rng(SEED)
    rows = []
    for condition, transform in CONDITIONS.items():
        attempts = [(name, path, True) for name in student_of for path in probes[name]]
        attempts += [(name, people[name][0], False) for name in impostors]
        for name, path, genuine in attempts:
            image = transform(Image.open(path).convert("RGB"), rng)
            body, round_trip, server = post(f"{backend}/mark-attendance", {"image": as_data_url(image)})
            matched = body.get("student", {}).get("_id")
            if genuine:
                outcome = ("correct" if matched == student_of[name] else
                           "wrong_identity" if matched else
                           "below_threshold" if body.get("recognised") is False else "no_usable_face")
            else:
                outcome = ("false_accept" if matched else
                           "rejected" if body.get("recognised") is False else "no_usable_face")
            rows.append({"condition": condition, "identity": name, "image": path.name, "genuine": genuine,
                         "outcome": outcome, "similarity": body.get("similarity"), "message": body["message"],
                         "round_trip_ms": round(round_trip, 1), "server_ms": server})

    with open(results / "attempts.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    with open(results / "enrolment.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=enrolment_log[0].keys())
        writer.writeheader()
        writer.writerows(enrolment_log)

    summary = {"seed": SEED, "identities_chosen": N_ENROLLED, "enrolled": len(student_of),
               "enrolment_images_rejected": sum(not e["accepted"] for e in enrolment_log),
               "impostor_identities": N_IMPOSTORS, "conditions": {}}
    for condition in CONDITIONS:
        subset = [r for r in rows if r["condition"] == condition]
        genuine = [r for r in subset if r["genuine"]]
        impostor = [r for r in subset if not r["genuine"]]
        count = lambda rs, outcome: sum(r["outcome"] == outcome for r in rs)
        n_g, n_t = len(genuine), len(subset)
        c, wrong, accepted = count(genuine, "correct"), count(genuine, "wrong_identity"), count(impostor, "false_accept")
        missed = count(genuine, "below_threshold") + count(genuine, "no_usable_face")
        times = [r["round_trip_ms"] for r in subset]
        summary["conditions"][condition] = {
            "Ng": n_g, "impostor_attempts": len(impostor), "Nt": n_t,
            "C": c, "W": wrong + accepted, "wrong_identity": wrong, "impostors_accepted": accepted,
            "R": missed, "R_below_threshold": count(genuine, "below_threshold"),
            "R_no_usable_face": count(genuine, "no_usable_face"),
            "impostors_no_usable_face": count(impostor, "no_usable_face"),
            "accuracy_pct": round(c / n_g * 100, 2), "FMR_pct": round((wrong + accepted) / n_t * 100, 2),
            "MRR_pct": round(missed / n_g * 100, 2),
            "impostor_acceptance_pct": round(accepted / len(impostor) * 100, 2),
            "mean_round_trip_ms": round(statistics.mean(times), 1),
            "p95_round_trip_ms": round(float(np.percentile(times, 95)), 1),
            "mean_server_ms": round(statistics.mean(r["server_ms"] for r in subset), 1)}
    (results / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else "http://127.0.0.1:8000")
