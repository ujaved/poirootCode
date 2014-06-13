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

PREFIX_RANGE = range(241,250,2)
RIOT_ASN = 47065

def getPoisonings(c, num):

	print num2PoisonRound[num]
	pfx = '184.164.' + str(num) + '.0/24'
	logging.info('prefix_getPoisonings 184.164.%d.0/24 bfs:%d poison_round:%d', num, num2BFSLevel[num],num2PoisonRound[num])
	print pfx
	print "------------------------------------"
	c.execute("select observedPath from ASGraph where prefix=? and bfs_level=? and poison_round=? group by observedPath",
		  (pfx,num2BFSLevel[num],num2PoisonRound[num]))

	paths = list()
	for row in c:
		as_list_temp = row[0].split()
		as_list = []
		prev_asn = ""
		for asn in as_list_temp:
			if asn==prev_asn or prev_asn==str(RIOT_ASN):
				continue
			as_list.append(asn)
			prev_asn = asn
		paths.append(as_list)

	asCount = dict()

	for p in paths:
		p.reverse()
		idx = num2startPoisIdx[num] + num2BFSLevel[num] -1
		if idx >= len(p):
			continue
		asn = p[idx]
		if asn not in asCount:
			asCount[asn] = 1
		else:
			asCount[asn] += 1


	for asn in asCount:
		if asCount[asn] < 0 or int(asn) in opts.blacklist:   #terminate the search
			continue
		found = False
		for c in num2PoisonCandidates[num]:
			if c.name==asn and c.poisoned:     #this shouldn't happen but checking anyway
				found = True
				c.path_count.append(asCount[asn])
				break
			if c.name==asn:              #unclear what to do here
				found = True
				c.path_count.append(asCount[asn])
				break
			
                if not found:
			num2PoisonCandidates[num].append(ASN(asn,num2BFSLevel[num], 
							     [asCount[asn]], False))

	#if no new paths for an asn in the candidate set, means that asn is filtering so poisoning itself
	a = []
	for c in num2PoisonCandidates[num]:
		if c.name in asCount or c.poisoned is True:
			a.append(c)
	num2PoisonCandidates[num] = a

	#if num2PoisonCandidates[num] has all members poisoned at this stage, we've exhausted this level
	
	maxPathCount = 0
	toPoison = 47065
	toPoisonFound = False
	for c in num2PoisonCandidates[num]:
		print c
		if c.path_count[-1] >= maxPathCount and not c.poisoned:   #check latest path count
			maxPathCount = c.path_count[-1]
			toPoisonFound = True
			toPoison = int(c.name) 

	for c in num2PoisonCandidates[num]:
		logging.info('poisonCandidate: %s', c)

        if not toPoisonFound:
		num2PoisonCandidates[num][:] = []
		num2BFSLevel[num] += 1
		# withdraw all poisonings and move to the next level
		num2PoisonSet[num] = set()
		num2PoisonSet[num].add(47065)
		return

	# mark the toPoison AS poisoned
	for c in num2PoisonCandidates[num]:
		if int(c.name) == toPoison:
			c.poisoned = True
			break

	# if 47065 is the only AS in the poison set, it means we're poisoning free right now
	if 47065 in num2PoisonSet[num]:
		num2PoisonSet[num] = set()

	num2PoisonSet[num].add(toPoison)
	po = ""
        for asn in num2PoisonSet[num]:
		po = po + " " + str(asn)
	logging.info('prefix_poisonSet: %s', po)
	print num2PoisonSet[num]
		

