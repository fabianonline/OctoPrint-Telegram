from __future__ import absolute_import
from PIL import Image
from subprocess import Popen, PIPE
import threading, requests, re, time, datetime, StringIO, json, random, logging, traceback, io, collections, os, flask,base64,PIL, pkg_resources,subprocess,zipfile,glob #,resource
import octoprint.plugin, octoprint.util, octoprint.filemanager
from flask_babel import gettext
from flask_login import current_user
from .telegramCommands import TCMD # telegramCommands.
from .telegramNotifications import TMSG # telegramNotifications
from .telegramNotifications import telegramMsgDict # dict of known notification messages
from .emojiDict import telegramEmojiDict # dict of known emojis
from babel.dates import format_date, format_datetime, format_time
####################################################
#        TelegramListener Thread Class
# Connects to Telegram and will listen for messages.
# On incomming message the listener will process it.
####################################################

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


	def run(self):
		self._logger.debug("Try first connect.")
		self.tryFirstContact()
		# repeat fetching and processing messages unitil thread stopped
		self._logger.debug("Listener is running.")
		try:
			while not self.do_stop:
				try:
					self.loop()
				except ExitThisLoopException:
					# do nothing, just go to the next loop
					pass
		except Exception as ex:
			self._logger.error("An Exception crashed the Listener: " + str(ex) + " Traceback: " + traceback.format_exc() )

		self._logger.debug("Listener exits NOW.")

	# Try to get first contact. Repeat every 120sek if no success
	# or stop if task stopped
	def tryFirstContact(self):
		gotContact = False
		while not self.do_stop and not gotContact:
			try:
				self.username = self.main.test_token()
				gotContact = True
				self.set_status(gettext("Connected as %(username)s.", username=self.username), ok=True)
			except Exception as ex:
				self.set_status(gettext("Got an exception while initially trying to connect to telegram (Listener not running: %(ex)s.  Waiting 2 minutes before trying again.)", ex=ex))
				time.sleep(120)

	def loop(self):
		chat_id = ""
		json = self.getUpdates()
		try:
			# seems like we got a message, so lets process it.
			for message in json['result']:
				self.processMessage(message)
		except ExitThisLoopException as exit:
			raise exit
		#wooooops. can't handle the message
		except Exception as ex:
			self._logger.error("Exception caught! " + str(ex))
		self.set_status(gettext("Connected as %(username)s.", username=self.username), ok=True)
		# we had first contact after octoprint startup
		# so lets send startup message
		if self.first_contact:
			self.first_contact = False
			self.main.on_event("PrinterStart",{})

	def set_update_offset(self, new_value):
		if new_value >= self.update_offset:
			self._logger.debug("Updating update_offset from {} to {}".format(self.update_offset, 1 + new_value))
			self.update_offset = 1 + new_value
		else:
			self._logger.debug("Not changing update_offset - otherwise would reduce it from {} to {}".format(self.update_offset, 1 + new_value))

	def processMessage(self, message):
		self._logger.debug("MESSAGE: " + str(message))
		# Get the update_id to only request newer Messages the next time
		self.set_update_offset(message['update_id'])
		# no message no cookies
		if 'message' in message and message['message']['chat']:

			chat_id, from_id = self.parseUserData(message)

			# if we come here without a continue (discard message)
			# we have a message from a known and not new user
			# so let's check what he send us
			# if message is a text message, we probably got a command
			# when the command is not known, the following handler will discard it
			if "text" in message['message']:
				self.handleTextMessage(message, chat_id, from_id)
			# we got no message with text (command) so lets check if we got a file
			# the following handler will check file and saves it to disk
			elif "document" in message['message']:
				self.handleDocumentMessage(message, chat_id, from_id)
			# we got message with notification for a new chat title photo
			# so lets download it
			elif "new_chat_photo" in message['message']:
				self.handleNewChatPhotoMessage(message, chat_id, from_id)
			# we got message with notification for a deleted chat title photo
			# so we do the same
			elif "delete_chat_photo" in message['message']:
				self.handleDeleteChatPhotoMessage(message, chat_id, from_id)
			# a member was removed from a group, so lets check if it's our bot and
			# delete the group from our chats if it is our bot
			elif "left_chat_member" in message['message']:
				self.handleLeftChatMemberMessage(message, chat_id, from_id)
			# we are at the end. At this point we don't know what message type it is, so we do nothing
			else:
				self._logger.warn("Got an unknown message. Doing nothing. Data: " + str(message))
		elif 'callback_query' in message:
			self.handleCallbackQuery(message)
		else:
			self._logger.warn("Response is missing .message or .message.chat or callback_query. Skipping it.")
			raise ExitThisLoopException()


	def handleCallbackQuery(self, message):
		message['callback_query']['message']['text'] = message['callback_query']['data']
		chat_id, from_id = self.parseUserData(message['callback_query'])
		self.handleTextMessage(message['callback_query'],chat_id, from_id)

	def handleLeftChatMemberMessage(self, message, chat_id, from_id):
		self._logger.debug("Message Del_Chat")
		if message['message']['left_chat_member']['username'] == self.username[1:] and str(message['message']['chat']['id']) in self.main.chats:
			del self.main.chats[str(message['message']['chat']['id'])]
			# do a self._settings.save() ???
			self._logger.debug("Chat deleted")

	def handleDeleteChatPhotoMessage(self, message, chat_id, from_id):
		self._logger.debug("Message Del_Chat_Photo")
		try:
			os.remove(self.main.get_plugin_data_folder()+"/img/user/pic" +str(message['message']['chat']['id'])+".jpg")
			self._logger.debug("File removed")
		except OSError:
			pass

	def handleNewChatPhotoMessage(self, message, chat_id, from_id):
		self._logger.debug("Message New_Chat_Photo")
		# only if we know the chat
		if str(message['message']['chat']['id']) in self.main.chats:
			self._logger.debug("New_Chat_Photo Found User")
			kwargs = {'chat_id':int(message['message']['chat']['id']), 'file_id': message['message']['new_chat_photo'][0]['file_id'] }
			t = threading.Thread(target=self.main.get_usrPic, kwargs=kwargs)
			t.daemon = True
			t.run()

	def handleDocumentMessage(self, message, chat_id, from_id):
		# first we have to check if chat or group is allowed to upload
		from_id = chat_id
		if not self.main.chats[chat_id]['private']: #is this needed? can one send files from groups to bots?
			from_id = str(message['message']['from']['id'])
		# is /upload allowed?
		if self.main.isCommandAllowed(chat_id,from_id,'/upload'):
			self.main.track_action("command/upload_exec")
			try:
				file_name = message['message']['document']['file_name']
				#if not (file_name.lower().endswith('.gcode') or file_name.lower().endswith('.gco') or file_name.lower().endswith('.g')):
				self._logger.info(str(file_name.lower().split('.')[-1]))
				isZipFile = False
				if not octoprint.filemanager.valid_file_type(file_name,"machinecode"):
					#giloser 09/05/2019 try to zip the gcode file to lower the size
					if file_name.lower().endswith('.zip'):
						isZipFile = True
					else:
						self.main.send_msg(self.gEmo('warning') + " Sorry, I only accept files with .gcode, .gco or .g or .zip extension.", chatID=chat_id)
						raise ExitThisLoopException()
				# download the file
				if self.main.version >= 1.3:
					target_filename = "TelegramPlugin/"+file_name
					from octoprint.server.api.files import _verifyFolderExists
					if not _verifyFolderExists(octoprint.filemanager.FileDestinations.LOCAL, "TelegramPlugin"):
						self.main._file_manager.add_folder(octoprint.filemanager.FileDestinations.LOCAL,"TelegramPlugin")
				else:
					target_filename = "telegram_"+file_name
				# for parameter no_markup see _send_edit_msg()
				self.main.send_msg(self.gEmo('save') + gettext(" Saving file {}...".format(target_filename)), chatID=chat_id)
				requests.get(self.main.bot_url + "/sendChatAction", params = {'chat_id': chat_id, 'action': 'upload_document'})
				data = self.main.get_file(message['message']['document']['file_id'])
				#giloser 09/05/2019 try to zip the gcode file to lower the size
				if isZipFile:
					try:
						#stream = octoprint.filemanager.util.StreamWrapper(target_filename, io.BytesIO(data))
						#self.main._file_manager.add_folder(self.get_plugin_data_folder() , "tmpzip", ignore_existing=True)
						zip_filename= self.main.get_plugin_data_folder()+"/tmpzip/" +file_name
						with open(zip_filename,'w') as f:
							f.write(data)
						#self.main._file_manager.add_file(octoprint.filemanager.FileDestinations.LOCAL, target_filename, stream, allow_overwrite=True)
					except Exception as ex:
						self._logger.info("Exception occured during save file : "+ traceback.format_exc() )

					self._logger.info('read archive '  + zip_filename)
					try:
						zf = zipfile.ZipFile(zip_filename, 'r')
						self._logger.info('namelist ')
						list_files = zf.namelist()
						stringmsg = ""
						for filename in list_files:
							if octoprint.filemanager.valid_file_type(filename,"machinecode"):
								try:
									data = zf.read(filename)
									stream = octoprint.filemanager.util.StreamWrapper(filename, io.BytesIO(data))
									if self.main.version >= 1.3:
										target_filename = "TelegramPlugin/"+filename
										from octoprint.server.api.files import _verifyFolderExists
										if not _verifyFolderExists(octoprint.filemanager.FileDestinations.LOCAL, "TelegramPlugin"):
											self.main._file_manager.add_folder(octoprint.filemanager.FileDestinations.LOCAL,"TelegramPlugin")
									else:
										target_filename = "telegram_"+filename
									self.main._file_manager.add_file(octoprint.filemanager.FileDestinations.LOCAL, target_filename, stream, allow_overwrite=True)
									if stringmsg == "":
										stringmsg = self.gEmo('upload') + " I've successfully saved the file you sent me as {}".format(target_filename)
									else:
										stringmsg = stringmsg + ", " + target_filename
									# for parameter msg_id see _send_edit_msg()
								except Exception as ex:
									self._logger.info("Exception occured during processing of a file: "+ traceback.format_exc() )
							else:
								self._logger.info('File '+ filename + ' is not a valide filename ')
					except Exception as ex:
						self.main.send_msg(self.gEmo('warning') + " Sorry, Problem managing the zip file.", chatID=chat_id)
						self._logger.info("Exception occured during processing of a file: "+ traceback.format_exc() )
						raise ExitThisLoopException()
					finally:
						self._logger.info('will now close the zip file')
						zf.close()
					if stringmsg != "":
						self.main.send_msg(stringmsg,msg_id=self.main.getUpdateMsgId(chat_id),chatID=chat_id)
					else:
						self.main.send_msg(self.gEmo('warning') + " Something went wrong during processing of your file."+self.gEmo('mistake')+" Sorry. More details are in octoprint.log.",msg_id=self.main.getUpdateMsgId(chat_id),chatID=chat_id)
						self._logger.info("Exception occured during processing of a file: "+ traceback.format_exc() )

					#self.main._file_manager.remove_file(zip_filename)
					os.remove(zip_filename)
				else:
					stream = octoprint.filemanager.util.StreamWrapper(file_name, io.BytesIO(data))
					self.main._file_manager.add_file(octoprint.filemanager.FileDestinations.LOCAL, target_filename, stream, allow_overwrite=True)
					# for parameter msg_id see _send_edit_msg()
					self.main.send_msg(self.gEmo('upload') + " I've successfully saved the file you sent me as {}.".format(target_filename),msg_id=self.main.getUpdateMsgId(chat_id),chatID=chat_id)
			except ExitThisLoopException:
				pass
			except Exception as ex:
				self.main.send_msg(self.gEmo('warning') + " Something went wrong during processing of your file."+self.gEmo('mistake')+" Sorry. More details are in octoprint.log.",msg_id=self.main.getUpdateMsgId(chat_id),chatID=chat_id)
				self._logger.debug("Exception occured during processing of a file: "+ traceback.format_exc() )
		else:
			self._logger.warn("Previous file was from an unauthorized user.")
			self.main.send_msg("Don't feed the octopuses! " + self.gEmo('octo'),chatID=chat_id)

	def handleTextMessage(self, message, chat_id, from_id):
		# We got a chat message.
		# handle special messages from groups (/commad@BotName)
		command = str(message['message']['text'].split('@')[0].encode('utf-8'))
		parameter = ""
		# TODO: Do we need this anymore?
		# reply_to_messages will be send on value inputs (eg notification height)
		# but also on android when pushing a button. Then we have to switch command and parameter.
		#if "reply_to_message" in message['message'] and "text" in message['message']['reply_to_message']:
			#command = message['message']['reply_to_message']['text']
			#parameter = message['message']['text']
			#if command.encode('utf-8') not in [str(k.encode('utf-8')) for k in self.main.tcmd.commandDict.keys()]:
				#command = message['message']['text']
				#parameter = message['message']['reply_to_message']['text']
		# if command is with parameter, get the parameter
		if any((k+"_") in command for k,v in self.main.tcmd.commandDict.iteritems() if 'param' in v):
			parameter = '_'.join(command.split('_')[1:])
			command = command.split('_')[0]
		self._logger.info("Got a command: '" + str(command.encode('utf-8')) + "' with parameter: '" + str(parameter.encode('utf-8')) + "' in chat " + str(message['message']['chat']['id']))
		# is command  known?
		if command not in self.main.tcmd.commandDict:
			# we dont know the command so skip the message
			self._logger.warn("Previous command was an unknown command.")
			self.main.send_msg("I do not understand you! " + self.gEmo('mistake'),chatID=chat_id)
			raise ExitThisLoopException()
		# check if user is allowed to execute the command
		if self.main.isCommandAllowed(chat_id,from_id,command):
			# Track command
			if command.startswith("/"):
				self.main.track_action("command/" + command[1:])
			# execute command
			self.main.tcmd.commandDict[command]['cmd'](chat_id,from_id,command,parameter)
		else:
			# user was not alloed to execute this command
			self._logger.warn("Previous command was from an unauthorized user.")
			self.main.send_msg("You are not allowed to do this! " + self.gEmo('notallowed'),chatID=chat_id)

	def parseUserData(self, message):
		self.main.chats = self.main._settings.get(["chats"])
		chat = message['message']['chat']
		chat_id = str(chat['id'])
		data = self.main.newChat # data for new user
		# if we know the user or chat, overwrite data with user data
		if chat_id in self.main.chats:
			data = self.main.chats[chat_id]
		# update data or get data for new user
		data['type'] = chat['type'].upper()
		if chat['type']=='group' or chat['type'] == 'supergroup':
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
		from_id = chat_id
		# if message is from a group, chat_id will be left as id of group
		# and from_id is set to id of user who send the message
		if not data['private']:
			if 'from' in message:
				from_id = str(message['from']['id'])
			else:
				from_id = str(message['message']['from']['id'])
			# if group accepts only commands from known users (allow_users = true, accept_commands=false)
			# and user is not in known chats, then he is unknown and we dont wnat to listen to him.
			if chat_id in self.main.chats:
				if self.main.chats[chat_id]['allow_users'] and from_id not in self.main.chats and not self.main.chats[chat_id]['accept_commands']:
					self._logger.warn("Previous command was from an unknown user.")
					self.main.send_msg("I don't know you! Certainly you are a nice Person " + self.gEmo('heart'),chatID=chat_id)
					raise ExitThisLoopException()
		# if we dont know the user or group, create new user
		# send welcome message and skip message
		if chat_id not in self.main.chats:
			self.main.chats[chat_id] = data
			self.main.send_msg(self.gEmo('info') + "Now I know you. Before you can do anything, go to OctoPrint Settings and edit some rights.",chatID=chat_id)
			kwargs = {'chat_id':int(chat_id)}
			t = threading.Thread(target=self.main.get_usrPic, kwargs=kwargs)
			t.daemon = True
			t.run()
			self._logger.debug("Got new User")
			raise ExitThisLoopException()
		return (chat_id, from_id)

	def getUpdates(self):
		self._logger.debug("listener: sending request with offset " + str(self.update_offset) + "...")
		req = None

		# try to check for incoming messages. wait 120sek and repeat on failure
		try:
			if self.update_offset == 0 and self.first_contact:
				res = ["0","0"]
				while len(res) > 0:
					req = requests.get(self.main.bot_url + "/getUpdates", params={'offset':self.update_offset, 'timeout':0}, allow_redirects=False, timeout=10)
					json = req.json()
					if not json['ok']:
						self.set_status(gettext("Response didn't include 'ok:true'. Waiting 2 minutes before trying again. Response was: %(response)s", response=json))
						time.sleep(120)
						raise ExitThisLoopException()
					if len(json['result']) > 0 and 'update_id' in json['result'][0]:
						self.set_update_offset(json['result'][0]['update_id'])
					res = json['result']
					if len(res) < 1:
						self._logger.debug("Ignoring message because first_contact is True.")
				if self.update_offset == 0:
					self.set_update_offset(0)
			else:
				req = requests.get(self.main.bot_url + "/getUpdates", params={'offset':self.update_offset, 'timeout':30}, allow_redirects=False, timeout=40)
		except requests.exceptions.Timeout:
			# Just start the next loop.
			raise ExitThisLoopException()
		except Exception as ex:
			self.set_status(gettext("Got an exception while trying to connect to telegram API: %(exception)s. Waiting 2 minutes before trying again.", exception=ex))
			time.sleep(120)
			raise ExitThisLoopException()
		if req.status_code != 200:
			self.set_status(gettext("Telegram API responded with code %(status_code)s. Waiting 2 minutes before trying again.", status_code=req.status_code))
			time.sleep(120)
			raise ExitThisLoopException()
		if req.headers['content-type'] != 'application/json':
			self.set_status(gettext("Unexpected Content-Type. Expected: application/json. Was: %(type)s. Waiting 2 minutes before trying again.", type=req.headers['content-type']))
			time.sleep(120)
			raise ExitThisLoopException()
		json = req.json()
		if not json['ok']:
			self.set_status(gettext("Response didn't include 'ok:true'. Waiting 2 minutes before trying again. Response was: %(response)s", response=json))
			time.sleep(120)
			raise ExitThisLoopException()
		if "result" in json and len(json['result']) > 0:
			for entry in json['result']:
				self.set_update_offset(entry['update_id'])
		return json

	# stop the listener
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

