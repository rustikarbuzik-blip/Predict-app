import streamlit as st
from openai import OpenAI
import requests
import html
from datetime import datetime, timezone, timedelta
import sqlite3

# Импорт парсеров (если используются локально)
try:
    from parsers import (
        get_arbworld_moneyway,
        get_corner_stats_data,
        get_footystats_data,
        get_fbref_data,
        get_oddsportal_dropping_odds
    )
except ImportError:
    def get_arbworld_moneyway(m): return ""
    def get_corner_stats_data(m): return ""
    def get_footystats_data(m): return ""
    def get_fbref_data(m): return ""
    def get_oddsportal_dropping_odds(m): return ""

st.set_page_config(
    page_title="Match Analytics AI Pro (Live Web)", 
    page_icon="⚽", 
    layout="wide"
)

# Время по Уфе (UTC+5 / MSK+2)
UFA_TZ = timezone(timedelta(hours=5))
now_ufa = datetime.now(UFA_TZ)

st.title("⚽ Аналитический центр спортивных матчей (Live Web AI 🕒)")
st.caption(f"Время генерации: **{now_ufa.strftime('%d.%m.%Y %H:%M')} (Уфа, UTC+5)** | Агрегатор + Live Web Search + SQLite")

# Ключи и настройки Telegram
vsegpt_key = st.secrets.get("VSEGPT_API_KEY", "")
default_tg_token = "8758421691:AAFfIvHR1g0ak2QejRqhNrpsy-DRXaHgTFU"
default_tg_chat_id = "500635733"
tg_token = st.secrets.get("TELEGRAM_BOT_TOKEN", default_tg_token)
tg_chat_id = st.secrets.get("TELEGRAM_CHAT_ID", default_tg_chat_id)

def escape_html(text):
    if not text:
        return ""
    return html.escape(str(text))

# ==============================================================================
# 🗄️ БАЗА ДАННЫХ SQLITE
# ==============================================================================

def init_db():
    conn = sqlite3.connect("match_history.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match TEXT,
            match_time_ufa TEXT,
            pick TEXT,
            total TEXT,
            ind_total TEXT,
            corners TEXT,
            my_pick TEXT,
            confidence TEXT,
            weather TEXT,
            review TEXT,
            message_id INTEGER,
            overall_status TEXT,
            status_pick TEXT,
            status_total TEXT,
            status_ind_total TEXT,
            status_corners TEXT,
            status_my_pick TEXT,
            date TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def load_history():
    conn = sqlite3.connect("match_history.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT match, match_time_ufa, pick, total, ind_total, corners, my_pick, confidence, weather, review, message_id, overall_status, status_pick, status_total, status_ind_total, status_corners, status_my_pick, date FROM history")
    rows = cursor.fetchall()
    conn.close()
    
    history = []
    for row in rows:
        history.append({
            "match": row[0], "match_time_ufa": row[1] if row[1] else "—",
            "pick": row[2], "total": row[3], "ind_total": row[4] if row[4] else "—",
            "corners": row[5], "my_pick": row[6] if row[6] else "—",
            "confidence": row[7], "weather": row[8], "review": row[9],
            "message_id": int(row[10]) if row[10] else 0, "overall_status": row[11],
            "status_pick": row[12], "status_total": row[13], "status_ind_total": row[14] if row[14] else "⏳",
            "status_corners": row[15], "status_my_pick": row[16] if row[16] else "⏳", "date": row[17]
        })
    return history

def save_match_to_db(item):
    conn = sqlite3.connect("match_history.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO history (match, match_time_ufa, pick, total, ind_total, corners, my_pick, confidence, weather, review, message_id, overall_status, status_pick, status_total, status_ind_total, status_corners, status_my_pick, date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        item.get("match"), item.get("match_time_ufa", "—"),
        item.get("pick"), item.get("total"), item.get("ind_total", "—"), item.get("corners"),
        item.get("my_pick", "—"), item.get("confidence"), item.get("weather"), item.get("review"), item.get("message_id"),
        item.get("overall_status", "⏳ Ожидание"), item.get("status_pick", "⏳"),
        item.get("status_total", "⏳"), item.get("status_ind_total", "⏳"),
        item.get("status_corners", "⏳"), item.get("status_my_pick", "⏳"), item.get("date")
    ))
    conn.commit()
    conn.close()

