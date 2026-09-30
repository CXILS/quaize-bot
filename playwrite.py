# ============================================================
#  Бот-автоответчик для Quaize
#  Читает вопрос → отправляет в GigaChat → отвечает сам
#  Поддерживает: варианты, текстовый ввод, картинки
# ============================================================

from PIL import Image
import os
import re
import random
import logging
import requests
from datetime import datetime
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole

CHROMIUM_PATH = "/data/data/com.termux/files/usr/bin/chromium-browser"

load_dotenv()


# ------------------------------------------------------------
#  НАСТРОЙКА ЛОГИРОВАНИЯ
# ------------------------------------------------------------
log_filename = f"bot_log_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.txt"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        #logging.FileHandler(log_filename, encoding="utf-8"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


# ------------------------------------------------------------
#  НАСТРОЙКИ — при необходимости меняй только тут
# ------------------------------------------------------------
QUESTION_SELECTOR      = "p.text-xl.font-medium"
OPTIONS_SELECTOR       = ".answer-tile"
INPUT_SELECTOR         = "input[data-slot='input-group-control'], textarea"
SUBMIT_BUTTON_SELECTOR = "button[data-slot='button'][type='submit']"
IMAGE_SELECTOR         = "img[src*='uploads.quaize.ru']"
GAME_URL               = "https://quaize.ru/join/330717"   # ← твоя ссылка

VISION_MODEL           = "GigaChat-2-Pro"   # модель со зрением
TEXT_MODEL             = "GigaChat-2"       # текстовая модель


# ============================================================
#  ФУНКЦИЯ: спрашиваем GigaChat по тексту
# ============================================================
def ask_ai(question, options):
    print("🔥 ask_ai ВЫЗВАНА")
    auth_key = os.getenv("GIGACHAT_AUTH_KEY")
    if not auth_key:
        raise ValueError("Не найден GIGACHAT_AUTH_KEY в файле .env")

    system_prompt = (
        "Ты — эксперт, который отвечает на вопросы русскоязычной викторины. "
        "Ты ВСЕГДА отвечаешь ТОЛЬКО НА РУССКОМ ЯЗЫКЕ. "
        "Ты даёшь ТОЧНЫЙ термин, а не описание процесса. "
        "Если у термина есть синонимы — перечисляешь их через запятую. "
        "Ты никогда не пишешь пояснений, номеров, переводов или лишних слов."
    )

    if options:
        user_prompt = (
            f"Вопрос викторины: {question}\n\n"
            f"Возможные варианты ответа:\n"
            + "\n".join(f"- {o}" for o in options) + "\n\n"
            f"Правильный ответ — ровно один из этих вариантов.\n"
            f"Скопируй его текст ДОСЛОВНО, символ в символ.\n"
            f"НЕ придумывай свой ответ, даже если кажется, что правильный вариант отсутствует.\n"
            f"Ответ:"
        )
    else:
        user_prompt = (
            f"Ты отвечаешь на вопрос русскоязычной викторины.\n"
            f"ОБЯЗАТЕЛЬНО пиши ответ ТОЛЬКО НА РУССКОМ ЯЗЫКЕ.\n\n"
            f"ПРАВИЛА ОТВЕТА:\n"
            f"1. Пиши ТОЧНЫЙ научный термин или факт, а не описание.\n"
            f"2. Если возможно — используй ОДНО СЛОВО или короткий термин.\n"
            f"3. Если у термина есть синонимы — перечисли их через запятую.\n"
            f"4. НЕ пиши общих фраз — пиши конкретный термин.\n"
            f"5. Никаких пояснений, переводов, английских слов, кавычек и точек.\n\n"
            f"Вопрос: {question}\n\n"
            f"Ответ (точный термин на русском):"
        )

    try:
        print("📡 Отправляю запрос в GigaChat...")
        with GigaChat(
            base_url="https://api.giga.chat/v1",
            credentials=auth_key,
            scope="GIGACHAT_API_PERS",
            verify_ssl_certs=False,
            timeout=60
        ) as client:
            chat = Chat(
                model=TEXT_MODEL,
                messages=[
                    Messages(role=MessagesRole.SYSTEM, content=system_prompt),
                    Messages(role=MessagesRole.USER,   content=user_prompt)
                ],
                temperature=0.1
            )
            print("⏳ Жду ответа от модели...")
            response = client.chat(chat)
            print("📥 Ответ получен!")

            answer = response.choices[0].message.content.strip()
            answer = answer.strip(' "\'.,!?').strip()
            print(f"📝 Ответ: {answer}")
            return answer

    except Exception as e:
        print(f"❌ Ошибка при запросе к GigaChat: {type(e).__name__}: {e}")
        return None


