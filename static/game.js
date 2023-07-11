document.addEventListener("DOMContentLoaded", function(){
    var socket = io()

    //接続、切断
    socket.on('connect', function() {
        console.log('fffffffffffffffffffffffffffffffffffffffff')
        socket.emit('join room', {'room_id':document.getElementById("room_id").textContent});
        if(document.getElementById("player_or_spectator").textContent=='対戦者'){
        }
        console.log('qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq')
    });
    socket.on('disconnect from server', function(data) {
        document.getElementById("players_condition").textContent = data['player_leave_room_dict']['nickname'] +  " さんが通信を切断したかもしれません。";
    });

    //対戦を始めるボタンをクリック
    var start_play_button = document.getElementById('start_play');
    start_play_button.addEventListener('click', function(e) {
        socket.emit('start play', {'room_id':document.getElementById("room_id").textContent});
    })

    //クリックで手を打つ
    var board = document.getElementById('board');
    board.addEventListener('click', function(e) {
        var rect = board.getBoundingClientRect();
        var x = Math.floor((e.clientX - rect.left) / (rect.width / 8));
        var y = Math.floor((e.clientY - rect.top) / (rect.height / 8));
        socket.emit('make a move', {'x': x, 'y': y, 'room_id':document.getElementById("room_id").textContent});
    });

    //socketでpythonから受け取り
    socket.on('move made', function(data) {
        console.log('dddddddddddddddddddddddddddddddddddddddddddddd')
        if(data.hasOwnProperty('board')){
            updateBoard(data['board'])
        }
        if(data.hasOwnProperty('how_many_players')){
            document.getElementById("how_many_players").textContent = data['how_many_players']
        }      
        if(data.hasOwnProperty('how_many_spectators')){
            document.getElementById("how_many_spectators").textContent = data['how_many_spectators']
        }
        var spectator_button = document.getElementById("spectator_button");
        if (data.hasOwnProperty("players_list")){
            if(data["players_list"].includes(parseInt(document.getElementById("hidden_user_id").value))){
                document.getElementById("player_or_spectator").textContent="対戦者"
                spectator_button.style.display = "none";
            }else{
                document.getElementById("player_or_spectator").textContent="観戦者"
                spectator_button.style.display = "block";
                if(data["players_list"].length==2){
                    document.getElementById("players_already_decided").textContent="対戦者はすでに決まっています。"
                }
            }
        }
        if(data.hasOwnProperty('current_turn')){
            if(document.getElementById("player_or_spectator").textContent=='対戦者'){
                if(parseInt(document.getElementById("hidden_user_id").value) == data['current_turn']){
                    document.getElementById("current_turn").textContent='あなたのターンです'
                }else{
                    document.getElementById("current_turn").textContent='あなたのターンではありません'
                }
            }
        }
        if(data.hasOwnProperty('ids_nicknames_blackorwhites_list')){
            let vs_members = '';
            if(data['ids_nicknames_blackorwhites_list'].length==1){
                vs_members = data['ids_nicknames_blackorwhites_list'][0]['nickname'] + ' vs ???'
            }
            if(data['ids_nicknames_blackorwhites_list'].length==2){
                vs_members = data['ids_nicknames_blackorwhites_list'][0]['nickname']+' '+data['ids_nicknames_blackorwhites_list'][0]['role'] + ' vs ' + data['ids_nicknames_blackorwhites_list'][1]['nickname']+' '+data['ids_nicknames_blackorwhites_list'][1]['role']
            }
            document.getElementById("players_nickname").textContent = vs_members
        }
        if(data.hasOwnProperty('game_finished_result_dict') && data['game_finished_result_dict']!=null){
            var game_condition_text="対戦が終了しました。";
            game_condition_text += data['game_finished_result_dict']['黒（先攻）']['nickname'] + '（黒）さんが' + data['game_finished_result_dict']['黒（先攻）']['count_2_black'] + '個です。'
            game_condition_text += data['game_finished_result_dict']['白（後攻）']['nickname'] + '（白）さんが' + data['game_finished_result_dict']['白（後攻）']['count_1_white'] + '個です。'
            document.getElementById("game_condition").textContent = game_condition_text;
        }
        if(data.hasOwnProperty('player_enter_room_dict') && Object.keys(data['player_enter_room_dict']).length !== 0){
            document.getElementById("players_condition").textContent = data['player_enter_room_dict']['nickname'] +  " さんが接続しました";
        }
    });

    //盤面を表示する関数。
    function updateBoard(board) {
        for (let i = 0; i < 8; i++) {
            for (let j = 0; j < 8; j++) {
                let cell = document.getElementById(`cell-${i}-${j}`);
                if (board[i][j] == 1) {
                    cell.className = "cell white";
                } else if (board[i][j] == 2) {
                    cell.className = "cell black";
                } else {
                    cell.className = "cell";
                }
            }
        }
    }
});
