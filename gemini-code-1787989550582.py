import streamlit as st
from openai import OpenAI
import re
from datetime import datetime, timezone, timedelta
import sqlite3
import requests
import html
from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests
from urllib.parse import quote

st.set_page_config(page_title="Match Analytics AI Pro", page_icon="⚽", layout="wide")

UFA_TZ = timezone(timedelta(hours=5))
now_ufa = datetime.now(UFA_TZ)

st.title("⚽ Автономный AI-Каппер (Hybrid Mode)")
st.caption(f"Время: **{now_ufa.strftime('%d.%m.%Y %H:%M')} (Уфа)** | Авто-поиск + Ручные ссылки + Proxy")

vsegpt_key = st.secrets.get("VSEGPT_API_KEY", "")
tg_token = st.secrets.get("TELEGRAM_BOT_TOKEN", "8758421691:AAFfIvHR1g0ak2QejRqhNrpsy-DRXaHgTFU")
tg_chat_id = st.secrets.get("TELEGRAM_CHAT_ID", "500635733")

google_api_key = st.secrets.get("GOOGLE_API_KEY", "")
google_cx = st.secrets.get("GOOGLE_CX", "")

proxy_ip = st.secrets.get("PROXY_IP", "")
proxy_port = st.secrets.get("PROXY_PORT", "")
proxy_login = st.secrets.get("PROXY_LOGIN", "")
proxy_pass = st.secrets.get("PROXY_PASS", "")

PROXIES = None
if proxy_ip:
    PROXY_URL = f"http://{proxy_login}:{proxy_pass}@{proxy_ip}:{proxy_port}"
    PROXIES = {"http": PROXY_URL, "https": PROXY_URL}

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

def escape_html(text):
    return html.escape(str(text)) if text else ""

def send_telegram_message(text, token, chat_id):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text[:4000], "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=5)
    except:
        pass

def ask_ai(prompt, model):
    client = OpenAI(api_key=vsegpt_key, base_url="https://api.vsegpt.ru/v1")
    res = client.chat.completions.create(
        model=model, messages=[{"role": "user", "content": prompt}],
        temperature=0.5, frequency_penalty=0.7, max_tokens=350
    )
    return res.choices[0].message.content

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

# Фоновый поиск через Google API или прямая генерация альтернативных поисковых урлов
def search_links(match_title):
    links = []
    if google_api_key and google_cx:
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "key": google_api_key,
            "cx": google_cx,
            "q": f"{match_title} статистика прогноз",
            "num": 3
        }
        try:
            res = requests.get(url, params=params, timeout=8)
            if res.status_code == 200:
                data = res.json()
                for item in data.get("items", []):
                    if item.get("link"):
                        links.append(item.get("link"))
        except:
            pass
            
    # Если Google API пустой, подставляем прямые поисковые запросы на Soccer365 и FotMob
    if not links:
        q = quote(match_title.strip())
        links = [
            f"https://soccer365.ru/s/?q={q}",
            f"https://www.fotmob.com/search?q={q}"
        ]
    return links

def scrape_url_data(url):
    if not PROXIES: return None
    try:
        res = cffi_requests.get(url, proxies=PROXIES, impersonate="chrome110", timeout=20)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            text = soup.get_text(separator=' ', strip=True)
            cleaned_text = re.sub(r'\s+', ' ', text).strip()
            return cleaned_text[:3500]
        return None
    except:
        return None

with st.sidebar:
    st.header("⚙️ Настройки AI")
    selected_model = st.selectbox("Модель:", ["google/gemini-2.5-flash-lite", "deepseek/deepseek-chat"], index=0)

st.markdown("### Введи матчи")
st.caption("Формат: название матча, а с новой строки можно указать прямую ссылку на статистику.")

match_input = st.text_area(
    "Поле ввода:", 
    placeholder="Real Madrid - Malaga\nhttps://soccer365.ru/matches/... (необязательно)",
    height=150
)

