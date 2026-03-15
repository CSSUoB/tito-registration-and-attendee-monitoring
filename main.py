import os
import sys
import time
import cv2  # type: ignore
import requests
from dotenv import load_dotenv
import zxingcpp  # type: ignore
from dataclasses import dataclass
from typing import Optional
from strictyaml import load  # type: ignore
import numpy as np
from playsound3 import playsound

import printer
import imggen

load_dotenv()

# --- Configuration ---
REG_SLUG: str = os.getenv("TITO_REGISTRATION_LIST_SLUG", "")
EE_SLUG: str = os.getenv("TITO_CHECKIN_LIST_SLUG", "")

# Core API Auth
TITO_ACCOUNT_SLUG = os.getenv("TITO_ACCOUNT_SLUG", "")
TITO_EVENT_SLUG = os.getenv("TITO_EVENT_SLUG", "")
TITO_SECRET = os.getenv("TITO_SECRET", "")

if not REG_SLUG or not EE_SLUG:
    print("Error: Missing TITO_REGISTRATION_LIST_SLUG or TITO_CHECKIN_LIST_SLUG in .env")
    sys.exit(1)

REG_BASE_URL: str = f"https://checkin.tito.io/checkin_lists/{REG_SLUG}"
EE_BASE_URL: str = f"https://checkin.tito.io/checkin_lists/{EE_SLUG}"
HEADERS: dict[str, str] = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "BirmingHack Sign-in System",
}

# Load Printer Configuration
try:
    with open("config.yaml", "r") as f:
        config = load(f.read()).data
    printer.init_printer(
        int(config['printer']['maj'], 16), 
        int(config['printer']['min'], 16)
    )
    # printer.test_print()
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
    fasting: bool = False
    dietary_reqs: Optional[str] = None
    student_id: Optional[str] = None

    @property
    def is_checked_in(self) -> bool:
        return self.checkin_uuid is not None


