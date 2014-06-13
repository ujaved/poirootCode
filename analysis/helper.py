#!/usr/bin/python

import sqlite3
import sys
import os
import errno
import random
import gzip
import resource
import logging
import logging.handlers
import time
from optparse import OptionParser
import subprocess, threading
import re
from collections import deque
 
RIOT_ASN = 47065
MUX_ASN = ['73','2381','2637','88','12148','47065']
muxASToName = dict()
muxASToName['12148'] = 'CLEMSON'
muxASToName['2637'] = 'GATECH'
muxASToName['88'] = 'PRINCE'
muxASToName['2381'] = 'WISC'
muxASToName['73'] = 'UW'
muxASToName['2722'] = 'CLEMSON'
muxASToName['101'] = 'UW'
muxASToName['10466'] = 'PRINCE'
muxASToName['7922'] = 'PRINCE'
muxASToName['174'] = 'GATECH'

SENTINEL = 0
TEST = 1


def create_parser(): # {{{
	def open_parse_list(option, _optstr, value, parser): # {{{
		if value.endswith('.gz'): fd = gzip.open(value, 'r')
		else: fd = open(value, 'r')
		vlist = list(int(l.strip()) for l in fd)
		setattr(parser.values, option.dest, vlist)
	# }}}

	parser = OptionParser()

	parser.add_option('--poisonlist',
			dest='poisonlist',
			metavar='FILE',
			action='callback',
			callback=open_parse_list,
			nargs=1, type='str',
			help='ASNs to poison (one ASN per line)')

	parser.add_option('--blacklist',
			dest='blacklist',
			metavar='FILE',
			action='callback',
			callback=open_parse_list,
			nargs=1, type='str',
			help='ASN blacklist (one ASN per line)')

	parser.add_option('--astype',
			dest='astype',
			metavar='FILENAME',
			action='store',
			help='file name to use for AS Types')

	parser.add_option('--poison_input',
			dest='poison_input',
			metavar='FILENAME',
			action='store',
			help='file name to use for a list of poisonings for each prefix')

	parser.add_option('--log',
			dest='logfile',
			metavar='FILENAME',
			action='store',
			default='log.txt',
			help='file name to use for logs [%default]')

	parser.add_option('--output',
			dest='output',
			metavar='FILENAME',
			action='store',
			default='output.txt',
			help='file name to use for stdout [%default]')

	parser.add_option('--database',
			dest='database',
			metavar='FILENAME',
			action='store',
			help='database file')

	parser.add_option('--logdir',
			dest='logdir',
			metavar='DIR',
			action='store',
			default='../log/',
			help='directory to store configurations [%default]')

	parser.add_option('--sleep',
			dest='sleep',
			metavar='SECONDS',
			action='store',
			type='int',
			default=90*60,
			help='time to sleep between announcement changes [%default]')

	parser.add_option('--asn',
			dest='asn',
			metavar='INT',
			action='store',
			type='int',
			default=47065,
			help='AS number to use in configuration commands [%default]')

	parser.add_option('--refasn',
			dest='refasn',
			metavar='INT',
			action='store',
			type='int',
			help='AS number to measure paths from')

	parser.add_option('--peer',
			dest='peer',
			metavar='IP',
			action='store',
			default='184.164.224.1',
			help='peer IP to use in configuration commands [%default]')

	return parser
# }}}

def mkdir_p(path): # {{{
	try:
		os.makedirs(path)
	except OSError, exc:
		if exc.errno == errno.EEXIST:
			pass
		else: raise
# }}}


class VP(object):

	def __init__(self, pfx, path, feed,mux,rv):
		self.pfx = pfx
		self.path = path
		self.feed = feed
		self.mux = mux
		self.rv = rv
		self.startingPoisonIdx = len(self.path)-3
		self.poisonIdx = len(self.path)-3

	def setPoisonIdx(idx):   #the as to be poisoned
		self.poisonIdx = idx

	def setNextPoisonIdx(self): 
		if self.poisonIdx==0:
			self.poisonIdx = self.startingPoisonIdx
		else:
			self.poisonIdx -= 1

	def __str__(self):
		
		pathASs = ""
		for asn in self.path:
			pathASs = pathASs + str(asn) + " "
		
		return str(self.pfx) + "|" + pathASs + "|" + str(self.rv) + \
		       "|" + str(self.feed) + "|" + str(self.mux) + "|" + str(self.poisonIdx)



