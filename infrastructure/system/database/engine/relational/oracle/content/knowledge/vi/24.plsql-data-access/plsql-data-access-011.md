# Bind theo vị trí/tên và khác biệt giữa SQL động với block PL/SQL trong Oracle

Trong Oracle, bind variable cho phép truyền giá trị vào câu SQL hoặc block PL/SQL mà không phải nối giá trị đó trực tiếp vào chuỗi lệnh. Bind giúp tách phần cú pháp khỏi dữ liệu, giảm nguy cơ SQL injection, hỗ trợ tái sử dụng cursor và làm rõ kiểu dữ liệu đầu vào.

Khi viết SQL động trong PL/SQL, cần hiểu một quy tắc dễ gây lỗi: **cách Oracle ghép bind argument với placeholder phụ thuộc vào loại nội dung đang thực thi**.

- Với một **SQL statement động** như SELECT, INSERT, UPDATE hoặc DELETE, Oracle ghép bind argument theo **vị trí xuất hiện của từng placeholder**. Hai placeholder cùng viết tên vẫn là hai lần xuất hiện và cần hai bind argument tương ứng.
- Với một **anonymous PL/SQL block động** hoặc câu lệnh **CALL**, Oracle ghép theo **tên placeholder duy nhất**. Nếu cùng một tên placeholder xuất hiện nhiều lần, chỉ cần một bind argument cho tên đó.
- Với **DBMS_SQL**, chương trình có thể bind rõ ràng theo tên bằng thủ tục BIND_VARIABLE.
- Ở tầng ứng dụng, API như JDBC PreparedStatement tiêu chuẩn dùng chỉ số vị trí của dấu hỏi; framework hoặc API riêng của driver có thể cung cấp cách đặt tên tham số riêng.

Nhầm lẫn giữa các quy tắc này thường dẫn tới lỗi số lượng bind không khớp, truyền nhầm giá trị, hoặc câu lệnh chạy thành công nhưng xử lý sai dữ liệu. Bài học trình bày cách phân biệt, ví dụ cụ thể và cách thiết kế SQL động an toàn.

## 1. Bind variable là gì?

Bind variable là một vị trí giữ chỗ cho giá trị được cung cấp khi câu lệnh được thực thi. Trong SQL động của Oracle, placeholder thường được viết với dấu hai chấm, ví dụ:

~~~sql
SELECT employee_id, last_name
FROM employees
WHERE department_id = :p_department_id;
~~~

Ở đây, :p_department_id là placeholder. Giá trị thật được truyền riêng trong USING clause hoặc qua API bind của client.

So sánh hai cách tạo câu SQL:

~~~sql
-- Nối giá trị trực tiếp vào chuỗi:
l_sql := 'SELECT employee_id FROM employees WHERE department_id = '
         || TO_CHAR(p_department_id);

-- Dùng bind variable:
l_sql := 'SELECT employee_id FROM employees WHERE department_id = :dept';
EXECUTE IMMEDIATE l_sql
    BULK COLLECT INTO l_employee_ids
    USING p_department_id;
~~~

Cách bind có một câu lệnh ổn định về cấu trúc và truyền giá trị riêng. Cách nối chuỗi tạo ra nội dung SQL khác nhau theo dữ liệu đầu vào, làm tăng rủi ro injection và có thể làm giảm khả năng dùng lại cursor.

### 1.1. Bind là dữ liệu, không phải đoạn cú pháp SQL

Bind variable phù hợp cho giá trị:

~~~sql
WHERE employee_id = :employee_id
WHERE hire_date >= :from_date
WHERE salary < :max_salary
~~~

Bind không thay thế tên bảng, tên cột, từ khóa, toán tử hoặc hướng sắp xếp:

~~~sql
-- Không có nghĩa là chọn cột có tên truyền trong :column_name:
SELECT :column_name FROM employees;

-- Không có nghĩa là thay tên bảng bằng giá trị bind:
SELECT * FROM :table_name;
~~~

Trong các ví dụ trên, placeholder là một giá trị biểu thức; Oracle không diễn giải giá trị đó thành identifier của bảng hoặc cột.

### 1.2. Lợi ích của bind

- **An toàn:** dữ liệu đầu vào được xử lý như giá trị, không trở thành cú pháp SQL.
- **Tái sử dụng cursor:** cùng cấu trúc câu lệnh có thể được thực thi với nhiều giá trị khác nhau.
- **Kiểu dữ liệu rõ ràng:** driver hoặc PL/SQL truyền giá trị theo kiểu phù hợp, tránh nhiều lỗi chuyển đổi chuỗi.
- **Dễ bảo trì:** câu SQL không bị trộn lẫn với dữ liệu đầu vào.
- **Hiệu năng:** có thể giảm hard parse khi nhiều lần thực thi dùng cùng cấu trúc SQL, dù kết quả thực tế còn phụ thuộc cursor sharing, bind peeking, adaptive cursor sharing và workload.

Bind không đảm bảo mọi lần thực thi có cùng execution plan. Optimizer vẫn có thể chọn plan khác theo thống kê, bind sensitivity và các tính năng của phiên bản Oracle.

## 2. SQL động và block PL/SQL động khác nhau thế nào?

SQL động là câu lệnh SQL hoặc PL/SQL được tạo thành chuỗi và phân tích/thực thi tại runtime. Trong PL/SQL, Native Dynamic SQL thường dùng EXECUTE IMMEDIATE hoặc OPEN FOR.

Có hai dạng cần phân biệt.

### 2.1. Dynamic SQL statement

Chuỗi chứa một câu SQL như SELECT, INSERT, UPDATE, DELETE, MERGE hoặc DDL:

~~~sql
l_sql := 'UPDATE employees
          SET salary = salary + :increase
          WHERE employee_id = :employee_id';

EXECUTE IMMEDIATE l_sql
    USING p_increase, p_employee_id;
~~~

Oracle phân tích nội dung như một SQL statement. Các placeholder được ghép với bind arguments theo từng lần xuất hiện, từ trái sang phải.

### 2.2. Dynamic anonymous PL/SQL block

Chuỗi chứa một block PL/SQL, ví dụ:

~~~sql
l_block := 'BEGIN
                payroll_api.adjust_salary(
                    p_employee_id => :p_employee_id,
                    p_increase    => :p_increase
                );
            END;';

EXECUTE IMMEDIATE l_block
    USING p_employee_id, p_increase;
~~~

