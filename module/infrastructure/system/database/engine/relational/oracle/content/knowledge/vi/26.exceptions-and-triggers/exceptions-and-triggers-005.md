# BEFORE, AFTER, row-level và statement-level trigger trong Oracle

DML trigger là chương trình PL/SQL được Oracle tự động gọi khi một sự kiện INSERT, UPDATE hoặc DELETE xảy ra trên bảng hoặc view. Trigger cho phép thực hiện logic gắn với thay đổi dữ liệu, chẳng hạn chuẩn hóa giá trị trước khi ghi, ghi audit, duy trì dữ liệu phụ trợ hoặc áp dụng quy tắc cần chạy dù dữ liệu được thay đổi từ ứng dụng, SQL client hay batch job.

Khi thiết kế trigger, cần phân biệt hai trục độc lập:

- **Timing:** trigger chạy trước hay sau thao tác DML — BEFORE hoặc AFTER.
- **Granularity:** trigger chạy một lần cho cả câu lệnh hay một lần cho từng hàng bị tác động — statement-level hoặc row-level.

Kết hợp hai trục này tạo ra bốn timing point phổ biến: BEFORE STATEMENT, BEFORE EACH ROW, AFTER EACH ROW và AFTER STATEMENT. Mỗi loại có phạm vi dữ liệu và mục đích khác nhau. Chọn sai timing hoặc granularity có thể dẫn tới logic lặp nhiều lần, không truy cập được :OLD/:NEW, lỗi mutating table hoặc thay đổi dữ liệu khó kiểm soát.

Bài học giải thích vòng đời trigger, pseudorecord :OLD/:NEW, điều kiện WHEN, hành vi với DML nhiều hàng, thứ tự chạy, compound trigger, transaction, lỗi, bảo mật, quản trị và cách kiểm thử.

## 1. DML trigger là gì?

Trigger là stored PL/SQL unit được database tự động thực thi khi sự kiện đã khai báo xảy ra. Với DML trigger trên bảng, sự kiện có thể là:

- INSERT: thêm hàng.
- UPDATE: thay đổi hàng.
- DELETE: xóa hàng.

Ví dụ trigger đơn giản ghi nhận thời điểm tạo đơn:

~~~sql
CREATE OR REPLACE TRIGGER orders_before_insert
BEFORE INSERT ON orders
FOR EACH ROW
BEGIN
    IF :NEW.created_at IS NULL THEN
        :NEW.created_at := CAST(SYSTIMESTAMP AS TIMESTAMP);
    END IF;
END;
/
~~~

Trigger này được gọi trước khi Oracle ghi từng hàng được insert. Từ khóa FOR EACH ROW xác định đây là row-level trigger. Trigger có thể gán giá trị cho :NEW trước khi hàng được lưu.

Nếu bỏ FOR EACH ROW, trigger trở thành statement-level trigger và chạy một lần cho câu INSERT, bất kể câu lệnh tác động bao nhiêu hàng.

### 1.1. Trigger khác procedure được gọi tường minh

Procedure chỉ chạy khi một chương trình gọi nó. Trigger được Oracle gọi tự động khi sự kiện tương ứng xảy ra.

| Đặc điểm | Procedure | DML trigger |
|---|---|---|
| Cách chạy | Caller gọi trực tiếp | Database tự gọi khi DML event xảy ra |
| Thời điểm | Theo luồng chương trình | Theo timing point đã khai báo |
| Tham số | Có thể khai báo IN/OUT/IN OUT | Không nhận tham số theo kiểu procedure |
| Dữ liệu hàng cũ/mới | Caller phải truyền hoặc truy vấn | Row trigger có :OLD và :NEW |
| Tính nhìn thấy | Lời gọi thường hiện trong source caller | Có thể bị ẩn sau một câu DML |
| Mục đích | API database, xử lý được gọi có chủ đích | Phản ứng với sự kiện dữ liệu |


## 2. Hai trục phân loại: BEFORE/AFTER và row/statement

### 2.1. BEFORE và AFTER

- **BEFORE trigger:** chạy trước khi Oracle thực hiện thao tác DML tại timing point tương ứng. BEFORE row trigger phù hợp để kiểm tra hoặc chuẩn hóa :NEW.
- **AFTER trigger:** chạy sau thao tác DML tại timing point tương ứng. AFTER row trigger phù hợp để ghi audit về thay đổi đã thực hiện; AFTER statement trigger phù hợp để xử lý tổng thể sau câu lệnh.

BEFORE/AFTER mô tả thời điểm trigger chạy tương đối với câu lệnh DML và các hàng được xử lý. Nó không có nghĩa AFTER trigger chạy sau COMMIT. Trigger AFTER vẫn chạy trong cùng transaction của câu DML; nếu transaction rollback, các thay đổi do trigger thực hiện cũng rollback theo, trừ trường hợp chủ động dùng autonomous transaction.

### 2.2. Row-level và statement-level

- **Row-level trigger:** có FOR EACH ROW và chạy một lần cho mỗi hàng được câu lệnh DML tác động.
- **Statement-level trigger:** không có FOR EACH ROW và chạy một lần cho mỗi câu lệnh DML kích hoạt trigger.

Ví dụ một UPDATE tác động 100 hàng:

| Trigger type | Số lần chạy |
|---|---:|
| BEFORE STATEMENT | 1 |
| BEFORE EACH ROW | 100 |
| AFTER EACH ROW | 100 |
| AFTER STATEMENT | 1 |

Nếu câu UPDATE không tìm thấy hàng nào, statement-level trigger vẫn chạy cho câu lệnh đó; row-level trigger không có hàng để chạy nên không được gọi.

### 2.3. Bốn timing point

| Timing point | Granularity | Công việc phù hợp |
|---|---|---|
| BEFORE STATEMENT | Một lần/câu lệnh | Khởi tạo trạng thái, ghi nhận bắt đầu, kiểm tra điều kiện cấp statement |
| BEFORE EACH ROW | Một lần/hàng | Gán mặc định, chuẩn hóa :NEW, kiểm tra giá trị hàng |
| AFTER EACH ROW | Một lần/hàng | Audit từng thay đổi, ghi nhận giá trị :OLD/:NEW |
| AFTER STATEMENT | Một lần/câu lệnh | Tổng hợp hoặc xử lý sau khi toàn bộ hàng đã được xử lý |

Một trigger có thể khai báo nhiều sự kiện DML, ví dụ INSERT OR UPDATE OR DELETE. Khi đó các timing point được thực hiện cho từng loại sự kiện tương ứng.

## 3. Cú pháp tạo DML trigger

Mẫu cú pháp đơn giản:

~~~sql
CREATE OR REPLACE TRIGGER trigger_name
    BEFORE | AFTER
    INSERT OR UPDATE OR DELETE
    ON table_name
    [FOR EACH ROW]
    [WHEN (condition)]
