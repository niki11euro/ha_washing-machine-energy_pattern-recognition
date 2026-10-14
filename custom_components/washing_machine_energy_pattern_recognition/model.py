"""Pure-Python signal modelling and prefix-DTW; no network or heavy dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, exp, isfinite, log1p, pi, sqrt
from statistics import median


@dataclass(frozen=True, slots=True)
class Reading:
    timestamp: float
    power: float


@dataclass(frozen=True, slots=True)
class Bin:
    mean: float
    maximum: float


@dataclass(frozen=True, slots=True)
class Prediction:
    remaining_seconds: int
    confidence: int
    pattern: str
    matched_cycle_ids: tuple[int, ...]
    distance: float


def clean_readings(readings: list[Reading]) -> list[Reading]:
    """Sort and coalesce duplicate timestamps; reject bad values."""
    ordered: dict[float, Reading] = {}
    for item in readings:
        if isfinite(item.timestamp) and isfinite(item.power) and item.power >= 0:
            ordered[item.timestamp] = item
    return sorted(ordered.values(), key=lambda item: item.timestamp)


def resample(readings: list[Reading], start: float, end: float, step: int = 30) -> list[Bin]:
    """Time-weighted intervals for irregular, piecewise-constant power readings.

    The first reading at or before start anchors the beginning; if no earlier
    reading exists, use the first subsequent reading only when it is within
    one step of start. Otherwise reject the incomplete sequence.
    """
    if step < 1 or end <= start:
        return []
    points = clean_readings(readings)
    if not points:
        return []
    index = 0
    while index + 1 < len(points) and points[index + 1].timestamp <= start:
        index += 1
    if points[index].timestamp > start + step:
        return []
    result: list[Bin] = []
    t0 = start
    while t0 < end:
        t1 = min(end, t0 + step)
        cursor = t0
        total = 0.0
        peak = 0.0
        while cursor < t1:
            while index + 1 < len(points) and points[index + 1].timestamp <= cursor:
                index += 1
            next_t = min(t1, points[index + 1].timestamp if index + 1 < len(points) else t1)
            value = points[index].power
            if next_t <= cursor:
                break
            total += value * (next_t - cursor)
            peak = max(peak, value)
            cursor = next_t
        result.append(Bin(round(total / (t1 - t0), 4), round(peak, 4)))
        t0 = t1
    return result


def energy_kwh(readings: list[Reading], start: float, end: float) -> float:
    """Integrate measured power, holding the previous value between reports."""
    bins = resample(readings, start, end, 30)
    if not bins:
        return 0.0
    # Final bin can be shorter than 30 s.
    return sum(item.mean * min(30, end - start - index * 30) for index, item in enumerate(bins)) / 3_600_000


def dct_coefficients(bins: list[Bin], count: int = 24) -> list[float]:
    """Orthonormal DCT-II over log(power+1), for compact metadata."""
    n = len(bins)
    if n == 0:
        return []
    values = [log1p(item.mean) for item in bins]
    result = []
    for k in range(min(count, n)):
        scale = sqrt((1 if k == 0 else 2) / n)
        value = scale * sum(v * cos(pi * (i + 0.5) * k / n) for i, v in enumerate(values))
        result.append(round(value, 6))
    return result


def dtw_distance(left: list[Bin], right: list[Bin], *, band_fraction: float = 0.25) -> float:
    """Normalized constrained DTW; lower means more similar."""
    n, m = len(left), len(right)
    if not n or not m:
        return float("inf")
    previous = [float("inf")] * (m + 1)
    lengths = [0] * (m + 1)
    previous[0] = 0.0
    band = max(6, int(max(n, m) * band_fraction))
    for i in range(1, n + 1):
        current = [float("inf")] * (m + 1)
        current_lengths = [0] * (m + 1)
        center = round(i * m / n)
        for j in range(max(1, center - band), min(m, center + band) + 1):
            cost = _distance(left[i - 1], right[j - 1])
            options = (
                (previous[j - 1], lengths[j - 1]),
                (previous[j], lengths[j]),
                (current[j - 1], current_lengths[j - 1]),
            )
            best, length = min(options, key=lambda item: item[0])
            if isfinite(best):
                current[j] = best + cost
                current_lengths[j] = length + 1
        previous, lengths = current, current_lengths
    return previous[m] / lengths[m] if lengths[m] else float("inf")


def prefix_dtw(current: list[Bin], reference: list[Bin]) -> tuple[float, int] | None:
    """Compare an unfinished trace to prefixes of a completed reference.

    Search end positions within 0.75x to 1.25x elapsed time to prevent
    pathological alignment of the current start to the reference's end.
    """
    n, m = len(current), len(reference)
    if n < 6 or m < 6:
        return None
    previous = [float("inf")] * (m + 1)
    lengths = [0] * (m + 1)
    previous[0] = 0.0
    for i in range(1, n + 1):
        row = [float("inf")] * (m + 1)
        counts = [0] * (m + 1)
        for j in range(max(1, int(i * 0.72) - 2), min(m, int(i * 1.33) + 2) + 1):
            cost = _distance(current[i - 1], reference[j - 1])
            options = (
                (previous[j - 1], lengths[j - 1]),
                (previous[j], lengths[j]),
                (row[j - 1], counts[j - 1]),
            )
            best, count = min(options, key=lambda item: item[0])
            if isfinite(best):
                row[j] = best + cost
                counts[j] = count + 1
        previous, lengths = row, counts
    candidates = (
        (previous[j] / lengths[j], j)
        for j in range(max(1, int(n * 0.75)), min(m, int(n * 1.25) + 1) + 1)
        if lengths[j] and isfinite(previous[j])
    )
    return min(candidates, default=None)


def predict(
    current: list[Bin],
    history: list[dict],
    *,
    step: int = 30,
    min_distance: float = 0.70,
) -> Prediction | None:
    """Predict using the three nearest complete cycles; refuse weak matches."""
    candidates: list[tuple[float, int, dict]] = []
    for cycle in history:
        reference = [Bin(float(x[0]), float(x[1])) for x in cycle["profile"]]
        match = prefix_dtw(current, reference)
        if match is None:
            continue
        distance, position = match
        # A historic cycle that is already at its final edge is not a
        # useful reference when the current machine still runs for long.
        if distance <= min_distance and len(reference) >= len(current) * 0.75:
            candidates.append((distance, position, cycle))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    best_three = candidates[:3]
    # Median is intentionally robust against one unusual historic duration.
    remaining = median(max(0, (len(item[2]["profile"]) - item[1]) * step) for item in best_three)
    # Distance score is a heuristic, not a statistical probability.
    quality = max(0, min(1, 1 - best_three[0][0] / min_distance))
    confidence = round(25 + 45 * quality + min(20, 10 * (len(best_three) - 1)))
    if len(best_three) == 1:
        confidence = min(confidence, 65)
    nearest = best_three[0][2]
    return Prediction(
        remaining_seconds=round(remaining),
        confidence=confidence,
        pattern=str(nearest.get("label") or nearest.get("pattern") or "Unknown"),
        matched_cycle_ids=tuple(int(item[2]["id"]) for item in best_three),
        distance=round(best_three[0][0], 4),
    )


def _distance(left: Bin, right: Bin) -> float:
    return abs(log1p(left.mean) - log1p(right.mean)) + 0.13 * abs(log1p(left.maximum) - log1p(right.maximum))


class CycleDetector:
    """Timestamp-based hysteresis with confirmed start/end, survives sparse data."""

    def __init__(self, start_w: float = 5.0, end_w: float = 2.5,
                 start_hold: int = 20, end_hold: int = 480) -> None:
        self.start_w, self.end_w = start_w, end_w
        self.start_hold, self.end_hold = start_hold, end_hold
        self.current_power: float | None = None
        self.start_candidate: float | None = None
        self.stop_candidate: float | None = None
        self.active_since: float | None = None
        self.last_timestamp: float | None = None

    def observe(self, timestamp: float, power: float | None) -> list[tuple]:
        events = self.advance(timestamp)
        self.last_timestamp = timestamp
        if power is None or not isfinite(power) or power < 0:
            self.current_power = None
            self.start_candidate = None
            self.stop_candidate = None
            return events
        self.current_power = power
        if self.active_since is None:
            self.start_candidate = timestamp if power >= self.start_w and self.start_candidate is None else (
                None if power < self.start_w else self.start_candidate
            )
        else:
            self.stop_candidate = timestamp if power <= self.end_w and self.stop_candidate is None else (
                None if power > self.end_w else self.stop_candidate
            )
        return events

    def advance(self, timestamp: float) -> list[tuple]:
        events: list[tuple] = []
        if self.current_power is None:
            return events
        if self.active_since is None and self.start_candidate is not None:
            if timestamp - self.start_candidate >= self.start_hold:
                self.active_since = self.start_candidate
                self.start_candidate = None
                events.append(("start", self.active_since))
        if self.active_since is not None and self.stop_candidate is not None:
            if timestamp - self.stop_candidate >= self.end_hold:
                events.append(("finish", self.active_since, self.stop_candidate))
                self.active_since = None
                self.stop_candidate = None
        return events


def detect_completed_cycles(readings: list[Reading], now: float, *,
                            start_w: float = 5.0, end_w: float = 2.5,
                            start_hold: int = 20, end_hold: int = 480,
                            min_duration: int = 600) -> list[tuple[float, float]]:
    """Use the same detector as live monitoring for historical imports."""
    detector = CycleDetector(start_w, end_w, start_hold, end_hold)
    completed: list[tuple[float, float]] = []
    for sample in clean_readings(readings):
        for event in detector.observe(sample.timestamp, sample.power):
            if event[0] == "finish" and event[2] - event[1] >= min_duration:
                completed.append((event[1], event[2]))
    for event in detector.advance(now):
        if event[0] == "finish" and event[2] - event[1] >= min_duration:
            completed.append((event[1], event[2]))
    return completed


def with_patterns(cycles: list[dict], max_distance: float = 0.45) -> list[dict]:
    """Assign deterministic IDs to clusters in chronological order."""
    anchors: list[list[Bin]] = []
    result: list[dict] = []
    for cycle in sorted(cycles, key=lambda item: item["start"]):
        current = [Bin(float(p[0]), float(p[1])) for p in cycle["profile"]]
        distances = [dtw_distance(current, existing) for existing in anchors]
        nearest = min(range(len(distances)), key=distances.__getitem__) if distances else -1
        if nearest == -1 or distances[nearest] > max_distance:
            anchors.append(current)
            nearest = len(anchors) - 1
        result.append({**cycle, "pattern": f"Pattern {nearest + 1}"})
    return result
