# :OLD, :NEW và xử lý INSERT/UPDATE/DELETE trong Oracle Database

Trong trigger DML của Oracle, **:OLD** và **:NEW** là hai pseudorecord đặc biệt cho phép truy cập giá trị của hàng trước và sau thao tác. Chúng giúp trigger biết một hàng vừa được INSERT, UPDATE hay DELETE, từ đó kiểm tra dữ liệu, gán giá trị mặc định, ghi audit hoặc đồng bộ thông tin liên quan.

Cách hiểu cốt lõi:

- Với **INSERT**, **:NEW** chứa giá trị hàng được thêm; **:OLD** không có giá trị hàng trước.
- Với **UPDATE**, **:OLD** chứa giá trị trước khi sửa và **:NEW** chứa giá trị sau khi áp dụng thay đổi.
- Với **DELETE**, **:OLD** chứa hàng sắp bị xóa; **:NEW** không có giá trị hàng mới.

Hai pseudorecord này chỉ dùng được trong ngữ cảnh row-level trigger. Trigger statement-level không có một hàng cụ thể để tham chiếu. Trong thân trigger, viết **:OLD.column_name** và **:NEW.column_name**; riêng điều kiện **WHEN** của trigger dùng **OLD.column_name** hoặc **NEW.column_name** mà không có dấu hai chấm.

Bài học giải thích vòng đời giá trị OLD/NEW, khác biệt giữa row-level và statement-level trigger, cách xử lý từng loại DML, kiểm tra cột thực sự thay đổi, audit, validation, trigger trên view, lỗi mutating table, compound trigger và các nguyên tắc vận hành.

## 1. Pseudorecord :OLD và :NEW

### 1.1. Pseudorecord là gì?

Pseudorecord là cấu trúc đặc biệt do Oracle cung cấp trong row-level trigger. Nó có cách truy cập giống record với các trường tương ứng cột của bảng hoặc view đang được trigger xử lý.

Ví dụ:

~~~sql
CREATE OR REPLACE TRIGGER trg_employee_salary
BEFORE UPDATE OF salary ON employees
FOR EACH ROW
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        'Old salary = ' || :OLD.salary
    );

    DBMS_OUTPUT.PUT_LINE(
        'New salary = ' || :NEW.salary
    );
END;
/
~~~

Khi một hàng được UPDATE, **:OLD.salary** là mức lương trước thao tác, còn **:NEW.salary** là mức lương sau khi áp dụng giá trị trong câu UPDATE. Trong BEFORE ROW trigger, giá trị NEW vẫn có thể được trigger điều chỉnh trước khi hàng được ghi.

Pseudorecord không phải biến PL/SQL mà lập trình viên khai báo. Không khai báo OLD hoặc NEW trong phần DECLARE, và không dùng chúng bên ngoài trigger tương ứng.

### 1.2. Ma trận OLD/NEW theo DML

| Thao tác | :OLD | :NEW | Ý nghĩa |
| --- | --- | --- | --- |
| INSERT | Không có hàng trước; các trường OLD là NULL | Giá trị hàng sắp được thêm | Đọc dữ liệu mới, có thể gán :NEW trong BEFORE ROW |
| UPDATE | Giá trị trước khi sửa | Giá trị sau khi áp dụng UPDATE | So sánh thay đổi, kiểm tra hoặc điều chỉnh :NEW trong BEFORE ROW |
| DELETE | Giá trị hàng sắp bị xóa | Không có hàng mới; các trường NEW là NULL | Đọc thông tin hàng để audit hoặc kiểm tra |

Có thể ghi nhớ:

~~~text
INSERT:  NULL  -> :NEW
UPDATE:  :OLD  -> :NEW
DELETE:  :OLD  -> NULL
~~~

Đây là cách nhìn theo từng hàng. Một câu lệnh DML có thể tác động nhiều hàng, vì vậy row trigger được gọi nhiều lần, mỗi lần với cặp giá trị tương ứng một hàng.

### 1.3. OLD và NEW không phải hai bản sao có thể sửa tùy ý

- **:OLD** là dữ liệu trước thao tác và chỉ đọc.
- **:NEW** có thể được gán trong BEFORE EACH ROW trigger của INSERT hoặc UPDATE.
- Trong AFTER EACH ROW trigger, **:NEW** chỉ đọc.
- Trong INSTEAD OF trigger trên view, dùng OLD/NEW để đọc giá trị đầu vào và thực hiện DML lên bảng nền; không gán trực tiếp vào pseudorecord.
- Không dùng pseudorecord trong statement-level trigger.

Không thể gán **:OLD.salary := ...**. Cũng không nên cố gán **:NEW** trong AFTER trigger vì thời điểm thay đổi hàng đã qua.

### 1.4. Truy cập theo từng cột

Đọc trường bằng dấu chấm:

~~~sql
:OLD.employee_id
:NEW.employee_id
:OLD.salary
:NEW.salary
~~~

Tên trường tương ứng với cột của bảng/view. Trong trigger nhiều sự kiện, một số trường không có giá trị ở sự kiện cụ thể. Ví dụ trigger xử lý cả INSERT và DELETE thì khi INSERT không có hàng OLD, còn khi DELETE không có hàng NEW.

## 2. Row-level trigger và statement-level trigger

### 2.1. Row-level trigger

Trigger có mệnh đề FOR EACH ROW là row-level trigger:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_row
AFTER UPDATE ON orders
FOR EACH ROW
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        'Changed order ' || :OLD.order_id
    );
END;
/
~~~

Nếu UPDATE tác động 100 hàng, trigger row-level chạy 100 lần. Mỗi lần OLD và NEW đại diện cho một hàng khác nhau.

Row-level trigger phù hợp khi cần:
- Kiểm tra giá trị từng hàng.
- Gán giá trị cột trước khi lưu.
- So sánh OLD và NEW.
- Ghi audit theo từng hàng.
- Tạo hành động phụ thuộc dữ liệu cụ thể của hàng.

### 2.2. Statement-level trigger

Trigger không có FOR EACH ROW là statement-level trigger:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_statement
AFTER UPDATE ON orders
BEGIN
    DBMS_OUTPUT.PUT_LINE('An UPDATE statement completed');
