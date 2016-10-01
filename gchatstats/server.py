import tornado.web, datetime, requests, time, sqlite3, json, os, pymorphy2, re, traceback, collections

#--------------------------
# Обработка запросов и логирование
   
def send_msg_to_admin(text):
    url = 'https://api.telegram.org/bot%s/sendMessage' % tg_report_token
    params = {'chat_id' : tg_report_chat_id, 'text' : text}
    requests.get(url, params=params)

def make_report():
    report = '=== Report: ===\n'
    report += 'gchatstats (%s)\n' % server_url
    with sqlite3.connect(data_dir + '/errors.lite') as conn:
        c = conn.cursor()
        if is_table_exists(conn, 'errors'):
            count, = c.execute('SELECT count(*) FROM errors WHERE julianday("now") - julianday(date, "-3 hours") < 1.2').fetchone()
        else:
            count = 0
        report += 'Error requests: %d\n' % count
    with sqlite3.connect(data_dir + '/requests.lite') as conn:
        c = conn.cursor()
        if is_table_exists(conn, 'requests'):
            count, = c.execute('SELECT count(*) FROM requests WHERE julianday("now") - julianday(date, "-3 hours") < 1.2').fetchone()
        else:
            count = 0
        report += 'All requests: %d\n' % count
    send_msg_to_admin(report)

def log_error(page, message, info, ip):
    with sqlite3.connect(data_dir + '/errors.lite') as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS errors
                  (page text, message text, info text, date text, ip text)''')
        date = datetime.datetime.now().isoformat(' ')
        values = (page, message, info, date, ip)
        c.execute('INSERT INTO errors (page, message, info, date, ip) VALUES (?, ?, ?, ?, ?)', values)
        conn.commit()
    return c.lastrowid

class CORSHandler(tornado.web.RequestHandler):

    def prepare(self):
        referer = self.request.headers.get("Referer", '')
        agent = self.request.headers.get("User-Agent", '')
        ip = self.request.remote_ip + ' ' + agent
        url = self.request.full_url()
        with sqlite3.connect(data_dir + '/requests.lite') as conn:
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS requests
                      (referer text, url text, date text, ip text)''')
            date = datetime.datetime.now().isoformat(' ')
            values = (referer, url, date, ip)
            c.execute('INSERT INTO requests (referer, url, date, ip) VALUES (?, ?, ?, ?)', values)
            conn.commit()

    def log_exception(self, typ, value, tb):
        descr = '\n'.join(traceback.TracebackException(type(value), value, tb).format(chain=True))        
        super(CORSHandler, self).log_exception(typ, value, tb)
        send_msg_to_admin(descr)

    def set_default_headers(self):
        if client_url != server_url:
            self.set_header("Access-Control-Allow-Origin", client_url)
            self.set_header("Access-Control-Allow-Headers", "x-requested-with")
            self.set_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')

    def options(self):
        self.set_status(204)
        self.finish()

        
class ErrorLog(CORSHandler):

    def post(self):
        page = self.get_argument('page')
        message = self.get_argument('message')
        info = self.get_argument('info')
        agent = self.request.headers.get("User-Agent", '')
        ip = self.request.remote_ip + ' ' + agent
        log_error(page, message, info, ip)
        send_msg_to_admin(message)

        
class NotFound(CORSHandler):

    def handler(self):
        page = self.request.headers.get("Referer", '')
        message = '404: %s' % self.request.full_url()
        agent = self.request.headers.get("User-Agent", '')
        ip = self.request.remote_ip + ' ' + agent
        info = ''
        log_error(page, message, info, ip)
        send_msg_to_admin(message)
        self.set_status(404)
        self.finish()
        
    def post(self):
        self.handler()
    
    def get(self):
        self.handler()

def start_minute_loop():
    global last_report_date
    every_minute()
    now = datetime.datetime.now()
    cur_date = now.date().isoformat()
    if cur_date != last_report_date:
        last_report_date = cur_date
        every_midnight()
    ioloop = tornado.ioloop.IOLoop.current()
    ioloop.call_later(60, start_minute_loop)

def every_minute():
    process_telegram_updates()

def every_midnight():
    make_report()


#--------------------------
# Вспомогательные функции для работы с базой данных

def is_table_exists(conn, table_name):
    c = conn.cursor()
    query = 'SELECT name FROM sqlite_master WHERE type="table" AND name=?'
    return len(c.execute(query, (table_name,)).fetchall()) > 0

def connect_meta():
    return sqlite3.connect(data_dir + '/chat_meta.lite')

