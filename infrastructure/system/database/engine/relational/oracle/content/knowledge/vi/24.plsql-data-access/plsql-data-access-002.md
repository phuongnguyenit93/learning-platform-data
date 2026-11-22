# DML trong PL/SQL và đọc SQL%ROWCOUNT

PL/SQL cho phép đặt các câu lệnh SQL trực tiếp bên trong block, procedure, function, trigger hoặc package. Khi một câu DML chạy, Oracle thực hiện thay đổi dữ liệu theo transaction hiện tại và cung cấp các thuộc tính của implicit SQL cursor để chương trình biết câu lệnh vừa tác động bao nhiêu hàng. Thuộc tính thường dùng nhất là SQL%ROWCOUNT.

SQL%ROWCOUNT trả về số hàng bị ảnh hưởng bởi câu SQL gần nhất được thực thi trong session. Với INSERT, UPDATE, DELETE và MERGE, giá trị này giúp kiểm tra một thao tác có tác động dữ liệu hay không, ghi log số hàng đã xử lý, phân biệt trường hợp không tìm thấy hàng và kiểm soát quy trình nghiệp vụ.

Điểm quan trọng là SQL%ROWCOUNT thay đổi sau mỗi câu SQL. Nếu thực hiện một SELECT, gọi procedure khác có chạy SQL, hoặc ghi log bằng câu INSERT sau DML chính rồi mới đọc thuộc tính, giá trị có thể không còn là số hàng của DML ban đầu. Hãy chụp ngay giá trị vào biến PL/SQL trước khi chạy câu SQL tiếp theo.

Sau bài học, bạn có thể:

- Thực hiện INSERT, UPDATE, DELETE và MERGE trong PL/SQL.
- Đọc SQL%ROWCOUNT ngay sau DML và hiểu ý nghĩa số hàng được trả về.
- Phân biệt SQL%ROWCOUNT với SQL%FOUND, SQL%NOTFOUND và SQL%ISOPEN.
- Xử lý trường hợp DML tác động 0 hàng mà không nhầm với exception.
- Lưu row count trước khi chạy SQL khác hoặc gọi procedure khác.
- Trả số hàng ảnh hưởng từ procedure qua OUT parameter.
- Dùng RETURNING INTO để nhận giá trị cột của hàng được DML tác động.
- Dùng dynamic SQL và FORALL, hiểu SQL%BULK_ROWCOUNT và SAVE EXCEPTIONS.
- Phân biệt số hàng bị ảnh hưởng với transaction đã COMMIT.
- Viết block có kiểm tra, logging và exception handling rõ ràng.

> Các ví dụ dùng bảng LAB_ để thực hành trong schema riêng. Câu lệnh COMMIT/ROLLBACK là quyết định transaction của ứng dụng; không tự động phát sinh chỉ vì block PL/SQL kết thúc.

## 1. DML trong PL/SQL là gì?

DML (Data Manipulation Language) là nhóm câu lệnh thao tác dữ liệu trong bảng hoặc view. Các câu lệnh thường gặp:

| Câu lệnh | Mục đích |
| --- | --- |
| INSERT | Thêm hàng mới |
| UPDATE | Sửa các hàng hiện có |
| DELETE | Xóa các hàng thỏa điều kiện |
| MERGE | Kết hợp INSERT và UPDATE theo điều kiện so khớp |

PL/SQL cho phép viết DML trực tiếp trong executable section của block:

```sql
BEGIN
    UPDATE employees
    SET salary = salary * 1.05
    WHERE department_id = 50;
END;
/
```

Câu UPDATE trên chạy như một câu SQL bình thường. PL/SQL chỉ bổ sung khả năng dùng biến, điều kiện, vòng lặp, exception handler và cursor attributes để điều khiển chương trình.

### 1.1. Cấu trúc block PL/SQL

Một block có cấu trúc:

```sql
DECLARE
    -- Khai báo biến, hằng, cursor, exception
BEGIN
    -- Câu lệnh thực thi: DML, SELECT INTO, gọi procedure...
EXCEPTION
    -- Xử lý exception nếu có
END;
/
```

DECLARE và EXCEPTION là tùy chọn; BEGIN và END là bắt buộc. DML được đặt trong phần BEGIN...END, không đặt trong phần DECLARE.

### 1.2. DML trong block không tự commit

Kết thúc block PL/SQL không đồng nghĩa commit transaction:

```sql
BEGIN
    UPDATE lab_accounts
    SET balance = balance - 100
    WHERE account_id = 10;
END;
/
```

Nếu không có COMMIT, thay đổi vẫn thuộc transaction của session. Client có thể commit hoặc rollback sau đó; một block khác trong cùng session cũng có thể tiếp tục transaction. SQL%ROWCOUNT chỉ báo số hàng bị tác động bởi câu SQL, không báo transaction đã commit hay dữ liệu đã được session khác nhìn thấy.

### 1.3. DML 0 hàng không phải lỗi cú pháp

UPDATE hoặc DELETE có thể chạy thành công nhưng không tìm thấy hàng thỏa WHERE:

```sql
BEGIN
    UPDATE lab_employees
    SET status = 'INACTIVE'
    WHERE employee_id = -1;

    DBMS_OUTPUT.PUT_LINE('Rows affected = ' || SQL%ROWCOUNT);
END;
/
```

Nếu không có EMPLOYEE_ID = -1, UPDATE tác động 0 hàng. Nó không tự phát sinh NO_DATA_FOUND. SQL%ROWCOUNT sẽ là 0.

Điều này khác SELECT ... INTO: SELECT INTO được thiết kế để lấy đúng một hàng; nếu không có hàng, PL/SQL phát sinh NO_DATA_FOUND.

## 2. Implicit SQL cursor và các thuộc tính SQL%

Khi PL/SQL thực thi câu SQL không dùng explicit cursor do người lập trình khai báo, Oracle quản lý một implicit cursor có tên SQL. Bạn có thể đọc các thuộc tính của cursor này bằng cú pháp SQL%....

### 2.1. SQL%ROWCOUNT

SQL%ROWCOUNT trả về số hàng được xử lý bởi câu SQL gần nhất. Với DML, đây là số hàng bị INSERT, UPDATE, DELETE hoặc bị tác động bởi MERGE.

Ví dụ:

```sql
BEGIN
    UPDATE lab_employees
    SET salary = salary + 500
    WHERE department_id = 20;

    DBMS_OUTPUT.PUT_LINE(
        'Updated rows: ' || SQL%ROWCOUNT
    );
END;
/
```

Nếu 7 hàng thỏa điều kiện, kết quả là 7. Nếu không hàng nào thỏa, kết quả là 0.

### 2.2. SQL%FOUND

SQL%FOUND là TRUE nếu câu SQL gần nhất tác động hoặc trả về ít nhất một hàng; FALSE nếu không có hàng. Trước khi câu SQL đầu tiên được thực thi trong session/ngữ cảnh phù hợp, thuộc tính có thể là NULL.

Với DML:

```sql
BEGIN
    DELETE FROM lab_sessions
    WHERE expires_at < SYSTIMESTAMP;

    IF SQL%FOUND THEN
        DBMS_OUTPUT.PUT_LINE('Có session hết hạn được xóa.');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Không có session hết hạn.');
    END IF;
END;
/
```

### 2.3. SQL%NOTFOUND

SQL%NOTFOUND là TRUE nếu câu SQL gần nhất không tác động/trả về hàng nào. Với DML, có thể dùng để kiểm tra câu lệnh vừa chạy không tác động hàng nào:

```sql
BEGIN
    UPDATE lab_orders
    SET status = 'CLOSED'
    WHERE order_id = 900001;

    IF SQL%NOTFOUND THEN
        DBMS_OUTPUT.PUT_LINE('Order không tồn tại hoặc không khớp điều kiện.');
    END IF;
END;
/
```

Trong thực tế, SQL%ROWCOUNT = 0 thường dễ đọc và tiện ghi log hơn khi cần con số cụ thể.

### 2.4. SQL%ISOPEN

SQL%ISOPEN luôn trả về FALSE vì Oracle tự đóng implicit cursor sau khi thực thi câu SQL. Không cần CLOSE implicit SQL cursor:

```sql
BEGIN
    UPDATE lab_employees
    SET status = 'ACTIVE'
    WHERE employee_id = 101;

    DBMS_OUTPUT.PUT_LINE(
        'Implicit SQL cursor open? ' ||
        CASE WHEN SQL%ISOPEN THEN 'YES' ELSE 'NO' END
    );
END;
/
```

Nếu cần tự điều khiển OPEN, FETCH và CLOSE, dùng explicit cursor hoặc cursor variable; khi đó đọc thuộc tính cursor_name%ROWCOUNT, cursor_name%FOUND, cursor_name%NOTFOUND và cursor_name%ISOPEN.

### 2.5. Bảng tổng hợp

| Thuộc tính | Ý nghĩa | Cách dùng thường gặp |
| --- | --- | --- |
| SQL%ROWCOUNT | Số hàng của SQL gần nhất | Đếm hàng DML tác động |
| SQL%FOUND | Có ít nhất một hàng được tác động/trả về | Kiểm tra có kết quả |
| SQL%NOTFOUND | Không có hàng được tác động/trả về | Kiểm tra không có kết quả |
| SQL%ISOPEN | Implicit cursor có đang mở không | Luôn FALSE |

