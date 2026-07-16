"""
Same pipeline as fetch_resourcetrade_data.py, run for USA, South Korea,
and Japan instead. See that module's docstring for how the scraper works.

Run with:
    python fetch_resourcetrade_data_usa_korea_japan.py

Output:
    ./resourcetrade_metals_2000_2024_usa_korea_japan.csv
    ./resourcetrade_metals_2000_2024_usa_korea_japan_exports.csv
    ./resourcetrade_metals_2000_2024_usa_korea_japan_imports.csv
    ./resourcetrade_metals_2000_2024_usa_korea_japan.xlsx
"""

from fetch_resourcetrade_data import run_batch

# UN M49 country codes
COUNTRIES = {
    "USA": 842,
    "South Korea": 410,
    "Japan": 392,
}

if __name__ == "__main__":
    run_batch(COUNTRIES, "resourcetrade_metals_2000_2024_usa_korea_japan")