Oracle phân tích nội dung như một PL/SQL block. Các placeholder được ghép theo tên placeholder duy nhất. Nếu :p_employee_id xuất hiện lại ở vị trí khác, nó vẫn là cùng một bind placeholder.

### 2.3. So sánh nhanh

| Đặc điểm | SQL statement động | Anonymous PL/SQL block động |
|---|---|---|
| Nội dung chuỗi | SELECT, INSERT, UPDATE, DELETE, MERGE, DDL... | DECLARE/BEGIN/EXCEPTION/END |
| Cách chạy | EXECUTE IMMEDIATE hoặc OPEN FOR | EXECUTE IMMEDIATE |
| Ghép bind trong Native Dynamic SQL | Theo vị trí từng occurrence | Theo tên placeholder duy nhất |
| Placeholder lặp cùng tên | Mỗi occurrence cần bind argument riêng | Một bind argument cho tên đó |
| Có thể dùng biến OUT/IN OUT qua USING | Thường lấy kết quả qua INTO hoặc RETURNING INTO | Có thể dùng USING OUT/IN OUT |
| Có thể chứa IF/LOOP/EXCEPTION | Không, vì đây là SQL statement | Có |
| Mục đích | Cấu trúc SQL thay đổi tại runtime | Gọi logic PL/SQL hoặc thực thi block được tạo tại runtime |

Điểm phân biệt cốt lõi không nằm ở việc placeholder được viết là :x hay :name. Nó nằm ở loại câu lệnh mà Oracle đang thực thi.

## 3. Bind theo vị trí trong SQL statement động

Với Native Dynamic SQL, nếu chuỗi là một SQL statement, bind argument trong USING được ghép với placeholder theo thứ tự xuất hiện. Tên placeholder không tạo ra cơ chế ghép theo tên.

Ví dụ:

~~~sql
DECLARE
    l_sql VARCHAR2(1000);
BEGIN
    l_sql := 'UPDATE employees
              SET salary = :new_salary
              WHERE employee_id = :employee_id';

    EXECUTE IMMEDIATE l_sql
        USING 9000, 101;
END;
/
~~~

Thứ tự bind:

| Vị trí | Placeholder | Giá trị truyền |
|---:|---|---:|
| 1 | :new_salary | 9000 |
| 2 | :employee_id | 101 |

Tên placeholder có thể đổi thành :x và :y mà không đổi quy tắc ghép theo vị trí.

### 3.1. Placeholder lặp tên vẫn cần bind nhiều lần

Đây là trường hợp quan trọng:

~~~sql
DECLARE
    l_sql VARCHAR2(1000);
BEGIN
    l_sql := 'SELECT employee_id
              FROM employees
              WHERE department_id = :dept
                 OR manager_id = :dept';

    EXECUTE IMMEDIATE l_sql
        BULK COLLECT INTO l_employee_ids
        USING 10, 10;
END;
/
~~~

Trong một SQL statement, hai lần xuất hiện của :dept được xem là hai placeholder theo vị trí. Vì vậy USING cần hai bind argument. Nếu chỉ truyền một giá trị, Oracle có thể báo lỗi thiếu bind.

Bảng ánh xạ:

| Vị trí | Placeholder trong SQL | Bind argument |
|---:|---|---|
| 1 | :dept ở điều kiện department_id | Giá trị thứ nhất |
| 2 | :dept ở điều kiện manager_id | Giá trị thứ hai |

Hai giá trị có thể giống nhau, như ví dụ trên, nhưng vẫn phải truyền hai lần.

### 3.2. Đổi tên placeholder không đổi thứ tự

~~~sql
l_sql := 'SELECT employee_id
          FROM employees
          WHERE department_id = :first_value
             OR manager_id = :second_value';

EXECUTE IMMEDIATE l_sql
    BULK COLLECT INTO l_employee_ids
    USING p_department_id, p_manager_id;
~~~

Bind đầu tiên ứng với :first_value; bind thứ hai ứng với :second_value. Nếu đổi tên thành :x và :y thì ánh xạ vẫn theo thứ tự xuất hiện.

### 3.3. Cẩn thận khi thay đổi câu SQL

Giả sử ban đầu:

~~~sql
l_sql := 'UPDATE employees
          SET salary = :salary
          WHERE employee_id = :employee_id';

EXECUTE IMMEDIATE l_sql
    USING p_salary, p_employee_id;
~~~

Sau đó một người bảo trì thêm điều kiện:

~~~sql
l_sql := 'UPDATE employees
          SET salary = :salary
          WHERE department_id = :department_id
            AND employee_id = :employee_id';

EXECUTE IMMEDIATE l_sql
    USING p_salary, p_employee_id, p_department_id;
~~~

Đoạn thứ hai sai thứ tự: bind thứ hai phải là department ID, bind thứ ba mới là employee ID. Nên đặt tên biến PL/SQL có ý nghĩa và đặt bind arguments theo thứ tự placeholder trong chuỗi.

### 3.4. SELECT INTO và USING có vai trò khác nhau

Với dynamic SELECT một hàng:

~~~sql
DECLARE
    l_sql        VARCHAR2(500);
    l_last_name  employees.last_name%TYPE;
    l_salary     employees.salary%TYPE;
BEGIN
    l_sql := 'SELECT last_name, salary
              FROM employees
              WHERE employee_id = :employee_id';

    EXECUTE IMMEDIATE l_sql
        INTO l_last_name, l_salary
        USING 101;
END;
/
~~~

- INTO nhận dữ liệu trả về từ SELECT.
- USING cung cấp giá trị đầu vào cho placeholder.

Không đưa biến nhận kết quả SELECT vào USING. Số lượng và thứ tự biến trong INTO phải tương ứng với các cột trong select list.

Nếu SELECT không trả hàng, Oracle phát sinh NO_DATA_FOUND. Nếu trả nhiều hơn một hàng trong dạng INTO một hàng, Oracle phát sinh TOO_MANY_ROWS.

### 3.5. Truy vấn nhiều hàng với OPEN FOR

Khi số hàng trả về không cố định, có thể dùng REF CURSOR:

~~~sql
DECLARE
    l_sql    VARCHAR2(500);
    l_cursor SYS_REFCURSOR;
    l_id     employees.employee_id%TYPE;
    l_name   employees.last_name%TYPE;
BEGIN
    l_sql := 'SELECT employee_id, last_name
              FROM employees
              WHERE department_id = :dept
              ORDER BY employee_id';

    OPEN l_cursor FOR l_sql USING 10;

    LOOP
        FETCH l_cursor INTO l_id, l_name;
        EXIT WHEN l_cursor%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(l_id || ' - ' || l_name);
    END LOOP;

    CLOSE l_cursor;
