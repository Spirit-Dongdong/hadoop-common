#Licensed to the Apache Software Foundation (ASF) under one
#or more contributor license agreements.  See the NOTICE file
#distributed with this work for additional information
#regarding copyright ownership.  The ASF licenses this file
#to you under the Apache License, Version 2.0 (the
#"License"); you may not use this file except in compliance
#with the License.  You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

#Unless required by applicable law or agreed to in writing, software
#distributed under the License is distributed on an "AS IS" BASIS,
#WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#See the License for the specific language governing permissions and
#limitations under the License.
"""define MapReduce as subclass of Service"""

# -*- python -*-

import os, copy, time

from service import *
from hodlib.Hod.nodePool import *
from hodlib.Common.desc import CommandDesc
from hodlib.Common.util import get_exception_string

class MapReduceExternal(MasterSlave):
  """dummy proxy to external MapReduce instance"""

  def __init__(self, serviceDesc, workDirs):
    MasterSlave.__init__(self, serviceDesc, workDirs,None)
    self.launchedMaster = True
    self.masterInitialized = True
    
  def getMasterRequest(self):
    return None

  def getMasterCommands(self, serviceDict):
    return []

  def getAdminCommands(self, serviceDict):
    return []

  def getWorkerCommands(self, serviceDict):
    return []

  def getMasterAddrs(self):
    attrs = self.serviceDesc.getfinalAttrs()
    addr = attrs['mapred.job.tracker']
    return [addr]

  def needsMore(self):
    return 0

  def needsLess(self):
    return 0

  def setMasterParams(self, list):
    raise NotImplementedError
  
  def getInfoAddrs(self):
    attrs = self.serviceDesc.getfinalAttrs()
    addr = attrs['mapred.job.tracker']
    k,v = addr.split( ":")
    # infoaddr = k + ':' + attrs['mapred.job.tracker.info.port']
    # After Hadoop-2185
    # Note: earlier,we never respected mapred.job.tracker.http.bindAddress
    infoaddr = attrs['mapred.job.tracker.http.bindAddress']
    return [infoaddr]
  