def prepare_meta_database():
    with connect_meta() as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS vk_chat
                  (hash text primary key, user_id int, chat_id text, chat_name text,
                   date text, ip text, first_msg_stamp int, last_msg_stamp int, msg_count int)''')
        c.execute('''CREATE TABLE IF NOT EXISTS tg_chat
                  (chat_id text primary key, type text, chat_name text, user_id text,
                   date text, update_id int, first_msg_stamp int, last_msg_stamp int, msg_count int)''')
        conn.commit()

def prepare_word_tables(conn):
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS message
              (id int primary key, user_id int, stamp int, body text, special_chars int, word_count int)''')
    c.execute('''CREATE TABLE IF NOT EXISTS word
              (word text primary key, pos text)''')
    c.execute('''CREATE TABLE IF NOT EXISTS msg_word
              (msg int, word int, unique (msg, word))''')
    conn.commit()

def db_path(site, hsh):
    return data_dir + '/' + site + str(hsh) + '.lite'

def connect_vk(hsh):
    return sqlite3.connect(db_path('vk', hsh))

def connect_tg(chat_id):
    return sqlite3.connect(db_path('tg', chat_id))

def prepare_vk_database(hsh):
    with connect_vk(hsh) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS user
                  (user_id text primary key, first_name text, last_name text, photo_50 text)''')
        c.execute('''CREATE TABLE IF NOT EXISTS invitation
          (user_id text primary key, invited_by text)''')
        c.execute('''CREATE TABLE IF NOT EXISTS raw_messages_chunk
                  (data text)''')
        conn.commit()
        prepare_word_tables(conn)        

def prepare_tg_database(chat_id):
    with connect_tg(chat_id) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS raw_messages_chunk
              (update_id text primary key, date text, data text)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user
          (user_id text primary key, first_name text, last_name text, username text)''')
        c.execute('''CREATE TABLE IF NOT EXISTS invitation
          (user_id text primary key, invited_by text)''')
        conn.commit()
        prepare_word_tables(conn)

def clear_cache(conn, keep_messages=True):
    q = conn.cursor().execute('SELECT name FROM sqlite_master WHERE type="table"')
    for table_name, in q.fetchall():
        if table_name in ['user', 'raw_messages_chunk', 'invitation']:
            continue
        if keep_messages:
            if table_name in ['message', 'word', 'msg_word']:
                continue
        conn.execute('DROP TABLE %s' % table_name)

def cache_exists(conn):
    return is_table_exists(conn, 'word_count')


#--------------------------
# Обработка запросов для VK

class UploadVkUsers(CORSHandler):
    def post(self):
        prepare_meta_database()
        with connect_meta() as conn:
            c = conn.cursor()
            date = datetime.datetime.now().isoformat(' ')
            agent = self.request.headers.get("User-Agent", '')
            ip = self.request.remote_ip + ' ' + agent
            hsh = self.get_argument('hash')
            user_id = self.get_argument('user_id')
            chat_name = self.get_argument('chat_name')
            chat_id = self.get_argument('chat_id')
            values = (hsh, user_id, chat_id, chat_name, date, ip)
            c.execute('INSERT INTO vk_chat (hash, user_id, chat_id, chat_name, date, ip) VALUES (?, ?, ?, ?, ?, ?)', values) 
            conn.commit()
        prepare_vk_database(self.get_argument('hash'))
        with connect_vk(self.get_argument('hash')) as conn:
            c = conn.cursor()
            users_data = json.loads(self.get_argument('users_data'))
            values = []
            invited_by_vals = []
            for user in users_data:
                cur_row = []
                for field in ['id', 'first_name', 'last_name', 'photo_50']:
                    cur_row.append(user[field])
                invited_by_vals.append((user['id'], user['invited_by']))
                values.append(cur_row)
            c.executemany('''INSERT OR REPLACE INTO user
                (user_id, first_name, last_name, photo_50)
                VALUES (?, ?, ?, ?)''', values)
            c.executemany('''INSERT OR REPLACE INTO invitation
                (user_id, invited_by)
                VALUES (?, ?)''', invited_by_vals)
            conn.commit()

class UploadVkMessages(CORSHandler):
    def post(self):
        with connect_vk(self.get_argument('hash')) as conn:
            c = conn.cursor()
            c.execute('INSERT INTO raw_messages_chunk (data) VALUES (?)', (self.get_argument('messages'),))
            conn.commit()
            parse_messages(conn, json.loads(self.get_argument('messages')))

class UploadVkFinalize(CORSHandler):
    def post(self):
        with connect_vk(self.get_argument('hash')) as conn:
            with connect_meta() as meta_conn:
                generate_cache(conn, meta_conn, 'vk', self.get_argument('hash'))


#--------------------------
# Работа с текстом

def get_words(text):
    res = []
    for word in re.findall('[а-яА-Я]+', text):
        variant = morph.parse(word)[0]
        if variant.normal_form.lower() in stopwords:
            continue
        res.append((variant.normal_form, variant.tag.POS))
    return res

