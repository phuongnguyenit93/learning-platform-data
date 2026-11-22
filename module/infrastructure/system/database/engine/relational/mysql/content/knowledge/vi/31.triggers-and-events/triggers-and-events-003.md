# Trigger cấp dòng và giới hạn so với trigger cấp câu lệnh

Trigger là stored program được MySQL tự động gọi khi một sự kiện INSERT, UPDATE hoặc DELETE xảy ra trên bảng. Điểm quan trọng trong MySQL là trigger luôn chạy ở cấp dòng: mỗi hàng được thao tác sẽ kích hoạt trigger tương ứng. MySQL không hỗ trợ trigger cấp câu lệnh (statement-level trigger), tức trigger chỉ chạy một lần cho toàn bộ câu SQL.

Sự khác biệt này ảnh hưởng trực tiếp đến thiết kế audit, kiểm tra dữ liệu, cập nhật bảng tổng hợp và hiệu năng của lệnh ghi nhiều hàng. Bài học thuộc module DATABASE_MYSQL này giúp bạn hiểu FOR EACH ROW, OLD/NEW, BEFORE/AFTER, số lần trigger chạy, giới hạn của trigger trong MySQL và các cách tổ chức logic cần thực hiện một lần cho cả câu lệnh.

## 1. Trigger cấp dòng là gì?

Trigger cấp dòng được khai báo với FOR EACH ROW. Khi một câu lệnh DML tác động đến nhiều hàng, phần thân trigger được thực thi riêng cho từng hàng.

Ví dụ:

~~~sql
UPDATE employees
SET salary = salary * 1.05
WHERE department_id = 10;
~~~

Nếu câu UPDATE tác động đến 200 hàng, trigger BEFORE UPDATE hoặc AFTER UPDATE tương ứng có thể được gọi 200 lần, mỗi lần gắn với một hàng. Trigger nhận được giá trị cũ và mới của hàng hiện tại qua OLD và NEW.

Nếu câu lệnh không tác động đến hàng nào, không có lần gọi row trigger nào. Nếu câu lệnh thêm 500 hàng bằng INSERT ... SELECT, trigger INSERT chạy theo từng hàng được chèn.

Trigger cấp dòng phù hợp với các việc cần xử lý theo từng bản ghi:

- Chuẩn hóa hoặc kiểm tra giá trị trước khi ghi.
- Ghi audit cho thay đổi của từng hàng.
- Duy trì một bảng phụ thuộc vào giá trị của từng hàng.
- Áp dụng quy tắc dữ liệu luôn phải được thực thi dù thao tác ghi đến từ ứng dụng nào.

## 2. MySQL không hỗ trợ trigger cấp câu lệnh

Một số hệ quản trị cơ sở dữ liệu có thể cung cấp hai loại trigger:

- Row-level trigger: chạy một lần cho mỗi hàng bị tác động.
- Statement-level trigger: chạy một lần cho toàn bộ câu lệnh DML, bất kể câu lệnh tác động bao nhiêu hàng.

MySQL chỉ hỗ trợ row-level trigger. Cú pháp CREATE TRIGGER yêu cầu FOR EACH ROW; không có lựa chọn FOR EACH STATEMENT.

| Tình huống | Trigger cấp dòng trong MySQL | Trigger cấp câu lệnh |
|---|---|---|
| UPDATE tác động 1 hàng | Chạy một lần | Nếu được hỗ trợ, chạy một lần |
| UPDATE tác động 200 hàng | Chạy 200 lần | Nếu được hỗ trợ, vẫn chỉ chạy một lần |
| UPDATE không tìm thấy hàng | Không chạy | Trong hệ hỗ trợ statement trigger, trigger có thể vẫn chạy một lần |
| INSERT ... SELECT thêm 500 hàng | Chạy theo 500 hàng được chèn | Nếu được hỗ trợ, chạy một lần |
| Cần biết tập tất cả hàng trước/sau câu lệnh | Chỉ thấy OLD/NEW của từng hàng | Một số hệ hỗ trợ transition table hoặc statement context |

Không thể đổi FOR EACH ROW thành một cú pháp khác để tạo statement trigger trong MySQL. Nếu nghiệp vụ cần chạy đúng một lần cho toàn bộ lệnh, hãy đặt bước đó trong stored procedure hoặc tầng ứng dụng điều phối DML.

