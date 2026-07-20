-- move_by_msgid.applescript <targetMailbox> <acct1> <rfcId1> [<acct2> <rfcId2> ...]
-- RFC Message-ID でメッセージを特定してローカルメールボックスへ移動する。
-- (Envelope Index 直読みモード用。whose 検索なのでやや遅い)
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
			set rfcId to item (i + 1) of argv
			try
				set mb to mailbox "INBOX" of account acctName
				set found to (messages of mb whose message id is rfcId)
				if (count of found) > 0 then
					move (item 1 of found) to target
					set moved to moved + 1
				else
					set failed to failed + 1
				end if
			on error
				set failed to failed + 1
			end try
			set i to i + 2
		end repeat
	end tell
	return (moved as text) & "," & (failed as text)
end run
