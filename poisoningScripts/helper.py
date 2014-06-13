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
import itertools
import copy
import bisect

RIOT = '47065'
MUX_NAMES = ['UW', 'WISC', 'GATECH', 'PRINCE', 'CLEMSON']
MUX_ASN = ['73','2381','2637','88','12148']
prep_MUX = ['WISC', 'UW','WISC','GATECH','PRINCE','UW','CLEMSON']
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
muxASToName['174'] = 'GATECH'  #comment out for other scripts

mux2ASN = dict()
mux2ASN['CLEMSON'] = '12148'
mux2ASN['GATECH'] = '2637'
mux2ASN['PRINCE'] = '88'
mux2ASN['WISC'] = '2381'
mux2ASN['UW'] = '73'

SET = 0
SINGLE = 1

SENTINEL = 0
TEST = 1

ACTUAL = 'ACTUAL'
INFERRED = 'INFERRED'

class comb_info(object):

    def __init__(self,comb,p1,p2,path_picked):
        
        self.comb = comb
        self.p1 = p1
        self.p2 = p2
        self.path_picked = path_picked

    def __str__(self):
        
        return str(self.p1) + "\n" + str(self.p2) + "\n" + str(self.path_picked) + "\n--------------"


class comb2(object):

    def __init__(self,comb,p1,p2):
        self.comb = comb
        self.p1 = p1
        self.p2 = p2
        if self.p1==0 and self.p2==0:
            self.ratio1 = 1.0
            self.ratio2 = 1.0
        else:
            self.ratio1 = float(self.p1)/float(self.p2)
            self.ratio2 = float(self.p2)/float(self.p1)

    def __eq__(self,other):
        ret = False
        if self.comb[0]==other.comb[0] and self.comb[1]==other.comb[1]:
            if self.ratio1==other.ratio1:
                ret = True
            else:
                ret = False
        if self.comb[1]==other.comb[0] and self.comb[0]==other.comb[1]:
            if self.ratio1==other.ratio2:
                ret = True
            else:
                ret = False
        return ret

    def __str__(self):
        
        return str(self.comb)  + "|" + str(self.p1) + "|" + str(self.p2) + "|" + str(self.ratio1) + \
		       "|" + str(self.ratio2)
        
class Path(object):

    def __init__(self, pfx, up_asn, mux, prepend, path_control, path_data, mux_list, prepend_status, alt_path_list,round_disc,wholePath,vp):
        self.pfx = pfx
        self.up_asn = up_asn    #upstream AS to which the announcement is made
        self.mux = mux
        self.prepend = prepend
        self.path_data = path_data
        self.path_control = path_control
        self.mux_list = mux_list
        self.prepend_status = prepend_status
        #self.all_path_data = all_path_data
        #alt_path_list is a list of paths; each path has the same prefix as pfx, but different mux. This
        # is for the case when the AS makes different announcements to different neighbors, sometimes seen in the data plane
        self.alt_path_list = alt_path_list
        self.round_disc = round_disc
        self.status = ACTUAL
        self.wholePath = wholePath
        self.vp = vp
        self.hash = hash(str(self))

    def __str__(self):
        
        return str(self.pfx)  + "|" + str(self.mux) + "|" + str(self.prepend) + "|" + str(self.path_control) + \
		       "|" + str(self.path_data) + "|" + str(self.mux_list) + "|" + str(self.prepend_status) + \
                       "|" + str(self.round_disc) + "|" + str(self.status) + "|" + str(self.up_asn) + "|" + str(self.wholePath) + "|" + str(self.vp)

    def __eq__(self,other):
        return  self.mux==other.mux and self.prepend==other.prepend \
            and self.path_data==other.path_data and self.path_control==other.path_control \
            and self.mux_list==other.mux_list and self.prepend_status==other.prepend_status
        #return self.hash==other.hash


class Path_Poison(object):

    def __init__(self, pfx, up_asn, mux, poisoning, path_control, path_data, \
                     wholePath_ctrl,wholePath_data, prevPath, vpoint, thisVPPoisoned):
        self.pfx = pfx
        self.up_asn = up_asn    #upstream AS to which the announcement is made
        self.mux = mux
        self.poisoning = poisoning #poisoning done to reach this path
        self.path_data = path_data
        self.path_control = path_control
        
        #prev Path on which poisoning was done

        #self.prevPath_ctrl = prevPath_ctrl
        self.prevPath = prevPath
        self.wholePath_ctrl = wholePath_ctrl
        self.wholePath_data = wholePath_data
        self.vpoint = vpoint
        self.thisVPPoisoned = thisVPPoisoned 
        self.alt_path_list = []
        self.hash = hash(str(self))

    def __str__(self):
        
        return str(self.pfx)  + "|" + str(self.mux) + "|" + str(self.poisoning) + "|" + str(self.path_control) + \
            "|" + str(self.path_data) + "|" + str(self.wholePath_ctrl) + "|" + str(self.wholePath_data) + \
            "|" + str(self.prevPath) + "|" + str(self.vpoint) 

    def __eq__(self,other):

        '''
        o = True
        if self.thisVPPoisoned:
            o = (self.poisoning==other.poisoning)
        '''
        '''
            x = True
            if len(self.wholePath_data) > 0:
                x = (self.wholePath_data==self.prevPath)
            else:
                x = (self.wholePath_ctrl==self.prevPath)
            o = o or x
        '''
        
        m = (self.mux==other.mux)
        p = False
        if len(self.path_data) > 0 and  len(other.path_data) > 0:
            p = (self.path_data==other.path_data)
        elif len(self.path_control) > 0 and len(other.path_control) > 0:
            p = (self.path_control==other.path_control)
        elif len(self.path_control) > 0 and len(other.path_data) > 0:
            p = (self.path_control==other.path_data)
        elif len(self.path_data) > 0 and len(other.path_control) > 0:
            p = (self.path_data==other.path_control)
            
        #return m and p and o
        return m and p
        
        #return self.hash==other.hash



