"""
XLF Translation Tool - Interactive CLI
Provides an interactive workflow for translating XLF files using OpenAI GPT-4o
"""

import os
import sys
from pathlib import Path
from typing import Optional, List

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from parser import XLFParser
from translator import XLFTranslator
from writer import XLFWriter


def clear_screen():
    """Clear the terminal screen"""
    os.system('clear' if os.name != 'nt' else 'cls')


def print_header(text: str):
    """Print a formatted header"""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70 + "\n")


def list_xlf_files(data_dir: str = "data") -> List[Path]:
    """
    List all XLF files in the data directory

    Args:
        data_dir: Path to data directory

    Returns:
        List of Path objects for XLF files
    """
    data_path = Path(data_dir)

    if not data_path.exists():
        print(f"L Error: Data directory '{data_dir}' not found!")
        return []

    xlf_files = list(data_path.glob("*.xlf"))

    if not xlf_files:
        print(f"L No XLF files found in '{data_dir}' directory!")
        return []

    return sorted(xlf_files)


def select_file(xlf_files: List[Path]) -> Optional[Path]:
    """
    Display files and let user select one

    Args:
        xlf_files: List of XLF file paths

    Returns:
        Selected file path or None if cancelled
    """
    print_header("Available XLF Files")

    for idx, file_path in enumerate(xlf_files, start=1):
        file_size = file_path.stat().st_size
        size_kb = file_size / 1024
        print(f"  {idx}. {file_path.name}")
        print(f"     Size: {size_kb:.2f} KB")
        print()

    while True:
        try:
            choice = input(f"Select a file (1-{len(xlf_files)}) or 'q' to quit: ").strip()

            if choice.lower() == 'q':
                return None

            file_idx = int(choice) - 1

            if 0 <= file_idx < len(xlf_files):
                return xlf_files[file_idx]
            else:
                print(f"L Invalid selection. Please enter a number between 1 and {len(xlf_files)}.")
        except ValueError:
            print("L Invalid input. Please enter a number or 'q' to quit.")
        except KeyboardInterrupt:
            print("\n\nL Cancelled by user.")
            return None


def parse_and_confirm(file_path: Path) -> Optional[XLFParser]:
    """
    Parse the XLF file and show statistics for confirmation

    Args:
        file_path: Path to XLF file

    Returns:
        XLFParser object if confirmed, None otherwise
    """
    print_header(f"Parsing: {file_path.name}")

    try:
        # Parse the file
        parser = XLFParser(str(file_path))

        # Get statistics
        stats = parser.get_statistics()
        units = parser.parse_all_units()

        # Display statistics
        print("=� File Statistics:")
        print(f"   • Total translation units: {stats['total_units']}")
        print(f"   • Plaintext units: {stats['plaintext_units']}")
        print(f"   • Styled units (with formatting): {stats['styled_units']}")
        print(f"   • Total characters: {stats['total_characters']:,}")
        print(f"   • Average characters per unit: {stats['avg_characters_per_unit']}")
        print(f"   • Source language: {stats['source_language']}")
        print(f"   • Target language: {stats['target_language']}")
        print()

        # Show sample units
        print("=� Sample Translation Units (first 3):")
        print("-" * 70)
        for unit in units[:3]:
            print(f"\n   ID: {unit.id}")
            print(f"   Type: {unit.datatype}")
            preview = unit.translatable_text[:80]
            if len(unit.translatable_text) > 80:
                preview += "..."
            print(f"   Text: {preview}")
        print("\n" + "-" * 70)

        # Validate tag pairing
        print("\n> Validating tag structure...")
        validation_errors = []
        for unit in units:
            if unit.has_inline_tags:
                is_valid, error = parser.validate_tag_pairing(unit.source_element)
                if not is_valid:
                    validation_errors.append(f"Unit {unit.id}: {error}")

        if validation_errors:
            print("�  Validation warnings:")
            for error in validation_errors[:5]:  # Show first 5 errors
                print(f"   • {error}")
            if len(validation_errors) > 5:
                print(f"   ... and {len(validation_errors) - 5} more")
        else:
            print(" All tags properly paired!")

        print(f"\n Successfully parsed {stats['total_units']} translation units!")

        return parser

    except Exception as e:
        print(f"L Error parsing file: {e}")
        return None


def confirm_translation() -> bool:
    """
    Ask user if they want to proceed with translation

    Returns:
        True if confirmed, False otherwise
    """
    print_header("Translation Confirmation")

    while True:
        choice = input("Do you want to translate this file? (yes/no): ").strip().lower()

        if choice in ['yes', 'y']:
            return True
        elif choice in ['no', 'n']:
            return False
        else:
            print("L Please enter 'yes' or 'no'.")



