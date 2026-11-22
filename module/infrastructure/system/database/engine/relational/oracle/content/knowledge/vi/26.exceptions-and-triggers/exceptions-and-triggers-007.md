# INSTEAD OF trigger cho thao tác thay đổi dữ liệu qua view trong Oracle

## 1. Vì sao cần INSTEAD OF trigger?

View là một đối tượng logic được định nghĩa bằng câu SELECT. Người dùng có thể đọc dữ liệu từ view như đọc bảng, nhưng khả năng INSERT, UPDATE và DELETE qua view phụ thuộc vào cấu trúc truy vấn định nghĩa view.

Một view đơn giản dựa trên một bảng thường có thể tự động cập nhật được. Ngược lại, view có JOIN phức tạp, UNION, DISTINCT, GROUP BY, hàm tổng hợp hoặc biểu thức có thể không cho phép DML trực tiếp theo các quy tắc updatable view của Oracle.

Khi muốn ứng dụng vẫn thao tác bằng một giao diện view thống nhất, Oracle cung cấp **INSTEAD OF trigger**. Trigger này chạy thay cho thao tác DML được gửi tới view. Phần thân trigger quyết định sẽ INSERT, UPDATE hoặc DELETE dữ liệu ở bảng nền nào và theo quy tắc nào.

~~~text
Ứng dụng
   |
   | INSERT / UPDATE / DELETE
   v
EMPLOYEE_DIRECTORY_V (view)
   |
   | INSTEAD OF trigger
   v
PL/SQL mapping logic
   |
   +------> EMPLOYEES
   |
   +------> DEPARTMENTS (nếu nghiệp vụ yêu cầu)
~~~

INSTEAD OF trigger hữu ích khi:

- View kết hợp nhiều bảng nhưng ứng dụng cần một điểm DML thống nhất.
- View dùng UNION hoặc cấu trúc khác không tự updatable.
- Dữ liệu hiển thị là dữ liệu tổng hợp/biến đổi và cần quy tắc cập nhật riêng.
- Một thao tác trên view phải được ánh xạ thành nhiều câu DML ở các bảng nền.
- Muốn giữ giao diện SQL ổn định trong khi cách lưu dữ liệu vật lý phức tạp hơn.

Điều quan trọng là trigger không tự suy luận nghiệp vụ. Người thiết kế phải xác định rõ mỗi INSERT, UPDATE và DELETE trên view sẽ có ý nghĩa gì ở các bảng nền.

> Nội dung dùng Oracle Database 19c. Các ví dụ giả định có quyền tạo view/trigger và quyền DML cần thiết trên bảng nền. INSTEAD OF trigger là cơ chế thay thế DML trên view; cần kiểm tra kỹ security, constraint, transaction và semantics trước khi đưa vào production.

## 2. View updatable và giới hạn DML trực tiếp

### 2.1. View đơn giản có thể tự cập nhật

Ví dụ:

~~~sql
CREATE OR REPLACE VIEW active_employees_v AS
SELECT employee_id,
       first_name,
       last_name,
       department_id
FROM employees
WHERE department_id = 50;
~~~

View lấy cột trực tiếp từ một bảng. Với các điều kiện phù hợp, Oracle có thể cho phép:

~~~sql
UPDATE active_employees_v
SET last_name = 'SMITH'
WHERE employee_id = 100;
~~~

Oracle tự ánh xạ câu UPDATE vào bảng EMPLOYEES. Không cần INSTEAD OF trigger nếu view inherently updatable và DML không vi phạm các hạn chế của view.

### 2.2. View phức tạp có thể không updatable

Một số cấu trúc thường khiến view không thể được sửa trực tiếp theo các quy tắc updatable view:

- Set operators như UNION, UNION ALL, INTERSECT hoặc MINUS.
- DISTINCT.
- Hàm tổng hợp như SUM, COUNT, AVG, MIN hoặc MAX.
- GROUP BY hoặc HAVING.
- Một số biểu thức, subquery hoặc analytic function trong select list.
- Một số dạng JOIN không đáp ứng quy tắc key-preserved table.
- Các cấu trúc phân cấp hoặc MODEL.

Ví dụ view tổng hợp:

~~~sql
CREATE OR REPLACE VIEW department_salary_v AS
SELECT department_id,
       COUNT(*) AS employee_count,
       AVG(salary) AS average_salary
FROM employees
GROUP BY department_id;
~~~

Một câu lệnh như:

~~~sql
UPDATE department_salary_v
SET average_salary = 5000
WHERE department_id = 50;
~~~

không có một ánh xạ tự nhiên duy nhất xuống các row EMPLOYEES. Cần quy tắc nghiệp vụ để quyết định phải thay đổi salary của từng nhân viên ra sao. INSTEAD OF trigger cho phép lập trình quy tắc đó nếu thao tác được định nghĩa có ý nghĩa.

### 2.3. Join view và key-preserved table

Với view JOIN, Oracle xét khái niệm **key-preserved table**. Một bảng được xem là key-preserved trong join nếu mỗi key của bảng đó vẫn xác định duy nhất một row trong kết quả join theo các điều kiện tương ứng.

Ví dụ:

~~~sql
CREATE OR REPLACE VIEW employee_department_v AS
SELECT e.employee_id,
       e.last_name,
       e.department_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id;
~~~

Nếu EMPLOYEES có primary key EMPLOYEE_ID và DEPARTMENTS có primary key DEPARTMENT_ID, mỗi nhân viên ghép với tối đa một department. Tuy nhiên, khả năng cập nhật tự động còn phụ thuộc bảng nào key-preserved, cột nào được cập nhật và các quy tắc của Oracle đối với join view.

Oracle có thể cho phép DML lên một bảng key-preserved trong một số trường hợp, nhưng không cho phép tùy ý cập nhật nhiều bảng qua một câu DML duy nhất. INSTEAD OF trigger cho phép định nghĩa cách ánh xạ tường minh.

### 2.4. Kiểm tra khả năng updatable của cột

Có thể xem metadata qua USER_UPDATABLE_COLUMNS:

~~~sql
SELECT table_name,
       column_name,
       updatable,
       insertable,
       deletable
FROM user_updatable_columns
WHERE table_name = 'EMPLOYEE_DEPARTMENT_V'
ORDER BY column_id;
~~~

Các cột UPDATABLE, INSERTABLE và DELETABLE cho biết khả năng DML trực tiếp theo metadata của view. Nếu view có INSTEAD OF trigger, hành vi DML thực tế sẽ do trigger đảm nhận.

## 3. INSTEAD OF trigger hoạt động thế nào?

### 3.1. Ý nghĩa của INSTEAD OF

Khi ứng dụng chạy DML trên view có INSTEAD OF trigger, Oracle kích hoạt trigger thay cho việc tự động thực hiện DML trên view.

Ví dụ:

~~~sql
INSERT INTO employee_department_v (
    employee_id,
    last_name,
    department_id,
    department_name
)
VALUES (9001, 'NGUYEN', 50, 'SALES');
~~~

Nếu view có INSTEAD OF INSERT trigger, trigger chạy. Trigger có thể chỉ INSERT vào EMPLOYEES, kiểm tra DEPARTMENTS hoặc thực hiện thêm các thao tác khác theo quy tắc được thiết kế.

