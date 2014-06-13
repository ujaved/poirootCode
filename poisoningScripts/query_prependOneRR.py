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
#from helper import create_parser, mkdir_p, Prefix
from helper import ASNQuery
import sqlite3
from collections import defaultdict
import operator

MUX_NAMES = ['UW', 'WISC', 'GATECH', 'PRINCE', 'CLEMSON']
MUX_ASN = ['73','2381','2637','88','2722', '47065']


class Path(object):

    def __init__(self, pfx, mux, prepend, path_control, path_data, mux_list, prepend_status):
        self.pfx = pfx
        self.mux = mux
        self.prepend = prepend
        self.path_data = path_data
        self.path_control = path_control
        self.mux_list = mux_list
        self.prepend_status = prepend_status
        self.hash = hash(str(self))

    def __str__(self):
        
        return str(self.pfx) + "|" + str(self.mux) + "|" + str(self.prepend) + "|" + str(self.path_control) + \
		       "|" + str(self.path_data) + "|" + str(self.mux_list) + "|" + str(self.prepend_status)  

    def __eq__(self,other):
        return self.hash==other.hash

    
def findShortestMux(mux2Path, round,i):

    shortMuxes = []
    minLen = 1000
    for mux in mux2Path:
        pathLen = len(mux2Path[mux].path_control)
        if round > 0:
            mux_idx = MUX_NAMES.index(mux)
            if mux_idx <= i:
                pathLen += round
            else:
                pathLen += (round-1)
        if pathLen <= minLen:
            shortMuxes.append(mux)
            minLen = pathLen

    return shortMuxes
        
conn = sqlite3.connect('../data/prepend_data/RR.py2012-05-01 08:20:04.857817')
c = conn.cursor()

as2mux2Path = defaultdict(lambda: defaultdict(dict))
for num in range(250,255):
    pfx = '184.164.' + str(num) + '.0/24'
    c.execute("select mux_seen,observedPath from ASGraph where prefix=? and prepend_round=? and feed=?", (pfx,0,'rv'))
    for row in c:
        
        mux = row[0]
        if len(mux)==0:
            print row

        unfiltered_path = row[1][1:len(row[1])-1]
        s = unfiltered_path.split(", ")
        for asn in s:
            if asn in MUX_ASN:
                continue
            idx = s.index(asn)
            P = Path(pfx, mux, 0, s[idx:],'',MUX_NAMES,[0,0,0,0,0])
            as2mux2Path[asn][mux] = P

Realas2mux2Path = defaultdict(lambda: defaultdict(dict))


'''
    c.execute("select mux,observedPath,vpoint,prepend_round from ASGraph where prefix=? and feed=? order by vpoint,prepend_round DESC", (pfx,'ftr'))
    for row in c:
        
        mux = row[0]
        unfiltered_path = row[1][1:len(row[1])-1]
        s = unfiltered_path.split(", ")
        if len(mux)==0:
            if '7922' in s:
                mux='PRINCE'
            elif '174' in s:
                mux='GATECH'
            else:
                continue

        prev_asn = '0'
        opath = []
        for asn in s:
            if asn==prev_asn or asn=='0':
                continue
            opath.append(asn)
            prev_asn = asn

        for asn in opath:
            idx = opath.index(asn)
            if asn in as2mux2Path:
                if mux in as2mux2Path[asn]:
                    as2mux2Path[asn][mux].path_data = opath[idx:]
                else:
                    P = Path(pfx, mux, 0,'', opath[idx:])
                    as2mux2Path[asn][mux] = P
            else:
                P = Path(pfx, mux, 0,'', opath[idx:])
                as2mux2Path[asn][mux] = P
'''

'''
for r in range(1,2):
    print "round: " + str(r)
    c.execute("select mux_ann from ASGraph where prepend_round=? and prefix=? order by unix_time",(r,'184.164.255.0/24'))
    for row in c:
        print row

sys.exit()
'''

#as2mux2round2path = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
as2round2paths = defaultdict(lambda: defaultdict(list))
pfx = '184.164.' + str(255) + '.0/24'
for r in range(0,2):
    c.execute("select mux_seen,mux_ann,observedPath,vpoint from ASGraph where prefix=? and prepend_round=? and feed=?", (pfx,r,'rv'))
    for row in c:

        mux_seen = row[0]
        mux_ann = row[1]

        unfiltered_path = row[2][1:len(row[2])-1]
        s = unfiltered_path.split(", ")
        if len(s) < 2:
            continue

        prep = 0
        if r>0:
            idx_seen = MUX_NAMES.index(mux_seen)
            idx_ann = MUX_NAMES.index(mux_ann)
            if idx_seen > idx_ann:
                prep = r-1
            else:
                prep = r
            prep_status = [r-1]*len(MUX_NAMES)
            for i in range(0,idx_ann+1):
                prep_status[i] += 1
        else:
            prep_status = [0]*len(MUX_NAMES)
            
        for asn in s:
            if asn in MUX_ASN:
                continue
            idx = s.index(asn)
            P = Path(pfx, mux_seen, prep, s[idx:],'',MUX_NAMES,prep_status)
            if P not in as2round2paths[asn][r]:
                as2round2paths[asn][r].append(P)


#print len(as2round2paths)
#print len(as2mux2Path)

for asn in as2round2paths:
    print "AS: " + asn
    for mux in as2mux2Path[asn]:
        print "mux: " + str(mux) + "  " + str(as2mux2Path[asn][mux]) 
    for r in as2round2paths[asn]:
        print "round: " + str(r)
        for path in as2round2paths[asn][r]:
            print path

sys.exit()

for r in range(0,2):
    for i in range(0,5):
        if r==0 and i > 0:
            continue
        if i > 2:
            sys.exit()
        asCount = 0
        asa = 0
        for asn in as2round2paths:
            shortMuxes = findShortestMux(as2mux2Path[asn], r,i)
            paths = as2round2paths[asn][r]
            if not paths:
                continue
            if r > 0:
                if i < len(paths):
                    pathTaken = paths[i]
                else:
                    pathTaken = paths[0]
            else:
                pathTaken = paths[0]

            asCount += 1
            if pathTaken.mux not in shortMuxes:
                asa += 1
                '''
                print asn
                for mux in as2mux2Path[asn]:
                    print "mux: " + str(mux) + "  " + str(as2mux2Path[asn][mux])
                print shortMuxes
                print pathTaken
                '''
        
        #print asa
        #print asCount
        #print "round: " + str(r) + " " + str(i) + " " + str((float(asa)/asCount)*100) 
            

        
