"""
XLF Writer Module

Handles writing translated content back to XLF files while preserving:
- XML structure and formatting
- Inline tags (bpt, ept, ph, it, g, etc.)
- Namespace declarations
- Attributes and metadata

Works in conjunction with XLFParser to maintain file integrity.
"""

from lxml import etree
from typing import Optional
from .parser import XLFParser, TransUnit


class XLFWriter:
    """Writes translated content back to XLF format"""

    def __init__(self, parser: XLFParser):
        """
        Initialize writer with a parsed XLF file

        Args:
            parser: XLFParser instance with loaded file
        """
        self.parser = parser
        self.tree = parser.tree
        self.root = parser.root
        self.NS = parser.NS
        self.modified_count = 0

    def update_translation(self, unit: TransUnit, translated_text: str):
        """
        Update a translation unit with translated text

        Args:
            unit: TransUnit object from parser
            translated_text: The translated text to insert
        """
        # Find or create target element
        source_elem = unit.source_element
        trans_unit_elem = source_elem.getparent()

        # Check if target element exists
        target_elem = trans_unit_elem.find('xliff:target', self.NS)

        if target_elem is None:
            # Create new target element
            target_elem = etree.Element('{%s}target' % self.NS['xliff'])
            # Insert after source
            source_index = list(trans_unit_elem).index(source_elem)
            trans_unit_elem.insert(source_index + 1, target_elem)

        # Update based on unit type
        if unit.datatype == 'plaintext':
            self._write_plaintext(target_elem, translated_text, unit)
        elif unit.datatype == 'x-DocumentState':
            self._write_document_state(target_elem, translated_text, unit)

        self.modified_count += 1

    def _write_plaintext(self, target_elem: etree._Element,
                        translated_text: str,
                        unit: TransUnit):
        """
        Write plaintext translation

        Args:
            target_elem: The <target> element to write to
            translated_text: Translated text
            unit: Original TransUnit
        """
        # Clear existing content
        target_elem.clear()

        # Copy attributes from source if needed
        if unit.xml_space_preserve:
            target_elem.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')

        # Set the text
        target_elem.text = translated_text

    def _write_document_state(self, target_elem: etree._Element,
                              translated_text: str,
                              unit: TransUnit):
        """
        Write x-DocumentState translation with inline tags

        Handles:
        - Extra __SEG__ markers from GPT-4
        - Markers at string boundaries
        - Empty segments
        - Mismatched segment counts
        - Whitespace preservation from source

        Args:
            target_elem: The <target> element to write to
            translated_text: Translated text (may contain __SEG__ markers)
            unit: Original TransUnit with g_segments info
        """
        # Clear existing content
        target_elem.clear()

        # Copy xml:space attribute if needed
        if unit.xml_space_preserve:
            target_elem.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')

        # Copy the entire structure from source
        source_elem = unit.source_element

        # Deep copy all children from source to target
        for child in source_elem:
            target_elem.append(self._deep_copy_element(child))

        # Copy text and tail
        target_elem.text = source_elem.text
        target_elem.tail = source_elem.tail

        # Now update the translatable content in <g> tags
        if unit.g_segments:
            # Get source g tags to know how many segments we SHOULD have
            source_g_tags = source_elem.findall('.//xliff:g[@ctype="x-text"]', self.NS)
            expected_segments = len(source_g_tags)

            # ROBUST SPLITTING LOGIC
            # Step 1: Split by __SEG__ (with or without spaces)
            # Handle both ' __SEG__ ' and '__SEG__'
            raw_segments = translated_text.split(' __SEG__ ')
            if len(raw_segments) == 1:
                # Try without spaces
                raw_segments = translated_text.split('__SEG__')

            # Step 2: Clean each segment
            # - Remove any remaining __SEG__ markers (in case they're in the middle)
            # - DO NOT strip whitespace yet - we'll preserve it from source later
            cleaned_segments = []
            for seg in raw_segments:
                # Remove __SEG__ markers but preserve whitespace for now
                cleaned = seg.replace('__SEG__', '')
                # Only filter out completely empty segments
                if cleaned or cleaned == '':  # Keep even whitespace-only segments
                    cleaned_segments.append(cleaned)

            # Remove truly empty segments (but keep whitespace-only ones)
            cleaned_segments = [s for s in cleaned_segments if s is not None]

            # Step 3: Handle segment count mismatch
            if len(cleaned_segments) != expected_segments:
                print(f"      ⚠️  Unit {unit.id}: Segment count mismatch")
                print(f"         Expected: {expected_segments} (from source <g> tags)")
                print(f"         Got: {len(cleaned_segments)} (after splitting/cleaning)")
                print(f"         Raw split gave: {len(raw_segments)} segments")

                # STRATEGY: Try to match segments intelligently
                if len(cleaned_segments) < expected_segments:
                    # Too few segments - pad with empty strings
                    while len(cleaned_segments) < expected_segments:
                        cleaned_segments.append('')
                    print(f"         → Padded to {expected_segments} segments")

                elif len(cleaned_segments) > expected_segments:
                    # Too many segments - need to merge some
                    print(f"         → Merging extra segments")

                    # Simple strategy: merge extra segments into the last one
                    merged_segments = cleaned_segments[:expected_segments-1]
                    merged_segments.append(' '.join(cleaned_segments[expected_segments-1:]))
                    cleaned_segments = merged_segments

                    print(f"         → Result: {len(cleaned_segments)} segments")

            # Step 4: Update <g> tag text content with whitespace preservation
            target_g_tags = target_elem.findall('.//xliff:g[@ctype="x-text"]', self.NS)

            for source_g, target_g, segment_text in zip(source_g_tags, target_g_tags, cleaned_segments):
                # Remove any remaining __SEG__ markers
                segment_text = segment_text.replace('__SEG__', '')

                # CRITICAL: Preserve whitespace patterns from source
                final_text = self._preserve_whitespace(
                    source_text=source_g.text or '',
                    target_text=segment_text
                )

                target_g.text = final_text
        else:
            # No g_segments, just copy structure
            pass

    def _deep_copy_element(self, elem: etree._Element) -> etree._Element:
        """
        Deep copy an XML element with all attributes and children

        Args:
            elem: Element to copy

        Returns:
            Copied element
        """
        # Create new element with same tag
        new_elem = etree.Element(elem.tag)

        # Copy attributes
        for key, value in elem.attrib.items():
            new_elem.set(key, value)

        # Copy text and tail
        new_elem.text = elem.text
        new_elem.tail = elem.tail

        # Recursively copy children
        for child in elem:
            new_elem.append(self._deep_copy_element(child))

        return new_elem

    def _preserve_whitespace(self, source_text: str, target_text: str) -> str:
        """
        Preserve leading and trailing whitespace from source in target text

        This is CRITICAL for Storyline XLF files because:
        - Differently styled segments are in separate <g> tags
        - Storyline doesn't add spacing between adjacent <g> tags
        - Missing spaces cause text to run together visually

        Example:
            Source: "into " (trailing space)
            Target: "in" (no space)
            Result: "in " (space restored)

        Args:
            source_text: Original text with correct whitespace pattern
            target_text: Translated text (may be missing whitespace)

        Returns:
            Target text with source whitespace pattern applied
        """
        if not source_text:
            return target_text

        # Strip target to get clean translated text
        clean_target = target_text.strip()

        # Analyze source whitespace pattern
        leading_ws = ''
        trailing_ws = ''

        # Extract leading whitespace
        for char in source_text:
            if char in (' ', '\t', '\n', '\r'):
                leading_ws += char
            else:
                break

        # Extract trailing whitespace
        for char in reversed(source_text):
            if char in (' ', '\t', '\n', '\r'):
                trailing_ws = char + trailing_ws
            else:
                break

        # Apply whitespace pattern to target
        result = leading_ws + clean_target + trailing_ws

        return result

    def _final_cleanup(self, output_path: str) -> int:
        """
        Final safety pass: Remove ANY remaining __SEG__ markers

        This is the SAFETY NET that catches anything the writer missed.

        Args:
            output_path: Path to the output XLF file

        Returns:
            Number of markers removed
        """
        tree = etree.parse(output_path)
        removed_count = 0

        for unit in tree.findall('.//xliff:trans-unit', self.NS):
            target = unit.find('xliff:target', self.NS)

            if target is None:
                continue

            # Check every <g> tag
            g_tags = target.findall('.//xliff:g[@ctype="x-text"]', self.NS)

            for g_tag in g_tags:
                if g_tag.text and '__SEG__' in g_tag.text:
                    original = g_tag.text
                    cleaned = g_tag.text.replace('__SEG__', '').strip()
                    g_tag.text = cleaned
                    removed_count += 1

                    print(f"      🧹 Cleaned {unit.get('id')}, <g id='{g_tag.get('id')}'>:")
                    print(f"         Before: '{original[:50]}...'")
                    print(f"         After:  '{cleaned[:50]}...'")

        if removed_count > 0:
            # Save the cleaned file
            tree.write(output_path, encoding='utf-8', xml_declaration=True, pretty_print=True)

        return removed_count

    def save(self, output_path: str, pretty_print: bool = True):
        """
        Save the modified XLF file

        Args:
            output_path: Path to save the file to
            pretty_print: Whether to format with indentation
        """
        # Write to file
        self.tree.write(
            output_path,
            encoding='utf-8',
            xml_declaration=True,
            pretty_print=pretty_print
        )

        # Run final cleanup pass
        print(f"\n🧹 Running final cleanup pass...")
        removed = self._final_cleanup(output_path)

        if removed > 0:
            print(f"⚠️  Final cleanup removed {removed} remaining __SEG__ marker(s)")
            print(f"✅ File has been cleaned and re-saved")
        else:
            print(f"✅ No cleanup needed - file is clean")

    def get_statistics(self):
        """Get statistics about modifications"""
        return {
            'modified_units': self.modified_count
        }

    def validate_output(self, output_path: str) -> dict:
        """
        Validate the output XLF file for common issues

        CRITICAL: This checks that NO __SEG__ markers remain!

        Args:
            output_path: Path to the output XLF file

        Returns:
            Dict with validation results and issues found
        """
        from lxml import etree

        tree = etree.parse(output_path)
        NS = {'xliff': 'urn:oasis:names:tc:xliff:document:1.2'}

        issues = {
            'seg_markers': [],      # CRITICAL: Should be empty!
            'empty_targets': [],
            'tag_mismatches': [],
            'missing_targets': []
        }

        # Check all trans-units
        for unit in tree.findall('.//xliff:trans-unit', NS):
            unit_id = unit.get('id')
            source = unit.find('xliff:source', NS)
            target = unit.find('xliff:target', NS)

            # Check for missing target
            if target is None:
                issues['missing_targets'].append(unit_id)
                continue

            # CRITICAL CHECK: Look for __SEG__ markers in individual <g> tags
            g_tags = target.findall('.//xliff:g[@ctype="x-text"]', NS)

            for g_tag in g_tags:
                if g_tag.text and '__SEG__' in g_tag.text:
                    issues['seg_markers'].append({
                        'unit_id': unit_id,
                        'g_id': g_tag.get('id'),
                        'text': g_tag.text,
                        'marker_count': g_tag.text.count('__SEG__')
                    })

            # Get all text from target for empty check
            target_text = ''.join(target.itertext())

            # Check for empty targets
            if not target_text.strip():
                issues['empty_targets'].append(unit_id)

            # Check tag structure matches source
            if source is not None:
                source_g_count = len(source.findall('.//xliff:g[@ctype="x-text"]', NS))
                target_g_count = len(target.findall('.//xliff:g[@ctype="x-text"]', NS))

                if source_g_count != target_g_count and source_g_count > 0:
                    issues['tag_mismatches'].append({
                        'unit_id': unit_id,
                        'source_tags': source_g_count,
                        'target_tags': target_g_count
                    })

        # Calculate total markers
        total_seg_markers = sum(item['marker_count'] for item in issues['seg_markers'])

        # Calculate validity
        is_valid = (
            len(issues['seg_markers']) == 0 and  # NO __SEG__ markers!
            len(issues['tag_mismatches']) < 5      # Some mismatches are OK
        )

        return {
            'is_valid': is_valid,
            'issues': issues,
            'total_seg_markers': total_seg_markers,
            'affected_g_tags': len(issues['seg_markers']),
            'total_issues': sum(len(v) if isinstance(v, list) else 0 for v in issues.values())
        }


def main():
    """Example usage"""
    import sys
    from parser import XLFParser

    if len(sys.argv) < 2:
        print("Usage: python writer.py <xlf_file>")
        sys.exit(1)

    xlf_file = sys.argv[1]

    # Parse the file
    print("Parsing file...")
    parser = XLFParser(xlf_file)
    units = parser.parse_all_units()

    # Create writer
    writer = XLFWriter(parser)

    # Example: Update first unit with mock translation
    if units:
        print(f"\nUpdating unit: {units[0].id}")
        print(f"Original: {units[0].translatable_text}")

        # Mock translation (in real use, this would come from translator)
        mock_translation = f"[TRANSLATED] {units[0].translatable_text}"
        writer.update_translation(units[0], mock_translation)

        # Save to new file
        output_path = xlf_file.replace('.xlf', '_test_output.xlf')
        writer.save(output_path)

        print(f"\n Saved to: {output_path}")
        print(f"Modified units: {writer.modified_count}")


if __name__ == '__main__':
    main()