Ngay cả khi view vốn inherently updatable, nếu có INSTEAD OF trigger cho event tương ứng, trigger sẽ được ưu tiên thay cho DML tự động trên view. Vì vậy, tạo trigger có thể thay đổi semantics mà caller trước đó đang dựa vào.

### 3.2. INSTEAD OF chỉ dùng trên view

Không thể khai báo INSTEAD OF trigger trực tiếp trên table:

~~~sql
-- Không hợp lệ: INSTEAD OF không áp dụng cho table
CREATE OR REPLACE TRIGGER trg_orders_io
INSTEAD OF INSERT ON orders
FOR EACH ROW
BEGIN
    NULL;
END;
/
~~~

Đối với table, Oracle dùng các timing point như BEFORE và AFTER. INSTEAD OF là cơ chế dành cho view.

### 3.3. Chỉ có row-level semantics

INSTEAD OF trigger chỉ kích hoạt cho từng row. Cú pháp có FOR EACH ROW; không có statement-level INSTEAD OF trigger.

Nếu câu lệnh tác động 100 row trong view, trigger có thể chạy 100 lần, mỗi lần nhận một cặp giá trị :OLD và :NEW tương ứng với row đó.

Ví dụ:

~~~sql
UPDATE employee_department_v
SET department_id = 60
WHERE department_id = 50;
~~~

Trigger xử lý từng row được tác động. Vì vậy, không đặt giả định rằng phần thân trigger chỉ chạy một lần cho toàn bộ câu UPDATE.

### 3.4. Không có BEFORE hoặc AFTER cho INSTEAD OF

Không khai báo BEFORE INSERT hoặc AFTER UPDATE để thay thế INSTEAD OF. Trigger trên view dùng timing point INSTEAD OF. Nó được gọi thay cho thao tác DML trên view.

### 3.5. Trigger chạy trong transaction hiện tại

INSTEAD OF trigger chạy trong transaction của user đã gửi câu DML. Các câu INSERT/UPDATE/DELETE trên bảng nền thuộc cùng transaction đó.

Thông thường:

- Trigger không tự COMMIT.
- Trigger không tự ROLLBACK transaction gọi.
- Caller có thể COMMIT hoặc ROLLBACK theo use case.
- Lỗi không được xử lý có thể làm câu DML gốc thất bại.

Không thiết kế trigger như một transaction độc lập.

## 4. Cú pháp tạo INSTEAD OF trigger

Cú pháp tổng quát:

~~~sql
CREATE [OR REPLACE] TRIGGER trigger_name
INSTEAD OF {INSERT | UPDATE | DELETE}
ON view_name
FOR EACH ROW
DECLARE
    -- Biến local (nếu cần)
BEGIN
    -- DML trên bảng nền
END;
/
~~~

Có thể khai báo một trigger xử lý nhiều event:

~~~sql
CREATE OR REPLACE TRIGGER trg_employee_directory_io
INSTEAD OF INSERT OR UPDATE OR DELETE
ON employee_directory_v
FOR EACH ROW
BEGIN
    IF INSERTING THEN
        ...
    ELSIF UPDATING THEN
        ...
    ELSIF DELETING THEN
        ...
    END IF;
END;
/
~~~

Các điều kiện event:

| Predicate | Ý nghĩa |
| --- | --- |
| INSERTING | Trigger đang xử lý INSERT |
| UPDATING | Trigger đang xử lý UPDATE |
| DELETING | Trigger đang xử lý DELETE |
| UPDATING('COLUMN_NAME') | Câu UPDATE có chỉ định cột đó trong SET |

UPDATING('COLUMN_NAME') kiểm tra cột có xuất hiện trong mệnh đề SET, không có nghĩa giá trị thực tế chắc chắn đã thay đổi.

## 5. Pseudorecord :OLD và :NEW

Trong row trigger, Oracle cung cấp correlation variables để đọc giá trị row đang được xử lý.

| DML event | :OLD | :NEW |
| --- | --- | --- |
| INSERT | NULL cho các field | Giá trị row được yêu cầu insert |
| UPDATE | Giá trị trước khi update | Giá trị mới được yêu cầu |
| DELETE | Giá trị trước khi delete | NULL cho các field |

Ví dụ:

~~~sql
IF INSERTING THEN
    INSERT INTO employees(employee_id, last_name)
    VALUES (:NEW.employee_id, :NEW.last_name);
ELSIF UPDATING THEN
    UPDATE employees
    SET last_name = :NEW.last_name
    WHERE employee_id = :OLD.employee_id;
ELSIF DELETING THEN
    DELETE FROM employees
    WHERE employee_id = :OLD.employee_id;
END IF;
~~~

### 5.1. INSTEAD OF trigger chỉ đọc được :OLD và :NEW

Một quy tắc quan trọng của Oracle: INSTEAD OF trigger có thể đọc cả :OLD và :NEW, nhưng không được gán giá trị cho các field này.

Không viết:

~~~sql
:NEW.last_name := UPPER(:NEW.last_name);
~~~

Nếu cần chuẩn hóa giá trị, dùng local variable:

~~~sql
DECLARE
    l_last_name employees.last_name%TYPE;
BEGIN
    l_last_name := UPPER(:NEW.last_name);

    INSERT INTO employees(employee_id, last_name)
    VALUES (:NEW.employee_id, l_last_name);
END;
~~~

### 5.2. Dùng :OLD để xác định row cần sửa hoặc xóa

Trong UPDATE, thường dùng khóa cũ để tìm row nền:

~~~sql
UPDATE employees
SET employee_id = :NEW.employee_id,
    last_name = :NEW.last_name
WHERE employee_id = :OLD.employee_id;
~~~

Nếu dùng :NEW.employee_id trong WHERE, khi khóa chính thay đổi trigger có thể không tìm thấy row cũ.

Trong DELETE, dùng :OLD:

~~~sql
DELETE FROM employees
WHERE employee_id = :OLD.employee_id;
~~~

### 5.3. Đừng giả định mọi cột view đều được truyền

Caller có thể chỉ đưa một số cột vào INSERT hoặc UPDATE. Những field không được chỉ định có thể mang giá trị mặc định/null theo semantics của câu DML và view. Trigger phải kiểm tra các giá trị bắt buộc và không giả định mọi cột đều có giá trị hợp lệ.

Nên khuyến nghị caller dùng column list tường minh:

~~~sql
INSERT INTO employee_directory_v (
    employee_id,
    last_name,
    department_id
)
VALUES (9001, 'NGUYEN', 50);
~~~

Điều này làm rõ input contract và giảm lỗi khi view được mở rộng thêm cột.

## 6. Ví dụ đầy đủ: DML trên view JOIN hai bảng

Giả sử có hai bảng:

- EMPLOYEES chứa thông tin nhân viên.
- DEPARTMENTS chứa tên phòng ban.

View hiển thị nhân viên kèm tên phòng ban:

~~~sql
CREATE OR REPLACE VIEW employee_directory_v AS
SELECT e.employee_id,
       e.first_name,
       e.last_name,
       e.salary,
       e.department_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id;
~~~

Đây là view JOIN. Ta định nghĩa semantics:

- INSERT: tạo một row trong EMPLOYEES; DEPARTMENT_ID phải trỏ tới department đã tồn tại.
- UPDATE: sửa các thuộc tính nhân viên trong EMPLOYEES. DEPARTMENT_NAME là cột hiển thị dẫn xuất, không được sửa trực tiếp qua API này.
- DELETE: xóa row nhân viên trong EMPLOYEES; ràng buộc khóa ngoại ở bảng nền vẫn được áp dụng.

### 6.1. Tạo INSTEAD OF trigger cho INSERT

~~~sql
CREATE OR REPLACE TRIGGER trg_employee_directory_ins
INSTEAD OF INSERT ON employee_directory_v
FOR EACH ROW
BEGIN
    IF :NEW.employee_id IS NULL THEN
        RAISE_APPLICATION_ERROR(-20101, 'Employee ID is required');
    END IF;

    IF :NEW.department_id IS NULL THEN
        RAISE_APPLICATION_ERROR(-20102, 'Department ID is required');
    END IF;

    INSERT INTO employees (
        employee_id,
        first_name,
        last_name,
        salary,
        department_id
    )
    VALUES (
        :NEW.employee_id,
        :NEW.first_name,
        :NEW.last_name,
        :NEW.salary,
        :NEW.department_id
    );
END;
/
~~~

Gọi:

~~~sql
INSERT INTO employee_directory_v (
    employee_id,
    first_name,
    last_name,
    salary,
    department_id
)
VALUES (
    9001,
    'AN',
    'NGUYEN',
    2500,
    50
);
~~~

Trigger ghi vào EMPLOYEES. Cột DEPARTMENT_NAME được tạo ra từ JOIN nên không cần INSERT trực tiếp vào DEPARTMENTS.

Nếu DEPARTMENT_ID không tồn tại, foreign key ở EMPLOYEES (nếu đã khai báo) sẽ từ chối INSERT. INSTEAD OF trigger không vô hiệu hóa constraint của bảng nền.

### 6.2. Tạo INSTEAD OF trigger cho UPDATE

~~~sql
CREATE OR REPLACE TRIGGER trg_employee_directory_upd
INSTEAD OF UPDATE ON employee_directory_v
FOR EACH ROW
BEGIN
    IF UPDATING('DEPARTMENT_NAME') THEN
        RAISE_APPLICATION_ERROR(
            -20103,
            'Department name is read-only in this view'
        );
    END IF;

    UPDATE employees
    SET employee_id   = :NEW.employee_id,
        first_name    = :NEW.first_name,
        last_name     = :NEW.last_name,
        salary        = :NEW.salary,
        department_id = :NEW.department_id
    WHERE employee_id = :OLD.employee_id;

    IF SQL%ROWCOUNT = 0 THEN
        RAISE_APPLICATION_ERROR(-20104, 'Employee row not found');
    END IF;
END;
/
~~~

Gọi:

~~~sql
UPDATE employee_directory_v
SET salary = salary * 1.05
WHERE department_id = 50;
~~~

Oracle gọi trigger cho từng row được cập nhật. Mỗi lần trigger cập nhật row tương ứng trong EMPLOYEES.

UPDATING('DEPARTMENT_NAME') kiểm tra câu UPDATE có chỉ định cột này trong SET. Nếu caller chỉ cập nhật SALARY, trigger không từ chối. Nếu caller đưa DEPARTMENT_NAME vào SET, trigger từ chối theo contract.

Lưu ý: trigger đang cập nhật toàn bộ nhóm cột nhân viên từ :NEW. Nếu cần xử lý cột nào được chỉ định riêng, có thể dùng UPDATING('COLUMN_NAME') để xây dựng UPDATE phù hợp. Khi view có nhiều cột dẫn xuất, hãy định nghĩa rõ cột nào được ghi và cột nào chỉ để hiển thị.

### 6.3. Tạo INSTEAD OF trigger cho DELETE

~~~sql
CREATE OR REPLACE TRIGGER trg_employee_directory_del
INSTEAD OF DELETE ON employee_directory_v
FOR EACH ROW
BEGIN
    DELETE FROM employees
    WHERE employee_id = :OLD.employee_id;

    IF SQL%ROWCOUNT = 0 THEN
        RAISE_APPLICATION_ERROR(-20105, 'Employee row not found');
    END IF;
END;
/
~~~

Gọi:

~~~sql
DELETE FROM employee_directory_v
WHERE employee_id = 9001;
~~~

Trigger xóa row trong EMPLOYEES. Nếu bảng khác tham chiếu EMPLOYEES bằng foreign key, quy tắc referential integrity của bảng nền vẫn quyết định có được xóa hay không.

### 6.4. Dùng một trigger cho cả ba event

Thay vì ba trigger riêng, có thể gom logic:

~~~sql
CREATE OR REPLACE TRIGGER trg_employee_directory_dml
INSTEAD OF INSERT OR UPDATE OR DELETE
ON employee_directory_v
FOR EACH ROW
BEGIN
    IF INSERTING THEN
        INSERT INTO employees (
            employee_id,
            first_name,
            last_name,
            salary,
            department_id
        )
        VALUES (
            :NEW.employee_id,
            :NEW.first_name,
            :NEW.last_name,
            :NEW.salary,
            :NEW.department_id
        );

    ELSIF UPDATING THEN
        IF UPDATING('DEPARTMENT_NAME') THEN
            RAISE_APPLICATION_ERROR(
                -20103,
                'Department name is read-only in this view'
            );
        END IF;

        UPDATE employees
        SET first_name    = :NEW.first_name,
            last_name     = :NEW.last_name,
            salary        = :NEW.salary,
            department_id = :NEW.department_id
        WHERE employee_id = :OLD.employee_id;

    ELSIF DELETING THEN
        DELETE FROM employees
        WHERE employee_id = :OLD.employee_id;
    END IF;
END;
/
~~~

Một trigger duy nhất giúp gom logic event, nhưng trigger có thể dài. Nếu logic mỗi event phức tạp, có thể tách helper procedure private trong package và gọi helper từ trigger.

Không tạo nhiều trigger cùng loại cho cùng event nếu thứ tự chạy giữa chúng có thể ảnh hưởng kết quả mà không có thiết kế rõ. Với nhiều thao tác cần thứ tự, một trigger gọi các helper theo thứ tự xác định thường dễ hiểu hơn.

## 7. Ví dụ view UNION ALL ánh xạ tới nhiều bảng nền

INSTEAD OF trigger đặc biệt hữu ích khi view hợp nhất các loại dữ liệu khác nhau.

Giả sử có hai bảng:

~~~sql
CREATE TABLE person_contacts (
    person_id NUMBER PRIMARY KEY,
    full_name VARCHAR2(200 CHAR) NOT NULL
);

CREATE TABLE company_contacts (
    company_id NUMBER PRIMARY KEY,
    company_name VARCHAR2(200 CHAR) NOT NULL
);
~~~

Tạo view thống nhất:

~~~sql
CREATE OR REPLACE VIEW all_contacts_v AS
SELECT person_id AS contact_id,
       full_name AS display_name,
       'PERSON' AS contact_type
FROM person_contacts
UNION ALL
SELECT company_id AS contact_id,
       company_name AS display_name,
       'COMPANY' AS contact_type
FROM company_contacts;
~~~

View có UNION ALL nên không inherently updatable theo DML trực tiếp. Trigger sẽ chọn bảng nền theo CONTACT_TYPE.

### 7.1. Trigger INSERT

