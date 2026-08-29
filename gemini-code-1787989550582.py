import streamlit as st
from openai import OpenAI
import requests
import html
from datetime import datetime, timezone, timedelta
import sqlite3
import re

st.set_page_config(
    page_title="Match Analytics AI Pro", 
    page_icon="⚽", 
    layout="wide"
)

# Время по Уфе (UTC+5)
UFA_TZ = timezone(timedelta(hours=5))
now_ufa = datetime.now(UFA_TZ)

st.title("⚽ Автоматический генератор прогнозов")
st.caption(f"Время: **{now_ufa.strftime('%d.%m.%Y %H:%M')} (Уфа)** | Self-Contained AI Core")

# Ключи и настройки по умолчанию
vsegpt_key = st.secrets.get("VSEGPT_API_KEY", "")
default_tg_token = "8758421691:AAFfIvHR1g0ak2QejRqhNrpsy-DRXaHgTFU"
default_tg_chat_id = "500635733"
tg_token = st.secrets.get("TELEGRAM_BOT_TOKEN", default_tg_token)
tg_chat_id = st.secrets.get("TELEGRAM_CHAT_ID", default_tg_chat_id)

def escape_html(text):
    if not text:
        return ""
    return html.escape(str(text))

def split_teams(match_str: str):
    """Надежный внутренний разделитель команд"""
    cleaned = match_str.strip()
    for sep in [" — ", " – ", " - ", " vs ", " vs. ", " v ", " против ", "—", "–", "-"]:
        if sep in cleaned:
            parts = cleaned.split(sep, 1)
            t1, t2 = parts[0].strip(), parts[1].strip()
            if t1 and t2:
                return t1, t2
    words = cleaned.split()
    if len(words) == 2:
        return words[0], words[1]
    elif len(words) >= 4:
        mid = len(words) // 2
        return " ".join(words[:mid]), " ".join(words[mid:])
    return cleaned, "Соперник"

# ==============================================================================
# 🗄️ БАЗА ДАННЫХ SQLITE
# ==============================================================================

