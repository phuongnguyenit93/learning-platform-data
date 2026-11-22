# Tham số IN, OUT, IN OUT và giá trị mặc định

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** Thủ tục và package  
> **Mục tiêu:** Hiểu cách khai báo và truyền tham số cho procedure/function trong PL/SQL; phân biệt ba chế độ IN, OUT và IN OUT; sử dụng giá trị mặc định; gọi subprogram bằng positional notation và named notation; chọn kiểu dữ liệu tham số phù hợp bằng %TYPE/%ROWTYPE; xử lý kết quả, NULL, exception và NOCOPY an toàn.

## 1. Tham số giúp subprogram nhận dữ liệu và trả kết quả

Procedure và function thường cần làm việc với dữ liệu thay đổi theo từng lần gọi. Tham số (parameter) là giao diện để caller truyền đầu vào cho subprogram hoặc nhận kết quả từ nó.

Ví dụ một procedure tính giá sau giảm giá có thể nhận:

- Giá gốc.
- Tỷ lệ giảm giá.
- Giá cuối cùng cần trả về.

~~~sql
CREATE OR REPLACE PROCEDURE calculate_price (
    p_original_price IN NUMBER,
    p_discount_rate  IN NUMBER,
    p_final_price    OUT NUMBER
) IS
BEGIN
    p_final_price :=
        p_original_price * (1 - p_discount_rate);
END;
/
~~~

Gọi procedure:

~~~sql
DECLARE
    l_final_price NUMBER;
BEGIN
    calculate_price(
        1000,
        0.10,
        l_final_price
    );

    DBMS_OUTPUT.PUT_LINE('Final price = ' || l_final_price);
END;
/
~~~

Ở đây P_ORIGINAL_PRICE và P_DISCOUNT_RATE nhận dữ liệu đầu vào; P_FINAL_PRICE được procedure gán và trả lại cho caller.

Trong PL/SQL, mỗi formal parameter có một mode xác định cách dữ liệu đi qua ranh giới gọi:

- **IN:** nhận giá trị đầu vào để đọc.
- **OUT:** trả giá trị cho caller.
- **IN OUT:** nhận giá trị ban đầu, cho phép thay đổi và trả giá trị mới.

Nếu không ghi mode, Oracle mặc định là IN.

## 2. Formal parameter và actual parameter

Cần phân biệt hai khái niệm:

- **Formal parameter:** tên tham số được khai báo trong procedure/function.
- **Actual parameter (argument):** giá trị hoặc biến thực tế được truyền tại vị trí gọi.

Ví dụ:

~~~sql
CREATE OR REPLACE PROCEDURE greet_user (
    p_user_name IN VARCHAR2
) IS
BEGIN
    DBMS_OUTPUT.PUT_LINE('Hello ' || p_user_name);
END;
/
~~~

Khi gọi:

~~~sql
DECLARE
    l_name VARCHAR2(50) := 'Lan';
BEGIN
    greet_user(l_name);
END;
/
~~~

P_USER_NAME là formal parameter; L_NAME là actual parameter.

Actual parameter có thể là literal, hằng, biến hoặc biểu thức đối với tham số IN. Với OUT và IN OUT, actual parameter phải là một biến có thể nhận kết quả.

## 3. IN: tham số đầu vào

IN là mode mặc định. Subprogram nhận giá trị từ caller và được phép đọc giá trị đó. Formal parameter IN có tính chất chỉ đọc trong subprogram; không gán giá trị mới cho nó.

Cú pháp:

~~~sql
p_parameter_name IN datatype
~~~

Ví dụ:

~~~sql
CREATE OR REPLACE PROCEDURE show_employee (
    p_employee_id IN employees.employee_id%TYPE
) IS
    l_employee_name employees.employee_name%TYPE;
BEGIN
    SELECT employee_name
    INTO l_employee_name
    FROM employees
    WHERE employee_id = p_employee_id;

    DBMS_OUTPUT.PUT_LINE(l_employee_name);
END;
/
~~~

Gọi procedure:

~~~sql
BEGIN
    show_employee(100);
END;
/
~~~

### 3.1. IN là read-only

Không thể gán cho formal parameter IN:

~~~sql
CREATE OR REPLACE PROCEDURE invalid_example (
    p_amount IN NUMBER
) IS
BEGIN
    p_amount := 100; -- Không hợp lệ
END;
/
~~~

Nếu cần tính toán trên giá trị đầu vào, gán nó vào local variable:

~~~sql
CREATE OR REPLACE PROCEDURE calculate_tax (
    p_amount IN NUMBER
) IS
    l_tax NUMBER;
BEGIN
    l_tax := p_amount * 0.10;

    DBMS_OUTPUT.PUT_LINE('Tax = ' || l_tax);
END;
/
~~~

Cách này giữ nguyên ý nghĩa đầu vào và làm rõ đâu là dữ liệu nhận từ caller, đâu là kết quả tính toán nội bộ.

### 3.2. Actual parameter của IN có thể là biểu thức

Vì IN chỉ nhận đầu vào, caller có thể truyền literal hoặc biểu thức:

~~~sql
BEGIN
    calculate_tax(1000);
    calculate_tax(500 + 500);
END;
/
~~~

Cũng có thể truyền biến:

~~~sql
DECLARE
    l_amount NUMBER := 2500;
BEGIN
    calculate_tax(l_amount);
END;
/
~~~

Không dùng literal hoặc biểu thức cho OUT/IN OUT vì các mode đó cần nơi ghi kết quả.

## 4. OUT: tham số đầu ra

