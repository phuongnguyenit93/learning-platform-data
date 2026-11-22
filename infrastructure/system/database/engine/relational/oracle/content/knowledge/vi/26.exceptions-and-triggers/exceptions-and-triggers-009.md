# Thứ tự thực thi, trigger lồng nhau và tác động ngoài dự kiến

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** Lỗi và trigger  
> **Mục tiêu:** Hiểu thứ tự thực thi DML trigger trong Oracle; phân biệt statement-level và row-level trigger; kiểm soát thứ tự giữa nhiều trigger cùng timing point; nhận diện trigger lồng nhau, đệ quy và mutating-table error; sử dụng compound trigger khi cần xử lý theo từng hàng rồi tổng hợp ở cấp statement; hiểu transaction, exception và side effect; chẩn đoán hành vi trigger bằng data dictionary và xây dựng quy trình kiểm thử an toàn.

## 1. Vì sao trigger có thể tạo ra hành vi ngoài dự kiến?

Trigger là PL/SQL được Oracle tự động gọi khi một sự kiện xảy ra trên bảng, view, schema hoặc database. Với DML trigger, sự kiện thường là INSERT, UPDATE hoặc DELETE.

Một câu lệnh tưởng như đơn giản:

~~~sql
UPDATE orders
SET status = 'PAID'
WHERE order_id = 100;
~~~

có thể kích hoạt nhiều đoạn code:

1. BEFORE STATEMENT trigger trên ORDERS.
2. BEFORE EACH ROW trigger cho hàng được cập nhật.
3. DML thay đổi hàng.
4. AFTER EACH ROW trigger cho hàng đó.
5. AFTER STATEMENT trigger trên ORDERS.
6. Trigger trên bảng khác nếu trigger trước đó thực hiện INSERT/UPDATE/DELETE.
7. Các trigger tiếp theo trong chuỗi DML phát sinh.

Vì vậy, tác động thực tế của một DML statement có thể rộng hơn phần SQL nhìn thấy. Một trigger ghi audit có thể kích hoạt trigger trên bảng audit; trigger đồng bộ trạng thái có thể sửa thêm bảng khác; trigger trên bảng đích lại cập nhật bảng nguồn.

Nếu không hiểu thứ tự và ranh giới transaction, hệ thống có thể gặp:

- Dữ liệu bị cập nhật nhiều lần hoặc theo thứ tự không mong muốn.
- Trigger gọi lẫn nhau tạo chuỗi DML khó theo dõi.
- ORA-04091 do truy cập bảng đang mutating.
- ORA-04088 khi lỗi xảy ra trong lúc thực thi trigger.
- Một câu lệnh thất bại vì trigger phụ thất bại.
- Audit hoặc thông báo bên ngoài không phản ánh đúng kết quả commit.
- Khó dự đoán hiệu năng vì một DML kích hoạt thêm nhiều câu SQL.

Bài học quan trọng là phải xem trigger như một phần của execution path và transaction, không phải một đoạn code độc lập chạy “sau cùng”.

## 2. Các timing point của DML trigger

Oracle hỗ trợ các timing point chính cho DML trigger trên bảng:

- BEFORE STATEMENT
- BEFORE EACH ROW
- AFTER EACH ROW
- AFTER STATEMENT

Một DML statement có thể kích hoạt trigger ở nhiều timing point. Trigger statement-level chạy một lần cho statement; trigger row-level chạy cho từng hàng bị tác động.

### 2.1. Thứ tự cơ bản của một câu UPDATE

Giả sử một câu UPDATE tác động đến ba hàng và có đủ bốn loại trigger:

~~~text
UPDATE ... (một statement)
        |
        v
BEFORE STATEMENT trigger
        |
        v
Với từng hàng được tác động:
    BEFORE EACH ROW trigger
        |
        v
    Oracle thực hiện thay đổi hàng
        |
        v
    AFTER EACH ROW trigger
        |
        v
Lặp lại cho hàng tiếp theo
        |
        v
AFTER STATEMENT trigger
        |
        v
Statement hoàn tất nếu không có lỗi
~~~

Nếu statement tác động đến ba hàng:

- BEFORE STATEMENT chạy một lần.
- BEFORE EACH ROW chạy ba lần.
- AFTER EACH ROW chạy ba lần.
- AFTER STATEMENT chạy một lần.

Thứ tự xử lý từng hàng không được bảo đảm chỉ vì bảng có primary key hoặc query có vẻ trả về theo một thứ tự quen thuộc. Không xây dựng logic nghiệp vụ dựa trên giả định trigger row-level luôn chạy theo ROWID, index order hoặc thứ tự INSERT trước đây.

### 2.2. Statement-level trigger chạy cả khi không có hàng phù hợp

Một câu UPDATE có thể không tìm thấy hàng:

~~~sql
UPDATE orders
SET status = 'PAID'
WHERE order_id = -1;
~~~

Nếu bảng có statement-level trigger phù hợp, trigger đó vẫn được kích hoạt vì statement đã được thực thi. Row-level trigger không chạy vì không có hàng nào bị tác động.

Điểm này quan trọng với audit số lần statement, ghi nhận batch, hoặc logic kiểm tra đầu-cuối. Không suy luận rằng statement-level trigger chỉ chạy khi SQL%ROWCOUNT lớn hơn 0.

### 2.3. Row-level trigger chỉ chạy khi có hàng được tác động

Trigger có FOR EACH ROW được gọi cho mỗi hàng mà DML thực sự tác động:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_after_row
AFTER UPDATE ON orders
FOR EACH ROW
BEGIN
    INSERT INTO order_audit (
        order_id,
        old_status,
        new_status,
        changed_at
    )
    VALUES (
        :NEW.order_id,
        :OLD.status,
        :NEW.status,
        SYSTIMESTAMP
    );
END;
/
~~~

Nếu UPDATE sửa 100 hàng, phần thân trigger có thể chạy 100 lần. Điều này tạo thêm 100 lần INSERT audit, cùng chi phí index, constraint và các trigger trên ORDER_AUDIT nếu có.

### 2.4. BEFORE và AFTER có mục đích khác nhau

| Timing point | Mục đích thường gặp |
|---|---|
| BEFORE STATEMENT | Kiểm tra/khởi tạo trạng thái cho toàn statement |
| BEFORE EACH ROW | Chuẩn hóa hoặc gán :NEW; kiểm tra từng hàng trước khi ghi |
| AFTER EACH ROW | Ghi nhận thay đổi của hàng; xử lý cần biết :OLD/:NEW sau DML row operation |
| AFTER STATEMENT | Xử lý tổng hợp sau khi các hàng của statement đã được xử lý |

