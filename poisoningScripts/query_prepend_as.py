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
import sqlite3
from collections import defaultdict
import operator
import copy
from helper import Path, MUX_NAMES, MUX_ASN, SET, SINGLE, getFilteredPath, getPrependStatus, findShortestMux, getChosenMux, prep_MUX
 
       
conn = sqlite3.connect('../data/prepend_data/prepend_one_as.db2012-04-28 16:25:29.859463')
c = conn.cursor()

as2mux2Path = defaultdict(lambda: defaultdict())
as2mux2datapaths = defaultdict(lambda: defaultdict(list))
for num in range(241,250,2):
    pfx = '184.164.' + str(num) + '.0/24'
    c.execute("select mux,observedPath from ASGraph where prefix=? and prepend_round=? and feed=?", (pfx,0,'rv'))
    for row in c:
        mux = row[0]
        if len(mux)==0: mux='PRINCE'

        unfiltered_path = row[1][1:len(row[1])-1]
        s = unfiltered_path.split(", ")
        prev_asn = '0'
        for asn in s:
            if asn in MUX_ASN or asn==prev_asn:
                prev_asn = asn
                continue
            idx = s.index(asn)
            P = Path(pfx, prev_asn, mux, 0, s[idx:],'',MUX_NAMES,[0,0,0,0,0],[])
            as2mux2Path[asn][mux] = P
            prev_asn = asn

    
    c.execute("select mux,observedPath from ASGraph where prefix=? and prepend_round=? and feed=?", (pfx,0,'ftr'))
    for row in c:
        
        mux = row[0]
        if len(mux)==0:
            if '7922' in s:
                mux='PRINCE'
            elif '174' in s:
                mux='GATECH'
            else:
                continue
        unfiltered_path = row[1][1:len(row[1])-1]
        s = unfiltered_path.split(", ")
        if len(s) < 2:
            continue
        if len(s) < 3 and s[-1] not in MUX_ASN:
             continue
        filpath = getFilteredPath(s,mux)
        if filpath is None:
            continue

        prev_asn = '0'
        for asn in filpath:
            if asn in MUX_ASN or asn==prev_asn:
                prev_asn = asn
                continue
            idx = filpath.index(asn)
            P = Path(pfx, prev_asn, mux, 0,'',filpath[idx:],MUX_NAMES,[0,0,0,0,0],[])
            as2mux2datapaths[asn][mux].append(filpath[idx:])
            if asn in as2mux2Path:
                if mux in as2mux2Path[asn]:
                    as2mux2Path[asn][mux].path_data = filpath[idx:]
                else:
                    as2mux2Path[asn][mux] = P
            else:
                as2mux2Path[asn][mux] = P
            prev_asn = asn


'''
for asn in as2mux2Path:
    print "AS: " + asn
    for mux in as2mux2Path[asn]:
        P = as2mux2Path[asn][mux]
        if not P.path_control or not P.path_data:
            continue
        if P.path_control==P.path_data:
            continue
        print "mux: " + str(mux) + " " + str(P)
sys.exit()
'''

as2round2path = defaultdict(lambda: defaultdict())
pfx = '184.164.' + str(240) + '.0/24'
for r in range(0,7):
    c.execute("select mux,observedPath from ASGraph where prefix=? and prepend_round=? and feed=?", (pfx,r,'rv'))
    for row in c:

        mux = row[0]
        if len(mux)==0:
            if '7922' in s:
                mux='PRINCE'
            elif '174' in s:
                mux='GATECH'
            else:
                continue
        
        unfiltered_path = row[1][1:len(row[1])-1]
        s = unfiltered_path.split(", ")
        if len(s) < 2:
             continue

        prep_status = [0]*len(MUX_NAMES)
        if r>0:
            prep_status = getPrependStatus(r)
        prep = prep_status[MUX_NAMES.index(mux)]

        prev_asn = '0'
        for asn in s:
            if asn in MUX_ASN or asn==prev_asn:
                prev_asn = asn
                continue
            idx = s.index(asn)
            P = Path(pfx, prev_asn, mux, prep, s[idx:],'',MUX_NAMES,prep_status,[])
            as2round2path[asn][r] = P
            prev_asn = asn


    c.execute("select mux,observedPath from ASGraph where prefix=? and prepend_round=? and feed=?", (pfx,r,'ftr'))
    for row in c:
        mux = row[0]
        if len(mux)==0:
            if '7922' in s:
                mux='PRINCE'
            elif '174' in s:
                mux='GATECH'
            else:
                continue
        unfiltered_path = row[1][1:len(row[1])-1]
        s = unfiltered_path.split(", ")
        if len(s) < 2:
            continue
        if len(s) < 3 and s[-1] not in MUX_ASN:
             continue
        filpath = getFilteredPath(s,mux)
        if filpath is None:
            continue

        prep_status = [0]*len(MUX_NAMES)
        if r>0:
            prep_status = getPrependStatus(r)
        prep = prep_status[MUX_NAMES.index(mux)]

        prev_asn = '0'
        for asn in filpath:
            if asn in MUX_ASN or asn==prev_asn:
                prev_asn = asn
                continue
            idx = filpath.index(asn)
            P = Path(pfx, prev_asn, mux, prep,'',filpath[idx:],MUX_NAMES,prep_status,[])
            if asn in as2round2path:
                if r in as2round2path[asn]:
                    if len(as2round2path[asn][r].path_data)==0:
                        as2round2path[asn][r].path_data = filpath[idx:]
                    else:
                        if not (mux==as2round2path[asn][r].mux):
                            if P not in as2round2path[asn][r].alt_path_list:
                                as2round2path[asn][r].alt_path_list.append(P)
                else:
                    as2round2path[asn][r] = P
            else:
                as2round2path[asn][r] = P
            prev_asn = asn

