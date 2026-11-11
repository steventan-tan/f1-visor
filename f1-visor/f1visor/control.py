"""Hardware-independent timing and trigger policy."""
import math
import threading
import time
from contextlib import contextmanager
from pathlib import Path


class DetectionGate:
    def __init__(self, threshold, hold_seconds, cooldown_seconds):
        if not math.isfinite(threshold) or not 0 <= threshold <= 1:
            raise ValueError("threshold must be between 0 and 1")
        if not all(math.isfinite(v) and v > 0 for v in (hold_seconds, cooldown_seconds)):
            raise ValueError("hold and cooldown must be positive and finite")
        self.threshold = threshold
        self.hold = hold_seconds
        self.cooldown = cooldown_seconds
        self.since = None
        self.ready_at = 0.0

    def reset(self):
        self.since = None

    def actuated(self, now):
        self.reset()
        self.ready_at = now + self.cooldown

    def update(self, probability, now):
        if not math.isfinite(probability) or not 0 <= probability <= 1:
            self.reset()
            raise ValueError("invalid model probability")
        if now < self.ready_at or probability < self.threshold:
            self.reset()
            return False
        if self.since is None:
            self.since = now
        return now - self.since >= self.hold


def is_manual_trigger(data):
    return data in (b"S", b"s")


class ServoController:
    """One actuator for both inputs; concurrent requests are discarded, never queued."""
    def __init__(self, servo, stop, seconds, neutral, speed):
        self.servo = servo
        self.stop = stop
        self.seconds = seconds
        self.neutral = neutral
        self.speed = speed
        self.lock = threading.Lock()
        self.last_finished = None

    def run(self, *, automatic_since=None):
        if not self.lock.acquire(blocking=False):
            return False
        try:
            if self.stop.is_set():
                return False
            # A manual move may finish after the camera check but before this lock.
            if automatic_since is not None and self.last_finished is not None and self.last_finished >= automatic_since:
                return False
            try:
                self.servo.value = self.speed
                self.stop.wait(self.seconds)
            finally:
                self.servo.value = self.neutral
                self.last_finished = time.monotonic()
            return True
        finally:
            self.lock.release()


@contextmanager
def single_instance(path):
    # Keep the inode: unlinking a locked file lets another process lock a new inode.
    import fcntl
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Another controller is already running") from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
