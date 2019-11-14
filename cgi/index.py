#!/usr/bin/python

import sys, cgi, cgitb,json,websockets,asyncio,html

async def makeRequest(data): 
	async with websockets.connect("ws://mammothpool.hopto.org:33369/ws2/control") as ws:
		await ws.send(data)
		result = await ws.recv()
		print ("Content-type:application/json\r\n\r\n")
		print (result)

asyncio.run(makeRequest(sys.stdin.read()))

