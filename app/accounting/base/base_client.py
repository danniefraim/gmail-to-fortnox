from abc import ABC, abstractmethod

class BaseAccountingClient(ABC):
    """Base class for all accounting system clients
    
    This abstract class defines the common interface that all accounting
    system clients must implement.
    """
    
    @abstractmethod
    def is_authenticated(self):
        """Check if the client is authenticated with the accounting system
        
        Returns:
            bool: True if authenticated, False otherwise
        """
        pass
    
    @abstractmethod
    def ensure_auth(self):
        """Ensure we have a valid access token/authentication
        
        Returns:
            bool: True if we have valid credentials, False otherwise
        """
        pass
    
    @abstractmethod
    def get_authorization_url(self, scopes=None):
        """Generate the authorization URL for OAuth flow
        
        Args:
            scopes (list, optional): List of scopes to request
            
        Returns:
            str: The authorization URL
        """
        pass
    
    @abstractmethod
    def fetch_tokens(self, authorization_code):
        """Exchange authorization code for tokens
        
        Args:
            authorization_code (str): The authorization code from the redirect
            
        Returns:
            bool: True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    def create_voucher(self, description, voucher_series, voucher_date, entries, attachment_path=None):
        """Create a voucher (financial entry) in the accounting system
        
        Args:
            description (str): Description of the voucher
            voucher_series (str): Voucher series code
            voucher_date (str): Date for the voucher in YYYY-MM-DD format
            entries (list): List of accounting entries
            attachment_path (str, optional): Path to attachment file
            
        Returns:
            dict: Created voucher information
        """
        pass
    
    @abstractmethod
    def get_voucher_series(self):
        """Get available voucher series
        
        Returns:
            list: List of voucher series
        """
        pass
    
    @abstractmethod
    def get_chart_of_accounts(self):
        """Get chart of accounts
        
        Returns:
            list: List of accounts
        """
        pass
    
    @abstractmethod
    def test_connection(self):
        """Test the connection to the accounting system
        
        Returns:
            dict: Connection test results
        """
        pass 