OUT dùng để subprogram trả kết quả về caller. Caller phải truyền một biến có thể được gán.

Cú pháp:

~~~sql
p_parameter_name OUT datatype
~~~

Ví dụ procedure trả tên nhân viên và mức lương:

~~~sql
CREATE OR REPLACE PROCEDURE get_employee_details (
    p_employee_id   IN  employees.employee_id%TYPE,
    p_employee_name OUT employees.employee_name%TYPE,
    p_salary        OUT employees.salary%TYPE
) IS
BEGIN
    SELECT employee_name, salary
    INTO p_employee_name, p_salary
    FROM employees
    WHERE employee_id = p_employee_id;
END;
/
~~~

Caller khai báo biến nhận:

~~~sql
DECLARE
    l_name employees.employee_name%TYPE;
    l_salary employees.salary%TYPE;
BEGIN
    get_employee_details(
        p_employee_id   => 100,
        p_employee_name => l_name,
        p_salary        => l_salary
    );

    DBMS_OUTPUT.PUT_LINE(l_name || ': ' || l_salary);
END;
/
~~~

### 4.1. OUT không dùng để đọc giá trị cũ của actual parameter

OUT được thiết kế để trả kết quả. Khi vào subprogram, không dựa vào giá trị caller đang có trong biến actual như một dữ liệu đầu vào. Hãy gán giá trị cho formal OUT trước khi dùng nó làm kết quả.

Ví dụ:

~~~sql
CREATE OR REPLACE PROCEDURE get_discount (
    p_customer_type IN  VARCHAR2,
    p_discount_rate OUT NUMBER
) IS
BEGIN
    IF p_customer_type = 'VIP' THEN
        p_discount_rate := 0.20;
    ELSE
        p_discount_rate := 0.05;
    END IF;
END;
/
~~~

Không viết logic kiểu “nếu p_discount_rate đã có giá trị từ trước thì cộng thêm...” vì OUT không mang ý nghĩa đọc-sửa giá trị actual đầu vào. Nếu cần nhận giá trị ban đầu và trả giá trị đã sửa, dùng IN OUT.

### 4.2. OUT phải được gán trên mọi đường đi thành công

Một procedure nên xác định rõ kết quả đầu ra trước khi kết thúc bình thường:

~~~sql
CREATE OR REPLACE PROCEDURE calculate_bonus (
    p_salary IN  NUMBER,
    p_bonus  OUT NUMBER
) IS
BEGIN
    IF p_salary IS NULL THEN
        p_bonus := 0;
    ELSIF p_salary >= 10000 THEN
        p_bonus := p_salary * 0.20;
    ELSE
        p_bonus := p_salary * 0.10;
    END IF;
END;
/
~~~

Nếu một nhánh bình thường kết thúc mà không gán OUT, caller có thể nhận giá trị không như mong đợi. Quy tắc tốt là gán mặc định trước, sau đó thay đổi theo nhánh:

~~~sql
BEGIN
    p_bonus := 0;

    IF p_salary >= 10000 THEN
        p_bonus := p_salary * 0.20;
    END IF;
END;
~~~

Đoạn thứ hai chỉ minh họa cách khởi tạo kết quả; procedure đầy đủ phải có phần khai báo và tham số tương ứng.

### 4.3. OUT với SELECT INTO

Một trường hợp thường dùng là trả dữ liệu truy vấn:

~~~sql
CREATE OR REPLACE PROCEDURE find_customer_name (
    p_customer_id   IN  customers.customer_id%TYPE,
    p_customer_name OUT customers.customer_name%TYPE
) IS
BEGIN
    SELECT customer_name
    INTO p_customer_name
    FROM customers
    WHERE customer_id = p_customer_id;
END;
/
~~~

SELECT INTO có thể phát sinh:

- NO_DATA_FOUND nếu không có hàng.
- TOO_MANY_ROWS nếu có nhiều hơn một hàng.

Nếu exception thoát khỏi subprogram, caller không nên dựa vào giá trị OUT như thể kết quả đã được trả bình thường. Hãy định nghĩa rõ hợp đồng lỗi: propagate exception, trả status, hoặc dùng kết quả nullable có quy ước riêng.

### 4.4. Trả status qua OUT

Có thể thiết kế procedure trả cả dữ liệu và trạng thái:

~~~sql
CREATE OR REPLACE PROCEDURE try_get_customer (
    p_customer_id   IN  customers.customer_id%TYPE,
    p_customer_name OUT customers.customer_name%TYPE,
    p_found         OUT VARCHAR2
) IS
BEGIN
    p_customer_name := NULL;
    p_found := 'N';

    BEGIN
        SELECT customer_name
        INTO p_customer_name
        FROM customers
        WHERE customer_id = p_customer_id;

        p_found := 'Y';
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            p_customer_name := NULL;
            p_found := 'N';
    END;
END;
/
~~~

Trong ví dụ này, NO_DATA_FOUND được xử lý bên trong và procedure kết thúc bình thường với status N. Nếu có lỗi khác, exception tiếp tục truyền lên caller.

Không dùng NULL làm status nếu NULL cũng có thể là giá trị dữ liệu hợp lệ hoặc trạng thái chưa xác định. Chọn miền status rõ ràng như Y/N, FOUND/NOT_FOUND hoặc mã kết quả đã quy định.

## 5. IN OUT: vừa nhận vừa trả giá trị

IN OUT cho phép subprogram nhận giá trị hiện tại của actual parameter, đọc hoặc thay đổi nó, rồi trả giá trị mới về caller.

Cú pháp:

~~~sql
p_parameter_name IN OUT datatype
~~~

