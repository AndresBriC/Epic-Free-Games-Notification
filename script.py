import requests
import sqlite3
import os
from datetime import datetime, timezone

DISCORD_WEBHOOK = os.environ["DISCORD_WEBHOOK"]
EPIC_API = "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"
DB_FILE = "games.db"


# ---------- DATABASE ----------


def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sent_games (
        game_id TEXT,
        title TEXT,
        start_date TEXT,
        PRIMARY KEY (game_id, start_date)
    )
    """)

    conn.commit()
    conn.close()


def is_already_sent(game_id, start_date):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT 1 FROM sent_games WHERE game_id=? AND start_date=?",
        (game_id, start_date),
    )

    result = cursor.fetchone()
    conn.close()

    return result is not None


def mark_as_sent(game_id, title, start_date):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute(
        "INSERT OR IGNORE INTO sent_games VALUES (?, ?, ?)",
        (game_id, title, start_date),
    )

    conn.commit()
    conn.close()


# ---------- FETCHING ----------


def get_free_games():
    response = requests.get(EPIC_API)
    data = response.json()

    games = data["data"]["Catalog"]["searchStore"]["elements"]
    now = datetime.now(timezone.utc)

    free_games = []

    for game in games:
        promotions = game.get("promotions")
        if not promotions:
            continue

        price_info = game.get("price", {}).get("totalPrice", {})
        discount_price = price_info.get("discountPrice", -1)
        original_price = price_info.get("originalPrice", 0)

        # Must actually be free
        if discount_price != 0 or original_price == 0:
            continue

        offers = promotions.get("promotionalOffers", [])
        if not offers:
            continue

        for offer_group in offers:
            print(offer_group)
            for offer in offer_group.get("promotionalOffers", []):
                try:
                    start = datetime.fromisoformat(
                        offer["startDate"].replace("Z", "+00:00")
                    )
                    end = datetime.fromisoformat(
                        offer["endDate"].replace("Z", "+00:00")
                    )
                except Exception:
                    # Skip malformed dates
                    continue

                if not (start <= now <= end):
                    continue

                game_id = game.get("id")
                slug = game.get("productSlug")

                # Fallback to alternative mappings
                if not slug:
                    mappings = game.get("catalogNs", {}).get("mappings", [])
                    if mappings:
                        slug = mappings[0].get("pageSlug")

                if not game_id:
                    continue  # still required for deduplication

                image = None
                if game.get("keyImages"):
                    image = game["keyImages"][0].get("url")

                url = f"https://store.epicgames.com/en-US/p/{slug}" if slug else None

                free_games.append(
                    {
                        "id": game_id,
                        "title": game["title"],
                        "url": url,
                        "image": image,
                        "start_date": start.isoformat(),
                    }
                )

    return free_games


# ---------- LOGGING ----------


def log(msg):
    print(f"[EPIC BOT][{datetime.utcnow().isoformat()}] {msg}")


def send_heartbeat():
    requests.post(
        DISCORD_WEBHOOK,
        json={"content": "✅ Checked Epic Store — no new free games this week."},
    )


# ---------- DISCORD ----------


def build_embed(game):
    return {
        "title": game["title"],
        "url": game["url"],
        "description": "Free on Epic Games Store 🎮",
        "image": {"url": game["image"]} if game["image"] else {},
        "footer": {"text": "Claim before it expires!"},
    }


def send_to_discord(games):
    if not games:
        requests.post(
            DISCORD_WEBHOOK,
            json={"content": "✅ Checked Epic Store — no new free games."},
        )
        return

    embeds = [build_embed(g) for g in games]

    payload = {"content": "🆓 **New Free Games on Epic Store!**", "embeds": embeds}

    response = requests.post(DISCORD_WEBHOOK, json=payload)

    if response.status_code != 204:
        log(f"Embed failed: {response.status_code}")
        log("Falling back to text")

        text = "\n\n".join(
            [f"{g['title']}\n{g['url'] or 'No link available'}" for g in games]
        )

        fallback_payload = {
            "content": f"⚠️ Could not send embeds, showing plain text:\n\n{text}"
        }

        fallback_response = requests.post(DISCORD_WEBHOOK, json=fallback_payload)

        if fallback_response.status_code != 204:
            print(
                f"Fallback ALSO failed: {fallback_response.status_code} {fallback_response.text}"
            )


# ---------- MAIN FLOW ----------


def main():
    log("=== START RUN ===")

    init_db()

    games = get_free_games()
    log(f"Fetched {len(games)} games")

    new_games = []

    for game in games:
        game_id = game["id"]
        start_date = game["start_date"]
        title = game["title"]

        if is_already_sent(game_id, start_date):
            log(f"Skipping duplicate: {title}")
            continue

        log(f"New game detected: {title}")
        new_games.append(game)
        mark_as_sent(game_id, title, start_date)

    log(f"Summary → New: {len(new_games)}, Total checked: {len(games)}")

    if new_games:
        send_to_discord(new_games)
    else:
        log("No new games found")
        send_heartbeat()  # optional


if __name__ == "__main__":
    main()
