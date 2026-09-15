#!/usr/bin/env python3
"""
Point your webcam at an object, click on it, and this prints an HSV range
you can paste straight into config/checklists.yaml for that item.

Run tonight on your own laptop with your own webcam, against your actual
sorting items — you'll likely need to loosen the range slightly tomorrow
under the lab's different lighting, but this gets you 90% of the way
there instead of guessing numbers from scratch.

Usage:
    python3 tools/color_picker.py [camera_index]

Click on the object in the window, then press 'q' to quit.
Click multiple times on different parts of the same object to widen the
sample if it looks too narrow.
"""
import sys
import cv2
import numpy as np

samples = []


def on_click(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        frame = param
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        # average a small patch around the click, not just one pixel
        patch = hsv[max(0, y - 5):y + 5, max(0, x - 5):x + 5]
        h, s, v = patch.reshape(-1, 3).mean(axis=0)
        samples.append((h, s, v))
        print(f"Sampled HSV ~= ({h:.0f}, {s:.0f}, {v:.0f})  [{len(samples)} sample(s) so far]")
        if samples:
            arr = np.array(samples)
            h_lo, s_lo, v_lo = np.maximum(arr.min(axis=0) - np.array([10, 40, 40]), 0)
            h_hi, s_hi, v_hi = np.minimum(arr.max(axis=0) + np.array([10, 40, 40]), [179, 255, 255])
            print("  Suggested range for checklists.yaml:")
            print(f"    hsv_low:  [{int(h_lo)}, {int(s_lo)}, {int(v_lo)}]")
            print(f"    hsv_high: [{int(h_hi)}, {int(s_hi)}, {int(v_hi)}]")


def main():
    cam_index = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    cap = cv2.VideoCapture(cam_index)
    if not cap.isOpened():
        print(f"Could not open camera index {cam_index}. Try a different index (0, 1, 2...).")
        return

    cv2.namedWindow("color_picker")
    print("Click on your item in the window. Press 'q' to quit.")

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        cv2.setMouseCallback("color_picker", on_click, frame)
        cv2.imshow("color_picker", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
