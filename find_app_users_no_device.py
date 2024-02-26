import csv
import os
import sys
import json
import logging
import pandas as pd
from tqdm import tqdm
from datetime import datetime
from dotenv import load_dotenv

# load custom modules
from okta_app_functions import fetch_all_applications, get_app_ids_for_targeted_apps, fetch_all_app_users
from okta_device_functions import get_all_device_users, get_device_mapping_obj
from okta_user_functions import get_user_mapping_table, find_user_push_factor

load_dotenv()  # load env variables from .env

###########################################################
###########################################################
# GLOBAL VARIABLES
###########################################################
###########################################################
USER_DEVICE_MAPPING = {}
USER_ID_MAPPING = {}
FAILED_TO_FETCH_USER_FACTORS = []
###########################################################
###########################################################


###########################################################
###########################################################
#INITALIZE THE LOGGER
# Logger variable
logger: logging.Logger
print(f"Initalizing logging framework for {__name__}.")
logFilePrefix="./logs/"
# If there is not a subdirectory in CWD for logs, create it
if not os.path.exists("./logs"):
    logStr = "Logs directory did not exist."
    logger.debug(logStr)
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
    logger = logging.getLogger("okta-reenrollment-script")
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


def determine_users_without_devices(user_list: list) -> list:
    users_without_devices = []
    logger.info("Determining which users from the app list do not have a registered device within Okta...")
    total_users = len(user_list)
    cur_user = 0
    for user in tqdm(user_list):
        cur_user += 1
        if user["id"] not in USER_DEVICE_MAPPING:
            users_without_devices.append(user)
            logger.debug(
                f"#{cur_user}/{total_users}: Associate {user['id']} does not have a registered device."
            )
        else:
            logger.debug(
                f"#{cur_user}/{total_users}: Associate {user['id']} does have a registered device."
            )
    return users_without_devices


def find_app_users_without_devices(app_list: list) -> list:
    for app in app_list:
        app.update({"usersNoRegisteredDevices": []})
        logger.info(f"Finding users who do not have a registered device for application: {app['name']}")
        for user in tqdm(app["users"]):
            if user["id"] not in USER_DEVICE_MAPPING:
                app["usersNoRegisteredDevices"].append(user)
                logger.debug(
                    f"Current App: {app['name']} - Associate {user['id']} does not have a registered device."
                )
            else:
                logger.debug(
                    f"Current App: {app['name']} - Associate {user['id']} does have a registered device."
                )

    return app_list


def find_users_needing_reenrollment(app_list: list) -> list:
    for app in app_list:
        logger.info(f"Determining which users of {app['name']} will need an MFA factor reset...")
        app.update({"usersTargetedForReEnrollment": []})
        if len(app["usersNoRegisteredDevices"]) > 0:
            count=0
            total=len(app["usersNoRegisteredDevices"])
            logger.info(f"Checking if users of app {app['name']} without registered device have an Okta Verify push factor.")
            for user in tqdm(app["usersNoRegisteredDevices"]):
                count+=1
                logger.debug(
                    f"(#{count}/{total}) - Checking factors for {user['id']}"
                )
                user = find_user_push_factor(user=user)
                if user["userPushFactorExists"]:
                    logger.debug(
                    f"User {user['id']} has valid Okta Verify factor present"
                    )
                    app["usersTargetedForReEnrollment"].append(user)
                else:
                    logger.debug(
                        f"User {user['id']} does not have any valid Okta Verify factors present"
                    )
        else:
            logger.info(
                f"All users of application {app['name']} already have regisetered devices, no need to check for user factors."
            )
    return app_list


def generate_unique_users_for_reenrollment(app_list: list):
    logger.info("Script will now prepare a list of users that require re-enrollment.")
    unique_users = {}
    for app in app_list:
        logger.info(f"Formatting user list for app {app['name']}")
        for target_user in tqdm(app["usersTargetedForReEnrollment"]):
            
            logger.debug(f"Formatting data for user {target_user['id']}")
            
            #prepare user details
            userId =  target_user['id']
            
            if "login" in target_user['profile']:
                userName = target_user['profile']['login']
            else:
                userName = target_user['profile']['email']
                
            userEmail = target_user['profile']['email']
            
            if "displayName" in target_user['profile']:
                userFullName = target_user['profile']['displayName']
            elif "firstName" not in target_user['profile'] or "lastName" not in target_user['profile']['email']:
                userFullName = userName
            else:
                userFullName = f"{target_user['profile']['firstName']} {target_user['profile']['lastName']}"
            
            if userId in unique_users:
                unique_users[userId]['appsInScope'].append(app["name"])
            else:
                unique_users.update(
                    {
                        userId : {
                            "userId":userId,
                            "userName":userName,
                            "userFullName": userFullName,
                            "userEmail": userEmail,
                            "oktaVerifyExistingFactor":target_user["userPushFactorExists"],
                            "appsInScope":[app['name']]
                        }
                    }
                )
    logger.info(f"Prepared a list of {len(unique_users)} that require re-enrollment...")
    return unique_users


