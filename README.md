# EG.D HDO pro Home Assistant

Časy nízkého tarifu (HDO) distributora **EG.D** (dříve E.ON Distribuce) v Home Assistantu.
Data bere z veřejného API EG.D, takže nepotřebujete účet ani přihlášení.

*English below.*

## Co dostanete

Pro každý nastavený kód HDO jedno zařízení se třemi entitami:

| Entita | Typ | Hodnota |
|---|---|---|
| Nízký tarif | binary sensor | `on` během nízkého tarifu (NT), jinak `off` |
| Začátek nízkého tarifu | sensor (čas) | začátek právě běžícího NT, jinak příštího |
| Konec nízkého tarifu | sensor (čas) | konec právě běžícího NT, jinak příštího |

Stav se přepne přesně v čase změny. Rozvrh se stahuje dvakrát denně.
Když EG.D na dnešek žádný rozvrh nezveřejní, je stav `unknown`.

## Instalace

Potřebujete Home Assistant **2026.11** nebo novější a HACS (v HA 2026.11 jako *Marketplace*).

[![Otevřít v HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=mkutlak&repository=ha-egd-hdo&category=integration)

Nebo ručně:

1. HACS → menu ⋮ → **Vlastní repozitáře** (Custom repositories).
2. URL `https://github.com/mkutlak/ha-egd-hdo`, typ **Integrace**.
3. Najděte **EG.D HDO**, stáhněte a restartujte Home Assistant.

Bez HACS: zkopírujte složku `custom_components/egd_hdo` do `config/custom_components/` a restartujte.

## Nastavení

**Nastavení → Zařízení a služby → Přidat integraci → EG.D HDO**, pak:

1. **Co spíná nízký tarif**: přijímač HDO v rozvaděči, chytrý elektroměr, spínací hodiny (kód `PH…`) nebo elektroměr TOU.
   U přijímače zadejte i **PSČ**; podle něj se určí region.
2. **Sazba a relé**, např. `D25d-relé1-TAR`. Sazbu najdete na faktuře.
   `TAR` je hlavní tarifní relé, `TUV` spíná ohřev vody.
3. **Kód HDO**. Je na štítku přijímače HDO v elektroměrovém rozvaděči
   (u regionů Východ a Versacom ve tvaru A/B/DP, např. `A1 B5 DP4`),
   na displeji chytrého elektroměru nebo v aplikaci Distribuce24.
   U každé volby jsou vidět dnešní časy NT, takže je můžete porovnat se skutečností.

Chcete-li sledovat víc relé (např. TAR i TUV), přidejte integraci vícekrát.

## Příklad: nabíjení baterie v nízkém tarifu

Názvy entit se odvíjí od názvu zařízení; níže je nahraďte svými.

```yaml
automation:
  - alias: "Baterie: nabíjet ze sítě jen v NT"
    triggers:
      - trigger: state
        entity_id: binary_sensor.hdo_nizky_tarif
        to: ["on", "off"]
    actions:
      - action: "switch.turn_{{ trigger.to_state.state }}"
        target:
          entity_id: switch.nabijeni_baterie_ze_site
```

Kolik hodin NT zbývá (pro šablonu nebo podmínku):

```jinja
{{ ((as_datetime(states('sensor.hdo_konec_nizkeho_tarifu')) - now()).total_seconds() / 3600) | round(1) }}
```

## Soukromí a bezpečnost

- Integrace volá jen `https://hdo.distribuce24.cz/casy` a `/region`, bez přihlášení a bez osobních údajů.
- Ukládá jen region, sazbu a kód HDO. PSČ se použije jednou při nastavení; neukládá se ani neloguje.
- Odpověď API má limit 16 MiB a každé použité pole se kontroluje. Vadná data aktualizaci zastaví,
  stav se z nich nepočítá; zůstane poslední platný rozvrh.
- Žádné závislosti mimo Home Assistant.
- Zranitelnosti hlaste podle [SECURITY.md](SECURITY.md).

## Upozornění

Neoficiální projekt, nemá vztah k EG.D. Rozhodující je vždy skutečný signál HDO;
data v API se mohou lišit nebo chybět. Používáte na vlastní riziko.

---

## English

Home Assistant integration for the low-tariff (HDO) schedule of **EG.D**, the Czech
distribution system operator formerly known as E.ON Distribuce. It uses EG.D's public API,
so no account is needed.

**Entities** per configured HDO code: a *Low tariff* binary sensor, and *Low tariff start* /
*Low tariff end* timestamp sensors for the current window, or the next one while the low tariff is off.
States switch exactly at the boundaries; the schedule is downloaded twice a day.

**Install** (Home Assistant 2026.11+): use the HACS button above, or add
`https://github.com/mkutlak/ha-egd-hdo` as a custom repository of type *Integration*,
install **EG.D HDO** and restart. Then add the integration and pick the device type
(plus your postal code for an HDO receiver), the tariff and relay, and the HDO code
from your receiver label, smart meter display or the Distribuce24 app.

**Privacy**: only the region, tariff and code are stored. The postal code is used once and never stored.

Not affiliated with EG.D. The real HDO signal is authoritative.

## Development

The schedule logic lives in `custom_components/egd_hdo/hdo.py` and needs only the
Python standard library. Its tests use real EG.D data excerpts:

```sh
python3 -I -m unittest discover -s tests
```

MIT license, see [LICENSE](LICENSE).