Các thuộc tính SQL% luôn tham chiếu tới implicit cursor SQL, không phải cursor tường minh mà bạn tự khai báo.

## 3. Đọc SQL%ROWCOUNT sau INSERT

### 3.1. INSERT một hàng

```sql
BEGIN
    INSERT INTO lab_departments (
        department_id,
        department_name,
        created_at
    )
    VALUES (
        90,
        'Data Platform',
        SYSTIMESTAMP
    );

    DBMS_OUTPUT.PUT_LINE(
        'Inserted rows = ' || SQL%ROWCOUNT
    );
END;
/
```

INSERT một hàng thành công thường làm SQL%ROWCOUNT bằng 1.

### 3.2. INSERT nhiều hàng bằng INSERT ... SELECT

```sql
BEGIN
    INSERT INTO lab_employee_archive (
        employee_id,
        department_id,
        archived_at
    )
    SELECT
        employee_id,
        department_id,
        SYSTIMESTAMP
    FROM lab_employees
    WHERE status = 'INACTIVE';

    DBMS_OUTPUT.PUT_LINE(
        'Archived rows = ' || SQL%ROWCOUNT
    );
END;
/
```

SQL%ROWCOUNT là tổng số hàng được INSERT bởi statement. Nếu SELECT nguồn không trả hàng, INSERT ... SELECT vẫn thực thi thành công và row count bằng 0.

### 3.3. INSERT ... SELECT không đồng nghĩa SELECT INTO

Hai cấu trúc có semantics khác nhau:

```sql
-- INSERT ... SELECT: có thể thêm 0, 1 hoặc nhiều hàng.
INSERT INTO lab_archive (employee_id)
SELECT employee_id
FROM lab_employees
WHERE department_id = -1;

-- SELECT INTO: yêu cầu đúng một hàng.
SELECT employee_id
INTO l_employee_id
FROM lab_employees
WHERE employee_id = -1;
```

INSERT ... SELECT với nguồn rỗng có row count 0. SELECT INTO với nguồn rỗng phát sinh NO_DATA_FOUND; với nhiều hơn một hàng phát sinh TOO_MANY_ROWS.

### 3.4. INSERT và duplicate key

Nếu INSERT vi phạm PRIMARY KEY/UNIQUE constraint, Oracle phát sinh exception (thường ORA-00001). Khi statement thất bại, không dùng SQL%ROWCOUNT để giả định một phần hàng đã được thêm. Với một INSERT statement thông thường, lỗi constraint khiến statement đó thất bại; xử lý lỗi theo exception và transaction semantics.

Không bắt mọi exception rồi ghi nhận row count như thể INSERT thành công. Phân biệt duplicate key dự kiến với lỗi kết nối, NOT NULL, CHECK, foreign key hoặc lỗi khác.

## 4. Đọc SQL%ROWCOUNT sau UPDATE

### 4.1. UPDATE nhiều hàng

```sql
DECLARE
    l_rows_updated PLS_INTEGER;
BEGIN
    UPDATE lab_employees
    SET salary = salary * 1.10
    WHERE department_id = 30;

    l_rows_updated := SQL%ROWCOUNT;

    DBMS_OUTPUT.PUT_LINE(
        'Rows updated = ' || l_rows_updated
    );
END;
/
```

Biến l_rows_updated lưu số hàng ngay sau UPDATE. Nếu sau đó chương trình chạy một SELECT hoặc INSERT log, SQL%ROWCOUNT có thể thay đổi; biến cục bộ vẫn giữ giá trị đã chụp.

### 4.2. UPDATE không thay đổi giá trị

Nếu câu UPDATE khớp một hàng nhưng gán lại giá trị bằng giá trị hiện tại, SQL%ROWCOUNT vẫn đếm hàng bị tác động bởi statement. Nó không chỉ đếm số hàng có giá trị thực sự thay đổi.

Ví dụ:

```sql
UPDATE lab_employees
SET status = 'ACTIVE'
WHERE employee_id = 101;
```

Nếu EMPLOYEE_ID = 101 tồn tại và statement cập nhật hàng đó, row count là 1 kể cả STATUS đã là ACTIVE. Nếu cần chỉ đếm hàng có giá trị khác trước khi update, đưa điều kiện khác biệt vào WHERE và xử lý NULL đúng:

```sql
UPDATE lab_employees
SET status = 'ACTIVE'
WHERE employee_id = 101
  AND (status <> 'ACTIVE' OR status IS NULL);
```

Với nhiều cột nullable, cần biểu diễn phép so sánh null-safe phù hợp. Oracle DECODE xem hai NULL là bằng nhau; có thể dùng biểu thức đó khi phù hợp:

```sql
UPDATE lab_employees
SET status = 'ACTIVE'
WHERE employee_id = 101
  AND DECODE(status, 'ACTIVE', 0, 1) = 1;
```

### 4.3. UPDATE 0 hàng

```sql
BEGIN
    UPDATE lab_employees
    SET status = 'INACTIVE'
    WHERE employee_id = -1;

    IF SQL%ROWCOUNT = 0 THEN
        DBMS_OUTPUT.PUT_LINE('Không có hàng nào được cập nhật.');
    END IF;
END;
/
```

Không có exception tự động chỉ vì UPDATE tác động 0 hàng. Nếu nghiệp vụ yêu cầu đúng một hàng phải được cập nhật, tự kiểm tra row count và chủ động phát sinh exception:

```sql
DECLARE
    e_employee_not_updated EXCEPTION;
    l_rows PLS_INTEGER;
BEGIN
    UPDATE lab_employees
    SET status = 'INACTIVE'
    WHERE employee_id = 101;

    l_rows := SQL%ROWCOUNT;

    IF l_rows <> 1 THEN
        RAISE e_employee_not_updated;
    END IF;
EXCEPTION
    WHEN e_employee_not_updated THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Expected exactly one employee row to be updated.'
        );
END;
/
```

Đây là kiểm tra số hàng, không phải kiểm tra transaction đã commit. Caller vẫn quyết định commit/rollback theo ranh giới nghiệp vụ.

## 5. Đọc SQL%ROWCOUNT sau DELETE

### 5.1. DELETE nhiều hàng

```sql
DECLARE
    l_deleted_rows PLS_INTEGER;
BEGIN
    DELETE FROM lab_sessions
    WHERE expires_at < SYSTIMESTAMP;

    l_deleted_rows := SQL%ROWCOUNT;

    DBMS_OUTPUT.PUT_LINE(
        'Deleted rows = ' || l_deleted_rows
    );
END;
/
```

SQL%ROWCOUNT trả về tổng số hàng bị xóa bởi DELETE. Nếu không có session hết hạn, giá trị là 0.

### 5.2. DELETE có điều kiện và kiểm tra đúng một hàng

Nếu nghiệp vụ yêu cầu xóa đúng một đơn hàng:

```sql
DECLARE
    l_deleted_rows PLS_INTEGER;
BEGIN
    DELETE FROM lab_orders
    WHERE order_id = 5001
      AND status = 'CANCELLED';

    l_deleted_rows := SQL%ROWCOUNT;

    IF l_deleted_rows = 0 THEN
        RAISE_APPLICATION_ERROR(
            -20011,
            'Order was not found or is not cancellable.'
        );
    ELSIF l_deleted_rows > 1 THEN
        RAISE_APPLICATION_ERROR(
            -20012,
            'Unexpectedly deleted more than one order.'
        );
    END IF;
END;
/
```

Nếu ORDER_ID là primary key, số hàng lớn hơn 1 về lý thuyết không thể xảy ra. Kiểm tra vẫn có thể giúp phát hiện sai predicate hoặc sai giả định schema khi thao tác trên bảng không có khóa duy nhất.

### 5.3. DELETE và foreign key

Nếu hàng bị xóa được tham chiếu bởi foreign key, DELETE có thể thất bại với lỗi ràng buộc (ví dụ ORA-02292) trừ khi quan hệ được cấu hình ON DELETE CASCADE hoặc dữ liệu con đã được xử lý. Khi statement thất bại do constraint, chương trình đi vào exception handler; đừng coi SQL%ROWCOUNT là số hàng đã xóa thành công.

### 5.4. DELETE không giống TRUNCATE

DELETE là DML, có thể lọc hàng bằng WHERE, tạo undo theo transaction và có thể rollback trước commit. TRUNCATE là DDL, làm rỗng segment/phạm vi được chỉ định, có implicit commit và không thể dùng SQL%ROWCOUNT như bộ đếm DML tương đương. Nếu cần biết số hàng đã xóa bởi DELETE, chụp SQL%ROWCOUNT ngay sau câu DELETE.

## 6. Đọc SQL%ROWCOUNT sau MERGE

### 6.1. MERGE là upsert

MERGE so sánh hàng nguồn với bảng đích theo điều kiện ON:

- WHEN MATCHED: thực hiện UPDATE theo nhánh được khai báo.
- WHEN NOT MATCHED: thực hiện INSERT theo nhánh được khai báo.

Ví dụ:

