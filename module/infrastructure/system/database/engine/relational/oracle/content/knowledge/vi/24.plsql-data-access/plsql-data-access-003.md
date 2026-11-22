# Implicit cursor và các thuộc tính SQL%FOUND/NOTFOUND/ISOPEN

Mỗi khi PL/SQL thực thi một câu lệnh SQL thuộc phạm vi mà PL/SQL quản lý, Oracle sử dụng một implicit cursor (con trỏ ngầm) có tên SQL. Lập trình viên không cần khai báo, OPEN, FETCH hoặc CLOSE con trỏ này. Sau khi câu lệnh hoàn tất, có thể dùng các thuộc tính của SQL để biết câu lệnh có tác động tới hàng nào và đã xử lý bao nhiêu hàng.

Bốn thuộc tính thường dùng:

- SQL%FOUND: cho biết câu SQL gần nhất có tác động hoặc trả về ít nhất một hàng hay không.
- SQL%NOTFOUND: cho biết câu SQL gần nhất không tác động hoặc không trả về hàng nào hay không.
- SQL%ISOPEN: cho biết implicit cursor có đang mở hay không; với SQL cursor, thuộc tính này luôn FALSE sau khi câu lệnh hoàn tất.
- SQL%ROWCOUNT: số hàng được câu SQL gần nhất xử lý.

Các thuộc tính này đặc biệt hữu ích sau INSERT, UPDATE, DELETE, MERGE và SELECT INTO. Điểm quan trọng nhất là chúng luôn phản ánh câu SQL gần nhất. Nếu chạy thêm một câu SQL khác, giá trị cần dùng có thể bị thay thế. Vì vậy, hãy đọc hoặc lưu thuộc tính ngay sau câu lệnh mà bạn muốn kiểm tra.

## 1. Implicit cursor là gì?

Cursor là cơ chế để PL/SQL làm việc với kết quả của câu truy vấn SQL. Có hai cách sử dụng phổ biến:

1. Implicit cursor: Oracle tự quản lý khi chạy SQL statement trong PL/SQL.
2. Explicit cursor: lập trình viên khai báo cursor, sau đó chủ động OPEN, FETCH và CLOSE hoặc dùng cursor FOR loop.

Ví dụ implicit cursor:

~~~sql
BEGIN
    UPDATE employees
    SET salary = salary * 1.05
    WHERE department_id = 10;

    DBMS_OUTPUT.PUT_LINE('Rows updated: ' || SQL%ROWCOUNT);
END;
/
~~~

Oracle tự tạo và quản lý cursor cho câu UPDATE. Không cần khai báo tên cursor hay gọi OPEN/CLOSE.

### 1.1 Vòng đời của implicit cursor

Với một câu SQL được thực thi:

1. Oracle mở implicit cursor để thực thi câu lệnh.
2. Oracle xử lý câu lệnh và xác định kết quả hoặc số hàng bị tác động.
3. Câu lệnh hoàn tất.
4. Oracle tự đóng implicit cursor.
5. PL/SQL có thể đọc các thuộc tính SQL% để lấy trạng thái và số hàng của câu lệnh vừa chạy.

Sơ đồ khái quát:

~~~text
PL/SQL executes SQL statement
            |
            v
Oracle opens implicit cursor
            |
            v
Execute / process rows
            |
            v
Statement completes
            |
            v
Oracle closes implicit cursor
            |
            v
Read SQL%FOUND / NOTFOUND / ISOPEN / ROWCOUNT
~~~

Lập trình viên không thể giữ implicit cursor mở để FETCH từng hàng như explicit cursor. Nếu truy vấn trả về nhiều hàng, hãy dùng cursor FOR loop, explicit cursor hoặc BULK COLLECT tùy yêu cầu.

### 1.2 SQL là tên cursor ngầm

Trong PL/SQL, SQL là tên cursor ngầm do Oracle cung cấp. Không khai báo biến tên SQL và không viết:

~~~sql
OPEN SQL;
FETCH SQL INTO ...;
CLOSE SQL;
~~~

Đây không phải cách sử dụng implicit cursor. Chỉ truy cập các thuộc tính:

~~~sql
SQL%FOUND
SQL%NOTFOUND
SQL%ISOPEN
SQL%ROWCOUNT
~~~

## 2. SQL%FOUND

SQL%FOUND trả về BOOLEAN:

- TRUE nếu câu SQL gần nhất tác động hoặc trả về ít nhất một hàng.
- FALSE nếu câu SQL gần nhất không tác động hoặc không trả về hàng nào.
- NULL nếu chưa có câu SQL nào được thực thi trong phạm vi trạng thái đang xét.

Ví dụ UPDATE có hàng phù hợp:

~~~sql
BEGIN
    UPDATE employees
    SET salary = salary + 100
    WHERE employee_id = 1001;

    IF SQL%FOUND THEN
        DBMS_OUTPUT.PUT_LINE('Employee was updated.');
    ELSE
        DBMS_OUTPUT.PUT_LINE('No employee matched.');
    END IF;
END;
/
~~~

Nếu EMPLOYEE_ID 1001 tồn tại và UPDATE tác động một hàng, SQL%FOUND là TRUE.

### 2.1 SQL%FOUND với UPDATE không tìm thấy hàng

UPDATE không khớp hàng nào vẫn là một câu lệnh SQL thực thi thành công. Oracle không phát sinh exception chỉ vì số hàng cập nhật bằng 0.

~~~sql
BEGIN
    UPDATE employees
    SET salary = salary + 100
    WHERE employee_id = -999;

    IF SQL%FOUND THEN
        DBMS_OUTPUT.PUT_LINE('At least one row updated.');
    ELSE
        DBMS_OUTPUT.PUT_LINE('No row updated.');
    END IF;
END;
/
~~~

Trong ví dụ này, SQL%FOUND là FALSE và SQL%ROWCOUNT là 0.

### 2.2 SQL%FOUND sau INSERT

INSERT ... VALUES thành công sẽ tác động một hàng:

~~~sql
BEGIN
    INSERT INTO departments(department_id, department_name)
    VALUES (900, 'Training');

    IF SQL%FOUND THEN
        DBMS_OUTPUT.PUT_LINE('Insert affected a row.');
    END IF;
END;
/
~~~

Nếu INSERT thành công, SQL%FOUND là TRUE và SQL%ROWCOUNT bằng 1.

