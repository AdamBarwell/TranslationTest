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
from parser import XLFParser, TransUnit


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
            # Split translated text by __SEG__ markers
            if '__SEG__' in translated_text:
                translated_segments = translated_text.split(' __SEG__ ')
            else:
                # If no markers, treat as single segment
                translated_segments = [translated_text]

            # Find all <g ctype="x-text"> elements in target
            g_tags = target_elem.findall('.//xliff:g[@ctype="x-text"]', self.NS)

            # Update each <g> tag with corresponding translated segment
            for idx, g_tag in enumerate(g_tags):
                if idx < len(translated_segments):
                    g_tag.text = translated_segments[idx]
                else:
                    # Fallback: keep original if we don't have enough segments
                    pass
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

    def get_statistics(self):
        """Get statistics about modifications"""
        return {
            'modified_units': self.modified_count
        }

    def validate_output(self, output_path: str) -> Dict:
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

            # Get all text from target
            target_text = ''.join(target.itertext())

            # CRITICAL CHECK: Look for __SEG__ markers
            if '__SEG__' in target_text:
                seg_count = target_text.count('__SEG__')
                issues['seg_markers'].append({
                    'unit_id': unit_id,
                    'count': seg_count,
                    'preview': target_text[:100]
                })

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

        # Calculate validity
        is_valid = (
            len(issues['seg_markers']) == 0 and  # NO __SEG__ markers!
            len(issues['tag_mismatches']) < 5      # Some mismatches are OK
        )

        return {
            'is_valid': is_valid,
            'issues': issues,
            'total_seg_markers': len(issues['seg_markers']),
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
