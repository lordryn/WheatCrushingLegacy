import base64
from io import BytesIO
from flask import Flask, render_template, request, redirect
import requests
import json
from urllib.request import urlopen
from bs4 import BeautifulSoup
import datetime
import pytz
import codecs
import firebase_admin
from firebase_admin import credentials, db
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import FormatStrFormatter
from matplotlib import rcParams
from apscheduler.schedulers.background import BackgroundScheduler

# Firebase init
cred = credentials.Certificate("wheatcrushinglegacy-firebase-adminsdk-s2vey-cfcbe88dbe.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://wheatcrushinglegacy-default-rtdb.firebaseio.com/'
})
fdb = db.reference()
print("✅ Firebase initialized")

# Plot style
rcParams["axes.grid"] = True
plt.style.use('dark_background')
rcParams["axes.formatter.limits"] = [0, 1000000000000]


try:
    ref = db.reference("leaderboard")
    snapshot = ref.get()
    if snapshot:
        print(f"✅ Found leaderboard data with {len(snapshot)} snapshots")
    else:
        print("⚠️ Leaderboard path exists but contains no data")
except Exception as e:
    print("❌ Firebase leaderboard read failed:", e)
app = Flask(__name__)


# --- Helpers ---
def get_dt():
    now = datetime.datetime.now(pytz.timezone('America/Chicago'))
    return now.strftime('%Y-%m-%d-%H-%M')

def get_stat_ref():
    with open("stat_ref.txt", "r") as f:
        return f.read().splitlines()