## 3. Cú pháp CREATE TRIGGER

Cú pháp tổng quát:

~~~sql
CREATE
    [DEFINER = user]
    TRIGGER trigger_name
    trigger_time trigger_event
    ON table_name
    FOR EACH ROW
    trigger_body;
~~~

Trong đó:

- trigger_time là BEFORE hoặc AFTER.
- trigger_event là INSERT, UPDATE hoặc DELETE.
- table_name là bảng gắn trigger.
- FOR EACH ROW xác định trigger được gọi cho từng hàng.
- trigger_body thường là một câu lệnh hoặc khối BEGIN ... END.

Ví dụ trigger đơn giản:

Ví dụ giả định bảng employees đã tồn tại theo cấu trúc ở mục 6; hãy tạo bảng trước khi chạy CREATE TRIGGER.

~~~sql
DELIMITER //

CREATE TRIGGER trg_employees_bi_validate
BEFORE INSERT ON employees
FOR EACH ROW
BEGIN
    IF NEW.salary < 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Salary cannot be negative';
    END IF;
END//

DELIMITER ;
~~~

DELIMITER là lệnh của client MySQL để thay ký tự kết thúc câu lệnh khi gửi định nghĩa trigger có nhiều dấu chấm phẩy. Server nhận nội dung CREATE TRIGGER đã hoàn chỉnh; DELIMITER không phải câu lệnh SQL của server.

## 4. BEFORE và AFTER khác nhau thế nào?

MySQL hỗ trợ hai thời điểm kích hoạt:

- BEFORE: chạy trước khi thao tác hàng được áp dụng.
- AFTER: chạy sau khi thao tác hàng đã được thực hiện thành công.

Các event được hỗ trợ:

| Event | BEFORE | AFTER | Ý nghĩa |
|---|---|---|---|
| INSERT | Có | Có | Trước hoặc sau khi thêm một hàng |
| UPDATE | Có | Có | Trước hoặc sau khi thay đổi một hàng |
| DELETE | Có | Có | Trước hoặc sau khi xóa một hàng |

BEFORE thường dùng để kiểm tra hoặc chuẩn hóa dữ liệu sắp ghi. AFTER thường dùng để ghi audit hoặc cập nhật bảng khác dựa trên thay đổi đã xảy ra.

AFTER không có nghĩa transaction đã COMMIT. Trigger vẫn chạy trong ngữ cảnh của câu lệnh và transaction đang thực hiện. Nếu transaction bị rollback, các thay đổi transactional do trigger thực hiện cũng bị rollback.

## 5. OLD và NEW theo từng loại event

OLD và NEW là hai pseudo-record để tham chiếu giá trị của hàng:

| Event | OLD | NEW |
|---|---|---|
| INSERT | Không khả dụng | Hàng sắp được chèn hoặc vừa được chèn |
| UPDATE | Giá trị trước cập nhật | Giá trị sau cập nhật |
| DELETE | Hàng sắp bị xóa hoặc vừa bị xóa | Không khả dụng |

Ví dụ với UPDATE:

~~~sql
IF OLD.salary <> NEW.salary THEN
    -- Có thay đổi mức lương.
END IF;
~~~

Với INSERT, không đọc OLD vì không có hàng trước khi chèn. Với DELETE, không đọc NEW vì hàng mới không tồn tại. Tham chiếu pseudo-record không hợp lệ cho event tương ứng sẽ gây lỗi khi tạo hoặc thực thi trigger.

OLD là giá trị chỉ đọc. Trong BEFORE INSERT và BEFORE UPDATE, trigger có thể gán giá trị cho NEW.column để thay đổi hàng sẽ được ghi. Không thể gán OLD.column và không thể sửa NEW trong AFTER trigger.

## 6. Gán NEW trong BEFORE trigger

Giả sử bảng nguồn có cấu trúc sau:

~~~sql
CREATE TABLE employees (
    employee_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    employee_name VARCHAR(120) NOT NULL,
    department_id INT NOT NULL,
    employment_status VARCHAR(20) NOT NULL,
    salary DECIMAL(12,2) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (employee_id),
    KEY idx_employees_department (department_id)
) ENGINE=InnoDB;
~~~

Ví dụ chuẩn hóa tên nhân viên và đặt thời điểm cập nhật:

~~~sql
DELIMITER //

