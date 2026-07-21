-- open_message.applescript <accountName> <mailboxName> <messageId>
-- 指定メールを Mail.app で開く(別ウインドウ表示)。
-- Gmail の [Gmail] 配下メールボックスは名前直指定できない(-1728)ため走査で解決する。
-- 出力: 成功 "1" / 失敗 "0"
on run argv
	set acctName to item 1 of argv
	set mbName to item 2 of argv
	set msgId to (item 3 of argv) as integer
	tell application "Mail"
		set acct to account acctName
		set mb to missing value
		try
			set mb to mailbox mbName of acct
			get name of mb
		on error
			set mb to missing value
		end try
		if mb is missing value then
			repeat with candMb in (every mailbox of acct)
				try
					if (name of candMb) is mbName then
						set mb to candMb
						exit repeat
					end if
				end try
			end repeat
		end if
		if mb is missing value then return "0"
		try
			set found to (messages of mb whose id is msgId)
			if (count of found) is 0 then return "0"
			set theMsg to item 1 of found
			open theMsg
			activate
			return "1"
		on error
			return "0"
		end try
	end tell
end run
