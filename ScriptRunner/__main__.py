from app import app
import argparse


args = argparse.ArgumentParser(
    prog="ScriptRunner",
    description='Run The ScriptRunner.'
)

args.add_argument("--host", default="0.0.0.0")
args.add_argument("--port", default=2122)

args = args.parse_args()

if __name__ == '__main__':
    # maybe use wsgi
    app.run(debug=False, host=args.host, port=args.port)
