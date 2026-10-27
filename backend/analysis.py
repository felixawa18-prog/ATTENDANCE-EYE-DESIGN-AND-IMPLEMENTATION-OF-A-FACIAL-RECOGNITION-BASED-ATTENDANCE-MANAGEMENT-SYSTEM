"""Plain-language summary of the day's attendance, shown in the frontend's "AI Analysis" panel.

The original service's analysis method is unknown. This module stands in for it with fixed rules,
so no attendance data is sent to any outside service.
"""


def summarise(total: int, present: int, by_level: dict[str, tuple[int, int]], first: str | None, last: str | None) -> str:
    if total == 0:
        return "No students have been registered yet, so there is no attendance to analyse."

    absent = total - present
    rate = present / total * 100
    parts = [f"{present} of {total} registered students ({rate:.1f}%) have been marked present today; "
             f"{absent} {'is' if absent == 1 else 'are'} absent."]
    if present:
        parts.append(f"Check-ins were recorded between {first} and {last}." if first != last
                     else f"The only check-in was recorded at {first}.")
    if len(by_level) > 1:
        levels = "; ".join(f"{level} Level: {p} of {t}" for level, (p, t) in sorted(by_level.items()))
        parts.append(f"By level, {levels}.")
    if rate < 50:
        parts.append("Fewer than half of the registered students are present, so the lecturer may wish "
                     "to follow up with the absent students.")
    elif present == total:
        parts.append("Every registered student is present.")
    return " ".join(parts)