class ExitThisLoopException(Exception):
	pass

########################################
########################################
############## THE PLUGIN ##############
########################################
########################################
class TelegramPlugin(octoprint.plugin.EventHandlerPlugin,
                     octoprint.plugin.SettingsPlugin,
                     octoprint.plugin.StartupPlugin,
                     octoprint.plugin.ShutdownPlugin,
                     octoprint.plugin.TemplatePlugin,
                     octoprint.plugin.SimpleApiPlugin,
                     octoprint.plugin.AssetPlugin
                     ):

	def __init__(self,version):
		self.version = float(version)
		# for more init stuff see on_after_startup()
		self.thread = None
		self.bot_url = None
		self.chats = {}
		self.connection_state_str = gettext("Disconnected.")
		self.connection_ok = False
		requests.packages.urllib3.disable_warnings()
		self.updateMessageID = {}
		self.shut_up = {}
		self.send_messages = True
		self.tcmd = None
		self.tmsg = None
		self.sending_okay_minute = None
		self.sending_okay_count = 0
		# initial settings for new chat. See on_after_startup()
		# !!! sync with newUsrDict in on_settings_migrate() !!!
		self.newChat = {}
		# use of emojis see below at method gEmo()
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
			'upload': u'\U0001F4E5',
			'check': u'\U00002705',
			'lamp': u'\U0001F4A1',
			'movie': u'\U0001F3AC',
			'finish': u'\U0001F3C1',
			'cam': u'\U0001F3A6',
			'hooray': u'\U0001F389',
			'error': u'\U000026D4',
			'play': u'\U000025B6',
			'stop': u'\U000025FC'
		}
		self.emojis.update(telegramEmojiDict)
	# all emojis will be get via this method to disable them globaly by the corrosponding setting
	# so if you want to use emojis anywhere use gEmo("...") istead of emojis["..."]
	def gEmo(self,key):
		if self._settings.get(["send_icon"]) and key in self.emojis:
			return self.emojis[key]
		return ""

	# starts the telegram listener thread
	def start_listening(self):
		if self._settings.get(['token']) != "" and self.thread is None:
			self._logger.debug("Starting listener.")
			self.bot_url = "https://api.telegram.org/bot" + self._settings.get(['token'])
			self.bot_file_url = "https://api.telegram.org/file/bot" + self._settings.get(['token'])
			self.thread = TelegramListener(self)
			self.thread.daemon = True
			self.thread.start()

	# stops the telegram listener thread
	def stop_listening(self):
		if self.thread is not None:
			self._logger.debug("Stopping listener.")
			self.thread.stop()
			self.thread = None

	def shutdown(self):
		self._logger.warn("shutdown() running!")
		self.stop_listening()
		self.send_messages = False

	def sending_okay(self):
		# If the count ever goeas above 10, we stop doing everything else and just return False
		# so if this is ever reached, it will stay this way.
		if self.sending_okay_count > 10:
			self._logger.warn("Sent more than 10 messages in the last minute. Shutting down...")
			self.shutdown()
			return False

		if self.sending_okay_minute != datetime.datetime.now().minute:
			self.sending_okay_minute = datetime.datetime.now().minute
			self.sending_okay_count = 1
		else:
			self.sending_okay_count += 1

		return True

