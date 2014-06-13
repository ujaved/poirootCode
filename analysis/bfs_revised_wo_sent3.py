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


def getNextVPToBePoisoned(num,VPBeingPoisoned):

	nextVP_idx = 0
	for v in pfx2VP[num]:
		if v==VPBeingPoisoned:
			nextVP_idx = pfx2VP[num].index(VPBeingPoisoned)+1
			break
		
	if nextVP_idx==0:
		#VPBeingPoisoned wasn't seen.
		for v in pfx2VP[num]:
			if v.rv in pfx2VPAlreadyPoisoned[num]:
				continue
			nextVP_idx = pfx2VP[num].index(v)
			break
		
	return pfx2VP[num][nextVP_idx]
	
			

def dealWithPathExhaustion(num):

	while ((pfx2VPBeingPoisoned[num].poisonIdx==0) or (pfx2VPBeingPoisoned[num].rv in pfx2VPAlreadyPoisoned[num]) \
		       or (pfx2PoisVPNotSeenCount[num]>=2)):
		print pfx2VPBeingPoisoned[num]
		pfx2VPAlreadyPoisoned[num].add(pfx2VPBeingPoisoned[num].rv)
		pfx2VPBeingPoisoned[num] = getNextVPToBePoisoned(num,pfx2VPBeingPoisoned[num])
		
		if pfx2PoisVPNotSeenCount[num]>=2:
			pfx2PoisVPNotSeenCount[num] = 0
		
	print pfx2VPBeingPoisoned[num]

def getNextPoisoning(num,poison_round,sentinel_just_used):

	print "------------------"
	print "getNextPoisoning"
	if poison_round%SENT_ROUND == 0 and sentinel_just_used is False:
		return set([RIOT_ASN])
        #if poisonIdx is the first AS (VP AS), we don't wanna poison that; move on to next VP
	dealWithPathExhaustion(num)
	
	#if cur path is empty, means we have exhausted this level of poisoning, move on to the next level
	#also if the next AS is in the blacklist

	nextAS2BePoisoned = pfx2VPBeingPoisoned[num].getNextAS2BePoisoned()
	while ((not pfx2VPBeingPoisoned[num].cur_path) or (nextAS2BePoisoned in opts.blacklist) \
		       or (pfx2VPBeingPoisoned[num].numPoisonNoEffect>=2) or \
		       (pfx2VPBeingPoisoned[num].numPoisonNoEffect > 0 and pfx2PoisVPNotSeenCount[num] > 0) or \
		       (pfx2VPBeingPoisoned[num].poisonIdx>len(pfx2VPBeingPoisoned[num].cur_path)-pfx2VPBeingPoisoned[num].min_poison_idx)):

		pfx2VPBeingPoisoned[num].poisonIdx -= 1
		pfx2VPBeingPoisoned[num].cur_path = pfx2VPBeingPoisoned[num].orig_path
		pfx2VPBeingPoisoned[num].prev_path = ""
		pfx2VPBeingPoisoned[num].curPoisonings = []

		if pfx2VPBeingPoisoned[num].numPoisonNoEffect > 0 and pfx2PoisVPNotSeenCount[num] > 0:
			pfx2VPBeingPoisoned[num].numPoisonNoEffect = 0
			pfx2PoisVPNotSeenCount[num] = 0
			
		elif pfx2VPBeingPoisoned[num].numPoisonNoEffect > 0:
			pfx2VPBeingPoisoned[num].numPoisonNoEffect = 0
		
		dealWithPathExhaustion(num)
		nextAS2BePoisoned = pfx2VPBeingPoisoned[num].getNextAS2BePoisoned()

	return pfx2VPBeingPoisoned[num].getPoisonList()

