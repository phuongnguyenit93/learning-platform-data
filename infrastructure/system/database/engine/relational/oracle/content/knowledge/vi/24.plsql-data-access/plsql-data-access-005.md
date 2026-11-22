# Cursor FOR LOOP, cursor có tham số và phạm vi tài nguyên trong PL/SQL

PL/SQL cho phép xử lý tập kết quả của một câu truy vấn bằng cursor. Khi truy vấn trả về nhiều hàng, chương trình có thể cần đọc từng hàng để tính toán, kiểm tra điều kiện hoặc gọi thủ tục xử lý. Cursor FOR LOOP giúp thực hiện công việc đó với ít mã quản lý hơn: PL/SQL tự mở cursor, lấy từng hàng, gán hàng vào record vòng lặp và đóng cursor khi vòng lặp kết thúc.

Với **cursor có tham số** (*parameterized cursor*), cùng một định nghĩa truy vấn có thể được mở nhiều lần với giá trị đầu vào khác nhau. Cách này hữu ích khi xử lý từng phòng ban, khách hàng, đơn hàng hoặc nhóm dữ liệu mà không phải viết lại câu SELECT cho mỗi lần lặp.

Bài học thuộc chủ đề **PL/SQL và dữ liệu** của *Database Engine Relational Oracle*. Nội dung tập trung vào:

- Cursor FOR LOOP với truy vấn trực tiếp và explicit cursor.
- Cursor có tham số và cách truyền giá trị khi mở cursor.
- Vòng đời OPEN, FETCH, CLOSE và tự động quản lý tài nguyên.
- Phạm vi của cursor, loop record và nested loop.
- Cursor attributes như %FOUND, %NOTFOUND, %ROWCOUNT và %ISOPEN.
- Xử lý exception, cursor lồng nhau, hiệu năng và các lỗi thường gặp.
- Phân biệt cursor thường với REF CURSOR và cách chọn công cụ phù hợp.

## 1. Cursor là gì?

Cursor là tên gọi cho vùng ngữ cảnh mà Oracle sử dụng để xử lý một câu SQL và tập kết quả của nó. Trong PL/SQL, cursor giúp chương trình truy cập từng hàng của truy vấn theo thứ tự xử lý.

Có hai dạng thường gặp:

- **Implicit cursor:** Oracle tự quản lý cho các câu SQL như INSERT, UPDATE, DELETE và SELECT INTO.
- **Explicit cursor:** lập trình viên khai báo cursor để xử lý truy vấn trả về nhiều hàng, rồi điều khiển việc mở, lấy hàng và đóng cursor hoặc dùng cursor FOR LOOP.

Ví dụ truy vấn nhiều hàng:

~~~sql
SELECT employee_id, last_name, salary
FROM employees
WHERE department_id = 50
ORDER BY employee_id;
~~~

Một câu SELECT có thể trả về 0, 1 hoặc nhiều hàng. SELECT INTO trong PL/SQL phù hợp khi mong đợi đúng một hàng; nếu trả về không hàng, Oracle phát sinh NO_DATA_FOUND; nếu trả về nhiều hơn một hàng, phát sinh TOO_MANY_ROWS. Cursor phù hợp khi cần xử lý một tập kết quả gồm nhiều hàng.

## 2. Cursor FOR LOOP với truy vấn trực tiếp

Cách ngắn nhất để duyệt kết quả là dùng SELECT ngay trong FOR LOOP:

~~~sql
BEGIN
    FOR emp IN (
        SELECT employee_id, last_name, salary
        FROM employees
        WHERE department_id = 50
        ORDER BY employee_id
    )
    LOOP
        DBMS_OUTPUT.PUT_LINE(
            emp.employee_id || ' ' ||
            emp.last_name || ' ' ||
            emp.salary
        );
    END LOOP;
END;
/
~~~

PL/SQL tự thực hiện các bước cần thiết:

1. Mở cursor cho truy vấn.
2. Fetch từng hàng.
3. Đưa các cột của hàng hiện tại vào record loop variable `emp`.
4. Chạy phần thân vòng lặp.
5. Fetch hàng tiếp theo cho tới khi hết dữ liệu.
6. Đóng cursor khi vòng lặp kết thúc, kể cả khi thoát do exception hoặc điều khiển luồng rời vòng lặp.

Không cần khai báo biến record riêng cho `emp`, cũng không cần viết OPEN, FETCH hoặc CLOSE. `emp` là record ngầm định, chỉ có scope trong vòng FOR LOOP.

### Loop record

Mỗi cột trong select list trở thành một field của record:

~~~sql
FOR r_order IN (
    SELECT order_id, order_date, amount
    FROM orders
    WHERE customer_id = 100
)
LOOP
    DBMS_OUTPUT.PUT_LINE(
        r_order.order_id || ': ' || r_order.amount
    );
END LOOP;
~~~

Tên field lấy từ tên cột hoặc alias trong select list. Nếu hai biểu thức có cùng tên hoặc tên không rõ ràng, hãy đặt alias tường minh:

~~~sql
FOR r_total IN (
    SELECT customer_id,
           SUM(amount) AS total_amount
    FROM orders
    GROUP BY customer_id
)
LOOP
    DBMS_OUTPUT.PUT_LINE(r_total.total_amount);
END LOOP;
~~~

Loop record là read-only trong cursor FOR LOOP: không gán giá trị mới vào field của record vòng lặp. Nếu cần tính toán trung gian, khai báo biến riêng:

~~~sql
DECLARE
    l_tax NUMBER(12,2);
BEGIN
    FOR r_order IN (
        SELECT order_id, amount
        FROM orders
        WHERE status = 'PAID'
    )
    LOOP
        l_tax := r_order.amount * 0.08;
        DBMS_OUTPUT.PUT_LINE(r_order.order_id || ': ' || l_tax);
    END LOOP;
END;
/
~~~

### Trường hợp không có hàng

Nếu SELECT trong cursor FOR LOOP trả về 0 hàng, phần thân vòng lặp không chạy lần nào. Đây không phải lỗi NO_DATA_FOUND:

~~~sql
BEGIN
    FOR r_emp IN (
        SELECT employee_id
        FROM employees
        WHERE department_id = -1
    )
    LOOP
        DBMS_OUTPUT.PUT_LINE(r_emp.employee_id);
    END LOOP;

    DBMS_OUTPUT.PUT_LINE('Loop finished');
