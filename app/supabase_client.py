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
        self.retry_delay = 1
    
    def execute_with_retry(self, operation, *args, **kwargs):
        """Execute operation with retry logic"""
        for attempt in range(self.max_retries):
            try:
                return operation(*args, **kwargs)
            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise e
                logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying...")
                time.sleep(self.retry_delay * (attempt + 1))
    
    def init_db(self):
        """Initialize database tables if they don't exist"""
        try:
            # Read and execute schema SQL
            schema_path = os.path.join(os.path.dirname(__file__), 'database', 'init_schema.sql')
            with open(schema_path, 'r') as f:
                schema_sql = f.read()
            
            # Execute the schema SQL using Supabase's SQL execution
            # Note: This requires the service_role key for database operations
            response = self.client.rpc('exec_sql', {'query': schema_sql}).execute()
            logger.info("Database schema initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Error initializing database schema: {e}")
            # Fallback: Try to create tables individually
            return self.create_tables_individually()
    
    def create_tables_individually(self):
        """Create tables individually as fallback"""
        try:
            # This is a simplified fallback - in production, use migrations
            tables_created = []
            
            # Check and create leave_requests table
            try:
                self.client.table('leave_requests').select('*').limit(1).execute()
                logger.info("leave_requests table already exists")
            except:
                # Table doesn't exist, create it
                create_leave_requests = """
                CREATE TABLE IF NOT EXISTS leave_requests (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    user_name TEXT NOT NULL,
                    start_date DATE NOT NULL,
                    end_date DATE NOT NULL,
                    reason TEXT,
                    leave_type TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    approved_by TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );
                """
                self.client.rpc('exec_sql', {'query': create_leave_requests}).execute()
                tables_created.append('leave_requests')
            
            # Check and create user_leave_balances table
            try:
                self.client.table('user_leave_balances').select('*').limit(1).execute()
                logger.info("user_leave_balances table already exists")
            except:
                create_balances = """
                CREATE TABLE IF NOT EXISTS user_leave_balances (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT UNIQUE NOT NULL,
                    vacation INTEGER DEFAULT 20,
                    sick INTEGER DEFAULT 10,
                    personal INTEGER DEFAULT 5,
                    other INTEGER DEFAULT 3,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );
                """
                self.client.rpc('exec_sql', {'query': create_balances}).execute()
                tables_created.append('user_leave_balances')
            
            if tables_created:
                logger.info(f"Created tables: {', '.join(tables_created)}")
            
            return True
        except Exception as e:
            logger.error(f"Error in fallback table creation: {e}")
            return False
    
    def create_leave_request(self, user_id, user_name, start_date, end_date, reason, leave_type):
        """Create a new leave request"""
        def _create():
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
        
        return self.execute_with_retry(_create)
    
    def get_leave_request(self, request_id):
        """Get a specific leave request"""
        def _get():
            response = self.client.table('leave_requests').select('*').eq('id', request_id).execute()
            return response.data[0] if response.data else None
        
        return self.execute_with_retry(_get)
    
    def update_leave_request_status(self, request_id, status, approved_by=None):
        """Update leave request status"""
        def _update():
            data = {
                'status': status,
                'updated_at': datetime.now().isoformat()
            }
            if approved_by:
                data['approved_by'] = approved_by
            
            response = self.client.table('leave_requests').update(data).eq('id', request_id).execute()
            return response.data[0] if response.data else None
        
        return self.execute_with_retry(_update)
    
    def get_user_leave_balance(self, user_id):
        """Get user's leave balance"""
        def _get_balance():
            response = self.client.table('user_leave_balances').select('*').eq('user_id', user_id).execute()
            return response.data[0] if response.data else None
        
        return self.execute_with_retry(_get_balance)
    
    def update_user_leave_balance(self, user_id, leave_type, days):
        """Update user's leave balance"""
        def _update_balance():
            # Get current balance
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
                    leave_type: max(0, days),  # Ensure non-negative
                    'created_at': datetime.now().isoformat()
                }
                response = self.client.table('user_leave_balances').insert(data).execute()
            
            return response.data[0] if response.data else None
        
        return self.execute_with_retry(_update_balance)
    
    def get_todays_leaves(self):
        """Get all leaves for today"""
        def _get_todays():
            today = date.today().isoformat()
            response = self.client.table('leave_requests').select('*').eq('start_date', today).eq('status', 'approved').execute()
            return response.data
        
        return self.execute_with_retry(_get_todays)
    
    def get_user_leave_requests(self, user_id):
        """Get all leave requests for a user"""
        def _get_user_requests():
            response = self.client.table('leave_requests').select('*').eq('user_id', user_id).order('created_at', desc=True).execute()
            return response.data
        
        return self.execute_with_retry(_get_user_requests)
    
    def get_all_users_leave_balances(self):
        """Get leave balances for all users (admin function)"""
        def _get_all_balances():
            response = self.client.table('user_leave_balances').select('*').execute()
            return response.data
        
        return self.execute_with_retry(_get_all_balances)