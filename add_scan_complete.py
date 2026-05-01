with open('ingestion/telegram_client.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add scan_complete at the end
content = content.rstrip() + '\n\nmonitor.scan_complete = True\nlogger.info("Scan complete")\n'

with open('ingestion/telegram_client.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Added scan_complete')