END;
/
~~~

Chương trình vẫn in `Loop finished`. Nếu nghiệp vụ cần thông báo không có hàng, có thể dùng biến đếm:

~~~sql
DECLARE
    l_count PLS_INTEGER := 0;
BEGIN
    FOR r_emp IN (
        SELECT employee_id
        FROM employees
        WHERE department_id = -1
    )
    LOOP
        l_count := l_count + 1;
        DBMS_OUTPUT.PUT_LINE(r_emp.employee_id);
    END LOOP;

    IF l_count = 0 THEN
        DBMS_OUTPUT.PUT_LINE('No employees found');
    END IF;
END;
/
~~~

## 3. Explicit cursor và cursor FOR LOOP

Explicit cursor được khai báo trong phần DECLARE của block hoặc trong specification/body của chương trình con. Nó có tên và có thể được mở bằng OPEN, đọc bằng FETCH và đóng bằng CLOSE.

Cú pháp:

~~~sql
CURSOR cursor_name IS
    select_statement;
~~~

Ví dụ:

~~~sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id, last_name, salary
        FROM employees
        WHERE department_id = 50
        ORDER BY employee_id;
BEGIN
    FOR emp IN c_employees
    LOOP
        DBMS_OUTPUT.PUT_LINE(
            emp.employee_id || ' ' || emp.last_name
        );
    END LOOP;
END;
/
~~~

Cursor FOR LOOP có thể dùng tên explicit cursor đã khai báo. Dù cursor có tên, PL/SQL vẫn tự OPEN, FETCH và CLOSE trong vòng lặp này.

### Khi nào dùng truy vấn trực tiếp, khi nào khai báo cursor?

| Cách viết | Phù hợp khi |
| --- | --- |
| FOR r IN (SELECT ...) | Truy vấn chỉ dùng tại một vị trí, muốn mã gọn và rõ. |
| CURSOR c IS SELECT ...; FOR r IN c | Muốn đặt tên truy vấn, tái sử dụng định nghĩa trong block hoặc thêm tham số. |
| OPEN/FETCH/CLOSE thủ công | Cần kiểm soát vòng đời cursor, fetch theo từng bước hoặc tích hợp logic đặc biệt. |
| REF CURSOR | Cần truyền tập kết quả qua tham số hoặc trả result set từ chương trình con. |

Cursor FOR LOOP thường là lựa chọn dễ đọc nhất khi chỉ cần xử lý tuần tự các hàng và không cần tự điều khiển việc fetch.

## 4. Cursor có tham số

Cursor có tham số là explicit cursor nhận giá trị đầu vào khi được mở. Tham số được dùng trong câu SELECT của cursor giống như biến đầu vào của một truy vấn có thể tái sử dụng.

Cú pháp:

~~~sql
CURSOR cursor_name (
    parameter_name [IN] datatype
    [, parameter_name [IN] datatype ...]
) IS
    select_statement;
~~~

Ví dụ cursor lọc nhân viên theo phòng ban:

~~~sql
DECLARE
    CURSOR c_employees (p_department_id NUMBER) IS
        SELECT employee_id, last_name, salary
        FROM employees
        WHERE department_id = p_department_id
        ORDER BY employee_id;
BEGIN
    FOR emp IN c_employees(50)
    LOOP
        DBMS_OUTPUT.PUT_LINE(
            emp.employee_id || ' ' ||
            emp.last_name || ' ' ||
            emp.salary
        );
    END LOOP;
END;
/
~~~

Mỗi lần cursor được mở, giá trị đối số được gán cho cursor parameter. Trong query, `p_department_id` tham chiếu tham số cursor, không phải cột của bảng EMPLOYEES.

### Truyền nhiều tham số

~~~sql
DECLARE
    CURSOR c_orders (
        p_customer_id NUMBER,
        p_min_amount  NUMBER
    ) IS
        SELECT order_id, order_date, amount
        FROM orders
        WHERE customer_id = p_customer_id
          AND amount >= p_min_amount
        ORDER BY order_date, order_id;
BEGIN
    FOR r_order IN c_orders(100, 500)
    LOOP
        DBMS_OUTPUT.PUT_LINE(
            r_order.order_id || ': ' || r_order.amount
        );
    END LOOP;
END;
/
~~~

Đối số có thể truyền theo vị trí:

~~~sql
FOR r_order IN c_orders(100, 500) LOOP
    NULL;
END LOOP;
~~~

Hoặc theo tên:

~~~sql
FOR r_order IN c_orders(
    p_min_amount => 500,
    p_customer_id => 100
)
LOOP
    NULL;
END LOOP;
~~~

Named notation giúp tránh nhầm thứ tự khi cursor có nhiều tham số hoặc nhiều tham số cùng kiểu dữ liệu.

### Mở cùng một cursor nhiều lần với giá trị khác nhau

~~~sql
DECLARE
    CURSOR c_employees (p_department_id NUMBER) IS
        SELECT employee_id, last_name
        FROM employees
        WHERE department_id = p_department_id;
BEGIN
    FOR emp IN c_employees(10)
    LOOP
        DBMS_OUTPUT.PUT_LINE('D10: ' || emp.last_name);
    END LOOP;

    FOR emp IN c_employees(20)
    LOOP
        DBMS_OUTPUT.PUT_LINE('D20: ' || emp.last_name);
    END LOOP;
END;
/
~~~

Mỗi cursor FOR LOOP mở cursor với tham số tương ứng, xử lý tập kết quả và đóng cursor sau khi hoàn tất. Cùng một định nghĩa query được dùng lại với hai tập dữ liệu khác nhau.

### Kiểu dữ liệu của cursor parameter

Nên khai báo kiểu tương thích với cột được so sánh. Có thể dùng anchored type:

~~~sql
DECLARE
    CURSOR c_employees (
        p_department_id employees.department_id%TYPE
    ) IS
        SELECT employee_id, last_name
        FROM employees
        WHERE department_id = p_department_id;
BEGIN
    FOR emp IN c_employees(50)
    LOOP
        DBMS_OUTPUT.PUT_LINE(emp.last_name);
    END LOOP;
END;
/
~~~

Cursor parameter mặc định là IN; nó nhận giá trị để truy vấn sử dụng. Cursor parameter không phải tham số OUT để trả dữ liệu về caller; kết quả được đọc qua các hàng cursor.

