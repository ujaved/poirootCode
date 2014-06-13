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
from helper import create_parser, mkdir_p, Prefix, ASN, VP, getFilteredPath, SENTINEL, TEST, muxASToName
import sqlite3
from operator import itemgetter
from collections import defaultdict

PREFIX_RANGE_SENT = [252,253]
PREFIX_RANGE = [240,242,244,246,248]
MUX_NAMES = ['CLEMSON', 'GATECH', 'PRINCE', 'UW','WISC']
RIOT_ASN = 47065
POISON_INTERVAL = 2100
START_TIME = int(time.time())


def create_db():

    global conn
    db_file = opts.database + str(datetime.now())
    conn = sqlite3.connect(db_file)
    c = conn.cursor()

    c.execute("create table if not exists ASGraph (prefix text, unix_time int, \
               poison_round int, status int, mux_seen text, poisonedAS int, feed text, observedPath text, ipPath text, vpoint text, thisVPoisoned int)")
    c.execute("create index idx_pfx on ASGraph(prefix)")
    c.execute("create index idx_asn on ASGraph(poisonedAS)")
    c.execute("create index idx_pfx_path on ASGraph(prefix,observedPath)")
    c.execute("create index idx_prepend on ASGraph(poison_round)")
    c.execute("create index idx_vpoint on ASGraph(vpoint)")

    return c