class VP_Poison(object):

	def __init__(self,pfx,path,feed,mux,rv,min_poison_idx):
		self.pfx = pfx
		self.orig_path = path
		self.cur_path = path
		self.prev_path = []
		self.feed = feed 
		self.mux = mux
		self.rv = rv
		self.min_poison_idx = min_poison_idx

		if len(self.cur_path) >= self.min_poison_idx:
			self.poisonIdx = len(self.cur_path)-self.min_poison_idx
		else:
			self.poisonIdx = 0
		
		self.curPoisonings = list()
		self.numPoisonNoEffect = 0

	def getNextAS2BePoisoned(self):
		if len(self.cur_path) > 0:
			 return int(self.cur_path[self.poisonIdx])
		else:
			return 0
		
	def getPoisonList(self):

		'''
		if len(self.cur_path)==len(self.prev_path):
			self.curPoisonings.add(getNextAS2BePoisoned())
		else:
		'''

		asn = self.getNextAS2BePoisoned()
		
		if self.numPoisonNoEffect==1:
			#no change in the poisoned path: try appending the same asn two times, prepended once already
			self.curPoisonings.append(asn)
		else:
			if asn not in self.curPoisonings:
				self.curPoisonings.append(asn)
		return self.curPoisonings

	
	def setCurPath(self,path):
		#path is a list
		self.cur_path = path
	def setPoisonIdx(idx):   #the as to be poisoned
		self.poisonIdx = idx

	def __str__(self):
		
		orig_pathASs = ""
		for asn in self.orig_path:
			orig_pathASs = orig_pathASs + str(asn) + " "

		cur_pathASs = ""
		for asn in self.cur_path:
			cur_pathASs = cur_pathASs + str(asn) + " "

		prev_pathASs = ""
		for asn in self.prev_path:
			prev_pathASs = prev_pathASs + str(asn) + " "

		pois_ASs = ""
		for asn in self.curPoisonings:
			pois_ASs = pois_ASs + str(asn) + " "
		
		return str(self.pfx) + "|" + orig_pathASs + "|" + cur_pathASs + "|" + prev_pathASs + \
		       "|" + str(self.rv) + "|" + str(self.feed) + "|" + str(self.mux) + "|" + \
		       str(self.poisonIdx) + "|" + pois_ASs + "|" + str(self.numPoisonNoEffect)

	def __eq__(self,other):
		return  self.rv==other.rv


class VP_Poison1(object):

	def __init__(self,pfx,path,feed,mux,rv,min_poison_idx):
		self.pfx = pfx
		self.orig_path = path
		self.cur_path = path
		self.prev_path = []
		self.feed = feed 
		self.mux = mux
		self.rv = rv
		self.min_poison_idx = min_poison_idx
		self.vp_asn = self.cur_path[0]

		if len(self.cur_path) >= self.min_poison_idx:
			self.initPoisonIdx = len(self.cur_path)-self.min_poison_idx
		else:
			self.initPoisonIdx = 0
		
		self.curPoisonings = list()
		self.numPoisonNoEffect = 0
		self.PoisonNoEffect = False
		self.PoisonQueue = deque()

		i = self.initPoisonIdx
		while i>0:
			self.PoisonQueue.append((int(self.cur_path[i]),[],self.cur_path))
			i -= 1

	def getNextAS2BePoisoned(self):

		
		if len(self.PoisonQueue) > 0:
			 return int(self.PoisonQueue[0][0])
		else:
			return 0

	def addStuff2PoisonQueue(self):

		if len(self.cur_path) < self.min_poison_idx:
			return
		newASes = []
		idx = 1
		while idx <= len(self.cur_path)-self.min_poison_idx:
			candAS = self.cur_path[idx]
			if candAS in self.prev_path:
				idx += 1 
				continue
			newASes.append(candAS)
			idx += 1
			
		newASes.reverse()
		for asn in newASes:
			self.PoisonQueue.appendleft((int(asn),self.curPoisonings,self.cur_path))
		
		
	def getPoisonList(self,numVPPoisonNotSeen):

		if numVPPoisonNotSeen > 0:
			return self.curPoisonings

		self.curPoisonings = []
		tup = self.PoisonQueue.popleft()
		for asn in tup[1]:
			self.curPoisonings.append(asn)
		self.curPoisonings.append(tup[0])

		'''
		if self.numPoisonNoEffect==1:
			#no change in the poisoned path: try appending the same asn two times, prepended once already
			asn = self.curPoisonings[-1]
			self.curPoisonings.append(asn)
		else:
			self.curPoisonings = []
			tup = self.PoisonQueue.popleft()
			for asn in tup[1]:
				self.curPoisonings.append(asn)
			self.curPoisonings.append(tup[0])
		'''
			
		return (self.curPoisonings,tup[2])

	def seeNextPoison(self,numVPPoisonNotSeen):

		p = []
		if len(self.PoisonQueue)>0:
			tup = self.PoisonQueue[0]
			for asn in tup[1]:
				p.append(asn)
			p.append(tup[0])
		return p
	

	def __str__(self):
		
		orig_pathASs = ""
		for asn in self.orig_path:
			orig_pathASs = orig_pathASs + str(asn) + " "

		cur_pathASs = ""
		for asn in self.cur_path:
			cur_pathASs = cur_pathASs + str(asn) + " "

		prev_pathASs = ""
		for asn in self.prev_path:
			prev_pathASs = prev_pathASs + str(asn) + " "

		pois_ASs = ""
		for asn in self.curPoisonings:
			pois_ASs = pois_ASs + str(asn) + " "
		
		return str(self.pfx) + "|" + orig_pathASs + "|" + cur_pathASs + "|" + prev_pathASs + \
		       "|" + str(self.rv) + "|" + str(self.feed) + "|" + str(self.mux) + "|" + \
		       pois_ASs + "|" + str(self.PoisonQueue) + "|" + str(self.PoisonNoEffect)

	def __eq__(self,other):
		return  self.rv==other.rv


