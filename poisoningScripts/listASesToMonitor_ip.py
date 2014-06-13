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
NUM_IPS = 10

AS2IP = defaultdict(set)
db_file = sys.argv[1]
asip_file = sys.argv[2]

asip_file_f = open(asip_file,'r+')
for line in asip_file_f:
    fields = line.split("|")
    asn = fields[0]
    ip = fields[1].rstrip()
    AS2IP[asn].add(ip)

asip_file_f.close()
asip_file_f = open(asip_file,'w')

conn = sqlite3.connect(db_file)
c = conn.cursor()
d = conn.cursor()

c.execute("select prefix from ASGraph group by prefix")
for row in c:
     PREFIXES.append(row[0])    

as2ip = defaultdict(set)

for pfx in PREFIXES:
    c.execute("select observedPath,vpoint,ipPath,feed from ASGraph where prefix=?",(pfx,))
    d.execute("select observedPath,vpoint,ipPath from TRGraph where prefix=?",(pfx,))

    paths = []
    data = c.fetchall()
    for p in data:
        paths.append(p)
    data = d.fetchall()
    for p in data:
        paths.append(p)

    for p in paths:
        path = p[0].split()
        vp = p[1]
        ipPath = p[2]
        if len(p)==4:
            feed = p[3]
        else:
            feed = 'ftr'

        if feed=='rv':
            vp = vp.split(',')
            asn = vp[0][1:]
            ip = vp[1][2:len(vp[1])-2]
            as2ip[asn].add(ip)
        else:
            as2ip_dict = getAS2IpDict(p[0],ipPath)
            for asn in as2ip_dict:
                for ip in as2ip_dict[asn]:
                    as2ip[asn].add(ip)

for asn in as2ip:
    if asn in AS2IP:
        if len(AS2IP[asn])>=NUM_IPS:
            continue
        else:
            ips_req = NUM_IPS-len(AS2IP[asn])
            present = True
    else:
        present = False
    ips = as2ip[asn]
    if len(ips) <= NUM_IPS:
        ip_list = list(ips)
    else:
        ip_list = list(random.sample(ips,NUM_IPS))
    if (present):
        if ips_req >= len(ip_list):
            for ip in ip_list:
                AS2IP[asn].add(ip)
        else:
            for i in range(0,ips_req):
                AS2IP[asn].add(ip_list[i])
    else:
        for ip in ip_list:
            AS2IP[asn].add(ip)

ip_file_f = open('IPs.txt','w')
for asn in AS2IP:
    for ip in AS2IP[asn]:
        asip_file_f.write(str(asn)+"|"+str(ip)+"\n")
        ip_file_f.write(str(ip)+"\n")
asip_file_f.flush()
asip_file_f.close()
ip_file_f.flush()
ip_file_f.close()

        
        
    
                    
            

        
