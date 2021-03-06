#!/usr/bin/env python3
import argparse
import hashlib
import json
import logging
import socket
import sys
import time



__version__ = "1.0.1"
major, minor, micro, release_level, serial = sys.version_info
if (major, minor) == (2, 7):
    try:
        import httplib as http_client
    except ImportError as ie:
        print(ie)
        print("Error httplib not found in this version: {}.{}".format(major,
                                                                      minor))
elif major >= 3:
    import http.client as http_client

logger = logging.getLogger(__name__)

def get_version():
    return __version__

class HueObject:
    def __init__(self, ip, username):
        self.ip = ip
        self.create_user_url = "/api"
        self.base_uri = self.create_user_url + "/" + username
        self.user = username
        self.logger = logging.getLogger(__name__ + ".HueObject")
        self.device_type = 'phuey'

    def _req(self, url, payload=None, meth="GET"):
        self.logger.debug("{} on {}".format(meth, url, payload))
        connection = http_client.HTTPConnection(self.ip, 80, timeout=3)
        body = None
        if payload:
            body = json.dumps(payload).encode()
            self.logger.debug("Body: {}".format(payload))
        ct = {"Content-type": "application/json"}
        connection.request(meth, url, body, ct)
        try:
            response = connection.getresponse()
        except ConnectionRefusedError:
            self.logger.critical("Connection refused from bridge!")
            exit()
        else:
            if response.status >= 400:
                self.logger.error(response.reason)
                raise ValueError("Invalid server response")
            self.logger.debug("Bridge header response: {}".format(
                                                      response.getheaders()))
            self.logger.debug("status: {}".format(response.status))
            resp_payload = response.read().decode("utf-8")
            self.logger.debug("Bridge response: {}".format(resp_payload))
            payload = self.error_check_response(resp_payload)
            return payload

    def find_new_lights(self):
        add_light_url = self.base_uri + "/lights"
        resp = self._req(add_light_url, None, "POST")
        result_code, message = list(resp[0].keys()), list(resp[0].values())
        if result_code == 'success':
            logger.info(message[0]['/lights'])
        else:
            logger.error(message[0]) 

    def error_check_response(self, non_json_payload):
        payload = json.loads(non_json_payload)
        if isinstance(payload, list) and 'error' in payload[0]:
            description = payload[0]['error']['description']
            self.logger.error(description)
            if isinstance(self, Light) and 'off' not in description:
                self.logger.warning("Is this a Link or Lux bulb?")
                self.logger.error("Can't change this parameter!")
        else:
            return payload

    def authorize(self):
        auth_payload = {'devicetype': self.device_type, 'username': self.user}
        self.logger.debug(auth_payload)
        self._req(self.create_user_url, auth_payload, "POST")

    def __str__(self):
        if isinstance(self, Light):
            return "Light id: {} name: {} currently on: {}".format(
                               self.light_id, str(self.name), self.on)
        elif isinstance(self, Bridge):
            self.logger.debug(type(self))
            return "name: {} with {} light(s)".format(self.name,
                                                      len(self.lights))
        elif isinstance(self, Scene):
            self.logger.debug(type(self))
            return "Scenes: {}".format(self.scenes)
        elif isinstance(self, Group):
            groups = []
            for key, value in self.__dict__.items():
                if key.isdigit():
                    groups.append(key)
                    
            return "Group IDs: {}".format(sorted(groups))

    def __repr__(self):
        if isinstance(self, Light):
            return "Light id: {} name: {} currently on: {}".format(
                               self.light_id, str(self.name), self.on)
        elif isinstance(self, Scene):
            return "Scenes: {}".format(self.scenes)
        else:
            logger.error("HueObject can't coerce the repr method for your object")
            return 'ERROR'


