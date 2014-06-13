#!/usr/bin/python

import Pyro4
import sys
import os
import errno
import random
import gzip
import resource
import logging
import logging.handlers
import time
from datetime import datetime
from optparse import OptionParser
import subprocess, threading
import re
from helper import create_parser, mkdir_p, Prefix, ASN, VP, getFilteredPath, SENTINEL, TEST
import sqlite3
from operator import itemgetter
from collections import defaultdict

PREFIX_RANGE = range(251,252)
PREFIX_RANGE_SENT = range(241,242)
MUX_NAMES = ['UW', 'WISC', 'GATECH', 'PRINCE', 'CLEMSON']
RIOT_ASN = 47065
PREPEND_INTERVAL = 2100
START_TIME = int(time.time())


def getNextPoisoning(vp2poison, PoisonedList):

    candAS = int(vp2poison.path[vp2poison.poisonIdx])
    while candAS in PoisonedList:
        if vp2poison.poisonIdx==0:
            candAS = 0
            break
        vp2poison.setNextPoisonIdx()
        candAS = int(vp2poison.path[vp2poison.poisonIdx])

    vp2poison.setNextPoisonIdx()
    return candAS
    
def main():

    global opts 
    parser = create_parser()
    opts, _args = parser.parse_args()

    resource.setrlimit(resource.RLIMIT_AS, (2147483648L, 2147483648L))
    
    Pyro4.config.HMAC_KEY = 'choffnes-cunha-javed-owning'
    sys.excepthook = Pyro4.util.excepthook
    ns = Pyro4.naming.locateNS('128.208.4.106', 51556)
    uri = ns.lookup('livedb.main')
    global api
    api = Pyro4.Proxy(uri)
                          
    mkdir_p(opts.logdir)
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(message)s')
    loghandler = logging.handlers.RotatingFileHandler(opts.logfile,
                                                      maxBytes=128*1024*1024, backupCount=5)
    loghandler.setFormatter(formatter)
    logger.addHandler(loghandler)
                          
    global feeds
    feeds = ['rv', 'ftr']
                          
    global pfxToLoc
    pfxToLoc = dict()
    for feed in feeds:
        pfxToLoc[feed] = api.get_prefix_to_locations(feed)
        
        
    global num2PoisonAS
    num2PoisonAS = dict()
    for num in PREFIX_RANGE:
        num2PoisonAS[num] = 47065
                          
    num2ASPoisonedThisRound = defaultdict(list)

    global pfx2VP
    pfx2VP = defaultdict(list)
    global pfx2VPtoPoison
    pfx2VPtoPoison = dict()    #the VP index to be poisoned
    for num in PREFIX_RANGE:
        pfx2VPtoPoison[num] = 0
        
    tstamp = int(time.time())
    for num in PREFIX_RANGE:
        pfx = '184.164.' + str(num) + '.0/24'
        for feed in feeds:
            locs = pfxToLoc[feed][pfx]
            for rv in locs:
                update = api.get_path(feed, pfx, rv, 'last_update')
                if not update.path:
                    continue
                if feed=='rv':
                    print update
                    if update.time < (START_TIME-10*3600):
                        continue
                    vp = str(rv).split(',')
                    if len(vp)<2:
                        continue
                if feed=='ftr':
                    if update.time < tstamp-(30*60):
                        continue
            
                path = ""
                for asn in update.path:
                    path += (str(asn) + " ")
                path = path.split()
                tup = getFilteredPath(path,feed)
                if tup is None:
                    continue
                filpath = tup[0]
                mux = tup[1]
                
                vPoint = VP(pfx,filpath,feed,mux,str(rv))
                pfx2VP[num].append(vPoint)

    '''
    for num in PREFIX_RANGE:
        for vp in pfx2VP[num]:
            print vp

    for i in range(0,200):
        print "-------------------------------"
        for num in PREFIX_RANGE:
            print num2ASPoisonedThisRound[num]
            vp2poison = pfx2VP[num][pfx2VPtoPoison[num]]
            print "vp to poison: " + str(pfx2VPtoPoison[num]) + " " + str(vp2poison)
            num2PoisonAS[num] = getNextPoisoning(vp2poison, num2ASPoisonedThisRound[num])
            if num2PoisonAS[num] > 0:
                num2ASPoisonedThisRound[num].append(num2PoisonAS[num])
            print "as to poison: " + str(num2PoisonAS[num])
            print "new poisonidx: " + str(vp2poison.poisonIdx)
            if vp2poison.poisonIdx==vp2poison.startingPoisonIdx:
                if (pfx2VPtoPoison[num]+1)==len(pfx2VP[num]):
                    num2ASPoisonedThisRound[num] = []
                pfx2VPtoPoison[num] = (pfx2VPtoPoison[num]+1)%len(pfx2VP[num])
            print "new vp to poison: " + str(pfx2VPtoPoison[num])
     '''


if __name__ == '__main__':
    sys.exit(main())
