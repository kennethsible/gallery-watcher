# Image Gallery Watcher & Downloader

**Gallery Watcher** is a [`gallery-dl`](https://github.com/mikf/gallery-dl) wrapper that uses [`apscheduler`](https://github.com/agronholm/apscheduler) to monitor galleries and download updates.

## Docker Compose

```yaml
services:
  gallery-watcher:
    build:
      context: .
    container_name: gallery-watcher
    user: ${PUID:-1000}:${PGID:-1000}
    environment:
      TZ: "America/New_York"
      CRON_SCHEDULE: "0 * * * *"
      ONCE_ON_STARTUP: "false"
      # DISCORD_WEBHOOK: ""
      # PUSHOVER_USER_KEY: ""
      # PUSHOVER_APP_TOKEN: ""
    volumes:
      - ./config:/config
      - ./downloads:/downloads
    restart: unless-stopped
```

## Example Configuration

```json
{
    "https://mangadex.org/title/":
    [
        "mangadex/Dandadan",
        {
            "68112dc1-2b80-4f20-beb8-2f2a8716a430": [
                "--chapter-filter",
                "1 <= chapter <= 5",
                "-o",
                "lang=en"
            ]
        }
    ]
}
```

> [!NOTE]
> The `/config` directory must include a `config.json` file and can optionally include a `gallery-dl.conf` file.