##########
### Asset API
##########

	def get_assets(self):
		return dict(js=["js/telegram.js"])

##########
### Template API
##########

	def get_template_configs(self):
		return [
			dict(type="settings", name="Telegram", custom_bindings=True)
		]

##########
### Wizard API
##########

	def is_wizard_required(self):
		return self._settings.get(["token"]) is ""

	def get_wizard_version(self):
		return 1
		# Wizard version numbers used in releases
		# < 1.4.2 : no wizard
		# 1.4.2 : 1
		# 1.4.3 : 1

##########
### Startup/Shutdown API
##########

	def on_after_startup(self):
		self.set_log_level()
		self._logger.addFilter(TelegramPluginLoggingFilter())
		self.tcmd = TCMD(self)
		self.tmsg = TMSG(self) # Notification Message Handler class. called only by on_event()
		# initial settings for new chat.
		# !!! sync this dict with newUsrDict in on_settings_migrate() !!!
		self.newChat = {
			'private': True,
			'title': "[UNKNOWN]",
			'accept_commands' : False,
			'send_notifications' : False,
			'new': True,
			'type': '',
			'allow_users': False,
			'commands': {k: False for k,v in self.tcmd.commandDict.iteritems()},
			'notifications': {k: False for k,v in telegramMsgDict.iteritems()}
			}
		self.chats = self._settings.get(["chats"])
		self.start_listening()
		self.track_action("started")
		# Delete user profile photos if user doesn't exist anymore
		for f in os.listdir(self.get_plugin_data_folder()+"/img/user"):
			fcut = f.split('.')[0][3:]
			self._logger.debug("Testing Pic ID " + str(fcut))
			if fcut not in self.chats:
				self._logger.debug("Removing pic" +fcut+".jpg")
				try:
					os.remove(self.get_plugin_data_folder()+"/img/user/"+f)
				except OSError:
					pass
		#Update user profile photos
		for key in self.chats:
			try:
				if key is not 'zBOTTOMOFCHATS':
					kwargs = {}
					kwargs['chat_id'] = int(key)
					t = threading.Thread(target=self.get_usrPic, kwargs=kwargs)
					t.daemon = True
					t.run()
			except Exception:
				pass

	def on_startup(self, host, port):
		try:
			self.tcmd.port = port
			#self.main.tcmd.port = port
		except Exception as ex:
			self._logger.error("Exception on_startup: "+ str(ex) )
		

	def on_shutdown(self):
		self.on_event("PrinterShutdown",{})
		self.stop_listening()