Với BEFORE EACH ROW trigger trên bảng, có thể gán giá trị cho :NEW khi INSERT hoặc UPDATE. Ví dụ tự gán thời điểm tạo:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_bir
BEFORE INSERT ON orders
FOR EACH ROW
BEGIN
    IF :NEW.created_at IS NULL THEN
        :NEW.created_at := SYSTIMESTAMP;
    END IF;
END;
/
~~~

Không gán :NEW trong AFTER EACH ROW trigger. Nếu cần thay đổi giá trị trước khi lưu, dùng BEFORE EACH ROW hoặc thiết kế DML ở lớp ứng dụng.

## 3. :OLD, :NEW và các điều kiện nhận diện thao tác

Trong row-level DML trigger, Oracle cung cấp pseudorecord :OLD và :NEW:

| Thao tác | :OLD | :NEW |
|---|---|---|
| INSERT | Không có giá trị hàng cũ (các field là NULL) | Hàng sắp được chèn |
| UPDATE | Giá trị trước thay đổi | Giá trị mới |
| DELETE | Hàng bị xóa | Không có giá trị hàng mới (các field là NULL) |

Ví dụ:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_audit
AFTER INSERT OR UPDATE OR DELETE ON orders
FOR EACH ROW
BEGIN
    IF INSERTING THEN
        INSERT INTO order_audit(order_id, action_name, changed_at)
        VALUES (:NEW.order_id, 'INSERT', SYSTIMESTAMP);

    ELSIF UPDATING THEN
        INSERT INTO order_audit(order_id, action_name, changed_at)
        VALUES (:NEW.order_id, 'UPDATE', SYSTIMESTAMP);

    ELSIF DELETING THEN
        INSERT INTO order_audit(order_id, action_name, changed_at)
        VALUES (:OLD.order_id, 'DELETE', SYSTIMESTAMP);
    END IF;
END;
/
~~~

Các điều kiện INSERTING, UPDATING và DELETING giúp trigger nhận biết loại DML đang kích hoạt nó.

### 3.1. UPDATE OF column không có nghĩa giá trị chắc chắn thay đổi

Trigger:

~~~sql
CREATE OR REPLACE TRIGGER trg_salary_update
BEFORE UPDATE OF salary ON employees
FOR EACH ROW
BEGIN
    DBMS_OUTPUT.PUT_LINE('SALARY is in the SET list');
END;
/
~~~

Trigger được xét khi câu UPDATE có cột SALARY trong danh sách SET. Ví dụ:

~~~sql
UPDATE employees
SET salary = salary
WHERE employee_id = 100;
~~~

Cột SALARY vẫn được nêu trong SET dù giá trị trước/sau có thể giống nhau. Vì vậy UPDATE OF SALARY không đồng nghĩa giá trị lương đã thay đổi.

Nếu chỉ muốn xử lý khi giá trị thực sự khác, so sánh :OLD và :NEW. Với cột nullable, phải xử lý NULL tường minh:

~~~sql
IF (:OLD.salary IS NULL AND :NEW.salary IS NOT NULL)
   OR (:OLD.salary IS NOT NULL AND :NEW.salary IS NULL)
   OR (:OLD.salary <> :NEW.salary)
THEN
    -- Giá trị đã thay đổi
    NULL;
END IF;
~~~

Có thể dùng DECODE để so sánh hai giá trị theo quy tắc NULL của DECODE, nhưng hãy chọn cách biểu đạt dễ đọc và phù hợp datatype.

### 3.2. WHEN clause

Row trigger có thể dùng WHEN clause để chỉ chạy trigger body khi điều kiện thỏa:

~~~sql
CREATE OR REPLACE TRIGGER trg_large_order
AFTER INSERT ON orders
FOR EACH ROW
WHEN (NEW.total_amount >= 10000)
BEGIN
    INSERT INTO large_order_alert(order_id, created_at)
    VALUES (:NEW.order_id, SYSTIMESTAMP);
END;
/
~~~

Trong WHEN clause, tham chiếu pseudorecord không dùng dấu hai chấm; trong trigger body dùng :NEW và :OLD.

WHEN clause chỉ áp dụng cho row-level trigger. Điều kiện nên ngắn và rõ; nếu logic phức tạp, đưa vào body hoặc package được gọi từ trigger.

## 4. Nhiều trigger cùng timing point: thứ tự có thể không xác định

Một bảng có thể có nhiều trigger cho cùng sự kiện và timing point. Ví dụ hai BEFORE INSERT FOR EACH ROW trigger cùng thay đổi dữ liệu.

Nếu không khai báo quan hệ thứ tự được Oracle hỗ trợ, không dựa vào thứ tự tạo trigger hoặc tên trigger để suy luận trigger nào chạy trước. Thứ tự giữa các trigger cùng timing point có thể không xác định.

Ví dụ không nên dựa vào việc một trigger tên NORMALIZE luôn chạy trước trigger tên VALIDATE. Tên object và thời điểm CREATE không phải hợp đồng thứ tự thực thi.

### 4.1. Thiết kế để không phụ thuộc thứ tự

Tốt nhất, mỗi trigger nên độc lập ở mức có thể. Nếu nhiều hành động cần phối hợp trên cùng một timing point, cân nhắc:

- Gộp logic vào một trigger duy nhất theo thứ tự rõ ràng.
- Gọi các procedure trong package với thứ tự tường minh.
- Tách trách nhiệm validation, normalization và audit sao cho không ghi đè lẫn nhau.
- Dùng constraint cho quy tắc dữ liệu có thể biểu diễn bằng constraint.

Ví dụ một trigger điều phối:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_bir
BEFORE INSERT ON orders
FOR EACH ROW
BEGIN
    order_rules.normalize_new_order(:NEW);
    order_rules.validate_new_order(:NEW);
    order_rules.set_default_priority(:NEW);
END;
/
~~~

Đây là sơ đồ thiết kế; các procedure được gọi phải có signature tương thích với cách truyền record :NEW hoặc được triển khai bằng các tham số cột riêng. Mục đích là thể hiện trình tự gọi trong một nơi.

### 4.2. FOLLOWS để chỉ định thứ tự

Oracle hỗ trợ mệnh đề FOLLOWS trong các trường hợp DML trigger phù hợp để chỉ định một trigger chạy sau trigger khác tại timing point tương ứng.

Ví dụ hai BEFORE INSERT row trigger:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_normalize
BEFORE INSERT ON orders
FOR EACH ROW
BEGIN
    :NEW.order_code := UPPER(TRIM(:NEW.order_code));
END;
/