def count_special_chars(text):
    res = 0
    for char in text:
        if not char.isalnum() and not char.isspace():
            res += 1
    return res

def parse_messages(conn, messages):
    c = conn.cursor()
    words = c.execute('SELECT word FROM word ORDER BY rowid ASC').fetchall()
    max_word_id = len(words)
    word_invidx = {
        word[0]: pos + 1
        for pos, word in enumerate(words)
    }
    message_values = []
    word_values = []
    msg_word_values = []
    for message in messages:
        msg_id = message['id']
        user_id = message['user_id']
        stamp = message['date']
        body = message['body']
        special_chars = count_special_chars(body)
        msg_words = get_words(body)
        word_count = len(msg_words)
        cur_row = (msg_id, user_id, stamp, body, special_chars, word_count)
        message_values.append(cur_row)
        for word, pos in msg_words:
            word_id = word_invidx.get(word, None)
            if word_id is None:
                word_id = max_word_id + 1
                max_word_id = word_id
                word_values.append((word, pos))
                word_invidx[word] = word_id
            msg_word_values.append((msg_id, word_id))
    c.executemany('''INSERT OR IGNORE INTO word
        (word, pos) VALUES (?, ?)''', word_values)
    c.executemany('''INSERT OR IGNORE INTO msg_word
        (msg, word) VALUES (?, ?)''', msg_word_values)
    c.executemany('''INSERT OR IGNORE INTO message
        (id, user_id, stamp, body, special_chars, word_count) \
        VALUES (?, ?, ?, ?, ?, ?)''', message_values)
    conn.commit()


#--------------------------
# Работа с telegram

def send_tg_msg(typ, chat_id):
    view_url = server_url + '/tg' + str(chat_id)
    if typ == 'greet':
        text = 'Всем привет! Я буду собирать статистику для этого чата. ' + \
                'Она будет доступна по адресу %s' % view_url 
    elif typ == 'reminder':
        text = 'Кто-то меня упоминал? Если что, вот ссылка:\n %s' % view_url
    params = {
        'chat_id': chat_id,
        'text': text
    }
    r = requests.get('https://api.telegram.org/bot%s/sendMessage' % main_bot_token, params)

def get_next_update_id():
    with connect_meta() as conn:
        if is_table_exists(conn, 'tg_chat'):
            c = conn.cursor()
            res, = c.execute('SELECT max(update_id) FROM tg_chat').fetchone()
            return (res or 0) + 1
        else:
            return 0

def get_message_from_update(update):
    if 'message' in update:
        return update['message']
    elif 'edited_message' in update:
        return update['edited_message']
    return None

def join_name(first_name, last_name):
    t = []
    if first_name:
        t.append(first_name)
    if last_name:
        t.append(last_name)
    if len(t) == 0:
        return None
    return ' '.join(t)

