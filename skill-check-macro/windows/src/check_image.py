from __future__ import annotations

import os
import sys

import detector
import imgio
from engine import annotate
from predictor import zones


def describe(path: str) -> str:
    img = imgio.imread(path)
    if img is None:
        return "Couldn't open %s" % path
    ring, rd = detector.find_ring(img, slow=True)
    if ring is None:
        return ("No skill check found in %s.\nIt needs the ring plus its white zone on screen "
                "(a screenshot taken while a skill check is up)." % os.path.basename(path))
    out = annotate(img, ring, rd)
    base, _ = os.path.splitext(path)
    saved = imgio.imwrite(base + "_checked.png", out)
    lines = ["Found the skill check: ring at (%.0f, %.0f), radius %.0f px." % (ring.cx, ring.cy, ring.r)]
    for z in zones(rd):
        g = "white bar %.0f-%.0f deg" % z.great if z.great else "no white bar"
        lines.append("Zone %.0f-%.0f deg (%s)." % (z.start, z.end, g))
    lines.append("Needle at %.0f deg." % rd.needle if rd.needle is not None else
                 "No red needle seen. If the needle isn't red in this game, tell whoever made this.")
    lines.append("Angles are clockwise from the top. " + (
        "Marked-up copy: %s" % os.path.basename(base + "_checked.png") if saved else
        "Couldn't save a marked-up copy next to the picture (is that folder read-only?)."))
    return "\n".join(lines)


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(describe(p))
        print()
