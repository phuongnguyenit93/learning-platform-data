# Explicit cursor: khai báo, mở, fetch và đóng

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** PL/SQL và dữ liệu  
> **Mục tiêu:** Hiểu và sử dụng explicit cursor trong PL/SQL: khai báo truy vấn, mở cursor, fetch từng hàng và đóng cursor. Biết cách khai báo cursor có tham số, nhận dữ liệu bằng biến hoặc record, dùng cursor attributes, xử lý hết dữ liệu và exception an toàn; áp dụng FOR UPDATE và WHERE CURRENT OF khi cần cập nhật hàng đang đọc; lựa chọn explicit cursor hay cursor FOR LOOP và SQL set-based theo đúng nhu cầu.

## 1. Cursor là gì?

Một câu SELECT có thể trả về không, một hoặc nhiều hàng. Khi PL/SQL cần xử lý từng hàng của kết quả, cursor cung cấp một cách làm việc với tập kết quả đó.

Có thể hình dung cursor như một vùng làm việc gắn với câu truy vấn đang thực thi:

1. Khai báo cursor để xác định câu SELECT.
2. Mở cursor để Oracle thực thi truy vấn và thiết lập tập kết quả.
3. FETCH để lấy từng hàng vào biến hoặc record PL/SQL.
4. Kiểm tra cursor attribute để biết còn hàng hay đã hết.
5. Đóng cursor để giải phóng tài nguyên liên quan.

**Explicit cursor** là cursor do lập trình viên khai báo và điều khiển rõ ràng bằng OPEN, FETCH và CLOSE. Nó thường dùng khi cần kiểm soát chi tiết vòng đời cursor hoặc xử lý từng hàng theo logic PL/SQL.

Ví dụ tổng quát:

~~~sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id, employee_name, salary
        FROM employees
        WHERE department_id = 10
        ORDER BY employee_id;

    l_employee_id employees.employee_id%TYPE;
    l_employee_name employees.employee_name%TYPE;
    l_salary employees.salary%TYPE;
BEGIN
    OPEN c_employees;

    LOOP
        FETCH c_employees
        INTO l_employee_id, l_employee_name, l_salary;

        EXIT WHEN c_employees%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(
            l_employee_id || ' - ' ||
            l_employee_name || ' - ' ||
            l_salary
        );
    END LOOP;

    CLOSE c_employees;
END;
/
~~~

Ví dụ này thể hiện đủ bốn thao tác: khai báo, mở, fetch và đóng.

## 2. Khai báo explicit cursor

Cursor được khai báo trong phần khai báo của một PL/SQL block, procedure, function hoặc package.

Cú pháp cơ bản:

~~~sql
CURSOR cursor_name IS
    select_statement;
~~~

Ví dụ:

~~~sql
DECLARE
    CURSOR c_open_orders IS
        SELECT order_id,
               customer_id,
               order_date,
               total_amount
        FROM orders
        WHERE status = 'OPEN';
BEGIN
    NULL;
END;
/
~~~

Việc khai báo cursor chỉ định nghĩa truy vấn. Nó chưa thực thi SELECT và chưa lấy hàng. Truy vấn được thực thi khi chương trình mở cursor bằng OPEN.

### 2.1. Cursor phải trả về tập cột phù hợp với FETCH

Nếu FETCH vào từng biến:

~~~sql
DECLARE
    CURSOR c_dept IS
        SELECT department_id, department_name
        FROM departments;

    l_department_id departments.department_id%TYPE;
    l_department_name departments.department_name%TYPE;
BEGIN
    OPEN c_dept;

    FETCH c_dept
    INTO l_department_id, l_department_name;

    CLOSE c_dept;
END;
/
~~~

Số lượng, thứ tự và kiểu dữ liệu của biến nhận phải tương thích với select list của cursor. Nếu query trả hai cột mà FETCH chỉ nhận một biến, chương trình không biên dịch hoặc phát sinh lỗi tương ứng.

Để giảm phụ thuộc vào kiểu dữ liệu và độ dài cột, nên dùng thuộc tính %TYPE thay vì tự khai báo NUMBER/VARCHAR2 với kích thước tùy ý.

### 2.2. Dùng cursor %ROWTYPE

Khi query trả nhiều cột, có thể khai báo record dựa trên cursor:

~~~sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id, employee_name, salary
        FROM employees
        WHERE department_id = 10;

    l_employee c_employees%ROWTYPE;
BEGIN
    OPEN c_employees;

    FETCH c_employees INTO l_employee;

    IF c_employees%FOUND THEN
        DBMS_OUTPUT.PUT_LINE(l_employee.employee_name);
    END IF;

    CLOSE c_employees;
END;
/
~~~

Record c_employees%ROWTYPE có các field tương ứng với select list của cursor. Tên field dựa trên tên cột hoặc alias của query.

Ví dụ dùng alias để đặt tên field rõ ràng:

~~~sql
DECLARE
    CURSOR c_sales IS
        SELECT sale_id AS id,
               amount AS sale_amount
        FROM sales;

    l_sale c_sales%ROWTYPE;
BEGIN
    OPEN c_sales;
    FETCH c_sales INTO l_sale;

    IF c_sales%FOUND THEN
        DBMS_OUTPUT.PUT_LINE(
            l_sale.id || ': ' || l_sale.sale_amount
        );
    END IF;

    CLOSE c_sales;
END;
/
~~~

