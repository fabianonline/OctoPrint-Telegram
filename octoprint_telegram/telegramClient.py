import requests, json

class TelegramException(Exception):
	pass

class TelegramStatuscodeNotOkException(TelegramException):
	pass

class TelegramUnexpectedContentTypeException(TelegramException):
	pass

class TelegramNotOkException(TelegramException):
	pass
	
class TelegramUpdateWithMissingUpdateIdException(TelegramException):
	pass

class TelegramNoDataException(TelegramException):
	pass

class TelegramClient:
	def __init__(self, token):
		self.token = token
		self.url = "https://api.telegram.org/bot_" + token
	
	def _get(self, path, **kwargs):
		return self._request("GET", path, **kwargs)
	
	def _request(self, method, path, **kwargs):
		response = requests.request(method, self.url + "/" + path, **kwargs)
		
		if response.status_code != 200:
			raise TelegramStatuscodeNotOkException()
		if response.headers["content-type"] != 'application/json':
			raise TelegramUnexpectedContentTypeException()
		
		json = response.json()
		if not 'ok' in json or not json['ok']:
			raise TelegramNotOkException()
		
		if not 'result' in json:
			raise TelegramNoDataException()
			
		return json['result']
	
	def getUpdates(self, offset=0, timeout=30):
		new_offset = None
		result = self._get("getUpdates", params={'offset':offset, 'timeout': timeout}, allow_redirects=False, timeout=timeout+10)
		
		if result is None:
			raise TelegramNotOkException()
		
		if len(result)>0:
			if not 'update_id' in result[0]:
				raise TelegramUpdateWithMissingUpdateIdException()
			new_offset = result[0]['update_id']
			
		return new_offset, result