def populateDB(c, num, poison_round, status, vpPoisoned):

    #vpPoisoned is a string
    pfx = '184.164.' + str(num) + '.0/24'
    print "---------------------------------"
    print "prefix: " + str(pfx)
    print "poison_round: " + str(poison_round)
    print "status: " + str(status)
    if status==TEST:
        print "vpPoisoned: " + str(vpPoisoned) + " " + str(pfx2VPtoPoison[num])
    VPseen = num2VPseen[num]
    curVP = dict()
    tstamp = int(time.time())

    for feed in feeds:
        locs = pfxToLoc[feed][pfx]
        for rv in locs:
            update = api.get_path(feed, pfx, rv, 'last_update')
            if feed=='rv':
                if update.time < START_TIME:
                    continue
                vp = str(rv).split(',')
                if len(vp)<2:
                    continue
            if feed=='ftr':
                if update.time < tstamp-(30*60):
                    continue
                if rv in VPseen:
                    prev_upd = VPseen[rv]
                    if update.time<=prev_upd.time:
                        continue

            curVP[rv] = update
            unix_time = update.time
            
            if poison_round==0 and ((not update.path) is False) and status==TEST:
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
                print vPoint
                
                
            if not update.path:
                update.path = [0]
            if not update.hops:
                update.hops = [0]
                
            mux = ''
            for m in muxASToName:
                if int(m) in update.path:
                    mux = muxASToName[m]
                    break

            if len(mux)==0:
                continue
            
            path_str = ""
            for n in update.path:
                path_str += (str(n) + " ")
            hops_str = ""
            for n in update.hops:
                hops_str += (str(n) + " ")

            if status==SENTINEL:
                c.execute('insert into ASGraph values (?,?,?,?,?,?,?,?,?,?,?)', \
                              (pfx, unix_time, poison_round, status, str(mux), -1, \
                                   feed, path_str, hops_str, str(rv),0))              
            else:
                thisVPoisoned = 0
                if str(rv)==vpPoisoned:
                              thisVPoisoned = 1
                c.execute('insert into ASGraph values (?,?,?,?,?,?,?,?,?,?,?)', \
                              (pfx, unix_time,poison_round,status, str(mux), \
                                   num2PoisonAS[num],feed,path_str,hops_str,str(rv),thisVPoisoned))

                          
    VPseen.clear()
    for vp in curVP:
               VPseen[vp] = curVP[vp]
    sys.stdout.flush()


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
                          if  opts.database is None:
                              parser.parse_args(['-h'])

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

                          sys.stdout = open(opts.output, 'w')
                          sys.stderr = sys.stdout

                          global conn
                          c = create_db()
                          
                          global feeds
                          feeds = ['rv', 'ftr']
                          
                          num2pfx = dict()
                          
                          global pfxToLoc
                          pfxToLoc = dict()
                          for feed in feeds:
                              pfxToLoc[feed] = api.get_prefix_to_locations(feed)

                          global num2VPseen
                          num2VPseen = dict()
                          for num in PREFIX_RANGE:
                              num2VPseen[num] = dict()
                          for num in PREFIX_RANGE_SENT:
                              num2VPseen[num] = dict()

                          global num2PoisonAS
                          num2PoisonAS = dict()
                          for num in PREFIX_RANGE:
                              num2PoisonAS[num] = RIOT_ASN
                          
                          num2ASPoisonedThisRound = defaultdict(list)

                          global pfx2VP
                          pfx2VP = defaultdict(list)
                          global pfx2VPtoPoison
                          pfx2VPtoPoison = dict()    #the VP index to be poisoned
                          for num in PREFIX_RANGE:
                              pfx2VPtoPoison[num] = -1

                          
                          for num in PREFIX_RANGE:
                              num2pfx[num] = Prefix(num, RIOT_ASN, "announced")
                              pfx = num2pfx[num]
                              pfx.poisonList([RIOT_ASN])
                              pfx.up()
                          
                          for num in PREFIX_RANGE:
                              pfx = num2pfx[num]
                              for mux in MUX_NAMES:
                                 if PREFIX_RANGE.index(num)==MUX_NAMES.index(mux):
                                    pfx.update_route_map1(mux, True)
                                 else:
                                    pfx.update_route_map1(mux,False)
                              pfx.up()
                          
                          for num in PREFIX_RANGE_SENT:
                              num2pfx[num] = Prefix(num, RIOT_ASN, "announced")
                              pfx = num2pfx[num]
                              pfx.poisonList([RIOT_ASN])
                              pfx.up()
                          
                          for num in PREFIX_RANGE_SENT:
                              pfx = num2pfx[num]
                              for mux in MUX_NAMES:
                                 if PREFIX_RANGE_SENT.index(num)==MUX_NAMES.index(mux):
                                     pfx.update_route_map1(mux, True)
                                 else:
                                     pfx.update_route_map1(mux,False)
                              pfx.up()

                          soft_reset(num2pfx)
                          wait_cmd(POISON_INTERVAL)
                          
                          poisonRound = 0
 
                          while True:
                              for num in PREFIX_RANGE_SENT:
                                 populateDB(c,num,poisonRound,SENTINEL,"")
                                 conn.commit()
                          
                              for num  in PREFIX_RANGE:
                                 if poisonRound==0:
                                     vpJustPoisoned = ""
                                 else:
                                     vpJustPoisoned = pfx2VP[num][pfx2VPtoPoison[num]].rv
                                 populateDB(c,num,poisonRound,TEST,vpJustPoisoned)
                                 conn.commit()

                                 if poisonRound==0:
                                     for num in PREFIX_RANGE:
                                         pfx2VPtoPoison[num] = 0
                                         
                                 pfx = num2pfx[num]
                                 print num2ASPoisonedThisRound[num]
                                 vp2poison = pfx2VP[num][pfx2VPtoPoison[num]]
                                 print "vp to poison: " + str(pfx2VPtoPoison[num]) + " " + str(vp2poison)
                                 num2PoisonAS[num] = getNextPoisoning(vp2poison, num2ASPoisonedThisRound[num])
                                 if num2PoisonAS[num] > 0 and num2PoisonAS[num] not in opts.blacklist:
                                     num2ASPoisonedThisRound[num].append(num2PoisonAS[num])
                                 print "as to poison: " + str(num2PoisonAS[num])
                                 print "new poisonidx: " + str(vp2poison.poisonIdx)
                                              
                                 if vp2poison.poisonIdx==vp2poison.startingPoisonIdx:
                                     if (pfx2VPtoPoison[num]+1)==len(pfx2VP[num]):
                                        num2ASPoisonedThisRound[num] = []
                                     pfx2VPtoPoison[num] = (pfx2VPtoPoison[num]+1)%len(pfx2VP[num])
                                 print "new vp to poison: " + str(pfx2VPtoPoison[num])
                                 if num2PoisonAS[num] > 0 and num2PoisonAS[num] not in opts.blacklist:
                                     pfx.poisonList([num2PoisonAS[num]])
                                 else:
                                     pfx.poisonList([RIOT_ASN])

                                 for mux in MUX_NAMES:
                                     if PREFIX_RANGE.index(num)==MUX_NAMES.index(mux):
                                         pfx.update_route_map1(mux, True)
                                     else:
                                         pfx.update_route_map1(mux,False)
                                         
                                 pfx.up()

                              sys.stdout.flush()
                              soft_reset(num2pfx)
                              poisonRound += 1
                              wait_cmd(POISON_INTERVAL)


def soft_reset(num2pfx): # {{{
                          tstamp = int(time.time())
                          logging.info('soft_reset %s', tstamp)
                          cmd = 'vtysh -d bgpd -c "clear ip bgp * soft out"'
                          logging.debug(cmd)
                          #sys.stderr.write(cmd+'\n')
                          os.system(cmd)
                          cmd = 'vtysh -d bgpd -c "show running-config" > log/%s.config' % tstamp
                          logging.debug(cmd)
                          #sys.stderr.write(cmd+'\n')
                          os.system(cmd)
                          opts.last_reset = tstamp
                          for num in PREFIX_RANGE:
                              logging.info('prefix_grep %d 184.164.%d.0/24 %s %s', tstamp, num,
                                           num2pfx[num].status, num2pfx[num].as_path_string)
                          # }}}

def wait_cmd(interval):
                          logging.debug('sleeping for %d seconds', interval)
                          time.sleep(interval)

if __name__ == '__main__':
                          sys.exit(main())

