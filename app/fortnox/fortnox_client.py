import requests
import datetime
import json
import time
from pathlib import Path
from urllib.parse import urlencode
import os

class FortnoxClient:
    def __init__(self, client_id, client_secret, redirect_uri=None, base_url='https://api.fortnox.se/3', token_file=None):
        """Initialize Fortnox client with OAuth2 credentials
        
        Args:
            client_id (str): The client ID from the Fortnox developer portal
            client_secret (str): The client secret from the Fortnox developer portal
            redirect_uri (str, optional): The redirect URI registered in the Fortnox developer portal
            base_url (str): The base URL for the Fortnox API
            token_file (str, optional): Path to file where tokens are stored
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.base_url = base_url
        self.token_file = token_file or str(Path(__file__).parent.parent / "config" / "fortnox_token.json")
        self.auth_url = "https://apps.fortnox.se/oauth-v1/auth"
        self.token_url = "https://apps.fortnox.se/oauth-v1/token"
        
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
            print(f"Error loading tokens: {e}")
    
    def _save_tokens(self):
        """Save access token and refresh token to file"""
        token_data = {
            'access_token': self.access_token,
            'refresh_token': self.refresh_token,
            'expires_at': self.token_expires_at
        }
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
        original_attachment_id = None
        attachment_data = {}
        
        try:
            # First upload attachment if provided
            attachment_id = None
            if attachment_path:
                print(f"Uploading attachment for voucher: {attachment_path}")
                # Try to upload file and get both attachment ID and full response
                result = self.upload_attachment_with_details(attachment_path)
                attachment_id = result.get('file_id')
                attachment_data = result.get('response_data', {})
                original_attachment_id = attachment_id
                print(f"Attachment uploaded successfully, ID: {attachment_id}")
            
            # Create voucher payload
            voucher_data = {
                "Voucher": {
                    "Description": description,
                    "TransactionDate": voucher_date,
                    "VoucherSeries": voucher_series,
                    "VoucherRows": []
                }
            }
            
            # Add voucher rows
            for entry in entries:
                row = {
                    "Account": entry["account"],
                    "Debit": entry["debit"],
                    "Credit": entry["credit"]
                }
                voucher_data["Voucher"]["VoucherRows"].append(row)
            
            # Send request to create voucher (without attachment first)
            url = f"{self.base_url}/vouchers"
            headers = self.get_headers()
            
            print(f"Creating voucher with payload: {voucher_data}")
            print(f"Sending request to: {url}")
            
            response = requests.post(url, headers=headers, json=voucher_data)
            
            print(f"Voucher creation response status: {response.status_code}")
            print(f"Voucher creation response: {response.text}")
            
            if response.status_code not in (200, 201):
                raise Exception(f"Failed to create voucher: Status {response.status_code} - {response.text}")
            
            result = response.json()
            
            # If we have an attachment, attach it to the voucher in a separate request
            if attachment_id:
                try:
                    voucher_number = result['Voucher']['VoucherNumber']
                    voucher_series = result['Voucher']['VoucherSeries']
                    voucher_year = result['Voucher'].get('Year', datetime.datetime.now().year)
                    
                    print(f"Attaching file to voucher {voucher_series}{voucher_number}...")
                    
                    # Use the correct endpoint and payload structure based on Fortnox documentation
                    attachment_url = f"{self.base_url}/voucherfileconnections"
                    attachment_payload = {
                        "VoucherFileConnection": {
                            "FileId": attachment_id,
                            "VoucherNumber": str(voucher_number),
                            "VoucherSeries": voucher_series
                        }
                    }
                    
                    print(f"Attachment connection payload: {attachment_payload}")
                    
                    attachment_response = requests.post(
                        attachment_url,
                        headers=self.get_headers(),
                        json=attachment_payload
                    )
                    
                    print(f"Attachment connection response status: {attachment_response.status_code}")
                    print(f"Attachment connection response text: {attachment_response.text}")
                    
                    if attachment_response.status_code not in (200, 201, 204):
                        print(f"Warning: Failed to connect attachment to voucher: {attachment_response.text}")
                        
                        # Try alternative method if this one failed
                        print("Trying alternative attachment method...")
                        # Use fileconnections endpoint instead, which is also a valid way to connect files
                        alt_attachment_url = f"{self.base_url}/fileconnections"
                        alt_attachment_payload = {
                            "FileConnection": {
                                "FileId": attachment_id,
                                "ObjectId": f"{voucher_series}{voucher_number}",
                                "ObjectType": "Voucher"
                            }
                        }
                        
                        alt_attachment_response = requests.post(
                            alt_attachment_url,
                            headers=self.get_headers(),
                            json=alt_attachment_payload
                        )
                        
                        print(f"Alternative attachment method response: {alt_attachment_response.status_code}")
                        print(f"Alternative attachment method response text: {alt_attachment_response.text}")
                        
                        if alt_attachment_response.status_code not in (200, 201, 204):
                            print(f"Warning: Alternative attachment method also failed: {alt_attachment_response.text}")
                            # Continue anyway, the voucher was created successfully
                        else:
                            print("Alternative attachment method succeeded!")
                    else:
                        print("Successfully attached file to voucher!")
                except Exception as e:
                    print(f"Warning: Failed to attach file to voucher: {str(e)}")
                    # Continue anyway, the voucher was created successfully
            
            print(f"Voucher created successfully: {result}")
            return result
            
        except Exception as e:
            error_msg = str(e)
            detailed_error = f"Voucher creation failed: {error_msg}"
            print(detailed_error)
            raise Exception(detailed_error)
            
    def upload_attachment_with_details(self, file_path):
        """Upload file to Fortnox and return both the file ID and full response data
        
        Args:
            file_path (str): Path to file
            
        Returns:
            dict: Contains 'file_id' and 'response_data'
            
        Raises:
            Exception: If upload fails
        """
        try:
            print(f"Attempting to upload file: {file_path}")
            
            # Check if file exists
            if not os.path.exists(file_path):
                raise Exception(f"File not found: {file_path}")
                
            # Get file size
            file_size = os.path.getsize(file_path)
            print(f"File size: {file_size} bytes")
            
            if file_size == 0:
                raise Exception(f"File is empty: {file_path}")
                
            # Check file extension
            file_ext = os.path.splitext(file_path)[1].lower()
            supported_extensions = ['.pdf', '.jpeg', '.jpg', '.png', '.tiff', '.txt', '.rtf', '.doc', '.docx', '.xls', '.xlsx']
            
            if file_ext not in supported_extensions:
                print(f"WARNING: File extension '{file_ext}' may not be supported by Fortnox API.")
                print(f"Supported file types: {', '.join(supported_extensions)}")
            
            # Upload file
            url = f"{self.base_url}/archive"
            
            with open(file_path, 'rb') as f:
                file_content = f.read()
                
            files = {'file': (os.path.basename(file_path), file_content)}
            print(f"Uploading file with name: {os.path.basename(file_path)}")
            
            response = requests.post(url, headers=self.get_headers(with_content_type=False), files=files)
            
            print(f"Upload response status: {response.status_code}")
            
            if response.status_code not in (200, 201):
                print(f"Upload failed: {response.text}")
                raise Exception(f"Failed to upload file: {response.text}")
                
            response_json = response.json()
            print(f"Upload response: {response_json}")
            
            # Dictionary to hold both the file ID and complete response
            result = {
                'file_id': None,
                'response_data': response_json
            }
            
            # Try to extract file ID from different response formats
            if 'File' in response_json:
                file_obj = response_json['File']
                
                # For voucherfileconnections we need the Id (not ArchiveFileId)
                file_id = file_obj.get('Id')
                
                if file_id:
                    print(f"Successfully uploaded file with ID: {file_id} (from File object)")
                    result['file_id'] = file_id
                    
                    # Store both IDs just in case
                    result['archive_file_id'] = file_obj.get('ArchiveFileId')
                    return result
                    
                # Fall back to ArchiveFileId if Id is not available
                archive_file_id = file_obj.get('ArchiveFileId')
                if archive_file_id:
                    print(f"Successfully uploaded file with ArchiveFileID: {archive_file_id} (from File object)")
                    result['file_id'] = archive_file_id
                    return result
            
            if 'Attachment' in response_json and 'FileId' in response_json['Attachment']:
                file_id = response_json['Attachment']['FileId']
                print(f"Successfully uploaded file with ID: {file_id} (from Attachment object)")
                result['file_id'] = file_id
                return result
            
            # If we get here, we couldn't find a file ID in the response
            print(f"Unexpected response format: {response_json}")
            raise Exception(f"Could not find file ID in response: {response_json}")
            
        except Exception as e:
            print(f"Error in upload_attachment_with_details: {str(e)}")
            raise Exception(f"Failed to upload attachment: {str(e)}")
            
    def upload_attachment(self, file_path):
        """Upload file to Fortnox - legacy method that calls upload_attachment_with_details
        
        Args:
            file_path (str): Path to file
            
        Returns:
            str: File ID
            
        Raises:
            Exception: If upload fails
        """
        result = self.upload_attachment_with_details(file_path)
        return result['file_id']
    
    def get_voucher_series(self):
        """Get all available voucher series"""
        url = f"{self.base_url}/voucherseries"
        headers = self.get_headers()
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            raise Exception(f"Failed to get voucher series: {response.text}")
        
        return response.json()['VoucherSeriesCollection']['VoucherSeries']
    
    def get_chart_of_accounts(self):
        """Get the chart of accounts from Fortnox"""
        url = f"{self.base_url}/accounts"
        headers = self.get_headers()
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            raise Exception(f"Failed to get chart of accounts: {response.text}")
        
        return response.json()['Accounts']['Account']
    
    def check_api_access(self):
        """Check what API scopes we have access to
        
        This can help diagnose permission issues with the Fortnox API
        
        Returns:
            dict: Dictionary with results of each endpoint test
        """
        try:
            print("Checking API access and permissions...")
            
            # Try accessing various endpoints to see what we have access to
            endpoints_to_check = [
                ("/voucherseries", "Voucher series access"),
                ("/accounts", "Accounts access"),
                ("/archive", "Archive access (upload files)"),
                ("/companyinformation", "Company information access")
            ]
            
            print("\nAPI Access Check Results:")
            print("--------------------------")
            
            results = {}
            
            for endpoint, description in endpoints_to_check:
                url = f"{self.base_url}{endpoint}"
                try:
                    headers = self.get_headers()
                    response = requests.get(url, headers=headers)
                    
                    if response.status_code == 200:
                        print(f"✅ {description}: SUCCESS")
                        results[endpoint] = {
                            "success": True,
                            "status_code": response.status_code,
                            "description": description
                        }
                    else:
                        print(f"❌ {description}: FAILED - Status {response.status_code}")
                        error_detail = ""
                        if response.text:
                            error_detail = response.text
                            print(f"   Error: {response.text}")
                        
                        results[endpoint] = {
                            "success": False,
                            "status_code": response.status_code,
                            "description": description,
                            "error": error_detail
                        }
                except Exception as e:
                    print(f"❌ {description}: ERROR - {str(e)}")
                    results[endpoint] = {
                        "success": False,
                        "error": str(e),
                        "description": description
                    }
            
            # Calculate overall success rate
            success_count = sum(1 for result in results.values() if result.get("success", False))
            success_percentage = (success_count / len(endpoints_to_check)) * 100
            print(f"\nAccess check complete: {success_count}/{len(endpoints_to_check)} endpoints accessible ({success_percentage:.1f}%)")
            
            # Check if we have bookkeeping and archive scopes
            if results.get("/accounts", {}).get("success", False) and results.get("/voucherseries", {}).get("success", False):
                print("✅ Bookkeeping scope appears to be granted")
            else:
                print("❌ Bookkeeping scope may be missing")
                
            if results.get("/archive", {}).get("success", False):
                print("✅ Archive scope appears to be granted")
            else:
                print("❌ Archive scope may be missing")
            
            print("\nDone checking API access")
            return results
            
        except Exception as e:
            error_message = f"Failed to check API access: {str(e)}"
            print(error_message)
            return {"error": error_message}
            
    def test_connection(self):
        """Test the connection to Fortnox API
        
        Tests basic connectivity, authentication and API permissions.
        
        Returns:
            dict: Connection test results including success status and detailed information
            
        Raises:
            Exception: If connection fails and raise_error is True
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
            print("Testing connection to Fortnox API...")
            
            # First check if we can authenticate
            if not self.ensure_auth():
                raise Exception("Authentication failed. No valid access token available.")
            
            test_results["authenticated"] = True
            print("✅ Authentication successful")
            
            # Try a simple API call
            url = f"{self.base_url}/companyinformation"
            response = requests.get(url, headers=self.get_headers())
            
            # Print response for debugging
            print(f"Fortnox company info response: {response.status_code}")
            
            if response.status_code != 200:
                raise Exception(f"Failed to connect to Fortnox: Status {response.status_code} - {response.text}")
            
            # Save company info in results
            company_info = response.json().get("CompanyInformation", {})
            test_results["company_info"] = company_info
            print(f"✅ Connected to Fortnox company: {company_info.get('Name', 'Unknown')}")
                
            # Check API access while we're at it
            api_access_results = self.check_api_access()
            test_results["api_access"] = api_access_results
            
            # Set overall success
            test_results["success"] = True
            return test_results
            
        except Exception as e:
            error_message = f"Fortnox connection test failed: {str(e)}"
            print(f"❌ {error_message}")
            test_results["error"] = error_message
            raise Exception(error_message)
            
    def is_authenticated(self):
        """Check if we have a valid access token
        
        Returns:
            bool: True if we have a valid access token
        """
        return self.ensure_auth() 