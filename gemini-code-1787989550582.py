import streamlit as st
from openai import OpenAI
from PIL import Image
import requests
import base64
import io
from datetime import datetime
import sqlite3
from parsers import (
    get_arbworld_moneyway, 
    get_corner_stats_data, 
    get_footystats_data,
    get_fbref_data,
    get_oddsportal_dropping_odds
)

st.set_page_config(page_title="Match Analytics AI", page_icon="⚽", layout="wide")

st.title("⚽ Аналитический центр спортивных матчей (VseGPT Unlimited 🚀)")
st.caption("Агрегатор: Arbworld, Corner Stats, FootyStats, FBref & Oddsportal + SQLite + VseGPT API")

vsegpt_key = st.secrets.get("VSEGPT_API_KEY", "")

default_tg_token = "8758421691:AAFfIvHR1g0ak2QejRqhNrpsy-DRXaHgTFU"
default_tg_chat_id = "500635733"

tg_token = st.secrets.get("TELEGRAM_BOT_TOKEN", default_tg_token)
tg_chat_id = st.secrets.get("TELEGRAM_CHAT_ID", default_tg_chat_id)

def init_db():
    conn = sqlite3.connect("match_history.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match TEXT,
            pick TEXT,
            total TEXT,
            corners TEXT,
            confidence TEXT,
            weather TEXT,
            review TEXT,
            message_id INTEGER,
            overall_status TEXT,
            status_pick TEXT,
            status_total TEXT,
            status_corners TEXT,
            date TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def load_history():
    conn = sqlite3.connect("match_history.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT match, pick, total, corners, confidence, weather, review, message_id, overall_status, status_pick, status_total, status_corners, date FROM history")
    rows = cursor.fetchall()
    conn.close()
    
    history = []
    for row in rows:
        history.append({
            "match": row[0], "pick": row[1], "total": row[2], "corners": row[3],
            "confidence": row[4], "weather": row[5], "review": row[6],
            "message_id": int(row[7]) if row[7] else 0, "overall_status": row[8],
            "status_pick": row[9], "status_total": row[10], "status_corners": row[11], "date": row[12]
        })
    return history

def save_match_to_db(item):
    conn = sqlite3.connect("match_history.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO history (match, pick, total, corners, confidence, weather, review, message_id, overall_status, status_pick, status_total, status_corners, date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        item.get("match"), item.get("pick"), item.get("total"), item.get("corners"),
        item.get("confidence"), item.get("weather"), item.get("review"), item.get("message_id"),
        item.get("overall_status", "⏳ Ожидание"), item.get("status_pick", "⏳"),
        item.get("status_total", "⏳"), item.get("status_corners", "⏳"), item.get("date")
    ))
    conn.commit()
    conn.close()