```sql
DECLARE
    l_rows_affected PLS_INTEGER;
BEGIN
    MERGE INTO lab_products t
    USING (
        SELECT
            101 AS product_id,
            'Keyboard' AS product_name,
            850000 AS unit_price
        FROM dual
    ) s
    ON (t.product_id = s.product_id)
    WHEN MATCHED THEN
        UPDATE SET
            t.product_name = s.product_name,
            t.unit_price = s.unit_price
    WHEN NOT MATCHED THEN
        INSERT (product_id, product_name, unit_price)
        VALUES (s.product_id, s.product_name, s.unit_price);

    l_rows_affected := SQL%ROWCOUNT;

    DBMS_OUTPUT.PUT_LINE(
        'MERGE rows affected = ' || l_rows_affected
    );
END;
/
```

Nếu source row khớp một hàng target, MERGE có thể UPDATE một hàng và row count là 1. Nếu không khớp, MERGE INSERT một hàng và row count cũng là 1. Nếu nguồn rỗng hoặc không có hàng nào được xử lý, row count có thể bằng 0.

### 6.2. SQL%ROWCOUNT không phân biệt INSERT và UPDATE

Với MERGE có cả hai nhánh, SQL%ROWCOUNT là tổng số hàng bị tác động bởi statement. Nó không cung cấp riêng số hàng được INSERT và số hàng được UPDATE.

Ví dụ source có 10 hàng: 6 hàng match target và được UPDATE, 4 hàng không match và được INSERT. Row count tổng là 10. Nếu ứng dụng cần hai con số riêng, phải thiết kế cách đo riêng, ví dụ phân loại source trước khi MERGE theo một snapshot phù hợp, ghi audit/action trong quy trình được thiết kế cẩn thận, hoặc tách thao tác khi nghiệp vụ cho phép. Không suy ra số INSERT từ SQL%ROWCOUNT.

### 6.3. MERGE không nhất thiết cập nhật mọi hàng MATCHED

MERGE có thể có điều kiện WHERE trong nhánh UPDATE:

```sql
MERGE INTO lab_products t
USING (
    SELECT
        :product_id AS product_id,
        :unit_price AS unit_price
    FROM dual
) s
ON (t.product_id = s.product_id)
WHEN MATCHED THEN
    UPDATE SET t.unit_price = s.unit_price
    WHERE t.unit_price <> s.unit_price
WHEN NOT MATCHED THEN
    INSERT (product_id, unit_price)
    VALUES (s.product_id, s.unit_price);
```

Nếu target đã có product nhưng giá bằng giá nguồn, điều kiện UPDATE không thỏa nên hàng đó không được cập nhật. Row count không đếm hàng này. Nếu UNIT_PRICE có thể NULL, điều kiện so sánh khác nhau cần được thay bằng biểu thức null-safe để không bỏ sót trường hợp NULL chuyển sang có giá trị hoặc ngược lại.

### 6.4. MERGE source phải có quy tắc một hàng cho mỗi target key

Nếu nhiều hàng nguồn cùng match một hàng target, MERGE có thể thất bại với ORA-30926 (unable to get a stable set of rows). Nếu nhiều hàng nguồn cùng không match một khóa, có thể phát sinh duplicate key khi insert. Hãy chuẩn hóa/deduplicate source trước MERGE.

### 6.5. MERGE và nhánh DELETE

Oracle cho phép MERGE có DELETE WHERE trong nhánh UPDATE ở những phiên bản/cú pháp hỗ trợ. Row count vẫn là số hàng bị tác động bởi MERGE statement; không dùng nó để phân biệt bao nhiêu hàng UPDATE và bao nhiêu hàng DELETE. Kiểm tra cú pháp cụ thể và semantics DELETE WHERE theo Oracle SQL Language Reference của release đang dùng.

## 7. SQL%ROWCOUNT thay đổi sau mỗi câu SQL

Đây là quy tắc quan trọng nhất khi dùng thuộc tính này: SQL%ROWCOUNT mô tả câu SQL gần nhất, không ghi nhớ kết quả của một DML cũ.

### 7.1. Ví dụ đọc sai vì chạy SELECT trước

```sql
BEGIN
    UPDATE lab_employees
    SET status = 'INACTIVE'
    WHERE department_id = 40;

    SELECT COUNT(*)
    INTO l_total
    FROM lab_employees;

    DBMS_OUTPUT.PUT_LINE(
        'Updated rows = ' || SQL%ROWCOUNT
    );
END;
/
```

Sau SELECT INTO thành công, SQL%ROWCOUNT phản ánh SELECT vừa thực hiện (SELECT INTO trả một hàng vào biến), không còn là số hàng UPDATE. Để tránh lỗi, lưu row count ngay sau UPDATE:

```sql
DECLARE
    l_updated_rows PLS_INTEGER;
    l_total PLS_INTEGER;
BEGIN
    UPDATE lab_employees
    SET status = 'INACTIVE'
    WHERE department_id = 40;

    l_updated_rows := SQL%ROWCOUNT;

    SELECT COUNT(*)
    INTO l_total
    FROM lab_employees;

    DBMS_OUTPUT.PUT_LINE(
        'Updated rows = ' || l_updated_rows
    );
    DBMS_OUTPUT.PUT_LINE(
        'Total rows = ' || l_total
    );
END;
/
```

### 7.2. Lệnh logging có thể ghi đè SQL%ROWCOUNT

Đoạn sau dễ gây nhầm:

```sql
UPDATE lab_orders
SET status = 'CLOSED'
WHERE order_date < DATE '2025-01-01';

INSERT INTO lab_audit_log (
    event_name,
    affected_rows,
    created_at
)
VALUES (
    'CLOSE_OLD_ORDERS',
    SQL%ROWCOUNT,
    SYSTIMESTAMP
);
```

Trong VALUES, SQL%ROWCOUNT được đánh giá trước khi INSERT log thực thi, nên có thể ghi được số hàng UPDATE. Tuy nhiên sau INSERT log, SQL%ROWCOUNT đã phản ánh INSERT log (thường là 1). Nếu muốn in hoặc dùng lại số hàng UPDATE, phải lưu vào biến trước:

```sql
DECLARE
    l_updated_rows PLS_INTEGER;
BEGIN
    UPDATE lab_orders
    SET status = 'CLOSED'
    WHERE order_date < DATE '2025-01-01';

    l_updated_rows := SQL%ROWCOUNT;

    INSERT INTO lab_audit_log (
        event_name, affected_rows, created_at
    )
    VALUES (
        'CLOSE_OLD_ORDERS',
        l_updated_rows,
        SYSTIMESTAMP
    );

    DBMS_OUTPUT.PUT_LINE(
        'Orders closed = ' || l_updated_rows
    );
END;
/
```

### 7.3. Procedure được gọi có thể chạy SQL

Nếu gọi một procedure sau DML chính và procedure đó thực hiện SELECT/INSERT/UPDATE/DELETE, không nên dựa vào SQL%ROWCOUNT sau lời gọi để lấy số hàng của DML trước. Hãy chụp giá trị trước khi gọi procedure, hoặc truyền row count qua tham số.

### 7.4. SQL%ROWCOUNT không phải biến lịch sử

SQL%ROWCOUNT không giữ danh sách số hàng của nhiều câu DML trước đó. Nếu cần thống kê nhiều bước, dùng biến PL/SQL riêng:

```sql
DECLARE
    l_inserted PLS_INTEGER := 0;
    l_updated  PLS_INTEGER := 0;
    l_deleted  PLS_INTEGER := 0;
BEGIN
    INSERT INTO lab_archive (employee_id)
    SELECT employee_id
    FROM lab_employees
    WHERE status = 'INACTIVE';
    l_inserted := SQL%ROWCOUNT;

    UPDATE lab_employees
    SET status = 'ARCHIVED'
    WHERE status = 'INACTIVE';
    l_updated := SQL%ROWCOUNT;

    DELETE FROM lab_sessions
    WHERE expires_at < SYSTIMESTAMP;
    l_deleted := SQL%ROWCOUNT;

    DBMS_OUTPUT.PUT_LINE('Inserted = ' || l_inserted);
    DBMS_OUTPUT.PUT_LINE('Updated  = ' || l_updated);
    DBMS_OUTPUT.PUT_LINE('Deleted  = ' || l_deleted);
END;
/
```

Mỗi biến là snapshot của một câu DML cụ thể; chúng không bị ảnh hưởng bởi câu SQL tiếp theo.

## 8. SQL%ROWCOUNT với SELECT INTO

SQL%ROWCOUNT cũng có thể phản ánh câu SELECT INTO gần nhất, nhưng cách xử lý kết quả SELECT INTO khác DML:

- Trả đúng một hàng: SELECT INTO thành công.
- Không trả hàng: PL/SQL phát sinh NO_DATA_FOUND.
- Trả nhiều hơn một hàng: PL/SQL phát sinh TOO_MANY_ROWS.

Không dùng SELECT INTO như một câu truy vấn có thể trả tùy ý nhiều hàng rồi hy vọng SQL%ROWCOUNT cho biết số hàng. Dùng explicit cursor, cursor FOR loop hoặc BULK COLLECT nếu cần xử lý nhiều hàng.

Ví dụ:

```sql
DECLARE
    l_employee_name lab_employees.employee_name%TYPE;
    l_rows PLS_INTEGER;
BEGIN
    SELECT employee_name
    INTO l_employee_name
    FROM lab_employees
    WHERE employee_id = 101;

    l_rows := SQL%ROWCOUNT;

    DBMS_OUTPUT.PUT_LINE(
        'Rows fetched by SELECT INTO = ' || l_rows
    );
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('Không tìm thấy employee.');
    WHEN TOO_MANY_ROWS THEN
        DBMS_OUTPUT.PUT_LINE('Truy vấn trả về nhiều hơn một hàng.');
END;
/
```

