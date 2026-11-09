"""EG.D HDO (low tariff) schedule: parsing, lookup and window maths.

Pure Python without Home Assistant imports, so the tests need only the
standard library. Everything read from the EG.D API passes through here,
which makes this module the trust boundary: it validates every field it uses.

Data quirks (see tests/fixtures for real samples):
- A schedule is identified by region + tariff + ``kodHdo_A``. ``skupinaPovelu``
  and the A/B/DP triple are not unique.
- ``sazba`` is ``tariffs[-relays][-uses]`` and each part is a comma list:
  ``"C45d,D45d-relé1-PV"`` is two tariffs on one relay, ``"D25d-relé1-TAR,TUV"``
  one relay with two uses, ``"A2T-relé1,2"`` relays 1 and 2.
- A period starting in year 9999 repeats every year and may wrap New Year;
  an end in year 9999 means "no end".
- ``23:59`` is the end of the day. A weekday missing from ``dny`` has no NT.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from itertools import product
import re
from typing import Any
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Prague")  # EG.D publishes Czech wall-clock times
DAY_MINUTES = 24 * 60
HORIZON_DAYS = 8  # a week ahead covers every weekly pattern
RECEIVER_REGIONS = frozenset({"VERSACOM", "VYCHOD"})  # receivers labelled A/B/DP

_RECURRING_YEAR = "9999"
_TIME_RE = re.compile(r"(\d{2}):(\d{2})(?::(\d{2}))?")
_PSC_RE = re.compile(r"\d{5}")
_DIGITS_RE = re.compile(r"\d{1,4}")


class HdoDataError(ValueError):
    """EG.D data does not have the expected shape."""


Interval = tuple[int, int]  # NT from/to, minutes after local midnight


@dataclass(frozen=True, slots=True)
class Period:
    """One validity period of a schedule with its weekly NT intervals."""

    first: date | None  # None: no lower bound
    last: date | None  # None: no upper bound
    yearly: tuple[tuple[int, int], tuple[int, int]] | None  # (month, day) span
    days: tuple[tuple[Interval, ...], ...]  # index 0 = Monday

    def covers(self, day: date) -> bool:
        """Return whether the period applies on ``day``."""
        if self.yearly is not None:
            start, end = self.yearly
            md = (day.month, day.day)
            return start <= md <= end if start <= end else md >= start or md <= end
        return (self.first is None or self.first <= day) and (
            self.last is None or day <= self.last
        )

    def specificity(self) -> int:
        """Sort key: fixed dates beat yearly seasons beat open-ended periods."""
        if self.yearly is not None:
            return 1
        return 0 if self.last is not None else 2


@dataclass(frozen=True, slots=True)
class Schedule:
    """All published periods of one code and tariff, most specific first."""

    periods: tuple[Period, ...]

    def intervals_on(self, day: date) -> tuple[Interval, ...] | None:
        """NT intervals on ``day``; None when EG.D has not published that day."""
        for period in self.periods:
            if period.covers(day):
                return period.days[day.isoweekday() - 1]
        return None


@dataclass(frozen=True, slots=True)
class State:
    """Low-tariff state at one instant. Datetimes are in UTC."""

    active: bool | None  # None: no published schedule for now
    start: datetime | None  # current window if active, else the next one
    end: datetime | None
    next_change: datetime  # when the state must be computed again


@dataclass(frozen=True, slots=True)
class CodeOption:
    """One HDO code to offer in the config flow."""

    code: str  # kodHdo_A, the stored identifier
    name: str  # what the customer sees on the receiver or meter
    label: str  # name plus today's NT times


def normalize_psc(value: str) -> str:
    """Return a 5-digit PSČ or raise ValueError."""
    psc = "".join(str(value).split())
    if not _PSC_RE.fullmatch(psc):
        raise ValueError("PSČ must have 5 digits")
    return psc


def regions_for_psc(rows: Any, psc: str) -> list[str]:
    """EG.D regions serving ``psc`` (data from the /region endpoint)."""
    return sorted(
        {
            row["Region"]
            for row in _rows(rows)
            if row.get("PSC") == psc and isinstance(row.get("Region"), str)
        }
    )


def split_tariffs(sazba: str) -> list[str]:
    """One option per tariff, relay and use: ``"C45d,D45d-relé1-TAR,TUV"`` gives four."""
    lists = [
        [f"relé{p}" if p.isdigit() else p for p in (p.strip() for p in seg.split(",")) if p]
        for seg in sazba.split("-")
    ]
    return ["-".join(combo) for combo in product(*lists)]


def tariffs(entries: Any, region: str) -> list[str]:
    """All tariffs (with relay) EG.D lists for ``region``."""
    found: set[str] = set()
    for entry in _rows(entries):
        if entry.get("region") == region:
            for sazba in _sazby(entry):
                found.update(split_tariffs(sazba["sazba"]))
    return sorted(found)


def codes(entries: Any, region: str, tariff: str, today: date) -> list[CodeOption]:
    """HDO codes for a region and tariff, labelled with today's NT times."""
    names = {
        entry["kodHdo_A"]: _code_name(entry) for entry, _ in _matching(entries, region, tariff)
    }
    options = []
    for code in sorted(names):
        try:
            intervals = select_schedule(entries, region, tariff, code).intervals_on(today)
        except HdoDataError:
            continue  # one broken row must not hide every other code
        times = ", ".join(_format(i) for i in intervals) if intervals else "—"
        options.append(CodeOption(code, names[code], f"{names[code]} · {times}"))
    return options


