# app/__init__.py
import os
from flask import Flask
# 修正導入方式：直接導入 config 模組
import config # 從 config.py 導入 config 模組
from flask_login import LoginManager
import mysql.connector # 導入 MySQL 連接庫
# 導入 Flask-Moment
from flask_moment import Moment
from datetime import datetime # 導入 datetime 模組
# 導入 generate_password_hash 用於初始化管理員密碼示例
from werkzeug.security import generate_password_hash

# 初始化 Flask-Login
login_manager = LoginManager()
# 設定登入視圖函式名稱，當使用者需要登入時，Flask-Login 會重定向到此視圖
login_manager.login_view = 'auth.login' # 假設我們有一個名為 'auth' 的藍圖，其中包含 'login' 路由
# 設定登入提示訊息的類別
login_manager.login_message_category = 'info'

# 初始化 Flask-Moment
moment = Moment()

# 資料庫連接函式
# 這裡提供一個簡單的連接函式，您可能需要根據實際情況進行更複雜的連接池管理
def get_db():
    """建立並返回一個資料庫連接"""
    try:
        # 修正：使用 config.變數名 來訪問配置
        conn = mysql.connector.connect(
            host=config.MYSQL_HOST,
            user=config.MYSQL_USER,
            password=config.MYSQL_PASSWORD,
            database=config.MYSQL_DB
        )
        return conn
    except mysql.connector.Error as err:
        print(f"資料庫連接錯誤: {err}")
        # 在實際應用中，您可能需要更優雅地處理這個錯誤
        return None

def init_db(app):
    """
    初始化資料庫：檢查並創建資料庫表 (如果不存在)
    這個函式應該在應用程式啟動時，在應用程式上下文中執行一次。
    """
    conn = get_db()
    if conn:
        cursor = conn.cursor()
        try:
            # 檢查 classes 表是否存在作為一個簡單的判斷標誌
            # 修正：檢查 school_records_db 數據庫是否存在
            cursor.execute(f"SHOW DATABASES LIKE '{config.MYSQL_DB}'")
            db_exists = cursor.fetchone()

            if not db_exists:
                print(f"資料庫 '{config.MYSQL_DB}' 不存在，正在創建...")
                cursor.execute(f"CREATE DATABASE {config.MYSQL_DB} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                print(f"資料庫 '{config.MYSQL_DB}' 創建成功。")
                conn.database = config.MYSQL_DB # 切換到新創建的資料庫


            # 檢查 classes 表是否存在
            cursor.execute("SHOW TABLES LIKE 'classes'")
            table_exists = cursor.fetchone()

            if not table_exists:
                print("資料庫表不存在，正在創建...")
                # 讀取 schema.sql 文件並執行
                # 假設 schema.sql 位於專案根目錄
                schema_path = os.path.join(app.root_path, '..', 'schema.sql') # 調整路徑以找到 schema.sql
                if not os.path.exists(schema_path):
                    print(f"錯誤：找不到 schema.sql 文件於 {schema_path}")
                    return # 如果找不到 schema 文件，停止初始化

                with open(schema_path, 'r', encoding='utf-8') as f:
                    sql_script = f.read()

                # 分割 SQL 語句並執行
                # 這裡簡單地按分號分割，可能不適用於所有複雜的 SQL 腳本
                # 需要過濾掉 CREATE DATABASE 和 USE 語句，因為我們已經手動處理了
                statements = [s.strip() for s in sql_script.split(';') if s.strip()]
                for statement in statements:
                    # 跳過 CREATE DATABASE 和 USE 語句
                    if statement.upper().startswith('CREATE DATABASE') or statement.upper().startswith('USE'):
                         continue
                    try:
                        cursor.execute(statement)
                    except mysql.connector.Error as err:
                        print(f"執行 SQL 語句時發生錯誤: {err}")
                        # 根據需要處理錯誤，例如停止應用程式或記錄錯誤
                        conn.rollback() # 回滾可能的部分更改
                        # 這裡不 break，嘗試執行所有語句以提供更多錯誤信息
                conn.commit()
                print("資料庫表創建完成。")
            else:
                print("資料庫表已存在，跳過創建。")

        except mysql.connector.Error as err:
            print(f"資料庫初始化錯誤: {err}")
        finally:
            cursor.close()
            conn.close()
    else:
        print("無法連接到資料庫，無法初始化。請檢查您的資料庫配置和伺服器狀態。")


# 應用程式工廠函式
# 修正：移除 config_class 參數，直接使用導入的 config 模組
def create_app():
    """
    創建並配置 Flask 應用程式實例
    """
    app = Flask(__name__)
    # 從導入的 config 模組載入設定
    # 修正：使用 from_object 載入 config 模組本身
    app.config.from_object(config)

    # 初始化 Flask 擴展
    login_manager.init_app(app)
    moment.init_app(app) # 初始化 Flask-Moment

    # 將 datetime 對象添加到模板上下文
    @app.context_processor
    def inject_datetime():
        return dict(datetime=datetime)


    # 定義使用者載入器 (User Loader)
    # 這個函式會被 Flask-Login 用來從 session 中載入使用者對象
    @login_manager.user_loader
    def load_user(user_id):
        """根據使用者 ID 從資料庫載入使用者"""
        from app.models import User # 在函式內部導入，避免循環依賴
        conn = get_db()
        user = None
        if conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
                user_data = cursor.fetchone()
                if user_data:
                    user = User(user_data)
            except mysql.connector.Error as err:
                print(f"Error loading user: {err}")
            finally:
                # 在 user_loader 中通常不關閉連接，而是讓應用程式上下文自動處理
                # 如果需要手動關閉，請謹慎操作，避免影響請求生命週期
                if conn and conn.is_connected():
                    cursor.close()
                    # conn.close() # 不在這裡關閉
                pass # 保持連接打開，由應用程式上下文管理

        return user

    # 註冊藍圖 (Blueprints)
    # 藍圖用於組織應用程式的不同部分 (例如認證、主要功能、管理功能)
    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth') # 認證相關路由，如 /auth/login, /auth/logout

    # 修正：從 app.main 導入 main_bp
    from app.main import main_bp
    app.register_blueprint(main_bp) # 主要應用功能路由，如 /, /dashboard, /students

    from app.admin import bp as admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin') # 管理員功能路由，如 /admin/users, /admin/students

    # 確保上傳文件夾存在 (也可以放在 run.py 中處理)
    # 這裡再次檢查是為了確保在任何情況下都存在
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])

    # 在應用程式啟動時初始化資料庫 (檢查並創建表)
    # 注意：這會在每次應用程式啟動時執行，對於生產環境可能需要更精細的控制
    # 例如，可以添加一個配置標誌來控制是否執行初始化
    with app.app_context(): # 確保在應用程式上下文中執行
        init_db(app)


    # 您可以在這裡添加其他初始化步驟，例如註冊錯誤處理函式等

    return app