END;
/
~~~

Trigger chạy một lần cho câu lệnh UPDATE, không phải một lần cho mỗi hàng. Nó không có OLD hoặc NEW, vì vậy không thể biết trực tiếp từng hàng nào đã thay đổi.

Statement-level trigger phù hợp với công việc ở cấp câu lệnh, chẳng hạn:
- Ghi nhận một đợt thao tác bắt đầu/kết thúc.
- Khởi tạo hoặc dọn trạng thái dùng trong trigger.
- Tính toán tổng hợp sau khi tất cả hàng đã được xử lý.
- Thực hiện công việc cần truy vấn lại bảng sau statement.

### 2.3. Câu lệnh không tác động hàng nào

Với DML statement hợp lệ, statement-level trigger vẫn có thể chạy một lần dù predicate không khớp hàng nào. Row-level trigger chỉ chạy khi có hàng thực sự được xử lý.

~~~sql
UPDATE orders
SET status = 'CLOSED'
WHERE order_id = -999;
~~~

Nếu không có hàng phù hợp:
- AFTER STATEMENT trigger cho sự kiện UPDATE vẫn được gọi.
- AFTER EACH ROW trigger không được gọi.

Điểm này quan trọng khi dùng statement trigger để ghi nhận một lần chạy batch: trigger ghi nhận câu lệnh đã chạy, không đồng nghĩa có hàng đã thay đổi.

### 2.4. Thứ tự các thời điểm trigger

Một DML statement thông thường có các giai đoạn:

~~~text
BEFORE STATEMENT
       |
       v
  Với từng hàng:
  BEFORE EACH ROW
       |
       v
  Oracle áp dụng thay đổi hàng
       |
       v
  AFTER EACH ROW
       |
       v
AFTER STATEMENT
~~~

Trigger statement-level chạy một lần ở đầu/cuối statement. Trigger row-level chạy quanh thao tác của từng hàng. Khi có nhiều trigger cùng timing/event, không nên dựa vào thứ tự ngẫu nhiên; nếu cần điều khiển thứ tự, xem cơ chế FOLLOWS/PRECEDES được hỗ trợ cho loại trigger và phiên bản cụ thể.

## 3. Sử dụng INSERTING, UPDATING và DELETING

### 3.1. Các điều kiện nhận diện sự kiện

Trong thân DML trigger, Oracle cung cấp các điều kiện:
- INSERTING: trigger đang xử lý nhánh INSERT.
- UPDATING: trigger đang xử lý nhánh UPDATE.
- DELETING: trigger đang xử lý nhánh DELETE.

Ví dụ một trigger xử lý nhiều sự kiện:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_dml
AFTER INSERT OR UPDATE OR DELETE ON orders
FOR EACH ROW
BEGIN
    IF INSERTING THEN
        DBMS_OUTPUT.PUT_LINE('INSERT order ' || :NEW.order_id);

    ELSIF UPDATING THEN
        DBMS_OUTPUT.PUT_LINE('UPDATE order ' || :OLD.order_id);

    ELSIF DELETING THEN
        DBMS_OUTPUT.PUT_LINE('DELETE order ' || :OLD.order_id);
    END IF;
END;
/
~~~

Trong mỗi nhánh, hãy dùng pseudorecord phù hợp với sự kiện.

### 3.2. UPDATING('column_name')

UPDATING('column_name') kiểm tra cột có xuất hiện trong danh sách SET của câu UPDATE hay không.

~~~sql
IF UPDATING('SALARY') THEN
    DBMS_OUTPUT.PUT_LINE('SALARY was included in SET list');
END IF;
~~~

Điều này không khẳng định giá trị thực sự thay đổi. Ví dụ:

~~~sql
UPDATE employees
SET salary = salary
WHERE employee_id = 100;
~~~

UPDATING('SALARY') vẫn TRUE vì SALARY nằm trong SET list, dù giá trị cũ và mới giống nhau.

### 3.3. UPDATE OF trong khai báo trigger

Có thể giới hạn trigger chỉ kích hoạt cho UPDATE có nhắc đến một số cột:

~~~sql
CREATE OR REPLACE TRIGGER trg_salary_change
AFTER UPDATE OF salary ON employees
FOR EACH ROW
BEGIN
    IF :OLD.salary <> :NEW.salary THEN
        DBMS_OUTPUT.PUT_LINE('Salary value changed');
    END IF;
END;
/
~~~

UPDATE OF salary là điều kiện ở mức khai báo sự kiện. Nó vẫn có thể kích hoạt khi câu lệnh viết SET salary = salary; so sánh OLD/NEW bên trong giúp phân biệt giá trị có thay đổi thực tế hay không.

### 3.4. Một trigger xử lý nhiều sự kiện

Một trigger có thể khai báo nhiều sự kiện DML:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_audit
AFTER INSERT OR UPDATE OR DELETE ON orders
FOR EACH ROW
BEGIN
    IF INSERTING THEN
        -- Xử lý INSERT
        NULL;
    ELSIF UPDATING THEN
        -- Xử lý UPDATE
        NULL;
    ELSIF DELETING THEN
        -- Xử lý DELETE
        NULL;
    END IF;
END;
/
~~~

Dùng ELSIF để bảo đảm mỗi lần xử lý đi vào đúng nhánh. Không truy cập NEW trong nhánh DELETE hoặc OLD như thể có dữ liệu trước INSERT.

## 4. So sánh giá trị OLD và NEW

### 4.1. So sánh đơn giản khi cột không NULL

Nếu cột luôn NOT NULL, có thể dùng:

~~~sql
IF :OLD.status <> :NEW.status THEN
    -- Giá trị status đã thay đổi
END IF;
~~~

Với cột nullable, phép so sánh <> có thể cho kết quả UNKNOWN khi một phía là NULL. Khi đó điều kiện IF không được coi là TRUE.

### 4.2. So sánh có xử lý NULL

Một cách rõ ràng:

~~~sql
IF (:OLD.status <> :NEW.status)
   OR (:OLD.status IS NULL AND :NEW.status IS NOT NULL)
   OR (:OLD.status IS NOT NULL AND :NEW.status IS NULL)
