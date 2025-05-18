# app/models.py
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash # 導入 generate_password_hash
import mysql.connector
from app.__init__ import get_db # 導入資料庫連接函式
from flask import current_app # 導入 current_app 以使用 logger

# Flask-Login 需要一個 user_loader 函數 (通常放在 __init__.py 或其他應用程式初始化的地方)
# 這個函數告訴 Flask-Login 如何從使用者 ID 加載使用者對象
# 示例 (假設在 __init__.py 中):
# @login_manager.user_loader
# def load_user(user_id):
#     conn = get_db()
#     if conn:
#         cursor = conn.cursor(dictionary=True)
#         try:
#             cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
#             user_data = cursor.fetchone()
#             if user_data:
#                 return User(user_data)
#         except Exception as e:
#             current_app.logger.error(f"Error loading user: {e}")
#         finally:
#             if conn and conn.is_connected():
#                 cursor.close()
#                 conn.close()
#     return None


# User 類別繼承自 Flask-Login 的 UserMixin，提供了使用者物件所需的基本屬性和方法
class User(UserMixin):
    """
    使用者模型。
    屬性與資料庫中的 users 表相對應。
    """
    def __init__(self, user_data):
        """
        使用從資料庫獲取的使用者數據初始化 User 物件。
        Args:
            user_data (dict): 包含使用者資料的字典，通常來自資料庫查詢結果。
                              期望包含 user_id, username, password_hash, role, teacher_name, id_card_number。
        """
        self.id = user_data['user_id'] # Flask-Login 需要一個名為 'id' 的屬性，對應資料庫的 user_id
        self.username = user_data['username']
        self.password_hash = user_data['password_hash']
        self.role = user_data['role']
        self.teacher_name = user_data.get('teacher_name') # 使用 get 以處理可能為 None 的情況
        self.id_card_number = user_data.get('id_card_number') # 使用 get 以處理可能為 None 的情況

        # 如果需要，可以在這裡加載或初始化與使用者相關的其他數據
        # 例如：教師負責的班級
        # self.assigned_classes = self._load_assigned_classes()


    def __repr__(self):
        return f'<User {self.username}>'

    # 密碼處理方法
    def set_password(self, password):
        """設定使用者密碼，使用哈希加密"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """檢查提供的密碼是否與儲存的哈希值匹配"""
        return check_password_hash(self.password_hash, password)

    # 角色檢查方法
    def is_admin(self):
        """檢查使用者是否為管理員"""
        return self.role == 'admin'

    def is_supervisor(self):
        """檢查使用者是否為主管"""
        return self.role == 'supervisor'

    def is_teacher(self):
        """檢查使用者是否為教師"""
        return self.role == 'teacher'

    # 獲取教師負責的班級列表
    @property
    def assigned_classes(self):
        """
        如果使用者是教師，返回其負責的班級列表；否則返回空列表。
        返回的列表中的每個元素是包含 class_id 和 class_name 的字典。
        這個屬性會在每次訪問時執行資料庫查詢，如果需要頻繁訪問，可以考慮在加載用戶時緩存。
        """
        if self.is_teacher():
            conn = get_db()
            classes = []
            if conn:
                cursor = conn.cursor(dictionary=True)
                try:
                    cursor.execute("""
                        SELECT c.class_id, c.class_name
                        FROM classes c
                        JOIN teacher_classes tc ON c.class_id = tc.class_id
                        WHERE tc.user_id = %s
                        ORDER BY c.class_name
                    """, (self.id,)) # 使用 self.id (user_id)
                    classes = cursor.fetchall()
                except mysql.connector.Error as err:
                    current_app.logger.error(f"資料庫錯誤 (獲取教師負責班級): {err}")
                    # 這裡不閃現錯誤，因為這是在模型方法中
                finally:
                     if conn and conn.is_connected():
                          cursor.close()
                          conn.close()
            return classes
        return [] # 如果不是教師，返回空列表


# --- 其他資料表對應的模型類別骨架 ---
# 這些類別主要是為了程式碼結構清晰，並未實現 ORM 功能
# 它們用於將資料庫查詢結果轉換為具有屬性的物件

class SchoolClass: # 將 Class 改名為 SchoolClass
    """班級模型骨架，對應資料庫中的 classes 表"""
    def __init__(self, data):
        """
        使用字典數據初始化 SchoolClass 對象。
        Args:
            data (dict): 包含班級資料的字典，通常來自資料庫查詢結果。
                         期望包含 class_id, class_name。
        """
        self.class_id = data.get('class_id')
        self.class_name = data.get('class_name')
        # 您可以根據需要在這裡添加更多屬性或方法

class Student:
    """學生模型骨架，對應資料庫中的 students 表"""
    def __init__(self, data):
        """
        使用字典數據初始化 Student 對象。
        Args:
            data (dict): 包含學生資料的字典，通常來自資料庫查詢結果。
                         期望包含 student_id, student_number, name, class_id, id_card_number,
                         student_id_number, late_count, incomplete_homework_count,
                         violation_points, award_points。
        """
        self.student_id = data.get('student_id')
        self.student_number = data.get('student_number')
        self.name = data.get('name')
        self.class_id = data.get('class_id')
        self.id_card_number = data.get('id_card_number')
        self.student_id_number = data.get('student_id_number')
        self.late_count = data.get('late_count', 0) # 設置預設值為 0
        self.incomplete_homework_count = data.get('incomplete_homework_count', 0) # 設置預設值為 0
        self.violation_points = data.get('violation_points', 0) # 設置預設值為 0
        self.award_points = data.get('award_points', 0) # 設置預設值為 0
        # 您可以根據需要在這裡添加更多屬性或方法

    # 獲取學生所屬班級的名稱 (如果需要頻繁在模板中顯示，可以考慮在查詢時 JOIN)
    # 這裡提供一個通過查詢獲取班級名稱的方法作為示例
    @property
    def class_name(self):
         conn = get_db()
         class_name = None
         if conn:
              cursor = conn.cursor()
              try:
                   cursor.execute("SELECT class_name FROM classes WHERE class_id = %s", (self.class_id,))
                   result = cursor.fetchone()
                   if result:
                        class_name = result[0]
              except mysql.connector.Error as err:
                   current_app.logger.error(f"資料庫錯誤 (獲取班級名稱 for Student {self.student_id}): {err}")
              finally:
                   if conn and conn.is_connected():
                        cursor.close()
                        conn.close()
         return class_name


class Absence:
    """缺席記錄模型骨架，對應資料庫中的 absences 表"""
    def __init__(self, data):
        """
        使用字典數據初始化 Absence 對象。
        Args:
            data (dict): 包含缺席記錄資料的字典，通常來自資料庫查詢結果。
                         期望包含 absence_id, student_id, absence_date, session_count, type,
                         reason, upload_path, recorded_by_user_id, recorded_at。
        """
        self.absence_id = data.get('absence_id')
        self.student_id = data.get('student_id')
        self.absence_date = data.get('absence_date')
        self.session_count = data.get('session_count')
        self.type = data.get('type')
        self.reason = data.get('reason')
        self.upload_path = data.get('upload_path')
        self.recorded_by_user_id = data.get('recorded_by_user_id')
        self.recorded_at = data.get('recorded_at')
        # 您可以根據需要在這裡添加更多屬性或方法


class AwardPunishment:
    """獎懲記錄模型骨架，對應資料庫中的 awards_punishments 表"""
    def __init__(self, data):
        """
        使用字典數據初始化 AwardPunishment 對象。
        Args:
            data (dict): 包含獎懲記錄資料的字典，通常來自資料庫查詢結果。
                         期望包含 record_id, student_id, record_date, type, description,
                         upload_path, recorded_by_user_id, recorded_at。
        """
        self.record_id = data.get('record_id')
        self.student_id = data.get('student_id')
        self.record_date = data.get('record_date')
        self.type = data.get('type')
        self.description = data.get('description')
        self.upload_path = data.get('upload_path')
        self.recorded_by_user_id = data.get('recorded_by_user_id')
        self.recorded_at = data.get('recorded_at')
        # 您可以根據需要在這裡添加更多屬性或方法


class Competition:
    """參賽記錄模型骨架，對應資料庫中的 competitions 表"""
    def __init__(self, data):
        """
        使用字典數據初始化 Competition 對象。
        Args:
            data (dict): 包含參賽記錄資料的字典，通常來自資料庫查詢結果。
                         期望包含 comp_record_id, student_id, comp_date, comp_name,
                         result, description, upload_path, recorded_by_user_id, recorded_at。
        """
        self.comp_record_id = data.get('comp_record_id')
        self.student_id = data.get('student_id')
        self.comp_date = data.get('comp_date')
        self.comp_name = data.get('comp_name')
        self.result = data.get('result')
        self.description = data.get('description')
        self.upload_path = data.get('upload_path')
        self.recorded_by_user_id = data.get('recorded_by_user_id')
        self.recorded_at = data.get('recorded_at')
        # 您可以根據需要在這裡添加更多屬性或方法


class LateRecord:
    """遲到記錄模型骨架，對應資料庫中的 late_records 表"""
    def __init__(self, data):
        """
        使用字典數據初始化 LateRecord 對象。
        Args:
            data (dict): 包含遲到記錄資料的字典，通常來自資料庫查詢結果。
                         期望包含 late_id, student_id, late_date, reason,
                         recorded_by_user_id, recorded_at。
        """
        self.late_id = data.get('late_id')
        self.student_id = data.get('student_id')
        self.late_date = data.get('late_date')
        self.reason = data.get('reason')
        self.recorded_by_user_id = data.get('recorded_by_user_id')
        self.recorded_at = data.get('recorded_at')
        # 您可以根據需要在這裡添加更多屬性或方法


class IncompleteHomeworkRecord:
    """欠交功課記錄模型骨架，對應資料庫中的 incomplete_homework_records 表"""
    def __init__(self, data):
        """
        使用字典數據初始化 IncompleteHomeworkRecord 對象。
        Args:
            data (dict): 包含欠交功課記錄資料的字典，通常來自資料庫查詢結果。
                         期望包含 incomplete_hw_id, student_id, record_date, subject,
                         description, recorded_by_user_id, recorded_at。
        """
        self.incomplete_hw_id = data.get('incomplete_hw_id')
        self.student_id = data.get('student_id')
        self.record_date = data.get('record_date')
        self.subject = data.get('subject')
        self.description = data.get('description')
        self.recorded_by_user_id = data.get('recorded_by_user_id')
        self.recorded_at = data.get('recorded_at')
        # 您可以根據需要在這裡添加更多屬性或方法

# 關聯表模型骨架 (如果需要)
class TeacherClass:
    """教師與班級關聯模型骨架，對應資料庫中的 teacher_classes 表"""
    def __init__(self, data):
        """
        使用字典數據初始化 TeacherClass 對象。
        Args:
            data (dict): 包含關聯資料的字典，通常來自資料庫查詢結果。
                         期望包含 user_id, class_id。
        """
        self.user_id = data.get('user_id')
        self.class_id = data.get('class_id')
        # 您可以根據需要在這裡添加更多屬性或方法