Ví dụ tăng giá trị biến lên một tỷ lệ:

~~~sql
CREATE OR REPLACE PROCEDURE apply_increase (
    p_amount IN OUT NUMBER,
    p_rate   IN     NUMBER DEFAULT 0.10
) IS
BEGIN
    p_amount := p_amount * (1 + p_rate);
END;
/
~~~

Gọi:

~~~sql
DECLARE
    l_amount NUMBER := 1000;
BEGIN
    apply_increase(l_amount, 0.20);

    DBMS_OUTPUT.PUT_LINE('New amount = ' || l_amount);
END;
/
~~~

Ban đầu L_AMOUNT là 1000. Procedure nhận giá trị đó, tính thành 1200 và trả kết quả về chính biến L_AMOUNT.

### 5.1. IN OUT cần actual variable

Hợp lệ:

~~~sql
DECLARE
    l_counter NUMBER := 5;
BEGIN
    apply_increase(l_counter);
END;
/
~~~

Không hợp lệ:

~~~sql
BEGIN
    apply_increase(1000); -- Literal không thể nhận kết quả trả về
END;
/
~~~

IN OUT cần một biến để nhận giá trị sau khi subprogram hoàn thành.

### 5.2. Phân biệt IN và IN OUT

Nếu chỉ cần đọc đầu vào và trả kết quả riêng, dùng IN + OUT:

~~~sql
calculate_price(
    p_original_price => l_original,
    p_discount_rate  => l_rate,
    p_final_price    => l_final
);
~~~

Nếu cần thay đổi chính giá trị được truyền vào, dùng IN OUT:

~~~sql
apply_increase(l_amount, 0.10);
~~~

Không dùng IN OUT chỉ vì tiện. Mode nên diễn tả đúng hợp đồng của subprogram để caller hiểu biến nào được phép thay đổi.

## 6. So sánh ba mode

| Đặc điểm | IN | OUT | IN OUT |
|---|---|---|---|
| Nhận dữ liệu từ caller | Có | Không dùng giá trị cũ làm input | Có |
| Đọc formal parameter trong subprogram | Có | Chỉ đọc sau khi đã gán kết quả | Có |
| Gán formal parameter | Không | Có | Có |
| Trả kết quả cho caller | Không | Có | Có |
| Actual parameter cần là biến | Không bắt buộc | Có | Có |
| Cho phép giá trị mặc định | Có | Không | Không |
| Mục đích | Input | Output | Input được biến đổi thành output |

Một procedure có thể kết hợp nhiều mode:

~~~sql
CREATE OR REPLACE PROCEDURE calculate_invoice (
    p_subtotal IN     NUMBER,
    p_tax_rate IN     NUMBER DEFAULT 0.08,
    p_tax      OUT    NUMBER,
    p_total    OUT    NUMBER
) IS
BEGIN
    p_tax := NVL(p_subtotal, 0) * p_tax_rate;
    p_total := NVL(p_subtotal, 0) + p_tax;
END;
/
~~~

Khi gọi, caller cung cấp subtotal, có thể bỏ qua tax rate, và truyền hai biến nhận kết quả.

## 7. Giá trị mặc định cho tham số

Giá trị mặc định giúp caller không phải truyền mọi tham số trong mỗi lần gọi. Trong PL/SQL, default được khai báo cho tham số IN.

Cú pháp:

~~~sql
parameter_name IN datatype DEFAULT expression
~~~

Hoặc dùng toán tử gán:

~~~sql
parameter_name IN datatype := expression
~~~

Ví dụ:

~~~sql
CREATE OR REPLACE PROCEDURE create_ticket (
    p_title    IN VARCHAR2,
    p_priority IN VARCHAR2 DEFAULT 'NORMAL',
    p_source   IN VARCHAR2 DEFAULT 'WEB'
) IS
BEGIN
    INSERT INTO support_tickets (
        title,
        priority,
        source
    )
    VALUES (
        p_title,
        p_priority,
        p_source
    );
END;
/
~~~

Gọi đủ tham số:

~~~sql
BEGIN
    create_ticket('Cannot sign in', 'HIGH', 'MOBILE');
END;
/
~~~

Bỏ qua các tham số mặc định ở cuối:

~~~sql
BEGIN
    create_ticket('Question about invoice');
END;
/
~~~

Trong lần gọi thứ hai, P_PRIORITY nhận NORMAL và P_SOURCE nhận WEB.

### 7.1. Default chỉ được dùng khi tham số bị bỏ qua

Đây là khác biệt quan trọng:

~~~sql
BEGIN
    create_ticket('Cannot sign in');
END;
/
~~~

P_PRIORITY nhận giá trị mặc định NORMAL.

~~~sql
BEGIN
    create_ticket(
        p_title    => 'Cannot sign in',
        p_priority => NULL
    );
END;
/
~~~

P_PRIORITY nhận NULL vì caller đã truyền một giá trị tường minh. Oracle không tự thay NULL bằng default.

Nếu nghiệp vụ muốn NULL cũng có nghĩa dùng mặc định, procedure phải xử lý rõ:

~~~sql
IF p_priority IS NULL THEN
    l_priority := 'NORMAL';
ELSE
    l_priority := p_priority;
END IF;
~~~

Ở đây L_PRIORITY là local variable; formal IN P_PRIORITY vẫn chỉ đọc.

### 7.2. Chỉ IN có thể có default

Không khai báo default cho OUT hoặc IN OUT:

~~~sql
CREATE OR REPLACE PROCEDURE invalid_defaults (
    p_input  IN     NUMBER DEFAULT 0,
    p_result OUT    NUMBER DEFAULT 0
) IS
BEGIN
    NULL;
