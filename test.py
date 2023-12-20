from flask import Flask, render_template, request, redirect, url_for, jsonify
import requests
from chatterbot import ChatBot
from chatterbot.trainers import ChatterBotCorpusTrainer
import sqlite3
import re
import datetime
import time
import os

app = Flask(__name__)
weather_data = []  # Global variable to store weather data
error_message = None  # Variable to store the error message

# Retrieve API keys from environment variables
weather_api_key = os.environ.get('OpenWeather_API_key')
maps_api_key = os.environ.get('GoogleMaps_API_key')

# raise error if api key cannot be found by environment variable
if not weather_api_key:
    raise ValueError("OpenWeather_API_key environment variable not set.")

if not maps_api_key:
    raise ValueError("GoogleMaps_API_key environment variable not set.")

CACHE_TIMEOUT = 3600

locations = [
    {"name": "Lake District National Park, UK", "lat": 54.4609, "lon": -3.0886},
    {"name": "Corfe Castle", "lat": 50.6395, "lon": -2.0566},
    {"name": "The Cotswolds", "lat": 51.8330, "lon": -1.8433},
    {"name": "Cambridge, UK", "lat": 52.2053, "lon": 0.1218},
    {"name": "Bristol", "lat": 51.4545, "lon": -2.5879},
    {"name": "Oxford, UK", "lat": 51.7520, "lon": -1.2577},
    {"name": "Norwich", "lat": 52.6309, "lon": 1.2974},
    {"name": "Stonehenge, UK", "lat": 51.1789, "lon": -1.8262},
    {"name": "Watergate Bay", "lat": 50.4429, "lon": -5.0553},
    {"name": "Birmingham", "lat": 52.4862, "lon": -1.8904}
]


# initialize the database
def init_db():
    conn = sqlite3.connect('pybot.db')
    cursor = conn.cursor()


# Connect to SQLite database
conn = sqlite3.connect('pybot.db')

# Create a cursor object
cursor = conn.cursor()

# Create table for responses
cursor.execute('''CREATE TABLE IF NOT EXISTS responses
                  (id INTEGER PRIMARY KEY, query TEXT, response TEXT)''')

