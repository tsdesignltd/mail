#!/bin/bash
# MailDeck 起動スクリプト — Finder でダブルクリックでも、ターミナルからでも起動できます
cd "$(dirname "$0")"

PORT=8765

# 既に起動済みならブラウザを開くだけ
if curl -s -o /dev/null --max-time 2 "http://localhost:$PORT/api/sync/status"; then
  echo "MailDeck は既に起動しています → http://localhost:$PORT"
  open "http://localhost:$PORT"
  exit 0
fi

if ! pgrep -xq Mail; then
  echo "Mail.app を起動します..."
  open -a Mail
fi

echo "MailDeck を起動します (終了するにはこのウインドウで Ctrl+C)..."
python3 server.py &
SERVER_PID=$!

# サーバーが応答したらブラウザを開く
for i in $(seq 1 30); do
  if curl -s -o /dev/null --max-time 1 "http://localhost:$PORT/api/sync/status"; then
    open "http://localhost:$PORT"
    break
  fi
  sleep 0.5
done

wait $SERVER_PID
