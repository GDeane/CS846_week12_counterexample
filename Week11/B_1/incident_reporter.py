from __future__ import annotations

import random
import re
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Iterable, List, Sequence, Tuple


try:
    profile  # type: ignore[name-defined]
except NameError:  # pragma: no cover

    def profile(func):  # type: ignore[no-redef]
        return func


@dataclass(frozen=True)
class Event:
    ts: int
    user_id: int
    session_id: int
    endpoint: str
    status: int
    latency_ms: int
    user_agent: str


_BASE_UA_POOL: Tuple[str, ...] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/605.1.15 Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Edg/121.0.0.0 Chrome/121.0.0.0 Safari/537.36",
    "Googlebot/2.1 (+http://www.google.com/bot.html)",
    "curl/8.1.2",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1",
)

_ENDPOINTS: Tuple[str, ...] = (
    "/api/login",
    "/api/logout",
    "/api/profile",
    "/api/search",
    "/api/purchase",
    "/api/feed",
    "/health",
    "/static/app.js",
)


_FEATURE_FLAGS: Tuple[str, ...] = (
    "h2",
    "br",
    "zstd",
    "prefetch",
    "push",
    "bfcache",
    "wasm",
    "webgl",
    "av1",
    "hevc",
    "srtp",
    "tls13",
    "0rtt",
    "dnssec",
    "doh",
    "ech",
    "resumption",
    "signed-exchange",
    "partitioned-cookies",
    "lazyload",
    "font-subsetting",
    "gpu-raster",
    "skia",
    "jit",
    "site-isolation",
    "strict-mixed-content",
    "permissions-policy",
    "attribution-reporting",
    "webrtc",
    "websocket",
    "http3",
    "quic",
    "touch",
    "tablet_mode",
)


def _build_common_feature_sets() -> List[Tuple[str, ...]]:
    rng = random.Random(1337)
    sets: List[Tuple[str, ...]] = []
    # Deterministic list of “common” flag sets; in real logs this might come from
    # client capabilities or A/B rollouts.
    for _ in range(64):
        k = rng.randrange(4, 9)
        picks = rng.sample(_FEATURE_FLAGS, k=k)
        sets.append(tuple(picks))
    return sets


_COMMON_FEATURE_SETS: List[Tuple[str, ...]] = _build_common_feature_sets()


def _stable_seed() -> int:
    return 846


