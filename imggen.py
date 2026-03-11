from PIL import Image, ImageDraw, ImageFont
import math

font_bold = ImageFont.truetype("fonts/IosevkaSS08-Bold.ttc", 70, encoding="unic")
font_norm = ImageFont.truetype("fonts/IosevkaSS08-Regular.ttc", 40, encoding="unic")

MAX_WIDTH = 576

def name(name: str):
    txt_len = font_bold.getlength(name)
    if txt_len > MAX_WIDTH:
        img = Image.new('RGB', (math.ceil(txt_len), 80), (255, 255, 255))
    else:
        img = Image.new('RGB', (MAX_WIDTH, 80), (255, 255, 255))

    draw = ImageDraw.Draw(img)
    draw.text((0, 0), name, font=font_bold, fill="black")

    if txt_len > MAX_WIDTH:
        wpercent = (MAX_WIDTH / float(img.size[0]))
        hsize = int((float(img.size[1]) * float(wpercent)))
        img = img.resize((MAX_WIDTH, hsize), Image.Resampling.LANCZOS)

        new_img = Image.new('RGB', (MAX_WIDTH, 80), (255, 255, 255))
        new_img.paste(img, (0,math.floor(80-hsize)))
        img = new_img

    return img

def pronouns(pronouns: str):
    img = Image.new('RGB', (MAX_WIDTH, 50), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((0, 0), pronouns, font=font_norm, fill="black")
    return img