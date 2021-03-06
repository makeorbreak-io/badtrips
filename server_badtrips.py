from flask import Flask, session, request, jsonify, send_from_directory, escape
import os
import json
import redis
import wrapper_yelp
import google_photo

r = redis.Redis(host='localhost', port=6379, password='')
app = Flask("badtrips", static_url_path='')
app.secret_key = 'A0Zr98j/3yX R~XHH!jmN]LWX/,?RZ'
static_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'static')


@app.route('/static/<path:path>')
def send_js(path):
    return send_from_directory(static_dir, path)


@app.route('/')
def index():
    '''
    Starting page
    user chooses the location of the game
    :return:
    '''
    return send_from_directory(static_dir, 'index.html')


@app.route('/play', methods=['POST'])
def play():
    '''
    Must recieve a location in the request
    if we dont have a location generate a random one?

    :return:
    '''
    id = newGame(request.form['location'], request.form['username'])
    session['id'] = id
    app.logger.debug('New game created with location: '+ request.form['location'] +' id: ' + str(id))
    return send_from_directory(static_dir, 'play.html')


@app.route('/newquestion', methods=['POST'])
def newQuestion():
    '''
    Create a new question from yelp
    returns a json with:
     id: this question id, to check the correct responce
     A:
     B:
    :return:
    '''
    game = getGame(session['id'])
    app.logger.debug("New question from "+ str(session['id']) +"\nGame object: "+ str(game) +"\n"  )
    if game['state'] != "playing":
        return jsonify({"state":"no no no no"})
    question, answer, worst_rev = wrapper_yelp.createNewQuestion(game['location'])
    if question['A']['image_url'] == "":
        app.logger.debug("A sem imagem")
        try:
            question['A']['image_url'] = google_photo.get_photo(question['A']['name'],
                                                            (question['A']['coordinates.latitude'], question['A']['coordinates.longitude']))
        except:
            question['A']['image_url'] = "/static/burger.jpg"
    if question['B']['image_url'] == "":
        app.logger.debug("B sem imagem")
        try:
            question['B']['image_url'] = google_photo.get_photo(question['B']['name'],
                                                            (question['B']['coordinates.latitude'], question['B']['coordinates.longitude']))
        except:
            question['B']['image_url'] = "/static/burger.jpg"
    store_answer(answer, session['id'], game)
    store_review(worst_rev, session['id'], game)
    return jsonify(question)


@app.route('/answer', methods=['POST'])
def answer():
    '''
    will recieve answer:<nome>
    :return:
    '''
    answer = request.form['answer']
    game = getGame(session['id'])
    if game['state'] != "playing":
        return jsonify({"state":"no no no no"})
    response, correct_answer, review = check_answer(answer, session['id'], game)
    app.logger.debug("New answer from " + str(session['id']) +"\nGame object: " + str(game) + "\nAnswer: " + answer)
    if response:
        return jsonify({"correct": True, "answer": correct_answer, "review": review})
    else:
        app.logger.debug("GAME OVER")
        register_gameover(session['id'], game)
        return jsonify({"correct": False, "answer": correct_answer, "review": review})


@app.route('/leaderboard',methods=['POST'])
def lead():
    game = getGame(session['id'])
    l = leaderboard(game)
    j = []
    for i  in l:
        print(i)
        j.append([escape(str(i[0], 'latin-1')),i[1]])
    print(j)
    return jsonify(j)


@app.route('/answermulti', methods=['POST'])
def answermulti():
    answer = request.form['answer']
    user = request.form['user']
    game = getGame(session['id'])
    if game['state'] != "playing":
        return jsonify({"state":"no no no no"})
    response, correct_answer, review = check_answer_multi(answer, user, session['id'], game)
    return jsonify({"correct": response, "answer": correct_answer, "review": review})


@app.route('/playmulti', methods=['POST'])
def multi():
    p1_name = "p1"
    p2_name = "p2"
    id = newMultiGame(request.form['location'], p1_name, p2_name)
    session['id'] = id
    app.logger.debug('New multiplayer game created with location: ' + request.form['location'] + ' id: ' + str(id))
    return send_from_directory(static_dir, 'playmulti.html')


def newGame(location, username):
    '''
    create a new game that has a location, username, id, score and state
    :return: session id
    '''
    id = os.urandom(32)
    game = {
        "location": location,
        "score": 0,
        "username": username,
        "state": "playing"
    }
    r.set(id, json.dumps(game))
    return id


def getGame(id):
    '''
    get a game session from redis
    :param id:
    :return:
    '''
    game = r.get(id)
    print("game from redis")
    print(game)
    return json.loads(game)


def store_answer(answer, id, game):
    '''
    store a answer for a game
    :param answer:
    :param game:
    :param id:
    :return:
    '''
    game["answer"] = answer
    r.set(id, json.dumps(game))


def store_review(review, id, game):
    '''
    store a review for a game
    :param review:
    :param game:
    :param id:
    :return:
    '''
    game["review"] = review
    r.set(id, json.dumps(game))	


def leaderboard(game):
    l = r.zrevrange("scores" + game['location'], 0, 5, withscores=True)
    print(l)
    return l


def register_gameover(id, game):
    '''
    Register in the db this user score and set the state to gameover
    :param id:
    :param game:
    :return:
    '''
    game['state'] = 'gameover'
    r.set(id, json.dumps(game))
    score = r.zscore("scores" + game['location'], game["username"])
    app.logger.debug("SCORE IN BD: " + str(score))
    if score is not None:
        if score < game['score']:
            app.logger.debug("ADDING score to leaderboard")
            r.zadd("scores"+ game['location'], game['username'], game['score'])
    else:
        app.logger.debug("ADDING score to leaderboard")
        r.zadd("scores" + game['location'], game['username'], game['score'])


def check_answer_multi(answer, user, id, game):
    if game["answer"] == answer:
        if user == 1:
            game['p1_score'] += 1
        elif user == 2:
            game['p2_score'] += 1
        r.set(id, json.dumps(game))
        return True, game['answer'], game['review']
    return False, game['answer'], game['review']


def check_answer(answer, id, game):
    '''
    Check if the user answer is correct and updates the user score in the db
    :param answer: the user answer
    :param id: this game id
    :param game: this game session
    :return: True if is correct,false if incorrect and
    '''
    if game["answer"] == answer:
        game["score"] += 1
        r.set(id, json.dumps(game))
        return True, game["answer"], game['review']
    return False, game["answer"], game['review']


def newMultiGame(location, p1, p2):
    id = os.urandom(32)
    game = {
        "location": location,
        "score_p1": 0,
        "score_p2": 0,
        "p1": p1,
        "p2": p2,
        "state": "playing"
    }
    r.set(id, json.dumps(game))
    return id