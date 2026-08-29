import streamlit as st
import google.generativeai as genai
from PIL import Image
import time
import requests
import json
import os
from datetime import datetime
from parsers import (
    get_arbworld_moneyway, 
    get_corner_stats_data, 
    get_footystats_data,
    get_fbref_data,
    get_oddsportal_dropping_odds
)

st.set_page_config(page_title="Match Analytics AI", page_icon="⚽", layout="wide")

st.title("⚽ Аналитический центр спортивных матчей")
st.caption("Агрегатор: Arbworld, Corner Stats, FootyStats, FBref & Oddsportal + Экспресс дня (9.5-10/10) + Детальный трекер 🚀")

gemini_key = st.secrets.get("GEMINI_API_KEY", "")

# Ваши предустановленные данные Telegram
default_tg_token = "8758421691:AAFfIvHR1g0ak2QejRqhNrpsy-DRXaHgTFU"
default_tg_chat_id = "500635733"

tg_token = st.secrets.get("TELEGRAM_BOT_TOKEN", default_tg_token)
tg_chat_id = st.secrets.get("TELEGRAM_CHAT_ID", default_tg_chat_id)

HISTORY_FILE = "match_history.json"

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []
    return []

def save_history(history_data):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history_data, f, ensure_ascii=False, indent=4)

with st.sidebar:
    st.header("⚙️ Настройки")
    if gemini_key:
        st.success("🟢 Gemini API подключен!")
    else:
        gemini_key = st.text_input("Gemini API Key:", type="password")

    st.markdown("---")
    st.header("🤖 Telegram Бот")
    input_tg_token = st.text_input("Bot Token:", value=tg_token, type="password")
    input_tg_chat_id = st.text_input("Chat ID:", value=tg_chat_id)
    st.info("💡 Бот должен иметь возможность редактировать сообщения.")

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

