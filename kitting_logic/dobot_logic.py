"""
Arm control logic — no ROS dependency, and no hardware required tonight.

Two interchangeable controllers, same interface:
  - SimulatedDobot: just logs what it would do. Use this tonight to prove
    the whole pipeline reacts correctly once a kit is complete.
  - RealDobot: talks to the actual arm over USB using pydobot. Use this
    tomorrow once you're at the lab and have jogged the arm to find your
    real coordinates (fill them into config/coordinates.yaml).

Both are used the exact same way by the ROS node, so swapping one for the
other tomorrow is a one-line config change, not a code change.
"""
from typing import List, Dict


class SimulatedDobot:
    """Logs intended actions instead of moving anything. Safe to run anywhere, anytime."""

    def __init__(self, port: str = "SIMULATED"):
        self.port = port
        self.connected = False

    def connect(self):
        self.connected = True
        print(f"[SIM] Connected to Dobot on '{self.port}' (simulated)")

    def home(self):
        print("[SIM] Homing arm")

    def move_to(self, x: float, y: float, z: float, r: float = 0.0):
        print(f"[SIM] Move to x={x}, y={y}, z={z}, r={r}")

    def set_suction(self, on: bool):
        print(f"[SIM] Suction {'ON' if on else 'OFF'}")

    def set_conveyor(self, on: bool, speed: float = 0.0):
        print(f"[SIM] Conveyor {'ON at speed ' + str(speed) if on else 'OFF'}")

    def disconnect(self):
        self.connected = False
        print("[SIM] Disconnected")


class RealDobot:
    """
    Thin wrapper around the `pydobot` library. Talks to the arm directly
    over its USB serial connection — this deliberately does NOT depend on
    Dobot's official ROS driver package, since that requires you to build
    and match its exact ROS service names, which is unverified in this
    setup. pydobot is a small, stable, well-documented library that
    controls the exact same arm over the exact same USB cable, so this is
    the lower-risk path for a one-day build. (Nothing stops you from
    switching to the official ROS driver's services later if you want to
    — that would only mean changing THIS file, nothing else.)
    """

    def __init__(self, port: str):
        self.port = port
        self._dobot = None

    def connect(self):
        import pydobot  # imported here so this file loads fine even before
        # pydobot is installed, e.g. while testing SimulatedDobot tonight.

        self._dobot = pydobot.Dobot(port=self.port, verbose=False)

    def home(self):
        # pydobot doesn't expose a one-call "home" in older versions; if
        # yours doesn't have .home(), just move to your saved home
        # coordinates instead using move_to() below.
        if hasattr(self._dobot, "home"):
            self._dobot.home()

    def move_to(self, x: float, y: float, z: float, r: float = 0.0):
        self._dobot.move_to(x, y, z, r, wait=True)

    def set_suction(self, on: bool):
        self._dobot.suck(on)

    def set_conveyor(self, on: bool, speed: float = 0.0):
        # pydobot's conveyor support varies by version/fork. If
        # `conveyor_belt` isn't available in your installed version, drive
        # the conveyor with the arm's SetEMotor command directly instead —
        # check pydobot's source for the exact call your version exposes.
        if hasattr(self._dobot, "conveyor_belt"):
            self._dobot.conveyor_belt(speed if on else 0)
        else:
            print("[WARN] This pydobot version has no conveyor_belt() — "
                  "check its source for the equivalent EMotor call.")

    def disconnect(self):
        if self._dobot is not None:
            self._dobot.close()


def run_pick_and_place(dobot, sequence: List[Dict]):
    """
    Executes a taught pick-and-place sequence, e.g.:
        [
          {"action": "move", "x": 200, "y": 0, "z": 50, "r": 0},
          {"action": "suck", "on": true},
          {"action": "move", "x": 200, "y": 100, "z": 80, "r": 0},
          {"action": "suck", "on": false},
        ]
    Same function, same sequence format, works against SimulatedDobot
    tonight and RealDobot tomorrow — only the coordinates in
    config/coordinates.yaml need to change.
    """
    for step in sequence:
        action = step["action"]
        if action == "move":
            dobot.move_to(step["x"], step["y"], step["z"], step.get("r", 0.0))
        elif action == "suck":
            dobot.set_suction(step["on"])
        elif action == "conveyor":
            dobot.set_conveyor(step["on"], step.get("speed", 0.0))
        elif action == "home":
            dobot.home()
        else:
            raise ValueError(f"Unknown action in sequence: {action}")