~~~sql
CREATE OR REPLACE TRIGGER trg_all_contacts_ins
INSTEAD OF INSERT ON all_contacts_v
FOR EACH ROW
BEGIN
    IF :NEW.contact_type = 'PERSON' THEN
        INSERT INTO person_contacts(person_id, full_name)
        VALUES (:NEW.contact_id, :NEW.display_name);

    ELSIF :NEW.contact_type = 'COMPANY' THEN
        INSERT INTO company_contacts(company_id, company_name)
        VALUES (:NEW.contact_id, :NEW.display_name);

    ELSE
        RAISE_APPLICATION_ERROR(-20110, 'Unknown contact type');
    END IF;
END;
/
~~~

### 7.2. Trigger UPDATE

~~~sql
CREATE OR REPLACE TRIGGER trg_all_contacts_upd
INSTEAD OF UPDATE ON all_contacts_v
FOR EACH ROW
BEGIN
    IF :OLD.contact_type <> :NEW.contact_type THEN
        RAISE_APPLICATION_ERROR(
            -20111,
            'Changing contact type is not supported'
        );
    END IF;

    IF :OLD.contact_type = 'PERSON' THEN
        UPDATE person_contacts
        SET person_id = :NEW.contact_id,
            full_name = :NEW.display_name
        WHERE person_id = :OLD.contact_id;

    ELSIF :OLD.contact_type = 'COMPANY' THEN
        UPDATE company_contacts
        SET company_id = :NEW.contact_id,
            company_name = :NEW.display_name
        WHERE company_id = :OLD.contact_id;

    ELSE
        RAISE_APPLICATION_ERROR(-20112, 'Unknown old contact type');
    END IF;
END;
/
~~~

### 7.3. Trigger DELETE

~~~sql
CREATE OR REPLACE TRIGGER trg_all_contacts_del
INSTEAD OF DELETE ON all_contacts_v
FOR EACH ROW
BEGIN
    IF :OLD.contact_type = 'PERSON' THEN
        DELETE FROM person_contacts
        WHERE person_id = :OLD.contact_id;

    ELSIF :OLD.contact_type = 'COMPANY' THEN
        DELETE FROM company_contacts
        WHERE company_id = :OLD.contact_id;
    END IF;
END;
/
~~~

Ví dụ này cho thấy một view có thể là façade trên nhiều bảng nền. Tuy nhiên, cần bảo đảm khóa nhận diện row là duy nhất trong từng loại. CONTACT_ID có thể trùng giữa PERSON và COMPANY; vì vậy cặp CONTACT_TYPE + CONTACT_ID mới là định danh logic của row view.

Nếu cần đổi một contact từ PERSON sang COMPANY, đó là thao tác chuyển đổi entity có thể bao gồm INSERT bảng đích, chuyển quan hệ phụ thuộc và DELETE bảng nguồn. Không nên âm thầm coi nó là UPDATE đơn giản nếu nghiệp vụ chưa định nghĩa rõ.

## 8. DML nhiều row và hiệu năng

### 8.1. Trigger chạy theo từng row

~~~sql
INSERT INTO all_contacts_v(contact_id, display_name, contact_type)
SELECT person_id, full_name, 'PERSON'
FROM staging_person_contacts;
~~~

Nếu câu INSERT tạo 50.000 row, INSTEAD OF trigger có thể chạy 50.000 lần. Mỗi lần lại thực hiện DML vào bảng nền.

Đây là row-level processing. Không có statement-level INSTEAD OF trigger để gom toàn bộ row của câu DML thành một lần xử lý.

### 8.2. Tránh nhiều câu SQL không cần thiết trong mỗi lần trigger

Trigger chạy cho mỗi row nên các query lookup lặp lại có thể gây overhead lớn. Hãy cân nhắc:

- Dùng constraint/foreign key để kiểm tra tính hợp lệ khi có thể.
- Chỉ query thông tin thật sự cần thiết.
- Dùng index phù hợp trên khóa tìm kiếm bảng nền.
- Tránh gọi remote database hoặc service bên ngoài cho từng row.
- Tránh DML không cần thiết nếu cột không thay đổi.

### 8.3. Dùng set-based SQL khi có thể

Nếu nghiệp vụ chỉ là cập nhật hàng loạt một bảng nền, có thể dùng trực tiếp SQL set-based trên bảng thay vì view trigger. Trigger là lớp ánh xạ cho giao diện view; nó không tự biến xử lý row-by-row thành bulk SQL.

### 8.4. Khi cần bulk processing

Nếu cần xử lý khối lượng lớn với nhiều bước, cân nhắc:

- Procedure/package nhận collection và dùng FORALL.
- Staging table và set-based INSERT/UPDATE.
- ETL hoặc batch job.
- Một API DML chuyên dụng thay cho view trigger.

Không chọn INSTEAD OF trigger chỉ vì muốn che nhiều thao tác DML khỏi caller nếu nó tạo overhead hoặc làm transaction khó dự đoán.

## 9. Constraint, default và dữ liệu bảng nền

### 9.1. Constraint của bảng nền vẫn có hiệu lực

INSTEAD OF trigger không bỏ qua:

- NOT NULL.
- PRIMARY KEY.
- UNIQUE.
- CHECK.
- FOREIGN KEY.

Nếu trigger INSERT giá trị vi phạm constraint, Oracle trả lỗi từ bảng nền và statement trên view thất bại nếu lỗi không được xử lý phù hợp.

### 9.2. Default value

Nếu cột bảng nền có DEFAULT, trigger nên bỏ cột đó khỏi INSERT khi muốn Oracle áp dụng default. Nếu trigger truyền explicit NULL, default thông thường không tự thay thế NULL.

Ví dụ:

~~~sql
INSERT INTO employees (
    employee_id,
    last_name,
    department_id
)
VALUES (
    :NEW.employee_id,
    :NEW.last_name,
    :NEW.department_id
);
~~~

Nếu CREATED_AT có default, không đưa CREATED_AT vào danh sách cột để Oracle áp dụng default. Nếu trigger truyền :NEW.created_at mà giá trị là NULL, kết quả có thể khác mong đợi.

### 9.3. Identity và sequence

Nếu bảng nền dùng identity column hoặc sequence, trigger cần quyết định nguồn khóa:

- Dùng identity/default bằng cách bỏ cột identity khỏi INSERT.
- Hoặc lấy NEXTVAL từ sequence theo quy ước.
- Nếu view phải trả lại generated key ngay cho caller, cần thiết kế API output riêng; INSTEAD OF trigger không thể gán lại :NEW.

Không tự tạo một sequence thứ hai nếu bảng nền đã có identity/sequence quản lý khóa.

### 9.4. Kiểm tra khóa và số row bị ảnh hưởng

~~~sql
UPDATE employees
SET salary = :NEW.salary
WHERE employee_id = :OLD.employee_id;

IF SQL%ROWCOUNT <> 1 THEN
    RAISE_APPLICATION_ERROR(-20120, 'Expected one employee row');
END IF;
~~~

Kiểm tra số row giúp phát hiện mapping sai hoặc row nền không còn tồn tại. Tuy nhiên, nếu view có thể biểu diễn một row logic từ nhiều row nền, quy tắc cardinality cần được định nghĩa riêng.

## 10. WITH CHECK OPTION và INSTEAD OF trigger

