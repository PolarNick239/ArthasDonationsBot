from typing import Optional

import cv2
import numpy as np

import arthas
from arthas.utils.donates_detector_utils import estimate_is_appeared, estimate_is_gone, detect_donate  # type: ignore


def extract_donate_robust(prev: np.ndarray, cur: np.ndarray, next: np.ndarray) -> Optional[np.ndarray]:
    enable_debug_dir = arthas.utils.donates_detector_utils.enable_debug_dir
    if enable_debug_dir:
        cv2.imwrite(enable_debug_dir + "00_prev.png", prev)
        cv2.imwrite(enable_debug_dir + "01_prev.png", cur)
        cv2.imwrite(enable_debug_dir + "02_next.png", next)

    is_appeared = estimate_is_appeared(prev, cur)
    is_gone = estimate_is_gone(cur, next)

    if enable_debug_dir:
        cv2.imwrite(enable_debug_dir + "11_is_appeared_mask.png", np.uint8(is_appeared)*255)
        cv2.imwrite(enable_debug_dir + "12_is_gone_mask.png", np.uint8(is_gone)*255)

    img = cur.copy()
    img[~is_appeared] = 0

    if enable_debug_dir:
        cv2.imwrite(enable_debug_dir + "20_frame.png", cur)
        cv2.imwrite(enable_debug_dir + "21_frame_without_old_data.png", img)

    img[is_gone] = 0

    if enable_debug_dir:
        cv2.imwrite(enable_debug_dir + "22_frame_without_old_data_and_without_what_is_gone.png", img)

    xy_range = detect_donate(img)

    if xy_range is None:
        return None
    else:
        from_x, to_x, from_y, to_y = xy_range
        return cur[from_y:to_y, from_x:to_x]
