# Anonymous block, DECLARE, BEGIN, EXCEPTION và END trong PL/SQL

## 1. PL/SQL block là đơn vị cấu trúc cơ bản

PL/SQL là ngôn ngữ thủ tục mở rộng SQL của Oracle. SQL mô tả dữ liệu cần truy vấn hoặc thay đổi; PL/SQL bổ sung biến, điều kiện, vòng lặp, xử lý lỗi và khả năng nhóm nhiều câu lệnh thành một đơn vị thực thi.

Đơn vị cơ bản của PL/SQL là **block** (khối lệnh). Một block có thể khai báo biến, thực hiện câu lệnh và xử lý exception. Block có thể là:

- **Anonymous block:** khối lệnh không có tên, không được lưu như một procedure/function độc lập trong schema. Thường dùng để chạy thử, thực hiện một tác vụ ngắn, gọi logic hoặc làm script triển khai.
- **Named block:** chương trình có tên được lưu trong schema, ví dụ procedure, function, package hoặc trigger. Các đối tượng này có thể được gọi lại theo tên và có vòng đời riêng trong database.

Một anonymous block điển hình:

```sql
DECLARE
    v_message VARCHAR2(100);
BEGIN
    v_message := 'Hello PL/SQL';
    DBMS_OUTPUT.PUT_LINE(v_message);
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE('An error occurred: ' || SQLERRM);
        RAISE;
END;
/
```

Block có bốn phần:

| Phần | Bắt buộc? | Mục đích |
|---|---|---|
| `DECLARE` | Không | Khai báo biến, hằng, kiểu, cursor và exception cục bộ |
| `BEGIN` | Có | Chứa các câu lệnh thực thi |
| `EXCEPTION` | Không | Xử lý các exception phát sinh trong phần thực thi |
| `END` | Có | Kết thúc block |

Điểm cần nhớ: `DECLARE` và `EXCEPTION` là tùy chọn; `BEGIN` và `END` luôn cần có. Dấu `/` ở dòng riêng trong ví dụ là lệnh của client như SQL*Plus/SQLcl để gửi block đã nhập đến Oracle, không phải một phần cú pháp PL/SQL.

Bài học thuộc chương **PL/SQL cơ bản**, tập trung vào cấu trúc anonymous block và vai trò của `DECLARE`, `BEGIN`, `EXCEPTION`, `END`; cách khai báo biến/hằng, thực thi SQL và câu lệnh PL/SQL, xử lý lỗi, lồng block, phạm vi biến, quản lý transaction và chạy block từ công cụ hoặc Java.

## 2. Cấu trúc tổng quát của anonymous block

Cú pháp:

```sql
[DECLARE
    -- declarations
]
BEGIN
    -- executable statements
[EXCEPTION
    -- exception handlers
]
END;
/
```

Các quy tắc:

1. `DECLARE` chỉ xuất hiện khi block cần khai báo phần tử cục bộ.
2. Phần khai báo kết thúc khi gặp `BEGIN`.
3. Mọi câu lệnh thực thi nằm giữa `BEGIN` và `EXCEPTION` hoặc `END`.
4. `EXCEPTION` bắt đầu phần xử lý lỗi; các handler không phải câu lệnh tiếp tục của phần `BEGIN`.
5. `END;` đóng block.
6. Dấu chấm phẩy kết thúc các câu lệnh PL/SQL; dấu `/` là terminator của script client trong một số công cụ.

### 2.1. Block tối thiểu

Không cần khai báo biến thì có thể bỏ `DECLARE`:

```sql
BEGIN
    DBMS_OUTPUT.PUT_LINE('PL/SQL is running');
END;
/
```

Block này có một câu lệnh thực thi và không có handler riêng.

### 2.2. Block có DECLARE

```sql
DECLARE
    v_count NUMBER := 0;
BEGIN
    v_count := v_count + 1;
    DBMS_OUTPUT.PUT_LINE('Count = ' || v_count);
END;
/
```

`v_count` chỉ tồn tại trong thời gian thực thi block và các block con có thể truy cập nó theo quy tắc scope.

### 2.3. Block có EXCEPTION

```sql
BEGIN
    DBMS_OUTPUT.PUT_LINE(10 / 0);
EXCEPTION
    WHEN ZERO_DIVIDE THEN
        DBMS_OUTPUT.PUT_LINE('Cannot divide by zero');
END;
/
```

Khi phép chia gây `ZERO_DIVIDE`, luồng thực thi rời phần `BEGIN` và chuyển đến handler tương ứng. Sau khi handler hoàn tất bình thường, block kết thúc.

### 2.4. Block không có EXCEPTION

```sql
BEGIN
    UPDATE accounts
    SET status = 'ACTIVE'
    WHERE account_id = 100;
END;
/
```

Nếu câu UPDATE phát sinh lỗi, exception truyền ra caller vì block không có handler. Việc không viết `EXCEPTION` không làm lỗi biến mất.

## 3. Vai trò của DECLARE

`DECLARE` mở đầu vùng khai báo. Phần này có thể chứa:

- Biến và hằng.
- Kiểu dữ liệu và record type cục bộ.
- Cursor tường minh.
- Exception do người dùng định nghĩa.
- Subprogram cục bộ (procedure/function).
- Pragma được phép trong ngữ cảnh khai báo.

Các khai báo được viết trước `BEGIN`. Không đặt câu lệnh thực thi thông thường như `UPDATE`, `IF` hoặc `DBMS_OUTPUT.PUT_LINE` trực tiếp trong vùng này.

### 3.1. Khai báo biến

```sql
DECLARE
    v_employee_id NUMBER;
    v_employee_name VARCHAR2(100);
    v_salary NUMBER(10, 2);
BEGIN
    v_employee_id := 100;
    v_employee_name := 'An Nguyen';
    v_salary := 25000;

    DBMS_OUTPUT.PUT_LINE(
        v_employee_name || ' has salary ' || v_salary
    );
END;
/
```

Quy ước đặt tên như `v_` cho variable chỉ là convention, không phải yêu cầu của Oracle. Tên biến không được trùng hoặc gây mơ hồ với tên cột trong SQL nhúng.

### 3.2. Khai báo biến có giá trị mặc định

Có thể khởi tạo biến bằng `:=` hoặc `DEFAULT`:

```sql
DECLARE
    v_attempts NUMBER := 0;
    v_status VARCHAR2(20) DEFAULT 'NEW';
BEGIN
    v_attempts := v_attempts + 1;
    DBMS_OUTPUT.PUT_LINE(v_status || ', attempts=' || v_attempts);
END;
/
```

Nếu không khởi tạo, biến kiểu scalar thường có giá trị NULL ban đầu. Phép toán với NULL thường cho kết quả NULL, nên cần chủ động gán giá trị nếu logic yêu cầu.

### 3.3. Khai báo hằng số

Hằng số dùng từ khóa `CONSTANT` và phải được khởi tạo trong khai báo:

```sql
DECLARE
    c_tax_rate CONSTANT NUMBER := 0.10;
    v_amount NUMBER := 1000;
    v_tax NUMBER;
BEGIN
    v_tax := v_amount * c_tax_rate;
    DBMS_OUTPUT.PUT_LINE('Tax = ' || v_tax);
END;
/
```

Sau khi khai báo, không thể gán giá trị mới cho `c_tax_rate`. Hằng số giúp thể hiện những giá trị không được thay đổi trong phạm vi block.

### 3.4. Biến NOT NULL

Biến khai báo `NOT NULL` phải có giá trị khởi tạo khác NULL:

```sql
DECLARE
    v_department_id NUMBER NOT NULL := 10;
BEGIN
    DBMS_OUTPUT.PUT_LINE(v_department_id);
END;
/
```

Nếu bỏ initializer hoặc gán NULL cho biến NOT NULL, PL/SQL có thể phát sinh lỗi. Chỉ dùng NOT NULL khi giá trị thực sự luôn bắt buộc.

### 3.5. Dùng %TYPE để bám kiểu cột

`%TYPE` khai báo biến theo kiểu của một cột hoặc biến khác:

```sql
DECLARE
    v_employee_id employees.employee_id%TYPE;
    v_salary employees.salary%TYPE;
BEGIN
    v_employee_id := 100;
    v_salary := 30000;
END;
/
```

Lợi ích:

- Giảm lặp lại kiểu dữ liệu trong code.
- Khi kiểu cột thay đổi, khai báo có thể theo kiểu mới sau khi compile lại.
- Giúp biến tương thích hơn với cột nguồn.

`%TYPE` không tự động sao chép mọi constraint của cột, ví dụ NOT NULL constraint không nhất thiết được kế thừa thành hành vi NOT NULL của biến. Nếu biến phải NOT NULL, khai báo rõ.

### 3.6. Dùng %ROWTYPE để giữ một hàng

`%ROWTYPE` khai báo record có cấu trúc theo hàng của bảng hoặc cursor:

```sql
DECLARE
    v_employee employees%ROWTYPE;
BEGIN
    SELECT *
    INTO v_employee
    FROM employees
    WHERE employee_id = 100;

    DBMS_OUTPUT.PUT_LINE(v_employee.last_name);
    DBMS_OUTPUT.PUT_LINE(v_employee.salary);
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('Employee not found');
END;
/
```

Record `v_employee` có các field tương ứng với cột của `EMPLOYEES`. Dùng `%ROWTYPE` hữu ích khi cần lấy cả hàng; nếu chỉ cần vài cột, có thể khai báo biến riêng và SELECT đúng các cột đó.

## 4. Kiểu dữ liệu và record trong vùng khai báo

### 4.1. Các kiểu scalar thường gặp

| Kiểu | Dùng cho |
|---|---|
| `NUMBER` | Số nguyên và số thập phân |
| `VARCHAR2(n)` | Chuỗi ký tự có độ dài tối đa |
| `CHAR(n)` | Chuỗi có độ dài cố định |
| `DATE` | Ngày và thời gian đến giây |
| `TIMESTAMP` | Ngày giờ có độ chính xác phần giây |
| `BOOLEAN` | Giá trị TRUE/FALSE/NULL trong PL/SQL |
| `CLOB` | Dữ liệu ký tự lớn |
| `BLOB` | Dữ liệu nhị phân lớn |

`BOOLEAN` là kiểu PL/SQL; không phải kiểu cột SQL truyền thống trong nhiều phiên bản Oracle trước 23c/23ai. Khả năng SQL BOOLEAN phụ thuộc phiên bản Oracle Database. Khi viết code tương thích nhiều phiên bản, không giả định cột BOOLEAN tồn tại trong bảng.

### 4.2. Tạo record type cục bộ

```sql
DECLARE
    TYPE employee_summary_t IS RECORD (
        employee_id NUMBER,
        full_name VARCHAR2(150),
        annual_salary NUMBER
    );

    v_summary employee_summary_t;
BEGIN
    v_summary.employee_id := 100;
    v_summary.full_name := 'An Nguyen';
    v_summary.annual_salary := 360000;

    DBMS_OUTPUT.PUT_LINE(v_summary.full_name);
END;
/
```

`RECORD` nhóm nhiều field có thể có kiểu khác nhau thành một biến có cấu trúc. Đây là record PL/SQL cục bộ, khác object type được tạo ở cấp schema bằng `CREATE TYPE`.

### 4.3. Gán record

Hai record cùng kiểu tương thích có thể được gán theo quy tắc PL/SQL:

```sql
DECLARE
    TYPE amount_info_t IS RECORD (
        net_amount NUMBER,
        tax_amount NUMBER
    );

    v_a amount_info_t;
    v_b amount_info_t;
BEGIN
    v_a.net_amount := 1000;
    v_a.tax_amount := 100;

    v_b := v_a;
END;
/
```

Không giả định mọi record có cùng field name nhưng được khai báo độc lập đều có thể gán trực tiếp cho nhau. Hãy dùng cùng một record type hoặc gán field riêng khi cần.

## 5. Vai trò của BEGIN

`BEGIN` bắt đầu phần executable section. Đây là phần bắt buộc của mọi block PL/SQL và chứa các câu lệnh được thực hiện theo thứ tự.

Các câu lệnh thường gặp:

- Gán biến bằng `:=`.
- Gọi procedure hoặc function.
- `SELECT ... INTO`.
- DML: `INSERT`, `UPDATE`, `DELETE`, `MERGE`.
- Điều kiện `IF`, `CASE`.
- Vòng lặp `LOOP`, `WHILE`, `FOR`.
- Lệnh `NULL`.
- Block PL/SQL lồng bên trong.

### 5.1. Gán và tính toán

```sql
DECLARE
    v_quantity NUMBER := 3;
    v_unit_price NUMBER := 15000;
    v_total NUMBER;
BEGIN
    v_total := v_quantity * v_unit_price;
    DBMS_OUTPUT.PUT_LINE('Total = ' || v_total);
END;
/
```

Trong PL/SQL, `:=` dùng để gán biến. Dấu `=` dùng trong điều kiện so sánh; không dùng `=` thay cho `:=` khi gán.

### 5.2. SELECT INTO

`SELECT ... INTO` đưa kết quả truy vấn vào biến PL/SQL:

```sql
DECLARE
    v_name employees.last_name%TYPE;
    v_salary employees.salary%TYPE;
BEGIN
    SELECT last_name, salary
    INTO v_name, v_salary
    FROM employees
    WHERE employee_id = 100;

    DBMS_OUTPUT.PUT_LINE(v_name || ': ' || v_salary);
END;
/
```

Đối với SELECT INTO thông thường:

- Trả đúng một hàng: gán giá trị vào các biến.
- Không trả hàng: phát sinh `NO_DATA_FOUND`.
- Trả nhiều hơn một hàng: phát sinh `TOO_MANY_ROWS`.

Số cột trong SELECT list phải khớp số biến trong INTO và kiểu dữ liệu phải tương thích.

### 5.3. Dùng aggregate để luôn nhận một hàng

Aggregate không có GROUP BY như `COUNT(*)` thường trả một hàng ngay cả khi không có hàng nguồn:

```sql
DECLARE
    v_count NUMBER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM employees
    WHERE department_id = 999;

    DBMS_OUTPUT.PUT_LINE('Employees = ' || v_count);
END;
/
```

Kết quả là 0 nếu không có nhân viên phù hợp. Với `SUM`, `AVG`, `MIN`, `MAX`, khi không có giá trị đầu vào, kết quả có thể là NULL; riêng `COUNT` trả 0.

### 5.4. Thực hiện DML

```sql
BEGIN
    UPDATE employees
    SET salary = salary * 1.05
    WHERE department_id = 10;

    DBMS_OUTPUT.PUT_LINE(
        'Updated rows = ' || SQL%ROWCOUNT
    );
END;
/
```

`SQL%ROWCOUNT` trả số hàng bị tác động bởi câu SQL implicit cursor gần nhất. Đọc ngay sau DML cần kiểm tra; nếu chạy một câu SQL khác trước đó, thuộc tính sẽ phản ánh câu SQL mới.

### 5.5. INSERT và RETURNING INTO

```sql
DECLARE
    v_new_id employees.employee_id%TYPE;
BEGIN
    INSERT INTO employee_audit (
        employee_id,
        action_name,
        action_time
    )
    VALUES (
        100,
        'REVIEWED',
        SYSTIMESTAMP
    )
    RETURNING employee_id INTO v_new_id;

    DBMS_OUTPUT.PUT_LINE('Employee = ' || v_new_id);
END;
/
```

`RETURNING INTO` lấy giá trị từ hàng vừa được DML tác động. Ví dụ giả định INSERT đúng một hàng; với DML nhiều hàng cần cơ chế phù hợp như `RETURNING BULK COLLECT INTO` trong PL/SQL khi được hỗ trợ.

### 5.6. IF và ELSIF