def get_target_language() -> str:
    """
    Ask user for target language

    Returns:
        Target language string
    """
    print_header("Target Language Selection")
    print("Source language: EN-UK (English - United Kingdom)")
    print()
    while True:
        lang = input("Enter target language (e.g., Spanish, French, de-DE, fr-FR): ").strip()
        if lang:
            print(f"\n✅ Target language set to: {lang}")
            return lang
        print("❌ Please enter a target language.")


def get_translation_parameters() -> tuple:
    """
    Get all translation parameters: terms to preserve and custom context

    Returns:
        Tuple of (preserve_terms, context)
    """
    print_header("Translation Parameters & Context")

    # Step 1: Terms to preserve
    print("STEP 1: Terms to Preserve")
    print("Enter any brand names, product names, or terms that should NOT be translated.")
    print("Examples: Pixel, MbG, Google, etc.")
    print()
    terms_input = input("Enter terms to preserve (comma-separated, or press Enter to skip): ").strip()

    preserve_terms = None
    if terms_input:
        preserve_terms = [term.strip() for term in terms_input.split(',')]
        preserve_terms = [term for term in preserve_terms if term]
        if preserve_terms:
            print(f"\nWill preserve: {', '.join(preserve_terms)}")
    else:
        print("\nNo terms to preserve")

    print("\n" + "-" * 70 + "\n")

    # Step 2: Custom context/rules
    print("STEP 2: Additional Context & Rules")
    print("Enter any additional context or rules for the translation.")
    print("This will be added to the GPT-4o prompt for better accuracy.")
    print()
    print("Examples:")
    print("  - 'This is a training module for healthcare professionals'")
    print("  - 'Use formal tone, avoid colloquialisms'")
    print("  - 'Target audience is enterprise customers'")
    print()
    print("Enter your context (or press Enter to skip):")
    print("-" * 70)

    lines = []
    print("(Type your context below. Enter an empty line when done)")

    while True:
        try:
            line = input()
            if line.strip() == "":
                break
            lines.append(line)
        except KeyboardInterrupt:
            print("\n")
            break

    context = "\n".join(lines).strip()

    if context:
        print(f"\nContext saved ({len(context)} characters)")
    else:
        print("\nNo additional context provided")

    return preserve_terms, context


def validate_translation_structure(parser: XLFParser, results: List, original_units: List) -> bool:
    """
    Validate that translated content maintains source file structure

    Args:
        parser: XLFParser instance
        results: List of TranslationResult objects
        original_units: List of original TransUnit objects

    Returns:
        True if validation passes, False otherwise
    """
    print_header("Validating Translation Structure")

    validation_passed = True
    issues = []

    # Check 1: Count matches
    successful_results = [r for r in results if r.success]
    if len(successful_results) != len(original_units):
        issues.append(f"Unit count mismatch: {len(successful_results)} translated vs {len(original_units)} original")
        validation_passed = False

    # Check 2: Validate each translation
    result_map = {r.unit_id: r for r in results if r.success}

    for unit in original_units:
        if unit.id not in result_map:
            continue

        result = result_map[unit.id]
        original_text = unit.translatable_text
        translated_text = result.translated_text

        # Check __SEG__ markers preservation
        if '__SEG__' in original_text:
            original_seg_count = original_text.count('__SEG__')
            translated_seg_count = translated_text.count('__SEG__')

            if original_seg_count != translated_seg_count:
                issues.append(f"Unit {unit.id}: __SEG__ marker mismatch ({original_seg_count} -> {translated_seg_count})")
                validation_passed = False

        # Check for empty translations
        if not translated_text.strip() and original_text.strip():
            issues.append(f"Unit {unit.id}: Empty translation for non-empty source")
            validation_passed = False

        # Check length discrepancy (warn if translation is >300% or <20% of original)
        if len(original_text) > 10:  # Only check for non-trivial text
            ratio = len(translated_text) / len(original_text)
            if ratio > 3.0:
                issues.append(f"Unit {unit.id}: Translation suspiciously long ({ratio:.1f}x original)")
            elif ratio < 0.2:
                issues.append(f"Unit {unit.id}: Translation suspiciously short ({ratio:.1f}x original)")

    # Display results
    if validation_passed and not issues:
        print("All structure validations passed!")
        print(f"  - {len(successful_results)} units validated")
        print("  - All __SEG__ markers preserved")
        print("  - No structural issues detected")
    else:
        if not validation_passed:
            print("CRITICAL ISSUES DETECTED:")
        else:
            print("WARNINGS (not blocking):")

        for issue in issues[:10]:  # Show first 10 issues
            print(f"  - {issue}")

        if len(issues) > 10:
            print(f"  ... and {len(issues) - 10} more issues")

    print()
    return validation_passed


