from flask import Flask, render_template, request, redirect, url_for, session
from flask_socketio import SocketIO, emit
import numpy as np
import ast
import mysql.connector
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import hashlib
import time
from flask_login import LoginManager, UserMixin, current_user, login_user, logout_user
from copy import deepcopy
import random
from flask_socketio import join_room, leave_room
import logging
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = 'your-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*")

handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)
app.logger.addHandler(handler)
app.logger.setLevel(logging.DEBUG)

######################################################################
time.sleep(7)
#DBに使う名前。
db_user_name='site10user'
db_password='140286TakaHiro'
#db_host='localhost'
#db_host='site10-db-1'#dockerのmysqlコンテナはこれを使う。
db_host='site10_db_1'#VPSのdockerのmysqlコンテナはこれを使う。
db_name='site10db_1'

# DBを構築
cnx = mysql.connector.connect(
    user=db_user_name, 
    password=db_password, 
    host=db_host
)
cursor = cnx.cursor()

cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name}")
cnx.database = db_name

cursor.execute("""
    CREATE TABLE IF NOT EXISTS user (
        ID INT PRIMARY KEY NOT NULL AUTO_INCREMENT,
        nickname VARCHAR(128) NOT NULL,
        password VARCHAR(128) NOT NULL
    )
""")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS room (
        ID INT PRIMARY KEY NOT NULL AUTO_INCREMENT,
        room_name VARCHAR(128) NOT NULL,
        room_password VARCHAR(128),
        for_all_or_not BOOLEAN NOT NULL,
        result TEXT NOT NULL,
        current_turn INT DEFAULT NULL
    )
""")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_room (
        user_ID INT NOT NULL,
        room_ID INT NOT NULL,
        is_player BOOLEAN NOT NULL DEFAULT False,
        role ENUM('黒（先攻）', '白（後攻）') DEFAULT NULL,
        PRIMARY KEY(user_ID, room_ID),
        FOREIGN KEY(user_ID) REFERENCES user(ID),
        FOREIGN KEY(room_ID) REFERENCES room(ID)
    )
""")
cnx.commit()
cursor.close()
cnx.close()

# DBにアクセス
def get_db():
    return mysql.connector.connect(
        user=db_user_name, 
        password=db_password, 
        host=db_host, 
        database=db_name
    )
######################################################################
#ログイン
limiter = Limiter(app,key_func=get_remote_address,default_limits=["30 per minute"])
#limiter = Limiter(get_remote_address, app=app, default_limits=["30 per minute"])
login_manager = LoginManager()
login_manager.init_app(app)

class User(UserMixin):
    def __init__(self, id, nickname, password):
        self.id = id
        self.nickname = nickname
        self.password = password

