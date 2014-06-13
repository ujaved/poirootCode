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
	ns = Pyro4.naming.locateNS('128.208.4.106', 51992)
	# get the livedb object:
	uri = ns.lookup('livedb.main')
	global api
	api = Pyro4.Proxy(uri)
	print api.get_available_feeds()

	'''
	PREFIX_RANGE = [240]
	feeds = ['ftr', 'rv','rtr']

	pfxToLoc = dict()
	for feed in feeds:
		pfxToLoc[feed] = api.get_prefix_to_locations(feed)

	tstamp = int(time.time())
	for num in PREFIX_RANGE:
		pfx = '184.164.' + str(num) + '.0/24'
		for feed in feeds:
			for rv in reversed(list(pfxToLoc[feed][pfx])):
				update = api.get_path(feed, pfx, rv, 'last_update')
				if update.time < tstamp-(10*60*60):
					continue
				print update
	'''
			

if __name__ == '__main__':
	sys.exit(main())

