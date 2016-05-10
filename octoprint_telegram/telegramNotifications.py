from __future__ import absolute_import
import time, datetime, logging  # StringIO, traceback, io, collections 
import octoprint.util
from flask.ext.babel import gettext

telegramMsgDict = {
			'PrinterStart': {
				'text': "{emo[rocket]} " + gettext("Hello. I'm online and ready to receive your commands."),
				'image': False,
			},
			'PrinterShutdown': {
				'text': "{emo[octo]} {emo[shutdown]} " + gettext("Shutting down. Goodbye."),
				'image': False,
			},
			'PrintStarted': {
				'text': gettext("Started printing {file}."),
				'image': True,
			},
			'PrintFailed': {
				'text': gettext("Printing {file} failed."),
				'image': True,
			},
			'ZChange': {
				'text': gettext("Printing at Z={z}.\nBed {bed_temp}/{bed_target}, Extruder {e1_temp}/{e1_target}.\n{time_done}, {percent}%% done, {time_left} remaining."),
				'image': True,
			},
			'PrintDone': {
				'text': gettext("Finished printing {file}."),
				'image': True,
			},
			'StatusNotPrinting': {
				'text': gettext("Not printing.\nBed {bed_temp}/{bed_target}, Extruder {e1_temp}/{e1_target}."),
				'image': True,
				'no_setting': True
			},
			'StatusPrinting': {
				'bind_msg': 'ZChange',
			}
		}

class TMSG():
	def __init__(self, main):
		self.main = main
		self.last_z = 0.0
		self.last_notification_time = 0
		self.track = True
		self.z = ""
		self._logger = main._logger.getChild("listener")
		
		self.msgCmdDict = {
			'PrinterStart': {
				'cmd': self.msgPrinterStart_Shutdown
			},
			'PrinterShutdown': {
				'cmd': self.msgPrinterStart_Shutdown
			},
			'PrintStarted': {
				'cmd': self.msgPrintStarted
			},
			'PrintFailed': {
				'cmd': self.msgPrintFailed
			},
			'ZChange': {
				'cmd': self.msgZChange
			},
			'PrintDone': {
				'cmd': self.msgPrintDone
			},
			'StatusNotPrinting': {
				'cmd': self.msgStatusNotPrinting
			},
			'StatusPrinting': {
				'cmd': self.msgStatusPrinting
			}
		}

	def _prepMsg(self, event):
		status = self.main._printer.get_current_data()
		self.z = status['currentZ'] or 0.0
		if 'bind-msg' in telegramMsgDict[event]:
			event = telegramMsgDict[event]['bind-msg']
		return event

	def msgPrinterStart_Shutdown(self, event, payload, **kwargs):
		kwargs['event'] = self._prepMsg(event)
		self._sendNotification(payload, **kwargs)

	def msgZChange(self, event, payload, **kwargs):
		kwargs['event'] = self._prepMsg(event)
		status = self._printer.get_current_data()
		if not status['state']['flags']['printing'] or not self.is_notification_necessary(payload['new'], payload['old']):
			return
		self.z = payload['new']
		self._logger.debug("Z-Change. new_z=%.2f old_z=%.2f last_z=%.2f notification_height=%.2f notification_time=%d",
			z,
			payload['old'],
			self.last_z,
			self._settings.get_float(['notification_height']),
			self._settings.get_int(['notification_time']))
		self._sendNotification(payload, **kwargs)

	def msgPrintStarted(self, event, payload, **kwargs):
		kwargs['event'] = self._prepMsg(event)
		self.last_z = 0.0
		self.last_notification_time = time.time()
		self._sendNotification(payload, **kwargs)

	def msgPrintDone(self, event, payload, **kwargs):
		kwargs['event'] = self._prepMsg(event)
		self.main.shut_up = {}
		kwargs["delay"] = self.main._settings.get_int(["message_at_print_done_delay"])
		self._sendNotification(payload, **kwargs)

	def msgPrintFailed(self, event, payload, **kwargs):
		kwargs['event'] = self._prepMsg(event)
		self.main.shut_up = {}
		self._sendNotification(payload, **kwargs)
		
	def msgStatusPrinting(self, event, payload, **kwargs):
		kwargs['event'] = self._prepMsg(event)
		self.track = False
		self._sendNotification(payload, **kwargs)

	def msgStatusNotPrinting(self, event, payload, **kwargs):
		kwargs['event'] = self._prepMsg(event)
		self.track = False
		self._sendNotification(payload, **kwargs)

	def _sendNotification(self, payload, **kwargs):
		status = self.main._printer.get_current_data()
		kwargs['with_image'] = telegramMsgDict[kwargs['event']]['image']
		self._logger.debug(str(status))
		z = self.z
		# is the if useful? i got an error sometimes
		temps = self.main._printer.get_current_temperatures()
		self._logger.debug("TEMPS - " + str(temps))
		bed_temp = temps['bed']['actual'] if 'bed' in temps else 0.0
		bed_target = temps['bed']['target'] if 'bed' in temps else 0.0 
		e1_temp = temps['tool0']['actual'] if 'tool0' in temps else 0.0
		e1_target = temps['tool0']['target'] if 'tool0' in temps else 0.0
		e2_temp = e2_target = None
		e2_temp = temps['tool1']['actual'] if 'tool1' in temps else 0.0
		e2_target = temps['tool1']['target'] if 'tool1' in temps else 0.0
		percent = int(status['progress']['completion'] or 0)
		time_done = octoprint.util.get_formatted_timedelta(datetime.timedelta(seconds=(status['progress']['printTime'] or 0)))
		time_left = octoprint.util.get_formatted_timedelta(datetime.timedelta(seconds=(status['progress']['printTimeLeft'] or 0)))
		file = ""
		if "file" in payload: file = payload["file"]
		if "gcode" in payload: file = payload["gcode"]
		if "filename" in payload: file = payload["filename"]
		emo = {}; #{k: v.encode("utf-8") for k, v in self.main.emojis.iteritems()}
		for k in self.main.emojis:
			emo[k] = self.main.gEmo(k).encode("utf-8")

		message = self.main._settings.get(["messages",kwargs['event'],"text"]).format(**locals())
		self._logger.debug("Sending message: " + message)
		self.main.send_msg(message, **kwargs)

		if self.track:
			self.main.track_action("notification/" + kwargs['event'])
		self.track = True

	def is_notification_necessary(self, new_z, old_z):
		timediff = self.main._settings.get_int(['notification_time'])
		if timediff and timediff > 0:
			# check the timediff
			if self.last_notification_time + timediff*60 <= time.time():
				self.last_notification_time = time.time();
				return True
		zdiff = self.main._settings.get_float(['notification_height'])
		if zdiff and zdiff > 0.0:
			if old_z is None:
				return False
			# check the zdiff
			if abs(new_z - (old_z or 0.0)) >= 1.0:
				# big changes in height are not interesting for notifications - we ignore them
				self.last_z = new_z
				return False
			if new_z >= self.last_z + zdiff or new_z < self.last_z:
				self.last_z= new_z
				return True
		return False