@login_manager.user_loader
def load_user(user_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM user WHERE ID = %s", (user_id,))
    user = cursor.fetchone()
    conn.close()
    if user:
        return User(user['ID'], user['nickname'], user['password'])
    else:
        return None

def hash_password(password):
    hash_object = hashlib.sha256()
    hash_object.update(password.encode('utf-8'))
    hashed_password = hash_object.hexdigest()
    return hashed_password

def get_nickname():
    if current_user.is_authenticated:
        return current_user.nickname
    else:
        return "ログインしていません"

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("30/minute") 
def login():
    nickname=get_nickname()
    if request.method == 'POST':
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM user WHERE nickname = %s", (request.form['nickname'], ))
        user_db = cursor.fetchone()
        conn.close()
        if user_db and user_db['password'] == hash_password(request.form['password']):
            user = User(user_db['ID'], user_db['nickname'], user_db['password'])
            login_user(user)
            nickname=get_nickname()
            return redirect(url_for('home'))
        else:
            good_or_bad="nicknameかpasswordが間違っています。"
    elif request.method == 'GET':
        good_or_bad="対戦や観戦にはログインが必要です"
    return render_template('login.html', good_or_bad=good_or_bad, nickname=nickname)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    nickname=get_nickname()
    if request.method == 'POST':
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        try:
            conn.start_transaction()
            cursor.execute("SELECT * FROM user WHERE nickname = %s", (request.form['nickname'], ))
            user_db = cursor.fetchone()
            if user_db:
                already_used_or_not='すでに使われているnicknameです'
            else:
                cursor.execute("INSERT INTO user (nickname, password) VALUES (%s, %s)", (request.form['nickname'], hash_password(request.form['password'])))
                conn.commit()
                user_id = cursor.lastrowid
                user = User(user_id, request.form['nickname'], hash_password(request.form['password']))
                login_user(user)
                nickname=get_nickname()
                return redirect(url_for('home'))
        except Exception as e:
            print(e)
            conn.rollback()
        finally:
            conn.close()
    elif request.method == 'GET':
        already_used_or_not='他のサービスで使っているパスワードや名前などは絶対に使用しないでください。'
    return render_template('signup.html', already_used_or_not=already_used_or_not, nickname=nickname)

######################################################################
# 盤面を初期化
board_first = np.zeros((8,8), dtype=int)
board_first[3,3] = board_first[4,4] = 1  # White pieces
board_first[3,4] = board_first[4,3] = 2  # Black pieces

# ホームへ
@app.route('/', methods=['GET', 'POST'])
def home():
    app.logger.debug('qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq')
    nickname=get_nickname()
    roomid_password_wrong_or_not=""
    rooms_each_users=[]
    rooms_for_all_each_users=[]
    if request.method=='POST':
        if 'new_room_name' in request.form:
            if request.form['new_room_password']==request.form['new_room_password2']:
                make_new_room_with_password(request)
            else:
                roomid_password_wrong_or_not="RoomIDかPasswordが間違っています。"
        elif 'new_room_name_without_pass' in request.form:
            make_new_room_without_password(request)
        elif 'enter_room_id' in request.form:
            room=get_room(request.form['enter_room_id'])
            if room and room['for_all_or_not'] == True:
                roomid_password_wrong_or_not="無差別対戦の部屋なので、入力の必要はありません。"
            elif room and room['for_all_or_not'] == False and room['room_password']==hash_password(request.form['enter_room_password']):
                _, _, _, _, _, _, players_and_spectators_list=players_and_spectators_from_room(request.form['enter_room_id'])
                if not current_user.id in players_and_spectators_list:
                    enter_room_as_spectator(request.form['enter_room_id'])
                else:
                    roomid_password_wrong_or_not="あなたはその部屋に既に入室しています。"
            else:
                roomid_password_wrong_or_not="RoomIDかPasswordが間違っています。"
    if current_user.is_authenticated:
        get_rooms_each_users(rooms_each_users)
        get_rooms_for_all_each_users(rooms_for_all_each_users)
    return render_template('home.html', rooms_each_users=rooms_each_users, rooms_for_all_each_users=rooms_for_all_each_users, nickname=nickname, login_true_or_false=(current_user.is_authenticated), roomid_password_wrong_or_not=roomid_password_wrong_or_not)

# 部屋へ
@app.route('/room/<int:room_id>')
def room(room_id):
    app.logger.debug('yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy')
    _, _, _, _, players_list, spectators_list, players_and_spectators_list=players_and_spectators_from_room(room_id)
    if get_room(room_id)['for_all_or_not']==True:
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        elif not current_user.id in players_and_spectators_list:
            enter_room_as_spectator(room_id)
    elif not (current_user.is_authenticated and current_user.id in players_and_spectators_list):
        return 'あなたはこの部屋への入室を許可されていません'
    nickname=get_nickname()
    room=get_room(room_id)
    return render_template('room.html', room_id=room_id, room_name=room['room_name'], nickname=nickname, user_id=current_user.id)#user_idはhtmlに埋め込むため

#ホーム画面などを管理する関数
#make_new_room_with_password
def make_new_room_with_password(request):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    conn.start_transaction()
    try:
        cursor.execute("INSERT INTO room (room_name, room_password, for_all_or_not, result) VALUES (%s, %s, %s, %s)", (request.form['new_room_name'], hash_password(request.form['new_room_password']), False, str(board_first.tolist())))
        cursor.execute("SELECT LAST_INSERT_ID()")
        room_id = cursor.fetchone()['LAST_INSERT_ID()']
        cursor.execute("INSERT INTO user_room (user_ID, room_ID) VALUES (%s, %s)", (current_user.id, room_id))
        conn.commit()
    except:
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

#make_new_room_without_password
def make_new_room_without_password(request):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    conn.start_transaction()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("INSERT INTO room (room_name, room_password, for_all_or_not, result) VALUES (%s, %s, %s, %s)", (request.form['new_room_name_without_pass'], None, True, str(board_first.tolist())))
        cursor.execute("SELECT LAST_INSERT_ID()")
        room_id = cursor.fetchone()['LAST_INSERT_ID()']
        cursor.execute("INSERT INTO user_room (user_ID, room_ID) VALUES (%s, %s)", (current_user.id, room_id))
        conn.commit()
    except:
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

#enter_room_as_spectator
def enter_room_as_spectator(room_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("INSERT INTO user_room (user_ID, room_ID, is_player) VALUES (%s, %s, %s)", (current_user.id, room_id, False))
    conn.commit()
    conn.close()

#get_room
def get_room(room_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM room WHERE ID = %s", (room_id,))
    room=cursor.fetchone()
    conn.close()
    return room

#現在のユーザが入室可能な鍵付きの部屋を取得
def get_rooms_each_users(rooms_each_users):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT room.* 
        FROM room 
        JOIN user_room ON room.ID = user_room.room_ID
        JOIN user ON user.ID = user_room.user_ID
        WHERE user.ID = %s AND room.for_all_or_not = %s
    """, (current_user.id, False, ))
    rooms = cursor.fetchall()
    conn.close()
    if rooms:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        for room in rooms:
            players, spectators, how_many_players, how_many_spectators, players_list, spectators_list, players_and_spectators_list = players_and_spectators_from_room(room['ID'])
            players_nickname_list=[]
            for player in players:
                cursor.execute("SELECT * FROM user WHERE ID = %s ", (player['user_ID'],))
                player_from_user=cursor.fetchone()
                players_nickname_list.append(player_from_user['nickname'])
            spectators_nickname_list=[]
            for spectator in spectators:
                cursor.execute("SELECT * FROM user WHERE ID = %s ", (spectator['user_ID'],))
                spectator_from_user=cursor.fetchone()
                spectators_nickname_list.append(spectator_from_user['nickname'])
            rooms_each_users.append((room, players_nickname_list, spectators_nickname_list))
        conn.close()

#無差別の部屋を取得
def get_rooms_for_all_each_users(rooms_for_all_each_users):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM room WHERE for_all_or_not = %s ", (True,))
    rooms = cursor.fetchall()
    conn.close()
    if rooms:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        for room in rooms:
            players, spectators, how_many_players, how_many_spectators, players_list, spectators_list, players_and_spectators_list = players_and_spectators_from_room(room['ID'])
            players_nickname_list=[]
            for player in players:
                cursor.execute("SELECT * FROM user WHERE ID = %s ", (player['user_ID'],))
                player_from_user=cursor.fetchone()
                players_nickname_list.append(player_from_user['nickname'])
            spectators_nickname_list=[]
            for spectator in spectators:
                cursor.execute("SELECT * FROM user WHERE ID = %s ", (spectator['user_ID'],))
                spectator_from_user=cursor.fetchone()
                spectators_nickname_list.append(spectator_from_user['nickname'])
            rooms_for_all_each_users.append((room, players_nickname_list, spectators_nickname_list))
        conn.close()

######################################################################
#接続、切断
@socketio.on('join room')
def handle_connect(data):
    app.logger.debug('kkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkkk')
    join_room(data['room_id'])
    players, spectators, how_many_players, how_many_spectators, players_list, spectators_list, players_and_spectators_list = players_and_spectators_from_room(data['room_id'])
    session['user_id']=current_user.id
    session['nickname']=current_user.nickname
    session['room_id']=data['room_id']
    result = get_room(data['room_id'])['result']
    board=np.array(ast.literal_eval(result)).astype(int)
    current_turn=get_room(data['room_id'])['current_turn']
    ids_nicknames_blackorwhites_list=make_ids_nicknames_blackorwhites_list(players)
    game_finished_result_dict=None
    if np.all(board != 0):
        game_finished_result_dict=make_game_finished_result_dict(board, data['room_id'])
    player_enter_room_dict={}
    if current_user.id in players_list:
        player_enter_room_dict['nickname']=current_user.nickname
    app.logger.debug('eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee')
    emit('move made', {'board':board.tolist(), 'current_turn':current_turn, 'how_many_players':how_many_players, 'how_many_spectators':how_many_spectators, 'players_list':players_list, 'ids_nicknames_blackorwhites_list':ids_nicknames_blackorwhites_list, 'game_finished_result_dict':game_finished_result_dict, 'player_enter_room_dict':player_enter_room_dict}, room=data['room_id'])

#タブを消さないと発火しない。ホーム画面に戻っただけでは発火しない。
@socketio.on('disconnect')
def handle_disconnect():
    leave_room(session['room_id'])
    players, spectators, how_many_players, how_many_spectators, players_list, spectators_list, players_and_spectators_list = players_and_spectators_from_room(session['room_id'])
    if session['user_id'] in players_list:
        player_leave_room_dict={}
        player_leave_room_dict['nickname']=session['nickname']
        emit('disconnect from server', {'player_leave_room_dict': player_leave_room_dict}, room=session['room_id'])

#誰かが対戦ボタンを押した時
@socketio.on('start play')
def handle_start_play(data):
    players, spectators, how_many_players, how_many_spectators, players_list, spectators_list, players_and_spectators_list = players_and_spectators_from_room(data['room_id'])
    if current_user.id in players_list or 2<=how_many_players:
        return
    enter_players(data['room_id'])
    current_turn=None
    if how_many_players + 1 == 2:
        current_turn=change_turn(data['room_id'])
        players_list.append(current_user.id)
        add_black_or_white(players_list, current_turn, data['room_id'])
    players, spectators, how_many_players, how_many_spectators, players_list, spectators_list, players_and_spectators_list = players_and_spectators_from_room(data['room_id'])
    ids_nicknames_blackorwhites_list=make_ids_nicknames_blackorwhites_list(players)
    emit('move made', {'current_turn':current_turn, 'how_many_players':how_many_players, 'how_many_spectators':how_many_spectators, 'players_list':players_list, 'ids_nicknames_blackorwhites_list':ids_nicknames_blackorwhites_list}, room=data['room_id'])

#手を打った後の処理
@socketio.on('make a move')
def handle_move(data):
    if not get_room(data['room_id'])['current_turn']==current_user.id:
        return
    x, y= data['x'], data['y']
    color=get_color(data['room_id'])
    result=get_room(data['room_id'])['result']
    board=np.array(ast.literal_eval(result)).astype(int)
    if is_valid_move(board, y, x, color):
        make_move(board, y, x, color)
        update_board(board, data['room_id'])
        current_turn=change_turn(data['room_id'])
        emit('move made', {'board':board.tolist(), 'current_turn':current_turn}, room=data['room_id'])
    elif not can_move_or_not(board, color):
        current_turn=change_turn(data['room_id'])
        emit('move made', {'current_turn':current_turn}, room=data['room_id'])
    game_finished_result_dict=None
    if np.all(board != 0):
        game_finished_result_dict=make_game_finished_result_dict(board, data['room_id'])
        emit('move made', {'game_finished_result_dict':game_finished_result_dict}, room=data['room_id'])

#オセロの盤面変更のための関数
directions = [(0,1),(1,0),(0,-1),(-1,0),(1,1),(-1,-1),(1,-1),(-1,1)]

def can_move_or_not(board, color):
    for i in range(8):
        for j in range(8):
            if is_valid_move(board, i, j, color):
                return True
    return False

def is_valid_move(board, y, x, color):
    if  0 <= y < 8 and 0 <= x < 8 and board[y][x] != 0:
        return False
    for dy, dx in directions:
        if can_flip(board, y, x, dy, dx, color):
            return True
    return False

def make_move(board, y, x, color):
    board[y][x] = color
    for dy, dx in directions:
        if can_flip(board, y, x, dy, dx, color):
            flip(board, y, x, dy, dx, color)

def can_flip(board, y, x, dy, dx, color):
    y += dy
    x += dx
    if y < 0 or y > 7 or x < 0 or x > 7 or board[y][x] != 3 - color:
        return False
    while 0 <= y <= 7 and 0 <= x <= 7 and board[y][x] == 3 - color:
        y += dy
        x += dx
    return 0 <= y <= 7 and 0 <= x <= 7 and board[y][x] == color

def flip(board, y, x, dy, dx, color):
    y += dy
    x += dx
    while 0 <= y <= 7 and 0 <= x <= 7 and board[y][x] == 3 - color:
        board[y][x] = color
        y += dy
        x += dx

#試合を管理する様々な関数
# update_board
def update_board(board, room_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("UPDATE room SET result = %s WHERE ID = %s", (str(board.tolist()), room_id, ))
    conn.commit()
    conn.close()

#user_room_playersとuser_room_spectators
def players_and_spectators_from_room(room_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM user_room WHERE room_ID = %s AND is_player = %s", (room_id, True,))
    user_room_players=cursor.fetchall()
    cursor.execute("SELECT * FROM user_room WHERE room_ID = %s AND is_player = %s", (room_id, False,))
    user_room_spectators= cursor.fetchall()
    conn.close()
    user_room_players_list=[]
    for user_room_player in user_room_players:
        user_room_players_list.append(user_room_player['user_ID'])
    user_room_spectators_list=[]
    for user_room_spectator in user_room_spectators:
        user_room_spectators_list.append(user_room_spectator['user_ID'])
    return user_room_players, user_room_spectators, len(user_room_players), len(user_room_spectators), user_room_players_list, user_room_spectators_list, user_room_players_list+user_room_spectators_list

#change_turn 
def change_turn(room_id):
    user_room_players, user_room_spectators, how_many_players, how_many_spectators, user_room_players_list, user_room_spectators_list, user_room_players_and_spectators_list=players_and_spectators_from_room(room_id)
    current_turn=get_room(room_id)['current_turn']
    if 0<=how_many_players<=1:
        current_turn_next=None
    elif current_turn==None and how_many_players==2:
        current_turn_next=random.choice(user_room_players_list)
    elif user_room_players_list[0] == current_turn:
        current_turn_next = user_room_players_list[1]
    else:
        current_turn_next = user_room_players_list[0]
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("UPDATE room SET current_turn = %s WHERE ID = %s", (current_turn_next, room_id, ))
    conn.commit()
    conn.close()
    return current_turn_next

#enter_players
def enter_players(room_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("UPDATE user_room SET is_player = %s WHERE room_ID = %s AND user_ID = %s", (True, room_id, current_user.id, ))
    conn.commit()
    conn.close()

#make_ids_nicknames_blackorwhites_list
def make_ids_nicknames_blackorwhites_list(players):
    ids_nicknames_blackorwhites_list=[]
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    for player in players:
        cursor.execute("SELECT * FROM user WHERE ID = %s", (player['user_ID'], ))
        user=cursor.fetchone()
        id_nickname_blackorwhite_each_dict={}
        id_nickname_blackorwhite_each_dict['ID']=user['ID']
        id_nickname_blackorwhite_each_dict['nickname']=user['nickname']
        id_nickname_blackorwhite_each_dict['role']=player['role']
        ids_nicknames_blackorwhites_list.append(id_nickname_blackorwhite_each_dict)
    conn.close()
    return ids_nicknames_blackorwhites_list

#get_color
def get_color(room_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM user_room WHERE user_ID = %s AND room_ID = %s", (current_user.id, room_id, ))
    user_room=cursor.fetchone()
    conn.close()
    if user_room['role']=='黒（先攻）':
        color=2
    elif user_room['role']=='白（後攻）':
        color=1
    return color

#add_black_or_white
def add_black_or_white(players_list, current_turn, room_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    next_turn=players_list[0] if players_list[0] != current_turn else players_list[1]
    cursor.execute("UPDATE user_room SET role = %s WHERE room_ID = %s AND user_ID = %s", ('黒（先攻）', room_id, current_turn))
    cursor.execute("UPDATE user_room SET role = %s WHERE room_ID = %s AND user_ID = %s", ('白（後攻）', room_id, next_turn))
    conn.commit()
    conn.close()

#who_is_black_or_white
def who_is_black_or_white(room_id):
    role_black_white_list=['黒（先攻）', '白（後攻）']
    user_black_white_dict={}
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    for role_black_or_white in role_black_white_list:
        cursor.execute("SELECT * FROM user_room WHERE room_ID = %s AND is_player = %s AND role = %s", (room_id, True, role_black_or_white, ))
        player_black_or_white=cursor.fetchone()
        cursor.execute("SELECT * FROM user WHERE ID = %s", (player_black_or_white['user_ID'], ))
        user_black_or_white=cursor.fetchone()
        user_black_white_dict[role_black_or_white]=user_black_or_white
    conn.close()
    return user_black_white_dict

def make_game_finished_result_dict(board, room_id):
    count_1_white = int(np.sum(board == 1))
    count_2_black = int(np.sum(board == 2))
    user_black_white_dict=who_is_black_or_white(room_id)
    game_finished_result_dict={}
    game_finished_result_dict['黒（先攻）']={'nickname': user_black_white_dict['黒（先攻）']['nickname'], 'count_2_black': count_2_black}
    game_finished_result_dict['白（後攻）']={'nickname': user_black_white_dict['白（後攻）']['nickname'], 'count_1_white': count_1_white}
    return game_finished_result_dict

######################################################################
# 実行
if __name__ == '__main__':
    socketio.run(app, debug=False, host='0.0.0.0', port=5000)
