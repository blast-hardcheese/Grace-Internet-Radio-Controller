#!/usr/bin/env python

import warnings
warnings.simplefilter("ignore") # Be quiet

from twisted.internet import reactor
from twisted.internet import stdio
from twisted.protocols import basic

import time

from coherence.base import Coherence
from coherence.upnp.devices.control_point import ControlPoint

logfile = None
config = {'logmode':'none', 'logfile':logfile}
coherence = Coherence(config)

controlpoint = ControlPoint(coherence,auto_client=[])

devices = []
unknown_devices = []

def add_device(device=None, *args, **kwargs):
    control = None
    for service in device.services:
        _,_,_,service_class,version = service.service_type.split(':')
        if service_class == 'RecivaRadio':
            control = service
    d = {
          'name': device.get_friendly_name(),
          'device':device,
          'control':control,
        }
    if control:
        devices.append(d)
    else:
        unknown_devices.append(d)

def remove_device(*args, **kwargs):
    ''' Remove device '''
#    print "remove_device:", args, kwargs

def create_device(infos=None, device_type=None, *args, **kwargs):
    ''' Create device '''
#    print "create_device:", infos, device_type, args, kwargs

coherence.connect( create_device, 'Coherence.UPnP.SSDP.new_device')
coherence.connect( add_device, 'Coherence.UPnP.RootDevice.detection_completed')
coherence.connect( remove_device, 'Coherence.UPnP.SSDP.removed_device')

class CoherenceMenu(basic.LineReceiver):
    from os import linesep as delimiter
    queue = []
    device = None

    def connectionMade(self):
        self.sendLine('Welcome to Grace Internet Radio Controller')


    def action(self, key):
        actions = self.device['control'].get_actions()
#        keys = actions.keys()
#        keys.sort()
#        s = ''
#        for key in keys:
#          action = actions[key]
#          s += action.name + '\n'
#          for argument in action.get_in_arguments():
#              s += '  ' + str(argument) + '\n'
#        open('/tmp/woo.txt', 'w').write(s)
        return actions[key]

    def lineReceived(self, line):
        if not self.device:
            if devices:
                self.device = devices[0]
            else:
                self.sendLine('Devices not found yet')
        if line.startswith('exec'):
            cmd = line[5:]
            try:
                self.sendLine(str(eval(cmd)))
            except:
                self.sendLine('Syntax error')
#### PAGER
        elif line == '' and self.queue:
            try:
                for i in xrange(25):
                    line = self.queue.pop()
                    self.sendLine(line)
            except IndexError:
                pass
        elif line == 'q':
            self.queue = []

#### LIST DEVICES
## This gives a one-indexed list of all known devices
## The user can also choose which device to talk to, via
## dN where N is a number (eg: d3 for the third device)
        elif line.startswith('d'):
            dstr = line[1:]
            if not dstr:
                for i,d in zip(range(1, len(devices)+1),devices):
                    self.sendLine('%d: %s' % (i, str(d['name'])))
            else:
                try:
                    dnum = int(dstr) - 1
                    self.device = devices[dnum]
                    self.sendLine('Selected device %s: %s' % (dstr, str(self.device['name'])))
                except ValueError:
                    self.sendLine('Invalid device selection: %s' % dstr)

#### GET/SET VOLUME
        elif line.startswith('v'):
            vol = line[1:]
            if not vol:
                action = self.action('GetVolume')
                def getVol(result=None):
                    self.sendLine('volume: ' + str(result['RetVolumeValue']))
                def fail(*args, **kwargs):
                    self.sendLine("get volume failed: "+ str(args) + ' ' + str(kwargs))
                d = action.call()
                d.addCallback(getVol)
                d.addErrback(fail)
            else:
                try:
                    ivol = int(vol)
                    action = self.action('SetVolume')
                    def setVol(result=None):
                        self.sendLine('volume set: ' + str(ivol))
                    def fail(*args, **kwargs):
                        self.sendLine("set volume failed: " + str(args) + ' ' + str(kwargs))
                    d = action.call(NewVolumeValue=ivol)
                    d.addCallback(setVol)
                    d.addErrback(fail)
                except ValueError:
                    self.sendLine('Invalid volume: %s' % vol)
#### GET/SET STATION ID
        elif line.startswith('s'):
            stationstr = line[1:]
            if not stationstr:
                action = self.action('GetStationId')
                def getStation(result=None):
                    self.sendLine('Current Station ID: ' + str(result['RetStationIdValue']))
                def fail(*args, **kwargs):
                    self.sendLine("Unable to get station ID: " + str(args) + ' ' + str(kwargs))
                d = action.call()
                d.addCallback(getStation)
                d.addErrback(fail)
            else:
                def setStation(result=None):
                    self.sendLine('Changing to station ID: ' + str(stationstr))
                def fail(*args, **kwargs):
                    self.sendLine('Unable to change to station ID: ' + str(args) + ' ' + str(kwargs))
                action = self.action('SetStationId')
                d = action.call(NewStationIdValue=str(stationstr))
                d.addCallback(setStation)
                d.addErrback(fail)

def main():
    stdio.StandardIO(CoherenceMenu())
    reactor.run()

if __name__ == '__main__':
    main()