class Path_Simple(object):

    def __init__(self, path_control, path_data, vp,feed,fullpath,unix_time,path,ipPath):
        
        self.path_data = path_data
        self.path_control = path_control
        self.feed = feed
        
        if len(vp) > 0:
            self.VPs = [(vp,fullpath,path,ipPath,unix_time)]
        else:
            self.VPs = []
        
        self.alt_path_list = []
        self.hash = hash(str(self))

    def hugeDiscrepancy(self,other):

        bigger = self
        smaller = other
        if len(self.VPs) < len(other.VPs):
            bigger = other
            smaller = self
        if (len(bigger.VPs) >= 30) and (len(smaller.VPs) < 0.150*len(bigger.VPs)):
            return True
        return False
        

    def __str__(self):
        
        #return str(self.path_control) + "|" + str(self.path_data) + "|" + str(self.VPs) + "|" + str(self.feed)
        return str(self.path_control) + "|" + str(self.path_data) + "|" + str(len(self.VPs))

    def __eq__(self,other):
        
        if len(self.path_control) > 0 and len(other.path_control) > 0:
            return (self.path_control==other.path_control)
        elif len(self.path_data) > 0 and  len(other.path_data) > 0:

            '''
            if len(self.path_control)==0 and len(other.path_control)==0: 
                return (self.path_data==other.path_data)
            else:
            '''
                #at this point data paths are the same, but not control paths
                
            if self.hugeDiscrepancy(other):
                return False
            else:
                if self.path_data==other.path_data:
                    return True
                else:
                    #check for paths in alt_path_list
                    for p in self.alt_path_list:
                        if p.path_data==other.path_data:
                            return True
                    for p in other.alt_path_list:
                        if p.path_data==self.path_data:
                            return True
                    return False

                '''
                if len(self.VPs)>2 and len(other.VPs)>2:
                    return (self.path_data==other.path_data)
                else:
                    return False
                '''
                
        elif len(self.path_control) > 0 and len(other.path_data) > 0:
            return (self.path_control==other.path_data)
        elif len(self.path_data) > 0 and len(other.path_control) > 0:
            return (self.path_data==other.path_control)
            
        return False


class PATH(object):

    def __init__(self,path_control,path_data,vp,fullpath,unix_time,unfilteredPath,ipPath):
        
        self.path_data = path_data
        self.path_control = path_control
        self.fullpath = fullpath
        
        if len(vp) > 0:
            self.VPs = [(vp,fullpath,unfilteredPath,unix_time,ipPath)]
        else:
            self.VPs = []
        
        self.alt_path_list = []
        self.up_asn = ''
        self.hash = hash(str(self))

    def hugeDiscrepancy(self,other):

        bigger = self
        smaller = other
        if len(self.VPs) < len(other.VPs):
            bigger = other
            smaller = self
        if (len(bigger.VPs) >= 8) and (len(smaller.VPs) < 0.150*len(bigger.VPs)):
            return True
        if (len(bigger.VPs) >= 8) and (len(smaller.VPs) < 0.20*len(bigger.VPs)) \
                and self.path_data[0]=='7922':
            return True
        return False
        

    def getPath(self):
        if len(self.path_control)>0:
            return self.path_control
        else:
            return self.path_data

    def getMaxTime(self):
        max_time = 0.0
        for vp in self.VPs:
            if vp[3] > max_time:
                max_time = vp[3]
        return max_time
    
    def __str__(self):

        max_time = self.getMaxTime()
        #return str(self.path_control) + "|" + str(self.path_data) + "|" + str(self.VPs) + "|" + str(self.feed)
        return str(self.path_control) + "|" + str(self.path_data) + "|" + str(len(self.VPs)) + "|" + str(len(self.alt_path_list))

    def __eq__(self,other):

        if len(self.path_control)==0 and len(other.path_control)==0 and \
                len(self.path_data)==0 and len(other.path_data)==0:
            return True
        if len(self.path_control) > 0 and len(other.path_control) > 0:
            if self.path_control==other.path_control:
                return True
            else:
                return False
                #data path might be the same: if data path is the same, only consider it if #vps is at least 6 on both paths
                if len(self.path_data)>0 and len(other.path_data)>0:
                    if self.path_data==other.path_data:
                        if (not self.hugeDiscrepancy(other)):
                            return True
                    '''
                    else:
                        if whollyContained(self.path_data,other.path_data):
                            if ('22388' not in self.path_data and '22388' not in other.path_data):
                                    #and ('1299' not in self.path_data and '1299' not in other.path_data):
                            #this is 'WISC' round 22, path strating from 7660
                                return True
                    '''
                
        elif len(self.path_data) > 0 and  len(other.path_data) > 0:
            if self.path_data==other.path_data:
                if self.hugeDiscrepancy(other):
                    min_length = 3
                    '''
                    if self.path_data[-2]=='12148':
                        min_length = 4
                    '''
                    if len(self.path_data)>min_length or self.path_data[0]=='10466' or self.path_data[0]=='7922':
                        return False
                return True
            else:
                    #check for paths in alt_path_list
                for p in self.alt_path_list:
                    if p.path_data==other.path_data:
                        return True
                for p in other.alt_path_list:
                    if p.path_data==self.path_data:
                        return True

                if whollyContained(self.path_data,other.path_data):
                    return True
                #look for shorter path wholly contained in bigger path
                
        elif len(self.path_control) > 0 and len(other.path_data) > 0:
            if self.path_control==other.path_data:
                return True
            else:
                if whollyContained(self.path_control,other.path_data):
                    return True
                return False
        elif len(self.path_data) > 0 and len(other.path_control) > 0:
            if self.path_data==other.path_control:
                return True
            else:
                if whollyContained(self.path_data,other.path_control):
                    return True
                return False
            
        return False


    def alternative_equal(self,other):

        if len(self.path_control)==0 and len(other.path_control)==0 and \
                len(self.path_data)==0 and len(other.path_data)==0:
            return True
        if len(self.path_control) > 0 and len(other.path_control) > 0:
            return (self.path_control==other.path_control)
        elif len(self.path_data) > 0 and  len(other.path_data) > 0:
            if self.path_data==other.path_data:
                return True
            else:
                    #check for paths in alt_path_list
                for p in self.alt_path_list:
                    if p.path_data==other.path_data:
                        return True
                for p in other.alt_path_list:
                    if p.path_data==self.path_data:
                        return True
                    
                #look for shorter path wholly contained in bigger path
                if whollyContained(self.path_data,other.path_data):
                    return True
                
        elif len(self.path_control) > 0 and len(other.path_data) > 0:
            if self.path_control==other.path_data:
                return True
            else:
                if whollyContained(self.path_control,other.path_data):
                    return True
                return False
        elif len(self.path_data) > 0 and len(other.path_control) > 0:
            if self.path_data==other.path_control:
                return True
            else:
                if whollyContained(self.path_data,other.path_control):
                    return True
                return False
            
        return False

