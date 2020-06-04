from __future__ import absolute_import
import ddt
import unittest
import logging
from octoprint_telegram import TelegramListener, TelegramPlugin
from octoprint_telegram.telegramCommands import TCMD
from mock import MagicMock

@ddt.ddt
class TelegramListenerTests(unittest.TestCase):
	def setUp(self):
		parent = TelegramPlugin(5)
		logger = logging.getLogger("octoprint.plugin.telegram.testing")
		parent._logger = MagicMock(return_value=logger)
		parent.tcmd = TCMD(parent)
		self.listener = TelegramListener(parent)
		
	@ddt.data(
		("/abort", ("/abort", "")),
		("/abort@my_bot", ("/abort", "")),
		("/files_abc", ("/files", "abc")),
		("/files_abc_def", ("/files", "abc_def")),
		("/files_abc_def@my_bot_foo", ("/files", "abc_def"))
	)
	@ddt.unpack
	def test_extractCommandFromText(self, message, expected):
		result = self.listener.extractCommandFromText(message)
		self.assertEqual(result, expected)

	def test_handleTextMessage(self):
		message = {'message': {'text': "/abort_yes@my_bot"}}
		self.listener.main.send_msg = MagicMock()
		self.listener.extractCommandFromText = MagicMock(return_value=("/abort", "yes"))
		self.listener.main.isCommandAllowed = MagicMock(return_value=True)
		self.listener.main._settings = MagicMock()
		self.listener.main.track_action = MagicMock()
		abort = MagicMock()
		self.listener.main.tcmd.commandDict["/abort"]["cmd"] = abort
		
		self.listener.handleTextMessage(message, 12, 34)
		
		self.listener.main.isCommandAllowed.assert_called_with(12, 34, "/abort")
		self.listener.extractCommandFromText.assert_called_with("/abort_yes@my_bot")
		self.listener.main.send_msg.assert_not_called()
		abort.assert_called()
