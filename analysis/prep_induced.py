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

def announce_null(pfx):

	for m in MUX_NAMES:
		pfx.update_route_map1(m,False)
	pfx.up()


def announce_sentinel(pfx,mux):

	for m in MUX_NAMES:
		if m==mux:
			pfx.update_route_map1(m, True)
		else:
			pfx.update_route_map1(m,False)
	pfx.up()



PREFIX_RANGE = range(250,256)
RIOT_ASN = 47065
SENTINEL = 0
TEST = 1
MUX_NAMES = ['UW', 'WISC', 'GATECH', 'PRINCE', 'CLEMSON']
muxASToName = dict()
muxASToName[12148] = 'CLEMSON'
muxASToName[2637] = 'GATECH'
muxASToName[88] = 'PRINCE'
muxASToName[2381] = 'WISC'
muxASToName[73] = 'UW'
muxASToName[2722] = 'CLEMSON'
muxASToName[101] = 'UW'
muxASToName[10466] = 'PRINCE'
muxASToName[174] = 'GATECH'

NULL_INTERVAL = 200

def main():

	num = 251	
	pfx_object = Prefix(num, 47065, "announced")
	pfx_object.up()
	announce_null(pfx_object)

	soft_reset()
	wait_cmd(NULL_INTERVAL)

	muxesToPrepend = ['PRINCE']
	prependLengths = [2]
	for mux in MUX_NAMES:
		if mux in muxesToPrepend:
			idx = muxesToPrepend.index(mux)
			pfx_object.set_num_prepend1(prependLengths[idx],mux)
		else:
			pfx_object.update_route_map1(mux,False)

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