class HueDescriptor:
    def __init__(self, name, initval):
        self.name = initval
        self.__name__ = name
        self.logger = logging.getLogger(__name__ + ".HueDescriptor")

    def __get__(self, inst, cls):
        self.logger.debug("calling get on {}".format(type(inst)))
        self.logger.debug("{} keys".format(inst.__dict__.keys()))
        self.logger.debug("is a {}".format(cls))
        if cls is Light:
            return inst._req(inst.get_state_uri, None, "GET")
        elif cls is Group:
            return inst._req(inst.uri, None, "GET")
        else:
            self.logger.debug(cls)
     
        try:
            return inst.__dict__[self.__name__]
        except KeyError as ke:
            msg = "{} not a valid read parameter for {}".format(ke, inst)
            return msg

            

    def __set__(self, inst, val):
        dbg_msg = "calling set on: {} from: {} to: {} ".format(self.__name__,
                                                               self.name, val)
        self.logger.debug(dbg_msg)
        if val is None:
            val = "none"
        if self.__name__ is 'state':
            self.logger.debug("__name__ is state!")
            for key, value in val.items():
                logger.debug('{} {}'.format(inst.__dict__.keys(), key))
                inst.__dict__[key] = value
            inst._req(inst.state_uri, val, "PUT")
            return
        if self.__name__ is not 'light_id':
            self.logger.debug("val: {}".format(val))
            if isinstance(inst, Light) and self.__name__ == "name":
                self.logger.debug("{} {}".format(val, type(val)))
                self.logger.debug(inst.__dict__.keys())
                self.logger.debug(type(inst))
                if (inst.__dict__[self.__name__] is not None or
                inst.__dict__[self.__name__] is not "None"):
                    self.logger.debug("self.__name__ is {}".format(
                                                               self.__name__))
                    input('press enter to continue...')
            elif isinstance(inst, Light) and self.__name__ != "name":
                if val is not None:
                    self.logger.debug("calling req against: {}".format(
                                                              inst.state_uri))
                    inst._req(inst.state_uri, {self.__name__: val}, "PUT")

            elif isinstance(inst, Group):
                payload = {self.__name__: val}
                inst._req(inst.state_uri, payload, "PUT")
            else:
                self.logger.debug("How the fuck did I get here?")
                self.logger.debug("type of {} is {}".format(inst, type(inst)))
                self.logger.debug(self.__name__)
                quit(0)

        else:
            self.logger.debug("{} {} {}".format(self.__name__, self.name, val))
            self.logger.debug("{} is None!".format(self.__name__))
        inst.__dict__[self.__name__] = val
        self.logger.debug(inst.__dict__.keys())

    def __str__(self):
        return self.name


class Light(HueObject):
    on = HueDescriptor('on', None)
    bri = HueDescriptor('bri', None)
    xy = HueDescriptor('xy', None)
    ct = HueDescriptor('ct', None)
    sat = HueDescriptor('sat', None)
    hue = HueDescriptor('hue', None)
    alert = HueDescriptor('alert', None)
    effect = HueDescriptor('effect', None)
    state = HueDescriptor('state', None)
    transitiontime = HueDescriptor('transitiontime', None)
    reachable = HueDescriptor('reachable', None)

    def __init__(self, ip, username, light_id, name, model, start_state=None):
        super().__init__(ip, username)
        self.light_id = light_id
        self.modelid = model 
        self.name = HueDescriptor('name', name)
        self.logger = logging.getLogger(__name__ + ".Light")
        self.name_uri = self.base_uri + "/lights/" + str(self.light_id)
        self.get_state_uri = self.name_uri
        self.state_uri = self.name_uri + "/state"
        if start_state:
            self.logger.debug(type(start_state))
            self.logger.debug(start_state)
            for key, value in json.loads(start_state).items():
                self.__dict__[key] = value
        self.__dict__['transitiontime'] = 4

    def __gt__(self, other):
        return self.light_id > other.light_id

    def __lt__(self, other):
        return self.light_id < other.light_id

    def __eq__(self, other):
        return not self.light_id < other and not other.light_id < self.light_id

    def __getitem__(self, key):
        if isinstance(key, str):
            self.logger.debug("returning by key: {}".format(key))
            for dict_key, value in self.__dict__.items():
                logger.debug(value)
                logger.debug(type(value))
                if key.lower() == dict_key.lower():
                    return value
#             return "Can't find light by id or name of {}".format(key)
#         else:
#             self.logger.debug('returning by light id')
#             return self._get_light_by_id(key)


