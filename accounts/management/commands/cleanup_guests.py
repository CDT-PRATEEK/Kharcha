from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from django.db.models import Q 

User = get_user_model()

class Command(BaseCommand):
    help = 'Safely deletes inactive guest users (No email + inactive > 24hrs)'

    def handle(self, *args, **kwargs):
        # 1.  (24 hours ago)
        cutoff_date = timezone.now() - timedelta(hours=24)

        
        old_guests = User.objects.filter(
            username__startswith='guest_',  
            email=''                        
        ).filter(
            
            Q(last_login__lt=cutoff_date) | 
            Q(last_login__isnull=True, date_joined__lt=cutoff_date)
        )

        count = old_guests.count()

        # 3. Delete
        if count > 0:
            old_guests.delete() 
            self.stdout.write(self.style.SUCCESS(f'Successfully cleaned up {count} abandoned guest accounts.'))
        else:
            self.stdout.write(self.style.SUCCESS('No abandoned guest accounts found.'))