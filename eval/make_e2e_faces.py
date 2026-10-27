"""Write e2e_faces.js: test photos for the browser tests, taken from people whose images behaved cleanly
in the recognition evaluation (enrolment accepted, first test image recognised, unenrolled person rejected).

Usage: python make_e2e_faces.py LFW_DIR RESULTS_DIR OUTPUT_JS
"""
import base64
import csv
import io
import json
import random
import sys
from pathlib import Path

from PIL import Image

lfw, results, output = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
enrolment = {r["identity"]: r["image"] for r in csv.DictReader(open(results / "enrolment.csv")) if r["accepted"] == "True"}
attempts = list(csv.DictReader(open(results / "attempts.csv")))
normal = [r for r in attempts if r["condition"] == "normal"]
clean = sorted({r["identity"] for r in normal if r["genuine"] == "True" and r["outcome"] == "correct"
                and r["identity"] in enrolment})
first_probe = {}
for r in normal:
    if r["genuine"] == "True":
        first_probe.setdefault(r["identity"], r)
clean = [n for n in clean if first_probe[n]["outcome"] == "correct"]
rejected = sorted(r["identity"] for r in normal if r["genuine"] == "False" and r["outcome"] == "rejected")

rng = random.Random(7)
people = rng.sample(clean, 6)
stranger = rng.choice(rejected)


def data_url(path):
    buffer = io.BytesIO()
    Image.open(path).convert("RGB").save(buffer, "JPEG", quality=90)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()


faces, key = {}, {}
for i, name in enumerate(people, start=1):
    faces[f"s{i}_enrol"] = data_url(lfw / name / enrolment[name])
    faces[f"s{i}_probe"] = data_url(lfw / name / first_probe[name]["image"])
    key[f"Test Student {i:02d}"] = {"identity": name, "enrol": enrolment[name], "probe": first_probe[name]["image"]}
stranger_image = sorted((lfw / stranger).glob("*.jpg"))[0]
faces["stranger"] = data_url(stranger_image)
key["stranger"] = {"identity": stranger, "image": stranger_image.name}

output.write_text("window.__faces = " + json.dumps(faces) + ";\n")
(results / "e2e_identities.json").write_text(json.dumps(key, indent=2))
print(json.dumps(key, indent=2))
