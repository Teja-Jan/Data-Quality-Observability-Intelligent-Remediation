"""Fix indentation for TABs 3, 4, and 5 in app.py.

The issue:
- tabs = st.tabs(...) is now at 4-space indent (correct, top-level in function)
- with tabs[2]: is at 4-space (correct)
  - BUT its content is at 12-space (should be 8-space, i.e. was double-indented from old else: block)
- with tabs[3]: is at 8-space (should be 4-space)
  - content is at 12-space (should be 8-space)
- with tabs[4]: is at 8-space (should be 4-space)
  - content is at 12-space (should be 8-space)
"""
import re

with open('src/app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find and fix the indentation
# Strategy: Find the line ranges for each section and de-indent by 4 spaces

def find_line(lines, search_str, start=0):
    for i in range(start, len(lines)):
        if search_str in lines[i]:
            return i
    return -1

# Find key markers (0-indexed)
tab3_comment = find_line(lines, '# TAB 3', 1400)
tab4_comment = find_line(lines, '# TAB 4', tab3_comment + 1)
tab5_comment = find_line(lines, '# TAB 5', tab4_comment + 1)

print(f"TAB3 comment at line {tab3_comment+1}")
print(f"TAB4 comment at line {tab4_comment+1}")
print(f"TAB5 comment at line {tab5_comment+1}")
print(f"Total lines: {len(lines)}")

# TAB3 content: from tab3_comment to tab4_comment-1, de-indent by 4 spaces
# TAB4 content: from tab4_comment to tab5_comment-1, de-indent by 4 spaces
# TAB5 content: from tab5_comment to end, de-indent by 4 spaces

def deindent_range(lines, start, end, spaces=4):
    """Remove `spaces` spaces from the beginning of each line in range [start, end)."""
    prefix = ' ' * spaces
    result = []
    for i, line in enumerate(lines):
        if start <= i < end:
            if line.startswith(prefix):
                result.append(line[spaces:])
            elif line.strip() == '' or line.strip().startswith('#') and not line.startswith(prefix):
                result.append(line)
            else:
                result.append(line)
        else:
            result.append(line)
    return result

# Apply de-indentation to TAB3 content (lines tab3_comment to tab4_comment-1)
# But NOT the tab3_comment line itself or the 'with tabs[2]:' line (already correct)
# Check: the 'with tabs[2]:' should be at 4-space indent

tab3_with = find_line(lines, 'with tabs[2]:', tab3_comment)
tab4_with = find_line(lines, 'with tabs[3]:', tab4_comment)
tab5_with = find_line(lines, 'with tabs[4]:', tab5_comment)

print(f"TAB3 'with' at line {tab3_with+1}: {repr(lines[tab3_with][:40])}")
print(f"TAB4 'with' at line {tab4_with+1}: {repr(lines[tab4_with][:40])}")
print(f"TAB5 'with' at line {tab5_with+1}: {repr(lines[tab5_with][:40])}")

# Check indentation of content right after each 'with'
print(f"TAB3 content after 'with': {repr(lines[tab3_with+1][:40])}")
print(f"TAB4 content after 'with': {repr(lines[tab4_with+1][:40])}")

# De-indent everything from tab3_with+1 to end by 4 spaces
# (TAB3 body goes from 12-space to 8-space, TAB4/5 'with' goes from 8-space to 4-space, etc.)
new_lines = deindent_range(lines, tab3_with + 1, len(lines), spaces=4)

with open('src/app.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("Done! Applied 4-space de-indentation from TAB3 content onwards.")

# Verify
with open('src/app.py', 'r', encoding='utf-8') as f:
    verify_lines = f.readlines()

new_tab4_with = find_line(verify_lines, 'with tabs[3]:', tab4_comment)
new_tab5_with = find_line(verify_lines, 'with tabs[4]:', tab5_comment)
print(f"After fix - TAB4 'with' at line {new_tab4_with+1}: {repr(verify_lines[new_tab4_with][:40])}")
print(f"After fix - TAB5 'with' at line {new_tab5_with+1}: {repr(verify_lines[new_tab5_with][:40])}")
