import streamlit as st
from openai import OpenAI
import requests
import html
from datetime import datetime, timezone, timedelta
import sqlite3

# Импорт парсеров
try:
    from parsers import (
        get_arbworld_moneyway,
        get_corner_stats_data,
        get_footystats_data,
        get_fbref_data,
        get_oddsportal_dropping_odds
    )
except ImportError:
    def get_arbworld_moneyway(m): return None
    def get_corner_stats_data(m): return None
    def get_footystats_data(m): return None
    def get_fbref_data(m): return None
    def get_oddsportal_dropping_odds(m): return None

st.set_page_config(
    page_title="Match Analytics AI Pro", 
    page_icon="⚽", 
    layout="wide"
)

# Время по Уфе (UTC+5 / MSK+2)
UFA_TZ = timezone(timedelta(hours=5))
now_ufa = datetime.now(UFA_TZ)

st.title("⚽ Аналитический центр спортивных матчей (Smart Synthesis 🕒)")
st.caption(f"Время генерации: **{now_ufa.strftime('%d.%m.%Y %H:%M')} (Уфа, UTC+5)** | Multi-Source Matrix + SQLite")

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
        CREATE TABLE IF NOT EXISTS history_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match TEXT,
            match_time_ufa TEXT,
            bet_main TEXT,
            ind_total TEXT,
            bet_aggressive TEXT,
            bet_cautious TEXT,
            best_pick TEXT,
            confidence TEXT,
            review TEXT,
            message_id INTEGER,
            overall_status TEXT,
            status_main TEXT,
            status_ind_total TEXT,
            status_aggressive TEXT,
            status_cautious TEXT,
            status_best_pick TEXT,
            date TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def load_history():
    conn = sqlite3.connect("match_history.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT match, match_time_ufa, bet_main, ind_total, bet_aggressive, bet_cautious, best_pick, confidence, review, message_id, overall_status, status_main, status_ind_total, status_aggressive, status_cautious, status_best_pick, date FROM history_v2")
    rows = cursor.fetchall()
    conn.close()
    
    history = []
    for row in rows:
        history.append({
            "match": row[0], "match_time_ufa": row[1] if row[1] else "—",
            "bet_main": row[2], "ind_total": row[3] if row[3] else "—",
            "bet_aggressive": row[4], "bet_cautious": row[5],
            "best_pick": row[6] if row[6] else "—",
            "confidence": row[7], "review": row[8],
            "message_id": int(row[9]) if row[9] else 0, "overall_status": row[10],
            "status_main": row[11], "status_ind_total": row[12],
            "status_aggressive": row[13], "status_cautious": row[14],
            "status_best_pick": row[15], "date": row[16]
        })
    return history

def save_match_to_db(item):
    conn = sqlite3.connect("match_history.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO history_v2 (match, match_time_ufa, bet_main, ind_total, bet_aggressive, bet_cautious, best_pick, confidence, review, message_id, overall_status, status_main, status_ind_total, status_aggressive, status_cautious, status_best_pick, date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        item.get("match"), item.get("match_time_ufa", "—"),
        item.get("bet_main"), item.get("ind_total", "—"), item.get("bet_aggressive"),
        item.get("bet_cautious"), item.get("best_pick", "—"), item.get("confidence"),
        item.get("review"), item.get("message_id"),
        item.get("overall_status", "⏳ Ожидание"), item.get("status_main", "⏳"),
        item.get("status_ind_total", "⏳"), item.get("status_aggressive", "⏳"),
        item.get("status_cautious", "⏳"), item.get("status_best_pick", "⏳"), item.get("date")
    ))
    conn.commit()
    conn.close()