Nếu dùng record theo %ROWTYPE, FETCH phải nhận toàn bộ row shape của cursor. Không thể chỉ fetch một phần field của record trong câu FETCH thông thường; nếu cần chọn một số cột, khai báo biến nhận riêng hoặc một record phù hợp.

## 3. OPEN: thực thi truy vấn và mở cursor

Cú pháp:

~~~sql
OPEN cursor_name;
~~~

OPEN yêu cầu Oracle thực thi câu SELECT được khai báo trong cursor và thiết lập context để FETCH các hàng.

Ví dụ:

~~~sql
DECLARE
    CURSOR c_products IS
        SELECT product_id, product_name
        FROM products
        WHERE active_flag = 'Y';

    l_product_id products.product_id%TYPE;
    l_product_name products.product_name%TYPE;
BEGIN
    OPEN c_products;

    FETCH c_products
    INTO l_product_id, l_product_name;

    CLOSE c_products;
END;
/
~~~

OPEN không đưa tất cả hàng vào các biến PL/SQL. Mỗi FETCH lấy hàng tiếp theo theo thứ tự của query result. Nếu cần thứ tự xử lý xác định, câu SELECT nên có ORDER BY với tiêu chí đủ phân biệt các hàng.

### 3.1. Mở cursor nhiều lần

Một explicit cursor có thể được mở lại sau khi đã đóng. Mỗi lần OPEN sẽ bắt đầu một lần thực thi cursor mới theo tham số và snapshot phù hợp.

~~~sql
OPEN c_products;
-- FETCH và xử lý
CLOSE c_products;

OPEN c_products;
-- Một lượt đọc mới
CLOSE c_products;
~~~

Không OPEN một cursor đang mở. OPEN lại khi cursor chưa CLOSE gây INVALID_CURSOR.

### 3.2. Truy vấn được thực thi ở thời điểm OPEN

Nếu bảng nguồn thay đổi giữa hai lần mở, mỗi lần OPEN có thể quan sát dữ liệu đã commit theo snapshot của statement tương ứng. Cursor đã mở tiếp tục đại diện cho lần thực thi đó; nó không tự động trở thành một truy vấn mới sau mỗi FETCH.

Điều này quan trọng khi xử lý dữ liệu đồng thời. Một cursor không phải cơ chế tự động cập nhật tập kết quả khi session khác thay đổi bảng.

## 4. FETCH: lấy từng hàng

Cú pháp:

~~~sql
FETCH cursor_name INTO variable_1, variable_2, ...;
~~~

Mỗi FETCH lấy hàng tiếp theo từ tập kết quả và gán các cột vào biến nhận theo thứ tự select list.

Ví dụ:

~~~sql
DECLARE
    CURSOR c_departments IS
        SELECT department_id, department_name
        FROM departments
        ORDER BY department_id;

    l_id departments.department_id%TYPE;
    l_name departments.department_name%TYPE;
BEGIN
    OPEN c_departments;

    FETCH c_departments INTO l_id, l_name;

    IF c_departments%FOUND THEN
        DBMS_OUTPUT.PUT_LINE('First department: ' || l_name);
    END IF;

    CLOSE c_departments;
END;
/
~~~

Nếu cursor không trả hàng nào, FETCH không ném NO_DATA_FOUND như SELECT INTO. Thay vào đó, cursor attribute %NOTFOUND trở thành TRUE và %FOUND trở thành FALSE sau lần FETCH không lấy được hàng.

### 4.1. Vòng lặp FETCH phổ biến

~~~sql
OPEN c_employees;

LOOP
    FETCH c_employees INTO l_employee;

    EXIT WHEN c_employees%NOTFOUND;

    -- Xử lý hàng hiện tại
    DBMS_OUTPUT.PUT_LINE(l_employee.employee_name);
END LOOP;

CLOSE c_employees;
~~~

Điểm quan trọng là kiểm tra %NOTFOUND ngay sau FETCH và trước khi xử lý record. FETCH cuối cùng có thể không tìm thấy hàng; không xử lý record cũ như thể nó là một hàng mới.

### 4.2. Dùng EXIT WHEN %NOTFOUND

Đây là mẫu dễ đọc và thường được sử dụng:

~~~sql
LOOP
    FETCH c_orders INTO l_order;
    EXIT WHEN c_orders%NOTFOUND;

    process_order(l_order.order_id);
END LOOP;
~~~

Có thể dùng EXIT WHEN NOT c_orders%FOUND sau FETCH. Hai cách biểu đạt cùng mục tiêu khi cursor đã được mở và đã FETCH.

### 4.3. Vì sao không kiểm tra %NOTFOUND trước FETCH?

Sau OPEN, chưa có hàng nào được FETCH. %FOUND và %NOTFOUND chưa xác định giá trị TRUE/FALSE theo nghĩa đã lấy hàng; giá trị thuộc trạng thái NULL. Nếu viết:

~~~sql
WHILE c_orders%NOTFOUND LOOP
    FETCH c_orders INTO l_order;
END LOOP;
~~~

vòng lặp không chạy như mong đợi vì điều kiện WHILE không TRUE ở thời điểm đầu. Mẫu đúng là FETCH trước rồi EXIT WHEN %NOTFOUND.

### 4.4. FETCH từng biến và FETCH record

FETCH vào từng biến:

~~~sql
FETCH c_employees
INTO l_employee_id, l_employee_name, l_salary;
~~~

FETCH vào record:

~~~sql
FETCH c_employees INTO l_employee;
~~~

