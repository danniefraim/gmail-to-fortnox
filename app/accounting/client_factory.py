from pathlib import Path

class AccountingClientFactory:
    """Factory for creating accounting system clients based on configuration
    
    This factory determines which accounting system client to create based on
    the configuration and returns the appropriate client instance.
    """
    
    @staticmethod
    def create_client(config, debug=False):
        """Create and return the appropriate accounting client
        
        Args:
            config (dict): The application configuration
            debug (bool): Whether to enable debug mode
            
        Returns:
            BaseAccountingClient: An instance of the appropriate accounting client
            
        Raises:
            ValueError: If the accounting system type is not supported or required config is missing
        """
        # Get the accounting system type from config, default to fortnox for backward compatibility
        accounting_type = config.get('accounting', {}).get('type', 'fortnox')
        
        if accounting_type == 'fortnox':
            from app.accounting.fortnox.fortnox_client import FortnoxClient
            
            fortnox_config = config['fortnox']
            
            # Validate required Fortnox parameters
            if not fortnox_config.get('client_id'):
                raise ValueError("Missing client_id in Fortnox configuration!")
                
            if not fortnox_config.get('client_secret'):
                raise ValueError("Missing client_secret in Fortnox configuration!")
            
            fortnox_token_file = Path(fortnox_config.get('token_file', 'fortnox_token.json'))
            
            if not fortnox_token_file.is_absolute():
                fortnox_token_file = Path(__file__).parent.parent / "config" / fortnox_token_file
            
            return FortnoxClient(
                client_id=fortnox_config['client_id'],
                client_secret=fortnox_config['client_secret'],
                redirect_uri=fortnox_config.get('redirect_uri', 'http://localhost:8000/callback'),
                base_url=fortnox_config['base_url'],
                token_file=str(fortnox_token_file),
                debug=debug
            )
            
        elif accounting_type == 'kleer':
            from app.accounting.kleer.kleer_client import KleerClient
            
            kleer_config = config['kleer']
            
            # Validate required Kleer parameters
            if not kleer_config.get('client_id'):
                raise ValueError("Missing client_id in Kleer configuration!")
                
            if not kleer_config.get('client_secret'):
                raise ValueError("Missing client_secret in Kleer configuration!")
            
            kleer_token_file = Path(kleer_config.get('token_file', 'kleer_token.json'))
            
            if not kleer_token_file.is_absolute():
                kleer_token_file = Path(__file__).parent.parent / "config" / kleer_token_file
            
            return KleerClient(
                client_id=kleer_config['client_id'],
                client_secret=kleer_config['client_secret'],
                redirect_uri=kleer_config.get('redirect_uri', 'http://localhost:8001/callback'),
                base_url=kleer_config.get('base_url', 'https://api.kleer.se'),
                token_file=str(kleer_token_file),
                debug=debug
            )
            
        else:
            raise ValueError(f"Unsupported accounting system type: {accounting_type}") 