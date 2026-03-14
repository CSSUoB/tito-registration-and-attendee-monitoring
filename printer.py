from PIL import Image
from escpos.printer import Usb, Dummy  # type: ignore
from typing import Optional, Union
import math

p = Dummy()

def init_printer(maj: int, min: int):
    global p
    p = Usb(maj, min, 0, profile="TM-P80")

def test_print():
    p.image("assets/tex.png", center=True)
    p.cut()

def print_dietary_summary(dietary_counts: list[tuple[str, str, str]]):
    p.linedisplay_clear()
    p.set(align="center",bold=True,custom_size=True,width=3,height=3)
    p.textln("Dietary Summary")

    for name, dietary, pizza in dietary_counts:
        p.set(align="left",bold=False,normal_textsize=True)
        p.software_columns([name, dietary, pizza], widths=48, align=["left", "left", "right"])
    p.cut()

def print_pizza_summary(pizza_counts: dict[str, int], dietary_counts: dict[str, int], fasting_counts: dict[str, int], total_counts: dict[str, int]):
    # for pizza sections, columns to show pizza type, count of attendees and number of pizzas
    p.linedisplay_clear()
    p.set(align="center",bold=True,custom_size=True,width=3,height=3)
    p.textln("Summary (Totals)")
    p.ln()
    p.set(align="left",bold=False,normal_textsize=True)
    p.software_columns(["Pizza Type", "Attendees", "Pizzas", "Slices"], widths=48, align=["left", "right", "right", "right"])
    for pizza_type, count in total_counts.items():
        p.software_columns([pizza_type, str(count), str(math.ceil((count * 4) // 12)), str(count * 4)], widths=48, align=["left", "right", "right", "right"])
    p.ln()
    p.text("Total: " + str(sum(total_counts.values())))
    p.ln()

    p.set(align="center", bold=True, custom_size=True, width=2, height=2)
    p.textln("Summary (Non-Fasting)")
    p.set(align="left",bold=False,normal_textsize=True)
    p.software_columns(["Pizza Type", "Attendees", "Pizzas", "Slices"], widths=48, align=["left", "right", "right", "right"])
    for pizza_type, count in pizza_counts.items():
        p.software_columns([pizza_type, str(count), str(math.ceil((count * 4) // 12)), str(count * 4)], widths=48, align=["left", "right", "right", "right"])
    p.ln()
    p.text("Total: " + str(sum(pizza_counts.values())))

    p.ln()
    p.ln()
    p.set(align="center",bold=True,custom_size=True,width=2,height=2)
    p.text("Fasting Summary")
    p.ln()
    p.set(align="left",bold=False,normal_textsize=True)
    p.software_columns(["Pizza Type", "Attendees", "Pizzas", "Slices"], widths=48, align=["left", "right", "right", "right"])
    for pizza_type, count in fasting_counts.items():
        p.software_columns([pizza_type, str(count), str(math.ceil((count * 4) // 12)), str(count * 4)], widths=48, align=["left", "right", "right", "right"])

    p.text("Total: " + str(sum(fasting_counts.values())))

    p.ln()
    p.ln()
    p.set(align="center",bold=True,custom_size=True,width=2,height=2)
    p.text("Allergy Summary")
    p.ln()
    p.set(align="left",bold=False,normal_textsize=True)
    for dietary_req, count in dietary_counts.items():
        p.software_columns([dietary_req, str(count)], widths=48, align=["left", "right"])
    p.cut()

def print_pass(name_image: Union[str, Image.Image], pronouns_image: Union[str, Image.Image], reference: str, ticket_type: str, slug: str):
    p.linedisplay_clear()
    p.image("assets/birminghack-logo-raster-bw-rs.png",center=True)
    p.ln()
    p.ln()
    p.image(name_image,center=True)
    p.image(pronouns_image,center=True)
    p.set(align="left",bold=False,custom_size=True,width=2,height=2)
    p.ln()
    p.qr(slug, size=10, center=True)
    p.set(align="left",bold=True,normal_textsize=True)
    p.software_columns(["Reference", reference], widths=48, align=["left", "right"])
    p.software_columns(["Type", ticket_type], widths=48, align=["left", "right"])
    p.set(align="left",bold=False,normal_textsize=True)
    p.ln()
    p.textln("By attending this event you agree to the")
    p.textln("birmingHack Code of Conduct:")
    p.set(align="right",bold=False,normal_textsize=True)
    p.textln("birminghack.com/conduct")
    p.set(align="left",bold=False,normal_textsize=True)
    p.ln()
    p.textln("Please wear your attendee pass at all times.")
    p.cut()

def print_food(issued_to: str, pizza_type: str, group: str, d_req: Optional[str] = None):
    p.linedisplay_clear()
    p.ln()
    p.set(align="center",bold=True,custom_size=True,width=3,height=3,smooth=True)
    p.textln("Pizza Token")
    p.ln()
    p.set(align="left",bold=False,normal_textsize=True)
    p.textln("Exchange me for pizza!")
    p.image("assets/pizza.png",center=True)
    p.ln()
    p.set(align="left",bold=True,normal_textsize=True)
    p.software_columns(["Group", group], widths=48, align=["left", "right"])
    p.software_columns(["Pizza Type", pizza_type], widths=48, align=["left", "right"])
    p.software_columns(["Issued To", issued_to], widths=48, align=["left", "right"])
    p.ln()
    if d_req:
        p.set(align="left",bold=False,custom_size=True,width=2,height=2,invert=True)
        p.textln("Dietary Requirement")
        p.ln()
        p.set(align="left",bold=False,normal_textsize=True,invert=False)
        p.textln(d_req)
    p.cut()

def print_security_badge() -> None:
    p.linedisplay_clear()
    p.image("assets/birminghack-logo-raster-bw-rs.png",center=True)
    p.ln()
    p.set(align="center", bold=True, custom_size=True, width=3, height=3)
    p.textln("Security")
    p.ln()
    p.cut()
