import os
import logging
from flask import Flask, jsonify
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from supabase_client import SupabaseClient
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, date
import threading

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
flask_app = Flask(__name__)

# Initialize Slack app with Socket Mode
slack_app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET")
)

# Initialize clients
supabase_client = SupabaseClient()

# Initialize scheduler
scheduler = BackgroundScheduler()

class SlackUtils:
    def __init__(self, supabase_client):
        self.supabase = supabase_client
        self.admin_user_id = os.getenv('ADMIN_USER_ID')
    
    def send_approval_request(self, leave_request):
        """Send DM to admin for approval"""
        try:
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "🚀 New Leave Request"
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*User:*\n{leave_request['user_name']}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Dates:*\n{leave_request['start_date']} to {leave_request['end_date']}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Type:*\n{leave_request['leave_type']}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Reason:*\n{leave_request['reason']}"
                        }
                    ]
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "✅ Approve"
                            },
                            "style": "primary",
                            "action_id": "approve_leave",
                            "value": str(leave_request['id'])
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "❌ Reject"
                            },
                            "style": "danger",
                            "action_id": "reject_leave",
                            "value": str(leave_request['id'])
                        }
                    ]
                }
            ]
            
            slack_app.client.chat_postMessage(
                channel=self.admin_user_id,
                blocks=blocks,
                text=f"New leave request from {leave_request['user_name']}"
            )
        except Exception as e:
            logger.error(f"Error sending approval request: {e}")
    
    def send_approval_notification(self, user_id, leave_request, approved=True):
        """Send notification to user about approval status"""
        try:
            status = "approved" if approved else "rejected"
            emoji = "✅" if approved else "❌"
            
            message = f"{emoji} Your leave request from {leave_request['start_date']} to {leave_request['end_date']} has been {status}."
            
            slack_app.client.chat_postMessage(
                channel=user_id,
                text=message
            )
        except Exception as e:
            logger.error(f"Error sending approval notification: {e}")
    
    def post_leave_announcement(self, channel, user_name, leave_date):
        """Post leave announcement to channel"""
        try:
            message = f"🏖️ {user_name} is on leave today ({leave_date})"
            
            slack_app.client.chat_postMessage(
                channel=channel,
                text=message
            )
        except Exception as e:
            logger.error(f"Error posting leave announcement: {e}")
    
    def create_leave_modal(self, trigger_id):
        """Create modal for leave request"""
        try:
            modal = {
                "type": "modal",
                "callback_id": "leave_request_modal",
                "title": {"type": "plain_text", "text": "Request Leave"},
                "submit": {"type": "plain_text", "text": "Submit"},
                "close": {"type": "plain_text", "text": "Cancel"},
                "blocks": [
                    {
                        "type": "section",
                        "block_id": "leave_type_section",
                        "text": {"type": "mrkdwn", "text": "Select leave type:"},
                        "accessory": {
                            "type": "static_select",
                            "action_id": "leave_type_select",
                            "placeholder": {"type": "plain_text", "text": "Select type"},
                            "options": [
                                {"text": {"type": "plain_text", "text": "Vacation"}, "value": "vacation"},
                                {"text": {"type": "plain_text", "text": "Sick Leave"}, "value": "sick"},
                                {"text": {"type": "plain_text", "text": "Personal"}, "value": "personal"},
                                {"text": {"type": "plain_text", "text": "Other"}, "value": "other"}
                            ]
                        }
                    },
                    {
                        "type": "input",
                        "block_id": "start_date",
                        "element": {"type": "datepicker", "action_id": "start_date_picker"},
                        "label": {"type": "plain_text", "text": "Start Date"}
                    },
                    {
                        "type": "input",
                        "block_id": "end_date",
                        "element": {"type": "datepicker", "action_id": "end_date_picker"},
                        "label": {"type": "plain_text", "text": "End Date"}
                    },
                    {
                        "type": "input",
                        "block_id": "reason",
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "reason_input",
                            "multiline": True,
                            "placeholder": {"type": "plain_text", "text": "Reason for leave"}
                        },
                        "label": {"type": "plain_text", "text": "Reason"}
                    }
                ]
            }
            
            slack_app.client.views_open(trigger_id=trigger_id, view=modal)
        except Exception as e:
            logger.error(f"Error creating leave modal: {e}")

