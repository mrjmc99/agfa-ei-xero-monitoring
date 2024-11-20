import base64
import json
import urllib
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
import ast
import requests
import os
import configparser
import paramiko
import logging
import uuid
from time import sleep
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import concurrent.futures
import cx_Oracle
import urllib3

# ignore insecure warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Set up logging
logging.basicConfig(
    filename='xero_ticket.log',
    level=logging.ERROR,
    format='%(asctime)s [%(levelname)s]: %(message)s',
)

# Get the absolute path of the script
script_dir = os.path.dirname(os.path.abspath(__file__))

# Construct the absolute path of the configuration file
config_file_path = os.path.join(script_dir, "xeroticket.ini")

# Load the configuration file
config = configparser.ConfigParser()
config.read(config_file_path)

# Xero API Variables
xero_user = config.get("Xero", "xero_user")
xero_password = config.get("Xero", "xero_password")
xero_domain = config.get("Xero", "xero_domain")
xero_query_constraints = config.get("Xero", "xero_query_constraints")
xero_nodes = config.get("Xero", "xero_nodes").split(',')
xero_restart_command = config.get("Xero", "xero_restart_command")
xero_disable_command = config.get("Xero", "xero_disable_command")
xero_wado_purge_command = config.get("Xero", "xero_wado_purge_command")
xero_server_user = config.get("Xero", "xero_server_user")
xero_server_private_key = config.get("Xero", "xero_server_private_key")
xero_get_ticket_timeout = int(config.get("Xero", "xero_get_ticket_timeout"))
xero_ticket_validation_timeout = int(config.get("Xero", "xero_ticket_validation_timeout"))
xero_wado = ast.literal_eval(config.get("Xero", "xero_wado"))
validation_study_PatientID = config.get("Xero", "validation_study_PatientID")
validation_study_AccessionNumber = config.get("Xero", "validation_study_AccessionNumber")
xero_theme = config.get("Xero", "theme")
disabled_servers_file = os.path.join(script_dir, config.get("Xero", "disabled_servers_file"))
cluster_db_host = config.get("Xero", "cluster_db_host")
cluster_db_port = config.get("Xero", "cluster_db_port")
cluster_db_service_name = config.get("Xero", "cluster_db_service_name")
cluster_db_user = config.get("Xero", "cluster_db_user")
cluster_db_password = config.get("Xero", "cluster_db_password")


query_constraints = f"PatientID={validation_study_PatientID}, AccessionNumber={validation_study_AccessionNumber}"
display_vars = f"theme={xero_theme}, PatientID={validation_study_PatientID}, AccessionNumber={validation_study_AccessionNumber}"



# email variables
smtp_server = config.get("Email", "smtp_server")
smtp_port = int(config.get("Email", "smtp_port"))
smtp_username = config.get("Email", "smtp_username")
smtp_password = config.get("Email", "smtp_password")
smtp_from_domain = config.get("Email", "smtp_from_domain")
smtp_recipients_string = config.get("Email", "smtp_recipients")
smtp_recipients = smtp_recipients_string.split(",")

# meme variables
use_memes = ast.literal_eval(config.get("Meme", "use_memes"))
successful_restart_meme_path = os.path.join(script_dir, 'memes', config.get("Meme", "successful_restart_meme"))
unsuccessful_restart_meme_path = os.path.join(script_dir, 'memes', config.get("Meme", "unsuccessful_restart_meme"))
temp_meme_path = os.path.join(script_dir, os.path.dirname('memes'), 'temp_meme.jpg')
font_path = os.path.join(script_dir, 'fonts', config.get("Meme", "font"))

