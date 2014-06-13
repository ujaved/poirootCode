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
from helper import create_parser, mkdir_p, Prefix, ASN, getFilteredPath,VP_Poison1
import sqlite3
from operator import itemgetter
from collections import defaultdict
import traceback, signal


PREFIX_RANGE = [241,243,245,247,249]
RIOT_ASN = 47065
VP_NOT_SEEN_THRESH = 2
NUM_FTR = 7
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
FTR_INTERVAL = 11*60
START_TIME = int(time.time())


class TR_path_object(object): # {{{

	def __init__(self, unix_time, filpath, path_str, hops_str,feed,mux,update):
		self.unix_time = unix_time
		self.filpath = filpath
		self.path_str = path_str
		self.hops_str = hops_str
		self.feed = feed
		self.mux = mux
		self.update = update


def printStack(sig,frame):

	f=open('stack_trace.txt', 'w')
	f.write(traceback.print_stack(frame))
	f.flush()

def getNextVPToBePoisoned(num,VPBeingPoisoned):

	nextVP_idx = 0
	for v in pfx2VP[num]:
		if v==VPBeingPoisoned:
			nextVP_idx = pfx2VP[num].index(VPBeingPoisoned)+1
			break
		
	if nextVP_idx==0 or nextVP_idx >= len(pfx2VP[num]):
		#VPBeingPoisoned wasn't seen, or vp's have been exhausted: go back for any missed vps
		for v in pfx2VP[num]:
			if v.rv in pfx2VPAlreadyPoisoned[num]:
				continue
			nextVP_idx = pfx2VP[num].index(v)
			break

	if nextVP_idx >= len(pfx2VP[num]):
		return None
	return pfx2VP[num][nextVP_idx]
	
			

def dealWithPathExhaustion(num):

	while ((len(pfx2VPBeingPoisoned[num].PoisonQueue)==0) or (pfx2VPBeingPoisoned[num].rv in pfx2VPAlreadyPoisoned[num]) \
		       or (pfx2PoisVPNotSeenCount[num]>=VP_NOT_SEEN_THRESH) or (pfx2VPBeingPoisoned[num].vp_asn in pfx2VPASNAlreadyDone[num])):

		if pfx2PoisVPNotSeenCount[num] > 0 and pfx2PoisVPNotSeenCount[num] < VP_NOT_SEEN_THRESH:
			break
		print pfx2VPBeingPoisoned[num]
		pfx2VPAlreadyPoisoned[num].add(pfx2VPBeingPoisoned[num].rv)
		pfx2VPASNAlreadyDone[num].add(pfx2VPBeingPoisoned[num].vp_asn)
		pfx2VPBeingPoisoned[num] = getNextVPToBePoisoned(num,pfx2VPBeingPoisoned[num])
		
		if pfx2PoisVPNotSeenCount[num]>=VP_NOT_SEEN_THRESH:
			pfx2PoisVPNotSeenCount[num] = 0

		if pfx2VPBeingPoisoned[num] is None:
			print pfx2VPBeingPoisoned[num]
			break
		
	print pfx2VPBeingPoisoned[num]

def getNextPoisoning(num,poison_round):

	print "------------------"
	print "getNextPoisoning"
	if (poison_round%SENT_ROUND == 0 and sentinel_just_used is False) or pfx2VPBeingPoisoned[num] is None:
		return set([RIOT_ASN])
        #if poisonIdx is the first AS (VP AS), we don't wanna poison that; move on to next VP
	dealWithPathExhaustion(num)
	
	#if cur path is empty, means we have exhausted this level of poisoning, move on to the next level

	tup = pfx2VPBeingPoisoned[num].getPoisonList(pfx2PoisVPNotSeenCount[num])
	if ((not pfx2VPBeingPoisoned[num].cur_path) \
		       or (pfx2VPBeingPoisoned[num].PoisonNoEffect==True)):
		pfx2VPBeingPoisoned[num].cur_path = tup[1]
		pfx2VPBeingPoisoned[num].prev_path = ""
		if pfx2VPBeingPoisoned[num].PoisonNoEffect==True:
			pfx2VPBeingPoisoned[num].PoisonNoEffect = False

	if pfx2PoisVPNotSeenCount[num]==0:
		return tup[0]
	else:
		return tup

