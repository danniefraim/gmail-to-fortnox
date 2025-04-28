import os
import sys
import datetime
from pathlib import Path

class CLI:
    def __init__(self):
        """Initialize the CLI interface"""
        pass
    
    def print_header(self, text):
        """Print a header with formatting"""
        print("\n" + "=" * 60)
        print(f" {text}")
        print("=" * 60)
    
    def print_section(self, text):
        """Print a section header with formatting"""
        print("\n" + "-" * 40)
        print(f" {text}")
        print("-" * 40)
    
    def print_success(self, message):
        """Print a success message"""
        print(f"\n✅ {message}")
    
    def print_error(self, message):
        """Print an error message"""
        print(f"\n❌ {message}")
    
    def print_info(self, message):
        """Print an info message"""
        print(f"\nℹ️ {message}")
    
    def print_warning(self, message):
        """Print a warning message"""
        print(f"⚠️ {message}")
    
    def confirm(self, message, default=True):
        """Ask for user confirmation
        
        Args:
            message (str): Message to display
            default (bool): Default response if user just presses Enter
            
        Returns:
            str: 'y' (yes), 'n' (no), or 'i' (ignore) 
        """
        if default:
            options = "[Y/n/i] "
            default_option = 'y'
        else:
            options = "[y/N/i] "
            default_option = 'n'
        
        while True:
            choice = input(f"{message} {options}").lower() or default_option
            
            if choice in ('y', 'yes'):
                return 'y'
            elif choice in ('n', 'no'):
                return 'n'
            elif choice in ('i', 'ignore'):
                return 'i'
            else:
                print("Please respond with 'y', 'n', or 'i'.")
    
    def print_email_summary(self, email):
        """Print a summary of an email"""
        self.print_section(f"Email from {email.get('sender', 'Unknown')}")
        print(f"Subject: {email.get('subject', 'No Subject')}")
        print(f"Date: {email.get('date', datetime.datetime.now()).strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Print a snippet of the body
        body = email.get('body_text', '') or email.get('body_html', '')
        if body:
            snippet = body[:150] + "..." if len(body) > 150 else body
            print(f"\nSnippet: {snippet}")
    
    def print_verification_summary(self, rule, pdf_path):
        """Print a summary of a verification to be created"""
        self.print_section(f"Verification: {rule['accounting']['description']}")
        print(f"Series: {rule['accounting']['series']}")
        print(f"Date: {datetime.datetime.now().strftime('%Y-%m-%d')}")
        print(f"Attachment: {pdf_path}")
        
        # Print entries
        print("\nEntries:")
        for entry in rule['accounting']['entries']:
            account = entry['account']
            debit = entry.get('debit', 0)
            credit = entry.get('credit', 0)
            
            # Handle both numeric values and string formulas
            debit_display = f"{float(debit):.2f}" if isinstance(debit, (int, float)) else debit
            credit_display = f"{float(credit):.2f}" if isinstance(credit, (int, float)) else credit
            
            # Only show non-zero values or formula strings
            if debit and debit != 0:
                print(f"  {account} debit: {debit_display} SEK")
            if credit and credit != 0:
                print(f"  {account} credit: {credit_display} SEK")
        
        try:
            # Try to calculate totals, but only if values are numeric
            total_debit = sum(float(entry['debit']) for entry in rule['accounting']['entries'] 
                             if isinstance(entry.get('debit'), (int, float)))
            total_credit = sum(float(entry['credit']) for entry in rule['accounting']['entries'] 
                              if isinstance(entry.get('credit'), (int, float)))
            
            # Only show totals if we could calculate them
            if total_debit > 0 or total_credit > 0:
                print(f"\nTotal: {total_debit:.2f} SEK = {total_credit:.2f} SEK")
            else:
                print("\nNote: Entries contain formulas - actual values will be calculated at processing time")
        except (ValueError, TypeError):
            # If we can't calculate totals (e.g., due to formula strings), show a note
            print("\nNote: Entries contain formulas - actual values will be calculated at processing time")
    
    def show_menu(self, options):
        """Show a menu with options and get user selection
        
        Args:
            options (list): List of option strings
            
        Returns:
            int: The selected option index (0-based)
        """
        self.print_section("Menu")
        
        for i, option in enumerate(options, 1):
            print(f"{i}. {option}")
        
        while True:
            try:
                choice = int(input("\nEnter your choice (number): "))
                if 1 <= choice <= len(options):
                    return choice - 1
                else:
                    print(f"Please enter a number between 1 and {len(options)}")
            except ValueError:
                print("Please enter a valid number")
    
    def get_input(self, prompt, default=None):
        """Get user input with a prompt
        
        Args:
            prompt (str): The prompt to display
            default (str, optional): Default value if user just presses Enter
            
        Returns:
            str: User input or default value
        """
        default_text = f" [{default}]" if default is not None else ""
        response = input(f"{prompt}{default_text}: ").strip()
        
        if not response and default is not None:
            return default
        
        return response 