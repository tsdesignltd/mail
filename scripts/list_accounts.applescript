-- list_accounts.applescript
-- 有効なアカウントと、受信トレイ相当・送信済み相当のメールボックス名と件数を返す
-- 出力: アカウント名␞受信MB␞受信件数␞送信MB␞送信件数 を ␟ で連結
--   (送信MBが見つからない場合は 送信MB="" 送信件数=0)
-- 注: Gmail の送信済みは [Gmail] 配下にネストされ `mailbox "名前" of account` で
--     参照できない(-1728)。そのためメールボックス「オブジェクト」を走査して解決する。
on run argv
	set fieldSep to character id 9246 -- ␞
	set recSep to character id 9247 -- ␟
	set sentCandidates to {"Sent Mail", "Sent Messages", "送信済みメール", "送信済みメッセージ", "Sent", "送信済み", "送信"}
	set out to {}
	tell application "Mail"
		repeat with acct in accounts
			try
				if enabled of acct then
					set acctName to name of acct
					set mbNames to name of mailboxes of acct
					-- 受信トレイ (INBOX は全アカウントで直接参照できる)
					if mbNames contains "INBOX" then
						set inName to "INBOX"
					else if mbNames contains "受信" then
						set inName to "受信"
					else
						set inName to ""
					end if
					-- 送信済み: 候補名に一致するメールボックスオブジェクトを走査で探す
					set sentName to ""
					set sentCount to 0
					repeat with cand in sentCandidates
						set candName to cand as text
						if mbNames contains candName then
							repeat with mb in (every mailbox of acct)
								try
									if (name of mb) is candName then
										set sentName to candName
										set sentCount to (count of messages of mb)
										exit repeat
									end if
								end try
							end repeat
						end if
						if sentName is not "" then exit repeat
					end repeat
					if inName is not "" then
						set inCount to count of messages of mailbox inName of acct
						copy (acctName & fieldSep & inName & fieldSep & (inCount as text) & fieldSep & sentName & fieldSep & (sentCount as text)) to end of out
					end if
				end if
			end try
		end repeat
	end tell
	set AppleScript's text item delimiters to recSep
	set txt to out as text
	set AppleScript's text item delimiters to ""
	return txt
end run