def populateDB(c,num,poison_round,status,vpPoisoned):

	pfx = '184.164.' + str(num) + '.0/24'

	print "---------------------------------"
	print "populateDB"
	print "prefix: " + str(pfx)
	print "poison_round: " + str(poison_round)
	print "status: " + str(status)
	if status==TEST:
		print "vpPoisoned: " + vpPoisoned
	VPseen = num2VPseen[num]
	curVP = dict()
	tstamp = int(time.time())

	vpPois_seen = False
    
	if status==SENTINEL:
		pfx2VP[num] = []

	mux = MUX_NAMES[PREFIX_RANGE.index(num)]
	
	for feed in feeds:	
		locs = pfxToLoc[feed][pfx]
		for rv in reversed(list(locs)):
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
				if rv in VPseen:
					prev_upd = VPseen[rv]
					if update.time<=prev_upd.time:
						continue

			if str(rv)==vpPoisoned:
				vpPois_seen = True

			curVP[rv] = update
			unix_time = update.time		     

			if (not update.path) is False:
				path = ""
				for asn in update.path:
					path += (str(asn) + " ")
				path = path.split()
				tup = getFilteredPath(path,feed)
				#or update.path[0] != tup[0][0]
				if tup is None:
					update.path = []
				else:
					filpath = tup[0]
					mux = tup[1]

					if num==240: #CLEMSON
						vPoint = VP_Poison(pfx,filpath,feed,mux,str(rv),5)
					else:
						vPoint = VP_Poison(pfx,filpath,feed,mux,str(rv),4)
					if status==SENTINEL:
						if poison_round==0:
							pfx2VP[num].append(vPoint)
							#pfx2VPOrder[num].append(vPoint)
							pfx2VPBeingPoisoned[num] = pfx2VP[num][0]
						else:
							if str(rv) != pfx2VPBeingPoisoned[num].rv: 
								pfx2VP[num].append(vPoint)
							else:
								pfx2VP[num].append(pfx2VPBeingPoisoned[num])
					else:
						if str(rv)==vpPoisoned:
							pfx2VPBeingPoisoned[num].prev_path = pfx2VPBeingPoisoned[num].cur_path
							pfx2VPBeingPoisoned[num].cur_path = filpath

							if pfx2VPBeingPoisoned[num].cur_path==pfx2VPBeingPoisoned[num].prev_path:
								pfx2VPBeingPoisoned[num].numPoisonNoEffect += 1
							else:
								if pfx2VPBeingPoisoned[num].numPoisonNoEffect > 0:
									pfx2VPBeingPoisoned[num].numPoisonNoEffect = 0
								

			if not update.path and str(rv)==vpPoisoned:
				pfx2VPBeingPoisoned[num].prev_path = pfx2VPBeingPoisoned[num].cur_path
				pfx2VPBeingPoisoned[num].cur_path = []
		    
			if not update.path:
				update.path = [0]
			if not update.hops:
				update.hops = [0]
                
            
			path_str = ""
			for n in update.path:
				path_str += (str(n) + " ")
			hops_str = ""
			for n in update.hops:
				hops_str += (str(n) + " ")

			prev_path_str = ""
			for n in pfx2VPBeingPoisoned[num].prev_path:
				prev_path_str += (str(n) + " ")

			if status==SENTINEL:
				c.execute('insert into ASGraph values (?,?,?,?,?,?,?,?,?,?,?,?)', \
					  (pfx, unix_time, poison_round, status, str(mux), "", \
					   feed, path_str, hops_str, prev_path_str, str(rv),0))              
			else:
				thisVPoisoned = 0
				if str(rv)==vpPoisoned:
					thisVPoisoned = 1
				poison_str = ""
				for p in pfx2PoisonList[num]:
					poison_str += (str(p) + " ")
				c.execute('insert into ASGraph values (?,?,?,?,?,?,?,?,?,?,?,?)', \
					  (pfx, unix_time,poison_round,status,str(mux), \
                                           poison_str,feed,path_str,hops_str,prev_path_str,str(rv),thisVPoisoned))


	print "poisoned VP seen: " + str(vpPois_seen)
	if vpPois_seen is True:
		pfx2PoisVPNotSeenCount[num] = 0
	elif vpPois_seen is False and status==TEST:
		pfx2PoisVPNotSeenCount[num] += 1
		

	'''
	if status==SENTINEL:
		vpOrder = []
		vpFound = [False]*len(pfx2VP[num])
		for v in pfx2VPOrder[num]:
			for w in pfx2VP[num]:
				if v==w:
					vpOrder.append(w)
					vpFound[pfx2VP[num].index(w)] = True
					break
		for i in range(0,len(vpFound)):
			if vpFound[i] is False:
				vpOrder.append(pfx2VP[num][i])
		pfx2VP[num] = vpOrder
	'''
		
	VPseen.clear()
	for vp in curVP:
		VPseen[vp] = curVP[vp]
	sys.stdout.flush()


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

