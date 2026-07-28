-- move_to_trash.applescript <accountName> [<mailbox> <id> <rfcId>]...
-- 指定メールを Mail.app のゴミ箱へ移動する(delete = ゴミ箱へ移動・復元可能)。
-- 照合は RFC Message-ID 優先・番号IDフォールバック。Gmail の [Gmail] 配下は走査で解決。
-- 出力: ゴミ箱へ移した件数
on run argv
	set acctName to item 1 of argv
	set n to 0
	with timeout of 890 seconds
		tell application "Mail"
			set acct to account acctName
			set i to 2
			repeat while i ≤ (count of argv)
				set mbName to item i of argv
				set msgId to (item (i + 1) of argv) as integer
				set rfcId to item (i + 2) of argv
				set i to i + 3
				-- メールボックス解決(直接→ダメなら走査)
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
				if mb is not missing value then
					set theMsg to missing value
					if rfcId is not "" then
						try
							set f to (messages of mb whose message id is rfcId)
							if (count of f) > 0 then set theMsg to item 1 of f
						end try
					end if
					if theMsg is missing value then
						try
							set f2 to (messages of mb whose id is msgId)
							if (count of f2) > 0 then set theMsg to item 1 of f2
						end try
					end if
					if theMsg is not missing value then
						try
							delete theMsg
							set n to n + 1
						end try
					end if
				end if
			end repeat
		end tell
	end timeout
	return (n as text)
end run