### Giá trị mặc định của tham số cursor

Tham số cursor có thể có biểu thức mặc định:

~~~sql
DECLARE
    CURSOR c_orders (
        p_status VARCHAR2 DEFAULT 'OPEN'
    ) IS
        SELECT order_id, amount
        FROM orders
        WHERE status = p_status;
BEGIN
    FOR r IN c_orders
    LOOP
        DBMS_OUTPUT.PUT_LINE(r.order_id);
    END LOOP;

    FOR r IN c_orders('PAID')
    LOOP
        DBMS_OUTPUT.PUT_LINE('Paid: ' || r.order_id);
    END LOOP;
END;
/
~~~

Lần gọi không truyền đối số dùng giá trị mặc định OPEN; lần gọi thứ hai dùng PAID. Khi thiết kế cursor có nhiều tham số mặc định, dùng named notation nếu muốn bỏ qua một số tham số đầu hoặc làm rõ ý nghĩa.

## 5. Cursor có tham số với OPEN/FETCH/CLOSE thủ công

Cursor có tham số cũng có thể được quản lý thủ công:

~~~sql
DECLARE
    CURSOR c_employees (p_department_id NUMBER) IS
        SELECT employee_id, last_name, salary
        FROM employees
        WHERE department_id = p_department_id
        ORDER BY employee_id;

    l_employee_id employees.employee_id%TYPE;
    l_last_name   employees.last_name%TYPE;
    l_salary      employees.salary%TYPE;
BEGIN
    OPEN c_employees(50);

    LOOP
        FETCH c_employees
        INTO l_employee_id, l_last_name, l_salary;

        EXIT WHEN c_employees%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(
            l_employee_id || ' ' || l_last_name || ' ' || l_salary
        );
    END LOOP;

    CLOSE c_employees;
END;
/
~~~

Trong cách viết này, lập trình viên chịu trách nhiệm:

1. OPEN cursor với đối số cần thiết.
2. FETCH từng hàng vào danh sách biến tương ứng.
3. Kiểm tra %NOTFOUND sau mỗi FETCH.
4. Dừng vòng lặp khi không còn hàng.
5. CLOSE cursor để giải phóng cursor state.

Thứ tự kiểm tra rất quan trọng. Nếu kiểm tra %NOTFOUND trước FETCH đầu tiên, giá trị thuộc tính chưa phản ánh kết quả lần fetch; luôn FETCH trước rồi kiểm tra.

### Dùng cursor%ROWTYPE để giảm lỗi lệch danh sách biến

Thay vì khai báo từng biến nhận cột, có thể khai báo record theo cursor:

~~~sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id, last_name, salary
        FROM employees
        WHERE department_id = 50;

    r_employee c_employees%ROWTYPE;
BEGIN
    OPEN c_employees;
    LOOP
        FETCH c_employees INTO r_employee;
        EXIT WHEN c_employees%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(
            r_employee.employee_id || ' ' || r_employee.last_name
        );
    END LOOP;
    CLOSE c_employees;
END;
/
~~~

Cursor%ROWTYPE tạo record có field tương ứng với select list của cursor. Nếu thay đổi select list, record cũng theo cấu trúc cursor sau khi chương trình được biên dịch lại.

## 6. Phạm vi tài nguyên và tự động đóng cursor

Một explicit cursor có hai khía cạnh cần phân biệt:

- **Scope của tên cursor:** nơi mã PL/SQL có thể tham chiếu tới cursor đã khai báo.
- **Trạng thái mở của cursor:** cursor đã được OPEN và chưa CLOSE hay chưa.

Cursor được khai báo trong phần DECLARE của block có thể được sử dụng trong phần thực thi và các block con. Khi block kết thúc, cursor local không còn thuộc phạm vi sử dụng của block đó. Nhưng trong quá trình chạy, một explicit cursor được OPEN thủ công phải được CLOSE đúng cách.

### Cursor FOR LOOP tự quản lý OPEN/FETCH/CLOSE

~~~sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id, last_name
        FROM employees
        WHERE department_id = 50;
BEGIN
    FOR emp IN c_employees
    LOOP
        DBMS_OUTPUT.PUT_LINE(emp.last_name);

        IF emp.employee_id = 100 THEN
            EXIT;
        END IF;
    END LOOP;

    -- Cursor c_employees đã được đóng tự động.
    IF c_employees%ISOPEN THEN
        DBMS_OUTPUT.PUT_LINE('Still open');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Closed');
    END IF;
END;
/
~~~

Khi vòng lặp kết thúc tự nhiên, gặp EXIT, hoặc bị rời do exception, PL/SQL tự đóng cursor đã mở cho vòng lặp. Không gọi CLOSE cho cursor do cursor FOR LOOP quản lý; việc đó là không cần thiết và có thể gây lỗi nếu cursor đã đóng.

### Manual cursor phải đóng trong cả nhánh thành công và lỗi

Nếu tự OPEN/FETCH/CLOSE, cần bảo đảm CLOSE kể cả khi xử lý một hàng phát sinh exception:

~~~sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id, last_name
        FROM employees
        WHERE department_id = 50;

    r_employee c_employees%ROWTYPE;
BEGIN
    OPEN c_employees;

    LOOP
        FETCH c_employees INTO r_employee;
        EXIT WHEN c_employees%NOTFOUND;

        -- Thay bằng xử lý nghiệp vụ thực tế.
        DBMS_OUTPUT.PUT_LINE(r_employee.last_name);
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

Handler kiểm tra %ISOPEN trước khi CLOSE để không cố đóng cursor chưa mở hoặc đã đóng. RAISE chuyển lỗi cho caller thay vì âm thầm bỏ qua. Nếu code có nhiều điểm RETURN/EXIT hoặc nhiều nhánh lỗi, hãy rà soát mọi đường đi để tránh cursor bị bỏ mở.

### OPEN thất bại

Nếu OPEN cursor phát sinh lỗi, trạng thái cursor có thể chưa mở. Trong exception handler, kiểm tra %ISOPEN trước khi CLOSE là cách an toàn:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        IF c_employees%ISOPEN THEN
            CLOSE c_employees;
        END IF;
        RAISE;
~~~

Không gọi FETCH hoặc đọc %FOUND/%NOTFOUND của cursor chưa mở. %ISOPEN là thuộc tính có thể dùng để kiểm tra trạng thái mở.

