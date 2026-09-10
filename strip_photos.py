#!/usr/bin/env python3
"""
strip_photos.py — pull PHOTO fields out of a vCard file, save them to a
sidecar JSON keyed by UID, and write a photo-free vCard file that's safe
to hand to a small model or script for merging.

No external libraries. Handles vCard line folding per RFC 6350/2426:
a continuation line starts with a single space or tab.

USAGE:
    python3 strip_photos.py input.vcf stripped.vcf photos.json

EXAMPLE:
    python3 strip_photos.py contacts_big.vcf stripped.vcf photos.json

    This reads contacts_big.vcf, writes a photo-free copy to
    stripped.vcf (safe to hand to a small model or merge tool), and
    saves every removed photo to photos.json, keyed by each
    contact's UID so it can find its way back later.

    Sample output:
        Contacts processed: 214
        Photos extracted:   61
        Stripped file:      stripped.vcf
        Photo sidecar:      photos.json
"""
import sys
import json
import hashlib
import re

def unfold(text):
    """Join folded lines back into single logical lines."""
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    lines = text.split('\n')
    out = []
    for line in lines:
        if line.startswith(' ') or line.startswith('\t'):
            if out:
                out[-1] += line[1:]
            # else: malformed leading continuation, drop it
        else:
            out.append(line)
    return out

def fold(line, limit=75):
    """Fold a single logical line back to RFC-safe chunks."""
    if len(line.encode('utf-8')) <= limit:
        return line
    out = []
    cur = line
    first = True
    while cur:
        take = limit if first else limit - 1
        chunk = cur[:take]
        # avoid splitting mid multi-byte char (rough safety, ok for ascii-heavy vcards)
        cur = cur[take:]
        out.append(chunk if first else ' ' + chunk)
        first = False
    return '\n'.join(out)

def split_vcards(lines):
    """Group unfolded lines into a list of vCard blocks (each a list of lines)."""
    cards = []
    current = None
    for line in lines:
        if line.strip().upper() == 'BEGIN:VCARD':
            current = [line]
        elif line.strip().upper() == 'END:VCARD':
            if current is not None:
                current.append(line)
                cards.append(current)
            current = None
        elif current is not None:
            current.append(line)
    return cards

def get_prop_value(card_lines, prop_name):
    for l in card_lines:
        if l.upper().startswith(prop_name.upper() + ':') or l.upper().startswith(prop_name.upper() + ';'):
            return l.split(':', 1)[-1].strip()
    return None

def make_stable_uid(card_lines):
    """Build a deterministic UID from name + phone/email, so it stays the
    same across re-runs even without an existing UID."""
    fn = get_prop_value(card_lines, 'FN') or ''
    tel = get_prop_value(card_lines, 'TEL') or ''
    email = get_prop_value(card_lines, 'EMAIL') or ''
    basis = f"{fn}|{tel}|{email}".encode('utf-8')
    return 'stripscript-' + hashlib.sha1(basis).hexdigest()[:16]

def strip_one(card_lines, photos):
    uid = None
    new_lines = []
    photo_buf = None  # (uid placeholder set after we know it)
    has_photo = False

    for l in card_lines:
        if l.upper().startswith('UID:') or l.upper().startswith('UID;'):
            uid = l.split(':', 1)[-1].strip()

    if not uid:
        uid = make_stable_uid(card_lines)

    for l in card_lines:
        if l.upper().startswith('PHOTO:') or l.upper().startswith('PHOTO;'):
            photos[uid] = l  # store the full original PHOTO line, unfolded
            has_photo = True
            continue  # drop from output
        new_lines.append(l)

    # make sure UID line exists in the output so reattach can find it later
    if not any(x.upper().startswith('UID:') for x in new_lines):
        # insert UID right after BEGIN:VCARD
        insert_at = 1 if new_lines and new_lines[0].upper().startswith('BEGIN:VCARD') else 0
        new_lines.insert(insert_at, f"UID:{uid}")

    if has_photo:
        # leave a marker so it's obvious, during merge, that a photo existed
        end_idx = len(new_lines) - 1 if new_lines and new_lines[-1].upper().startswith('END:VCARD') else len(new_lines)
        new_lines.insert(end_idx, "X-PHOTO-REMOVED:true")

    return new_lines

def main(in_path, out_path, photos_json_path):
    with open(in_path, 'r', encoding='utf-8', errors='replace') as f:
        raw = f.read()
    lines = unfold(raw)
    cards = split_vcards(lines)

    photos = {}
    out_cards = []
    for c in cards:
        out_cards.append(strip_one(c, photos))

    with open(out_path, 'w', encoding='utf-8') as f:
        for card in out_cards:
            for l in card:
                f.write(fold(l) + '\n')

    with open(photos_json_path, 'w', encoding='utf-8') as f:
        json.dump(photos, f)

    print(f"Contacts processed: {len(cards)}")
    print(f"Photos extracted:   {len(photos)}")
    print(f"Stripped file:      {out_path}")
    print(f"Photo sidecar:      {photos_json_path}")

if __name__ == '__main__':
    if len(sys.argv) != 4:
        print("Usage: strip_photos.py input.vcf output_stripped.vcf photos.json")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2], sys.argv[3])