THEN
    DBMS_OUTPUT.PUT_LINE('STATUS changed');
END IF;
~~~

Điều kiện xử lý đủ ba trường hợp:
- Cả hai có giá trị và khác nhau.
- OLD NULL, NEW có giá trị.
- OLD có giá trị, NEW NULL.

Nếu cả hai cùng NULL, giá trị không thay đổi.

### 4.3. Dùng DECODE để so sánh NULL

Trong Oracle, DECODE xem hai NULL là bằng nhau. Có thể dùng:

~~~sql
IF DECODE(:OLD.status, :NEW.status, 0, 1) = 1 THEN
    DBMS_OUTPUT.PUT_LINE('STATUS changed');
END IF;
~~~

Cách này ngắn nhưng cần hiểu quy tắc DECODE. Với logic quan trọng, biểu thức xử lý NULL tường minh có thể dễ bảo trì hơn.

### 4.4. So sánh nhiều cột

Không cần so sánh mọi cột nếu trigger chỉ quan tâm một số thuộc tính. Hãy giới hạn bằng UPDATE OF hoặc UPDATING('COLUMN'), sau đó so sánh OLD/NEW của cột liên quan.

~~~sql
IF UPDATING('SALARY')
   AND (
       (:OLD.salary <> :NEW.salary)
       OR (:OLD.salary IS NULL AND :NEW.salary IS NOT NULL)
       OR (:OLD.salary IS NOT NULL AND :NEW.salary IS NULL)
   )
THEN
    -- Ghi nhận thay đổi salary
END IF;
~~~

Tránh viết một trigger lớn xử lý tất cả cột và tất cả nghiệp vụ nếu có thể tách logic rõ ràng.

## 5. Gán :NEW trong BEFORE INSERT/UPDATE

### 5.1. Tự đặt giá trị trước khi lưu

BEFORE EACH ROW trigger có thể thay đổi giá trị NEW của hàng INSERT hoặc UPDATE.

~~~sql
CREATE OR REPLACE TRIGGER trg_employees_biu
BEFORE INSERT OR UPDATE ON employees
FOR EACH ROW
BEGIN
    IF INSERTING THEN
        :NEW.created_at := COALESCE(
            :NEW.created_at,
            SYSTIMESTAMP
        );
    END IF;

    IF UPDATING THEN
        :NEW.updated_at := SYSTIMESTAMP;
    END IF;
END;
/
~~~

Khi INSERT, trigger đặt CREATED_AT nếu caller không cung cấp giá trị. Khi UPDATE, trigger cập nhật UPDATED_AT.

Đây là ví dụ minh họa. Nếu chỉ cần giá trị mặc định khi INSERT, có thể dùng DEFAULT trên cột; nếu cần cập nhật timestamp khi UPDATE, trigger có thể phù hợp hoặc ứng dụng có thể quản lý rõ ràng ở tầng service.

### 5.2. Chuẩn hóa dữ liệu

Ví dụ chuẩn hóa email:

~~~sql
CREATE OR REPLACE TRIGGER trg_customers_email_biu
BEFORE INSERT OR UPDATE OF email ON customers
FOR EACH ROW
BEGIN
    IF :NEW.email IS NOT NULL THEN
        :NEW.email := LOWER(TRIM(:NEW.email));
    END IF;
END;
/
~~~

Giá trị sau chuẩn hóa sẽ được lưu. Tuy nhiên, cần cân nhắc quy tắc nghiệp vụ và collation; không phải mọi trường dữ liệu đều nên tự động chuyển lowercase.

### 5.3. Không gán :NEW trong AFTER ROW

AFTER ROW không phải thời điểm để sửa giá trị hàng:

~~~sql
-- Ví dụ sai về mục đích:
CREATE OR REPLACE TRIGGER trg_bad_after
AFTER UPDATE ON employees
FOR EACH ROW
BEGIN
    :NEW.updated_at := SYSTIMESTAMP;
END;
/
~~~

Nếu cần sửa giá trị hàng, dùng BEFORE EACH ROW hoặc xử lý trong câu DML gốc. AFTER trigger phù hợp để quan sát kết quả và thực hiện hành động phụ trợ.

### 5.4. Dùng DEFAULT khi trigger không cần thiết

Nếu cột chỉ cần giá trị mặc định lúc INSERT:

~~~sql
CREATE TABLE application_events (
    event_id NUMBER GENERATED ALWAYS AS IDENTITY,
    event_type VARCHAR2(50) NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_application_events PRIMARY KEY (event_id)
);
~~~

DEFAULT thường đơn giản và dễ hiểu hơn trigger chỉ để gán một giá trị mặc định. Dùng trigger khi cần logic phụ thuộc OLD/NEW hoặc nhiều điều kiện DML.

## 6. Validation dữ liệu bằng OLD/NEW

### 6.1. Chặn thay đổi không hợp lệ

Ví dụ không cho phép lùi ngày tạo đơn:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_date_check
BEFORE UPDATE OF created_at ON orders
FOR EACH ROW
BEGIN
    IF :NEW.created_at < :OLD.created_at THEN
        RAISE_APPLICATION_ERROR(
            -20031,
            'Created date cannot move backwards'
        );
    END IF;
END;
/
~~~

RAISE_APPLICATION_ERROR trả lỗi nghiệp vụ do ứng dụng định nghĩa. Khi trigger phát sinh exception không được xử lý, câu DML gây ra trigger sẽ thất bại.

### 6.2. Kiểm tra salary

~~~sql
CREATE OR REPLACE TRIGGER trg_salary_limit
BEFORE INSERT OR UPDATE OF salary ON employees
FOR EACH ROW
BEGIN
    IF :NEW.salary < 0 THEN
        RAISE_APPLICATION_ERROR(
            -20032,
            'Salary must not be negative'
        );
    END IF;
END;
/
~~~

Với điều kiện đơn giản chỉ kiểm tra một cột, CHECK constraint thường là lựa chọn tốt hơn:

~~~sql
ALTER TABLE employees
ADD CONSTRAINT ck_employees_salary_nonnegative
CHECK (salary >= 0);
~~~

