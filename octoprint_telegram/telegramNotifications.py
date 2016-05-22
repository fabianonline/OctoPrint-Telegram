from __future__ import absolute_import
import time, datetime, logging
import octoprint.util
from flask.ext.babel import gettext

###################################################################################################
# Here you find the known notification messages and their handles.
# The only way to start a messageHandle should be via on_event() in __init__.py 
# If you want to add/remove notifications read the following:
# SEE DOCUMENTATION IN WIKI: https://github.com/fabianonline/OctoPrint-Telegram/wiki/Add%20commands%20and%20notifications
#####################################################################################################################################################

telegramMsgDict = {
			'PrinterStart': {
				'text': "{emo:rocket} " + gettext("Hello. I'm online and ready to receive your commands."),
				'image': False,
				'markup': "off"
			},
			'PrinterShutdown': {
				'text': "{emo:octo} {emo:shutdown} " + gettext("Shutting down. Goodbye."),
				'image': False,
				'markup': "off"
			},
			'PrintStarted': {
				'text': gettext("Started printing {file}."),
				'image': True,
				'markup': "off"
			},
			'PrintFailed': {
				'text': gettext("Printing {file} failed."),
				'image': True,
				'markup': "off"
			},
			'ZChange': {
				'text': gettext("Printing at Z={z}.\nBed {bed_temp}/{bed_target}, Extruder {e1_temp}/{e1_target}.\n{time_done}, {percent}%% done, {time_left} remaining."),
				'image': True,
				'markup': "off"
			},
			'PrintDone': {
				'text': gettext("Finished printing {file}."),
				'image': True,
				'markup': "off"
			},
			'StatusNotPrinting': {
				'text': gettext("Not printing.\nBed {bed_temp}/{bed_target}, Extruder {e1_temp}/{e1_target}."),
				'image': True,
				'markup': "off",
				'no_setting': True
			},
			'StatusPrinting': {
				'bind_msg': 'ZChange',
				'no_setting': True
			}
		}

# class to handle emojis on notifigation message format
class EmojiFormatter():
	def __init__(self,main):
		self.main = main

	def __format__(self,format):
		if format in self.main.emojis:
			return self.main.gEmo(format).encode("utf-8")
		return ""


class TMSG():
	def __init__(self, main):
		self.main = main
		self.last_z = 0.0
		self.last_notification_time = 0
		self.track = True
		self.z = ""
		self._logger = main._logger.getChild("TMSG")
		
		self.msgCmdDict = {
			'PrinterStart': self.msgPrinterStart_Shutdown,
			'PrinterShutdown': self.msgPrinterStart_Shutdown,
			'PrintStarted': self.msgPrintStarted,
			'PrintFailed': self.msgPrintFailed,
			'ZChange': self.msgZChange,
			'PrintDone': self.msgPrintDone,
			'StatusNotPrinting': self.msgStatusNotPrinting,
			'StatusPrinting': self.msgStatusPrinting
		}

	def _prepMsg(self, event):
		status = self.main._printer.get_current_data()
		self.z = status['currentZ'] or 0.0
		if 'bind_msg' in telegramMsgDict[event]:
			event = telegramMsgDict[event]['bind_msg']
		return event

	def msgPrinterStart_Shutdown(self, event, payload, **kwargs):
		kwargs['event'] = self._prepMsg(event)
		self._sendNotification(payload, **kwargs)

	def msgZChange(self, event, payload, **kwargs):
		kwargs['event'] = self._prepMsg(event)
		status = self.main._printer.get_current_data()
		if not status['state']['flags']['printing'] or not self.is_notification_necessary(payload['new'], payload['old']):
			return
		self.z = payload['new']
		self._logger.debug("Z-Change. new_z=%.2f old_z=%.2f last_z=%.2f notification_height=%.2f notification_time=%d",
			self.z,
			payload['old'],
			self.last_z,
			self.main._settings.get_float(['notification_height']),
			self.main._settings.get_int(['notification_time']))
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
		kwargs['with_image'] = self.main._settings.get(['messages',str(kwargs['event']),'image'])
		self._logger.debug("Printer Status" + str(status))
		# define locals for string formatting
		z = self.z
		event = kwargs['event']
		temps = self.main._printer.get_current_temperatures()
		self._logger.debug("TEMPS - " + str(temps))
		bed_temp = temps['bed']['actual'] if 'bed' in temps else 0.0
		bed_target = temps['bed']['target'] if 'bed' in temps else 0.0 
		e1_temp = temps['tool0']['actual'] if 'tool0' in temps else 0.0
		e1_target = temps['tool0']['target'] if 'tool0' in temps else 0.0
		e2_temp = temps['tool1']['actual'] if 'tool1' in temps else 0.0
		e2_target = temps['tool1']['target'] if 'tool1' in temps else 0.0
		percent = int(status['progress']['completion'] or 0)
		time_done = octoprint.util.get_formatted_timedelta(datetime.timedelta(seconds=(status['progress']['printTime'] or 0)))
		time_left = octoprint.util.get_formatted_timedelta(datetime.timedelta(seconds=(status['progress']['printTimeLeft'] or 0)))
		if status['progress']['printTimeLeft'] == None:
			time_left = gettext('[Unknown]')
		file = ""
		if "file" in payload: file = payload["file"]
		if "gcode" in payload: file = payload["gcode"]
		if "filename" in payload: file = payload["filename"]
		emo = EmojiFormatter(self.main)
		try:
			# call format with emo class object to handle emojis, otherwise use locals
			message = self.main._settings.get(["messages",kwargs['event'],"text"]).format(emo,**locals())
		except Exception as ex:
			self._logger.debug("Exception on formatting message: " + str(ex))
			message =  self.main.gEmo('warning') + " ERROR: I was not able to format the Notification for '"+kwargs['event']+"' properly. Please open your OctoPrint settings for " + self.main._plugin_name + " and check message settings for '" + kwargs['event'] + "'."
		self._logger.debug("Sending Notification: " + message)
		# Do we want to send with Markup?
		kwargs['markup'] = self.main._settings.get(["messages",kwargs['event'],"markup"]) 
		# finally send MSG
		self.main.send_msg(message, **kwargs)

		if self.track:
			self.main.track_action("notification/" + kwargs['event'])
		self.track = True

	# Helper to determine if notification will be send on gcode ZChange event
	# depends on notification time and notification height
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