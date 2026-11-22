# SELECT INTO và các lỗi NO_DATA_FOUND hoặc TOO_MANY_ROWS trong PL/SQL

## 1. SELECT INTO dùng để làm gì?

Trong SQL, câu lệnh `SELECT` trả về một tập kết quả gồm 0, 1 hoặc nhiều hàng. Khi viết PL/SQL, nếu chương trình cần đưa dữ liệu của một hàng vào biến để tính toán hoặc ra quyết định, ta dùng cú pháp **`SELECT ... INTO`**.

`SELECT INTO` trong PL/SQL có quy tắc rất rõ: truy vấn phải trả về **đúng một hàng**.

- Không có hàng nào: PL/SQL phát sinh `NO_DATA_FOUND`.
- Có đúng một hàng: giá trị các cột được gán vào các biến đích.
- Có từ hai hàng trở lên: PL/SQL phát sinh `TOO_MANY_ROWS`.

Ví dụ:

```sql
DECLARE
    v_employee_id employees.employee_id%TYPE := 100;
    v_last_name   employees.last_name%TYPE;
    v_salary      employees.salary%TYPE;
BEGIN
    SELECT last_name, salary
    INTO v_last_name, v_salary
    FROM employees
    WHERE employee_id = v_employee_id;

    DBMS_OUTPUT.PUT_LINE(
        v_last_name || ' earns ' || v_salary
    );
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('Employee does not exist');
    WHEN TOO_MANY_ROWS THEN
        DBMS_OUTPUT.PUT_LINE('Query returned more than one employee');
END;
/
```

`EMPLOYEE_ID` thường là khóa chính trong sample schema, vì vậy điều kiện này kỳ vọng tối đa một hàng. Hai exception handler vẫn minh họa cách bảo vệ block khi dữ liệu hoặc truy vấn không đúng kỳ vọng.

Bài học thuộc chương **PL/SQL và dữ liệu**, tập trung vào cách dùng `SELECT INTO`, quy tắc một hàng, hai exception `NO_DATA_FOUND` và `TOO_MANY_ROWS`, nguyên nhân phát sinh, cách xử lý phù hợp, và lựa chọn cursor hoặc `BULK COLLECT` khi truy vấn có thể trả nhiều hàng.

## 2. Cú pháp SELECT INTO

Cú pháp tổng quát:

```sql
SELECT select_list
INTO variable_list
FROM table_or_view
[WHERE condition]
[GROUP BY ...]
[HAVING ...]
[ORDER BY ...];
```

Phần `INTO` là điểm khác biệt quan trọng khi dùng trong PL/SQL: nó chỉ định nơi nhận kết quả.

Ví dụ:

```sql
DECLARE
    v_department_name departments.department_name%TYPE;
BEGIN
    SELECT department_name
    INTO v_department_name
    FROM departments
    WHERE department_id = 10;

    DBMS_OUTPUT.PUT_LINE(v_department_name);
END;
/
```

Các quy tắc cơ bản:

1. Số biểu thức trong SELECT list phải khớp số biến trong INTO list.
2. Kiểu dữ liệu của từng biểu thức phải tương thích với biến nhận tương ứng.
3. Truy vấn phải trả đúng một hàng nếu muốn phần tiếp theo của block chạy bình thường.
4. Nếu truy vấn không trả đúng một hàng, PL/SQL phát sinh exception và chuyển luồng điều khiển sang handler phù hợp.
5. Mỗi biểu thức được gán theo vị trí; tên alias trong SELECT không tự quyết định biến nhận nào được gán.

### 2.1. Một cột vào một biến

```sql
DECLARE
    v_department_name departments.department_name%TYPE;
BEGIN
    SELECT department_name
    INTO v_department_name
    FROM departments
    WHERE department_id = 10;
END;
/
```

### 2.2. Nhiều cột vào nhiều biến

```sql
DECLARE
    v_name   employees.last_name%TYPE;
    v_salary employees.salary%TYPE;
BEGIN
    SELECT last_name, salary
    INTO v_name, v_salary
    FROM employees
    WHERE employee_id = 100;
END;
/
```

SELECT có hai biểu thức nên INTO có hai biến. Giá trị của biểu thức thứ nhất vào biến thứ nhất, biểu thức thứ hai vào biến thứ hai.

### 2.3. Dùng %TYPE để khai báo biến nhận

```sql
DECLARE
    v_employee_id employees.employee_id%TYPE;
    v_salary      employees.salary%TYPE;
BEGIN
    SELECT employee_id, salary
    INTO v_employee_id, v_salary
    FROM employees
    WHERE employee_id = 100;
END;
/
```

`%TYPE` giúp biến dùng kiểu dữ liệu gắn với cột. Nếu kiểu cột thay đổi, khai báo có thể theo kiểu mới khi block hoặc chương trình được biên dịch lại. `%TYPE` không tự bảo đảm truy vấn trả một hàng; cardinality vẫn phải được thiết kế riêng.

### 2.4. Dùng %ROWTYPE nhận cả hàng

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
END;
/
```

`%ROWTYPE` tạo record có các field tương ứng với hàng của bảng. Khi dùng `SELECT * INTO record`, cấu trúc và thứ tự cột của kết quả phải tương thích với record. Nếu chỉ cần một vài cột, nên liệt kê rõ cột và dùng các biến riêng để code ít phụ thuộc vào thay đổi cấu trúc bảng.

## 3. NO_DATA_FOUND: truy vấn không trả hàng

`NO_DATA_FOUND` là predefined exception của PL/SQL. Nó được phát sinh khi câu `SELECT ... INTO` không tìm thấy hàng nào.

Ví dụ:

```sql
DECLARE
    v_name employees.last_name%TYPE;
BEGIN
    SELECT last_name
    INTO v_name
    FROM employees
    WHERE employee_id = -1;

    DBMS_OUTPUT.PUT_LINE('Name = ' || v_name);
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('No employee matched the supplied ID');
END;
/
```

Nếu không có nhân viên mang ID `-1`, dòng `DBMS_OUTPUT.PUT_LINE('Name = ...')` không chạy. Luồng chuyển thẳng đến handler `NO_DATA_FOUND`.

### 3.1. Những nguyên nhân thường gặp

- ID hoặc mã nghiệp vụ truyền vào không tồn tại.
- Bộ lọc WHERE quá chặt.
- Dữ liệu chưa được tạo hoặc chưa commit trong transaction khác.
- JOIN hoặc điều kiện bổ sung loại bỏ hàng dự kiến.
- Người gọi truyền sai giá trị bind.
- Dữ liệu đã bị xóa hoặc thay đổi giữa các thao tác của ứng dụng.

Không nên tự động kết luận `NO_DATA_FOUND` luôn là lỗi dữ liệu. Trong một số nghiệp vụ, không tìm thấy là trạng thái bình thường, ví dụ tìm cấu hình tùy chọn chưa được thiết lập. Cách xử lý phụ thuộc ý nghĩa của thao tác.

### 3.2. Xử lý khi không tìm thấy là trạng thái hợp lệ

Nếu một cấu hình tùy chọn có thể chưa tồn tại, có thể đặt giá trị mặc định:

```sql
DECLARE
    v_discount_rate NUMBER;
