import base64
from io import BytesIO
from flask import Flask, render_template, request, redirect
import requests
import json
import runescapeapi
from urllib.request import urlopen
from bs4 import BeautifulSoup
import datetime
import pytz as pytz
import codecs
import pyrebase
from apscheduler.schedulers.background import BackgroundScheduler
import firebase_admin
from firebase_admin import credentials
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.ticker import FormatStrFormatter
from matplotlib import rcParams

rcParams["axes.grid"] = True
# change ranl to gains then put gains in rank stats spot

plt.style.use('dark_background')
rcParams["axes.formatter.limits"] = [0, 1000000000000]
cred = credentials.Certificate(
    "wheatcrushinglegacy-firebase-adminsdk-s2vey-cfcbe88dbe.json")
firebase_admin.initialize_app(cred, {
    'databaseURL':
    'https://wheatcrushinglegacy-default-rtdb.firebaseio.com/'
})

config = {
    "apiKey": "AIzaSyAhDA9Wx67X1gSuM6Y8Z8w2Y5Y2u-rbLAY",
    "authDomain": "wheatcrushinglegacy.firebaseapp.com",
    "databaseURL": "https://wheatcrushinglegacy-default-rtdb.firebaseio.com",
    "projectId": "wheatcrushinglegacy",
    "storageBucket": "wheatcrushinglegacy.appspot.com",
    "messagingSenderId": "482550136777",
    "appId": "1:482550136777:web:0c54b67226a8ddb42db218",
    "measurementId": "G-MVJJLFV5BV",
    "serviceAccount":
    "wheatcrushinglegacy-firebase-adminsdk-s2vey-cfcbe88dbe.json"
}
firebase = pyrebase.initialize_app(config)
fdb = firebase.database()
print(fdb.generate_key())


def get_dt():

    cst = pytz.timezone('America/Chicago')
    now = datetime.datetime.now(cst)
    dt = datetime.datetime.strftime(now, '%Y-%m-%d-%H-%M')
    return dt


def get_stat_ref():

    my_file = open("stat_ref.txt", "r")

    # reading the file
    data = my_file.read()

    # replacing end splitting the text
    # when newline ('\n') is seen.
    keyList = data.split("\n")
    my_file.close()
    return keyList


def strip_to_text(url):

    url2 = url.replace('�', '%20')

    html = urlopen(url2).read()
    soup = BeautifulSoup(html, features="html.parser")

    # kill all script and style elements
    for script in soup(["script", "style"]):
        script.extract()  # rip it out

    # get text
    text = soup.get_text()

    # break into lines and remove leading and trailing space on each
    lines = (line.strip() for line in text.splitlines())
    # break multi-headlines into a line each
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    # drop blank lines
    text = '\n'.join(chunk for chunk in chunks if chunk)

    return text


def assign_all(raw, key, rsn):

    formed = raw.replace(',', '\n')
    rawList = formed.splitlines()  #1st level list
    n = len(rawList)

    for i in range(0, n - 87):
        rawList.pop()

    intList = [int(i) for i in rawList]
    formedDict = dict(zip(key, intList))
    # for k, v in list(formedDict.items()):
    #     if k.split('-')[1] == 'Gain':
    #         new_key = f"{k}                        "
    #         formedDict[new_key] = formedDict.pop(k)

    dt = get_dt()
    fdb.child('stats').child(rsn).child(dt).set(formedDict)


def commit_skills(rsn):
    statsURL = f'https://secure.runescape.com/m=hiscore/index_lite.ws?player={rsn}'
    raw = strip_to_text(statsURL)
    key = get_stat_ref()
    assign_all(raw, key, rsn)


def list_to_int(test_list):

    # using loop

    for i in range(0, len(test_list)):
        try:
            test_list[i] = int(test_list[i])
        except:
            pass
    test_list.sort()
    return test_list