Record thường gọn hơn khi query có nhiều cột và toàn bộ hàng cần được xử lý cùng nhau. Biến riêng phù hợp khi chỉ cần một vài cột hoặc muốn biểu đạt rõ dữ liệu được dùng.

## 5. CLOSE: đóng cursor

Cú pháp:

~~~sql
CLOSE cursor_name;
~~~

CLOSE kết thúc việc sử dụng cursor đang mở và giải phóng các tài nguyên cursor liên quan. Sau khi đóng, không thể FETCH tiếp cho đến khi OPEN lại.

Ví dụ hoàn chỉnh:

~~~sql
DECLARE
    CURSOR c_customers IS
        SELECT customer_id, customer_name
        FROM customers
        ORDER BY customer_id;

    l_customer c_customers%ROWTYPE;
BEGIN
    OPEN c_customers;

    LOOP
        FETCH c_customers INTO l_customer;
        EXIT WHEN c_customers%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(
            l_customer.customer_id || ': ' ||
            l_customer.customer_name
        );
    END LOOP;

    CLOSE c_customers;
END;
/
~~~

### 5.1. Vì sao phải đóng cursor?

Đóng cursor khi hoàn tất giúp giải phóng tài nguyên và tránh giữ cursor mở lâu hơn cần thiết. Nếu cursor không còn cần dùng, đừng giữ nó mở trong khi chương trình chờ người dùng hoặc gọi dịch vụ bên ngoài.

Kết thúc một PL/SQL block thường giải phóng cursor local theo vòng đời block, nhưng vẫn nên viết CLOSE tường minh để kiểm soát tài nguyên và làm rõ ý định.

### 5.2. Không đóng cursor chưa mở hoặc đóng hai lần

Các thao tác sai:

~~~sql
CLOSE c_orders; -- khi cursor chưa được OPEN
~~~

hoặc:

~~~sql
OPEN c_orders;
CLOSE c_orders;
CLOSE c_orders; -- đóng lần thứ hai
~~~

Có thể phát sinh INVALID_CURSOR. Dùng %ISOPEN để kiểm tra trạng thái trước khi đóng trong phần xử lý exception.

## 6. Cursor attributes

Explicit cursor cung cấp các thuộc tính để kiểm tra trạng thái và số hàng đã fetch.

| Attribute | Ý nghĩa |
|---|---|
| %ISOPEN | TRUE nếu cursor đang mở; FALSE nếu chưa mở hoặc đã đóng |
| %FOUND | TRUE nếu FETCH gần nhất lấy được một hàng; FALSE nếu không |
| %NOTFOUND | TRUE nếu FETCH gần nhất không lấy được hàng; FALSE nếu có |
| %ROWCOUNT | Số hàng đã FETCH thành công từ lần OPEN hiện tại |

Ví dụ:

~~~sql
DECLARE
    CURSOR c_products IS
        SELECT product_id
        FROM products;

    l_product_id products.product_id%TYPE;
BEGIN
    OPEN c_products;

    DBMS_OUTPUT.PUT_LINE(
        'Is open: ' ||
        CASE WHEN c_products%ISOPEN THEN 'YES' ELSE 'NO' END
    );

    LOOP
        FETCH c_products INTO l_product_id;
        EXIT WHEN c_products%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(
            'Fetched rows: ' || c_products%ROWCOUNT
        );
    END LOOP;

    DBMS_OUTPUT.PUT_LINE(
        'Total fetched: ' || c_products%ROWCOUNT
    );

    CLOSE c_products;
END;
/
~~~

### 6.1. %ISOPEN

%ISOPEN kiểm tra cursor có đang mở hay không. Đây là attribute có thể dùng để kiểm tra an toàn trước CLOSE.

~~~sql
IF c_orders%ISOPEN THEN
    CLOSE c_orders;
END IF;
~~~

%ISOPEN trả FALSE nếu cursor chưa mở hoặc đã đóng.

### 6.2. %FOUND và %NOTFOUND

Hai thuộc tính này mô tả kết quả của FETCH gần nhất:

- Sau FETCH lấy được hàng: %FOUND = TRUE, %NOTFOUND = FALSE.
- Sau FETCH không lấy được hàng: %FOUND = FALSE, %NOTFOUND = TRUE.
- Sau OPEN nhưng trước FETCH đầu tiên: chưa có kết quả FETCH để kiểm tra; các thuộc tính này có giá trị NULL.

Không dùng %FOUND/%NOTFOUND trước lần FETCH đầu tiên để quyết định vòng lặp.

### 6.3. %ROWCOUNT

%ROWCOUNT bắt đầu từ 0 sau OPEN và tăng một sau mỗi FETCH thành công. FETCH không tìm thấy hàng không làm tăng số đếm.

~~~sql
OPEN c_orders;

LOOP
    FETCH c_orders INTO l_order;
    EXIT WHEN c_orders%NOTFOUND;

    DBMS_OUTPUT.PUT_LINE(
        'Current row number: ' || c_orders%ROWCOUNT
    );
END LOOP;

DBMS_OUTPUT.PUT_LINE(
    'Rows fetched: ' || c_orders%ROWCOUNT
);

CLOSE c_orders;
~~~

%ROWCOUNT là số hàng đã lấy, không nhất thiết là số hàng đã cập nhật hoặc xóa. Nếu chương trình chỉ xử lý một phần tập kết quả, giá trị này chỉ phản ánh số hàng đã FETCH.

### 6.4. Trạng thái cursor sau CLOSE

