from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app import db
from app.models import Expense
from flask_wtf import FlaskForm
from wtforms import FloatField, StringField, SelectField, DateField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Length, NumberRange
from datetime import datetime, date, timedelta
from sqlalchemy import func
import os
import json
from app.models import Expense, Budget

expenses_bp = Blueprint("expenses", __name__)

CATEGORIES = [
    ("Food", "Food"),
    ("Dining", "Dining Out"),
    ("Groceries", "Groceries"),
    ("Transport", "Transport"),
    ("Travel", "Travel"),
    ("Housing", "Housing & Rent"),
    ("Utilities", "Utilities & Bills"),
    ("Health", "Health & Medical"),
    ("Fitness", "Fitness & Sports"),
    ("Education", "Education"),
    ("Shopping", "Shopping"),
    ("Clothing", "Clothing & Fashion"),
    ("Tech", "Tech & Gadgets"),
    ("Entertainment", "Entertainment"),
    ("Gaming", "Gaming"),
    ("Streaming", "Streaming & Subscriptions"),
    ("Books", "Books & Stationery"),
    ("Beauty", "Beauty & Personal Care"),
    ("Pets", "Pets"),
    ("Gifts", "Gifts & Donations"),
    ("Family", "Family & Kids"),
    ("Social", "Social & Events"),
    ("Business", "Business & Work"),
    ("Freelance", "Freelance Expenses"),
    ("Investment", "Investments & Savings"),
    ("Insurance", "Insurance"),
    ("Repairs", "Repairs & Maintenance"),
    ("Fuel", "Fuel & Parking"),
    ("Mobile", "Mobile & Internet"),
    ("Other", "Other"),
]


# ── AI Categorization ─────────────────────────────────────────────────────────

def categorize_with_ai(description):
    try:
        from groq import Groq
        client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{
                "role": "user",
                "content": f"""Categorize this expense into exactly ONE of these categories:
Food, Transport, Housing, Health, Entertainment, Shopping, Other

Expense: "{description}"

Reply with ONLY the category word, nothing else."""
            }],
            max_tokens=10,
            temperature=0
        )
        category = response.choices[0].message.content.strip()
        valid = [c[0] for c in CATEGORIES]
        return category if category in valid else "Other"
    except Exception:
        return "Other"


# ── Forms ─────────────────────────────────────────────────────────────────────

class ExpenseForm(FlaskForm):
    amount = FloatField("Amount (BDT)",
                        validators=[DataRequired(), NumberRange(min=0.01)])
    description = StringField("Description",
                               validators=[DataRequired(), Length(min=2, max=200)])
    category = SelectField("Category", choices=CATEGORIES)
    date = DateField("Date", validators=[DataRequired()], default=date.today)
    notes = TextAreaField("Notes (optional)", validators=[Length(max=500)])
    submit = SubmitField("Save Expense")


# ── Helper ────────────────────────────────────────────────────────────────────

def get_category_badge(category):
    return f"badge-{category.lower()}"


# ── Routes ────────────────────────────────────────────────────────────────────

