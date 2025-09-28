import os
import cv2
import csv
import numpy as np
import pandas as pd
from mtcnn import MTCNN
import face_recognition
import io
from datetime import datetime
from flask import Flask, render_template, request, redirect, session, url_for, send_file, jsonify

app = Flask(_name_)
app.secret_key = 'secret123'

UPLOAD_FOLDER = 'uploads'
RESULT_PATH = 'static/result.jpg'
ATTENDANCE_FILE = 'data.csv'
TRAINING_DIR = os.path.join('static', 'data')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Load training encodings once
training_encodings = {}
for name in os.listdir(TRAINING_DIR):
    person_dir = os.path.join(TRAINING_DIR, name)
    if not os.path.isdir(person_dir):
        continue
    for fname in os.listdir(person_dir):
        if not fname.lower().endswith(('.jpg', 'png', 'jpeg')):
            continue
        img_path = os.path.join(person_dir, fname)
        img = face_recognition.load_image_file(img_path)
        encs = face_recognition.face_encodings(img)
        if encs:
            training_encodings.setdefault(name, []).append(encs[0])

# Initialize attendance file
if not os.path.exists(ATTENDANCE_FILE) or os.stat(ATTENDANCE_FILE).st_size == 0:
    if training_encodings:
        initial_data = pd.DataFrame(list(training_encodings.keys()), columns=['Name'])
        initial_data.to_csv(ATTENDANCE_FILE, index=False)
    else:
        with open(ATTENDANCE_FILE, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Name'])

@app.route('/', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        with open('users.csv', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['username'] == username and row['password'] == password:
                    session['username'] = username
                    return redirect('/dashboard')
        error = "Invalid credentials"
    return render_template('login.html', error=error)

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'username' not in session:
        return redirect('/')
    try:
        if request.method == 'POST':
            file = request.files.get('image')
            if not file:
                return "No file uploaded."

            group_path = os.path.join(UPLOAD_FOLDER, file.filename)
            file.save(group_path)

            # df = pd.read_csv(ATTENDANCE_FILE)
            # current_date_str = datetime.now().strftime('%Y-%m-%d')

            # if current_date_str not in df.columns:
            #     df[current_date_str] = 'Absent'
            df = pd.read_csv(ATTENDANCE_FILE)
            # current_date_str = datetime.now().strftime('%Y-%m-%d')
            current_date_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Reset all to 'Absent' for the current date, even if column exists
            df[current_date_str] = 'Absent'

            bgr = cv2.imread(group_path)
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            detector = MTCNN()
            faces = detector.detect_faces(rgb)

            present_students = []

            for face in faces:
                x, y, w, h = face['box']
                m = 10
                top = max(0, y - m)
                right = min(rgb.shape[1], x + w + m)
                bottom = min(rgb.shape[0], y + h + m)
                left = max(0, x - m)

                encs = face_recognition.face_encodings(rgb, [(top, right, bottom, left)])
                if not encs:
                    cv2.rectangle(bgr, (left, top), (right, bottom), (0, 0, 255), 2)
                    cv2.putText(bgr, "Unknown", (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
                    continue

                face_enc = encs[0]
                best_match = None
                best_dist = 0.5

                for name, train_enc_list in training_encodings.items():
                    for train_enc in train_enc_list:
                        dist = np.linalg.norm(face_enc - train_enc)
                        if dist < best_dist:
                            best_dist = dist
                            best_match = name

                if best_match:
                    present_students.append(best_match)
                    color = (0, 255, 0)
                    label = best_match
                else:
                    color = (0, 0, 255)
                    label = "Unknown"

                cv2.rectangle(bgr, (left, top), (right, bottom), color, 2)
                cv2.putText(bgr, label, (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

            for student_name in df['Name']:
                if student_name in present_students:
                    df.loc[df["Name"] == student_name, current_date_str] = 'Present'

            df.to_csv(ATTENDANCE_FILE, index=False)
            cv2.imwrite(RESULT_PATH, bgr)
            return redirect('/result')

        return render_template('dashboard.html')
    except Exception as e:
        print("Error in dashboard:", e)
        return str(e)

@app.route('/logout')
def logout():
    session.clear()  # or session.pop('user', None)
    return redirect(url_for('login'))  # Redirect to the login page

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')
@app.route('/view-database')
def view_database():
    students = {}
    data_dir = os.path.join(app.static_folder, 'data')
    for name in os.listdir(data_dir):
        path = os.path.join(data_dir, name)
        if os.path.isdir(path):
            images = [url_for('static', filename=f'data/{name}/{img}') 
                      for img in os.listdir(path) if img.lower().endswith(('.jpg','.png','.jpeg'))]
            students[name] = images
    return render_template('database.html', students=students)

@app.route('/result')
def result():
    return render_template('result.html', image=RESULT_PATH)

@app.route('/download_attendance_csv')
def download_attendance_csv():
    if not os.path.exists(ATTENDANCE_FILE):
        return "Attendance file not found!", 404

    df = pd.read_csv(ATTENDANCE_FILE)
    csv_buffer = io.BytesIO()
    df.to_csv(csv_buffer, index=False, encoding='utf-8')
    csv_buffer.seek(0)

    return send_file(
        csv_buffer,
        mimetype='text/csv',
        as_attachment=True,
        download_name='full_attendance_report.csv'
    )


@app.route('/total-attendance')
def total_attendance():
    if not os.path.exists(ATTENDANCE_FILE):
        return "Attendance file not found!", 404

    df = pd.read_csv(ATTENDANCE_FILE)
    if df.shape[1] <= 2:  # Only Roll No and Name
        return "No attendance data to summarize yet.", 200

    summary_data = []

    for index, row in df.iterrows():
        name = row['Name']
        present_count = sum(str(value).strip().lower() == 'present' for value in row[2:])
        summary_data.append({'Name': name, 'Total Attendance': present_count})

    return render_template('total_attendance.html', summary=summary_data)

 
# @app.route('/total-attendance')
# def total_attendance():
#     if not os.path.exists(ATTENDANCE_FILE):
#         return "Attendance file not found!", 404

#     df = pd.read_csv(ATTENDANCE_FILE)
#     summary_data = df.to_dict(orient='records')
#     return render_template('total_attendance.html', summary=summary_data)
@app.route('/view-attendance-page')
def view_attendance_page():
    if not os.path.exists(ATTENDANCE_FILE) or os.stat(ATTENDANCE_FILE).st_size == 0:
        if training_encodings:
            initial_data = pd.DataFrame(list(training_encodings.keys()), columns=['Name'])
            initial_data.to_csv(ATTENDANCE_FILE, index=False)
        else:
            with open(ATTENDANCE_FILE, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['Name'])

    attendance_df = pd.read_csv(ATTENDANCE_FILE)
    attendance_df = attendance_df.fillna('N/A')
    attendance_data = attendance_df.to_dict(orient='records')
    headers = attendance_df.columns.tolist()
    return render_template('updated_attendance.html', attendance=attendance_data, headers=headers)

if _name_ == '_main_':
    # print(app.url_map)
    app.run(debug=True, port=5050)
