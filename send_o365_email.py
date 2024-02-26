import os
import sys
import base64
import logging
import requests
import pandas as pd
from tqdm import tqdm
from urllib.parse import quote
from dotenv import load_dotenv
from datetime import datetime, timedelta
from requests.exceptions import RequestException, ConnectionError, HTTPError, Timeout

# Global variables
logger: logging.Logger
OAUTH_TOKEN: dict = {}
TOKEN_EXPIRATION_TS: datetime = datetime.now()

# Load .env file if needed
load_dotenv()

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
    logger = logging.getLogger("0365_email_wrapper")
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


def fetch_oauth_session() -> dict:
    logger.info("Fetching OAuth access token for MS Graph API.")
    oauth_url = os.getenv("MS_OAUTH_TOKEN_URL")
    oauth_client_id = os.getenv("MS_OAUTH_CLIENT_ID")
    oauth_client_sec = os.getenv("MS_OAUTH_CLIENT_SEC")
    try:
        if oauth_client_id is None:
            raise ValueError("Value of MS_CLIENT_ID environment variable is empty.")
        if oauth_client_sec is None:
            raise ValueError("Value of MS_CLIENT_SEC environment variable is empty.")
        if oauth_url is None:
            raise ValueError(
                "Value of MS_OAUTH_TOKEN_URL environment variable is empty."
            )
    except ValueError as val_error:
        logger.critical(str(val_error))
        sys.exit(1)

    oauth_body = {
        "grant_type": "client_credentials",
        "client_id": oauth_client_id,
        "client_secret": oauth_client_sec,
        "scope": "https://graph.microsoft.com/.default",
    }

    try:
        response = requests.post(url=oauth_url, data=oauth_body)
        response.raise_for_status()
        logger.info("Successfully fetched access token.")
        resp_json = response.json()
        resp_json["fetched_timestamp"] = int(datetime.now().timestamp())
        return resp_json
    except Exception as err:
        logger.critical(
            f"A critical error occurred when attempting to fetch OAuth access token from {oauth_url}."
        )
        logger.critical(str(err))
        sys.exit(1)


def validate_token() -> None:
    global OAUTH_TOKEN
    logger.debug("Checking if OAuth token is expired")
    if OAUTH_TOKEN is None or OAUTH_TOKEN == {}:
        OAUTH_TOKEN = fetch_oauth_session()
    elif is_token_expired():
        logger.debug("OAuth Token was expired, attempting to fetch new one...")
        OAUTH_TOKEN = fetch_oauth_session()


def is_token_expired() -> bool:
    current_time = int(datetime.now().timestamp())
    logger.debug(
        f"Current Timestamp is {current_time}. Token expires at timestamp {OAUTH_TOKEN['fetched_timestamp']+OAUTH_TOKEN['expires_in']}..."
    )
    if (OAUTH_TOKEN["fetched_timestamp"] + OAUTH_TOKEN["expires_in"]) >= current_time:
        logger.debug("Token Expired")
        return False
    else:
        logger.debug("Token valid")
        return True


def load_email_html_template(path: str) -> str:
    logger.info("Loading base HTML template that will be used to send emails...")
    logger.debug(f"Provided path for HTML template is {path}")
    try:
        with open(path, "r") as file:
            file_content = file.read()
    except FileNotFoundError as missing_err:
        logger.critical(f"No HTML file was found at path {path}. Terminating script as there is no valid template to base emails off of.")
        logger.info("A critical error occurred while trying to load the HTML template used to send notification emails. The script has terminated")
        sys.exit(1)
    except Exception as err:
        logger.critical(f"A generic exception occurred when trying to open HTML template at {path}. See error below. Script will terminate")
        logger.info("A generic error occurred when attempting to load HTML template for sending emails. Script will exit due to this error.")
        logger.critical(str(err))
        sys.exit(1)
    return file_content


def load_file_attachment(path: str) -> dict or None:
    logger.debug(f"Attempting to load contents of {path} into Script... This file will be attached to notification emails.")
    path_struct = path.split("/")
    filename = path_struct[len(path_struct)-1]
    
    attachment_obj = {
        "name": filename
    }
    try:
        with open(path, 'rb') as file:
            file_data = file.read()
            encoded_file_content = base64.b64encode(file_data).decode('utf-8')
            attachment_obj.update({"encoded_content":encoded_file_content})
            logger.debug(f"Successfully loaded and Base64 encoded the contents of {filename}")
            return attachment_obj
    except Exception as err:
        logger.error(f"An error occurred while trying to load file attachment {path} into script.")
        logger.error(str(err))
        return None


