import requests
import cloudscraper
from bs4 import BeautifulSoup
import re

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}

def clean_team_name(name):
    """Очищает название команды от спецсимволов для поиска"""
    return re.sub(r'[^\w\s]', '', name).strip()

def get_arbworld_moneyway(match_name):
    """Парсит реальные денежные прогрузы с Arbworld"""
    try:
        url = "https://www.arbworld.net/en/moneyway/football-1x2"
        session = requests.Session()
        response = session.get(url, headers=HEADERS, timeout=4)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            rows = soup.find_all("tr")
            teams = [clean_team_name(t).lower() for t in match_name.replace("—", "-").split("-") if len(clean_team_name(t)) > 3]
            
            for row in rows:
                row_text = row.get_text().lower()
                if any(team in row_text for team in teams):
                    cols = [td.get_text(strip=True) for td in row.find_all("td")]
                    if len(cols) >= 4:
                        return f"Moneyway: {cols[0]} | Объемы: {' | '.join(cols[1:6])}"
        return None
    except Exception:
        return None


def get_corner_stats_data(match_name):
    """Парсит данные по угловым с Corner Stats"""
    try:
        scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
        search_query = requests.utils.quote(clean_team_name(match_name.replace("—", "-").split("-")[0]))
        url = f"https://corner-stats.com/index.php?route=information/search&search={search_query}"
        
        response = scraper.get(url, timeout=4)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            tables = soup.find_all("table")
            for table in tables:
                text = table.get_text().lower()
                if "corners" in text or "угловые" in text:
                    rows = [tr.get_text(" ", strip=True) for tr in table.find_all("tr")[:2]]
                    if rows:
                        return f"Corner Stats: {' | '.join(rows)}"
        return None
    except Exception:
        return None


def get_footystats_data(match_name):
    """Парсит показатели FootyStats"""
    try:
        scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
        first_team = clean_team_name(match_name.replace("—", "-").split("-")[0])
        search_url = f"https://footystats.org/search?q={requests.utils.quote(first_team)}"
        
        response = scraper.get(search_url, timeout=4)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            xg_elements = soup.find_all(class_="xg-value") or soup.find_all("div", class_="team-stat")
            if xg_elements:
                stats_text = " ".join([el.get_text(strip=True) for el in xg_elements[:3]])
                return f"FootyStats: {stats_text}"
        return None
    except Exception:
        return None


def get_fbref_data(match_name):
    """Парсит данные продвинутой статистики FBref"""
    try:
        scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
        first_team = clean_team_name(match_name.replace("—", "-").split("-")[0])
        search_url = f"https://fbref.com/en/search/search.fcgi?search={requests.utils.quote(first_team)}"
        
        response = scraper.get(search_url, timeout=4)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            results = soup.find_all("div", class_="search-item")
            if results:
                summary = results[0].get_text(" ", strip=True)[:150]
                return f"FBref: {summary}"
        return None
    except Exception:
        return None


def get_oddsportal_dropping_odds(match_name):
    """Парсит движение коэффициентов Oddsportal"""
    try:
        scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
        search_query = requests.utils.quote(clean_team_name(match_name.replace("—", "-").split("-")[0]))
        url = f"https://www.oddsportal.com/search/{search_query}/"
        
        response = scraper.get(url, timeout=4)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            rows = soup.find_all("tr")
            for row in rows:
                if "dropping" in row.get_text().lower():
                    return f"Oddsportal Dropping: {row.get_text(' ', strip=True)[:120]}"
        return None
    except Exception:
        return None
        
