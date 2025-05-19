# app/forms.py
from flask_wtf import FlaskForm
# 導入所有需要的字段和驗證器
from wtforms import (
    StringField, PasswordField, SubmitField, SelectField,
    TextAreaField, DateField, IntegerField, BooleanField,
    FieldList, FormField
)
from wtforms.validators import (
    DataRequired, Length, ValidationError, Optional,
    NumberRange, InputRequired, EqualTo, Email # 如果需要 Email 驗證
)
from flask_wtf.file import FileField, FileAllowed
import mysql.connector
from app.__init__ import get_db # 導入資料庫連接函式
from flask import current_app # 導入 current_app 以使用 logger


# 輔助表單：用於 FieldList 中的每個班級勾選項
class AssignedClassForm(FlaskForm):
    """用於 FieldList 中的單個班級選擇項"""
    # class_id 使用 HiddenField 或者只用於驗證
    class_id = IntegerField('Class ID', validators=[InputRequired()]) # 儲存班級 ID, 需要 InputRequired
    # class_name 僅用於顯示，不需驗證
    class_name = StringField('Class Name', render_kw={'readonly': True}) # 顯示班級名稱，設定為只讀
    # class_selected 是實際的勾選框
    class_selected = BooleanField('Selected') # 勾選框，表示是否選中該班級

# 使用者相關表單
class LoginForm(FlaskForm):
    """使用者登入表單"""
    username = StringField('使用者名稱', validators=[DataRequired()])
    password = PasswordField('密碼', validators=[DataRequired()])
    remember_me = BooleanField('記住我')
    submit = SubmitField('登入')

class AddUserForm(FlaskForm):
    """新增使用者表單"""
    username = StringField('使用者名稱', validators=[DataRequired(), Length(min=2, max=50)])
    password = PasswordField('密碼', validators=[DataRequired(), Length(min=8)])
    # 新增：確認密碼欄位，使用 EqualTo 驗證器確保與 password 欄位相符
    confirm_password = PasswordField('確認密碼', validators=[DataRequired(), EqualTo('password', message='密碼不相符')])
    role = SelectField('角色', choices=[('teacher', '教師'), ('supervisor', '主管'), ('admin', '管理員')], validators=[DataRequired()])
    teacher_name = StringField('教師姓名', validators=[Optional(), Length(max=100)]) # 教師姓名可選
    id_card_number = StringField('ID卡號碼', validators=[Optional(), Length(max=50)]) # ID卡號碼可選
    # 使用 FieldList 包含 AssignedClassForm，用於教師分配班級的多選
    # min_entries=0 允許 FieldList 為空
    assigned_classes = FieldList(FormField(AssignedClassForm), min_entries=0)
    submit = SubmitField('新增使用者')

    def validate_username(self, username):
        """驗證使用者名稱是否已存在"""
        conn = get_db()
        if conn:
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT user_id FROM users WHERE username = %s", (username.data,))
                user = cursor.fetchone()
                if user:
                    raise ValidationError('該使用者名稱已被使用。')
            except mysql.connector.Error as err:
                current_app.logger.error(f"資料庫錯誤 (驗證使用者名稱): {err}")
                # 可以考慮在此處添加一個通用的資料庫錯誤閃現訊息
                raise ValidationError('驗證使用者名稱時發生資料庫錯誤。') # 拋出錯誤以阻止提交
            finally:
                 if conn and conn.is_connected():
                      cursor.close()
                      conn.close()

    def validate_id_card_number(self, id_card_number):
        """驗證 ID 卡號碼是否已存在 (如果填寫了)"""
        if id_card_number.data: # 只有當填寫了 ID 卡號碼時才驗證
            conn = get_db()
            if conn:
                cursor = conn.cursor()
                try:
                    cursor.execute("SELECT user_id FROM users WHERE id_card_number = %s", (id_card_number.data,))
                    user = cursor.fetchone()
                    if user:
                        raise ValidationError('該ID卡號碼已被使用。')
                except mysql.connector.Error as err:
                    current_app.logger.error(f"資料庫錯誤 (驗證ID卡號碼): {err}")
                    raise ValidationError('驗證ID卡號碼時發生資料庫錯誤。')
                finally:
                    if conn and conn.is_connected():
                         cursor.close()
                         conn.close()

    # 這裡根據您的要求，教師必須選擇一個班級的驗證是關閉的 (註解掉的)
    # def validate_assigned_classes(self, assigned_classes):
    #     """驗證教師角色是否至少選擇了一個班級 (如果需要此驗證，請取消註解)"""
    #     if self.role.data == 'teacher':
    #         selected_class_ids = [
    #             subfield.form.class_id.data
    #             for subfield in assigned_classes.entries
    #             if subfield.form.class_selected.data
    #         ]
    #         if not selected_class_ids:
    #             # 將錯誤添加到 FieldList 本身，而不是單個子表單
    #             raise ValidationError('教師角色必須至少選擇一個負責的班級。')

    def populate_classes_for_fieldlist(self, classes_data, assigned_class_ids=None):
        """
        根據資料庫中的班級資料動態填充 assigned_classes FieldList。
        assigned_class_ids 是一個列表，包含該使用者已分配的班級 ID (用於編輯時預選)。
        """
        # 清空現有的 FieldList 條目
        # 更好的清空 FieldList 方式
        while len(self.assigned_classes) > 0:
            self.assigned_classes.pop_entry()

        for class_info in classes_data:
            # 為每個班級添加一個 FieldList 條目
            entry = self.assigned_classes.append_entry()
            entry.form.class_id.data = class_info['class_id']
            entry.form.class_name.data = class_info['class_name']
            # 如果提供了 assigned_class_ids 且當前班級 ID 在列表中，則預設勾選
            if assigned_class_ids is not None and class_info['class_id'] in assigned_class_ids:
                 entry.form.class_selected.data = True
            else:
                 entry.form.class_selected.data = False # 確保未分配的班級不被勾選


