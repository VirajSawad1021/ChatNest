from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from flask import jsonify

import os


app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chat.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize SocketIO and SQLAlchemy
socketio = SocketIO(app)
db = SQLAlchemy(app)

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)

class ChatRoom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    is_private = db.Column(db.Boolean, default=False)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(500), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('chat_room.id'), nullable=False)


with app.app_context():
    
    db.create_all()

# Prevent caching
@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    rooms = ChatRoom.query.all()
    return render_template('index.html', rooms=rooms)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = username
            return redirect(url_for('index'))
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('register'))
            
        user = User(username=username, password_hash=generate_password_hash(password))
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/create_room', methods=['POST'])
def create_room():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    room_name = request.form.get('room_name')
    is_private = request.form.get('is_private') == 'true'
    
    room = ChatRoom(name=room_name, is_private=is_private)
    db.session.add(room)
    db.session.commit()
    return redirect(url_for('index'))

# Socket.IO events
@socketio.on('join')
def on_join(data):
    room = str(data['room'])
    join_room(room)
    emit('status', {'msg': session.get('username') + ' has entered the room.'}, room=room)

@socketio.on('leave')
def on_leave(data):
    room = str(data['room'])
    leave_room(room)
    emit('status', {'msg': session.get('username') + ' has left the room.'}, room=room)

@socketio.on('message')
def handle_message(data):
    room_id = data['room']
    content = data['message']
    
    if 'user_id' not in session:
        return
    
    message = Message(
        content=content,
        user_id=session['user_id'],
        room_id=room_id
    )
    db.session.add(message)
    db.session.commit()
    
    emit('message', {
        'user': session.get('username'),
        'message': content,
        'timestamp': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    }, room=str(room_id))
@app.route('/messages/<int:room_id>')
def get_room_messages(room_id):
    messages = Message.query.filter_by(room_id=room_id).all()
    message_data = []
    for message in messages:
        message_data.append({
            'user': User.query.get(message.user_id).username,
            'message': message.content,
            'timestamp': message.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        })
    return jsonify(message_data)


if __name__ == '__main__':
    socketio.run(app, debug=True, port=5001)  