def send_okta_enrollment_email(
    source_email: str = "security@mycompany.com",
    destination_email: str = None,
    qr_code_url: str = None,
    attach_instructions: bool = False,
) -> None:
    logger.info(
        f"Attempting to send Okta re-enrollment notification email to {destination_email}..."
    )
    logger.info("Checking OAuth expiration")
    validate_token()
    html_template = load_email_html_template(
        path="./email_templates/enrollment_email_template.html"
    )

    logger.info("Sending email...")

    if len(destination_email) <= 0:
        logger.info(
            "The destination email is empty, please provide a valid email and try again."
        )
        logger.error(
            "The value of destnation_email is None. No email can be sent, as there is no valid recepient."
        )
        return
    if html_template is None:
        logger.info(
            f"Valid HTML Email template was not supplied. Email to {destination_email} will not send..."
        )
        logger.error(
            f"The value of html_template is None. A valid HTML template is required to send Okta notification email to {destination_email}. No email will be sent."
        )
        return
    if qr_code_url is None:
        logger.info(
            f"A valid Okta enrollment QR code URL was not provided. Email to {destination_email} will not be sent."
        )
        logger.error(
            f"The value of qr_code_url is None. A valid QR code image URL is required to send Okta notification email to {destination_email}. No email will be sent."
        )
        return

    html_template_updated = html_template.replace(
        "REPLACE WITH QR CODE URL", qr_code_url
    )

    header = {
        "Authorization": f"Bearer {OAUTH_TOKEN['access_token']}",
        "Content-Type": "application/json",
    }

    full_url = f"https://graph.microsoft.com/v1.0/users/{source_email}/sendMail"

    mail_payload = {
        "message": {
            "subject": "[ACTION REQUIRED] You are required to sign back into Okta Verify",
            "body": {
                "contentType": "HTML",
                "content": html_template_updated,
            },
            "toRecipients": [{"emailAddress": {"address": destination_email}}],
        },
        "saveToSentItems": "true",
    }
    if attach_instructions:
        logger.info(f"Flag was set to include enrollment instructions in email to {destination_email}")
        file_attachment = load_file_attachment(path="./documents/Logging Out and Back Into Okta Verify Mobile - Instructional Guide v1.pdf")
        
        if file_attachment is not None:
            logger.info(f"Instructions for enrollment procedure will be attached to email to {destination_email}")
            mail_payload['message'].update(
                {
                    "hasAttachments": True,
                    "attachments": [{
                        "@odata.type": "#microsoft.graph.fileAttachment",
                        "name": file_attachment["name"],
                        "contentType":"application/pdf",
                        "contentBytes":file_attachment['encoded_content']
                    }],
                }
            )
    else:
        logger.info(f"Flag to attach enrollment procedure docuemtnation was not set. No file with be attached to the email to {destination_email}")

    try:
        response = requests.post(url=full_url, headers=header, json=mail_payload)
        response.raise_for_status()
        logger.info(
            f"Successfully sent email from {source_email} to {destination_email}..."
        )
    except Exception as err:
        logger.critical(f"A critical error occurred when attempting to send email")
        logger.critical(str(err))
        sys.exit(1)