Nếu INSERT ... SELECT không tạo ra hàng nào vì SELECT nguồn rỗng, câu INSERT có thể hoàn tất nhưng không thêm hàng; khi đó SQL%FOUND là FALSE và SQL%ROWCOUNT bằng 0.

### 2.3 SQL%FOUND sau DELETE

~~~sql
BEGIN
    DELETE FROM employees
    WHERE department_id = -999;

    IF SQL%FOUND THEN
        DBMS_OUTPUT.PUT_LINE('At least one employee deleted.');
    ELSE
        DBMS_OUTPUT.PUT_LINE('No employee matched the DELETE.');
    END IF;
END;
/
~~~

Nếu không có hàng phù hợp, DELETE không báo lỗi; SQL%FOUND là FALSE.

### 2.4 SQL%FOUND là BOOLEAN, không phải chuỗi

Không so sánh với chuỗi:

~~~sql
-- Không đúng:
IF SQL%FOUND = 'TRUE' THEN
    NULL;
END IF;
~~~

Sử dụng trực tiếp trong điều kiện PL/SQL:

~~~sql
IF SQL%FOUND THEN
    ...
END IF;
~~~

SQL%FOUND có thể là NULL nếu chưa có SQL statement nào được thực thi. Trong PL/SQL, IF chỉ đi vào nhánh THEN khi điều kiện là TRUE; FALSE hoặc NULL đều không đi vào nhánh đó.

## 3. SQL%NOTFOUND

SQL%NOTFOUND là thuộc tính đối nghịch với SQL%FOUND:

- TRUE nếu câu SQL gần nhất không tác động hoặc không trả về hàng nào.
- FALSE nếu câu SQL gần nhất tác động hoặc trả về ít nhất một hàng.
- NULL nếu chưa có câu SQL nào được thực thi.

Ví dụ:

~~~sql
BEGIN
    DELETE FROM employees
    WHERE employee_id = 1001;

    IF SQL%NOTFOUND THEN
        DBMS_OUTPUT.PUT_LINE('Employee does not exist.');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Employee deleted.');
    END IF;
END;
/
~~~

### 3.1 SQL%NOTFOUND không có nghĩa câu SQL thất bại

Tên thuộc tính dễ gây hiểu nhầm. SQL%NOTFOUND = TRUE chỉ có nghĩa không có hàng nào được tác động hoặc trả về. Nó không có nghĩa câu lệnh gặp lỗi.

Ví dụ:

~~~sql
UPDATE employees
SET salary = salary + 500
WHERE employee_id = -1;
~~~

Câu lệnh chạy thành công, không có exception, nhưng SQL%NOTFOUND là TRUE. Nếu câu UPDATE vi phạm CHECK constraint hoặc lỗi trigger, Oracle phát sinh exception; luồng điều khiển chuyển sang exception handler thay vì chạy tiếp đến câu IF thông thường.

### 3.2 Dùng NOTFOUND để phát hiện DELETE không có hàng

~~~sql
DECLARE
    l_deleted PLS_INTEGER;
BEGIN
    DELETE FROM employees
    WHERE employee_id = 1001;

    IF SQL%NOTFOUND THEN
        DBMS_OUTPUT.PUT_LINE('Nothing was deleted.');
    ELSE
        l_deleted := SQL%ROWCOUNT;
        DBMS_OUTPUT.PUT_LINE('Deleted rows: ' || l_deleted);
    END IF;
END;
/
~~~

Ở ví dụ này, SQL%ROWCOUNT được đọc ngay sau DELETE trong nhánh ELSE, trước khi có câu SQL khác.

### 3.3 Quan hệ giữa FOUND và NOTFOUND

Khi thuộc tính đã có trạng thái TRUE/FALSE:

| SQL%FOUND | SQL%NOTFOUND |
|---|---|
| TRUE | FALSE |
| FALSE | TRUE |

Trước khi thực thi SQL, cả hai có thể là NULL. Vì vậy, không nên dùng phép so sánh để suy luận rằng chúng luôn là hai giá trị boolean đối nghịch đã xác định.

## 4. SQL%ISOPEN

SQL%ISOPEN cho biết implicit cursor SQL có đang mở hay không. Với implicit cursor, thuộc tính này luôn trả về FALSE khi PL/SQL có thể kiểm tra sau khi câu lệnh hoàn tất, vì Oracle tự đóng cursor sau khi thực thi.

Ví dụ:

~~~sql
BEGIN
    UPDATE employees
    SET salary = salary + 100
    WHERE employee_id = 1001;

    IF SQL%ISOPEN THEN
        DBMS_OUTPUT.PUT_LINE('Implicit cursor is open.');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Implicit cursor is closed.');
    END IF;
END;
/
~~~

Kết quả là nhánh cursor closed. Đây là hành vi bình thường.

### 4.1 Không dùng SQL%ISOPEN để kiểm tra SELECT có dữ liệu

Một hiểu nhầm thường gặp:

~~~sql
IF SQL%ISOPEN THEN
    DBMS_OUTPUT.PUT_LINE('Query returned rows.');
END IF;
~~~

Điều kiện trên không kiểm tra truy vấn có trả về hàng hay không. Implicit cursor đã được Oracle đóng sau khi câu SQL hoàn tất.

Để kiểm tra DML có tác động hàng, dùng SQL%FOUND hoặc SQL%ROWCOUNT. Với SELECT INTO, xử lý NO_DATA_FOUND và TOO_MANY_ROWS. Với truy vấn nhiều hàng, dùng cursor phù hợp.

### 4.2 SQL%ISOPEN khác cursor_name%ISOPEN

Explicit cursor có vòng đời do chương trình điều khiển:

~~~sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id
        FROM employees;
BEGIN
    OPEN c_employees;

    IF c_employees%ISOPEN THEN
        DBMS_OUTPUT.PUT_LINE('Explicit cursor is open.');
    END IF;

    CLOSE c_employees;
END;
/
~~~

Ở đây c_employees%ISOPEN có thể TRUE giữa OPEN và CLOSE. Điều này khác với SQL%ISOPEN của implicit cursor.

## 5. SQL%ROWCOUNT

SQL%ROWCOUNT trả về số hàng được câu SQL gần nhất xử lý. Đây thường là thuộc tính hữu ích nhất khi cần kiểm tra kết quả DML.

Ví dụ:

~~~sql
DECLARE
    l_rows_updated PLS_INTEGER;
