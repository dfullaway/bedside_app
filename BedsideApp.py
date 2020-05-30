from os import system, environ

environ['KIVY_GL_BACKEND'] = 'gl'
from kivy.app import App
from kivy.uix.screenmanager import Screen
from kivy.properties import ListProperty
import kivy.clock
from kivy.network.urlrequest import UrlRequest
from time import strftime, mktime, time, strptime
from platform import machine
import configparser
from subprocess import Popen
import datetime
import random
import glob
import paho.mqtt.client as mqtt
import signal
import pickle
from ha_helpers import getState, set_scene, switch_on, ha_setup, getStateAttributes
from kivy.support import install_twisted_reactor
import requests

install_twisted_reactor()
from twisted.internet import reactor
from twisted.internet import protocol
import rpi_backlight
import json

__author__ = 'Dan Fullaway'

# TODO Setup Logging

# If the machine is not a Pi, treat it as a test machine
if machine() == 'armv7l':
    PI = True
    CHANNEL = 'Master'
else:
    PI = False
    CHANNEL = 'Master'


def mqttc_fail(signum, frame):
    print('No mqttc client connection!')
    # raise TimeoutError


def setup_mqtt():
    try:
        signal.signal(signal.SIGALRM, mqttc_fail)
        signal.alarm(5)
        mqttc = mqtt.Client(client_id=CLIENT_NAME, clean_session=False)
        mqttc.tls_set(CERT_PATH)
        mqttc.username_pw_set(CLIENT_NAME, PASSWORD)
        mqttc.connect(SERVER, port=8883)

        # Subscribe to topics related to settings for light
        mqttc.subscribe([(TOPIC_STRING + '/light/switch', 2), (TOPIC_STRING + '/light/brightness/set', 2),
                         (TOPIC_STRING + '/light/rgb/set', 2), ('hermes/intent/dfullaway:SetAlarm', 2),
                         ('home/daenerys/backlight', 2)])

        mqttc.loop_start()
        signal.alarm(0)
    except:
        print('MQTT Connection Failed!')
        # Logger.warning('MQTT: connection failure')

    mqttc.on_message = on_message
    mqttc.on_disconnect = on_disconnect
    return mqttc


# Callbacks for MQTT
def on_message(client, userdata, message):
    """
    Handles receipt of message from MQTT Server; currently sets lights as appropriate
    :param client:
    :param userdata:
    :param message: Payload
    :return:
    """
    # print(message.topic, message.payload)
    # Logger.debug('MQTT: Message with topic %s and payload %s', message.topic, message.payload)
    if message.topic == TOPIC_STRING + '/light/switch':
        if message.payload == b'OFF':
            set_lights(current_light, False)
        elif message.payload == b'ON':
            set_lights(current_light, True)
    elif message.topic == TOPIC_STRING + '/light/brightness/set':
        set_lights([current_light[0], current_light[1], current_light[2], float(message.payload) / 255.0], True)
    elif message.topic == TOPIC_STRING + '/light/rgb/set':
        temp = message.payload.decode('ascii').split(',')
        set_lights([float(temp[0]) / 255, float(temp[1]) / 255, float(temp[2]) / 255, current_light[3]], True)
    elif message.topic == 'hermes/intent/dfullaway:SetAlarm':
        print('Alarm Message Recieved')
        if PI:
            message.payload = message.payload.decode('UTF-8')
        Intent = json.loads(message.payload)
        alarmTime = datetime.datetime(*strptime(Intent["slots"][0]["value"]["value"].replace(':', ''),
                                                '%Y-%m-%d %H%M%S %z')[:6])
        # site = Intent["siteId"]
        session = Intent["sessionId"]
        BedsideApp.schedule_alarm(top, alarmTime)
        response = '{"SessionId":"{ ' + session + ' }", "text":"Alarm has been set"}'
        # print(response)
        mqttc.publish('hermes/dialogueManager/endSession', payload=response)
    elif message.topic == 'home/daenerys/backlight':
        if (message.payload == b'DIM'):
            BedsideApp.backlight_dim(top)
        elif (message.payload == b'BRIGHT'):
            BedsideApp.backlight_bright(top)
        else:
            print(message.payload)


def on_disconnect(client, userdata, rc):
    setup_mqtt()


# Setup Protocol and Factory for Twisted Reactor / Pianobar event script

