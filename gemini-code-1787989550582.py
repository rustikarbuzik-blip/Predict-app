import streamlit as st
from openai import OpenAI
import requests
import html
from datetime import datetime, timezone, timedelta
import sqlite3
import cloudscraper
from bs4 import BeautifulSoup

st.set_page_config(
    page_title="Match Analytics AI Pro", 
    page_icon="⚽", 
    layout="wide"
)

# Время по Уфе (UTC+5)
UFA_TZ = timezone(timedelta(hours=5))
now_ufa = datetime.now(UFA_TZ)

st.title("⚽ Автоматический генератор прогнозов")
st.caption(f"Время: **{now_ufa.strftime('%d.%m.%Y %H:%M')} (Уфа)** | AI-Core + Proxy Bypass")

# ==============================================================================
# ⚙️ НАСТРОЙКИ И КЛЮЧИ (из Secrets)
# ==============================================================================
vsegpt_key = st.secrets.get("VSEGPT_API_KEY", "")
tg_token = st.secrets.get("TELEGRAM_BOT_TOKEN", "8758421691:AAFfIvHR1g0ak2QejRqhNrpsy-DRXaHgTFU")
tg_chat_id = st.secrets.get("TELEGRAM_CHAT_ID", "500635733")

def escape_html(text):
    return html.escape(str(text)) if text else ""

def split_teams(match_str: str):
    cleaned = match_str.strip()
    for sep in [" — ", " – ", " - ", " vs ", " vs. ", " v ", " против ", "—", "–", "-"]:
        if sep in cleaned:
            parts = cleaned.split(sep, 1)
            t1, t2 = parts[0].strip(), parts[1].strip()
            if t1 and t2:
                return t1, t2
    words = cleaned.split()
    if len(words) >= 2:
        mid = len(words) // 2
        return " ".join(words[:mid]), " ".join(words[mid:])
    return cleaned, "Соперник"

# ==============================================================================
# 🗄️ БАЗА ДАННЫХ SQLITE
# ==============================================================================
def init_db():
    conn = sqlite3.connect("match_history.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS history_v4 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match TEXT,
            match_time_ufa TEXT,
            bet_main TEXT,
            ind_total TEXT,
            corners TEXT,
            my_choice TEXT,
            bet_aggressive TEXT,
            review TEXT,
            confidence TEXT,
            date TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def save_match_to_db(item):
    conn = sqlite3.connect("match_history.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO history_v4 (match, match_time_ufa, bet_main, ind_total, corners, my_choice, bet_aggressive, review, confidence, date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        item.get("match"), item.get("match_time_ufa", "—"),
        item.get("bet_main"), item.get("ind_total", "—"), 
        item.get("corners", "—"), item.get("my_choice", "—"),
        item.get("bet_aggressive"), item.get("review"), 
        item.get("confidence"), item.get("date")
    ))
    conn.commit()
    conn.close()

# ==============================================================================
# 🧠 AI ВЫЗОВ С ЖЕСТКИМИ ПАРАМЕТРАМИ
# ==============================================================================
def ask_vsegpt(prompt, model):
    if not vsegpt_key:
        raise Exception("API ключ VseGPT не указан!")
    client = OpenAI(api_key=vsegpt_key, base_url="https://api.vsegpt.ru/v1")
    
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        frequency_penalty=0.7, # Защита от повторов
        max_tokens=300
    )
    return response.choices[0].message.content

def sanitize_text(text: str) -> str:
    return text.replace("`", "").replace('"', '').replace("'", "").strip() if text else "—"

def parse_match_block(block_text):
    data = {}
    lines = block_text.split('\n')
    current_key = None
    expected_keys = ['ВРЕМЯ_МАТЧА', 'СТАВКА', 'ИНДИВИДУАЛЬНЫЙ_ТОТАЛ', 'УГЛОВЫЕ', 'МОЙ_ВЫБОР', 'БОЛЕЕ_АГРЕССИВНО', 'УВЕРЕННОСТЬ', 'РАЗБОР']
    
    for line in lines:
        l_clean = line.strip()
        if ':' in l_clean:
            parts = l_clean.split(':', 1)
            key = parts[0].strip().upper().replace(" ", "_")
            if key in expected_keys:
                current_key = key
                data[current_key] = sanitize_text(parts[1])
                continue
        if current_key == 'РАЗБОР' and l_clean:
            data[current_key] += " " + l_clean
    return data

def send_telegram_message(text, token, chat_id):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text[:4000], "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=5)
    except:
        pass

# ==============================================================================
# ⚙️ БОКОВОЕ МЕНЮ И ТЕСТ ПРОКСИ
# ==============================================================================
with st.sidebar:
    st.header("⚙️ Настройки AI")
    selected_model = st.selectbox(
        "Модель:",
        ["google/gemini-2.5-flash-lite", "deepseek/deepseek-chat", "openai/gpt-4o-mini", "google/gemini-2.5-flash"],
        index=0
    )
    
    st.markdown("---")
    st.header("🔧 Тест HTTP-Прокси (Cloudscraper)")
    test_url = st.text_input("Ссылка для парсинга:", value="https://smart-tables.ru/")
    
    if st.button("Пробить защиту сайта"):
        with st.spinner("Стучимся через прокси..."):
            ip = st.secrets.get("PROXY_IP", "")
            port = st.secrets.get("PROXY_PORT", "")
            login = st.secrets.get("PROXY_LOGIN", "")
            password = st.secrets.get("PROXY_PASS", "")

            if not ip:
                st.error("Прокси не прописаны в Secrets!")
            else:
                proxy_url = f"http://{login}:{password}@{ip}:{port}"
                proxies = {"http": proxy_url, "https": proxy_url}
                scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})

                try:
                    res = scraper.get(test_url, proxies=proxies, timeout=30)
                    if res.status_code == 200:
                        soup = BeautifulSoup(res.text, 'html.parser')
                        st.success("✅ УСПЕХ! Сайт нас пустил.")
                        st.info(f"Заголовок сайта: {soup.title.text.strip()}")
                    else:
                        st.error(f"❌ Ошибка {res.status_code}")
                except Exception as e:
                    st.error(f"❌ Ошибка соединения: {e}")

