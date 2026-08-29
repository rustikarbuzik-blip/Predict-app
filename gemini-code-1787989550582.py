import streamlit as st
import google.generativeai as genai
from PIL import Image
import time
import requests
from parsers import (
    get_arbworld_moneyway, 
    get_corner_stats_data, 
    get_footystats_data,
    get_fbref_data,
    get_oddsportal_dropping_odds
)

st.set_page_config(page_title="Match Analytics AI", page_icon="⚽", layout="wide")

st.title("⚽ Аналитический центр спортивных матчей")
st.caption("Агрегатор: Arbworld, Corner Stats, FootyStats, FBref & Oddsportal + Авто-отправка в Telegram")

gemini_key = st.secrets.get("GEMINI_API_KEY", "")

# Ваши предустановленные данные Telegram
default_tg_token = "8758421691:AAFfIvHR1g0ak2QejRqhNrpsy-DRXaHgTFU"
default_tg_chat_id = "500635733"

tg_token = st.secrets.get("TELEGRAM_BOT_TOKEN", default_tg_token)
tg_chat_id = st.secrets.get("TELEGRAM_CHAT_ID", default_tg_chat_id)

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
    st.info("💡 Не забудьте нажать /start в вашем боте в Telegram, чтобы он мог присылать сообщения.")

tab1, tab2 = st.tabs(["📝 Название матча(ей)", "📸 Скриншот линии"])
matches_list = []
uploaded_image = None

with tab1:
    match_input = st.text_area(
        "Введите матчи (каждый с новой строки):", 
        placeholder="Факел - Зенит\nТоттенхэм - Ньюкасл"
    )
    if match_input.strip():
        matches_list = [m.strip() for m in match_input.strip().split("\n") if m.strip()]

with tab2:
    uploaded_file = st.file_uploader("Перетащите сюда скриншот линии:", type=["jpg", "jpeg", "png"])
    if uploaded_file is not None:
        uploaded_image = Image.open(uploaded_file)
        st.image(uploaded_image, caption="Загруженный скриншот", width=450)

def ask_gemini(prompt, image=None):
    candidate_models = [
        'gemini-2.5-flash',
        'models/gemini-2.5-flash',
        'gemini-3.5-flash',
        'models/gemini-3.5-flash'
    ]
    last_error = ""
    for model_name in candidate_models:
        for attempt in range(2):
            try:
                m = genai.GenerativeModel(model_name)
                inputs = [prompt, image] if image else [prompt]
                response = m.generate_content(inputs)
                return response.text
            except Exception as e:
                last_error = str(e)
                time.sleep(2)
                continue
    raise Exception(f"Детали ошибки API: {last_error}")

def parse_match_block(block_text):
    data = {}
    for line in block_text.split('\n'):
        if ':' in line:
            k, v = line.split(':', 1)
            data[k.strip().upper()] = v.strip()
    return data

def send_telegram_message(text, token, chat_id):
    if not token or not chat_id:
        return False, "Не заполнены настройки Telegram (Token или Chat ID)."
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        res = requests.post(url, json=payload, timeout=5)
        if res.status_code == 200:
            return True, "Успешно отправлено!"
        else:
            return False, f"Ошибка Telegram API: {res.text}"
    except Exception as e:
        return False, f"Ошибка соединения: {e}"

