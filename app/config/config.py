import os
import json
from dotenv import load_dotenv
from pathlib import Path

def load_config():
    """Load configuration from .env file and config.json"""
    load_dotenv()
    
    # Define default config path
    config_dir = Path(__file__).parent
    config_path = config_dir / "config.json"
    
    # Load config from JSON if it exists
    if config_path.exists():
        with open(config_path, 'r') as f:
            config = json.load(f)
    else:
        config = {}
    
    # Environment variables override JSON config
    config.update({
        'gmail': {
            'credentials_file': os.getenv('GMAIL_CREDENTIALS_FILE', config.get('gmail', {}).get('credentials_file', 'credentials.json')),
            'token_file': os.getenv('GMAIL_TOKEN_FILE', config.get('gmail', {}).get('token_file', 'token.json')),
            'scopes': ['https://www.googleapis.com/auth/gmail.readonly'],
        },
        'fortnox': {
            'client_id': os.getenv('FORTNOX_CLIENT_ID', config.get('fortnox', {}).get('client_id')),
            'client_secret': os.getenv('FORTNOX_CLIENT_SECRET', config.get('fortnox', {}).get('client_secret')),
            'redirect_uri': os.getenv('FORTNOX_REDIRECT_URI', config.get('fortnox', {}).get('redirect_uri', 'http://localhost:8000/callback')),
            'base_url': os.getenv('FORTNOX_BASE_URL', config.get('fortnox', {}).get('base_url', 'https://api.fortnox.se/3')),
        },
        'email_rules': config.get('email_rules', [
            {
                'sender': 'no_reply@email.apple.com',
                'subject': '',
                'body_contains': 'iCloud+ med 6 TB lagrings­utrymme',  # Can be a string or a list of strings
                'accounting': {
                    'description': 'Apple iCloud',
                    'series': 'F',
                    'entries': [
                        {'account': '6540', 'debit': 319.20, 'credit': 0},
                        {'account': '2641', 'debit': 79.80, 'credit': 0},
                        {'account': '2820', 'debit': 0, 'credit': 399.00}
                    ]
                }
            }
        ])
    })
    
    return config

def save_config(config):
    """
    Save configuration to config.json file.
    
    Args:
        config (dict): Configuration dictionary to save
    """
    config_dir = Path(__file__).parent
    config_path = config_dir / "config.json"
    
    # Create a backup of the existing config
    if config_path.exists():
        backup_path = config_path.with_suffix('.json.bak')
        try:
            # Copy content rather than moving to preserve original in case of error
            with open(config_path, 'r') as src, open(backup_path, 'w') as dst:
                dst.write(src.read())
        except Exception as e:
            print(f"Warning: Failed to create backup of config: {str(e)}")
    
    # Save updated config
    try:
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving configuration: {str(e)}")
        return False

def get_processed_emails():
    """Load processed email IDs from file"""
    # Try both potential locations
    paths_to_check = [
        Path(__file__).parent / "processed_emails.json",  # New location
        Path(__file__).parent.parent / "data" / "processed_emails.json"  # Old location
    ]
    
    for path in paths_to_check:
        if path.exists():
            with open(path, 'r') as f:
                emails = json.load(f)
                return emails
    
    return []

def save_processed_email(email_id):
    """Save a processed email ID to file"""
    emails = get_processed_emails()
    if email_id not in emails:
        emails.append(email_id)
    
    # Ensure data directory exists
    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(exist_ok=True)
    
    # Save to the data directory
    emails_file = data_dir / "processed_emails.json"
    with open(emails_file, 'w') as f:
        json.dump(emails, f)

def get_ignored_emails():
    """Load ignored email IDs from file"""
    # Try both potential locations
    paths_to_check = [
        Path(__file__).parent / "ignored_emails.json",  # New location
        Path(__file__).parent.parent / "data" / "ignored_emails.json"  # Old location
    ]
    
    for path in paths_to_check:
        if path.exists():
            with open(path, 'r') as f:
                emails = json.load(f)
                return emails
    
    return []

def save_ignored_email(email_id):
    """Save an ignored email ID to file"""
    emails = get_ignored_emails()
    if email_id not in emails:
        emails.append(email_id)
    
    # Ensure data directory exists
    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(exist_ok=True)
    
    # Save to the data directory
    emails_file = data_dir / "ignored_emails.json"
    with open(emails_file, 'w') as f:
        json.dump(emails, f) 