class VP_Poison2(object):

	
	def __init__(self,pfx,path,mux,rv,min_poison_idx,as2type):
		self.pfx = pfx
		self.orig_path = path
		self.cur_path = path
		self.prev_path = []
		self.mux = mux
		self.rv = rv
		self.min_poison_idx = min_poison_idx
		self.vp_asn = self.cur_path[0]

		if len(self.cur_path) >= self.min_poison_idx:
			self.initPoisonIdx = len(self.cur_path)-self.min_poison_idx
		else:
			self.initPoisonIdx = 0
		
		self.curPoisonings = list()
		self.PoisonQueue = deque()

		i = self.initPoisonIdx
		while i>0:
			if self.cur_path[i] in as2type:
				if as2type[self.cur_path[i]]=="tier1":
					i -= 1
					continue
			self.PoisonQueue.append((int(self.cur_path[i]),[],self.cur_path,True)) #last field is whether this is a poisoning or unpoisoning
			i -= 1

		if len(self.PoisonQueue)>0:
			self.noMorePoison = False
		else:
			self.noMorePoison = True
		self.curUnpoisoning = False
		

	def addStuff2PoisonQueue(self,as2type):

		if len(self.cur_path) < self.min_poison_idx:
			return
		newASes = []
		idx = 1
		while idx <= len(self.cur_path)-self.min_poison_idx:
			candAS = self.cur_path[idx]
			if (candAS in self.prev_path) or (as2type[candAS]=="tier1") or (int(candAS) in self.curPoisonings):
				idx += 1 
				continue
			newASes.append(candAS)
			idx += 1
			
		newASes.reverse()
		for asn in newASes:
			self.PoisonQueue.appendleft((int(asn),self.curPoisonings,self.cur_path,True))
		
		
	def getPoisonList(self):

		self.nextPoisonings = []
		if len(self.PoisonQueue)>0:
			tup = self.PoisonQueue[0]
			for asn in tup[1]:
				self.nextPoisonings.append(asn)
			self.nextPoisonings.append(tup[0])

		if len(self.nextPoisonings)==0:
			print "just added 0 to nextPoisoning"
			self.nextPoisonings.append(0)

		#do nothing if the next poisioning is an unpoisoning or just starting
		# if curPoisonings[0] == RIOT_ASN, means this is an unpoisoning => just pick the next poisoning from the queue
		if len(self.curPoisonings)!= 0 and self.nextPoisonings[0] != RIOT_ASN and self.curPoisonings[0] != RIOT_ASN :
			comm_idx = -1
			if len(self.curPoisonings) <= len(self.nextPoisonings):
				s = self.curPoisonings
			else:
				s = self.nextPoisonings
			for i in range(0,len(s)):
				if self.curPoisonings[i]==self.nextPoisonings[i]:
					comm_idx = i
			print "comm_idx: " + str(comm_idx)
			if len(self.curPoisonings)>=len(self.nextPoisonings):
				# cur and next poisoning is of the form: (A B C), (D), so remove the original poisonings one by one, or
				# cur and next poisoning is of the form: (A...B C),(A...B D) so put just (A...B)
				i = comm_idx+1
				if comm_idx==-1:
					self.PoisonQueue.appendleft((RIOT_ASN,[],self.cur_path,False))
					i = 1
				if (len(self.curPoisonings)==len(self.nextPoisonings)+1) and (len(self.nextPoisonings)==comm_idx+1):
					#cur and next poisoning is of the form: (A B C), (A B), so don't do anything
					a = 1
				else:
					while (i<len(self.curPoisonings)):
						self.PoisonQueue.appendleft((self.curPoisonings[i-1],self.curPoisonings[0:i-1],self.cur_path,False))
						i += 1
				
				print str(self.PoisonQueue)


		self.curPoisonings = []
		tup = self.PoisonQueue.popleft()
		for asn in tup[1]:
			self.curPoisonings.append(asn)
		self.curPoisonings.append(tup[0])
		if tup[3]==False:
			self.curUnpoisoning = True
		else:
			 self.curUnpoisoning = False
		print "curUnpoisoning: " + str(self.curUnpoisoning)
		if self.curPoisonings[0]==RIOT_ASN and len(self.PoisonQueue)==0:
			#exhausted this vantage point for poisoning
			self.noMorePoison = True
		print "noMorePoison: " + str(self.noMorePoison)
		return (self.curPoisonings,tup[2])
	

	def __str__(self):
		
		orig_pathASs = ""
		for asn in self.orig_path:
			orig_pathASs = orig_pathASs + str(asn) + " "

		cur_pathASs = ""
		for asn in self.cur_path:
			cur_pathASs = cur_pathASs + str(asn) + " "

		prev_pathASs = ""
		for asn in self.prev_path:
			prev_pathASs = prev_pathASs + str(asn) + " "

		pois_ASs = ""
		for asn in self.curPoisonings:
			pois_ASs = pois_ASs + str(asn) + " "
		
		return str(self.pfx) + "|" + orig_pathASs + "|" + cur_pathASs + "|" + prev_pathASs + \
		       "|" + str(self.rv) + "|" + str(self.mux) + "|" + \
		       pois_ASs + "|" + str(self.PoisonQueue)

	def __eq__(self,other):
		return  self.rv==other.rv
	

