# app.py
from flask import Flask, request, jsonify, render_template
from datetime import datetime, time, timedelta
import json
import os

app = Flask(__name__)

# --- In-memory Data Storage ---
# For a production application, consider a persistent database (e.g., SQLite, PostgreSQL)
# or a more robust key-value store. This uses basic dictionaries for demonstration.

# Path for the data file to persist data across server restarts (simple JSON file)
DATA_FILE = 'data.json'

# Default data structure
default_data = {
    "light_status": {
        # 'esp32_reported_status': The ACTUAL status reported by the ESP32
        # 'esp32_last_reported_time': Timestamp of the last successful report from ESP32
        # 'control_mode': "MANUAL" or "SCHEDULE" - determines what the ESP32 should follow
        # 'manual_target_state': The state set by the frontend's manual toggle button (only applies in MANUAL mode)
        # 'server_last_command_time': Timestamp of the last manual_target_state change OR control_mode change
        "A": {"esp32_reported_status": "UNKNOWN", "esp32_last_reported_time": None, "control_mode": "MANUAL", "manual_target_state": "OFF", "server_last_command_time": None},
        "B": {"esp32_reported_status": "UNKNOWN", "esp32_last_reported_time": None, "control_mode": "MANUAL", "manual_target_state": "OFF", "server_last_command_time": None},
        "C": {"esp32_reported_status": "UNKNOWN", "esp32_last_reported_time": None, "control_mode": "MANUAL", "manual_target_state": "OFF", "server_last_command_time": None},
        "D": {"esp32_reported_status": "UNKNOWN", "esp32_last_reported_time": None, "control_mode": "MANUAL", "manual_target_state": "OFF", "server_last_command_time": None},
    },
    "light_schedules": {
        "A": [],  # Example: [{"start_time": "08:00", "end_time": "18:00"}]
        "B": [],
        "C": [],
        "D": [],
    },
    "ac_data": {
        "current_temp": 25,  # Default current temperature
        "hourly_schedule": {str(h).zfill(2): 22 for h in range(24)} # Default 22C for all hours
    }
}

# Function to load data from JSON file
def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                loaded_data = json.load(f)
                # Merge loaded data with default_data to handle new fields gracefully
                for rack_id in default_data["light_status"]:
                    if rack_id not in loaded_data["light_status"]:
                        loaded_data["light_status"][rack_id] = default_data["light_status"][rack_id]
                    else:
                        for key, default_value in default_data["light_status"][rack_id].items():
                            if key not in loaded_data["light_status"][rack_id]:
                                loaded_data["light_status"][rack_id][key] = default_value
                # Ensure other top-level keys exist if not loaded
                for key, default_value in default_data.items():
                    if key not in loaded_data:
                        loaded_data[key] = default_value
                return loaded_data
        except json.JSONDecodeError:
            print(f"Warning: Could not decode {DATA_FILE}, using default data.")
            return default_data
    return default_data

# Function to save data to JSON file
def save_data():
    with open(DATA_FILE, 'w') as f:
        json.dump(app.data, f, indent=4)

# Load data when the application starts
app.data = load_data()

# --- Utility Functions ---
def get_current_time_str():
    return datetime.now().isoformat()

def is_time_in_range(current_time_str, start_time_str, end_time_str):
    """
    Checks if current_time (HH:MM) is within the start and end time (HH:MM).
    Handles overnight schedules (e.g., 22:00 - 06:00).
    """
    try:
        current_t = datetime.strptime(current_time_str, "%H:%M").time()
        start_t = datetime.strptime(start_time_str, "%H:%M").time()
        end_t = datetime.strptime(end_time_str, "%H:%M").time()

        if start_t <= end_t:
            return start_t <= current_t <= end_t
        else: # Overnight schedule
            return current_t >= start_t or current_t <= end_t
    except ValueError:
        return False # Invalid time format

# --- Frontend Routes ---
@app.route('/')
def index():
    """Serves the main HTML frontend page."""
    return render_template('index.html')

# --- API Endpoints for Lights ---

@app.route('/api/light/status', methods=['GET'])
def get_all_light_status():
    """
    GET: Returns the current physical status (as reported by ESP),
         last active time, control mode, and manual target state for all racks.
    Accessible by frontend for display.
    """
    return jsonify(app.data["light_status"])