class Group(HueObject):
    on = HueDescriptor('on', None)
    bri = HueDescriptor('bri', None)
    xy = HueDescriptor('xy', None)
    ct = HueDescriptor('ct', None)
    sat = HueDescriptor('sat', None)
    hue = HueDescriptor('hue', None)
    alert = HueDescriptor('alert', None)
    effect = HueDescriptor('effect', None)
    state = HueDescriptor('state', None)
    transitiontime = HueDescriptor('transitiontime', None)
    reachable = HueDescriptor('reachable', None)
    def __init__(self, ip, user, group_id):
        super().__init__(ip, user)
        self.group_id = group_id
        self.logger = logging.getLogger(__name__ + ".Group")
        self.create_uri = self.base_uri + "/groups"
        self.uri = self.create_uri + "/" + str(self.group_id)
        self.state_uri = self.uri + "/action"

    def remove(self, group_id):
        response = self._req(self.uri, None, "DELETE")
        try:
            message = response[0]['success']
        except KeyError as ke:
            self.logger.error(ke)
        except TypeError as te:
            self.logger.error(te)
            self.logger.error("Received empty response from server")
        else:
            self.logger.info("Group id {} deleted".format(group_id))
       

class Scene(HueObject):
    def __init__(self, ip, user):
        super().__init__(ip, user)
        self.logger = logging.getLogger(__name__ + ".Scene")
        self.create_uri = self.base_uri + "/scenes"
        self.all = self._req(self.create_uri)
            
class Bridge(HueObject):
    def __init__(self, ip, user):
        super().__init__(ip, user)
        self.logger = logging.getLogger(__name__ + ".Bridge")
        try:
            lights_dict = self._req(self.base_uri)
        except KeyError as ke:
            self.logger.error(ke)
            lights_dict = self._req(self.base_uri)
        self.logger.debug(lights_dict)
        self.name = lights_dict['config']['name']
        self.lights = []
        self.logger.debug(self.__dict__)
        for key, value in lights_dict['lights'].items():
            self.logger.debug("Key: {} Value: {}".format(key, value['state']))
            state = json.dumps(value['state'])
            name = value['name']
            model = value['modelid']
            light = Light(ip, user, int(key), name, model, state)
            self.logger.debug("Created this light: {}".format(light))
            self.__dict__[key] = light
            self.lights.append(light)
        self.logger.debug("all lights in bridge: {}".format(self.__dict__))

    def __len__(self):
        return len(self.lights)

    def __getitem__(self, key):
        if isinstance(key, str):
            self.logger.debug("returning by key: {}".format(key))
            for value in self.__dict__.values():
                if isinstance(value, Light):
                    self.logger.debug(value)
                    name = str(value.name)
                    if name.lower() == key.lower():
                        return value
                else:
                    self.logger.debug("{} != {}".format(value, key))
            return "Can't find light by id or name of {}".format(key)
        else:
            self.logger.debug('returning by light id')
            return self._get_light_by_id(key)

    def __setitem__(self, key, value):
        self.logger.debug("calling setitem with {}:{}".format(key, value))
        self.logger.debug("setting item with {}".format(type(value)))
        if (isinstance(key, str) or isinstance(key, int)) and isinstance(value,
                                                                        int):
            self.logger.debug('key is string and value is int!')
            self.lights[key] = value
        elif (isinstance(key, str) or isinstance(key, int) and
              isinstance(value, dict)):
            if key.lower != "state":
                raise ValueError("Can't set any attribute but state with a dictionary")
            self.logger.debug("what? it should go off here!")
            self.logger.debug(value)
            self.logger.debug(key)
            self.lights[key] = value
        else:
            self._get_light_by_id(key)

    def _get_light_by_id(self, lid):
        light_id = str(lid)
        self.logger.debug("trying to match against %s" % light_id)
        return self.__dict__.get(light_id)


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('--bridge', '-b', metavar="BRIDGEIPADDRESS")
    arg_parser.add_argument('--user', '-u', metavar="USERNAME")
    args = arg_parser.parse_args()
    bridge_ip = args.bridge
    user = args.user
    logger.setLevel(logging.DEBUG)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG)
    fmt = '%(levelname)s %(name)s - %(asctime)s - %(lineno)d - %(message)s'
    formatter = logging.Formatter(fmt)
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    bridge_ip = '192.168.1.116'
    user = '23c05db12a8212d7c359e528b19f0b'
#     b = Bridge(bridge_ip, user)
    g = Group(bridge_ip, user, 0)
    g.on = True   
