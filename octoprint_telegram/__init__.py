from __future__ import absolute_import
from PIL import Image
import threading, requests, re, time, datetime, StringIO, json, random, logging, traceback, io, collections, os, flask,base64,PIL
import octoprint.plugin, octoprint.util, octoprint.filemanager
from flask.ext.babel import gettext
from .telegramCommands import TCMD #telegramCommands.
from .telegramNotifications import TMSG #telegramNotifications
from .telegramNotifications import telegramMsgDict

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

		
	def newChat(self):
		return {'accept_commands' : False, 
				'send_notifications' : False, 
				'new': True, 
				'allow_users': False,
				'commands': {k: False for k,v in self.main.tcmd.commandDict.iteritems()}, 
				'notifications': {k: False for k,v in telegramMsgDict.iteritems()}
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
					data = {}
					self._logger.debug("NEW USER: " + str(data))
					iAmNew = False
					if chat_id in self.main.chats:
						data = self.main.chats[chat_id]
					else:
						data = self.newChat()
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
							if command.startswith("/") and command in self.main.tcmd.commandDict:
								if self.main.chats[from_id]['commands'][command]:
									allowed = True
							elif parameter != None:
								if parameter.startswith("/") and parameter in self.main.tcmd.commandDict:
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
								if command in self.main.tcmd.commandDict :
									self.main.tcmd.commandDict[command]['cmd'](chat_id=chat_id,parameter=parameter)
								elif parameter in self.main.tcmd.commandDict:
									self.main.tcmd.commandDict[parameter]['cmd'](chat_id=chat_id,parameter=command)
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
									requests.get(self.main.bot_url + "/sendChatAction", params = {'chat_id': chat_id, 'action': 'upload_document'})
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
					elif "left_chat_member" in message['message']:
						self._logger.debug("Message Del_Chat")
						if message['message']['left_chat_member']['username'] == self.username[1:] and str(message['message']['chat']['id']) in self.main.chats:
							del self.main.chats[str(message['message']['chat']['id'])]
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
		self.bot_url = None
		self.chats = {}
		self.connection_state_str = gettext("Disconnected.")
		self.connection_ok = False
		self.messageResponseID = None
		requests.packages.urllib3.disable_warnings()
		self.updateMessageID = {}
		self.shut_up = {}
		self.tcmd = None
		self.tmsg = None
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
		self._logger.debug("ON_STARTUP")
		self.tcmd = TCMD(self)
		self.tmsg = TMSG(self)
		self.start_listening()
		self.track_action("started")
		self.chats = self._settings.get(["chats"])
		# Delete user profile photos if user doesn't exist anymore
		for f in os.listdir(self.get_plugin_data_folder()):
			fcut = f.split('.')[0][3:]
			self._logger.debug("Testing Pic ID " + str(fcut))
			if fcut not in self.chats:
				self._logger.debug("Removing pic" +fcut+".jpg")
				try:
					os.remove(self.get_plugin_data_folder()+"/pic" +fcut+".jpg")
				except OSError:
					pass
		#Update user profile photos
		for key in self.chats:
			try:
				kwargs = {}
				kwargs['chat_id'] = int(key)
				threading.Thread(target=self.get_usrPic, kwargs=kwargs).run()
			except Exception:
				pass
	
	def on_shutdown(self):
		self.on_event("PrinterShutdown",{})
	
	def set_log_level(self):
		self._logger.setLevel(logging.DEBUG if self._settings.get_boolean(["debug"]) else logging.NOTSET)

### Settings API

	def get_settings_defaults(self):
		return dict(
			token = "",
			notification_height = 5.0,
			notification_time = 15,
			message_at_print_done_delay = 0,
			messages = telegramMsgDict,
			tracking_activated = False,
			tracking_token = None,
			chats = {'zBOTTOMOFCHATS':{'send_notifications': False,'accept_commands':False,'private':False}},
			debug = False,
			send_icon = True
		)

	def get_settings_version(self):
		return 1

	def get_settings_preprocessors(self):
		return dict(), dict(
			notification_height=lambda x: float(x),
			notification_time=lambda x: int(x)
		)

	def on_settings_migrate(self, target, current=None):
		self._logger.setLevel(logging.DEBUG)
		self._logger.debug("MIGRATE DO")
		tcmd = TCMD(self)
		if current is None or current < 1:
			# Reset Chats (there shouldn't be any chats)
			# disabled = self._settings.get(['disabled'])
			# if disabled is None:
			# 	self._settings.set(['disabled'], False)
			self._settings.set(["chats"],{'zBOTTOMOFCHATS':{'send_notifications': False,'accept_commands':False,'private':False}})
			# Is there an chat from old plugin version chats?
			# then migrate it
			chat = self._settings.get(["chat"])
			if chat is not None:
				self._settings.set(["chat"], None)
				data = {'accept_commands' : False, 
					'send_notifications' : False, 
					'new': False, 
					'allow_users': False,
					'commands': {k: False for k,v in tcmd.commandDict.iteritems()}, 
					'notifications': {k: False for k,v in telegramMsgDict.iteritems()}
					}
				#try to get infos from telegram by sending a "you are migrated" message
				try:
					message = {	'text':"The Plugin" + self._plugin_name + " has been updated to new Version "+self._plugin_version+ ".\n\n"
									+"Please open your" + self._plugin_name + " settings and set configurations for this chat. Until then you are not able to do or receive anything with this account.\n\n"
									+"More informations on: " + self._plugin_url,
								'chat_id': chat}
					r = responses.get("https://api.telegram.org/bot" + self._settings.get(['token']) + "/sendMessage", params =  message)
					r.raise_for_status()
					if req.headers['content-type'] != 'application/json':
						raise Exception("invalid content-type")
					json = req.json()
					if not json['ok']:
						raise Exception("invalid request")
					chat = json['message']['chat']
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
					else: 
						data['private'] = True
						data['title'] = "[UNKNOWN]"
				except Exception as ex:
					data['private'] = True
					data['title'] = "[UNKNOWN]"
					self._logger.debug("ERROR migrating chat. Done with defaults private=true,title=[UNKNOWN] : " + str(ex))
				self._settings.set(["chats",chat],data)
				self._logger.debug("MIGRATED USER: " + str(data))
			emojis = self._settings.get(["send_icon"])
			# Update or delete new/old settings
			if emojis is None:
				self._settings.set(["send_icon"], False)

			self._settings.set(["messages"],telegramMsgDict)	
			self._settings.set(["message_at_startup"], None)
			self._settings.set(["message_at_shutdown"], None)
			self._settings.set(["message_at_print_started"], None)
			self._settings.set(["message_at_print_done"], None)
			self._settings.set(["message_at_print_failed"], None)
			try:
				self._settings.save()
			except Exception as ex:
				self._logger.error("MIGRATED Save failed - " + str(ex)) 
			self._logger.debug("MIGRATED Saved")

		if current is None or current < target:
			pass

	def on_settings_save(self, data):
		delList = []
		# Remove 'new'-flag and apply bindings for all chats
		for key in data['chats']:
			if 'new' in data['chats'][key] or 'new' in data['chats'][key]:
				data['chats'][key]['new'] = False
			# Apply command bindings
			if not key == "zBOTTOMOFCHATS":
				for cmd in self.tcmd.commandDict:
					if 'bind_cmd' in self.tcmd.commandDict[cmd]:
						data['chats'][key]['commands'][cmd] = data['chats'][key]['commands'][self.tcmd.commandDict[cmd]['bind_cmd']]
					if 'bind_none' in self.tcmd.commandDict[cmd]:
						data['chats'][key]['commands'][cmd] = True
			# Look for deleted chats
			if not key in self.chats and not key == "zBOTTOMOFCHATS":
				delList.append(key)
		# Delete chats finally
		for key in delList:
			del data['chats'][key]
		# Also remove 'new'-flag from self.chats so settingsUI is consistent 
		# self.chats will only update to settings data on first received message after saving done
		for key in self.chats:
			if 'new' in self.chats[key]:
				self.chats[key]['new'] = False

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
		# Reconnect on new token
		# Will stop listener on invalid token
		if data['token']!=old_token:
			self.stop_listening()
		if data['token']!="":
			self.start_listening()
		else:
			self.connection_state_str = gettext("No token given.")
	
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
		
	def on_event(self, event, payload, **kwargs):
		try:
			if event in self.tmsg.msgCmdDict:
				# Start event handler
				self._logger.debug("Got an event: " + event + " Payload: " + str(payload))
				self.tmsg.msgCmdDict[event]['cmd'](event, payload, **kwargs)
			else:
				# return as fast as possible
				return
		except Exception as e:
			self._logger.debug("Exception: " + str(e))
	
	def get_assets(self):
		return dict(js=["js/telegram.js"])

	def send_msg(self, message, **kwargs):
		kwargs['message'] = message
		try:
			# If it's a regular event notification
			if 'chatID' not in kwargs and 'event' in kwargs:
				for key in self.chats:
					if self.chats[key]['notifications'][kwargs['event']] and key not in self.shut_up and self.chats[key]['send_notifications']:
						kwargs['chatID'] = key
						threading.Thread(target=self._send_msg, kwargs = kwargs).run()
			# Seems to be a broadcast
			elif 'chatID' not in kwargs:
				for key in self.chats:
					kwargs['chatID'] = key
					threading.Thread(target=self._send_msg, kwargs = kwargs).run()
			# This is a 'editMessageText' message
			elif 'msg_id' in kwargs:
				if kwargs['msg_id'] is not None:
					threading.Thread(target=self._send_edit_msg, kwargs = kwargs).run()
			# direct message or event notification to a chat_id
			else:
				threading.Thread(target=self._send_msg, kwargs = kwargs).run()
		except Exception as ex:
			self._logger.debug("Caught an exception in send_msg(): " + str(ex))

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
			self._logger.debug("Caught an exception in _send_edit_msg(): " + str(ex))

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
					keyboard = {'keyboard':map(lambda x: [x], responses), 'one_time_keyboard': True, 'selective': True, 'force_reply': True}
					data['reply_markup'] = json.dumps(keyboard)
					data['reply_to_message_id'] = self.messageResponseID
				else:
					keyboard = {'keyboard':map(lambda x: [x], responses), 'one_time_keyboard': True, 'force_reply': True}
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
				r.raise_for_status()
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
			r = self.get_file(data['result']['photos'][0][0]['file_id'])
			file_name = self.get_plugin_data_folder() + "/pic" + str(chat_id) + ".jpg"
			f = open(file_name,"wb")
			f.write(r)
			f.close()
			img = Image.open(file_name)
			img = img.resize((40, 40), PIL.Image.ANTIALIAS)
			img.save(file_name)
			self._logger.debug("Saved Photo")

		except Exception as ex:
			self._logger.error("Can't load UserImage: " + str(ex))

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
			delChat=["ID"]
		)

	def str2bool(self,v):
		return v.lower() in ("yes", "true", "t", "1")

	def on_api_get(self, request):
		if 'id' in request.args and 'cmd' in request.args and 'note' in request.args:
			self.chats[request.args['id']]['accept_commands'] = self.str2bool(str(request.args['cmd']))
			self.chats[request.args['id']]['send_notifications'] = self.str2bool(str(request.args['note']))
			self._logger.debug("Updated chat - " + str(request.args['id']))

		if 'id' in request.args and 'img' in request.args:
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
			return flask.make_response(flask.jsonify({'result':base64.b64encode(res), 'id': chat_id}),200)
		elif 'bindings' in request.args:
			bind_text = {}
			for key in {k: v for k, v in telegramMsgDict.iteritems() if 'bind_msg' in v }:
				if telegramMsgDict[key]['bind_msg'] in bind_text:
					bind_text[telegramMsgDict[key]['bind_msg']].append(key)
				else:
					bind_text[telegramMsgDict[key]['bind_msg']] = [key]
			return json.dumps({
				'bind_cmd':[k for k, v in self.tcmd.commandDict.iteritems() if 'bind_cmd' not in v and 'bind_none' not in v ],
				'bind_msg':[k for k, v in telegramMsgDict.iteritems() if 'bind_msg' not in v ],
				'bind_text':bind_text,
				'no_setting':[k for k, v in telegramMsgDict.iteritems() if 'no_setting' in v ]})

		return json.dumps({'chats':{k: v for k, v in self.chats.iteritems() if 'delMe' not in v and k != 'zBOTTOMOFCHATS'}, 'connection_state_str':self.connection_state_str, 'connection_ok':self.connection_ok})
	
	def on_api_command(self, command, data):
		if command=="testToken":
			self._logger.debug("Testing token {}".format(data['token']))
			try:
				if self._settings.get(["token"]) != data["token"]:
					username = self.test_token(data['token'])
					self._settings.set(['token'], data['token'])
					self.stop_listening() #to start with new token if already running
					self.start_listening()
					return json.dumps({'ok': True, 'connection_state_str': gettext("Token valid for %(username)s.", username=username), 'error_msg': None, 'username': username})
				return json.dumps({'ok': True, 'connection_state_str': gettext("Token valid for %(username)s.", username=self.thread.username), 'error_msg': None, 'username': self.thread.username})
			except Exception as ex:
				return json.dumps({'ok': False, 'connection_state_str': gettext("Error: %(error)s", error=ex), 'username': None, 'error_msg': str(ex)})
		elif command=="delChat":
			strId = str(data['ID'])
			if strId in self.chats:	
				del self.chats[strId]
			return json.dumps({'chats':{k: v for k, v in self.chats.iteritems() if 'delMe' not in v and k != 'zBOTTOMOFCHATS'}, 'connection_state_str':self.connection_state_str, 'connection_ok':self.connection_ok})
		
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