END;
/
~~~

Khai báo trên không hợp lệ vì OUT không hỗ trợ default parameter value. Tương tự, IN OUT không được khai báo default.

Nếu một subprogram có tham số OUT, caller vẫn phải cung cấp biến nhận kết quả.

### 7.3. Thứ tự tham số mặc định

Với positional notation, các tham số có default thường được đặt ở cuối để caller có thể bỏ qua chúng mà không làm thay đổi cách ánh xạ vị trí.

Ví dụ:

~~~sql
CREATE OR REPLACE PROCEDURE search_orders (
    p_customer_id IN NUMBER,
    p_status      IN VARCHAR2 DEFAULT 'OPEN',
    p_min_amount  IN NUMBER DEFAULT 0
) IS
BEGIN
    NULL;
END;
/
~~~

Có thể gọi:

~~~sql
BEGIN
    search_orders(100);
    search_orders(100, 'PAID');
    search_orders(100, 'PAID', 500);
END;
/
~~~

Nếu muốn bỏ qua P_STATUS nhưng vẫn truyền P_MIN_AMOUNT, positional notation không thuận tiện; dùng named notation.

### 7.4. Default expression

Default có thể là biểu thức tương thích với kiểu tham số, ví dụ:

~~~sql
CREATE OR REPLACE PROCEDURE register_event (
    p_event_name IN VARCHAR2,
    p_created_at IN TIMESTAMP DEFAULT SYSTIMESTAMP
) IS
BEGIN
    NULL;
END;
/
~~~

Khi caller bỏ qua P_CREATED_AT, giá trị mặc định được dùng. Khi caller truyền timestamp cụ thể, giá trị đó được dùng thay thế.

Default expression phải tương thích datatype và tuân theo giới hạn của PL/SQL. Không nhầm default của formal parameter với DEFAULT của cột trong CREATE TABLE; hai cơ chế có thời điểm và ngữ cảnh áp dụng khác nhau.

## 8. Positional notation: truyền theo vị trí

Với positional notation, actual arguments được ánh xạ theo thứ tự khai báo formal parameters.

Ví dụ:

~~~sql
CREATE OR REPLACE PROCEDURE register_customer (
    p_name   IN VARCHAR2,
    p_email  IN VARCHAR2,
    p_region IN VARCHAR2 DEFAULT 'VN'
) IS
BEGIN
    NULL;
END;
/
~~~

Gọi:

~~~sql
BEGIN
    register_customer('An', 'an@example.com', 'SG');
    register_customer('Binh', 'binh@example.com');
END;
/
~~~

Lần gọi đầu ánh xạ:

- P_NAME = An
- P_EMAIL = an@example.com
- P_REGION = SG

Lần gọi thứ hai chỉ truyền hai đối số nên P_REGION dùng default VN.

### 8.1. Ưu điểm và giới hạn

Positional notation ngắn gọn khi procedure có ít tham số và thứ tự dễ nhớ. Nhưng nếu nhiều tham số cùng datatype, người đọc khó phát hiện truyền nhầm vị trí.

Ví dụ:

~~~sql
calculate_transfer(
    100,
    200,
    500
);
~~~

Nếu cả ba đều NUMBER, rất khó nhận ra giá trị nào là source account, destination account hay amount chỉ bằng lời gọi.

## 9. Named notation: truyền theo tên

Named notation chỉ rõ formal parameter nào nhận actual argument nào:

~~~sql
BEGIN
    register_customer(
        p_name   => 'An',
        p_email  => 'an@example.com',
        p_region => 'VN'
    );
END;
/
~~~

Có thể đổi thứ tự các named arguments:

~~~sql
BEGIN
    register_customer(
        p_region => 'SG',
        p_email  => 'binh@example.com',
        p_name   => 'Binh'
    );
END;
/
~~~

Tên tham số giúp code dễ đọc và giảm nguy cơ truyền nhầm khi nhiều tham số có cùng kiểu dữ liệu.

### 9.1. Named notation giúp bỏ qua tham số mặc định ở giữa

Ví dụ:

~~~sql
CREATE OR REPLACE PROCEDURE create_report (
    p_report_name IN VARCHAR2,
    p_format      IN VARCHAR2 DEFAULT 'PDF',
    p_language    IN VARCHAR2 DEFAULT 'VI',
    p_owner       IN VARCHAR2 DEFAULT 'SYSTEM'
) IS
BEGIN
    NULL;
END;
/
~~~

Muốn dùng default cho FORMAT và LANGUAGE nhưng truyền OWNER:

~~~sql
BEGIN
    create_report(
        p_report_name => 'Monthly sales',
        p_owner       => 'FINANCE'
    );
END;
/
~~~

Oracle dùng default cho các tham số bị bỏ qua. Đây là lý do named notation hữu ích khi có nhiều tham số tùy chọn.

### 9.2. Không truyền positional sau named

Nếu đã bắt đầu dùng named notation, không tiếp tục truyền một actual positional phía sau.

Không hợp lệ:

~~~sql
BEGIN
    create_report(
        p_report_name => 'Monthly sales',
        'CSV'
    );
END;
/
~~~

Hãy đặt positional arguments trước, rồi mới đến named arguments; hoặc dùng named notation cho tất cả:

~~~sql
BEGIN
    create_report(
        p_report_name => 'Monthly sales',
        p_format      => 'CSV'
    );
END;
/
~~~

### 9.3. Dùng ký hiệu =>

Trong named notation, dấu => nối tên formal parameter với actual argument:

