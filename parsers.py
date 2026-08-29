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

# Таблица транслитерации для корректного поиска русских названий в глобальной базе
TRANSLIT_DICT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
    '—': '-', '–': '-'
}

def transliterate(text: str) -> str:
    res = []
    for char in text.lower():
        res.append(TRANSLIT_DICT.get(char, char))
    return "".join(res)

def clean_name(name: str) -> str:
    name = re.sub(r'\(.*?\)', '', name)
    name = re.sub(r'[^\w\s-]', '', name)
    return transliterate(name.strip())

@lru_cache(maxsize=128)
def search_fotmob_team(team_name: str):
    """Поиск ID команды с поддержкой транслитерации"""
    try:
        clean = clean_name(team_name)
        # Берем первое ключевое слово, если название длинное
        query = clean.split()[0] if clean.split() else clean
        url = f"https://www.fotmob.com/api/search/search?term={requests.utils.quote(query)}"
        res = requests.get(url, headers=FOTMOB_HEADERS, timeout=5)
        
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
    """Получение турнирной статистики команды"""
    if not team_id:
        return None
    try:
        url = f"https://www.fotmob.com/api/teams?id={team_id}"
        res = requests.get(url, headers=FOTMOB_HEADERS, timeout=5)
        if res.status_code == 200:
            return res.json()
        return None
    except Exception:
        return None

def extract_metrics_for_match(match_name: str):
    """Сбор и сопоставление реальных метрик обоих клубов"""
    teams_raw = match_name.replace("—", "-").replace("–", "-").split("-")
    if len(teams_raw) < 2:
        return None

    t1_input, t2_input = teams_raw[0].strip(), teams_raw[1].strip()
    t1_id, t1_real = search_fotmob_team(t1_input)
    t2_id, t2_real = search_fotmob_team(t2_input)

    stats1 = get_fotmob_team_stats(t1_id) if t1_id else None
    stats2 = get_fotmob_team_stats(t2_id) if t2_id else None

    result = {
        "t1_name": t1_real or t1_input,
        "t2_name": t2_real or t2_input,
        "form1": "Нет данных",
        "form2": "Нет данных",
        "rank1": "—",
        "rank2": "—",
        "goals1": "—",
        "goals2": "—",
        "status": "OK" if (stats1 or stats2) else "NOT_FOUND"
    }

    if stats1:
        overview = stats1.get("overview", {})
        table_data = overview.get("table", [{}])[0].get("data", {}).get("table", {}).get("all", [])
        for row in table_data:
            if row.get("id") == t1_id:
                result["rank1"] = f"{row.get('idx')} место ({row.get('pts')} очк.)"
                result["goals1"] = f"Мячи: {row.get('scoresStr')}"
                break
        form = [f.get("result", "") for f in stats1.get("form", []) if isinstance(f, dict)]
        if form:
            result["form1"] = "".join(form[-5:])

    if stats2:
        overview = stats2.get("overview", {})
        table_data = overview.get("table", [{}])[0].get("data", {}).get("table", {}).get("all", [])
        for row in table_data:
            if row.get("id") == t2_id:
                result["rank2"] = f"{row.get('idx')} место ({row.get('pts')} очк.)"
                result["goals2"] = f"Мячи: {row.get('scoresStr')}"
                break
        form = [f.get("result", "") for f in stats2.get("form", []) if isinstance(f, dict)]
        if form:
            result["form2"] = "".join(form[-5:])

    return result

def get_footystats_data(match_name):
    m = extract_metrics_for_match(match_name)
    if not m or m.get("status") == "NOT_FOUND":
        return None
    return f"{m['t1_name']} [{m['rank1']}, {m['goals1']}, Форма: {m['form1']}] vs {m['t2_name']} [{m['rank2']}, {m['goals2']}, Форма: {m['form2']}]"

def get_fbref_data(match_name):
    return None

def get_corner_stats_data(match_name):
    return None

def get_arbworld_moneyway(match_name):
    return None

def get_oddsportal_dropping_odds(match_name):
    return None
    