## 7. Cursor attributes

Explicit cursor có các thuộc tính giúp kiểm tra trạng thái và kết quả FETCH:

| Attribute | Ý nghĩa |
| --- | --- |
| %ISOPEN | TRUE nếu cursor đang mở; FALSE nếu đang đóng. |
| %FOUND | TRUE nếu FETCH gần nhất trả về một hàng; FALSE nếu không trả hàng. |
| %NOTFOUND | TRUE nếu FETCH gần nhất không trả hàng; FALSE nếu có hàng. |
| %ROWCOUNT | Số hàng đã FETCH từ cursor kể từ khi OPEN. |

Ví dụ:

~~~sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id, last_name
        FROM employees
        WHERE department_id = 50;

    r_employee c_employees%ROWTYPE;
BEGIN
    OPEN c_employees;

    DBMS_OUTPUT.PUT_LINE(
        'Open? ' || CASE WHEN c_employees%ISOPEN THEN 'YES' ELSE 'NO' END
    );

    LOOP
        FETCH c_employees INTO r_employee;
        EXIT WHEN c_employees%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(
            'Fetched ' || c_employees%ROWCOUNT ||
            ': ' || r_employee.last_name
        );
    END LOOP;

    DBMS_OUTPUT.PUT_LINE('Total fetched: ' || c_employees%ROWCOUNT);
    CLOSE c_employees;
END;
/
~~~

### Giá trị thuộc tính trước và sau FETCH

- Sau OPEN nhưng trước FETCH đầu tiên, %ROWCOUNT là 0; %FOUND và %NOTFOUND chưa có kết quả fetch nên là NULL.
- Sau FETCH thành công, %FOUND là TRUE, %NOTFOUND là FALSE và %ROWCOUNT tăng.
- Sau FETCH không còn hàng, %FOUND là FALSE, %NOTFOUND là TRUE; %ROWCOUNT không tăng thêm.
- Sau CLOSE, chỉ dùng %ISOPEN để kiểm tra trạng thái; các thuộc tính yêu cầu cursor đang mở sẽ gây INVALID_CURSOR nếu truy cập.

Vì vậy mẫu loop chuẩn là:

~~~sql
LOOP
    FETCH c_employees INTO r_employee;
    EXIT WHEN c_employees%NOTFOUND;

    -- Xử lý hàng vừa fetch.
END LOOP;
~~~

Không viết EXIT WHEN %NOTFOUND trước FETCH, vì chương trình phải lấy một hàng rồi mới biết lần fetch vừa rồi có thành công hay không.

### Implicit SQL cursor attributes

Các câu SQL DML dùng implicit cursor SQL. Có thể xem các thuộc tính như SQL%ROWCOUNT ngay sau statement:

~~~sql
BEGIN
    UPDATE employees
    SET salary = salary * 1.05
    WHERE department_id = 50;

    DBMS_OUTPUT.PUT_LINE(
        'Updated rows: ' || SQL%ROWCOUNT
    );
END;
/
~~~

SQL%ROWCOUNT là số hàng bị tác động bởi câu SQL gần nhất. Nếu chạy một câu SQL khác trước khi đọc thuộc tính, giá trị thuộc tính có thể đã thay đổi. SQL%ISOPEN luôn FALSE vì implicit cursor được Oracle đóng tự động sau statement; không dùng SQL%ISOPEN để kiểm soát explicit cursor.

## 8. Scope của cursor và loop record

Cursor khai báo trong block chỉ có thể được tham chiếu trong block đó và các block con. Một block bên ngoài không thể tham chiếu cursor chỉ được khai báo bên trong block con.

~~~sql
DECLARE
    CURSOR c_outer IS
        SELECT employee_id FROM employees;
BEGIN
    DECLARE
        CURSOR c_inner IS
            SELECT department_id FROM departments;
    BEGIN
        OPEN c_outer;
        CLOSE c_outer;

        OPEN c_inner;
        CLOSE c_inner;
    END;

    -- c_outer vẫn thuộc scope tại đây.
    -- c_inner không thuộc scope tại đây.
END;
/
~~~

Loop record được khai báo ngầm định cho vòng FOR và chỉ có scope trong vòng lặp:

~~~sql
BEGIN
    FOR emp IN (
        SELECT employee_id, last_name
        FROM employees
    )
    LOOP
        DBMS_OUTPUT.PUT_LINE(emp.last_name);
    END LOOP;

    -- emp không còn được nhìn thấy ở đây.
END;
/
~~~

Nếu cần giữ giá trị sau vòng lặp, sao chép field cần thiết vào biến khai báo ở block ngoài:

~~~sql
DECLARE
    l_last_employee_id employees.employee_id%TYPE;
BEGIN
    FOR emp IN (
        SELECT employee_id
        FROM employees
        ORDER BY employee_id
    )
    LOOP
        l_last_employee_id := emp.employee_id;
    END LOOP;

    DBMS_OUTPUT.PUT_LINE(l_last_employee_id);
END;
/
~~~

Nếu không có hàng, biến l_last_employee_id vẫn NULL vì không được gán trong vòng lặp.

## 9. Nested cursor FOR LOOP với cursor có tham số

Cursor có tham số đặc biệt hữu ích khi một vòng lặp ngoài xác định nhóm dữ liệu và vòng lặp trong lấy các hàng thuộc nhóm đó.

Ví dụ duyệt từng phòng ban rồi từng nhân viên của phòng ban:

~~~sql
DECLARE
    CURSOR c_departments IS
        SELECT department_id, department_name
        FROM departments
        ORDER BY department_id;

    CURSOR c_employees (
        p_department_id employees.department_id%TYPE
    ) IS
        SELECT employee_id, last_name, salary
        FROM employees
        WHERE department_id = p_department_id
        ORDER BY employee_id;
BEGIN
    FOR d IN c_departments
    LOOP
        DBMS_OUTPUT.PUT_LINE(
            'Department: ' || d.department_name
        );

        FOR e IN c_employees(d.department_id)
        LOOP
            DBMS_OUTPUT.PUT_LINE(
                '  ' || e.employee_id || ' ' ||
                e.last_name || ' ' || e.salary
            );
        END LOOP;
    END LOOP;
END;
/
~~~

