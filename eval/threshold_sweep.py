"""Repeat the recognition evaluation offline at several similarity thresholds.

Uses the backend's own recognition code on exactly the images, conditions and JPEG encoding of
evaluate_recognition.py, and checks that the result at the deployed threshold matches the API run.

Usage: python threshold_sweep.py LFW_DIR RESULTS_DIR   (run after evaluate_recognition.py)
"""
import csv
import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["AE_DB"] = ":memory:"   # importing the app opens a database; keep it in memory
from backend.main import ATTEND_MIN_FACE_PX, ENROL_MIN_FACE_PX, THRESHOLD   # noqa: E402
from backend.recognition import FaceEngine, FaceError, best_match, decode_image   # noqa: E402
from evaluate_recognition import CONDITIONS, PROBES_PER_PERSON, SEED, as_data_url, choose_identities   # noqa: E402

THRESHOLDS = [0.25, 0.30, THRESHOLD, 0.40, 0.45, 0.50, 0.55]


def main(lfw: Path, results: Path):
    engine = FaceEngine(Path(__file__).resolve().parent.parent / "models")
    people, enrolled, impostors = choose_identities(lfw)
    with open(results / "enrolment.csv") as f:
        accepted = {r["identity"]: r["image"] for r in csv.DictReader(f) if r["accepted"] == "True"}

    names = [n for n in enrolled if n in accepted]
    gallery = np.stack([engine.template(decode_image(as_data_url(Image.open(lfw / n / accepted[n]).convert("RGB"))), ENROL_MIN_FACE_PX)
                        for n in names])
    probes = {}
    for n in names:
        images = people[n]
        index = [p.name for p in images].index(accepted[n])
        probes[n] = images[index + 1:][:PROBES_PER_PERSON]

    rng = np.random.default_rng(SEED)
    scored = []   # (condition, genuine, true index or None, best index or None, similarity)
    for condition, transform in CONDITIONS.items():
        attempts = [(n, p, True) for n in names for p in probes[n]] + [(n, people[n][0], False) for n in impostors]
        for name, path, genuine in attempts:
            image = transform(Image.open(path).convert("RGB"), rng)
            truth = names.index(name) if genuine else None
            try:
                best, similarity = best_match(engine.template(decode_image(as_data_url(image)), ATTEND_MIN_FACE_PX), gallery)
            except FaceError:
                best, similarity = None, None
            scored.append((condition, genuine, truth, best, similarity))

    table = []
    for threshold in THRESHOLDS:
        for condition in list(CONDITIONS) + ["all"]:
            subset = [s for s in scored if condition in ("all", s[0])]
            genuine = [s for s in subset if s[1]]
            accepted_ = lambda s: s[4] is not None and s[4] >= threshold
            c = sum(accepted_(s) and s[3] == s[2] for s in genuine)
            w = sum(accepted_(s) and (not s[1] or s[3] != s[2]) for s in subset)
            r = sum(not accepted_(s) for s in genuine)
            table.append({"threshold": round(threshold, 3), "condition": condition, "Ng": len(genuine), "Nt": len(subset),
                          "accuracy_pct": round(c / len(genuine) * 100, 2), "FMR_pct": round(w / len(subset) * 100, 2),
                          "MRR_pct": round(r / len(genuine) * 100, 2)})

    # Consistency check against the API run at the deployed threshold.
    api = json.loads((results / "summary.json").read_text())["conditions"]
    for row in table:
        if row["threshold"] == round(THRESHOLD, 3) and row["condition"] in api:
            a = api[row["condition"]]
            assert (row["accuracy_pct"], row["FMR_pct"], row["MRR_pct"]) == (a["accuracy_pct"], a["FMR_pct"], a["MRR_pct"]), (row, a)

    (results / "threshold_sweep.json").write_text(json.dumps(table, indent=2))
    for row in table:
        print(row)
    print("Consistent with the API run at threshold", THRESHOLD)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
