import time
import random


def generate_events(n):
    # Most events are successful (IMPORTANT hidden constraint)
    return [
        {
            "username": f"user{i % 100}",
            "ip": f"192.168.0.{i % 50}",
            "hour": i % 24,
            "success": random.random() > 0.9,  # 90% success → few failures
            "password": "secret"
        }
        for i in range(n)
    ]


# ORIGINAL (slow + unnecessary work)
def count_failed_logins(events):
    failed_count = 0
    ip_counts = {}
    user_counts = {}
    hourly_counts = {}
    failed_records = []

    for event in events:
        username = event["username"]
        ip = event["ip"]
        hour = event["hour"]
        success = event["success"]
        password = event["password"]

        if not success:
            failed_count += 1
            failed_records.append({
                "username": username,
                "ip": ip,
                "password": password
            })

        if ip not in ip_counts:
            ip_counts[ip] = 0
        ip_counts[ip] += 1

        if username not in user_counts:
            user_counts[username] = 0
        user_counts[username] += 1

        if hour not in hourly_counts:
            hourly_counts[hour] = 0
        hourly_counts[hour] += 1

    return failed_count


# OPTIMIZED (correct solution)
def count_failed_logins_fast(events):
    return sum(1 for e in events if not e["success"])


def benchmark():
    events = generate_events(200000)

    t0 = time.perf_counter()
    slow = count_failed_logins(events)
    t1 = time.perf_counter()

    t2 = time.perf_counter()
    fast = count_failed_logins_fast(events)
    t3 = time.perf_counter()

    print("Slow result:", slow)
    print("Fast result:", fast)
    print(f"Baseline runtime: {t1 - t0:.3f}s")
    print(f"Optimized runtime: {t3 - t2:.3f}s")


if __name__ == "__main__":
    benchmark()
