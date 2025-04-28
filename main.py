#!/usr/bin/env python3
"""
Gmail to Fortnox Integration - Command Line Runner

This script is the main entry point for the Gmail to Fortnox Integration application.
It properly handles command line arguments and routes them to the appropriate functions.
"""

import sys
import argparse
from app.config.config import load_config, get_processed_emails, get_ignored_emails
from app.main import main, print_rules, show_processed_emails, create_rule_interactive

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Gmail to Fortnox Integration')
    parser.add_argument('--show-rules', action='store_true', help='Show the email rules and exit')
    parser.add_argument('--show-emails', action='store_true', help='Show processed and ignored emails with Gmail URLs')
    parser.add_argument('--debug', action='store_true', help='Enable additional debug output')
    parser.add_argument('--dry-run', action='store_true', help='Run without making actual requests to Fortnox')
    parser.add_argument('--ignore-processed', action='store_true', help='Ignore previously processed emails (for testing)')
    parser.add_argument('--create-rule', action='store_true', help='Interactively create or modify a rule')
    parser.add_argument('--email-id', type=str, help='Gmail message ID to use for rule creation')
    parser.add_argument('--rule-file', type=str, help='File to load/save rule from/to')
    
    args = parser.parse_args()
    
    # Load configuration first (needed for all modes)
    try:
        config = load_config()
    except Exception as e:
        print(f"Failed to load configuration: {str(e)}")
        sys.exit(1)
    
    # If show-rules is specified, just show the rules and exit
    if args.show_rules:
        print_rules(config)
        sys.exit(0)
    
    # If show-emails is specified, show the processed emails and exit
    if args.show_emails:
        processed_emails = get_processed_emails()
        ignored_emails = get_ignored_emails()
        show_processed_emails(processed_emails, ignored_emails)
        sys.exit(0)
    
    # If create-rule is specified, run the interactive rule creator
    if args.create_rule:
        create_rule_interactive(
            config=config,
            email_id=args.email_id,
            rule_file=args.rule_file,
            debug=args.debug
        )
        sys.exit(0)
    
    # Otherwise run the main program
    main(args.debug, args.dry_run, args.ignore_processed)