def process_telegram_updates():
    
    prepare_meta_database()
    params = {
        'offset': get_next_update_id()
    }
    r = requests.get('https://api.telegram.org/bot%s/getUpdates' % main_bot_token, params)
    updates = json.loads(r.text)['result']

    by_chat_id = {}
    for update in updates:
        message = get_message_from_update(update)
        if message is None:
            continue
        chat_id = message['chat']['id']
        if chat_id not in by_chat_id:
            by_chat_id[chat_id] = []
        by_chat_id[chat_id].append(update)

    uploaded_users = [] # (uploaded_user_id, chat_id), ..
    for chat_id, updates in by_chat_id.items():
        prepare_tg_database(chat_id)
        with connect_tg(chat_id) as conn:
            c = conn.cursor()

            values = []
            for update in updates:
                update_id = update['update_id']
                data = json.dumps(update)
                date = datetime.datetime.now().isoformat(' ')
                values.append((update_id, data, date))
            c.executemany('INSERT OR REPLACE INTO raw_messages_chunk \
                          (update_id, date, data) VALUES (?, ?, ?)', values)
            conn.commit()
            values = []

            for update in updates:
                if 'message' in update and \
                'new_chat_member' in update['message'] and \
                'from' in update['message']:
                    user_id = update['message']['new_chat_member']['id']
                    invited_by = update['message']['from']['id']
                    values.append((user_id, invited_by))
                    bot_id = int(main_bot_token.split(':')[0])
                    if user_id == bot_id:
                        uploaded_users.append((invited_by, chat_id))
                        send_tg_msg('greet', chat_id)
                elif 'message' in update and update['message'].get('text') == '/start' \
                and update['message']['chat']['type'] == 'private':
                    uploaded_users.append((update['message']['chat']['id'], chat_id))
                    send_tg_msg('greet', chat_id)
            if len(values) > 0:
                c.executemany('INSERT OR REPLACE INTO invitation (user_id, invited_by) VALUES (?, ?)', values)
                conn.commit()

            users = {}
            for update in updates:
                if 'message' not in update or 'from' not in update['message']:
                    continue
                user = update['message']['from']
                users[user['id']] = (
                    user['id'],
                    user.get('first_name'),
                    user.get('last_name'),
                    user.get('username')
                )
            query = 'INSERT OR REPLACE INTO user (user_id, first_name, last_name, username) VALUES (?, ?, ?, ?)'
            c.executemany(query, list(users.values()))
            conn.commit()

            mentioned = False
            messages = []
            for update in updates:
                if 'message' not in update or \
                'from' not in update['message'] or \
                'text' not in update['message']:
                    continue
                message = update['message']
                from_user = message['from']
                messages.append({
                    'id': message['message_id'],
                    'user_id': from_user['id'],
                    'date': message['date'],
                    'body': message['text']
                })
                if 'gchatstats' in message['text']:
                    mentioned = True
                parse_messages(conn, messages)
            if mentioned:
                send_tg_msg('reminder', chat_id)
            
            clear_cache(conn)

    with connect_meta() as conn:
        c = conn.cursor()
        chat_vals = []
        chat_ids = []
        for chat_id, updates in by_chat_id.items():
            for update in updates:
                message = get_message_from_update(update)
                chat = message['chat']
                update_id = update['update_id']
            date = datetime.datetime.now().isoformat(' ')
            chat_type = chat['type']
            chat_name = chat.get('title') or join_name(chat.get('first_name'), chat.get('last_name'))
            chat_vals.append((chat_type, chat_name, date, update_id, chat_id))
            chat_ids.append((chat_id,))
        c.executemany('INSERT OR IGNORE INTO tg_chat (chat_id) VALUES (?)', chat_ids)
        c.executemany('''UPDATE tg_chat
                         SET type=?, chat_name=?, date=?, update_id=?
                         WHERE chat_id=?''', chat_vals)
        c.executemany('''UPDATE tg_chat SET user_id=? WHERE chat_id=?''', uploaded_users)
        conn.commit()


#--------------------------
# Создание кеша с результатами анализа

def create_msg_stats(conn, meta_conn, site, chat_id):
    query = '''
    SELECT
        min(stamp) as min_stamp,
        max(stamp) as max_stamp,
        count(*) as msg_count
    FROM message'''
    res = conn.cursor().execute(query).fetchone()
    query = '''
    UPDATE %s_chat
    SET first_msg_stamp=?,
        last_msg_stamp=?,
        msg_count=?
    WHERE %s = ?'''
    params = (site, 'hash' if site == 'vk' else 'chat_id')
    meta_conn.cursor().execute(query % params, res + (chat_id,))
    meta_conn.commit()

def create_word_count(conn):
    query = '''
    CREATE TABLE IF NOT EXISTS word_count
    AS SELECT
        word.rowid as word_id,
        count(*) as msg_count
    FROM msg_word
    JOIN word ON word.rowid = msg_word.word
    GROUP BY msg_word.word
    ORDER BY msg_count DESC'''
    conn.cursor().execute(query)
    conn.commit()

def create_top_words(conn, min_msg_count, top_count):
    query = '''
    CREATE TABLE IF NOT EXISTS top_words
    AS SELECT
        word_count.word_id as word_id,
        word.word as word,
        word.pos as pos,
        word_count.msg_count as msg_count
    FROM word_count
    JOIN word ON word.rowid = word_count.word_id
    WHERE msg_count > ?
    ORDER BY msg_count DESC LIMIT ?'''
    conn.cursor().execute(query, (min_msg_count, top_count))
    conn.commit()

def create_user_pos(conn):
    query = '''
    CREATE TABLE IF NOT EXISTS user_pos
    AS SELECT
        user.user_id as user_id,
        word.pos as pos,
        count(*) as cnt
    FROM msg_word
    JOIN word ON word.rowid = msg_word.word
    JOIN message ON msg_word.msg = message.id
    JOIN user ON message.user_id = user.user_id
    GROUP BY user.user_id, word.pos'''
    conn.cursor().execute(query)
    conn.commit()

def create_user_stats(conn):
    query = '''
    CREATE TABLE IF NOT EXISTS user_stats
    AS SELECT
        user.user_id as user_id,
        count(*) as msg_count,
        sum(length(message.body)) as total_chars,
        sum(message.word_count) as total_words,
        sum(message.special_chars) as total_special_chars
    FROM message
    JOIN user ON message.user_id = user.user_id
    GROUP BY user.user_id'''
    conn.cursor().execute(query)
    conn.commit()

