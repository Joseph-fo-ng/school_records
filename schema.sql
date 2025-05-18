-- school_records_db 資料庫的 schema

-- 創建資料庫 (如果不存在)
CREATE DATABASE IF NOT EXISTS school_records_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 使用剛創建或已存在的資料庫
USE school_records_db;

-- 刪除現有的表格 (如果存在)，以便重新創建
DROP TABLE IF EXISTS teacher_classes;
DROP TABLE IF EXISTS absences;
DROP TABLE IF EXISTS awards_punishments;
DROP TABLE IF EXISTS competitions;
DROP TABLE IF EXISTS late_records;
DROP TABLE IF EXISTS incomplete_homework_records;
DROP TABLE IF EXISTS students;
DROP TABLE IF EXISTS classes;
DROP TABLE IF EXISTS users;


-- 創建 users 表格
-- user_id: 使用者唯一識別碼 (自動生成數字)
-- username: 使用者名稱 (唯一)
-- password_hash: 密碼的雜湊值
-- role: 使用者角色 (admin, supervisor, teacher)
-- teacher_name: 教師姓名 (只有教師角色需要)
-- id_card_number: ID 卡號碼 (可選，唯一)
CREATE TABLE users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('admin', 'supervisor', 'teacher') NOT NULL,
    teacher_name VARCHAR(100),
    id_card_number VARCHAR(50) UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 創建 classes 表格
-- class_id: 班級唯一識別碼 (自動生成數字)
-- class_name: 班級名稱 (唯一)
CREATE TABLE classes (
    class_id INT AUTO_INCREMENT PRIMARY KEY,
    class_name VARCHAR(10) UNIQUE NOT NULL
);

-- 創建 students 表格
-- student_id: 學生唯一識別碼 (自動生成數字)
-- student_number: 學號 (可選，在班級內唯一)
-- name: 學生姓名
-- class_id: 學生所屬班級 (外鍵參考 classes 表格的 class_id)
-- id_card_number: ID 卡號碼 (可選，唯一)
-- student_id_number: 學生證號碼 (可選，唯一)
-- late_count: 遲到次數計數
-- incomplete_homework_count: 欠交功課次數計數
-- violation_points: 違規點數計數
-- award_points: 獎勵點數計數
CREATE TABLE students (
    student_id INT AUTO_INCREMENT PRIMARY KEY,
    student_number VARCHAR(20),
    name VARCHAR(100) NOT NULL,
    class_id INT NOT NULL,
    id_card_number VARCHAR(50) UNIQUE,
    student_id_number VARCHAR(50) UNIQUE,
    late_count INT DEFAULT 0,
    incomplete_homework_count INT DEFAULT 0,
    violation_points INT DEFAULT 0,
    award_points INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (class_id) REFERENCES classes(class_id) ON DELETE RESTRICT, -- 班級刪除時限制
    UNIQUE KEY unique_student_number_in_class (student_number, class_id) -- 確保學號在同一班級內唯一
);

-- 創建 teacher_classes 關聯表格
-- 用於記錄教師負責哪些班級 (多對多關係)
-- user_id: 教師使用者 ID (外鍵參考 users 表格的 user_id)
-- class_id: 班級 ID (外鍵參考 classes 表格的 class_id)
CREATE TABLE teacher_classes (
    user_id INT NOT NULL,
    class_id INT NOT NULL,
    PRIMARY KEY (user_id, class_id), -- 複合主鍵
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE, -- 使用者刪除時，刪除其班級關聯
    FOREIGN KEY (class_id) REFERENCES classes(class_id) ON DELETE CASCADE -- 班級刪除時，刪除其教師關聯
);


-- 創建 absences 表格 (缺席記錄)
-- absence_id: 缺席記錄唯一識別碼 (自動生成)
-- student_id: 學生 ID (外鍵參考 students 表格的 student_id)
-- absence_date: 缺席日期
-- session_count: 缺席節數
-- type: 缺席類型 (事假, 病假, 無故缺席等)
-- reason: 缺席原因
-- upload_path: 證明文件上傳路徑
-- recorded_at: 記錄時間
-- recorded_by_user_id: 記錄者使用者 ID (外鍵參考 users 表格的 user_id)
CREATE TABLE absences (
    absence_id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    absence_date DATE NOT NULL,
    session_count INT NOT NULL,
    type VARCHAR(50) NOT NULL,
    reason TEXT,
    upload_path VARCHAR(255),
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    recorded_by_user_id INT NOT NULL,
    FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE, -- 學生刪除時，刪除其缺席記錄
    FOREIGN KEY (recorded_by_user_id) REFERENCES users(user_id) ON DELETE RESTRICT -- 記錄者使用者刪除時限制
);