END;
/
~~~

Với OPEN FOR, bind argument của dynamic SQL statement cũng theo vị trí. Cần đóng cursor sau khi dùng, kể cả trong nhánh xử lý lỗi của chương trình thực tế.

## 4. Bind theo tên trong anonymous PL/SQL block động

Với dynamic anonymous PL/SQL block hoặc CALL statement, Oracle ghép bind theo tên placeholder duy nhất. Một placeholder được nhắc lại nhiều lần trong block vẫn tham chiếu cùng bind.

Ví dụ:

~~~sql
DECLARE
    l_block VARCHAR2(1000);
BEGIN
    l_block := 'BEGIN
                    audit_api.record_values(
                        p_old_value => :value,
                        p_new_value => :value,
                        p_actor     => :actor
                    );
                END;';

    EXECUTE IMMEDIATE l_block
        USING 'ACTIVE', 'APP_USER';
END;
/
~~~

Ở đây có hai tên placeholder duy nhất:

1. :value
2. :actor

Dù :value xuất hiện hai lần, nó vẫn là một bind. USING cung cấp một giá trị cho :value và một giá trị cho :actor, theo thứ tự xuất hiện đầu tiên của mỗi tên trong block.

### 4.1. Placeholder lặp tên dùng chung một giá trị

~~~sql
l_block := 'BEGIN
                report_api.compare_values(
                    :input_value,
                    :input_value,
                    :output_value
                );
            END;';

EXECUTE IMMEDIATE l_block
    USING p_value, p_result;
~~~

Trong block:
- :input_value là một placeholder duy nhất, được dùng ở hai vị trí.
- :output_value là placeholder duy nhất thứ hai.

Nếu hai vị trí cần hai giá trị khác nhau, phải đặt hai tên placeholder khác nhau, ví dụ :first_value và :second_value.

### 4.2. Tên placeholder có ý nghĩa giúp tránh lỗi

~~~sql
l_block := 'BEGIN
                order_api.change_status(
                    p_order_id => :p_order_id,
                    p_status   => :p_status
                );
            END;';

EXECUTE IMMEDIATE l_block
    USING p_order_id, p_status;
~~~

Nên đặt tên placeholder phản ánh parameter của procedure. Tên rõ ràng không làm thay đổi thứ tự đối số trong USING, nhưng giúp người đọc hiểu hợp đồng giữa chuỗi PL/SQL động và giá trị được truyền.

### 4.3. Tên placeholder không phải cú pháp đặt tên argument trong USING

Trong Native Dynamic SQL, USING là danh sách bind arguments theo quy tắc của câu lệnh đang thực thi. Không viết theo dạng gán tên PL/SQL như:

~~~sql
-- Không phải cú pháp USING hợp lệ của EXECUTE IMMEDIATE:
EXECUTE IMMEDIATE l_block
    USING p_order_id => p_order_id;
~~~

Việc ghép theo tên trong dynamic PL/SQL block là quy tắc Oracle áp dụng cho các placeholder trong chuỗi block, không có nghĩa USING hỗ trợ named-argument notation giống lời gọi procedure thông thường.

## 5. Ví dụ đối chiếu cùng tên placeholder trong SQL và PL/SQL block

Đây là ví dụ quan trọng nhất để ghi nhớ sự khác nhau.

### 5.1. Trường hợp A: SQL statement

~~~sql
DECLARE
    l_sql VARCHAR2(1000);
BEGIN
    l_sql := 'UPDATE employees
              SET salary = salary + :amount
              WHERE manager_id = :amount';

    EXECUTE IMMEDIATE l_sql
        USING 500, 500;
END;
/
~~~

Có hai lần xuất hiện của :amount trong SQL statement, nên phải truyền hai bind arguments.

### 5.2. Trường hợp B: PL/SQL block

~~~sql
DECLARE
    l_block VARCHAR2(1000);
BEGIN
    l_block := 'BEGIN
                    payroll_api.apply_adjustment(
                        :amount,
                        :amount
                    );
                END;';

    EXECUTE IMMEDIATE l_block
        USING 500;
END;
/
~~~

Có một tên placeholder duy nhất là :amount, nên chỉ truyền một bind argument. Cả hai vị trí trong block nhận cùng giá trị.

### 5.3. Bảng kết luận

| Nội dung chuỗi | Số lần placeholder xuất hiện | Số tên placeholder duy nhất | Số bind arguments trong NDS |
|---|---:|---:|---:|
| SQL: WHERE a = :x OR b = :x | 2 | 1 | 2 |
| PL/SQL: BEGIN p(:x, :x); END; | 2 | 1 | 1 |
| SQL: WHERE a = :x AND b = :y | 2 | 2 | 2 |
| PL/SQL: BEGIN p(:x, :y); END; | 2 | 2 | 2 |
| SQL: WHERE a = :x OR b = :y OR c = :x | 3 | 2 | 3 |
| PL/SQL: BEGIN p(:x, :y, :x); END; | 3 | 2 | 2 |

Với dynamic PL/SQL block, USING arguments tương ứng các tên placeholder duy nhất theo thứ tự xuất hiện đầu tiên. Với SQL statement, mỗi occurrence được bind riêng theo vị trí.

## 6. IN, OUT và IN OUT trong dynamic PL/SQL block

Dynamic PL/SQL block có thể gọi procedure hoặc function có tham số đầu vào, đầu ra và hai chiều. Native Dynamic SQL cho phép chỉ định mode trong USING clause.

- IN: truyền giá trị vào block.
- OUT: nhận giá trị block trả về.
- IN OUT: truyền giá trị ban đầu và nhận giá trị sau khi block chạy.

### 6.1. Ví dụ OUT

Giả sử package có procedure trả về tổng tiền:

~~~sql
CREATE OR REPLACE PROCEDURE get_order_total (
    p_order_id IN NUMBER,
    p_total    OUT NUMBER
) AS
BEGIN
    SELECT NVL(SUM(quantity * unit_price), 0)
    INTO p_total
    FROM order_items
    WHERE order_id = p_order_id;
END;
/
~~~

Gọi bằng dynamic PL/SQL block:

~~~sql
DECLARE
    l_block VARCHAR2(500);
    l_total NUMBER;
BEGIN
    l_block := 'BEGIN
                    get_order_total(
                        p_order_id => :p_order_id,
                        p_total    => :p_total
                    );
                END;';

    EXECUTE IMMEDIATE l_block
        USING IN 1001, OUT l_total;

    DBMS_OUTPUT.PUT_LINE('Total = ' || l_total);
