with open('ingestion/telegram_client.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find line 239 (for loop) and keep everything up to 247 (end of for body)
# Then add proper closing

fixed_lines = lines[:248]  # Keep up to line 248 (empty line after for loop)

# Add proper closing - dedent to match function level
fixed_lines.append('\n')
fixed_lines.append('        monitor.scan_complete = True\n')
fixed_lines.append('        logger.info("✅ Scan complete for " + monitor.username)\n')
fixed_lines.append('\n')
fixed_lines.append('    except Exception as e:\n')
fixed_lines.append('        logger.error(f"Error scanning: {e}")\n')
fixed_lines.append('\n')
fixed_lines.append('    self._scan_in_progress = False\n')

with open('ingestion/telegram_client.py', 'w', encoding='utf-8') as f:
    f.writelines(fixed_lines)

print("Fixed! Added proper try/except closing")
