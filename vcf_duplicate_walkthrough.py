#!/usr/bin/env python3
"""
vcf_duplicate_walkthrough.py — go through duplicate contacts one group
at a time. For each group you see the full contact ("blob") at each
line location, and choose:

    m        merge them into one contact (auto-combined, you approve
             the result before it's kept)
    1        keep copy 1, delete copy 2 (or 3, 4, ...)
    2        keep copy 2, delete copy 1 (etc for higher numbers)
    s        skip this group, leave both as-is
    q        stop here, save everything decided so far

USAGE:
    python3 vcf_duplicate_walkthrough.py input.vcf output.vcf

Nothing is written until you've gone through the groups (or quit) —
input.vcf is never touched. output.vcf is the new file with your
choices applied; everything you didn't reach a decision on is copied
through unchanged.
"""
import sys
import re

def unfold_block(raw_lines):
    out = []
    for line in raw_lines:
        if line.startswith(' ') or line.startswith('\t'):
            if out:
                out[-1] += line[1:]
        else:
            out.append(line)
    return out

def fold(line, limit=75):
    if len(line.encode('utf-8')) <= limit:
        return line
    out = []
    cur = line
    first = True
    while cur:
        take = limit if first else limit - 1
        chunk = cur[:take]
        cur = cur[take:]
        out.append(chunk if first else ' ' + chunk)
        first = False
    return '\n'.join(out)

def read_raw_lines(path):
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        raw = f.read()
    raw = raw.replace('\r\n', '\n').replace('\r', '\n')
    return raw.split('\n')

def find_blocks(raw_lines):
    blocks = []
    start = None
    for i, line in enumerate(raw_lines):
        s = line.strip().upper()
        if s == 'BEGIN:VCARD':
            start = i
        elif s == 'END:VCARD' and start is not None:
            end = i
            block_raw = raw_lines[start:end + 1]
            unfolded = unfold_block(block_raw)
            blocks.append({'start': start, 'end': end, 'props': unfolded})
            start = None
    return blocks

def get_prop(props, name):
    name_u = name.upper()
    for l in props:
        head = l.split(':', 1)[0]
        prop = head.split(';', 1)[0].upper()
        if prop == name_u:
            return l.split(':', 1)[-1].strip()
    return None

def get_all_props(props, name):
    name_u = name.upper()
    vals = []
    for l in props:
        head = l.split(':', 1)[0]
        prop = head.split(';', 1)[0].upper()
        if prop == name_u:
            vals.append(l)  # keep full line, params and all
    return vals

def digits_only(s):
    return re.sub(r'\D', '', s or '')

def identity_keys(props):
    keys = set()
    for l in get_all_props(props, 'TEL'):
        v = l.split(':', 1)[-1]
        d = digits_only(v)
        if len(d) >= 7:
            keys.add('tel:' + d[-10:])
    for l in get_all_props(props, 'EMAIL'):
        v = l.split(':', 1)[-1].strip().lower()
        if v:
            keys.add('email:' + v)
    return keys

def name_of(props):
    return get_prop(props, 'FN') or get_prop(props, 'N') or '(no name)'

def display_line(l, limit=90):
    """Shorten PHOTO (or any huge base64 blob) lines for terminal viewing."""
    if len(l) > limit:
        head = l.split(':', 1)[0]
        return f"{head}: [large value, {len(l)} chars, not shown in full here]"
    return l

def print_blob(block, label):
    print(f"--- {label}: lines {block['start']+1}-{block['end']+1} ---")
    for l in block['props']:
        print("  " + display_line(l))
    print()

def build_groups(blocks):
    n = len(blocks)
    parent = list(range(n))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    index = {}
    for i, b in enumerate(blocks):
        for k in identity_keys(b['props']):
            index.setdefault(k, []).append(i)
    for k, idxs in index.items():
        for i in idxs[1:]:
            union(idxs[0], i)
    groups_map = {}
    for i in range(n):
        groups_map.setdefault(find(i), []).append(i)
    return [sorted(v) for v in groups_map.values() if len(v) > 1]

SINGULAR_PROPS = {'FN', 'N', 'NICKNAME', 'BDAY', 'ORG', 'TITLE', 'UID', 'VERSION', 'PHOTO'}

