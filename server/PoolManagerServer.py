#!/usr/bin/env python


#
#
#  This file is started in from systemctl 
#  edit this file to change start up directives. 
# /etc/systemd/system/PoolManager.service
# use sudo systemctl commands to start and stop the service 
# i.e. sudo systemctl [start|stop|enable|disable] PoolManager.service

import datetime
import time
import asyncio
import json
import logging
import websockets
import sqlite3
import time
import RPi.GPIO as GPIO
import os
import glob
import requests


logging.basicConfig()

STATE = {'value': 0}
TEST = {'value' : 'clicked'}

times = {'pump','lights','copper','ion'}

USERS = set()

def d_print(*args):
	global DEBUG
	if (DEBUG):
		print(' '.join(str(p) for p in args))

def setDeviceStatus(bcm,on,invert):
	if testMode:
		return
	output  = on
	if invert  == "Y":
		output = 1 if on == 0 else 0
	GPIO.setmode(GPIO.BCM)   
	GPIO.setup(bcm, GPIO.OUT) 
	GPIO.output(bcm, output) 
	
def getDeviceInfo(name):
	curs = conn.cursor()
	stat = curs.execute("select * from device where name = ?",(name,))
	row = curs.fetchone()
	curs.close()
	return row
	
def setDeviceData(name,data,mode):
	curs = conn.cursor()
	stat = curs.execute("update device set data = ?, mode = ? where name = ?",(data,mode,name))
	conn.commit()
	curs.close()
	
def getDeviceStatus(bcm,invert):
	GPIO.setmode(GPIO.BCM)   
	GPIO.setup(bcm, GPIO.OUT) 
	status = not GPIO.input(bcm) if invert == "Y" else GPIO.input(bcm) 
	return status 
	
def convertOnOff(s):
	return "1" if s =='on' else "0"	
	
def convertBool(b):
	return "1" if b else "0"	


def convertStr(s):
	return s == '1'


def time_event(name,jsn = True):
	days = [["--:--","--:--"] for x in range(7)]
	curs = conn.cursor()
	curs.execute("select s.day,s.start,s.stop from schedule as s join device as d on s.device_id = d.id where d.name = ? order by s.day",(name,))
	rows = curs.fetchall()
	for r in rows:
		days[r[0]][0] = r[1]
		days[r[0]][1] = r[2]
	reply = ""
	for da in days:
		reply += "<td>{0} {1}</td>".format(da[0],da[1])
	curs.close()
	d = {'type': 'time', 'id' : name,'times': reply}
	return json.dumps(d) if jsn else d 
	
def pump_event(jsn = True):
	info = getDeviceInfo('pump')
	status = getDeviceStatus(info[3],info[5])
	d = {'type': 'pump', 'on' : convertBool(status), 'auto' : info[6] }
	return json.dumps(d) if jsn else d 

def temp_event(jsn = True):
	d = {'type': 'temp', 'atemp' : temps[0],'ptemp' : temps[1] }
	return json.dumps(d) if jsn else d 
	
def test_event(jsn = True):
	d_print(convertBool(testMode) )
	d = {'type':'test','testmode':  convertBool(testMode) }
	return json.dumps(d) if jsn else d 

def lights_event(jsn = True):
	info = getDeviceInfo("lights")
	d = info[4].split('|')
	#d = data.split('|')
	status = convertBool(getDeviceStatus(info[3],info[5]))
	#content = "{0},{1},{2}\n".format(convertBool(status),data,info[6])
	dt = '{:%I:%M}'.format(duskTime.time())
	d = {'type': 'lights', 'on' : status,'auto' : info[6],'color' : d[0],'duskon':d[1],'timer':d[2],'dusktime':dt}
	return json.dumps(d) if jsn else d 
	
