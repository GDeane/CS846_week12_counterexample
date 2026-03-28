"""
Task Queue with Dispatcher and Worker Threads.

A dispatcher assigns tasks from a shared queue to a pool of worker threads.
Each worker must acquire a shared resource lock before processing its task.

Known bug: ~10% of tasks trigger a simulated deadlock inside perform_computation,
causing that worker thread to hang indefinitely without raising an exception.
The thread simply stops making progress while holding or waiting on the lock.
"""

import threading
import time
import random
from queue import Queue, Empty


def perform_computation(task_id: int) -> str:
    """Simulate CPU-bound work. Occasionally blocks forever (deadlock simulation)."""
    if random.random() < 0.10:
        # Simulates a thread deadlocking: waits on an Event that is never set.
        threading.Event().wait()
    time.sleep(random.uniform(0.05, 0.2))
    return f"result_for_{task_id}"


def worker_thread(
    worker_id: int,
    task_queue: Queue,
    resource_lock: threading.Lock,
    results: dict,
    stop_event: threading.Event,
) -> None:
    """
    Pull tasks from the queue, acquire a shared resource lock,
    perform computation, and store the result.
    """
    while not stop_event.is_set():
        try:
            task_id = task_queue.get(timeout=0.5)
        except Empty:
            continue

        with resource_lock:
            result = perform_computation(task_id)

        results[task_id] = result
        task_queue.task_done()


def run_dispatcher(num_tasks: int, num_workers: int) -> dict:
    """
    Dispatch `num_tasks` tasks across `num_workers` worker threads.
    Returns a dict mapping task_id -> result for all completed tasks.
    """
    task_queue: Queue = Queue()
    resource_lock = threading.Lock()
    results: dict = {}
    stop_event = threading.Event()

    for task_id in range(num_tasks):
        task_queue.put(task_id)

    workers = []
    for worker_id in range(num_workers):
        t = threading.Thread(
            target=worker_thread,
            args=(worker_id, task_queue, resource_lock, results, stop_event),
            daemon=True,
        )
        t.start()
        workers.append(t)

    task_queue.join()
    stop_event.set()

    for t in workers:
        t.join(timeout=1.0)

    return results
