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

PREFIX_RANGE = [248,249]
RIOT_ASN = 47065

def getPoisonings(c, num):

	if num==248:
		return

	print "---------------------------------------"
	pfx = '184.164.' + str(num) + '.0/24'
	sentinel_pfx = '184.164.248.0/24'

	vpoints = []
	c.execute("select distinct vpoint from ASGraph where prefix=?", (pfx,))
	for row in c:
		vpoints.append(row[0])

	vidx = 0
	for idx, vp in enumerate(vpoints):
		if vp == num2VPoint[num]:
			vidx = idx+1
			if vidx >= len(vpoints):
				ASPoisoned.clear()
				vidx = 0
	vpoint_to_poison = vpoints[vidx]
	print num2VPoint[num]
	print vpoint_to_poison
	num2VPoint[num] = vpoint_to_poison

	c.execute("select filteredASPath from ASGraph where prefix=? and vpoint=? order by poison_round DESC limit 1", (sentinel_pfx,vpoint_to_poison))
	for row in c:
		sentinel_path = row[0].split()

	print sentinel_path
	c.execute("select poisonedAS,thisVPoisoned from ASGraph where prefix=? and vpoint=? \
                   order by poison_round DESC", (pfx,vpoint_to_poison))

	prev_poison = RIOT_ASN
	for row in c:
		if row[1] == 1:
			prev_poison = row[0]
			break

	print prev_poison
	asn_to_poison = 0
	p = list(sentinel_path)
	p.reverse()
	if prev_poison==RIOT_ASN:
		asn_to_poison = int(p[5])

	else:
		prev_asn = 0
		for asn in sentinel_path:
			if int(asn)==prev_poison:
				asn_to_poison = prev_asn
				break
			prev_asn = int(asn)

	if asn_to_poison==0:
		asn_to_poison = int(p[5])
	print asn_to_poison
	if asn_to_poison in ASPoisoned:
		print "already poisoned"
		return False
	ASPoisoned[asn_to_poison] = 1
	num2PoisonSet[num] = set()
	num2PoisonSet[num].add(asn_to_poison)
	
	sys.stdout.flush()
	return True
	
	
def populateDB(c, num):
	pfx = '184.164.' + str(num) + '.0/24'
	for feed in feeds:
		locs = pfxToLoc[feed][pfx]
		for rv in locs:
			update = api.get_path(feed, pfx, rv, 'last_update')
			unix_time = update.time
			dtime = str(datetime.fromtimestamp(update.time))
			prev_asn = 0
			opath = ""

			if not update.path:
				update.path = [0]

			#removing duplicates from the path in case of 'ftr'
			for asn in update.path:
				if (asn==prev_asn or asn==0) and feed=='ftr':
					continue
			        opath = opath + " " + str(asn)
				prev_asn = asn
			opath.strip()

			poisonedAS = iter(num2PoisonSet[num]).next()

			thisVPoisoned = 0
			'''
			if num==249:
				c.execute("select filteredASPath from ASGraph where prefix='184.164.248.0/24' and vpoint=? order by poison_round DESC limit 1", (str(rv),))
				for row in c:
					sentinel_path = row[0].split()
				p = list(sentinel_path)
				if str(poisonedAS) in p and poisonedAS != RIOT_ASN:
                                #if str(rv)==num2VPoint[num]:
					thisVPoisoned = 1
			'''
			if str(rv)==num2VPoint[num]:
				thisVPoisoned = 1
			c.execute('insert into ASGraph values (?,?,?,?,?,?,?,?,?,?)', \
					  (pfx, unix_time, dtime, \
					   poisonRound, poisonedAS,feed, str(update.path),opath,rv,thisVPoisoned))
		

def main():

	global opts 
	parser = create_parser()
	opts, _args = parser.parse_args()

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

	db_file = opts.database + str(datetime.now())
	#db_file = "../data/mike_data/mike.db2012-04-25 00:08:59.710008"
	conn = sqlite3.connect(db_file)
	c = conn.cursor()


	c.execute("create table if not exists ASGraph (prefix text, unix_time int, dtime text, \
                   poison_round int, poisonedAS int, feed text, observedPath text, filteredASPath, vpoint text, thisVPoisoned int)")
	c.execute("create index idx_pfx on ASGraph(prefix)")
	c.execute("create index idx_asn on ASGraph(poisonedAS)")
	c.execute("create index idx_pfx_path on ASGraph(prefix,observedPath)")
	c.execute("create index idx_pfx_filpath on ASGraph(prefix,filteredASPath)")
	c.execute("create index idx_prepend on ASGraph(poison_round)")
	c.execute("create index idx_vpoint on ASGraph(vpoint)")

	num2pfx = dict()
	for num in PREFIX_RANGE:
		num2pfx[num] = Prefix(num, 47065, "announced")

        
	global feeds
	#feeds = ['rv', 'ftr']
	feeds = ['rv']

	global num2PoisonSet
	num2PoisonSet = dict()
	for num in PREFIX_RANGE:
		num2PoisonSet[num] = set()
		num2PoisonSet[num].add(47065)

	global num2VPoint
	num2VPoint = dict()
	for num in PREFIX_RANGE:
		num2VPoint[num] = "0"

	global ASPoisoned
	ASPoisoned = dict()


	for num in PREFIX_RANGE:
		pfx = num2pfx[num]
		pfx.poisonList([47065])
		pfx.up()

	soft_reset(num2pfx)
	wait_cmd(1800)
	
	
	global poisonRound
	poisonRound = 0
 
	global pfxToLoc
	pfxToLoc = dict()
	for feed in feeds:
		pfxToLoc[feed] = api.get_prefix_to_locations(feed)
		
	while True:
		
		for num in PREFIX_RANGE:
			populateDB(c,num)
			conn.commit()

		#wait_cmd(1800)
		for num in PREFIX_RANGE:
			pfx = num2pfx[num]
			f = False
			while f is False:
				f = getPoisonings(c,num)
			pfx.poisonList(list(num2PoisonSet[num]))
			pfx.up()

		soft_reset(num2pfx)
		
		poisonRound += 1
		
		wait_cmd(3600)


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