class AttendeeTracker:
    def __init__(self) -> None:
        self.tickets_by_slug: dict[str, Ticket] = {}
        self.tickets_by_id: dict[int, Ticket] = {}
        self.tickets_by_student_id: dict[str, Ticket] = {}
        self.huk_agreed_tickets: list[Ticket] = []
        self.last_scan_time: float = 0
        self.scan_cooldown: int = 4
        
        self.group: int = 1
        self.serial: int = 1

        self.reprint: bool = False

    def initialize_data(self) -> None:
        print("Fetching tickets from Tito...")
        
        # 1. Fetch all tickets via Check-in API (Needed for rapid scanning)
        try:
            tickets_response = requests.get(f"{EE_BASE_URL}/tickets", headers=HEADERS)
            tickets_response.raise_for_status()
            tickets_data = tickets_response.json()

            tickets = tickets_data.get("tickets", tickets_data) if isinstance(tickets_data, dict) else tickets_data

            for t in tickets:
                ref = t.get("reference")
                slug = t.get("slug")
                t_id = t.get("id")
                name = f"{t.get('first_name') or ''} {t.get('last_name') or ''}".strip() or "Unknown Guest"
                ticket_type = t.get("release_title") or t.get("release", {}).get("title", "Attendee")

                if slug and ref and t_id:
                    self.tickets_by_slug[slug] = Ticket(
                        slug=slug, reference=ref, t_id=t_id, name=name, ticket_type=ticket_type
                    )
                    self.tickets_by_id[t_id] = self.tickets_by_slug[slug]

            print(f"Loaded {len(self.tickets_by_slug)} valid tickets.")

        except requests.RequestException as e:
            print(f"Failed to fetch tickets: {e}")
            sys.exit(1)

        # 2. Fetch Answers via Authenticated Core API
        if not all([TITO_ACCOUNT_SLUG, TITO_EVENT_SLUG, TITO_SECRET]):
            print("WARNING: Missing Core API credentials in .env! Cannot fetch pizza/pronouns.")
        else:
            print("Using Tito Core API to fetch custom answers securely...")
            core_headers = {
                "Authorization": f"Token token={TITO_SECRET}",
                "Accept": "application/json",
            }
            try:
                q_response = requests.get(f"https://api.tito.io/v3/{TITO_ACCOUNT_SLUG}/{TITO_EVENT_SLUG}/questions", headers=core_headers)
                q_response.raise_for_status()
                questions = q_response.json().get("questions", [])
                
                target_questions = {
                    'What are your preferred pronouns?': 'pronouns',
                    'What is your pizza preference?': 'pizza_pref',
                    'Do you have any dietary restrictions?': 'dietary_reqs',
                    'What is your Student ID?': 'student_id',
                    'Are you fasting?': 'fasting',
                    'Hackathons UK Data Sharing Agreement': 'huk-approval'
                }

                for q in questions:
                    q_title = q.get("title", "")
                    if q_title in target_questions:
                        q_slug = q.get("slug")
                        attr_name = target_questions[q_title]
                        
                        ans_resp = requests.get(f"https://api.tito.io/v3/{TITO_ACCOUNT_SLUG}/{TITO_EVENT_SLUG}/questions/{q_slug}/answers?page[size]=1000", headers=core_headers)
                        ans_resp.raise_for_status()
                        
                        for ans in ans_resp.json().get("answers", []):
                            t_id = ans.get("ticket_id") or ans.get("ticket", {}).get("id")
                            if t_id and t_id in self.tickets_by_id:
                                response_text = ans.get("response", "")
                                if attr_name in ['pronouns', 'pizza_pref', 'dietary_reqs']:
                                    setattr(self.tickets_by_id[t_id], attr_name, response_text)

                                if attr_name == 'student_id' and response_text:
                                    clean_id = str(response_text).strip()
                                    self.tickets_by_student_id[clean_id] = self.tickets_by_id[t_id]

                                if attr_name == 'huk-approval' and response_text == 'I agree':
                                    self.huk_agreed_tickets.append(self.tickets_by_id[t_id])

                                if attr_name == 'fasting' and 'yes' in response_text.lower().strip():
                                    self.tickets_by_id[t_id].fasting = True
                
                pizza_count = sum(1 for t in self.tickets_by_slug.values() if t.pizza_pref)
                print(f"Successfully mapped answers for {pizza_count} attendees using Core API.")
                print(f"HUK Agreement Count: {len(self.huk_agreed_tickets)}")
                print(f"Fasting Count: {sum(1 for t in self.tickets_by_slug.values() if t.fasting)}")
                
            except requests.RequestException as e:
                print(f"Failed to fetch answers via Core API: {e}")

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
        if qr_data in self.tickets_by_slug:
            ticket = self.tickets_by_slug[qr_data]
        elif qr_data in self.tickets_by_student_id:
            ticket = self.tickets_by_student_id[qr_data]
        else:
            print(self.tickets_by_student_id)
            return f"INVALID TICKET: {qr_data}"

        status = ""

        if ticket not in self.huk_agreed_tickets:
            print(f"Attendee {ticket.name} has not agreed to the HUK Data Sharing Agreement. Denying entry.")
            self.initialize_data()
            return "HUK AGREEMENT REQUIRED"
        
        if self.reprint:
            self.reprint = False
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
                print(f"Reprinted pass for {ticket.name}.")
            except Exception as e:
                print(f"Printer error during reprint: {e}")
                return "REPRINT ERROR"

        # --- 1. HANDLE REGISTRATION (First Time Only) ---
        if not ticket.has_registered:
            print(f"First scan for {ticket.name}. Registering & Printing...")
            
            url = f"{REG_BASE_URL}/checkins"
            payload = {"checkin": {"ticket_reference": ticket.reference}}
            try:
                requests.post(url, headers=HEADERS, json=payload).raise_for_status()
                ticket.has_registered = True
                status = "REGISTERED & "

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
                    else:
                        print(f"No pizza preference found for {ticket.name}! Skipping food token.")
                            
                except Exception as e:
                    print(f"Printer error: {e}")
                    status += "(PRINTER ERROR) "

            except requests.RequestException as e:
                error_details = e.response.text if e.response is not None else "No response"
                print(f"API Error during Registration: {e}\nTito says: {error_details}")
                return "REGISTRATION ERROR"

        # --- 2. HANDLE ENTRY/EXIT (Every Time) ---
        if ticket.is_checked_in:
            url = f"{EE_BASE_URL}/checkins/{ticket.checkin_uuid}"
            try:
                requests.delete(url, headers=HEADERS).raise_for_status()
                ticket.checkin_uuid = None
                status += "CHECKED OUT"
            except requests.RequestException as e:
                print(f"API Error during Check-out: {e}")
                return "API ERROR"
        else:
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
    
    def print_pizza_data(self) -> None:
        pizza_summary: dict[str, int] = {}
        fasting_pizza_summary: dict[str, int] = {}
        allergy_list: dict[str, int] = {}
        total_counts: dict[str, int] = {}
        # only get tickets that are checked in
        for ticket in self.tickets_by_slug.values():
            if ticket.has_registered and ticket.pizza_pref and not ticket.fasting:
                pizza_summary[ticket.pizza_pref] = pizza_summary.get(ticket.pizza_pref, 0) + 1

            # add dietary requirements summary
            if ticket.has_registered and ticket.dietary_reqs:
                allergy_list[ticket.dietary_reqs] = allergy_list.get(ticket.dietary_reqs, 0) + 1

            # add fasting summary
            if ticket.has_registered and ticket.pizza_pref and ticket.fasting:
                fasting_pizza_summary[ticket.pizza_pref] = fasting_pizza_summary.get(ticket.pizza_pref, 0) + 1


        # add totals
        for pizza_type in set(pizza_summary.keys()).union(fasting_pizza_summary.keys()):
            total_counts[pizza_type] = pizza_summary.get(pizza_type, 0) + fasting_pizza_summary.get(pizza_type, 0)

        printer.print_pizza_summary(pizza_summary, allergy_list, fasting_pizza_summary, total_counts)

    def print_dietary(self) -> None:
        # print the attendee name, their dietary requirement and pizza preference, we do not need a count
        dietary_list: list[tuple[str, str, str]] = []
        for ticket in self.tickets_by_slug.values():
            if ticket.has_registered and ticket.dietary_reqs and ticket.pizza_pref:
                dietary_list.append((ticket.name, ticket.dietary_reqs, ticket.pizza_pref))

        printer.print_dietary_summary(dietary_list)

    def print_checked_in(self) -> None: 
        # print ticket type, number registered, number checked in
        summary: dict[str, dict[str, int]] = {}
        for ticket in self.tickets_by_slug.values():
            if ticket.ticket_type not in summary:
                summary[ticket.ticket_type] = {"registered": 0, "checked_in": 0}
            if ticket.has_registered:
                summary[ticket.ticket_type]["registered"] += 1
            if ticket.is_checked_in:
                summary[ticket.ticket_type]["checked_in"] += 1

        printer.print_checked_in_summary(summary)


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

        key = cv2.waitKey(1) & 0xFF

        if key == ord("q"):
            break

        if key == ord("p"):
            print("Generating pizza summary report...")
            tracker.print_pizza_data()
            continue

        if key == ord("d"):
            print("Generating dietary summary report...")
            tracker.print_dietary()
            continue

        if key == ord("s"):
            print("Printing security badge...")
            printer.print_security_badge()
            continue

        if key == ord("r"):
            print("Enabling reprint mode for next scan...")
            tracker.reprint = True
            continue

        if key == ord("c"):
            print("Generating checked-in summary report...")
            tracker.print_checked_in()
            continue

        current_time = time.time()

        if current_time < freeze_until and frozen_frame is not None:
            cv2.imshow("Tito Live Check-in Scanner", frozen_frame)
            continue

        decoded_objects = zxingcpp.read_barcodes(frame)

        for obj in decoded_objects:
            qr_data = obj.text

            if current_time - tracker.last_scan_time < tracker.scan_cooldown:
                continue

            message = tracker.process_qr_code(qr_data)
            tracker.last_scan_time = current_time

            p = obj.position
            pts = np.array([
                [p.top_left.x, p.top_left.y],
                [p.top_right.x, p.top_right.y],
                [p.bottom_right.x, p.bottom_right.y],
                [p.bottom_left.x, p.bottom_left.y]
            ], np.int32)
            pts = pts.reshape((-1, 1, 2))
            cv2.polylines(frame, [pts], True, (255, 0, 0), 3)

            color = (0, 0, 255) if "OUT" in message or "ERROR" in message else (0, 255, 0)
            (text_w, text_h), _ = cv2.getTextSize(message, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)
            cv2.rectangle(frame, (25, 25), (35 + text_w, 60), (0, 0, 0), -1)
            cv2.putText(frame, message, (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

            frozen_frame = frame.copy()
            freeze_until = current_time + freeze_duration
            break 

        if current_time >= freeze_until:
            cv2.imshow("Tito Live Check-in Scanner", frame)

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()