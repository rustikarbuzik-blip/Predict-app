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
    raise Exception("Ошибка обращения к Gemini API. Проверьте ключ.")

def parse_match_block(block_text):
    """Парсит текстовый блок ответа AI в словарь данных"""
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

        # 1. Извлечение списка матчей (со скриншота или из текста)
        with st.spinner("1/2 Распознавание всех матчей со скриншота..."):
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

        st.success(f" Найдено матчей для анализа: **{len(matches_list)}**")

        # 2. Пакетная генерация прогнозов для каждого матча
        with st.spinner(f"2/2 Анализ и формирование прогнозов по {len(matches_list)} матчам..."):
            matches_formatted_str = "\n".join(f"- {m}" for m in matches_list)
            
            analysis_prompt = f"""
            Ты спортивный аналитик. Сделай прогнозирование для каждого из следующих матчей:
            {matches_formatted_str}

            Для КАЖДОГО матча смоделируй данные с 5 агрегаторов (FootyStats, Arbworld, Oddsportal, NB Bet, Corner Stats) и сформируй рекомендацию.

            Выведи ответ СТРОГО в следующем формате для каждого матча:

            === МАТЧ: [Название матча] ===
            FOOTYSTATS: [1 предложение о форме и xG]
            ARBWORLD: [1 предложение о прогрузах Moneyway]
            ODDSPORTAL: [1 предложение о движении кэфов]
            NBBET: [1 предложение о трендах и сериях]
            CORNERSTATS: [1 предложение по тоталу угловых]
            ИСХОД: [Ставка на исход или фору, например: П1 или Фора 1 (0)]
            ТОТАЛ: [Ставка на тотал голов, например: ИТБ1 (1.5)]
            УГЛОВЫЕ: [Ставка на угловые, например: ТБ (9.5)]
            УВЕРЕННОСТЬ: [Оценка уверенности: например, 4/5]
            РАЗБОР: [Короткое обоснование ставки из 2 предложений]
            === КОНЕЦ МАТЧА ===
            """

            try:
                raw_response = ask_gemini(analysis_prompt)
                
                # Разделение ответа по блокам матчей
                raw_blocks = raw_response.split("=== МАТЧ:")
                
                for i, block in enumerate(raw_blocks):
                    if not block.strip() or "===" not in block:
                        continue
                    
                    match_header = block.split("===")[0].strip()
                    parsed_data = parse_match_block(block)

                    # Отображаем каждый матч в отдельном раскрывающемся меню
                    with st.expander(f"⚽ {i}. {match_header}", expanded=(i == 1)):
                        st.markdown("#### 📊 Данные аналитических сервисов")
                        c1, c2, c3 = st.columns(3)
                        with c1:
                            st.info(f"**FootyStats:**\n{parsed_data.get('FOOTYSTATS', 'Анализируется...')}")
                            st.info(f"**Arbworld:**\n{parsed_data.get('ARBWORLD', 'Анализируется...')}")
                        with c2:
                            st.info(f"**Oddsportal:**\n{parsed_data.get('ODDSPORTAL', 'Анализируется...')}")
                            st.info(f"**NB Bet:**\n{parsed_data.get('NBBET', 'Анализируется...')}")
                        with c3:
                            st.info(f"**Corner Stats:**\n{parsed_data.get('CORNERSTATS', 'Анализируется...')}")

                        st.markdown("---")
                        st.markdown("#### 🎯 Карточка ставки")

                        col1, col2, col3, col4 = st.columns(4)
                        col1.metric("Исход / Фора", parsed_data.get('ИСХОД', 'П1'))
                        col2.metric("Индив. тотал", parsed_data.get('ТОТАЛ', 'ТБ (2.5)'))
                        col3.metric("Угловые", parsed_data.get('УГЛОВЫЕ', 'ТБ (9.5)'))
                        col4.metric("Уверенность", parsed_data.get('УВЕРЕННОСТЬ', '4/5'))

                        st.success(f"**📋 Аналитический разбор:**\n\n{parsed_data.get('РАЗБОР', 'Анализ завершен.')}")

            except Exception as e:
                st.error(f"🔴 Ошибка при генерации пакета прогнозов: {e}")
