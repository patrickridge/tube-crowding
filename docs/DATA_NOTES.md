# TfL crowding data: what Phase 0 found (6 Oct 2026)

Checked against the live API, including a sweep of all 270 tube stations.

## Endpoints

| Endpoint | Returns |
|---|---|
| `GET /crowding/{naptan}` | Typical profile: 7 days x 96 fifteen-minute bands, plus AM/PM peak band labels |
| `GET /crowding/{naptan}/{day}` | One day (`MON`..`SUN`), same shape |
| `GET /crowding/{naptan}/Live` | `dataAvailable`, `percentageOfBaseline`, `timeLocal` |
| `GET /StopPoint/Mode/tube` | All tube stops; filter `stopType == NaptanMetroStation` to get the 270 stations |
| `GET /StopPoint/Search/{q}` | Free-text search; returns **hub** IDs (`HUBKGX`), which the crowding API does *not* accept |
| `GET /Line/Mode/tube/Status` | Line status (useful for v2) |

## Units and resolution

- `percentageOfBaseLine` is a **fraction** despite its name: `0.25` means 25% of baseline.
- TfL does not document the baseline. It is **per station**: quiet Kensal Green peaks at
  0.71 while King's Cross peaks at 0.56, so values are *not* comparable across stations
  as absolute crowd sizes. The median station peak is 0.34. Treat them as relative busyness.
- Typical: 15-minute bands, `00:00-00:15` ... `23:45-00:00`.
- Live is on the same scale as typical (live/typical ratio 0.8-1.4 across 12 stations,
  Tue 21:40). It updates about every 5 minutes, and the timestamp lags real time by a few minutes.

## Coverage (tube only)

- 267/270 stations return a full 7x96 typical grid; **252** have real (non-zero) data.
- No usable typical data: **Monument** (`isFound: false`, and Bank has data),
  **Hammersmith (District & Piccadilly)**, plus 15 stations that return an all-zero grid:
  Arsenal, Caledonian Road, Canning Town, Colindale, Heathrow T5, Holloway Road,
  Kensington (Olympia), Ladbroke Grove, Pimlico, Russell Square, St James's Park,
  South Kenton, Seven Sisters, Willesden Junction, West Acton.
- Live available at 253 stations (the same gaps).
- Elizabeth line, Overground, DLR and national rail IDs (`910G...`, `940GZZDL...`) return empty.

## Quirks the parser handles

- An unknown NaPTAN returns **HTTP 200** with `daysOfWeek: []`, not 404.
- An all-zero profile means "not measured", not "always empty".
- Hammersmith (H&C) returns **192** bands per day: every band twice with different values. We average them.
- `daysOfWeek` is in random order.
- Small overnight values at stations with no night service (e.g. Roding Valley, 01:00-02:00).
  This is noise to smooth, not a real crowd.

## Rate limits and keys

- Anonymous access works, but gets HTTP 429 after roughly 25-50 quick calls.
- With a free key from the API portal: 500 requests/min. Pass it as `?app_key=...`.

## Licence

TfL transport data terms (based on OGL v2): the app must show **"Powered by TfL Open Data"**.
Must not use TfL logos or branding in a way that implies endorsement. No scraping.