class MapReduce(MasterSlave):

  def __init__(self, serviceDesc, workDirs,required_node):
    MasterSlave.__init__(self, serviceDesc, workDirs,required_node)

    self.masterNode = None
    self.masterAddr = None
    self.infoAddr = None
    self.workers = []
    self.required_node = required_node

  def isLaunchable(self, serviceDict):
    hdfs = serviceDict['hdfs']
    if (hdfs.isMasterInitialized()):
      return True
    return False
  
  def getMasterRequest(self):
    req = NodeRequest(1, [], False)
    return req

  def getMasterCommands(self, serviceDict):

    hdfs = serviceDict['hdfs']

    cmdDesc = self._getJobTrackerCommand(hdfs)
    return [cmdDesc]

  def getAdminCommands(self, serviceDict):
    return []

  def getWorkerCommands(self, serviceDict):

    hdfs = serviceDict['hdfs']

    cmdDesc = self._getTaskTrackerCommand(hdfs)
    return [cmdDesc]

  def setMasterNodes(self, list):
    node = list[0]
    self.masterNode = node

  def getMasterAddrs(self):
    return [self.masterAddr]

  def getInfoAddrs(self):
    return [self.infoAddr]

  def getWorkers(self):
    return self.workers

  def requiredNode(self):
    return self.required_host

  def setMasterParams(self, list):
    dict = self._parseEquals(list)
    self.masterAddr = dict['mapred.job.tracker']
    k,v = self.masterAddr.split(":")
    self.masterNode = k
    # self.infoAddr = self.masterNode + ':' + dict['mapred.job.tracker.info.port']
    # After Hadoop-2185
    self.infoAddr = dict['mapred.job.tracker.http.bindAddress']
  
  def _parseEquals(self, list):
    dict = {}
    for elems in list:
      splits = elems.split('=')
      dict[splits[0]] = splits[1]
    return dict

  def _getJobTrackerPort(self):
    sd = self.serviceDesc
    attrs = sd.getfinalAttrs()
    if not 'mapred.job.tracker' in attrs:
      return ServiceUtil.getUniqPort()
    
    v = attrs['mapred.job.tracker']
    try:
      [n, p] = v.split(':', 1)
      return int(p)
    except:
      print get_exception_string()
      raise ValueError, "Can't find port from attr mapred.job.tracker: %s" % (v)

  def _getJobTrackerInfoPort(self):
    sd = self.serviceDesc
    attrs = sd.getfinalAttrs()
    # if not 'mapred.job.tracker.info.port' in attrs:
    if 'mapred.job.tracker.http.bindAddress' not in attrs:
      return ServiceUtil.getUniqPort()

    # p = attrs['mapred.job.tracker.info.port']
    p = attrs['mapred.job.tracker.http.bindAddress']
    try:
      return int(p)
    except:
      print get_exception_string()
      # raise ValueError, "Can't find port from attr mapred.job.tracker.info.port: %s" % (p)
      raise ValueError, "Can't find port from attr mapred.job.tracker.http.bindAddress: %s" % (p)

  def _setWorkDirs(self, workDirs, envs, attrs, parentDirs, subDir):
    local = []
    system = None
    temp = None
    dfsclient = []
    
    for p in parentDirs:
      workDirs.append(p)
      workDirs.append(os.path.join(p, subDir))
      dir = os.path.join(p, subDir, 'mapred-local')
      local.append(dir)
      if not system:
        system = os.path.join(p, subDir, 'mapred-system')
      if not temp:
        temp = os.path.join(p, subDir, 'mapred-temp')
      dfsclientdir = os.path.join(p, subDir, 'dfs-client')
      dfsclient.append(dfsclientdir)
      workDirs.append(dfsclientdir)
    # FIXME!! use csv
    attrs['mapred.local.dir'] = ','.join(local)
    attrs['mapred.system.dir'] = 'fillindir'
    attrs['mapred.temp.dir'] = temp
    attrs['dfs.client.buffer.dir'] = ','.join(dfsclient)


    envs['HADOOP_ROOT_LOGGER'] = ["INFO,DRFA",]


  def _getJobTrackerCommand(self, hdfs):
    sd = self.serviceDesc

    parentDirs = self.workDirs
    workDirs = []
    attrs = sd.getfinalAttrs()
    envs = sd.getEnvs()

    #self.masterPort = port = self._getJobTrackerPort()
    if 'mapred.job.tracker' not in attrs:
      attrs['mapred.job.tracker'] = 'fillinhostport'

    #self.infoPort = port = self._getJobTrackerInfoPort()
    # if 'mapred.job.tracker.info.port' not in attrs:
    #   attrs['mapred.job.tracker.info.port'] = 'fillinport'

    attrs['fs.default.name'] = hdfs.getMasterAddrs()[0]
    # Addressing Hadoop-2815,
    if 'mapred.job.tracker.http.bindAddress' not in attrs:
      attrs['mapred.job.tracker.http.bindAddress'] = 'fillinhostport'

    self._setWorkDirs(workDirs, envs, attrs, parentDirs, 'mapred-jt')

    dict = { 'name' : 'jobtracker' }
    dict['program'] = os.path.join('bin', 'hadoop')
    dict['argv'] = ['jobtracker']
    dict['envs'] = envs
    dict['pkgdirs'] = sd.getPkgDirs()
    dict['workdirs'] = workDirs
    dict['final-attrs'] = attrs
    dict['attrs'] = sd.getAttrs()
    cmd = CommandDesc(dict)
    return cmd

  def _getTaskTrackerCommand(self, hdfs):

    sd = self.serviceDesc

    parentDirs = self.workDirs
    workDirs = []
    attrs = sd.getfinalAttrs()
    envs = sd.getEnvs()
    jt = self.masterAddr

    if jt == None:
      raise ValueError, "Can't get job tracker address"

    attrs['mapred.job.tracker'] = jt
    attrs['fs.default.name'] = hdfs.getMasterAddrs()[0]

    # Adding the following. Hadoop-2815
    if 'mapred.task.tracker.report.bindAddress' not in attrs:
      attrs['mapred.task.tracker.report.bindAddress'] = 'fillinhostport'
    if 'mapred.task.tracker.http.bindAddress' not in attrs:
      attrs['mapred.task.tracker.http.bindAddress'] = 'fillinhostport'

    self._setWorkDirs(workDirs, envs, attrs, parentDirs, 'mapred-tt')

    dict = { 'name' : 'tasktracker' }
    dict['program'] = os.path.join('bin', 'hadoop')
    dict['argv'] = ['tasktracker']
    dict['envs'] = envs
    dict['pkgdirs'] = sd.getPkgDirs()
    dict['workdirs'] = workDirs
    dict['final-attrs'] = attrs
    dict['attrs'] = sd.getAttrs()
    cmd = CommandDesc(dict)
    return cmd

