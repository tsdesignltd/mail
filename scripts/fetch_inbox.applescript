-- fetch_inbox.applescript <accountName> <mailboxName> <limit>
-- 指定アカウントのメールボックスから直近 limit 件のメタデータを一括取得する。
-- 出力: 1レコード = "␟" 区切り、フィールド = "␞" 区切り
--   id␞ISO日時␞既読(true/false)␞差出人␞件名
on run argv
	set acctName to item 1 of argv
	set mbName to item 2 of argv
	set lim to (item 3 of argv) as integer
	set fieldSep to character id 9246 -- ␞
	set recSep to character id 9247 -- ␟
	tell application "Mail"
		set acct to account acctName
		set mb to mailbox mbName of acct
		set c to count of messages of mb
		if c is 0 then return ""
		if lim > c then set lim to c
		set idList to id of messages 1 thru lim of mb
		set dateList to date received of messages 1 thru lim of mb
		set readList to read status of messages 1 thru lim of mb
		set senderList to sender of messages 1 thru lim of mb
		set subjList to subject of messages 1 thru lim of mb
	end tell
	set out to {}
	repeat with i from 1 to lim
		set d to item i of dateList
		set ds to my isoDate(d)
		set rec to (item i of idList as text) & fieldSep & ds & fieldSep & (item i of readList as text) & fieldSep & (item i of senderList) & fieldSep & (item i of subjList)
		copy rec to end of out
	end repeat
	set AppleScript's text item delimiters to recSep
	set txt to out as text
	set AppleScript's text item delimiters to ""
	return txt
end run

on isoDate(d)
	set y to year of d as integer
	set m to month of d as integer
	set dd to day of d as integer
	set t to time of d -- 0時からの秒数
	set hh to t div 3600
	set mi to (t mod 3600) div 60
	set ss to t mod 60
	return (y as text) & "-" & my pad(m) & "-" & my pad(dd) & "T" & my pad(hh) & ":" & my pad(mi) & ":" & my pad(ss)
end isoDate

on pad(n)
	set t to n as text
	if length of t < 2 then set t to "0" & t
	return t
end pad
