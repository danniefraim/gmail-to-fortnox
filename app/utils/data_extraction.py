import re
import html
from bs4 import BeautifulSoup
import decimal
from typing import Dict, Any, Optional, Union, List

class DataExtractor:
    """
    Extracts data from email content using regex patterns.
    Handles both HTML and plain text content.
    """
    
    def __init__(self):
        """Initialize the data extractor"""
        # Configure decimal context for rounding
        decimal.getcontext().rounding = decimal.ROUND_HALF_UP
    
    def strip_html(self, html_content: str) -> str:
        """
        Strip HTML tags and convert entities to create plain text.
        
        Args:
            html_content: HTML content as string
            
        Returns:
            Plain text without HTML tags
        """
        if not html_content:
            return ""
        
        try:
            # Use BeautifulSoup to parse and extract text from HTML
            soup = BeautifulSoup(html_content, 'html.parser')
            # Get text and normalize whitespace
            text = soup.get_text(separator=' ', strip=True)
            # Replace multiple spaces with a single space
            text = re.sub(r'\s+', ' ', text)
            return text
        except Exception as e:
            print(f"Error stripping HTML: {str(e)}")
            # Fallback: use simple regex-based HTML tag removal
            text = re.sub(r'<[^>]+>', ' ', html_content)
            text = html.unescape(text)  # Handle HTML entities
            text = re.sub(r'\s+', ' ', text)  # Normalize whitespace
            return text.strip()
    
    def extract_value(self, pattern: str, text: str) -> Optional[str]:
        """
        Extract a value from text using a regex pattern.
        The pattern should include a capture group for the value to extract.
        
        Args:
            pattern: Regex pattern with a capture group
            text: Text to search in
            
        Returns:
            Extracted value or None if not found
        """
        if not text or not pattern:
            return None
            
        match = re.search(pattern, text)
        if match and match.group(1):
            return match.group(1).strip()
        return None
    
    def normalize_decimal(self, value_str: Optional[str]) -> Optional[decimal.Decimal]:
        """
        Convert a string representation of a number to a Decimal.
        Handles different formats (comma/period as decimal separator).
        
        Args:
            value_str: String representation of a number
            
        Returns:
            Decimal object or None if conversion fails
        """
        if not value_str:
            return None
            
        try:
            # Replace comma with period if it's used as decimal separator
            normalized = value_str.replace(',', '.')
            # Remove any non-numeric characters except the decimal point
            normalized = re.sub(r'[^\d.]', '', normalized)
            # Convert to Decimal
            return decimal.Decimal(normalized)
        except (decimal.InvalidOperation, ValueError):
            print(f"Error converting '{value_str}' to decimal")
            return None
    
    def extract_data(self, email_content: Dict[str, Any], 
                    extraction_rules: Dict[str, Dict[str, Any]]) -> Dict[str, decimal.Decimal]:
        """
        Extract data from email content using the provided extraction rules.
        
        Args:
            email_content: Email content with body_text and body_html
            extraction_rules: Dictionary of data extraction rules
            
        Returns:
            Dictionary of extracted values as Decimal objects
        """
        results = {}
        
        # Get both text and HTML content
        body_text = email_content.get('body_text', '')
        body_html = email_content.get('body_html', '')
        
        # Strip HTML to create an additional text version
        stripped_html = self.strip_html(body_html) if body_html else ""
        
        # Process each extraction rule
        for var_name, rule in extraction_rules.items():
            value = None
            
            # Try HTML pattern if specified
            if 'html_pattern' in rule and body_html:
                value = self.extract_value(rule['html_pattern'], body_html)
            
            # Try text pattern on body_text if value not found yet
            if not value and 'pattern' in rule and body_text:
                value = self.extract_value(rule['pattern'], body_text)
            
            # Try text pattern on stripped HTML if value not found yet
            if not value and 'pattern' in rule and stripped_html:
                value = self.extract_value(rule['pattern'], stripped_html)
            
            # Convert to Decimal
            decimal_value = None
            if value:
                decimal_value = self.normalize_decimal(value)
            
            # Use default if specified and no value found or conversion failed
            if not decimal_value and 'default' in rule:
                if isinstance(rule['default'], (int, float, str)):
                    decimal_value = decimal.Decimal(str(rule['default']))
                else:
                    print(f"Invalid default value for {var_name}: {rule['default']}")
            
            # Round to 2 decimal places if we have a value
            if decimal_value is not None:
                decimal_value = decimal_value.quantize(decimal.Decimal('0.01'))
                results[var_name] = decimal_value
        
        return results 