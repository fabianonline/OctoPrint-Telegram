from __future__ import absolute_import
import logging, sarge, hashlib
import octoprint.filemanager
from flask.ext.babel import gettext
from .telegramNotifications import telegramMsgDict

################################################################################################################
# This class handles received commands/messages (commands in the following). commandDict{} holds the commands and their behavior.
# Each command has its own handler. If you want to add/del commands, read the following:
#
#
# 	commandDict{}
#
# 	The commandDict holds the command objects which define the known commands. 
# 	Each object looks like the following:
# 	<commandName>: { 'cmd': <commandHandle> [, 'bind_none': <Boolean>, 'bind_cmd': <bindCmdName>]}
#
# 		- <commandName>: The name of the command corresponds to the message text received.
# 						 If you use emojis in commands, than you ALWAYS have to define
# 						 a second object and set the command name to the same text without emojis.
# 						 Otherwise the 'Send emojis" option won't work properly.
# 						 The other values of the two objects should be the same.
# 						 See " Enter height" ans " Enter time" as example.
#
# 		- 'cmd': <commandHandle>: Here you have to point to the message handle method
#
# 		Optional:
#
# 		- 'bind_none': <Boolean>: Sets the authorization for the command ALWAYS TRUE for EVERY user/group.
# 								  So if accept_commands is activated for a user/group he is automatically 
# 								  able to do this command.
# 								  This is used to hide the command in user command authorization settings.
# 								  It is only used for non critical commands: Yes, No and Cancel which only
# 								  respond with a text message and wont cause any unwanted action.
#
# 		- 'bind_cmd': <bindCmdName>: This binds the authorization for the command to the authorization of
# 									 the given bind command. So if the bind command is changed in settings,
# 									 this command will be changed to the same value. This applies individual
# 									 each user/group setting.
# 									 The command is also hidden in user command authorization settings.
# 									 This otion is for commands which depend on other commands like
# 									 the settings. See "/settings", "Change height", "Change time" etc.
#
#
# 	commandHandler
#
# 	This is a method to handle the command and to execute desired actions. It should always at minimum look as follows:
#
# 	def cmd<commandName>(self,chat_id,**kwargs):
# 		self.main.send_msg(responseMessage,chatID=chat_id)
#
# 	The Name of the method should be the name of the command with 'cmd' as prefix.
# 	At least a response should be send to the user. so do a call on self.main.send_msg()
# 	with a responseMessage. YOU HAVE TO pass also the chat_id the handler got when called.
# 	This ensures that always the right user gets the response.
#
# 	!!!!!!!!!!!!!!!!!!! IT IS IMPORTANT TO DO THIS !!!!!!!!!!!!!!!!!
# 	If you add and or del one ore more commands, you have to increment the settings
#	version counter in get_ettings_version() in __init__.py.
# 	This will start settings migration to add/remove command settings to/from users.
# 	!!!!!!!!!!!!!!!!!!! IT IS IMPORTANT TO DO THIS !!!!!!!!!!!!!!!!!
#
#
#
# 	To ADD a command:
# 		- add an command object to commandDict
# 		- add a handler method to the TCMD class
#
# 	To REMOVE a Notivication:
# 		- do above in reverse
#
# 	ON BOTH DO:
# 	- increment plugin version
#####################################################################################################################


