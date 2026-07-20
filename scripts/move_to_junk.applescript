-- move_to_junk.applescript <acct1> <mb1> <kind1> <ref1> [<acct2> <mb2> <kind2> <ref2> ...]
-- 指定メッセージを「そのアカウント自身の迷惑メールフォルダ」へ移動する。
--   kind = "id"  : Mail 内部の numeric id
--   kind = "mid" : RFC Message-ID (Envelope Index 直読みモード用)
-- 迷惑フォルダ名はアカウントにより異なるため候補から自動解決する。
-- 戻り値: 1レコード1文字 ("1"=成功 / "0"=失敗) をカンマ区切りで、引数の順に返す
on run argv
	set junkNames to {"迷惑メール", "Junk", "Junk E-mail", "Spam", "spam"}
	set results to {}
	tell application "Mail"
		set i to 1
		repeat while i ≤ (count of argv)
			set acctName to item i of argv
			set mbName to item (i + 1) of argv
			set refKind to item (i + 2) of argv
			set refVal to item (i + 3) of argv
			try
				set acct to account acctName
				set junkMB to missing value
				repeat with cand in junkNames
					if (exists mailbox (cand as text) of acct) then
						set junkMB to mailbox (cand as text) of acct
						exit repeat
					end if
				end repeat
				if junkMB is missing value then error "junk mailbox not found"
				set mb to mailbox mbName of acct
				if refKind is "id" then
					set found to (messages of mb whose id is (refVal as integer))
				else
					set found to (messages of mb whose message id is refVal)
				end if
				if (count of found) > 0 then
					move (item 1 of found) to junkMB
					copy "1" to end of results
				else
					copy "0" to end of results
				end if
			on error
				copy "0" to end of results
			end try
			set i to i + 4
		end repeat
	end tell
	set AppleScript's text item delimiters to ","
	set txt to results as text
	set AppleScript's text item delimiters to ""
	return txt
end run
