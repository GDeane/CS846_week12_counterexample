"""
Tests for the task_queue dispatcher/worker system.
"""

import threading
import time
from unittest.mock import patch

from task_queue import run_dispatcher


def test_all_tasks_complete():
    """All tasks complete and return results when there is no deadlock."""
    def fast_computation(task_id):
        time.sleep(0.01)
        return f"ok_{task_id}"

    with patch("task_queue.perform_computation", side_effect=fast_computation):
        results = run_dispatcher(num_tasks=6, num_workers=3, timeout=5.0)

    assert len(results) == 6, f"Expected 6 results, got {len(results)}"
    for task_id in range(6):
        assert task_id in results, f"Missing result for task_id={task_id}"


def test_deadlock_causes_incomplete_results():
    """
    When a worker deadlocks, run_dispatcher returns before all tasks finish.
    This demonstrates the bug: the dispatcher silently returns fewer results
    than tasks submitted, with no indication of which task or worker is stuck.
    """
    deadlock_event = threading.Event()  # never set — simulates infinite deadlock

    def computation_with_deadlock(task_id):
        if task_id == 1:
            deadlock_event.wait()   # hangs indefinitely
        time.sleep(0.05)
        return f"result_for_{task_id}"

    with patch("task_queue.perform_computation", side_effect=computation_with_deadlock):
        results = run_dispatcher(num_tasks=4, num_workers=2, timeout=1.5)

    deadlock_event.set()  # release for clean process exit

    assert len(results) < 4, (
        f"Expected fewer than 4 results due to deadlock, got {len(results)}"
    )


if __name__ == "__main__":
    print("Running test_all_tasks_complete ...")
    test_all_tasks_complete()
    print("  PASSED")

    print("Running test_deadlock_causes_incomplete_results ...")
    test_deadlock_causes_incomplete_results()
    print("  PASSED — dispatcher returned with incomplete results (deadlock confirmed)")
