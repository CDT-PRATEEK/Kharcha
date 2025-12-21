import base64
import json
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from django.core.mail.backends.base import BaseEmailBackend
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

class GmailAPIBackend(BaseEmailBackend):
    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently)
        self.service = None

    def open(self):
        if self.service: return True
        try:
            # Loading token from Render Environment
            token_data = os.environ.get('GMAIL_TOKEN_JSON')
            if not token_data: return False

            creds = Credentials.from_authorized_user_info(json.loads(token_data))
            self.service = build('gmail', 'v1', credentials=creds)
            return True
        except Exception as e:
            if not self.fail_silently: raise e
            return False

    def send_messages(self, email_messages):
        if not self.service:
            if not self.open(): return 0

        count = 0
        for message in email_messages:
            try:
                msg = MIMEMultipart('alternative')
                msg['to'] = ','.join(message.to)
                msg['from'] = message.from_email
                msg['subject'] = message.subject
                msg.attach(MIMEText(message.body, 'plain'))

                if hasattr(message, 'alternatives'):
                    for content, mimetype in message.alternatives:
                        if mimetype == 'text/html':
                            msg.attach(MIMEText(content, 'html'))

                raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
                self.service.users().messages().send(userId="me", body={'raw': raw}).execute()
                count += 1
            except:
                if not self.fail_silently: raise
        return count