def populateDB(c, num):
	pfx = '184.164.' + str(num) + '.0/24'
	poisonList = ""
	for p in num2PoisonSet[num]:
		poisonList = poisonList + " " + str(p)
	poisonList.strip()
	for feed in feeds:
		as_path = dict()
		as_edge = dict()
		locs = pfxToLoc[feed][pfx]
		for rv in locs:
			update = api.get_path(feed, pfx, rv, 'last_update')
			unix_time = update.time
			prev_asn = 0
			opath = ""

			#discarding paths that are unreachable
			if not update.path:
				continue

			if (update.path[-1] != RIOT_ASN) and (update.path[-1] != 47065):
				continue

			#removing duplicates from the path in case of 'ftr'
			for asn in update.path:
				if (asn==prev_asn or asn==0) and feed=='ftr':
					continue
			        opath = opath + " " + str(asn)
				prev_asn = asn
			opath.strip()
			if len(opath.split()) < 3:
				continue
			if opath in as_path:
				continue
			else:
				as_path[opath] = 1
			prev_asn = 0
			for asn in update.path:
				if asn==47065 or asn==RIOT_ASN:
					break
				if prev_asn==asn or asn==0:
					continue
				
				k = str(asn)+ " " +str(prev_asn)
				if k in as_edge:
					prev_asn = asn
					continue
				else:
					as_edge[k] = 1
				dtime = str(datetime.fromtimestamp(update.time))
				c.execute('insert into ASGraph values (?,?,?,?,?,?,?,?,?,?,?,?)', \
						  (pfx, unix_time, dtime, \
							   asn, prev_asn, num2BFSLevel[num], num2PoisonRound[num], startTime, poisonList, feed, opath,rv))
				
				prev_asn = asn
	#conn.commit()
		

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

	#sys.stdout = open(opts.output, 'w')
	#sys.stderr = sys.stdout

	global num2PoisonCandidates
	num2PoisonCandidates = dict()
	for num in PREFIX_RANGE:
		num2PoisonCandidates[num] = list()

	global num2commonAS
	num2commonAS = dict()
	num2commonAS[241] = [101,73]
	num2commonAS[243] = [6939,2381]
	num2commonAS[245] = [174,2637]
	num2commonAS[247] = [7922,88]
	num2commonAS[249] = [209,2722,12148]

	global num2startPoisIdx
	num2startPoisIdx = dict()
	num2startPoisIdx[241] = 3
	num2startPoisIdx[243] = 2
	num2startPoisIdx[245] = 2
	num2startPoisIdx[247] = 2
	num2startPoisIdx[249] = 3

	conn = sqlite3.connect('data/imc3.db')
	c = conn.cursor()

	global feeds
	feeds = ['rv', 'ftr']

	global num2PoisonSet
	num2PoisonSet = dict()
	for num in PREFIX_RANGE:
		num2PoisonSet[num] = set()
		num2PoisonSet[num].add(47065)
	
	
	global num2BFSLevel
	num2BFSLevel = dict()
	for num in PREFIX_RANGE:
		num2BFSLevel[num] = 1 
	global num2PoisonRound
	num2PoisonRound = dict()
	for num in PREFIX_RANGE:
		num2PoisonRound[num] = 1 
	global pfxToLoc
	pfxToLoc = dict()
	for feed in feeds:
		pfxToLoc[feed] = api.get_prefix_to_locations(feed)


	i = 1
	while (i < 5):
		for num in PREFIX_RANGE:
			getPoisonings(c,num)

		for num in PREFIX_RANGE:
			num2PoisonRound[num] += 1
		
		i += 1
	

	'''
	while True:
		for num in PREFIX_RANGE:
			populateDB(c,num)
			conn.commit()

		#wait_cmd(1800)
		for num in PREFIX_RANGE:
			pfx = num2pfx[num]
			getPoisonings(c,num)
			pfx.poisonList(list(num2PoisonSet[num]))
			pfx.up()

		soft_reset(num2pfx)
		
		for num in PREFIX_RANGE:
			num2PoisonRound[num] += 1

		#for num in PREFIX_RANGE:
		#	logging.info('prefix_getPoisonings 184.164.%d.0/24 %s %s', num, num2PoisonSet[num])
		
		wait_cmd(1800)
	'''

	'''
	while True:

		for num in PREFIX_RANGE:
			pfx = num2pfx[num]
			getPoisonings(c,num)
			pfx.poisonList(list(num2PoisonSet[num]))
			pfx.up()

		soft_reset(num2pfx)

		for num in PREFIX_RANGE:
			num2PoisonRound[num] += 1

		#for num in PREFIX_RANGE:
		#	logging.info('prefix_getPoisonings 184.164.%d.0/24 %s %s', num, num2PoisonSet[num])
 
		wait_cmd(1800)

		for num in PREFIX_RANGE:
			populateDB(c,num)
			conn.commit()
         
	'''


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