WITH CHECK OPTION trên view thông thường yêu cầu row được INSERT/UPDATE qua view phải tiếp tục thỏa điều kiện của view.

Ví dụ:

~~~sql
CREATE OR REPLACE VIEW active_customers_v AS
SELECT customer_id, customer_name, status
FROM customers
WHERE status = 'ACTIVE'
WITH CHECK OPTION;
~~~

Với DML trực tiếp được Oracle xử lý trên view, CHECK OPTION được áp dụng theo semantics của view.

Tuy nhiên, khi INSERT hoặc UPDATE được xử lý bằng INSTEAD OF trigger, Oracle không tự enforce WITH CHECK OPTION. Trigger body phải tự kiểm tra điều kiện tương ứng.

Ví dụ:

~~~sql
CREATE OR REPLACE TRIGGER trg_active_customers_ins
INSTEAD OF INSERT ON active_customers_v
FOR EACH ROW
BEGIN
    IF :NEW.status <> 'ACTIVE' THEN
        RAISE_APPLICATION_ERROR(
            -20130,
            'Only ACTIVE customers can be inserted through this view'
        );
    END IF;

    INSERT INTO customers(customer_id, customer_name, status)
    VALUES (:NEW.customer_id, :NEW.customer_name, :NEW.status);
END;
/
~~~

Nếu bỏ qua bước kiểm tra, trigger có thể ghi một row không thỏa điều kiện view. Row đó không xuất hiện khi query view, khiến caller tưởng INSERT thất bại hoặc dữ liệu biến mất.

**Quy tắc:** Khi có INSTEAD OF trigger, phải đưa mọi điều kiện lọc quan trọng của view vào logic trigger hoặc một lớp validation được gọi từ trigger.

## 11. Security: trigger có thể thay đổi ranh giới quyền

### 11.1. Quyền thực thi trigger

Trigger được tạo trong schema sở hữu view và chạy theo privilege model của stored PL/SQL. Owner của trigger cần các quyền cần thiết để thao tác bảng nền. Với stored PL/SQL definer-rights, privilege cần cho truy cập object thường phải được cấp trực tiếp, không chỉ thông qua role.

Nếu bảng nền thuộc schema khác, hãy cấp đúng quyền DML cho owner phù hợp:

~~~sql
GRANT INSERT, UPDATE, DELETE
ON hr.employees
TO reporting_owner;
~~~

Không cấp DBA hoặc quyền rộng chỉ để trigger hoạt động.

### 11.2. EXECUTE/DML trên view không có nghĩa được quyền tùy ý trên bảng nền

Một ứng dụng có thể được cấp quyền DML trên view và trigger thực hiện thao tác có kiểm soát trên các bảng nền. Đây là một cách đóng gói access path.

Tuy nhiên, nếu trigger nhận các cột hoặc giá trị không được kiểm tra, caller có thể điều khiển nhiều dữ liệu hơn dự kiến. Trigger cần validate:

- Khóa row.
- Tenant/customer scope.
- Trạng thái nghiệp vụ.
- Các cột được phép thay đổi.
- Giá trị từ client không được tin cậy.

### 11.3. Fine-Grained Access Control trên view

Oracle lưu ý rằng nếu view có row-level security policy (Fine-Grained Access Control/VPD) và đồng thời có INSTEAD OF trigger, policy trên view không được enforce theo cách DML thông thường vì trigger được chạy thay cho DML trên view.

Đây là điểm bảo mật quan trọng. Nếu hệ thống dựa vào VPD policy trên view để giới hạn row, không được giả định policy vẫn bảo vệ DML khi thêm INSTEAD OF trigger.

Phải thiết kế kiểm tra tenant/row access ngay trong trigger hoặc một lớp được bảo vệ tương đương, đồng thời kiểm tra policy ở bảng nền nếu có.

### 11.4. Không dùng view trigger để bỏ qua authorization

Một trigger có thể chạy với quyền owner và ghi vào bảng mà caller không có quyền trực tiếp. Điều đó hữu ích khi API được kiểm soát, nhưng cũng có thể trở thành privilege escalation nếu:

- Trigger nhận table/column name tùy ý.
- Dynamic SQL nối input không an toàn.
- Caller có thể sửa tenant ID hoặc owner ID.
- Trigger không kiểm tra trạng thái/role nghiệp vụ.
- Public view cho phép sửa dữ liệu ngoài phạm vi người dùng.

Chỉ công bố các thao tác cần thiết và kiểm tra quyền theo business identity.

## 12. Transaction, lỗi và rollback

### 12.1. Không COMMIT trong INSTEAD OF trigger

Trigger chạy trong transaction của câu DML gọi nó. Không dùng COMMIT hoặc ROLLBACK trong trigger thông thường:

~~~sql
CREATE OR REPLACE TRIGGER trg_bad_io
INSTEAD OF INSERT ON some_view
FOR EACH ROW
BEGIN
    INSERT INTO base_table(id) VALUES (:NEW.id);
    COMMIT; -- Không hợp lệ trong trigger thông thường
END;
/
~~~

Transaction control trong trigger có thể gây ORA-04092. Caller phải quyết định COMMIT/ROLLBACK sau khi use case hoàn tất.

Không dùng autonomous transaction để commit dữ liệu nghiệp vụ của trigger. Autonomous transaction chỉ phù hợp cho một số tác vụ độc lập như log kỹ thuật, nếu đã hiểu rõ consistency và locking.

### 12.2. Statement atomicity

Giả sử một câu INSERT vào view tạo 100 row. INSTEAD OF trigger chạy cho từng row. Nếu trigger ở row thứ 80 phát sinh exception không được xử lý:

- Câu INSERT trên view thất bại.
- Các thay đổi do câu INSERT và các lần trigger của chính statement đó được rollback như một statement atomic.
- Những thay đổi đã thực hiện trước statement trong cùng transaction không tự động bị rollback toàn bộ.
- Caller có thể quyết định rollback transaction rộng hơn.

Không bắt lỗi rồi bỏ qua nếu điều đó khiến caller nghĩ toàn bộ batch đã thành công.

### 12.3. Chuyển lỗi nghiệp vụ rõ ràng

~~~sql
IF :NEW.department_id IS NULL THEN
    RAISE_APPLICATION_ERROR(-20140, 'Department ID is required');
END IF;
~~~

Giữ mã lỗi ổn định và thông điệp đủ rõ cho caller. Nếu lỗi kỹ thuật từ bảng nền cần được giữ nguyên, có thể để exception propagate hoặc log rồi RAISE.

### 12.4. Không nuốt lỗi

Tránh:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        NULL;
~~~

Nếu trigger bỏ qua lỗi duplicate, FK hoặc lỗi chuyển đổi, trạng thái dữ liệu có thể không đúng với ý nghĩa DML của view. Chỉ xử lý exception khi có quy tắc nghiệp vụ rõ và caller biết kết quả.

## 13. Trigger trên view và trigger trên bảng nền

Một DML qua view có thể tạo chuỗi xử lý:

~~~text
INSERT INTO VIEW
       |
       v
INSTEAD OF trigger trên VIEW
       |
       v
INSERT INTO BASE TABLE
       |
       +--> BEFORE/AFTER row trigger trên BASE TABLE
       |
       +--> constraints / indexes
       |
       v
Kết quả trong cùng transaction
~~~