Sau SELECT INTO thành công, row count là 1. Với trường hợp NO_DATA_FOUND hoặc TOO_MANY_ROWS, xử lý exception cụ thể; không dùng một giá trị row count đọc muộn trong exception handler như thể nó là số hàng DML trước đó. Nếu cần kiểm tra số hàng của DML trước khi chạy SELECT INTO, lưu nó vào biến trước.

## 9. SQL%ROWCOUNT và explicit cursor

PL/SQL có hai nhóm cursor attribute thường bị nhầm:

- SQL%ROWCOUNT: số hàng của câu SQL gần nhất được thực thi qua implicit SQL cursor.
- cursor_name%ROWCOUNT: số hàng đã FETCH qua explicit cursor được khai báo.

Ví dụ explicit cursor:

```sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id, employee_name
        FROM lab_employees
        WHERE department_id = 20;

    l_employee_id lab_employees.employee_id%TYPE;
    l_employee_name lab_employees.employee_name%TYPE;
BEGIN
    OPEN c_employees;

    LOOP
        FETCH c_employees
        INTO l_employee_id, l_employee_name;

        EXIT WHEN c_employees%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(
            c_employees%ROWCOUNT || ': ' ||
            l_employee_id || ' - ' || l_employee_name
        );
    END LOOP;

    DBMS_OUTPUT.PUT_LINE(
        'Fetched rows = ' || c_employees%ROWCOUNT
    );

    CLOSE c_employees;
END;
/
```

cursor_name%ROWCOUNT tăng theo số hàng đã FETCH, không phải tổng số hàng DML đã tác động. Sau OPEN nhưng trước FETCH, giá trị thường là 0. Khi FETCH hết dữ liệu, nó giữ số hàng đã fetch.

### 9.1. So sánh các cursor attribute

| Trường hợp | Thuộc tính nên đọc |
| --- | --- |
| UPDATE/INSERT/DELETE/MERGE vừa chạy | SQL%ROWCOUNT |
| SELECT INTO vừa chạy thành công | SQL%ROWCOUNT thường là 1 |
| Explicit cursor đã FETCH | c_name%ROWCOUNT |
| Kiểm tra explicit cursor còn mở | c_name%ISOPEN |
| Kiểm tra DML vừa tác động hàng nào | SQL%FOUND hoặc SQL%ROWCOUNT |

### 9.2. Cursor FOR loop

Cursor FOR loop tự OPEN, FETCH và CLOSE cursor:

```sql
BEGIN
    FOR r IN (
        SELECT employee_id, employee_name
        FROM lab_employees
        WHERE department_id = 20
    ) LOOP
        DBMS_OUTPUT.PUT_LINE(
            r.employee_id || ' - ' || r.employee_name
        );
    END LOOP;
END;
/
```

Nếu cần đếm số hàng được xử lý trong vòng lặp, dùng biến PL/SQL tự tăng. Không dùng SQL%ROWCOUNT như bộ đếm số hàng của cursor FOR loop.

## 10. Trả row count từ procedure

### 10.1. Vì sao nên dùng OUT parameter?

Procedure có thể thực hiện DML, nhưng caller không nên phụ thuộc vào giá trị SQL%ROWCOUNT sau lời gọi. Procedure có thể chạy thêm SQL để ghi log, truy vấn dữ liệu hoặc gọi procedure con. Một OUT parameter biểu đạt rõ kết quả mà procedure cam kết trả về.

### 10.2. Procedure cập nhật và trả số hàng

```sql
CREATE OR REPLACE PROCEDURE deactivate_department (
    p_department_id IN  NUMBER,
    p_rows_updated  OUT PLS_INTEGER
)
AS
BEGIN
    UPDATE lab_employees
    SET status = 'INACTIVE'
    WHERE department_id = p_department_id
      AND status <> 'INACTIVE';

    p_rows_updated := SQL%ROWCOUNT;
END;
/
```

Caller:

```sql
DECLARE
    l_rows PLS_INTEGER;
BEGIN
    deactivate_department(
        p_department_id => 30,
        p_rows_updated  => l_rows
    );

    DBMS_OUTPUT.PUT_LINE(
        'Rows deactivated = ' || l_rows
    );
END;
/
```

OUT parameter giữ con số được procedure chụp ngay sau UPDATE, kể cả khi caller chạy SQL khác sau đó.

### 10.3. Procedure ghi log và giữ đúng row count

```sql
CREATE OR REPLACE PROCEDURE close_old_orders (
    p_cutoff_date  IN  DATE,
    p_rows_closed  OUT PLS_INTEGER
)
AS
    l_rows PLS_INTEGER;
BEGIN
    UPDATE lab_orders
    SET status = 'CLOSED'
    WHERE order_date < p_cutoff_date
      AND status = 'OPEN';

    l_rows := SQL%ROWCOUNT;
    p_rows_closed := l_rows;

    INSERT INTO lab_job_log (
        job_name,
        affected_rows,
        logged_at
    )
    VALUES (
        'CLOSE_OLD_ORDERS',
        l_rows,
        SYSTIMESTAMP
    );
END;
/
```

INSERT vào LAB_JOB_LOG làm SQL%ROWCOUNT thay đổi, nhưng p_rows_closed vẫn chứa số hàng của UPDATE. DML chính và log nằm trong cùng transaction của caller; nếu caller rollback, cả hai thay đổi đều có thể rollback.

### 10.4. Thiết kế OUT parameter và exception

Quy ước nên rõ ràng:

- OUT parameter chỉ được gán khi procedure xác định được kết quả.
- Nếu DML thất bại và exception được phát sinh, caller nhận exception; không coi giá trị OUT là kết quả thành công.
- Không nuốt exception rồi trả 0, vì 0 có nghĩa statement chạy thành công nhưng không tác động hàng nào.
- Nếu cần báo cả trạng thái, row count và thông tin lỗi, thiết kế contract rõ ràng (OUT status/message hoặc exception có mã nghiệp vụ).

## 11. RETURNING INTO và SQL%ROWCOUNT

RETURNING INTO cho phép lấy giá trị cột của các hàng vừa được INSERT, UPDATE hoặc DELETE mà không cần chạy SELECT riêng sau đó.

### 11.1. INSERT ... RETURNING INTO

```sql
DECLARE
    l_new_employee_id lab_employees.employee_id%TYPE;
BEGIN
    INSERT INTO lab_employees (
        employee_id,
        employee_name,
        department_id,
        status
    )
    VALUES (
        lab_employee_seq.NEXTVAL,
        'Mai Tran',
        20,
        'ACTIVE'
    )
    RETURNING employee_id INTO l_new_employee_id;

    DBMS_OUTPUT.PUT_LINE(
        'Created employee ID = ' || l_new_employee_id
    );
    DBMS_OUTPUT.PUT_LINE(
        'Inserted rows = ' || SQL%ROWCOUNT
    );
END;
/
```

RETURNING lấy ID vừa được insert. SQL%ROWCOUNT vẫn cho biết số hàng của DML statement.

### 11.2. UPDATE ... RETURNING INTO

```sql
DECLARE
    l_new_salary lab_employees.salary%TYPE;
BEGIN
    UPDATE lab_employees
    SET salary = salary * 1.05
    WHERE employee_id = 101
    RETURNING salary INTO l_new_salary;

    DBMS_OUTPUT.PUT_LINE(
        'New salary = ' || l_new_salary
    );
    DBMS_OUTPUT.PUT_LINE(
        'Updated rows = ' || SQL%ROWCOUNT
    );
END;
/
```

Ví dụ này giả định EMPLOYEE_ID xác định tối đa một hàng. Nếu DML có thể tác động nhiều hàng, một biến scalar không đủ để nhận nhiều giá trị trả về.

### 11.3. DELETE nhiều hàng với RETURNING BULK COLLECT

```sql
DECLARE
    TYPE t_order_ids IS TABLE OF lab_orders.order_id%TYPE;
    l_deleted_ids t_order_ids;
    l_deleted_count PLS_INTEGER;
BEGIN
    DELETE FROM lab_orders
    WHERE status = 'CANCELLED'
      AND created_at < DATE '2025-01-01'
    RETURNING order_id BULK COLLECT INTO l_deleted_ids;

    l_deleted_count := SQL%ROWCOUNT;

    DBMS_OUTPUT.PUT_LINE(
        'Deleted rows = ' || l_deleted_count
    );

    FOR i IN 1 .. l_deleted_ids.COUNT LOOP
        DBMS_OUTPUT.PUT_LINE(
            'Deleted order = ' || l_deleted_ids(i)
        );
    END LOOP;
END;
/
```

BULK COLLECT nhận nhiều giá trị được trả về vào collection. SQL%ROWCOUNT vẫn là số hàng bị xóa. Với kết quả rỗng, collection không có phần tử và vòng lặp không chạy; kiểm tra COUNT trước nếu cần.

### 11.4. RETURNING không commit

RETURNING INTO chỉ trả giá trị của hàng DML vừa tác động. Nó không commit transaction và không đảm bảo thay đổi đã bền vững. Caller vẫn quản lý COMMIT/ROLLBACK.

## 12. Dynamic DML và SQL%ROWCOUNT