DECLARE
    -- Khai báo cục bộ nếu cần
BEGIN
    -- Trigger body
END;
/
~~~

Các phần chính:

- CREATE OR REPLACE TRIGGER: tạo mới hoặc thay source trigger.
- BEFORE/AFTER: chọn timing.
- INSERT/UPDATE/DELETE: chọn sự kiện.
- ON table_name: bảng hoặc view mà trigger gắn vào.
- FOR EACH ROW: chọn row-level; bỏ đi là statement-level.
- WHEN: điều kiện bổ sung cho row-level trigger.
- DECLARE: phần khai báo tùy chọn.
- BEGIN ... END: phần thân PL/SQL.

Ví dụ trigger chỉ chạy khi salary được nêu trong SET list:

~~~sql
CREATE OR REPLACE TRIGGER employees_salary_audit
AFTER UPDATE OF salary ON employees
FOR EACH ROW
BEGIN
    INSERT INTO employee_salary_audit (
        employee_id,
        old_salary,
        new_salary,
        changed_at
    ) VALUES (
        :OLD.employee_id,
        :OLD.salary,
        :NEW.salary,
        SYSTIMESTAMP
    );
END;
/
~~~

UPDATE OF salary chỉ định trigger gắn với UPDATE có nhắc cột salary trong mệnh đề SET. Điều này không tự bảo đảm giá trị thực tế đã đổi. Ví dụ UPDATE employees SET salary = salary vẫn có thể kích hoạt trigger vì cột salary xuất hiện trong SET list. Nếu chỉ muốn ghi audit khi giá trị khác, cần kiểm tra :OLD và :NEW trong trigger.

## 4. Row-level trigger và pseudorecord :OLD, :NEW

Trong row-level trigger, Oracle cung cấp hai pseudorecord:

- :OLD: giá trị hàng trước thao tác DML.
- :NEW: giá trị hàng sau thao tác DML hoặc giá trị sẽ được ghi.

Chúng là cấu trúc đặc biệt do Oracle cung cấp trong trigger, không phải biến record do lập trình viên khai báo.

### 4.1. :OLD và :NEW theo sự kiện

| Sự kiện | :OLD | :NEW |
|---|---|---|
| INSERT | Không có giá trị hàng cũ; không sử dụng như hàng hợp lệ | Hàng sắp được insert |
| UPDATE | Hàng trước khi update | Hàng sau khi update |
| DELETE | Hàng trước khi delete | Không có giá trị hàng mới |

Với INSERT, các trường :OLD không có giá trị hàng cũ; với DELETE, :NEW không có giá trị hàng mới. Không viết logic phụ thuộc vào giá trị không tồn tại của thao tác tương ứng.

### 4.2. BEFORE EACH ROW có thể thay đổi :NEW

Ví dụ chuẩn hóa email và gán thời gian tạo:

~~~sql
CREATE OR REPLACE TRIGGER customers_before_write
BEFORE INSERT OR UPDATE OF email ON customers
FOR EACH ROW
BEGIN
    IF INSERTING AND :NEW.created_at IS NULL THEN
        :NEW.created_at := CAST(SYSTIMESTAMP AS TIMESTAMP);
    END IF;

    IF :NEW.email IS NOT NULL THEN
        :NEW.email := LOWER(TRIM(:NEW.email));
    END IF;
END;
/
~~~

BEFORE row trigger có thể gán trường :NEW cho INSERT và UPDATE. Điều này cho phép chuẩn hóa giá trị ngay trước khi Oracle ghi hàng.

Không thể gán giá trị cho :OLD. Cũng không thể dùng :NEW để sửa hàng trong AFTER row trigger; tại thời điểm AFTER, thao tác hàng đã diễn ra. Nếu cần thay đổi giá trị được lưu, hãy dùng BEFORE row trigger hoặc đưa phép chuẩn hóa vào câu DML/API.

### 4.3. AFTER EACH ROW đọc giá trị trước và sau

Ví dụ audit:

~~~sql
CREATE TABLE employee_salary_audit (
    employee_id NUMBER,
    old_salary  NUMBER,
    new_salary  NUMBER,
    changed_by  VARCHAR2(128),
    changed_at  TIMESTAMP
);
~~~

~~~sql
CREATE OR REPLACE TRIGGER employees_salary_audit
AFTER UPDATE OF salary ON employees
FOR EACH ROW
BEGIN
    INSERT INTO employee_salary_audit (
        employee_id,
        old_salary,
        new_salary,
        changed_by,
        changed_at
    ) VALUES (
        :OLD.employee_id,
        :OLD.salary,
        :NEW.salary,
        SYS_CONTEXT('USERENV', 'SESSION_USER'),
        SYSTIMESTAMP
    );
END;
/
~~~

Mỗi hàng được update sẽ tạo một bản ghi audit trong cùng transaction. Nếu transaction chính rollback, bản ghi audit này cũng rollback.

### 4.4. Không dùng dấu hai chấm trong WHEN clause

Trong thân trigger, tham chiếu pseudorecord dùng cú pháp :OLD.column và :NEW.column. Trong mệnh đề WHEN, cú pháp tham chiếu không có dấu hai chấm:

~~~sql
CREATE OR REPLACE TRIGGER employees_high_salary
AFTER INSERT OR UPDATE OF salary ON employees
FOR EACH ROW
WHEN (NEW.salary >= 100000)
BEGIN
    INSERT INTO high_salary_log (
        employee_id,
        salary_value,
        recorded_at
    ) VALUES (
        :NEW.employee_id,
        :NEW.salary,
        SYSTIMESTAMP
    );
END;
/
~~~

WHEN chỉ dùng cho row-level trigger. Không khai báo WHEN cho statement-level trigger. Điều kiện WHEN được Oracle kiểm tra cho từng hàng trước khi gọi trigger body.

### 4.5. NULL và so sánh giá trị cũ/mới

Trong Oracle, biểu thức :OLD.salary <> :NEW.salary trả UNKNOWN nếu một phía là NULL. Nếu cần phát hiện cả chuyển đổi NULL sang có giá trị hoặc ngược lại, phải viết điều kiện xử lý NULL rõ ràng.

~~~sql
IF (:OLD.salary <> :NEW.salary)
   OR (:OLD.salary IS NULL AND :NEW.salary IS NOT NULL)
   OR (:OLD.salary IS NOT NULL AND :NEW.salary IS NULL)
THEN
    -- Giá trị thực sự thay đổi
    NULL;
END IF;
~~~

Nếu cột được khai báo NOT NULL, điều kiện so sánh đơn giản có thể đủ. Hãy xác định nullability và semantics mong muốn trước khi viết audit condition.


## 5. Statement-level trigger

Statement-level trigger chạy một lần cho câu lệnh DML, không có FOR EACH ROW.

Ví dụ ghi nhận thời điểm một câu lệnh UPDATE bắt đầu và kết thúc:

~~~sql
CREATE TABLE dml_statement_log (
    table_name  VARCHAR2(128),
    action_name VARCHAR2(10),
    phase_name  VARCHAR2(20),
    logged_at   TIMESTAMP,
    session_user_name VARCHAR2(128)
);
~~~

~~~sql
CREATE OR REPLACE TRIGGER employees_update_statement
BEFORE UPDATE ON employees
BEGIN
    INSERT INTO dml_statement_log (
        table_name,
        action_name,
        phase_name,
        logged_at,
        session_user_name
    ) VALUES (
        'EMPLOYEES',
        'UPDATE',
        'BEFORE',
        SYSTIMESTAMP,
        SYS_CONTEXT('USERENV', 'SESSION_USER')
    );
END;
/
~~~

Trigger chạy một lần trước câu UPDATE, kể cả khi câu UPDATE tác động nhiều hàng hoặc không tác động hàng nào.

Có thể tạo AFTER statement trigger để ghi nhận pha kết thúc:

~~~sql
CREATE OR REPLACE TRIGGER employees_update_after_stmt
AFTER UPDATE ON employees
BEGIN
    INSERT INTO dml_statement_log (
        table_name,
        action_name,
        phase_name,
        logged_at,
        session_user_name
    ) VALUES (
        'EMPLOYEES',
        'UPDATE',
        'AFTER',
        SYSTIMESTAMP,
        SYS_CONTEXT('USERENV', 'SESSION_USER')
    );
END;
/
~~~

Đây là audit kỹ thuật minh họa. Với yêu cầu audit bảo mật và truy vết chính thức, cần đánh giá Oracle Unified Auditing hoặc cơ chế audit được quản trị tập trung; trigger tự viết không thay thế mọi khả năng audit của database.

### 5.1. Statement trigger không có :OLD/:NEW

Statement-level trigger không gắn với một hàng cụ thể, vì vậy không có pseudorecord :OLD và :NEW. Không thể lấy :NEW.employee_id trong statement-level trigger.

Nếu cần biết giá trị từng hàng, phải dùng row-level trigger hoặc compound trigger có section EACH ROW.

### 5.2. Statement trigger vẫn chạy khi không có hàng phù hợp

~~~sql
UPDATE employees
SET salary = salary * 1.05
WHERE department_id = -999;
~~~

Nếu không có nhân viên thuộc department -999:
- BEFORE STATEMENT vẫn chạy một lần.
- AFTER STATEMENT vẫn chạy một lần.
- BEFORE EACH ROW và AFTER EACH ROW không chạy vì không có hàng nào được xử lý.

Điều này hữu ích khi cần theo dõi câu lệnh DML đã được gửi, kể cả câu lệnh không làm thay đổi hàng nào.

## 6. Vòng đời và thứ tự timing point

Với một DML statement trên bảng có đủ trigger tương ứng, thứ tự khái quát là:

~~~text
DML statement bắt đầu
        |
        v
BEFORE STATEMENT trigger
        |
        v
Với từng hàng được xử lý:
    BEFORE EACH ROW trigger
        |
        v
    Oracle thực hiện thay đổi hàng
        |
        v
    AFTER EACH ROW trigger
        |
        v
Lặp tới hàng tiếp theo
        |
        v
AFTER STATEMENT trigger
        |
        v
DML statement hoàn tất
        |
        v
Caller tiếp tục transaction
        |
        v
COMMIT hoặc ROLLBACK do transaction owner quyết định
~~~

Sơ đồ thể hiện thứ tự các timing point. Nó không có nghĩa AFTER STATEMENT là sau COMMIT. Trigger vẫn chạy trước khi transaction được commit.

### 6.1. Ví dụ UPDATE nhiều hàng

~~~sql
UPDATE employees
SET salary = salary * 1.10
WHERE department_id = 20;
~~~

Giả sử 25 hàng được tác động:
- BEFORE STATEMENT chạy một lần.
- BEFORE EACH ROW chạy 25 lần.
- AFTER EACH ROW chạy 25 lần.
- AFTER STATEMENT chạy một lần.

Nếu có nhiều trigger cùng timing point và cùng sự kiện, không nên phụ thuộc vào thứ tự ngầm định giữa chúng. Hãy gộp logic có quan hệ phụ thuộc vào một trigger hoặc dùng cơ chế FOLLOWS khi phiên bản và loại trigger hỗ trợ, đồng thời tài liệu hóa thứ tự.

### 6.2. Một trigger khai báo nhiều sự kiện

~~~sql
CREATE OR REPLACE TRIGGER employees_dml_audit
AFTER INSERT OR UPDATE OR DELETE ON employees
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

Các conditional predicates INSERTING, UPDATING, DELETING cho biết loại DML đang kích hoạt trigger. Chúng có thể được dùng trong trigger body để phân nhánh.

Có thể kiểm tra một cột cụ thể được nhắc trong SET list bằng UPDATING('COLUMN_NAME'). Điều này kiểm tra cột có xuất hiện trong mệnh đề SET, không khẳng định giá trị đã thay đổi.

### 6.3. UPDATE OF và thay đổi giá trị thực tế

~~~sql
CREATE OR REPLACE TRIGGER employees_salary_change
AFTER UPDATE OF salary ON employees
FOR EACH ROW
BEGIN
    IF :OLD.salary <> :NEW.salary THEN
        NULL; -- Xử lý thay đổi thực tế
    END IF;
END;
/
~~~

Câu lệnh sau vẫn có thể kích hoạt trigger vì salary nằm trong SET list:

~~~sql
UPDATE employees
SET salary = salary
WHERE employee_id = 101;
~~~

Nhưng điều kiện trong body không chạy nếu giá trị cũ và mới bằng nhau (với giả định salary không NULL). Cần phân biệt cột được chỉ định trong câu lệnh và dữ liệu thực sự đổi.

## 7. BEFORE EACH ROW: chuẩn hóa và kiểm tra hàng

BEFORE row trigger thường phù hợp để:
- Gán giá trị mặc định nếu caller bỏ trống.
- Chuẩn hóa chuỗi.
- Kiểm tra quy tắc phụ thuộc giá trị hàng.
- Gán một số thuộc tính kỹ thuật trước khi lưu.
- Tạo khóa nếu không dùng identity/default/sequence trực tiếp.

Ví dụ kiểm tra số lượng:

~~~sql
CREATE OR REPLACE TRIGGER order_items_validate
BEFORE INSERT OR UPDATE OF quantity ON order_items
FOR EACH ROW
BEGIN
    IF :NEW.quantity IS NULL OR :NEW.quantity <= 0 THEN
        RAISE_APPLICATION_ERROR(
            -20101,
            'Quantity must be greater than zero'
        );
    END IF;
END;
/
~~~

Tuy nhiên, nếu quy tắc có thể diễn đạt bằng CHECK constraint, hãy ưu tiên constraint:

~~~sql
ALTER TABLE order_items
ADD CONSTRAINT order_items_quantity_ck
CHECK (quantity > 0);
~~~

Constraint minh bạch hơn, được database bảo đảm và không cần trigger để thực hiện một kiểm tra đơn giản. Trigger phù hợp hơn khi logic không thể biểu diễn bằng constraint khai báo.

### 7.1. Gán ID trong trigger

Các hệ thống cũ có thể dùng BEFORE INSERT trigger để lấy NEXTVAL:

~~~sql
CREATE OR REPLACE TRIGGER orders_assign_id
BEFORE INSERT ON orders
FOR EACH ROW
WHEN (NEW.order_id IS NULL)
BEGIN
    :NEW.order_id := orders_seq.NEXTVAL;
END;
/
~~~

Với phiên bản Oracle hỗ trợ identity column hoặc DEFAULT sequence expression phù hợp, có thể cân nhắc cơ chế khai báo thay cho trigger. Lựa chọn phụ thuộc yêu cầu tương thích, schema hiện hữu và cách quản lý sequence.

## 8. AFTER EACH ROW: audit và phản ứng theo từng hàng

AFTER row trigger phù hợp khi cần đọc giá trị cũ/mới sau khi Oracle xử lý hàng.

Ví dụ audit cả INSERT, UPDATE và DELETE:

~~~sql
CREATE TABLE employee_change_audit (
    employee_id NUMBER,
    operation   VARCHAR2(10),
    old_salary  NUMBER,
    new_salary  NUMBER,
    changed_at  TIMESTAMP,
    changed_by  VARCHAR2(128)
);
~~~

~~~sql
CREATE OR REPLACE TRIGGER employees_change_audit
AFTER INSERT OR UPDATE OF salary OR DELETE ON employees
FOR EACH ROW
BEGIN
    IF INSERTING THEN
        INSERT INTO employee_change_audit (
            employee_id, operation, old_salary, new_salary,
            changed_at, changed_by
        ) VALUES (
            :NEW.employee_id, 'INSERT', NULL, :NEW.salary,
            SYSTIMESTAMP, SYS_CONTEXT('USERENV', 'SESSION_USER')
        );

    ELSIF UPDATING THEN
        INSERT INTO employee_change_audit (
            employee_id, operation, old_salary, new_salary,
            changed_at, changed_by
        ) VALUES (
            :NEW.employee_id, 'UPDATE', :OLD.salary, :NEW.salary,
            SYSTIMESTAMP, SYS_CONTEXT('USERENV', 'SESSION_USER')
        );

    ELSIF DELETING THEN
        INSERT INTO employee_change_audit (
            employee_id, operation, old_salary, new_salary,
            changed_at, changed_by
        ) VALUES (
            :OLD.employee_id, 'DELETE', :OLD.salary, NULL,
            SYSTIMESTAMP, SYS_CONTEXT('USERENV', 'SESSION_USER')
        );
    END IF;
END;
/
~~~

Ví dụ tập trung minh họa pseudorecord và conditional predicates. Trong hệ thống thật, cần xác định cột audit, dữ liệu nhạy cảm, quyền truy cập audit, chính sách retention và cách xử lý lỗi.

### 8.1. Trigger audit cùng transaction

DML trong trigger thông thường thuộc cùng transaction với câu lệnh kích hoạt nó. Nếu insert audit thất bại và exception không được xử lý theo cách phù hợp, câu DML chính có thể thất bại. Nếu caller rollback, cả thay đổi nghiệp vụ và audit row trong cùng transaction rollback.

Đây thường là hành vi mong muốn nếu audit phải phản ánh chính xác những thay đổi đã commit. Nếu yêu cầu ghi lại cả lần thử thất bại, phải thiết kế logging độc lập có chủ đích và hiểu rõ autonomous transaction.

## 9. AFTER STATEMENT: xử lý sau toàn bộ câu lệnh

AFTER statement trigger phù hợp khi cần thực hiện công việc một lần sau khi tất cả hàng của câu DML đã được xử lý.

~~~sql
CREATE OR REPLACE TRIGGER employees_after_update_stmt
AFTER UPDATE ON employees
BEGIN
    INSERT INTO dml_statement_log (
        table_name,
        action_name,
        phase_name,
        logged_at,
        session_user_name
    ) VALUES (
        'EMPLOYEES',
        'UPDATE',
        'STATEMENT_COMPLETE',
        SYSTIMESTAMP,
        SYS_CONTEXT('USERENV', 'SESSION_USER')
    );
END;
/
~~~

Nếu một câu UPDATE thay đổi 5.000 hàng, trigger vẫn chỉ insert một dòng log statement. Nếu cần log 5.000 thay đổi riêng, dùng row-level trigger.

### 9.1. Statement trigger không có danh sách hàng tự động

Statement-level trigger không cung cấp collection chứa các hàng vừa thay đổi. Nếu cần tổng hợp theo các hàng bị ảnh hưởng, có thể:
- Dùng row-level trigger thu thập thông tin.
- Dùng compound trigger chia sẻ trạng thái giữa các timing point.
- Đưa xử lý tổng hợp vào procedure/API được gọi rõ ràng.
- Dùng câu SQL set-based tiếp theo từ ứng dụng hoặc package.

Không nên giả định statement trigger có thể đọc :OLD/:NEW của từng hàng.


## 10. Mutating table và lỗi ORA-04091

Một lỗi thường gặp với row-level trigger là **mutating table**. Trong khi Oracle đang thay đổi một bảng, row-level trigger trên chính bảng đó không được truy vấn hoặc sửa trực tiếp bảng đang biến đổi trong nhiều ngữ cảnh DML thông thường. Nếu làm vậy, Oracle có thể phát sinh ORA-04091: table is mutating, trigger/function may not see it.

Ví dụ dễ gây lỗi:

~~~sql
CREATE OR REPLACE TRIGGER employees_check_department
AFTER UPDATE OF department_id ON employees
FOR EACH ROW
DECLARE
    l_count NUMBER;
BEGIN
    SELECT COUNT(*)
    INTO l_count
    FROM employees
    WHERE department_id = :NEW.department_id;
END;
/
~~~

Trigger đang chạy cho một hàng của EMPLOYEES nhưng lại truy vấn toàn bảng EMPLOYEES trong lúc câu UPDATE vẫn đang xử lý các hàng. Oracle không cho phép truy vấn bảng đang mutating theo cách này vì kết quả có thể không nhất quán giữa các hàng đã và chưa được xử lý.

### 10.1. Hướng xử lý

- Chuyển truy vấn tổng hợp sang AFTER STATEMENT, khi câu lệnh đã xử lý xong các hàng.
- Dùng compound trigger để thu thập khóa cần thiết trong EACH ROW rồi truy vấn bảng ở AFTER STATEMENT.
- Chuyển logic sang procedure được gọi rõ ràng sau DML.
- Nếu quy tắc là invariant đơn giản, cân nhắc constraint hoặc mô hình dữ liệu khác.