Sau CLOSE, cursor không còn mở. %ISOPEN trả FALSE. Các attribute khác như %FOUND, %NOTFOUND hoặc %ROWCOUNT không nên tiếp tục tham chiếu; việc truy cập cursor đã đóng có thể gây INVALID_CURSOR.

## 7. Cursor có tham số

Cursor có thể nhận tham số để tái sử dụng cùng một câu SELECT cho các giá trị đầu vào khác nhau.

Cú pháp:

~~~sql
CURSOR cursor_name (
    parameter_name datatype
) IS
    SELECT ...;
~~~

Ví dụ:

~~~sql
DECLARE
    CURSOR c_employees_by_dept (
        p_department_id employees.department_id%TYPE
    ) IS
        SELECT employee_id, employee_name, salary
        FROM employees
        WHERE department_id = p_department_id
        ORDER BY employee_id;

    l_employee c_employees_by_dept%ROWTYPE;
BEGIN
    OPEN c_employees_by_dept(10);

    LOOP
        FETCH c_employees_by_dept INTO l_employee;
        EXIT WHEN c_employees_by_dept%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(
            l_employee.employee_id || ': ' ||
            l_employee.employee_name
        );
    END LOOP;

    CLOSE c_employees_by_dept;
END;
/
~~~

P_DEPARTMENT_ID là tham số của cursor. Khi OPEN, truyền giá trị thực tế. Query dùng tham số đó làm điều kiện lọc.

### 7.1. Mở lại với tham số khác

Có thể tái sử dụng cursor sau khi đóng:

~~~sql
OPEN c_employees_by_dept(10);
-- Fetch và xử lý
CLOSE c_employees_by_dept;

OPEN c_employees_by_dept(20);
-- Fetch tập kết quả cho department 20
CLOSE c_employees_by_dept;
~~~

Mỗi lần OPEN, truyền bộ tham số cần dùng cho lần thực thi mới.

### 7.2. Dùng nhiều kiểu tham số

~~~sql
DECLARE
    CURSOR c_orders (
        p_customer_id orders.customer_id%TYPE,
        p_min_total NUMBER
    ) IS
        SELECT order_id, total_amount
        FROM orders
        WHERE customer_id = p_customer_id
          AND total_amount >= p_min_total;
BEGIN
    OPEN c_orders(100, 500);
    -- FETCH...
    CLOSE c_orders;
END;
/
~~~

Nên dùng %TYPE cho tham số có cùng ý nghĩa với cột để tránh lệch kiểu khi schema thay đổi. Các tham số cursor là đầu vào cho truy vấn; chúng không phải biến được cập nhật từ bên trong cursor.

## 8. Xử lý exception và bảo đảm CLOSE

Một lỗi có thể xảy ra sau OPEN nhưng trước CLOSE, ví dụ lỗi chuyển kiểu, lỗi trong procedure xử lý một hàng hoặc lỗi DML. Nếu không đóng cursor, chương trình có thể giữ tài nguyên lâu hơn cần thiết.

Mẫu an toàn:

~~~sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id, employee_name
        FROM employees;

    l_employee c_employees%ROWTYPE;
BEGIN
    OPEN c_employees;

    LOOP
        FETCH c_employees INTO l_employee;
        EXIT WHEN c_employees%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(l_employee.employee_name);
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
~~~

Nếu exception xảy ra khi cursor đang mở, nhánh WHEN OTHERS kiểm tra %ISOPEN rồi đóng cursor. RAISE chuyển lỗi gốc lên caller để caller quyết định xử lý.

Không nên bắt mọi lỗi rồi chỉ in thông báo và bỏ qua. Việc nuốt exception có thể làm caller tưởng rằng xử lý đã thành công.

### 8.1. Dùng nested block để giới hạn phạm vi cleanup

~~~sql
DECLARE
    CURSOR c_orders IS
        SELECT order_id
        FROM orders
        WHERE status = 'OPEN';

    l_order_id orders.order_id%TYPE;
BEGIN
    OPEN c_orders;

    BEGIN
        LOOP
            FETCH c_orders INTO l_order_id;
            EXIT WHEN c_orders%NOTFOUND;

            process_order(l_order_id);
        END LOOP;
    EXCEPTION
        WHEN OTHERS THEN
            IF c_orders%ISOPEN THEN
                CLOSE c_orders;
            END IF;
            RAISE;
    END;

    IF c_orders%ISOPEN THEN
        CLOSE c_orders;
    END IF;
END;
/
~~~

Nested block giúp cleanup gần với đoạn code có thể phát sinh lỗi. Trong chương trình thực tế, có thể tách xử lý cursor thành procedure riêng để dễ quản lý vòng đời và exception.

## 9. Cursor FOR LOOP: cách viết gọn hơn

PL/SQL hỗ trợ cursor FOR LOOP. Oracle tự động OPEN cursor, FETCH từng hàng, kiểm tra hết dữ liệu và CLOSE cursor khi vòng lặp kết thúc hoặc thoát bằng exception.

Ví dụ dùng cursor đã khai báo:

~~~sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id, employee_name
        FROM employees
        WHERE department_id = 10
        ORDER BY employee_id;
BEGIN
    FOR r_employee IN c_employees LOOP
        DBMS_OUTPUT.PUT_LINE(
            r_employee.employee_id || ': ' ||
            r_employee.employee_name
        );
    END LOOP;
END;
/
~~~

