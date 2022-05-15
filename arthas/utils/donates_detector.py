from typing import Optional

import numpy as np

from arthas.utils.donates_detector_utils import estimate_is_appeared, estimate_is_gone, detect_donate  # type: ignore


def extract_donate_robust(prev: np.ndarray, cur: np.ndarray, next: np.ndarray) -> Optional[np.ndarray]:
    is_appeared = estimate_is_appeared(prev, cur)
    is_gone = estimate_is_gone(cur, next)

    img = cur.copy()
    img[~is_appeared] = 0
    img[is_gone] = 0

    xy_range = detect_donate(img)

    if xy_range is None:
        return None
    else:
        from_x, to_x, from_y, to_y = xy_range
        return cur[from_y:to_y, from_x:to_x]
