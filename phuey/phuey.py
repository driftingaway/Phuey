#!/usr/bin/env python3
from sys import stdout
import argparse
import hashlib
import http.client
import json
import logging
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)


class HueObject:
    def __init__(self, ip, username):
        self.ip = ip
        self.base_uri = "http://" + ip + "/api/" + username
        self.user = username
        self.logger = logging.getLogger(__name__ + ".HueObject")

    def _req(self, url, payload=None, meth="GET"):
        self.logger.debug("{} on {}".format(meth, url, payload))
        body = json.dumps(payload).encode()
        if payload:
            self.logger.debug("Body: {}".format(payload))
            request = urllib.request.Request(url, body, method=meth)
        else:

            request = urllib.request.Request(url)
        try:
            response = urllib.request.urlopen(request)
        except urllib.error.URLError as ue:
            self.logger.error("Couldn't connect to bridge reason: {}".format(
                                                                    ue.reason))
            return None
        except ConnectionRefusedError:
            self.logger.error("Connection refused from bridge!")
            return None
        else:
            self.logger.debug("Bridge header response: %s" %
                              response.getheaders())
            resp_payload = response.read().decode("utf-8")
            self.logger.debug("Bridge response: %s" % resp_payload)
            payload = json.loads(resp_payload)
            self.logger.debug(payload)
            return payload

    def __str__(self):
        if isinstance(self, Light):
            return "Light name: {} id: {} currently on: {}".format(
                               str(self.name), self.light_id, self.on)
        elif isinstance(self, Bridge):
            self.logger.debug(type(self))
            return "name: {} with {} light(s)".format(self.name,
                                                      len(self.lights))
        else:
            return "Group: {}".format(self.name)


class HueDescriptor:
    def __init__(self, name, initval):
        self.name = initval
        self.__name__ = name
        self.logger = logging.getLogger(__name__ + ".HueDescriptor")

    def __get__(self, inst, cls):
        self.logger.debug("calling get on {}".format(type(inst)))
        self.logger.debug("{} keys".format(inst.__dict__.keys()))
        return inst.__dict__[self.__name__]

    def __set__(self, inst, val):
        self.logger.debug("calling set! {} {} {} ".format(self.__name__,
                                                          self.name,
                                                          val))
        if self.__name__ is 'state':
            self.logger.debug("__name__ is state!")
            input("what now?")
            for key, value in val.items():
                logger.debug('{} {}'.format(inst.__dict__.keys(), key))
                inst.__dict__[key] = value
            inst._req(inst.state_uri, val, "PUT")
        if self.__name__ is not 'light_id':
            self.logger.debug("self.__name__ is not light_id")
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

    def __init__(self, ip, username, light_id, name, start_state=None):
        super().__init__(ip, username)
        self.light_id = light_id
        self.name = HueDescriptor('name', name)
        self.logger = logging.getLogger(__name__ + ".Light")
        self.name_uri = self.base_uri + "/lights/" + str(self.light_id)
        self.state_uri = self.name_uri + "/state"
        if start_state:
            self.logger.debug(type(start_state))
            self.logger.debug(start_state)
            for key, value in json.loads(start_state).items():
                self.logger.debug("Setting {} with {}".format(key, value))
                self.__dict__[key] = value


class Bridge(HueObject):
    def __init__(self, ip, user):
        super().__init__(ip, user)
        self.logger = logging.getLogger(__name__ + ".Bridge")
        self.uri = self.base_uri
        lights_dict = self._req(self.uri)
        self.name = lights_dict['config']['name']
        self.lights = {}
        self.logger.debug(self.__dict__)
        for key, value in lights_dict['lights'].items():
            self.logger.debug("Key: {} Value: {}".format(key, value['state']))
            if str(key).isdigit():
                state = json.dumps(value['state'])
                name = value['name']
                light = Light(ip, user, key, name, state)
                self.logger.debug("Created this light: {}".format(light))
                self.__dict__[key] = light
                self.lights[int(key)] = light
            else:
                self.logger.debug("Whawt?!")
                self.logger.debug(str(key).isdigit())
        self.logger.debug("all lights in bridge: {}".format(self.__dict__))

    def __len__(self):
        return len(self.lights)

    def __getitem__(self, key):
        if isinstance(key, str):
            self.logger.debug("returning by key: {}".format(key))
            for l in self.lights.values():
                if str(l.name).lower() == key.lower():
                    return l
                else:
                    self.logger.debug("{} != {}".format(str(l.name), key))
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
    ch = logging.StreamHandler(stdout)
    ch.setLevel(logging.DEBUG)
    fmt = '%(name)s - %(asctime)s - %(module)s-%(funcName)s/%(lineno)d - %(message)s'
    formatter = logging.Formatter(fmt)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    b = Bridge(bridge_ip, user)