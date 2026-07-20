-- list_accounts.applescript
-- 有効なアカウントと、その受信トレイ相当メールボックス名・件数を返す
-- 出力: アカウント名␞メールボックス名␞件数 を ␟ で連結
on run argv
	set fieldSep to character id 9246 -- ␞
	set recSep to character id 9247 -- ␟
	set out to {}
	tell application "Mail"
		repeat with acct in accounts
			try
				if enabled of acct then
					set acctName to name of acct
					set mbNames to name of mailboxes of acct
					if mbNames contains "INBOX" then
						set mbName to "INBOX"
					else if mbNames contains "受信" then
						set mbName to "受信"
					else
						set mbName to ""
					end if
					if mbName is not "" then
						set c to count of messages of mailbox mbName of acct
						copy (acctName & fieldSep & mbName & fieldSep & (c as text)) to end of out
					end if
				end if
			end try
		end repeat
	end tell
	set AppleScript's text item delimiters to recSep
	set txt to out as text
	set AppleScript's text item delimiters to ""
	return txt
end run
