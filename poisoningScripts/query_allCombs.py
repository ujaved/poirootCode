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
import sqlite3
from collections import defaultdict
import operator
from helper import Path,getFilteredPath,SENTINEL,MUX_ASN,RIOT,muxASToName,MUX_NAMES,mapAS2Comb,fillMuxMap,getPathChosenByNeigh,comb_info,INFERRED
import itertools
import copy


def findInducedPathChangeCandidates(as2NeighCombData,as2NeighComb_stats,as2upstream, as2neigh):

    t = 0.8
    cand = []
    for asn in as2NeighComb_stats:
        for comb in as2NeighComb_stats[asn]:
            count = as2NeighComb_stats[asn][comb]['total']
            policy_count = as2NeighComb_stats[asn][comb]['policy']
            if policy_count < t*count:
                continue
            up = []
            for a in as2upstream[asn]:
                if a in as2NeighComb_stats and len(as2neigh[a])>1:
                    up.append(a)
            if len(up)==0:
                continue
            '''
            bothInSamepath = False
            for c in as2NeighCombData[asn][comb]:
                if comb[0] in c.p2.path_control or comb[0] in c.p2.path_data:
                    bothInSamepath = True
                    break
                if comb[1] in c.p1.path_control or comb[1] in c.p1.path_data:
                    bothInSamepath = True
                    break
            if bothInSamepath is True:
                continue
            '''
            cand.append((asn,comb,up))
    return cand


def makePlot_policyThresh_ASPolicy(as2NeighComb_stats):

    as_tot = float(len(as2NeighComb_stats))
    thresh = []
    percentASes1 = []
    percentASes2 = []
    for i in range(0,105,5):
        thresh.append(float(i)/100.0)
    for t in thresh:
        asCountPolicy1 = 0
        asCountPolicy2 = 0
        for asn in as2NeighComb_stats:
            for comb in as2NeighComb_stats[asn]:
                count = as2NeighComb_stats[asn][comb]['total']
                policy_count = as2NeighComb_stats[asn][comb]['policy']
                if policy_count >= t*count:
                    asCountPolicy1 += 1
                    break
        percentASes1.append(float(asCountPolicy1)/as_tot)

        for asn in as2NeighComb_stats:
            for comb in as2NeighComb_stats[asn]:
                count = as2NeighComb_stats[asn][comb]['total']
                policy_count = as2NeighComb_stats[asn][comb]['policy']
                equal_count = as2NeighComb_stats[asn][comb]['equal']
                if policy_count >= t*(count-equal_count):
                    asCountPolicy2 += 1
                    break
        percentASes2.append(float(asCountPolicy2)/as_tot)

    for t in thresh:
        print str(t) + " " + str(percentASes1[thresh.index(t)]) + " " + str(percentASes2[thresh.index(t)])

def getFilteredPathLen(path):

    l = 0
    if len(path.path_control) > 0:
        for i in range(0,len(path.path_control)):
            l += 1
            if path.path_control[i]==RIOT:
                break
        return l
    else:
        return len(path.path_data) 
            

def altPathEqualsMainPath(altPath,P):

    if altPath.path_data==P.path_data or altPath.path_control==P.path_control:
        return True
    else:
        return False

def getPathFirstHop(path):

    if len(path.path_control) > 0:
        return path.path_control[1]
    if len(path.path_data) > 0:
        return path.path_data[1]

    return None



conn = sqlite3.connect('../data/prepend_data/2012-05-16 15:30:49.578289')
c = conn.cursor()

as2mux2Path = defaultdict(lambda: defaultdict())
as2neigh = defaultdict(set)
as2mux2neigh = defaultdict(lambda: defaultdict(set))
as2comb = defaultdict(lambda: defaultdict())
as2round2pfx2path = defaultdict(lambda: defaultdict(lambda: defaultdict()))

