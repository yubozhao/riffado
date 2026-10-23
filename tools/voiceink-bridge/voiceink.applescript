on nodesFor(windowName)
    tell application "System Events" to tell process "VoiceInk"
        return entire contents of window windowName
    end tell
end nodesFor

on itemWithId(windowName, identifier)
    set uiNodes to my nodesFor(windowName)
    tell application "System Events"
        repeat with elem in uiNodes
            try
                if value of attribute "AXIdentifier" of elem is identifier then return contents of elem
            end try
        end repeat
    end tell
    error "Expected VoiceInk control is missing: " & identifier
end itemWithId

on jobGroup(filename)
    tell application "System Events" to tell process "VoiceInk"
        set queueRows to UI elements of scroll area 1 of group 1 of window "VoiceInk"
        repeat with queueRow in queueRows
            if role of queueRow is "AXGroup" then
                set rowNodes to UI elements of queueRow
                repeat with elem in rowNodes
                    if role of elem is "AXStaticText" then
                        if value of elem is filename then return contents of queueRow
                    end if
                end repeat
            end if
        end repeat
    end tell
    return missing value
end jobGroup

on queueState()
    tell application "System Events" to tell process "VoiceInk"
        set uiNodes to UI elements of group 1 of window "VoiceInk"
    end tell
    tell application "System Events"
        repeat with elem in uiNodes
            if role of elem is "AXButton" then
                if help of elem is "Cancel transcription" then return "busy"
                if help of elem is "Start transcription" then return "pending"
                if help of elem is "Select an enabled mode to start" then return "pending"
                if help of elem is "Clear all items" then return "ready"
            end if
        end repeat
    end tell
    return "ready"
end queueState

on pendingCount(filename)
    set rowGroup to my jobGroup(filename)
    set waitingCount to 0
    tell application "System Events"
        set queueParent to value of attribute "AXParent" of rowGroup
        set queueRows to UI elements of queueParent
        repeat with queueRow in queueRows
            if role of queueRow is "AXGroup" then
                set rowNodes to UI elements of queueRow
                repeat with elem in rowNodes
                    if role of elem is "AXStaticText" then
                        if value of elem is "Waiting" then set waitingCount to waitingCount + 1
                    end if
                end repeat
            end if
        end repeat
    end tell
    return waitingCount
end pendingCount

on jobState(filename)
    set rowGroup to my jobGroup(filename)
    if rowGroup is missing value then return "missing"
    tell application "System Events"
        set rowNodes to UI elements of rowGroup
        repeat with elem in rowNodes
            if role of elem is "AXMenuButton" and help of elem is "Save to file" then return "completed"
            if role of elem is "AXStaticText" then
                if value of elem is "Waiting" then return "pending"
            end if
        end repeat
    end tell
    if my queueState() is "busy" then return "processing"
    return "failed"
end jobState

on pressHelp(labelText)
    tell application "System Events" to tell process "VoiceInk"
        set uiNodes to UI elements of group 1 of window "VoiceInk"
    end tell
    tell application "System Events"
        repeat with elem in uiNodes
            if role of elem is "AXButton" and help of elem is labelText then
                if enabled of elem is not true then error "VoiceInk control is disabled: " & labelText
                perform action "AXPress" of elem
                return
            end if
        end repeat
    end tell
    error "VoiceInk control is missing: " & labelText
end pressHelp

on run argv
    with timeout of 20 seconds
        set taskAction to item 1 of argv
        if taskAction is "navigate" then
            my pressHelp("Transcribe")
            return "opened"
        else if taskAction is "preflight" then
            repeat 4 times
                try
                    return my queueState()
                on error errorText number errorNumber
                    if errorNumber is not -1719 then error errorText number errorNumber
                    delay 0.2
                end try
            end repeat
            error "VoiceInk queue is changing; try again after it settles"
        else if taskAction is "status" then
            return my jobState(item 2 of argv)
        else if taskAction is "start" then
            set filename to item 2 of argv
            if my jobState(filename) is not "pending" then error "Expected exactly one pending bridge recording"
            if my queueState() is "busy" then error "VoiceInk is already processing"
            if my pendingCount(filename) is not 1 then error "Other recordings are waiting in VoiceInk"
            my pressHelp("Start transcription")
            return "started"
        else if taskAction is "export" then
            set filename to item 2 of argv
            set outputDirectory to item 3 of argv
            set outputName to item 4 of argv
            if my jobState(filename) is not "completed" then error "Recording is not completed"
            set rowGroup to my jobGroup(filename)
            tell application "System Events"
                set rowNodes to UI elements of rowGroup
                set saveControl to missing value
                repeat with elem in rowNodes
                    if role of elem is "AXMenuButton" and help of elem is "Save to file" then
                        set saveControl to contents of elem
                        exit repeat
                    end if
                end repeat
                if saveControl is missing value then error "Transcript export control is missing"
                perform action "AXPress" of saveControl
                tell process "VoiceInk"
                    click menu item "Save as TXT" of menu 1 of saveControl
                    repeat 50 times
                        if exists window "Save Transcription" then exit repeat
                        delay 0.1
                    end repeat
                    if not (exists window "Save Transcription") then error "VoiceInk did not open its save dialog"
                    set frontmost to true
                    keystroke "g" using {command down, shift down}
                    repeat 50 times
                        if exists sheet 1 of window "Save Transcription" then exit repeat
                        delay 0.1
                    end repeat
                    set value of text field 1 of sheet 1 of window "Save Transcription" to outputDirectory
                    key code 36
                    repeat 50 times
                        if not (exists sheet 1 of window "Save Transcription") then exit repeat
                        delay 0.1
                    end repeat
                end tell
                set nameControl to my itemWithId("Save Transcription", "saveAsNameTextField")
                set value of nameControl to outputName
                set saveButton to my itemWithId("Save Transcription", "OKButton")
                perform action "AXPress" of saveButton
            end tell
            return "exported"
        end if
        error "Unknown bridge action"
    end timeout
end run