Không dùng autonomous transaction để né mutating table một cách tùy tiện. Cách đó thay đổi transaction semantics, có thể đọc dữ liệu không nhất quán và tạo lỗi logic mới.

## 11. Compound trigger: chia sẻ trạng thái giữa các timing point

Compound DML trigger cho phép khai báo nhiều timing section trong cùng một trigger body:

- BEFORE STATEMENT
- BEFORE EACH ROW
- AFTER EACH ROW
- AFTER STATEMENT

Các biến khai báo ở phần khai báo chung được chia sẻ giữa các section trong một lần thực thi câu lệnh. Đây là cách hữu ích để gom thông tin từ từng hàng rồi xử lý một lần sau khi statement hoàn tất.

### 11.1. Ví dụ thu thập department ID

Giả sử có bảng tổng hợp số nhân viên theo phòng ban:

~~~sql
CREATE TABLE department_headcount_summary (
    department_id NUMBER PRIMARY KEY,
    employee_count NUMBER NOT NULL,
    refreshed_at TIMESTAMP
);
~~~

Compound trigger thu thập department ID cũ/mới của các hàng thay đổi, sau đó tính lại số nhân viên trong AFTER STATEMENT:

~~~sql
CREATE OR REPLACE TRIGGER employees_headcount_ct
FOR INSERT OR UPDATE OR DELETE ON employees
COMPOUND TRIGGER

    TYPE t_dept_ids IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    g_dept_ids t_dept_ids;
    g_count    PLS_INTEGER := 0;

    AFTER EACH ROW IS
    BEGIN
        IF INSERTING OR UPDATING THEN
            IF :NEW.department_id IS NOT NULL THEN
                g_count := g_count + 1;
                g_dept_ids(g_count) := :NEW.department_id;
            END IF;
        END IF;

        IF DELETING OR UPDATING THEN
            IF :OLD.department_id IS NOT NULL THEN
                g_count := g_count + 1;
                g_dept_ids(g_count) := :OLD.department_id;
            END IF;
        END IF;
    END AFTER EACH ROW;

    AFTER STATEMENT IS
        l_employee_count NUMBER;
    BEGIN
        FOR i IN 1 .. g_count LOOP
            SELECT COUNT(*)
            INTO l_employee_count
            FROM employees
            WHERE department_id = g_dept_ids(i);

            MERGE INTO department_headcount_summary d
            USING (
                SELECT g_dept_ids(i) AS department_id,
                       l_employee_count AS employee_count
                FROM dual
            ) s
            ON (d.department_id = s.department_id)
            WHEN MATCHED THEN
                UPDATE SET
                    d.employee_count = s.employee_count,
                    d.refreshed_at = SYSTIMESTAMP
            WHEN NOT MATCHED THEN
                INSERT (department_id, employee_count, refreshed_at)
                VALUES (s.department_id, s.employee_count, SYSTIMESTAMP);
        END LOOP;
    END AFTER STATEMENT;

END employees_headcount_ct;
/
~~~

Ví dụ trên minh họa cách chuyển thao tác đọc EMPLOYEES sang AFTER STATEMENT để tránh truy vấn bảng đang mutating từ AFTER EACH ROW. Nó có thể tính lại cùng một department nhiều lần nếu nhiều hàng cùng thuộc phòng ban đó; trong triển khai thực tế nên loại trùng department ID hoặc gom thành collection/set phù hợp để tránh công việc lặp.

Bảng summary cũng cần được khởi tạo đồng bộ với dữ liệu hiện có và có chiến lược xử lý concurrency. Nếu nhiều transaction cùng cập nhật một department, cần đánh giá locking và tính đúng đắn của việc duy trì summary.

### 11.2. Compound trigger không phải bốn trigger độc lập

Các timing section thuộc cùng một trigger và chia sẻ trạng thái chung trong lần thực thi statement. Nó giúp kiểm soát lifecycle tốt hơn khi một thuật toán cần thông tin ở nhiều timing point.

Compound trigger vẫn chịu các quy tắc trigger và transaction của Oracle. Không dùng nó như một cách bỏ qua constraint hoặc biến mọi logic nghiệp vụ thành trigger.

## 12. Thứ tự giữa nhiều trigger

Một bảng có thể có nhiều trigger cùng sự kiện và timing point. Không nên dựa vào thứ tự thực thi mặc định giữa các trigger cùng loại nếu thứ tự đó không được khai báo.

Nếu trigger B phụ thuộc vào kết quả trigger A, thiết kế này dễ tạo coupling. Các hướng tốt hơn:
- Gộp logic phụ thuộc vào cùng trigger/package.
- Tạo một procedure chung để các trigger gọi theo thứ tự rõ.
- Dùng mệnh đề FOLLOWS trong những trường hợp Oracle hỗ trợ và đã kiểm tra phiên bản.
- Tránh trigger chain sâu hoặc trigger kích hoạt DML lẫn nhau.

Thứ tự timing point tổng thể vẫn có ý nghĩa: BEFORE STATEMENT trước xử lý hàng, BEFORE EACH ROW trước thao tác hàng, AFTER EACH ROW sau thao tác hàng và AFTER STATEMENT sau tất cả hàng. Nhưng thứ tự giữa nhiều trigger trong cùng timing point cần được quản lý riêng.

## 13. Trigger và MERGE

MERGE có thể thực hiện nhánh UPDATE và INSERT tùy trạng thái hàng đích. Khi MERGE kích hoạt trigger, cần kiểm thử cả các nhánh DML thực sự được sử dụng:
- Hàng khớp điều kiện và được UPDATE.
- Hàng không khớp và được INSERT.
- Nhánh DELETE nếu cú pháp MERGE có điều kiện DELETE phù hợp.

Trigger gắn với các sự kiện INSERT/UPDATE/DELETE tương ứng có thể được gọi theo thao tác xảy ra. Với statement-level trigger và nhiều nhánh trong MERGE, hãy kiểm tra hành vi theo tài liệu release đang dùng và thử nghiệm thực tế; không suy luận từ một câu INSERT hoặc UPDATE đơn lẻ.

Không nên dựa vào trigger để thay thế logic rõ ràng của MERGE. Nếu cần biết chính xác số lượng hàng từng nhánh hoặc tạo event theo nghiệp vụ, cân nhắc API/package điều phối hoặc cơ chế ghi nhận rõ ràng.

## 14. Trigger trên view và INSTEAD OF trigger

BEFORE/AFTER DML trigger thông thường gắn trên bảng. Với view không thể cập nhật trực tiếp theo cách Oracle hỗ trợ, có thể dùng INSTEAD OF trigger để định nghĩa hành động thay thế khi ứng dụng DML lên view.

