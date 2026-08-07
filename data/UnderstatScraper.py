"""
Understat scraper, hybrid two-phase approach:

  Phase 1 (library): collect match IDs for ALL seasons up front, with a small
                     respectful delay between season requests. Fast and light.
  Phase 2 (own scraper): per season, loop its match ids and scrape match_info
                     for the advanced stats (PPDA, deep, etc.), with a delay.

Stage 1 uses understatapi so we don't hand-roll league-page extraction.
Stage 2 keeps our own match-page scrape for the rich stats the library omits.
Saved per season (understat_matches_<season>.pickle/csv), like the PL scraper.

understat season = start year: 2024 -> 2024/25.
"""

import re
import json
import time
import random
from pathlib import Path

import requests
import pandas as pd
from understatapi import UnderstatClient

SEASONS = ["2025", "2024", "2023", "2022", "2021", "2020", "2019", "2018"]
MATCH_URL = "https://understat.com/match/{match_id}"
HEADERS = {"User-Agent": "Mozilla/5.0 (research)"}

SEASON_PAUSE = (1, 2)     # between season id-collection calls (light)
MATCH_PAUSE = (1, 2)    # between match-page scrapes
SAVE_EVERY = 25


def collect_ids(seasons=SEASONS):
    """Phase 1: {season: [match_id, ...]} for all seasons, via the library."""
    ids_by_season = {}
    with UnderstatClient() as understat:
        for season in seasons:
            try:
                matches = understat.league(league="EPL").get_match_data(season=season)
                ids_by_season[season] = [m["id"] for m in matches if m.get("id")]
                print(f"{season}: {len(ids_by_season[season])} match ids")
            except Exception as e:
                print(f"{season}: id collection error - {e}")
                ids_by_season[season] = []
            time.sleep(random.uniform(*SEASON_PAUSE))
    return ids_by_season


def get_match_info(match_id):
    """Phase 2 unit: match page -> match_info -> advanced stats dict, or None."""
    r = requests.get(MATCH_URL.format(match_id=match_id), headers=HEADERS, timeout=20)
    r.raise_for_status()
    m = re.search(r"match_info\s*=\s*JSON\.parse\('([^']+)", r.text)
    if not m:
        return None
    decoded = bytes(m.group(1), "utf-8").decode("unicode_escape")
    return json.loads(decoded)


def scrape_season(season, ids, out_dir="data/understat"):
    """Phase 2 for one season: scrape advanced stats for its match ids. Resumable."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stats_path = out / f"understat_matches_{season}.pickle"

    # resume: skip ids already scraped
    if stats_path.exists():
        done = pd.read_pickle(stats_path)
        rows = done.to_dict("records")
        have = set(str(x) for x in done["id"]) if "id" in done else set()
        ids = [i for i in ids if str(i) not in have]
        print(f"{season}: resuming, {len(have)} done, {len(ids)} to go")
    else:
        rows = []

    total = len(ids)
    for n, mid in enumerate(ids, 1):
        try:
            info = get_match_info(mid)
            if info:
                info["understat_season"] = season
                rows.append(info)
        except Exception as e:
            print(f"  match {mid}: {e}")
        if n % SAVE_EVERY == 0:
            pd.DataFrame(rows).to_pickle(stats_path)
            print(f"  {season}: ...{n}/{total}")
        time.sleep(random.uniform(*MATCH_PAUSE))

    df = pd.DataFrame(rows)
    df.to_pickle(stats_path)
    df.to_csv(out / f"understat_matches_{season}.csv", index=False)
    print(f"{season}: {len(df)} matches saved")
    return df


def scrape_all(seasons=SEASONS, out_dir="data/understat"):
    """Phase 1 (all seasons' ids) then Phase 2 (per season)."""
    ids_by_season = collect_ids(seasons)
    print()
    for season in seasons:
        scrape_season(season, ids_by_season.get(season, []), out_dir)


if __name__ == "__main__":
    scrape_all()