# Initialize Slack utils
slack_utils = SlackUtils(supabase_client)

@flask_app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        db_status = "healthy"
        try:
            supabase_client.client.table('leave_requests').select('id').limit(1).execute()
        except Exception as e:
            db_status = f"unhealthy: {str(e)}"
        
        health_info = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "database": db_status,
            "scheduler": "running" if scheduler.running else "stopped",
            "version": "1.0.0"
        }
        
        return jsonify(health_info), 200
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 500

@flask_app.route("/ready", methods=["GET"])
def readiness_check():
    """Readiness check for Kubernetes"""
    try:
        supabase_client.client.table('leave_requests').select('id').limit(1).execute()
        return jsonify({"status": "ready"}), 200
    except Exception as e:
        return jsonify({"status": "not ready", "error": str(e)}), 503

# Slack command handlers
@slack_app.command("/request-leave")
def handle_leave_request(ack, body, client, logger):
    """Handle leave request command"""
    ack()
    try:
        user_id = body["user_id"]
        
        # Check if user is admin
        if user_id == os.getenv('ADMIN_USER_ID'):
            client.chat_postEphemeral(
                channel=body["channel_id"],
                user=user_id,
                text="Admins cannot request leaves through this command."
            )
            return
        
        # Open leave request modal
        slack_utils.create_leave_modal(body["trigger_id"])
    except Exception as e:
        logger.error(f"Error handling leave request: {e}")

@slack_app.command("/leave-balance")
def handle_leave_balance(ack, body, client, logger):
    """Handle leave balance check command"""
    ack()
    try:
        user_id = body["user_id"]
        balance = supabase_client.get_user_leave_balance(user_id)
        
        if balance:
            message = f"📊 Your Leave Balance:\n"
            message += f"• Vacation: {balance.get('vacation', 0)} days\n"
            message += f"• Sick Leave: {balance.get('sick', 0)} days\n"
            message += f"• Personal: {balance.get('personal', 0)} days\n"
            message += f"• Other: {balance.get('other', 0)} days"
        else:
            message = "No leave balance found. Please contact admin."
        
        client.chat_postEphemeral(
            channel=body["channel_id"],
            user=user_id,
            text=message
        )
    except Exception as e:
        logger.error(f"Error handling leave balance: {e}")

@slack_app.command("/admin-update-balance")
def handle_admin_update_balance(ack, body, client, logger):
    """Handle admin balance update command"""
    ack()
    try:
        user_id = body["user_id"]
        
        # Check if user is admin
        if user_id != os.getenv('ADMIN_USER_ID'):
            client.chat_postEphemeral(
                channel=body["channel_id"],
                user=user_id,
                text="This command is only available for admins."
            )
            return
        
        # Open admin modal for balance updates
        try:
            modal = {
                "type": "modal",
                "callback_id": "admin_update_modal",
                "title": {"type": "plain_text", "text": "Update Leave Balance"},
                "submit": {"type": "plain_text", "text": "Update"},
                "close": {"type": "plain_text", "text": "Cancel"},
                "blocks": [
                    {
                        "type": "input",
                        "block_id": "user_input",
                        "element": {
                            "type": "users_select",
                            "action_id": "user_select",
                            "placeholder": {"type": "plain_text", "text": "Select user"}
                        },
                        "label": {"type": "plain_text", "text": "User"}
                    },
                    {
                        "type": "section",
                        "block_id": "leave_type_section",
                        "text": {"type": "mrkdwn", "text": "Select leave type:"},
                        "accessory": {
                            "type": "static_select",
                            "action_id": "leave_type_select",
                            "placeholder": {"type": "plain_text", "text": "Select type"},
                            "options": [
                                {"text": {"type": "plain_text", "text": "Vacation"}, "value": "vacation"},
                                {"text": {"type": "plain_text", "text": "Sick Leave"}, "value": "sick"},
                                {"text": {"type": "plain_text", "text": "Personal"}, "value": "personal"},
                                {"text": {"type": "plain_text", "text": "Other"}, "value": "other"}
                            ]
                        }
                    },
                    {
                        "type": "input",
                        "block_id": "days_input",
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "days_input",
                            "placeholder": {"type": "plain_text", "text": "Enter number of days (use - to subtract)"}
                        },
                        "label": {"type": "plain_text", "text": "Days to add/subtract"}
                    }
                ]
            }
            
            client.views_open(trigger_id=body["trigger_id"], view=modal)
        except Exception as e:
            logger.error(f"Error opening admin modal: {e}")
            client.chat_postEphemeral(
                channel=body["channel_id"],
                user=user_id,
                text="Error opening admin panel. Please try again."
            )
    except Exception as e:
        logger.error(f"Error handling admin update: {e}")

