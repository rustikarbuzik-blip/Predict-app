import streamlit as st
from openai import OpenAI
import re
import html
from datetime import datetime, timezone, timedelta
import sqlite3
from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

st.set_page_config(page_title="Match Analytics AI Pro", page_icon="⚽", layout="wide")

# Время по Уфе (UTC+5)
UFA_TZ = timezone(timedelta(hours=5))
now_ufa = datetime.now(UFA_TZ)

st.title("⚽ AI-Каппер: Мульти-Парсинг")
st.caption(f"Время: **{now_ufa.strftime('%d.%m.%Y %H:%M')} (Уфа)** | Proxy: Proxyline (curl_cffi)")

# ==============================================================================
# ⚙️ НАСТРОЙКИ (из Secrets)
# ==============================================================================
vsegpt_key = st.secrets.get("VSEGPT_API_KEY", "")
tg_token = st.secrets.get("TELEGRAM_BOT_TOKEN", "8758421691:AAFfIvHR1g0ak2QejRqhNrpsy-DRXaHgTFU")
tg_chat_id = st.secrets.get("TELEGRAM_CHAT_ID", "500635733")

proxy_ip = st.secrets.get("PROXY_IP", "")
proxy_port = st.secrets.get("PROXY_PORT", "")
proxy_login = st.secrets.get("PROXY_LOGIN", "")
proxy_pass = st.secrets.get("PROXY_PASS", "")

if proxy_ip:
    PROXY_URL = f"http://{proxy_login}:{proxy_pass}@{proxy_ip}:{proxy_port}"
    PROXIES = {"http": PROXY_URL, "https": PROXY_URL}
else:
    PROXIES = None