BEGIN
    SELECT discount_rate
    INTO v_discount_rate
    FROM customer_discounts
    WHERE customer_id = 501;

    DBMS_OUTPUT.PUT_LINE('Discount=' || v_discount_rate);
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        v_discount_rate := 0;
        DBMS_OUTPUT.PUT_LINE('No discount configured; use 0');
END;
/
```

Ở đây, nghiệp vụ quy định khách hàng không có cấu hình thì không được giảm giá. Vì vậy, handler chuyển trạng thái không tìm thấy thành giá trị mặc định 0.

Nếu không tìm thấy là lỗi nghiệp vụ, nên thông báo rõ hoặc ném lỗi ứng dụng thay vì âm thầm gán mặc định:

```sql
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Customer discount configuration is required'
        );
```

### 3.3. Handler có thể gán trạng thái để caller tiếp tục

```sql
DECLARE
    v_department_name departments.department_name%TYPE;
    v_found BOOLEAN := TRUE;
BEGIN
    BEGIN
        SELECT department_name
        INTO v_department_name
        FROM departments
        WHERE department_id = 999;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            v_found := FALSE;
    END;

    IF v_found THEN
        DBMS_OUTPUT.PUT_LINE(v_department_name);
    ELSE
        DBMS_OUTPUT.PUT_LINE('Department is optional and was not found');
    END IF;
END;
/
```

Block con giới hạn phạm vi bắt `NO_DATA_FOUND`. Sau khi block con kết thúc, block ngoài kiểm tra cờ `v_found` và tiếp tục xử lý.

### 3.4. Mã lỗi của NO_DATA_FOUND

Trong handler:

```sql
BEGIN
    RAISE NO_DATA_FOUND;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('SQLCODE=' || SQLCODE);
        DBMS_OUTPUT.PUT_LINE('SQLERRM=' || SQLERRM);
END;
/
```

`NO_DATA_FOUND` thường có `SQLCODE` là `+100`. Thông điệp hiển thị thường tương ứng `ORA-01403: no data found`. Trong PL/SQL, nên bắt exception bằng tên `NO_DATA_FOUND` thay vì so sánh chuỗi thông báo.

## 4. TOO_MANY_ROWS: truy vấn trả nhiều hơn một hàng

`TOO_MANY_ROWS` là predefined exception được phát sinh khi `SELECT ... INTO` trả từ hai hàng trở lên.

Ví dụ:

```sql
DECLARE
    v_name employees.last_name%TYPE;
BEGIN
    SELECT last_name
    INTO v_name
    FROM employees
    WHERE department_id = 10;

    DBMS_OUTPUT.PUT_LINE(v_name);
EXCEPTION
    WHEN TOO_MANY_ROWS THEN
        DBMS_OUTPUT.PUT_LINE(
            'The department has more than one employee'
        );
END;
/
```

Nếu phòng ban 10 có nhiều nhân viên, truy vấn không thể đưa nhiều giá trị `LAST_NAME` vào một biến scalar. PL/SQL phát sinh `TOO_MANY_ROWS`.

### 4.1. Những nguyên nhân thường gặp

- Điều kiện WHERE không đủ chọn lọc.
- Lập trình viên giả định một cột là duy nhất nhưng schema không có constraint bảo đảm.
- JOIN một bảng cha với nhiều hàng con làm nhân bản hàng kết quả.
- Truy vấn có nhiều phiên bản hiệu lực nhưng thiếu điều kiện thời gian.
- Dữ liệu bị trùng do import hoặc quy trình ghi dữ liệu.
- Dùng `SELECT INTO` trong khi nghiệp vụ thực sự cần một danh sách.

### 4.2. Kiểm tra cardinality bằng COUNT

Trong lúc điều tra, có thể chạy truy vấn đếm:

```sql
SELECT COUNT(*)
FROM employees
WHERE department_id = 10;
```

Nếu kết quả lớn hơn 1, điều kiện không phù hợp với giả định một hàng. Tuy nhiên, không nên luôn viết ứng dụng theo quy trình `COUNT(*)` trước rồi SELECT lần nữa. Hai câu SQL là hai statement riêng; dữ liệu có thể thay đổi giữa hai lần đọc theo transaction isolation và hoạt động đồng thời.

Nếu mục tiêu là lấy một hàng, hãy thiết kế điều kiện/constraint bảo đảm một hàng. Nếu mục tiêu là lấy nhiều hàng, dùng cursor hoặc collection.

### 4.3. Không dùng DISTINCT để che lỗi cardinality một cách tùy tiện

```sql
SELECT DISTINCT department_id
INTO v_department_id
FROM employees
WHERE department_id = 10;
```

`DISTINCT` có thể trả một giá trị nếu mọi hàng có cùng `DEPARTMENT_ID`, nhưng điều đó không có nghĩa truy vấn gốc đã chọn đúng một nhân viên. Nếu cần tên hoặc lương từng người, DISTINCT không giải quyết được sự nhập nhằng nghiệp vụ.

Chỉ dùng DISTINCT khi loại bỏ bản sao là một phần đúng đắn của ý nghĩa truy vấn, không phải để làm biến mất `TOO_MANY_ROWS`.

### 4.4. Mã lỗi của TOO_MANY_ROWS

`TOO_MANY_ROWS` tương ứng lỗi `ORA-01422: exact fetch returns more than requested number of rows`; `SQLCODE` thường là `-1422`.

Ví dụ:

```sql
BEGIN
    DECLARE
        v_name employees.last_name%TYPE;
    BEGIN
        SELECT last_name
        INTO v_name
        FROM employees
        WHERE department_id = 10;
    END;
EXCEPTION
    WHEN TOO_MANY_ROWS THEN
        DBMS_OUTPUT.PUT_LINE(
            'SQLCODE=' || SQLCODE || ', ' || SQLERRM
        );