class PATH_PEER(object):

    def __init__(self,path,vp,unix_time):
        # path in this case is a list of (asn,peeringPoint) tuples

        self.path = path
        
        if len(vp) > 0:
            self.VPs = [(vp,unix_time)]
        else:
            self.VPs = []
        
        self.hash = hash(str(self))

    def hugeDiscrepancy(self,other):

        bigger = self
        smaller = other
        if len(self.VPs) < len(other.VPs):
            bigger = other
            smaller = self
        if (len(bigger.VPs) >= 8) and (len(smaller.VPs) < 0.150*len(bigger.VPs)):
            return True
        if (len(bigger.VPs) >= 8) and (len(smaller.VPs) < 0.20*len(bigger.VPs)) \
                and self.path_data[0]=='7922':
            return True
        return False
    
    def __str__(self):

        return str(self.path) + "|" + str(len(self.VPs))

    def __eq__(self,other):

        if len(self.path)==0 and len(other.path)==0:
            return True
                
        elif len(self.path_data) > 0 and  len(other.path_data) > 0:
            if self.path_data==other.path_data:
                if self.hugeDiscrepancy(other):
                    min_length = 3
                    '''
                    if self.path_data[-2]=='12148':
                        min_length = 4
                    '''
                    if len(self.path_data)>min_length or self.path_data[0]=='10466' or self.path_data[0]=='7922':
                        return False
                return True
            else:
                    #check for paths in alt_path_list
                for p in self.alt_path_list:
                    if p.path_data==other.path_data:
                        return True
                for p in other.alt_path_list:
                    if p.path_data==self.path_data:
                        return True

                if whollyContained(self.path_data,other.path_data):
                    return True
                #look for shorter path wholly contained in bigger path
                
        elif len(self.path_control) > 0 and len(other.path_data) > 0:
            if self.path_control==other.path_data:
                return True
            else:
                if whollyContained(self.path_control,other.path_data):
                    return True
                return False
        elif len(self.path_data) > 0 and len(other.path_control) > 0:
            if self.path_data==other.path_control:
                return True
            else:
                if whollyContained(self.path_data,other.path_control):
                    return True
                return False
            
        return False


def whollyContained(p1,p2):
    if len(p1)>len(p2):
        shorter = p2
        longer = p1
    else:
        shorter = p1
        longer = p2
    if len(set(shorter)-set(longer))==0:
        if len(set(longer)-set(shorter))==1:
            return True
    
class Path_RC(object):

    def __init__(self,path,vp,fullpath,unix_time,unfilteredPath,ipPath):
        
        self.path = path
        if len(vp) > 0:
            self.VPs = [(vp,fullpath,unfilteredPath,ipPath,unix_time)]
        else:
            self.VPs = []
        
        self.alt_path_list = []
        self.hash = hash(str(self))

    def hugeDiscrepancy(self,other):

        bigger = self
        smaller = other
        if len(self.VPs) < len(other.VPs):
            bigger = other
            smaller = self
        if (len(bigger.VPs) >= 8) and (len(smaller.VPs) <= 0.125*len(bigger.VPs)):
            return True
        
        return False
        

    def __str__(self):
        
        return str(self.path) + "|" + str(len(self.VPs))

    def __eq__(self,other):

        if self.path==other.path:
            #check for discrepancy
            if self.hugeDiscrepancy(other):
                #if the as is very close to riot let it go
                min_length = 3
                if self.path[-2]=='12148':
                    min_length = 4
                if len(self.path)>min_length:
                    return False
            return True
        else:
            #check for paths in alt_path_list
            for p in self.alt_path_list:
                if p.path==other.path:
                    return True
                for p in other.alt_path_list:
                    if p.path==self.path:
                            return True

            #look for shorter path wholly contained in bigger path
            if len(self.path)>0 and len(other.path)>0:
                if len(self.path)>len(other.path):
                    shorter = other.path
                    longer = self.path
                else:
                    shorter = self.path
                    longer = other.path
                if len(set(shorter)-set(longer))==0:
                    if len(set(longer)-set(shorter))==1:
                        return True
            
            return False


class Path_History(object):

    def __init__(self):
        self.pfx = pfx
        self.up_asn = up_asn    #upstream AS to which the announcement is made
        self.mux = mux
        self.poisoning = poisoning #poisoning done to reach this path
        self.path_data = path_data
        self.path_control = path_control
        self.prev_Path = prev_Path      #prev Path on which poisoning was done
        self.alt_path_list = []
        self.hash = hash(str(self))


class Path_VP(object):

    def __init__(self, orig,filpath,feed,vp,ipPath):
        self.origpath = orig
        self.filpath = filpath
        self.feed = feed
        self.vp = vp
        self.ipPath = ipPath
        

    def __str__(self):
        
        #return str(self.origpath)  + "|" + str(self.filpath)
        p = ""
        for asn in self.filpath:
            p += str(asn) + " "
        return p.strip()
        #return str(self.filpath)

def sentinelChange(cur_path_sent,old_path_sent):

    if cur_path_sent==old_path_sent:
        return False
    if len(cur_path_sent)>0 and len(old_path_sent)>0:
        if len(cur_path_sent)>len(old_path_sent):
            shorter = old_path_sent
            longer = cur_path_sent
        else:
            shorter = cur_path_sent
            longer = old_path_sent
        if len(set(shorter)-set(longer))==0:
            #shorter path is wholly contained in the longer path, not needed
            if len(set(longer)-set(shorter))==1:
                return False

    return True
    

