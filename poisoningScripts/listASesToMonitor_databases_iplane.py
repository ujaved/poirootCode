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
from helper import  getFilteredPath1

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


PREFIXES = []
NUM_IPS = 30

AS2IP = defaultdict(set)
as2ip_iplane = defaultdict(set)
iplane_ip2as_f = open(sys.argv[1],'r')
for line in iplane_ip2as_f:
    fields = line.split()
    ip = fields[0]
    asn = fields[1].rstrip()
    as2ip_iplane[asn].add(ip)

for i in range(2,len(sys.argv)):
    db_file = sys.argv[i]
    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    d = conn.cursor()

    c.execute("select prefix from ASGraph group by prefix")
    for row in c:
        PREFIXES.append(row[0])

    for pfx in PREFIXES:
        c.execute("select observedPath,feed,vpoint,ipPath from ASGraph where prefix=?",(pfx,))
        d.execute("select observedPath,feed,vpoint,ipPath from TRGraph where prefix=?",(pfx,))

        paths = []
        data = c.fetchall()
        for p in data:
            paths.append(p)
        data = d.fetchall()
        for p in data:
            paths.append(p)

        for p in paths:
            path = p[0].split()
            feed = p[1]
            vp = p[2]
            ipPath = p[3]

            if feed=='rv':
                vp = vp.split(',')
                asn = vp[0][1:]
                ip = vp[1][2:len(vp[1])-2]
                AS2IP[asn].add(ip)
            else:
                as2ip_dict = getAS2IpDict(p[0],ipPath)
                for asn in as2ip_dict:
                    for ip in as2ip_dict[asn]:
                        AS2IP[asn].add(ip)

for asn in AS2IP:
    if asn in as2ip_iplane:
        for ip in as2ip_iplane[asn]:
            AS2IP[asn].add(ip)

ip_file_f = open('IPs.txt','w')
as2ip_file_f = open('as2ip.txt','w')
for asn in AS2IP:
    ips = AS2IP[asn]
    if len(ips) <= NUM_IPS:
        ip_list = list(ips)
    else:
        ip_list = list(random.sample(ips,NUM_IPS))

    for ip in ip_list:
        as2ip_file_f.write(str(asn)+"|"+str(ip)+"\n")
        ip_file_f.write(str(ip)+"\n")
as2ip_file_f.flush()
as2ip_file_f.close()
ip_file_f.flush()
ip_file_f.close()

        
        
    
                    
            

        