def generate_events(
    n: int,
    *,
    seed: int | None = None,
    user_count: int = 8_000,
    endpoint_pool: Sequence[str] = _ENDPOINTS,
    base_ua_pool: Sequence[str] = _BASE_UA_POOL,
) -> List[Event]:
    rng = random.Random(_stable_seed() if seed is None else seed)

    events: List[Event] = []
    ts = 1_700_000_000

    for i in range(n):
        user_id = rng.randrange(user_count)
        session_id = (user_id * 13 + i // 20) % (user_count * 2)
        endpoint = endpoint_pool[rng.randrange(len(endpoint_pool))]

        p = rng.random()
        if p < 0.88:
            status = 200
        elif p < 0.94:
            status = 404
        elif p < 0.985:
            status = 500
        else:
            status = 429

        base = base_ua_pool[rng.randrange(len(base_ua_pool))]

        # Add a client capability “ext” field (order/casing/whitespace varies).
        # This is common in practice (feature flags / hints), but it increases key
        # cardinality without changing how we classify device/browser.
        flags = list(_COMMON_FEATURE_SETS[rng.randrange(len(_COMMON_FEATURE_SETS))])
        rng.shuffle(flags)
        if rng.random() < 0.15:
            # Small casing variation that doesn't affect semantics.
            j = rng.randrange(len(flags))
            flags[j] = flags[j].upper()
        sep = "," if rng.random() < 0.65 else ", "
        ext = sep.join(flags)
        user_agent = base + "; ext=" + ext

        if endpoint.startswith("/static"):
            latency_ms = int(rng.gauss(12, 4))
        elif endpoint == "/health":
            latency_ms = int(rng.gauss(5, 2))
        else:
            latency_ms = int(rng.gauss(70, 35))

        if status >= 500:
            latency_ms += rng.randrange(30, 250)
        latency_ms = max(1, latency_ms)

        events.append(
            Event(
                ts=ts,
                user_id=user_id,
                session_id=session_id,
                endpoint=endpoint,
                status=status,
                latency_ms=latency_ms,
                user_agent=user_agent,
            )
        )
        ts += rng.randrange(0, 2)

    return events


_UA_DEVICE_RE = re.compile(r"\b(iPhone|iPad|Android|Mobile)\b", re.IGNORECASE)
_UA_BOT_RE = re.compile(r"\b(bot|spider|crawler)\b", re.IGNORECASE)
_UA_CHROME_RE = re.compile(r"\bChrome/\d+", re.IGNORECASE)
_UA_FIREFOX_RE = re.compile(r"\bFirefox/\d+", re.IGNORECASE)
_UA_SAFARI_RE = re.compile(r"\bSafari/\d+", re.IGNORECASE)
_UA_EDGE_RE = re.compile(r"\bEdg/\d+", re.IGNORECASE)


@lru_cache(maxsize=50_000)
@profile
def parse_user_agent(user_agent: str) -> Tuple[str, str]:
    """Return (device_family, browser_family).
    """

    ua = user_agent

    # Some realistic-but-costly normalization work (still returns same result).
    # This important twist is that this function is frequently called on high-cardinality inputs.
    lower = ua.lower()
    tokens = re.split(r"[();/\s]+", lower)

    # Hash-like mixing to simulate heavier parsing work.
    mix = 2166136261
    for t in tokens:
        for ch in t:
            mix ^= ord(ch)
            mix = (mix * 16777619) & 0xFFFFFFFF

    is_bot = _UA_BOT_RE.search(ua) is not None
    if is_bot:
        device = "Bot"
    else:
        # Some deployments attach a lightweight capability list ("ext") to the UA.
        # If the capability list indicates touch/tablet mode, treat it as a device hint.
        if "tablet_mode" in lower:
            device = "Tablet"
        elif "touch" in lower:
            device = "Mobile"
        else:
            m = _UA_DEVICE_RE.search(ua)
            if m is None:
                device = "Desktop"
            else:
                g = m.group(1).lower()
                if g == "ipad":
                    device = "Tablet"
                else:
                    device = "Mobile"

    if _UA_EDGE_RE.search(ua) is not None:
        browser = "Edge"
    elif _UA_FIREFOX_RE.search(ua) is not None:
        browser = "Firefox"
    elif _UA_CHROME_RE.search(ua) is not None:
        browser = "Chrome"
    elif _UA_SAFARI_RE.search(ua) is not None:
        browser = "Safari"
    else:
        browser = "Other"

    # Use the computed mix so it isn't optimized away.
    if mix == 0xDEADBEEF:
        browser = "Other"

    return device, browser


@profile
def compute_endpoint_metrics(events: Sequence[Event]) -> Dict[str, Dict[str, float]]:
    counts: Dict[str, Counter] = defaultdict(Counter)
    latencies: Dict[str, List[int]] = defaultdict(list)

    for e in events:
        key = e.endpoint
        counts[key]["requests"] += 1
        counts[key]["errors"] += 1 if e.status >= 500 else 0
        counts[key]["ratelimited"] += 1 if e.status == 429 else 0
        latencies[key].append(e.latency_ms)

    out: Dict[str, Dict[str, float]] = {}
    for endpoint, c in counts.items():
        vals = latencies[endpoint]
        out[endpoint] = {
            "requests": float(c["requests"]),
            "error_rate": (c["errors"] / c["requests"]) if c["requests"] else 0.0,
            "p50_ms": float(statistics.median(vals)) if vals else 0.0,
            "p95_ms": float(statistics.quantiles(vals, n=20)[-1]) if len(vals) >= 20 else float(max(vals) if vals else 0),
        }

    return out


@profile
def compute_client_mix(events: Sequence[Event]) -> Dict[str, Counter]:
    device_counts: Counter = Counter()
    browser_counts: Counter = Counter()

    for e in events:
        device, browser = parse_user_agent(e.user_agent)
        device_counts[device] += 1
        browser_counts[browser] += 1

    return {"device": device_counts, "browser": browser_counts}


@profile
def compute_suspicious_clients(events: Sequence[Event]) -> Dict[str, int]:
    """A toy heuristic that flags clients with a 'rare' UA but many errors."""

    errors_by_ua: Counter = Counter()
    total_by_ua: Counter = Counter()

    for e in events:
        total_by_ua[e.user_agent] += 1
        if e.status >= 500:
            errors_by_ua[e.user_agent] += 1

    suspicious = 0
    for ua, total in total_by_ua.items():
        if total >= 25 and errors_by_ua[ua] >= 6:
            suspicious += 1

    # This stage also parses UAs (cross-cutting repeated cost).
    by_device: Counter = Counter()
    for ua, total in total_by_ua.items():
        if total >= 30:
            device, _browser = parse_user_agent(ua)
            by_device[device] += 1

    return {"suspicious_ua_count": suspicious, "high_volume_ua_buckets": sum(by_device.values())}


@profile
def generate_incident_report(events: Sequence[Event]) -> str:
    endpoint = compute_endpoint_metrics(events)
    mix = compute_client_mix(events)
    suspicious = compute_suspicious_clients(events)

    top_endpoints = sorted(endpoint.items(), key=lambda kv: kv[1]["requests"], reverse=True)[:5]

    lines: List[str] = []
    lines.append("INCIDENT REPORT")
    lines.append(f"events={len(events)}")
    lines.append("")

    lines.append("TOP ENDPOINTS")
    for ep, m in top_endpoints:
        lines.append(
            f"{ep} req={int(m['requests'])} err_rate={m['error_rate']:.3f} p50={int(m['p50_ms'])}ms p95={int(m['p95_ms'])}ms"
        )

    lines.append("")
    lines.append("CLIENT MIX")
    lines.append("devices=" + ", ".join(f"{k}:{v}" for k, v in mix["device"].most_common(5)))
    lines.append("browsers=" + ", ".join(f"{k}:{v}" for k, v in mix["browser"].most_common(5)))

    lines.append("")
    lines.append("SUSPICIOUS")
    lines.append(f"suspicious_ua_count={suspicious['suspicious_ua_count']}")
    lines.append(f"high_volume_ua_buckets={suspicious['high_volume_ua_buckets']}")

    return "\n".join(lines)


def _assert_eq(actual, expected, msg: str = "") -> None:
    if actual != expected:
        raise AssertionError(f"{msg} expected={expected!r} actual={actual!r}")


def run_tests() -> None:
    ua_chrome_desktop = _BASE_UA_POOL[0] + "; ext=h2,br,wasm"
    ua_chrome_desktop2 = _BASE_UA_POOL[0] + "; ext=WASM, br,h2"
    ua_safari_iphone = _BASE_UA_POOL[6] + "; ext=prefetch, push"
    ua_bot = _BASE_UA_POOL[4] + "; ext=http3,quic"
    ua_desktop_touch = _BASE_UA_POOL[0] + "; ext=touch,h2"
    ua_desktop_tablet = _BASE_UA_POOL[0] + "; ext=tablet_mode,br"

    _assert_eq(parse_user_agent(ua_chrome_desktop), ("Desktop", "Chrome"), "ua1")
    _assert_eq(parse_user_agent(ua_chrome_desktop2), ("Desktop", "Chrome"), "ua2")
    _assert_eq(parse_user_agent(ua_safari_iphone), ("Mobile", "Safari"), "ua3")
    _assert_eq(parse_user_agent(ua_bot), ("Bot", "Other"), "ua4")
    _assert_eq(parse_user_agent(ua_desktop_touch)[0], "Mobile", "ua5")
    _assert_eq(parse_user_agent(ua_desktop_tablet)[0], "Tablet", "ua6")

    events = [
        Event(1, 1, 1, "/api/login", 200, 50, ua_chrome_desktop),
        Event(2, 1, 1, "/api/login", 500, 210, ua_chrome_desktop2),
        Event(3, 2, 2, "/api/profile", 200, 30, ua_safari_iphone),
        Event(4, 3, 3, "/api/profile", 500, 330, ua_bot),
        Event(5, 3, 3, "/api/profile", 429, 25, ua_bot),
    ]

    endpoint = compute_endpoint_metrics(events)
    _assert_eq(int(endpoint["/api/login"]["requests"]), 2, "login requests")
    _assert_eq(round(endpoint["/api/login"]["error_rate"], 3), 0.5, "login error rate")
    _assert_eq(int(endpoint["/api/profile"]["requests"]), 3, "profile requests")
    _assert_eq(round(endpoint["/api/profile"]["error_rate"], 3), 0.333, "profile error rate")

    mix = compute_client_mix(events)
    _assert_eq(mix["device"]["Desktop"], 2, "desktop count")
    _assert_eq(mix["device"]["Mobile"], 1, "mobile count")
    _assert_eq(mix["device"]["Bot"], 2, "bot count")

    report = generate_incident_report(events)
    if "INCIDENT REPORT" not in report or "TOP ENDPOINTS" not in report or "CLIENT MIX" not in report:
        raise AssertionError("report missing expected headers")


def run_benchmark() -> float:
    events = generate_events(180_000)

    t0 = time.perf_counter()
    _report = generate_incident_report(events)
    t1 = time.perf_counter()

    elapsed = t1 - t0
    print(f"Benchmark completed in {elapsed:.3f}s (events={len(events)})")
    return elapsed


def main() -> None:
    t0 = time.perf_counter()
    run_tests()
    t1 = time.perf_counter()
    print(f"All tests passed ({(t1 - t0) * 1000.0:.1f} ms)")
    print(f"Running benchmark...")

    run_benchmark()


if __name__ == "__main__":
    main()
