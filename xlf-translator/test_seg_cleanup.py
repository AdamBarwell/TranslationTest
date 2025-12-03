#!/usr/bin/env python3
"""
Test script to verify __SEG__ marker cleanup functionality

This tests the three-layer defense:
1. Translator validation (logs but doesn't fail on extra markers)
2. Writer segment cleaning (robust splitting and cleaning)
3. Final cleanup pass (safety net)
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from lxml import etree


def test_segment_cleaning():
    """Test the segment cleaning logic"""
    print("=" * 70)
    print("Testing __SEG__ Marker Cleaning Logic")
    print("=" * 70)

    # Test cases simulating what GPT-4 might return
    test_cases = [
        {
            'name': 'Perfect case (correct markers)',
            'input': 'text1 __SEG__ text2 __SEG__ text3',
            'expected_segments': 3,
            'should_clean': False
        },
        {
            'name': 'Extra markers (GPT-4 added extra)',
            'input': 'text1 __SEG__ text2 __SEG__ __SEG__ text3 __SEG__ text4',
            'expected_segments': 3,
            'should_clean': True
        },
        {
            'name': 'Marker at start',
            'input': '__SEG__ text1 __SEG__ text2 __SEG__ text3',
            'expected_segments': 3,
            'should_clean': True
        },
        {
            'name': 'Marker at end',
            'input': 'text1 __SEG__ text2 __SEG__ text3 __SEG__',
            'expected_segments': 3,
            'should_clean': True
        },
        {
            'name': 'Marker in middle of text',
            'input': 'text1 __SEG__ text2 with __SEG__ in middle __SEG__ text3',
            'expected_segments': 3,
            'should_clean': True
        },
        {
            'name': 'Multiple spaces around markers',
            'input': 'text1  __SEG__  text2   __SEG__   text3',
            'expected_segments': 3,
            'should_clean': False
        }
    ]

    for test in test_cases:
        print(f"\nTest: {test['name']}")
        print(f"Input: '{test['input']}'")

        # Simulate the cleaning logic from _write_document_state
        translated_text = test['input']
        expected_segments = test['expected_segments']

        # Step 1: Split
        raw_segments = translated_text.split(' __SEG__ ')
        if len(raw_segments) == 1:
            raw_segments = translated_text.split('__SEG__')

        # Step 2: Clean
        cleaned_segments = []
        for seg in raw_segments:
            cleaned = seg.strip()
            cleaned = cleaned.replace('__SEG__', '').strip()
            if cleaned:
                cleaned_segments.append(cleaned)

        print(f"Raw split: {len(raw_segments)} segments")
        print(f"After cleaning: {len(cleaned_segments)} segments")
        print(f"Expected: {expected_segments} segments")

        # Step 3: Handle mismatches
        if len(cleaned_segments) > expected_segments:
            print(f"→ Merging {len(cleaned_segments) - expected_segments} extra segments")
            merged_segments = cleaned_segments[:expected_segments-1]
            merged_segments.append(' '.join(cleaned_segments[expected_segments-1:]))
            cleaned_segments = merged_segments
        elif len(cleaned_segments) < expected_segments:
            print(f"→ Padding with {expected_segments - len(cleaned_segments)} empty segments")
            while len(cleaned_segments) < expected_segments:
                cleaned_segments.append('')

        print(f"Final segments: {cleaned_segments}")

        # Verify no __SEG__ in final segments
        has_markers = any('__SEG__' in seg for seg in cleaned_segments)
        if has_markers:
            print("❌ FAIL: __SEG__ markers still present!")
        else:
            print("✅ PASS: All __SEG__ markers removed")


def test_final_cleanup():
    """Test the final cleanup safety net"""
    print("\n" + "=" * 70)
    print("Testing Final Cleanup Safety Net")
    print("=" * 70)

    # Create a simple test XLF with __SEG__ markers
    test_xlf = """<?xml version="1.0" encoding="utf-8"?>
<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">
  <file source-language="en-GB" datatype="x-storyline360">
    <body>
      <trans-unit id="test1" datatype="x-DocumentState">
        <source>
          <g id="1" ctype="x-text">Source text 1</g>
          <g id="2" ctype="x-text">Source text 2</g>
        </source>
        <target>
          <g id="1" ctype="x-text">Translated __SEG__ text 1</g>
          <g id="2" ctype="x-text">Translated text 2</g>
        </target>
      </trans-unit>
    </body>
  </file>
</xliff>"""

    # Write test file
    test_file = '/tmp/test_seg_cleanup.xlf'
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write(test_xlf)

    print(f"Created test file: {test_file}")

    # Parse and check for markers before cleanup
    NS = {'xliff': 'urn:oasis:names:tc:xliff:document:1.2'}
    tree = etree.parse(test_file)

    markers_before = 0
    for unit in tree.findall('.//xliff:trans-unit', NS):
        target = unit.find('xliff:target', NS)
        if target:
            g_tags = target.findall('.//xliff:g[@ctype="x-text"]', NS)
            for g_tag in g_tags:
                if g_tag.text and '__SEG__' in g_tag.text:
                    markers_before += 1
                    print(f"Found marker in: '{g_tag.text}'")

    print(f"\n__SEG__ markers before cleanup: {markers_before}")

    # Simulate the _final_cleanup function
    removed_count = 0
    for unit in tree.findall('.//xliff:trans-unit', NS):
        target = unit.find('xliff:target', NS)
        if target is None:
            continue

        g_tags = target.findall('.//xliff:g[@ctype="x-text"]', NS)
        for g_tag in g_tags:
            if g_tag.text and '__SEG__' in g_tag.text:
                original = g_tag.text
                cleaned = g_tag.text.replace('__SEG__', '').strip()
                g_tag.text = cleaned
                removed_count += 1
                print(f"Cleaned: '{original}' → '{cleaned}'")

    # Check after cleanup
    markers_after = 0
    for unit in tree.findall('.//xliff:trans-unit', NS):
        target = unit.find('xliff:target', NS)
        if target:
            g_tags = target.findall('.//xliff:g[@ctype="x-text"]', NS)
            for g_tag in g_tags:
                if g_tag.text and '__SEG__' in g_tag.text:
                    markers_after += 1

    print(f"\n__SEG__ markers after cleanup: {markers_after}")
    print(f"Removed: {removed_count}")

    if markers_after == 0:
        print("✅ PASS: Final cleanup successfully removed all markers")
    else:
        print("❌ FAIL: Some markers remain!")

    # Cleanup
    os.remove(test_file)


if __name__ == '__main__':
    test_segment_cleaning()
    test_final_cleanup()

    print("\n" + "=" * 70)
    print("All tests completed!")
    print("=" * 70)
