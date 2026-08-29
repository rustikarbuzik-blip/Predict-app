import requests
import re
import streamlit as st
from functools import lru_cache

# Получаем ключ API-Football из Secrets Streamlit
API_KEY = st.secrets.get("FOOTBALL_API_KEY", "")
API_URL = "https://v3.football.api-sports.io"
HEADERS = {
    "x-apisports-key": API_KEY
}

# Словарь синонимов для популярных клубов
TEAM_ALIASES = {
    "сиэтл": "Seattle Sounders", "sounders": "Seattle Sounders",
    "чикаго": "Chicago Fire", "fire": "Chicago Fire",
    "портленд": "Portland Timbers", "timbers": "Portland Timbers",
    "остин": "Austin", "сан диего": "San Diego", "сандиего": "San Diego",
    "гэлакси": "LA Galaxy", "интер майами": "Inter Miami", "майами": "Inter Miami",
    "монреаль": "CF Montreal", "колорадо": "Colorado Rapids",
    "солт лейк": "Real Salt Lake", "реал солт": "Real Salt Lake",
    "миннесота": "Minnesota United", "нэшвилл": "Nashville SC",
    "цинциннати": "FC Cincinnati", "севилья": "Sevilla",
    "атлетико": "Atletico Madrid", "реал": "Real Madrid",
    "барселона": "Barcelona", "арсенал": "Arsenal", "челси": "Chelsea",
    "ливерпуль": "Liverpool", "манчестер сити": "Manchester City",
    "псж": "Paris Saint Germain", "ювентус": "Juventus", "интер": "Inter"
}

TRANSLIT_DICT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
}

def normalize_query(name: str) -> str:
    """Очищает и нормализует имя команды для API поиска"""
    cleaned = re.sub(r'[^\w\s]', '', name.lower()).strip()
    for ru_name, en_name in TEAM_ALIASES.items():
        if ru_name in cleaned:
            return en_name
    return "".join(TRANSLIT_DICT.get(c, c) for c in cleaned)

def split_teams(match_str: str):
    """Разделяет строку матча на команду хозяев и гостей"""
    for sep in [" — ", " – ", " - ", " vs ", " vs. ", " v ", " против ", "—", "–", "-"]:
        if sep in match_str:
            parts = match_str.split(sep, 1)
            return parts[0].strip(), parts[1].strip()
    words = match_str.strip().split()
    if len(words) >= 4:
        mid = len(words) // 2
        return " ".join(words[:mid]), " ".join(words[mid:])
    return match_str.strip(), "Соперник"

@lru_cache(maxsize=128)
def search_team_api(team_name: str):
    """Поиск ID клуба в базе API-Football"""
    if not API_KEY:
        return None, None
    try:
        search_query = normalize_query(team_name)
        url = f"{API_URL}/teams?search={requests.utils.quote(search_query)}"
        res = requests.get(url, headers=HEADERS, timeout=5)
        if res.status_code == 200:
            data = res.json().get("response", [])
            if data:
                team_obj = data[0].get("team", {})
                return team_obj.get("id"), team_obj.get("name")
        return None, None
    except Exception:
        return None, None

@lru_cache(maxsize=128)
def get_team_recent_form(team_id: int):
    """Получение статистики только фактически сыгранных матчей"""
    if not team_id or not API_KEY:
        return "—"
    try:
        # Запрашиваем последние завершенные игры
        url = f"{API_URL}/fixtures?team={team_id}&last=10"
        res = requests.get(url, headers=HEADERS, timeout=5)
        if res.status_code == 200:
            raw_fixtures = res.json().get("response", [])
            
            # Фильтруем только сыгранные матчи со счетом
            fixtures = [
                f for f in raw_fixtures 
                if f.get("fixture", {}).get("status", {}).get("short") in ["FT", "AET", "PEN"]
                and f.get("goals", {}).get("home") is not None
            ][-5:]

            if not fixtures:
                return "Форма: нет свежих сыгранных матчей"

            form_letters = []
            goals_scored = 0
            goals_conceded = 0

            for f in fixtures:
                teams = f.get("teams", {})
                goals = f.get("goals", {})
                
                hg = goals.get("home") or 0
                ag = goals.get("away") or 0
                
                is_home = (teams.get("home", {}).get("id") == team_id)
                my_goals = hg if is_home else ag
                opp_goals = ag if is_home else hg
                
                goals_scored += my_goals
                goals_conceded += opp_goals

                if my_goals > opp_goals:
                    form_letters.append("W")
                elif my_goals == opp_goals:
                    form_letters.append("D")
                else:
                    form_letters.append("L")

            form_str = "".join(form_letters) if form_letters else "—"
            games_count = max(len(fixtures), 1)
            avg_scored = round(goals_scored / games_count, 1)
            avg_conceded = round(goals_conceded / games_count, 1)

            return f"Форма: {form_str} | Мячи: {goals_scored}:{goals_conceded} (в ср. {avg_scored} заб. / {avg_conceded} проп.)"
        return "—"
    except Exception:
        return "—"

def get_footystats_data(match_name: str):
    """Сбор статистики по матчу для передачи в нейросеть"""
    t1_input, t2_input = split_teams(match_name)
    t1_id, t1_real = search_team_api(t1_input)
    t2_id, t2_real = search_team_api(t2_input)

    if not t1_id and not t2_id:
        return None

    name1 = t1_real or t1_input
    name2 = t2_real or t2_input
    form1 = get_team_recent_form(t1_id) if t1_id else "нет данных"
    form2 = get_team_recent_form(t2_id) if t2_id else "нет данных"

    return f"1. {name1} [{form1}] vs 2. {name2} [{form2}]"

def get_fbref_data(m): return None
def get_corner_stats_data(m): return None
def get_arbworld_moneyway(m): return None
def get_oddsportal_dropping_odds(m): return None
    
