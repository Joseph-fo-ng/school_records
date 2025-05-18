from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash # 導入用於檢查密碼雜湊的函式
import mysql.connector # 導入資料庫連接庫

# 導入資料庫連接函式和 User 模型
from app.__init__ import get_db
from app.models import User # 假設 User 類在 app/models.py 中定義
from app.forms import LoginForm # 假設 LoginForm 在 app/forms.py 中定義

# 創建一個藍圖實例，命名為 'auth'
# url_prefix='/auth' 會為此藍圖中的所有路由添加前綴 /auth
bp = Blueprint('auth', __name__, url_prefix='/auth')

@bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    處理使用者登入。
    GET 請求顯示登入表單。
    POST 請求處理表單提交並驗證使用者。
    """
    # 如果使用者已經登入，重定向到儀表板
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard')) # 假設 main 藍圖中有一個 dashboard 路由

    form = LoginForm() # 創建登入表單實例

    if form.validate_on_submit(): # 驗證表單數據是否有效 (POST 請求且 CSRF token 有效)
        username = form.username.data
        password = form.password.data
        remember = form.remember_me.data

        conn = get_db()
        if conn:
            cursor = conn.cursor(dictionary=True) # 使用 dictionary=True 可以按欄位名獲取資料
            try:
                # 從資料庫查詢使用者
                cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
                user_data = cursor.fetchone()

                if user_data:
                    # 創建 User 對象並檢查密碼
                    user = User(user_data) # 使用 app.models.User 類
                    if user.check_password(password):
                        # 密碼正確，登入使用者
                        login_user(user, remember=remember)
                        # 登入成功後重定向到使用者之前嘗試訪問的頁面 (如果有)，或預設到儀表板
                        next_page = request.args.get('next')
                        flash('登入成功！', 'success')
                        return redirect(next_page or url_for('main.dashboard'))
                    else:
                        # 密碼不正確
                        flash('無效的使用者名稱或密碼', 'danger')
                else:
                    # 找不到使用者
                    flash('無效的使用者名稱或密碼', 'danger')

            except mysql.connector.Error as err:
                # 處理資料庫錯誤
                flash(f"資料庫錯誤: {err}", 'danger')
                print(f"資料庫錯誤 (登入): {err}") # 在控制台印出詳細錯誤以便調試
            finally:
                # 確保關閉游標和連接
                cursor.close()
                conn.close()
        else:
            # 無法連接到資料庫
            flash('無法連接到資料庫，請稍後再試。', 'danger')

    # 如果是 GET 請求或表單驗證失敗 (POST 請求)，渲染登入頁面模板
    return render_template('login.html', title='使用者登入', form=form)

@bp.route('/logout')
@login_required # 需要登入才能訪問此路由
def logout():
    """
    處理使用者登出。
    """
    logout_user() # 登出當前使用者
    flash('您已成功登出', 'info') # 閃現一個消息
    return redirect(url_for('auth.login')) # 重定向回登入頁面

# 您可以在這裡添加其他與認證相關的路由，例如註冊、忘記密碼等（如果需要）