Ưu tiên constraint cho các quy tắc toàn vẹn dữ liệu khai báo được. Trigger phù hợp khi quy tắc cần OLD/NEW, nhiều bước hoặc logic không thể biểu diễn bằng constraint.

### 6.3. Ngăn thay đổi khóa định danh

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_pk_immutable
BEFORE UPDATE OF order_id ON orders
FOR EACH ROW
BEGIN
    IF :OLD.order_id <> :NEW.order_id THEN
        RAISE_APPLICATION_ERROR(
            -20033,
            'ORDER_ID cannot be changed'
        );
    END IF;
END;
/
~~~

Nên cân nhắc thiết kế PK ổn định và quyền UPDATE của ứng dụng trước khi thêm trigger. Có thể thu hồi quyền UPDATE trên cột nếu phù hợp với mô hình quyền.

### 6.4. Trigger không thay thế constraint đồng thời

Một trigger kiểm tra kiểu “không được trùng mã” bằng cách SELECT COUNT(*) rồi INSERT có thể gặp race condition khi hai session chạy đồng thời. Cả hai có thể cùng thấy chưa tồn tại rồi cùng INSERT.

Dùng UNIQUE constraint để database bảo đảm duy nhất trong concurrency. Trigger không phải cách thay thế constraint cho các quy tắc uniqueness.

## 7. Xử lý INSERT, UPDATE và DELETE trong audit trigger

### 7.1. Tạo bảng ví dụ

~~~sql
CREATE TABLE orders_demo (
    order_id     NUMBER GENERATED ALWAYS AS IDENTITY,
    status       VARCHAR2(20) DEFAULT 'NEW' NOT NULL,
    total_amount NUMBER(12,2) NOT NULL,
    created_at   TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    updated_at   TIMESTAMP,
    CONSTRAINT pk_orders_demo PRIMARY KEY (order_id),
    CONSTRAINT ck_orders_demo_amount CHECK (total_amount >= 0)
);

CREATE TABLE orders_demo_audit (
    audit_id     NUMBER GENERATED ALWAYS AS IDENTITY,
    action_type  VARCHAR2(10) NOT NULL,
    order_id     NUMBER NOT NULL,
    old_status   VARCHAR2(20),
    new_status   VARCHAR2(20),
    old_amount   NUMBER(12,2),
    new_amount   NUMBER(12,2),
    changed_at   TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    changed_by   VARCHAR2(128),
    CONSTRAINT pk_orders_demo_audit PRIMARY KEY (audit_id)
);
~~~

Bảng audit giữ giá trị trước/sau cho các cột cần theo dõi. Bảng này không cần FK tới ORDERS_DEMO nếu muốn lưu lịch sử sau khi đơn hàng bị xóa.

### 7.2. Trigger cập nhật timestamp

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_demo_bu
BEFORE UPDATE ON orders_demo
FOR EACH ROW
BEGIN
    :NEW.updated_at := SYSTIMESTAMP;
END;
/
~~~

Trigger này chỉ sửa NEW trong BEFORE UPDATE row trigger.

### 7.3. Trigger audit cho cả ba thao tác

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_demo_audit
AFTER INSERT OR UPDATE OR DELETE ON orders_demo
FOR EACH ROW
BEGIN
    IF INSERTING THEN
        INSERT INTO orders_demo_audit (
            action_type, order_id, old_status, new_status,
            old_amount, new_amount, changed_at, changed_by
        )
        VALUES (
            'INSERT',
            :NEW.order_id,
            NULL,
            :NEW.status,
            NULL,
            :NEW.total_amount,
            SYSTIMESTAMP,
            SYS_CONTEXT('USERENV', 'SESSION_USER')
        );

    ELSIF UPDATING THEN
        INSERT INTO orders_demo_audit (
            action_type, order_id, old_status, new_status,
            old_amount, new_amount, changed_at, changed_by
        )
        VALUES (
            'UPDATE',
            :OLD.order_id,
            :OLD.status,
            :NEW.status,
            :OLD.total_amount,
            :NEW.total_amount,
            SYSTIMESTAMP,
            SYS_CONTEXT('USERENV', 'SESSION_USER')
        );

    ELSIF DELETING THEN
        INSERT INTO orders_demo_audit (
            action_type, order_id, old_status, new_status,
            old_amount, new_amount, changed_at, changed_by
        )
        VALUES (
            'DELETE',
            :OLD.order_id,
            :OLD.status,
            NULL,
            :OLD.total_amount,
            NULL,
            SYSTIMESTAMP,
            SYS_CONTEXT('USERENV', 'SESSION_USER')
        );
    END IF;
END;
/
~~~

Đặc điểm:
- INSERT ghi ID và giá trị mới từ NEW.
- UPDATE ghi cả giá trị cũ từ OLD và giá trị mới từ NEW.
- DELETE ghi giá trị cũ từ OLD; các cột NEW được lưu NULL.
- SYS_CONTEXT('USERENV','SESSION_USER') ghi nhận user database đăng nhập.

### 7.4. Thử ba thao tác

INSERT:

~~~sql
INSERT INTO orders_demo (status, total_amount)
VALUES ('NEW', 250000);
~~~

UPDATE:

~~~sql
UPDATE orders_demo
SET status = 'PAID',
    total_amount = 275000
WHERE order_id = 1;
~~~

DELETE:

~~~sql
DELETE FROM orders_demo
WHERE order_id = 1;
~~~

Xem audit:

~~~sql
SELECT action_type,
       order_id,
       old_status,
       new_status,
       old_amount,
       new_amount,
       changed_at,
       changed_by
FROM   orders_demo_audit
ORDER  BY audit_id;
~~~

ID 1 chỉ là ví dụ nếu đây là hàng đầu tiên. Trong môi trường dùng chung, lấy ID thực tế từ INSERT bằng RETURNING INTO hoặc truy vấn theo khóa nghiệp vụ đã biết.

### 7.5. Audit trigger tham gia transaction

Audit row được INSERT trong cùng transaction với DML gốc. Nếu ứng dụng ROLLBACK thao tác trên ORDERS_DEMO, audit row do trigger thêm cũng bị rollback.