class PandoraProtocol(protocol.Protocol):

    def dataReceived(self, data):
        self.factory.app.handle_message(data)


class PandoraFactory(protocol.Factory):
    protocol = PandoraProtocol

    def __init__(self, app):
        self.app = app


def cToF(temp):
    return (temp * 9.0/5.0)+32

def set_lights(light_intensity, light_state):
    """
    :param light_intensity: a list of four values between 0 and 1 representing red, green, blue and brightness
    :param light_state: a True/False indicating if the light should be off or on
    :return:
    """
    global current_light
    current_light = light_intensity
    if PI:
        system('echo "%d=%f" > /dev/pi-blaster' % (RED_PIN, float(current_light[0] * current_light[3]) * light_state))
        system('echo "%d=%f" > /dev/pi-blaster' % (GREEN_PIN, float(current_light[1] * current_light[3]) * light_state))
        system('echo "%d=%f" > /dev/pi-blaster' % (BLUE_PIN, float(current_light[2] * current_light[3]) * light_state))
    else:
        print(light_intensity)
        print(float(current_light[0] * current_light[3]) * light_state)
    if light_state is False or current_light[3] == 0:
        status = 'OFF'
    else:
        status = 'ON'
    mqttc.publish(TOPIC_STRING + '/light/status', status, 2, retain=True)
    mqttc.publish(TOPIC_STRING + '/light/brightness/status', int(light_intensity[3] * 255), 2, retain=True)
    rgb_status = ','.join(str(int(num * 255)) for num in light_intensity[:3])
    mqttc.publish(TOPIC_STRING + '/light/rgb/status', rgb_status, 2, retain=True)


class ClockWidget(Screen):
    '''
    Setup for Main Screen
    '''

    def __init__(self, **kwargs):
        Screen.__init__(self, **kwargs)

        # Initiates the Clock
        kivy.clock.Clock.schedule_interval(self.clockupdater, 0.2)

    def clockupdater(self, dt):
        """
        Updates the clock
        :param dt: How often to update the clock
        :return: None
        """
        self.ids['time'].text = strftime("%H%M:%S")
        self.ids['date'].text = strftime("%a, %d %B %Y")
        return None

    def start_clock(self):
        """
        Restarts clock when returning to main screen
        :return:
        """
        # print('Started')
        kivy.clock.Clock.schedule_interval(self.clockupdater, 0.2)

    def stop_clock(self):
        '''
        Stops clock when leaving main screen
        :return:
        '''
        # print('Stopped')
        kivy.clock.Clock.unschedule(self.clockupdater)

    def set_scene(self, scene):
        set_scene(scene)


class ProgramDialog(Screen):

    def __init__(self, **kw):
        Screen.__init__(self, **kw)

    def set_scene(self, scene):
        set_scene(scene)


class WeatherPage(Screen):

    def __init__(self, **kw):
        Screen.__init__(self, **kw)
        if int(strftime("%H")) < 17:
            self.i = 0
        else:
            self.i = 1

    def fill_page(self):
        """
        Run upon entering the weather page. Checks to ensure latest weather was pulled, then displays it. Shows blank
        if the previous weather pull failed.
        :return:
        """
        # global top

        def add_current_weather(req, result):
            jsonresult = json.loads(result)
            self.ids.locationlabel.text = 'Weather at {0} as of {1}'.format(jsonresult['properties']['rawMessage'][:4],
                                                                       jsonresult['properties']['rawMessage'][5:13])

            self.ids.currenttemp.text = str(round(cToF(jsonresult['properties'] ['temperature']['value'])))  + '\u00B0 F'
            self.ids.currenthumidity.text = str(round(jsonresult['properties']['relativeHumidity']['value']))+ '%'
            self.ids.currentwind.text = '{0} at {1} knots'.format(jsonresult['properties']['windDirection']['value'],
                                                                  round(jsonresult['properties']['windSpeed']['value']
                                                                        *1.944))
            #self.ids.currentsky.text = str(jsonresult['properties']['rawMessage'][13:])


        headers = {'Content-Type': 'application/json', 'User-Agent': '(MyAlarmClock, dfullaway@danielmfullaway.com)'}

        UrlRequest('https://api.weather.gov/stations/klgb/observations/latest', add_current_weather,
                         req_headers=headers, decode=True)

        weatherJson = getStateAttributes('weather.klgb_daynight')['attributes']
        nextWeatherJson = weatherJson['forecast'][1]
        followingWeatherJson = weatherJson['forecast'][2]
        current_summary = weatherJson['forecast'][0]['detailed_description']
        tomorrow_high = max(nextWeatherJson['temperature'], followingWeatherJson['temperature'])
        tomorrow_low = min(nextWeatherJson['temperature'], followingWeatherJson['temperature'])
        tomorrow_condition = nextWeatherJson['detailed_description']

        try:
            self.ids.currentsky.text = current_summary
            self.ids.forecasthigh.text = '{0}\u00B0 F'.format(tomorrow_high)
            self.ids.forecastlow.text = '{0}\u00B0 F'.format(tomorrow_low)
            self.ids.forecastsky.text = tomorrow_condition
        except AttributeError:
            pass


