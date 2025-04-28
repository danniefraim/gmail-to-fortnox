import os
import datetime
from pathlib import Path
from weasyprint import HTML

class PdfConverter:
    def __init__(self, output_dir=None):
        """Initialize the PDF converter with an output directory"""
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            self.output_dir = Path(__file__).parent.parent / "data" / "pdfs"
        
        # Create output directory if it doesn't exist
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def email_to_pdf(self, email_content):
        """Convert email content to PDF and save it
        
        Args:
            email_content: Dict containing email details
            
        Returns:
            Path to the saved PDF file
        """
        # Create a filename from email subject and ID
        subject = email_content.get('subject', 'No Subject')
        safe_subject = "".join(c for c in subject if c.isalnum() or c in ' -_').strip()
        safe_subject = safe_subject[:30]  # Limit length
        
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{safe_subject}_{timestamp}_{email_content['id'][:8]}.pdf"
        output_path = self.output_dir / filename
        
        # Create HTML content
        html_content = self._create_html_from_email(email_content)
        
        # Convert to PDF
        HTML(string=html_content).write_pdf(output_path)
        
        return output_path
    
    def _create_html_from_email(self, email):
        """Create HTML content from email data"""
        # If we have HTML content in the email, use it
        if email.get('body_html'):
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>{email.get('subject', 'Email')}</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; }}
                    .email-header {{ border-bottom: 1px solid #ddd; padding-bottom: 10px; margin-bottom: 20px; }}
                    .email-metadata {{ color: #666; font-size: 0.9em; }}
                </style>
            </head>
            <body>
                <div class="email-header">
                    <h2>{email.get('subject', 'No Subject')}</h2>
                    <div class="email-metadata">
                        <p><strong>From:</strong> {email.get('sender', 'Unknown')}</p>
                        <p><strong>Date:</strong> {email.get('date', datetime.datetime.now()).strftime('%Y-%m-%d %H:%M:%S')}</p>
                    </div>
                </div>
                <div class="email-content">
                    {email.get('body_html', '')}
                </div>
            </body>
            </html>
            """
        else:
            # Fall back to plain text
            text_content = email.get('body_text', 'No content')
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>{email.get('subject', 'Email')}</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; }}
                    .email-header {{ border-bottom: 1px solid #ddd; padding-bottom: 10px; margin-bottom: 20px; }}
                    .email-metadata {{ color: #666; font-size: 0.9em; }}
                    .email-content {{ white-space: pre-wrap; }}
                </style>
            </head>
            <body>
                <div class="email-header">
                    <h2>{email.get('subject', 'No Subject')}</h2>
                    <div class="email-metadata">
                        <p><strong>From:</strong> {email.get('sender', 'Unknown')}</p>
                        <p><strong>Date:</strong> {email.get('date', datetime.datetime.now()).strftime('%Y-%m-%d %H:%M:%S')}</p>
                    </div>
                </div>
                <div class="email-content">
                    {text_content}
                </div>
            </body>
            </html>
            """
        
        return html_content 