# ============================================================
#  Скачиваем картинку вопроса по URL
# ============================================================
def download_image(page, save_path="question_image.png"):
    """Скачивает картинку вопроса и конвертирует её в PNG (GigaChat не принимает webp)."""
    try:
        img = page.locator(IMAGE_SELECTOR).first
        img_url = img.get_attribute("src")

        if not img_url:
            return False

        print(f"🖼️ Найдена картинка: {img_url[:80]}...")
        response = requests.get(img_url, timeout=15)
        response.raise_for_status()

        # Сначала сохраняем как есть (webp)
        temp_path = "question_image_raw.webp"
        with open(temp_path, "wb") as f:
            f.write(response.content)

        # Конвертируем в PNG
        img = Image.open(temp_path).convert("RGB")
        img.save(save_path, "PNG")
        print(f"💾 Картинка сохранена как PNG: {save_path}")
        return True

    except Exception as e:
        print(f"⚠️ Не удалось скачать/конвертировать картинку: {e}")
        return False


# ============================================================
#  Спрашиваем GigaChat про картинку + текст
# ============================================================
def ask_ai_about_image(image_path, question, options=None):
    auth_key = os.getenv("GIGACHAT_AUTH_KEY")
    if not auth_key:
        raise ValueError("Не найден GIGACHAT_AUTH_KEY")

    options = options or []

    try:
        print("📡 Загружаю картинку в GigaChat...")
        with GigaChat(
            base_url="https://api.giga.chat/v1",
            credentials=auth_key,
            scope="GIGACHAT_API_PERS",
            verify_ssl_certs=False,
            timeout=60
        ) as client:
            with open(image_path, "rb") as f:
                uploaded = client.upload_file(f, purpose="general")
            file_id = uploaded.id_ if hasattr(uploaded, "id_") else uploaded.id
            print(f"📤 Файл загружен, ID: {file_id}")

            if options:
                options_block = (
                    "\n\nВАРИАНТЫ ОТВЕТА (выбери РОВНО ОДИН и скопируй его ТОЧНО):\n"
                    + "\n".join(f"{i+1}. {o}" for i, o in enumerate(options))
                )
                rules = (
                    "ИНСТРУКЦИЯ (выполняй ПО ШАГАМ):\n"
                    "ШАГ 1. Прочитай текст вопроса выше. Это главное.\n"
                    "ШАГ 2. Посмотри на картинку — она лишь ПОМОГАЕТ, но не заменяет текст.\n"
                    "ШАГ 3. Выбери ОДИН вариант из списка, который ТОЧНО отвечает на вопрос.\n"
                    "ШАГ 4. Напиши ТОЛЬКО текст выбранного варианта, символ в символ.\n\n"
                    "ЗАПРЕЩЕНО: придумывать свой ответ, писать пояснения, "
                    "отвечать по картинке в обход текста."
                )
            else:
                options_block = ""
                rules = (
                    "Пиши ТОЧНЫЙ ответ (одно слово или короткий термин) на русском языке. "
                    "Без пояснений и английских слов."
                )

            prompt = (
                f"Вопрос викторины:\n{question}{options_block}\n\n"
                f"{rules}\n"
                f"Ответ:"
            )

            chat = Chat(
                model=VISION_MODEL,
                messages=[
                    Messages(
                        role=MessagesRole.USER,
                        content=prompt,
                        attachments=[file_id]
                    )
                ],
                temperature=0.1
            )

            print("⏳ Жду ответа от модели...")
            response = client.chat(chat)
            print("📥 Ответ получен!")

            answer = response.choices[0].message.content.strip()
            answer = answer.strip(' "\'.,!?').strip()
            print(f"📝 Ответ по картинке: {answer}")
            return answer

    except Exception as e:
        print(f"❌ Ошибка при работе с картинкой: {type(e).__name__}: {e}")
        return None


