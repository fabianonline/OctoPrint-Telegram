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
		self._logger = main._logger.getChild("listener")
	
	def run(self):
		self._logger.debug("Listener is running.")
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
				self._logger.error("Got an exception while trying to connect to telegram API: " + str(ex))
				self._logger.error("Waiting 2 minutes before trying again.")
				time.sleep(120)
				continue
			if req.status_code != 200:
				self._logger.warn("Telegram API responded with code " + str(req.status_code) + ". Waiting 2 minutes before trying again.")
				time.sleep(120)
				continue
			if req.headers['content-type'] != 'application/json':
				self._logger.warn("Unexpected Content-Type. Expected: application/json. Was: " + req.headers['content-type'])
				self._logger.warn("Waiting 2 minutes before trying again.")
				time.sleep(120)
				continue
			json = req.json()
			if not json['ok']:
				self._logger.warn("Response didn't include 'ok:true'. Waiting 2 minutes before trying again. Response was: " + str(json))
				time.sleep(120)
				continue
			try:
				for message in json['result']:
					self._logger.debug(str(message))
					if message['update_id'] >= self.update_offset:
						self.update_offset = message['update_id']+1
					if message['message']['chat']['type']!='private':
						continue
					self.main.known_chats[str(message['message']['chat']['id'])] = message['message']['chat']['first_name'] + " " + message['message']['chat']['last_name'] + " (" + message['message']['chat']['username'] + ")"
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
				
			if self.first_contact:
				self.first_contact = False
				self.main.send_msg("Hello. I'm online and ready to receive your commands.", with_image=False)
		self._logger.debug("Listener exits NOW.")
	
	def stop(self):
		self.do_stop = True

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
		self.send_msg("Shutting down. Goodbye.", with_image=False)
	
	def get_settings_preprocessors(self):
		return dict(), dict(
			chat=lambda x: int(x),
			notification_height=lambda x: float(x),
			notification_time=lambda x: int(x)
		)
	
	def on_settings_save(self, data):
		self._logger.debug("Saving data: " + str(data))
		if not re.match("^[0-9]+:[a-zA-Z0-9]+$", data['token']):
			self._logger.warn("Not saving token because it doesn't seem to have the right format.")
			data['token'] = ""
		old_token = self._settings.get(["token"])
		octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
		if data['token']!="" and data['token']!=old_token:
			self.stop_listening()
			self.start_listening()
	
	def get_settings_defaults(self):
		return dict(
			token = "",
			chat = "",
			notification_height = 5.0,
			notification_time = 15,
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
	
	def is_notification_necessary(self, new_z, old_z):
		timediff = self._settings.get_int(['notification_time'])
		if timediff and timediff > 0:
			# check the timediff
			if self.last_notification_time + timediff*60 <= time.time():
				return True
		zdiff = self._settings.get_float(['notification_height'])
		if zdiff and zdiff > 0.0:
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
		
			if event=="ZChange":
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
			
			status = self._printer.get_current_data()
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
		return json.dumps({'known_chats':chats})
	
	def get_assets(self):
		return dict(js=["js/telegram.js"])

__plugin_name__ = "Telegram Notifications"
__plugin_implementation__ = TelegramPlugin()