def get_clan_csv(clan):

    url = "https://services.runescape.com/m=clan-hiscores/members_lite.ws?clanName=the%20misfit%20marauders"
    response = requests.get(url)
    sourceFileName = 'members_lite-OG.txt'
    targetFileName = 'members_lite.txt'
    open(sourceFileName, 'wb').write(response.content)
    BLOCKSIZE = 1048576
    with codecs.open(sourceFileName, "r", "ISO-8859-1") as sourceFile:
        with codecs.open(targetFileName, "w", "utf-8") as targetFile:
            while True:
                contents = sourceFile.read(BLOCKSIZE)
                if not contents:
                    break
                targetFile.write(contents)
    print(get_dt() + "clan file retrieved")


def get_clan_members():
    f = open('members_lite.txt', 'r', encoding='utf-8')

    lines = f.readlines()[1:]

    f.close()
    usernames = []
    for l in range(len(lines)):

        #SPLIT TO LIST
        l = lines[l].split(',')
        usernames.append(l[0].lower())
        #TAKE FIRST INDEX AND ADD TO LIST
    return usernames


def get_total_xp():
    f = open('members_lite.txt', 'r', encoding='utf-8')

    lines = f.readlines()[1:]

    f.close()
    totalXP = []
    for l in range(len(lines)):

        #SPLIT TO LIST
        l = lines[l].split(',')
        totalXP.append(int(l[2]))
        #TAKE FIRST INDEX AND ADD TO LIST
    return totalXP


def update_clan_stats():
    get_clan_csv('')
    usernames = get_clan_members()
    for i in range(len(usernames)):
        try:
            rawRSN = usernames[i].replace('\xa0', '%20')
            rsn = rawRSN.replace(' ', '%20')
            commit_skills(rsn)
        except:
            pass
    print(get_dt() + "clan stats updated")


def update_leaderboard():
    dt = get_dt()
    get_clan_csv('')
    usernamesList = get_clan_members()
    totalsList = get_total_xp()
    leaderboardDict = dict(zip(usernamesList, totalsList))
    print(dt + ' uploading data')
    fdb.child('leaderboard').child(dt).set(leaderboardDict)
    print(dt + ' upload complete')
    return usernamesList


def create_player_df(rawRSN, update):
    dt = get_dt()
    rsn = rawRSN.replace(' ', '%20')
    if update:
        commit_skills(rsn)

    userDict = dict(fdb.child(f"stats/{rawRSN}").get().val())
    df2 = pd.DataFrame.from_dict(userDict)

    print('dict assigned')
    df2 = df2.transpose()

    df2.sort_index(axis=0)

    print('assigning gains')
    for (columnName, columnData) in df2.items():

        gainName = columnName.split(' ')[0] + ' Gain'
        # Calculating the difference between two rows
        if columnName.split(' ')[1] == 'XP':

            df2[gainName] = df2[columnName].diff()

    print('sorting')
    df2 = df2.transpose()
    df2 = df2.sort_index(axis=1, ascending=False)
    print(rawRSN)
    return df2
#


#---------uncomment to repopulate  data--------------#
# fdb.child('stats').remove()
# update_leaderboard()
# get_clan_csv("the%20misfit%20marauders")
# update_clan_stats()
# fdb.child('leaderboard').remove()

#--------------start of flask--------------#

app = Flask(__name__)


@app.route('/')
def home():

    return render_template("index.html")


@app.route('/search', methods=['POST', 'GET'])
def my_form_post():

    if request.method == "POST":
        name = request.form.get('nm')
        is_checked = request.form.get('Get latest')
        if is_checked: append = 'yes'
        else: append = 'no'
        directory = f'{name}_append={append}'
        return redirect(f'/skillhistory/{directory}')
    else:
        return render_template("search.html")


