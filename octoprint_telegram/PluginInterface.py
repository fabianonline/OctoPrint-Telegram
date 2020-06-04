class PluginInterface:
	def __init__(self, main):
		self.main = main
		self.hooks = []
	
	def sendText(self, text=""):
		return self.main.send_msg(text)
	
	def registerHook(self, hook):
		self.hooks.push(hook)
		return True

	def process_hooks(self, command, parameter):
		success = False
		for hook in self.hooks:
			result = hook(command, parameter)
			success = success or result
		return success