Trigger trên bảng nền vẫn có thể chạy khi INSTEAD OF trigger thực hiện DML trên bảng đó. Constraint và index của bảng nền cũng tiếp tục được duy trì.

Điều này có thể tạo nhiều tầng trigger. Cần lập sơ đồ thứ tự và side effect:

- INSTEAD OF trigger gọi bảng nào?
- Base table có trigger nào khác?
- Base trigger có ghi audit hoặc cập nhật bảng khác không?
- Có nguy cơ gọi ngược lại view không?
- Có vòng lặp trigger hoặc recursion không?

Không thực hiện DML trên chính view từ INSTEAD OF trigger của view đó nếu không có thiết kế chống đệ quy; nó có thể kích hoạt lại cùng trigger và tạo recursion.

Mutating-table restriction của row trigger trên bảng nền vẫn có thể áp dụng cho các trigger bảng nền. INSTEAD OF trigger không tự động loại bỏ các hạn chế đó.

## 14. Các trường hợp đặc biệt và giới hạn

### 14.1. Editioning view

Oracle Database 19c không cho tạo INSTEAD OF trigger trên editioning view. Editioning view có các quy tắc riêng, chủ yếu cung cấp lớp tương thích schema cho Edition-Based Redefinition.

Nếu view là editioning view, cần thiết kế DML theo các khả năng được Oracle hỗ trợ cho loại view này; không cố thêm INSTEAD OF trigger.

### 14.2. View hierarchy

Nếu view thuộc một hierarchy, INSTEAD OF trigger được tạo trên view không tự động được kế thừa bởi subviews. Mỗi view cần được xem xét theo định nghĩa và trigger của chính nó.

### 14.3. Nested table view columns

Oracle còn hỗ trợ INSTEAD OF trigger trên nested table view columns. Trigger dạng này xử lý từng phần tử của nested table và có thể tham chiếu parent row theo cơ chế correlation name tương ứng.

Đây là trường hợp chuyên biệt, khác với trigger thông thường đặt trên toàn bộ view. Cần đọc cú pháp và ví dụ nested-table-specific trong PL/SQL Language Reference trước khi áp dụng.

### 14.4. View READ ONLY

View được tạo với WITH READ ONLY có mục đích ngăn DML qua view. Không dùng INSTEAD OF trigger như một cách tùy tiện để phá vỡ contract read-only. Nếu thiết kế yêu cầu DML, hãy định nghĩa view/API phù hợp và kiểm tra giới hạn CREATE VIEW/CREATE TRIGGER của Oracle.

### 14.5. Một INSTEAD OF trigger không phải cơ chế thay thế mọi view design

Nếu view có thể đơn giản hóa để tự updatable, ưu tiên cách đơn giản. Trigger bổ sung logic ẩn, cần quyền, test và bảo trì. Chỉ dùng khi mapping DML thực sự cần thiết.

## 15. Khi nào nên dùng INSTEAD OF trigger, khi nào nên dùng API procedure?

| Tiêu chí | INSTEAD OF trigger | Procedure/package API |
| --- | --- | --- |
| Cách gọi | DML trực tiếp lên view | Gọi procedure/function |
| Mapping DML | Trigger ánh xạ từng row | Procedure điều khiển toàn use case |
| Dễ thấy side effect ở call site | Thấp hơn; logic ẩn sau view | Cao hơn; tên procedure thể hiện hành động |
| Bulk operation | Trigger chạy theo row | Có thể thiết kế set-based/BULK |
| Validation phức tạp | Có thể làm nhưng trigger dễ phình to | Thường dễ tổ chức nhiều bước hơn |
| Dùng như SQL façade | Rất phù hợp | Caller phải gọi API |
| Transaction | Dùng transaction của câu DML gọi | Caller/API thiết kế transaction boundary |
| Khả năng test | Test qua DML view và base tables | Test trực tiếp public routine |

INSTEAD OF trigger phù hợp khi caller cần thao tác như DML trên một view và mapping row-level rõ ràng. Package procedure phù hợp khi thao tác là một use case nhiều bước, có kết quả trả về, cần transaction orchestration hoặc xử lý tập dữ liệu lớn.

Hai cơ chế có thể cùng tồn tại: view cung cấp read model; package cung cấp command API. Không cần ép mọi thao tác thay đổi dữ liệu phải đi qua view.

## 16. Theo dõi, kiểm tra và quản lý trigger

### 16.1. USER_TRIGGERS

~~~sql
SELECT trigger_name,
       trigger_type,
       triggering_event,
       table_name,
       status
FROM user_triggers
WHERE table_name = 'EMPLOYEE_DIRECTORY_V'
ORDER BY trigger_name;
~~~

View USER_TRIGGERS cho biết trigger trong schema hiện tại. Với quyền rộng hơn, dùng ALL_TRIGGERS hoặc DBA_TRIGGERS.

### 16.2. Xem source

~~~sql
SELECT line, text
FROM user_source
WHERE name = 'TRG_EMPLOYEE_DIRECTORY_DML'
  AND type = 'TRIGGER'
ORDER BY line;
~~~

### 16.3. Kiểm tra compile errors

~~~sql
SELECT line, position, text
FROM user_errors
WHERE name = 'TRG_EMPLOYEE_DIRECTORY_DML'
  AND type = 'TRIGGER'
ORDER BY sequence;
~~~

Hoặc trong SQL*Plus/SQLcl:

~~~sql
SHOW ERRORS TRIGGER trg_employee_directory_dml;
~~~

### 16.4. Enable và disable

~~~sql
ALTER TRIGGER trg_employee_directory_dml DISABLE;
ALTER TRIGGER trg_employee_directory_dml ENABLE;
~~~

Disable trigger có thể làm DML trên view không còn được ánh xạ như dự kiến hoặc thất bại nếu view không tự updatable. Chỉ disable trong maintenance window và phải có kế hoạch phục hồi.

### 16.5. Thay thế hoặc xóa

~~~sql
CREATE OR REPLACE TRIGGER trg_employee_directory_dml
...
~~~

~~~sql
DROP TRIGGER trg_employee_directory_dml;
~~~

Trước khi thay/xóa, kiểm tra ứng dụng đang phụ thuộc view DML và các grants liên quan.

## 17. Debug và kiểm thử INSTEAD OF trigger

### 17.1. Test riêng từng DML event

Với mỗi view, cần kiểm thử:

- INSERT một row hợp lệ.
- INSERT thiếu giá trị bắt buộc.
- INSERT khóa đã tồn tại.
- UPDATE một cột được phép.
- UPDATE cột read-only hoặc cột dẫn xuất.
- UPDATE không tìm thấy row.
- DELETE một row.
- DELETE row có child references.
- DML nhiều row.

### 17.2. Đối chiếu cả view và bảng nền

Sau DML, không chỉ kiểm tra view:

~~~sql
SELECT *
FROM employee_directory_v
WHERE employee_id = 9001;

SELECT *
FROM employees
WHERE employee_id = 9001;
~~~

Nếu trigger ghi nhiều bảng nền, kiểm tra tất cả bảng liên quan và các audit records.

### 17.3. Kiểm tra statement atomicity

Thử một INSERT nhiều row trong đó một row vi phạm constraint. Xác nhận toàn bộ statement được rollback theo semantics của Oracle, sau đó kiểm tra transaction trước statement vẫn ở trạng thái caller mong muốn.

