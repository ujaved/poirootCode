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


def populateDB(c, num, muxesToPrepend, prependLengths, prepend_round, status):

	print "----------------------"
	print "prepend_round: " + str(prepend_round)
	print "muxesToPrepend: " + str(muxesToPrepend)
	print "prependLengths: " + str(prependLengths)
	print "status: " + str(status)
	pfx = '184.164.' + str(num) + '.0/24'
	print pfx
	VPseen = num2VPseen[num]
	curVP = dict()
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
			if feed=='ftr':
				if update.time < tstamp-(30*60):
					continue
				if rv in VPseen:
					prev_upd = VPseen[rv] 
					if update.time<=prev_upd.time:
						continue

			curVP[rv] = update

			unix_time = update.time

			if not update.path:
				update.path = [0]
			if not update.hops:
				update.hops = [0]
				

			mux = ''
			for m in muxASToName:
				if m in update.path:
					mux = muxASToName[m]
					break

			if len(mux)==0:
				continue

			path_str = ""
			for n in update.path:
				path_str += (str(n) + " ")
			hops_str = ""
			for n in update.hops:
				hops_str += (str(n) + " ")
			if status==SENTINEL:
				c.execute('insert into ASGraph values (?,?,?,?,?,?,?,?,?,?,?)', \
						  (pfx, unix_time, \
						   "", -1, prepend_round, status, str(mux), feed, path_str, hops_str,str(rv)))
			else:
				for m in muxesToPrepend:
					l = prependLengths[muxesToPrepend.index(m)]
					c.execute('insert into ASGraph values (?,?,?,?,?,?,?,?,?,?,?)', \
						  (pfx, unix_time, \
						   str(m), l, prepend_round, status, str(mux), feed, path_str, hops_str, str(rv)))

	VPseen.clear()
	for vp in curVP:
		VPseen[vp] = curVP[vp]
		
	sys.stdout.flush()


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

PREPEND_LEN = range(0,4)
PREPEND_INTERVAL = 2100
START_TIME = int(time.time())

def next(mask, max_prepend):

	#mask: mask that signifies which mux has what prepend length
	#max_prepend: max prepend length

	n = len(mask)
	i = 0
	while (i < n and mask[i]==max_prepend):
		mask[i] = 1

		i += 1

	if (i < n):
		mask[i] += 1
		return True

	return False
	
def announce_sentinel(pfx,mux):

	for m in MUX_NAMES:
		if m==mux:
			pfx.update_route_map1(m, True)
		else:
			pfx.update_route_map1(m,False)
	pfx.up()


def create_db():

	global conn
	conn = sqlite3.connect(opts.database + str(datetime.now()))
	c = conn.cursor()

	#observedPath is the raw path that you see both feeds: lists if ASs from ftr and list of ASes from rv (W in case of withdrawn rv path)
	#prepend_mux is one of the muxes where prependings are done; note that the prefix is announced only through these muxes
	#prepend_length is the prepend length for the prepend_mux
	#prepend_round is the prepend round in the script: prepend_muxes for the same prepend_round were perpended together
	#status: SENTINEL(0) or TEST(1)
	#mux_seen is the mux selected for this prefix

	c.execute("create table if not exists ASGraph (prefix text, unix_time int, \
                  prepend_mux text, prepend_length int, prepend_round int, status int, mux_seen text, feed text, observedPath text, ipPath text, vpoint text)")
	c.execute("create index idx_pfx on ASGraph(prefix)")
	c.execute("create index idx_prep_rnd on ASGraph(prepend_round)")
	c.execute("create index idx_status on ASGraph(status)")
	c.execute("create index idx_pfx_path on ASGraph(prefix,observedPath)")

	return c

def createCombinations():

	combs_all = list()
	for i in range(1,len(MUX_NAMES)+1):
		#genertae all combinations of length i
		combs = list(itertools.combinations(MUX_NAMES,i))
		#for each combination, compute a mask for the number of prepends, i.e., 3^n new prependings where n is the length of the combination
		for c in combs:
			num_muxes = len(c)
			init_prepend = [1]*num_muxes
			mask = init_prepend
			combs_all.append((c,list(mask)))
			while (next(mask,3)) :
				combs_all.append((c,list(mask)))

	return combs_all

def main():

	global opts 
	parser = create_parser()
	opts, _args = parser.parse_args()
	if  opts.database is None:
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
	
	global conn
	c = create_db()
	combs_all = createCombinations()
	

	global feeds
	feeds = ['rv', 'ftr']
	num2pfx = dict()

	global pfxToLoc
	pfxToLoc = dict()
	for feed in feeds:
		pfxToLoc[feed] = api.get_prefix_to_locations(feed)

	global num2VPseen
	num2VPseen = dict()
	for num in PREFIX_RANGE:
		num2VPseen[num] = dict()

	for num in PREFIX_RANGE:
		num2pfx[num] = Prefix(num, 47065, "announced")


	#announce the first prefix from all muxes : this corresponds to the case with 0 prepends 
	pfx = num2pfx[PREFIX_RANGE[0]]
	for mux in MUX_NAMES:
		pfx.update_route_map1(mux, True)
	pfx.up()

	sent_pfx_idx = 1
	#sentinel prefixes
	for mux in MUX_NAMES:
		pfx = num2pfx[PREFIX_RANGE[sent_pfx_idx]]
		announce_sentinel(pfx,mux)
		sent_pfx_idx += 1
		
	soft_reset(num2pfx)
	wait_cmd(PREPEND_INTERVAL)
	

	#conn = sqlite3.connect('../data/prepend_data/allC.db2012-05-11 19:33:07.248784')
	#c = conn.cursor()
	populateDB(c,PREFIX_RANGE[0],MUX_NAMES,[0,0,0,0,0], 0 ,TEST)
	for num in PREFIX_RANGE[1:]:
		idx = PREFIX_RANGE.index(num)-1
		populateDB(c,num,[MUX_NAMES[idx]],[],0,SENTINEL)
                conn.commit()

	sent_pfx = PREFIX_RANGE[0]
	sent_mux_idx = 0
	j = 0
	prepend_round = 1
	while (j < len(combs_all)):
		pfx_range = PREFIX_RANGE[1:]
		comb_thisRound = dict()
		for num in pfx_range:
			pfx = num2pfx[num]
			comb = combs_all[j]
			comb_thisRound[num] = comb
			muxesToPrepend = comb[0]
			prependLengths = comb[1]
			for mux in MUX_NAMES:
				if mux in muxesToPrepend:
					idx = muxesToPrepend.index(mux)
					pfx.set_num_prepend1(prependLengths[idx],mux)
				else:
					pfx.update_route_map1(mux,False)

			pfx.up()
			j += 1
		
		announce_sentinel(num2pfx[sent_pfx], MUX_NAMES[sent_mux_idx])

		soft_reset(num2pfx)
		wait_cmd(PREPEND_INTERVAL)  

		print "comb:"
		print comb_thisRound
		for num in PREFIX_RANGE:
			if num is not sent_pfx:
				muxesPrepended = comb_thisRound[num][0]
				prependLengths = comb_thisRound[num][1]
				populateDB(c,num,muxesPrepended,prependLengths,prepend_round,TEST)
			else:
				populateDB(c,num,[],[],prepend_round,SENTINEL)
			conn.commit()

		sent_mux_idx = (sent_mux_idx+1)%len(MUX_NAMES)
		prepend_round += 1

		
      

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

