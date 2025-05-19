import os
import csv
import io # To write CSV to an in-memory file
from flask import render_template, request, redirect, url_for, flash, Blueprint, current_app, send_from_directory, abort, Response
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from config import allowed_file # 導入 allowed_file 函式
from app.__init__ import get_db # 導入資料庫連接函式
from app.models import User # 導入 User 模型
import mysql.connector # 導入 MySQL 連接庫
from datetime import datetime
# 導入所有需要的表單類
from app.forms import (
    LoginForm, AddUserForm, EditUserForm, AddStudentForm, EditStudentForm,
    AddClassForm, EditClassForm, ChangePasswordForm,
    RecordAbsenceForm, EditAbsenceForm,
    RecordAwardPunishForm, EditAwardPunishForm,
    RecordCompetitionForm, EditCompetitionForm,
    RecordLateForm, EditLateForm,
    RecordIncompleteHomeworkForm, EditIncompleteHomeworkForm
)

# 導入相應的資料庫模型
# 請確保這些模型在您的 app.models 檔案中已定義
from app.models import Student, SchoolClass, Absence, AwardPunishment, Competition, LateRecord, IncompleteHomeworkRecord


main_bp = Blueprint('main', __name__) # 主要應用功能路由

# --- 主要應用功能 (Main) 藍圖路由 ---