with tab3:
    st.subheader("📊 История прогнозов и автообновление маркеров в Telegram")
    history = load_history()
    
    if not history:
        st.info("История пуста. Сформируйте прогнозы, и они автоматически появятся здесь.")
    else:
        if st.button("🔄 Проверить результаты по каждому маркету"):
            with st.spinner("Проверяем фактические итоги матчей и обновляем Telegram..."):
                genai.configure(api_key=gemini_key)
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
                    Ты спортивный бот-аналитик. Проверь результаты реально завершившегося матча: "{match_name}".
                    Нам нужно узнать итоги по трем позициям:
                    1. Исход/фора: "{pick}"
                    2. Тотал голов: "{total_pick}"
                    3. Угловые: "{corners_pick}"

                    Ответь СТРОГО в формате:
                    ИСХОД: [WIN или LOSS]
                    ТОТАЛ: [WIN или LOSS]
                    УГЛОВЫЕ: [WIN или LOSS]
                    Если матч еще не завершился, напиши PENDING для соответствующих полей.
                    """
                    try:
                        m = genai.GenerativeModel('gemini-2.5-flash')
                        res = m.generate_content(check_prompt).text.strip()
                        
                        res_upper = res.upper()
                        if "PENDING" in res_upper:
                            continue

                        # Определяем статус каждого маркета
                        item["status_pick"] = "✅" if "ИСХОД: WIN" in res_upper or "WIN" in res_upper.split("ИСХОД")[-1].split("\n")[0] else "❌"
                        item["status_total"] = "✅" if "ТОТАЛ: WIN" in res_upper else "❌"
                        item["status_corners"] = "✅" if "УГЛОВЫЕ: WIN" in res_upper else "❌"
                        item["overall_status"] = "🎯 Завершено"

                        # Пересобираем текст сообщения для Telegram с актуальными маркетами
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
                        item["original_text"] = updated_msg_text
                        updated_count += 1
                    except Exception as e:
                        continue
                
                save_history(history)
                st.success(f"Проверка завершена! Обновлено матчей: {updated_count}")
        
        for idx, h_item in enumerate(reversed(history), 1):
            with st.expander(f"{h_item['overall_status']} | {h_item['match']} ({h_item['date']})"):
                st.write(f"**Исход:** {h_item['pick']} [{h_item.get('status_pick', '⏳')}]")
                st.write(f"**Тотал:** {h_item['total']} [{h_item.get('status_total', '⏳')}]")
                st.write(f"**Угловые:** {h_item['corners']} [{h_item.get('status_corners', '⏳')}]")
                st.code(h_item['original_text'], language="markdown")

def ask_gemini(prompt, image=None):
    candidate_models = ['gemini-2.5-flash', 'models/gemini-2.5-flash', 'gemini-3.5-flash', 'models/gemini-3.5-flash']
    last_error = ""
    for model_name in candidate_models:
        for attempt in range(3):
            try:
                m = genai.GenerativeModel(model_name)
                inputs = [prompt, image] if image else [prompt]
                return m.generate_content(inputs).text
            except Exception as e:
                last_error = str(e)
                time.sleep(4 if ("429" in str(e) or "Quota" in str(e)) else 2)
                continue
    raise Exception(f"Превышен лимит запросов (Quota 429). Детали: {last_error}")

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
    if not gemini_key:
        st.error("Укажите Gemini API Key!")
    elif not matches_list and not uploaded_image:
        st.warning("Укажите матчи или загрузите скриншот!")
    else:
        genai.configure(api_key=gemini_key)

        with st.spinner("1/3 Распознавание матчей со скриншота..."):
            if uploaded_image and not matches_list:
                try:
                    ocr_prompt = "Найди на скриншоте ВСЕ спортивные матчи в формате: Команда 1 - Команда 2."
                    raw_ocr = ask_gemini(ocr_prompt, uploaded_image)
                    matches_list = [m.strip().replace("*", "") for m in raw_ocr.strip().split("\n") if "-" in m or "—" in m]
                except Exception as e:
                    st.error(f"🔴 Ошибка чтения скриншота: {e}")
                    st.stop()

        if not matches_list:
            st.error("Матчи не найдены.")
            st.stop()

        st.success(f"Найдено матчей для анализа: **{len(matches_list)}**")

        accumulated_express_items = []
        history_data = load_history()

        for i, match in enumerate(matches_list, 1):
            with st.spinner(f"2/3 Анализ матча {i}/{len(matches_list)}: {match}..."):
                time.sleep(4)

                real_arbworld = get_arbworld_moneyway(match)
                real_corners = get_corner_stats_data(match)
                real_footystats = get_footystats_data(match)
                real_fbref = get_fbref_data(match)
                real_oddsportal = get_oddsportal_dropping_odds(match)

                analysis_prompt = f"""
                Ты профессиональный спортивный аналитик. Сделай глубокий прогноз для матча: {match}.
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
                УВЕРЕННОСТЬ: [Оценка по 10-ти бальной шкале строго в формате X/10, например: 9.5/10 или 10/10]
                ПОГОДА_ПОЛЕ: [Краткий учет фактора поля и погоды]
                РАЗБОР: [Обоснование ставки]
                """

                try:
                    raw_response = ask_gemini(analysis_prompt)
                    parsed_data = parse_match_block(raw_response)

                    confidence_str = parsed_data.get('УВЕРЕННОСТЬ', '9.5/10')
                    pick_val = parsed_data.get('ИСХОД', '—')
                    total_val = parsed_data.get('ТОТАЛ', '—')
                    corners_val = parsed_data.get('УГЛОВЫЕ', '—')
                    weather_val = parsed_data.get('ПОГОДА_ПОЛЕ', '—')
                    review_val = parsed_data.get('РАЗБОР', '—')
                    
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

                    # Текст с разделенными маркетами статусов для каждого маркета
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
                        st.toast(f"📤 Прогноз по матчу {match} отправлен в Telegram!", icon="✅")
                        history_data.append({
                            "match": match,
                            "pick": pick_val,
                            "total": total_val,
                            "corners": corners_val,
                            "confidence": confidence_str,
                            "weather": weather_val,
                            "review": review_val,
                            "original_text": tg_message_text,
                            "message_id": msg_id,
                            "overall_status": "⏳ Ожидание",
                            "status_pick": "⏳",
                            "status_total": "⏳",
                            "status_corners": "⏳",
                            "date": datetime.now().strftime("%Y-%m-%d %H:%M")
                        })
                    else:
                        st.error(f"Не удалось отправить в Telegram: {msg}")

                except Exception as e:
                    st.error(f"🔴 Ошибка анализа матча {match}: {e}")

        save_history(history_data)

        if len(accumulated_express_items) >= 1:
            with st.spinner("3/3 Формирование ТОП-Экспресса дня..."):
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