##########
### Settings API
##########

	def get_settings_version(self):
		return 5
		# Settings version numbers used in releases
		# < 1.3.0: no settings versioning
		# 1.3.0 : 1
		# 1.3.1 : 2
		# 1.3.2 : 2
		# 1.3.3 : 2
		# 1.4.0 : 3
		# 1.4.1 : 3
		# 1.4.2 : 3
		# 1.4.3 : 4
		# 1.5.1 : 5 (PauseForUser)

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
			send_icon = True,
			image_not_connected = True,
			gif_not_connected = False, #GWE 05/05/19,
			send_gif = False, #giloser 12/08/2019,
			multicam = False,
			scale_gif=0,
			delay_img_gif=.5,
			number_img_gif=20,
			frame_img_gif=15,
			fileOrder = False
		)

	def get_settings_preprocessors(self):
		return dict(), dict(
			notification_height=lambda x: float(x),
			notification_time=lambda x: int(x)
		)

	def on_settings_migrate(self, target, current=None):
		self._logger.setLevel(logging.DEBUG)
		self._logger.debug("MIGRATE DO")
		tcmd = TCMD(self)
		# initial settings for new chat.
		# !!! sync this dict with newChat in on_after_startup() !!!
		newUsrDict = {
			'private': True,
			'title': "[UNKNOWN]",
			'accept_commands' : False,
			'send_notifications' : False,
			'new': False,
			'type': '',
			'allow_users': False,
			'commands': {k: False for k,v in tcmd.commandDict.iteritems()},
			'notifications': {k: False for k,v in telegramMsgDict.iteritems()}
			}

		##########
		### migrate from old plugin Versions < 1.3 (old versions had no settings version check)
		##########
		chats = {k: v for k, v in self._settings.get(['chats']).iteritems() if k != 'zBOTTOMOFCHATS'}
		self._logger.debug("LOADED CHATS: " + str(chats))
		self._settings.set(['chats'], {})
		if current is None or current < 1:
			########## Update Chats
			# there shouldn't be any chats, but maybe somone had installed any test branch.
			# Then we have to check if all needed settings are populated
			for chat in chats:
				for setting in newUsrDict:
					if setting not in chats[chat]:
						if setting == "commands":
							chats[chat]['commands'] = {k: False for k,v in tcmd.commandDict.iteritems() if 'bind_none' not in v}
						elif setting == "notifications":
							chats[chat]['notifications'] = {k: False for k,v in telegramMsgDict.iteritems()}
						else:
							chats[chat][setting] = False
			########## Is there a chat from old single user plugin version?
			# then migrate it into chats
			chat = self._settings.get(["chat"])
			if chat is not None:
				self._settings.set(["chat"], None)
				data = {}
				data.update(newUsrDict)
				data['private'] = True
				data['title'] = "[UNKNOWN]"
				#try to get infos from telegram by sending a "you are migrated" message
				try:
					message = {}
					message['text'] = "The OctoPrint Plugin " + self._plugin_name + " has been updated to new Version "+self._plugin_version+ ".\n\nPlease open your " + self._plugin_name + " settings in OctoPrint and set configurations for this chat. Until then you are not able to send or receive anything useful with this Bot.\n\nMore informations on: https://github.com/fabianonline/OctoPrint-Telegram"
					message['chat_id'] = chat
					message['disable_web_page_preview'] = True
					r = requests.post("https://api.telegram.org/bot" + self._settings.get(['token']) + "/sendMessage", data =  message)
					r.raise_for_status()
					if r.headers['content-type'] != 'application/json':
						raise Exception("invalid content-type")
					json = r.json()
					if not json['ok']:
						raise Exception("invalid request")
					chat = json['result']['chat']
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
				except Exception as ex:
					self._logger.debug("ERROR migrating chat. Done with defaults private=true,title=[UNKNOWN] : " + str(ex))
				# place the migrated chat in chats
				chats.update({str(chat['id']): data})
			self._logger.debug("MIGRATED Chats: " + str(chats))
			########## Update messages. Old text will be taken to new structure
			messages = self._settings.get(['messages'])
			msgOut = {}
			for msg in messages:
				if msg == 'TelegramSendNotPrintingStatus':
					msg2 = 'StatusNotPrinting'
				elif msg == 'TelegramSendPrintingStatus':
					msg2 = 'StatusPrinting'
				else:
					msg2 = msg
				if type(messages[msg]) is not type({}):
					newMsg = telegramMsgDict[msg2].copy()
					newMsg['text'] = str(messages[msg])
					msgOut.update({msg2: newMsg})
				else:
					msgOut.update({msg2: messages[msg]})
			self._settings.set(['messages'], msgOut)
			########## Delete old settings
			self._settings.set(["message_at_startup"], None)
			self._settings.set(["message_at_shutdown"], None)
			self._settings.set(["message_at_print_started"], None)
			self._settings.set(["message_at_print_done"], None)
			self._settings.set(["message_at_print_failed"], None)

		##########
		### Migrate to new command/notification settings version.
		### This should work on all future versions. So if you add/del
		### some commands/notifications, then increment settings version counter
		### in  get_settings_version(). This will trigger octoprint to update settings
		##########
		if current is None or current < target:
			# first we have to check if anything has changed in commandDict or telegramMsgDict
			# then we have to update user comamnd or notification settings
			if chats is not None and chats is not {}:
				# this for loop updates commands and notifications settings items of chats
				# if there are changes in commandDict or telegramMsgDict
				for chat in chats:
					# handle renamed commands
					if '/list' in chats[chat]['commands']:
						chats[chat]['commands'].update({'/files':chats[chat]['commands']['/list']})
					if '/imsorrydontshutup' in chats[chat]['commands']:
						chats[chat]['commands'].update({'/dontshutup':chats[chat]['commands']['/imsorrydontshutup']})
					if 'type' not in chats[chat]:
						chats[chat].update({'type': 'PRIVATE' if chats[chat]['private'] else 'GROUP'})
					delCmd = []
					# collect remove 'bind_none' commands
					for cmd in tcmd.commandDict:
						if cmd in chats[chat]['commands'] and 'bind_none' in tcmd.commandDict[cmd]:
							delCmd.append(cmd)
					# collect Delete commands from settings if they don't belong to commandDict anymore
					for cmd in chats[chat]['commands']:
						if cmd not in tcmd.commandDict:
							delCmd.append(cmd)
					# finally delete commands
					for cmd in delCmd:
						del chats[chat]['commands'][cmd]
					# If there are new commands in comamndDict, add them to settings
					for cmd in tcmd.commandDict:
						if cmd not in chats[chat]['commands']:
							if 'bind_none' not in tcmd.commandDict[cmd]:
								chats[chat]['commands'].update({cmd: False})
					# Delete notifications from settings if they don't belong to msgDict anymore
					delMsg = []
					for msg in chats[chat]['notifications']:
						if msg not in telegramMsgDict:
							delMsg.append(msg)
					for msg in delMsg:
						del chats[chat]['notifications'][msg]
					# If there are new notifications in msgDict, add them to settings
					for msg in telegramMsgDict:
						if msg not in chats[chat]['notifications']:
							chats[chat]['notifications'].update({msg: False})
				self._settings.set(['chats'],chats)
			########## if anything changed in telegramMsgDict, we also have to update settings for messages
			messages = self._settings.get(['messages'])
			if messages is not None and messages is not {}:
				# this for loop deletes items from messages settings
				# if they dont't belong to telegramMsgDict anymore
				delMsg = []
				for msg in messages:
					if msg not in telegramMsgDict:
						delMsg.append(msg)
				for msg in delMsg:
					del messages[msg]
				# this for loop adds new message settings from telegramMsgDict to settings
				for msg in telegramMsgDict:
					if msg not in messages:
						messages.update({msg: telegramMsgDict[msg]})
					elif 'combined' not in messages[msg]:
						messages[msg].update({'combined' : True})

				self._settings.set(['messages'],messages)
				self._logger.debug("MESSAGES: " + str(self._settings.get(['messages'])))


		if current is not None:
			if current < 2:
				if chats is not None and chats is not {}:
					for chat in chats:
						if os.path.isfile(self.get_plugin_data_folder()+"/pic"+chat+".jpg"):
							os.remove(self.get_plugin_data_folder()+"/pic"+chat+".jpg")


		##########
		### save the settings after Migration is done
		##########
		self._logger.debug("SAVED Chats: " + str(self._settings.get(['chats'])))
		try:
			self._settings.save()
		except Exception as ex:
			self._logger.error("MIGRATED Save failed - " + str(ex))
		self._logger.debug("MIGRATED Saved")


	def on_settings_save(self, data):
		# Remove 'new'-flag and apply bindings for all chats
		if 'chats' in data and data['chats']:
			delList = []
			for key in data['chats']:
				if 'new' in data['chats'][key] or 'new' in data['chats'][key]:
					data['chats'][key]['new'] = False
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
		# Check token for right format
		if 'token' in data:
			data['token'] = data['token'].strip()
			if not re.match("^[0-9]+:[a-zA-Z0-9_\-]+$", data['token']):
				self._logger.error("Not saving token because it doesn't seem to have the right format.")
				self.connection_state_str = gettext("The previously entered token doesn't seem to have the correct format. It should look like this: 12345678:AbCdEfGhIjKlMnOpZhGtDsrgkjkZTCHJKkzvjhb")
				data['token'] = ""
		old_token = self._settings.get(["token"])
		# Update Tracking
		if 'tracking_activated' in data and not data['tracking_activated']:
			data['tracking_token'] = None
		# Now save settings
		octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
		self.set_log_level()
		# Reconnect on new token
		# Will stop listener on invalid token
		if 'token' in data:
			if data['token']!=old_token:
				self.stop_listening()
			if data['token']!="":
				self.start_listening()
			else:
				self.connection_state_str = gettext("No token given.")

	def on_settings_load(self):
		data = octoprint.plugin.SettingsPlugin.on_settings_load(self)

		# only return our restricted settings to admin users - this is only needed for OctoPrint <= 1.2.16
		restricted = (("token", None), ("tracking_token", None), ("chats", dict()))
		for r, v in restricted:
			if r in data and (current_user is None or current_user.is_anonymous() or not current_user.is_admin()):
				data[r] = v

		return data

	def get_settings_restricted_paths(self):
		# only used in OctoPrint versions > 1.2.16
		return dict(admin=[["token"], ["tracking_token"], ["chats"]])

##########
### Softwareupdate API
##########

	def get_update_information(self, *args, **kwargs):
		return dict(
			telegram=dict(
				displayName=self._plugin_name,
				displayVersion=self._plugin_version,
				type="github_release",
				current=self._plugin_version,
				user="fabianonline",
				repo="OctoPrint-Telegram",
				pip="https://github.com/fabianonline/OctoPrint-Telegram/releases/download/{target_version}/release.zip"
			)
		)

