-- fetch_sent_chunk.applescript <accountName> <sentMailboxName> <start> <end>
-- 送信済みメールボックスの start〜end 番目 (1が最新) のメタデータを取得する。
-- 受信と違い「相手 = 宛先(最初の受取人)」なので、宛先アドレス/名前を返す。
-- 出力: 1レコード = "␟" 区切り、フィールド = "␞" 区切り
--   id␞ISO日時(送信日時)␞宛先アドレス␞宛先名␞件名
on run argv
	set acctName to item 1 of argv
	set mbName to item 2 of argv
	set startIdx to (item 3 of argv) as integer
	set endIdx to (item 4 of argv) as integer
	set fieldSep to character id 9246 -- ␞
	set recSep to character id 9247 -- ␟
	set out to {}
	with timeout of 570 seconds
		tell application "Mail"
			set acct to account acctName
			-- Gmail の送信済みは [Gmail] 配下でネスト参照(名前直指定)ができないため、
			-- メールボックスオブジェクトを走査して該当名のものを解決する。
			set mb to missing value
			repeat with candMb in (every mailbox of acct)
				try
					if (name of candMb) is mbName then
						set mb to candMb
						exit repeat
					end if
				end try
			end repeat
			if mb is missing value then return ""
			set c to count of messages of mb
			if c is 0 or startIdx > c then return ""
			if endIdx > c then set endIdx to c
			repeat with i from startIdx to endIdx
				try
					set msg to message i of mb
					set rid to id of msg as text
					set ds to my isoDate(date sent of msg)
					set subj to subject of msg
					set toAddr to ""
					set toName to ""
					try
						set recs to to recipients of msg
						if (count of recs) > 0 then
							set r1 to item 1 of recs
							set toAddr to address of r1
							try
								set nm to name of r1
								if nm is not missing value then set toName to nm
							end try
						end if
					end try
					set rec to rid & fieldSep & ds & fieldSep & toAddr & fieldSep & toName & fieldSep & subj
					copy rec to end of out
				end try
			end repeat
		end tell
	end timeout
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
