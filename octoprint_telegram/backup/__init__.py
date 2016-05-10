from __future__ import absolute_import
from PIL import Image
import threading, requests, re, time, datetime, StringIO, json, random, logging, traceback, io, collections, os, flask,base64,PIL
import octoprint.plugin, octoprint.util, octoprint.filemanager
from flask.ext.babel import gettext

class TelegramListener(threading.Thread):
	def __init__(self, main):
		threading.Thread.__init__(self)
		self.update_offset = 0
		self.first_contact = True
		self.main = main
		self.do_stop = False
		self.username = "UNKNOWN"
		self._logger = main._logger.getChild("listener")
		self.gEmo = self.main.gEmo

		self.commandDict = {
			gettext("Yes"): {'cmd': self.cmdYes, 'bind_none': True},
			gettext("Cancel"): {'cmd': self.cmdNo, 'bind_none': True},
			gettext("No"):  {'cmd': self.cmdNo,'bind_none': True},
			gettext("Change height"):  {'cmd': self.cmdChgHeight, 'bind_cmd': '/settings'},
			self.gEmo('enter') + gettext(" Enter height"):  {'cmd': self.cmdSetHeight, 'bind_cmd': '/settings'},
			gettext("Change time"):  {'cmd': self.cmdChgTime, 'bind_cmd': '/settings'},
			self.gEmo('enter') + gettext(" Enter time"):  {'cmd': self.cmdSetTime, 'bind_cmd': '/settings'},
			gettext("Start print"):  {'cmd': self.cmdStartPrint, 'bind_cmd': '/print'},
			gettext("Stop print"):  {'cmd': self.cmdHalt, 'bind_cmd': '/print'},
			'/print_':  {'cmd': self.cmdRunPrint, 'bind_cmd': '/print'},
			'/test':  {'cmd': self.cmdTest},
			'/status':  {'cmd': self.cmdStatus},
			'/abort':  {'cmd': self.cmdAbort},
			'/settings':  {'cmd': self.cmdSettings},
			'/shutup':  {'cmd': self.cmdShutup},
			'/imsorrydontshutup':  {'cmd': self.cmdNShutup},
			'/list':  {'cmd': self.cmdList},
			'/print':  {'cmd': self.cmdPrint},
			'/light':  {'cmd': self.cmdLight},
			'/upload':  {'cmd': self.cmdUpload},
			'/darkness':  {'cmd': self.cmdDarkness},
			'/help':  {'cmd': self.cmdHelp}
		}


	def cmdYes(self,chat_id,**kwargs):
		self.main.send_msg(gettext("Alright."),chatID=chat_id)

	def cmdNo(self,chat_id,**kwargs):
		self.main.send_msg(gettext("Maybe next time."),chatID=chat_id)

	def cmdTest(self,chat_id,**kwargs):
		self.main.track_action("command/test")
		self.main.send_msg(self.gEmo('question') + gettext(" Is this a test?\n\n") , responses=[gettext("Yes"), gettext("No")],chatID=chat_id)

	def cmdStatus(self,chat_id,**kwargs):
		self.main.track_action("command/status")
		if not self.main._printer.is_operational():
			self.main.send_msg(self.gEmo('warning') + gettext(" Not connected to a printer."),chatID=chat_id)
		elif self.main._printer.is_printing():
			status = self.main._printer.get_current_data()
			self.main.on_event("StatusPrinting", {'z': (status['currentZ'] or 0.0)},chatID=chat_id)
		else:
			self.main.on_event("StatusNotPrinting", {},chatID=chat_id)

	def cmdSettings(self,chat_id,**kwargs):
		self.main.track_action("command/settings")
		msg = self.gEmo('settings') + gettext(" Current notification settings are:\n\n\n"+self.gEmo('height')+" height: %(height)fmm\n\n"+self.gEmo('clock')+" time: %(time)dmin\n\n\n"+self.gEmo('question')+"Which value do you want to change?",
			height=self.main._settings.get_float(["notification_height"]),
			time=self.main._settings.get_int(["notification_time"]))
		self.main.send_msg(msg, responses=[gettext("Change height"), gettext("Change time"), gettext("Cancel")],chatID=chat_id)

	def cmdChgHeight(self,chat_id,**kwargs):
		self.main.send_msg(self.gEmo('enter') + gettext(" Enter height"), force_reply=True,chatID=chat_id)

	def cmdSetHeight(self,chat_id,parameter,**kwargs): 
		self.main._settings.set_float(['notification_height'], parameter, force=True)
		self.main.send_msg(self.gEmo('height') + gettext(" Notification height is now %(height)fmm.", height=self.main._settings.get_float(['notification_height'])),chatID=chat_id)

	def cmdChgTime(self,chat_id,**kwargs):
		self.main.send_msg(self.gEmo('enter') + gettext(" Enter time"), force_reply=True,chatID=chat_id)

	def cmdSetTime(self,chat_id,parameter,**kwargs):
		self.main._settings.set_int(['notification_time'], parameter, force=True)
		self.main.send_msg(self.gEmo('clock') + gettext(" Notification time is now %(time)dmins.", time=self.main._settings.get_int(['notification_time'])),chatID=chat_id)

	def cmdAbort(self,chat_id,**kwargs):
		self.main.track_action("command/abort")
		if self.main._printer.is_printing():
			self.main.send_msg(self.gEmo('question') + gettext(" Really abort the currently running print?"), responses=[gettext("Stop print"), gettext("Cancel")],chatID=chat_id)
		else:
			self.main.send_msg(self.gEmo('warning') + gettext(" Currently I'm not printing, so there is nothing to stop."),chatID=chat_id)

	def cmdHalt(self,chat_id,**kwargs):
		self.main.send_msg(self.gEmo('info') + gettext(" Aborting the print."),chatID=chat_id)
		self.main._printer.cancel_print()
							
	def cmdShutup(self,chat_id,**kwargs):
		self.main.track_action("command/shutup")
		self.main.shut_up = True
		self.main.send_msg(self.gEmo('noNotify') + gettext(" Okay, shutting up until the next print is finished." + self.gEmo('shutup')+" Use /imsorrydontshutup to let me talk again before that. "),chatID=chat_id)

	def cmdNShutup(self,chat_id,**kwargs):
		self.main.track_action("command/imsorrydontshutup")
		self.main.shut_up = False
		self.main.send_msg(self.gEmo('notify') + gettext(" Yay, I can talk again."),chatID=chat_id)

	def cmdPrint(self,chat_id,**kwargs):
		self.main.send_msg(self.gEmo('info') + " Use /list to get a list of files and click the command beginning with /print after the correct file.",chatID=chat_id)

	def cmdRunPrint(self,chat_id,parameter,**kwargs):
		self.main.track_action("command/print")
		self._logger.debug("Looking for hash: %s", parameter)
		destination, file = self.find_file_by_hash(parameter)
		self._logger.debug("Destination: %s", destination)
		self._logger.debug("File: %s", file)
		if file is None or parameter is None or parameter is "":
			self.main.send_msg(self.gEmo('warning') + " I'm sorry, but I couldn't find the file you wanted me to print. Perhaps you want to have a look at /list again?",chatID=chat_id)
			return
		self._logger.debug("data: %s", self.main._printer.get_current_data())
		self._logger.debug("state: %s", self.main._printer.get_current_job())
		if destination==octoprint.filemanager.FileDestinations.SDCARD:
			self.main._printer.select_file(file, True, printAfterSelect=False)
		else:
			file = self.main._file_manager.path_on_disk(octoprint.filemanager.FileDestinations.LOCAL, file)
			self._logger.debug("Using full path: %s", file)
			self.main._printer.select_file(file, False, printAfterSelect=False)
		data = self.main._printer.get_current_data()
		if data['job']['file']['name'] is not None:
			self.main.send_msg(self.gEmo('info') + gettext(" Okay. The file %(file)s is loaded.\n\n"+self.gEmo('question')+" Do you want me to start printing it now?", file=data['job']['file']['name']), responses=[gettext("Start print"), gettext("No")],chatID=chat_id)

	def cmdStartPrint(self,chat_id,**kwargs):
		data = self.main._printer.get_current_data()
		if data['job']['file']['name'] is None:
			self.main.send_msg(self.gEmo('warning') + gettext(" Uh oh... No file is selected for printing. Did you select one using /list?"),chatID=chat_id)
			return
		if not self.main._printer.is_operational():
			self.main.send_msg(self.gEmo('warning') + gettext(" Can't start printing: I'm not connected to a printer."),chatID=chat_id)
			return
		if self.main._printer.is_printing():
			self.main.send_msg(self.gEmo('warning') + " A print job is already running. You can't print two thing at the same time. Maybe you want to use /abort?",chatID=chat_id)
			return
		self.main._printer.start_print()
		self.main.send_msg(self.gEmo('rocket') + gettext(" Started the print job."),chatID=chat_id)

	def cmdList(self,chat_id,**kwargs):
		self.main.track_action("command/list")
		files = self.get_flat_file_tree()
		self.main.send_msg(self.gEmo('save') + " File List:\n\n" + "\n".join(files) + "\n\n"+self.gEmo('info')+" You can click the command beginning with /print after a file to start printing this file.",chatID=chat_id)

	def cmdLight(self,chat_id,**kwargs):
		self.main._printer.commands("M42 P47 S255")
		self.main.send_msg("I put the lights on.",chatID=chat_id)

	def cmdDarkness(self,chat_id,**kwargs):
		self.main._printer.commands("M42 P47 S0")
		self.main.send_msg("Lights are off now.",chatID=chat_id)

	def cmdUpload(self,chat_id,**kwargs):
		self.main.track_action("command/upload_command_that_tells_the_user_to_just_send_a_file")
		self.main.send_msg(self.gEmo('info') + " To upload a gcode file, just send it to me.",chatID=chat_id)

	def cmdHelp(self,chat_id,**kwargs):
		self.main.track_action("command/help")
		self.main.send_msg(self.gEmo('info') + gettext(" You can use following commands:\n"
		                           "/abort - Aborts the currently running print. A confirmation is required.\n"
		                           "/shutup - Disables automatic notifications till the next print ends.\n"
		                           "/imsorrydontshutup - The opposite of /shutup - Makes the bot talk again.\n"
		                           "/status - Sends the current status including a current photo.\n"
		                           "/settings - Displays the current notification settings and allows you to change them."),chatID=chat_id)

	def newChat(self):
		return {'accept_commands' : False, 
				'send_notifications' : False, 
				'new': True, 
				'allow_users': False,
				'commands': {k: False for k,v in self.commandDict.iteritems()}, 
				'notifications': {k: False for k,v in self.main.msgDict.iteritems()}
				}
		

	def run(self):
		self._logger.debug("Listener is running.")
		try:
			self.username = self.main.test_token()
		except Exception as ex:
			self.set_status(gettext("Got an exception while initially trying to connect to telegram: %(ex)s", ex=ex))
			return
		self.set_status(gettext("Connected as %(username)s.", username=self.username), ok=True)
		
		while not self.do_stop:
			self._logger.debug("listener: sending request with offset " + str(self.update_offset) + "...")
			req = None
			iAmNew = False
			chat_id = ""
			try:
				timeout = '30'
				if self.update_offset == 0 and self.first_contact:
					timeout = '0'
					self.update_offset = 1
				req = requests.get(self.main.bot_url + "/getUpdates", params={'offset':self.update_offset, 'timeout':timeout}, allow_redirects=False)
			except Exception as ex:
				self.set_status(gettext("Got an exception while trying to connect to telegram API: %(exception)s. Waiting 2 minutes before trying again.", exception=ex))
				time.sleep(120)
				continue
			if req.status_code != 200:
				self.set_status(gettext("Telegram API responded with code %(status_code)s. Waiting 2 minutes before trying again.", status_code=req.status_code))
				time.sleep(120)
				continue
			if req.headers['content-type'] != 'application/json':
				self.set_status(gettext("Unexpected Content-Type. Expected: application/json. Was: %(type)s. Waiting 2 minutes before trying again.", type=req.headers['content-type']))
				time.sleep(120)
				continue
			json = req.json()
			if not json['ok']:
				self.set_status(gettext("Response didn't include 'ok:true'. Waiting 2 minutes before trying again. Response was: %(response)s", json))
				time.sleep(120)
				continue
			try:
				for message in json['result']:
					self._logger.debug("MESSAGE: " + str(message))
					# Get the update_id to only request newer Messages the next time
					if message['update_id'] >= self.update_offset:
						self.update_offset = message['update_id']+1
					
					if not message['message'] or not message['message']['chat']:
						self._logger.warn("Response is missing .message or .message.chat. Skipping it.")
						continue
					
					### Parse new chats
					self.main.chats = self.main._settings.get(["chats"])
					chat = message['message']['chat']
					chat_id = str(chat['id'])
					data = self.newChat()
					self._logger.debug("NEW USER: " + str(data))
					iAmNew = False
					if chat_id in self.main.chats:
						data = self.main.chats[chat_id]
					else:
						self.main.chats[chat_id] = data
						iAmNew = True
					
					if chat['type']=='group':
						data['private'] = False
						data['title'] = chat['title']
					elif chat['type']=='private':
						data['private'] = True
						data['title'] = ""
						if "first_name" in chat:
							data['title'] += chat['first_name'] + " - "
						if "last_name" in chat:
							data['title'] += chat['last_name'] + " - "
						if "username" in chat:
							data['title'] += "@" + chat['username']
						
					if self.first_contact:
						self._logger.debug("Ignoring message because first_contact is True.")
						continue
					elif iAmNew:
						self.main.send_msg(self.gEmo('info') + "Now i know you. Before you can do anything, go to OctoPrint Settings and edit some rignts.",chatID=chat_id)
						self.main.get_usrPic(chat_id)
						continue

					
					if "text" in message['message']:
						# We got a chat message.
						# handle special messages
						command = str(message['message']['text'].split('@')[0])
						parameter = None
						if "reply_to_message" in message['message'] and "text" in message['message']['reply_to_message']:
							command = message['message']['reply_to_message']['text']
							parameter = message['message']['text']
						elif "/print_" in command:
							parameter = command.split('_')[1]
							command = command.split('_')[0] + "_"
							
						
						self._logger.info("Got a command: '" + command + "' with parameter: '" + str(parameter) + "' in chat " + str(message['message']['chat']['id']))

						#if message from group, user allowed?
						allowed = True
						unknownCMD = False
						from_id = chat_id
						if not data['private'] and data['accept_commands']:
							from_id = str(message['message']['from']['id'])
						elif not data['private'] and not data['accept_commands']:
							allowed = False;

						if allowed:
							allowed = False;
							if command.startswith("/") and command in self.commandDict:
								if self.main.chats[from_id]['commands'][command]:
									allowed = True
							elif parameter != None:
								if parameter.startswith("/") and parameter in self.commandDict:
									if self.main.chats[from_id]['commands'][parameter]:
										allowed = True
								else:
									allowed = True
							else:
								if (
									command == "Start print" or parameter == "Start print" 
									or command == "Stop print" or parameter == "Stop print"
									):
									if self.main.chats[from_id]['commands']["/print"]:
										allowed = True
								elif (
									command == "Change height" or parameter == "Change height" 
									or command == "Change time" or parameter == "Change time"
									or command == self.gEmo('enter') + "Enter height" or parameter == self.gEmo('enter') + "Enter height" 
									or command == self.gEmo('enter') + "Enter time" or parameter == self.gEmo('enter') + "Enter time"
									):
									if self.main.chats[from_id]['commands']["/settings"]:
										allowed = True
								else:
									allowed = True


						if from_id in self.main.chats:
							if self.main.chats[from_id]['accept_commands'] and allowed:
								self.main.messageResponseID = message['message']['message_id']
								if command in self.commandDict :
									self.commandDict[command]['cmd'](chat_id=chat_id,parameter=parameter)
								elif parameter in self.commandDict:
									self.commandDict[parameter]['cmd'](chat_id=chat_id,parameter=command)
								self.main.messageResponseID = None
							else:
								self._logger.warn("Previous command was from an unauthorized user.")
								self.main.send_msg("You are not allowed to do this! " + self.gEmo('notallowed'),chatID=chat_id)
						else:
							self._logger.warn("Previous command was from an unknown user.")
							self.main.send_msg("I don't know you! Certainly you are a nice Person " + self.gEmo('heart'),chatID=chat_id)
					elif "document" in message['message']:
						from_id = chat_id
						if not data['private'] and data['accept_commands']: #is this needed? can one send files from groups to bots?
							from_id = str(message['message']['from']['id'])

						if self.main.chats[from_id]['accept_commands'] and self.main.chats[from_id]['private']:
							if self.main.chats[from_id]['commands']['/upload']:
								self.main.track_action("command/upload")
								try:
									file_name = message['message']['document']['file_name']
									if not (file_name.lower().endswith('.gcode') or file_name.lower().endswith('.gco') or file_name.lower().endswith('.g')):
										self.main.send_msg(self.gEmo('warning') + " Sorry, I only accept files with .gcode, .gco or .g extension.", chatID=chat_id)
										continue
									# download the file
									target_filename = "telegram_" + file_name
									self.main.send_msg(self.gEmo('save') + gettext(" Saving file {}...".format(target_filename)), chatID=chat_id, noMarkup=True)
									data = self.main.get_file(message['message']['document']['file_id'])
									stream = octoprint.filemanager.util.StreamWrapper(file_name, io.BytesIO(data))
									self.main._file_manager.add_file(octoprint.filemanager.FileDestinations.LOCAL, target_filename, stream, allow_overwrite=True)
									self.main.send_msg(self.gEmo('upload') + " I've successfully saved the file you sent me as {}.".format(target_filename),msg_id=self.getUpdateMsgId(chat_id),chatID=chat_id)
								except Exception as ex:
									self.main.send_msg(self.gEmo('warning') + " Something went wrong during processing of your file."+self.gEmo('mistake')+" Sorry. More details are in octoprint.log.",msg_id=self.getUpdateMsgId(chat_id),chatID=chat_id)
									self._logger.debug("Exception occured during processing of a file: "+ traceback.format_exc() )
							else:
								self._logger.warn("Previous file was from an unauthorized user.")
								self.main.send_msg("Don't feed the octopuses! " + self.gEmo('octo'),chatID=chat_id)
						else:
							self._logger.warn("Previous file was from an unauthorized user.")
							self.main.send_msg("Don't feed the octopuses! " + self.gEmo('octo'),chatID=chat_id)
					elif "new_chat_photo" in message['message']:
						self._logger.debug("Message New_Chat_Photo")
						if message['message']['chat']['id'] in self.main.chats:
							self.main.getPic(message['message']['chat']['id'],message['message']['new_chat_photo'][0][0]['file_id'])
					# WILL BE DONE ON TOP ON FIRST MESSAGE HANDLE LINES
					# elif "new_chat_title" in message['message']:
					# 	self._logger.debug("Message New_Chat_Title")
					# 	if message['message']['chat']['id'] in self.main.chats:
					# 		self.main.chats[message['message']['chat']['id']]['title'] = message['message']['new_hat_title']
					elif "delete_chat_photo" in message['message']:
						self._logger.debug("Message Del_Chat_Photo")
						if message['message']['chat']['id'] in self.main.chats:
							try:
								os.remove(self.main.get_plugin_data_folder()+"/pic" +message['message']['chat']['id']+".jpg")
								elf._logger.debug("File removed")

							except OSError:
								pass
					elif "left_chat_member" in message['message]']:
						self._logger.debug("Message Del_Chat")
						if message['message']['new_chat_member']['username'] == self.username[1:] and message['message']['chat']['id'] in self.main.chats:
							del self.main.chats[message['message']['chat']['id']]
							self._logger.debug("Chat deleted")
					# WILL BE DONE ON TOP ON FIRST MESSAGE HANDLE LINES
					# elif "new_chat_member" in message['message']:
					# 	self._logger.debug("Message New_Chat_Member")
					# 	if message['message']['new_chat_member']['username'] == self.username[1:] and message['message']['chat']['id'] not in self.main.chats:
					# 		data = self.newChat()
					# 		data['private'] = False
					# 		data['title'] = message['message']['chat']['title']
					# 		self.main.chats[message['message']['chat']['id']] = data
					else:
						self._logger.warn("Got an unknown message. Doing nothing. Data: " + str(message))
			except Exception as ex:
				self._logger.error("Exception caught! " + str(ex))
			
			self.set_status(gettext("Connected as %(username)s.", username=self.username), ok=True)
				
			if self.first_contact:
				self.first_contact = False
				if self.main._settings.get_boolean(["message_at_startup"]):
					self.main.on_event("PrinterStart",{})
				if iAmNew:
					self.main.send_msg(self.gEmo('info') + "Now i know you. Before you can do anything, go to OctoPrint Settings and edit some rignts.",chatID=json['result']['message']['chat']['id'])
					self.main.get_usrPic(chat_id)
		self._logger.debug("Listener exits NOW.")
	
	def getUpdateMsgId(self,id):
		uMsgID = None
		if id in self.main.updateMessageID:
			uMsgID = self.main.updateMessageID[id]
			del self.main.updateMessageID[id]
		return uMsgID

	def stop(self):
		self.do_stop = True
	
	def set_status(self, status, ok=False):
		if status != self.main.connection_state_str:
			if self.do_stop:
				self._logger.debug("Would set status but do_stop is True: %s", status)
				return
			if ok:
				self._logger.debug("Setting status: %s", status)
			else:
				self._logger.error("Setting status: %s", status)
		self.connection_ok = ok
		self.main.connection_state_str = status

	def get_flat_file_tree(self):
		tree = self.main._file_manager.list_files(recursive=True)
		array = []
		for key in tree:
			array.append(key + ":")
			array.extend(sorted(self.flatten_file_tree_recursively(tree[key])))
		return array
			
	def flatten_file_tree_recursively(self, tree, base=""):
		array = []
		for key in tree:
			if tree[key]['type']=="folder":
				array.extend(self.flatten_file_tree_recursively(tree[key]['children'], base=base+key+"/"))
			elif tree[key]['type']=="machinecode":
				array.append(base+key + " - /print_" + tree[key]['hash'][0:8])
			else:
				array.append(base+key)
		return array
	
	def find_file_by_hash(self, hash):
		tree = self.main._file_manager.list_files(recursive=True)
		for key in tree:
			result = self.find_file_by_hash_recursively(tree[key], hash)
			if result is not None:
				return key, result
		return None, None
	
	def find_file_by_hash_recursively(self, tree, hash, base=""):
		for key in tree:
			if tree[key]['type']=="folder":
				result = self.find_file_by_hash_recursively(tree[key]['children'], hash, base=base+key+"/")
				if result is not None:
					return result
				continue
			if tree[key]['hash'].startswith(hash):
				return base+key
		return None

