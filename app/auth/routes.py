from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models import User, Expense
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError
from sqlalchemy import func


auth_bp = Blueprint("auth", __name__)


# ── Forms ────────────────────────────────────────────────────────────────────

class RegistrationForm(FlaskForm):
    username = StringField("Username",
                           validators=[DataRequired(), Length(min=3, max=80)])
    email = StringField("Email",
                        validators=[DataRequired(), Email()])
    password = PasswordField("Password",
                             validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField("Confirm Password",
                                     validators=[DataRequired(), EqualTo("password")])
    submit = SubmitField("Create Account")

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError("Username already taken. Please choose another.")

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError("Email already registered. Please log in.")


class LoginForm(FlaskForm):
    email = StringField("Email",
                        validators=[DataRequired(), Email()])
    password = PasswordField("Password",
                             validators=[DataRequired()])
    remember = BooleanField("Remember Me")
    submit = SubmitField("Login")


# ── Routes ───────────────────────────────────────────────────────────────────

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("expenses.dashboard"))
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash("Account created! Please log in.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/register.html", form=form)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("expenses.dashboard"))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get("next")
            flash(f"Welcome back, {user.username}!", "success")
            return redirect(next_page or url_for("expenses.dashboard"))
        flash("Invalid email or password.", "danger")
    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))

# ── Profile Forms ─────────────────────────────────────────────────────────────

class EditProfileForm(FlaskForm):
    username = StringField("Username",
                           validators=[DataRequired(), Length(min=3, max=80)])
    email = StringField("Email",
                        validators=[DataRequired(), Email()])
    submit = SubmitField("Save Changes")

    def validate_username(self, username):
        if username.data != current_user.username:
            user = User.query.filter_by(username=username.data).first()
            if user:
                raise ValidationError("Username already taken.")

    def validate_email(self, email):
        if email.data != current_user.email:
            user = User.query.filter_by(email=email.data).first()
            if user:
                raise ValidationError("Email already registered.")


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField("Current Password",
                                     validators=[DataRequired()])
    new_password = PasswordField("New Password",
                                 validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField("Confirm New Password",
                                     validators=[DataRequired(),
                                                 EqualTo("new_password")])
    submit = SubmitField("Update Password")


# ── Profile Routes ────────────────────────────────────────────────────────────

@auth_bp.route("/profile")
@login_required
def profile():
    edit_form = EditProfileForm(obj=current_user)
    password_form = ChangePasswordForm()

    # Stats
    from datetime import date
    total_expenses = Expense.query.filter_by(user_id=current_user.id).count()
    total_spent = db.session.query(func.sum(Expense.amount))\
                            .filter_by(user_id=current_user.id).scalar() or 0
    top_category = db.session.query(
        Expense.category, func.sum(Expense.amount).label("total")
    ).filter_by(user_id=current_user.id)\
     .group_by(Expense.category)\
     .order_by(func.sum(Expense.amount).desc()).first()

    return render_template("auth/profile.html",
                           edit_form=edit_form,
                           password_form=password_form,
                           total_expenses=total_expenses,
                           total_spent=total_spent,
                           top_category=top_category.category if top_category else "—",
                           member_since=current_user.created_at.strftime("%B %Y"))


@auth_bp.route("/profile/edit", methods=["POST"])
@login_required
def edit_profile():
    form = EditProfileForm()
    if form.validate_on_submit():
        current_user.username = form.username.data
        current_user.email = form.email.data
        db.session.commit()
        flash("Profile updated successfully!", "success")
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{error}", "danger")
    return redirect(url_for("auth.profile"))


@auth_bp.route("/profile/password", methods=["POST"])
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if current_user.check_password(form.current_password.data):
            current_user.set_password(form.new_password.data)
            db.session.commit()
            flash("Password changed successfully!", "success")
        else:
            flash("Current password is incorrect.", "danger")
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{error}", "danger")
    return redirect(url_for("auth.profile"))


@auth_bp.route("/profile/delete", methods=["POST"])
@login_required
def delete_account():
    user = current_user
    logout_user()
    db.session.delete(user)
    db.session.commit()
    flash("Your account has been deleted.", "info")
    return redirect(url_for("auth.register"))