Vòng ngoài mở cursor phòng ban. Với mỗi phòng ban, vòng trong mở cursor nhân viên bằng department_id của hàng hiện tại. Khi vòng trong kết thúc, cursor nhân viên được đóng; vòng ngoài tiếp tục tới phòng ban kế tiếp. Khi vòng ngoài kết thúc, cursor phòng ban cũng được đóng.

### Phạm vi của loop record trong nested loop

- `d` chỉ tồn tại trong vòng FOR của phòng ban.
- `e` chỉ tồn tại trong vòng FOR của nhân viên.
- Vòng trong có thể tham chiếu `d.department_id` vì `d` thuộc phạm vi bao quanh.
- Sau khi vòng tương ứng kết thúc, loop record không còn nhìn thấy được.

Không khai báo biến cùng tên với loop record ở phạm vi trong nếu không cần thiết; việc shadowing khiến tham chiếu khó đọc.

### Chú ý số lần thực thi query

Trong ví dụ trên, truy vấn cursor nhân viên được mở một lần cho mỗi phòng ban. Nếu có hàng nghìn phòng ban, điều đó có thể tạo nhiều lần thực thi truy vấn. Đây là mô hình nested cursor loop, không phải luôn là cách hiệu quả nhất.

Nếu mục tiêu chỉ là lấy phòng ban cùng nhân viên, một câu JOIN có thể đơn giản và hiệu quả hơn:

~~~sql
SELECT d.department_id,
       d.department_name,
       e.employee_id,
       e.last_name,
       e.salary
FROM departments d
LEFT JOIN employees e
  ON e.department_id = d.department_id
ORDER BY d.department_id, e.employee_id;
~~~

Chỉ dùng nested cursor khi mỗi nhóm thực sự cần logic xử lý riêng hoặc truy vấn phụ thuộc giá trị nhóm theo cách không dễ biểu diễn trong một câu SQL. Hãy cân nhắc số nhóm, chi phí parse/execute và kế hoạch thực thi.

## 10. Exception trong cursor FOR LOOP

Cursor FOR LOOP tự đóng cursor nếu exception làm luồng điều khiển rời khỏi vòng lặp. Tuy nhiên, exception không tự động rollback mọi thay đổi DML mà phần thân vòng lặp đã thực hiện.

Ví dụ:

~~~sql
BEGIN
    FOR emp IN (
        SELECT employee_id, salary
        FROM employees
        WHERE department_id = 50
    )
    LOOP
        DBMS_OUTPUT.PUT_LINE(emp.employee_id);

        IF emp.salary < 0 THEN
            RAISE_APPLICATION_ERROR(
                -20001,
                'Invalid salary'
            );
        END IF;
    END LOOP;
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(SQLERRM);
        RAISE;
END;
/
~~~

Khi exception thoát khỏi vòng lặp, cursor do vòng lặp quản lý được đóng tự động. Nếu có UPDATE/INSERT đã chạy trước khi exception xảy ra, các thay đổi đó vẫn thuộc transaction hiện tại và cần được caller COMMIT hoặc ROLLBACK theo nghiệp vụ.

### Exception handler ở block trong

Có thể đặt handler trong block thân vòng lặp để xử lý lỗi của từng hàng và tiếp tục hàng tiếp theo:

~~~sql
BEGIN
    FOR emp IN (
        SELECT employee_id, salary
        FROM employees
        WHERE department_id = 50
        ORDER BY employee_id
    )
    LOOP
        BEGIN
            IF emp.salary < 0 THEN
                RAISE_APPLICATION_ERROR(
                    -20001,
                    'Invalid salary for employee ' || emp.employee_id
                );
            END IF;

            DBMS_OUTPUT.PUT_LINE(
                'Processed employee ' || emp.employee_id
            );
        EXCEPTION
            WHEN OTHERS THEN
                DBMS_OUTPUT.PUT_LINE(
                    'Skipped employee ' || emp.employee_id ||
                    ': ' || SQLERRM
                );
        END;
    END LOOP;
END;
/
~~~

Handler bên trong xử lý lỗi của hàng hiện tại, sau đó vòng lặp có thể tiếp tục. Chỉ dùng cách này khi nghiệp vụ cho phép bỏ qua hàng lỗi; không nuốt lỗi nếu điều đó làm sai kết quả hoặc che giấu sự cố.

### DML trong loop và transaction boundary

Ví dụ:

~~~sql
BEGIN
    FOR emp IN (
        SELECT employee_id
        FROM employees
        WHERE department_id = 50
    )
    LOOP
        UPDATE employee_audit
        SET processed_flag = 'Y'
        WHERE employee_id = emp.employee_id;
    END LOOP;
END;
/
~~~

Cursor FOR LOOP không tự COMMIT sau mỗi hàng và cũng không tự ROLLBACK khi kết thúc. Tất cả DML vẫn thuộc transaction của session. Caller quyết định COMMIT/ROLLBACK; nếu cần xử lý từng batch có commit riêng, phải thiết kế ranh giới transaction tường minh.

## 11. Phân biệt cursor FOR LOOP với REF CURSOR

Explicit cursor tĩnh có câu SELECT được xác định trong mã PL/SQL. REF CURSOR là cursor variable có thể trỏ tới result set được mở bằng OPEN FOR; nó có thể được truyền qua tham số hoặc trả về cho caller.

Ví dụ dùng SYS_REFCURSOR:

~~~sql
CREATE OR REPLACE PROCEDURE open_employee_result (
    p_department_id IN NUMBER,
    p_result OUT SYS_REFCURSOR
) AS
BEGIN
    OPEN p_result FOR
        SELECT employee_id, last_name, salary
        FROM employees
        WHERE department_id = p_department_id
        ORDER BY employee_id;
END;
/
~~~

Caller nhận cursor variable và chịu trách nhiệm đọc/đóng theo API đang dùng. REF CURSOR phù hợp khi cần trả result set cho ứng dụng hoặc truyền kết quả giữa các chương trình con. Nó có vòng đời tài nguyên riêng; không nhầm với loop record tự động của một cursor FOR LOOP.

### Chọn loại cursor