@slack_app.command("/leave-history")
def handle_leave_history(ack, body, client, logger):
    """Handle leave history command"""
    ack()
    try:
        user_id = body["user_id"]
        leave_requests = supabase_client.get_user_leave_requests(user_id)
        
        if leave_requests:
            message = "📋 Your Leave History:\n"
            for req in leave_requests[:10]:  # Show last 10 requests
                status_emoji = "✅" if req['status'] == 'approved' else "⏳" if req['status'] == 'pending' else "❌"
                message += f"{status_emoji} {req['start_date']} to {req['end_date']} - {req['leave_type']} ({req['status']})\n"
        else:
            message = "No leave requests found."
        
        client.chat_postEphemeral(
            channel=body["channel_id"],
            user=user_id,
            text=message
        )
    except Exception as e:
        logger.error(f"Error handling leave history: {e}")

# Modal submission handlers
@slack_app.view("leave_request_modal")
def handle_modal_submission(ack, body, client, view, logger):
    """Handle leave request modal submission"""
    ack()
    try:
        user_id = body["user"]["id"]
        user_name = body["user"]["name"]
        
        # Extract form values
        values = view["state"]["values"]
        leave_type = values["leave_type_section"]["leave_type_select"]["selected_option"]["value"]
        start_date = values["start_date"]["start_date_picker"]["selected_date"]
        end_date = values["end_date"]["end_date_picker"]["selected_date"]
        reason = values["reason"]["reason_input"]["value"]
        
        # Create leave request
        leave_request = supabase_client.create_leave_request(
            user_id=user_id,
            user_name=user_name,
            start_date=start_date,
            end_date=end_date,
            reason=reason,
            leave_type=leave_type
        )
        
        if leave_request:
            # Send approval request to admin
            slack_utils.send_approval_request(leave_request)
            
            # Confirm to user
            client.chat_postMessage(
                channel=user_id,
                text=f"✅ Your leave request has been submitted and is pending approval."
            )
        else:
            client.chat_postMessage(
                channel=user_id,
                text="❌ Failed to submit leave request. Please try again."
            )
            
    except Exception as e:
        logger.error(f"Error handling modal submission: {e}")

@slack_app.view("admin_update_modal")
def handle_admin_modal_submission(ack, body, client, view, logger):
    """Handle admin update modal submission"""
    ack()
    try:
        admin_user_id = body["user"]["id"]
        
        # Extract form values
        values = view["state"]["values"]
        target_user_id = values["user_input"]["user_select"]["selected_user"]
        leave_type = values["leave_type_section"]["leave_type_select"]["selected_option"]["value"]
        days = int(values["days_input"]["days_input"]["value"])
        
        # Update user balance
        result = supabase_client.update_user_leave_balance(target_user_id, leave_type, days)
        
        if result:
            # Get user info for confirmation
            user_info = client.users_info(user=target_user_id)
            user_name = user_info["user"]["real_name"]
            
            client.chat_postMessage(
                channel=admin_user_id,
                text=f"✅ Updated {user_name}'s {leave_type} balance by {days} days."
            )
        else:
            client.chat_postMessage(
                channel=admin_user_id,
                text="❌ Failed to update balance. Please try again."
            )
            
    except Exception as e:
        logger.error(f"Error handling admin modal submission: {e}")

