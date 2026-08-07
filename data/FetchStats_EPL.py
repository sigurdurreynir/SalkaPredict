"""
Step 2 — fetch per-match stats from each match's /stats page, keyed on `url`,
then merge onto the collected match records (collect_matches.py) on `url`.

NOTE: targets premierleague.com stats pages as of 2025. Stats are div-based
(match-stats__table-row); date is on the scoreboard (scoreboard-bottom__match-info-item).
"""

import time
import random
import pickle
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BASE_URL = "https://www.premierleague.com"
COOKIE_BTN_ID = "onetrust-accept-btn-handler"

# rate limiting — match pages are many, so be gentle to avoid IP blocks.
# ~30 min/season target: page load + render (~3-4s) + this pause per match.
MATCH_PAUSE = (1.5, 3)   # random seconds between match pages
MATCH_RETRIES = 3


def _sleep(rng):
    time.sleep(random.uniform(*rng))


def _build_driver():
    opts = webdriver.ChromeOptions()
    for flag in ("--headless=new", "--no-sandbox", "--disable-dev-shm-usage"):
        opts.add_argument(flag)
    opts.add_argument("--window-size=1920,1080")
    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(30)   # hung page fails fast, retry fires sooner
    return driver


def _accept_cookies(driver):
    try:
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, COOKIE_BTN_ID))).click()
    except Exception:
        pass


def _overview_to_stats(url):
    """Turn a match URL (…/overview or bare) into its /stats URL."""
    u = url.rstrip("/")
    if u.endswith("overview"):
        return u.rsplit("/", 1)[0] + "/stats"
    if u.endswith("stats"):
        return u
    return u + "/stats"


def _parse_stats(soup):
    """Div-based stats page -> {stat_name: (home, away)}. First occurrence wins."""
    stats = {}
    for row in soup.select("div.match-stats__table-row"):
        name_el = row.select_one(".match-stats__stat-name")
        if not name_el:
            continue
        if "match-stats__table-row--bar" in row.get("class", []):  # Possession
            home_el = row.select_one(".match-stats__stat-percentage--home")
            away_el = row.select_one(".match-stats__stat-percentage--away")
        else:
            home_el = row.select_one(".match-stats__stat-value.match-stats__table-cell--home")
            away_el = row.select_one(".match-stats__stat-value.match-stats__table-cell--away")
        if home_el and away_el:
            stats.setdefault(name_el.get_text(strip=True),
                             (home_el.get_text(strip=True), away_el.get_text(strip=True)))
    return stats


def _fetch_one(driver, url):
    """Fetch stats for one match. Returns a dict keyed with `url`, or None."""
    driver.get(_overview_to_stats(url))
    time.sleep(1)   # brief settle; the wait below handles actual load timing
    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "div.match-stats__table-row")))

    stats = _parse_stats(BeautifulSoup(driver.page_source, "html.parser"))
    if not stats:
        return None

    row = {"url": url}
    for name, (h, a) in stats.items():
        key = name.replace(" ", "_")
        row[f"Home_{key}"] = h
        row[f"Away_{key}"] = a
    return row


def fetch_season_stats(season, in_dir="data/matches", out_dir="data/stats", limit=None):
    """
    Read collected matches for a season, fetch stats for each, save keyed on url.
    Resumable: skips matches already in stats_<season>.pickle, so if a run is
    blocked partway you just re-run and it picks up where it stopped. Saves
    progress every SAVE_EVERY matches so a block never loses much.
    `limit` caps how many matches to fetch this run (for safe trial runs).
    """
    SAVE_EVERY = 20
    matches = pd.read_pickle(Path(in_dir) / f"matches_{season}.pickle")
    urls = matches.dropna(subset=["Home_Goals"])["url"].tolist()  # skip unplayed

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stats_path = out / f"stats_{season}.pickle"

    # resume: load what's already scraped, skip those urls
    if stats_path.exists():
        done_df = pd.read_pickle(stats_path)
        rows = done_df.to_dict("records")
        have = set(done_df["url"])
        urls = [u for u in urls if u not in have]
        print(f"{season}: resuming, {len(have)} already done, {len(urls)} to go")
    else:
        rows = []

    if limit:                    # trial run: only fetch this many
        urls = urls[:limit]
        print(f"{season}: limited to {len(urls)} matches this run")

    RESTART_EVERY = 50   # rebuild driver periodically; long sessions degrade

    def fresh_driver(old=None):
        if old is not None:
            try:
                old.quit()
            except Exception:
                pass
        d = _build_driver()
        d.get(BASE_URL)
        _accept_cookies(d)
        return d

    driver = fresh_driver()
    failed = []
    try:
        for i, url in enumerate(urls, 1):
            for attempt in range(MATCH_RETRIES):
                try:
                    r = _fetch_one(driver, url)
                    if r is not None:
                        rows.append(r)
                        _sleep(MATCH_PAUSE)   # gentle randomized gap
                        break
                except Exception as e:
                    print(f"[{i}/{len(urls)}] [{attempt+1}/{MATCH_RETRIES}] {url}: {e}")
                    driver = fresh_driver(driver)   # a hang taints the session; rebuild
            else:
                failed.append(url)

            if i % RESTART_EVERY == 0:   # proactively rebuild before it degrades
                driver = fresh_driver(driver)
            if i % SAVE_EVERY == 0:
                pd.DataFrame(rows).to_pickle(stats_path)
                print(f"  ...checkpoint at {i}/{len(urls)} ({len(rows)} total)")
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    stats_df = pd.DataFrame(rows)
    stats_df.to_pickle(stats_path)
    pickle.dump(failed, open(out / f"failed_{season}.pickle", "wb"))
    print(f"{season}: {len(stats_df)} stat rows total, {len(failed)} failed this run")
    return stats_df, failed


def merge_season(season, matches_dir="data/matches", stats_dir="data/stats",
                 out_dir="data/merged"):
    """Merge match facts + stats on `url` into one season dataframe."""
    matches = pd.read_pickle(Path(matches_dir) / f"matches_{season}.pickle")
    stats = pd.read_pickle(Path(stats_dir) / f"stats_{season}.pickle")
    merged = matches.merge(stats, on="url", how="inner")

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    merged.to_pickle(out / f"epl_{season}.pickle")
    merged.to_csv(out / f"epl_{season}.csv", index=False)
    print(f"{season}: merged {len(merged)} matches, {merged.shape[1]} columns")
    return merged


if __name__ == "__main__":
    SEASON = "2025-26"
    # trial first: fetch 10 matches, check timing + output, confirm no block
    #fetch_season_stats(SEASON, limit=10)
    # then the full season (resumes past the 10 already done):
    fetch_season_stats(SEASON)
    # merge_season(SEASON)