def populateDB(c,num,poison_round,vpPoisoned):

	pfx = '184.164.' + str(num) + '.0/24'

	print "---------------------------------"
	print "populateDB"
	print "time: " + str(int(time.time()))
	print "prefix: " + str(pfx)
	print "poison_round: " + str(poison_round)
	print "status: " + str(status)
	
	print "vpPoisoned: " + vpPoisoned

	poison_str = ""
	for p in pfx2PoisonList[num]:
		poison_str += (str(p) + " ")
	
	curVP = dict()
	tstamp = int(time.time())

	vpPois_seen = False
    
	if poison_round==last_base_round:
		pfx2VP[num] = []

	mux = MUX_NAMES[PREFIX_RANGE.index(num)]
	
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
				if update.time < tstamp-(40*60):
					continue
				if str(rv) in num2VPseen[num]:
					prev_upd = num2VPseen[num][str(rv)]
					if update.time<=prev_upd.time:
						continue

			if str(rv)==vpPoisoned:
				vpPois_seen = True

			curVP[str(rv)] = update
			unix_time = update.time

			if str(rv) in num2VPseen[num]:
				prev_update = num2VPseen[num][str(rv)]
			else:
				prev_update = None

			if (not update.path) is False:
				path = ""
				for asn in update.path:
					path += (str(asn) + " ")
				path = path.split()
				tup = getFilteredPath(path,feed)
				if tup is None:
					update.path = []
				else:
					filpath = tup[0]
					mux = tup[1]

					if num==240 or num==241: #CLEMSON
						vPoint = VP_Poison1(pfx,filpath,feed,mux,str(rv),5)
					else:
						vPoint = VP_Poison1(pfx,filpath,feed,mux,str(rv),4)
					if poison_round==last_base_round:
						pfx2VP[num].append(vPoint)
						if poison_round==0:
							pfx2VPBeingPoisoned[num] = pfx2VP[num][0]
					else:
						if str(rv)==vpPoisoned:
							pfx2VPBeingPoisoned[num].prev_path = pfx2VPBeingPoisoned[num].cur_path
							pfx2VPBeingPoisoned[num].cur_path = filpath

							if pfx2VPBeingPoisoned[num].cur_path==pfx2VPBeingPoisoned[num].prev_path:
								pfx2VPBeingPoisoned[num].PoisonNoEffect = True
							else:
								#potentially some new ASes in the new path
								pfx2VPBeingPoisoned[num].addStuff2PoisonQueue()
								

			if not update.path and str(rv)==vpPoisoned:
				pfx2VPBeingPoisoned[num].prev_path = pfx2VPBeingPoisoned[num].cur_path
				pfx2VPBeingPoisoned[num].cur_path = []
		    
			if not update.path:
				update.path = [0]
			if not update.hops:
				update.hops = [0]

			prev_path_str = ""
			if prev_update is not None:
				if not prev_update.path:
					prev_update.path = [0]
				for n in prev_update.path:
					prev_path_str += (str(n) + " ")
                
            
			path_str = ""
			for n in update.path:
				path_str += (str(n) + " ")
			hops_str = ""
			for n in update.hops:
				hops_str += (str(n) + " ")


			if status==SENTINEL:
				c.execute('insert into ASGraph values (?,?,?,?,?,?,?,?,?,?,?,?,?)', \
					  (pfx, unix_time, last_poison_time,poison_round, str(mux), "", \
					   feed, path_str, hops_str, prev_path_str, str(rv),0))              
			else:
				thisVPoisoned = 0
				if str(rv)==vpPoisoned:
					thisVPoisoned = 1
				c.execute('insert into ASGraph values (?,?,?,?,?,?,?,?,?,?,?,?)', \
					  (pfx, unix_time,last_poison_time,poison_round,str(mux), \
                                           poison_str,feed,path_str,hops_str,prev_path_str,str(rv),thisVPoisoned))


	print "poisoned VP seen: " + str(vpPois_seen)
	if vpPois_seen is True:
		pfx2PoisVPNotSeenCount[num] = 0
	elif vpPois_seen is False and status==TEST:
		if vpPois_seen_prevTR[num] is True:
			print "poisoned VP not seen has a previous traceroute" 
			pfx2VPBeingPoisoned[num].prev_path = pfx2VPBeingPoisoned[num].cur_path
			pfx2VPBeingPoisoned[num].cur_path = vpPois_TR_path[num].filpath   #this path might be empty
			
			if pfx2VPBeingPoisoned[num].cur_path==pfx2VPBeingPoisoned[num].prev_path:
				pfx2VPBeingPoisoned[num].PoisonNoEffect = True
			else:
				#potentially some new ASes in the new path
				pfx2VPBeingPoisoned[num].addStuff2PoisonQueue()


			curVP[vpPoisoned] = vpPois_TR_path[num].update
			if vpPoisoned in num2VPseen[num]:
				prev_update = num2VPseen[num][vpPoisoned]
			else:
				prev_update = None
			
			prev_path_str = ""
			if prev_update is not None:
				if not prev_update.path:
					prev_update.path = [0]
				for n in prev_update.path:
					prev_path_str += (str(n) + " ")
				
                        c.execute('insert into ASGraph values (?,?,?,?,?,?,?,?,?,?,?,?,?)', \
				   (pfx, vpPois_TR_path[num].unix_time,last_poison_time,poison_round,status,str(vpPois_TR_path[num].mux), \
				    poison_str,vpPois_TR_path[num].feed,vpPois_TR_path[num].path_str,vpPois_TR_path[num].hops_str, \
				    prev_path_str,vpPoisoned,1))
		else:
			pfx2PoisVPNotSeenCount[num] += 1
	
	num2VPseen[num].clear()
	for vp in curVP:
		num2VPseen[num][vp] = curVP[vp]
	sys.stdout.flush()