END;
/
```

Handler của block ngoài nhận exception truyền từ block con.

## 5. Vì sao phải bảo đảm đúng một hàng?

`SELECT INTO` phù hợp khi chương trình cần một giá trị đơn nhất để tiếp tục logic. Ví dụ:

- Tìm một khách hàng bằng khóa chính.
- Đọc cấu hình duy nhất theo mã cấu hình.
- Lấy mức thuế hiện hành theo một khóa hiệu lực đã được xác định duy nhất.
- Đọc trạng thái của một đơn hàng theo ID.

Điều kiện WHERE nên dựa trên khóa chính, unique key hoặc một quy tắc nghiệp vụ có thể chứng minh chỉ có tối đa một hàng.

### 5.1. Dùng khóa chính

```sql
SELECT customer_name
INTO v_customer_name
FROM customers
WHERE customer_id = p_customer_id;
```

Nếu `CUSTOMER_ID` là PRIMARY KEY, truy vấn trả tối đa một hàng. Nó vẫn có thể trả 0 hàng nếu ID không tồn tại, vì vậy `NO_DATA_FOUND` vẫn có thể xảy ra.

### 5.2. Dùng unique key

```sql
SELECT email
INTO v_email
FROM customers
WHERE normalized_email = p_normalized_email;
```

Truy vấn chỉ có thể được xem là tối đa một hàng nếu schema có constraint UNIQUE phù hợp với biểu thức và quy tắc NULL. Không nên dựa vào nhận định “người dùng không bao giờ nhập trùng” nếu database không bảo đảm điều đó.

Lưu ý: Oracle UNIQUE constraint cho phép nhiều NULL theo semantics của unique key; điều kiện `column = NULL` không tìm được hàng vì phép so sánh với NULL cho kết quả UNKNOWN. Nếu nghiệp vụ cần email bắt buộc và duy nhất, thường cần cả NOT NULL và UNIQUE.

### 5.3. JOIN có thể làm tăng số hàng

Giả sử một khách hàng có nhiều đơn hàng:

```sql
SELECT c.customer_name,
       o.order_id
INTO v_customer_name,
     v_order_id
FROM customers c
JOIN orders o
  ON o.customer_id = c.customer_id
WHERE c.customer_id = p_customer_id;
```

Mặc dù `CUSTOMER_ID` là khóa chính của bảng khách hàng, JOIN với `ORDERS` có thể trả nhiều hàng. Điều kiện chọn một hàng ở bảng cha không bảo đảm toàn bộ query chỉ trả một hàng khi bảng con là quan hệ one-to-many.

Nếu chỉ cần thông tin khách hàng, truy vấn bảng `CUSTOMERS` riêng. Nếu cần nhiều đơn hàng, dùng cursor. Nếu chỉ cần đơn hàng mới nhất, xác định quy tắc chọn mới nhất bằng ORDER BY và tie-breaker.

## 6. Khi nghiệp vụ cần đúng một hàng, nhiều hơn một hàng là lỗi dữ liệu

Nếu truy vấn được thiết kế để tìm một cấu hình duy nhất hoặc một bản ghi theo khóa, `TOO_MANY_ROWS` thường cho thấy vấn đề cần điều tra.

Ví dụ, bảng cấu hình:

```sql
CREATE TABLE app_settings (
    setting_key VARCHAR2(100) NOT NULL,
    setting_value VARCHAR2(4000),
    CONSTRAINT uq_app_settings_key UNIQUE (setting_key)
);
```

Truy vấn:

```sql
SELECT setting_value
INTO v_setting_value
FROM app_settings
WHERE setting_key = 'PAYMENT_MODE';
```

UNIQUE constraint bảo đảm không có hai hàng cùng `SETTING_KEY`. Nếu ứng dụng nhận `TOO_MANY_ROWS`, hãy kiểm tra xem câu truy vấn thực tế có JOIN hoặc UNION làm nhân bản kết quả hay không, hoặc schema/đối tượng thực tế có đúng như giả định không.

Không nên xử lý lỗi bằng cách chọn đại một hàng, vì có thể che giấu vi phạm dữ liệu hoặc lỗi JOIN.

## 7. Khi nghiệp vụ cho phép nhiều hàng: dùng cursor

Nếu truy vấn có thể trả nhiều hàng, không dùng scalar `SELECT INTO`. Dùng cursor FOR loop là cách đơn giản để đọc từng hàng:

```sql
BEGIN
    FOR r_employee IN (
        SELECT employee_id, last_name, salary
        FROM employees
        WHERE department_id = 10
        ORDER BY employee_id
    ) LOOP
        DBMS_OUTPUT.PUT_LINE(
            r_employee.employee_id || ' - ' ||
            r_employee.last_name || ' - ' ||
            r_employee.salary
        );
    END LOOP;
END;
/
```

Cursor FOR loop tự mở cursor, fetch các hàng và đóng cursor khi kết thúc bình thường hoặc thoát vòng lặp. Nếu không có hàng, vòng lặp chạy 0 lần; nó không phát sinh `NO_DATA_FOUND`.

### 7.1. Explicit cursor

Khi cần kiểm soát OPEN/FETCH/CLOSE:

```sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id, last_name
        FROM employees
        WHERE department_id = 10
        ORDER BY employee_id;

    v_employee_id employees.employee_id%TYPE;
    v_last_name employees.last_name%TYPE;
BEGIN
    OPEN c_employees;

    LOOP
        FETCH c_employees
        INTO v_employee_id, v_last_name;

        EXIT WHEN c_employees%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(
            v_employee_id || ' - ' || v_last_name
        );
    END LOOP;

    CLOSE c_employees;
EXCEPTION
    WHEN OTHERS THEN
        IF c_employees%ISOPEN THEN
            CLOSE c_employees;
        END IF;
        RAISE;
END;
/
```

Cursor explicit trả 0 hàng thì vòng FETCH đầu tiên đặt `%NOTFOUND` thành TRUE. Không có `NO_DATA_FOUND` chỉ vì cursor không có hàng.

### 7.2. Cursor với LIMIT và BULK COLLECT

Với tập kết quả lớn, có thể fetch theo batch để tránh giữ toàn bộ kết quả trong bộ nhớ:

```sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id, last_name
        FROM employees
        ORDER BY employee_id;

    TYPE employee_batch_t IS TABLE OF c_employees%ROWTYPE;
    v_batch employee_batch_t;
BEGIN
    OPEN c_employees;

    LOOP
        FETCH c_employees
        BULK COLLECT INTO v_batch
        LIMIT 100;

        EXIT WHEN v_batch.COUNT = 0;

        FOR i IN 1 .. v_batch.COUNT LOOP
            DBMS_OUTPUT.PUT_LINE(
                v_batch(i).employee_id || ' - ' ||
                v_batch(i).last_name
            );
        END LOOP;
    END LOOP;

    CLOSE c_employees;
EXCEPTION
    WHEN OTHERS THEN
        IF c_employees%ISOPEN THEN
            CLOSE c_employees;
        END IF;
        RAISE;
END;
/
```

`BULK COLLECT ... LIMIT` lấy một nhóm hàng mỗi lần FETCH. Với batch cuối có ít hơn 100 hàng, collection chứa số hàng còn lại; lần FETCH sau collection rỗng và vòng lặp kết thúc.

## 8. Khi cần nhiều hàng trong một collection: SELECT BULK COLLECT INTO

`BULK COLLECT INTO` là cách đưa nhiều hàng vào collection PL/SQL:

```sql
DECLARE
    TYPE employee_id_list_t IS TABLE OF employees.employee_id%TYPE;
    v_employee_ids employee_id_list_t;
