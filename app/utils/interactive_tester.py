import re
import json
import os
from typing import Dict, Any, Optional, List, Tuple
from .data_extraction import DataExtractor
from .formula_evaluator import FormulaEvaluator

class InteractiveTester:
    """
    Interactive tool for testing regex patterns against email content
    and creating/modifying rules.
    """
    
    def __init__(self, email_content: Dict[str, Any]):
        """
        Initialize the interactive tester with email content.
        
        Args:
            email_content: Dictionary containing email content (body_text, body_html)
        """
        self.email_content = email_content
        self.data_extractor = DataExtractor()
        self.formula_evaluator = FormulaEvaluator()
        
        # Create a plain text version of HTML content for easier testing
        if email_content.get('body_html'):
            self.plain_html = self.data_extractor.strip_html(email_content['body_html'])
        else:
            self.plain_html = ""
    
    def test_pattern(self, pattern: str, use_html: bool = False) -> List[str]:
        """
        Test a regex pattern against email content.
        
        Args:
            pattern: Regex pattern to test
            use_html: Whether to use HTML content (True) or plain text content (False)
            
        Returns:
            List of matches found
        """
        try:
            content = None
            if use_html:
                content = self.email_content.get('body_html', '')
            else:
                # Try body_text first, then fall back to stripped HTML
                content = self.email_content.get('body_text', '')
                if not content:
                    content = self.plain_html
            
            if not content:
                return []
                
            # Use findall to get all matches
            matches = re.findall(pattern, content)
            
            # Handle tuple results (multiple capture groups)
            result = []
            for match in matches:
                if isinstance(match, tuple):
                    # Get the first capture group
                    result.append(match[0])
                else:
                    result.append(match)
            
            return result
            
        except Exception as e:
            print(f"Error testing pattern: {str(e)}")
            return []
    
    def preview_extraction(self, extraction_rules: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Preview data extraction using the provided rules.
        
        Args:
            extraction_rules: Dictionary of extraction rules
            
        Returns:
            Dictionary of extracted values
        """
        try:
            extracted_data = self.data_extractor.extract_data(
                self.email_content, extraction_rules
            )
            return extracted_data
        except Exception as e:
            print(f"Error previewing extraction: {str(e)}")
            return {}
    
    def preview_voucher(self, 
                       rule: Dict[str, Any], 
                       extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Preview voucher entries using the provided rule and extracted data.
        
        Args:
            rule: Rule containing accounting entries
            extracted_data: Dictionary of extracted values
            
        Returns:
            Dictionary with calculated voucher entries
        """
        try:
            accounting = rule.get('accounting', {})
            entries = accounting.get('entries', [])
            
            # Calculate voucher entries
            calculated_entries = self.formula_evaluator.calculate_voucher_entries(
                entries, extracted_data
            )
            
            # Calculate totals
            total_debit = sum(entry['debit'] for entry in calculated_entries)
            total_credit = sum(entry['credit'] for entry in calculated_entries)
            
            return {
                'description': accounting.get('description', ''),
                'series': accounting.get('series', ''),
                'entries': calculated_entries,
                'total_debit': total_debit,
                'total_credit': total_credit,
                'balanced': total_debit == total_credit
            }
        except Exception as e:
            print(f"Error previewing voucher: {str(e)}")
            return {}
    
    def show_email_preview(self, max_length: int = 500) -> None:
        """
        Show a preview of the email content for pattern testing.
        
        Args:
            max_length: Maximum length of content to show
        """
        print("\n=== EMAIL PREVIEW ===")
        print(f"Subject: {self.email_content.get('subject', '')}")
        print(f"From: {self.email_content.get('sender', '')}")
        print("\n--- PLAIN TEXT ---")
        text = self.email_content.get('body_text', '')
        if text:
            if len(text) > max_length:
                print(f"{text[:max_length]}...(truncated)")
            else:
                print(text)
        else:
            print("(No plain text content)")
            
        print("\n--- STRIPPED HTML ---")
        if self.plain_html:
            if len(self.plain_html) > max_length:
                print(f"{self.plain_html[:max_length]}...(truncated)")
            else:
                print(self.plain_html)
        else:
            print("(No HTML content)")
            
    def run_interactive_session(self, rule: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Run an interactive session to create or modify a rule.
        
        Args:
            rule: Existing rule to modify (or None to create a new one)
            
        Returns:
            New or modified rule
        """
        print("\n=== INTERACTIVE RULE CREATOR ===")
        
        # Initialize rule if not provided
        if rule is None:
            rule = {
                'sender': '',
                'subject': '',
                'body_contains': '',
                'data_extraction': {},
                'accounting': {
                    'description': '',
                    'series': '',
                    'entries': []
                }
            }
        
        # Show email preview
        self.show_email_preview()
        
        # Basic rule attributes
        print("\n=== BASIC RULE ATTRIBUTES ===")
        rule['sender'] = input(f"Sender (current: '{rule.get('sender', '')}'): ") or rule.get('sender', '')
        rule['subject'] = input(f"Subject (current: '{rule.get('subject', '')}'): ") or rule.get('subject', '')
        
        # Body contains
        current_body = rule.get('body_contains', '')
        if isinstance(current_body, list):
            current_body = ', '.join(current_body)
        body_contains = input(f"Body contains (comma-separated, current: '{current_body}'): ") or current_body
        if ',' in body_contains:
            rule['body_contains'] = [item.strip() for item in body_contains.split(',')]
        else:
            rule['body_contains'] = body_contains.strip()
        
        # Initialize data extraction if not present
        if 'data_extraction' not in rule:
            rule['data_extraction'] = {}
        
        # Data extraction patterns
        print("\n=== DATA EXTRACTION ===")
        
        done = False
        while not done:
            print("\nCurrent extraction variables:")
            if rule['data_extraction']:
                for var_name, var_rule in rule['data_extraction'].items():
                    pattern = var_rule.get('pattern', '')
                    default = var_rule.get('default', '')
                    print(f"  {var_name}: pattern='{pattern}', default={default}")
            else:
                print("  (None)")
                
            action = input("\nAdd/Modify variable (a), Test pattern (t), Delete variable (d), Continue (c): ").lower()
            
            if action == 'a':
                # Add or modify variable
                var_name = input("Variable name: ")
                if not var_name:
                    continue
                    
                # Initialize variable if not exists
                if var_name not in rule['data_extraction']:
                    rule['data_extraction'][var_name] = {}
                
                # Get pattern
                pattern = input(f"Pattern (with capturing group): ")
                if pattern:
                    rule['data_extraction'][var_name]['pattern'] = pattern
                
                # Test pattern
                if pattern:
                    text_matches = self.test_pattern(pattern, use_html=False)
                    if text_matches:
                        print(f"Matches in text content: {text_matches}")
                    else:
                        print("No matches found in text content.")
                        
                        # Try stripped HTML
                        if self.plain_html:
                            stripped_matches = self.test_pattern(pattern, use_html=True)
                            if stripped_matches:
                                print(f"Matches in HTML content: {stripped_matches}")
                            else:
                                print("No matches found in HTML content either.")
                
                # Get default value
                default_str = input(f"Default value (current: '{rule['data_extraction'][var_name].get('default', '')}'): ")
                if default_str:
                    try:
                        default_value = float(default_str)
                        rule['data_extraction'][var_name]['default'] = default_value
                    except ValueError:
                        print("Invalid numeric value. Using as string.")
                        rule['data_extraction'][var_name]['default'] = default_str
                
            elif action == 't':
                # Test pattern
                pattern = input("Test pattern (with capturing group): ")
                if pattern:
                    print("\nTesting against text content:")
                    text_matches = self.test_pattern(pattern, use_html=False)
                    if text_matches:
                        print(f"Matches: {text_matches}")
                    else:
                        print("No matches found.")
                        
                    print("\nTesting against HTML content:")
                    html_matches = self.test_pattern(pattern, use_html=True)
                    if html_matches:
                        print(f"Matches: {html_matches}")
                    else:
                        print("No matches found.")
            
            elif action == 'd':
                # Delete variable
                var_name = input("Variable name to delete: ")
                if var_name in rule['data_extraction']:
                    del rule['data_extraction'][var_name]
                    print(f"Deleted variable '{var_name}'")
            
            elif action == 'c':
                done = True
        
        # Preview extraction
        if rule['data_extraction']:
            print("\n=== EXTRACTION PREVIEW ===")
            extracted_data = self.preview_extraction(rule['data_extraction'])
            for var_name, value in extracted_data.items():
                print(f"  {var_name} = {value}")
        
        # Accounting entries
        print("\n=== ACCOUNTING ENTRIES ===")
        
        # Initialize accounting if not present
        if 'accounting' not in rule:
            rule['accounting'] = {
                'description': '',
                'series': '',
                'entries': []
            }
        
        # Description and series
        rule['accounting']['description'] = input(f"Description (current: '{rule['accounting'].get('description', '')}'): ") or rule['accounting'].get('description', '')
        rule['accounting']['series'] = input(f"Voucher series (current: '{rule['accounting'].get('series', '')}'): ") or rule['accounting'].get('series', '')
        
        # Entries
        entries = rule['accounting'].get('entries', [])
        
        print("\nCurrent entries:")
        if entries:
            for i, entry in enumerate(entries):
                print(f"  {i+1}. Account: {entry['account']}, Debit: {entry.get('debit', 0)}, Credit: {entry.get('credit', 0)}")
        else:
            print("  (None)")
        
        done = False
        while not done:
            action = input("\nAdd entry (a), Modify entry (m), Delete entry (d), Continue (c): ").lower()
            
            if action == 'a':
                # Add entry
                account = input("Account number: ")
                if not account:
                    continue
                
                debit_str = input("Debit (number or formula): ")
                credit_str = input("Credit (number or formula): ")
                
                entry = {'account': account}
                
                # Handle debit value
                if debit_str:
                    try:
                        # Try to convert to float first
                        debit_value = float(debit_str)
                        entry['debit'] = debit_value
                    except ValueError:
                        # If not a number, treat as formula
                        entry['debit'] = debit_str
                else:
                    entry['debit'] = 0
                
                # Handle credit value
                if credit_str:
                    try:
                        # Try to convert to float first
                        credit_value = float(credit_str)
                        entry['credit'] = credit_value
                    except ValueError:
                        # If not a number, treat as formula
                        entry['credit'] = credit_str
                else:
                    entry['credit'] = 0
                
                entries.append(entry)
            
            elif action == 'm':
                # Modify entry
                index_str = input("Entry number to modify: ")
                try:
                    index = int(index_str) - 1
                    if 0 <= index < len(entries):
                        entry = entries[index]
                        
                        account = input(f"Account number (current: '{entry['account']}'): ")
                        if account:
                            entry['account'] = account
                        
                        debit_str = input(f"Debit (current: '{entry.get('debit', 0)}'): ")
                        if debit_str:
                            try:
                                debit_value = float(debit_str)
                                entry['debit'] = debit_value
                            except ValueError:
                                entry['debit'] = debit_str
                        
                        credit_str = input(f"Credit (current: '{entry.get('credit', 0)}'): ")
                        if credit_str:
                            try:
                                credit_value = float(credit_str)
                                entry['credit'] = credit_value
                            except ValueError:
                                entry['credit'] = credit_str
                    else:
                        print(f"Invalid entry number. Must be between 1 and {len(entries)}.")
                except ValueError:
                    print("Invalid entry number.")
            
            elif action == 'd':
                # Delete entry
                index_str = input("Entry number to delete: ")
                try:
                    index = int(index_str) - 1
                    if 0 <= index < len(entries):
                        del entries[index]
                        print(f"Deleted entry {index+1}")
                    else:
                        print(f"Invalid entry number. Must be between 1 and {len(entries)}.")
                except ValueError:
                    print("Invalid entry number.")
            
            elif action == 'c':
                done = True
        
        # Update entries in rule
        rule['accounting']['entries'] = entries
        
        # Preview voucher
        if rule['data_extraction'] and entries:
            print("\n=== VOUCHER PREVIEW ===")
            extracted_data = self.preview_extraction(rule['data_extraction'])
            voucher_preview = self.preview_voucher(rule, extracted_data)
            
            print(f"Description: {voucher_preview.get('description', '')}")
            print(f"Series: {voucher_preview.get('series', '')}")
            print("\nEntries:")
            for entry in voucher_preview.get('entries', []):
                print(f"  Account: {entry['account']}, Debit: {entry['debit']}, Credit: {entry['credit']}")
                
            print(f"\nTotal Debit: {voucher_preview.get('total_debit', 0)}")
            print(f"Total Credit: {voucher_preview.get('total_credit', 0)}")
            
            if voucher_preview.get('balanced', False):
                print("\nVoucher is BALANCED ✓")
            else:
                print("\nWARNING: Voucher is NOT BALANCED ✗")
        
        return rule
        
    def save_rule(self, rule: Dict[str, Any], filename: str) -> None:
        """
        Save a rule to a file.
        
        Args:
            rule: Rule to save
            filename: Filename to save to
        """
        try:
            with open(filename, 'w') as f:
                json.dump(rule, f, indent=2)
            print(f"Rule saved to {filename}")
        except Exception as e:
            print(f"Error saving rule: {str(e)}") 