as2upstream = defaultdict(set)
path_file_f = open(sys.argv[1],'r')
for line in path_file_f:
    fields = line.rstrip().split("|")
    path = fields[2].split()
    for i in range(len(path)):
        if i==0:
            prev_asn = path[i]
            continue
        asn = path[i]
        as2upstream[asn].add(prev_asn)
        prev_asn = asn

for r in range(0,200):    
    if r==0:
        c.execute("select prefix,prepend_mux,prepend_length,mux_seen,observedPath,feed,status,unix_time,vpoint,prepend_round from ASGraph where prepend_round=? \
               order by prefix DESC",(r,))
    else:
        c.execute("select prefix,prepend_mux,prepend_length,mux_seen,observedPath,feed,status,unix_time,vpoint,prepend_round from ASGraph where prepend_round=? \
               order by prefix",(r,))

    #the idea here is that we want to update the as2comb map after all the sentinels are done. All the sentinels should always be the
    #first group in the cursor
    combMapped = 0
    muxMapFilled = 0
    res = c.fetchall()

    muxesToPrepend = [] 
    prependLengths = []
    for i in range(len(res)):
        row = res[i]
        pfx = row[0]
        feed = row[5]
        s = row[4].split()
        status = row[6]
        time = row[7]
        vpoint = row[8]
        prepend_mux = row[1]
        prepend_length = row[2]

        if len(s) < 3:
            continue
        z = list(s)
        z.reverse()
        mux = row[3]
        for asn in z:
            if asn in muxASToName:
                mux = muxASToName[asn]
                break

        filpath = getFilteredPath(s,mux,feed)
        if filpath is None:
            continue

        if status==SENTINEL:
            prev_asn = '0'
            for asn in filpath:
                if asn==prev_asn or asn==RIOT:
                    continue
                if asn in MUX_ASN:
                    
                    if prev_asn=='3267' and asn=='20388':
                            print P
                    
                    as2neigh[prev_asn].add(asn)
                    as2mux2neigh[prev_asn][mux].add(asn)
                    prev_asn = asn
                    continue
                idx = filpath.index(asn)
                if feed=='rv':
                    P = Path(pfx, prev_asn, mux, 0, filpath[idx:],'',[mux],[0],[],r,filpath,vpoint)
                else:
                    P = Path(pfx, prev_asn, mux, 0, '',filpath[idx:],[mux],[0],[],r,filpath,vpoint)
                '''
                if prev_asn=='292':
                    print P
                '''

                if asn in as2mux2Path:
                    if mux in as2mux2Path[asn]:
                        if len(as2mux2Path[asn][mux].path_control)==0 and feed=='rv':
                            as2mux2Path[asn][mux].path_control = filpath[idx:]
                        elif feed=='rv':
                            if P not in as2mux2Path[asn][mux].alt_path_list and not altPathEqualsMainPath(P,as2mux2Path[asn][mux]):
                                as2mux2Path[asn][mux].alt_path_list.append(P)
                        elif len(as2mux2Path[asn][mux].path_data)==0 and feed=='ftr':
                            as2mux2Path[asn][mux].path_data = filpath[idx:]
                        elif feed=='ftr':
                            if P not in as2mux2Path[asn][mux].alt_path_list and not altPathEqualsMainPath(P,as2mux2Path[asn][mux]):
                                as2mux2Path[asn][mux].alt_path_list.append(P)
                    else:
                        as2mux2Path[asn][mux] = P
                else:
                    as2mux2Path[asn][mux] = P
                if prev_asn is not '0':
                    
                    if prev_asn=='3267' and asn=='20388':
                            print P
                            
                    as2neigh[prev_asn].add(asn)
                    as2mux2neigh[prev_asn][mux].add(asn)
                prev_asn = asn
        else:
            if combMapped==0:
                combMapped = 1
                for asn in as2neigh:
                    mapAS2Comb(as2comb,asn,list(as2neigh[asn]))

            if muxMapFilled==0:
                muxMapFilled = 1
                for asn in as2round2pfx2path:
                    for ro in as2round2pfx2path[asn]:
                        for pf in as2round2pfx2path[asn][ro]:
                            fillMuxMap(asn,as2round2pfx2path[asn][ro][pf],as2mux2Path)

            if (i+1)<len(res):
                next_time = res[i+1][7]
                next_vpoint = res[i+1][8]
            if time==next_time and vpoint==next_vpoint and (i+1)<len(res):
                muxesToPrepend.append(prepend_mux)
                prependLengths.append(prepend_length)
                continue
            else:
                muxesToPrepend.append(prepend_mux)
                prependLengths.append(prepend_length)
                if mux not in muxesToPrepend:
                    continue
                prep = prependLengths[muxesToPrepend.index(mux)]
                prev_asn = '0'
                for asn in filpath:
                    if asn==prev_asn or asn==RIOT:
                        continue
                    if asn in MUX_ASN:
                        
                        if prev_asn=='3267' and asn=='20388':
                            print P
                        
                        as2neigh[prev_asn].add(asn)
                        as2mux2neigh[prev_asn][mux].add(asn)
                        prev_asn = asn
                        continue
                    idx = filpath.index(asn)
                    if feed=='rv':
                        P = Path(pfx, prev_asn, mux, prep, filpath[idx:],'',muxesToPrepend,prependLengths,[],r,filpath,vpoint)
                    else:
                        P = Path(pfx, prev_asn, mux, prep, '',filpath[idx:],muxesToPrepend,prependLengths,[],r,filpath,vpoint)
                    '''
                    if asn=='2153' and r==39 and pfx=='184.164.254.0/24':
                        print "path: " + str(P)
                        if pfx in as2round2pfx2path['2153'][39]:
                            a = as2round2pfx2path['2153'][39]['184.164.254.0/24']
                            print "already path: " + str(a)
                            print "alt_paths:"
                            for b in a.alt_path_list:
                                print b
                    '''
                    if asn in as2round2pfx2path:
                        if r in as2round2pfx2path[asn]:
                            if pfx in as2round2pfx2path[asn][r]:
                                p = as2round2pfx2path[asn][r][pfx]
                                if mux==p.mux:
                                    if len(p.path_control)==0 and feed=='rv':
                                        p.path_control = filpath[idx:]
                                    elif feed=='rv':
                                        if P not in p.alt_path_list and not altPathEqualsMainPath(P,p):
                                            p.alt_path_list.append(P)
                                    elif len(p.path_data)==0 and feed=='ftr':
                                        p.path_data = filpath[idx:]
                                    elif feed=='ftr':
                                        if P not in p.alt_path_list and not altPathEqualsMainPath(P,p):
                                            p.alt_path_list.append(P)
                                else:
                                    #an example of as announcing different muxes to differents ASes
                                    #when the mux is different, it's just a different path
                                    
                                    if len(p.path_control)==0 and feed=='rv':
                                        #prefer the new path as the main path since it has a control path
                                        P.alt_path_list.append(p)
                                        as2round2pfx2path[asn][r][pfx] = P
                                    elif P not in p.alt_path_list:
                                        p.alt_path_list.append(P)
                                '''
                                if len(as2round2pfx2path[asn][r][pfx].path_data)==0:
                                    as2round2pfx2path[asn][r][pfx].path_data = filpath[idx:]
                                else:
                                    if not (mux==as2round2pfx2path[asn][r][pfx].mux):
                                        if P not in as2round2pfx2path[asn][r][pfx].alt_path_list:
                                            as2round2pfx2path[asn][r][pfx].alt_path_list.append(P)
                                '''
                            else:
                                as2round2pfx2path[asn][r][pfx] = P
                        else:
                            as2round2pfx2path[asn][r][pfx] = P
                    else:
                        as2round2pfx2path[asn][r][pfx] = P
                    if prev_asn is not '0':
                        
                        if prev_asn=='3267' and asn=='20388':
                            print P
                        
                        as2neigh[prev_asn].add(asn)
                        as2mux2neigh[prev_asn][mux].add(asn)
                    prev_asn = asn
                muxesToPrepend = []
                prependLengths = []



