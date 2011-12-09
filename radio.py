#!/usr/bin/env python

import warnings
warnings.simplefilter("ignore") # Be quiet

from twisted.internet import reactor
from twisted.internet import stdio
from twisted.internet import defer
from twisted.protocols import basic

from lxml import etree

import time, json, shutil, os

from coherence.base import Coherence
from coherence.upnp.devices.control_point import ControlPoint

logfile = None
config = {'logmode':'none', 'logfile':logfile}
coherence = Coherence(config)

controlpoint = ControlPoint(coherence,auto_client=[])

BOOKMARKPATH = os.path.expanduser('~/.grace-bookmarks')

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
    NavigatorId = None
    handlers = {}
    menu = []
    lastSelection = None
    currentStation = None

    def __init__(self, *args, **kwargs):
        self.handlers = {
          'GetMenu': self.handleGetMenu,
          'SelectItemAndGetResponse': self.handleSelectItemAndGetResponse,
          'GetMenuAtOffset': self.handleGetMenuAtOffset,
          'GetVolume': self.handleGetVolume,
          'SetVolume': self.handleSetVolume,
          'RegisterNavigator': self.handleRegisterNavigator,
          'GetStationId': self.handleGetStationId,
          'GoBackAndGetResponse': self.handleGoBackAndGetResponse,
          'GetPlaybackDetails': self.handleGetPlaybackDetails,
          'SetStationId': self.handleSetStationId,
        }

    def welcome(self):
        self.sendLine('Press "h" for help')

    def waitForDevice(self, numTries=0):
        if devices:
            self.selectDevice(0)
            self.waitForNavigator()
        else:
            self.sendLine('Probing for device...')
            d = defer.Deferred()
            d.addCallback(self.waitForDevice)
            reactor.callLater(2, d.callback, numTries + 1)

    def waitForNavigator(self, numTries=0):
        if self.NavigatorId:
            self.sendLine('Connected!')
            self.welcome()
        else:
            if numTries > 1:
                self.sendLine('Connecting...')
            d = defer.Deferred()
            d.addCallback(self.waitForNavigator)
            reactor.callLater(.5, d.callback, numTries + 1)

    def connectionMade(self):
        self.sendLine('Welcome to Grace Internet Radio Controller')

    def sendLine(self, *args, **kwargs):
        self.queue = []
        self._sendLine(*args, **kwargs)

    def _sendLine(self, *args, **kwargs):
        basic.LineReceiver.sendLine(self, *args, **kwargs)

    def bufferLine(self, s):
        try:
#            _s = str(unicode(s, errors='replace').replace(u'FFFD', '?'))
            _s = s.encode(errors='replace')
            self.queue.append(str(_s))
        except:
            print "ERROR: ", (s,)

    def sendBuffered(self, num=20):
        num = min(len(self.queue), num)
        for i in xrange(num):
            s = self.queue[0]
            del self.queue[0]
            self._sendLine(s)

    def logActions(self, actions):
        keys = actions.keys()
        keys.sort()
        s = ''
        for key in keys:
          action = actions[key]
          s += action.name + '\n'
          for argument in action.get_in_arguments():
              s += '  ' + str(argument) + '\n'
        open('/tmp/woo.txt', 'w').write(s)

    def selectDevice(self, id):
        if self.device and self.NavigatorId:
            action = self.action('ReleaseNavigator')
            d = action.call(NavigatorId=self.NavigatorId)
            # TODO This should probably delay all other actions
        self.device = devices[id]
        self.NavigatorId = None
        self.performAction('RegisterNavigator')
        self.sendLine('Using device: ' + str(self.device['name']))

    def action(self, key):
        actions = self.device['control'].get_actions()
