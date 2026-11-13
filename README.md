# project_binance

Antrade is a Telegram bot for algorithmic spot trading on Binance. It fetches market data, lets users choose a trading strategy, pair, timeframe, and trade size, and can start or stop a trading session and close an open order.

## Run with Docker

Requirements: Docker with Compose, a Binance API key and secret, and a Telegram bot token and chat ID.

From the repository root:

```sh
cd "project binance/antrade-main"
```

Create a `.env` file in that directory:

```dotenv
API_KEY=your_binance_api_key
SECRET_KEY=your_binance_secret_key
CHAT_ID=your_telegram_chat_id
TELETOKEN=your_telegram_bot_token
```

Then start the bot:

```sh
docker compose up --build
```

Keep your API credentials and bot token private. Use Binance API permissions appropriate for your needs.

## License

This project is licensed under the BSD 3-Clause License; see [LICENSE](LICENSE).