#as2mux2Path gives you a prepend-free path to each mux from the AS if it were available. This path is not necessarily available to the AS
#at any given time. Sometimes you would have a prepend-free path to a mux in as2round2path that won't be available in as2mux2Path. We have to take care
#of that here


for a in as2neigh:
    for b in as2neigh[a]:
        as2upstream[b].add(a)
            
for asn in as2round2pfx2path:
    for r in as2round2pfx2path[asn]:
        for pfx in as2round2pfx2path[asn][r]:
            path = as2round2pfx2path[asn][r][pfx]
            if path.mux not in as2mux2Path[asn]:
                as2mux2Path[asn][path.mux] = copy.deepcopy(path)
                P = as2mux2Path[asn][path.mux]
                P.status = INFERRED
                P.prepend = 0
            for p in path.alt_path_list:
                if p.mux not in as2mux2Path[asn]:
                    as2mux2Path[asn][p.mux] = copy.deepcopy(p)
                    P = as2mux2Path[asn][p.mux]
                    P.status = INFERRED
                    P.prepend = 0

'''
for asn in as2neigh:
    print "ASN: " + asn
    print as2neigh[asn]

sys.exit()
'''

'''
for asn in as2round2pfx2path:
    print "AS: " + asn
    for mux in as2mux2Path[asn]:
        print "mux: " + str(mux) + "  " + str(as2mux2Path[asn][mux])
        if not as2mux2Path[asn][mux].alt_path_list:
            continue
        print "alt paths:"
        for p in as2mux2Path[asn][mux].alt_path_list:
            print p
    for r in as2round2pfx2path[asn]:
        print "round: " + str(r)
        for pfx in as2round2pfx2path[asn][r]:
            print "pfx: " + str(pfx)
            print as2round2pfx2path[asn][r][pfx]
            if not as2round2pfx2path[asn][r][pfx].alt_path_list:
                continue
            print "alt paths:"
            for p in as2round2pfx2path[asn][r][pfx].alt_path_list:
                print p
sys.exit()
'''

