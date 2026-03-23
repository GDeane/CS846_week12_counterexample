import time
import random


def generate_data(n):
    # Most values are small: this is the important hidden constraint
    return [random.randint(0, 20) for _ in range(n)]


def count_high_values_slow(nums):
    count = 0
    for num in nums:
        value = num**3 + num**2 + num
        if value > 1000:
            count += 1
    return count


def count_high_values_fast(nums):
    count = 0
    for num in nums:
        # Constraint-aware skip: small values cannot affect result
        if num < 10:
            continue

        value = num**3 + num**2 + num
        if value > 1000:
            count += 1
    return count


def benchmark():
    nums = generate_data(200000)

    t0 = time.perf_counter()
    slow_result = count_high_values_slow(nums)
    t1 = time.perf_counter()

    t2 = time.perf_counter()
    fast_result = count_high_values_fast(nums)
    t3 = time.perf_counter()

    print("Slow result:", slow_result)
    print("Fast result:", fast_result)
    print(f"Baseline runtime: {t1 - t0:.3f}s")
    print(f"Optimized runtime: {t3 - t2:.3f}s")


if __name__ == "__main__":
    benchmark()
