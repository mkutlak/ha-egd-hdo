"""Download the EG.D schedule and keep the part for one config entry."""

from __future__ import annotations

from datetime import timedelta
import json
import logging
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from . import hdo
from .const import CONF_CODE, CONF_REGION, CONF_TARIFF, DOMAIN, HDO_URL

_LOGGER = logging.getLogger(__name__)

MAX_BYTES = 16 * 1024 * 1024  # /casy is ~1.5 MB; refuse anything absurd
_TIMEOUT = aiohttp.ClientTimeout(total=60)

type HdoConfigEntry = ConfigEntry[HdoCoordinator]


async def async_fetch_json(
    hass: HomeAssistant, url: str, etag: str | None = None
) -> tuple[Any, str | None]:
    """GET a public EG.D endpoint and decode JSON, with a size cap.

    Returns the data and its ETag; the data is None when it still matches ``etag``.
    """
    session = async_get_clientsession(hass)
    headers = {"If-None-Match": etag} if etag else None
    body = bytearray()
    async with session.get(
        url, headers=headers, timeout=_TIMEOUT, raise_for_status=True
    ) as resp:
        if resp.status == 304:
            return None, etag
        async for chunk in resp.content.iter_chunked(64 * 1024):
            body += chunk
            if len(body) > MAX_BYTES:
                raise hdo.HdoDataError(f"{url} sent more than {MAX_BYTES} bytes")
        new_etag = resp.headers.get("ETag")
    return json.loads(body), new_etag


class HdoCoordinator(DataUpdateCoordinator[hdo.Schedule]):
    """Refresh the schedule twice a day; EG.D publishes weeks ahead."""

    config_entry: HdoConfigEntry

    def __init__(self, hass: HomeAssistant, entry: HdoConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(hours=12),
            always_update=False,
        )
        self._etag: str | None = None  # ETag of the body that self.data came from

    async def _async_update_data(self) -> hdo.Schedule:
        data = self.config_entry.data
        try:
            entries, etag = await async_fetch_json(self.hass, HDO_URL, self._etag)
            if entries is None:  # 304: EG.D data unchanged
                return self.data
            schedule = hdo.select_schedule(
                entries, data[CONF_REGION], data[CONF_TARIFF], data[CONF_CODE]
            )
            self._etag = etag
            return schedule
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            # ValueError covers bad JSON and HdoDataError.
            if self.data is not None:
                _LOGGER.warning("Keeping the last EG.D schedule, update failed: %s", err)
                return self.data
            raise UpdateFailed(f"Cannot load the EG.D schedule: {err}") from err