class EditUserForm(FlaskForm):
    """修改使用者表單"""
    # Include username field for display, but validation handled separately in route
    username = StringField('使用者名稱', validators=[DataRequired(), Length(min=2, max=50)]) # Keep for rendering, but validation handled in backend
    role = SelectField('角色', choices=[('admin', '管理員'), ('supervisor', '主管'), ('teacher', '教師')], validators=[DataRequired()]) # Corrected supervisor label? No, schema says supervisor. Let's keep it as is.
    teacher_name = StringField('教師姓名 (如果角色是教師)', validators=[Optional(), Length(max=100)])
    id_card_number = StringField('ID 卡號碼 (可選)', validators=[Optional(), Length(max=50)])

    # Fields for forcing password reset
    new_password = PasswordField('新密碼 (強制修改)', validators=[Optional(), Length(min=6)])
    confirm_password = PasswordField('確認新密碼', validators=[EqualTo('new_password', message='密碼不一致')]) # EqualTo validator checks against new_password

    submit = SubmitField('更新使用者')

    # Custom validation for password fields
    def validate_new_password(self, field):
        if field.data: # If new_password field has data (user intends to change password)
            if not self.confirm_password.data: # Check if confirm_password is empty
                raise ValidationError('請確認新密碼') # Require confirm_password
            # Length validator is already applied
        elif self.confirm_password.data: # If new_password is empty but confirm_password is not
             raise ValidationError('請輸入新密碼') # Require new_password if confirm_password has data


    def __init__(self, *args, **kwargs):
        # 接收原始使用者的 user_id, original_id_card_number 以在驗證時排除當前使用者
        self.user_id = kwargs.pop('user_id', None)
        self.original_id_card_number = kwargs.pop('original_id_card_number', None)
        super(EditUserForm, self).__init__(*args, **kwargs)


    def validate_id_card_number(self, id_card_number):
        """驗證 ID 卡號碼是否已存在 (如果填寫了，且不是當前使用者的原始號碼)"""
        if id_card_number.data: # 只有當填寫了 ID 卡號碼時才驗證
            conn = get_db()
            if conn:
                cursor = conn.cursor()
                try:
                    # 查詢是否存在其他使用者的 ID 卡號碼與當前填寫的相同
                    cursor.execute("SELECT user_id FROM users WHERE id_card_number = %s AND user_id != %s", (id_card_number.data, self.user_id))
                    user = cursor.fetchone()
                    if user:
                        raise ValidationError('該ID卡號碼已被其他使用者使用。')
                except mysql.connector.Error as err:
                    current_app.logger.error(f"資料庫錯誤 (驗證ID卡號碼): {err}")
                    raise ValidationError('驗證ID卡號碼時發生資料庫錯誤。')
                finally:
                    if conn and conn.is_connected():
                         cursor.close()
                         conn.close()

    # 這裡根據您的要求，教師必須選擇一個班級的驗證是關閉的 (註解掉的)
    # def validate_assigned_classes(self, assigned_classes):
    #     """驗證教師角色是否至少選擇了一個班級 (如果需要此驗證，請取消註解)"""
    #     if self.role.data == 'teacher':
    #         selected_class_ids = [
    #             subfield.form.class_id.data
    #             for subfield in assigned_classes.entries
    #             if subfield.form.class_selected.data
    #         ]
    #         if not selected_class_ids:
    #             raise ValidationError('教師角色必須至少選擇一個負責的班級。')

    def populate_classes_for_fieldlist(self, classes_data, assigned_class_ids=None):
        """
        根據資料庫中的班級資料動態填充 assigned_classes FieldList。
        assigned_class_ids 是一個列表，包含該使用者已分配的班級 ID (用於編輯時預選)。
        """
        # 清空現有的 FieldList 條目
        while len(self.assigned_classes) > 0:
            self.assigned_classes.pop_entry()


        for class_info in classes_data:
            # 為每個班級添加一個 FieldList 條目
            entry = self.assigned_classes.append_entry()
            entry.form.class_id.data = class_info['class_id']
            entry.form.class_name.data = class_info['class_name']
            # 如果提供了 assigned_class_ids 且當前班級 ID 在列表中，則預設勾選
            if assigned_class_ids is not None and class_info['class_id'] in assigned_class_ids:
                 entry.form.class_selected.data = True
            else:
                 entry.form.class_selected.data = False # 確保未分配的班級不被勾選


