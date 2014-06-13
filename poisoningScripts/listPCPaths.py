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
import sqlite3
from collections import defaultdict
import operator
import random


def getAS2IpDict(path,ipPath):

    as2ip = defaultdict(set)
    
    path = path.split()
    ipPath = ipPath.split()

    prev_asn = '0'
    ips = set()
    for i in range(0,len(path)):
        asn = path[i]
        if asn=='0':
            continue
        if prev_asn=='0':
            ips = set()
        if not asn==prev_asn and not prev_asn=='0':
            as2ip[prev_asn] = ips
            ips = set()
        ips.add(ipPath[i])
        prev_asn = asn

    as2ip[prev_asn] = ips
    return as2ip

    
PREFIX_RANGE = [241,243,245,247,249]
#pfx_ip_list = ['130.127.3.0/24','143.215.193.0/24','204.153.48.0/24','128.208.4.0/24','140.189.1.0/24']
pfx_ip_list = ['130.127.3.33','143.215.193.17','204.153.48.42','128.208.4.47','140.189.1.79']
MUX_NAMES = ['CLEMSON', 'GATECH', 'PRINCE', 'UW','WISC']
conn = sqlite3.connect('../data/poison_data/bfs_revised_tr.db2012-08-14 23:41:24.443064')
c = conn.cursor()

c.execute("select max(poison_round) from ASGraph")
rnd = c.fetchone()[0]

as2ip = defaultdict(set)
for r in range(0,rnd):
    for num in PREFIX_RANGE:
        pfx = '184.164.' + str(num) + '.0/24'
        c.execute("select observedPath,feed,vpoint,ipPath from ASGraph where prefix=? and poison_round=?", (pfx,r))
        for row in c:
            path = row[0]
            feed = row[1]
            vp = row[2]
            ipPath = row[3]
            if feed=='rv':
                vp = vp.split(',')
                asn = vp[0][1:]
                ip = vp[1][2:len(vp[1])-2]
                as2ip[asn].add(ip)
            else:
                as2ip_dict = getAS2IpDict(path,ipPath)
                for asn in as2ip_dict:
                    for ip in as2ip_dict[asn]:
                        as2ip[asn].add(ip)

for asn in as2ip:
    ips = as2ip[asn]
    if len(ips) < 4:
        ip_list = ips
    else:
        ip_list = random.sample(ips,3)

    for ip in ip_list:

        '''
        for num in PREFIX_RANGE:
            pfx_ip = '184.164.' + str(num) + '.1'
            print str(ip) + " " + str(pfx_ip)
        '''    
        
        
         
        for pfx_ip in pfx_ip_list:
            print str(ip) + " " + str(pfx_ip)
        
        
    
                    
            

        