temporal_selector = {
    'hour' : "strftime('%H', stamp, 'unixepoch')",
    'dow' : "strftime('%w', stamp, 'unixepoch')",
    'week' : "date(stamp, 'unixepoch', 'weekday 6')",
    'month' : "strftime('%Y-%m', stamp, 'unixepoch', 'start of month')",
}

def create_temporal(conn, by):
    query = '''
    CREATE TABLE IF NOT EXISTS temporal_%s
    AS SELECT
        %s as period,
        count(*) as msg_count,
        count(distinct user_id) as active_users,
        sum(special_chars) as total_punct,
        sum(length(body)) as total_chars,
        sum(word_count) as total_words
    FROM message GROUP BY period'''
    params = (by, temporal_selector[by])
    conn.cursor().execute(query % params)
    conn.commit()

def create_temporal_word(conn, by):
    query = '''
    CREATE TABLE IF NOT EXISTS temporal_%s_word
    AS SELECT
        %s as period,
        word.rowid as word_id,
        count(*) as msg_count
    FROM msg_word
    JOIN word ON word.rowid = msg_word.word
    JOIN message ON message.id = msg_word.msg
    GROUP BY period, word_id'''
    params = (by, temporal_selector[by])
    conn.cursor().execute(query % params)
    conn.commit()
    query = '''CREATE INDEX IF NOT EXISTS temporal_%s_word_idx
               ON temporal_%s_word (word_id)'''
    params = (by, by)
    conn.cursor().execute(query % params)
    conn.commit()

def create_temporal_user(conn, by):
    query = '''
    CREATE TABLE IF NOT EXISTS temporal_%s_user
    AS SELECT
        %s as period,
        user_id,
        count(*) as msg_count
    FROM message GROUP BY period, user_id'''
    params = (by, temporal_selector[by])
    conn.cursor().execute(query % params)
    conn.commit()
    query = '''CREATE INDEX IF NOT EXISTS temporal_%s_user_idx
               ON temporal_%s_user (user_id)'''
    params = (by, by)
    conn.cursor().execute(query % params)
    conn.commit()

def create_user_word(conn):
    query = '''
    CREATE TABLE IF NOT EXISTS user_word
    AS SELECT
        message.user_id as user_id,
        word.rowid as word_id,
        count(*) as msg_count
    FROM msg_word
    JOIN word ON word.rowid = msg_word.word
    JOIN message ON message.id = msg_word.msg
    GROUP BY user_id, word_id'''
    conn.cursor().execute(query)
    conn.commit()
    query = '''CREATE INDEX IF NOT EXISTS user_word_idx
               ON user_word (user_id, word_id)'''
    conn.cursor().execute(query)
    conn.commit()

def create_temporal_top_word(conn, by, min_msg_count, top_count):
    query = 'CREATE TABLE IF NOT EXISTS temporal_%s_top_word \
             (period text, word_id text, word text, pos text, \
              msg_count int, total_count int, rel_coeff real)' % by
    conn.cursor().execute(query)
    conn.commit()
    query = 'SELECT period FROM temporal_%s' % by
    periods = conn.cursor().execute(query).fetchall()
    params = (by, by, by, by, by, by, min_msg_count, top_count)
    query = '''
    INSERT INTO temporal_%s_top_word
    (period, word_id, word, pos, msg_count, total_count, rel_coeff)
    SELECT
        period,
        word.rowid as word_id,
        word.word as word,
        word.pos as pos,
        temporal_%s_word.msg_count as msg_count,
        word_count.msg_count as total_count,
        temporal_%s_word.msg_count * 1.0 / word_count.msg_count as rel_coeff
    FROM temporal_%s_word
    JOIN word ON word.rowid = temporal_%s_word.word_id
    JOIN word_count ON word_count.word_id = word.rowid
    WHERE period = ? AND temporal_%s_word.msg_count >= %d
    ORDER BY rel_coeff DESC LIMIT %d''' % params
    conn.cursor().executemany(query, periods)
    conn.commit()

def create_user_top_word(conn, min_msg_count, top_count):
    query = 'CREATE TABLE IF NOT EXISTS user_top_word \
             (user_id text, word_id text, word text, pos text, \
              msg_count int, total_count int, rel_coeff real)'
    conn.cursor().execute(query)
    conn.commit()
    query = 'SELECT user_id FROM user'
    user_ids = conn.cursor().execute(query).fetchall()
    params = (min_msg_count, top_count)
    query = '''
    INSERT INTO user_top_word
    (user_id, word_id, word, pos, msg_count, total_count, rel_coeff)
    SELECT
        user_id,
        word.rowid as word_id,
        word.word as word,
        word.pos as pos,
        user_word.msg_count as msg_count,
        word_count.msg_count as total_count,
        user_word.msg_count * 1.0 / word_count.msg_count as rel_coeff
    FROM user_word
    JOIN word ON word.rowid = user_word.word_id
    JOIN word_count ON word_count.word_id = word.rowid
    WHERE user_id = ? AND user_word.msg_count >= %d
    ORDER BY rel_coeff DESC LIMIT %d''' % params
    conn.cursor().executemany(query, user_ids)
    conn.commit()

