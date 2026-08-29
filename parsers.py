def split_teams(match_str: str):
    """Надежный сплиттер названий команд"""
    for sep in [" — ", " – ", " - ", " vs ", " vs. ", " v ", " против ", "—", "–", "-"]:
        if sep in match_str:
            parts = match_str.split(sep, 1)
            return parts[0].strip(), parts[1].strip()
    words = match_str.strip().split()
    if len(words) >= 4:
        mid = len(words) // 2
        return " ".join(words[:mid]), " ".join(words[mid:])
    return match_str.strip(), "Соперник"

def get_footystats_data(m): return None
def get_fbref_data(m): return None
def get_corner_stats_data(m): return None
def get_arbworld_moneyway(m): return None
def get_oddsportal_dropping_odds(m): return None
    