CREATE TRIGGER trg_employees_bi_normalize
BEFORE INSERT ON employees
FOR EACH ROW
BEGIN
    SET NEW.employee_name = TRIM(NEW.employee_name);

    IF NEW.employee_name IS NULL OR NEW.employee_name = '' THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Employee name is required';
    END IF;

    IF NEW.salary < 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Salary cannot be negative';
    END IF;
END//

CREATE TRIGGER trg_employees_bu_normalize
BEFORE UPDATE ON employees
FOR EACH ROW
BEGIN
    SET NEW.employee_name = TRIM(NEW.employee_name);
    SET NEW.updated_at = CURRENT_TIMESTAMP(6);

    IF NEW.employee_name IS NULL OR NEW.employee_name = '' THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Employee name is required';
    END IF;

    IF NEW.salary < 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Salary cannot be negative';
    END IF;
END//

DELIMITER ;
~~~

Trong BEFORE INSERT, NEW chứa giá trị ứng dụng cung cấp hoặc giá trị mặc định ban đầu. Nếu bảng dùng AUTO_INCREMENT, giá trị NEW của cột tự tăng có thể vẫn là 0 trong BEFORE INSERT; không dựa vào đó để lấy ID cuối cùng. Trong AFTER INSERT, giá trị AUTO_INCREMENT đã được tạo có thể được đọc qua NEW.

Nếu cần chuẩn hóa dữ liệu, hãy xác định quy tắc rõ ràng và nhất quán với collation, kiểu dữ liệu và validation ở tầng ứng dụng. Trigger không nên âm thầm biến đổi dữ liệu theo quy tắc mà caller không biết.

## 7. OLD/NEW để ghi audit theo từng hàng

Audit trigger thường là ví dụ điển hình cho row-level behavior. Mỗi lần một hàng thay đổi, trigger ghi một bản ghi lịch sử tương ứng.

Tạo bảng audit:

~~~sql
CREATE TABLE employee_salary_audit (
    audit_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    employee_id BIGINT UNSIGNED NOT NULL,
    old_salary DECIMAL(12,2) NOT NULL,
    new_salary DECIMAL(12,2) NOT NULL,
    changed_at DATETIME(6) NOT NULL,
    connection_user VARCHAR(288) NOT NULL,
    PRIMARY KEY (audit_id),
    KEY idx_salary_audit_employee_time (employee_id, changed_at)
) ENGINE=InnoDB;
~~~

Tạo trigger AFTER UPDATE:

~~~sql
DELIMITER //

CREATE TRIGGER trg_employees_au_salary_audit
AFTER UPDATE ON employees
FOR EACH ROW
BEGIN
    IF NOT (OLD.salary <=> NEW.salary) THEN
        INSERT INTO employee_salary_audit (
            employee_id,
            old_salary,
            new_salary,
            changed_at,
            connection_user
        )
        VALUES (
            OLD.employee_id,
            OLD.salary,
            NEW.salary,
            CURRENT_TIMESTAMP(6),
            USER()
        );
    END IF;
END//

DELIMITER ;
~~~

Toán tử <=> là phép so sánh null-safe của MySQL. Nó trả TRUE khi hai giá trị bằng nhau, kể cả khi cả hai là NULL; biểu thức NOT (OLD.salary <=> NEW.salary) chỉ đúng khi hai giá trị khác nhau. Trong ví dụ salary là NOT NULL, nhưng null-safe comparison giúp mẫu logic rõ ràng hơn khi áp dụng cho cột nullable.

USER() ghi nhận tài khoản kết nối của session. Trigger chạy trong ngữ cảnh quyền DEFINER; CURRENT_USER() bên trong trigger phản ánh tài khoản DEFINER, không nhất thiết là người dùng ứng dụng cuối cùng. Nếu cần ghi nhận actor nghiệp vụ như nhân viên đang thao tác, ứng dụng nên truyền actor qua một hợp đồng dữ liệu được kiểm soát thay vì suy ra từ DEFINER.

## 8. Một câu lệnh nhiều hàng sẽ gọi trigger bao nhiêu lần?

Giả sử câu lệnh:

~~~sql
UPDATE employees
SET salary = salary + 100
WHERE department_id = 10;
~~~