BEGIN
    SELECT employee_id
    BULK COLLECT INTO v_employee_ids
    FROM employees
    WHERE department_id = 10;

    DBMS_OUTPUT.PUT_LINE('Count=' || v_employee_ids.COUNT);
END;
/
```

Khác với scalar `SELECT INTO`, `BULK COLLECT` có thể nhận nhiều hàng. Nếu truy vấn không trả hàng, collection được làm rỗng; nó không phát sinh `NO_DATA_FOUND` chỉ vì không có hàng.

### 8.1. Nhiều cột vào nhiều collection

```sql
DECLARE
    TYPE id_list_t IS TABLE OF employees.employee_id%TYPE;
    TYPE name_list_t IS TABLE OF employees.last_name%TYPE;

    v_ids id_list_t;
    v_names name_list_t;
BEGIN
    SELECT employee_id, last_name
    BULK COLLECT INTO v_ids, v_names
    FROM employees
    WHERE department_id = 10;

    FOR i IN 1 .. v_ids.COUNT LOOP
        DBMS_OUTPUT.PUT_LINE(v_ids(i) || ' ' || v_names(i));
    END LOOP;
END;
/
```

Các collection nhận dữ liệu theo cùng vị trí. Số biểu thức và số collection nhận phải tương ứng.

### 8.2. Cân nhắc bộ nhớ

`SELECT BULK COLLECT INTO` không có LIMIT sẽ đưa toàn bộ tập kết quả vào collection. Với dữ liệu lớn, có thể tiêu thụ nhiều PGA memory. Dùng explicit cursor với `FETCH BULK COLLECT ... LIMIT n` khi cần kiểm soát kích thước batch.

## 9. Khi chỉ cần một hàng trong số nhiều hàng: chọn có quy tắc

Có những nghiệp vụ hợp lệ cần chọn một hàng đại diện trong tập nhiều hàng, ví dụ đơn hàng mới nhất, phiên bản hiệu lực mới nhất hoặc mức giá ưu tiên cao nhất.

Trong trường hợp đó, phải xác định **quy tắc chọn hàng** bằng `ORDER BY`, sau đó giới hạn kết quả.

### 9.1. FETCH FIRST 1 ROW ONLY

Oracle Database 12c Release 1 trở lên hỗ trợ row-limiting clause:

```sql
DECLARE
    v_order_id orders.order_id%TYPE;
    v_order_date orders.order_date%TYPE;
BEGIN
    SELECT order_id, order_date
    INTO v_order_id, v_order_date
    FROM orders
    WHERE customer_id = 501
    ORDER BY order_date DESC, order_id DESC
    FETCH FIRST 1 ROW ONLY;

    DBMS_OUTPUT.PUT_LINE(
        'Latest order=' || v_order_id
    );
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('Customer has no orders');
END;
/
```

`ORDER BY order_date DESC, order_id DESC` chọn đơn hàng mới nhất; `ORDER_ID` là tie-breaker để kết quả xác định nếu hai đơn có cùng thời điểm.

Nếu không có hàng, SELECT INTO vẫn phát sinh `NO_DATA_FOUND`. Nếu có ít nhất một hàng, FETCH FIRST 1 ROW ONLY giới hạn kết quả còn một hàng.

### 9.2. FETCH FIRST 1 ROW ONLY không sửa dữ liệu trùng

Nếu truy vấn vốn phải trả đúng một hàng theo khóa duy nhất nhưng lại có dữ liệu trùng, thêm `FETCH FIRST 1 ROW ONLY` có thể che giấu lỗi. Chỉ dùng row limiting khi “chọn hàng tốt nhất” là yêu cầu nghiệp vụ thực sự.

### 9.3. WITH TIES có thể vẫn trả nhiều hàng

`FETCH FIRST 1 ROW WITH TIES` có thể trả nhiều hàng nếu có nhiều hàng cùng giá trị sort key cuối cùng. Vì vậy, dùng với scalar SELECT INTO có thể vẫn phát sinh `TOO_MANY_ROWS`. Nếu muốn chắc chắn đúng một hàng, dùng `ONLY` và một thứ tự có tie-breaker phù hợp.

### 9.4. Cách dùng ROWNUM trong phiên bản cũ

Trước khi có row-limiting clause, có thể bọc truy vấn đã sắp xếp trong inline view rồi lọc `ROWNUM`:

```sql
SELECT order_id, order_date
INTO v_order_id, v_order_date
FROM (
    SELECT order_id, order_date
    FROM orders
    WHERE customer_id = 501
    ORDER BY order_date DESC, order_id DESC
)
WHERE ROWNUM = 1;
```

Không viết `WHERE ROWNUM = 1` ở cùng query block với `ORDER BY` nếu mục tiêu là lấy hàng đầu theo thứ tự sắp xếp, vì ROWNUM được gán trước bước ORDER BY trong cùng query block. Inline view giúp sắp xếp trước rồi mới giới hạn.

## 10. Aggregate và SELECT INTO khi không có hàng nguồn

Một điểm dễ nhầm: SELECT INTO không phải lúc nào cũng phát sinh `NO_DATA_FOUND` khi bảng không có hàng phù hợp. Các hàm aggregate không có `GROUP BY` thường trả đúng một hàng kết quả.

### 10.1. COUNT trả 0

```sql
DECLARE
    v_count NUMBER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM employees
    WHERE department_id = 999;

    DBMS_OUTPUT.PUT_LINE('Count=' || v_count);
END;
/
```

Nếu không có nhân viên ở department 999, `COUNT(*)` trả 0. SELECT vẫn trả một hàng aggregate nên không phát sinh `NO_DATA_FOUND`.

### 10.2. SUM, AVG, MIN, MAX có thể trả NULL

```sql
DECLARE
    v_total_salary NUMBER;
BEGIN
    SELECT SUM(salary)
    INTO v_total_salary
    FROM employees
    WHERE department_id = 999;

    IF v_total_salary IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('No salary values');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Total=' || v_total_salary);
    END IF;
END;
/
```

Khi không có hàng đầu vào, `SUM`, `AVG`, `MIN` và `MAX` thường trả NULL trong một hàng kết quả. `COUNT` trả 0. Nếu có `GROUP BY`, truy vấn có thể không tạo group nào và do đó không trả hàng; khi đó scalar SELECT INTO có thể phát sinh `NO_DATA_FOUND`.

### 10.3. GROUP BY có thể tạo nhiều hàng

```sql
SELECT department_id, COUNT(*)
INTO v_department_id, v_count
FROM employees
GROUP BY department_id;
```

Nếu có nhiều phòng ban, truy vấn trả nhiều group và gây `TOO_MANY_ROWS`. Nếu mục tiêu là đếm theo từng phòng ban, hãy dùng cursor hoặc `BULK COLLECT`.

## 11. Dùng cursor để phân biệt “không có hàng” với “một hoặc nhiều hàng”

Cursor phù hợp khi số hàng có thể thay đổi và chương trình cần xử lý từng hàng.

Ví dụ:

```sql
BEGIN
    FOR r IN (
        SELECT employee_id, last_name
        FROM employees
        WHERE department_id = 999
        ORDER BY employee_id
    ) LOOP
        DBMS_OUTPUT.PUT_LINE(
            r.employee_id || ' ' || r.last_name
        );
    END LOOP;

    DBMS_OUTPUT.PUT_LINE('Loop completed');
