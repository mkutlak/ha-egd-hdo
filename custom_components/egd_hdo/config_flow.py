"""Config flow: device type -> (PSČ -> region) -> tariff -> HDO code."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import probatio

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)
from homeassistant.util import dt as dt_util

from . import hdo
from .const import (
    CONF_CODE,
    CONF_DEVICE,
    CONF_PSC,
    CONF_REGION,
    CONF_TARIFF,
    DEVICE_RECEIVER,
    DEVICE_REGIONS,
    DOMAIN,
    HDO_URL,
    REGION_URL,
)
from .coordinator import async_fetch_json

_LOGGER = logging.getLogger(__name__)


def _select(
    options: list[str] | list[SelectOptionDict],
    mode: SelectSelectorMode = SelectSelectorMode.DROPDOWN,
    translation_key: str | None = None,
) -> SelectSelector:
    config = SelectSelectorConfig(options=options, mode=mode)
    if translation_key:  # the selector rejects translation_key=None
        config["translation_key"] = translation_key
    return SelectSelector(config)


class HdoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Pick one HDO schedule. The PSČ is used once and never stored."""

    VERSION = 1

    def __init__(self) -> None:
        self._entries: Any = None  # the /casy list, kept only while the flow runs
        self._regions: list[str] = []
        self._region = ""
        self._tariff = ""
        self._codes: list[hdo.CodeOption] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask what switches the low tariff and, for a receiver, the PSČ."""
        errors: dict[str, str] = {}
        if user_input is not None:
            device = user_input[CONF_DEVICE]
            try:
                psc = (
                    hdo.normalize_psc(user_input.get(CONF_PSC, ""))
                    if device == DEVICE_RECEIVER
                    else None
                )
            except ValueError:
                errors[CONF_PSC] = "invalid_psc"
            else:
                errors = await self._async_load(device, psc)
            if not errors:
                if len(self._regions) > 1:
                    return await self.async_step_region()
                self._region = self._regions[0]
                return await self.async_step_tariff()

        schema = probatio.Schema(
            {
                probatio.Required(CONF_DEVICE, default=DEVICE_RECEIVER): _select(
                    list(DEVICE_REGIONS), SelectSelectorMode.LIST, CONF_DEVICE
                ),
                probatio.Optional(CONF_PSC): TextSelector(),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    async def _async_load(self, device: str, psc: str | None) -> dict[str, str]:
        """Download EG.D data; return form errors."""
        try:
            if psc is None:
                regions = [DEVICE_REGIONS[device]]
            else:
                rows, _ = await async_fetch_json(self.hass, REGION_URL)
                if not (regions := hdo.regions_for_psc(rows, psc)):
                    return {CONF_PSC: "unknown_psc"}
            self._entries, _ = await async_fetch_json(self.hass, HDO_URL)
            self._regions = [r for r in regions if hdo.tariffs(self._entries, r)]
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.debug("Cannot reach EG.D: %s", err)
            return {"base": "cannot_connect"}
        except ValueError as err:  # bad JSON or HdoDataError
            _LOGGER.warning("EG.D sent data this integration cannot read: %s", err)
            return {"base": "bad_data"}
        return {} if self._regions else {"base": "bad_data"}

    async def async_step_region(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """The PSČ belongs to more than one EG.D region."""
        if user_input is not None:
            self._region = user_input[CONF_REGION]
            return await self.async_step_tariff()
        return self.async_show_form(
            step_id="region",
            data_schema=probatio.Schema(
                {
                    probatio.Required(CONF_REGION): _select(
                        self._regions, SelectSelectorMode.LIST
                    )
                }
            ),
        )

    async def async_step_tariff(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick the distribution tariff and relay, e.g. D25d-relé1-TAR."""
        if user_input is not None:
            self._tariff = user_input[CONF_TARIFF]
            today = dt_util.now(hdo.TZ).date()
            self._codes = hdo.codes(self._entries, self._region, self._tariff, today)
            if not self._codes:
                return self.async_abort(reason="bad_data")
            if len(self._codes) == 1:
                return await self._async_create(self._codes[0])
            return await self.async_step_code()
        return self.async_show_form(
            step_id="tariff",
            data_schema=probatio.Schema(
                {
                    probatio.Required(CONF_TARIFF): _select(
                        hdo.tariffs(self._entries, self._region)
                    )
                }
            ),
        )

    async def async_step_code(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick the HDO code; each label shows today's NT times."""
        if user_input is not None:
            by_code = {option.code: option for option in self._codes}
            return await self._async_create(by_code[user_input[CONF_CODE]])
        options = [SelectOptionDict(value=o.code, label=o.label) for o in self._codes]
        return self.async_show_form(
            step_id="code",
            data_schema=probatio.Schema({probatio.Required(CONF_CODE): _select(options)}),
        )

    async def _async_create(self, option: hdo.CodeOption) -> ConfigFlowResult:
        await self.async_set_unique_id(f"{self._region}_{option.code}_{self._tariff}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=f"HDO {option.name} · {self._tariff}",
            data={
                CONF_REGION: self._region,
                CONF_TARIFF: self._tariff,
                CONF_CODE: option.code,
            },
        )
