import asyncio
import json
import logging
import os
import shutil
import signal
import subprocess
import tempfile
import zipfile
from importlib.metadata import version
from pathlib import Path

import rarfile
import requests
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

__version__ = 'v1.0.0'

logger = logging.getLogger('gallery-watcher')

DISCORD_WEBHOOK = os.getenv('DISCORD_WEBHOOK')
PUSHOVER_USER_KEY = os.getenv('PUSHOVER_USER_KEY')
PUSHOVER_APP_TOKEN = os.getenv('PUSHOVER_APP_TOKEN')
ONCE_ON_STARTUP = os.getenv('ONCE_ON_STARTUP', 'false').lower() in ('true', '1', 't')

CRON_MACROS = {
    '@yearly': '0 0 1 1 *',
    '@annually': '0 0 1 1 *',
    '@monthly': '0 0 1 * *',
    '@weekly': '0 0 * * 0',
    '@daily': '0 0 * * *',
    '@midnight': '0 0 * * *',
    '@hourly': '0 * * * *',
}
CRON_SCHEDULE = os.getenv('CRON_SCHEDULE')


def notify_discord(message: str, gallery: str, webhook_url: str) -> None:
    message = f'{message} from\n**{gallery}**'
    data = {'embeds': [{'description': message, 'color': 1146986}]}
    result = requests.post(webhook_url, json=data)
    try:
        result.raise_for_status()
    except requests.exceptions.HTTPError as e:
        logger.error(f'upstream connection failed to Discord: {e}')


def notify_pushover(message: str, gallery: str, user_key: str, app_token: str) -> None:
    message = f'{message} from<br><b>{gallery}</b>'
    data = {'message': message, 'html': 1, 'token': app_token, 'user': user_key}
    result = requests.post('https://api.pushover.net/1/messages.json', json=data)
    try:
        result.raise_for_status()
    except requests.exceptions.HTTPError as e:
        logger.error(f'upstream connection failed to Pushover: {e}')


def extract_archives(gallery_path: Path) -> None:
    for archive in gallery_path.iterdir():
        if not archive.is_file():
            continue
        if archive.suffix not in ('.zip', '.rar'):
            continue

        archive_stats = archive.stat()
        archive_mtime = archive_stats.st_mtime

        with tempfile.TemporaryDirectory() as tmp_f:
            temp_path = Path(tmp_f)
            if archive.suffix == '.zip':
                with zipfile.ZipFile(archive) as zip_f:
                    zip_f.extractall(temp_path)
            elif archive.suffix == '.rar':
                with rarfile.RarFile(archive) as rar_f:
                    rar_f.extractall(temp_path)

            for old_path in temp_path.rglob('*'):
                new_path = gallery_path / f'{archive.stem}_{old_path.name}'

                i = 1
                while new_path.is_file():
                    unique_suffix = f'({i}){old_path.suffix}'
                    new_path = gallery_path / f'{archive.stem}_{old_path.name} {unique_suffix}'
                    i += 1

                shutil.move(old_path, new_path)
                os.utime(new_path, (archive_mtime, archive_mtime))

        archive.unlink()


def gallery_dl() -> None:
    with open('/config/config.json') as config_f:
        config = json.load(config_f)

    for gallery_url in config:
        root_path, galleries = config[gallery_url]
        for gallery_id, gallery_args in galleries.items():
            gallery = f'{root_path}/{gallery_id}'.replace('+', ' ')
            logger.info(f'scanning {gallery}')

            gallery_dl = ['gallery-dl', gallery_url + gallery_id] + gallery_args
            conf_file, download_dir = '/config/gallery-dl.conf', f'/downloads/{gallery}'
            args = ['--config', conf_file, '--directory', download_dir, '--verbose']
            result = subprocess.run(gallery_dl + args, capture_output=True, text=True)

            counter = 0
            if result.stdout:
                for output in result.stdout.strip().split('\n'):
                    if not output.startswith('#'):
                        logger.info(output)
                        counter += 1
                    else:
                        logger.debug(output)
            if result.stderr:
                for output in result.stderr.strip().split('\n'):
                    logger.debug(output)

            if counter > 0:
                suffix = 's' if counter > 1 else ''
                message = f'{counter} image{suffix} downloaded'
                logger.info(f'{message} from {gallery}')

                if DISCORD_WEBHOOK:
                    notify_discord(message, gallery, DISCORD_WEBHOOK)
                if PUSHOVER_USER_KEY and PUSHOVER_APP_TOKEN:
                    notify_pushover(message, gallery, PUSHOVER_USER_KEY, PUSHOVER_APP_TOKEN)

                extract_archives(Path(f'/downloads/{gallery}'))


async def create_scheduler(schedule: str, timezone: str | None) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    try:
        trigger = CronTrigger.from_crontab(schedule, timezone)
    except ValueError:
        logger.exception(f"invalid expression or unsupported macro: '{schedule}'")
        raise
    scheduler.add_job(gallery_dl, trigger)
    scheduler.start()
    return scheduler


def main() -> None:
    logging.basicConfig(
        level=logging.ERROR,
        format='[%(asctime)s %(levelname)s] [%(name)s] %(message)s',
    )
    logger.setLevel(os.getenv('LOG_LEVEL', 'INFO').upper())

    async def run_all(schedule: str) -> None:
        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()

        loop.add_signal_handler(signal.SIGTERM, lambda: stop_event.set())
        loop.add_signal_handler(signal.SIGINT, lambda: stop_event.set())

        schedule = CRON_MACROS.get(schedule, schedule)
        timezone = os.getenv('TZ', 'UTC')
        logger.info(f"scheduling session for '{schedule}' ({timezone})")

        scheduler = await create_scheduler(schedule, timezone)
        await stop_event.wait()
        scheduler.shutdown(wait=False)

    logger.info(f'Gallery Watcher {__version__}-{version("gallery-dl")}')

    if ONCE_ON_STARTUP:
        gallery_dl()
    if CRON_SCHEDULE is not None:
        asyncio.run(run_all(CRON_SCHEDULE))


if __name__ == '__main__':
    main()
