from app import app


@app.shell_context_processor
def sh_context():
    return


if __name__ == "__main__":
    app.run()