class AlarmSchedule(Screen):

    def __init__(self, **kw):
        Screen.__init__(self, **kw)

    def time_handler(self):
        """
        Takes the time displayed on the alarm schedule screen and schedules the alarm for that time. Currently sets for
        the current day if the time shown is later than the current time or the following day if the time shown is
        earlier than the current time.
        :return:
        """
        tomorrow = datetime.date.today() + datetime.timedelta(days=1)
        use_hour = int(self.ids.alarmhour.text)
        if self.ids.alarmAMPM.text == "PM":
            if use_hour == 12:
                use_hour = 12
            else:
                use_hour += 12
        elif self.ids.alarmAMPM.text == "AM" and use_hour == 12:
            use_hour = 0
        if int(strftime("%H")) > use_hour:
            use_date = tomorrow
        else:
            use_date = datetime.date.today()
        use_time = datetime.time(hour=use_hour, minute=int(self.ids.alarmminute.text))
        dtg = datetime.datetime.combine(use_date, use_time)
        top.schedule_alarm(dtg)

    def test(self):
        """
        Used during testing only. Should not be called during production.
        :return:
        """
        use_hour = int(strftime("%H"))
        use_time = datetime.time(hour=use_hour, minute=int(strftime("%M")) + 1)
        dtg = datetime.datetime.combine(datetime.date.today(), use_time)
        top.schedule_alarm(dtg)

    def nap(self):
        '''
        Sets a 20 minute nap. Currently broken - simply adds 20 minutes to the current minute. Should be updated to use
        datetime functions to add 20 minutes.
        :return:
        '''
        use_hour = int(strftime("%H"))
        use_time = datetime.datetime.now() + datetime.timedelta(minutes=20)
        # use_time = datetime.time(hour=use_hour, minute=int(strftime("%M"))+20)
        # dtg = datetime.datetime.combine(datetime.date.today(), use_time)
        top.schedule_alarm(use_time)


class AlarmCancel(Screen):

    def __init__(self, **kw):
        Screen.__init__(self, **kw)

    def canceler(self, text):
        for date in top.alarm_schedule:
            if date[0].strftime('%d %b %H%M') == text:
                top.cancel_method(date)


class Alarm(Screen):
    def __init__(self, **kw):
        Screen.__init__(self, **kw)
        self.redmax = .5
        self.greenmax = 1.0
        self.bluemax = 1.0
        self.counter = 1

    def trigger(self):
        """
        Runs upon the alarm triggering. Sets the weather text, starts the music and lights coming up and turns on the
        screen if currently off.
        :return:
        """
        weatherJson = getStateAttributes('weather.klgb_daynight')['attributes']

        current_summary = weatherJson['forecast'][0]['detailed_description']

        string = "Today's Weather: {0}".format(current_summary)

        self.ids.wakeupweather.text = string
        self.song = self.choose_song()
        Popen(['rpi-backlight', '-b', '255', '-s', '-d', '3'])

        # Start Song with fade in and Stepup method to increase volume and brightness
        self.snd = Popen(["play", self.song, 'fade', '45', 'vol', '45'])
        switch_on('coffee_machine')
        kivy.clock.Clock.schedule_interval(self.stepup, 1.5)

    def stepup(self, dt):
        """
        Increases volume of audio and lights
        :param dt: required for scheduling with Kivy clock function, amount of time between increments
        :return: Boolean
        """
        # Check if volume is less than maximum - increases volume and lights if it is
        if self.counter < (MAX_VOLUME) + 1:
            self.counter += 1
            # Popen(["amixer", 'sset', CHANNEL, str(self.counter) + '%'])
            set_lights([self.redmax, self.greenmax, self.bluemax, float(self.counter) / 100], True)

        elif self.counter >= MAX_VOLUME and self.snd.poll() is not None:
            top.alarm_schedule_update()
            self.counter = 1
            return False

    def cancel_alarm(self):
        """
        Stops the in progress alarm
        :return:
        """
        # Stop the loop that changes volume and light level
        kivy.clock.Clock.unschedule(self.stepup)
        # Stops Audio
        self.snd.terminate()
        # Shuts off lights
        set_lights(current_light, False)
        # Resets Counter (used to increment lights and sound)
        self.counter = 1
        # Update the Alarm Schedule
        top.alarm_schedule_update()

    def choose_song(self):
        """ Randomly chooses a song from the given directory and returns its location
        Returns: String"""
        song_list = glob.glob(MUSIC_DIR + '*.mp3')
        song = random.choice(song_list)
        return song


