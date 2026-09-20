from flask import Flask, render_template, request, redirect, session, send_file
import psycopg2
from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.styles import getSampleStyleSheet

app = Flask(__name__)
app.secret_key = "secret"

# ---------------- DATABASE ----------------
def get_connection():
    return psycopg2.connect(
        host="localhost",
        database="srms",
        user="postgres",
        password="1234"
    )

def get_student_data():
    conn = get_connection()
    cur = conn.cursor()

    sid = session['student_id']

    # Get marks
    cur.execute("SELECT * FROM marks WHERE student_id=%s", (sid,))
    data = cur.fetchone()

    print("Fetched data:", data)

    # Get subjects
    cur.execute("SELECT name FROM subjects ORDER BY id")
    subject_rows = cur.fetchall()

    subjects = [row[0] for row in subject_rows]

    # Get marks list
    if data:
        marks = list(data[3:])
    else:
        marks = []

    # Match length (VERY IMPORTANT)
    min_len = min(len(subjects), len(marks))
    subjects = subjects[:min_len]
    marks = marks[:min_len]

    return marks, subjects


# ---------------- LOGIN ----------------
@app.route("/")
def home():
    return render_template("home.html")

@app.route("/choose_login")
def choose_login():
    return render_template("choose_login.html")

@app.route("/teacher_login", methods=["GET","POST"])
def teacher_login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if username == "admin" and password == "1234":
            session["role"] = "teacher"   # 🔥 ADD THIS
            return redirect("/dashboard")
        else:
            return render_template("login.html", error="❌ Wrong Username or Password")

    return render_template("login.html")

@app.route("/student_login", methods=["GET","POST"])
def student_login():
    if request.method == "POST":
        sid = request.form["student_id"]
        pwd = request.form["password"]

        conn = get_connection()
        cur = conn.cursor()

        cur.execute("SELECT student_id,name FROM students WHERE student_id=%s AND password=%s", (sid, pwd))
        data = cur.fetchone()

        if data:
            session['student_id'] = data[0]
            session['student'] = data[1]
            session['role'] = 'student'   

            return redirect("/dashboard")
        else:
            return render_template("student_login.html", 
                                   error="❌ Invalid Student ID or Password")

    return render_template("student_login.html")

@app.route("/manage_subjects", methods=["GET","POST"])
def manage_subjects():
    conn = get_connection()
    cur = conn.cursor()

    if request.method == "POST":
        cur.execute("DELETE FROM subjects")

        for i in range(1, 11):
            sub = request.form.get(f"sub{i}")
            if sub:
                cur.execute("INSERT INTO subjects(name) VALUES (%s)", (sub,))

        conn.commit()

    cur.execute("SELECT name FROM subjects")
    data = cur.fetchall()

    return render_template("manage_subjects.html", data=data)

# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
def dashboard():
    role = session.get('role')

    if role == 'teacher':
        return render_template("dashboard.html")

    elif role == 'student':
        return render_template("student_dashboard.html")

    else:
        return redirect("/login")

@app.route("/student_dashboard")
def student_dashboard():
    name = session.get("student")

    conn = get_connection()
    cur = conn.cursor()

    # Get student id
    cur.execute("SELECT student_id FROM students WHERE name=%s", (name,))
    sid = cur.fetchone()[0]

    # Get marks
    cur.execute("SELECT * FROM marks WHERE student_id=%s", (sid,))
    data = cur.fetchone()

    prediction = None

    if data:
        prediction = predict_next_sem(data)

    return render_template("student_dashboard.html", prediction=prediction)

# ---------------- ADD STUDENT ----------------
@app.route("/add_student", methods=["GET","POST"])
def add_student():
    msg = ""

    if request.method == "POST":
        conn = get_connection()
        cur = conn.cursor()

        sid = request.form["student_id"]

        cur.execute("""
        INSERT INTO students(name, student_id, password, phone, email, class)
        VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            request.form["name"],
            sid,
            sid,
            request.form["phone"],
            request.form["email"],
            request.form["class"]
        ))

        conn.commit()
        conn.close()

        return redirect("/dashboard")

    return render_template("add_student.html", msg=msg)

# ---------------- ENTER MARKS ----------------
@app.route("/enter_marks", methods=["GET","POST"])
def enter_marks():
    msg = ""

    if request.method == "POST":
        conn = get_connection()
        cur = conn.cursor()

        data = [int(request.form[f"sub{i}"]) for i in range(1,11)]

        cur.execute("""
        INSERT INTO marks(student_id,sem,sub1,sub2,sub3,sub4,sub5,sub6,sub7,sub8,sub9,sub10)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (request.form["student_id"], request.form["sem"], *data))

        conn.commit()
        conn.close()

        msg = "✅ Marks Saved & Result Generated!"

    return render_template("enter_marks.html", msg=msg)

