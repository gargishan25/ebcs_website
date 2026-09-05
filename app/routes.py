from flask import Blueprint, render_template


main = Blueprint("main", __name__)


@main.route("/")
def home():
    return render_template("home.html", active_page="home")


@main.route("/team/")
def team():
    return render_template("team.html", active_page="team")


@main.route("/events/")
def tournaments():
    return render_template("tournaments.html", active_page="tournaments")


@main.route("/2026r&b/")
def event_details():
    return render_template("event_details.html", active_page="tournaments")