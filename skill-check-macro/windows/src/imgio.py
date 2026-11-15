from __future__ import annotations

import os

import cv2
import numpy as np


def imread(path: str) -> np.ndarray | None:
    try:
        data = np.fromfile(path, np.uint8)
    except OSError:
        return None
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def imwrite(path: str, img: np.ndarray) -> bool:
    ok, buf = cv2.imencode(os.path.splitext(path)[1] or ".png", img)
    if not ok:
        return False
    try:
        buf.tofile(path)
    except OSError:
        return False
    return True