```sql
DECLARE
    v_score NUMBER := 82;
    v_result VARCHAR2(20);
BEGIN
    IF v_score >= 90 THEN
        v_result := 'EXCELLENT';
    ELSIF v_score >= 75 THEN
        v_result := 'GOOD';
    ELSIF v_score >= 50 THEN
        v_result := 'PASS';
    ELSE
        v_result := 'FAIL';
    END IF;

    DBMS_OUTPUT.PUT_LINE(v_result);
END;
/
```

Mỗi IF phải có `END IF;`. Điều kiện có thể kết hợp `AND`, `OR`, `NOT` và các phép so sánh.

### 5.7. Vòng lặp

Vòng lặp cơ bản:

```sql
DECLARE
    v_counter PLS_INTEGER := 1;
BEGIN
    LOOP
        DBMS_OUTPUT.PUT_LINE(v_counter);
        v_counter := v_counter + 1;
        EXIT WHEN v_counter > 3;
    END LOOP;
END;
/
```

Vòng lặp WHILE:

```sql
DECLARE
    v_counter PLS_INTEGER := 1;
BEGIN
    WHILE v_counter <= 3 LOOP
        DBMS_OUTPUT.PUT_LINE(v_counter);
        v_counter := v_counter + 1;
    END LOOP;
END;
/
```

Vòng lặp FOR:

```sql
BEGIN
    FOR i IN 1..3 LOOP
        DBMS_OUTPUT.PUT_LINE('Iteration ' || i);
    END LOOP;
END;
/
```

Biến `i` của FOR loop được khai báo ngầm trong phạm vi vòng lặp; không cần khai báo trong DECLARE và không nên gán lại biến điều khiển vòng lặp.

### 5.8. NULL statement

`NULL;` là câu lệnh hợp lệ không thực hiện hành động:

```sql
BEGIN
    IF 1 = 1 THEN
        NULL;
    END IF;
END;
/
```

Nó hữu ích khi cần một nhánh rỗng hợp lệ hoặc tạo khung code trong quá trình phát triển. Không nhầm `NULL;` statement với giá trị NULL.

## 6. Vai trò của EXCEPTION

`EXCEPTION` bắt đầu phần xử lý lỗi của block. Khi một exception được phát sinh trong phần executable hoặc trong lời gọi được thực hiện từ đó, PL/SQL tìm handler phù hợp.

Nếu tìm thấy handler:

1. Phần executable còn lại của block bị bỏ qua.
2. Oracle chạy handler tương ứng.
3. Nếu handler kết thúc bình thường, block kết thúc.
4. Nếu handler phát sinh hoặc re-raise exception, lỗi truyền ra block/caller bên ngoài.

Nếu không có handler phù hợp, exception truyền ra enclosing block hoặc môi trường gọi.

### 6.1. Cú pháp handler

```sql
BEGIN
    -- executable statements
EXCEPTION
    WHEN exception_name THEN
        -- handling statements
    WHEN another_exception THEN
        -- another handling path
    WHEN OTHERS THEN
        -- catch remaining exceptions
END;
/
```

Mỗi handler bắt đầu bằng `WHEN`. `OTHERS` bắt các exception chưa được xử lý bởi handler cụ thể và nên đặt cuối cùng.

### 6.2. Xử lý NO_DATA_FOUND

```sql
DECLARE
    v_name employees.last_name%TYPE;
BEGIN
    SELECT last_name
    INTO v_name
    FROM employees
    WHERE employee_id = -1;

    DBMS_OUTPUT.PUT_LINE(v_name);
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('No employee matched the ID');
END;
/
```

Nếu SELECT không trả hàng, câu lệnh tiếp theo trong phần BEGIN không được thực hiện; luồng chuyển đến handler.

### 6.3. Xử lý TOO_MANY_ROWS

```sql
DECLARE
    v_salary employees.salary%TYPE;
BEGIN
    SELECT salary
    INTO v_salary
    FROM employees
    WHERE department_id = 10;

    DBMS_OUTPUT.PUT_LINE(v_salary);
EXCEPTION
    WHEN TOO_MANY_ROWS THEN
        DBMS_OUTPUT.PUT_LINE(
            'The query returned more than one employee'
        );
END;
/
```

Nếu nghiệp vụ cần nhiều hàng, đừng cố bắt `TOO_MANY_ROWS` rồi chọn tùy tiện một kết quả. Hãy dùng cursor, cursor FOR loop hoặc điều kiện đảm bảo một hàng.

### 6.4. Một số predefined exceptions thường gặp

| Exception | Tình huống phổ biến |
|---|---|
| `NO_DATA_FOUND` | SELECT INTO không trả hàng |
| `TOO_MANY_ROWS` | SELECT INTO trả nhiều hơn một hàng |
| `ZERO_DIVIDE` | Chia cho 0 |
| `DUP_VAL_ON_INDEX` | INSERT/UPDATE vi phạm unique index hoặc constraint |
| `VALUE_ERROR` | Lỗi chuyển đổi hoặc giá trị không phù hợp với biến |
| `INVALID_NUMBER` | Chuyển chuỗi sang số không hợp lệ trong một số ngữ cảnh |
| `CURSOR_ALREADY_OPEN` | Mở cursor tường minh đã mở |
| `INVALID_CURSOR` | Thao tác cursor không hợp lệ |
| `COLLECTION_IS_NULL` | Gọi method trên collection atomically NULL |
| `CASE_NOT_FOUND` | CASE statement không có nhánh phù hợp và không có ELSE |

Oracle định nghĩa nhiều predefined exceptions trong package `STANDARD`; có thể dùng trực tiếp trong handler mà không cần khai báo.

### 6.5. Xử lý DUP_VAL_ON_INDEX

```sql
BEGIN
    INSERT INTO departments (department_id, department_name)
    VALUES (10, 'Engineering');
EXCEPTION
    WHEN DUP_VAL_ON_INDEX THEN
        DBMS_OUTPUT.PUT_LINE(
            'A row with the same unique key already exists'
        );
END;
/
```

Exception có thể xuất hiện do trùng khóa chính hoặc unique key. Trong ứng dụng thật, cần xác định đó là dữ liệu đã tồn tại hợp lệ hay lỗi nghiệp vụ; không nên bỏ qua mọi trường hợp trùng mà không kiểm tra.

### 6.6. Dùng WHEN OTHERS

```sql
BEGIN
    -- statements that may fail
    NULL;
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(
            'Error ' || SQLCODE || ': ' || SQLERRM
        );
        RAISE;
END;
/
```

`WHEN OTHERS` bắt các exception còn lại. Khi log lỗi rồi `RAISE;`, exception gốc được ném lại để caller biết thao tác thất bại.

Không dùng handler kiểu:

```sql
WHEN OTHERS THEN
    NULL;
```

trừ khi có chủ đích rất cụ thể và đã xử lý hậu quả. Nuốt lỗi làm ứng dụng tưởng thao tác thành công dù dữ liệu có thể chưa được cập nhật.

## 7. SQLCODE và SQLERRM

Trong exception handler:

- `SQLCODE` trả mã số của exception hiện tại.
- `SQLERRM` trả thông báo lỗi.

Ví dụ:

```sql
BEGIN
    DECLARE
        v_result NUMBER;
    BEGIN
        v_result := 10 / 0;
    END;
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE('SQLCODE=' || SQLCODE);
        DBMS_OUTPUT.PUT_LINE('SQLERRM=' || SQLERRM);
        RAISE;
END;
/
```

`SQLERRM` hữu ích cho chẩn đoán, nhưng không nên dùng chuỗi thông báo làm logic nghiệp vụ vì nội dung có thể thay đổi theo ngôn ngữ hoặc phiên bản. Hãy xử lý theo exception name hoặc mã lỗi phù hợp.

### 7.1. Ghi log rồi re-raise

Một pattern:

```sql
DECLARE
    v_order_id NUMBER := 1001;
BEGIN
    UPDATE orders
    SET status = 'PAID'
    WHERE order_id = v_order_id;

    IF SQL%ROWCOUNT = 0 THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Order does not exist: ' || v_order_id
        );
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(
            'Failed order=' || v_order_id ||
            ', code=' || SQLCODE ||
            ', message=' || SQLERRM
        );
        RAISE;
END;
/
```