# ==============================================================================
# 📝 ОСНОВНОЙ ИНТЕРФЕЙС АНАЛИЗА
# ==============================================================================
match_input = st.text_area(
    "Список матчей (каждый с новой строки):", 
    placeholder="Интер Майами - Монреаль\nАрсенал - Челси",
    height=130
)

if st.button("🚀 Сформировать прогнозы", type="primary", use_container_width=True):
    matches = [m.strip() for m in match_input.strip().split("\n") if m.strip()]
    
    if not matches:
        st.warning("Введите хотя бы один матч!")
    else:
        time_str = now_ufa.strftime('%d.%m.%Y %H:%M')
        
        for i, match in enumerate(matches, 1):
            home, away = split_teams(match)
            with st.spinner(f"Анализ {i}/{len(matches)} ({home} — {away})..."):
                
                prompt = f"""
                Ты профессиональный каппер. Проанализируй матч:
                Хозяева: {home} | Гости: {away}. Время: {time_str} (Уфа).

                🚨 ЖЕСТКИЕ ПРАВИЛА:
                1. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать одинаковые маркеты подряд. Обязательно давай разные варианты: форы (0, +1, -1), тоталы, двойные шансы.
                2. Запрещены сокращения П1/П2. Пиши полное название команды.

                ВЫДАЙ СТРОГО ПО ШАБЛОНУ (без лишних слов и markdown):
                ВРЕМЯ_МАТЧА: {time_str}
                РАЗБОР: [2-3 предложения глубокой аналитики]
                СТАВКА: [{home} или {away} победа / фора]
                ИНДИВИДУАЛЬНЫЙ_ТОТАЛ: [индивидуальный тотал больше/меньше с точным значением на {home} или {away}]
                УГЛОВЫЕ: [прогноз на тотал угловых или победу по угловым]
                МОЙ_ВЫБОР: [твой личный, главный выбор каппера по матчу]
                БОЛЕЕ_АГРЕССИВНО: [ставка с высоким кэфом / сухая победа / ОЗ]
                УВЕРЕННОСТЬ: [⭐⭐⭐⭐ или ⭐⭐⭐⭐⭐]
                """

                try:
                    raw = ask_vsegpt(prompt, selected_model)
                    data = parse_match_block(raw)

                    m_time = data.get('ВРЕМЯ_МАТЧА', time_str)
                    b_main = data.get('СТАВКА', f"{home} победа")
                    i_tot = data.get('ИНДИВИДУАЛЬНЫЙ_ТОТАЛ', "—")
                    corners = data.get('УГЛОВЫЕ', "—")
                    my_choice = data.get('МОЙ_ВЫБОР', b_main)
                    b_agg = data.get('БОЛЕЕ_АГРЕССИВНО', "—")
                    conf = data.get('УВЕРЕННОСТЬ', '⭐⭐⭐⭐')
                    review = data.get('РАЗБОР', 'Анализ завершен.')

                    # UI Вывод
                    with st.expander(f"⚽ {i}. {home} — {away} | {m_time}", expanded=True):
                        st.caption(f"Уверенность: {conf}")
                        st.markdown(f"🎯 **Ставка:** `{b_main}`")
                        st.markdown(f"📈 **Индивидуальный тотал:** `{i_tot}`")
                        st.markdown(f"🚩 **Угловые:** `{corners}`")
                        st.success(f"🔥 **Мой выбор:** `{my_choice}`")
                        st.markdown(f"⚡ **Агрессивно:** `{b_agg}`")
                        st.markdown(f"📋 **Разбор:**\n{review}")

                    # Отправка в Telegram
                    tg_text = (
                        f"⚽ <b>{escape_html(home)} — {escape_html(away)}</b>\n"
                        f"🕒 <b>Время (Уфа):</b> <code>{escape_html(m_time)}</code>\n\n"
                        f"🎯 <b>Ставка:</b> <code>{escape_html(b_main)}</code>\n"
                        f"📈 <b>ИТ:</b> <code>{escape_html(i_tot)}</code>\n"
                        f"🚩 <b>Угловые:</b> <code>{escape_html(corners)}</code>\n"
                        f"🔥 <b>Мой выбор:</b> <code>{escape_html(my_choice)}</code>\n"
                        f"⚡ <b>Агрессивно:</b> <code>{escape_html(b_agg)}</code>\n"
                        f"⭐ <b>Уверенность:</b> {conf}\n\n"
                        f"📝 <b>Разбор:</b>\n{escape_html(review)}"
                    )
                    
                    send_telegram_message(tg_text, tg_token, tg_chat_id)
                    
                    # Сохраняем в БД
                    save_match_to_db({
                        "match": f"{home} — {away}", "match_time_ufa": m_time,
                        "bet_main": b_main, "ind_total": i_tot,
                        "corners": corners, "my_choice": my_choice,
                        "bet_aggressive": b_agg, "review": review, 
                        "confidence": conf, "date": now_ufa.strftime("%Y-%m-%d %H:%M")
                    })

                except Exception as e:
                    st.error(f"Ошибка по матчу {match}: {e}")