class Lights(Screen):
    def __init__(self, **kw):
        Screen.__init__(self, **kw)
        self.light_state = light_state

    def set_color(self):
        set_lights([self.ids.cp.color[0], self.ids.cp.color[1], self.ids.cp.color[2], self.ids.cp.color[3]], self.light_state)
        light_state = self.light_state


class PandoraRadio(Screen):
    def __init__(self, **kw):
        Screen.__init__(self, **kw)
        self.paused = False

    def send_command(self, command):
        if music:
            self.fifo = open(fifopath, "w")
            self.fifo.write(command)
            self.fifo.flush()
            self.fifo.close()

    def pause_play(self):
        self.send_command('p')
        if self.paused and music:
            top.root.ids.radio.ids.pauseimage.source = 'ic_pause_white_48dp_1x.png'
            top.root.ids.radio.ids.pauseimage.reload()
            self.paused = False
        elif music:
            top.root.ids.radio.ids.pauseimage.source = 'ic_play_arrow_white_48dp_1x.png'
            top.root.ids.radio.ids.pauseimage.reload()
            self.paused = True
        elif not music:
            top.root.ids.radio.ids.pauseimage.source = 'ic_pause_white_48dp_1x.png'
            top.root.ids.radio.ids.pauseimage.reload()
            self.paused = False
            top.start_standard_music()


class ScreenOff(Screen):
    def __init__(self, **kw):
        Screen.__init__(self, **kw)

    def on_enter(self, *args):
        top.backlight_swap()

    def on_leave(self, *args):
        top.backlight_swap()