def isValidPathChange(cur_path,old_path,mux,wholeCurPath,wholeOldPath,cur_path_sent,old_path_sent,round,prev_r,
                      as2round2pfx2path,cur_poisoning,prev_poisoning,pfx,as2mux2AllPaths,p2pMap,vp):

    if len(cur_path)<=3 and len(old_path)<=3:
        return False
    if cur_path==old_path:
        return False
    if (round==1 and len(old_path)==0):
        return False
    if (len(cur_path)>0 and len(cur_path)<3) or (len(old_path)>0 and len(old_path)<3):
        return False
    if len(cur_path)>0 and len(old_path)>0 and cur_path[0] != old_path[0]:
        return False
    if (len(old_path)>0 and old_path[-2]!=mux2ASN[mux]) or \
            (len(cur_path)>0 and cur_path[-2]!=mux2ASN[mux]):
        return False

    if cur_poisoning.split()[0]==RIOT:
        #unpoisoning --> if cur_path is empty, ignore
        if len(cur_path)==0:
            return False

    #poisoning --> if prev_path is empty, ignore-->path can't appear from nothing 
    if (len(prev_poisoning.split())>0 and prev_poisoning.split()[0]==RIOT) or \
            (len(cur_poisoning.split()) > len(prev_poisoning.split())):
        if len(old_path)==0:
            return False

    '''
    if len(wholeCurPath) != len(wholeOldPath):
        return True
    for i in range(len(wholeCurPath)):
        if wholeCurPath[i] != wholeOldPath[i] and wholeCurPath[i] != '0' and wholeOldPath[i] != '0':
            return True
    '''
    
    if len(cur_path)>0 and len(old_path)>0:
        if len(cur_path)>len(old_path):
            shorter = old_path
            longer = cur_path
        else:
            shorter = cur_path
            longer = old_path
        if len(set(shorter)-set(longer))==0:
            #shorter path is wholly contained in the longer path, not needed
            if len(set(longer)-set(shorter))==1:
                return False

    if sentinelChange(cur_path_sent,old_path_sent):
        return False

    if (len(cur_poisoning.split()) > len(prev_poisoning.split())) \
		    or (prev_poisoning.split()[0]==RIOT):
		poisonAS = cur_poisoning.split()[-1]
                isDown = True
    else:
        poisonAS = prev_poisoning.split()[-1]
        isDown = False

    '''
    if premPoisoning(as2round2pfx2path,poisonAS,isDown,old_path,cur_path,pfx,round,prev_r,p2pMap,mux,vp):
        #print "premature" + "|" + str(old_path) + "|" + str(cur_path)
        return False
    '''

    '''
    if (prematurePoisoning1(as2round2pfx2path,old_path,cur_path,cur_poisoning,prev_poisoning,\
                                       pfx,round,prev_r,as2mux2AllPaths,p2pMap,mux,vp)):                                   
        return False
    '''
    
    return True

def isValidFeldmannPath(cur_path,old_path,mux,wholeCurPath,wholeOldPath,cur_path_sent,old_path_sent,round,prev_r,
                      as2round2pfx2path,cur_poisoning,prev_poisoning,pfx,as2mux2AllPaths,p2pMap,vp):

    if len(cur_path)<=3 and len(old_path)<=3:
        return False
    if (round==1 and len(old_path)==0):
        return False
    if (len(cur_path)>0 and len(cur_path)<3) or (len(old_path)>0 and len(old_path)<3):
        return False
    if len(cur_path)>0 and len(old_path)>0 and cur_path[0] != old_path[0]:
        return False
    if (len(old_path)>0 and old_path[-2]!=mux2ASN[mux]) or \
            (len(cur_path)>0 and cur_path[-2]!=mux2ASN[mux]):
        return False

    if cur_poisoning.split()[0]==RIOT:
        #unpoisoning --> if cur_path is empty, ignore
        if len(cur_path)==0:
            return False

    #poisoning --> if prev_path is empty, ignore-->path can't appear from nothing 
    if (len(prev_poisoning.split())>0 and prev_poisoning.split()[0]==RIOT) or \
            (len(cur_poisoning.split()) > len(prev_poisoning.split())):
        if len(old_path)==0:
            return False

    if sentinelChange(cur_path_sent,old_path_sent):
        return False
    
    return True


def isValidPathChangeForRanking(cur_path,old_path,mux,cur_path_sent,old_path_sent,cur_poisoning,prev_poisoning):

    #both paths are guaranteed to be non-zero length
    if len(cur_path)<=2 and len(old_path)<=2:
        return False
    if cur_path==old_path:
        return False
    if cur_path[0] != old_path[0]:
        return False
    if (old_path[-2]!=mux2ASN[mux]) or (cur_path[-2]!=mux2ASN[mux]):
        return False

    '''
    if len(cur_path)>len(old_path):
        shorter = old_path
        longer = cur_path
    else:
        shorter = cur_path
        longer = old_path
    if len(set(shorter)-set(longer))==0:
            #shorter path is wholly contained in the longer path, not needed
        if len(set(longer)-set(shorter))==1:
            return False
    '''
    if sentinelChange(cur_path_sent,old_path_sent):
        return False
    
    return True

def populateReachability(as2round2pfx2latency,r,pfx,min_time,max_time,pfx2time2as2Reachability):

    data = []
    l = sorted(pfx2time2as2Reachability[pfx].keys())
    idx_lo = bisect.bisect_left(l,min_time)
    idx_hi = bisect.bisect_left(l,max_time)
     
    times = l[idx_lo:idx_hi]
    for t in times:
        for asn in pfx2time2as2Reachability[pfx][t]:
            latency = float(pfx2time2as2Reachability[pfx][t][asn])
            as2round2pfx2latency[asn][r][pfx].append((latency,t))