if st.button("🚀 Собрать статистику и дать прогноз", type="primary"):
    blocks = match_input.strip().split("\n\n")
    time_str = now_ufa.strftime('%d.%m.%Y %H:%M')
    
    for block in blocks:
        lines = [line.strip() for line in block.strip().split("\n") if line.strip()]
        if not lines: 
            continue
            
        match = lines[0]
        manual_urls = [link for link in lines[1:] if link.startswith("http")]
        
        with st.expander(f"⚙️ Обработка: {match}", expanded=True):
            if manual_urls:
                st.info(f"🔗 Использую {len(manual_urls)} ручных ссылок.")
                urls = manual_urls
            else:
                st.info("🔍 Ищу страницы матча...")
                urls = search_links(match)
            
            scraped_context = ""
            st.markdown("### Статус загрузки:")
            
            for url in urls:
                try:
                    domain = url.split('/')[2].replace("www.", "")
                except:
                    domain = "Сайт"
                    
                with st.spinner(f"Тяну данные с {domain}..."):
                    data_text = scrape_url_data(url)
                
                if data_text and len(data_text) > 200:
                    st.success(f"✅ **{domain}** — Успешно загружено")
                    scraped_context += f"\nДанные ({domain}):\n{data_text}\n"
                else:
                    st.error(f"❌ **{domain}** — Ошибка или пустой ответ")
            
            if not scraped_context:
                st.error("❌ Не удалось получить данные. Добавь прямую ссылку на матч с новой строки под названием команд.")
                continue
                
            st.success("🤖 Данные собраны. Генерирую прогноз...")
            
            prompt = f"""
            Ты профессиональный каппер. Прогноз на матч: "{match}". Время: {time_str} (Уфа).
            Сырые данные с сайтов статистики:
            {scraped_context}
            
            ВЫДАЙ СТРОГО ПО ШАБЛОНУ:
            ВРЕМЯ_МАТЧА: {time_str}
            РАЗБОР: [3-4 предложения аналитики на основе цифр]
            СТАВКА: [основной выбор]
            ИНДИВИДУАЛЬНЫЙ_ТОТАЛ: [индивидуальный тотал больше/меньше с точным значением]
            УГЛОВЫЕ: [тотал или фора по угловым]
            МОЙ_ВЫБОР: [твой личный главный выбор по матчу]
            БОЛЕЕ_АГРЕССИВНО: [высокий кэф]
            УВЕРЕННОСТЬ: [от 1 до 5 звезд]
            """
            
            try:
                raw_ans = ask_ai(prompt, selected_model)
                res = parse_block(raw_ans)
                
                st.markdown("---")
                st.markdown(f"🎯 **Ставка:** `{res.get('СТАВКА', '—')}`")
                st.markdown(f"📈 **Индивидуальный тотал:** `{res.get('ИНДИВИДУАЛЬНЫЙ_ТОТАЛ', '—')}`")
                st.markdown(f"🚩 **Угловые:** `{res.get('УГЛОВЫЕ', '—')}`")
                st.success(f"🔥 **Мой выбор:** `{res.get('МОЙ_ВЫБОР', '—')}`")
                st.markdown(f"⚡ **Агрессивно:** `{res.get('БОЛЕЕ_АГРЕССИВНО', '—')}`")
                st.markdown(f"📋 **Разбор:**\n{res.get('РАЗБОР', '—')}")
                
                tg_text = (
                    f"⚽ <b>{escape_html(match)}</b>\n"
                    f"🕒 <b>Время (Уфа):</b> <code>{escape_html(res.get('ВРЕМЯ_МАТЧА', time_str))}</code>\n\n"
                    f"🎯 <b>Ставка:</b> <code>{escape_html(res.get('СТАВКА', '—'))}</code>\n"
                    f"📈 <b>ИТ:</b> <code>{escape_html(res.get('ИНДИВИДУАЛЬНЫЙ_ТОТАЛ', '—'))}</code>\n"
                    f"🚩 <b>Угловые:</b> <code>{escape_html(res.get('УГЛОВЫЕ', '—'))}</code>\n"
                    f"🔥 <b>Мой выбор:</b> <code>{escape_html(res.get('МОЙ_ВЫБОР', '—'))}</code>\n"
                    f"⚡ <b>Агрессивно:</b> <code>{escape_html(res.get('БОЛЕЕ_АГРЕССИВНО', '—'))}</code>\n"
                    f"⭐ <b>Уверенность:</b> {res.get('УВЕРЕННОСТЬ', '—')}\n\n"
                    f"📝 <b>Разбор:</b>\n{escape_html(res.get('РАЗБОР', '—'))}"
                )
                send_telegram_message(tg_text, tg_token, tg_chat_id)
                
                save_match({
                    "match": match, "match_time_ufa": res.get('ВРЕМЯ_МАТЧА', time_str),
                    "bet_main": res.get('СТАВКА'), "ind_total": res.get('ИНДИВИДУАЛЬНЫЙ_ТОТАЛ'),
                    "corners": res.get('УГЛОВЫЕ'), "my_choice": res.get('МОЙ_ВЫБОР'),
                    "bet_aggressive": res.get('БОЛЕЕ_АГРЕССИВНО'), "review": res.get('РАЗБОР'),
                    "confidence": res.get('УВЕРЕННОСТЬ'), "date": now_ufa.strftime("%Y-%m-%d %H:%M")
                })
            except Exception as e:
                st.error(f"Ошибка генерации прогноза: {e}")