def auto_merge(blocks_in_group):
    """Build one merged vCard from N copies. Multi-value props (TEL,
    EMAIL, CATEGORIES, ADR, NOTE, URL) are unioned and de-duplicated.
    Singular props take the first non-empty value found."""
    all_props_lists = [b['props'] for b in blocks_in_group]

    # collect every property name across all copies, in first-seen order
    prop_names = []
    for props in all_props_lists:
        for l in props:
            head = l.split(':', 1)[0]
            nm = head.split(';', 1)[0].upper()
            if nm not in ('BEGIN', 'END') and nm not in prop_names:
                prop_names.append(nm)

    merged_lines = ['BEGIN:VCARD']
    if 'VERSION' in prop_names:
        v = get_prop(all_props_lists[0], 'VERSION') or '3.0'
        merged_lines.append(f'VERSION:{v}')
        prop_names.remove('VERSION')

    for nm in prop_names:
        if nm in SINGULAR_PROPS:
            for props in all_props_lists:
                lines = get_all_props(props, nm)
                if lines:
                    merged_lines.append(lines[0])
                    break
        elif nm == 'CATEGORIES':
            seen = []
            for props in all_props_lists:
                for l in get_all_props(props, 'CATEGORIES'):
                    val = l.split(':', 1)[-1]
                    for cat in val.split(','):
                        cat = cat.strip()
                        if cat and cat not in seen:
                            seen.append(cat)
            if seen:
                merged_lines.append('CATEGORIES:' + ','.join(seen))
        elif nm == 'TEL':
            seen_full_lines = []
            seen_digit_keys = set()
            for props in all_props_lists:
                for l in get_all_props(props, 'TEL'):
                    v = l.split(':', 1)[-1]
                    d = digits_only(v)
                    key = d[-10:] if len(d) >= 7 else v.strip().lower()
                    if key not in seen_digit_keys:
                        seen_digit_keys.add(key)
                        seen_full_lines.append(l)
            merged_lines.extend(seen_full_lines)
        else:
            seen_full_lines = []
            seen_values = set()
            for props in all_props_lists:
                for l in get_all_props(props, nm):
                    val = l.split(':', 1)[-1].strip().lower()
                    if val not in seen_values:
                        seen_values.add(val)
                        seen_full_lines.append(l)
            merged_lines.extend(seen_full_lines)

    if not any(l.upper().startswith('UID:') for l in merged_lines):
        import hashlib
        fn = get_prop(all_props_lists[0], 'FN') or ''
        merged_lines.insert(1, 'UID:merged-' + hashlib.sha1(fn.encode('utf-8')).hexdigest()[:16])

    merged_lines.append('END:VCARD')
    return merged_lines

def main():
    if len(sys.argv) != 3:
        print("Usage: python3 vcf_duplicate_walkthrough.py input.vcf output.vcf")
        sys.exit(1)
    in_path, out_path = sys.argv[1], sys.argv[2]

    raw_lines = read_raw_lines(in_path)
    blocks = find_blocks(raw_lines)
    groups = build_groups(blocks)

    if not groups:
        print("No duplicate groups found. Nothing to do.")
        return

    print(f"Found {len(groups)} duplicate group(s).\n")

    # decisions: block_index -> 'drop' or ('replace_with', merged_lines) applied to the WHOLE group as one unit
    drop_indices = set()
    replace_group = {}  # group's first block index -> merged lines to put in its place

    quit_early = False
    merged_count = 0
    kept_one_count = 0
    skipped_count = 0
    groups_reached = 0

    for gi, idxs in enumerate(groups, start=1):
        print(f"=========== Group {gi} of {len(groups)}: \"{name_of(blocks[idxs[0]]['props'])}\" ===========")
        for ci, i in enumerate(idxs, start=1):
            print_blob(blocks[i], f"Copy {ci}")

        groups_reached += 1
        while True:
            choice = input(
                "Choose: [m]erge all copies, keep copy number (e.g. 1), [s]kip, [q]uit: "
            ).strip().lower()

            if choice == 'q':
                quit_early = True
                groups_reached -= 1  # didn't actually decide this one
                break

            if choice == 's':
                skipped_count += 1
                break

            if choice == 'm':
                merged = auto_merge([blocks[i] for i in idxs])
                print("\n--- Proposed merged contact ---")
                for l in merged:
                    print("  " + display_line(l))
                confirm = input("Use this merged contact? [y/n]: ").strip().lower()
                if confirm == 'y':
                    replace_group[idxs[0]] = merged
                    for i in idxs[1:]:
                        drop_indices.add(i)
                    merged_count += 1
                    break
                else:
                    print("Not applied. Choose again for this group.\n")
                    continue

            if choice.isdigit():
                keep_num = int(choice)
                if 1 <= keep_num <= len(idxs):
                    keep_i = idxs[keep_num - 1]
                    for i in idxs:
                        if i != keep_i:
                            drop_indices.add(i)
                    print(f"Keeping copy {keep_num}, deleting the rest.\n")
                    kept_one_count += 1
                    break
                else:
                    print(f"No copy numbered {keep_num} in this group.")
                    continue

            print("Not understood. Type m, s, q, or a copy number.")

        print()
        if quit_early:
            break

    # assemble output
    out_lines = []
    for i, b in enumerate(blocks):
        if i in drop_indices:
            continue
        if i in replace_group:
            out_lines.extend(replace_group[i])
        else:
            out_lines.extend(b['props'])

    # anything outside any BEGIN/END block (rare, but keep it safe) - reattach in original order
    # simplest safe approach: rebuild by walking blocks in order and copying
    # non-block raw lines between them too
    final = []
    cursor = 0
    for i, b in enumerate(blocks):
        final.extend(raw_lines[cursor:b['start']])
        if i in drop_indices:
            pass
        elif i in replace_group:
            final.extend(replace_group[i])
        else:
            final.extend(b['props'])
        cursor = b['end'] + 1
    final.extend(raw_lines[cursor:])

    with open(out_path, 'w', encoding='utf-8') as f:
        for l in final:
            f.write(fold(l) + '\n')

    print(f"Done. Merged: {merged_count} group(s). Kept one copy (deleted the rest): {kept_one_count} group(s). "
          f"Skipped: {skipped_count} group(s).")
    remaining = len(groups) - groups_reached
    if remaining > 0:
        print(f"Not reached (you quit early): {remaining} group(s), left untouched.")
    print(f"Wrote: {out_path}")

if __name__ == '__main__':
    main()