~~~sql
p_parameter_name => actual_value
~~~

Không nhầm => với toán tử gán :=. Dấu := dùng để gán giá trị cho biến trong PL/SQL; => dùng trong lời gọi để ánh xạ tham số theo tên.

## 10. Kết hợp positional và named notation

PL/SQL cho phép truyền các đối số theo vị trí trước, sau đó dùng named notation cho các đối số còn lại.

Ví dụ:

~~~sql
BEGIN
    create_report(
        'Monthly sales',
        p_owner => 'FINANCE'
    );
END;
/
~~~

P_REPORT_NAME được truyền positional. P_OWNER được truyền named. P_FORMAT và P_LANGUAGE bị bỏ qua nên dùng default.

Không được đặt positional argument sau named argument. Trong code production, dùng named notation cho lời gọi nhiều tham số thường dễ bảo trì hơn.

## 11. Dùng %TYPE và %ROWTYPE cho datatype tham số

Khi tham số có cùng kiểu với một cột bảng, dùng %TYPE để tránh khai báo kiểu dữ liệu thủ công:

~~~sql
CREATE OR REPLACE PROCEDURE update_employee_salary (
    p_employee_id IN employees.employee_id%TYPE,
    p_new_salary  IN employees.salary%TYPE
) IS
BEGIN
    UPDATE employees
    SET salary = p_new_salary
    WHERE employee_id = p_employee_id;
END;
/
~~~

Nếu datatype hoặc precision của cột thay đổi, khai báo tham chiếu %TYPE giúp tham số đồng bộ theo kiểu cột.

### 11.1. %ROWTYPE cho record

Có thể dùng %ROWTYPE khi cần truyền cả một hàng:

~~~sql
CREATE OR REPLACE PROCEDURE display_employee (
    p_employee IN employees%ROWTYPE
) IS
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        p_employee.employee_id || ': ' ||
        p_employee.employee_name
    );
END;
/
~~~

Caller tạo record tương thích:

~~~sql
DECLARE
    l_employee employees%ROWTYPE;
BEGIN
    SELECT *
    INTO l_employee
    FROM employees
    WHERE employee_id = 100;

    display_employee(l_employee);
END;
/
~~~

Parameter record hữu ích khi nhiều field luôn được truyền cùng nhau. Tuy nhiên, nó tạo phụ thuộc vào cấu trúc row; nếu procedure chỉ cần vài field, tham số riêng thường thể hiện hợp đồng rõ hơn.

### 11.2. Tham số collection hoặc object

PL/SQL cũng cho phép truyền collection, record, object và kiểu dữ liệu phức hợp phù hợp. Với collection lớn, mode OUT/IN OUT có thể cần cân nhắc NOCOPY để giảm chi phí sao chép; xem phần sau.

Datatype của actual và formal phải tương thích theo quy tắc PL/SQL. Implicit conversion có thể xảy ra ở một số trường hợp, nhưng không nên dựa vào chuyển đổi ngầm mơ hồ giữa chuỗi và số/ngày.

## 12. Giá trị NULL và giá trị mặc định

Default chỉ áp dụng khi caller bỏ qua tham số. NULL là một giá trị được truyền tường minh.

| Cách gọi | Kết quả cho tham số có default |
|---|---|
| Không truyền tham số | Dùng default |
| Truyền giá trị cụ thể | Dùng giá trị cụ thể |
| Truyền NULL | Giá trị tham số là NULL |
| Truyền biến đang NULL | Giá trị tham số là NULL |

Ví dụ:

~~~sql
CREATE OR REPLACE PROCEDURE set_priority (
    p_priority IN VARCHAR2 DEFAULT 'NORMAL'
) IS
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        'Priority = ' || NVL(p_priority, 'NULL')
    );
END;
/
~~~

Gọi:

~~~sql
BEGIN
    set_priority;          -- NORMAL
    set_priority('HIGH');  -- HIGH
    set_priority(NULL);    -- NULL
END;
/
~~~

Nếu muốn NULL được coi như default:

~~~sql
CREATE OR REPLACE PROCEDURE set_priority (
    p_priority IN VARCHAR2 DEFAULT 'NORMAL'
) IS
    l_priority VARCHAR2(20);
BEGIN
    l_priority := NVL(p_priority, 'NORMAL');

    DBMS_OUTPUT.PUT_LINE('Priority = ' || l_priority);
END;
/
~~~

Đây là quy tắc do procedure định nghĩa. Chỉ thêm NVL khi NULL thực sự có nghĩa giống giá trị mặc định trong nghiệp vụ.

## 13. OUT và IN OUT khi exception xảy ra

Tham số OUT/IN OUT là kênh trả kết quả. Nếu subprogram kết thúc bình thường, giá trị formal được chuyển về actual parameter theo semantics PL/SQL.

Nếu exception thoát khỏi subprogram, caller không nên dựa vào giá trị OUT/IN OUT như một kết quả hợp lệ. Hãy xử lý exception và định nghĩa rõ hợp đồng trả kết quả.

Ví dụ:

~~~sql
CREATE OR REPLACE PROCEDURE calculate_total (
    p_quantity IN  NUMBER,
    p_price    IN  NUMBER,
    p_total    OUT NUMBER
) IS
BEGIN
    p_total := NULL;

    IF p_quantity IS NULL OR p_price IS NULL THEN
        RAISE_APPLICATION_ERROR(-20001, 'Input is required');
    END IF;

    p_total := p_quantity * p_price;
END;
/
~~~

Caller nên xử lý lỗi:

~~~sql
DECLARE
    l_total NUMBER;
