"""Two-side comparison and the PDF inspection report."""

from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

GOOD_BOARD_LABELS = {"goodpcb", "goodboard", "normalpcb", "normalboard", "nodefect", "defectfree"}
# Checked in order, so the more specific keywords come first.
REPAIR_ADVICE = (
    (("insufficient",), "Add solder and reflow the joint until a smooth concave fillet covers the pad and lead."),
    (("excess", "bridge"), "Remove the extra solder with desoldering braid, then reflow and check that no pins are bridged."),
    (("short",), "Find and remove the copper or solder bridge between the two conductors, then check isolation with a multimeter."),
    (("open", "breakoff", "break", "crack"), "Repair the broken trace with a jumper wire or conductive ink and confirm continuity."),
    (("mousebite",), "Smooth the damaged board edge after depaneling; reject the board if the copper near the edge is cut."),
    (("spurious", "spur"), "Scrape off the unwanted copper with a fine blade and confirm the nearby nets are isolated."),
    (("hole",), "Drill the missing hole to the drawing size, or reject the board if it is a plated via."),
    (("misalign", "allign", "align", "shift", "tomb"), "Reflow the part and re-seat it centred on its pads."),
    (("microcontroller", "driver", "missing"), "Place and solder the missing part according to the BOM and assembly drawing."),
    (("burn", "burnt", "burnout"), "Replace the damaged part and clean the area; find the cause of overheating before powering the board again."),
)
GENERIC_ADVICE = "Inspect this area by eye or under magnification, then rework or reject it under your QA standard."


def normalise(name: str) -> str:
    return "".join(character for character in name.lower() if character.isalnum())


def is_good_label(name: str) -> bool:
    return normalise(name) in GOOD_BOARD_LABELS


def repair_advice(name: str) -> str:
    key = normalise(name)
    return next((advice for words, advice in REPAIR_ADVICE if any(word in key for word in words)), GENERIC_ADVICE)


def side_summary(scan: dict) -> dict:
    defects = [finding for finding in scan["findings"] if not is_good_label(finding["name"])]
    types: dict[str, dict] = {}
    for finding in defects:
        entry = types.setdefault(finding["name"], {"name": finding["name"], "count": 0, "confidence": 0.0})
        entry["count"] += 1
        entry["confidence"] = max(entry["confidence"], finding["confidence"])
    outcome = "defect" if defects else "good" if any(is_good_label(f["name"]) for f in scan["findings"]) else "unknown"
    return {"outcome": outcome, "defect_count": len(defects), "types": sorted(types.values(), key=lambda t: -t["count"])}


def compare_sides(front: dict, back: dict) -> dict:
    sides = {"front": side_summary(front), "back": side_summary(back)}
    names = list(dict.fromkeys([t["name"] for t in sides["front"]["types"]] + [t["name"] for t in sides["back"]["types"]]))
    rows = []
    for name in names:
        on_front = next((t for t in sides["front"]["types"] if t["name"] == name), None)
        on_back = next((t for t in sides["back"]["types"] if t["name"] == name), None)
        where = "both" if on_front and on_back else "front" if on_front else "back"
        rows.append({"name": name, "front": on_front, "back": on_back, "where": where, "fix": repair_advice(name)})

    outcomes = {sides["front"]["outcome"], sides["back"]["outcome"]}
    overall = "defect" if "defect" in outcomes else "good" if outcomes == {"good"} else "unknown"
    label = {"defect": "has defects", "good": "is good", "unknown": "could not be confirmed"}
    differences = []
    if sides["front"]["outcome"] != sides["back"]["outcome"]:
        differences.append(f"The front {label[sides['front']['outcome']]}, but the back {label[sides['back']['outcome']]}.")
    front_count, back_count = sides["front"]["defect_count"], sides["back"]["defect_count"]
    if front_count or back_count:
        if front_count == back_count:
            differences.append(f"Both sides have {front_count} defect{'s' if front_count != 1 else ''}.")
        else:
            worse = "front" if front_count > back_count else "back"
            differences.append(f"The front has {front_count} defect{'s' if front_count != 1 else ''} and the back has "
                               f"{back_count}; the {worse} needs the most rework.")
    for row in rows:
        if row["where"] == "both":
            differences.append(f"{row['name']} is on both sides, which points to a process problem rather than a single bad joint.")
        else:
            differences.append(f"{row['name']} is only on the {row['where']} side.")
    if not differences:
        differences.append("No difference: neither side shows a defect.")
    return {"overall": overall, "sides": sides, "rows": rows, "differences": differences}


def defect_type_stats(history: list[dict], class_names: list[str]) -> list[dict]:
    """Per defect type: detections, scans affected and confidence, least detected first."""
    stats = {name: {"name": name, "count": 0, "scans": 0, "confidences": []} for name in class_names if not is_good_label(name)}
    for scan in history:
        seen = set()
        for finding in scan["findings"]:
            if is_good_label(finding["name"]):
                continue
            entry = stats.setdefault(finding["name"], {"name": finding["name"], "count": 0, "scans": 0, "confidences": []})
            entry["count"] += 1
            entry["confidences"].append(finding["confidence"])
            if finding["name"] not in seen:
                entry["scans"] += 1
                seen.add(finding["name"])
    rows = []
    for entry in stats.values():
        values = entry.pop("confidences")
        entry.update(average=sum(values) / len(values) if values else None, low=min(values, default=None), high=max(values, default=None))
        rows.append(entry)
    return sorted(rows, key=lambda row: (row["count"], row["average"] or 0, row["name"].lower()))


