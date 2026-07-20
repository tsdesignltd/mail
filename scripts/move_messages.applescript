-- move_messages.applescript <targetMailbox> <acct1> <mb1> <id1> [<acct2> <mb2> <id2> ...]
-- 指定メッセージ群を「このMac内」のローカルメールボックスへ移動する。
-- ローカルメールボックスが無ければ作成する。
on run argv
	set targetName to item 1 of argv
	set moved to 0
	set failed to 0
	tell application "Mail"
		if not (exists mailbox targetName) then
			make new mailbox with properties {name:targetName}
		end if
		set target to mailbox targetName
		set i to 2
		repeat while i ≤ (count of argv)
			set acctName to item i of argv
			set mbName to item (i + 1) of argv
			set msgId to (item (i + 2) of argv) as integer
			try
				set mb to mailbox mbName of account acctName
				set found to (messages of mb whose id is msgId)
				if (count of found) > 0 then
					move (item 1 of found) to target
					set moved to moved + 1
				else
					set failed to failed + 1
				end if
			on error
				set failed to failed + 1
			end try
			set i to i + 3
		end repeat
	end tell
	return (moved as text) & "," & (failed as text)
end run
