import os
import sys
import json
import re
import logging
import requests
from requests.exceptions import Timeout, HTTPError
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
USER_ID_MAPPING = {}
###########################################################
###########################################################


###########################################################
###########################################################
# CREATE LOGGER INSTANCE
logger: logging.Logger
print(f"Initalizing logging framework for {__name__}.")
logFilePrefix = "./logs/"
# If there is not a subdirectory in CWD for logs, create it
if not os.path.exists("./logs"):
    logStr = "Logs directory did not exist."
    print(logStr)
    try:
        os.mkdir("./logs")
        logStr: str = "Created logs directory"
        logger.debug(logStr)
    except OSError as os_err:
        logStr: str = f"FAILED TO CREATE LOGS DIRECTORY"
        print(logStr)
        print(str(os_err))
        logFilePrefix = "."
# Add the current date to the log file name
dateStr: datetime = datetime.now().strftime("%Y-%m-%d")
log_name: str = os.getenv("LOG_FILE_NAME")
if len(log_name) == 0:
    log_name: str = os.path.basename(__file__)
logFileName = f"{logFilePrefix}/{dateStr}-{log_name}"
# Try to create a logger with both a stream and file handler
try:
    # Create logger
    logger = logging.getLogger("okta_user_functions")
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


def get_user_mapping_table() -> None:
    user_list = fetch_users()
    global USER_ID_MAPPING
    logger.info("Creating local user mapping lookup table...")
    for user in tqdm(user_list):
        logger.debug(f"MAPPING USER: {user['id']}")
        USER_ID_MAPPING.update({user["id"]: user})

    dump_json_to_file(filepath="okta_users.json", data=USER_ID_MAPPING)

    return USER_ID_MAPPING


def fetch_users(next_page_url: str = None, page_num: int = 1) -> list:
    logger.info(f"Fetching page {page_num} Okta users...")

    user_list = []

    url = f"{OKTA_URL}/api/v1/users"

    if next_page_url:
        full_url = next_page_url
    else:
        full_url = url + "?limit=200"

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

        user_list += data

    except requests.exceptions.RequestException as req_error:
        logger.critical(str(req_error))
        logger.critical("Error occurred fetching users, terminating script.")
        sys.exit(1)
    except Exception as error:
        logger.critical(str(error))
        logger.critical("Error occurred fetching users, terminating script.")
        sys.exit(1)

    try:
        if ' rel="next"' in dict(response.headers)["link"]:
            pattern = r'<.*?;\srel="self",\s<(.*?)>;\srel="next"$'
            match = re.search(pattern, dict(response.headers)["link"])

            if match:
                next_page_url = match.group(1)
                logger.debug(f"URL for next page of data: {next_page_url}")
                user_list += fetch_users(
                    next_page_url=next_page_url, page_num=(page_num + 1)
                )
            else:
                logger.debug("No match found for next URL.")

    except KeyError:
        logger.debug("Link not found in reponse headers, must be all users")

    return user_list

    ""


def fetch_user(email: str = None, retry: int = 0) -> dict:
    try:
        if email is None or not re.match(pattern=r".*@siteone\.com", string=email):
            raise ValueError(
                f'The provided email is either blank, or not a valid @siteone.com email address. Email provided is "{email}"'
            )

        # Okta has this weird thing where emails are case sensitive. Most emails have the first two characters capitalized.
        # So to find a user, like, tobarowski@siteone.com, you MUST pass the api TObarowski@siteone.com D:
        email = email[:2].upper() + email[2:]

        logger.info(f"Fetching user information for {email}")

        base_url = OKTA_URL
        api_path = "/api/v1/users"
        params = f'?filter=profile.email eq "{email}"'
        full_url = base_url + api_path + params

        payload = {}
        headers = {
            "Accept": "application/json",
            "Authorization": f"SSWS {OKTA_TOKEN}",
        }

        response = requests.get(url=full_url, headers=headers, data=payload)
        response.raise_for_status()

        logger.info(f"Successfully fetched user profile for {email}")

        return response.json()[0]

    except ValueError as val_err:
        logger.critical(str(val_err))
        sys.exit(1)
    except HTTPError as http_err:
        logger.critical(
            f"HTTP error occurred when fetching user profile for {email}. Terminating script."
        )
        logger.critical(f"{http_err}")
        sys.exit(1)
    except Timeout as timeout_err:
        logger.critical(
            f"The request to get user profile for {email} timed out. Terminating script."
        )
        logger.critical(timeout_err)
        sys.exit(1)
    except RequestException as err:
        logger.critical(
            f"A generic requests error occurred when fetching user profile for {email}. Terminating script."
        )
        logger.critical(err)
        sys.exit(1)


def fetch_user_profile(user_id: str) -> dict:
    logger.info(f"Fetching user information for {user_id}")

    full_url = f"{OKTA_URL}/api/v1/users/{user_id}"

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

        return data

    except requests.exceptions.RequestException as req_error:
        logger.critical(str(req_error))
        logger.critical(f"Error occurred fetching user {user_id}, terminating script.")
        sys.exit(1)
    except Exception as error:
        logger.critical(str(error))
        logger.critical(f"Error occurred fetching user {user_id}, terminating script.")
        sys.exit(1)


