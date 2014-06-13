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
from helper import getFilteredPath1, Path_VP

VP2OrigPath = defaultdict()

pfx = '184.164.252.0/24'
conn = sqlite3.connect('../data/poison_data/init_poison.db2012-06-23 00:40:35.238744')
c = conn.cursor()


c.execute("select observedPath,vpoint,feed,ipPath from ASGraph where prefix=? and poison_round=?", (pfx,0))
for row in c:
    path = row[0]
    path = path.split()
    feed = row[2]
    ipPath = row[3]
    tup = getFilteredPath1(path,feed)
    if tup is None:
        continue
    filpath = tup[0]
    vp = row[1]
    VP2OrigPath[vp] = Path_VP(path,filpath,feed,vp,ipPath)

c.execute("select max(poison_round) from ASGraph where prefix=?", (pfx,))
rnd = c.fetchone()[0]
    
for r in range(1,rnd):
    c.execute("select observedPath,feed,thisVPoisoned,vpoint,ipPath from ASGraph where prefix=? and poison_round=?", (pfx,r))
    res = c.fetchall()
    c.execute("select poisonedAS from ASGraph where prefix=? and poison_round=? group by poisonedAS", (pfx,r))
    poisonedAS = str(c.fetchone()[0])
    if poisonedAS=='0':
        continue
    vp2res = dict()
    for row in res:
        vp2res[row[3]] = row
    for v in VP2OrigPath:
        if v not in vp2res and poisonedAS in VP2OrigPath[v].filpath:
            print str(v) + "|" + str(VP2OrigPath[v]) + "|" + "W" + "|" + poisonedAS + \
                "|" + str(VP2OrigPath[v].feed)
            continue
        if v not in vp2res:
            continue
        res_p = vp2res[v] 
        #if poisonedAS in VP2OrigPath[v].filpath:
        path = res_p[0]
        path = path.split()
        feed = res_p[1]
        ipPath = res_p[4]
        tup = getFilteredPath1(path,feed)
        if tup is None:
            continue
        filpath = tup[0]
        p = Path_VP(path,filpath,feed,v,ipPath)
        #print str(v) + "|" + str(VP2OrigPath[v]) + "|" + str(p) + "|" + poisonedAS + \
        #    "|" + str(VP2OrigPath[v].feed) + "|" + str(VP2OrigPath[v].ipPath) + "|" + str(p.ipPath)
        print str(v) + "|" + str(VP2OrigPath[v]) + "|" + str(p) + "|" + poisonedAS + \
            "|" + str(VP2OrigPath[v].feed)
            

        
