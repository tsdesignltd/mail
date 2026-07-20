-- get_content.applescript <accountName> <mailboxName> <messageId>
-- 1通の本文テキストを取得する(numeric id 指定なので whose 検索より速い)
on run argv
	set acctName to item 1 of argv
	set mbName to item 2 of argv
	set msgId to (item 3 of argv) as integer
	tell application "Mail"
		set mb to mailbox mbName of account acctName
		set found to (messages of mb whose id is msgId)
		if (count of found) is 0 then error "message not found"
		return content of (item 1 of found)
	end tell
end run
