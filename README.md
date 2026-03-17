# BirmingHack Check-in & Attendee Monitoring

This repository contains a Python application for managing attendee check-in, tracking venue capacity, and printing badges.

The application uses a webcam to scan QR codes and Data Matrix codes. It interfaces with the Tito API to fetch attendee data and update check-in lists. 

## System Architecture and State Management

The application tracks two attendee states using two separate Tito check-in lists:

1. Registration State (Printed): The first time an attendee is scanned, the application prints a name badge and a pizza token. The attendee is then checked into the Registration list on Tito. On startup, the application downloads this list to know who has already received a badge. The application requires internet connectivity to Tito on startup to restore this state.
2. Capacity State (Entry/Exit): Subsequent scans toggle the attendee's status on the Entry/Exit list in Tito. This tracks how many people are currently inside the venue.

## Hardware Requirements

* A webcam (USB or integrated).
* An ESC/POS-compatible USB receipt printer. The application defaults to the Epson TM-P80 profile.

## Setup and Installation

### 1. Install Dependencies

The application requires `git` to install version-controlled dependencies from GitHub. Ensure `git` (and standard build essentials, if required by your operating system) is installed on your machine before proceeding.

Install the required Python packages using a virtual environment:

    pip install -r requirements.txt

Linux USB Permissions: The application requires direct access to USB ports to communicate with the printer. Add your user to the `lp` and `plugdev` groups using the following commands, then log out and log back in:

    sudo usermod -aG lp $USER
    sudo usermod -aG plugdev $USER

### 2. Printer Configuration

Create a `config.yaml` file in the root directory. Add your printer's USB Vendor ID (`maj`) and Product ID (`min`) in hexadecimal format. Use the `lsusb` command in the terminal to find these values.

    # config.yaml
    printer:
      maj: "0x04b8"  # Epson Vendor ID example
      min: "0x0202"  # Product ID example

### 3. Tito API Configuration

Create a `.env` file in the root directory. 

Core API credentials are strictly mandatory. If they are missing, the application cannot verify the Hackathons UK Data Sharing Agreement, and all check-ins will be rejected.

Important: Do not copy the placeholders literally. You must replace the `202X` and `your-...` values with your actual event year, slugs, and secrets.

    # Check-in API Configuration
    TITO_REGISTRATION_LIST_SLUG="birminghack-202X-registration"
    TITO_CHECKIN_LIST_SLUG="birminghack-202X-building-access"

    # Core API Configuration
    TITO_ACCOUNT_SLUG="your-tito-account-name"
    TITO_EVENT_SLUG="birminghack-202X"
    TITO_SECRET="your-secret-tito-api-token"

### 4. Tito Dashboard Custom Questions

The application parses specific custom questions from Tito to print badges, enforce data sharing agreements, and map student IDs. Your Tito event must include questions with these exact titles:

* `What are your preferred pronouns?`
* `What is your pizza preference?`
* `Do you have any dietary restrictions?`
* `What is your Student ID?`
* `Are you fasting?`
* `Hackathons UK Data Sharing Agreement`

Agreement Enforcement: The application will deny entry to any attendee whose response to the Hackathons UK Data Sharing Agreement is not exactly `I agree`.

## Usage and Operations

Run the application:

    python main.py

The application will query Tito, map the responses, and open the camera feed. 

### Scanning Codes

Hold a code up to the camera. The application supports two code types:
* Tito Ticket QR Codes: Found in the attendee's ticket email.
* Student ID Data Matrix: Use the Data Matrix code located in the top right corner of the student ID card. The barcodes at the bottom of the card are not supported and will not scan.

### Keyboard Controls

While the camera window is active, use the following keys to operate the application:

* `q`: Quit the application.
* `p`: Print the pizza summary report. Separates fasting and non-fasting counts.
* `d`: Print the dietary requirement summary report.
* `c`: Print the checked-in capacity summary report.
* `s`: Print a generic security badge.
* `r`: Enable reprint mode. The next scanned ticket will reprint the badge and food token without altering check-in states.

Printer Rate Limiting: The printer is configured with a 3-second delay between print jobs to prevent queue failures. 

## Asset Management

Place image assets in the `assets/` directory.

Thermal printers have strict resolution limits. Images must be resized to a maximum width of 576 pixels. You can resize and convert images to a monochrome format using ImageMagick:

    magick original_image.png -resize 576x -monochrome assets/new_image.png