def populateDB_ftr(c,num,poison_round,vpPoisoned):

	pfx = '184.164.' + str(num) + '.0/24'

	print "---------------------------------"
	print "populateDB_ftr"
	print "time: " + str(int(time.time()))
	print "prefix: " + str(pfx)
	
	tstamp = int(time.time())

	mux = MUX_NAMES[PREFIX_RANGE.index(num)]
	
	for feed in feeds:	
		locs = pfxToLoc[feed][pfx]
		for rv in locs:
			update = api.get_path(feed, pfx, rv, 'last_update')
			if feed=='rv':
				continue
				
			unix_time = update.time

			if (not update.path) is False:
				path = ""
				for asn in update.path:
					path += (str(asn) + " ")
				path = path.split()
				tup = getFilteredPath(path,feed)
				if tup is None:
					update.path = []
				else:
					filpath = tup[0]

		    
			if not update.path:
				update.path = [0]
				filpath = []
			if not update.hops:
				update.hops = [0]
            
			path_str = ""
			for n in update.path:
				path_str += (str(n) + " ")
			hops_str = ""
			for n in update.hops:
				hops_str += (str(n) + " ")

			c.execute('insert into TRGraph values (?,?,?,?,?,?,?,?,?)', \
				   (pfx, unix_time, poison_round,last_poison_time, feed, path_str, hops_str, str(rv),num_ftr_query))

			if str(rv)==vpPoisoned and num_ftr_query >=4:
				#confident that poisoning effect has been seen
				vpPois_TR_path[num].unix_time = unix_time
				vpPois_TR_path[num].filpath = filpath
				vpPois_TR_path[num].path_str = path_str
				vpPois_TR_path[num].hops_str = hops_str
				vpPois_TR_path[num].feed = feed
				vpPois_TR_path[num].mux = mux
				vpPois_TR_path[num].update = update

				vpPois_seen_prevTR[num] = True

			elif str(rv)==vpPoisoned:
				vpPois_seen_prevTR[num] = False
				
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

	c.execute("create table if not exists ASGraph (prefix text, unix_time int, poison_time int, poison_round int, \
                   mux_seen text, poisonedASes text, feed text, observedPath text, ipPath text, prevPath text, vpoint text, thisVPoisoned int)")
	c.execute("create index idx_pfx on ASGraph(prefix)")
	c.execute("create index idx_asn on ASGraph(poisonedASes)")
	c.execute("create index idx_pfx_path on ASGraph(prefix,observedPath)")
	c.execute("create index idx_poison on ASGraph(poison_round)")
	c.execute("create index idx_vpoint on ASGraph(vpoint)")

	c.execute("create table if not exists TRGraph (prefix text, unix_time int, poison_round int, poison_time int, feed text, observedPath text, ipPath text, \
                   vpoint text, num_ftr_query int)")
	c.execute("create index idx_pfx_tr on TRGraph(prefix)")
	c.execute("create index idx_vpoint_tr on TRGraph(vpoint)")
			     

	return c
				
