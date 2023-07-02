import subprocess
import sys
from venv import EnvBuilder
import os


class EnvWithPackages(EnvBuilder):
    def __init__(self, *args, **kwargs):
        self.venv_dir = kwargs.pop('venv_dir', None)
        self.packages = kwargs.pop('packages', [])

        # Always include pip since it's needed to insall packages
        kwargs["with_pip"] = True
        super().__init__(*args, **kwargs)
        self.create(self.venv_dir)


    def post_setup(self, context):
        super().post_setup(context)
        
        # Activate the virtual environment and install packages
        # TODO: test (for linux espacially)
        activate_script = self.venv_dir + ('/Scripts/activate.bat' if sys.platform == 'win32' else '/bin/activate')
        activate_cmd = f"{activate_script} && pip install {' '.join(self.packages)}"
        os.system(activate_cmd)


vdir = "/workspaces/ScriptRunner/testing-venv"

EnvWithPackages(venv_dir=vdir, packages=["BetterString", "PasswordCardGenerator", "CardGameBase"])