as2NeighCombData = defaultdict(lambda: defaultdict(list))
for r in range(0,200):
 

    '''
    print "----------------------------------"
    print "round: " + str(r)
    print "----------------------------------"
    '''    
    
    for asn in as2round2pfx2path:
        if len(as2neigh[asn]) < 2:
            continue

        ''' 
        print "---------------------------------------"
        print "ASN: " + asn
        '''
        
        for pfx in as2round2pfx2path[asn][r]:
            firstHop = set()
            P = as2round2pfx2path[asn][r][pfx]
            if len(P.mux_list) < 2:
                continue

            ''' 
            print "prefix: " + pfx
            print "path: " + str(P)
            print "mux2neigh: " + str(as2mux2neigh[asn])
            '''
            
            for m in P.mux_list:
                if m in as2mux2neigh[asn]:
                    for n in as2mux2neigh[asn][m]:
                        #if n in MUX_ASN:
                        #    continue
                        firstHop.add(n)
            if len(firstHop) < 2:
                continue
            #print "firstHop: " + str(firstHop)
            combs =  list(itertools.combinations(firstHop,2))
            for comb in combs:
                if comb[0] not in as2round2pfx2path or comb[1] not in as2round2pfx2path:
                    continue
                #disregard the combination that doesn't have the path's first hop in it
                h = getPathFirstHop(P)
                if h not in comb or h is None:
                    continue
                #each asn in the firstHop can be responsible for more than one mux
                m1 = []
                m2 = []
                for m in P.mux_list:
                    if m not in as2mux2neigh[asn]:
                        continue
                    if comb[0] in as2mux2neigh[asn][m]:
                        m1.append((m,P.prepend_status[P.mux_list.index(m)]))
                    if comb[1] in as2mux2neigh[asn][m]:
                        m2.append((m,P.prepend_status[P.mux_list.index(m)]))
                
                #print "muxes for " + str(comb[0]) + ": " + str(m1)
                #print "muxes for " + str(comb[1]) + ": " + str(m2)
                
                p1 = getPathChosenByNeigh(as2round2pfx2path[comb[0]],r,pfx,asn,as2mux2Path[comb[0]],m1,comb[0]==h,P.mux)
                p2 = getPathChosenByNeigh(as2round2pfx2path[comb[1]],r,pfx,asn,as2mux2Path[comb[1]],m2,comb[1]==h,P.mux)

                #print "path for " + str(comb[0]) + ": " + str(p1)
                #print "path for " + str(comb[1]) + ": " + str(p2)
                as2NeighCombData[asn][comb].append(comb_info(comb,p1,p2,P))

