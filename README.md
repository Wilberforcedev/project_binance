# project_binance

Antrade is a Telegram bot for algorithmic Binance Spot trading, with SMA and WoodieCCI strategies.

## Features

- Binance Spot market data and account balance access.
- Selectable trading strategy, USDT pair, candle interval, and trade budget.
- Telegram controls to start or stop a session and request a manual sale.
- Owner-only message and button access.

## Run with Docker

Requirements: Docker with Compose, a Binance API key and secret, and a Telegram bot token and chat ID.

From the repository root:

```sh
cd "project binance/antrade-main"
cp .env.example .env
```

Edit `.env` with your credentials and numeric Telegram user ID in `TELEGRAM_ALLOWED_USER_ID`. In a private chat, `CHAT_ID` is usually the same as your user ID. Then start the bot:

```sh
docker compose up --build
```

The bot can place live trades on Binance. Keep credentials private and use API key permissions carefully; do not enable withdrawals.

## License

This project is licensed under the BSD 3-Clause License; see [LICENSE](LICENSE).