BEGIN
    UPDATE employees
    SET salary = salary * 1.10
    WHERE department_id = 10;

    l_rows_updated := SQL%ROWCOUNT;

    DBMS_OUTPUT.PUT_LINE(
        'Updated rows: ' || l_rows_updated
    );
END;
/
~~~

Nếu có 25 nhân viên thuộc department 10, SQL%ROWCOUNT bằng 25.

### 5.1 SQL%ROWCOUNT bằng 0 không phải exception

~~~sql
BEGIN
    UPDATE employees
    SET salary = salary + 100
    WHERE employee_id = -999;

    DBMS_OUTPUT.PUT_LINE(
        'Affected rows: ' || SQL%ROWCOUNT
    );
END;
/
~~~

Nếu không có employee phù hợp, câu lệnh vẫn chạy thành công và in 0.

Nếu nghiệp vụ yêu cầu bắt buộc cập nhật đúng một hàng:

~~~sql
DECLARE
    l_rows PLS_INTEGER;
BEGIN
    UPDATE employees
    SET salary = salary + 100
    WHERE employee_id = 1001;

    l_rows := SQL%ROWCOUNT;

    IF l_rows <> 1 THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Expected exactly one employee row to be updated'
        );
    END IF;
END;
/
~~~

Lưu ý: ví dụ chỉ minh họa kiểm tra row count. Ứng dụng thực tế cần xác định transaction có phải rollback khi lỗi nghiệp vụ hay không và ai sở hữu quyết định COMMIT.

### 5.2 SQL%ROWCOUNT sau INSERT

INSERT một hàng:

~~~sql
BEGIN
    INSERT INTO departments(department_id, department_name)
    VALUES (901, 'Operations');

    DBMS_OUTPUT.PUT_LINE(SQL%ROWCOUNT);
END;
/
~~~

Kết quả là 1 nếu INSERT thành công.

INSERT nhiều hàng bằng INSERT ... SELECT:

~~~sql
BEGIN
    INSERT INTO employee_archive (
        employee_id,
        employee_name,
        department_id
    )
    SELECT employee_id,
           employee_name,
           department_id
    FROM employees
    WHERE status = 'INACTIVE';

    DBMS_OUTPUT.PUT_LINE(
        'Inserted rows: ' || SQL%ROWCOUNT
    );
END;
/
~~~

SQL%ROWCOUNT cho biết số hàng được INSERT bởi câu lệnh. Nếu SELECT nguồn không trả hàng, số lượng là 0.

### 5.3 SQL%ROWCOUNT sau DELETE

~~~sql
BEGIN
    DELETE FROM employee_archive
    WHERE archived_at < DATE '2020-01-01';

    DBMS_OUTPUT.PUT_LINE(
        'Deleted rows: ' || SQL%ROWCOUNT
    );
END;
/
~~~

Số hàng bị xóa được trả về ngay sau DELETE.

### 5.4 SQL%ROWCOUNT sau MERGE

MERGE có thể INSERT hoặc UPDATE các hàng theo điều kiện match. SQL%ROWCOUNT cho biết tổng số hàng bị tác động bởi câu MERGE, không phải chỉ số hàng INSERT hoặc chỉ số hàng UPDATE riêng lẻ.

~~~sql
BEGIN
    MERGE INTO employee_summary target
    USING employee_stage source
       ON (target.employee_id = source.employee_id)
    WHEN MATCHED THEN
        UPDATE SET target.salary = source.salary
    WHEN NOT MATCHED THEN
        INSERT (employee_id, salary)
        VALUES (source.employee_id, source.salary);

    DBMS_OUTPUT.PUT_LINE(
        'Rows affected by MERGE: ' || SQL%ROWCOUNT
    );
END;
/
~~~

Nếu cần tách số hàng INSERT và UPDATE, SQL%ROWCOUNT đơn lẻ không cung cấp hai con số riêng. Hãy thiết kế cách đo phù hợp, chẳng hạn nguồn staging có cờ phân loại, audit, hoặc quy trình DML tách riêng khi yêu cầu báo cáo cần chính xác từng nhóm.

### 5.5 SQL%ROWCOUNT sau SELECT INTO

SELECT ... INTO là truy vấn một hàng. Khi truy vấn trả đúng một hàng, câu lệnh thành công và SQL%ROWCOUNT là 1:

~~~sql
DECLARE
    l_name employees.employee_name%TYPE;
BEGIN
    SELECT employee_name
    INTO l_name
    FROM employees
    WHERE employee_id = 1001;

    DBMS_OUTPUT.PUT_LINE('Rows fetched: ' || SQL%ROWCOUNT);
END;
/
~~~

Không dùng SELECT INTO như một cursor nhiều hàng. Nếu không có hàng, Oracle phát sinh NO_DATA_FOUND; nếu có nhiều hơn một hàng, Oracle phát sinh TOO_MANY_ROWS. Hãy xử lý các exception đó thay vì mong câu lệnh tiếp tục đến một câu IF kiểm tra SQL%NOTFOUND.

### 5.6 SQL%ROWCOUNT sau SELECT aggregate

Aggregate không có GROUP BY thường trả một hàng ngay cả khi nguồn không có hàng:

~~~sql
DECLARE
    l_count PLS_INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO l_count
    FROM employees
    WHERE department_id = -999;

    DBMS_OUTPUT.PUT_LINE('Count value: ' || l_count);
    DBMS_OUTPUT.PUT_LINE('Rows fetched: ' || SQL%ROWCOUNT);
END;
/
~~~

Ở đây COUNT(*) trả giá trị 0, nhưng SELECT INTO vẫn lấy được một hàng kết quả. Do đó SQL%ROWCOUNT là 1. Cần phân biệt:

- SQL%ROWCOUNT: số hàng kết quả mà câu SELECT INTO lấy được.
- l_count: giá trị COUNT(*) trong hàng kết quả, có thể bằng 0.

Hai con số trả lời hai câu hỏi khác nhau.

### 5.7 SQL%ROWCOUNT và SELECT BULK COLLECT INTO

SELECT BULK COLLECT INTO lấy nhiều hàng vào collection và không phát sinh NO_DATA_FOUND chỉ vì kết quả rỗng:

~~~sql
DECLARE
    TYPE t_employee_ids IS TABLE OF employees.employee_id%TYPE;
    l_employee_ids t_employee_ids;
