from flask_wtf import FlaskForm
from wtforms import (BooleanField, DateField, IntegerField, PasswordField, RadioField, SelectField,
                     SelectMultipleField, StringField, SubmitField, TextAreaField, TimeField)
from wtforms.validators import (DataRequired, Email, EqualTo, Length, NumberRange, Optional,
                                ValidationError)

from .catalog import (AGE_BANDS, ALL_SLOTS, FOCUS_AREAS, GRADES, HOUR_KINDS, LEVELS,
                      MINOR_BANDS, SKILLS, TRACKS)

SLOT_CHOICES = [(s, s) for s in ALL_SLOTS]


def _rating(label):
    return IntegerField(label, validators=[Optional(), NumberRange(min=100, max=3200)])


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember = BooleanField("Keep me signed in on this device")
    submit = SubmitField("Sign in")


class LearnerSignupForm(FlaskForm):
    name = StringField("Full name", validators=[DataRequired(), Length(max=120)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=160)])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8, message="At least 8 characters.")])
    confirm = PasswordField("Confirm password", validators=[DataRequired(), EqualTo("password", "Passwords must match.")])

    age_band = RadioField("Age", choices=AGE_BANDS, validators=[DataRequired()])
    level = RadioField("Where are you right now?", choices=LEVELS, validators=[DataRequired()])
    rating = _rating("Rating, if you have one")
    goals = SelectMultipleField("What do you want to work on?", choices=FOCUS_AREAS)
    goal_text = TextAreaField("Anything else your coach should know?", validators=[Optional(), Length(max=1000)])
    availability = SelectMultipleField("When are you free?", choices=SLOT_CHOICES)

    guardian_name = StringField("Parent / guardian name", validators=[Length(max=120)])
    guardian_email = StringField("Parent / guardian email", validators=[Length(max=160)])
    guardian_phone = StringField("Parent / guardian phone", validators=[Optional(), Length(max=40)])
    guardian_consent = BooleanField("I am the parent or guardian and I consent to this learner joining EBCS coaching.")
    conduct = BooleanField("I agree to the EBCS community guidelines.", validators=[DataRequired("Required.")])
    submit = SubmitField("Create account")

    def validate_availability(self, field):
        if len(field.data or []) < 2:
            raise ValidationError("Mark at least two hours so we can find you a match.")

    def validate(self, extra_validators=None):
        ok = super().validate(extra_validators)
        if self.age_band.data in MINOR_BANDS:
            def need(field, msg):
                field.errors = list(field.errors) + [msg]
                return False
            if not (self.guardian_name.data or "").strip():
                ok = need(self.guardian_name, "Required for learners under 18.")
            email = (self.guardian_email.data or "").strip()
            if not email:
                ok = need(self.guardian_email, "Required for learners under 18.")
            else:
                try:
                    Email()(self, self.guardian_email)
                except ValidationError as e:
                    ok = need(self.guardian_email, str(e) or "Invalid email address.")
            if not self.guardian_consent.data:
                ok = need(self.guardian_consent, "A parent or guardian must consent.")
        return ok


class CoachApplyForm(FlaskForm):
    name = StringField("Full name", validators=[DataRequired(), Length(max=120)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=160)])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8, message="At least 8 characters.")])
    confirm = PasswordField("Confirm password", validators=[DataRequired(), EqualTo("password", "Passwords must match.")])

    school = StringField("High school", validators=[DataRequired(), Length(max=160)])
    grade = RadioField("Grade", choices=GRADES, validators=[DataRequired()])
    phone = StringField("Phone", validators=[Optional(), Length(max=40)])

    uscf_id = StringField("USCF ID", validators=[Optional(), Length(max=20)])
    uscf_rating = _rating("USCF rating")
    online_platform = SelectField("Online platform", choices=[("", "-"), ("lichess", "Lichess"), ("chess.com", "Chess.com")],
                                  validators=[Optional()])
    online_username = StringField("Username", validators=[Optional(), Length(max=60)])
    online_rating = _rating("Rapid rating")

    experience = TextAreaField("Your chess background", validators=[DataRequired(), Length(max=2000)])
    why = TextAreaField("Why do you want to coach?", validators=[DataRequired(), Length(max=2000)])
    bio = TextAreaField("Short bio learners will see", validators=[Optional(), Length(max=600)])
    specialties = SelectMultipleField("What can you teach well?", choices=FOCUS_AREAS,
                                      validators=[DataRequired("Pick at least one.")])
    availability = SelectMultipleField("Weekly availability", choices=SLOT_CHOICES)
    max_learners = SelectField("Learners you can take", choices=[("1", "1"), ("2", "2"), ("3", "3"), ("4", "4")],
                               default="2")
    conduct = BooleanField("I agree to the EBCS coach code of conduct.", validators=[DataRequired("Required.")])
    submit = SubmitField("Submit application")

    def validate(self, extra_validators=None):
        ok = super().validate(extra_validators)
        if not self.uscf_rating.data and not self.online_rating.data:
            self.uscf_rating.errors = list(self.uscf_rating.errors) + [
                "Give a USCF rating or an online rating so we can verify strength."]
            ok = False
        return ok

    def validate_availability(self, field):
        if len(field.data or []) < 2:
            raise ValidationError("Mark at least two hours.")


