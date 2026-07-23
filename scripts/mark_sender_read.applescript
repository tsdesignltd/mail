-- mark_sender_read.applescript <accountName> <inboxName> <address>
-- 指定アドレスからの受信メールを Mail.app 側で既読にする。
-- Gmail は whose 結果が [Gmail]/All Mail 参照になり一括 set が失敗するため1通ずつ設定する。
-- 出力: 既読にした件数
on run argv
	set acctName to item 1 of argv
	set inName to item 2 of argv
	set addr to item 3 of argv
	set n to 0
	with timeout of 570 seconds
		tell application "Mail"
			set acct to account acctName
			-- 受信MBを解決(INBOX等は直接、ダメなら走査)
			set inMb to missing value
			try
				set inMb to mailbox inName of acct
				get name of inMb
			on error
				set inMb to missing value
			end try
			if inMb is missing value then
				repeat with candMb in (every mailbox of acct)
					try
						if (name of candMb) is inName then
							set inMb to candMb
							exit repeat
						end if
					end try
				end repeat
			end if
			if inMb is missing value then return "0"
			try
				set found to (messages of inMb whose sender contains addr)
				repeat with m in found
					try
						if (read status of m) is false then
							set read status of m to true
							set n to n + 1
						end if
					end try
				end repeat
			end try
		end tell
	end timeout
	return (n as text)
end run
