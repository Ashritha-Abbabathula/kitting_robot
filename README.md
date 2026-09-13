# Vision-Verified Kitting & Sorting Robot

## What's already done (built and tested tonight, no ROS or hardware needed)

Everything under `kitting_logic/` is plain Python — no ROS, no Dobot, no
lab camera required. It's tested: run `python3 test/test_logic.py` and you
should see 8/8 passed. This is the actual brains of the project:

- `qr_logic.py` — reads a QR code from a camera frame
- `checklist_logic.py` — looks up what's required for a given mode
- `vision_logic.py` — checks whether an item's colour is visible in a frame
- `notify_logic.py` — sends (or fakes sending) an email alert when items are missing
- `dobot_logic.py` — moves the arm, with a **simulated** version that just
  logs what it would do, so you can run the whole thing without the arm

Notifications go by email, not SMS/WhatsApp — no Twilio account, sandbox,
or phone verification needed. Just your own email address and a Gmail
"app password" (see `config/secrets.example.yaml` for the exact steps).

## What's left for tomorrow

1. Get this onto the lab's Ubuntu machine (or your own laptop if it runs
   Ubuntu) — see "Getting this onto the lab machine" below.
2. Install ROS 1 Noetic if it isn't already there.
3. `pip install -r requirements.txt` on that machine too.
4. Jog the real arm to find your actual coordinates, and put them in
   `config/coordinates.yaml` (it currently has placeholder numbers).
5. Point `tools/color_picker.py` at your actual sorting items under the
   lab's actual lighting, and update `config/checklists.yaml` with the
   real HSV ranges (do this even if you tuned them tonight at home —
   lighting changes the numbers).
6. Copy `config/secrets.example.yaml` to `config/secrets.yaml` and fill in
   your real email + app password (see comments in that file).
7. Run it:
   ```
   roslaunch kitting_robot kitting.launch                        # simulated arm, safe default
   roslaunch kitting_robot kitting.launch simulate:=false port:=/dev/ttyUSB0   # real arm
   ```

Nothing else changes between simulation and the real run — same code,
same launch file, one flag.

## Running the logic tonight, without ROS

```
pip install -r requirements.txt
python3 test/test_logic.py                 # confirm everything passes
python3 demo_integration.py --webcam       # watch the whole pipeline run, end to end
python3 tools/color_picker.py              # click on your objects to get HSV ranges
```

If `pyzbar` fails to install (it needs a system library called `libzbar`
that pip can't install by itself on Linux — Windows usually just works),
the QR code will still work — the code automatically falls back to
OpenCV's built-in QR reader (see `kitting_logic/qr_logic.py`).

One QR-printing tip that actually mattered when testing this: print your
QR codes at a reasonable size (a few cm across) with a plain white margin
around them — a QR code with no white border around it, or a screenshot
cropped too tightly, is much harder for either decoder to read.

## Getting this onto the lab machine

Easiest: push this to a GitHub repo tonight, then on the lab machine:

```
git clone <your-repo-url> ~/catkin_ws/src/kitting_robot
cd ~/catkin_ws
catkin_make
source devel/setup.bash
```

(If you don't already have a catkin workspace on the lab machine, `mkdir
-p ~/catkin_ws/src` first, then clone into it as above.)

## Project structure

```
kitting_robot/
  kitting_logic/        <- pure Python, no ROS — the actual logic, tested tonight
  scripts/               <- thin ROS node wrappers around kitting_logic/
  config/                <- checklists, coordinates, email secrets (fill in for real)
  launch/kitting.launch   <- starts all three nodes together
  tools/color_picker.py   <- click-to-get-HSV-range helper for tuning item colours
  test/test_logic.py      <- run tonight, no ROS needed
  demo_integration.py     <- run the whole pipeline end-to-end right now, no ROS needed
```
