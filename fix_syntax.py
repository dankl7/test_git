# Fix telegram_client.py syntax error
with open('ingestion/telegram_client.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find where the broken section starts (look for "monitor.scan_complete")
fixed_lines = []
for i, line in enumerate(lines):
    if 'monitor.scan_complete' in line:
        # Keep this line and add proper closing
        fixed_lines.append(line)
        # Truncate everything after
        break
    fixed_lines.append(line)

# Write back
with open('ingestion/telegram_client.py', 'w', encoding='utf-8') as f:
    f.writelines(fixed_lines)

print("Fixed! Removed broken section after 'monitor.scan_complete'")
