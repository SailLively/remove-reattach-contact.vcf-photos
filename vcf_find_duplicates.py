#!/usr/bin/env python3
"""
vcf_find_duplicates.py — find contacts that appear more than once in ONE
vCard file, tell you which lines each copy sits on, and show a full
field-by-field diff between the copies (not just categories/photo —
every property).

Matching: same rule as vcf_report.py — any shared phone (last 10
digits) or email counts as the same person, so formatting differences
like "+1 (555) 234-5678" vs "5552345678" don't create false negatives.

USAGE:
    python3 vcf_find_duplicates.py yourfile.vcf

EXAMPLE:
    python3 vcf_find_duplicates.py contacts_current.vcf

    Sample output:
        Found 3 duplicate group(s), 7 contact(s) total involved.

        === Group 1: "Dana Formatted" (2 copies) ===
        Copy 1: lines 14-19
        Copy 2: lines 340-347
        Field differences:
          CATEGORIES:
            copy 1: Work
            copy 2: Work,Family
          TEL:
            copy 1: +1 (555) 234-5678
            copy 2: 5552345678
          (all other fields match)
"""
import sys
import re

def unfold_block(raw_lines):
    """Unfold a small run of raw lines (already known to be one vCard)."""
    out = []
    for line in raw_lines:
        if line.startswith(' ') or line.startswith('\t'):
            if out:
                out[-1] += line[1:]
        else:
            out.append(line)
    return out

def read_raw_lines(path):
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        raw = f.read()
    raw = raw.replace('\r\n', '\n').replace('\r', '\n')
    return raw.split('\n')

def find_blocks(raw_lines):
    """Return list of (start_line_1based, end_line_1based, unfolded_props)."""
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
            blocks.append((start + 1, end + 1, unfolded))
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
            vals.append(l.split(':', 1)[-1].strip())
    return vals

def all_prop_names(props):
    names = []
    for l in props:
        head = l.split(':', 1)[0]
        prop = head.split(';', 1)[0].upper()
        if prop not in ('BEGIN', 'END', 'VERSION') and prop not in names:
            names.append(prop)
    return names

def digits_only(s):
    return re.sub(r'\D', '', s or '')

def identity_keys(props):
    keys = set()
    for t in get_all_props(props, 'TEL'):
        d = digits_only(t)
        if len(d) >= 7:
            keys.add('tel:' + d[-10:])
    for e in get_all_props(props, 'EMAIL'):
        e = e.strip().lower()
        if e:
            keys.add('email:' + e)
    return keys

def name_of(props):
    return get_prop(props, 'FN') or get_prop(props, 'N') or '(no name)'

def shorten(val, limit=60):
    if val is None:
        return '(missing)'
    if len(val) > limit:
        return f"[{len(val)} chars, starts: {val[:limit]}...]"
    return val or '(empty)'

def main(path):
    raw_lines = read_raw_lines(path)
    blocks = find_blocks(raw_lines)

    # union-find over shared identity keys, same approach as vcf_report.py
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
    for i, (_, _, props) in enumerate(blocks):
        for k in identity_keys(props):
            index.setdefault(k, []).append(i)
    for k, idxs in index.items():
        for i in idxs[1:]:
            union(idxs[0], i)

    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    dup_groups = [v for v in groups.values() if len(v) > 1]

    total_involved = sum(len(v) for v in dup_groups)
    print(f"Found {len(dup_groups)} duplicate group(s), {total_involved} contact(s) total involved.\n")

    for gi, idxs in enumerate(dup_groups, start=1):
        first_props = blocks[idxs[0]][2]
        print(f'=== Group {gi}: "{name_of(first_props)}" ({len(idxs)} copies) ===')
        for ci, i in enumerate(idxs, start=1):
            start, end, _ = blocks[i]
            print(f"Copy {ci}: lines {start}-{end}")

        # gather every property name seen across all copies in this group
        names = []
        for i in idxs:
            for nm in all_prop_names(blocks[i][2]):
                if nm not in names:
                    names.append(nm)

        diffs = []
        no_diff = []
        for nm in names:
            values_per_copy = [get_all_props(blocks[i][2], nm) for i in idxs]
            if all(v == values_per_copy[0] for v in values_per_copy):
                no_diff.append(nm)
            else:
                diffs.append((nm, values_per_copy))

        if diffs:
            print("Field differences:")
            for nm, values_per_copy in diffs:
                print(f"  {nm}:")
                for ci, vals in enumerate(values_per_copy, start=1):
                    if not vals:
                        print(f"    copy {ci}: (missing)")
                    else:
                        shown = ', '.join(shorten(v) for v in vals)
                        print(f"    copy {ci}: {shown}")
        if no_diff:
            print(f"  (matching on: {', '.join(no_diff)})")
        print()

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: python3 vcf_find_duplicates.py yourfile.vcf")
        sys.exit(1)
    main(sys.argv[1])