class Prefix(object): # {{{    #asn: poisoning asn=47065
	ANNOUNCED = 'announced'
	WITHDRAWN = 'withdrawn'
	PREPEND_SEQUENCE = [0, 2]

	def __init__(self, pfx, ann_asn,direction):
		self.ann_asn = ann_asn
		self.pfx = pfx
		if direction == Prefix.ANNOUNCED:
			self.status = Prefix.WITHDRAWN
			self.up()
		if direction == Prefix.WITHDRAWN:
			self.status = Prefix.ANNOUNCED
			self.down()
		self.prepend_idx = 0
		self.prepend = None
		self.poisoned_as = None
		self.poisonedList = None
		self.poisonidx = 0
		self.as_path_string = 'no-prepend'
		self.update_route_map()
		self.asn = None
		self.paths = list()
		

	def up(self):
		if self.status == Prefix.ANNOUNCED: return
		logging.info('prefix up %d', self.pfx)
		cmd = 'vtysh -d bgpd -c "config terminal" ' + \
					('-c "router bgp %d" ' % self.ann_asn) + \
					('-c "network 184.164.%d.0/24 ' % self.pfx) + \
					('route-map POISON-%d" ' % self.pfx) + \
					'-c "end" -c "end"'
		logging.info(cmd)
		#sys.stderr.write(cmd+'\n')
		os.system(cmd)
		self.status = Prefix.ANNOUNCED

	def down(self):
		if self.status == Prefix.WITHDRAWN:
			return
		logging.info('prefix down %d', self.pfx)
		cmd = 'vtysh -d bgpd -c "config terminal" ' + \
					('-c "router bgp %d" ' % self.ann_asn) + \
					('-c "no network 184.164.%d.0/24" ' % self.pfx) + \
					'-c "end" -c "end"'
		logging.info(cmd)
		#sys.stderr.write(cmd+'\n')
		os.system(cmd)
		self.status = Prefix.WITHDRAWN

	def toggle_up_down(self):
		if self.status == Prefix.WITHDRAWN:
			self.up()
		else:
			self.down()

	def poison(self, asn):
		self.poisoned_as = asn
		self.update_route_map()

	def poisonList(self, as_list):
		self.poisoned_as = 47065
		self.poisonedList = as_list
		#self.update_route_map()


	def random_prepend(self):
		self.prepend_idx = random.randint(0, len(Prefix.PREPEND_SEQUENCE)-1)
		self.set_prepend_idx()

	def next_prepend(self):
		self.prepend_idx += 1
		self.prepend_idx = self.prepend_idx % len(Prefix.PREPEND_SEQUENCE)
		self.set_prepend_idx()

	def set_prepend_idx(self, idx=None):
		if idx is not None:
			self.prepend_idx = idx
		nprepends = Prefix.PREPEND_SEQUENCE[self.prepend_idx]
		if nprepends == 0:
			self.prepend = None
		else:
			self.prepend = [self.ann_asn] * nprepends
		logging.info('set_prepend_idx %s', self.prepend)
		self.update_route_map()

	def set_num_prepend(self, nprepends):

		if nprepends == 0:
			self.prepend = None
		else:
			self.prepend = [self.ann_asn] * nprepends
		logging.info('set_prepend_idx %s', self.prepend)
		self.update_route_map()

	def set_num_prepend1(self, nprepends, mux):

		if nprepends == 0:
			self.prepend = None
		else:
			self.prepend = [self.ann_asn] * nprepends
		logging.info('set_prepend_idx %s', self.prepend)
		self.update_route_map1(mux, True)

	def addPath(self, path):
		self.paths.append(path)

	def update_route_map1(self, mux, status):
		#status can have three values: 1) True, 2) False, 3) None. Do nothing if it is None
		#assert mux in MUX_NAMES
		logging.info('update_route_map %s %d', mux, self.pfx)
		cmd = 'vtysh -d bgpd -c "config terminal"'
		cmd += ' -c "route-map POISON-%d permit %d"' % (self.pfx, self.pfx)
		cmd += ' -c "set as-path prepend 1"'
		cmd += ' -c "no set as-path prepend"'
		cmd += ' -c "end"'
		cmd += ' -c "configure terminal"'
		cmd += ' -c "route-map %s permit %d"' % (mux, self.pfx)
		flag = True
		if status is False:
			#cmd += ' -c "no match ip address prefix-list NET-%d"' % (self.pfx)
			cmd += ' -c "match ip address prefix-list NONET"'
			flag = False
		elif status is True:
			cmd += ' -c "match ip address prefix-list NET-%d"' % self.pfx
		if self.poisonedList is None and self.prepend is not None and flag is True:
			asns = list()
			asns.extend(str(a) for a in self.prepend)
			#asns = [str(opts.ann_asn) for _i in range(self.prepend)]
			self.as_path_string = ' '.join(asns)
			cmd += ' -c "set as-path prepend %s"' % self.as_path_string

		elif self.poisonedList is None and self.prepend is None:
			cmd += ' -c "set as-path prepend 1"'
			cmd += ' -c "no set as-path prepend"'
			self.as_path_string = 'no-prepend'

		elif self.poisonedList is not None and flag is True:
			a = ""
			for b in self.poisonedList:
				a = a + " " + str(b)
			asns = [a, str(self.ann_asn)]
			self.as_path_string = ' '.join(asns)
			cmd += ' -c "set as-path prepend %s"' % self.as_path_string

		elif self.poisonedList is not None and flag is False:
			cmd += ' -c "set as-path prepend 1"'
			cmd += ' -c "no set as-path prepend"'
			self.as_path_string = 'no-prepend'
		
		cmd += ' -c "end" -c "end"'
		logging.debug(cmd)
		#sys.stderr.write(cmd+'\n')
		os.system(cmd)

	def update_route_map(self):
		logging.info('update_route_map %d', self.pfx)
		cmd = 'vtysh -d bgpd -c "config terminal"'
		cmd += ' -c "route-map POISON-%d permit %d"' % (self.pfx, self.pfx)
		if self.poisoned_as is None and self.prepend is None:
			cmd += ' -c "set as-path prepend 1"'
			cmd += ' -c "no set as-path prepend"'
			self.as_path_string = 'no-prepend'
		else:
			asns = list()
			if self.poisonedList is not None:
                                a = ""
				for b in self.poisonedList:
					a = a + " " + str(b)
				asns = [a, str(self.ann_asn)]
                        elif self.poisoned_as is not None:
				asns = [str(self.poisoned_as), str(self.ann_asn)]
			elif self.prepend is not None:
				asns.extend(str(a) for a in self.prepend)
			self.as_path_string = ' '.join(asns)
			cmd += ' -c "set as-path prepend %s"' % self.as_path_string
		cmd += ' -c "set community none" -c "end" -c "end"'
		logging.debug(cmd)
		#print cmd
		os.system(cmd)
