import os
import sys
import re
import requests
import logging
import pandas as pd
from tqdm import tqdm
from datetime import datetime
from dotenv import load_dotenv

#load custom modules
from okta_user_functions import fetch_full_user_profiles

load_dotenv()  # load env variables from .env

###########################################################
###########################################################
# GLOBAL VARIABLES
###########################################################
###########################################################
OKTA_TOKEN = os.getenv("OKTA_TOKEN")
OKTA_URL = os.getenv("OKTA_URL")
###########################################################
###########################################################


###########################################################
###########################################################
# CREATE LOGGER INSTANCE
logger: logging.Logger
print(f"Initalizing logging framework for {__name__}.")
logFilePrefix="./logs/"
# If there is not a subdirectory in CWD for logs, create it
if not os.path.exists("./logs"):
    logStr = "Logs directory did not exist."
    print(logStr)
    logFilePrefix="./logs/"
    try:
        os.mkdir("./logs")
        logStr: str = "Created logs directory"
        logger.debug(logStr)
    except OSError as os_err:
        logStr: str = f"FAILED TO CREATE LOGS DIRECTORY"
        print(logStr)
        print(str(os_err))
        logFilePrefix="."
# Add the current date to the log file name
dateStr: datetime = datetime.now().strftime("%Y-%m-%d")
log_name: str = os.getenv("LOG_FILE_NAME")
if len(log_name) == 0:
    log_name: str = os.path.basename(__file__)
logFileName = f"{logFilePrefix}/{dateStr}-{log_name}"
# Try to create a logger with both a stream and file handler
try:
    # Create logger
    logger = logging.getLogger("okta_app_functions")
    logger.setLevel(logging.DEBUG)

    # file handler logs to specific file. Debug log level
    file_handler = logging.FileHandler(logFileName)
    file_handler.setLevel(logging.DEBUG)

    # Stream handler will log to stdout. Log level just INFO
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)

    # Create formatter and add it to handlers
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)

    # Add handlers to the logger global object. Anytime you log to this
    # object, it logs to the file and stdout
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
except:
    print(f"Failed to initalize logger for {__name__} . Exiting script")
    sys.exit(1)
###########################################################
###########################################################


def fetch_all_applications(next_page_url: str = None):
    url = f"{OKTA_URL}/api/v1/apps"

    headers = {
        "Accept": "application/json",
        "Authorization": f"SSWS {OKTA_TOKEN}",
    }
    payload = {}

    if next_page_url:
        full_url = next_page_url
    else:
        full_url = url + "?limit=1000"
        logger.info("Fetching all Okta applications")

    app_list = []

    try:
        response = requests.request("GET", full_url, headers=headers, data=payload)
        response.raise_for_status()

        data = response.json()

        if "error" in data:
            raise requests.exceptions.RequestException(
                "Okta response states there as an error."
            )

        app_list += data

    except requests.exceptions.RequestException as req_error:
        logger.critical(str(req_error))
        logger.critical("Error occurred fetching apps, terminating script.")
        sys.exit(1)
    except Exception as error:
        logger.critical(str(error))
        logger.critical("Error occurred fetching apps, terminating script.")
        sys.exit(1)

    try:
        if ' rel="next"' in dict(response.headers)["link"]:
            pattern = r'<.*?;\srel="self",\s<(.*?)>;\srel="next"$'
            match = re.search(pattern, dict(response.headers)["link"])

            if match:
                next_page_url = match.group(1)
                logger.info(f"URL for next page of data: {next_page_url}")
                app_list += fetch_all_applications(next_page_url=next_page_url)
            else:
                logger.info("No match found for next URL.")

    except KeyError:
        logger.debug("Link not found in reponse headers, must be all devices")

    return app_list


def get_app_ids_for_targeted_apps(targeted_apps: pd.DataFrame, all_apps: list) -> list:
    apps_with_ids = []
    app_map = {}

    logger.info("Creating app dictionary lookup table...")
    for app in tqdm(all_apps):
        app_map.update({app["label"]: app})

    targeted_apps_list = list(targeted_apps.AppName)

    logger.info("Generating list of targeted apps based on provided CSV data...")
    for app in tqdm(targeted_apps_list):
        if app in app_map:
            app_details = app_map[app]
            apps_with_ids.append(
                {"name": app_details["label"], "id": app_details["id"]}
            )
        else:
            logger.critical(f"APP NAME {app} NOT FOUND IN LIST OF OKTA APPS")
            #sys.exit(1)

    return apps_with_ids


def fetch_users_for_app(app_details: dict, next_page_url: str = None):
    url = f"{OKTA_URL}/api/v1/apps/{app_details['id']}/users"

    headers = {
        "Accept": "application/json",
        "Authorization": f"SSWS {OKTA_TOKEN}",
    }
    payload = {}

    if next_page_url:
        full_url = next_page_url
    else:
        logger.info(f"Fetching Okta users for application: {app_details['name']}")
        full_url = url + "?limit=1000"

    user_list = []

    try:
        response = requests.request("GET", full_url, headers=headers, data=payload)
        response.raise_for_status()

        data = response.json()

        if "error" in data:
            raise requests.exceptions.RequestException(
                "Okta response states there as an error."
            )

        user_list += data

    except requests.exceptions.RequestException as req_error:
        logger.critical(str(req_error))
        logger.critical("Error occurred fetching app users, terminating script.")
        sys.exit(1)
    except Exception as error:
        logger.critical(str(error))
        logger.critical("Error occurred fetching app users, terminating script.")
        sys.exit(1)

    try:
        if ' rel="next"' in dict(response.headers)["link"]:
            pattern = r'<.*?;\srel="self",\s<(.*?)>;\srel="next"$'
            match = re.search(pattern, dict(response.headers)["link"])

            if match:
                next_page_url = match.group(1)
                logger.debug(f"URL for next page of data: {next_page_url}")
                user_list += fetch_users_for_app(
                    app_details=app_details, next_page_url=next_page_url
                )
            else:
                logger.debug("No match found for next URL.")

    except KeyError:
        logger.error("Link not found in reponse headers, must be all devices")

    return user_list


def fetch_all_app_users(app_list: list):
    logger.info("Fetching users for each application.")
    for app in app_list:
        logger.info(f"Fetching all detailed user profiles for {app['name']}")
        app.update(
            {
                "users": fetch_full_user_profiles(
                    user_list = fetch_users_for_app(app_details=app)
                )
            }
        )
    return app_list