@app.route('/api/light/update', methods=['POST'])
def update_light_status():
    """
    POST: Endpoint for ESP32 to update its *physical* light status and the time it reported.
    Expected JSON: {"rack_id": "A", "status": "ON"}
    This updates the 'esp32_reported_status' and 'esp32_last_reported_time' fields.
    """
    data = request.get_json()
    rack_id = data.get('rack_id')
    status = data.get('status')

    if not rack_id or not status:
        return jsonify({"error": "Missing rack_id or status"}), 400

    if rack_id not in app.data["light_status"]:
        return jsonify({"error": "Invalid rack_id"}), 400

    if status.upper() not in ["ON", "OFF"]:
        return jsonify({"error": "Invalid status. Must be 'ON' or 'OFF'"}), 400

    app.data["light_status"][rack_id]['esp32_reported_status'] = status.upper()
    app.data["light_status"][rack_id]['esp32_last_reported_time'] = get_current_time_str()
    save_data() # Persist changes
    print(f"ESP32 reported status updated for {rack_id}: {status}")
    return jsonify({"message": "ESP32 status updated successfully", "rack_id": rack_id, "reported_status": status.upper()})

@app.route('/api/light/manual_control', methods=['POST'])
def manual_light_control():
    """
    POST: Endpoint for frontend to set the 'manual_target_state'.
    This state is only acted upon by the ESP32 if its 'control_mode' is MANUAL.
    Expected JSON: {"rack_id": "A", "status": "ON"}
    """
    data = request.get_json()
    rack_id = data.get('rack_id')
    status = data.get('status')

    if not rack_id or not status:
        return jsonify({"error": "Missing rack_id or status"}), 400

    if rack_id not in app.data["light_status"]:
        return jsonify({"error": "Invalid rack_id"}), 400

    if status.upper() not in ["ON", "OFF"]:
        return jsonify({"error": "Invalid status. Must be 'ON' or 'OFF'"}), 400

    # Update the manual_target_state. The ESP32 will act on this if in MANUAL mode.
    app.data["light_status"][rack_id]['manual_target_state'] = status.upper()
    app.data["light_status"][rack_id]['server_last_command_time'] = get_current_time_str()
    save_data()
    print(f"Manual target state set for {rack_id}: {status}")
    return jsonify({"message": "Manual target state updated", "rack_id": rack_id, "manual_target_state": status.upper()})

@app.route('/api/light/set_control_mode', methods=['POST'])
def set_light_control_mode():
    """
    POST: Sets the control mode for a specific rack (MANUAL or SCHEDULE).
    Expected JSON: {"rack_id": "A", "mode": "MANUAL"}
    """
    data = request.get_json()
    rack_id = data.get('rack_id')
    mode = data.get('mode')

    if not rack_id or not mode:
        return jsonify({"error": "Missing rack_id or mode"}), 400
    if rack_id not in app.data["light_status"]:
        return jsonify({"error": "Invalid rack_id"}), 400
    if mode.upper() not in ["MANUAL", "SCHEDULE"]:
        return jsonify({"error": "Invalid mode. Must be 'MANUAL' or 'SCHEDULE'"}), 400

    app.data["light_status"][rack_id]['control_mode'] = mode.upper()
    app.data["light_status"][rack_id]['server_last_command_time'] = get_current_time_str()
    save_data()
    print(f"Control mode set for {rack_id}: {mode}")
    return jsonify({"message": "Control mode set successfully", "rack_id": rack_id, "control_mode": mode.upper()})


@app.route('/api/light/config/<rack_id>', methods=['GET'])
def get_rack_config(rack_id):
    """
    GET: Returns the full configuration for an ESP32, including control mode,
    schedule, and the 'server_commanded_status' based on the control mode.
    ESP32 should poll this endpoint to know what to do.
    """
    if rack_id not in app.data["light_status"]:
        return jsonify({"error": "Rack not found"}), 404

    current_time_hhmm = datetime.now().strftime("%H:%M")
    rack_info = app.data["light_status"][rack_id]
    schedule = app.data["light_schedules"].get(rack_id, [])

    control_mode = rack_info['control_mode']
    server_commanded_status = "OFF" # Default to OFF

    if control_mode == "MANUAL":
        server_commanded_status = rack_info['manual_target_state'] # Follow the manual set status
    elif control_mode == "SCHEDULE":
        # Evaluate schedule to determine commanded status
        should_be_on_according_to_schedule = False
        for entry in schedule:
            if is_time_in_range(current_time_hhmm, entry['start_time'], entry['end_time']):
                should_be_on_according_to_schedule = True
                break
        server_commanded_status = "ON" if should_be_on_according_to_schedule else "OFF"
    
    return jsonify({
        "rack_id": rack_id,
        "control_mode": control_mode,
        "current_time": current_time_hhmm,
        "schedule": schedule,
        "server_commanded_status": server_commanded_status, # What the ESP32 should aim for
        "message": f"Configuration for rack {rack_id}"
    })


