"""Constants for EG.D HDO."""

DOMAIN = "egd_hdo"

# Public EG.D endpoints, no account needed.
HDO_URL = "https://hdo.distribuce24.cz/casy"
REGION_URL = "https://hdo.distribuce24.cz/region"
INFO_URL = "https://www.egd.cz/vse-o-nizkem-tarifu-hdo-nocni-proud"

CONF_DEVICE = "device"
CONF_PSC = "psc"
CONF_REGION = "region"
CONF_TARIFF = "tariff"
CONF_CODE = "code"

# What switches the low tariff -> EG.D data region. None: the PSČ decides.
# Keys are lowercase because they are translation keys.
DEVICE_RECEIVER = "receiver"
DEVICE_REGIONS: dict[str, str | None] = {
    DEVICE_RECEIVER: None,
    "smart_meter": "SM",
    "time_switch": "PH",
    "tou_meter": "TOU",
}
