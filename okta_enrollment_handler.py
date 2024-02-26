# Load custom modules
import os
import sys
import csv
import json
import tqdm
import logging
import textwrap
import argparse
import pandas as pd
from textwrap import dedent
from datetime import datetime
from dotenv import load_dotenv
from okta_user_functions import (
    fetch_user,
    find_user_push_factor,
    unenroll_all_user_push_factors,
    enroll_new_push_factor,
)
from okta_device_functions import (
    get_all_device_users_v2
)
from send_o365_email import send_okta_enrollment_email_v2

# Load env variables
load_dotenv()

###########################################################
###########################################################
# CREATE LOGGER INSTANCE
logger: logging.Logger
print(f"Initalizing logging framework for {os.path.basename(__file__)}.")
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
    logger = logging.getLogger("okta_enrollment_handler")
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
    print(
        f"Failed to initalize logger for {os.path.basename(__file__)} . Exiting script"
    )
    sys.exit(1)
###########################################################
###########################################################


def load_user_list_csv(path: str) -> list:
    try:
        df = pd.read_csv(path)
        return df.to_dict(orient="records")
    except FileNotFoundError as fne_err:
        logger.critical(
            f"The specified file path {path} is not valid. Please provide a valid filepath to a CSV of users to re-enroll, using the parameter --path <filepath>"
        )
        logger.critical(
            f"{os.path.basename(__file__)} will now terminate due to this critical error."
        )
        sys.exit(1)
    except pd.errors.EmptyDataError:
        logger.critical(
            f"The CSV file provided at {path} was empty. Please provide a valid CSV file containing a list of users to re-enroll, using the parameter --path <filepath>"
        )
        logger.critical(
            f"{os.path.basename(__file__)} will now terminate due to this critical error."
        )
        sys.exit(1)
    except pd.errors.ParserError as pd_parse_err:
        logger.critical(
            f"The CSV file provided at {path} could not be properly parsed. Please review below error message, and provide a valid CSV file containing a list of users to re-enroll, using the parameter --path <filepath"
        )
        logger.critical(str(pd_parse_err))
        logger.critical(
            f"{os.path.basename(__file__)} will now terminate due to this critical error."
        )
        sys.exit(1)
    except TypeError as type_err:
        logger.critical(
            f"A type error occurred when trying to load the contents of {path}. Please review the below error message and correct the issue. Then, provide a valid CSV file containing a list of users to re-enroll, using the parameter --path <filepath "
        )
        logger.critical(str(type_err))
        logger.critical(
            f"{os.path.basename(__file__)} will now terminate due to this critical error."
        )
        sys.exit(1)
    except Exception as generic_err:
        logger.critical(
            f"An unexpected error occurred when trying to load the contents of {path}. Please review the below error message and correct the issue. Then, provide a valid CSV file containing a list of users to re-enroll, using the parameter --path <filepath "
        )
        logger.critical(str(generic_err))
        logger.critical(
            f"{os.path.basename(__file__)} will now terminate due to this critical error."
        )
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


def save_json_file(filepath: str, json_obj: dict) -> bool:
    logger.debug(f"Saving json to {filepath}")
    try:
        with open(filepath, 'w') as jsonFileObj:
            json.dumps(json_obj,jsonFileObj,indent=4)
            logger.debug(f"Successfully wrote JSON data to {filepath}")
    except Exception as err:
        logger.error(f"An error occurred when attempting to save JSON to {filepath}. See below error.")
        logger.error(str(err))
    