# }}}


class ASN(object): # {{{

	# path count is a list -- number of paths in successive rounds
	def __init__(self, name, bfs_level, path_count, poisoned):
		self.name = name    #int
		self.bfs_level = bfs_level
		self.path_count = path_count    #number of paths thsi asn shows up in at bfs_level
		self.poisoned = poisoned

	def __str__(self):
		
		return "as: " + self.name + " bfs_level:" + str(self.bfs_level) + \
		    " path_count:" + str(self.path_count) + " poisoned:" + str(self.poisoned)


class ASNQuery(object): # {{{

	def __init__(self, name, poison_rounds, paths, IsPoisoned):
		self.name = name    #int
		self.poison_rounds = poison_rounds
		self.paths = paths 
		self.IsPoisoned = IsPoisoned

	def __str__(self):
		
		'''
		return "as: " + self.name + " bfs_level:" + str(self.bfs_level) + \
		    " path_count:" + str(self.path_count) + " poisoned:" + str(self.poisoned)
		'''

class Path(object): # {{{

	POISON = 'poison'
	UNPOISON = 'unpoison'
       
	def __init__(self, pfx, time, poisonedASes, path):
		self.pfx = pfx
		self.time = time
		self.poisonedASes = poisonedASes
		self.path = path
		self.nextPoisonList = list()
		self.nextPoisonStatus = None

	def __str__(self):
		pASs = ""
                for a in self.poisonedASes:
			pASs = pASs + str(a) + " "
		pathASs = ""
		if self.path:
			for a in self.path:
				pathASs = pathASs + str(a) + " "
		fASs = ""
                for a in self.nextPoisonList:
			fASs = fASs + str(a) + " "
		return str(self.pfx) + "|" + str(self.time) + "|" + pASs + "|" + pathASs + \
		       "|" + fASs + "|" + self.nextPoisonStatus

	def addPoisonedAS(self, asn):
		if self.poisonedASes is None:
			self.poisonedASes = list()
		self.poisonedASes.append(asn)