Dynamic SQL cho phép tạo câu SQL ở runtime. Với EXECUTE IMMEDIATE chạy DML, có thể đọc SQL%ROWCOUNT ngay sau lệnh.

### 12.1. Dynamic UPDATE với bind variable

```sql
DECLARE
    l_sql VARCHAR2(1000);
    l_rows PLS_INTEGER;
BEGIN
    l_sql :=
        'UPDATE lab_employees ' ||
        'SET status = :1 ' ||
        'WHERE department_id = :2';

    EXECUTE IMMEDIATE l_sql
        USING 'INACTIVE', 40;

    l_rows := SQL%ROWCOUNT;

    DBMS_OUTPUT.PUT_LINE(
        'Dynamic update rows = ' || l_rows
    );
END;
/
```

EXECUTE IMMEDIATE chạy DML như statement SQL thông thường; SQL%ROWCOUNT phản ánh số hàng tác động. Dùng bind variable cho giá trị thay đổi để giảm parse và tránh SQL injection.

### 12.2. Dynamic DELETE

```sql
DECLARE
    l_table_name VARCHAR2(30) := 'LAB_SESSIONS';
    l_rows PLS_INTEGER;
BEGIN
    EXECUTE IMMEDIATE
        'DELETE FROM ' || DBMS_ASSERT.SQL_OBJECT_NAME(l_table_name) ||
        ' WHERE status = :1'
        USING 'EXPIRED';

    l_rows := SQL%ROWCOUNT;
    DBMS_OUTPUT.PUT_LINE('Deleted = ' || l_rows);
END;
/
```

Tên bảng/column không thể truyền bằng bind variable như một giá trị. Nếu phải ghép identifier vào câu SQL, xác thực bằng whitelist hoặc DBMS_ASSERT phù hợp; không nối trực tiếp input không tin cậy.

### 12.3. Dynamic SELECT

Với dynamic SELECT trả một hàng, dùng INTO:

```sql
DECLARE
    l_count NUMBER;
BEGIN
    EXECUTE IMMEDIATE
        'SELECT COUNT(*) FROM lab_employees WHERE status = :1'
        INTO l_count
        USING 'ACTIVE';

    DBMS_OUTPUT.PUT_LINE('Active employees = ' || l_count);
END;
/
```

SELECT COUNT(*) luôn trả một hàng tổng hợp, kể cả khi không có employee thỏa điều kiện. Nếu dynamic SELECT trả nhiều hàng, dùng collection BULK COLLECT hoặc DBMS_SQL/ref cursor phù hợp.

### 12.4. DDL động không có row count DML hữu ích

EXECUTE IMMEDIATE có thể chạy DDL như CREATE TABLE hoặc ALTER TABLE. Không dùng SQL%ROWCOUNT để đếm số hàng cho DDL; DDL không phải thao tác DML trên tập hàng theo nghĩa này. Dùng dictionary và kiểm tra trạng thái đối tượng sau DDL.

## 13. FORALL và SQL%BULK_ROWCOUNT

Khi cần thực hiện cùng một câu DML cho nhiều phần tử trong collection, FORALL có thể gửi các bind values theo lô, giảm số lần chuyển qua lại giữa PL/SQL engine và SQL engine. Đây là bulk DML.

FORALL không phải vòng lặp PL/SQL thông thường. Nó lặp một DML statement theo các chỉ số của collection và cho phép đọc kết quả từng lần thực thi qua SQL%BULK_ROWCOUNT.

### 13.1. Ví dụ FORALL UPDATE

```sql
DECLARE
    TYPE t_employee_ids IS TABLE OF NUMBER
        INDEX BY PLS_INTEGER;

    l_employee_ids t_employee_ids;
    l_total_rows PLS_INTEGER;
BEGIN
    l_employee_ids(1) := 101;
    l_employee_ids(2) := 102;
    l_employee_ids(3) := 999999;

    FORALL i IN 1 .. l_employee_ids.COUNT
        UPDATE lab_employees
        SET status = 'INACTIVE'
        WHERE employee_id = l_employee_ids(i);

    l_total_rows := SQL%ROWCOUNT;

    DBMS_OUTPUT.PUT_LINE(
        'Total rows affected by FORALL = ' || l_total_rows
    );

    FOR i IN 1 .. l_employee_ids.COUNT LOOP
        DBMS_OUTPUT.PUT_LINE(
            'Input index ' || i ||
            ' affected rows = ' || SQL%BULK_ROWCOUNT(i)
        );
    END LOOP;
END;
/
```

Giả sử ID 101 và 102 tồn tại, ID 999999 không tồn tại. SQL%BULK_ROWCOUNT có thể cho kết quả 1, 1 và 0 tương ứng; SQL%ROWCOUNT là tổng số hàng bị tác động bởi tất cả lần thực thi, trong ví dụ này là 2.

### 13.2. SQL%ROWCOUNT và SQL%BULK_ROWCOUNT

| Thuộc tính | Ý nghĩa sau FORALL |
| --- | --- |
| SQL%ROWCOUNT | Tổng số hàng bị tác động bởi tất cả lần chạy DML trong FORALL |
| SQL%BULK_ROWCOUNT(i) | Số hàng bị tác động bởi lần chạy DML thứ i |

SQL%ROWCOUNT trả lời tổng thể; SQL%BULK_ROWCOUNT giúp xác định phần tử đầu vào nào tác động 0, 1 hoặc nhiều hàng.

### 13.3. Xử lý từng kết quả bulk

Nếu mỗi ID phải xác định đúng một hàng:

```sql
DECLARE
    TYPE t_ids IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    l_ids t_ids;
BEGIN
    l_ids(1) := 101;
    l_ids(2) := 102;
    l_ids(3) := 999999;

    FORALL i IN 1 .. l_ids.COUNT
        UPDATE lab_employees
        SET status = 'ACTIVE'
        WHERE employee_id = l_ids(i);

    FOR i IN 1 .. l_ids.COUNT LOOP
        IF SQL%BULK_ROWCOUNT(i) = 0 THEN
            DBMS_OUTPUT.PUT_LINE(
                'Không tìm thấy employee ID ' || l_ids(i)
            );
        ELSIF SQL%BULK_ROWCOUNT(i) > 1 THEN
            DBMS_OUTPUT.PUT_LINE(
                'ID không duy nhất: ' || l_ids(i)
            );
        END IF;
    END LOOP;
END;
/
```

Vòng lặp đọc SQL%BULK_ROWCOUNT phải chạy trước khi một FORALL khác thay thế thông tin bulk của câu lệnh trước. Nếu cần lưu kết quả lâu hơn, copy từng giá trị vào collection PL/SQL riêng trước khi thực hiện SQL tiếp theo.

### 13.4. FORALL với collection thưa

Collection associative array có thể có chỉ số không liên tục. Nếu dùng phạm vi 1..COUNT trên collection thưa, có thể gặp phần tử không tồn tại. Dùng các dạng chỉ số phù hợp như:

```sql
FORALL i IN INDICES OF l_ids
    DELETE FROM lab_sessions
    WHERE session_id = l_ids(i);
```

Hoặc VALUES OF với collection chỉ số khi cần chỉ định tập phần tử. Đọc tài liệu PL/SQL FORALL cho cú pháp và giới hạn của loại collection đang dùng. SQL%BULK_ROWCOUNT được truy cập bằng chỉ số iteration tương ứng.

### 13.5. FORALL không thay thế transaction

FORALL giảm chi phí gọi SQL lặp lại; nó không tự COMMIT và không làm toàn bộ batch trở thành transaction độc lập. Các thay đổi vẫn thuộc transaction hiện tại. Caller có thể COMMIT hoặc ROLLBACK theo ranh giới nghiệp vụ.

## 14. FORALL SAVE EXCEPTIONS và SQL%BULK_EXCEPTIONS

Mặc định, lỗi trong một lần thực thi DML của FORALL có thể làm FORALL dừng và phát sinh exception. Khi muốn tiếp tục xử lý các phần tử còn lại và thu thập lỗi, dùng SAVE EXCEPTIONS.

### 14.1. Khai báo exception ORA-24381

SAVE EXCEPTIONS báo lỗi tổng hợp ORA-24381 sau khi các iteration được thử. Có thể đặt tên exception:

```sql
DECLARE
    e_bulk_errors EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_bulk_errors, -24381);
BEGIN
    NULL;
END;
/
```

### 14.2. Ví dụ bulk DML có lỗi một phần tử

Giả sử bảng LAB_BONUSES có EMPLOYEE_ID là khóa ngoại hoặc khóa chính phù hợp. Ví dụ dưới đây minh họa xử lý nhiều ID:

```sql
DECLARE
    TYPE t_ids IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    l_ids t_ids;
    e_bulk_errors EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_bulk_errors, -24381);
BEGIN
    l_ids(1) := 101;
    l_ids(2) := 102;
    l_ids(3) := 103;

    FORALL i IN 1 .. l_ids.COUNT SAVE EXCEPTIONS
        INSERT INTO lab_bonuses (
            employee_id,
            bonus_amount,
            created_at
        )
        VALUES (
            l_ids(i),
            1000,
            SYSTIMESTAMP
        );

    DBMS_OUTPUT.PUT_LINE(
        'Rows inserted = ' || SQL%ROWCOUNT
    );
EXCEPTION
    WHEN e_bulk_errors THEN
        DBMS_OUTPUT.PUT_LINE(
            'Successful rows affected = ' || SQL%ROWCOUNT
        );

        FOR j IN 1 .. SQL%BULK_EXCEPTIONS.COUNT LOOP
            DBMS_OUTPUT.PUT_LINE(
                'Failed iteration = ' ||
                SQL%BULK_EXCEPTIONS(j).ERROR_INDEX ||
                ', Oracle error = ' ||
                SQL%BULK_EXCEPTIONS(j).ERROR_CODE
            );
            DBMS_OUTPUT.PUT_LINE(
                SQLERRM(-SQL%BULK_EXCEPTIONS(j).ERROR_CODE)
            );
        END LOOP;
END;
/
```