def execute_enrollment_verification_workflow(users: list, useCachedData: bool = False) -> None:
    logger.info("Executing workflow to verify the users previously targeted for re-enrollment (within provided CSV) have re-enrolled")
    user_device_mapping_obj =  None
    # If we have a local cache of device/user mappings, load that as it saves significant time. However, this may not be too handy at all times because 
    # in order to verify if a user re-enrolled, you need may need fresh data, as they may have re-enrolled after you last fetched the data
    fp_device_list = "user_device_mapping.json"
    if useCachedData:
        if os.path.exists(fp_device_list):
            logger.debug(f"Local copy of the user device mapping object exists at {fp_device_list}. Attempting to load it now.")
            user_device_mapping_obj = load_json_file(filepath=fp_device_list)
            logger.debug(f"Successfully loaded JSON {fp_device_list} into memory")
        else:
            logger.error(f"The flag was set to use locally cached device/user mapping data, but the required file {fp_device_list} does not exist.")
            logger.info(f"The flag was set to use locally cached device/user mapping data, but the required file {fp_device_list} does not exist.")
            sys.exit(1)
    
    if user_device_mapping_obj is None or len(user_device_mapping_obj) == 0:
        logger.debug(f"The user_device_mapping_obj variable is empty or has not been initalized. Will fetch fresh data from Okta.")
        user_device_mapping_obj = get_all_device_users_v2()
        save_json_file(filepath="user_device_mapping.json",json_obj=user_device_mapping_obj)
        
    logger.debug(f"Fetched data structure containing user ID to device ownership mappings. Total mappings: {len(user_device_mapping_obj)}")
    
    user_enrollment_status_list = []
    logger.info("Comparing each user against list of users with registered devices...")
    for user in users:
        logger.debug(f"Checking if {user['userFullName']} - {user['userId']} is present in user/device mapping object.")
        if user['userId'] in user_device_mapping_obj:
            logger.debug(f"{user['userFullName']} - {user['userId']} is present in user/device mapping object.")
            user.update({'enrollmentStatus':True})
            user_enrollment_status_list.append(user)
        else:
            logger.debug(f"{user['userFullName']} - {user['userId']} is NOT present in user/device mapping object.")
            user.update({'enrollmentStatus':False})
            user_enrollment_status_list.append(user)
    logger.info("Finished comparison.")
            
    try:
        csvfileName = f"{datetime.now().strftime('%Y-%m-%d')}_enrollment_verification_results.csv"
        logger.info(f"Attempting to export results of enrollment verification to CSV file {csvfileName}")
        with open(csvfileName,'w') as file:
            logger.debug(f"Successfully opened file {csvfileName} for writing")
            csvDictWriter = csv.DictWriter(file,fieldnames=user_enrollment_status_list[0].keys())
            logger.debug(f"Successfully created a csv.DictWriter object, and supplied it fieldnames: {user_enrollment_status_list[0].keys()}")
            csvDictWriter.writeheader()
            logger.debug("Successful wrote headers to CSV file")
            csvDictWriter.writerows(user_enrollment_status_list)
            logger.debug("Successfully wrote all indices within user_enrollment_status_list: list to CSV")
            logger.info(f"Done generating CSV: {csvfileName}")
    except Exception as err:
        logger.info(f"An error occurred when attempting to export the results of enrollment verification to CSV file '{csvfileName}'")
        logger.error(f"An error occurred when trying to export contents of user_enrollment_status_list: list to CSV named {csvfileName}. See error below")
        logger.error(str(err))
        sys.exit(1)
            

def execute_reenrollment_workflow(users: list) -> None:
    # Check to see if the path to the HTML template file exists, if not raise error and exit script
    try:
        email_template_path = os.getenv("ENROLLMENT_EMAIL_TEMPLATE_PATH")
        if not os.path.exists(email_template_path):
            raise FileNotFoundError(
                f"The path for the enrollment email template does not exist: {email_template_path}"
            )
    except FileNotFoundError as file_err:
        logger.critical(file_err)
        print(file_err)
        logger.critical("Exiting script.")
        print("Exiting script.")
        sys.exit(1)
    for user_record in users:
        logger.info(
            f"ATTEMPTING TO PERFORM RE-ENROLLMENT WORKFLOW AGAINST {user_record['userEmail']}"
        )
        user: dict = fetch_user(email=user_record["userEmail"])
        user_with_factors: dict = find_user_push_factor(user=user)
        user_with_unenrolled_factors: dict = unenroll_all_user_push_factors(user_with_factors=user_with_factors)
        new_factor_information: dict = enroll_new_push_factor(user=user_with_unenrolled_factors)
        #send_okta_enrollment_email(destination_email=user_with_unenrolled_factors['profile']['email'],qr_code_url=new_factor_information['_embedded']['activation']['_links']['qrcode']['href'],attach_instructions=True)
        send_okta_enrollment_email_v2(
            destination_email=user_with_factors["profile"]["email"],
            attach_instructions=True,
            attachment_path=os.getenv('ATTACHMENT_FILEPATH'),
            html_template_path=email_template_path
        )


