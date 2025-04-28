#!/usr/bin/env python3
import os
import sys
import datetime
import http.server
import socketserver
import threading
import webbrowser
import urllib.parse
import time
import argparse
import json
from pathlib import Path

# Add the parent directory to the path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config.config import load_config, get_processed_emails, save_processed_email, get_ignored_emails, save_ignored_email, save_config
from app.gmail.gmail_service import GmailService
from app.pdf.pdf_converter import PdfConverter
from app.accounting.client_factory import AccountingClientFactory
from app.utils.cli import CLI
from app.utils.data_extraction import DataExtractor
from app.utils.formula_evaluator import FormulaEvaluator
from app.utils.interactive_tester import InteractiveTester

# Global variable to store the authorization code
auth_code = None

# Simple HTTP server to handle the OAuth callback
class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    # Suppress server logs for cleaner output
    def log_message(self, format, *args):
        return
        
    def do_GET(self):
        global auth_code
        
        # Handle favicon.ico requests separately
        if self.path == '/favicon.ico':
            self.send_response(204)  # No content
            self.end_headers()
            return
            
        parse_result = urllib.parse.urlparse(self.path)
        query = parse_result.query
        query_components = urllib.parse.parse_qs(query)
        
        print(f"OAuth callback received: {self.path}")
        print(f"Query components: {query_components}")
        
        # If this isn't the callback path we're expecting, ignore it
        if not self.path.startswith('/callback'):
            self.send_response(404)
            self.end_headers()
            return
        
        # Check for state parameter (CSRF protection)
        expected_state = "random_state"  # Should match the state in get_authorization_url
        received_state = query_components.get('state', [''])[0]
        
        if received_state != expected_state:
            print(f"Warning: State mismatch - expected '{expected_state}', got '{received_state}'")
            # We'll continue anyway as this is a local app
        
        if 'code' in query_components:
            auth_code = query_components['code'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b'<html><head><title>Authentication Successful</title></head>')
            self.wfile.write(b'<body><h1>Authentication Successful!</h1>')
            self.wfile.write(b'<p>You can close this window and return to the application.</p>')
            self.wfile.write(b'</body></html>')
        elif 'error' in query_components:
            error = query_components['error'][0]
            error_description = query_components.get('error_description', ['Unknown error'])[0]
            print(f"OAuth Error: {error} - {error_description}")
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b'<html><head><title>Authentication Failed</title></head>')
            self.wfile.write(f'<body><h1>Authentication Failed</h1>'.encode('utf-8'))
            self.wfile.write(f'<p>Error: {error}</p>'.encode('utf-8'))
            self.wfile.write(f'<p>Description: {error_description}</p>'.encode('utf-8'))
            self.wfile.write(b'<p>Please try again or check your client credentials.</p>')
            self.wfile.write(b'</body></html>')
        else:
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b'<html><head><title>Authentication Failed</title></head>')
            self.wfile.write(b'<body><h1>Authentication Failed</h1>')
            self.wfile.write(b'<p>No authorization code received. Please try again.</p>')
            self.wfile.write(b'</body></html>')

def start_auth_server(redirect_uri):
    """Start a simple HTTP server to handle OAuth callback using the port from redirect_uri
    
    Args:
        redirect_uri: The redirect URI registered with the accounting system
        
    Returns:
        socketserver.TCPServer: The server instance
        
    Raises:
        Exception: If the port is already in use or if the redirect URI is invalid
    """
    # Parse the redirect URI to get the port
    try:
        parsed_uri = urllib.parse.urlparse(redirect_uri)
        host = parsed_uri.hostname
        
        # Get the port from the URI, or use default port 80 for HTTP/443 for HTTPS
        if parsed_uri.port:
            port = parsed_uri.port
        elif parsed_uri.scheme == 'https':
            port = 443
        else:
            port = 80
            
        print(f"Using port {port} from redirect URI {redirect_uri}")
    except Exception as e:
        raise Exception(f"Invalid redirect URI format: {redirect_uri}. Error: {str(e)}")
    
    # Try to start the server on the exact port from the redirect URI
    try:
        server = socketserver.TCPServer((host, port), OAuthCallbackHandler)
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        print(f"Auth server started on {host}:{port}")
        return server
    except OSError as e:
        if "Address already in use" in str(e):
            raise Exception(f"""
Port {port} is already in use. This typically happens when:
1. Another instance of this application is running
2. The previous run didn't shut down the server properly
3. Another application is using this port

Please try:
- Waiting 30-60 seconds and trying again
- Checking for and closing other instances of this application
- Restarting your computer

If you continue to have issues, you can modify your accounting system application to use a different port in the redirect URI.
""")
        else:
            raise Exception(f"Failed to start server on {host}:{port}: {str(e)}")