def create_communication(conn):
    edges_cnt = collections.Counter()
    msg_cnt = collections.Counter()
    c = conn.cursor()
    msg_infos = c.execute('SELECT user_id FROM message').fetchall()
    prev_user_id = None
    for user_id, in msg_infos:
        msg_cnt[user_id] += 1
        if prev_user_id is not None:
            if prev_user_id > user_id:
                edges_cnt[(user_id, prev_user_id)] += 1
            else:
                edges_cnt[(prev_user_id, user_id)] += 1
        prev_user_id = user_id
    total_msg = sum(msg_cnt.values())
    common = edges_cnt.most_common()
    values = []
    for (fr, to), c in common:
        if fr == to:
            continue
        if c <= 1:
            continue
        expectation = msg_cnt[fr] * msg_cnt[to] / total_msg
        coeff = c / expectation
        values.append((coeff, fr, to, c))
    values.sort(reverse=True)
    query = 'CREATE TABLE IF NOT EXISTS communication \
            (from_id text, to_id text, msg_count int, coeff real)'
    conn.cursor().execute(query)
    query = 'INSERT INTO communication(coeff, from_id, to_id, msg_count) VALUES (?, ?, ?, ?)'
    conn.cursor().executemany(query, values)
    conn.commit()

def generate_cache(conn, meta_conn, site, chat_id):
    create_msg_stats(conn, meta_conn, site, chat_id)
    create_word_count(conn)
    create_top_words(conn, min_msg_count=2, top_count=200)
    create_user_pos(conn)
    create_user_stats(conn)
    create_user_word(conn)
    create_user_top_word(conn, min_msg_count=2, top_count=10)
    for by in temporal_selector:
        create_temporal(conn, by)
        create_temporal_user(conn, by)
        create_temporal_word(conn, by)
        create_temporal_top_word(conn, by, min_msg_count=2, top_count=10)
    create_communication(conn)


#--------------------------
# Выдача результатов анализа в виде json

def dict_query(conn, query, *args):
    cols = []
    res = []
    r = conn.cursor()
    r.execute(query, *args)
    for col_pos, col_descr in enumerate(r.description):
        col_name = col_descr[0]
        cols.append(col_name)
    for row in r.fetchall():
        res_row = {}
        for col_name, val in zip(cols, row):
            res_row[col_name] = val
        res.append(res_row)
    return res

def dict_table(conn, table):
    return dict_query(conn, 'SELECT * FROM %s' % table)

def query_trans(key, lst, multi=False):
    res = {}
    for dct in lst:
        r = {}
        for k in dct:
            # if k == key:
            #    continue
            r[k] = dct[k]
        if multi:
            if dct[key] not in res:
                res[dct[key]] = []
            res[dct[key]].append(r)
        else:
            res[dct[key]] = r
    return res

def query_chat_info(conn, meta_conn, site, hsh):
    c = conn.cursor()
    mc = meta_conn.cursor()
    params = (site, 'hash' if site == 'vk' else 'chat_id')
    res = mc.execute('''
    SELECT user_id, chat_name, date,
        first_msg_stamp, last_msg_stamp, msg_count
    FROM %s_chat WHERE %s=?
    '''% params, (hsh,)).fetchone()
    user_id, chat_name, date, first_msg_stamp, last_msg_stamp, msg_count = res
    res = {
        'site': site, 'title': chat_name, 'uploaded_by': user_id,
        'msg_count': msg_count, 'first_msg_stamp': first_msg_stamp, 'last_msg_stamp': last_msg_stamp
    }
    if site == 'tg':
        res['update_date'] = date
        res['chat_type'], = mc.execute('SELECT \
            type FROM tg_chat WHERE chat_id=?', (hsh,)).fetchone()
    elif site == 'vk':
        res['uploaded_date'] = date
    return res