CREATE OR REPLACE TRIGGER trg_orders_validate
BEFORE INSERT ON orders
FOR EACH ROW
FOLLOWS trg_orders_normalize
BEGIN
    IF :NEW.order_code IS NULL THEN
        RAISE_APPLICATION_ERROR(-20001, 'ORDER_CODE is required');
    END IF;
END;
/
~~~

FOLLOWS thể hiện TRG_ORDERS_VALIDATE phải theo sau TRG_ORDERS_NORMALIZE trong phạm vi Oracle hỗ trợ.

Các giới hạn cần nhớ:

- FOLLOWS không biến trigger ở các timing point khác nhau thành một chuỗi tùy ý.
- Trigger được tham chiếu phải tồn tại và tương thích với điều kiện ordering.
- Với compound trigger, quan hệ thứ tự gắn với timing section tương ứng; các section không tồn tại có thể làm giới hạn ordering.
- Khả năng và chi tiết cú pháp phụ thuộc Oracle release.

Đối chiếu SQL Language Reference của phiên bản đang chạy trước khi triển khai. Nếu thứ tự là phần thiết yếu của nghiệp vụ, một trigger điều phối thường dễ kiểm soát và bảo trì hơn nhiều trigger phụ thuộc lẫn nhau.

### 4.3. Không dùng thứ tự trigger làm hợp đồng nghiệp vụ ngầm

Ngay cả khi FOLLOWS đang hoạt động, đừng xây một mạng trigger dài trong đó trigger A phụ thuộc B, B phụ thuộc C, C lại sửa dữ liệu A đã kiểm tra. Chuỗi phụ thuộc như vậy khó debug và dễ bị phá vỡ khi thêm trigger mới hoặc thay đổi timing point.

Hãy thể hiện luồng nghiệp vụ bằng procedure/service có lời gọi rõ ràng khi có thể.

## 5. Trigger lồng nhau và trigger đệ quy

Trigger lồng nhau (cascading/nested triggers) xảy ra khi trigger thực hiện DML trên một bảng khác, và DML đó kích hoạt trigger khác.

Ví dụ:

~~~text
UPDATE ORDERS
   |
   v
TRG_ORDERS_AFTER_UPDATE
   |
   +-- INSERT ORDER_AUDIT
             |
             v
       TRG_AUDIT_AFTER_INSERT
             |
             +-- UPDATE CUSTOMER_SUMMARY
                       |
                       v
                 TRG_CUSTOMER_SUMMARY
~~~

Một câu UPDATE trên ORDERS có thể dẫn đến nhiều DML statement và trigger khác. Các thao tác này thường vẫn thuộc cùng transaction của statement gốc.

### 5.1. Trigger lồng nhau khác trigger tự gọi lại

- **Cascading trigger:** trigger trên bảng A sửa bảng B; trigger trên B lại sửa bảng C.
- **Recursive trigger:** trigger trực tiếp hoặc gián tiếp gây ra DML làm trigger đó được kích hoạt lại.

Ví dụ trigger trên CUSTOMERS cập nhật CUSTOMERS lần nữa có thể tạo vòng lặp hoặc gặp mutating-table restriction tùy cách truy cập.

Không nên xem mọi trigger chain là lỗi. Nhưng chuỗi cần có điểm dừng rõ, tránh cập nhật lặp không cần thiết và có thể truy vết.

### 5.2. Ví dụ chuỗi trigger hợp lệ nhưng có chi phí

Trigger ghi audit:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_audit
AFTER UPDATE ON orders
FOR EACH ROW
BEGIN
    INSERT INTO order_audit (
        order_id,
        old_status,
        new_status,
        changed_at
    )
    VALUES (
        :NEW.order_id,
        :OLD.status,
        :NEW.status,
        SYSTIMESTAMP
    );
END;
/
~~~

Nếu ORDER_AUDIT có trigger kiểm tra hoặc ghi thêm audit khác, trigger đó cũng được kích hoạt. Một UPDATE 10.000 hàng có thể tạo 10.000 INSERT vào ORDER_AUDIT và kích hoạt thêm 10.000 row trigger trên bảng audit.

Tính toán chi phí của toàn bộ chain, không chỉ câu SQL ban đầu.

### 5.3. Tránh vòng lặp trigger

Một ví dụ nguy hiểm:

- Trigger A sau UPDATE bảng A cập nhật bảng B.
- Trigger B sau UPDATE bảng B cập nhật bảng A.
- Trigger A được gọi lại, rồi B lại được gọi.

Để tránh vòng lặp:

- Không tạo quan hệ cập nhật hai chiều nếu không thực sự cần.
- Dùng điều kiện thay đổi thực sự trước khi thực hiện DML tiếp theo.
- Thiết kế một chiều cho luồng đồng bộ.
- Đưa quy trình đồng bộ vào procedure/service điều phối thay vì trigger tự kích hoạt lẫn nhau.
- Dùng idempotent operation: chạy lặp không làm dữ liệu sai thêm.
- Không dựa duy nhất vào cờ package toàn cục để che vòng lặp; cờ có thể không được reset khi exception hoặc tạo hành vi khó hiểu.

Oracle giới hạn độ sâu trigger cascade. Thiết kế vượt giới hạn có thể phát sinh lỗi runtime; không dùng giới hạn này như một mục tiêu kiến trúc.

## 6. Mutating table và ORA-04091

Một lỗi thường gặp khi viết row-level trigger là trigger truy vấn hoặc thay đổi chính bảng đang bị câu DML sửa.

Ví dụ bảng EMPLOYEES có trigger sau mỗi hàng UPDATE:

~~~sql
CREATE OR REPLACE TRIGGER trg_employee_check
AFTER UPDATE OF salary ON employees
FOR EACH ROW
DECLARE
    l_avg_salary NUMBER;
BEGIN
    SELECT AVG(salary)
    INTO l_avg_salary
    FROM employees
    WHERE department_id = :NEW.department_id;

    IF :NEW.salary > l_avg_salary * 3 THEN
        RAISE_APPLICATION_ERROR(
            -20010,
            'Salary exceeds department threshold'
        );
    END IF;
END;
/
~~~

Khi UPDATE EMPLOYEES, bảng đang trong trạng thái mutating đối với row-level trigger. Truy vấn lại EMPLOYEES trong trigger có thể gây:

~~~text
ORA-04091: table ... is mutating, trigger/function may not see it
~~~

Oracle ngăn row-level trigger quan sát trạng thái bảng đang thay đổi theo cách có thể không nhất quán.

### 6.1. Vì sao lỗi xuất hiện?

Trong một câu UPDATE nhiều hàng, Oracle xử lý hàng theo các bước row-level. Khi trigger của một hàng truy vấn toàn bảng, một số hàng có thể đã thay đổi, một số chưa; kết quả trung gian không đại diện trạng thái hoàn chỉnh của statement.

