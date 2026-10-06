
import json, os, sqlite3, hashlib, secrets, urllib.parse, urllib.request
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).parent
DB = ROOT / "worldmate.db"
PORT = 8000

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def hash_pw(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 160000)
    return salt.hex() + ":" + h.hex()

def verify_pw(password, stored):
    try:
        s, h = stored.split(":")
        salt = bytes.fromhex(s)
        x = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 160000).hex()
        return secrets.compare_digest(x, h)
    except Exception:
        return False

def init_db():
    c = db()
    c.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS countries(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        code TEXT,
        language TEXT,
        currency TEXT,
        emergency TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS announcements(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        body TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    admin = c.execute("SELECT id FROM users WHERE username='admin'").fetchone()
    if not admin:
        c.execute("INSERT INTO users(username,email,password_hash,role) VALUES(?,?,?,?)",
                  ("admin","admin@worldmate.local",hash_pw("WorldMate@2026!"),"admin"))
    if c.execute("SELECT COUNT(*) n FROM countries").fetchone()["n"] == 0:
        rows = [
            ("Uzbekistan","UZ","Uzbek","UZS","112"),
            ("China","CN","Chinese","CNY","110 / 120"),
            ("South Korea","KR","Korean","KRW","112 / 119"),
            ("Japan","JP","Japanese","JPY","110 / 119"),
            ("United States","US","English","USD","911"),
            ("United Kingdom","GB","English","GBP","999 / 112"),
            ("Germany","DE","German","EUR","112"),
            ("France","FR","French","EUR","112 / 15 / 17"),
            ("Türkiye","TR","Turkish","TRY","112"),
            ("United Arab Emirates","AE","Arabic","AED","999 / 998 / 997"),
        ]
        c.executemany("INSERT INTO countries(name,code,language,currency,emergency) VALUES(?,?,?,?,?)", rows)
    if c.execute("SELECT COUNT(*) n FROM announcements").fetchone()["n"] == 0:
        c.execute("INSERT INTO announcements(title,body) VALUES(?,?)",
                  ("WorldMate Pro demo","Real map, live weather, routing, currency and travel tools are enabled."))
    c.commit()
    c.close()

class Handler(SimpleHTTPRequestHandler):
    def _json(self, code, obj):
        raw = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(raw)))
        self.send_header("Access-Control-Allow-Origin","*")
        self.end_headers()
        self.wfile.write(raw)

    def _body(self):
        n = int(self.headers.get("Content-Length","0"))
        return json.loads(self.rfile.read(n) or b"{}")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Access-Control-Allow-Headers","Content-Type")
        self.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")
        self.end_headers()

    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        if p.path == "/api/health":
            return self._json(200, {"ok":True,"service":"WorldMate Pro","version":"3.0"})
        if p.path == "/api/countries":
            c=db(); rows=[dict(x) for x in c.execute("SELECT * FROM countries ORDER BY name").fetchall()]; c.close()
            return self._json(200, rows)
        if p.path == "/api/announcements":
            c=db(); rows=[dict(x) for x in c.execute("SELECT * FROM announcements ORDER BY id DESC").fetchall()]; c.close()
            return self._json(200, rows)
        if p.path == "/api/admin/users":
            c=db(); rows=[dict(x) for x in c.execute("SELECT id,username,email,role,created_at FROM users ORDER BY id DESC").fetchall()]; c.close()
            return self._json(200, rows)
        return super().do_GET()

    def do_POST(self):
        p = urllib.parse.urlparse(self.path)
        data = self._body()
        if p.path == "/api/register":
            username=str(data.get("username","")).strip()
            email=str(data.get("email","")).strip()
            password=str(data.get("password",""))
            if len(username)<3 or len(password)<6 or "@" not in email:
                return self._json(400,{"ok":False,"message":"Username, email yoki parol noto'g'ri."})
            c=db()
            try:
                c.execute("INSERT INTO users(username,email,password_hash) VALUES(?,?,?)",
                          (username,email,hash_pw(password)))
                c.commit()
                return self._json(200,{"ok":True,"message":"Account yaratildi."})
            except sqlite3.IntegrityError:
                return self._json(409,{"ok":False,"message":"Username yoki email allaqachon mavjud."})
            finally:
                c.close()
        if p.path == "/api/login":
            username=str(data.get("username","")).strip()
            password=str(data.get("password",""))
            c=db(); u=c.execute("SELECT * FROM users WHERE username=?",(username,)).fetchone(); c.close()
            if not u or not verify_pw(password,u["password_hash"]):
                return self._json(401,{"ok":False,"message":"Login yoki parol noto'g'ri."})
            token=secrets.token_urlsafe(32)
            return self._json(200,{"ok":True,"token":token,"user":{"id":u["id"],"username":u["username"],"email":u["email"],"role":u["role"]}})
        if p.path == "/api/admin/country":
            if data.get("admin_key") != "WorldMate@2026!":
                return self._json(403,{"ok":False,"message":"Admin ruxsati kerak."})
            c=db()
            c.execute("INSERT INTO countries(name,code,language,currency,emergency) VALUES(?,?,?,?,?)",
                      (data.get("name",""),data.get("code",""),data.get("language",""),data.get("currency",""),data.get("emergency","")))
            c.commit(); c.close()
            return self._json(200,{"ok":True})
        if p.path == "/api/admin/announcement":
            if data.get("admin_key") != "WorldMate@2026!":
                return self._json(403,{"ok":False,"message":"Admin ruxsati kerak."})
            c=db(); c.execute("INSERT INTO announcements(title,body) VALUES(?,?)",(data.get("title",""),data.get("body",""))); c.commit(); c.close()
            return self._json(200,{"ok":True})
        if p.path == "/api/assistant":
            q=str(data.get("message","")).lower()
            answers=[]
            if any(x in q for x in ["pharmacy","dorixona","аптека"]): answers.append("Yaqin dorixonani xaritada qidirish uchun Places → Pharmacy tugmasini ishlating.")
            if any(x in q for x in ["hotel","mehmonxona","отель"]): answers.append("Hotels bo‘limida joylashuv bo‘yicha mehmonxonalarni topishingiz mumkin.")
            if any(x in q for x in ["weather","ob-havo","погода"]): answers.append("Weather bo‘limi koordinatangiz bo‘yicha yangilanadigan prognozni ko‘rsatadi.")
            if any(x in q for x in ["route","yo‘l","маршрут"]): answers.append("Map bo‘limida boshlanish va manzilni kiriting — avtomobil, piyoda yoki velosiped marshrutini hisoblaydi.")
            if not answers: answers.append("Men WorldMate yordamchisiman. Xarita, marshrut, tarjima, ob-havo, valyuta, transport va joylarni topishda yordam beraman.")
            return self._json(200,{"ok":True,"answer":" ".join(answers)})
        return self._json(404,{"ok":False,"message":"API topilmadi."})

if __name__ == "__main__":
    init_db()
    os.chdir(ROOT)
    print("="*55)
    print(" WORLD MATE PRO — LOCAL SERVER")
    print("="*55)
    print("Ilova: http://localhost:8000")
    print("Admin: http://localhost:8000/admin.html")
    print("Admin login: admin / WorldMate@2026!")
    print("To'xtatish: Ctrl+C")
    ThreadingHTTPServer(("127.0.0.1",PORT),Handler).serve_forever()