@app.route('/api/light/schedule/<rack_id>', methods=['GET'])
def get_light_schedule_frontend(rack_id):
    """
    GET: Returns the light schedule for a specific rack (for frontend display/editing).
    """
    if rack_id not in app.data["light_schedules"]:
        return jsonify({"error": "Rack not found"}), 404
    
    return jsonify({
        "rack_id": rack_id,
        "schedule": app.data["light_schedules"][rack_id]
    })


@app.route('/api/light/schedule/set', methods=['POST'])
def set_light_schedule():
    """
    POST: Sets the light schedule for a specific rack.
    Expected JSON: {"rack_id": "A", "schedule": [{"start_time": "HH:MM", "end_time": "HH:MM"}, ...]}
    The schedule should be an array of time range objects.
    """
    data = request.get_json()
    rack_id = data.get('rack_id')
    schedule = data.get('schedule')

    if not rack_id or not isinstance(schedule, list):
        return jsonify({"error": "Missing rack_id or invalid schedule format"}), 400

    if rack_id not in app.data["light_schedules"]:
        return jsonify({"error": "Invalid rack_id"}), 400

    # Validate schedule entries
    for entry in schedule:
        if not all(k in entry for k in ['start_time', 'end_time']):
            return jsonify({"error": "Each schedule entry must have 'start_time' and 'end_time'"}), 400
        try:
            datetime.strptime(entry['start_time'], "%H:%M")
            datetime.strptime(entry['end_time'], "%H:%M")
        except ValueError:
            return jsonify({"error": f"Invalid time format in schedule: {entry['start_time']} or {entry['end_time']}. Use HH:MM"}), 400

    app.data["light_schedules"][rack_id] = schedule
    save_data()
    print(f"Schedule set for {rack_id}: {schedule}")
    return jsonify({"message": "Schedule set successfully", "rack_id": rack_id, "schedule": schedule})

# --- API Endpoints for AC Control ---

@app.route('/api/ac/status', methods=['GET'])
def get_ac_status():
    """
    GET: Returns the current AC temperature and the hourly schedule.
    """
    current_hour = datetime.now().hour
    current_hour_str = str(current_hour).zfill(2)
    target_temp_for_hour = app.data["ac_data"]["hourly_schedule"].get(current_hour_str, 22) # Default 22 if hour not found

    return jsonify({
        "current_temp": app.data["ac_data"]["current_temp"],
        "hourly_schedule": app.data["ac_data"]["hourly_schedule"],
        "current_time": datetime.now().strftime("%H:%M"),
        "target_temp_for_current_hour": target_temp_for_hour
    })

@app.route('/api/ac/update_temp', methods=['POST'])
def update_ac_temp():
    """
    POST: Endpoint for ESP32 to update its current AC temperature reading.
    Expected JSON: {"temperature": 24.5}
    """
    data = request.get_json()
    temperature = data.get('temperature')

    if temperature is None or not isinstance(temperature, (int, float)):
        return jsonify({"error": "Missing or invalid 'temperature'"}), 400

    app.data["ac_data"]["current_temp"] = temperature
    save_data()
    print(f"AC current temperature updated: {temperature}°C")
    return jsonify({"message": "AC temperature updated successfully", "current_temp": temperature})

@app.route('/api/ac/schedule/set', methods=['POST'])
def set_ac_schedule():
    """
    POST: Sets the hourly AC temperature schedule.
    Expected JSON: {"hourly_schedule": {"00": 20, "01": 21, ..., "23": 20}}
    """
    data = request.get_json()
    hourly_schedule = data.get('hourly_schedule')

    if not isinstance(hourly_schedule, dict):
        return jsonify({"error": "Missing or invalid 'hourly_schedule' format. Must be a dictionary."}), 400

    # Basic validation for keys (hours 00-23) and values (temperatures)
    validated_schedule = {}
    for hour_str in range(24):
        hour_key = str(hour_str).zfill(2)
        temp_value = hourly_schedule.get(hour_key)
        if temp_value is None or not isinstance(temp_value, (int, float)):
            # If a specific hour is missing or invalid, default to a reasonable temperature
            validated_schedule[hour_key] = 22
        else:
            validated_schedule[hour_key] = temp_value

    app.data["ac_data"]["hourly_schedule"] = validated_schedule
    save_data()
    print(f"AC hourly schedule set: {validated_schedule}")
    return jsonify({"message": "AC hourly schedule set successfully", "hourly_schedule": validated_schedule})


if __name__ == '__main__':
    # Create the 'templates' directory if it doesn't exist
    os.makedirs('templates', exist_ok=True)
    # Run the Flask app
    app.run(debug=True, host='0.0.0.0', port=5000)