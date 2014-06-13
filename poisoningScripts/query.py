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
import collections


class Path(object):

    def __init__(self, asn, pfx, mux, path):
        self.asn = asn
        self.pfx = pfx
        self.mux = mux
        self.path = path
    

conn = sqlite3.connect('../data/prepend_data/prepend_one.db2012-04-28 12:47:56.579990')
c = conn.cursor()
pfx = '184.164.250.0/24'
c.execute("select observedPath,ipPath from ASGraph where prefix=? and prepend_round=?", (pfx,0))

for row in c:
    print row


        
