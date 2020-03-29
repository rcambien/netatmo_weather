#!/usr/bin/python
# -*- coding:utf-8 -*-

from PIL import Image, ImageDraw, ImageFont
from gpiozero import Button
import pyowm
from netatmo import WeatherStation
import pytz
from datetime import datetime
import time
import epd2in7
import logging
import math
import os
import signal
import sys
fontdir = os.path.join(os.path.dirname(
    os.path.realpath(__file__)), 'data/font/')


logging.basicConfig(level=logging.DEBUG)

REFRESH_RATE = 600.0
REFRESH_RATE_QUICK = 60.0

# Fonts
small = ImageFont.truetype(
    '/usr/share/fonts/truetype/freefont/FreeSans.ttf', 20)
big = ImageFont.truetype('/usr/share/fonts/truetype/freefont/FreeSans.ttf', 45)
meteo = ImageFont.truetype(os.path.join(
    fontdir, 'weathericons-regular-webfont.ttf'), 50)
meteoSmall = ImageFont.truetype(os.path.join(
    fontdir, 'weathericons-regular-webfont.ttf'), 30)
utility = ImageFont.truetype(os.path.join(fontdir, 'icofont.ttf'), 20)
utilityBig = ImageFont.truetype(os.path.join(fontdir, 'icofont.ttf'), 80)

# Screen
epd = epd2in7.EPD()

# Netatmo
ws = WeatherStation()

# OpenWeatherMap
owm = pyowm.OWM('7f4307249c914cd8ec3fa2a51ac445ba')


nextRefresh = time.time()
currentInteriorModuleIndex = 0
currentExteriorModuleIndex = 0


def refresh():
    global data
    global nextRefresh
    global currentInteriorModuleIndex
    global currentExteriorModuleIndex

    logging.info("Refresh data and screen")

    # Get data
    ws.get_data()
    data = ws.devices[0]

    # Reset module index
    currentInteriorModuleIndex = 0
    currentExteriorModuleIndex = 0

    # drawFarecast()
    drawModule(data)

    nextRefresh = time.time() + REFRESH_RATE


def handleBtnPress(btn):
    global nextRefresh

    logging.info(str(btn.pin.number) + " pressed")

    switcher = {
        5:  drawFarecast,
        6:  drawNextExteriorModule,
        13: drawNextInteriorModule,
        19: refresh
    }
    switcher.get(btn.pin.number, lambda: print("Invalid button"))()

    # move refresh
    nextRefresh = time.time() + REFRESH_RATE_QUICK


def display(image):
    # Refresh
    epd.init()

    epd.display_frame(epd.get_frame_buffer(image.rotate(180)))

    epd.sleep()

    logging.info("Draw finished, going to sleep")


def drawFarecast():
    (lat, lon) = data['place']['location']
    weathers = owm.three_hours_forecast_at_coords(
        lon, lat).get_forecast().get_weathers()

    image = Image.new('1', (epd.width, epd.height), 255)
    draw = ImageDraw.Draw(image)

    pos = 0
    for w in weathers:
        temp = w.get_temperature(unit='celsius')
        wind = w.get_wind()
        time = w.get_reference_time(timeformat='date').astimezone(pytz.timezone(data['place']['timezone'])).strftime("%Hh")
        draw.text((5, pos+10), time, font=small)
        draw.text((45, pos), getWeatherIconCode(w.get_weather_code(), w.get_reference_time() > w.get_sunset_time()), font=meteoSmall)
        draw.text((85, pos), "\uf055", font=meteoSmall)
        draw.text((105, pos+10), str(int(temp['temp'])) + "°", font=small)
        draw.text((145, pos), getWindDirection(wind['deg'], wind['speed']), font=meteoSmall)
        pos += 35

    display(image)

def getWeatherIconCode(code, night = False):
    if code > 800: # Cloud
        return "\uf041"
    elif code == 800: # Clear
        return "\uf02e" if night else "\uf00d"
    elif code >= 700: # Fog
        return "\uf014"
    elif code >= 600: # Snow
        return "\uf076"
    elif code >= 500: # Rain
        return "\uf019"
    elif code >= 300: # Drizzle
        return "\uf0b5"
    elif code >= 200: # Storm
        return "\uf016"

def getWindDirection(deg, speed):
    if (speed * 3600 / 1000 < 40):
        return ""
    else:
        split = round(deg / 8)
        if split == 8:
            return "\uf058"
        elif split == 7:
            return "\uf087"
        elif split == 6:
            return "\uf048"
        elif split == 5:
            return "\uf043"
        elif split == 4:
            return "\uf044"
        elif split == 3:
            return "\uf088"
        elif split == 2:
            return "\uf04d"
        elif split == 1:
            return "\uf057"
        else:
            return "\uf058"

def drawNextInteriorModule():
    global currentInteriorModuleIndex

    modules = []
    for m in data['modules']:
        if 'NAModule4' == m['type']:
            modules.append(m)

    if currentInteriorModuleIndex >= len(modules):
        currentInteriorModuleIndex = 0

    drawModule(modules[currentInteriorModuleIndex])

    currentInteriorModuleIndex += 1