class TCMD():
	def __init__(self, main):
		self.main = main
		self.gEmo = self.main.gEmo
		self.tmpSysCmd = {}
		self._logger = main._logger.getChild("TCMD")
		self.commandDict = {
			gettext("Yes"): {'cmd': self.cmdYes, 'bind_none': True},
			gettext("Cancel"): {'cmd': self.cmdNo, 'bind_none': True},
			gettext("No"):  {'cmd': self.cmdNo,'bind_none': True},
			gettext("Change height"):  {'cmd': self.cmdChgHeight, 'bind_cmd': '/settings'},
			(self.gEmo('enter') + gettext(" Enter height")):  {'cmd': self.cmdSetHeight, 'bind_cmd': '/settings'},
			gettext(" Enter height"):  {'cmd': self.cmdSetHeight, 'bind_cmd': '/settings'},
			gettext("Change time"):  {'cmd': self.cmdChgTime, 'bind_cmd': '/settings'},
			(self.gEmo('enter') + gettext(" Enter time")):  {'cmd': self.cmdSetTime, 'bind_cmd': '/settings'},
			gettext(" Enter time"):  {'cmd': self.cmdSetTime, 'bind_cmd': '/settings'},
			gettext("Start print"):  {'cmd': self.cmdStartPrint, 'bind_cmd': '/print'},
			gettext("Stop print"):  {'cmd': self.cmdHalt, 'bind_cmd': '/print'},
			gettext("Don't print"):  {'cmd': self.cmdDontPrint, 'bind_cmd': '/print'},
			gettext("Do System Command"): {'cmd': self.cmdSysRun, 'bind_cmd': '/sys'},
			'/print_':  {'cmd': self.cmdRunPrint, 'bind_cmd': '/print'},
			'/test':  {'cmd': self.cmdTest},
			'/status':  {'cmd': self.cmdStatus},
			'/abort':  {'cmd': self.cmdAbort},
			'/settings':  {'cmd': self.cmdSettings},
			'/shutup':  {'cmd': self.cmdShutup},
			'/imsorrydontshutup':  {'cmd': self.cmdNShutup},
			'/list':  {'cmd': self.cmdList},
			'/print':  {'cmd': self.cmdPrint},
			'/upload':  {'cmd': self.cmdUpload},
			'/help':  {'cmd': self.cmdHelp},
			'/sys': {'cmd': self.cmdSys},
			'/sys_': {'cmd': self.cmdSysReq, 'bind_cmd': '/sys'},
			'/ctrl': {'cmd': self.cmdCtrl},
			'/ctrl_': {'cmd': self.cmdCtrlRun, 'bind_cmd': '/ctrl'}
		}

	def cmdYes(self,chat_id,**kwargs):
		self.main.send_msg(gettext("Alright."),chatID=chat_id)

	def cmdNo(self,chat_id,**kwargs):
		if chat_id in self.tmpSysCmd:
			del self.tmpSysCmd[chat_id]
		self.main.send_msg(gettext("Maybe next time."),chatID=chat_id)

	def cmdTest(self,chat_id,**kwargs):
		self.main.send_msg(self.gEmo('question') + gettext(" Is this a test?\n\n") , responses=[gettext("Yes"), gettext("No")],chatID=chat_id)

	def cmdStatus(self,chat_id,**kwargs):
		if not self.main._printer.is_operational():
			self.main.send_msg(self.gEmo('warning') + gettext(" Not connected to a printer."),chatID=chat_id)
		elif self.main._printer.is_printing():
			self.main.on_event("StatusPrinting", {},chatID=chat_id)
		else:
			self.main.on_event("StatusNotPrinting", {},chatID=chat_id)

	def cmdSettings(self,chat_id,**kwargs):
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
		if self.main._printer.is_printing():
			self.main.send_msg(self.gEmo('question') + gettext(" Really abort the currently running print?"), responses=[gettext("Stop print"), gettext("Cancel")],chatID=chat_id)
		else:
			self.main.send_msg(self.gEmo('warning') + gettext(" Currently I'm not printing, so there is nothing to stop."),chatID=chat_id)

	def cmdHalt(self,chat_id,**kwargs):
		self.main.send_msg(self.gEmo('info') + gettext(" Aborting the print."),chatID=chat_id)
		self.main._printer.cancel_print()

	def cmdDontPrint(self, chat_id, **kwargs):
		self.main._printer.unselect_file()
		self.main.send_msg(gettext("Maybe next time."),chatID=chat_id)
							
	def cmdShutup(self,chat_id,**kwargs):
		if chat_id not in self.main.shut_up:
			self.main.shut_up[chat_id] = True
		self.main.send_msg(self.gEmo('noNotify') + gettext(" Okay, shutting up until the next print is finished." + self.gEmo('shutup')+" Use /imsorrydontshutup to let me talk again before that. "),chatID=chat_id)

	def cmdNShutup(self,chat_id,**kwargs):
		if chat_id in self.main.shut_up:
			del self.main.shut_up[chat_id]
		self.main.send_msg(self.gEmo('notify') + gettext(" Yay, I can talk again."),chatID=chat_id)

	def cmdPrint(self,chat_id,**kwargs):
		self.main.send_msg(self.gEmo('info') + " Use /list to get a list of files and click the command beginning with /print after the correct file.",chatID=chat_id)

	def cmdRunPrint(self,chat_id,parameter,**kwargs):
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
			self.main.send_msg(self.gEmo('info') + gettext(" Okay. The file %(file)s is loaded.\n\n"+self.gEmo('question')+" Do you want me to start printing it now?", file=data['job']['file']['name']), responses=[gettext("Start print"), gettext("Don't print")],chatID=chat_id)

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
		files = self.get_flat_file_tree()
		self.main.send_msg(self.gEmo('save') + " File List:\n\n" + "\n".join(files) + "\n\n"+self.gEmo('info')+" You can click the command beginning with /print after a file to start printing this file.",chatID=chat_id)

	def cmdUpload(self,chat_id,**kwargs):
		self.main.send_msg(self.gEmo('info') + " To upload a gcode file, just send it to me.",chatID=chat_id)

	def cmdSys(self,chat_id,**kwargs):
		message = self.gEmo('info') + " You have to pass a System Command. The following System Commands are known.\n(Click to execute)\n\n"
		empty = True
		for action in self.main._settings.global_get(['system','actions']):
			empty = False
			if action['action'] != "divider":
				message += action['name'] + "\n/sys_" + self.hashMe(action['action'], 6) + "\n"
			else:
				message += "---------------------------\n"
		if empty: message += "No System Commands found..."
		self.main.send_msg(message,chatID=chat_id)

	def cmdSysReq(self,chat_id,parameter,**kwargs):
		if parameter is None or parameter is "":
			self.cmdSys(chat_id, **kwargs)
			return
		actions = self.main._settings.global_get(['system','actions'])
		command = next((d for d in actions if 'action' in d and self.hashMe(d['action'], 6) == parameter) , False)
		if command :
			self.tmpSysCmd.update({chat_id: parameter})
			self.main.send_msg(self.gEmo('question') + " Really execute "+command['name']+"?",responses=[gettext("Do System Command"), gettext("Cancel")],chatID=chat_id)
			return
		self.main.send_msg(self.gEmo('warning') + " Sorry, i don't know this System Command.",chatID=chat_id)

	def cmdSysRun(self,chat_id,**kwargs):
		if chat_id not in self.tmpSysCmd:
			return
		parameter = self.tmpSysCmd[chat_id]
		del self.tmpSysCmd[chat_id]
		actions = self.main._settings.global_get(['system','actions'])
		action = next((i for i in actions if self.hashMe(i['action'], 6) == parameter), False)
		### The following is taken from OctoPrint/src/octoprint/server/api/__init__.py -> performSystemAction()
		async = action["async"] if "async" in action else False
		ignore = action["ignore"] if "ignore" in action else False
		self._logger.info("Performing command: %s" % action["command"])
		try:
			# we run this with shell=True since we have to trust whatever
			# our admin configured as command and since we want to allow
			# shell-alike handling here...
			p = sarge.run(action["command"], stderr=sarge.Capture(), shell=True, async=async)
			if not async:
				if p.returncode != 0:
					returncode = p.returncode
					stderr_text = p.stderr.text
					self._logger.warn("Command failed with return code %i: %s" % (returncode, stderr_text))
					self.main.send_msg(self.gEmo('warning') + " Command failed with return code %i: %s" % (returncode, stderr_text),chatID=chat_id)
					return
			self.main.send_msg(self.gEmo('check') + " Command " + action["name"] + " executed." ,chatID=chat_id)
		except Exception, e:
			self._logger.warn("Command failed: %s" % e)
			self.main.send_msg(self.gEmo('warning') + " Command failed with exception: %s!" % e,chatID = chat_id)

	def cmdCtrl(self,chat_id,**kwargs):
		message = self.gEmo('info') + " You have to pass a Printer Control Command. The following Printer Controls are known.\n(Click to execute)\n\n"
		empty = True
		for action in self.get_controls_recursively():
			empty=False
			message += action['name'] + "\n/ctrl_" + action['hash'] + "\n"
		if empty: message += "No Printer Control Command found..."
		self.main.send_msg(message,chatID=chat_id)

	def cmdCtrlRun(self,chat_id,parameter,**kwargs):
		if parameter is None or parameter is "":
			self.cmdCtrl(chat_id, **kwargs)
			return
		actions = self.get_controls_recursively()
		command = next((d for d in actions if d['hash'] == parameter), False)
		if command:
			if type(command['command']) is type([]):
				for key in command['command']:
					self.main._printer.commands(key)
			else:
				self.main._printer.commands(command['command'])
			self.main.send_msg(self.gEmo('check') + " Control Command " + command['name'] + " executed." ,chatID=chat_id)
		else:
			self.main.send_msg(self.gEmo('warning') + " Control Command ctrl_" + parameter + " not found." ,chatID=chat_id)

	def cmdHelp(self,chat_id,**kwargs):
		self.main.send_msg(self.gEmo('info') + gettext(" You can use following commands:\n\n"
		                           "/abort - Aborts the currently running print. A confirmation is required.\n"
		                           "/shutup - Disables automatic notifications till the next print ends.\n"
		                           "/imsorrydontshutup - The opposite of /shutup - Makes the bot talk again.\n"
		                           "/status - Sends the current status including a current photo.\n"
		                           "/settings - Displays the current notification settings and allows you to change them.\n"
		                           "/list - Lists all the files available for printing and lets you start printing them.\n"
		                           "/print - Lets you start a print. A confirmation is required.\n"
		                           "/upload - You can just send me a gcode file to save it to my library."
		                           "/sys - Execute Octoprint System Comamnds"
		                           "/ctrl - Use self defined controls from Octoprint"),chatID=chat_id)

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

	def get_controls_recursively(self, tree = None, base = "", first = ""):
		array = []
		if tree == None:
			tree = self.main._settings.global_get(['controls'])
		for key in tree:
			if type(key) is type({}):
				if base == "":
					first = " "+key['name']+" "
				if 'children' in key:
					array.extend(self.get_controls_recursively(key['children'], base + " " + key['name'],first))
				elif ('commands' in key or 'command' in key) and not 'confirm' in key and not 'regex' in key and not 'input' in key and not 'script' in key:
					# rename 'commands' to 'command' so its easier to handle later on
					newKey = {}
					command = key['command'] if 'command' in key else key['commands']
					newKey['name'] = base.replace(first,"") + " " + key['name']
					newKey['hash'] = self.hashMe(base + " " + key['name'] + str(command), 6)
					newKey['command'] = command
					array.append(newKey)
		return array

	def hashMe(self, text, length):
		return hashlib.md5(text).hexdigest()[0:length]