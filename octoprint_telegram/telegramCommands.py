from __future__ import absolute_import
import logging, sarge, hashlib, datetime
import octoprint.filemanager
from flask.ext.babel import gettext
from .telegramNotifications import telegramMsgDict

################################################################################################################
# This class handles received commands/messages (commands in the following). commandDict{} holds the commands and their behavior.
# Each command has its own handler. If you want to add/del commands, read the following:
# SEE DOCUMENTATION IN WIKI: https://github.com/fabianonline/OctoPrint-Telegram/wiki/Add%20commands%20and%20notifications
################################################################################################################

class TCMD():
	def __init__(self, main):
		self.main = main
		self.gEmo = self.main.gEmo
		self._logger = main._logger.getChild("TCMD")
		self.SettingsTemp = []
		self.conSettingsTemp = []
		#self.dirHashDict = {}
		self.commandDict = {
			"Yes": 			{'cmd': self.cmdYes, 'bind_none': True},
			"No":  			{'cmd': self.cmdNo, 'bind_none': True},
			'/test':  		{'cmd': self.cmdTest, 'bind_none': True},
			'/status':  	{'cmd': self.cmdStatus},
			'/settings':  	{'cmd': self.cmdSettings, 'param': True},
			'/abort':  		{'cmd': self.cmdAbort, 'param': True},
			'/togglepause':	{'cmd': self.cmdTogglePause},
			'/shutup':  	{'cmd': self.cmdShutup},
			'/dontshutup':  {'cmd': self.cmdNShutup},
			'/print':  		{'cmd': self.cmdPrint, 'param': True},
			'/files':  		{'cmd': self.cmdFiles, 'param': True},
			'/upload':  	{'cmd': self.cmdUpload},
			'/sys': 		{'cmd': self.cmdSys, 'param': True},
			'/ctrl': 		{'cmd': self.cmdCtrl, 'param': True},
			'/con': 		{'cmd': self.cmdConnection, 'param': True},
			'/user': 		{'cmd': self.cmdUser},
			'/help':  		{'cmd': self.cmdHelp, 'bind_none': True}
		}
############################################################################################
# COMMAND HANDLERS
############################################################################################
	def cmdYes(self,chat_id,from_id,cmd,parameter):
		self.main.send_msg(gettext("Alright."),chatID=chat_id, msg_id = self.main.getUpdateMsgId(chat_id),inline=False)
############################################################################################
	def cmdNo(self,chat_id,from_id,cmd,parameter):
		self.main.send_msg(gettext("Maybe next time."),chatID=chat_id, msg_id = self.main.getUpdateMsgId(chat_id),inline=False)
############################################################################################
	def cmdTest(self,chat_id,from_id,cmd,parameter):
		self.main.send_msg(self.gEmo('question') + gettext(" Is this a test?\n\n") , responses=[[[gettext("Yes"),"Yes"], [gettext("No"),"No"]]],chatID=chat_id)
############################################################################################
	def cmdStatus(self,chat_id,from_id,cmd,parameter):
		if not self.main._printer.is_operational():
			with_image = self.main._settings.get_boolean(["image_not_connected"])
			self.main.send_msg(self.gEmo('warning') + gettext(" Not connected to a printer. Use /con to connect."),chatID=chat_id,inline=False,with_image=with_image)
		elif self.main._printer.is_printing():
			self.main.on_event("StatusPrinting", {},chatID=chat_id)
		else:
			self.main.on_event("StatusNotPrinting", {},chatID=chat_id)
############################################################################################
	def cmdSettings(self,chat_id,from_id,cmd,parameter):
		if parameter and parameter != "back":
			params = parameter.split('_')
			if params[0] == "h":
				if len(params) > 1:
					if params[1].startswith('+'):
						self.SettingsTemp[0] += float(100)/(10**len(params[1]))
					elif params[1].startswith('-'):
						self.SettingsTemp[0] -= float(100)/(10**len(params[1]))
					else:
						self.main._settings.set_float(['notification_height'], self.SettingsTemp[0], force=True)
						self.main._settings.save()
						self.cmdSettings(chat_id,"back")
						return
					if self.SettingsTemp[0] < 0:
						self.SettingsTemp[0] = 0
				msg = self.gEmo('height') + gettext(" Set new height.\nCurrent:  *%(height).2fmm*",height=self.SettingsTemp[0])
				keys = [
						[["+10","/settings_h_+"],["+1","/settings_h_++"],["+.1","/settings_h_+++"],["+.01","/settings_h_++++"]],
						[["-10","/settings_h_-"],["-1","/settings_h_--"],["-.1","/settings_h_---"],["-.01","/settings_h_----"]],
						[["Save","/settings_h_s"],["Back","/settings_back"]]
					]
				self.main.send_msg(msg,chatID=chat_id,responses=keys,msg_id = self.main.getUpdateMsgId(chat_id),markup="Markdown")
			elif params[0] == "t":
				if len(params) > 1:
					if params[1].startswith('+'):
						self.SettingsTemp[1] += 100/(10**len(params[1]))
					elif params[1].startswith('-'):
						self.SettingsTemp[1] -= 100/(10**len(params[1]))
					else:
						self.main._settings.set_int(['notification_time'], self.SettingsTemp[1], force=True)
						self.main._settings.save()
						self.cmdSettings(chat_id,"back")
						return
					if self.SettingsTemp[1] < 0:
						self.SettingsTemp[1] = 0
				msg = self.gEmo('clock') + gettext(" Set new time.\nCurrent: *%(time)dmin*",time=self.SettingsTemp[1])
				keys = [
						[["+10","/settings_t_+"],["+1","/settings_t_++"]],
						[["-10","/settings_t_-"],["-1","/settings_t_--"]],
						[["Save","/settings_t_s"],["Back","/settings_back"]]
					]
				self.main.send_msg(msg,chatID=chat_id,responses=keys,msg_id = self.main.getUpdateMsgId(chat_id),markup="Markdown")
		else:
			self.SettingsTemp = [self.main._settings.get_float(["notification_height"]),self.main._settings.get_float(["notification_time"])]
			msg = self.gEmo('settings') + gettext(" Current notification settings are:\n\n"+self.gEmo('height')+" Height: %(height).2fmm\n\n"+self.gEmo('clock')+" Time: %(time)dmin",
				height=self.main._settings.get_float(["notification_height"]),
				time=self.main._settings.get_int(["notification_time"]))
			msg_id=self.main.getUpdateMsgId(chat_id) if parameter == "back" else ""
			self.main.send_msg(msg, responses=[[[gettext("Set height"),"/settings_h"], [gettext("Set time"),"/settings_t"], [gettext("Cancel"),"No"]]],chatID=chat_id,msg_id=msg_id)
