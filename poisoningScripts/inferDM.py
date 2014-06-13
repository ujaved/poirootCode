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
import random
from helper import  getFilteredPath1

timeInterval2jobs = dict()
job2time = defaultdict(set)
job2task = defaultdict(set)
time2switch2switch2demand = defaultdict(lambda: defaultdict(lambda: defaultdict()))
timeInterval2JobsEnding = defaultdict(list)
job2switch = dict()
num_switches = 500 #indexed 1 to 500
min_time = 90000
switch2switch = defaultdict(list)
task2time = dict()
timeIntervals = set()
file_f = open(sys.argv[1],'r')
for line in file_f:
    fields = line.rstrip().split()
    try : time = int(fields[0])
    except ValueError: continue
    max_time = time
    timeIntervals.add(time)
    jobid = int(fields[1])
    taskid = int(fields[2])
    job2time[jobid].add(time)
    job2task[jobid].add(taskid)
    switch = random.randint(1,num_switches)
    job2switch[jobid] = switch
    if taskid in task2time:
        (start_time, elapse_time) = task2time[taskid]
        task2time[taskid] = (start_time,time)
    else:
        task2time[taskid] = (time,time)

file_f.close()
total_time = max_time - min_time + 300

for job in job2task:
    if len(job2task[job]) <= 20:
        continue
    num_external_tasks = len(job2task[job])-20
    external_tasks = random.sample(job2task[job],num_external_tasks)
    switch = job2switch[job]
    
    for tsk in external_tasks:
        s = random.randint(1,num_switches)
        while (s==switch):
            s = random.randint(1,num_switches)
        switch2switch[switch].append((s,tsk))

for job in job2time:
    t = sorted(list(job2time[job]))
    endingTime = t[-1]
    timeInterval2JobsEnding[endingTime].append(job)


for tm in timeInterval2JobsEnding:
    for job in timeInterval2JobsEnding[tm]:
         masterSwitch = job2switch[job]
        for s in switch2switch[masterSwitch]:
            task = s[1]
            if task not in job2task[job]:
                continue
            tsk_duration = task2time[task][1] - task2time[task][0] + 300
            tsk_duration_norm = float(tsk_duration)/total_time
            neigh_switch = s[0]
            if neigh_switch in time2switch2switch2demand[tm][masterSwitch]:
                time2switch2switch2demand[tm][masterSwitch][neigh_switch] += tsk_duration_norm
            else:
                time2switch2switch2demand[tm][masterSwitch][neigh_switch] = tsk_duration_norm
            


        
        
    
                    
            

        