def fetch_full_user_profiles(user_list: list) -> list:
    user_full_profiles = []
    for user in tqdm(user_list):
        if len(USER_ID_MAPPING) > 0:
            try:
                user_full_profiles.append(USER_ID_MAPPING[user["id"]])
            except KeyError:
                logger.debug(
                    f"USER_ID_MAPPING was populated, but user id {user['id']} was not found. Querying Okta..."
                )
                user_full_profiles.append(fetch_user_profile(user_id=user["id"]))
            logger.debug(
                f"Found full user profile for {user['id']} in local data structure USER_ID_MAPPING"
            )
        else:
            user_full_profiles.append(fetch_user_profile(user_id=user["id"]))
    return user_full_profiles


def fetch_user_factors(user: dict) -> dict:
    full_url = f"{OKTA_URL}/api/v1/users/{user['id']}/factors"

    headers = {
        "Accept": "application/json",
        "Authorization": f"SSWS {OKTA_TOKEN}",
    }
    payload = {}

    try:
        response = requests.request("GET", full_url, headers=headers, data=payload)
        response.raise_for_status()

        data = response.json()

        if "error" in data:
            raise requests.exceptions.RequestException(
                "Okta response states there as an error."
            )

        return data

    except requests.exceptions.HTTPError as http_err:
        logger.critical(str(http_err))

        if response.status_code == 404:
            logger.critical(f"No factors were found for user {user['id']}.")
            return []
        else:
            logger.critical(
                f"Error occurred fetching user factors for {user['id']}, terminating script."
            )
            sys.exit(1)
    except requests.exceptions.RequestException as req_error:
        logger.critical(str(req_error))
        logger.critical("A generic request exception occurred.")
        sys.exit(1)
    except Exception as error:
        logger.critical(str(error))
        logger.critical(
            f"Error occurred fetching user factors for {user['id']}, terminating script."
        )
        sys.exit(1)


def find_user_push_factor(user: dict) -> dict:
    try:
        logger.info(f"Querying Okta to see what factors {user['profile']['email']} is enrolled with.")
    except KeyError:
        logger.info(f"Querying Okta to see what factors {user['id']} is enrolled with.")
        
    user_factors = fetch_user_factors(user=user)

    user.update(
        {
            "userPushFactorExists": False,
            "userPushFactorList": [],
            "allUserFactors": user_factors,
        }
    )

    # Else for every factor in the list, see if it's a "push" factor
    for factor in user_factors:
        if "push" in factor["factorType"]:
            try:
                logger.debug(f"Found push factor enrolled for {user['profile']['email']}.")
            except KeyError:
                logger.debug(f"Found push factor enrolled for  {user['id']}")
            # If so, remove keys attribute as thats sensitive crypto info, and return user obj
            # containing factor info
            try:
                try:
                    if "keys" in factor["profile"]:
                        factor["profile"].pop("keys")
                except KeyError as ke:
                    try:
                        logger.warning(f"No profile or keys attribute for {user['profile']['email']}.")
                    except KeyError:
                        logger.warning(f"No profile or keys attribute for  {user['id']}")
                user['userPushFactorExists'] = True
                user['userPushFactorList'].append(factor)
            except KeyError as ke:
                logger.warning("key error")

    # If code makes it to here, no push factor was found, so returned an updated user obj refletcing that
    if not user['userPushFactorExists']:
        try:
            logger.debug(f"Did not find push factor enrolled for {user['profile']['email']}.")
        except KeyError:
            logger.debug(f"Did not find push factor enrolled for  {user['id']}")
    
    return user


def unenroll_all_user_push_factors(user_with_factors: dict) -> None:
    """
    unenroll_all_user_push_factors Iterates over all push factors within user['userPushFactorList']
    and calls unenroll_user_factor to unenroll said factor

    Args:
        user_with_factors (dict): Okta user profile object WITH the additional attributes put in place from call "find_user_push_factor".
            That method returns a new user object with attributes containing any push factors the user is enrolled in (user['userPushFactorList'])
    """

    try:
        logger.info(f"Will now attempt to unenroll all push factors that user {user_with_factors['profile']['email']} is enrolled with.")
    except KeyError:
        logger.info(f"Will now attempt to unenroll all push factors that user id {user_with_factors['id']} is enrolled with")
    
    user_with_factors.update({
        "userSuccessfulUnenrolledFactors":[],
        "userFailedUnenrolledFactors":[]
    })
    
    for push_factor in user_with_factors['userPushFactorList']:
        result = unenroll_user_factor(user=user_with_factors,factor=push_factor)
        if result:
            try:
                logger.debug(f"Attempting to add unenrolled factor {push_factor['id']} to list of successfully unenrolled factors")
                user_with_factors['userSuccessfulUnenrolledFactors'].append(push_factor)
            except ValueError as val_err:
                logger.error(
                    f"Unable to remove factor {push_factor['id']} from user_with_factors['userPushFactorList'] attribute and add it to user_with_factors['userSuccessfulUnenrolledFactors']"
                )
                logger.error(str(val_err))
        else:
            try:
                logger.debug(f"Attempting to add push factor {push_factor['id']} to list of FAILED TO unenroll factors")
                user_with_factors['userFailedUnenrolledFactors'].append(push_factor)
            except ValueError as val_err:
                logger.error(
                    f"Unable to remove factor {push_factor['id']} from user_with_factors['userPushFactorList'] attribute and add it to user_with_factors['userFailedUnenrolledFactors']"
                )
                logger.error(str(val_err))
    
    return user_with_factors
                
    