##########
### EventHandler API
##########

	def on_event(self, event, payload, **kwargs):
		try:
			self._logger.debug("self.tmsg = " + str(self.tmsg))
			# if we know the event, start handler
			if event in self.tmsg.msgCmdDict:
				self._logger.debug("Got an event: " + event + " Payload: " + str(payload))
				# Start event handler
				self.tmsg.startEvent(event, payload, **kwargs)
			else:
				# return as fast as possible
				return
		except Exception as e:
			self._logger.debug("Exception: " + str(e))

##########
### SimpleApi API
##########

	def get_api_commands(self):
		return dict(
			testToken=["token"],
			delChat=["ID"]
		)

	def on_api_get(self, request):
		# got an user-update with this command. so lets do that
		if 'id' in request.args and 'cmd' in request.args and 'note' in request.args  and 'allow' in request.args:
			self.chats[request.args['id']]['accept_commands'] = self.str2bool(str(request.args['cmd']))
			self.chats[request.args['id']]['send_notifications'] = self.str2bool(str(request.args['note']))
			self.chats[request.args['id']]['allow_users'] = self.str2bool(str(request.args['allow']))
			self._logger.debug("Updated chat - " + str(request.args['id']))
		elif 'bindings' in request.args:
			bind_text = {}
			for key in {k: v for k, v in telegramMsgDict.iteritems() if 'bind_msg' in v }:
				if telegramMsgDict[key]['bind_msg'] in bind_text:
					bind_text[telegramMsgDict[key]['bind_msg']].append(key)
				else:
					bind_text[telegramMsgDict[key]['bind_msg']] = [key]
			return json.dumps({
				'bind_cmd':[k for k, v in self.tcmd.commandDict.iteritems() if 'bind_none' not in v ],
				'bind_msg':[k for k, v in telegramMsgDict.iteritems() if 'bind_msg' not in v ],
				'bind_text':bind_text,
				'no_setting':[k for k, v in telegramMsgDict.iteritems() if 'no_setting' in v ]})

		retChats = {k: v for k, v in self.chats.iteritems() if 'delMe' not in v and k != 'zBOTTOMOFCHATS'}
		for chat in retChats:
			if os.path.isfile(self.get_plugin_data_folder()+"/img/user/pic" +chat+".jpg"):
				retChats[chat]['image'] = "/plugin/telegram/img/user/pic" +chat+".jpg"
			elif int(chat) < 0:
				retChats[chat]['image'] = "/plugin/telegram/img/static/group.jpg"
			else:
				retChats[chat]['image'] = "/plugin/telegram/img/static/default.jpg"

		return json.dumps({'chats':retChats, 'connection_state_str':self.connection_state_str, 'connection_ok':self.connection_ok})

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
		# delete a chat (will not be removed and show up again on octorint restart
		# if save button is not pressed on settings dialog)
		elif command=="delChat":
			strId = str(data['ID'])
			if strId in self.chats:
				del self.chats[strId]
				# do self._settings.save() here???????
			return json.dumps({'chats':{k: v for k, v in self.chats.iteritems() if 'delMe' not in v and k != 'zBOTTOMOFCHATS'}, 'connection_state_str':self.connection_state_str, 'connection_ok':self.connection_ok})

