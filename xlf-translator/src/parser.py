"""
XLF Parser for Articulate Storyline Translation Files

Handles XLF 1.2 format with two main trans-unit types:
1. datatype="plaintext" - Simple text strings (scene names, buttons, etc.)
2. datatype="x-DocumentState" - Complex styled content with inline tags

Key features:
- Extracts translatable text while preserving tag structure
- Handles multi-<g> segments that form single sentences
- Preserves whitespace (xml:space="preserve")
- Validates tag pairing (bpt/ept matching)
"""

from lxml import etree
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import re


@dataclass
class TransUnit:
    """Represents a single translation unit from XLF"""
    id: str
    datatype: str
    source_element: etree._Element  # Keep reference to original element
    translatable_text: str
    has_inline_tags: bool
    xml_space_preserve: bool
    tag_map: Dict[str, etree._Element]  # Placeholder -> original tag element
    g_segments: List[Dict]  # For x-DocumentState: list of <g> tag info


class XLFParser:
    """Parser for XLF 1.2 translation files"""
    
    # Namespace for XLF 1.2
    NS = {'xliff': 'urn:oasis:names:tc:xliff:document:1.2'}
    
    def __init__(self, xlf_path: str):
        """
        Initialize parser with XLF file path
        
        Args:
            xlf_path: Path to the XLF file
        """
        self.xlf_path = xlf_path
        self.tree = None
        self.root = None
        self._load_file()
    
    def _load_file(self):
        """Load and parse the XLF file"""
        try:
            parser = etree.XMLParser(remove_blank_text=False, strip_cdata=False)
            self.tree = etree.parse(self.xlf_path, parser)
            self.root = self.tree.getroot()
        except etree.XMLSyntaxError as e:
            raise ValueError(f"Invalid XML in XLF file: {e}")
        except FileNotFoundError:
            raise FileNotFoundError(f"XLF file not found: {self.xlf_path}")
    
    def get_source_language(self) -> str:
        """Extract source language from file element"""
        file_elem = self.root.find('.//xliff:file', self.NS)
        if file_elem is not None:
            return file_elem.get('source-language', 'unknown')
        return 'unknown'
    
    def get_target_language(self) -> Optional[str]:
        """Extract target language if specified"""
        file_elem = self.root.find('.//xliff:file', self.NS)
        if file_elem is not None:
            return file_elem.get('target-language')
        return None
    
    def parse_all_units(self) -> List[TransUnit]:
        """
        Parse all trans-units from the XLF file
        
        Returns:
            List of TransUnit objects ready for translation
        """
        trans_units = self.root.findall('.//xliff:trans-unit', self.NS)
        parsed_units = []
        
        for unit in trans_units:
            try:
                parsed = self._parse_trans_unit(unit)
                if parsed:
                    parsed_units.append(parsed)
            except Exception as e:
                unit_id = unit.get('id', 'unknown')
                print(f"Warning: Failed to parse trans-unit {unit_id}: {e}")
        
        return parsed_units
    
    def _parse_trans_unit(self, unit: etree._Element) -> Optional[TransUnit]:
        """
        Parse a single trans-unit element
        
        Args:
            unit: The <trans-unit> XML element
            
        Returns:
            TransUnit object or None if no translatable content
        """
        unit_id = unit.get('id')
        datatype = unit.get('datatype', 'plaintext')
        xml_space = unit.get('{http://www.w3.org/XML/1998/namespace}space')
        preserve_space = xml_space == 'preserve'
        
        # Find the source element
        source = unit.find('xliff:source', self.NS)
        if source is None:
            return None
        
        # Route to appropriate parser based on datatype
        if datatype == 'plaintext':
            return self._parse_plaintext_unit(unit_id, source, preserve_space)
        elif datatype == 'x-DocumentState':
            return self._parse_document_state_unit(unit_id, source, preserve_space)
        else:
            # Fallback: treat as plaintext
            return self._parse_plaintext_unit(unit_id, source, preserve_space)
    
    def _parse_plaintext_unit(self, unit_id: str, source: etree._Element, 
                              preserve_space: bool) -> TransUnit:
        """
        Parse a simple plaintext trans-unit
        
        These have no inline tags, just plain text content
        """
        text = source.text or ''
        
        return TransUnit(
            id=unit_id,
            datatype='plaintext',
            source_element=source,
            translatable_text=text.strip() if not preserve_space else text,
            has_inline_tags=False,
            xml_space_preserve=preserve_space,
            tag_map={},
            g_segments=[]
        )
    
    def _parse_document_state_unit(self, unit_id: str, source: etree._Element,
                                   preserve_space: bool) -> TransUnit:
        """
        Parse a complex x-DocumentState trans-unit
        
        These contain inline formatting tags. Only <g ctype="x-text"> elements
        contain translatable content. We need to:
        1. Extract all <g ctype="x-text"> segments
        2. Merge them into a single translatable string
        3. Keep track of boundaries for splitting after translation
        """
        # Find all <g> tags with translatable content
        g_tags = source.findall('.//xliff:g[@ctype="x-text"]', self.NS)
        
        if not g_tags:
            # No translatable content
            return TransUnit(
                id=unit_id,
                datatype='x-DocumentState',
                source_element=source,
                translatable_text='',
                has_inline_tags=True,
                xml_space_preserve=preserve_space,
                tag_map={},
                g_segments=[]
            )
        
        # Extract text and metadata from each <g> segment
        g_segments = []
        text_parts = []
        
        for idx, g_tag in enumerate(g_tags):
            text = g_tag.text or ''
            
            # Handle &#xD; (carriage return) and other XML entities
            if preserve_space:
                # Keep whitespace as-is
                clean_text = text
            else:
                # Normalize whitespace but preserve intentional breaks
                clean_text = re.sub(r'\s+', ' ', text).strip()
            
            g_segments.append({
                'index': idx,
                'element': g_tag,
                'original_text': text,
                'char_count': len(clean_text)
            })
            
            text_parts.append(clean_text)
        
        # Merge all text segments with a separator
        # Use a special marker to track segment boundaries
        merged_text = ' __SEG__ '.join(text_parts)
        
        return TransUnit(
            id=unit_id,
            datatype='x-DocumentState',
            source_element=source,
            translatable_text=merged_text,
            has_inline_tags=True,
            xml_space_preserve=preserve_space,
            tag_map={},
            g_segments=g_segments
        )
    
    def validate_tag_pairing(self, source: etree._Element) -> Tuple[bool, str]:
        """
        Validate that all <bpt> and <ept> tags are properly paired
        
        Returns:
            (is_valid, error_message)
        """
        bpt_tags = source.findall('.//xliff:bpt', self.NS)
        ept_tags = source.findall('.//xliff:ept', self.NS)
        
        bpt_ids = {tag.get('id') for tag in bpt_tags}
        ept_ids = {tag.get('id') for tag in ept_tags}
        
        if bpt_ids != ept_ids:
            missing_epts = bpt_ids - ept_ids
            missing_bpts = ept_ids - bpt_ids
            error_parts = []
            if missing_epts:
                error_parts.append(f"Missing <ept> for: {missing_epts}")
            if missing_bpts:
                error_parts.append(f"Missing <bpt> for: {missing_bpts}")
            return False, '; '.join(error_parts)
        
        return True, ""
    
    def get_statistics(self) -> Dict:
        """
        Get statistics about the XLF file
        
        Returns:
            Dictionary with counts and metadata
        """
        units = self.parse_all_units()
        
        plaintext_count = sum(1 for u in units if u.datatype == 'plaintext')
        styled_count = sum(1 for u in units if u.datatype == 'x-DocumentState')
        
        total_chars = sum(len(u.translatable_text) for u in units)
        avg_chars = total_chars / len(units) if units else 0
        
        return {
            'total_units': len(units),
            'plaintext_units': plaintext_count,
            'styled_units': styled_count,
            'total_characters': total_chars,
            'avg_characters_per_unit': round(avg_chars, 2),
            'source_language': self.get_source_language(),
            'target_language': self.get_target_language() or 'not specified'
        }


