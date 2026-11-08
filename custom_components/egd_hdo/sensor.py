"""Start and end of the current or next low-tariff window."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import HdoConfigEntry, HdoCoordinator
from .entity import HdoEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HdoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the window start and end sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            WindowSensor(coordinator, "window_start", end=False),
            WindowSensor(coordinator, "window_end", end=True),
        ]
    )


class WindowSensor(HdoEntity, SensorEntity):
    """Timestamp of the current window if NT is on, else of the next one."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: HdoCoordinator, key: str, *, end: bool) -> None:
        super().__init__(coordinator, key)
        self._end = end

    @property
    def native_value(self) -> datetime | None:
        state = self.hdo_state
        return state.end if self._end else state.start