Nếu 75 hàng thuộc department 10 được cập nhật, trigger BEFORE UPDATE và AFTER UPDATE tương ứng được kích hoạt cho từng hàng được xử lý. Trigger không chạy một lần cho toàn bộ câu UPDATE.

Có thể hình dung:

~~~mermaid
flowchart TD
    A[UPDATE employees WHERE department_id = 10] --> B[MySQL xử lý hàng thứ nhất]
    B --> C[BEFORE UPDATE trigger]
    C --> D[Áp dụng thay đổi hàng]
    D --> E[AFTER UPDATE trigger]
    E --> F{Còn hàng phù hợp?}
    F -->|Có| B
    F -->|Không| G[Kết thúc câu UPDATE]
~~~

Nếu cùng một lệnh UPDATE tác động 75 hàng, phần thân trigger chạy 75 lần cho mỗi trigger phù hợp. Nếu có hai trigger cùng thời điểm/event, cả hai được chạy cho từng hàng theo thứ tự được xác định.

Điều này có thể làm một câu DML tưởng như đơn giản tạo ra nhiều thao tác phụ. Một trigger ghi audit sẽ thêm 75 hàng audit; trigger duy trì bảng tổng hợp có thể thực hiện thêm nhiều phép đọc/ghi tương ứng.

## 9. Thử nghiệm với INSERT nhiều hàng

Với:

~~~sql
INSERT INTO employees (
    employee_name,
    department_id,
    employment_status,
    salary
)
VALUES
    ('An', 10, 'ACTIVE', 1200.00),
    ('Binh', 10, 'ACTIVE', 1500.00),
    ('Chi', 20, 'ACTIVE', 1300.00);
~~~

BEFORE INSERT và AFTER INSERT trigger được gọi theo từng hàng được chèn. Một trigger có thể kiểm tra NEW của từng hàng và từ chối hàng không hợp lệ bằng SIGNAL.

Nếu một trigger phát lỗi trong lúc câu lệnh đang chèn nhiều hàng, câu lệnh có thể thất bại. Với InnoDB, các thay đổi của câu lệnh và các thao tác transactional do trigger thực hiện được rollback cùng nhau. Không giả định các engine không transactional có cùng bảo đảm.

INSERT ... SELECT và LOAD DATA cũng có thể kích hoạt trigger INSERT theo từng hàng được thêm. Bulk insert không biến row trigger thành statement trigger.

## 10. Kiểm chứng trigger cấp dòng bằng audit

Sau khi tạo audit trigger, chạy:

~~~sql
UPDATE employees
SET salary = salary + 100
WHERE department_id = 10;

SELECT
    employee_id,
    old_salary,
    new_salary,
    changed_at
FROM employee_salary_audit
ORDER BY audit_id;
~~~

Nếu ba nhân viên thuộc department 10 được cập nhật và salary thay đổi ở cả ba, bảng audit sẽ có ba bản ghi. Nếu điều kiện WHERE không khớp hàng nào, trigger không chạy và không có bản ghi audit mới.

Có thể đếm số bản ghi audit trước và sau một thao tác thử để xác nhận số lần xử lý theo hàng. Khi kiểm thử, nên dùng transaction và dữ liệu test riêng để không làm nhiễu audit nghiệp vụ.

Lưu ý: trigger AFTER UPDATE trong ví dụ chỉ ghi audit khi salary thay đổi. Nếu UPDATE chỉ đổi status hoặc một cột khác, trigger vẫn được gọi cho từng hàng, nhưng điều kiện IF không chèn audit salary.

## 11. Vì sao MySQL không có transition table cho statement trigger?

Statement-level trigger trong một số hệ quản trị có thể truy cập tập hàng cũ/mới của toàn bộ câu lệnh qua transition table hoặc biến thể tương đương. Điều đó cho phép tính tổng thay đổi một lần sau khi DML hoàn tất.

MySQL row trigger chỉ cung cấp OLD và NEW của hàng hiện tại. Nó không cung cấp một bảng ảo chứa tất cả hàng bị tác động bởi câu lệnh để trigger xử lý theo batch.

Do đó, không thể viết trigger MySQL để nói “sau UPDATE, hãy tính tổng tất cả hàng đã đổi đúng một lần” bằng cú pháp statement-level. Nếu cần tổng hợp, hãy cân nhắc:

- Một câu SQL set-based chạy sau DML trong cùng stored procedure.
- Ứng dụng điều phối DML và thao tác tổng hợp trong cùng transaction.
- Bảng staging chứa tập khóa bị ảnh hưởng, sau đó xử lý tập đó bằng một câu SQL.
- Cơ chế đồng bộ bất đồng bộ nếu nghiệp vụ cho phép eventual consistency.

Chọn phương án dựa trên yêu cầu nhất quán, quy mô dữ liệu và quyền kiểm soát luồng ghi.

## 12. Thực hiện logic một lần cho cả câu lệnh

Nếu ứng dụng có thể gọi stored procedure thay vì gửi DML tùy ý, procedure có thể gom thao tác thành một đơn vị:

~~~sql
CREATE TABLE department_change_log (
    log_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    department_id INT NOT NULL,
    increase_amount DECIMAL(12,2) NOT NULL,
    department_total DECIMAL(14,2) NOT NULL,
    recorded_at DATETIME(6) NOT NULL,
    PRIMARY KEY (log_id)
) ENGINE=InnoDB;

DELIMITER //

CREATE PROCEDURE increase_department_salary(
    IN p_department_id INT,
    IN p_increase DECIMAL(12,2)
)
BEGIN
    DECLARE v_department_total DECIMAL(14,2) DEFAULT 0.00;

    UPDATE employees
    SET salary = salary + p_increase
    WHERE department_id = p_department_id;

    SELECT COALESCE(SUM(salary), 0.00)
    INTO v_department_total
    FROM employees
    WHERE department_id = p_department_id;

    INSERT INTO department_change_log (
        department_id,
        increase_amount,
        department_total,
        recorded_at
    )
    VALUES (
        p_department_id,
        p_increase,
        v_department_total,
        CURRENT_TIMESTAMP(6)
    );
END//

DELIMITER ;
~~~

UPDATE vẫn kích hoạt row trigger cho từng nhân viên. INSERT vào department_change_log chỉ chạy một lần trong procedure. Đây là cách tạo hành vi theo cấp nghiệp vụ/câu lệnh bằng logic tường minh, không phải statement-level trigger.

Nếu procedure phải đảm bảo UPDATE và log cùng thành công hoặc cùng thất bại, hãy xác định rõ transaction ownership. Procedure có thể chạy trong transaction do caller quản lý hoặc tự quản lý transaction theo hợp đồng được thiết kế; không tự ý COMMIT một transaction mà caller đang sở hữu.

## 13. Hiệu năng của row trigger

Chi phí trigger nhân theo số hàng. Một trigger đơn giản cho mỗi hàng có thể vẫn tạo chi phí đáng kể khi DML tác động hàng trăm nghìn hàng.

Ví dụ UPDATE một triệu hàng có thể dẫn đến:

- Một triệu lần gọi BEFORE UPDATE.
- Một triệu lần gọi AFTER UPDATE.
- Một triệu lần INSERT audit nếu điều kiện audit đúng.
- Nhiều lần kiểm tra constraint, index và ghi log bổ sung.

Các nguyên tắc tối ưu:

1. Giữ trigger ngắn, tránh truy vấn lặp không cần thiết.
2. Chỉ ghi audit khi giá trị cần theo dõi thực sự thay đổi.
3. Tạo index phù hợp cho truy vấn phụ trong trigger.
4. Tránh gọi stored procedure hoặc thực hiện phép tính nặng cho mỗi hàng nếu có thể chuyển sang xử lý set-based.
5. Tránh trigger tạo chuỗi thao tác ghi phụ khó dự đoán.
6. Đo thời gian của câu DML khi trigger được bật và khi thử trên môi trường tương đương không có logic phụ.
7. Kiểm thử với kích thước batch gần thực tế, không chỉ một hàng.

Không nên dùng trigger để cập nhật bảng tổng hợp bằng cách SELECT rồi UPDATE một lần cho từng hàng nếu có thể gom thay đổi và cập nhật tổng một lần trong procedure hoặc job.

## 14. Giới hạn quan trọng khi viết trigger MySQL

Trigger là stored program nhưng có các giới hạn riêng:

- Không được trả result set cho client. Có thể dùng SELECT ... INTO để gán biến, nhưng không dùng SELECT độc lập nhằm trả dữ liệu từ trigger.
- Không được dùng START TRANSACTION, COMMIT hoặc ROLLBACK để tự quản lý transaction bên trong trigger.
- Không thể sửa bảng đang được câu lệnh kích hoạt trigger sử dụng. Ví dụ UPDATE employees kích hoạt trigger rồi trigger lại UPDATE employees sẽ gặp lỗi.
- Không thể gọi trực tiếp trigger bằng CALL; trigger chỉ được kích hoạt bởi event DML tương ứng.
- Không có OLD trong INSERT và không có NEW trong DELETE.
- Không thể gán NEW trong AFTER trigger.
- Không có FOR EACH STATEMENT hoặc transition table.

Nếu trigger cần thay đổi dữ liệu, thường ghi sang bảng khác. Ví dụ audit trigger INSERT vào employee_salary_audit khi câu lệnh gốc UPDATE employees. Tránh tạo vòng lặp ghi qua nhiều trigger không có giới hạn rõ.

## 15. Không thể cập nhật lại bảng đang được câu lệnh kích hoạt sử dụng

Một lỗi phổ biến là tạo AFTER UPDATE trigger trên employees rồi bên trong trigger lại UPDATE employees:

~~~sql
-- Minh họa anti-pattern; không tạo trigger này.
CREATE TRIGGER trg_employees_au_bad
AFTER UPDATE ON employees
FOR EACH ROW
BEGIN
    UPDATE employees
    SET updated_at = CURRENT_TIMESTAMP
    WHERE employee_id = NEW.employee_id;
END;
~~~

MySQL không cho trigger hoặc stored function được gọi từ trigger thay đổi bảng đang được câu lệnh đã kích hoạt trigger sử dụng. Lỗi thường gặp là 1442. Để sửa, hãy gán NEW.updated_at trong BEFORE UPDATE trigger:

~~~sql
CREATE TRIGGER trg_employees_bu_timestamp
BEFORE UPDATE ON employees
FOR EACH ROW
SET NEW.updated_at = CURRENT_TIMESTAMP(6);
~~~

Đây là trường hợp đúng với mục đích của BEFORE trigger: thay đổi giá trị hàng trước khi MySQL ghi nó.

## 16. Thứ tự khi có nhiều trigger cùng event và timing

MySQL cho phép nhiều trigger cùng gắn với một bảng, cùng event và cùng timing trong các phiên bản hiện đại (từ MySQL 5.7.2). Khi có nhiều trigger, thứ tự mặc định là thứ tự tạo. Có thể chỉ định thứ tự tương đối bằng FOLLOWS hoặc PRECEDES khi tạo trigger mới.

Ví dụ:

~~~sql
CREATE TRIGGER trg_employees_bi_audit_context
BEFORE INSERT ON employees
FOR EACH ROW
FOLLOWS trg_employees_bi_normalize
BEGIN
    -- Bổ sung logic trước khi hàng được chèn.
    SET NEW.created_at = COALESCE(
        NEW.created_at,
        CURRENT_TIMESTAMP(6)
    );
END;
~~~

FOLLOWS/PRECEDES chỉ xác định thứ tự tương đối giữa các trigger có cùng bảng, event và timing. Nếu thứ tự thực thi có ý nghĩa nghiệp vụ, hãy ghi rõ trong thiết kế và kiểm tra ACTION_ORDER trong metadata.

Đừng chia một logic phụ thuộc chặt chẽ thành nhiều trigger chỉ để tạo cấu trúc nhỏ hơn. Một trigger lớn nhưng rõ thứ tự có thể dễ bảo trì hơn một chuỗi trigger phụ thuộc lẫn nhau.

## 17. Những thao tác không kích hoạt trigger như DML thông thường

Trigger không phải bộ theo dõi mọi thay đổi vật lý trong bảng. Một số thao tác không kích hoạt trigger tương ứng:

- TRUNCATE TABLE không kích hoạt DELETE trigger.
- DROP TABLE không chạy DELETE trigger cho từng hàng trước khi xóa bảng.
- Hành động cascade của foreign key như ON DELETE CASCADE hoặc ON UPDATE CASCADE không kích hoạt trigger trên các hàng bị tác động bởi cascade.

Nếu hệ thống dựa vào trigger để ghi audit xóa hàng, không thể giả định TRUNCATE hoặc foreign key cascade sẽ tạo audit record. Hãy kiểm soát quyền DDL, dùng thao tác DML có chủ đích hoặc thiết kế audit ở tầng khác cho các đường thay đổi này.

