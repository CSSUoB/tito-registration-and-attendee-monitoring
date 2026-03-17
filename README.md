# BirmingHack Check-in & Attendee Monitoring

This repository contains a local Python application used for managing attendee check-in, tracking building capacity, and automating badge printing for BirmingHack.

The system uses a webcam to scan QR codes and interfaces with the Tito API to update attendee records. To ensure the scanning process remains fast and resilient against venue Wi-Fi dropouts, the application downloads the necessary attendee data on startup and manages print state locally, rather than relying on webhooks.

## System Architecture and Logic

The application tracks two distinct attendee states:

1.  **Registration (Permanent State):** The first time an attendee is scanned, the system registers them and sends a print job to the connected thermal printer to produce their name badge and pizza token. This state is tracked so that subsequent scans do not reprint the badge.
2.  **Entry/Exit Tracking (Volatile State):** After initial registration, scanning an attendee will toggle their status between "Checked In" and "Checked Out". This is used to maintain an accurate count of attendees currently inside the building.

### Dual-Scanning Capability
The scanner accepts two types of QR codes:
* **Tito Ticket QR Codes:** The standard ticket QR code emailed to attendees.
* **Student ID Cards:** The application maps the attendees' Student ID numbers (collected via Tito custom questions) during startup. This allows attendees to simply scan their university ID card instead of locating their ticket email.

## Hardware Requirements

* A standard USB or integrated webcam.
* A Brother Thermal Printer (or an ESC/POS compatible receipt printer) connected via USB.

## Setup and Installation

### 1. Install Dependencies
It is recommended to use a Python virtual environment. Install the required packages using:

    pip install -r requirements.txt

*Linux User Note:* The `pyusb` and `python-escpos` libraries require direct access to the USB ports. You will likely need to run the application with `sudo` or add your user account to the `plugdev` and `lp` groups to grant the necessary permissions.

### 2. Printer Configuration
Create a `config.yaml` file in the root directory. This file must contain your specific printer's USB Vendor ID (`maj`) and Product ID (`min`) in hexadecimal format. You can locate these IDs by running `lsusb` in your terminal.

    # config.yaml
    printer:
      maj: "0x04b8"  # Replace with your printer's Vendor ID
      min: "0x0202"  # Replace with your printer's Product ID

### 3. Tito API Configuration
Create a `.env` file in the root directory. The application requires credentials for both the Tito Check-in API (for rapid state toggling) and the Tito Core API (for securely downloading custom answers like dietary requirements and Student IDs).

You must create two separate Check-in Lists on the Tito dashboard: one dedicated to initial registration, and one dedicated to entry/exit tracking.

    # Check-in API Configuration
    TITO_REGISTRATION_LIST_SLUG="birminghack-202X-registration"
    TITO_CHECKIN_LIST_SLUG="birminghack-202X-building-access"
    
    # Core API Configuration
    TITO_ACCOUNT_SLUG="your-tito-account-name"
    TITO_EVENT_SLUG="birminghack-202X"
    TITO_SECRET="your-secret-tito-api-token"

### 4. Tito Dashboard Requirements
For the application to correctly map data for the printed badges and ID scanning, your Tito event must include custom questions with these exact titles:
* `What are your preferred pronouns?`
* `What is your pizza preference?`
* `Do you have any dietary restrictions?`
* `What is your Student ID?`

## Usage

To launch the scanner, run the main script:

    python main.py

Upon startup, the script will pause for a few seconds to query the Tito API and build the local dictionaries. Once the camera feed window opens, the system is ready. Hold a valid QR code up to the camera to trigger the process.

### Testing the Printer Output
To verify the printer connection and scaling before the event begins, you can enable a test print. Open `main.py`, locate the printer initialization block, and uncomment the `printer.test_print()` function call. This will print the `assets/tex.png` file as soon as the script starts.

## Asset Management

Image assets (logos, icons, and test prints) are stored in the `assets/` directory.

Because thermal printers have strict resolution limits, any new images added to this folder must be resized to a maximum width of **576 pixels**. If an image exceeds this width, the printer script will likely fail.

You can resize and convert images to a thermal-friendly monochrome format using ImageMagick via the terminal:

    magick original_image.png -resize 576x -monochrome assets/new_image.png