class ChangePasswordForm(FlaskForm):
    """修改密碼表單 (使用者自己修改)"""
    # 修改欄位名稱以符合模板預期
    current_password = PasswordField('舊密碼', validators=[DataRequired()])
    new_password = PasswordField('新密碼', validators=[DataRequired(), Length(min=8)])
    # 確認新密碼欄位，使用 EqualTo 驗證器確保與 new_password 欄位相符
    confirm_password = PasswordField('確認新密碼', validators=[DataRequired(), EqualTo('new_password', message='新密碼和確認密碼不相符')]) # 添加 message 參數提供更友好的提示
    submit = SubmitField('修改密碼')

# 學生相關表單
class AddStudentForm(FlaskForm):
    """新增學生表單"""
    student_number = StringField('學號', validators=[Optional(), Length(max=20)])
    name = StringField('姓名', validators=[DataRequired(), Length(max=100)])
    class_id = SelectField('班級', coerce=int, validators=[DataRequired()]) # coerce=int 將值轉換為整數
    id_card_number = StringField('ID卡號碼', validators=[Optional(), Length(max=50)]) # ID卡號碼可選
    student_id_number = StringField('學生證號碼', validators=[Optional(), Length(max=50)]) # 學生證號碼可選
    submit = SubmitField('新增學生')

    def validate_student_number(self, student_number):
        """驗證學號是否已存在 (如果填寫了)"""
        if student_number.data:
             conn = get_db()
             if conn:
                 cursor = conn.cursor()
                 try:
                     # 驗證學號在 *所有* 班級中是否唯一，如果要求學號在班級內唯一，則需要修改查詢
                     # cursor.execute("SELECT student_id FROM students WHERE student_number = %s AND class_id = %s", (student_number.data, self.class_id.data)) # 班級內唯一
                     cursor.execute("SELECT student_id FROM students WHERE student_number = %s", (student_number.data,)) # 所有班級中唯一
                     student = cursor.fetchone()
                     if student:
                         # 修正錯誤提示以反映驗證範圍
                         raise ValidationError('該學號已被使用。') # 如果是班級內唯一，則改為 '該學號已在選定班級中使用。'
                 except mysql.connector.Error as err:
                     current_app.logger.error(f"資料庫錯誤 (驗證學號): {err}")
                     raise ValidationError('驗證學號時發生資料庫錯誤。')
                 finally:
                     if conn and conn.is_connected():
                          cursor.close()
                          conn.close()

    def validate_id_card_number(self, id_card_number):
        """驗證學生 ID 卡號碼是否已存在 (如果填寫了)"""
        if id_card_number.data:
             conn = get_db()
             if conn:
                 cursor = conn.cursor()
                 try:
                     cursor.execute("SELECT student_id FROM students WHERE id_card_number = %s", (id_card_number.data,))
                     student = cursor.fetchone()
                     if student:
                         raise ValidationError('該ID卡號碼已被使用。')
                 except mysql.connector.Error as err:
                     current_app.logger.error(f"資料庫錯誤 (驗證學生ID卡號碼): {err}")
                     raise ValidationError('驗證學生ID卡號碼時發生資料庫錯誤。')
                 finally:
                     if conn and conn.is_connected():
                          cursor.close()
                          conn.close()

    def validate_student_id_number(self, student_id_number):
        """驗證學生證號碼是否已存在 (如果填寫了)"""
        if student_id_number.data:
             conn = get_db()
             if conn:
                 cursor = conn.cursor()
                 try:
                     cursor.execute("SELECT student_id FROM students WHERE student_id_number = %s", (student_id_number.data,))
                     student = cursor.fetchone()
                     if student:
                         raise ValidationError('該學生證號碼已被使用。')
                 except mysql.connector.Error as err:
                     current_app.logger.error(f"資料庫錯誤 (驗證學生證號碼): {err}")
                     raise ValidationError('驗證學生證號碼時發生資料庫錯誤。')
                 finally:
                     if conn and conn.is_connected():
                          cursor.close()
                          conn.close()


