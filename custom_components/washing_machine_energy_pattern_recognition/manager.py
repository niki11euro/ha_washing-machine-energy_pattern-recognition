"""Live tracking, persistent cycle archive, Recorder import and prediction."""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timedelta, timezone
from functools import partial
import logging
from math import isfinite
import time
from typing import Callable

from homeassistant.components.recorder import get_instance, history
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval

from .const import CONF_POWER_ENTITY, DEFAULT_OPTIONS
from .model import (
    CycleDetector, Prediction, Reading, clean_readings, detect_completed_cycles,
    predict, resample, with_patterns,
)
from .storage import CycleStorage

_LOGGER = logging.getLogger(__name__)
_MAX_CYCLE_SECONDS = 12 * 3600


class WashingMachineManager:
    """Own exactly one source power sensor and its independent SQLite store."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        self.hass = hass
        self.entry = entry
        self.entity_id: str = entry.data[CONF_POWER_ENTITY]
        self.name: str = entry.data.get("name", "Washing machine")
        self.options = {**DEFAULT_OPTIONS, **entry.options}
        self.storage = CycleStorage(hass.config.path(f"washing_pattern_{entry.entry_id}.db"))
        self.detector = CycleDetector(
            self.options["start_w"], self.options["end_w"],
            self.options["start_hold"], self.options["end_hold"],
        )
        self.active_since: float | None = None
        self.last_power: float | None = None
        self.samples: list[Reading] = []
        self._unsaved: list[Reading] = []
        self._candidate: deque[Reading] = deque(maxlen=5000)
        self._pending: list[Reading | None] = []
        self._lock = asyncio.Lock()
        self._callbacks: set[Callable] = set()
        self._unsub: list[Callable] = []
        self._tasks: set[asyncio.Task] = set()
        self._last_flush = 0.0
        self._next_predict = 0.0
        self.cycles: list[dict] = []
        self.prediction: Prediction | None = None
        self.predicted_end: float | None = None
        self.status = "idle"

    async def async_start(self) -> None:
        await self.hass.async_add_executor_job(self.storage.initialize)
        await self.async_refresh()
        active_start, recorded = await self.hass.async_add_executor_job(self.storage.get_active)
        if active_start is not None and recorded:
            self.active_since = active_start
            self.samples = recorded
            self.detector.active_since = active_start
            self.detector.current_power = recorded[-1].power
            self.detector.last_timestamp = recorded[-1].timestamp
            self.status = "running"
            _LOGGER.info("Recovered washing cycle starting at %s", active_start)
        self._unsub.append(async_track_state_change_event(
            self.hass, [self.entity_id], self._state_changed
        ))
        self._unsub.append(async_track_time_interval(
            self.hass, self._timer, timedelta(seconds=10)
        ))
        initial = self._parse_state(self.hass.states.get(self.entity_id))
        self._pending.append(Reading(time.time(), initial) if initial is not None else None)
        self._create_task(self._delayed_import(), "wash_import")
        self._create_task(self.async_tick(), "wash_first_tick")

    @callback
    def subscribe(self, listener: Callable) -> Callable:
        self._callbacks.add(listener)
        return lambda: self._callbacks.discard(listener)

    @callback
    def _notify(self) -> None:
        for listener in tuple(self._callbacks):
            listener()

    def _create_task(self, coroutine, name: str) -> None:
        task = self.hass.async_create_task(coroutine, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    @staticmethod
    def _parse_state(state: State | None) -> float | None:
        if state is None:
            return None
        try:
            power = float(state.state)
            unit = state.attributes.get("unit_of_measurement", "W")
            if unit == "kW":
                power *= 1000
            elif unit == "mW":
                power /= 1000
            elif unit != "W":
                return None
            return power if isfinite(power) and power >= 0 else None
        except (ValueError, TypeError):
            return None

    @callback
    def _state_changed(self, event: Event) -> None:
        state = event.data.get("new_state")
        value = self._parse_state(state)
        stamp = event.time_fired.timestamp()
        self._pending.append(Reading(stamp, value) if value is not None else None)

    @callback
    def _timer(self, _: datetime) -> None:
        self._create_task(self.async_tick(), "wash_tick")

    async def async_tick(self) -> None:
        async with self._lock:
            now = time.time()
            pending, self._pending = self._pending, []
            for sample in pending:
                stamp = sample.timestamp if sample is not None else now
                value = sample.power if sample is not None else None
                if sample is not None:
                    self.last_power = sample.power
                    self._candidate.append(sample)
                events = self.detector.observe(stamp, value)
                await self._transitions(events)
                if sample is not None and self.active_since is not None:
                    # Start event may already have placed this sample in the buffer.
                    if not self.samples or self.samples[-1].timestamp != sample.timestamp:
                        self.samples.append(sample)
                        self._unsaved.append(sample)
            await self._transitions(self.detector.advance(now))
            if self.active_since is not None and now - self.active_since > _MAX_CYCLE_SECONDS:
                _LOGGER.warning("Aborting cycle older than 12 hours; retaining no invalid profile")
                await self.hass.async_add_executor_job(self.storage.clear_active)
                self.active_since = None
                self.samples.clear()
                self._unsaved.clear()
                self.detector = CycleDetector(
                    self.options["start_w"], self.options["end_w"],
                    self.options["start_hold"], self.options["end_hold"],
                )
                self.status = "idle"
            if self.active_since is not None:
                if now - self._last_flush >= 30 and self._unsaved:
                    await self._flush()
                if (
                    now - self.active_since >= self.options["prediction_after_minutes"] * 60
                    and now >= self._next_predict
                ):
                    current = resample(self.samples, self.active_since, now)
                    # Predict in the executor to keep HA's event loop responsive.
                    self.prediction = await self.hass.async_add_executor_job(
                        partial(predict, current, self.cycles)
                    )
                    self.predicted_end = (
                        now + self.prediction.remaining_seconds if self.prediction else None
                    )
                    self._next_predict = now + self.options["prediction_every_minutes"] * 60
            self._notify()

    async def _transitions(self, events: list[tuple]) -> None:
        for event in events:
            if event[0] == "start":
                self.active_since = event[1]
                self.samples = [s for s in self._candidate if s.timestamp >= self.active_since]
                self._unsaved = list(self.samples)
                self.status = "running"
                self.prediction = None
                self.predicted_end = None
                self._next_predict = 0
                await self._flush()
                _LOGGER.info("Washing cycle started at %s", self.active_since)
            elif event[0] == "finish":
                start, end = event[1], event[2]
                # Query Recorder before committing: recovers samples missed on a restart.
                recorder_samples = await self._read_history(start - 30, end + 1)
                merged = clean_readings(self.samples + recorder_samples)
                if end - start >= self.options["min_cycle_minutes"] * 60:
                    cycle_id = await self.hass.async_add_executor_job(
                        partial(self.storage.add_cycle, start, end, merged, clear_active=True)
                    )
                    if cycle_id is not None:
                        _LOGGER.info("Archived washing cycle %s", cycle_id)
                        await self.async_refresh()
                else:
                    await self.hass.async_add_executor_job(self.storage.clear_active)
                self.active_since = None
                self.samples.clear()
                self._unsaved.clear()
                self.prediction = None
                self.predicted_end = None
                self.status = "idle"

    async def _flush(self) -> None:
        if self.active_since is None:
            return
        await self.hass.async_add_executor_job(
            self.storage.save_active, self.active_since, self._unsaved
        )
        self._unsaved.clear()
        self._last_flush = time.time()

    async def async_refresh(self) -> None:
        self.cycles = await self.hass.async_add_executor_job(self.storage.list_cycles)
        # Cluster formation uses DTW and belongs off the event loop.
        self.cycles = await self.hass.async_add_executor_job(with_patterns, self.cycles)
        self._notify()

    async def _read_history(self, start: float, end: float) -> list[Reading]:
        from_dt = datetime.fromtimestamp(start, timezone.utc)
        to_dt = datetime.fromtimestamp(end, timezone.utc)
        try:
            results = await get_instance(self.hass).async_add_executor_job(
                partial(
                    history.get_significant_states,
                    self.hass, from_dt, to_dt,
                    entity_ids=[self.entity_id],
                    significant_changes_only=True,
                    include_start_time_state=True,
                    no_attributes=False,
                )
            )
        except (RuntimeError, ValueError, OSError):
            _LOGGER.exception("Recorder data unavailable for washing history")
            return []
        output = []
        for state in results.get(self.entity_id, []):
            value = self._parse_state(state)
            if value is not None:
                output.append(Reading(state.last_updated.timestamp(), value))
        return output

    async def async_import_history(self, days: int | None = None) -> int:
        """One-off backfill from HA Recorder's available raw (typically 10 days)."""
        async with self._lock:
            days = min(9, max(1, int(days or self.options["import_days"])))
            now = time.time()
            start = now - days * 86400
            all_states: list[Reading] = []
            cursor = start
            while cursor < now:
                boundary = min(cursor + 86400, now)
                all_states.extend(await self._read_history(cursor, boundary))
                cursor = boundary
            all_states = clean_readings(all_states)
            completed = detect_completed_cycles(
                all_states, now,
                start_w=self.options["start_w"],
                end_w=self.options["end_w"],
                start_hold=self.options["start_hold"],
                end_hold=self.options["end_hold"],
                min_duration=self.options["min_cycle_minutes"] * 60,
            )
            before = len(self.cycles)
            for cycle_start, cycle_end in completed:
                # Refuse incomplete cycles that started on the import boundary.
                if cycle_start < start + 30 or cycle_end - cycle_start > _MAX_CYCLE_SECONDS:
                    continue
                await self.hass.async_add_executor_job(
                    partial(self.storage.add_cycle, cycle_start, cycle_end, all_states)
                )
            await self.async_refresh()
            return len(self.cycles) - before

    async def _delayed_import(self) -> None:
        # Initial import is idempotent. Running it on subsequent startups also
        # recovers completed cycles missed during an extended HA outage.
        await asyncio.sleep(15)
        try:
            count = await self.async_import_history()
            _LOGGER.info("Imported %s historical washing cycles", count)
        except Exception:
            _LOGGER.exception("Could not import initial washing history")

    async def async_label_cycle(self, cycle_id: int, label: str) -> bool:
        changed = await self.hass.async_add_executor_job(
            self.storage.label_cycle, cycle_id, label
        )
        if changed:
            await self.async_refresh()
        return changed

    async def async_stop(self) -> None:
        for unsub in self._unsub:
            unsub()
        self._unsub.clear()
        for task in tuple(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        async with self._lock:
            if self.active_since is not None and self._unsaved:
                await self._flush()
        self._callbacks.clear()
