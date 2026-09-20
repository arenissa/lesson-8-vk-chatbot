import os
import sys
import random
import logging
import traceback
from dotenv import load_dotenv
from openai import OpenAI
import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType

load_dotenv()

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ProxyAPI
PROXY_API_KEY = os.getenv("PROXY_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
PROXY_API_BASE_URL = "https://api.proxyapi.ru/openai/v1"

# VK
VK_TOKEN = os.getenv("VK_TOKEN")
VK_GROUP_ID = os.getenv("VK_GROUP_ID")

# Загружаем базу знаний из файла
KNOWLEDGE_BASE_PATH = os.path.join(os.path.dirname(__file__), "knowledge_base.md")
try:
    with open(KNOWLEDGE_BASE_PATH, "r", encoding="utf-8") as f:
        KNOWLEDGE_BASE = f.read()
    logger.info("Knowledge base loaded successfully")
except Exception as e:
    logger.error(f"Failed to load knowledge base: {e}")
    KNOWLEDGE_BASE = ""

SYSTEM_PROMPT = f"""Ты — Алина, доброжелательная девушка-консультант онлайн-университета Зерокодер (zerocoder.ru).
Твоя задача — консультировать клиентов по курсам и направлениям обучения университета.

ОБЯЗАТЕЛЬНЫЕ ПРАВИЛА:
1. Ты говоришь ТОЛЬКО в женском роде (я помогаю, я расскажу, я рекомендую).
2. Твое имя — Алина. Представляйся при первом обращении.
3. Ты НЕ отходишь от темы разговора. Отвечаешь ТОЛЬКО по направлениям и курсам Зерокодер.
4. Если вопрос не связан с обучением в Зерокодер — вежливо перенаправляй на тему курсов.
5. В конце каждого диалога предложи заполнить форму для связи с отделом продаж.

ИСПОЛЬЗУЙ СЛЕДУЮЩУЮ БАЗУ ЗНАНИЙ ДЛЯ ОТВЕТОВ:
{KNOWLEDGE_BASE}

СТИЛЬ: Дружелюбный, профессиональный тон. Обращение «вы». Называй актуальные цены и детали из базы знаний."""


def main():
    logger.info("=== Bot starting ===")
    logger.info(f"VK_GROUP_ID: {VK_GROUP_ID}")
    logger.info(f"PROXY_API_KEY set: {bool(PROXY_API_KEY)}")
    logger.info(f"VK_TOKEN set: {bool(VK_TOKEN)}")
    logger.info(f"Model: {OPENAI_MODEL}")

    if not all([PROXY_API_KEY, VK_TOKEN, VK_GROUP_ID]):
        logger.error("Missing env variables!")
        return

    # Инициализация OpenAI клиента через ProxyAPI
    client = OpenAI(
        api_key=PROXY_API_KEY,
        base_url=PROXY_API_BASE_URL,
    )

    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk = vk_session.get_api()

    try:
        result = vk.groups.getById(group_id=int(VK_GROUP_ID))
        logger.info(f"VK OK. Group: {result[0]['name']}")
    except Exception as e:
        logger.error(f"VK FAILED: {e}")
        return

    conversation_history = {}
    longpoll = VkBotLongPoll(vk_session, int(VK_GROUP_ID))
    logger.info("Listening for messages...")

    for event in longpoll.listen():
        try:
            if event.type != VkBotEventType.MESSAGE_NEW:
                continue

            user_id = event.message["from_id"]
            text = event.message.get("text", "")
            logger.info(f">>> From {user_id}: {text}")

            if user_id not in conversation_history:
                conversation_history[user_id] = []
            history = conversation_history[user_id]
            text_lower = text.strip().lower()

            if text_lower in ("/start", "начать", "привет", "здравствуйте", "здравствуй"):
                history.clear()
                reply = (
                    "Привет! Я Алина, консультант онлайн-университета Зерокодер.\n\n"
                    "Я помогу вам выбрать курс по нейросетям, zero-code разработке или аналитике данных.\n\n"
                    "Расскажите, что вас интересует!"
                )
            elif text_lower in ("/help", "помощь"):
                reply = (
                    "Я могу рассказать вам о курсах Зерокодер:\n"
                    "• Нейросети и ИИ\n"
                    "• Zero-code разработка (Bubble, Flutter Flow)\n"
                    "• Аналитика данных\n"
                    "• Бесплатные мероприятия\n\n"
                    "Просто спросите!"
                )
            elif text_lower in ("/reset", "сброс"):
                history.clear()
                reply = "Диалог сброшен. Чем могу помочь?"
            else:
                history.append({"role": "user", "content": text})
                messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history[-10:]
                try:
                    response = client.chat.completions.create(
                        model=OPENAI_MODEL,
                        messages=messages,
                    )
                    reply = response.choices[0].message.content
                    history.append({"role": "assistant", "content": reply})
                    if len(history) > 20:
                        conversation_history[user_id] = history[-20:]
                except Exception as e:
                    logger.error(f"OpenAI/ProxyAPI error: {e}\n{traceback.format_exc()}")
                    reply = "Извини, технические сложности. Попробуй ещё раз через минуту."

            logger.info(f"<<< To {user_id}: {reply[:80]}...")
            vk.messages.send(
                user_id=user_id,
                message=reply,
                random_id=random.randint(1, 2**31),
            )
            logger.info("Sent OK")

        except Exception as e:
            logger.error(f"Event error: {e}\n{traceback.format_exc()}")


if __name__ == "__main__":
    main()