############################################################################################
	def cmdAbort(self,chat_id,from_id,cmd,parameter):
		if parameter and parameter == "stop":
			self.main._printer.cancel_print()
			self.main.send_msg(self.gEmo('info') + gettext(" Aborting the print."),chatID=chat_id, msg_id = self.main.getUpdateMsgId(chat_id))
		else:
			if self.main._printer.is_printing():
				self.main.send_msg(self.gEmo('question') + gettext(" Really abort the currently running print?"), responses=[[[gettext("Stop print"),"/abort_stop"], [gettext("Cancel"),"No"]]],chatID=chat_id)
			else:
				self.main.send_msg(self.gEmo('info') + gettext(" Currently I'm not printing, so there is nothing to stop."),chatID=chat_id,inline=False)		
############################################################################################
	def cmdTogglePause(self,chat_id,from_id,cmd,parameter):
		msg = ""
		if self.main._printer.is_printing():
			msg = " Pausing the print."
			self.main._printer.toggle_pause_print()
		elif self.main._printer.is_paused():
			msg = " Resuming the print."
			self.main._printer.toggle_pause_print()	
		else:
			msg = "  Currently I'm not printing, so there is nothing to pause/resume."		
		self.main.send_msg(self.gEmo('info') + msg, chatID=chat_id,inline=False)
############################################################################################							
	def cmdShutup(self,chat_id,from_id,cmd,parameter):
		if chat_id not in self.main.shut_up:
			self.main.shut_up[chat_id] = True
		self.main.send_msg(self.gEmo('noNotify') + gettext(" Okay, shutting up until the next print is finished." + self.gEmo('shutup')+" Use /dontshutup to let me talk again before that. "),chatID=chat_id,inline=False)
############################################################################################
	def cmdNShutup(self,chat_id,from_id,cmd,parameter):
		if chat_id in self.main.shut_up:
			del self.main.shut_up[chat_id]
		self.main.send_msg(self.gEmo('notify') + gettext(" Yay, I can talk again."),chatID=chat_id,inline=False)
############################################################################################
	def cmdPrint(self,chat_id,from_id,cmd,parameter):
		if parameter and len(parameter.split('|')) == 1:
			if parameter =="s": # start print
				data = self.main._printer.get_current_data()
				if data['job']['file']['name'] is None:
					self.main.send_msg(self.gEmo('warning') + gettext(" Uh oh... No file is selected for printing. Did you select one using /list?"),chatID=chat_id, msg_id = self.main.getUpdateMsgId(chat_id))
				elif not self.main._printer.is_operational():
					self.main.send_msg(self.gEmo('warning') + gettext(" Can't start printing: I'm not connected to a printer."),chatID=chat_id, msg_id = self.main.getUpdateMsgId(chat_id))
				elif self.main._printer.is_printing():
					self.main.send_msg(self.gEmo('warning') + " A print job is already running. You can't print two thing at the same time. Maybe you want to use /abort?",chatID=chat_id, msg_id = self.main.getUpdateMsgId(chat_id))
				else:
					self.main._printer.start_print()
					self.main.send_msg(self.gEmo('rocket') + gettext(" Started the print job."),chatID=chat_id, msg_id = self.main.getUpdateMsgId(chat_id))
			elif parameter == "x": # do not print
				self.main._printer.unselect_file()
				self.main.send_msg(gettext("Maybe next time."),chatID=chat_id, msg_id = self.main.getUpdateMsgId(chat_id))
			else:	# prepare print
				self._logger.debug("Looking for hash: %s", parameter)
				destination, file , f = self.find_file_by_hash(parameter)
				if file is None:
					msg = self.gEmo('warning') + " I'm sorry, but I couldn't find the file you wanted me to print. Perhaps you want to have a look at /list again?"
					self.main.send_msg(msg,chatID=chat_id,noMarkup=True, msg_id = self.main.getUpdateMsgId(chat_id))
					return
				if destination==octoprint.filemanager.FileDestinations.SDCARD:
					self.main._printer.select_file(file, True, printAfterSelect=False)
				else:
					file = self.main._file_manager.path_on_disk(octoprint.filemanager.FileDestinations.LOCAL, file)
					self._logger.debug("Using full path: %s", file)
					self.main._printer.select_file(file, False, printAfterSelect=False)
				data = self.main._printer.get_current_data()
				if data['job']['file']['name'] is not None:
					msg = self.gEmo('info') + gettext(" Okay. The file %(file)s is loaded.\n\n"+self.gEmo('question')+" Do you want me to start printing it now?", file=data['job']['file']['name'])
					self.main.send_msg(msg,noMarkup=True, msg_id = self.main.getUpdateMsgId(chat_id), responses=[[[gettext("Print"),"/print_s"], [gettext("Cancel"),"/print_x"]]],chatID=chat_id)
				elif not self.main._printer.is_operational():
					self.main.send_msg(self.gEmo('warning') + gettext(" Can't start printing: I'm not connected to a printer."),chatID=chat_id, msg_id = self.main.getUpdateMsgId(chat_id))
				else:
					self.main.send_msg(self.gEmo('warning') + gettext(" Uh oh... Problems on loading the file for print."),chatID=chat_id, msg_id = self.main.getUpdateMsgId(chat_id))
		else:
			self.cmdFiles(chat_id,from_id,cmd,parameter)
