# Vision-Verified Kitting & Sorting Robot

A robot scans a QR code to pick a task mode, checks with computer vision that
the right items are physically present, emails an alert for anything missing,
and then runs the pick-and-place with a Dobot Magician once the kit is
complete.

See [`docs/Dobot_Kitting_Sorting_Robot_Presentation.pdf`](docs/Dobot_Kitting_Sorting_Robot_Presentation.pdf)
for the original project proposal (problem statement, architecture, timeline,
team). Note the proposal specs WhatsApp/Twilio for notifications — the build
below uses plain email instead (see "What's already done"), since it needs no
Twilio account, sandbox, or phone verification.

## What's already done (built and tested tonight, no ROS or hardware needed)

Everything under `kitting_logic/` is plain Python — no ROS, no Dobot, no
lab camera required. It's tested: run `python3 test/test_logic.py` and you
should see 10/10 passed. This is the actual brains of the project:

- `qr_logic.py` — reads a QR code from a camera frame
- `checklist_logic.py` — looks up what's required for a given mode
- `vision_logic.py` — checks whether an item is visible in a frame, using a
  YOLOv8 object detector (see "Training the YOLOv8 model" below)
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
3. `pip install -r requirements.txt` on that machine too (this now
   includes `ultralytics`, which pulls in PyTorch — a much bigger install
   than before, budget a few extra minutes).
4. Jog the real arm to find your actual coordinates, and put them in
   `config/coordinates.yaml` (it currently has placeholder numbers).
5. Train a YOLOv8 model on your actual sorting items under the lab's
   actual lighting — see "Training the YOLOv8 model" below (do this even
   if you trained one tonight at home — lighting changes what the model
   needs to see).
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
python3 test/test_logic.py                 # confirm everything passes (no model needed)
python3 demo_integration.py                # walk the pipeline with no camera or model needed
python3 demo_integration.py --webcam       # real webcam + real YOLO model, end to end
```

`demo_integration.py --webcam` and the ROS `perception_node` both need a
trained model at `config/checklists.yaml`'s `yolo.weights` path (default
`models/best.pt`) — see "Training the YOLOv8 model" below. Without one,
they fail immediately with a clear error rather than silently detecting
nothing. `test/test_logic.py` and the no-camera `demo_integration.py`
don't need a model at all — they use a fake detector.

## Training the YOLOv8 model

The color-blob approach (matching a fixed HSV range) was swapped for a
real YOLOv8 object detector, since colour matching broke down under
lighting changes and couldn't tell two same-coloured items apart.

**red_block and blue_block**: a public dataset already covers this —
[colored-blocks](https://universe.roboflow.com/autonomous-object-picking-robot/colored-blocks)
(CC BY 4.0, 513 images, classes `red`/`green`/`blue`, 98.9% mAP@50). That's
why `config/checklists.yaml` points `red_block`/`blue_block` at classes
`red`/`blue` — matching its own class names means you don't have to
relabel its images. **matchbox** has no public dataset — capture and label
that one yourself. Recommended path, since a single model needs one
consistent set of classes:

1. On Roboflow, open the [colored-blocks
   dataset](https://universe.roboflow.com/autonomous-object-picking-robot/colored-blocks)
   and click **Fork Dataset** into your own (free) workspace — this copies
   its 513 labelled red/green/blue images into a project you can edit.
2. Capture matchbox photos: `python3 tools/capture_training_images.py
   matchbox` — press SPACE to save a frame, `q` when done. Move the item
   around a bit between shots (angle, position, background) — 30-50
   varied photos is enough. Saves to `training_images/matchbox/`.
3. Upload those photos into the same forked Roboflow project and label
   them `matchbox` (Roboflow's web UI). You can drop the `green` class
   here too, since nothing in this project needs it.
4. Generate a new dataset version and export it in **YOLOv8** format —
   this gives you a `data.yaml` plus labelled image folders covering all
   3 classes (`red`, `blue`, `matchbox`) in one consistent set.
5. Train: `yolo detect train data=data.yaml model=yolov8n.pt epochs=50 imgsz=640`
   — ultralytics prints the resulting weights path when done, usually
   `runs/detect/train/weights/best.pt`.
6. Copy that file to `models/best.pt` (or wherever `config/checklists.yaml`'s
   `yolo.weights` points).

If you'd rather skip the public dataset and capture/label everything
yourself instead (e.g. your actual blocks look nothing like the ones in
that dataset), do the same thing but run
`tools/capture_training_images.py red_block blue_block matchbox` in step 2
and use `red_block`/`blue_block`/`matchbox` as the class names — just
update `item_classes` in `config/checklists.yaml` to match (`class_name:
red_block` etc.) since you won't be constrained by the public dataset's
naming anymore.

CC BY 4.0 requires attribution if you use the colored-blocks dataset —
Roboflow's project page has a ready-made citation under "Cite This
Project"; worth including in your final report/slides.

Neither the trained weights nor the captured/downloaded photos are
committed to git (see `.gitignore`) — they're per-lab, per-lighting build
artifacts, not source.

If `pyzbar` fails to install (it needs a system library called `libzbar`
that pip can't install by itself on Linux — Windows usually just works),
the QR code will still work — the code automatically falls back to
OpenCV's built-in QR reader (see `kitting_logic/qr_logic.py`).

One QR-printing tip that actually mattered when testing this: print your
QR codes at a reasonable size (a few cm across) with a plain white margin
around them — a QR code with no white border around it, or a screenshot
cropped too tightly, is much harder for either decoder to read.

Ready-made test codes are included: [`MODE_1.png`](MODE_1.png) and
[`MODE_2.png`](MODE_2.png) encode `MODE_1`/`MODE_2` directly — print or
display either one to trigger that mode without generating your own.

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
  config/                <- checklists, coordinates, YOLO/email config (fill in for real)
  launch/kitting.launch   <- starts all three nodes together
  tools/capture_training_images.py  <- webcam capture helper for YOLO training photos
  models/                 <- trained YOLO weights go here (gitignored — train your own)
  training_images/        <- captured training photos go here (gitignored)
  test/test_logic.py      <- run tonight, no ROS or model needed
  demo_integration.py     <- run the whole pipeline end-to-end right now, no ROS needed
  MODE_1.png, MODE_2.png  <- printable QR codes for testing mode switching
  docs/                   <- original project proposal (PDF)
```

## Keeping secrets out of git

`config/secrets.yaml` holds your real Gmail address and app password — it's
listed in `.gitignore` and must never be committed. Only
`config/secrets.example.yaml` (a template with placeholder values) is
tracked. If you ever regenerate the Gmail app password in `secrets.yaml`
(e.g. because it was accidentally shared), revoke the old one at
[myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).