| Nhu cầu | Cách phù hợp |
| --- | --- |
| Duyệt một truy vấn cục bộ trong PL/SQL | Cursor FOR LOOP với SELECT trực tiếp |
| Dùng lại truy vấn trong block, truyền điều kiện | Explicit cursor có tham số |
| Cần tự điều khiển từng lần FETCH | OPEN/FETCH/CLOSE |
| Trả result set cho client/caller | REF CURSOR hoặc SYS_REFCURSOR |
| Chỉ cần cập nhật/xóa theo một điều kiện SQL | DML set-based, không cần cursor |

## 12. Hiệu năng và lựa chọn xử lý theo tập hợp

Cursor FOR LOOP làm mã quản lý cursor gọn và an toàn hơn, nhưng không biến xử lý từng hàng thành cách nhanh hơn mọi câu SQL set-based.

### Ưu tiên một câu SQL nếu nghiệp vụ có thể diễn đạt theo tập hợp

Thay vì:

~~~sql
BEGIN
    FOR emp IN (
        SELECT employee_id
        FROM employees
        WHERE department_id = 50
    )
    LOOP
        UPDATE employees
        SET salary = salary * 1.05
        WHERE employee_id = emp.employee_id;
    END LOOP;
END;
/
~~~

Thường có thể dùng một câu:

~~~sql
UPDATE employees
SET salary = salary * 1.05
WHERE department_id = 50;
~~~

Một câu UPDATE set-based thường giảm số lần chuyển qua lại giữa engine PL/SQL và SQL, đồng thời cho optimizer cơ hội tối ưu toàn bộ thao tác.

### Khi nào cursor loop hợp lý?

- Mỗi hàng cần gọi logic PL/SQL riêng không dễ biểu diễn bằng SQL.
- Cần xử lý từng record và gọi API khác theo từng hàng.
- Tập dữ liệu nhỏ hoặc logic nghiệp vụ yêu cầu thứ tự xử lý cụ thể.
- Cần điều khiển lỗi theo từng hàng hoặc ghi nhận kết quả từng hàng.

Nếu xử lý hàng lớn, xem xét BULK COLLECT với LIMIT và FORALL để giảm context switching, nhưng phải quản lý kích thước batch và bộ nhớ.

### BULK COLLECT và FORALL

Ví dụ minh họa lấy dữ liệu theo batch:

~~~sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id
        FROM employees
        WHERE department_id = 50;

    TYPE t_employee_ids IS TABLE OF employees.employee_id%TYPE;
    l_employee_ids t_employee_ids;
BEGIN
    OPEN c_employees;
    LOOP
        FETCH c_employees
        BULK COLLECT INTO l_employee_ids
        LIMIT 500;

        EXIT WHEN l_employee_ids.COUNT = 0;

        FORALL i IN 1 .. l_employee_ids.COUNT
            UPDATE employee_audit
            SET processed_flag = 'Y'
            WHERE employee_id = l_employee_ids(i);
    END LOOP;
    CLOSE c_employees;
END;
/
~~~

LIMIT 500 là ví dụ; chọn theo kích thước hàng, PGA và workload. Với code production, cũng cần xử lý exception để bảo đảm cursor được đóng nếu lỗi xảy ra, hoặc dùng cấu trúc cursor FOR LOOP phù hợp. Nếu UPDATE có thể thực hiện set-based trực tiếp thì thường vẫn nên chọn cách đó.

## 13. Cursor FOR UPDATE và WHERE CURRENT OF

Cursor có thể khóa các hàng được chọn để chương trình xử lý rồi cập nhật đúng hàng hiện tại. Dùng mệnh đề FOR UPDATE trong cursor query và WHERE CURRENT OF trong DML:

~~~sql
DECLARE
    CURSOR c_orders IS
        SELECT order_id, status
        FROM orders
        WHERE status = 'PENDING'
        FOR UPDATE OF status;
BEGIN
    FOR r_order IN c_orders
    LOOP
        UPDATE orders
        SET status = 'PROCESSING'
        WHERE CURRENT OF c_orders;
    END LOOP;
END;
/
~~~

Cursor FOR LOOP tự mở cursor và đóng khi kết thúc; các row lock được giữ theo transaction cho tới COMMIT hoặc ROLLBACK. Đóng cursor không tự nhả row lock nếu transaction vẫn còn mở.

### NOWAIT, WAIT và SKIP LOCKED

Có thể điều khiển cách xử lý khi hàng đã bị session khác khóa:

~~~sql
CURSOR c_orders IS
    SELECT order_id, status
    FROM orders
    WHERE status = 'PENDING'
    FOR UPDATE SKIP LOCKED;
~~~

- NOWAIT: nếu hàng cần khóa đang bị session khác giữ, phát sinh lỗi thay vì chờ.
- WAIT n: chờ tối đa số giây chỉ định rồi có thể phát sinh lỗi timeout.
- SKIP LOCKED: bỏ qua các hàng hiện đang bị khóa và tiếp tục lấy hàng khác.

SKIP LOCKED hữu ích cho nhiều worker cùng xử lý queue, nhưng phải thiết kế sao cho hàng bị bỏ qua sẽ được worker khác xử lý sau. Không dùng nó nếu việc bỏ qua hàng làm mất tính đầy đủ của báo cáo hoặc nghiệp vụ.

### Giới hạn của FOR UPDATE

FOR UPDATE không áp dụng tùy tiện cho mọi query. Một số query có DISTINCT, GROUP BY, aggregate, set operator hoặc view phức tạp có thể không cho phép khóa hàng theo cách mong muốn. Hãy kiểm tra cú pháp và plan với query thực tế. Mệnh đề OF chỉ rõ cột/bảng liên quan đến khóa; nó không phải danh sách cột sẽ được cập nhật.

## 14. Phạm vi của cursor parameter và giá trị truyền vào

Cursor parameter được dùng trong câu SELECT của cursor và nhận giá trị khi cursor được mở. Mỗi lần OPEN có thể dùng giá trị khác nhau; cursor FOR LOOP thực hiện OPEN/CLOSE ngầm định cho từng lần chạy.

~~~sql
DECLARE
    l_department_id NUMBER := 10;

    CURSOR c_employees(p_department_id NUMBER) IS
        SELECT employee_id, last_name
        FROM employees
        WHERE department_id = p_department_id;
BEGIN
    FOR emp IN c_employees(l_department_id)
    LOOP
        DBMS_OUTPUT.PUT_LINE(emp.last_name);
    END LOOP;

    l_department_id := 20;

    FOR emp IN c_employees(l_department_id)
    LOOP
        DBMS_OUTPUT.PUT_LINE(emp.last_name);
    END LOOP;