def chlor_event(jsn = True):
	cInfo = getDeviceInfo('copper')
	iInfo = getDeviceInfo('ion')
	copper = getDeviceStatus(cInfo[3],cInfo[5])
	ion = getDeviceStatus(iInfo[3],iInfo[5])
	onStatus = copper or ion
	dStatus = "--"
	if onStatus:
		d = getDeviceInfo('copper_dir') if copper else getDeviceInfo('ion_dir')
		dStatus = "up" if getDeviceStatus(d[3],d[5]) else "down"
	data = convertBool(not copper) if onStatus else cInfo[4]
	content = "{0},{1},{2},{3}\n".format(convertBool(onStatus),data,cInfo[6],iInfo[6])
	d = {'type': 'chlor', 'on' : convertBool(onStatus),'copper' : data,'copperauto' : cInfo[6],'ionauto' : iInfo[6],'direction' : dStatus }
	return json.dumps(d) if jsn else d 
	
def stopChlor():
	cInfo = getDeviceInfo('copper')
	iInfo = getDeviceInfo('ion')
	if getDeviceStatus(cInfo[3],cInfo[5]) or getDeviceStatus(iInfo[3],iInfo[5]):
		cDir = getDeviceInfo('copper_dir')
		iDir = getDeviceInfo('ion_dir')
		setDeviceStatus(cInfo[3],0,cInfo[5])
		setDeviceStatus(iInfo[3],0,iInfo[5])
		setDeviceStatus(cDir[3],0,cDir[5])
		setDeviceStatus(iDir[3],0,iDir[5])		
	
def setPump(d): 
	name = d['action']
	on = convertStr(d['on'])
	mode = convertStr(d['mode'])
	dInfo = getDeviceInfo(name)
	setDeviceStatus(dInfo[3],on,dInfo[5])
	setDeviceData(name,dInfo[4],mode)
	if not on:
		stopChlor()
	return on
		
		
def read_temp_raw(f):
   with open(f, 'r') as f:
	   lines = f.readlines()                                  
   return lines
   
   

	   

async def read_temp():

	try:
		c = 0
		temp = 0.0
		updated = False
		for f in device_file:
			lines = read_temp_raw(f)
			while 'YES' not in lines[0]:
				time.sleep(0.2)
				lines = read_temp_raw(f)
			equals_pos = lines[1].find('t=')                        # find temperature in the details
			if equals_pos != -1:
				temp_string = lines[1][equals_pos+2:]
				temp = round(float(temp_string) / 1000.0,1)         # convert to Celsius
				updated = True
				temps[c] = temp
			c = c + 1 
	except:
		updated = True
		temps[0] = 0.0	
		temps[1] = 0.0	
	
	if updated:
		await notifyTemp() 
		
async def setLightSequence(d): #(bcm,seq,invert):
	DELAY = .1
	dInfo = getDeviceInfo(d['action'])
	invert = dInfo[5]
	bcm = dInfo[3]
	s = int(d['seq'])
	for i in range(0,s):
		setDeviceStatus(bcm,0,invert)
		time.sleep(DELAY)
		setDeviceStatus(bcm,1,invert)
		time.sleep(DELAY)

def setLights(d): 
	name = d['action']
	seq = d['seq']
	timer = d['timer']
	duskOn = d['duskon']
	on = convertStr(d['on'])
	mode = convertStr(d['mode'])
	data = seq+'|'+duskOn+'|'+timer
	dInfo = getDeviceInfo(name)
	setDeviceStatus(dInfo[3],on,dInfo[5])
	setDeviceData(name,data,mode)
	di = dInfo[4].split("|")
	d_print (d)
	d_print (di)
	d_print ("compare",d['mode'] != convertStr(dInfo[6]))
	mode = d['mode'] == '1' and ((d['mode'] != convertStr(dInfo[6])) or (duskOn != di[1]) or (timer != di[2]))
	d_print ("mode = ",mode)
	return {'seq':on and seq != di[0],'mode': mode }


def setAutoChlor(d):
	name = d['name']
	mode = convertStr(d['mode'])
	cInfo = getDeviceInfo(name)
	setDeviceData(name,cInfo[4],mode)
	return mode
	

