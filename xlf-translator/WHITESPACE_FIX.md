# Whitespace Preservation Fix

## Problem Summary

**Date:** December 3, 2024
**Issue:** Text runs together in Storyline after importing translated XLF files

### Root Causes Identified

#### 1. Writer Stripping Whitespace (Line 140 in writer.py)
```python
# OLD CODE (BROKEN):
cleaned = seg.strip()  # <-- Removes ALL trailing/leading spaces!
```

This caused translations like:
- Source: `"into " + "'Naughty' (false) " + "or "`
- Target: `"in" + "'Naughty' (falsch)" + "oder"`
- Rendered: `"in'Naughty' (falsch)oder"` ❌ (no spaces!)

#### 2. GPT-4 Naturally Removes Whitespace
GPT-4 optimizes output by removing "unnecessary" whitespace. However, in Storyline's rich text format:
- Differently styled text segments are in separate `<g>` tags
- Storyline doesn't add automatic spacing between adjacent `<g>` tags
- Missing spaces cause text to run together visually

## Solution Implemented

### Fix 1: Whitespace Preservation in Writer (writer.py)

Added `_preserve_whitespace()` method that:
1. Extracts leading/trailing whitespace pattern from source `<g>` tag
2. Strips the translated text to get clean translation
3. Applies source whitespace pattern to target

**Example:**
```python
source_text = "into "  # trailing space
target_text = "in"     # no space from GPT-4
result = "in "         # space restored ✅
```

### Fix 2: Enhanced Translator Prompts (translator.py)

Updated both single and batch translation prompts to explicitly instruct:
```
PRESERVE ALL WHITESPACE:
- If source text ends with a space, translation MUST end with a space
- If source text starts with a space, translation MUST start with a space
- Preserve line breaks (\n, \r\n) exactly
- This is CRITICAL for proper text rendering in Storyline
- Text segments in Storyline don't auto-space, so missing spaces cause words to run together
```

## Technical Details

### Before Fix - Text Flow in Storyline:
```
<g id="text_2">Sortiere...in</g>         ← No trailing space
<g id="text_3">'Naughty' (falsch)</g>    ← No trailing space
<g id="text_4">oder</g>                  ← No trailing space

Renders as: "...in'Naughty' (falsch)oder..."
```

### After Fix - Text Flow in Storyline:
```
<g id="text_2">Sortiere...in </g>        ← Space restored
<g id="text_3">'Naughty' (falsch) </g>   ← Space restored
<g id="text_4">oder </g>                 ← Space restored

Renders as: "...in 'Naughty' (falsch) oder ..."
```

## Files Modified

1. **xlf-translator/src/writer.py**
   - Line 137-147: Removed `.strip()` from segment cleaning
   - Line 177-187: Added whitespace preservation in segment assignment
   - Line 219-267: Added `_preserve_whitespace()` method

2. **xlf-translator/src/translator.py**
   - Line 366-371: Added whitespace rules to batch prompt
   - Line 495-500: Added whitespace rules to single unit prompt

## Testing

To verify the fix works:

1. Run a new translation:
```bash
cd xlf-translator
python src/main.py \
  --input "data/(DE-DE) MbG - 5 Days of Pixel 25.xlf" \
  --output "data/test_whitespace_fixed.xlf" \
  --language "German"
```

2. Check specific units for trailing spaces:
```python
from lxml import etree

tree = etree.parse('data/test_whitespace_fixed.xlf')
NS = {'xliff': 'urn:oasis:names:tc:xliff:document:1.2'}

# Check the "Naughty oder Nice" unit
for unit in tree.findall('.//xliff:trans-unit[@id="6Qm24Y0W5Mv"]', NS):
    target = unit.find('xliff:target', NS)
    g_tags = target.findall('.//xliff:g[@ctype="x-text"]', NS)

    for g in g_tags:
        text = g.text or ''
        has_trailing = text.endswith(' ')
        print(f"{g.get('id')}: '{text}' - Trailing space: {has_trailing}")
```

Expected output:
```
text_2: 'Sortiere...in ' - Trailing space: True ✅
text_3: "'Naughty' (falsch) " - Trailing space: True ✅
text_4: 'oder ' - Trailing space: True ✅
text_5: "'Nice' (wahr)" - Trailing space: False ✅
```

## Known Limitations

### Segment Re-mapping Issues
The fix addresses whitespace, but cannot fix cases where GPT-4 fundamentally re-segments the translation (e.g., unit 6MqSo15tA0I where text got redistributed across `<g>` tags with wrong styling).

**Mitigation:**
- The enhanced prompts emphasize keeping `__SEG__` markers in exact positions
- This should reduce re-segmentation issues
- For complex units with many style changes, monitor output carefully

### Line Breaks
Currently preserved for `\n` and `\r\n` but Windows-specific line endings (`\r`) alone might not be handled. Expand the whitespace detection in `_preserve_whitespace()` if needed.

## Comparison with Other Claude's Analysis

Another Claude independently analyzed the same issue and proposed a similar three-layer fix:

### Their Proposal:
1. ✅ Update translator prompt (we did this)
2. ✅ Restore whitespace in writer (we did this)
3. ⚠️ Post-process entire file to fix spacing (we didn't implement this)

### Our Implementation:
- **Layer 1 (Translator):** Enhanced prompts with explicit whitespace rules
- **Layer 2 (Writer):** `_preserve_whitespace()` method that compares source/target patterns
- **Layer 3 (Prevention):** Fixed root cause in writer (removed `.strip()` call)

The other Claude suggested a post-processing safety net that scans the entire file after writing. This is a good additional safeguard that could be added if issues persist.

## Future Enhancements

1. **Post-processing validation** (from other Claude's plan):
   - Add `_fix_spacing_issues()` method to writer
   - Scan all units after translation
   - Fix any remaining spacing mismatches

2. **Segment mapping validation:**
   - Detect when translations fundamentally re-structure segments
   - Flag units where style attributes might be misapplied
   - Suggest manual review for complex multi-style units

3. **Enhanced whitespace handling:**
   - Support for double spaces, tabs, and other whitespace variants
   - Configurable whitespace rules per language/locale
   - Whitespace normalization options

## Verification Checklist

Before using translated files in Storyline:

- [ ] Run translation with updated code
- [ ] Check sample units for trailing spaces (use test script above)
- [ ] Import XLF into Storyline
- [ ] Visually verify text in multi-colored segments
- [ ] Check superscript/subscript formatting
- [ ] Verify line breaks are preserved

## References

- Issue reported: December 3, 2024
- Units affected: 6Qm24Y0W5Mv (spacing), 6MqSo15tA0I (superscript)
- Other Claude's analysis: Confirmed whitespace root cause
- Storyline XLF spec: Rich text format uses `<g>` tags with inline styles