END;
/
~~~

Placeholder :p_order_id nhận input; :p_total nhận output. Thứ tự bind arguments trong USING khớp với thứ tự các tên placeholder xuất hiện lần đầu trong block.

### 6.2. Ví dụ IN OUT

~~~sql
CREATE OR REPLACE PROCEDURE add_fee (
    p_amount IN OUT NUMBER,
    p_fee    IN NUMBER
) AS
BEGIN
    p_amount := p_amount + p_fee;
END;
/
~~~

Gọi động:

~~~sql
DECLARE
    l_block  VARCHAR2(300);
    l_amount NUMBER := 1000;
BEGIN
    l_block := 'BEGIN
                    add_fee(:amount, :fee);
                END;';

    EXECUTE IMMEDIATE l_block
        USING IN OUT l_amount, IN 50;

    DBMS_OUTPUT.PUT_LINE(l_amount);
END;
/
~~~

Sau khi block chạy thành công, l_amount nhận giá trị mới. OUT/IN OUT phù hợp với dynamic PL/SQL block hoặc CALL. Với SQL query, kết quả thường được nhận qua INTO hoặc BULK COLLECT INTO; với DML có RETURNING, dùng cơ chế RETURNING INTO của EXECUTE IMMEDIATE.

### 6.3. Không dùng biến OUT như bind input thông thường

Phải xác định rõ parameter mode của procedure được gọi. Nếu block cần trả kết quả, placeholder tương ứng phải được bind với OUT hoặc IN OUT phù hợp. Truyền một biến output bằng mặc định IN không tạo ra đường trả kết quả.

## 7. Gọi procedure động và gọi procedure tĩnh

Nếu tên procedure và signature đã biết tại thời điểm compile, lời gọi tĩnh thường rõ ràng hơn:

~~~sql
BEGIN
    order_api.approve_order(p_order_id => 1001);
END;
/
~~~

Compiler có thể kiểm tra dependency và kiểu dữ liệu theo quy tắc compile của PL/SQL.

Nếu tên package/procedure hoặc cấu trúc block chỉ biết tại runtime, có thể dùng block động:

~~~sql
DECLARE
    l_block VARCHAR2(500);
BEGIN
    l_block := 'BEGIN order_api.approve_order(:p_order_id); END;';

    EXECUTE IMMEDIATE l_block USING 1001;
END;
/
~~~

Dùng dynamic block khi cần thực sự tạo cấu trúc PL/SQL tại runtime. Nếu chỉ truyền giá trị thay đổi cho procedure đã biết, lời gọi tĩnh đơn giản và dễ kiểm tra hơn.

### 7.1. Static PL/SQL và dynamic PL/SQL

| Tiêu chí | Static PL/SQL | Dynamic PL/SQL block |
|---|---|---|
| Nội dung | Viết trực tiếp trong source | Được tạo thành chuỗi |
| Kiểm tra compile | Có thể kiểm tra dependency và kiểu tại compile time | Nội dung chuỗi được parse khi chạy |
| Thay đổi tên object lúc runtime | Không linh hoạt | Có thể tạo tên object/block động, phải kiểm soát an toàn |
| Bind giá trị | Dùng biến PL/SQL trực tiếp trong static SQL hoặc lời gọi | Dùng placeholder và USING |
| Debug | Thường dễ hơn | Khó hơn vì source thực tế hình thành runtime |
| Rủi ro injection | Thấp hơn khi không dùng SQL động | Cần quản lý chuỗi, bind và identifier chặt chẽ |

## 8. Native Dynamic SQL: EXECUTE IMMEDIATE và OPEN FOR

Native Dynamic SQL (NDS) là cách viết SQL động trực tiếp trong PL/SQL bằng cú pháp ngôn ngữ.

### 8.1. DML

~~~sql
DECLARE
    l_sql VARCHAR2(500);
BEGIN
    l_sql := 'UPDATE employees
              SET salary = salary * :factor
              WHERE department_id = :dept';

    EXECUTE IMMEDIATE l_sql
        USING 1.05, 10;

    DBMS_OUTPUT.PUT_LINE('Rows updated: ' || SQL%ROWCOUNT);
END;
/
~~~

Sau DML, SQL%ROWCOUNT cho biết số hàng bị tác động bởi câu SQL vừa thực thi. Đây là thuộc tính implicit cursor của câu lệnh gần nhất.

### 8.2. SELECT một hàng

~~~sql
DECLARE
    l_sql    VARCHAR2(500);
    l_name   employees.last_name%TYPE;
BEGIN
    l_sql := 'SELECT last_name
              FROM employees
              WHERE employee_id = :id';

    EXECUTE IMMEDIATE l_sql
        INTO l_name
        USING 101;

    DBMS_OUTPUT.PUT_LINE(l_name);
END;
/
~~~

### 8.3. SELECT nhiều hàng

Có thể dùng OPEN FOR với REF CURSOR, hoặc BULK COLLECT INTO khi kiểu dữ liệu và kích thước kết quả phù hợp:

~~~sql
DECLARE
    TYPE t_names IS TABLE OF employees.last_name%TYPE;
    l_names t_names;
    l_sql   VARCHAR2(500);
BEGIN
    l_sql := 'SELECT last_name
              FROM employees
              WHERE department_id = :dept';

    EXECUTE IMMEDIATE l_sql
        BULK COLLECT INTO l_names
        USING 10;

    FOR i IN 1 .. l_names.COUNT LOOP
        DBMS_OUTPUT.PUT_LINE(l_names(i));
    END LOOP;
END;
/
~~~

Nếu tập dữ liệu rất lớn, cân nhắc cursor fetch theo batch thay vì đưa toàn bộ kết quả vào collection.

### 8.4. DDL động

NDS cũng có thể thực thi DDL:

~~~sql
BEGIN
    EXECUTE IMMEDIATE 'CREATE TABLE lab_dynamic_demo (id NUMBER)';
END;
/
~~~

DDL thường không nhận bind variable để thay tên object hoặc các phần cú pháp. Tên object phải được xây dựng từ nguồn đã xác thực. Cần nhớ DDL của Oracle có implicit commit; chạy DDL động có thể làm thay đổi transaction boundary của session.

## 9. Khác biệt dấu kết thúc SQL và PL/SQL block động

Chuỗi SQL statement thường không chứa dấu chấm phẩy ở cuối:

~~~sql
l_sql := 'DELETE FROM employees WHERE employee_id = :id';
EXECUTE IMMEDIATE l_sql USING 101;
~~~

Chuỗi PL/SQL block phải chứa dấu chấm phẩy để kết thúc statement bên trong block và dấu chấm phẩy sau END:

~~~sql
l_block := 'BEGIN
                cleanup_api.remove_employee(:id);
            END;';

EXECUTE IMMEDIATE l_block USING 101;
~~~

Không thêm dấu gạch chéo của SQL*Plus/SQLcl vào cuối chuỗi block. Dấu gạch chéo là lệnh của client, không phải cú pháp bên trong block được gửi tới EXECUTE IMMEDIATE.

Một lỗi thường gặp là tạo chuỗi:

~~~sql
l_sql := 'UPDATE employees SET salary = salary + 100 WHERE employee_id = :id;';
~~~

Dấu chấm phẩy ở cuối SQL statement có thể gây lỗi cú pháp trong dynamic SQL. Với PL/SQL block, dấu chấm phẩy bên trong block là bắt buộc.

## 10. DBMS_SQL và bind tường minh theo tên

NDS phù hợp khi số lượng bind và kiểu kết quả đã biết lúc compile. Nếu số cột hoặc số bind chỉ xác định tại runtime, DBMS_SQL cung cấp API linh hoạt hơn.

DBMS_SQL cho phép:
- Mở cursor động.
- Parse câu SQL.
- Bind biến bằng tên placeholder.
- Mô tả cột của query khi chưa biết cấu trúc kết quả.
- Define/fetch các cột theo metadata runtime.
- Thực thi và đóng cursor.

### 10.1. Ví dụ bind theo tên với DBMS_SQL

~~~sql
DECLARE
    l_cursor   INTEGER;
    l_rows     INTEGER;
    l_sql      VARCHAR2(500);
BEGIN
    l_sql := 'UPDATE employees
              SET salary = salary + :increase
              WHERE employee_id = :employee_id';

    l_cursor := DBMS_SQL.OPEN_CURSOR;

    DBMS_SQL.PARSE(
        l_cursor,
        l_sql,
        DBMS_SQL.NATIVE
    );

    DBMS_SQL.BIND_VARIABLE(
        l_cursor,
        ':increase',
        500
    );

    DBMS_SQL.BIND_VARIABLE(
        l_cursor,
        ':employee_id',
        101
    );

    l_rows := DBMS_SQL.EXECUTE(l_cursor);

    DBMS_OUTPUT.PUT_LINE('Rows updated: ' || l_rows);

    DBMS_SQL.CLOSE_CURSOR(l_cursor);
EXCEPTION
    WHEN OTHERS THEN
        IF l_cursor IS NOT NULL AND DBMS_SQL.IS_OPEN(l_cursor) THEN
            DBMS_SQL.CLOSE_CURSOR(l_cursor);
        END IF;
        RAISE;
END;
/
~~~

Ở đây tên placeholder được chỉ định rõ trong lời gọi BIND_VARIABLE. Cách này khác với NDS USING clause, vốn không có cú pháp đặt tên argument theo kiểu p_name => value.

### 10.2. Khi nào nên chọn DBMS_SQL?

| Tình huống | Lựa chọn thường phù hợp |
|---|---|
| Câu SQL và số bind đã biết | EXECUTE IMMEDIATE |
| SELECT một hàng đã biết cấu trúc | EXECUTE IMMEDIATE ... INTO |
| Query nhiều hàng có cấu trúc biết trước | OPEN FOR hoặc BULK COLLECT |
| Dynamic PL/SQL block có parameter biết trước | EXECUTE IMMEDIATE ... USING |
| Số cột SELECT chỉ biết tại runtime | DBMS_SQL |
| Cần describe metadata của result set động | DBMS_SQL |
| Cần bind tường minh theo tên | DBMS_SQL.BIND_VARIABLE |

DBMS_SQL mạnh hơn nhưng verbose và phức tạp hơn. Không chọn nó chỉ vì muốn đặt tên placeholder trong một câu SQL đơn giản nếu NDS theo vị trí đã đáp ứng.

## 11. JDBC và bind parameter từ ứng dụng

Khi gọi Oracle từ Java, cách bind phụ thuộc API.

### 11.1. PreparedStatement dùng vị trí

JDBC PreparedStatement tiêu chuẩn dùng dấu hỏi và chỉ số bắt đầu từ 1:

