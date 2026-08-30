import streamlit as st
from openai import OpenAI
import re
from datetime import datetime, timezone, timedelta
import sqlite3
import requests
import html
from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

st.set_page_config(page_title="Match Analytics AI Pro", page_icon="⚽", layout="wide")

UFA_TZ = timezone(timedelta(hours=5))
now_ufa = datetime.now(UFA_TZ)

st.title("⚽ Автономный AI-Каппер (Multi-Source Search)")
st.caption(f"Время: **{now_ufa.strftime('%d.%m.%Y %H:%M')} (Уфа)** | FotMob + NB-Bet + Soccer365 + Proxy")

vsegpt_key = st.secrets.get("VSEGPT_API_KEY", "")
tg_token = st.secrets.get("TELEGRAM_BOT_TOKEN", "8758421691:AAFfIvHR1g0ak2QejRqhNrpsy-DRXaHgTFU")
tg_chat_id = st.secrets.get("TELEGRAM_CHAT_ID", "500635733")

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

# Умный поиск по ключевым спорт-порталам (FotMob, NB-Bet, Soccer365)
def search_links(match_title):
    found_links = []
    # Ищем упоминания матча в связке с нужными доменами через DuckDuckGo
    queries = [
        f"{match_title} site:soccer365.ru",
        f"{match_title} site:nb-bet.com",
        f"{match_title} site:fotmob.com",
        f"{match_title} статистика прогноз"
    ]
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    for q in queries:
        search_url = f"https://html.duckduckgo.com/html/?q={q}"
        try:
            res = cffi_requests.get(search_url, headers=headers, proxies=PROXIES, impersonate="chrome110", timeout=8)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                for a in soup.find_all('a', class_='result__url'):
                    href = a.get('href')
                    if href and 'http' in href and href not in found_links:
                        # Отбираем ссылки с целевых ресурсов или общие спортивные
                        if any(domain in href for domain in ['soccer365', 'nb-bet', 'fotmob', 'footystats', 'flashscore']):
                            found_links.append(href)
                            if len(found_links) >= 4:
                                break
        except:
            continue
            
        if len(found_links) >= 4:
            break
            
    return found_links

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
st.caption("Формат: просто название матча (например: Real Madrid - Malaga).")

match_input = st.text_area(
    "Поле ввода:", 
    placeholder="Real Madrid - Malaga\nSpartak - Zenit",
    height=150
)

if st.button("🚀 Найти статистику и дать прогноз", type="primary"):
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
                st.info(f"🔗 Найдено {len(manual_urls)} ручных ссылок. Пропускаю авто-поиск.")
                urls = manual_urls
            else:
                st.info("🔍 Ищу ссылки на FotMob, NB-Bet и Soccer365...")
                urls = search_links(match)
            
            if not urls:
                st.warning("⚠️ Не удалось найти ссылки автоматически. Попробуй указать ссылку вручную с новой строки.")
                continue
                
            scraped_context = ""
            st.markdown("### Статус загрузки:")
            
            for url in urls:
                try:
                    domain = url.split('/')[2].replace("www.", "")
                except:
                    domain = "Неизвестный сайт"
                    
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
                
            st.success("🤖 Данные собраны со всех источников. Генерирую прогноз...")
            
            prompt = f"""
            Ты профессиональный каппер. Прогноз на матч: "{match}". Время: {time_str} (Уфа).
            Сырые данные с FotMob, NB-Bet, Soccer365 и других платформ (найди тренды по угловым, форме команд и ставкам):
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