Ví dụ dùng DBMS_OUTPUT để minh họa. Trong production, log nên được ghi bằng cơ chế logging có thiết kế rõ ràng; không mặc định DBMS_OUTPUT là log bền vững.

## 8. Exception do người dùng định nghĩa

Ngoài predefined exceptions, có thể định nghĩa exception theo nghiệp vụ.

### 8.1. Khai báo và RAISE exception

```sql
DECLARE
    e_invalid_salary EXCEPTION;
    v_salary NUMBER := -100;
BEGIN
    IF v_salary < 0 THEN
        RAISE e_invalid_salary;
    END IF;

    DBMS_OUTPUT.PUT_LINE('Salary is valid');
EXCEPTION
    WHEN e_invalid_salary THEN
        DBMS_OUTPUT.PUT_LINE('Salary cannot be negative');
END;
/
```

`e_invalid_salary` được khai báo trong DECLARE và được kích hoạt bằng `RAISE`. Handler dùng đúng tên exception để xử lý.

### 8.2. Dùng RAISE_APPLICATION_ERROR

Nếu muốn trả mã lỗi ứng dụng và thông điệp rõ ràng:

```sql
BEGIN
    RAISE_APPLICATION_ERROR(
        -20010,
        'The requested quantity exceeds available stock'
    );
END;
/
```

Mã lỗi do ứng dụng định nghĩa phải nằm trong khoảng `-20000` đến `-20999`. `RAISE_APPLICATION_ERROR` thường dùng để báo lỗi nghiệp vụ từ PL/SQL cho caller.

Ví dụ kiểm tra số lượng:

```sql
DECLARE
    v_requested_qty NUMBER := 5;
    v_available_qty NUMBER := 3;
BEGIN
    IF v_requested_qty > v_available_qty THEN
        RAISE_APPLICATION_ERROR(
            -20011,
            'Insufficient stock'
        );
    END IF;
END;
/
```

### 8.3. Ánh xạ mã Oracle sang tên exception với PRAGMA EXCEPTION_INIT

Có thể gắn một exception name với mã lỗi Oracle:

```sql
DECLARE
    e_resource_busy EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_resource_busy, -54);
BEGIN
    -- Một thao tác có thể phát sinh ORA-00054.
    NULL;
EXCEPTION
    WHEN e_resource_busy THEN
        DBMS_OUTPUT.PUT_LINE('Resource is busy');
END;
/
```

`PRAGMA EXCEPTION_INIT` giúp handler dùng tên có ý nghĩa thay vì phải dựa vào `WHEN OTHERS`. Mã truyền vào là mã số âm tương ứng với lỗi Oracle, ví dụ ORA-00054 dùng `-54`.

## 9. Exception propagation và block lồng nhau

PL/SQL cho phép đặt một block bên trong block khác. Block con có DECLARE, BEGIN, EXCEPTION và END riêng.

```sql
DECLARE
    v_message VARCHAR2(100) := 'Outer block';
BEGIN
    DBMS_OUTPUT.PUT_LINE(v_message);

    DECLARE
        v_count NUMBER := 10;
    BEGIN
        DBMS_OUTPUT.PUT_LINE('Inner count=' || v_count);
    END;

    DBMS_OUTPUT.PUT_LINE('Back to outer block');
END;
/
```

Block con có thể truy cập biến của block cha theo quy tắc scope; block cha không thể truy cập biến cục bộ chỉ được khai báo bên trong block con sau khi block con kết thúc.

### 9.1. Handler của block con

```sql
BEGIN
    DBMS_OUTPUT.PUT_LINE('Outer begins');

    BEGIN
        DBMS_OUTPUT.PUT_LINE(10 / 0);
    EXCEPTION
        WHEN ZERO_DIVIDE THEN
            DBMS_OUTPUT.PUT_LINE('Handled in inner block');
    END;

    DBMS_OUTPUT.PUT_LINE('Outer continues');
END;
/
```

Exception được xử lý trong block con, vì vậy block cha tiếp tục chạy sau khi block con kết thúc bình thường.

### 9.2. Exception không được xử lý ở block con

```sql
BEGIN
    DBMS_OUTPUT.PUT_LINE('Outer begins');

    BEGIN
        DBMS_OUTPUT.PUT_LINE(10 / 0);
    END;

    DBMS_OUTPUT.PUT_LINE('This line is skipped');
EXCEPTION
    WHEN ZERO_DIVIDE THEN
        DBMS_OUTPUT.PUT_LINE('Handled by outer block');
END;
/
```

Block con không có handler nên exception truyền ra block cha. Dòng `This line is skipped` không được thực hiện; handler của block cha xử lý lỗi.

### 9.3. Exception phát sinh trong handler

Nếu một handler phát sinh exception mới, exception mới truyền ra block bao ngoài; cùng block không quay lại tìm handler khác trong chính phần EXCEPTION của nó.

Có thể dùng block lồng để xử lý lỗi trong chính logic xử lý lỗi:

```sql
BEGIN
    -- Main work
    NULL;
EXCEPTION
    WHEN OTHERS THEN
        BEGIN
            -- Attempt secondary logging.
            DBMS_OUTPUT.PUT_LINE(SQLERRM);
        EXCEPTION
            WHEN OTHERS THEN
                NULL; -- Only if logging failure is deliberately ignored.
        END;

        RAISE;
END;
/
```

Trong ví dụ, block con bao quanh việc log để lỗi khi log có thể được xử lý riêng; sau đó `RAISE` ở handler ngoài ném lại lỗi chính. Trong hệ thống thật, nên thiết kế logging sao cho không làm mất lỗi gốc.

### 9.4. Exception trong phần DECLARE

Exception phát sinh khi khởi tạo biến trong vùng khai báo không được xử lý bởi EXCEPTION handler của chính block đó; nó truyền ra block bao ngoài. Nếu cần xử lý lỗi khởi tạo, hãy dùng block con riêng:

```sql
BEGIN
    DECLARE
        v_number NUMBER := TO_NUMBER('not-a-number');
    BEGIN
        DBMS_OUTPUT.PUT_LINE(v_number);
    EXCEPTION
        WHEN OTHERS THEN
            DBMS_OUTPUT.PUT_LINE('Inner executable handler');
    END;
EXCEPTION
    WHEN INVALID_NUMBER THEN
        DBMS_OUTPUT.PUT_LINE('Handled by outer block');
END;
/
```

Trong ví dụ, lỗi chuyển đổi phát sinh khi khởi tạo `v_number`, trước khi phần BEGIN của block con bắt đầu. Handler của block con không bắt được lỗi đó; block ngoài có thể xử lý theo exception phù hợp.

## 10. Phạm vi biến và tên block

### 10.1. Scope của biến

Biến khai báo trong một block chỉ có hiệu lực trong block đó và các block con lồng bên trong.

```sql
DECLARE
    v_value NUMBER := 10;
BEGIN
    DECLARE
        v_inner NUMBER := 20;
    BEGIN
        DBMS_OUTPUT.PUT_LINE(v_value); -- outer variable
        DBMS_OUTPUT.PUT_LINE(v_inner); -- inner variable
    END;

    DBMS_OUTPUT.PUT_LINE(v_value);
    -- v_inner không còn nằm trong scope tại đây.
END;
/
```

### 10.2. Biến cùng tên trong block lồng

Nếu block con khai báo biến cùng tên, biến cục bộ của block con che khuất biến cùng tên ở block ngoài trong phạm vi block con:

```sql
<<outer_block>>
DECLARE
    v_status VARCHAR2(20) := 'OUTER';
BEGIN
    DECLARE
        v_status VARCHAR2(20) := 'INNER';
    BEGIN
        DBMS_OUTPUT.PUT_LINE(v_status);
        DBMS_OUTPUT.PUT_LINE(outer_block.v_status);
    END;
END outer_block;
/
```

Label `outer_block` cho phép tham chiếu rõ biến ở block ngoài khi có tên bị che khuất. Không lạm dụng biến cùng tên ở nhiều scope vì có thể làm code khó đọc.

### 10.3. Đặt tên block

Có thể đặt label trước block và lặp lại label ở END:

```sql
<<process_order>>
DECLARE
    v_order_id NUMBER := 1001;
BEGIN
    DBMS_OUTPUT.PUT_LINE('Order ' || v_order_id);
END process_order;
/
```

Tên block là tùy chọn. Label hữu ích khi có block lồng hoặc cần tham chiếu biến ở scope bên ngoài.

## 11. Cursor trong anonymous block

Khi SELECT trả nhiều hàng, có thể dùng cursor. Một cursor FOR loop tự mở, fetch và đóng cursor:

```sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id, last_name, salary
        FROM employees
        WHERE department_id = 10
        ORDER BY employee_id;
BEGIN
    FOR r_employee IN c_employees LOOP
        DBMS_OUTPUT.PUT_LINE(
            r_employee.employee_id || ': ' ||
            r_employee.last_name || ' - ' ||
            r_employee.salary
        );
    END LOOP;
END;
/
```

`r_employee` được khai báo ngầm cho vòng lặp và có các field theo SELECT list. Cursor FOR loop phù hợp khi chỉ cần đọc tuần tự kết quả.

### 11.1. Cursor FOR loop với truy vấn trực tiếp

Không nhất thiết phải khai báo cursor riêng:

```sql
BEGIN
    FOR r IN (
        SELECT department_id, department_name
        FROM departments
        ORDER BY department_id
    ) LOOP
        DBMS_OUTPUT.PUT_LINE(
            r.department_id || ' - ' || r.department_name
        );
    END LOOP;
END;
/
```

### 11.2. Explicit cursor thủ công

Khi cần kiểm soát OPEN/FETCH/CLOSE:

```sql
DECLARE
    CURSOR c_departments IS
        SELECT department_id, department_name
        FROM departments;

    v_department_id departments.department_id%TYPE;
    v_department_name departments.department_name%TYPE;
BEGIN
    OPEN c_departments;

    LOOP
        FETCH c_departments
        INTO v_department_id, v_department_name;

        EXIT WHEN c_departments%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(
            v_department_id || ' - ' || v_department_name
        );
    END LOOP;

    CLOSE c_departments;
EXCEPTION
    WHEN OTHERS THEN
        IF c_departments%ISOPEN THEN
            CLOSE c_departments;
        END IF;
        RAISE;
END;
/
```

Cursor FOR loop thường ít code và ít rủi ro quên đóng cursor hơn. Explicit cursor hữu ích khi cần fetch theo batch hoặc dùng thuộc tính cursor cụ thể.

### 11.3. Implicit cursor attributes

Sau DML hoặc SELECT INTO, có thể dùng:

| Thuộc tính | Ý nghĩa |
|---|---|
| `SQL%FOUND` | Câu SQL gần nhất tác động/trả ít nhất một hàng theo ngữ cảnh |
| `SQL%NOTFOUND` | Không có hàng được tác động/trả về |
| `SQL%ROWCOUNT` | Số hàng được tác động hoặc trả về |
| `SQL%ISOPEN` | Trạng thái mở của implicit cursor; implicit cursor được Oracle tự quản lý và đóng sau câu lệnh |

Với SELECT INTO, nếu không có hàng, `NO_DATA_FOUND` được phát sinh trước khi code có thể tiếp tục đọc `SQL%NOTFOUND`. Với nhiều hàng, `TOO_MANY_ROWS` được phát sinh.

## 12. Thứ tự thực thi và luồng điều khiển

Một anonymous block thực thi theo trình tự:

```text
Bắt đầu block
    |
    v
Chạy phần DECLARE (khởi tạo khai báo)
    |
    v
Chạy các câu lệnh trong BEGIN
    |
    +---- Không có lỗi --------------------+
    |                                      |
    |                                      v
    |                                  END block
    |
    +---- Có exception
              |
              v
       Tìm WHEN phù hợp
              |
        +-----+-----+
        |           |
      Có handler   Không có handler
        |           |
        v           v
     Chạy handler  Truyền lỗi ra ngoài
        |
        +-- handler kết thúc bình thường --> END block
        |
        +-- handler RAISE/lỗi mới ---------> Truyền lỗi ra ngoài
```

Sơ đồ giúp phân biệt phần khai báo, phần thực thi và phần xử lý lỗi. Exception không phải một nhánh IF thông thường; khi exception xảy ra, các câu lệnh còn lại trong phần executable của block bị bỏ qua.

## 13. EXCEPTION và transaction

Xử lý exception không tự động có nghĩa rollback toàn bộ transaction.

### 13.1. Block lỗi không tự COMMIT

```sql
BEGIN
    UPDATE accounts
    SET balance = balance - 100
    WHERE account_id = 1;

    UPDATE accounts
    SET balance = balance + 100
    WHERE account_id = 2;
END;
/
```

Anonymous block không tự COMMIT khi kết thúc. Các thay đổi DML vẫn thuộc transaction của session/caller. Ứng dụng có thể COMMIT hoặc ROLLBACK theo ranh giới nghiệp vụ.

### 13.2. Exception không tự rollback mọi thay đổi trước đó

Nếu câu lệnh thứ hai lỗi, câu lệnh thứ nhất không mặc nhiên bị rollback toàn transaction chỉ vì exception truyền ra. Oracle bảo đảm statement có lỗi được rollback ở mức statement, còn các thay đổi trước đó trong transaction vẫn có thể còn pending.

Ví dụ:

```sql
BEGIN
    UPDATE accounts
    SET balance = balance - 100
    WHERE account_id = 1;

    UPDATE accounts
    SET balance = balance + 100
    WHERE account_id = -1;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
```

Ở đây handler chủ động rollback toàn transaction hiện tại rồi ném lại lỗi. Chỉ dùng `ROLLBACK` toàn transaction nếu block thực sự sở hữu transaction boundary; trong ứng dụng nhiều tầng, rollback có thể hủy cả thay đổi của caller trước khi gọi block.

### 13.3. Dùng SAVEPOINT để rollback một phần

```sql
BEGIN
    SAVEPOINT before_adjustment;

    UPDATE accounts
    SET balance = balance - 100
    WHERE account_id = 1;

    UPDATE accounts
    SET balance = balance + 100
    WHERE account_id = -1;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK TO before_adjustment;
        RAISE;
END;
/
```

`ROLLBACK TO SAVEPOINT` chỉ hủy các thay đổi sau savepoint trong transaction hiện tại. Savepoint không kết thúc transaction.

### 13.4. COMMIT trong anonymous block

Có thể viết COMMIT trong PL/SQL:

```sql
BEGIN
    UPDATE employees
    SET status = 'ACTIVE'
    WHERE employee_id = 100;

    COMMIT;
END;
/
```

Nhưng nên để transaction boundary do tầng nghiệp vụ phù hợp quản lý. Một block được gọi từ service khác mà tự COMMIT có thể làm caller mất khả năng rollback toàn bộ chuỗi thao tác.

### 13.5. DDL và implicit commit

DDL như `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE` có hành vi commit ngầm theo quy tắc Oracle. DDL không được viết trực tiếp như một static SQL statement trong phần PL/SQL thông thường; nếu cần chạy DDL từ PL/SQL, dùng dynamic SQL như `EXECUTE IMMEDIATE`.

Không coi anonymous block là cách gom nhiều DDL/DML thành một transaction có thể rollback hoàn toàn.

## 14. DBMS_OUTPUT và cách xem kết quả

`DBMS_OUTPUT.PUT_LINE` ghi thông điệp vào output buffer của session. Công cụ client cần bật hoặc đọc DBMS_OUTPUT thì mới hiển thị nội dung.

### 14.1. Bật output trong SQL*Plus/SQLcl

```sql
SET SERVEROUTPUT ON;

BEGIN
    DBMS_OUTPUT.PUT_LINE('Hello from Oracle');
END;
/
```

`SET SERVEROUTPUT ON` là lệnh của client, không phải câu lệnh PL/SQL.

### 14.2. SQL Developer

Trong Oracle SQL Developer, có thể bật panel DBMS Output và gắn với connection đang dùng. Sau đó chạy block bằng chế độ chạy script nếu có dấu `/` ở dòng riêng.