def perform_translation(parser: XLFParser,
                       file_path: Path,
                       target_language: str,
                       preserve_terms: Optional[List[str]],
                       context: str) -> bool:
    """
    Perform the actual translation

    Args:
        parser: XLFParser instance with parsed file
        file_path: Original file path
        target_language: Target language for translation (e.g., 'es', 'fr-FR', 'Spanish')
        preserve_terms: Terms to not translate
        context: Additional context for translation

    Returns:
        True if translation and save successful, False otherwise
    """
    print_header("Starting Translation")

    # Check for API key
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("L Error: OPENAI_API_KEY environment variable not set!")
        print()
        print("To set your API key:")
        print("  export OPENAI_API_KEY='your-key-here'")
        return False

    # Initialize translator
    print("=' Initializing translator (GPT-4o)...")
    try:
        translator = XLFTranslator(api_key=api_key, model="gpt-4o")
    except Exception as e:
        print(f"L Error initializing translator: {e}")
        return False

    # Parse units
    units = parser.parse_all_units()
    print(f"=� Found {len(units)} units to translate")
    print()

    # Prepare units for translation
    translation_units = []
    for unit in units:
        # Skip empty units
        if not unit.translatable_text.strip():
            continue

        translation_units.append({
            'text': unit.translatable_text,
            'id': unit.id,
            'has_seg_markers': '__SEG__' in unit.translatable_text,
            'unit_obj': unit  # Keep reference for writing later
        })

    print(f"> Translating {len(translation_units)} units...")
    print("-" * 70)

    # Translate with custom context if provided
    results = translator.translate_batch(
        units=translation_units,
        target_language=target_language,
        preserve_terms=preserve_terms,
        custom_context=context if context else None
    )

    # Show results
    print()
    print_header("Translation Results")

    stats = translator.get_statistics()
    print(f" Successful: {stats['successful']}")
    print(f"L Failed: {stats['failed']}")
    print(f"> Retries: {stats['retries']}")
    print(f"=� Success rate: {stats['success_rate']}%")

    # Show failed translations
    failed_results = [r for r in results if not r.success]
    if failed_results:
        print(f"\n�  Failed translations:")
        for result in failed_results[:5]:
            print(f"   • {result.unit_id}: {result.error_message}")
        if len(failed_results) > 5:
            print(f"   ... and {len(failed_results) - 5} more")

    # Validate translation structure
    print()
    validation_passed = validate_translation_structure(
        parser=parser,
        results=results,
        original_units=[unit_dict['unit_obj'] for unit_dict in translation_units]
    )

    if not validation_passed:
        print("WARNING: Validation detected critical issues!")
        print("You may still save the file, but review it carefully.")

    # Ask if user wants to save
    print()
    while True:
        save = input("Save translated file? (yes/no): ").strip().lower()
        if save in ['yes', 'y']:
            break
        elif save in ['no', 'n']:
            print("L Translation not saved.")
            return False
        else:
            print("L Please enter 'yes' or 'no'.")

    # Write output file
    output_path = file_path.parent / f"{file_path.stem}_translated.xlf"

    try:
        writer = XLFWriter(parser)

        # Map results back to units
        result_map = {r.unit_id: r for r in results}

        for unit_dict in translation_units:
            unit = unit_dict['unit_obj']
            result = result_map.get(unit.id)

            if result and result.success:
                writer.update_translation(unit, result.translated_text)

        writer.save(str(output_path))

        print(f"\n Translation saved to: {output_path}")
        print(f"=� File size: {output_path.stat().st_size / 1024:.2f} KB")

        return True
    except Exception as e:
        print(f"L Error saving file: {e}")
        return False


def main():
    """Main interactive workflow"""

    try:
        clear_screen()
        print_header("XLF Translation Tool")
        print("Welcome to the interactive XLF translator!")
        print("This tool uses OpenAI GPT-4o for high-quality translations.")

        # Step 1: List and select file
        xlf_files = list_xlf_files()
        if not xlf_files:
            return

        selected_file = select_file(xlf_files)
        if not selected_file:
            print("\n=K Goodbye!")
            return

        # Step 2: Get target language (source is always EN-UK)
        target_language = get_target_language()

        # Step 3: Parse and confirm
        parser = parse_and_confirm(selected_file)
        if not parser:
            print("\nL Failed to parse file. Exiting.")
            return

        # Step 4: Confirm translation
        if not confirm_translation():
            print("\n=K Translation cancelled. Goodbye!")
            return

        # Step 5: Get translation parameters (terms to preserve + context)
        preserve_terms, context = get_translation_parameters()

        # Step 6: Perform translation with validation
        perform_translation(
            parser=parser,
            file_path=selected_file,
            target_language=target_language,
            preserve_terms=preserve_terms,
            context=context
        )

        print("\n" + "=" * 70)
        print("  Translation Complete!")
        print("=" * 70)

    except KeyboardInterrupt:
        print("\n\nL Interrupted by user. Goodbye!")
    except Exception as e:
        print(f"\nL Unexpected error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
