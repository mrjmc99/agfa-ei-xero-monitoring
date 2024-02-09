
# Xero Ticket Management Script

This script automates the management of Xero tickets by interacting with the Xero API, performing server actions, and creating incidents in ServiceNow based on specific conditions.

## Prerequisites

Before running the script, ensure the following:

- Python is installed on your system.
- Install the required Python packages using the following command:

  ```bash
  pip install requests paramiko
  ```

## Configuration

The script uses a configuration file named `xeroticket.ini` to store various parameters. Ensure that this file is present in the same directory as the script. Example configuration parameters include:

- Xero API Variables
- Email Variables
- ServiceNow Variables

## Logging

The script logs its activities to a file named `xero_ticket.log` using the `logging` module. This log file can be referenced for debugging and auditing purposes.

## Usage

Run the script using the following command:

```bash
python xero_ticket_script.py
```

The script performs the following actions:

1. **Xero Ticket Creation**: Obtains a ticket from the Xero API for each specified Xero server.

2. **Ticket Verification**: Verifies the obtained ticket's validity by making a request to the Xero server.

3. **Server Actions**: Depending on the verification result, the script may restart or disable the Xero server.

4. **Incident Creation in ServiceNow**: In case of server actions, incidents are created in ServiceNow, and email notifications are sent.

## Script Logic

The script is structured as follows:

- **Configuration Loading**: Loads configuration parameters from `xeroticket.ini`.
- **Xero Ticket Management**: Obtains, verifies, and manages Xero tickets for specified servers.
- **Remote Server Actions**: Restarts or disables Xero servers based on verification results.
- **ServiceNow Integration**: Creates incidents in ServiceNow based on server actions.
- **Logging**: Captures activities and errors in the `xero_ticket.log` file.

## Error Handling

The script includes error handling for various scenarios, such as authentication failures, SSH connection errors, and ticket verification failures.

## Support and Issues

For any issues or questions, please create an issue in the [GitHub repository](https://github.com/mrjmc99/agfa-ei-xero-monitoring).

```

Make sure to replace "yourusername" and "yourrepository" with your actual GitHub username and repository name. Additionally, customize the README to provide more specific details based on your use case and audience.