BEGIN
    SELECT employee_id
    BULK COLLECT INTO l_employee_ids
    FROM employees
    WHERE department_id = -999;

    DBMS_OUTPUT.PUT_LINE(
        'Rows fetched: ' || SQL%ROWCOUNT
    );
    DBMS_OUTPUT.PUT_LINE(
        'Collection count: ' || l_employee_ids.COUNT
    );
END;
/
~~~

Nếu không có hàng, collection rỗng và SQL%ROWCOUNT bằng 0. Đây là trường hợp khác với SELECT COUNT(*) INTO một biến, vì COUNT vẫn trả một hàng kết quả.

## 6. Các thuộc tính SQL% luôn phản ánh câu SQL gần nhất

Đây là quy tắc quan trọng nhất khi dùng implicit cursor.

~~~sql
BEGIN
    UPDATE employees
    SET salary = salary + 100
    WHERE department_id = 10;

    -- SQL%ROWCOUNT ở đây là số hàng UPDATE.
    DBMS_OUTPUT.PUT_LINE('Updated: ' || SQL%ROWCOUNT);

    DELETE FROM employee_archive
    WHERE department_id = 10;

    -- SQL%ROWCOUNT bây giờ là số hàng DELETE,
    -- không còn là số hàng UPDATE.
    DBMS_OUTPUT.PUT_LINE('Deleted: ' || SQL%ROWCOUNT);
END;
/
~~~

Nếu cần dùng số hàng UPDATE ở cuối block, phải lưu ngay sau UPDATE:

~~~sql
DECLARE
    l_updated_rows PLS_INTEGER;
    l_deleted_rows PLS_INTEGER;
BEGIN
    UPDATE employees
    SET salary = salary + 100
    WHERE department_id = 10;

    l_updated_rows := SQL%ROWCOUNT;

    DELETE FROM employee_archive
    WHERE department_id = 10;

    l_deleted_rows := SQL%ROWCOUNT;

    DBMS_OUTPUT.PUT_LINE('Updated=' || l_updated_rows);
    DBMS_OUTPUT.PUT_LINE('Deleted=' || l_deleted_rows);
END;
/
~~~

### 6.1 Đọc thuộc tính trước câu SQL tiếp theo

Không nên:

~~~sql
UPDATE employees
SET salary = salary + 100
WHERE department_id = 10;

SELECT COUNT(*)
INTO l_count
FROM employees;

-- SQL%ROWCOUNT ở đây thuộc SELECT COUNT(*), không còn thuộc UPDATE.
DBMS_OUTPUT.PUT_LINE(SQL%ROWCOUNT);
~~~

Nếu cần số hàng UPDATE, chụp ngay sau UPDATE:

~~~sql
UPDATE employees
SET salary = salary + 100
WHERE department_id = 10;

l_updated_rows := SQL%ROWCOUNT;

SELECT COUNT(*)
INTO l_count
FROM employees;
~~~

### 6.2 Procedure được gọi cũng có thể thực thi SQL

Khi một procedure con thực hiện SQL, trạng thái implicit cursor có thể thay đổi. Nếu caller cần giữ số hàng của câu DML trước khi gọi procedure con, hãy lưu vào biến cục bộ trước lời gọi.

~~~sql
UPDATE employees
SET salary = salary + 100
WHERE department_id = 10;

l_rows_updated := SQL%ROWCOUNT;

write_audit_log(...);

-- Dùng l_rows_updated, không đọc lại SQL%ROWCOUNT
-- vì procedure log có thể đã chạy SQL khác.
~~~

Đây là lý do code nên chụp thuộc tính ngay tại nơi thực hiện DML thay vì đọc chúng ở một vị trí xa hơn.

## 7. Kết hợp FOUND, NOTFOUND và ROWCOUNT

Các thuộc tính có thể được dùng cùng nhau:

~~~sql
DECLARE
    l_rows PLS_INTEGER;
BEGIN
    UPDATE employees
    SET salary = salary * 1.05
    WHERE department_id = 10;

    l_rows := SQL%ROWCOUNT;

    IF SQL%FOUND THEN
        DBMS_OUTPUT.PUT_LINE(
            'Updated ' || l_rows || ' employees.'
        );
    ELSIF SQL%NOTFOUND THEN
        DBMS_OUTPUT.PUT_LINE('No employees matched.');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Cursor state is unknown.');
    END IF;
END;
/
~~~

Trong ví dụ, UPDATE đã chạy trước nên trạng thái FOUND/NOTFOUND được xác định. Nhánh ELSE chủ yếu minh họa trường hợp boolean chưa xác định; trong luồng thông thường này nó không được chọn.

Với DML, kiểm tra SQL%ROWCOUNT thường đủ để xử lý:

~~~sql
IF SQL%ROWCOUNT = 0 THEN
    ...
ELSIF SQL%ROWCOUNT = 1 THEN
    ...
ELSE
    ...
END IF;
~~~

Nhưng nếu cần sử dụng rowcount nhiều lần hoặc sau một SQL statement khác, hãy gán vào biến cục bộ.

## 8. Xử lý exception và implicit cursor attributes

Nếu câu SQL thất bại do constraint, conversion, trigger hoặc lỗi runtime khác, PL/SQL chuyển sang exception handler. Không nên dựa vào SQL%FOUND/NOTFOUND/ROWCOUNT để diễn giải một câu SQL chưa hoàn tất bình thường.

Ví dụ INSERT trùng khóa:

~~~sql
BEGIN
    INSERT INTO departments(department_id, department_name)
    VALUES (10, 'Duplicate');

    DBMS_OUTPUT.PUT_LINE('Inserted rows: ' || SQL%ROWCOUNT);
EXCEPTION
    WHEN DUP_VAL_ON_INDEX THEN
        DBMS_OUTPUT.PUT_LINE('Department ID already exists.');
END;
/
~~~

Nếu INSERT gặp unique violation, dòng DBMS_OUTPUT sau INSERT không được thực thi. Exception handler xử lý lỗi. Nếu cần log số hàng trước lỗi, lưu số liệu từ các câu SQL đã hoàn tất trước đó vào biến riêng.

### 8.1 NO_DATA_FOUND không giống SQL%NOTFOUND sau DML

UPDATE không tìm thấy hàng:

~~~sql
UPDATE employees
SET salary = salary + 100
WHERE employee_id = -999;
~~~