# ---------------- CALCULATION ----------------
def calculate_result(row):
    marks = list(map(int, row[3:]))
    total = sum(marks)
    percent = total / 10
    sgpa = round(percent / 10, 2)

    if percent >= 80:
        performance = "Excellent ⭐"
    elif percent >= 60:
        performance = "Good 👍"
    else:
        performance = "Needs Improvement ⚠️"

    return total, percent, sgpa, performance

def predict_next_sem(row):
    marks = list(map(int, row[3:]))

    avg = sum(marks) / len(marks)

    # Predict SGPA
    predicted_sgpa = round((avg / 100) * 10, 2)

    # Find weak subjects
    subjects = ["Marathi", "IKS", "DS", "DBMS", "Practical",
                "SE", "Mini Project", "Maths", "Python", "AI"]

    weak = [subjects[i] for i in range(len(marks)) if marks[i] < 50]

    # Suggestion
    if predicted_sgpa >= 8:
        msg = "Excellent performance expected 🎯"
    elif predicted_sgpa >= 6:
        msg = "Good, but improve weak subjects 👍"
    else:
        msg = "Needs serious improvement ⚠️"

    return predicted_sgpa, weak, msg

# ---------------- VIEW RESULT ----------------
@app.route('/view_result', methods=['GET', 'POST'])
def view_result():
    result = None
    calc = None
    student_name = None
    show_result = False

    if request.method == "POST":
        student_id = request.form["student_id"]

        conn = get_connection()
        cur = conn.cursor()

        # Get marks
        cur.execute("SELECT * FROM marks WHERE student_id=%s", (student_id,))
        data = cur.fetchall()

        # Get student name
        cur.execute("SELECT name FROM students WHERE student_id=%s", (student_id,))
        name_data = cur.fetchone()

        if data:
            result = data
            calc = [calculate_result(r) for r in data]
            show_result = True

        if name_data:
            student_name = name_data[0]

        conn.close()

    return render_template(
        "view_result.html",
        result=result,
        calc=calc,
        student_name=student_name,
        show_result=show_result
    )

# ---------------- PDF DOWNLOAD ----------------
from flask import send_file
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

@app.route("/download_pdf/<student_id>")
def download_pdf(student_id):

    conn = get_connection()
    cur = conn.cursor()

    # ✅ Get student details
    cur.execute("SELECT name, phone, email, class FROM students WHERE student_id=%s", (student_id,))
    student = cur.fetchone()

    # ✅ Get marks
    cur.execute("SELECT * FROM marks WHERE student_id=%s", (student_id,))
    marks = cur.fetchone()

    conn.close()

    filename = f"result_{student_id}.pdf"
    doc = SimpleDocTemplate(filename)
    styles = getSampleStyleSheet()
    elements = []

    # ✅ Title (bigger font automatically)
    elements.append(Paragraph("<b>Student Result Report</b>", styles['Title']))
    elements.append(Spacer(1, 15))

    # ✅ Student Info
    elements.append(Paragraph(f"<b>Name:</b> {student[0]}", styles['Normal']))
    elements.append(Paragraph(f"<b>Phone:</b> {student[1]}", styles['Normal']))
    elements.append(Paragraph(f"<b>Email:</b> {student[2]}", styles['Normal']))
    elements.append(Paragraph(f"<b>Class:</b> {student[3]}", styles['Normal']))
    elements.append(Spacer(1, 15))

    # ✅ Subjects
    subjects = ["Marathi", "IKS", "DS", "DBMS", "Practical", "SE", "Mini Project", "Maths", "Python", "AI"]

    table_data = [["Subject", "Marks", "Remark"]]

    total = 0

    for i in range(10):
        mark = marks[i+3]   # important

        total += mark

        if mark >= 75:
            remark = "Good"
        elif mark >= 50:
            remark = "Average"
        else:
            remark = "Improve"

        table_data.append([subjects[i], mark, remark])

    # ✅ Calculate SGPA
    sgpa = round((total / 10) / 10, 2)

    # ✅ Table
    table = Table(table_data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.grey),
        ('TEXTCOLOR',(0,0),(-1,0),colors.white),
        ('ALIGN',(0,0),(-1,-1),'CENTER'),
        ('GRID',(0,0),(-1,-1),1,colors.black),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold')
    ]))

    elements.append(table)
    elements.append(Spacer(1, 20))

    # ✅ SGPA
    elements.append(Paragraph(f"<b>SGPA:</b> {sgpa}", styles['Normal']))
    elements.append(Spacer(1, 10))

    # ✅ Suggestion (FIXED)
    if sgpa >= 8:
        suggestion = "Maintain consistency and aim for higher excellence."
    elif sgpa >= 6:
        suggestion = "Focus on weak subjects to improve performance."
    else:
        suggestion = "Needs strong focus and regular practice in all subjects."

    elements.append(Paragraph(f"<b>Suggestion:</b> {suggestion}", styles['Normal']))

    # ✅ Build PDF
    doc.build(elements)

    return send_file(filename, as_attachment=True)

