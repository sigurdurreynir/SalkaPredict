"""
Step 1 — collect match-level facts from matchweek cards:
url, teams, score, season, matchweek. Saved per season.
Stats are fetched separately (fetch_stats.py) and merged on `url`.

NOTE: targets premierleague.com matchweek pages as of 2025
(/en/matches/premier-league/<season>/matchweek-<n>).
"""

import time
import random
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BASE_URL = "https://www.premierleague.com"
COOKIE_BTN_ID = "onetrust-accept-btn-handler"
MATCH_CARD_SEL = 'a[data-testid="matchCard"]'
DAY_DATE_SEL = 'span[data-testid="dayDate"]'   # day header, e.g. 'Sat 12 Sep'

MATCHWEEKS = range(1, 39)

# rate limiting — be gentle on the source, avoid IP blocks
PAGE_PAUSE = (4, 8)     # random seconds between matchweek pages
JITTER = (0.5, 1.5)     # extra small random wait after each page load


def _sleep(rng):
    time.sleep(random.uniform(*rng))


def _resolve_date(raw, season):
    """'Sat 12 Sep' + season slug -> 'YYYY/MM/DD'. Aug-Dec = start yr, Jan-Jul = end yr."""
    if not raw or not season:
        return None
    start_yr = int("20" + season.split("-")[0][-2:])
    for yr in (start_yr, start_yr + 1):
        try:
            dt = pd.to_datetime(f"{raw} {yr}", format="%a %d %b %Y")
            if (dt.month >= 8) == (yr == start_yr):
                return dt.strftime("%Y/%m/%d")
        except ValueError:
            continue
    return None


def _build_driver():
    opts = webdriver.ChromeOptions()
    for flag in ("--headless=new", "--no-sandbox", "--disable-dev-shm-usage"):
        opts.add_argument(flag)
    opts.add_argument("--window-size=1920,1080")
    return webdriver.Chrome(options=opts)


def _accept_cookies(driver):
    try:
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, COOKIE_BTN_ID))).click()
    except Exception:
        pass


def matchweek_url(season, wk):
    return f"{BASE_URL}/en/matches/premier-league/{season}/matchweek-{wk}"


def get_cards(page_url, driver, season, matchweek):
    """Match-level records from one matchweek page, each stamped with its day date."""
    driver.get(page_url)
    _accept_cookies(driver)
    _sleep(JITTER)   # small random wait, less bot-like
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, MATCH_CARD_SEL)))
    except Exception:
        return []  # no cards (unplayed week or selector miss)

    soup = BeautifulSoup(driver.page_source, "html.parser")
    # walk day-headers and cards in document order; carry the latest date forward
    nodes = soup.select(f"{DAY_DATE_SEL}, {MATCH_CARD_SEL}")
    records, current_date = [], None
    for node in nodes:
        if node.get("data-testid") == "dayDate":
            current_date = _resolve_date(node.get_text(strip=True), season)
            continue

        href = node.get("href")
        if not href:
            continue
        names = node.select('[data-testid="matchCardTeamFullName"]')
        score = node.select_one('[data-testid="matchCardScore"]')
        rec = {
            "url": href if href.startswith("http") else BASE_URL + href,
            "Season": season,
            "Matchweek": matchweek,
            "Date": current_date,
            "Home_Team": names[0].get_text(strip=True) if len(names) > 0 else None,
            "Away_Team": names[1].get_text(strip=True) if len(names) > 1 else None,
            "Home_Goals": None,
            "Away_Goals": None,
        }
        if score:  # 'H - A'; blank for unplayed fixtures
            parts = score.get_text(strip=True).split("-")
            if len(parts) == 2 and parts[0].strip().isdigit():
                rec["Home_Goals"] = int(parts[0].strip())
                rec["Away_Goals"] = int(parts[1].strip())
        records.append(rec)
    return records


def collect_season(season, out_dir="data/matches"):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    driver = _build_driver()
    driver.get(BASE_URL)
    _accept_cookies(driver)
    records = []
    try:
        for wk in MATCHWEEKS:
            recs = get_cards(matchweek_url(season, wk), driver, season, wk)
            print(f"  {season} mw{wk}: {len(recs)} matches")
            records += recs
            _sleep(PAGE_PAUSE)   # gentle gap between pages
    finally:
        driver.quit()

    df = pd.DataFrame(records).drop_duplicates("url").reset_index(drop=True)
    _save(df, out, season)
    print(f"{season}: {len(df)} matches saved\n")
    return df


def _save(df, out, season):
    """Save pickle + csv; warn (don't crash) if a file is locked, e.g. open in Excel."""
    df.to_pickle(out / f"matches_{season}.pickle")  # pickle rarely locked
    try:
        df.to_csv(out / f"matches_{season}.csv", index=False)
    except PermissionError:
        print(f"  WARNING: matches_{season}.csv is locked (open in Excel?) — "
              f"pickle saved, csv skipped")


if __name__ == "__main__":
    # scrape ONE season at a time — gentler on the source, avoids IP blocks.
    # change this and re-run for each season you want (4-7 total is plenty):
    SEASON = "2018-19"
    collect_season(SEASON)