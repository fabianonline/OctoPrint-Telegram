/*
 * View model for OctoPrint-Telegram
 *
 * Author: Fabian Schlenz
 * License: AGPLv3
 */
$(function() {
    function TelegramViewModel(parameters) {
        var self = this;

        // assign the injected parameters, e.g.:
        // self.loginStateViewModel = parameters[0];
        self.settings = parameters[0];
        console.log(self.settings);

        // TODO: Implement your plugin's view model here.
        
        self.listHelper = new ItemListHelper(
            "known_chats",
            {},
            {},
            "",
            [],
            [],
            999);
        
        self.requestData = function() {
            $.ajax({
                url: API_BASEURL + "plugin/telegram",
                type: "GET",
                dataType: "json",
                success: self.fromResponse
            });
        };
        
        self.fromResponse = function(response) {
            var entries = response.known_chats;
            if (entries === undefined) return;
            self.listHelper.updateItems(entries);
        };
        
        self.onSettingsShown = function() {
            self.requestData();
        }
    }

    // view model class, parameters for constructor, container to bind to
    OCTOPRINT_VIEWMODELS.push([
        TelegramViewModel,

        // e.g. loginStateViewModel, settingsViewModel, ...
        [ "settingsViewModel" ],

        // e.g. #settings_plugin_telegram, #tab_plugin_telegram, ...
        [ '#settings_plugin_telegram' ]
    ]);
});
