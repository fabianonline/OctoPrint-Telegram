from __future__ import absolute_import, unicode_literals
from cmath import log, pi
from email import message
from inspect import classify_class_attrs
from socketserver import ThreadingMixIn

import time, threading
from traceback import format_exc
from octoprint.events import Events

import flask
import octoprint.plugin
import RPi.GPIO as GPIO


class GPIO_Variable():
    def __init__(self, _name, _default):
        self.variableName = _name
        self.value = _default
    def __str__(self):
        return "Name: {}; Value: {}".format(self.variableName,self.value)

class GPIO_Control():
    def __init__(self, main):
        self.main = main
        self._logger = main._logger.getChild("gpiocontrol")
        self._logger.info ("Initialized GPIO-Control")
        self.pinMode = GPIO.BCM
        self.pinsConfigured = False
        self.channelsUsed = []
        self.variables = []


## Start/Stop
    def gpio_startup(self):
        """Loading and setting up safed Pins"""
        self._logger.info("Startup GPIO")
        GPIO.setmode(self.pinMode)
        self._logger.info("Set GPIOMode to: {}".format(GPIO.getmode()))
        self.configurePins()
        
    def gpio_afterStartup(self):
        """Print Message"""
        self._logger.info("Started up GPIO-Control")    

    def gpio_shutdown(self):
        """Cleaning up all Pins"""
        GPIO.cleanup()
        self._logger.info("Cleaned up GPIO-Pins because Plugin is shutting down.")

# Settings
    def handleSettingsBeforeSave(self, data):
        self._logger.debug("Handling GPIO-Settings")

        # Collect all Pins to cleanup => not all in Settings since some can be double and so not configured
        _toClean = []
        for pin in self.channelsUsed:
            if pin>0:
                GPIO.cleanup(pin)

                self._logger.info(
                    "Cleaned up Pin "+ str(pin)
                )
                _toClean.append(pin)

        for pin in _toClean:
            self.channelsUsed.remove(pin)

        return data

    def onSettingsSave(self, data):
        self._logger.info("Saving Settings...")

        info = ""
        for pin in self.channelsUsed:
            info = "{}\n{}".format(info, pin)
        
        self.pinsConfigured = False

        listToClean = []
        # Cleanup all Pins 
        for pin in self.channelsUsed:
            

            if pin > 0:
                GPIO.cleanup(pin)

                self._logger.info(
                    "Cleaned up Pin "+ str(pin)
                )
                listToClean.append(pin)
        
        for pin in listToClean:
            self.channelsUsed.remove(pin)

        # Saving
        octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
        self._logger.info("Saved Settings!")

        # Reconfigure Pins
        self.configurePins(self)


# CommandAPI
    def onCommand(self, command, data):
        """React to an Command run by Frontend to toggle the Outputs"""
        # Get the Pin via the Index of the config
        pinData = self.main._settings.get(["gpio_PinConfigs"])[int(data["id"])]
        pin = pinData["pin"]

        if self.pinsConfigured == True:
            if data["state"] == "activate":
                if pin > 0:
                    self._logger.info("Activated Pin {}".format(pin))
                    if pinData["activeState"] == "high":
                        GPIO.output(pin, GPIO.HIGH)
                    else:
                        GPIO.output(pin, GPIO.LOW)
            elif data["state"] == "deactivate":
                if pin >0:
                    self._logger.info("Deactivated Pin {}".format(pin))
                    if pinData["activeState"] == "high":
                        GPIO.output(pin, GPIO.LOW)
                    else:
                        GPIO.output(pin, GPIO.HIGH)
                    
        # return empty
        return flask.jsonify("")

    def onRequest(self, request):
        """React to Request from Frontend and collect the current State of the Pins"""
        states =[]

        if self.pinsConfigured == False:
            # Not done with Configuration
            for pinData in self.main._settings.get(["gpio_PinConfigs"]):
                states.append("")
            
        else:
            # Pins configured
            for pinData in self.main._settings.get(["gpio_PinConfigs"]):
                pin = int(pinData["pin"])

                if pin not in self.channelsUsed:
                    states.append("")
                    continue

                if pin > 0:
                    if pinData["mode"] == "output":
                        if pinData["activeState"] == "high":
                            if GPIO.input(pin) == 1:
                                states.append("on")
                            else:
                                states.append("off")
                        else:
                            if GPIO.input(pin) == 1:
                                states.append("off")
                            else:
                                states.append("on")
                    else:
                        # Input
                        if pinData["pullUpDown"] == "up":
                            if GPIO.input(pin) == 1:
                                states.append("off")
                            else:
                                states.append("on")
                        else:
                            if GPIO.input(pin) == 1:
                                states.append("on")
                            else:
                                states.append("off")
                else:   
                    states.append("")


        return flask.jsonify(states)

