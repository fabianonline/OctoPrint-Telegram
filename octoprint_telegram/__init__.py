from __future__ import absolute_import
from PIL import Image
import threading, requests, re, time, datetime, StringIO, json
import octoprint.plugin, octoprint.util

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
		response = requests.get(self.main.bot_url + "/getMe")
		self._logger.debug("getMe returned: " + str(response.json()))
		self._logger.debug("getMe status code: " + str(response.status_code))
		try:
			json = response.json()
			if not 'ok' in json or not json['ok']:
				if json['description']:
					self.set_status("Telegram returned error code {}: {}".format(json['error_code'], json['description']))
				else:
					self.set_status("Telegram returned an unspecified error.")
				return
			else:
				self.set_status("Connected as @{}.".format(json['result']['username']), ok=True)
				self.username = "@" + json['result']['username']
		except Exception as ex:
			self.set_status("An exception occurred while trying to initially connect to telegram. Exception was: {}".format(ex))
			return
		
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
				self.set_status("Got an exception while trying to connect to telegram API: {}. Waiting 2 minutes before trying again.".format(ex))
				time.sleep(120)
				continue
			if req.status_code != 200:
				self.set_status("Telegram API responded with code {}. Waiting 2 minutes before trying again.".format(req.status_code))
				time.sleep(120)
				continue
			if req.headers['content-type'] != 'application/json':
				self.set_status("Unexpected Content-Type. Expected: application/json. Was: {}. Waiting 2 minutes before trying again.".format(req.headers['content-type']))
				time.sleep(120)
				continue
			json = req.json()
			if not json['ok']:
				self.set_status("Response didn't include 'ok:true'. Waiting 2 minutes before trying again. Response was: {}".format(json))
				time.sleep(120)
				continue
			try:
				for message in json['result']:
					self._logger.debug(str(message))
					if message['update_id'] >= self.update_offset:
						self.update_offset = message['update_id']+1
					if not message['message'] or not message['message']['chat'] or message['message']['chat']['type']!='private':
						self._logger.warn("Chat is non-private")
						continue
					chat = message['message']['chat']
					chat_str = ""
					if "first_name" in chat:
						chat_str += chat['first_name'] + " - "
					if "last_name" in chat:
						chat_str += chat['last_name'] + " - "
					if "username" in chat:
						chat_str += "@" + chat['username']
					self.main.known_chats[str(chat['id'])] = chat_str
					self._logger.debug("Known chats: " + str(self.main.known_chats))
					if self.first_contact:
						continue
					
					if "text" in message['message']:
						# We got a chat message.
						command = message['message']['text']
						parameter = None
						if "reply_to_message" in message['message'] and "text" in message['message']['reply_to_message']:
							command = message['message']['reply_to_message']['text']
							parameter = message['message']['text']
						
						self._logger.info("Got a command: '" + command + "' in chat " + str(message['message']['chat']['id']))
						if self.main._settings.get(['chat'])==str(message['message']['chat']['id']):
							if command=="/abort":
								if self.main._printer.is_printing():
									self.main.send_msg("Really abort the currently running print?", responses=["Yes, abort the print!", "No, don't abort the print."])
								else:
									self.main.send_msg("Currently I'm not printing, so there is nothing to stop.")
							elif command=="Yes, abort the print!":
								self.main.send_msg("Aborting the print.")
								self.main._printer.cancel_print()
							elif command=="No, don't abort the print.":
								self.main.send_msg("Okay, nevermind.")
							elif command=="/shutup":
								self.main.shut_up = True
								self.main.send_msg("Okay, shutting up until the next print is finished. Use /imsorrydontshutup to let me talk again before that.")
							elif command=="/imsorrydontshutup":
								self.main.shut_up = False
								self.main.send_msg("Yay, I can talk again.")
							elif command=="/test":
								self.main.send_msg("Is this a test?", responses=["Yes, this is a test!", "A test? Why would there be a test?"])
							elif command=="Yes, this is a test!":
								self.main.send_msg("I'm behaving, then.")
							elif command=="A test? Why would there be a test?":
								self.main.send_msg("Phew.")
							elif command=="/status":
								if self.main._printer.is_printing():
									status = self.main._printer.get_current_data()
									self.main.on_event("TelegramSendPrintingStatus", {'z': (status['currentZ'] or 0.0)})
								else:
									self.main.on_event("TelegramSendNotPrintingStatus", {})
							elif command=="/settings":
								msg = "Current settings are:\n\nNotification height: {}mm\nNotification time: {}min\n\nWhich value do you want to change?".format(
									self.main._settings.get_float(["notification_height"]),
									self.main._settings.get_int(["notification_time"]))
								self.main.send_msg(msg, responses=["Change notification height", "Change notification time", "None"])
							elif command=="None":
								self.main.send_msg("OK.")
							elif command=="Change notification height":
								self.main.send_msg("Please enter new notification height.", force_reply=True)
							elif command=="Please enter new notification height." and parameter:
								self.main._settings.set_float(['notification_height'], parameter, force=True)
								self.main.send_msg("Notification height is now {}mm.".format(self.main._settings.get_float(['notification_height'])))
							elif command=="Change notification time":
								self.main.send_msg("Please enter new notification time.", force_reply=True)
							elif command=="Please enter new notification time." and parameter:
								self.main._settings.set_int(['notification_time'], parameter, force=True)
								self.main.send_msg("Notification time is now {}mins.".format(self.main._settings.get_int(['notification_time'])))
							elif command=="/help":
								msg = "You can use following commands:\n"
								msg+= "/abort - Aborts the currently running print. A confirmation is required.\n"
								msg+= "/shutup - Disables automatic notifications till the next print ends.\n"
								msg+= "/imsorrydontshutup - The opposite of /shutup - Makes the bot talk again.\n"
								msg+= "/status - Sends the current status including a current photo.\n"
								msg+= "/settings - Displays the current notification settings and allows you to change them."
								self.main.send_msg(msg)
						else:
							self._logger.warn("Previous command was from an unknown user.")
					elif "document" in message['message']:
						# we got a file. Doing nothing (for now...)
						self._logger.warn("Got a file. Doing nothing. Data: " + str(msg))
					else:
						self._logger.warn("Got an unknown message. Doing nothing. Data: " + str(msg))
			except Exception as ex:
				self._logger.error("Exception caught! " + str(ex))
			
			self.set_status("Connected as {}".format(self.username), ok=True)
				
			if self.first_contact:
				self.first_contact = False
				if self.main._settings.get_boolean(["message_at_startup"]):
					self.main.send_msg("Hello. I'm online and ready to receive your commands.")
		self._logger.debug("Listener exits NOW.")
	
	def stop(self):
		self.do_stop = True
	
	def set_status(self, status, ok=False):
		if self.do_stop:
			self._logger.debug("Would set status but do_stop is True: %s", status)
			return
		if ok:
			self._logger.debug("Setting status: %s", status)
		else:
			self._logger.error("Setting status: %s", status)
		self.main.connection_state_str = status

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
		self.known_chats = {}
		self.shut_up = False
		self.connection_state_str = "Disconnected."
		requests.packages.urllib3.disable_warnings()

	def start_listening(self):
		if self._settings.get(['token']) != "" and self.thread is None:
			self._logger.debug("Starting listener.")
			self.bot_url = "https://api.telegram.org/bot" + self._settings.get(['token'])
			self.thread = TelegramListener(self)
			self.thread.daemon = True
			self.thread.start()
	
	def stop_listening(self):
		if self.thread is not None:
			self._logger.debug("Stopping listener.")
			self.thread.stop()
			self.thread = None
	
	def on_after_startup(self):
		self.start_listening()
	
	def on_shutdown(self):
		if self._settings.get_boolean(["message_at_shutdown"]):
			self.send_msg("Shutting down. Goodbye.")
	
	def get_settings_preprocessors(self):
		return dict(), dict(
			chat=lambda x: int(x),
			notification_height=lambda x: float(x),
			notification_time=lambda x: int(x)
		)
	
	def on_settings_save(self, data):
		self._logger.debug("Saving data: " + str(data))
		data['token'] = data['token'].strip()
		if not re.match("^[0-9]+:[a-zA-Z0-9_\-]+$", data['token']):
			self._logger.error("Not saving token because it doesn't seem to have the right format.")
			self.connection_state_str = "The previously entered token doesn't seem to have the correct format. It should look like this: 12345678:AbCdEfGhIjKlMnOpZhGtDsrgkjkZTCHJKkzvjhb"
			data['token'] = ""
		old_token = self._settings.get(["token"])
		octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
		if data['token']!=old_token:
			self.stop_listening()
		if data['token']!="":
			self.start_listening()
		else:
			self.connection_state_str = "No token given."
	
	def get_settings_defaults(self):
		return dict(
			token = "",
			chat = "",
			notification_height = 5.0,
			notification_time = 15,
			message_at_startup = True,
			message_at_shutdown = True,
			message_at_print_started = True,
			message_at_print_done = True,
			message_at_print_failed = True,
			messages = dict(
				PrintStarted = "Started printing {file}.",
				PrintFailed = "Printing {file} failed.",
				ZChange = "Printing at Z={z}.\nBed {bed_temp}/{bed_target}, Extruder {e1_temp}/{e1_target}.\n{time_done}, {percent}% done, {time_left} remaining.",
				PrintDone = "Finished printing {file}.",
				TelegramSendNotPrintingStatus = "Not printing.\nBed {bed_temp}/{bed_target}, Extruder {e1_temp}/{e1_target}."
			)
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
			
			self.last_notification_time = time.time()
			self.last_z = z
				
			if self.shut_up:
				return
			
			self._logger.debug(str(status))
			temps = self._printer.get_current_temperatures()
			bed_temp = temps['bed']['actual']
			bed_target = temps['bed']['target']
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
			thread = threading.Thread(target=self.send_msg, args=(message, True,))
			#if event=="MovieDone":
			#	thread = threading.Thread(target=self.send_video, args=(message, payload["movie"],))
			thread.daemon = True
			thread.run()
		except Exception as e:
			self._logger.debug("Exception: " + str(e))

	def send_msg(self, message, with_image=False, responses=None, force_reply=False):
		try:
			self._logger.debug("Sending a message: " + message.replace("\n", "\\n") + " with_image=" + str(with_image))
			data = {'chat_id': self._settings.get(['chat'])}
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
				r = requests.post(self.bot_url + "/sendPhoto", files=files, data=data)
				self._logger.debug("Sending finished. " + str(r.status_code) + " " + str(r.content))
			else:
				self._logger.debug("Sending without image.")
				data['text'] = message
				requests.post(self.bot_url + "/sendMessage", data=data)
		except Exception as ex:
			self._logger.debug("Caught an exception in send_msg(): " + str(ex))
	
	def send_video(self, message, video_file):
		files = {'video': open(video_file, 'rb')}
		r = requests.post(self.bot_url + "/sendVideo", files=files, data={'chat_id':self._settings.get(["chat"]), 'caption':message})
		self._logger.debug("Sending finished. " + str(r.status_code) + " " + str(r.content))
		
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
	
	def on_api_get(self, request):
		chats = []
		for key, value in self.known_chats.iteritems():
			chats.append({'id': key, 'name': value})
		return json.dumps({'known_chats':chats, 'connection_state_str':self.connection_state_str})
	
	def get_assets(self):
		return dict(js=["js/telegram.js"])

__plugin_name__ = "Telegram Notifications"
__plugin_implementation__ = TelegramPlugin()
__plugin_hooks__ = {
	"octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
}