Nếu trigger dùng kết quả đó để ra quyết định, hành vi phụ thuộc thứ tự xử lý hàng và có thể không nhất quán. Mutating-table restriction ngăn cách tiếp cận này.

### 6.2. Không giải quyết bằng cách đổi AFTER thành BEFORE

Đổi trigger từ AFTER EACH ROW sang BEFORE EACH ROW không loại bỏ bản chất vấn đề: trigger vẫn là row-level trigger trên bảng đang bị sửa.

Cũng không nên dùng autonomous transaction để né ORA-04091. Autonomous transaction không làm cho trạng thái đang sửa trở thành snapshot nhất quán và còn tạo transaction độc lập với side effect riêng.

## 7. Compound trigger để xử lý dữ liệu ở cấp statement

Compound DML trigger cho phép gom các timing section trong một trigger và chia sẻ trạng thái PL/SQL trong suốt một câu DML.

Các section có thể gồm:

- BEFORE STATEMENT
- BEFORE EACH ROW
- AFTER EACH ROW
- AFTER STATEMENT

Không bắt buộc phải có đủ mọi section. Phần khai báo chung có thể chứa collection hoặc biến được dùng giữa các section.

Một kỹ thuật phổ biến:

1. Trong AFTER EACH ROW, chỉ thu thập khóa hoặc dữ liệu cần kiểm tra vào collection.
2. Khi tất cả hàng đã được xử lý, AFTER STATEMENT chạy.
3. Trong AFTER STATEMENT, truy vấn bảng sau khi row-level processing hoàn tất và kiểm tra dữ liệu tổng hợp.
4. Nếu vi phạm, raise exception để statement gốc thất bại.

Ví dụ minh họa thu thập department ID:

~~~sql
CREATE OR REPLACE TRIGGER trg_employee_salary_check
FOR UPDATE OF salary ON employees
COMPOUND TRIGGER

    TYPE dept_id_list_t IS TABLE OF employees.department_id%TYPE
        INDEX BY PLS_INTEGER;

    g_department_ids dept_id_list_t;
    g_count PLS_INTEGER := 0;

    AFTER EACH ROW IS
    BEGIN
        IF :NEW.department_id IS NOT NULL THEN
            g_count := g_count + 1;
            g_department_ids(g_count) := :NEW.department_id;
        END IF;
    END AFTER EACH ROW;

    AFTER STATEMENT IS
        l_avg_salary NUMBER;
    BEGIN
        FOR i IN 1 .. g_count LOOP
            SELECT AVG(salary)
            INTO l_avg_salary
            FROM employees
            WHERE department_id = g_department_ids(i);

            -- Ví dụ minh họa: kiểm tra quy tắc tổng hợp
            -- sau khi statement đã xử lý các hàng.
            NULL;
        END LOOP;
    END AFTER STATEMENT;

END trg_employee_salary_check;
/
~~~

Trong ví dụ thực tế cần loại trùng department ID trước khi truy vấn để tránh chạy cùng phép kiểm tra nhiều lần. Có thể dùng associative array làm tập hợp hoặc collection phù hợp.

Điểm quan trọng: AFTER STATEMENT chạy sau row-level changes của statement, nên không còn cùng mutating restriction như row trigger khi truy vấn bảng đó.

### 7.1. Compound trigger chia sẻ state trong một statement

Các biến khai báo ở declarative section thuộc về một lần kích hoạt compound trigger. Chúng được dùng giữa các timing sections của statement đó, rồi hết vòng đời khi statement kết thúc.

Không xem biến này là trạng thái bền vững giữa nhiều câu SQL hoặc nhiều session. Mỗi session và mỗi statement có context riêng.

### 7.2. Dùng compound trigger có chọn lọc

Compound trigger phù hợp khi cần phối hợp row-level capture với statement-level processing. Không cần dùng nó cho mọi trigger.

Nếu chỉ cần gán giá trị mặc định trước khi INSERT, một BEFORE EACH ROW trigger đơn giản hơn. Nếu chỉ cần ghi audit từng hàng, AFTER EACH ROW có thể đủ.

## 8. Trigger trên nhiều bảng và thứ tự giữa các statement

Một trigger có thể thực hiện DML trên bảng khác:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_after_insert
AFTER INSERT ON orders
FOR EACH ROW
BEGIN
    UPDATE customer_summary
    SET order_count = order_count + 1
    WHERE customer_id = :NEW.customer_id;
END;
/
~~~

Nếu CUSTOMER_SUMMARY có trigger, trigger đó được kích hoạt bởi UPDATE vừa phát sinh.

### 8.1. Không giả định thứ tự giữa các hàng

Nếu một INSERT ... SELECT chèn hàng cho nhiều customer, trigger row-level được gọi theo thứ tự xử lý nội bộ của Oracle. Không dùng trigger để xây số thứ tự nghiệp vụ dựa trên thứ tự ngầm đó.

Nếu cần thứ tự, tạo số thứ tự bằng sequence hoặc xử lý tập dữ liệu với ORDER BY ở bước riêng có hợp đồng rõ ràng.

### 8.2. Tránh cập nhật counter bằng read-modify-write không an toàn

Một trigger có thể tăng counter:

~~~sql
UPDATE customer_summary
SET order_count = order_count + 1
WHERE customer_id = :NEW.customer_id;
~~~

Phép cộng được thực hiện trong SQL và Oracle khóa hàng phù hợp, an toàn hơn việc SELECT counter vào biến rồi tính ở PL/SQL sau đó UPDATE giá trị tuyệt đối. Tuy vậy, nhiều đơn hàng cùng customer vẫn có thể tranh chấp trên một hàng summary và tạo hotspot.

Cần cân nhắc:

- Tạo summary bằng batch hoặc materialized view nếu phù hợp.
- Dùng cấu trúc dữ liệu có thể chịu write concurrency.
- Đánh giá việc cập nhật một hàng counter cho mỗi order.
- Đo row lock wait và throughput.

## 9. MERGE và trigger

MERGE có thể thực hiện UPDATE cho hàng khớp và INSERT cho hàng không khớp; một số cú pháp còn có DELETE cho hàng được UPDATE thỏa điều kiện.

Ví dụ:

~~~sql
MERGE INTO customers t
USING customer_stage s
ON (t.customer_id = s.customer_id)
WHEN MATCHED THEN
    UPDATE SET t.customer_name = s.customer_name
WHEN NOT MATCHED THEN
    INSERT (customer_id, customer_name)
    VALUES (s.customer_id, s.customer_name);
~~~

