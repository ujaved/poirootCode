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

def main():

	resource.setrlimit(resource.RLIMIT_AS, (2147483648L, 2147483648L))

	Pyro4.config.HMAC_KEY = 'choffnes-cunha-javed-owning'
	sys.excepthook = Pyro4.util.excepthook
	ns = Pyro4.naming.locateNS('128.208.4.106', 51556)
	# get the livedb object:
	uri = ns.lookup('livedb.main')
	global api
	api = Pyro4.Proxy(uri)
	
	feeds = ['rv', 'ftr']
		
	pfxToLoc = dict()
	for feed in feeds:
		pfxToLoc[feed] = api.get_prefix_to_locations(feed)

	num = 241
	P = Prefix(num, 47065, "announced")
	tstamp = int(time.time())
	pfx = '184.164.' + str(num) + '.0/24'
	count = 0
	tot = 0
	VP_before = dict()
	VP_after = dict()
	for feed in feeds:
		locs = pfxToLoc[feed][pfx]
		for rv in locs:
			update = api.get_path(feed, pfx, rv, 'last_update')
			tot += 1
			if update.time < tstamp-(30*60):
				count += 1
				continue
			else:
				VP_before[rv] = update

	
	P.poisonList([47065])
	P.up()
	soft_reset()
	wait_cmd(1800)

	for feed in feeds:
		locs = pfxToLoc[feed][pfx]
		for rv in locs:
			update = api.get_path(feed, pfx, rv, 'last_update')
			if rv not in VP_before:
				continue
			VP_after[rv] = update

	
	for rv in VP_before:
		print "----------------------"
		print rv
		print VP_before[rv]
		print VP_before[rv].hops
		print "*******"
		if rv in VP_after:
			print VP_after[rv]
			print VP_after[rv].hops

		print "----------------\n"


def soft_reset(): # {{{
        tstamp = int(time.time())
        logging.info('soft_reset %s', tstamp)
        cmd = 'vtysh -d bgpd -c "clear ip bgp * soft out"'
        logging.debug(cmd)
        os.system(cmd)
        cmd = 'vtysh -d bgpd -c "show running-config" > log/%s.config' % tstamp
        logging.debug(cmd)
        os.system(cmd)
# }}}

def wait_cmd(interval):
        logging.debug('sleeping for %d seconds', interval)
        time.sleep(interval)


if __name__ == '__main__':
	sys.exit(main())