@expenses_bp.route("/")
@expenses_bp.route("/dashboard")
@login_required
def dashboard():
    # All expenses for current user
    expenses = Expense.query.filter_by(user_id=current_user.id)\
                            .order_by(Expense.date.desc()).all()

    # This month
    today = date.today()
    first_day = today.replace(day=1)
    this_month = Expense.query.filter(
        Expense.user_id == current_user.id,
        Expense.date >= first_day
    ).all()

    total_this_month = sum(e.amount for e in this_month)
    avg_daily = total_this_month / today.day if today.day > 0 else 0
    top_category = "—"
    total_entries = len(expenses)

    # Top category this month
    if this_month:
        cat_totals = {}
        for e in this_month:
            cat_totals[e.category] = cat_totals.get(e.category, 0) + e.amount
        top_category = max(cat_totals, key=cat_totals.get)

    # Last 6 months chart data — fixed
    month_data = []
    for i in range(5, -1, -1):
        month_date = today.replace(day=1)
        for _ in range(i):
            month_date = (month_date - timedelta(days=1)).replace(day=1)
        m_label = month_date.strftime("%b %Y")
        m_total = db.session.query(func.sum(Expense.amount)).filter(
            Expense.user_id == current_user.id,
            func.strftime("%Y-%m", Expense.date) == month_date.strftime("%Y-%m")
        ).scalar() or 0
        month_data.append({"month": m_label, "total": round(m_total, 2)})

    # Category breakdown for doughnut
    cat_data = db.session.query(
        Expense.category,
        func.sum(Expense.amount)
    ).filter_by(user_id=current_user.id).group_by(Expense.category).all()
    cat_data = [{"category": c, "total": round(t, 2)} for c, t in cat_data]

    # Budget warnings
    from app.models import Budget
    all_budgets = Budget.query.filter_by(user_id=current_user.id).all()
    budget_warnings = []
    for b in all_budgets:
        spent = db.session.query(func.sum(Expense.amount)).filter(
            Expense.user_id == current_user.id,
            Expense.category == b.category,
            Expense.date >= first_day
        ).scalar() or 0
        percentage = (spent / b.amount * 100) if b.amount > 0 else 0
        if percentage >= 80:
            budget_warnings.append({
                "category": b.category,
                "spent": spent,
                "budget": b.amount,
                "percentage": round(percentage, 1),
                "over": percentage >= 100
            })

    return render_template("expenses/dashboard.html",
        expenses=expenses[:10],
        total_this_month=total_this_month,
        avg_daily=avg_daily,
        top_category=top_category,
        total_entries=total_entries,
        month_data=json.dumps(month_data),
        cat_data=json.dumps(cat_data),
        get_category_badge=get_category_badge,
        budget_warnings=budget_warnings
    )


@expenses_bp.route("/add", methods=["GET", "POST"])
@login_required
def add_expense():
    form = ExpenseForm()
    if form.validate_on_submit():
        category = form.category.data
        ai_categorized = False

        # AI categorize if user left it as "Other"
        if category == "Other":
            ai_cat = categorize_with_ai(form.description.data)
            if ai_cat != "Other":
                category = ai_cat
                ai_categorized = True

        expense = Expense(
            user_id=current_user.id,
            amount=form.amount.data,
            description=form.description.data,
            category=category,
            date=form.date.data,
            notes=form.notes.data,
            ai_categorized=ai_categorized
        )
        db.session.add(expense)
        db.session.commit()

        if ai_categorized:
            flash(f'✓ "{form.description.data}" added — AI categorized as {category} (৳{form.amount.data:,.2f})', "success")
        else:
            flash(f'✓ "{form.description.data}" added under {category} — ৳{form.amount.data:,.2f}', "success")
        return redirect(url_for("expenses.dashboard"))

    return render_template("expenses/add_expense.html", form=form, title="Add Expense")


@expenses_bp.route("/edit/<int:id>", methods=["GET", "POST"])
@login_required
def edit_expense(id):
    expense = Expense.query.get_or_404(id)
    if expense.user_id != current_user.id:
        flash("Unauthorized.", "danger")
        return redirect(url_for("expenses.dashboard"))

    form = ExpenseForm(obj=expense)
    if form.validate_on_submit():
        expense.amount = form.amount.data
        expense.description = form.description.data
        expense.category = form.category.data
        expense.date = form.date.data
        expense.notes = form.notes.data
        expense.ai_categorized = False
        db.session.commit()
        flash("Expense updated!", "success")
        return redirect(url_for("expenses.dashboard"))

    return render_template("expenses/add_expense.html", form=form,
                           title="Edit Expense", expense=expense)


@expenses_bp.route("/delete/<int:id>", methods=["POST"])
@login_required
def delete_expense(id):
    expense = Expense.query.get_or_404(id)
    if expense.user_id != current_user.id:
        flash("Unauthorized.", "danger")
        return redirect(url_for("expenses.dashboard"))
    db.session.delete(expense)
    db.session.commit()
    flash("Expense deleted.", "info")
    return redirect(url_for("expenses.dashboard"))