Trigger liên quan đến các thao tác thực tế mà MERGE thực hiện có thể được kích hoạt:

- Hàng được cập nhật kích hoạt trigger UPDATE tương ứng.
- Hàng được chèn kích hoạt trigger INSERT tương ứng.
- Nếu có DELETE clause và hàng bị xóa, trigger DELETE tương ứng có thể được kích hoạt.

Đừng viết code giả định MERGE chỉ kích hoạt một loại trigger. Kiểm thử cả nhánh matched và not matched, cũng như DELETE clause nếu dùng.

MERGE vẫn là một statement; statement-level trigger và row-level trigger cần được đánh giá theo các DML operation được thực hiện. Nếu trigger phụ thuộc thứ tự hoặc trạng thái tổng hợp, compound trigger và thiết kế điều phối có thể cần thiết.

## 10. Trigger, constraint và validation

Không phải mọi quy tắc dữ liệu đều nên triển khai bằng trigger.

Dùng constraint khi quy tắc có thể diễn đạt trực tiếp:

- NOT NULL cho cột bắt buộc.
- CHECK cho điều kiện trên một hàng.
- UNIQUE/PRIMARY KEY cho tính duy nhất.
- FOREIGN KEY cho toàn vẹn tham chiếu.

Ví dụ:

~~~sql
ALTER TABLE orders
ADD CONSTRAINT ck_orders_total
CHECK (total_amount >= 0);
~~~

Constraint thường rõ ràng hơn trigger, được optimizer và database hiểu như metadata toàn vẹn, và tránh viết lại logic validation ở nhiều nơi.

Trigger có thể phù hợp khi cần:

- Ghi audit theo từng thay đổi.
- Gán giá trị hoặc chuẩn hóa dữ liệu theo quy tắc đặc thù.
- Phối hợp logic không biểu diễn được bằng constraint.
- Duy trì dữ liệu phụ trợ có chủ đích.
- Chặn thao tác bằng RAISE_APPLICATION_ERROR.

### 10.1. Trigger không phải giải pháp an toàn cho mọi quy tắc liên hàng

Nếu trigger đọc một bảng để xác nhận “không có hàng trùng” rồi cho phép INSERT, nhiều session đồng thời có thể cùng thấy chưa có hàng và cùng chèn. Đây là race condition nếu không có cơ chế khóa/constraint phù hợp.

Dùng UNIQUE constraint/index để bảo vệ uniqueness. Dùng transaction/locking đúng cách cho các quy tắc cần đồng bộ. Trigger chỉ có thể bổ sung logic; nó không tự thay thế concurrency control.

## 11. Transaction và lỗi trong trigger

DML do trigger thực hiện thường thuộc cùng transaction với câu DML đã kích hoạt trigger.

Ví dụ:

1. Session chạy UPDATE ORDERS.
2. Trigger INSERT vào ORDER_AUDIT.
3. Trigger UPDATE CUSTOMER_SUMMARY.
4. Statement hoàn tất.
5. Caller COMMIT.

Nếu caller ROLLBACK transaction, các thay đổi ORDERS, ORDER_AUDIT và CUSTOMER_SUMMARY trong cùng transaction đều bị rollback.

### 11.1. Lỗi trong trigger làm statement gốc thất bại

Ví dụ:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_validate
BEFORE INSERT ON orders
FOR EACH ROW
BEGIN
    IF :NEW.total_amount < 0 THEN
        RAISE_APPLICATION_ERROR(
            -20020,
            'TOTAL_AMOUNT cannot be negative'
        );
    END IF;
END;
/
~~~

Khi INSERT có TOTAL_AMOUNT âm, lỗi được trả về caller và câu INSERT thất bại.

Nếu trigger đã thực hiện một số DML trước khi phát sinh lỗi chưa được xử lý, các thay đổi thuộc statement đó được Oracle rollback theo statement atomicity. Các statement thành công trước đó trong transaction vẫn có thể còn pending; không suy luận rằng lỗi trigger luôn rollback toàn bộ transaction.

### 11.2. ORA-04088 là lỗi bao ngoài

Khi lỗi xảy ra trong lúc chạy trigger, Oracle có thể hiển thị ORA-04088 cùng lỗi gốc:

~~~text
ORA-04088: error during execution of trigger ...
ORA-20020: TOTAL_AMOUNT cannot be negative
~~~

ORA-04088 cho biết trigger execution thất bại; hãy đọc lỗi gốc và dòng PL/SQL để tìm nguyên nhân.

### 11.3. Không COMMIT/ROLLBACK trong trigger thông thường

Trigger chạy trong transaction của statement kích hoạt nó. Không gọi COMMIT hoặc ROLLBACK trực tiếp trong trigger thông thường. Cố làm vậy có thể gây ORA-04092.

Quyền sở hữu transaction nên thuộc caller/service hoặc một quy trình được thiết kế rõ. Trigger không nên tự quyết định commit một phần dữ liệu nghiệp vụ.

## 12. Autonomous transaction và side effect ngoài database

Một số trigger gọi procedure được khai báo PRAGMA AUTONOMOUS_TRANSACTION. Autonomous transaction có transaction context riêng, có thể COMMIT độc lập.

Ví dụ này chỉ minh họa hành vi:

~~~sql
CREATE OR REPLACE PROCEDURE write_independent_log (
    p_message IN VARCHAR2
) IS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO independent_log(message, created_at)
    VALUES (p_message, SYSTIMESTAMP);

    COMMIT;
END;
/
~~~

Trigger có thể gọi procedure đó. Nếu statement gốc sau đó rollback, dòng trong INDEPENDENT_LOG vẫn tồn tại vì đã commit trong transaction độc lập.

### 12.1. Vì sao đây có thể là tác động ngoài dự kiến?

Giả sử trigger ghi “ORDER CREATED” bằng autonomous transaction, nhưng INSERT ORDERS sau đó thất bại và rollback. Log độc lập vẫn ghi ORDER CREATED dù order không tồn tại.

Điều này có thể hữu ích cho một số loại diagnostic log, nhưng không phù hợp làm audit nghiệp vụ đòi hỏi phản ánh đúng dữ liệu đã commit.

Rủi ro khác:

- Autonomous transaction có thể deadlock nếu cố truy cập tài nguyên đang bị transaction cha giữ.
- Caller có thể thấy log ghi nhận một sự kiện chưa commit.
- Lỗi ở transaction cha không tự rollback dữ liệu autonomous đã commit.
- Dữ liệu log có thể không còn đồng nhất với trạng thái nghiệp vụ.

Chỉ dùng autonomous transaction khi semantics độc lập được chủ đích và được tài liệu hóa.