class EditStudentForm(FlaskForm):
    """修改學生表單"""
    student_number = StringField('學號', validators=[Optional(), Length(max=20)])
    name = StringField('姓名', validators=[DataRequired(), Length(max=100)])
    class_id = SelectField('班級', coerce=int, validators=[DataRequired()])
    id_card_number = StringField('ID卡號碼', validators=[Optional(), Length(max=50)]) # ID卡號碼可選
    student_id_number = StringField('學生證號碼', validators=[Optional(), Length(max=50)]) # 學生證號碼可選
    submit = SubmitField('更新學生')

    def __init__(self, *args, **kwargs):
        # 接收原始學生的 student_id, original_student_number, original_id_card_number, original_student_id_number
        self.student_id = kwargs.pop('student_id', None)
        self.original_student_number = kwargs.pop('original_student_number', None)
        self.original_id_card_number = kwargs.pop('original_id_card_number', None)
        self.original_student_id_number = kwargs.pop('original_student_id_number', None)
        super(EditStudentForm, self).__init__(*args, **kwargs)

    def validate_student_number(self, student_number):
        """驗證學號是否已存在 (如果填寫了，且不是當前學生的原始學號)"""
        if student_number.data and student_number.data != self.original_student_number:
             conn = get_db()
             if conn:
                 cursor = conn.cursor()
                 try:
                     # 驗證是否存在其他學生的學號與當前填寫的相同
                     # cursor.execute("SELECT student_id FROM students WHERE student_number = %s AND class_id = %s AND student_id != %s", (student_number.data, self.class_id.data, self.student_id)) # 班級內唯一
                     cursor.execute("SELECT student_id FROM students WHERE student_number = %s AND student_id != %s", (student_number.data, self.student_id)) # 所有班級中唯一
                     student = cursor.fetchone()
                     if student:
                         raise ValidationError('該學號已被使用。') # 如果是班級內唯一，則改為 '該學號已在選定班級中使用。'
                 except mysql.connector.Error as err:
                     current_app.logger.error(f"資料庫錯誤 (驗證學號): {err}")
                     raise ValidationError('驗證學號時發生資料庫錯誤。')
                 finally:
                     if conn and conn.is_connected():
                          cursor.close()
                          conn.close()

    def validate_id_card_number(self, id_card_number):
        """驗證學生 ID 卡號碼是否已存在 (如果填寫了，且不是當前學生的原始號碼)"""
        if id_card_number.data and id_card_number.data != self.original_id_card_number:
             conn = get_db()
             if conn:
                 cursor = conn.cursor()
                 try:
                     # 驗證是否存在其他學生的 ID 卡號碼與當前填寫的相同
                     cursor.execute("SELECT student_id FROM students WHERE id_card_number = %s AND student_id != %s", (id_card_number.data, self.student_id))
                     student = cursor.fetchone()
                     if student:
                         raise ValidationError('該ID卡號碼已被使用。')
                 except mysql.connector.Error as err:
                     current_app.logger.error(f"資料庫錯誤 (驗證學生ID卡號碼): {err}")
                     raise ValidationError('驗證學生ID卡號碼時發生資料庫錯誤。')
                 finally:
                     if conn and conn.is_connected():
                          cursor.close()
                          conn.close()

    def validate_student_id_number(self, student_id_number):
        """驗證學生證號碼是否已存在 (如果填寫了，且不是當前學生的原始號碼)"""
        if student_id_number.data and student_id_number.data != self.original_student_id_number:
             conn = get_db()
             if conn:
                 cursor = conn.cursor()
                 try:
                     # 驗證是否存在其他學生的學生證號碼與當前填寫的相同
                     cursor.execute("SELECT student_id FROM students WHERE student_id_number = %s AND student_id != %s", (student_id_number.data, self.student_id))
                     student = cursor.fetchone()
                     if student:
                         raise ValidationError('該學生證號碼已被使用。')
                 except mysql.connector.Error as err:
                     current_app.logger.error(f"資料庫錯誤 (驗證學生證號碼): {err}")
                     raise ValidationError('驗證學生證號碼時發生資料庫錯誤。')
                 finally:
                     if conn and conn.is_connected():
                          cursor.close()
                          conn.close()


