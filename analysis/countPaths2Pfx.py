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
from helper import create_parser, mkdir_p, Prefix, ASN, getFilteredPath,VP_Poison
import sqlite3
from operator import itemgetter
from collections import defaultdict


def announce_sentinel(pfx,mux):

	for m in MUX_NAMES:
		if m==mux:
			pfx.update_route_map1(m, True)
		else:
			pfx.update_route_map1(m,False)
	pfx.up()

def announce_null(pfx):

	for m in MUX_NAMES:
		pfx.update_route_map1(m,False)
	pfx.up()

PREFIX_RANGE = [241,243,245,247,249]
RIOT_ASN = 47065
SENTINEL = 0
TEST = 1
MUX_NAMES = ['CLEMSON', 'GATECH', 'PRINCE', 'UW','WISC']
muxASToName = dict()
muxASToName[12148] = 'CLEMSON'
muxASToName[2637] = 'GATECH'
muxASToName[88] = 'PRINCE'
muxASToName[2381] = 'WISC'
muxASToName[73] = 'UW'
muxASToName[2722] = 'CLEMSON'
muxASToName[101] = 'UW'
muxASToName[10466] = 'PRINCE'
muxASToName[7922] = 'PRINCE'
muxASToName[174] = 'GATECH'

POISON_INTERVAL = 1200
POISON_INTERVAL_2 = 600
START_TIME = int(time.time())
				
def main():

	global opts 
	parser = create_parser()
	opts, _args = parser.parse_args()

	opts.output = opts.output + str(datetime.now())
	resource.setrlimit(resource.RLIMIT_AS, (2147483648L, 2147483648L))

	Pyro4.config.HMAC_KEY = 'choffnes-cunha-javed-owning'
	sys.excepthook = Pyro4.util.excepthook
	ns = Pyro4.naming.locateNS('128.208.4.106', 51556)
	# get the livedb object:
	uri = ns.lookup('livedb.main')
	global api
	api = Pyro4.Proxy(uri)

	mkdir_p(opts.logdir)
	logger = logging.getLogger()
	logger.setLevel(logging.DEBUG)
	formatter = logging.Formatter('%(message)s')
	loghandler = logging.handlers.RotatingFileHandler(opts.logfile,
			maxBytes=128*1024*1024, backupCount=5)
	loghandler.setFormatter(formatter)
	logger.addHandler(loghandler)

	global feeds
	feeds = ['ftr', 'rv', 'rtr']
	num2pfx = dict()

	global pfxToLoc
	pfxToLoc = dict()
	for feed in feeds:
		pfxToLoc[feed] = api.get_prefix_to_locations(feed)
	
	for num in PREFIX_RANGE:
		num2pfx[num] = Prefix(num, RIOT_ASN, "announced")
		num2pfx[num].up()
		announce_null(num2pfx[num])

	soft_reset(num2pfx)
	wait_cmd(POISON_INTERVAL_2)
	
	#initial poisoning so that the path shows up in the data feeds
	pfx_idx = 0
	for mux in MUX_NAMES:
		pfx = num2pfx[PREFIX_RANGE[pfx_idx]]
		pfx.poisonList([RIOT_ASN])
		announce_sentinel(pfx,mux)
		pfx_idx += 1

	soft_reset(num2pfx)
	wait_cmd(POISON_INTERVAL)

	numPaths = 0
	tstamp = int(time.time())
	for feed in feeds:	
		locs = pfxToLoc[feed][pfx]
		for rv in locs:
			update = api.get_path(feed, pfx, rv, 'last_update')
			if feed=='rv':
				if update.time < START_TIME:
					continue
				vp = str(rv).split(',')
				if len(vp)<2:
					continue
			elif feed=='ftr' or feed=='rtr':
				if update.time < tstamp-(30*60):
					continue
			numPaths += 1

	print numPaths

	
	


def soft_reset(num2pfx): # {{{
	tstamp = int(time.time())
	logging.info('soft_reset %s', tstamp)
	cmd = 'vtysh -d bgpd -c "clear ip bgp * soft out"'
	logging.debug(cmd)
	#sys.stderr.write(cmd+'\n')
	os.system(cmd)
	cmd = 'vtysh -d bgpd -c "show running-config" > log/%s.config' % tstamp
	logging.debug(cmd)
	#sys.stderr.write(cmd+'\n')
	os.system(cmd)
	opts.last_reset = tstamp
	for num in PREFIX_RANGE:
		logging.info('prefix_grep %d 184.164.%d.0/24 %s %s', tstamp, num,
				num2pfx[num].status, num2pfx[num].as_path_string)
# }}}

def wait_cmd(interval):
	logging.debug('sleeping for %d seconds', interval)
	time.sleep(interval)

if __name__ == '__main__':
	sys.exit(main())