Ví dụ chỉ minh họa cấu trúc. Nếu mọi hàng đều hợp lệ và không có lỗi, exception handler không chạy. Nếu có lỗi, SAVE EXCEPTIONS cho phép Oracle tiếp tục các iteration còn lại rồi phát sinh ORA-24381.

### 14.3. SQL%BULK_EXCEPTIONS

Các thuộc tính quan trọng:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| SQL%BULK_EXCEPTIONS.COUNT | Số lỗi được thu thập |
| SQL%BULK_EXCEPTIONS(i).ERROR_INDEX | Chỉ số iteration bị lỗi |
| SQL%BULK_EXCEPTIONS(i).ERROR_CODE | Mã Oracle error dương, không gồm dấu âm |

Để lấy thông báo lỗi, có thể gọi SQLERRM với mã âm: SQLERRM(-ERROR_CODE).

### 14.4. SAVE EXCEPTIONS không tự rollback toàn batch

Với SAVE EXCEPTIONS, các iteration được thực hiện thành công vẫn là thay đổi thuộc transaction hiện tại; iteration lỗi được ghi vào SQL%BULK_EXCEPTIONS. Exception ORA-24381 báo rằng có một hoặc nhiều iteration thất bại, không tự quyết định commit hay rollback các iteration thành công.

Ứng dụng phải chọn chính sách:

- Rollback toàn transaction nếu batch phải nguyên tử.
- Giữ các hàng thành công và ghi nhận lỗi để retry phần thất bại nếu nghiệp vụ cho phép.
- Dùng SAVEPOINT và ranh giới transaction được thiết kế rõ ràng.

Không nuốt ORA-24381 rồi commit mà không kiểm tra SQL%BULK_EXCEPTIONS. Điều đó có thể làm batch hoàn tất một phần mà người gọi tưởng tất cả đều thành công.

### 14.5. Phân biệt SAVE EXCEPTIONS với LOG ERRORS

SAVE EXCEPTIONS là cơ chế xử lý lỗi của FORALL trong PL/SQL. DML error logging (LOG ERRORS INTO ... REJECT LIMIT) là cơ chế SQL ghi một số lỗi DML vào error logging table trong những tình huống được hỗ trợ. Hai cách có mục đích và giới hạn khác nhau; chọn theo yêu cầu batch và cách cần truy vết lỗi.

## 15. FORALL, BULK COLLECT và xử lý theo lô

### 15.1. BULK COLLECT dùng để fetch nhiều hàng

BULK COLLECT lấy nhiều hàng vào collection:

```sql
DECLARE
    TYPE t_ids IS TABLE OF lab_employees.employee_id%TYPE;
    l_ids t_ids;
BEGIN
    SELECT employee_id
    BULK COLLECT INTO l_ids
    FROM lab_employees
    WHERE department_id = 20;

    DBMS_OUTPUT.PUT_LINE(
        'Fetched rows = ' || l_ids.COUNT
    );
END;
/
```

Đây là số phần tử đã fetch vào collection. Nếu SELECT BULK COLLECT không trả hàng, collection rỗng. SQL%ROWCOUNT sau SELECT có thể phản ánh số hàng được fetch; khi cần đếm số phần tử đang có, l_ids.COUNT thể hiện trực tiếp kích thước collection.

### 15.2. Kết hợp BULK COLLECT và FORALL

```sql
DECLARE
    TYPE t_ids IS TABLE OF lab_employees.employee_id%TYPE;
    l_ids t_ids;
    l_rows PLS_INTEGER;
BEGIN
    SELECT employee_id
    BULK COLLECT INTO l_ids
    FROM lab_employees
    WHERE status = 'PENDING';

    IF l_ids.COUNT > 0 THEN
        FORALL i IN 1 .. l_ids.COUNT
            UPDATE lab_employees
            SET status = 'READY'
            WHERE employee_id = l_ids(i);

        l_rows := SQL%ROWCOUNT;
    ELSE
        l_rows := 0;
    END IF;

    DBMS_OUTPUT.PUT_LINE(
        'Rows updated = ' || l_rows
    );
END;
/
```

SELECT BULK COLLECT đưa ID vào collection; FORALL dùng các ID để thực hiện DML hàng loạt. SQL%ROWCOUNT sau FORALL là tổng số hàng bị tác động bởi bulk DML, còn collection.COUNT là số ID được fetch. Hai số này có thể khác nhau nếu một số ID không còn tồn tại hoặc predicate UPDATE không khớp.

### 15.3. Giới hạn bộ nhớ và LIMIT

Với bảng lớn, BULK COLLECT toàn bộ dữ liệu vào collection có thể dùng quá nhiều PGA memory. Dùng cursor fetch theo lô với LIMIT:

```sql
DECLARE
    CURSOR c_pending IS
        SELECT employee_id
        FROM lab_employees
        WHERE status = 'PENDING';

    TYPE t_ids IS TABLE OF lab_employees.employee_id%TYPE;
    l_ids t_ids;
    l_total_updated PLS_INTEGER := 0;
BEGIN
    OPEN c_pending;

    LOOP
        FETCH c_pending BULK COLLECT INTO l_ids LIMIT 500;
        EXIT WHEN l_ids.COUNT = 0;

        FORALL i IN 1 .. l_ids.COUNT
            UPDATE lab_employees
            SET status = 'READY'
            WHERE employee_id = l_ids(i);

        l_total_updated := l_total_updated + SQL%ROWCOUNT;
    END LOOP;

    CLOSE c_pending;

    DBMS_OUTPUT.PUT_LINE(
        'Total updated = ' || l_total_updated
    );
END;
/
```

Mỗi FORALL chỉ xử lý tối đa 500 ID trong ví dụ. Biến l_total_updated cộng số hàng tác động qua từng batch vì SQL%ROWCOUNT chỉ giữ kết quả của FORALL gần nhất.

### 15.4. Chọn batch size

Batch size quá nhỏ làm tăng số lần round-trip nội bộ và overhead; quá lớn có thể dùng nhiều PGA, giữ transaction/undo lâu và làm tăng thời gian rollback. Đo với dữ liệu thực tế, kích thước hàng, chỉ mục và tài nguyên hệ thống. 500 chỉ là con số minh họa, không phải giá trị tối ưu mặc định.

## 16. SQL%ROWCOUNT và transaction

SQL%ROWCOUNT là thông tin về câu SQL vừa thực thi. Nó không cho biết transaction đã commit, có thể rollback hay đã được session khác nhìn thấy.

### 16.1. DML thành công nhưng chưa commit

```sql
BEGIN
    UPDATE lab_accounts
    SET balance = balance - 100
    WHERE account_id = 10;

    DBMS_OUTPUT.PUT_LINE(
        'Rows updated = ' || SQL%ROWCOUNT
    );

    -- Không COMMIT ở đây.
END;
/
```

Nếu UPDATE tác động một hàng, SQL%ROWCOUNT là 1 ngay sau statement. Thay đổi vẫn thuộc transaction hiện tại cho tới khi COMMIT hoặc ROLLBACK. Block kết thúc không tự commit.

### 16.2. Rollback không làm row count trở thành số hàng đã commit

```sql
BEGIN
    UPDATE lab_accounts
    SET balance = balance - 100
    WHERE account_id = 10;

    DBMS_OUTPUT.PUT_LINE(
        'Rows affected before rollback = ' || SQL%ROWCOUNT
    );

    ROLLBACK;
END;
/
```

Row count đã in là số hàng được UPDATE trước khi rollback. Sau ROLLBACK, thay đổi dữ liệu bị hủy, nhưng con số đã in không có nghĩa 1 hàng đã commit. Hãy dùng tên biến và log diễn đạt đúng: rows affected by statement, rows committed hoặc batch status là những khái niệm khác nhau.

### 16.3. Statement-level rollback và transaction rollback

Nếu một DML statement thất bại do constraint hoặc lỗi runtime, Oracle rollback tác động của statement đó. Những DML statement trước đó trong transaction không tự động bị rollback chỉ vì statement sau lỗi. Ứng dụng quyết định rollback toàn transaction, rollback về SAVEPOINT hoặc tiếp tục theo chính sách nghiệp vụ.

Ví dụ:

```sql
BEGIN
    UPDATE lab_accounts
    SET balance = balance - 100
    WHERE account_id = 10;

    -- Giả sử INSERT này vi phạm constraint.
    INSERT INTO lab_payments (
        payment_id, account_id, amount
    )
    VALUES (
        1, 10, -100
    );
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
```

Ví dụ chủ động rollback toàn transaction trong exception handler. Nếu không có ROLLBACK, thay đổi từ statement trước vẫn có thể đang pending trong transaction tùy ngữ cảnh gọi. Không viết exception handler chỉ để in lỗi rồi bỏ qua trạng thái transaction.

