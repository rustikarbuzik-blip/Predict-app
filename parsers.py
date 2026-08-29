import requests
import re
from functools import lru_cache

FOTMOB_HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.fotmob.com",
    "Referer": "https://www.fotmob.com/"
}

TEAM_ALIASES = {
    "сиэтл": "seattle", "чикаго": "chicago", "портленд": "portland",
    "остин": "austin", "сан диего": "san diego", "сандиего": "san diego",
    "гэлакси": "galaxy", "интер майами": "inter miami", "майами": "inter miami",
    "монреаль": "montreal", "колорадо": "colorado", "солт лейк": "salt lake",
    "миннесота": "minnesota", "нэшвилл": "nashville", "цинциннати": "cincinnati",
    "севилья": "sevilla", "атлетико": "atletico"
}

TRANSLIT_DICT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
}

def clean_search_term(name: str) -> str:
    cleaned = re.sub(r'[^\w\s]', '', name.lower()).strip()
    for ru_name, en_name in TEAM_ALIASES.items():
        if ru_name in cleaned:
            return en_name
    return "".join(TRANSLIT_DICT.get(c, c) for c in cleaned)

@lru_cache(maxsize=128)
def search_fotmob_team(team_name: str):
    try:
        clean = clean_search_term(team_name)
        # Ищем по первому слову для точности
        query = clean.split()[0] if clean.split() else clean
        url = f"https://www.fotmob.com/api/search/search?term={requests.utils.quote(query)}"
        res = requests.get(url, headers=FOTMOB_HEADERS, timeout=4)
        if res.status_code == 200:
            data = res.json()
            teams = data.get("team", []) or data.get("teams", [])
            if teams:
                return teams[0].get("id"), teams[0].get("name")
        return None, None
    except Exception:
        return None, None

@lru_cache(maxsize=128)
def get_fotmob_team_stats(team_id: int):
    if not team_id:
        return None
    try:
        url = f"https://www.fotmob.com/api/teams?id={team_id}"
        res = requests.get(url, headers=FOTMOB_HEADERS, timeout=4)
        if res.status_code == 200:
            return res.json()
        return None
    except Exception:
        return None

def split_teams(match_str: str):
    """Надежный разделитель команд по любым разделителям"""
    for sep in [" — ", " – ", " - ", " vs ", " vs. ", " v ", " против ", "—", "–", "-"]:
        if sep in match_str:
            parts = match_str.split(sep, 1)
            return parts[0].strip(), parts[1].strip()
    # Если разделитель не найден, пробуем разделить пополам
    words = match_str.strip().split()
    if len(words) >= 4:
        mid = len(words) // 2
        return " ".join(words[:mid]), " ".join(words[mid:])
    return match_str.strip(), "Соперник"

def get_footystats_data(match_name: str):
    t1_name, t2_name = split_teams(match_name)
    t1_id, t1_real = search_fotmob_team(t1_name)
    t2_id, t2_real = search_fotmob_team(t2_name)

    if not t1_id and not t2_id:
        return None

    stats1 = get_fotmob_team_stats(t1_id)
    stats2 = get_fotmob_team_stats(t2_id)

    def extract_info(stats, team_id, fallback):
        if not stats:
            return f"{fallback} (данные отсутствуют)"
        name = stats.get("details", {}).get("name", fallback)
        rank, form_str, goals = "—", "—", "—"
        
        overview = stats.get("overview", {})
        table = overview.get("table", [{}])[0].get("data", {}).get("table", {}).get("all", [])
        for row in table:
            if row.get("id") == team_id:
                rank = f"{row.get('idx')} место ({row.get('pts')} очк.)"
                goals = f"голы {row.get('scoresStr')}"
                break
        
        form = [f.get("result", "") for f in stats.get("form", []) if isinstance(f, dict)]
        if form:
            form_str = "".join(form[-5:])
            
        return f"{name} [{rank}, {goals}, форма: {form_str}]"

    return f"{extract_info(stats1, t1_id, t1_name)} vs {extract_info(stats2, t2_id, t2_name)}"

def get_fbref_data(m): return None
def get_corner_stats_data(m): return None
def get_arbworld_moneyway(m): return None
def get_oddsportal_dropping_odds(m): return None
    
