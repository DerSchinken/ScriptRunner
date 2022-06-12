from flask import request, redirect, url_for, render_template, Flask
from flask_limiter.util import get_remote_address
from werkzeug.utils import secure_filename
from _thread import start_new_thread
from flask_httpauth import HTTPBasicAuth
from script_runner import RunnerManager
from matplotlib import pyplot as plt
from flask_limiter import Limiter
import logging
import sqlite3
import time
import ast
import os


app = Flask(__name__)
auth = HTTPBasicAuth()
limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["3 per second"]
)
runner_manager = RunnerManager(app)
con = sqlite3.connect("db.sqlite")
cur = con.cursor()
configs = cur.execute("SELECT * FROM app_configs").fetchall()[0]

host = configs[0]
port = configs[1]
debug = configs[2]

app.config["UPLOAD_FOLDER"] = configs[3]
app.secret_key = configs[4]
logging.basicConfig(filename=f"logs/log.txt", level=logging.DEBUG)
allowed_extensions = {"py", "txt"}

users = ast.literal_eval(configs[5])

if not os.path.exists(app.config["UPLOAD_FOLDER"]):
    os.makedirs(app.config["UPLOAD_FOLDER"])


def allowed_file(filename):
    # print(filename.split('.')[-1].lower() in allowed_extensions)
    return '.' in filename and filename.split('.')[-1].lower() in allowed_extensions


def clear_runner_graphs(after: int = 900):
    while True:
        for file in os.listdir("static/img/cpu"):
            os.remove(f"static/img/cpu/{file}")
        for file in os.listdir("static/img/ram"):
            os.remove(f"static/img/ram/{file}")

        time.sleep(after)


start_new_thread(clear_runner_graphs, ())


@auth.verify_password
def verify_password(username, password):
    if username in users:
        return users[username] == password
    return False


@app.route('/')
@auth.login_required
def index():
    return render_template("index.html")


@app.route("/dashboard")
@auth.login_required
@limiter.limit("3 per second")
def dashboard():
    runners = runner_manager.get_runners().keys()
    list_of_runners = {}
    for runner in runners:
        list_of_runners[runner] = "on" if runner_manager.get_runner_status(runner) else 'off'
        # f"{runner} {'on' if runner_manager.get_runner_status(runner) else 'off'}</ br>"
    return render_template(
        "dashboard.html",
        runners=list_of_runners
    )


@app.route("/dashboard/<runner>")
@auth.login_required
@limiter.limit("20 per minute")
def dashboard_runner(runner):
    if runner not in runner_manager.get_runners():
        return "Runner not found!", 404

    t = runner_manager.get_runner(runner).time
    hours = t // 60 // 60
    minutes = t // 60 % 60
    seconds = t % 60

    if not minutes > 0 and not hours > 0:
        run_time = f"{seconds}s"
    elif not hours > 0 and minutes > 0:
        run_time = f"{minutes}m {seconds}s"
    else:
        run_time = f"{hours}h {minutes}m {seconds}s"

    # Create graphs
    ram_usage = runner_manager.get_runner(runner).ram_usage
    cpu_usage = runner_manager.get_runner(runner).cpu_usage
    ram_usage_fig, ax_ram = plt.subplots()
    cpu_usage_fig, ax_cpu = plt.subplots()
    ax_ram.set_ylabel("Memory Usage (in MB)")
    ax_cpu.set_ylabel("CPU Usage (in %)")
    ram_usage_fig.patch.set_alpha(0)
    cpu_usage_fig.patch.set_alpha(0)
    ax_ram.set_title("RAM Usage")
    ax_cpu.set_title("CPU Usage")

    ax_ram.plot(ram_usage)
    ax_cpu.plot(cpu_usage)

    ram_usage_fig.savefig(f"static/img/ram/{runner}_ram.svg")
    cpu_usage_fig.savefig(f"static/img/cpu/{runner}_cpu.svg")

    plt.close("all")

    return render_template(
        "runner_info.html",
        name=runner,
        time=run_time,
        stopped="" if runner_manager.get_runner_status(runner) else "This runner has stopped!",
        ram_usage=url_for("static", filename=f"img/ram/{runner}_ram.svg"),
        cpu_usage=url_for("static", filename=f"img/cpu/{runner}_cpu.svg"),
    )


@app.route("/dashboard/<runner>/<command>")
@auth.login_required
@limiter.limit("20 per minute")
def dashboard_runner_command(runner, command):
    if runner not in runner_manager.get_runners():
        return "Runner not found!", 404

    if command == "start":
        if not runner_manager.get_runner_status(runner):
            runner_manager.run(runner)
            return "Runner started!", 200
        return "Runner already running!", 400
    elif command == "stop":
        # print(runner_manager.get_runner_status(runner))
        if runner_manager.get_runner_status(runner):
            runner_manager.stop_runner(runner)
            return "Runner stopped!", 200
        return "Runner already stopped!", 400
    elif command == "restart":
        runner_manager.restart_runner(runner)
        return "Runner restarted!", 200
    elif command == "delete":
        runner_manager.remove_runner(runner)
        return "Runner deleted!", 200

    return "Wrong command!", 400


@app.route("/upload", methods=["GET", "POST"])
@auth.login_required
@limiter.limit("3 per second")
def upload():
    if request.method == "POST":
        name = request.form["name"]
        script = request.files["script"]
        requirements = request.files["requirements"]

        if not name:
            return render_template("upload.html", ERROR_NAME="Name is required!")
        if not script:
            return render_template("upload.html", ERROR_SCRIPT="Script is required!")
        if not allowed_file(script.filename):
            return render_template("upload.html", ERROR_SCRIPT="File extension not allowed!")
        if not allowed_file(requirements.filename) and requirements.filename:
            return render_template("upload.html", ERROR_REQUIREMENTS="File extension not allowed!")

        # Save script
        filename_script = secure_filename(script.filename)
        if os.path.exists(os.path.join(app.config["UPLOAD_FOLDER"], name)):
            return render_template("upload.html", ERROR_NAME="Name already exists!")
        # Create folder
        os.mkdir(os.path.join(app.config["UPLOAD_FOLDER"], name))
        # print(os.path.join(app.config['UPLOAD_FOLDER'], name, filename_script))
        script.save(os.path.join(app.config['UPLOAD_FOLDER'], name, filename_script))

        # Save requirements
        if requirements.filename:
            filename_requirements = secure_filename(requirements.filename)
            requirements.save(os.path.join(app.config['UPLOAD_FOLDER'], name, filename_requirements))
        else:
            filename_requirements = None

        # print(filename_script)

        if filename_requirements:
            runner_manager.add_runner(
                name,
                os.path.join(
                    app.config['UPLOAD_FOLDER'],
                    name,
                    filename_script
                ),
                os.path.join(
                    app.config['UPLOAD_FOLDER'],
                    name,
                    filename_requirements
                )
            )
        else:
            runner_manager.add_runner(
                name,
                os.path.join(
                    app.config['UPLOAD_FOLDER'],
                    name,
                    filename_script
                ), None
            )

        return redirect(url_for("dashboard"))
    return render_template("upload.html")


@app.route("/loading")
@auth.login_required
def loading():
    return render_template("loading.html", LOADING_TEXT=f"Loading nothing!")


if __name__ == '__main__':
    app.run(debug=debug, host=host, port=port)
