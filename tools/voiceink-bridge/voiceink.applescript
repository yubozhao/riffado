on jobGroup(filename)
    tell application "System Events" to tell process "VoiceInk"
        set queueRows to UI elements of scroll area 1 of group 1 of window "VoiceInk"
        repeat with queueRow in queueRows
            if role of queueRow is "AXGroup" then
                set rowTexts to value of static texts of queueRow
                if filename is in rowTexts then return contents of queueRow
            end if
        end repeat
    end tell
    return missing value
end jobGroup

on queueState()
    tell application "System Events" to tell process "VoiceInk"
        set labels to help of buttons of group 1 of window "VoiceInk"
        if "Cancel transcription" is in labels then return "busy"
        if "Start transcription" is in labels then return "pending"
        if "Select an enabled mode to start" is in labels then return "pending"
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
                if "Waiting" is in (value of static texts of queueRow) then set waitingCount to waitingCount + 1
            end if
        end repeat
    end tell
    return waitingCount
end pendingCount

on jobState(filename)
    set rowGroup to my jobGroup(filename)
    if rowGroup is missing value then return "missing"
    tell application "System Events"
        if "Save to file" is in (help of menu buttons of rowGroup) then return "completed"
        if "Waiting" is in (value of static texts of rowGroup) then return "pending"
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
        if taskAction is "running" then
            tell application "System Events"
                if exists process "VoiceInk" then return "ready"
            end tell
            return "closed"
        else if taskAction is "available" then
            tell application "System Events"
                if not (exists process "VoiceInk") then return "closed"
                tell process "VoiceInk"
                    if not (exists window "VoiceInk") then return "closed"
                end tell
            end tell
            return "ready"
        else if taskAction is "navigate" then
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

        end if
        error "Unknown bridge action"
    end timeout
end run