def setChlor(d):
	pInfo = getDeviceInfo("pump")
	if getDeviceStatus(pInfo[3],pInfo[5]) == 1:
		action = d['type']
		on = convertStr(d['on'])
		cmode = int(d['copperauto'])
		imode = int(d['ionauto'])
		cInfo = getDeviceInfo('copper')
		iInfo = getDeviceInfo('ion')
		cDir = getDeviceInfo('copper_dir')
		iDir = getDeviceInfo('ion_dir')
		if on == 0:
			setDeviceStatus(cInfo[3],on,cInfo[5])
			setDeviceStatus(iInfo[3],on,iInfo[5])
			setDeviceStatus(cDir[3],0,cDir[5])
			setDeviceStatus(iDir[3],0,iDir[5])
		else:
			setDeviceStatus(cDir[3],0,cDir[5])
			setDeviceStatus(iDir[3],0,iDir[5])
			if action == '0':
				setDeviceStatus(iInfo[3],0,iInfo[5])
				setDeviceStatus(cInfo[3],1,cInfo[5])
			else:
				setDeviceStatus(iInfo[3],1,iInfo[5])
				setDeviceStatus(cInfo[3],0,cInfo[5])
		setDeviceData('copper',action,cmode)
		setDeviceData('ion',action,imode)			
	
def setSchedule(d):
	allDays = convertStr(d['all'])
	name = d['name']
	start = d['start']
	stop = d['stop']
	day = int(d['day'])
	clearDay = convertStr(d['clear'])
	curs = conn.cursor()
	if allDays:
		curs.execute("delete from schedule where device_id = (select id from device where name = ?)",(name,))
		conn.commit()
		if not clearDay:
			for i in range(0,7):
				curs.execute("insert into schedule (device_id,day,start,stop) select id,?,?,? from device where name =?",(i,start,stop,name))
				conn.commit()
	else:
		curs.execute("delete from schedule where day = ? and  device_id = (select id from device where name = ?)",(day,name))
		conn.commit()
		if not clearDay:
			curs.execute("insert into schedule (device_id,day,start,stop) select id,?,?,? from device where name =?",(day,start,stop,name))
			conn.commit()	
	curs.close()	

def fixDate(dt):
	d_print("dt = ",dt)
	s= dt.split('T')
	d_print (s)
	s = (s[1].split('+')[0][0:5]).split(':')
	d_print("s[0] = ",s[0])
	s[0] = "24" if s[0] == "00" else s[0]
	d_print (s)
	dt = datetime.datetime.now()
	d_print("current date = ",dt)
	dst = 0 if time.localtime().tm_isdst > 0 else 1
	tzDiff = -(int(time.altzone/3600)+dst)
	d_print ("tzDiff= ",tzDiff)
	dt = dt.replace(hour = int(s[0])+tzDiff,minute = int(s[1]),second = 0,microsecond = 0)
	return dt	
	
async def updateDusk():
	d_print ("in updateDusk")
	global duskNextUpdate,duskUpdated,duskTime

	if duskNextUpdate  == None or not duskUpdated or duskNextUpdate < datetime.datetime.now():
		timeOut = 0
		duskTime = None;
		duskUpdated = False
		while  not duskUpdated and timeOut < 5:
			r = requests.get("https://api.sunrise-sunset.org/json?lat=42.8789&lng=-71.3812&date=today&formatted=0")
			data  = r.json()
			d_print(data)
			if "OK" in data['status'] :
				d_print ("OK")
				duskUpdated = True;
				results = data['results']
				d_print(results)
				duskTime = (fixDate(results['sunset']))
				d_print ("duskTime = ",duskTime)
				dt = datetime.datetime.now()
				duskNextUpdate = datetime.datetime(dt.year,dt.month,dt.day,1,0,0,0) + datetime.timedelta(days=1)
			timeOut += 1
	d_print ("duskUpdated = ",duskUpdated)
	

