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

import requests

logging.basicConfig(level=logging.DEBUG)

REFRESH_RATE = 600.0
REFRESH_RATE_QUICK = 60.0

OPENWEATHERMAP_API = "http://api.openweathermap.org/data/2.5/onecall?APPID=7f4307249c914cd8ec3fa2a51ac445ba"

# Fonts
small = ImageFont.truetype(
    '/usr/share/fonts/truetype/freefont/FreeSans.ttf', 20)
big = ImageFont.truetype('/usr/share/fonts/truetype/freefont/FreeSans.ttf', 45)
meteo = ImageFont.truetype(os.path.join(
    fontdir, 'weathericons-regular-webfont.ttf'), 45)
meteoSmall = ImageFont.truetype(os.path.join(
    fontdir, 'weathericons-regular-webfont.ttf'), 25)
utility = ImageFont.truetype(os.path.join(fontdir, 'icofont.ttf'), 20)
utilityBig = ImageFont.truetype(os.path.join(fontdir, 'icofont.ttf'), 80)

# Screen
epd = epd2in7.EPD()

# Netatmo
ws = WeatherStation()

# OpenWeatherMap
owm = pyowm.OWM('7f4307249c914cd8ec3fa2a51ac445ba')


nextRefresh = time.time()

def refresh():
    global data
    global forecast
    global nextRefresh
    global currentInteriorModuleIndex
    global currentExteriorModuleIndex
    global currentForecastIsHourly

    logging.info("Refresh data and screen")

    # Get data
    ws.get_data()
    data = ws.devices[0]
    (lon, lat) = data['place']['location']
    forecast = requests.get(OPENWEATHERMAP_API, params={ 
        'lon':   lon,
        'lat':   lat,
        'units': 'metric'
    }).json()


    # Reset module index
    currentInteriorModuleIndex = 0
    currentExteriorModuleIndex = 0
    currentForecastIsHourly = False

    drawModule(data)

    nextRefresh = time.time() + REFRESH_RATE