def populateRTRFeed_dave(as2round2pfx2path,r,pfx,min_time,max_time,pfx2time2RTR):

     data = []
     l = sorted(pfx2time2RTR[pfx].keys())
     idx_lo = bisect.bisect_left(l,min_time)
     idx_hi = bisect.bisect_left(l,max_time)
     
     times = l[idx_lo:idx_hi]
     for t in times:
          for d in pfx2time2RTR[pfx][t]:
               data.append(d)

     for d in data:
          filpath = d[0]
          vp = d[1]
          unix_time = d[2]
          ipPath = d[4]
          path = d[3]
          
          prev_asn = '0'
          for asn in filpath:
               if asn==prev_asn or asn==RIOT:
                    continue
               if asn in MUX_ASN:
                    prev_asn = asn
                    continue
               idx = filpath.index(asn)
               P = Path_Simple('',filpath[idx:],vp,'rtr',filpath,unix_time,path,ipPath)
               if asn in as2round2pfx2path:
                    if r in as2round2pfx2path[asn]:
                         if pfx in as2round2pfx2path[asn][r]:
                              p = as2round2pfx2path[asn][r][pfx]
                              #p.VPs.append((vp,filpath,path,ipPath))
                              p.VPs.append((vp,unix_time))
                              if (not P.__eq__(p)) and (P not in p.alt_path_list):
                                   p.alt_path_list.append(P)
                         else:
                              as2round2pfx2path[asn][r][pfx] = P
                    else:
                         as2round2pfx2path[asn][r][pfx] = P
               else:
                    as2round2pfx2path[asn][r][pfx] = P
               prev_asn = asn
        

def getRTRFeed(pfx2time2RTR,f_revtr):

     for line in f_revtr:
          line = line.split()
          try:
               time = int(line[0])
          except ValueError:
               continue
          asPath = []
          ipPath = []
          if len(line) < 5:
               continue
          vp = str(line[2])
          pfx_ip =str(line[1])
          tmp = pfx_ip.split('.')
          tmp[3] = '0/24'
          pfx = ".".join(tmp)
          for i in range(3,len(line)):
               if i%3==0:
                    ipPath.append(line[i])
               if i%3==1:
                    asPath.append(line[i])
               if line[i]==RIOT:
                    break
          tup = getFilteredPath1(asPath,'rtr')
          if (tup is None):
               filpath = []
          else:
               filpath = tup[0]
          pfx2time2RTR[pfx][time].append((filpath,vp,time,asPath,ipPath))
     f_revtr.close()
    

def findHistoricalTRPath(as2round2pfx2path,asn,orig_path,r,pfx):

    if r in as2round2pfx2path[asn]:
        if pfx in as2round2pfx2path[asn][r]:
            path = as2round2pfx2path[asn][r][pfx]
            return path
        else:
            path = Path_RC([-1],'',[],0,[],[])
    else:
        path = Path_RC([-1],'',[],0,[],[])
     
    if orig_path.index(asn) < len(orig_path)-3:
        return path

     #path is empty: now make a complete pass
          
    path_list = []
    for r in as2round2pfx2path[asn]:
        if pfx in as2round2pfx2path[asn][r]:
            path_list.append(as2round2pfx2path[asn][r][pfx])

    if len(path_list)==0:
        return path

    prev_p = path_list[0]
     
    for i in range(len(path_list)):
        p = path_list[i]
        if (not p.__eq__(prev_p)):
            return path
        prev_p = p

    return prev_p
    

def prematurePoisoning(as2round2pfx2path,old_path,cur_path,cur_poisoning,prev_poisoning,\
                             pfx,r,prev_r,as2mux2AllPaths,p2pMap,mux,vp):

     asns_back_up = []
     for asn in prev_poisoning.split():
          if asn not in cur_poisoning.split():
               asns_back_up.append(asn)
     peerAS_cand_up = set()

     as_down = ''
     peerAS_cand_down = set()
     if len(cur_poisoning.split()) > 0:
          as_down = cur_poisoning.split()[-1]
          if as_down not in old_path:
               #induced path changes: peer withdrew announcement from all its neighbors
               for path in as2mux2AllPaths[as_down][mux]:
                    path = path.split()
                    if path[1] not in old_path:
                         continue
                    peerAS_cand_down.add((path[1],"old","induced"))
               for peer in p2pMap[as_down]:
                   if peer not in old_path:
                         continue
                   peerAS_cand_down.add((peer,"old","induced"))
               if len(peerAS_cand_down)==0 and len(asns_back_up)==0:
                    return False     
          else:
               #if len(cur_path)==0:
               pois_idx = old_path.index(as_down)
               peerAS_cand_down.add((old_path[pois_idx+1],"old","straight"))

     if len(asns_back_up) > 0:
          induced = True
          p_asn = ''
          for asn in asns_back_up:
               if asn in cur_path:
                    induced = False
                    p_asn = asn
                    break
          if (induced):
               for asn in asns_back_up:
                    for path in as2mux2AllPaths[asn][mux]:
                         path = path.split()
                         if path[1] not in cur_path:
                              continue
                         peerAS_cand_up.add((path[1],"new","induced"))
                    for peer in p2pMap[asn]:
                        if peer not in cur_path:
                            continue
                        peerAS_cand_up.add((peer,"new","induced"))
               if len(peerAS_cand_up)==0 and len(peerAS_cand_down)==0:
                    return False
          else:
               #if len(old_path)==0:
               pois_idx = cur_path.index(p_asn)
               peerAS_cand_up.add((cur_path[pois_idx+1],"new","straight"))

     peerAS_cand = peerAS_cand_up.union(peerAS_cand_down)
     for tup in peerAS_cand:
          asn = tup[0]
          pois = set(cur_poisoning.split()).union(set(prev_poisoning.split()))
          if tup[1]=="old":
                if pfx in as2round2pfx2path[asn][(prev_r,prev_status)]:
                     p_old = as2round2pfx2path[asn][(prev_r,prev_status)][pfx]
                else:
                     p_old = Path_Simple([-1],'','','',[],0,[],[])
                p_new = findHistoricalTRPath(as2round2pfx2path,asn,old_path,(r,status),pfx,pois)
          else:
               if pfx in as2round2pfx2path[asn][(r,status)]:
                    p_new = as2round2pfx2path[asn][(r,status)][pfx]
               else:
                    p_new = Path_Simple([-1],'','','',[],0,[],[])
               p_old = findHistoricalTRPath(as2round2pfx2path,asn,cur_path,(prev_r,prev_status),pfx,pois)
          path_type = tup[2]

          '''
          print vp + " " + asn
          print p_old
          print p_new
          print p_old.__eq__(p_new)
          '''
          if (not p_old.__eq__(p_new)):
               if path_type=="induced":
                    return True
               else:
                    #if path type is straight, may or may not be premature poisoning
                    #heuristic: if the difference in vantage points is huge, treat it as premature poisoning
                    #otherwise treat it as completely behind the poisoned/unpoisoned AS
                    diff = abs(len(p_old.VPs)-len(p_new.VPs))
                    if diff >= 10:
                         return True
          
     return False