def update_history_in_db(history_data):
    conn = sqlite3.connect("match_history.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM history")
    for item in history_data:
        cursor.execute('''
            INSERT INTO history (match, match_time_ufa, pick, total, ind_total, corners, my_pick, confidence, weather, review, message_id, overall_status, status_pick, status_total, status_ind_total, status_corners, status_my_pick, date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            item.get("match"), item.get("match_time_ufa", "—"),
            item.get("pick"), item.get("total"), item.get("ind_total", "—"), item.get("corners"),
            item.get("my_pick", "—"), item.get("confidence"), item.get("weather"), item.get("review"), item.get("message_id"),
            item.get("overall_status"), item.get("status_pick"), item.get("status_total"),
            item.get("status_ind_total", "⏳"), item.get("status_corners"),
            item.get("status_my_pick", "⏳"), item.get("date")
        ))
    conn.commit()
    conn.close()

# ==============================================================================
# ⚙️ БОКОВОЕ МЕНЮ
# ==============================================================================

with st.sidebar:
    st.header("⚙️ Настройки AI & Web-поиска")
    input_vsegpt_key = st.text_input(
        "VseGPT API Key:", 
        value=vsegpt_key, 
        type="password"
    )
    
    selected_model = st.selectbox(
        "Модель нейросети:",
        options=[
            "perplexity/sonar",             # 🔥 Прямой онлайн-поиск статистики
            "perplexity/sonar-reasoning",   # 🔥 Глубокий расчет с веб-поиском
            "google/gemini-2.5-flash",      # Быстрая базовая модель
            "openai/gpt-4o-mini",            # Модель OpenAI
            "google/gemini-2.5-flash-lite"  # Эконом вариант
        ],
        index=0
    )
    
    if "sonar" in selected_model:
        st.info("🌐 Включен прямой поиск статистики через Perplexity Sonar (FootyStats, Oddsportal, Flashscore).")
    
    if input_vsegpt_key:
        st.success("🟢 VseGPT подключен!")
    else:
        st.warning("⚠️ Введите API ключ VseGPT")

    st.markdown("---")
    st.header("🤖 Telegram Бот")
    input_tg_token = st.text_input("Bot Token:", value=tg_token, type="password")
    input_tg_chat_id = st.text_input("Chat ID:", value=tg_chat_id)

tab1, tab2 = st.tabs(["📝 Ввод матчей и анализ", "📋 История и результаты"])

# ==============================================================================
# 🧠 ОБРАЩЕНИЕ К VSEGPT
# ==============================================================================

def ask_vsegpt(prompt):
    if not input_vsegpt_key:
        raise Exception("API ключ VseGPT не указан!")

    client = OpenAI(
        api_key=input_vsegpt_key,
        base_url="https://api.vsegpt.ru/v1"
    )

    response = client.chat.completions.create(
        model=selected_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=450
    )
    return response.choices[0].message.content

def parse_match_block(block_text):
    data = {}
    lines = block_text.split('\n')
    current_key = None
    
    for line in lines:
        if ':' in line:
            parts = line.split(':', 1)
            candidate_key = parts[0].strip().upper()
            if candidate_key in [
                'ВРЕМЯ_МАТЧА', 'ИСХОД', 'ТОТАЛ', 'ИНДИВИДУАЛЬНЫЙ_ТОТАЛ', 
                'УГЛОВЫЕ', 'МОЙ_ВЫБОР', 'УВЕРЕННОСТЬ', 'ПОГОДА_ПОЛЕ', 'РАЗБОР'
            ]:
                current_key = candidate_key
                data[current_key] = parts[1].strip()
                continue
        if current_key == 'РАЗБОР' and line.strip():
            data[current_key] += "\n" + line.strip()
            
    return data

# ==============================================================================
# 📨 TELEGRAM API
# ==============================================================================

def send_telegram_message(text, token, chat_id):
    if not token or not chat_id:
        return False, "Не заполнены настройки Telegram.", None
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    safe_text = text[:4000] if len(text) > 4000 else text
    payload = {"chat_id": chat_id, "text": safe_text, "parse_mode": "HTML"}
    try:
        res = requests.post(url, json=payload, timeout=5)
        if res.status_code == 200:
            return True, "Успешно", res.json()["result"]["message_id"]
        return False, res.text, None
    except Exception as e:
        return False, str(e), None

def edit_telegram_message_full(token, chat_id, message_id, new_text):
    if not token or not chat_id or not message_id:
        return False
    url = f"https://api.telegram.org/bot{token}/editMessageText"
    safe_text = new_text[:4000] if len(new_text) > 4000 else new_text
    payload = {"chat_id": chat_id, "message_id": message_id, "text": safe_text, "parse_mode": "HTML"}
    try:
        res = requests.post(url, json=payload, timeout=5)
        return res.status_code == 200
    except:
        return False

# ==============================================================================
# 📋 ВКЛАДКА 1: АНАЛИЗ МАТЧЕЙ
# ==============================================================================

with tab1:
    match_input = st.text_area(
        "Введите список матчей (каждый матч с новой строки):", 
        placeholder="Лорьян - Труа\nЛион - Гавр\nБрест - Тулуза\nАвеллино - Виченца",
        height=150
    )
    
    if st.button("🚀 Сформировать прогнозы и Экспресс дня", type="primary", use_container_width=True):
        matches_list = [m.strip() for m in match_input.strip().split("\n") if m.strip()] if match_input.strip() else []
        
        if not input_vsegpt_key:
            st.error("Укажите VseGPT API Key в боковом меню!")
        elif not matches_list:
            st.warning("Введите хотя бы один матч в текстовое поле!")
        else:
            current_time_str = now_ufa.strftime('%d.%m.%Y %H:%M')
            st.success(f"Анализ **{len(matches_list)}** матчей (Время генерации: {current_time_str} по Уфе)")
            accumulated_express_items = []

            for i, match in enumerate(matches_list, 1):
                with st.spinner(f"Анализ матча {i}/{len(matches_list)} ({match})..."):
                    raw_arb = get_arbworld_moneyway(match)
                    raw_corn = get_corner_stats_data(match)
                    raw_footy = get_footystats_data(match)
                    raw_fbref = get_fbref_data(match)
                    raw_odds = get_oddsportal_dropping_odds(match)

                    real_arbworld = str(raw_arb)[:200] if raw_arb else "Поиск в Live Web"
                    real_corners = str(raw_corn)[:200] if raw_corn else "Поиск в Live Web"
                    real_footystats = str(raw_footy)[:200] if raw_footy else "Поиск в Live Web"
                    real_fbref = str(raw_fbref)[:200] if raw_fbref else "Поиск в Live Web"
                    real_oddsportal = str(raw_odds)[:200] if raw_odds else "Поиск в Live Web"

                    analysis_prompt = f"""
                    Найди актуальные спортивные данные в интернете и проведи глубокий анализ матча: "{match}".
                    Время запроса: {current_time_str} (Уфа, UTC+5).

                    ВХОДНЫЕ ДАННЫЕ (если пусты — найди в сети FootyStats / Flashscore / CornerStats):
                    - Arbworld (деньги): {real_arbworld}
                    - Corner Stats (угловые): {real_corners}
                    - FootyStats (xG/форма): {real_footystats}
                    - Oddsportal (кэфы): {real_oddsportal}

                    СТРОГИЕ ПРАВИЛА МАТЕМАТИЧЕСКОГО РАСЧЕТА:
                    1. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО выдавать шаблонные «П1, ТБ 2.5, ИТБ1 1.5, УГЛ ТБ 9.5» на все матчи подряд.
                    2. Вычисли реальный xG и форму обеих команд:
                       - Если играют оборонительные/низовые клубы или сумма xG < 2.3 — СТРОГО выбирай ТМ 2.5 / ТМ 2.0, ИТМ1 / ИТМ2 1.0.
                       - Если фаворит играет на выезде — ставь П2, Х2, Ф2(0) или ИТБ2.
                       - Угловые: проверь среднюю статистику команд. Если средний тотал угловых < 9.5 — СТРОГО ставь УГЛ ТМ 8.5 или УГЛ ТМ 9.5.
                    3. В блоке РАЗБОР напиши конкретные реальные цифры (фактический средний тотал, xG или положение в таблице).

                    ФОРМАТ ОТВЕТА СТРОГО:
                    ВРЕМЯ_МАТЧА: [Дата и время начала по Уфе (UTC+5)]
                    ИСХОД: [П1, П2, Х, 1Х, Х2, Ф1(...), Ф2(...)]
                    ТОТАЛ: [ТМ 2.0, ТМ 2.5, ТМ 3.0, ТБ 2.5 или ТБ 3.0]
                    ИНДИВИДУАЛЬНЫЙ_ТОТАЛ: [ИТМ1 1.0, ИТМ2 1.0, ИТМ1 1.5, ИТБ2 1.0 или ИТБ1 1.5]
                    УГЛОВЫЕ: [УГЛ ТМ 8.5, УГЛ ТМ 9.5, УГЛ ТБ 9.5 или УГЛ Ф2(+1.5)]
                    МОЙ_ВЫБОР: [Главная валуйная ставка]
                    УВЕРЕННОСТЬ: [Оценка 6-10]
                    ПОГОДА_ПОЛЕ: [Кратко]
                    РАЗБОР: [3 коротких тезиса с реальными цифрами команд]
                    """

                    try:
                        raw_response = ask_vsegpt(analysis_prompt)
                        parsed_data = parse_match_block(raw_response)

                        match_time_ufa = parsed_data.get('ВРЕМЯ_МАТЧА', 'Предстоящий матч')
                        confidence_str = parsed_data.get('УВЕРЕННОСТЬ', '7.5/10')
                        pick_val = parsed_data.get('ИСХОД', '—')
                        total_val = parsed_data.get('ТОТАЛ', '—')
                        ind_total_val = parsed_data.get('ИНДИВИДУАЛЬНЫЙ_ТОТАЛ', '—')
                        corners_val = parsed_data.get('УГЛОВЫЕ', '—')
                        my_pick_val = parsed_data.get('МОЙ_ВЫБОР', pick_val)
                        weather_val = parsed_data.get('ПОГОДА_ПОЛЕ', '—')
                        review_val = parsed_data.get('РАЗБОР', 'Анализ завершен.')
                        
                        conf_numeric = 0.0
                        try:
                            conf_numeric = float(confidence_str.replace('/10', '').replace(',', '.').strip())
                        except:
                            conf_numeric = 7.5

                        if conf_numeric >= 9.5:
                            accumulated_express_items.append({
                                "match": match,
                                "time": match_time_ufa,
                                "pick": my_pick_val,
                                "confidence": confidence_str
                            })

                        with st.expander(f"⚽ {i}. {match} | 🕒 {match_time_ufa}", expanded=(i == 1)):
                            st.caption(f"🕒 **Начало:** {match_time_ufa}")
                            col1, col2, col3, col4, col5 = st.columns(5)
                            col1.metric("Исход / Фора", pick_val)
                            col2.metric("Общий тотал", total_val)
                            col3.metric("Индив. тотал", ind_total_val)
                            col4.metric("Угловые", corners_val)
                            col5.metric("Уверенность", confidence_str)

                            st.success(f"🎯 **МОЙ ВЫБОР (Основная ставка):** `{my_pick_val}`")
                            st.info(f"🏟️ **Погода и поле:** {weather_val}")
                            st.markdown(f"**📋 Разбор метрик:**\n\n{review_val}")
                            
                            # 🔍 Диагностика входящих данных
                            with st.expander("🔍 Сырые данные парсеров для проверки"):
                                st.text(f"Arbworld: {real_arbworld}")
                                st.text(f"Corners: {real_corners}")
                                st.text(f"FootyStats: {real_footystats}")
                                st.text(f"Oddsportal: {real_oddsportal}")

                        tg_message_text = (
                            f"⚽ <b>Прогноз на матч: {escape_html(match)}</b>\n"
                            f"🕒 <b>Начало:</b> <code>{escape_html(match_time_ufa)}</code>\n\n"
                            f"🎯 <b>Исход/Фора:</b> <code>{escape_html(pick_val)}</code> [⏳]\n"
                            f"📈 <b>Общий тотал:</b> <code>{escape_html(total_val)}</code> [⏳]\n"
                            f"⚽ <b>Инд. тотал:</b> <code>{escape_html(ind_total_val)}</code> [⏳]\n"
                            f"🚩 <b>Угловые:</b> <code>{escape_html(corners_val)}</code> [⏳]\n"
                            f"🔥 <b>МОЙ ВЫБОР:</b> <code>{escape_html(my_pick_val)}</code> [⏳]\n"
                            f"⭐ <b>Уверенность:</b> <code>{escape_html(confidence_str)}</code>\n"
                            f"🏟️ <b>Погода/Поле:</b> {escape_html(weather_val)}\n\n"
                            f"📝 <b>Разбор метрик:</b>\n{escape_html(review_val)}"
                        )

                        success, msg, msg_id = send_telegram_message(tg_message_text, input_tg_token, input_tg_chat_id)
                        if success and msg_id:
                            st.toast(f"📤 Прогноз отправлен в Telegram!", icon="✅")
                            match_item = {
                                "match": match, "match_time_ufa": match_time_ufa,
                                "pick": pick_val, "total": total_val, "ind_total": ind_total_val,
                                "corners": corners_val, "my_pick": my_pick_val,
                                "confidence": confidence_str, "weather": weather_val, "review": review_val,
                                "message_id": msg_id, "overall_status": "⏳ Ожидание",
                                "status_pick": "⏳", "status_total": "⏳", "status_ind_total": "⏳",
                                "status_corners": "⏳", "status_my_pick": "⏳",
                                "date": datetime.now().strftime("%Y-%m-%d %H:%M")
                            }
                            save_match_to_db(match_item)
                        else:
                            st.error(f"Ошибка Telegram: {msg}")

                    except Exception as e:
                        st.error(f"🔴 Ошибка анализа {match}: {e}")

            if len(accumulated_express_items) >= 1:
                with st.spinner("Формирование ТОП-Экспресса..."):
                    express_lines = []
                    approx_total_odds = round(1.75 ** len(accumulated_express_items), 2)

                    for idx, item in enumerate(accumulated_express_items, 1):
                        express_lines.append(f"{idx}. <b>{escape_html(item['match'])}</b> (🕒 <code>{escape_html(item['time'])}</code>) — Выбор: <code>{escape_html(item['pick'])}</code> (⭐ {escape_html(item['confidence'])})")

                    express_text = (
                        f"🔥 <b>ТОП-ЭКСПРЕСС ДНЯ (9.5+ / 10)</b> 🔥\n\n"
                        + "\n".join(express_lines) +
                        f"\n\n📊 <b>Примерный итоговый коэффициент:</b> <code>~{approx_total_odds}</code>\n"
                        f"💡 <b>Статус:</b> Отобраны по коэффициенту уверенности."
                    )

                    send_telegram_message(express_text, input_tg_token, input_tg_chat_id)
                    st.success("🔥 ТОП-Экспресс дня отправлен в Telegram!")
            else:
                st.info("ℹ️ Нет матчей с уверенностью 9.5+/10 для Экспресса дня.")

# ==============================================================================
# 📊 ВКЛАДКА 2: ИСТОРИЯ
# ==============================================================================

with tab2:
    st.subheader("📊 История прогнозов (База данных)")
    history = load_history()
    
    if not history:
        st.info("История пуста. Сформируйте прогнозы.")
    else:
        if st.button("🔄 Проверить результаты по каждому маркету"):
            with st.spinner("Проверяем фактические итоги матчей..."):
                updated_count = 0
                
                for item in history:
                    if item.get("overall_status") != "⏳ Ожидание":
                        continue
                    
                    match_name = item["match"]
                    match_time_ufa = item.get("match_time_ufa", "—")
                    pick = item["pick"]
                    total_pick = item["total"]
                    ind_total_pick = item.get("ind_total", "—")
                    corners_pick = item["corners"]
                    my_pick_val = item.get("my_pick", "—")
                    msg_id = item["message_id"]
                    
                    check_prompt = f"""
                    Проверь результат матча: "{match_name}".
                    Маркеты для проверки:
                    - Исход: {pick}
                    - Общий тотал: {total_pick}
                    - Индив тотал: {ind_total_pick}
                    - Угловые: {corners_pick}
                    - Мой выбор: {my_pick_val}

                    Ответь СТРОГО:
                    ИСХОД: [WIN/LOSS]
                    ТОТАЛ: [WIN/LOSS]
                    ИНДИВИДУАЛЬНЫЙ_ТОТАЛ: [WIN/LOSS]
                    УГЛОВЫЕ: [WIN/LOSS]
                    МОЙ_ВЫБОР: [WIN/LOSS]
                    (Если идет или не начался, напиши PENDING)
                    """
                    try:
                        res = ask_vsegpt(check_prompt).upper()
                        
                        if "PENDING" in res:
                            continue

                        item["status_pick"] = "✅" if "ИСХОД: WIN" in res or "WIN" in res.split("ИСХОД")[-1].split("\n")[0] else "❌"
                        item["status_total"] = "✅" if "ТОТАЛ: WIN" in res else "❌"
                        item["status_ind_total"] = "✅" if "ИНДИВИДУАЛЬНЫЙ_ТОТАЛ: WIN" in res else "❌"
                        item["status_corners"] = "✅" if "УГЛОВЫЕ: WIN" in res else "❌"
                        item["status_my_pick"] = "✅" if "МОЙ_ВЫБОР: WIN" in res else "❌"
                        item["overall_status"] = "🎯 Завершено"

                        updated_msg_text = (
                            f"⚽ <b>Прогноз на матч: {escape_html(match_name)}</b>\n"
                            f"🕒 <b>Начало:</b> <code>{escape_html(match_time_ufa)}</code>\n\n"
                            f"🎯 <b>Исход/Фора:</b> <code>{escape_html(pick)}</code> [{item['status_pick']}]\n"
                            f"📈 <b>Общий тотал:</b> <code>{escape_html(total_pick)}</code> [{item['status_total']}]\n"
                            f"⚽ <b>Инд. тотал:</b> <code>{escape_html(ind_total_pick)}</code> [{item['status_ind_total']}]\n"
                            f"🚩 <b>Угловые:</b> <code>{escape_html(corners_pick)}</code> [{item['status_corners']}]\n"
                            f"🔥 <b>МОЙ ВЫБОР:</b> <code>{escape_html(my_pick_val)}</code> [{item['status_my_pick']}]\n"
                            f"⭐ <b>Уверенность:</b> <code>{escape_html(item['confidence'])}</code>\n"
                            f"🏟️ <b>Погода/Поле:</b> {escape_html(item['weather'])}\n\n"
                            f"📝 <b>Разбор метрик:</b>\n{escape_html(item['review'])}"
                        )
                        
                        edit_telegram_message_full(input_tg_token, input_tg_chat_id, msg_id, updated_msg_text)
                        updated_count += 1
                    except Exception as e:
                        continue
                
                update_history_in_db(history)
                st.success(f"Готово! Обновлено матчей: {updated_count}")
        
        for idx, h_item in enumerate(reversed(history), 1):
            with st.expander(f"{h_item['overall_status']} | {h_item['match']} (🕒 {h_item.get('match_time_ufa', '—')})"):
                st.write(f"**Время начала:** {h_item.get('match_time_ufa', '—')}")
                st.write(f"**Исход:** {h_item['pick']} [{h_item.get('status_pick', '⏳')}]")
                st.write(f"**Общий тотал:** {h_item['total']} [{h_item.get('status_total', '⏳')}]")
                st.write(f"**Индивидуальный тотал:** {h_item.get('ind_total', '—')} [{h_item.get('status_ind_total', '⏳')}]")
                st.write(f"**Угловые:** {h_item['corners']} [{h_item.get('status_corners', '⏳')}]")
                st.write(f"**🔥 Мой выбор:** {h_item.get('my_pick', '—')} [{h_item.get('status_my_pick', '⏳')}]")
                st.markdown(f"**Разбор:**\n\n{h_item['review']}")