# GPIO Control
    def configurePins(self):
        """Configure Pins with the current Settingsdata"""
        configuredPins = [] # Keeps track which one is already configured
        self.pinsConfigured = False

        for pinData in self.main._settings.get(["gpio_PinConfigs"]):
            pin = int(pinData["pin"])

            if pin > 0:
                if configuredPins.__contains__(pin) or self.channelsUsed.__contains__(pin):
                    # This Pin is already configured => Disabling this Pin to safe Electronics
                    self._logger.warning("Didn't configure pin {} cause it is already defined at least twice. Clearing all other ocations of this Pin.".format(pin))
                    GPIO.cleanup(pin)
                    self.channelsUsed.remove(pin)
                    continue

                if pinData["mode"] == "input":
                    # This Pin should be an Input => Setup and hook the Interruptfunction
                    self.addInputEvent(pin, pinData["pullUpDown"], int(pinData["bounceTime"]))
                else: 
                    # This Pin should be an Output => Setup
                    self.addOutput(pin, pinData["activeState"], pinData["defaultState"])

                # Add Pin to usedPins
                configuredPins.append(pin)
                self.channelsUsed.append(pin)
        self.configureVariables()
        
        self.pinsConfigured = True
        self.sendUIMessage()
        

    def configureVariables(self):
        self.variables = []

        for _variable in self.main._settings.get(["gpio_Variables"]):
            self.variables.append(GPIO_Variable(_variable["name"], int(_variable["value"])))

        self._logger.info("Variables: {}".format(self.variables))

    def addOutput(self, _pin = 0, _active = "low", _default = "off"):
        #Setup Pin
        GPIO.setup(_pin, GPIO.OUT)

        #Activate Pin to correct state
        if _active == "low":
            if _default == "on":
                GPIO.output(_pin, GPIO.LOW)
            elif _default == "off":
                GPIO.output(_pin, GPIO.HIGH)
        elif _active == "high":
            if _default == "on":
                GPIO.output(_pin, GPIO.HIGH)
            elif _default == "off":
                GPIO.output(_pin, GPIO.LOW)

        self._logger.info("Configured Pin {} as Output with Activestate {} and Defaultstate {}.".format(_pin, _active, _default))

    def addInputEvent(self, _pin = 0, _usePullup = "none", _bouncetime = 50):
        """Declaring an Pin as an Input and adding its react Function.            """
        _pull_up_down = GPIO.PUD_OFF
        _PUD = "Floating"


        # Check if Pullup or Pulldown
        if _usePullup == "down":
            _pull_up_down = GPIO.PUD_DOWN
            _PUD = "Pulldown"
        elif _usePullup == "up":
            _pull_up_down = GPIO.PUD_UP
            _PUD = "Pullup"

        # Setup Pin
        GPIO.setup(_pin, GPIO.IN, pull_up_down = _pull_up_down)    

        # Check if Bouncetime is smaller than 1 => Problems with Bouncetime 0
        if _bouncetime < 1:
            _bouncetime = 1

        # Attach interruptfunction
        GPIO.add_event_detect(_pin, GPIO.BOTH, callback = lambda *a: self.reactToInterrupt(_pin), bouncetime = _bouncetime)

        self._logger.info("Configured Pin {} as Input with an Pullup/Pulldown as {} and an Bouncetime of {}ms.".format(_pin, _PUD, _bouncetime))

    def reactToInterrupt(self, _pin):
        """Update the UI and check if it needs to run Logic"""
        # Since the UI needs to update every Time the Pin is triggered this needs to run every Time. 
        # The Logic only needs to run if the Current Pinstate is the same as the needed LogicState.

        _currentstate = GPIO.input(_pin)


        # Send Update to UI
        self.sendUIMessage()

        # Check if it needs to perform logic
        for pinData in self.main._settings.get(["gpio_PinConfigs"]):
            _pinToCheck = int(pinData["pin"])

            if _pinToCheck == _pin:
                #This Pin triggered the function
                if pinData["edgeDetection"] == "rising":
                    if _currentstate == 1:
                        # Needed Rising Edge detected
                        self.triggerAction(_pin)

                elif pinData["edgeDetection"] == "falling":
                    if _currentstate == 0:
                        # Needed Falling Edge detected
                        self.triggerAction(_pin)
                else:
                    # Detect Both Edges
                        self.triggerAction(_pin)
            
                break # Found Pin => Stop searching

    def triggerAction(self, _pin):
        """Checks and triggers Logic with the pin as Trigger"""

        for logicData in self.main._settings.get(["gpio_LogicConfigs"]):
            if logicData["trigger"] == "pin":
                
                trigger = int(logicData["triggerPin"])

                if trigger > 0 and trigger == _pin :
                    # This Logicdata gets triggered by the pin

                    _delay = int(logicData["triggerDelay"])

                    (threading.Thread(target=self.threadedTriggerLogic,args= (logicData,_delay), daemon=True)).start()

    def threadedTriggerLogic(self, logicData, delay, currentVariableValue = ""):
        if delay > 0:
            time.sleep(delay)
        self.triggerLogic(logicData, currentVariableValue)

    def triggerLogic(self, logicData, currentVariableValue = ""):
        """Checks what logic should trigger and triggeres it"""

        if logicData["type"] == "output":
            #Trigger Outputpin
            targetPin = int(logicData["pin"])
            triggerMode = logicData["pinMode"]

            for pinData in self.main._settings.get(["gpio_PinConfigs"]):
                # Search every PinData for this Pin
                if pinData["mode"] == "output" and targetPin in self.channelsUsed:
                    _pin = int(pinData["pin"])
                    _newState = ""

                    if targetPin == _pin:
                        # This Pin should be triggered  => Check how
                        if pinData["activeState"] == "high":
                            # Pin is active when high
                            if triggerMode == "toggle":
                                # Get Current State and toggle
                                if GPIO.input(_pin) == 0:
                                    # Pin is currently low => Set high
                                    GPIO.output(_pin, GPIO.HIGH)     
                                    _newState = "High"                                   
                                else:
                                    # Pin is currently high => set low
                                    GPIO.output(_pin, GPIO.LOW)
                                    _newState = "Low"            
                            elif triggerMode == "enable":
                                # Enable Pin
                                GPIO.output(_pin, GPIO.HIGH)  
                                _newState = "High"            
                            else:   
                                # Disable Pin
                                GPIO.output(_pin, GPIO.LOW)
                                _newState = "Low"            
                        else:
                            # Pin is active when low
                            if triggerMode == "toggle":
                                # Get Current State and toggle
                                if GPIO.input(_pin) == 0:
                                    # Pin is currently low => Set high
                                    GPIO.output(_pin, GPIO.HIGH)    
                                    _newState = "High"                                                  
                                else:
                                    # Pin is currently high => set low
                                    GPIO.output(_pin, GPIO.LOW)  
                                    _newState = "Low"            
                            elif triggerMode == "enable":
                                # Enable Pin
                                GPIO.output(_pin, GPIO.LOW)
                                _newState = "Low"            
                            else:   
                                # Disable Pin
                                GPIO.output(_pin, GPIO.HIGH)  
                                _newState = "High"            

                        self._logger.info("Triggered Output {} via {}. NewState is {}".format(_pin, logicData["pinMode"], _newState))
                        # Stop cycling trough the loop couse we found the Pin and triggered the Action                
                        break
                    
        elif logicData["type"] == "message":
            _message = logicData["message"]

            if logicData["trigger"] == "variable" and logicData["sendVariable"] == "true":
                _message = _message.replace("XGPIOX", currentVariableValue)

            self._logger.info("Send message: {}".format(_message))
            self.main.send_msg(_message)

        elif logicData["type"] == "emergency":
            _count = 1
            _intervall = 1
            _time = 1

            if "emergencyCount" in logicData:
                _count = int(logicData["emergencyCount"])
                
            if "emergencyIntervall" in logicData:
                _intervall = int(logicData["emergencyIntervall"])

            if "emergencyTime" in logicData:
                _time = int(logicData["emergencyTime"])

            (threading.Thread(target=self.sendEmergencyMessage, args = (logicData["emergency"], _count, _intervall, _time), daemon=True)).start()
               
        elif logicData["type"] == "printer":
            if logicData["printerAction"] == "gcode":
                commands = logicData["gCode"]
                self._logger.info("Triggered G-Code Command {}".format(commands))
                self.main._printer.commands(commands)
            elif logicData["printerAction"] == "pausePrint":
                self._logger.info("Pausing Print")
                self.main._printer.pause_print()
                self._logger.info("Pausing Print")
            elif logicData["printerAction"] == "resumePrint":
                self._logger.info("Resuming Print")
                self.main._printer.resume_print()
            elif logicData["printerAction"] == "togglePrint":
                if self.main._printer.is_paused():
                    self._logger.info("Resuming Print")
                    self.main._printer.resume_print()
                else:
                    self._logger.info("Pausing Print")
                    self.main._printer.pause_print()
            elif logicData["printerAction"] == "home":
                _axes = []

                if "x" in logicData["axes"].lower():
                    _axes.append("x")
                
                if "y" in logicData["axes"].lower():
                    _axes.append("y")

                if "z" in logicData["axes"].lower():
                    _axes.append("z")
                
                if len(_axes) > 0:
                    self.main._printer.home(_axes)
                    self._logger.info("Homing Printer on Axis {}".format(_axes))
                else:
                    self._logger.info("Not homing printer since no Axis defined")
            
            elif logicData["printerAction"] == "cancel": 
                self._logger.info("Cancelling Print")
                self.main._printer.cancel_print()
            elif logicData["printerAction"] == "setTemperature":
                target = logicData["tempTarget"]
                temp = int(logicData["temp"])

                if temp < 0:
                    temp = 0

                self.main._printer.set_temperature(target, temp)
                self._logger.info("Set Targettemperature of {} to {}°C.".format(target, temp))
                
            else:
                self._logger.info("Unknown Printeraction triggered")
        
        elif logicData["type"] == "variable":
            # First check if Variable Name exists

            for _variable in self.variables:
                if _variable.variableName == logicData["variableName"]:
                    # Now check what action to perform
                    _number = int(logicData["variableCount"])
                    _current = _variable.value

                   # try:
                    if logicData["variableAction"] == "set":
                        _variable.value = _number
                        self._logger.info("Set Variable {} to {}".format(logicData["variableName"], _variable.value))
                        self.handleVariableChange(logicData["variableName"], _variable.value)
                    elif logicData["variableAction"] == "add":
                        _variable.value = _current + _number
                        self._logger.info("Added {} to Variable {}. New Value: {}".format(_number, logicData["variableName"], _variable.value))
                        self.handleVariableChange(logicData["variableName"], _variable.value)
                    elif logicData["variableAction"] == "subtract":
                        _variable.value = _current - _number
                        self._logger.info("Subtracted {} from Variable {}. New Value: {}".format(_number, logicData["variableName"], _variable.value))
                        self.handleVariableChange(logicData["variableName"], _variable.value)
                 #   except Exception as e:
                  #      self._logger.info("Error while doing variable Action on {}. Error: {}".format(logicData["variableName"],e.__class__))
                  #  break
            else:
                self._logger.info("Can't find Variable {}. Maybe it is not registered".format(logicData["variableName"]))
        else:
            self._logger.info("Unknown Action triggered")

    def handleVariableChange(self, _name, _value):
        """Called when a variable changed"""
        self._logger.info("Variable {} changed. Check what to do".format(_name))


        for logicData in self.main._settings.get(["gpio_LogicConfigs"]):
            if logicData["trigger"] == "variable":
                if logicData["triggerVariable"] == _name:
                    # This Variable changed

                    _condition = logicData["triggerVariableCondition"]
                    _target = int(logicData["triggerVariableValue"])
                    _delay = int(logicData["triggerDelay"])

                    
                    if _condition == "<":
                        if _value < _target:
                            self._logger.info("Variablehandling: {} is {} than {}. Triggering Logic.".format(_value, _condition, _target))
                            self.threadedTriggerLogic(logicData,_delay, str(_value))

                    elif _condition == "<=":
                        if _value <= _target:
                            self._logger.info("Variablehandling: {} is {} than {}. Triggering Logic.".format(_value, _condition, _target))
                            self.threadedTriggerLogic(logicData,_delay, str(_value))

                    elif _condition == "=":
                        if _value == _target:
                            self._logger.info("Variablehandling: {} is {} than {}. Triggering Logic.".format(_value, _condition, _target))
                            self.threadedTriggerLogic(logicData,_delay, str(_value))

                    elif _condition == ">=":
                        if _value >= _target:
                            self._logger.info("Variablehandling: {} is {} than {}. Triggering Logic.".format(_value, _condition, _target))
                            self.threadedTriggerLogic(logicData,_delay, str(_value))

                    elif _condition == ">":                        
                        if _value > _target:
                            self._logger.info("Variablehandling: {} is {} than {}. Triggering Logic.".format(_value, _condition, _target))
                            self.threadedTriggerLogic(logicData,_delay, str(_value))
                            self._logger.info()
                        
                    elif _condition == "!=":
                        if _value != _target:
                            self._logger.info("Variablehandling: {} is {} than {}. Triggering Logic.".format(_value, _condition, _target))
                            self.threadedTriggerLogic(logicData,_delay, str(_value))

    def handleGPIOCommand(self, _pin, _mode):
        """This Function handles the Activation/Deactivation of an Pin"""
        self._logger.info("Pin: {}, Mode: {}".format(_pin, _mode))
        _message = "This pin was not found"
        
        if _pin in self.channelsUsed: # Check if Pin is activated (not doubled or so)
            for pinData in self.main._settings.get(["gpio_PinConfigs"]):    # Search for the mode of the Pin
                if int(pinData["pin"]) == _pin:
                    if pinData["mode"] == "output" and pinData["visibleInTelegram"] == "true":     # Pin is Output
                        # This is the Pin to activate
                        _activation = _mode.lower()

                        if pinData["activeState"] == "high":
                            if _activation == "on":
                                GPIO.output(_pin, GPIO.HIGH)
                                _message = "Activated Pin {}: {}".format(_pin, pinData["name"])
                            elif _activation == "off":
                                GPIO.output(_pin, GPIO.LOW)
                                _message = "Deactivated Pin {}: {}".format(_pin, pinData["name"])
                            elif _activation == "toggle":
                                if GPIO.input(_pin) == 0:
                                    GPIO.output(_pin, GPIO.HIGH)
                                    _message = "Activated Pin {}: {}".format(_pin, pinData["name"])
                                else:
                                    GPIO.output(_pin, GPIO.LOW)
                                    _message = "Deactivated Pin {}: {}".format(_pin, pinData["name"])
                            else:
                                _message = "I dont know what you want me to do with this Pin. Use toggle, off or on!!"
                        else:                            
                            if _activation == "on":
                                GPIO.output(_pin, GPIO.LOW)
                                _message = "Activated Pin {}: {}".format(_pin, pinData["name"])
                            elif _activation == "off":
                                GPIO.output(_pin, GPIO.HIGH)
                                _message = "Deactivated Pin {}: {}".format(_pin, pinData["name"])
                            elif _activation == "toggle":
                                if GPIO.input(_pin) == 0:
                                    GPIO.output(_pin, GPIO.HIGH)
                                    _message = "Deactivated Pin {}: {}".format(_pin, pinData["name"])
                                else:
                                    GPIO.output(_pin, GPIO.LOW)
                                    _message = "Activated Pin {}: {}".format(_pin, pinData["name"])
                            else:
                                _message = "I dont know what you want me to do with this Pin. Use toggle, off or on!!"
                    
                    else:
                        _message = "This Pin is not registered as an Output or not allowed to be changed by Telegram."
                    break
        return _message

    def getCurrentOutputs(self):
        s = "You have currently theese Pins configured as an Output:"
        count = 0
        for pinData in self.main._settings.get(["gpio_PinConfigs"]):
            if pinData["mode"] == "output" and int(pinData["pin"]) in self.channelsUsed:
                _pin = int(pinData["pin"])
                state = GPIO.input(_pin)
                count = count +1

                if pinData["visibleInTelegram"] == "true":
                    s = "{}\n{}: {} which is currently {}".format(s, _pin, pinData["name"], "On" if state==1 else "Off")
        
        if count == 0:
            s = "You have currently no Pins configured as an Output."
        return s

    

# Eventhandling
    def handleEventTriggers(self, event, payload, **kwargs):
        """Checking if an Event is an trigger and trigger the logic if so"""
        self._logger.info("Handling event: {}".format(event))

        for logicData in self.main._settings.get(["gpio_LogicConfigs"]):
            if logicData["trigger"] == "event":
                # The Logictrigger is an Event

                if logicData["triggerEvent"] == event:
                    _delay = int(logicData["triggerDelay"])

                    (threading.Thread(target=self.threadedTriggerLogic,args= (logicData,_delay), daemon=True)).start()


# Emergency
    def sendEmergencyMessage(self, _message, count = 1, interval=1, pause=0):
        self._logger.info("Running Emergencymessagethread, Count {}; Intervall {}, Pause {}".format(count, interval, pause))

        if interval < 1:
            interval = 1

        if count < 1:
            count = 1

        for x in range(interval):
            for y in range(count):
                self.main.send_msg(_message, silent = False) 
            time.sleep(pause)


# UI Handling
    def sendUIMessage(self):
        """Sending an Message to the UI, so the UI requests the changes and updates"""
        self.main._plugin_manager.send_plugin_message("telegram", dict())