def getFilteredPath(path,feed):
    r = list(path)
    r.reverse()

    mux = ''
    for asn in r:
	    if asn in muxASToName:
		    mux  = muxASToName[asn]
		    break

    if not mux or len(path)<3:
	    return None

    filpath = []

    if feed=='rv':
	    prev_asn = '0'
	    for asn in path:
		    if asn==prev_asn:
			    continue
		    filpath.append(asn)
		    prev_asn = asn

	    loopDet = dict()
	    for i in range(len(filpath)):
		    asn = filpath[i]
		    if asn in loopDet:
			    filpath = filpath[0:loopDet[asn]+1]
			    break
		    loopDet[asn] = i
		    
            return (filpath,mux)

    prev_asn = '0'
    for asn in path:
        if asn==prev_asn or asn=='0' or asn=='3303':
            continue
        if prev_asn=='10466' and mux=='PRINCE' and asn=='47065':
            filpath.append('88')
	if prev_asn=='7922' and mux=='PRINCE' and asn=='47065':
            filpath.append('88')
        if prev_asn=='174' and mux=='GATECH' and asn=='47065':
            filpath.append('2637')
	if prev_asn=='101' and mux=='UW' and asn=='47065':
            filpath.append('73')
        if prev_asn=='2722' and mux=='CLEMSON' and asn=='47065':
            filpath.append('12148')
        filpath.append(asn)
        prev_asn = asn
    if prev_asn=='10466' and mux=='PRINCE':
        prev_asn = '88'
        filpath.append('88')
    if prev_asn=='7922' and mux=='PRINCE':
        prev_asn = '88'
        filpath.append('88')
    if prev_asn=='174' and mux=='GATECH':
        prev_asn = '2637'
        filpath.append('2637')
    if prev_asn=='101' and mux=='UW':
        prev_asn = '73'
        filpath.append('73')
    if prev_asn=='2722' and mux=='CLEMSON':
        prev_asn = '12148'
        filpath.append('12148')
    if prev_asn in MUX_ASN[0:5]:
        filpath.append('47065')

    loopDet = dict()
    for i in range(len(filpath)):
        asn = filpath[i]
        if asn in loopDet:
            filpath = filpath[i:]
            break
        loopDet[asn] = 1

    return (filpath,mux)