if st.button("🚀 Сформировать и отправить прогнозы", type="primary", use_container_width=True):
    if not gemini_key:
        st.error("Укажите Gemini API Key в Secrets или в левом меню!")
    elif not matches_list and not uploaded_image:
        st.warning("Укажите хотя бы один матч или загрузите скриншот!")
    else:
        genai.configure(api_key=gemini_key)

        with st.spinner("1/3 Распознавание матчей со скриншота..."):
            if uploaded_image and not matches_list:
                try:
                    ocr_prompt = (
                        "Найди на скриншоте ВСЕ спортивные матчи. "
                        "Верни их списком, каждый с новой строки в формате: Команда 1 - Команда 2."
                    )
                    raw_ocr = ask_gemini(ocr_prompt, uploaded_image)
                    matches_list = [m.strip().replace("*", "") for m in raw_ocr.strip().split("\n") if "-" in m or "—" in m]
                except Exception as e:
                    st.error(f"🔴 Ошибка чтения скриншота: {e}")
                    st.stop()

        if not matches_list:
            st.error("Не удалось найти матчи на скриншоте.")
            st.stop()

        st.success(f"Найдено матчей для анализа: **{len(matches_list)}**")

        for i, match in enumerate(matches_list, 1):
            with st.spinner(f"2/3 Анализ матча {i}/{len(matches_list)}: {match}..."):
                
                time.sleep(3)

                real_arbworld = get_arbworld_moneyway(match)
                real_corners = get_corner_stats_data(match)
                real_footystats = get_footystats_data(match)
                real_fbref = get_fbref_data(match)
                real_oddsportal = get_oddsportal_dropping_odds(match)

                analysis_prompt = f"""
                Ты профессиональный спортивный аналитик. Сделай глубокий прогноз для матча: {match}.
                Обязательно учитывай фактор поля (домашний/гостевой тренд) и вероятное влияние погодных условий (сезонный фактор, состояние газона, температура/осадки для этой лиги).

                ДАННЫЕ АГРЕГАТОРОВ:
                - Arbworld: {real_arbworld}
                - Corner Stats: {real_corners}
                - FootyStats: {real_footystats}
                - FBref (StatsBomb): {real_fbref}
                - Oddsportal: {real_oddsportal}

                Ответь СТРОГО в формате:
                ИСХОД: [Ставка на исход или фору]
                ТОТАЛ: [Ставка на тотал голов]
                УГЛОВЫЕ: [Ставка на угловые]
                УВЕРЕННОСТЬ: [Оценка от 1 до 5, например: 4/5]
                ПОГОДА_ПОЛЕ: [Краткий учет фактора поля и погоды в 1 предложении]
                РАЗБОР: [Обоснование ставки из 2 предложений]
                """

                try:
                    raw_response = ask_gemini(analysis_prompt)
                    parsed_data = parse_match_block(raw_response)

                    # Отображение в интерфейсе Streamlit
                    with st.expander(f"⚽ {i}. {match}", expanded=(i == 1)):
                        st.markdown("#### 📊 Данные аналитических сервисов")
                        c1, c2, c3 = st.columns(3)
                        with c1:
                            st.success(f"**FootyStats:**\n{real_footystats}")
                            st.success(f"**Arbworld:**\n{real_arbworld}")
                        with c2:
                            st.success(f"**FBref:**\n{real_fbref}")
                            st.success(f"**Oddsportal:**\n{real_oddsportal}")
                        with c3:
                            st.success(f"**Corner Stats:**\n{real_corners}")

                        st.markdown("---")
                        st.markdown("#### 🎯 Карточка ставки")

                        col1, col2, col3, col4 = st.columns(4)
                        col1.metric("Исход / Фора", parsed_data.get('ИСХОД', 'П1'))
                        col2.metric("Индив. тотал", parsed_data.get('ТОТАЛ', 'ТБ (2.5)'))
                        col3.metric("Угловые", parsed_data.get('УГЛОВЫЕ', 'ТБ (9.5)'))
                        col4.metric("Уверенность", parsed_data.get('УВЕРЕННОСТЬ', '4/5'))

                        st.info(f"🏟️ **Погода и фактор поля:** {parsed_data.get('ПОГОДА_ПОЛЕ', 'Учитывается стандартный домашний фактор.')}")
                        st.success(f"**📋 Аналитический разбор:**\n\n{parsed_data.get('РАЗБОР', 'Анализ завершен.')}")

                    # АВТОМАТИЧЕСКАЯ ОТПРАВКА В TELEGRAM СРАЗУ ПОСЛЕ АНАЛИЗА
                    tg_message_text = (
                        f"⚽ *Прогноз на матч: {match}*\n\n"
                        f"🎯 *Исход/Фора:* `{parsed_data.get('ИСХОД', '—')}`\n"
                        f"📈 *Тотал:* `{parsed_data.get('ТОТАЛ', '—')}`\n"
                        f"🚩 *Угловые:* `{parsed_data.get('УГЛОВЫЕ', '—')}`\n"
                        f"⭐ *Уверенность:* `{parsed_data.get('УВЕРЕННОСТЬ', '—')}`\n"
                        f"🏟️ *Погода/Поле:* {parsed_data.get('ПОГОДА_ПОЛЕ', '—')}\n\n"
                        f"📝 *Разбор:* {parsed_data.get('РАЗБОР', '—')}"
                    )

                    success, msg = send_telegram_message(tg_message_text, input_tg_token, input_tg_chat_id)
                    if success:
                        st.toast(f"📤 Прогноз по матчу {match} отправлен в Telegram!", icon="✅")
                    else:
                        st.error(f"Не удалось отправить в Telegram матча {match}: {msg}")

                except Exception as e:
                    st.error(f"🔴 Ошибка анализа матча {match}: {e}")
