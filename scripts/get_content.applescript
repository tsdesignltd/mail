-- get_content.applescript <accountName> <mailboxName> <messageId>
-- 1通の本文テキストを取得する(numeric id 指定なので whose 検索より速い)
-- 注: Gmail の送信済み等 [Gmail] 配下のメールボックスは名前直指定(-1728)できないため、
--     直接参照に失敗したらメールボックスオブジェクトを走査して解決する。
on run argv
	set acctName to item 1 of argv
	set mbName to item 2 of argv
	set msgId to (item 3 of argv) as integer
	tell application "Mail"
		set acct to account acctName
		set mb to missing value
		try
			set mb to mailbox mbName of acct
			-- 参照が有効か軽く確認 (無効なら例外を投げてフォールバックへ)
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
		set found to (messages of mb whose id is msgId)
		if (count of found) is 0 then error "message not found"
		return content of (item 1 of found)
	end tell
end run
