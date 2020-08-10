
import logging, sarge, hashlib, datetime, time, operator, socket
import octoprint.filemanager
import requests
from flask_babel import gettext
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
		self.tuneTemp = [100,100]
		self.tempTemp = []
		self.conSettingsTemp = []
		self.dirHashDict = {}
		self.tmpFileHash = ""
		self.port = 80
		self.commandDict = {
			"Yes": 			{'cmd': self.cmdYes, 'bind_none': True},
			"No":  			{'cmd': self.cmdNo, 'bind_none': True},
			'/test':  		{'cmd': self.cmdTest, 'bind_none': True},
			'/status':  	{'cmd': self.cmdStatus},
			'/gif':  		{'cmd': self.cmdGif}, #giloser 05/05/19 add gif command
			'/supergif':  	{'cmd': self.cmdSuperGif}, #giloser 05/05/19 add gif command
			'/settings':  	{'cmd': self.cmdSettings, 'param': True},
			'/abort':  		{'cmd': self.cmdAbort, 'param': True},
			'/togglepause':	{'cmd': self.cmdTogglePause},
			'/shutup':  	{'cmd': self.cmdShutup},
			'/dontshutup':  {'cmd': self.cmdNShutup},
			'/print':  		{'cmd': self.cmdPrint, 'param': True},
			'/files':  		{'cmd': self.cmdFiles, 'param': True},
			'/upload':  	{'cmd': self.cmdUpload},
			'/filament':	{'cmd': self.cmdFilament, 'param': True},
			'/sys': 		{'cmd': self.cmdSys, 'param': True},
			'/ctrl': 		{'cmd': self.cmdCtrl, 'param': True},
			'/con': 		{'cmd': self.cmdConnection, 'param': True},
			'/user': 		{'cmd': self.cmdUser},
			'/tune':		{'cmd': self.cmdTune, 'param': True},
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
		self.main.send_msg(self.gEmo('question') + gettext(" Is this a test?\n\n") , responses=[[[self.main.emojis['check']+gettext(" Yes"),"Yes"], [self.main.emojis['cross mark']+gettext(" No"),"No"]]],chatID=chat_id)
############################################################################################
	def cmdStatus(self,chat_id,from_id,cmd,parameter):
		if not self.main._printer.is_operational():
			with_image = self.main._settings.get_boolean(["image_not_connected"])
			with_gif = False #self.main._settings.get_boolean(["gif_not_connected"])
			self.main.send_msg(self.gEmo('warning') + gettext(" Not connected to a printer. Use /con to connect."),chatID=chat_id,inline=False,with_image=with_image)
		elif self.main._printer.is_printing():
			self.main.on_event("StatusPrinting", {},chatID=chat_id)
		else:
			self.main.on_event("StatusNotPrinting", {},chatID=chat_id)
############################################################################################
	def cmdGif(self,chat_id,from_id,cmd,parameter): #GWE 05/05/2019 add command to get gif
		if self.main._settings.get(["send_gif"]):
			if not self.main._printer.is_operational():
				with_image = self.main._settings.get_boolean(["image_not_connected"])
				self.main.send_msg(self.gEmo('warning') + gettext(" Not connected to a printer. Use /con to connect."),chatID=chat_id,inline=False,with_image=with_image)
			else:
			#elif self.main._printer.is_printing():
				sendOneInLoop = False
				try:
					self._logger.info("Will try to create a gif")
					ret = ""
					if self.main._plugin_manager.get_plugin("multicam") and self.main._settings.get(["multicam"]):
						try:
							curr = self.main._settings.global_get(["plugins","multicam","multicam_profiles"])
							for li in curr:
								try:
									url = li.get("URL")
									ret = self.main.create_gif_new(chat_id,5,url)
									if ret != "":
										self.main.send_file(chat_id, ret,"")
										sendOneInLoop = True
								except Exception as ex:
									self._logger.error("Exception loop multicam URL to create gif: "+ str(ex) )
						except Exception as ex:
							self._logger.error("Exception occured on getting multicam options: "+ str(ex) )
					else:
						ret = self.main.create_gif_new(chat_id,5,0)

					if ret == "":
						ret = self.main.create_gif_new(chat_id,5,0)

					if ret != "" and not sendOneInLoop:
						self.main.send_file(chat_id, ret,"")
				except Exception as ex:
					self._logger.error("Exception occured during creating of the gif: "+ str(ex) )
					self.main.send_msg(self.gEmo('dizzy face') + " Problem creating gif, please check log file ",chatID=chat_id)
			#else:
			#	self.main.on_event("StatusNotPrinting", {},chatID=chat_id)
		else:
			self.main.send_msg(self.gEmo('dizzy face') + " Sending GIF is disabled in plugin settings.",chatID=chat_id)

############################################################################################
	def cmdSuperGif(self,chat_id,from_id,cmd,parameter): #GWE 05/05/2019 add command to get gif
		if self.main._settings.get(["send_gif"]):
			if not self.main._printer.is_operational():
				with_image = self.main._settings.get_boolean(["image_not_connected"])
				self.main.send_msg(self.gEmo('warning') + gettext(" Not connected to a printer. Use /con to connect."),chatID=chat_id,inline=False,with_image=with_image)
			elif self.main._printer.is_printing():
				try:
					sendOneInLoop = False
					self._logger.info("Will try to create a super gif")
					if self.main._plugin_manager.get_plugin("multicam") and self.main._settings.get(["multicam"]):
						try:
							curr = self.main._settings.global_get(["plugins","multicam","multicam_profiles"])
							self._logger.error("MUUUUUUUUUUUUUUUUUULTICAM  "+ str(curr))
							for li in curr:
								try:
									self._logger.error("MUUUUUUUUUUUUUUUUUULTICAM  "+ str(li))
									url = li.get("URL")
									self._logger.error("MUUUUUUUUUUUUUUUUUULTICAM  "+ str(url))
									ret = self.main.create_gif_new(chat_id,10,url)
									if ret != "":
										self.main.send_file(chat_id, ret,"")
										sendOneInLoop = True
								except Exception as ex:
									self._logger.error("Exception loop multicam URL to create gif: "+ str(ex) )
						except Exception as ex:
							self._logger.error("Exception occured on getting multicam options: "+ str(ex) )
					else:
						ret = self.main.create_gif_new(chat_id,10,0)

					if ret == "":
						ret = self.main.create_gif_new(chat_id,10,0)

					if ret != "" and not sendOneInLoop:
						self.main.send_file(chat_id, ret,"")
				except Exception as ex:
					self._logger.error("Exception occured during creating of the supergif: "+ str(ex) )
					self.main.send_msg(self.gEmo('dizzy face') + " Problem creating super gif, please check log file",chatID=chat_id)
			else:
				self.main.on_event("StatusNotPrinting", {},chatID=chat_id)
		else:
			self.main.send_msg(self.gEmo('dizzy face') + " Sending GIF is disabled in plugin settings.",chatID=chat_id)

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
						self.cmdSettings(chat_id,from_id,cmd,"back")
						return
					if self.SettingsTemp[0] < 0:
						self.SettingsTemp[0] = 0
				msg = self.gEmo('height') + gettext(" Set new height.\nCurrent:  *%(height).2fmm*",height=self.SettingsTemp[0])
				keys = [
						[["+10","/settings_h_+"],["+1","/settings_h_++"],["+.1","/settings_h_+++"],["+.01","/settings_h_++++"]],
						[["-10","/settings_h_-"],["-1","/settings_h_--"],["-.1","/settings_h_---"],["-.01","/settings_h_----"]],
						[[self.main.emojis['save']+" Save","/settings_h_s"],[self.main.emojis['leftwards arrow with hook']+" Back","/settings_back"]]
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
						self.cmdSettings(chat_id,from_id,cmd,"back")
						return
					if self.SettingsTemp[1] < 0:
						self.SettingsTemp[1] = 0
				msg = self.gEmo('clock') + gettext(" Set new time.\nCurrent: *%(time)dmin*",time=self.SettingsTemp[1])
				keys = [
						[["+10","/settings_t_+"],["+1","/settings_t_++"]],
						[["-10","/settings_t_-"],["-1","/settings_t_--"]],
						[[self.main.emojis['save']+" Save","/settings_t_s"],[self.main.emojis['leftwards arrow with hook']+" Back","/settings_back"]]
					]
				self.main.send_msg(msg,chatID=chat_id,responses=keys,msg_id = self.main.getUpdateMsgId(chat_id),markup="Markdown")
			elif params[0] =="g":
				if self.main._settings.get_boolean(["send_gif"]):
					self.main._settings.set_int(['send_gif'], 0, force=True)
				else:
					self.main._settings.set_int(['send_gif'], 1, force=True)
				self.main._settings.save()
				self.cmdSettings(chat_id,from_id,cmd,"back")
				return
			elif params[0] == "m":
				if self.main._settings.get_boolean(["multicam"]):
					self.main._settings.set_int(['multicam'], 0, force=True)
				else:
					self.main._settings.set_int(['multicam'], 1, force=True)
				self.main._settings.save()
				self.cmdSettings(chat_id,from_id,cmd,"back")
				return
		else:
			if self.main._settings.get_boolean(["send_gif"]):
				gif_txt = "Desactivate gif"
				gif_emo = self.gEmo('check')
			else:
				gif_txt = "Activate gif"
				gif_emo = self.gEmo('error')

			if self.main._settings.get_boolean(["multicam"]):
				multicam_txt = "Desactivate management of multicam"
				multicam_emo = self.gEmo('check')
			else:
				multicam_txt = "Activate mangement of multicam"
				multicam_emo = self.gEmo('error')


			self.SettingsTemp = [self.main._settings.get_float(["notification_height"]),self.main._settings.get_float(["notification_time"])]
			msg = self.gEmo('settings') + gettext(" *Current notification settings are:*\n\n"+self.gEmo('height')+" Height: %(height).2fmm\n\n"+self.gEmo('clock')+" Time: %(time)dmin\n\n"+self.gEmo('film frame')+" Gif is activate: "+gif_emo+"\n\n"+self.gEmo('video camera')+" Multicam is activate: "+multicam_emo,
				height=self.main._settings.get_float(["notification_height"]),
				time=self.main._settings.get_int(["notification_time"]))

			msg_id=self.main.getUpdateMsgId(chat_id) if parameter == "back" else ""
			self.main.send_msg(msg, responses=[[[self.main.emojis['height']+gettext(" Set height"),"/settings_h"], [self.main.emojis['clock']+gettext(" Set time"),"/settings_t"], [self.main.emojis['film frame']+gettext(gif_txt),"/settings_g"], [self.main.emojis['video camera']+gettext(multicam_txt),"/settings_m"]], [[self.main.emojis['cross mark']+gettext(" Close"),"No"]]],chatID=chat_id,msg_id=msg_id,markup="Markdown")
############################################################################################
	def cmdAbort(self,chat_id,from_id,cmd,parameter):
		if parameter and parameter == "stop":
			self.main._printer.cancel_print()
			self.main.send_msg(self.gEmo('info') + gettext(" Aborting the print."),chatID=chat_id, msg_id = self.main.getUpdateMsgId(chat_id))
		else:
			if self.main._printer.is_printing():
				self.main.send_msg(self.gEmo('question') + gettext(" Really abort the currently running print?"), responses=[[[self.main.emojis['check']+gettext(" Stop print"),"/abort_stop"], [self.main.emojis['cross mark']+gettext(" Close"),"No"]]],chatID=chat_id)
			else:
				self.main.send_msg(self.gEmo('info') + gettext(" Currently I'm not printing, so there is nothing to stop."),chatID=chat_id,inline=False)
############################################################################################
	def cmdTogglePause(self,chat_id,from_id,cmd,parameter):
		msg = ""
		if self.main._printer.is_printing():
			msg =self.gEmo('hourglass') + " Pausing the print."
			self.main._printer.toggle_pause_print()
		elif self.main._printer.is_paused():
			msg =self.gEmo('black right-pointing triangle') + " Resuming the print."
			self.main._printer.toggle_pause_print()
		else:
			msg = "  Currently I'm not printing, so there is nothing to pause/resume."
		self.main.send_msg(msg, chatID=chat_id,inline=False)
############################################################################################
	def cmdShutup(self,chat_id,from_id,cmd,parameter):
		if chat_id not in self.main.shut_up:
			self.main.shut_up[chat_id] = 0
		self.main.shut_up[chat_id] += 1
		if self.main.shut_up[chat_id] >= 5:
			self._logger.warn("shut_up value is %d. Shutting down.", self.main.shut_up[chat_id])
			self.main.shutdown()
		self.main.send_msg(self.gEmo('noNotify') + gettext(" Okay, shutting up until the next print is finished." + self.gEmo('shutup')+" Use /dontshutup to let me talk again before that. "),chatID=chat_id,inline=False)
############################################################################################
	def cmdNShutup(self,chat_id,from_id,cmd,parameter):
		if chat_id in self.main.shut_up:
			self.main.shut_up[chat_id] = 0
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
					self.main.send_msg(msg,noMarkup=True, msg_id = self.main.getUpdateMsgId(chat_id), responses=[[[self.main.emojis['check']+gettext("Print"),"/print_s"], [self.main.emojis['cross mark']+gettext(" Cancel"),"/print_x"]]],chatID=chat_id)
				elif not self.main._printer.is_operational():
					self.main.send_msg(self.gEmo('warning') + gettext(" Can't start printing: I'm not connected to a printer."),chatID=chat_id, msg_id = self.main.getUpdateMsgId(chat_id))
				else:
					self.main.send_msg(self.gEmo('warning') + gettext(" Uh oh... Problems on loading the file for print."),chatID=chat_id, msg_id = self.main.getUpdateMsgId(chat_id))
		else:
			self.cmdFiles(chat_id,from_id,cmd,parameter)
############################################################################################
	def cmdFiles(self,chat_id,from_id,cmd,parameter):
		try:
			if parameter:
				par = 		parameter.split('|')
				pathHash = 	par[0]
				page = 		int(par[1])
				fileHash = 	par[2] if len(par) > 2 else ""
				opt = 		par[3] if len(par) > 3 else ""
				if fileHash == "" and opt =="":
					self.fileList(pathHash,page,cmd,chat_id)
				elif opt == "":
					self.fileDetails(pathHash,page,cmd,fileHash,chat_id,from_id)
				else:
					if opt.startswith("dir"):
						self.fileList(fileHash,0,cmd,chat_id)
					else:
						self.fileOption(pathHash,page,cmd,fileHash,opt,chat_id,from_id)
			else:
				storages = self.main._file_manager.list_files(recursive=False)
				if len(list(storages.keys())) < 2:
					self.main.send_msg("Loading files...",chatID=chat_id)
					self.generate_dir_hash_dict()
					self.cmdFiles(chat_id,from_id,cmd,self.hashMe(str(list(storages.keys())[0]+"/"),8)+"|0")
				else:
					self.generate_dir_hash_dict()
					keys=[]
					keys.extend([([k,(cmd+"_"+self.hashMe(k,8)+"/|0")] for k in storages)])
					keys.append([[self.main.emojis['cross mark']+" Close","No"]])
					msg_id=self.main.getUpdateMsgId(chat_id) if parameter == "back" else ""
					self.main.send_msg(self.gEmo('save') + " *Select Storage*",chatID=chat_id,markup="Markdown",responses=keys,msg_id=msg_id)
		except Exception as e:
			self._logger.warn("Command failed: %s" % e)
			self.main.send_msg(self.gEmo('warning') + " Command failed with exception: %s!" % e,chatID = chat_id, msg_id = self.main.getUpdateMsgId(chat_id))
############################################################################################
	def cmdUpload(self,chat_id,from_id,cmd,parameter):
		self.main.send_msg(self.gEmo('info') + " To upload a gcode file, just send it to me.\nThe file will be stored in 'TelegramPlugin' folder.",chatID=chat_id)
############################################################################################
	def cmdSys(self,chat_id,from_id,cmd,parameter):
		if parameter and parameter != "back":
			params = parameter.split('_')
			if params[0] == "sys":
				if params[1] != "do":
					self.main.send_msg(self.gEmo('question') +" *"+ params[1]+"*\nExecute system command?",responses=[[[self.main.emojis['check']+gettext(" Execute"),"/sys_sys_do_"+params[1]], [self.main.emojis['leftwards arrow with hook']+ gettext(" Back"),"/sys_back"]]],chatID=chat_id, msg_id = self.main.getUpdateMsgId(chat_id), markup="Markdown")
					return
				try:
					if params[2] == "Restart OctoPrint":
						myCmd = self.main._settings.global_get(['server','commands','serverRestartCommand'])
					elif params[2] == "Reboot System":
						myCmd = self.main._settings.global_get(['server','commands','systemRestartCommand'])
					elif params[2] == "Shutdown System":
						myCmd = self.main._settings.global_get(['server','commands','systemShutdownCommand'])

					p = sarge.run(myCmd, stderr=sarge.Capture(), shell=True, async_=False)

					if p.returncode != 0:
						returncode = p.returncode
						stderr_text = p.stderr.text
						self._logger.warn("Command failed with return code %i: %s" % (returncode, stderr_text))
						self.main.send_msg(self.gEmo('warning') + " Command failed with return code %i: %s" % (returncode, stderr_text),chatID=chat_id, msg_id = self.main.getUpdateMsgId(chat_id))
						return
					self.main.send_msg(self.gEmo('check') + " System Command executed." ,chatID=chat_id, msg_id = self.main.getUpdateMsgId(chat_id))
				except Exception as e:
					self._logger.warn("Command failed: %s" % e)
					self.main.send_msg(self.gEmo('warning') + " Command failed with exception: %s!" % e,chatID = chat_id, msg_id = self.main.getUpdateMsgId(chat_id))
					return
			elif params[0] == "do":
				parameter = params[1]
			else:
				parameter = params[0]
			actions = self.main._settings.global_get(['system','actions'])
			command = next((d for d in actions if 'action' in d and self.hashMe(d['action']) == parameter) , False)
			if command :
				if 'confirm' in command and params[0] != "do":
					self.main.send_msg(self.gEmo('question') + str(command['name'])+"\nExecute system command?",responses=[[[self.main.emojis['check'] + gettext(" Execute"),"/sys_do_" + str(parameter)], [self.main.emojis['leftwards arrow with hook'] + gettext(" Back"),"/sys_back"]]],chatID=chat_id, msg_id = self.main.getUpdateMsgId(chat_id))
					return
				else:
					async_ = command["async"] if "async" in command else False
					self._logger.info("Performing command: %s" % command["command"])
					try:
						# we run this with shell=True since we have to trust whatever
						# our admin configured as command and since we want to allow
						# shell-alike handling here...
						p = sarge.run(command["command"], stderr=sarge.Capture(), shell=True, async_=async_)
						if not async_:
							if p.returncode != 0:
								returncode = p.returncode
								stderr_text = p.stderr.text
								self._logger.warn("Command failed with return code %i: %s" % (returncode, stderr_text))
								self.main.send_msg(self.gEmo('warning') + " Command failed with return code %i: %s" % (returncode, stderr_text),chatID=chat_id, msg_id = self.main.getUpdateMsgId(chat_id))
								return
						self.main.send_msg(self.gEmo('check') + " System Command " + command["name"] + " executed." ,chatID=chat_id, msg_id = self.main.getUpdateMsgId(chat_id))
					except Exception as e:
						self._logger.warn("Command failed: %s" % e)
						self.main.send_msg(self.gEmo('warning') + " Command failed with exception: %s!" % e,chatID = chat_id, msg_id = self.main.getUpdateMsgId(chat_id))
			else:
				self.main.send_msg(self.gEmo('warning') + " Sorry, i don't know this System Command.",chatID=chat_id, msg_id = self.main.getUpdateMsgId(chat_id))
				return
		else:
			keys = []
			tmpKeys = []
			i = 1
			for action in self.main._settings.global_get(['system','actions']):
				if action['action'] != "divider":
					tmpKeys.append([str(action['name']),"/sys_"+self.hashMe(action['action'])])
					if i%2 == 0:
						keys.append(tmpKeys)
						tmpKeys = []
					i += 1
			if len(tmpKeys) > 0:
				keys.append(tmpKeys)

			tmpKeys = []
			i = 1
			serverCommands = { 'serverRestartCommand':   ["Restart OctoPrint", "/sys_sys_Restart OctoPrint"],
							  'systemRestartCommand':   ["Reboot System", "/sys_sys_Reboot System"],
						      'systemShutdownCommand':  ["Shutdown System","/sys_sys_Shutdown System"]
			}
			for index in serverCommands:
				commandText = self.main._settings.global_get(['server', 'commands', index])
				if commandText is not None:
					tmpKeys.append(serverCommands[index])
					if i % 2 == 0:
						keys.append(tmpKeys)
						tmpKeys = []
					i += 1
			if len(tmpKeys) > 0:
				keys.append(tmpKeys)

			if len(keys) > 0 :
				message_text = " The following System Commands are known."
			else:
				message_text = " No known System Commands."
			try:
				server_ip = [(s.connect((self.main._settings.global_get(["server","onlineCheck","host"]), self.main._settings.global_get(["server","onlineCheck","port"]))), s.getsockname()[0], s.close()) for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]
				message_text += "\n\nIP: " + server_ip
			except Exception as ex: self._logger.error("Exception retrieving IP address: " + str(ex))

			message = self.gEmo('info') + message_text

			keys.append([[self.main.emojis['cross mark']+gettext(" Close"),"No"]])
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
					self.main.send_msg(self.gEmo('question') + str(command['name']) + "\nExecute control command?",responses=[[[self.main.emojis['check']+gettext("Execute"),"/ctrl_do_" + str(parameter)], [self.main.emojis['leftwards arrow with hook']+gettext(" Back"),"/ctrl_back"]]],chatID=chat_id, msg_id = self.main.getUpdateMsgId(chat_id))
					return
				else:
					if 'script' in command:
						try:
							self.main._printer.script(command["command"])
						except UnknownScript:
							self.main.send_msg(self.gEmo('warning') + " Unknown script: " + command['command'],chatID=chat_id, msg_id = self.main.getUpdateMsgId(chat_id))
					elif type(command['command']) is type([]):
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
			try:
				for action in self.get_controls_recursively():
					empty=False
					try:
						tmpKeys.append([str(action['name']),"/ctrl_" + str(action['hash'])])
						if i%2 == 0:
							keys.append(tmpKeys)
							tmpKeys = []
						i += 1
					except Exception as ex:
						self._logger.info("An Exception in get action: " + str(ex) )
				if len(tmpKeys) > 0:
					keys.append(tmpKeys)
				keys.append([[self.main.emojis['cross mark']+gettext(" Close"),"No"]])
			except Exception as ex:
				self._logger.info("An Exception in get list action: " + str(ex) )
			if empty: message += "\n\n"+self.gEmo('warning')+" No Printer Control Command found..."
			msg_id=self.main.getUpdateMsgId(chat_id) if parameter == "back" else ""
			self.main.send_msg(message,chatID=chat_id,responses=keys,msg_id = msg_id)
############################################################################################
	def cmdUser(self,chat_id,from_id,cmd,parameter):
		msg = self.gEmo('info') + " *Your user settings:*\n\n"
		msg += "*ID:* " + str(chat_id) + "\n"
		msg += "*Name:* " + self.main.chats[chat_id]['title'] + "\n"
		if self.main.chats[chat_id]['private']:
			msg += "*Type:* Private\n\n"
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
				if self.main.chats[chat_id]['commands'][key]:
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
					self.main.send_msg(msg + self.gEmo('warning') + " You can't disconnect while printing.",responses=[[[self.main.emojis['settings']+gettext(" Defaults"),"/con_s"], [self.main.emojis['cross mark']+gettext(" Close"),"No"]]],chatID=chat_id,msg_id=msg_id,markup="Markdown")
				else:
					self.main.send_msg(msg,responses=[[[self.main.emojis['error']+gettext(" Disconnect"),"/con_d"],[self.main.emojis['settings']+gettext(" Defaults"),"/con_s"], [self.main.emojis['cross mark']+gettext(" Close"),"No"]]],chatID=chat_id,msg_id=msg_id,markup="Markdown")
			else:
				self.main.send_msg(msg,responses=[[[self.main.emojis['electric plug']+gettext(" Connect"),"/con_c"],[self.main.emojis['settings']+gettext(" Defaults"),"/con_s"],[self.main.emojis['cross mark']+gettext(" Close"),"No"]]],chatID=chat_id,msg_id=msg_id,markup="Markdown")
############################################################################################
	def cmdTune(self,chat_id,from_id,cmd,parameter):
		if parameter and parameter != "back":
			params = parameter.split('_')
			if params[0] == "feed":
				if len(params) > 1:
					base = 1000
					if params[1].endswith('*'):
						base = 2500
					if params[1].startswith('+'):
						self.tuneTemp[0] += base/(10**len(params[1]))
					elif params[1].startswith('-'):
						self.tuneTemp[0] -= base/(10**len(params[1]))
					else:
						self.main._printer.feed_rate(int(self.tuneTemp[0]))
						self.cmdTune(chat_id,from_id,cmd,"back")
						return
					if self.tuneTemp[0] < 50:
						self.tuneTemp[0] = 50
					elif self.tuneTemp[0] > 200:
						self.tuneTemp[0] = 200
				msg = self.gEmo('black right-pointing double triangle') + gettext(" Set feedrate.\nCurrent:  *%(height)d%%*",height=self.tuneTemp[0])
				keys = [
						[["+25","/tune_feed_+*"],["+10","/tune_feed_++"],["+1","/tune_feed_+++"],["-1","/tune_feed_---"],["-10","/tune_feed_--"],["-25","/tune_feed_-*"]],
						[[self.main.emojis['check']+" Set","/tune_feed_s"],[self.main.emojis['leftwards arrow with hook']+" Back","/tune_back"]]
					]
				self.main.send_msg(msg,chatID=chat_id,responses=keys,msg_id = self.main.getUpdateMsgId(chat_id),markup="Markdown")
			elif params[0] == "flow":
				if len(params) > 1:
					base = 1000
					if params[1].endswith('*'):
						base = 2500
					if params[1].startswith('+'):
						self.tuneTemp[1] += base/(10**len(params[1]))
					elif params[1].startswith('-'):
						self.tuneTemp[1] -= base/(10**len(params[1]))
					else:
						self.main._printer.flow_rate(int(self.tuneTemp[1]))
						self.cmdTune(chat_id,from_id,cmd,"back")
						return
					if self.tuneTemp[1] < 50:
						self.tuneTemp[1] = 200
					elif self.tuneTemp[1] > 200:
						self.tuneTemp[1] = 200
				msg = self.gEmo('black down-pointing double triangle') + gettext(" Set flowrate.\nCurrent: *%(time)d%%*",time=self.tuneTemp[1])
				keys = [
						[["+25","/tune_flow_+*"],["+10","/tune_flow_++"],["+1","/tune_flow_+++"],["-1","/tune_flow_---"],["-10","/tune_flow_--"],["-25","/tune_flow_-*"]],
						[[self.main.emojis['check']+" Set","/tune_flow_s"],[self.main.emojis['leftwards arrow with hook']+" Back","/tune_back"]]
					]
				self.main.send_msg(msg,chatID=chat_id,responses=keys,msg_id = self.main.getUpdateMsgId(chat_id),markup="Markdown")
			elif params[0] == "e":
				temps = self.main._printer.get_current_temperatures()
				toolNo = int(params[1])
				if len(params) > 2:
					base = 1000
					if params[2].endswith('*'):
						base = 5000
					if params[2].startswith('+'):
						self.tempTemp[toolNo] += base/(10**len(params[2]))
					elif params[2].startswith('-'):
						self.tempTemp[toolNo] -= base/(10**len(params[2]))
					elif params[2].startswith('s'):
						self.main._printer.set_temperature("tool"+str(toolNo),self.tempTemp[toolNo])
						self.cmdTune(chat_id,from_id,cmd,"back")
						return
					else:
						self.main._printer.set_temperature("tool"+str(toolNo),0)
						self.tempTemp[toolNo] = 0
						self.cmdTune(chat_id,from_id,cmd,"back")
						return
					if self.tempTemp[toolNo] < 0:
						self.tempTemp[toolNo] = 0
				msg = self.gEmo('fire') + gettext(" Set temperature for tool "+params[1]+".\nCurrent: %(temp).02f/*%(time)d"+'\u00b0'+"C*",temp=temps["tool"+params[1]]['actual'],time=self.tempTemp[toolNo])
				keys = [
						[["+100","/tune_e_"+params[1]+"_+"],["+50","/tune_e_"+params[1]+"_+*"],["+10","/tune_e_"+params[1]+"_++"],["+5","/tune_e_"+params[1]+"_++*"],["+1","/tune_e_"+params[1]+"_+++"]],
						[["-100","/tune_e_"+params[1]+"_-"],["-50","/tune_e_"+params[1]+"_-*"],["-10","/tune_e_"+params[1]+"_--"],["-5","/tune_e_"+params[1]+"_--*"],["-1","/tune_e_"+params[1]+"_---"]],
						[[self.main.emojis['check']+" Set","/tune_e_"+params[1]+"_s"],[self.main.emojis['snowflake']+" Off","/tune_e_"+params[1]+"_off"],[self.main.emojis['leftwards arrow with hook']+" Back","/tune_back"]]
					]
				self.main.send_msg(msg,chatID=chat_id,responses=keys,msg_id = self.main.getUpdateMsgId(chat_id),markup="Markdown")
			elif params[0] == "b":
				temps = self.main._printer.get_current_temperatures()
				toolNo = len(self.tempTemp)-1
				if len(params) > 1:
					base = 1000
					if params[1].endswith('*'):
						base = 5000
					if params[1].startswith('+'):
						self.tempTemp[toolNo] += base/(10**len(params[1]))
					elif params[1].startswith('-'):
						self.tempTemp[toolNo] -= base/(10**len(params[1]))
					elif params[1].startswith('s'):
						self.main._printer.set_temperature("bed",self.tempTemp[toolNo])
						self.cmdTune(chat_id,from_id,cmd,"back")
						return
					else:
						self.main._printer.set_temperature("bed",0)
						self.tempTemp[toolNo] = 0
						self.cmdTune(chat_id,from_id,cmd,"back")
						return
					if self.tempTemp[toolNo] < 0:
						self.tempTemp[toolNo] = 0
				self._logger.debug("BED TEMPS: "+str(temps))
				self._logger.debug("BED self.TEMPS: "+str(self.tempTemp))
				msg = self.gEmo('hot springs') + gettext(" Set temperature for bed.\nCurrent: %(temp).02f/*%(time)d"+'\u00b0'+"C*",temp=temps["bed"]['actual'],time=self.tempTemp[toolNo])
				keys = [
						[["+100","/tune_b_+"],["+50","/tune_b_+*"],["+10","/tune_b_++"],["+5","/tune_b_++*"],["+1","/tune_b_+++"]],
						[["-100","/tune_b_-"],["-50","/tune_b_-*"],["-10","/tune_b_--"],["-5","/tune_b_--*"],["-1","/tune_b_---"]],
						[[self.main.emojis['check']+" Set","/tune_b_s"],[self.main.emojis['snowflake']+" Off","/tune_b_off"],[self.main.emojis['leftwards arrow with hook']+" Back","/tune_back"]]
					]
				self.main.send_msg(msg,chatID=chat_id,responses=keys,msg_id = self.main.getUpdateMsgId(chat_id),markup="Markdown")
		else:
			msg = self.gEmo('settings') + gettext(" *Tune print stettings*")
			profile = self.main._printer_profile_manager.get_current()
			temps = self.main._printer.get_current_temperatures()
			self.tempTemp = []
			msg_id=self.main.getUpdateMsgId(chat_id) if parameter == "back" else ""
			keys = [[[self.main.emojis['black right-pointing double triangle']+gettext(" Feedrate"),"/tune_feed"], [self.main.emojis['black down-pointing double triangle']+gettext(" Flowrate"),"/tune_flow"]]]
			if self.main._printer.is_operational():
				tmpKeys=[]
				for i in range(0,profile["extruder"]["count"]):
					tmpKeys.append([self.main.emojis['wrench']+" Tool "+str(i),"/tune_e_"+str(i)])
					self.tempTemp.append(int(temps["tool"+str(i)]['target']))
				if profile["heatedBed"]:
					tmpKeys.append([self.main.emojis['hot springs']+" Bed","/tune_b"])
					self.tempTemp.append(int(temps["bed"]['target']))
				keys.append(tmpKeys)
			keys.append([[self.main.emojis['cross mark']+gettext(" Close"),"No"]])
			self.main.send_msg(msg, responses=keys,chatID=chat_id,msg_id=msg_id,markup="Markdown")
############################################################################################
	def cmdFilament(self,chat_id,from_id,cmd,parameter):
		if parameter and parameter != "back":
			self._logger.info("Parameter received for filament: %s" % parameter)
			params = parameter.split('_')
			apikey = self.main._settings.global_get(['api','key'])
			errorText = ""
			if params[0] == "spools":
				try:
					resp = requests.get("http://localhost:" + str(self.port) + "/plugin/filamentmanager/spools?apikey="+apikey)
					resp2 = requests.get("http://localhost:" + str(self.port) + "/plugin/filamentmanager/selections?apikey="+apikey)
					if (resp.status_code != 200):
						errorText = resp.text
					resp = resp.json()
					resp2 = resp2.json()
					self._logger.info("Spools: %s" % resp["spools"])
					message = self.gEmo('info') + " Available filament spools are:\n"
					for spool in resp["spools"]:
						weight = spool["weight"]
						used = spool["used"]
						percent = int(100 - (used / weight * 100))
						message += str(spool["profile"]["vendor"]) + " " + str(spool["name"]) + " " + str(spool["profile"]["material"]) + " [" + str(percent) + "%]\n"
					for selection in resp2["selections"]:
						if selection["tool"] == 0:
							message += "\n\nCurrently selected: " + str(selection["spool"]["profile"]["vendor"]) + " " + str(selection["spool"]["name"]) + " " + str(selection["spool"]["profile"]["material"])
					msg_id=self.main.getUpdateMsgId(chat_id)
					self.main.send_msg(message,chatID=chat_id,msg_id = msg_id,inline=False)
				except ValueError:
					message = self.gEmo('mistake')+" Error getting spools. Are you sure, you have installed the Filament Manager Plugin?"
					if (errorText != ""):
						message += "\nError text: " + str(errorText)
					msg_id=self.main.getUpdateMsgId(chat_id)
					self.main.send_msg(message,chatID=chat_id,msg_id = msg_id,inline=False)
			if params[0] == "changeSpool":
				self._logger.info("Command to change spool: %s" % params)
				if len(params) > 1:
					self._logger.info("Changing to spool: %s" % params[1])
					try:
						payload = {"selection": {"spool": {"id": params[1]},"tool": 0}}
						self._logger.info("Payload: %s" % payload)
						resp = requests.patch("http://localhost:" + str(self.port) + "/plugin/filamentmanager/selections/0?apikey="+apikey, json=payload, headers={'Content-Type': 'application/json'})
						if (resp.status_code != 200):
							errorText = resp.text
						self._logger.info("Response: %s" % resp)
						resp = resp.json()
						message = self.gEmo('check') + " Selected spool is now: " + str(resp["selection"]["spool"]["profile"]["vendor"]) + " " + str(resp["selection"]["spool"]["name"]) + " " + str(resp["selection"]["spool"]["profile"]["material"])
						msg_id=self.main.getUpdateMsgId(chat_id)
						self.main.send_msg(message,chatID=chat_id,msg_id = msg_id,inline=False)
					except ValueError:
						message = self.gEmo('mistake')+" Error changing spool"
						if (errorText != ""):
							message += "\nError text: " + str(errorText)
						msg_id=self.main.getUpdateMsgId(chat_id)
						self.main.send_msg(message,chatID=chat_id,msg_id = msg_id,inline=False)
				else:
					self._logger.info("Asking for spool")
					try:
						resp = requests.get("http://localhost:" + str(self.port) + "/plugin/filamentmanager/spools?apikey="+apikey)
						if (resp.status_code != 200):
							errorText = resp.text
						resp = resp.json()
						message = self.gEmo('question') + " which filament spool do you want to select?"
						keys = []
						tmpKeys = []
						i = 1
						for spool in resp["spools"]:
							self._logger.info("Appending spool: %s" % spool)
							tmpKeys.append([str(spool["profile"]["vendor"]) + " " + str(spool['name']) + " " + str(spool["profile"]["material"]) ,"/filament_changeSpool_" + str(spool['id'])])
							if i%2 == 0:
								keys.append(tmpKeys)
								tmpKeys = []
							i += 1
						if len(tmpKeys) > 0:
							keys.append(tmpKeys)
						keys.append([[self.main.emojis['cross mark']+gettext(" Close"),"No"]])
						msg_id=self.main.getUpdateMsgId(chat_id)
						self._logger.info("Sending message")
						self.main.send_msg(message,chatID=chat_id,responses=keys,msg_id=msg_id)
					except ValueError:
						message = self.gEmo('mistake')+" Error changing spool"
						if (errorText != ""):
							message += "\nError text: " + str(errorText)
						msg_id=self.main.getUpdateMsgId(chat_id)
						self.main.send_msg(message,chatID=chat_id,msg_id = msg_id,inline=False)
		else:
			message = self.gEmo('info') + " The following Filament Manager commands are known."
			keys = []
			keys.append([["Show spools","/filament_spools"]])
			keys.append([["Change spool","/filament_changeSpool"]])
			keys.append([[self.main.emojis['cross mark']+gettext(" Close"),"No"]])
			msg_id=self.main.getUpdateMsgId(chat_id) if parameter == "back" else ""
			self.main.send_msg(message,chatID=chat_id,responses=keys,msg_id=msg_id)

############################################################################################
	def cmdHelp(self,chat_id,from_id,cmd,parameter):
		self.main.send_msg(self.gEmo('info') + gettext(" *The following commands are known:*\n\n"
		                           "/abort - Aborts the currently running print. A confirmation is required.\n"
		                           "/shutup - Disables automatic notifications till the next print ends.\n"
		                           "/dontshutup - The opposite of /shutup - Makes the bot talk again.\n"
		                           "/status - Sends the current status including a current photo.\n"
								   "/gif - Sends a gif from the current video. "+ self.gEmo('warning') +" \n"
								   "/supergif - Sends a bigger gif from the current video.\n"
		                           "/settings - Displays the current notification settings and allows you to change them.\n"
		                           "/files - Lists all the files available for printing.\n"
								   "/filament - Shows you your filament spools or lets you change it. Requires the Filament Manager Plugin.\n"
		                           "/print - Lets you start a print. A confirmation is required.\n"
		                           "/togglepause - Pause/Resume current Print.\n"
		                           "/con - Connect/disconnect printer.\n"
		                           "/upload - You can just send me a gcode file to save it to my library.\n"
		                           "/sys - Execute Octoprint System Commands.\n"
		                           "/ctrl - Use self defined controls from Octoprint.\n"
		                           "/tune - Set feed- and flowrate. Control temperatures.\n"
		                           "/user - Get user info.\n"
		                           "/help - Show this help message."),chatID=chat_id,markup="Markdown")
############################################################################################
# FILE HELPERS
############################################################################################
	def fileList(self,pathHash,page,cmd,chat_id,wait = 0):
		try:
			fullPath = self.dirHashDict[pathHash]
			storageKeys = list(self.main._file_manager.list_files(recursive=False).keys())
			dest = fullPath.split("/")[0]
			pathWoDest = "/".join(fullPath.split("/")[1:]) if len(fullPath.split("/")) > 1 else fullPath
			path = "/".join(fullPath.split("/")[1:])
			self._logger.debug("fileList path : " + str(path) )
			fileList = self.main._file_manager.list_files(path = path, destinations = dest, recursive=False)
			files = fileList[dest]
			arrayD = []
			self._logger.debug("fileList before loop folder " )
			if self.main.version >= 1.3:
				M =  {k:v for k,v in files.items() if v['type'] == "folder"}
				for key in M:
					arrayD.append([self.main.emojis['open file folder']+" "+key,cmd+"_"+pathHash+"|0|"+self.hashMe(fullPath+key+"/",8)+"|dir"])
			array = []
			self._logger.debug("fileList before loop files items")
			L = {k:v for k,v in files.items() if v['type']=="machinecode"}
			for key,val in sorted(iter(L.items()), key=lambda x: x[1]['date'] , reverse=True):
				try:
					self._logger.debug("should get info on item " )
					vfilename = self.main.emojis['page facing up']+" "+('.').join(key.split('.')[:-1])
					self._logger.debug("vfilename : " + str(vfilename) )
					vhash = self.hashMe(pathWoDest + key)
					self._logger.debug("vhash : " + str(vhash) )
					if vhash != "":
						vcmd = cmd+"_" + pathHash + "|"+str(page)+"|"+ vhash
						self._logger.debug("cmd : " + str(cmd) )
						array.append([vfilename,vcmd])
				except Exception as ex:
					self._logger.error("An Exception in fileList loop file items : " + str(ex) )
					self._logger.error("files[key]" + str(files[key]))
			arrayD = sorted(arrayD)
			if not self.main._settings.get_boolean(["fileOrder"]):
				arrayD.extend(sorted(array))
			else:
				arrayD.extend(array)
			files = arrayD
			pageDown = page-1 if page > 0 else 0
			pageUp = page+1 if len(files)-(page+1)*10 > 0 else page
			keys = []
			tmpKeys = []
			i = 1
			self._logger.debug("fileList before check nbpages " )
			for k in files[page*10:page*10+10]:
				tmpKeys.append(k)
				if not i%2:
					keys.append(tmpKeys)
					tmpKeys = []
				i += 1
			if len(tmpKeys):
				keys.append(tmpKeys)
			tmpKeys = []
			backBut = [[self.main.emojis['settings'],cmd+"_" + pathHash + "|"+str(page)+"|0|s"],[self.main.emojis['cross mark']+" Close","No"]] if len(fullPath.split("/")) < 3 else [[self.main.emojis['leftwards arrow with hook']+" Back",cmd+"_"+self.hashMe("/".join(fullPath.split("/")[:-2])+"/",8)+"|0"],[self.main.emojis['settings'],cmd+"_" + pathHash + "|"+str(page)+"|0|s"],[self.main.emojis['cross mark']+" Close","No"]]
			if pageDown != pageUp:
				if pageDown != page:
					tmpKeys.append([self.main.emojis['black left-pointing triangle'],cmd+"_"+pathHash+"|"+ str(pageDown)])
				if pageUp != page:
					tmpKeys.append([self.main.emojis['black right-pointing triangle'],cmd+"_"+pathHash+"|"+str(pageUp)])
				tmpKeys.extend(backBut)

			else:
				tmpKeys.extend(backBut)
			keys.append(tmpKeys)
			pageStr = str(page+1)+"/"+str(len(files)/10 + (1 if len(files)%10 > 0 else 0))
			self._logger.debug("fileList before send msg " )
			self.main.send_msg(self.gEmo('save') + " Files in */"+pathWoDest[:-1]+"*    \["+pageStr+"]",chatID=chat_id,markup="Markdown",responses=keys,msg_id = self.main.getUpdateMsgId(chat_id),delay=wait)
		except Exception as ex:
			self._logger.error("An Exception in fileList : " + str(ex) )
############################################################################################
	def fileDetails(self,pathHash,page,cmd,fileHash,chat_id,from_id,wait=0):
		dest, path, file = self.find_file_by_hash(fileHash)
		self.tmpFileHash = ""
		meta = self.main._file_manager.get_metadata(dest,path)
		msg = self.gEmo("info") + " <b>File Informations</b>\n\n"
		msg += "<b>"+self.main.emojis['name badge']+"Name:</b> " + path
		try:
			msg += "\n<b>"+self.main.emojis['clock face twelve oclock']+"Uploaded:</b> " + datetime.datetime.fromtimestamp(file['date']).strftime('%Y-%m-%d %H:%M:%S')
		except Exception as ex:
			self._logger.info("An Exception in get upload time : " + str(ex) )
		msg += "\n<b>"+self.main.emojis['flexed biceps']+"Size:</b> " + self.formatSize(file['size'])
		filaLen = 0
		printTime = 0
		if 'analysis' in meta:
			if 'filament' in meta['analysis']:
				msg += "\n<b>"+self.main.emojis['straight ruler']+"Filament:</b> "
				filament = meta['analysis']['filament']
				if len(filament) == 1 and 'length' in filament['tool0']:
					msg += self.formatFilament(filament['tool0'])
					filaLen += float(filament['tool0']['length'])
				else:
					for key in sorted(filament):
						if 'length' in filament[key]:
							msg +=  "\n      "+str(key)+": "+ self.formatFilament(filament[key])
							filaLen += float(filament[key]['length'])
			if 'estimatedPrintTime' in meta['analysis']:
				msg += "\n<b>"+self.main.emojis['hourglass with flowing sand']+"Print Time:</b> "+ self.formatFuzzyPrintTime(meta['analysis']['estimatedPrintTime'])
				printTime = meta['analysis']['estimatedPrintTime']
        # giloser 17/07/19''
		try:
			time_finish = self.main.calculate_ETA(printTime)
			msg += "\n<b>"+self.main.emojis['chequered flag']+"Completed Time:</b> "+ time_finish
		except Exception as ex:
			self._logger.info("An Exception in get final time : " + str(ex) )
		if self.main._plugin_manager.get_plugin("cost"):
			if printTime != 0 and filaLen != 0:
				try:
					cpH = self.main._settings.global_get_float(["plugins","cost","cost_per_time"])
					cpM = self.main._settings.global_get_float(["plugins","cost","cost_per_length"])
					curr = self.main._settings.global_get(["plugins","cost","currency"])
					try:
						curr = curr
						msg += "\n<b>"+self.main.emojis['money bag']+"Cost:</b> "+curr+"%.02f " % ((filaLen/1000) * cpM + (printTime/3600) * cpH)
					except Exception as ex:
						self._logger.error("An Exception the cost function in decode : " + str(ex) )
						msg += "\n<b>"+self.main.emojis['money bag']+"Cost:</b> -"
				except Exception as ex:
					self._logger.error("An Exception the cost function on get: " + str(ex) )
					msg += "\n<b>"+self.main.emojis['money bag']+"Cost:</b> -"
			else:
				msg += "\n<b>"+self.main.emojis['money bag']+"Cost:</b> -"
		keyPrint = [self.main.emojis['rocket']+" Print","/print_"+fileHash]
		keyDetails = [self.main.emojis['left-pointing magnifying glass']+" Details",cmd+"_"+pathHash+"|"+str(page)+"|"+fileHash+"|inf"]
		keyDownload = [self.main.emojis['save']+" Download",cmd+"_"+pathHash+"|"+str(page)+"|"+fileHash+"|dl"]
		keyMove = [self.main.emojis['black scissors']+" Move",cmd+"_"+pathHash+"|"+str(page)+"|"+fileHash+"|m"]
		keyCopy = [self.main.emojis['clipboard']+" Copy",cmd+"_"+pathHash+"|"+str(page)+"|"+fileHash+"|c"]
		keyDelete = [self.main.emojis['error']+" Delete",cmd+"_"+pathHash+"|"+str(page)+"|"+fileHash+"|d"]
		keyBack = [self.main.emojis['leftwards arrow with hook']+" Back",cmd+"_"+pathHash+"|"+str(page)]
		keysRow = []
		keys = []
		chkID = chat_id
		if self.main.isCommandAllowed(chat_id, from_id, "/print"):
			keysRow.append(keyPrint)
		keysRow.append(keyDetails)
		keys.append(keysRow)
		keysRow = []
		if self.main.isCommandAllowed(chat_id, from_id, "/files"):
			if self.main.version >= 1.3:
				keysRow.append(keyMove)
				keysRow.append(keyCopy)
			keysRow.append(keyDelete)
			keys.append(keysRow)
			keysRow = []
			if self.dirHashDict[pathHash].split("/")[0] == octoprint.filemanager.FileDestinations.LOCAL:
				keysRow.append(keyDownload)
		keysRow.append(keyBack)
		keys.append(keysRow)
		self.main.send_msg(msg,chatID=chat_id,markup="HTML",responses=keys,msg_id = self.main.getUpdateMsgId(chat_id),delay=wait)
############################################################################################
	def fileOption(self,loc,page,cmd,hash,opt,chat_id,from_id):
		if opt != "m_m" and opt != "c_c":
			dest, path, file = self.find_file_by_hash(hash)
			meta = self.main._file_manager.get_metadata(dest,path)
		if opt.startswith("inf"):
			msg = self.gEmo("info") + " <b>Detailed File Informations</b>\n\n"
			msg += "<b>"+self.main.emojis['name badge']+"Name:</b> " + path
			msg += "\n<b>"+self.main.emojis['flexed biceps']+"Size:</b> " + self.formatSize(file['size'])
			msg += "\n<b>"+self.main.emojis['clock face twelve oclock']+"Uploaded:</b> " + datetime.datetime.fromtimestamp(file['date']).strftime('%Y-%m-%d %H:%M:%S')
			filaLen = 0
			printTime = 0
			if 'analysis' in meta:
				if 'filament' in meta['analysis']:
					msg += "\n<b>"+self.main.emojis['straight ruler']+"Filament:</b> "
					filament = meta['analysis']['filament']
					if len(filament) == 1 and 'length' in filament['tool0']:
						msg += self.formatFilament(filament['tool0'])
						filaLen += float(filament['tool0']['length'])
					else:
						for key in sorted(filament):
							if 'length' in filament[key]:
								msg +=  "\n      "+str(key)+": "+ self.formatFilament(filament[key])
								filaLen += float(filament[key]['length'])
				if 'estimatedPrintTime' in meta['analysis']:
					msg += "\n<b>"+self.main.emojis['hourglass with flowing sand']+"Print Time:</b> "+ self.formatFuzzyPrintTime(meta['analysis']['estimatedPrintTime'])
					printTime = float(meta['analysis']['estimatedPrintTime'])
			# giloser 17/07/19 add ETA and try catch on cost plugin + emo
			try:
				time_finish = self.main.calculate_ETA(printTime)
				msg += "\n<b>"+self.main.emojis['chequered flag']+"Completed Time:</b> "+ time_finish
			except Exception as ex:
				self._logger.error("An Exception in get final time : " + str(ex) )
			if self.main._plugin_manager.get_plugin("cost"):
				if printTime != 0 and filaLen != 0:
					try:
						cpH = self.main._settings.global_get_float(["plugins","cost","cost_per_time"])
						cpM = self.main._settings.global_get_float(["plugins","cost","cost_per_length"])
						curr = self.main._settings.global_get(["plugins","cost","currency"])
						try:
							curr = curr
							msg += "\n<b>"+self.main.emojis['money bag']+"Cost:</b> "+curr+"%.02f " % ((filaLen/1000) * cpM + (printTime/3600) * cpH)
						except Exception as ex:
							self._logger.error("An Exception the cost function in decode : " + str(ex) )
							msg += "\n<b>"+self.main.emojis['money bag']+"Cost:</b> -"
						self._logger.debug("AF TRY")
					except Exception as ex:
						self._logger.error("An Exception the cost function on get: " + str(ex) )
						msg += "\n<b>"+self.main.emojis['money bag']+"Cost:</b> -"
				else:
					msg += "\n<b>"+self.main.emojis['money bag']+"Cost:</b> -"
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
			if 'history' in meta:
				if len(meta['history'])>0:
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
			self.main.send_msg(msg,chatID=chat_id,responses=[[[self.main.emojis['leftwards arrow with hook']+" Back",cmd+"_" + loc + "|"+str(page)+"|"+ hash]]],msg_id=self.main.getUpdateMsgId(chat_id),markup="HTML")
		elif opt.startswith("dl"):
			mb = float(file['size']) /1024/1024
			if mb > 50:
				self.main.send_msg(self.gEmo('warning')+path+" ist to big to download (>50MB)!",chatID=chat_id,msg_id=self.main.getUpdateMsgId(chat_id))
				self.fileDetails(loc,page,cmd,hash,chat_id,from_id,wait=3)
			else:
				self.main.send_file(chat_id,self.main._file_manager.path_on_disk(dest,path),"")
		elif opt.startswith("m"):
			msg_id = self.main.getUpdateMsgId(chat_id)
			if opt == "m_m":
				destM, pathM, fileM = self.find_file_by_hash(self.tmpFileHash)
				targetPath = self.dirHashDict[hash]
				cpRes = self.fileCopyMove(destM,"move",pathM,"/".join(targetPath.split("/")[1:]))
				self._logger.debug("OUT MOVE: "+cpRes)
				if cpRes == "GOOD":
					self.main.send_msg(self.gEmo('info')+" File "+pathM+" moved",chatID=chat_id,msg_id=msg_id)
					self.fileList(loc,page,cmd,chat_id,wait = 3)
				else:
					self.main.send_msg(self.gEmo('warning')+"FAILED: Move file "+pathM+"\nReason: "+cpRes,chatID=chat_id,msg_id=msg_id)
					self.fileDetails(loc,page,cmd,self.tmpFileHash,chat_id,from_id,wait = 3)
			else:
				keys = [[[self.main.emojis['leftwards arrow with hook']+" Back",cmd+"_" + loc + "|"+str(page)+"|"+ hash]]]
				self.tmpFileHash = hash
				for key,val in sorted(list(self.dirHashDict.items()), key = operator.itemgetter(1)):
					keys.append([[self.main.emojis['open file folder']+" "+self.dirHashDict[key],cmd+"_" + loc + "|"+str(page)+"|"+ key + "|m_m"]])
				self.main.send_msg(self.gEmo('question') + " *Choose destination to move file*",chatID=chat_id,responses=keys,msg_id=msg_id,markup="Markdown")

		elif opt.startswith("c"):
			msg_id = self.main.getUpdateMsgId(chat_id)
			if opt == "c_c":
				destM, pathM, fileM = self.find_file_by_hash(self.tmpFileHash)
				targetPath = self.dirHashDict[hash]
				cpRes = self.fileCopyMove(destM,"copy",pathM,"/".join(targetPath.split("/")[1:]))
				if cpRes == "GOOD":
					self.main.send_msg(self.gEmo('info')+" File "+pathM+" copied",chatID=chat_id,msg_id=msg_id)
					self.fileList(loc,page,cmd,chat_id,wait = 3)
				else:
					self.main.send_msg(self.gEmo('warning')+"FAILED: Copy file "+pathM+"\nReason: "+cpRes,chatID=chat_id,msg_id=msg_id)
					self.fileDetails(loc,page,cmd,self.tmpFileHash,chat_id,from_id,wait = 3)
			else:
				keys = [[[self.main.emojis['leftwards arrow with hook']+" Back",cmd+"_" + loc + "|"+str(page)+"|"+ hash]]]
				self.tmpFileHash = hash
				for key,val in sorted(list(self.dirHashDict.items()), key = operator.itemgetter(1)):
					keys.append([[self.main.emojis['open file folder']+" "+self.dirHashDict[key],cmd+"_" + loc + "|"+str(page)+"|"+ key + "|c_c"]])
				self.main.send_msg(self.gEmo('question') + " *Choose destination to copy file*",chatID=chat_id,responses=keys,msg_id=msg_id,markup="Markdown")

		elif opt.startswith("d"):
			msg_id = self.main.getUpdateMsgId(chat_id)
			if opt == "d_d":
				delRes = self.fileDelete(dest, path)
				if delRes == "GOOD"	:
					self.main.send_msg(self.gEmo('info')+" File "+path+" deleted",chatID=chat_id,msg_id=msg_id)
					self.fileList(loc,page,cmd,chat_id,wait = 3)
				else:
					self.main.send_msg(self.gEmo('warning')+"FAILED: Delete file "+path+"\nReason: "+delRes,chatID=chat_id,msg_id=msg_id)
					self.fileList(loc,page,cmd,chat_id,wait = 3)
			else:
				keys = [[[self.main.emojis['check']+" Yes",cmd+"_" + loc + "|"+str(page)+"|"+ hash+"|d_d"],[self.main.emojis['cross mark']+" No",cmd+"_" + loc + "|"+str(page)+"|"+ hash]]]
				self.main.send_msg(self.gEmo('warning')+" Delete "+path+" ?",chatID=chat_id,responses=keys,msg_id=msg_id)
		elif opt.startswith("s"):
			if opt == "s_n":
				self.main._settings.set_boolean(["fileOrder"],False)
				self.fileList(loc,page,cmd,chat_id)
			elif opt == "s_d":
				self.main._settings.set_boolean(["fileOrder"],True)
				self.fileList(loc,page,cmd,chat_id)
			else:
				keys = [[[self.main.emojis['input symbol for latin letters']+" By name",cmd+"_"+loc+"|"+str(page)+"|"+hash+"|s_n"], [self.main.emojis['tear-off calendar']+" By date",cmd+"_"+loc+"|"+str(page)+"|"+hash+"|s_d"]],[ [self.main.emojis['leftwards arrow with hook']+" Back",cmd+"_"+loc+"|"+str(page)]]]
				self.main.send_msg(self.gEmo('question') + " *Choose sorting order of files*",chatID=chat_id,markup="Markdown",responses=keys,msg_id = self.main.getUpdateMsgId(chat_id))
### From filemanager plugin - https://github.com/Salandora/OctoPrint-FileManager/blob/master/octoprint_filemanager/__init__.py
############################################################################################
	def fileCopyMove(self, target, command, source, destination):
		from octoprint.server.api.files import _verifyFolderExists, _verifyFileExists
		if not _verifyFileExists(target, source) and not _verifyFolderExists(target, source):
			return "Source does not exist"

		if _verifyFolderExists(target, destination):
			path, name = self.main._file_manager.split_path(target, source)
			destination = self.main._file_manager.join_path(target, destination, name)

		if _verifyFileExists(target, destination) or _verifyFolderExists(target, destination):
			return "Destination does not exist"

		if command == "copy":
			if self.main._file_manager.file_exists(target, source):
				self.main._file_manager.copy_file(target, source, destination)
			elif self.main._file_manager.folder_exists(target, source):
				self.main._file_manager.copy_folder(target, source, destination)
		elif command == "move":
			from octoprint.server.api.files import _isBusy
			if _isBusy(target, source):
				return "You can't move a file while it is in use"

			# deselect the file if it's currently selected
			from octoprint.server.api.files import _getCurrentFile
			currentOrigin, currentFilename = _getCurrentFile()
			if currentFilename is not None and source == currentFilename:
				self.main._printer.unselect_file()

			if self.main._file_manager.file_exists(target, source):
				self.main._file_manager.move_file(target, source, destination)
			elif self.main._file_manager.folder_exists(target, source):
				self.main._file_manager.move_folder(target, source, destination)
		return "GOOD"
### From filemanager plugin - https://github.com/Salandora/OctoPrint-FileManager/blob/master/octoprint_filemanager/__init__.py
############################################################################################
	def fileDelete(self, target, source):
		from octoprint.server.api.files import _verifyFolderExists, _verifyFileExists, _isBusy

		# prohibit deleting or moving files that are currently in use
		from octoprint.server.api.files import _getCurrentFile
		currentOrigin, currentFilename = _getCurrentFile()

		if _verifyFileExists(target, source):
			from octoprint.server.api.files import _isBusy
			if _isBusy(target, source):
				return "Trying to delete a file that is currently in use"

			# deselect the file if it's currently selected
			if currentFilename is not None and source == currentFilename:
				self.main._printer.unselect_file()

			# delete it
			if target == octoprint.filemanager.FileDestinations.SDCARD:
				self.main._printer.delete_sd_file(source)
			else:
				self.main._file_manager.remove_file(target, source)
		elif _verifyFolderExists(target, source):
			if not target in [octoprint.filemanager.FileDestinations.LOCAL]:
				return "Unknown target"

			folderpath = source
			if _isBusy(target, folderpath):
				return "Trying to delete a folder that contains a file that is currently in use"

			# deselect the file if it's currently selected
			if currentFilename is not None and self._file_manager.file_in_path(target, folderpath, currentFilename):
				self.main._printer.unselect_file()

			# delete it
			self.main._file_manager.remove_folder(target, folderpath)
		return "GOOD"
############################################################################################
	def generate_dir_hash_dict(self):
		try:
			self.dirHashDict = {}
			tree = self.main._file_manager.list_files(recursive=True)
			for key in tree:
				self.dirHashDict.update({str(self.hashMe(key+"/",8)):key+"/"})
				self.dirHashDict.update(self.generate_dir_hash_dict_recursively(tree[key],key+"/"))
			self._logger.debug(str(self.dirHashDict))
		except Exception as ex:
			self._logger.error("An Exception in generate_dir_hash_dict : " + str(ex) )
############################################################################################
	def generate_dir_hash_dict_recursively(self,tree,loc):
		try:
			myDict = {}
			for key in tree:
				if tree[key]['type']=="folder":
					myDict.update({self.hashMe(loc+key+"/",8):loc+key+"/"})
					self.dirHashDict.update(self.generate_dir_hash_dict_recursively(tree[key]['children'],loc+key+"/"))
		except Exception as ex:
			self._logger.error("An Exception in generate_dir_hash_dict_recursively : " + str(ex) )
		return myDict
############################################################################################
	def find_file_by_hash(self, hash):
		try:
			tree = self.main._file_manager.list_files(recursive=True)
			for key in tree:
				result,file = self.find_file_by_hash_recursively(tree[key], hash)
				if result is not None:
					return key, result, file
		except Exception as ex:
			self._logger.error("An Exception in find_file_by_hash : " + str(ex) )
		return None, None, None
############################################################################################
	def find_file_by_hash_recursively(self, tree, hash, base=""):
		for key in tree:
			if tree[key]['type']=="folder":
				result, file = self.find_file_by_hash_recursively(tree[key]['children'], hash, base=base+key+"/")
				if result is not None:
					return result, file
				continue
			if self.hashMe(base+tree[key]['name']).startswith(hash):
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
			try:
				if type(key) is type({}):
					keyName =  str(key['name']) if 'name' in key else ""
					if base == "":
						first = " "+keyName
					if 'children' in key:
						array.extend(self.get_controls_recursively(key['children'], base + " " + keyName,first))
					elif ('commands' in key or 'command' in key or 'script' in key) and not 'regex' in key and not 'input' in key:
						newKey = {}
						if 'script' in key:
							newKey['script'] = True
							command =  key['script']
						else:
							command =  key['command'] if 'command' in key else key['commands']
						newKey['name'] = base.replace(first,"") + " " + keyName
						newKey['hash'] = self.hashMe(base + " " + keyName + str(command), 6)
						newKey['command'] = command
						if 'confirm' in key:
							newKey['confirm'] = key['confirm']
						array.append(newKey)
			except Exception as ex:
				self._logger.error("An Exception in get key from tree : " + str(ex) )
		return array
############################################################################################
	def hashMe(self, text, length = 32):
		try:
			return hashlib.md5(text.encode()).hexdigest()[0:length]
		except Exception as ex:
			self._logger.error("An Exception in hashMe : " + str(ex) )
			return ""
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
				self.ConAuto(chat_id,parameter[1:])
		else:
			con = octoprint.printer.get_connection_options()
			profile = self.main._printer_profile_manager.get_default()
			msg = self.gEmo('settings') + " Default connection settings \n\n"
			msg += "*Port:* "+ str(con['portPreference'])
			msg += "\n*Baud:* "+ (str(con['baudratePreference']) if con['baudratePreference'] else "AUTO")
			msg += "\n*Profil:* "+ str(profile['name'])
			msg += "\n*AutoConnect:* "+ str(con['autoconnect'])
			self.main.send_msg(msg,responses=[[[self.main.emojis['electric plug']+gettext(" Port"),"/con_s|p"],[self.main.emojis['high voltage sign']+gettext(" Baud"),"/con_s|b"],[self.main.emojis['bust in silhouette']+gettext(" Profile"),"/con_s|pr"], [self.main.emojis['lamp']+gettext(" Auto"),"/con_s|a"]], [[self.main.emojis['leftwards arrow with hook']+gettext(" Back"),"/con_back"]]],chatID=chat_id,markup="Markdown",msg_id=self.main.getUpdateMsgId(chat_id))
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
			tmpKeys = [[self.main.emojis['lamp']+' AUTO','/con_'+parent+'|p|AUTO']]
			i = 2
			for k in con['ports']:
				tmpKeys.append([self.main.emojis['electric plug']+" "+str(k),"/con_"+parent+"|p|"+str(k)])
				if i%3 == 0:
					keys.append(tmpKeys)
					tmpKeys = []
				i += 1
			if len(tmpKeys) > 0 and len(tmpKeys) < 3:
				keys.append(tmpKeys)
			keys.append([[self.main.emojis['leftwards arrow with hook']+gettext(" Back"),"/con_"+parent]])
			self.main.send_msg(self.gEmo('question') + " Select default port.\nCurrent setting: "+(str(con['portPreference']) if con['portPreference'] else "AUTO"),responses=keys,chatID=chat_id,msg_id=self.main.getUpdateMsgId(chat_id))
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
			tmpKeys = [[self.main.emojis['lamp']+' AUTO','/con_'+parent+'|b|0']]
			i = 2
			for k in con['baudrates']:
				tmpKeys.append([self.main.emojis['high voltage sign']+" "+str(k),"/con_"+parent+"|b|"+str(k)])
				if i%3 == 0:
					keys.append(tmpKeys)
					tmpKeys = []
				i += 1
			if len(tmpKeys) > 0 and len(tmpKeys) < 3:
				keys.append(tmpKeys)
			keys.append([[self.main.emojis['leftwards arrow with hook']+gettext(" Back"),"/con_"+parent]])
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
				tmpKeys.append([self.main.emojis['bust in silhouette']+" "+str(con[k]['name']),"/con_"+parent+"|pr|"+str(con[k]['id'])])
				if i%3 == 0:
					keys.append(tmpKeys)
					tmpKeys = []
				i += 1
			if len(tmpKeys) > 0 and len(tmpKeys) < 3:
				keys.append(tmpKeys)
			keys.append([[self.main.emojis['leftwards arrow with hook']+gettext(" Back"),"/con_"+parent]])
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
			keys=[[[self.main.emojis['check']+" ON","/con_s|a|true"],[self.main.emojis['error']+" OFF","/con_s|a|false"]],[[self.main.emojis['leftwards arrow with hook']+gettext(" Back"),"/con_s"]]]
			self.main.send_msg(self.gEmo('question') + " AutoConnect on startup.\nCurrent setting: "+str(con['autoconnect']),responses=keys,chatID=chat_id,msg_id=self.main.getUpdateMsgId(chat_id))
############################################################################################
	def ConConnect(self,chat_id,parameter):
		if parameter:
			if parameter[0] == "a":
					self.conSettingsTemp.extend([None,None,None])
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
			waitStates=["Offline","Detecting baudrate","Connecting","Opening serial port","Detecting serial port"]
			while any(s in con[0] for s in waitStates):
				con = self.main._printer.get_current_connection()
			self._logger.debug("EXIT WITH: "+str(con[0]))

			if con[0] == "Operational":
				self.main.send_msg(self.gEmo('check') + " Connection established.",chatID=chat_id, msg_id = self.main.getUpdateMsgId(chat_id))
			else:
				self.main.send_msg(self.gEmo('warning') + " Failed to start connection.\n\n"+con[0],chatID=chat_id, msg_id = self.main.getUpdateMsgId(chat_id))
		else:
			keys=[[[self.main.emojis['lamp']+" AUTO","/con_c|a"],[self.main.emojis['high voltage sign']+" Default","/con_c|d"]],[[self.main.emojis['settings']+" Manual","/con_c|p"],[self.main.emojis['leftwards arrow with hook']+" Back","/con_back"]]]
			self.main.send_msg(self.gEmo('question') + " Select connection option.",chatID=chat_id,responses=keys, msg_id = self.main.getUpdateMsgId(chat_id))
############################################################################################
	def ConDisconnect(self,chat_id):
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
		for i in range(0, len(units)):
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
