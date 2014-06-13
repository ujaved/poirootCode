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
MUX_ASN = ['73','2381','2637','88','12148', '47065']
muxASToName = dict()
muxASToName['12148'] = 'CLEMSON'
muxASToName['2637'] = 'GATECH'
muxASToName['88'] = 'PRINCE'
muxASToName['2381'] = 'WISC'
muxASToName['73'] = 'UW'
muxASToName['2722'] = 'CLEMSON'
muxASToName['101'] = 'UW'
muxASToName['10466'] = 'PRINCE'
muxASToName['174'] = 'GATECH'

SET = 0
SINGLE = 1


class Path(object):

    def __init__(self, pfx, up_asn, mux, prepend, path_control, path_data, mux_list, prepend_status):
        self.pfx = pfx
        self.up_asn = up_asn    #upstream AS to which the announcement is made
        self.mux = mux
        self.prepend = prepend
        self.path_data = path_data
        self.path_control = path_control
        self.mux_list = mux_list
        self.prepend_status = prepend_status
        self.hash = hash(str(self))

    def __str__(self):
        
        return str(self.pfx)  + "|" + str(self.mux) + "|" + str(self.prepend) + "|" + str(self.path_control) + \
		       "|" + str(self.path_data) + "|" + str(self.mux_list) + "|" + str(self.prepend_status)  

    def __eq__(self,other):
        return self.hash==other.hash


def getFilteredPath(path,mux):
    r = list(path)
    r.reverse()
    m = mux
    for asn in r:
        if asn in muxASToName:
            m = muxASToName[asn]
            break

    if not m==mux:
        return None
    
    filpath = []

    prev_asn = '0'
    for asn in s:
        if asn==prev_asn or asn=='0':
            continue
        if prev_asn=='10466':
            filpath.append('88')
        filpath.append(asn)
        prev_asn = asn
    if asn=='0' and prev_asn in MUX_ASN[0:5]:
        filpath.append('47065')

    loopDet = dict()
    for asn in filpath:
        if asn in loopDet:
            idx = filpath.index(asn)
            filpath = filpath[idx:]
            break
        loopDet[asn] = 1

    return filpath
    
def findShortestMux(mux2Path, round,i, shortest_status):

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

    if shortest_status==SET:
        return shortMuxes
    else:
        return shortMuxes[0]

def getChosenMux(round2paths,round,i):

    paths = round2paths[round]
    if not paths and round==0:
        return None
    if not paths:
        paths = round2paths[0]
    if round > 0:
        if i < len(paths):
            muxTaken = paths[i].mux
        else:
            muxTaken = paths[0].mux
    else:
        muxTaken = paths[0].mux

    return muxTaken
    

        
conn = sqlite3.connect('../data/prepend_data/RR.py2012-05-01 08:20:04.857817')
c = conn.cursor()

as2mux2Path = defaultdict(lambda: defaultdict(dict))
for num in range(250,255):
    pfx = '184.164.' + str(num) + '.0/24'
    c.execute("select mux_seen,observedPath from ASGraph where prefix=? and prepend_round=? and feed=?", (pfx,0,'rv'))
    for row in c:
        
        mux = row[0]
        if len(mux)==0:
            continue

        unfiltered_path = row[1][1:len(row[1])-1]
        s = unfiltered_path.split(", ")
        prev_asn = '0'
        for asn in s:
            if asn in MUX_ASN or asn==prev_asn:
                prev_asn = asn
                continue
            idx = s.index(asn)
            P = Path(pfx, prev_asn, mux, 0, s[idx:],'',MUX_NAMES,[0,0,0,0,0])
            #if asn=='6939':
                #print P
            as2mux2Path[asn][mux] = P
            prev_asn = asn


    c.execute("select mux_seen,observedPath from ASGraph where prefix=? and prepend_round=? and feed=?", (pfx,0,'ftr'))
    for row in c:
        
        mux = row[0]
        unfiltered_path = row[1][1:len(row[1])-1]
        s = unfiltered_path.split(", ")
        filpath = getFilteredPath(s,mux)
        if filpath is None:
            continue

        prev_asn = '0'
        for asn in filpath:
            if asn in MUX_ASN or asn==prev_asn:
                prev_asn = asn
                continue
            idx = filpath.index(asn)
            if asn in as2mux2Path:
                if mux in as2mux2Path[asn]:
                    as2mux2Path[asn][mux].path_data = filpath[idx:]
                else:
                    P = Path(pfx, prev_asn, mux, 0,'',filpath[idx:],MUX_NAMES,[0,0,0,0,0])
                    as2mux2Path[asn][mux] = P
            else:
                P = Path(pfx, prev_asn, mux, 0,'',filpath[idx:],MUX_NAMES,[0,0,0,0,0])
                as2mux2Path[asn][mux] = P
            prev_asn = asn
          

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

        prev_asn = '0'
        for asn in s:
            if asn in MUX_ASN or asn==prev_asn:
                prev_asn = asn
                continue
            idx = s.index(asn)
            P = Path(pfx, prev_asn, mux_seen, prep, s[idx:],'',MUX_NAMES,prep_status)
            prev_asn = asn
            if P not in as2round2paths[asn][r]:
                as2round2paths[asn][r].append(P)


