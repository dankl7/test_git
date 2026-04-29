# Fix telegram_client.py indentation
with open('ingestion/telegram_client.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove the bad logger.info and add fixed version
if 'monitor.scan_complete = True\n        logger.info(' in content:
    # Remove emoji lines
    content = content.replace('f"✅ Scan complete for {monitor.username}",', '')
    content = content.replace('f"📊 SCAN REPORT for {monitor.username}"', '')
    content = content.replace('f"💡 Status: Waiting for new posts from {monitor.username}..."', '')
    
    with open('ingestion/telegram_client.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Fixed emoji issue")
else:
    print("Pattern not found, file may already be fixed")
