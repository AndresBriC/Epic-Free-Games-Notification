# Epic Games Free Games Notifier

A Python script that checks the Epic Games Store for current free games and sends them to a Discord webhook.

Runs weekly via GitHub Actions and avoids duplicate notifications across runs.

## Setup

```bash
pip install requests
export DISCORD_WEBHOOK="your_webhook_url"
python script.py