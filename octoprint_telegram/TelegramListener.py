from PIL import Image
from subprocess import Popen, PIPE
import threading, requests, re, time, datetime, StringIO, json, random, logging, traceback, io, collections, os, flask,base64,PIL, pkg_resources,subprocess,zipfile,glob #,resource
import octoprint.plugin, octoprint.util, octoprint.filemanager
from flask.ext.babel import gettext
from flask.ext.login import current_user

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
			self._logger.error("Exception caught! " + traceback.format_exc())
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
	
	def extractCommandFromText(self, text):
		command = str(text.split('@')[0].encode('utf-8'))
		if "_" in command:
			parameter = '_'.join(command.split('_')[1:])
			command = command.split('_')[0]
		else:
			parameter = ""
		return command, parameter
	
	def getCommandObject(self, command):
		return self.main.tcmd.getCommandObject(command)
	
	def handleTextMessage(self, message, chat_id, from_id):
		# We got a chat message.
		# handle special messages from groups (/commad@BotName)
		command, parameter = self.extractCommandFromText(message['message']['text'])
		self._logger.info("Got a command: '" + str(command.encode('utf-8')) + "' with parameter: '" + str(parameter.encode('utf-8')) + "' in chat " + str(chat_id))
		# is command known?
		known_internally = True
		try:
			commandObject = self.getCommandObject(command)
		except CommandNotFoundException: 
			known_internally = False
		
		# check if user is allowed to execute the command
		if self.main.isCommandAllowed(chat_id,from_id,command):
			# Track command
			if command.startswith("/"):
				self.main.track_action("command/" + command[1:])
			# execute command
			commandObject['cmd'](chat_id,from_id,command,parameter)
		else:
			# user was not allowed to execute this command
			self._logger.warn("Previous command was from an unauthorized user.")
			self.main.send_msg("You are not allowed to do this! " + self.gEmo('notallowed'),chatID=chat_id)
		
		known_externally = False
		if self.main.isCommandAllowed(chat_id, from_id, "PLUGIN"):
			known_externally = self.main.plugin_interface.process_hooks(command, parameter)
		
		if not known_internally and not known_externally:
			# we dont know the command so skip the message
			self._logger.warn("Previous command was an unknown command.")
			self.main.send_msg("I do not understand you! " + self.gEmo('mistake'),chatID=chat_id)
			raise ExitThisLoopException()

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
						self.set_status(gettext("Response didn't include 'ok:true'. Waiting 2 minutes before trying again. Response was: %(response)s", json))
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
			self.set_status(gettext("Response didn't include 'ok:true'. Waiting 2 minutes before trying again. Response was: %(response)s", json))
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