### 17.4. Kiểm tra concurrency

Nếu trigger đọc trạng thái rồi ghi dữ liệu, có thể xảy ra race condition giữa nhiều session. Dùng:

- Constraint để bảo đảm uniqueness/integrity.
- UPDATE có điều kiện.
- SELECT FOR UPDATE khi cần khóa row.
- Khóa theo thứ tự nhất quán để giảm deadlock.
- Idempotency key cho thao tác có thể retry.

Không dựa vào một SELECT kiểm tra tồn tại rồi mới INSERT nếu unique constraint mới là cơ chế bảo đảm cuối cùng.

### 17.5. Kiểm thử quyền

Đăng nhập bằng application user thực tế:

- Xác nhận user chỉ có quyền cần thiết trên view.
- Xác nhận trigger có thể thao tác base table theo privilege model.
- Kiểm tra không thể sửa tenant/owner khác.
- Kiểm tra VPD/FGA policies và các kiểm soát row-level.
- Kiểm tra trigger không mở ra thao tác ngoài public contract.

## 18. Ví dụ kiểm tra DML mapping qua view

Giả sử các trigger ở phần 6 đã được tạo.

### 18.1. INSERT

~~~sql
INSERT INTO employee_directory_v (
    employee_id,
    first_name,
    last_name,
    salary,
    department_id
)
VALUES (9001, 'AN', 'NGUYEN', 2500, 50);
~~~

Kiểm tra:

~~~sql
SELECT employee_id, last_name, department_id
FROM employees
WHERE employee_id = 9001;
~~~

### 18.2. UPDATE

~~~sql
UPDATE employee_directory_v
SET salary = 2700
WHERE employee_id = 9001;
~~~

Kiểm tra:

~~~sql
SELECT salary
FROM employees
WHERE employee_id = 9001;
~~~

### 18.3. DELETE

~~~sql
DELETE FROM employee_directory_v
WHERE employee_id = 9001;
~~~

Kiểm tra:

~~~sql
SELECT COUNT(*)
FROM employees
WHERE employee_id = 9001;
~~~

### 18.4. COMMIT hoặc ROLLBACK ở caller

~~~sql
COMMIT;
~~~

Hoặc trong môi trường test:

~~~sql
ROLLBACK;
~~~

Trigger không tự commit. Hãy kiểm tra transaction boundary của ứng dụng thực tế.

## 19. Những lỗi thường gặp

| Lỗi/hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| ORA-04098 | Trigger invalid hoặc compile thất bại khi kích hoạt | Xem USER_ERRORS, sửa source và compile lại |
| ORA-04092 | Trigger cố COMMIT hoặc ROLLBACK | Bỏ transaction control khỏi trigger; để caller quản lý |
| ORA-01031 | Trigger owner thiếu quyền trên bảng nền | Cấp trực tiếp đúng object privilege cho owner |
| ORA-01400 | Trigger INSERT NULL vào cột NOT NULL | Validate input hoặc để default của bảng nền hoạt động |
| ORA-00001 | Trigger tạo duplicate primary/unique key | Kiểm tra key mapping và unique constraint |
| ORA-02291 | Giá trị FK không có parent row | Kiểm tra parent key và thứ tự thao tác |
| ORA-02292 | DELETE parent bị child row tham chiếu | Xử lý child theo chính sách referential integrity |
| ORA-01403 | SELECT INTO trong trigger không tìm thấy row | Xử lý NO_DATA_FOUND hoặc dùng DML/logic phù hợp |
| ORA-04091 | Trigger bảng nền query/update bảng đang mutating | Thiết kế lại trigger bảng nền; INSTEAD OF không loại bỏ giới hạn này |
| View DML không thay đổi bảng mong muốn | Trigger map sai khóa hoặc sai bảng nền | Kiểm tra :OLD/:NEW, key và mapping |
| UPDATE chỉ sửa một số cột nhưng trigger ghi đè cột khác | Trigger dùng toàn bộ :NEW không xem xét cột được SET | Dùng UPDATING('COLUMN') hoặc chỉ cập nhật field cần thiết |
| Row không còn xuất hiện trong view sau INSERT | Dữ liệu nền không thỏa WHERE/JOIN của view | Validate điều kiện view trong trigger |
| View có WITH CHECK OPTION nhưng row sai vẫn được ghi | INSTEAD OF trigger không tự enforce CHECK OPTION | Tự kiểm tra predicate trong trigger |
| Policy VPD trên view không giới hạn DML như mong đợi | INSTEAD OF trigger làm policy trên view không được enforce | Đưa authorization vào trigger/bảng nền và test bằng application user |
| Trigger chạy quá chậm với DML nhiều row | Trigger row-level chạy nhiều lần và có SQL lặp | Dùng set-based/package/bulk processing nếu phù hợp |
| DML bị đệ quy | Trigger lại thao tác trên chính view kích hoạt nó | DML trực tiếp bảng nền và kiểm soát call graph |

## 20. Anti-pattern cần tránh

### 20.1. DML lại chính view trong trigger

Không viết:

~~~sql
CREATE OR REPLACE TRIGGER trg_view_io
INSTEAD OF INSERT ON employee_directory_v
FOR EACH ROW
BEGIN
    INSERT INTO employee_directory_v(employee_id, last_name)
    VALUES (:NEW.employee_id, :NEW.last_name);
END;
/
~~~

Lệnh INSERT lại view có thể kích hoạt chính trigger, tạo recursion. Trigger phải thao tác trên bảng nền hoặc gọi package thực hiện DML nền.

### 20.2. Không xác định khóa duy nhất

Nếu DELETE dùng điều kiện không duy nhất:

~~~sql
DELETE FROM employees
WHERE last_name = :OLD.last_name;
~~~

có thể xóa nhiều row. Dùng primary key hoặc một khóa nghiệp vụ được bảo đảm unique.

### 20.3. Coi mọi cột view đều có thể ghi

View có thể chứa cột dẫn xuất, cột aggregate, cột constant/discriminator hoặc cột chỉ phục vụ hiển thị. Không ghi các cột này xuống bảng nền nếu chưa định nghĩa semantics. Nêu rõ cột read-only và từ chối thay đổi nếu cần.

### 20.4. Nuốt exception

Không bắt lỗi rồi NULL chỉ để ứng dụng không nhìn thấy lỗi. Caller cần biết thao tác thất bại để rollback/retry hoặc trả thông báo đúng.

### 20.5. Dùng trigger cho workflow nhiều bước quá lớn

Nếu một DML trên view phải gọi nhiều service, gửi email, cập nhật nhiều hệ thống, thực hiện retry hoặc phối hợp nhiều transaction, hãy cân nhắc package API hoặc application service. Trigger nên giữ mapping DML rõ và đồng bộ với transaction database.

## 21. Checklist thiết kế INSTEAD OF trigger