BEGIN
    calculate_total(2, 100, l_total);
    DBMS_OUTPUT.PUT_LINE(l_total);
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(SQLERRM);
        RAISE;
END;
/
~~~

Trong ví dụ, khi input không hợp lệ, procedure ném exception. Caller không được giả định L_TOTAL có giá trị kết quả mới. Nếu API cần trả cả trạng thái thất bại, có thể bắt lỗi đã dự kiến trong procedure và trả status OUT theo hợp đồng; lỗi bất ngờ vẫn nên được propagate.

Không bắt WHEN OTHERS rồi giả vờ thành công. Nếu bắt lỗi, phải có quyết định rõ ràng về rollback, trạng thái output và thông báo lỗi.

## 14. NOCOPY: gợi ý truyền tham chiếu

NOCOPY có thể được dùng với OUT hoặc IN OUT để gợi ý compiler truyền tham số theo tham chiếu thay vì sao chép dữ liệu. Nó có thể hữu ích cho record hoặc collection lớn.

Ví dụ:

~~~sql
CREATE OR REPLACE PROCEDURE normalize_names (
    p_names IN OUT NOCOPY name_list_type
) IS
BEGIN
    FOR i IN 1 .. p_names.COUNT LOOP
        p_names(i) := UPPER(TRIM(p_names(i)));
    END LOOP;
END;
/
~~~

NOCOPY là một **hint**, không phải bảo đảm Oracle luôn truyền theo tham chiếu. Compiler có thể bỏ qua trong một số trường hợp.

### 14.1. Rủi ro khi dùng NOCOPY

Với cách truyền theo tham chiếu, caller có thể quan sát một phần thay đổi của actual parameter ngay cả khi subprogram kết thúc bằng exception. Điều này khác với kỳ vọng copy-in/copy-out thông thường của một số chương trình.

Ví dụ, procedure thay đổi phần tử đầu tiên của collection rồi lỗi ở phần tử sau; caller có thể thấy một phần collection đã bị thay đổi nếu NOCOPY được áp dụng.

Vì vậy:

- Chỉ dùng NOCOPY khi có lý do hiệu năng đo được.
- Không dựa vào việc toàn bộ OUT/IN OUT sẽ chỉ được cập nhật khi subprogram thành công.
- Thiết kế xử lý lỗi sao cho caller biết dữ liệu có thể đã bị thay đổi một phần.
- Kiểm thử hành vi trên Oracle release/compiler thực tế.
- Tránh truyền cùng một biến actual cho nhiều tham số NOCOPY có thể gây aliasing và kết quả khó dự đoán.

Không thêm NOCOPY theo thói quen cho mọi tham số OUT/IN OUT.

## 15. Tham số trong package specification và package body

Khi procedure/function là thành phần public của package, khai báo trong package specification xác định giao diện mà caller nhìn thấy.

Ví dụ:

~~~sql
CREATE OR REPLACE PACKAGE employee_api AS
    PROCEDURE get_salary (
        p_employee_id IN employees.employee_id%TYPE,
        p_salary      OUT employees.salary%TYPE
    );

    PROCEDURE apply_bonus (
        p_employee_id IN employees.employee_id%TYPE,
        p_rate        IN NUMBER DEFAULT 0.10
    );
END employee_api;
/
~~~

Package body triển khai logic:

~~~sql
CREATE OR REPLACE PACKAGE BODY employee_api AS
    PROCEDURE get_salary (
        p_employee_id IN employees.employee_id%TYPE,
        p_salary      OUT employees.salary%TYPE
    ) IS
    BEGIN
        SELECT salary
        INTO p_salary
        FROM employees
        WHERE employee_id = p_employee_id;
    END get_salary;

    PROCEDURE apply_bonus (
        p_employee_id IN employees.employee_id%TYPE,
        p_rate        IN NUMBER
    ) IS
    BEGIN
        UPDATE employees
        SET salary = salary * (1 + p_rate)
        WHERE employee_id = p_employee_id;
    END apply_bonus;
END employee_api;
/
~~~

Default được công bố trong specification để caller có thể bỏ qua tham số. Khi định nghĩa body, cần giữ signature tương thích; không tự ý thay mode hoặc datatype so với specification.

Package specification là hợp đồng công khai. Thay đổi tên, thứ tự, mode hoặc default có thể ảnh hưởng source code caller và cần được triển khai có kiểm soát.

## 16. OUT parameter và function RETURN

Function có một giá trị trả về chính thức qua RETURN:

~~~sql
CREATE OR REPLACE FUNCTION calculate_area (
    p_width  IN NUMBER,
    p_height IN NUMBER
) RETURN NUMBER IS
BEGIN
    RETURN p_width * p_height;
END;
/
~~~

Gọi:

~~~sql
DECLARE
    l_area NUMBER;
BEGIN
    l_area := calculate_area(10, 20);
END;
/
~~~

Function cũng có thể có OUT/IN OUT parameter trong PL/SQL, nhưng không nên dùng nhiều kênh trả kết quả nếu một RETURN value đã đủ rõ ràng. Ngoài ra, function được gọi từ SQL phải tuân thủ các giới hạn của SQL-callable function; các tham số OUT/IN OUT không được dùng như tham số gọi từ SQL statement thông thường.

Chọn:

- Function RETURN khi kết quả chính là một giá trị.
- Procedure với OUT khi thao tác có nhiều kết quả hoặc là một hành động nghiệp vụ.
- IN OUT khi caller chủ ý đưa một giá trị vào để subprogram biến đổi và trả lại.

