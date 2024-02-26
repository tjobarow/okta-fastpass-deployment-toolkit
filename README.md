
# Okta Workforce (OIE) FastPass Deployment Toolkit

This toolkit helps you identify, and the force end users to re-enroll their Okta Verify (mobile phone) factors with Okta Workforce Identity Engine. This is valuable, as a prerequisite to implementing device trust controls within your Okta tenant is to ensure each user is enrolled with Okta FastPass, and subsequently has a device registered to their Okta account. If your Okta deployment existed prior to Identity Engine, it is likely that a large subset of your user base does not have a registered device, and is not enrolled in FastPass. 

By using this toolkit, you can identify users that will need to "re-enroll" their device on a per app basis, and separately reset their Okta Verify factor(s), forcing them to enroll in Okta FastPass. The script includes mechanisms to email notifications to end users informing them that they will need to sign back into Okta Verify on a future date, as well as a notification that they have been signed out of Okta Verify, and need to sign back in. 

*The email templates and documentation that is sent to users is excluded due to privacy reasons. You will need to create these on your own, and change the scripting to utilize them. 


## Installation

### Dependencies

The following dependencies are required between the two scripts.

#### Python Version

Python v3.10 or greater

#### Python Modules

```bash
certifi==2023.11.17
charset-normalizer==3.3.2
idna==3.6
numpy==1.26.3
pandas==2.1.4
python-dateutil==2.8.2
python-dotenv==1.0.0
pytz==2023.3.post1
requests==2.31.0
six==1.16.0
tqdm==4.66.1
tzdata==2023.4
urllib3==2.1.0

```
    
## Usage/Examples

### Finding users that will need to re-enroll
#### Populate okta_apps.csv
First, populate the ```okta_apps.csv``` file with the names (labels) of Okta applications you wish to target in the script.
#### Configure .env file
Make sure to populate the ```.env``` file with your __Okta API token__, __Okta URL__, and __Log file name__.
#### Install dependencies
Install python dependencies 
```bash
pip install -r requirements.txt
```
#### Run the script
Run the script ```find_app_users_no_device.py```. The script *may take a long time to run* due to the way the Okta implements user-device relationships. Eventually, it will generate a CSV with a name like ```<current_date>_unique_okta_users_for_reenrollment.csv```.

```bash
python3.10 find_app_users_no_device.py
```

TO BE CONTINUED

## Authors

- Thomas Obarowski - [@tjobarow (GitHub)](https://www.github.com/tjobarow) / [Thomas Obarowski (LinkedIn)](https://www.linkedin.com/in/tjobarow/)