Không cần khai báo biến record riêng, không cần OPEN/FETCH/CLOSE thủ công. Biến R_EMPLOYEE được PL/SQL khai báo ngầm và chỉ có phạm vi bên trong vòng lặp.

### 9.1. Cursor FOR LOOP với tham số

~~~sql
DECLARE
    CURSOR c_employees (
        p_department_id employees.department_id%TYPE
    ) IS
        SELECT employee_id, employee_name
        FROM employees
        WHERE department_id = p_department_id;
BEGIN
    FOR r_employee IN c_employees(20) LOOP
        DBMS_OUTPUT.PUT_LINE(r_employee.employee_name);
    END LOOP;
END;
/
~~~

PL/SQL tự mở cursor với tham số 20 và đóng khi vòng lặp kết thúc.

### 9.2. Cursor FOR LOOP với truy vấn trực tiếp

Có thể bỏ khai báo explicit cursor nếu chỉ cần một vòng lặp:

~~~sql
BEGIN
    FOR r_order IN (
        SELECT order_id, total_amount
        FROM orders
        WHERE status = 'OPEN'
        ORDER BY order_id
    ) LOOP
        DBMS_OUTPUT.PUT_LINE(
            r_order.order_id || ': ' || r_order.total_amount
        );
    END LOOP;
END;
/
~~~

Đây là implicit cursor FOR LOOP: Oracle quản lý cursor nội bộ. Cách viết ngắn và dễ đọc khi query chỉ được dùng tại một vị trí.

### 9.3. Khi nào vẫn cần OPEN/FETCH/CLOSE tường minh?

Explicit OPEN/FETCH/CLOSE hữu ích khi:

- Cần fetch theo từng bước ở nhiều vị trí khác nhau.
- Cần kiểm soát chính xác thời điểm mở và đóng.
- Cần dùng cursor attribute giữa các thao tác.
- Cần phối hợp cursor với logic transaction hoặc lock đặc thù.
- Cần truyền cursor hoặc quản lý vòng đời trong một cấu trúc phức tạp.

Nếu chỉ duyệt mọi hàng một lần, cursor FOR LOOP thường dễ đọc và ít lỗi cleanup hơn.

## 10. Cursor FOR UPDATE và khóa hàng

Một explicit cursor có thể khai báo SELECT FOR UPDATE để khóa các hàng được chọn, phục vụ đọc-sửa-ghi an toàn trong transaction.

Ví dụ:

~~~sql
DECLARE
    CURSOR c_accounts IS
        SELECT account_id, balance
        FROM accounts
        WHERE status = 'ACTIVE'
        FOR UPDATE OF balance;

    l_account c_accounts%ROWTYPE;
BEGIN
    OPEN c_accounts;

    LOOP
        FETCH c_accounts INTO l_account;
        EXIT WHEN c_accounts%NOTFOUND;

        UPDATE accounts
        SET balance = balance + 100
        WHERE CURRENT OF c_accounts;
    END LOOP;

    CLOSE c_accounts;
    COMMIT;
END;
/
~~~

FOR UPDATE khóa các hàng được chọn cho transaction. Các session khác muốn thay đổi những hàng đó phải chờ hoặc nhận lỗi tùy cách lấy lock.

### 10.1. WHERE CURRENT OF

WHERE CURRENT OF cursor_name cập nhật hoặc xóa hàng hiện tại mà cursor FOR UPDATE đang trỏ tới:

~~~sql
UPDATE accounts
SET balance = balance + 100
WHERE CURRENT OF c_accounts;
~~~

Không cần tự lấy khóa chính từ record rồi viết lại điều kiện WHERE. Oracle xác định hàng hiện tại theo cursor đang mở.

WHERE CURRENT OF chỉ dùng với cursor thích hợp có FOR UPDATE và đang ở trạng thái hợp lệ. Không dùng nó với cursor đã đóng hoặc cursor không được khai báo FOR UPDATE.

Có thể DELETE hàng hiện tại:

~~~sql
DELETE FROM staging_orders
WHERE CURRENT OF c_staging_orders;
~~~

### 10.2. OF column

Trong FOR UPDATE OF, tên cột chỉ rõ cột/tables được khóa trong một số truy vấn join. Nó không có nghĩa chỉ riêng cột đó bị khóa; Oracle khóa hàng tương ứng. Cột được liệt kê giúp xác định bảng cần khóa khi query có nhiều bảng.

### 10.3. NOWAIT, WAIT và SKIP LOCKED

Có thể thêm chính sách chờ:

~~~sql
CURSOR c_accounts IS
    SELECT account_id, balance
    FROM accounts
    WHERE status = 'ACTIVE'
    FOR UPDATE NOWAIT;
~~~

NOWAIT yêu cầu lấy lock ngay; nếu không được, câu lệnh trả lỗi resource busy.

~~~sql
CURSOR c_accounts IS
    SELECT account_id, balance
    FROM accounts
    WHERE status = 'ACTIVE'
    FOR UPDATE WAIT 5;
~~~

WAIT 5 chờ tối đa khoảng năm giây.

~~~sql
CURSOR c_jobs IS
    SELECT job_id, payload
    FROM job_queue
    WHERE status = 'READY'
    FOR UPDATE SKIP LOCKED;
~~~

SKIP LOCKED bỏ qua hàng đang bị khóa để worker có thể lấy hàng khác. Chỉ dùng khi semantics queue và cơ chế retry/claim phù hợp.

### 10.4. Thời gian giữ lock