def strip_to_text(url):
    html = urlopen(url.replace('�', '%20')).read()
    soup = BeautifulSoup(html, features="html.parser")
    for script in soup(["script", "style"]):
        script.extract()
    lines = (line.strip() for line in soup.get_text().splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    return '\n'.join(chunk for chunk in chunks if chunk)

def assign_all(raw, key, rsn):
    rawList = raw.replace(',', '\n').splitlines()
    while len(rawList) > 87:
        rawList.pop()
    formedDict = dict(zip(key, map(int, rawList)))
    dt = get_dt()
    fdb.child('stats').child(rsn).child(dt).set(formedDict)
    print(f"✅ Pushed stats for {rsn} at {dt}")


def commit_skills(rsn):
    raw = strip_to_text(f'https://secure.runescape.com/m=hiscore/index_lite.ws?player={rsn}')
    assign_all(raw, get_stat_ref(), rsn)

def list_to_int(lst):
    return sorted([int(x) for x in lst if x.isdigit()])

def get_clan_csv():
    url = "https://services.runescape.com/m=clan-hiscores/members_lite.ws?clanName=the%20misfit%20marauders"
    r = requests.get(url)
    with open('members_lite-OG.txt', 'wb') as f:
        f.write(r.content)
    with codecs.open('members_lite-OG.txt', 'r', 'ISO-8859-1') as source, \
         codecs.open('members_lite.txt', 'w', 'utf-8') as target:
        while chunk := source.read(1048576):
            target.write(chunk)

def get_clan_members():
    with open('members_lite.txt', 'r', encoding='utf-8') as f:
        return [line.split(',')[0].lower() for line in f.readlines()[1:]]

def get_total_xp():
    with open('members_lite.txt', 'r', encoding='utf-8') as f:
        return [int(line.split(',')[2]) for line in f.readlines()[1:] if len(line.split(',')) > 2]

def update_clan_stats():
    get_clan_csv()
    for name in get_clan_members():
        try:
            rsn = name.replace('\xa0', '%20').replace(' ', '%20')
            commit_skills(rsn)
        except: pass

def update_leaderboard():
    dt = get_dt()
    get_clan_csv()
    usernames = get_clan_members()
    totals = get_total_xp()
    fdb.child('leaderboard').child(dt).set(dict(zip(usernames, totals)))
    return usernames
    print(f"✅ Leaderboard updated at {dt} with {len(usernames)} members")


def create_player_df(rawRSN, update):
    rsn = rawRSN.replace(' ', '%20')
    if update:
        commit_skills(rsn)
    data = db.reference(f"stats/{rawRSN}").get()
    print(f"📥 Retrieved {len(data)} snapshots for {rawRSN}")
    df = pd.DataFrame.from_dict(data).T.sort_index()
    for col in df:
        if 'XP' in col:
            df[f"{col.split(' ')[0]} Gain"] = df[col].diff()
    return df.T.sort_index(axis=1)


# --- Scheduler ---
scheduler = BackgroundScheduler()

@scheduler.scheduled_job('cron', minute=2)
def scheduled_stat_update():
    print("⏱️ Scheduled: Updating clan stats at minute 2")
    update_clan_stats()

@scheduler.scheduled_job('cron', day_of_week='sat', hour=0, minute=5)
def scheduled_leaderboard_reset():
    print("⏱️ Scheduled: Resetting leaderboard on Saturday")
    db.reference("leaderboard").delete()
    update_leaderboard()

scheduler.start()


# --- Routes ---
@app.route('/')
def home():
    return render_template("index.html")

@app.route('/search', methods=['POST', 'GET'])
def my_form_post():
    if request.method == "POST":
        name = request.form.get('nm')
        if not name.isalnum():
            return render_template("notexist.html")
        append = 'yes' if request.form.get('Get latest') else 'no'
        return redirect(f'/skillhistory/{name}_append={append}')
    return render_template("search.html")

@app.route('/skillhistory/<options>')
def skillhistory(options):
    try:
        name, append = options.split('_')
        update = append == 'append=yes'
        df = create_player_df(name.lower(), update)
        xpDict = {col: df.T[col].astype('int') for col in df.T if 'XP' in col}
        xpMap = pd.DataFrame(xpDict).sort_index()

        fig, axs = plt.subplots(nrows=min(29, len(xpMap.columns)), ncols=1, figsize=(20, 80))
        xpMap.plot(subplots=True, ax=axs)
        plt.tight_layout(pad=4)

        buf = BytesIO()
        fig.savefig(buf, format="png")
        data = base64.b64encode(buf.getbuffer()).decode("ascii")

        for col in df.columns:
            df.loc[:, col] = df[col].map('{:,.0f}'.format)

        return render_template("table.html",
                               name=name,
                               tables=[df.T.to_html(classes='data')],
                               titles=df.columns.values,
                               graphs=data)
    except:
        return render_template("notexist.html")

@app.route('/leaderboards')
def clan_leaderboard_default():
    return redirect('/leaderboards-isRaw=no')

@app.route('/leaderboards-isRaw=<isRaw>')
def clan_leaderboard(isRaw):
    leaderboard = db.reference("leaderboard").get()
    if not leaderboard:
        return render_template("notexist.html")

    timestamps = sorted(leaderboard.keys())
    if len(timestamps) < 2:
        return "Not enough snapshots to compare leaderboard gains."

    first = timestamps[0]
    last = timestamps[-1]
    first_data = leaderboard[first]
    last_data = leaderboard[last]

    usernames = list(last_data.keys())
    df = pd.DataFrame([first_data, last_data], index=[first, last], columns=usernames).T
    df['Gains'] = df[last] - df[first]
    df = df.sort_values(by='Gains', ascending=False)

    if isRaw == "no":
        df_fmt = df.copy()
        for col in df_fmt.columns:
            df_fmt[col] = df_fmt[col].map('{:,.0f}'.format)

        styled_table = df_fmt.to_html(
            classes='table is-striped is-hoverable is-fullwidth has-text-centered',
            border=0
        )

        return render_template("table.html",
                               name=f"Misfits (From {first} to {last})",
                               tables=[styled_table],
                               titles=df_fmt.columns.values)
    else:
        return f'<p>{df["Gains"].to_dict()}</p>'


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=42069, debug=True)
