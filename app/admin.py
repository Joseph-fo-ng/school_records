# app/admin.py
import os
import csv
from io import StringIO # 導入 StringIO 用於處理處理 CSV 數據
# 修正導入：將 send_response 替換為 send_file
from flask import render_template, request, redirect, url_for, flash, Blueprint, current_app, send_file # 導入 send_file
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
# 導入 config 以使用 UPLOAD_FOLDER 和 allowed_file
import config
from app.__init__ import get_db # 導入資料庫連接函式
from app.models import User # 導入 User 模型
# 修正導入方式，確保從 app.forms 導入所有需要的表單類
from app.forms import (
    AddUserForm, EditUserForm, AddStudentForm, EditStudentForm,
    AddClassForm, EditClassForm, CSVUploadForm, AssignedClassForm # 確保導入 AssignedClassForm
)
import mysql.connector # 導入 MySQL 連接庫
from datetime import datetime # 導入 datetime 模組
# 導入 functools 以使用 wraps 裝飾器
from functools import wraps


# 定義管理員藍圖
bp = Blueprint('admin', __name__, url_prefix='/admin') # 將藍圖命名為 bp 以符合註冊習慣

# 權限檢查裝飾器 (確保只有管理員可以訪問)
def admin_required(f):
    """自定義裝飾器，要求使用者必須是管理員"""
    # 使用 functools.wraps 來保留原始函式的元數據
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            flash('您無權訪問此頁面', 'danger')
            return redirect(url_for('main.dashboard')) # 重定向到主儀表板或其他合適的頁面
        return f(*args, **kwargs)
    return decorated_function


# --- 管理員儀表板 ---
@bp.route('/')
@login_required
@admin_required # 使用自定義裝飾器進行權限檢查
def admin_dashboard():
    """管理員儀表板"""
    # 這裡只渲染模板，管理選項按鈕在模板中定義
    return render_template('admin/admin_dashboard.html', title='管理員儀表板')


# --- 使用者管理 ---
@bp.route('/users')
@login_required
@admin_required
def manage_users():
    """管理使用者帳號列表"""
    conn = get_db()
    users = []
    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            # 獲取所有使用者列表及其分配的班級名稱 (如果有的話)
            # 使用 GROUP_CONCAT 來合併教師負責的多個班級名稱
            cursor.execute("""
                SELECT u.user_id, u.username, u.role, u.teacher_name, u.id_card_number,
                       GROUP_CONCAT(c.class_name ORDER BY c.class_name SEPARATOR ', ') AS assigned_class_names
                FROM users u
                LEFT JOIN teacher_classes tc ON u.user_id = tc.user_id
                LEFT JOIN classes c ON tc.class_id = c.class_id
                GROUP BY u.user_id
                ORDER BY u.role, u.username
            """)
            users = cursor.fetchall()
        except mysql.connector.Error as err:
            flash(f"資料庫錯誤: {err}", 'danger')
            current_app.logger.error(f"資料庫錯誤 (管理使用者列表): {err}")
        finally:
            if conn and conn.is_connected():
                 cursor.close()
                 conn.close()

    return render_template('admin/manage_users.html', title='管理使用者', users=users)