# service now variables
service_now_instance = config.get("ServiceNow", "instance")
service_now_table = config.get("ServiceNow", "table")
service_now_api_user = config.get("ServiceNow", "api_user")
service_now_api_password = config.get("ServiceNow", "api_password")
ticket_type = config.get("ServiceNow", "ticket_type")
configuration_item = config.get("ServiceNow", "configuration_item")
assignment_group = config.get("ServiceNow", "assignment_group")
assignee = config.get("ServiceNow", "assignee")
business_hours_start_time = config.get("ServiceNow", "business_hours_start_time")
business_hours_end_time = config.get("ServiceNow", "business_hours_end_time")
after_hours_urgency = config.get("ServiceNow", "after_hours_urgency")
after_hours_impact = config.get("ServiceNow", "after_hours_impact")
business_hours_urgency = config.get("ServiceNow", "business_hours_urgency")
business_hours_impact = config.get("ServiceNow", "business_hours_impact")

# print(f"xero_restart_command: {xero_restart_command}")
# print(f"xero_disable_command: {xero_disable_command}")


# Get the current time and day of the week
current_time = datetime.now().time()
current_day = datetime.now().weekday()

# Define business hours
business_hours_start = datetime.strptime(business_hours_start_time, "%H:%M:%S").time()
business_hours_end = datetime.strptime(business_hours_end_time, "%H:%M:%S").time()

# Set default values
urgency = after_hours_urgency  # Default value for after hours and weekends
impact = after_hours_urgency  # Default value for after hours and weekends

# Check if it's business hours
if business_hours_start <= current_time <= business_hours_end and current_day < 5:  # Monday to Friday
    urgency = business_hours_urgency
    impact = business_hours_impact

local_time_str = datetime.now().time()