def update_history_in_db(history_data):
    conn = sqlite3.connect("match_history.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM history_v2")
    for item in history_data:
        cursor.execute('''
            INSERT INTO history_v2 (match, match_time_ufa, bet_main, ind_total, bet_aggressive, bet_cautious, best_pick, confidence, review, message_id, overall_status, status_main, status_ind_total, status_aggressive, status_cautious, status_best_pick, date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            item.get("match"), item.get("match_time_ufa", "—"),
            item.get("bet_main"), item.get("ind_total", "—"), item.get("bet_aggressive"),
            item.get("bet_cautious"), item.get("best_pick", "—"), item.get("confidence"),
            item.get("review"), item.get("message_id"),
            item.get("overall_status"), item.get("status_main"), item.get("status_ind_total"),
            item.get("status_aggressive"), item.get("status_cautious"),
            item.get("status_best_pick"), item.get("date")
        ))
    conn.commit()
    conn.close()

# ==============================================================================
# ⚙️ БОКОВОЕ МЕНЮ
# ==============================================================================

with st.sidebar:
    st.header("⚙️ Настройки AI")
    input_vsegpt_key = st.text_input(
        "VseGPT API Key:", 
        value=vsegpt_key, 
        type="password"
    )
    
    selected_model = st.selectbox(
        "Модель нейросети:",
        options=[
            "google/gemini-2.5-flash-lite",
            "openai/gpt-4o-mini",
            "google/gemini-2.5-flash"
        ],
        index=0
    )
    
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
# 🧠 ВЫЗОВ НЕЙРОСЕТИ
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
        temperature=0.3,
        max_tokens=350
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
                'ВРЕМЯ_МАТЧА', 'СТАВКА', 'ИТ', 'БОЛЕЕ_АГРЕССИВНО', 
                'ОСТОРОЖНАЯ_СТАВКА', 'ЛУЧШАЯ_СТАВКА', 'УВЕРЕННОСТЬ', 'РАЗБОР'
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
        "1. Введите список матчей (каждый матч с новой строки):", 
        placeholder="Портленд Тимберс - Остин ФК\nКолорадо Рэпидс - Реал Солт-Лейк\nСан-Диего - Лос-Анджелес Гэлакси",
        height=130
    )
    
    manual_metrics = st.text_area(
        "2. (Опционально) Вставьте скопированные данные/статистику:",
        placeholder="Сюда можно вставить текст или цифры с Flashscore / Arbworld / NB Bet для строгого расчета...",
        height=80
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
                    real_metrics = get_footystats_data(match)

                    if real_metrics:
                        metrics_summary = f"РЕАЛЬНАЯ СТАТИСТИКА ИЗ БАЗЫ OPTA:\n{real_metrics}"
                    else:
                        metrics_summary = "Данные по турнирной таблице не найдены. Оценивай строго по реальному классу клубов."

                    analysis_prompt = f"""
                    Ты спортивный аналитик. Сделай объективный капперский прогноз на матч: "{match}".
                    Время запроса: {current_time_str} (Уфа, UTC+5).

                    ВХОДНЫЕ ФАКТЫ:
                    {metrics_summary}

                    СТРОГИЕ ПРАВИЛА:
                    1. Опирайся на реальное место в таблице и текущую форму команд.
                    2. Не штампуй одинаковые тоталы: если команда забивает мало или идет на серии поражений — выбирай ИТМ(1.0 / 1.5) или плюсовую фору соперника.
                    3. Если явный фаворит играет в гостях — выбирай П2 или Ф2(0).

                    ФОРМАТ ВЫВОДА:
                    ВРЕМЯ_МАТЧА: [Дата и время по Уфе]
                    СТАВКА: [*Название* фора или победа]
                    ИТ: [*Название* ИТБ(1.5), ИТБ(1.0), ИТМ(1.5) или ИТМ(1.0)]
                    БОЛЕЕ_АГРЕССИВНО: [Рискованная ставка]
                    ОСТОРОЖНАЯ_СТАВКА: [Надежный исход: 1Х, Х2, плюсовая фора]
                    ЛУЧШАЯ_СТАВКА: [Главный выбор]
                    УВЕРЕННОСТЬ: [От ⭐⭐⭐ до ⭐⭐⭐⭐⭐]
                    РАЗБОР: [2 конкретных тезиса по фактической форме и положению в таблице]
                    """

                    try:
                        raw_response = ask_vsegpt(analysis_prompt)
                        parsed_data = parse_match_block(raw_response)

                        match_time_ufa = parsed_data.get('ВРЕМЯ_МАТЧА', 'Предстоящий матч')
                        bet_main = parsed_data.get('СТАВКА', '—')
                        ind_total = parsed_data.get('ИТ', '—')
                        bet_agg = parsed_data.get('БОЛЕЕ_АГРЕССИВНО', '—')
                        bet_caut = parsed_data.get('ОСТОРОЖНАЯ_СТАВКА', '—')
                        best_pick = parsed_data.get('ЛУЧШАЯ_СТАВКА', bet_main)
                        confidence_str = parsed_data.get('УВЕРЕННОСТЬ', '⭐⭐⭐⭐')
                        review_val = parsed_data.get('РАЗБОР', 'Анализ завершен.')

                        with st.expander(f"⚽ {i}. {match} | 🕒 {match_time_ufa}", expanded=(i == 1)):
                            if real_metrics:
                                st.info(f"📊 **Метрики из базы:** {real_metrics}")
                            else:
                                st.warning("⚠️ Команда не найдена в базе FotMob, расчет по внутренним знаниям.")

                            st.caption(f"🕒 **Начало:** {match_time_ufa} | **Уверенность:** {confidence_str}")
                            st.markdown(f"🎯 **Ставка:** `{bet_main}`")
                            st.markdown(f"⚽ **ИТ:** `{ind_total}`")
                            st.markdown(f"⚡ **Более агрессивно:** `{bet_agg}`")
                            st.markdown(f"🛡️ **Осторожная ставка:** `{bet_caut}`")
                            st.success(f"🔥 **Лучшая ставка на этот матч:** `{best_pick}`")
                            st.markdown(f"📋 **Разбор:**\n\n{review_val}")
                    
                        tg_message_text = (
                            f"⚽ <b>Прогноз на матч: {escape_html(match)}</b>\n"
                            f"🕒 <b>Начало:</b> <code>{escape_html(match_time_ufa)}</code>\n\n"
                            f"🎯 <b>Ставка:</b> <code>{escape_html(bet_main)}</code> [⏳]\n"
                            f"⚽ <b>ИТ:</b> <code>{escape_html(ind_total)}</code> [⏳]\n"
                            f"⚡ <b>Более агрессивно:</b> <code>{escape_html(bet_agg)}</code> [⏳]\n"
                            f"🛡️ <b>Осторожная ставка:</b> <code>{escape_html(bet_caut)}</code> [⏳]\n"
                            f"🔥 <b>Лучшая ставка на этот матч:</b> <code>{escape_html(best_pick)}</code> [⏳]\n"
                            f"⭐ <b>Уверенность:</b> {confidence_str}\n\n"
                            f"📝 <b>Разбор метрик:</b>\n{escape_html(review_val)}"
                        )

                        success, msg, msg_id = send_telegram_message(tg_message_text, input_tg_token, input_tg_chat_id)
                        if success and msg_id:
                            st.toast(f"📤 Прогноз отправлен в Telegram!", icon="✅")
                            match_item = {
                                "match": match, "match_time_ufa": match_time_ufa,
                                "bet_main": bet_main, "ind_total": ind_total,
                                "bet_aggressive": bet_agg, "bet_cautious": bet_caut,
                                "best_pick": best_pick, "confidence": confidence_str,
                                "review": review_val, "message_id": msg_id,
                                "overall_status": "⏳ Ожидание",
                                "status_main": "⏳", "status_ind_total": "⏳",
                                "status_aggressive": "⏳", "status_cautious": "⏳",
                                "status_best_pick": "⏳",
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
                        express_lines.append(f"{idx}. <b>{escape_html(item['match'])}</b> (🕒 <code>{escape_html(item['time'])}</code>) — Выбор: <code>{escape_html(item['pick'])}</code> ({item['confidence']})")

                    express_text = (
                        f"🔥 <b>ТОП-ЭКСПРЕСС ДНЯ (⭐⭐⭐⭐⭐)</b> 🔥\n\n"
                        + "\n".join(express_lines) +
                        f"\n\n📊 <b>Примерный итоговый коэффициент:</b> <code>~{approx_total_odds}</code>\n"
                        f"💡 <b>Статус:</b> Отобраны матчи с максимальной уверенностью."
                    )

                    send_telegram_message(express_text, input_tg_token, input_tg_chat_id)
                    st.success("🔥 ТОП-Экспресс дня отправлен в Telegram!")
            else:
                st.info("ℹ️ Нет матчей с уверенностью ⭐⭐⭐⭐⭐ для Экспресса дня.")

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
                    b_main = item["bet_main"]
                    i_total = item.get("ind_total", "—")
                    b_agg = item["bet_aggressive"]
                    b_caut = item["bet_cautious"]
                    b_best = item.get("best_pick", "—")
                    msg_id = item["message_id"]
                    
                    check_prompt = f"""
                    Проверь результат матча: "{match_name}".
                    Маркеты:
                    - Ставка: {b_main}
                    - ИТ: {i_total}
                    - Более агрессивно: {b_agg}
                    - Осторожная ставка: {b_caut}
                    - Лучшая ставка: {b_best}

                    Ответь СТРОГО:
                    СТАВКА: [WIN/LOSS]
                    ИТ: [WIN/LOSS]
                    БОЛЕЕ_АГРЕССИВНО: [WIN/LOSS]
                    ОСТОРОЖНАЯ_СТАВКА: [WIN/LOSS]
                    ЛУЧШАЯ_СТАВКА: [WIN/LOSS]
                    (Если идет или не начался, напиши PENDING)
                    """
                    try:
                        res = ask_vsegpt(check_prompt).upper()
                        
                        if "PENDING" in res:
                            continue

                        item["status_main"] = "✅" if "СТАВКА: WIN" in res else "❌"
                        item["status_ind_total"] = "✅" if "ИТ: WIN" in res else "❌"
                        item["status_aggressive"] = "✅" if "БОЛЕЕ_АГРЕССИВНО: WIN" in res else "❌"
                        item["status_cautious"] = "✅" if "ОСТОРОЖНАЯ_СТАВКА: WIN" in res else "❌"
                        item["status_best_pick"] = "✅" if "ЛУЧШАЯ_СТАВКА: WIN" in res else "❌"
                        item["overall_status"] = "🎯 Завершено"

                        updated_msg_text = (
                            f"⚽ <b>Прогноз на матч: {escape_html(match_name)}</b>\n"
                            f"🕒 <b>Начало:</b> <code>{escape_html(match_time_ufa)}</code>\n\n"
                            f"🎯 <b>Ставка:</b> <code>{escape_html(b_main)}</code> [{item['status_main']}]\n"
                            f"⚽ <b>ИТ:</b> <code>{escape_html(i_total)}</code> [{item['status_ind_total']}]\n"
                            f"⚡ <b>Более агрессивно:</b> <code>{escape_html(b_agg)}</code> [{item['status_aggressive']}]\n"
                            f"🛡️ <b>Осторожная ставка:</b> <code>{escape_html(b_caut)}</code> [{item['status_cautious']}]\n"
                            f"🔥 <b>Лучшая ставка на этот матч:</b> <code>{escape_html(b_best)}</code> [{item['status_best_pick']}]\n"
                            f"⭐ <b>Уверенность:</b> {item['confidence']}\n\n"
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
                st.write(f"**Ставка:** {h_item['bet_main']} [{h_item.get('status_main', '⏳')}]")
                st.write(f"**ИТ:** {h_item.get('ind_total', '—')} [{h_item.get('status_ind_total', '⏳')}]")
                st.write(f"**Более агрессивно:** {h_item.get('bet_aggressive', '—')} [{h_item.get('status_aggressive', '⏳')}]")
                st.write(f"**Осторожная ставка:** {h_item.get('bet_cautious', '—')} [{h_item.get('status_cautious', '⏳')}]")
                st.write(f"**🔥 Лучшая ставка:** {h_item.get('best_pick', '—')} [{h_item.get('status_best_pick', '⏳')}]")
                st.markdown(f"**Разбор:**\n\n{h_item['review']}")
