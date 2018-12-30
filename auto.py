import os, sys
import subprocess, signal
import json
import threading, psutil
import time
from shutil import copy
import re
from subprocess import call
import datetime
import urllib.request, urllib.error, urllib.parse
from shutil import get_terminal_size as tsize

from crop import crop
from ref import ref
from zoom import zoom



def auto(*args):


	def printErase(arg):
		tsiz = tsize()[0]
		print("\r{}{}".format(arg, " " * (tsiz-len(arg))), end="\r\n" if tsiz <= len(arg) else "")




	def parseArg(arg):
		if arg[0:2] != "--":
			return True
		kwargs[arg[2:].split("=",2)[0]] = arg[2:].split("=",2)[1] if len(arg[2:].split("=",2)) > 1 else True
		return False

	kwargs = {}
	args = list(filter(parseArg, args))
	foldername = args[0] if len(args) > 0 else os.path.splitext(os.path.basename(max([os.path.join("../../saves", basename) for basename in os.listdir("../../saves") if basename not in { "_autosave1.zip", "_autosave2.zip", "_autosave3.zip" }], key=os.path.getmtime)))[0]
	savenames = args[1:] or [ foldername ]

	possiblePaths = [
		"C:/Program Files/Factorio/bin/x64/factorio.exe",
		"D:/Program Files/Factorio/bin/x64/factorio.exe",
		"C:/Games/Factorio/bin/x64/factorio.exe",
		"D:/Games/Factorio/bin/x64/factorio.exe",
		"../../bin/x64/factorio",
		"C:/Program Files (x86)/Steam/steamapps/common/Factorio/bin/x64/factorio.exe",
		"D:/Program Files (x86)/Steam/steamapps/common/Factorio/bin/x64/factorio.exe"
	]
	try:
		factorioPath = next(x for x in map(os.path.abspath, [kwargs["factorio"]] if "factorio" in kwargs else possiblePaths) if os.path.isfile(x))
	except StopIteration:
		raise Exception("Can't find factorio.exe. Please pass --factorio=PATH as an argument.")

	print("factorio path: {}".format(factorioPath))

	psutil.Process(os.getpid()).nice(psutil.ABOVE_NORMAL_PRIORITY_CLASS if os.name == 'nt' else 5)

	basepath = kwargs["basepath"] if "basepath" in kwargs else "../../script-output/FactorioMaps"
	workthread = None

	workfolder = os.path.join(basepath, foldername)
	print("output folder: {}".format(os.path.relpath(workfolder, "../..")))


	if "noupdate" not in kwargs:
		try:
			print("checking for updates")
			latestUpdates = json.loads(urllib.request.urlopen('https://cdn.jsdelivr.net/gh/L0laapk3/FactorioMaps@latest/updates.json', timeout=10).read())
			with open("updates.json", "r") as f:
				currentUpdates = json.load(f)

			updates = []
			majorUpdate = False
			currentVersion = (0, 0, 0)
			for verStr, changes in currentUpdates.items():
				ver = tuple(map(int, verStr.split(".")))
				if currentVersion[0] < ver[0] or (currentVersion[0] == ver[0] and currentVersion[1] < ver[1]):
					currentVersion = ver
			for verStr, changes in latestUpdates.items():
				if verStr not in currentUpdates:
					ver = tuple(map(int, verStr.split(".")))
					updates.append((verStr, changes))
					if currentVersion[0] < ver[0] or (currentVersion[0] == ver[0] and currentVersion[1] < ver[1]):
						majorUpdate = True
			updates.sort(key = lambda u: u[0])
			if len(updates) > 0:
				print("")
				print("")
				print("================================================================================")
				print("")
				print(("  an " + ("important" if majorUpdate else "incremental") + " update has been found!"))
				print("")
				print("  heres what changed:")

				padding = max(map(lambda u: len(u[0]), updates))
				print(padding)
				for update in updates:
					print("    %s: %s" % (update[0].rjust(padding), update[1] if isinstance(update[1], str) else str(("\r\n      " + " "*padding).join(update[1]))))
				print("")
				print("")
				print("  Download: https://mods.factorio.com/mod/L0laapk3_FactorioMaps")
				print("            OR")
				print("            https://github.com/L0laapk3/FactorioMaps")
				if majorUpdate:
					print("")
					print("You can dismiss this by using --noupdate (not recommended)")
				print("")
				print("================================================================================")
				print("")
				print("")
				if majorUpdate:
					sys.exit(1)


		except Exception as e:
			print("Failed to check for updates:")
			print("", e)


	if os.path.isfile("autorun.lua"):
		os.remove("autorun.lua")


	print("enabling FactorioMaps mod")
	def changeModlist(newState):
		done = False
		with open("../mod-list.json", "r") as f:
			modlist = json.load(f)
		for mod in modlist["mods"]:
			if mod["name"] == "L0laapk3_FactorioMaps":
				mod["enabled"] = newState
				done = True
		if not done:
			modlist["mods"].append({"name": "L0laapk3_FactorioMaps", "enabled": newState})
		with open("../mod-list.json", "w") as f:
			json.dump(modlist, f, indent=2)

	changeModlist(True)



	def printGameLog(pipe):
		with os.fdopen(pipe) as reader:
			while True:
				line = reader.readline().rstrip('\n')
				if "err" in line.lower() or "warn" in line.lower() or "exc" in line.lower():
					printErase("[GAME] {}".format(line))


	logIn, logOut = os.pipe()
	logthread = threading.Thread(target=printGameLog, args=[logIn])
	logthread.daemon = True
	logthread.start()




	datapath = os.path.join(workfolder, "latest.txt")

	try:

		for index, savename in enumerate(savenames):



			printErase("cleaning up")
			if os.path.isfile(datapath):
				os.remove(datapath)




			printErase("building autorun.lua")
			if (os.path.isfile(os.path.join(workfolder, "mapInfo.json"))):
				with open(os.path.join(workfolder, "mapInfo.json"), "r") as f:
					mapInfoLua = re.sub(r'"([^"]+)" *:', lambda m: '["'+m.group(1)+'"] = ', f.read().replace("[", "{").replace("]", "}"))
			else:
				mapInfoLua = "{}"
			if (os.path.isfile(os.path.join(workfolder, "chunkCache.json"))):
				with open(os.path.join(workfolder, "chunkCache.json"), "r") as f:
					chunkCache = re.sub(r'"([^"]+)" *:', lambda m: '["'+m.group(1)+'"] = ', f.read().replace("[", "{").replace("]", "}"))
			else:
				chunkCache = "{}"

			with open("autorun.lua", "w") as target:
				with open("autorun.template.lua", "r") as template:
					for line in template:
						target.write(line.replace("%%NAME%%", foldername + "/").replace("%%CHUNKCACHE%%", chunkCache.replace("\n", "\n\t")).replace("%%MAPINFO%%", mapInfoLua.replace("\n", "\n\t")).replace("%%DATE%%", datetime.date.today().strftime('%d/%m/%y')))


			printErase("starting factorio")
			p = subprocess.Popen([factorioPath, '--load-game', os.path.abspath(os.path.join("../../saves", savename+".zip")), '--disable-audio', '--no-log-rotation'], stdout=logOut)
			time.sleep(1)
			if p.poll() is not None:
				print("WARNING: running in limited support mode trough steam. Consider using standalone factorio instead.\n\tPlease confirm the steam 'start game with arguments' popup.")

			if not os.path.exists(datapath):
				while not os.path.exists(datapath):
					time.sleep(0.4)

			latest = []
			with open(datapath, 'r') as f:
				for line in f:
					latest.append(line.rstrip("\n"))

			
			firstOtherInputs = latest[0].split(" ")
			firstOutFolder = firstOtherInputs.pop(0).replace("/", " ")
			waitfilename = os.path.join(basepath, firstOutFolder, "Images", firstOtherInputs[0], firstOtherInputs[1], "done.txt")

			
			isKilled = [False]
			def waitKill(isKilled):
				while not isKilled[0]:
					if os.path.isfile(waitfilename):
						isKilled[0] = True
						printErase("killing factorio")
						if p.poll() is None:
							p.kill()
						else:
							os.system("taskkill /im factorio.exe")
						break
					time.sleep(0.4)

			killthread = threading.Thread(target=waitKill, args=(isKilled,))
			killthread.daemon = True
			killthread.start()



			if workthread and workthread.isAlive():
				#print("waiting for workthread")
				workthread.join()





			for jindex, screenshot in enumerate(latest):
				otherInputs = screenshot.split(" ")
				outFolder = otherInputs.pop(0).replace("/", " ")
				print("Processing {}/{} ({} of {})".format(outFolder, "/".join(otherInputs), len(latest) * index + jindex + 1, len(latest) * len(savenames)))
				#print("Cropping %s images" % screenshot)
				crop(outFolder, otherInputs[0], otherInputs[1], otherInputs[2], basepath)
				waitlocalfilename = os.path.join(basepath, outFolder, "Images", otherInputs[0], otherInputs[1], otherInputs[2], "done.txt")
				if not os.path.exists(waitlocalfilename):
					#print("waiting for done.txt")
					while not os.path.exists(waitlocalfilename):
						time.sleep(0.4)



				def refZoom():
					#print("Crossreferencing %s images" % screenshot)
					ref(outFolder, otherInputs[0], otherInputs[1], otherInputs[2], basepath)
					#print("downsampling %s images" % screenshot)
					zoom(outFolder, otherInputs[0], otherInputs[1], otherInputs[2], basepath)

				if screenshot != latest[-1]:
					refZoom()
				else:
					if not isKilled[0]:
						isKilled[0] = True
						printErase("killing factorio")
						if p.poll() is None:
							p.kill()
						else:
							os.system("taskkill /im factorio.exe")

					if savename == savenames[-1]:
						refZoom()
					else:
						workthread = threading.Thread(target=refZoom)
						workthread.daemon = True
						workthread.start()


		os.close(logOut)


			

		if os.path.isfile(os.path.join(workfolder, "mapInfo.out.json")):
			print("generating mapInfo.json")
			with open(os.path.join(workfolder, "mapInfo.json"), 'r+') as outf, open(os.path.join(workfolder, "mapInfo.out.json"), "r") as inf:
				data = json.load(outf)
				for mapIndex, mapStuff in json.load(inf)["maps"].items():
					for surfaceName, surfaceStuff in mapStuff["surfaces"].items():
						data["maps"][int(mapIndex)]["surfaces"][surfaceName]["chunks"] = surfaceStuff["chunks"]
				outf.seek(0)
				json.dump(data, outf)
				outf.truncate()
			os.remove(os.path.join(workfolder, "mapInfo.out.json"))


		print("generating mapInfo.js")
		with open(os.path.join(workfolder, "mapInfo.js"), 'w') as outf, open(os.path.join(workfolder, "mapInfo.json"), "r") as inf:
			outf.write("window.mapInfo = JSON.parse('")
			outf.write(inf.read())
			outf.write("');")
			
			
		print("creating index.html")
		copy("index.html.template", os.path.join(workfolder, "index.html"))



	except KeyboardInterrupt:
		print("killing factorio")
		if p.poll() is None:
			p.kill()
		else:
			os.system("taskkill /im factorio.exe")
		raise

	finally:
		print("disabling FactorioMaps mod")
		changeModlist(False)



		print("cleaning up")
		open("autorun.lua", 'w').close()








if __name__ == '__main__':
	auto(*sys.argv[1:])