Đây thường là hành vi phù hợp cho audit thay đổi dữ liệu nghiệp vụ: audit phản ánh thay đổi đã commit. Nếu cần ghi nhận cả lần thử bị rollback, cần thiết kế logging khác và hiểu rõ rủi ro của autonomous transaction. Không tự ý thêm PRAGMA AUTONOMOUS_TRANSACTION vào audit trigger chỉ để giữ log sau rollback; nó có thể tạo lịch sử không phản ánh trạng thái cuối và gây vấn đề khóa/deadlock.

Với yêu cầu audit bảo mật hoặc tuân thủ, xem Oracle Unified Auditing và cơ chế audit được quản trị tập trung thay vì tự xây trigger như giải pháp duy nhất.

## 8. Điều kiện WHEN và tham chiếu OLD/NEW

### 8.1. WHEN clause

Row-level trigger có thể có mệnh đề WHEN để chỉ chạy khi điều kiện đúng:

~~~sql
CREATE OR REPLACE TRIGGER trg_closed_order
AFTER UPDATE OF status ON orders_demo
FOR EACH ROW
WHEN (NEW.status = 'CLOSED')
BEGIN
    INSERT INTO orders_demo_audit (
        action_type, order_id, old_status, new_status,
        old_amount, new_amount, changed_at, changed_by
    )
    VALUES (
        'CLOSE',
        :OLD.order_id,
        :OLD.status,
        :NEW.status,
        :OLD.total_amount,
        :NEW.total_amount,
        SYSTIMESTAMP,
        SYS_CONTEXT('USERENV', 'SESSION_USER')
    );
END;
/
~~~

Trong WHEN clause viết NEW.status không có dấu hai chấm. Trong thân PL/SQL trigger viết :NEW.status.

### 8.2. WHEN chỉ là điều kiện đơn giản

WHEN clause không phải một block PL/SQL đầy đủ. Không viết câu SELECT, subquery hoặc câu lệnh nhiều bước bên trong. Nếu điều kiện phức tạp, để trigger chạy và kiểm tra trong phần BEGIN...END.

### 8.3. Không dùng WHEN thay cho so sánh OLD/NEW phức tạp

Nếu cần so sánh OLD và NEW có xử lý NULL, hoặc gọi hàm nghiệp vụ, hãy viết IF trong thân trigger. Điều này dễ đọc và kiểm soát hơn.

## 9. Mutating table và ORA-04091

### 9.1. Mutating table là gì?

Khi row-level trigger đang xử lý một bảng, Oracle có thể không cho trigger truy vấn hoặc thay đổi chính bảng đang bị DML tác động. Bảng đang trong trạng thái thay đổi này được gọi là mutating table.

Ví dụ trigger có vấn đề:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_bad_check
AFTER UPDATE OF status ON orders_demo
FOR EACH ROW
DECLARE
    v_count NUMBER;
BEGIN
    SELECT COUNT(*)
    INTO   v_count
    FROM   orders_demo
    WHERE  status = :NEW.status;
END;
/
~~~

Khi chạy UPDATE trên ORDERS_DEMO, trigger row-level lại SELECT chính ORDERS_DEMO. Oracle có thể phát sinh ORA-04091: table is mutating, trigger/function may not see it.

Lý do là ở thời điểm row trigger chạy, statement có thể mới xử lý một phần hàng. Nếu cho phép đọc bảng như trạng thái hoàn chỉnh, kết quả có thể không nhất quán.

### 9.2. Không chữa bằng cách bỏ qua exception

Không bắt ORA-04091 rồi bỏ qua. Cần thay đổi thiết kế:
- Dùng OLD và NEW cho thông tin của hàng hiện tại.
- Dùng statement-level trigger nếu công việc cần thực hiện sau khi statement kết thúc.
- Dùng compound trigger để thu thập dữ liệu ở row section rồi xử lý ở AFTER STATEMENT.
- Dùng constraint hoặc mô hình dữ liệu khác nếu quy tắc có thể khai báo.

### 9.3. Compound trigger

Compound trigger gom nhiều timing section trong một trigger và chia sẻ trạng thái PL/SQL trong phạm vi một DML statement:
- BEFORE STATEMENT.
- BEFORE EACH ROW.
- AFTER EACH ROW.
- AFTER STATEMENT.

Pseudorecord OLD/NEW chỉ có ở các row section. AFTER STATEMENT không có :OLD/:NEW, nhưng có thể dùng dữ liệu đã lưu trong collection ở các row section.

Ví dụ ghi nhận thay đổi trạng thái rồi ghi audit sau statement:

~~~sql
CREATE TABLE orders_demo_status_audit (
    audit_id    NUMBER GENERATED ALWAYS AS IDENTITY,
    order_id    NUMBER NOT NULL,
    old_status  VARCHAR2(20),
    new_status  VARCHAR2(20),
    changed_at  TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_orders_demo_status_audit PRIMARY KEY (audit_id)
);
~~~

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_status_ct
FOR UPDATE OF status ON orders_demo
COMPOUND TRIGGER

    TYPE t_id_tab IS TABLE OF orders_demo.order_id%TYPE
        INDEX BY PLS_INTEGER;
    TYPE t_status_tab IS TABLE OF orders_demo.status%TYPE
        INDEX BY PLS_INTEGER;

    g_order_ids  t_id_tab;
    g_old_status t_status_tab;
    g_new_status t_status_tab;
    g_count      PLS_INTEGER := 0;

    AFTER EACH ROW IS
    BEGIN
        IF (:OLD.status <> :NEW.status)
           OR (:OLD.status IS NULL AND :NEW.status IS NOT NULL)
           OR (:OLD.status IS NOT NULL AND :NEW.status IS NULL)
        THEN
            g_count := g_count + 1;
            g_order_ids(g_count) := :NEW.order_id;
            g_old_status(g_count) := :OLD.status;
            g_new_status(g_count) := :NEW.status;
        END IF;
    END AFTER EACH ROW;

    AFTER STATEMENT IS
    BEGIN
        IF g_count > 0 THEN
            FORALL i IN 1 .. g_count
                INSERT INTO orders_demo_status_audit (
                    order_id,
                    old_status,
                    new_status,
                    changed_at
                )
                VALUES (
                    g_order_ids(i),
                    g_old_status(i),
                    g_new_status(i),
                    SYSTIMESTAMP
                );
        END IF;
    END AFTER STATEMENT;