def generate_meme(image_path, top_text, bottom_text, output_path):
    # Open the image
    img = Image.open(image_path)
    draw = ImageDraw.Draw(img)

    # Load a TrueType font
    font_size = 20  # Adjust the font size as needed
    font = ImageFont.truetype(font_path, font_size)

    # Add top text
    top_text_width = draw.textlength(top_text, font)
    draw.text(((img.width - top_text_width) // 2, 10), top_text, (255, 255, 255), font=font)

    # Add bottom text
    bottom_text_width = draw.textlength(bottom_text, font)
    draw.text(((img.width - bottom_text_width) // 2, img.height - 10), bottom_text, (255, 255, 255), font=font)

    # Save the meme
    img.save(output_path)
    return output_path


# Function to load disabled servers from file
def load_disabled_servers():
    try:
        with open(disabled_servers_file, 'r') as file:
            content = file.read().strip()
            if not content:  # Check if the file is blank
                raise ValueError("File is blank")
            disabled_servers = json.loads(content)  # Load as JSON
        return disabled_servers
    except (FileNotFoundError, ValueError, json.JSONDecodeError):
        # Create a new file or replace a blank file with an empty dictionary
        with open(disabled_servers_file, 'w') as file:
            json.dump({}, file)
        return {}


# Function to Save disabled servers to file
def save_disabled_server(xero_server, incident_number):
    disabled_servers = load_disabled_servers()
    disabled_servers[xero_server] = incident_number  # Add server and incident number to dictionary
    with open(disabled_servers_file, 'w') as file:
        json.dump(disabled_servers, file)  # Save as JSON


# Function to check for disabled server from file
def is_server_disabled(xero_server):
    disabled_servers = load_disabled_servers()
    return xero_server in disabled_servers


# Function to remove server from disabled list
def remove_disabled_server(xero_server):
    disabled_servers = load_disabled_servers()
    if xero_server in disabled_servers:
        incident = disabled_servers[xero_server]  # Extract the incident number from the dictionary
        if incident == 'PREPARE':
            subject = f"Xero Ticketing/Image Display has been Restored on {xero_server} at {local_time_str}"
            body = f"Xero Ticketing/Image Display has been Restored on {xero_server} at {local_time_str}"
        else:
            subject = f"Xero Ticketing/Image Display has been Restored on {xero_server} at {local_time_str}"
            body = f"Xero Ticketing/Image Display has been Restored on {xero_server} at {local_time_str}\nPlease Close {incident}"
        send_email(smtp_recipients, subject, body, xero_server)
        del disabled_servers[xero_server]  # Remove server from dictionary
        with open(disabled_servers_file, 'w') as file:
            json.dump(disabled_servers, file)  # Save as JSON



# Function to encode an image as base64
def image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        encoded_image = base64.b64encode(image_file.read()).decode("utf-8")
    return encoded_image


# Function to send plain text email
def send_email(smtp_recipients, subject, body, node):
    smtp_from = f"{node}@{smtp_from_domain}"
    msg = MIMEText(body)
    msg["From"] = smtp_from
    msg["To"] = ", ".join(smtp_recipients)  # Join smtp_recipients with a comma and space
    msg["Subject"] = subject

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.sendmail(smtp_from, smtp_recipients, msg.as_string())
        server.quit()
        print(f"Email sent to {', '.join(smtp_recipients)}")
    except Exception as e:
        print(f"Email sending failed to {', '.join(smtp_recipients)}: {e}")


# Function to send an email with the generated meme embedded in the body
def send_email_meme(smtp_recipients, subject, body, node, meme_path):
    smtp_from = f"{node}@{smtp_from_domain}"
    msg = MIMEMultipart()
    msg["From"] = smtp_from
    msg["To"] = ", ".join(smtp_recipients)  # Join smtp_recipients with a comma and space
    msg["Subject"] = subject

    # Attach the text body
    msg.attach(MIMEText(body, 'plain'))

    # Embed the generated meme in the body
    meme_data = image_to_base64(meme_path)
    meme_cid = 'meme_image'
    msg.attach(MIMEText(f'<img src="data:image/jpeg;base64,{meme_data}" alt="Meme" />', 'html'))
    msg.attach(MIMEImage(base64.b64decode(meme_data), name='meme.jpg'))
    msg.get_payload()[1]._headers.append(('Content-ID', f'<{meme_cid}>'))
    msg.get_payload()[1]._headers.append(('Content-Disposition', f'inline; filename="{meme_cid}"'))

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.sendmail(smtp_from, smtp_recipients, msg.as_string())
        server.quit()
        print(f"Meme Email sent to {', '.join(smtp_recipients)}")
    except Exception as e:
        print(f"Meme Email sending failed to {', '.join(smtp_recipients)}: {e}")



def create_service_now_incident(summary, description, configuration_item, external_unique_id, urgency, impact):
    incident_api_url = f"https://{service_now_instance}/api/now/table/{service_now_table}"

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payload = {
        "u_short_description": summary,
        "u_description": description,
        "u_affected_user_id": "",
        "u_configuration_item": configuration_item,
        "u_external_unique_id": external_unique_id,
        "u_urgency": urgency,
        "u_impact": impact,
        "u_type": ticket_type,
        "u_assignment_group": assignment_group,
    }

    try:
        # print("Incident Creation Payload:", payload)  # Print payload for debugging
        response = requests.post(
            incident_api_url,
            headers=headers,
            auth=(service_now_api_user, service_now_api_password),
            json=payload,
        )

        # print("Incident Creation Response Status Code:", response.status_code)  # Print status code for debugging
        # print("Incident Creation Response Content:", response.text)  # Print response content for debugging

        if response.status_code == 201:
            incident_number = response.json().get("result", {}).get("u_task_string")
            sys_id = response.json().get('result', {}).get('u_task', {}).get('value')
            print(f"ServiceNow incident created successfully: {incident_number}")
            return incident_number
        else:
            print(f"Failed to create ServiceNow incident. Response: {response.text}")

    except requests.exceptions.RequestException as e:
        print(f"An error occurred while creating ServiceNow incident: {e}")

    return None


def get_xero_ticket(xero_server):
    api_url = f"https://{xero_server}/encodedTicket"

    # URL encode the query constraints and display vars
    query_constraints_encoded = urllib.parse.quote(query_constraints)
    display_vars_encoded = urllib.parse.quote(display_vars)
    #print(query_constraints_encoded)
    #print(display_vars_encoded)
    payload = {
        "user": xero_user,
        "password": xero_password,
        "domain": xero_domain,
        "queryConstraints": query_constraints_encoded,
        #"initialDisplay": display_vars_encoded,
        "ticketDuration": "300",
        "uriEncodedTicket": "true",
        "ticketUser": "TICKET_TESTING_USER",
        "ticketRoles": "EprUser",
    }

    headers = {}

    try:
        print(f"Testing Ticket Creation for {xero_server}")
        response = requests.post(api_url, headers=headers, data=payload, verify=False, timeout=xero_get_ticket_timeout)
        print(f"{xero_server} Ticket Creation Response Status Code:",
              response.status_code)  # Print status code for debugging
        if response.status_code == 200:
            print(f"{xero_server} created a ticket successfully")
            #print(response.text)
            return response.text
        else:
            print(f"{xero_server} Ticket Creation Failure")
            return None

    except requests.exceptions.RequestException as e:
        print(f"An error occurred while attempting to create xero tickets on {xero_server}: {e}")
        return None

def get_xero_ticket_old(xero_server):
    api_url = f"https://{xero_server}/encodedTicket?user={xero_user}&password={xero_password}&ticketUser=TICKET_TESTING_USER&ticketDuration=600&ticketRoles=EprUser&queryConstraints={xero_query_constraints}&uriEncodedTicket=true&domain={xero_domain}"

    payload = {}
    headers = {}

    try:
        print(f"Testing Ticket Creation for {xero_server}")
        response = requests.request("POST", api_url, headers=headers, data=payload, verify=False, timeout=xero_get_ticket_timeout)

        print(f"{xero_server} Ticket Creation Response Status Code:",
              response.status_code)  # Print status code for debugging
        # print(f"{xero_server} Ticket Creation Response Content:",
        # response.text)  # Print response content for debugging
        xero_ticket = response.text

        if response.status_code == 200:
            print(f"{xero_server} created a ticket successfully")
            return xero_ticket
        else:
            print(f"{xero_server} Ticket Creation Failure")
            return None

    except requests.exceptions.RequestException as e:
        print(f"An error occurred while attempting to create xero tickets on {xero_server}: {e}")

    return None


def verify_ticket(xero_server, xero_ticket):
    try:
        # Append the ticket as a query parameter to the verification URL
        #verification_url = f"https://{xero_server}/?ticket={xero_ticket}"
        verification_url = f"https://{xero_server}/?PatientID={validation_study_PatientID}&AccessionNumber={validation_study_AccessionNumber}&theme={xero_theme}&ticket={xero_ticket}"
        #print(verification_url)
        #print(xero_ticket)
        response = requests.get(verification_url, verify=False, timeout=xero_ticket_validation_timeout)

        print(f"{xero_server} Verification URL Response Status Code: {response.status_code}")
        # print(f"Verification URL Response Content: {response.text}")

        if response.status_code == 200:
            print(f"{xero_server} Ticket verification successful")
            return True
        else:
            print(f"{xero_server} Ticket verification failed")
            return False

    except requests.exceptions.RequestException as e:
        print(f"An error occurred while attempting to verify the ticket: {e}")
        return False

def clear_wado_cache(xero_server):
    api_url = f"https://{xero_server}/wado/?clearfilecache=true&requesttype=clearcache&user={xero_user}&password={xero_password}"

    payload = {}
    headers = {}

    try:
        print(f"Executing Clear Cluster Wado Cache against {xero_server}")
        response = requests.request("POST", api_url, headers=headers, data=payload, verify=False,
                                    timeout=10)

        print(f"{xero_server} Clear Cluster Wado Cache Response Status Code:",
              response.status_code)  # Print status code for debugging
        # print(f"{xero_server} Ticket Creation Response Content:",
        # response.text)  # Print response content for debugging

        if response.status_code == 200:
            print(f"{xero_server} Clear Cluster Wado Cache successfully")
            return True
        else:
            print(f"{xero_server} Clear Cluster Wado Cache Failure")
            return None

    except requests.exceptions.RequestException as e:
        print(f"An error occurred while attempting to Clear Cluster Wado Cache on {xero_server}: {e}")

    return None


#  check for upgrade pending/inprogress
def check_for_upgrade(xero_server):
    # Oracle database connection details
    dsn = cx_Oracle.makedsn(cluster_db_host, cluster_db_port, service_name=cluster_db_service_name)
    connection = cx_Oracle.connect(user=cluster_db_user, password=cluster_db_password, dsn=dsn)

    query = """
    select t.installstage "Installation Stage", inode.id "Cluster node"
    from installer_node inode,
    xmltable('/installStatus' 
        passing xmltype(inode.status) 
        columns 
            installstage varchar2(64) path 'stage',
            uninstalled varchar2(64) path 'uninstall'
        ) t
    where upper(inode.id) like upper(:xero_server)
    and uninstalled = 'false'
    and installstage = 'PREPARE'
    """

    try:
        cursor = connection.cursor()
        cursor.execute(query, xero_server=f"{xero_server}%")
        result = cursor.fetchone()
        print(f"upgrade check for {xero_server} result is:{result}")
        return result is not None
    except cx_Oracle.DatabaseError as e:
        print(f"Database error occurred: {e}")
        return False
    finally:
        cursor.close()
        connection.close()


def restart_xero_server(xero_server):
    try:
        print(f"attempting to restart {xero_server}")
        result = execute_remote_command(
            xero_server,
            xero_server_user,
            xero_server_private_key,
            xero_restart_command,
        )
    except Exception as e:
        logging.error(f"Error restarting Xero server ({xero_server}): {e}")
        subject = f"Xero Ticketing/Image Display is failing on {xero_server} at {local_time_str} (Unable to connect to server) (Ticket Creation Failure))"
        body = f"Xero Ticketing/Image Display is failing on {xero_server} at {local_time_str} (Unable to connect to server)/nPlease investigate"
        incident_summary = f"Xero Ticketing/Image Display is failing on {xero_server} at {local_time_str} (Unable to connect to server)"
        incident_description = body
        external_unique_id = str(uuid.uuid4())
        incident_number = create_service_now_incident(
            incident_summary, incident_description,
            configuration_item, external_unique_id,
            urgency, impact
        )
        if incident_number:
            print(incident_number)
            subject = f"Xero Ticketing/Image Display is failing on {xero_server} at {local_time_str} (Unable to connect to server) {incident_number}"
        send_email(smtp_recipients, subject, body, xero_server)
    else:
        logging.info(f"Xero server restarted successfully: {result}")

    return None


def purge_local_wado_cache(xero_server):
    try:
        print("attempting to Purge Local Wado Cache")
        result = execute_remote_command(
            xero_server,
            xero_server_user,
            xero_server_private_key,
            xero_wado_purge_command,
        )
    except Exception as e:
        logging.error(f"Error Purging Local Wado Cache on Xero server ({xero_server}): {e}")

    else:
        logging.info(f"Xero server Wado Cache Purged successfully: {result}")

    return True


def disable_xero_server(xero_server):
    try:
        print("attempting to disable xero")
        result = execute_remote_command(
            xero_server,
            xero_server_user,
            xero_server_private_key,
            xero_disable_command,
        )
    except Exception as e:
        logging.error(f"Error Disabling Xero server ({xero_server}): {e}")
        subject = f"Xero Ticketing/Image Display is failing on {xero_server} at {local_time_str} (Unable to connect to server) (Ticket Creation Failure))"
        body = f"Xero Ticketing/Image Display is failing on {xero_server} at {local_time_str} (Unable to connect to server)/nPlease investigate"
        incident_summary = f"Xero Ticketing/Image Display is failing on {xero_server} at {local_time_str} (Unable to connect to server)"
        incident_description = body
        external_unique_id = str(uuid.uuid4())
        incident_number = create_service_now_incident(
            incident_summary, incident_description,
            configuration_item, external_unique_id,
            urgency, impact
        )
        if incident_number:
            print(incident_number)
            subject = f"Xero Ticketing/Image Display is failing on {xero_server} at {local_time_str} (Unable to connect to server) {incident_number}"
            save_disabled_server(xero_server, incident_number)
        else:
            save_disabled_server(xero_server, "Ticket Creation Failed")
        if use_memes:
            generate_meme(unsuccessful_restart_meme_path, "ONE DOES NOT SIMPLY",f"RESTART XERO SERVICES ON {xero_server}", temp_meme_path)
            send_email_meme(smtp_recipients, subject, body, xero_server, temp_meme_path)
            os.remove(temp_meme_path)
        else:
            send_email(smtp_recipients, subject, body, xero_server)
    else:
        logging.info(f"Xero server Disabling successfully: {result}")
        subject = f"Xero Ticketing/Image Display has been Disabled on {xero_server} at {local_time_str}"
        body = f"Xero Ticketing/Image Display has been Disabled on {xero_server} at {local_time_str}\nTo manually purge cache run the following command: sudo /bin/nice -n +15 /bin/find /wado2cache* -mmin +240 -delete \nTo enable the server run the following command on the xero server: sudo agility-haproxy start"
        incident_summary = f"Xero Ticketing/Image Display is failing on {xero_server} at {local_time_str} (Server Disabled)"
        incident_description = body
        external_unique_id = str(uuid.uuid4())
        incident_number = create_service_now_incident(
            incident_summary, incident_description,
            configuration_item, external_unique_id,
            urgency, impact
        )
        if incident_number:
            print(incident_number)
            subject = f"Xero Ticketing/Image Display has been Disabled on {xero_server} at {local_time_str} {incident_number}"
            save_disabled_server(xero_server,incident_number)
        else:
            save_disabled_server(xero_server, "Ticket Creation Failed")
        if use_memes:
            generate_meme(unsuccessful_restart_meme_path, "ONE DOES NOT SIMPLY",f"RESTART XERO SERVICES ON {xero_server}", temp_meme_path)
            send_email_meme(smtp_recipients, subject, body, xero_server, temp_meme_path)
            os.remove(temp_meme_path)
        else:
            send_email(smtp_recipients, subject, body, xero_server)
    return None  # Return the result or another suitable value


def execute_remote_command(hostname, username, private_key_path, command):
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(hostname, username=username, key_filename=private_key_path)
        stdin, stdout, stderr = ssh.exec_command(command)
        output = stdout.read().decode()
        error = stderr.read().decode()

        result = {'output': output, 'error': error}
        ssh.close()
        return result
    except Exception as e:
        print(f"Error executing remote command: {e}")
        return None


def test_xero(xero_server,xero_ticket):
    verification_status = verify_ticket(xero_server, xero_ticket)
    if verification_status:
        if is_server_disabled(xero_server):
            print(f"Xero services restored on {xero_server}, removing from Disabled Servers File")
            remove_disabled_server(xero_server)
            return True
        return True
    else:
        print(f"Ticket Validation failed for {xero_server}")
        if is_server_disabled(xero_server):
            print(f"Skipping {xero_server} - Server is already disabled.")
            return False
        restart_xero_server(xero_server)
        print("Restart Completed, waiting 10 seconds to retest")
        sleep(10)
        verification_status = verify_ticket(xero_server, xero_ticket)
        if verification_status:
            subject = f"Xero Ticketing/Image Display has been restored on {xero_server} at {local_time_str}"
            body = f"Xero Ticketing/Image Display has been restored on {xero_server} at {local_time_str}"
            send_email(smtp_recipients, subject, body, xero_server)
            return True
        return False


def wado_clear_and_retest(xero_server):
    wado_cache = clear_wado_cache(xero_server)

    if wado_cache:
        print("Cluster Wado Cache Cleared, waiting 10 seconds to retest")
        sleep(10)
        xero_ticket = get_xero_ticket(xero_server)

        if xero_ticket:
            verification_status = verify_ticket(xero_server, xero_ticket)

            if verification_status:
                subject = f"Xero Ticketing/Image Display has been restored on {xero_server} at {local_time_str} (Cluster Wado Cache Cleared)"
                body = f"Xero Ticketing/Image Display has been restored on {xero_server} at {local_time_str} (Cluster Wado Cache Cleared)"
                send_email(smtp_recipients, subject, body, xero_server)
            else:
                disable_xero_server(xero_server)
                return
    else:
        disable_xero_server(xero_server)
    return


def local_wado_purge_and_retest(xero_server):
    wado_cache = purge_local_wado_cache(xero_server)

    if wado_cache:
        print("Local Wado Cache Cleared, waiting 10 seconds to retest")
        sleep(10)
        xero_ticket = get_xero_ticket(xero_server)

        if xero_ticket:
            verification_status = verify_ticket(xero_server, xero_ticket)

            if verification_status:
                subject = f"Xero Ticketing/Image Display has been restored on {xero_server} at {local_time_str} (Local Wado Cache Cleared)"
                body = f"Xero Ticketing/Image Display has been restored on {xero_server} at {local_time_str} (Local Wado Cache Cleared)"
                send_email(smtp_recipients, subject, body, xero_server)
            else:
                disable_xero_server(xero_server)
                return
    else:
        disable_xero_server(xero_server)
    return


def notify_failed_server_pending_upgrade(xero_server):
    subject = f"Xero Ticketing/Image Display Failing on {xero_server} at {local_time_str} (Server in PREPARE Status)"
    body = f"Xero Ticketing/Image Display Failing on {xero_server} at {local_time_str} (Server in PREPARE Status)\n The server will has been placed on the disabled servers lists, and will be removed automacailly after the upgrade is complete and ticketing is validated."
    send_email(smtp_recipients, subject, body, xero_server)
    save_disabled_server(xero_server, "PREPARE")
    return


def process_node(node):
    xero_ticket = get_xero_ticket(node)
    server_in_prepare_status = check_for_upgrade(node)
    if xero_ticket:
        test_xero(node,xero_ticket)
        if test_xero:
            return
        else:
            if is_server_disabled(node):
                print(f"Skipping {node} - Server is already disabled.")
                return
            else:
                if server_in_prepare_status:
                    notify_failed_server_pending_upgrade(node)
                    return
                else:
                    restart_xero_server(node)
                    print("Restart Completed, waiting 10 seconds to retest")
                    sleep(10)
                    xero_ticket = get_xero_ticket(node)

                    if xero_ticket:
                        verification_status = verify_ticket(node, xero_ticket)
                        if verification_status:
                            return
                        else:
                            local_wado_purge_and_retest(node)

                    else:
                        print(f"Ticket Creation failed for {node} Disabling Server")
                        disable_xero_server(node)


    else:
        if is_server_disabled(node):
            print(f"Skipping {node} - Server is already disabled.")
            return
        print(f"Ticket Creation failed for {node}")
        print(f"check for upgrade:{server_in_prepare_status}")
        if server_in_prepare_status:
            print(f"Skipping {node} - Server is in a PREPARE Status")
            notify_failed_server_pending_upgrade(node)
            return
        restart_xero_server(node)
        print("Restart Completed, waiting 10 seconds to retest")
        sleep(10)
        xero_ticket = get_xero_ticket(node)

        if xero_ticket:
            verification_status = verify_ticket(node, xero_ticket)
            if verification_status:
                return
            else:
                local_wado_purge_and_retest(node)

        else:
            print(f"Ticket Creation failed for {node} Disabling Server")
            disable_xero_server(node)


def main():
    with concurrent.futures.ThreadPoolExecutor() as executor:
        executor.map(process_node, xero_nodes)
    print("All tasks completed. Shutting down.")

if __name__ == '__main__':
    main()