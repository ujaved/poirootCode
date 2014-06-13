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


class Path(object):

    def __init__(self, pfx, mux, prepend, path_data, path_control):
        self.pfx = pfx
        self.mux = mux
        self.prepend = prepend
        self.path_data = path_data
        self.path_control = path_control

    def __str__(self):
        
        return str(self.pfx) + "|" + str(self.mux) + "|" + str(self.prepend) + "|" + str(self.path_control) + \
		       "|" + str(self.path_data)
    

conn = sqlite3.connect('../data/prepend_data/prepend_one.db2012-04-28 12:47:56.579990')
c = conn.cursor()
PREFIX_RANGE = range(250,256)
refasn = 11537
MUX_NAMES = ['CLEMSON', 'GATECH', 'PRINCE', 'WISC', 'UW']
'''
muxASToName[12148] = 'CLEMSON'
muxASToName[2637] = 'GATECH'
muxASToName[88] = 'PRINCE'
muxASToName[2381] = 'WISC'
muxASToName[73] = 'UW'
muxASToName[2722] = 'CLEMSON'
muxASToName[101] = 'UW'
muxASToName[174] = 'GATECH'
'''

pfx2Round2Path = defaultdict(lambda: defaultdict(dict))

for numPrepend in range(0,10):

    for num in PREFIX_RANGE:
    
        pfx = '184.164.' + str(num) + '.0/24'
        #print "-----------------------"
        #print pfx
        #print "-----------------------"
        c.execute("select mux,feed,observedPath from ASGraph where prefix=? and prepend_round=?", (pfx,numPrepend))

        mux2Count = dict()
        path2Count_ctrl = dict()
        path2Count_data = dict()
        for row in c:
            mux = row[0]
            if len(mux)==0: mux='PRINCE'
            if mux in mux2Count:
                mux2Count[mux] += 1
            else:
                mux2Count[mux] = 1

            unfiltered_path = row[2][1:len(row[2])-1]
            s = unfiltered_path.split(", ")
            idx = s.index(str(refasn))
            s = s[idx:]

            if row[1]=='ftr':
                prev_asn = '0'
                opath = ""
                for asn in s:
                    if asn==prev_asn or asn=='0':
                        continue
                    opath = opath + " " + str(asn)
                    prev_asn = asn
                opath.strip()

                if opath in path2Count_data:
                    path2Count_data[opath] += 1
                else:
                    path2Count_data[opath] = 1

            if row[1]=='rv':
                opath = ""
                for asn in s:
                    opath = opath + " " + str(asn)
                opath.strip()

                if opath in path2Count_ctrl:
                    path2Count_ctrl[opath] += 1
                else:
                    path2Count_ctrl[opath] = 1
                    
        sorted_muxC = sorted(mux2Count.iteritems(), key=operator.itemgetter(1),reverse=True)
        sorted_data = sorted(path2Count_data.iteritems(), key=operator.itemgetter(1),reverse=True)
        sorted_ctrl = sorted(path2Count_ctrl.iteritems(), key=operator.itemgetter(1),reverse=True)

        
        if num==255:
            print sorted_muxC
            print sorted_data
            print sorted_ctrl
        
        
        P = Path(pfx, sorted_muxC[0][0], numPrepend, sorted_data[0][0], sorted_ctrl[0][0])
        pfx2Round2Path[pfx][numPrepend] = P

'''
for numPrepend in range(0,4):
    for num in PREFIX_RANGE:

        pfx = '184.164.' + str(num) + '.0/24'
        print pfx2Round2Path[pfx][numPrepend]
'''     
            

        
