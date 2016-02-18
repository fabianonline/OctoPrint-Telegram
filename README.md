# OctoPrint-Telegram

This plugin integrates Telegram Messenger with Octoprint. It sends messages (with photos if available) on print start, end and failure. Also it sends messages during the print at configurable intervals. That way you don't have to remember to regularly have a look at the printing process.
Also, you can control Octoprint via messages. Send `/status` to get the current printer status or `/abort` to abort the current print. Send `/help` for a list of all recognized events.

## Setup

Install via the bundled [Plugin Manager](https://github.com/foosel/OctoPrint/wiki/Plugin:-Plugin-Manager)
or manually using this URL:

    https://github.com/fabianonline/OctoPrint-Telegram/archive/stable.zip

To allow the plugin to send messages via telegram, you have to register a telegram bot. Follow these steps:

* Contact [@botfather](http://telegram.me/botfather) in Telegram Messenger.
* Send `/newbot`. Enter a name for the bot, e.g. "Fabians Octoprinter Bot". Then enter a username for the bot, e.g. "FabiansOctoprinterBot". This username has to end in "bot".
* The Botfather hands you a token. You need this to use your bot. Keep this token secret!
* While you're there, you could also (these steps are optional!):
 * Give your bot a nice profile picture. Send `/setuserpic`, select the bot and send the Octoprint logo.
 * Tell the Botfather which commands are available. This enables Telegram to auto-complete commands to your bot. Send `/setcommands`, select the bot and then send this (one message with multiple lines):
 ```
 abort - Aborts the currently running print.
 shutup - Disables automatic notifications till the next print ends.
 imsorrydontshutup - The opposite of /shutup - Makes the bot talk again.
 status - Sends the current status including a photo.
 help - Displays the help.
 settings - Display and modify settings.
 ```
* Send a message to your new bot. Any message is okay, Telegram's default `/start` is fine as well.
* Now check the configuration.


## Configuration

* Configuration is done via Octoprint's settings dialog.
* Token: Enter your bot token here. You got this from @botfather, when you created your bot there.
* Chat-ID: Which Telegram chat the plugin uses for communication. Commands from other chats are ignored, so you don't have to worry about other people controlling your Octoprint. Known chats (chats that have been active during the time octoprint is running) are listed below - find your chat and copy the ID into this field. If you're missing a chat in the list of known chats, close the settings, send any message to your bot and then re-open the settings. It should now be listed.
* Send notification every: Whenever the current z value grows by this value (or more) or the given time has passed since the last notification, a message will be sent.
 * Setting the height to 1.0mm would send messages at z=1.0, z=2.0, z=3.0 and so on.
 * Having the height at 1.0mm with a layer height of 0.3 would send messages at z=1.2, z=2.4, z=3.6 and so on.
 * Setting the time or height to `0` disables those checks. Setting both values to `0` completely disables automatic notifications while printing.
* You can set if you want messages at print start, finish and failure events.
* You can change the messages. Usable variables are:
 * `{file}` (only usable while printing) - The currently printing file.
 * `{z}` (only for height change events) - The current z value.
 * `{percent}` (only useful for height change notifications) - The current percentage of the print progress.
 * `{time_done}`, `{time_left}` (only useful for height change events) - Time done / left in the print.
 * `{bed_temp}`, `{e1_temp}`, `{e2_temp}` - Temperatures of bed, extruder 1 and extruder 2.
 * `{bed_target}`, `{e1_target}`, `{e2_target}` - Target temperatures of bed, extruder 1 and extruder 2.