def query_users(conn, site):
    res = {}

    if site == 'vk':
        query = 'SELECT user_id, first_name, last_name, photo_50 FROM user'
        users = conn.cursor().execute(query).fetchall()
        for user_id, first_name, last_name, photo_50 in users:
            res[user_id] = {
                'id' : user_id,
                'full_name' : join_name(first_name, last_name),
                'profile_url': 'http://vk.com/id%s' % user_id,
                'avatar': photo_50
            }
    
    elif site == 'tg':
        query = 'SELECT user_id, first_name, last_name FROM user'
        users = conn.cursor().execute(query).fetchall()
        for user_id, first_name, last_name in users:
            res[user_id] = {
                'id' : user_id,
                'full_name' : join_name(first_name, last_name)
            }
    
    query = 'SELECT user_id, msg_count, total_chars, \
             total_words, total_special_chars FROM user_stats'
    users = conn.cursor().execute(query).fetchall()
    for user_id, msg_cnt, total_chars, total_words, total_special_chars in users:
        res[user_id].update({
            'msg_count': msg_cnt, 'word_count': total_words,
            'punct_count': total_special_chars, 'total_length': total_chars
        })
    
    query = 'SELECT user_id, pos, cnt FROM user_pos'
    stats = conn.cursor().execute(query).fetchall()
    for user_id, pos, cnt in stats:
        if pos == 'ADJF' or pos == 'ADJS':
            res[user_id]['adj_count'] = res[user_id].get('adj_count', 0) + cnt
        elif pos == 'NOUN':
            res[user_id]['noun_count'] = cnt
    return res

def query_users_word(conn, word_id):
    query = 'SELECT user_id, msg_count FROM user_word WHERE word_id = ?'
    return query_trans('user_id', dict_query(conn, query, word_id))

def query_communications(conn):
    return {'relations': dict_table(conn, 'communication')}

def query_invitations(conn):
    return {'relations': dict_table(conn, 'invitation')}

def query_temporal(conn, by):
    return query_trans('period',
        dict_query(conn,'SELECT * FROM temporal_%s' % by)
    )

def query_temporal_user(conn, by, user_id):
    return query_trans('period',
        dict_query(conn,
            'SELECT period, msg_count FROM temporal_%s_user WHERE user_id=?' % by,
        (user_id,))
    )

def query_temporal_word(conn, by, word_id):
    return query_trans('period',
        dict_query(conn,
            'SELECT period, msg_count FROM temporal_%s_word WHERE word_id=?' % by,
        (word_id,))
    )

def query_top_words(conn):
    return dict_table(conn, 'top_words')

def query_temporal_top_words(conn, by):
    return query_trans('period',
        dict_query(conn,
            'SELECT * FROM temporal_%s_top_word' % by
        ),
        multi=True
    )

def query_users_top_words(conn):
    return query_trans('user_id',
        dict_query(conn, 'SELECT * FROM user_top_word'),
        multi=True
    )

class Query(CORSHandler):
    def get(self, site, hsh, qtype):
        self.set_header('Content-Type', 'text/json; charset="utf-8"')
        if not os.path.exists(db_path(site, hsh)):
            self.write('{error: "chat info does not exist or has been deleted"}')
            return
        with sqlite3.connect(db_path(site, hsh)) as conn:
            with connect_meta() as meta_conn:
                if not cache_exists(conn):
                    generate_cache(conn, meta_conn, site, hsh)
                res = {'error': "unknown query type"}
                if qtype == 'chat_info':
                    res = query_chat_info(conn, meta_conn, site, hsh)
                elif qtype == 'users':
                    res = query_users(conn, site)
                elif qtype == 'users_word':
                    res = query_users_word(conn, self.get_argument('word_id'))
                elif qtype == 'communications':
                    res = query_communications(conn)
                elif qtype == 'invitations':
                    res = query_invitations(conn)
                elif qtype == 'temporal':
                    res = query_temporal(conn, self.get_argument('by'))
                elif qtype == 'temporal_user':
                    res = query_temporal_user(conn, self.get_argument('by'), self.get_argument('user_id'))
                elif qtype == 'temporal_word':
                    res = query_temporal_word(conn, self.get_argument('by'), self.get_argument('word_id'))
                elif qtype == 'top_words':
                    res = query_top_words(conn)
                elif qtype == 'temporal_top_words':
                    res = query_temporal_top_words(conn, self.get_argument('by'))
                elif qtype == 'users_top_words':
                    res = query_users_top_words(conn)
        self.write(json.dumps(res, indent=4, ensure_ascii=False))


#--------------------------
# Выдача статических страниц

class ServeIndex(CORSHandler):
    def get(self):
        self.write(open(static_dir + '/index.html').read())

class ServeUpload(CORSHandler):
    def get(self):
        self.write(open(static_dir + '/upload.html').read())

class ServeView(CORSHandler):
    def get(self, site, chat_id):
        self.write(open(static_dir + '/view.html').read())

class ServeStatic(tornado.web.StaticFileHandler):
    def parse_url_path(self, url_path):
        res = super().parse_url_path(url_path)
        print(res)
        return res