# ============================================================
#  Проверяем, правильный ли был ответ
# ============================================================
def check_answer_result(page):
    try:
        page.wait_for_function(
            """() => {
                const text = document.body.innerText;
                return text.includes('Неверно') ||
                       text.includes('Верно') ||
                       text.includes('Правильный ответ') ||
                       text.includes('Идеальный результат');
            }""",
            timeout=3000
        )

        body_text = page.locator("body").inner_text()

        if "Неверно" in body_text or "Правильный ответ" in body_text:
            return False
        elif "Верно" in body_text or "Идеальный результат" in body_text:
            return True
        else:
            return None
    except Exception:
        return None

def question_needs_image(question):
    """Проверяет, относится ли вопрос к картинке."""
    q = question.lower()
    markers = [
        "что изображено", "что на картинке", "что на рисунке", "что на фото",
        "какой объект", "какое изображение", "кто изображён", "кто изображен",
        "на картинке", "на рисунке", "на фото", "на изображении",
        "изображено", "изображён", "изображен", "показано", "изображение",
        "определи", "узнай", "найди на картинке"
    ]
    return any(m in q for m in markers)

# ============================================================
#  ОСНОВНАЯ ФУНКЦИЯ
# ============================================================
def main():
    logger.info("=" * 60)
    logger.info("🚀 Бот запущен")
    logger.info(f"🎮 Игра: {GAME_URL}")
    logger.info(f"📁 Лог-файл: {log_filename}")
    logger.info("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executablePath=CHROMIUM_PATH,
            args=["--no-sandbox", "--disable-gpu"]
        )
        page = browser.new_page()
        page.goto(GAME_URL)

        question_number = 0
        prev_question = ""
        total_answered = 0
        total_correct = 0

        while True:
            try:
                logger.info("")
                logger.info("=" * 50)
                logger.info(f"⏳ Ждём НОВЫЙ вопрос №{question_number + 1}...")
                logger.info("=" * 50)

                # 1. Ждём НОВЫЙ вопрос
                page.wait_for_function(
                    """(prevText) => {
                        const el = document.querySelector('%s');
                        if (!el) return false;
                        const t = el.innerText.trim();
                        return t.length > 5 && t !== prevText;
                    }""" % QUESTION_SELECTOR,
                    arg=prev_question,
                    timeout=120000
                )

                # 2. Ищем самый длинный текст с "?"
                candidates = []
                for el in page.locator(QUESTION_SELECTOR).all():
                    text = el.inner_text().strip()
                    if text.endswith("?"):
                        candidates.append(text)

                if candidates:
                    question = max(candidates, key=len)
                else:
                    all_texts = [el.inner_text().strip() for el in page.locator(QUESTION_SELECTOR).all()]
                    question = max(all_texts, key=len) if all_texts else None

                if not question:
                    logger.warning("⚠️ Вопрос не найден, ждём следующий...")
                    page.wait_for_timeout(2000)
                    continue

                prev_question = question
                question_number += 1
                logger.info(f"📖 Вопрос №{question_number}: {question}")

                # 3. Ждём появления вариантов ИЛИ поля ввода
                logger.info("⏳ Ждём варианты или поле ввода...")
                try:
                    page.wait_for_function(
                        """() => {
                            const tiles = document.querySelectorAll('.answer-tile').length;
                            const inputs = document.querySelectorAll(
                                "input[data-slot='input-group-control'], textarea").length;
                            return tiles > 0 || inputs > 0;
                        }""",
                        timeout=5000
                    )
                except Exception:
                    pass

                has_options = page.locator(OPTIONS_SELECTOR).count() > 0
                has_input = page.locator(INPUT_SELECTOR).count() > 0
                has_image_element = page.locator(IMAGE_SELECTOR).count() > 0
                has_image = has_image_element and question_needs_image(question)
                
                if has_image_element and not has_image:
                    logger.info("🖼️ Картинка есть, но вопрос НЕ про неё — игнорируем.")
                elif has_image:
                    logger.info("🖼️ Вопрос ПРО картинку — будем её смотреть.")

                logger.info(f"🔎 Плиток: {page.locator(OPTIONS_SELECTOR).count()}, "
                            f"полей ввода: {page.locator(INPUT_SELECTOR).count()}, "
                            f"картинок: {page.locator(IMAGE_SELECTOR).count()}")

                # ============================================
                #  СЛУЧАЙ A: вопрос с вариантами
                # ============================================
                if has_options:
                    logger.info("🅰️ Вопрос с вариантами — кликаем сами.")

                    options = []
                    for el in page.locator(OPTIONS_SELECTOR).all():
                        text = el.inner_text().strip()
                        text = " ".join(text.split())
                        options.append(text)

                    logger.info(f"🔍 Найдено вариантов: {len(options)}")
                    for i, opt in enumerate(options):
                        logger.info(f"    {i+1}. {opt}")

                    delay = 0
                    logger.info(f"⏱️ Пауза {delay:.1f} сек...")
                    page.wait_for_timeout(int(delay * 1000))

                    # Спрашиваем ИИ (с картинкой или без)
                    if has_image:
                        logger.info("🖼️ Спрашиваем ИИ про картинку...")
                        download_image(page, "question_image.png")

                        ai_answer = None
                        for attempt in range(2):
                            ai_answer = ask_ai_about_image("question_image.png", question, options)
                            if ai_answer:
                                break
                            logger.warning(f"⚠️ Пустой ответ, попытка {attempt + 1}/2...")
                            page.wait_for_timeout(1000)

                        # Если ответ не среди вариантов — спрашиваем БЕЗ картинки
                        if ai_answer and options:
                            ai_lower = ai_answer.lower().strip()
                            found = any(
                                ai_lower in o.lower() or o.lower() in ai_lower
                                for o in options
                            )
                            if not found:
                                logger.warning(f"⚠️ Ответ '{ai_answer}' не найден среди вариантов.")
                                logger.info("🔄 Пробуем БЕЗ картинки — по тексту...")
                                ai_answer = ask_ai(question, options)
                                logger.info(f"🤖 Ответ по тексту: {ai_answer}")
                    else:
                        ai_answer = ask_ai(question, options)

                    logger.info(f"🤖 ИИ говорит: {ai_answer}")

                    if not ai_answer:
                        logger.warning("⚠️ GigaChat не ответил, кликаем случайно.")
                        random.choice(page.locator(OPTIONS_SELECTOR).all()).click()
                        total_answered += 1
                        page.wait_for_timeout(2000)
                        continue

                    # Ищем совпадение
                    ai_lower = ai_answer.lower().strip()
                    matching_option = None
                    matching_text = ""

                    for option in page.locator(OPTIONS_SELECTOR).all():
                        option_text = option.inner_text().strip()
                        option_lower = option_text.lower().strip()
                        if ai_lower == option_lower or \
                           ai_lower in option_lower or \
                           option_lower in ai_lower:
                            matching_option = option
                            matching_text = option_text
                            break

                    if matching_option:
                        matching_option.click()
                        logger.info(f"✅ Кликнули по варианту: {matching_text}")
                    else:
                        logger.warning(f"⚠️ Ответ '{ai_answer}' не найден среди вариантов!")
                        logger.warning("🎲 Отвечаем случайно.")
                        random.choice(page.locator(OPTIONS_SELECTOR).all()).click()

                    # Проверяем результат
                    total_answered += 1
                    result = check_answer_result(page)
                    if result is True:
                        total_correct += 1
                        logger.info(f"✅ Правильно! Счёт: {total_correct}/{total_answered}")
                    elif result is False:
                        logger.info(f"❌ Неправильно. Счёт: {total_correct}/{total_answered}")
                    else:
                        logger.info(f"❓ Результат не определён. Счёт: {total_correct}/{total_answered}")

                # ============================================
                #  СЛУЧАЙ B: вопрос с текстовым вводом
                # ============================================
                elif has_input:
                    logger.info("🅱️ Вопрос с текстовым вводом — вводим ответ сами.")

                    if has_image:
                        logger.info("🖼️ Спрашиваем ИИ про картинку (ввод)...")
                        download_image(page, "question_image.png")
                        ai_answer = ask_ai_about_image("question_image.png", question, [])
                    else:
                        ai_answer = ask_ai(question, [])

                    logger.info(f"🤖 ИИ говорит: {ai_answer}")

                    if not ai_answer:
                        logger.warning("⚠️ GigaChat не ответил, пропускаем.")
                        page.wait_for_timeout(5000)
                        continue

                    ai_answer = ai_answer.strip().strip('"\'').strip()
                    logger.info(f"📝 Вводим в поле: {ai_answer}")

                    delay = 0
                    logger.info(f"⏱️ Пауза {delay:.1f} сек...")
                    page.wait_for_timeout(int(delay * 1000))

                    input_field = page.locator(INPUT_SELECTOR).first
                    input_field.click()
                    input_field.fill(ai_answer)
                    logger.info("✍️ Ответ введён в поле.")
                    page.wait_for_timeout(500)

                    try:
                        submit_btn = page.locator(SUBMIT_BUTTON_SELECTOR).first
                        submit_btn.click()
                        logger.info("✅ Нажали кнопку «Продолжить».")
                    except Exception as e:
                        logger.warning(f"⚠️ Не нашли кнопку: {e}")
                        page.wait_for_timeout(10000)

                    # Проверяем результат
                    total_answered += 1
                    result = check_answer_result(page)
                    if result is True:
                        total_correct += 1
                        logger.info(f"✅ Правильно! Счёт: {total_correct}/{total_answered}")
                    elif result is False:
                        logger.info(f"❌ Неправильно. Счёт: {total_correct}/{total_answered}")
                    else:
                        logger.info(f"❓ Результат не определён. Счёт: {total_correct}/{total_answered}")

                # ============================================
                #  СЛУЧАЙ C: ничего не нашли
                # ============================================
                else:
                    logger.warning("⚠️ Ни плиток, ни поля ввода не найдено. Ждём 5 сек.")
                    page.wait_for_timeout(5000)

                logger.info("⏸️ Ждём следующий вопрос...")
                page.wait_for_timeout(1000)

            except Exception as e:
                logger.info("")
                logger.info("=" * 60)
                logger.info(f"🏁 Цикл завершён: {type(e).__name__}: {e}")
                logger.info(f"📊 Всего отвечено вопросов: {question_number}")
                logger.info("")
                logger.info("📈 ИТОГОВАЯ СТАТИСТИКА:")
                logger.info(f"   ✅ Правильных: {total_correct}")
                logger.info(f"   ❌ Неправильных: {total_answered - total_correct}")
                if total_answered > 0:
                    percent = round(total_correct / total_answered * 100, 1)
                    logger.info(f"   🎯 Точность: {percent}%")
                else:
                    logger.info("   🎯 Точность: нет данных")
                logger.info("=" * 60)
                break

        logger.info("👋 Закрываем браузер.")
        browser.close()


if __name__ == "__main__":
    main()
