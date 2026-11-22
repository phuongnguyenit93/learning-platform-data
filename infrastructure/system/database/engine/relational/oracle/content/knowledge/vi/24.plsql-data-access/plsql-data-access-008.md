# SQL tĩnh, SQL động và tiêu chí lựa chọn trong PL/SQL

PL/SQL có thể thực thi SQL theo hai cách chính: **SQL tĩnh (static SQL)** và **SQL động (dynamic SQL)**. Với SQL tĩnh, câu lệnh SQL được viết trực tiếp trong khối PL/SQL. Với SQL động, chương trình tạo câu lệnh dưới dạng chuỗi rồi yêu cầu Oracle phân tích và thực thi ở runtime.

SQL tĩnh thường là lựa chọn đầu tiên vì cú pháp dễ đọc, được kiểm tra khi biên dịch PL/SQL, hỗ trợ theo dõi dependency và ít rủi ro hơn khi xử lý đầu vào. SQL động hữu ích khi cấu trúc câu lệnh chỉ biết lúc chạy, chẳng hạn tên bảng, tên cột, điều kiện lọc hoặc câu DDL được lựa chọn theo cấu hình.

Chọn sai cách có thể làm chương trình khó bảo trì, phát sinh lỗi chỉ khi chạy, tăng chi phí parse hoặc mở ra lỗ hổng SQL injection. Bài học này giải thích hai cách thực thi, native dynamic SQL, DBMS_SQL, bind variables, bảo mật, quyền thực thi, hiệu năng và tiêu chí lựa chọn.

## 1. SQL tĩnh là gì?

SQL tĩnh là câu SQL được viết trực tiếp trong mã PL/SQL. Câu lệnh và cấu trúc của nó đã được xác định trong source code:

~~~sql
DECLARE
    v_salary employees.salary%TYPE;
BEGIN
    SELECT salary
    INTO v_salary
    FROM employees
    WHERE employee_id = 100;

    DBMS_OUTPUT.PUT_LINE('Salary = ' || v_salary);
END;
/
~~~

Trong ví dụ này, bảng EMPLOYEES, cột SALARY, cột EMPLOYEE_ID và cấu trúc SELECT đều được viết rõ trong chương trình. Giá trị 100 là một literal; có thể thay bằng biến PL/SQL mà không cần chuyển câu SQL thành SQL động.

### 1.1. Dùng biến PL/SQL trong SQL tĩnh

~~~sql
DECLARE
    v_employee_id employees.employee_id%TYPE := 100;
    v_salary      employees.salary%TYPE;
BEGIN
    SELECT salary
    INTO v_salary
    FROM employees
    WHERE employee_id = v_employee_id;

    DBMS_OUTPUT.PUT_LINE(v_salary);
END;
/
~~~

PL/SQL tự truyền giá trị biến V_EMPLOYEE_ID vào câu SQL như một bind value. Không cần nối chuỗi SQL để đưa giá trị vào điều kiện.

### 1.2. Kiểm tra và dependency

Vì SQL tĩnh được nhúng trực tiếp trong PL/SQL:

- Compiler có thể kiểm tra cú pháp và ý nghĩa của câu SQL trong ngữ cảnh biên dịch.
- Oracle có thể ghi nhận dependency giữa stored program và các đối tượng schema được tham chiếu.
- Thay đổi cấu trúc đối tượng phụ thuộc có thể làm chương trình invalid và cần biên dịch lại.
- Người đọc source dễ nhận biết bảng, cột và kiểu dữ liệu mà chương trình sử dụng.

Việc biên dịch thành công không bảo đảm mọi lần chạy đều thành công. Ví dụ, SELECT INTO vẫn có thể gặp NO_DATA_FOUND hoặc TOO_MANY_ROWS tùy dữ liệu runtime; constraint, quyền và trạng thái hệ thống cũng có thể gây lỗi khi thực thi.

## 2. Ví dụ SQL tĩnh trong PL/SQL

### 2.1. SELECT INTO

SELECT INTO dùng để lấy một dòng vào biến hoặc record:

~~~sql
DECLARE
    v_name employees.last_name%TYPE;
BEGIN
    SELECT last_name
    INTO v_name
    FROM employees
    WHERE employee_id = 100;

    DBMS_OUTPUT.PUT_LINE(v_name);
END;
/
~~~

SELECT INTO có các tình huống quan trọng:

| Kết quả truy vấn | Hành vi |
|---|---|
| Đúng một dòng | Gán giá trị vào biến |
| Không có dòng | Phát sinh NO_DATA_FOUND |
| Nhiều hơn một dòng | Phát sinh TOO_MANY_ROWS |

Nếu truy vấn có thể trả nhiều dòng, dùng cursor, cursor FOR LOOP hoặc BULK COLLECT thay vì SELECT INTO một dòng.

### 2.2. DML tĩnh

~~~sql
DECLARE
    v_department_id employees.department_id%TYPE := 50;
    v_raise_rate    NUMBER := 0.05;
BEGIN
    UPDATE employees
    SET salary = salary * (1 + v_raise_rate)
    WHERE department_id = v_department_id;

    DBMS_OUTPUT.PUT_LINE(
        'Updated rows = ' || SQL%ROWCOUNT
    );
END;
/
~~~

SQL%ROWCOUNT trả số dòng bị tác động bởi câu SQL gần nhất trong session. Với DML tĩnh, có thể dùng các thuộc tính cursor ngầm như SQL%ROWCOUNT, SQL%FOUND và SQL%NOTFOUND để kiểm tra kết quả.

Block trên không tự COMMIT. Các thay đổi vẫn thuộc transaction hiện tại; caller hoặc session quyết định COMMIT/ROLLBACK theo quy trình ứng dụng.

### 2.3. Cursor tĩnh

~~~sql
DECLARE
    CURSOR c_employee IS
        SELECT employee_id, last_name, salary
        FROM employees
        WHERE department_id = 50
        ORDER BY employee_id;
BEGIN
    FOR rec IN c_employee LOOP
        DBMS_OUTPUT.PUT_LINE(
            rec.employee_id || ' - ' ||
            rec.last_name || ' - ' ||
            rec.salary
        );
    END LOOP;
END;
/
~~~

Cursor FOR LOOP tự mở, fetch và đóng cursor. Cấu trúc SELECT đã biết khi biên dịch, vì vậy đây là SQL tĩnh.

## 3. SQL động là gì?

SQL động là câu lệnh SQL được tạo thành chuỗi và thực thi tại runtime. Chương trình có thể tạo nội dung câu lệnh dựa trên tham số, metadata hoặc lựa chọn của người dùng.

Ví dụ:

~~~sql
DECLARE
    v_sql   VARCHAR2(1000);
    v_count NUMBER;
BEGIN
    v_sql := 'SELECT COUNT(*) FROM employees WHERE department_id = :dept';

    EXECUTE IMMEDIATE v_sql
        INTO v_count
        USING 50;

    DBMS_OUTPUT.PUT_LINE('Employee count = ' || v_count);