END trg_orders_status_ct;
/
~~~

Trong ví dụ:
- AFTER EACH ROW chỉ đọc OLD/NEW và lưu các giá trị cần thiết vào collection.
- AFTER STATEMENT chạy sau khi các hàng của statement đã được xử lý.
- AFTER STATEMENT không truy cập trực tiếp pseudorecord.
- FORALL ghi các dòng audit theo mảng, giảm số lần chuyển đổi giữa PL/SQL và SQL.

Compound trigger có trạng thái riêng cho mỗi statement. Nếu statement lỗi và rollback, các thay đổi do trigger thực hiện trong transaction cũng rollback theo quy tắc transaction thông thường.

### 9.4. Khi nào dùng compound trigger?

Dùng khi cần:
- Thu thập thông tin từng hàng.
- Tính toán hoặc kiểm tra sau khi toàn bộ statement hoàn tất.
- Tránh truy vấn mutating table trong row-level section.
- Gom thao tác DML phụ trợ theo batch.

Không dùng compound trigger chỉ để làm code phức tạp hơn. Nếu chỉ cần gán NEW hoặc ghi một dòng audit đơn giản cho từng hàng, row trigger thường dễ hiểu hơn.

## 10. INSTEAD OF trigger trên view

### 10.1. Mục đích

Một số view không thể INSERT/UPDATE/DELETE trực tiếp vì có join, group hoặc cấu trúc phức tạp. INSTEAD OF trigger định nghĩa cách chuyển DML trên view thành thao tác trên bảng nền.

INSTEAD OF trigger là row-level trigger trên view. Có thể đọc OLD và NEW để biết giá trị người dùng gửi tới view và giá trị cũ mà view đại diện.

### 10.2. Ví dụ view đơn giản

~~~sql
CREATE OR REPLACE VIEW order_summary_v AS
SELECT order_id,
       status
FROM   orders_demo;
~~~

Tạo trigger:

~~~sql
CREATE OR REPLACE TRIGGER trg_order_summary_v_iud
INSTEAD OF INSERT OR UPDATE OR DELETE ON order_summary_v
FOR EACH ROW
BEGIN
    IF INSERTING THEN
        INSERT INTO orders_demo (status, total_amount)
        VALUES (:NEW.status, 0);

    ELSIF UPDATING THEN
        UPDATE orders_demo
        SET status = :NEW.status
        WHERE order_id = :OLD.order_id;

    ELSIF DELETING THEN
        DELETE FROM orders_demo
        WHERE order_id = :OLD.order_id;
    END IF;
END;
/
~~~

Ví dụ giả định bảng nền cho phép amount bằng 0. Trong ứng dụng thật, cần xác định đầy đủ cách sinh khóa, giá trị bắt buộc và ánh xạ mọi cột cần thiết.

### 10.3. OLD/NEW trong INSTEAD OF trigger

Trong INSTEAD OF trigger:
- :NEW thể hiện dữ liệu mà câu DML gửi tới view muốn tạo/cập nhật.
- :OLD thể hiện dữ liệu cũ của hàng view khi UPDATE/DELETE.
- Trigger dùng các giá trị đó để DML lên bảng nền.
- Không gán trực tiếp :NEW để thay đổi dữ liệu view; hãy quyết định giá trị cần ghi vào bảng nền trong câu DML tương ứng.

## 11. Các tình huống DML cần phân biệt

### 11.1. UPDATE không đổi giá trị

~~~sql
UPDATE orders_demo
SET status = status
WHERE order_id = 10;
~~~

Sự kiện UPDATE vẫn xảy ra. UPDATING('STATUS') là TRUE. Nếu chỉ muốn audit khi giá trị thực sự khác, so sánh OLD/NEW với xử lý NULL.

### 11.2. DELETE khác TRUNCATE

DELETE là DML và kích hoạt DELETE trigger theo phạm vi row/statement đã khai báo.

TRUNCATE là DDL. Nó không kích hoạt row-level DELETE trigger cho từng hàng như câu DELETE. Không dùng trigger DELETE để kỳ vọng ghi audit từng hàng khi DBA chạy TRUNCATE PARTITION hoặc TRUNCATE TABLE.

Nếu cần audit việc truncate, hãy quản lý quyền DDL, dùng auditing phù hợp hoặc quy trình quản trị riêng.

### 11.3. MERGE

MERGE có thể thực hiện INSERT cho hàng không khớp và UPDATE cho hàng khớp. Trigger INSERT/UPDATE liên quan có thể được kích hoạt theo thao tác thực tế mà MERGE thực hiện.

Khi dùng trigger với MERGE:
- Kiểm tra nhánh INSERT và UPDATE riêng.
- Dùng INSERTING/UPDATING trong trigger để phân biệt.
- Thử trường hợp matched và not matched.
- Không giả định MERGE luôn chỉ gọi một loại trigger.

### 11.4. DML nhiều hàng

Một câu UPDATE có thể sửa nhiều hàng. Row trigger chạy một lần trên mỗi hàng; statement trigger chạy một lần cho câu lệnh.

Không giả định thứ tự các hàng mà trigger row-level xử lý là thứ tự khóa chính hoặc thứ tự trong câu SELECT. Nếu nghiệp vụ phụ thuộc thứ tự, hãy thiết kế thao tác riêng có ORDER BY/processing logic rõ ràng thay vì dựa vào trigger firing order.

## 12. Transaction và exception trong trigger

### 12.1. Trigger tham gia transaction gọi nó

DML bên trong trigger thông thường thuộc cùng transaction với câu lệnh kích hoạt. Nếu câu DML ngoài rollback, thao tác phụ trợ trong trigger cũng rollback.

Không gọi COMMIT hoặc ROLLBACK trong trigger thông thường. Trigger không được tự ý kết thúc transaction của caller.

### 12.2. Exception trong trigger

Nếu trigger phát sinh exception không được xử lý, lỗi truyền về câu DML và statement thất bại. Ví dụ:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_amount_guard
BEFORE INSERT OR UPDATE OF total_amount ON orders_demo
FOR EACH ROW
BEGIN
    IF :NEW.total_amount < 0 THEN
        RAISE_APPLICATION_ERROR(
            -20040,
            'Total amount must be non-negative'
        );
    END IF;