Các phím tắt có thể khác theo cấu hình và phiên bản; điều quan trọng là dùng chế độ thực thi script phù hợp để client gửi toàn bộ block và đọc DBMS_OUTPUT.

### 14.3. DBMS_OUTPUT không phải hệ thống logging bền vững

Output buffer:

- Không tự lưu thành bảng log.
- Không thay thế audit trail.
- Có thể không được client hiển thị nếu chưa bật.
- Không phù hợp làm kênh giao tiếp duy nhất giữa database và ứng dụng production.

Trong ứng dụng, hãy trả kết quả qua OUT parameters, result set/ref cursor, bảng trạng thái hoặc cơ chế logging được thiết kế phù hợp.

## 15. Chạy anonymous block bằng công cụ SQL

### 15.1. SQL*Plus và SQLcl

Ví dụ:

```sql
SET SERVEROUTPUT ON;

DECLARE
    v_message VARCHAR2(100) := 'Hello';
BEGIN
    DBMS_OUTPUT.PUT_LINE(v_message);
END;
/
```

Client tích lũy block đến khi gặp `/` trên dòng riêng rồi gửi block thực thi.

### 15.2. SQL Developer

Trong SQL Worksheet:

- Chạy script để thực thi cả block và dấu `/` theo cách SQL*Plus.
- Bật DBMS Output cho connection nếu muốn xem `PUT_LINE`.
- Nếu chỉ chọn một phần code, cần bảo đảm phần được chọn là block hoàn chỉnh.

### 15.3. Dấu slash không gửi qua JDBC

Khi ứng dụng Java gửi anonymous PL/SQL block qua JDBC, chuỗi SQL là:

```sql
BEGIN
    DBMS_OUTPUT.PUT_LINE('Hello');
END;
```

Không thêm dấu `/` ở cuối chuỗi gửi bằng `PreparedStatement` hoặc `CallableStatement`. Slash là command separator của client script, không phải token kết thúc PL/SQL mà JDBC cần gửi.

## 16. Anonymous block và named PL/SQL unit

| Tiêu chí | Anonymous block | Procedure/function/package |
|---|---|---|
| Có tên schema object | Không | Có |
| Lưu trong schema | Không lưu như một unit độc lập | Có thể được lưu/compile trong schema |
| Gọi lại | Gửi block mỗi lần hoặc lưu script ở client | Gọi bằng tên đã định nghĩa |
| Parameters | Không có parameter list của riêng block; có thể dùng bind variables | Có IN/OUT/IN OUT parameters |
| Reuse | Thường thấp hơn, trừ khi client quản lý script | Phù hợp tái sử dụng |
| Quyền | Chạy theo context/session và quyền liên quan | Có thể dùng definer's rights hoặc invoker's rights |
| Mục đích | Tác vụ ngắn, script, thử nghiệm, gọi API PL/SQL | Logic dùng chung, nghiệp vụ được quản lý trong schema |

Ví dụ anonymous block gọi procedure đã tồn tại:

```sql
BEGIN
    update_employee_salary(
        p_employee_id => 100,
        p_percent => 5
    );
END;
/
```

Anonymous block không thay thế procedure. Nếu cùng logic được gọi thường xuyên từ nhiều nơi, nên cân nhắc đóng gói thành named procedure/function.

## 17. Gọi anonymous block từ Java/JDBC

Java có thể gửi một PL/SQL block bằng `CallableStatement` hoặc `PreparedStatement`, tùy việc có cần OUT parameters hay không.

### 17.1. Block đơn giản

```java
String plsql = """
    BEGIN
        UPDATE employees
        SET salary = salary * ?
        WHERE employee_id = ?;
    END;
    """;

try (PreparedStatement ps = connection.prepareStatement(plsql)) {
    ps.setBigDecimal(1, new BigDecimal("1.05"));
    ps.setLong(2, 100L);
    ps.execute();
}
```

Text block `"""` yêu cầu Java 15 trở lên. Với Java cũ hơn, dùng chuỗi nối bằng `+`. Không nối dữ liệu đầu vào trực tiếp vào SQL; dùng bind parameters.

### 17.2. Block có OUT parameter

```java
String plsql = """
    BEGIN
        SELECT COUNT(*)
        INTO ?
        FROM employees
        WHERE department_id = ?;
    END;
    """;

try (CallableStatement cs = connection.prepareCall(plsql)) {
    cs.registerOutParameter(1, java.sql.Types.NUMERIC);
    cs.setInt(2, 10);
    cs.execute();

    BigDecimal count = cs.getBigDecimal(1);
}
```

Ví dụ minh họa ý tưởng bind OUT parameter; cú pháp placeholder trong PL/SQL block và cách đăng ký bind phải được kiểm tra theo Oracle JDBC driver đang dùng. Trong thực tế, OUT parameter thường được khai báo tường minh trong PL/SQL block:

```java
String plsql = """
    BEGIN
        :out_count := 0;
        SELECT COUNT(*)
        INTO :out_count
        FROM employees
        WHERE department_id = :department_id;
    END;
    """;
```

Việc bind tên `:out_count` và `:department_id` tùy API Oracle JDBC; `CallableStatement` thường dùng placeholder theo vị trí với `?`, còn named binding có API driver-specific. Hãy theo tài liệu driver và tránh trộn cú pháp named bind với positional binding một cách tùy tiện.

### 17.3. Exception từ PL/SQL sang Java

Nếu block không xử lý exception, lỗi Oracle được driver chuyển thành `SQLException`. Ứng dụng có thể đọc:

- `getErrorCode()` để lấy mã lỗi Oracle.
- `getSQLState()` để lấy SQLState nếu driver cung cấp.
- `getMessage()` để đọc thông báo.

Nếu block bắt lỗi rồi không re-raise, Java có thể nhận kết quả như thể block kết thúc bình thường. Vì vậy, chỉ bắt lỗi trong PL/SQL khi có xử lý phù hợp hoặc chủ động chuyển lỗi ra caller.

## 18. Ví dụ hoàn chỉnh: đọc, kiểm tra và cập nhật nhân viên

Ví dụ sau minh họa biến, `%TYPE`, SELECT INTO, IF, UPDATE, SQL%ROWCOUNT và exception:

```sql
DECLARE
    v_employee_id employees.employee_id%TYPE := 100;
    v_salary employees.salary%TYPE;
    v_new_salary employees.salary%TYPE;
BEGIN
    SELECT salary
    INTO v_salary
    FROM employees
    WHERE employee_id = v_employee_id;

    IF v_salary IS NULL THEN
        RAISE_APPLICATION_ERROR(
            -20020,
            'Employee salary is not set'
        );
    END IF;

    v_new_salary := v_salary * 1.05;

    UPDATE employees
    SET salary = v_new_salary
    WHERE employee_id = v_employee_id;

    IF SQL%ROWCOUNT = 1 THEN
        DBMS_OUTPUT.PUT_LINE(
            'Updated employee ' || v_employee_id ||
            ', new salary=' || v_new_salary
        );
    ELSE
        RAISE_APPLICATION_ERROR(
            -20021,
            'Unexpected update count'
        );
    END IF;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('Employee not found');
        RAISE;
    WHEN TOO_MANY_ROWS THEN
        DBMS_OUTPUT.PUT_LINE('Employee ID is not unique');
        RAISE;
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(
            'Error ' || SQLCODE || ': ' || SQLERRM
        );
        RAISE;
END;
/
```

Ví dụ giả định `EMPLOYEE_ID` được bảo đảm duy nhất. Block không tự COMMIT; caller quyết định xác nhận hoặc rollback transaction. Nếu `NO_DATA_FOUND` được bắt rồi re-raise, client vẫn nhận lỗi.

## 19. Các lỗi cú pháp và lỗi logic thường gặp