END;
/
~~~

Ở đây, câu SQL được giữ trong biến chuỗi V_SQL. Oracle phân tích câu lệnh khi chương trình thực thi EXECUTE IMMEDIATE. :DEPT là bind placeholder; giá trị 50 được truyền riêng trong USING.

### 3.1. Khi nào cấu trúc SQL mới chỉ biết lúc chạy?

Một số tình huống điển hình:

- Tên bảng được chọn từ cấu hình, ví dụ bảng dữ liệu theo năm.
- Tên cột sắp xếp do người dùng chọn trong một danh sách cho phép.
- Bộ lọc tùy chọn làm số lượng predicate thay đổi.
- Cần tạo hoặc thay đổi đối tượng bằng DDL.
- Một tiện ích quản trị phải truy vấn nhiều bảng có tên thay đổi.
- Một công cụ báo cáo cho phép chọn cột và nhóm dữ liệu ở runtime.

SQL động không cần thiết chỉ vì giá trị điều kiện thay đổi. Nếu bảng, cột và cấu trúc SQL đã cố định, hãy dùng SQL tĩnh với biến bind.

## 4. Native Dynamic SQL (NDS)

Oracle cung cấp Native Dynamic SQL để thực thi câu lệnh động trực tiếp trong PL/SQL. Các cấu trúc thường dùng:

- EXECUTE IMMEDIATE: thực thi DML, DDL, SELECT một dòng, anonymous PL/SQL block hoặc lời gọi phù hợp.
- OPEN ... FOR: mở một cursor biến cho truy vấn động trả nhiều dòng.
- FETCH và CLOSE: đọc rồi đóng cursor động.

NDS thường đơn giản hơn DBMS_SQL khi số lượng, kiểu dữ liệu và cấu trúc tham số đã biết lúc viết chương trình.

## 5. EXECUTE IMMEDIATE với DML

### 5.1. UPDATE động có bind variables

Giả sử tên bảng được lựa chọn trong chương trình, còn mức tăng và mã phòng ban là giá trị:

~~~sql
DECLARE
    v_table_name VARCHAR2(30) := 'EMPLOYEES';
    v_sql        VARCHAR2(1000);
    v_rate       NUMBER := 0.05;
    v_dept_id    NUMBER := 50;
BEGIN
    v_sql :=
        'UPDATE ' || v_table_name ||
        ' SET salary = salary * (1 + :rate)' ||
        ' WHERE department_id = :dept';

    EXECUTE IMMEDIATE v_sql
        USING v_rate, v_dept_id;

    DBMS_OUTPUT.PUT_LINE(
        'Updated rows = ' || SQL%ROWCOUNT
    );
END;
/
~~~

Tên bảng được ghép vào chuỗi vì identifier không thể truyền như một bind value. Các giá trị 0.05 và 50 được truyền bằng USING để Oracle xử lý như dữ liệu.

Ví dụ trên giả định tên bảng được kiểm soát. Nếu tên bảng đến từ đầu vào bên ngoài, phải kiểm tra bằng allowlist và/hoặc DBMS_ASSERT trước khi ghép vào SQL.

### 5.2. DELETE động

~~~sql
DECLARE
    v_sql VARCHAR2(1000);
    v_id  NUMBER := 100;
BEGIN
    v_sql := 'DELETE FROM employees WHERE employee_id = :id';

    EXECUTE IMMEDIATE v_sql USING v_id;

    DBMS_OUTPUT.PUT_LINE(
        'Deleted rows = ' || SQL%ROWCOUNT
    );
END;
/
~~~

DELETE động tham gia transaction hiện tại như DELETE tĩnh. EXECUTE IMMEDIATE không tự COMMIT DML.

### 5.3. INSERT động

~~~sql
DECLARE
    v_sql VARCHAR2(1000);
BEGIN
    v_sql :=
        'INSERT INTO employees ' ||
        '(employee_id, last_name, email, hire_date, job_id, salary)' ||
        ' VALUES (:id, :name, :email, SYSDATE, :job, :salary)';

    EXECUTE IMMEDIATE v_sql
        USING 9001, 'Nguyen', 'NGUYEN9001', 'IT_PROG', 8000;
END;
/
~~~

Các giá trị bind được truyền theo thứ tự placeholder trong câu SQL. Nếu dùng SQL động dạng statement, hãy quản lý vị trí bind nhất quán; đừng dựa vào việc tên placeholder giống nhau để thay đổi thứ tự tham số.

## 6. EXECUTE IMMEDIATE với SELECT

### 6.1. SELECT trả đúng một dòng

~~~sql
DECLARE
    v_sql    VARCHAR2(1000);
    v_salary NUMBER;
    v_id     NUMBER := 100;
BEGIN
    v_sql :=
        'SELECT salary FROM employees WHERE employee_id = :id';

    EXECUTE IMMEDIATE v_sql
        INTO v_salary
        USING v_id;

    DBMS_OUTPUT.PUT_LINE('Salary = ' || v_salary);
END;
/
~~~

Với SELECT một dòng, INTO nhận các cột kết quả theo thứ tự. Số biến và kiểu dữ liệu phải phù hợp với select list.

Nếu không có dòng, phát sinh NO_DATA_FOUND. Nếu có nhiều dòng, phát sinh TOO_MANY_ROWS.

### 6.2. SELECT nhiều dòng với BULK COLLECT

Nếu số cột và kiểu dữ liệu đã biết, có thể lấy nhiều dòng vào collection:

~~~sql
DECLARE
    TYPE t_employee_ids IS TABLE OF employees.employee_id%TYPE;
    v_ids t_employee_ids;
    v_dept_id NUMBER := 50;
BEGIN
    EXECUTE IMMEDIATE
        'SELECT employee_id
           FROM employees
          WHERE department_id = :dept
          ORDER BY employee_id'
        BULK COLLECT INTO v_ids
        USING v_dept_id;

    FOR i IN 1 .. v_ids.COUNT LOOP
        DBMS_OUTPUT.PUT_LINE(v_ids(i));
    END LOOP;
END;
/
~~~

BULK COLLECT lấy tất cả kết quả vào collection. Nếu truy vấn có thể trả lượng dữ liệu rất lớn, cần cân nhắc giới hạn bộ nhớ PGA; dùng cursor động và fetch theo batch nếu cần xử lý theo từng nhóm.

## 7. OPEN FOR với cursor động

Khi truy vấn trả nhiều dòng và cần fetch từng dòng, dùng REF CURSOR:

~~~sql
DECLARE
    v_sql         VARCHAR2(1000);
    v_dept_id     NUMBER := 50;
    v_employee_id employees.employee_id%TYPE;
    v_last_name   employees.last_name%TYPE;
    v_salary      employees.salary%TYPE;
    v_rc          SYS_REFCURSOR;