# Button action handlers
@slack_app.action("approve_leave")
def handle_approve_leave(ack, body, client, logger):
    """Handle leave approval"""
    ack()
    try:
        request_id = body["actions"][0]["value"]
        admin_user_id = body["user"]["id"]
        
        # Update leave request status
        leave_request = supabase_client.update_leave_request_status(
            request_id=request_id,
            status="approved",
            approved_by=admin_user_id
        )
        
        if leave_request:
            # Notify user
            slack_utils.send_approval_notification(
                user_id=leave_request["user_id"],
                leave_request=leave_request,
                approved=True
            )
            
            # Update response message
            client.chat_update(
                channel=body["container"]["channel_id"],
                ts=body["container"]["message_ts"],
                text=f"✅ Leave request approved by <@{admin_user_id}>"
            )
            
    except Exception as e:
        logger.error(f"Error approving leave: {e}")

@slack_app.action("reject_leave")
def handle_reject_leave(ack, body, client, logger):
    """Handle leave rejection"""
    ack()
    try:
        request_id = body["actions"][0]["value"]
        admin_user_id = body["user"]["id"]
        
        # Update leave request status
        leave_request = supabase_client.update_leave_request_status(
            request_id=request_id,
            status="rejected",
            approved_by=admin_user_id
        )
        
        if leave_request:
            # Notify user
            slack_utils.send_approval_notification(
                user_id=leave_request["user_id"],
                leave_request=leave_request,
                approved=False
            )
            
            # Update response message
            client.chat_update(
                channel=body["container"]["channel_id"],
                ts=body["container"]["message_ts"],
                text=f"❌ Leave request rejected by <@{admin_user_id}>"
            )
            
    except Exception as e:
        logger.error(f"Error rejecting leave: {e}")

def post_daily_leave_announcements():
    """Post daily leave announcements"""
    try:
        today = date.today().isoformat()
        leaves_today = supabase_client.get_todays_leaves()
        
        if leaves_today:
            # Post to a general channel
            channel = "#general"
            for leave in leaves_today:
                slack_utils.post_leave_announcement(
                    channel=channel,
                    user_name=leave["user_name"],
                    leave_date=today
                )
            logger.info(f"Posted {len(leaves_today)} leave announcements for {today}")
    except Exception as e:
        logger.error(f"Error posting daily leave announcements: {e}")

def start_socket_mode():
    """Start Socket Mode handler"""
    try:
        socket_handler = SocketModeHandler(slack_app, os.environ["SLACK_APP_TOKEN"])
        logger.info("Starting Socket Mode handler...")
        socket_handler.start()
    except Exception as e:
        logger.error(f"Failed to start Socket Mode: {e}")

def initialize_app():
    """Initialize application"""
    logger.info("Initializing Leave Tracker Application...")
    
    # Initialize database
    if supabase_client.init_db():
        logger.info("Database initialized successfully")
    else:
        logger.error("Failed to initialize database")
    
    # Start scheduler for daily announcements (9 AM daily)
    scheduler.add_job(
        post_daily_leave_announcements,
        trigger=CronTrigger(hour=9, minute=0),
        id="daily_leave_announcements"
    )
    
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started")
    
    # Start Socket Mode in a separate thread
    socket_thread = threading.Thread(target=start_socket_mode, daemon=True)
    socket_thread.start()
    logger.info("Socket Mode thread started")

if __name__ == "__main__":
    initialize_app()
    
    # Start Flask app
    flask_app.run(host="0.0.0.0", port=5000, debug=False)