def authenticate_accounting(accounting_client, cli):
    """Handle accounting system OAuth2 authentication flow
    
    Args:
        accounting_client (BaseAccountingClient): The accounting client instance
        cli (CLI): CLI interface for user interaction

    Returns:
        bool: True if authenticated, False otherwise
    """
    # Check if we're already authenticated
    if accounting_client.is_authenticated():
        return True
    
    # Get the accounting system name from the client class name
    client_class_name = accounting_client.__class__.__name__
    accounting_system_name = client_class_name.replace('Client', '')

    cli.print_section(f"{accounting_system_name} Authentication")
    cli.print_info(f"You need to authenticate with {accounting_system_name}.")
    
    # Get authorization URL
    auth_url = accounting_client.get_authorization_url()
    cli.print_info(f"Opening browser to authorize the application...")
    cli.print_info(f"Auth URL: {auth_url}")
    
    # Verify client ID and redirect URI
    cli.print_info(f"Client ID: {accounting_client.client_id}")
    cli.print_info(f"Redirect URI: {accounting_client.redirect_uri}")
    
    server = None
    try:
        # Start local server to handle the callback
        try:
            server = start_auth_server(accounting_client.redirect_uri)
        except Exception as e:
            cli.print_error(f"Failed to start authentication server: {str(e)}")
            return False
        
        # Open browser for user to authenticate
        webbrowser.open(auth_url)
        
        # Wait for the authorization code with timeout
        global auth_code
        auth_code = None
        timeout_seconds = 120  # 2 minutes
        cli.print_info(f"Waiting for authentication (timeout: {timeout_seconds} seconds)...")
        
        start_time = time.time()
        while auth_code is None and (time.time() - start_time) < timeout_seconds:
            time.sleep(1)
            # Show a progress indicator every 10 seconds
            elapsed = int(time.time() - start_time)
            if elapsed > 0 and elapsed % 10 == 0:
                cli.print_info(f"Still waiting... ({elapsed} seconds elapsed)")
        
        if auth_code is None:
            cli.print_error(f"Authentication timed out after {timeout_seconds} seconds.")
            cli.print_info("You can try again by restarting the application.")
            return False
        
        # Exchange the auth code for tokens
        cli.print_info("Exchanging authorization code for tokens...")
        if accounting_client.fetch_tokens(auth_code):
            cli.print_success(f"Successfully authenticated with {accounting_system_name}!")
            return True
        else:
            cli.print_error(f"Failed to authenticate with {accounting_system_name}.")
            return False
    
    finally:
        # Always shut down the server properly
        if server:
            cli.print_info("Shutting down authentication server...")
            try:
                server.shutdown()
                server.server_close()
                cli.print_info("Authentication server shut down successfully.")
            except Exception as e:
                cli.print_error(f"Error shutting down server: {str(e)}")
                # Continue anyway

