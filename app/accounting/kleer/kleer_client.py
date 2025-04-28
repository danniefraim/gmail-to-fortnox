import requests
import datetime
import json
import time
from pathlib import Path
from urllib.parse import urlencode
import os

from app.accounting.base.base_client import BaseAccountingClient

class KleerClient(BaseAccountingClient):
    def __init__(self, client_id, client_secret, redirect_uri=None, base_url='https://api.kleer.se', token_file=None, debug=False):
        """Initialize Kleer client with OAuth2 credentials
        
        Args:
            client_id (str): The client ID from the Kleer developer portal
            client_secret (str): The client secret from the Kleer developer portal
            redirect_uri (str, optional): The redirect URI registered in the Kleer developer portal
            base_url (str): The base URL for the Kleer API
            token_file (str, optional): Path to file where tokens are stored
            debug (bool): Whether to enable debug output
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.base_url = base_url
        self.token_file = token_file or str(Path(__file__).parent.parent.parent / "config" / "kleer_token.json")
        self.auth_url = "https://auth.kleer.se/oauth/authorize"
        self.token_url = "https://auth.kleer.se/oauth/token"
        self.debug = debug
        
        # Try to load existing tokens
        self.access_token = None
        self.refresh_token = None
        self.token_expires_at = 0
        self._load_tokens()
    
    def _load_tokens(self):
        """Load access token and refresh token from file"""
        try:
            if Path(self.token_file).exists():
                with open(self.token_file, 'r') as f:
                    token_data = json.load(f)
                    self.access_token = token_data.get('access_token')
                    self.refresh_token = token_data.get('refresh_token')
                    self.token_expires_at = token_data.get('expires_at', 0)
        except Exception as e:
            if self.debug:
                print(f"Error loading tokens: {e}")
    
    def _save_tokens(self):
        """Save access token and refresh token to file"""
        token_data = {
            'access_token': self.access_token,
            'refresh_token': self.refresh_token,
            'expires_at': self.token_expires_at
        }
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.token_file), exist_ok=True)
        with open(self.token_file, 'w') as f:
            json.dump(token_data, f)
    
    def get_authorization_url(self, scopes=None):
        """Generate the authorization URL for the user to visit
        
        Args:
            scopes (list, optional): List of scopes to request
            
        Returns:
            str: The authorization URL
        """
        if scopes is None:
            # Use the specific scopes needed for our application
            # Adjust based on Kleer API documentation
            scopes = ['vouchers:read', 'vouchers:write', 'accounts:read', 'files:write']
        
        # Join the scopes with a space
        scope_str = ' '.join(scopes)
        
        # Use urllib.parse to properly encode the query parameters
        auth_params = {
            'client_id': self.client_id,
            'scope': scope_str,
            'response_type': 'code',
            'redirect_uri': self.redirect_uri,
            'state': 'random_state'  # State parameter for CSRF protection
        }
        
        # Use urlencode instead of manual string construction
        params = urlencode(auth_params)
        
        if self.debug:
            print(f"Auth params: {auth_params}")
            print(f"Encoded params: {params}")
        
        return f"{self.auth_url}?{params}"
    
    def fetch_tokens(self, authorization_code):
        """Exchange authorization code for tokens
        
        Args:
            authorization_code (str): The authorization code from the redirect
            
        Returns:
            bool: True if successful, False otherwise
        """
        # For debugging
        if self.debug:
            print(f"Fetching tokens with code: {authorization_code}")
            print(f"Token URL: {self.token_url}")
            print(f"Redirect URI: {self.redirect_uri}")
        
        # Form data must be properly formatted for x-www-form-urlencoded
        payload = {
            'grant_type': 'authorization_code',
            'code': authorization_code,
            'redirect_uri': self.redirect_uri,
            'client_id': self.client_id,
            'client_secret': self.client_secret
        }
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json'
        }
        
        try:
            # Print the complete request for debugging
            if self.debug:
                print(f"Request to token endpoint:")
                print(f"  Headers: {headers}")
                print(f"  Payload: {payload}")
            
            # Use data parameter for form data
            response = requests.post(
                self.token_url, 
                headers=headers,
                data=payload
            )
            
            # Print response for debugging
            if self.debug:
                print(f"Token response status: {response.status_code}")
                print(f"Token response: {response.text}")
            
            response.raise_for_status()
            
            token_data = response.json()
            self.access_token = token_data.get('access_token')
            self.refresh_token = token_data.get('refresh_token')
            expires_in = token_data.get('expires_in', 3600)
            self.token_expires_at = time.time() + expires_in
            
            self._save_tokens()
            return True
        except Exception as e:
            if self.debug:
                print(f"Error fetching tokens: {e}")
            return False
    
    def refresh_access_token(self):
        """Refresh the access token using the refresh token
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.refresh_token:
            return False
        
        payload = {
            'grant_type': 'refresh_token',
            'refresh_token': self.refresh_token,
            'client_id': self.client_id,
            'client_secret': self.client_secret
        }
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json'
        }
        
        try:
            response = requests.post(
                self.token_url, 
                headers=headers,
                data=payload
            )
            response.raise_for_status()
            
            token_data = response.json()
            self.access_token = token_data.get('access_token')
            # Some OAuth implementations refresh the refresh token too
            if 'refresh_token' in token_data:
                self.refresh_token = token_data.get('refresh_token')
            expires_in = token_data.get('expires_in', 3600)
            self.token_expires_at = time.time() + expires_in
            
            self._save_tokens()
            return True
        except Exception as e:
            if self.debug:
                print(f"Error refreshing tokens: {e}")
            return False
    
    def ensure_auth(self):
        """Ensure we have a valid access token
        
        Returns:
            bool: True if we have a valid token, False otherwise
        """
        # If token is expired or will expire in the next 60 seconds
        if time.time() > self.token_expires_at - 60:
            return self.refresh_access_token()
        return bool(self.access_token)
    
    def get_headers(self, with_content_type=True):
        """Get the headers for API requests
        
        Returns:
            dict: Headers with authorization
        """
        if not self.ensure_auth():
            raise Exception("Not authenticated with Kleer. Call get_authorization_url and fetch_tokens first.")
        
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Accept': 'application/json'
        }
        
        if with_content_type:
            headers['Content-Type'] = 'application/json'
        
        return headers
    
    def create_voucher(self, description, voucher_series, voucher_date, entries, attachment_path=None):
        """Create a new voucher in Kleer
        
        Args:
            description (str): Description for the voucher
            voucher_series (str): Voucher series code (e.g., 'A', 'B', 'F')
            voucher_date (str): Date in format YYYY-MM-DD
            entries (list): List of voucher entries with account, debit, credit
            attachment_path (str, optional): Path to attachment file
        
        Returns:
            dict: Response from Kleer API with voucher details
        """
        # Store the original attachment ID
        attachment_id = None
        
        try:
            # First upload attachment if provided
            if attachment_path:
                if self.debug:
                    print(f"Uploading attachment for voucher: {attachment_path}")
                # Try to upload file and get ID
                attachment_id = self.upload_attachment(attachment_path)
                
                if self.debug:
                    print(f"Uploaded attachment with ID: {attachment_id}")
            
            # Format voucher entries
            voucher_entries = []
            for entry in entries:
                voucher_entry = {
                    "accountNumber": entry["account"],
                    "debit": float(entry["debit"]) if entry["debit"] else 0,
                    "credit": float(entry["credit"]) if entry["credit"] else 0,
                }
                voucher_entries.append(voucher_entry)
            
            # Create the voucher payload - adapt to Kleer API format
            voucher_data = {
                "description": description,
                "seriesId": voucher_series,
                "transactionDate": voucher_date,
                "rows": voucher_entries
            }
            
            # Add attachment reference if we have one
            if attachment_id:
                voucher_data["attachmentIds"] = [attachment_id]
            
            if self.debug:
                print(f"Creating voucher with payload: {json.dumps(voucher_data, indent=2)}")
            
            # Make the API request
            response = requests.post(
                f"{self.base_url}/v1/vouchers",
                headers=self.get_headers(),
                json=voucher_data
            )
            
            if self.debug:
                print(f"Voucher creation response status: {response.status_code}")
                print(f"Voucher creation response: {response.text}")
            
            response.raise_for_status()
            result = response.json()
            
            return result
            
        except Exception as e:
            if self.debug:
                print(f"Error creating voucher: {e}")
            raise
    
    def upload_attachment(self, file_path):
        """Upload a file to Kleer
        
        Args:
            file_path (str): Path to the file to upload
            
        Returns:
            str: Attachment ID
        """
        try:
            # Check if file exists
            if not os.path.exists(file_path):
                raise Exception(f"File not found: {file_path}")
            
            # Get file name and size
            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            
            if self.debug:
                print(f"Uploading file: {file_name} ({file_size} bytes)")
            
            # Determine content type based on file extension
            file_ext = os.path.splitext(file_name)[1].lower()
            content_type = {
                '.pdf': 'application/pdf',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.txt': 'text/plain',
                '.doc': 'application/msword',
                '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                '.xls': 'application/vnd.ms-excel',
                '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            }.get(file_ext, 'application/octet-stream')
            
            # Read file
            with open(file_path, 'rb') as f:
                file_data = f.read()
            
            # Prepare multipart form data
            files = {
                'file': (file_name, file_data, content_type)
            }
            
            # Upload file - using multipart form data instead of direct binary upload
            response = requests.post(
                f"{self.base_url}/v1/attachments",
                headers=self.get_headers(with_content_type=False),
                files=files
            )
            
            if self.debug:
                print(f"Upload response status: {response.status_code}")
                print(f"Upload response: {response.text}")
            
            response.raise_for_status()
            
            # Parse response
            result = response.json()
            
            # Extract attachment ID
            attachment_id = result.get('id')
            
            return attachment_id
            
        except Exception as e:
            if self.debug:
                print(f"Error uploading attachment: {e}")
            raise
    
    def get_voucher_series(self):
        """Get available voucher series
        
        Returns:
            list: List of voucher series
        """
        response = requests.get(f"{self.base_url}/v1/series", headers=self.get_headers())
        response.raise_for_status()
        return response.json()
    
    def get_chart_of_accounts(self):
        """Get chart of accounts
        
        Returns:
            list: List of accounts
        """
        response = requests.get(f"{self.base_url}/v1/accounts", headers=self.get_headers())
        response.raise_for_status()
        return response.json()
    
    def check_api_access(self):
        """Check API access permissions
        
        Returns:
            dict: Dictionary with access information for different areas
        """
        # Endpoint paths to test
        endpoints = {
            "vouchers": "/v1/vouchers", 
            "chart_of_accounts": "/v1/accounts",
            "attachments": "/v1/attachments",
        }
        
        results = {}
        
        try:
            # Get headers with access token
            headers = self.get_headers()
            
            # Test each endpoint
            for key, path in endpoints.items():
                try:
                    # Use HEAD request to check access without retrieving data
                    response = requests.head(f"{self.base_url}{path}", headers=headers)
                    
                    # If we got a 405 Method Not Allowed, try GET instead (some endpoints don't support HEAD)
                    if response.status_code == 405:
                        response = requests.get(f"{self.base_url}{path}", headers=headers)
                    
                    # Check if request was successful
                    results[key] = {
                        "access": response.status_code < 400,
                        "status_code": response.status_code,
                        "details": "Access granted" if response.status_code < 400 else f"Access denied: {response.reason}"
                    }
                except Exception as e:
                    results[key] = {
                        "access": False,
                        "status_code": None,
                        "details": f"Error testing access: {str(e)}"
                    }
            
            # Check overall status
            all_accessible = all(item["access"] for item in results.values())
            
            return {
                "has_all_required_access": all_accessible,
                "endpoints": results
            }
        
        except Exception as e:
            if self.debug:
                print(f"Error checking API access: {e}")
            return {
                "has_all_required_access": False,
                "error": str(e),
                "endpoints": results
            }
    
    def test_connection(self):
        """Test the connection to Kleer API
        
        Tests basic connectivity, authentication and API permissions.
        
        Returns:
            dict: Connection test results including success status and detailed information
        """
        test_results = {
            "success": False,
            "authenticated": False,
            "api_access": None,
            "company_info": None,
            "error": None,
            "timestamp": datetime.datetime.now().isoformat()
        }
        
        try:
            if self.debug:
                print("Testing connection to Kleer API...")
            
            # First check if we can authenticate
            if not self.ensure_auth():
                raise Exception("Authentication failed. No valid access token available.")
            
            test_results["authenticated"] = True
            if self.debug:
                print("✅ Authentication successful")
            
            # Try a simple API call to get company information
            url = f"{self.base_url}/v1/company"
            response = requests.get(url, headers=self.get_headers())
            
            # Print response for debugging
            if self.debug:
                print(f"Kleer company info response: {response.status_code}")
            
            if response.status_code != 200:
                raise Exception(f"Failed to connect to Kleer: Status {response.status_code} - {response.text}")
            
            # Save company info in results
            company_info = response.json()
            test_results["company_info"] = company_info
            if self.debug:
                print(f"✅ Connected to Kleer company: {company_info.get('name', 'Unknown')}")
                
            # Check API access while we're at it
            api_access_results = self.check_api_access()
            test_results["api_access"] = api_access_results
            
            if api_access_results["has_all_required_access"]:
                if self.debug:
                    print("✅ API access check passed")
                test_results["success"] = True
            else:
                if self.debug:
                    print("❌ Missing some required API access")
                test_results["success"] = False
                test_results["error"] = "Missing required API access"
                
            return test_results
            
        except Exception as e:
            error_message = str(e)
            if self.debug:
                print(f"❌ Connection test failed: {error_message}")
            
            test_results["error"] = error_message
            return test_results
    
    def is_authenticated(self):
        """Check if the client is authenticated
        
        Returns:
            bool: True if authenticated, False otherwise
        """
        return bool(self.access_token) and time.time() < self.token_expires_at 