@bp.route('/users/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_user():
    """新增使用者帳號"""
    form = AddUserForm()

    conn = get_db()
    classes = [] # 用於儲存所有班級列表
    # assigned_class_ids 用於在表單驗證失敗時保留已選中的班級
    assigned_class_ids = []

    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            # 獲取所有班級列表供分配
            cursor.execute("SELECT class_id, class_name FROM classes ORDER BY class_name")
            classes = cursor.fetchall()
        except mysql.connector.Error as err:
            flash(f"資料庫錯誤: {err}", 'danger')
            current_app.logger.error(f"資料庫錯誤 (新增使用者 - 獲取班級): {err}")
        finally:
            # 這裡不關閉連接，因為 POST 請求時還會用到
            pass # 保持連接開啟，直到請求結束或在 POST 處理中關閉


    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        role = form.role.data
        teacher_name = form.teacher_name.data if role == 'teacher' else None # 只有教師角色才儲存教師姓名
        id_card_number = form.id_card_number.data

        # 獲取使用者選擇的班級 ID 列表 (來自 checkbox)
        # request.form.getlist('assigned_classes') 返回的是字串列表，需要轉換為整數
        assigned_class_ids = [int(id) for id in request.form.getlist('assigned_classes')]


        # 雜湊密碼
        hashed_password = generate_password_hash(password)

        if conn: # 使用上面開啟的連接
            cursor = conn.cursor()
            try:
                # 檢查使用者名稱是否已存在
                cursor.execute("SELECT user_id FROM users WHERE username = %s", (username,))
                existing_user = cursor.fetchone()

                if existing_user:
                    flash('使用者名稱已存在，請選擇其他名稱。', 'warning')
                    # 重新渲染模板，並傳回已選中的班級 ID，以便使用者不必重新勾選
                    # assigned_class_ids 已經在上面從 request.form 獲取並轉換為整數列表
                    return render_template('admin/add_user.html', title='新增使用者', form=form, classes=classes, assigned_class_ids=assigned_class_ids)

                # 插入新使用者到資料庫
                cursor.execute(
                    "INSERT INTO users (username, password_hash, role, teacher_name, id_card_number) VALUES (%s, %s, %s, %s, %s)",
                    (username, hashed_password, role, teacher_name, id_card_number)
                )
                conn.commit()

                # 獲取剛剛插入的新使用者 ID
                new_user_id = cursor.lastrowid

                # 如果是教師，處理班級與教師的關聯 (teacher_classes 表)
                if role == 'teacher' and assigned_class_ids:
                    # 插入教師與班級的關聯到 teacher_classes 表
                    insert_teacher_classes_sql = "INSERT INTO teacher_classes (user_id, class_id) VALUES (%s, %s)"
                    teacher_classes_values = [(new_user_id, class_id) for class_id in assigned_class_ids]
                    cursor.executemany(insert_teacher_classes_sql, teacher_classes_values)
                    conn.commit() # 提交班級關聯的更改


                flash(f'使用者 "{username}" 已成功新增', 'success')
                return redirect(url_for('admin.manage_users'))
            except mysql.connector.Error as err:
                conn.rollback() # 發生錯誤時回滾
                flash(f"資料庫錯誤: {err}", 'danger')
                current_app.logger.error(f"資料庫錯誤 (新增使用者): {err}")
            finally:
                 if conn and conn.is_connected():
                      cursor.close()
                      conn.close()
        else:
             flash('無法連接到資料庫', 'danger')

    # GET 請求或表單驗證失敗時渲染模板
    # 對於 GET 請求，assigned_class_ids 為空列表 (已初始化)
    # 對於 POST 驗證失敗，assigned_class_ids 來自 request.form (已在上面獲取並轉換)
    return render_template('admin/add_user.html', title='新增使用者', form=form, classes=classes, assigned_class_ids=assigned_class_ids)


@bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    """
    編輯使用者。管理員專用。
    """
    conn = get_db()
    user_data = None
    classes = []
    assigned_class_ids = []
    form = EditUserForm() # Create form instance here

    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            # Fetch the existing user data
            cursor.execute("SELECT user_id, username, role, teacher_name, id_card_number FROM users WHERE user_id = %s", (user_id,))
            user_data = cursor.fetchone()

            if not user_data:
                flash('找不到該使用者', 'danger')
                if conn.is_connected(): cursor.close(); conn.close()
                return redirect(url_for('admin.manage_users'))

            # Fetch all classes for the assigned classes checkbox list
            cursor.execute("SELECT class_id, class_name FROM classes ORDER BY class_name")
            classes_data = cursor.fetchall()
            classes = classes_data # Pass as 'classes' to template


            if request.method == 'GET':
                # On GET, populate the form with existing user data
                form.username.data = user_data['username'] # Populate username (will be read-only)
                form.role.data = user_data['role']
                form.teacher_name.data = user_data.get('teacher_name') # Use .get for optional fields
                form.id_card_number.data = user_data.get('id_card_number') # Use .get for optional fields

                # Fetch currently assigned classes for this user
                # This is needed to check the correct checkboxes in the template
                cursor.execute("SELECT class_id FROM teacher_classes WHERE user_id = %s", (user_id,))
                assigned_classes_data = cursor.fetchall()
                assigned_class_ids = [item['class_id'] for item in assigned_classes_data] # Pass list of IDs to template

            elif request.method == 'POST':
                # On POST, process the submitted form data
                # Note: form.validate_on_submit() will run validators including the custom password validator
                if form.validate_on_submit():
                    try:
                        # Use a non-dictionary cursor for UPDATE/DELETE/INSERT
                        cursor_non_dict = conn.cursor()

                        # Update user's role, teacher_name, id_card_number
                        # Get data directly from form.data to exclude username (which is read-only)
                        update_fields = ['role', 'teacher_name', 'id_card_number']
                        update_query = "UPDATE users SET " + ", ".join([f"{field} = %s" for field in update_fields]) + " WHERE user_id = %s"
                        update_values = [form.data[field] for field in update_fields]
                        update_values.append(user_id)
                        cursor_non_dict.execute(update_query, tuple(update_values))


                        # Handle password reset if new password is provided
                        if form.new_password.data:
                            new_password_hash = generate_password_hash(form.new_password.data)
                            cursor_non_dict.execute("UPDATE users SET password_hash = %s WHERE user_id = %s", (new_password_hash, user_id))


                        # Handle assigned classes if the role is 'teacher'
                        if form.role.data == 'teacher':
                            # Get selected class IDs from the request form data
                            # request.form.getlist('assigned_classes') returns a list of strings
                            selected_class_ids_str = request.form.getlist('assigned_classes')
                            selected_class_ids = [int(id) for id in selected_class_ids_str if id.isdigit()] # Convert to int and filter invalid

                            # Delete existing teacher_class assignments for this user
                            cursor_non_dict.execute("DELETE FROM teacher_classes WHERE user_id = %s", (user_id,))

                            # Insert new teacher_class assignments
                            if selected_class_ids:
                                insert_query = "INSERT INTO teacher_classes (user_id, class_id) VALUES (%s, %s)"
                                insert_values = [(user_id, class_id) for class_id in selected_class_ids]
                                cursor_non_dict.executemany(insert_query, insert_values)

                        elif form.role.data != 'teacher':
                             # If the role is changed FROM teacher to something else, delete existing assignments
                             cursor_non_dict.execute("DELETE FROM teacher_classes WHERE user_id = %s", (user_id,))


                        # Commit the transaction
                        conn.commit()

                        flash('使用者資料已成功更新', 'success')
                        return redirect(url_for('admin.manage_users')) # Redirect back to manage users page

                    except mysql.connector.Error as err:
                        conn.rollback()
                        flash(f"資料庫錯誤: {err}", 'danger')
                        current_app.logger.error(f"資料庫錯誤 (編輯使用者): {err}")
                        # Re-fetch classes and assigned_class_ids on DB error before re-rendering template
                        cursor_dict_on_error = conn.cursor(dictionary=True)
                        cursor_dict_on_error.execute("SELECT class_id, class_name FROM classes ORDER BY class_name")
                        classes = cursor_dict_on_error.fetchall()
                        if user_data: # user_data should be available from the initial fetch
                            cursor_dict_on_error.execute("SELECT class_id FROM teacher_classes WHERE user_id = %s", (user_id,))
                            assigned_classes_data_on_error = cursor_dict_on_error.fetchall()
                            assigned_class_ids = [item['class_id'] for item in assigned_classes_data_on_error]
                        cursor_dict_on_error.close()


                else:
                     # Form validation failed on POST
                     # Re-fetch classes and assigned_class_ids on validation failure before re-rendering template
                     # The form object will retain the submitted data and errors
                     cursor_dict_on_error = conn.cursor(dictionary=True)
                     cursor_dict_on_error.execute("SELECT class_id, class_name FROM classes ORDER BY class_name")
                     classes = cursor_dict_on_error.fetchall()
                     if user_data: # user_data should be available from the initial fetch
                         # For validation errors on assigned classes, the form doesn't handle it directly
                         # The submitted assigned_classes are in request.form.getlist('assigned_classes')
                         # We can't easily repopulate the checkboxes based on form errors unless we read request.form again.
                         # However, the template uses assigned_class_ids passed from the backend.
                         # On validation failure, we need to pass the *previously assigned* class IDs (if GET)
                         # OR attempt to get the *submitted* class IDs from request.form (if POST failed).
                         # Let's pass the previously assigned IDs for simplicity on validation failure.
                         # A more robust solution might involve re-reading request.form.getlist('assigned_classes') here.
                          cursor_dict_on_error.execute("SELECT class_id FROM teacher_classes WHERE user_id = %s", (user_id,))
                          assigned_classes_data_on_error = cursor_dict_on_error.fetchall()
                          assigned_class_ids = [item['class_id'] for item in assigned_classes_data_on_error]
                     cursor_dict_on_error.close()


        except mysql.connector.Error as err:
            # Catch database errors during GET or initial POST fetch
             flash(f"資料庫錯誤: {err}", 'danger')
             current_app.logger.error(f"資料庫錯誤 (載入編輯使用者資料): {err}")
             # Redirect to manage users page on initial fetch error
             if conn and conn.is_connected():
                 cursor.close()
                 conn.close()
             return redirect(url_for('admin.manage_users'))

        except Exception as e:
             # Catch other potential unknown errors
             if request.method == 'POST' and conn: conn.rollback() # Rollback on POST error
             flash(f"發生未知錯誤: {e}", 'danger')
             current_app.logger.error(f"未知錯誤 (編輯使用者): {e}")
             # Re-fetch classes and assigned_class_ids on other errors before re-rendering template
             if conn and conn.is_connected():
                 cursor_dict_on_error = conn.cursor(dictionary=True)
                 cursor_dict_on_error.execute("SELECT class_id, class_name FROM classes ORDER BY class_name")
                 classes = cursor_dict_on_error.fetchall()
                 if user_data: # user_data should be available from the initial fetch
                      cursor_dict_on_error.execute("SELECT class_id FROM teacher_classes WHERE user_id = %s", (user_id,))
                      assigned_classes_data_on_error = cursor_dict_on_error.fetchall()
                      assigned_class_ids = [item['class_id'] for item in assigned_classes_data_on_error]
                 cursor_dict_on_error.close()


        finally:
                # 確保游標在它們被成功創建 (即不是 None) 且連接仍然開啟時被關閉。
                # 檢查游標變數是否存在於本地作用域 (locals())，並且游標物件本身不是 None。
                # 注意：CMySQLCursorDict 物件沒有 .connection 屬性，檢查連接狀態應該在 conn 物件上進行。
                # 這裡只檢查游標是否被創建，如果連接已關閉，游標的 close() 應該能安全處理。
                if 'cursor' in locals() and cursor is not None:
                    try:
                        cursor.close()
                    except Exception as e: # 捕獲關閉游標時可能發生的任何異常
                        current_app.logger.error(f"錯誤關閉字典游標 (finally): {e}")

                # 對非字典游標進行同樣的檢查和關閉
                if 'cursor_non_dict' in locals() and cursor_non_dict is not None:
                    try:
                        cursor_non_dict.close()
                    except Exception as e: # 捕獲關閉游標時可能發生的任何異常
                        current_app.logger.error(f"錯誤關閉非字典游標 (finally): {e}")

                # 在 except 區塊中創建的 cursor_dict_on_error_fetch 已經在使用後立即關閉，所以 finally 區塊不需要再處理它。

                # 檢查連接是否被成功創建 (即不是 None) 且連接仍然活動，然後關閉它。
                # 使用 conn.is_connected() 來檢查連接狀態。
                if conn is not None and conn.is_connected():
                    try:
                        conn.close()
                    except Exception as e: # 捕獲關閉連接時可能發生的任何異常
                        current_app.logger.error(f"錯誤關閉資料庫連接 (finally): {e}")

    else:
        # Handle database connection failure
        flash('無法連接到資料庫', 'danger')
        return redirect(url_for('admin.manage_users'))

    # Render template on GET or POST validation failure
    # Ensure user_data is passed, even on POST validation failure, for title/header
    return render_template('admin/edit_user.html', title=f'修改使用者: {user_data["username"]}', user=user_data, form=form, classes=classes, assigned_class_ids=assigned_class_ids)


@bp.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    """刪除使用者帳號"""
    # 避免刪除當前登入的 admin 帳號
    if current_user.get_id() == user_id:
        flash('您不能刪除您自己的帳號', 'danger')
        return redirect(url_for('admin.manage_users'))

    conn = get_db()
    if conn:
        cursor = conn.cursor()
        try:
            # 刪除使用者
            # 由於 teacher_classes 表格使用了 ON DELETE CASCADE，刪除使用者時其班級關聯會自動刪除
            # 記錄表格 (absences, awards_punishments, competitions, late_records, incomplete_homework_records)
            # 的 recorded_by_user_id 欄位使用了 ON DELETE RESTRICT，
            # 如果該使用者有記錄任何事項，將無法直接刪除使用者。
            # 如果您希望刪除使用者時同時刪除其記錄的所有事項，需要修改 schema.sql 的 ON DELETE 約束為 CASCADE，
            # 或者在這裡手動刪除相關記錄 (不推薦，因為可能刪除其他人的記錄)。
            # 這裡保持 RESTRICT 約束，要求先刪除使用者記錄的所有事項才能刪除使用者。

            cursor.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
            conn.commit()
            flash('使用者已成功刪除', 'success')
        except mysql.connector.IntegrityError as err:
             # 捕獲外鍵約束錯誤
             flash('無法刪除該使用者，因為該使用者記錄了某些事項。請先刪除其記錄的所有事項。', 'danger')
             current_app.logger.error(f"資料庫完整性錯誤 (刪除使用者): {err}")
        except mysql.connector.Error as err:
            conn.rollback()
            flash(f"資料庫錯誤: {err}", 'danger')
            current_app.logger.error(f"資料庫錯誤 (刪除使用者): {err}")
        finally:
            if conn and conn.is_connected():
                 cursor.close()
                 conn.close()
    else:
        flash('無法連接到資料庫', 'danger')

    return redirect(url_for('admin.manage_users'))

@bp.route('/users/export_csv')
@login_required
@admin_required
def export_users_csv():
    """匯出使用者帳號為 CSV 文件"""
    conn = get_db()
    if not conn:
        flash('無法連接到資料庫，無法匯出使用者數據', 'danger')
        return redirect(url_for('admin.manage_users'))

    try:
        cursor = conn.cursor(dictionary=True)
        # 獲取所有使用者數據，包括分配的班級名稱
        cursor.execute("""
            SELECT u.user_id, u.username, u.role, u.teacher_name, u.id_card_number,
                   GROUP_CONCAT(c.class_name ORDER BY c.class_name SEPARATOR ', ') AS assigned_class_names
            FROM users u
            LEFT JOIN teacher_classes tc ON u.user_id = tc.user_id
            LEFT JOIN classes c ON tc.class_id = c.class_id
            GROUP BY u.user_id
            ORDER BY u.role, u.username
        """)
        users = cursor.fetchall()

        # 使用 StringIO 在記憶體中構建 CSV 數據
        si = StringIO()
        cw = csv.writer(si)

        # 寫入 CSV 表頭
        # 根據您希望匯出的欄位來定義表頭
        headers = ['使用者ID', '使用者名稱', '角色', '教師姓名', 'ID卡號碼', '分配班級']
        cw.writerow(headers)

        # 寫入使用者數據
        for user in users:
            # 確保每個欄位都是字串或可以轉換為字串
            row = [
                user.get('user_id', ''),
                user.get('username', ''),
                user.get('role', ''),
                user.get('teacher_name', ''),
                user.get('id_card_number', ''),
                user.get('assigned_class_names', '') # 已合併的班級名稱
            ]
            cw.writerow(row)

        # 獲取 CSV 數據
        output = si.getvalue()

        # 使用 send_file 發送 CSV 文件
        # 需要將 StringIO 對象轉換為文件對象，或者直接傳遞 StringIO 對象 (Flask 1.0+ 支持)
        # 或者將數據寫入臨時文件再發送
        # 最簡單的方式是使用 BytesIO 或 StringIO 並設置 mimetype
        from io import BytesIO
        buffer = BytesIO(output.encode('utf-8'))
        buffer.seek(0) # 將文件指針移到開頭

        # 修正：使用 send_file
        return send_file(buffer,
                         mimetype='text/csv',
                         as_attachment=True,
                         download_name='users_export.csv')


    except mysql.connector.Error as err:
        flash(f"資料庫錯誤，無法匯出使用者數據: {err}", 'danger')
        current_app.logger.error(f"資料庫錯誤 (匯出使用者 CSV): {err}")
    except Exception as e:
        flash(f"匯出使用者數據時發生錯誤: {e}", 'danger')
        current_app.logger.error(f"匯出使用者 CSV 時發生錯誤: {e}")
    finally:
        if conn and conn.is_connected():
             cursor.close()
             conn.close()

    return redirect(url_for('admin.manage_users')) # 匯出失敗時重定向

@bp.route('/users/import_csv', methods=['GET', 'POST'])
@login_required
@admin_required
def import_users_csv():
    """從 CSV 文件匯入使用者帳號"""
    form = CSVUploadForm()

    if form.validate_on_submit():
        csv_file = form.csv_file.data
        # 確保文件存在且是允許的類型 (FileAllowed 驗證器已經檢查了擴展名)

        try:
            # 使用 StringIO 從文件對象讀取 CSV 數據
            stream = StringIO(csv_file.stream.read().decode("UTF8"))
            csv_reader = csv.reader(stream)
            header = next(csv_reader) # 跳過表頭行

            # 根據您的 CSV 格式確定各欄位在 CSV 中的索引
            # 這裡假設 CSV 欄位順序為：使用者名稱, 密碼, 角色, 教師姓名, ID卡號碼, 分配班級(以逗號分隔)
            # 請根據實際 CSV 文件格式調整索引
            try:
                username_idx = header.index('使用者名稱')
                password_idx = header.index('密碼')
                role_idx = header.index('角色')
                teacher_name_idx = header.index('教師姓名') if '教師姓名' in header else -1 # 可選欄位
                id_card_number_idx = header.index('ID卡號碼') if 'ID卡號碼' in header else -1 # 可選欄位
                assigned_classes_idx = header.index('分配班級') if '分配班級' in header else -1 # 可選欄位
            except ValueError as e:
                 flash(f"CSV 文件表頭格式不正確，缺少必要欄位: {e}", 'danger')
                 return render_template('admin/import_csv.html', title='匯入使用者 (CSV)', form=form)


            conn = get_db()
            if not conn:
                flash('無法連接到資料庫，無法匯入使用者數據', 'danger')
                return render_template('admin/import_csv.html', title='匯入使用者 (CSV)', form=form)

            cursor = conn.cursor()
            imported_count = 0
            updated_count = 0
            errors = []

            # 獲取所有班級的 class_name 到 class_id 的映射，以便處理分配班級
            class_name_to_id = {}
            try:
                cursor.execute("SELECT class_id, class_name FROM classes")
                for class_id, class_name in cursor.fetchall():
                    class_name_to_id[class_name] = class_id
            except mysql.connector.Error as err:
                 flash(f"資料庫錯誤，無法獲取班級列表: {err}", 'danger')
                 current_app.logger.error(f"資料庫錯誤 (匯入使用者 CSV - 獲取班級): {err}")
                 if conn.is_connected(): cursor.close(); conn.close()
                 return render_template('admin/import_csv.html', title='匯入使用者 (CSV)', form=form)


            for row in csv_reader:
                # 確保行數據長度足夠包含所有預期的欄位
                if not row or len(row) < max(username_idx, password_idx, role_idx) + 1:
                    errors.append(f"跳過無效行 (欄位不足): {row}")
                    continue

                try:
                    username = row[username_idx].strip()
                    password = row[password_idx].strip()
                    role = row[role_idx].strip().lower() # 角色轉換為小寫
                    teacher_name = row[teacher_name_idx].strip() if teacher_name_idx != -1 and len(row) > teacher_name_idx and row[teacher_name_idx].strip() else None
                    id_card_number = row[id_card_number_idx].strip() if id_card_number_idx != -1 and len(row) > id_card_number_idx and row[id_card_number_idx].strip() else None
                    assigned_classes_str = row[assigned_classes_idx].strip() if assigned_classes_idx != -1 and len(row) > assigned_classes_idx and row[assigned_classes_idx].strip() else ''


                    # 驗證角色是否有效
                    if role not in ['admin', 'supervisor', 'teacher']:
                        errors.append(f"使用者 '{username}' 的角色無效: {row}")
                        continue

                    # 雜湊密碼
                    hashed_password = generate_password_hash(password)

                    # 檢查使用者名稱是否已存在
                    cursor.execute("SELECT user_id FROM users WHERE username = %s", (username,))
                    existing_user = cursor.fetchone()

                    if existing_user:
                        # 使用者已存在，更新
                        user_id = existing_user[0]
                        update_sql = "UPDATE users SET password_hash = %s, role = %s, teacher_name = %s, id_card_number = %s WHERE user_id = %s"
                        update_params = (hashed_password, role, teacher_name, id_card_number, user_id)
                        cursor.execute(update_sql, update_params)
                        updated_count += 1

                         # 處理班級分配更新 (先刪除舊的，再插入新的)
                        cursor.execute("DELETE FROM teacher_classes WHERE user_id = %s", (user_id,))
                        if role == 'teacher' and assigned_classes_str:
                            assigned_class_names = [name.strip() for name in assigned_classes_str.split(',') if name.strip()]
                            teacher_classes_values = []
                            for class_name in assigned_class_names:
                                if class_name in class_name_to_id:
                                    teacher_classes_values.append((user_id, class_name_to_id[class_name]))
                                else:
                                    errors.append(f"使用者 '{username}' 分配的班級 '{class_name}' 不存在。")
                            if teacher_classes_values:
                                cursor.executemany("INSERT INTO teacher_classes (user_id, class_id) VALUES (%s, %s)", teacher_classes_values)

                    else:
                        # 使用者不存在，插入新使用者
                        insert_sql = "INSERT INTO users (username, password_hash, role, teacher_name, id_card_number) VALUES (%s, %s, %s, %s, %s)"
                        insert_params = (username, hashed_password, role, teacher_name, id_card_number)
                        cursor.execute(insert_sql, insert_params)
                        user_id = cursor.lastrowid # 獲取新插入使用者的 ID
                        imported_count += 1

                        # 如果是教師，處理班級分配
                        if role == 'teacher' and assigned_classes_str:
                            assigned_class_names = [name.strip() for name in assigned_classes_str.split(',') if name.strip()]
                            teacher_classes_values = []
                            for class_name in assigned_class_names:
                                if class_name in class_name_to_id:
                                    teacher_classes_values.append((user_id, class_name_to_id[class_name]))
                                else:
                                    errors.append(f"使用者 '{username}' 分配的班級 '{class_name}' 不存在。")
                            if teacher_classes_values:
                                cursor.executemany("INSERT INTO teacher_classes (user_id, class_id) VALUES (%s, %s)", teacher_classes_values)


                except mysql.connector.IntegrityError as err:
                    # 捕獲唯一性約束錯誤 (例如 ID 卡號碼重複)
                    errors.append(f"使用者 '{username}' 數據無效 (唯一性衝突): {err}")
                    current_app.logger.error(f"資料庫完整性錯誤 (匯入使用者 CSV): {err}")
                except Exception as e:
                    errors.append(f"處理使用者 '{username}' 數據時發生錯誤: {e}")
                    current_app.logger.error(f"處理使用者 CSV 行時發生錯誤: {e}")

            conn.commit() # 提交所有更改
            flash(f'使用者數據匯入完成。新增 {imported_count} 筆，更新 {updated_count} 筆。', 'success')
            if errors:
                flash(f"匯入過程中發生以下錯誤: {'; '.join(errors)}", 'warning')

        except Exception as e:
            flash(f"讀取或處理 CSV 文件時發生錯誤: {e}", 'danger')
            current_app.logger.error(f"讀取或處理使用者 CSV 文件時發生錯誤: {e}")
        finally:
            if conn and conn.is_connected():
                 cursor.close()
                 conn.close()


        return redirect(url_for('admin.manage_users')) # 匯入完成後重定向

    # GET 請求時渲染上傳表單
    return render_template('admin/import_csv.html', title='匯入使用者 (CSV)', form=form)


# --- 學生管理 ---
@bp.route('/students')
@login_required
@admin_required
def manage_students():
    """管理學生資料列表"""
    conn = get_db()
    students = []
    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            # 獲取所有學生列表及其班級名稱，並包含統計數據
            cursor.execute("""
                SELECT s.student_id, s.student_number, s.name, c.class_name,
                       s.late_count, s.incomplete_homework_count, s.violation_points, s.award_points,
                       s.id_card_number, s.student_id_number -- 新增獲取 ID 卡號碼和學生證號碼
                FROM students s
                JOIN classes c ON s.class_id = c.class_id
                ORDER BY c.class_name, s.student_number, s.name
            """)
            students = cursor.fetchall()

            # TODO: 計算缺席總節數和參賽記錄計數 (這需要在獲取學生列表後進行額外查詢或在模板中處理)
            # 這裡可以在後端為每個學生添加這些統計數據
            for student in students:
                 # 獲取缺席總節數
                 cursor.execute("SELECT SUM(session_count) AS total_sessions FROM absences WHERE student_id = %s", (student['student_id'],))
                 absence_summary = cursor.fetchone()
                 student['total_absences_sessions'] = absence_summary['total_sessions'] if absence_summary and absence_summary['total_sessions'] is not None else 0

                 # 獲取參賽記錄計數
                 cursor.execute("SELECT result, COUNT(*) as count FROM competitions WHERE student_id = %s GROUP BY result", (student['student_id'],))
                 comp_summary_list = cursor.fetchall()
                 comp_summary = {item['result']: item['count'] for item in comp_summary_list}
                 student['comp_count_參與'] = comp_summary.get('參與', 0)
                 student['comp_count_入圍'] = comp_summary.get('入圍', 0)
                 student['comp_count_得獎'] = comp_summary.get('得獎', 0)


        except mysql.connector.Error as err:
            flash(f"資料庫錯誤: {err}", 'danger')
            current_app.logger.error(f"資料庫錯誤 (管理學生列表): {err}")
        finally:
            if conn and conn.is_connected():
                 cursor.close()
                 conn.close()


    return render_template('admin/manage_students.html', title='管理學生', students=students)

@bp.route('/students/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_student():
    """新增學生資料"""
    form = AddStudentForm()

    conn = get_db()
    classes_data = []
    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            # 獲取所有班級列表供選擇
            cursor.execute("SELECT class_id, class_name FROM classes ORDER BY class_name")
            classes_data = cursor.fetchall()
            form.class_id.choices = [(c['class_id'], c['class_name']) for c in classes_data]
        except mysql.connector.Error as err:
            flash(f"資料庫錯誤: {err}", 'danger')
            current_app.logger.error(f"資料庫錯誤 (新增學生 - 獲取班級): {err}")
            if conn.is_connected(): cursor.close(); conn.close()
            return render_template('admin/add_student.html', title='新增學生', form=form) # 發生錯誤時渲染表單


    if form.validate_on_submit():
        student_number = form.student_number.data
        name = form.name.data
        class_id = form.class_id.data
        id_card_number = form.id_card_number.data
        student_id_number = form.student_id_number.data

        conn = get_db()
        if conn:
            cursor = conn.cursor()
            try:
                # 插入新學生到資料庫
                cursor.execute(
                    "INSERT INTO students (student_number, name, class_id, id_card_number, student_id_number) VALUES (%s, %s, %s, %s, %s)",
                    (student_number, name, class_id, id_card_number, student_id_number)
                )
                conn.commit()
                flash(f'學生 "{name}" 已成功新增', 'success')
                return redirect(url_for('admin.manage_students'))
            except mysql.connector.Error as err:
                conn.rollback()
                flash(f"資料庫錯誤: {err}", 'danger')
                current_app.logger.error(f"資料庫錯誤 (新增學生): {err}")
            finally:
                if conn and conn.is_connected():
                     cursor.close()
                     conn.close()
        else:
            flash('無法連接到資料庫', 'danger')

    # 如果是 GET 請求或 POST 失敗，渲染表單 (班級選項已填充)
    return render_template('admin/add_student.html', title='新增學生', form=form)


@bp.route('/students/<int:student_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_student(student_id):
    """修改學生資料"""
    conn = get_db()
    student_data = None
    classes_data = []

    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            # 獲取要修改的學生資訊
            cursor.execute("SELECT * FROM students WHERE student_id = %s", (student_id,))
            student_data = cursor.fetchone()

            if not student_data:
                flash('找不到該學生', 'danger')
                if conn.is_connected(): cursor.close(); conn.close()
                return redirect(url_for('admin.manage_students'))

            # 獲取所有班級列表供選擇
            cursor.execute("SELECT class_id, class_name FROM classes ORDER BY class_name")
            classes_data = cursor.fetchall()


        except mysql.connector.Error as err:
            flash(f"資料庫錯誤: {err}", 'danger')
            current_app.logger.error(f"資料庫錯誤 (修改學生 - 獲取數據): {err}")
            if conn.is_connected(): cursor.close(); conn.close()
            return redirect(url_for('admin.manage_students')) # 發生錯誤時重定向

    if not student_data:
        return redirect(url_for('admin.manage_students'))

    # 初始化表單，並傳入原始數據用於驗證唯一性
    form = EditStudentForm(student_id=student_id,
                           original_student_number=student_data['student_number'],
                           original_id_card_number=student_data['id_card_number'],
                           original_student_id_number=student_data['student_id_number'])

    # 填充班級選項
    form.class_id.choices = [(c['class_id'], c['class_name']) for c in classes_data]


    # 在 GET 請求時用現有數據填充表單
    if request.method == 'GET':
         form.student_number.data = student_data['student_number']
         form.name.data = student_data['name']
         form.class_id.data = student_data['class_id'] # 設置預設選中的班級
         form.id_card_number.data = student_data['id_card_number']
         form.student_id_number.data = student_data['student_id_number']


    if form.validate_on_submit():
        student_number = form.student_number.data
        name = form.name.data
        class_id = form.class_id.data
        id_card_number = form.id_card_number.data
        student_id_number = form.student_id_number.data

        conn = get_db()
        if conn:
            cursor = conn.cursor()
            try:
                # 更新學生資料
                cursor.execute(
                    "UPDATE students SET student_number = %s, name = %s, class_id = %s, id_card_number = %s, student_id_number = %s WHERE student_id = %s",
                    (student_number, name, class_id, id_card_number, student_id_number, student_id)
                )
                conn.commit()
                flash(f'學生 "{name}" 的資料已成功更新', 'success')
                return redirect(url_for('admin.manage_students'))
            except mysql.connector.Error as err:
                conn.rollback()
                flash(f"資料庫錯誤: {err}", 'danger')
                current_app.logger.error(f"資料庫錯誤 (更新學生): {err}")
            finally:
                if conn and conn.is_connected():
                     cursor.close()
                     conn.close()
        else:
            flash('無法連接到資料庫', 'danger')

    # GET 請求或 POST 失敗時渲染表單 (班級選項已填充，數據已填充)
    return render_template('admin/edit_student.html', title=f'修改學生: {student_data["name"]}', student=student_data, form=form)


@bp.route('/students/<int:student_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_student(student_id):
    """刪除學生資料及其相關記錄"""
    conn = get_db()
    if conn:
        cursor = conn.cursor()
        try:
            # 刪除學生
            # 由於記錄表格使用了 ON DELETE CASCADE，刪除學生時其相關記錄會自動刪除
            cursor.execute("DELETE FROM students WHERE student_id = %s", (student_id,))
            conn.commit()
            flash('學生資料及其相關記錄已成功刪除', 'success')
        except mysql.connector.Error as err:
            conn.rollback()
            flash(f"資料庫錯誤: {err}", 'danger')
            current_app.logger.error(f"資料庫錯誤 (刪除學生): {err}")
        finally:
            if conn and conn.is_connected():
                 cursor.close()
                 conn.close()
    else:
        flash('無法連接到資料庫', 'danger')

    return redirect(url_for('admin.manage_students'))

@bp.route('/students/export_csv')
@login_required
@admin_required
def export_students_csv():
    """匯出學生資料為 CSV 文件"""
    conn = get_db()
    if not conn:
        flash('無法連接到資料庫，無法匯出學生數據', 'danger')
        return redirect(url_for('admin.manage_students'))

    try:
        cursor = conn.cursor(dictionary=True)
        # 獲取所有學生資料，包括班級名稱和所有統計數據
        cursor.execute("""
            SELECT s.student_id, s.student_number, s.name, c.class_name,
                   s.late_count, s.incomplete_homework_count, s.violation_points, s.award_points,
                   s.id_card_number, s.student_id_number -- 新增獲取 ID 卡號碼和學生證號碼
            FROM students s
            JOIN classes c ON s.class_id = c.class_id
            ORDER BY c.class_name, s.student_number, s.name
        """)
        students = cursor.fetchall()

        # 獲取每個學生的詳細記錄以計算額外統計數據 (缺席總節數, 參賽計數)
        for student in students:
             # 獲取缺席總節數
             cursor.execute("SELECT SUM(session_count) AS total_sessions FROM absences WHERE student_id = %s", (student['student_id'],))
             absence_summary = cursor.fetchone()
             student['total_absences_sessions'] = absence_summary['total_sessions'] if absence_summary and absence_summary['total_sessions'] is not None else 0

             # 獲取獎懲記錄計數 (警告, 缺點, 小過, 大過, 表揚, 優點, 小功, 大功)
             award_punish_counts = {}
             cursor.execute("SELECT type, COUNT(*) as count FROM awards_punishments WHERE student_id = %s GROUP BY type", (student['student_id'],))
             for row in cursor.fetchall():
                  award_punish_counts[row['type']] = row['count']

             student['award_punish_count_警告'] = award_punish_counts.get('警告', 0)
             student['award_punish_count_缺點'] = award_punish_counts.get('缺點', 0)
             student['award_punish_count_小過'] = award_punish_counts.get('小過', 0) # 修正這裡的鍵名
             student['award_punish_count_大過'] = award_punish_counts.get('大過', 0) # 修正這裡的鍵名
             student['award_punish_count_表揚'] = award_punish_counts.get('表揚', 0)
             student['award_punish_count_優點'] = award_punish_counts.get('優點', 0)
             student['award_punish_count_小功'] = award_punish_counts.get('小功', 0)
             student['award_punish_count_大功'] = award_punish_counts.get('大功', 0)


             # 獲取參賽記錄計數 (參與, 入圍, 得獎)
             comp_counts = {}
             cursor.execute("SELECT result, COUNT(*) as count FROM competitions WHERE student_id = %s GROUP BY result", (student['student_id'],))
             for row in cursor.fetchall():
                  comp_counts[row['result']] = row['count']

             student['comp_count_參與'] = comp_counts.get('參與', 0)
             student['comp_count_入圍'] = comp_counts.get('入圍', 0)
             student['comp_count_得獎'] = comp_counts.get('得獎', 0)


        # 使用 StringIO 在記憶體中構建 CSV 數據
        si = StringIO()
        cw = csv.writer(si)

        # 寫入 CSV 表頭
        headers = [
            '學生ID', '學號', '姓名', '班級名稱', 'ID卡號碼', '學生證號碼', '總缺席節數', '總遲到次數', '總欠交功課次數',
            '總違規點數', '總獎勵點數',
            '獎懲_警告次數', '獎懲_缺點次數', '獎懲_小過次數', '獎懲_大過次數',
            '獎懲_表揚次數', '獎懲_優點次數', '獎懲_小功次數', '獎懲_大功次數',
            '參賽_參與次數', '參賽_入圍次數', '參賽_得獎次數'
        ]
        cw.writerow(headers)

        # 寫入學生數據
        for student in students:
            row = [
                student.get('student_id', ''),
                student.get('student_number', ''),
                student.get('name', ''),
                student.get('class_name', ''),
                student.get('id_card_number', ''), # 匯出 ID 卡號碼
                student.get('student_id_number', ''), # 匯出 學生證號碼
                student.get('total_absences_sessions', 0),
                student.get('late_count', 0),
                student.get('incomplete_homework_count', 0),
                student.get('violation_points', 0),
                student.get('award_points', 0),
                student.get('award_punish_count_警告', 0),
                student.get('award_punish_count_缺點', 0),
                student.get('award_punish_count_小過', 0), # 修正這裡的鍵名
                student.get('award_punish_count_大過', 0), # 修正這裡的鍵名
                student.get('award_punish_count_表揚', 0),
                student.get('award_punish_count_優點', 0),
                student.get('award_punish_count_小功', 0),
                student.get('award_punish_count_大功', 0),
                student.get('comp_count_參與', 0),
                student.get('comp_count_入圍', 0),
                student.get('comp_count_得獎', 0)
            ]
            cw.writerow(row)

        # 獲取 CSV 數據
        output = si.getvalue()

        # 使用 send_file 發送 CSV 文件
        from io import BytesIO
        buffer = BytesIO(output.encode('utf-8'))
        buffer.seek(0) # 將文件指針移到開頭

        # 修正：使用 send_file
        return send_file(buffer,
                         mimetype='text/csv',
                         as_attachment=True,
                         download_name='students_export.csv')


    except mysql.connector.Error as err:
        flash(f"資料庫錯誤，無法匯出學生數據: {err}", 'danger')
        current_app.logger.error(f"資料庫錯誤 (匯出學生 CSV): {err}")
    except Exception as e:
        flash(f"匯出學生數據時發生錯誤: {e}", 'danger')
        current_app.logger.error(f"匯出學生 CSV 時發生錯誤: {e}")
    finally:
        if conn and conn.is_connected():
             cursor.close()
             conn.close()

    return redirect(url_for('admin.manage_students')) # 匯出失敗時重定向


@bp.route('/students/import_csv', methods=['GET', 'POST'])
@login_required
@admin_required
def import_students_csv():
    """從 CSV 文件匯入學生資料"""
    form = CSVUploadForm()

    if form.validate_on_submit():
        csv_file = form.csv_file.data
        # 確保文件存在且是允許的類型 (FileAllowed 驗證器已經檢查了擴展名)

        try:
            # 使用 StringIO 從文件對象讀取 CSV 數據
            stream = StringIO(csv_file.stream.read().decode("UTF8"))
            csv_reader = csv.reader(stream)
            header = next(csv_reader) # 跳過表頭行

            # 根據您的 CSV 格式確定各欄位在 CSV 中的索引
            # 這裡假設 CSV 欄位順序為：學號, 姓名, 班級名稱, ID卡號碼, 學生證號碼
            # 請根據實際 CSV 文件格式調整索引
            try:
                student_number_idx = header.index('學號') if '學號' in header else -1
                name_idx = header.index('姓名')
                class_name_idx = header.index('班級名稱')
                id_card_number_idx = header.index('ID卡號碼') if 'ID卡號碼' in header else -1
                student_id_number_idx = header.index('學生證號碼') if '學生證號碼' in header else -1
            except ValueError as e:
                 flash(f"CSV 文件表頭格式不正確，缺少必要欄位 (姓名, 班級名稱): {e}", 'danger')
                 return render_template('admin/import_csv.html', title='匯入學生 (CSV)', form=form)


            conn = get_db()
            if not conn:
                flash('無法連接到資料庫，無法匯入學生數據', 'danger')
                return render_template('admin/import_csv.html', title='匯入學生 (CSV)', form=form)

            cursor = conn.cursor()
            imported_count = 0
            updated_count = 0
            errors = []

            # 獲取所有班級的 class_name 到 class_id 的映射
            class_name_to_id = {}
            try:
                cursor.execute("SELECT class_id, class_name FROM classes")
                for class_id, class_name in cursor.fetchall():
                    class_name_to_id[class_name] = class_id
            except mysql.connector.Error as err:
                 flash(f"資料庫錯誤，無法獲取班級列表: {err}", 'danger')
                 current_app.logger.error(f"資料庫錯誤 (匯入學生 CSV - 獲取班級): {err}")
                 if conn.is_connected(): cursor.close(); conn.close()
                 return render_template('admin/import_csv.html', title='匯入學生 (CSV)', form=form)


            for row in csv_reader:
                # 確保行數據長度足夠包含所有預期的欄位
                if not row or len(row) < max(name_idx, class_name_idx) + 1:
                    errors.append(f"跳過無效行 (欄位不足): {row}")
                    continue

                try:
                    student_number = row[student_number_idx].strip() if student_number_idx != -1 and len(row) > student_number_idx and row[student_number_idx].strip() else None
                    name = row[name_idx].strip()
                    class_name = row[class_name_idx].strip()
                    id_card_number = row[id_card_number_idx].strip() if id_card_number_idx != -1 and len(row) > id_card_number_idx and row[id_card_number_idx].strip() else None
                    student_id_number = row[student_id_number_idx].strip() if student_id_number_idx != -1 and len(row) > student_id_number_idx and row[student_id_number_idx].strip() else None


                    # 獲取班級 ID
                    class_id = class_name_to_id.get(class_name)
                    if class_id is None:
                        errors.append(f"學生 '{name}' (學號: {student_number if student_number else 'N/A'}) 的班級 '{class_name}' 不存在。")
                        continue

                    # 檢查學生是否已存在 (根據學號和姓名，或者其他唯一標識)
                    # 這裡假設根據學號和姓名組合來判斷是否為同一學生
                    # 更嚴謹的做法可能是根據 ID 卡號碼或學生證號碼等唯一識別碼
                    # 這裡使用學號作為主要判斷依據，如果學號存在，則更新；如果學號不存在但姓名和班級組合存在，也可以考慮更新
                    existing_student_id = None
                    if student_number:
                         cursor.execute("SELECT student_id FROM students WHERE student_number = %s", (student_number,))
                         result = cursor.fetchone()
                         if result:
                              existing_student_id = result[0]
                    # 如果沒有學號，嘗試根據姓名和班級判斷 (可能不夠準確)
                    # else:
                    #      cursor.execute("SELECT student_id FROM students WHERE name = %s AND class_id = %s", (name, class_id))
                    #      result = cursor.fetchone()
                    #      if result:
                    #           existing_student_id = result[0]


                    if existing_student_id:
                        # 學生已存在，更新
                        update_sql = "UPDATE students SET name = %s, class_id = %s, id_card_number = %s, student_id_number = %s WHERE student_id = %s"
                        update_params = (name, class_id, id_card_number, student_id_number, existing_student_id)
                        cursor.execute(update_sql, update_params)
                        updated_count += 1
                    else:
                        # 學生不存在，插入新學生
                        insert_sql = "INSERT INTO students (student_number, name, class_id, id_card_number, student_id_number) VALUES (%s, %s, %s, %s, %s)"
                        insert_params = (student_number, name, class_id, id_card_number, student_id_number)
                        cursor.execute(insert_sql, insert_params)
                        imported_count += 1

                except mysql.connector.IntegrityError as err:
                    # 捕獲唯一性約束錯誤 (例如 ID 卡號碼或學生證號碼重複)
                    errors.append(f"學生 '{name}' (學號: {student_number if student_number else 'N/A'}) 數據無效 (唯一性衝突): {err}")
                    current_app.logger.error(f"資料庫完整性錯誤 (匯入學生 CSV): {err}")
                except Exception as e:
                    errors.append(f"處理學生 '{name}' (學號: {student_number if student_number else 'N/A'}) 數據時發生錯誤: {e}")
                    current_app.logger.error(f"處理學生 CSV 行時發生錯誤: {e}")

            conn.commit() # 提交所有更改
            flash(f'學生數據匯入完成。新增 {imported_count} 筆，更新 {updated_count} 筆。', 'success')
            if errors:
                flash(f"匯入過程中發生以下錯誤: {'; '.join(errors)}", 'warning')

        except Exception as e:
            flash(f"讀取或處理 CSV 文件時發生錯誤: {e}", 'danger')
            current_app.logger.error(f"讀取或處理學生 CSV 文件時發生錯誤: {e}")
        finally:
            if conn and conn.is_connected():
                 cursor.close()
                 conn.close()


        return redirect(url_for('admin.manage_students')) # 匯入完成後重定向

    # GET 請求時渲染上傳表單
    return render_template('admin/import_csv.html', title='匯入學生 (CSV)', form=form)


# --- 班級管理 ---
@bp.route('/classes')
@login_required
@admin_required
def manage_classes():
    """管理班級列表"""
    conn = get_db()
    classes = []
    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            # 獲取所有班級列表
            cursor.execute("SELECT * FROM classes ORDER BY class_name")
            classes = cursor.fetchall()
        except mysql.connector.Error as err:
            flash(f"資料庫錯誤: {err}", 'danger')
            current_app.logger.error(f"資料庫錯誤 (管理班級列表): {err}")
        finally:
            if conn and conn.is_connected():
                 cursor.close()
                 conn.close()

    return render_template('admin/manage_classes.html', title='管理班級', classes=classes)

@bp.route('/classes/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_class():
    """新增班級"""
    form = AddClassForm()

    if form.validate_on_submit():
        class_name = form.class_name.data

        conn = get_db()
        if conn:
            cursor = conn.cursor()
            try:
                # 插入新班級到資料庫
                cursor.execute("INSERT INTO classes (class_name) VALUES (%s)", (class_name,))
                conn.commit()
                flash(f'班級 "{class_name}" 已成功新增', 'success')
                return redirect(url_for('admin.manage_classes'))
            except mysql.connector.Error as err:
                conn.rollback()
                flash(f"資料庫錯誤: {err}", 'danger')
                current_app.logger.error(f"資料庫錯誤 (新增班級): {err}")
            finally:
                if conn and conn.is_connected():
                     cursor.close()
                     conn.close()
        else:
            flash('無法連接到資料庫', 'danger')

    # GET 請求或 POST 失敗時渲染表單
    return render_template('admin/add_class.html', title='新增班級', form=form)


@bp.route('/classes/<int:class_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_class(class_id):
    """修改班級"""
    conn = get_db()
    class_data = None

    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            # 獲取要修改的班級資訊
            cursor.execute("SELECT * FROM classes WHERE class_id = %s", (class_id,))
            class_data = cursor.fetchone()

            if not class_data:
                flash('找不到該班級', 'danger')
                if conn.is_connected(): cursor.close(); conn.close()
                return redirect(url_for('admin.manage_classes'))

        except mysql.connector.Error as err:
            flash(f"資料庫錯誤: {err}", 'danger')
            current_app.logger.error(f"資料庫錯誤 (修改班級 - 獲取數據): {err}")
            if conn.is_connected(): cursor.close(); conn.close()
            return redirect(url_for('admin.manage_classes')) # 發生錯誤時重定向

    if not class_data:
        return redirect(url_for('admin.manage_classes'))

    # 初始化表單，並傳入原始數據用於驗證唯一性
    form = EditClassForm(class_id=class_id, original_class_name=class_data['class_name'])

    # 在 GET 請求時用現有數據填充表單
    if request.method == 'GET':
         form.class_name.data = class_data['class_name']


    if form.validate_on_submit():
        class_name = form.class_name.data

        conn = get_db()
        if conn:
            cursor = conn.cursor()
            try:
                # 更新班級名稱
                cursor.execute("UPDATE classes SET class_name = %s WHERE class_id = %s", (class_name, class_id))
                conn.commit()
                flash(f'班級 "{class_name}" 已成功更新', 'success')
                return redirect(url_for('admin.manage_classes'))
            except mysql.connector.Error as err:
                conn.rollback()
                flash(f"資料庫錯誤: {err}", 'danger')
                current_app.logger.error(f"資料庫錯誤 (更新班級): {err}")
            finally:
                if conn and conn.is_connected():
                     cursor.close()
                     conn.close()
        else:
            flash('無法連接到資料庫', 'danger')

    # GET 請求或 POST 失敗時渲染表單 (數據已填充)
    return render_template('admin/edit_class.html', title=f'修改班級: {class_data["class_name"]}', class_obj=class_data, form=form)


@bp.route('/classes/<int:class_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_class(class_id):
    """刪除班級及其下的所有學生和相關記錄"""
    conn = get_db()
    if conn:
        cursor = conn.cursor()
        try:
            # 檢查班級是否存在
            cursor.execute("SELECT class_id FROM classes WHERE class_id = %s", (class_id,))
            if not cursor.fetchone():
                 flash('找不到該班級', 'danger')
                 if conn.is_connected(): cursor.close(); conn.close()
                 return redirect(url_for('admin.manage_classes'))

            # 刪除班級
            # 由於 students 和 teacher_classes 表格使用了 ON DELETE CASCADE，
            # 刪除班級時其下的所有學生及其相關記錄，以及與該班級相關的教師關聯都會自動刪除。
            cursor.execute("DELETE FROM classes WHERE class_id = %s", (class_id,))
            conn.commit()
            flash('班級及其下的所有學生和相關記錄已成功刪除', 'success')
        except mysql.connector.Error as err:
            conn.rollback()
            flash(f"資料庫錯誤: {err}", 'danger')
            current_app.logger.error(f"資料庫錯誤 (刪除班級): {err}")
        finally:
            if conn and conn.is_connected():
                 cursor.close()
                 conn.close()
    else:
        flash('無法連接到資料庫', 'danger')

    return redirect(url_for('admin.manage_classes'))

# TODO: 實現主管儀表板的記錄列表頁面路由 (view_all_absences, view_all_awards_punishments, view_all_competitions, view_all_late, view_all_incomplete_homework)
# 這些路由應該在 main.py 中實現，並包含權限檢查 (允許 admin 和 supervisor)
# 並且需要獲取所有相關記錄，而不是特定學生的記錄。
# 在這些頁面中，也需要顯示記錄所屬的學生姓名和班級。

# TODO: 更新 main.py 中的 uploaded_file 路由，添加權限檢查，允許 admin, supervisor, 以及該文件所屬學生班級的教師訪問。
# 這需要查詢資料庫以確定文件所屬的記錄 (absence, award_punishment, competition)，然後獲取學生的班級 ID，再檢查使用者權限。
# 由於 uploaded_file 路由在 main.py 中，這部分邏輯將在 main.py 中實現。
