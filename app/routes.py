from app import app


@app.route("/")
@app.route("/index")
def setup():
    return "hey"
