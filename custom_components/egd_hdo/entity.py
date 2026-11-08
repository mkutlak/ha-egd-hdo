"""Base entity: state is computed from the schedule, refreshed at each switch."""

from __future__ import annotations

from datetime import datetime

from homeassistant.core import CALLBACK_TYPE, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import hdo
from .const import DOMAIN, INFO_URL
from .coordinator import HdoCoordinator


class HdoEntity(CoordinatorEntity[HdoCoordinator]):
    """Entity whose state changes at NT boundaries, without polling."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: HdoCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.unique_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="EG.D",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=INFO_URL,
        )
        self._unsub_timer: CALLBACK_TYPE | None = None

    @property
    def hdo_state(self) -> hdo.State:
        """Low-tariff state right now."""
        return hdo.state_at(self.coordinator.data, dt_util.utcnow())

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._cancel_timer)
        self._schedule_next_change()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._schedule_next_change()
        super()._handle_coordinator_update()

    @callback
    def _schedule_next_change(self) -> None:
        self._cancel_timer()
        self._unsub_timer = async_track_point_in_utc_time(
            self.hass, self._handle_change, self.hdo_state.next_change
        )

    @callback
    def _handle_change(self, _now: datetime) -> None:
        self._unsub_timer = None
        self.async_write_ha_state()
        self._schedule_next_change()

    @callback
    def _cancel_timer(self) -> None:
        if self._unsub_timer is not None:
            self._unsub_timer()
            self._unsub_timer = None