def select_schedule(entries: Any, region: str, tariff: str, code: str) -> Schedule:
    """Parse the schedule of one code and tariff; raise HdoDataError if absent."""
    periods = {
        _parse_period(entry, sazba)
        for entry, sazba in _matching(entries, region, tariff)
        if entry["kodHdo_A"] == code
    }
    if not periods:
        raise HdoDataError(f"No schedule for code {code!r} and tariff {tariff!r}")
    return Schedule(tuple(sorted(periods, key=Period.specificity)))


def state_at(schedule: Schedule, now: datetime) -> State:
    """Low-tariff state at the aware datetime ``now``."""
    now = now.astimezone(UTC)
    today = now.astimezone(TZ).date()
    if schedule.intervals_on(today) is None:  # tomorrow may be published
        return State(None, None, None, _instant(today + timedelta(days=1), 0))
    windows, horizon = _windows(schedule, today - timedelta(days=1))
    for start, end in windows:
        if start <= now < end:
            return State(True, start, end, end)
        if now < start:
            return State(False, start, end, start)
    return State(False, None, None, horizon)  # no NT within the published days


def _windows(
    schedule: Schedule, first_day: date
) -> tuple[list[tuple[datetime, datetime]], datetime]:
    """Merged NT windows from ``first_day`` on, and where published data ends."""
    merged: list[tuple[datetime, datetime]] = []
    day = first_day
    for _ in range(HORIZON_DAYS + 1):
        intervals = schedule.intervals_on(day)
        if intervals is None and day != first_day:
            break
        for from_min, to_min in intervals or ():
            start, end = _instant(day, from_min), _instant(day, to_min)
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        day += timedelta(days=1)
    return merged, _instant(day, 0)


