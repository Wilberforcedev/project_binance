# project_binance

Antrade is a Telegram bot for algorithmic spot trading on Binance.

## Features

- Binance Spot market data and account balance access.
- Trading strategy options: Test, SMA, and WoodieCCI.
- Selectable USDT trading pairs, candle intervals, and trade budget.
- Telegram controls to start or stop a session and request a manual sale.

## Run with Docker

Requirements: Docker with Compose, a Binance API key and secret, and a Telegram bot token and chat ID.

From the repository root:

```sh
cd "project binance/antrade-main"
cp .env.example .env
```

Edit `.env` with your credentials, then start the bot:

```sh
docker compose up --build
```

The bot can place live trades on Binance. Keep credentials private and use API key permissions carefully; do not enable withdrawals.

## License

This project is licensed under the BSD 3-Clause License; see [LICENSE](LICENSE).