#        self.logActions(actions)
        return actions[key]

    def performAction(self, name, *args, **kwargs):
        action = self.action(name)
        def succ(response, *args, **kwargs):
            if name in self.handlers:
                self.handlers[name](response)
            else:
                self.sendLine("Unhandled success: %s %s %s %s" % (str(name), str(response), str(args), str(kwargs)))
        def fail(failure, *args, **kwargs):
            self.sendLine("fail: %s %s %s %s" % (str(name), str(args), str(kwargs), str(failure.getErrorMessage())))

        d = action.call(*args, **kwargs)
        d.addCallback(succ)
        d.addErrback(fail)

    def renderBookmarkMenu(self):
        self.sendLine('Bookmarks:')
        try:
            bookmarks = json.load(open(BOOKMARKPATH))
            for id,bookmark in zip(xrange(len(bookmarks)),bookmarks):
                self.bufferLine('%d: %s' % (id, bookmark['name']))
            self.sendBuffered()
        except:
            self.sendLine('Error loading bookmarks (Do you have any bookmarks?)')

    def addBookmark(self, bname):
        self.sendLine('Add bookmark: ' + bname)
        try:
            bookmarks = json.load(open(BOOKMARKPATH))
        except IOError,e:
            if e.errno == 2:
                bookmarks = []
            else:
                self.sendLine('Unable to parse bookmarks file. %s' % BOOKMARKPATH)
                return
        if not self.currentStation:
            self.sendLine('Current station unavailable')
            self.performAction('GetPlaybackDetails',
                NavigatorId=self.NavigatorId,
            )
            return

        bookmarks.append({
            'name': bname,
            'realname': self.currentStation['name'],
            'id': self.currentStation['id'],
        })
        try:
            shutil.move(BOOKMARKPATH, BOOKMARKPATH + '.bak')
        except IOError,e:
            if e.errno == 2:
                pass
            else:
                self.sendLine('Error: ' + str(e))
                return
        json.dump(bookmarks, open(BOOKMARKPATH, 'w'))
        self.sendLine('Bookmark added')

    def loadBookmark(self, bkey):
        try:
            bookmarks = json.load(open(BOOKMARKPATH))
        except IOError,e:
            if e.errno == 2:
                self.sendLine('No bookmarks found in %s.' % BOOKMARKPATH)
                return
            else:
                self.sendLine('Unable to parse bookmarks file. %s' % BOOKMARKPATH)
                return

        id = None
        name = None

        for id,bookmark in zip(xrange(len(bookmarks)),bookmarks):
            if bkey in (str(id),
                        bookmark['name'],
                        bookmark['realname']):
                self.performAction('SetStationId',
                    NewStationIdValue=str(bookmark['id']),
                )
                self.sendLine(str("Loading bookmark %d, %s (%s)" % (id, bookmark['name'], bookmark['realname'])))
                break

    def renderMenu(self, elements):
        self.menu = []
        self.lastSelection = None

        for element in elements:
            elid = int(element.get('id'))
            name = element.text
            type = element.get('type')
            self.menu.append({
                'id': elid,
                'name': name,
                'type': type,
            })
            self.bufferLine("%s: %s" % (elid+1, element.text))
        self.sendBuffered()

    def parseMenuXML(self, xml):
        dom = etree.fromstring(xml)
        (items,) = dom.xpath('./menu/items')
        numitems = items.get('count')
        elements = items.xpath('./item')
        if int(numitems) == len(elements):
            self.sendLine("%s menu items" % numitems)
            self.renderMenu(elements)
        else:
            self.sendLine("Loading menu...")
            self.performAction("GetMenuAtOffset",
                NavigatorId=self.NavigatorId,
                Count=int(numitems),
                Offset=0,
            )
    def parseStateXML(self, xml):
        dom = etree.fromstring(xml)
        state = dom.xpath('//state')[0].text
        title = dom.xpath('.//title')[0].text
        id = dom.xpath('//station')[0].get('id')

        self.currentStation = {'type': 'station', 'id': id, 'name': title}
        self.currentState = state

    def showCurrentStation(self):
        self.sendLine('Status: ' + self.currentState)
        self.sendLine('Station: ' + self.currentStation['name'])