def main(debug=False, dry_run=False, ignore_processed=False):
    # Initialize the CLI interface
    cli = CLI()
    cli.print_header("Gmail to Accounting Integration")
    
    if dry_run:
        cli.print_info("Running in DRY RUN mode - no actual changes will be made to the accounting system")
        
    # Load configuration
    try:
        config = load_config()
        cli.print_info("Configuration loaded")
    except Exception as e:
        cli.print_error(f"Failed to load configuration: {str(e)}")
        return
    
    # Initialize services
    try:
        # Initialize Gmail service
        gmail_config = config['gmail']
        credentials_file = Path(gmail_config['credentials_file'])
        token_file = Path(gmail_config['token_file'])
        
        # Make paths absolute if they're relative
        if not credentials_file.is_absolute():
            credentials_file = Path(__file__).parent / "config" / credentials_file
        
        if not token_file.is_absolute():
            token_file = Path(__file__).parent / "config" / token_file
        
        gmail = GmailService(
            credentials_file=str(credentials_file),
            token_file=str(token_file),
            scopes=gmail_config['scopes']
        )
        cli.print_info("Gmail service initialized")
        
        # Initialize Accounting client using the factory
        try:
            accounting = AccountingClientFactory.create_client(config, debug=debug)

            # Get the accounting system name from the client class name
            accounting_system_name = accounting.__class__.__name__.replace('Client', '')
            cli.print_info(f"{accounting_system_name} client initialized")

        except ValueError as e:
            cli.print_error(f"Failed to initialize accounting client: {str(e)}")
            return

        # Initialize data extraction and formula evaluation modules
        data_extractor = DataExtractor()
        formula_evaluator = FormulaEvaluator()
        cli.print_info("Data extraction and formula modules initialized")
        
        # Authenticate with accounting system if needed (skip in dry run mode)
        if not dry_run:
            if not authenticate_accounting(accounting, cli):
                return
        else:
            cli.print_info(f"Skipping accounting system authentication in dry run mode")
        
        # Initialize PDF converter
        pdf_converter = PdfConverter()
        cli.print_info("PDF converter initialized")
        
    except Exception as e:
        cli.print_error(f"Failed to initialize services: {str(e)}")
        return
    
    # Load processed emails to avoid duplicates
    processed_emails = [] if ignore_processed else get_processed_emails()
    if ignore_processed:
        cli.print_info("Ignoring previously processed emails (for testing)")
    else:
        cli.print_info(f"Loaded {len(processed_emails)} processed email IDs")
    
    # Load ignored emails
    ignored_emails = get_ignored_emails()
    cli.print_info(f"Loaded {len(ignored_emails)} ignored email IDs")
    
    # Display current rules
    print_rules(config)
    
    # Get emails from Gmail
    try:
        cli.print_section("Fetching emails")
        
        # Get all matching rules
        rules = config.get('email_rules', [])
        if not rules:
            cli.print_error("No email rules defined in config!")
            return

        # Prepare query for each rule and collect results
        matching_emails = []

        for rule_index, rule in enumerate(rules):
            rule_name = rule.get('name', f"Rule {rule_index + 1}")

            # Get sender
            sender = rule.get('sender', '')
            if not sender:
                cli.print_warning(f"Rule {rule_name} has no sender specified, skipping")
                continue

            # Get subject pattern
            subject = rule.get('subject', '')

            # Get body contains patterns
            body_contains = rule.get('body_contains', [])
            if isinstance(body_contains, str):
                body_contains = [body_contains]

            # Build search query
            search_parts = []
            
            # Add date restriction for last 3 months
            start_date = (datetime.datetime.now() - datetime.timedelta(days=30 * 3)).strftime('%Y/%m/%d')
            search_parts.append(f"after:{start_date}")
            
            if sender:
                search_parts.append(f"from:({sender})")
                
            if subject:
                search_parts.append(f"subject:({subject})")
            
            # Combine parts
            search_query = " ".join(search_parts)

            # Display query
            cli.print_info(f"Searching for rule '{rule_name}': {search_query}")

            # Run search
            emails = gmail.search_emails(search_query)

            if not emails:
                cli.print_info(f"No emails found matching rule '{rule_name}'")
                continue

            cli.print_info(f"Found {len(emails)} email(s) matching rule '{rule_name}'")

            # Check each email for body_contains patterns
            for email in emails:
                email_id = email['id']

                # Skip if already processed or ignored
                if email_id in processed_emails:
                    cli.print_info(f"Skipping already processed email: {email_id}")
                    continue

                if email_id in ignored_emails:
                    cli.print_info(f"Skipping ignored email: {email_id}")
                    continue

                # Get full email content
                msg = gmail.get_message(email_id)

                # Get email body
                email_body = gmail.get_email_body(msg)

                # Check for body_contains patterns
                body_match = True

                if body_contains:
                    body_match = False
                    for pattern in body_contains:
                        if pattern.lower() in email_body.lower():
                            body_match = True
                            break

                if body_match:
                    matching_emails.append({
                        'email': email,
                        'message': msg,
                        'rule': rule,
                        'rule_index': rule_index
                    })

        if not matching_emails:
            cli.print_info("No new matching emails found.")
            return

        cli.print_info(f"Found {len(matching_emails)} new matching email(s)")

        # Process each matching email
        for match in matching_emails:
            email = match['email']
            msg = match['message']
            rule = match['rule']
            rule_index = match['rule_index']

            email_id = email['id']

            # Get email info
            headers = msg['payload']['headers']
            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
            sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'Unknown Sender')

            cli.print_section(f"Processing email: {subject}")
            cli.print_info(f"From: {sender}")
            cli.print_info(f"Email ID: {email_id}")

            # Get email body
            email_body = gmail.get_email_body(msg)

            # Get email attachments
            attachments = gmail.get_attachments(msg)

            # Create a PDF of the email
            pdf_path = None
            try:
                pdf_path = pdf_converter.convert_email_to_pdf(
                    subject=subject,
                    sender=sender,
                    body=email_body,
                    attachments=attachments
                )
                cli.print_info(f"Created PDF: {pdf_path}")
                
                # Open the PDF file in the default viewer
                cli.print_info("Opening PDF preview...")
                webbrowser.open(f"file://{pdf_path}")
            except Exception as pdf_error:
                cli.print_warning(f"Failed to create PDF: {str(pdf_error)}")

            # Extract data from email based on rules
            extracted_data = {}

            # Check if the rule has data extraction patterns
            if 'data_extraction' in rule:
                cli.print_info("Extracting data from email...")
                
                # Create email content dict for data extraction
                email_content = {
                    'body_text': email_body,
                    'body_html': email_body  # Using the same content for both since get_email_body returns either HTML or text
                }
                
                # Use extract_data method which handles html_pattern correctly
                extracted_data = data_extractor.extract_data(
                    email_content=email_content,
                    extraction_rules=rule['data_extraction']
                )
                
                # Display extracted data
                for field_name, value in extracted_data.items():
                    cli.print_info(f"Extracted {field_name}: {value}")
            
            # Process accounting information if present
            if 'accounting' in rule:
                cli.print_info("Preparing accounting verification...")

                accounting_info = rule['accounting']

                # Get accounting details
                description = accounting_info.get('description', f"Email: {subject}")
                voucher_series = accounting_info.get('series', 'A')

                # Process accounting entries
                entries = []

                for entry in accounting_info.get('entries', []):
                    # Create a copy of the entry
                    processed_entry = entry.copy()

                    # Evaluate debit and credit using formula evaluator
                    try:
                        if isinstance(entry['debit'], str):
                            processed_entry['debit'] = formula_evaluator.evaluate(
                                entry['debit'],
                                extracted_data
                            )

                        if isinstance(entry['credit'], str):
                            processed_entry['credit'] = formula_evaluator.evaluate(
                                entry['credit'],
                                extracted_data
                            )
                    except Exception as eval_error:
                        cli.print_error(f"Error evaluating formula: {str(eval_error)}")
                        continue

                    entries.append(processed_entry)

                # Create a verification rule for display purposes
                verification_rule = {
                    'email_subject': subject,
                    'email_from': sender,
                }

                # Create a copy of the accounting section to avoid modifying the original
                verification_rule['accounting'] = accounting_info.copy()
                # Replace the entries with calculated entries
                verification_rule['accounting']['entries'] = entries

                # Show verification details
                cli.print_verification_summary(verification_rule, pdf_path)

                # Confirm creating verification
                confirmation = cli.confirm("Create this verification in the accounting system?")
                if confirmation != 'y':
                    cli.print_info("Skipping verification creation")
                    continue

                # Create verification in accounting system
                cli.print_info("Creating verification in the accounting system...")

                # Get current date in required format
                today = datetime.datetime.now().strftime('%Y-%m-%d')

                # Skip actual API call in dry run mode
                if dry_run:
                    cli.print_success("DRY RUN: Verification would be created with these details")
                    cli.print_info(f"Description: {description}")
                    cli.print_info(f"Series: {voucher_series}")
                    cli.print_info(f"Date: {today}")
                    for entry in entries:
                        cli.print_info(f"Account: {entry['account']}, Debit: {entry['debit']}, Credit: {entry['credit']}")
                    
                    # Save as processed in dry run mode too
                    save_processed_email(email_id)
                    cli.print_info(f"Email marked as processed (in dry run mode)")
                    continue
                
                # Create the actual voucher
                try:
                    voucher = accounting.create_voucher(
                        description=description,
                        voucher_series=voucher_series,
                        voucher_date=today,
                        entries=entries,
                        attachment_path=pdf_path
                    )

                    # Different accounting systems may return different voucher formats
                    # Try to extract voucher number and series in a generic way
                    voucher_number = None
                    voucher_series_result = voucher_series

                    # Check if response is a dict with Voucher key (Fortnox format)
                    if isinstance(voucher, dict) and 'Voucher' in voucher:
                        fortnox_voucher = voucher['Voucher']
                        voucher_number = fortnox_voucher.get('VoucherNumber')
                        voucher_series_result = fortnox_voucher.get('VoucherSeries', voucher_series)
                    # Check for Kleer format
                    elif isinstance(voucher, dict) and 'id' in voucher:
                        voucher_number = voucher.get('id')
                        voucher_series_result = voucher.get('seriesId', voucher_series)

                    if voucher_number:
                        cli.print_success(f"Verification created successfully! Voucher: {voucher_series_result}{voucher_number}")
                    else:
                        cli.print_success(f"Verification created successfully!")

                    # Save email as processed
                    save_processed_email(email_id)
                    cli.print_info(f"Email marked as processed")

                except Exception as voucher_error:
                    error_msg = str(voucher_error)

                    # If the error mentions the Attachments field
                    if "Felaktigt fältnamn (Attachments)" in error_msg:
                        cli.print_warning("The API doesn't accept attachments in the voucher creation request.")
                        cli.print_info("This is likely because the API expects attachments to be connected separately.")

                        if cli.confirm("Do you want to try creating the voucher without attachment?", default=True) == 'y':
                            try:
                                # Try again without attachment
                                voucher = accounting.create_voucher(
                                    description=description,
                                    voucher_series=voucher_series,
                                    voucher_date=today,
                                    entries=entries,
                                    attachment_path=None  # No attachment this time
                                )

                                # Different accounting systems may return different voucher formats
                                # Try to extract voucher number and series in a generic way
                                voucher_number = None
                                voucher_series_result = voucher_series

                                # Check if response is a dict with Voucher key (Fortnox format)
                                if isinstance(voucher, dict) and 'Voucher' in voucher:
                                    fortnox_voucher = voucher['Voucher']
                                    voucher_number = fortnox_voucher.get('VoucherNumber')
                                    voucher_series_result = fortnox_voucher.get('VoucherSeries', voucher_series)
                                # Check for Kleer format
                                elif isinstance(voucher, dict) and 'id' in voucher:
                                    voucher_number = voucher.get('id')
                                    voucher_series_result = voucher.get('seriesId', voucher_series)

                                if voucher_number:
                                    cli.print_success(f"Verification created successfully! Voucher: {voucher_series_result}{voucher_number}")
                                else:
                                    cli.print_success(f"Verification created successfully!")

                                # Save email as processed
                                save_processed_email(email_id)
                                cli.print_info(f"Email marked as processed")

                            except Exception as retry_error:
                                cli.print_error(f"Failed to create voucher without attachment: {str(retry_error)}")
                                if cli.confirm("Do you want to ignore this email in the future?") == 'y':
                                    save_ignored_email(email_id)
                                    cli.print_info(f"Email marked as ignored")
                    else:
                        cli.print_error(f"Failed to create voucher: {error_msg}")
                        if cli.confirm("Do you want to ignore this email in the future?") == 'y':
                            save_ignored_email(email_id)
                            cli.print_info(f"Email marked as ignored")
            else:
                cli.print_warning("No accounting information found in rule")

                if cli.confirm("Do you want to ignore this email in the future?") == 'y':
                    save_ignored_email(email_id)
                    cli.print_info(f"Email marked as ignored")

        cli.print_section("Processing complete")

    except Exception as e:
        cli.print_error(f"Error processing emails: {str(e)}")