def write_users_to_csv(filepath: str,data: list) -> None:
    logger.info(f"Writing the list of unique users requiring re-enrollment to {filepath}")
    try:
        current_date = datetime.now().strftime("%Y-%m-%d")
        filename = f"{current_date}_{filepath}"    
        df=pd.DataFrame.from_dict(data,orient="index")
        df.to_csv(filename,index=False)
    except Exception as err:
        logger.error(f"Failed to write users requiring re-enrollment to {filepath}")
        logger.error(str(err))
    

def save_data_csv(filepath: str, data: list):
    logger.info(f"Exporting user data to {filepath}...")
    
    # Specify the CSV file path
    csv_file_path = filepath

    # Write data to CSV file with header
    with open(csv_file_path, "w", newline="") as csvfile:
        # Define the CSV writer
        csv_writer = csv.writer(csvfile)

        csv_writer.writerow(["Name", "User ID", "Email"])

        for row in data:
            csv_writer.writerow(
                [
                    f"{row['profile']['firstName']} {row['profile']['lastName']}",
                    row["profile"]["login"],
                    row["profile"]["email"],
                ]
            )

    logger.info(f"Data has been exported to {csv_file_path}")


def load_csv_dataframe(filepath: str) -> pd.DataFrame:
    logger.info(f"Loading {filepath} into script as pandas dataframe...")
    try:
        return pd.read_csv(filepath)
    except FileNotFoundError as file_err:
        logger.critical(f"Script could not find {filepath} and generated the following error.")
        logger.critical(str(file_err))
        logger.critical("Script will now exit due to this error")
        sys.exit(1)
    except Exception as err:
        logger.critical(f"Script generated the following error when trying to open {filepath}")
        logger.critical(str(file_err))
        logger.critical("Script will now exit due to this error")
        sys.exit(1)


def load_json_file(filepath: str) -> dict:
    logger.info(f"Loading JSON file at {filepath} into script...")
    try:
        with open(filepath, "r") as json_file:
            data = json.load(json_file)
        return data
    except FileNotFoundError as fe:
        logger.error(str(fe))
        logger.error(f"File {filepath} was not found")
        return None


def dump_json_to_file(filepath: str, data: dict) -> None:
    logger.info(f"Saving JSON data to file {filepath}")
    try:
        with open(filepath, "w") as file:
            json.dump(data, file)
    except Exception as err:
        logger.error(f"Failed to save JSON data to {filepath}")
        logger.error(str(err))


if __name__ == "__main__":
    
    """
     _summary_

    _extended_summary_
    """
    
    
        # Fetch apps and get app users
    all_apps = fetch_all_applications()
    targeted_apps = load_csv_dataframe(filepath="./okta_apps.csv")
    targeted_app_ids = get_app_ids_for_targeted_apps(
        targeted_apps=targeted_apps, all_apps=all_apps
    )
    
    # A table full of user profile information, more verbose then that returned from app user membership API calls
        # if a local json w/ user device mapping exists, load that to save time.
    fp_user_list = "okta_users.json"
    if os.path.exists(fp_user_list):
        USER_ID_MAPPING = load_json_file(filepath=fp_user_list)
    if USER_ID_MAPPING is None or len(USER_ID_MAPPING) == 0:
        USER_ID_MAPPING = get_user_mapping_table()
        
        
    # if a local json w/ user device mapping exists, load that to save time.
    fp_device_list = "okta_device_users.json"
    if os.path.exists(fp_device_list):
        USER_DEVICE_MAPPING = load_json_file(filepath=fp_device_list)
    if USER_DEVICE_MAPPING is None or len(USER_DEVICE_MAPPING) == 0:
        device_user_list = get_all_device_users()
        USER_DEVICE_MAPPING = get_device_mapping_obj()
        dump_json_to_file(filepath=fp_device_list, data=USER_DEVICE_MAPPING)
        

    app_list_users = fetch_all_app_users(app_list=targeted_app_ids)
    app_list_users_no_devices = find_app_users_without_devices(app_list=app_list_users)
    app_list_with_targeted_users = find_users_needing_reenrollment(
        app_list=app_list_users_no_devices
    )
    unique_users = generate_unique_users_for_reenrollment(app_list=app_list_with_targeted_users)
    write_users_to_csv("unique_okta_users_for_reenrollment.csv",data=unique_users)
    logger.info("Script complete!")