def unenroll_user_factor(user: dict, factor: dict) -> bool:
    user_id = user['id']
    try:
        logger.info(f"Will attempt to unenroll factor {factor['id']} for user {user['profile']['email']}")
    except KeyError:
        logger.info(f"Will attempt to unenroll factor {factor['id']} for user {user_id}")
    
    base_url = OKTA_URL
    api_path_params = f"/api/v1/users/{user_id}/factors/{factor['id']}"
    full_url = base_url+api_path_params
    
    payload = {}
    headers = {
        "Accept": "application/json",
        "Authorization": f"SSWS {OKTA_TOKEN}",
    }
    try:
        response = requests.delete(url=full_url,headers=headers,data=payload)
        response.raise_for_status()
        try:
            logger.info(f"Successfully unenrolled factor {factor['id']} for user {user['profile']['email']}")
        except KeyError:
            logger.info(f"Successfully unenrolled factor {factor['id']} for user {user_id}")
        return True
    except HTTPError as http_err:
        try:
            logger.error(
            f"HTTP error occurred while unenrolling factor {factor['id']} for {user['profile']['email']}."
        )
        except KeyError:
            logger.error(
            f"HTTP error occurred while unenrolling factor {factor['id']} for {user_id}."
        )
        finally:
            logger.error(f"{http_err}")
            return False
    except Timeout as timeout_err:
        try:
            logger.error(
            f"Timeout error occurred while unenrolling factor {factor['id']} for {user['profile']['email']}."
        )
        except KeyError:
            logger.error(
            f"Timeout error occurred while unenrolling factor {factor['id']} for {user_id}."
        )
        finally:
            logger.error(f"{timeout_err}")
            return False
    except RequestException as err:
        try:
            logger.error(
            f"Generic error occurred while unenrolling factor {factor['id']} for {user['profile']['email']}."
        )
        except KeyError:
            logger.error(
            f"Generic error occurred while unenrolling factor {factor['id']} for {user_id}."
        )
        finally:
            logger.error(f"{err}")
            return False
    

def enroll_new_push_factor(user: dict) -> dict:
    try:
        logger.info(f"Enrolling new push factor for {user['profile']['email']}. This will generate a enroll QR code.")
    except KeyError:
        logger.info(f"Enrolling new push factor for {user['id']}. This will generate a enroll QR code.")
    
    base_url = OKTA_URL
    api_path_params = f"/api/v1/users/{user['id']}/factors?activate=true"
    full_url = base_url+api_path_params
    
    payload = {
        "factorType": "push",
        "provider": "OKTA"
    }
    
    headers = {
        "Accept": "application/json",
        "Authorization": f"SSWS {OKTA_TOKEN}",
    }
    
    try:
        response = requests.post(url=full_url,headers=headers,json=payload)
        response.raise_for_status()
        try:
            logger.info(f"Successfully enrolled a new push factor for user {user['profile']['email']}")
        except KeyError:
            logger.info(f"Successfully enrolled a new push factor for user {user['id']}")
        #return {"TEST":"test"}
        logger.debug(json.dumps(response.json(),indent=4))
        return response.json()
    except HTTPError as http_err:
        try:
            logger.error(
            f"HTTP error occurred while enrolling new factor for {user['profile']['email']}."
        )
        except KeyError:
            logger.error(
            f"HTTP error occurred while enrolling new factor for {user['id']}."
        )
        finally:
            logger.error(f"{http_err}")
            return False
    except Timeout as timeout_err:
        try:
            logger.error(
            f"Timeout error occurred while enrolling new factor for {user['profile']['email']}."
        )
        except KeyError:
            logger.error(
            f"Timeout error occurred while enrolling new factor for {user['id']}."
        )
        finally:
            logger.error(f"{timeout_err}")
            return False
    except RequestException as err:
        try:
            logger.error(
            f"Generic error occurred while enrolling new factor for {user['profile']['email']}."
        )
        except KeyError:
            logger.error(
            f"Generic error occurred while enrolling new factor for {user['id']}."
        )
        finally:
            logger.error(f"{err}")
            return False
    except Exception as err:
        try:
            logger.error(
            f"An unexpected error occurred while enrolling new factor for {user['profile']['email']}."
        )
        except KeyError:
            logger.error(
            f"An unexpected error occurred while enrolling new factor for {user['id']}."
        )
        finally:
            logger.error(f"{err}")
            return False
    
    

def dump_json_to_file(filepath: str, data: dict) -> None:
    with open(filepath, "w") as file:
        json.dump(data, file)