END;
/
~~~

Khi INSERT/UPDATE với amount âm, trigger từ chối thao tác. Tuy nhiên, quy tắc đơn giản này nên được thể hiện bằng CHECK constraint nếu không cần logic trigger.

### 12.3. Autonomous transaction cần cân nhắc kỹ

Có thể khai báo autonomous transaction trong một số trigger để log độc lập với transaction chính. Nhưng khi dùng, audit có thể commit dù DML nghiệp vụ rollback. Điều đó làm ý nghĩa audit khác đi và có thể gây deadlock nếu autonomous transaction chờ tài nguyên do transaction cha giữ.

Không dùng autonomous transaction như cách mặc định để giữ log. Chỉ dùng khi yêu cầu nghiệp vụ xác định rõ cần ghi nhận sự kiện độc lập với transaction chính và đã đánh giá tương tác khóa.

## 13. Thiết kế trigger dễ bảo trì

### 13.1. Ưu tiên constraint khi có thể

Dùng:
- NOT NULL cho cột bắt buộc.
- CHECK cho điều kiện trên một hàng.
- PRIMARY KEY cho định danh.
- UNIQUE cho giá trị duy nhất.
- FOREIGN KEY cho quan hệ tham chiếu.

Trigger nên dành cho logic cần OLD/NEW, audit tùy biến, chuẩn hóa hoặc hành vi không biểu diễn gọn bằng constraint.

### 13.2. Giữ trigger ngắn và có một mục đích

Trigger chạy ngầm khi DML xảy ra. Nếu trigger quá dài hoặc gọi nhiều procedure phụ, người bảo trì khó hiểu vì sao một câu INSERT/UPDATE lại gây ra side effect.

Nên:
- Đặt tên trigger thể hiện timing/event/mục đích.
- Dùng INSERTING, UPDATING, DELETING rõ ràng.
- Chỉ truy cập cột cần thiết.
- Không thực hiện truy vấn nặng cho từng hàng nếu có thể xử lý sau statement.
- Tránh gọi dịch vụ ngoài hoặc thao tác không transactional trong trigger.
- Kiểm thử cả DML một hàng và nhiều hàng.

### 13.3. Tránh trigger phụ thuộc thứ tự không được bảo đảm

Nếu nhiều trigger cùng chạy trên một bảng và cùng timing point, không giả định thứ tự tự nhiên. Khi cần sắp thứ tự, xem cú pháp FOLLOWS/PRECEDES và giới hạn áp dụng trong phiên bản Oracle. Tốt hơn là gom các bước phụ thuộc chặt vào một trigger hoặc một API nghiệp vụ rõ ràng.

### 13.4. Tránh vòng lặp trigger

Trigger trên bảng A có thể DML bảng B, rồi trigger bảng B lại DML A. Điều này có thể tạo chuỗi trigger hoặc recursion ngoài dự kiến.

Vẽ rõ luồng phụ thuộc và tránh để trigger gọi ngược lại chính bảng đang thay đổi. Nếu cần đồng bộ hai chiều, cân nhắc thiết kế service/procedure nghiệp vụ hoặc cơ chế queue thay vì cascade trigger khó kiểm soát.

## 14. Kiểm tra và quản lý trigger

### 14.1. Xem trigger trong schema

~~~sql
SELECT trigger_name,
       table_name,
       trigger_type,
       triggering_event,
       status
FROM   user_triggers
ORDER  BY table_name, trigger_name;
~~~

Các cột giúp xác định trigger thuộc bảng nào, loại trigger, sự kiện và trạng thái ENABLED/DISABLED.

### 14.2. Xem source code

~~~sql
SELECT line,
       text
FROM   user_source
WHERE  type = 'TRIGGER'
AND    name = 'TRG_ORDERS_DEMO_AUDIT'
ORDER  BY line;
~~~

Có thể dùng DBMS_METADATA.GET_DDL để lấy DDL đầy đủ của trigger nếu có quyền phù hợp.

### 14.3. Xem lỗi biên dịch

Trong SQL*Plus/SQLcl có thể dùng:

~~~sql
SHOW ERRORS TRIGGER trg_orders_demo_audit;
~~~

Hoặc xem lỗi trong dictionary:

~~~sql
SELECT line,
       position,
       text
FROM   user_errors
WHERE  type = 'TRIGGER'
AND    name = 'TRG_ORDERS_DEMO_AUDIT'
ORDER  BY sequence;
~~~

SHOW ERRORS là lệnh client của SQL*Plus/SQLcl và được một số script runner mô phỏng. Nó không phải câu SQL thông thường.

### 14.4. Enable và disable

~~~sql
ALTER TRIGGER trg_orders_demo_audit DISABLE;

ALTER TRIGGER trg_orders_demo_audit ENABLE;
~~~

Có thể enable/disable toàn bộ trigger trên bảng bằng ALTER TABLE ... ENABLE/DISABLE ALL TRIGGERS. Đây là thao tác quản trị có tác động rộng; cần ghi nhận trạng thái ban đầu và kiểm tra các trigger liên quan trước khi chạy.

Không disable trigger trên production chỉ để tăng tốc load nếu chưa đánh giá audit, validation, đồng bộ và side effect mà trigger đang đảm nhiệm.

## 15. Bài thực hành tổng hợp

Dùng schema học tập và bảng demo ở mục 7. Không chạy các lệnh xóa hoặc thay đổi dữ liệu trên hệ thống thật khi chưa có bản sao.

### Bài 1 — Quan sát OLD/NEW khi INSERT

Tạo BEFORE INSERT row trigger in các giá trị :NEW.status và :NEW.total_amount. Quan sát rằng không có hàng OLD trước INSERT.

### Bài 2 — Quan sát OLD/NEW khi UPDATE

Cập nhật status và amount. In cả OLD lẫn NEW để xác nhận hai giá trị thuộc hai thời điểm khác nhau.

### Bài 3 — Quan sát DELETE

Tạo BEFORE DELETE trigger và in :OLD.order_id, :OLD.status. Giải thích vì sao không dùng NEW để lấy hàng sắp xóa.

