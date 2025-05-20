import json
import logging
import os
import signal
import subprocess
import time

import pytz
import requests
import schedule

stop_requested = False


def discord_webhook(message: str, gallery: str, webhook_url: str):
    message += f' from **{gallery}**'
    data = {'embeds': [{'description': message.lower(), 'color': 1146986}]}
    result = requests.post(webhook_url, json=data)
    try:
        result.raise_for_status()
    except requests.exceptions.HTTPError as http_error:
        logging.error(http_error)


def pushover_webhook(message: str, gallery: str, app_token: str, user_key: str):
    message += f' from <b>{gallery}</b>'
    data = {'message': message.lower(), 'html': 1, 'token': app_token, 'user': user_key}
    result = requests.post('https://api.pushover.net/1/messages.json', json=data)
    try:
        result.raise_for_status()
    except requests.exceptions.HTTPError as http_error:
        logging.error(http_error)


def gallery_dl():
    with open('gallery-dl/config.json') as config_f:
        config = json.load(config_f)
    logging.info('Monitoring Session Started')
    for url in config:
        root_path, galleries = config[url]
        for gallery_id in galleries:
            command = ['gallery-dl', url + gallery_id] + galleries[gallery_id]
            logging.info(f'Running {command}')
            command += [
                '-d',
                '/downloads',
                '--download-archive',
                '/gallery-dl/archive.sqlite3',
            ]
            result = subprocess.run(command, capture_output=True, text=True)
            counter = 0
            if result.stdout:
                for output in result.stdout.strip().split('\n'):
                    if not output.startswith('#'):
                        counter += 1
                    logging.debug(output)
            if result.stderr:
                for output in result.stderr.strip().split('\n'):
                    logging.error(output)
            message = f'{counter} Image(s) Downloaded'
            gallery = f'{root_path}/{gallery_id}'
            logging.info(f'{message} from {gallery}')
            if counter > 0:
                webhook_url = os.environ['DISCORD_WEBHOOK_URL']
                if webhook_url:
                    discord_webhook(message, gallery, webhook_url)
                app_token = os.environ['PUSHOVER_APP_TOKEN']
                user_key = os.environ['PUSHOVER_USER_KEY']
                if app_token and user_key:
                    pushover_webhook(message, gallery, app_token, user_key)
    logging.info('Monitoring Session Finished')


def main():
    global stop_requested
    logging.basicConfig(format='[%(levelname)s] %(message)s')
    logger = logging.getLogger()
    match os.environ['LOGGING_LEVEL']:
        case 'debug':
            logger.setLevel(logging.DEBUG)
        case 'info':
            logger.setLevel(logging.INFO)
        case 'warning':
            logger.setLevel(logging.WARNING)
        case 'error':
            logger.setLevel(logging.ERROR)
        case 'critical':
            logger.setLevel(logging.CRITICAL)

    def handle_signal():
        global stop_requested
        stop_requested = True

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    logging.info('Application Initialized')
    logging.info('Logging Level Set to ' + os.environ['LOGGING_LEVEL'])
    schedule_time = os.environ['SCHEDULE_TIME']
    if schedule_time:
        logging.info('Monitoring Scheduled for ' + os.environ['SCHEDULE_TIME'])
    if os.environ['ONCE_ON_STARTUP'] == 'true':
        gallery_dl()
    if schedule_time:
        tz = pytz.timezone(os.environ['TZ'])
        schedule.every().day.at(schedule_time, tz).do(gallery_dl)
        while not stop_requested:
            schedule.run_pending()
            time.sleep(1)


if __name__ == '__main__':
    main()