Lock được giữ đến COMMIT hoặc ROLLBACK. Nếu cursor FOR UPDATE đọc hàng triệu dòng rồi xử lý chậm, transaction có thể giữ nhiều row lock lâu và làm tăng blocking.

Hãy lọc đúng phạm vi, xử lý nhanh, không gọi dịch vụ ngoài trong lúc giữ khóa và chọn transaction boundary theo yêu cầu nghiệp vụ.

## 11. Không COMMIT tùy tiện giữa vòng FETCH FOR UPDATE

Một lỗi thiết kế phổ biến là COMMIT sau từng hàng trong vòng lặp cursor FOR UPDATE:

~~~sql
-- Không nên dùng mẫu này cho cursor FOR UPDATE
LOOP
    FETCH c_accounts INTO l_account;
    EXIT WHEN c_accounts%NOTFOUND;

    UPDATE accounts
    SET balance = balance + 100
    WHERE CURRENT OF c_accounts;

    COMMIT;
END LOOP;
~~~

COMMIT giải phóng các row lock và có thể làm cursor FOR UPDATE không còn dùng được cho các lần FETCH tiếp theo; chương trình có thể nhận ORA-01002 (fetch out of sequence).

Ngoài ra, commit từng hàng làm mất atomicity của batch và tăng commit overhead. Nếu lỗi giữa vòng lặp, một phần dữ liệu đã commit trong khi phần còn lại chưa xử lý.

Nếu cần chia batch lớn, hãy thiết kế các batch độc lập có khóa phạm vi rõ, trạng thái tiến độ và khả năng chạy lại. Không chỉ thêm COMMIT vào vòng lặp để “giải phóng lock”.

Với cursor đọc thông thường không FOR UPDATE, hành vi khi commit giữa fetch và khả năng consistent read phụ thuộc transaction/query lifetime; vẫn cần tránh giữ query quá lâu khi undo có thể bị tái sử dụng. Không coi việc cursor còn mở sau commit là một chiến lược batching an toàn.

## 12. Explicit cursor và implicit cursor

Oracle tự tạo implicit cursor cho một số câu SQL như INSERT, UPDATE, DELETE và SELECT INTO. PL/SQL cung cấp các attribute SQL%FOUND, SQL%NOTFOUND, SQL%ROWCOUNT và SQL%ISOPEN để xem trạng thái câu SQL gần nhất.

Explicit cursor do lập trình viên khai báo và điều khiển, dùng tên cursor riêng:

~~~sql
c_employees%ROWCOUNT
~~~

Implicit cursor attribute dùng tiền tố SQL:

~~~sql
SQL%ROWCOUNT
~~~

Ví dụ implicit cursor sau UPDATE:

~~~sql
BEGIN
    UPDATE employees
    SET salary = salary * 1.05
    WHERE department_id = 10;

    DBMS_OUTPUT.PUT_LINE(
        'Updated rows: ' || SQL%ROWCOUNT
    );
END;
/
~~~

Đây không phải explicit cursor. Câu UPDATE tự thực thi; không có OPEN/FETCH/CLOSE do lập trình viên viết.

### 12.1. SELECT INTO và explicit cursor khác nhau

SELECT INTO phù hợp khi mong đợi đúng một hàng:

~~~sql
SELECT employee_name
INTO l_employee_name
FROM employees
WHERE employee_id = 100;
~~~

Nếu không có hàng, SELECT INTO ném NO_DATA_FOUND. Nếu có nhiều hơn một hàng, nó ném TOO_MANY_ROWS.

Explicit cursor phù hợp khi cần duyệt nhiều hàng. FETCH không ném NO_DATA_FOUND khi đến cuối tập kết quả; kiểm tra %NOTFOUND để kết thúc vòng lặp.

| Nhu cầu | Cách dùng |
|---|---|
| Lấy đúng một hàng | SELECT INTO |
| Chạy DML một lần và xem số hàng | SQL%ROWCOUNT |
| Duyệt nhiều hàng bằng vòng lặp tự quản lý | Explicit cursor |
| Duyệt nhiều hàng với quản lý tự động | Cursor FOR LOOP |

## 13. Cursor và hiệu năng: tránh row-by-row khi có thể

Cursor giúp xử lý từng hàng, nhưng vòng lặp từng hàng có thể chậm hơn một câu SQL set-based vì PL/SQL phải chuyển điều khiển qua lại với SQL engine nhiều lần.

Ví dụ xử lý tăng lương toàn bộ nhân viên phòng 10:

Cách row-by-row:

~~~sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id, salary
        FROM employees
        WHERE department_id = 10;

BEGIN
    FOR r IN c_employees LOOP
        UPDATE employees
        SET salary = r.salary * 1.05
        WHERE employee_id = r.employee_id;
    END LOOP;
END;
/
~~~

Nếu mọi hàng áp dụng cùng quy tắc, dùng một UPDATE:

~~~sql
UPDATE employees
SET salary = salary * 1.05
WHERE department_id = 10;
~~~

Câu UPDATE set-based thường đơn giản hơn, ít context switch và để optimizer xử lý tập hàng.

### 13.1. Khi cursor phù hợp

Explicit cursor phù hợp khi từng hàng cần:

- Quyết định xử lý dựa trên nhiều bước PL/SQL.
- Gọi procedure khác với dữ liệu hàng hiện tại.
- Áp dụng quy tắc không thể biểu diễn gọn bằng một câu SQL set-based.
- Dùng SELECT FOR UPDATE và WHERE CURRENT OF.
- Ghi nhận kết quả hoặc lỗi riêng từng hàng theo thiết kế.