##########
### Telegram API-Functions
##########

	def send_msg(self, message, **kwargs):
		if not self.send_messages:
			return

		kwargs['message'] = message
		try:
			# If it's a regular event notification
			if 'chatID' not in kwargs and 'event' in kwargs:
				self._logger.debug("Send_msg() found event: " + str(kwargs['event']))
				for key in self.chats:
					if key != 'zBOTTOMOFCHATS':
						if self.chats[key]['notifications'][kwargs['event']] and (key not in self.shut_up or self.shut_up[key]==0) and self.chats[key]['send_notifications']:
							kwargs['chatID'] = key
							t = threading.Thread(target=self._send_msg, kwargs = kwargs).run()
			# Seems to be a broadcast
			elif 'chatID' not in kwargs:
				for key in self.chats:
					kwargs['chatID'] = key
					t = threading.Thread(target=self._send_msg, kwargs = kwargs).run()
			# This is a 'editMessageText' message
			elif 'msg_id' in kwargs and kwargs['msg_id'] is not "" and  kwargs['msg_id'] is not None:
				t = threading.Thread(target=self._send_edit_msg, kwargs = kwargs).run()
			# direct message or event notification to a chat_id
			else:
				t = threading.Thread(target=self._send_msg, kwargs = kwargs).run()
		except Exception as ex:
			self._logger.debug("Caught an exception in send_msg(): " + str(ex))


	# this method is used to update a message text of a sent message
	# the sent message had to have no_markup = true when calling send_msg() (otherwise it would not work)
	# by setting no_markup = true we got a messageg_id on sending the message which is saved in selfupdateMessageID
	# if this message_id is passed in msg_id to send_msg() then this method will be called
	def _send_edit_msg(self,message="",msg_id="",chatID="", responses= None, inline=True, markup=None,delay=0, **kwargs):
		if not self.send_messages:
			return

		if delay > 0:
			time.sleep(delay)
		try:
			self._logger.debug("Sending a message UPDATE: " + message.replace("\n", "\\n") + " chatID= " + str(chatID))
			data = {}
			data['text'] = message
			data['message_id'] = msg_id
			data['chat_id'] = int(chatID)
			if markup is not None:
				if "HTML" in markup  or "Markdown" in markup:
					data["parse_mode"] = markup
			if responses and inline:
				myArr = []
				for k in responses:
					myArr.append(map(lambda x: {"text":x[0],"callback_data":x[1]}, k))
				keyboard = {'inline_keyboard':myArr}
				data['reply_markup'] = json.dumps(keyboard)
			self._logger.debug("SENDING UPDATE: " + str(data))
			req = requests.post(self.bot_url + "/editMessageText", data=data)
			if req.headers['content-type'] != 'application/json':
				self._logger.debug(gettext("Unexpected Content-Type. Expected: application/json. Was: %(type)s. Waiting 2 minutes before trying again.", type=req.headers['content-type']))
				return
			myJson = req.json()
			self._logger.debug("REQUEST RES: "+str(myJson))
			if inline:
				self.updateMessageID[chatID] = msg_id
		except Exception as ex:
			self._logger.debug("Caught an exception in _send_edit_msg(): " + str(ex))

	def _send_msg(self, message="", with_image=False,with_gif=False,responses=None, delay=0, inline = True, chatID = "", markup=None, showWeb=False, **kwargs):
		if not self.send_messages:
			return

		if delay > 0:
			time.sleep(delay)
		try:
			if with_image:
				if 'event' in kwargs and not self._settings.get(["messages",kwargs['event'],"combined"]):
					args = locals()
					del args['kwargs']['event']
					del args['self']
					args['message'] = ""
					self._logger.debug("Sending image...")
					t = threading.Thread(target=self._send_msg, kwargs = args).run()
					args['message'] = message
					args['with_image'] = False
					self._logger.debug("Sending text...")
					t = threading.Thread(target=self._send_msg, kwargs = args).run()
					return
			
			self._logger.info("Sending a message: " + message.replace("\n", "\\n") + " with_image=" + str(with_image) + " with_gif=" + str(with_gif) + " chatID= " + str(chatID))
			data = {}
			# Do we want to show web link previews?
			data['disable_web_page_preview'] = not showWeb
			# Do we want the message to be parsed in any markup?
			if markup is not None:
				if "HTML" in markup  or "Markdown" in markup:
					data["parse_mode"] = markup
			if responses:
				myArr = []
				for k in responses:
					myArr.append(map(lambda x: {"text":x[0],"callback_data":x[1]}, k))
				keyboard = {'inline_keyboard':myArr}
				data['reply_markup'] = json.dumps(keyboard)

			image_data = None
			data['chat_id'] = chatID
			if with_gif : #giloser 05/05/19
				try:
					self._logger.info("Will try to create a gif ")
					sendOneInLoop = False
					#requests.get(self.main.bot_url + "/sendChatAction", params = {'chat_id': chat_id, 'action': 'upload_document'})
					if self._plugin_manager.get_plugin("multicam") and self._settings.get(["multicam"]):
						try:
							curr = self._settings.global_get(["plugins","multicam","multicam_profiles"])
							self._logger.error("multicam_profiles : "+ str(curr))
							for li in curr: 
								try:
									self._logger.error("multicam profile : "+ str(li))
									url = li.get("URL")
									self._logger.error("multicam URL : "+ str(url))
									ret = self.create_gif_new(chatID,0,url)
									if ret != "":
										if not sendOneInLoop:
											self.send_file(chatID, ret,message)
										else:
											self.send_file(chatID, ret,"")											
										sendOneInLoop = True
								except Exception as ex:
									self._logger.error("Exception loop multicam URL to create gif: "+ str(ex) )
						except Exception as ex:
							self._logger.error("Exception occured on getting multicam options: "+ str(ex) )
					else:
						ret = self.create_gif_new(chatID,0,0)
					
					if ret == "":
						ret = self.create_gif_new(chatID,0,0)

					if ret != "" and not sendOneInLoop:
						self.send_file(chatID, ret,message)
					#ret = self.create_gif_new(chatID,0,0)
					#if ret != "":
					#	self.send_file(chatID, ret,message)
				except Exception as ex:
					self._logger.info("Caught an exception trying send gif: " + str(ex))
					self.main.send_msg(self.gEmo('dizzy face') + " Problem creating gif, please check log file", chatID=chatID)#and make sure you have installed libav-tools or ffmpeg with command : `sudo apt-get install libav-tools`",chatID=chat_id)
			else:
				if with_image:
					try:
						image_data = self.take_image(self._settings.global_get(["webcam", "snapshot"]))
					except Exception as ex:
						self._logger.info("Caught an exception trying take image: " + str(ex))

				self._logger.debug("data so far: " + str(data))
				if with_image:
					self._logger.debug("image data so far: " + str(image_data))

				if (not image_data or 'html' in image_data) and with_image:
					message = "[ERR GET IMAGE]\n\n" + message
					image_data = None

				r = None
				
				if image_data:
					self._logger.debug("Sending with image.. " + str(chatID))
					files = {'photo':("image.jpg", image_data)}
					self._logger.debug("files so far: " + str(files))
					if message is not "":
						data['caption'] = message
					r = requests.post(self.bot_url + "/sendPhoto", files=files, data=data)
					
					self._logger.debug("Sending finished. " + str(r.status_code))
				else:
					self._logger.debug("Sending without image.. " + str(chatID))
					data['text'] = message
					r =requests.post(self.bot_url + "/sendMessage", data=data)
					self._logger.debug("Sending finished. " + str(r.status_code))

				if with_image:
					try:
						files={}
						sendOneInLoop = False
						if self._plugin_manager.get_plugin("multicam") and self._settings.get(["multicam"]):
							try:
								curr = self._settings.global_get(["plugins","multicam","multicam_profiles"])
								self._logger.debug("multicam_profiles : "+ str(curr))
								for li in curr: 
									try:
										self._logger.debug("multicam profile:  "+ str(li))
										snapshot_url = li.get("URL")
										self._logger.debug("multicam url :  "+ str(snapshot_url))

										defsnap = self._settings.global_get(["webcam", "snapshot"])
										defstream = self._settings.global_get(["webcam", "stream"])
										streamname = defstream.rsplit('/', 1).pop()
										snapname = defsnap.rsplit('/', 1).pop()
										if streamname in snapshot_url:
											self._logger.debug( str(streamname) + " found so should be replaced by " + str(snapname) )
											snapshot_url = snapshot_url.replace(streamname,snapname)

										self._logger.debug("Snapshot URL: " + str(snapshot_url))
										if snapshot_url != self._settings.global_get(["webcam", "snapshot"]):
											image_data = self.take_image(snapshot_url)
											if image_data != "":
												self._logger.debug("Image for  " + str(li.get("name")))
												files = {'photo':("image.jpg", image_data)}
												data2 = data
												data2['caption'] = ""
												r = requests.post(self.bot_url + "/sendPhoto", files=files, data=data2)
											else:
												self._logger.debug("no image  " + str(li.get("name")))
										else:
											self._logger.debug("url is the same as the one from octoprint " )
												
									except Exception as ex:
										self._logger.error("Exception loop multicam URL to create image: "+ str(ex) )
							except Exception as ex:
								self._logger.error("Exception occured on getting multicam options: "+ str(ex) )
					except Exception as ex:
						self._logger.error("Exception occured on getting multicam plugin: "+ str(ex) )

				if r is not None and inline:
					r.raise_for_status()
					myJson = r.json()
					if not myJson['ok']:
						raise NameError("ReqErr")
					if 'message_id' in myJson['result']:
						self.updateMessageID[chatID] = myJson['result']['message_id']

			
		except Exception as ex:
			self._logger.debug("Caught an exception in _send_msg(): " + str(ex))

	def send_file(self,chat_id,path,text):
		if not self.send_messages:
			return

		try:
			requests.get(self.bot_url + "/sendChatAction", params = {'chat_id': chat_id, 'action': 'upload_document'})
			files = {'document': open(path, 'rb')}
			r = requests.post(self.bot_url + "/sendDocument", files=files, data={'chat_id':chat_id,'caption':text})
		except Exception as ex:
			pass

	def send_editMessageMedia(self,chat_id,path,message_id):
		if not self.send_messages:
			return
		try:
			requests.get(self.bot_url + "/sendChatAction", params = {'chat_id': chat_id, 'action': 'upload_document'})
			files = {'document': open(path, 'rb')}
			r = requests.post(self.bot_url + "/editMessageMedia", files=files, data={'chat_id':chat_id,'message_id':message_id})
		except Exception as ex:
			pass

	def delete_msg(self,chat_id,message_id):
		try:
			r = requests.post(self.bot_url + "/deleteMessage", data={'chat_id':chat_id,'message_id':message_id})
		except Exception as ex:
			pass

	def send_video(self, message, video_file):
		if not self.send_messages:
			return

		files = {'video': open(video_file, 'rb')}
		#r = requests.post(self.bot_url + "/sendVideo", files=files, data={'chat_id':self._settings.get(["chat"]), 'caption':message})
		self._logger.debug("Sending finished. " + str(r.status_code) + " " + str(r.content))

	def get_file(self, file_id):
		if not self.send_messages:
			return

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

	def get_usrPic(self,chat_id, file_id=""):
		if not self.send_messages:
			return

		self._logger.debug("Requesting Profile Photo for chat_id: " + str(chat_id))
		try:
			if file_id == "":
				if int(chat_id) < 0:
					self._logger.debug("Not able to load group photos. "+ str(chat_id)+" EXIT")
					return
				self._logger.debug("requests.get("+self.bot_url + "/getUserProfilePhotos")
				r = requests.get(self.bot_url + "/getUserProfilePhotos", params = {'limit': 1, "user_id": chat_id})
				r.raise_for_status()
				data = r.json()
				if not "ok" in data:
					raise Exception(_("Telegram didn't respond well to getUserProfilePhoto "+ str(chat_id)+". The response was: %(response)s", response=r.text))
				if data['result']['total_count'] < 1:
					self._logger.debug("NO PHOTOS "+ str(chat_id)+". EXIT")
					return
				r = self.get_file(data['result']['photos'][0][0]['file_id'])
			else:
				r = self.get_file(file_id)
			file_name = self.get_plugin_data_folder() + "/img/user/pic" + str(chat_id) + ".jpg"
			img = Image.open(StringIO.StringIO(r))
			img = img.resize((40, 40), PIL.Image.ANTIALIAS)
			img.save(file_name, format="JPEG")
			self._logger.debug("Saved Photo "+ str(chat_id))

		except Exception as ex:
			self._logger.error("Can't load UserImage: " + str(ex))

	def test_token(self, token=None):
		if not self.send_messages:
			return

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

##########
### Helper methods
##########

	def str2bool(self,v):
		return v.lower() in ("yes", "true", "t", "1")

	def set_log_level(self):
		self._logger.setLevel(logging.DEBUG if self._settings.get_boolean(["debug"]) else logging.NOTSET)

