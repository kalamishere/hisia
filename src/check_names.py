#!/usr/bin/env python3
"""Fail if any fictional artist/title shares a distinctive word with a real chart artist/title."""
import json, re, sys
lib = json.load(open(sys.argv[1] if len(sys.argv) > 1 else 'library.json'))
# argv[2]: the week's manifest (radio/refresh passes the new week-stamped one);
# default stays the 2026-08-24 fixtures dir so publish.sh keeps working unchanged.
man = json.load(open(sys.argv[2] if len(sys.argv) > 2 else
                     '/Users/kalam/ableton-v1-wt-continuous/marathon/fixtures/regional-previews/manifest.json'))
STOP = {'feat', 'remix', 'live', 'with', 'the', 'and', 'love', 'you', 'song', 'music', 'version', 'from',
        'banda', 'grupo', 'los', 'las', 'club', 'band', 'boys', 'girls'}  # generic genre/ensemble words, not identities
words = {w.lower() for r in man.values() for t in r for s in (t['artist'], t['title']) for w in re.findall(r"[A-Za-z']{4,}", s)} - STOP
bad = []
for t in lib['tracks']:
    hits = [w for w in re.findall(r"[A-Za-z']{4,}", t['artist'] + ' ' + t['title']) if w.lower() in words]
    if hits:
        bad.append((t['id'], t['artist'], t['title'], hits))
for b in bad: print('REAL-NAME OVERLAP', b)
print('checked', len(lib['tracks']), 'tracks;', len(bad), 'overlaps')
sys.exit(1 if bad else 0)