# Create table for logging chat sessions
cursor.execute('''CREATE TABLE IF NOT EXISTS chat_log
                  (id INTEGER PRIMARY KEY, user_input TEXT, bot_response TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')

# Create a table for response templates
cursor.execute('''CREATE TABLE IF NOT EXISTS response_templates (
                        id INTEGER PRIMARY KEY,
                        template TEXT)''')

# Commit the changes and close the connection
conn.commit()
conn.close()

init_db()

weather_data_backend = {}  # Global dictionary to store weather data

# Create a chatbot instance
chatbot = ChatBot('WeatherBot')

# Create a new trainer for the chatbot
trainer = ChatterBotCorpusTrainer(chatbot)

# Train the chatbot based on the English corpus
trainer.train("chatterbot.corpus.english")


def is_cache_valid(location, cache):
    """Check if the cache entry is valid."""
    if location in cache:
        cached_time = cache[location]['timestamp']
        if time.time() - cached_time < CACHE_TIMEOUT:
            return True
    return False


def construct_api_url(location_name, matched_location):
    api_key = weather_api_key
    base_url = "http://api.openweathermap.org/data/2.5/weather?"

    if matched_location:
        # Use latitude and longitude for the API URL
        lat, lon = matched_location['lat'], matched_location['lon']
        return f"{base_url}lat={lat}&lon={lon}&appid={api_key}&units=metric"
    else:
        # Use the location name for the API URL
        return f"{base_url}q={location_name}&appid={api_key}&units=metric"


def process_forecast_data(forecast_data):
    forecast_summary = ""
    for entry in forecast_data['list'][::8]:  # Assumes the API provides data in 3-hour intervals
        # Extract the date and time
        date_str = entry['dt_txt']
        # Convert the string to a datetime object
        date_obj = datetime.datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
        # Get the weekday name
        weekday = date_obj.strftime("%A")
        # Get the temperature
        temperature = entry['main']['temp']
        # Add to the summary, each day on a new line
        forecast_summary += f"{weekday}: {temperature}°C\n"
    return forecast_summary


app = Flask(__name__)


@app.route("/get-response", methods=['POST'])
def get_bot_response():
    user_input = request.form.get('text').lower()

    # Check for greeting in the user input
    if user_input in ['hello', 'hi', 'greetings', 'hey']:
        # Fetch greeting response from database
        conn = sqlite3.connect('pybot.db')
        cursor = conn.cursor()
        cursor.execute("SELECT response FROM responses WHERE query = 'greeting'")
        data = cursor.fetchone()
        conn.close()

        if data:
            bot_response = data[0]
        else:
            bot_response = "Hello! How can I assist you?"

    elif user_input in ['help']:
        # Fetch Cow response from Database
        conn = sqlite3.connect('pybot.db')
        cursor = conn.cursor()
        cursor.execute("SELECT response FROM responses WHERE query = 'help'")
        data = cursor.fetchone()
        conn.close()

        if data:
            bot_response = data[0]
        else:
            bot_response = "Hello! How can I assist you?"

    elif user_input in ['what do you think about weather?']:
        # Fetch Cow response from Database
        conn = sqlite3.connect('pybot.db')
        cursor = conn.cursor()
        cursor.execute("SELECT response FROM responses WHERE query = 'weather thoughts'")
        data = cursor.fetchone()
        conn.close()

        if data:
            bot_response = data[0]
        else:
            bot_response = "Hello! How can I assist you?"

    elif 'forecast for' in user_input:
        match = re.search(r'forecast\sfor\s([\w\s]+)', user_input, re.IGNORECASE)
        if match:
            location_name = match.group(1).strip()

            # Check if location_name matches any in the predefined locations list
            matched_location = next((loc for loc in locations if loc['name'].lower() == location_name.lower()), None)

            if matched_location:
                # Use latitude and longitude if a match is found
                lat, lon = matched_location['lat'], matched_location['lon']
                api_url = f"http://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={weather_api_key}&units=metric"
            else:
                # Use the location name as entered if no match is found
                api_url = f"http://api.openweathermap.org/data/2.5/forecast?q={location_name}&appid={weather_api_key}&units=metric"

            # Make the API call here
            response = requests.get(api_url)

            if response.status_code == 200:
                forecast_data = response.json()
                forecast_content = process_forecast_data(forecast_data)

                # Fetch forecast template from database
                conn = sqlite3.connect('pybot.db')
                cursor = conn.cursor()
                cursor.execute("SELECT template FROM response_templates WHERE id = 2")
                template = cursor.fetchone()[0]
                conn.close()

                # Fill in the template with fetched data
                bot_response = template.format(location=location_name.title(), forecast=forecast_content)
            else:
                bot_response = "Sorry, I couldn't find the forecast for that location."
        else:
            bot_response = "Please specify a location for the forecast."



    elif 'weather' in user_input:
        # Updated regex to capture multiple locations
        match = re.search(r'(?:weather|forecast)\s(?:in|for|at)\s([\w\s,]+)', user_input, re.IGNORECASE)
        if match:
            locations_input = match.group(1).strip()
            # Splitting the locations by commas and stripping extra spaces
            location_names = [loc.strip() for loc in re.split(r'\s*,\s*|\s+and\s+', locations_input)]

            # Initialize an empty list to hold individual responses for each location
            responses = []

            for location_name in location_names:
                if location_name:
                    # Check if location_name matches any in the predefined locations list
                    matched_location = next((loc for loc in locations if loc['name'].lower() == location_name.lower()),
                                            None)

                    # Use latitude and longitude if a match is found, else use the location name
                    if matched_location:
                        lat, lon = matched_location['lat'], matched_location['lon']
                        location_key = f"{lat},{lon}"
                        api_url = construct_api_url('', matched_location)
                    else:
                        location_key = location_name.lower()
                        api_url = construct_api_url(location_name, None)

                    # Check cache
                    if is_cache_valid(location_key, weather_data_backend):
                        print(f"Cache hit for {location_key}")  # Debug print
                        response_text = weather_data_backend[location_key]['data']
                    else:
                        print(f"Cache miss for {location_key}, fetching new data...")  # Debug print

                        # Fetch weather data from API
                        response = requests.get(api_url)
                        print("API Response Status:", response.status_code)  # Debug print

                        if response.status_code == 200:
                            weather_data = response.json()
                            temperature = weather_data['main']['temp']
                            condition = weather_data['weather'][0]['description']

                            # Fetch response template from database
                            conn = sqlite3.connect('pybot.db')
                            cursor = conn.cursor()
                            cursor.execute("SELECT template FROM response_templates WHERE id = 1")
                            template = cursor.fetchone()[0]
                            conn.close()

                            # Fill in the template with fetched data
                            response_text = template.format(location=location_name.title(), temperature=temperature,
                                                            condition=condition) + "<br>"

                            # Update cache
                            weather_data_backend[location_key] = {
                                'data': response_text,
                                'timestamp': time.time()
                            }
                        else:
                            response_text = f"Sorry, I couldn't find the weather for {location_name}."

                    # Append the response for the current location
                    responses.append(response_text)

            # Combine the responses for all locations
            bot_response = ' '.join(responses)
        else:
            bot_response = "Please specify a location for the weather."
    else:
        # Normal chatbot response
        bot_response = str(chatbot.get_response(user_input))

        # Store user input and bot response in the chat_log table
    conn = sqlite3.connect('pybot.db')
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO chat_log (user_input, bot_response) VALUES (?, ?)", (user_input, bot_response))
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        conn.close()

    return jsonify(bot_response=bot_response)


weather_data = []  # Global variable to store weather data
error_message = None  # Variable to store the error message


@app.route('/', methods=['GET', 'POST'])
def index():
    global weather_data  # Use the global variable
    # Locations defined by assignment

    # Add Location Form and OpenWeatherMap API Request:
    existing_locations = {entry['location'] for entry in weather_data}
    if request.method == 'POST':
        user_location = request.form.get('location')
        if user_location and user_location not in existing_locations:
            api_url = f"https://api.openweathermap.org/data/2.5/weather?q={user_location}&appid={weather_api_key}&units=metric"
            response = requests.get(api_url)
            if response.status_code == 200:
                current_weather = response.json()
                weather_data.append({
                    'location': user_location,
                    'temperature': current_weather['main']['temp'],
                    'condition': current_weather['weather'][0]['description']
                })

    # OpenWeatherMap API Request for pre-defined locations:
    if request.method == 'GET':
        for location in locations:
            if location['name'] not in existing_locations:
                lat, lon = location['lat'], location['lon']
                api_url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={weather_api_key}&units=metric"
                response = requests.get(api_url)
                if response.status_code == 200:
                    current_weather = response.json()
                    weather_data.append({
                        'location': location['name'],
                        'temperature': current_weather['main']['temp'],
                        'condition': current_weather['weather'][0]['description']
                    })

        # Pass api variables to html file for dynamic use
        return render_template('index.html', weather_data=weather_data, google_maps_api_key=maps_api_key)



# Clear user-added locations
@app.route('/clear', methods=['GET'])
def clear_data():
    global weather_data
    weather_data.clear()
    return redirect(url_for('index'))


if __name__ == "__main__":
    app.run(debug=True)