def main():

	global opts 
	parser = create_parser()
	opts, _args = parser.parse_args()
	
	if opts.database is None:
		parser.parse_args(['-h'])

	opts.output = opts.output + str(datetime.now())
	resource.setrlimit(resource.RLIMIT_AS, (2147483648L, 2147483648L))

	Pyro4.config.HMAC_KEY = 'choffnes-cunha-javed-owning'
	sys.excepthook = Pyro4.util.excepthook
	ns = Pyro4.naming.locateNS('128.208.4.106', 51555)
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

	global pfx2VPAlreadyPoisoned
	pfx2VPAlreadyPoisoned = dict()
	for num in PREFIX_RANGE:
		pfx2VPAlreadyPoisoned[num] = set()

	global pfx2VPASNAlreadyDone
	pfx2VPASNAlreadyDone = dict()
	for num in PREFIX_RANGE:
		pfx2VPASNAlreadyDone[num] = set()

	global pfx2PoisVPNotSeenCount
	pfx2PoisVPNotSeenCount = dict()
	for num in PREFIX_RANGE:
		pfx2PoisVPNotSeenCount[num] = 0

	global vpPois_TR_path
	vpPois_TR_path = dict()
	for num in PREFIX_RANGE:
		vpPois_TR_path[num] = TR_path_object('','','','','','','')

	global vpPois_seen_prevTR
	vpPois_seen_prevTR = dict()
	for num in PREFIX_RANGE:
		vpPois_seen_prevTR[num] = False

	#signal.signal(signal.SIGUSR1, lambda sig, stack: traceback.print_stack(stack))

	signal.signal(signal.SIGUSR1, printStack)
	
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
	global last_poison_time
	last_poison_time = int(time.time())
	wait_cmd(POISON_INTERVAL)

	poisonRound = 0
	global num_ftr_query
	num_ftr_query = NUM_FTR
	global last_base_round
	last_base_round = 0
 		
	while True:
		if num_ftr_query>=NUM_FTR:
			for num in PREFIX_RANGE:				
				populateDB(c,num,poisonRound,pfx2VPBeingPoisoned[num].rv)
				conn.commit()

				print "VPNotSeenCount: " + str(pfx2PoisVPNotSeenCount[num])
				'''
				print "vantage points:"
				for v in pfx2VP[num]:
					print v
				'''

				print "vp's already poisoned: " + str(pfx2VPAlreadyPoisoned[num])
				print "vp ASes already done: " + str(pfx2VPASNAlreadyDone[num])
				pfx2PoisonList[num] = getNextPoisoning(num,poisonRound)
				print "poison_list: " + str(pfx2PoisonList[num])

				pfx = num2pfx[num]
				pfx.poisonList(list(pfx2PoisonList[num]))
			
				for mux in MUX_NAMES:
					if PREFIX_RANGE.index(num)==MUX_NAMES.index(mux):
						pfx.update_route_map1(mux, True)
					else:
						pfx.update_route_map1(mux,False)
                                         
				pfx.up()

			poisonRound += 1
			
			sys.stdout.flush()
			soft_reset(num2pfx)
			last_poison_time = int(time.time())
			num_ftr_query = 1
			wait_cmd(FTR_INTERVAL)
			
		else:
			for num in PREFIX_RANGE:
				populateDB_ftr(c,num,poisonRound,pfx2VPBeingPoisoned[num].rv)
				conn.commit()
			num_ftr_query += 1
			wait_cmd(FTR_INTERVAL)
	


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

