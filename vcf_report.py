#!/usr/bin/env python3
"""
vcf_report.py — sanity-check vCard files before and after editing.

Reports, per file: contact count, how many have CATEGORIES (and which
categories are in use), how many have a PHOTO, how many look empty or
broken, and any duplicates within that same file.

If you give it exactly two files, it also prints a diff: contacts
added, contacts removed, and contacts whose CATEGORIES or PHOTO
changed between the two — matched by name/phone/email, not UID.

USAGE:
    python3 vcf_report.py file1.vcf                  (report on one file)
    python3 vcf_report.py before.vcf after.vcf        (report on both + diff)

EXAMPLE:
    python3 vcf_report.py contacts_current_stripped.vcf contacts_current_stripped_updated.vcf

    Sample output:
        === contacts_current_stripped.vcf ===
        Contacts:        214
        With CATEGORIES: 180  (34 missing)
        With PHOTO:      0
        Empty/broken:    2
        Duplicates in file: 0

        === contacts_current_stripped_updated.vcf ===
        Contacts:        221
        With CATEGORIES: 221  (0 missing)
        With PHOTO:      0
        Empty/broken:    0
        Duplicates in file: 0

        === DIFF: before -> after ===
        Added contacts (7):
          - Jane Doe
          - ...
        Removed contacts (0): (none)
        CATEGORIES changed on 34 contacts:
          - John Smith: '' -> 'Work,Friends'
          - ...
        PHOTO changed on 0 contacts.
"""
import sys
import re

def unfold(text):
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    lines = text.split('\n')
    out = []
    for line in lines:
        if line.startswith(' ') or line.startswith('\t'):
            if out:
                out[-1] += line[1:]
        else:
            out.append(line)
    return out

def split_vcards(lines):
    cards = []
    current = None
    for line in lines:
        s = line.strip().upper()
        if s == 'BEGIN:VCARD':
            current = [line]
        elif s == 'END:VCARD':
            if current is not None:
                current.append(line)
                cards.append(current)
            current = None
        elif current is not None:
            current.append(line)
    return cards

def get_prop(card, name):
    """Return the value of the first matching property, or None."""
    name_u = name.upper()
    for l in card:
        head = l.split(':', 1)[0]
        prop = head.split(';', 1)[0].upper()
        if prop == name_u:
            return l.split(':', 1)[-1].strip()
    return None

def get_all_props(card, name):
    name_u = name.upper()
    vals = []
    for l in card:
        head = l.split(':', 1)[0]
        prop = head.split(';', 1)[0].upper()
        if prop == name_u:
            vals.append(l.split(':', 1)[-1].strip())
    return vals

def digits_only(s):
    return re.sub(r'\D', '', s or '')

def norm_name(card):
    fn = (get_prop(card, 'FN') or '').strip().lower()
    fn = re.sub(r'\s+', ' ', fn)
    return fn

def identity_keys(card):
    """All the ways this contact could be recognized across files: every
    phone (last 10 digits, to survive +1/formatting differences) and
    every email (lowercased). A contact matches another if ANY key
    overlaps - far more forgiving than comparing just the first phone."""
    keys = set()
    for t in get_all_props(card, 'TEL'):
        d = digits_only(t)
        if len(d) >= 7:
            keys.add('tel:' + d[-10:])
    for e in get_all_props(card, 'EMAIL'):
        e = e.strip().lower()
        if e:
            keys.add('email:' + e)
    return keys

def build_index(cards):
    """key -> list of card indices that carry that key."""
    index = {}
    for i, c in enumerate(cards):
        for k in identity_keys(c):
            index.setdefault(k, []).append(i)
    return index

def fuzzy_ratio(a, b):
    import difflib
    return difflib.SequenceMatcher(None, a, b).ratio()

def is_empty(card):
    fn = (get_prop(card, 'FN') or '').strip()
    tels = [t for t in get_all_props(card, 'TEL') if digits_only(t)]
    emails = [e for e in get_all_props(card, 'EMAIL') if e.strip()]
    return not fn and not tels and not emails

def load(path):
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        raw = f.read()
    return split_vcards(unfold(raw))

def name_of(card):
    return get_prop(card, 'FN') or get_prop(card, 'N') or '(no name)'

def report(path):
    cards = load(path)
    total = len(cards)
    with_cat = sum(1 for c in cards if get_prop(c, 'CATEGORIES'))
    with_photo = sum(1 for c in cards if get_prop(c, 'PHOTO'))
    empties = [c for c in cards if is_empty(c)]

    index = build_index(cards)
    # union-find: two contacts are the same group if they share ANY key
    parent = list(range(len(cards)))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    for k, idxs in index.items():
        for i in idxs[1:]:
            union(idxs[0], i)
    groups = {}
    for i in range(len(cards)):
        groups.setdefault(find(i), []).append(cards[i])
    dup_groups = [v for v in groups.values() if len(v) > 1]
    dupes = sum(len(v) for v in dup_groups)

    print(f"=== {path} ===")
    print(f"Contacts:        {total}")
    print(f"With CATEGORIES: {with_cat}  ({total - with_cat} missing)")
    print(f"With PHOTO:      {with_photo}")
    print(f"Empty/broken:    {len(empties)}")
    if empties:
        for c in empties[:10]:
            print(f"  - {name_of(c)} (uid={get_prop(c, 'UID')})")
        if len(empties) > 10:
            print(f"  ...and {len(empties) - 10} more")
    print(f"Duplicates in file: {dupes} contact(s) across {len(dup_groups)} group(s)")
    if dup_groups:
        for grp in dup_groups[:10]:
            print(f"  - {name_of(grp[0])} appears {len(grp)} times")
    print()
    return cards