def handleBtnPress(btn):
    global nextRefresh

    logging.info(str(btn.pin.number) + " pressed")

    switcher = {
        5:  drawForecast,
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


def drawForecast():
    global currentForecastIsHourly

    if currentForecastIsHourly:
        currentForecastIsHourly = False
        drawDailyForecast()
    else:
        currentForecastIsHourly = True
        drawHourlyForecast()

def drawHourlyForecast():
    image = Image.new('1', (epd.width, epd.height), 255)
    draw = ImageDraw.Draw(image)

    sunset = datetime.utcfromtimestamp(forecast['current']['sunset']).astimezone(pytz.timezone(data['place']['timezone'])).time()

    y = 0
    for h in forecast['hourly'][0:7]:
        dt = datetime.utcfromtimestamp(h['dt']).astimezone(pytz.timezone(data['place']['timezone']))
        draw.text((5, y+10),  dt.strftime("%Hh"), font=small)
        centerText(draw, getWeatherIconCode(h['weather'][0]['id'], dt.time() > sunset), meteoSmall, y,  40, 45)
        draw.text((85, y+10), str(int(h['temp'])) + "°", font=small)
        centerText(draw,getWindDirection(h['wind_deg']), meteoSmall, y+5,  120, 25)
        draw.text((145, y+10), str(int(h['wind_speed'] * 3600 / 1000)), font=small)
        y += 36

    display(image)

def drawDailyForecast():
    image = Image.new('1', (epd.width, epd.height), 255)
    draw = ImageDraw.Draw(image)

    y = 0
    for d in forecast['daily'][0:6]:
        dt = datetime.utcfromtimestamp(d['dt']).astimezone(pytz.timezone(data['place']['timezone']))
        draw.text((5, y+10),  dt.strftime("%a"), font=small)
        centerText(draw, getWeatherIconCode(d['weather'][0]['id']), meteoSmall, y,  45, 45)
        draw.text((90, y), str(int(d['temp']['min'])) + "°", font=small)
        draw.text((90, y+20), str(int(d['temp']['max'])) + "°", font=small)
        centerText(draw,getWindDirection(d['wind_deg']), meteoSmall, y+5,  125, 30)
        draw.text((150, y+10), str(int(d['wind_speed'] * 3600 / 1000)), font=small)
        y += 44

    display(image)

def getWeatherIconCode(code, night = False):
    if code > 802: # Full cloud
        return "\uf013"
    elif code == 802: # Cloud
        return "\uf041"
    elif code == 801: # Partial cloud
        return "\uf086" if night else "\uf002"
    elif code == 800: # Clear
        return "\uf02e" if night else "\uf00d"
    elif code >= 700: # Fog
        return "\uf014"
    elif code >= 600: # Snow
        return "\uf076"
    elif code >= 520: # Showers Rain
        return "\uf029" if night else "\uf009" 
    elif code >= 502: # Heavy rain
        return "\uf019"
    elif code >= 500: # Rain
        return "\uf028" if night else "\uf008"
    elif code >= 300: # Drizzle
        return "\uf0b5"
    elif code >= 200: # Storm
        return "\uf016"

def getWindDirection(deg):
    split = round(deg / (360 / 8))
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
    centerText(draw, moduleData['module_name'], small, 0)

    draw.line((20, 25, epd.width - 20, 25))

    if 'dashboard_data' in moduleData:
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
        draw.text((5, 242), "\ueedc", font=utility)
        draw.text(
            (25, 240), 
            datetime.fromtimestamp(
                mesures['time_utc'],
                pytz.timezone(data['place']['timezone'])
            ).strftime("%Hh%M"),
            font=small
        )
    else:
        image.paste(drawError("No data"), (0, 50))
        # Last seen
        if 'last_status_store' in moduleData:
            lastSeen = moduleData['last_status_store']
        else:
            lastSeen = moduleData['last_seen']
        draw.text((5, 240), "\ueedc", font=utility)
        draw.text(
            (30, 240),
            datetime.fromtimestamp(
                lastSeen,
                pytz.timezone(data['place']['timezone'])
            ).strftime("%H:%M"),
            font=small
        )

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

    centerText(draw, "\uf055", meteo, 5, width=60)
    temp = str(float(current))
    (w,h) = big.getsize(temp)
    draw.text((60, 0), temp, font=big)
    draw.text((60+w, -10), "\uf03c", font=meteo)
    draw.text((50, 52), "\ueab2", font=utility)
    draw.text((70, 50), str(float(min)), font=small)
    draw.text((110, 52), "\ueab9", font=utility)
    draw.text((130, 50), str(float(max)), font=small)

    return image


def drawHumidiy(humidity):
    image = Image.new('1', (epd.height, 100), 255)
    draw = ImageDraw.Draw(image)

    centerText(draw, "\uf07a", meteo, 5, width=60)
    draw.text((60,10), str(humidity) + "%", font=big)

    return image


def drawCO2(co2):
    image = Image.new('1', (epd.height, 100), 255)
    draw = ImageDraw.Draw(image)

    centerText(draw, "\uf077", meteo, 0, width=60)
    draw.text((60,0), str(co2), font=big)
    draw.text((60,40), "ppm", font=small)

    return image


def drawPressure(pressure):
    image = Image.new('1', (epd.height, 100), 255)
    draw = ImageDraw.Draw(image)

    centerText(draw, "\uf079", meteo, 0, width=60)
    draw.text((60,0), str(int(pressure)), font=big)
    draw.text((60,40), "mbar", font=small)

    return image


def drawError(error):
    image = Image.new('1', (epd.height, 200), 255)
    draw = ImageDraw.Draw(image)

    logging.warning(error)

    centerText(draw, "\uf025", utilityBig, 0)
    centerText(draw, error, small, 100)

    return image

def centerText(draw, text, font, y, x = 0, width = epd.width, debug=False):
    w,h = font.getsize(text)
    draw.text((x + ((width - w) / 2), y), text, font=font)
    if debug:
        draw.rectangle((x,y,x+width,y+h))

def rightText(draw, text, font, height, width = epd.width):
    if (width < 0):
        width = epd.width + width

    w,h = font.getsize(text)
    draw.text(((width - w), height), text, font=font)

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
