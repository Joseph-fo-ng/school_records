// static/js/script.js

// 這個文件用於存放前端的 JavaScript 程式碼，以增加頁面的互動性。

// 確保 DOM 完全載入後再執行腳本
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM fully loaded and parsed');

    // 範例：處理班級選擇後的動態學生列表載入 (如果使用 AJAX 而非頁面跳轉)
    // 注意：目前的 Flask 路由設計是通過頁面跳轉來顯示學生列表，
    // 如果您希望實現無刷新載入，需要修改後端路由以返回 JSON 數據，並在這裡使用 AJAX 處理。
    const classSelect = document.getElementById('class_id'); // 假設班級選擇框的 ID 是 'class_id'
    if (classSelect) {
        classSelect.addEventListener('change', function() {
            const selectedClassId = this.value;
            if (selectedClassId) {
                // 這裡可以發送 AJAX 請求到後端獲取該班級的學生列表
                // 範例 (僅為示意，需要後端對應的 JSON 接口):
                // fetch(`/class/${selectedClassId}/students_json`)
                //     .then(response => response.json())
                //     .then(data => {
                //         // 在前端更新學生列表的 HTML
                //         console.log('學生列表數據:', data);
                //         // updateStudentList(data.students); // 調用一個函式來更新頁面上的學生列表
                //     })
                //     .catch(error => {
                //         console.error('獲取學生列表失敗:', error);
                //     });

                // 目前的實現是通過表單提交或鏈接跳轉，所以這裡可以不做任何事情
                // 或者如果班級選擇框在一個表單中，提交表單會觸發後端路由
            }
        });
    }

    // 範例：文件上傳區域的互動效果 (如果使用自定義文件上傳區域)
    const fileUploadArea = document.querySelector('.file-upload-area');
    const fileInput = document.querySelector('.file-upload-area input[type="file"]');
    const fileInfo = document.querySelector('.file-upload-area p'); // 用於顯示選中的文件名

    if (fileUploadArea && fileInput && fileInfo) {
        // 當點擊自定義區域時觸發文件輸入框的點擊事件
        fileUploadArea.addEventListener('click', function() {
            fileInput.click();
        });

        // 當文件輸入框的值改變時 (用戶選擇了文件)
        fileInput.addEventListener('change', function() {
            if (this.files && this.files.length > 0) {
                // 顯示選中的文件名
                fileInfo.textContent = `已選擇文件: ${this.files[0].name}`;
                // 您也可以在這裡添加文件預覽邏輯 (例如圖片預覽)
            } else {
                // 如果沒有選擇文件
                fileInfo.textContent = '或將文件拖放到此處';
            }
        });

        // 阻止默認的拖放行為，以便處理文件拖放上傳 (如果需要)
        fileUploadArea.addEventListener('dragover', function(e) {
            e.preventDefault();
            e.stopPropagation();
            fileUploadArea.classList.add('border-blue-500'); // 添加視覺效果
        });

        fileUploadArea.addEventListener('dragleave', function(e) {
            e.preventDefault();
            e.stopPropagation();
            fileUploadArea.classList.remove('border-blue-500');
        });

        fileUploadArea.addEventListener('drop', function(e) {
            e.preventDefault();
            e.stopPropagation();
            fileUploadArea.classList.remove('border-blue-500');

            const files = e.dataTransfer.files;
            if (files.length > 0) {
                // 將拖放的文件設置到文件輸入框中
                fileInput.files = files;
                 if (fileInput.files && fileInput.files.length > 0) {
                    fileInfo.textContent = `已選擇文件: ${fileInput.files[0].name}`;
                 }
                // 如果是單文件上傳，只處理第一個文件
                // 如果是多文件上傳，需要更複雜的處理
            }
        });
    }

    // 範例：客戶端表單驗證 (可選，Flask-WTF 已提供後端驗證)
    // 如果需要更即時的用戶反饋，可以在這裡添加 JavaScript 驗證邏輯。
    const recordForm = document.querySelector('form'); // 獲取頁面上的第一個表單
    if (recordForm) {
        recordForm.addEventListener('submit', function(event) {
            // 這裡可以添加客戶端驗證邏輯
            // 範例：檢查日期欄位是否填寫
            // const dateInput = recordForm.querySelector('input[type="date"]');
            // if (dateInput && !dateInput.value) {
            //     alert('請填寫日期！'); // 使用更友好的方式提示用戶，而不是 alert
            //     event.preventDefault(); // 阻止表單提交
            // }
            // 添加其他欄位的驗證...
        });
    }

    // 範例：消息閃現自動消失 (可選)
    const flashMessages = document.querySelectorAll('.flash-message');
    flashMessages.forEach(function(message) {
        setTimeout(function() {
            message.style.transition = 'opacity 0.5s ease';
            message.style.opacity = '0';
            setTimeout(function() {
                message.remove(); // 漸隱後移除元素
            }, 500); // 過渡時間
        }, 5000); // 5秒後開始漸隱
    });

});

// 您可以在這裡添加其他 JavaScript 函式，例如：
// function updateStudentList(students) {
//     // 根據獲取的學生數據更新頁面上的學生列表 HTML
// }

// function previewImage(file) {
//     // 預覽圖片文件
// }