def diff(cards_before, cards_after, label_before, label_after):
    # index every phone/email key from BEFORE, pointing at a card index
    before_index = build_index(cards_before)

    matched_before = set()
    matched_after = set()
    pairs = []  # (before_idx, after_idx)

    for j, c in enumerate(cards_after):
        found = None
        for k in identity_keys(c):
            if k in before_index:
                found = before_index[k][0]  # first before-contact carrying this key
                break
        if found is not None and found not in matched_before:
            pairs.append((found, j))
            matched_before.add(found)
            matched_after.add(j)

    truly_removed = [i for i in range(len(cards_before)) if i not in matched_before]
    truly_added = [j for j in range(len(cards_after)) if j not in matched_after]

    print(f"=== DIFF: {label_before} -> {label_after} ===")

    # fuzzy-name suggestion pass over whatever's left, before calling it final
    suggestions = []
    used_added = set()
    for bi in truly_removed:
        b = cards_before[bi]
        b_name = norm_name(b)
        if not b_name:
            continue
        best = None
        best_score = 0.0
        for aj in truly_added:
            if aj in used_added:
                continue
            score = fuzzy_ratio(b_name, norm_name(cards_after[aj]))
            if score > best_score:
                best_score = score
                best = aj
        if best is not None and best_score >= 0.72:
            suggestions.append((bi, best, best_score))
            used_added.add(best)

    suggested_before = {bi for bi, _, _ in suggestions}
    suggested_after = {aj for _, aj, _ in suggestions}
    final_removed = [i for i in truly_removed if i not in suggested_before]
    final_added = [j for j in truly_added if j not in suggested_after]

    print(f"Added contacts ({len(final_added)}):")
    if final_added:
        for j in final_added[:20]:
            print(f"  - {name_of(cards_after[j])}")
        if len(final_added) > 20:
            print(f"  ...and {len(final_added) - 20} more")
    else:
        print("  (none)")

    print(f"Removed contacts ({len(final_removed)}):")
    if final_removed:
        for i in final_removed[:20]:
            print(f"  - {name_of(cards_before[i])}")
        if len(final_removed) > 20:
            print(f"  ...and {len(final_removed) - 20} more")
    else:
        print("  (none)")

    if suggestions:
        print(f"\nPossible same-person matches ({len(suggestions)}) — name is close but no phone/email overlap, check these by hand:")
        for bi, aj, score in sorted(suggestions, key=lambda x: -x[2])[:20]:
            print(f"  - '{name_of(cards_before[bi])}'  <->  '{name_of(cards_after[aj])}'  (name similarity {score:.2f})")
        if len(suggestions) > 20:
            print(f"  ...and {len(suggestions) - 20} more")

    cat_changed = []
    photo_changed = []
    for bi, aj in pairs:
        b, a = cards_before[bi], cards_after[aj]
        b_cat = get_prop(b, 'CATEGORIES') or ''
        a_cat = get_prop(a, 'CATEGORIES') or ''
        if b_cat != a_cat:
            cat_changed.append((name_of(b), b_cat, a_cat))
        b_photo = get_prop(b, 'PHOTO')
        a_photo = get_prop(a, 'PHOTO')
        if bool(b_photo) != bool(a_photo) or (b_photo and a_photo and b_photo != a_photo):
            photo_changed.append((name_of(b), bool(b_photo), bool(a_photo)))

    print(f"\nCATEGORIES changed on {len(cat_changed)} contact(s):")
    for name, b_cat, a_cat in cat_changed[:20]:
        print(f"  - {name}: '{b_cat}' -> '{a_cat}'")
    if len(cat_changed) > 20:
        print(f"  ...and {len(cat_changed) - 20} more")

    print(f"PHOTO changed on {len(photo_changed)} contact(s):")
    for name, had, has in photo_changed[:20]:
        print(f"  - {name}: had_photo={had} -> has_photo={has}")
    if len(photo_changed) > 20:
        print(f"  ...and {len(photo_changed) - 20} more")

def main():
    if len(sys.argv) not in (2, 3):
        print("Usage:")
        print("  python3 vcf_report.py file.vcf")
        print("  python3 vcf_report.py before.vcf after.vcf")
        sys.exit(1)

    if len(sys.argv) == 2:
        report(sys.argv[1])
    else:
        before_path, after_path = sys.argv[1], sys.argv[2]
        cards_before = report(before_path)
        cards_after = report(after_path)
        diff(cards_before, cards_after, before_path, after_path)

if __name__ == '__main__':
    main()