### Bài 4 — Một trigger cho ba sự kiện

Viết AFTER INSERT OR UPDATE OR DELETE trigger. Dùng INSERTING, UPDATING, DELETING để chọn đúng nhánh.

### Bài 5 — UPDATING('column')

Chạy UPDATE SET status = status. Quan sát UPDATING('STATUS') vẫn TRUE. Sau đó thêm so sánh OLD/NEW để chỉ ghi nhận thay đổi thực tế.

### Bài 6 — Gán :NEW

Tạo BEFORE INSERT trigger tự điền CREATED_AT nếu NULL. Tạo BEFORE UPDATE trigger cập nhật UPDATED_AT. Xác nhận giá trị được lưu.

### Bài 7 — Validation

Tạo trigger từ chối amount âm bằng RAISE_APPLICATION_ERROR. Sau đó thay bằng CHECK constraint và so sánh cách khai báo.

### Bài 8 — Audit ba sự kiện

Tạo audit table và trigger ghi INSERT/UPDATE/DELETE. Thử COMMIT và ROLLBACK để xác nhận audit row tham gia cùng transaction.

### Bài 9 — Mutating table

Tạo row trigger truy vấn lại bảng đang bị UPDATE. Quan sát ORA-04091 trong schema test. Giải thích vì sao không nên bỏ qua exception.

### Bài 10 — Compound trigger

Viết compound trigger thu thập ID và trạng thái OLD/NEW trong AFTER EACH ROW, sau đó ghi audit trong AFTER STATEMENT. Thử UPDATE nhiều hàng.

### Bài 11 — INSTEAD OF trigger

Tạo view và trigger chuyển INSERT/UPDATE/DELETE trên view thành DML trên bảng nền. Kiểm tra ánh xạ OLD/NEW.

### Bài 12 — DELETE và TRUNCATE

So sánh DELETE với TRUNCATE trên bảng test. Xác nhận DELETE trigger không chạy theo từng hàng khi dùng TRUNCATE.

### Bài 13 — MERGE

Viết MERGE có cả nhánh WHEN MATCHED UPDATE và WHEN NOT MATCHED INSERT. Ghi nhận nhánh trigger tương ứng.

### Bài 14 — Trigger firing và nhiều hàng

Tạo statement-level trigger và row-level trigger cho cùng một sự kiện. Chạy DML tác động nhiều hàng rồi DML không khớp hàng nào. Ghi nhận số lần từng loại trigger chạy.

## 16. Những nhầm lẫn thường gặp

**“:OLD và :NEW dùng được trong mọi trigger.”** Không. Chúng dành cho row-level trigger; statement-level trigger không có pseudorecord của một hàng.

**“INSERT có :OLD chứa giá trị trước khi thêm.”** Không. Không có hàng trước INSERT; OLD không có giá trị hàng và các trường OLD là NULL.

**“DELETE có :NEW chứa hàng sau khi xóa.”** Không. DELETE chỉ có giá trị hàng cũ qua OLD.

**“Có thể sửa :NEW trong AFTER trigger.”** Không. Chỉ gán NEW trong BEFORE EACH ROW của INSERT/UPDATE.

**“UPDATING('SALARY') nghĩa salary đã thay đổi.”** Không. Nó chỉ cho biết SALARY có mặt trong SET list.

**“Statement trigger chạy một lần cho mỗi hàng.”** Không. Nó chạy một lần cho statement; row trigger mới chạy theo từng hàng.

**“UPDATE không đổi giá trị thì trigger không chạy.”** Trigger vẫn có thể chạy vì statement là UPDATE; so sánh OLD/NEW để phát hiện thay đổi thực tế.

**“DELETE và TRUNCATE đều kích hoạt DELETE trigger.”** Không. TRUNCATE là DDL và không kích hoạt row DELETE trigger.

**“Có thể SELECT bảng đang cập nhật từ row trigger.”** Có thể gặp ORA-04091. Dùng OLD/NEW hoặc compound trigger/statement-level logic.

**“Audit trigger luôn giữ log kể cả khi transaction rollback.”** Không. Audit DML thông thường cùng transaction và rollback theo DML gốc.

**“Trigger là nơi tốt nhất để kiểm tra mọi constraint.”** Không. Ưu tiên NOT NULL, CHECK, UNIQUE, PRIMARY KEY và FOREIGN KEY khi có thể.

**“Thứ tự nhiều trigger cùng timing luôn cố định.”** Không nên giả định; dùng cơ chế ordering được hỗ trợ hoặc thiết kế lại phụ thuộc.

## 17. Tài liệu Oracle tham khảo

- [Oracle Database PL/SQL Language Reference — Triggers](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/triggers.html): loại trigger, timing point, row-level và statement-level.
- [Oracle Database PL/SQL Language Reference — Correlation Names and Pseudorecords](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/correlation-names-and-pseudorecords.html): OLD, NEW và cách truy cập pseudorecord.
- [Oracle Database PL/SQL Language Reference — Compound DML Triggers](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/dml-triggers.html): compound trigger và các timing section.
- [Oracle Database Error Messages — ORA-04091](https://docs.oracle.com/en/database/oracle/oracle-database/19/errmg/ORA-04091.html): lỗi mutating table.
- [Oracle Database SQL Language Reference — CREATE TRIGGER](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TRIGGER.html): cú pháp tạo trigger và điều kiện WHEN.
- [Oracle Database Security Guide — Auditing](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/): các cơ chế audit và kiểm soát bảo mật.

:OLD và :NEW cho trigger biết trạng thái hàng trước và sau DML. INSERT chủ yếu dùng NEW, DELETE dùng OLD, UPDATE dùng cả hai. Chọn row-level khi cần dữ liệu từng hàng, statement-level khi xử lý cấp câu lệnh; dùng BEFORE ROW để gán NEW, AFTER ROW để quan sát và audit. Với kiểm tra đơn giản, ưu tiên constraint; với logic cần xử lý nhiều hàng hoặc tránh mutating table, cân nhắc compound trigger. **Luôn kiểm tra đúng timing, event và phạm vi transaction trước khi đưa trigger vào production.**