class TelegramPluginLoggingFilter(logging.Filter):
	def filter(self, record):
		for match in re.findall("[0-9]+:[a-zA-Z0-9_\-]+", record.msg):
			new = re.sub("[0-9]", "1", re.sub("[a-z]", "a", re.sub("[A-Z]", "A", match)))
			record.msg = record.msg.replace(match, new)
		return True

class TelegramPlugin(octoprint.plugin.EventHandlerPlugin,
                     octoprint.plugin.SettingsPlugin,
                     octoprint.plugin.StartupPlugin,
                     octoprint.plugin.ShutdownPlugin,
                     octoprint.plugin.TemplatePlugin,
                     octoprint.plugin.SimpleApiPlugin,
                     octoprint.plugin.AssetPlugin
                     ):

	def __init__(self):
		self.thread = None
		self.last_z = 0.0
		self.last_notification_time = 0
		self.bot_url = None
		self.chats = {}
		self.shut_up = False
		self.connection_state_str = gettext("Disconnected.")
		self.connection_ok = False
		self.messageResponseID = None
		requests.packages.urllib3.disable_warnings()
		self.updateMessageID = {}
		self.emojis = {
			'octo': 	u'\U0001F419', #octopus
			'mistake': 	u'\U0001F616',
			'notify': u'\U0001F514',
			'shutdown' : u'\U0001F4A4',
			'shutup':	 u'\U0001F64A',
			'noNotify': u'\U0001F515',
			'notallowed': u'\U0001F62C',
			'rocket': u'\U0001F680',
			'save': u'\U0001F4BE',
			'heart': u'\U00002764',
			'info': u'\U00002139',
			'settings': u'\U0001F4DD',
			'clock': u'\U000023F0',
			'height': u'\U00002B06',
			'question': u'\U00002753',
			'warning': u'\U000026A0',
			'enter': u'\U0000270F',
			'upload': u'\U0001F4E5'
		}
		self.msgDict = {
				'PrinterStart': {
					'text': "{emo[rocket]} " + gettext("Hello. I'm online and ready to receive your commands."),
					'image': False
					},
				'PrinterShutdown': {
					'text': "{emo[octo]} {emo[shutdown]} " + gettext("Shutting down. Goodbye."),
					'image': False
					},
				'PrintStarted': {
					'text': gettext("Started printing {file}."),
					'image': True
					},
				'PrintFailed': {
					'text': gettext("Printing {file} failed."),
					'image': True
					},
				'ZChange': {
					'text': gettext("Printing at Z={z}.\nBed {bed_temp}/{bed_target}, Extruder {e1_temp}/{e1_target}.\n{time_done}, {percent}%% done, {time_left} remaining."),
					'image': True
					},
				'PrintDone': {
					'text': gettext("Finished printing {file}."),
					'image': True
					},
				'StatusNotPrinting': {
					'text': gettext("Not printing.\nBed {bed_temp}/{bed_target}, Extruder {e1_temp}/{e1_target}."),
					'image': True
					},
				'StatusPrinting': {
					'bind_msg': 'ZChange'
					},
				}

	def gEmo(self,key):
		if self._settings.get(["send_icon"]):
			if key in self.emojis:
				return self.emojis[key]
		return ""

	def start_listening(self):
		if self._settings.get(['token']) != "" and self.thread is None:
			self._logger.debug("Starting listener.")
			self.bot_url = "https://api.telegram.org/bot" + self._settings.get(['token'])
			self.bot_file_url = "https://api.telegram.org/file/bot" + self._settings.get(['token'])
			self.thread = TelegramListener(self)
			self.thread.daemon = True
			self.thread.start()
	
	def stop_listening(self):
		if self.thread is not None:
			self._logger.debug("Stopping listener.")
			self.thread.stop()
			self.thread = None
	
	def on_after_startup(self):
		self.set_log_level()
		self._logger.addFilter(TelegramPluginLoggingFilter())
		
		self.start_listening()
		self.track_action("started")
		self.chats = self._settings.get(["chats"])
		for f in os.listdir(self.get_plugin_data_folder()):
			fcut = f.split('.')[0][3:]
			self._logger.debug("Testing Pic ID " + str(fcut))
			if fcut not in self.chats:
				self._logger.debug("Removing pic" +fcut+".jpg")
				try:
					os.remove(self.get_plugin_data_folder()+"/pic" +fcut+".jpg")
				except OSError:
					pass
		for key in self.chats:
			try:
				kwargs = {}
				kwargs['chat_id'] = int(key)
				threading.Thread(target=self.get_usrPic, kwargs=kwargs).run()
			except Exception:
				pass
	
	def on_shutdown(self):
		if self._settings.get_boolean(["message_at_shutdown"]):
			self.main.on_event("PrinterShutdown",{})
	
	def set_log_level(self):
		self._logger.setLevel(logging.DEBUG if self._settings.get_boolean(["debug"]) else logging.NOTSET)
	
	def get_settings_preprocessors(self):
		return dict(), dict(
			notification_height=lambda x: float(x),
			notification_time=lambda x: int(x)
		)
	
	def on_settings_save(self, data):
		#remove chats deleted by user
		self._logger.debug("Chats: " + str(self.chats))
		self._logger.debug("Data: " + str(data))
		delList = []
		for key in data['chats']:
			if 'new' in data['chats'][key] or 'new' in data['chats'][key]:
				data['chats'][key]['new'] = False
			if not key == "zBOTTOMOFCHATS":
				for cmd in self.thread.commandDict:
					if 'bind_cmd' in self.thread.commandDict[cmd]:
						data['chats'][key]['commands'][cmd] = data['chats'][key]['commands'][self.thread.commandDict[cmd]['bind_cmd']]
					if 'bind_none' in self.thread.commandDict[cmd]:
						data['chats'][key]['commands'][cmd] = True
			if not key in self.chats and not key == "zBOTTOMOFCHATS":
				delList.append(key)
		for key in delList:
			del data['chats'][key]
			
		for key in self.chats:
			if 'new' in self.chats[key]:
				self._logger.debug("FOUND NEW in " + str(key))
				self.chats[key]['new'] = False
			if not key in data['chats']: #really needed?????
				self._logger.debug("FOUND CHAT in " + str(key))
				data['chats'][key].update(self.chats[key])

		self._logger.debug("Saving data: " + str(data))

		data['token'] = data['token'].strip()
		if not re.match("^[0-9]+:[a-zA-Z0-9_\-]+$", data['token']):
			self._logger.error("Not saving token because it doesn't seem to have the right format.")
			self.connection_state_str = gettext("The previously entered token doesn't seem to have the correct format. It should look like this: 12345678:AbCdEfGhIjKlMnOpZhGtDsrgkjkZTCHJKkzvjhb")
			data['token'] = ""
		old_token = self._settings.get(["token"])
		if not data['tracking_activated']:
			data['tracking_token'] = None
		octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
		self.set_log_level()
		if data['token']!=old_token:
			self.stop_listening()
		if data['token']!="":
			self.start_listening()
		else:
			self.connection_state_str = gettext("No token given.")
	
	def get_settings_defaults(self):
		return dict(
			token = "",
			notification_height = 5.0,
			notification_time = 15,
			message_at_startup = True,
			message_at_shutdown = True,
			message_at_print_started = True,
			message_at_print_done = True,
			message_at_print_done_delay = 0,
			message_at_print_failed = True,
			messages = self.msgDict,
			tracking_activated = False,
			tracking_token = None,
			chats = {'zBOTTOMOFCHATS':{'send_notifications': False,'accept_commands':False,'private':False}},
			debug = False,
			send_icon = True
		)
	
	def get_template_configs(self):
		return [
			dict(type="settings", name="Telegram", custom_bindings=True)
		]
	
	def get_update_information(self, *args, **kwargs):
		return dict(
			telegram=dict(
				displayName=self._plugin_name,
				displayVersion=self._plugin_version,
				
				type="github_release",
				current=self._plugin_version,
				user="fabianonline",
				repo="OctoPrint-Telegram",
				
				pip="https://github.com/fabianonline/OctoPrint-Telegram/archive/{target}.zip"
			)
		)
	
	def is_notification_necessary(self, new_z, old_z):
		timediff = self._settings.get_int(['notification_time'])
		if timediff and timediff > 0:
			# check the timediff
			if self.last_notification_time + timediff*60 <= time.time():
				return True
		zdiff = self._settings.get_float(['notification_height'])
		if zdiff and zdiff > 0.0:
			if old_z is None:
				return False
			# check the zdiff
			if abs(new_z - (old_z or 0.0)) >= 0.8:
				# big changes in height are not interesting for notifications - we ignore them
				self.last_z = new_z
				return False
			if new_z >= self.last_z + zdiff or new_z < self.last_z:
				return True
		return False
		
	def on_event(self, event, payload, *args, **kwargs):
		try:
			if event not in self.msgDict:
				# return as fast as possible
				return
			
			self._logger.debug("Got an event: " + event + " Payload: " + str(payload))
			# PrintFailed Payload: {'origin': 'local', 'file': u'cube.gcode'}
			# MovieDone Payload: {'gcode': u'cube.gcode', 'movie_basename': 'cube_20160216125143.mpg', 'movie': '/home/pi/.octoprint/timelapse/cube_20160216125143.mpg'}
			
			z = ""
			
			status = self._printer.get_current_data()
			delay = 0
			track = True
			if event=="ZChange":
				if not status['state']['flags']['printing']:
					return
				z = payload['new']
				self._logger.debug("Z-Change. new_z=%.2f old_z=%.2f last_z=%.2f notification_height=%.2f notification_time=%d",
					z,
					payload['old'],
					self.last_z,
					self._settings.get_float(['notification_height']),
					self._settings.get_int(['notification_time']))
				
				if not self.is_notification_necessary(payload['new'], payload['old']):
					return
			elif event=="PrintStarted":
				self.last_z = 0.0
				self.last_notification_time = time.time()
				if not self._settings.get_boolean(["message_at_print_started"]):
					return
			elif event=="PrintDone":
				if self.shut_up:
					self.shut_up = False
					return
				if not self._settings.get_boolean(["message_at_print_done"]):
					return
				delay = self._settings.get_int(["message_at_print_done_delay"])
			elif event=="PrintFailed":
				if self.shut_up:
					self.shut_up = False
					return
				if not self._settings.get_boolean(["message_at_print_failed"]):
					return
			elif event=="StatusPrinting":
				z = payload['z']
				# Change the event type in order to generate a ZChange message
				event = "ZChange"
				track = False
			elif event=="StatusNotPrinting":
				track = False
			
			self.last_notification_time = time.time()
			self.last_z = z
				
			if self.shut_up:
				return
			#build locals for message parsing

			self._logger.debug(str(status))
			if event != "PrinterStart":
				temps = self._printer.get_current_temperatures()
				self._logger.debug(str(temps))
				bed_temp = temps['bed']['actual'] if 'bed' in temps else 0.0
				bed_target = temps['bed']['target'] if 'bed' in temps else 0.0 
				e1_temp = temps['tool0']['actual']
				e1_target = temps['tool0']['target']
				e2_temp = e2_target = None
				if "tool1" in temps:
					e2_temp = temps['tool1']['actual']
					e2_target = temps['tool1']['target']
			percent = int(status['progress']['completion'] or 0)
			time_done = octoprint.util.get_formatted_timedelta(datetime.timedelta(seconds=(status['progress']['printTime'] or 0)))
			time_left = octoprint.util.get_formatted_timedelta(datetime.timedelta(seconds=(status['progress']['printTimeLeft'] or 0)))
			file = ""
			if "file" in payload: file = payload["file"]
			if "gcode" in payload: file = payload["gcode"]
			if "filename" in payload: file = payload["filename"]
			emo = {}
			for k in self.emojis:
				emo[k] = self.emojis[k].encode("utf-8")

			message = self._settings.get(["messages",event,"text"]).format(**locals())
			self._logger.debug("Sending message: " + message)
			if "chatID" in kwargs:
				self.send_msg(message, with_image=True, delay=delay,chatID=kwargs['chatID'])
			else:
				self.send_msg(message, with_image=True, delay=delay)
			if track:
				self.track_action("notification/" + event)
		except Exception as e:
			self._logger.debug("Exception: " + str(e))
	
	def send_msg(self, message, **kwargs):
		kwargs['message'] = message
		if 'chatID' not in kwargs:
			for key in self.chats:
				if self.chats[key]['send_notifications']:
					kwargs['chatID'] = key
					threading.Thread(target=self._send_msg, kwargs=kwargs).run()
			return
		if 'msg_id' in kwargs:
			if kwargs['msg_id'] is not None:
				threading.Thread(target=self._send_edit_msg, kwargs=kwargs).run()
				return
		threading.Thread(target=self._send_msg, kwargs=kwargs).run()


	def _send_edit_msg(self,message="",msg_id="",chatID="", **kwargs):
		try:
			self._logger.debug("Sending a message UPDATE: " + message.replace("\n", "\\n") + " chatID= " + str(chatID))
			data = {}
			data['text'] = message
			data['message_id'] = msg_id
			data['chat_id'] = int(chatID)
			self._logger.debug("SENDING UPDATE: " + str(data))
			req = requests.post(self.bot_url + "/editMessageText", data=data)
			if req.headers['content-type'] != 'application/json':
				self.set_status(gettext("Unexpected Content-Type. Expected: application/json. Was: %(type)s. Waiting 2 minutes before trying again.", type=req.headers['content-type']))
				return
			myJson = req.json()
			self._logger.debug("REQUEST RES: "+str(myJson))
		except Exception as ex:
			self._logger.debug("Caught an exception in send_msg(): " + str(ex))

	def _send_msg(self, message="", with_image=False, responses=None, force_reply=False, delay=0, noMarkup = False, chatID = "", **kwargs):
		if delay > 0:
			time.sleep(delay)
		try:
			self._logger.debug("Sending a message: " + message.replace("\n", "\\n") + " with_image=" + str(with_image) + " chatID= " + str(chatID))
			data = {}
			# We always send hide_keyboard unless we send an actual keyboard or an Message Update (noMarkup = true)
			if not noMarkup:
				data['reply_markup'] = json.dumps({'hide_keyboard': True})  
				
			if force_reply:			
				if self.messageResponseID != None:
					data['reply_markup'] = json.dumps({'force_reply': True, 'selective': True})
					data['reply_to_message_id'] = self.messageResponseID
				else:
					data['reply_markup'] = json.dumps({'force_reply': True})
			if responses:
				if self.messageResponseID != None:
					keyboard = {'keyboard':map(lambda x: [x], responses), 'one_time_keyboard': True, 'selective': True}
					data['reply_markup'] = json.dumps(keyboard)
					data['reply_to_message_id'] = self.messageResponseID
				else:
					keyboard = {'keyboard':map(lambda x: [x], responses), 'one_time_keyboard': True}
					data['reply_markup'] = json.dumps(keyboard)

			image_data = None
			if with_image:
				image_data = self.take_image()
			self._logger.debug("data so far: " + str(data))

			if chatID in self.updateMessageID:
				del self.updateMessageID[chatID]

			r = None
			data['chat_id'] = chatID
			if image_data:
				self._logger.debug("Sending with image.. " + str(chatID))
				files = {'photo':("image.jpg", image_data)}
				data['caption'] = message
				r = requests.post(self.bot_url + "/sendPhoto", files=files, data=data)
				self._logger.debug("Sending finished. " + str(r.status_code) + " " + str(r.content))

			else:
				self._logger.debug("Sending without image.. " + str(chatID))
				data['text'] = message
				r =requests.post(self.bot_url + "/sendMessage", data=data)

			if r is not None and noMarkup:
				if r.status_code != 200 or r.headers['content-type'] != 'application/json':
					raise NameError("ReqErr")
				myJson = r.json()
				if not myJson['ok']:
					raise NameError("ReqErr")
				if 'message_id' in myJson['result']:
					self.updateMessageID[chatID] = myJson['result']['message_id']
		except Exception as ex:
			self._logger.debug("Caught an exception in send_msg(): " + str(ex))
		self.messageResponseID = None
	
	def send_video(self, message, video_file):
		files = {'video': open(video_file, 'rb')}
		#r = requests.post(self.bot_url + "/sendVideo", files=files, data={'chat_id':self._settings.get(["chat"]), 'caption':message})
		self._logger.debug("Sending finished. " + str(r.status_code) + " " + str(r.content))
	
	def get_file(self, file_id):
		self._logger.debug("Requesting file with id %s.", file_id)
		r = requests.get(self.bot_url + "/getFile", data={'file_id': file_id})
		# {"ok":true,"result":{"file_id":"BQADAgADCgADrWJxCW_eFdzxDPpQAg","file_size":26,"file_path":"document\/file_3.gcode"}}
		r.raise_for_status()
		data = r.json()
		if not "ok" in data:
			raise Exception(_("Telegram didn't respond well to getFile. The response was: %(response)s", response=r.text))
		url = self.bot_file_url + "/" + data['result']['file_path']
		self._logger.debug("Downloading file: %s", url)
		r = requests.get(url)
		r.raise_for_status()
		return r.content

	def get_usrPic(self,chat_id):
		self._logger.debug("Requesting Profile Photo for chat_id: " + str(chat_id))
		try:
			if int(chat_id) < 0:
				self._logger.debug("Not able to load group photos. EXIT")
				return
			r = requests.get(self.bot_url + "/getUserProfilePhotos", params = {'limit': 1, "user_id": chat_id})
			r.raise_for_status()
			data = r.json()
			if not "ok" in data:
				raise Exception(_("Telegram didn't respond well to getUserProfilePhoto. The response was: %(response)s", response=r.text))
			if data['result']['total_count'] < 1:
				self._logger.debug("NO PHOTOS. EXIT")
				return
			self.get_Pic(chat_id,data['result']['photos'][0][0]['file_id'])
		except Exception as ex:
			self._logger.error("Can't load UserImage: " + str(ex))

	def get_Pic(self,chat_id,file_id):
		self._logger.debug("Requesting Profile Photo File Path")
		url = self.bot_url + "/getFile"
		r = requests.get(self.bot_url + "/getFile", params = {'file_id': file_id})
		r.raise_for_status()
		data = r.json()
		if not "ok" in data:
			raise Exception(_("Telegram didn't respond well to getFile. The response was: %(response)s", response=r.text))
		url = self.bot_file_url + "/" + data['result']['file_path']
		self._logger.debug("Downloading Profile Photo: %s", url)
		r = requests.get(url)
		r.raise_for_status()

		file_name = self.get_plugin_data_folder() + "/pic" + str(chat_id) + ".jpg"
		f = open(file_name,"wb")
		f.write(r.content)
		f.close()

		img = Image.open(file_name)
		img = img.resize((40, 40), PIL.Image.ANTIALIAS)
		img.save(file_name)

		self._logger.debug("Saved Photo")




	def take_image(self):
		snapshot_url = self._settings.global_get(["webcam", "snapshot"])
		self._logger.debug("Snapshot URL: " + str(snapshot_url))
		data = None
		if snapshot_url:
			try:
				r = requests.get(snapshot_url)
				data = r.content
			except Exception as e:
				return None
		flipH = self._settings.global_get(["webcam", "flipH"])
		flipV = self._settings.global_get(["webcam", "flipV"])
		rotate= self._settings.global_get(["webcam", "rotate90"])
		
		if flipH or flipV or rotate:
			image = Image.open(StringIO.StringIO(data))
			if rotate:
				image = image.transpose(Image.ROTATE_90)
			if flipH:
				image = image.transpose(Image.FLIP_LEFT_RIGHT)
			if flipV:
				image = image.transpose(Image.FLIP_TOP_BOTTOM)
			output = StringIO.StringIO()
			image.save(output, format="JPEG")
			data = output.getvalue()
			output.close()
		return data
	
	def test_token(self, token=None):
		if token is None:
			token = self._settings.get(["token"])
		response = requests.get("https://api.telegram.org/bot" + token + "/getMe")
		self._logger.debug("getMe returned: " + str(response.json()))
		self._logger.debug("getMe status code: " + str(response.status_code))
		json = response.json()
		if not 'ok' in json or not json['ok']:
			if json['description']:
				raise(Exception(gettext("Telegram returned error code %(error)s: %(message)s", error=json['error_code'], message=json['description'])))
			else:
				raise(Exception(gettext("Telegram returned an unspecified error.")))
		else:
			return "@" + json['result']['username']
	
	def get_api_commands(self):
		return dict(
			testToken=["token"],
			updateChat=["ID"],
			delChat=["ID"]
		)

	def on_api_get(self, request):
		if 'id' in request.args and 'cmd' in request.args and 'note' in request.args:
			self.chats[request.args['id']]['accept_commands'] = request.args['cmd']
			self.chats[request.args['id']]['send_notifications'] = request.args['note']
			self._logger.debug("Updated chat - " + str(request.args['id']))

		elif 'id' in request.args and 'img' in request.args:
			chat_id = request.args['id']
			file_path = self._basefolder+"/static/img/default.jpg"
			if int(chat_id) < 0:
				file_path = self._basefolder+"/static/img/group.jpg"
			else:
				for f in os.listdir(self.get_plugin_data_folder()):
					if f.endswith("pic" +chat_id+".jpg"):
						file_path = self.get_plugin_data_folder()+"/pic" +chat_id+".jpg"
				
			f = open(file_path,"r")
			res = f.read()
			f.close()
			self._logger.debug("LOAD DEFAULT IMAGE")
			return flask.make_response(flask.jsonify({'result':base64.b64encode(res), 'id': chat_id}),200)
		elif 'bindings' in request.args:
			return json.dumps({'bind_cmd':[k for k, v in self.thread.commandDict.iteritems() if 'bind_cmd' in v or 'bind_none' in v ], 'messages':[k for k, v in self.msgDict.iteritems() if 'bind_msg' not in v ]})

		return json.dumps({'chats':{k: v for k, v in self.chats.iteritems() if 'delMe' not in v and k != 'zBOTTOMOFCHATS'}, 'connection_state_str':self.connection_state_str, 'connection_ok':self.connection_ok})
	
	def on_api_command(self, command, data):
		if command=="testToken":
			self._logger.debug("Testing token {}".format(data['token']))
			try:
				username = self.test_token(data['token'])
				self._settings.set(['token'], data['token'])
				self.stop_listening() #to start with new token if already running
				self.start_listening()
				return json.dumps({'ok': True, 'connection_state_str': gettext("Token valid for %(username)s.", username=username), 'error_msg': None, 'username': username})
			except Exception as ex:
				return json.dumps({'ok': False, 'connection_state_str': gettext("Error: %(error)s", error=ex), 'username': None, 'error_msg': str(ex)})
		elif command=="delChat":
			strId = str(data['ID'])
			if strId in self.chats:	
				del self.chats[strId]
			return json.dumps({'chats':{k: v for k, v in self.chats.iteritems() if 'delMe' not in v and k != 'zBOTTOMOFCHATS'}, 'connection_state_str':self.connection_state_str, 'connection_ok':self.connection_ok})
		
	
	def get_assets(self):
		return dict(js=["js/telegram.js"])
		
	def track_action(self, action):
		if not self._settings.get_boolean(["tracking_activated"]):
			return
		if self._settings.get(["tracking_token"]) is None:
			token = "".join(random.choice("abcdef0123456789") for i in xrange(16))
			self._settings.set(["tracking_token"], token)
		params = {'idsite': '3', 'rec': '1', 'url': 'http://octoprint-telegram/'+action, 'action_name': ("%20/%20".join(action.split("/"))), '_id': self._settings.get(["tracking_token"])}
		threading.Thread(target=requests.get, args=("http://piwik.schlenz.ruhr/piwik.php",), kwargs={'params': params}).run()

__plugin_name__ = "Telegram Notifications"
__plugin_implementation__ = TelegramPlugin()
__plugin_hooks__ = {
	"octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
}