def send_okta_enrollment_email_v2(
    source_email: str = "security@yourcompany.com",
    destination_email: str = None,
    attach_instructions: bool = False,
    attachment_path: str = None,
    notification_format: bool = False,
    date_of_change: str = None,
    subject: str = "[ACTION REQUIRED] You are required to sign back into Okta Verify",
    html_template_path: str = "./email_templates/enrollment_email_template_v2.html"
) -> None:
    if notification_format:
        logger.info(f"Sending email to {destination_email} to notify user of upcoming change requirements.")
    else:
        logger.info(
            f"Attempting to send Okta re-enrollment notification email to {destination_email}..."
        )
    logger.info("Checking OAuth expiration")
    validate_token()
    html_template = load_email_html_template(
        path=html_template_path
    )
    
    if notification_format:
        logger.debug(f"Attempting to replace the '&lt;DATE&gt;' placeholder in the HTML template with the provided date: {date_of_change}")
        html_template = html_template.replace("&lt;DATE&gt;",date_of_change)

    if len(destination_email) <= 0:
        logger.info(
            "The destination email is empty, please provide a valid email and try again."
        )
        logger.error(
            "The value of destnation_email is None. No email can be sent, as there is no valid recepient."
        )
        return
    if html_template is None:
        logger.info(
            f"Valid HTML Email template was not supplied. Email to {destination_email} will not send..."
        )
        logger.error(
            f"The value of html_template is None. A valid HTML template is required to send Okta notification email to {destination_email}. No email will be sent."
        )
        return


    header = {
        "Authorization": f"Bearer {OAUTH_TOKEN['access_token']}",
        "Content-Type": "application/json",
    }

    full_url = f"https://graph.microsoft.com/v1.0/users/{source_email}/sendMail"

    mail_payload = {
        "message": {
            "subject": f"{subject}",
            "body": {
                "contentType": "HTML",
                "content": html_template,
            },
            "toRecipients": [{"emailAddress": {"address": destination_email}}],
        },
        "saveToSentItems": "true",
    }
    if attach_instructions:
        logger.debug(f"Flag was set to include attachment in email to {destination_email}.")
        logger.debug(f"Attachment local filepath is {attachment_path}")
        file_attachment = load_file_attachment(path=attachment_path)
        
        if file_attachment is not None:
            logger.info(f"Instructions for enrollment procedure will be attached to email to {destination_email}")
            mail_payload['message'].update(
                {
                    "hasAttachments": True,
                    "attachments": [{
                        "@odata.type": "#microsoft.graph.fileAttachment",
                        "name": file_attachment["name"],
                        "contentType":"application/pdf",
                        "contentBytes":file_attachment['encoded_content']
                    }],
                }
            )
    else:
        logger.info(f"Flag to attach enrollment procedure docuemtnation was not set. No file with be attached to the email to {destination_email}")

    try:
        logger.info(f"Sending email to {destination_email}...")
        response = requests.post(url=full_url, headers=header, json=mail_payload)
        response.raise_for_status()
        logger.info(
            f"Successfully sent email from {source_email} to {destination_email}..."
        )
    except Exception as err:
        logger.critical(f"A critical error occurred when attempting to send email")
        logger.critical(str(err))
        sys.exit(1)



def send_email(
    source_email: str = "security@siteone.com", destination_email_list: list = None
) -> None:
    logger.info("Checking OAuth expiration")
    validate_token()

    logger.info("Sending email...")

    if len(destination_email_list) <= 0:
        logger.info(
            "The list of destination emails is empty, please provide a valid list of emails and try again."
        )
        logger.critical("The list of destination emails was not populated.")
        sys.exit(1)

    destination_email_obj = []

    for email in destination_email_list:
        destination_email_obj.append({"emailAddress": {"address": email}})

    header = {
        "Authorization": f"Bearer {OAUTH_TOKEN['access_token']}",
        "Content-Type": "application/json",
    }

    full_url = f"https://graph.microsoft.com/v1.0/users/{source_email}/sendMail"

    mail_payload = {
        "message": {
            "subject": "Test Message from Your Company Security",
            "body": {
                "contentType": "Text",
                "content": "TEST TEST TEST - From Python",
            },
            "toRecipients": destination_email_obj,
        },
        "saveToSentItems": "false",
    }
    try:
        response = requests.post(url=full_url, headers=header, json=mail_payload)
        response.raise_for_status()
        logger.info(
            f"Successfully sent email from {source_email} to {len(destination_email_list)} recepients..."
        )
    except Exception as err:
        logger.critical(f"A critical error occurred when attempting to send email")
        logger.critical(str(err))
        sys.exit(1)


################
# Main script flow
################
if __name__ == "__main__":
    # Initialize logger
    logger.info("Initalized logger...")

    # Fetch access token
    OAUTH_TOKEN = fetch_oauth_session()
    logger.info("Fetched OAuth token...")

    send_okta_enrollment_email(
        destination_email="tobarowski@siteone.com",
        qr_code_url="https://images.squarespace-cdn.com/content/v1/6155e54045f7787728e27225/a2120a69-26f7-45a4-9073-ba2e1b93ecab/SiteOne_StoneCenter_Logo-Web_C.png",
        attach_instructions=True
    )
    # send_okta_enrollment_email(html_template=html_template,destination_email="jlehman@siteone.com",qr_code_url="https://images.squarespace-cdn.com/content/v1/6155e54045f7787728e27225/a2120a69-26f7-45a4-9073-ba2e1b93ecab/SiteOne_StoneCenter_Logo-Web_C.png")
