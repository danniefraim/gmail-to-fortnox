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
from app.fortnox.fortnox_client import FortnoxClient
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
        redirect_uri: The redirect URI registered with Fortnox
        
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

If you continue to have issues, you can modify your Fortnox application to use a different port in the redirect URI.
""")
        else:
            raise Exception(f"Failed to start server on {host}:{port}: {str(e)}")

def authenticate_fortnox(fortnox_client, cli):
    """Handle Fortnox OAuth2 authentication flow
    
    Returns:
        bool: True if authenticated, False otherwise
    """
    # Check if we're already authenticated
    if fortnox_client.is_authenticated():
        return True
    
    cli.print_section("Fortnox Authentication")
    cli.print_info("You need to authenticate with Fortnox.")
    
    # Get authorization URL
    auth_url = fortnox_client.get_authorization_url()
    cli.print_info(f"Opening browser to authorize the application...")
    cli.print_info(f"Auth URL: {auth_url}")
    
    # Verify client ID and redirect URI
    cli.print_info(f"Client ID: {fortnox_client.client_id}")
    cli.print_info(f"Redirect URI: {fortnox_client.redirect_uri}")
    
    server = None
    try:
        # Start local server to handle the callback
        try:
            server = start_auth_server(fortnox_client.redirect_uri)
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
        if fortnox_client.fetch_tokens(auth_code):
            cli.print_success("Successfully authenticated with Fortnox!")
            return True
        else:
            cli.print_error("Failed to authenticate with Fortnox.")
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
    cli.print_header("Gmail to Fortnox Integration")
    
    if dry_run:
        cli.print_info("Running in DRY RUN mode - no actual changes will be made to Fortnox")
        
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
        
        # Initialize Fortnox client
        fortnox_config = config['fortnox']
        
        # Validate required Fortnox parameters
        if not fortnox_config.get('client_id'):
            cli.print_error("Missing client_id in Fortnox configuration!")
            cli.print_info("Please check your app/config/config.json file and ensure client_id is specified.")
            return
            
        if not fortnox_config.get('client_secret'):
            cli.print_error("Missing client_secret in Fortnox configuration!")
            cli.print_info("Please check your app/config/config.json file and ensure client_secret is specified.")
            return
        
        fortnox_token_file = Path(fortnox_config.get('token_file', 'fortnox_token.json'))
        
        if not fortnox_token_file.is_absolute():
            fortnox_token_file = Path(__file__).parent / "config" / fortnox_token_file
        
        fortnox = FortnoxClient(
            client_id=fortnox_config['client_id'],
            client_secret=fortnox_config['client_secret'],
            redirect_uri=fortnox_config.get('redirect_uri', 'http://localhost:8000/callback'),
            base_url=fortnox_config['base_url'],
            token_file=str(fortnox_token_file)
        )
        cli.print_info("Fortnox client initialized")
        
        # Initialize data extraction and formula evaluation modules
        data_extractor = DataExtractor()
        formula_evaluator = FormulaEvaluator()
        cli.print_info("Data extraction and formula modules initialized")
        
        # Authenticate with Fortnox if needed (skip in dry run mode)
        if not dry_run:
            if not authenticate_fortnox(fortnox, cli):
                return
        else:
            cli.print_info("Skipping Fortnox authentication in dry run mode")
        
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
    
    # Search for matching emails
    try:
        cli.print_section("Searching for matching emails")
        
        matching_emails = gmail.find_matching_emails(
            rules=config['email_rules'],
            processed_emails=processed_emails,
            ignored_emails=ignored_emails,
            months_back=14,
            debug=debug
        )
        
        if not matching_emails:
            cli.print_info("No new matching emails found")
            return
        
        cli.print_success(f"Found {len(matching_emails)} new matching emails")
    except Exception as e:
        cli.print_error(f"Failed to search emails: {str(e)}")
        return
    
    # Process each matching email
    for match in matching_emails:
        email = match['email']
        rule = match['rule']
        
        # Show detailed email information including Gmail URL
        show_email_info(email)
        
        # Show email summary
        cli.print_email_summary(email)
        
        try:
            # Extract data from email if data_extraction rules are specified
            extracted_data = {}
            if 'data_extraction' in rule and rule['data_extraction']:
                cli.print_info("Extracting data from email using patterns...")
                extracted_data = data_extractor.extract_data(email, rule['data_extraction'])
                
                # Show extracted data
                if extracted_data:
                    cli.print_success("Data extracted from email:")
                    for var_name, value in extracted_data.items():
                        cli.print_info(f"  {var_name} = {value}")
                else:
                    cli.print_warning("No data could be extracted from the email.")
            
            # Convert email to PDF
            cli.print_info("Converting email to PDF...")
            pdf_path = pdf_converter.email_to_pdf(email)
            cli.print_success(f"PDF created: {pdf_path}")
            
            # Open PDF in default viewer (Preview on macOS)
            cli.print_info("Opening PDF for preview...")
            try:
                if sys.platform == "darwin":  # macOS
                    os.system(f"open '{pdf_path}'")
                elif sys.platform == "win32":  # Windows
                    os.system(f'start "" "{pdf_path}"')
                else:  # Linux or other Unix
                    os.system(f"xdg-open '{pdf_path}' &>/dev/null &")
            except Exception as e:
                cli.print_warning(f"Could not open PDF automatically: {str(e)}")
            
            # Confirm processing this email
            confirmation = cli.confirm("Process this email?")
            if confirmation == 'n':
                cli.print_info("Skipping this email for now")
                continue
            elif confirmation == 'i':
                cli.print_info("Adding email to ignored list - it will be skipped in all future runs")
                save_ignored_email(email['id'])
                continue
            
            # Calculate voucher entries if data was extracted
            accounting = rule['accounting']
            if extracted_data and 'entries' in accounting:
                cli.print_info("Calculating voucher entries based on extracted data...")
                entries = formula_evaluator.calculate_voucher_entries(
                    accounting['entries'], extracted_data
                )
                
                # Calculate totals to verify balance
                total_debit = sum(entry['debit'] for entry in entries)
                total_credit = sum(entry['credit'] for entry in entries)
                
                # Show calculated entries
                cli.print_success("Calculated voucher entries:")
                for entry in entries:
                    cli.print_info(f"  Account: {entry['account']}, Debit: {entry['debit']}, Credit: {entry['credit']}")
                    
                cli.print_info(f"  Total Debit: {total_debit}")
                cli.print_info(f"  Total Credit: {total_credit}")
                
                if total_debit != total_credit:
                    cli.print_warning("WARNING: Voucher is not balanced!")
                    if not cli.confirm("Voucher is not balanced. Continue anyway?"):
                        cli.print_info("Skipping this verification")
                        continue
            else:
                # Use original entries if no data extraction or calculation needed
                entries = accounting['entries']
            
            # Create a modified rule with calculated entries for verification summary
            verification_rule = rule.copy()
            # Create a copy of the accounting section to avoid modifying the original
            verification_rule['accounting'] = accounting.copy()
            # Replace the entries with calculated entries
            verification_rule['accounting']['entries'] = entries
            
            # Show verification details
            cli.print_verification_summary(verification_rule, pdf_path)
            
            # Confirm creating verification
            confirmation = cli.confirm("Create this verification in Fortnox?")
            if confirmation != 'y':
                cli.print_info("Skipping verification creation")
                continue
            
            # Create verification in Fortnox
            cli.print_info("Creating verification in Fortnox...")
            
            # Get current date in required format
            today = datetime.datetime.now().strftime('%Y-%m-%d')
            
            try:
                # If dry run, just print what would happen
                if dry_run:
                    cli.print_info("DRY RUN: Would create a voucher with the following details:")
                    cli.print_info(f"  Description: {accounting['description']}")
                    cli.print_info(f"  Voucher Series: {accounting['series']}")
                    cli.print_info(f"  Date: {today}")
                    cli.print_info(f"  Entries: {len(entries)} entries")
                    for i, entry in enumerate(entries, 1):
                        cli.print_info(f"    Entry {i}: Account {entry['account']}, Debit: {entry.get('debit', 0)}, Credit: {entry.get('credit', 0)}")
                    cli.print_info(f"  Attachment: {pdf_path}")
                    
                    # Save email as processed if requested
                    if cli.confirm("Would you like to mark this email as processed?"):
                        save_processed_email(email['id'])
                        cli.print_success("Email marked as processed")
                    continue
                
                # Create voucher - convert Decimal objects to float for JSON serialization
                float_entries = []
                for entry in entries:
                    float_entry = {
                        'account': entry['account'],
                        'debit': float(entry['debit']),
                        'credit': float(entry['credit'])
                    }
                    float_entries.append(float_entry)
                
                voucher = fortnox.create_voucher(
                    description=accounting['description'],
                    voucher_series=accounting['series'],
                    voucher_date=today,
                    entries=float_entries,
                    attachment_path=pdf_path
                )
                
                # Save email as processed
                save_processed_email(email['id'])
                
                voucher_number = voucher['Voucher']['VoucherNumber']
                voucher_series = voucher['Voucher']['VoucherSeries']
                cli.print_success(f"Verification created successfully! Voucher number: {voucher_series}{voucher_number}")
            except Exception as voucher_error:
                error_msg = str(voucher_error)
                
                # If the error mentions the Attachments field
                if "Felaktigt fältnamn (Attachments)" in error_msg:
                    cli.print_warning("The Fortnox API doesn't accept attachments in the voucher creation request.")
                    cli.print_info("This is likely because the API expects attachments to be connected separately.")
                    
                    if cli.confirm("Do you want to try creating the voucher without attachment?", default=True) == 'y':
                        try:
                            # Try again without attachment
                            cli.print_info("Creating voucher without attachment...")
                            voucher = fortnox.create_voucher(
                                description=accounting['description'],
                                voucher_series=accounting['series'],
                                voucher_date=today,
                                entries=float_entries
                                # No attachment_path
                            )
                            
                            # Save email as processed
                            save_processed_email(email['id'])
                            
                            voucher_number = voucher['Voucher']['VoucherNumber']
                            voucher_series = voucher['Voucher']['VoucherSeries']
                            cli.print_success(f"Verification created successfully without attachment! Voucher number: {voucher_series}{voucher_number}")
                            cli.print_info("You can manually add the attachment through the Fortnox web interface if needed.")
                            continue
                        except Exception as e:
                            cli.print_error(f"Failed to create voucher without attachment: {str(e)}")
                
                # If there was an issue with the voucherfileconnections endpoint
                elif "voucherfileconnections" in error_msg and ("404" in error_msg or "401" in error_msg or "403" in error_msg):
                    cli.print_warning("There was an issue connecting the file to the voucher.")
                    cli.print_info("This may be due to missing permissions or incorrect file ID.")
                    
                    if cli.confirm("Do you want to try creating the voucher without attachment?", default=True) == 'y':
                        try:
                            # Try again without attachment
                            cli.print_info("Creating voucher without attachment...")
                            voucher = fortnox.create_voucher(
                                description=accounting['description'],
                                voucher_series=accounting['series'],
                                voucher_date=today,
                                entries=float_entries
                                # No attachment_path
                            )
                            
                            # Save email as processed
                            save_processed_email(email['id'])
                            
                            voucher_number = voucher['Voucher']['VoucherNumber']
                            voucher_series = voucher['Voucher']['VoucherSeries']
                            cli.print_success(f"Verification created successfully without attachment! Voucher number: {voucher_series}{voucher_number}")
                            cli.print_info("You can manually add the attachment through the Fortnox web interface if needed.")
                            continue
                        except Exception as e:
                            cli.print_error(f"Failed to create voucher without attachment: {str(e)}")
                
                # General error handling
                cli.print_error(f"Failed to create voucher: {str(voucher_error)}")
                
                # Offer to mark as processed anyway
                if cli.confirm("Would you like to mark this email as processed anyway?"):
                    save_processed_email(email['id'])
                    cli.print_success("Email marked as processed")
                
        except Exception as e:
            cli.print_error(f"Error processing email: {str(e)}")
            if cli.confirm("Continue with next email?"):
                continue
            else:
                break
    
    cli.print_section("Processing complete")

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
    parser = argparse.ArgumentParser(description='Gmail to Fortnox Integration')
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