END;
/
~~~

Hai lần gọi mở cursor với hai giá trị khác nhau. Giá trị tham số được dùng cho lần mở tương ứng; thay đổi biến PL/SQL sau vòng đầu không làm thay đổi tập kết quả đã xử lý.

### Cursor không tham số và cursor có tham số

Một explicit cursor không có tham số vẫn có thể tham chiếu biến trong scope tại nơi khai báo, nhưng điều đó tạo phụ thuộc ngầm vào trạng thái của block. Cursor có tham số thể hiện rõ đầu vào trong lời gọi, giúp dễ tái sử dụng và dễ hiểu hơn.

~~~sql
DECLARE
    l_department_id NUMBER := 10;

    CURSOR c_employees IS
        SELECT employee_id, last_name
        FROM employees
        WHERE department_id = l_department_id;
BEGIN
    FOR emp IN c_employees
    LOOP
        DBMS_OUTPUT.PUT_LINE(emp.last_name);
    END LOOP;
END;
/
~~~

Ví dụ này hợp lệ, nhưng query phụ thuộc vào biến ngoài. Khi cần mở cùng query cho nhiều department, parameterized cursor rõ ràng hơn:

~~~sql
CURSOR c_employees(p_department_id NUMBER) IS
    SELECT employee_id, last_name
    FROM employees
    WHERE department_id = p_department_id;
~~~

## 15. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| SELECT INTO phát sinh TOO_MANY_ROWS | Truy vấn trả nhiều hàng nhưng dùng dạng lấy một hàng | Dùng cursor FOR LOOP hoặc sửa điều kiện để đúng một hàng. |
| Cursor FOR LOOP không chạy | Query trả về 0 hàng | Kiểm tra predicate; dùng biến đếm nếu cần phát hiện tập rỗng. |
| Loop record không dùng được sau END LOOP | Record chỉ thuộc scope vòng lặp | Sao chép field cần giữ sang biến ở block ngoài. |
| Cursor đã mở nhưng không đóng | Dùng OPEN/FETCH/CLOSE thủ công và có nhánh lỗi thiếu CLOSE | Dùng cursor FOR LOOP hoặc exception handler kiểm tra %ISOPEN rồi CLOSE. |
| INVALID_CURSOR | FETCH/CLOSE hoặc đọc attribute khi cursor không ở trạng thái hợp lệ | Kiểm tra OPEN/CLOSE và dùng %ISOPEN trước khi thao tác. |
| FETCH INTO báo sai số lượng/kiểu | Danh sách biến nhận không khớp select list | Dùng cursor%ROWTYPE hoặc đồng bộ số lượng, thứ tự và kiểu biến. |
| Cursor parameter lọc sai | Truyền sai thứ tự đối số hoặc nhầm tên với cột | Dùng named notation và prefix p_ cho parameter. |
| %NOTFOUND được kiểm tra sai | Kiểm tra trước FETCH | FETCH trước rồi EXIT WHEN cursor%NOTFOUND. |
| DML trong loop không được rollback tự động | Cursor lifecycle và transaction lifecycle là hai việc riêng | Caller quyết định COMMIT/ROLLBACK. |
| Nested cursor chậm | Query trong loop trong chạy nhiều lần | Xem xét JOIN/set-based SQL hoặc batch processing. |
| Cursor loop xử lý dữ liệu lớn chậm | Xử lý row-by-row, context switching hoặc logic quá nhiều | Dùng set-based SQL, BULK COLLECT/FORALL khi phù hợp. |
| Row lock vẫn tồn tại sau CLOSE cursor | Transaction chưa kết thúc | COMMIT/ROLLBACK để nhả lock. |

## 16. Bài thực hành tổng hợp

Các ví dụ sử dụng bảng mẫu trong schema học tập có quyền CREATE TABLE và quota phù hợp. DDL có implicit commit trong Oracle; không chạy lệnh tạo/xóa bảng trên schema nghiệp vụ thật.

### Bước 1: tạo dữ liệu

~~~sql
CREATE TABLE lab_departments (
    department_id NUMBER PRIMARY KEY,
    department_name VARCHAR2(50) NOT NULL
);

CREATE TABLE lab_employees (
    employee_id NUMBER PRIMARY KEY,
    department_id NUMBER NOT NULL,
    employee_name VARCHAR2(80) NOT NULL,
    salary NUMBER(12,2) NOT NULL
);

INSERT INTO lab_departments VALUES (10, 'Sales');
INSERT INTO lab_departments VALUES (20, 'Engineering');
INSERT INTO lab_departments VALUES (30, 'Support');

INSERT INTO lab_employees VALUES (1, 10, 'Mai', 12000);
INSERT INTO lab_employees VALUES (2, 10, 'An', 13000);
INSERT INTO lab_employees VALUES (3, 20, 'Binh', 18000);
INSERT INTO lab_employees VALUES (4, 20, 'Lan', 19000);
INSERT INTO lab_employees VALUES (5, 30, 'Minh', 11000);
COMMIT;
~~~

### Bước 2: cursor FOR LOOP với SELECT trực tiếp

~~~sql
SET SERVEROUTPUT ON;

BEGIN
    FOR r_emp IN (
        SELECT employee_id, employee_name, salary
        FROM lab_employees
        WHERE department_id = 10
        ORDER BY employee_id
    )
    LOOP
        DBMS_OUTPUT.PUT_LINE(
            r_emp.employee_id || ' ' ||
            r_emp.employee_name || ' ' || r_emp.salary
        );
    END LOOP;
END;
/
~~~

Thử đổi department_id thành 999 và quan sát vòng lặp không chạy nhưng block vẫn kết thúc bình thường.

### Bước 3: explicit cursor có tham số

~~~sql
DECLARE
    CURSOR c_employees(p_department_id NUMBER) IS
        SELECT employee_id, employee_name, salary
        FROM lab_employees
        WHERE department_id = p_department_id
        ORDER BY employee_id;
BEGIN
    FOR r_emp IN c_employees(20)
    LOOP
        DBMS_OUTPUT.PUT_LINE(
            r_emp.employee_name || ': ' || r_emp.salary
        );
    END LOOP;
END;
/
~~~

Chạy lại với 10 và 30. Giải thích vì sao cùng cursor có thể dùng cho nhiều department.

