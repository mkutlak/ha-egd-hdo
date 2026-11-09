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
Když EG.D na dnešek žádný rozvrh nezveřejní, je stav `unknown`. Když ve zveřejněných dnech
žádný nízký tarif není, je stav `off` a začátek i konec jsou `unknown`.

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
   U přijímače zadejte i **PSČ**; podle něj se určí region. Patří-li PSČ do dvou regionů EG.D,
   následuje krok **Region**: zkuste jeden a nabídnuté kódy porovnejte se štítkem přijímače.
2. **Sazba a relé**, např. `D25d-relé1-TAR`. Sazbu najdete na faktuře.
   Konec říká, co relé spíná: `TAR` nízký tarif elektroměru, `TUV` ohřev vody,
   `AKU` akumulační vytápění, `EMO` nabíjení elektromobilu. Jedno relé může spínat víc věcí,
   pak mají volby (např. `D25d-relé1-TAR` a `D25d-relé1-TUV`) stejné časy.
3. **Kód HDO**, viz [Kde najdu kód HDO](#kde-najdu-kód-hdo).
   U každé volby jsou vidět dnešní časy NT, takže je můžete porovnat se skutečností;
   `—` znamená, že kód dnes žádný NT nemá. Odpovídá-li sazbě jediný kód, tento krok se přeskočí.

Chcete-li sledovat víc relé (např. TAR i TUV), přidejte integraci vícekrát.

### Co vznikne

Zařízení s názvem `HDO <kód> · <sazba>` a třemi entitami z tabulky výše. ID entit se odvozují
od názvu zařízení; najdete je v **Nastavení → Zařízení a služby → EG.D HDO → zařízení**.
Příklady níže používají krátká zástupná ID, která nahraďte svými.

### Změna a odebrání

Integrace nemá žádná další nastavení. Jinou sazbu nebo kód nastavíte tak, že položku odeberete
a přidáte znovu. Stejnou kombinaci regionu, sazby a kódu lze přidat jen jednou.

### Když to nejde

- „Zadejte PSČ s 5 číslicemi.“: jen číslice, mezera uvnitř nevadí.
- „Pro toto PSČ nemá EG.D region HDO.“: EG.D není váš distributor. Distributora najdete
  na faktuře; jinde v ČR je to ČEZ Distribuce nebo PREdistribuce.
- „API EG.D není dostupné.“: EG.D má výpadek, nebo Home Assistant nemá internet. Zkuste to později.
- „API EG.D poslalo data, kterým integrace nerozumí.“: EG.D změnilo formát dat. Založte
  [issue](https://github.com/mkutlak/ha-egd-hdo/issues) a uveďte sazbu a typ zařízení;
  kód HDO ani PSČ neposílejte.

### Kde najdu kód HDO

- **Přijímač HDO**: otevřete elektroměrový rozvaděč. Vedle elektroměru je přijímač HDO
  (např. Siemens 7RR701 nebo 7RR703, FMX 100, 300, 511, 519 nebo 529, RC2301).
  Na jeho štítku je buď **kód HDO** (jen číslice), nebo **povel HDO** (písmena a číslice,
  u regionů Východ a Versacom ve tvaru A/B/DP, např. `A1 B5 DP4`).
  Fotky štítků jednotlivých přijímačů ukazuje návod EG.D
  [Jak vyhledat kód HDO](https://www.egd.cz/jak-vyhledat-kod-hdo).
  V seznamu kódů je u povelu A/B/DP v závorce i číselný kód, takže najdete obojí.
- **Chytrý elektroměr**: kód je na displeji elektroměru nebo v aplikaci Distribuce24.
- **Spínací hodiny**: kód začíná na `PH`.
- **Kód nenajdete?** Porovnejte dnešní časy u jednotlivých voleb s tím, kdy se vám nízký tarif
  opravdu přepíná, nebo s časy z [vyhledávání časů HDO](https://www.egd.cz/vyhledat-casy-hdo-pro-vasi-lokalitu) na webu EG.D.

## Příklady

ID entit v příkladech jsou zástupná; svá najdete podle [Co vznikne](#co-vznikne).

### Nabíjet baterii jen v nízkém tarifu

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

### Spotřeba zvlášť v NT a VT

Měřič [utility_meter](https://www.home-assistant.io/integrations/utility_meter/) s tarify vytvoří
`sensor.spotreba_mesicni_nt`, `sensor.spotreba_mesicni_vt` a `select.spotreba_mesicni`,
který automatizace přepíná podle HDO. Oba senzory lze přidat do panelu Energie.

```yaml
utility_meter:
  spotreba_mesicni:
    source: sensor.elektromer_spotreba  # kWh z vašeho elektroměru
    cycle: monthly
    tariffs: [nt, vt]

automation:
  - alias: "HDO: přepnout tarif měřiče"
    triggers:
      - trigger: state
        entity_id: binary_sensor.hdo_nizky_tarif
        to: ["on", "off"]
    actions:
      - action: select.select_option
        target:
          entity_id: select.spotreba_mesicni
        data:
          option: "{{ 'nt' if trigger.to_state.state == 'on' else 'vt' }}"
```

### Upozornění 15 minut před koncem NT

Podmínka na `on` je nutná: když NT neběží, ukazuje senzor konec *příštího* NT.

```yaml
automation:
  - alias: "HDO: končí nízký tarif"
    triggers:
      - trigger: time
        at:
          entity_id: sensor.hdo_konec_nizkeho_tarifu
          offset: "-00:15:00"
    conditions:
      - condition: state
        entity_id: binary_sensor.hdo_nizky_tarif
        state: "on"
    actions:
      - action: notify.mobile_app_muj_telefon
        data:
          message: "Nízký tarif končí za 15 minut."
```

### Podmínka: zbývají aspoň 2 hodiny NT

Na dashboardu ukazují senzory začátku a konce relativní čas („za 2 hodiny“) samy; šablona je
potřeba jen v automatizacích. Ve stavu `unknown` je podmínka nepravdivá a nehlásí chybu.

```yaml
conditions:
  - condition: state
    entity_id: binary_sensor.hdo_nizky_tarif
    state: "on"
  - condition: template
    value_template: >
      {% set end = states('sensor.hdo_konec_nizkeho_tarifu') | as_datetime %}
      {{ end is datetime and end - now() >= timedelta(hours=2) }}
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
Start/end are `unknown` when no window is published ahead.

**Install** (Home Assistant 2026.11+): use the HACS button above, or add
`https://github.com/mkutlak/ha-egd-hdo` as a custom repository of type *Integration*,
install **EG.D HDO** and restart. Then add the integration and pick the device type
(plus your postal code for an HDO receiver), the tariff and relay, and the HDO code
from your receiver label, smart meter display or the Distribuce24 app.
A *Region* step appears when your postal code spans two EG.D regions, and the code step is
skipped when only one code matches the tariff. There are no options to edit: to change the
tariff or code, remove the entry and add it again.

**Finding the HDO code**: the HDO receiver sits next to the electricity meter in the meter box.
Its label shows either a numeric *kód HDO* or a *povel HDO* such as `A1 B5 DP4`; the code list
shows both. EG.D's guide [Jak vyhledat kód HDO](https://www.egd.cz/jak-vyhledat-kod-hdo)
has photos of each receiver model. Time-switch codes start with `PH`. If you cannot find the code,
compare today's times shown next to each option with when your low tariff really switches.

**Examples**: the YAML above works in any language; replace the placeholder entity IDs with
those listed on the device page (*Settings → Devices & services → EG.D HDO*).

**Privacy**: only the region, tariff and code are stored. The postal code is used once and never stored.

Not affiliated with EG.D. The real HDO signal is authoritative.

## Development

The schedule logic lives in `custom_components/egd_hdo/hdo.py` and needs only the
Python standard library. Its tests use real EG.D data excerpts:

```sh
python3 -I -m unittest discover -s tests
```

MIT license, see [LICENSE](LICENSE).
