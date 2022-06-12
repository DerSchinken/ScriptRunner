from exceptions import ProcessError, RunnerError
from _thread import start_new_thread
from collections import OrderedDict
from flask import Flask
import time as timem
import pkg_resources
import subprocess
import sqlite3
import psutil
import sys
import os

DEFAULT = "default"


def install(*packages):
    reqs_version_specified = {d.project_name + "==" + d.version for d in pkg_resources.working_set}
    reqs_version_not_specified = {d.project_name for d in pkg_resources.working_set}

    reqs_not_satisfied = []

    for package in packages:
        if package not in reqs_version_specified or package not in reqs_version_not_specified:
            reqs_not_satisfied.append(package)

    for req in reqs_not_satisfied:
        subprocess.call([sys.executable, "-m", "pip", "install", req])


class Runner:
    def __init__(self, file: str, packages: list, app: Flask, *args):
        self.file = file
        self.packages = packages
        self.app = app
        self.args = args

        self.time = 0
        self.ram_usage = [0.0]
        self.cpu_usage = [0.0]

        self.process = None

        install(*self.packages)

    def run(self):
        # print(self.file.split("/" if "/" in self.file else "\\")[-2])

        # print(os.path.join(self.app.config["UPLOAD_FOLDER"], self.file.split("/" if "/" in self.file else "\\")[-2]))

        self.process = subprocess.Popen(
            [
                sys.executable,
                *self.args,
                self.file,
            ],
            # cwd=os.path.join(
            #     self.app.config['UPLOAD_FOLDER'],
            #     self.file.split("/" if "/" in self.file else "\\")[-1]
            # ),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        start_new_thread(self.__count_resources, ())

    def stop(self):
        if not self.process or isinstance(self.process.poll(), int):
            raise ProcessError("Process was not started!")
        self.process.kill()

    def get_output(self):
        if not self.process or not self.process.poll():
            raise ProcessError("Process was not started!")

        stdout, stderr = self.process.communicate()
        return stdout.decode(), stderr.decode()

    def status(self):
        # print(self.process, self.process.poll())
        if self.process is None:
            return False
        if isinstance(self.process.poll(), int):
            return False
        return True

    def __count_resources(self):
        while not isinstance(self.process.poll(), int):
            if len(self.ram_usage) > 100:
                self.ram_usage.pop(0)
            if len(self.cpu_usage) > 100:
                self.cpu_usage.pop(0)

            self.time += 10
            # self.ram_usage.append(round(16 * psutil.Process(self.process.pid).memory_percent() / 100 * 1024, 2))
            # ^ psutil is a pos. It always gives wrong numbers. Example: on my pi zero with 500mb total ram
            # it says that one process uses over 700mb of ram
            if os.name == "nt":
                get_ram_usage = subprocess.Popen(
                    ["wmic", "process", "where", f"processid={self.process.pid}", "get", "WorkingSetSize"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                self.ram_usage.append(
                    round(int(list(
                        filter(
                            lambda a: a != "",
                            get_ram_usage.communicate()[0].decode().replace(" ", "").replace("\r", "").split("\n")
                        )
                    )[-1]) / 1024 / 1024, 2)
                )
            else:
                get_ram_usage = subprocess.Popen(
                    [f"pmap {str(self.process.pid)} | grep total | awk '/[0-9]K/" + "{print $2}'"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=True
                )
                self.app.logger.info(get_ram_usage.communicate())
                # print(get_ram_usage.communicate()[0].decode())
                self.ram_usage.append(
                    round(int(get_ram_usage.communicate()[0].decode().replace("K", "")) / 1024, 2)
                )
            # Luckily this works v
            self.cpu_usage.append(psutil.Process(self.process.pid).cpu_percent(interval=1))
            timem.sleep(10)
            # > v
            # ^ <


class RunnerManager:
    def __init__(self, app: Flask, db_name: str = DEFAULT):
        self.app = app
        self.runners = OrderedDict()

        if db_name == DEFAULT:
            db_name = "db.sqlite"

        self.con = sqlite3.connect(db_name)

    def add_runner(self, name: str, script_file: str, requirements_file: str or None, auto_start: bool = True):
        if requirements_file:
            with open(requirements_file, "r") as f:
                packages = f.read().split("\n")
        else:
            packages = []

        self.runners[name] = Runner(
            script_file, packages, self.app
        )

        if auto_start:
            self.run(name)

    def remove_runner(self, name: str):
        if self.get_runner_status(name):
            self.runners[name].process.kill()

        os.remove(self.runners[name].file)
        os.rmdir(os.path.dirname(self.runners[name].file))
        del self.runners[name]

    def stop_runner(self, name: str):
        self.get_runner(name).stop()

    def get_runner_status(self, name: str):
        return self.get_runner(name).status()

    def get_runner(self, name: str):
        if name not in self.get_runners():
            raise RunnerError(f"Runner {name} does not exist!")
        return self.runners[name]

    def get_runners(self):
        return self.runners

    def restart_runner(self, name: str):
        if self.get_runner_status(name):
            self.stop_runner(name)
        self.run(name)

    def run(self, name: str):
        start_new_thread(self.get_runner(name).run, ())
