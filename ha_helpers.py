import requests
from urllib3.exceptions import MaxRetryError

HAURL = ""
headers = {}

def ha_setup(url, token):
    global HAURL, headers
    HAURL = url
    headers = {
        'Authorization': token,
        'content-type': 'application/json',
    }

def getState(entity):
    try:
        response = requests.get(HAURL + 'states/'+ entity, headers=headers)
    except TimeoutError:
        return "Host not available"
    except MaxRetryError:
        return "Network Issues"
    return response.json()["state"]

def getStateAttributes(entity):
    try:
       response = requests.get(HAURL + 'states/' + entity, headers=headers)
    except MaxRetryError:
        return "Network Issues"
    except ConnectionError:
        return "Network Issues"
    except requests.ConnectionError:
        return "Connection Error"
    return response.json()

def set_scene(scene):
    string_scene = '"scene.' + str(scene) + '"'
    post_url = HAURL + 'services/scene/turn_on'
    data = '{"entity_id":' + string_scene + '}'
    requests.post(post_url, headers=headers, data=data)

def switch_on(switch):
    string_switch = '"switch.' + str(switch) + '"'
    post_url = HAURL + 'services/switch/turn_on'
    data = '{"entity_id":' + string_switch +'}'
    requests.post(post_url, headers=headers, data=data)

def switch_toggle(switch):
    string_switch = '"switch.' + str(switch) + '"'
    post_url = HAURL + 'services/switch/toggle'
    data = '{"entity_id":' + string_switch +'}'
    requests.post(post_url, headers=headers, data=data)