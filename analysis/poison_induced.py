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
import itertools

RIOT_ASN = 47065
MUX_NAMES = ['UW', 'WISC', 'GATECH', 'PRINCE', 'CLEMSON']


def main():

	pfx = '184.164.250.0/24'
	num = 250
	
	pfx_object = Prefix(num, 47065, "announced")
	pfx_object.up()

	mux2Poison = 'PRINCE'
	controlMux = 'GATECH'
	poisonAS = 7922
	pfx_object.poisonList([poisonAS])
	pfx_object.update_route_map1(mux2Poison,True)

	pfx_object.up()
	soft_reset()

	
def soft_reset(): # {{{
	tstamp = int(time.time())
	print tstamp
	cmd = 'vtysh -d bgpd -c "clear ip bgp * soft out"'
	os.system(cmd)
	cmd = 'vtysh -d bgpd -c "show running-config" > log/%s.config' % tstamp
	os.system(cmd)
# }}}

def wait_cmd(interval):
	logging.debug('sleeping for %d seconds', interval)
	time.sleep(interval)

if __name__ == '__main__':
	sys.exit(main())