for r in range(0,2):
    c.execute("select mux_seen,mux_ann,observedPath from ASGraph where prefix=? and prepend_round=? and feed=?", (pfx,r,'ftr'))
    for row in c:

        mux_seen = row[0]
        mux_ann = row[1]

        unfiltered_path = row[2][1:len(row[2])-1]
        s = unfiltered_path.split(", ")
        filpath = getFilteredPath(s,mux)
        if filpath is None:
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

        prev_asn = '0'
        for asn in s:
            if asn in MUX_ASN or asn==prev_asn:
                prev_asn = asn
                continue
            idx = filpath.index(asn)
            if asn in as2round2paths:
                if r in as2mux2Path[asn]:
                    as2mux2Path[asn][mux].path_data = filpath[idx:]
                else:
                    P = Path(pfx, prev_asn, mux, 0,'',filpath[idx:],MUX_NAMES,[0,0,0,0,0])
                    as2mux2Path[asn][mux] = P
            else:
                P = Path(pfx, prev_asn, mux, 0,'',filpath[idx:],MUX_NAMES,[0,0,0,0,0])
                as2mux2Path[asn][mux] = P
            prev_asn = asn
            P = Path(pfx, prev_asn, mux_seen, prep, s[idx:],'',MUX_NAMES,prep_status)
            prev_asn = asn
            if P not in as2round2paths[asn][r]:
                as2round2paths[asn][r].append(P)

#there would be some asns in in as2mux2Path that won't be as2round2paths
#limited only to round 0. More than one path means you'd have to infer what this AS would've picked

for asn in as2mux2Path:
    if asn not in as2round2paths:
        m = findShortestMux(as2mux2Path[asn],0,0,SINGLE)
        as2round2paths[asn][0].append(as2mux2Path[asn][m])


#print len(as2round2paths)
#print len(as2mux2Path)
'''
for asn in as2round2paths:
    print "AS: " + asn
    for mux in as2mux2Path[asn]:
        print "mux: " + str(mux) + "  " + str(as2mux2Path[asn][mux]) 
    for r in as2round2paths[asn]:
        print "round: " + str(r)
        for path in as2round2paths[asn][r]:
            print path

sys.exit()
'''

for r in range(0,2):
    for i in range(0,5):
        if r==0 and i > 0:
            continue
        '''
        print "-----------------------------------------------"
        print i
        print "-----------------------------------------------"
        '''
        asCount = 0
        asa = 0
        for asn in as2round2paths:
            #print "AS: " + str(asn)
            firstHop = dict()
            #print "init: "
            for mux in as2mux2Path[asn]:
                #print as2mux2Path[asn][mux]
                path = as2mux2Path[asn][mux].path_control
                firstHop[path[1]] = as2mux2Path[asn][mux]
            muxes_available = []
            for h in firstHop:
                if h in MUX_ASN:
                    m = MUX_NAMES[MUX_ASN.index(h)]
                else:
                    if asn=='3549' and h=='6939': 
                        m = getChosenMux(as2round2paths[h],r,i*2)
                    else:
                        m = getChosenMux(as2round2paths[h],r,i)
                if not m:
                    m = firstHop[h].mux
                if m not in muxes_available:
                    muxes_available.append(m)
        
            '''
            print "available: "
            for m in muxes_available:
                print m
            '''
            

            tempmux2path = dict()
            for m in as2mux2Path[asn]:
                if m in muxes_available:
                    tempmux2path[m] = as2mux2Path[asn][m] 
            shortMuxes = findShortestMux(tempmux2path,r,i,SET)

            '''
            print "shortest: "
            for m in shortMuxes:
                print m
            '''

            paths = as2round2paths[asn][r]
            if not paths and r==0:
                continue
            if not paths:
                paths = as2round2paths[asn][0]
                pathTaken = paths[0]
            if r > 0:
                if i < len(paths):
                    pathTaken = paths[i]
                else:
                    pathTaken = paths[0]
            else:
                pathTaken = paths[0]

            '''
            print "taken: "
            print pathTaken
            '''

            
            asCount += 1
            if pathTaken.mux not in shortMuxes:
                asa += 1
            
        
        print asa
        print asCount
        print "round: " + str(r) + " " + str(i) + " " + str((float(asa)/asCount)*100) 
            

        
