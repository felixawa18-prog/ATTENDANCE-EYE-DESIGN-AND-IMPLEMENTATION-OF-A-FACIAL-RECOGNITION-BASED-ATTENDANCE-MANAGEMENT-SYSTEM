"""Write the photos for the load test: one per enrolled person, taken from people whose first test image
was recognised correctly in the recognition evaluation (so that every request is a valid attendance attempt).

Usage: python make_load_images.py LFW_DIR RESULTS_DIR
The photos are written to RESULTS_DIR/load_images/.
"""
import csv
import sys
from pathlib import Path

from PIL import Image

lfw, results = Path(sys.argv[1]), Path(sys.argv[2])
enrolment = {r["identity"]: r["image"] for r in csv.DictReader(open(results / "enrolment.csv")) if r["accepted"] == "True"}
attempts = list(csv.DictReader(open(results / "attempts.csv")))
first_probe = {}
for r in attempts:
    if r["condition"] == "normal" and r["genuine"] == "True":
        first_probe.setdefault(r["identity"], r)

output = results / "load_images"
output.mkdir(parents=True, exist_ok=True)
n = 0
for name, enrolled in enrolment.items():
    images = sorted((lfw / name).glob("*.jpg"))
    probe = images[[p.name for p in images].index(enrolled) + 1]   # the image after the enrolment photo
    row = first_probe.get(name)
    if row is None or row["image"] != probe.name or row["outcome"] != "correct":
        continue
    Image.open(probe).convert("RGB").save(output / f"{name}.jpg", "JPEG", quality=80)
    n += 1
print(n, "load-test images written to", output)
