import os
import sys
import re
import time
import requests
import logging
from tqdm import tqdm
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()  # load env variables from .env

###########################################################
###########################################################
# GLOBAL VARIABLES
###########################################################
###########################################################
OKTA_TOKEN = os.getenv("OKTA_TOKEN")
OKTA_URL = os.getenv("OKTA_URL")
USER_DEVICE_MAPPING = {}
###########################################################
###########################################################


###########################################################
###########################################################
# CREATE LOGGER INSTANCE
###########################################################
###########################################################
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
    logger = logging.getLogger("okta_device_functions")
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


def fetch_devices(next_page_url: str = None, page_num: int = 1) -> list:
    logger.info(f"Fetching page number {page_num} of Okta devices...")

    device_list = []

    url = f"{OKTA_URL}/api/v1/devices"

    if next_page_url:
        full_url = next_page_url
    else:
        full_url = url + "?limit=1000"

    payload = {}
    headers = {
        "Accept": "application/json",
        "Authorization": f"SSWS {OKTA_TOKEN}",
    }

    try:
        response = requests.request("GET", full_url, headers=headers, data=payload)
        response.raise_for_status()

        data = response.json()

        if "error" in data:
            raise requests.exceptions.RequestException(
                "Okta response states there as an error."
            )

        device_list += data

    except requests.exceptions.RequestException as req_error:
        logger.critical(str(req_error))
        logger.critical("Error occurred fetching devices, terminating script.")
        sys.exit(1)
    except Exception as error:
        logger.critical(str(error))
        logger.critical("Error occurred fetching devices, terminating script.")
        sys.exit(1)

    try:
        if ' rel="next"' in dict(response.headers)["link"]:
            pattern = r'<.*?;\srel="self",\s<(.*?)>;\srel="next"$'
            match = re.search(pattern, dict(response.headers)["link"])

            if match:
                next_page_url = match.group(1)
                logger.debug(f"URL for next page of data: {next_page_url}")
                device_list += fetch_devices(next_page_url=next_page_url,page_num=(page_num+1))
            else:
                logger.debug("No match found for next URL.")

    except KeyError:
        logger.debug("Link not found in reponse headers, must be all devices")

    return device_list

    ""


def loop_get_all_device_users(device_list: list) -> list:
    device_api_rate_limit = 500
    temp_list = []
    total_devices = len(device_list)
    current_number_device = 0
    logger.info("Fetching users for each device...")
    for device in tqdm(device_list):
        current_number_device += 1
        logger.debug(
            f"#{current_number_device}/{total_devices}: Fetching users for {device['resourceDisplayName']['value']}"
        )
        temp_list.append(fetch_device_users(device))
        time.sleep((1 / device_api_rate_limit))
        # if current_number_device == 500:
        # break
    return temp_list


def fetch_device_users(okta_device: dict) -> list:
    global USER_DEVICE_MAPPING

    full_url = f"{OKTA_URL}/api/v1/devices/{okta_device['id']}/users"

    payload = {}
    headers = {
        "Accept": "application/json",
        "Authorization": f"SSWS {OKTA_TOKEN}",
    }

    try:
        response = requests.request("GET", full_url, headers=headers, data=payload)
        response.raise_for_status()

        data = response.json()

        if len(data) == 0:
            okta_device.update({"users": None})
            okta_device.update({"managementStatus": "N/A"})
        else:
            temp_users = []
            for user_data in data:
                temp_users.append(user_data["user"])

                okta_device.update({"users": temp_users})
                okta_device.update({"managementStatus": data[0]["managementStatus"]})

                if user_data["user"]["id"] in USER_DEVICE_MAPPING:
                    USER_DEVICE_MAPPING[user_data["user"]["id"]].append(okta_device)
                else:
                    USER_DEVICE_MAPPING.update({user_data["user"]["id"]: [okta_device]})

        return okta_device

    except Exception as err:
        logger.error(str(err))


def get_device_mapping_obj() -> dict:
    return USER_DEVICE_MAPPING


def get_all_device_users() -> list:
    device_list = fetch_devices()
    return loop_get_all_device_users(device_list=device_list)

def get_all_device_users_v2() -> list:
    device_list = fetch_devices()
    devices_with_users = loop_get_all_device_users(device_list=device_list)
    return get_device_mapping_obj()
