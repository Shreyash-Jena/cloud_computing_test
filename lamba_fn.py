import json
import boto3
import uuid
import os
import math
from datetime import datetime
from decimal import Decimal

# Initialize DynamoDB resources
dynamodb = boto3.resource('dynamodb')
request_table = dynamodb.Table(os.environ.get('LAUNDRY_TABLE', 'IIITBLaundry'))
pin_table = dynamodb.Table(os.environ.get('PIN_TABLE', 'StudentPins'))

VALID_PC_EMAIL = os.environ.get('PC_EMAIL', 'pc@iiit-bh.ac.in')
VALID_PC_PASS = os.environ.get('PC_PASSWORD', 'LaundryAdmin123')

SYSTEM_STATUS_KEY = '__SYSTEM_STATUS__'
DEFAULT_CYCLE_MINUTES = 45

# Helper to serialize DynamoDB Decimal and other types into JSON
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super(DecimalEncoder, self).default(obj)

def get_system_config():
    """Retrieve system configuration (working machines, alert message, etc.)"""
    try:
        res = request_table.get_item(Key={'id': SYSTEM_STATUS_KEY})
        if 'Item' in res:
            item = res['Item']
            return {
                'total_machines': int(item.get('total_machines', 5)),
                'working_machines': int(item.get('working_machines', 4)),
                'alert_message': str(item.get('alert_message', '')),
                'cycle_time': int(item.get('cycle_time', DEFAULT_CYCLE_MINUTES)),
                'last_updated': item.get('last_updated', '')
            }
    except Exception as e:
        print(f"Error fetching system config: {e}")
    
    # Default fallback values
    return {
        'total_machines': 5,
        'working_machines': 4,
        'alert_message': '',
        'cycle_time': DEFAULT_CYCLE_MINUTES,
        'last_updated': ''
    }

def calculate_wait_time(queued_ahead_count, working_machines, cycle_time=DEFAULT_CYCLE_MINUTES):
    """Calculate estimated wait time based on queue depth and operational machines"""
    if working_machines <= 0:
        return -1  # Indicates all machines are down / maintenance
    batches = math.ceil((queued_ahead_count + 1) / max(1, working_machines))
    return batches * cycle_time