Ngay cả khi cần xử lý từng hàng, hãy cân nhắc BULK COLLECT và FORALL để giảm context switch khi tập dữ liệu lớn và thao tác phù hợp với bulk processing.

### 13.2. BULK COLLECT và FORALL là bước nâng cao

BULK COLLECT lấy nhiều hàng vào collection trong một lần fetch; FORALL thực hiện DML cho nhiều phần tử collection. Đây là kỹ thuật khác với FETCH từng hàng truyền thống.

Ví dụ minh họa:

~~~sql
DECLARE
    TYPE id_list_t IS TABLE OF employees.employee_id%TYPE;
    l_ids id_list_t;
BEGIN
    SELECT employee_id
    BULK COLLECT INTO l_ids
    FROM employees
    WHERE department_id = 10;

    FORALL i IN 1 .. l_ids.COUNT
        UPDATE employees
        SET status = 'REVIEWED'
        WHERE employee_id = l_ids(i);
END;
/
~~~

Với tập lớn, BULK COLLECT không giới hạn có thể tiêu thụ nhiều PGA. Có thể dùng LIMIT với cursor fetch bulk trong vòng lặp. Chỉ áp dụng khi có lý do đo được; một câu DML set-based vẫn thường là lựa chọn đầu tiên.

## 14. Các lỗi thường gặp với explicit cursor

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Quên OPEN trước FETCH | INVALID_CURSOR | Mở cursor trước khi fetch |
| OPEN cursor đang mở | INVALID_CURSOR | CLOSE trước khi OPEN lại |
| FETCH sau CLOSE | INVALID_CURSOR | Chỉ FETCH khi cursor đang mở |
| CLOSE cursor chưa mở hoặc đã đóng | INVALID_CURSOR | Kiểm tra %ISOPEN |
| Không kiểm tra %NOTFOUND sau FETCH | Xử lý record cũ khi đã hết hàng | FETCH rồi EXIT WHEN %NOTFOUND |
| Kiểm tra %NOTFOUND trước FETCH đầu tiên | Vòng lặp không chạy như mong đợi | Đặt FETCH trước điều kiện EXIT |
| Số biến FETCH không khớp select list | Lỗi biên dịch/thực thi | Khớp số lượng, thứ tự và datatype |
| Không đóng cursor khi exception | Giữ tài nguyên lâu hơn cần thiết | Cleanup bằng %ISOPEN và RAISE |
| Dùng SELECT INTO cho nhiều hàng | TOO_MANY_ROWS | Dùng cursor hoặc query tổng hợp |
| Mong FETCH hết dữ liệu ném NO_DATA_FOUND | Vòng lặp không bắt được như dự kiến | Kiểm tra %NOTFOUND |
| COMMIT trong cursor FOR UPDATE | Có thể ORA-01002 và nhả lock sớm | Chọn transaction boundary khác |
| Duyệt cursor để làm cùng một UPDATE cho mọi hàng | Chậm, nhiều context switch | Dùng set-based DML |
| Quên ORDER BY nhưng kỳ vọng thứ tự cố định | Thứ tự FETCH không được bảo đảm | Thêm ORDER BY nếu nghiệp vụ cần |
| Giữ cursor/transaction mở quá lâu | Tăng tài nguyên, lock và rủi ro undo | Giới hạn phạm vi, xử lý nhanh, đóng cursor |

## 15. Bài thực hành

Chạy các bài trên schema lab được phép. Bật DBMS_OUTPUT trong công cụ SQL để xem thông báo.

### Bài 1 — Khai báo cursor

Khai báo cursor lấy EMPLOYEE_ID, EMPLOYEE_NAME và SALARY từ EMPLOYEES. Chưa cần OPEN; giải thích vì sao khai báo cursor chưa thực thi SELECT.

### Bài 2 — OPEN và FETCH một hàng

Mở cursor, FETCH một hàng vào các biến %TYPE, in ra dữ liệu và đóng cursor. Thêm ORDER BY để biết hàng đầu tiên theo tiêu chí nào.

### Bài 3 — Duyệt toàn bộ kết quả

Dùng LOOP, FETCH và EXIT WHEN c_cursor%NOTFOUND. Đếm số hàng bằng %ROWCOUNT và in tổng số sau vòng lặp.

### Bài 4 — Cursor không có hàng

Thêm predicate không có dữ liệu. Xác nhận FETCH đầu tiên không ném NO_DATA_FOUND và %NOTFOUND trở thành TRUE.

### Bài 5 — Record theo cursor %ROWTYPE

Thay các biến riêng bằng biến record c_cursor%ROWTYPE. Truy cập field theo tên cột hoặc alias trong select list.

### Bài 6 — Cursor có tham số

Khai báo cursor nhận DEPARTMENT_ID. Mở cùng cursor với hai department khác nhau, đóng giữa hai lần OPEN và so sánh kết quả.

### Bài 7 — Cursor attributes

In %ISOPEN sau OPEN, %ROWCOUNT sau từng FETCH, %FOUND/%NOTFOUND sau FETCH thành công và FETCH cuối cùng. Đóng cursor rồi kiểm tra %ISOPEN.

### Bài 8 — Exception cleanup

Gọi một procedure có thể phát sinh lỗi trong vòng FETCH. Dùng WHEN OTHERS, kiểm tra %ISOPEN, CLOSE và RAISE. Xác nhận lỗi gốc vẫn được chuyển lên caller.

