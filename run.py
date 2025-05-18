import os
from app import create_app

from config import UPLOAD_FOLDER
app = create_app()

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
    print(f"Created upload folder: {UPLOAD_FOLDER}")

# 如果直接運行此腳本，則啟動開發伺服器
if __name__ == '__main__':
    app.run(debug=True)