############################################################################################
	def cmdFiles(self,chat_id,from_id,cmd,parameter):
		if parameter:
			par = parameter.split('|')
			loc = par[0]
			hash = par[2] if len(par) > 2 else ""
			opt = par[3] if len(par) > 3 else ""
			page = int(par[1])			
			if len(par) < 3:
				self.fileList(loc,page,cmd,chat_id)
			elif len(par) < 4:
				self.fileDetails(loc,page,cmd,hash,chat_id,from_id)	
			else:
				self.fileOption(loc,page,cmd,hash,opt,chat_id,from_id)
		else:
			storages = self.main._file_manager.list_files(recursive=False)
			#self.generate_dir_hash_dict()
			if len(storages.keys()) < 2:
				self.main.send_msg("Loading files...",chatID=chat_id)
				self.cmdFiles(chat_id,from_id,cmd,str(storages.keys()[0])+"|0")
			else:
				keys=[]
				keys.extend([([k,(cmd+"_"+k+"|0")] for k in storages)])
				keys.append([["Cancel","No"]])
				msg_id=self.main.getUpdateMsgId(chat_id) if parameter == "back" else ""
				self.main.send_msg(self.gEmo('save') + " *Select Storage*",chatID=chat_id,markup="Markdown",responses=keys,msg_id=msg_id)
############################################################################################
	def cmdUpload(self,chat_id,from_id,cmd,parameter):
		self.main.send_msg(self.gEmo('info') + " To upload a gcode file, just send it to me.",chatID=chat_id)
############################################################################################
	def cmdSys(self,chat_id,from_id,cmd,parameter):
		if parameter and parameter != "back":
			params = parameter.split('_')
			if params[0] == "do":
				parameter = params[1]
			else:
				parameter = params[0]
			actions = self.main._settings.global_get(['system','actions'])
			command = next((d for d in actions if 'action' in d and self.hashMe(d['action']) == parameter) , False)
			if command :
				if 'confirm' in command and params[0] != "do":
					self.main.send_msg(self.gEmo('question') + command['confirm']+"\nExecute system command?",responses=[[[gettext("Execute"),"/sys_do_"+parameter], [gettext("Back"),"/sys_back"]]],chatID=chat_id, msg_id = self.main.getUpdateMsgId(chat_id))
					return	
				else:
					async = command["async"] if "async" in command else False
					self._logger.info("Performing command: %s" % command["command"])
					try:
						# we run this with shell=True since we have to trust whatever
						# our admin configured as command and since we want to allow
						# shell-alike handling here...
						p = sarge.run(command["command"], stderr=sarge.Capture(), shell=True, async=async)
						if not async:
							if p.returncode != 0:
								returncode = p.returncode
								stderr_text = p.stderr.text
								self._logger.warn("Command failed with return code %i: %s" % (returncode, stderr_text))
								self.main.send_msg(self.gEmo('warning') + " Command failed with return code %i: %s" % (returncode, stderr_text),chatID=chat_id, msg_id = self.main.getUpdateMsgId(chat_id))
								return
						self.main.send_msg(self.gEmo('check') + " System Command " + command["name"] + " executed." ,chatID=chat_id, msg_id = self.main.getUpdateMsgId(chat_id))
					except Exception, e:
						self._logger.warn("Command failed: %s" % e)
						self.main.send_msg(self.gEmo('warning') + " Command failed with exception: %s!" % e,chatID = chat_id, msg_id = self.main.getUpdateMsgId(chat_id))
			else:
				self.main.send_msg(self.gEmo('warning') + " Sorry, i don't know this System Command.",chatID=chat_id, msg_id = self.main.getUpdateMsgId(chat_id))
				return
		else:
			message = self.gEmo('info') + " The following System Commands are known."
			empty = True
			keys = []
			tmpKeys = []
			i = 1
			for action in self.main._settings.global_get(['system','actions']):
				empty = False
				if action['action'] != "divider":
					tmpKeys.append([str(action['name']),"/sys_"+self.hashMe(action['action'])])
					if i%2 == 0:
						keys.append(tmpKeys)
						tmpKeys = []
					i += 1
			if len(tmpKeys) > 0:
				keys.append(tmpKeys)
			keys.append([[gettext("Cancel"),"No"]])
			if empty: message += "\n\n"+self.gEmo('warning')+" No System Commands found..."
			msg_id=self.main.getUpdateMsgId(chat_id) if parameter == "back" else ""
			self.main.send_msg(message,chatID=chat_id,responses=keys,msg_id=msg_id)
############################################################################################
	def cmdCtrl(self,chat_id,from_id,cmd,parameter):
		if not self.main._printer.is_operational():
			self.main.send_msg(self.gEmo('warning')+" Printer not connected. You can't send any command.",chatID=chat_id)
			return
		if parameter and parameter != "back":
			params = parameter.split('_')
			if params[0] == "do":
				parameter = params[1]
			else:
				parameter = params[0]
			actions = self.get_controls_recursively()
			command = next((d for d in actions if d['hash'] == parameter), False)
			if command:
				if 'confirm' in command and params[0] != "do":
					self.main.send_msg(self.gEmo('question') + command['confirm']+"\nExecute control command?",responses=[[[gettext("Execute"),"/ctrl_do_"+parameter], [gettext("Back"),"/ctrl_back"]]],chatID=chat_id, msg_id = self.main.getUpdateMsgId(chat_id))
					return
				else:
					if type(command['command']) is type([]):
						for key in command['command']:
							self.main._printer.commands(key)
					else:
						self.main._printer.commands(command['command'])
					self.main.send_msg(self.gEmo('check') + " Control Command " + command['name'] + " executed." ,chatID=chat_id, msg_id = self.main.getUpdateMsgId(chat_id))
			else:
				self.main.send_msg(self.gEmo('warning') + " Control Command not found." ,chatID=chat_id, msg_id = self.main.getUpdateMsgId(chat_id))
		else:
			message = self.gEmo('info') + " The following Printer Controls are known."
			empty = True
			keys = []
			tmpKeys = []
			i = 1
			for action in self.get_controls_recursively():
				empty=False
				tmpKeys.append([str(action['name']),"/ctrl_"+str(action['hash'])])
				if i%2 == 0:
					keys.append(tmpKeys)
					tmpKeys = []
				i += 1
			if len(tmpKeys) > 0:
				keys.append(tmpKeys)
			keys.append([[gettext("Cancel"),"No"]])
			if empty: message += "\n\n"+self.gEmo('warning')+" No Printer Control Command found..."
			msg_id=self.main.getUpdateMsgId(chat_id) if parameter == "back" else ""
			self.main.send_msg(message,chatID=chat_id,responses=keys,msg_id = msg_id)