def prematurePoisoning1(as2round2pfx2path,old_path,cur_path,cur_poisoning,prev_poisoning,\
                             pfx,r,prev_r,as2mux2AllPaths,p2pMap,mux,vp):

    peerAS_cand = set()
    asn_back_up = ''
    for asn in prev_poisoning.split():
        if asn==RIOT:
            continue
        if asn not in cur_poisoning.split():
            asn_back_up = asn
            break

    as_down = ''
    if cur_poisoning.split()[0] != RIOT and len(asn_back_up)==0:
        as_down = cur_poisoning.split()[-1]
        if as_down not in old_path:
               #induced path changes: peer withdrew announcement from all its neighbors
            for path in as2mux2AllPaths[as_down][mux]:
                path = path.split()
                if path[1] not in old_path:
                    continue
                peerAS_cand.add((path[1],"old","induced"))
            for peer in p2pMap[as_down]:
                if peer not in old_path:
                    continue
                peerAS_cand.add((peer,"old","induced"))
            if len(peerAS_cand)==0:
                return False     
        else:
               #if len(cur_path)==0:
            pois_idx = old_path.index(as_down)
            peerAS_cand.add((old_path[pois_idx+1],"old","straight"))

    if cur_poisoning.split()[0] != RIOT and len(asn_back_up) > 0:
        if asn_back_up not in cur_path:
             #induced path change
            for path in as2mux2AllPaths[asn_back_up][mux]:
                path = path.split()
                if path[1] not in cur_path:
                    continue
                peerAS_cand.add((path[1],"new","induced"))
            for peer in p2pMap[asn]:
                if peer not in cur_path:
                    continue
                peerAS_cand.add((peer,"new","induced"))
            if len(peerAS_cand)==0:
                return False
        else:
               #if len(old_path)==0:
            pois_idx = cur_path.index(asn_back_up)
            peerAS_cand.add((cur_path[pois_idx+1],"new","straight"))

    for tup in peerAS_cand:
        asn = tup[0]
        pois = set(cur_poisoning.split()).union(set(prev_poisoning.split()))
        if pfx in as2round2pfx2path[asn][prev_r]:
            p_old = as2round2pfx2path[asn][prev_r][pfx]
        else:
            #p_old = ""
            p_old = PATH([],[],"",[],0,[],[])
        if pfx in as2round2pfx2path[asn][r]:
            p_new = as2round2pfx2path[asn][r][pfx]
        else:
            #p_new = ""
            p_new = PATH([],[],"",[],0,[],[])

        if (not p_old.__eq__(p_new)):
            return True

        '''
        if p_old != p_new:
            return True
        '''

        '''
        if (not p_old.__eq__(p_new)):
            if path_type=="induced":
                return True
            else:
                diff = abs(len(p_old.VPs)-len(p_new.VPs))
                if diff >= 10:
                    return True
        '''            
    return False

def premPoisoning(as2round2pfx2path,poisonAS,isDown,old_path,cur_path,pfx,r,prev_r,p2pMap,mux,vp):

    peerAS_cand = set()

    if isDown: 
        if poisonAS not in old_path:
            #induced path changes: peer withdrew announcement from all its neighbors
            for peer in p2pMap[poisonAS]:
                if peer not in old_path:
                    continue
                peerAS_cand.add((peer,"old","induced"))
            if len(peerAS_cand)==0:
                return False     
        else:
               #if len(cur_path)==0:
            pois_idx = old_path.index(poisonAS)
            peerAS_cand.add((old_path[pois_idx+1],"old","straight"))

    else:
        if poisonAS not in cur_path:
             #induced path change
            for peer in p2pMap[poisonAS]:
                if peer not in cur_path:
                    continue
                peerAS_cand.add((peer,"new","induced"))
            if len(peerAS_cand)==0:
                return False
        else:
               #if len(old_path)==0:
            pois_idx = cur_path.index(poisonAS)
            peerAS_cand.add((cur_path[pois_idx+1],"new","straight"))

    for tup in peerAS_cand:
        asn = tup[0]
        if pfx in as2round2pfx2path[asn][prev_r]:
            p_old = as2round2pfx2path[asn][prev_r][pfx]
        else:
            p_old = PATH([],[],"",[],0,[],[])
        if pfx in as2round2pfx2path[asn][r]:
            p_new = as2round2pfx2path[asn][r][pfx]
        else:
            p_new = PATH([],[],"",[],0,[],[])

        if (not p_old.__eq__(p_new)):
            return True
        
    return False


def getRTRFile(pfx_ip_list,min_time,max_time,outputName):

    f_input = open('/tmp/historical_targets.txt', 'w')
    for ip in pfx_ip_list:
        f_input.write(ip + " " + str(min_time) + " " + str(max_time) + "\n")
    f_input.close()

    curPath = os.getcwd()
    os.chdir('/home/choffnes/reverse_traceroute/reverse_traceroute')
    cmd = 'jruby fetch_historical_revtr_for_umar.rb /tmp/historical_targets.txt > ' + str(outputName)
    os.system(cmd)
    cmd = 'cp ' + str(outputName) + ' ' + str(curPath)
    os.system(cmd)
    os.chdir(curPath)
    