# 班級相關表單
class AddClassForm(FlaskForm):
    """新增班級表單"""
    class_name = StringField('班級名稱', validators=[DataRequired(), Length(max=10)])
    submit = SubmitField('新增班級')

    def validate_class_name(self, class_name):
        """驗證班級名稱是否已存在"""
        conn = get_db()
        if conn:
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT class_id FROM classes WHERE class_name = %s", (class_name.data,))
                class_data = cursor.fetchone()
                if class_data:
                    raise ValidationError('該班級名稱已存在。')
            except mysql.connector.Error as err:
                current_app.logger.error(f"資料庫錯誤 (驗證班級名稱): {err}")
                raise ValidationError('驗證班級名稱時發生資料庫錯誤。')
            finally:
                if conn and conn.is_connected():
                     cursor.close()
                     conn.close()


class EditClassForm(FlaskForm):
    """修改班級表單"""
    class_name = StringField('班級名稱', validators=[DataRequired(), Length(max=10)])
    submit = SubmitField('更新班級')

    def __init__(self, *args, **kwargs):
        # 接收原始班級的 class_id 和 original_class_name 以在驗證時排除當前班級
        self.class_id = kwargs.pop('class_id', None)
        self.original_class_name = kwargs.pop('original_class_name', None)
        super(EditClassForm, self).__init__(*args, **kwargs)


    def validate_class_name(self, class_name):
        """驗證班級名稱是否已存在 (如果填寫了，且不是當前班級的原始名稱)"""
        if class_name.data and class_name.data != self.original_class_name:
            conn = get_db()
            if conn:
                cursor = conn.cursor()
                try:
                    # 查詢是否存在其他班級的名稱與當前填寫的相同
                    cursor.execute("SELECT class_id FROM classes WHERE class_name = %s AND class_id != %s", (class_name.data, self.class_id))
                    class_data = cursor.fetchone()
                    if class_data:
                        raise ValidationError('該班級名稱已被使用。')
                except mysql.connector.Error as err:
                    current_app.logger.error(f"資料庫錯誤 (驗證班級名稱): {err}")
                    raise ValidationError('驗證班級名稱時發生資料庫錯誤。')
                finally:
                    if conn and conn.is_connected():
                         cursor.close()
                         conn.close()


