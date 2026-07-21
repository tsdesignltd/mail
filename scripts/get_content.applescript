-- get_content.applescript <accountName> <mailboxName> <messageId> [rfcMessageId]
-- 1通の本文テキストを取得する。
-- 照合は RFC Message-ID(安定・一意)を優先し、無ければ番号IDにフォールバックする。
-- 番号IDは Mail の再インデックスで別メールに振り替わることがあり、取り違えの原因になるため。
-- 注: Gmail の送信済み等 [Gmail] 配下は名前直指定できない(-1728)ためオブジェクト走査で解決。
on run argv
	set acctName to item 1 of argv
	set mbName to item 2 of argv
	set msgId to (item 3 of argv) as integer
	set rfcId to ""
	if (count of argv) ≥ 4 then set rfcId to item 4 of argv
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
		if mb is missing value then error "mailbox not found"
		set theMsg to missing value
		-- RFC Message-ID 優先
		if rfcId is not "" then
			try
				set f to (messages of mb whose message id is rfcId)
				if (count of f) > 0 then set theMsg to item 1 of f
			end try
		end if
		-- フォールバック: 番号ID
		if theMsg is missing value then
			set f2 to (messages of mb whose id is msgId)
			if (count of f2) is 0 then error "message not found"
			set theMsg to item 1 of f2
		end if
		return content of theMsg
	end tell
end run
