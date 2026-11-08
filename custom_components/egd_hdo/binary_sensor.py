"""Low tariff on/off."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import HdoConfigEntry
from .entity import HdoEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HdoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the low-tariff binary sensor."""
    async_add_entities([LowTariffSensor(entry.runtime_data, "low_tariff")])


class LowTariffSensor(HdoEntity, BinarySensorEntity):
    """On while the low tariff (NT) is active; unknown if EG.D has no data."""

    @property
    def is_on(self) -> bool | None:
        return self.hdo_state.active
