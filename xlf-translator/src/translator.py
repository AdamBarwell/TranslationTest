"""
XLF Translator Module

Sends translatable text to OpenAI API with proper handling of:
- __SEG__ marker preservation for multi-segment units
- Brand names and special terms
- Batch translation for efficiency
- Retry logic for failed translations
"""

import os
from typing import List, Dict, Optional
from dataclasses import dataclass
import time

try:
    from openai import OpenAI
except ImportError:
    print("Warning: openai package not installed. Run: pip install openai")
    OpenAI = None


@dataclass
class TranslationResult:
    """Result of a translation operation"""
    success: bool
    translated_text: str
    original_text: str
    unit_id: str
    error_message: Optional[str] = None
    retry_count: int = 0


class XLFTranslator:
    """Translator for XLF content using OpenAI API"""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o"):
        """
        Initialize translator with API key
        
        Args:
            api_key: OpenAI API key (or set OPENAI_API_KEY env var)
            model: OpenAI model to use (default: gpt-4o)
        """
        if OpenAI is None:
            raise ImportError("openai package required. Install with: pip install openai")
        
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("API key required. Set OPENAI_API_KEY or pass api_key parameter")
        
        self.client = OpenAI(api_key=self.api_key)
        self.model = model
        self.stats = {
            'total_translations': 0,
            'successful': 0,
            'failed': 0,
            'retries': 0
        }
    
    def translate_unit(self, 
                      text: str, 
                      unit_id: str,
                      target_language: str,
                      has_seg_markers: bool = False,
                      preserve_terms: Optional[List[str]] = None,
                      max_retries: int = 2) -> TranslationResult:
        """
        Translate a single unit
        
        Args:
            text: Text to translate
            unit_id: Unit ID for tracking
            target_language: Target language code or name (e.g., 'es', 'Spanish', 'fr')
            has_seg_markers: Whether text contains __SEG__ markers
            preserve_terms: List of terms to not translate (e.g., brand names)
            max_retries: Maximum retry attempts
            
        Returns:
            TranslationResult object
        """
        if not text or not text.strip():
            return TranslationResult(
                success=True,
                translated_text=text,
                original_text=text,
                unit_id=unit_id,
                error_message="Empty text, skipped translation"
            )
        
        retry_count = 0
        last_error = None
        
        while retry_count <= max_retries:
            try:
                # Build the prompt
                prompt = self._build_prompt(
                    text=text,
                    target_language=target_language,
                    has_seg_markers=has_seg_markers,
                    preserve_terms=preserve_terms
                )
                
                # Call OpenAI API
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are a professional translator specializing in UI and e-learning content. You follow instructions precisely and preserve all formatting markers."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,  # Lower temperature for more consistent translations
                    max_tokens=2000
                )
                
                translated_text = response.choices[0].message.content.strip()
                
                # Validate the translation
                is_valid, error = self._validate_translation(
                    original=text,
                    translated=translated_text,
                    has_seg_markers=has_seg_markers
                )
                
                if is_valid:
                    self.stats['total_translations'] += 1
                    self.stats['successful'] += 1
                    if retry_count > 0:
                        self.stats['retries'] += retry_count
                    
                    return TranslationResult(
                        success=True,
                        translated_text=translated_text,
                        original_text=text,
                        unit_id=unit_id,
                        retry_count=retry_count
                    )
                else:
                    # Validation failed, retry with stricter prompt
                    last_error = f"Validation failed: {error}"
                    retry_count += 1
                    if retry_count <= max_retries:
                        print(f"⚠️  Retry {retry_count}/{max_retries} for unit {unit_id}: {error}")
                        time.sleep(1)  # Brief delay before retry
                    
            except Exception as e:
                last_error = str(e)
                retry_count += 1
                if retry_count <= max_retries:
                    print(f"⚠️  API error, retry {retry_count}/{max_retries} for unit {unit_id}: {e}")
                    time.sleep(2)  # Longer delay for API errors
        
        # All retries exhausted
        self.stats['total_translations'] += 1
        self.stats['failed'] += 1
        
        return TranslationResult(
            success=False,
            translated_text=text,  # Return original as fallback
            original_text=text,
            unit_id=unit_id,
            error_message=f"Translation failed after {max_retries} retries: {last_error}",
            retry_count=retry_count
        )
    
    def translate_batch(self,
                       units: List[Dict],
                       target_language: str,
                       preserve_terms: Optional[List[str]] = None) -> List[TranslationResult]:
        """
        Translate multiple units
        
        Args:
            units: List of dicts with keys: 'text', 'id', 'has_seg_markers'
            target_language: Target language
            preserve_terms: Terms to preserve across all units
            
        Returns:
            List of TranslationResult objects
        """
        results = []
        
        for i, unit in enumerate(units):
            print(f"Translating {i+1}/{len(units)}: {unit['id']}")
            
            result = self.translate_unit(
                text=unit['text'],
                unit_id=unit['id'],
                target_language=target_language,
                has_seg_markers=unit.get('has_seg_markers', False),
                preserve_terms=preserve_terms
            )
            
            results.append(result)
            
            # Brief pause to avoid rate limits (adjust as needed)
            if i < len(units) - 1:
                time.sleep(0.5)
        
        return results
    
    def _build_prompt(self,
                     text: str,
                     target_language: str,
                     has_seg_markers: bool,
                     preserve_terms: Optional[List[str]]) -> str:
        """Build the translation prompt"""
        
        prompt_parts = [
            f"Translate the following text from English to {target_language}.",
            "",
            "CRITICAL RULES:"
        ]
        
        if has_seg_markers:
            prompt_parts.extend([
                "1. The text contains __SEG__ markers. These are STRUCTURAL MARKERS.",
                "   - You MUST preserve EVERY __SEG__ marker EXACTLY as-is",
                "   - Do NOT translate, modify, move, or remove __SEG__ markers",
                "   - Keep __SEG__ in the EXACT SAME POSITIONS in the translation",
                ""
            ])
        
        if preserve_terms:
            terms_str = ", ".join(f'"{term}"' for term in preserve_terms)
            prompt_parts.extend([
                f"2. Do NOT translate these brand/product names: {terms_str}",
                "   - Keep them exactly as written in the source text",
                ""
            ])
        
        prompt_parts.extend([
            "3. Preserve the tone and style:",
            "   - This is UI text for an interactive learning module",
            "   - Keep it natural, friendly, and engaging",
            "   - Maintain any formatting like line breaks",
            "",
            "4. OUTPUT FORMAT:",
            "   - Provide ONLY the translated text",
            "   - No explanations, no notes, no markdown formatting",
            "   - Just the pure translation",
            "",
            "TEXT TO TRANSLATE:",
            text
        ])
        
        return "\n".join(prompt_parts)
    
    def _validate_translation(self,
                            original: str,
                            translated: str,
                            has_seg_markers: bool) -> tuple[bool, str]:
        """
        Validate the translation output
        
        Returns:
            (is_valid, error_message)
        """
        # Check if translation is suspiciously similar (might be untranslated)
        if original == translated and len(original) > 10:
            return False, "Translation appears identical to source"
        
        # Validate __SEG__ marker preservation
        if has_seg_markers:
            original_count = original.count('__SEG__')
            translated_count = translated.count('__SEG__')
            
            if original_count != translated_count:
                return False, f"__SEG__ marker count mismatch: expected {original_count}, got {translated_count}"
        
        # Check for common API errors
        if "I cannot" in translated or "I apologize" in translated:
            return False, "Translation contains refusal language"
        
        return True, ""
    
    def get_statistics(self) -> Dict:
        """Get translation statistics"""
        return {
            **self.stats,
            'success_rate': round(self.stats['successful'] / self.stats['total_translations'] * 100, 2) 
                           if self.stats['total_translations'] > 0 else 0
        }