def percent(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def stamp(value: str) -> str:
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%d %b %Y %H:%M")
    except (TypeError, ValueError):
        return value or "—"


def build_report_pdf(state: dict) -> bytes:
    history, pairs = state.get("history", []), state.get("pairs", [])
    styles = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=styles["BodyText"], fontSize=8, leading=10)
    green, light, line = colors.HexColor("#19835c"), colors.HexColor("#eff7f2"), colors.HexColor("#d6e5db")

    def table(rows: list[list], widths: list[float], highlight: list[int] = ()) -> Table:
        body = [[Paragraph(str(cell), small) for cell in row] for row in rows]
        result = Table(body, colWidths=[w * mm for w in widths], repeatRows=1)
        style = [("BACKGROUND", (0, 0), (-1, 0), green), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                 ("GRID", (0, 0), (-1, -1), 0.4, line), ("VALIGN", (0, 0), (-1, -1), "TOP")]
        style += [("BACKGROUND", (0, row), (-1, row), colors.HexColor("#fff4e7")) for row in highlight]
        result.setStyle(TableStyle(style))
        return result

    outcomes = [side_summary(scan)["outcome"] for scan in history]
    story = [
        Paragraph("PCB Inspection Report", styles["Title"]),
        Paragraph(f"Generated {datetime.now().strftime('%d %b %Y %H:%M')} · {len(history)} saved scans", styles["BodyText"]),
        Spacer(1, 6 * mm),
        table([["Scans", "Good", "Defective", "Not confirmed", "Two-side checks"],
               [len(history), outcomes.count("good"), outcomes.count("defect"), outcomes.count("unknown"), len(pairs)]],
              [34, 34, 34, 34, 34]),
        Spacer(1, 7 * mm),
        Paragraph("Defect types — least detected first", styles["Heading2"]),
    ]
    stats = defect_type_stats(history, [item["name"] for item in state.get("classes", [])])
    if stats:
        found = [row for row in stats if row["count"]]
        fewest = found[0]["count"] if found else 0
        least = [row for row in found if row["count"] == fewest]
        if least:
            story.append(Paragraph(
                "Least detected: " + ", ".join(
                    f"<b>{row['name']}</b> ({row['count']} detection{'s' if row['count'] != 1 else ''}, average confidence "
                    f"{percent(row['average'])}, range {percent(row['low'])}–{percent(row['high'])})" for row in least) + ".",
                styles["BodyText"]))
        missing = [row["name"] for row in stats if not row["count"]]
        if missing:
            story.append(Paragraph("Not detected in any saved scan: " + ", ".join(missing) + ".", styles["BodyText"]))
        story.append(Spacer(1, 3 * mm))
        rows = [["Defect type", "Detections", "Scans", "Avg confidence", "Lowest", "Highest", "What to change"]]
        rows += [[row["name"], row["count"], row["scans"], percent(row["average"]), percent(row["low"]), percent(row["high"]),
                  repair_advice(row["name"])] for row in stats]
        story.append(table(rows, [28, 18, 13, 20, 15, 15, 71], highlight=[i + 1 for i, row in enumerate(stats) if row["count"] == fewest]))
    else:
        story.append(Paragraph("No defect types recorded yet.", styles["BodyText"]))

    if pairs:
        story += [Spacer(1, 7 * mm), Paragraph("Two-side comparisons", styles["Heading2"])]
        rows = [["Date", "Result", "Front", "Back", "Differences"]]
        for pair in pairs[:30]:
            comparison = pair["comparison"]
            describe = lambda side: ", ".join(f"{t['name']} ×{t['count']} ({percent(t['confidence'])})" for t in comparison["sides"][side]["types"]) or comparison["sides"][side]["outcome"].title()
            rows.append([stamp(pair["created_at"]), comparison["overall"].title(), describe("front"), describe("back"), " ".join(comparison["differences"])])
        story.append(table(rows, [24, 17, 35, 35, 69]))

    story += [Spacer(1, 7 * mm), Paragraph("Scan log", styles["Heading2"])]
    if history:
        rows = [["Date", "Side", "Result", "Defects found (confidence)"]]
        for scan, outcome in zip(history, outcomes):
            findings = ", ".join(f"{f['name']} ({percent(f['confidence'])})" for f in scan["findings"] if not is_good_label(f["name"]))
            rows.append([stamp(scan["created_at"]), (scan.get("side") or "single").title(), outcome.title(), findings or "—"])
        story.append(table(rows, [30, 18, 22, 110]))
    else:
        story.append(Paragraph("No scans saved yet.", styles["BodyText"]))

    buffer = io.BytesIO()
    SimpleDocTemplate(buffer, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm, bottomMargin=15 * mm,
                      title="PCB Inspection Report").build(story)
    return buffer.getvalue()