Đừng nhầm OUT parameter với mệnh đề DML RETURNING INTO:

~~~sql
UPDATE employees
SET salary = salary + 500
WHERE employee_id = 100
RETURNING salary INTO l_new_salary;
~~~

RETURNING INTO là cú pháp SQL DML để nhận giá trị từ hàng bị thay đổi; nó không phải mode OUT của formal parameter.

## 17. Ví dụ tổng hợp: procedure nhận input, default và trả output

Ví dụ tính phí giao hàng:

~~~sql
CREATE OR REPLACE PROCEDURE calculate_shipping (
    p_order_amount IN  NUMBER,
    p_customer_type IN VARCHAR2 DEFAULT 'REGULAR',
    p_shipping_fee OUT NUMBER,
    p_is_free      OUT VARCHAR2
) IS
BEGIN
    p_shipping_fee := 0;
    p_is_free := 'N';

    IF p_order_amount IS NULL OR p_order_amount < 0 THEN
        RAISE_APPLICATION_ERROR(-20010, 'Invalid order amount');
    ELSIF p_order_amount >= 1000 THEN
        p_shipping_fee := 0;
        p_is_free := 'Y';
    ELSIF p_customer_type = 'VIP' THEN
        p_shipping_fee := 10;
    ELSE
        p_shipping_fee := 25;
    END IF;
END;
/
~~~

Gọi positional:

~~~sql
DECLARE
    l_fee NUMBER;
    l_free VARCHAR2(1);
BEGIN
    calculate_shipping(800, 'VIP', l_fee, l_free);

    DBMS_OUTPUT.PUT_LINE(
        'Fee=' || l_fee || ', free=' || l_free
    );
END;
/
~~~

Gọi named và dùng default customer type:

~~~sql
DECLARE
    l_fee NUMBER;
    l_free VARCHAR2(1);
BEGIN
    calculate_shipping(
        p_order_amount => 500,
        p_shipping_fee => l_fee,
        p_is_free      => l_free
    );

    DBMS_OUTPUT.PUT_LINE(
        'Fee=' || l_fee || ', free=' || l_free
    );
END;
/
~~~

Ở lời gọi named, P_CUSTOMER_TYPE được bỏ qua nên nhận REGULAR. Hai tham số OUT luôn phải được cung cấp bằng biến nhận.

## 18. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Gán giá trị cho IN parameter | Lỗi biên dịch | Dùng local variable hoặc IN OUT |
| Truyền literal cho OUT | Không có nơi nhận kết quả | Truyền biến |
| Truyền biểu thức cho IN OUT | Actual không thể nhận giá trị mới | Dùng biến |
| Đọc OUT như dữ liệu đầu vào | Logic không đúng hợp đồng mode | Dùng IN OUT nếu cần đọc giá trị cũ |
| Không gán OUT trên đường thành công | Caller nhận kết quả không xác định theo logic ứng dụng | Khởi tạo và gán output rõ ràng |
| Khai báo default cho OUT/IN OUT | Khai báo không hợp lệ | Chỉ đặt default cho IN |
| Nghĩ truyền NULL sẽ dùng default | Tham số nhận NULL | Bỏ qua đối số hoặc xử lý NULL riêng |
| Bỏ qua tham số giữa positional | Ánh xạ sai vị trí hoặc không gọi được | Dùng named notation |
| Đặt positional sau named | Lỗi cú pháp lời gọi | Positional trước, named sau |
| Nhầm => với := | Viết sai lời gọi/gán | => ánh xạ named argument, := gán biến |
| Dùng datatype không đồng bộ với cột | Rủi ro conversion/precision | Dùng %TYPE |
| Dùng NOCOPY mà giả định atomic copy-out | Caller có thể thấy thay đổi một phần khi exception | Chỉ dùng khi hiểu rõ semantics |
| Thay signature package không đồng bộ | Caller không compile hoặc hành vi đổi | Cập nhật spec/body và kiểm thử consumer |
| Dùng OUT thay RETURN cho mọi function | API khó hiểu | Chọn kênh trả kết quả phù hợp |

## 19. Bài thực hành

Chạy các bài trong schema lab. Tạo bảng hoặc dùng bảng mẫu được phép; không cập nhật dữ liệu production khi chưa có phê duyệt.

### Bài 1 — IN parameter

Viết procedure nhận EMPLOYEE_ID IN, truy vấn tên nhân viên và in ra. Thử truyền literal, biến và biểu thức phù hợp.

### Bài 2 — OUT parameter

Viết procedure nhận EMPLOYEE_ID và trả SALARY qua OUT. Gọi từ anonymous block và in giá trị nhận được.

### Bài 3 — IN OUT

Viết procedure nhận một NUMBER IN OUT và tăng 10%. Gọi bằng biến; thử truyền literal và giải thích vì sao không hợp lệ.

### Bài 4 — So sánh IN, OUT, IN OUT

Tạo ba procedure nhỏ: procedure đầu chỉ đọc input; procedure thứ hai tạo output; procedure thứ ba biến đổi giá trị input. Viết lời gọi thể hiện khác biệt.

### Bài 5 — Default parameter

Khai báo P_STATUS IN DEFAULT 'NEW'. Thử bỏ qua, truyền 'PAID' và truyền NULL. Ghi lại ba kết quả.

### Bài 6 — Default ở giữa danh sách

Khai báo procedure có ba tham số IN, trong đó tham số thứ hai và thứ ba có default. Dùng named notation để bỏ qua tham số thứ hai nhưng truyền tham số thứ ba.

### Bài 7 — Positional và named notation

