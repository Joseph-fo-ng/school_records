import os
SECRET_KEY = os.environ.get('SECRET_KEY') or 'a-very-hard-to-guess-default-key-please-change-in-production'

MYSQL_HOST = '192.168.1.41'  # 資料庫主機位址，如果是遠程資料庫，請修改為對應的 IP 或域名
MYSQL_USER = 'admin' # <<<<<< 請將這裡替換為您的 MySQL 使用者名稱
MYSQL_PASSWORD = 'cdsj' # <<<<<< 請將這裡替換為您的 MySQL 密碼
MYSQL_DB = 'school_records_db' # <<<<<< 請將這裡替換為您的資料庫名稱 (需要先創建)

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx'}

# 檢查文件擴展名是否允許
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# 您可以在這裡添加其他設定，例如：
# DEBUG = True # 開啟或關閉調試模式
# MAIL_SERVER = 'smtp.example.com'
# MAIL_PORT = 587
# MAIL_USE_TLS = True
# MAIL_USERNAME = 'your-email@example.com'
# MAIL_PASSWORD = 'your-email-password'
