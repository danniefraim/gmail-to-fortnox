import os
import base64
import datetime
import json
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

class GmailService:
    def __init__(self, credentials_file, token_file, scopes):
        """Initialize Gmail service with OAuth credentials"""
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.scopes = scopes
        self.service = self._authenticate()
    
    def _authenticate(self):
        """Authenticate with Gmail API"""
        creds = None
        
        # Check if token.json exists
        if os.path.exists(self.token_file):
            creds = Credentials.from_authorized_user_info(
                json.loads(open(self.token_file).read()), 
                self.scopes
            )
        
        # If credentials don't exist or are invalid, get new ones
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, self.scopes
                )
                creds = flow.run_local_server(port=0)
            
            # Save the updated credentials
            with open(self.token_file, 'w') as token:
                token.write(creds.to_json())
        
        return build('gmail', 'v1', credentials=creds)
    
    def search_messages(self, query, max_results=500):
        """Search for emails matching the query string (alias for search_emails)
        
        Args:
            query (str): Gmail search query
            max_results (int): Maximum number of results to return
            
        Returns:
            list: List of message dictionaries with id and threadId
        """
        return self.search_emails(query, max_results)
    
    def search_emails(self, query, max_results=500):
        """Search for emails matching the query string
        
        Args:
            query (str): Gmail search query
            max_results (int): Maximum number of results to return
            
        Returns:
            list: List of message dictionaries with id and threadId
        """
        messages = []
        next_page_token = None
        
        # Keep track of how many emails we've fetched
        total_fetched = 0
        fetch_count = 0
        
        print(f"Fetching emails (up to {max_results})...")
        
        while total_fetched < max_results:
            # Calculate how many results to request in this page
            # We can request at most 500 per page in Gmail API
            page_size = min(500, max_results - total_fetched)
            
            # Request this page of results
            request = self.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=page_size,
                pageToken=next_page_token
            )
            
            result = request.execute()
            
            # Add the messages from this page to our list
            page_messages = result.get('messages', [])
            messages.extend(page_messages)
            total_fetched += len(page_messages)
            fetch_count += 1
            
            # Get the next page token
            next_page_token = result.get('nextPageToken')
            
            # If there's no next page token, we've reached the end
            if not next_page_token:
                break
            
            # If we've already fetched the max number of results, stop
            if total_fetched >= max_results:
                break
            
            # Show progress for each page after the first
            print(f"Fetched {total_fetched} emails so far... (page {fetch_count})")
        
        if total_fetched >= 1000:
            print(f"Completed fetching {total_fetched} emails ({fetch_count} pages)")
            
        return messages
    
    def get_email(self, msg_id):
        """Get full email details by ID
        
        Args:
            msg_id (str): Email ID from Gmail API
            
        Returns:
            dict: Full email message
        """
        try:
            message = self.service.users().messages().get(
                userId='me', id=msg_id, format='full'
            ).execute()
            return message
        except Exception as e:
            print(f"Error getting email {msg_id}")
            # Return a minimal message that won't cause errors
            return {'id': msg_id, 'payload': {'headers': [], 'body': {'data': ''}}}
    
    def get_message(self, msg_id):
        """Alias for get_email method for compatibility
        
        Args:
            msg_id (str): Email ID from Gmail API
            
        Returns:
            dict: Full email message
        """
        return self.get_email(msg_id)
    
    def get_email_body(self, message):
        """Extract the text body from a message
        
        Args:
            message (dict): Full email message from Gmail API
            
        Returns:
            str: Email body text
        """
        # First get the full content
        content = self.get_email_content(message)
        
        # Prefer HTML content since it might have more information
        if content.get('body_html'):
            return content['body_html']
        
        # Fall back to text content
        return content.get('body_text', '')
    
    def get_attachments(self, message):
        """Extract attachments from a message
        
        Args:
            message (dict): Full email message from Gmail API
            
        Returns:
            list: List of attachment dictionaries with filename and data
        """
        attachments = []
        
        try:
            parts = []
            
            # Get parts from the payload
            if 'payload' in message:
                parts = self._get_parts_with_attachments(message['payload'])
            
            # Extract attachments from parts
            for part in parts:
                if 'filename' in part and part['filename'] and 'body' in part and 'attachmentId' in part['body']:
                    # Get the attachment ID
                    attachment_id = part['body']['attachmentId']
                    
                    # Get the attachment data
                    attachment = self.service.users().messages().attachments().get(
                        userId='me',
                        messageId=message['id'],
                        id=attachment_id
                    ).execute()
                    
                    # Decode the data
                    file_data = base64.urlsafe_b64decode(attachment['data'])
                    
                    # Add to attachments list
                    attachments.append({
                        'filename': part['filename'],
                        'data': file_data,
                        'mime_type': part.get('mimeType', 'application/octet-stream')
                    })
        except Exception as e:
            print(f"Error getting attachments: {e}")
        
        return attachments
    
    def _get_parts_with_attachments(self, payload):
        """Recursively extract all parts from message payload that could have attachments
        
        Args:
            payload (dict): Message payload
            
        Returns:
            list: List of parts that might have attachments
        """
        parts = []
        
        # If this part has a filename, it's an attachment
        if 'filename' in payload and payload['filename']:
            parts.append(payload)
        
        # If this part has sub-parts
        if 'parts' in payload:
            for part in payload['parts']:
                parts.extend(self._get_parts_with_attachments(part))
        
        return parts
    
    def get_email_content(self, message):
        """Extract email content (subject, sender, body, date) from a message
        
        Args:
            message (dict): Full email message from Gmail API
            
        Returns:
            dict: Extracted email content with id, subject, sender, date, body_text, body_html
        """
        try:
            # Check if message has required fields
            if 'payload' not in message or 'headers' not in message['payload']:
                return {
                    'id': message.get('id', 'unknown'),
                    'thread_id': message.get('threadId', ''),
                    'subject': '',
                    'sender': '',
                    'date': datetime.datetime.now(),
                    'body_html': '',
                    'body_text': '',
                    'headers': []
                }
                
            headers = message['payload']['headers']
            parts = self._get_parts(message['payload'])
            
            # Extract headers
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), '')
            date_str = next((h['value'] for h in headers if h['name'] == 'Date'), '')
            
            # Extract body content
            body_html = None
            body_text = None
            
            for part in parts:
                if part['mimeType'] == 'text/html' and 'body' in part and 'data' in part['body']:
                    body_html = part['body']['data']
                elif part['mimeType'] == 'text/plain' and 'body' in part and 'data' in part['body']:
                    body_text = part['body']['data']
            
            # Decode body content
            if body_html:
                try:
                    body_html = base64.urlsafe_b64decode(body_html).decode('utf-8')
                except Exception:
                    body_html = ''
                    
            if body_text:
                try:
                    body_text = base64.urlsafe_b64decode(body_text).decode('utf-8')
                except Exception:
                    body_text = ''
            
            # Parse date
            date = None
            if date_str:
                try:
                    # This is a simplified approach - proper date parsing might need more work
                    date = datetime.datetime.strptime(date_str[:25], '%a, %d %b %Y %H:%M:%S')
                except ValueError:
                    # Fall back to current date if parsing fails
                    date = datetime.datetime.now()
            else:
                date = datetime.datetime.now()
            
            return {
                'id': message['id'],
                'thread_id': message.get('threadId', ''),
                'subject': subject,
                'sender': sender,
                'date': date,
                'body_html': body_html or '',
                'body_text': body_text or '',
                'headers': headers
            }
        except Exception:
            # Return a minimal content that won't cause errors
            return {
                'id': message.get('id', 'unknown'),
                'thread_id': message.get('threadId', ''),
                'subject': '',
                'sender': '',
                'date': datetime.datetime.now(),
                'body_html': '',
                'body_text': '',
                'headers': []
            }
    
    def _get_parts(self, payload):
        """Recursively extract all parts from message payload"""
        parts = []
        
        # If this part has a body
        if 'body' in payload and 'data' in payload['body']:
            parts.append(payload)
        
        # If this part has sub-parts
        if 'parts' in payload:
            for part in payload['parts']:
                parts.extend(self._get_parts(part))
        
        return parts
    
    def find_matching_emails(self, rules, processed_emails=None, ignored_emails=None, months_back=3, debug=False):
        """Search for emails matching the rules
        
        Args:
            rules (list): List of rules to match against
            processed_emails (list, optional): List of already processed email IDs
            ignored_emails (list, optional): List of ignored email IDs
            months_back (int, optional): Number of months to look back
            debug (bool, optional): Enable additional debug output
            
        Returns:
            list: Matched emails with their matching rule
        """
        if processed_emails is None:
            processed_emails = []
            
        if ignored_emails is None:
            ignored_emails = []
        
        # Get emails from the last N months
        start_date = (datetime.datetime.now() - datetime.timedelta(days=30 * months_back)).strftime('%Y/%m/%d')
        
        matching_emails = []
        
        # Process each rule with its own targeted search query
        for rule in rules:
            print(f"\nChecking rule: sender='{rule.get('sender', 'any')}', subject='{rule.get('subject', 'any')}'")
            
            # Show body_contains criteria if present
            if rule.get('body_contains'):
                if isinstance(rule['body_contains'], list):
                    body_terms = "', '".join(rule['body_contains'])
                    print(f"Body must contain ALL: '{body_terms}'")
                else:
                    print(f"Body must contain: '{rule['body_contains']}'")
            
            # Build a specific query for each rule
            query_parts = [f'after:{start_date}']
            
            if rule.get('sender'):
                query_parts.append(f'from:{rule["sender"]}')
            
            # For subject, don't use subject: prefix as it's too restrictive
            # Instead, just search for the term in all email content
            # if rule.get('subject'):
            #     query_parts.append(f'subject:"{rule["subject"]}"')
            
            query = ' '.join(query_parts)
            
            print(f"Search query: {query}")
            
            try:
                # Search using the rule-specific query
                messages = self.search_emails(query, max_results=1000)
                
                if not messages:
                    print("No matching emails found for this rule.")
                    continue
                    
                print(f"Found {len(messages)} potential matches for this rule. Processing...")
                
                # Print first few subjects if debugging
                if debug and messages:
                    print("First few matching emails:")
                    for i, msg in enumerate(messages[:5]):
                        try:
                            msg_data = self.get_email(msg['id'])
                            content = self.get_email_content(msg_data)
                            print(f"  {i+1}. Subject: '{content.get('subject', 'No subject')}' from {content.get('sender', 'unknown')}")
                        except Exception as e:
                            print(f"  {i+1}. Error getting details: {str(e)}")
                
                rule_matches = 0
                
                for message in messages:
                    message_id = message['id']
                    
                    # Skip if already processed or ignored
                    if message_id in processed_emails or message_id in ignored_emails:
                        continue
                    
                    # Get full message details
                    message_data = self.get_email(message_id)
                    
                    # Extract content for matching
                    email_content = self.get_email_content(message_data)
                    
                    # We've already filtered by sender in the API query,
                    # but we need to check subject and body_contains manually
                    matches = True
                    
                    # Check subject if specified in the rule
                    if rule.get('subject'):
                        subject = email_content.get('subject', '')
                        if not subject or rule['subject'] not in subject:
                            matches = False
                            if debug:
                                print(f"Subject mismatch: '{rule['subject']}' not found in '{subject}'")
                            continue
                        elif debug:
                            print(f"Subject match: '{rule['subject']}' found in '{subject}'")
                    
                    # Check body_contains criteria
                    if matches and rule.get('body_contains'):
                        body_text = email_content.get('body_text', '')
                        body_html = email_content.get('body_html', '')

                        # Convert single string to list for consistent handling
                        required_terms = rule['body_contains']
                        if isinstance(required_terms, str):
                            required_terms = [required_terms]
                        
                        # Check if all terms are in either body_text or body_html
                        for term in required_terms:
                            text_match = body_text and term in body_text
                            html_match = body_html and term in body_html
                            
                            if not (text_match or html_match):
                                matches = False
                                if debug:
                                    print(f"Body content mismatch: '{term}' not found in email body")
                                    # Print a more substantial preview of the body content
                                    print(f"Email subject: {email_content.get('subject', 'No subject')}")
                                    if body_text:
                                        print(f"Text body preview (first 200 chars): {body_text[:200].replace('\n', ' ')}...")
                                    if body_html:
                                        html_preview = body_html.replace('\n', ' ').replace('\r', '')
                                        html_preview = ' '.join(html_preview.split())  # Normalize whitespace
                                        print(f"HTML body preview (first 200 chars): {html_preview[:200]}...")
                                break
                    
                    if matches:
                        print(f">>> MATCH FOUND: {email_content['subject']} from {email_content['sender']}")
                        rule_matches += 1
                        matching_emails.append({
                            'email': email_content,
                            'rule': rule
                        })
                
                print(f"Found {rule_matches} matching emails for this rule.")
                
            except Exception as e:
                print(f"Error processing rule: {str(e)}")
        
        # Sort matching emails by date (newest first)
        matching_emails.sort(key=lambda x: x['email'].get('date', datetime.datetime.now()), reverse=True)
        
        return matching_emails
    
    def _email_matches_rule(self, email, rule, debug=False):
        """Check if an email matches a rule
        
        Args:
            email (dict): Email content with subject, sender, body_text, body_html
            rule (dict): Rule with sender, subject, and body_contains criteria
            debug (bool, optional): Enable additional debug output
            
        Returns:
            bool: True if the email matches the rule
        """
        # Debug output tracking
        if not hasattr(self, 'debug_count'):
            self.debug_count = 0
            
        should_debug = debug and self.debug_count < 15
        debug_prefix = f"[DEBUG {self.debug_count}]" if should_debug else ""
        
        # Always show debug info for emails with specific senders we're looking for if debugging is on
        if debug and rule.get('sender') and rule['sender'] in email.get('sender', ''):
            should_debug = True
            debug_prefix = f"[SENDER-MATCH]"
            
        if should_debug:
            self.debug_count += 1
            email_snippet = f"Email: '{email.get('subject', '')}' from '{email.get('sender', '')}'"
            rule_desc = f"Rule: sender='{rule.get('sender', 'any')}', subject='{rule.get('subject', 'any')}'"
            print(f"{debug_prefix} Checking {email_snippet} against {rule_desc}")
        
        # Check sender
        if rule.get('sender'):
            sender = email.get('sender', '')
            if not sender or rule['sender'] not in sender:
                if should_debug:
                    print(f"{debug_prefix} Sender mismatch: '{rule['sender']}' not in '{sender}'")
                return False
            elif should_debug:
                print(f"{debug_prefix} Sender match: '{rule['sender']}' found in '{sender}'")
        
        # Check subject
        if rule.get('subject'):
            subject = email.get('subject', '')
            if not subject or rule['subject'] not in subject:
                if should_debug:
                    print(f"{debug_prefix} Subject mismatch: '{rule['subject']}' not in '{subject}'")
                return False
            elif should_debug:
                print(f"{debug_prefix} Subject match: '{rule['subject']}' found in '{subject}'")
        
        # Check body content
        if rule.get('body_contains'):
            body_text = email.get('body_text', '')
            body_html = email.get('body_html', '')
            
            # Convert single string to list for consistent handling
            required_terms = rule['body_contains']
            if isinstance(required_terms, str):
                required_terms = [required_terms]
            
            # Check if all terms are in either body_text or body_html
            for term in required_terms:
                text_match = body_text and term in body_text
                html_match = body_html and term in body_html
                
                if not (text_match or html_match):
                    if should_debug:
                        print(f"{debug_prefix} Body content mismatch: '{term}' not found in email body")
                        # Show first 100 chars of body for debugging
                        body_preview = (body_text or body_html or "")[:100].replace("\n", " ") + "..."
                        print(f"{debug_prefix} Body preview: {body_preview}")
                    return False
                elif should_debug:
                    print(f"{debug_prefix} Body content match: '{term}' found in email body")
            
            # If we made it here, all terms matched
            if should_debug:
                print(f"{debug_prefix} ALL CRITERIA MATCHED - THIS IS A MATCH!")
            return True
        
        # If we get here and there was no body_contains check,
        # the email matches based on sender and subject
        if should_debug:
            print(f"{debug_prefix} No body_contains criteria, matching based on sender/subject only - THIS IS A MATCH!")
        return True
    
    def _get_header_value(self, email, header_name):
        """Extract a header value from an email
        
        Args:
            email (dict): Email details
            header_name (str): Name of the header to extract
            
        Returns:
            str: Header value or empty string if not found
        """
        if 'headers' not in email:
            return ""
            
        for header in email['headers']:
            if header['name'].lower() == header_name.lower():
                return header['value']
                
        return "" 