import os
import pprint
from datetime import datetime
from zoneinfo import ZoneInfo  # Python 3.9+

def play_notification(sound_type):
  os.system(f"afplay /System/Library/Sounds/{sound_type}.aiff")


def record_event(events_counter, change_type, count = 1):
  events_counter[change_type] += count
  now = datetime.now(ZoneInfo("Europe/Budapest"))
  print(f"[INFO] Event recorded:")
  print(now.strftime("%Y-%m-%d %H:%M:%S %Z"))
  pprint.pprint(events_counter)