def populateRTRFeed(as2round2pfx2path,vp2data,r,pfx):
    
    for v in vp2data:
        row = vp2data[v][-1]
        path = row[0].split()
        vp = row[1]
        feed = row[2]
        ipPath = row[3]
        unix_time = row[4]

        tup = getFilteredPath1(path,feed)
        if (tup is None):
            filpath = []
        else:
            filpath = tup[0]
            mux = tup[1]
               
        prev_asn = '0'
        for asn in filpath:
            if asn==prev_asn or asn==RIOT:
                continue
            if asn in MUX_ASN:
                prev_asn = asn
                continue
            idx = filpath.index(asn)
            P = Path_Simple('',filpath[idx:],vp,feed,filpath,unix_time,path,ipPath)

            if asn in as2round2pfx2path:
                if r in as2round2pfx2path[asn]:
                    if pfx in as2round2pfx2path[asn][r]:
                        p = as2round2pfx2path[asn][r][pfx]
                        #p.VPs.append((vp,filpath,path,ipPath))
                        p.VPs.append((vp,unix_time))
                        if (not P.__eq__(p)) and (P not in p.alt_path_list):
                            p.alt_path_list.append(P)
                    else:
                        as2round2pfx2path[asn][r][pfx] = P
                else:
                    as2round2pfx2path[asn][r][pfx] = P
            else:
                as2round2pfx2path[asn][r][pfx] = P
            prev_asn = asn
    
def altPathEqualsMainPath(altPath,P):

    if altPath.path_data==P.path_data or altPath.path_control==P.path_control:
        return True
    else:
        return False
            

def getPathFromFutureRounds(round2pfx2path,muxes,muxes_prep):

    for r in round2pfx2path:
        for f in round2pfx2path[r]:
            p = round2pfx2path[r][f]
            if p.mux not in muxes:
                continue
            allmuxesPresent = True
            for m in muxes:
                if m not in p.mux_list:
                    allmuxesPresent = False
                    break
            if allmuxesPresent is False:
                continue
            allRatiosEqual = True
            combs =  list(itertools.combinations(muxes,2))
            for c in combs:
                m1 = c[0]
                m2 = c[1]
                p1 = muxes_prep[muxes.index(m1)]
                p2 = muxes_prep[muxes.index(m2)]
                if p1==0 and p2==0:
                    ratio = 1.0
                else:
                    ratio = float(p1)/float(p2)
                p3 = p.prepend_status[p.mux_list.index(m1)]
                p4 = p.prepend_status[p.mux_list.index(m2)]
                if p3==0 and p4==0:
                    ratio1 = 1.0
                else:
                    ratio1 = float(p3)/float(p4)
                if not ratio==ratio1:
                    allRatiosEqual = False
                    break

            if allRatiosEqual is True:
                path = copy.deepcopy(p)
                path.prepend = muxes_prep[muxes.index(path.mux)]
                path.status = INFERRED
                return path
            else:
                continue

def getPathFromPairwiseVoting(round2pfx2path,muxes,muxes_prep,mux2path):

    #select the mux that wins the most 2-way contests
    #muxes and muxes_prep is the stuff that we have to check
    path = None
    mux2count = dict()
    mux2tot = dict()
    comb2PrepRatio = []
    twod_list = []
    for m in muxes:
        c = []
        for n in muxes:
            c.append(0)
        twod_list.append(c)
    combs =  list(itertools.combinations(muxes,2))
    for c in combs:
        p1 = muxes_prep[muxes.index(c[0])]
        p2 = muxes_prep[muxes.index(c[1])]
        c2 = comb2(c,p1,p2)
        comb2PrepRatio.append(c2)

    #for c in comb2PrepRatio:
    #    print c
        
    for r in round2pfx2path:
        for f in round2pfx2path[r]:
            p = round2pfx2path[r][f]
            combs =  list(itertools.combinations(p.mux_list,2))
            for c in combs:
                if p.mux not in c:
                    continue
                p1 = p.prepend_status[p.mux_list.index(c[0])]
                p2 = p.prepend_status[p.mux_list.index(c[1])]
                c2 = comb2(c,p1,p2)
                if c2 in comb2PrepRatio:
                    if c[0] in mux2tot:
                        mux2tot[c[0]] += 1
                    else:
                        mux2tot[c[0]] = 1
                    if c[1] in mux2tot:
                        mux2tot[c[1]] += 1
                    else:
                        mux2tot[c[1]] = 1
                    
                    m = p.mux
                    if m in mux2count:
                        mux2count[m] += 1
                    else:
                        mux2count[m] = 0

                    if m==c[0]:
                        twod_list[muxes.index(m)][muxes.index(c[1])] += 1
                    else:
                        twod_list[muxes.index(m)][muxes.index(c[0])] += 1


    #print twod_list
    #print mux2count
    #print mux2tot

    winner_mux = ''
    for a in twod_list:
        win = True
        for b in a:
            if a.index(b)==twod_list.index(a):
                continue
            if b==0:
                win = False
                break
        if win==True:
            winner_mux = muxes[twod_list.index(a)]
            break

    if not winner_mux:
        win = 0.0
        winner_mux = ''
        for m in mux2count:
            if float(mux2count[m])/float(mux2tot[m]) > win:
                win = float(mux2count[m])/float(mux2tot[m])
                winner_mux = m

    if not winner_mux:
        return path

    if winner_mux in mux2path:
        path = copy.deepcopy(mux2path[winner_mux])
    else:
        for r in round2pfx2path:
            for f in round2pfx2path[r]:
                p = round2pfx2path[r][f]
                if p.mux==winner_mux:
                    path = copy.deepcopy(p)

    if path is None:
        return path
    path.status = INFERRED
    path.prepend = muxes_prep[muxes.index(winner_mux)]
    return path

def getShortestPath(muxes,muxes_prep,mux2path):

    minLength = 1000
    mux = ''
    for m in muxes:
        if m not in mux2path:
            continue
        p = mux2path[m]
        if len(p.path_control) > 0:
            l = len(p.path_control) + muxes_prep[muxes.index(m)]
        else:
            l = len(p.path_data) + muxes_prep[muxes.index(m)]
        if l < minLength:
            minLength = l
            mux = m

    if not mux:
        return None
    else:
        mux2path[mux]
        
    
    