Gọi cùng procedure theo hai cách. Đổi thứ tự named arguments và xác nhận kết quả không đổi.

### Bài 8 — OUT với NO_DATA_FOUND

Viết procedure SELECT INTO một khách hàng. Thử ID tồn tại và không tồn tại; chọn propagate exception hoặc trả status OUT, rồi giải thích hợp đồng API.

### Bài 9 — %TYPE và %ROWTYPE

Dùng %TYPE cho ID/salary và %ROWTYPE cho record khách hàng. So sánh mức độ phụ thuộc vào schema.

### Bài 10 — Package specification

Khai báo procedure có default trong package specification và triển khai trong body. Gọi từ anonymous block bằng named notation.

### Bài 11 — NOCOPY

Tạo collection type và procedure IN OUT NOCOPY sửa vài phần tử rồi phát sinh exception có kiểm soát. Quan sát actual collection và thảo luận vì sao caller không nên giả định copy-out nguyên tử.

### Bài 12 — Thiết kế API

Thiết kế procedure chuyển tiền nhận source ID, destination ID, amount và trả status. Xác định mode từng tham số, default nào hợp lý, trường hợp NULL, exception và transaction ownership.

## 20. Checklist thiết kế tham số

- [ ] Xác định dữ liệu nào là input, output và input cần biến đổi.
- [ ] Dùng IN cho đầu vào chỉ đọc.
- [ ] Dùng OUT cho kết quả cần trả về caller.
- [ ] Dùng IN OUT khi cần nhận giá trị ban đầu và trả giá trị đã thay đổi.
- [ ] Chỉ khai báo default cho tham số IN.
- [ ] Hiểu rằng bỏ qua tham số mới dùng default; truyền NULL vẫn là NULL.
- [ ] Đặt tham số có default ở cuối nếu muốn gọi positional đơn giản.
- [ ] Dùng named notation khi bỏ qua tham số tùy chọn hoặc lời gọi có nhiều đối số cùng datatype.
- [ ] Không đặt positional argument sau named argument.
- [ ] Truyền biến cho OUT/IN OUT.
- [ ] Dùng %TYPE/%ROWTYPE khi cần đồng bộ với cấu trúc schema.
- [ ] Gán OUT trên mọi đường đi kết thúc bình thường.
- [ ] Định nghĩa rõ output khi không tìm thấy dữ liệu hoặc khi có lỗi.
- [ ] Không dựa vào OUT/IN OUT nếu exception thoát khỏi subprogram.
- [ ] Chỉ dùng NOCOPY khi hiểu rủi ro thay đổi một phần và có lợi ích đo được.
- [ ] Đồng bộ signature giữa package specification và body.
- [ ] Xác định rõ procedure nào chịu trách nhiệm COMMIT/ROLLBACK.
- [ ] Kiểm thử lời gọi positional, named, bỏ qua default, truyền NULL và exception.

## 21. Ghi nhớ cốt lõi

- IN nhận dữ liệu để đọc; OUT trả kết quả; IN OUT nhận giá trị ban đầu rồi trả giá trị đã biến đổi.
- Mode mặc định của formal parameter là IN.
- IN parameter không được gán trong subprogram; OUT/IN OUT cần actual parameter có thể ghi.
- OUT không dùng giá trị cũ của actual làm input; gán output rõ ràng trước khi kết thúc bình thường.
- IN OUT phù hợp khi logic cần đọc và thay đổi chính giá trị được caller truyền vào.
- Chỉ IN parameter có thể khai báo giá trị mặc định.
- Bỏ qua tham số có default sẽ dùng default; truyền NULL tường minh không kích hoạt default.
- Positional notation ánh xạ theo thứ tự khai báo; named notation ánh xạ bằng tên và giúp bỏ qua tham số tùy chọn.
- Khi kết hợp notation, positional arguments phải đứng trước named arguments.
- %TYPE và %ROWTYPE giúp datatype tham số/record bám theo schema.
- Exception thoát khỏi subprogram khiến caller không nên dựa vào kết quả OUT/IN OUT; thiết kế status/error contract rõ ràng.
- NOCOPY là hint có thể giảm sao chép dữ liệu lớn nhưng có thể làm caller thấy thay đổi một phần khi exception.
- Function dùng RETURN cho kết quả chính; procedure với OUT phù hợp khi cần nhiều kết quả hoặc hành động nghiệp vụ.
- Signature public trong package specification phải đồng bộ với package body và các caller.
- Chọn mode theo hợp đồng dữ liệu và quyền sở hữu transaction, không theo thói quen.

### Tài liệu Oracle nên đối chiếu

- [Oracle Database PL/SQL Language Reference](https://docs.oracle.com/en/database/) — Subprogram parameters, parameter modes, default values, positional/named notation và NOCOPY.
- [Oracle Database PL/SQL Language Fundamentals](https://docs.oracle.com/en/database/) — Datatypes, records, %TYPE, %ROWTYPE và parameter passing.
- [Oracle Database PL/SQL Packages and Types Reference](https://docs.oracle.com/en/database/) — Package specification/body và subprogram interface.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — SQL-callable functions và RETURNING INTO.
- [Oracle Database Error Messages](https://docs.oracle.com/en/database/) — Các lỗi liên quan compile, argument mapping và exception trong PL/SQL.

Chi tiết parameter passing, NOCOPY, datatype và giới hạn function gọi từ SQL có thể phụ thuộc Oracle release. Đối chiếu tài liệu đúng phiên bản, biên dịch ví dụ trong schema lab và kiểm thử cả lời gọi thành công, NULL, tham số mặc định lẫn exception.

