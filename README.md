# Gmail to Fortnox Integration

A utility script that automates the process of finding specific emails in Gmail and creating accounting verifications in Fortnox. This can be used for instance to automatically add recurring company card charged to the accounting, or to take certain expenses and book them as a liability to yourself. I created this because Apple doesn't allow me to separate business expenses and private expenses when buying things in App Store and so on. The script was created almost entirely using Cursor's AI agent mode, so use it with care. If you make any improvements, feel free to submit them as a PR. If you like the script and find it useful, drop me a line.

## Features

- Connect to Gmail using OAuth2 authentication
- Connect to Fortnox using OAuth2 authentication
- Search for emails matching specific criteria (sender, subject, body content)
- Extract amounts from emails using regex patterns
- Calculate voucher entries dynamically using extracted values
- Convert matched emails to PDF
- Create verifications in Fortnox with the correct accounting entries
- Attach the email PDF to the Fortnox verification
- Track processed emails to avoid duplicates
- Console-based UI that guides the user through the process
- Interactive rule creation mode with pattern testing
- Extensible configuration for multiple email rules and accounting templates

## Requirements

- Python 3.7+
- Gmail account with API access
- Fortnox account with API access

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/gmail-to-fortnox.git
   cd gmail-to-fortnox
   ```

2. Create a virtual environment and install dependencies:
   ```
   # Using uv (recommended)
   uv venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   uv pip install -r requirements.txt
   
   # Or using pip
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Set up Gmail API credentials:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select an existing one
   - Enable the Gmail API
   - Create OAuth credentials (Desktop app)
   - Download the credentials JSON file and save it as `app/config/credentials.json`

4. Set up Fortnox API access:
   - Log in to your Fortnox account
   - Go to the developer portal in the menu (if you do not have a developer license activated you need to contact Fortnox support about this)
   - Create a new application
   - Set the redirect URI to `http://localhost:8000/callback`
   - Request API scopes for `voucher` and `archive`
   - Note your Client ID and Client Secret and add them to your configuration

5. Create a configuration file:
   - Copy the example config file: `cp config.example.json app/config/config.json`
   - Edit `app/config/config.json` with your Fortnox client ID and client secret
   - You can run `python main.py --create-rule` to interactively create a new config rule

## Usage

Run the script:
```
python main.py
```

The script will:
1. Connect to Gmail and search for matching emails (prompting for authentication if needed)
2. Connect to Fortnox (opening a browser for authentication if needed)
3. For each matching email, prompt for confirmation
4. Convert the email to PDF
5. Show the verification details that will be created in Fortnox
6. Create the verification in Fortnox (with your confirmation)
7. Mark the email as processed to avoid duplicate handling

## Authentication Flow

### Gmail Authentication
The first time you run the script, it will open a browser window asking you to sign in to your Google account and authorize the application to access your Gmail. After successful authorization, a token will be saved to `app/config/token.json` for future use.

### Fortnox Authentication
The first time you run the script, it will:
1. Open a browser window to the Fortnox authentication page
2. Start a local web server to receive the authorization callback
3. After you authorize the application in your browser, Fortnox will redirect to the callback URL
4. The application will exchange the authorization code for access and refresh tokens
5. The tokens will be saved to `app/config/fortnox_token.json` for future use

Both tokens will be automatically refreshed when they expire.

## Configuration

The `app/config/config.json` file allows you to configure:

- Gmail API credentials location
- Fortnox OAuth credentials and redirect URI
- Email rules that define what to look for in emails
- Data extraction patterns to extract values from emails
- Accounting formulas that define how to create verifications

Example configuration:
```json
{
  "gmail": {
    "credentials_file": "credentials.json",
    "token_file": "token.json",
    "scopes": ["https://www.googleapis.com/auth/gmail.readonly"]
  },
  "fortnox": {
    "client_id": "YOUR_CLIENT_ID",
    "client_secret": "YOUR_CLIENT_SECRET",
    "redirect_uri": "http://localhost:8000/callback",
    "base_url": "https://api.fortnox.se/3"
  },
  "email_rules": [
    {
      "sender": "no_reply@email.apple.com",
      "subject": "",
      "body_contains": "iCloud+",
      "data_extraction": {
        "total_amount": {
          "pattern": "(?:betalat|avgift|SEK|kr)[\\s:]*([0-9]+[,.]?[0-9]*)",
          "default": 399.00
        }
      },
      "accounting": {
        "description": "Apple iCloud",
        "series": "F",
        "entries": [
          {"account": "6540", "debit": "total_amount * 0.8", "credit": 0},
          {"account": "2641", "debit": "total_amount * 0.2", "credit": 0},
          {"account": "2820", "debit": 0, "credit": "total_amount"}
        ]
      }
    }
  ]
}
```

## Email Rule Configuration

In the `config.json` file, you can define rules to match emails:

```json
"email_rules": [
  {
    "sender": "no_reply@email.apple.com",
    "subject": "",
    "body_contains": "iCloud+",
    "data_extraction": {
      "total_amount": {
        "pattern": "(?:betalat|avgift|SEK|kr)[\\s:]*([0-9]+[,.]?[0-9]*)",
        "default": 399.00
      }
    },
    "accounting": {
      "description": "Apple iCloud",
      "series": "F",
      "entries": [
        {"account": "6540", "debit": "total_amount * 0.8", "credit": 0},
        {"account": "2641", "debit": "total_amount * 0.2", "credit": 0},
        {"account": "2820", "debit": 0, "credit": "total_amount"}
      ]
    }
  }
]
```

### Rule Properties:

- **sender**: Email address of the sender to match (partial matching supported)
- **subject**: Text that must appear in the subject (partial matching supported)
- **body_contains**: Text that must appear in the email body. This can be:
  - A single string: `"body_contains": "Payment received"`
  - An array of strings (all must match): `"body_contains": ["Payment", "Invoice #123"]`
- **data_extraction**: Patterns to extract values from email content
  - Each key defines a variable name that can be used in formulas
  - **pattern**: Regex pattern with a capturing group to extract values from text
  - **html_pattern**: Optional regex pattern for matching against HTML content
  - **default**: Default value to use if no match is found
- **accounting**: Definition of how to create the voucher in Fortnox
  - **description**: Description for the voucher
  - **series**: Voucher series to use (e.g., "F")
  - **entries**: Array of accounting entries with:
    - **account**: Account number
    - **debit**: Debit amount or formula using extracted variables
    - **credit**: Credit amount or formula using extracted variables

## Interactive Rule Creation

You can create rules interactively by using the rule creation mode:

```
python main.py --create-rule
```

This mode allows you to:
1. Search for a sample email to use as a template
2. Test regex patterns directly against the email content
3. Define variables to extract from the email
4. Create accounting entries with formulas
5. Preview the resulting voucher
6. Save the rule to your configuration

Optional parameters:
- `--email-id=ID`: Use a specific Gmail message ID
- `--rule-file=FILE`: Load/save rule from/to a specific file
- `--debug`: Enable debug output

## Formula Syntax

In accounting entries, you can use formulas that reference extracted variables:

- Simple variable reference: `"debit": "total_amount"`
- Mathematical operations: `"debit": "amount * 0.8"`
- Percentage calculation: `"debit": "base_amount * (tax_percent/100)"`
- Addition/subtraction: `"credit": "price + shipping"`

All calculations are automatically rounded to two decimal places.

## License

MIT

Copyright 2025 Danni Efraim

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.