def _instant(day: date, minutes: int) -> datetime:
    """Prague wall-clock ``day`` + ``minutes`` as a UTC datetime."""
    day += timedelta(days=minutes // DAY_MINUTES)
    minutes %= DAY_MINUTES
    local = datetime(day.year, day.month, day.day, minutes // 60, minutes % 60, tzinfo=TZ)
    return local.astimezone(UTC)


def _format(interval: Interval) -> str:
    return "–".join(f"{m // 60:02d}:{m % 60:02d}" for m in interval)


def _code_name(entry: dict[str, Any]) -> str:
    """The code as printed on the customer's device."""
    code = entry["kodHdo_A"]
    abdp = [entry.get(key) for key in ("A", "B", "DP")]
    if entry.get("region") in RECEIVER_REGIONS and all(
        isinstance(v, str) and _DIGITS_RE.fullmatch(v) for v in abdp
    ):
        a, b, dp = (int(v) for v in abdp)
        return f"A{a} B{b} DP{dp} ({code})"
    return code


def _rows(data: Any) -> Iterator[dict[str, Any]]:
    """Dict rows of a top-level JSON list; other junk rows are skipped."""
    if not isinstance(data, list):
        raise HdoDataError("Expected a JSON list from EG.D")
    return (row for row in data if isinstance(row, dict))


def _sazby(entry: dict[str, Any]) -> Iterator[dict[str, Any]]:
    sazby = entry.get("sazby")
    return (
        s
        for s in (sazby if isinstance(sazby, list) else ())
        if isinstance(s, dict) and isinstance(s.get("sazba"), str)
    )


def _matching(
    entries: Any, region: str, tariff: str
) -> Iterator[tuple[dict[str, Any], dict[str, Any]]]:
    for entry in _rows(entries):
        if entry.get("region") != region or not isinstance(entry.get("kodHdo_A"), str):
            continue
        for sazba in _sazby(entry):
            if tariff in split_tariffs(sazba["sazba"]):
                yield entry, sazba


def _parse_period(entry: dict[str, Any], sazba: dict[str, Any]) -> Period:
    od_year, od_md = _parse_date(entry.get("od"))
    do_year, do_md = _parse_date(entry.get("do"))
    if od_year == _RECURRING_YEAR:
        first = last = None
        yearly: tuple[tuple[int, int], tuple[int, int]] | None = (od_md, do_md)
    else:
        first = _date(od_year, od_md)
        last = None if do_year == _RECURRING_YEAR else _date(do_year, do_md)
        yearly = None
    days: list[tuple[Interval, ...]] = [()] * 7
    for day in _list(sazba.get("dny"), "dny"):
        weekday = day.get("denVTydnu") if isinstance(day, dict) else None
        if type(weekday) is not int or not 1 <= weekday <= 7:
            raise HdoDataError(f"Invalid weekday {weekday!r}")
        days[weekday - 1] = tuple(sorted(_parse_interval(c) for c in _list(day.get("casy"), "casy")))
    return Period(first, last, yearly, tuple(days))


def _parse_date(value: Any) -> tuple[str, tuple[int, int]]:
    """``{"den": "01", "mesic": "09", "rok": "2026"}`` -> ("2026", (9, 1))."""
    if not isinstance(value, dict):
        raise HdoDataError(f"Invalid date {value!r}")
    parts = [value.get(key) for key in ("rok", "mesic", "den")]
    if not all(isinstance(p, str) and _DIGITS_RE.fullmatch(p) for p in parts):
        raise HdoDataError(f"Invalid date {value!r}")
    year, month, day = parts
    if len(year) != 4 or not 1 <= int(month) <= 12 or not 1 <= int(day) <= 31:
        raise HdoDataError(f"Invalid date {value!r}")
    return year, (int(month), int(day))


def _date(year: str, month_day: tuple[int, int]) -> date:
    try:
        return date(int(year), *month_day)
    except ValueError as err:
        raise HdoDataError(f"Invalid date {year}-{month_day}") from err


def _parse_interval(value: Any) -> Interval:
    if not isinstance(value, dict):
        raise HdoDataError(f"Invalid interval {value!r}")
    start, end = _minutes(value.get("od")), _minutes(value.get("do"))
    if end == DAY_MINUTES - 1:
        end = DAY_MINUTES  # EG.D writes the end of the day as 23:59
    if not start < end:
        raise HdoDataError(f"Invalid interval {value!r}")
    return start, end


def _minutes(value: Any) -> int:
    match = _TIME_RE.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        raise HdoDataError(f"Invalid time {value!r}")
    hours, minutes, seconds = (int(g or 0) for g in match.groups())
    if hours > 23 or minutes > 59 or seconds > 59:
        raise HdoDataError(f"Invalid time {value!r}")
    return hours * 60 + minutes


def _list(value: Any, what: str) -> list[Any]:
    if not isinstance(value, list):
        raise HdoDataError(f"Expected a list for {what!r}")
    return value
