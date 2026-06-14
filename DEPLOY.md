# Деплой на Railway

## Быстрый старт

1. Создай проект на [Railway](https://railway.app)
2. Подключи GitHub-репозиторий
3. Railway автоматически определит Dockerfile и соберёт образ

## Переменные окружения

В Settings → Variables добавь:

| Переменная | Описание | Пример |
|---|---|---|
| `BOT_TOKEN` | Токен Telegram бота | `123456:ABC...` |
| `DATABASE_URL` | PostgreSQL URL (Railway даёт автоматически) | `postgresql://...` |
| `CHECK_INTERVAL_MINUTES` | Интервал проверки цен | `30` |
| `FREE_LIMIT` | Лимит товаров для бесплатных | `3` |
| `PREMIUM_LIMIT` | Лимит товаров для премиум | `20` |

## PostgreSQL

Railway автоматически создаёт переменную `DATABASE_URL` когда добавляешь
плагин **PostgreSQL** в проект:

1. В левом меню проекта нажми **+ New**
2. Выбери **Database** → **PostgreSQL**
3. Переменная `DATABASE_URL` добавится автоматически

## Деплой

1. Запушь изменения в GitHub
2. Railway автоматически пересоберёт и задеплоит
3. Логи смотри во вкладке **Deployments**

## Автоперезапуск

Railway автоматически перезапускает контейнер при падении
(max 10 попыток).

## Локальная разработка

```bash
cp .env.example .env
# Заполни BOT_TOKEN и DATABASE_URL (можно использовать локальный PostgreSQL)
pip install -r requirements.txt
playwright install chromium
python -m src.bot
```

## Структура

```
price-tracker-bot/
├── Dockerfile           # Сборка образа
├── railway.json         # Конфиг Railway
├── requirements.txt     # Python зависимости
├── config/
│   └── settings.py      # Чтение ENV
├── src/
│   ├── bot.py           # Точка входа
│   ├── chart.py         # Графики цены
│   ├── database/db.py   # PostgreSQL (asyncpg)
│   ├── handlers/        # Хендлеры бота
│   ├── parsers/         # Парсеры маркетплейсов
│   └── scheduler/       # Фоновая проверка цен
└── .env.example         # Шаблон переменных
```