### Bước 4: truyền tham số theo tên

~~~sql
DECLARE
    CURSOR c_employees(
        p_department_id NUMBER,
        p_min_salary NUMBER
    ) IS
        SELECT employee_id, employee_name, salary
        FROM lab_employees
        WHERE department_id = p_department_id
          AND salary >= p_min_salary;
BEGIN
    FOR r_emp IN c_employees(
        p_min_salary => 15000,
        p_department_id => 20
    )
    LOOP
        DBMS_OUTPUT.PUT_LINE(r_emp.employee_name);
    END LOOP;
END;
/
~~~

### Bước 5: dùng OPEN/FETCH/CLOSE và cursor attributes

~~~sql
DECLARE
    CURSOR c_employees(p_department_id NUMBER) IS
        SELECT employee_id, employee_name
        FROM lab_employees
        WHERE department_id = p_department_id
        ORDER BY employee_id;

    r_emp c_employees%ROWTYPE;
BEGIN
    OPEN c_employees(10);

    LOOP
        FETCH c_employees INTO r_emp;
        EXIT WHEN c_employees%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(
            c_employees%ROWCOUNT || ': ' || r_emp.employee_name
        );
    END LOOP;

    DBMS_OUTPUT.PUT_LINE(
        'Fetched rows = ' || c_employees%ROWCOUNT
    );
    CLOSE c_employees;
END;
/
~~~

### Bước 6: nested cursor FOR LOOP

~~~sql
DECLARE
    CURSOR c_departments IS
        SELECT department_id, department_name
        FROM lab_departments
        ORDER BY department_id;

    CURSOR c_employees(p_department_id NUMBER) IS
        SELECT employee_id, employee_name
        FROM lab_employees
        WHERE department_id = p_department_id
        ORDER BY employee_id;
BEGIN
    FOR d IN c_departments
    LOOP
        DBMS_OUTPUT.PUT_LINE(d.department_name);

        FOR e IN c_employees(d.department_id)
        LOOP
            DBMS_OUTPUT.PUT_LINE('  ' || e.employee_name);
        END LOOP;
    END LOOP;
END;
/
~~~

### Bước 7: quan sát exception và tự đóng cursor

~~~sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id, employee_name
        FROM lab_employees;

    r_emp c_employees%ROWTYPE;
BEGIN
    OPEN c_employees;
    FETCH c_employees INTO r_emp;

    RAISE_APPLICATION_ERROR(-20010, 'Test cleanup');

    CLOSE c_employees;
EXCEPTION
    WHEN OTHERS THEN
        IF c_employees%ISOPEN THEN
            CLOSE c_employees;
        END IF;
        DBMS_OUTPUT.PUT_LINE(SQLERRM);
END;
/
~~~

Quan sát handler đóng cursor trước khi block kết thúc. Trong cursor FOR LOOP, PL/SQL tự thực hiện phần cleanup tương ứng.

### Bước 8: dọn dữ liệu

~~~sql
DROP TABLE lab_employees PURGE;
DROP TABLE lab_departments PURGE;
~~~

Chỉ chạy khi đã hoàn thành lab và không cần giữ dữ liệu. DROP TABLE là DDL có implicit commit; PURGE bỏ qua Recycle Bin.

## 17. Câu hỏi tự kiểm tra

1. **Cursor dùng để làm gì?** Quản lý ngữ cảnh xử lý câu SQL và tập kết quả, cho phép đọc từng hàng.
2. **Cursor FOR LOOP tự thực hiện những bước nào?** OPEN, FETCH, lặp qua các hàng và CLOSE.
3. **SELECT trong cursor FOR LOOP trả 0 hàng có gây NO_DATA_FOUND không?** Không; thân vòng lặp không chạy lần nào.
4. **Loop record có scope ở đâu?** Chỉ trong vòng FOR tương ứng.
5. **Explicit cursor được khai báo ở đâu?** Trong phần khai báo của block/chương trình con hoặc package theo cấu trúc phù hợp.
6. **Cursor có tham số là gì?** Explicit cursor nhận giá trị đầu vào khi mở để lọc hoặc tính toán result set.
7. **Cursor parameter mặc định có mode gì?** IN.
8. **Có thể mở cùng cursor có tham số với giá trị khác nhau không?** Có; mỗi lần OPEN truyền đối số riêng.
9. **Named notation có ích gì?** Làm rõ đối số và tránh nhầm thứ tự.
10. **OPEN/FETCH/CLOSE thủ công cần chú ý điều gì?** Phải FETCH trước khi kiểm tra %NOTFOUND và bảo đảm CLOSE cả khi lỗi.
11. **%ROWCOUNT có ý nghĩa gì?** Số hàng đã fetch từ cursor kể từ khi mở.
12. **%ISOPEN dùng để làm gì?** Kiểm tra cursor đang mở hay đã đóng.
13. **Cursor FOR LOOP có tự COMMIT không?** Không; cursor cleanup không phải transaction cleanup.
14. **Đóng cursor có nhả row lock FOR UPDATE không?** Không nhất thiết; row lock được giữ tới COMMIT/ROLLBACK.
15. **Nested cursor loop có rủi ro hiệu năng nào?** Truy vấn trong lặp trong có thể chạy nhiều lần; JOIN/set-based có thể hiệu quả hơn.
16. **Khi nào dùng REF CURSOR?** Khi cần truyền/trả result set giữa chương trình con hoặc client.
17. **Khi nào nên dùng BULK COLLECT/FORALL?** Khi cần xử lý lượng lớn theo batch và không thể thay bằng một câu SQL set-based.
18. **Exception trong cursor FOR LOOP có tự rollback DML trước đó không?** Không; chỉ cursor được đóng tự động, transaction vẫn do caller quản lý.

Cursor FOR LOOP giúp xử lý tập kết quả gọn và an toàn vì PL/SQL tự quản lý OPEN, FETCH và CLOSE. Cursor có tham số giúp tái sử dụng truy vấn với đầu vào rõ ràng, đặc biệt trong nested loop theo nhóm. Khi cần tự kiểm soát fetch, phải quản lý trạng thái cursor và cleanup trong cả đường chạy lỗi. Luôn phân biệt vòng đời cursor với transaction, và ưu tiên SQL set-based hoặc bulk processing khi xử lý khối lượng lớn.
