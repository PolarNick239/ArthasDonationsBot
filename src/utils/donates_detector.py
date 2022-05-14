import cv2
import logging
import itertools
import numpy as np
import scipy
import scipy.ndimage

logger = logging.getLogger("Donates detector")
enable_debug_gui = False


# base_color_median_donate_text = [82, 192, 214]
# base_color_diff_donate_text   = [10, 20, 20]
# base_color_median_header_text = [232, 155, 20]
# base_color_diff_header_text   = [20, 20, 20]

def from_100_to_255(range):
    from_value = range[0] * 255 / 100
    to_value = (range[1] * 255 + 99) / 100
    return [from_value, to_value]


# donate_hue = [48, 58]
donate_hue = [40, 58]
donate_sat = from_100_to_255([50, 100])
donate_val = from_100_to_255([70, 100])
# header_hue = [196, 205]
header_hue = [196, 213]
header_sat = from_100_to_255([70, 100])
header_val = from_100_to_255([70, 100])

typical_letter_width = 14
minimum_donate_border_width = 600


def detect_letters(rgb, hue_range, sat_range, val_range, radius):
    assert (3 == rgb.shape[-1])

    hsv = cv2.cvtColor(rgb, cv2.COLOR_BGR2HSV)

    hue_mask = np.logical_and(hsv[:, :, 0] >= hue_range[0] / 2, hsv[:, :, 0] <= hue_range[1] / 2)
    sat_mask = np.logical_and(hsv[:, :, 1] >= sat_range[0], hsv[:, :, 1] <= sat_range[1])
    val_mask = np.logical_and(hsv[:, :, 2] >= val_range[0], hsv[:, :, 2] <= val_range[1])
    mask = np.logical_and(hue_mask, np.logical_and(sat_mask, val_mask))

    if enable_debug_gui:
        rgb_copy = rgb.copy()
        rgb_copy[~mask] = 0
        cv2.imshow("test", rgb_copy)
        cv2.waitKey()

    params = cv2.SimpleBlobDetector_Params()
    params.thresholdStep = 1
    params.minThreshold = 127
    params.maxThreshold = 129  # should be 128, but this is workaround to https://github.com/opencv/opencv/issues/6667
    params.filterByArea = True
    params.minArea = 10
    params.maxArea = np.pi * radius * radius
    params.filterByColor = False
    params.blobColor = 255
    params.filterByCircularity = False
    params.filterByConvexity = False
    params.filterByInertia = False

    detector = cv2.SimpleBlobDetector_create(params)

    mask = np.uint8(mask) * 255
    blobs = detector.detect(mask)

    if enable_debug_gui:
        blobs_mask = np.uint8(mask)
        blobs_mask = np.dstack([blobs_mask, blobs_mask, blobs_mask])
        for blob in blobs:
            cv2.circle(blobs_mask, (int(blob.pt[0]), int(blob.pt[1])), int(blob.size), (255, 0, 0), thickness=2)
        cv2.imshow("blobs_mask", blobs_mask)
        cv2.waitKey()

    return blobs


def letter_graph_by_x(blobs, width, height, forced_blob_width=None):
    letters_by_x = np.zeros(width, np.float32)

    for blob in blobs:
        multiplier = 5
        blob_size = forced_blob_width if forced_blob_width else blob.size
        from_x = max(0, int(blob.pt[0] - blob_size))
        to_x = min(width, int(blob.pt[0] + blob_size))
        letters_by_x[from_x:to_x] += 1

    if enable_debug_gui:
        import matplotlib.pyplot as plt
        plt.plot(letters_by_x)
        plt.show()

    return letters_by_x


def letter_graph_by_y(letters_blobs, width, height):
    letters_by_y = np.zeros(height, np.float32)

    for blob in letters_blobs:
        from_y = max(0, int(blob.pt[1] - blob.size))
        to_y = min(height, int(blob.pt[1] + blob.size))
        letters_by_y[from_y:to_y] += 1

    # import matplotlib.pyplot as plt
    # plt.plot(letters_by_y)
    # plt.show()

    return letters_by_y


def detect_donate(img):
    height, width = img.shape[:2]

    img_from_y = 0
    img_to_y = 400
    img = img[img_from_y:img_to_y, :, :]
    radius = 25

    header_letters = detect_letters(img, header_hue, header_sat, header_val, radius)
    header_graph_y = letter_graph_by_y(header_letters, width, height)
    donate_header_y = np.argmax(header_graph_y)
    if header_graph_y[donate_header_y] < 7:
        return None

    donate_letters = detect_letters(img, donate_hue, donate_sat, donate_val, radius)
    donate_graph_y = letter_graph_by_y(donate_letters, width, height)
    if np.max(donate_graph_y) < 8:
        return None

    threshold = np.max(donate_graph_y) / 2
    indices = np.nonzero(donate_graph_y > threshold)
    from_y, to_y = np.min(indices) - radius, np.max(indices) + 3 * radius

    if not (from_y - 3 * radius < donate_header_y < from_y + radius):
        return None

    from_y = donate_header_y - radius

    from_y = max(0, from_y)
    to_y = min(to_y, len(img))

    donate_graph_x = letter_graph_by_x([blob for blob in itertools.chain(header_letters, donate_letters)
                                        if from_y <= blob.pt[1] <= to_y],
                                       width, height,
                                       forced_blob_width=typical_letter_width*4)

    donate_graph_x = scipy.ndimage.filters.maximum_filter1d(donate_graph_x, 3 * radius)
    max_radius = 0
    for donate_graph_x_part in [donate_graph_x[:width // 2][::-1], donate_graph_x[width // 2:]]:
        donate_graph_x_part[-1] = 0
        max_radius = max(max_radius, np.nonzero(donate_graph_x_part == 0)[0][0])

    #from_x = max(0, width // 2 - max_radius - 3 * radius)
    #to_x = min(width, width // 2 + max_radius + 3 * radius)

    # from_x = 0
    # to_x = width

    from_x = np.nonzero(donate_graph_x)[0][0]
    to_x = np.nonzero(donate_graph_x)[0][-1]
    if to_x - from_x < minimum_donate_border_width:
        center_x = (from_x + to_x) / 2
        from_x = max(0, center_x - minimum_donate_border_width//2)
        to_x = min(center_x + minimum_donate_border_width//2, width)

    return from_x, to_x, img_from_y + from_y, img_from_y + to_y


def estimate_is_appeared(img0, img1):
    threshold = 20
    diff = np.uint8(np.abs(np.float32(img0) - img1))

    diff = 255 * np.uint8(np.uint8(diff > threshold).sum(axis=-1) >= 1)
    # diff = cv2.erode(diff, np.ones((3, 3), np.uint8), 1)
    # diff = cv2.dilate(diff, np.ones((3, 3), np.uint8), 1)

    return diff != 0


def estimate_is_gone(img0, img1):
    threshold = 20
    diff = np.uint8(np.abs(np.float32(img0) - img1))

    return np.uint8(diff > threshold).sum(axis=-1) >= 1


def extract_donate_robust(prev, cur, next):
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


if __name__ == '__main__':
    import os
    import sys
    import config

    logging.basicConfig(level=logging.DEBUG, format=config.logger_format)

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
