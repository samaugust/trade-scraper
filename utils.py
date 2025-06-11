import os
import pprint

def play_notification(sound_type):
  os.system(f"afplay /System/Library/Sounds/{sound_type}.aiff")


def record_event(events_counter, change_type, count = 1):
  events_counter[change_type] += count
  print(f"[INFO] Events tracker updated:")
  pprint.pprint(events_counter)