class AvailabilityForm(FlaskForm):
    availability = SelectMultipleField("Availability", choices=SLOT_CHOICES)
    submit = SubmitField("Save")


DURATIONS = [("30", "30 min"), ("45", "45 min"), ("60", "60 min"), ("75", "75 min"), ("90", "90 min")]


class SessionForm(FlaskForm):
    pairing = SelectField("Learner", coerce=int)
    date = DateField("Date", validators=[DataRequired()])
    time = TimeField("Start", validators=[DataRequired()])
    duration = SelectField("Length", choices=DURATIONS, default="60")
    location = StringField("Meeting link", validators=[Optional(), Length(max=240)])
    agenda = TextAreaField("Plan for the session", validators=[Optional(), Length(max=1000)])
    repeat = SelectField("Repeat", choices=[("0", "Just once"), ("4", "Weekly x4"), ("8", "Weekly x8")], default="0")
    submit = SubmitField("Schedule")


class ReportForm(FlaskForm):
    outcome = RadioField("What happened?", choices=[("completed", "Session happened"),
                                                    ("no_show", "Learner didn't show"),
                                                    ("cancelled", "Cancelled")], default="completed")
    minutes = IntegerField("Actual length (minutes)", validators=[Optional(), NumberRange(min=5, max=240)])
    topics = SelectMultipleField("Covered", choices=SKILLS)
    summary = TextAreaField("What you worked on", validators=[Optional(), Length(max=3000)])
    homework = TextAreaField("Homework", validators=[Optional(), Length(max=1000)])
    submit = SubmitField("File report")


class FeedbackForm(FlaskForm):
    rating = RadioField("How was it?", choices=[(str(i), str(i)) for i in range(1, 6)], validators=[DataRequired()])
    feedback = TextAreaField("Anything to add?", validators=[Optional(), Length(max=1000)])
    submit = SubmitField("Send feedback")


class MessageForm(FlaskForm):
    body = TextAreaField("Message", validators=[DataRequired(), Length(max=4000)])
    submit = SubmitField("Send")


class AssignForm(FlaskForm):
    lesson = SelectField("Lesson", coerce=int)
    due_on = DateField("Due", validators=[Optional()])
    note = StringField("Note", validators=[Optional(), Length(max=300)])
    submit = SubmitField("Assign")


class HourForm(FlaskForm):
    kind = SelectField("Type", choices=[k for k in HOUR_KINDS if k[0] != "session"])
    worked_on = DateField("Date", validators=[DataRequired()])
    minutes = IntegerField("Minutes", validators=[DataRequired(), NumberRange(min=5, max=600)])
    description = StringField("What did you do?", validators=[DataRequired(), Length(max=300)])
    submit = SubmitField("Log time")


class LessonForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=160)])
    track = SelectField("Track", choices=TRACKS)
    level = SelectField("Level", choices=[("1", "1 - Beginner"), ("2", "2 - Developing"),
                                          ("3", "3 - Intermediate"), ("4", "4 - Advanced")], default="1")
    minutes = IntegerField("Minutes", default=15, validators=[Optional(), NumberRange(min=5, max=120)])
    summary = StringField("One-line summary", validators=[Optional(), Length(max=300)])
    body = TextAreaField("Lesson", validators=[Optional()])
    fen = StringField("Position (FEN)", validators=[Optional(), Length(max=100)])
    solution = StringField("Solution / key line", validators=[Optional(), Length(max=200)])
    published = BooleanField("Published", default=True)
    submit = SubmitField("Save lesson")


class CoachReviewForm(FlaskForm):
    status = SelectField("Status", choices=[("applied", "Applied"), ("screening", "Screening"),
                                           ("approved", "Approved"), ("paused", "Paused"),
                                           ("rejected", "Not accepted")])
    max_learners = SelectField("Roster size", choices=[(str(i), str(i)) for i in range(0, 6)])
    admin_notes = TextAreaField("Internal notes", validators=[Optional(), Length(max=4000)])
    submit = SubmitField("Save review")