def toggleDev(dev):
	if testMode:
		return 
	info = getDeviceInfo(dev)
	GPIO.setmode(GPIO.BCM)   
	GPIO.setup(info[3], GPIO.OUT) 
	state = (GPIO.input(info[3]) + 1 ) % 2
	d_print ("state = {}",state)
	GPIO.output(info[3], state) 
	
""" 
	This is a hack to handle in bound messages from google assistant 
    This function will not be needed once the messaging is standardized. 
"""	
def fixMessage(msg):
	m = json.loads(msg)
	d_print ("m = ",m)
	if not 'cmd' in m:
		return msg
	if m['device'] == 'pump':
	  return  json.dumps({'action': 'pump', 'on' : convertOnOff(m['action']),'mode' : '0'})
	elif m['device'] == 'light':
		l = json.loads(lights_event())
		if 'action' in m:
			return  json.dumps({'action': l['type'], 'on' : convertOnOff(m['action']),'seq' : l['color'],'mode': 0, 'duskon':l['duskon'],'timer':l['timer']})
		else:
			if 'color' in m:
				return  json.dumps({'action': l['type'], 'on' : '1','seq' : m['color'],'mode': 0, 'duskon':l['duskon'],'timer':l['timer']})
			else:
				return msg
	elif m['device'] == 'thermometer':
		return json.dumps({'action':'temp'});
	elif m['device'] == 'status':
		return json.dumps({'action':'status','location':m['location']});
	else:
		return msg


async def togglePump():
	d_print("toggling the pump")
	d = getDeviceInfo("pump")
	status = getDeviceStatus(d[3],d[5])	
	data =  {'action': 'pump', 'on': convertBool(not status), 'mode': '0'}
	d_print("data = ",data)
	setPump(data)
	await notifyPump()
	await notifyChlor()
	d_print ("Done toggle pump")


""" This function handles the pushbutton change event The button is mommentary
"""

def on_button_event(channel):
	global cmdAction
	d_print('Falling event detected')
	d_print (channel)
	d_print (cmdAction)
	if not cmdAction:
		aLoop.create_task(togglePump())

	
	
async def toggleChlor():  
	d_print ("in toggle") 
	cInfo = getDeviceInfo('copper')
	iInfo = getDeviceInfo('ion')
	copper = getDeviceStatus(cInfo[3],cInfo[5])
	ion = getDeviceStatus(iInfo[3],iInfo[5])
	onStatus = copper or ion
	d_print ("Chlor = {}", onStatus)
	if(onStatus):
		if(copper):
			d_print("copper")
			toggleDev("copper_dir")
		else: 
			d_print ("ion")
			toggleDev("ion_dir")
		await notifyChlor()