def main():
    """Example usage"""
    import sys
    
    # Check for API key
    if not os.getenv('OPENAI_API_KEY'):
        print("Error: OPENAI_API_KEY environment variable not set")
        print("Set it with: export OPENAI_API_KEY='your-key-here'")
        sys.exit(1)
    
    # Initialize translator
    translator = XLFTranslator()
    
    # Example: Translate a simple unit
    print("=== Example 1: Simple Translation ===")
    result = translator.translate_unit(
        text="5 Days of Pixel",
        unit_id="test1",
        target_language="Spanish",
        preserve_terms=["Pixel"]
    )
    print(f"Success: {result.success}")
    print(f"Original: {result.original_text}")
    print(f"Translated: {result.translated_text}")
    print()
    
    # Example: Translate unit with __SEG__ markers
    print("=== Example 2: Multi-Segment Translation ===")
    result = translator.translate_unit(
        text="The Pixelves have almost finished __SEG__ their yearly duties __SEG__ of delivering presents",
        unit_id="test2",
        target_language="Spanish",
        has_seg_markers=True,
        preserve_terms=["Pixelves"]
    )
    print(f"Success: {result.success}")
    print(f"Original: {result.original_text}")
    print(f"Translated: {result.translated_text}")
    print()
    
    # Show statistics
    print("=== Translation Statistics ===")
    stats = translator.get_statistics()
    for key, value in stats.items():
        print(f"{key}: {value}")


if __name__ == '__main__':
    main()