class BedsideApp(App):

    def __init__(self, **kw):
        App.__init__(self, **kw)
        self.counter = int(MAX_VOLUME)
        self.weather_conds = []

    alarm_schedule = ListProperty()

    def build(self):
        reactor.listenTCP(50007, PandoraFactory(self))
        self.counter = int(MAX_VOLUME)
        self.weather_conds = []
        self.weather_update()
        self.temp_update()
        set_lights(current_light, False)
        try:
            #with open('/home/pi/.local/bin/alarmschedule', 'rb') as f:
            with open(ALARMFILE, 'rb') as f:
                sched = pickle.load(f)
            for alarm in sched:
                self.schedule_alarm(alarm)
        except EOFError:
            pass
        kivy.clock.Clock.schedule_interval(lambda dt: self.weather_update(), 600)
        kivy.clock.Clock.schedule_interval(lambda dt: self.temp_update(), 60)

    def start_sleep_music(self):
        global music
        self.redmax = 1.0
        self.greenmax = 0.5
        music = True
        self.root.ids.home.ids['program'].text = 'Night Music'
        Popen(["amixer", 'sset', CHANNEL, str(self.counter) + '%'])
        green = (self.greenmax * float(self.counter - 40) * .01) ** 2
        red = (self.redmax * float(self.counter - 40) * .01) ** 2
        if PI:
            system('echo "%d=%f" > /dev/pi-blaster' % (RED_PIN, red))
            system('echo "%d=%f" > /dev/pi-blaster' % (GREEN_PIN, green))
        pandora = Popen(['pianobar'])
        # self.fifo = open(fifopath, "w")
        # self.fifo.flush()
        kivy.clock.Clock.schedule_interval(self.stepdown, 30)

    def start_standard_music(self):
        global music
        music = True
        self.root.ids.home.ids['program'].text = 'Playing Music'
        Popen(["amixer", 'sset', CHANNEL, str(MAX_VOLUME) + '%'])
        Popen(['pianobar'])

    def stepdown(self, dt):
        Popen(["amixer", 'sset', CHANNEL, str(self.counter) + '%'])
        # Popen(["pactl", ])
        self.counter -= 1
        set_lights([self.redmax, self.greenmax, 0, (float(self.counter - 40) * .01) ** 2], True)
        if self.counter == (MAX_VOLUME - 40):
            self.pandora_cleanup()
            self.counter = MAX_VOLUME
            return False

    def program_ender(self):
        kivy.clock.Clock.unschedule(self.stepdown)
        self.pandora_cleanup()
        self.counter = MAX_VOLUME
        self.root.current = 'Home'

    def pandora_cleanup(self):
        global music
        if music:
            music = False
            try:
                self.fifo = open(fifopath, 'w')
                self.fifo.write('q')
                self.fifo.flush()
                self.fifo.close()
            except AttributeError:
                pass
            Popen(['amixer', 'sset', CHANNEL, str(MAX_VOLUME) + '%'])
            set_lights(current_light, False)
            self.root.ids.home.ids['program'].text = 'None'
            self.root.ids.home.ids.musicdisplay.text = " "
            self.root.ids.radio.ids.songdetail.text = ''
            self.root.ids.radio.ids.stationlabel.text = ''
            self.root.ids.radio.ids.musicpicture.source = 'pandora-internet-radio.jpg'
            self.root.ids.radio.ids.musicpicture.reload()

    def weather_update(self):
        """  Updates weather information
        Text turns red if update of weather fails
        :return:None

        """
        weatherJson = getStateAttributes('weather.klgb_daynight')
        weather = requests.get('https://api.weather.gov/stations/klgb/observations/latest',
                               headers={'accept': 'application/geon+json'})
        try:
           outside_temp = str(weatherJson['attributes']['temperature'])
        except KeyError:
            outside_temp = "Unknown"
        except TypeError:
            outside_temp ="Unknown"
        try:
           weather_condition = weather.json()['properties']['textDescription']
        except KeyError:
            weather_condtion = "Unknown"
        self.root.ids.home.ids.weather.color = [1, 1, 1, 1]
        try:
            self.root.ids.home.ids.weather.text = (weather_condition + '\n' + outside_temp + '\u00B0 F')
        except AttributeError:
            self.root.ids.home.ids.weather.color = [1, 0, 0, 1]
            self.root.ids.home.ids.weather.text = "Unknown"

    def schedule_alarm(self, alarm_time):
        """
        
        :rtype: None
        :param alarm_time: Time that the alarm should be triggered
        :return: None
        """
        time_delta = int(mktime(alarm_time.timetuple()) - time())
        if time_delta > 0:
            t = kivy.clock.Clock.schedule_once(self.alarm, time_delta)
            top.alarm_schedule.append([alarm_time, t])
            stored_alarm_schedule.append(alarm_time)
            with open(ALARMFILE,'wb') as f:
                pickle.dump(stored_alarm_schedule, f)

        self.alarm_schedule_update()

    def alarm_schedule_update(self):
        updated = []
        for date in top.alarm_schedule:
            if date[0] > datetime.datetime.today():
                updated.append(date)
        if len(updated) > 0:
            top.alarm_schedule = updated[:]
        else:
            top.alarm_schedule = []
        top.alarm_schedule.sort()
        if len(top.alarm_schedule):
            string = 'Next:\n' + top.alarm_schedule[0][0].strftime('%d %b %H%M')
        else:
            string = 'None'
        self.root.ids.home.ids.alarm.text = string

    def cancel_method(self, date):
        kivy.clock.Clock.unschedule(date[1])
        top.alarm_schedule.remove(date)
        stored_alarm_schedule.remove(date[0])
        self.alarm_schedule_update()

    def alarm(self, *args):
        print('alarm has been called')
        self.root.current = 'Alarm'

    def pre_alarm(self, *args):
        """
        Starts lights and coffee early.
        :param args:
        :return:
        """

    def temp_update(self):
        with open(TEMPFILE, 'r') as f:
            data = f.read()
        temp, hum = data.split('\n')
        temp = temp.replace('Temp:', '').replace('deg F', '')
        hum = hum.replace('Humidity:', '').replace('%', '')
        topic_temp = TOPIC_STRING + '/temp'
        topic_hum = TOPIC_STRING + '/humidity'
        mqttc.publish(topic_temp, temp, qos=2)
        mqttc.publish(topic_hum, hum, qos=2)
        data = data.replace('deg', '\u00B0')
        self.root.ids.home.ids.roomtemp.text = data

    def backlight_swap(self):
        """ Dims and brightens the back light for the display. 
        No arguments
        returns nothing
        """
        global backlit
        # print("Swapped!")
        if PI:
            if rpi_backlight.get_actual_brightness() < 50:
                Popen(['rpi-backlight', '-b', '255', '-s', '-d', '3'])
            else:
                Popen(['rpi-backlight', '-b', '11', '-s', '-d', '3'])
    
    def backlight_bright(self, lightLevel='255'):
        """Brightens the back light for the display.
        arguments: lightLevel
        returns nothing
        """
        if PI:
            Popen(['rpi-backlight', '-b', lightLevel, '-s', '-d', '3'])
        print('Light level set to %s', lightLevel)

    def backlight_dim(self):
        if PI:
            Popen(['rpi-backlight', '-b', '11', '-s', '-d', '3'])

    def handle_message(self, msg):
        pandora_fields = pickle.loads(msg)
        # print('Message Arrived!')
        if pandora_fields['event'] == 'songstart':
            self.root.ids.home.ids.musicdisplay.text = "Song: %s\nArtist: %s" % (pandora_fields['title'],
                                                                                 pandora_fields['artist'])
            self.root.ids.radio.ids.songdetail.text = '%s by %s' % (pandora_fields['title'], pandora_fields['artist'])
            self.root.ids.radio.ids.stationlabel.text = pandora_fields['stationName']
            self.root.ids.radio.ids.musicpicture.source = pandora_fields['coverArt']
            self.root.ids.radio.ids.musicpicture.reload()
            if pandora_fields['rating'] == 1:
                self.root.ids.radio.ids.thumbsup.color = [0, 0, .6, 1]
            else:
                self.root.ids.radio.ids.thumbsup.color = [1, 1, 1, 1]
            self.root.ids.radio.ids.thumbsup.reload()
            print(pandora_fields)

        elif pandora_fields['event'] == 'songlove':
            self.root.ids.radio.ids.thumbsup.color = [0, 0, .6, 1]
        elif pandora_fields['event'] == 'songstop':
            self.root.ids.home.ids.musicdisplay.text = " "
            self.root.ids.radio.ids.thumbsup.color = [1, 1, 1, 1]


