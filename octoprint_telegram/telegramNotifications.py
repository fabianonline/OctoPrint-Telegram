from __future__ import absolute_import
import time, datetime, logging
import octoprint.util
from flask.ext.babel import gettext

###################################################################################################
# Here you find the known notification messages and their handles.
# The only way to start a messageHandle should be via on_event() in __init__.py 
# If you want to add/remove notifications read the following:
#
#
# 	telegramMsgDict {  }
#	
# 		telegramMsgDict contains the Message Settings. For each message there is a object as follows:
# 		<MessageName>: {'text': <MessageText>, 'image': <Boolean> [,'no_setting':<Boolean>, 'bind_msg': <BindMessageName>]}
#		
# 		- MessageName: 	The name of the Message. You can hook on octoprint events by choosing the name 
# 						of the event you want to handle. You can find a list of events here:
# 						http://docs.octoprint.org/en/master/events/index.html#sec-events-available-events
#
# 		- 'text': <MessageText>: 	The text which will be sent with the notification. yo can use some 
# 									variables in the text via .format(**locals()). Even emojis are possible
# 									See _sendNotification() below for more details
#
# 		- 'image': <Boolean>: 	if this is true a snapshot will be send with the message	
#		
#		Optional:
#
#		- 'no_setting': <Boolean>: if this value exists (true or false does not matter) no checkbox for 
#						enable/disable of this notification will be showen in the notification settings 
#						in octoprint. This is used for messages which will be triggered by the user, so
#						he wants to remove them when he triggers them. If you use this messages, you have
#						to - YOU HAVE TO - pass the chat_id when calling them or it will be send to all 
#						users with notifications enabled. Can cause strange behavior.
#						In telegrammCommands.py cmdStatus() you will see how to use it.
#						StatusPrinting ans StatusNotPrinting are using this feature. 
#
#		- 'bind_msg': <bindMessageName>: This option will bind this message to an other message. So it shares
#										 text and image setting with the message given by it's name as string.
#										 So when this notification is sent, it will contain the same content
#										 as the message bound to will. Also no extra edit box is shown in the
#										 settings dialog, but the messageName will be shown beside the box of
#										 the bound message.
#										 StatusPrinting and ZChange are using this feature.
#
#
#
#
# 	The TMSG class handles the messages. There is an other dict - msgCmdDict{} - which will bind the messageName 
# 	to the corresponding messageHandler.
#
#		Each messageHandler must look something like this:
#
#		def msg<messageName>(self, event, payload, **kwargs):
#			kwargs['event'] = self._prepMsg(event)
#			#your handler code
#			self._sendNotification(payload, **kwargs)
#
#		This means you should name your hanlder like your message with 'msg' as prefix
#		If your message is named MyMessage, then your handler should be named msgMyMessage
#		'event' argument contains the name of the event which called the handler
#		In 'payload' argument you get the payload of the octoprint event if it is one. See link mentioned above.
#		it is !important! to include the two lines of code shown above
#			- the call on _prepMsg will do message binding. should be done as first line.
#			  even if your message is not bound, call it. so if you ever change it in 
#			  telegramMsgDict you won't forget. Also it will setup z-info for message parsing
#
#			- at the end of the you have to call _sendNotification with the shown arguments to start parsing and sending of the message
#
#
#
# 	!!!!!!!!!!!!!!!!!!! IT IS IMPORTANT TO DO THIS !!!!!!!!!!!!!!!!!
# 	If you add and or del one ore more notifications, you have to increment the settings
#	version counter in get_ettings_version() in __init__.py. This will start settings migration
#	to add/remove notification settings to/from users and updates message settings on next startup of octoprint.
# 	!!!!!!!!!!!!!!!!!!! IT IS IMPORTANT TO DO THIS !!!!!!!!!!!!!!!!!
#
#
#
# 	To ADD a Notification:
# 		- add an message object to telegramMsgDict
# 		- add a handler bind to msgCmdDict in class TMSG
# 		- add a handler method to the TMSG class
#
# 	To REMOVE a Notivication:
# 		- do above in reverse
#
#	ON BOTH DO:
#	- increment plugin version
#
#
#
#####################################################################################################################################################




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
				'no_setting': True
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
		kwargs['with_image'] = self.main._settings.get(['messages',str(kwargs['event']),'image'])
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
		emo = {}
		for k in self.main.emojis:
			emo[k] = self.main.gEmo(k).encode("utf-8")

		message = self.main._settings.get(["messages",kwargs['event'],"text"]).format(**locals())
		self._logger.debug("Sending Notification: " + message)
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