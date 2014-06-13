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

ASes = set()
db_file = sys.argv[1]
as_file = sys.argv[2]

as_file_f = open(as_file,'r+')
for line in as_file_f:
    line = line.split()
    asn = line[0].rstrip()
    ASes.add(asn)

as_file_f.close()
as_file_f = open(as_file,'w')

conn = sqlite3.connect(db_file)
c = conn.cursor()
d = conn.cursor()


c.execute("select prefix from ASGraph group by prefix")
for row in c:
     PREFIXES.append(row[0])    

as2ip = defaultdict(set)

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
        path_orig = p[0]
        path = path_orig.split()
        feed = p[1]
        vp = p[2]
        ipPath = p[3]
        
        tup = getFilteredPath1(path,feed)
        if (tup is None):
            continue

        if feed=='rv':
            vp = vp.split(',')
            asn = vp[0][1:]
            ip = vp[1][2:len(vp[1])-2]
            as2ip[asn].add(ip)
        else:
            as2ip_dict = getAS2IpDict(path_orig,ipPath)
            for asn in as2ip_dict:
                for ip in as2ip_dict[asn]:
                    as2ip[asn].add(ip)

        filpath = tup[0]
        for asn in filpath:
            ASes.add(asn)

for asn in ASes:
    as_file_f.write(str(asn)+"\n")

as_file_f.flush()
as_file_f.close()

for asn in as2ip:
    print asn
    ips = as2ip[asn]
    if len(ips) < 4:
        ip_list = ips
    else:
        ip_list = random.sample(ips,3)

    for ip in ip_list:
        print str(ip)
        
    
                    
            

        