if __name__ == '__main__':
    # TODO Get configuration file location from command line
    # Import Settings from a configuration file in the same folder as the executable
    config = configparser.ConfigParser()
    #config.read("./config.txt")
    config.read('/home/pi/.config/bedsideapp/config.txt')
    lights = config['Lights']
    RED_PIN = lights.getint('Red', fallback='4')
    GREEN_PIN = lights.getint('Green', fallback='22')
    BLUE_PIN = lights.getint('Blue', fallback='24')
    location = config['Location']
    CURRENT_ZIP = location.get('Zip', fallback='92057')
    sounds = config['Sounds']
    MUSIC_DIR = sounds.get('MusicDir', fallback='/home/dan/Music/')
    MAX_VOLUME = int(sounds.get('MaxVolume', fallback='90'))
    sensor = config['Sensor']
    TOPIC_STRING = sensor.get('MqttPath')
    CERT_PATH = sensor.get('CertPath')
    CLIENT_NAME = sensor.get('ClientName')
    PASSWORD = sensor.get('PW')
    SERVER = sensor.get('ServerAddress')
    home = config['HomeAssistant']
    HAServer = home.get('Server')
    HAToken = home.get('TOKEN', fallback='')
    PATHS = config['LocalPaths']
    fifopath = PATHS.get('fifo')
    ALARMFILE = PATHS.get('Alarm')
    TEMPFILE = PATHS.get('Temperature')

    # Setup connection to Home Assistant
    HAURL = 'http://' + HAServer + ':8123/api/'
    TOKEN = 'Bearer ' + HAToken
    ha_setup(HAURL, TOKEN)

    # Setup MQTT Client and connect
    stored_alarm_schedule = []
    current_light = [0, 0, 0, 0]  # Current state of LEDs
    light_state = False
    music = False
    mqttc = setup_mqtt()

    top = BedsideApp()
    top.run()