BEGIN
    v_sql :=
        'SELECT employee_id, last_name, salary ' ||
        'FROM employees ' ||
        'WHERE department_id = :dept ' ||
        'ORDER BY employee_id';

    OPEN v_rc FOR v_sql USING v_dept_id;

    LOOP
        FETCH v_rc
        INTO v_employee_id, v_last_name, v_salary;

        EXIT WHEN v_rc%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(
            v_employee_id || ' - ' ||
            v_last_name || ' - ' ||
            v_salary
        );
    END LOOP;

    CLOSE v_rc;
EXCEPTION
    WHEN OTHERS THEN
        IF v_rc%ISOPEN THEN
            CLOSE v_rc;
        END IF;
        RAISE;
END;
/
~~~

SYS_REFCURSOR là weak ref cursor, có thể mở cho các truy vấn có select list khác nhau. Tuy nhiên, khi FETCH vào biến PL/SQL, số cột và kiểu dữ liệu vẫn phải khớp với kết quả thực tế. Weak cursor linh hoạt ở thời điểm mở, nhưng không tự biến một record có cấu trúc không xác định thành các biến có kiểu phù hợp.

### 7.1. Khi nào dùng OPEN FOR thay cho BULK COLLECT?

| Nhu cầu | Cách phù hợp để xem xét |
|---|---|
| Kết quả ít, cấu trúc cột đã biết | EXECUTE IMMEDIATE ... BULK COLLECT INTO |
| Kết quả nhiều, cần fetch theo lượt/batch | OPEN FOR với SYS_REFCURSOR |
| Cần trả result set cho caller | Trả REF CURSOR qua tham số OUT |
| Không biết số lượng/kiểu cột lúc compile time | DBMS_SQL |

## 8. Dynamic SQL cho anonymous PL/SQL block

EXECUTE IMMEDIATE cũng có thể chạy một block PL/SQL được tạo ở runtime:

~~~sql
DECLARE
    v_block VARCHAR2(1000);
    v_dept  NUMBER := 50;
    v_rate  NUMBER := 0.05;
BEGIN
    v_block :=
        'BEGIN ' ||
        '  UPDATE employees ' ||
        '  SET salary = salary * (1 + :rate) ' ||
        '  WHERE department_id = :dept; ' ||
        'END;';

    EXECUTE IMMEDIATE v_block
        USING v_rate, v_dept;
END;
/
~~~

Block động hữu ích khi cần gọi thủ tục hoặc thực thi PL/SQL có cấu trúc thay đổi. Nếu chỉ có một câu UPDATE, thực thi trực tiếp câu DML thường đơn giản hơn.

### 8.1. Tham số IN, OUT và IN OUT

Khi gọi một PL/SQL block động hoặc procedure qua dynamic SQL, USING có thể khai báo chế độ truyền tham số:

~~~sql
DECLARE
    v_block  VARCHAR2(500);
    v_input  NUMBER := 10;
    v_output NUMBER;
BEGIN
    v_block := 'BEGIN :out_value := :in_value * 2; END;';

    EXECUTE IMMEDIATE v_block
        USING OUT v_output, IN v_input;

    DBMS_OUTPUT.PUT_LINE(v_output);
END;
/
~~~

Ví dụ minh họa tham số OUT và IN trong anonymous block động. Với block PL/SQL, bind placeholder có thể dùng cho tham số đầu vào và đầu ra; cần khai báo mode đúng thứ tự tương ứng với placeholder.

## 9. Dynamic DDL

DDL như CREATE, ALTER, DROP thường cần SQL động khi tên đối tượng hoặc cấu trúc được quyết định tại runtime:

~~~sql
BEGIN
    EXECUTE IMMEDIATE
        'CREATE TABLE lab_dynamic_log (
            log_id NUMBER,
            message VARCHAR2(200)
        )';
END;
/
~~~

Không cần INTO cho DDL. Câu DDL động được phân tích và thực thi tại runtime.

### 9.1. Bind variables không thay thế tên bảng hoặc tên cột

Không thể viết:

~~~sql
EXECUTE IMMEDIATE
    'CREATE TABLE :table_name (id NUMBER)'
USING 'LAB_DYNAMIC_LOG';
~~~

Bind variables đại diện cho **giá trị dữ liệu**, không đại diện cho identifier, keyword hoặc đoạn cú pháp SQL. Tên bảng, tên cột, tên schema, hướng ORDER BY phải được kiểm soát và ghép vào chuỗi sau khi xác thực.

### 9.2. DDL và transaction

Các lệnh DDL thông thường gây implicit commit theo quy tắc Oracle. Vì vậy, DDL động cũng có thể kết thúc transaction DML đang mở. Không đặt CREATE/ALTER/DROP vào giữa một quy trình DML mà ứng dụng dự định rollback toàn bộ nếu có lỗi.

Ví dụ:

~~~sql
UPDATE employees
SET salary = salary + 100
WHERE employee_id = 100;

EXECUTE IMMEDIATE 'CREATE TABLE lab_ddl_test (id NUMBER)';

ROLLBACK;
~~~

Không thể dựa vào ROLLBACK cuối để hoàn tác UPDATE trước DDL vì DDL đã gây implicit commit. Hãy tách quy trình thay đổi schema khỏi transaction nghiệp vụ.

## 10. Bind variables: tách dữ liệu khỏi cấu trúc SQL

Bind variable là placeholder trong câu SQL, được gắn với giá trị khi thực thi. Đây là nguyên tắc quan trọng nhất khi viết SQL động an toàn và hiệu quả.

Ví dụ đúng:

~~~sql
DECLARE
    v_sql VARCHAR2(500);
    v_id  NUMBER := 100;
BEGIN
    v_sql := 'DELETE FROM employees WHERE employee_id = :id';
    EXECUTE IMMEDIATE v_sql USING v_id;
END;
/
~~~

Giá trị 100 được truyền riêng, không được ghép trực tiếp vào chuỗi SQL.

### 10.1. Tránh nối giá trị người dùng vào SQL

Cách dễ gây lỗi:

~~~sql
v_sql :=
    'SELECT COUNT(*) FROM users WHERE username = '''
    || p_username || '''';

EXECUTE IMMEDIATE v_sql INTO v_count;
~~~

Nếu đầu vào chứa dấu nháy hoặc chuỗi có ý nghĩa cú pháp SQL, câu lệnh có thể lỗi hoặc bị thay đổi ý nghĩa. Nếu đầu vào bị lợi dụng để chèn điều kiện, đây là SQL injection.

Cách an toàn hơn:

~~~sql
v_sql :=
    'SELECT COUNT(*) FROM users WHERE username = :name';

EXECUTE IMMEDIATE v_sql
    INTO v_count
    USING p_username;
~~~

Bind variables giúp Oracle xử lý dữ liệu đúng kiểu, tránh phải tự escape literal và thường hỗ trợ tái sử dụng cursor.

### 10.2. Bind không áp dụng cho identifier

Ví dụ sau không có nghĩa “sắp xếp theo cột có tên truyền vào”:

~~~sql
EXECUTE IMMEDIATE
    'SELECT employee_id, last_name FROM employees ORDER BY :column_name'
USING p_column_name;
~~~

:COLUMN_NAME là một giá trị bind. Oracle sẽ sắp xếp theo giá trị bind đó, không diễn giải nó thành tên cột. Muốn chọn cột sắp xếp, phải chọn identifier từ danh sách cho phép và ghép tên cột đã xác thực vào SQL.

## 11. Xây dựng câu SQL động an toàn với allowlist

Giả sử báo cáo cho phép sắp xếp theo EMPLOYEE_ID, LAST_NAME hoặc SALARY. Không ghép thẳng chuỗi do người dùng gửi vào ORDER BY. Hãy ánh xạ lựa chọn sang danh sách identifier cố định:

~~~sql
DECLARE
    v_sort_column VARCHAR2(30);
    v_direction   VARCHAR2(4);
    v_sql         VARCHAR2(1000);
    v_min_salary  NUMBER := 5000;
    v_rc          SYS_REFCURSOR;
    v_id          NUMBER;
    v_name        VARCHAR2(100);
    v_salary      NUMBER;
BEGIN
    -- Giá trị giả định nhận từ giao diện.
    CASE UPPER('SALARY')
        WHEN 'EMPLOYEE_ID' THEN
            v_sort_column := 'EMPLOYEE_ID';
        WHEN 'LAST_NAME' THEN
            v_sort_column := 'LAST_NAME';
        WHEN 'SALARY' THEN
            v_sort_column := 'SALARY';
        ELSE
            RAISE_APPLICATION_ERROR(-20001, 'Invalid sort column');
    END CASE;

    v_direction := 'DESC';
    IF v_direction NOT IN ('ASC', 'DESC') THEN
        RAISE_APPLICATION_ERROR(-20002, 'Invalid sort direction');
    END IF;

    v_sql :=
        'SELECT employee_id, last_name, salary ' ||
        'FROM employees ' ||
        'WHERE salary >= :min_salary ' ||
        'ORDER BY ' || v_sort_column || ' ' || v_direction;

    OPEN v_rc FOR v_sql USING v_min_salary;

    LOOP
        FETCH v_rc INTO v_id, v_name, v_salary;
        EXIT WHEN v_rc%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(
            v_id || ' ' || v_name || ' ' || v_salary
        );
    END LOOP;

    CLOSE v_rc;
END;
/
~~~

Trong ứng dụng thật, thay literal SALARY bằng tham số đầu vào. CASE chỉ cho phép các lựa chọn đã định nghĩa. Giá trị MIN_SALARY vẫn được bind.

Allowlist giúp kiểm soát identifier và keyword có thể được ghép vào SQL. Bind variables vẫn được dùng cho các giá trị dữ liệu.

## 12. DBMS_ASSERT để xác thực identifier

Oracle cung cấp package DBMS_ASSERT với các hàm kiểm tra hoặc quote tên SQL. Một số hàm thường gặp:

| Hàm | Mục đích khái quát |
|---|---|
| SIMPLE_SQL_NAME | Kiểm tra một simple SQL name |
| QUALIFIED_SQL_NAME | Kiểm tra tên được qualify theo cú pháp cho phép |
| SQL_OBJECT_NAME | Kiểm tra tên đối tượng SQL hợp lệ và tồn tại theo quy tắc hàm |
| ENQUOTE_NAME | Quote một SQL identifier |
| ENQUOTE_LITERAL | Quote một SQL literal |

Ví dụ kiểm tra tên đơn giản:

~~~sql
DECLARE
    v_input_name VARCHAR2(128) := 'LAB_EMPLOYEE';
    v_safe_name  VARCHAR2(128);
    v_sql        VARCHAR2(1000);
    v_count      NUMBER;
BEGIN
    v_safe_name := DBMS_ASSERT.SIMPLE_SQL_NAME(v_input_name);

    v_sql := 'SELECT COUNT(*) FROM ' || v_safe_name;

    EXECUTE IMMEDIATE v_sql INTO v_count;
    DBMS_OUTPUT.PUT_LINE(v_count);
END;
/
~~~

DBMS_ASSERT giúp xác thực hình dạng identifier, nhưng không thay thế kiểm soát quyền nghiệp vụ. Một tên hợp lệ về cú pháp vẫn có thể trỏ đến đối tượng mà người dùng không được phép truy cập hoặc không nên được phép chọn.

### 12.1. Kết hợp allowlist và DBMS_ASSERT

Với tên bảng do người dùng chọn:

1. So sánh đầu vào với danh sách bảng được phép.
2. Nếu hợp lệ, dùng DBMS_ASSERT để kiểm tra/quote identifier theo cách phù hợp.
3. Ghép identifier vào câu SQL.
4. Bind mọi giá trị dữ liệu.
5. Xử lý exception và ghi log cần thiết.

Allowlist là quyết định nghiệp vụ; DBMS_ASSERT là lớp kiểm tra cú pháp/identifier. Dùng cả hai khi đối tượng được chọn từ đầu vào.

### 12.2. Không dùng ENQUOTE_LITERAL để thay bind variables

ENQUOTE_LITERAL có thể quote một literal theo cú pháp SQL, nhưng bind variable vẫn là lựa chọn tốt hơn cho giá trị dữ liệu. Bind tránh phải tự xây dựng literal, hỗ trợ kiểu dữ liệu và cursor sharing. Chỉ dùng literal quoting khi có lý do cụ thể và hiểu rõ ngữ cảnh.

## 13. SQL injection trong dynamic SQL

SQL injection xảy ra khi dữ liệu đầu vào bị ghép vào chuỗi SQL và làm thay đổi cấu trúc hoặc ý nghĩa của câu lệnh.

Ví dụ nguy hiểm:

~~~sql
v_sql :=
    'SELECT COUNT(*) FROM users WHERE username = '''
    || p_username || '''';
~~~

Nếu đầu vào chứa dấu nháy và biểu thức SQL, chuỗi tạo ra có thể khác với ý định ban đầu. Trong ứng dụng thực tế, injection có thể dẫn đến đọc dữ liệu ngoài phạm vi, thay đổi hoặc xóa dữ liệu nếu quyền của chương trình cho phép.

### 13.1. Quy tắc phòng tránh

- Dùng bind variables cho mọi giá trị dữ liệu có thể bind.
- Dùng allowlist cho tên bảng, cột, schema, hướng sắp xếp và keyword động.
- Dùng DBMS_ASSERT phù hợp để xác thực identifier.
- Không nối trực tiếp đầu vào không tin cậy vào câu SQL.
- Cấp quyền tối thiểu cho schema và stored program.
- Cân nhắc AUTHID DEFINER và AUTHID CURRENT_USER theo yêu cầu bảo mật.
- Không trả thông tin nội bộ nhạy cảm trong thông báo lỗi gửi ra giao diện.
- Ghi log truy vấn/lỗi theo chính sách, tránh ghi dữ liệu bí mật hoặc thông tin xác thực.

### 13.2. Vì sao bind variables không giải quyết tên bảng động?

Bind chỉ thay thế giá trị trong vị trí biểu thức mà SQL cho phép bind. Parser cần biết cấu trúc câu lệnh, bảng và cột nào tham gia trước khi thực thi. Vì vậy, identifier phải được xác thực và ghép vào chuỗi SQL.

Không cố dùng bind cho:

- Tên bảng hoặc view.
- Tên schema.
- Tên cột.
- Từ khóa ASC/DESC.
- Đoạn cú pháp như JOIN hoặc WHERE.

## 14. DBMS_SQL là gì?

DBMS_SQL là package PL/SQL cung cấp API để phân tích, bind, định nghĩa cột, thực thi và fetch SQL động ở mức chi tiết hơn Native Dynamic SQL.

NDS thường phù hợp khi chương trình biết trước:

- Số lượng bind variable.
- Kiểu dữ liệu của bind variable.
- Số lượng và kiểu cột trả về.

DBMS_SQL hữu ích khi cấu trúc kết quả chỉ biết lúc runtime, chẳng hạn:

- Một công cụ báo cáo cho phép chọn số lượng cột khác nhau.
- Một tiện ích quản trị đọc metadata rồi tạo SELECT với select list thay đổi.
- Một framework cần mô tả các cột kết quả bằng DESCRIBE_COLUMNS.
- Một ứng dụng cần xử lý SQL động tổng quát mà kiểu record không thể khai báo trước.

### 14.1. Quy trình DBMS_SQL cơ bản

Luồng thông thường:

1. OPEN_CURSOR để lấy cursor number.
2. PARSE để phân tích câu SQL.
3. BIND_VARIABLE để gắn giá trị.
4. Với SELECT, DESCRIBE_COLUMNS để lấy metadata nếu cần.
5. DEFINE_COLUMN để định nghĩa biến nhận từng cột.
6. EXECUTE để thực thi.
7. FETCH_ROWS để đọc dòng.
8. COLUMN_VALUE để lấy giá trị từng cột.
9. CLOSE_CURSOR để đóng cursor.

### 14.2. Ví dụ khung DBMS_SQL với một cột VARCHAR2

~~~sql
DECLARE
    v_cursor INTEGER;
    v_rows   INTEGER;
    v_value  VARCHAR2(4000);
    v_sql    VARCHAR2(1000);
BEGIN
    v_cursor := DBMS_SQL.OPEN_CURSOR;

    v_sql := 'SELECT last_name FROM employees WHERE department_id = :dept';

    DBMS_SQL.PARSE(
        v_cursor,
        v_sql,
        DBMS_SQL.NATIVE
    );

    DBMS_SQL.BIND_VARIABLE(
        v_cursor,
        ':dept',
        50
    );

    DBMS_SQL.DEFINE_COLUMN(
        v_cursor,
        1,
        v_value,
        4000
    );

    v_rows := DBMS_SQL.EXECUTE(v_cursor);

    WHILE DBMS_SQL.FETCH_ROWS(v_cursor) > 0 LOOP
        DBMS_SQL.COLUMN_VALUE(
            v_cursor,
            1,
            v_value
        );

        DBMS_OUTPUT.PUT_LINE(v_value);
    END LOOP;

    DBMS_SQL.CLOSE_CURSOR(v_cursor);
EXCEPTION
    WHEN OTHERS THEN
        IF v_cursor IS NOT NULL
           AND DBMS_SQL.IS_OPEN(v_cursor)
        THEN
            DBMS_SQL.CLOSE_CURSOR(v_cursor);
        END IF;
        RAISE;
END;
/
~~~

Đây là ví dụ cho select list một cột VARCHAR2 đã biết. Với select list không biết trước, chương trình cần dùng DESCRIBE_COLUMNS hoặc biến thể phù hợp, sau đó DEFINE_COLUMN theo kiểu dữ liệu từng cột và gọi COLUMN_VALUE tương ứng. Một chương trình tổng quát phải xử lý NUMBER, DATE, VARCHAR2, CLOB và các kiểu được hỗ trợ riêng.

### 14.3. NDS hay DBMS_SQL?

| Tiêu chí | Native Dynamic SQL | DBMS_SQL |
|---|---|---|
| Cú pháp | Ngắn và gần SQL/PLSQL thông thường | API nhiều bước |
| Biết trước kiểu bind | Phù hợp | Phù hợp |
| Biết trước select list | Phù hợp | Phù hợp |
| Không biết số cột/kiểu cột lúc compile time | Hạn chế | Có DESCRIBE_COLUMNS và DEFINE_COLUMN |
| Trả nhiều dòng | OPEN FOR hoặc BULK COLLECT | FETCH_ROWS |
| Trường hợp sử dụng phổ biến | Dynamic DML/SELECT/DDL trong ứng dụng | Framework SQL tổng quát, metadata-driven |

Không dùng DBMS_SQL chỉ vì câu SQL được tạo động. Nếu NDS đáp ứng được cấu trúc và kiểu dữ liệu, NDS thường dễ viết và bảo trì hơn.

## 15. Chuyển đổi giữa DBMS_SQL và REF CURSOR

Oracle cung cấp các hàm chuyển đổi để phối hợp hai API trong một số trường hợp:

- DBMS_SQL.TO_REFCURSOR: chuyển cursor DBMS_SQL sang REF CURSOR.
- DBMS_SQL.TO_CURSOR_NUMBER: chuyển REF CURSOR sang cursor number của DBMS_SQL.

Điều này hữu ích khi một phần chương trình cần mô tả SQL động bằng DBMS_SQL, nhưng phần khác muốn trả kết quả qua REF CURSOR. Việc chuyển đổi có quy tắc ownership và trạng thái cursor; sau khi chuyển, không tiếp tục dùng cùng cursor theo cách không phù hợp với API cũ. Hãy xem tài liệu Oracle đúng phiên bản trước khi dùng trong framework dùng chung.

## 16. Placeholder và thứ tự bind

Khi viết NDS, phải bảo đảm số lượng, thứ tự và mode bind khớp với placeholder trong câu lệnh.

Ví dụ:

~~~sql
DECLARE
    v_sql VARCHAR2(500);
BEGIN
    v_sql :=
        'UPDATE employees ' ||
        'SET salary = :new_salary ' ||
        'WHERE employee_id = :employee_id';

    EXECUTE IMMEDIATE v_sql
        USING 9000, 100;
END;
/
~~~

Giá trị 9000 được gắn với placeholder đầu tiên, 100 với placeholder thứ hai trong SQL statement. Để tránh nhầm lẫn, giữ thứ tự bind rõ ràng và dùng biến có tên gợi nghĩa.

### 16.1. Placeholder lặp lại

Quy tắc liên kết placeholder có khác biệt giữa dynamic SQL statement và anonymous PL/SQL block/CALL. Với SQL statement, bind arguments được gắn theo vị trí xuất hiện của placeholder; nếu một placeholder name lặp lại, mỗi occurrence trong SQL statement cần được tính trong danh sách bind theo quy tắc của NDS. Với anonymous PL/SQL block/CALL, quy tắc placeholder lặp lại khác và cần đối chiếu tài liệu Oracle của phiên bản đang dùng.

Để giảm nhầm lẫn, tránh lặp placeholder không cần thiết hoặc viết câu lệnh theo cách có thứ tự bind dễ kiểm tra. Khi có nhiều tham số, ghi chú thứ tự rõ ràng và kiểm tra bằng test trên đúng phiên bản.

### 16.2. Bind giá trị NULL

Trong USING, không truyền literal NULL trực tiếp như một bind argument. Dùng biến PL/SQL có giá trị NULL:

~~~sql
DECLARE
    v_null_value VARCHAR2(1);
    v_count NUMBER;
BEGIN
    EXECUTE IMMEDIATE
        'SELECT COUNT(*) FROM employees WHERE commission_pct = :x'
        INTO v_count
        USING v_null_value;
END;
/
~~~

Lưu ý: phép so sánh COLUMN = NULL không trả về TRUE; nếu muốn tìm NULL, predicate đúng thường là COLUMN IS NULL. Ví dụ trên minh họa cách truyền biến NULL, không phải cách kiểm tra giá trị NULL trong SQL.

## 17. SQL động với nhiều điều kiện tùy chọn

Một báo cáo có thể nhận department_id và mức lương tối thiểu tùy chọn. Có hai cách thiết kế:

### 17.1. Giữ SQL tĩnh bằng predicate tùy chọn

~~~sql
SELECT employee_id, last_name, salary
FROM employees
WHERE (p_department_id IS NULL
       OR department_id = p_department_id)
  AND (p_min_salary IS NULL
       OR salary >= p_min_salary);
~~~

Đây là minh họa logic; trong PL/SQL, biến tham số được dùng trực tiếp trong static SQL. Cách này giữ câu lệnh tĩnh, dễ kiểm tra và bind giá trị.

Tuy nhiên, predicate kiểu :p IS NULL OR column = :p có thể ảnh hưởng cardinality estimate hoặc khả năng dùng index tùy dữ liệu, bind peeking và optimizer. Cần đo execution plan trên workload thực tế.

### 17.2. Tạo predicate động

~~~sql
DECLARE
    v_sql VARCHAR2(2000);
    v_count NUMBER;
    v_dept_id NUMBER := 50;
    v_min_salary NUMBER := 5000;
BEGIN
    v_sql := 'SELECT COUNT(*) FROM employees WHERE 1 = 1';

    IF v_dept_id IS NOT NULL THEN
        v_sql := v_sql || ' AND department_id = :dept';
    END IF;

    IF v_min_salary IS NOT NULL THEN
        v_sql := v_sql || ' AND salary >= :min_salary';
    END IF;

    -- Ví dụ này minh họa trường hợp cả hai tham số đều có giá trị.
    EXECUTE IMMEDIATE v_sql
        INTO v_count
        USING v_dept_id, v_min_salary;

    DBMS_OUTPUT.PUT_LINE(v_count);
END;
/
~~~

Nếu các tham số có thể NULL và số predicate thay đổi, phần USING cũng phải được xây dựng đúng với số placeholder thực tế. Không thể luôn truyền tất cả biến theo một danh sách cố định nếu SQL string có thể không chứa placeholder tương ứng. Có thể dùng các nhánh IF với EXECUTE IMMEDIATE riêng cho từng cấu hình, hoặc xây dựng API bind linh hoạt phù hợp.

### 17.3. Chọn giữa hai cách

| Điều kiện | Cách thường cân nhắc |
|---|---|
| Chỉ vài tham số, predicate ổn định | Static SQL với predicate tùy chọn |
| Có ít cấu hình truy vấn rõ ràng | Nhiều nhánh IF, mỗi nhánh dùng static SQL |
| Số predicate thay đổi theo cấu hình | Dynamic SQL với bind management cẩn thận |
| Cần thay tên bảng/cột | Dynamic SQL, allowlist identifier |
| Cần cấu trúc truy vấn tổng quát do metadata quyết định | NDS hoặc DBMS_SQL |

Không chọn dynamic SQL chỉ để tránh viết một vài nhánh IF. Hãy cân nhắc tính rõ ràng, kế hoạch thực thi và khả năng bảo trì.

## 18. Quyền thực thi: AUTHID DEFINER và AUTHID CURRENT_USER

Stored procedure/function có thể chạy với quyền của người định nghĩa hoặc người gọi tùy AUTHID:

- AUTHID DEFINER: definer-rights; quyền thực thi được đánh giá theo ngữ cảnh quyền của chủ sở hữu chương trình, với các quy tắc Oracle về role và quyền trực tiếp.
- AUTHID CURRENT_USER: invoker-rights; quyền được đánh giá theo người gọi trong ngữ cảnh invoker-rights.

Ví dụ:

~~~sql
CREATE OR REPLACE PROCEDURE lab_count_rows
AUTHID CURRENT_USER
AS
    v_count NUMBER;
BEGIN
    EXECUTE IMMEDIATE
        'SELECT COUNT(*) FROM lab_employee'
        INTO v_count;

    DBMS_OUTPUT.PUT_LINE(v_count);
END;
/
~~~

Dynamic SQL được phân tích ở runtime, nhưng không tự vượt qua mô hình bảo mật của Oracle. Quyền truy cập đối tượng, quyền hệ thống, role và ngữ cảnh definer/invoker vẫn có hiệu lực theo quy tắc của stored PL/SQL.

Đặc biệt, dynamic SQL trong definer-rights program cần được thiết kế cẩn thận. Nếu người gọi có thể điều khiển identifier hoặc predicate, chương trình có thể bị lợi dụng để thực hiện thao tác bằng quyền của chủ sở hữu. Dùng allowlist, bind variables và quyền tối thiểu.

## 19. Dependency và lỗi runtime của SQL động

SQL tĩnh cho phép compiler nhận biết các đối tượng được tham chiếu. Với SQL động, nội dung chuỗi thường chỉ được parse khi chạy:

~~~sql
EXECUTE IMMEDIATE
    'SELECT missing_column FROM missing_table';
~~~

Block PL/SQL chứa chuỗi trên có thể biên dịch dù bảng hoặc cột không tồn tại, vì câu SQL bên trong chuỗi chưa được compiler kiểm tra như static SQL. Khi thực thi, Oracle mới parse và báo lỗi như object không tồn tại hoặc invalid identifier.

Hệ quả:

- Lỗi chính tả tên bảng/cột có thể chỉ xuất hiện ở runtime.
- Đổi schema/object có thể làm một chuỗi SQL cũ thất bại.
- Test cần bao phủ các cấu hình SQL động khác nhau.
- Cần log câu SQL đã chuẩn hóa và mã lỗi đủ để điều tra, nhưng không log bí mật hoặc giá trị nhạy cảm.

## 20. Hiệu năng và parse của dynamic SQL

SQL động có thêm công việc tạo chuỗi và parse câu lệnh ở runtime. Oracle có thể tái sử dụng cursor khi câu SQL giống nhau và môi trường thực thi tương thích, nhưng tạo nhiều chuỗi khác nhau không cần thiết có thể làm giảm khả năng chia sẻ cursor.

### 20.1. Tránh literal thay đổi liên tục

Ví dụ kém thuận lợi:

~~~sql
v_sql :=
    'SELECT COUNT(*) FROM employees WHERE department_id = '
    || TO_CHAR(v_department_id);

EXECUTE IMMEDIATE v_sql INTO v_count;
~~~

Mỗi giá trị department có thể tạo một text SQL khác nhau. Cách tốt hơn:

~~~sql
v_sql :=
    'SELECT COUNT(*) FROM employees WHERE department_id = :dept';

EXECUTE IMMEDIATE v_sql
    INTO v_count
    USING v_department_id;
~~~

SQL text ổn định hơn và giá trị được bind riêng.

### 20.2. Hard parse và soft parse

- **Hard parse**: Oracle phải phân tích và tối ưu SQL mới hoặc không thể dùng cursor phù hợp.
- **Soft parse**: Oracle tìm được cursor có thể tái sử dụng trong shared pool và giảm công việc parse.

Bind variables có thể giúp nhiều lần thực thi dùng chung một SQL text. Tuy nhiên, cursor sharing còn phụ thuộc kiểu bind, schema, optimizer environment, quyền, object state và các yếu tố khác.

### 20.3. Không biến mọi SQL thành dynamic

Nếu câu SQL không thay đổi cấu trúc, static SQL thường:

- Dễ đọc và kiểm tra.
- Giảm rủi ro nối chuỗi không an toàn.
- Có dependency rõ ràng.
- Dễ kiểm tra compile-time.
- Dễ theo dõi trong công cụ phát triển.

Dynamic SQL chỉ nên được dùng khi tính linh hoạt runtime có giá trị thực sự.

## 21. Xử lý lỗi trong SQL động

Các lỗi thường xuất hiện:

- ORA-00942: table or view does not exist.
- ORA-00904: invalid identifier.
- ORA-01008: not all variables bound.
- ORA-01006: bind variable does not exist.
- ORA-01403: no data found.
- ORA-01422: exact fetch returns more than requested number of rows.
- ORA-01031: insufficient privileges.

Ví dụ xử lý:

~~~sql
DECLARE
    v_count NUMBER;
BEGIN
    EXECUTE IMMEDIATE
        'SELECT COUNT(*) FROM employees WHERE department_id = :d'
        INTO v_count
        USING 50;

    DBMS_OUTPUT.PUT_LINE(v_count);
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('No row returned');
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(
            'Error ' || SQLCODE || ': ' || SQLERRM
        );
        RAISE;
END;
/
~~~

COUNT(*) luôn trả một dòng, kể cả khi không có dòng thỏa điều kiện, nên NO_DATA_FOUND không phát sinh trong riêng ví dụ này. Handler chỉ minh họa cách tổ chức exception; trong ứng dụng thật, hãy bắt lỗi đúng tình huống và không nuốt lỗi ngoài dự kiến.

### 21.1. Log câu SQL và bind values

Khi điều tra lỗi, cần biết:

- SQL template nào được thực thi.
- Bind nào được truyền, theo kiểu và vị trí nào.
- Schema/current user và module/action liên quan.
- SQLCODE/SQLERRM và thời điểm.

Không ghi mật khẩu, token, thông tin cá nhân hoặc giá trị bí mật vào log. Có thể ghi mã định danh request và SQL template đã chuẩn hóa để liên kết sự kiện.

## 22. Transaction behavior của SQL động

EXECUTE IMMEDIATE không tự tạo transaction độc lập cho DML. Câu INSERT/UPDATE/DELETE động tham gia transaction hiện tại giống DML tĩnh:

~~~sql
BEGIN
    EXECUTE IMMEDIATE
        'UPDATE employees SET salary = salary + 100 WHERE employee_id = 100';

    ROLLBACK;
END;
/
~~~

UPDATE bị rollback nếu chưa có COMMIT trước đó. Ngược lại, DDL động vẫn chịu quy tắc implicit commit của Oracle.

Không đưa COMMIT hoặc ROLLBACK vào dynamic block một cách tùy tiện. Hãy thống nhất rõ tầng nào sở hữu transaction: caller hay procedure. Procedure được tái sử dụng thường nên tránh tự commit nếu caller cần kiểm soát nhiều bước nghiệp vụ trong cùng transaction.

## 23. Tiêu chí lựa chọn SQL tĩnh và SQL động

### 23.1. Bảng quyết định

| Câu hỏi | Nên ưu tiên |
|---|---|
| Bảng và cột đã biết khi viết chương trình? | SQL tĩnh |
| Chỉ giá trị WHERE thay đổi? | SQL tĩnh với bind variable |
| Có vài cấu trúc truy vấn cố định? | SQL tĩnh với IF/CASE |
| Tên bảng/cột thay đổi tại runtime? | SQL động với allowlist và kiểm tra identifier |
| Cần DDL ở runtime? | SQL động |
| Select list có số cột/kiểu cột không biết trước? | DBMS_SQL |
| Cần trả nhiều dòng có kiểu đã biết? | Cursor tĩnh hoặc OPEN FOR |
| Cần thực thi nhiều DML với cấu trúc cố định? | SQL tĩnh |
| Cần sinh SQL từ metadata hoặc cấu hình? | SQL động, cân nhắc DBMS_SQL |

### 23.2. Ví dụ lựa chọn theo tình huống

**Tình huống A — Tăng lương theo phòng ban**

~~~sql
UPDATE employees
SET salary = salary * 1.05
WHERE department_id = p_department_id;
~~~

Bảng, cột và cấu trúc cố định; chỉ giá trị department thay đổi. Dùng SQL tĩnh.

**Tình huống B — Chọn bảng lưu trữ theo năm**

Ứng dụng có bảng SALES_2024, SALES_2025, SALES_2026 và chọn bảng theo năm báo cáo. Tên bảng thay đổi tại runtime. Cần SQL động, nhưng năm phải được kiểm tra và ánh xạ sang tên bảng cho phép.

**Tình huống C — Báo cáo chọn cột sắp xếp**

Người dùng chọn sắp xếp theo DATE, CUSTOMER hoặc AMOUNT. Cần allowlist identifier và ghép tên cột đã xác thực; giá trị lọc vẫn dùng bind.

**Tình huống D — Công cụ quản trị xem bảng bất kỳ**

Người vận hành chọn bảng và muốn hiển thị các cột mà không biết trước số lượng/kiểu. DBMS_SQL có thể cần thiết để mô tả select list và đọc cột theo metadata.

## 24. Quy trình viết SQL động an toàn

Trước khi tạo câu SQL động:

1. Xác định phần nào thật sự cần thay đổi tại runtime.
2. Giữ tên bảng/cột cố định nếu có thể.
3. Dùng bind variables cho mọi giá trị dữ liệu.
4. Dùng allowlist cho identifier và keyword.
5. Dùng DBMS_ASSERT để kiểm tra identifier theo ngữ cảnh.
6. Không nối trực tiếp đầu vào không tin cậy vào SQL.
7. Kiểm tra số lượng, thứ tự và mode của bind.
8. Xử lý SELECT một dòng, nhiều dòng và DML theo đúng API.
9. Xử lý cursor/exception để không rò rỉ cursor.
10. Kiểm tra quyền thực thi và transaction behavior.
11. Test mọi cấu hình chuỗi SQL có thể sinh ra.
12. Đo parse, execution plan và runtime trên workload đại diện.

Sơ đồ:

~~~text
Cần SQL động?
      |
      v
Cấu trúc SQL có thật sự thay đổi?
       /             \
     Không            Có
      |                |
      v                v
 SQL tĩnh         Phân loại phần thay đổi
                       |
              +--------+---------+
              |                  |
           Giá trị            Identifier/DDL
              |                  |
              v                  v
         Bind variable       Allowlist + DBMS_ASSERT
              |                  |
              +--------+---------+
                       |
                       v
                Chọn NDS hay DBMS_SQL
                       |
                       v
             Kiểm tra bind và kiểu kết quả
                       |
                       v
              Quyền, transaction, lỗi
                       |
                       v
               Test và đo runtime
~~~

## 25. Bài tập thực hành

### Bài 1 — Nhận diện SQL tĩnh

Viết procedure tăng lương nhân viên theo employee_id. Dùng tham số PL/SQL trong WHERE.

**Câu hỏi:** Vì sao đây là SQL tĩnh dù giá trị employee_id thay đổi mỗi lần gọi?

### Bài 2 — EXECUTE IMMEDIATE với bind

Viết block cập nhật salary theo department_id và mức tăng truyền bằng biến. In SQL%ROWCOUNT.

### Bài 3 — SELECT động một dòng

Viết EXECUTE IMMEDIATE lấy last_name theo employee_id. Xử lý NO_DATA_FOUND và TOO_MANY_ROWS phù hợp.

### Bài 4 — OPEN FOR

Viết cursor động đọc employee_id, last_name và salary theo department_id. Fetch từng dòng rồi đóng cursor cả khi có lỗi.

### Bài 5 — Tên bảng động

Viết procedure cho phép chọn một trong ba bảng lab đã định nghĩa sẵn. Dùng CASE/allowlist để xác thực tên bảng và bind giá trị lọc.

### Bài 6 — SQL injection

Tạo ví dụ nối trực tiếp last_name vào câu SQL và giải thích rủi ro khi đầu vào chứa dấu nháy. Viết lại bằng bind variable.

### Bài 7 — DBMS_ASSERT

Dùng SIMPLE_SQL_NAME kiểm tra tên đơn giản. Giải thích vì sao vẫn cần allowlist đối tượng nghiệp vụ.

### Bài 8 — Dynamic DDL

Dùng EXECUTE IMMEDIATE tạo bảng lab có tên được chọn từ danh sách cho phép. Giải thích tác động implicit commit của DDL.

### Bài 9 — NDS và DBMS_SQL

Một báo cáo có số cột thay đổi theo lựa chọn runtime. Giải thích vì sao DBMS_SQL phù hợp hơn SELECT INTO hoặc OPEN FOR với record cố định.

### Bài 10 — Lựa chọn kiến trúc

Một procedure nhận department_id, min_salary, sort_column và tên bảng archive. Phân loại từng tham số:

- Giá trị dữ liệu nào cần bind?
- Identifier nào cần allowlist?
- Có thể giữ phần nào thành SQL tĩnh?
- Khi nào cần DBMS_SQL?

## 26. Những lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách xử lý |
|---|---|---|
| ORA-00942 | Tên bảng/view sai hoặc không có quyền | Kiểm tra schema, object và grant |
| ORA-00904 | Tên cột hoặc identifier sai | Xác thực tên cột, xem metadata |
| ORA-01008 | Thiếu bind argument | Đối chiếu placeholder và USING |
| ORA-01006 | Bind placeholder không tồn tại | Kiểm tra chuỗi SQL và danh sách bind |
| ORA-01403 | SELECT INTO không có dòng | Xử lý NO_DATA_FOUND hoặc thay đổi logic |
| ORA-01422 | SELECT INTO trả nhiều dòng | Dùng cursor/BULK COLLECT hoặc giới hạn kết quả |
| SQL injection | Nối đầu vào không tin cậy vào SQL | Bind values, allowlist identifiers |
| Cursor chưa đóng | Exception thoát trước CLOSE | Đóng cursor trong exception handler |
| SQL động parse nhiều lần | SQL text thay đổi do nối literal | Dùng bind để giữ text ổn định |
| DDL làm commit DML trước đó | DDL implicit commit | Tách schema maintenance khỏi transaction nghiệp vụ |
| Procedure chạy thiếu quyền | Ngữ cảnh AUTHID/grant không phù hợp | Kiểm tra quyền trực tiếp, role và invoker/definer rights |

## 27. Kết luận lựa chọn

SQL tĩnh phù hợp khi cấu trúc câu lệnh đã biết và chỉ có giá trị dữ liệu thay đổi. SQL động phù hợp khi chính cấu trúc SQL hoặc identifier phải được xác định ở runtime. Với dynamic SQL, hãy ưu tiên Native Dynamic SQL nếu số lượng và kiểu bind/result đã biết; dùng DBMS_SQL khi cần xử lý cấu trúc kết quả tổng quát không biết trước.

Giá trị dữ liệu nên được bind. Tên bảng, tên cột và cú pháp thay đổi phải được kiểm soát bằng allowlist và kiểm tra identifier. DDL động vẫn có implicit commit; DML động vẫn tham gia transaction hiện tại. Khi chọn đúng công cụ và giữ ranh giới giữa dữ liệu với cú pháp, chương trình PL/SQL sẽ dễ bảo trì, an toàn hơn và có hành vi thực thi dễ dự đoán.
