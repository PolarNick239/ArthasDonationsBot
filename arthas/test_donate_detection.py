# type: ignore

import os
import sys
from arthas import config
import cv2
import logging

from arthas.utils.donates_detector import extract_donate_robust
from arthas.utils.donates_detector_utils import detect_donate
import arthas.utils.donates_detector_utils


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format=config.logger_format)

    arthas.utils.donates_detector_utils.enable_debug_gui = True

    for image_path in sys.argv[1:]:
        if os.path.isdir(image_path):
            images = sorted(os.listdir(image_path))
            assert (len(images) == 3)
            img0 = cv2.imread(image_path + images[0])
            img1 = cv2.imread(image_path + images[1])
            img2 = cv2.imread(image_path + images[2])
            print("{}:".format(image_path))
            print("    {} -> {} -> {}".format(images[0], images[1], images[2]))
            donate = extract_donate_robust(img0, img1, img2)
            if donate is None:
                img = img1
        else:
            img = cv2.imread(image_path)
            if img is None:
                print("File not found: {}".format(image_path))
                continue
            xy_range = detect_donate(img)

            if xy_range is None:
                donate = None
            else:
                from_x, to_x, from_y, to_y = xy_range
                donate = img[from_y:to_y, from_x:to_x]

        if donate is None:
            print("NO!  {}".format(image_path))
            cv2.imshow("No donate", img)
            cv2.waitKey()
        else:
            print("YES! {}".format(image_path))
            cv2.imshow("Donate", donate)
            cv2.waitKey()