END;
/
```

Nếu không có hàng, vòng lặp không chạy và block vẫn in `Loop completed`. Đây là hành vi khác với `SELECT ... INTO`, vốn phát sinh `NO_DATA_FOUND`.

### 11.1. Kiểm tra cursor có hàng bằng %NOTFOUND

Với explicit cursor:

```sql
DECLARE
    CURSOR c_orders IS
        SELECT order_id, total_amount
        FROM orders
        WHERE customer_id = 501;

    v_order_id orders.order_id%TYPE;
    v_total orders.total_amount%TYPE;
BEGIN
    OPEN c_orders;
    FETCH c_orders INTO v_order_id, v_total;

    IF c_orders%NOTFOUND THEN
        DBMS_OUTPUT.PUT_LINE('No orders');
    ELSE
        DBMS_OUTPUT.PUT_LINE(
            'First order=' || v_order_id
        );
    END IF;

    CLOSE c_orders;
END;
/
```

Nếu cần xử lý tất cả hàng, phải tiếp tục FETCH trong loop cho đến `%NOTFOUND`, không chỉ fetch một lần.

## 12. JOIN và nguy cơ TOO_MANY_ROWS

Một truy vấn có thể có WHERE chọn đúng một hàng ở bảng cha nhưng vẫn trả nhiều hàng do JOIN một-nhiều.

Giả sử:

- `CUSTOMERS.CUSTOMER_ID` là primary key.
- Một khách hàng có thể có nhiều đơn hàng trong `ORDERS`.

Truy vấn:

```sql
SELECT c.customer_name,
       o.order_id
INTO v_customer_name,
     v_order_id
FROM customers c
JOIN orders o
  ON o.customer_id = c.customer_id
WHERE c.customer_id = 501;
```

Nếu khách hàng 501 có ba đơn hàng, truy vấn trả ba hàng và phát sinh `TOO_MANY_ROWS`.

### 12.1. Chỉ lấy dữ liệu của bảng cha

Nếu mục tiêu là tên khách hàng:

```sql
SELECT customer_name
INTO v_customer_name
FROM customers
WHERE customer_id = 501;
```

Không JOIN bảng con nếu không cần dữ liệu bảng con.

### 12.2. Dùng EXISTS khi chỉ cần kiểm tra có bản ghi con

```sql
SELECT c.customer_name
INTO v_customer_name
FROM customers c
WHERE c.customer_id = 501
  AND EXISTS (
      SELECT 1
      FROM orders o
      WHERE o.customer_id = c.customer_id
  );
```

EXISTS kiểm tra sự tồn tại mà không nhân bản hàng cha theo số lượng hàng con. Tuy nhiên, nếu khách hàng không có đơn hàng, SELECT INTO sẽ phát sinh `NO_DATA_FOUND`; điều này có thể đúng hoặc không tùy nghiệp vụ.

### 12.3. Chỉ lấy một hàng con theo quy tắc

```sql
SELECT order_id
INTO v_order_id
FROM orders
WHERE customer_id = 501
ORDER BY order_date DESC, order_id DESC
FETCH FIRST 1 ROW ONLY;
```

Chỉ dùng cách này nếu nghiệp vụ cần đơn hàng mới nhất. Nếu cần toàn bộ đơn hàng, dùng cursor.

## 13. Tránh kiểm tra COUNT rồi SELECT lần thứ hai

Một pattern dễ thấy:

```sql
SELECT COUNT(*)
INTO v_count
FROM customers
WHERE customer_id = p_customer_id;

IF v_count > 0 THEN
    SELECT customer_name
    INTO v_customer_name
    FROM customers
    WHERE customer_id = p_customer_id;
END IF;
```

Pattern này thực hiện hai lần truy vấn. Ngoài chi phí dư thừa, hai statement có thể quan sát trạng thái dữ liệu khác nhau khi có transaction đồng thời thay đổi bảng. Kết quả COUNT > 0 không phải cam kết rằng câu SELECT sau chắc chắn vẫn có hàng.

Nếu mục tiêu là đọc một hàng và xử lý trường hợp không có, hãy SELECT INTO một lần rồi bắt `NO_DATA_FOUND`:

```sql
BEGIN
    SELECT customer_name
    INTO v_customer_name
    FROM customers
    WHERE customer_id = p_customer_id;

    v_found := TRUE;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        v_found := FALSE;
END;
```

Nếu chỉ cần biết có hay không mà không cần dữ liệu hàng, dùng EXISTS hoặc COUNT tùy mục đích. Nếu cần đọc dữ liệu, tránh query lặp lại chỉ để kiểm tra trước.

## 14. Xử lý đồng thời và read consistency

Oracle cung cấp read consistency ở mức statement trong READ COMMITTED mặc định. Mỗi câu SELECT nhìn thấy dữ liệu đã commit tại thời điểm nhất quán của statement đó, cùng với các thay đổi của transaction hiện tại.

### 14.1. Không có hàng tại snapshot của statement

Một session có thể SELECT INTO và nhận `NO_DATA_FOUND` vì hàng chưa được commit ở session khác tại thời điểm statement bắt đầu. Nếu session kia commit sau đó, câu SELECT tiếp theo có thể nhìn thấy hàng.

### 14.2. Hai câu SELECT có thể thấy hai trạng thái khác nhau

Ví dụ:

1. Session A chạy `COUNT(*)` và nhận 1.
2. Session B xóa hàng rồi COMMIT.
3. Session A chạy SELECT INTO và nhận `NO_DATA_FOUND`.

Trong READ COMMITTED, mỗi statement có snapshot riêng. Vì vậy, COUNT trước không bảo đảm SELECT sau trả cùng số hàng.

### 14.3. SELECT INTO không khóa hàng

SELECT INTO thông thường chỉ đọc dữ liệu theo read consistency; nó không tự khóa hàng để ngăn session khác sửa hoặc xóa sau khi đọc.

Nếu nghiệp vụ cần đọc rồi cập nhật và phải ngăn thay đổi đồng thời trên hàng, cân nhắc `SELECT ... FOR UPDATE` trong cùng transaction. `FOR UPDATE` là chủ đề khóa và đồng thời; chỉ dùng khi thật sự cần khóa, vì nó giữ row lock cho đến COMMIT hoặc ROLLBACK.

## 15. Exception handling có trách nhiệm

### 15.1. Bắt lỗi cụ thể

```sql
BEGIN
    SELECT department_name
    INTO v_department_name
    FROM departments
    WHERE department_id = p_department_id;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        -- Xử lý trường hợp không có phòng ban.
        NULL;
    WHEN TOO_MANY_ROWS THEN
        -- Truy vấn đáng lẽ phải duy nhất.
        RAISE_APPLICATION_ERROR(
            -20002,
            'Department lookup returned duplicate rows'
        );
