import os
from supabase import create_client, Client
from datetime import datetime, date
import logging
import time

logger = logging.getLogger(__name__)

class SupabaseClient:
    def __init__(self):
        self.url = os.getenv('SUPABASE_URL')
        self.key = os.getenv('SUPABASE_KEY')
        self.client: Client = create_client(self.url, self.key)
        self.max_retries = 3
    
    def init_db(self):
        """Initialize database - tables are created via SQL"""
        try:
            # Test connection
            self.client.table('leave_requests').select('id').limit(1).execute()
            logger.info("Database connection successful")
            return True
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            return False
    
    def create_leave_request(self, user_id, user_name, start_date, end_date, reason, leave_type):
        """Create a new leave request"""
        for attempt in range(self.max_retries):
            try:
                data = {
                    'user_id': user_id,
                    'user_name': user_name,
                    'start_date': start_date,
                    'end_date': end_date,
                    'reason': reason,
                    'leave_type': leave_type,
                    'status': 'pending',
                    'created_at': datetime.now().isoformat()
                }
                response = self.client.table('leave_requests').insert(data).execute()
                return response.data[0] if response.data else None
            except Exception as e:
                if attempt == self.max_retries - 1:
                    logger.error(f"Error creating leave request: {e}")
                    return None
                time.sleep(1)
    
    def get_leave_request(self, request_id):
        """Get a specific leave request"""
        try:
            response = self.client.table('leave_requests').select('*').eq('id', request_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error getting leave request: {e}")
            return None
    
    def update_leave_request_status(self, request_id, status, approved_by=None):
        """Update leave request status"""
        try:
            data = {
                'status': status,
                'updated_at': datetime.now().isoformat()
            }
            if approved_by:
                data['approved_by'] = approved_by
            
            response = self.client.table('leave_requests').update(data).eq('id', request_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error updating leave request: {e}")
            return None
    
    def get_user_leave_balance(self, user_id):
        """Get user's leave balance"""
        try:
            response = self.client.table('user_leave_balances').select('*').eq('user_id', user_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error getting leave balance: {e}")
            return None
    
    def update_user_leave_balance(self, user_id, leave_type, days):
        """Update user's leave balance"""
        try:
            current = self.get_user_leave_balance(user_id)
            if current:
                new_balance = current.get(leave_type, 0) + days
                response = self.client.table('user_leave_balances').update({
                    leave_type: new_balance,
                    'updated_at': datetime.now().isoformat()
                }).eq('user_id', user_id).execute()
            else:
                data = {
                    'user_id': user_id,
                    leave_type: max(0, days),
                    'created_at': datetime.now().isoformat()
                }
                response = self.client.table('user_leave_balances').insert(data).execute()
            
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error updating leave balance: {e}")
            return None
    
    def get_todays_leaves(self):
        """Get all leaves for today"""
        try:
            today = date.today().isoformat()
            response = self.client.table('leave_requests').select('*').eq('start_date', today).eq('status', 'approved').execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting today's leaves: {e}")
            return []
    
    def get_user_leave_requests(self, user_id):
        """Get all leave requests for a user"""
        try:
            response = self.client.table('leave_requests').select('*').eq('user_id', user_id).order('created_at', desc=True).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting user leave requests: {e}")
            return []