@app.route('/student_analytics')
def student_analytics():
    if 'student_id' not in session:
        return redirect('/student_login')

    marks, subjects = get_student_data()

    return render_template("student_analytics.html", marks=marks, subjects=subjects)

@app.route('/analytics')
def analytics():
    if session.get('role') !='teacher':
        return redirect('/teacher_login')

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM marks")
    all_data = cur.fetchall()

    cur.execute("SELECT student_id, name FROM students")
    students = dict(cur.fetchall())

    if not all_data:
        return render_template("analytics.html", msg="No data available")

    total_students = len(all_data)

    subject_totals = [0]*10
    results = []
    total_marks_all = 0
    total_subjects = 0

    for row in all_data:
        marks = list(row[3:])
        total = sum(marks)
        avg = total / len(marks)

        total_marks_all += total
        total_subjects += len(marks)

        for i in range(len(marks)):
            subject_totals[i] += marks[i]

        results.append({
            "name": students.get(row[1], "Unknown"),
            "avg": round(avg, 2),
            "total": total
        })

    class_avg = round(total_marks_all / total_subjects, 2)
    topper = max(results, key=lambda x: x['total'])

    subject_avg = [round(s/total_students, 2) for s in subject_totals]

    subjects = [
        "Marathi", "IKS", "DS", "DBMS", "Practical",
        "SE", "Mini Project", "Maths", "Python", "AI"
    ]

    return render_template(
        "analytics.html",
        class_avg=class_avg,
        topper=topper,
        subject_avg=subject_avg,
        subjects=subjects,
        results=results
    )

@app.route('/bar')
def bar():
    if 'student_id' not in session:
        return redirect('/student_login')

    conn = get_connection()
    cur = conn.cursor()

    sid = session['student_id']

    cur.execute("SELECT * FROM marks WHERE student_id=%s", (sid,))
    data = cur.fetchone()

    print("Fetched Data:", data)

    if not data:
        return "No data found"

    
    marks = list(data[3:])  

    # Temporary
    subjects = [
        "Marathi", "IKS", "DS", "DBMS", "Practical",
        "SE", "Mini Project", "Maths", "Python", "AI"
    ]

    print("Marks Sent:", marks)
    print("Subjects Sent:", subjects)

    return render_template("bar.html", marks=marks, subjects=subjects)

@app.route('/pie')
def pie():
    if 'student_id' not in session:
        return redirect('/student_login')

    conn = get_connection()
    cur = conn.cursor()

    sid = session['student_id']

    cur.execute("SELECT * FROM marks WHERE student_id=%s", (sid,))
    data = cur.fetchone()

    if not data:
        return "No data found"

    marks = list(data[3:])
    subjects = [
        "Marathi", "IKS", "DS", "DBMS", "Practical",
        "SE", "Mini Project", "Maths", "Python", "AI"
    ]

    return render_template("pie.html", marks=marks, subjects=subjects)

@app.route('/teacher_bar')
def teacher_bar():
    if session.get('role') !='teacher':
        return redirect('/teacher_login')

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM marks")
    all_data = cur.fetchall()

    if not all_data:
        return "No data available"

    subject_totals = [0]*10
    total_students = len(all_data)

    for row in all_data:
        marks = list(row[3:])
        for i in range(len(marks)):
            subject_totals[i] += marks[i]

    subject_avg = [round(s/total_students, 2) for s in subject_totals]

    subjects = [
        "Marathi", "IKS", "DS", "DBMS", "Practical",
        "SE", "Mini Project", "Maths", "Python", "AI"
    ]

    return render_template("teacher_bar.html", subjects=subjects, marks=subject_avg)