END;
```

Trong code thực tế, thay `NULL` bằng hành động phù hợp với nghiệp vụ: gán mặc định, đánh dấu không tìm thấy hoặc truyền lỗi cho caller.

### 15.2. WHEN OTHERS không thay thế handler cụ thể

```sql
BEGIN
    SELECT employee_id
    INTO v_employee_id
    FROM employees
    WHERE employee_id = p_employee_id;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE_APPLICATION_ERROR(
            -20003,
            'Employee not found'
        );
    WHEN TOO_MANY_ROWS THEN
        RAISE_APPLICATION_ERROR(
            -20004,
            'Employee ID is not unique'
        );
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(
            'Unexpected error: ' || SQLCODE || ' ' || SQLERRM
        );
        RAISE;
END;
```

Handler cụ thể diễn đạt đúng hai trường hợp cardinality. `WHEN OTHERS` chỉ xử lý lỗi ngoài dự kiến, ghi nhận thông tin rồi ném lại để caller không hiểu nhầm thao tác thành công.

### 15.3. Không dùng exception để thay thế luồng điều khiển thông thường

Nếu truy vấn thường xuyên có thể trả 0 đến nhiều hàng, cursor hoặc collection thường diễn đạt ý định rõ hơn. Exception phù hợp để xử lý trường hợp lệch khỏi kỳ vọng của một thao tác exact fetch.

Ví dụ, tìm nhân viên theo primary key và không có nhân viên là tình huống có thể dùng `NO_DATA_FOUND`. Nhưng lấy danh sách nhân viên của phòng ban bằng scalar SELECT INTO là sai cấu trúc ngay từ đầu; không nên dùng `TOO_MANY_ROWS` như một cách kiểm tra danh sách.

## 16. SELECT INTO và SQLCODE/SQLERRM

Có thể ghi lại mã và thông báo trong exception handler:

```sql
DECLARE
    v_name employees.last_name%TYPE;
BEGIN
    SELECT last_name
    INTO v_name
    FROM employees
    WHERE employee_id = -1;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('Code=' || SQLCODE);
        DBMS_OUTPUT.PUT_LINE('Message=' || SQLERRM);
END;
/
```

Các giá trị thường gặp:

| Exception | Oracle error | SQLCODE thường gặp |
|---|---|---:|
| `NO_DATA_FOUND` | ORA-01403 | `+100` |
| `TOO_MANY_ROWS` | ORA-01422 | `-1422` |

Thông điệp lỗi có thể thay đổi theo ngôn ngữ hoặc phiên bản. Hãy dùng tên exception hoặc mã lỗi để phân nhánh, không parse chuỗi SQLERRM như một API ổn định.

## 17. SELECT INTO trong named procedure và anonymous block

Quy tắc exact fetch giống nhau dù câu lệnh nằm trong anonymous block, procedure, function hoặc trigger.

Ví dụ procedure:

```sql
CREATE OR REPLACE PROCEDURE get_employee_name (
    p_employee_id IN employees.employee_id%TYPE,
    p_last_name OUT employees.last_name%TYPE
) AS
BEGIN
    SELECT last_name
    INTO p_last_name
    FROM employees
    WHERE employee_id = p_employee_id;
END;
/
```

Nếu ID không tồn tại, procedure truyền `NO_DATA_FOUND` ra caller vì chưa có handler. Nếu query trả nhiều hàng, `TOO_MANY_ROWS` được truyền ra. Caller có thể xử lý hoặc procedure có thể chuyển thành lỗi nghiệp vụ rõ ràng.

Gọi procedure:

```sql
DECLARE
    v_last_name employees.last_name%TYPE;
BEGIN
    get_employee_name(100, v_last_name);
    DBMS_OUTPUT.PUT_LINE(v_last_name);
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('Employee not found');
END;
/
```

## 18. SELECT INTO và Java/JDBC

Ứng dụng Java thường gọi procedure hoặc gửi PL/SQL block có SELECT INTO. Khi SELECT INTO phát sinh lỗi và không được xử lý trong PL/SQL, Oracle JDBC driver chuyển lỗi về `SQLException`.

Ví dụ gọi procedure đã tạo:

```java
String sql = "{ call get_employee_name(?, ?) }";

