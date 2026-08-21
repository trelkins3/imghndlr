"""Shared timing utilities for progress reporting."""

import time


class ElapsedTimer:
    """Tracks elapsed wall-clock time for a long-running operation."""

    def __init__(self) -> None:
        self._start_time = time.perf_counter()

    def elapsed_seconds(self) -> float:
        """Return the elapsed time since this timer was created."""
        return time.perf_counter() - self._start_time

    def format_elapsed(self) -> str:
        """Return elapsed time using the application's progress format."""
        return f"{self.elapsed_seconds():.1f}s"