| Lỗi/hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `PLS-00103` gần DECLARE/BEGIN/END | Thiếu từ khóa, dấu chấm phẩy hoặc đặt câu lệnh sai vùng | Kiểm tra cấu trúc block và terminator |
| `PLS-00201: identifier must be declared` | Dùng biến/exception/type chưa khai báo hoặc thiếu quyền | Khai báo đúng scope và kiểm tra quyền |
| `ORA-06550` | Lỗi biên dịch PL/SQL, thường đi kèm mã PLS cụ thể | Đọc toàn bộ dòng lỗi và vị trí báo lỗi |
| `NO_DATA_FOUND` | SELECT INTO không trả hàng | Xử lý exception hoặc thay đổi truy vấn theo nghiệp vụ |
| `TOO_MANY_ROWS` | SELECT INTO trả nhiều hàng | Dùng cursor hoặc bảo đảm điều kiện duy nhất |
| `VALUE_ERROR` | Chuyển đổi/độ dài/giá trị không phù hợp | Kiểm tra kiểu, độ dài và dữ liệu đầu vào |
| Không thấy DBMS_OUTPUT | Client chưa bật hoặc chưa đọc output | Bật DBMS Output/Serveroutput |
| Block không chạy trong JDBC | Gửi dấu `/` của SQL*Plus hoặc gửi sai chuỗi block | Gửi block từ BEGIN đến END; không gửi slash |
| Lỗi bị che mất | WHEN OTHERS nuốt lỗi | Log có kiểm soát rồi RAISE |
| Dữ liệu vẫn thay đổi sau lỗi | Hiểu nhầm exception tự rollback toàn transaction | Quản lý ROLLBACK/SAVEPOINT rõ ràng |
| Biến không được nhìn thấy | Biến nằm ngoài scope hoặc block con đã kết thúc | Đưa khai báo vào scope phù hợp |
| Lỗi khởi tạo không vào handler cùng block | Exception xảy ra trong DECLARE section | Dùng block lồng và handler ở block ngoài |

### 19.1. Phân biệt lỗi compile và lỗi runtime

**Compile error** xảy ra khi PL/SQL không thể biên dịch block, ví dụ sai cú pháp hoặc identifier chưa khai báo. Phần thực thi chưa bắt đầu.

**Runtime exception** xảy ra trong lúc block đang chạy, ví dụ chia cho 0, SELECT INTO không có hàng hoặc vi phạm constraint. Handler có thể xử lý nếu exception được phát sinh trong phạm vi mà handler đó bao phủ.

### 19.2. Đọc cả dòng lỗi

Oracle thường trả nhiều dòng:

```text
ORA-06550: line 8, column 5:
PLS-00201: identifier 'V_TOTAL' must be declared
ORA-06550: line 8, column 5:
PL/SQL: Statement ignored
```

`ORA-06550` cung cấp vị trí lỗi trong block; `PLS-00201` giải thích identifier chưa được khai báo. Hãy đọc mã lỗi chi tiết thay vì chỉ nhìn dòng ORA-06550.

## 20. Thực hành tốt khi viết anonymous block

1. Khai báo biến ở đầu block và đặt tên thể hiện ý nghĩa.
2. Dùng `%TYPE`/`%ROWTYPE` khi biến gắn với cấu trúc bảng hoặc cursor.
3. Giữ phần BEGIN theo trình tự nghiệp vụ rõ ràng.
4. Dùng SELECT INTO chỉ khi kỳ vọng đúng một hàng.
5. Dùng cursor khi cần xử lý nhiều hàng.
6. Bắt exception cụ thể trước; đặt `WHEN OTHERS` cuối cùng.
7. Không nuốt lỗi nếu chưa có xử lý thay thế.
8. Ghi log đủ ngữ cảnh nhưng không làm lộ dữ liệu nhạy cảm.
9. Xác định rõ ai sở hữu COMMIT/ROLLBACK.
10. Không giữ transaction lâu khi chờ người dùng hoặc dịch vụ ngoài.
11. Dùng bind variables cho dữ liệu đầu vào.
12. Chuyển logic dùng chung thành procedure/function khi cần tái sử dụng.

### 20.1. Đặt tên biến để tránh nhầm với tên cột

Ví dụ dễ gây mơ hồ:

```sql
DECLARE
    employee_id NUMBER := 100;
BEGIN
    SELECT salary
    INTO employee_id
    FROM employees
    WHERE employee_id = employee_id;
END;
/
```

Tên `employee_id` vừa là biến vừa là tên cột; biểu thức WHERE khó xác định ý định và có thể bị phân giải không như mong muốn.

Nên đặt prefix:

```sql
DECLARE
    v_employee_id NUMBER := 100;
    v_salary employees.salary%TYPE;
BEGIN
    SELECT e.salary
    INTO v_salary
    FROM employees e
    WHERE e.employee_id = v_employee_id;
END;
/
```

Alias cho bảng và prefix cho biến giúp câu SQL rõ ràng hơn.

### 20.2. Giữ handler ngắn và có mục tiêu

Handler nên:

- Ghi nhận lỗi cần thiết.
- Thực hiện cleanup cần thiết.
- Chuyển đổi lỗi nếu cần thành mã nghiệp vụ.
- Re-raise nếu caller cần biết thao tác thất bại.

Tránh đặt quá nhiều logic nghiệp vụ trong `WHEN OTHERS`, vì điều đó làm luồng xử lý thành công và lỗi khó phân biệt.

## 21. Bài thực hành tổng hợp

Các ví dụ sau có thể chạy trong schema học tập. Nếu dùng bảng mẫu Oracle như `EMPLOYEES`, hãy bảo đảm schema có cài đặt sample schema và có quyền DML phù hợp. Các câu UPDATE có thể thay đổi dữ liệu; chạy trong transaction thử nghiệm và ROLLBACK nếu không muốn giữ thay đổi.

### Bước 1. Chạy block tối thiểu

```sql
BEGIN
    DBMS_OUTPUT.PUT_LINE('First PL/SQL block');
END;
/
```

### Bước 2. Khai báo biến và hằng

```sql
DECLARE
    c_rate CONSTANT NUMBER := 0.08;
    v_net_amount NUMBER := 250000;
    v_tax NUMBER;
BEGIN
    v_tax := v_net_amount * c_rate;
    DBMS_OUTPUT.PUT_LINE('Tax=' || v_tax);
END;
/
```

### Bước 3. Dùng %TYPE và SELECT INTO

```sql
DECLARE
    v_employee_id employees.employee_id%TYPE := 100;
    v_name employees.last_name%TYPE;
BEGIN
    SELECT last_name
    INTO v_name
    FROM employees
    WHERE employee_id = v_employee_id;

    DBMS_OUTPUT.PUT_LINE(v_name);
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('No matching employee');
END;
/
```

### Bước 4. Thử TOO_MANY_ROWS

```sql
DECLARE
    v_name employees.last_name%TYPE;
BEGIN
    SELECT last_name
    INTO v_name
    FROM employees
    WHERE department_id = 10;
EXCEPTION
    WHEN TOO_MANY_ROWS THEN
        DBMS_OUTPUT.PUT_LINE('More than one row returned');
END;
/
```

Kết quả phụ thuộc số nhân viên trong phòng ban 10; nếu chỉ có một hàng thì handler không chạy.

### Bước 5. Dùng IF và vòng lặp

```sql
DECLARE
    v_score NUMBER := 78;
BEGIN
    IF v_score >= 80 THEN
        DBMS_OUTPUT.PUT_LINE('Very good');
    ELSIF v_score >= 50 THEN
        DBMS_OUTPUT.PUT_LINE('Passed');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Failed');
    END IF;

    FOR i IN 1..3 LOOP
        DBMS_OUTPUT.PUT_LINE('Step ' || i);
    END LOOP;
END;
/
```

### Bước 6. Dùng cursor FOR loop

```sql
BEGIN
    FOR r IN (
        SELECT employee_id, last_name
        FROM employees
        WHERE department_id = 10
        ORDER BY employee_id
    ) LOOP
        DBMS_OUTPUT.PUT_LINE(
            r.employee_id || ' ' || r.last_name
        );
    END LOOP;
END;
/
```

### Bước 7. Tạo và bắt exception nghiệp vụ