Không phát sinh NO_DATA_FOUND; SQL%ROWCOUNT bằng 0.

SELECT INTO không tìm thấy hàng:

~~~sql
SELECT employee_name
INTO l_name
FROM employees
WHERE employee_id = -999;
~~~

Phát sinh NO_DATA_FOUND. Đây là hai cơ chế khác nhau:

| Thao tác | Không có hàng |
|---|---|
| UPDATE/DELETE không khớp | Thành công, rowcount 0 |
| INSERT ... SELECT nguồn rỗng | Thành công, rowcount 0 |
| SELECT ... INTO | NO_DATA_FOUND |
| SELECT ... BULK COLLECT INTO | Thành công, collection rỗng |
| SELECT COUNT(*) INTO | Lấy một hàng với giá trị 0 |

### 8.2 Mẫu xử lý SELECT INTO

~~~sql
DECLARE
    l_name employees.employee_name%TYPE;
BEGIN
    SELECT employee_name
    INTO l_name
    FROM employees
    WHERE employee_id = 1001;

    DBMS_OUTPUT.PUT_LINE(l_name);
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('Employee not found.');
    WHEN TOO_MANY_ROWS THEN
        DBMS_OUTPUT.PUT_LINE('Query returned more than one employee.');
END;
/
~~~

Nếu nghiệp vụ yêu cầu đúng một hàng, hãy bảo đảm predicate dựa trên khóa unique hoặc xử lý rõ hai exception trên.

## 9. Implicit cursor trong các câu DML khác nhau

### 9.1 UPDATE có điều kiện

~~~sql
DECLARE
    l_rows PLS_INTEGER;
BEGIN
    UPDATE products
    SET unit_price = unit_price * 1.03
    WHERE category_id = 5
      AND discontinued = 'N';

    l_rows := SQL%ROWCOUNT;

    IF l_rows = 0 THEN
        DBMS_OUTPUT.PUT_LINE('No active products in category.');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Updated products: ' || l_rows);
    END IF;
END;
/
~~~

### 9.2 DELETE theo batch

~~~sql
DECLARE
    l_deleted PLS_INTEGER;
BEGIN
    DELETE FROM audit_events
    WHERE created_at < ADD_MONTHS(SYSDATE, -24);

    l_deleted := SQL%ROWCOUNT;

    DBMS_OUTPUT.PUT_LINE('Deleted events: ' || l_deleted);
END;
/
~~~

Trong hệ thống dữ liệu lớn, DELETE một lượng lớn hàng có thể tạo nhiều undo/redo và ảnh hưởng index. Nếu bảng partition theo thời gian, thao tác partition maintenance có thể là lựa chọn khác; đó là quyết định thiết kế và vận hành riêng, không phải tác dụng của SQL%ROWCOUNT.

### 9.3 MERGE

~~~sql
DECLARE
    l_affected PLS_INTEGER;
BEGIN
    MERGE INTO product_price target
    USING product_price_stage source
       ON (target.product_id = source.product_id)
    WHEN MATCHED THEN
        UPDATE SET target.price = source.price
    WHEN NOT MATCHED THEN
        INSERT (product_id, price)
        VALUES (source.product_id, source.price);

    l_affected := SQL%ROWCOUNT;

    DBMS_OUTPUT.PUT_LINE(
        'MERGE affected rows: ' || l_affected
    );
END;
/
~~~

Rowcount là tổng số hàng bị tác động bởi MERGE. Nếu cần thống kê riêng insert/update, cần thiết kế thêm cách phân loại.

### 9.4 DML với RETURNING INTO

RETURNING INTO lấy giá trị cột bị tác động về biến PL/SQL:

~~~sql
DECLARE
    l_new_salary employees.salary%TYPE;
    l_rows       PLS_INTEGER;
BEGIN
    UPDATE employees
    SET salary = salary + 500
    WHERE employee_id = 1001
    RETURNING salary INTO l_new_salary;

    l_rows := SQL%ROWCOUNT;

    IF l_rows = 1 THEN
        DBMS_OUTPUT.PUT_LINE('New salary: ' || l_new_salary);
    ELSE
        DBMS_OUTPUT.PUT_LINE('No employee updated.');
    END IF;
END;
/
~~~

Ví dụ giả định UPDATE tác động tối đa một hàng. Với nhiều hàng, dạng RETURNING INTO cần collection/bulk binding phù hợp; không dùng một biến scalar cho kết quả nhiều hàng.

## 10. FORALL và các thuộc tính bulk cursor

FORALL là cơ chế bulk binding để gửi nhiều lần thực thi DML từ collection, giảm round-trip giữa PL/SQL engine và SQL engine.

Ví dụ:

~~~sql
DECLARE
    TYPE t_id_list IS TABLE OF employees.employee_id%TYPE;
    l_ids t_id_list := t_id_list(1001, 1002, 1003);
BEGIN
    FORALL i IN 1 .. l_ids.COUNT
        UPDATE employees
        SET salary = salary + 100
        WHERE employee_id = l_ids(i);

    DBMS_OUTPUT.PUT_LINE(
        'Total rows affected: ' || SQL%ROWCOUNT
    );
END;
/
~~~

Sau FORALL, SQL%ROWCOUNT phản ánh tổng số hàng bị tác động bởi các lần DML trong FORALL vừa thực hiện.

### 10.1 SQL%BULK_ROWCOUNT

Nếu cần biết mỗi lần thực thi trong FORALL tác động bao nhiêu hàng, dùng SQL%BULK_ROWCOUNT:

~~~sql
DECLARE
    TYPE t_id_list IS TABLE OF employees.employee_id%TYPE;
    l_ids t_id_list := t_id_list(1001, 1002, 9999);
BEGIN
    FORALL i IN 1 .. l_ids.COUNT
        UPDATE employees
        SET salary = salary + 100
        WHERE employee_id = l_ids(i);

    FOR i IN 1 .. l_ids.COUNT LOOP
        DBMS_OUTPUT.PUT_LINE(
            'Input index ' || i ||
            ' affected ' || SQL%BULK_ROWCOUNT(i) || ' rows'
        );
    END LOOP;
END;
/
~~~

SQL%BULK_ROWCOUNT(i) cho biết số hàng bị tác động bởi lần thực thi DML thứ i. Đây là thông tin chi tiết hơn tổng SQL%ROWCOUNT.

### 10.2 SAVE EXCEPTIONS và SQL%BULK_EXCEPTIONS