def create_db():

	global conn
	db_file = opts.database + str(datetime.now())
	conn = sqlite3.connect(db_file)
	c = conn.cursor()

	#observedPath is the raw path that you see both feeds: lists if ASs from ftr and list of ASes from rv (W in case of withdrawn rv path)
	#poison_round is the poison round in the script
	#status: SENTINEL(0) or TEST(1)
	#mux_seen is the mux selected for this prefix

	c.execute("create table if not exists ASGraph (prefix text, unix_time int, poison_round int, status int, \
                   mux_seen text, poisonedASes text, feed text, observedPath text, ipPath text, prevPath text, vpoint text, thisVPoisoned int)")
	c.execute("create index idx_pfx on ASGraph(prefix)")
	c.execute("create index idx_asn on ASGraph(poisonedASes)")
	c.execute("create index idx_pfx_path on ASGraph(prefix,observedPath)")
	c.execute("create index idx_poison on ASGraph(poison_round)")
	c.execute("create index idx_vpoint on ASGraph(vpoint)")
			     

	return c

PREFIX_RANGE = [240,242,244,246,248]
RIOT_ASN = 47065
SENTINEL = 0
TEST = 1
SENT_ROUND = 10
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

POISON_INTERVAL = 1860
POISON_INTERVAL_2 = 600
START_TIME = int(time.time())
				
def main():

	global opts 
	parser = create_parser()
	opts, _args = parser.parse_args()
	
	if opts.database is None or opts.blacklist is None:
		parser.parse_args(['-h'])

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

	
	sys.stdout = open(opts.output, 'w')
	sys.stderr = sys.stdout
	
	global conn
	c = create_db()
	
 	global feeds
	feeds = ['ftr', 'rv', 'rtr']
	num2pfx = dict()

	global pfxToLoc
	pfxToLoc = dict()
	for feed in feeds:
		pfxToLoc[feed] = api.get_prefix_to_locations(feed)
			

	global num2VPseen
	num2VPseen = dict()
	for num in PREFIX_RANGE:
		num2VPseen[num] = dict()

	global pfx2PoisonList
	pfx2PoisonList = dict()
	for num in PREFIX_RANGE:
		pfx2PoisonList[num] = list()
		pfx2PoisonList[num].append(RIOT_ASN)

	global pfx2VPBeingPoisoned
	pfx2VPBeingPoisoned = dict()

	global pfx2VP
	pfx2VP = defaultdict(list)

	'''
	global pfx2VPOrder
	pfx2VPOrder = defaultdict(list)
	'''

	global pfx2VPAlreadyPoisoned
	pfx2VPAlreadyPoisoned = dict()
	for num in PREFIX_RANGE:
		pfx2VPAlreadyPoisoned[num] = set()

	global pfx2PoisVPNotSeenCount
	pfx2PoisVPNotSeenCount = dict()
	for num in PREFIX_RANGE:
		pfx2PoisVPNotSeenCount[num] = 0

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

	poisonRound = 0
	sent_used = True
 		
	while True:
		for num in PREFIX_RANGE:
			
			if poisonRound%SENT_ROUND==0 and sent_used is True:
				vpJustPoisoned = ""
				populateDB(c,num,poisonRound,SENTINEL,"")
			else:
				vpJustPoisoned = pfx2VPBeingPoisoned[num].rv
				populateDB(c,num,poisonRound,TEST,vpJustPoisoned)
			conn.commit()
			
			print "vantage points:"
			for v in pfx2VP[num]:
				print v

			print "vp's already poisoned: " + str(pfx2VPAlreadyPoisoned[num])
			pfx2PoisonList[num] = getNextPoisoning(num,poisonRound,sent_used)
			print "poison_list: " + str(pfx2PoisonList[num])
			print "sentinel used: " + str(sent_used)

			pfx = num2pfx[num]
			pfx.poisonList(list(pfx2PoisonList[num]))
			
			for mux in MUX_NAMES:
				if PREFIX_RANGE.index(num)==MUX_NAMES.index(mux):
					pfx.update_route_map1(mux, True)
				else:
					pfx.update_route_map1(mux,False)
                                         
			pfx.up()

		if poisonRound%SENT_ROUND != 0:
			poisonRound += 1
		else:
			if sent_used is False:
				#we just sent sentinels out
				sent_used = True
			else:
				sent_used = False
				poisonRound += 1
			
		sys.stdout.flush()
		soft_reset(num2pfx)
		wait_cmd(POISON_INTERVAL)
	


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