~~~sql
CREATE OR REPLACE TRIGGER order_view_insert
INSTEAD OF INSERT ON order_entry_view
FOR EACH ROW
BEGIN
    INSERT INTO orders (
        order_id,
        customer_id,
        status
    ) VALUES (
        :NEW.order_id,
        :NEW.customer_id,
        'NEW'
    );
END;
/
~~~

INSTEAD OF trigger là loại riêng, thường là row-level và chạy thay cho thao tác DML trực tiếp trên view. Không nhầm INSTEAD OF với BEFORE hoặc AFTER trên bảng.

## 15. Trigger, constraint và logic ứng dụng

Trigger là một công cụ mạnh nhưng không phải lựa chọn đầu tiên cho mọi quy tắc.

| Yêu cầu | Cơ chế thường nên cân nhắc |
|---|---|
| Cột bắt buộc có giá trị | NOT NULL constraint |
| Giá trị phải nằm trong miền hợp lệ | CHECK constraint |
| Không trùng khóa | UNIQUE/PRIMARY KEY |
| Quan hệ cha-con hợp lệ | FOREIGN KEY |
| Chuẩn hóa input đơn giản trước khi ghi | Application hoặc BEFORE row trigger; cân nhắc datatype/default |
| Audit từng hàng thay đổi | AFTER row trigger hoặc Oracle auditing phù hợp |
| Ghi nhận một lần cho mỗi câu DML | AFTER statement trigger |
| Quy trình nhiều bước được gọi có chủ đích | Procedure/package |
| Gửi email, publish message | Application worker/outbox |
| Quy tắc chỉ áp dụng cho một giao diện | Application/service layer |

Constraint khai báo dễ nhìn thấy trong schema, được optimizer hiểu và được database thực thi nhất quán. Trigger phù hợp cho các phản ứng mà constraint không diễn đạt được, nhưng làm tăng độ phức tạp của DML.


## 16. Transaction và COMMIT trong trigger

Trigger thông thường chạy trong transaction đã kích hoạt nó. Vì vậy:

- Trigger không được COMMIT hoặc ROLLBACK transaction chính.
- DML do trigger thực hiện tham gia cùng transaction.
- Nếu trigger phát sinh exception không được xử lý, câu DML kích hoạt có thể thất bại và các thay đổi của statement được rollback theo cơ chế Oracle.
- Caller vẫn quyết định COMMIT/ROLLBACK transaction sau khi statement hoàn tất.

Ví dụ:

~~~sql
CREATE OR REPLACE TRIGGER orders_after_insert
AFTER INSERT ON orders
FOR EACH ROW
BEGIN
    INSERT INTO order_audit (
        order_id,
        event_name,
        event_time
    ) VALUES (
        :NEW.order_id,
        'CREATED',
        SYSTIMESTAMP
    );
END;
/
~~~

Nếu caller rollback transaction tạo order, bản ghi audit cũng rollback.

### 16.1. Autonomous transaction trong trigger

Có thể khai báo autonomous transaction trong một trigger theo các quy tắc Oracle cho phép, thường dùng trong một số tình huống logging độc lập. Nhưng autonomous transaction có transaction boundary riêng:
- Có thể commit log dù DML chính rollback.
- Không nhìn thấy các thay đổi chưa commit của transaction chính như một phần dữ liệu đã commit.
- Có thể gặp lock hoặc deadlock nếu truy cập dữ liệu đang bị transaction chính giữ.
- Không nên dùng để làm trigger luôn commit các thay đổi nghiệp vụ.

Chỉ dùng khi yêu cầu audit/log độc lập đã được xác định rõ và được kiểm thử. Không dùng autonomous transaction để né mutating table hoặc ép DML chính thành công.

## 17. Exception trong trigger

Nếu trigger phát sinh lỗi, Oracle thường truyền lỗi về statement đã kích hoạt trigger. Ví dụ:

~~~sql
CREATE OR REPLACE TRIGGER orders_validate_amount
BEFORE INSERT OR UPDATE OF total_amount ON orders
FOR EACH ROW
BEGIN
    IF :NEW.total_amount < 0 THEN
        RAISE_APPLICATION_ERROR(
            -20110,
            'Order amount cannot be negative'
        );
    END IF;
END;
/
~~~

Ứng dụng nhận lỗi Oracle và có thể ánh xạ thành lỗi nghiệp vụ. Nếu trigger nuốt exception bằng WHEN OTHERS THEN NULL, caller có thể không biết một phần xử lý đã thất bại.

### 17.1. Không nuốt lỗi tùy tiện

Không nên:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        NULL;
~~~

Nếu cần thêm ngữ cảnh, có thể ghi nhận lỗi theo cơ chế đã thiết kế rồi RAISE lại. Cần cẩn trọng với logging trong autonomous transaction vì nó có thể tồn tại dù transaction chính rollback.

### 17.2. Trigger làm DML thất bại

Nếu trigger insert vào bảng audit nhưng bảng audit hết quota, thiếu privilege hoặc vi phạm constraint, câu DML chính có thể thất bại. Đây là lý do cần kiểm thử trigger cùng schema, quyền, tablespace và workload thật.

## 18. Quản trị trigger: xem, enable, disable và compile

Các dictionary view thường dùng:

- USER_TRIGGERS: trigger thuộc schema hiện tại.
- ALL_TRIGGERS: trigger mà user có quyền xem.
- DBA_TRIGGERS: toàn bộ trigger trong database, cần quyền phù hợp.
- USER_OBJECTS: trạng thái object.
- USER_ERRORS: lỗi compile của trigger và các stored object.

### 18.1. Liệt kê trigger

~~~sql
SELECT trigger_name,
       table_name,
       triggering_event,
       trigger_type,
       status,
       when_clause
FROM user_triggers
ORDER BY table_name, trigger_name;
~~~

### 18.2. Xem lỗi compile

~~~sql
SELECT name,
       type,
       line,
       position,
       text
FROM user_errors
WHERE type = 'TRIGGER'
ORDER BY name, sequence;
~~~

### 18.3. Enable và disable

~~~sql
ALTER TRIGGER orders_before_insert DISABLE;
ALTER TRIGGER orders_before_insert ENABLE;
~~~

Có thể enable/disable toàn bộ trigger trên bảng bằng ALTER TABLE theo cú pháp Oracle:

~~~sql
ALTER TABLE orders DISABLE ALL TRIGGERS;
ALTER TABLE orders ENABLE ALL TRIGGERS;
~~~

Disable trigger có thể khiến logic chuẩn hóa, audit hoặc invariant dựa vào trigger không chạy. Chỉ dùng trong quy trình bảo trì đã đánh giá tác động và có kế hoạch bật lại, kiểm tra dữ liệu bị ảnh hưởng.

### 18.4. Recompile

~~~sql
ALTER TRIGGER orders_before_insert COMPILE;
~~~