def main():
    """Example usage and testing"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python parser.py <xlf_file>")
        sys.exit(1)
    
    xlf_file = sys.argv[1]
    
    # Parse the file
    parser = XLFParser(xlf_file)
    
    # Show statistics
    stats = parser.get_statistics()
    print("\n=== XLF File Statistics ===")
    for key, value in stats.items():
        print(f"{key}: {value}")
    
    # Parse all units
    units = parser.parse_all_units()
    
    # Show first 5 units as examples
    print("\n=== Sample Translation Units ===")
    for unit in units[:5]:
        print(f"\nID: {unit.id}")
        print(f"Type: {unit.datatype}")
        print(f"Has inline tags: {unit.has_inline_tags}")
        print(f"Preserve space: {unit.xml_space_preserve}")
        print(f"Text: {unit.translatable_text[:100]}..." if len(unit.translatable_text) > 100 
              else f"Text: {unit.translatable_text}")
        if unit.g_segments:
            print(f"Number of <g> segments: {len(unit.g_segments)}")
        print("-" * 50)
    
    # Validation example
    print("\n=== Validation Check ===")
    all_valid = True
    for unit in units:
        if unit.has_inline_tags:
            is_valid, error = parser.validate_tag_pairing(unit.source_element)
            if not is_valid:
                print(f"⚠️  Unit {unit.id}: {error}")
                all_valid = False
    
    if all_valid:
        print("✅ All tags properly paired!")


if __name__ == '__main__':
    main()