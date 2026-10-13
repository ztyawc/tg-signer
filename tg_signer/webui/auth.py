import hmac
import secrets
import time
from collections import OrderedDict, deque

SESSION_SECONDS = 12 * 60 * 60
_PROCESS_NONCE = secrets.token_hex(32)


class LoginLimiter:
    def __init__(self, attempts=5, window=300, capacity=4096, clock=time.monotonic):
        self.attempts, self.window, self.capacity = attempts, window, capacity
        self.clock = clock
        self.failures = OrderedDict()

    def remaining(self, key):
        now = self.clock()
        queue = self.failures.get(key, deque())
        while queue and now - queue[0] >= self.window:
            queue.popleft()
        return (
            max(1, int(self.window - (now - queue[0])))
            if len(queue) >= self.attempts
            else 0
        )

    def failed(self, key):
        self.remaining(key)
        queue = self.failures.setdefault(key, deque())
        queue.append(self.clock())
        self.failures.move_to_end(key)
        while len(self.failures) > self.capacity:
            self.failures.popitem(last=False)

    def succeeded(self, key):
        self.failures.pop(key, None)


def auth_version(code: str) -> str:
    return hmac.digest(_PROCESS_NONCE.encode(), code.encode(), "sha256").hex()


def create_session(code: str) -> dict:
    return {"version": auth_version(code), "expires_at": time.time() + SESSION_SECONDS}


def session_valid(session, code: str) -> bool:
    if not isinstance(session, dict):
        return False
    try:
        return float(
            session.get("expires_at", 0)
        ) > time.time() and secrets.compare_digest(
            str(session.get("version", "")), auth_version(code)
        )
    except (TypeError, ValueError):
        return False