@app.route('/skillhistory/<options>')
def skillhistory(options):
    try:
        options = options.split('_')
        name = options[0]
        append = options[1]
        if append == 'append=yes': update = True
        else: update = False

        rawRSN = name.lower()
        df = create_player_df(rawRSN, update)

        df2 = df.transpose().sort_index(1)
        xpDict = {}
        print('preparing new table')
        datapoints = 20
        count = 0
        
        for (columnName, columnData) in df2.items():

            gainName = columnName.split(' ')[0] + ' Gain'
            # Calculating the difference between two rows
            if columnName.split(' ')[1] == 'XP':

                xpDict[columnName] = df2[columnName].astype('int')

        print(df)
        xpMap = pd.DataFrame.from_dict(xpDict)
        
        # xpMap = xpMap.astype(str)
        print('plotting')
        
        xpMap = xpMap.sort_index(axis=0)
        print(xpMap)
        try:
            fig = Figure()
            height = 80
            width = 20
            fig, axs = plt.subplots(nrows=29,
                                    ncols=1,
                                    figsize=(width, height),
                                    linewidth=5)
            xpMap.plot(subplots=True, ax=axs)
            # xpMap.plot()
            plt.tight_layout(pad=4)

        except:
            print('failed')
        print('plot')
        buf = BytesIO()
        fig.savefig(buf, format="png")
        data = base64.b64encode(buf.getbuffer()).decode("ascii")
        for (columnName, columnData) in df2.items():
                df2.loc[:, columnName] = df2[columnName].map('{:,.0f}'.format)
                
                
        df2 = df2.astype(str).transpose()
        print('ready to render')

        return render_template("table.html",
                               name=name,
                               tables=[df2.to_html(classes='data')],
                               titles=df2.columns.values,
                               graphs=data)
    except:
        return render_template("notexist.html")


@app.route('/leaderboards-isRaw=<isRaw>')
def clan_leaderboard(isRaw):
    dt = get_dt()
    name = "misfits"
    usernamesList = update_leaderboard()
    main = []
    historyList = list_to_int(
        list(fdb.child("leaderboard").shallow().get().val()))
    first = 0
    last = len(historyList) - 1
    firstDate = historyList[first]
    lastDate = historyList[last]
    pollingDates = [firstDate, lastDate]
    firstDict = dict(fdb.child(f'leaderboard/{firstDate}').get().val())
    secondDict = dict(fdb.child(f'leaderboard/{lastDate}').get().val())
    main = [firstDict, secondDict]
    df = pd.DataFrame(main, index=pollingDates, columns=usernamesList)

    df = df.transpose()

    df['Gains'] = df[lastDate] - df[firstDate]
    df = df.sort_values(by=['Gains'], ascending=False)
    for (columnName, columnData) in df.items():
                df.loc[:, columnName] = df[columnName].map('{:,.0f}'.format)
                
    df = df.astype(str)
    if isRaw == "no":
        return render_template("table.html",
                               name=name,
                               tables=[df.to_html(classes='data')],
                               titles=df.columns.values)
    else:
        df.style.format("{:.1f}")
        gainDF = df['Gains']
        return f'<p>{gainDF.to_dict()}</p>'


def updater():
    cst = pytz.timezone('America/Chicago')
    now = datetime.datetime.now(cst)
    if now.minute == 2:
        update_clan_stats()
        allRSNs = list(fdb.child("stats").shallow().get().val())

        for i in range(len(allRSNs)):
            rawRSN = allRSNs[i].replace(' ', '%20')
            statsURL = f'https://secure.runescape.com/m=hiscore/index_lite.ws?player={rawRSN}'
            raw = strip_to_text(statsURL)
            key = get_stat_ref()
            assign_all(raw, key, rawRSN)
    if now.weekday == 5:
        fdb.child('leaderboard').remove()
        update_leaderboard()


def main():
    pass


# entry point when running this code as a script
if __name__ == "__main__":
    main()

with app.app_context():
    scheduler = BackgroundScheduler()
    scheduler.add_job(updater, 'interval', minutes=1)
    scheduler.start()

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=81)