############################################################################################
	def cmdUser(self,chat_id,from_id,cmd,parameter):
		msg = self.gEmo('info') + " *Your user settings:*\n\n"
		msg += "*ID:* " + str(chat_id) + "\n"
		msg += "*Name:* " + str(self.main.chats[chat_id]['title']) + "\n"
		if self.main.chats[chat_id]['private']:
			msg += "*Type:* Priavte\n\n"
		else:
			msg += "*Type:* Group\n"
			if self.main.chats[chat_id]['accept_commands']:
				msg += "*Accept-Commands:* All users\n\n"
			elif self.main.chats[chat_id]['allow_users']:
				msg += "*Accept-Commands:* Allowed users\n\n"
			else:
				msg += "*Accept-comands:* None\n\n"

		msg += "*Allowed commands:*\n"
		if self.main.chats[chat_id]['accept_commands']:
			myTmp = 0
			for key in self.main.chats[chat_id]['commands']:
				if self.main.chats[chat_id]['commands'][key] and 'bind_none' not in self.commandDict[key]:
					msg += key + ", "
					myTmp += 1
			if myTmp < 1:
				msg += "You are NOT allowed to send any command."
			msg += "\n\n"
		elif self.main.chats[chat_id]['allow_users']:
			msg += "Allowed users ONLY. See specific user settings for details.\n\n"
		else:
			msg += "You are NOT allowed to send any command.\n\n"

		msg += "*Get notification on:*\n"
		if self.main.chats[chat_id]['send_notifications']:
			myTmp = 0
			for key in self.main.chats[chat_id]['notifications']:
				if self.main.chats[chat_id]['notifications'][key]:
					msg += key + ", "
					myTmp += 1
			if myTmp < 1:
				msg += "You will receive NO notifications."
			msg += "\n\n"
		else:
			msg += "You will receive NO notifications.\n\n"

		self.main.send_msg(msg, chatID=chat_id, markup="Markdown")
############################################################################################
	def cmdConnection(self,chat_id,from_id,cmd,parameter):
		if parameter and parameter != "back":
			params = parameter.split('|')
			if params[0] == "s":
				self.ConSettings(chat_id,params[1:])
			elif params[0] == "c":
				self.ConConnect(chat_id,params[1:])
			elif params[0] == "d":
				self.ConDisconnect(chat_id)
		else:
			con = self.main._printer.get_current_connection()
			con2 = octoprint.printer.get_connection_options()
			msg = self.gEmo('info') + gettext(" Connection informations\n\n*Status*: %(status)s\n\n*Port*: %(port)s\n*Baud*: %(baud)s\n*Profile*: %(profile)s\n*AutoConnect*: %(auto)s\n\n",status = str(con[0]),port = str(con[1]),baud = str("AUTO" if str(con[2]) == '0'  else con[2]),profile = str((con[3] if con[3]is None else con[3]['name'])),auto=str(con2['autoconnect']))
			msg_id=self.main.getUpdateMsgId(chat_id) if parameter == "back" else ""
			if self.main._printer.is_operational():
				if self.main._printer.is_printing() or self.main._printer.is_paused():
					self.main.send_msg(msg + self.gEmo('warning') + " You can't change connection state while printing.",responses=[[[gettext("Settings"),"/con_s"], [gettext("Cancel"),"No"]]],chatID=chat_id,msg_id=msg_id,markup="Markdown")
				else:
					self.main.send_msg(msg,responses=[[[gettext("Disconnect"),"/con_d"],[gettext("Defaults"),"/con_s"], [gettext("Cancel"),"No"]]],chatID=chat_id,msg_id=msg_id,markup="Markdown")
			else:
				self.main.send_msg(msg,responses=[[[gettext("Connect"),"/con_c"],[gettext("Defaults"),"/con_s"],[gettext("Cancel"),"No"]]],chatID=chat_id,msg_id=msg_id,markup="Markdown")
############################################################################################
	def cmdHelp(self,chat_id,from_id,cmd,parameter):
		self.main.send_msg(self.gEmo('info') + gettext(" The following commands are known:\n\n"
		                           "/abort - Aborts the currently running print. A confirmation is required.\n"
		                           "/shutup - Disables automatic notifications till the next print ends.\n"
		                           "/imsorrydontshutup - The opposite of /shutup - Makes the bot talk again.\n"
		                           "/status - Sends the current status including a current photo.\n"
		                           "/settings - Displays the current notification settings and allows you to change them.\n"
		                           "/list - Lists all the files available for printing and lets you start printing them.\n"
		                           "/print - Lets you start a print. A confirmation is required.\n"
		                           "/togglepause - Pause/Resume current Print.\n"
		                           "/con - Connect/disconnect printer.\n"
		                           "/upload - You can just send me a gcode file to save it to my library.\n"
		                           "/sys - Execute Octoprint System Comamnds.\n"
		                           "/ctrl - Use self defined controls from Octoprint.\n"
		                           "/user - get user info."),chatID=chat_id)
