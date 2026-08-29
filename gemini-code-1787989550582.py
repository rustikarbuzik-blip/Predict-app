import streamlit as st
import google.generativeai as genai
from PIL import Image
import time
from parsers import (
    get_arbworld_moneyway, 
    get_corner_stats_data, 
    get_footystats_data,
    get_fbref_data,
    get_oddsportal_dropping_odds
)

st.set_page_config(page_title="Match Analytics AI", page_icon="⚽", layout="wide")

st.title("⚽ Аналитический центр спортивных матчей")
st.caption("Агрегатор: РЕАЛЬНЫЕ Arbworld, Corner Stats, FootyStats, FBref & Oddsportal")

gemini_key = st.secrets.get("GEMINI_API_KEY", "")

with st.sidebar:
    st.header("⚙️ Настройки")
    if gemini_key:
        st.success("🟢 Бесплатный Gemini API подключен!")
    else:
        gemini_key = st.text_input("Gemini API Key:", type="password", help="Вставьте ключ с aistudio.google.com")

tab1, tab2 = st.tabs(["📝 Название матча(ей)", "📸 Скриншот линии"])
matches_list = []
uploaded_image = None

with tab1:
    match_input = st.text_area(
        "Введите матчи (каждый с новой строки):", 
        placeholder="Тоттенхэм - Ньюкасл\nКовентри Сити - Халл\nБорнмут - Эвертон"
    )
    if match_input.strip():
        matches_list = [m.strip() for m in match_input.strip().split("\n") if m.strip()]

with tab2:
    uploaded_file = st.file_uploader("Перетащите сюда скриншот линии:", type=["jpg", "jpeg", "png"])
    if uploaded_file is not None:
        uploaded_image = Image.open(uploaded_file)
        st.image(uploaded_image, caption="Загруженный скриншот", width=450)

def ask_gemini(prompt, image=None):
    # Актуальные стабильные модели для API v1beta
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

if st.button("🚀 Сформировать прогнозы по всем матчам", type="primary", use_container_width=True):
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
                        "Найди на скриншоте ВСЕ спортивные матчи (соперничающие пары команд). "
                        "Верни их простым списком, где каждый матч с новой строки в формате: Команда 1 - Команда 2. "
                        "Не добавляй лишнего текста, только названия матчей."
                    )
                    raw_ocr = ask_gemini(ocr_prompt, uploaded_image)
                    matches_list = [m.strip().replace("*", "") for m in raw_ocr.strip().split("\n") if "-" in m or "—" in m]
                except Exception as e:
                    st.error(f"🔴 Ошибка чтения скриншота: {e}")
                    st.stop()

        if not matches_list:
            st.error("Не удалось найти матчи. Попробуйте загрузить более четкий скриншот.")
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
                Ты спортивный аналитик. Сделай глубокий прогноз для матча: {match}.

                РЕАЛЬНЫЕ ДАННЫЕ С АГРЕГАТОРОВ:
                - Arbworld: {real_arbworld}
                - Corner Stats: {real_corners}
                - FootyStats: {real_footystats}
                - FBref (StatsBomb): {real_fbref}
                - Oddsportal: {real_oddsportal}

                Задания:
                1. Сформируй итоговую рекомендацию с учетом продвинутого xG, прессинга (FBref) и изменения коэффициентов.

                Ответь СТРОГО в формате:
                ИСХОД: [Ставка на исход или фору, например: П1 или Фора 1 (0)]
                ТОТАЛ: [Ставка на тотал голов, например: ИТБ1 (1.5)]
                УГЛОВЫЕ: [Ставка на угловые, например: ТБ (9.5)]
                УВЕРЕННОСТЬ: [Оценка уверенности: например, 4/5]
                РАЗБОР: [Короткое обоснование ставки из 2 предложений]
                """

                try:
                    raw_response = ask_gemini(analysis_prompt)
                    parsed_data = parse_match_block(raw_response)

                    with st.expander(f"⚽ {i}. {match}", expanded=(i == 1)):
                        st.markdown("#### 📊 Данные аналитических сервисов")
                        c1, c2, c3 = st.columns(3)
                        with c1:
                            st.success(f"**FootyStats:**\n{real_footystats}")
                            st.success(f"**Arbworld:**\n{real_arbworld}")
                        with c2:
                            st.success(f"**FBref (StatsBomb):**\n{real_fbref}")
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

                        st.success(f"**📋 Аналитический разбор:**\n\n{parsed_data.get('РАЗБОР', 'Анализ завершен.')}")

                except Exception as e:
                    st.error(f"🔴 Ошибка анализа матча {match}: {e}")                     
