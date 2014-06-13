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


def populateDB(c, num, refASN):
	print "----------------------"
	print numPrepend
	pfx = '184.164.' + str(num) + '.0/24'
	print pfx
	VPseen = num2VPseen[num]
	curVP = dict()
	muxCount = dict()
	tstamp = int(time.time())
	for feed in feeds:
		locs = pfxToLoc[feed][pfx]
		for rv in locs:
			update = api.get_path(feed, pfx, rv, 'last_update')
			if feed=='ftr':
				if update.time < tstamp-(30*60):
					continue
				if rv in VPseen:
					prev_upd = VPseen[rv] 
					if update.time<=prev_upd.time:
						continue

			curVP[rv] = update
			#discarding paths that don't contain refASN

			unix_time = update.time

			if not update.path:
				update.path = [0]

			if refASN not in update.path:
				continue

			mux = ''
			for m in muxASToName:
				if m in update.path:
					mux = muxASToName[m]
					break

			if mux in muxCount and len(mux)>0:
				muxCount[mux] += 1
			elif len(mux)>0:
				muxCount[mux] = 1


			'''
			#removing duplicates from the path in case of 'ftr'
			prev_asn = 0
			filpath = ""
			for asn in update.path:
				if (asn==prev_asn or asn==0) and feed=='ftr':
					continue
			        filpath = filpath + " " + str(asn)
				prev_asn = asn
			filpath.strip()
			'''

			dtime = str(datetime.fromtimestamp(update.time))
			c.execute('insert into ASGraph values (?,?,?,?,?,?,?,?,?,?)', \
						  (pfx, unix_time, dtime, \
						   refASN, numPrepend, mux, feed, str(update.path), str(update.hops),rv))

	print muxCount
	VPseen.clear()
	for vp in curVP:
		VPseen[vp] = curVP[vp]
	
	global mux_255
	if num==255:
		counts = muxCount.items()
		counts.sort(key = itemgetter(1), reverse=True)
		mux_255 = counts[0][0]
		print mux_255
		
	sys.stdout.flush()


PREFIX_RANGE = range(250,256)
RIOT_ASN = 47065
MUX_NAMES = ['CLEMSON', 'GATECH', 'PRINCE', 'WISC', 'UW']
muxASToName = dict()
muxASToName[12148] = 'CLEMSON'
muxASToName[2637] = 'GATECH'
muxASToName[88] = 'PRINCE'
muxASToName[2381] = 'WISC'
muxASToName[73] = 'UW'
muxASToName[2722] = 'CLEMSON'
muxASToName[101] = 'UW'
muxASToName[174] = 'GATECH'


def main():

	global opts 
	parser = create_parser()
	opts, _args = parser.parse_args()
	if  opts.database is None or opts.refasn is None:
		parser.parse_args(['-h'])

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

	sys.stdout = open(opts.output, 'w')
	sys.stderr = sys.stdout

	conn = sqlite3.connect(opts.database + str(datetime.now()))
	c = conn.cursor()

	#observedPath is the raw path that you see both feeds: lists if ASs from ftr and list of ASes from rv (W in case of withdrawn rv path)
	#filteredASPath is the filtered AS path
	#asn: the ASN that we're trying to measure

	c.execute("create table if not exists ASGraph (prefix text, unix_time int, dtime text, asn int, \
                   prepend_round int, mux text, feed text, observedPath text, ipPath text, vpoint text)")
	c.execute("create index idx_pfx on ASGraph(prefix)")
	c.execute("create index idx_asn on ASGraph(asn)")
	c.execute("create index idx_pfx_path on ASGraph(prefix,observedPath)")
	c.execute("create index idx_prepend on ASGraph(prepend_round)")
	

	global feeds
	feeds = ['rv', 'ftr']
	num2pfx = dict()

	#announce 250-254 from one mux and 255 from all muxesscreen emacs help
	for num in PREFIX_RANGE:
		num2pfx[num] = Prefix(num, 47065, "announced")

	#initial poisoning so that the path shows up in the data feeds
	for num in PREFIX_RANGE:
		pfx = num2pfx[num]
		if num==255:
			for mux in MUX_NAMES:
				pfx.update_route_map1(mux, True)
		else:
			for mux in MUX_NAMES:
				if PREFIX_RANGE.index(num)==MUX_NAMES.index(mux):
					pfx.update_route_map1(mux, True)
				else:
					pfx.update_route_map1(mux,False)
		pfx.up()

	soft_reset(num2pfx)
	wait_cmd(1800)
		
	global pfxToLoc
	pfxToLoc = dict()
	for feed in feeds:
		pfxToLoc[feed] = api.get_prefix_to_locations(feed)

	global num2VPseen
	num2VPseen = dict()
	for num in PREFIX_RANGE:
		num2VPseen[num] = dict()

	global mux_255
	global numPrepend
	numPrepend = 0
	#for refasn store the initial path for each prefix

	for num in PREFIX_RANGE:
		populateDB(c,num,opts.refasn)
		conn.commit()

	numPrepend = 1
	while True:

		print "mux_255: " + str(mux_255)
		pfx = num2pfx[255]
		assert mux_255 in MUX_NAMES
		pfx.set_num_prepend1(numPrepend,mux_255)
		pfx.up()

		soft_reset(num2pfx)
		wait_cmd(1800)

		for num in PREFIX_RANGE:
			populateDB(c,num,opts.refasn)
			conn.commit()
		
		numPrepend += 1
		


def soft_reset(num2pfx): # {{{
	tstamp = int(time.time())
	tstamp = tstamp / opts.sleep
	tstamp = tstamp * opts.sleep
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