~~~java
String sql = """
    UPDATE employees
       SET salary = salary + ?
     WHERE employee_id = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setBigDecimal(1, increase);
    ps.setLong(2, employeeId);

    int updated = ps.executeUpdate();
}
~~~

Mỗi dấu hỏi là một vị trí bind riêng. Nếu cùng một giá trị xuất hiện hai lần trong SQL, cần bind vào cả hai chỉ số.

### 11.2. CallableStatement gọi procedure

Ví dụ gọi procedure có IN và OUT parameter:

~~~java
String call = "{ call order_api.get_order_total(?, ?) }";

try (CallableStatement cs = connection.prepareCall(call)) {
    cs.setLong(1, orderId);
    cs.registerOutParameter(2, Types.NUMERIC);

    cs.execute();

    BigDecimal total = cs.getBigDecimal(2);
}
~~~

JDBC tiêu chuẩn dùng vị trí parameter trong ví dụ này. Một số driver hoặc framework có API named parameter riêng, nhưng không nên mặc định cú pháp đặt tên của framework giống quy tắc Native Dynamic SQL bên trong Oracle. Hãy phân biệt:
- Bind mapping của JDBC driver.
- Bind mapping của EXECUTE IMMEDIATE.
- Bind mapping của DBMS_SQL.

### 11.3. Gọi block PL/SQL động qua JDBC

~~~java
String block = """
    BEGIN
        order_api.approve_order(:p_order_id);
    END;
    """;

try (CallableStatement cs = connection.prepareCall(block)) {
    cs.setLong(1, orderId);
    cs.execute();
}
~~~

Từ phía JDBC, parameter thường được gán theo API driver và chỉ số bind. Khi block được Oracle nhận và parse, quy tắc placeholder bên trong NDS của PL/SQL là một chủ đề khác. Đừng suy luận rằng vì JDBC dùng chỉ số thì mọi dynamic block NDS bên trong cũng có quy tắc giống SQL statement.

## 12. Bind NULL và kiểu dữ liệu

Trong PL/SQL Native Dynamic SQL, không dùng literal NULL trực tiếp trong USING clause. Có thể khai báo biến chưa khởi tạo có kiểu phù hợp rồi bind biến đó.

~~~sql
DECLARE
    l_sql       VARCHAR2(500);
    l_status    VARCHAR2(20);
BEGIN
    -- l_status chưa được gán nên có giá trị NULL.
    l_sql := 'UPDATE employees
              SET commission_pct = :commission
              WHERE employee_id = :id';

    EXECUTE IMMEDIATE l_sql
        USING l_status, 101;
END;
/
~~~

Với ứng dụng JDBC, dùng setter phù hợp hoặc setNull với JDBC type tương ứng:

~~~java
ps.setNull(1, Types.NUMERIC);
~~~

Không nên chuyển mọi giá trị thành chuỗi rồi bind chuỗi nếu cột đích là DATE, NUMBER hoặc TIMESTAMP. Hãy truyền đúng datatype để tránh phụ thuộc NLS settings và implicit conversion.

### 12.1. DATE và TIMESTAMP

~~~sql
l_sql := 'SELECT COUNT(*)
          FROM orders
          WHERE order_date >= :from_date
            AND order_date < :to_date';

EXECUTE IMMEDIATE l_sql
    INTO l_count
    USING p_from_date, p_to_date;
~~~

Truyền biến DATE/TIMESTAMP có kiểu tương ứng. Tránh nối chuỗi ngày tháng vào SQL vì cách parse có thể phụ thuộc NLS_DATE_FORMAT hoặc định dạng session.

## 13. Bind variable không thay thế danh sách IN hoặc identifier

### 13.1. Một bind là một giá trị scalar

Câu sau không có nghĩa :ids đại diện cho nhiều giá trị:

~~~sql
SELECT *
FROM employees
WHERE employee_id IN (:ids);
~~~

Nếu bind :ids bằng chuỗi '10,20,30', Oracle coi đó là một giá trị chuỗi, không tự tách thành ba phần tử.

Nếu cần danh sách động, có thể:
- Dùng collection SQL/PLSQL phù hợp và TABLE() nếu kiểu collection được thiết kế để SQL truy vấn.
- Tạo đúng số placeholder scalar từ số lượng phần tử, rồi bind từng giá trị.
- Nạp danh sách vào global temporary table hoặc bảng staging rồi join.
- Dùng một API nhận collection theo kiểu được Oracle hỗ trợ.

Không nối trực tiếp chuỗi ID từ request vào mệnh đề IN.

### 13.2. Identifier cần whitelist

Nếu cần chọn bảng theo loại báo cáo, hãy ánh xạ đầu vào sang danh sách identifier cho phép:

~~~sql
DECLARE
    l_table_name VARCHAR2(30);
    l_sql        VARCHAR2(500);
    l_count      NUMBER;
BEGIN
    CASE UPPER(:requested_source)
        WHEN 'ORDERS' THEN
            l_table_name := 'ORDERS';
        WHEN 'CUSTOMERS' THEN
            l_table_name := 'CUSTOMERS';
        ELSE
            RAISE_APPLICATION_ERROR(-20060, 'Unsupported source');
    END CASE;

    l_sql := 'SELECT COUNT(*) FROM ' || l_table_name;

    EXECUTE IMMEDIATE l_sql INTO l_count;
END;
/
~~~

Ví dụ trên minh họa whitelist; trong PL/SQL thực tế, biến đầu vào cần được khai báo và gán từ tham số procedure hoặc context phù hợp. Nếu identifier có schema/quote đặc biệt, dùng quy tắc chuẩn hóa và xác thực thích hợp.

### 13.3. DBMS_ASSERT hỗ trợ xác thực identifier

DBMS_ASSERT có các hàm xác thực hoặc quote identifier như SIMPLE_SQL_NAME, SQL_OBJECT_NAME và ENQUOTE_NAME. Chúng hữu ích khi xây dựng SQL động, nhưng không thay thế kiểm tra quyền nghiệp vụ. Một identifier hợp lệ về cú pháp vẫn có thể trỏ tới object mà caller không được phép thao tác.

## 14. SQL injection và cách viết SQL động an toàn

SQL injection xảy ra khi dữ liệu không tin cậy bị ghép vào chuỗi SQL và được diễn giải thành cú pháp.

### 14.1. Ví dụ không an toàn

~~~sql
l_sql := 'SELECT employee_id
          FROM employees
          WHERE last_name = '''
          || p_last_name || '''';

EXECUTE IMMEDIATE l_sql INTO l_employee_id;
~~~

Nếu p_last_name chứa ký tự quote và một đoạn SQL, cấu trúc câu lệnh có thể bị thay đổi.

### 14.2. Dùng bind variable

~~~sql
l_sql := 'SELECT employee_id
          FROM employees
          WHERE last_name = :last_name';

EXECUTE IMMEDIATE l_sql
    INTO l_employee_id
    USING p_last_name;
~~~

Giá trị p_last_name được truyền riêng. Nội dung của nó không được parse như một phần cú pháp SQL.

### 14.3. Khi cần dynamic identifier

Không thể bind tên cột hoặc tên bảng như một giá trị. Giải pháp an toàn là:
1. Chỉ cho phép identifier nằm trong whitelist.
2. Xác thực identifier và schema/object theo ngữ cảnh.
3. Dùng DBMS_ASSERT khi phù hợp.
4. Bind mọi giá trị dữ liệu còn lại.
5. Cấp quyền database tối thiểu cho chương trình thực thi.

Không dùng thủ thuật tự thay quote để biến input tùy ý thành SQL an toàn. Escape thủ công rất dễ thiếu trường hợp và không thay thế bind.

## 15. Các lỗi bind thường gặp

| Lỗi/triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| ORA-01008: not all variables bound | Thiếu bind argument hoặc số occurrence không khớp trong SQL statement | Đếm từng placeholder occurrence và đối chiếu USING |
| ORA-01006: bind variable does not exist | Bind một tên không có trong câu lệnh hoặc block | Kiểm tra chuỗi SQL/block sau khi dựng |
| ORA-01036: illegal variable name/number | Tên hoặc số bind không hợp lệ, mismatch theo API | Kiểm tra placeholder và API bind đang dùng |
| Truyền đúng số giá trị nhưng cập nhật nhầm hàng | Thứ tự USING bị lệch so với SQL statement | Lập bảng vị trí placeholder trước khi bind |
| Dynamic block chỉ cần một bind nhưng truyền nhiều lần | Nhầm quy tắc occurrence của SQL với unique name của block | Đếm tên placeholder duy nhất trong block |
| Không bind được tên bảng/cột | Identifier không phải giá trị bind | Whitelist và xác thực identifier |
| IN chỉ trả một giá trị | Một bind scalar bị hiểu nhầm là danh sách | Dùng collection, placeholder list hoặc staging table |
| Lỗi cú pháp gần cuối chuỗi | Thêm semicolon không phù hợp trong dynamic SQL hoặc thiếu semicolon trong block | Phân biệt cú pháp SQL statement và PL/SQL block |
| Giá trị DATE/NUMBER không đúng | Chuyển sang chuỗi và phụ thuộc NLS | Bind đúng datatype |
| Query bị hard parse quá nhiều | Nối literal vào SQL tạo nhiều text khác nhau | Bind các giá trị thay đổi |
| Bind NULL không chạy | Dùng literal NULL trực tiếp trong USING | Dùng biến chưa khởi tạo có kiểu phù hợp |
| Function/procedure không nhận OUT | Dùng mode IN mặc định cho output | Khai báo OUT hoặc IN OUT trong USING |

## 16. Quy trình xây dựng dynamic SQL có kiểm soát

Khi cần tạo câu lệnh tại runtime, có thể làm theo trình tự:

1. Xác định nội dung là SQL statement hay PL/SQL block.
2. Xác định phần nào thay đổi: giá trị dữ liệu, identifier hay cấu trúc câu lệnh.
3. Giữ cấu trúc cố định nếu chỉ có giá trị thay đổi; dùng bind variable.
4. Nếu identifier phải thay đổi, ánh xạ qua whitelist và xác thực.
5. Đếm placeholder occurrence nếu là SQL statement.
6. Đếm placeholder name duy nhất nếu là PL/SQL block hoặc CALL.
7. Đặt bind arguments theo đúng quy tắc của API đang dùng.
8. Chọn INTO, BULK COLLECT, OPEN FOR hoặc OUT/IN OUT phù hợp.
9. Xử lý cursor và exception, bảo đảm đóng tài nguyên.
10. Kiểm tra transaction boundary, đặc biệt khi dynamic statement là DDL.
11. Kiểm thử input NULL, ký tự quote, datatype biên, số lượng bind và identifier không hợp lệ.
12. Ghi log SQL_ID hoặc thông tin chẩn đoán cần thiết mà không ghi lộ dữ liệu nhạy cảm.

## 17. Ví dụ tổng hợp: một SQL và một block PL/SQL dùng cùng placeholder name

Giả sử cần tăng lương và ghi nhận hai lần xuất hiện của một giá trị trong logic.

### 17.1. Dynamic SQL statement

~~~sql
DECLARE
    l_sql VARCHAR2(1000);
BEGIN
    l_sql := 'UPDATE employees
              SET salary = salary + :delta
              WHERE employee_id = :employee_id
                 OR manager_id = :employee_id';

    EXECUTE IMMEDIATE l_sql
        USING 250, 101, 101;

    DBMS_OUTPUT.PUT_LINE('Rows affected: ' || SQL%ROWCOUNT);
END;
/
~~~

Có ba occurrence:
1. :delta
2. :employee_id trong điều kiện đầu
3. :employee_id trong điều kiện thứ hai

Vì đây là SQL statement, cần ba bind arguments.

### 17.2. Dynamic PL/SQL block

~~~sql
DECLARE
    l_block VARCHAR2(1000);
BEGIN
    l_block := 'BEGIN
                    payroll_api.audit_adjustment(
                        p_employee_id => :employee_id,
                        p_requested_by => :actor,
                        p_confirmed_for => :employee_id
                    );
                END;';

    EXECUTE IMMEDIATE l_block
        USING 101, 'APP_USER';
END;
/
~~~

Có hai tên placeholder duy nhất:
1. :employee_id
2. :actor

Dù :employee_id xuất hiện hai lần, block chỉ cần một bind argument cho tên này.

### 17.3. Nguyên tắc ghi nhớ

~~~text
NATIVE DYNAMIC SQL

SQL statement:
    :x, :x, :y, :x
    -> 4 occurrences
    -> 4 bind arguments theo vị trí

Anonymous PL/SQL block / CALL:
    :x, :x, :y, :x
    -> 2 tên duy nhất
    -> 2 bind arguments theo tên
       (theo thứ tự tên xuất hiện đầu tiên)

DBMS_SQL:
    BIND_VARIABLE(cursor, ':x', value)
    -> chỉ định tên bind tường minh
~~~

## 18. Bài thực hành có kiểm soát

Các bài thực hành dùng bảng EMPLOYEES của schema mẫu nếu có. Nếu không có quyền hoặc schema mẫu không được cài, hãy tạo bảng lab riêng trong schema DEV/TEST. Không chạy DML hoặc DDL mẫu trên dữ liệu nghiệp vụ production.

### Bài 1 — Bind theo vị trí trong SQL động

Tạo câu UPDATE có hai placeholder khác tên. Truyền hai giá trị theo thứ tự và xác nhận hàng được cập nhật đúng. Đổi thứ tự hai giá trị, quan sát kết quả hoặc lỗi.

### Bài 2 — Lặp placeholder trong SQL statement

Viết:

~~~sql
SELECT employee_id
FROM employees
WHERE department_id = :x
   OR manager_id = :x
~~~

Chạy với hai bind argument. Sau đó thử chỉ truyền một bind và ghi nhận lỗi. Giải thích vì sao cùng tên vẫn có hai occurrence.

### Bài 3 — Lặp placeholder trong PL/SQL block

Viết block:

~~~sql
BEGIN
    demo_api.compare_values(:x, :x, :y);
END;
~~~

Gọi bằng EXECUTE IMMEDIATE với hai bind argument. Thử đổi tên placeholder thứ hai từ :x sang :z và quan sát số lượng bind cần truyền.

### Bài 4 — IN và OUT

Tạo procedure có một tham số IN và một tham số OUT. Gọi procedure qua dynamic PL/SQL block, khai báo mode trong USING. Xác nhận giá trị OUT nhận được.

### Bài 5 — SELECT INTO và OPEN FOR

Viết một dynamic SELECT trả đúng một hàng và dùng INTO. Sau đó viết query trả nhiều hàng và dùng REF CURSOR với OPEN FOR. So sánh cách fetch và đóng cursor.

### Bài 6 — DBMS_SQL named binding

Dùng DBMS_SQL để parse một câu UPDATE có hai placeholder. Gọi BIND_VARIABLE bằng tên cho từng placeholder rồi execute. So sánh với EXECUTE IMMEDIATE theo vị trí.

### Bài 7 — SQL injection

Tạo một ví dụ nối chuỗi với input có dấu quote. Sau đó sửa thành bind variable. Giải thích vì sao bind không áp dụng cho tên bảng và cách whitelist identifier.

### Bài 8 — Bind NULL và datatype

Bind một biến NUMBER chưa khởi tạo vào điều kiện SQL. Sau đó thử DATE/TIMESTAMP. Xác nhận giá trị được truyền đúng kiểu và không phụ thuộc NLS string format.

### Thu dọn dữ liệu lab

Chỉ xóa đúng object được tạo cho bài thực hành trong schema DEV/TEST sau khi xác nhận không có người khác sử dụng. DDL trong Oracle có implicit commit; không chạy lệnh thu dọn trên object ngoài phạm vi lab.

## 19. Câu hỏi ôn tập

**Câu 1.** Bind variable là gì?

**Đáp án:** Placeholder nhận giá trị lúc thực thi, tách dữ liệu khỏi chuỗi cú pháp SQL/PLSQL.

**Câu 2.** Trong Native Dynamic SQL, SQL statement ghép bind theo quy tắc nào?

**Đáp án:** Theo vị trí của từng occurrence trong SQL statement, không theo tên placeholder.

**Câu 3.** Nếu :x xuất hiện hai lần trong dynamic UPDATE thì cần bao nhiêu bind arguments?

**Đáp án:** Hai bind arguments, một cho mỗi occurrence.

**Câu 4.** Trong dynamic anonymous PL/SQL block, :x xuất hiện hai lần thì cần bao nhiêu bind arguments?

**Đáp án:** Một bind argument cho tên placeholder duy nhất :x.

**Câu 5.** Nếu hai vị trí trong dynamic PL/SQL block cần hai giá trị khác nhau thì làm sao?

**Đáp án:** Dùng hai tên placeholder khác nhau và truyền hai bind argument tương ứng.

**Câu 6.** USING trong EXECUTE IMMEDIATE có cú pháp đặt tên argument như lời gọi procedure không?

**Đáp án:** Không. USING là danh sách bind argument; quy tắc ghép phụ thuộc SQL statement hay PL/SQL block.

**Câu 7.** INTO khác USING thế nào khi chạy dynamic SELECT?

**Đáp án:** INTO nhận cột kết quả; USING cung cấp giá trị đầu vào cho placeholder.

**Câu 8.** Khi nào dùng OPEN FOR?

**Đáp án:** Khi dynamic query trả nhiều hàng và cần fetch qua REF CURSOR.

**Câu 9.** Khi nào dùng DBMS_SQL thay vì NDS?

**Đáp án:** Khi số lượng/kiểu cột hoặc bind chỉ biết tại runtime, cần describe metadata hoặc cần bind tường minh theo tên.

**Câu 10.** Có thể bind tên bảng không?

**Đáp án:** Không. Bind variable đại diện giá trị; identifier cần whitelist và xác thực riêng.

**Câu 11.** Vì sao không nên nối dữ liệu người dùng vào SQL động?

**Đáp án:** Có nguy cơ SQL injection, tạo nhiều SQL text và gây khó kiểm soát datatype/cursor reuse. Dùng bind cho giá trị.

**Câu 12.** JDBC PreparedStatement tiêu chuẩn bind theo cách nào?

**Đáp án:** Theo vị trí dấu hỏi, chỉ số bắt đầu từ 1. API named binding của framework/driver là cơ chế riêng và cần kiểm tra tài liệu tương ứng.

**Câu 13.** Dynamic PL/SQL block có tự commit không?

**Đáp án:** Không chỉ vì nó là block động. Transaction phụ thuộc các câu lệnh bên trong; DML vẫn theo transaction của session, còn COMMIT, ROLLBACK hoặc DDL bên trong có thể thay đổi transaction boundary.

**Câu 14.** Vì sao phải phân biệt semicolon trong dynamic SQL và dynamic PL/SQL block?

**Đáp án:** SQL statement động thường không có dấu chấm phẩy cuối chuỗi; block PL/SQL cần dấu chấm phẩy cho statement và END. Dấu gạch chéo của SQL*Plus không thuộc chuỗi block.

## Kết luận

Trong Oracle Native Dynamic SQL, cách ghép bind phụ thuộc loại nội dung được thực thi. Với **SQL statement**, Oracle ghép theo vị trí từng placeholder occurrence; placeholder cùng tên lặp lại vẫn cần bind argument riêng. Với **anonymous PL/SQL block hoặc CALL**, Oracle ghép theo tên placeholder duy nhất; một tên lặp nhiều lần chỉ cần một bind argument. USING arguments của block đi theo thứ tự xuất hiện đầu tiên của từng tên placeholder. DBMS_SQL cung cấp cách bind tường minh theo tên qua BIND_VARIABLE.

Bind variable chỉ đại diện giá trị dữ liệu, không thay thế identifier hoặc đoạn cú pháp. Khi cần tên bảng/cột động, hãy dùng whitelist và xác thực identifier; luôn bind các giá trị còn lại. Phân biệt rõ INTO/OPEN FOR với USING, mode IN/OUT/IN OUT, cú pháp kết thúc SQL và PL/SQL block, cũng như transaction boundary của DDL. Nếu số bind và cấu trúc kết quả đã biết, Native Dynamic SQL thường gọn; nếu metadata chỉ biết tại runtime, cân nhắc DBMS_SQL. Ở tầng Java, PreparedStatement tiêu chuẩn dùng bind theo vị trí, vì vậy cần hiểu đúng contract của từng API thay vì áp dụng lẫn lộn quy tắc.

## Tài liệu Oracle tham khảo

- [Oracle Database 19c PL/SQL Language Reference — Native Dynamic SQL](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/native-dynamic-sql.html): EXECUTE IMMEDIATE, OPEN FOR, USING và quy tắc bind placeholder.
- [Oracle Database 19c PL/SQL Language Reference — Dynamic SQL](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/dynamic-sql.html): lựa chọn Native Dynamic SQL và DBMS_SQL.
- [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_SQL](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_SQL.html): PARSE, BIND_VARIABLE, DESCRIBE_COLUMNS và EXECUTE.
- [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_ASSERT](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_ASSERT.html): xác thực tên object và identifier khi tạo SQL động.
- [Oracle Database 19c SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/index.html): cú pháp SQL, bind variable và DDL.

