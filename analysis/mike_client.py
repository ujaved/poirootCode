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
from helper import create_parser, mkdir_p, Prefix, ASN
import sqlite3
from operator import itemgetter

RIOT_ASN = 47065

db_file = "../data/mike_data/mike.db2012-04-26 09:33:20.934717"
conn = sqlite3.connect(db_file)
c = conn.cursor()

sentinel_pfx = '184.164.248.0/24'
pfx = '184.164.249.0/24'
c.execute("select vpoint,filteredASPath from ASGraph where prefix=? group by vpoint", (sentinel_pfx,))
orig_paths = c.fetchall()


for i in range(0,len(orig_paths)):
    
    vpoint = orig_paths[i][0]
    sent_path = orig_paths[i][1]

    print "rv: " + vpoint
    print "sentinel path: " + sent_path
    
    c.execute("select filteredASPath from ASGraph where prefix=? and vpoint=? order by unix_time DESC limit 1 ", (pfx,vpoint))

    cur_path = c.fetchone()
    print "current path: " + cur_path[0]