def print_rules(config):
    """Print the email rules for debugging"""
    print("\nEmail Rules:")
    print("=" * 50)
    for i, rule in enumerate(config['email_rules'], 1):
        print(f"Rule #{i}:")
        print(f"  Sender: {rule.get('sender', 'any')}")
        print(f"  Subject: {rule.get('subject', 'any')}")
        
        if 'body_contains' in rule:
            if isinstance(rule['body_contains'], list):
                print(f"  Body must contain ALL of these terms:")
                for term in rule['body_contains']:
                    print(f"    - '{term}'")
            else:
                print(f"  Body must contain: '{rule['body_contains']}'")
        
        print(f"  Accounting:")
        print(f"    Description: {rule['accounting']['description']}")
        print(f"    Series: {rule['accounting']['series']}")
        print(f"    Entries: {len(rule['accounting']['entries'])} entries")
        print("-" * 50)

def gmail_id_to_url(gmail_id):
    """Convert a Gmail API message ID to a Gmail web URL
    
    Args:
        gmail_id (str): Gmail API message ID
        
    Returns:
        str: Gmail web URL for the message
    """
    return f"https://mail.google.com/mail/u/0/#inbox/{gmail_id}"

def show_email_info(email):
    """Show extended information about an email including its Gmail URL
    
    Args:
        email (dict): Email content dictionary
    """
    email_id = email.get('id', '')
    subject = email.get('subject', 'No subject')
    sender = email.get('sender', 'Unknown sender')
    date = email.get('date', datetime.datetime.now()).strftime('%Y-%m-%d %H:%M:%S')
    
    print(f"\nEmail: {subject}")
    print(f"From: {sender}")
    print(f"Date: {date}")
    print(f"Gmail ID: {email_id}")
    print(f"Gmail URL: {gmail_id_to_url(email_id)}")
    print("*" * 80)