#### HANDLER METHODS

    def handleRegisterNavigator(self, response):
        self.NavigatorId = response['RetNavigatorId']

    def handleGetMenu(self, response):
        xml = response["RetMenuXML"]
        self.parseMenuXML(xml)

    def handleGetMenuAtOffset(self, response):
        xml = response["RetMenuXML"]
        self.parseMenuXML(xml)

    def handleSelectItemAndGetResponse(self, response):
        def menu(arg):
            self.performAction("GetMenu",
                        NavigatorId=self.NavigatorId,
            )

        item = self.menu[self.lastSelection]
        if item.get('type') == 'station':
            self.sendLine('Tuning to station %s' % item['name'])
            self.currentStation = item
        else:
            xml = response['RetNavigationResponse']
            dom = etree.fromstring(xml)
            if dom.xpath('//deferred'):
                d = defer.Deferred()
                d.addCallback(menu)
                reactor.callLater(2, d.callback, None) # Wait for menu to load
                self.sendLine("Loading...")
            elif dom.xpath('//menu'):
                self.parseMenuXML(xml)

    def handleGetVolume(self, response):
        self.sendLine('volume: ' + str(response['RetVolumeValue']))

    def handleSetVolume(self, response):
        self.sendLine('volume set')

    def handleGetStationId(self, result):
        self.sendLine('Current Station ID: ' + str(result['RetStationIdValue']))

    def handleSetStationId(self, result):
        self.sendLine('Changing to station ID: ' + str(stationstr))

    def handleGoBackAndGetResponse(self, result):
        xml = result['RetNavigationResponse']
        self.parseMenuXML(xml)

    def handleGetPlaybackDetails(self, result):
        stateXML = result['RetPlaybackXML']
        self.parseStateXML(stateXML)

    def handleSetStationId(self, result):
        self.sendLine('Station change successful')

    def lineReceived(self, line):
        if (not self.device or
            not self.NavigatorId):
            self.sendLine('Connecting, be patient')
            return

        if not self.currentStation:
            self.performAction('GetPlaybackDetails',
                NavigatorId=self.NavigatorId,
            )

#### MENU NAVIGATOR
        if line.startswith('m'):
            self.performAction("GetMenu",
                NavigatorId=self.NavigatorId,
            )
        elif line.startswith('s'):
            try:
                sid = int(line[1:])-1
                self.lastSelection = sid
                self.performAction("SelectItemAndGetResponse",
                    NavigatorId=self.NavigatorId,
                    NewMenuItemId=sid,
                )
            except:
                self.sendLine('Invalid command: ' + line)
        elif line.startswith('r'):
            self.performAction("GoBackAndGetResponse",
                NavigatorId=self.NavigatorId,
            )
#### PAGER
        elif line == '' and self.queue:
            self.sendBuffered()
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
                    self.selectDevice(dnum)
                except ValueError:
                    self.sendLine('Invalid device selection: %s' % dstr)

#### GET/SET VOLUME
        elif line.startswith('v'):
            vol = line[1:]
            if not vol:
                self.performAction('GetVolume')
            else:
                try:
                    ivol = int(vol)
                    self.performAction('SetVolume',
                        NewVolumeValue=ivol,
                    )
                except ValueError:
                    self.sendLine('Invalid volume: %s' % vol)

#### GET/SET STATION ID
        elif line.startswith('b'):
            bline = line[1:].strip()
            if bline.startswith('a'):
                bname = bline[1:]
                self.addBookmark(bname)
            elif bline.startswith('l'):
                bkey = bline[1:]
                self.loadBookmark(bkey)
            else:
                self.renderBookmarkMenu()

#            stationstr = line[1:]
#            if not stationstr:
#                self.performAction('GetStationId')
#            else:
#                self.performAction('SetStationId',
#                    NewStationIdValue=str(stationstr),
#                )

        elif line.startswith('c') or line == '':
            self.performAction('GetPlaybackDetails',
                NavigatorId=self.NavigatorId,
            )
            reactor.callLater(1, self.showCurrentStation)
#### MANHOLE
        elif line.startswith(' '):
            try:
                self.sendLine(str(eval(line.strip())))
            except Exception,e:
                self.sendLine('Syntax error: ' + str(e))

def main():
    o = CoherenceMenu()
    stdio.StandardIO(o)
    o.waitForDevice()
    reactor.run()

if __name__ == '__main__':
    main()