@expenses_bp.route("/insights")
@login_required
def insights():
    # Last 30 days expenses as CSV for Groq
    thirty_days_ago = date.today() - timedelta(days=30)
    expenses = Expense.query.filter(
        Expense.user_id == current_user.id,
        Expense.date >= thirty_days_ago
    ).order_by(Expense.date.desc()).all()

    if not expenses:
        flash("Add some expenses first to get AI insights!", "info")
        return redirect(url_for("expenses.dashboard"))

    csv_text = "Date,Description,Category,Amount(BDT)\n"
    for e in expenses:
        csv_text += f"{e.date},{e.description},{e.category},{e.amount}\n"

    insights_text = ""
    try:
        from groq import Groq
        client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{
                "role": "user",
                "content": f"""You are a personal finance advisor. Analyze these expenses from the last 30 days and provide exactly 5 bullet-point insights. Be specific with amounts in BDT. Focus on spending patterns, areas to cut back, and positive habits.

{csv_text}

Format your response as exactly 5 bullet points starting with •"""
            }],
            max_tokens=600,
            temperature=0.7
        )
        insights_text = response.choices[0].message.content.strip()
    except Exception as e:
        insights_text = f"• Error loading insights: {str(e)}"

    total = sum(e.amount for e in expenses)
    return render_template("expenses/insights.html",
                           insights=insights_text,
                           expenses=expenses,
                           total=total)

@expenses_bp.route("/all")
@login_required
def all_expenses():
    page = request.args.get("page", 1, type=int)
    category_filter = request.args.get("category", "")
    search_query = request.args.get("search", "")
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")

    query = Expense.query.filter_by(user_id=current_user.id)

    if category_filter:
        query = query.filter(Expense.category == category_filter)
    if search_query:
        query = query.filter(Expense.description.ilike(f"%{search_query}%"))
    if date_from:
        try:
            query = query.filter(Expense.date >= datetime.strptime(date_from, "%Y-%m-%d").date())
        except ValueError:
            pass
    if date_to:
        try:
            query = query.filter(Expense.date <= datetime.strptime(date_to, "%Y-%m-%d").date())
        except ValueError:
            pass

    expenses = query.order_by(Expense.date.desc()).paginate(
        page=page, per_page=15, error_out=False
    )

    total_filtered = query.with_entities(func.sum(Expense.amount)).scalar() or 0

    return render_template("expenses/all_expenses.html",
                           expenses=expenses,
                           category_filter=category_filter,
                           search_query=search_query,
                           date_from=date_from,
                           date_to=date_to,
                           total_filtered=total_filtered,
                           categories=CATEGORIES,
                           get_category_badge=get_category_badge)

# ── Budget Routes ─────────────────────────────────────────────────────────────

@expenses_bp.route("/budgets", methods=["GET", "POST"])
@login_required
def budgets():
    today = date.today()
    first_day = today.replace(day=1)

    if request.method == "POST":
        category = request.form.get("category")
        amount = request.form.get("amount")
        try:
            amount = float(amount)
            if amount <= 0:
                raise ValueError
        except (TypeError, ValueError):
            flash("Please enter a valid budget amount.", "danger")
            return redirect(url_for("expenses.budgets"))

        existing = Budget.query.filter_by(
            user_id=current_user.id,
            category=category
        ).first()

        if existing:
            existing.amount = amount
            flash(f"{category} budget updated to ৳{amount:,.2f}!", "success")
        else:
            budget = Budget(
                user_id=current_user.id,
                category=category,
                amount=amount
            )
            db.session.add(budget)
            flash(f"{category} budget set to ৳{amount:,.2f}!", "success")

        db.session.commit()
        return redirect(url_for("expenses.budgets"))

    # Get all budgets with current month spending
    budgets = Budget.query.filter_by(user_id=current_user.id).all()

    budget_data = []
    for b in budgets:
        spent = db.session.query(func.sum(Expense.amount)).filter(
            Expense.user_id == current_user.id,
            Expense.category == b.category,
            Expense.date >= first_day
        ).scalar() or 0

        percentage = (spent / b.amount * 100) if b.amount > 0 else 0
        remaining = b.amount - spent

        if percentage >= 100:
            status = "danger"
            status_text = "Over budget!"
        elif percentage >= 80:
            status = "warning"
            status_text = "Almost there!"
        elif percentage >= 50:
            status = "info"
            status_text = "On track"
        else:
            status = "success"
            status_text = "Good"

        budget_data.append({
            "id": b.id,
            "category": b.category,
            "budget": b.amount,
            "spent": spent,
            "remaining": remaining,
            "percentage": min(percentage, 100),
            "real_percentage": percentage,
            "status": status,
            "status_text": status_text,
        })

    # Sort by percentage descending
    budget_data.sort(key=lambda x: x["real_percentage"], reverse=True)

    # Dashboard warnings — categories over 80%
    warnings = [b for b in budget_data if b["real_percentage"] >= 80]

    return render_template("expenses/budgets.html",
                           budget_data=budget_data,
                           warnings=warnings,
                           categories=CATEGORIES,
                           month=today.strftime("%B %Y"))