### 12.2. Gọi email, HTTP hoặc message broker từ trigger

Một lời gọi mạng không nằm trong transaction Oracle theo cách có thể rollback. Ví dụ trigger gửi email rồi statement thất bại; email vẫn đã được gửi.

Không nên gọi dịch vụ bên ngoài đồng bộ trong trigger nghiệp vụ nếu yêu cầu là chỉ phát thông báo sau khi transaction commit thành công.

### 12.3. Transactional outbox

Một mẫu an toàn hơn:

1. Trigger hoặc application ghi một dòng event vào bảng OUTBOX cùng transaction với DML nghiệp vụ.
2. Nếu statement/transaction rollback, dòng outbox cũng rollback.
3. Sau COMMIT, worker riêng đọc các event chưa gửi.
4. Worker gửi message/email đến hệ thống ngoài.
5. Worker đánh dấu trạng thái và retry có giới hạn.
6. Consumer xử lý idempotent để chịu được gửi lặp.

Ví dụ bảng:

~~~sql
CREATE TABLE event_outbox (
    event_id NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    aggregate_id NUMBER NOT NULL,
    event_type VARCHAR2(50) NOT NULL,
    payload CLOB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    published_at TIMESTAMP WITH TIME ZONE
);
~~~

Trigger có thể ghi event vào OUTBOX; worker xử lý sau commit. Với hệ thống lớn, application service có thể ghi outbox trực tiếp trong cùng transaction để luồng nghiệp vụ rõ hơn trigger ẩn.

## 13. Compound trigger và ví dụ xử lý mutating table

Một ví dụ cụ thể hơn là cần kiểm tra tổng lương của phòng ban sau khi cập nhật một hoặc nhiều nhân viên. Row trigger không nên query EMPLOYEES trong lúc bảng đang mutating.

Ta có thể thu thập department ID và thực hiện kiểm tra ở AFTER STATEMENT.

~~~sql
CREATE OR REPLACE TRIGGER trg_check_dept_salary
FOR UPDATE OF salary ON employees
COMPOUND TRIGGER

    TYPE dept_set_t IS TABLE OF BOOLEAN
        INDEX BY VARCHAR2(100);

    g_dept_set dept_set_t;

    AFTER EACH ROW IS
        l_key VARCHAR2(100);
    BEGIN
        IF :NEW.department_id IS NOT NULL THEN
            l_key := TO_CHAR(:NEW.department_id);
            g_dept_set(l_key) := TRUE;
        END IF;
    END AFTER EACH ROW;

    AFTER STATEMENT IS
        l_key VARCHAR2(100);
        l_total_salary NUMBER;
    BEGIN
        l_key := g_dept_set.FIRST;

        WHILE l_key IS NOT NULL LOOP
            SELECT SUM(salary)
            INTO l_total_salary
            FROM employees
            WHERE department_id = TO_NUMBER(l_key);

            -- Thực hiện validation hoặc cập nhật summary ở đây.
            -- Không thực hiện DML lặp lại không cần thiết.
            l_key := g_dept_set.NEXT(l_key);
        END LOOP;
    END AFTER STATEMENT;

END trg_check_dept_salary;
/
~~~

Ví dụ dùng associative array làm tập hợp key để loại trùng; trong hệ thống thật cần chọn kiểu key phù hợp với datatype, format và quy tắc chuyển đổi. Nếu department ID là NUMBER, có thể dùng collection numeric index với cách lưu ID riêng hoặc SQL collection type. Mục đích ở đây là minh họa thu thập trong row section và truy vấn sau statement.

Không nên copy ví dụ vào production mà chưa kiểm thử datatype, nullability, số lượng hàng, hiệu năng và semantics validation. Nếu AFTER STATEMENT raise lỗi, statement gốc thất bại và thay đổi cùng statement được rollback.

## 14. Chẩn đoán trigger và thứ tự thực thi

Khi một DML có tác động bất ngờ, kiểm tra trigger trên bảng trước khi sửa code ứng dụng.

### 14.1. Liệt kê trigger trong schema

~~~sql
SELECT trigger_name,
       trigger_type,
       triggering_event,
       table_name,
       status,
       action_type
FROM user_triggers
ORDER BY table_name, trigger_name;
~~~

Các cột giúp biết trigger thuộc loại statement/row, event nào, bảng nào và đang ENABLED hay DISABLED.

### 14.2. Xem trigger theo một bảng

~~~sql
SELECT trigger_name,
       trigger_type,
       triggering_event,
       status,
       when_clause
FROM user_triggers
WHERE table_name = 'ORDERS'
ORDER BY trigger_name;
~~~

Không suy ra thứ tự thực thi từ ORDER BY trigger_name. Query chỉ liệt kê tên; thứ tự firing giữa nhiều trigger cùng timing point không được xác định bằng alphabet.

### 14.3. Xem cột mà trigger UPDATE OF theo dõi

~~~sql
SELECT trigger_name,
       table_name,
       column_name,
       column_list,
       column_usage
FROM user_trigger_cols
WHERE table_name = 'EMPLOYEES'
ORDER BY trigger_name, column_name;
~~~

View này giúp kiểm tra trigger có gắn với cột nào.

### 14.4. Xem compile error

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

Nếu trigger INVALID hoặc compile lỗi, xem đầy đủ lỗi và source line. Với schema khác, DBA có thể dùng ALL_TRIGGERS/DBA_TRIGGERS và ALL_ERRORS/DBA_ERRORS theo quyền.

### 14.5. Xem source trigger

~~~sql
SELECT line, text
FROM user_source
WHERE name = 'TRG_ORDERS_AUDIT'
  AND type = 'TRIGGER'
ORDER BY line;
~~~

Có thể dùng DBMS_METADATA.GET_DDL để lấy DDL trigger khi có quyền:

~~~sql
SELECT DBMS_METADATA.GET_DDL(
    'TRIGGER',
    'TRG_ORDERS_AUDIT',
    USER
)
FROM dual;
~~~

### 14.6. Enable, disable và compile

~~~sql
ALTER TRIGGER trg_orders_audit DISABLE;
ALTER TRIGGER trg_orders_audit ENABLE;
ALTER TRIGGER trg_orders_audit COMPILE;
~~~

Tắt trigger có thể làm mất audit hoặc validation trong thời gian đó. Chỉ disable khi có quy trình kiểm soát, hiểu dữ liệu phát sinh trong khoảng tắt và có bước đối soát sau khi enable.

## 15. Thực hành: quan sát thứ tự statement và row trigger

Dùng schema lab riêng.

### 15.1. Tạo bảng và log

~~~sql
CREATE TABLE lab_trigger_orders (
    order_id NUMBER PRIMARY KEY,
    amount NUMBER NOT NULL,
    status VARCHAR2(20)
);

