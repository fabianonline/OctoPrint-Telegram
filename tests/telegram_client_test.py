from __future__ import absolute_import
import ddt
import unittest
import logging
import requests
from octoprint_telegram.telegramClient import *
from mock import MagicMock, patch

@ddt.ddt
class TelegramClientTests(unittest.TestCase):
	def setUp(self):
		self.client = TelegramClient("TOKEN")
	
	def mock_default_response(self, mock):
		mock.return_value.status_code = 200
		mock.return_value.headers = {"content-type": "application/json"}
		mock.return_value.json.return_value = {'ok': True, 'result': []}
	
	@ddt.data(
		{},
		{"params": "abc", "wait_for_timeout": True}
	)	
	def test_get(self, kwargs):
		self.client._request = MagicMock()
		self.client._get("getUpdates", **kwargs)
		self.client._request.assert_called_with("GET", "getUpdates", **kwargs)
	
	@ddt.data("GET", "POST", "DELETE")
	def test_request_setting_the_correct_method(self, method):
		with patch('requests.request') as mock:
			self.mock_default_response(mock)
			self.client._request(method, "path")
			mock.assert_called_with(method, "https://api.telegram.org/bot_TOKEN/path")
	
	@ddt.data("text/html", "application/xml")
	def test_request_with_wrong_content_types(self, content_type):
		with patch('requests.request') as mock:
			self.mock_default_response(mock)
			mock.return_value.headers = {"content-type": content_type}
			with self.assertRaises(TelegramUnexpectedContentTypeException):
				self.client._request("get", "path")
	
	@ddt.data(400, 403, 404, 500)
	def test_request_with_wrong_status_code(self, status):
		with patch('requests.request') as mock:
			self.mock_default_response(mock)
			mock.return_value.status_code = status
			with self.assertRaises(TelegramStatuscodeNotOkException):
				self.client._request("get", "path")		
	
	@ddt.data(
		{'ok': False, 'result': []},
		{'foo': 'bar', 'result': []}
	)
	def test_request_without_ok(self, json):
		with patch('requests.request') as mock:
			self.mock_default_response(mock)
			mock.return_value.json.return_value = json
			with self.assertRaises(TelegramNotOkException):
				self.client._request("get", "path")

	@ddt.data(
		{'ok': True, 'result': None},
		{'ok': True, 'result': False},
		{'ok': True, 'result': []},
		{'ok': True, 'result': 0}
	)
	def test_request_with_result(self, json):
		with patch('requests.request') as mock:
			self.mock_default_response(mock)
			mock.return_value.json.return_value = json
			try:
				self.client._request("get", "path")
			except TelegramNoDataException:
				self.fail("Caught unexpected TelegramNoDataException")
	
	def test_request_without_result(self):
		with patch('requests.request') as mock:
			self.mock_default_response(mock)
			mock.return_value.json.return_value = {'ok': True}
			with self.assertRaises(TelegramNoDataException):
				self.client._request("get", "path")
