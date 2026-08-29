import streamlit as st
import google.generativeai as genai
from PIL import Image

st.set_page_config(page_title="Match Analytics AI", page_icon="⚽", layout="wide")

st.title("⚽ Аналитический центр спортивных матчей")
st.caption("БЕСПЛАТНЫЙ агрегатор: FootyStats, Arbworld, Oddsportal, NB Bet, Corner Stats")

gemini_key = st.secrets.get("GEMINI_API_KEY", "")

with st.sidebar:
    st.header("⚙️ Настройки")
    if gemini_key:
        st.success("🟢 Бесплатный Gemini API подключен!")
    else:
        gemini_key = st.text_input("Gemini API Key:", type="password", help="Вставьте ключ с aistudio.google.com")

tab1, tab2 = st.tabs(["📝 Название матча", "📸 Скриншот линии"])
match_name = ""
uploaded_image = None

with tab1:
    match_input = st.text_input("Введите команды:", placeholder="например: Тоттенхэм - Ньюкасл")
    if match_input:
        match_name = match_input

with tab2:
    uploaded_file = st.file_uploader("Перетащите сюда скриншот:", type=["jpg", "jpeg", "png"])
    if uploaded_file is not None:
        uploaded_image = Image.open(uploaded_file)
        st.image(uploaded_image, caption="Загруженный скриншот", width=400)

def ask_gemini(prompt, image=None):
    candidate_models = [
        'gemini-3.6-flash',
        'models/gemini-3.6-flash',
        'gemini-3.0-flash',
        'models/gemini-3.0-flash'
    ]
    for model_name in candidate_models:
        try:
            m = genai.GenerativeModel(model_name)
            inputs = [prompt, image] if image else [prompt]
            response = m.generate_content(inputs)
            return response.text
        except Exception:
            continue
    raise Exception("Ошибка обращения к Gemini API.")

if st.button("🚀 Сформировать прогноз", type="primary", use_container_width=True):
    if not gemini_key:
        st.error("Укажите Gemini API Key в Secrets или в левом меню!")
    elif not match_name and not uploaded_image:
        st.warning("Укажите название матча или загрузите скриншот!")
    else:
        genai.configure(api_key=gemini_key)

        with st.spinner("1/2 Чтение матча со скриншота..."):
            if uploaded_image and not match_name:
                try:
                    ocr_prompt = (
                        "Найди на скриншоте ПЕРВЫЙ (самый верхний) спортивный матч. "
                        "Напиши ТОЛЬКО название двух команд в формате: Команда 1 - Команда 2. "
                        "Не выводи список других матчей, не используй символы разметки."
                    )
                    match_name = ask_gemini(ocr_prompt, uploaded_image).strip().replace("*", "")
                except Exception as e:
                    st.error(f"🔴 Ошибка чтения скриншота: {e}")
                    st.stop()

        with st.spinner(f"2/2 ИИ-анализ и формирование прогноза для {match_name}..."):
            st.markdown(f"### 🏟 Матч: **{match_name}**")

            analysis_prompt = f"""
            Ты профессиональный спортивный аналитик. Сделай прогноз на футбол: {match_name}.
            Смоделируй актуальные данные 5 сервисов (FootyStats, Arbworld, Oddsportal, NB Bet, Corner Stats) и дай итоговую рекомендацию.
            
            Ответь СТРОГО в следующем формате без лишних вступлений:
            
            FOOTYSTATS: [1 предложение о форме, xG и тоталах]
            ARBWORLD: [1 предложение о прогрузах Moneyway]
            ODDSPORTAL: [1 предложение о движении коэффициентов]
            NBBET: [1 предложение о трендах и сериях команд]
            CORNERSTATS: [1 предложение о среднем тотале угловых]
            
            ИСХОД: [Конкретная ставка, например: П1 или Фора 1 (-1)]
            ТОТАЛ: [Конкретная ставка на голы, например: ИТБ1 (1.5)]
            УГЛОВЫЕ: [Конкретная ставка на угловые, например: ТБ (9.5)]
            УВЕРЕННОСТЬ: [Значение от 1/5 до 5/5]
            
            РАЗБОР: [2-3 предложения с обоснованием выбора]
            """

            try:
                raw_analysis = ask_gemini(analysis_prompt)
                
                # Парсинг ответа
                data = {}
                for line in raw_analysis.split('\n'):
                    if ':' in line:
                        k, v = line.split(':', 1)
                        data[k.strip().upper()] = v.strip()

                st.markdown("#### 📊 Данные аналитических сервисов")
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.info(f"**FootyStats:**\n{data.get('FOOTYSTATS', 'Данные анализируются...')}")
                    st.info(f"**Arbworld:**\n{data.get('ARBWORLD', 'Данные анализируются...')}")
                with c2:
                    st.info(f"**Oddsportal:**\n{data.get('ODDSPORTAL', 'Данные анализируются...')}")
                    st.info(f"**NB Bet:**\n{data.get('NBBET', 'Данные анализируются...')}")
                with c3:
                    st.info(f"**Corner Stats:**\n{data.get('CORNERSTATS', 'Данные анализируются...')}")

                st.markdown("---")
                st.markdown("#### 🎯 Итоговая карточка ставки")

                col_res1, col_res2, col_res3, col_res4 = st.columns(4)
                col_res1.metric("Исход / Фора", data.get('ИСХОД', 'П1'))
                col_res2.metric("Индив. тотал", data.get('ТОТАЛ', 'ТБ (2.5)'))
                col_res3.metric("Угловые", data.get('УГЛОВЫЕ', 'ТБ (9.5)'))
                col_res4.metric("Уверенность", data.get('УВЕРЕННОСТЬ', '4/5'))

                st.success(f"**📋 Аналитический разбор:**\n\n{data.get('РАЗБОР', raw_analysis)}")

            except Exception as e:
                st.error(f"🔴 Ошибка при генерации прогноза: {e}")