1. **View có thực sự cần trigger không?** Kiểm tra khả năng inherently updatable và USER_UPDATABLE_COLUMNS.
2. **View thuộc loại nào?** Join view, UNION, aggregate, object view hay nested-table view column.
3. **DML semantics đã rõ chưa?** Xác định INSERT/UPDATE/DELETE map tới bảng nền nào.
4. **Khóa row là gì?** Dùng :OLD key để tìm row cũ; bảo đảm key không mơ hồ.
5. **Cột nào chỉ đọc?** Chặn UPDATE trên cột dẫn xuất hoặc discriminator không được phép sửa.
6. **:OLD/:NEW có được dùng đúng không?** INSTEAD OF trigger chỉ đọc, không gán field.
7. **Mỗi row có thể tạo nhiều DML không?** Đánh giá chi phí khi statement tác động nhiều row.
8. **Constraint/default/identity được xử lý ra sao?** Không vô tình truyền NULL thay cho default.
9. **WITH CHECK OPTION có được enforce thủ công không?** Trigger phải thực hiện điều kiện tương ứng.
10. **Security policy có bị ảnh hưởng không?** Kiểm tra VPD/FGA và authorization theo tenant.
11. **Trigger owner có direct grants không?** Không dựa vào role nếu stored code cần direct object privilege.
12. **Base-table triggers có chạy không?** Lập sơ đồ side effects và tránh recursion/mutating table.
13. **Transaction ownership rõ chưa?** Không COMMIT/ROLLBACK trong trigger.
14. **Exception có được propagate đúng không?** Không nuốt lỗi.
15. **DML multi-row có hiệu năng chấp nhận được không?** Cân nhắc package/set-based/bulk.
16. **Đã test cả ba event chưa?** INSERT, UPDATE, DELETE và failure paths.
17. **Đã test bằng application user chưa?** Kiểm tra quyền thực tế và row-level security.
18. **Có thể thay bằng procedure/package API không?** Chọn abstraction dễ quan sát side effects hơn khi workflow phức tạp.

## 22. Câu hỏi tự kiểm tra

**Câu 1.** INSTEAD OF trigger dùng để giải quyết vấn đề gì khi DML qua view?

**Câu 2.** View inherently updatable có bắt buộc cần INSTEAD OF trigger không?

**Câu 3.** Key-preserved table là gì trong join view?

**Câu 4.** INSTEAD OF trigger có thể tạo trên table không?

**Câu 5.** INSTEAD OF trigger có statement-level không?

**Câu 6.** Có thể khai báo BEFORE hoặc AFTER cho INSTEAD OF trigger không?

**Câu 7.** INSTEAD OF trigger có thể sửa giá trị :NEW không?

**Câu 8.** Khi UPDATE đổi primary key, nên dùng :OLD hay :NEW trong WHERE để tìm row gốc?

**Câu 9.** INSERT, UPDATE và DELETE có giá trị :OLD/:NEW như thế nào?

**Câu 10.** Một view UNION ALL có thể được làm DML-capable bằng INSTEAD OF trigger không?

**Câu 11.** Vì sao phải tự enforce WITH CHECK OPTION trong trigger?

**Câu 12.** INSTEAD OF trigger có thể làm thay đổi semantics của view vốn updatable không?

**Câu 13.** Vì sao VPD policy trên view cần được xem xét lại khi có INSTEAD OF trigger?

**Câu 14.** Trigger có được COMMIT không?

**Câu 15.** Nếu trigger của một row trong INSERT nhiều row phát sinh lỗi không xử lý, statement được xử lý thế nào?

**Câu 16.** Trigger trên bảng nền có thể chạy khi INSTEAD OF trigger DML vào bảng đó không?

**Câu 17.** Vì sao INSTEAD OF trigger có thể chậm với bulk DML?

**Câu 18.** Khi nào package procedure là lựa chọn phù hợp hơn INSTEAD OF trigger?

<details>
<summary>Gợi ý đáp án</summary>

1. Cung cấp cách ánh xạ DML trên view xuống một hoặc nhiều bảng nền khi view không tự updatable hoặc cần semantics riêng.
2. Không. Nếu view tự updatable và không cần custom mapping, DML trực tiếp có thể đủ.
3. Bảng mà key của nó vẫn xác định duy nhất row trong kết quả join theo điều kiện join.
4. Không. INSTEAD OF chỉ áp dụng cho view.
5. Không. Nó chỉ row-level.
6. Không. INSTEAD OF là timing point riêng; không dùng BEFORE/AFTER.
7. Không. Có thể đọc :OLD/:NEW nhưng không được thay đổi field.
8. :OLD để xác định row gốc.
9. INSERT: OLD null, NEW input; UPDATE: OLD trước, NEW mới; DELETE: OLD trước, NEW null.
10. Có. Trigger có thể phân loại row theo discriminator rồi DML vào bảng nền phù hợp.
11. Vì Oracle không enforce CHECK OPTION cho INSERT/UPDATE được thực hiện qua INSTEAD OF trigger.
12. Có. Trigger được ưu tiên và chạy thay cho DML tự động.
13. Vì policy trên view không được enforce như DML thông thường khi trigger thay thế thao tác trên view.
14. Không. Trigger chạy trong transaction gọi và không được COMMIT/ROLLBACK thông thường.
15. Câu DML thất bại và thay đổi của statement đó được rollback; các statement trước đó trong transaction không tự động bị rollback toàn bộ.
16. Có. DML trong trigger trên bảng nền có thể kích hoạt trigger và constraint của bảng nền.
17. Vì trigger chạy một lần cho từng row và có thể thực hiện SQL lặp lại.
18. Khi workflow nhiều bước, cần kết quả trả về, transaction orchestration, bulk processing hoặc side effect rõ tại call site.

</details>

## 23. Tài liệu Oracle chính thức

1. [Oracle Database 19c PL/SQL Language Reference — INSTEAD OF DML Triggers](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/dml-triggers.html): ngữ nghĩa, row-level behavior, :OLD/:NEW và giới hạn của INSTEAD OF trigger.
2. [Oracle Database 19c SQL Language Reference — CREATE TRIGGER](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/CREATE-TRIGGER-statement.html): cú pháp tạo trigger, event predicates và trigger restrictions.
3. [Oracle Database 19c SQL Language Reference — CREATE VIEW](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-VIEW.html): view definition, WITH CHECK OPTION, WITH READ ONLY và editioning view restrictions.
4. [Oracle Database 19c Administrator's Guide — Managing Views](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-views-sequences-and-synonyms.html): updatable views, join views và key-preserved tables.
5. [Oracle Database 19c Reference — USER_UPDATABLE_COLUMNS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_UPDATABLE_COLUMNS.html): metadata về khả năng INSERT/UPDATE/DELETE trên view columns.
6. [Oracle Database 19c Reference — USER_TRIGGERS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_TRIGGERS.html): metadata trigger trong schema hiện tại.
7. [Oracle Database 19c PL/SQL Language Reference — Trigger Design](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/plsql-triggers.html): trigger execution, transaction, restrictions và thiết kế.

**Nguyên tắc cần nhớ:** INSTEAD OF trigger là adapter cho DML qua view: Oracle gọi trigger thay cho thao tác tự động trên view, còn trigger chịu trách nhiệm ánh xạ row xuống bảng nền. Trigger chỉ row-level, chỉ áp dụng trên view, có thể đọc nhưng không sửa :OLD/:NEW, và chạy trong transaction của caller. Phải tự enforce điều kiện view như WITH CHECK OPTION, kiểm tra authorization, khóa row và constraint, đồng thời đánh giá hiệu năng khi DML nhiều row. Nếu mapping trở thành một workflow phức tạp, package procedure thường là giao diện dễ kiểm soát hơn.
