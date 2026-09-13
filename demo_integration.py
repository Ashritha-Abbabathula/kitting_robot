#!/usr/bin/env python3
"""
Runs the WHOLE pipeline end-to-end, right now, with no ROS and no
hardware — so you can actually watch it work tonight.

This is NOT how it runs tomorrow (tomorrow, five separate ROS nodes pass
messages to each other). This script just calls the same functions those
nodes will call, one after another in a single process, so you can see
the full chain of decisions with your own eyes before any ROS wiring
exists.

Two ways to run it:

    python3 demo_integration.py            # fully synthetic — no camera needed, runs anywhere
    python3 demo_integration.py --webcam   # uses your real webcam for the QR code step

Watch the printed output — it walks through exactly what each "node"
would be thinking at each moment.
"""
import argparse
import json
import os
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from kitting_logic.qr_logic import decode_qr, normalize_mode
from kitting_logic.checklist_logic import load_checklists, get_required_items
from kitting_logic.vision_logic import find_missing_items
from kitting_logic.whatsapp_logic import format_missing_message, build_notifier
from kitting_logic.dobot_logic import SimulatedDobot, run_pick_and_place
from kitting_logic.dobot_logic import run_pick_and_place as _rpp  # noqa: F401 (import proves the module wires up)

import yaml

HERE = os.path.dirname(__file__)
CHECKLIST_PATH = os.path.join(HERE, "config", "checklists.yaml")
COORDS_PATH = os.path.join(HERE, "config", "coordinates.yaml")


def banner(text):
    print("\n" + "=" * 60)
    print(text)
    print("=" * 60)


def make_colored_frame(h, w, bgr):
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[:, :] = bgr
    return frame


def get_qr_from_webcam():
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Could not open a webcam — falling back to synthetic mode for this step.")
        return None
    print("Point a printed/displayed QR code (encoding MODE_1 or MODE_2) at your webcam...")
    print("(Press 'q' to give up after a few seconds.)")
    deadline = time.time() + 15
    found = None
    while time.time() < deadline:
        ok, frame = cap.read()
        if not ok:
            continue
        cv2.imshow("Show your QR code here", frame)
        raw = decode_qr(frame)
        if raw:
            found = raw
            break
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
    cap.release()
    cv2.destroyAllWindows()
    return found


def synthetic_qr_frame():
    """Generates a real, scannable QR code image encoding MODE_1 — same code
    path used to prove qr_logic.py works in test_logic.py's sibling checks."""
    encoder = cv2.QRCodeEncoder_create()
    raw = encoder.encode("MODE_1")
    big = cv2.resize(raw, (250, 250), interpolation=cv2.INTER_NEAREST)
    bordered = cv2.copyMakeBorder(big, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=(255, 255, 255))
    return bordered


def build_bin_completion_sequence(mode, required_items, coords):
    home = coords["home"]
    pickup = coords["pickup"]["default"]
    hover = coords.get("hover_height_offset", 40)
    bins = coords["bins"]
    seq = [{"action": "home"}]
    for item in required_items:
        bin_pos = bins.get(item, home)
        seq += [
            {"action": "move", "x": pickup["x"], "y": pickup["y"], "z": pickup["z"] + hover, "r": pickup["r"]},
            {"action": "move", "x": pickup["x"], "y": pickup["y"], "z": pickup["z"], "r": pickup["r"]},
            {"action": "suck", "on": True},
            {"action": "move", "x": bin_pos["x"], "y": bin_pos["y"], "z": bin_pos["z"] + hover, "r": bin_pos["r"]},
            {"action": "move", "x": bin_pos["x"], "y": bin_pos["y"], "z": bin_pos["z"], "r": bin_pos["r"]},
            {"action": "suck", "on": False},
        ]
    seq.append({"action": "home"})
    return seq


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--webcam", action="store_true", help="use a real webcam for the QR step")
    args = parser.parse_args()

    checklists = load_checklists(CHECKLIST_PATH)
    with open(CHECKLIST_PATH) as f:
        item_colors = (yaml.safe_load(f) or {}).get("item_colors", {})
    with open(COORDS_PATH) as f:
        coords = yaml.safe_load(f)

    # ---- Step 1: perception_node's job, part 1 — read the QR code ----
    banner("STEP 1 — perception_node: reading the QR code")
    raw_text = None
    if args.webcam:
        raw_text = get_qr_from_webcam()
    if raw_text is None:
        print("Using a synthetic generated QR code (no real camera involved).")
        frame = synthetic_qr_frame()
        raw_text = decode_qr(frame)
    mode = normalize_mode(raw_text)
    print(f"  -> decoded text: {raw_text!r}")
    print(f"  -> normalized mode: {mode!r}")
    print(f"  -> [would publish to /task_mode]: {mode}")

    # ---- Step 2: checklist_manager's job — look up requirements ----
    banner("STEP 2 — perception_node: looking up the checklist for this mode")
    required_items = get_required_items(checklists, mode)
    print(f"  -> required items for {mode}: {required_items}")
    print(f"  -> [would publish to /required_items]: {json.dumps(required_items)}")

    # ---- Step 3 & 4: vision + whatsapp, looping until complete ----
    banner("STEP 3/4 — perception_node checks the table, whatsapp_node reports gaps")
    secrets_path = os.path.join(HERE, "config", "secrets.yaml")
    notifier = build_notifier(secrets_path, min_interval=0)

    # Simulate items "appearing" on the table one at a time across a few
    # checks, the way they would as you actually place objects tomorrow.
    for round_num in range(len(required_items) + 1):
        present_so_far = required_items[:round_num]
        print(f"\n  -- check #{round_num + 1}: pretend these are currently on the table: {present_so_far or '(nothing yet)'}")

        # Build a synthetic frame that only "shows" the colours of items
        # present_so_far — a stand-in for a real camera frame tomorrow.
        # Each item gets its own patch of the frame so several can be
        # "on the table" at once, same as several real objects would sit
        # in different spots under the real camera.
        frame = make_colored_frame(200, 400, (40, 40, 40))  # neutral background
        for i, item in enumerate(present_so_far):
            cfg = item_colors.get(item)
            if cfg:
                hue = cfg["hsv_low"][0]
                hsv_patch = np.uint8([[[hue, 200, 200]]])
                bgr = cv2.cvtColor(hsv_patch, cv2.COLOR_HSV2BGR)[0][0]
                x0 = i * 150
                frame[50:150, x0:x0 + 100] = bgr

        missing = find_missing_items(frame, required_items, item_colors)
        print(f"     -> [would publish to /missing_items]: {json.dumps(missing)}")
        body = format_missing_message(mode, missing)
        notifier.maybe_send(body, now=time.time())
        complete = len(missing) == 0
        print(f"     -> [would publish to /verification_complete]: {complete}")
        if complete:
            break

    # ---- Step 5: dobot_node's job — execute once complete ----
    banner("STEP 5 — dobot_node: checklist complete, executing pick-and-place (SIMULATED)")
    dobot = SimulatedDobot()
    dobot.connect()
    dobot.home()
    sequence = build_bin_completion_sequence(mode, required_items, coords)
    run_pick_and_place(dobot, sequence)
    dobot.disconnect()

    banner("DONE — this is the exact chain of decisions your 3 ROS nodes will make tomorrow")


if __name__ == "__main__":
    main()