FORALL có thể dùng SAVE EXCEPTIONS để tiếp tục xử lý các lần DML còn lại khi một số lần gặp lỗi. Sau đó SQL%BULK_EXCEPTIONS cung cấp danh sách lỗi:

~~~sql
DECLARE
    TYPE t_id_list IS TABLE OF employees.employee_id%TYPE;
    l_ids t_id_list := t_id_list(1001, 1002, 1003);

    e_bulk_errors EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_bulk_errors, -24381);
BEGIN
    FORALL i IN 1 .. l_ids.COUNT SAVE EXCEPTIONS
        UPDATE employees
        SET salary = salary + 100
        WHERE employee_id = l_ids(i);

EXCEPTION
    WHEN e_bulk_errors THEN
        FOR j IN 1 .. SQL%BULK_EXCEPTIONS.COUNT LOOP
            DBMS_OUTPUT.PUT_LINE(
                'Failed input index: ' ||
                SQL%BULK_EXCEPTIONS(j).ERROR_INDEX
            );
            DBMS_OUTPUT.PUT_LINE(
                'Oracle error code: ' ||
                SQL%BULK_EXCEPTIONS(j).ERROR_CODE
            );
        END LOOP;
END;
/
~~~

SQL%BULK_EXCEPTIONS là thuộc tính riêng của bulk DML, không phải một trong bốn thuộc tính SQL%FOUND/NOTFOUND/ISOPEN/ROWCOUNT. Cần phân biệt lỗi ở từng lần thực thi với tổng số hàng được cập nhật thành công. Chính sách COMMIT/ROLLBACK vẫn do logic transaction quyết định.

## 11. So sánh implicit cursor và explicit cursor

| Đặc điểm | Implicit cursor SQL | Explicit cursor |
|---|---|---|
| Khai báo tên cursor | Không | Có |
| OPEN | Oracle tự quản lý | Lập trình viên hoặc cursor FOR loop quản lý |
| FETCH từng hàng | Không trực tiếp | Có |
| CLOSE | Oracle tự đóng sau statement | Phải đóng nếu tự OPEN |
| Thuộc tính | SQL%FOUND, SQL%NOTFOUND, SQL%ISOPEN, SQL%ROWCOUNT | cursor_name%FOUND, %NOTFOUND, %ISOPEN, %ROWCOUNT |
| Phù hợp | DML, SELECT INTO, truy vấn một hàng, bulk collect | Truy vấn nhiều hàng cần xử lý tuần tự |

### 11.1 Explicit cursor mẫu

~~~sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id, employee_name
        FROM employees
        WHERE department_id = 10;

    l_employee_id   employees.employee_id%TYPE;
    l_employee_name employees.employee_name%TYPE;
BEGIN
    OPEN c_employees;

    LOOP
        FETCH c_employees
        INTO l_employee_id, l_employee_name;

        EXIT WHEN c_employees%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(
            l_employee_id || ' - ' || l_employee_name
        );
    END LOOP;

    DBMS_OUTPUT.PUT_LINE(
        'Rows fetched: ' || c_employees%ROWCOUNT
    );

    CLOSE c_employees;
END;
/
~~~

Ở đây phải dùng c_employees%NOTFOUND và c_employees%ROWCOUNT, không dùng SQL%NOTFOUND để kiểm tra vòng FETCH. SQL% attributes phản ánh SQL statement gần nhất, có thể bị thay đổi bởi SQL khác bên trong vòng lặp hoặc procedure được gọi.

### 11.2 Cursor FOR loop

Nếu chỉ cần đọc và xử lý từng hàng, cursor FOR loop tự OPEN, FETCH và CLOSE:

~~~sql
BEGIN
    FOR rec IN (
        SELECT employee_id, employee_name
        FROM employees
        WHERE department_id = 10
    ) LOOP
        DBMS_OUTPUT.PUT_LINE(
            rec.employee_id || ' - ' || rec.employee_name
        );
    END LOOP;
END;
/
~~~

Không cần tự quản lý vòng đời cursor. Nếu cần đếm số hàng đã xử lý trong loop, tạo biến đếm PL/SQL:

~~~sql
DECLARE
    l_count PLS_INTEGER := 0;
BEGIN
    FOR rec IN (
        SELECT employee_id
        FROM employees
        WHERE department_id = 10
    ) LOOP
        l_count := l_count + 1;
    END LOOP;

    DBMS_OUTPUT.PUT_LINE('Processed rows: ' || l_count);
END;
/
~~~

## 12. Các trường hợp dễ nhầm

### 12.1 SELECT INTO và SQL%NOTFOUND

Không viết:

~~~sql
SELECT employee_name
INTO l_name
FROM employees
WHERE employee_id = -999;

IF SQL%NOTFOUND THEN
    DBMS_OUTPUT.PUT_LINE('Not found');
END IF;
~~~

Khi không có hàng, SELECT INTO phát sinh NO_DATA_FOUND và luồng không đi tới IF. Hãy bắt exception hoặc dùng một truy vấn có dạng trả về một hàng như COUNT(*) nếu đó là điều cần đo.

### 12.2 COUNT(*) trả 0 nhưng SQL%FOUND vẫn TRUE

~~~sql
SELECT COUNT(*)
INTO l_count
FROM employees
WHERE department_id = -999;
~~~

Truy vấn aggregate trả một hàng với giá trị 0. Do đó SQL%FOUND là TRUE và SQL%ROWCOUNT là 1. Giá trị l_count mới là số hàng thỏa predicate.

### 12.3 SQL%ISOPEN luôn FALSE

Không dùng SQL%ISOPEN để xác định SELECT có trả hàng hay không. Dùng FOUND/NOTFOUND cho DML phù hợp, exception cho SELECT INTO, hoặc thuộc tính explicit cursor cho FETCH.

### 12.4 Một câu SQL tiếp theo ghi đè trạng thái

~~~sql
UPDATE employees
SET salary = salary + 100
WHERE department_id = 10;

SELECT COUNT(*)
INTO l_count
FROM departments;

-- SQL%ROWCOUNT lúc này là 1 của SELECT COUNT(*),
-- không phải số nhân viên đã UPDATE.
~~~

Lưu thuộc tính vào biến trước câu SQL tiếp theo.

### 12.5 Không có hàng bị tác động khác với lỗi constraint