# ==============================================================================
# 🗄️ БАЗА ДАННЫХ
# ==============================================================================
def init_db():
    conn = sqlite3.connect("match_history.db", check_same_thread=False)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS history_v5 (
            id INTEGER PRIMARY KEY AUTOINCREMENT, match TEXT, match_time_ufa TEXT,
            bet_main TEXT, ind_total TEXT, corners TEXT, my_choice TEXT,
            bet_aggressive TEXT, review TEXT, confidence TEXT, date TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def save_match(item):
    conn = sqlite3.connect("match_history.db", check_same_thread=False)
    conn.execute('''
        INSERT INTO history_v5 (match, match_time_ufa, bet_main, ind_total, corners, my_choice, bet_aggressive, review, confidence, date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        item.get("match"), item.get("match_time_ufa", "—"), item.get("bet_main"), 
        item.get("ind_total", "—"), item.get("corners", "—"), item.get("my_choice", "—"),
        item.get("bet_aggressive"), item.get("review"), item.get("confidence"), item.get("date")
    ))
    conn.commit()
    conn.close()

# ==============================================================================
# 🕵️ ПАРСИНГ ДАННЫХ (ОБХОД ЗАЩИТЫ)
# ==============================================================================
def scrape_url_data(url):
    if not PROXIES:
        return "[Ошибка: Прокси не настроены в Secrets]"
    
    try:
        res = cffi_requests.get(url, proxies=PROXIES, impersonate="chrome110", timeout=30)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            # Вытягиваем весь текст со страницы, очищаем от мусора
            text = soup.get_text(separator=' ', strip=True)
            # Ограничиваем объем, чтобы не перегрузить ИИ (берем первые 8000 символов)
            return text[:8000]
        else:
            return f"[Сайт вернул ошибку {res.status_code}]"
    except Exception as e:
        return f"[Ошибка загрузки: {str(e)}]"

# ==============================================================================
# 🧠 AI ЛОГИКА
# ==============================================================================
def ask_ai(prompt, model):
    client = OpenAI(api_key=vsegpt_key, base_url="https://api.vsegpt.ru/v1")
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5, frequency_penalty=0.7, max_tokens=350
    )
    return response.choices[0].message.content

def parse_block(text):
    data = {}
    current_key = None
    keys = ['ВРЕМЯ_МАТЧА', 'СТАВКА', 'ИНДИВИДУАЛЬНЫЙ_ТОТАЛ', 'УГЛОВЫЕ', 'МОЙ_ВЫБОР', 'БОЛЕЕ_АГРЕССИВНО', 'УВЕРЕННОСТЬ', 'РАЗБОР']
    for line in text.split('\n'):
        if ':' in line:
            k, v = [p.strip() for p in line.split(':', 1)]
            k_upper = k.upper().replace(" ", "_")
            if k_upper in keys:
                current_key = k_upper
                data[current_key] = v.replace("`", "").replace('"', '').strip()
                continue
        if current_key == 'РАЗБОР' and line.strip():
            data[current_key] += " " + line.strip()
    return data

# ==============================================================================
# 📝 ИНТЕРФЕЙС
# ==============================================================================
with st.sidebar:
    st.header("⚙️ Настройки AI")
    selected_model = st.selectbox("Модель:", ["google/gemini-2.5-flash-lite", "deepseek/deepseek-chat"], index=0)

st.markdown("### Введи матчи и ссылки на статистику")
st.caption("Формат: Название матча, а под ним ссылки на FotMob, NB Bet или Arbworld (можно все сразу).")

match_input = st.text_area(
    "Поле ввода:", 
    placeholder="Арсенал - Челси\nhttps://www.fotmob.com/...\nhttps://www.arbworld.net/...",
    height=200
)

if st.button("🚀 Собрать данные и дать прогноз", type="primary", use_container_width=True):
    # Разбиваем ввод на блоки (матчи отделяются пустой строкой или определяются логически)
    blocks = match_input.strip().split("\n\n")
    time_str = now_ufa.strftime('%d.%m.%Y %H:%M')
    
    for block in blocks:
        lines = block.strip().split("\n")
        if not lines: continue
        
        match_title = lines[0].strip() # Первая строка всегда название матча
        urls = [link.strip() for link in lines[1:] if link.startswith("http")]
        
        with st.expander(f"⚙️ Обработка: {match_title}", expanded=True):
            st.info("🔄 Собираю статистику с сайтов...")
            
            scraped_context = ""
            for url in urls:
                domain = url.split("/")[2]
                st.write(f"Загрузка с {domain}...")
                data_text = scrape_url_data(url)
                scraped_context += f"\n--- Данные с {domain} ---\n{data_text}\n"
            
            st.success(f"✅ Данные собраны. Подключаю ИИ ({selected_model})...")
            
            prompt = f"""
            Ты профессиональный каппер. Сформируй прогноз на матч: "{match_title}".
            Время: {time_str} (Уфа).

            Вот сырые данные статистики и прогрузов, которые мы спарсили для тебя (проанализируй их глубоко, найди тренды по угловым, форме команд и ставкам):
            {scraped_context}

            🚨 ПРАВИЛА:
            1. Избегай шаблонных тоталов > 1.5. Давай разные маркеты!
            2. Опирайся на переданные цифры из статистики.
            
            ВЫДАЙ СТРОГО ПО ШАБЛОНУ:
            ВРЕМЯ_МАТЧА: {time_str}
            РАЗБОР: [3-4 предложения аналитики на основе цифр]
            СТАВКА: [основной выбор]
            ИНДИВИДУАЛЬНЫЙ_ТОТАЛ: [индивидуальный тотал на одну из команд]
            УГЛОВЫЕ: [тотал или фора по угловым]
            МОЙ_ВЫБОР: [твой личный главный выбор по матчу]
            БОЛЕЕ_АГРЕССИВНО: [высокий кэф]
            УВЕРЕННОСТЬ: [от 1 до 5 звезд]
            """
            
            try:
                raw_ans = ask_ai(prompt, selected_model)
                res = parse_block(raw_ans)
                
                # Вывод
                st.markdown("---")
                st.markdown(f"🎯 **Ставка:** `{res.get('СТАВКА', '—')}`")
                st.markdown(f"📈 **Индивидуальный тотал:** `{res.get('ИНДИВИДУАЛЬНЫЙ_ТОТАЛ', '—')}`")
                st.markdown(f"🚩 **Угловые:** `{res.get('УГЛОВЫЕ', '—')}`")
                st.success(f"🔥 **Мой выбор:** `{res.get('МОЙ_ВЫБОР', '—')}`")
                st.markdown(f"⚡ **Агрессивно:** `{res.get('БОЛЕЕ_АГРЕССИВНО', '—')}`")
                st.markdown(f"📋 **Разбор:**\n{res.get('РАЗБОР', '—')}")
                
                # Сохраняем и отправляем в ТГ (код отправки аналогичен предыдущему)
                save_match({"match": match_title, "match_time_ufa": res.get('ВРЕМЯ_МАТЧА', time_str),
                            "bet_main": res.get('СТАВКА'), "ind_total": res.get('ИНДИВИДУАЛЬНЫЙ_ТОТАЛ'),
                            "corners": res.get('УГЛОВЫЕ'), "my_choice": res.get('МОЙ_ВЫБОР'),
                            "bet_aggressive": res.get('БОЛЕЕ_АГРЕССИВНО'), "review": res.get('РАЗБОР'),
                            "confidence": res.get('УВЕРЕННОСТЬ'), "date": now_ufa.strftime("%Y-%m-%d %H:%M")})
            except Exception as e:
                st.error(f"Ошибка ИИ: {e}")
