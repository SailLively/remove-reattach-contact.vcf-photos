#!/usr/bin/env python3
"""
reattach_photos.py — put PHOTO fields back into a merged vCard file,
matched by the UID that strip_photos.py guaranteed exists.

USAGE:
    python3 reattach_photos.py merged.vcf photos.json final_output.vcf

EXAMPLE:
    python3 reattach_photos.py opencode_merged.vcf photos.json 2026-09-10_opencode_contact_merge.vcf

    Run this AFTER your merge tool (OpenCode, local model, etc.) has
    finished working on the photo-free file from strip_photos.py.
    merged.vcf is that tool's output. photos.json is the same
    sidecar file strip_photos.py made earlier — don't lose it.

    Sample output:
        Contacts in merged file: 198
        Photos reattached:       59 of 61 available
        Final file: 2026-09-10_opencode_contact_merge.vcf

    If a photo doesn't come back, the script says exactly which
    contact it lost track of (a merge tool dropped or changed its
    UID) instead of silently skipping it.
"""
import sys
import json
from strip_photos import unfold, fold, split_vcards, get_prop_value

def reattach_one(card_lines, photos, stats):
    uid = get_prop_value(card_lines, 'UID')
    new_lines = [l for l in card_lines if not l.upper().startswith('X-PHOTO-REMOVED')]

    had_marker = any(l.upper().startswith('X-PHOTO-REMOVED') for l in card_lines)

    if uid and uid in photos:
        end_idx = len(new_lines) - 1 if new_lines and new_lines[-1].upper().startswith('END:VCARD') else len(new_lines)
        new_lines.insert(end_idx, photos[uid])
        stats['reattached'] += 1
    elif had_marker:
        stats['missing'].append(uid or '(no uid)')

    return new_lines

def main(merged_path, photos_json_path, out_path):
    with open(photos_json_path, 'r', encoding='utf-8') as f:
        photos = json.load(f)

    with open(merged_path, 'r', encoding='utf-8', errors='replace') as f:
        raw = f.read()
    cards = split_vcards(unfold(raw))

    stats = {'reattached': 0, 'missing': []}
    out_cards = [reattach_one(c, photos, stats) for c in cards]

    with open(out_path, 'w', encoding='utf-8') as f:
        for card in out_cards:
            for l in card:
                f.write(fold(l) + '\n')

    print(f"Contacts in merged file: {len(cards)}")
    print(f"Photos reattached:       {stats['reattached']} of {len(photos)} available")
    if stats['missing']:
        print(f"WARNING - had a photo marker but no UID match: {stats['missing']}")
    print(f"Final file: {out_path}")

if __name__ == '__main__':
    if len(sys.argv) != 4:
        print("Usage: reattach_photos.py merged.vcf photos.json final_output.vcf")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2], sys.argv[3])
