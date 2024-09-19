from flask import Flask, render_template, request, jsonify, redirect, session
from deepface import DeepFace
import cv2
import numpy as np
import base64
import pandas as pd
import random
from flask_sqlalchemy import SQLAlchemy
import requests
import traceback
from datetime import datetime
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# Database Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///songs.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'secret_369'
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)

from flask_migrate import Migrate

# Initialize Flask-Migrate
migrate = Migrate(app, db)

# Define the User model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

# Define the Song model
class Song(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    artist = db.Column(db.String(100), nullable=False)
    album = db.Column(db.String(100), nullable=False)
    release_date = db.Column(db.String(100), nullable=False)
    mood = db.Column(db.String(50), nullable=False)

class RecommendationHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    song_id = db.Column(db.Integer, db.ForeignKey('song.id'), nullable=False)
    recommended_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    song = db.relationship('Song', backref=db.backref('recommendations', lazy=True))

# Define the Survey model to store user preferences
class Response(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    mood = db.Column(db.String(50), nullable=False)
    preferred_mood_songs = db.Column(db.String(200), nullable=False)

class ShareablePlaylist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    song_id = db.Column(db.Integer, db.ForeignKey('song.id'), nullable=False)
    shareable_link = db.Column(db.String(200), unique=True, nullable=False)

    song = db.relationship('Song', backref=db.backref('playlist_songs', lazy=True))

class PlaylistSong(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    playlist_id = db.Column(db.Integer, db.ForeignKey('shareable_playlist.id'), nullable=False)
    song_id = db.Column(db.Integer, db.ForeignKey('song.id'), nullable=False)

    playlist = db.relationship('ShareablePlaylist', backref=db.backref('songs', lazy=True))
    song = db.relationship('Song')


class EmotionLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    emotion = db.Column(db.String(50), nullable=False)
    logged_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

class Alarm(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    time = db.Column(db.DateTime, nullable=False)  # Alarm time
    emotion = db.Column(db.String(50), nullable=False)  # Chosen emotion
    active = db.Column(db.Boolean, default=True)  # Whether the alarm is active

# Initialize Flask-Login UserMixin
class UserSession(UserMixin):
    def __init__(self, user_id):
        self.id = user_id

# User loader function
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Function to load CSV data into the database
def load_csv_data():
    df = pd.read_csv("C:/Users/Korisnik/Desktop/CV_MUSIC/face_emotion_analysis/data_moods (1) (1).csv")
    for _, row in df.iterrows():
        song = Song(name=row['name'], artist=row['artist'], album=row['album'],
                    release_date=row['release_date'], mood=row['mood'].strip().lower())
        db.session.add(song)
    db.session.commit()

# YouTube Data API Key (replace with your actual key)
YOUTUBE_API_KEY = 'AIzaSyB-XtO_O3GRPSvjeZgRtqO9nwgJaMxG6fs'
YOUTUBE_SEARCH_URL = 'https://www.googleapis.com/youtube/v3/search'

# Function to fetch YouTube link for the recommended song
def get_youtube_link(song_name, artist):
    search_query = f"{song_name} {artist}"
    params = {
        'part': 'snippet',
        'q': search_query,
        'key': YOUTUBE_API_KEY,
        'type': 'video',
        'maxResults': 1
    }
    
    response = requests.get(YOUTUBE_SEARCH_URL, params=params)
    
    if response.status_code == 200:
        results = response.json().get('items')
        if results:
            video_id = results[0]['id']['videoId']
            youtube_link = f"https://www.youtube.com/watch?v={video_id}"
            return youtube_link
        else:
            print("No results found on YouTube.")
    else:
        print(f"Error response from YouTube API: {response.text}")
    
    return None

# Route for the homepage
@app.route('/')
def index():
    return render_template('index.html')


def recommend_song(mood):
    try:
        print(f"Received mood for recommendation: {mood}")
        mood = mood.lower()

        # Fetch the survey response for the given mood
        user_survey = Response.query.filter_by(mood=mood).first()

        if user_survey:
            # Use the preferred mood songs from the survey response
            preferred_mood_songs = user_survey.preferred_mood_songs
            filtered_songs = Song.query.filter(Song.mood == preferred_mood_songs).all()
        else:
            # Default to songs of the same mood if no survey response exists
            filtered_songs = Song.query.filter(Song.mood == mood).all()

        if not filtered_songs:
            print(f"No songs found for mood: {mood}")
            return {'error': 'No songs found for this mood.'}

        # Randomly select a song from the filtered list
        song = random.choice(filtered_songs)

        # Fetch YouTube link for the song
        youtube_link = get_youtube_link(song.name, song.artist)
        if not youtube_link:
            print(f"Error: Could not fetch YouTube link for {song.name} by {song.artist}.")
            return {'error': 'Could not fetch YouTube link for the song.'}

        # Log the recommendation
        recommendation = RecommendationHistory(
            song_id=song.id,
            recommended_at=datetime.now()
        )
        db.session.add(recommendation)
        db.session.commit()

        print(f"Recommended song: {song.name} by {song.artist}")

        return {
            'name': song.name,
            'artist': song.artist,
            'album': song.album,
            'release_date': song.release_date,
            'youtube_link': youtube_link
        }
    except Exception as e:
        print(f"Error in recommend_song: {str(e)}")
        return {'error': str(e)}


def check_consecutive_negative_emotions():
    negative_emotions = ['angry', 'sad', 'fear']
    
    # Query last 5 emotions logged in the EmotionLog table
    last_five_emotions = EmotionLog.query.order_by(EmotionLog.logged_at.desc()).limit(5).all()

    # Check if there are 5 emotions and all of them are negative
    if len(last_five_emotions) == 5:
        return all(emotion.emotion in negative_emotions for emotion in last_five_emotions)
    
    return False

# Route to analyze frame sent from the frontend
@app.route('/analyze_frame', methods=['POST'])
def analyze_frame():
    try:
        # Get the base64 encoded image from the request
        data_url = request.json['image']
        encoded_image = data_url.split(",")[1]
        
        # Decode the base64 image to bytes
        img_data = base64.b64decode(encoded_image)
        np_arr = np.frombuffer(img_data, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        
        # Analyze the frame using DeepFace
        analysis = DeepFace.analyze(img_path=img, actions=['emotion'])
        
        # Handle multiple face results
        if isinstance(analysis, list):
            analysis = analysis[0]
        
        dominant_emotion = analysis['dominant_emotion']
        
        # Log the emotion data
        emotion_log = EmotionLog(emotion=dominant_emotion)
        db.session.add(emotion_log)
        db.session.commit()
        
        # Check if the last 5 emotions are negative
        show_motivational_popup = check_consecutive_negative_emotions()
        
        # Get a recommended song based on the detected emotion
        recommended_song = recommend_song(dominant_emotion)
        
        return jsonify({
            'emotion': dominant_emotion,
            'recommended_song': recommended_song,
            'show_motivational_popup': show_motivational_popup,
            'motivational_message': "Everything is going to be okay!"
        }), 200
    
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/recommendation_history')
def recommendation_history():
    try:
        recommendations = RecommendationHistory.query.order_by(RecommendationHistory.recommended_at.desc()).all()
        recommended_songs = []

        for rec in recommendations:
            song = Song.query.get(rec.song_id)
            if song:  # Ensure song exists
                recommended_songs.append({
                    'name': song.name,
                    'artist': song.artist,
                    'album': song.album,
                    'release_date': song.release_date,
                    'recommended_at': rec.recommended_at.strftime('%Y-%m-%d %H:%M:%S'),
                
                })

        return render_template('recommendation_history.html', recommended_songs=recommended_songs)

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

from sqlalchemy.sql import func

# Route for mood playlists
@app.route('/mood_playlists')
def mood_playlists():
    # Get all distinct moods from the Song table
    distinct_moods = Song.query.with_entities(Song.mood).distinct().all()
    
    mood_playlists = {}
    
    # For each mood, fetch 10 random songs
    for mood_tuple in distinct_moods:
        mood = mood_tuple[0]  # Extract the mood from the tuple
        songs = Song.query.filter_by(mood=mood).order_by(func.random()).limit(10).all()
        
        # Prepare song data with YouTube links
        song_data = []
        for song in songs:
            song_data.append({
                'name': song.name,
                'artist': song.artist,
                'album': song.album,
                'release_date': song.release_date,
            })
        
        # Add songs to the mood playlist
        mood_playlists[mood] = song_data

    return render_template('mood_playlists.html', mood_playlists=mood_playlists)

# Admin login route
@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if username == 'admin' and password == 'adminadmin1234':
            # login_user(UserSession(1))  # Assuming '1' as admin user id
            return redirect('/admin')

        return 'Invalid username or password.'

    return render_template('admin_login.html')

@app.route('/admin', methods=['GET', 'POST'])
# @login_required
def admin():
    if request.method == 'POST':
        name = request.form.get('name')
        artist = request.form.get('artist')
        album = request.form.get('album')
        release_date = request.form.get('release_date')
        mood = request.form.get('mood')

        # Create a new song record
        song = Song(name=name, artist=artist, album=album,
                    release_date=release_date, mood=mood.lower().strip())
        db.session.add(song)
        db.session.commit()

        return 'Song added successfully!'

    return render_template('admin.html')

# Admin logout route
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect('/admin_login')

# CLI command to create an admin user (Optional for future use)
@app.cli.command('create_admin')
def create_admin():
    username = input('Enter admin username: ')
    password = input('Enter admin password: ')
    hashed_password = generate_password_hash(password)
    admin = User(username=username, password_hash=hashed_password)
    db.session.add(admin)
    db.session.commit()
    print('Admin user created.')

@app.route('/survey', methods=['GET', 'POST'])
def survey():
    if request.method == 'POST':
        happy_preference = request.form.get('happy_preference')
        sad_preference = request.form.get('sad_preference')
        angry_preference = request.form.get('angry_preference')

        # Update or create survey responses
        happy_survey = Response.query.filter_by(mood='happy').first()
        if happy_survey:
            happy_survey.preferred_mood_songs = happy_preference
        else:
            happy_survey = Response(mood='happy', preferred_mood_songs=happy_preference)
            db.session.add(happy_survey)

        sad_survey = Response.query.filter_by(mood='sad').first()
        if sad_survey:
            sad_survey.preferred_mood_songs = sad_preference
        else:
            sad_survey = Response(mood='sad', preferred_mood_songs=sad_preference)
            db.session.add(sad_survey)

        angry_survey = Response.query.filter_by(mood='angry').first()
        if angry_survey:
            angry_survey.preferred_mood_songs = angry_preference
        else:
            angry_survey = Response(mood='angry', preferred_mood_songs=angry_preference)
            db.session.add(angry_survey)

        db.session.commit()

        return redirect('/')

    return render_template('survey.html')


import plotly.graph_objects as go

@app.route('/emotion_chart')
def emotion_chart():
    try:
        # Fetch emotion data from the database
        emotion_logs = EmotionLog.query.order_by(EmotionLog.logged_at).all()
        emotions = [log.emotion for log in emotion_logs]
        timestamps = [log.logged_at.strftime('%Y-%m-%d %H:%M:%S') for log in emotion_logs]
        
        # Create a Plotly graph
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=timestamps, y=emotions, mode='lines+markers', name='Emotion'))
        
        fig.update_layout(
                          xaxis_title='Time',
                          yaxis_title='Emotion')
        
        # Save the plot as HTML
        graph_html = fig.to_html(full_html=False)
        
        return render_template('emotion_chart.html', graph_html=graph_html)
    
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

from midiutil import MIDIFile
from flask import Flask, request, jsonify, send_file
import os

EMOTION_MUSIC_MAPPING = {
    'happy': {
        'tempo': 130,
        'notes': [
            (60, 1), (62, 1), (64, 1), (65, 1), (67, 2), (69, 1), (71, 1), (72, 2),
            (60, 1), (64, 1), (67, 1), (65, 1), (69, 2), (71, 1), (74, 1), (72, 2),
            (74, 1), (72, 1), (69, 1), (67, 1), (65, 2), (64, 1), (62, 1), (60, 2)
        ]
    },
    'sad': {
        'tempo': 70,
        'notes': [
            (60, 2), (62, 2), (63, 2), (65, 2), (67, 2), (68, 2), (70, 2), (72, 2),
            (67, 2), (65, 2), (63, 2), (62, 2), (60, 2), (58, 2), (60, 2), (62, 2),
            (63, 2), (65, 2), (67, 2), (68, 2), (70, 2), (72, 2), (70, 2), (67, 2)
        ]
    },
    'angry': {
        'tempo': 150,
        'notes': [
            (60, 0.5), (61, 0.5), (63, 0.5), (64, 0.5), (65, 0.5), (66, 0.5), (68, 0.5), (69, 0.5),
            (70, 0.5), (72, 0.5), (74, 0.5), (76, 0.5), (77, 0.5), (79, 0.5), (81, 0.5), (82, 0.5),
            (84, 0.5), (86, 0.5), (88, 0.5), (89, 0.5), (91, 0.5), (93, 0.5), (95, 0.5), (96, 0.5)
        ]
    },
    'neutral': {
        'tempo': 100,
        'notes': [
            (60, 1), (62, 1), (64, 1), (65, 1), (67, 1), (69, 1), (71, 1), (72, 1),
            (74, 1), (76, 1), (77, 1), (79, 1), (81, 1), (83, 1), (85, 1), (86, 1),
            (88, 1), (89, 1), (91, 1), (93, 1), (95, 1), (97, 1), (99, 1), (101, 1)
        ]
    },
    'fear': {
        'tempo': 80,
        'notes': [
            (60, 1), (61, 1), (63, 1), (64, 1), (65, 1), (66, 1), (68, 1), (69, 1),
            (71, 1), (72, 1), (74, 1), (75, 1), (77, 1), (78, 1), (80, 1), (81, 1),
            (83, 1), (84, 1), (86, 1), (87, 1), (89, 1), (90, 1), (92, 1), (93, 1),
            (95, 1), (96, 1), (98, 1), (99, 1), (101, 1), (102, 1), (104, 1), (105, 1)
        ]
    }
}

def generate_music_based_on_emotion(emotion):
    try:
        print(f"Generating music for emotion: {emotion}")

        # Get the music properties based on emotion
        music_properties = EMOTION_MUSIC_MAPPING.get(emotion, {'tempo': 90, 'notes': [(60, 1)]})
        print(f"Music properties: {music_properties}")

        tempo = music_properties['tempo']
        notes = music_properties['notes']

        # Create a MIDI file with one track
        midi = MIDIFile(1)
        track = 0
        time = 0  # Start at the beginning
        midi.addTrackName(track, time, f"{emotion.capitalize()} Music")
        midi.addTempo(track, time, tempo)

        # Add notes to the MIDI file
        for note, duration in notes:
            volume = 100  # Max volume
            midi.addNote(track, 0, note, time, duration, volume)
            time += duration  # Move time forward by note duration
            print(f"Added note {note} with duration {duration}")

        # Define absolute path for the MIDI file
        midi_filename = os.path.join(os.getcwd(), f'generated_music_{emotion}.mid')

        # Save the MIDI file to disk
        with open(midi_filename, 'wb') as midi_file:
            midi.writeFile(midi_file)

        print(f"MIDI file saved as {midi_filename}")

        # Verify file creation
        if not os.path.isfile(midi_filename):
            raise FileNotFoundError(f"File {midi_filename} not found after creation.")

        return midi_filename
    except Exception as e:
        print(f"Error generating music: {e}")
        return None

@app.route('/generate_emotion_music', methods=['GET', 'POST'])
def emotion_music():
    if request.method == 'GET':
        # Render the HTML form when a GET request is made
        return render_template('emotion_music.html')  # Make sure this template exists

    if request.method == 'POST':
        try:
            # Ensure the content type is JSON
            if request.content_type != 'application/json':
                return jsonify({'error': 'Content-Type must be application/json'}), 415

            # Parse the emotion from the request
            data = request.json
            emotion = data.get('emotion', 'neutral').lower()
            print(f"Received emotion: {emotion}")  # Debugging: Check the received emotion

            # Generate music based on the emotion
            midi_file = generate_music_based_on_emotion(emotion)

            if midi_file and os.path.isfile(midi_file):
                print(f"Sending file: {midi_file}")  # Debugging: Check if the file exists before sending
                return send_file(midi_file, as_attachment=True, download_name=f'generated_music_{emotion}.mid')
            else:
                return jsonify({'error': 'Failed to generate music'}), 500
        except Exception as e:
            print(f"Error handling request: {e}")  # Log the error
            return jsonify({'error': str(e)}), 500



# JOŠ SAMO IMPLEMENTIRAT NEKI PIP-PIP SOUND KAD SE OPALI NOTIFICATION

import random, time, threading
alarms = {}
songs = {}


@app.route('/set_alarm', methods=['GET', 'POST'])
def set_alarm():
    if request.method == 'POST':
        try:
            alarm_date = request.form.get('date')
            alarm_time = request.form.get('time')
            mood = request.form.get('mood')

            if not alarm_date or not alarm_time or not mood:
                return jsonify({'error': 'Missing required parameters.'}), 400

            alarm_time_str = f"{alarm_date} {alarm_time}:00"

            # Convert to datetime object
            alarm_time_dt = datetime.strptime(alarm_time_str, '%Y-%m-%d %H:%M:%S')

            # Calculate time difference
            now = datetime.now()
            if alarm_time_dt <= now:
                return jsonify({'error': 'Alarm time must be in the future.'}), 400

            time_diff = (alarm_time_dt - now).total_seconds()

            # Store alarm information in global dictionary
            alarm_id = len(alarms) + 1
            alarms[alarm_id] = {'alarm_time': alarm_time_str, 'mood': mood}

            # Start countdown
            def fetch_song_after_delay(alarm_id):
                time.sleep(time_diff)
                with app.app_context():
                    try:
                        # Fetch random song based on emotion
                        song_response = fetch_random_song(alarms[alarm_id]['mood'])
                        songs[alarm_id] = song_response
                    except Exception as e:
                        songs[alarm_id] = {'error': str(e)}

            threading.Thread(target=fetch_song_after_delay, args=(alarm_id,)).start()

            return jsonify({'message': 'Alarm set successfully!', 'alarmDateTime': alarm_time_str, 'mood': mood}), 200

        except Exception as e:
            # Handle any exceptions that occur in the main route
            return jsonify({'error': str(e)}), 500

    # Render the alarm.html template
    return render_template('alarm.html')


@app.route('/get_song_info', methods=['GET'])
def get_song_info():
    try:
        song_info = songs.get(len(songs), {})  # Assuming you want the latest song info
        return jsonify(song_info)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/alarm_result', methods=['GET', 'POST'])
def alarm_result():
    # Retrieve song information from the session
    song_info = songs.get(len(songs), {})  # Assuming you want the latest song info
    return render_template('alarm_triggered.html', song_info=song_info)


import random
from datetime import datetime

def fetch_random_song(emotion):
    try:
        with app.app_context():  # Ensure we are in the application context
            print(f"Received emotion for random song fetching: {emotion}")

            # Query the database for songs that match the given emotion
            songs = Song.query.filter_by(mood=emotion).all()  # Change to the correct field

            if not songs:
                print(f"No songs found for emotion: {emotion}")
                return {'error': 'No songs found for the specified emotion.'}

            # Select a random song from the list
            random_song = random.choice(songs)

            # Fetch YouTube link for the song
            youtube_link = get_youtube_link(random_song.name, random_song.artist)
            if not youtube_link:
                print(f"Error: Could not fetch YouTube link for {random_song.name} by {random_song.artist}.")
                return {'error': 'Could not fetch YouTube link for the song.'}

            # Log the recommendation
            recommendation = RecommendationHistory(
                song_id=random_song.id,
                recommended_at=datetime.now()
            )
            db.session.add(recommendation)
            db.session.commit()

            print(f"Recommended song: {random_song.name} by {random_song.artist}")

            return {
                'name': random_song.name,
                'artist': random_song.artist,
                'album': random_song.album,
                'release_date': random_song.release_date,
                'youtube_link': youtube_link
            }

    except Exception as e:
        print(f"Error in fetch_random_song: {str(e)}")
        return {'error': str(e)}



if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # This will create the tables in the database
        if Song.query.count() == 0:  # Only load data if the table is empty
            load_csv_data()
app.run(host = '0.0.0.0', port=4000, debug=True)