Sau compile, kiểm tra STATUS trong USER_TRIGGERS hoặc USER_OBJECTS và xem USER_ERRORS nếu object vẫn INVALID. Không coi lệnh COMPILE thành công là bằng chứng trigger chạy đúng nghiệp vụ.

## 19. Hiệu năng và rủi ro vận hành

Trigger chạy trong đường thực thi DML nên mọi chi phí của trigger cộng vào thời gian thao tác dữ liệu.

Các nguyên nhân thường làm trigger chậm:
- Row-level trigger thực hiện nhiều SELECT/DML cho từng hàng.
- Gọi function/procedure tốn kém cho mỗi row.
- Truy vấn lại bảng nguồn hoặc bảng liên quan với index không phù hợp.
- Ghi audit quá nhiều cột hoặc dữ liệu lớn.
- Trigger chain nhiều tầng.
- Lock contention giữa bảng chính và bảng phụ.
- Gọi dịch vụ ngoài hoặc thực hiện xử lý kéo dài.
- Exception/rollback thường xuyên do logic trigger.

### 19.1. Trigger row-level và chi phí theo số hàng

Nếu một câu UPDATE tác động 100.000 hàng, row-level trigger chạy 100.000 lần. Một câu SELECT/DML trong mỗi lần có thể tạo khối lượng công việc lớn.

Nếu chỉ cần một thao tác tổng hợp sau statement, dùng statement-level trigger hoặc compound trigger để gom dữ liệu và xử lý một lần.

### 19.2. Không gọi dịch vụ ngoài trực tiếp

Không nên để trigger gọi email, HTTP endpoint hoặc message broker trong đường DML chính. Dịch vụ ngoài có thể chậm hoặc lỗi, giữ transaction và lock lâu, đồng thời không rollback cùng Oracle transaction.

Có thể ghi event vào bảng outbox trong cùng transaction rồi để worker ứng dụng gửi sau COMMIT. Worker cần cơ chế retry và idempotency.

### 19.3. Không tạo trigger để thay thế mọi API

Nếu ứng dụng cần một workflow rõ ràng, procedure/package được gọi tường minh thường dễ đọc và kiểm thử hơn. Trigger nên phản ứng với sự kiện dữ liệu có phạm vi hẹp, có mục đích rõ và không tạo bất ngờ cho caller.

## 20. Checklist thiết kế DML trigger

Trước khi tạo trigger, hãy xác định:

1. Sự kiện là INSERT, UPDATE, DELETE hay kết hợp?
2. Trigger cần chạy BEFORE hay AFTER?
3. Cần chạy một lần cho câu lệnh hay từng hàng?
4. Có cần :OLD/:NEW không?
5. Có cần gán :NEW? Nếu có, phải là BEFORE row trigger.
6. UPDATE OF đang kiểm tra cột trong SET list hay giá trị thực sự thay đổi?
7. Có cần WHEN condition không? WHEN chỉ dành cho row-level.
8. Trigger có truy vấn/sửa chính bảng đang mutating không?
9. Có thể dùng constraint hoặc SQL set-based thay thế không?
10. Trigger có ghi audit trong cùng transaction hay cần logging độc lập?
11. Trigger có nuốt exception hoặc làm DML thất bại ngoài dự kiến không?
12. Có nhiều trigger cùng timing point phụ thuộc thứ tự không?
13. Có xử lý DML nhiều hàng, câu lệnh không tác động hàng nào và MERGE không?
14. Có gọi dịch vụ ngoài hoặc giữ transaction quá lâu không?
15. Có quyền, dependency, deployment, enable/disable và rollback plan không?

## 21. Bài thực hành có kiểm soát

Các bài thực hành dùng bảng EMPLOYEES nếu schema mẫu có sẵn. Nếu không, tạo bảng lab riêng trong schema DEV/TEST được cấp quyền. Không tạo trigger trên bảng nghiệp vụ production khi chưa có kế hoạch được phê duyệt.

### 21.1. Tạo bảng lab

~~~sql
CREATE TABLE lab_employees (
    employee_id NUMBER PRIMARY KEY,
    department_id NUMBER,
    employee_name VARCHAR2(100),
    salary NUMBER(12,2),
    created_at TIMESTAMP
);

INSERT ALL
    INTO lab_employees VALUES (1, 10, 'An', 1000, NULL)
    INTO lab_employees VALUES (2, 10, 'Binh', 1500, NULL)
    INTO lab_employees VALUES (3, 20, 'Chi', 2000, NULL)
SELECT 1 FROM dual;

COMMIT;
~~~

### Bài 1 — BEFORE EACH ROW

Tạo trigger BEFORE INSERT trên LAB_EMPLOYEES:
- Nếu created_at là NULL, gán timestamp hiện tại.
- Chuẩn hóa employee_name bằng TRIM.
- Không tự COMMIT.

Insert một hàng thiếu created_at và kiểm tra giá trị được gán.

### Bài 2 — AFTER EACH ROW

Tạo bảng audit riêng và trigger AFTER UPDATE OF salary:
- Ghi employee_id.
- Ghi salary cũ và mới.
- Ghi session user và thời điểm.
- Thử UPDATE một hàng và UPDATE nhiều hàng.

Đếm số audit row để thấy row-level trigger chạy theo số hàng.

### Bài 3 — BEFORE STATEMENT và AFTER STATEMENT

Tạo bảng statement log. Tạo hai trigger:
- BEFORE UPDATE statement ghi phase START.
- AFTER UPDATE statement ghi phase END.

Chạy UPDATE tác động nhiều hàng. Xác nhận chỉ có hai log row cho hai statement trigger.

### Bài 4 — Câu lệnh không tác động hàng nào

Chạy UPDATE với điều kiện không khớp hàng. Xác nhận statement-level trigger vẫn chạy, còn row-level trigger không chạy.

### Bài 5 — UPDATE OF và giá trị thực sự thay đổi

Tạo trigger UPDATE OF salary. Chạy:
- SET salary = salary.
- SET salary = salary + 100.

Quan sát trigger được kích hoạt trong cả hai trường hợp nhưng điều kiện so sánh :OLD/:NEW chỉ nhận diện thay đổi thực tế.

### Bài 6 — Mutating table

Tạo một row trigger truy vấn lại LAB_EMPLOYEES trong lúc update bảng đó. Quan sát lỗi ORA-04091 trong môi trường lab. Sau đó chuyển phần truy vấn sang AFTER STATEMENT hoặc compound trigger.

### Bài 7 — Compound trigger

Tạo compound trigger thu thập department ID cũ/mới trong AFTER EACH ROW, sau đó đếm nhân viên theo department trong AFTER STATEMENT. Đối chiếu kết quả với truy vấn GROUP BY trực tiếp.

### Bài 8 — Transaction rollback

