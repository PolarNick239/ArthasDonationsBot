import time


class TimeoutWatcher:
    def __init__(self) -> None:
        self.previous_query_time = -float('inf')
        self.query_timeout = 1.0

    def ensure_timeout(self, *, query_following: bool = True) -> None:
        current_time = time.time()
        passed = current_time - self.previous_query_time

        if passed < self.query_timeout:
            time.sleep(1.1 * self.query_timeout - passed)

        if query_following:
            self.previous_query_time = current_time