# 記錄相關表單 (這些表單與之前提供的大致相同，確保字段和驗證器正確)
class RecordAbsenceForm(FlaskForm):
    """記錄缺席表單"""
    absence_date = DateField('缺席日期', format='%Y-%m-%d', validators=[DataRequired()]) # 指定日期格式
    session_count = IntegerField('缺席節數', validators=[DataRequired(), NumberRange(min=1)])
    absence_type = SelectField('缺席類型', choices=[('事假', '事假'), ('病假', '病假'), ('無故缺席', '無故缺席'), ('其他', '其他')], validators=[DataRequired()]) # 添加'其他'選項
    reason = TextAreaField('原因 (可選)', validators=[Optional(), Length(max=500)]) # 添加長度限制
    proof = FileField('證明文件 (可選)', validators=[FileAllowed(['jpg', 'png', 'pdf', 'doc', 'docx'], '只允許圖片、PDF和Word文件!'), Optional()]) # 允許更多文件類型，並設定為 Optional
    submit = SubmitField('記錄缺席')

class EditAbsenceForm(FlaskForm):
    """修改缺席記錄表單"""
    absence_date = DateField('缺席日期', format='%Y-%m-%d', validators=[DataRequired()]) # 指定日期格式
    session_count = IntegerField('缺席節數', validators=[DataRequired(), NumberRange(min=1)])
    absence_type = SelectField('缺席類型', choices=[('事假', '事假'), ('病假', '病假'), ('無故缺席', '無故缺席'), ('其他', '其他')], validators=[DataRequired()]) # 添加'其他'選項
    reason = TextAreaField('原因 (可選)', validators=[Optional(), Length(max=500)]) # 添加長度限制
    proof = FileField('證明文件 (可選)', validators=[FileAllowed(['jpg', 'png', 'pdf', 'doc', 'docx'], '只允許圖片、PDF和Word文件!'), Optional()]) # 允許更多文件類型，並設定為 Optional
    # delete_proof = BooleanField('刪除現有證明') # 這個欄位通常直接在模板中使用 input type="checkbox" 來處理
    submit = SubmitField('更新記錄')


class RecordAwardPunishForm(FlaskForm):
    """記錄獎懲表單"""
    record_date = DateField('記錄日期', format='%Y-%m-%d', validators=[DataRequired()]) # 指定日期格式
    record_type = SelectField('獎懲類型', choices=[('表揚', '表揚'), ('優點', '優點'), ('小功', '小功'), ('大功', '大功'), ('警告', '警告'), ('缺點', '缺點'), ('小過', '小過'), ('大過', '大過')], validators=[DataRequired()])
    description = TextAreaField('描述', validators=[DataRequired(), Length(max=1000)]) # 添加長度限制
    proof = FileField('證明文件 (可選)', validators=[FileAllowed(['jpg', 'png', 'pdf', 'doc', 'docx'], '只允許圖片、PDF和Word文件!'), Optional()]) # 允許更多文件類型，並設定為 Optional
    submit = SubmitField('記錄獎懲')

class EditAwardPunishForm(FlaskForm):
    """修改獎懲記錄表單"""
    record_date = DateField('記錄日期', format='%Y-%m-%d', validators=[DataRequired()]) # 指定日期格式
    record_type = SelectField('獎懲類型', choices=[('表揚', '表揚'), ('優點', '優點'), ('小功', '小功'), ('大功', '大功'), ('警告', '警告'), ('缺點', '缺點'), ('小過', '小過'), ('大過', '大過')], validators=[DataRequired()])
    description = TextAreaField('描述', validators=[DataRequired(), Length(max=1000)]) # 添加長度限制
    proof = FileField('證明文件 (可選)', validators=[FileAllowed(['jpg', 'png', 'pdf', 'doc', 'docx'], '只允許圖片、PDF和Word文件!'), Optional()]) # 允許更多文件類型，並設定為 Optional
    submit = SubmitField('更新記錄')