js_libs = {
    'jquery@2.1.1/jquery.min.js': 'https://cdnjs.cloudflare.com/ajax/libs/jquery/2.1.1/jquery.min.js',
    'jquery@2.1.1/jquery.min.map': 'https://cdnjs.cloudflare.com/ajax/libs/jquery/2.1.1/jquery.min.map',
    'ramda@0.22.1/ramda.min.js': 'https://cdnjs.cloudflare.com/ajax/libs/ramda/0.22.1/ramda.min.js',
    'react@15.3.1/build/react-dom.min.js': 'https://cdnjs.cloudflare.com/ajax/libs/react/15.3.1/react-dom.min.js',
    'react@15.3.1/build/react.min.js': 'https://cdnjs.cloudflare.com/ajax/libs/react/15.3.1/react.min.js',
    'requirejs@2.3.1/require.min.js': 'https://cdnjs.cloudflare.com/ajax/libs/require.js/2.3.1/require.min.js',
    'requirejs@2.3.1/require.min.js.map': 'https://cdnjs.cloudflare.com/ajax/libs/require.js/2.3.1/require.min.js.map',
    'visjs@4.16.1/dist/vis.min.css': 'https://cdnjs.cloudflare.com/ajax/libs/vis/4.15.0/vis.min.css',
    'visjs@4.16.1/dist/vis.min.js': 'https://cdnjs.cloudflare.com/ajax/libs/vis/4.15.0/vis.min.js',
    'visjs@4.16.1/dist/vis.map': 'https://cdnjs.cloudflare.com/ajax/libs/vis/4.15.0/vis.map',
    'fontawesome@4.6.3.zip': 'http://fontawesome.io/assets/font-awesome-4.6.3.zip'
}

def install_js_libs():
    for path in js_libs:
        full_path = static_dir + '/' + path
        dir_path = os.path.dirname(full_path)
        url = js_libs[path]
        if not os.path.exists(full_path):
            print('Downloading %s' % path)
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)
            with open(full_path, 'wb') as f:
                f.write(requests.get(url).content)
        if path.endswith('.zip'):
            extract_path = dir_path + '/' + url.split('/')[-1][:-4]
            destination_path = full_path[:-4]
            if not os.path.exists(destination_path):
                print('Extracting %s' % path)
                import zipfile
                zip_ref = zipfile.ZipFile(full_path, 'r')
                zip_ref.extractall(dir_path)
                zip_ref.close()
                os.rename(extract_path, destination_path)


if 'get_ipython' in globals():
    port = 8080
    client_url = 'http://localhost:8080'
    server_url = 'http://localhost:%d' % port
    data_dir = '/data/sets/server/gchatstats/data'
    server_dir = '/data/sets/server/gchatstats'
    static_dir = '/data/sets/server/gchatstats/static'
else:
    port = 8000
    client_url = 'http://localhost:8888'
    server_url = 'http://host:%d' % port
    data_dir = 'data' # '/data/sets/server/gchatstats/data'
    server_dir = '.' # '/data/sets/server/gchatstats'
    static_dir = 'static' #'/data/sets/server/gchatstats/static'

main_bot_token = '280926150:AAH8z72HwMDrmRXdUHQiCeWqobDzThnD1HU'
tg_report_token = '253264911:AAEAJFEq0gQ6SdUKjlBBAXbNAzGSskSrcBg'
tg_report_chat_id = '153015804'

if not os.path.exists(data_dir):
    os.mkdir(data_dir)

import mimetypes
mimetypes.add_type("application/x-font-woff", ".woff")
mimetypes.add_type("application/octet-stream", ".ttf")

handlers = [
    (r"/?error", ErrorLog),
    (r"/?", ServeIndex),
    (r"/?upload", ServeUpload),
    (r"/?(vk|tg)([\-0-9]+)", ServeView),
    (r"/?static/(.*)", ServeStatic, {'path': static_dir}),
    (r"/?upload_vk_users", UploadVkUsers),
    (r"/?upload_vk_messages", UploadVkMessages),
    (r"/?upload_vk_finalize", UploadVkFinalize),
    (r"/?(vk|tg)([\-0-9]+)/(.*)", Query),
    (r"/?.*", NotFound)
]

morph = pymorphy2.MorphAnalyzer()
stopwords = open(server_dir + '/stop-words-russian.txt').read().split()
install_js_libs()

if 'app' not in globals():
    app = tornado.web.Application(handlers)
    print('Visit %s' % server_url)
    server = app.listen(port)
    last_report_date = None
    start_minute_loop()
    if 'get_ipython' not in globals():
        tornado.ioloop.IOLoop.current().start()
else:
    print("skipping")
    app.handlers = []
    app.add_handlers('.*$', handlers)