-- 創建 awards_punishments 表格 (獎懲記錄)
-- record_id: 獎懲記錄唯一識別碼 (自動生成)
-- student_id: 學生 ID (外鍵參考 students 表格的 student_id)
-- record_date: 記錄日期
-- type: 獎懲類型 (表揚, 優點, 小功, 大功, 警告, 缺點, 小過, 大過)
-- description: 描述
-- upload_path: 證明文件上傳路徑
-- recorded_at: 記錄時間
-- recorded_by_user_id: 記錄者使用者 ID (外鍵參考 users 表格的 user_id)
CREATE TABLE awards_punishments (
    record_id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    record_date DATE NOT NULL,
    type VARCHAR(50) NOT NULL,
    description TEXT NOT NULL,
    upload_path VARCHAR(255),
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    recorded_by_user_id INT NOT NULL,
    FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE, -- 學生刪除時，刪除其獎懲記錄
    FOREIGN KEY (recorded_by_user_id) REFERENCES users(user_id) ON DELETE RESTRICT -- 記錄者使用者刪除時限制
);

-- 創建 competitions 表格 (參賽記錄)
-- comp_record_id: 參賽記錄唯一識別碼 (自動生成)
-- student_id: 學生 ID (外鍵參考 students 表格的 student_id)
-- comp_date: 參賽日期
-- comp_name: 比賽名稱
-- result: 結果 (參與, 入圍, 得獎)
-- description: 描述/備註
-- upload_path: 證明文件上傳路徑
-- recorded_at: 記錄時間
-- recorded_by_user_id: 記錄者使用者 ID (外鍵參考 users 表格的 user_id)
CREATE TABLE competitions (
    comp_record_id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    comp_date DATE NOT NULL,
    comp_name VARCHAR(255) NOT NULL,
    result ENUM('參與', '入圍', '得獎') NOT NULL,
    description TEXT,
    upload_path VARCHAR(255),
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    recorded_by_user_id INT NOT NULL,
    FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE, -- 學生刪除時，刪除其參賽記錄
    FOREIGN KEY (recorded_by_user_id) REFERENCES users(user_id) ON DELETE RESTRICT -- 記錄者使用者刪除時限制
);

-- 創建 late_records 表格 (遲到記錄)
-- late_id: 遲到記錄唯一識別碼 (自動生成)
-- student_id: 學生 ID (外鍵參考 students 表格的 student_id)
-- late_date: 遲到日期
-- reason: 原因
-- recorded_at: 記錄時間
-- recorded_by_user_id: 記錄者使用者 ID (外鍵參考 users 表格的 user_id)
CREATE TABLE late_records (
    late_id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL, -- Foreign Key to students(student_id)
    late_date DATE NOT NULL,
    reason TEXT,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    recorded_by_user_id INT NOT NULL, -- Foreign Key to users(user_id)
    FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE, -- 學生刪除時，刪除其遲到記錄
    FOREIGN KEY (recorded_by_user_id) REFERENCES users(user_id) ON DELETE RESTRICT -- 記錄者使用者刪除時限制
);

-- 創建 incomplete_homework_records 表格 (欠交功課記錄)
-- incomplete_hw_id: 欠交功課記錄唯一識別碼 (自動生成)
-- student_id: 學生 ID (外鍵參考 students 表格的 student_id)
-- record_date: 記錄日期
-- subject: 科目
-- description: 描述/備註
-- recorded_at: 記錄時間
-- recorded_by_user_id: 記錄者使用者 ID (外鍵參考 users 表格的 user_id)
CREATE TABLE incomplete_homework_records (
    incomplete_hw_id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL, -- Foreign Key to students(student_id)
    record_date DATE NOT NULL,
    subject VARCHAR(100),
    description TEXT,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    recorded_by_user_id INT NOT NULL, -- Foreign Key to users(user_id)
    FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE, -- 學生刪除時，刪除其欠交功課記錄
    FOREIGN KEY (recorded_by_user_id) REFERENCES users(user_id) ON DELETE RESTRICT -- 記錄者使用者刪除時限制
);

-- 插入一個預設管理員使用者 (請在實際部署時更改密碼！)
-- 密碼 'admin_password' 的雜湊值，請替換為您自己生成的雜湊值
-- 您可以使用 Flask 的 generate_password_hash('您的密碼') 來生成
-- 這裡使用一個示例雜湊值，您需要替換它
INSERT INTO users (username, password_hash, role, teacher_name, id_card_number) VALUES ('admin','scrypt:32768:8:1$3joQ2X38l7UYcYW4$fd38948c8a94fa823cb887c02b6aa5f07772d5750d9f1a9ff1f5f73eedf40aa098593dc6cc74a67100a6a1e3b90652a8dc20504676882e223213b93b9b6a1a52', 'admin', NULL, NULL);