def init_db():
    conn = sqlite3.connect("match_history.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS history_v3 (
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
    cursor.execute("SELECT match, match_time_ufa, bet_main, ind_total, bet_aggressive, bet_cautious, best_pick, confidence, review, message_id, overall_status, status_main, status_ind_total, status_aggressive, status_cautious, status_best_pick, date FROM history_v3")
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
        INSERT INTO history_v3 (match, match_time_ufa, bet_main, ind_total, bet_aggressive, bet_cautious, best_pick, confidence, review, message_id, overall_status, status_main, status_ind_total, status_aggressive, status_cautious, status_best_pick, date)
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
    cursor.execute("DELETE FROM history_v3")
    for item in history_data:
        cursor.execute('''
            INSERT INTO history_v3 (match, match_time_ufa, bet_main, ind_total, bet_aggressive, bet_cautious, best_pick, confidence, review, message_id, overall_status, status_main, status_ind_total, status_aggressive, status_cautious, status_best_pick, date)
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
    input_vsegpt_key = st.text_input("VseGPT API Key:", value=vsegpt_key, type="password")
    selected_model = st.selectbox(
        "Модель:",
        options=[
            "google/gemini-2.5-flash-lite",
            "deepseek/deepseek-chat",
            "openai/gpt-4o-mini",
            "google/gemini-2.5-flash"
        ],
        index=0
    )
    if input_vsegpt_key:
        st.success("🟢 Подключено")
    else:
        st.warning("⚠️ Введите ключ")

    st.markdown("---")
    st.header("🤖 Telegram")
    input_tg_token = st.text_input("Bot Token:", value=tg_token, type="password")
    input_tg_chat_id = st.text_input("Chat ID:", value=tg_chat_id)

tab1, tab2 = st.tabs(["📝 Ввод и Анализ", "📋 История"])

# ==============================================================================
# 🧠 AI ВЫЗОВ С ЗАЩИТОЙ ОТ ПОВТОРОВ
# ==============================================================================

def ask_vsegpt(prompt):
    if not input_vsegpt_key:
        raise Exception("API ключ не указан!")
    client = OpenAI(api_key=input_vsegpt_key, base_url="https://api.vsegpt.ru/v1")
    
    # frequency_penalty принудительно запрещает модели штамповать одинаковые маркеты (ИТБ 1.5)
    response = client.chat.completions.create(
        model=selected_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        frequency_penalty=0.7,
        max_tokens=250
    )
    return response.choices[0].message.content

def sanitize_text(text: str) -> str:
    if not text:
        return "—"
    return text.replace("`", "").replace('"', '').replace("'", "").strip()

def parse_match_block(block_text):
    data = {}
    lines = block_text.split('\n')
    current_key = None
    for line in lines:
        l_clean = line.strip()
        if ':' in l_clean:
            parts = l_clean.split(':', 1)
            key = parts[0].strip().upper()
            if key in ['ВРЕМЯ_МАТЧА', 'СТАВКА', 'ИТ', 'БОЛЕЕ_АГРЕССИВНО', 'ОСТОРОЖНАЯ_СТАВКА', 'ЛУЧШАЯ_СТАВКА', 'УВЕРЕННОСТЬ', 'РАЗБОР']:
                current_key = key
                data[current_key] = sanitize_text(parts[1])
                continue
        if current_key == 'РАЗБОР' and l_clean:
            data[current_key] += " " + l_clean
    return data

def send_telegram_message(text, token, chat_id):
    if not token or not chat_id:
        return False, "Нет настроек Telegram", None
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text[:4000], "parse_mode": "HTML"}
    try:
        res = requests.post(url, json=payload, timeout=5)
        if res.status_code == 200:
            return True, "Успешно", res.json()["result"]["message_id"]
        return False, res.text, None
    except Exception as e:
        return False, str(e), None

def edit_telegram_message(token, chat_id, message_id, text):
    if not token or not chat_id or not message_id:
        return False
    url = f"https://api.telegram.org/bot{token}/editMessageText"
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text[:4000], "parse_mode": "HTML"}
    try:
        res = requests.post(url, json=payload, timeout=5)
        return res.status_code == 200
    except:
        return False

# ==============================================================================
# 📝 ВКЛАДКА 1: АНАЛИЗ
# ==============================================================================

with tab1:
    match_input = st.text_area(
        "Список матчей (каждый с новой строки):", 
        placeholder="Интер Майами - Монреаль\nСиэтл Саундерс - Чикаго Файр\nАрсенал - Челси",
        height=130
    )
    
    if st.button("🚀 Сформировать прогнозы и Экспресс", type="primary", use_container_width=True):
        matches = [m.strip() for m in match_input.strip().split("\n") if m.strip()]
        
        if not input_vsegpt_key:
            st.error("Укажите VseGPT API Key!")
        elif not matches:
            st.warning("Введите хотя бы один матч!")
        else:
            time_str = now_ufa.strftime('%d.%m.%Y %H:%M')
            st.success(f"Анализ матчей: {len(matches)}")
            express_items = []

            for i, match in enumerate(matches, 1):
                home, away = split_teams(match)
                with st.spinner(f"Анализ {i}/{len(matches)} ({home} — {away})..."):

                    prompt = f"""
                    Ты профессиональный каппер. Проанализируй матч:
                    Хозяева: {home} | Гости: {away}. Время: {time_str} (Уфа).

                    ПРАВИЛА АНАЛИЗА И МАРКЕТОВ:
                    1. Избегай шаблонов! Подбирай разные рынки в зависимости от силы клубов: используй ИТМ, ИТБ, форы (0, +1.5, -1), ТМ или ТБ индивидуально для каждого матча.
                    2. Запрещены сокращения П1/П2/ИТ1. Всегда пиши название команды.

                    ВЫДАЙ СТРОГО ПО ШАБЛОНУ:
                    ВРЕМЯ_МАТЧА: {time_str}
                    РАЗБОР: [2 предложения: анализ текущей формы и результативности]
                    СТАВКА: [{home} или {away} победа / фора]
                    ИТ: [{home} или {away} ИТБ/ИТМ с точным значением]
                    БОЛЕЕ_АГРЕССИВНО: [{home} или {away} с форой / победа + тотал / ОЗ]
                    ОСТОРОЖНАЯ_СТАВКА: [{home} 1X / {away} X2 / плюсовая фора / тотал]
                    ЛУЧШАЯ_СТАВКА: [Главный выбор каппера, строго из разбора]
                    УВЕРЕННОСТЬ: [⭐⭐⭐⭐ или ⭐⭐⭐⭐⭐]
                    """

                    try:
                        raw = ask_vsegpt(prompt)
                        data = parse_match_block(raw)

                        m_time = data.get('ВРЕМЯ_МАТЧА', time_str)
                        b_main = data.get('СТАВКА', f"{home} победа")
                        i_tot = data.get('ИТ', f"{home} ИТБ(1.0)")
                        b_agg = data.get('БОЛЕЕ_АГРЕССИВНО', f"{home} фора(-1)")
                        b_caut = data.get('ОСТОРОЖНАЯ_СТАВКА', f"{home} 1X")
                        b_best = data.get('ЛУЧШАЯ_СТАВКА', b_main)
                        conf = data.get('УВЕРЕННОСТЬ', '⭐⭐⭐⭐')
                        review = data.get('РАЗБОР', 'Анализ завершен.')

                        if conf.count('⭐') >= 5:
                            express_items.append({"match": f"{home} — {away}", "time": m_time, "pick": b_best, "conf": conf})

                        with st.expander(f"⚽ {i}. {home} — {away} | {m_time}", expanded=(i == 1)):
                            st.caption(f"Уверенность: {conf}")
                            st.markdown(f"🎯 **Ставка:** `{b_main}`")
                            st.markdown(f"⚽ **ИТ:** `{i_tot}`")
                            st.markdown(f"⚡ **Агрессивно:** `{b_agg}`")
                            st.markdown(f"🛡️ **Осторожно:** `{b_caut}`")
                            st.success(f"🔥 **Лучшая ставка:** `{b_best}`")
                            st.markdown(f"📋 **Разбор:**\n\n{review}")

                        tg_text = (
                            f"⚽ <b>Матч: {escape_html(home)} — {escape_html(away)}</b>\n"
                            f"🕒 <b>Начало:</b> <code>{escape_html(m_time)}</code>\n\n"
                            f"🎯 <b>Ставка:</b> <code>{escape_html(b_main)}</code> [⏳]\n"
                            f"⚽ <b>ИТ:</b> <code>{escape_html(i_tot)}</code> [⏳]\n"
                            f"⚡ <b>Агрессивно:</b> <code>{escape_html(b_agg)}</code> [⏳]\n"
                            f"🛡️ <b>Осторожно:</b> <code>{escape_html(b_caut)}</code> [⏳]\n"
                            f"🔥 <b>Лучшая ставка:</b> <code>{escape_html(b_best)}</code> [⏳]\n"
                            f"⭐ <b>Уверенность:</b> {conf}\n\n"
                            f"📝 <b>Разбор:</b>\n{escape_html(review)}"
                        )

                        success, _, msg_id = send_telegram_message(tg_text, input_tg_token, input_tg_chat_id)
                        if success and msg_id:
                            save_match_to_db({
                                "match": f"{home} — {away}", "match_time_ufa": m_time,
                                "bet_main": b_main, "ind_total": i_tot,
                                "bet_aggressive": b_agg, "bet_cautious": b_caut,
                                "best_pick": b_best, "confidence": conf,
                                "review": review, "message_id": msg_id,
                                "overall_status": "⏳ Ожидание",
                                "date": datetime.now().strftime("%Y-%m-%d %H:%M")
                            })
                    except Exception as e:
                        st.error(f"Ошибка по матчу {match}: {e}")

            if express_items:
                express_lines = [f"{idx}. <b>{escape_html(it['match'])}</b> — Выбор: <code>{escape_html(it['pick'])}</code>" for idx, it in enumerate(express_items, 1)]
                express_text = "🔥 <b>ТОП-ЭКСПРЕСС ДНЯ (⭐⭐⭐⭐⭐)</b> 🔥\n\n" + "\n".join(express_lines)
                send_telegram_message(express_text, input_tg_token, input_tg_chat_id)
                st.success("🔥 Экспресс дня отправлен в Telegram!")

# ==============================================================================
# 📋 ВКЛАДКА 2: ИСТОРИЯ
# ==============================================================================

with tab2:
    st.subheader("📊 История и статусы")
    history = load_history()
    if not history:
        st.info("История пуста.")
    else:
        for h in reversed(history):
            with st.expander(f"{h['overall_status']} | {h['match']}"):
                st.write(f"**Ставка:** {h['bet_main']} [{h.get('status_main', '⏳')}]")
                st.write(f"**ИТ:** {h['bet_aggressive']}")
                st.markdown(f"**Разбор:**\n\n{h['review']}")