@main_bp.route('/')
def index():
    """根目錄，重定向到登入或儀表板"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('auth.login')) # 重定向到 auth 藍圖的 login 路由

@main_bp.route('/dashboard')
@login_required # 需要登入才能訪問此路由
def dashboard():
    """使用者儀表板"""
    # 根據使用者角色渲染不同的儀表板模板或內容
    if current_user.is_admin():
        return redirect(url_for('admin.admin_dashboard')) # 重定向到 admin 藍圖的儀表板
    elif current_user.is_supervisor():
        # 獲取主管的使用者名稱（可能是老師姓名）
        # 使用 User 模型中已有的 teacher_name 屬性
        supervisor_name = current_user.teacher_name if current_user.teacher_name else current_user.username
        # 主管通常可以看到所有班級的匯總數據或入口連結
        conn = get_db()
        classes = []
        if conn:
             cursor = conn.cursor(dictionary=True)
             try:
                  # 主管通常可以看到所有班級
                  cursor.execute("SELECT class_id, class_name FROM classes ORDER BY class_name")
                  classes = cursor.fetchall()
             except mysql.connector.Error as err:
                  flash(f"資料庫錯誤: {err}", 'danger')
                  current_app.logger.error(f"資料庫錯誤 (主管儀表板獲取班級): {err}")
             finally:
                  if conn and conn.is_connected():
                       cursor.close()
                       conn.close()

        return render_template('supervisor_dashboard.html', title='主管儀表板', supervisor_name=supervisor_name, classes=classes)
    elif current_user.is_teacher():
        # 教師儀表板需要顯示其管理的班級 (從 teacher_classes 關聯表中獲取)
        # User 模型中已經有了 assigned_classes 屬性
        assigned_classes = current_user.assigned_classes # 直接使用 User 模型的方法

        return render_template('teacher_dashboard.html', title='教師儀表板', assigned_classes=assigned_classes)
    else:
        # 未知角色，可能需要處理
        flash('未知的使用者角色', 'warning')
        logout_user() # 強制登出未知角色的使用者
        return redirect(url_for('auth.login'))

@main_bp.route('/class/<int:class_id>/students')
@login_required
def student_list(class_id):
    """顯示特定班級的學生列表"""
    # 檢查使用者是否有權限查看此班級的學生列表
    # 教師只能查看自己負責的班級，主管和管理員可以查看所有班級
    conn = get_db()
    class_name = None
    students = []

    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            # 獲取班級名稱
            cursor.execute("SELECT class_id, class_name FROM classes WHERE class_id = %s", (class_id,))
            class_data = cursor.fetchone()
            if class_data:
                class_name = class_data['class_name']
            else:
                 flash('找不到該班級', 'danger')
                 if conn and conn.is_connected():
                      cursor.close()
                      conn.close()
                 return redirect(url_for('main.dashboard'))

            # 檢查權限
            has_permission = False
            if current_user.is_admin() or current_user.is_supervisor():
                 has_permission = True
            elif current_user.is_teacher():
                 # 檢查教師是否負責此班級
                 # 使用 User 模型中實現的方法
                 if any(c['class_id'] == class_id for c in current_user.assigned_classes):
                      has_permission = True


            if not has_permission:
                 flash('您無權查看此班級', 'danger')
                 if conn and conn.is_connected():
                      cursor.close()
                      conn.close()
                 return redirect(url_for('main.dashboard'))


            # 獲取班級學生列表，包括所有計數和點數
            cursor.execute("""
                SELECT student_id, student_number, name, late_count, incomplete_homework_count, violation_points, award_points, id_card_number, student_id_number
                FROM students
                WHERE class_id = %s
                ORDER BY student_number, name
            """, (class_id,))
            students = cursor.fetchall()

            # For CSV export, we might need more detailed record counts per student
            # This could be optimized with JOINs or separate queries if needed for display
            # For now, we fetch totals and get details for CSV export separately if requested

        except mysql.connector.Error as err:
            flash(f"資料庫錯誤: {err}", 'danger')
            current_app.logger.error(f"資料庫錯誤 (學生列表): {err}")
        finally:
            if conn and conn.is_connected():
                 cursor.close()
                 conn.close()


    # Passing class_data object for consistency with other edit forms if needed later
    return render_template('student_list.html', title=f'{class_name} 學生列表', students=students, class_id=class_id, class_name=class_name, class_data=class_data)

@main_bp.route('/class/<int:class_id>/students/export/csv')
@login_required
def export_student_list_csv(class_id):
    """匯出特定班級的學生數據到 CSV 文件"""
    # 檢查使用者是否有權限匯出此班級的數據
    conn = get_db()
    students_data = []
    class_name = None

    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            # 獲取班級名稱
            cursor.execute("SELECT class_name FROM classes WHERE class_id = %s", (class_id,))
            class_info = cursor.fetchone()
            if class_info:
                 class_name = class_info['class_name']
            else:
                 flash('找不到該班級', 'danger')
                 if conn and conn.is_connected():
                      cursor.close()
                      conn.close()
                 return redirect(url_for('main.dashboard')) # Or a specific error page


            # 檢查權限 (與 student_list 路由邏輯相同)
            has_permission = False
            if current_user.is_admin() or current_user.is_supervisor():
                 has_permission = True
            elif current_user.is_teacher():
                 # 檢查教師是否負責此班級
                 # 使用 User 模型中實現的方法
                 if any(c['class_id'] == class_id for c in current_user.assigned_classes):
                      has_permission = True

            if not has_permission:
                 flash('您無權匯出此班級數據', 'danger')
                 if conn and conn.is_connected():
                      cursor.close()
                      conn.close()
                 return redirect(url_for('main.dashboard'))

            # 獲取班級所有學生數據，包括所有計數和點數
            cursor.execute("""
                SELECT student_id, student_number, name, late_count, incomplete_homework_count, violation_points, award_points, id_card_number, student_id_number
                FROM students
                WHERE class_id = %s
                ORDER BY student_number, name
            """, (class_id,))
            students = cursor.fetchall()

            # 對於每個學生，獲取詳細的獎懲、參賽等記錄計數
            detailed_students_data = []
            for student in students:
                 student_details = student.copy() # 複製學生基本信息
                 student_id = student['student_id']

                 # 獲取詳細的獎懲計數
                 award_punish_counts = {}
                 award_punish_types = ['表揚', '優點', '小功', '大功', '警告', '缺點', '小過', '大過']
                 for ap_type in award_punish_types:
                      cursor.execute("SELECT COUNT(*) AS count FROM awards_punishments WHERE student_id = %s AND type = %s", (student_id, ap_type))
                      award_punish_counts[ap_type] = cursor.fetchone()['count']
                 student_details.update(award_punish_counts) # 將計數添加到學生數據中

                 # 獲取詳細的參賽計數
                 comp_counts = {}
                 comp_results = ['參與', '入圍', '得獎']
                 for comp_result in comp_results:
                      cursor.execute("SELECT COUNT(*) AS count FROM competitions WHERE student_id = %s AND result = %s", (student_id, comp_result))
                      comp_counts[comp_result] = cursor.fetchone()['count']
                 student_details.update(comp_counts) # 將計數添加到學生數據中

                 # 總缺席節數已在 students 表中
                 # 總遲到次數已在 students 表中
                 # 總欠交功課次數已在 students 表中

                 detailed_students_data.append(student_details)

        except mysql.connector.Error as err:
            flash(f"資料庫錯誤: {err}", 'danger')
            current_app.logger.error(f"資料庫錯誤 (匯出學生數據): {err}")
            if conn and conn.is_connected():
                 cursor.close()
                 conn.close()
            return redirect(url_for('main.student_list', class_id=class_id)) # 匯出失敗，返回學生列表頁面
        finally:
            if conn and conn.is_connected():
                 cursor.close()
                 conn.close()

    # 生成 CSV 數據
    if not detailed_students_data:
        flash('該班級沒有學生數據可匯出', 'warning')
        return redirect(url_for('main.student_list', class_id=class_id))

    # 使用 io.StringIO 創建一個記憶體中的文件對象
    output = io.StringIO()
    writer = csv.writer(output)

    # 寫入 CSV 表頭
    # 表頭順序可以根據需要調整
    header = [
        '學生ID', '學號', '姓名', 'ID卡號碼', '學生證號碼',
        '總遲到次數', '總欠交功課次數', '總違規點數', '總獎勵點數',
        '表揚次數', '優點次數', '小功次數', '大功次數',
        '警告次數', '缺點次數', '小過次數', '大過次數',
        '參賽次數 (參與)', '參賽次數 (入圍)', '參賽次數 (得獎)'
        # 總缺席節數已在學生基本信息中
    ]
    writer.writerow(header)

    # 寫入學生數據行
    for student in detailed_students_data:
        row = [
            student.get('student_id', ''),
            student.get('student_number', ''),
            student.get('name', ''),
            student.get('id_card_number', ''),
            student.get('student_id_number', ''),
            student.get('late_count', 0),
            student.get('incomplete_homework_count', 0),
            student.get('violation_points', 0),
            student.get('award_points', 0),
            student.get('表揚', 0), student.get('優點', 0), student.get('小功', 0), student.get('大功', 0),
            student.get('警告', 0), student.get('缺點', 0), student.get('小過', 0), student.get('大過', 0),
            student.get('參與', 0), student.get('入圍', 0), student.get('得獎', 0)
        ]
        writer.writerow(row)

    # 構建 Response
    response = Response(output.getvalue(), mimetype='text/csv')
    response.headers['Content-Disposition'] = f'attachment; filename="{class_name}_學生數據.csv"'
    return response


@main_bp.route('/students/<int:student_id>/records')
@login_required
# @roles_required('admin', 'supervisor', 'teacher') # Assuming this check is done, or is handled by is_accessible_by
def view_records(student_id):
    """
    查看單個學生的所有記錄。
    需要 student_id 參數來確定要查看哪個學生的記錄。
    用戶需要有 'admin', 'supervisor', 或 'teacher' 角色。
    老師只能查看其負責班級的學生記錄。
    """
    # 檢查權限 - 只有 admin, supervisor, 或負責該班級的老師可以查看
    conn_check = get_db()
    if conn_check:
        cursor_check = conn_check.cursor(dictionary=True)
        try:
            # 獲取學生的班級 ID 以便進行權限檢查
            cursor_check.execute("SELECT class_id FROM students WHERE student_id = %s", (student_id,))
            student_class_data = cursor_check.fetchone()

            if not student_class_data:
                flash('找不到該學生', 'danger')
                # 安全重定向，例如到學生列表或儀表板
                if conn_check.is_connected(): cursor_check.close(); conn_check.close()
                if current_user.is_admin() or current_user.is_supervisor():
                     return redirect(url_for('admin.manage_students'))
                else: # 老師或其他角色
                     return redirect(url_for('main.dashboard'))


            student_class_id = student_class_data['class_id']

            # 檢查使用者角色和班級權限
            if current_user.is_teacher():
                # 如果是老師，檢查他是否負責這個班級
                cursor_check.execute("""
                    SELECT COUNT(*) FROM teacher_classes
                    WHERE user_id = %s AND class_id = %s
                """, (current_user.get_id(), student_class_id))
                if cursor_check.fetchone()['COUNT(*)'] == 0:
                    # 如果不是負責老師，且不是 admin 或 supervisor
                    if not (current_user.is_admin() or current_user.is_supervisor()):
                        flash('您沒有權限查看這個學生的記錄。', 'danger')
                        if conn_check.is_connected(): cursor_check.close(); conn_check.close()
                        return redirect(url_for('main.dashboard')) # 重定向到老師儀表板或通用儀表板

            # Admin 和 Supervisor 預設有權限，無需額外檢查班級

        except mysql.connector.Error as err:
             flash(f"權限檢查資料庫錯誤: {err}", 'danger')
             current_app.logger.error(f"權限檢查資料庫錯誤 (view_records): {err}")
             if conn_check.is_connected(): cursor_check.close(); conn_check.close()
             return redirect(url_for('main.dashboard')) # 安全重定向
        finally:
            if conn_check and conn_check.is_connected():
                 cursor_check.close()
                 conn_check.close()


    # 如果權限檢查通過，則繼續獲取並顯示記錄
    conn = get_db()
    student = None
    absences = []
    awards_punishments = []
    competitions = []
    late_records = []
    incomplete_homework_records = []
    total_absences_sessions = 0 # 初始化總缺席節數

    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            # Fetch student data INCLUDING class_id and counts/points (EXCEPT total_absences_sessions which is calculated)
            # 修正: 在 SELECT 語句中加入 s.class_id
            cursor.execute("""
                SELECT
                    s.student_id,
                    s.student_number,
                    s.name,
                    s.class_id,          -- 加入 s.class_id
                    c.class_name,
                    s.late_count,
                    s.incomplete_homework_count,
                    s.violation_points,
                    s.award_points
                FROM students s
                JOIN classes c ON s.class_id = c.class_id
                WHERE s.student_id = %s
            """, (student_id,))
            student = cursor.fetchone()

            if not student:
                # This case should ideally be caught by the initial check, but good to double check
                flash('無法載入學生資料', 'danger')
                if conn.is_connected(): cursor.close(); conn.close()
                if current_user.is_admin() or current_user.is_supervisor():
                     return redirect(url_for('admin.manage_students'))
                else:
                     return redirect(url_for('main.dashboard'))


            # 計算總缺席節數
            # 新增查詢來計算 absence 表的 session_count 總和
            cursor.execute("""
                SELECT SUM(session_count) AS total_absences_sessions
                FROM absences
                WHERE student_id = %s
            """, (student_id,))
            total_absences_data = cursor.fetchone()
            # 將計算結果添加到 student 字典中
            total_absences_sessions = total_absences_data['total_absences_sessions'] if total_absences_data and total_absences_data['total_absences_sessions'] is not None else 0
            student['total_absences_sessions'] = total_absences_sessions # 將結果添加到 student 字典


            # Fetch absence records INCLUDING recorder name
            # 修正: 聯接 users 表，選取 teacher_name 作為 recorder_name
            cursor.execute("""
                SELECT
                    a.absence_id,
                    a.student_id,
                    a.absence_date,
                    a.session_count,
                    a.type,
                    a.reason,
                    a.upload_path,
                    a.recorded_by_user_id,
                    a.recorded_at,
                    u.teacher_name AS recorder_name -- 從 users 表獲取記錄者姓名
                FROM absences a
                JOIN users u ON a.recorded_by_user_id = u.user_id
                WHERE a.student_id = %s
                ORDER BY a.absence_date DESC, a.recorded_at DESC
            """, (student_id,))
            absences = cursor.fetchall()

            # Fetch award/punishment records INCLUDING recorder name
            # 修正: 聯接 users 表，選取 teacher_name 作為 recorder_name
            cursor.execute("""
                SELECT
                    ap.record_id,
                    ap.student_id,
                    ap.record_date,
                    ap.type,
                    ap.description,
                    ap.upload_path,
                    ap.recorded_by_user_id,
                    ap.recorded_at,
                     u.teacher_name AS recorder_name -- 從 users 表獲取記錄者姓名
                FROM awards_punishments ap
                JOIN users u ON ap.recorded_by_user_id = u.user_id
                WHERE ap.student_id = %s
                ORDER BY ap.record_date DESC, ap.recorded_at DESC
            """, (student_id,))
            awards_punishments = cursor.fetchall()

            # Fetch competition records INCLUDING recorder name
            # 修正: 聯接 users 表，選取 teacher_name 作為 recorder_name
            cursor.execute("""
                SELECT
                    c.comp_record_id,
                    c.student_id,
                    c.comp_date,
                    c.comp_name,
                    c.result,
                    c.description,
                    c.upload_path,
                    c.recorded_by_user_id,
                    c.recorded_at,
                     u.teacher_name AS recorder_name -- 從 users 表獲取記錄者姓名
                FROM competitions c
                 JOIN users u ON c.recorded_by_user_id = u.user_id
                WHERE c.student_id = %s
                ORDER BY c.comp_date DESC, c.recorded_at DESC
            """, (student_id,))
            competitions = cursor.fetchall()

            # Fetch late records INCLUDING recorder name
             # 修正: 聯接 users 表，選取 teacher_name 作為 recorder_name
            cursor.execute("""
                SELECT
                    lr.late_id,
                    lr.student_id,
                    lr.late_date,
                    lr.reason,
                    lr.recorded_by_user_id,
                    lr.recorded_at,
                     u.teacher_name AS recorder_name -- 從 users 表獲取記錄者姓名
                FROM late_records lr
                 JOIN users u ON lr.recorded_by_user_id = u.user_id
                WHERE lr.student_id = %s
                ORDER BY lr.late_date DESC, lr.recorded_at DESC
            """, (student_id,))
            late_records = cursor.fetchall()

            # Fetch incomplete homework records INCLUDING recorder name
             # 修正: 聯接 users 表，選取 teacher_name 作為 recorder_name
            cursor.execute("""
                SELECT
                    ihr.incomplete_hw_id,
                    ihr.student_id,
                    ihr.record_date,
                    ihr.subject,
                    ihr.description,
                    ihr.recorded_by_user_id,
                    ihr.recorded_at,
                     u.teacher_name AS recorder_name -- 從 users 表獲取記錄者姓名
                FROM incomplete_homework_records ihr
                JOIN users u ON ihr.recorded_by_user_id = u.user_id
                WHERE ihr.student_id = %s
                ORDER BY ihr.record_date DESC, ihr.recorded_at DESC
            """, (student_id,))
            incomplete_homework_records = cursor.fetchall()


        except mysql.connector.Error as err:
            flash(f"資料庫錯誤: {err}", 'danger')
            current_app.logger.error(f"資料庫錯誤 (view_records - 獲取記錄): {err}")
            # 如果獲取記錄失敗，仍然嘗試渲染頁面，但記錄列表會是空的
            # 確保 student 物件存在，即使記錄獲取失敗
            # 在這個修正中，student 物件在獲取記錄之前就已經獲取了，所以這裡只需要處理記錄獲取失敗的情況
            # 但如果 student 獲取也失敗了（前面的檢查會處理，但作為 fallback），我們需要重定向
            if student is None: # 再次檢查 student 是否為 None，作為額外保障
                 if conn and conn.is_connected(): cursor.close(); conn.close()
                 if current_user.is_admin() or current_user.is_supervisor():
                      return redirect(url_for('admin.manage_students'))
                 else:
                      return redirect(url_for('main.dashboard'))


        finally:
            if conn and conn.is_connected():
                 cursor.close()
                 conn.close()

    else:
        flash('無法連接到資料庫。', 'danger')
        # Redirect if cannot connect to DB
        if current_user.is_admin() or current_user.is_supervisor():
             return redirect(url_for('admin.manage_students'))
        else:
             return redirect(url_for('main.dashboard'))


    # 渲染模板並傳遞數據
    # 確保 student 是一個字典，以便在模板中使用 student["name"] 等
    # 由於我們使用 dictionary=True 獲取結果，student 應該是字典
    return render_template('view_records.html', title=f'{student["name"]} 的記錄', student=student,
                           absences=absences, awards_punishments=awards_punishments,
                           competitions=competitions, late_records=late_records,
                           incomplete_homework_records=incomplete_homework_records)


# --- 記錄表單路由 (GET 顯示表單, POST 處理提交) ---

@main_bp.route('/student/<int:student_id>/record/absence', methods=['GET', 'POST'])
@login_required
def record_absence(student_id):
    """記錄學生缺席"""
    form = RecordAbsenceForm() # 使用表單類

    conn = get_db()
    student = None
    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT student_id, name, class_id FROM students WHERE student_id = %s", (student_id,))
            student = cursor.fetchone()
            if student:
                 # 檢查使用者是否有權限為此學生記錄
                 has_permission = False
                 if current_user.is_admin() or current_user.is_supervisor():
                      has_permission = True
                 elif current_user.is_teacher():
                      # 使用 User 模型中實現的方法
                      if any(c['class_id'] == student['class_id'] for c in current_user.assigned_classes):
                           has_permission = True

                 if not has_permission:
                      flash('您無權為此學生記錄', 'danger')
                      if conn and conn.is_connected():
                           cursor.close()
                           conn.close()
                      return redirect(url_for('main.dashboard'))
            else:
                 flash('找不到該學生', 'danger')
                 if conn and conn.is_connected():
                      cursor.close()
                      conn.close()
                 return redirect(url_for('main.dashboard'))

        except mysql.connector.Error as err:
             flash(f"資料庫錯誤: {err}", 'danger')
             current_app.logger.error(f"資料庫錯誤 (記錄缺席 - 獲取學生): {err}")
        finally:
             if conn and conn.is_connected():
                  cursor.close()
                  conn.close()

    if not student:
        return redirect(url_for('main.dashboard'))

    if form.validate_on_submit():
        absence_date = form.absence_date.data
        session_count = form.session_count.data
        absence_type = form.absence_type.data
        reason = form.reason.data
        uploaded_file = form.proof.data # 從表單獲取文件

        # 處理文件上傳
        upload_path = None
        # 修正：直接使用從 config 導入的 allowed_file 函式
        if uploaded_file and uploaded_file.filename:
            if allowed_file(uploaded_file.filename):
                # 根據班級獲取或創建上傳子目錄
                class_upload_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], str(student['class_id'])) # 使用 class_id 作為文件夾名稱
                if not os.path.exists(class_upload_folder):
                    os.makedirs(class_upload_folder)

                filename = secure_filename(uploaded_file.filename)
                # 可以在這裡添加時間戳或 UUID 到文件名，以確保唯一性
                file_base, file_ext = os.path.splitext(filename)
                timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                unique_filename = f"{file_base}_{timestamp}{file_ext}"
                file_save_path = os.path.join(class_upload_folder, unique_filename)
                try:
                    uploaded_file.save(file_save_path)
                    # 儲存相對於 UPLOAD_FOLDER 的路徑
                    upload_path = os.path.join(str(student['class_id']), unique_filename).replace('\\', '/') # 確保路徑分隔符正確
                except Exception as e:
                     flash(f"文件上傳失敗: {e}", 'danger')
                     current_app.logger.error(f"文件上傳失敗: {e}")
                     # 重新渲染表單
                     return render_template('record_absence.html', title=f'記錄 {student["name"]} 缺席', student=student, form=form)


            else:
                 flash('不允許的文件類型', 'danger')
                 return render_template('record_absence.html', title=f'記錄 {student["name"]} 缺席', student=student, form=form)


        conn = get_db()
        if conn:
            cursor = conn.cursor()
            try:
                # 插入缺席記錄到資料庫
                cursor.execute(
                    "INSERT INTO absences (student_id, absence_date, session_count, type, reason, upload_path, recorded_by_user_id) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (student_id, absence_date, session_count, absence_type, reason, upload_path, current_user.get_id()) # 使用 current_user.get_id() 獲取使用者 ID
                )
                conn.commit()
                flash('缺席記錄已成功添加', 'success')
                # 重定向到學生記錄查看頁面
                return redirect(url_for('main.view_records', student_id=student_id))
            except mysql.connector.Error as err:
                conn.rollback() # 回滾事務
                flash(f"資料庫錯誤: {err}", 'danger')
                current_app.logger.error(f"資料庫錯誤 (記錄缺席): {err}")
            finally:
                if conn and conn.is_connected():
                     cursor.close()
                     conn.close()
        else:
            flash('無法連接到資料庫', 'danger')


    # GET 請求或 POST 失敗時渲染表單
    return render_template('record_absence.html', title=f'記錄 {student["name"]} 缺席', student=student, form=form)

@main_bp.route('/student/<int:student_id>/record/award_punish', methods=['GET', 'POST'])
@login_required
def record_award_punish(student_id):
    """記錄學生獎懲"""
    form = RecordAwardPunishForm() # 使用表單類

    conn = get_db()
    student = None
    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT student_id, name, class_id FROM students WHERE student_id = %s", (student_id,))
            student = cursor.fetchone()
            if student:
                 # 檢查使用者是否有權限為此學生記錄
                 has_permission = False
                 if current_user.is_admin() or current_user.is_supervisor():
                      has_permission = True
                 elif current_user.is_teacher():
                      # 使用 User 模型中實現的方法
                      if any(c['class_id'] == student['class_id'] for c in current_user.assigned_classes):
                           has_permission = True

                 if not has_permission:
                      flash('您無權為此學生記錄', 'danger')
                      if conn and conn.is_connected():
                           cursor.close()
                           conn.close()
                      return redirect(url_for('main.dashboard'))
            else:
                 flash('找不到該學生', 'danger')
                 if conn and conn.is_connected():
                      cursor.close()
                      conn.close()
                 return redirect(url_for('main.dashboard'))

        except mysql.connector.Error as err:
             flash(f"資料庫錯誤: {err}", 'danger')
             current_app.logger.error(f"資料庫錯誤 (記錄獎懲 - 獲取學生): {err}")
        finally:
             if conn and conn.is_connected():
                  cursor.close()
                  conn.close()

    if not student:
        return redirect(url_for('main.dashboard'))


    if form.validate_on_submit():
        record_date = form.record_date.data
        record_type = form.record_type.data
        description = form.description.data
        uploaded_file = form.proof.data

        # 處理文件上傳
        upload_path = None
        # 修正：直接使用從 config 導入的 allowed_file 函式
        if uploaded_file and uploaded_file.filename:
            if allowed_file(uploaded_file.filename):
                 class_upload_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], str(student['class_id']))
                 if not os.path.exists(class_upload_folder):
                     os.makedirs(class_upload_folder)

                 filename = secure_filename(uploaded_file.filename)
                 file_base, file_ext = os.path.splitext(filename)
                 timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                 unique_filename = f"{file_base}_{timestamp}{file_ext}"
                 file_save_path = os.path.join(class_upload_folder, unique_filename)
                 try:
                     uploaded_file.save(file_save_path)
                     upload_path = os.path.join(str(student['class_id']), unique_filename).replace('\\', '/')
                 except Exception as e:
                      flash(f"文件上傳失敗: {e}", 'danger')
                      current_app.logger.error(f"文件上傳失敗: {e}")
                      return render_template('record_award_punish.html', title=f'記錄 {student["name"]} 獎懲', student=student, form=form)

            else:
                 flash('不允許的文件類型', 'danger')
                 return render_template('record_award_punish.html', title=f'記錄 {student["name"]} 獎懲', student=student, form=form)


        conn = get_db()
        if conn:
            cursor = conn.cursor()
            try:
                # 插入獎懲記錄到資料庫
                cursor.execute(
                    "INSERT INTO awards_punishments (student_id, record_date, type, description, upload_path, recorded_by_user_id) VALUES (%s, %s, %s, %s, %s, %s)",
                    (student_id, record_date, record_type, description, upload_path, current_user.get_id())
                )
                conn.commit()

                # 更新學生獎勵/違規點數
                if record_type in ['優點', '小功', '大功']:
                     points = {'優點': 1, '小功': 3, '大功': 9}.get(record_type, 0)
                     cursor.execute("UPDATE students SET award_points = award_points + %s WHERE student_id = %s", (points, student_id))
                     conn.commit()
                elif record_type in ['警告', '缺點', '小過', '大過']:
                     points = {'警告': 0, '缺點': 1, '小過': 3, '大過': 9}.get(record_type, 0) # 警告通常不計點數
                     cursor.execute("UPDATE students SET violation_points = violation_points + %s WHERE student_id = %s", (points, student_id))
                     conn.commit()


                flash('獎懲記錄已成功添加', 'success')
                return redirect(url_for('main.view_records', student_id=student_id))
            except mysql.connector.Error as err:
                conn.rollback()
                flash(f"資料庫錯誤: {err}", 'danger')
                current_app.logger.error(f"資料庫錯誤 (記錄獎懲): {err}")
            finally:
                if conn and conn.is_connected():
                     cursor.close()
                     conn.close()
        else:
            flash('無法連接到資料庫', 'danger')

    # GET 請求或 POST 失敗時渲染表單
    return render_template('record_award_punish.html', title=f'記錄 {student["name"]} 獎懲', student=student, form=form)

@main_bp.route('/student/<int:student_id>/record/competition', methods=['GET', 'POST'])
@login_required
def record_competition(student_id):
    """記錄學生參賽"""
    form = RecordCompetitionForm() # 使用表單類

    conn = get_db()
    student = None
    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT student_id, name, class_id FROM students WHERE student_id = %s", (student_id,))
            student = cursor.fetchone()
            if student:
                 # 檢查使用者是否有權限為此學生記錄
                 has_permission = False
                 if current_user.is_admin() or current_user.is_supervisor():
                      has_permission = True
                 elif current_user.is_teacher():
                      # 使用 User 模型中實現的方法
                      if any(c['class_id'] == student['class_id'] for c in current_user.assigned_classes):
                           has_permission = True

                 if not has_permission:
                      flash('您無權為此學生記錄', 'danger')
                      if conn and conn.is_connected():
                           cursor.close()
                           conn.close()
                      return redirect(url_for('main.dashboard'))
            else:
                 flash('找不到該學生', 'danger')
                 if conn and conn.is_connected():
                      cursor.close()
                      conn.close()
                 return redirect(url_for('main.dashboard'))

        except mysql.connector.Error as err:
             flash(f"資料庫錯誤: {err}", 'danger')
             current_app.logger.error(f"資料庫錯誤 (記錄參賽 - 獲取學生): {err}")
        finally:
             if conn and conn.is_connected():
                  cursor.close()
                  conn.close()

    if not student:
        return redirect(url_for('main.dashboard'))

    if form.validate_on_submit():
        comp_date = form.comp_date.data
        comp_name = form.comp_name.data
        result = form.result.data
        description = form.description.data
        uploaded_file = form.proof.data

        # 處理文件上傳
        upload_path = None
        # 修正：直接使用從 config 導入的 allowed_file 函式
        if uploaded_file and uploaded_file.filename:
            if allowed_file(uploaded_file.filename):
                 class_upload_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], str(student['class_id']))
                 if not os.path.exists(class_upload_folder):
                     os.makedirs(class_upload_folder)

                 filename = secure_filename(uploaded_file.filename)
                 file_base, file_ext = os.path.splitext(filename)
                 timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                 unique_filename = f"{file_base}_{timestamp}{file_ext}"
                 file_save_path = os.path.join(class_upload_folder, unique_filename)
                 try:
                     uploaded_file.save(file_save_path)
                     upload_path = os.path.join(str(student['class_id']), unique_filename).replace('\\', '/')
                 except Exception as e:
                      flash(f"文件上傳失敗: {e}", 'danger')
                      current_app.logger.error(f"文件上傳失敗: {e}")
                      return render_template('record_competition.html', title=f'記錄 {student["name"]} 參賽', student=student, form=form)

            else:
                 flash('不允許的文件類型', 'danger')
                 return render_template('record_competition.html', title=f'記錄 {student["name"]} 參賽', student=student, form=form)


        conn = get_db()
        if conn:
            cursor = conn.cursor()
            try:
                # 插入參賽記錄到資料庫
                cursor.execute(
                    "INSERT INTO competitions (student_id, comp_date, comp_name, result, description, upload_path, recorded_by_user_id) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (student_id, comp_date, comp_name, result, description, upload_path, current_user.get_id())
                )
                conn.commit()
                flash('參賽記錄已成功添加', 'success')
                return redirect(url_for('main.view_records', student_id=student_id))
            except mysql.connector.Error as err:
                conn.rollback()
                flash(f"資料庫錯誤: {err}", 'danger')
                current_app.logger.error(f"資料庫錯誤 (記錄參賽): {err}")
            finally:
                if conn and conn.is_connected():
                     cursor.close()
                     conn.close()
        else:
            flash('無法連接到資料庫', 'danger')


    # GET 請求或 POST 失敗時渲染表單
    return render_template('record_competition.html', title=f'記錄 {student["name"]} 參賽', student=student, form=form)

# 記錄遲到路由
@main_bp.route('/student/<int:student_id>/record/late', methods=['GET', 'POST'])
@login_required
def record_late(student_id):
    """記錄學生遲到"""
    form = RecordLateForm()

    conn = get_db()
    student = None
    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT student_id, name, class_id FROM students WHERE student_id = %s", (student_id,))
            student = cursor.fetchone()
            if student:
                 # 檢查使用者是否有權限為此學生記錄
                 has_permission = False
                 if current_user.is_admin() or current_user.is_supervisor():
                      has_permission = True
                 elif current_user.is_teacher():
                      # 使用 User 模型中實現的方法
                      if any(c['class_id'] == student['class_id'] for c in current_user.assigned_classes):
                           has_permission = True

                 if not has_permission:
                      flash('您無權為此學生記錄', 'danger')
                      if conn and conn.is_connected():
                           cursor.close()
                           conn.close()
                      return redirect(url_for('main.dashboard'))
            else:
                 flash('找不到該學生', 'danger')
                 if conn and conn.is_connected():
                      cursor.close()
                      conn.close()
                 return redirect(url_for('main.dashboard'))

        except mysql.connector.Error as err:
             flash(f"資料庫錯誤: {err}", 'danger')
             current_app.logger.error(f"資料庫錯誤 (記錄遲到 - 獲取學生): {err}")
        finally:
             if conn and conn.is_connected():
                  cursor.close()
                  conn.close()

    if not student:
        return redirect(url_for('main.dashboard'))

    if form.validate_on_submit():
        late_date = form.late_date.data
        reason = form.reason.data

        conn = get_db()
        if conn:
            cursor = conn.cursor()
            try:
                # 插入遲到記錄
                cursor.execute(
                    "INSERT INTO late_records (student_id, late_date, reason, recorded_by_user_id) VALUES (%s, %s, %s, %s)",
                    (student_id, late_date, reason, current_user.get_id())
                )
                conn.commit()

                # 更新學生遲到計數
                cursor.execute("UPDATE students SET late_count = late_count + 1 WHERE student_id = %s", (student_id,))
                conn.commit()

                flash('遲到記錄已成功添加', 'success')
                return redirect(url_for('main.view_records', student_id=student_id))
            except mysql.connector.Error as err:
                conn.rollback()
                flash(f"資料庫錯誤: {err}", 'danger')
                current_app.logger.error(f"資料庫錯誤 (記錄遲到): {err}")
            finally:
                if conn and conn.is_connected():
                     cursor.close()
                     conn.close()
        else:
            flash('無法連接到資料庫', 'danger')

    return render_template('record_late.html', title=f'記錄 {student["name"]} 遲到', student=student, form=form)

# 記錄欠交功課路由
@main_bp.route('/student/<int:student_id>/record/incomplete_homework', methods=['GET', 'POST'])
@login_required
def record_incomplete_homework(student_id):
    """記錄學生欠交功課"""
    form = RecordIncompleteHomeworkForm()

    conn = get_db()
    student = None
    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT student_id, name, class_id FROM students WHERE student_id = %s", (student_id,))
            student = cursor.fetchone()
            if student:
                 # 檢查使用者是否有權限為此學生記錄
                 has_permission = False
                 if current_user.is_admin() or current_user.is_supervisor():
                      has_permission = True
                 elif current_user.is_teacher():
                      # 使用 User 模型中實現的方法
                      if any(c['class_id'] == student['class_id'] for c in current_user.assigned_classes):
                           has_permission = True

                 if not has_permission:
                      flash('您無權為此學生記錄', 'danger')
                      if conn and conn.is_connected():
                           cursor.close()
                           conn.close()
                      return redirect(url_for('main.dashboard'))
            else:
                 flash('找不到該學生', 'danger')
                 if conn and conn.is_connected():
                      cursor.close()
                      conn.close()
                 return redirect(url_for('main.dashboard'))

        except mysql.connector.Error as err:
             flash(f"資料庫錯誤: {err}", 'danger')
             current_app.logger.error(f"資料庫錯誤 (記錄欠交功課 - 獲取學生): {err}")
        finally:
             if conn and conn.is_connected():
                  cursor.close()
                  conn.close()

    if not student:
        return redirect(url_for('main.dashboard'))

    if form.validate_on_submit():
        record_date = form.record_date.data
        subject = form.subject.data
        description = form.description.data

        conn = get_db()
        if conn:
            cursor = conn.cursor()
            try:
                # 插入欠交功課記錄
                cursor.execute(
                    "INSERT INTO incomplete_homework_records (student_id, record_date, subject, description, recorded_by_user_id) VALUES (%s, %s, %s, %s, %s)",
                    (student_id, record_date, subject, description, current_user.get_id())
                )
                conn.commit()

                # 更新學生欠交功課計數
                cursor.execute("UPDATE students SET incomplete_homework_count = incomplete_homework_count + 1 WHERE student_id = %s", (student_id,))
                conn.commit()

                flash('欠交功課記錄已成功添加', 'success')
                return redirect(url_for('main.view_records', student_id=student_id))
            except mysql.connector.Error as err:
                conn.rollback()
                flash(f"資料庫錯誤: {err}", 'danger')
                current_app.logger.error(f"資料庫錯誤 (記錄欠交功課): {err}")
            finally:
                if conn and conn.is_connected():
                     cursor.close()
                     conn.close()
        else:
            flash('無法連接到資料庫', 'danger')

    return render_template('record_incomplete_homework.html', title=f'記錄 {student["name"]} 欠交功課', student=student, form=form)


# --- 修改記錄路由 (GET 顯示表單, POST 處理提交) ---

@main_bp.route('/absence/<int:absence_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_absence(absence_id):
    """修改缺席記錄"""
    form = EditAbsenceForm() # 使用表單類

    conn = get_db()
    absence = None
    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            # 獲取缺席記錄及其相關學生資訊
            cursor.execute("SELECT a.*, s.student_id, s.name, s.class_id, c.class_name FROM absences a JOIN students s ON a.student_id = s.student_id JOIN classes c ON s.class_id = c.class_id WHERE a.absence_id = %s", (absence_id,))
            absence = cursor.fetchone()

            if absence:
                # 檢查使用者是否有權限修改此記錄
                has_permission = False
                if current_user.is_admin() or current_user.is_supervisor():
                     has_permission = True
                elif current_user.is_teacher():
                     # 使用 User 模型中實現的方法
                     if any(c['class_id'] == absence['class_id'] for c in current_user.assigned_classes):
                          has_permission = True

                if not has_permission:
                    flash('您無權修改此記錄', 'danger')
                    if conn and conn.is_connected():
                        cursor.close()
                        conn.close()
                    return redirect(url_for('main.dashboard'))
                # 主管和管理員可以修改所有記錄，無需額外檢查班級

            else:
                flash('找不到該缺席記錄', 'danger')
                if conn and conn.is_connected():
                     cursor.close()
                     conn.close()
                return redirect(url_for('main.dashboard'))

        except mysql.connector.Error as err:
            flash(f"資料庫錯誤: {err}", 'danger')
            current_app.logger.error(f"資料庫錯誤 (修改缺席 - 獲取記錄): {err}")
        finally:
            if conn and conn.is_connected():
                 cursor.close()
                 conn.close()

    if not absence:
        return redirect(url_for('main.dashboard'))

    # 如果是 GET 請求，用現有資料填充表單
    if request.method == 'GET':
         form.absence_date.data = absence['absence_date']
         form.session_count.data = absence['session_count']
         form.absence_type.data = absence['type']
         form.reason.data = absence['reason']


    if form.validate_on_submit():
        absence_date = form.absence_date.data
        session_count = form.session_count.data
        absence_type = form.absence_type.data
        reason = form.reason.data
        uploaded_file = form.proof.data # 獲取新的上傳文件
        # 獲取刪除證明文件的標誌，從隱藏欄位或 checkbox 獲取
        delete_proof = request.form.get('delete_proof_flag') == '1' # 假設模板中有一個隱藏欄位或 checkbox 名稱為 delete_proof_flag


        upload_path = absence['upload_path'] # 預設保留原來的路徑

        # 處理文件刪除 (如果在模板中勾選了刪除)
        if delete_proof and absence['upload_path']:
            old_file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], absence['upload_path'])
            if os.path.exists(old_file_path):
                try:
                    os.remove(old_file_path)
                    flash('原證明文件已刪除', 'info')
                    upload_path = None # 將資料庫中的路徑設為 None
                except OSError as e:
                    flash(f"刪除原證明文件失敗: {e}", 'danger')
                    current_app.logger.error(f"刪除原證明文件失敗: {e}")


        # 處理新的文件上傳
        if uploaded_file and uploaded_file.filename:
            # 修正：直接使用從 config 導入的 allowed_file 函式
            if allowed_file(uploaded_file.filename):
                 # 如果有新文件上傳且原文件未刪除 (或者原文件已在上面步驟中刪除)
                 # 這裡不再需要檢查 absence['upload_path'] and not delete_proof
                 # 因為如果勾選了刪除，upload_path 已經設為 None，如果沒勾選，就直接替換

                 # 根據班級獲取或創建上傳子目錄
                 class_upload_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], str(absence['class_id'])) # 使用 class_id 作為文件夾名稱
                 if not os.path.exists(class_upload_folder):
                     os.makedirs(class_upload_folder)

                 filename = secure_filename(uploaded_file.filename)
                 file_base, file_ext = os.path.splitext(filename)
                 timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                 unique_filename = f"{file_base}_{timestamp}{file_ext}"
                 file_save_path = os.path.join(class_upload_folder, unique_filename)
                 try:
                     uploaded_file.save(file_save_path)
                     upload_path = os.path.join(str(absence['class_id']), unique_filename).replace('\\', '/') # 儲存相對於 UPLOAD_FOLDER 的路徑
                 except Exception as e:
                      flash(f"新文件上傳失敗: {e}", 'danger')
                      current_app.logger.error(f"新文件上傳失敗: {e}")
                      # 重新渲染表單時需要傳遞 absence 對象
                      return render_template('edit_absence.html', title=f'修改缺席記錄 ({absence["name"]})', absence=absence, form=form)


            else:
                 flash('不允許的文件類型', 'danger')
                 # 重新渲染表單時需要傳遞 absence 對象
                 return render_template('edit_absence.html', title=f'修改缺席記錄 ({absence["name"]})', absence=absence, form=form)


        conn = get_db()
        if conn:
            cursor = conn.cursor()
            try:
                # 更新缺席記錄到資料庫
                cursor.execute(
                    "UPDATE absences SET absence_date = %s, session_count = %s, type = %s, reason = %s, upload_path = %s WHERE absence_id = %s",
                    (absence_date, session_count, absence_type, reason, upload_path, absence_id)
                )
                conn.commit()
                flash('缺席記錄已成功更新', 'success')
                # 重定向到學生記錄查看頁面
                return redirect(url_for('main.view_records', student_id=absence['student_id']))
            except mysql.connector.Error as err:
                conn.rollback() # 回滾事務
                flash(f"資料庫錯誤: {err}", 'danger')
                current_app.logger.error(f"資料庫錯誤 (更新缺席): {err}")
            finally:
                if conn and conn.is_connected():
                     cursor.close()
                     conn.close()
        else:
            flash('無法連接到資料庫', 'danger')

    # GET 請求或 POST 失敗時渲染表單
    # 在 GET 請求時，需要將現有的 upload_path 傳遞給模板以顯示文件信息
    return render_template('edit_absence.html', title=f'修改缺席記錄 ({absence["name"]})', absence=absence, form=form)

# 修改獎懲記錄路由
@main_bp.route('/award_punishment/<int:record_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_award_punishment(record_id):
    """修改獎懲記錄"""
    form = EditAwardPunishForm()

    conn = get_db()
    award_punishment = None
    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT ap.*, s.student_id, s.name, s.class_id, c.class_name FROM awards_punishments ap JOIN students s ON ap.student_id = s.student_id JOIN classes c ON s.class_id = c.class_id WHERE ap.record_id = %s", (record_id,))
            award_punishment = cursor.fetchone()

            if award_punishment:
                 # 檢查使用者是否有權限修改此記錄
                 has_permission = False
                 if current_user.is_admin() or current_user.is_supervisor():
                      has_permission = True
                 elif current_user.is_teacher():
                      # 使用 User 模型中實現的方法
                      if any(c['class_id'] == award_punishment['class_id'] for c in current_user.assigned_classes):
                           has_permission = True

                 if not has_permission:
                      flash('您無權修改此記錄', 'danger')
                      if conn and conn.is_connected():
                           cursor.close()
                           conn.close()
                      return redirect(url_for('main.dashboard'))
            else:
                 flash('找不到該獎懲記錄', 'danger')
                 if conn and conn.is_connected():
                      cursor.close()
                      conn.close()
                 return redirect(url_for('main.dashboard'))

        except mysql.connector.Error as err:
             flash(f"資料庫錯誤: {err}", 'danger')
             current_app.logger.error(f"資料庫錯誤 (修改獎懲 - 獲取記錄): {err}")
        finally:
             if conn and conn.is_connected():
                  cursor.close()
                  conn.close()

    if not award_punishment:
        return redirect(url_for('main.dashboard'))

    # 如果是 GET 請求，用現有資料填充表單
    if request.method == 'GET':
         form.record_date.data = award_punishment['record_date']
         form.record_type.data = award_punishment['type']
         form.description.data = award_punishment['description']

    if form.validate_on_submit():
        record_date = form.record_date.data
        record_type = form.record_type.data
        description = form.description.data
        uploaded_file = form.proof.data
        delete_proof = request.form.get('delete_proof_flag') == '1' # 假設模板中有一個隱藏欄位或 checkbox 名稱為 delete_proof_flag

        upload_path = award_punishment['upload_path']

        # 處理文件刪除
        if delete_proof and award_punishment['upload_path']:
            old_file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], award_punishment['upload_path'])
            if os.path.exists(old_file_path):
                try:
                    os.remove(old_file_path)
                    flash('原證明文件已刪除', 'info')
                    upload_path = None
                except OSError as e:
                     flash(f"刪除原證明文件失敗: {e}", 'danger')
                     current_app.logger.error(f"刪除原證明文件失敗: {e}")


        # 處理新的文件上傳
        if uploaded_file and uploaded_file.filename:
            # 修正：直接使用從 config 導入的 allowed_file 函式
            if allowed_file(uploaded_file.filename):
                 # 如果有新文件上傳且原文件未刪除 (或者原文件已在上面步驟中刪除)
                 # 這裡不再需要檢查 award_punishment['upload_path'] and not delete_proof

                 class_upload_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], str(award_punishment['class_id']))
                 if not os.path.exists(class_upload_folder):
                     os.makedirs(class_upload_folder)

                 filename = secure_filename(uploaded_file.filename)
                 file_base, file_ext = os.path.splitext(filename)
                 timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                 unique_filename = f"{file_base}_{timestamp}{file_ext}"
                 file_save_path = os.path.join(class_upload_folder, unique_filename)
                 try:
                     uploaded_file.save(file_save_path)
                     upload_path = os.path.join(str(award_punishment['class_id']), unique_filename).replace('\\', '/')
                 except Exception as e:
                     flash(f"新文件上傳失敗: {e}", 'danger')
                     current_app.logger.error(f"新文件上傳失敗: {e}")
                     return render_template('edit_award_punish.html', title=f'修改獎懲記錄 ({award_punishment["name"]})', award_punishment=award_punishment, form=form)
            else:
                 flash('不允許的文件類型', 'danger')
                 return render_template('edit_award_punish.html', title=f'修改獎懲記錄 ({award_punishment["name"]})', award_punishment=award_punishment, form=form)


        conn = get_db()
        if conn:
            cursor = conn.cursor()
            try:
                # 在更新前，需要先撤銷舊記錄對點數的影響 (如果需要的話)
                # 然後根據新的記錄類型重新計算並應用點數變化。
                # 這樣才能正確反映點數的變化。

                # 撤銷舊點數影響
                old_type = award_punishment['type']
                old_student_id = award_punishment['student_id']
                if old_type in ['優點', '小功', '大功']:
                     old_points = {'優點': 1, '小功': 3, '大功': 9}.get(old_type, 0)
                     cursor.execute("UPDATE students SET award_points = award_points - %s WHERE student_id = %s", (old_points, old_student_id))
                     conn.commit()
                elif old_type in ['警告', '缺點', '小過', '大過']:
                     old_points = {'警告': 0, '缺點': 1, '小過': 3, '大過': 9}.get(old_type, 0)
                     cursor.execute("UPDATE students SET violation_points = violation_points - %s WHERE student_id = %s", (old_points, old_student_id))
                     conn.commit()

                # 更新記錄內容
                cursor.execute(
                    "UPDATE awards_punishments SET record_date = %s, type = %s, description = %s, upload_path = %s WHERE record_id = %s",
                    (record_date, record_type, description, upload_path, record_id)
                )
                conn.commit()

                # 應用新點數影響
                if record_type in ['優點', '小功', '大功']:
                     new_points = {'優點': 1, '小功': 3, '大功': 9}.get(record_type, 0)
                     cursor.execute("UPDATE students SET award_points = award_points + %s WHERE student_id = %s", (new_points, award_punishment['student_id']))
                     conn.commit()
                elif record_type in ['警告', '缺點', '小過', '大過']:
                     new_points = {'警告': 0, '缺點': 1, '小過': 3, '大過': 9}.get(record_type, 0)
                     cursor.execute("UPDATE students SET violation_points = violation_points + %s WHERE student_id = %s", (new_points, award_punishment['student_id']))
                     conn.commit()


                flash('獎懲記錄已成功更新', 'success')
                return redirect(url_for('main.view_records', student_id=award_punishment['student_id']))
            except mysql.connector.Error as err:
                conn.rollback()
                flash(f"資料庫錯誤: {err}", 'danger')
                current_app.logger.error(f"資料庫錯誤 (更新獎懲): {err}")
            finally:
                if conn and conn.is_connected():
                     cursor.close()
                     conn.close()
        else:
            flash('無法連接到資料庫', 'danger')

    # GET 請求或 POST 失敗時渲染表單
    # 在 GET 請求時，需要將現有的 upload_path 傳遞給模板以顯示文件信息
    return render_template('edit_award_punish.html', title=f'修改獎懲記錄 ({award_punishment["name"]})', award_punishment=award_punishment, form=form)

# 修改參賽記錄路由
@main_bp.route('/competition/<int:comp_record_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_competition(comp_record_id):
    """修改參賽記錄"""
    form = EditCompetitionForm()

    conn = get_db()
    competition = None
    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT c.*, s.student_id, s.name, s.class_id, cl.class_name FROM competitions c JOIN students s ON c.student_id = s.student_id JOIN classes cl ON s.class_id = cl.class_id WHERE c.comp_record_id = %s", (comp_record_id,))
            competition = cursor.fetchone()

            if competition:
                 # 檢查使用者是否有權限修改此記錄
                 has_permission = False
                 if current_user.is_admin() or current_user.is_supervisor():
                      has_permission = True
                 elif current_user.is_teacher():
                      # 使用 User 模型中實現的方法
                      if any(c['class_id'] == competition['class_id'] for c in current_user.assigned_classes):
                           has_permission = True

                 if not has_permission:
                      flash('您無權修改此記錄', 'danger')
                      if conn and conn.is_connected():
                           cursor.close()
                           conn.close()
                      return redirect(url_for('main.dashboard'))
            else:
                 flash('找不到該參賽記錄', 'danger')
                 if conn and conn.is_connected():
                      cursor.close()
                      conn.close()
                 return redirect(url_for('main.dashboard'))

        except mysql.connector.Error as err:
             flash(f"資料庫錯誤: {err}", 'danger')
             current_app.logger.error(f"資料庫錯誤 (修改參賽 - 獲取記錄): {err}")
        finally:
             if conn and conn.is_connected():
                  cursor.close()
                  conn.close()

    if not competition:
        return redirect(url_for('main.dashboard'))

    # 如果是 GET 請求，用現有資料填充表單
    if request.method == 'GET':
         form.comp_date.data = competition['comp_date']
         form.comp_name.data = competition['comp_name']
         form.result.data = competition['result']
         form.description.data = competition['description']


    if form.validate_on_submit():
        comp_date = form.comp_date.data
        comp_name = form.comp_name.data
        result = form.result.data
        description = form.description.data
        uploaded_file = form.proof.data
        delete_proof = request.form.get('delete_proof_flag') == '1' # 假設模板中有一個隱藏欄位或 checkbox 名稱為 delete_proof_flag

        upload_path = competition['upload_path']

        # 處理文件刪除
        if delete_proof and competition['upload_path']:
            old_file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], competition['upload_path'])
            if os.path.exists(old_file_path):
                try:
                    os.remove(old_file_path)
                    flash('原證明文件已刪除', 'info')
                    upload_path = None
                except OSError as e:
                    flash(f"刪除原證明文件失敗: {e}", 'danger')
                    current_app.logger.error(f"刪除原證明文件失敗: {e}")


        # 處理新的文件上傳
        if uploaded_file and uploaded_file.filename:
            # 修正：直接使用從 config 導入的 allowed_file 函式
            if allowed_file(uploaded_file.filename):
                 # 如果有新文件上傳且原文件未刪除 (或者原文件已在上面步驟中刪除)
                 # 這裡不再需要檢查 competition['upload_path'] and not delete_proof

                 class_upload_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], str(competition['class_id']))
                 if not os.path.exists(class_upload_folder):
                     os.makedirs(class_upload_folder)

                 filename = secure_filename(uploaded_file.filename)
                 file_base, file_ext = os.path.splitext(filename)
                 timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                 unique_filename = f"{file_base}_{timestamp}{file_ext}"
                 file_save_path = os.path.join(class_upload_folder, unique_filename)
                 try:
                     uploaded_file.save(file_save_path)
                     upload_path = os.path.join(str(competition['class_id']), unique_filename).replace('\\', '/')
                 except Exception as e:
                     flash(f"新文件上傳失敗: {e}", 'danger')
                     current_app.logger.error(f"新文件上傳失敗: {e}")
                     return render_template('edit_competition.html', title=f'修改參賽記錄 ({competition["name"]})', competition=competition, form=form)
            else:
                 flash('不允許的文件類型', 'danger')
                 return render_template('edit_competition.html', title=f'修改參賽記錄 ({competition["name"]})', competition=competition, form=form)


        conn = get_db()
        if conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "UPDATE competitions SET comp_date = %s, comp_name = %s, result = %s, description = %s, upload_path = %s WHERE comp_record_id = %s",
                    (comp_date, comp_name, result, description, upload_path, comp_record_id)
                )
                conn.commit()
                flash('參賽記錄已成功更新', 'success')
                return redirect(url_for('main.view_records', student_id=competition['student_id']))
            except mysql.connector.Error as err:
                conn.rollback()
                flash(f"資料庫錯誤: {err}", 'danger')
                current_app.logger.error(f"資料庫錯誤 (更新參賽): {err}")
            finally:
                if conn and conn.is_connected():
                     cursor.close()
                     conn.close()
        else:
            flash('無法連接到資料庫', 'danger')

    return render_template('edit_competition.html', title=f'修改參賽記錄 ({competition["name"]})', competition=competition, form=form)

# 修改遲到記錄路由
@main_bp.route('/late_record/<int:late_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_late_record(late_id):
    """修改遲到記錄"""
    form = EditLateForm()

    conn = get_db()
    late_record = None
    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT lr.*, s.student_id, s.name, s.class_id FROM late_records lr JOIN students s ON lr.student_id = s.student_id WHERE lr.late_id = %s", (late_id,))
            late_record = cursor.fetchone()

            if late_record:
                 # 檢查使用者是否有權限修改此記錄
                 has_permission = False
                 if current_user.is_admin() or current_user.is_supervisor():
                      has_permission = True
                 elif current_user.is_teacher():
                      # 使用 User 模型中實現的方法
                      if any(c['class_id'] == late_record['class_id'] for c in current_user.assigned_classes):
                           has_permission = True

                 if not has_permission:
                      flash('您無權修改此記錄', 'danger')
                      if conn and conn.is_connected():
                           cursor.close()
                           conn.close()
                      return redirect(url_for('main.dashboard'))
            else:
                 flash('找不到該遲到記錄', 'danger')
                 if conn and conn.is_connected():
                      cursor.close()
                      conn.close()
                 return redirect(url_for('main.dashboard'))

        except mysql.connector.Error as err:
             flash(f"資料庫錯誤: {err}", 'danger')
             current_app.logger.error(f"資料庫錯誤 (修改遲到 - 獲取記錄): {err}")
        finally:
             if conn and conn.is_connected():
                  cursor.close()
                  conn.close()

    if not late_record:
        return redirect(url_for('main.dashboard'))

    # 如果是 GET 請求，用現有資料填充表單
    if request.method == 'GET':
         form.late_date.data = late_record['late_date']
         form.reason.data = late_record['reason']

    if form.validate_on_submit():
        late_date = form.late_date.data
        reason = form.reason.data

        conn = get_db()
        if conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "UPDATE late_records SET late_date = %s, reason = %s WHERE late_id = %s",
                    (late_date, reason, late_id)
                )
                conn.commit()
                flash('遲到記錄已成功更新', 'success')
                return redirect(url_for('main.view_records', student_id=late_record['student_id']))
            except mysql.connector.Error as err:
                conn.rollback()
                flash(f"資料庫錯誤: {err}", 'danger')
                current_app.logger.error(f"資料庫錯誤 (更新遲到): {err}")
            finally:
                if conn and conn.is_connected():
                     cursor.close()
                     conn.close()
        else:
            flash('無法連接到資料庫', 'danger')

    return render_template('edit_late_record.html', title=f'修改遲到記錄 ({late_record["name"]})', late_record=late_record, form=form)

# 修改欠交功課記錄路由
@main_bp.route('/incomplete_homework_record/<int:incomplete_hw_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_incomplete_homework_record(incomplete_hw_id):
    """修改欠交功課記錄"""
    form = EditIncompleteHomeworkForm()

    conn = get_db()
    incomplete_homework_record = None
    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT ihr.*, s.student_id, s.name, s.class_id FROM incomplete_homework_records ihr JOIN students s ON ihr.student_id = s.student_id WHERE ihr.incomplete_hw_id = %s", (incomplete_hw_id,))
            incomplete_homework_record = cursor.fetchone()

            if incomplete_homework_record:
                 # 檢查使用者是否有權限修改此記錄
                 has_permission = False
                 if current_user.is_admin() or current_user.is_supervisor():
                      has_permission = True
                 elif current_user.is_teacher():
                      # 使用 User 模型中實現的方法
                      if any(c['class_id'] == incomplete_homework_record['class_id'] for c in current_user.assigned_classes):
                           has_permission = True

                 if not has_permission:
                      flash('您無權修改此記錄', 'danger')
                      if conn and conn.is_connected():
                           cursor.close()
                           conn.close()
                      return redirect(url_for('main.dashboard'))
            else:
                 flash('找不到該欠交功課記錄', 'danger')
                 if conn and conn.is_connected():
                      cursor.close()
                      conn.close()
                 return redirect(url_for('main.dashboard'))

        except mysql.connector.Error as err:
             flash(f"資料庫錯誤: {err}", 'danger')
             current_app.logger.error(f"資料庫錯誤 (修改欠交功課 - 獲取記錄): {err}")
        finally:
             if conn and conn.is_connected():
                  cursor.close()
                  conn.close()

    if not incomplete_homework_record:
        return redirect(url_for('main.dashboard'))

    # 如果是 GET 請求，用現有資料填充表單
    if request.method == 'GET':
         form.record_date.data = incomplete_homework_record['record_date']
         form.subject.data = incomplete_homework_record['subject']
         form.description.data = incomplete_homework_record['description']

    if form.validate_on_submit():
        record_date = form.record_date.data
        subject = form.subject.data
        description = form.description.data

        conn = get_db()
        if conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "UPDATE incomplete_homework_records SET record_date = %s, subject = %s, description = %s WHERE incomplete_hw_id = %s",
                    (record_date, subject, description, incomplete_hw_id)
                )
                conn.commit()
                flash('欠交功課記錄已成功更新', 'success')
                return redirect(url_for('main.view_records', student_id=incomplete_homework_record['student_id']))
            except mysql.connector.Error as err:
                conn.rollback()
                flash(f"資料庫錯誤: {err}", 'danger')
                current_app.logger.error(f"資料庫錯誤 (更新欠交功課): {err}")
            finally:
                if conn and conn.is_connected():
                     cursor.close()
                     conn.close()
        else:
            flash('無法連接到資料庫', 'danger')

    return render_template('edit_incomplete_homework_record.html', title=f'修改欠交功課記錄 ({incomplete_homework_record["name"]})', incomplete_homework_record=incomplete_homework_record, form=form)


# app/main.py 中找到並替換 delete_absence, delete_award_punishment, delete_competition 這三個函數

# 刪除缺席記錄路由
@main_bp.route('/absence/<int:absence_id>/delete', methods=['POST'])
@login_required
def delete_absence(absence_id):
    """
    刪除缺席記錄。
    需要 absence_id 參數來確定要刪除哪筆記錄。
    只有記錄者本人、主管或管理員可以刪除。
    通過 POST 請求觸發。
    """
    conn = get_db()
    fetched_student_id = None # 初始化用於重定向的學生 ID
    recorded_by_user_id = None # 初始化記錄者使用者 ID
    upload_path = None # 初始化上傳文件路徑

    if conn:
        # 使用非字典游標進行後續的 DELETE 操作
        cursor = conn.cursor()
        try:
            # 1. 獲取記錄資訊以進行權限檢查、獲取 student_id 和 recorded_by_user_id
            # 使用字典游標方便通過欄位名訪問數據
            cursor_dict = conn.cursor(dictionary=True)
            # 修正 SQL 查詢：明確指定欄位來源
            cursor_dict.execute("""
                SELECT a.absence_id, a.student_id, a.upload_path, a.recorded_by_user_id, s.class_id
                FROM absences a
                JOIN students s ON a.student_id = s.student_id
                WHERE a.absence_id = %s
            """, (absence_id,))
            absence_record = cursor_dict.fetchone()
            cursor_dict.close() # 關閉這個臨時的字典游標


            if not absence_record:
                flash('找不到該缺席記錄', 'danger')
                # 如果找不到記錄，學生 ID 未知，重定向到安全頁面
                return redirect(url_for('main.dashboard'))

            # 從獲取的字典中取得數據
            fetched_student_id = absence_record['student_id']
            recorded_by_user_id = absence_record['recorded_by_user_id']
            upload_path = absence_record['upload_path']


            # 2. 檢查權限 (只有記錄者本人、主管或管理員可以刪除)
            # 將使用者 ID 和記錄者 ID 轉換為字串進行比較，以確保類型一致
            if not (str(current_user.get_id()) == str(recorded_by_user_id) or current_user.is_supervisor() or current_user.is_admin()):
                 flash('您沒有權限刪除此記錄。', 'danger')
                 # 重定向回原學生的記錄頁面
                 return redirect(url_for('main.view_records', student_id=fetched_student_id))

            # 3. 刪除相關文件 (如果存在且有權限)
            if upload_path:
                 file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], upload_path)
                 if os.path.exists(file_path):
                     try:
                         os.remove(file_path)
                         # 可以選擇性地在這裡閃現文件刪除成功的訊息
                         # flash('相關證明文件已刪除', 'info')
                     except OSError as e:
                         # 記錄文件刪除失敗的錯誤，但不影響資料庫刪除
                         current_app.logger.error(f"刪除相關證明文件失敗: {e}")
                         flash(f"刪除相關證明文件失敗: {e}", 'warning') # 使用 warning 表示問題，但不阻止主操作


            # 4. 執行資料庫刪除操作 (使用非字典游標)
            cursor.execute("DELETE FROM absences WHERE absence_id = %s", (absence_id,))

            # TODO: (原註解已移除) 重新計算並更新學生的總缺席節數
            # 根據 schema.sql，學生表格沒有 total_absences_sessions 欄位。
            # view_records 頁面會在載入時計算總數。
            # 因此，這裡不需要更新 students 表格的總缺席節數。
            # 如果你希望在 students 表中保留這個總數，你需要修改 schema.sql 添加該欄位，並重新創建或遷移資料庫。
            # 目前的邏輯是刪除記錄並提交。

            # 5. 提交事務
            conn.commit()

            flash('缺席記錄已成功刪除', 'success')

        except mysql.connector.Error as err:
            conn.rollback() # 如果發生錯誤，回滾所有變更
            flash(f"資料庫錯誤 (刪除缺席): {err}", 'danger')
            current_app.logger.error(f"資料庫錯誤 (刪除缺席): {err}")
            # 發生錯誤時，嘗試重定向回學生的記錄頁面或儀表板
            if fetched_student_id: # 如果學生 ID 已知
                return redirect(url_for('main.view_records', student_id=fetched_student_id))
            else:
                # 如果學生 ID 都沒獲取到，重定向到儀表板
                return redirect(url_for('main.dashboard'))

        except Exception as e:
             # 捕獲其他可能的未知錯誤
             conn.rollback() # 回滾
             flash(f"刪除缺席時發生未知錯誤: {e}", 'danger')
             current_app.logger.error(f"未知錯誤 (刪除缺席): {e}")
             if fetched_student_id:
                 return redirect(url_for('main.view_records', student_id=fetched_student_id))
             else:
                 return redirect(url_for('main.dashboard'))

        finally:
            # 確保關閉游標和連接
            if conn and conn.is_connected():
                 cursor.close()
                 conn.close()

    else:
        # 處理資料庫連接失敗的情況
        flash('無法連接到資料庫', 'danger')
        return redirect(url_for('main.dashboard')) # 連接失敗則重定向到儀表板

    # 刪除成功後，重定向回學生的記錄頁面
    # 使用之前獲取的 fetched_student_id
    return redirect(url_for('main.view_records', student_id=fetched_student_id))


# 刪除獎懲記錄路由
@main_bp.route('/award_punishment/<int:record_id>/delete', methods=['POST'])
@login_required
def delete_award_punishment(record_id):
    """
    刪除獎懲記錄，並撤銷對學生點數的影響。
    需要 record_id 參數來確定要刪除哪筆記錄。
    只有記錄者本人、主管或管理員可以刪除。
    通過 POST 請求觸發。
    """
    conn = get_db()
    fetched_student_id = None # 初始化用於重定向的學生 ID
    recorded_by_user_id = None # 初始化記錄者使用者 ID
    upload_path = None # 初始化上傳文件路徑
    record_type = None # 初始化記錄類型

    if conn:
        # 使用非字典游標進行後續的 UPDATE 和 DELETE 操作
        cursor = conn.cursor()
        try:
            # 1. 獲取記錄資訊以進行權限檢查、獲取 student_id、recorded_by_user_id 和記錄類型
            # 使用字典游標方便通過欄位名訪問數據
            cursor_dict = conn.cursor(dictionary=True)
            # 修正 SQL 查詢：明確指定欄位來源並添加 recorded_by_user_id
            cursor_dict.execute("""
                SELECT ap.record_id, ap.student_id, ap.upload_path, ap.type, ap.recorded_by_user_id, s.class_id
                FROM awards_punishments ap
                JOIN students s ON ap.student_id = s.student_id
                WHERE ap.record_id = %s
            """, (record_id,))
            award_punishment_record = cursor_dict.fetchone()
            cursor_dict.close() # 關閉這個臨時的字典游標


            if not award_punishment_record:
                flash('找不到該獎懲記錄', 'danger')
                # 如果找不到記錄，學生 ID 未知，重定向到安全頁面
                return redirect(url_for('main.dashboard'))

            # 從獲取的字典中取得數據
            fetched_student_id = award_punishment_record['student_id']
            recorded_by_user_id = award_punishment_record['recorded_by_user_id']
            upload_path = award_punishment_record['upload_path']
            record_type = award_punishment_record['type']


            # 2. 檢查權限 (只有記錄者本人、主管或管理員可以刪除)
            # 將使用者 ID 和記錄者 ID 轉換為字串進行比較，以確保類型一致
            if not (str(current_user.get_id()) == str(recorded_by_user_id) or current_user.is_supervisor() or current_user.is_admin()):
                 flash('您沒有權限刪除此記錄。', 'danger')
                 # 重定向回原學生的記錄頁面
                 return redirect(url_for('main.view_records', student_id=fetched_student_id))

            # 3. 在刪除記錄前，撤銷對學生點數的影響 (使用非字典游標)
            # 這裡不需要聯接，點數欄位在 students 表中存在
            if record_type in ['優點', '小功', '大功']:
                 points = {'優點': 1, '小功': 3, '大功': 9}.get(record_type, 0)
                 cursor.execute("UPDATE students SET award_points = award_points - %s WHERE student_id = %s", (points, fetched_student_id))
            elif record_type in ['警告', '缺點', '小過', '大過']:
                 points = {'警告': 0, '缺點': 1, '小過': 3, '大過': 9}.get(record_type, 0)
                 cursor.execute("UPDATE students SET violation_points = violation_points - %s WHERE student_id = %s", (points, fetched_student_id))

            # 4. 刪除相關文件 (如果存在且有權限)
            if upload_path:
                 file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], upload_path)
                 if os.path.exists(file_path):
                     try:
                         os.remove(file_path)
                         # 可以選擇性地在這裡閃現文件刪除成功的訊息
                         # flash('相關證明文件已刪除', 'info')
                     except OSError as e:
                         # 記錄文件刪除失敗的錯誤，但不影響資料庫刪除
                         current_app.logger.error(f"刪除相關證明文件失敗: {e}")
                         flash(f"刪除相關證明文件失敗: {e}", 'warning') # 使用 warning 表示問題，但不阻止主操作


            # 5. 刪除資料庫記錄 (使用非字典游標)
            cursor.execute("DELETE FROM awards_punishments WHERE record_id = %s", (record_id,))

            # 6. 提交事務 (所有操作成功後提交一次)
            conn.commit()

            flash('獎懲記錄已成功刪除', 'success')

        except mysql.connector.Error as err:
            conn.rollback() # 如果發生錯誤，回滾所有變更
            flash(f"資料庫錯誤 (刪除獎懲): {err}", 'danger')
            current_app.logger.error(f"資料庫錯誤 (刪除獎懲): {err}")
            # 發生錯誤時，嘗試重定向回學生的記錄頁面或儀表板
            if fetched_student_id: # 如果學生 ID 已知
                return redirect(url_for('main.view_records', student_id=fetched_student_id))
            else:
                # 如果學生 ID 都沒獲取到，重定向到儀表板
                return redirect(url_for('main.dashboard'))

        except Exception as e:
             # 捕獲其他可能的未知錯誤
             conn.rollback() # 回滾
             flash(f"刪除獎懲時發生未知錯誤: {e}", 'danger')
             current_app.logger.error(f"未知錯誤 (刪除獎懲): {e}")
             if fetched_student_id:
                 return redirect(url_for('main.view_records', student_id=fetched_student_id))
             else:
                 return redirect(url_for('main.dashboard'))

        finally:
            # 確保關閉游標和連接
            if conn and conn.is_connected():
                 cursor.close()
                 conn.close()

    else:
        # 處理資料庫連接失敗的情況
        flash('無法連接到資料庫', 'danger')
        return redirect(url_for('main.dashboard')) # 連接失敗則重定向到儀表板

    # 刪除成功後，重定向回學生的記錄頁面
    # 使用之前獲取的 fetched_student_id
    return redirect(url_for('main.view_records', student_id=fetched_student_id))


# 刪除參賽記錄路由
@main_bp.route('/competition/<int:comp_record_id>/delete', methods=['POST'])
@login_required
def delete_competition(comp_record_id):
    """
    刪除參賽記錄。
    需要 comp_record_id 參數來確定要刪除哪筆記錄。
    只有記錄者本人、主管或管理員可以刪除。
    通過 POST 請求觸發。
    """
    conn = get_db()
    fetched_student_id = None # 初始化用於重定向的學生 ID
    recorded_by_user_id = None # 初始化記錄者使用者 ID
    upload_path = None # 初始化上傳文件路徑

    if conn:
        # 使用非字典游標進行後續的 DELETE 操作
        cursor = conn.cursor()
        try:
            # 1. 獲取記錄資訊以進行權限檢查、獲取 student_id 和 recorded_by_user_id
            # 使用字典游標方便通過欄位名訪問數據
            cursor_dict = conn.cursor(dictionary=True)
            # 修正 SQL 查詢：明確指定欄位來源並添加 recorded_by_user_id
            cursor_dict.execute("""
                SELECT c.comp_record_id, c.student_id, c.upload_path, c.recorded_by_user_id, s.class_id
                FROM competitions c
                JOIN students s ON c.student_id = s.student_id
                WHERE c.comp_record_id = %s
            """, (comp_record_id,))
            competition_record = cursor_dict.fetchone()
            cursor_dict.close() # 關閉這個臨時的字典游標


            if not competition_record:
                flash('找不到該參賽記錄', 'danger')
                # 如果找不到記錄，學生 ID 未知，重定向到安全頁面
                return redirect(url_for('main.dashboard'))

            # 從獲取的字典中取得數據
            fetched_student_id = competition_record['student_id']
            recorded_by_user_id = competition_record['recorded_by_user_id']
            upload_path = competition_record['upload_path']


            # 2. 檢查權限 (只有記錄者本人、主管或管理員可以刪除)
            # 將使用者 ID 和記錄者 ID 轉換為字串進行比較，以確保類型一致
            if not (str(current_user.get_id()) == str(recorded_by_user_id) or current_user.is_supervisor() or current_user.is_admin()):
                 flash('您沒有權限刪除此記錄。', 'danger')
                 # 重定向回原學生的記錄頁面
                 return redirect(url_for('main.view_records', student_id=fetched_student_id))

            # 3. 刪除相關文件 (如果存在且有權限)
            if upload_path:
                 file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], upload_path)
                 if os.path.exists(file_path):
                     try:
                         os.remove(file_path)
                         # 可以選擇性地在這裡閃現文件刪除成功的訊息
                         # flash('相關證明文件已刪除', 'info')
                     except OSError as e:
                         # 記錄文件刪除失敗的錯誤，但不影響資料庫刪除
                         current_app.logger.error(f"刪除相關證明文件失敗: {e}")
                         flash(f"刪除相關證明文件失敗: {e}", 'warning') # 使用 warning 表示問題，但不阻止主操作


            # 4. 執行資料庫刪除操作 (使用非字典游標)
            cursor.execute("DELETE FROM competitions WHERE comp_record_id = %s", (comp_record_id,))

            # 這裡不需要更新 students 表格中的任何總數欄位

            # 5. 提交事務
            conn.commit()

            flash('參賽記錄已成功刪除', 'success')

        except mysql.connector.Error as err:
            conn.rollback() # 如果發生錯誤，回滾所有變更
            flash(f"資料庫錯誤 (刪除參賽): {err}", 'danger')
            current_app.logger.error(f"資料庫錯誤 (刪除參賽): {err}")
            # 發生錯誤時，嘗試重定向回學生的記錄頁面或儀表板
            if fetched_student_id: # 如果學生 ID 已知
                return redirect(url_for('main.view_records', student_id=fetched_student_id))
            else:
                # 如果學生 ID 都沒獲取到，重定向到儀表板
                return redirect(url_for('main.dashboard'))

        except Exception as e:
             # 捕獲其他可能的未知錯誤
             conn.rollback() # 回滾
             flash(f"刪除參賽時發生未知錯誤: {e}", 'danger')
             current_app.logger.error(f"未知錯誤 (刪除參賽): {e}")
             if fetched_student_id:
                 return redirect(url_for('main.view_records', student_id=fetched_student_id))
             else:
                 return redirect(url_for('main.dashboard'))

        finally:
            # 確保關閉游標和連接
            if conn and conn.is_connected():
                 cursor.close()
                 conn.close()

    else:
        # 處理資料庫連接失敗的情況
        flash('無法連接到資料庫', 'danger')
        return redirect(url_for('main.dashboard')) # 連接失敗則重定向到儀表板

    # 刪除成功後，重定向回學生的記錄頁面
    # 使用之前獲取的 fetched_student_id
    return redirect(url_for('main.view_records', student_id=fetched_student_id))

# 刪除遲到記錄路由
@main_bp.route('/late_record/<int:late_id>/delete', methods=['POST'])
@login_required
def delete_late_record(late_id):
    """刪除遲到記錄"""
    conn = get_db()
    late_record = None
    student_id = None # 儲存學生 ID 以便重定向

    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT lr.late_id, lr.student_id, s.class_id FROM late_records lr JOIN students s ON lr.student_id = s.student_id WHERE lr.late_id = %s", (late_id,))
            late_record = cursor.fetchone()

            if late_record:
                 student_id = late_record['student_id'] # 儲存學生 ID

                 # 檢查使用者是否有權限刪除此記錄
                 has_permission = False
                 if current_user.is_admin() or current_user.is_supervisor():
                      has_permission = True
                 elif current_user.is_teacher():
                      # 使用 User 模型中實現的方法
                      if any(c['class_id'] == late_record['class_id'] for c in current_user.assigned_classes):
                           has_permission = True

                 if not has_permission:
                      flash('您無權刪除此記錄', 'danger')
                      if conn and conn.is_connected():
                           cursor.close()
                           conn.close()
                      return redirect(url_for('main.dashboard'))

                 # 刪除資料庫記錄
                 cursor.execute("DELETE FROM late_records WHERE late_id = %s", (late_id,))
                 conn.commit()

                 # 更新學生遲到計數 (減少1)
                 cursor.execute("UPDATE students SET late_count = late_count - 1 WHERE student_id = %s", (student_id,))
                 conn.commit()

                 flash('遲到記錄已成功刪除', 'success')
                 return redirect(url_for('main.view_records', student_id=student_id))

            else:
                flash('找不到該遲到記錄', 'danger')

        except mysql.connector.Error as err:
            conn.rollback()
            flash(f"資料庫錯誤: {err}", 'danger')
            current_app.logger.error(f"資料庫錯誤 (刪除遲到): {err}")
        finally:
            if conn and conn.is_connected():
                 cursor.close()
                 conn.close()

    if student_id:
         return redirect(url_for('main.view_records', student_id=student_id))
    return redirect(url_for('main.dashboard')) # 如果找不到記錄或發生錯誤，嘗試重定向到學生記錄頁面 (如果學生 ID 已知)，否則到儀表板

# 刪除欠交功課記錄路由
@main_bp.route('/incomplete_homework_record/<int:incomplete_hw_id>/delete', methods=['POST'])
@login_required
def delete_incomplete_homework_record(incomplete_hw_id):
    """刪除欠交功課記錄"""
    conn = get_db()
    incomplete_homework_record = None
    student_id = None # 儲存學生 ID 以便重定向

    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT ihr.incomplete_hw_id, ihr.student_id, s.class_id FROM incomplete_homework_records ihr JOIN students s ON ihr.student_id = s.student_id WHERE incomplete_hw_id = %s", (incomplete_hw_id,))
            incomplete_homework_record = cursor.fetchone()

            if incomplete_homework_record:
                 student_id = incomplete_homework_record['student_id'] # 儲存學生 ID

                 # 檢查使用者是否有權限刪除此記錄
                 has_permission = False
                 if current_user.is_admin() or current_user.is_supervisor():
                      has_permission = True
                 elif current_user.is_teacher():
                      # 使用 User 模型中實現的方法
                      if any(c['class_id'] == incomplete_homework_record['class_id'] for c in current_user.assigned_classes):
                           has_permission = True

                 if not has_permission:
                      flash('您無權刪除此記錄', 'danger')
                      if conn and conn.is_connected():
                           cursor.close()
                           conn.close()
                      return redirect(url_for('main.dashboard'))

                 # 刪除資料庫記錄
                 cursor.execute("DELETE FROM incomplete_homework_records WHERE incomplete_hw_id = %s", (incomplete_hw_id,))
                 conn.commit()

                 # 更新學生欠交功課計數 (減少1)
                 cursor.execute("UPDATE students SET incomplete_homework_count = incomplete_homework_count - 1 WHERE student_id = %s", (student_id,))
                 conn.commit()

                 flash('欠交功課記錄已成功刪除', 'success')
                 return redirect(url_for('main.view_records', student_id=student_id))

            else:
                flash('找不到該欠交功課記錄', 'danger')

        except mysql.connector.Error as err:
            conn.rollback()
            flash(f"資料庫錯誤: {err}", 'danger')
            current_app.logger.error(f"資料庫錯誤 (刪除欠交功課): {err}")
        finally:
            if conn and conn.is_connected():
                 cursor.close()
                 conn.close()

    if student_id:
         return redirect(url_for('main.view_records', student_id=student_id))
    return redirect(url_for('main.dashboard')) # 如果找不到記錄或發生錯誤，嘗試重定向到學生記錄頁面 (如果學生 ID 已知)，否則到儀表板


# 查看上傳文件路由
@main_bp.route('/uploads/<path:filename>')
@login_required
def uploaded_file(filename):
    """安全地提供上傳的文件"""
    # filename 格式預期是 <class_id>/<unique_filename>
    try:
        class_id_str, unique_filename = filename.split('/', 1)
        class_id = int(class_id_str)
    except ValueError:
        # 如果文件名格式不正確，返回 404
        abort(404)
        return # abort 已經會終止請求，這裡的 return 只是為了明確流程

    conn = get_db()
    has_permission = False

    if conn:
        cursor = conn.cursor()
        try:
            # 檢查使用者是否有權限訪問這個班級的文件
            if current_user.is_admin() or current_user.is_supervisor():
                 has_permission = True
            elif current_user.is_teacher():
                 # 檢查教師是否負責此班級
                 # 使用 User 模型中實現的方法
                 if any(c['class_id'] == class_id for c in current_user.assigned_classes):
                      has_permission = True

            # 可以選擇添加一個額外的檢查，確保文件路徑存在於資料庫的某個記錄中
            # 這可以防止使用者猜測文件路徑來訪問未經授權的文件
            # 例如：
            # cursor.execute("SELECT 1 FROM absences WHERE upload_path = %s AND student_id IN (SELECT student_id FROM students WHERE class_id = %s)", (filename, class_id))
            # if cursor.fetchone():
            #     # 文件路徑存在且屬於該班級，進一步檢查使用者權限
            #     # (權限檢查已經在上面實現)
            #     pass
            # else:
            #     # 文件路徑不存在於資料庫中，或者不屬於該班級
            #     has_permission = False # 如果文件路徑不存在於資料庫中，無論角色是什麼都拒絕訪問

        except mysql.connector.Error as err:
             current_app.logger.error(f"資料庫錯誤 (檢查文件訪問權限): {err}")
             # 發生資料庫錯誤時，出於安全考慮，預設為無權限
             has_permission = False
        finally:
             if conn and conn.is_connected():
                  cursor.close()
                  conn.close()

    if not has_permission:
        # 如果沒有權限，返回 403 Forbidden
        abort(403)
        return # abort 已經會終止請求，這裡的 return 只是為了明確流程

    try:
        # 使用 send_from_directory 安全地提供文件
        # directory 應該是 UPLOAD_FOLDER 的根目錄， filename 則是相對於該目錄的路徑 (包含 class_id)
        return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)
    except FileNotFoundError:
        # 如果文件不存在，返回 404
        abort(404)
        return # abort 已經會終止請求，這裡的 return 只是為了明確流程

# 修改密碼路由 (使用者自己修改) - 保留此路由，但從 header 移除連結
@main_bp.route('/account/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    """使用者修改自己的密碼"""
    form = ChangePasswordForm()

    if form.validate_on_submit():
        current_password = form.current_password.data
        new_password = form.new_password.data

        conn = get_db()
        user = None
        if conn:
            cursor = conn.cursor(dictionary=True)
            try:
                # 獲取當前使用者資料以檢查舊密碼
                cursor.execute("SELECT * FROM users WHERE user_id = %s", (current_user.get_id(),))
                user_data = cursor.fetchone()
                if user_data:
                     user = User(user_data) # 創建 User 對象

                     if user.check_password(current_password):
                          # 舊密碼正確，更新密碼
                          hashed_password = generate_password_hash(new_password)
                          cursor.execute("UPDATE users SET password_hash = %s WHERE user_id = %s", (hashed_password, current_user.get_id()))
                          conn.commit()
                          flash('您的密碼已成功修改', 'success')
                          # 修改密碼後通常建議重新登入
                          logout_user()
                          return redirect(url_for('auth.login'))
                     else:
                          flash('舊密碼不正確', 'danger')
                else:
                     # 理論上不應該發生，因為使用者已經登入
                     flash('找不到您的使用者帳號', 'danger')
                     logout_user()
                     return redirect(url_for('auth.login'))

            except mysql.connector.Error as err:
                conn.rollback()
                flash(f"資料庫錯誤: {err}", 'danger')
                current_app.logger.error(f"資料庫錯誤 (修改密碼): {err}")
            finally:
                if conn and conn.is_connected():
                     cursor.close()
                     conn.close()
        else:
            flash('無法連接到資料庫', 'danger')


    return render_template('change_password.html', title='修改密碼', form=form)

# 查看帳號資料路由
@main_bp.route('/account/info')
@login_required
def account_info():
    """查看當前登入使用者的帳號資料"""
    # 帳號資料直接從 current_user 對象獲取
    # current_user 現在已經包含了 teacher_name 和 id_card_number
    return render_template('account_info.html', title='帳號資料')


# --- 新增的主管查看所有記錄的路由 ---

@main_bp.route('/supervisor/absences')
@login_required
def view_all_absences():
    """主管查看所有缺席記錄"""
    # 檢查使用者是否為主管
    if not current_user.is_supervisor():
        flash('您沒有權限訪問此頁面。', 'danger')
        return redirect(url_for('main.index')) # 或其他無權限頁面

    conn = get_db()
    all_absences = []
    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            # 查詢所有缺席記錄，並關聯學生和班級信息以便顯示
            cursor.execute("""
                SELECT a.*, s.student_number, s.name AS student_name, c.class_name
                FROM absences a
                JOIN students s ON a.student_id = s.student_id
                JOIN classes c ON s.class_id = c.class_id
                ORDER BY a.absence_date DESC, a.recorded_at DESC
            """)
            all_absences = cursor.fetchall()

        except mysql.connector.Error as err:
            flash(f"資料庫錯誤: {err}", 'danger')
            current_app.logger.error(f"資料庫錯誤 (主管查看所有缺席): {err}")
        finally:
            if conn and conn.is_connected():
                 cursor.close()
                 conn.close()

    # 渲染模板並傳遞數據
    return render_template('view_all_absences.html', title='所有缺席記錄', absences=all_absences)

@main_bp.route('/supervisor/awards_punishments')
@login_required
def view_all_awards_punishments():
    """主管查看所有獎懲記錄"""
    # 檢查使用者是否為主管
    if not current_user.is_supervisor():
        flash('您沒有權限訪問此頁面。', 'danger')
        return redirect(url_for('main.index'))

    conn = get_db()
    all_awards_punishments = []
    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            # 查詢所有獎懲記錄，並關聯學生和班級信息以便顯示
            cursor.execute("""
                SELECT ap.*, s.student_number, s.name AS student_name, c.class_name
                FROM awards_punishments ap
                JOIN students s ON ap.student_id = s.student_id
                JOIN classes c ON s.class_id = c.class_id
                ORDER BY ap.record_date DESC, ap.recorded_at DESC
            """)
            all_awards_punishments = cursor.fetchall()

        except mysql.connector.Error as err:
            flash(f"資料庫錯誤: {err}", 'danger')
            current_app.logger.error(f"資料庫錯誤 (主管查看所有獎懲): {err}")
        finally:
            if conn and conn.is_connected():
                 cursor.close()
                 conn.close()

    # 渲染模板並傳遞數據
    return render_template('view_all_awards_punishments.html', title='所有獎懲記錄', awards_punishments=all_awards_punishments)

@main_bp.route('/supervisor/competitions')
@login_required
def view_all_competitions():
    """主管查看所有參賽記錄"""
    # 檢查使用者是否為主管
    if not current_user.is_supervisor():
        flash('您沒有權限訪問此頁面。', 'danger')
        return redirect(url_for('main.index'))

    conn = get_db()
    all_competitions = []
    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            # 查詢所有參賽記錄，並關聯學生和班級信息以便顯示
            cursor.execute("""
                SELECT comp.*, s.student_number, s.name AS student_name, c.class_name
                FROM competitions comp
                JOIN students s ON comp.student_id = s.student_id
                JOIN classes c ON s.class_id = c.class_id
                ORDER BY comp.comp_date DESC, comp.recorded_at DESC
            """)
            all_competitions = cursor.fetchall()

        except mysql.connector.Error as err:
            flash(f"資料庫錯誤: {err}", 'danger')
            current_app.logger.error(f"資料庫錯誤 (主管查看所有參賽): {err}")
        finally:
            if conn and conn.is_connected():
                 cursor.close()
                 conn.close()

    # 渲染模板並傳遞數據
    return render_template('view_all_competitions.html', title='所有參賽記錄', competitions=all_competitions)

@main_bp.route('/supervisor/lates')
@login_required
def view_all_lates():
    """主管查看所有遲到記錄"""
    # 檢查使用者是否為主管
    if not current_user.is_supervisor():
        flash('您沒有權限訪問此頁面。', 'danger')
        return redirect(url_for('main.index'))

    conn = get_db()
    all_lates = []
    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            # 查詢所有遲到記錄，並關聯學生和班級信息以便顯示
            cursor.execute("""
                SELECT lr.*, s.student_number, s.name AS student_name, c.class_name
                FROM late_records lr
                JOIN students s ON lr.student_id = s.student_id
                JOIN classes c ON s.class_id = c.class_id
                ORDER BY lr.late_date DESC, lr.recorded_at DESC
            """)
            all_lates = cursor.fetchall()

        except mysql.connector.Error as err:
            flash(f"資料庫錯誤: {err}", 'danger')
            current_app.logger.error(f"資料庫錯誤 (主管查看所有遲到): {err}")
        finally:
            if conn and conn.is_connected():
                 cursor.close()
                 conn.close()

    # 渲染模板並傳遞數據
    return render_template('view_all_lates.html', title='所有遲到記錄', lates=all_lates)

@main_bp.route('/supervisor/incomplete_homeworks')
@login_required
def view_all_incomplete_homeworks():
    """主管查看所有欠交功課記錄"""
    # 檢查使用者是否為主管
    if not current_user.is_supervisor():
        flash('您沒有權限訪問此頁面。', 'danger')
        return redirect(url_for('main.index'))

    conn = get_db()
    all_incomplete_homeworks = []
    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            # 查詢所有欠交功課記錄，並關聯學生和班級信息以便顯示
            cursor.execute("""
                SELECT ihr.*, s.student_number, s.name AS student_name, c.class_name
                FROM incomplete_homework_records ihr
                JOIN students s ON ihr.student_id = s.student_id
                JOIN classes c ON s.class_id = c.class_id
                ORDER BY ihr.record_date DESC, ihr.recorded_at DESC
            """)
            all_incomplete_homeworks = cursor.fetchall()

        except mysql.connector.Error as err:
            flash(f"資料庫錯誤: {err}", 'danger')
            current_app.logger.error(f"資料庫錯誤 (主管查看所有欠交功課): {err}")
        finally:
            if conn and conn.is_connected():
                 cursor.close()
                 conn.close()

    # 渲染模板並傳遞數據
    return render_template('view_all_incomplete_homeworks.html', title='所有欠交功課記錄', incomplete_homeworks=all_incomplete_homeworks)


@main_bp.route('/supervisor/classes')
@login_required
def view_all_classes():
    """主管查看所有班級列表"""
    # 檢查使用者是否為主管
    if not current_user.is_supervisor():
        flash('您沒有權限訪問此頁面。', 'danger')
        return redirect(url_for('main.index'))

    conn = get_db()
    all_classes = []
    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            # 查詢所有班級
            cursor.execute("SELECT class_id, class_name FROM classes ORDER BY class_name")
            all_classes = cursor.fetchall()

        except mysql.connector.Error as err:
            flash(f"資料庫錯誤: {err}", 'danger')
            current_app.logger.error(f"資料庫錯誤 (主管查看所有班級): {err}")
        finally:
            if conn and conn.is_connected():
                 cursor.close()
                 conn.close()

    # 渲染模板並傳遞數據
    return render_template('view_all_classes.html', title='所有班級列表', classes=all_classes)


# 錯誤處理路由
@main_bp.app_errorhandler(403)
def forbidden(e):
    """處理 403 Forbidden 錯誤"""
    return render_template('errors/403.html'), 403

@main_bp.app_errorhandler(404)
def page_not_found(e):
    """處理 404 Not Found 錯誤"""
    return render_template('errors/404.html'), 404

# 您可以在這裡添加其他錯誤處理函式 (例如 500 內部伺服器錯誤)