```sql
DECLARE
    e_invalid_quantity EXCEPTION;
    v_quantity NUMBER := -1;
BEGIN
    IF v_quantity < 0 THEN
        RAISE e_invalid_quantity;
    END IF;
EXCEPTION
    WHEN e_invalid_quantity THEN
        DBMS_OUTPUT.PUT_LINE('Quantity must not be negative');
END;
/
```

### Bước 8. Thử block lồng

```sql
BEGIN
    DBMS_OUTPUT.PUT_LINE('Outer start');

    BEGIN
        RAISE_APPLICATION_ERROR(-20030, 'Inner failure');
    EXCEPTION
        WHEN OTHERS THEN
            DBMS_OUTPUT.PUT_LINE('Inner handler: ' || SQLERRM);
    END;

    DBMS_OUTPUT.PUT_LINE('Outer continues');
END;
/
```

### Bước 9. Quan sát transaction và ROLLBACK

```sql
BEGIN
    UPDATE employees
    SET salary = salary + 1
    WHERE employee_id = 100;

    DBMS_OUTPUT.PUT_LINE('Rows=' || SQL%ROWCOUNT);
END;
/

ROLLBACK;
```

Chạy SELECT trước và sau để quan sát dữ liệu được rollback. Không dùng ví dụ trên ở môi trường production.

### Bước 10. Thử exception propagation

```sql
BEGIN
    BEGIN
        RAISE ZERO_DIVIDE;
    END;
EXCEPTION
    WHEN ZERO_DIVIDE THEN
        DBMS_OUTPUT.PUT_LINE('Outer block handled the exception');
END;
/
```

Block con không bắt lỗi; block cha nhận exception và xử lý.

## 22. Quy tắc ghi nhớ

| Phần | Ghi nhớ |
|---|---|
| `DECLARE` | Tùy chọn; khai báo biến, hằng, type, cursor, exception và subprogram cục bộ |
| `BEGIN` | Bắt buộc; bắt đầu phần thực thi |
| `EXCEPTION` | Tùy chọn; bắt đầu các handler lỗi |
| `END;` | Bắt buộc; đóng block |
| `/` | Lệnh client chạy buffer trong SQL*Plus/SQLcl; không gửi như SQL token qua JDBC |
| `:=` | Gán giá trị cho biến PL/SQL |
| `%TYPE` | Bám kiểu của cột/biến |
| `%ROWTYPE` | Record theo cấu trúc một hàng |
| `SELECT INTO` | Đưa kết quả một hàng vào biến; không hàng/nhiều hàng sẽ phát sinh exception |
| `SQL%ROWCOUNT` | Số hàng bị tác động bởi DML gần nhất |
| `WHEN OTHERS` | Bắt lỗi còn lại; thường log rồi RAISE |
| `RAISE` | Phát sinh hoặc ném lại exception |
| `RAISE_APPLICATION_ERROR` | Trả mã lỗi ứng dụng trong khoảng -20000..-20999 |
| `SQLCODE`/`SQLERRM` | Mã và thông điệp exception hiện tại |
| `COMMIT`/`ROLLBACK` | Quản lý transaction; không tự động xảy ra chỉ vì block kết thúc |

## 23. Câu hỏi tự kiểm tra

**Câu 1.** Anonymous block là gì?

**Trả lời:** Một block PL/SQL không có tên schema object, thường được gửi trực tiếp từ client để thực hiện tác vụ hoặc thử nghiệm.

**Câu 2.** Những phần nào bắt buộc trong anonymous block?

**Trả lời:** `BEGIN` và `END`; `DECLARE` và `EXCEPTION` là tùy chọn.

**Câu 3.** `DECLARE` dùng để làm gì?

**Trả lời:** Khai báo biến, hằng, kiểu, cursor, exception và subprogram cục bộ trước phần thực thi.

**Câu 4.** `:=` khác `=` như thế nào?

**Trả lời:** `:=` dùng gán biến; `=` thường dùng để so sánh trong điều kiện hoặc biểu thức SQL.

**Câu 5.** `%TYPE` và `%ROWTYPE` khác nhau thế nào?

**Trả lời:** `%TYPE` bám kiểu của một cột/biến; `%ROWTYPE` tạo record theo cấu trúc một hàng của bảng hoặc cursor.

**Câu 6.** SELECT INTO không trả hàng gây exception nào?

**Trả lời:** `NO_DATA_FOUND`.

**Câu 7.** SELECT INTO trả nhiều hàng gây exception nào?

**Trả lời:** `TOO_MANY_ROWS`.

**Câu 8.** Có thể dùng cursor FOR loop khi SELECT trả nhiều hàng không?

**Trả lời:** Có. Cursor FOR loop tự mở, fetch và đóng cursor.

**Câu 9.** WHEN OTHERS nên đặt ở đâu?

**Trả lời:** Cuối danh sách handler; chỉ dùng sau các handler cụ thể và không nuốt lỗi nếu chưa có xử lý rõ ràng.

**Câu 10.** SQLCODE và SQLERRM cung cấp thông tin gì?

**Trả lời:** Mã lỗi và thông điệp của exception hiện tại.

**Câu 11.** RAISE_APPLICATION_ERROR dùng mã trong khoảng nào?

**Trả lời:** Từ -20000 đến -20999.

**Câu 12.** Exception trong block con không được xử lý sẽ đi đâu?

**Trả lời:** Nó truyền ra block bao ngoài; handler phù hợp của block cha có thể bắt.

**Câu 13.** Handler của block có bắt được lỗi xảy ra khi khởi tạo biến trong DECLARE của chính block đó không?

**Trả lời:** Không. Lỗi trong declaration section truyền ra enclosing block; cần block ngoài hoặc block con khác để xử lý.

**Câu 14.** Khi anonymous block kết thúc, Oracle có tự COMMIT không?

**Trả lời:** Không. DML vẫn thuộc transaction hiện tại; caller quyết định COMMIT hoặc ROLLBACK.

**Câu 15.** Dấu `/` có phải một phần của PL/SQL block gửi qua JDBC không?

**Trả lời:** Không. Slash là command của client script như SQL*Plus/SQLcl; JDBC gửi block từ BEGIN đến END.

**Câu 16.** DBMS_OUTPUT có phải log bền vững không?

**Trả lời:** Không. Nó là output buffer cần client bật/đọc và không thay thế bảng log hoặc hệ thống audit.

## 24. Kết luận

Anonymous block là cách trực tiếp để gom các câu lệnh PL/SQL thành một đơn vị thực thi mà không cần tạo procedure hoặc function có tên. Cấu trúc của block gồm vùng khai báo tùy chọn `DECLARE`, phần thực thi bắt buộc `BEGIN`, vùng xử lý lỗi tùy chọn `EXCEPTION` và phần kết thúc bắt buộc `END;`. Trong `DECLARE`, ta khai báo biến, hằng, record, cursor và exception; trong `BEGIN`, ta gán giá trị, truy vấn bằng SELECT INTO, chạy DML, điều kiện và vòng lặp; trong `EXCEPTION`, ta xử lý lỗi cụ thể hoặc chuyển lỗi về caller.

Hãy phân biệt lỗi compile với runtime exception, hiểu quy tắc `NO_DATA_FOUND`/`TOO_MANY_ROWS`, dùng `WHEN OTHERS` có trách nhiệm và không nuốt lỗi. Block lồng nhau tạo scope riêng và cho phép exception truyền lên block cha. `SQLCODE`, `SQLERRM`, `RAISE` và `RAISE_APPLICATION_ERROR` giúp chẩn đoán hoặc biểu đạt lỗi theo nghiệp vụ.

Cuối cùng, anonymous block không tự COMMIT khi kết thúc. Transaction boundary vẫn cần được thiết kế ở tầng phù hợp; dấu `/` là lệnh của SQL client chứ không phải nội dung gửi qua JDBC. Khi hiểu đúng bốn phần DECLARE, BEGIN, EXCEPTION và END, bạn có thể viết các script PL/SQL ngắn, dễ đọc, kiểm soát lỗi tốt và làm nền tảng để chuyển logic dùng chung thành procedure, function hoặc package.