CREATE TABLE lab_trigger_log (
    log_id NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    trigger_name VARCHAR2(50),
    timing_point VARCHAR2(30),
    order_id NUMBER,
    logged_at TIMESTAMP DEFAULT SYSTIMESTAMP
);
~~~

### 15.2. Tạo BEFORE STATEMENT

~~~sql
CREATE OR REPLACE TRIGGER lab_orders_before_stmt
BEFORE UPDATE ON lab_trigger_orders
BEGIN
    INSERT INTO lab_trigger_log(
        trigger_name, timing_point, order_id
    )
    VALUES (
        'LAB_ORDERS_BEFORE_STMT', 'BEFORE STATEMENT', NULL
    );
END;
/
~~~

### 15.3. Tạo BEFORE EACH ROW

~~~sql
CREATE OR REPLACE TRIGGER lab_orders_before_row
BEFORE UPDATE ON lab_trigger_orders
FOR EACH ROW
BEGIN
    INSERT INTO lab_trigger_log(
        trigger_name, timing_point, order_id
    )
    VALUES (
        'LAB_ORDERS_BEFORE_ROW', 'BEFORE EACH ROW', :OLD.order_id
    );
END;
/
~~~

### 15.4. Tạo AFTER EACH ROW

~~~sql
CREATE OR REPLACE TRIGGER lab_orders_after_row
AFTER UPDATE ON lab_trigger_orders
FOR EACH ROW
BEGIN
    INSERT INTO lab_trigger_log(
        trigger_name, timing_point, order_id
    )
    VALUES (
        'LAB_ORDERS_AFTER_ROW', 'AFTER EACH ROW', :NEW.order_id
    );
END;
/
~~~

### 15.5. Tạo AFTER STATEMENT

~~~sql
CREATE OR REPLACE TRIGGER lab_orders_after_stmt
AFTER UPDATE ON lab_trigger_orders
BEGIN
    INSERT INTO lab_trigger_log(
        trigger_name, timing_point, order_id
    )
    VALUES (
        'LAB_ORDERS_AFTER_STMT', 'AFTER STATEMENT', NULL
    );
END;
/
~~~

### 15.6. Chèn dữ liệu và thực hiện UPDATE nhiều hàng

~~~sql
INSERT INTO lab_trigger_orders VALUES (1, 100, 'NEW');
INSERT INTO lab_trigger_orders VALUES (2, 200, 'NEW');
INSERT INTO lab_trigger_orders VALUES (3, 300, 'NEW');
COMMIT;

UPDATE lab_trigger_orders
SET status = 'CHECKED'
WHERE order_id IN (1, 2, 3);

SELECT trigger_name,
       timing_point,
       order_id,
       logged_at
FROM lab_trigger_log
ORDER BY log_id;

COMMIT;
~~~

Quan sát:

- BEFORE STATEMENT có một log.
- BEFORE EACH ROW có ba log.
- AFTER EACH ROW có ba log.
- AFTER STATEMENT có một log.

Không dùng LOG_ID để suy ra thứ tự giữa các hàng là hợp đồng nghiệp vụ. Nó chỉ ghi lại thứ tự quan sát được trong lần chạy lab cụ thể.

### 15.7. UPDATE không khớp hàng

~~~sql
UPDATE lab_trigger_orders
SET status = 'NONE'
WHERE order_id = -1;

SELECT trigger_name, timing_point, order_id
FROM lab_trigger_log
ORDER BY log_id;

ROLLBACK;
~~~

Statement-level trigger vẫn tạo log; row-level trigger không tạo log vì không có hàng phù hợp.

## 16. Thực hành: trigger lồng nhau

Tạo bảng phụ:

~~~sql
CREATE TABLE lab_trigger_summary (
    order_id NUMBER PRIMARY KEY,
    status VARCHAR2(20)
);

CREATE OR REPLACE TRIGGER lab_log_after_insert
AFTER INSERT ON lab_trigger_log
FOR EACH ROW
BEGIN
    NULL;
END;
/
~~~

Ví dụ trigger trên ORDERS chèn audit:

~~~sql
CREATE OR REPLACE TRIGGER lab_order_insert_audit
AFTER INSERT ON lab_trigger_orders
FOR EACH ROW
BEGIN
    INSERT INTO lab_trigger_log(
        trigger_name, timing_point, order_id
    )
    VALUES (
        'LAB_ORDER_INSERT_AUDIT', 'AFTER INSERT', :NEW.order_id
    );
END;
/
~~~

Nếu bảng LAB_TRIGGER_LOG có trigger khác thực hiện DML tiếp theo, chuỗi trigger sẽ tiếp tục. Hãy thêm từng trigger một, kiểm tra số DML phát sinh và tránh tạo vòng lặp không giới hạn.

Sau khi thử, rollback transaction và dọn các object lab khi không cần nữa.

## 17. Các lỗi và tác động thường gặp

| Lỗi/tác động | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| ORA-04091 | Row trigger query/update bảng đang mutating | Compound trigger hoặc chuyển xử lý sang statement-level |
| ORA-04088 | Lỗi xảy ra trong quá trình thực thi trigger | Đọc lỗi gốc và dòng trigger |
| ORA-04092 | Trigger cố COMMIT/ROLLBACK | Để caller quản lý transaction |
| ORA-04098 | Trigger invalid và revalidation/recompile thất bại khi kích hoạt | USER_ERRORS, compile source và dependency |
| ORA-04084 | Gán :NEW trong AFTER row trigger | Chuyển gán sang BEFORE row |
| ORA-04082 | NEW/OLD không được phép ở statement trigger | Chỉ dùng pseudorecord trong row-level trigger |
| Trigger chạy nhiều lần | Row-level trigger chạy cho mỗi hàng | Kiểm tra số hàng DML và timing point |
| Thứ tự xử lý không ổn định | Dựa vào thứ tự trigger/hàng không được bảo đảm | FOLLOWS phù hợp hoặc gộp logic |
| Dữ liệu audit tồn tại sau rollback | Autonomous transaction hoặc side effect ngoài DB | Dùng cùng transaction/outbox nếu cần nhất quán |
| DML chậm bất thường | Trigger chain và DML phụ quá nhiều | Đo toàn bộ chain, giảm row-by-row |
| Trigger lặp vô hạn | A cập nhật B, B cập nhật lại A | Loại bỏ vòng phụ thuộc, idempotency |
| MERGE tạo nhiều hành động hơn dự kiến | Cả nhánh INSERT/UPDATE/DELETE có trigger tương ứng | Kiểm thử từng nhánh MERGE |