try (CallableStatement cs = connection.prepareCall(sql)) {
    cs.setLong(1, employeeId);
    cs.registerOutParameter(2, java.sql.Types.VARCHAR);

    cs.execute();

    String lastName = cs.getString(2);
} catch (SQLException ex) {
    int oracleCode = ex.getErrorCode();
    String message = ex.getMessage();

    // Phân loại lỗi theo mã Oracle hoặc lỗi nghiệp vụ đã được ánh xạ.
    throw ex;
}
```

Nếu procedure để `NO_DATA_FOUND` hoặc `TOO_MANY_ROWS` truyền ra, ứng dụng có thể nhận mã Oracle tương ứng. Nếu procedure bắt lỗi và trả về OUT status thay vì ném lại, Java phải kiểm tra status đó.

Không nên để Java nhận một giá trị OUT chưa được gán rồi tự suy đoán rằng đó là “không tìm thấy”. Hãy định nghĩa hợp đồng rõ ràng: exception, OUT status hoặc result set.

### 18.1. Khi nào trả result set thay vì SELECT INTO?

Nếu ứng dụng cần danh sách, hãy trả nhiều hàng qua ResultSet/ref cursor hoặc query trực tiếp bằng JDBC:

```java
String sql =
    "SELECT employee_id, last_name " +
    "FROM employees " +
    "WHERE department_id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setInt(1, departmentId);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("EMPLOYEE_ID");
            String name = rs.getString("LAST_NAME");
            // Xử lý từng hàng.
        }
    }
}
```

JDBC ResultSet tự thể hiện 0, 1 hoặc nhiều hàng; không cần biến scalar và hai exception exact fetch của PL/SQL.

## 19. Các lỗi và nhầm lẫn thường gặp

| Lỗi/hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `NO_DATA_FOUND` / ORA-01403 | SELECT INTO không trả hàng | Kiểm tra bind/predicate; xử lý optional hoặc báo lỗi nghiệp vụ |
| `TOO_MANY_ROWS` / ORA-01422 | SELECT INTO trả từ hai hàng | Kiểm tra cardinality, JOIN, constraint; dùng cursor nếu cần nhiều hàng |
| `ORA-00947: not enough values` | Số biểu thức SELECT không khớp số biến INTO | Cân bằng danh sách SELECT và INTO |
| `ORA-00913: too many values` | SELECT trả nhiều biểu thức hơn biến nhận | Khai báo đủ biến hoặc giảm SELECT list |
| `PLS-00306` | Sai số lượng/kiểu tham số hoặc biến nhận không tương thích trong một lời gọi | Kiểm tra kiểu và cấu trúc nhận |
| Kết quả sai do JOIN | JOIN một-nhiều làm nhân bản hàng | Kiểm tra cardinality; dùng EXISTS hoặc cursor theo mục tiêu |
| Dùng COUNT rồi SELECT | Hai lần truy vấn, có thể thấy snapshot khác nhau | SELECT INTO một lần và bắt NO_DATA_FOUND nếu cần dữ liệu |
| Dùng DISTINCT để tránh TOO_MANY_ROWS | Che giấu nhiều hàng không đúng kỳ vọng | Xác định quy tắc nghiệp vụ và constraint |
| Chọn hàng tùy tiện bằng ROWNUM | Giới hạn trước khi sắp xếp đúng | Sắp xếp trong inline view hoặc dùng FETCH FIRST |
| Aggregate trả NULL nhưng không báo lỗi | SUM/AVG/MIN/MAX trên tập rỗng trả một hàng NULL | Kiểm tra IS NULL; COUNT trả 0 |
| Cursor rỗng bị coi là NO_DATA_FOUND | Nhầm semantics cursor với SELECT INTO | Kiểm tra `%NOTFOUND` hoặc vòng FOR |
| BULK COLLECT không có hàng | Collection rỗng, không phải scalar NO_DATA_FOUND | Kiểm tra collection.COUNT |
| Bắt WHEN OTHERS rồi bỏ qua | Che lỗi ngoài dự kiến | Log có kiểm soát rồi RAISE |

### 19.1. Phân biệt ORA-01403 và ORA-01422

- `ORA-01403` nói rằng exact fetch không tìm thấy hàng.
- `ORA-01422` nói rằng exact fetch nhận nhiều hàng hơn yêu cầu.

Hai lỗi cho biết hai hướng điều tra khác nhau: một bên là không có dữ liệu thỏa điều kiện; bên kia là truy vấn hoặc giả định duy nhất không đúng.

### 19.2. Kiểm tra kiểu dữ liệu

Ví dụ:

```sql
DECLARE
    v_salary NUMBER(8, 2);
BEGIN
    SELECT salary
    INTO v_salary
    FROM employees
    WHERE employee_id = 100;
END;
/
```

Nếu giá trị không thể chuyển đổi hoặc vượt giới hạn của biến nhận, có thể phát sinh lỗi chuyển đổi/giá trị như `VALUE_ERROR`. Dùng `%TYPE` giúp giảm nguy cơ không tương thích giữa biến và cột.

## 20. Bài thực hành tổng hợp

Các ví dụ dưới đây dùng bảng mẫu `EMPLOYEES` trong Oracle sample schema. Hãy kiểm tra schema và quyền truy cập trước khi chạy. Các ví dụ chủ yếu đọc dữ liệu; phần INSERT/UPDATE không cần thiết cho bài này.

### Bước 1. SELECT INTO một hàng theo khóa

```sql
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
```

### Bước 2. Tạo tình huống NO_DATA_FOUND

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
        DBMS_OUTPUT.PUT_LINE('No employee found');
END;
/
```

### Bước 3. Tạo tình huống TOO_MANY_ROWS

```sql
DECLARE
    v_name employees.last_name%TYPE;
BEGIN
    SELECT last_name
    INTO v_name
    FROM employees
    WHERE department_id = 10;

    DBMS_OUTPUT.PUT_LINE(v_name);
EXCEPTION
    WHEN TOO_MANY_ROWS THEN
        DBMS_OUTPUT.PUT_LINE('More than one employee');
END;
/
```

Kết quả phụ thuộc dữ liệu sample schema; nếu department 10 chỉ có một hàng thì handler không chạy. Có thể chọn điều kiện đã biết trả nhiều hàng trong schema lab.

### Bước 4. Nhận nhiều cột bằng %TYPE

```sql
DECLARE
    v_id employees.employee_id%TYPE;
    v_name employees.last_name%TYPE;
    v_salary employees.salary%TYPE;
BEGIN
    SELECT employee_id, last_name, salary
    INTO v_id, v_name, v_salary
    FROM employees
    WHERE employee_id = 100;

    DBMS_OUTPUT.PUT_LINE(
        v_id || ' ' || v_name || ' ' || v_salary
    );
END;
/
```

### Bước 5. Aggregate trên tập rỗng

```sql
DECLARE
    v_count NUMBER;
    v_total_salary NUMBER;
BEGIN
    SELECT COUNT(*), SUM(salary)
    INTO v_count, v_total_salary
    FROM employees
    WHERE department_id = 999;

    DBMS_OUTPUT.PUT_LINE('Count=' || v_count);

    IF v_total_salary IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('SUM is NULL for this empty set');
    END IF;
END;
/
```

### Bước 6. Dùng cursor khi cần nhiều hàng

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

### Bước 7. Chọn hàng mới nhất một cách xác định

```sql
DECLARE
    v_order_id orders.order_id%TYPE;
    v_order_date orders.order_date%TYPE;
BEGIN
    SELECT order_id, order_date
    INTO v_order_id, v_order_date
    FROM orders
    WHERE customer_id = 501
    ORDER BY order_date DESC, order_id DESC
    FETCH FIRST 1 ROW ONLY;

    DBMS_OUTPUT.PUT_LINE('Latest order=' || v_order_id);
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('No order found');
END;
/
```

Ví dụ giả định có bảng `ORDERS` với các cột tương ứng và Oracle 12c Release 1 trở lên.

### Bước 8. Dùng BULK COLLECT cho danh sách

```sql
DECLARE
    TYPE id_list_t IS TABLE OF employees.employee_id%TYPE;
    v_ids id_list_t;
BEGIN
    SELECT employee_id
    BULK COLLECT INTO v_ids
    FROM employees
    WHERE department_id = 10;

    DBMS_OUTPUT.PUT_LINE('Rows=' || v_ids.COUNT);
END;
/
```

Nếu không có nhân viên phù hợp, `v_ids.COUNT` là 0.

### Bước 9. Quan sát mã lỗi

```sql
BEGIN
    DECLARE
        v_name employees.last_name%TYPE;
    BEGIN
        SELECT last_name
        INTO v_name
        FROM employees
        WHERE employee_id = -1;
    END;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE(
            'Code=' || SQLCODE || ', message=' || SQLERRM
        );
END;
/
```

