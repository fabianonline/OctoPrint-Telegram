$(function() {
    function GpioTelegramViewModel(parameters) {
        var self = this;

        self.settings = parameters[0];
        
        // constants
        self.possiblePins = ko.observableArray([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27]);
        self.pinModes = ko.observableArray(["Output", "Input"])
        self.possibleEvents = ko.observableArray([
            "Startup", "Shutdown", "ClientOpened", "ClientAuthed", "ClientClosed", "UserLoggedIn", "UserLoggedOut", "ConnectivityChanged",       //Server
            "Connecting", "Connected", "Disconnecting", "Disconnected", "Error", "PrinterStateChanged",  // Printer Communication
            "Upload",  "FileAdded", "FileRemoved", "FileMoved", "FolderAdded", "FolderRemoved", "FolderMoved", "UpdatedFiles", "MetadataAnalysisStarted", "MetadataAnalysisFinished", "FileSelected", "FileDeselected", "TransferStarted", "TransferDone",  // File handling
            "PrintStarted", "PrintFailed", "PrintDone", "PrintCancelling", "PrintCancelled", "PrintPaused", "PrintResumed", // Printing
            "PowerOn", "PowerOff", "Home", "ZChange", "Dwell", "Waiting", "Cooling", "Alert", "Conveyor", "Eject", "EStop", "FilamentChange", "PositionUpdate", "ToolChange", "CommandSuppressed", "InvalidToolReported", // GCode
            "CaptureStart", "CaptureDone", "CaptureFailed", "MovieRendering", "MovieDone", "MovieFailed", // TimeLapses
            "SlicingStarted", "SlicingDone", "SlicingCancelled", "SlicingFailed", "SlicingProfileAdded", "SlicingProfileModified", "SlicingProfileDeleted", // Slicing
            "SettingsUpdated", //Settings
            "PrinterProfileModified" // Printer Profile
        ])

        // Configs
        self.pinConfigs = ko.observableArray();
        self.logicConfigs = ko.observableArray();
        self.variables = ko.observableArray();
        
        // Helpers
        self.choosenOutputs = ko.observableArray([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27]);  
        self.choosenInputs = ko.observableArray([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27]);
        
        self.changed = ko.observable(false); // Check if something has Changed
        self.error = ko.observable(false); // Check if something has Changed

        // Tab
        self.buttons  = ko.observableArray();

        

        self.callChanged = function(obj, event){
            if(event.originalEvent){
                // User Changed something
                self.changed(true);
            }
        }

        // Copy settings to pinConfig
        self.onBeforeBinding = function(){
            self.pinConfigs(self.settings.settings.plugins.telegram.gpio_PinConfigs.slice(0));
            self.logicConfigs(self.settings.settings.plugins.telegram.gpio_LogicConfigs.slice(0));
            self.variables(self.settings.settings.plugins.telegram.gpio_Variables.slice(0));
            self.updateButtons();
        }


        // Copy settings to pinConfig
        self.onSettingsShown = function(){
            self.pinConfigs(self.settings.settings.plugins.telegram.gpio_PinConfigs.slice(0));
            self.logicConfigs(self.settings.settings.plugins.telegram.gpio_LogicConfigs.slice(0));
            self.variables(self.settings.settings.plugins.telegram.gpio_Variables.slice(0));
        }

        // Copy settings to pinConfig
        self.onSettingsHidden = function(){
            self.pinConfigs(self.settings.settings.plugins.telegram.gpio_PinConfigs.slice(0));
            self.logicConfigs(self.settings.settings.plugins.telegram.gpio_LogicConfigs.slice(0));
            self.variables(self.settings.settings.plugins.telegram.gpio_Variables.slice(0));
            self.updateButtons();
        }

        // Copy pinConfig to settings
        self.onSettingsBeforeSave = function(){
            self.settings.settings.plugins.telegram.gpio_PinConfigs(self.pinConfigs.slice(0));
            self.settings.settings.plugins.telegram.gpio_LogicConfigs(self.logicConfigs.slice(0));
            self.settings.settings.plugins.telegram.gpio_Variables(self.variables.slice(0));
            
        }

// Settings
        // Add an Default Pin to the List
        self.addGpioPin = function(){
            // create and push an new GPIO-Pin to the list
            pinData =  {
                pin: ko.observable(1),
                name: ko.observable("New Pin"),            // Both
                mode: ko.observable("Output"),             // Both
        
                activeState: ko.observable("high"),        // Output
                defaultState: ko.observable("off"),        // Output
                visibleInTelegram: ko.observable("true"),   // Output
                visibleInUI: ko.observable("true"),   

                edgeDetection: ko.observable("rising"),    // Input
                bounceTime: ko.observable(50),               // Input
                pullUpDown: ko.observable("none"),         // Input
                verified: ko.observable(false)    // Both
            };
            self.pinConfigs.push(pinData);
        }
        
        // Remove clicked Pin from List
        self.removeGpioPin = function (configuration){
            self.pinConfigs.remove(configuration);
        }

        self.addVariable = function(){
            variable = {
                name: ko.observable("Integername"),     // Name to be reffered
                value: ko.observable(0)                 // Defaultvalue
            }
            self.variables.push(variable);
        }

        self.removeVariable = function(configuration){
            self.variables.remove(configuration);
        }

        self.addLogic = function(){
            logic = {
                trigger: ko.observable("pin"),                 // Pin, Event, Variable
                triggerPin: ko.observable(0),                  // All
                triggerEvent: ko.observable("Startup"),
                triggerVariable : ko.observable(""),            // Name of Variable
                triggerVariableCondition: ko.observable(""),    // <, <= , =, >=, >, !=
                triggerVariableValue: ko.observable(0),         // Value of Trigger
                
                triggerDelay: ko.observable(0),                 // Delay before running the action


                type: ko.observable("output"),                 // All: possible: output, message, emergency, printer, variable
                pin: ko.observable(0),                         // Output
                pinMode: ko.observable("toggle"),              // Output => Enable / Disable / Toggle

                message: ko.observable("New Text Message"),
                sendVariable: ko.observable("false"),

                emergency: ko.observable("This is an Emergencymessage. Check your Printer"),
                emergencyCount: ko.observable(5),               // Amount of Messages per Block
                emergencyIntervall: ko.observable(1),           // Amount of Messageblocks
                emergencyTime: ko.observable(0),               // Time between blocks

                printerAction: ko.observable("gcode"),          // Gcode
                gCode: ko.observable("None"),                      // Printer/Gcode
                axes: ko.observable("xyz"),                      // Axes to home
                tempTarget: ko.observable("bed"),               // Target of the temp (bed, tool0-tool1)
                temp: ko.observable(0),                          // Temperature to set

                variableName: ko.observable(""),
                variableAction: ko.observable(""),               // Add, Set, Subtract
                variableCount: ko.observable(0)
            }
            self.logicConfigs.push(logic);

        }

        self.removeLogic = function(configuration){
            self.logicConfigs.remove(configuration);
        }

// Tab
        self.onAfterTabChange = function (current, previous){
            if(current == "gpiotelegram_tab"){
                self.updateButtons();
            }
        }

        self.onDataUpdaterPluginMessage = function(plugin, data){
            
            if(plugin != "telegram")
            {
                return;
            }
            
            self.updateButtons();
        }

        self.updateButtons = function(){
            self.buttons(ko.toJS(self.pinConfigs).map(function (item){
                return {
                    name: item.pin + ": " + item.name,
                    state: "",
                    visibleInUI: ko.observable(item.visibleInUI),
                    mode: ko.observable(item.mode)
                }
            }));
            
            self.getButtonStates();
        }


        self.getButtonStates = function(){
            try{
                OctoPrint.simpleApiGet("telegram", {data: {gpio: true}}).then(function (states) {
                    self.buttons().forEach(function (item, index)  {
                        self.buttons.replace(item, {
                            name: item.name,
                            state: states[index],
                            visibleInUI: item.visibleInUI,
                            mode: item.mode
                        });
                    });
                });
            }
            catch{
                self.getButtonStates();
            }
        }

        self.activatePin = function (){
            OctoPrint.simpleApiCommand(
                "telegram",
                "activateGPIO",
                { id: self.buttons.indexOf(this), state: "activate" }
            ).then(function () {
                self.updateButtons();
            });
        }

        self.deactivatePin = function(){
            OctoPrint.simpleApiCommand(
                "telegram",
                "activateGPIO",
                { id: self.buttons.indexOf(this), state: "deactivate" }
            ).then(function () {
                self.updateButtons();
            });
        }

    }
   
    OCTOPRINT_VIEWMODELS.push({
        construct: GpioTelegramViewModel,
        dependencies: ["settingsViewModel"],
        elements: ["#settings_gpio_plugin_telegram", "#tab_plugin_telegram"]
    });
});