## 18. Transaction và lỗi trong trigger

Với InnoDB, trigger chạy đồng bộ trong cùng câu lệnh và transaction với thao tác DML đã kích hoạt nó. Nếu trigger ghi audit vào một bảng InnoDB rồi câu lệnh bị lỗi, các thay đổi transactional trong câu lệnh bị rollback.

Ví dụ:

~~~sql
START TRANSACTION;

UPDATE employees
SET salary = salary + 100
WHERE employee_id = 101;

-- Kiểm tra audit trong cùng transaction.
SELECT *
FROM employee_salary_audit
WHERE employee_id = 101
ORDER BY audit_id DESC;

ROLLBACK;
~~~

Sau ROLLBACK, thay đổi salary và audit row được tạo bởi trigger đều bị hủy nếu cả hai bảng dùng InnoDB và không có hành động ngoài transaction. Nếu một bảng dùng engine không transactional, không có bảo đảm rollback tương tự cho thay đổi ở bảng đó.

Trigger có thể dùng SIGNAL để từ chối dữ liệu:

~~~sql
IF NEW.salary < 0 THEN
    SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Salary cannot be negative';
END IF;
~~~

Khi trigger phát lỗi, câu lệnh DML bị lỗi. Với InnoDB, statement changes được rollback; transaction caller có thể cần ROLLBACK tùy lỗi và chính sách xử lý. Không coi trigger là nơi tự COMMIT hoặc tự ROLLBACK transaction.

## 19. Definer và quyền thực thi

Trigger có DEFINER. Các câu lệnh bên trong trigger chạy theo security context của definer. Tài khoản tạo trigger cần quyền TRIGGER trên bảng gắn trigger và các quyền cần thiết cho những thao tác trong trigger.

Điều này quan trọng khi triển khai giữa môi trường:

- Tài khoản DEFINER phải tồn tại hoặc được xử lý phù hợp trên server đích.
- Definer cần quyền tối thiểu để thực hiện SELECT/INSERT/UPDATE mà trigger yêu cầu.
- Không cấp quyền rộng hơn chỉ để trigger chạy được.
- Kiểm tra SHOW CREATE TRIGGER và metadata sau migration.

CURRENT_USER() trong trigger phản ánh security account của trigger (DEFINER). USER() phản ánh tài khoản kết nối. Hai giá trị phục vụ mục đích khác nhau; hãy chọn đúng nếu ghi audit.

## 20. Kiểm tra và quản lý trigger

Liệt kê trigger:

~~~sql
SHOW TRIGGERS FROM app_db;
~~~

Xem định nghĩa cụ thể:

~~~sql
SHOW CREATE TRIGGER app_db.trg_employees_au_salary_audit;
~~~

Tra metadata:

~~~sql
SELECT
    TRIGGER_SCHEMA,
    TRIGGER_NAME,
    EVENT_MANIPULATION,
    EVENT_OBJECT_TABLE,
    ACTION_TIMING,
    ACTION_ORDER,
    DEFINER,
    SQL_MODE
FROM INFORMATION_SCHEMA.TRIGGERS
WHERE TRIGGER_SCHEMA = 'app_db'
ORDER BY EVENT_OBJECT_TABLE, EVENT_MANIPULATION, ACTION_TIMING, ACTION_ORDER;
~~~

Các cột này giúp xác định trigger gắn với bảng nào, event nào, timing nào, thứ tự và definer. Khi trigger gây lỗi ghi dữ liệu, kiểm tra cả định nghĩa, SQL_MODE được lưu khi tạo trigger và quyền definer.

Xóa trigger:

~~~sql
DROP TRIGGER IF EXISTS app_db.trg_employees_au_salary_audit;
~~~

DROP TRIGGER là DDL. Hãy triển khai thay đổi trigger qua migration có review, lưu định nghĩa hiện tại và kiểm tra tác động đến luồng ghi trước khi áp dụng.

## 21. Khi nào cần logic cấp câu lệnh?

Nếu yêu cầu nghiệp vụ cần xử lý một lần cho cả câu DML, không cố mô phỏng bằng biến session bên trong row trigger. Hãy chọn một cơ chế có ngữ cảnh statement rõ ràng:

| Nhu cầu | Cách thiết kế phù hợp |
|---|---|
| Validate từng hàng trước ghi | BEFORE row trigger hoặc constraint |
| Audit từng hàng cũ/mới | AFTER row trigger |
| Ghi một log cho mỗi request/batch | Application service hoặc stored procedure |
| Tính lại tổng sau khi cập nhật nhiều hàng | Một câu aggregate/set-based sau DML |
| Xử lý tập khóa bị ảnh hưởng | Staging table rồi xử lý theo tập |
| Phát sự kiện cho hệ thống khác | Transactional outbox hoặc cơ chế messaging phù hợp |

Biến session như @statement_id không tạo ra statement trigger. Connection pool có thể tái sử dụng session, nhiều câu lệnh có thể dùng cùng connection và lỗi giữa chừng có thể làm trạng thái bị sót. Nếu cần correlation ID, hãy truyền rõ qua procedure hoặc ghi vào bảng outbox theo một transaction có hợp đồng rõ ràng.

## 22. Quy trình thiết kế row trigger

1. Xác định event INSERT, UPDATE hay DELETE và thời điểm BEFORE/AFTER.
2. Xác định logic thực sự thuộc về từng hàng hay thuộc về toàn câu lệnh.
3. Kiểm tra cột nào được đọc từ OLD và NEW theo event.
4. Chọn BEFORE nếu cần gán NEW hoặc từ chối hàng trước khi ghi.
5. Chọn AFTER nếu cần ghi audit hoặc phản ánh thay đổi đã áp dụng.
6. Giữ trigger ngắn và tránh cập nhật lại bảng đã kích hoạt trigger.
7. Dùng SIGNAL cho điều kiện dữ liệu không hợp lệ.
8. Đảm bảo các bảng nguồn và bảng audit dùng engine transactional nếu cần rollback nguyên tử.
9. Kiểm tra hành vi khi DML tác động 0, 1 và nhiều hàng.
10. Kiểm tra thao tác bulk, TRUNCATE và foreign key cascade có bỏ qua trigger hay không.
11. Kiểm tra DEFINER, quyền và thứ tự nếu có nhiều trigger cùng event/timing.
12. Đo hiệu năng theo kích thước batch đại diện và ghi rõ chi phí phụ.

## 23. Bài tập thực hành

1. Tạo bảng employees và trigger BEFORE INSERT để TRIM employee_name, từ chối tên rỗng.
2. Tạo trigger BEFORE UPDATE để gán updated_at và từ chối salary âm.
3. Tạo bảng employee_salary_audit và trigger AFTER UPDATE chỉ ghi khi salary thay đổi.
4. Chạy UPDATE tác động một hàng, nhiều hàng và không hàng nào; đếm audit record tương ứng.
5. Chạy INSERT nhiều hàng và xác nhận trigger được gọi theo từng hàng được chèn.
6. Thử SIGNAL trong BEFORE trigger và xác nhận DML không ghi dữ liệu không hợp lệ.
7. Thử UPDATE employees từ chính trigger gắn trên employees trong môi trường kiểm thử; đọc lỗi và thay bằng gán NEW trong BEFORE UPDATE.
8. Thực hiện UPDATE trong transaction rồi ROLLBACK; xác nhận cả hàng nguồn và audit row InnoDB đều quay lại trạng thái cũ.
9. Tạo procedure cập nhật lương một phòng ban và ghi một dòng batch log; phân biệt một lần ghi log với nhiều lần row trigger.
10. Kiểm tra SHOW CREATE TRIGGER và INFORMATION_SCHEMA.TRIGGERS; ghi lại event, timing, definer và action order.
11. Thử TRUNCATE trên bảng test có DELETE trigger; xác nhận DELETE trigger không được gọi.
12. Viết giải thích vì sao MySQL không thể tạo FOR EACH STATEMENT và đề xuất cách xử lý một lần cho cả batch.

Bạn hoàn thành bài khi giải thích được vì sao MySQL chỉ có trigger cấp dòng, dự đoán đúng số lần trigger chạy với DML nhiều hàng, dùng OLD/NEW đúng event và timing, đồng thời chọn được stored procedure hoặc tầng ứng dụng cho logic cần chạy một lần ở cấp câu lệnh. Thiết kế trigger tốt phải tính cả transaction, quyền definer và chi phí trên từng hàng.
