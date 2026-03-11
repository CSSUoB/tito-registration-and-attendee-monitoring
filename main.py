import os
import sys
import time
import cv2  # type: ignore
import requests
from dotenv import load_dotenv
from pyzbar.pyzbar import decode  # type: ignore
from dataclasses import dataclass
from typing import Optional
from strictyaml import load  # type: ignore

import printer
import imggen

load_dotenv()

# --- Configuration ---
REG_SLUG: str = os.getenv("TITO_REGISTRATION_LIST_SLUG", "")
EE_SLUG: str = os.getenv("TITO_CHECKIN_LIST_SLUG", "")

if not REG_SLUG or not EE_SLUG:
    print("Error: Missing TITO_REGISTRATION_LIST_SLUG or TITO_CHECKIN_LIST_SLUG in .env")
    sys.exit(1)

REG_BASE_URL: str = f"https://checkin.tito.io/checkin_lists/{REG_SLUG}"
EE_BASE_URL: str = f"https://checkin.tito.io/checkin_lists/{EE_SLUG}"
HEADERS: dict[str, str] = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "BirmingHack Sign-in System (contact email css@guild.bham.ac.uk)",
}

# Load Printer Configuration
try:
    with open("config.yaml", "r") as f:
        config = load(f.read()).data
    printer.init_printer(
        int(config['printer']['maj'], 16), 
        int(config['printer']['min'], 16)
    )
except Exception as e:
    print(f"Warning: Could not initialize printer. Check config.yaml and USB. Error: {e}")


@dataclass
class Ticket:
    slug: str
    reference: str
    t_id: int
    name: str
    checkin_uuid: Optional[str] = None
    has_registered: bool = False
    ticket_type: str = ""
    pronouns: str = ""
    pizza_pref: str = ""
    dietary_reqs: Optional[str] = None

    @property
    def is_checked_in(self) -> bool:
        return self.checkin_uuid is not None