def update_history_in_db(history_data):
    conn = sqlite3.connect("match_history.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM history")
    for item in history_data:
        cursor.execute('''
            INSERT INTO history (match, pick, total, corners, confidence, weather, review, message_id, overall_status, status_pick, status_total, status_corners, date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            item.get("match"), item.get("pick"), item.get("total"), item.get("corners"),
            item.get("confidence"), item.get("weather"), item.get("review"), item.get("message_id"),
            item.get("overall_status"), item.get("status_pick"), item.get("status_total"),
            item.get("status_corners"), item.get("date")
        ))
    conn.commit()
    conn.close()

with st.sidebar:
    st.header("⚙️ Настройки VseGPT")
    input_vsegpt_key = st.text_input(
        "VseGPT API Key:", 
        value=vsegpt_key, 
        type="password"
    )
    selected_model = st.selectbox(
        "Модель нейросети:",
        options=[
            "google/gemini-2.5-flash",
            "google/gemini-2.0-flash",
            "openai/gpt-4o-mini"
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
    st.success("🟢 Локальная БД SQLite активна!")

tab1, tab2, tab3 = st.tabs(["📝 Название матча(ей)", "📸 Скриншот линии", "📋 История и результаты"])
matches_list = []
uploaded_image = None

with tab1:
    match_input = st.text_area(
        "Введите матчи (каждый с новой строки):", 
        placeholder="Унион Берлин - Айнтрахт Ф\nФакел - Зенит"
    )
    if match_input.strip():
        matches_list = [m.strip() for m in match_input.strip().split("\n") if m.strip()]

with tab2:
    uploaded_file = st.file_uploader("Перетащите сюда скриншот линии:", type=["jpg", "jpeg", "png"])
    if uploaded_file is not None:
        uploaded_image = Image.open(uploaded_file)
        st.image(uploaded_image, caption="Загруженный скриншот", width=450)

def ask_vsegpt(prompt, image=None):
    if not input_vsegpt_key:
        raise Exception("API ключ VseGPT не указан!")

    client = OpenAI(
        api_key=input_vsegpt_key,
        base_url="https://api.vsegpt.ru/v1"
    )

    if image:
        img_copy = image.copy()
        img_copy.thumbnail((600, 600))
        
        buffered = io.BytesIO()
        img_copy.save(buffered, format="JPEG", quality=65)
        img_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{img_b64}",
                            "detail": "low"
                        }
                    }
                ]
            }
        ]
    else:
        messages = [
            {"role": "user", "content": prompt}
        ]

    response = client.chat.completions.create(
        model=selected_model,
        messages=messages,
        temperature=0.3,
        max_tokens=350
    )
    return response.choices[0].message.content

with tab3:
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
                    pick = item["pick"]
                    total_pick = item["total"]
                    corners_pick = item["corners"]
                    msg_id = item["message_id"]
                    
                    check_prompt = f"""
                    Проверь результат матча: "{match_name}".
                    Ставки: 1) Исход: {pick}, 2) Тотал: {total_pick}, 3) Угловые: {corners_pick}.
                    Ответь СТРОГО:
                    ИСХОД: [WIN/LOSS]
                    ТОТАЛ: [WIN/LOSS]
                    УГЛОВЫЕ: [WIN/LOSS]
                    (Если идет или не начался, напиши PENDING)
                    """
                    try:
                        res = ask_vsegpt(check_prompt).upper()
                        
                        if "PENDING" in res:
                            continue

                        item["status_pick"] = "✅" if "ИСХОД: WIN" in res or "WIN" in res.split("ИСХОД")[-1].split("\n")[0] else "❌"
                        item["status_total"] = "✅" if "ТОТАЛ: WIN" in res else "❌"
                        item["status_corners"] = "✅" if "УГЛОВЫЕ: WIN" in res else "❌"
                        item["overall_status"] = "🎯 Завершено"

                        updated_msg_text = (
                            f"⚽ *Прогноз на матч: {match_name}*\n\n"
                            f"🎯 *Исход/Фора:* `{pick}` [{item['status_pick']}]\n"
                            f"📈 *Тотал голов:* `{total_pick}` [{item['status_total']}]\n"
                            f"🚩 *Угловые:* `{corners_pick}` [{item['status_corners']}]\n"
                            f"⭐ *Уверенность:* `{item['confidence']}`\n"
                            f"🏟️ *Погода/Поле:* {item['weather']}\n\n"
                            f"📝 *Разбор:* {item['review']}"
                        )
                        
                        edit_telegram_message_full(input_tg_token, input_tg_chat_id, msg_id, updated_msg_text)
                        updated_count += 1
                    except Exception as e:
                        continue
                
                update_history_in_db(history)
                st.success(f"Готово! Обновлено матчей: {updated_count}")
        
        for idx, h_item in enumerate(reversed(history), 1):
            with st.expander(f"{h_item['overall_status']} | {h_item['match']} ({h_item['date']})"):
                st.write(f"**Исход:** {h_item['pick']} [{h_item.get('status_pick', '⏳')}]")
                st.write(f"**Тотал:** {h_item['total']} [{h_item.get('status_total', '⏳')}]")
                st.write(f"**Угловые:** {h_item['corners']} [{h_item.get('status_corners', '⏳')}]")
                st.write(f"**Разбор:** {h_item['review']}")

def parse_match_block(block_text):
    data = {}
    for line in block_text.split('\n'):
        if ':' in line:
            k, v = line.split(':', 1)
            data[k.strip().upper()] = v.strip()
    return data

def send_telegram_message(text, token, chat_id):
    if not token or not chat_id:
        return False, "Не заполнены настройки Telegram.", None
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
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
    payload = {"chat_id": chat_id, "message_id": message_id, "text": new_text, "parse_mode": "Markdown"}
    try:
        res = requests.post(url, json=payload, timeout=5)
        return res.status_code == 200
    except:
        return False

if st.button("🚀 Сформировать прогнозы и Экспресс дня", type="primary", use_container_width=True):
    if not input_vsegpt_key:
        st.error("Укажите VseGPT API Key!")
    elif not matches_list and not uploaded_image:
        st.warning("Укажите матчи или загрузите скриншот!")
    else:
        with st.spinner("1/2 Распознавание матчей через VseGPT..."):
            if uploaded_image and not matches_list:
                try:
                    ocr_prompt = "Найди на скриншоте ВСЕ спортивные матчи в формате: Команда 1 - Команда 2. Верни только список матчей, каждый с новой строки."
                    raw_ocr = ask_vsegpt(ocr_prompt, uploaded_image)
                    matches_list = [m.strip().replace("*", "") for m in raw_ocr.strip().split("\n") if "-" in m or "—" in m]
                except Exception as e:
                    st.error(f"🔴 Ошибка чтения скриншота: {e}")
                    st.stop()

        if not matches_list:
            st.error("Матчи не найдены.")
            st.stop()

        st.success(f"Найдено матчей: **{len(matches_list)}**")

        accumulated_express_items = []

        for i, match in enumerate(matches_list, 1):
            with st.spinner(f"2/2 Анализ матча {i}/{len(matches_list)} ({match})..."):
                
                real_arbworld = get_arbworld_moneyway(match)
                real_corners = get_corner_stats_data(match)
                real_footystats = get_footystats_data(match)
                real_fbref = get_fbref_data(match)
                real_oddsportal = get_oddsportal_dropping_odds(match)

                analysis_prompt = f"""
                Сделай профессиональный прогноз для матча: {match}.
                Учитывай фактор поля и погоду.

                ДАННЫЕ АГРЕГАТОРОВ:
                - Arbworld: {real_arbworld}
                - Corner Stats: {real_corners}
                - FootyStats: {real_footystats}
                - FBref: {real_fbref}
                - Oddsportal: {real_oddsportal}

                Ответь СТРОГО в формате:
                ИСХОД: [Ставка на исход или фору]
                ТОТАЛ: [Ставка на тотал голов]
                УГЛОВЫЕ: [Ставка на угловые]
                УВЕРЕННОСТЬ: [X/10, например 9.5/10 или 8/10]
                ПОГОДА_ПОЛЕ: [Кратко факты]
                РАЗБОР: [Обоснование в 2-3 предложениях]
                """

                try:
                    raw_response = ask_vsegpt(analysis_prompt)
                    parsed_data = parse_match_block(raw_response)

                    confidence_str = parsed_data.get('УВЕРЕННОСТЬ', '9.5/10')
                    pick_val = parsed_data.get('ИСХОД', '—')
                    total_val = parsed_data.get('ТОТАЛ', '—')
                    corners_val = parsed_data.get('УГЛОВЫЕ', '—')
                    weather_val = parsed_data.get('ПОГОДА_ПОЛЕ', '—')
                    review_val = parsed_data.get('РАЗБОР', 'Анализ завершен.')
                    
                    conf_numeric = 0.0
                    try:
                        conf_numeric = float(confidence_str.replace('/10', '').replace(',', '.').strip())
                    except:
                        conf_numeric = 8.0

                    if conf_numeric >= 9.5:
                        accumulated_express_items.append({
                            "match": match,
                            "pick": pick_val,
                            "confidence": confidence_str
                        })

                    with st.expander(f"⚽ {i}. {match}", expanded=(i == 1)):
                        col1, col2, col3, col4 = st.columns(4)
                        col1.metric("Исход / Фора", pick_val)
                        col2.metric("Индив. тотал", total_val)
                        col3.metric("Угловые", corners_val)
                        col4.metric("Уверенность", confidence_str)

                        st.info(f"🏟️ **Погода и поле:** {weather_val}")
                        st.success(f"**📋 Разбор:**\n\n{review_val}")

                    tg_message_text = (
                        f"⚽ *Прогноз на матч: {match}*\n\n"
                        f"🎯 *Исход/Фора:* `{pick_val}` [⏳]\n"
                        f"📈 *Тотал голов:* `{total_val}` [⏳]\n"
                        f"🚩 *Угловые:* `{corners_val}` [⏳]\n"
                        f"⭐ *Уверенность:* `{confidence_str}`\n"
                        f"🏟️ *Погода/Поле:* {weather_val}\n\n"
                        f"📝 *Разбор:* {review_val}"
                    )

                    success, msg, msg_id = send_telegram_message(tg_message_text, input_tg_token, input_tg_chat_id)
                    if success and msg_id:
                        st.toast(f"📤 Прогноз отправлен в Telegram!", icon="✅")
                        match_item = {
                            "match": match, "pick": pick_val, "total": total_val, "corners": corners_val,
                            "confidence": confidence_str, "weather": weather_val, "review": review_val,
                            "message_id": msg_id, "overall_status": "⏳ Ожидание",
                            "status_pick": "⏳", "status_total": "⏳", "status_corners": "⏳",
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
                    express_lines.append(f"{idx}. *{item['match']}* — Ставка: `{item['pick']}` (⭐ {item['confidence']})")

                express_text = (
                    f"🔥 *ТОП-ЭКСПРЕСС ДНЯ (9.5+ / 10)* 🔥\n\n"
                    + "\n".join(express_lines) +
                    f"\n\n📊 *Примерный итоговый коэффициент:* `~{approx_total_odds}`\n"
                    f"💡 *Статус:* Прошли жесткий отбор."
                )

                send_telegram_message(express_text, input_tg_token, input_tg_chat_id)
                st.success("🔥 ТОП-Экспресс дня отправлен в Telegram!")
        else:
            st.info("ℹ️ Нет матчей с уверенностью 9.5+/10 для Экспресса дня.")
                