UPDATE 0 hàng không phải lỗi. UPDATE vi phạm constraint là lỗi SQL và đi vào exception handler. Ứng dụng cần quyết định riêng liệu rowcount 0 có phải lỗi nghiệp vụ hay là trạng thái hợp lệ.

## 13. Mẫu thực tế: cập nhật trạng thái và kiểm tra số hàng

Một thao tác nghiệp vụ thường cần biết một bản ghi có tồn tại và có được chuyển trạng thái hay không:

~~~sql
DECLARE
    l_rows PLS_INTEGER;
BEGIN
    UPDATE orders
    SET status = 'APPROVED',
        approved_at = SYSTIMESTAMP
    WHERE order_id = 5001
      AND status = 'PENDING';

    l_rows := SQL%ROWCOUNT;

    IF l_rows = 1 THEN
        DBMS_OUTPUT.PUT_LINE('Order approved.');
    ELSIF l_rows = 0 THEN
        DBMS_OUTPUT.PUT_LINE(
            'Order not found or not in PENDING state.'
        );
    ELSE
        RAISE_APPLICATION_ERROR(
            -20002,
            'Unexpected number of orders updated.'
        );
    END IF;
END;
/
~~~

Điều kiện STATUS = 'PENDING' giúp kiểm tra và chuyển trạng thái trong cùng một DML. Nếu một session khác đã đổi trạng thái trước đó, câu UPDATE có thể tác động 0 hàng. Đây thường là cách kiểm tra optimistic state transition rõ ràng hơn việc SELECT trạng thái rồi UPDATE không điều kiện.

Nếu cần phân biệt “không tồn tại” và “đã được xử lý”, cần một truy vấn hoặc mô hình kết quả bổ sung; rowcount 0 tự nó không cho biết nguyên nhân nào trong hai nguyên nhân đó.

## 14. Tình huống thực hành: kiểm tra tồn tại trước khi ghi log

~~~sql
DECLARE
    l_rows PLS_INTEGER;
BEGIN
    UPDATE inventory
    SET quantity = quantity - 1
    WHERE product_id = 100
      AND quantity > 0;

    l_rows := SQL%ROWCOUNT;

    IF l_rows = 1 THEN
        INSERT INTO inventory_log(
            product_id, action_name, action_time
        )
        VALUES (
            100, 'DECREASE', SYSTIMESTAMP
        );
    ELSIF l_rows = 0 THEN
        RAISE_APPLICATION_ERROR(
            -20010,
            'Product is missing or inventory is insufficient.'
        );
    END IF;
END;
/
~~~

UPDATE và INSERT log thuộc cùng transaction của session. Nếu INSERT log lỗi và exception không được xử lý tại block, ứng dụng cần áp dụng chính sách rollback phù hợp. SQL%ROWCOUNT phải được lưu ngay sau UPDATE, vì sau INSERT nó sẽ phản ánh số hàng INSERT chứ không còn là số hàng UPDATE.

## 15. Hiệu năng và cách dùng cursor attributes

Các thuộc tính SQL% có chi phí sử dụng rất thấp; chúng chỉ đọc metadata trạng thái của câu SQL gần nhất. Tuy nhiên, cách viết chương trình vẫn ảnh hưởng hiệu năng:

- Không chạy SELECT COUNT(*) chỉ để biết một UPDATE có tác động hàng hay không; dùng SQL%ROWCOUNT.
- Không SELECT trước rồi UPDATE chỉ để xác định hàng tồn tại nếu một DML có điều kiện có thể giải quyết an toàn.
- Dùng BULK COLLECT/FORALL cho workload nhiều hàng khi phù hợp, thay vì vòng lặp SQL từng hàng.
- Lưu rowcount vào biến khi cần dùng sau câu SQL khác.
- Dùng cursor FOR loop hoặc explicit cursor khi cần xử lý nhiều hàng.

Ví dụ không cần truy vấn phụ:

~~~sql
-- Không cần SELECT COUNT(*) trước để đo số hàng cập nhật.
UPDATE employees
SET salary = salary + 100
WHERE department_id = 10;

l_rows := SQL%ROWCOUNT;
~~~

Một SELECT COUNT(*) riêng có thể tốn thêm I/O và còn có thể quan sát trạng thái khác nếu dữ liệu thay đổi đồng thời giữa SELECT và UPDATE.

## 16. Bảng tổng hợp bốn thuộc tính

| Thuộc tính | Kiểu trả về | Ý nghĩa | Ví dụ sử dụng |
|---|---|---|---|
| SQL%FOUND | BOOLEAN | TRUE nếu SQL gần nhất tác động/trả ít nhất một hàng | Kiểm tra UPDATE có khớp hàng |
| SQL%NOTFOUND | BOOLEAN | TRUE nếu SQL gần nhất không tác động/trả hàng nào | Phát hiện DELETE không khớp |
| SQL%ISOPEN | BOOLEAN | FALSE với implicit SQL cursor sau khi statement hoàn tất | Hầu như không dùng để kiểm tra kết quả |
| SQL%ROWCOUNT | Số nguyên | Số hàng SQL gần nhất xử lý | Đếm INSERT/UPDATE/DELETE/MERGE |

Trạng thái trước khi có SQL:

| Thuộc tính | Trạng thái |
|---|---|
| SQL%FOUND | NULL |
| SQL%NOTFOUND | NULL |
| SQL%ISOPEN | FALSE |
| SQL%ROWCOUNT | NULL |

Sau một DML hoàn tất bình thường:

| Kết quả DML | SQL%FOUND | SQL%NOTFOUND | SQL%ROWCOUNT |
|---|---|---|---:|
| Tác động 0 hàng | FALSE | TRUE | 0 |
| Tác động 1 hàng | TRUE | FALSE | 1 |
| Tác động nhiều hàng | TRUE | FALSE | Số hàng bị tác động |

SQL%ISOPEN vẫn FALSE vì implicit cursor đã tự đóng.