### Bài 9 — Cursor FOR LOOP

Viết lại bài duyệt toàn bộ kết quả bằng FOR r IN c_cursor LOOP. So sánh số dòng code và trách nhiệm quản lý OPEN/FETCH/CLOSE.

### Bài 10 — WHERE CURRENT OF

Tạo cursor FOR UPDATE cho các hàng staging. Fetch từng hàng, UPDATE hoặc DELETE bằng WHERE CURRENT OF, sau đó COMMIT một lần ở cuối transaction.

### Bài 11 — Blocking

Session A mở cursor FOR UPDATE và giữ transaction. Session B thử UPDATE cùng hàng. Quan sát B chờ, sau đó A COMMIT/ROLLBACK và xem B tiếp tục ra sao.

### Bài 12 — So sánh set-based với cursor

Tạo dữ liệu lab đủ lớn. Thực hiện cùng một phép cập nhật bằng vòng lặp cursor và một câu UPDATE set-based. So sánh elapsed time, số lần SQL execution và độ phức tạp code.

## 16. Checklist khi sử dụng explicit cursor

- [ ] Query cursor trả đúng các cột cần xử lý.
- [ ] Dùng %TYPE hoặc cursor %ROWTYPE để giảm lỗi lệch datatype.
- [ ] OPEN trước FETCH.
- [ ] FETCH rồi kiểm tra %NOTFOUND trước khi xử lý record.
- [ ] Dùng %ROWCOUNT cho số hàng đã fetch, không nhầm với số hàng DML.
- [ ] CLOSE khi hoàn tất.
- [ ] Đóng cursor trong exception path nếu vẫn đang mở.
- [ ] Không OPEN lại cursor đang mở.
- [ ] Dùng cursor parameter khi cùng query cần chạy với nhiều giá trị đầu vào.
- [ ] Dùng ORDER BY nếu thứ tự xử lý có ý nghĩa.
- [ ] Dùng FOR UPDATE/WHERE CURRENT OF chỉ khi cần khóa và cập nhật hàng hiện tại.
- [ ] Không COMMIT tùy tiện giữa vòng lặp cursor FOR UPDATE.
- [ ] Ưu tiên SQL set-based nếu mọi hàng áp dụng cùng một phép xử lý.
- [ ] Cân nhắc BULK COLLECT/FORALL khi cần xử lý nhiều hàng bằng PL/SQL.
- [ ] Kiểm thử cursor rỗng, một hàng, nhiều hàng và exception giữa vòng lặp.

## 17. Ghi nhớ cốt lõi

- Explicit cursor là cursor do lập trình viên khai báo và điều khiển vòng đời.
- Khai báo cursor định nghĩa SELECT; OPEN mới thực thi truy vấn và mở tập kết quả.
- FETCH lấy từng hàng theo thứ tự select list vào biến hoặc record tương thích.
- FETCH không tìm thấy hàng không ném NO_DATA_FOUND; dùng %NOTFOUND để kết thúc vòng lặp.
- %FOUND/%NOTFOUND mô tả FETCH gần nhất; %ROWCOUNT đếm số hàng đã fetch; %ISOPEN kiểm tra trạng thái mở.
- Sau OPEN nhưng trước FETCH đầu tiên, %FOUND và %NOTFOUND chưa có giá trị TRUE/FALSE để điều khiển vòng lặp.
- CLOSE kết thúc cursor; chỉ OPEN lại sau khi đã đóng.
- Cursor parameter giúp tái sử dụng cùng SELECT với nhiều giá trị đầu vào.
- Cursor FOR LOOP tự quản lý OPEN/FETCH/CLOSE và thường phù hợp khi chỉ cần duyệt một lần.
- SELECT FOR UPDATE khóa hàng; WHERE CURRENT OF cập nhật/xóa hàng hiện tại của cursor đang mở.
- COMMIT trong vòng lặp FOR UPDATE có thể giải phóng lock và làm lần FETCH tiếp theo lỗi; thiết kế transaction boundary rõ ràng.
- Ưu tiên set-based SQL cho phép biến đổi giống nhau trên nhiều hàng; dùng cursor khi logic thực sự cần xử lý từng hàng.
- Cleanup exception, giới hạn thời gian giữ cursor/lock và kiểm thử tập kết quả rỗng giúp chương trình PL/SQL ổn định.

### Tài liệu Oracle nên đối chiếu

- [Oracle Database PL/SQL Language Reference](https://docs.oracle.com/en/database/) — Explicit cursors, cursor FOR LOOP, cursor variables và cursor attributes.
- [Oracle Database PL/SQL Language Fundamentals](https://docs.oracle.com/en/database/) — Cursor declarations, records, %TYPE, %ROWTYPE và exception handling.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — SELECT FOR UPDATE, WHERE CURRENT OF, NOWAIT, WAIT và SKIP LOCKED.
- [Oracle Database Performance Tuning Guide](https://docs.oracle.com/en/database/) — SQL/PLSQL context switching, bulk processing và execution performance.
- [Oracle Database PL/SQL Packages and Types Reference](https://docs.oracle.com/en/database/) — BULK COLLECT, FORALL và các tiện ích PL/SQL liên quan.

Chi tiết locking, cursor behavior, bulk processing và datatype support có thể khác theo Oracle release. Hãy đối chiếu tài liệu đúng phiên bản và chạy các ví dụ trên schema lab, đặc biệt kiểm tra cursor rỗng, exception giữa vòng lặp và transaction dùng FOR UPDATE.