def execute_proactive_notification_workflow(
    users: list = None, date_of_change: str = None
) -> None:
    logger.info(
        "Executing workflow to only send notification emails to targeted users."
    )

    # Check to see if the path to the HTML template file exists, if not raise error and exit script
    try:
        email_template_path = os.getenv("PROACTIVE_EMAIL_TEMPLATE_PATH")
        if not os.path.exists(email_template_path):
            raise FileNotFoundError(
                f"The path for the proactive email template does not exist: {email_template_path}"
            )
    except FileNotFoundError as file_err:
        logger.critical(file_err)
        print(file_err)
        logger.critical("Exiting script.")
        print("Exiting script.")
        sys.exit(1)

    # Fetch user info from Okta for each targeted user, and then send them a proactive "warning" email explaining of the future change
    prog_counter = 1
    total_users = len(users)
    for user_record in users:
        logger.info(
            f"#{prog_counter}/{total_users}: Attempting to send proactive notification email to {user_record['userEmail']}"
        )
        user: dict = fetch_user(email=user_record["userEmail"])
        send_okta_enrollment_email_v2(
            destination_email=user["profile"]["email"],
            attach_instructions=True,
            attachment_path="./documents/Logging Out and Back Into Okta Verify Mobile - Instructional Guide v3.pdf",
            notification_format=True,
            date_of_change=date_of_change,
            subject = f"[FUTURE ACTION REQUIRED] Action will be required on {date_of_change}",
            html_template_path=email_template_path,
        )
        prog_counter+=1


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser(
        description="This script will force un-enroll all Okta Verify PUSH factors, and enroll a brand new push factor, for a list of specified users. It will then send them an email containing the QR code required for enrollment."
    )
    arg_parser.add_argument(
        "--path",
        "-p",
        type=str,
        required=False,
        help="This script requires a list of users to force re-enrollment on, in CSV format. Provide the path to the CSV like '--path users.csv' or '--p users.csv'",
    )
    arg_parser.add_argument(
        "--example",
        "--e",
        action="store_true",
        help="Provide the --example or --e flag to be provided an example of how the CSV should be formatted",
    )
    arg_parser.add_argument(
        "--notification",
        "--n",
        action="store_true",
        help=dedent(
            """
        Provide the --notification, or --n flag to send a proactive email notification to the targeted users to warning them of the upcoming re-enrollment change.
        Using the --notification (--n) flag will also require you to provide a date the change will occur, using the --date (-d) flag. Additionally, you must also provide a 
        path to the user list CSV using the --path (--p) parameter.
        """
        ),
    )
    arg_parser.add_argument(
        "--verifyenrollment",
        "--ve",
        action="store_true",
        help=dedent(
            """
        Provide the --verifyenrollment, or --ve flag to verify that each user listed within the CSV of targeted users has a registered device associated with their user profile.
        This suggests that a user who previously had to re-enroll has successfully done so. This parameter also requires the --path (--p) parameter to be present, with a valid
        path to a CSV list of users to verify. 
        
        NOTE: This workflow will take a long time to run due to the amount of data needing to be retrieved from Okta, and the method with which Okta makes you retrieve it. 
        """
        ),
    )
    arg_parser.add_argument(
        "--usecacheddevices",
        "--cd",
        action="store_true",
        help=dedent(
            """
        Provide the --usecacheddevices, or --cd flag in conjunction with the --verifyenrollment, or --ve flag, in order to use a local 'cached' version of the user to device mappings.
        The file must be named 'user_device_mapping.json'. Running enrollment verification with this flag significantly speeds up the script (as we do not have to
        fetch loads of Data from Okta), HOWEVER, it could lead to inaccurate results. If the cached data is older than the datetime that the users re-enrolled their
        devices, the cached data may not have their newly enrolled device listed, and subsequently the script will report that the user has not enrolled, when they
        may have done so in actuality.
        """
        ),
    )
    arg_parser.add_argument(
        "--date",
        "--d",
        type=str,
        required=False,
        help="Provide the --date, or --d flag in conjunction with the --notification or --n flag, and provide a date that the change will occur on. I.e: '--date 01/31/2024'",
    )
    args = arg_parser.parse_args()
    if args.example:
        logger.info("Below is an example of how to format your CSV file of users:")
        logger.info(
            textwrap.dedent(
                """
                    userName,userFullName,userEmail
                    sv12345@test.com,Sebastian Vettle,SVettle@test.com
                    """
            )
        )
        sys.exit(1)

    if args.path:
        users: list = load_user_list_csv(path=args.path)
    elif os.getenv("USER_CSV_PATH"):
        user: list = load_user_list_csv(path=os.getenv("USER_CSV_PATH"))
    else:
        logger.error(
            f"You must provide {os.path.basename(__file__)} a path to a CSV list of users in 1 of 2 ways:"
        )
        logger.error(
            f"1. Provide the path using command-line arguments. Pass a valid path to a CSV containing the user emails to re-enroll, using the --path or --p parameter."
        )
        logger.error(
            "Please provide this parameter in the following format: --path <path to CSV> or --p <path to CSV>"
        )
        logger.error(
            f"2. Provide the path by configuring the 'USER_CSV_PATH' environment variable."
        )

        logger.info(
            "If you need an example of how to format the CSV, please run the script with the --example flag set."
        )
        sys.exit(1)
    if args.notification:
        logger.debug(f"Flag set to only send notifications to users.")
        if not args.date:
            logger.error(
                "When using the --notification (--n) flag, you must also provide the date of the change using the --date (--d) flag. See --help for more information."
            )
        elif args.date:
            logger.debug(f"Parsed --date value as {args.date}")
            execute_proactive_notification_workflow(
                users=users, date_of_change=args.date
            )
    elif args.verifyenrollment:
        logger.debug("Flag set to only run workflow that verifies users in provided CSV did complete re-enrollment workflow")
        if args.usecacheddevices:
            execute_enrollment_verification_workflow(users=users,useCachedData=True)
        else:
            execute_enrollment_verification_workflow(users=users)
        
    else:
        execute_reenrollment_workflow(users=users)