############################################################################################
# FILE HELPERS
############################################################################################
	def fileList(self,loc,page,cmd,chat_id,wait = 0):
		storage = self.main._file_manager.list_files(recursive=False)
		files = self.list_files(storage[loc],loc,page,cmd)
		pageDown = page-1 if page > 0 else 0
		pageUp = page+1 if len(files)-(page+1)*10 > 0 else page
		keys = []
		tmpKeys = []
		i = 1
		for k in files[page*10:page*10+10]:
			tmpKeys.append(k)
			if not i%2:
				keys.append(tmpKeys)
				tmpKeys = []
			i += 1
		if len(tmpKeys):
			keys.append(tmpKeys)
		tmpKeys = []
		backBut = [["Close","No"]] if len(storage.keys()) < 2 else [["Back",cmd+"_back"],["Close","No"]]
		if pageDown != pageUp:
			if pageDown != page:
				tmpKeys.append([self.main.emojis['black left-pointing triangle'],cmd+"_"+loc+"|"+ str(pageDown)])
			tmpKeys.extend(backBut)
			if pageUp != page:
				tmpKeys.append([self.main.emojis['black right-pointing triangle'],cmd+"_"+loc+"|"+str(pageUp)])
		else:
			tmpKeys.extend(backBut)
		keys.append(tmpKeys)
		pageStr = str(page+1)+"/"+str(len(files)/10 + (1 if len(files)%10 > 0 else 0))
		self.main.send_msg(self.gEmo('save') + " *Files on "+loc+" storage*    \["+pageStr+"]",chatID=chat_id,markup="Markdown",responses=keys,msg_id = self.main.getUpdateMsgId(chat_id),delay=wait)
############################################################################################
	def fileDetails(self,loc,page,cmd,hash,chat_id,from_id,wait=0):
		dest, path, file = self.find_file_by_hash(hash)
		meta = self.main._file_manager.get_metadata(dest,path)
		msg = self.gEmo("info") + " <b>File Informations</b>\n\n"
		msg += "<b>Name:</b> " + path
		msg += "\n<b>Size:</b> " + self.formatSize(file['size'])
		if 'analysis' in meta:
			if 'filament' in meta['analysis']:
				msg += "\n<b>Filament:</b> "
				filament = meta['analysis']['filament']
				if len(filament) == 1:
					msg += self.formatFilament(filament['tool0'])
				else:
					for key in sorted(filament):
						msg +=  "\n      "+str(key)+": "+ self.formatFilament(filament[key])
			if 'estimatedPrintTime' in meta['analysis']:
				msg += "\n<b>Print Time:</b> "+ self.formatFuzzyPrintTime(meta['analysis']['estimatedPrintTime'])
		keyPrint = ["Print","/print_"+hash]
		keyDetails = ["Details",cmd+"_"+loc+"|"+str(page)+"|"+hash+"|info"]
		keyDownload = ["Download",cmd+"_"+loc+"|"+str(page)+"|"+hash+"|dl"]
		keyDelete = ["Delete",cmd+"_"+loc+"|"+str(page)+"|"+hash+"|del"]
		keyBack = ["Back",cmd+"_"+loc+"|"+str(page)]
		keysRow = []
		keys = []
		chkID = chat_id 
		if self.main.isCommandAllowed(chat_id, from_id, "/print"):
			keysRow.append(keyPrint)
		keysRow.append(keyDetails)
		keys.append(keysRow)
		keysRow = []
		if self.main.isCommandAllowed(chat_id, from_id, "/files"):
			if loc == octoprint.filemanager.FileDestinations.LOCAL:
				keysRow.append(keyDownload)
			keysRow.append(keyDelete)
		keysRow.append(keyBack)
		keys.append(keysRow)
		self.main.send_msg(msg,chatID=chat_id,markup="HTML",responses=keys,msg_id = self.main.getUpdateMsgId(chat_id),delay=wait)