def lambda_handler(event, context):
    # Handle CORS preflight request
    if event.get('httpMethod') == 'OPTIONS':
        return {"statusCode": 200, "headers": cors(), "body": json.dumps({"status": "ok"})}

    try:
        body = json.loads(event.get('body', '{}')) if isinstance(event.get('body'), str) else (event.get('body') or {})
        action = body.get('action')
        
        # 1. PUBLIC STATS (For live cards and alerts on front-end)
        if action == 'GET_STATS':
            scan_res = request_table.scan()
            all_items = scan_res.get('Items', [])
            
            # Filter out the internal system status row
            requests = [item for item in all_items if item.get('id') != SYSTEM_STATUS_KEY]
            
            washing_count = sum(1 for r in requests if r.get('status') == 'WASHING')
            queued_count = sum(1 for r in requests if r.get('status') in ['REQUESTED', 'APPROVED_WAITING', 'QUEUED'])
            ready_count = sum(1 for r in requests if r.get('status') in ['READY', 'COMPLETED'])
            total_active = washing_count + queued_count
            
            config = get_system_config()
            working_machines = config['working_machines']
            total_machines = config['total_machines']
            alert_message = config['alert_message']
            cycle_time = config['cycle_time']
            
            est_wait_minutes = calculate_wait_time(queued_count, working_machines, cycle_time)
            
            return success_response({
                "total_submitted": len(requests),
                "washing_count": washing_count,
                "queued_count": queued_count,
                "ready_count": ready_count,
                "total_active": total_active,
                "working_machines": working_machines,
                "total_machines": total_machines,
                "alert_message": alert_message,
                "est_wait_minutes": est_wait_minutes,
                "cycle_time": cycle_time,
                "system_updated": config.get('last_updated', '')
            })

        # UNIFIED AUTH (Sign In / Sign Up for Student or Staff)
        elif action == 'AUTH_LOGIN':
            email = body.get('email', '').strip().lower()
            password = body.get('password', '').strip()
            roll_no = body.get('rollNo', '').strip().upper()
            is_signup = body.get('isSignUp', False)

            if not email or not password:
                return error_response("Email and PIN/Password are required.", 400)

            # Check if Laundry Staff / PC credentials
            if email == VALID_PC_EMAIL.lower() and password == VALID_PC_PASS:
                return success_response({
                    "role": "STAFF",
                    "email": VALID_PC_EMAIL,
                    "name": "Laundry Manager",
                    "message": "Staff login successful"
                })

            # Check if student email
            if not email.endswith('@iiit-bh.ac.in'):
                return error_response("Invalid credentials. Please use your @iiit-bh.ac.in email or Staff credentials.", 403)

            if len(password) < 4:
                return error_response("PIN must be at least 4 digits.", 400)

            pin_res = pin_table.get_item(Key={'email': email})
            if 'Item' in pin_res:
                saved_item = pin_res['Item']
                if saved_item.get('pin') != password:
                    return error_response("Incorrect 4-digit PIN for this student email.", 401)
                student_roll = saved_item.get('rollNo') or roll_no
                if roll_no and not saved_item.get('rollNo'):
                    pin_table.update_item(
                        Key={'email': email},
                        UpdateExpression='SET rollNo = :r',
                        ExpressionAttributeValues={':r': roll_no}
                    )
                    student_roll = roll_no
                return success_response({
                    "role": "STUDENT",
                    "email": email,
                    "rollNo": student_roll,
                    "message": "Student sign in successful",
                    "isNew": False
                })
            else:
                # Sign up new student
                if not roll_no:
                    return error_response("First time sign up: Please provide your Roll Number.", 400)
                pin_table.put_item(Item={'email': email, 'pin': password, 'rollNo': roll_no})
                return success_response({
                    "role": "STUDENT",
                    "email": email,
                    "rollNo": roll_no,
                    "message": "Student account registered and signed in!",
                    "isNew": True
                })

        # 2. CHECK SPECIFIC STUDENT STATUS
        elif action == 'CHECK_MY_STATUS':
            query = body.get('query', '').strip().lower()
            if not query:
                return error_response("Please enter your registered email or Roll No.", 400)
                
            scan_res = request_table.scan()
            requests = [r for r in scan_res.get('Items', []) if r.get('id') != SYSTEM_STATUS_KEY]
            
            # Find active requests matching email or roll number
            user_requests = [
                r for r in requests 
                if r.get('email', '').strip().lower() == query or r.get('rollNo', '').strip().lower() == query
            ]
            
            if not user_requests:
                return success_response({"has_active": False, "message": "No requests found for this student."})
                
            # Sort by date descending to find the latest
            user_requests.sort(key=lambda x: x.get('date', ''), reverse=True)
            latest = user_requests[0]
            status = latest.get('status')
            
            is_active = status in ['REQUESTED', 'APPROVED_WAITING', 'QUEUED', 'WASHING']
            config = get_system_config()
            
            # If in queue, count how many requests submitted before this one are ahead
            queue_position = 0
            if is_active and status != 'WASHING':
                queued_items = [r for r in requests if r.get('status') in ['REQUESTED', 'APPROVED_WAITING', 'QUEUED']]
                queued_items.sort(key=lambda x: x.get('date', ''))
                for idx, item in enumerate(queued_items):
                    if item.get('id') == latest.get('id'):
                        queue_position = idx + 1
                        break
            
            wait_time = calculate_wait_time(max(0, queue_position - 1), config['working_machines'], config['cycle_time']) if is_active else 0
            
            return success_response({
                "has_active": is_active,
                "request": latest,
                "queue_position": queue_position,
                "estimated_minutes": wait_time,
                "history": user_requests[:5]
            })

        # 3. STUDENT SUBMIT REQUEST (Prevents duplicate active submissions)
        elif action == 'STUDENT_REQUEST':
            student_email = body.get('email', '').strip().lower()
            student_pin = body.get('pin', '').strip()
            roll_no = body.get('rollNo', '').strip().upper()
            
            if not roll_no:
                return error_response("Roll Number is required.", 400)
                
            if not student_email.endswith('@iiit-bh.ac.in'):
                return error_response("Only @iiit-bh.ac.in institute email addresses are allowed.", 403)
            
            if len(student_pin) < 4:
                return error_response("PIN must be at least 4 characters.", 400)

            # Authenticate or register student PIN
            pin_response = pin_table.get_item(Key={'email': student_email})
            if 'Item' in pin_response:
                if pin_response['Item']['pin'] != student_pin:
                    return error_response("Incorrect PIN for this registered email.", 401)
            else:
                pin_table.put_item(Item={'email': student_email, 'pin': student_pin})

            # Check if student already has an active bucket in progress
            scan_res = request_table.scan()
            active_statuses = ['REQUESTED', 'APPROVED_WAITING', 'QUEUED', 'WASHING']
            for item in scan_res.get('Items', []):
                if item.get('id') == SYSTEM_STATUS_KEY:
                    continue
                same_email = item.get('email', '').strip().lower() == student_email
                same_roll = item.get('rollNo', '').strip().upper() == roll_no
                if (same_email or same_roll) and item.get('status') in active_statuses:
                    return error_response(
                        f"You already have an active bucket submitted (Bucket ID: #{item.get('id')}, Status: {item.get('status')}). "
                        f"You cannot submit another bucket until your previous bucket is completed and picked up.",
                        400
                    )

            # Insert new laundry request
            req_id = str(uuid.uuid4())[:8].upper()
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            request_table.put_item(
                Item={
                    'id': req_id,
                    'rollNo': roll_no,
                    'email': student_email,
                    'status': 'REQUESTED',
                    'date': now_str
                }
            )
            return success_response({
                "message": f"Bucket #{req_id} submitted successfully!", 
                "id": req_id,
                "rollNo": roll_no,
                "date": now_str
            })
            
        # 4. PC / LAUNDRY WORKER DASHBOARD
        elif action == 'PC_DASHBOARD':
            email_attempt = body.get('email', '').strip()
            pass_attempt = body.get('password', '').strip()
            
            if email_attempt != VALID_PC_EMAIL or pass_attempt != VALID_PC_PASS:
                return error_response("Invalid Staff Credentials", 401)
                
            response = request_table.scan()
            all_items = response.get('Items', [])
            requests = [item for item in all_items if item.get('id') != SYSTEM_STATUS_KEY]
            
            # Sort requests by date descending
            requests.sort(key=lambda x: x.get('date', ''), reverse=True)
            
            config = get_system_config()
            return success_response({
                "requests": requests,
                "config": config
            })

        # 5. WORKER UPDATES MACHINE & SYSTEM STATUS / ALERTS
        elif action == 'UPDATE_SYSTEM_CONFIG':
            email_attempt = body.get('email', '').strip()
            pass_attempt = body.get('password', '').strip()
            
            if email_attempt != VALID_PC_EMAIL or pass_attempt != VALID_PC_PASS:
                return error_response("Unauthorized: Staff login required", 401)
                
            total_m = int(body.get('total_machines', 5))
            working_m = int(body.get('working_machines', 4))
            alert_msg = str(body.get('alert_message', '')).strip()
            cycle_time = int(body.get('cycle_time', DEFAULT_CYCLE_MINUTES))
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            
            if working_m > total_m:
                working_m = total_m
            if working_m < 0:
                working_m = 0
                
            request_table.put_item(
                Item={
                    'id': SYSTEM_STATUS_KEY,
                    'total_machines': total_m,
                    'working_machines': working_m,
                    'alert_message': alert_msg,
                    'cycle_time': cycle_time,
                    'last_updated': now_str
                }
            )
            
            return success_response({
                "message": "System status & alert updated successfully!",
                "config": {
                    "total_machines": total_m,
                    "working_machines": working_m,
                    "alert_message": alert_msg,
                    "cycle_time": cycle_time,
                    "last_updated": now_str
                }
            })
            
        # 6. WORKER UPDATES BUCKET STATUS
        elif action == 'UPDATE_STATUS':
            req_id = body.get('id')
            new_status = body.get('newStatus')
            
            if not req_id or not new_status:
                return error_response("Missing Request ID or New Status", 400)
                
            # Fetch existing request to extract student details
            get_res = request_table.get_item(Key={'id': req_id})
            req_item = get_res.get('Item')
            
            if not req_item:
                return error_response("Request not found", 404)
                
            # Update status in DynamoDB
            request_table.update_item(
                Key={'id': req_id},
                UpdateExpression='SET #st = :s, #lu = :lu',
                ExpressionAttributeNames={'#st': 'status', '#lu': 'last_updated'},
                ExpressionAttributeValues={
                    ':s': new_status,
                    ':lu': datetime.now().strftime("%Y-%m-%d %H:%M")
                }
            )
            
            return success_response({
                "message": f"Bucket #{req_id} state updated to {new_status}",
                "newStatus": new_status
            })

        else:
            return error_response(f"Unknown action: '{action}'", 400)

    except Exception as e:
        print(f"Server exception: {str(e)}")
        return error_response(f"Internal Error: {str(e)}", 500)

def cors():
    return {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
        'Access-Control-Allow-Methods': 'OPTIONS,POST,GET',
        'Content-Type': 'application/json'
    }

def success_response(data):
    return {
        "statusCode": 200, 
        "headers": cors(), 
        "body": json.dumps(data, cls=DecimalEncoder)
    }

def error_response(msg, code=400):
    return {
        "statusCode": code,
        "headers": cors(),
        "body": json.dumps({"error": msg})
    }