def findShortestMux(mux2Path,round,shortest_status):

    sublist = prep_MUX[0:round]
    shortMuxes = []
    minLen = 1000
    for mux in mux2Path:
        if len(mux2Path[mux].path_control) > 0:
            pathLen = len(mux2Path[mux].path_control)
        else:
            pathLen = len(mux2Path[mux].path_data)
        if mux in sublist:
            pathLen += sublist.count(mux)
        if pathLen <= minLen:
            shortMuxes.append(mux)
            minLen = pathLen

    if shortest_status==SET:
        return shortMuxes
    else:
        return shortMuxes[0]


def mapAS2Comb(as2combmap, asn, neigh_list):
    combs = list(itertools.combinations(neigh_list,2))
    for comb in combs:
        as2combmap[asn][comb] = 1


'''
def findShortestMux(mux2Path, round,i, shortest_status):

    shortMuxes = []
    minLen = 1000
    for mux in mux2Path:
        pathLen = len(mux2Path[mux].path_control)
        if round > 0:
            mux_idx = MUX_NAMES.index(mux)
            if mux_idx <= i:
                pathLen += round
            else:
                pathLen += (round-1)
        if pathLen <= minLen:
            shortMuxes.append(mux)
            minLen = pathLen

    if shortest_status==SET:
        return shortMuxes
    else:
        return shortMuxes[0]
'''

'''
def getChosenMux(round2paths,round,i):
OB
    paths = round2paths[round]
    if not paths and round==0:
        return None
    if not paths:
        paths = round2paths[0]
    if round > 0:
        if i < len(paths):
            muxTaken = paths[i].mux
        else:
            muxTaken = paths[0].mux
    else:
        muxTaken = paths[0].mux

    return muxTaken
'''

def getPathChosenByNeigh(round2pfx2path,round,pfx,prev_asn,mux2path,mux_responsible_list,isPicked,picked_mux):

    muxes = []
    muxes_prep = []
    for m in mux_responsible_list:
        muxes.append(m[0])
        muxes_prep.append(m[1])
    #prev_asn is the upstream AS which this AS announced to
    if round not in round2pfx2path:
        path = ''
    else:
        if pfx in round2pfx2path[round]:
            path = round2pfx2path[round][pfx]
            if isPicked and picked_mux != path.mux:
                for p in path.alt_path_list:
                    if p.mux==picked_mux:
                        path = p
                        break
                
        else:
            path = ''

    if not path:
        if len(muxes)==1:
            path = copy.deepcopy(mux2path[muxes[0]])
            path.prepend = muxes_prep[0]
            path.status = INFERRED
        else:
            #if we're able to find this list of muxes elsewhere with the same ratio of prepend lengths, use it
            #otherwise use pairwise voting
            path = getPathFromFutureRounds(round2pfx2path,muxes,muxes_prep) 
            if path is None:
                path = getPathFromPairwiseVoting(round2pfx2path,muxes,muxes_prep,mux2path)
            if path is None:
                path = getShortestPath(muxes,muxes_prep,mux2path)
                
    return path

def getChosenMux(round2path,round,prev_asn):

    #prev_asn is the upstream AS which this AS announced to
    if round not in round2path:
        path = ''
    else:
        path = round2path[round]
    if not path and round==0:
        return None
    if not path:
        keys = round2path.keys()
        prev_key = keys[0]
        for k in keys:
            if k>=round:
                break
            prev_key = k

        #if prev mux wasn't prepended, pick it again. Otherwise pick the mux just after it
        prev_mux = round2path[prev_key].mux
        idx = round2path[k].mux_list.index(prev_mux)
        if round2path[prev_key].prepend==round2path[k].prepend_status[idx]:
            path = round2path[prev_key]
        else:
            path = round2path[k]

    if not path:
        return None

    if not path.alt_path_list or path.up_asn==prev_asn:
        return path.mux
    else:
        for p in path.alt_path_list:
            if p.up_asn==prev_asn:
                return p.mux
    return path.mux


def getPrependStatus(round):

    prep_status = [0]*len(MUX_NAMES)
    sublist = prep_MUX[0:round]
    for m in sublist:
        p = sublist.count(m)
        idx = MUX_NAMES.index(m)
        prep_status[idx] = p

    return prep_status


def fillMuxMap(asn, path, as2mux2Path):

    if path.mux not in as2mux2Path[asn]:
        #print asn
        #print path.mux
        as2mux2Path[asn][path.mux] = copy.deepcopy(path)
        P = as2mux2Path[asn][path.mux]
        if P.prepend == 0:
            return
        if len(P.path_control)>0:
            l = len(P.path_control)
            P.path_control = P.path_control[0:l-P.prepend]
            P.prepend = 0



def getFilteredPath1(path,feed):
    r = list(path)
    r.reverse()

    mux = ''
    for asn in r:
	    if asn in muxASToName:
		    mux  = muxASToName[asn]
		    break

    if not mux:
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


def getFilteredPath(aspath,ippath,feed,vp):
    #returns:
    #1) filtered AS path
    #2) mux
    #3) for each AS, it's ingress data point, i.e., the ingress through which it fowards the prefix announcement (this is a dictionary)
    r = list(aspath)
    r.reverse()

    mux = ''
    for asn in r:
	    if asn in muxASToName:
		    mux  = muxASToName[asn]
		    break

    if not mux:
	    return None

    filpath = []
    as2ingress = dict()

    if feed=='rv':
        vp_asn = vp.split(',')[0][1:]
        vp_asn_ingress = (vp.split(',')[1][0:len(vp.split(',')[1])-1].split()[0]).split("'")[1]
        as2ingress[vp_asn] = vp_asn_ingress 
        prev_asn = '0'
        for asn in aspath:
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
		    
        return (filpath,mux,as2ingress)
    
    prev_asn = '0'
    isPrev0 = False
    for i in range(len(aspath)):
        asn = aspath[i]
        if asn==prev_asn or asn=='0' or asn=='3303':
            if asn=='0':
                isPrev0 = True
            else:
                isPrev0 = False
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
        if isPrev0 is False:
            as2ingress[asn] = ippath[i]
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

    return (filpath,mux,as2ingress)