class AttendeeTracker:
    def __init__(self) -> None:
        self.tickets_by_slug: dict[str, Ticket] = {}
        self.tickets_by_id: dict[int, Ticket] = {}
        self.last_scan_time: float = 0
        self.scan_cooldown: int = 4
        
        # Track pizza groups locally
        self.group: int = 1
        self.serial: int = 1

    def initialize_data(self) -> None:
        """Fetches tickets, custom answers, and existing check-ins to sync state."""
        print("Fetching tickets and custom questions from Tito...")
        
        # 1. Fetch all tickets
        try:
            tickets_response = requests.get(f"{EE_BASE_URL}/tickets", headers=HEADERS)
            tickets_response.raise_for_status()
            tickets_data = tickets_response.json()

            tickets = (
                tickets_data.get("tickets", tickets_data)
                if isinstance(tickets_data, dict)
                else tickets_data
            )

            for t in tickets:
                ref = t.get("reference")
                slug = t.get("slug")
                t_id = t.get("id")
                first = t.get("first_name") or ""
                last = t.get("last_name") or ""
                name = f"{first} {last}".strip() or "Unknown Guest"
                
                ticket_type = t.get("release_title") or t.get("release", {}).get("title", "Attendee")

                if slug and ref and t_id:
                    ticket = Ticket(
                        slug=slug, 
                        reference=ref, 
                        t_id=t_id, 
                        name=name,
                        ticket_type=ticket_type
                    )
                    self.tickets_by_slug[slug] = ticket
                    self.tickets_by_id[t_id] = ticket

            print(f"Loaded {len(self.tickets_by_slug)} valid tickets.")

        except requests.RequestException as e:
            print(f"Failed to fetch tickets: {e}")
            sys.exit(1)

        # 2. Fetch Answers (Pizza, Pronouns, Dietary) via Check-in API
        try:
            answers_response = requests.get(f"{EE_BASE_URL}/answers", headers=HEADERS)
            answers_response.raise_for_status()
            answers_data = answers_response.json()
            
            answers = (
                answers_data.get("answers", answers_data)
                if isinstance(answers_data, dict)
                else answers_data
            )

            for ans in answers:
                t_id = ans.get("ticket_id")
                if t_id and t_id in self.tickets_by_id:
                    # Depending on the payload structure, title is sometimes under question -> title
                    question_title = ans.get("question", {}).get("title", "")
                    response = ans.get("response", "")
                    
                    if question_title == 'What are your preferred pronouns?':
                        self.tickets_by_id[t_id].pronouns = response
                    elif question_title == 'What is your pizza preference?':
                        self.tickets_by_id[t_id].pizza_pref = response
                    elif question_title == 'Do you have any dietary restrictions?':
                        self.tickets_by_id[t_id].dietary_reqs = response
                        
            print("Successfully mapped custom question answers to tickets.")
        except requests.RequestException as e:
            print(f"Failed to fetch custom answers: {e} - Proceeding without answers.")

        # 3. Fetch Registration Check-ins (Permanent Badging State)
        try:
            reg_response = requests.get(f"{REG_BASE_URL}/checkins", headers=HEADERS)
            reg_response.raise_for_status()
            for checkin in reg_response.json():
                if not checkin.get("deleted_at"):
                    t_id = checkin.get("ticket_id")
                    if t_id and t_id in self.tickets_by_id:
                        self.tickets_by_id[t_id].has_registered = True
            reg_count = sum(1 for t in self.tickets_by_slug.values() if t.has_registered)
            print(f"Synced {reg_count} existing registrations (Badges printed).")
        except requests.RequestException as e:
            print(f"Failed to fetch registration state: {e}")
            sys.exit(1)

        # 4. Fetch Entry/Exit Check-ins (Volatile Capacity State)
        try:
            ee_response = requests.get(f"{EE_BASE_URL}/checkins", headers=HEADERS)
            ee_response.raise_for_status()
            for checkin in ee_response.json():
                if not checkin.get("deleted_at"):
                    t_id = checkin.get("ticket_id")
                    c_uuid = checkin.get("uuid")
                    if t_id and c_uuid and t_id in self.tickets_by_id:
                        self.tickets_by_id[t_id].checkin_uuid = c_uuid
            inside_count = sum(1 for t in self.tickets_by_slug.values() if t.is_checked_in)
            print(f"Synced {inside_count} attendees currently inside.")
        except requests.RequestException as e:
            print(f"Failed to fetch entry/exit state: {e}")
            sys.exit(1)

    def process_qr_code(self, qr_data: str) -> str:
        """Handles registration, printing, and building capacity checking."""
        if qr_data not in self.tickets_by_slug:
            return f"INVALID TICKET: {qr_data}"

        ticket = self.tickets_by_slug[qr_data]
        status = ""

        # --- 1. HANDLE REGISTRATION (First Time Only) ---
        if not ticket.has_registered:
            print(f"First scan for {ticket.name}. Registering & Printing...")
            
            # Post to Tito Registration List
            url = f"{REG_BASE_URL}/checkins"
            payload = {"checkin": {"ticket_reference": ticket.reference}}
            try:
                requests.post(url, headers=HEADERS, json=payload).raise_for_status()
                ticket.has_registered = True
                status = "REGISTERED & "

                # Trigger Printer Scripts
                try:
                    printer.print_pass(
                        imggen.name(ticket.name), 
                        imggen.pronouns(ticket.pronouns), 
                        ticket.reference, 
                        ticket.ticket_type, 
                        ticket.slug
                    )

                    if ticket.pizza_pref:
                        printer.print_food(
                            ticket.name, 
                            ticket.pizza_pref, 
                            str(self.group), 
                            ticket.dietary_reqs
                        )
                        self.serial += 1
                        if self.serial % 10 == 0:
                            self.group += 1
                            print(f"Incrementing pizza group to {self.group}")
                            
                except Exception as e:
                    print(f"Printer error: {e}")
                    status += "(PRINTER ERROR) "

            except requests.RequestException as e:
                error_details = e.response.text if e.response is not None else "No response"
                print(f"API Error during Registration: {e}\nTito says: {error_details}")
                return "REGISTRATION ERROR"

        # --- 2. HANDLE ENTRY/EXIT (Every Time) ---
        if ticket.is_checked_in:
            # Attendee is inside, CHECK OUT
            url = f"{EE_BASE_URL}/checkins/{ticket.checkin_uuid}"
            try:
                requests.delete(url, headers=HEADERS).raise_for_status()
                ticket.checkin_uuid = None
                status += "CHECKED OUT"
            except requests.RequestException as e:
                print(f"API Error during Check-out: {e}")
                return "API ERROR"
        else:
            # Attendee is outside, CHECK IN
            url = f"{EE_BASE_URL}/checkins"
            payload = {"checkin": {"ticket_reference": ticket.reference}}
            try:
                response = requests.post(url, headers=HEADERS, json=payload)
                response.raise_for_status()
                ticket.checkin_uuid = response.json().get("uuid")
                status += "CHECKED IN"
            except requests.RequestException as e:
                print(f"API Error during Check-in: {e}")
                return "API ERROR"

        checked_in_count = sum(1 for t in self.tickets_by_slug.values() if t.is_checked_in)
        print(f"[{status}] {ticket.name} ({ticket.reference}) - Inside: {checked_in_count}")
        return f"{status}: {ticket.name}"


def main() -> None:
    tracker = AttendeeTracker()
    tracker.initialize_data()

    print("Starting Camera... Press 'q' to quit.")
    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        print("Error: Could not open video device.")
        return

    freeze_until = 0.0
    frozen_frame = None
    freeze_duration = 3.0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

        current_time = time.time()

        if current_time < freeze_until and frozen_frame is not None:
            cv2.imshow("Tito Live Check-in Scanner", frozen_frame)
            continue

        decoded_objects = decode(frame)

        for obj in decoded_objects:
            qr_data = obj.data.decode("utf-8")

            if current_time - tracker.last_scan_time < tracker.scan_cooldown:
                continue

            message = tracker.process_qr_code(qr_data)
            tracker.last_scan_time = current_time

            # Draw bounding box
            points = obj.polygon
            if len(points) == 4:
                for i in range(4):
                    cv2.line(frame, points[i], points[(i + 1) % 4], (255, 0, 0), 3)

            # Draw status text
            color = (0, 0, 255) if "OUT" in message or "ERROR" in message else (0, 255, 0)
            (text_w, text_h), _ = cv2.getTextSize(message, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)
            cv2.rectangle(frame, (25, 25), (35 + text_w, 60), (0, 0, 0), -1)
            cv2.putText(frame, message, (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

            # Snapshot and freeze
            frozen_frame = frame.copy()
            freeze_until = current_time + freeze_duration
            break 

        if current_time >= freeze_until:
            cv2.imshow("Tito Live Check-in Scanner", frame)

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()