############################################################################################
	def fileOption(self,loc,page,cmd,hash,opt,chat_id,from_id):
		dest, path, file = self.find_file_by_hash(hash)
		meta = self.main._file_manager.get_metadata(dest,path)
		if opt.startswith("info"):
			msg = self.gEmo("info") + " <b>Detailed File Informations</b>\n\n"
			msg += "<b>Name:</b> " + path
			msg += "\n<b>Size:</b> " + self.formatSize(file['size'])
			msg += "\n<b>Uploaded:</b> " + datetime.datetime.fromtimestamp(file['date']).strftime('%Y-%m-%d %H:%M:%S')
			if 'analysis' in meta:
				if 'filament' in meta['analysis']:
					msg += "\n<b>Filament:</b> "
					filament = meta['analysis']['filament']
					if len(filament) == 1:
						msg += self.formatFilament(filament['tool0'])
					else:
						for key in sorted(filament):
							msg +=  "\n      "+str(key)+": "+ self.formatFilament(filament[key])
				if 'estimatedPrintTime' in meta['analysis']:
					msg += "\n<b>Estimated Print Time:</b> "+ self.formatDuration(meta['analysis']['estimatedPrintTime'])
			if 'statistics' in meta:
				if 'averagePrintTime' in meta['statistics']:
					msg += "\n<b>Average Print Time:</b>"
					for avg in meta['statistics']['averagePrintTime']:
						prof = self.main._printer_profile_manager.get(avg)
						msg += "\n      "+ prof['name']+": "+ self.formatDuration(meta['statistics']['averagePrintTime'][avg])
				if 'lastPrintTime'in meta['statistics']:
					msg += "\n<b>Last Print Time:</b>"
					for avg in meta['statistics']['lastPrintTime']:
						prof = self.main._printer_profile_manager.get(avg)
						msg += "\n      "+ prof['name']+": "+ self.formatDuration(meta['statistics']['lastPrintTime'][avg])
			self._logger.debug("CHK 1")
			if 'history' in meta:
				self._logger.debug("CHK 2")
				if len(meta['history'])>0:
					self._logger.debug("CHK 2")
					msg += "\n\n<b>Print History:</b> "
					for hist in meta['history']:
						if 'timestamp' in hist:
							msg += "\n      Timestamp: "+datetime.datetime.fromtimestamp(hist['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
						if 'printTime' in hist:
							msg += "\n      Print Time: "+self.formatDuration(hist['printTime'])
						if 'printerProfile' in hist:
							prof = self.main._printer_profile_manager.get(hist['printerProfile'])
							msg += "\n      Printer Profile: "+prof['name']
						if 'success' in hist:
							if hist['success']:
								msg += "\n      Successful printed"
							else:
								msg += "\n      Print failed"
						msg += "\n"
			self.main.send_msg(msg,chatID=chat_id,responses=[[["Back",cmd+"_" + loc + "|"+str(page)+"|"+ hash]]],msg_id=self.main.getUpdateMsgId(chat_id),markup="HTML")
		elif opt.startswith("dl"):
			mb = float(file['size']) /1024/1024
			if mb > 50:
				self.main.send_msg(self.gEmo('warning')+path+" ist to big to download (>50MB)!",chatID=chat_id,msg_id=self.main.getUpdateMsgId(chat_id))
				self.fileDetails(loc,page,cmd,hash,chat_id,from_id,wait=2)
			else:
				self.main.send_file(chat_id,self.main._file_manager.path_on_disk(dest,path))
		elif opt.startswith("del"):
			msg_id = self.main.getUpdateMsgId(chat_id)
			if opt == "del_do":
				try:
					self.main._file_manager.remove_file(dest, path)
					self.main.send_msg(self.gEmo('info')+" File "+path+" deleted",chatID=chat_id,msg_id=msg_id)
					self.fileList(loc,page,cmd,chat_id,wait = 2)
				except Exception as ex:
					self.main.send_msg(self.gEmo('warning')+"FAILED: Delete file "+path,chatID=chat_id,msg_id=msg_id)
					self.fileList(loc,page,cmd,chat_id,wait = 2)
			else:
				keys = [[["Yes",cmd+"_" + loc + "|"+str(page)+"|"+ hash+"|del_do"],["No",cmd+"_" + loc + "|"+str(page)+"|"+ hash]]]
				self.main.send_msg(self.gEmo('warning')+" Delete "+path+" ?",chatID=chat_id,responses=keys,msg_id=msg_id)
			
############################################################################################
	def list_files(self, tree, source,page,cmd,base=""):
		array = []
		#arrayD = []
		for key in tree:
			#if tree[key]['type']=="folder":
				#arrayD.append([self.main.emojis['file folder']+" "+key,"/files_"+source+"|"+str(page)+"|"+self.hashMe(base+key+"/")+"|d"])
			if tree[key]['type']=="machinecode":
				array.append([self.main.emojis['page facing up']+" "+('.').join(key.split('.')[:-1]),cmd+"_" + source + "|"+str(page)+"|"+ tree[key]['hash']])
		#arrayD.extend(array)
		return sorted(array)
############################################################################################
	#def generate_dir_hash_dict(self):
		#self.dirHashDict = {}
		#tree = self.main._file_manager.list_files(recursive=True)
		#for key in tree:
			#self.dirHashDict.update({key:self.generate_dir_hash_dict_recursively(tree[key],key)})
############################################################################################
	#def generate_dir_hash_dict_recursively(self,tree,loc,base=""):
		#myDict = {}
		#self._logger.debug("SATRT RECUR")
		#for key in tree:
			#self._logger.debug("TEST: "+key)
			#if tree[key]['type']=="folder":
				#self._logger.debug("FOLER: "+key)
				#myDict.update({self.hashMe(loc+base+key+"/"):base+key+"/"})
				#self.generate_dir_hash_dict_recursively(tree[key]['children'],base+key+"/")
		#return myDict
############################################################################################	
	def find_file_by_hash(self, hash):
		tree = self.main._file_manager.list_files(recursive=True)
		for key in tree:
			result,file = self.find_file_by_hash_recursively(tree[key], hash)
			if result is not None:
				return key, result, file
		return None, None, None
############################################################################################	
	def find_file_by_hash_recursively(self, tree, hash, base=""):
		for key in tree:
			if tree[key]['type']=="folder":
				result, file = self.find_file_by_hash_recursively(tree[key]['children'], hash, base=base+key+"/")
				if result is not None:
					return result, file
				continue
			if tree[key]['hash'].startswith(hash):
				return base+key, tree[key]
		return None, None
############################################################################################
# CONTROL HELPERS
############################################################################################
	def get_controls_recursively(self, tree = None, base = "", first = ""):
		array = []
		if tree == None:
			tree = self.main._settings.global_get(['controls'])
		for key in tree:
			if type(key) is type({}):
				if base == "":
					first = " "+key['name']+" "
				if 'children' in key:
					array.extend(self.get_controls_recursively(key['children'], base + " " + key['name'],first))
				elif ('commands' in key or 'command' in key) and not 'regex' in key and not 'input' in key and not 'script' in key:
					# rename 'commands' to 'command' so its easier to handle later on
					newKey = {}
					command = key['command'] if 'command' in key else key['commands']
					newKey['name'] = base.replace(first,"") + " " + key['name']
					newKey['hash'] = self.hashMe(base + " " + key['name'] + str(command), 6)
					newKey['command'] = command
					if 'confirm' in key:
						newKey['confirm'] = key['confirm']
					array.append(newKey)
		return array
############################################################################################
	def hashMe(self, text, length = 32):
		return hashlib.md5(text).hexdigest()[0:length]
############################################################################################
# CONNECTION HELPERS
############################################################################################
	def ConSettings(self,chat_id,parameter):
		if parameter:
			if parameter[0] == "p":
				self.ConPort(chat_id,parameter[1:],'s')
			elif parameter[0] == "b":
				self.ConBaud(chat_id,parameter[1:],'s')
			elif parameter[0] == "pr":
				self.ConProfile(chat_id,parameter[1:],'s')
			elif parameter[0] == "a":
				self.ConAuto(chat_id,parameter[1:],'s')
		else:
			con = octoprint.printer.get_connection_options()
			profile = self.main._printer_profile_manager.get_default()
			msg = self.gEmo('info') + " Default connection settings \n\n"
			msg += "*Port:* "+ str(con['portPreference'])
			msg += "\n*Baud:* "+ (str(con['baudratePreference']) if con['baudratePreference'] else "AUTO")
			msg += "\n*Profil:* "+ str(profile['name'])
			msg += "\n*AutoConnect:* "+ str(con['autoconnect'])
			self.main.send_msg(msg,responses=[[[gettext("Port"),"/con_s|p"],[gettext("Baud"),"/con_s|b"],[gettext("Profile"),"/con_s|pr"], [gettext("Auto"),"/con_s|a"]], [[gettext("Back"),"/con_back"]]],chatID=chat_id,markup="Markdown",msg_id=self.main.getUpdateMsgId(chat_id))
############################################################################################
	def ConPort(self,chat_id,parameter,parent):
		if parameter:
			self._logger.debug("SETTING: "+str(parameter[0]))
			self.main._settings.global_set(["serial","port"],parameter[0],force=True)
			self.main._settings.save()
			self.ConSettings(chat_id,[])
		else:
			con = octoprint.printer.get_connection_options()
			keys = []
			tmpKeys = [['AUTO','/con_'+parent+'|p|AUTO']]
			i = 2
			for k in con['ports']:
				tmpKeys.append([str(k),"/con_"+parent+"|p|"+str(k)])
				if i%3 == 0:
					keys.append(tmpKeys)
					tmpKeys = []
				i += 1
			if len(tmpKeys) > 0 and len(tmpKeys) < 3:
				keys.append(tmpKeys)
			keys.append([[gettext("Back"),"/con_"+parent]])
			self.main.send_msg(self.gEmo('question') + " Select default port.\nCurrent setting: "+con['portPreference'],responses=keys,chatID=chat_id,msg_id=self.main.getUpdateMsgId(chat_id))
############################################################################################
	def ConBaud(self,chat_id,parameter,parent):
		if parameter:
			self._logger.debug("SETTING: "+str(parameter[0]))
			self.main._settings.global_set_int(["serial","baudrate"],parameter[0],force=True)
			self.main._settings.save()
			self.ConSettings(chat_id,[])
		else:
			con = octoprint.printer.get_connection_options()
			keys = []
			tmpKeys = [['AUTO','/con_'+parent+'|b|0']]
			i = 2
			for k in con['baudrates']:
				tmpKeys.append([str(k),"/con_"+parent+"|b|"+str(k)])
				if i%3 == 0:
					keys.append(tmpKeys)
					tmpKeys = []
				i += 1
			if len(tmpKeys) > 0 and len(tmpKeys) < 3:
				keys.append(tmpKeys)
			keys.append([[gettext("Back"),"/con_"+parent]])
			self.main.send_msg(self.gEmo('question') + " Select default baudrate.\nCurrent setting: "+(str(con['baudratePreference']) if con['baudratePreference'] else "AUTO"),responses=keys,chatID=chat_id,msg_id=self.main.getUpdateMsgId(chat_id))
############################################################################################
	def ConProfile(self,chat_id,parameter,parent):
		if parameter:
			self._logger.debug("SETTING: "+str(parameter[0]))
			self.main._settings.global_set(["printerProfiles","default"],parameter[0],force=True)
			self.main._settings.save()
			self.ConSettings(chat_id,[])
		else:
			con = self.main._printer_profile_manager.get_all()
			con2 = self.main._printer_profile_manager.get_default()
			keys = []
			tmpKeys = []
			i = 1
			for k in con:
				tmpKeys.append([str(con[k]['name']),"/con_"+parent+"|pr|"+str(con[k]['id'])])
				if i%3 == 0:
					keys.append(tmpKeys)
					tmpKeys = []
				i += 1
			if len(tmpKeys) > 0 and len(tmpKeys) < 3:
				keys.append(tmpKeys)
			keys.append([[gettext("Back"),"/con_"+parent]])
			self.main.send_msg(self.gEmo('question') + " Select default profile.\nCurrent setting: "+con2['name'],responses=keys,chatID=chat_id,msg_id=self.main.getUpdateMsgId(chat_id))
############################################################################################
	def ConAuto(self,chat_id,parameter):
		if parameter:
			self._logger.debug("SETTING: "+str(parameter[0]))
			self.main._settings.global_set_boolean(["serial","autoconnect"],parameter[0],force=True)
			self.main._settings.save()
			self.ConSettings(chat_id,[])
		else:
			con = octoprint.printer.get_connection_options()
			keys=[[["ON","/con_s|a|true"],["OFF","/con_s|a|false"]],[[gettext("Back"),"/con_s"]]]
			self.main.send_msg(self.gEmo('question') + " AutoConnect on startup.\nCurrent setting: "+str(con['autoconnect']),responses=keys,chatID=chat_id,msg_id=self.main.getUpdateMsgId(chat_id))
############################################################################################	
	def ConConnect(self,chat_id,parameter):
		if parameter:
			if parameter[0] == "a":
					self.conSettingsTemp.extend(["Auto",0,self.main._printer_profile_manager.get_default()['id']])
			elif parameter[0] == "d":
					self.conSettingsTemp.extend([self.main._settings.global_get(["serial","port"]),self.main._settings.global_get(["serial","baudrate"]),self.main._printer_profile_manager.get_default()])
			elif parameter[0] == "p" and len(parameter) < 2:
				self.ConPort(chat_id,[],'c')
				return
			elif parameter[0] == "p":
				self.conSettingsTemp.append(parameter[1])
				self.ConBaud(chat_id,[],'c')
				return
			elif parameter[0] == "b":
				self.conSettingsTemp.append(parameter[1])
				self.ConProfile(chat_id,[],'c')
				return
			elif parameter[0] == "pr":
				self.conSettingsTemp.append(parameter[1])
			self.main.send_msg(self.gEmo('info') + " Connecting...",chatID=chat_id, msg_id = self.main.getUpdateMsgId(chat_id))
			self.main._printer.connect(port=self.conSettingsTemp[0],baudrate=self.conSettingsTemp[1],profile=self.conSettingsTemp[2])
			self.conSettingsTemp = []
			con = self.main._printer.get_current_connection()
			waitStates=["Offline","Detecting baudrate","Connecting"]
			while any(s in con[0] for s in waitStates):
				con = self.main._printer.get_current_connection()
			self._logger.debug("EXIT WITH: "+str(con[0]))

			if con[0] == "Operational":
				self.main.send_msg(self.gEmo('info') + " Connection started.",chatID=chat_id, msg_id = self.main.getUpdateMsgId(chat_id))
			else:
				self.main.send_msg(self.gEmo('warning') + " Failed to start connection.\n\n"+con[0],chatID=chat_id, msg_id = self.main.getUpdateMsgId(chat_id))
		else:
			keys=[[["AUTO","/con_c|a"],["Default","/con_c|d"]],[["Manual","/con_c|p"],["Back","/con_back"]]]
			self.main.send_msg(self.gEmo('question') + " Select connection option.",chatID=chat_id,responses=keys, msg_id = self.main.getUpdateMsgId(chat_id))
############################################################################################
	def ConDisconnect(self,chat_id,parameter):
		self.main._printer.disconnect()
		self.main.send_msg(self.gEmo('info') + " Printer disconnected.",chatID=chat_id, msg_id = self.main.getUpdateMsgId(chat_id))
############################################################################################
# FORMAT HELPERS
############################################################################################
	def formatSize(self,bytes):
		# from octoprint/static/js/app/helpers.js transfered to python
		if not bytes:
			return "-"
		units = ["bytes", "KB", "MB", "GB"]
		for i in xrange(0, len(units)):
			if bytes < 1024:
				return "%3.1f %s" % (bytes, units[i])
			bytes = float(bytes) / 1024
		return "%.1f%s" % (bytes, "TB")
############################################################################################
	def formatFilament(self,filament):
		# from octoprint/static/js/app/helpers.js transfered to python
		if not filament or 'length' not in filament:
			return "-"
		result = "%.02f m" % (float(filament["length"])/1000)
		if "volume" in filament and filament['volume']:
			self._logger.debug("CHK 6")
			result += " / " + "%.02f cm^3" % (float(filament["volume"]))
		return result
############################################################################################
	def formatDuration(self,seconds):
		if seconds is None:
			return "-"
		if seconds < 1:
			return "00:00:00"
		s = int(seconds) % 60
		m = (int(seconds) % 3600) / 60
		h = int(seconds) / 3600
		return "%02d:%02d:%02d" % (h,m,s)

############################################################################################
	def formatFuzzyPrintTime(self,totalSeconds):
    ##
     # from octoprint/static/js/app/helpers.js transfered to python
     #
     # Formats a print time estimate in a very fuzzy way.
     #
     # Accuracy decreases the higher the estimation is:
     #
     #   # less than 30s: "a couple of seconds"
     #   # 30s to a minute: "less than a minute"
     #   # 1 to 30min: rounded to full minutes, above 30s is minute + 1 ("27 minutes", "2 minutes")
     #   # 30min to 40min: "40 minutes"
     #   # 40min to 50min: "50 minutes"
     #   # 50min to 1h: "1 hour"
     #   # 1 to 12h: rounded to half hours, 15min to 45min is ".5", above that hour + 1 ("4 hours", "2.5 hours")
     #   # 12 to 24h: rounded to full hours, above 30min is hour + 1, over 23.5h is "1 day"
     #   # Over a day: rounded to half days, 8h to 16h is ".5", above that days + 1 ("1 day", "4 days", "2.5 days")
     #/

	    if not totalSeconds or totalSeconds < 1:
	    	return "-";
	    replacements = {
	        'days': int(totalSeconds)/86400,
	        'hours': int(totalSeconds)/3600,
	        'minutes': int(totalSeconds)/60,
	        'seconds': int(totalSeconds),
	        'totalSeconds': totalSeconds
	    }
	    text = "-";
	    if replacements['days'] >= 1:
	        # days
	        if replacements["hours"] >= 16:
	            replacements['days'] += 1
	            text = "%(days)d days"
	        elif replacements["hours"] >= 8 and replacements["hours"] < 16:
	            text = "%(days)d.5 days"
	        else:
	            if days == 1:
	                text = "%(days)d day"
	            else:
	                text = "%(days)d days"
	    elif replacements['hours'] >= 1:
	        # only hours
	        if replacements["hours"] < 12:
	            if replacements['minutes'] < 15:
	                # less than .15 => .0
	                if replacements["hours"] == 1:
	                    text = "%(hours)d hour"
	                else:
	                    text = "%(hours)d hours"
	            elif replacements['minutes'] >= 15 and replacements['minutes'] < 45:
	                # between .25 and .75 => .5
	                text = "%(hours)d.5 hours"
	            else:
	                # over .75 => hours + 1
	                replacements["hours"] += 1
	                text = "%(hours)d hours"
	        else:
	            if replacements["hours"] == 23 and replacements['minutes'] > 30:
	                # over 23.5 hours => 1 day
	                text = "1 day"
	            else:
	                if replacements['minutes'] > 30:
	                    # over .5 => hours + 1
	                    replacements["hours"] += 1
	                text = "%(hours)d hours"
	    elif replacements['minutes'] >= 1:
	        # only minutes
	        if replacements['minutes'] < 2:
	            if replacements['seconds'] < 30:
	                text = "a minute"
	            else:
	                text = "2 minutes"
	        elif replacements['minutes'] < 30:
	            if replacements['seconds'] > 30:
	                replacements["minutes"] += 1;
	            text = "%(minutes)d minutes"
	        elif replacements['minutes'] <= 40:
	            text = "40 minutes"
	        elif replacements['minutes'] <= 50:
	            text = "50 minutes"
	        else:
	            text = "1 hour"
	    else:
	        # only seconds
	        if seconds < 30:
	            text = "a couple of seconds"
	        else:
	            text = "less than a minute"
	    return text % replacements