async def checkSchedules(dName=None):
	global cmdAction
	d_print ("in check schedule")
	currentDay = (datetime.datetime.today().weekday() + 1) % 7
	now = datetime.datetime.now()
	curs = conn.cursor()
	if (dName is None) :
		curs.execute("select d.id,d.name,s.start,s.stop,d.pin,d.bcm,d.data,d.invert, d.mode from schedule as s join device as d on d.id = s.device_id where s.day = ? order by d.id;",(currentDay,))
	else:
		curs.execute("select d.id,d.name,s.start,s.stop,d.pin,d.bcm,d.data,d.invert, d.mode from schedule as s join device as d on d.id = s.device_id where d.name = ? and s.day = ? order by d.id;",(dName,currentDay,))
	rows = curs.fetchall()
	for r in rows:
		d_print (r)
		if r[8] == AUTO:
			d_print ("in auto")
			st = r[2].split(":")
			ss = r[3].split(":")
			start = now.replace(hour=int(st[0]),minute=int(st[1]),second = 0,microsecond = 0)
			stop = now.replace(hour=int(ss[0]),minute=int(ss[1]),second = 0,microsecond = 0)
			run = now >= start and now < stop
			name = r[1]
			status = getDeviceStatus(r[5],r[7])
			if name in ('copper','ion'):
				if  status == 0 and run:
					pump = getDeviceInfo("pump")
					if getDeviceStatus(pump[3],pump[5]):
						cmdAction = True
						setDeviceStatus(r[5],1,r[7])
				elif status == 1 and not run:
					stopChlor()
				await notifyChlor()
			else:
				if name == "lights": 	#handle dusk
					d_print("checking dusk")
					d = r[6].split("|")
					d_print ("d = ",d)
					d_print ("duskUpdated = ",duskUpdated)
				
					if d[1] == '1' and duskUpdated:
						eDuskTime = duskTime + datetime.timedelta(hours= int(d[2]))
						d_print(now,duskTime,eDuskTime,datetime.timedelta(hours= int(d[2])))
						run = now >= duskTime and now < duskTime + datetime.timedelta(hours= int(d[2]))
						d_print ("run = ",run)
				if  status == 0 and run:
					cmdAction = True
					setDeviceStatus(r[5],1,r[7])
				elif status == 1 and not run:
					cmdAction = True
					setDeviceStatus(r[5],0,r[7])
					if name == "pump":
						stopChlor()
						await notifyChlor()
				if name == "pump":
					await notifyPump()
				elif name == "lights":
					await notifyLights()
				elif name == "chlor":
					await notifyChlor()
	curs.close()
	if cmdAction:
		await asyncio.sleep(1)
		cmdAction = False

# This is a simple sleep interrupt to allow for quick scheduling of async-coroutines
# mainly the push button calls.  This allows the push button to be more responsive.   
async def clock():
	while True:
		await asyncio.sleep(clockTick)

#Master Pool Scheduler
async def poolScheduler():
	global duskUpdated
	tTick = 0  #toggle 
	sTick = 0  #schedule
	dTick = 0  #dusk
	await read_temp()
	await checkSchedules()
	await toggleChlor()
	await updateDusk() 
	while True:
		await asyncio.sleep(30)
		await read_temp()
		if tTick ==2:
			await toggleChlor()
		if sTick ==1:
			await checkSchedules()
		if dTick == 30 or (not duskUpdated and sTick ==1):
			await updateDusk()
		tTick  = (tTick + 1) % 3
		sTick = (sTick + 1)% 2
		dTick = (dTick + 1) % 31

		
async def notifyTemp():
	if USERS:
		message = temp_event()
		await asyncio.wait([u.send(message) for u in USERS])
		

async def notifySchedule(name):
	if USERS:
		message = time_event(name)
		await asyncio.wait([u.send(message) for u in USERS])
		
async def notifyPump():
	if USERS:
		message = pump_event()
		await asyncio.wait([u.send(message) for u in USERS])
	
async def notifyLights():
	if USERS:
		message = lights_event()
		await asyncio.wait([u.send(message) for u in USERS])
		
		
async def notifyChlor():
	if USERS:
		message = chlor_event()
		await asyncio.wait([u.send(message) for u in USERS])
	
async def notifyTime():
	if USERS:
			message = time_event()
			await asyncio.wait([u.send(message) for u in USERS])

async def getLocationStatus(location,websocket):
	
	if location == 'pool':
		await websocket.send(json.dumps({'pool':{'success':1,'test':test_event(False),'temperature':temp_event(False),'pump':pump_event(False),'light':lights_event(False),'chloronation':chlor_event(False)}}))
	else:
		await websocket.send(json.dumps({location:{'success' : 0}}))
	
	

async def initConnection(websocket):
	await websocket.send(test_event())
	await websocket.send(temp_event())
	await websocket.send(pump_event())
	await websocket.send(lights_event())
	await websocket.send(chlor_event())	
	for t in times:			
		await websocket.send(time_event(t))		


async def register(websocket,init):
	d_print (websocket)
	USERS.add(websocket)
	d_print (init)
	if init:
		await initConnection(websocket)