class RecordCompetitionForm(FlaskForm):
    """記錄參賽表單"""
    comp_date = DateField('參賽日期', format='%Y-%m-%d', validators=[DataRequired()]) # 指定日期格式
    comp_name = StringField('比賽名稱', validators=[DataRequired(), Length(max=255)])
    result = SelectField('結果', choices=[('參與', '參與'), ('入圍', '入圍'), ('得獎', '得獎')], validators=[DataRequired()])
    description = TextAreaField('描述/備註 (可選)', validators=[Optional(), Length(max=1000)]) # 添加長度限制
    proof = FileField('證明文件 (可選)', validators=[FileAllowed(['jpg', 'png', 'pdf', 'doc', 'docx'], '只允許圖片、PDF和Word文件!'), Optional()]) # 允許更多文件類型，並設定為 Optional
    submit = SubmitField('記錄參賽')

class EditCompetitionForm(FlaskForm):
    """修改參賽記錄表單"""
    comp_date = DateField('參賽日期', format='%Y-%m-%d', validators=[DataRequired()]) # 指定日期格式
    comp_name = StringField('比賽名稱', validators=[DataRequired(), Length(max=255)])
    result = SelectField('結果', choices=[('參與', '參與'), ('入圍', '入圍'), ('得獎', '得獎')], validators=[DataRequired()])
    description = TextAreaField('描述/備註 (可選)', validators=[Optional(), Length(max=1000)]) # 添加長度限制
    proof = FileField('證明文件 (可選)', validators=[FileAllowed(['jpg', 'png', 'pdf', 'doc', 'docx'], '只允許圖片、PDF和Word文件!'), Optional()]) # 允許更多文件類型，並設定為 Optional
    submit = SubmitField('更新記錄')

# 記錄遲到表單
class RecordLateForm(FlaskForm):
    """記錄遲到表單"""
    late_date = DateField('遲到日期', format='%Y-%m-%d', validators=[DataRequired()]) # 指定日期格式
    reason = TextAreaField('原因 (可選)', validators=[Optional(), Length(max=500)]) # 添加長度限制
    submit = SubmitField('記錄遲到')

# 修改遲到記錄表單
class EditLateForm(FlaskForm):
    """修改遲到記錄表單"""
    late_date = DateField('遲到日期', format='%Y-%m-%d', validators=[DataRequired()]) # 指定日期格式
    reason = TextAreaField('原因 (可選)', validators=[Optional(), Length(max=500)]) # 添加長度限制
    submit = SubmitField('更新記錄')

# 記錄欠交功課表單
class RecordIncompleteHomeworkForm(FlaskForm):
    """記錄欠交功課表單"""
    record_date = DateField('記錄日期', format='%Y-%m-%d', validators=[DataRequired()]) # 指定日期格式
    subject = StringField('科目 (可選)', validators=[Optional(), Length(max=100)]) # 添加長度限制
    description = TextAreaField('描述/備註 (可選)', validators=[Optional(), Length(max=500)]) # 添加長度限制
    submit = SubmitField('記錄欠交功課')

# 修改欠交功課記錄表單
class EditIncompleteHomeworkForm(FlaskForm):
    """修改欠交功課記錄表單"""
    record_date = DateField('記錄日期', format='%Y-%m-%d', validators=[DataRequired()]) # 指定日期格式
    subject = StringField('科目 (可選)', validators=[Optional(), Length(max=100)]) # 添加長度限制
    description = TextAreaField('描述/備註 (可選)', validators=[Optional(), Length(max=500)]) # 添加長度限制
    submit = SubmitField('更新記錄')


# CSV 導入表單
class CSVUploadForm(FlaskForm):
    """CSV 文件上傳表單"""
    csv_file = FileField('選擇 CSV 文件', validators=[
        DataRequired(),
        FileAllowed(['csv'], '只允許 CSV 文件!')
    ])
    submit = SubmitField('上傳並導入')
