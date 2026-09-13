#!/usr/bin/env python3
"""
ROS1 node: watches /missing_items and /task_mode, and sends a WhatsApp
message whenever the missing-items list changes (rate-limited so it
doesn't spam every camera frame).

Uses a FAKE notifier by default (just prints) unless config/secrets.yaml
exists with real Twilio credentials — so this is safe to launch tonight
without any risk of accidentally trying to hit a real API with placeholder
credentials.
"""
import json
import os
import sys

import rospy
import yaml
from std_msgs.msg import String

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from kitting_logic.whatsapp_logic import (
    format_missing_message, WhatsAppNotifier, FakeWhatsAppNotifier, RateLimitedNotifier,
)

_state = {"mode": None, "notifier": None}


def missing_callback(msg):
    missing = json.loads(msg.data)
    mode = _state["mode"] or "unknown_mode"
    body = format_missing_message(mode, missing)
    _state["notifier"].maybe_send(body, now=rospy.get_time())


def mode_callback(msg):
    _state["mode"] = msg.data


def build_notifier():
    secrets_path = rospy.get_param(
        "~secrets_path",
        os.path.join(os.path.dirname(__file__), "..", "config", "secrets.yaml"),
    )
    min_interval = rospy.get_param("~min_interval_seconds", 8.0)

    if os.path.exists(secrets_path):
        with open(secrets_path) as f:
            creds = (yaml.safe_load(f) or {}).get("twilio", {})
        try:
            real = WhatsAppNotifier(
                account_sid=creds["account_sid"],
                auth_token=creds["auth_token"],
                from_whatsapp=creds["from_whatsapp"],
                to_whatsapp=creds["to_whatsapp"],
            )
            rospy.loginfo("whatsapp_node: using REAL Twilio notifier")
            return RateLimitedNotifier(real, min_interval=min_interval)
        except Exception as e:
            rospy.logerr(f"whatsapp_node: failed to init real Twilio client ({e}), "
                         f"falling back to fake/logging notifier")

    rospy.logwarn("whatsapp_node: no config/secrets.yaml found — using FAKE notifier "
                  "(messages will be logged, not actually sent). Copy "
                  "config/secrets.example.yaml to config/secrets.yaml and fill it in "
                  "to send real WhatsApp messages.")
    return RateLimitedNotifier(FakeWhatsAppNotifier(), min_interval=min_interval)


def main():
    rospy.init_node("whatsapp_node")
    _state["notifier"] = build_notifier()

    rospy.Subscriber("/missing_items", String, missing_callback)
    rospy.Subscriber("/task_mode", String, mode_callback)

    rospy.loginfo("whatsapp_node: ready")
    rospy.spin()


if __name__ == "__main__":
    main()
