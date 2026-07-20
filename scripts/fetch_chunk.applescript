-- fetch_chunk.applescript <accountName> <mailboxName> <start> <end>
-- メールボックスの start〜end 番目 (1が最新) のメタデータを取得する。
-- 巨大メールボックスでも接続が切れないよう、呼び出し側が小さい範囲で繰り返し呼ぶ。
-- 出力: 1レコード = "␟" 区切り、フィールド = "␞" 区切り
--   id␞ISO日時␞既読(true/false)␞差出人␞件名
on run argv
	set acctName to item 1 of argv
	set mbName to item 2 of argv
	set startIdx to (item 3 of argv) as integer
	set endIdx to (item 4 of argv) as integer
	set fieldSep to character id 9246 -- ␞
	set recSep to character id 9247 -- ␟
	-- 巨大メールボックスでは1イベントが2分(既定)を超えることがあるため延長する
	with timeout of 570 seconds
		tell application "Mail"
			set mb to mailbox mbName of account acctName
			set c to count of messages of mb
			if c is 0 or startIdx > c then return ""
			if endIdx > c then set endIdx to c
			set n to endIdx - startIdx + 1
			set idList to id of messages startIdx thru endIdx of mb
			set dateList to date received of messages startIdx thru endIdx of mb
			set readList to read status of messages startIdx thru endIdx of mb
			set senderList to sender of messages startIdx thru endIdx of mb
			set subjList to subject of messages startIdx thru endIdx of mb
		end tell
	end timeout
	set out to {}
	repeat with i from 1 to n
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
	set t to time of d
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
