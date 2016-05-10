from __future__ import absolute_import
import logging
import octoprint.filemanager
from flask.ext.babel import gettext
from .telegramNotifications import telegramMsgDict

class TCMD():
	def __init__(self, main):
		self.main = main
		self.gEmo = self.main.gEmo
		self._logger = main._logger.getChild("listener")
		self.commandDict = {
			gettext("Yes"): {'cmd': self.cmdYes, 'bind_none': True},
			gettext("Cancel"): {'cmd': self.cmdNo, 'bind_none': True},
			gettext("No"):  {'cmd': self.cmdNo,'bind_none': True},
			gettext("Change height"):  {'cmd': self.cmdChgHeight, 'bind_cmd': '/settings'},
			(self.gEmo('enter') + gettext(" Enter height")):  {'cmd': self.cmdSetHeight, 'bind_cmd': '/settings'},
			gettext("Enter height")):  {'cmd': self.cmdSetHeight, 'bind_cmd': '/settings'},
			gettext("Change time"):  {'cmd': self.cmdChgTime, 'bind_cmd': '/settings'},
			(self.gEmo('enter') + gettext(" Enter time")):  {'cmd': self.cmdSetTime, 'bind_cmd': '/settings'},
			gettext("Enter time")):  {'cmd': self.cmdSetTime, 'bind_cmd': '/settings'},
			gettext("Start print"):  {'cmd': self.cmdStartPrint, 'bind_cmd': '/print'},
			gettext("Stop print"):  {'cmd': self.cmdHalt, 'bind_cmd': '/print'},
			'/print_':  {'cmd': self.cmdRunPrint, 'bind_cmd': '/print'},
			'/test':  {'cmd': self.cmdTest},
			'/status':  {'cmd': self.cmdStatus},
			'/abort':  {'cmd': self.cmdAbort},
			'/settings':  {'cmd': self.cmdSettings},
			'/shutup':  {'cmd': self.cmdShutup},
			'/imsorrydontshutup':  {'cmd': self.cmdNShutup},
			'/list':  {'cmd': self.cmdList},
			'/print':  {'cmd': self.cmdPrint},
			'/light':  {'cmd': self.cmdLight},
			'/upload':  {'cmd': self.cmdUpload},
			'/darkness':  {'cmd': self.cmdDarkness},
			'/help':  {'cmd': self.cmdHelp}
		}

	def cmdYes(self,chat_id,**kwargs):
		self.main.send_msg(gettext("Alright."),chatID=chat_id)

	def cmdNo(self,chat_id,**kwargs):
		self.main.send_msg(gettext("Maybe next time."),chatID=chat_id)

	def cmdTest(self,chat_id,**kwargs):
		self.main.track_action("command/test")
		self.main.send_msg(self.gEmo('question') + gettext(" Is this a test?\n\n") , responses=[gettext("Yes"), gettext("No")],chatID=chat_id)

	def cmdStatus(self,chat_id,**kwargs):
		self.main.track_action("command/status")
		if not self.main._printer.is_operational():
			self.main.send_msg(self.gEmo('warning') + gettext(" Not connected to a printer."),chatID=chat_id)
		elif self.main._printer.is_printing():
			self.main.on_event("StatusPrinting", {},chatID=chat_id)
		else:
			self.main.on_event("StatusNotPrinting", {},chatID=chat_id)

	def cmdSettings(self,chat_id,**kwargs):
		self.main.track_action("command/settings")
		msg = self.gEmo('settings') + gettext(" Current notification settings are:\n\n\n"+self.gEmo('height')+" height: %(height)fmm\n\n"+self.gEmo('clock')+" time: %(time)dmin\n\n\n"+self.gEmo('question')+"Which value do you want to change?",
			height=self.main._settings.get_float(["notification_height"]),
			time=self.main._settings.get_int(["notification_time"]))
		self.main.send_msg(msg, responses=[gettext("Change height"), gettext("Change time"), gettext("Cancel")],chatID=chat_id)

	def cmdChgHeight(self,chat_id,**kwargs):
		self.main.send_msg(self.gEmo('enter') + " " + gettext("Enter height"), force_reply=True,chatID=chat_id)

	def cmdSetHeight(self,chat_id,parameter,**kwargs): 
		self.main._settings.set_float(['notification_height'], parameter, force=True)
		self.main.send_msg(self.gEmo('height') + gettext(" Notification height is now %(height)fmm.", height=self.main._settings.get_float(['notification_height'])),chatID=chat_id)

	def cmdChgTime(self,chat_id,**kwargs):
		self.main.send_msg(self.gEmo('enter') + " " +gettext("Enter time"), force_reply=True,chatID=chat_id)

	def cmdSetTime(self,chat_id,parameter,**kwargs):
		self.main._settings.set_int(['notification_time'], parameter, force=True)
		self.main.send_msg(self.gEmo('clock') + gettext(" Notification time is now %(time)dmins.", time=self.main._settings.get_int(['notification_time'])),chatID=chat_id)

	def cmdAbort(self,chat_id,**kwargs):
		self.main.track_action("command/abort")
		if self.main._printer.is_printing():
			self.main.send_msg(self.gEmo('question') + gettext(" Really abort the currently running print?"), responses=[gettext("Stop print"), gettext("Cancel")],chatID=chat_id)
		else:
			self.main.send_msg(self.gEmo('warning') + gettext(" Currently I'm not printing, so there is nothing to stop."),chatID=chat_id)

	def cmdHalt(self,chat_id,**kwargs):
		self.main.send_msg(self.gEmo('info') + gettext(" Aborting the print."),chatID=chat_id)
		self.main._printer.cancel_print()
							
	def cmdShutup(self,chat_id,**kwargs):
		self.main.track_action("command/shutup")
		if chat_id not in self.main.shut_up:
			self.main.shut_up[chat_id] = True
		self.main.send_msg(self.gEmo('noNotify') + gettext(" Okay, shutting up until the next print is finished." + self.gEmo('shutup')+" Use /imsorrydontshutup to let me talk again before that. "),chatID=chat_id)

	def cmdNShutup(self,chat_id,**kwargs):
		self.main.track_action("command/imsorrydontshutup")
		if chat_id in self.main.shut_up:
			del self.main.shut_up[chat_id]
		self.main.send_msg(self.gEmo('notify') + gettext(" Yay, I can talk again."),chatID=chat_id)

	def cmdPrint(self,chat_id,**kwargs):
		self.main.send_msg(self.gEmo('info') + " Use /list to get a list of files and click the command beginning with /print after the correct file.",chatID=chat_id)

	def cmdRunPrint(self,chat_id,parameter,**kwargs):
		self.main.track_action("command/print")
		self._logger.debug("Looking for hash: %s", parameter)
		destination, file = self.find_file_by_hash(parameter)
		self._logger.debug("Destination: %s", destination)
		self._logger.debug("File: %s", file)
		if file is None or parameter is None or parameter is "":
			self.main.send_msg(self.gEmo('warning') + " I'm sorry, but I couldn't find the file you wanted me to print. Perhaps you want to have a look at /list again?",chatID=chat_id)
			return
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
			self.main.send_msg(self.gEmo('info') + gettext(" Okay. The file %(file)s is loaded.\n\n"+self.gEmo('question')+" Do you want me to start printing it now?", file=data['job']['file']['name']), responses=[gettext("Start print"), gettext("No")],chatID=chat_id)

	def cmdStartPrint(self,chat_id,**kwargs):
		data = self.main._printer.get_current_data()
		if data['job']['file']['name'] is None:
			self.main.send_msg(self.gEmo('warning') + gettext(" Uh oh... No file is selected for printing. Did you select one using /list?"),chatID=chat_id)
			return
		if not self.main._printer.is_operational():
			self.main.send_msg(self.gEmo('warning') + gettext(" Can't start printing: I'm not connected to a printer."),chatID=chat_id)
			return
		if self.main._printer.is_printing():
			self.main.send_msg(self.gEmo('warning') + " A print job is already running. You can't print two thing at the same time. Maybe you want to use /abort?",chatID=chat_id)
			return
		self.main._printer.start_print()
		self.main.send_msg(self.gEmo('rocket') + gettext(" Started the print job."),chatID=chat_id)

	def cmdList(self,chat_id,**kwargs):
		self.main.track_action("command/list")
		files = self.get_flat_file_tree()
		self.main.send_msg(self.gEmo('save') + " File List:\n\n" + "\n".join(files) + "\n\n"+self.gEmo('info')+" You can click the command beginning with /print after a file to start printing this file.",chatID=chat_id)

	def cmdLight(self,chat_id,**kwargs):
		self.main._printer.commands("M42 P47 S255")
		self.main.send_msg("I put the lights on.",chatID=chat_id)

	def cmdDarkness(self,chat_id,**kwargs):
		self.main._printer.commands("M42 P47 S0")
		self.main.send_msg("Lights are off now.",chatID=chat_id)

	def cmdUpload(self,chat_id,**kwargs):
		self.main.track_action("command/upload_command_that_tells_the_user_to_just_send_a_file")
		self.main.send_msg(self.gEmo('info') + " To upload a gcode file, just send it to me.",chatID=chat_id)

	def cmdHelp(self,chat_id,**kwargs):
		self.main.track_action("command/help")
		self.main.send_msg(self.gEmo('info') + gettext(" You can use following commands:\n"
		                           "/abort - Aborts the currently running print. A confirmation is required.\n"
		                           "/shutup - Disables automatic notifications till the next print ends.\n"
		                           "/imsorrydontshutup - The opposite of /shutup - Makes the bot talk again.\n"
		                           "/status - Sends the current status including a current photo.\n"
		                           "/settings - Displays the current notification settings and allows you to change them."),chatID=chat_id)

	def newChat(self):
		return {'accept_commands' : False, 
				'send_notifications' : False, 
				'new': True, 
				'allow_users': False,
				'commands': {k: False for k,v in self.commandDict.iteritems()}, 
				'notifications': {k: False for k,v in telegramMsgDict.iteritems()}
				}


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