@app.route('/teacher_pie')
def teacher_pie():
    if session.get('role') !='teacher':
        return redirect('/teacher_login')

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM marks")
    all_data = cur.fetchall()

    if not all_data:
        return "No data available"

    excellent = good = poor = 0

    for row in all_data:
        marks = list(row[3:])
        avg = sum(marks)/len(marks)

        if avg >= 80:
            excellent += 1
        elif avg >= 60:
            good += 1
        else:
            poor += 1

    labels = ["Excellent", "Good", "Needs Improvement"]
    values = [excellent, good, poor]

    return render_template("teacher_pie.html", labels=labels, values=values)

import pandas as pd

@app.route("/download_excel/<sid>")
def download_excel(sid):
    conn = get_connection()
    query = "SELECT * FROM marks WHERE student_id=%s"
    df = pd.read_sql_query(query, conn, params=(sid,))

    file = f"{sid}_result.xlsx"
    df.to_excel(file, index=False)

    return send_file(file, as_attachment=True)

@app.route("/all_results")
def all_results():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
SELECT 
s.name,
s.student_id,
m.sem,
m.sub1, m.sub2, m.sub3, m.sub4, m.sub5,
m.sub6, m.sub7, m.sub8, m.sub9, m.sub10
FROM students s
JOIN marks m ON s.student_id = m.student_id
""")

    data = cur.fetchall()
    return render_template("all_results.html", data=data)

import smtplib
from email.message import EmailMessage

@app.route("/send_email", methods=["GET","POST"])
def send_email():
    if request.method == "POST":
        sid = request.form["student_id"]

        download_pdf(sid)

        conn = get_connection()
        cur = conn.cursor()

        cur.execute("SELECT email FROM students WHERE student_id=%s", (sid,))
        email = cur.fetchone()[0]

        file = f"result_{sid}.pdf"

        msg = EmailMessage()
        msg['Subject'] = "Your Result"
        msg['From'] = "your_email@gmail.com"
        msg['To'] = email
        msg.set_content("Please find your result attached.")

        with open(file, "rb") as f:
            msg.add_attachment(f.read(), maintype="application", subtype="pdf", filename=file)

        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login("shivangitapare3@gmail.com", "pkuf lvxs fvbc hdbr")
        server.send_message(msg)
        server.quit()

        return "Email Sent Successfully!"

    return render_template("send_email.html")

@app.route("/prediction")
def prediction():
    conn = get_connection()
    cur = conn.cursor()

    # get student id
    cur.execute("SELECT student_id FROM students WHERE name=%s", (session['student'],))
    sid_data = cur.fetchone()

    if not sid_data:
        return "Student not found"

    sid = sid_data[0]

    # get marks
    cur.execute("SELECT * FROM marks WHERE student_id=%s", (sid,))
    data = cur.fetchone()

    if data is None:
        return "No marks found"

    marks = list(data[3:13])
    subjects = [
    "Marathi 1",
    "IKS",
    "DS-I",
    "DBMS-II",
    "Practical (DS-I & DBMS-I)",
    "Software Engineering",
    "Mini Project",
    "Maths-I",
    "Practical (Maths-I Python)",
    "AI"
    ]

    # weak subjects logic
    weak_subjects = []
    for i in range(len(marks)):
        if marks[i] < 50:
            weak_subjects.append(subjects[i])

    # sgpa
    base_sgpa = (sum(marks)/len(marks)) / 10
    sgpa = base_sgpa + 0.2 - (len(weak_subjects) * 0.1)

    # adjust sgpa
    if len(weak_subjects) > 3:
        sgpa -= 1
    elif len(weak_subjects) > 1:
        sgpa -= 0.5

    # weak subjects string
    if weak_subjects:
        weak_subjects_str = ", ".join(weak_subjects)
    else:
        weak_subjects_str = "None 🎉"

    # suggestion
    if len(weak_subjects) == 0:
        suggestion = "Excellent performance 🚀"
    elif len(weak_subjects) <= 2:
        suggestion = "Good performance 👍"
    else:
        suggestion = "Focus more 📚"

    return render_template(
        "prediction.html",
        prediction=[round(sgpa, 2), weak_subjects_str, suggestion]
    )

from flask import redirect, url_for, session

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)