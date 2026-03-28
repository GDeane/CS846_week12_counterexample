"""
Tests for the task_queue dispatcher/worker system.

These tests illustrate why Guideline 6 (Explicit Anti-Overlogging Budget)
fails for multi-threaded systems:

- test_guideline6_strict_logging: applies the guideline literally — only one
  INFO log per final outcome. When a deadlock occurs, no log is ever emitted
  and the system appears to hang silently.

- test_heartbeat_logging: uses the revised guideline — two INFO logs per task
  (dequeue + completion). A hung task shows "STARTED" with no matching
  "COMPLETED", making the deadlock immediately visible in logs.
"""

import logging
import threading
import time
from queue import Queue, Empty
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Guideline 6 (strict) — only logs final outcome, deadlock is invisible
# ---------------------------------------------------------------------------

def worker_strict(worker_id, task_queue, resource_lock, results, stop_event, computation_fn):
    """Worker following Guideline 6 strictly: only 1 INFO log on completion."""
    while not stop_event.is_set():
        try:
            task_id = task_queue.get(timeout=0.5)
        except Empty:
            continue

        # Guideline 6: no log here — "per-task start" counts as overlogging
        with resource_lock:
            result = computation_fn(task_id)

        results[task_id] = result
        task_queue.task_done()

        # Guideline 6: 1 INFO log for final outcome only
        logger.info("task_id=%d completed successfully", task_id)


def test_guideline6_strict_logging():
    """
    Strict Guideline 6: when a deadlock occurs, the thread hangs silently.
    The log output shows nothing — no error, no warning, no start entry.
    A developer watching logs cannot tell if the system is idle or stuck.
    """
    deadlock_event = threading.Event()  # never set — simulates deadlock

    call_count = [0]

    def computation_with_deadlock(task_id):
        call_count[0] += 1
        if call_count[0] == 2:
            # Second task deadlocks: thread blocks here indefinitely
            logger.debug("(internal) task_id=%d entering deadlock simulation", task_id)
            deadlock_event.wait(timeout=3.0)  # times out after 3 s in test
            return f"result_for_{task_id}_after_timeout"
        time.sleep(0.05)
        return f"result_for_{task_id}"

    task_queue: Queue = Queue()
    resource_lock = threading.Lock()
    results = {}
    stop_event = threading.Event()

    for task_id in range(4):
        task_queue.put(task_id)

    workers = []
    for worker_id in range(2):
        t = threading.Thread(
            target=worker_strict,
            args=(worker_id, task_queue, resource_lock, results, stop_event, computation_with_deadlock),
            daemon=True,
        )
        t.start()
        workers.append(t)

    # Wait up to 5 seconds — in a real system this would block forever
    finished = threading.Event()

    def wait_for_queue():
        task_queue.join()
        finished.set()

    waiter = threading.Thread(target=wait_for_queue, daemon=True)
    waiter.start()
    completed_normally = finished.wait(timeout=5.0)

    stop_event.set()
    for t in workers:
        t.join(timeout=1.0)

    # Demonstrate the problem: fewer results than tasks
    print(f"\n[Strict Guideline 6] completed_normally={completed_normally}, "
          f"results={len(results)}/4 tasks")
    print("  -> If deadlock occurred, logs show nothing between last INFO and the hang.")
    # No assertion on completion — the point is to show the silent failure


# ---------------------------------------------------------------------------
# Revised guideline — heartbeat logs make deadlocks visible
# ---------------------------------------------------------------------------

def worker_heartbeat(worker_id, task_queue, resource_lock, results, stop_event, computation_fn):
    """
    Worker using revised guideline: 2 INFO logs per task (dequeue + completion).
    A hung task will always have a "STARTED" entry with no matching "COMPLETED".
    """
    while not stop_event.is_set():
        try:
            task_id = task_queue.get(timeout=0.5)
        except Empty:
            continue

        # Revised guideline: heartbeat log on dequeue — critical for detecting hung threads
        logger.info("worker_id=%d task_id=%d status=STARTED", worker_id, task_id)

        with resource_lock:
            result = computation_fn(task_id)

        results[task_id] = result
        task_queue.task_done()

        # Revised guideline: completion heartbeat
        logger.info("worker_id=%d task_id=%d status=COMPLETED result=%s", worker_id, task_id, result)


def test_heartbeat_logging():
    """
    Revised guideline: with heartbeat logs, a deadlocked task leaves a
    'STARTED' entry in the log with no matching 'COMPLETED' — immediately
    actionable for any developer watching the log stream.
    """
    deadlock_event = threading.Event()

    call_count = [0]

    def computation_with_deadlock(task_id):
        call_count[0] += 1
        if call_count[0] == 2:
            logger.debug("(internal) task_id=%d entering deadlock simulation", task_id)
            deadlock_event.wait(timeout=3.0)
            return f"result_for_{task_id}_after_timeout"
        time.sleep(0.05)
        return f"result_for_{task_id}"

    task_queue: Queue = Queue()
    resource_lock = threading.Lock()
    results = {}
    stop_event = threading.Event()

    for task_id in range(4):
        task_queue.put(task_id)

    workers = []
    for worker_id in range(2):
        t = threading.Thread(
            target=worker_heartbeat,
            args=(worker_id, task_queue, resource_lock, results, stop_event, computation_with_deadlock),
            daemon=True,
        )
        t.start()
        workers.append(t)

    finished = threading.Event()

    def wait_for_queue():
        task_queue.join()
        finished.set()

    waiter = threading.Thread(target=wait_for_queue, daemon=True)
    waiter.start()
    completed_normally = finished.wait(timeout=5.0)

    stop_event.set()
    for t in workers:
        t.join(timeout=1.0)

    print(f"\n[Heartbeat Logging] completed_normally={completed_normally}, "
          f"results={len(results)}/4 tasks")
    print("  -> Look at the log: you will see 'status=STARTED' with no 'status=COMPLETED' "
          "for the hung task. The deadlock is immediately visible.")


# ---------------------------------------------------------------------------
# Happy-path smoke test (no deadlock)
# ---------------------------------------------------------------------------

def test_all_tasks_complete_without_deadlock():
    """Sanity check: all tasks complete when there is no deadlock."""
    from task_queue import run_dispatcher

    def fast_computation(task_id):
        time.sleep(0.01)
        return f"ok_{task_id}"

    with patch("task_queue.perform_computation", side_effect=fast_computation):
        results = run_dispatcher(num_tasks=6, num_workers=3)

    assert len(results) == 6, f"Expected 6 results, got {len(results)}"
    for task_id in range(6):
        assert task_id in results, f"Missing result for task_id={task_id}"
    print("\n[Smoke test] All 6 tasks completed as expected.")


if __name__ == "__main__":
    print("=" * 60)
    print("TEST 1: Strict Guideline 6 — silent hang")
    print("=" * 60)
    test_guideline6_strict_logging()

    print()
    print("=" * 60)
    print("TEST 2: Heartbeat Logging — deadlock visible in logs")
    print("=" * 60)
    test_heartbeat_logging()

    print()
    print("=" * 60)
    print("TEST 3: Smoke test — no deadlock")
    print("=" * 60)
    test_all_tasks_complete_without_deadlock()
