with open('parser/parser_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove processing_status references
content = content.replace(", processing_status='pending'", '')
content = content.replace("raw_post.processing_status = 'completed'\n", '')

with open('parser/parser_service.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Removed processing_status')
