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

task2time = dict()
time2numtasks = dict()
min_time = 90000
file_f = open(sys.argv[1],'r')
for line in file_f:
    fields = line.rstrip().split()
    try : time = int(fields[0])
    except ValueError: continue
    task = int(fields[2])
    if task in task2time:
        (start_time, elapse_time) = task2time[task]
        task2time[task] = (start_time,time)
    else:
        task2time[task] = (time,time)

for t in task2time:
    tm = task2time[t][1] - task2time[t][0] 
    if tm in time2numtasks:
        time2numtasks[tm] += 1
    else:
        time2numtasks[tm] = 1

total_time = 0.0
for tm in time2numtasks:
    total_time += (tm*time2numtasks[tm])

num_tasks = len(task2time)
prevCumJobs = 0
prevCumTime = 0.0
for tm in sorted(time2numtasks.keys()):
    numCumJobs = time2numtasks[tm] + prevCumJobs
    cumTime = tm*time2numtasks[tm] + prevCumTime 
    print str(cumTime/total_time) + " " + str(float(numCumJobs)/num_tasks)
    prevCumJobs = numCumJobs
    prevCumTime = cumTime
sys.exit()



        
        
    
                    
            

        
