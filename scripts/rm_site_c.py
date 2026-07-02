#!/usr/bin/env python3
"""Remove all site_c / incudal references from monitor.py"""
import re

path = '/root/projects/vps-monitor/monitor.py'
with open(path, encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
in_site_c_func = False

for i, line in enumerate(lines):
    stripped = line.lstrip()
    linenum = i + 1  # 1-indexed

    # 1. Docstring: remove "Site C" from the header comment
    if 'Site C' in line and 'incudal' in line:
        # Remove this line entirely, or replace
        # Keep the line but remove the Site C part: "Site A / Site D / Site E"
        new_line = line.replace('Site C  incudal   (公开 API + Bearer)  间隔 C_INTERVAL 秒', '')
        new_line = new_line.replace('Site A  ', 'Site A  ').strip()
        if new_line.strip():
            new_lines.append(new_line)
        continue

    # 2. Config block: remove all SITE_C_* config lines and their comment header
    if '# ---- Site C' in stripped:
        in_site_c_func = True
        continue
    if in_site_c_func and ('SITE_C_' in line or line.strip() == '' or line.startswith('#') or stripped.startswith('SITE_C')):
        # Check if we've exited the config block (next non-blank, non-site_c config)
        if line.strip() and not stripped.startswith('SITE_C') and not line.startswith('#') and line.strip() != '':
            in_site_c_func = False
            # This is the next section's line - process normally
        else:
            continue

    # Reset flag when we hit a blank line after removing config
    if in_site_c_func and linenum > 108:
        in_site_c_func = False

    # 3. state.json init: skip site_c entry
    if '"site_c":' in line and 'packages' in line:
        continue

    # 4. All site_c_* function definitions and their bodies
    if re.match(r'def (fetch_site_c|_site_c_|compare_site_c|notify_site_c_|monitor_site_c)\b', stripped):
        # Skip this function entirely - need to skip until next non-indented def or blank+unindented
        continue

    # 5. References within function bodies that are site_c specific:
    # Check if we're inside a function and the line references site_c utilities
    # This catches cases like: if _site_c_id(notify_site_c_restock( etc.

    # 6. Main loop: remove site_c polling lines
    if 'monitor_site_c' in line:
        continue

    # Remove from combined last_* assignment: "last_a = last_c = last_d = last_e = 0"
    if 'last_c' in line and ('last_a' in line or 'last_d' in line or 'last_e' in line):
        # Remove "last_c = " from the chain
        new_line = re.sub(r'last_c\s*=\s*', '', line)
        new_line = new_line.replace('last_a =  last_d', 'last_a = last_d')
        new_lines.append(new_line)
        continue

    # Comment about site_c in main loop
    if 'site_d/site_c' in line:
        new_line = line.replace('site_d/site_c', 'site_d/site_e')
        new_lines.append(new_line)
        continue

    # SITE_C_POLL_INTERVAL reference
    if 'SITE_C_POLL_INTERVAL' in line:
        continue

    # Line 1552: "if now - last_c >= SITE_C_POLL_INTERVAL:"
    if 'last_c' in line and 'SITE_C' not in line and 'last_a' not in line and 'last_d' not in line and 'last_e' not in line:
        # Check if it's a standalone last_c usage
        if re.search(r'\blast_c\b', line):
            continue

    new_lines.append(line)

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f"Original: {len(lines)} lines, New: {len(new_lines)} lines, Removed: {len(lines) - len(new_lines)}")