# checks if the received command is allowed to execute by the user
	def isCommandAllowed(self, chat_id, from_id, command):
		if 'bind_none' in self.tcmd.commandDict[command]:
			return True
		if command is not None or command is not "":
			if self.chats[chat_id]['accept_commands']:
				if self.chats[chat_id]['commands'][command]:
						return True
				elif int(chat_id) < 0 and self.chats[chat_id]['allow_users']:
					if self.chats[from_id]['commands'][command] and self.chats[from_id]['accept_commands']:
						return True
			elif int(chat_id) < 0 and self.chats[chat_id]['allow_users']:
				if self.chats[from_id]['commands'][command] and self.chats[from_id]['accept_commands']:
						return True
		return False

	# Helper function to handle /editMessageText Telegram API commands
	# see main._send_edit_msg()
	def getUpdateMsgId(self,id):
		uMsgID = ""
		if id in self.updateMessageID:
			uMsgID = self.updateMessageID[id]
			del self.updateMessageID[id]
		return uMsgID

	def take_image(self,snapshot_url=""):
		if snapshot_url == "":
			snapshot_url = self._settings.global_get(["webcam", "snapshot"])

		self._logger.debug("Snapshot URL: " + str(snapshot_url))
		data = None
		if snapshot_url:
			try:
				r = requests.get(snapshot_url,timeout=10)
				data = r.content
			except Exception as e:
				self._logger.error("TimeOut Exception: " + str(e))
				return None
		flipH = self._settings.global_get(["webcam", "flipH"])
		flipV = self._settings.global_get(["webcam", "flipV"])
		rotate= self._settings.global_get(["webcam", "rotate90"])
		self._logger.debug("Image transformations [H:%s, V:%s, R:%s]", flipH, flipV, rotate)
		if data == None:
			return None
		if flipH or flipV or rotate:
			image = Image.open(StringIO.StringIO(data))
			if flipH:
				image = image.transpose(Image.FLIP_LEFT_RIGHT)
			if flipV:
				image = image.transpose(Image.FLIP_TOP_BOTTOM)
			if rotate:
				image = image.transpose(Image.ROTATE_270)
			output = StringIO.StringIO()
			image.save(output, format="JPEG")
			data = output.getvalue()
			output.close()
		return data


	def calculate_ETA(self,printTime = 0):
		try:
			strtime = ""
			strdate = ""
			currentData = self._printer.get_current_data()
			current_time = datetime.datetime.today()
			if not currentData["progress"]["printTimeLeft"]:
				if not printTime == 0:
					self._logger.debug("will do timedelta on printTime: " + str(printTime) )
					finish_time = current_time + datetime.timedelta(0,printTime)
				else:
					return ""
			else:
				self._logger.debug("will do timedelta on currentData['progress']['printTimeLeft']: " + str(currentData["progress"]["printTimeLeft"]) )				
				finish_time = current_time + datetime.timedelta(0,currentData["progress"]["printTimeLeft"])
			strtime = format_time(finish_time)
			strdate = ""
			if finish_time.day > current_time.day:
				if finish_time.day == current_time.day + 1:
					strdate = " Tomorrow"
				else:
					strtime = " " + format_date(finish_time,"EEE d")
		except Exception as ex:
			self._logger.error("An Exception in get final time : " + str(ex) )

		return strtime + strdate

	def create_gif_new(self,chatID,sec=7,stream_url=0):
		i=0
		ret = ""

		try:
			requests.get(self.bot_url + "/sendChatAction", params = {'chat_id': chatID, 'action': 'record_video'})
		#	saveDir = os.getcwd()
		#	os.chdir(self.get_plugin_data_folder()+"/tmpgif")
			outPath = self.get_plugin_data_folder()+"/tmpgif/gif.mp4"
			try:
				os.remove(outPath)
			except Exception as ex:
				self._logger.info("Caught an exception trying clean previous images : " + str(ex))
		#	self._logger.info("will try to save image in path " + os.getcwd())

			params = []
			self._logger.info("test if nice exist")
			if self.TestProgram(['nice','--version']) > 0:
				params = ['nice', '-n', '20']

			self._logger.info("test if cpulimit exist")
			if self.TestProgram(['cpulimit','--help']) <= 0:
				self._logger.info("cpulimit don't exist so send a message to install and exit")
				self.send_msg(self.gEmo('dizzy face') + " Problem creating gif, please check log file, and make sure you have installed cpulimit with following command : `sudo apt-get install cpulimit`",chatID=chatID)
				return ""

			self._logger.info("test if ffmpeg exist")
			if self.TestProgram(['ffmpeg','-h']) <= 0:
				self._logger.info("ffmpeg don't exist so send a message to install and exit")
				self.send_msg(self.gEmo('dizzy face') + " Problem creating gif, please check log file, and make sure you have installed ffmpeg with following command : `sudo apt-get install ffmpeg`",chatID=chatID)
				return ""

			requests.get(self.bot_url + "/sendChatAction", params = {'chat_id': chatID, 'action': 'record_video'})
			os.nice(20) # force this to use less CPU


			fps = 15
			if stream_url == 0:
				stream_url = self._settings.global_get(["webcam", "stream"])
			if "http" not in stream_url:
				stream_url = "http://localhost" +stream_url

			if sec == 0:
				sec = 5#int(self._settings.get(["number_img_gif"]))
			if(sec > 60):
				sec = 60

			if(sec < 1):
				sec = 1

			self._logger.info("sec="+str(sec))
			#timeSec = str(datetime.timedelta(seconds=sec))
			#self._logger.info("timeSec="+timeSec)
			timeSec = 0
			timeSec="00:00:" + str(sec)
			self._logger.info("timeSec="+timeSec)
			#timout = 4*sec
			#ffmpeg -i http://192.168.1.56/webcam/?action=stream -t 00:00:05 -vf scale=320x240 -y  -c:a copy out.mkv
			#params = ['ffmpeg', '-y', '-i' ,stream_url, '-t', "00:00:05",'-c:v','copy', '-c:a' ,'copy']
			params.append('cpulimit')
			params.append( '-l')
			params.append(  '65')
			params.append(  '-f')
			params.append(  '-z')
			params.append(  '--')
			params.append( 'ffmpeg')
			params.append(  '-y' )
			params.append( '-threads')
			params.append( '1')
			params.append(  '-i')
			params.append( stream_url)
			params.append(  '-t')
			params.append(  timeSec)
			params.append( '-c:v')
			params.append( 'mpeg4')
			params.append(  '-c:a' )
			params.append( 'mpeg4')

			#if (str(self._settings.get(["scale_gif"])) == "0"):#scale_gif
			#	scale = ""
			#	scale_opt =""
			#else:
			#	params.append( "-vf")
			#	params.append("scale="+self._settings.get(["scale_gif"]))

			params.append( outPath)

			self._logger.info("will now create the video  " + str(params).strip('[]') )
			requests.get(self.bot_url + "/sendChatAction", params = {'chat_id': chatID, 'action': 'record_video'})

			myproc = Popen(params, shell=False, stdout=PIPE, stderr=PIPE)
			while True:
				if myproc.poll() is not None:
					break
				requests.get(self.bot_url + "/sendChatAction", params = {'chat_id': chatID, 'action': 'record_video'})
				time.sleep(0.5)

			self._logger.info("Finish the video")
			requests.get(self.bot_url + "/sendChatAction", params = {'chat_id': chatID, 'action': 'record_video'})
			ret = outPath
		except Exception as ex:
			self._logger.info("Caught an exception trying create gif general error : " + str(ex))
			self.main.send_msg(self.gEmo('dizzy face') + " Problem creating gif, please check log file ",chatID=chatID)
			ret = ""

		os.nice(0) # use CPU usage to default
		return ret

	def TestProgram(self,name):
		try:
			self._logger.info("test exist program "+str(name).strip('[]'))
			# pipe output to /dev/null for silence
			ret = subprocess.call(name)
			self._logger.info("ret = "+str(ret))
			return ret >= 0

		except OSError:
			return -1
		return 1

	def create_gif(self,chatID,nbImg = 0):  #giloser 05/05/2019
		i=0
		ret = 0
		try:

			if nbImg == 0:
				nbImg = int(self._settings.get(["number_img_gif"]))

			wait_b_img =  self._settings.get(["delay_img_gif"])

			frame = self._settings.get(["frame_img_gif"]) #10
				#requests.get(self.main.bot_url + "/sendChatAction", params = {'chat_id': chat_id, 'action': 'upload_document'})
			requests.get(self.bot_url + "/sendChatAction", params = {'chat_id': chatID, 'action': 'record_video'})
			os.nice(20) # force this to use less CPU
			soft, hard = resource.getrlimit(resource.RLIMIT_CPU)
			self._logger.info("RLIMIT_CPU soft " + str(soft)  + " | hard "+ str(hard))
			soft, hard = resource.getrlimit(resource.RLIMIT_CORE)
			self._logger.info("RLIMIT_CORE soft " + str(soft)  + " | hard "+ str(hard))
			soft, hard = resource.getrlimit(resource.RLIMIT_DATA)
			self._logger.info("RLIMIT_DATA soft " + str(soft)  + " | hard "+ str(hard))
			#saveDir = os.getcwd()
			#os.chdir(self.get_plugin_data_folder()+"/tmpgif")
			#try:
			#	#self._file_manager.remove_folder(self.get_plugin_data_folder() , "/tmpgif", recursive=True)
			#	list_files = glob.glob('Gif_Telegram_*.jpg')
			#	for filename in list_files:
			#		os.remove(filename)
			#	os.remove(self.get_plugin_data_folder()+"/tmpgif/gif.mp4")
			#except Exception as ex:
			#	self._logger.info("Caught an exception trying clean previous images : " + str(ex))
			#self._logger.info("will try to save image in path " + os.getcwd())
			#try:
			#	self._file_manager.add_folder(self.get_plugin_data_folder() , "/tmpgif", ignore_existing=True)
			#except Exception as ex:
			#	self._logger.info("Caught an exception trying create tmpgif folder : " + str(ex))
			frames = []
			while(i<=nbImg):
				self._logger.info("image number " + str(i)  + " of "+ str(nbImg))
				data = self.take_image(self._settings.global_get(["webcam", "snapshot"]))
				try:
					requests.get(self.bot_url + "/sendChatAction", params = {'chat_id': chatID, 'action': 'record_video'})
					#self._file_manager.add_file(self.get_plugin_data_folder() + "/tmpgif",'Test_Telegram_%02d.jpg' % i,data,allow_overwrite=True)
					image = Image.open(StringIO.StringIO(data))
					image.thumbnail((320, 240))
					frames.append(image)
					#image.save('Gif_Telegram_%02d.jpg' % i, 'JPEG')
				except Exception as ex:
					self._logger.info("Caught an exception trying create gif() in loop as open of save image : " + str(ex))
					ret = -2
				self._logger.info("will sleep for  " + str(wait_b_img))
				time.sleep(float(wait_b_img)) #giloser 19/05/2019 add sleep to better gif
				i+=1
			try:

				frames[0].save(self.get_plugin_data_folder() + '/tmpgif/gif.gif', format='GIF', append_images=frames[1:], save_all=True, duration=100, loop=0)

				#params = []
				##ffmpeg -i http://192.168.1.56/webcam/?action=stream -t 00:00:05 -vf scale=320x240 -y  -c:a copy out.mkv
