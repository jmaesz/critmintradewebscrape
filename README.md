# critmintradewebscrape

Pulls commodity-level Metals & Minerals trade data from [resourcetrade.earth](https://resourcetrade.earth)
(Chatham House) for the Philippines, Thailand, and Malaysia — both exports-to-world
and imports-from-world — covering every year 2000-2024, and merges it into CSV /
Excel outputs.

## What it does

The script reverse-engineers resourcetrade.earth's own export flow:

1. `GET .../downloads?year=Y&exporter=CODE&category=ID&units=weight` kicks off an
   async export job and returns a job id (use `importer=CODE` instead of `exporter=CODE`
   for the reverse trade direction).
2. `GET .../downloads/<id>` is polled until the job reports `"status": "completed"`,
   at which point it returns an S3 url for the generated `.xlsx`.
3. The `.xlsx` is downloaded and its `Trades` sheet (one row per exporter / importer /
   commodity / year) is parsed.

"Metals and minerals" is category id `5` on the site, but that id is an aggregate —
its export file only breaks resources down into 6 subcategory buckets. To get real
commodity names (Gold, Platinum, Iron ores and concentrates, Manganese, ...) each
subcategory is queried separately:

| id  | subcategory           |
|-----|------------------------|
| 34  | Industrial minerals    |
| 35  | Iron and steel         |
| 37  | Non-ferrous metals     |
| 38  | Precious metals        |
| 39  | Specialty metals       |
| 160 | Metals not specified   |

Each request's `year` parameter returns a **trailing 5-year window** ending at that
year (e.g. `year=2004` returns rows for 2000-2004). Five checkpoint years —
2004, 2009, 2014, 2019, 2024 — tile the full 2000-2024 range with no gaps or overlap,
so only 5 requests per country/direction/subcategory are needed instead of 25.

Total requests for the default config: 3 countries × 2 directions × 6 subcategories ×
5 checkpoints = **180 requests**, taking roughly 10-15 minutes with the built-in
politeness delay between requests.

## Usage

```bash
pip install requests pandas openpyxl
python fetch_resourcetrade_data.py
```

Downloaded `.xlsx` files are cached in `./raw_downloads/` so re-running the script
after an interruption skips work that's already done.

### Outputs

- `resourcetrade_metals_2000_2024.csv` — combined long-format table, all countries,
  both directions, all subcategories
- `resourcetrade_metals_2000_2024_exports.csv` / `..._imports.csv` — the same data
  split by trade direction
- `resourcetrade_metals_2000_2024.xlsx` — one workbook with 6 sheets, one per
  `{country} ({export|import})` combination

Generated data files are otherwise not committed to this repo (see `.gitignore`) —
run the script to regenerate them locally. An example of the `.xlsx` output is
checked in at [`examples/resourcetrade_metals_2000_2024.xlsx`](examples/resourcetrade_metals_2000_2024.xlsx).

## Configuration

Edit the constants at the top of `fetch_resourcetrade_data.py` to change scope:

- `COUNTRIES` — dict of `{name: UN M49 country code}`
- `CATEGORIES` — dict of `{subcategory id: name}`
- `UNITS` — `"weight"` (tonnes) or `"value"` (USD)
- `YEAR_CHECKPOINTS` — which trailing-5-year windows to pull