async def unregister(websocket):
	if websocket in USERS :
		USERS.remove(websocket)

async def pumpCmd(data):
	if setPump(data) == 1:
		await checkSchedules()	
	await notifyPump()
	await notifyChlor()
	
async def tempCmd(data):
	await websocket.send(temp_event())
	
async def lightsCmd(data):
	result = setLights(data)
	d_print(result)
	if result['seq']:
		await setLightSequence(data)
	if result['mode']:	
		await checkSchedules(data['action'])
	await notifyLights()
		
async def chlorautoCmd(data):
	d_print("cholorauto called")
	if (setAutoChlor(data) ==1):
		await checkSchedules(data['name'])
	await notifyChlor()
	
async def chlorCmd(data):
	setChlor(data)
	await notifyChlor()		
	
async def scheduleCmd(data):
	setSchedule(data)
	await notifySchedule(data['name'])
	await checkSchedules()
	
async def statusCmd(data):
	await getLocationStatus(data['location'],websocket)	
	
async def unknownCmd(data):
	logging.error("unsupported event: {}", data)
	d_print("unsupported event: {}", data)
	
async def poolManager(websocket, path):
	global cmdAction
	d_print (path)
	await register(websocket, path == "/webclient")
	try:
		async for message in websocket:
			cmdAction = True
			d_print ("web = ",cmdAction)
			d_print ("message = ",message)
			data = json.loads(fixMessage(message))
			d_print("data = ",data)
			action = data['action']
			await commands.get(action,unknownCmd)(data)
			await asyncio.sleep(1)
			cmdAction = False
			d_print ("web = ",cmdAction)
	except Exception as e:
		pass
		d_print ("Exception Happened")
		d_print(e)
#		logging.error("exception caught")
	finally:
		await unregister(websocket)


# #################################################
# # 				main						  #
# #################################################
	

GPIO.setwarnings(False)
MANUAL = 0
AUTO = 1	
dbPath = '/home/pi/database/pool.db'
global conn
global temps
global devicefile
global duskNextUpdate
global testMode
global aLoop
global clockTick
global cmdAction
global DEBUG
global commands


DEBUG = not True
cmdAction = False
testMode = False
temps = [0.0,0.0]
device_file = ["",""]
conn = sqlite3.connect(dbPath)
os.system('modprobe w1-gpio')                              	# load one wire communication device kernel modules
os.system('modprobe w1-therm')
duskTime = None
duskNextUpdate = None
duskUpdated = False											# taken out below until thermometers are hooked up
base_dir = '/sys/bus/w1/devices/'                          # point to the address
pushBtn = 15
clockTick = .5

commands = {"pump":pumpCmd,
			"temp":tempCmd,
			"lights":lightsCmd,
			"chlorauto":chlorautoCmd,
			"chlor":chlorCmd,
			"schedule":scheduleCmd,
			"status":statusCmd
		   }

try:
	device_folder1 = glob.glob(base_dir + '28-01131a66*')[0]   # find device with address starting from 28*
	device_folder2 = glob.glob(base_dir + '28-01131a67*')[0]   # find device with address starting from 28*
	device_file = [device_folder1 + '/w1_slave',device_folder2 + '/w1_slave']
except:
	device_file = ["",""]
# see  /etc/apache2/sites-enabled
# and  /etc/apache2/sites-available/000-default.conf
#  for web service configuration 
aLoop = asyncio.get_event_loop()

GPIO.setmode(GPIO.BCM)
GPIO.setup(pushBtn, GPIO.IN, pull_up_down=GPIO.PUD_UP) 
GPIO.add_event_detect(pushBtn, GPIO.FALLING, callback=on_button_event,bouncetime=1000)	

aLoop.run_until_complete( asyncio.wait([
	websockets.serve(poolManager, 'localhost', 6789)
	,poolScheduler()
	,clock()
	]))
asyncio.get_event_loop().run_forever()