### 16.4. SAVEPOINT và row count

SAVEPOINT tạo mốc rollback trong transaction:

```sql
BEGIN
    SAVEPOINT before_batch;

    UPDATE lab_employees
    SET status = 'READY'
    WHERE status = 'PENDING';

    DBMS_OUTPUT.PUT_LINE(
        'Rows changed = ' || SQL%ROWCOUNT
    );

    -- Nếu kiểm tra sau đó thất bại:
    ROLLBACK TO before_batch;
END;
/
```

SQL%ROWCOUNT ở thời điểm in vẫn là số hàng UPDATE. ROLLBACK TO SAVEPOINT hoàn tác các thay đổi sau savepoint nhưng không biến row count đã chụp thành một bộ đếm hàng còn lại trong database.

### 16.5. COMMIT không phải bước xác nhận số hàng

COMMIT kết thúc transaction và làm các thay đổi đủ điều kiện trở nên bền vững. Nó không phải câu SELECT để đếm số hàng đã commit. Nếu ứng dụng cần lưu số hàng của từng DML, chụp SQL%ROWCOUNT trước COMMIT và ghi kết quả vào biến/log theo cùng transaction hoặc theo cơ chế audit được thiết kế rõ ràng.

## 17. Dùng SQL%ROWCOUNT cho kiểm soát nghiệp vụ

### 17.1. Kiểm tra optimistic locking

Một ứng dụng có thể dùng cột VERSION_NO để phát hiện dữ liệu đã bị session khác sửa:

```sql
DECLARE
    l_rows PLS_INTEGER;
BEGIN
    UPDATE lab_documents
    SET document_text = :new_text,
        version_no = version_no + 1,
        updated_at = SYSTIMESTAMP
    WHERE document_id = :document_id
      AND version_no = :expected_version;

    l_rows := SQL%ROWCOUNT;

    IF l_rows = 0 THEN
        RAISE_APPLICATION_ERROR(
            -20021,
            'Document was changed or no longer exists.'
        );
    END IF;
END;
/
```

Nếu row count là 1, hàng có version mong đợi đã được cập nhật. Nếu bằng 0, document có thể không tồn tại hoặc version đã đổi; ứng dụng cần đọc lại trạng thái và báo conflict phù hợp. Điều kiện VERSION_NO trong WHERE là phần bảo vệ concurrency; chỉ đọc SQL%ROWCOUNT sau UPDATE không tự tạo optimistic locking.

### 17.2. Phân biệt không tìm thấy và không đủ điều kiện

Một UPDATE có nhiều predicate:

```sql
UPDATE lab_orders
SET status = 'SHIPPED'
WHERE order_id = :order_id
  AND status = 'PAID';
```

Nếu row count bằng 0, có thể order không tồn tại hoặc order tồn tại nhưng status không phải PAID. Row count không phân biệt hai nguyên nhân. Nếu nghiệp vụ cần thông báo khác nhau, phải truy vấn/kiểm tra thêm theo cách xử lý concurrency an toàn; không suy đoán nguyên nhân từ 0.

### 17.3. Chống xử lý lặp bằng điều kiện DML

Một thao tác đặt trạng thái có thể được thiết kế để lần chạy thứ hai không tác động hàng:

```sql
UPDATE lab_orders
SET status = 'CLOSED',
    closed_at = SYSTIMESTAMP
WHERE order_id = :order_id
  AND status <> 'CLOSED';
```

Lần đầu có thể row count là 1; lần chạy lại sau khi trạng thái đã CLOSED có thể row count là 0. Đây là một pattern idempotent cho việc chuyển trạng thái đơn giản, nhưng cần xử lý NULL, transition hợp lệ, trigger và side effect ngoài database theo nghiệp vụ.

### 17.4. Row count lớn hơn một có thể là tín hiệu sai predicate

Nếu nghiệp vụ kỳ vọng một hàng nhưng UPDATE/DELETE tác động nhiều hàng, hãy coi đó là dấu hiệu cần điều tra:

```sql
UPDATE lab_users
SET locked_flag = 'Y'
WHERE email = :email;

IF SQL%ROWCOUNT > 1 THEN
    RAISE_APPLICATION_ERROR(
        -20022,
        'Email is not unique; more than one user was updated.'
    );
END IF;
```

Tốt hơn hết là bảo vệ uniqueness bằng constraint phù hợp. Kiểm tra row count là lớp kiểm soát bổ sung, không thay thế ràng buộc dữ liệu.

### 17.5. Đừng dùng SELECT COUNT(*) thay cho row count của DML

Nếu chỉ cần biết UPDATE vừa tác động bao nhiêu hàng, đọc SQL%ROWCOUNT ngay sau UPDATE. Chạy thêm SELECT COUNT(*) sau đó vừa tốn truy vấn, vừa có thể đếm tập dữ liệu khác do transaction/concurrency hoặc predicate khác. Nếu cần số hàng còn tồn tại sau thao tác, đó là câu hỏi riêng và cần query riêng.

## 18. Bài thực hành tổng hợp

Các ví dụ sau chạy trong schema lab. Tạo bảng và sequence một lần; nếu tên đã tồn tại, dùng schema thử nghiệm mới hoặc dọn dữ liệu theo quy trình của bạn.

### 18.1. Tạo bảng và dữ liệu mẫu

```sql
CREATE TABLE lab_employee_dml (
    employee_id NUMBER(10)
        CONSTRAINT pk_lab_employee_dml PRIMARY KEY,
    employee_name VARCHAR2(100) NOT NULL,
    department_id NUMBER(5),
    status VARCHAR2(20),
    salary NUMBER(12, 2),
    version_no NUMBER(10) DEFAULT 1 NOT NULL
);

CREATE SEQUENCE lab_employee_dml_seq
START WITH 1000
INCREMENT BY 1;

INSERT INTO lab_employee_dml VALUES
(101, 'An Nguyen', 10, 'ACTIVE', 20000, 1);
INSERT INTO lab_employee_dml VALUES
(102, 'Binh Tran', 10, 'ACTIVE', 22000, 1);
INSERT INTO lab_employee_dml VALUES
(103, 'Chi Le', 20, 'PENDING', 24000, 1);
INSERT INTO lab_employee_dml VALUES
(104, 'Dung Pham', 20, 'PENDING', 26000, 1);

COMMIT;
```

### 18.2. UPDATE và chụp row count

```sql
DECLARE
    l_rows PLS_INTEGER;
BEGIN
    UPDATE lab_employee_dml
    SET salary = salary * 1.05
    WHERE department_id = 10;

    l_rows := SQL%ROWCOUNT;

    DBMS_OUTPUT.PUT_LINE('Updated = ' || l_rows);
END;
/
```

Kết quả mong đợi với dữ liệu mẫu: 2 hàng được UPDATE.

### 18.3. Thử predicate không khớp

```sql
BEGIN
    DELETE FROM lab_employee_dml
    WHERE employee_id = -1;

    DBMS_OUTPUT.PUT_LINE(
        'Deleted = ' || SQL%ROWCOUNT
    );
END;
/
```

Kết quả mong đợi: 0, không phát sinh NO_DATA_FOUND.

### 18.4. INSERT ... SELECT và row count

```sql
DECLARE
    l_rows PLS_INTEGER;
BEGIN
    INSERT INTO lab_employee_archive (
        employee_id,
        employee_name,
        archived_at
    )
    SELECT
        employee_id,
        employee_name,
        SYSTIMESTAMP
    FROM lab_employee_dml
    WHERE status = 'INACTIVE';

    l_rows := SQL%ROWCOUNT;
    DBMS_OUTPUT.PUT_LINE('Archived = ' || l_rows);
END;
/
```

Tạo bảng LAB_EMPLOYEE_ARCHIVE phù hợp trước khi chạy. Với dữ liệu mẫu hiện tại chưa có hàng INACTIVE, row count dự kiến là 0.

### 18.5. MERGE và tổng số hàng

```sql
DECLARE
    l_rows PLS_INTEGER;
BEGIN
    MERGE INTO lab_employee_dml t
    USING (
        SELECT 101 AS employee_id, 'ACTIVE' AS status FROM dual
        UNION ALL
        SELECT 105, 'ACTIVE' FROM dual
    ) s
    ON (t.employee_id = s.employee_id)
    WHEN MATCHED THEN
        UPDATE SET t.status = s.status
    WHEN NOT MATCHED THEN
        INSERT (
            employee_id, employee_name, status,
            salary, version_no
        )
        VALUES (
            s.employee_id, 'New Employee', s.status,
            18000, 1
        );

    l_rows := SQL%ROWCOUNT;
    DBMS_OUTPUT.PUT_LINE('MERGE affected = ' || l_rows);
END;
/
```

Với source có hai hàng, một hàng match và một hàng không match, tổng số hàng bị tác động dự kiến là 2. SQL%ROWCOUNT không tách riêng một UPDATE và một INSERT.

### 18.6. Procedure trả OUT row count

```sql
CREATE OR REPLACE PROCEDURE set_department_status (
    p_department_id IN NUMBER,
    p_status        IN VARCHAR2,
    p_rows          OUT PLS_INTEGER
)
AS
BEGIN
    UPDATE lab_employee_dml
    SET status = p_status
    WHERE department_id = p_department_id;

    p_rows := SQL%ROWCOUNT;
END;
/

DECLARE
    l_rows PLS_INTEGER;
BEGIN
    set_department_status(20, 'ACTIVE', l_rows);
    DBMS_OUTPUT.PUT_LINE('Procedure changed = ' || l_rows);
END;
/
```

