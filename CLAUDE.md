# EG.D HDO: notes for agents

Home Assistant custom integration (domain `egd_hdo`, HACS) for the EG.D low-tariff schedule.

## Test

```sh
python3 -I -m unittest discover -s tests
```

No task runner, venv or packages. HA glue (config flow, entities) has no automated tests;
check it in a throwaway `ghcr.io/home-assistant/home-assistant:<min version>` container
with `custom_components/egd_hdo` mounted.

## Rules

- `hdo.py` is pure standard library: it is the trust boundary and the only tested module.
  Put parsing and time maths there, with a test that uses a real data excerpt from `tests/fixtures/`.
  The data quirks are listed in its module docstring; keep that list current.
- Config flow schemas use `probatio`. HA 2026.11 cannot serialize `voluptuous` schemas.
- Minimum HA is the `homeassistant` value in `hacs.json`. Raise it only for a used feature.
- Runtime `requirements` stay empty; HA already ships `aiohttp`.
- Every byte from EG.D is untrusted: keep the 16 MiB cap in `coordinator.async_fetch_json`,
  validate each field you read, raise `HdoDataError` on anything unexpected.
- The PSČ lives only in the config flow's memory: keep it out of config entries, logs and titles.
- Store schedule identity as region + tariff + `kodHdo_A`; other fields repeat across codes.
- Translations: keep `translations/en.json` and `cs.json` key-identical; selector option keys are lowercase.

## Release

1. Bump `version` in `custom_components/egd_hdo/manifest.json`.
2. Commit, tag `vX.Y.Z`, push the tag.
3. `gh release create vX.Y.Z --generate-notes`. HACS offers releases to users.