Mã lỗi chỉ là điểm bắt đầu. Cần kiểm tra trigger source, call stack, SQL gây kích hoạt và transaction state.

## 18. Nguyên tắc thiết kế trigger dễ kiểm soát

### 18.1. Giữ trigger ngắn

Trigger nên thực hiện công việc nhỏ, có tên và mục đích rõ. Nếu logic dài, gọi package/procedure có thể kiểm thử độc lập.

### 18.2. Không giấu transaction boundary

Trigger không nên tự COMMIT. Caller cần biết toàn bộ thay đổi nào nằm trong cùng transaction và khi nào chúng trở nên bền vững.

### 18.3. Ưu tiên constraint cho integrity

Nếu quy tắc có thể dùng CHECK, UNIQUE, PK, FK hoặc NOT NULL, ưu tiên constraint. Trigger chỉ nên xử lý logic mà constraint không diễn đạt được.

### 18.4. Không gửi side effect không thể rollback

Email, HTTP request hoặc message gửi ngay trong trigger có thể thoát khỏi transaction. Dùng transactional outbox hoặc cơ chế after-commit phù hợp.

### 18.5. Tránh trigger chain nhiều tầng

Một DML statement nên có execution path dễ giải thích. Trigger trên bảng audit không nên lại sửa bảng nghiệp vụ theo cách tạo vòng lặp khó đoán.

### 18.6. Kiểm thử cả statement và row semantics

Thử DML tác động 0 hàng, 1 hàng và nhiều hàng; INSERT, UPDATE, DELETE; UPDATE OF; MERGE; exception; rollback; nhiều session đồng thời.

### 18.7. Theo dõi hiệu năng tổng thể

Đo elapsed time, logical reads, redo, số hàng audit, số DML phụ, wait event và lock. Không chỉ benchmark SQL statement mà bỏ qua trigger.

## 19. Checklist trước khi triển khai trigger

- [ ] Xác định trigger là statement-level hay row-level.
- [ ] Xác nhận BEFORE/AFTER/INSTEAD OF phù hợp.
- [ ] Biết trigger chạy một lần hay một lần mỗi hàng.
- [ ] Không dựa vào thứ tự ngầm giữa nhiều trigger cùng timing point.
- [ ] Nếu dùng FOLLOWS, kiểm tra trigger/timing compatibility và Oracle release.
- [ ] Không dựa vào thứ tự xử lý row-level.
- [ ] Kiểm tra :OLD/:NEW đúng với INSERT/UPDATE/DELETE.
- [ ] Dùng BEFORE row nếu cần gán :NEW.
- [ ] Không query bảng đang mutating từ row-level trigger.
- [ ] Dùng compound trigger khi cần gom hàng rồi xử lý sau statement.
- [ ] Kiểm tra trigger chain và đường đệ quy.
- [ ] Đảm bảo các thao tác lặp là idempotent hoặc có điều kiện dừng.
- [ ] Không COMMIT/ROLLBACK trong trigger thường.
- [ ] Hiểu rõ autonomous transaction và side effect ngoài DB.
- [ ] Dùng outbox cho event cần gửi sau commit.
- [ ] Kiểm tra cả nhánh INSERT/UPDATE/DELETE khi dùng MERGE.
- [ ] Xem USER_TRIGGERS, USER_TRIGGER_COLS, USER_ERRORS.
- [ ] Kiểm thử 0, 1 và nhiều hàng; rollback và exception.
- [ ] Đo toàn bộ DML/trigger chain trước khi lên production.

## 20. Ghi nhớ cốt lõi

- Một DML statement có thể kích hoạt nhiều timing point và nhiều trigger lồng nhau.
- Thứ tự cơ bản là BEFORE STATEMENT, BEFORE EACH ROW, thao tác hàng, AFTER EACH ROW, rồi AFTER STATEMENT.
- Statement-level trigger chạy một lần cho statement phù hợp kể cả khi không có hàng bị tác động; row-level trigger chỉ chạy cho hàng thực sự được xử lý.
- Không dựa vào thứ tự tạo hoặc tên của nhiều trigger cùng timing point; dùng FOLLOWS khi được hỗ trợ hoặc gộp logic vào một trigger điều phối.
- :OLD và :NEW chỉ có ý nghĩa trong row-level trigger; :NEW có thể được gán trong BEFORE EACH ROW.
- UPDATE OF column chỉ cho biết cột xuất hiện trong SET list, không chứng minh giá trị thực sự thay đổi.
- Trigger lồng nhau phát sinh khi trigger thực hiện DML kích hoạt trigger khác; thiết kế vòng lặp cần được loại bỏ.
- ORA-04091 xảy ra khi row-level trigger truy cập bảng đang mutating; compound trigger có thể thu thập dữ liệu ở row section rồi xử lý trong AFTER STATEMENT.
- Trigger DML thường chạy trong cùng transaction; lỗi trigger có thể làm statement gốc thất bại và rollback các thay đổi của statement đó.
- Autonomous transaction và side effect bên ngoài có thể tồn tại sau rollback; dùng có chủ đích, ưu tiên transactional outbox cho event sau commit.
- Dùng constraint cho quy tắc integrity có thể biểu diễn bằng constraint; giữ trigger ngắn và dễ kiểm thử.
- Kiểm tra metadata, source, compile errors, call stack và toàn bộ trigger chain khi điều tra hành vi ngoài dự kiến.

### Tài liệu Oracle nên đối chiếu

- [Oracle Database PL/SQL Language Reference — DML Triggers](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/dml-triggers.html) — Timing points, row/statement triggers, :OLD/:NEW, trigger ordering và compound triggers.
- [Oracle Database PL/SQL Language Reference — Compound DML Triggers](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/dml-triggers.html) — Compound trigger sections, shared state và mutating-table workaround.
- [Oracle Database Concepts](https://docs.oracle.com/en/database/) — Transactions, statement-level atomicity, locks và read consistency.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — CREATE TRIGGER, FOLLOWS, MERGE và DML semantics.
- [Oracle Database Reference](https://docs.oracle.com/en/database/) — USER_TRIGGERS, USER_TRIGGER_COLS, USER_ERRORS và USER_SOURCE.
- [Oracle Database PL/SQL Packages and Types Reference](https://docs.oracle.com/en/database/) — DBMS_METADATA, DBMS_ASSERT và transaction utilities.

Trigger ordering, compound trigger restrictions, MERGE firing details và một số online/runtime behavior phụ thuộc Oracle release. Đối chiếu tài liệu đúng phiên bản và chạy các tình huống 0/1/n hàng, rollback, exception, lồng trigger và concurrent DML trên schema lab trước khi triển khai.

