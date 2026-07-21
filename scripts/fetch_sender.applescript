-- fetch_sender.applescript <accountName> <inboxName> <sentName> <address>
-- 指定アドレスとの「受信+送信」の全履歴を1アカウント分まとめて取得する。
-- 受信: 差出人にアドレスを含むもの / 送信: 宛先(受取人)にアドレスを含むもの
-- 出力: 1レコード = "␟" 区切り、フィールド = "␞" 区切り、先頭フィールドが種別 R/S
--   受信: R␞id␞rfcId␞ISO日時␞既読(true/false)␞差出人␞件名
--   送信: S␞id␞rfcId␞ISO日時(送信日時)␞宛先アドレス␞宛先名␞件名
-- rfcId は RFC Message-ID(安定・一意)。本文取得/メール表示の照合に使う。
on run argv
	set acctName to item 1 of argv
	set inName to item 2 of argv
	set sentName to item 3 of argv
	set addr to item 4 of argv
	set fieldSep to character id 9246 -- ␞
	set recSep to character id 9247 -- ␟
	set out to {}
	with timeout of 570 seconds
		tell application "Mail"
			set acct to account acctName
			-- 受信トレイ (INBOX は直接参照できる)
			if inName is not "" then
				try
					set inMb to mailbox inName of acct
					-- Gmail は whose 結果が [Gmail]/All Mail 参照になり一括プロパティ取得(id of ...)が
					-- -1728 で失敗するため、1通ずつ取得する(該当会話のみなので件数は少ない)。
					set rcv to (messages of inMb whose sender contains addr)
					repeat with m in rcv
						try
							set rid to id of m as text
							set rfc to ""
							try
								set rfc to message id of m
							end try
							set ds to my isoDate(date received of m)
							set rds to (read status of m) as text
							set snd to sender of m
							set subj to subject of m
							set rec to "R" & fieldSep & rid & fieldSep & rfc & fieldSep & ds & fieldSep & rds & fieldSep & snd & fieldSep & subj
							copy rec to end of out
						end try
					end repeat
				end try
			end if
			-- 送信済み (Gmail 等ネスト対応で走査解決)
			if sentName is not "" then
				set sentMb to missing value
				repeat with candMb in (every mailbox of acct)
					try
						if (name of candMb) is sentName then
							set sentMb to candMb
							exit repeat
						end if
					end try
				end repeat
				if sentMb is not missing value then
					try
						set snt to (messages of sentMb whose (address of every to recipient) contains addr)
						repeat with m in snt
							try
								set rid to id of m as text
								set rfc to ""
								try
									set rfc to message id of m
								end try
								set ds to my isoDate(date sent of m)
								set subj to subject of m
								set toAddr to ""
								set toName to ""
								set recs to to recipients of m
								if (count of recs) > 0 then
									set r1 to item 1 of recs
									set toAddr to address of r1
									try
										set nm to name of r1
										if nm is not missing value then set toName to nm
									end try
								end if
								set rec to "S" & fieldSep & rid & fieldSep & rfc & fieldSep & ds & fieldSep & toAddr & fieldSep & toName & fieldSep & subj
								copy rec to end of out
							end try
						end repeat
					end try
				end if
			end if
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