Thực hiện UPDATE làm trigger ghi audit, sau đó ROLLBACK. Kiểm tra cả dữ liệu chính và audit row. Giải thích vì sao trigger thông thường dùng cùng transaction với câu DML.

### Bài 9 — Exception

Tạo trigger kiểm tra salary không âm bằng RAISE_APPLICATION_ERROR. Thử insert/update salary âm và xác nhận câu DML bị từ chối. So sánh với CHECK constraint.

### Bài 10 — Quản trị trigger

Liệt kê USER_TRIGGERS, disable một trigger lab, thực hiện DML để quan sát hành vi, rồi enable lại. Kiểm tra STATUS và USER_ERRORS.

### Thu dọn dữ liệu lab

Chỉ sau khi xác nhận đúng object do mình tạo trong DEV/TEST và không có người khác sử dụng, disable/drop trigger lab trước rồi xóa bảng liên quan. Ví dụ:

~~~sql
DROP TRIGGER lab_employees_before_insert;
DROP TRIGGER lab_employees_salary_audit;
DROP TABLE lab_employee_audit PURGE;
DROP TABLE lab_employees PURGE;
~~~

Điều chỉnh tên theo object thực tế đã tạo. DDL trong Oracle có implicit commit; không chạy lệnh thu dọn trên object ngoài phạm vi lab.


## 22. Câu hỏi ôn tập

**Câu 1.** BEFORE và AFTER mô tả điều gì?

**Đáp án:** Thời điểm trigger chạy tương đối với thao tác DML ở timing point tương ứng.

**Câu 2.** Row-level trigger khác statement-level trigger thế nào?

**Đáp án:** Row-level có FOR EACH ROW và chạy một lần cho mỗi hàng được tác động; statement-level chạy một lần cho câu DML.

**Câu 3.** Một UPDATE tác động 100 hàng thì AFTER EACH ROW chạy bao nhiêu lần?

**Đáp án:** 100 lần.

**Câu 4.** UPDATE không tác động hàng nào thì statement trigger có chạy không?

**Đáp án:** Có. Statement-level trigger chạy cho câu lệnh; row-level trigger không chạy vì không có hàng được xử lý.

**Câu 5.** :OLD và :NEW dùng ở đâu?

**Đáp án:** Trong row-level trigger. Statement-level trigger không có pseudorecord của từng hàng.

**Câu 6.** BEFORE EACH ROW có thể làm gì với :NEW?

**Đáp án:** Có thể gán giá trị cho trường :NEW trước khi hàng được ghi. Không thể gán :OLD.

**Câu 7.** AFTER EACH ROW có thể sửa :NEW không?

**Đáp án:** Không. Nếu cần chuẩn hóa giá trị được lưu, dùng BEFORE EACH ROW hoặc xử lý trong câu DML.

**Câu 8.** UPDATE OF salary kiểm tra điều gì?

**Đáp án:** Cột salary có xuất hiện trong SET list; không khẳng định giá trị salary thực sự đổi.

**Câu 9.** WHEN clause dùng cho trigger nào?

**Đáp án:** Row-level trigger. Trong WHEN clause tham chiếu NEW/OLD không có dấu hai chấm.

**Câu 10.** ORA-04091 mutating table là gì?

**Đáp án:** Lỗi phát sinh khi row-level trigger truy vấn hoặc sửa bảng đang bị DML làm biến đổi trong ngữ cảnh không được Oracle cho phép.

**Câu 11.** Compound trigger giúp gì?

**Đáp án:** Cho phép chia sẻ trạng thái giữa các timing point, ví dụ thu thập dữ liệu ở EACH ROW rồi xử lý bảng sau statement để tránh mutating table.

**Câu 12.** AFTER trigger có chạy sau COMMIT không?

**Đáp án:** Không. AFTER là sau thao tác hàng hoặc statement nhưng vẫn trong transaction; caller commit/rollback sau đó.

**Câu 13.** Trigger thông thường có thể COMMIT không?

**Đáp án:** Không thể commit/rollback transaction chính trong trigger thông thường. Autonomous transaction là cơ chế riêng và cần cân nhắc semantics.

**Câu 14.** Vì sao không nên gửi email trực tiếp trong trigger?

**Đáp án:** Email là side effect ngoài transaction Oracle; nó có thể đã gửi dù transaction rollback hoặc làm DML chậm/thất bại. Dùng outbox và worker sau commit.

**Câu 15.** Khi nào nên dùng constraint thay trigger?

**Đáp án:** Khi quy tắc có thể diễn đạt bằng NOT NULL, CHECK, UNIQUE, PRIMARY KEY hoặc FOREIGN KEY. Constraint minh bạch và được database bảo đảm trực tiếp.

**Câu 16.** Có thể giả định thứ tự giữa hai trigger cùng timing point không?

**Đáp án:** Không nên. Nếu cần thứ tự, gộp logic hoặc dùng FOLLOWS trong trường hợp được hỗ trợ và kiểm tra theo phiên bản.

## Kết luận

BEFORE/AFTER xác định thời điểm trigger chạy; row-level/statement-level xác định phạm vi một hàng hay toàn câu DML. BEFORE EACH ROW phù hợp để kiểm tra và chuẩn hóa :NEW; AFTER EACH ROW phù hợp để ghi nhận thay đổi bằng :OLD/:NEW; BEFORE STATEMENT và AFTER STATEMENT chạy một lần cho mỗi câu lệnh và không có pseudorecord của từng hàng.

Với DML nhiều hàng, row trigger chạy theo từng hàng còn statement trigger chạy một lần, kể cả khi câu lệnh không tác động hàng nào. Cần phân biệt UPDATE OF với thay đổi giá trị thực tế, dùng WHEN đúng phạm vi, tránh truy vấn bảng đang mutating từ row trigger và cân nhắc compound trigger khi cần thu thập dữ liệu từng hàng rồi xử lý sau statement. Trigger thông thường nằm trong transaction kích hoạt nó, không tự commit và có thể làm DML thất bại nếu phát sinh lỗi. Hãy ưu tiên constraint cho invariant đơn giản, giữ trigger nhỏ và dễ quan sát, không gọi dịch vụ ngoài trực tiếp, đồng thời kiểm thử với DML nhiều hàng, rollback, exception và concurrency.

## Tài liệu Oracle tham khảo

- [Oracle Database 19c PL/SQL Language Reference — DML Triggers](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/dml-triggers.html): timing point, row/statement trigger, :OLD/:NEW, WHEN và compound trigger.
- [Oracle Database 19c SQL Language Reference — CREATE TRIGGER](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TRIGGER.html): cú pháp tạo trigger.
- [Oracle Database 19c Error Messages — ORA-04091](https://docs.oracle.com/en/error-help/db/ora-04091/): nguyên nhân và hướng xử lý lỗi mutating table.
- [Oracle Database 19c Reference — USER_TRIGGERS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_TRIGGERS.html): metadata trigger trong schema hiện tại.