## 17. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| SQL%ROWCOUNT cho kết quả 1 dù UPDATE trước đó sửa nhiều hàng | Có một SELECT hoặc DML khác chạy sau UPDATE | Lưu rowcount ngay sau UPDATE |
| IF SQL%NOTFOUND không chạy khi SELECT INTO không có hàng | SELECT INTO phát sinh NO_DATA_FOUND trước khi tới IF | Bắt NO_DATA_FOUND |
| SQL%ISOPEN luôn FALSE | Implicit cursor tự đóng sau statement | Dùng SQL%FOUND/ROWCOUNT hoặc explicit cursor |
| UPDATE không tìm thấy hàng nhưng không có exception | DML 0 hàng là thành công về cú pháp/thực thi | Kiểm tra SQL%ROWCOUNT và áp dụng quy tắc nghiệp vụ |
| COUNT(*) bằng 0 nhưng SQL%FOUND TRUE | SELECT COUNT(*) vẫn trả một hàng kết quả | Phân biệt giá trị COUNT với số hàng SELECT INTO |
| Mất số hàng của DML sau khi gọi procedure | Procedure con thực thi SQL khác | Lưu SQL%ROWCOUNT trước lời gọi |
| Dùng SQL%NOTFOUND trong explicit cursor loop | Nhầm implicit cursor với cursor có tên | Dùng cursor_name%NOTFOUND |
| SQL%ROWCOUNT không cho biết riêng INSERT và UPDATE của MERGE | MERGE trả tổng số hàng bị tác động | Thiết kế phép đo riêng nếu cần phân loại |
| Dùng một biến scalar cho RETURNING nhiều hàng | Kết quả có thể gồm nhiều hàng | Dùng collection/bulk RETURNING phù hợp |

## 18. Bài thực hành tự kiểm tra

Các bài tập giả định schema thử nghiệm có bảng EMPLOYEES, DEPARTMENTS, ORDERS và INVENTORY. Điều chỉnh tên cột theo schema thực tế nếu cần.

### Bài 1 — FOUND sau UPDATE

UPDATE một EMPLOYEE_ID tồn tại. In SQL%FOUND, SQL%NOTFOUND và SQL%ROWCOUNT. Lặp lại với ID không tồn tại và so sánh.

### Bài 2 — DELETE không khớp

DELETE theo một ID không tồn tại. Giải thích vì sao câu lệnh không phát sinh NO_DATA_FOUND nhưng SQL%NOTFOUND là TRUE.

### Bài 3 — ISOPEN

Chạy một UPDATE rồi kiểm tra SQL%ISOPEN. Giải thích vì sao kết quả luôn FALSE sau khi câu lệnh hoàn tất.

### Bài 4 — Thuộc tính bị ghi đè

UPDATE nhiều hàng, sau đó SELECT COUNT(*) INTO một biến, rồi in SQL%ROWCOUNT. Thử lưu rowcount vào biến ngay sau UPDATE và so sánh.

### Bài 5 — SELECT INTO

Viết SELECT INTO cho ID có một hàng, ID không tồn tại và predicate trả nhiều hàng. Xử lý NO_DATA_FOUND và TOO_MANY_ROWS.

### Bài 6 — Aggregate

SELECT COUNT(*) INTO biến với predicate không có hàng phù hợp. In giá trị biến COUNT và SQL%ROWCOUNT. Giải thích tại sao hai kết quả là 0 và 1.

### Bài 7 — INSERT SELECT

Chạy INSERT INTO ... SELECT với nguồn có nhiều hàng và nguồn rỗng. So sánh SQL%ROWCOUNT.

### Bài 8 — MERGE

Chạy MERGE có cả hàng match và không match. Ghi lại tổng SQL%ROWCOUNT. Đề xuất cách thống kê riêng số hàng insert/update.

### Bài 9 — FORALL

Dùng collection ID để UPDATE bằng FORALL. In SQL%ROWCOUNT và từng SQL%BULK_ROWCOUNT(i). Giải thích sự khác nhau giữa tổng và từng lần thực thi.

### Bài 10 — Explicit cursor

Khai báo cursor, OPEN, FETCH, kiểm tra cursor_name%NOTFOUND và cursor_name%ROWCOUNT. So sánh với SQL% attributes.

### Bài 11 — State transition

UPDATE một đơn hàng từ PENDING sang APPROVED với điều kiện trạng thái. Dùng SQL%ROWCOUNT để phát hiện request cập nhật không còn hợp lệ.

### Bài 12 — Lưu rowcount trước procedure call

UPDATE nhiều hàng, lưu SQL%ROWCOUNT, gọi procedure con có SELECT/INSERT, rồi in biến đã lưu. So sánh với đọc SQL%ROWCOUNT sau procedure.

## 19. Ghi nhớ

- Implicit cursor SQL được Oracle tự mở và đóng cho câu SQL trong PL/SQL.
- Không khai báo, OPEN, FETCH hoặc CLOSE implicit cursor SQL.
- SQL%FOUND là TRUE khi câu SQL gần nhất tác động/trả ít nhất một hàng.
- SQL%NOTFOUND là TRUE khi câu SQL gần nhất không tác động/trả hàng nào.
- SQL%ISOPEN luôn FALSE sau khi implicit statement hoàn tất.
- SQL%ROWCOUNT cho biết số hàng câu SQL gần nhất xử lý.
- Trước khi có SQL statement, FOUND, NOTFOUND và ROWCOUNT có thể là NULL.
- UPDATE/DELETE không khớp hàng thường không phát sinh exception; rowcount bằng 0.
- SELECT INTO không có hàng phát sinh NO_DATA_FOUND; nhiều hàng phát sinh TOO_MANY_ROWS.
- SELECT COUNT(*) INTO vẫn trả một hàng với giá trị 0 khi không có bản ghi phù hợp.
- SELECT BULK COLLECT INTO có thể trả collection rỗng mà không phát sinh NO_DATA_FOUND.
- Thuộc tính SQL% luôn gắn với câu SQL gần nhất; lưu vào biến trước khi chạy SQL tiếp theo.
- Với explicit cursor, dùng cursor_name%FOUND/NOTFOUND/ISOPEN/ROWCOUNT.
- Với FORALL, dùng SQL%BULK_ROWCOUNT và SQL%BULK_EXCEPTIONS khi cần thông tin theo từng lần DML.

Implicit cursor attributes là cách ngắn gọn để PL/SQL biết câu SQL gần nhất đã làm gì. Hãy dùng FOUND/NOTFOUND để kiểm tra có hàng được tác động, ROWCOUNT để biết số lượng, và nhớ ISOPEN luôn FALSE với implicit cursor. Đọc thuộc tính ngay sau statement cần đo, phân biệt DML không khớp hàng với SELECT INTO phát sinh exception, và chuyển sang explicit cursor khi cần điều khiển việc đọc nhiều hàng.