'''
for asn in as2round2path:
    print "AS: " + asn
    for mux in as2mux2Path[asn]:
        print "mux: " + str(mux) + "  " + str(as2mux2Path[asn][mux])
    for r in as2round2path[asn]:
        print "round: " + str(r)
        print as2round2path[asn][r]
        if not as2round2path[asn][r].alt_path_list:
            continue
        print "alt paths:"
        for p in as2round2path[asn][r].alt_path_list:
            print p
sys.exit()
'''

#as2mux2Path gives you a prepend-free path to each mux from the AS if it were available. This path is not necessarily available to the AS
#at any given time. Sometimes you would have a prepend-free path to a mux in as2round2path that won't be available in as2mux2Path. We have to take care
#of that here

for asn in as2round2path:
    for r in as2round2path[asn]:
        P = as2round2path[asn][r]
        if P.mux not in as2mux2Path[asn]:
            as2mux2Path[asn][P.mux] = copy.deepcopy(P)
            P = as2mux2Path[asn][P.mux]
            P.prepend_status = [0,0,0,0,0]
            if P.prepend == 0:
                continue
            if len(P.path_control)>0:
                l = len(P.path_control)
                P.path_control = P.path_control[0:l-P.prepend]
                print asn
            P.prepend = 0


#there would be some asns in in as2mux2Path that won't be as2round2paths
#limited only to round 0. More than one path means you'd have to infer what this AS would've picked

for asn in as2mux2Path:
    if asn not in as2round2path:
        #print asn
        m = findShortestMux(as2mux2Path[asn],0,SINGLE)
        as2round2path[asn][0] = as2mux2Path[asn][m]

    '''
    else:
        for r in as2round2path[asn]:
            p = as2round2path[asn][r]
            mux = p.mux
        if mux not in 
    '''


#print len(as2round2path)
#print len(as2mux2Path)

for asn in as2round2path:
    print "AS: " + asn
    for mux in as2mux2Path[asn]:
        print "mux: " + str(mux) + "  " + str(as2mux2Path[asn][mux])
    for r in as2round2path[asn]:
        print "round: " + str(r)
        print as2round2path[asn][r]
        if not as2round2path[asn][r].alt_path_list:
            continue
        print "alt paths:"
        for p in as2round2path[asn][r].alt_path_list:
            print p
sys.exit()

for r in range(0,7):

    print "--------------------------------"
    print r
    print "--------------------------------"

    asCount = 0
    asa = 0
    for asn in as2round2path:
        print "AS: " + str(asn)
        firstHop = dict()
        print "init: "
        for mux in as2mux2Path[asn]:
            print as2mux2Path[asn][mux]
            if len(as2mux2Path[asn][mux].path_control) > 0:
                path = as2mux2Path[asn][mux].path_control
            else:
                path = as2mux2Path[asn][mux].path_data
            firstHop[path[1]] = 1
        muxes_available = []
        
        for h in firstHop:
            if h in MUX_ASN:
                m = MUX_NAMES[MUX_ASN.index(h)]
            else:
                if asn=='3549' and h=='6939':
                    m = getChosenMux(as2round2path[h],r,asn)
                else:
                    m = getChosenMux(as2round2path[h],r,asn)
            if not m:
                #m = firstHop[h].mux
                continue
            if m not in muxes_available:
                muxes_available.append(m)

        if not muxes_available:
            continue

        print "available: "
        for m in muxes_available:
            print m

        tempmux2path = dict()
        for m in as2mux2Path[asn]:
            if m in muxes_available:
                tempmux2path[m] = as2mux2Path[asn][m]
        shortMuxes = findShortestMux(tempmux2path,r,SET)

        if r not in as2round2path[asn]:
            continue

        pathTaken = as2round2path[asn][r]
        
        asCount += 1
        if pathTaken.mux not in shortMuxes:
            asa += 1

            '''
            print asn
            for mux in as2mux2Path[asn]:
                print "mux: " + str(mux) + "  " + str(as2mux2Path[asn][mux])
            print pathTaken
            '''

    print "round: " + str(r) + " " + str((float(asa)/asCount)*100)
           

        
