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
            {
                "title": function(a, b) {
                    if(a.title.toLocaleLowerCase() < b.title.toLocaleLowerCase()) return -1;
                    if(a.title.toLocaleLowerCase() > b.title.toLocaleLowerCase()) return 1;
                    return 0;
                }
            },
            {},
            "title",
            [],
            [],
            999);
        

        self.connection_state_str = ko.observable("Unknown");
        self.isloading = ko.observable(false);
        self.errored = ko.observable(false);
        self.token_state_str = ko.observable("Unknown");
	self.editChatDialog = undefined;        
	self.currChatID = ko.observable("Unknown");
        self.currChatTitle = ko.observable("Unknown");
        self.currChatPrivate = ko.observable(false);
        self.currChatCommands = ko.observable(false);
        self.currChatNotify = ko.observable(false);

        self.requestData = function() {
            self.isloading(true);
            $.ajax({
                url: API_BASEURL + "plugin/telegram",
                type: "GET",
                dataType: "json",
                success: self.fromResponse
            });
        };

        self.updateChat = function() {
            self.isloading(true);
            var data = {};
            data['command'] = "updateChat";
            data['chatNotify'] = self.currChatNotify();
            data['chatCmd'] = self.currChatCommands();
            data['ID'] = self.currChatID();
            console.log("Update Chat Data " + String(data['ID']));
            $.ajax({
                url: API_BASEURL + "plugin/telegram",
                type: "POST",
                dataType: "json",
                data: JSON.stringify(data),
                contentType: "application/json",
                success: self.fromResponse
            });
            self.editChatDialog.modal("hide");
        }
        
        self.testToken = function(data, event) {
            self.isloading(true);
            console.log("Testing token " + $('#settings_plugin_telegram_token').val());
            $.ajax({
                url: API_BASEURL + "plugin/telegram",
                type: "POST",
                dataType: "json",
                data: JSON.stringify({ "command": "testToken", "token": $('#settings_plugin_telegram_token').val()}),
                contentType: "application/json",
                success: self.testResponse
            });
        }
        
        self.testResponse = function(response) {
            self.isloading(false);
            self.token_state_str(response.connection_state_str);
            self.errored(!response.ok);
        }
        
        self.fromResponse = function(response) {
            self.isloading(false);
            if(response === undefined) return;
            if(response.hasOwnProperty("connection_state_str"))
                self.connection_state_str(response.connection_state_str);
            if(response.hasOwnProperty("connection_ok"))
                self.errored(!response.connection_ok);
            var entries = response.chats;
            if (entries === undefined) return;
            var array = [];
            for(var id in entries) {
                var data = entries[id];
                data['id'] = id;
                if(!('accept_commands' in data)) data['accept_commands'] = false;
                if(!('send_notifications' in data)) data['send_notifications'] = false;
                array.push(data);
            }
            self.listHelper.updateItems(array);
        };

        self.showEditChatDialog = function(data) {
            if (data === undefined) return;
            self.currChatTitle(data.title);
            self.currChatID(data.id);
            self.currChatPrivate(data.private);
            self.currChatNotify(data.send_notifications);
            self.currChatCommands(data.accept_commands);
            if(!self.currChatPrivate())
                document.getElementById("telegram-groupNotify").innerHTML="(only from known Users)";
	        self.editChatDialog.modal("show");
        }

        self.delChat = function(data) {
            if (data === undefined) return;
            if (confirm('Do you really want to delete ' + data.title)){
                self.isloading(true);
                data['command'] = "delChat";
                data['ID'] = data.id
                console.log("Delete Chat Data " + String(data['ID']));
                $.ajax({
                    url: API_BASEURL + "plugin/telegram",
                    type: "POST",
                    dataType: "json",
                    data: JSON.stringify(data),
                    contentType: "application/json",
                    success: self.fromResponse
                });
            }
        }

        self.onSettingsShown = function() {
            self.requestData();
            self.editChatDialog = $("#settings-telegramDialogEditChat");
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
