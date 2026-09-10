# .VCF Contact Python Script Tools

I was exporting contacts from Google and from many contact libraries/books, trying to merge a pile of different files into one that actually worked, and this is what got me there.

**All scripts are non-destructive.** Every one of them reads your file and writes a *new* file. Your original never gets touched.

Two of them don't even write a file — they just print a report to the screen so you can check things.

| Script | Writes a new file? | What it does |
|---|---|---|
| `vcf_report.py` | No, prints only | Counts contacts, categories, photos, empty entries. Compares two files. |
| `vcf_find_duplicates.py` | No, prints only | Finds duplicates in one file, shows line numbers and what's different. |
| `strip_photos.py` | Yes | Pulls photos out of a file so it's small enough to hand to a model. |
| `reattach_photos.py` | Yes | Puts photos back in after editing is done. |
| `vcf_duplicate_walkthrough.py` | Yes | Walks you through each duplicate, one at a time — merge, delete, or keep. |

Run all of them from a terminal, in the folder where the scripts and your `.vcf` files sit. You'll need Python 3 installed — nothing else.

---

## Step 1: Get everything into one pile

Export from Google Takeout (it'll come as separate group folders). Export from your phone too. (on android Fossify Contacts can export everything from every account into one file)

You should end up with a handful of `.vcf` files sitting in one folder.

## Step 2: Check what you've got

```
python3 vcf_report.py current.vcf
```

Tells you how many contacts, how many have categories, how many have photos, how many look empty or broken.

## Step 3: Strip the photos out before any big edit

Only needed if you are using an offline LLM model to help merge and verify contacts. (DO NOT FEED AN LLM API YOUR CONTACTS)

```
python3 strip_photos.py current.vcf stripped.vcf photos.json
```

Open the script if you want to see what it's doing before you run it — it's just a text file. `stripped.vcf` is your same contacts with no photos. `photos.json` is where the photos went, so they can come back later.

## Step 4: Edit the stripped file

Wherever your actual merging happens — by hand, by a script, by a model like OpenCode — point it at `stripped.vcf`, not the original. It's small and text-only now, easy on memory.

## Step 5: Put the photos back

```
python3 reattach_photos.py edited.vcf photos.json merged.vcf
```

Tells you how many photos went back in, and calls out anyone it couldn't match a photo to.

## Step 6: Check what changed

```
python3 vcf_report.py current.vcf merged.vcf
```

Before-and-after: what got added, what got removed, what categories changed, what photos changed. If a number looks wrong, stop here and figure out why before going further.

## Step 7: See the duplicates up close (optional)

```
python3 vcf_find_duplicates.py merged.vcf
```

Line numbers for every duplicate copy, plus exactly which fields differ between them. Good to run before the walkthrough, just to see the size of the problem.

## Step 8: Go through the duplicates, one group at a time

```
python3 vcf_duplicate_walkthrough.py merged.vcf cleaned.vcf
```

Shows you each duplicate group in full, then asks what to do:

| Type this | What it does |
|---|---|
| `m` | Merge every copy still unresolved in this group |
| `m 2,3` | Merge only copies 2 and 3, leave the rest alone |
| `d 2` | Delete just copy 2, leave everyone else untouched |
| `k 1,3` | Keep only copies 1 and 3, delete anything else |
| `s` | Leave whatever's left as separate contacts, move on |
| `q` | Stop here, save what's decided, leave the rest untouched |

You can mix these within one group — merge two, leave two alone, before moving to the next.

## Step 9: One last check

```
python3 vcf_report.py merged.vcf cleaned.vcf
```

Confirms the walkthrough did what you meant it to.

---

## The whole thing, back to back

```
python3 vcf_report.py current.vcf
python3 strip_photos.py current.vcf stripped.vcf photos.json
# ... edit stripped.vcf however you're editing it ...
python3 reattach_photos.py edited.vcf photos.json merged.vcf
python3 vcf_report.py current.vcf merged.vcf
python3 vcf_find_duplicates.py merged.vcf
python3 vcf_duplicate_walkthrough.py merged.vcf cleaned.vcf
python3 vcf_report.py merged.vcf cleaned.vcf
```

Check the report after every step. If something looks off, stop and fix. Nothing here is destructive, so there's no rush.