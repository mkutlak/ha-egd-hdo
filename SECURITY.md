# Security

Please report vulnerabilities privately through GitHub:
**Security → Report a vulnerability** on
[mkutlak/ha-egd-hdo](https://github.com/mkutlak/ha-egd-hdo/security/advisories/new).
Do not open a public issue for them.

Only the latest release gets fixes.

## What the integration does

- It sends plain HTTPS GET requests to two public EG.D endpoints,
  `https://hdo.distribuce24.cz/casy` and `https://hdo.distribuce24.cz/region`.
  It sends no account, token, or personal data.
- It stores only the region, tariff, and HDO code in the config entry.
  The postal code (PSČ) is used once during setup; it is not stored or logged.
- Responses are capped at 16 MiB, and every field used is validated before use.
  Bad data makes the update fail; it never reaches Home Assistant as state.
- It has no dependencies beyond Home Assistant itself.
