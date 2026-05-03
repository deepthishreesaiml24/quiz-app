from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
import sqlite3, hashlib, os, random, json
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import inch, cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.pdfgen import canvas
import io

app = Flask(__name__)
app.secret_key = "quizapp_super_secret_key_2024"
DB = "data/quiz.db"

# ─── DATABASE INIT ────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        email TEXT,
        role TEXT DEFAULT 'student',
        avatar TEXT DEFAULT '🎓',
        level INTEGER DEFAULT 1,
        xp INTEGER DEFAULT 0,
        total_score INTEGER DEFAULT 0,
        quizzes_taken INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        icon TEXT DEFAULT '📚',
        color TEXT DEFAULT '#667eea',
        description TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category_id INTEGER NOT NULL,
        question TEXT NOT NULL,
        option_a TEXT NOT NULL,
        option_b TEXT NOT NULL,
        option_c TEXT NOT NULL,
        option_d TEXT NOT NULL,
        correct_answer TEXT NOT NULL,
        difficulty TEXT DEFAULT 'medium',
        created_by INTEGER DEFAULT 1,
        FOREIGN KEY(category_id) REFERENCES categories(id)
    );
    CREATE TABLE IF NOT EXISTS quiz_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        category_id INTEGER NOT NULL,
        score INTEGER DEFAULT 0,
        total_questions INTEGER DEFAULT 10,
        correct INTEGER DEFAULT 0,
        wrong INTEGER DEFAULT 0,
        time_taken INTEGER DEFAULT 0,
        percentage REAL DEFAULT 0,
        completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(category_id) REFERENCES categories(id)
    );
    CREATE TABLE IF NOT EXISTS badges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        icon TEXT NOT NULL,
        description TEXT NOT NULL,
        condition_type TEXT NOT NULL,
        condition_value INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS user_badges (
        user_id INTEGER, badge_id INTEGER,
        earned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(user_id, badge_id)
    );
    CREATE TABLE IF NOT EXISTS leaderboard (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        category_id INTEGER,
        score INTEGER DEFAULT 0,
        percentage REAL DEFAULT 0,
        quiz_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    """)
    conn.commit()
    conn.close()

# ─── SEED DATA ────────────────────────────────────────────────────────────────
def seed_data():
    conn = get_db()
    c = conn.cursor()
    # Admin
    admin_pw = hashlib.sha256("admin123".encode()).hexdigest()
    c.execute("INSERT OR IGNORE INTO users (username,password,email,role,avatar) VALUES (?,?,?,?,?)",
              ("admin","admin123","admin@quiz.com","admin","👑"))
    c.execute("INSERT OR IGNORE INTO users (username,password,email,role,avatar) VALUES (?,?,?,?,?)",
              ("student1","student123","student1@quiz.com","student","🎓"))

    # Badges
    badges = [
        ("First Step","🌟","Complete your first quiz","quizzes",1),
        ("Quiz Enthusiast","🔥","Complete 5 quizzes","quizzes",5),
        ("Quiz Master","🏆","Complete 20 quizzes","quizzes",20),
        ("Perfect Score","💯","Get 100% in any quiz","perfect",100),
        ("High Achiever","🎯","Score above 80% five times","high_score",5),
        ("Speed Demon","⚡","Finish quiz under 2 minutes","speed",120),
        ("Scholar","📚","Complete quizzes in 5 categories","categories",5),
        ("Legend","👑","Reach level 10","level",10),
    ]
    for b in badges:
        c.execute("INSERT OR IGNORE INTO badges (name,icon,description,condition_type,condition_value) VALUES (?,?,?,?,?)", b)

    # Categories
    cats = [
        ("Mathematics","➕","#FF6B6B","Master numbers and equations"),
        ("Science","🔬","#4ECDC4","Explore the natural world"),
        ("English","📝","#45B7D1","Language and literature"),
        ("History","🏛️","#96CEB4","Journey through time"),
        ("Geography","🌍","#FFEAA7","Explore our planet"),
        ("Computer Science","💻","#DDA0DD","Technology and coding"),
        ("Physics","⚛️","#98D8C8","Laws of the universe"),
        ("Chemistry","🧪","#F7DC6F","Elements and reactions"),
        ("Biology","🧬","#82E0AA","Life and living things"),
        ("Literature","📖","#F1948A","Great works and authors"),
        ("General Knowledge","🌐","#AED6F1","Know everything!"),
        ("Sports","⚽","#A9DFBF","Athletics and games"),
        ("Music","🎵","#F9E79F","Rhythms and melodies"),
        ("Art","🎨","#FAD7A0","Creativity and expression"),
        ("Economics","💰","#D7BDE2","Money and markets"),
        ("Logical Reasoning","🧠","#A8D8EA","Think and solve"),
        ("Current Affairs","📰","#F8C471","World events"),
        ("Environment","🌿","#ABEBC6","Nature and ecology"),
        ("Health & Nutrition","🍎","#F1948A","Wellness and fitness"),
        ("Technology","📱","#85C1E9","Modern innovations"),
    ]
    for cat in cats:
        c.execute("INSERT OR IGNORE INTO categories (name,icon,color,description) VALUES (?,?,?,?)", cat)

    conn.commit()
    conn.close()
    seed_questions()

def seed_questions():
    conn = get_db()
    c = conn.cursor()
    count = c.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    if count >= 600:
        conn.close()
        return

    all_questions = get_all_questions()
    cats = {r["name"]: r["id"] for r in c.execute("SELECT id,name FROM categories").fetchall()}

    for cat_name, qs in all_questions.items():
        cid = cats.get(cat_name)
        if not cid:
            continue
        for q in qs:
            c.execute("""INSERT OR IGNORE INTO questions
                (category_id,question,option_a,option_b,option_c,option_d,correct_answer,difficulty)
                VALUES (?,?,?,?,?,?,?,?)""",
                (cid, q[0], q[1], q[2], q[3], q[4], q[5], q[6]))
    conn.commit()
    conn.close()

def get_all_questions():
    return {
"Mathematics": [
    ("What is 12 × 12?","144","124","132","148","A","easy"),
    ("What is √144?","12","14","11","13","A","easy"),
    ("Solve: 2x + 5 = 15. x = ?","5","10","7","3","A","medium"),
    ("What is 15% of 200?","30","25","35","20","A","easy"),
    ("Value of π (pi) approximately?","3.14159","3.14169","3.12159","3.14000","A","easy"),
    ("What is 7! (7 factorial)?","5040","720","5000","4320","A","medium"),
    ("LCM of 4 and 6?","12","24","6","8","A","medium"),
    ("HCF of 18 and 24?","6","3","12","9","A","medium"),
    ("What is 2^10?","1024","512","2048","1000","A","medium"),
    ("Triangle angles 60°, 60°, third angle?","60°","90°","45°","30°","A","easy"),
    ("Area of circle with radius 7? (π=22/7)","154","144","164","174","A","medium"),
    ("What is 3/4 + 1/4?","1","2","7/8","1/2","A","easy"),
    ("0.75 as a fraction?","3/4","1/2","2/3","7/8","A","easy"),
    ("Perimeter of square with side 5?","20","25","15","10","A","easy"),
    ("What is -3 × -4?","12","-12","7","-7","A","easy"),
    ("1000 ÷ 25?","40","50","35","45","A","easy"),
    ("Mean of 2, 4, 6, 8, 10?","6","5","7","8","A","easy"),
    ("What is 5² + 12²?","169","144","196","225","A","medium"),
    ("If x = 3, what is x³?","27","9","18","36","A","medium"),
    ("Slope formula?","(y2-y1)/(x2-x1)","(x2-x1)/(y2-y1)","y/x","x/y","A","medium"),
    ("45 + 55 × 2 = ?","155","200","145","160","A","medium"),
    ("1000 - 378 = ?","622","632","612","642","A","easy"),
    ("Sides of a hexagon?","6","5","7","8","A","easy"),
    ("Roman numeral for 50?","L","X","C","V","A","easy"),
    ("Next prime after 7?","11","9","13","10","A","easy"),
    ("144 ÷ 12 = ?","12","11","13","14","A","easy"),
    ("Volume of cube with side 3?","27","9","18","6","A","medium"),
    ("25% of 400?","100","80","120","75","A","easy"),
    ("Simplify 18/24?","3/4","2/3","5/6","1/2","A","medium"),
    ("Median of 3, 5, 7, 9, 11?","7","5","9","6","A","easy"),
],
"Science": [
    ("Chemical symbol for water?","H2O","CO2","O2","H2","A","easy"),
    ("Planet closest to Sun?","Mercury","Venus","Earth","Mars","A","easy"),
    ("Speed of light?","3×10^8 m/s","3×10^6 m/s","3×10^10 m/s","3×10^4 m/s","A","medium"),
    ("Powerhouse of the cell?","Mitochondria","Nucleus","Ribosome","Golgi body","A","easy"),
    ("Bones in adult human body?","206","208","204","210","A","medium"),
    ("Gas plants absorb in photosynthesis?","CO2","O2","N2","H2","A","easy"),
    ("Newton's first law is about?","Inertia","Gravity","Motion","Force","A","medium"),
    ("Atomic number of Carbon?","6","12","8","14","A","medium"),
    ("Boiling point of water?","100°C","90°C","110°C","95°C","A","easy"),
    ("Organ that pumps blood?","Heart","Liver","Kidney","Lungs","A","easy"),
    ("Chemical symbol for Gold?","Au","Ag","Fe","Cu","A","easy"),
    ("Planet with rings?","Saturn","Jupiter","Neptune","Uranus","A","easy"),
    ("Smallest unit of matter?","Atom","Molecule","Cell","Quark","A","medium"),
    ("Photosynthesis produces?","Glucose and O2","CO2 and water","N2 and O2","H2O and CO2","A","medium"),
    ("Chambers in human heart?","4","2","3","6","A","easy"),
    ("Nearest star to Earth?","Sun","Proxima Centauri","Sirius","Alpha Centauri","A","easy"),
    ("A whale is a?","Mammal","Fish","Reptile","Amphibian","A","easy"),
    ("DNA stands for?","Deoxyribonucleic Acid","Deoxyribose Acid","Deoxyribonuclear Acid","None","A","medium"),
    ("Force that pulls objects to Earth?","Gravity","Magnetism","Friction","Tension","A","easy"),
    ("Chemical symbol for Oxygen?","O","O2","Ox","Om","A","easy"),
    ("Blood cells that fight infection?","White blood cells","Red blood cells","Platelets","Plasma","A","easy"),
    ("Hardest natural substance?","Diamond","Iron","Granite","Quartz","A","easy"),
    ("Unit of electric current?","Ampere","Volt","Watt","Ohm","A","medium"),
    ("Formula for speed?","Distance/Time","Time/Distance","Mass×Velocity","Force/Area","A","easy"),
    ("Most of Earth's atmosphere is?","Nitrogen","Oxygen","CO2","Hydrogen","A","medium"),
    ("pH of pure water?","7","0","14","5","A","easy"),
    ("Water turning to vapor is?","Evaporation","Condensation","Precipitation","Sublimation","A","easy"),
    ("Center of an atom?","Nucleus","Electron","Proton","Neutron","A","easy"),
    ("Sunlight provides which vitamin?","Vitamin D","Vitamin C","Vitamin A","Vitamin B","A","easy"),
    ("Unit of force?","Newton","Joule","Pascal","Watt","A","medium"),
],
"English": [
    ("A noun is?","Name of person/place/thing","Action word","Describing word","Connecting word","A","easy"),
    ("Past tense of 'run'?","Ran","Runned","Running","Runs","A","easy"),
    ("Synonym for 'happy'?","Joyful","Sad","Angry","Tired","A","easy"),
    ("Antonym of 'big'?","Small","Large","Huge","Giant","A","easy"),
    ("Correct spelling?","Beautiful","Beautifull","Beutiful","Beautful","A","easy"),
    ("A verb is?","Action word","Naming word","Describing word","Joining word","A","easy"),
    ("Punctuation ending a question?","?",".","!",";","A","easy"),
    ("Plural of 'child'?","Children","Childs","Childrens","Child","A","easy"),
    ("Adjective in 'The red car'?","Red","The","Car","A","A","easy"),
    ("'Enormous' means?","Very large","Very small","Very fast","Very slow","A","easy"),
    ("Simile uses?","like or as","just comparison","exaggeration","repetition","A","medium"),
    ("Correct sentence?","She is going to school.","She going school.","She go to school.","She goed school.","A","easy"),
    ("An adverb modifies?","A verb","A noun","A pronoun","A subject","A","medium"),
    ("Opposite of 'ancient'?","Modern","Old","Aged","Historic","A","easy"),
    ("Vowels in English alphabet?","5","6","4","7","A","easy"),
    ("Passive voice sentence?","The cat was chased.","The dog chased.","He ate food.","She reads.","A","medium"),
    ("Metaphor is?","Direct comparison","Comparison with like","Sound words","Story with moral","A","medium"),
    ("Superlative of 'good'?","Best","Better","Goodest","Most good","A","easy"),
    ("A conjunction joins?","Clauses/words","Verbs","Nouns","Adjectives","A","medium"),
    ("Alliteration repeats?","Initial sounds","End sounds","Vowels","Rhymes","A","medium"),
    ("Pronoun in 'She went home'?","She","Went","Home","The","A","easy"),
    ("Correct article: '___ apple'?","An","A","The","No article","A","easy"),
    ("Onomatopoeia example?","Buzz","Run","Happy","Big","A","medium"),
    ("Compound word example?","Sunflower","Running","Beautiful","Quickly","A","medium"),
    ("A preposition shows?","Relationship between words","Action","Description","Naming","A","medium"),
    ("Sentence with correct grammar?","I am going.","I is going.","I are going.","I be going.","A","easy"),
    ("'Quickly' is an?","Adverb","Adjective","Noun","Verb","A","easy"),
    ("Antonym of 'brave'?","Cowardly","Bold","Strong","Fierce","A","easy"),
    ("Which is a proper noun?","India","country","city","mountain","A","easy"),
    ("'The boy who cried wolf' is a?","Fable","Novel","Poem","Drama","A","medium"),
],
"History": [
    ("Who discovered America?","Columbus","Vespucci","Magellan","Drake","A","medium"),
    ("Which year did WW2 end?","1945","1944","1946","1943","A","easy"),
    ("First President of USA?","George Washington","Lincoln","Jefferson","Adams","A","easy"),
    ("Egyptian pyramids were built by?","Pharaohs","Greeks","Romans","Persians","A","easy"),
    ("French Revolution began in?","1789","1776","1800","1765","A","medium"),
    ("Great Wall of China built to?","Keep out invaders","Mark boundary","Trade route","Irrigation","A","easy"),
    ("World War 1 started in?","1914","1918","1910","1916","A","easy"),
    ("Who was Napoleon Bonaparte?","French Emperor","British King","Russian Tsar","German Kaiser","A","easy"),
    ("Ancient Olympics started in?","Greece","Rome","Egypt","Persia","A","easy"),
    ("Magna Carta signed in?","1215","1415","1115","1315","A","medium"),
    ("Who invented the telephone?","Alexander Bell","Edison","Tesla","Marconi","A","easy"),
    ("Cleopatra was ruler of?","Egypt","Rome","Greece","Persia","A","easy"),
    ("Cold War was between?","USA and USSR","USA and China","UK and USSR","France and Germany","A","easy"),
    ("First man on Moon in?","1969","1959","1979","1949","A","easy"),
    ("Indian Independence year?","1947","1950","1945","1942","A","easy"),
    ("Hiroshima bomb dropped in?","1945","1944","1946","1943","A","medium"),
    ("Who was Abraham Lincoln?","US President","British PM","French King","General","A","easy"),
    ("Industrial Revolution started in?","Britain","France","Germany","USA","A","medium"),
    ("Shakespeare lived in which era?","Elizabethan","Victorian","Modern","Medieval","A","medium"),
    ("The Renaissance started in?","Italy","France","Spain","England","A","medium"),
    ("Who was Julius Caesar?","Roman ruler","Greek hero","Egyptian pharaoh","Persian king","A","easy"),
    ("Battle of Waterloo year?","1815","1715","1915","1615","A","medium"),
    ("Gutenberg invented?","Printing press","Steam engine","Telegraph","Compass","A","easy"),
    ("Ottoman Empire capital?","Constantinople","Cairo","Baghdad","Damascus","A","medium"),
    ("Titanic sank in?","1912","1910","1914","1908","A","easy"),
    ("Who was Mahatma Gandhi?","Indian leader","Pakistani leader","British leader","Nepali leader","A","easy"),
    ("The Berlin Wall fell in?","1989","1991","1985","1993","A","medium"),
    ("Mongol Empire founded by?","Genghis Khan","Kublai Khan","Timur","Attila","A","easy"),
    ("Black Death was a?","Plague","War","Famine","Earthquake","A","easy"),
    ("Treaty of Versailles ended?","WW1","WW2","Cold War","Napoleonic Wars","A","medium"),
],
"Geography": [
    ("Largest continent?","Asia","Africa","North America","Europe","A","easy"),
    ("Longest river in the world?","Nile","Amazon","Yangtze","Mississippi","A","easy"),
    ("Capital of Australia?","Canberra","Sydney","Melbourne","Brisbane","A","medium"),
    ("Country with most population?","China","India","USA","Indonesia","A","easy"),
    ("Highest mountain in world?","Everest","K2","Kangchenjunga","Lhotse","A","easy"),
    ("Amazon rainforest is in?","South America","Africa","Asia","Australia","A","easy"),
    ("Capital of Japan?","Tokyo","Osaka","Kyoto","Hiroshima","A","easy"),
    ("Sahara Desert is in?","Africa","Asia","Middle East","Australia","A","easy"),
    ("Pacific Ocean is the?","Largest ocean","Second largest","Third largest","Smallest","A","easy"),
    ("Country shaped like a boot?","Italy","Greece","Portugal","Spain","A","easy"),
    ("Largest country by area?","Russia","Canada","USA","China","A","easy"),
    ("Great Barrier Reef is in?","Australia","Indonesia","Philippines","USA","A","easy"),
    ("River through Egypt?","Nile","Congo","Niger","Zambezi","A","easy"),
    ("Capital of Brazil?","Brasilia","Rio de Janeiro","São Paulo","Salvador","A","medium"),
    ("Continent with most countries?","Africa","Asia","Europe","Americas","A","medium"),
    ("Smallest country in world?","Vatican City","Monaco","Liechtenstein","San Marino","A","medium"),
    ("Dead Sea is located in?","Middle East","Africa","Asia","Europe","A","medium"),
    ("Eiffel Tower is in?","France","Germany","Italy","Spain","A","easy"),
    ("Which country has most lakes?","Canada","Russia","USA","Finland","A","medium"),
    ("Indian subcontinent includes?","India Pakistan Bangladesh","India Nepal Sri Lanka","India China Nepal","All of above","A","medium"),
    ("Antarctica is a?","Continent","Country","Island","Ocean","A","easy"),
    ("Great Wall of China borders?","Mongolia","Russia","India","Korea","A","medium"),
    ("Capital of Canada?","Ottawa","Toronto","Vancouver","Montreal","A","medium"),
    ("Deepest lake in world?","Baikal","Superior","Tanganyika","Titicaca","A","hard"),
    ("Suez Canal connects?","Red Sea and Med","Atlantic and Pacific","Indian and Pacific","Arctic and Atlantic","A","medium"),
    ("Mount Fuji is in?","Japan","China","Korea","Nepal","A","easy"),
    ("Capital of South Africa?","Pretoria","Cape Town","Johannesburg","Durban","A","hard"),
    ("River Thames flows through?","London","Paris","Rome","Madrid","A","easy"),
    ("Which country has Taj Mahal?","India","Pakistan","Bangladesh","Nepal","A","easy"),
    ("Mediterranean Sea borders?","Europe Africa Asia","Only Europe","Only Africa","Europe and Africa","A","medium"),
],
"Computer Science": [
    ("CPU stands for?","Central Processing Unit","Computer Processing Unit","Central Program Unit","Core Processing Unit","A","easy"),
    ("What is RAM?","Random Access Memory","Read Access Memory","Random Address Memory","Read Address Memory","A","easy"),
    ("HTML stands for?","HyperText Markup Language","High Text Markup Language","HyperText Making Language","High Transfer Markup Language","A","easy"),
    ("What is the binary of 10?","1010","1100","1001","1011","A","medium"),
    ("Which is not a programming language?","HTML","Python","Java","C++","A","easy"),
    ("What does CPU do?","Processes instructions","Stores data","Displays output","Manages network","A","easy"),
    ("What is a byte?","8 bits","4 bits","16 bits","1 bit","A","easy"),
    ("HTTP stands for?","HyperText Transfer Protocol","High Text Transfer Protocol","HyperText Transmission Protocol","High Transfer Text Protocol","A","medium"),
    ("What is an algorithm?","Step-by-step instructions","A programming language","Computer hardware","Software program","A","easy"),
    ("What is the internet?","Global computer network","Software program","Hardware device","Programming language","A","easy"),
    ("Python is what type of language?","High-level","Low-level","Machine-level","Assembly","A","medium"),
    ("What is a database?","Organized data collection","Programming language","Hardware device","Network protocol","A","easy"),
    ("What does SQL stand for?","Structured Query Language","Simple Query Language","Structured Question Language","System Query Language","A","medium"),
    ("Operating System examples?","Windows Mac Linux","Python Java C++","Chrome Firefox Edge","Gmail YouTube Facebook","A","easy"),
    ("What is malware?","Malicious software","Faulty hardware","Bad network","Slow computer","A","easy"),
    ("What is Wi-Fi?","Wireless network technology","Wired network technology","Internet provider","Hardware device","A","easy"),
    ("What is a compiler?","Translates source code","Runs programs","Stores data","Manages files","A","medium"),
    ("RAM vs ROM: ROM is?","Read-only memory","Random-only memory","Read-open memory","Runtime-only memory","A","medium"),
    ("What is open source?","Free to use/modify","Paid software","Secret software","Encrypted software","A","medium"),
    ("What is an IP address?","Network identifier","Computer password","File name","Email address","A","medium"),
    ("What is encryption?","Converting data to code","Deleting data","Compressing data","Copying data","A","medium"),
    ("WWW stands for?","World Wide Web","World Wide Work","Wide World Web","Work Wide Web","A","easy"),
    ("What is a virus?","Self-replicating malware","Helpful program","System file","Network tool","A","easy"),
    ("What is cloud computing?","Remote server computing","Local computing","Offline computing","Manual computing","A","medium"),
    ("What is a pixel?","Smallest screen element","Largest screen element","Color name","Font size","A","medium"),
    ("What is Boolean?","True/False data type","Number type","Text type","Image type","A","medium"),
    ("What is debugging?","Finding/fixing errors","Writing code","Running programs","Saving files","A","easy"),
    ("What is a firewall?","Network security system","File storage","Display device","Input device","A","medium"),
    ("What is resolution in screens?","Number of pixels","Screen brightness","Screen size","Screen weight","A","medium"),
    ("GitHub is used for?","Code version control","Email service","Social media","Video streaming","A","medium"),
],
"Physics": [
    ("Unit of energy?","Joule","Newton","Pascal","Watt","A","easy"),
    ("What is velocity?","Speed with direction","Speed without direction","Distance/time","Mass/time","A","medium"),
    ("Ohm's law: V = ?","I × R","I + R","I - R","I / R","A","medium"),
    ("What is frequency measured in?","Hertz","Decibel","Meter","Second","A","easy"),
    ("Light travels in?","Straight lines","Curved lines","Zigzag","Circular","A","easy"),
    ("What is kinetic energy?","Energy of motion","Stored energy","Sound energy","Heat energy","A","easy"),
    ("Boyle's law relates?","Pressure and volume","Temperature and volume","Mass and volume","Density and pressure","A","medium"),
    ("What is a neutron?","Neutral atomic particle","Positive particle","Negative particle","Charged particle","A","medium"),
    ("Decibel measures?","Sound intensity","Light intensity","Heat","Pressure","A","medium"),
    ("What is refraction?","Light bending in medium","Light reflecting","Light absorbing","Light scattering","A","medium"),
    ("Force = mass × ?","Acceleration","Velocity","Speed","Distance","A","easy"),
    ("What is absolute zero?","-273.15°C","0°C","-100°C","273.15°C","A","hard"),
    ("Electromagnetic waves need?","No medium","Air","Water","Solid","A","medium"),
    ("What is a lever?","Simple machine","Complex machine","Engine","Motor","A","easy"),
    ("Unit of electrical resistance?","Ohm","Volt","Ampere","Watt","A","easy"),
    ("What is buoyancy?","Upward fluid force","Downward force","Sideways force","No force","A","medium"),
    ("Infrared radiation is?","Heat radiation","Light radiation","Sound radiation","Radio waves","A","medium"),
    ("What is a black hole?","Object with extreme gravity","Empty space","Dark star","Cold planet","A","medium"),
    ("Speed of sound in air?","343 m/s","300 m/s","400 m/s","3×10^8 m/s","A","medium"),
    ("What is work in physics?","Force × distance","Mass × velocity","Energy × time","Power × time","A","medium"),
    ("Coulomb measures?","Electric charge","Magnetic field","Current","Resistance","A","hard"),
    ("What is torque?","Rotational force","Linear force","Normal force","Tension force","A","hard"),
    ("Nuclear fission splits?","Atomic nuclei","Electrons","Molecules","Cells","A","medium"),
    ("What is terminal velocity?","Constant fall speed","Maximum speed","Minimum speed","Initial speed","A","hard"),
    ("Photon is a particle of?","Light","Sound","Heat","Electricity","A","medium"),
    ("What is specific heat capacity?","Heat per unit mass per degree","Total heat energy","Heat per volume","None","A","hard"),
    ("Doppler effect involves?","Change in wave frequency","Wave amplitude","Wave speed","Wave length only","A","hard"),
    ("What is a wave?","Energy transfer","Matter transfer","Particle movement","Solid vibration","A","medium"),
    ("Magnetic poles: like poles?","Repel","Attract","No effect","Cancel","A","easy"),
    ("What is potential energy?","Stored energy","Moving energy","Light energy","Sound energy","A","easy"),
],
"Chemistry": [
    ("Periodic table element H is?","Hydrogen","Helium","Hafnium","Holmium","A","easy"),
    ("What is a covalent bond?","Shared electron bond","Transferred electron bond","Ionic bond","Metallic bond","A","medium"),
    ("Atomic number equals?","Protons in nucleus","Neutrons","Electrons + neutrons","Mass number","A","medium"),
    ("What is pH scale range?","0 to 14","0 to 7","7 to 14","1 to 10","A","easy"),
    ("Acid has pH?","Less than 7","Greater than 7","Equal to 7","Greater than 10","A","easy"),
    ("Noble gases are in which group?","Group 18","Group 1","Group 17","Group 2","A","medium"),
    ("What is an isotope?","Same element, different neutrons","Different element, same mass","Same element, same mass","Different element","A","hard"),
    ("Rusting is?","Oxidation","Reduction","Neutralization","Decomposition","A","medium"),
    ("Chemical formula of salt?","NaCl","KCl","CaCl2","MgCl2","A","easy"),
    ("Catalyst does what?","Speeds up reaction","Slows reaction","Produces energy","Creates products","A","medium"),
    ("What is a mole in chemistry?","6.022×10²³ particles","100 grams","1 liter","Atomic mass","A","hard"),
    ("Water is H2O which means?","2 hydrogen 1 oxygen","1 hydrogen 2 oxygen","2 hydrogen 2 oxygen","1 hydrogen 1 oxygen","A","easy"),
    ("Atomic mass unit is?","1/12 mass of carbon-12","Mass of proton","Mass of neutron","Mass of electron","A","hard"),
    ("What is combustion?","Burning with oxygen","Freezing","Melting","Evaporating","A","easy"),
    ("Alkali metals are in?","Group 1","Group 2","Group 17","Group 18","A","medium"),
    ("What is distillation?","Separating by boiling points","Filtering","Crystallizing","Chromatography","A","medium"),
    ("Organic chemistry studies?","Carbon compounds","Nitrogen compounds","All elements","Metals only","A","medium"),
    ("What is an alloy?","Metal mixture","Pure metal","Non-metal","Compound","A","easy"),
    ("Bronze is?","Copper and tin","Copper and zinc","Iron and carbon","Aluminum and copper","A","medium"),
    ("Electrons orbit in?","Shells/orbitals","Nucleus","Proton cloud","Neutron field","A","medium"),
    ("What is sublimation?","Solid to gas directly","Liquid to gas","Gas to liquid","Solid to liquid","A","medium"),
    ("Valence electrons are?","Outermost shell electrons","Inner electrons","Nucleus particles","Neutrons","A","medium"),
    ("What is an electrolyte?","Conducts electricity in solution","Non-conductor","Solid conductor","Gas conductor","A","medium"),
    ("Exothermic reaction?","Releases heat","Absorbs heat","No heat change","Changes color only","A","medium"),
    ("What is a polymer?","Long chain molecules","Short molecules","Single atoms","Metal compound","A","medium"),
    ("Nitrogen percentage in air?","78%","21%","50%","10%","A","medium"),
    ("What is a reducing agent?","Donates electrons","Accepts electrons","Produces acid","Creates base","A","hard"),
    ("Petroleum is mainly?","Hydrocarbons","Carbohydrates","Proteins","Nucleic acids","A","medium"),
    ("What is galvanization?","Zinc coating on iron","Painting metal","Heating metal","Polishing metal","A","medium"),
    ("Hard water contains?","Ca and Mg salts","Na and K salts","Fe and Cu salts","Al and Zn salts","A","medium"),
],
"Biology": [
    ("Photosynthesis occurs in?","Chloroplast","Mitochondria","Ribosome","Nucleus","A","easy"),
    ("DNA is found in?","Nucleus","Cytoplasm","Cell membrane","Ribosome","A","easy"),
    ("Osmosis is movement of?","Water through membrane","Solute through membrane","Gas through membrane","All particles","A","medium"),
    ("Number of chromosomes in human cell?","46","23","48","44","A","medium"),
    ("What is a pathogen?","Disease-causing organism","Helpful bacteria","Plant organism","Cell organelle","A","medium"),
    ("Blood type ABO discovered by?","Landsteiner","Pasteur","Fleming","Jenner","A","hard"),
    ("What do ribosomes make?","Proteins","Lipids","Carbohydrates","DNA","A","medium"),
    ("What is mitosis?","Cell division for growth","Sexual reproduction","Asexual budding","Meiosis","A","medium"),
    ("Largest organ in human body?","Skin","Liver","Brain","Lungs","A","easy"),
    ("What is natural selection?","Survival of fittest","Random mutation","Genetic drift","Bottleneck effect","A","medium"),
    ("Function of red blood cells?","Carry oxygen","Fight infection","Clot blood","Store energy","A","easy"),
    ("What is respiration?","Releasing energy from glucose","Breathing air in","Photosynthesis","Digestion","A","medium"),
    ("What is an enzyme?","Biological catalyst","Food molecule","Energy source","Structural protein","A","medium"),
    ("Cell membrane is made of?","Phospholipid bilayer","Protein only","Cellulose","Chitin","A","hard"),
    ("Insulin is produced by?","Pancreas","Liver","Kidney","Thyroid","A","medium"),
    ("What is a gene?","Segment of DNA","Protein chain","Cell type","Chromosome arm","A","medium"),
    ("Penicillin was discovered by?","Alexander Fleming","Louis Pasteur","Robert Koch","Edward Jenner","A","easy"),
    ("What is homeostasis?","Maintaining stable conditions","Cell division","Energy production","Digestion","A","medium"),
    ("Kingdom Fungi includes?","Mushrooms and molds","Bacteria","Plants","Animals","A","easy"),
    ("What is transpiration?","Water loss from leaves","Water absorption","Photosynthesis","Respiration","A","medium"),
    ("Nucleus controls?","Cell activities","Energy production","Protein synthesis","Water balance","A","medium"),
    ("What is binary fission?","Bacterial reproduction","Sexual reproduction","Spore formation","Budding","A","medium"),
    ("Vitamins A, D, E, K are?","Fat soluble","Water soluble","Both","Neither","A","medium"),
    ("What is a food chain?","Energy transfer in ecosystem","Food storage","Digestion process","Metabolism","A","easy"),
    ("Human blood pH is?","7.4","7.0","6.8","8.0","A","hard"),
    ("Myelin sheath covers?","Nerve fibers","Muscle fibers","Bone tissue","Blood vessels","A","hard"),
    ("What is a vaccine?","Weakened pathogen preparation","Antibiotic","Vitamin supplement","Painkiller","A","easy"),
    ("Cell wall in plants is made of?","Cellulose","Chitin","Starch","Protein","A","medium"),
    ("What is evolution?","Change in species over time","Individual growth","Seasonal change","Migration","A","easy"),
    ("ATP stands for?","Adenosine Triphosphate","Adenine Triphosphate","Adenosine Triprotein","None","A","hard"),
],
"Literature": [
    ("Who wrote Romeo and Juliet?","Shakespeare","Dickens","Austen","Tolstoy","A","easy"),
    ("Harry Potter was written by?","J.K. Rowling","Tolkien","C.S. Lewis","Roald Dahl","A","easy"),
    ("1984 was written by?","George Orwell","Aldous Huxley","Ray Bradbury","Philip K Dick","A","easy"),
    ("What is a haiku?","17-syllable Japanese poem","Sonnet","Limerick","Free verse","A","medium"),
    ("To Kill a Mockingbird author?","Harper Lee","Steinbeck","Hemingway","Faulkner","A","easy"),
    ("Pride and Prejudice author?","Jane Austen","Bronte","Eliot","Gaskell","A","easy"),
    ("The Odyssey was written by?","Homer","Virgil","Sophocles","Euripides","A","easy"),
    ("Don Quixote was written by?","Cervantes","Shakespeare","Dante","Chaucer","A","medium"),
    ("Protagonist is?","Main character","Villain","Supporting character","Narrator","A","easy"),
    ("What is a soliloquy?","Speaking alone on stage","Dialogue","Narration","Stage direction","A","medium"),
    ("Hamlet is a?","Tragedy","Comedy","Romance","History","A","easy"),
    ("War and Peace author?","Leo Tolstoy","Dostoevsky","Chekhov","Turgenev","A","easy"),
    ("What is foreshadowing?","Hinting at future events","Flashback","Climax","Resolution","A","medium"),
    ("The Great Gatsby author?","F. Scott Fitzgerald","Hemingway","Faulkner","Steinbeck","A","easy"),
    ("What is an epic poem?","Long narrative heroic poem","Short lyric","Sonnet","Haiku","A","medium"),
    ("Moby Dick is about?","Whale hunting","Mountain climbing","War","Love story","A","easy"),
    ("Canterbury Tales by?","Chaucer","Shakespeare","Milton","Dryden","A","medium"),
    ("Lord of the Rings author?","J.R.R. Tolkien","C.S. Lewis","Roald Dahl","Philip Pullman","A","easy"),
    ("Dystopia means?","Imagined terrible society","Perfect society","Future society","Past society","A","medium"),
    ("What is irony?","Opposite of what expected","Direct meaning","Literal statement","Exaggeration","A","medium"),
    ("Macbeth is set in?","Scotland","England","Denmark","France","A","medium"),
    ("Great Expectations by?","Charles Dickens","Thomas Hardy","George Eliot","Wilkie Collins","A","easy"),
    ("What is a ballad?","Narrative folk song/poem","Epic poem","Sonnet","Haiku","A","medium"),
    ("Narrator in first person uses?","I and we","He and she","They and them","You","A","easy"),
    ("What is a thesis statement?","Main argument of essay","Introduction","Conclusion","Summary","A","medium"),
    ("Frankenstein author?","Mary Shelley","Bram Stoker","Edgar Allan Poe","H.G. Wells","A","easy"),
    ("What is stream of consciousness?","Character's continuous thoughts","Plot summary","Dialogue","Description","A","hard"),
    ("Animal Farm by?","George Orwell","Aldous Huxley","C.S. Lewis","John Steinbeck","A","easy"),
    ("What is blank verse?","Unrhymed iambic pentameter","Free verse","Sonnet","Couplet","A","hard"),
    ("The Iliad is about?","Trojan War","Greek gods","Roman history","Persian wars","A","easy"),
],
"General Knowledge": [
    ("Who invented the telephone?","Alexander Graham Bell","Edison","Tesla","Marconi","A","easy"),
    ("How many colors in rainbow?","7","6","8","5","A","easy"),
    ("Currency of Japan?","Yen","Won","Yuan","Rupee","A","easy"),
    ("Who painted Mona Lisa?","Leonardo da Vinci","Michelangelo","Raphael","Picasso","A","easy"),
    ("Fastest land animal?","Cheetah","Lion","Horse","Leopard","A","easy"),
    ("Number of days in a leap year?","366","365","364","367","A","easy"),
    ("Largest organ in human body?","Skin","Liver","Brain","Intestine","A","easy"),
    ("Which country gifted Statue of Liberty?","France","Britain","Germany","Italy","A","easy"),
    ("What language do most people speak?","Mandarin Chinese","English","Spanish","Hindi","A","medium"),
    ("How many continents on Earth?","7","6","5","8","A","easy"),
    ("Olympics held every how many years?","4","2","6","8","A","easy"),
    ("Largest desert in world?","Sahara","Arabian","Gobi","Antarctic","A","medium"),
    ("Who invented the airplane?","Wright Brothers","Edison","Bell","Ford","A","easy"),
    ("Currency of India?","Rupee","Dollar","Pound","Dinar","A","easy"),
    ("How many sides does a triangle have?","3","4","5","6","A","easy"),
    ("What is the capital of USA?","Washington D.C.","New York","Los Angeles","Chicago","A","easy"),
    ("What does UNESCO stand for?","UN Educational Scientific Cultural Org","UN Emergency Security Council","UN Economic Social Commission","None","A","medium"),
    ("How many strings does a guitar have?","6","4","5","8","A","easy"),
    ("Butterfly is the adult stage of?","Caterpillar","Larva","Pupa","Grub","A","easy"),
    ("Heart of cricket bat made from?","Willow","Oak","Pine","Teak","A","medium"),
    ("How many hours in a day?","24","12","48","36","A","easy"),
    ("What is the national bird of India?","Peacock","Parrot","Eagle","Kingfisher","A","easy"),
    ("Water freezes at what temperature?","0°C","4°C","-4°C","100°C","A","easy"),
    ("How many teeth does an adult have?","32","28","30","34","A","medium"),
    ("Light year measures?","Distance","Time","Speed","Mass","A","medium"),
    ("Which animal cannot jump?","Elephant","Tiger","Horse","Lion","A","medium"),
    ("Great Wall of China is in?","China","Mongolia","Tibet","Korea","A","easy"),
    ("Who wrote the national anthem of India?","Rabindranath Tagore","Bankim Chandra","Iqbal","Gandhi","A","easy"),
    ("Largest planet in solar system?","Jupiter","Saturn","Uranus","Neptune","A","easy"),
    ("How many bones in human skull?","22","20","24","18","A","hard"),
],
"Sports": [
    ("How many players in cricket team?","11","9","10","12","A","easy"),
    ("Football (soccer) goal width?","7.32 meters","6 meters","8 meters","7 meters","A","hard"),
    ("Olympic rings represent?","5 continents","5 oceans","5 sports","5 nations","A","easy"),
    ("A century in cricket is?","100 runs","50 runs","200 runs","150 runs","A","easy"),
    ("Wimbledon is played on?","Grass","Clay","Hard court","Carpet","A","easy"),
    ("How many players in basketball team?","5","6","4","7","A","easy"),
    ("Marathon distance?","42.195 km","40 km","45 km","50 km","A","medium"),
    ("Who holds most Grand Slam titles (men)?","Novak Djokovic","Federer","Nadal","Sampras","A","medium"),
    ("Offside rule is in?","Football (soccer)","Cricket","Tennis","Basketball","A","easy"),
    ("How many holes in golf?","18","9","27","36","A","easy"),
    ("A hat-trick in football means?","3 goals in one match","3 assists","2 goals","4 goals","A","easy"),
    ("Swimming stroke 'butterfly' invented in?","USA","Australia","UK","Germany","A","hard"),
    ("How many sets in women's Grand Slam?","3","5","2","4","A","medium"),
    ("Penalty shootout in football: distance?","12 yards","10 yards","15 yards","8 yards","A","medium"),
    ("Yellow card in football means?","Caution/Warning","Sending off","Goal disallowed","Penalty","A","easy"),
    ("Highest score in single cricket over?","36","30","24","42","A","medium"),
    ("Badminton originated in?","India","China","England","Japan","A","medium"),
    ("How many players in volleyball team?","6","5","7","8","A","easy"),
    ("Ashes cricket series is between?","England and Australia","England and India","Australia and India","England and WI","A","medium"),
    ("Chess originated in?","India","China","Persia","Greece","A","medium"),
    ("In swimming, how many lengths is 1km in 50m pool?","20","10","25","50","A","medium"),
    ("Table tennis also known as?","Ping pong","Squash","Racquetball","Paddle ball","A","easy"),
    ("Fastest bowler speed in cricket?","160+ km/h","140 km/h","150 km/h","170 km/h","A","hard"),
    ("Tour de France is a?","Cycling race","Marathon","Triathlon","Rally","A","easy"),
    ("Formula 1 tire type for rain?","Wet tyres","Slick tyres","Hard tyres","Soft tyres","A","medium"),
    ("A birdie in golf is?","1 under par","1 over par","2 under par","Even par","A","medium"),
    ("Fencing sport uses what weapon?","Foil épée sabre","Sword only","Spear","Bow","A","medium"),
    ("How many quarters in basketball?","4","2","3","6","A","easy"),
    ("Decathlon has how many events?","10","5","7","12","A","medium"),
    ("LBW rule is in?","Cricket","Football","Tennis","Hockey","A","easy"),
],
"Music": [
    ("How many notes in a musical scale?","7","5","8","6","A","easy"),
    ("A guitar has how many strings?","6","4","5","8","A","easy"),
    ("Beethoven was?","Composer","Painter","Writer","Sculptor","A","easy"),
    ("What is tempo in music?","Speed of music","Volume","Pitch","Rhythm pattern","A","medium"),
    ("Treble clef notes start with?","E G B D F","A C E G B","F A C E","B D F A","A","hard"),
    ("How many keys does a standard piano have?","88","76","72","100","A","medium"),
    ("Mozart was from?","Austria","Germany","France","Italy","A","easy"),
    ("What is an octave?","8 notes apart","4 notes","12 notes","6 notes","A","medium"),
    ("Rhythm means?","Beat pattern","Volume","Speed","Pitch","A","easy"),
    ("Jazz music originated in?","USA","UK","France","Brazil","A","easy"),
    ("Violin family includes?","Viola cello double bass","Guitar banjo mandolin","Clarinet oboe bassoon","Trumpet horn tuba","A","medium"),
    ("What is a rest in music?","Silence symbol","Loud note","Low note","Fast note","A","medium"),
    ("Solfege system: do re mi... what comes next?","Fa","La","Sol","Ti","A","medium"),
    ("Opera is?","Dramatic musical performance","Instrumental only","Dance performance","Poetry reading","A","easy"),
    ("The Beatles were from?","England","USA","Australia","Ireland","A","easy"),
    ("What is harmony?","Multiple notes together","Single note","Tempo change","Volume change","A","medium"),
    ("Notation for very soft music?","pp (pianissimo)","ff (fortissimo)","mf (mezzo-forte)","f (forte)","A","medium"),
    ("Flute belongs to which family?","Woodwind","Brass","String","Percussion","A","easy"),
    ("What is a chord?","3+ notes played together","Single note","Scale","Arpeggio","A","medium"),
    ("Bass clef is also called?","F clef","G clef","C clef","B clef","A","medium"),
    ("What is syncopation?","Off-beat emphasis","On-beat emphasis","Even rhythm","No rhythm","A","hard"),
    ("Hip-hop originated in?","USA","Jamaica","UK","Africa","A","easy"),
    ("What is a coda?","End section of music","Beginning","Middle section","Repeated section","A","medium"),
    ("Timpani is a type of?","Drum","String","Wind","Brass","A","medium"),
    ("What is a ballad?","Slow romantic song","Fast song","Dance music","Instrumental","A","easy"),
    ("Reggae music originated in?","Jamaica","USA","UK","Nigeria","A","easy"),
    ("What is vibrato?","Pitch variation in singing","Volume change","Speed change","Tone change","A","medium"),
    ("Staccato means?","Short detached notes","Long smooth notes","Loud notes","Soft notes","A","medium"),
    ("What does Da Capo mean?","From the beginning","To the end","Repeat twice","Slow down","A","hard"),
    ("Sitar is instrument from?","India","China","Japan","Persia","A","easy"),
],
"Art": [
    ("Who painted the Sistine Chapel ceiling?","Michelangelo","da Vinci","Raphael","Botticelli","A","easy"),
    ("Primary colors are?","Red Blue Yellow","Red Green Blue","Cyan Magenta Yellow","Red Orange Yellow","A","easy"),
    ("What is perspective in art?","Depth on flat surface","Color mixing","Texture","Composition","A","medium"),
    ("Impressionism started in?","France","England","Italy","Germany","A","easy"),
    ("The Starry Night by?","Van Gogh","Monet","Renoir","Cézanne","A","easy"),
    ("What is a portrait?","Picture of a person","Landscape","Still life","Abstract","A","easy"),
    ("What medium did Michelangelo use for David?","Marble","Bronze","Clay","Wood","A","easy"),
    ("Picasso co-founded?","Cubism","Surrealism","Impressionism","Realism","A","easy"),
    ("What is a fresco?","Paint on wet plaster","Oil painting","Watercolor","Pastel","A","medium"),
    ("Japanese art style 'ukiyo-e' means?","Pictures of floating world","Mountain scenes","Ocean scenes","City scenes","A","hard"),
    ("What is chiaroscuro?","Light and shadow contrast","Color mixing","Line technique","Texture","A","hard"),
    ("Salvador Dali associated with?","Surrealism","Cubism","Impressionism","Expressionism","A","easy"),
    ("What is collage?","Assembled paper/materials art","Paint technique","Drawing method","Print technique","A","easy"),
    ("Rodin's famous sculpture?","The Thinker","David","Venus de Milo","The Kiss","A","easy"),
    ("Renaissance means?","Rebirth","Revolution","Reform","Religion","A","easy"),
    ("What is negative space?","Empty space around subject","Dark colors","Background color","Shadow","A","medium"),
    ("Andy Warhol is associated with?","Pop Art","Abstract Expressionism","Cubism","Surrealism","A","easy"),
    ("What is watercolor?","Water-soluble paint","Oil-based paint","Acrylic paint","Chalk paint","A","easy"),
    ("Mona Lisa is how wide?","77 cm","100 cm","50 cm","120 cm","A","hard"),
    ("What is typography?","Art of text arrangement","Color theory","Sculpture technique","Photography","A","medium"),
    ("What is a mosaic?","Art from small tiles/pieces","Weaving","Pottery","Wood carving","A","easy"),
    ("What is abstract art?","Non-representational art","Realistic art","Portrait art","Landscape art","A","easy"),
    ("Bauhaus was a?","Design school","Art movement","Museum","Gallery","A","medium"),
    ("What is etching?","Print-making with acid","Painting","Sculpture","Photography","A","medium"),
    ("Color wheel opposite colors are?","Complementary","Analogous","Monochromatic","Triadic","A","medium"),
    ("What is a still life?","Painting of inanimate objects","Landscape","Portrait","Abstract","A","easy"),
    ("Banksy is a famous?","Street artist","Classical painter","Sculptor","Photographer","A","easy"),
    ("What is calligraphy?","Beautiful handwriting art","Typography","Printing","Engraving","A","easy"),
    ("Leonardo da Vinci was also a?","Scientist and inventor","Only painter","Only sculptor","Only architect","A","easy"),
    ("What is a triptych?","3-panel artwork","Single painting","2-panel artwork","4-panel artwork","A","medium"),
],
"Economics": [
    ("GDP stands for?","Gross Domestic Product","General Domestic Product","Gross Development Product","General Development Product","A","easy"),
    ("Inflation means?","Rising prices","Falling prices","Stable prices","Price control","A","easy"),
    ("What is supply and demand?","Market price theory","Government policy","Trade agreement","Banking system","A","easy"),
    ("A monopoly is?","One seller controls market","Many sellers compete","Government control","No competition law","A","easy"),
    ("What is fiscal policy?","Government spending/taxation","Central bank interest rates","Trade policy","Foreign exchange","A","medium"),
    ("What is a recession?","2+ quarters GDP decline","GDP growth","Stock market rise","Low unemployment","A","medium"),
    ("Who wrote The Wealth of Nations?","Adam Smith","Keynes","Marx","Friedman","A","easy"),
    ("What is depreciation?","Asset value decrease","Asset value increase","Cost of production","Revenue loss","A","medium"),
    ("Opportunity cost is?","Next best alternative forgone","Total cost","Fixed cost","Variable cost","A","medium"),
    ("What is a budget deficit?","Spending exceeds revenue","Revenue exceeds spending","Balanced budget","Surplus budget","A","easy"),
    ("IMF stands for?","International Monetary Fund","International Market Fund","Internal Monetary Finance","International Money Foundation","A","easy"),
    ("What is free trade?","No trade barriers","High tariffs","Import quotas","Trade wars","A","easy"),
    ("What is outsourcing?","Hiring external companies","Internal production","Government contracts","Trade agreements","A","easy"),
    ("Barter economy uses?","Goods for goods exchange","Money exchange","Credit exchange","Digital exchange","A","easy"),
    ("What is compound interest?","Interest on interest","Simple interest","Fixed interest","Zero interest","A","medium"),
    ("Bull market means?","Rising stock prices","Falling stock prices","Stable prices","High volatility","A","medium"),
    ("What is PPP?","Purchasing Power Parity","Price Parity Policy","Production Power Parity","None","A","hard"),
    ("WTO handles?","International trade rules","Currency exchange","Development loans","Emergency aid","A","medium"),
    ("What is an oligopoly?","Few firms dominate market","One firm dominates","Many firms compete","Government monopoly","A","medium"),
    ("What is microeconomics?","Study of individual units","Study of whole economy","Study of government","Study of trade","A","easy"),
    ("Quantitative easing involves?","Central bank buying assets","Tax reduction","Interest rate increase","Trade barriers","A","hard"),
    ("Elasticity measures?","Demand response to price change","Supply only","Income only","Cost change","A","medium"),
    ("What is stagflation?","Inflation + stagnation","Just inflation","Just stagnation","Deflation + growth","A","hard"),
    ("Bear market means?","Falling stock prices","Rising stock prices","Stable market","High volume trading","A","medium"),
    ("What is venture capital?","Investment in startups","Government loans","Bank loans","Bonds","A","medium"),
    ("Laissez-faire means?","Let market be free","Government control","Mixed economy","Planned economy","A","medium"),
    ("What is a tariff?","Tax on imports","Import ban","Export tax","Currency tax","A","easy"),
    ("Keynesian economics focuses on?","Government spending","Free markets","Gold standard","Barter","A","medium"),
    ("What is liquidity?","Ease of converting to cash","Interest rate","Credit score","Asset value","A","medium"),
    ("What is GNP?","Gross National Product","Gross National Price","General National Product","Gross National Policy","A","easy"),
],
"Logical Reasoning": [
    ("All roses are flowers. All flowers need water. Therefore?","Roses need water","Flowers are roses","Water makes flowers","None","A","easy"),
    ("What comes next: 2, 4, 8, 16, ?","32","24","20","28","A","easy"),
    ("If A > B and B > C, then?","A > C","C > A","A = C","Cannot determine","A","easy"),
    ("What comes next: 1, 4, 9, 16, ?","25","20","24","30","A","easy"),
    ("Odd one out: Square, Circle, Triangle, Cone?","Cone","Square","Circle","Triangle","A","medium"),
    ("If today is Monday, what day is 100 days later?","Wednesday","Thursday","Tuesday","Friday","A","medium"),
    ("What comes next: A, C, E, G, ?","I","H","J","F","A","easy"),
    ("If MANGO = 13142115, what is APPLE?","1161612","116125","1161612","116512","A","hard"),
    ("Complete: 3 : 9 :: 5 : ?","25","10","15","20","A","easy"),
    ("How many squares in a 3×3 grid?","14","9","12","16","A","hard"),
    ("If all cats are animals and some animals are pets, then?","Some cats may be pets","All cats are pets","No cats are pets","Cats are not animals","A","medium"),
    ("What comes next: 1, 1, 2, 3, 5, 8, ?","13","11","12","14","A","medium"),
    ("Odd one out: Apple, Mango, Carrot, Banana?","Carrot","Apple","Mango","Banana","A","easy"),
    ("Mirror image: 'p' becomes?","q","b","d","p","A","medium"),
    ("If 5 workers take 5 days, how many workers to finish in 1 day?","25","5","10","15","A","medium"),
    ("What is the angle sum in a triangle?","180°","360°","90°","270°","A","easy"),
    ("A is B's father. B is C's son. What is A to C?","Grandfather","Father","Uncle","Brother","A","medium"),
    ("Clock shows 3:00. What is angle between hands?","90°","180°","45°","60°","A","easy"),
    ("What comes next: Z, X, V, T, ?","R","S","Q","P","A","medium"),
    ("If 2+3=10, 3+4=21, 4+5=34, then 5+6=?","55","45","50","65","A","hard"),
    ("Odd one out: Dog, Cat, Parrot, Lion?","Parrot","Dog","Cat","Lion","A","medium"),
    ("What comes next: 100, 50, 25, 12.5, ?","6.25","5","7.5","8","A","medium"),
    ("If NORTH = SOUTH, then EAST = ?","WEST","NORTH","SOUTH","UP","A","easy"),
    ("How many triangles in a Star of David?","6","12","8","10","A","hard"),
    ("If a clock gains 5 min every hour, in 12 hours it shows?","1 hour ahead","30 min ahead","2 hours ahead","15 min ahead","A","medium"),
    ("Complete: Man : Biped :: Bird : ?","Biped","Quadruped","Triped","Multiped","A","medium"),
    ("What comes next: 3, 6, 12, 24, ?","48","36","40","56","A","easy"),
    ("Odd one out: Pen, Pencil, Eraser, Sharpener?","Sharpener","Pen","Pencil","Eraser","A","hard"),
    ("If 4 boys eat 4 sandwiches in 4 minutes, how many in 8 minutes?","8","16","4","12","A","hard"),
    ("Square root of 256?","16","14","18","20","A","medium"),
],
"Current Affairs": [
    ("United Nations headquarters is in?","New York","Geneva","Paris","London","A","easy"),
    ("G20 is a group of?","20 major economies","20 nations","20 UN members","20 democracies","A","easy"),
    ("WHO stands for?","World Health Organization","World Heritage Organization","World Human Organization","World Help Organization","A","easy"),
    ("Paris Agreement is about?","Climate change","Trade","Security","Nuclear","A","easy"),
    ("BRICS originally included Brazil Russia India China and?","South Africa","USA","Japan","Germany","A","medium"),
    ("SDGs stand for?","Sustainable Development Goals","Social Development Goals","Science Development Goals","Safety Development Goals","A","medium"),
    ("NATO is a?","Military alliance","Trade alliance","Cultural alliance","Economic alliance","A","easy"),
    ("Interpol is?","International police organization","Internet police","Space agency","Trade body","A","easy"),
    ("Where is UN Security Council?","New York","Geneva","Vienna","Brussels","A","medium"),
    ("UNICEF helps?","Children","Adults","Environment","Economy","A","easy"),
    ("What does IMF do?","International financial stability","World trade","Development projects","Security operations","A","medium"),
    ("World Bank focuses on?","Development and poverty","Military","Culture","Space","A","easy"),
    ("OPEC controls?","Oil production","Food supply","Technology","Finance","A","medium"),
    ("COP meetings discuss?","Climate change","Population","Food","Technology","A","medium"),
    ("Human rights declaration year?","1948","1945","1950","1960","A","medium"),
    ("Internet governance is by?","Multi-stakeholder","Single government","UN only","USA only","A","hard"),
    ("Artificial Intelligence regulations are?","Being developed globally","Fully established","Not needed","US only","A","medium"),
    ("Cybersecurity threats include?","Ransomware, phishing, hacking","Only viruses","Only spam","Only theft","A","medium"),
    ("Space tourism is?","Becoming commercial","Not possible","Very old","Only military","A","easy"),
    ("What is cryptocurrency?","Digital currency","Physical coin","Bank currency","Stock","A","easy"),
    ("Social media's biggest challenge?","Misinformation","Slow speed","High cost","Low users","A","medium"),
    ("Electric vehicles aim to reduce?","Carbon emissions","Traffic","Accidents","Speed","A","easy"),
    ("5G networks offer?","Faster connectivity","Slower speeds","Less coverage","Less security","A","easy"),
    ("Pandemic preparedness involves?","Global cooperation","Single country","Local only","Military","A","medium"),
    ("Refugees are protected by?","UNHCR","WHO","UNICEF","IMF","A","medium"),
    ("E-waste is a problem because?","Toxic materials","Heavy weight","High cost","Slow recycling","A","medium"),
    ("Digital divide refers to?","Unequal tech access","Internet speed","Social media","Gaming","A","medium"),
    ("Telemedicine uses?","Technology for remote healthcare","Physical hospitals","Surgery robots","Lab tests only","A","easy"),
    ("What is food security?","Access to sufficient food","Food quality","Organic food","Fast food","A","easy"),
    ("Smart cities use?","Technology for efficiency","Only buildings","Parks only","Roads only","A","easy"),
],
"Environment": [
    ("Greenhouse gases include?","CO2, methane, N2O","O2 and N2","Argon and helium","Only CO2","A","easy"),
    ("Ozone layer protects from?","UV radiation","Gamma rays","X-rays","Infrared","A","easy"),
    ("What is deforestation?","Clearing forests","Planting trees","Forest fire","Flood","A","easy"),
    ("Acid rain is caused by?","SO2 and NOx emissions","CO2","Dust","Water vapor","A","medium"),
    ("Biodiversity means?","Variety of life forms","Same species","Plant life only","Animal life only","A","easy"),
    ("What is composting?","Organic waste decomposition","Burning waste","Plastic recycling","Chemical treatment","A","easy"),
    ("Solar energy is?","Renewable","Non-renewable","Nuclear","Chemical","A","easy"),
    ("What is an ecosystem?","Community of organisms + environment","Only animals","Only plants","Only water","A","medium"),
    ("Carbon footprint measures?","CO2 emissions from activities","Water usage","Land usage","Energy produced","A","medium"),
    ("Fossil fuels include?","Coal, oil, natural gas","Wood and biomass","Solar and wind","Nuclear and hydro","A","easy"),
    ("Rainforest covers what % of Earth's surface?","6%","20%","30%","10%","A","hard"),
    ("What is eutrophication?","Excess nutrients in water","Water shortage","Ocean acidification","Drought","A","hard"),
    ("What is permafrost?","Permanently frozen ground","Tropical soil","Desert sand","Ocean floor","A","medium"),
    ("Which gas causes most warming?","CO2","Methane","N2O","Water vapor","A","medium"),
    ("What is reforestation?","Replanting cut forests","Cutting forests","Burning forests","Flooding forests","A","easy"),
    ("Ocean acidification is due to?","CO2 absorption","Salt increase","Temperature only","Wind change","A","medium"),
    ("What is sustainable development?","Meeting needs without harming future","Economic growth only","Industrialization","Urbanization","A","medium"),
    ("Endangered species are?","At risk of extinction","Common species","Invasive species","Domestic species","A","easy"),
    ("What is a wetland?","Water-saturated land ecosystem","Desert","Forest","Mountain","A","medium"),
    ("Climate change is mainly caused by?","Human activities","Natural cycles","Solar changes","Volcanic eruptions","A","medium"),
    ("What is the carbon cycle?","Carbon movement through environment","Carbon storage","Carbon burning","Carbon mining","A","medium"),
    ("Coral reefs are threatened by?","Warming and acidification","Cold water","Rain","Wind","A","medium"),
    ("Wind energy uses?","Turbines","Solar panels","Dams","Geothermal","A","easy"),
    ("What is environmental impact assessment?","Evaluating project effects on environment","Building assessment","Economic evaluation","Political review","A","medium"),
    ("Plastic pollution affects?","Oceans and marine life","Only land","Only air","Only soil","A","easy"),
    ("What is a carbon sink?","Absorbs more CO2 than releases","Releases more CO2","Neutral CO2","Produces oxygen only","A","hard"),
    ("Hydroelectric power uses?","Water flow","Sunlight","Wind","Heat","A","easy"),
    ("What is biomass energy?","Energy from organic material","Solar energy","Wind energy","Nuclear energy","A","medium"),
    ("What are invasive species?","Non-native harmful species","Native species","Endangered species","Extinct species","A","medium"),
    ("Earth Day is celebrated on?","April 22","June 5","March 21","July 4","A","easy"),
],
"Health & Nutrition": [
    ("BMI stands for?","Body Mass Index","Body Muscle Index","Basic Mass Index","Body Metabolic Index","A","easy"),
    ("How many calories in 1 gram of fat?","9","4","7","11","A","medium"),
    ("Which vitamin prevents scurvy?","Vitamin C","Vitamin D","Vitamin A","Vitamin B12","A","easy"),
    ("Anemia is lack of?","Iron","Calcium","Vitamin D","Zinc","A","easy"),
    ("Normal resting heart rate?","60-100 bpm","40-60 bpm","100-120 bpm","30-50 bpm","A","easy"),
    ("What is a calorie?","Unit of energy","Unit of weight","Unit of fat","Unit of protein","A","easy"),
    ("Which food is highest in protein?","Eggs","Rice","Bread","Fruit","A","easy"),
    ("What is hypertension?","High blood pressure","Low blood pressure","Fast heartbeat","Slow heartbeat","A","easy"),
    ("Recommended daily water intake?","2-3 liters","1 liter","5 liters","0.5 liters","A","easy"),
    ("What is diabetes?","High blood sugar condition","Low blood pressure","Heart condition","Bone condition","A","easy"),
    ("Omega-3 fatty acids found in?","Fish and nuts","Candy","Soda","White bread","A","easy"),
    ("What is a balanced diet?","All nutrients in right proportions","Only vegetables","Only protein","Only carbs","A","easy"),
    ("Calcium is important for?","Bones and teeth","Vision","Immunity","Blood","A","easy"),
    ("What is the immune system?","Body defense against disease","Digestive system","Skeletal system","Nervous system","A","easy"),
    ("Sleep is important for?","Recovery and health","Only rest","Only growth","Only memory","A","easy"),
    ("What is cholesterol?","Fatty substance in blood","Sugar in blood","Protein in blood","Mineral in blood","A","medium"),
    ("Fiber helps with?","Digestion","Muscle growth","Vision","Immunity","A","easy"),
    ("What is obesity?","Excess body fat condition","Muscle condition","Bone condition","Skin condition","A","easy"),
    ("Iron deficiency causes?","Anemia","Rickets","Scurvy","Goiter","A","medium"),
    ("Vitamin D deficiency causes?","Rickets","Scurvy","Anemia","Goiter","A","medium"),
    ("Which mineral strengthens teeth?","Fluoride","Iron","Zinc","Copper","A","medium"),
    ("What is metabolism?","Chemical processes in body","Exercise type","Diet type","Sleep pattern","A","medium"),
    ("Probiotics are good for?","Gut health","Bone health","Eye health","Heart health","A","medium"),
    ("What is dehydration?","Lack of body water","Lack of food","Lack of sleep","Lack of vitamins","A","easy"),
    ("Antioxidants protect against?","Cell damage","Bone loss","Muscle loss","Weight gain","A","medium"),
    ("What is malnutrition?","Poor nutrition status","Only starvation","Only overeating","Vitamin excess","A","easy"),
    ("Potassium is found in?","Bananas and potatoes","Only meat","Only fish","Only dairy","A","easy"),
    ("What is a pandemic?","Global disease outbreak","Local disease","Seasonal flu","Epidemic","A","medium"),
    ("Exercise benefits include?","Physical and mental health","Only weight loss","Only strength","Only flexibility","A","easy"),
    ("What is insomnia?","Inability to sleep","Too much sleep","Irregular sleep","Daytime sleep","A","easy"),
],
"Technology": [
    ("AI stands for?","Artificial Intelligence","Automated Intelligence","Actual Intelligence","Applied Intelligence","A","easy"),
    ("What is machine learning?","AI that learns from data","Programming languages","Computer hardware","Internet protocol","A","easy"),
    ("What is the Internet of Things?","Connected physical devices","Internet network","Software system","Database","A","medium"),
    ("Blockchain technology is?","Decentralized digital ledger","Centralized database","Social network","Cloud storage","A","medium"),
    ("What is augmented reality?","Digital overlay on real world","Virtual world","Computer simulation","Game engine","A","medium"),
    ("What is a smartphone?","Handheld computer phone","Only calling device","Only camera","Music player","A","easy"),
    ("What is 5G?","5th generation wireless","5 gigabyte internet","5 GB phone storage","5 GHz only","A","easy"),
    ("What is big data?","Large complex data sets","Small structured data","Manual data","Paper data","A","medium"),
    ("What is cybersecurity?","Protecting digital systems","Physical security","Building security","Document security","A","easy"),
    ("What is an app?","Software application","Hardware device","Internet service","Data storage","A","easy"),
    ("What is automation?","Machines doing tasks automatically","Manual work","Outsourcing","Remote work","A","easy"),
    ("What is virtual reality?","Simulated 3D environment","Online meeting","Video calling","Photography","A","easy"),
    ("What is a QR code?","Quick Response code","Queue Request code","Quick Rate code","Query Result code","A","easy"),
    ("What is nanotechnology?","Manipulating matter at atomic scale","Space technology","Chemical technology","Medical only","A","medium"),
    ("What is GPS?","Global Positioning System","General Purpose Software","Graphics Processing System","Group Protocol Service","A","easy"),
    ("What is data privacy?","Controlling personal information","Sharing data","Deleting data","Copying data","A","easy"),
    ("What is a bot?","Automated software program","Human worker","Hardware device","Network cable","A","medium"),
    ("What is e-commerce?","Online buying and selling","Electronic mail","Digital entertainment","Online education","A","easy"),
    ("What is a server?","Computer providing services to others","Personal computer","Tablet","Phone","A","medium"),
    ("What is open source software?","Freely available source code","Expensive software","Secret code","Patented software","A","easy"),
    ("What is API?","Application Programming Interface","Automated Process Integration","Application Procedure Interface","Advanced Programming Interface","A","medium"),
    ("What is streaming?","Real-time data delivery","Downloading files","Uploading data","Storing data","A","easy"),
    ("What is a pixel in a camera?","Light-capturing unit","Color unit","Lens type","Shutter speed","A","medium"),
    ("What is SaaS?","Software as a Service","System as a Service","Storage as a Service","Security as a Service","A","medium"),
    ("What is a digital signature?","Electronic verification","Physical stamp","Username","Password","A","medium"),
    ("What is thermal printing?","Heat-based printing","Ink-based printing","Laser printing","3D printing","A","medium"),
    ("What is a touchscreen?","Pressure-sensitive display","Regular screen","Projector","Monitor","A","easy"),
    ("What is wireless charging?","Electromagnetic energy transfer","Battery replacement","Solar charging","Manual charging","A","medium"),
    ("What is a smart home?","IoT-connected home systems","Large house","New house","Renovated house","A","easy"),
    ("What is deepfake technology?","AI-generated fake media","Real media","Traditional editing","Animation","A","medium"),
],
    }

# ─── HELPERS ─────────────────────────────────────────────────────────────────
def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def current_user():
    return session.get("user")

def get_level_info(xp):
    level = xp // 100 + 1
    progress = xp % 100
    return level, progress

def check_and_award_badges(user_id):
    conn = get_db()
    c = conn.cursor()
    user = c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    badges = c.execute("SELECT * FROM badges").fetchall()
    sessions = c.execute("SELECT * FROM quiz_sessions WHERE user_id=?", (user_id,)).fetchall()
    for badge in badges:
        owned = c.execute("SELECT 1 FROM user_badges WHERE user_id=? AND badge_id=?", (user_id, badge["id"])).fetchone()
        if owned:
            continue
        earned = False
        if badge["condition_type"] == "quizzes" and len(sessions) >= badge["condition_value"]:
            earned = True
        elif badge["condition_type"] == "perfect":
            if any(s["percentage"] == 100 for s in sessions):
                earned = True
        elif badge["condition_type"] == "high_score":
            high = sum(1 for s in sessions if s["percentage"] >= 80)
            if high >= badge["condition_value"]:
                earned = True
        elif badge["condition_type"] == "level" and user["level"] >= badge["condition_value"]:
            earned = True
        if earned:
            c.execute("INSERT OR IGNORE INTO user_badges (user_id,badge_id) VALUES (?,?)", (user_id, badge["id"]))
    conn.commit()
    conn.close()

# ─── ROUTES ───────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    if current_user():
        if current_user()["role"] == "admin":
            return redirect(url_for("admin_dashboard"))
        return redirect(url_for("student_dashboard"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username=? AND password=?", (u, p)).fetchone()
        conn.close()
        if user:
            session["user"] = dict(user)
            if user["role"] == "admin":
                return redirect(url_for("admin_dashboard"))
            return redirect(url_for("student_dashboard"))
        flash("Invalid credentials!","error")
    return render_template("login.html")

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]
        e = request.form.get("email","")
        conn = get_db()
        try:
            conn.execute("INSERT INTO users (username,password,email) VALUES (?,?,?)", (u, p, e))
            conn.commit()
            flash("Account created! Please login.","success")
            return redirect(url_for("login"))
        except:
            flash("Username already exists!","error")
        finally:
            conn.close()
    return render_template("register.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ─── STUDENT ──────────────────────────────────────────────────────────────────
@app.route("/dashboard")
def student_dashboard():
    if not current_user() or current_user()["role"] != "student":
        return redirect(url_for("login"))
    conn = get_db()
    uid = current_user()["id"]
    user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    cats = conn.execute("SELECT * FROM categories").fetchall()
    recent = conn.execute("""SELECT qs.*,c.name as cat_name,c.icon FROM quiz_sessions qs
        JOIN categories c ON qs.category_id=c.id WHERE qs.user_id=?
        ORDER BY qs.completed_at DESC LIMIT 5""", (uid,)).fetchall()
    badges = conn.execute("""SELECT b.* FROM badges b JOIN user_badges ub ON b.id=ub.badge_id WHERE ub.user_id=?""", (uid,)).fetchall()
    top = conn.execute("""SELECT u.username,u.avatar,u.level,
        SUM(qs.score) as total, COUNT(qs.id) as count
        FROM users u JOIN quiz_sessions qs ON u.id=qs.user_id
        WHERE u.role='student' GROUP BY u.id ORDER BY total DESC LIMIT 5""").fetchall()
    conn.close()
    level, progress = get_level_info(user["xp"])
    return render_template("dashboard.html", user=user, cats=cats,
                           recent=recent, badges=badges, top=top,
                           level=level, progress=progress)

@app.route("/quiz/<int:cat_id>")
def start_quiz(cat_id):
    if not current_user() or current_user()["role"] != "student":
        return redirect(url_for("login"))
    conn = get_db()
    cat = conn.execute("SELECT * FROM categories WHERE id=?", (cat_id,)).fetchone()
    qs = conn.execute("SELECT * FROM questions WHERE category_id=?", (cat_id,)).fetchall()
    conn.close()
    if len(qs) < 10:
        flash("Not enough questions!","error")
        return redirect(url_for("student_dashboard"))
    selected = random.sample(list(qs), 10)
    random.shuffle(selected)
    session["quiz"] = {
        "cat_id": cat_id,
        "questions": [dict(q) for q in selected],
        "current": 0,
        "score": 0,
        "correct": 0,
        "wrong": 0,
        "answers": [],
        "start_time": datetime.now().isoformat()
    }
    return render_template("quiz_start.html", cat=cat, total=len(selected))

@app.route("/quiz/question")
def quiz_question():
    if not current_user() or "quiz" not in session:
        return redirect(url_for("student_dashboard"))
    qz = session["quiz"]
    if qz["current"] >= len(qz["questions"]):
        return redirect(url_for("quiz_result"))
    q = qz["questions"][qz["current"]]
    options = [
        ("A", q["option_a"]),
        ("B", q["option_b"]),
        ("C", q["option_c"]),
        ("D", q["option_d"]),
    ]
    random.shuffle(options)
    return render_template("quiz_question.html", q=q, options=options,
                           num=qz["current"]+1, total=len(qz["questions"]),
                           score=qz["score"])

@app.route("/quiz/answer", methods=["POST"])
def quiz_answer():
    if not current_user() or "quiz" not in session:
        return redirect(url_for("student_dashboard"))
    qz = session["quiz"]
    q = qz["questions"][qz["current"]]
    chosen = request.form.get("answer","")
    correct = q["correct_answer"]
    is_correct = chosen == correct
    if is_correct:
        qz["score"] += 10
        qz["correct"] += 1
    else:
        qz["wrong"] += 1
    qz["answers"].append({"q": q["question"], "chosen": chosen, "correct": correct, "ok": is_correct})
    qz["current"] += 1
    session["quiz"] = qz
    return render_template("quiz_feedback.html", is_correct=is_correct,
                           correct_answer=correct, q=q, num=qz["current"],
                           total=len(qz["questions"]))

@app.route("/quiz/result")
def quiz_result():
    if not current_user() or "quiz" not in session:
        return redirect(url_for("student_dashboard"))
    qz = session["quiz"]
    uid = current_user()["id"]
    total_q = len(qz["questions"])
    pct = round((qz["correct"] / total_q) * 100, 1)
    start = datetime.fromisoformat(qz["start_time"])
    elapsed = int((datetime.now() - start).total_seconds())
    conn = get_db()
    conn.execute("""INSERT INTO quiz_sessions
        (user_id,category_id,score,total_questions,correct,wrong,time_taken,percentage)
        VALUES (?,?,?,?,?,?,?,?)""",
        (uid, qz["cat_id"], qz["score"], total_q, qz["correct"], qz["wrong"], elapsed, pct))
    xp_gain = qz["correct"] * 10 + (20 if pct == 100 else 0)
    conn.execute("UPDATE users SET xp=xp+?, total_score=total_score+?, quizzes_taken=quizzes_taken+1 WHERE id=?",
                 (xp_gain, qz["score"], uid))
    user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    new_level = user["xp"] // 100 + 1
    conn.execute("UPDATE users SET level=? WHERE id=?", (new_level, uid))
    conn.execute("INSERT INTO leaderboard (user_id,category_id,score,percentage) VALUES (?,?,?,?)",
                 (uid, qz["cat_id"], qz["score"], pct))
    conn.commit()
    cat = conn.execute("SELECT * FROM categories WHERE id=?", (qz["cat_id"],)).fetchone()
    conn.close()
    check_and_award_badges(uid)
    answers = qz["answers"]
    session.pop("quiz", None)
    return render_template("quiz_result.html",
                           score=qz["score"], correct=qz["correct"], wrong=qz["wrong"],
                           total=total_q, pct=pct, time=elapsed,
                           xp=xp_gain, cat=cat, answers=answers, uid=uid)

@app.route("/certificate/<int:uid>/<int:score>/<int:pct>/<cat_name>")
def download_certificate(uid, score, pct, cat_name):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    conn.close()
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(A4))
    W, H = landscape(A4)

    # Background gradient-like
    c.setFillColorRGB(0.05, 0.05, 0.15)
    c.rect(0, 0, W, H, fill=1, stroke=0)

    # Gold border
    c.setStrokeColorRGB(1, 0.84, 0)
    c.setLineWidth(8)
    c.rect(20, 20, W-40, H-40, fill=0, stroke=1)
    c.setLineWidth(2)
    c.rect(28, 28, W-56, H-56, fill=0, stroke=1)

    # Decorative corners
    for x, y in [(40,40),(W-40,40),(40,H-40),(W-40,H-40)]:
        c.circle(x, y, 8, fill=1, stroke=0)
        c.setFillColorRGB(1, 0.84, 0)
        c.circle(x, y, 8, fill=1, stroke=0)

    c.setFillColorRGB(1, 0.84, 0)
    c.setFont("Helvetica-Bold", 42)
    c.drawCentredString(W/2, H-100, "🏆 CERTIFICATE OF ACHIEVEMENT 🏆")

    c.setFillColorRGB(0.8, 0.8, 1.0)
    c.setFont("Helvetica", 18)
    c.drawCentredString(W/2, H-140, "This is to certify that")

    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 36)
    c.drawCentredString(W/2, H-190, user["username"].upper())

    c.setFillColorRGB(0.8, 0.8, 1.0)
    c.setFont("Helvetica", 18)
    c.drawCentredString(W/2, H-230, f"has successfully completed the  \"{cat_name}\"  Quiz")

    c.setFillColorRGB(1, 0.84, 0)
    c.setFont("Helvetica-Bold", 28)
    c.drawCentredString(W/2, H-280, f"Score: {score} Points  |  Accuracy: {pct}%")

    grade = "A+" if pct >= 90 else "A" if pct >= 80 else "B+" if pct >= 70 else "B" if pct >= 60 else "C"
    c.setFillColorRGB(0.4, 1, 0.4)
    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(W/2, H-320, f"Grade: {grade}")

    c.setFillColorRGB(0.6, 0.6, 0.9)
    c.setFont("Helvetica", 14)
    c.drawCentredString(W/2, H-370, f"Issued on: {datetime.now().strftime('%B %d, %Y')}")

    c.setFillColorRGB(1, 0.84, 0)
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(W/2, 80, "QUIZ MASTER APP  •  Excellence in Learning")

    # Stars
    c.setFont("Helvetica", 30)
    c.setFillColorRGB(1, 0.84, 0)
    stars = "★" * min(5, int(pct // 20))
    c.drawCentredString(W/2, H-350, stars)

    c.save()
    buf.seek(0)
    fname = f"Certificate_{user['username']}_{cat_name}.pdf"
    return send_file(buf, as_attachment=True, download_name=fname, mimetype="application/pdf")

@app.route("/leaderboard")
def leaderboard():
    if not current_user():
        return redirect(url_for("login"))
    conn = get_db()
    overall = conn.execute("""SELECT u.username,u.avatar,u.level,
        SUM(qs.score) as total_score, COUNT(qs.id) as quizzes,
        AVG(qs.percentage) as avg_pct
        FROM users u JOIN quiz_sessions qs ON u.id=qs.user_id
        WHERE u.role='student' GROUP BY u.id ORDER BY total_score DESC LIMIT 20""").fetchall()
    cats = conn.execute("SELECT * FROM categories").fetchall()
    conn.close()
    return render_template("leaderboard.html", overall=overall, cats=cats, user=current_user())

# ─── ADMIN ────────────────────────────────────────────────────────────────────
@app.route("/admin")
def admin_dashboard():
    if not current_user() or current_user()["role"] != "admin":
        return redirect(url_for("login"))
    conn = get_db()
    stats = {
        "users": conn.execute("SELECT COUNT(*) FROM users WHERE role='student'").fetchone()[0],
        "questions": conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0],
        "quizzes": conn.execute("SELECT COUNT(*) FROM quiz_sessions").fetchone()[0],
        "categories": conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0],
    }
    cats = conn.execute("""SELECT c.*, COUNT(q.id) as q_count
        FROM categories c LEFT JOIN questions q ON c.id=q.category_id
        GROUP BY c.id""").fetchall()
    recent_users = conn.execute("SELECT * FROM users WHERE role='student' ORDER BY created_at DESC LIMIT 5").fetchall()
    recent_sessions = conn.execute("""SELECT qs.*,u.username,c.name as cat_name,c.icon
        FROM quiz_sessions qs JOIN users u ON qs.user_id=u.id
        JOIN categories c ON qs.category_id=c.id ORDER BY qs.completed_at DESC LIMIT 10""").fetchall()
    conn.close()
    return render_template("admin_dashboard.html", stats=stats, cats=cats,
                           recent_users=recent_users, recent_sessions=recent_sessions,
                           user=current_user())

@app.route("/admin/questions/<int:cat_id>")
def admin_questions(cat_id):
    if not current_user() or current_user()["role"] != "admin":
        return redirect(url_for("login"))
    conn = get_db()
    cat = conn.execute("SELECT * FROM categories WHERE id=?", (cat_id,)).fetchone()
    qs = conn.execute("SELECT * FROM questions WHERE category_id=?", (cat_id,)).fetchall()
    conn.close()
    return render_template("admin_questions.html", cat=cat, questions=qs, user=current_user())

@app.route("/admin/add_question", methods=["GET","POST"])
def add_question():
    if not current_user() or current_user()["role"] != "admin":
        return redirect(url_for("login"))
    conn = get_db()
    cats = conn.execute("SELECT * FROM categories").fetchall()
    if request.method == "POST":
        f = request.form
        conn.execute("""INSERT INTO questions
            (category_id,question,option_a,option_b,option_c,option_d,correct_answer,difficulty)
            VALUES (?,?,?,?,?,?,?,?)""",
            (f["category_id"], f["question"], f["option_a"], f["option_b"],
             f["option_c"], f["option_d"], f["correct_answer"], f["difficulty"]))
        conn.commit()
        conn.close()
        flash("Question added!","success")
        return redirect(url_for("admin_questions", cat_id=f["category_id"]))
    conn.close()
    return render_template("add_question.html", cats=cats, user=current_user())

@app.route("/admin/delete_question/<int:qid>", methods=["POST"])
def delete_question(qid):
    if not current_user() or current_user()["role"] != "admin":
        return redirect(url_for("login"))
    conn = get_db()
    q = conn.execute("SELECT category_id FROM questions WHERE id=?", (qid,)).fetchone()
    cat_id = q["category_id"] if q else 1
    conn.execute("DELETE FROM questions WHERE id=?", (qid,))
    conn.commit()
    conn.close()
    flash("Question deleted!","success")
    return redirect(url_for("admin_questions", cat_id=cat_id))

@app.route("/admin/users")
def admin_users():
    if not current_user() or current_user()["role"] != "admin":
        return redirect(url_for("login"))
    conn = get_db()
    users = conn.execute("""SELECT u.*,
        COUNT(qs.id) as quiz_count, SUM(qs.score) as total_score
        FROM users u LEFT JOIN quiz_sessions qs ON u.id=qs.user_id
        WHERE u.role='student' GROUP BY u.id ORDER BY total_score DESC""").fetchall()
    conn.close()
    return render_template("admin_users.html", users=users, user=current_user())

@app.route("/admin/scores")
def admin_scores():
    if not current_user() or current_user()["role"] != "admin":
        return redirect(url_for("login"))
    conn = get_db()
    sessions = conn.execute("""SELECT qs.*,u.username,c.name as cat_name,c.icon,c.color
        FROM quiz_sessions qs JOIN users u ON qs.user_id=u.id
        JOIN categories c ON qs.category_id=c.id
        ORDER BY qs.completed_at DESC""").fetchall()
    conn.close()
    return render_template("admin_scores.html", sessions=sessions, user=current_user())

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    os.makedirs("certificates", exist_ok=True)
    init_db()
    seed_data()
    print("\n" + "="*55)
    print("   🎓  QUIZ MASTER APP  — RUNNING!")
    print("="*55)
    print("   URL  :  http://127.0.0.1:5000")
    print("   Admin:  username=admin  password=admin123")
    print("   Student: username=student1  password=student123")
    print("="*55 + "\n")
    app.run(debug=True, port=5000)
