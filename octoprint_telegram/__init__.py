from __future__ import absolute_import
from PIL import Image
import threading, requests, re, time, datetime, StringIO, json, random, logging, traceback, io
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
					self._logger.debug(str(message))
					# Get the update_id to only request newer Messages the next time
					if message['update_id'] >= self.update_offset:
						self.update_offset = message['update_id']+1
					
					if not message['message'] or not message['message']['chat']:
						self._logger.warn("Response is missing .message or .message.chat. Skipping it.")
						continue
					
					### Parse new chats
					chat = message['message']['chat']
					chat_id = str(chat['id'])
					data = {'accept_commands' : False, 'send_notifications' : False}
					if chat_id in self.main.chats:
						data = self.main.chats[chat_id]
					else:
						self.main.chats[chat_id] = data
					
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
					self._logger.debug("Chats: " + repr(self.main.chats))

					#if message from group, user allowed?
					from_id = chat_id
					if not data['private'] and data['accept_commands']:
						from_id = str(message['message']['from']['id'])
						
					if self.first_contact:
						self._logger.debug("Ignoring message because first_contact is True.")
						continue
					
					if "text" in message['message']:
						# We got a chat message.
						#msg_list = message['message']['text'].split('@')
						command = message['message']['text'].split('@')[0]
						parameter = None
						if "reply_to_message" in message['message'] and "text" in message['message']['reply_to_message']:
							command = message['message']['reply_to_message']['text']
							parameter = message['message']['text']
						
						self._logger.info("Got a command: '" + command + "' in chat " + str(message['message']['chat']['id']))
						if from_id in self.main.chats and self.main.chats[from_id]['accept_commands'] and self.main.chats[from_id]['private']:
							if command=="/abort":
								self.main.track_action("command/abort")
								if self.main._printer.is_printing():
									self.main.send_msg(gettext("Really abort the currently running print?"), responses=[gettext("Yes, abort the print!"), gettext("No, don't abort the print.")],chatID=chat_id)
								else:
									self.main.send_msg(gettext("Currently I'm not printing, so there is nothing to stop."),chatID=chat_id)
							elif command==gettext("Yes, abort the print!") or parameter==gettext("Yes, abort the print!"):
								self.main.send_msg(gettext("Aborting the print."),chatID=chat_id)
								self.main._printer.cancel_print()
							elif command==gettext("No, don't abort the print.") or parameter==gettext("No, don't abort the print."):
								self.main.send_msg(gettext("Okay, nevermind."),chatID=chat_id)
							elif command=="/shutup":
								self.main.track_action("command/shutup")
								self.main.shut_up = True
								self.main.send_msg(gettext("Okay, shutting up until the next print is finished. Use /imsorrydontshutup to let me talk again before that."),chatID=chat_id)
							elif command=="/imsorrydontshutup":
								self.main.track_action("command/imsorrydontshutup")
								self.main.shut_up = False
								self.main.send_msg(gettext("Yay, I can talk again."),chatID=chat_id)
							elif command=="/test":
								self.main.track_action("command/test")
								self.main.send_msg(gettext("Is this a test?"), responses=[gettext("Yes, this is a test!"), gettext("A test? Why would there be a test?")],chatID=chat_id)
							elif command==gettext("Yes, this is a test!") or parameter==gettext("Yes, this is a test!"):
								self.main.send_msg(gettext("I'm behaving, then."),chatID=chat_id)
							elif command==gettext("A test? Why would there be a test?") or parameter==gettext("A test? Why would there be a test?"):
								self.main.send_msg(gettext("Phew."),chatID=chat_id)
							elif command=="/status":
								self.main.track_action("command/status")
								if not self.main._printer.is_operational():
									self.main.send_msg(gettext("Not connected to a printer."),chatID=chat_id)
								elif self.main._printer.is_printing():
									status = self.main._printer.get_current_data()
									self.main.on_event("TelegramSendPrintingStatus", {'z': (status['currentZ'] or 0.0)},chatID=chat_id)
								else:
									self.main.on_event("TelegramSendNotPrintingStatus", {},chatID=chat_id)
							elif command=="/settings":
								self.main.track_action("command/settings")
								msg = gettext("Current settings are:\n\nNotification height: %(height)fmm\nNotification time: %(time)dmin\n\nWhich value do you want to change?",
									height=self.main._settings.get_float(["notification_height"]),
									time=self.main._settings.get_int(["notification_time"]))
								self.main.send_msg(msg, responses=[gettext("Change notification height"), gettext("Change notification time"), gettext("None")],chatID=chat_id)
							elif command==gettext("None") or parameter==gettext("None"):
								self.main.send_msg(gettext("OK."),chatID=chat_id)
							elif command==gettext("Change notification height") or parameter==gettext("Change notification height"):
								self.main.send_msg(gettext("Please enter new notification height."), force_reply=True,chatID=chat_id)
							elif command==gettext("Please enter new notification height.") and parameter:
								self.main._settings.set_float(['notification_height'], parameter, force=True)
								self.main.send_msg(gettext("Notification height is now %(height)fmm.", height=self.main._settings.get_float(['notification_height'])),chatID=chat_id)
							elif command==gettext("Change notification time") or parameter==gettext("Change notification time"):
								self.main.send_msg(gettext("Please enter new notification time."), force_reply=True,chatID=chat_id)
							elif command==gettext("Please enter new notification time.") and parameter:
								self.main._settings.set_int(['notification_time'], parameter, force=True)
								self.main.send_msg(gettext("Notification time is now %(time)dmins.", time=self.main._settings.get_int(['notification_time'])),chatID=chat_id)
							elif command=="/list":
								self.main.track_action("command/list")
								files = self.get_flat_file_tree()
								self.main.send_msg("File List:\n\n" + "\n".join(files) + "\n\nYou can click the command beginning with /print after a file to start printing this file.",chatID=chat_id)
							elif command=="/print":
								self.main.send_msg("I don't know which file to print. Use /list to get a list of files and click the command beginning with /print after the correct file.",chatID=chat_id)
							elif command.startswith("/print_"):
								self.main.track_action("command/print")
								hash = command[7:]
								self._logger.debug("Looking for hash: %s", hash)
								destination, file = self.find_file_by_hash(hash)
								self._logger.debug("Destination: %s", destination)
								self._logger.debug("File: %s", file)
								if file is None:
									self.main.send_msg("I'm sorry, but I couldn't find the file you wanted me to print. Perhaps you want to have a look at /list again?",chatID=chat_id)
									continue
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
									self.main.send_msg(gettext("Okay. The file %(file)s is loaded. Do you want me to start printing it now?", file=data['job']['file']['name']), responses=[gettext("Yes, start printing, please."), gettext("Nope.")],chatID=chat_id)
							elif command==gettext("Yes, start printing, please.") or parameter==gettext("Yes, start printing, please."):
								data = self.main._printer.get_current_data()
								if data['job']['file']['name'] is None:
									self.main.send_msg(gettext("Uh oh... No file is selected for printing. Did you select one using /list?"),chatID=chat_id)
									continue
								if not self.main._printer.is_operational():
									self.main.send_msg(gettext("Can't start printing: I'm not connected to a printer."),chatID=chat_id)
									continue
								if self.main._printer.is_printing():
									self.main.send_msg("A print job is already running. You can't print two thing at the same time. Maybe you want to use /abort?",chatID=chat_id)
									continue
								self.main._printer.start_print()
								self.main.send_msg(gettext("Started the print job."),chatID=chat_id)
							elif command==gettext("Nope.") or parameter==gettext("Nope."):
								self.main.send_msg("It's okay. We all make mistakes sometimes.",chatID=chat_id)
							elif command=="/upload":
								self.main.track_action("command/upload_command_that_tells_the_user_to_just_send_a_file")
								self.main.send_msg("To upload a gcode file, just send it to me.",chatID=chat_id)
							elif command=="/light":
								self.main._printer.commands("M42 P47 S255")
								self.main.send_msg("I put the lights on.",chatID=chat_id)
							elif command=="/darkness":
								self.main._printer.commands("M42 P47 S0")
								self.main.send_msg("Lights are off now.",chatID=chat_id)
							elif command=="/help":
								self.main.track_action("command/help")
								self.main.send_msg(gettext("You can use following commands:\n"
								                           "/abort - Aborts the currently running print. A confirmation is required.\n"
								                           "/shutup - Disables automatic notifications till the next print ends.\n"
								                           "/imsorrydontshutup - The opposite of /shutup - Makes the bot talk again.\n"
								                           "/status - Sends the current status including a current photo.\n"
								                           "/settings - Displays the current notification settings and allows you to change them."),chatID=chat_id)
						else:
							self._logger.warn("Previous command was from an unknown user.")
							self.main.send_msg("You are not allowed to do this!",chatID=chat_id)
					elif "document" in message['message']:
						self.main.track_action("command/upload")
						try:
							file_name = message['message']['document']['file_name']
							if not (file_name.lower().endswith('.gcode') or file_name.lower().endswith('.gco') or file_name.lower().endswith('.g')):
								self.main.send_msg("Sorry, I only accept files with .gcode, .gco or .g extension.", chatID=message['message']['chat']['id'])
								continue
							# download the file
							data = self.main.get_file(message['message']['document']['file_id'])
							stream = octoprint.filemanager.util.StreamWrapper(file_name, io.BytesIO(data))
							target_filename = "telegram_" + file_name
							self.main._file_manager.add_file(octoprint.filemanager.FileDestinations.LOCAL, target_filename, stream, allow_overwrite=True)
							self.main.send_msg("I've successfully saved the file you sent me as {}.".format(target_filename), chatID=message['message']['chat']['id'])
						except Exception as ex:
							self.main.send_msg("Something went wrong during processing of your file. Sorry. More details are in octoprint.log.", chatID=message['message']['chat']['id'])
							self._logger.debug("Exception occured during processing of a file: "+ traceback.format_exc() )
					else:
						self._logger.warn("Got an unknown message. Doing nothing. Data: " + str(message))
			except Exception as ex:
				self._logger.error("Exception caught! " + str(ex))
			
			self.set_status(gettext("Connected as %(username)s.", username=self.username), ok=True)
				
			if self.first_contact:
				self.first_contact = False
				if self.main._settings.get_boolean(["message_at_startup"]):
					self.main.send_msg(gettext("Hello. I'm online and ready to receive your commands."))
		self._logger.debug("Listener exits NOW.")
	
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
                     octoprint.plugin.AssetPlugin):
	def __init__(self):
		self.thread = None
		self.last_z = 0.0
		self.last_notification_time = 0
		self.bot_url = None
		self.first_contact = True
		self.chats = {}
		self.shut_up = False
		self.connection_state_str = gettext("Disconnected.")
		self.connection_ok = False
		requests.packages.urllib3.disable_warnings()

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
	
	def on_shutdown(self):
		if self._settings.get_boolean(["message_at_shutdown"]):
			self.send_msg(gettext("Shutting down. Goodbye."))
	
	def set_log_level(self):
		self._logger.setLevel(logging.DEBUG if self._settings.get_boolean(["debug"]) else logging.NOTSET)
	
	def get_settings_preprocessors(self):
		return dict(), dict(
			notification_height=lambda x: float(x),
			notification_time=lambda x: int(x)
		)
	
	def on_settings_save(self, data):
		data['chats'] = self.chats
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
			messages = dict(
				PrintStarted = gettext("Started printing {file}."),
				PrintFailed = gettext("Printing {file} failed."),
				ZChange = gettext("Printing at Z={z}.\nBed {bed_temp}/{bed_target}, Extruder {e1_temp}/{e1_target}.\n{time_done}, {percent}%% done, {time_left} remaining."),
				PrintDone = gettext("Finished printing {file}."),
				TelegramSendNotPrintingStatus = gettext("Not printing.\nBed {bed_temp}/{bed_target}, Extruder {e1_temp}/{e1_target}.")
			),
			tracking_activated = False,
			tracking_token = None,
			chats = dict(),  
			debug = False
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
			if abs(new_z - (old_z or 0.0)) >= 2.0:
				# big changes in height are not interesting for notifications - we ignore them
				self.last_z = new_z
				return False
			if new_z >= self.last_z + zdiff or new_z < self.last_z:
				return True
		return False
		
	def on_event(self, event, payload, *args, **kwargs):
		try:
			if event != "PrintDone" and event != "PrintStarted" and event != "ZChange" and event!="PrintFailed" and event!="TelegramSendPrintingStatus" and event!="TelegramSendNotPrintingStatus":
				# return as fast as possible
				return
			
			self._logger.debug("Got an event: " + event + " Payload: " + str(payload))
			# PrintFailed Payload: {'origin': 'local', 'file': u'cube.gcode'}
			# MovieDone Payload: {'gcode': u'cube.gcode', 'movie_basename': 'cube_20160216125143.mpg', 'movie': '/home/pi/.octoprint/timelapse/cube_20160216125143.mpg'}
			
			z = ""
			file = ""
		
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
			elif event=="TelegramSendPrintingStatus":
				z = payload['z']
				# Change the event type in order to generate a ZChange message
				event = "ZChange"
				track = False
			elif event=="TelegramSendNotPrintingStatus":
				track = False
			
			self.last_notification_time = time.time()
			self.last_z = z
				
			if self.shut_up:
				return
			
			self._logger.debug(str(status))
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
			
			if "file" in payload: file = payload["file"]
			if "gcode" in payload: file = payload["gcode"]
			if "filename" in payload: file = payload["filename"]
			message = self._settings.get(["messages", event]).format(**locals())
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
		threading.Thread(target=self._send_msg, kwargs=kwargs).run()

	def _send_msg(self, message="", with_image=False, responses=None, force_reply=False, delay=0, chatID = ""):
		if delay > 0:
			time.sleep(delay)
		try:
			self._logger.debug("Sending a message: " + message.replace("\n", "\\n") + " with_image=" + str(with_image) + " chatID= " + str(chatID))
			data = {}
			# We always send hide_keyboard unless we send an actual keyboard
			data['reply_markup'] = json.dumps({'hide_keyboard': True})  

			if force_reply:
				data['reply_markup'] = json.dumps({'force_reply': True})
			if responses:
				keyboard = {'keyboard':map(lambda x: [x], responses), 'one_time_keyboard': True}
				data['reply_markup'] = json.dumps(keyboard)
			image_data = None
			if with_image:
				image_data = self.take_image()
			self._logger.debug("data so far: " + str(data))
			if image_data:
				self._logger.debug("Sending with image.")
				files = {'photo':("image.jpg", image_data)}
				data['caption'] = message
				if chatID == "":
					chats = self._settings.get(['chats'])
					for key in chats:
						if chats[key]['send_notifications'] is True:
							data['chat_id'] = key
							self._logger.debug("Sending... " + str(key))
							r = requests.post(self.bot_url + "/sendPhoto", files=files, data=data)
							self._logger.debug("Sending finished. " + str(r.status_code) + " " + str(r.content))
				else:
					data['chat_id'] = chatID
					r = requests.post(self.bot_url + "/sendPhoto", files=files, data=data)
					self._logger.debug("Sending finished. " + str(r.status_code) + " " + str(r.content))

			else:
				self._logger.debug("Sending without image.")
				data['text'] = message
				if chatID == "":
					chats = self._settings.get(['chats'])
					for key in chats:
						if chats[key]['send_notifications'] is True:
							data['chat_id'] = key
							self._logger.debug("Sending... " + str(key))
							requests.post(self.bot_url + "/sendMessage", data=data)
				else:
					data['chat_id'] = chatID
					requests.post(self.bot_url + "/sendMessage", data=data)
		except Exception as ex:
			self._logger.debug("Caught an exception in send_msg(): " + str(ex))
	
	def send_video(self, message, video_file):
		files = {'video': open(video_file, 'rb')}
		#r = requests.post(self.bot_url + "/sendVideo", files=files, data={'chat_id':self._settings.get(["chat"]), 'caption':message}) #############################HIER
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
		return json.dumps({'chats':self.chats, 'connection_state_str':self.connection_state_str, 'connection_ok':self.connection_ok})
	
	def on_api_command(self, command, data):
		if command=="testToken":
			self._logger.debug("Testing token {}".format(data['token']))
			try:
				username = self.test_token(data['token'])
				return json.dumps({'ok': True, 'connection_state_str': gettext("Token valid for %(username)s.", username=username), 'error_msg': None, 'username': username})
			except Exception as ex:
				return json.dumps({'ok': False, 'connection_state_str': gettext("Error: %(error)s", error=ex), 'username': None, 'error_msg': str(ex)})
		elif command=="updateChat":
			strId = str(data['ID'])
			if strId in self.chats:								
				self.chats[strId]['send_notifications'] = data['chatNotify']
				self.chats[strId]['accept_commands'] = data['chatCmd']	
			return json.dumps({'chats':self.chats, 'connection_state_str':self.connection_state_str, 'connection_ok':self.connection_ok})
		elif command=="delChat":
			strId = str(data['ID'])
			self._logger.debug("Deleting Chat ID {}".format(data['ID']))
			if strId in self.chats:	
				del self.chats[strId]
				self._logger.debug("Done Deleting ID {}".format(data['ID']))
			return json.dumps({'chats':self.chats, 'connection_state_str':self.connection_state_str, 'connection_ok':self.connection_ok})


	
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