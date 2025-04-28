import requests
import datetime
import json
import time
from pathlib import Path
from urllib.parse import urlencode
import os

from app.accounting.base.base_client import BaseAccountingClient

class FortnoxClient(BaseAccountingClient):
    def __init__(self, client_id, client_secret, redirect_uri=None, base_url='https://api.fortnox.se/3', token_file=None, debug=False):
        """Initialize Fortnox client with OAuth2 credentials
        
        Args:
            client_id (str): The client ID from the Fortnox developer portal
            client_secret (str): The client secret from the Fortnox developer portal
            redirect_uri (str, optional): The redirect URI registered in the Fortnox developer portal
            base_url (str): The base URL for the Fortnox API
            token_file (str, optional): Path to file where tokens are stored
            debug (bool): Whether to enable debug output
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.base_url = base_url
        self.token_file = token_file or str(Path(__file__).parent.parent.parent / "config" / "fortnox_token.json")
        self.auth_url = "https://apps.fortnox.se/oauth-v1/auth"
        self.token_url = "https://apps.fortnox.se/oauth-v1/token"
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
            scopes = ['bookkeeping', 'archive', 'connectfile']
        
        # Join the scopes with a space
        scope_str = ' '.join(scopes)
        
        # Use urllib.parse to properly encode the query parameters
        auth_params = {
            'client_id': self.client_id,
            'scope': scope_str,
            'response_type': 'code',
            'redirect_uri': self.redirect_uri,
            'state': 'random_state'  # State parameter is required by Fortnox
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
            'redirect_uri': self.redirect_uri
        }
        
        # Basic auth with client_id and client_secret
        auth = (self.client_id, self.client_secret)
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json'
        }
        
        try:
            # Print the complete request for debugging
            if self.debug:
                print(f"Request to token endpoint:")
                print(f"  Headers: {headers}")
                print(f"  Auth: {auth}")
                print(f"  Payload: {payload}")
            
            # Use auth parameter for basic auth and data parameter for form data
            response = requests.post(
                self.token_url, 
                headers=headers,
                auth=auth,
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
            'refresh_token': self.refresh_token
        }
        
        # Basic auth with client_id and client_secret
        auth = (self.client_id, self.client_secret)
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json'
        }
        
        try:
            response = requests.post(
                self.token_url, 
                headers=headers,
                auth=auth,
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
            raise Exception("Not authenticated with Fortnox. Call get_authorization_url and fetch_tokens first.")
        
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Accept': 'application/json'
        }
        
        if with_content_type:
            headers['Content-Type'] = 'application/json'
        
        return headers
    
    def create_voucher(self, description, voucher_series, voucher_date, entries, attachment_path=None):
        """Create a new voucher in Fortnox
        
        Args:
            description (str): Description for the voucher
            voucher_series (str): Voucher series code (e.g., 'A', 'B', 'F')
            voucher_date (str): Date in format YYYY-MM-DD
            entries (list): List of voucher entries with account, debit, credit
            attachment_path (str, optional): Path to attachment file
        
        Returns:
            dict: Response from Fortnox API with voucher details
        """
        # Store the original attachment ID and file data
        attachment_id = None
        attachment_data = {}
        
        try:
            # First upload attachment if provided
            if attachment_path:
                if self.debug:
                    print(f"Uploading attachment for voucher: {attachment_path}")
                # Try to upload file and get both attachment ID and full response
                result = self.upload_attachment_with_details(attachment_path)
                attachment_id = result.get('file_id')
                
                if self.debug:
                    print(f"Uploaded attachment with ID: {attachment_id}")
            
            # Format voucher entries
            voucher_entries = []
            for entry in entries:
                voucher_entry = {
                    "Account": entry["account"],
                    "Debit": float(entry["debit"]) if entry["debit"] else 0,
                    "Credit": float(entry["credit"]) if entry["credit"] else 0,
                }
                voucher_entries.append(voucher_entry)
            
            # Create the voucher payload
            voucher_data = {
                "Description": description,
                "VoucherSeries": voucher_series,
                "TransactionDate": voucher_date,
                "VoucherRows": voucher_entries
            }
            
            # Add attachment reference if we have one
            if attachment_id:
                voucher_data["Attachments"] = [{"@url": f"{self.base_url}/fileattachments/{attachment_id}"}]
            
            # Format the final payload for Fortnox API
            payload = {"Voucher": voucher_data}
            
            if self.debug:
                print(f"Creating voucher with payload: {json.dumps(payload, indent=2)}")
            
            # Make the API request
            response = requests.post(
                f"{self.base_url}/vouchers",
                headers=self.get_headers(),
                json=payload
            )
            
            if self.debug:
                print(f"Voucher creation response status: {response.status_code}")
                print(f"Voucher creation response: {response.text}")
            
            response.raise_for_status()
            result = response.json()
            
            # Attach file if we have an attachment ID but it wasn't included in the voucher creation
            if attachment_id and "Attachments" not in voucher_data:
                voucher_number = result["Voucher"]["VoucherNumber"]
                voucher_series = result["Voucher"]["VoucherSeries"]
                
                connect_url = f"{self.base_url}/vouchers/{voucher_series}/{voucher_number}/attachments"
                connect_payload = {
                    "FileId": attachment_id
                }
                
                if self.debug:
                    print(f"Connecting attachment to voucher: {connect_url}")
                    print(f"Connect payload: {connect_payload}")
                
                connect_response = requests.post(
                    connect_url,
                    headers=self.get_headers(),
                    json=connect_payload
                )
                
                if self.debug:
                    print(f"Attachment connection response: {connect_response.status_code}")
                    print(f"Attachment connection response: {connect_response.text}")
                
                # Don't raise exception here - the voucher was created successfully
                
            return result
            
        except Exception as e:
            if self.debug:
                print(f"Error creating voucher: {e}")
            raise
    
    def upload_attachment_with_details(self, file_path):
        """Upload a file to Fortnox and return attachment details
        
        Args:
            file_path (str): Path to the file to upload
            
        Returns:
            dict: Dictionary with file_id, attachment_id and full response data
            
        Raises:
            Exception: If the upload fails
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
            
            # Set up headers - don't include Content-Type from get_headers()
            headers = self.get_headers(with_content_type=False)
            
            # Fortnox API requires a specific content type for the file
            headers['Content-Type'] = content_type
            
            # Upload file
            response = requests.post(
                f"{self.base_url}/archive",
                headers=headers,
                data=file_data
            )
            
            if self.debug:
                print(f"Upload response status: {response.status_code}")
                print(f"Upload response: {response.text}")
            
            response.raise_for_status()
            
            # Parse response
            result = response.json()
            
            # Extract file ID (might be in different formats)
            file_id = None
            if 'FileId' in result:
                file_id = result['FileId']
            elif 'Attachment' in result and 'FileId' in result['Attachment']:
                file_id = result['Attachment']['FileId']
            elif '@id' in result:
                file_id = result['@id']
            
            # Return combined result
            return {
                'file_id': file_id,
                'response_data': result
            }
            
        except Exception as e:
            if self.debug:
                print(f"Error uploading attachment: {e}")
            raise
    
    def upload_attachment(self, file_path):
        """Simple wrapper around upload_attachment_with_details that returns just the file ID
        
        Args:
            file_path (str): Path to the file to upload
            
        Returns:
            str: File ID
        """
        result = self.upload_attachment_with_details(file_path)
        return result.get('file_id')
    
    def get_voucher_series(self):
        """Get available voucher series
        
        Returns:
            list: List of voucher series
        """
        response = requests.get(f"{self.base_url}/voucherseries", headers=self.get_headers())
        response.raise_for_status()
        return response.json()["VoucherSeriesCollection"]["VoucherSeries"]
    
    def get_chart_of_accounts(self):
        """Get chart of accounts
        
        Returns:
            list: List of accounts
        """
        response = requests.get(f"{self.base_url}/accounts", headers=self.get_headers())
        response.raise_for_status()
        return response.json()["Accounts"]["Account"]
    
    def check_api_access(self):
        """Check API access permissions
        
        Returns:
            dict: Dictionary with access information for different areas
        """
        # Endpoint paths to test
        endpoints = {
            "vouchers": "/vouchers", 
            "chart_of_accounts": "/accounts",
            "archive": "/archive",
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
        """Test the connection to Fortnox API
        
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
                print("Testing connection to Fortnox API...")
            
            # First check if we can authenticate
            if not self.ensure_auth():
                raise Exception("Authentication failed. No valid access token available.")
            
            test_results["authenticated"] = True
            if self.debug:
                print("✅ Authentication successful")
            
            # Try a simple API call
            url = f"{self.base_url}/companyinformation"
            response = requests.get(url, headers=self.get_headers())
            
            # Print response for debugging
            if self.debug:
                print(f"Fortnox company info response: {response.status_code}")
            
            if response.status_code != 200:
                raise Exception(f"Failed to connect to Fortnox: Status {response.status_code} - {response.text}")
            
            # Save company info in results
            company_info = response.json().get("CompanyInformation", {})
            test_results["company_info"] = company_info
            if self.debug:
                print(f"✅ Connected to Fortnox company: {company_info.get('Name', 'Unknown')}")
                
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