def show_processed_emails(processed_emails, ignored_emails=None):
    """Display the list of processed and ignored emails with their Gmail URLs
    
    Args:
        processed_emails (list): List of processed email IDs
        ignored_emails (list, optional): List of ignored email IDs
    """
    print("\nProcessed emails:")
    print("=" * 80)
    if not processed_emails:
        print("No processed emails found.")
    else:
        for i, email_id in enumerate(processed_emails, 1):
            print(f"{i}. ID: {email_id}")
            print(f"   URL: {gmail_id_to_url(email_id)}")
    
    if ignored_emails:
        print("\nIgnored emails:")
        print("=" * 80)
        if not ignored_emails:
            print("No ignored emails found.")
        else:
            for i, email_id in enumerate(ignored_emails, 1):
                print(f"{i}. ID: {email_id}")
                print(f"   URL: {gmail_id_to_url(email_id)}")
    
    print("\nTo open a specific email, click on its URL or copy it to your browser.")
    print("Note: If the URL doesn't work, the email may have been deleted or moved to a different folder.")

def create_rule_interactive(config, email_id=None, rule_file=None, debug=False):
    """
    Interactively create or modify a rule using a sample email.
    
    Args:
        config (dict): Application configuration
        email_id (str, optional): Gmail message ID to use
        rule_file (str, optional): File to load/save rule from/to
        debug (bool, optional): Enable debug output
    """
    cli = CLI()
    cli.print_header("Interactive Rule Creator")
    
    # Initialize Gmail service
    try:
        gmail_config = config['gmail']
        credentials_file = Path(gmail_config['credentials_file'])
        token_file = Path(gmail_config['token_file'])
        
        # Make paths absolute if they're relative
        if not credentials_file.is_absolute():
            credentials_file = Path(__file__).parent / "config" / credentials_file
        
        if not token_file.is_absolute():
            token_file = Path(__file__).parent / "config" / token_file
        
        gmail = GmailService(
            credentials_file=str(credentials_file),
            token_file=str(token_file),
            scopes=gmail_config['scopes']
        )
        cli.print_info("Gmail service initialized")
    except Exception as e:
        cli.print_error(f"Failed to initialize Gmail service: {str(e)}")
        return
    
    # Get email to use
    email_content = None
    
    if email_id:
        # Use specified email
        cli.print_info(f"Getting email with ID: {email_id}")
        try:
            message = gmail.get_email(email_id)
            email_content = gmail.get_email_content(message)
            cli.print_success(f"Got email: '{email_content.get('subject', '')}' from {email_content.get('sender', '')}")
        except Exception as e:
            cli.print_error(f"Failed to get email: {str(e)}")
            return
    else:
        # Let user search for an email
        cli.print_section("Email Search")
        cli.print_info("No email ID provided. Let's search for an email to use.")
        
        search_term = input("Enter search term (sender, subject, etc.): ")
        if not search_term:
            cli.print_error("No search term provided. Exiting.")
            return
        
        try:
            query = search_term
            messages = gmail.search_emails(query, max_results=20)
            
            if not messages:
                cli.print_error("No matching emails found.")
                return
                
            cli.print_success(f"Found {len(messages)} matching emails.")
            
            # Show email list for selection
            print("\nAvailable emails:")
            for i, msg in enumerate(messages):
                msg_data = gmail.get_email(msg['id'])
                content = gmail.get_email_content(msg_data)
                print(f"{i+1}. Subject: '{content.get('subject', 'No subject')}' from {content.get('sender', 'unknown')}")
                
            # Let user select an email
            selection = input("\nSelect email number (or 'q' to quit): ")
            if selection.lower() == 'q':
                return
                
            try:
                index = int(selection) - 1
                if 0 <= index < len(messages):
                    msg_data = gmail.get_email(messages[index]['id'])
                    email_content = gmail.get_email_content(msg_data)
                    cli.print_success(f"Selected email: '{email_content.get('subject', '')}' from {email_content.get('sender', '')}")
                else:
                    cli.print_error(f"Invalid selection: {selection}")
                    return
            except ValueError:
                cli.print_error(f"Invalid selection: {selection}")
                return
                
        except Exception as e:
            cli.print_error(f"Error searching emails: {str(e)}")
            return
    
    # Load existing rule if specified
    existing_rule = None
    if rule_file:
        try:
            if os.path.exists(rule_file):
                with open(rule_file, 'r') as f:
                    existing_rule = json.load(f)
                cli.print_info(f"Loaded existing rule from {rule_file}")
        except Exception as e:
            cli.print_warning(f"Failed to load rule from {rule_file}: {str(e)}")
            cli.print_info("Starting with a new rule instead.")
    
    # Create interactive tester
    tester = InteractiveTester(email_content)
    
    # Run interactive session
    rule = tester.run_interactive_session(existing_rule)
    
    # Save rule if needed
    if rule:
        if rule_file:
            try:
                with open(rule_file, 'w') as f:
                    json.dump(rule, f, indent=2)
                cli.print_success(f"Rule saved to {rule_file}")
            except Exception as e:
                cli.print_error(f"Failed to save rule to {rule_file}: {str(e)}")
        
        # Ask if user wants to add rule to config
        add_to_config = input("\nAdd this rule to your configuration? (y/n): ").lower()
        if add_to_config == 'y':
            try:
                # Add rule to config
                if 'email_rules' not in config:
                    config['email_rules'] = []
                    
                # Check if rule already exists (by sender, subject, body_contains)
                existing_index = None
                for i, existing in enumerate(config['email_rules']):
                    if (existing.get('sender') == rule.get('sender') and
                        existing.get('subject') == rule.get('subject') and
                        existing.get('body_contains') == rule.get('body_contains')):
                        existing_index = i
                        break
                
                if existing_index is not None:
                    # Update existing rule
                    confirm = input(f"Rule already exists at position {existing_index+1}. Replace it? (y/n): ").lower()
                    if confirm == 'y':
                        config['email_rules'][existing_index] = rule
                        save_config(config)
                        cli.print_success("Rule updated in configuration.")
                    else:
                        cli.print_info("Rule not updated.")
                else:
                    # Add new rule
                    config['email_rules'].append(rule)
                    save_config(config)
                    cli.print_success("Rule added to configuration.")
                    
            except Exception as e:
                cli.print_error(f"Failed to update configuration: {str(e)}")
    else:
        cli.print_warning("No rule created.")

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Gmail to Accounting Integration')
    parser.add_argument('--show-rules', action='store_true', help='Show the email rules and exit')
    parser.add_argument('--show-emails', action='store_true', help='Show processed and ignored emails with Gmail URLs')
    parser.add_argument('--debug', action='store_true', help='Enable additional debug output')
    
    args = parser.parse_args()
    
    # Load configuration first (needed for both modes)
    try:
        from app.config.config import load_config
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
    
    # Otherwise run the main program
    main(args.debug) 
