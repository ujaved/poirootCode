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

PREFIX_RANGE = [240]
SLEEP_INTERVAL = 30

def executeThread():

	tstamp = int(time.time())
	for num in PREFIX_RANGE:
		pfx = '184.164.' + str(num) + '.0/24'
		for feed in feeds:
			for rv in pfxToLoc[feed][pfx]:
				update = api.get_path(feed, pfx, rv, 'last_update')
				print update

	

def main():

	resource.setrlimit(resource.RLIMIT_AS, (2147483648L, 2147483648L))

	Pyro4.config.HMAC_KEY = 'choffnes-cunha-javed-owning'
	sys.excepthook = Pyro4.util.excepthook
	ns = Pyro4.naming.locateNS('128.208.4.106', 51556)
	# get the livedb object:
	uri = ns.lookup('livedb.main')
	global api
	api = Pyro4.Proxy(uri)

	global feeds
	#feeds = ['rv', 'ftr','rtr']
	feeds = ['rtr']

	global pfxToLoc
	pfxToLoc = dict()
	for feed in feeds:
		pfxToLoc[feed] = api.get_prefix_to_locations(feed)

	t = threading.Thread(target=executeThread)
	t.start()
	t.join()

if __name__ == '__main__':
	sys.exit(main())