### Bước 10. Bật DBMS_OUTPUT

Trong SQL*Plus hoặc SQLcl:

```sql
SET SERVEROUTPUT ON;
```

Trong SQL Developer, bật panel DBMS Output cho đúng connection. Dấu `/` trên dòng riêng là lệnh client để gửi block, không phải một phần câu lệnh PL/SQL.

## 21. Quy tắc ghi nhớ

| Nhu cầu | Cách dùng |
|---|---|
| Đọc đúng một hàng | `SELECT ... INTO ...` |
| Không tìm thấy hàng | Bắt `NO_DATA_FOUND` hoặc chuyển thành lỗi nghiệp vụ |
| Truy vấn trả nhiều hàng ngoài dự kiến | Bắt `TOO_MANY_ROWS`, điều tra predicate/JOIN/constraint |
| Đọc danh sách nhiều hàng | Cursor FOR loop hoặc explicit cursor |
| Đưa nhiều hàng vào collection | `SELECT ... BULK COLLECT INTO ...` |
| Fetch theo batch | Cursor với `FETCH BULK COLLECT ... LIMIT n` |
| Chọn một hàng theo ưu tiên | `ORDER BY ... FETCH FIRST 1 ROW ONLY` |
| Đếm số hàng phù hợp | `COUNT(*) INTO`; không có group thì nhận 0 nếu tập nguồn rỗng |
| Tổng trên tập rỗng | `SUM`/`AVG`/`MIN`/`MAX` thường nhận NULL |
| Bảo đảm tối đa một hàng | PRIMARY KEY/UNIQUE constraint và predicate phù hợp |
| Tránh JOIN nhân bản | Hiểu quan hệ 1-1, 1-n; cân nhắc EXISTS hoặc truy vấn riêng |
| Xử lý lỗi tổng quát | `WHEN OTHERS` ghi nhận rồi `RAISE` nếu caller cần biết |

## 22. Câu hỏi tự kiểm tra

**Câu 1.** SELECT INTO trong PL/SQL yêu cầu truy vấn trả bao nhiêu hàng?

**Trả lời:** Đúng một hàng để gán kết quả vào các biến nhận.

**Câu 2.** Nếu truy vấn không trả hàng, exception nào được phát sinh?

**Trả lời:** `NO_DATA_FOUND` (ORA-01403).

**Câu 3.** Nếu truy vấn trả hai hàng trở lên, exception nào được phát sinh?

**Trả lời:** `TOO_MANY_ROWS` (ORA-01422).

**Câu 4.** SELECT INTO có cần số biến nhận bằng số cột trong SELECT list không?

**Trả lời:** Có. Mỗi biểu thức được gán vào biến tương ứng theo vị trí và kiểu phải tương thích.

**Câu 5.** Vì sao dùng `%TYPE` cho biến nhận?

**Trả lời:** Để biến bám theo kiểu dữ liệu của cột/biến nguồn và giảm lặp lại khai báo kiểu.

**Câu 6.** COUNT(*) INTO trên tập dữ liệu rỗng có phát sinh NO_DATA_FOUND không?

**Trả lời:** Không. Aggregate COUNT không GROUP BY trả một hàng với giá trị 0.

**Câu 7.** SUM(salary) trên tập rỗng trả gì?

**Trả lời:** Thường trả một hàng có giá trị NULL; cần kiểm tra IS NULL.

**Câu 8.** Nếu cần xử lý nhiều nhân viên, nên dùng SELECT INTO hay cursor?

**Trả lời:** Dùng cursor FOR loop, explicit cursor hoặc BULK COLLECT.

**Câu 9.** Cursor FOR loop không có hàng có phát sinh NO_DATA_FOUND không?

**Trả lời:** Không. Vòng lặp chạy 0 lần.

**Câu 10.** BULK COLLECT không có hàng có phát sinh NO_DATA_FOUND không?

**Trả lời:** Không chỉ vì không có hàng; collection nhận được là rỗng.

**Câu 11.** Vì sao JOIN có thể gây TOO_MANY_ROWS dù lọc theo primary key của bảng cha?

**Trả lời:** Bảng con có thể có nhiều hàng cho một hàng cha, khiến kết quả JOIN nhân bản.

**Câu 12.** Có nên thêm FETCH FIRST 1 ROW ONLY để chữa mọi TOO_MANY_ROWS không?

**Trả lời:** Không. Chỉ dùng khi nghiệp vụ thật sự cần chọn một hàng theo quy tắc sắp xếp; nếu truy vấn phải duy nhất, hãy sửa predicate hoặc constraint.

**Câu 13.** Vì sao COUNT rồi SELECT lần nữa có thể không an toàn?

**Trả lời:** Hai câu là hai statement có snapshot riêng trong READ COMMITTED; dữ liệu có thể thay đổi giữa chúng và còn phát sinh truy vấn dư thừa.

**Câu 14.** SELECT INTO thông thường có khóa hàng không?

**Trả lời:** Không. Nó đọc theo read consistency; muốn khóa để đọc rồi cập nhật cần cân nhắc SELECT FOR UPDATE.

**Câu 15.** TOO_MANY_ROWS có SQLCODE thường gặp là bao nhiêu?

**Trả lời:** `-1422`; NO_DATA_FOUND thường có SQLCODE `+100`.

## 23. Kết luận

`SELECT ... INTO` là cách đưa dữ liệu từ SQL vào biến PL/SQL khi chương trình kỳ vọng đúng một hàng. Truy vấn không có hàng sẽ phát sinh `NO_DATA_FOUND`; truy vấn có nhiều hàng sẽ phát sinh `TOO_MANY_ROWS`. Hai exception này không chỉ là lỗi cú pháp: chúng phản ánh cardinality thực tế của dữ liệu so với kỳ vọng của chương trình.

Hãy dùng khóa chính hoặc unique key để bảo đảm truy vấn tối đa một hàng, đồng thời vẫn xử lý trường hợp không tìm thấy. Khi cần nhiều hàng, dùng cursor hoặc `BULK COLLECT`; khi cần chọn một hàng trong số nhiều hàng, xác định quy tắc nghiệp vụ bằng `ORDER BY` và row limiting có thứ tự rõ ràng. Aggregate không GROUP BY là trường hợp đặc biệt: `COUNT` trả 0 trên tập rỗng, còn `SUM`, `AVG`, `MIN`, `MAX` thường trả NULL trong một hàng kết quả.

Cuối cùng, hiểu tác động của JOIN, read consistency và transaction giúp tránh các lỗi khó phát hiện như đếm trước rồi truy vấn sau, hoặc chọn đại một hàng để che dữ liệu trùng. Bắt `NO_DATA_FOUND` và `TOO_MANY_ROWS` theo đúng ý nghĩa nghiệp vụ, giữ `WHEN OTHERS` có trách nhiệm và để caller biết khi thao tác thật sự thất bại.
