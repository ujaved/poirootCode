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
from helper import create_parser, mkdir_p, Prefix
import sqlite3


conn = sqlite3.connect('data/imc1.db')
c = conn.cursor()
d = conn.cursor()
PREFIX_RANGE = range(241,250,2)
#pfx = '184.164.249.0/24'
#c.execute("select x.vpoint, x.observedPath, y.vpoint, y.observedPath from ASGraph x, ASGraph y where x.prefix=? and y.prefix=? and x.vpoint=y.vpoint and x.bfs_level=?  and x.poison_round=? and \
#y.bfs_level=? and y.poison_round=? group by x.vpoint,x.observedPath", (pfx,pfx,1,1,1,2))

for row in c:
    print row

#c.execute("select asn,edge from ASGraph where prefix=? and bfs_iteration=? and edge is not ? group by asn,edge", (pfx,1,0))

for num in PREFIX_RANGE:
    pfx = '184.164.' + str(num) + '.0/24'
    print pfx
    print "-----------------------------"
    path_dict = dict()
    edge_dict = dict()
    for poison_round in range(1,5):
        print "-------------"
        print poison_round
        print "-------------"
        c.execute("select observedPath from ASGraph where prefix=? and bfs_level=? and poison_round=? group by observedPath", (pfx,1,poison_round))
        d.execute("select asn,edge from ASGraph where prefix=? and bfs_level=? and poison_round=? and edge is not ? group by asn,edge", (pfx,1,poison_round,0))

        path_count = 0
        edge_count = 0
        for row in c:
            if row[0] in path_dict:
                continue
            path_dict[row[0]] = 1
            path_count += 1

        for row in d:
            p = str(row[0]) + "," + str(row[1])
            if p in edge_dict:
                continue
            edge_dict[p] = 1
            edge_count += 1

        print path_count
        print edge_count
        

    count = 0
    for row in d:
        if row[0] in path_dict:
            continue
        count += 1

    print pfx + " " + str(count)


#c.execute("select max(bfs_level) from ASGraph")
#for row in c:
#    print row
#c.execute("select * from ASGraph where prefix=? and bfs_iteration=?", (pfx,1))

'''
count = 0
for row in c:
    asn = row[0]
    edge = row[1]
    d.execute("select * from ASGraph where prefix=? and asn=? and edge=? and bfs_iteration=?", (pfx,asn,edge,0))
    data=d.fetchall()
    if len(data) == 0:
        count += 1

print count
'''
