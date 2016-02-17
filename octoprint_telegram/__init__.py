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
	
	def run(self):
		self.main._logger.debug("Listener is running.")
		while not self.do_stop:
			self.main._logger.debug("listener: sending request with offset " + str(self.update_offset) + "...")
			req = None
			try:
				timeout = '30'
				if self.update_offset == 0 and self.first_contact:
					timeout = '0'
					self.update_offset = 1
				req = requests.get(self.main.bot_url + "/getUpdates", params={'offset':self.update_offset, 'timeout':timeout}, allow_redirects=False)
			except Exception as ex:
				self.main._logger.error("Got an exception while trying to connect to telegram API: " + str(ex))
				self.main._logger.error("Waiting 2 minutes before trying again.")
				time.sleep(120)
				continue
			if req.status_code != 200:
				self.main._logger.warn("Telegram API responded with code " + str(req.status_code) + ". Waiting 2 minutes before trying again.")
				time.sleep(120)
				continue
			if req.headers['content-type'] != 'application/json':
				self.main._logger.warn("Unexpected Content-Type. Expected: application/json. Was: " + req.headers['content-type'])
				self.main._logger.warn("Waiting 2 minutes before trying again.")
				time.sleep(120)
				continue
			json = req.json()
			if not json['ok']:
				self.main._logger.warn("Response didn't include 'ok:true'. Waiting 2 minutes before trying again. Response was: " + str(json))
				time.sleep(120)
				continue
			try:
				for message in json['result']:
					self.main._logger.debug(str(message))
					if message['update_id'] >= self.update_offset:
						self.update_offset = message['update_id']+1
					if message['message']['chat']['type']!='private':
						continue
					self.main.known_chats[str(message['message']['chat']['id'])] = message['message']['chat']['first_name'] + " " + message['message']['chat']['last_name'] + " (" + message['message']['chat']['username'] + ")"
					self.main._logger.debug("Known chats: " + str(self.main.known_chats))
					if self.first_contact:
						continue
					
					if self.main._settings.get(['chat'])==str(message['message']['chat']['id']):
						command = message['message']['text']
						self.main._logger.debug("Got a command: " + command)
						if command=="/photo":
							self.main.send_msg("Current photo.", with_image=True)
						elif command=="/abort":
							self.main.send_msg("Really abort the currently running print?", responses=["Yes, abort the print!", "No, don't abort the print."])
						elif command=="Yes, abort the print!":
							# abort the print
						elif command=="No, don't abort the print.":
							self.main.send_msg("Okay, nevermind.")
						elif command=="/shutup":
							self.main.shut_up = True
							self.main.send_msg("Okay, shutting up until the next print is finished. Use /imsorrydontshutup to let me talk again before that.")
						elif command=="/imsorrydontshutup":
							self.main.shut_up = False
							self.main.send_msg("Yay, I can talk again.")
						
					else:
						self.main._logger.warn("Got a command from an unknown user.")
			except Exception as ex:
				self.main._logger.error("Exception caught! " + str(ex))
				
			if self.first_contact:
				self.first_contact = False
				self.main.send_msg("Hello. I'm online and ready to receive your commands.", with_image=False)
		self.main._logger.debug("Listener exits NOW.")
	
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
		self.bot_url = None
		self.first_contact = True
		self.known_chats = {}
		self.shut_up = False

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
	
	def on_settings_save(self, data):
		self._logger.debug("Saving data: " + str(data))
		if not re.match("^[0-9]+:[a-zA-Z0-9]+$", data['token']):
			self._logger.warn("Not saving token because it doesn't seem to have the right format.")
			data['token'] = ""
		if not re.match("^[0-9]+$", data['chat']):
			self._logger.warn("Not saving chat_id because it seems to have a wrong format.")
			data['chat'] = ""
		if not re.match("^[0-9]+(\.[0-9])?$", data['height']):
			self._logger.warn("Height is not a float. Using default 5.0 instead.")
			data['height'] = "5.0"
		old_token = self._settings.get(["token"])
		octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
		if data['token']!="" and data['token']!=old_token:
			self.stop_listening()
			self.start_listening()
	
	def get_settings_defaults(self):
		return dict(
			token = "",
			chat = "",
			height = "5.0",
			message_at_print_started = True,
			message_at_print_done = True,
			message_at_print_failed = True,
			messages = dict(
				PrintStarted = "Started printing {file}.",
				PrintFailed = "Printing {file} failed.",
				ZChange = "Printing at Z={z}",
				PrintDone = "Finished printing {file}.",
			)
		)
	
	def get_template_configs(self):
		return [
			dict(type="settings", name="Telegram", custom_bindings=True)
		]
	
	def on_event(self, event, payload, *args, **kwargs):
		try:
			if event != "PrintDone" and event != "PrintStarted" and event != "ZChange" and event!="PrintFailed":
				# return as fast as possible
				return
			
			self._logger.debug("Got an event: " + event + " Payload: " + str(payload))
			# PrintFailed Payload: {'origin': 'local', 'file': u'cube.gcode'}
			# MovieDone Payload: {'gcode': u'cube.gcode', 'movie_basename': 'cube_20160216125143.mpg', 'movie': '/home/pi/.octoprint/timelapse/cube_20160216125143.mpg'}
			
			if event=="PrintDone":
				self.shut_up = False
				if not self._settings.get_boolean(["message_at_print_done"]):
					return
			elif event=="PrintStarted" and not self._settings.get_boolean(["message_at_print_started"]):
				return
			elif event=="PrintFailed":
				self.shut_up = False
				if not self._settings.get_boolean(["message_at_print_failed"]):
					return
			
			z = ""
			file = ""
			
			if event=="PrintStarted":
				self.last_z = 0.0
			
			if event=="ZChange":
				z = payload['new']
				self._logger.debug("Z-Change. z=" + str(z) + " last_z=" + str(self.last_z) + ", settings_height=" + str(self._settings.get_float(['height'])))
				if abs(z - payload['old']) >= 2.0:
					# a big jump in height is usually due to lifting at the beginning or end of a print
					# we just ignore this.
					self.last_z = z
					return
				if z >= self.last_z + self._settings.get_float(["height"]) or z < self.last_z:
					self.last_z = z
				else:
					return
			
			if self.shut_up:
				return
					
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

	def send_msg(self, message, with_image=False, responses=None):
		try:
			self._logger.debug("Sending a message: " + message + " with_image=" + str(with_image))
			data = {'chat_id': self._settings.get(['chat'])}
			if responses:
				keyboard = {'keyboard':[responses], 'one_time_keyboard': True}
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