### 18.7. Kiểm tra kết quả

```sql
SELECT
    department_id,
    status,
    COUNT(*) AS employee_count
FROM lab_employee_dml
GROUP BY department_id, status
ORDER BY department_id, status;
```

So sánh số hàng DML báo cáo với trạng thái dữ liệu sau khi COMMIT. Nếu chưa commit, kết quả trong cùng session vẫn thấy thay đổi của chính session; session khác có thể chưa thấy.

## 19. Các lỗi và bẫy thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| SQL%ROWCOUNT in ra 1 dù UPDATE nhiều hàng | Có SELECT INTO hoặc INSERT log chạy sau UPDATE | Lưu row count ngay sau DML |
| UPDATE 0 hàng nhưng không có exception | Đây là hành vi bình thường của DML | Kiểm tra SQL%ROWCOUNT = 0 và xử lý nghiệp vụ |
| SELECT INTO không tìm thấy hàng | SELECT INTO phát sinh NO_DATA_FOUND | Bắt exception hoặc dùng cursor/aggregate phù hợp |
| SQL%ROWCOUNT sau procedure không đúng DML caller | Procedure con đã thực hiện SQL khác | Trả OUT parameter hoặc chụp trước khi gọi |
| MERGE row count không tách INSERT/UPDATE | SQL%ROWCOUNT chỉ là tổng số hàng tác động | Thiết kế audit/đo riêng nếu thật sự cần |
| SQL%ROWCOUNT sau FORALL chỉ là tổng | Đang đọc tổng thay vì từng iteration | Dùng SQL%BULK_ROWCOUNT(i) |
| FORALL dừng khi có lỗi | Không dùng SAVE EXCEPTIONS | Dùng SAVE EXCEPTIONS nếu cần tiếp tục và xử lý SQL%BULK_EXCEPTIONS |
| Batch lỗi một phần nhưng bị coi thành công | Nuốt ORA-24381 mà không kiểm tra lỗi | Kiểm tra toàn bộ SQL%BULK_EXCEPTIONS và quyết định commit/rollback |
| SQL%ROWCOUNT bị mất sau câu SQL khác | Thuộc tính chỉ mô tả câu SQL gần nhất | Copy vào biến PL/SQL |
| Row count là 1 nhưng transaction rollback | Row count đo statement, không đo commit | Log rõ rows affected và transaction outcome |
| DML 0 hàng bị coi là lỗi database | Nhầm với SELECT INTO | Phân biệt semantics DML và SELECT INTO |
| DML cập nhật cùng giá trị vẫn đếm hàng | Row count đếm hàng được statement tác động | Đưa điều kiện khác biệt vào WHERE nếu cần |
| Dynamic DML có SQL injection | Nối input vào SQL text | Bind giá trị; whitelist/DBMS_ASSERT cho identifier |
| Bulk collect dùng quá nhiều bộ nhớ | Fetch toàn bộ dữ liệu lớn vào collection | Dùng LIMIT và xử lý theo batch |
| Dùng SQL%ROWCOUNT để đếm cursor fetch | Nhầm implicit và explicit cursor | Dùng cursor_name%ROWCOUNT hoặc biến đếm |

## 20. Nguyên tắc thực hành tốt

1. **Chụp row count ngay sau DML.** Gán SQL%ROWCOUNT vào biến trước SELECT, logging hoặc procedure call.
2. **Dùng tên biến mô tả đúng nghĩa.** Ví dụ l_rows_updated hoặc l_rows_deleted, không dùng một biến chung khó hiểu.
3. **Xử lý 0 hàng theo nghiệp vụ.** DML 0 hàng không tự là lỗi; xác định đó là bình thường, conflict hay record không tồn tại.
4. **Kiểm tra số hàng kỳ vọng.** Nếu phải tác động đúng một hàng, kiểm tra bằng SQL%ROWCOUNT và bảo vệ uniqueness bằng constraint.
5. **Không nhầm row count với commit.** Chỉ COMMIT/ROLLBACK mới quyết định transaction.
6. **Dùng OUT parameter cho procedure.** Đừng bắt caller phụ thuộc implicit cursor state sau lời gọi.
7. **Dùng RETURNING INTO khi cần giá trị hàng vừa thay đổi.** Tránh SELECT lại nếu DML đã có thể trả dữ liệu.
8. **Dùng bind variable cho dynamic SQL.** Xác thực identifier bằng whitelist hoặc DBMS_ASSERT.
9. **Dùng FORALL cho bulk DML phù hợp.** Đọc tổng bằng SQL%ROWCOUNT, từng iteration bằng SQL%BULK_ROWCOUNT.
10. **Xử lý SAVE EXCEPTIONS có chủ đích.** Không bỏ qua lỗi bulk; quyết định batch nguyên tử hay chấp nhận thành công một phần.
11. **Giới hạn BULK COLLECT theo batch.** Tránh dùng PGA không kiểm soát.
12. **Tách SQL%ROWCOUNT và cursor_name%ROWCOUNT.** Một cái theo implicit SQL statement, một cái theo số hàng explicit cursor đã fetch.
13. **Không suy ra nguyên nhân từ row count 0.** Có thể không tồn tại hàng hoặc predicate không thỏa.
14. **Ghi log số hàng đúng thời điểm.** Log nên phân biệt attempted/affected/committed/failed nếu hệ thống cần các trạng thái đó.

## 21. Câu hỏi tự kiểm tra

1. DML là gì? Những câu lệnh DML nào thường dùng trong PL/SQL?
2. SQL%ROWCOUNT trả về điều gì?
3. Vì sao phải đọc SQL%ROWCOUNT ngay sau DML?
4. SQL%FOUND và SQL%NOTFOUND khác SQL%ROWCOUNT ở điểm nào?
5. Vì sao SQL%ISOPEN luôn FALSE với implicit cursor SQL?
6. UPDATE không khớp hàng nào có phát sinh NO_DATA_FOUND không?
7. INSERT ... SELECT không trả hàng khác SELECT INTO không tìm thấy hàng như thế nào?
8. Nếu UPDATE khớp một hàng nhưng gán lại cùng giá trị, SQL%ROWCOUNT thường là bao nhiêu?
9. MERGE có cả UPDATE và INSERT thì SQL%ROWCOUNT biểu thị điều gì?
10. Vì sao SQL%ROWCOUNT không tách riêng số hàng INSERT và UPDATE trong MERGE?
11. Sau UPDATE, chạy SELECT INTO rồi đọc SQL%ROWCOUNT sẽ gặp vấn đề gì?
12. Vì sao procedure nên trả row count qua OUT parameter?
13. RETURNING INTO khác việc SELECT lại sau DML như thế nào?
14. SQL%ROWCOUNT có báo transaction đã commit không?
15. Explicit cursor dùng thuộc tính nào để đếm số hàng đã FETCH?
16. Dynamic DML dùng EXECUTE IMMEDIATE có thể đọc SQL%ROWCOUNT không?
17. FORALL khác vòng lặp FOR thông thường như thế nào?
18. SQL%BULK_ROWCOUNT(i) và SQL%ROWCOUNT sau FORALL khác nhau ra sao?
19. SAVE EXCEPTIONS và SQL%BULK_EXCEPTIONS dùng để làm gì?
20. Vì sao cần LIMIT khi BULK COLLECT trên tập dữ liệu lớn?
21. Nếu SQL%ROWCOUNT bằng 0 sau optimistic update, có thể có những nguyên nhân nào?
22. Vì sao cần phân biệt rows affected với rows committed trong log?

## 22. Mô hình ghi nhớ

```text
DML TRONG PL/SQL
   |
   +-- INSERT
   +-- UPDATE
   +-- DELETE
   +-- MERGE
   |
   v
IMPLICIT SQL CURSOR
   |
   +-- SQL%ROWCOUNT : số hàng của SQL gần nhất
   +-- SQL%FOUND    : có hàng được tác động/trả về?
   +-- SQL%NOTFOUND: không có hàng?
   +-- SQL%ISOPEN  : luôn FALSE
   |
   v
CHỤP NGAY SAU DML
   |
   +-- Gán vào biến
   +-- Dùng OUT parameter khi trả khỏi procedure
   +-- RETURNING INTO để lấy giá trị hàng
   |
   v
BULK DML
   |
   +-- FORALL
   +-- SQL%ROWCOUNT: tổng hàng bị tác động
   +-- SQL%BULK_ROWCOUNT(i): từng iteration
   +-- SAVE EXCEPTIONS / SQL%BULK_EXCEPTIONS
   |
   v
TRANSACTION
   |
   +-- DML không tự COMMIT
   +-- Row count không phải commit status
   +-- Caller quyết định COMMIT / ROLLBACK
```

**Điểm cần nhớ:** SQL%ROWCOUNT là kết quả của câu SQL gần nhất, không phải bộ đếm lịch sử và không phải xác nhận commit. Hãy lưu giá trị ngay sau DML, dùng OUT parameter để truyền kết quả qua procedure, và dùng SQL%BULK_ROWCOUNT khi cần biết từng lần thực thi trong FORALL. Luôn tách số hàng bị tác động khỏi kết quả transaction cuối cùng.