@expenses_bp.route("/budgets/delete/<int:id>", methods=["POST"])
@login_required
def delete_budget(id):
    budget = Budget.query.get_or_404(id)
    if budget.user_id != current_user.id:
        flash("Unauthorized.", "danger")
        return redirect(url_for("expenses.budgets"))
    db.session.delete(budget)
    db.session.commit()
    flash("Budget removed.", "info")
    return redirect(url_for("expenses.budgets"))

@expenses_bp.route("/budgets/reset", methods=["POST"])
@login_required
def reset_budgets():
    Budget.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    flash("All budgets have been reset.", "info")
    return redirect(url_for("expenses.budgets"))

@expenses_bp.route("/export/pdf")
@login_required
def export_pdf():
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.units import cm
    from io import BytesIO
    from flask import send_file

    today = date.today()
    first_day = today.replace(day=1)

    export_type = request.args.get("type", "month")

    if export_type == "all":
        expenses = Expense.query.filter(
            Expense.user_id == current_user.id
        ).order_by(Expense.date).all()
        report_title = "Full Expense Report — All Time"
        download_name = "expense_report_all_time.pdf"
    else:
        expenses = Expense.query.filter(
            Expense.user_id == current_user.id,
            Expense.date >= first_day
        ).order_by(Expense.date).all()
        report_title = f"Expense Report — {today.strftime('%B %Y')}"
        download_name = f"expense_report_{today.strftime('%B_%Y')}.pdf"

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story = []

    # Title
    title_style = ParagraphStyle('title', parent=styles['Title'],
                                  fontSize=20, textColor=colors.HexColor('#16a34a'),
                                  spaceAfter=8)
    story.append(Paragraph(report_title, title_style))
    story.append(Paragraph(f"Generated for: {current_user.username}", styles['Normal']))
    story.append(Spacer(1, 0.5*cm))

    # Summary table
    cat_totals = {}
    for e in expenses:
        cat_totals[e.category] = cat_totals.get(e.category, 0) + e.amount

    summary_data = [["Category", "Total (BDT)", "Count"]]
    for cat, total in sorted(cat_totals.items()):
        count = sum(1 for e in expenses if e.category == cat)
        summary_data.append([cat, f"{total:,.2f}", str(count)])
    summary_data.append(["TOTAL", f"{sum(e.amount for e in expenses):,.2f}",
                          str(len(expenses))])

    summary_table = Table(summary_data, colWidths=[6*cm, 5*cm, 4*cm])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#16a34a')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 10),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e5e7eb')),
        ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor('#f0fdf4')),
        ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
        ('ROWBACKGROUNDS', (0,1), (-1,-2), [colors.white, colors.HexColor('#f9fafb')]),
        ('ALIGN', (1,0), (-1,-1), 'RIGHT'),
        ('PADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(Paragraph("Summary by Category", styles['Heading2']))
    story.append(Spacer(1, 0.3*cm))
    story.append(summary_table)
    story.append(Spacer(1, 0.7*cm))

    # Itemized table
    item_data = [["Date", "Description", "Category", "Amount (BDT)"]]
    for e in expenses:
        item_data.append([
            e.date.strftime("%d %b %Y"),
            e.description[:35] + ("..." if len(e.description) > 35 else ""),
            e.category,
            f"{e.amount:,.2f}"
        ])

    item_table = Table(item_data, colWidths=[3*cm, 8*cm, 4*cm, 4*cm])
    item_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1f2937')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('GRID', (0,0), (-1,-1), 0.3, colors.HexColor('#e5e7eb')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f9fafb')]),
        ('ALIGN', (3,0), (3,-1), 'RIGHT'),
        ('PADDING', (0,0), (-1,-1), 7),
    ]))
    story.append(Paragraph("Itemized Expenses", styles['Heading2']))
    story.append(Spacer(1, 0.3*cm))
    story.append(item_table)

    doc.build(story)
    buffer.seek(0)
    return send_file(buffer, mimetype="application/pdf",
                     download_name=download_name,
                     as_attachment=True)