#				#params = ['nice','-n','20','cpulimit','-l','50','-f','-z','--','ffmpeg', '-y', '-i' ,self.get_plugin_data_folder() + '/tmpgif/Gif_Telegram_%2d.jpg', '-crf', '20', '-g' ,'15']
				#params.append('-r')
				#params.append(str(self._settings.get(["frame_img_gif"])))

				#if (str(self._settings.get(["scale_gif"])) == "0"):#scale_gif
				#	scale = ""
				#	scale_opt =""
				#else:
				#	params.append( "-vf")
				#	params.append("scale="+self._settings.get(["scale_gif"]))


				#params.append( self.get_plugin_data_folder() + '/tmpgif/gif.mp4')

				#self._logger.info("finish the image will now create the video  " + str(params).strip('[]') )# 'nice -n 20 cpulimit -l 50 -f -z -- ffmpeg -r 10 -y -i' +self.get_plugin_data_folder() + '/tmpgif/Gif_Telegram_%2d.jpg -crf 20 -g 15 ' +scale_opt+ ' ' +scale + ' ' + self.get_plugin_data_folder() + '/tmpgif/gif.mp4')
				#requests.get(self.bot_url + "/sendChatAction", params = {'chat_id': chatID, 'action': 'record_video'})
				#subprocess.check_call(params)
#				subprocess.check_call(['nice','-n','20','cpulimit','-l','50','-f','-z','--','ffmpeg', '-r', '10', '-y', '-i' ,self.get_plugin_data_folder() + '/tmpgif/Gif_Telegram_%2d.jpg', '-crf', '20', '-g' ,'15', self.get_plugin_data_folder() + '/tmpgif/gif.mp4'])
				#self._logger.info("video created ")

			except Exception as ex:
				self._logger.info("Caught an exception trying create mp4 with ffmpeg : " + str(ex))
				try:
					requests.get(self.bot_url + "/sendChatAction", params = {'chat_id': chatID, 'action': 'record_video'})
					subprocess.check_call(['nice','-n','20','cpulimit','-l','50','-f','-z','--','avconv', '-r', '10', '-y', '-i' ,self.get_plugin_data_folder() + '/tmpgif/Gif_Telegram_%2d.jpg', '-crf', '20', '-g' ,'15',scale_opt,scale, self.get_plugin_data_folder() + '/tmpgif/gif.mp4'])
				except Exception as ex:
					self._logger.info("Caught an exception trying create mp4 with ffmpeg : " + str(ex))
					try:
						requests.get(self.bot_url + "/sendChatAction", params = {'chat_id': chatID, 'action': 'record_video'})
						subprocess.call(['nice','-n','20','cpulimit','-l','50','-f','-z','--','ffmpeg','-r 10','-y','-i',scale_opt,scale,self.get_plugin_data_folder() + '/tmpgif/Gif_Telegram_%02d.jpg',self.get_plugin_data_folder() + '/tmpgif/gif.mp4'])
					except Exception as ex:
						self._logger.info("Caught an exception trying create mp4 2 : " + str(ex))
						ret = -1
		#subprocess.call(['avconv -r 3 -y -i Test_Telegram_%02d.jpg -r 3 -vcodec libx264 -vf  scale=1280:720 timelapse.mp4'])
		#avconv -r 10 -y -i Test_Telegram_%02d.jpg -r 3 -vcodec libx264 -vf  scale=1280:720 timelapse.mp4
		except Exception as ex:
			self._logger.info("Caught an exception trying create gif general error : " + str(ex))
			ret = -3
		#os.chdir(saveDir)
		self._logger.info("finish creating gif return = " + str(ret))
		os.nice(0) # use CPU usage to default
		return ret


	def track_action(self, action):
		if not self._settings.get_boolean(["tracking_activated"]):
			return
		if self._settings.get(["tracking_token"]) is None:
			token = "".join(random.choice("abcdef0123456789") for i in xrange(16))
			self._settings.set(["tracking_token"], token)
		params = {
			'idsite': '3',
			'rec': '1',
			'url': 'http://octoprint-telegram/'+action,
			'action_name': ("%20/%20".join(action.split("/"))),
			'_id': self._settings.get(["tracking_token"]),
			'uid': self._settings.get(["tracking_token"]),
			'cid': self._settings.get(["tracking_token"]),
			'send_image': '0',
			'_idvc': '1',
			'dimension1': str(self._plugin_version)
		}
		t = threading.Thread(target=requests.get, args=("http://piwik.schlenz.ruhr/piwik.php",), kwargs={'params': params})
		t.daemon = True
		t.run()

	def route_hook(self, server_routes, *args, **kwargs):
		from octoprint.server.util.tornado import LargeResponseHandler, UrlProxyHandler, path_validation_factory
		from octoprint.util import is_hidden_path
		if not os.path.exists(self.get_plugin_data_folder()+"/img"):
			os.mkdir(self.get_plugin_data_folder()+"/img")
		if not os.path.exists(self.get_plugin_data_folder()+"/img/user"):
			os.mkdir(self.get_plugin_data_folder()+"/img/user")
		if not os.path.exists(self.get_plugin_data_folder()+"/tmpgif"): #GWE 05/05/2019 add a folder temp to put image used in gif
			os.mkdir(self.get_plugin_data_folder()+"/tmpgif")
		if not os.path.exists(self.get_plugin_data_folder()+"/tmpzip"): #GWE 05/05/2019 add a folder temp to put image used in gif
			os.mkdir(self.get_plugin_data_folder()+"/tmpzip")
		return [
				(r"/img/user/(.*)", LargeResponseHandler, dict(path=self.get_plugin_data_folder() + r"/img/user/", as_attachment=True,allow_client_caching =False)),
				(r"/img/static/(.*)", LargeResponseHandler, dict(path=self._basefolder + "/static/img/", as_attachment=True,allow_client_caching =True))
				]

########################################
########################################
### Some methods to check version and
### get the right implementation
########################################
########################################

# copied from pluginmanager plugin
def _is_octoprint_compatible(compatibility_entries):
	"""
	Tests if the current octoprint_version is compatible to any of the provided ``compatibility_entries``.
	"""

	octoprint_version = _get_octoprint_version()
	for octo_compat in compatibility_entries:
		if not any(octo_compat.startswith(c) for c in ("<", "<=", "!=", "==", ">=", ">", "~=", "===")):
			octo_compat = ">={}".format(octo_compat)

		s = next(pkg_resources.parse_requirements("OctoPrint" + octo_compat))
		if octoprint_version in s:
			break
	else:
		return False

	return True

# copied from pluginmanager plugin
def _get_octoprint_version():
	from octoprint.server import VERSION
	octoprint_version_string = VERSION

	if "-" in octoprint_version_string:
		octoprint_version_string = octoprint_version_string[:octoprint_version_string.find("-")]

	octoprint_version = pkg_resources.parse_version(octoprint_version_string)
	if isinstance(octoprint_version, tuple):
		# old setuptools
		base_version = []
		for part in octoprint_version:
			if part.startswith("*"):
				break
			base_version.append(part)
		octoprint_version = ".".join(base_version)
	else:
		# new setuptools
		octoprint_version = pkg_resources.parse_version(octoprint_version.base_version)

	return octoprint_version
# check if we have min version 1.3.0
# this is important because of WizardPlugin mixin and folders in filebrowser
def get_implementation_class():
	if not _is_octoprint_compatible(["1.3.0"]):
		return TelegramPlugin(1.2)
	else:
		class NewTelegramPlugin(TelegramPlugin,octoprint.plugin.WizardPlugin):
			def __init__(self,version):
				super(self.__class__, self).__init__(version)
		return NewTelegramPlugin(1.3)


__plugin_name__ = "Telegram Notifications"
__plugin_implementation__ = get_implementation_class()
__plugin_hooks__ = {
	"octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information,
	"octoprint.server.http.routes": __plugin_implementation__.route_hook
}