#still have to take care of the case where the neighbor is not picked and we have alt_paths
#idea: keep count of alt_paths with the same mux if you don't wanna do shortest path
                
as2NeighComb_stats = defaultdict(lambda: defaultdict(lambda: defaultdict()))
for asn in as2NeighCombData:
    for comb in as2NeighCombData[asn]:
        count = 0
        policy_count = 0
        equal_count = 0
        shortest_count = 0
        #print "comb: " + str(comb)
        for c in as2NeighCombData[asn][comb]:
            count += 1
            if len(c.path_picked.path_control)>0:
                neigh_picked = c.path_picked.path_control[1]
            else:
                neigh_picked = c.path_picked.path_data[1]
            if len(c.p1.path_control)>0:
                p1_vpasn = c.p1.path_control[0]
            else:
                p1_vpasn = c.p1.path_data[0]
            if len(c.p2.path_control)>0:
                p2_vpasn = c.p2.path_control[0]
            else:
                p2_vpasn = c.p2.path_data[0]
                
            if neigh_picked==p1_vpasn:
                path_picked = c.p1
                path_not_picked = c.p2
            else:
                path_picked = c.p2
                path_not_picked = c.p1
                
            pp_len = getFilteredPathLen(path_picked) + path_picked.prepend
            pnp_len = getFilteredPathLen(path_not_picked) + path_not_picked.prepend

            if comb[0] in c.p2.path_control or comb[0] in c.p2.path_data:
                pp_len = pnp_len
            if comb[1] in c.p1.path_control or comb[1] in c.p1.path_data:
                pp_len = pnp_len

            if pp_len==pnp_len:
                equal_count += 1
            elif pp_len > pnp_len:
                policy_count += 1
            elif pp_len < pnp_len:
                shortest_count += 1

        as2NeighComb_stats[asn][comb]['policy'] = policy_count
        as2NeighComb_stats[asn][comb]['shortest'] = shortest_count
        as2NeighComb_stats[asn][comb]['equal'] = equal_count
        as2NeighComb_stats[asn][comb]['total'] = count


cand = findInducedPathChangeCandidates(as2NeighCombData,as2NeighComb_stats,as2upstream,as2neigh)
print len(cand)
sys.exit()
for c in cand:
    asn = c[0]
    comb = c[1]
    upstream = c[2]
    print "ASN: " + str(asn)
    print "comb: " + str(comb)
    print "upstream: " + str(upstream)
    
    for d in as2NeighCombData[asn][comb]:
            print d

#makePlot_policyThresh_ASPolicy(as2NeighComb_stats)

'''
for asn in as2NeighCombData:
    print "ASN: " + asn
    for comb in as2NeighCombData[asn]:
        print "comb: " + str(comb)
        for c in as2NeighCombData[asn][comb]:
            print c
'''
            

        