def drawNextExteriorModule():
    global currentExteriorModuleIndex

    modules = []
    for m in data['modules']:
        if 'NAModule4' != m['type']:
            modules.append(m)

    if currentExteriorModuleIndex >= len(modules):
        currentExteriorModuleIndex = 0

    drawModule(modules[currentExteriorModuleIndex])

    currentExteriorModuleIndex += 1


def drawModule(moduleData):
    image = Image.new('1', (epd.width, epd.height), 255)
    draw = ImageDraw.Draw(image)

    # Name
    (x, y) = small.getsize(moduleData['module_name'])
    draw.text(((epd.width - x) / 2, 0), moduleData['module_name'], font=small)

    draw.line((20, 25, epd.width - 20, 25))

    if (moduleData['dashboard_data']):
        type = moduleData['type']
        mesures = moduleData['dashboard_data']

        if 'NAMain' == type or 'NAModule4' == type:  # Main or Interior
            # Temperature
            image.paste(drawTemperature(
                mesures['Temperature'], mesures['min_temp'], mesures['max_temp']), (0, 30))
            # Humidity
            image.paste(drawHumidiy(mesures['Humidity']), (0, 100))
            # CO2
            image.paste(drawCO2(mesures['CO2']), (0, 170))
        elif 'NAModule1' == type:  # Exterior
            # Temperature
            image.paste(drawTemperature(
                mesures['Temperature'], mesures['min_temp'], mesures['max_temp']), (0, 30))
            # Humidity
            image.paste(drawHumidiy(mesures['Humidity']), (0, 100))
            # Pressure
            image.paste(drawPressure(
                data['dashboard_data']['Pressure']), (0, 170))
        elif 'NAModule2' == type:  # Wind
            logging.info("TODO: add wind module")
        elif 'NAModule3' == type:  # Rain
            logging.info("TODO: add rain module")
        else:
            image.paste(drawError("Unknown module type : " + type), (0, 100))

        # Update
        draw.text((5, 240), "\ueedc", font=utility)
        draw.text((25, 240), datetime.fromtimestamp(mesures['time_utc'], pytz.timezone(
            data['place']['timezone'])).strftime("%H:%M"), font=small)
    else:
        image.paste(drawError("No data"), (0, 100))

    draw.line((20, 235, epd.width - 20, 235))

    # Battery
    if 'battery_percent' in moduleData:
        if moduleData['battery_percent'] > 90:
            battery = "\ueeb2"
        elif moduleData['battery_percent'] > 50:
            battery = "\ueeb3"
        elif moduleData['battery_percent'] > 20:
            battery = "\ueeb4"
        else:
            battery = "\ueeb1"

        draw.text((125, 241), battery, font=utility)
        draw.text((150, 240), str(moduleData['battery_percent']), font=small)
    else:
        draw.text((125, 241), "\uf02b", font=utility)
        draw.text((150, 240), str(data['wifi_status']), font=small)

    display(image)


def drawTemperature(current, min, max):
    image = Image.new('1', (epd.height, 100), 255)
    draw = ImageDraw.Draw(image)

    draw.text((15, 7), "\uf055", font=meteo)
    draw.text((60, 0), str(float(current)) + "°", font=big)
    draw.text((45, 40), "\uf088", font=meteoSmall)
    draw.text((60, 50), str(float(min)) + "°", font=small)
    draw.text((110, 40), "\uf057", font=meteoSmall)
    draw.text((125, 50), str(float(max)) + "°", font=small)

    return image


def drawHumidiy(humidity):
    image = Image.new('1', (epd.height, 100), 255)
    draw = ImageDraw.Draw(image)

    draw.text((10, 0), "\uf07a", font=meteo)
    draw.text((60, 10), str(humidity) + "%", font=big)

    return image


def drawCO2(co2):
    image = Image.new('1', (epd.height, 100), 255)
    draw = ImageDraw.Draw(image)

    draw.text((5, 0), "\uf077", font=meteo)
    draw.text((60, 0), str(co2), font=big)
    draw.text((65, 40), "ppm", font=small)

    return image


def drawPressure(pressure):
    image = Image.new('1', (epd.height, 100), 255)
    draw = ImageDraw.Draw(image)

    draw.text((5, 0), "\uf079", font=meteo)
    draw.text((60, 0), str(int(pressure)), font=big)
    draw.text((65, 40), "mbar", font=small)

    return image


def drawError(error):
    image = Image.new('1', (epd.height, 200), 255)
    draw = ImageDraw.Draw(image)

    logging.warn(error)

    draw.text((45, 0), "\uf025", font=utilityBig)
    draw.text((0, 100), error, font=small)

    return image


def terminate():
    # Clear
    display(Image.new('1', (epd.width, epd.height), 255))
    sys.exit()


# Buttons
btn1 = Button(5)
btn2 = Button(6)
btn3 = Button(13)
btn4 = Button(19)

btn1.when_pressed = handleBtnPress
btn2.when_pressed = handleBtnPress
btn3.when_pressed = handleBtnPress
btn4.when_pressed = handleBtnPress

# Signal
signal.signal(signal.SIGTERM, terminate)

while True:
    if (time.time() > nextRefresh):
        refresh()

    time.sleep(10)
