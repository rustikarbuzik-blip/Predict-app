import streamlit as st
from openai import OpenAI
import re
from datetime import datetime, timezone, timedelta
import sqlite3
from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests
from duckduckgo_search import DDGS

st.set_page_config(page_title="Match Analytics AI Pro", page_icon="⚽", layout="wide")

# Время по Уфе (UTC+5)
UFA_TZ = timezone(timedelta(hours=5))
now_ufa = datetime.now(UFA_TZ)

st.title("⚽ Автономный AI-Каппер (5 Источников)")
st.caption(f"Время: **{now_ufa.strftime('%d.%m.%Y %H:%M')} (Уфа)** | Авто-поиск + Proxy")

vsegpt_key = st.secrets.get("VSEGPT_API_KEY", "")

proxy_ip = st.secrets.get("PROXY_IP", "")
proxy_port = st.secrets.get("PROXY_PORT", "")
proxy_login = st.secrets.get("PROXY_LOGIN", "")
proxy_pass = st.secrets.get("PROXY_PASS", "")

PROXIES = None
if proxy_ip:
    PROXY_URL = f"http://{proxy_login}:{proxy_pass}@{proxy_ip}:{proxy_port}"
    PROXIES = {"http": PROXY_URL, "https": PROXY_URL}

def search_links(match_title):
    sites = ["fotmob.com", "nb-bet.com", "arbworld.net", "footystats.org", "corner-stats.com"]
    found_links = []
    with DDGS() as ddgs:
        for site in sites:
            try:
                results = list(ddgs.text(f"{match_title} site:{site}", max_results=1))
                if results:
                    found_links.append(results[0]['href'])
            except:
                pass
    return found_links

def scrape_url_data(url):
    if not PROXIES: return None
    try:
        # Ставим таймаут 20 секунд, чтобы скрипт не зависал слишком долго на одном сайте
        res = cffi_requests.get(url, proxies=PROXIES, impersonate="chrome110", timeout=20)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            text = soup.get_text(separator=' ', strip=True)
            cleaned_text = re.sub(r'\s+', ' ', text).strip()
            return cleaned_text[:3500]
        return None
    except:
        return None

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

with st.sidebar:
    selected_model = st.selectbox("Модель:", ["google/gemini-2.5-flash-lite", "deepseek/deepseek-chat"], index=0)

match_input = st.text_area("Введи матчи (каждый с новой строки):", placeholder="Арсенал - Челси\nСпартак - Зенит")

if st.button("🚀 Найти статистику и дать прогноз", type="primary"):
    matches = [m.strip() for m in match_input.strip().split("\n") if m.strip()]
    time_str = now_ufa.strftime('%d.%m.%Y %H:%M')
    
    for match in matches:
        with st.expander(f"⚙️ Обработка: {match}", expanded=True):
            st.info("🔍 Ищу ссылки на статистику на 5 сайтах...")
            urls = search_links(match)
            
            if not urls:
                st.warning("Не удалось найти ссылки для этого матча.")
                continue
                
            scraped_context = ""
            
            st.markdown("### Статус загрузки:")
            for url in urls:
                domain = url.split('/')[2].replace("www.", "")
                
                with st.spinner(f"Тяну данные с {domain}..."):
                    data_text = scrape_url_data(url)
                
                if data_text:
                    st.success(f"✅ **{domain}** — Успешно загружено")
                    scraped_context += f"\nДанные ({domain}):\n{data_text}\n"
                else:
                    st.error(f"❌ **{domain}** — Ошибка (блокировка или таймаут)")
            
            if not scraped_context:
                st.error("❌ Ни один сайт не отдал данные. ИИ не сможет сделать качественный прогноз.")
                continue
                
            st.success("🤖 Данные собраны. Генерирую прогноз...")
            
            prompt = f"""
            Ты профессиональный каппер. Прогноз на матч: "{match}". Время: {time_str} (Уфа).
            Сырые данные (найди тренды по угловым, форме команд и ставкам):
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
            except Exception as e:
                st.error(f"Ошибка: {e}")
