from flask import Blueprint, render_template


main = Blueprint("main", __name__)


@main.route("/")
def home():
    return render_template("home.html", active_page="home")


@main.route("/mission")
def mission():
    return render_template("mission.html", active_page="mission")


@main.route("/team")
def team():
    return render_template("team.html", active_page="team")


@main.route("/tournaments")
def tournaments():
    return render_template("tournaments.html", active_page="tournaments")


@main.route("/tournaments/inaugural/register")
def inaugural_register():
    return render_template("register.html", active_page="tournaments")
