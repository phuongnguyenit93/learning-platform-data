# CREATE PROCEDURE, CREATE FUNCTION và lựa chọn đơn vị chương trình trong Oracle

## 1. Từ anonymous block đến chương trình PL/SQL có tên

Một anonymous block giúp chạy một nhóm câu lệnh PL/SQL mà không cần tạo đối tượng lưu trong schema. Cách này thuận tiện khi thử nghiệm hoặc thực hiện một tác vụ một lần. Khi logic cần được gọi lại từ nhiều nơi, có giao diện tham số rõ ràng và cần quản lý quyền thực thi, Oracle cung cấp các **named PL/SQL units** như procedure, function và package.

Hai đơn vị chương trình độc lập thường dùng là:

- **Procedure:** thực hiện một hành động hoặc một quy trình. Có thể nhận tham số đầu vào và trả dữ liệu qua tham số `OUT` hoặc `IN OUT`; procedure không có biểu thức `RETURN` mang giá trị kết quả như function.
- **Function:** tính toán hoặc lấy một giá trị và trả về bằng `RETURN`. Function có thể được gọi trong biểu thức PL/SQL; nếu đáp ứng các quy tắc của SQL, function còn có thể được gọi trực tiếp trong câu SQL.

Ví dụ procedure:

```sql
CREATE OR REPLACE PROCEDURE say_hello (
    p_name IN VARCHAR2
) AS
BEGIN
    DBMS_OUTPUT.PUT_LINE('Hello, ' || p_name);
END say_hello;
/
```

Ví dụ function:

```sql
CREATE OR REPLACE FUNCTION calculate_tax (
    p_amount IN NUMBER
) RETURN NUMBER
AS
BEGIN
    RETURN p_amount * 0.10;
END calculate_tax;
/
```

Procedure được gọi để thực hiện hành động; function được gọi khi cần một giá trị trả về. Đây là nguyên tắc khởi đầu để lựa chọn đơn vị chương trình. Trong thực tế, package thường được dùng để nhóm các procedure/function có liên quan thành một API schema thống nhất.

Bài học thuộc chương **Thủ tục và package**, trình bày cú pháp `CREATE PROCEDURE`, `CREATE FUNCTION`, tham số, giá trị trả về, cách gọi, quyền, transaction, biên dịch và phụ thuộc schema; đồng thời so sánh anonymous block, procedure, function, package và trigger để chọn đúng đơn vị chương trình cho từng nhu cầu.

## 2. Stored procedure và stored function là gì?

Procedure và function là các chương trình PL/SQL được lưu trong Oracle Database dưới dạng schema objects. Sau khi tạo và biên dịch thành công, các chương trình có thể được gọi từ:

- Anonymous PL/SQL block.
- Procedure hoặc function khác.
- Package.
- Trigger.
- Ứng dụng client như Java/JDBC.
- Câu SQL đối với function đáp ứng điều kiện gọi từ SQL.

### 2.1. Vì sao lưu logic trong database?

Stored PL/SQL có thể hữu ích khi:

- Nhiều ứng dụng cùng dùng một quy tắc nghiệp vụ.
- Cần đóng gói nhiều câu DML thành một thao tác có giao diện ổn định.
- Cần giảm số lần round trip giữa ứng dụng và database.
- Muốn cấp quyền `EXECUTE` trên chương trình thay vì cấp trực tiếp quyền DML trên mọi bảng cho người dùng ứng dụng.
- Cần đặt logic gần dữ liệu để xử lý các thao tác cần phối hợp chặt chẽ.

Tuy nhiên, không phải mọi logic đều nên chuyển vào database. Logic giao diện, gọi dịch vụ ngoài, điều phối workflow dài hoặc xử lý không gắn chặt với dữ liệu có thể phù hợp hơn ở tầng ứng dụng. Hãy cân nhắc khả năng kiểm thử, triển khai, quản lý phiên bản và phụ thuộc Oracle.

### 2.2. Procedure/function là schema object

Khi chạy:

```sql
CREATE OR REPLACE PROCEDURE refresh_customer_status AS
BEGIN
    NULL;
END refresh_customer_status;
/
```

Oracle tạo hoặc thay thế procedure `REFRESH_CUSTOMER_STATUS` trong schema hiện tại. Procedure có tên, metadata, trạng thái biên dịch và quyền truy cập riêng.

Anonymous block không có đối tượng độc lập tương tự để người dùng khác gọi theo tên. Nếu một block cần được sử dụng lặp lại, có thể chuyển phần logic thành procedure/function.

## 3. CREATE PROCEDURE

### 3.1. Cú pháp tổng quát

```sql
CREATE [OR REPLACE] PROCEDURE procedure_name
    [(parameter [IN | OUT | IN OUT] datatype [DEFAULT expression], ...)]
    [AUTHID DEFINER | CURRENT_USER]
AS
    -- declarations
BEGIN
    -- executable statements
[EXCEPTION
    -- exception handlers
]
END [procedure_name];
/
```

Các phần:

- `CREATE PROCEDURE`: tạo stored procedure.
- `OR REPLACE`: thay định nghĩa hiện tại bằng định nghĩa mới nếu object cùng tên đã tồn tại và người dùng có quyền phù hợp.
- `procedure_name`: tên procedure trong schema.
- Parameter list: danh sách tham số tùy chọn.
- `AUTHID`: chọn quyền thực thi theo definer hoặc invoker.
- `AS` hoặc `IS`: bắt đầu phần khai báo và thân procedure.
- `BEGIN ... END`: phần thực thi bắt buộc.
- `EXCEPTION`: phần xử lý lỗi tùy chọn.

`AS` và `IS` có thể dùng thay nhau trong định nghĩa procedure/function thông thường.

### 3.2. Procedure không có tham số

```sql
CREATE OR REPLACE PROCEDURE show_server_time AS
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        TO_CHAR(SYSTIMESTAMP, 'YYYY-MM-DD HH24:MI:SS.FF TZH:TZM')
    );
END show_server_time;
/
```

Gọi procedure:

```sql
BEGIN
    show_server_time;
END;
/
```

Trong PL/SQL, có thể gọi procedure bằng tên và danh sách tham số. Dấu ngoặc rỗng không bắt buộc với procedure không có tham số.

### 3.3. Procedure có tham số đầu vào

```sql
CREATE OR REPLACE PROCEDURE print_employee (
    p_employee_id IN NUMBER
) AS
    v_name VARCHAR2(100);
BEGIN
    SELECT last_name
    INTO v_name
    FROM employees
    WHERE employee_id = p_employee_id;

    DBMS_OUTPUT.PUT_LINE(v_name);
END print_employee;
/
```

`p_employee_id` là dữ liệu caller truyền vào. Từ khóa `IN` là mode mặc định, nhưng nên ghi rõ để giao diện dễ đọc.

Gọi:

```sql
BEGIN
    print_employee(100);
END;
/
```

### 3.4. Procedure dùng %TYPE cho tham số

```sql
CREATE OR REPLACE PROCEDURE print_employee (
    p_employee_id IN employees.employee_id%TYPE
) AS
    v_name employees.last_name%TYPE;
BEGIN
    SELECT last_name
    INTO v_name
    FROM employees
    WHERE employee_id = p_employee_id;

    DBMS_OUTPUT.PUT_LINE(v_name);
END print_employee;
/
```

`%TYPE` giúp tham số và biến theo kiểu cột. Khi cấu trúc bảng thay đổi, stored unit có thể cần được biên dịch lại; Oracle theo dõi dependency và có thể đánh dấu unit INVALID nếu thay đổi ảnh hưởng đến chương trình.

## 4. Tham số IN, OUT và IN OUT

PL/SQL hỗ trợ ba parameter modes.

| Mode | Dữ liệu đi theo hướng | Ý nghĩa |
|---|---|---|
| `IN` | Caller → chương trình | Đầu vào; chương trình đọc giá trị |
| `OUT` | Chương trình → caller | Đầu ra; chương trình gán kết quả cho tham số |
| `IN OUT` | Caller ↔ chương trình | Nhận giá trị ban đầu, có thể thay đổi và trả lại |

### 4.1. IN parameter

```sql
CREATE OR REPLACE PROCEDURE calculate_discount (
    p_amount IN NUMBER,
    p_rate   IN NUMBER
) AS
    v_discount NUMBER;
BEGIN
    v_discount := p_amount * p_rate;
    DBMS_OUTPUT.PUT_LINE('Discount=' || v_discount);
END calculate_discount;
/
```

Trong procedure, không thể gán lại một tham số IN như một biến đầu ra thông thường. Nếu cần giá trị tính toán trả về caller, dùng OUT hoặc function.

### 4.2. OUT parameter

```sql
CREATE OR REPLACE PROCEDURE get_employee_salary (
    p_employee_id IN employees.employee_id%TYPE,
    p_salary      OUT employees.salary%TYPE
) AS
BEGIN
    SELECT salary
    INTO p_salary
    FROM employees
    WHERE employee_id = p_employee_id;
END get_employee_salary;
/
```

Caller nhận giá trị qua biến:

```sql
DECLARE
    v_salary employees.salary%TYPE;
BEGIN
    get_employee_salary(100, v_salary);
    DBMS_OUTPUT.PUT_LINE('Salary=' || v_salary);
END;
/
```

OUT parameter phù hợp khi procedure cần trả nhiều kết quả hoặc cần biểu đạt trạng thái qua nhiều tham số.

Nếu procedure phát sinh exception trước khi gán OUT parameter, caller không nên dựa vào giá trị đó như một kết quả hợp lệ. Hãy định nghĩa rõ hợp đồng lỗi và chỉ đọc OUT values khi lời gọi thành công.

### 4.3. IN OUT parameter

```sql
CREATE OR REPLACE PROCEDURE add_bonus (
    p_salary IN OUT NUMBER,
    p_bonus  IN NUMBER
) AS
BEGIN
    p_salary := p_salary + p_bonus;
END add_bonus;
/
```

Gọi:

```sql
DECLARE
    v_salary NUMBER := 30000;
BEGIN
    add_bonus(v_salary, 2500);
    DBMS_OUTPUT.PUT_LINE(v_salary); -- 32500
END;
/
```

`IN OUT` nhận giá trị ban đầu rồi trả giá trị đã thay đổi. Dùng mode này khi caller thực sự cần một biến được cập nhật; nếu chỉ trả kết quả mới, OUT hoặc function thường dễ hiểu hơn.

### 4.4. Tham số có giá trị mặc định

Tham số IN có thể khai báo default:

```sql
CREATE OR REPLACE PROCEDURE print_message (
    p_message IN VARCHAR2,
    p_prefix  IN VARCHAR2 DEFAULT 'INFO'
) AS
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        '[' || p_prefix || '] ' || p_message
    );
END print_message;
/
```

Gọi với giá trị mặc định:

```sql
BEGIN
    print_message('Database is ready');
END;
/
```

Gọi và truyền giá trị khác:

```sql
BEGIN
    print_message('Disk usage is high', 'WARNING');
END;
/
```

Khi dùng positional notation, không thể bỏ qua một tham số ở giữa rồi truyền tham số phía sau. Named notation cho phép bỏ qua tham số có default.

### 4.5. Positional notation

```sql
BEGIN
    print_message('Job completed', 'SUCCESS');
END;
/
```

Giá trị được gán theo thứ tự khai báo tham số.

### 4.6. Named notation

```sql
BEGIN
    print_message(
        p_prefix  => 'SUCCESS',
        p_message => 'Job completed'
    );
END;
/
```

Named notation làm lời gọi dễ đọc hơn và không phụ thuộc thứ tự tham số. Đặc biệt hữu ích khi procedure có nhiều tham số hoặc nhiều tham số có default.

### 4.7. Kết hợp positional và named notation

Có thể truyền một số tham số đầu bằng positional rồi tiếp tục bằng named notation:

```sql
BEGIN
    print_message(
        'Job completed',
        p_prefix => 'SUCCESS'
    );
END;
/
```

Không đặt tham số positional sau khi đã bắt đầu named notation trong cùng lời gọi.

### 4.8. Kiểu dữ liệu của tham số

Trong khai báo formal parameter, thường dùng kiểu dữ liệu không kèm độ dài hoặc precision constraint:

```sql
CREATE OR REPLACE PROCEDURE set_customer_name (
    p_customer_id IN customers.customer_id%TYPE,
    p_name        IN VARCHAR2
) AS
BEGIN
    UPDATE customers
    SET customer_name = p_name
    WHERE customer_id = p_customer_id;
END set_customer_name;
/
```

Nếu cần giới hạn độ dài hoặc định dạng, hãy xác định ở kiểu cột, constraint hoặc validate trong thân chương trình. Không khai báo `VARCHAR2(100)` trực tiếp như một formal parameter.

## 5. CREATE FUNCTION

### 5.1. Cú pháp tổng quát

```sql
CREATE [OR REPLACE] FUNCTION function_name
    [(parameter [IN | OUT | IN OUT] datatype [DEFAULT expression], ...)]
    RETURN return_datatype
    [AUTHID DEFINER | CURRENT_USER]
AS
    -- declarations
BEGIN
    -- executable statements
    RETURN expression;
[EXCEPTION
    -- exception handlers
]
END [function_name];
/
```

Function bắt buộc có mệnh đề `RETURN return_datatype` trong phần khai báo và phải trả về một giá trị tương thích bằng câu lệnh `RETURN expression`.

### 5.2. Function đơn giản

```sql
CREATE OR REPLACE FUNCTION calculate_tax (
    p_amount IN NUMBER
) RETURN NUMBER
AS
BEGIN
    RETURN p_amount * 0.10;
END calculate_tax;
/
```

Gọi trong PL/SQL:

```sql
DECLARE
    v_tax NUMBER;
BEGIN
    v_tax := calculate_tax(1000);
    DBMS_OUTPUT.PUT_LINE('Tax=' || v_tax);
END;
/
```

Function trả một giá trị NUMBER. Caller có thể dùng giá trị đó trong phép gán, biểu thức, điều kiện hoặc truyền làm đối số cho lời gọi khác.

### 5.3. Function có phần khai báo cục bộ

```sql
CREATE OR REPLACE FUNCTION calculate_net_amount (
    p_gross_amount IN NUMBER,
    p_tax_rate     IN NUMBER
) RETURN NUMBER
AS
    v_tax NUMBER;
    v_net NUMBER;
BEGIN
    v_tax := p_gross_amount * p_tax_rate;
    v_net := p_gross_amount - v_tax;

    RETURN v_net;
END calculate_net_amount;
/
```

Biến cục bộ được khai báo giữa `AS` và `BEGIN`. Function có thể có `EXCEPTION` section như procedure.

### 5.4. Mọi đường thực thi bình thường phải trả về giá trị

```sql
CREATE OR REPLACE FUNCTION classify_amount (
    p_amount IN NUMBER
) RETURN VARCHAR2
AS
BEGIN
    IF p_amount < 0 THEN
        RETURN 'INVALID';
    ELSIF p_amount = 0 THEN
        RETURN 'ZERO';
    ELSE
        RETURN 'POSITIVE';
    END IF;
END classify_amount;
/
```

Mỗi nhánh bình thường đều có RETURN. Nếu function đi đến cuối thân mà chưa trả giá trị, Oracle phát sinh lỗi runtime liên quan function đã kết thúc mà không trả về giá trị, thường là `ORA-06503`.

### 5.5. RETURN trong procedure và function khác nhau

Trong function:

```sql
RETURN expression;
```

trả giá trị và kết thúc function.

Trong procedure, có thể dùng:

```sql
RETURN;
```

để thoát sớm khỏi procedure, nhưng không có giá trị trả về trong câu lệnh RETURN. Procedure trả dữ liệu qua OUT/IN OUT parameters hoặc các cơ chế kết quả khác.

### 5.6. Function có thể phát sinh exception

```sql
CREATE OR REPLACE FUNCTION get_employee_salary (
    p_employee_id IN employees.employee_id%TYPE
) RETURN NUMBER
AS
    v_salary employees.salary%TYPE;
BEGIN
    SELECT salary
    INTO v_salary
    FROM employees
    WHERE employee_id = p_employee_id;

    RETURN v_salary;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE_APPLICATION_ERROR(
            -20010,
            'Employee does not exist'
        );
END get_employee_salary;
/
```

Nếu không tìm thấy nhân viên, function chuyển `NO_DATA_FOUND` thành lỗi nghiệp vụ có mã `-20010`. Nếu không bắt exception, lỗi gốc sẽ truyền ra caller.

Không nên trả 0 hoặc NULL cho mọi lỗi nếu caller cần phân biệt “không có nhân viên”, “lương chưa thiết lập” và “lỗi truy vấn”.

## 6. Khác biệt cốt lõi giữa procedure và function

| Tiêu chí | Procedure | Function |
|---|---|---|
| Mục đích chính | Thực hiện hành động/quy trình | Tính toán hoặc trả về một giá trị |
| Giá trị RETURN | Không có giá trị trả về bằng RETURN; có thể dùng `RETURN;` để thoát | Bắt buộc khai báo kiểu trả về và trả giá trị |
| Kết quả | OUT/IN OUT, DML, trạng thái hoặc cursor | Một giá trị theo kiểu khai báo |
| Gọi trong PL/SQL | Gọi như một statement | Gọi trong biểu thức hoặc statement phù hợp |
| Gọi trong SQL | Không gọi procedure trực tiếp trong SELECT | Có thể gọi function nếu đáp ứng SQL invocation rules |
| OUT parameters | Phù hợp | Có thể có trong PL/SQL, nhưng function gọi từ SQL không được dùng OUT/IN OUT |
| COMMIT/ROLLBACK | Có thể viết trong procedure, nhưng cần thiết kế transaction boundary | Không thể thực hiện transaction control trong function được gọi từ SQL; nói chung nên giữ function tính toán không có side effect |
| Ví dụ | Tạo đơn hàng, cập nhật trạng thái, gửi dữ liệu ra OUT | Tính thuế, chuẩn hóa giá trị, trả tổng tiền |

Quy tắc thực hành: nếu tên chương trình là một hành động như `CREATE_ORDER`, `CLOSE_ACCOUNT`, `PROCESS_PAYMENT`, thường bắt đầu bằng procedure. Nếu tên biểu đạt một giá trị như `CALCULATE_TAX`, `GET_ORDER_TOTAL`, thường bắt đầu bằng function.

## 7. Ví dụ hoàn chỉnh: procedure tạo đơn hàng

### 7.1. Tạo bảng minh họa

Ví dụ dùng identity column, cần Oracle Database 12c Release 1 trở lên:

```sql
CREATE TABLE demo_orders (
    order_id NUMBER GENERATED BY DEFAULT AS IDENTITY
        CONSTRAINT pk_demo_orders PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    amount NUMBER(12, 2) NOT NULL,
    status VARCHAR2(20) DEFAULT 'NEW' NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT ck_demo_orders_amount CHECK (amount >= 0)
);
```

### 7.2. Tạo procedure

```sql
CREATE OR REPLACE PROCEDURE create_demo_order (
    p_customer_id IN demo_orders.customer_id%TYPE,
    p_amount      IN demo_orders.amount%TYPE,
    p_order_id    OUT demo_orders.order_id%TYPE
) AS
BEGIN
    IF p_amount < 0 THEN
        RAISE_APPLICATION_ERROR(
            -20020,
            'Order amount cannot be negative'
        );
    END IF;

    INSERT INTO demo_orders (
        customer_id,
        amount,
        status
    )
    VALUES (
        p_customer_id,
        p_amount,
        'NEW'
    )
    RETURNING order_id INTO p_order_id;
END create_demo_order;
/
```

Procedure kiểm tra dữ liệu đầu vào, INSERT một hàng và trả khóa mới qua OUT parameter. Procedure không COMMIT; transaction vẫn thuộc caller.

### 7.3. Gọi procedure trong anonymous block

```sql
DECLARE
    v_order_id demo_orders.order_id%TYPE;
BEGIN
    create_demo_order(
        p_customer_id => 501,
        p_amount      => 250000,
        p_order_id    => v_order_id
    );

    DBMS_OUTPUT.PUT_LINE('Created order=' || v_order_id);
END;
/
```

Sau đó caller quyết định:

```sql
COMMIT;
```

Hoặc hủy thao tác:

```sql
ROLLBACK;
```

Không COMMIT tự động trong procedure giúp caller có thể kết hợp việc tạo đơn hàng với các thao tác nghiệp vụ khác trong cùng transaction.

## 8. Ví dụ hoàn chỉnh: function tính tổng đơn hàng

Function chỉ đọc dữ liệu và trả về một giá trị:

```sql
CREATE OR REPLACE FUNCTION get_customer_order_total (
    p_customer_id IN demo_orders.customer_id%TYPE
) RETURN NUMBER
AS
    v_total NUMBER;
BEGIN
    SELECT NVL(SUM(amount), 0)
    INTO v_total
    FROM demo_orders
    WHERE customer_id = p_customer_id
      AND status <> 'CANCELLED';

    RETURN v_total;
END get_customer_order_total;
/
```

`SUM` không có GROUP BY trả một hàng aggregate ngay cả khi không có đơn phù hợp; `NVL` chuyển NULL thành 0. Vì vậy, function trả 0 nếu khách hàng chưa có đơn hàng thỏa điều kiện.

### 8.1. Gọi function trong PL/SQL

```sql
DECLARE
    v_total NUMBER;
BEGIN
    v_total := get_customer_order_total(501);
    DBMS_OUTPUT.PUT_LINE('Total=' || v_total);
END;
/
```

### 8.2. Gọi function trong SQL

```sql
SELECT get_customer_order_total(501) AS order_total
FROM dual;
```

Đây là lợi ích quan trọng của function: nếu đáp ứng quy tắc SQL invocation, nó có thể được dùng trong SELECT, WHERE, ORDER BY hoặc biểu thức SQL phù hợp.

## 9. Quy tắc khi gọi function từ SQL

Không phải mọi function PL/SQL đều có thể được gọi từ SQL. Function cần tuân thủ các giới hạn về tham số, kiểu dữ liệu và tác động phụ.

### 9.1. Dùng tham số IN cho function gọi từ SQL

Function được gọi trực tiếp từ SQL không được khai báo tham số `OUT` hoặc `IN OUT`. Các tham số dùng trong SQL invocation phải tương thích với kiểu dữ liệu mà SQL hỗ trợ trong phiên bản database đó.

Ví dụ phù hợp:

```sql
CREATE OR REPLACE FUNCTION add_tax (
    p_amount IN NUMBER
) RETURN NUMBER
AS
BEGIN
    RETURN p_amount * 1.10;
END add_tax;
/

SELECT add_tax(1000)
FROM dual;
```

Function dùng IN parameter và trả scalar NUMBER.

### 9.2. Function gọi từ SQL nên tránh DML và side effect

Function được gọi trong câu SQL nên được thiết kế như một phép tính/đọc dữ liệu không gây tác động phụ. Nếu function cố thực hiện DML trong ngữ cảnh truy vấn SQL, Oracle có thể phát sinh lỗi như `ORA-14551: cannot perform a DML operation inside a query`.

Function được gọi từ SQL cũng không thể thực hiện transaction control như COMMIT hoặc ROLLBACK. Không dùng function trong SELECT để âm thầm cập nhật bảng, ghi log bằng DML hoặc điều khiển workflow.

Nếu cần thay đổi dữ liệu, dùng procedure hoặc câu DML rõ ràng.

### 9.3. Không dựa vào số lần function được gọi

Khi function xuất hiện trong SQL, optimizer có thể biến đổi kế hoạch thực thi. Không giả định function được gọi đúng một lần cho mỗi hàng, hoặc được gọi theo thứ tự hàng mà bạn nhìn thấy trong kết quả.

Function dùng trong SQL cần tránh side effect và không nên phụ thuộc vào thứ tự hay số lần được gọi. Nếu cần điều khiển thứ tự thực thi, hãy viết logic rõ ràng trong PL/SQL hoặc cấu trúc SQL phù hợp.

### 9.4. Function có thể đọc bảng

Function đọc bảng và trả một giá trị có thể dùng trong SQL nếu đáp ứng các điều kiện khác:

```sql
CREATE OR REPLACE FUNCTION get_customer_level (
    p_customer_id IN customers.customer_id%TYPE
) RETURN VARCHAR2
AS
    v_level customers.customer_level%TYPE;
BEGIN
    SELECT customer_level
    INTO v_level
    FROM customers
    WHERE customer_id = p_customer_id;

    RETURN v_level;
END get_customer_level;
/
```

Nếu không tìm thấy khách hàng, function phát sinh `NO_DATA_FOUND` trừ khi có handler. Khi function được gọi từ một truy vấn lớn, exception có thể làm cả statement thất bại. Hãy cân nhắc cardinality và chi phí gọi function trên nhiều hàng.

### 9.5. Tránh gọi function PL/SQL theo từng hàng nếu có thể dùng SQL set-based

Ví dụ:

```sql
SELECT order_id,
       get_customer_level(customer_id)
FROM orders;
```

Nếu function chạy truy vấn riêng cho từng đơn hàng, một câu SELECT lớn có thể dẫn đến rất nhiều lần thực thi PL/SQL và SQL. Nếu logic có thể viết thành JOIN hoặc biểu thức SQL thuần, thường nên ưu tiên cách set-based để optimizer có nhiều thông tin tối ưu hơn.

Không phải mọi function call đều chậm; hãy đo workload. Nhưng cần nhận diện nguy cơ context switching và repeated lookup khi function được gọi trên nhiều hàng.

## 10. Transaction trong procedure và function

### 10.1. Procedure thường để caller quản lý transaction

Một procedure thực hiện DML:

```sql
CREATE OR REPLACE PROCEDURE update_demo_order_status (
    p_order_id IN demo_orders.order_id%TYPE,
    p_status   IN demo_orders.status%TYPE
) AS
BEGIN
    UPDATE demo_orders
    SET status = p_status
    WHERE order_id = p_order_id;

    IF SQL%ROWCOUNT = 0 THEN
        RAISE_APPLICATION_ERROR(
            -20021,
            'Order does not exist'
        );
    END IF;
END update_demo_order_status;
/
```

Procedure không COMMIT. Caller có thể gọi thêm procedure khác rồi COMMIT tất cả như một nghiệp vụ, hoặc ROLLBACK nếu một bước thất bại.

### 10.2. Vì sao COMMIT ẩn trong procedure có thể nguy hiểm?

Giả sử ứng dụng cần:

1. Tạo đơn hàng.
2. Trừ tồn kho.
3. Ghi lịch sử thanh toán.

Nếu procedure tạo đơn hàng tự COMMIT ở bước 1, caller không thể ROLLBACK toàn bộ đơn hàng khi bước trừ tồn kho thất bại. Transaction boundary bị chia cắt ngoài ý muốn.

Chỉ để procedure tự COMMIT khi hợp đồng nghiệp vụ quy định rõ procedure đó sở hữu transaction và caller hiểu tác động.

### 10.3. Function dùng để tính giá trị

Function thông thường nên không DML và không điều khiển transaction:

```sql
CREATE OR REPLACE FUNCTION calculate_line_total (
    p_quantity IN NUMBER,
    p_unit_price IN NUMBER
) RETURN NUMBER
AS
BEGIN
    RETURN p_quantity * p_unit_price;
END calculate_line_total;
/
```

Function như vậy có thể dùng trong PL/SQL và SQL mà không gây side effect.

### 10.4. Function có DML trong PL/SQL context

PL/SQL function có thể chứa DML trong một số cách gọi từ PL/SQL, nhưng điều đó làm function có side effect và giới hạn khả năng gọi từ SQL. Nếu mục tiêu là cập nhật dữ liệu, procedure diễn đạt ý định rõ hơn.

Một function có DML khi được gọi từ câu SELECT có thể gặp `ORA-14551`. Autonomous transaction có các quy tắc riêng và không phải cách chung để biến function có side effect thành thiết kế tốt. Không dùng autonomous transaction chỉ để né giới hạn DML trong SQL.

## 11. AUTHID DEFINER và AUTHID CURRENT_USER

Stored procedure/function có thể chạy theo quyền của chủ sở hữu chương trình hoặc quyền của người gọi.

### 11.1. Definer's rights

Mặc định, stored PL/SQL unit dùng **definer's rights** (`AUTHID DEFINER`). Chương trình thực thi trong security context của schema sở hữu unit, theo các quy tắc quyền Oracle.

Ví dụ:

```sql
CREATE OR REPLACE PROCEDURE app_owner.close_demo_order (
    p_order_id IN NUMBER
) AUTHID DEFINER
AS
BEGIN
    UPDATE app_owner.demo_orders
    SET status = 'CLOSED'
    WHERE order_id = p_order_id;
END close_demo_order;
/
```

Ứng dụng có thể được cấp `EXECUTE` trên procedure mà không cần cấp trực tiếp quyền UPDATE trên bảng, nếu chương trình và quyền được thiết kế phù hợp.

### 11.2. Invoker's rights

Khai báo:

```sql
AUTHID CURRENT_USER
```

để dùng invoker's rights. Quyền truy cập được đánh giá theo current user/invoker theo quy tắc Oracle. Cách này hữu ích khi chương trình cần hoạt động trong security context của người gọi.

Ví dụ:

```sql
CREATE OR REPLACE PROCEDURE show_current_schema
AUTHID CURRENT_USER
AS
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        'CURRENT_USER=' || SYS_CONTEXT('USERENV', 'CURRENT_USER')
    );
END show_current_schema;
/
```

### 11.3. Chọn AUTHID có chủ đích

| Nhu cầu | Hướng cân nhắc |
|---|---|
| API database do schema sở hữu kiểm soát quyền truy cập bảng | `AUTHID DEFINER` |
| Logic cần áp dụng quyền của người gọi | `AUTHID CURRENT_USER` |
| Ứng dụng chỉ được phép gọi một số thao tác đã đóng gói | Definer's rights với GRANT EXECUTE tối thiểu |
| Chương trình truy cập đối tượng theo quyền caller | Invoker's rights, sau khi đánh giá kỹ security |

Không dùng `AUTHID CURRENT_USER` chỉ vì nghĩ nó an toàn hơn. Cần hiểu quyền truy cập, role, schema resolution và dependency của chương trình trong cả hai mô hình.

### 11.4. Quyền trực tiếp khi biên dịch stored PL/SQL

Khi biên dịch stored PL/SQL, quyền truy cập đối tượng phụ thuộc thường cần được cấp trực tiếp cho schema sở hữu chương trình; quyền chỉ đến từ role có thể không đủ để biên dịch các tham chiếu tĩnh. Hãy cấp quyền tối thiểu và kiểm tra lỗi compile nếu chương trình tham chiếu bảng/schema khác.

## 12. Gọi procedure và function

### 12.1. Gọi procedure trong anonymous block

```sql
BEGIN
    update_demo_order_status(
        p_order_id => 1001,
        p_status   => 'PAID'
    );
END;
/
```

Procedure được gọi như một statement, không đặt trực tiếp vào biểu thức SELECT.

### 12.2. Gọi function trong PL/SQL expression

```sql
DECLARE
    v_tax NUMBER;
BEGIN
    v_tax := calculate_tax(5000);

    IF v_tax > 0 THEN
        DBMS_OUTPUT.PUT_LINE('Tax=' || v_tax);
    END IF;
END;
/
```

### 12.3. Gọi function trong SQL

```sql
SELECT calculate_tax(5000) AS tax_amount
FROM dual;
```

### 12.4. Gọi procedure bằng EXEC trong SQL*Plus/SQLcl

```sql
EXEC update_demo_order_status(1001, 'PAID');
```

`EXEC` là lệnh tiện ích của client SQL*Plus/SQLcl, không phải cú pháp SQL chuẩn gửi trực tiếp từ JDBC. Khi viết script có nhiều lệnh, có thể dùng anonymous block.

### 12.5. Gọi procedure có OUT parameter từ SQL*Plus

```sql
VARIABLE v_order_id NUMBER;

BEGIN
    create_demo_order(501, 250000, :v_order_id);
END;
/

PRINT v_order_id;
```

`VARIABLE` và `PRINT` là lệnh client SQL*Plus/SQLcl. Bind variable `:v_order_id` được truyền vào OUT parameter.

## 13. Lựa chọn đơn vị chương trình phù hợp

Không phải logic nào cũng cần procedure hoặc function độc lập. Hãy chọn cấu trúc theo phạm vi tái sử dụng, mục tiêu và cách gọi.

| Đơn vị | Dùng khi | Ví dụ |
|---|---|---|
| Anonymous block | Tác vụ một lần, thử nghiệm, script triển khai hoặc glue code ngắn | Chạy một batch nhỏ, gọi procedure |
| Procedure | Thực hiện hành động, thay đổi dữ liệu hoặc điều phối nhiều bước trong database | `CREATE_ORDER`, `CLOSE_ACCOUNT` |
| Function | Trả về một giá trị tính toán/tra cứu, có thể dùng trong biểu thức | `CALCULATE_TAX`, `GET_ORDER_TOTAL` |
| Package | Nhóm API liên quan, cần public/private members, state hoặc overload | `ORDER_API`, `PAYMENT_API` |
| Trigger | Tự động phản ứng với sự kiện DML/DDL/database event | Audit, kiểm tra sự kiện đặc biệt |
| Object type method | Hành vi gắn với object type | Method của một object-relational type |

### 13.1. Khi nào dùng anonymous block?

Dùng anonymous block khi:

- Chỉ cần chạy một lần từ SQL client.
- Đang thử logic trước khi tạo stored unit.
- Muốn gọi nhiều procedure trong một script.
- Cần một đoạn glue code ngắn và không có nhu cầu gọi lại theo tên.

Nếu logic trở thành một API được dùng lại, hãy chuyển thành procedure/function hoặc package.

### 13.2. Khi nào dùng procedure?

Dùng procedure khi mục tiêu là hành động:

- INSERT một nghiệp vụ.
- Cập nhật trạng thái.
- Thực hiện một quy trình có nhiều bước DML.
- Trả nhiều kết quả qua OUT parameters.
- Mở và trả REF CURSOR khi API cần tập kết quả.

Procedure không trả giá trị trong biểu thức SQL như function.

### 13.3. Khi nào dùng function?

Dùng function khi caller cần một giá trị:

- Tính thuế, chiết khấu hoặc điểm.
- Chuẩn hóa một mã.
- Tra cứu một thuộc tính duy nhất.
- Trả tổng, số lượng hoặc một phân loại.
- Dùng trong biểu thức SQL nếu function tuân thủ các giới hạn.

Function nên có hành vi dễ dự đoán. Nếu function chỉ được gọi từ PL/SQL và có side effect, hãy xem xét liệu procedure có biểu đạt ý định rõ hơn.

### 13.4. Khi nào dùng package?

Khi có nhiều chương trình cùng phục vụ một miền nghiệp vụ, package giúp gom chúng thành một giao diện:

```sql
CREATE OR REPLACE PACKAGE order_api AS
    PROCEDURE create_order (
        p_customer_id IN NUMBER,
        p_amount IN NUMBER,
        p_order_id OUT NUMBER
    );

    FUNCTION get_order_total (
        p_customer_id IN NUMBER
    ) RETURN NUMBER;
END order_api;
/
```

Package body chứa implementation:

```sql
CREATE OR REPLACE PACKAGE BODY order_api AS
    PROCEDURE create_order (
        p_customer_id IN NUMBER,
        p_amount IN NUMBER,
        p_order_id OUT NUMBER
    ) AS
    BEGIN
        INSERT INTO demo_orders (customer_id, amount)
        VALUES (p_customer_id, p_amount)
        RETURNING order_id INTO p_order_id;
    END create_order;

    FUNCTION get_order_total (
        p_customer_id IN NUMBER
    ) RETURN NUMBER AS
        v_total NUMBER;
    BEGIN
        SELECT NVL(SUM(amount), 0)
        INTO v_total
        FROM demo_orders
        WHERE customer_id = p_customer_id;

        RETURN v_total;
    END get_order_total;
END order_api;
/
```

Package specification là public API; package body chứa implementation và có thể chứa private subprogram/variable không công khai trong spec.

Package còn hỗ trợ overloading trong cùng package, giúp dùng cùng tên cho các phiên bản có chữ ký khác nhau phù hợp quy tắc Oracle.

### 13.5. Khi nào không dùng trigger để thay procedure?

Trigger tự chạy khi sự kiện xảy ra, không được caller gọi như một API thông thường. Trigger hữu ích cho phản ứng tự động và một số quy tắc cần bảo vệ ở database, nhưng trigger ẩn hành động khỏi luồng gọi và có thể tạo side effect khó lần theo.

Nếu ứng dụng cần yêu cầu rõ ràng “đóng đơn hàng”, hãy dùng procedure. Trigger chỉ nên bổ sung hành vi tự động có lý do rõ ràng, không thay thế toàn bộ API nghiệp vụ.

## 14. Package và overloading

Standalone procedure/function cùng schema không hỗ trợ overloading theo cách package hỗ trợ. Nếu cần nhiều phiên bản cùng tên với các kiểu tham số khác nhau, hãy cân nhắc package.

Ví dụ:

```sql
CREATE OR REPLACE PACKAGE format_api AS
    FUNCTION format_value(p_value IN NUMBER) RETURN VARCHAR2;
    FUNCTION format_value(p_value IN DATE) RETURN VARCHAR2;
END format_api;
/

CREATE OR REPLACE PACKAGE BODY format_api AS
    FUNCTION format_value(p_value IN NUMBER) RETURN VARCHAR2 AS
    BEGIN
        RETURN TO_CHAR(p_value, 'FM999999990D00');
    END format_value;

    FUNCTION format_value(p_value IN DATE) RETURN VARCHAR2 AS
    BEGIN
        RETURN TO_CHAR(p_value, 'YYYY-MM-DD');
    END format_value;
END format_api;
/
```

Gọi:

```sql
SELECT format_api.format_value(1250.5)
FROM dual;

SELECT format_api.format_value(DATE '2026-11-14')
FROM dual;
```

Oracle chọn overload dựa trên kiểu và chữ ký tham số. Tránh thiết kế các overload có chữ ký mơ hồ hoặc các kiểu dữ liệu dễ bị chuyển đổi ngầm gây nhầm lẫn.

## 15. Biên dịch, kiểm tra lỗi và quản lý dependency

### 15.1. CREATE OR REPLACE

```sql
CREATE OR REPLACE PROCEDURE hello_app AS
BEGIN
    DBMS_OUTPUT.PUT_LINE('Hello');
END hello_app;
/
```

`OR REPLACE` cập nhật định nghĩa object cùng tên. Nó thuận tiện khi triển khai phiên bản mới, nhưng vẫn cần kiểm tra trạng thái compile và ảnh hưởng đến các unit phụ thuộc.

### 15.2. Xem lỗi biên dịch trong SQL*Plus/SQLcl

```sql
SHOW ERRORS PROCEDURE hello_app;
```

Với function:

```sql
SHOW ERRORS FUNCTION calculate_tax;
```

`SHOW ERRORS` là lệnh client, không phải SQL statement.

### 15.3. Xem lỗi qua USER_ERRORS

```sql
SELECT name,
       type,
       line,
       position,
       text
FROM user_errors
WHERE name = 'HELLO_APP'
ORDER BY sequence;
```

### 15.4. Xem trạng thái object

```sql
SELECT object_name,
       object_type,
       status,
       last_ddl_time
FROM user_objects
WHERE object_name IN ('HELLO_APP', 'CALCULATE_TAX')
ORDER BY object_type, object_name;
```

`VALID` nghĩa là unit đã biên dịch hợp lệ tại thời điểm xem. `INVALID` nghĩa là cần kiểm tra lỗi hoặc dependency và biên dịch lại.

### 15.5. Biên dịch lại

```sql
ALTER PROCEDURE hello_app COMPILE;
ALTER FUNCTION calculate_tax COMPILE;
```

Sau đó kiểm tra `USER_ERRORS` và `USER_OBJECTS`. Biên dịch thành công không chứng minh logic runtime đúng; cần kiểm thử với dữ liệu và tình huống thực tế.

### 15.6. Dependency

Procedure/function có thể phụ thuộc:

- Bảng và view.
- Type và collection type.
- Package.
- Function/procedure khác.
- Sequence hoặc schema objects khác.

Khi đối tượng phụ thuộc thay đổi, stored unit có thể bị invalidated và cần compile lại. Hãy kiểm tra `USER_DEPENDENCIES`:

```sql
SELECT name,
       type,
       referenced_owner,
       referenced_name,
       referenced_type
FROM user_dependencies
WHERE name = 'GET_EMPLOYEE_SALARY'
ORDER BY referenced_owner, referenced_name;
```

## 16. Quyền tạo, gọi và cấp EXECUTE

### 16.1. Quyền tạo procedure/function

Người dùng cần quyền tạo stored procedure/function trong schema của mình, thường là `CREATE PROCEDURE`. Để tạo trong schema khác cần quyền phù hợp như `CREATE ANY PROCEDURE`, vốn là quyền mạnh và chỉ nên cấp cho tài khoản quản trị triển khai.

### 16.2. Cấp quyền gọi procedure/function

Chủ sở hữu có thể cấp quyền EXECUTE:

```sql
GRANT EXECUTE ON create_demo_order TO app_user;
GRANT EXECUTE ON get_customer_order_total TO app_user;
```

Nếu object nằm trong schema khác:

```sql
BEGIN
    app_owner.create_demo_order(
        p_customer_id => 501,
        p_amount => 100000,
        p_order_id => v_order_id
    );
END;
/
```

Caller cần quyền EXECUTE phù hợp và tham chiếu đúng schema/object.

### 16.3. Definer's rights có thể đóng gói quyền DML

Với definer's rights, schema sở hữu procedure có thể được cấp quyền trực tiếp trên bảng; ứng dụng chỉ được cấp EXECUTE trên procedure. Đây là một cách xây dựng API database có kiểm soát.

Tuy nhiên, cần:

- Cấp quyền tối thiểu cho owner.
- Không ghép chuỗi SQL động từ input không tin cậy.
- Kiểm tra AUTHID và schema resolution.
- Không cấp quyền EXECUTE rộng cho người dùng không cần thiết.

## 17. Dynamic SQL trong procedure/function

Khi tên bảng, cột hoặc cấu trúc câu SQL chỉ biết lúc runtime, PL/SQL có thể dùng dynamic SQL:

```sql
CREATE OR REPLACE PROCEDURE count_rows (
    p_table_name IN VARCHAR2,
    p_count OUT NUMBER
) AS
    v_sql VARCHAR2(1000);
BEGIN
    v_sql := 'SELECT COUNT(*) FROM ' || DBMS_ASSERT.SQL_OBJECT_NAME(p_table_name);

    EXECUTE IMMEDIATE v_sql INTO p_count;
END count_rows;
/
```

Tên đối tượng SQL không thể bind bằng placeholder như giá trị dữ liệu. Ví dụ dùng `DBMS_ASSERT.SQL_OBJECT_NAME` để xác thực tên object theo quy tắc Oracle; trong ứng dụng thật, nên whitelist các tên bảng được phép.

Với giá trị dữ liệu, hãy dùng bind variables:

```sql
EXECUTE IMMEDIATE
    'SELECT COUNT(*) FROM demo_orders WHERE customer_id = :id'
INTO p_count
USING p_customer_id;
```

Không nối trực tiếp giá trị đầu vào vào SQL string vì có nguy cơ SQL injection và vấn đề parse.

Dynamic SQL không phải lý do để đưa mọi câu truy vấn vào chuỗi. Static SQL giúp compiler kiểm tra tên object/kiểu và theo dõi dependency tốt hơn.

## 18. Gọi procedure/function từ Java JDBC

### 18.1. Gọi procedure không có OUT parameter

```java
String sql = "{ call app_owner.update_demo_order_status(?, ?) }";

try (CallableStatement cs = connection.prepareCall(sql)) {
    cs.setLong(1, 1001L);
    cs.setString(2, "PAID");
    cs.execute();
}
```

`CallableStatement` là API JDBC chuẩn để gọi stored procedure. Tên schema có thể được ghi rõ để tránh nhầm object cùng tên ở schema khác.

### 18.2. Gọi procedure có OUT parameter

```java
String sql = "{ call app_owner.create_demo_order(?, ?, ?) }";

try (CallableStatement cs = connection.prepareCall(sql)) {
    cs.setLong(1, 501L);
    cs.setBigDecimal(2, new BigDecimal("250000.00"));
    cs.registerOutParameter(3, java.sql.Types.NUMERIC);

    cs.execute();

    long orderId = cs.getLong(3);
}
```

OUT parameter phải được đăng ký bằng kiểu JDBC phù hợp trước khi đọc kết quả.

### 18.3. Gọi function bằng escape syntax

```java
String sql = "{ ? = call app_owner.get_customer_order_total(?) }";

try (CallableStatement cs = connection.prepareCall(sql)) {
    cs.registerOutParameter(1, java.sql.Types.NUMERIC);
    cs.setLong(2, 501L);

    cs.execute();

    BigDecimal total = cs.getBigDecimal(1);
}
```

Placeholder đầu tiên nhận giá trị RETURN của function; placeholder tiếp theo là tham số đầu vào.

### 18.4. Gọi function qua SELECT

```java
String sql =
    "SELECT app_owner.get_customer_order_total(?) FROM dual";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 501L);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            BigDecimal total = rs.getBigDecimal(1);
        }
    }
}
```

Cách này dùng function như một biểu thức SQL; function phải đáp ứng các giới hạn gọi từ SQL. Dùng `CallableStatement` thường rõ ràng hơn khi cần gọi function theo hợp đồng stored program.

### 18.5. Transaction trong JDBC

```java
connection.setAutoCommit(false);

try (CallableStatement cs =
         connection.prepareCall("{ call app_owner.update_demo_order_status(?, ?) }")) {
    cs.setLong(1, 1001L);
    cs.setString(2, "PAID");
    cs.execute();

    connection.commit();
} catch (SQLException ex) {
    connection.rollback();
    throw ex;
}
```

Ví dụ minh họa caller quản lý transaction. Nếu connection được quản lý bởi framework transaction manager, hãy để framework sở hữu commit/rollback thay vì tự commit ở nhiều tầng.

## 19. Thiết kế API PL/SQL dễ sử dụng

### 19.1. Tên procedure nên diễn tả hành động

Ví dụ:

- `CREATE_ORDER`
- `CANCEL_ORDER`
- `UPDATE_CUSTOMER_ADDRESS`
- `REBUILD_DAILY_SUMMARY`

### 19.2. Tên function nên diễn tả giá trị

Ví dụ:

- `CALCULATE_TAX`
- `GET_ORDER_TOTAL`
- `NORMALIZE_EMAIL`
- `IS_CUSTOMER_ACTIVE`

Function trả BOOLEAN chỉ có thể dùng theo khả năng kiểu dữ liệu của phiên bản và ngữ cảnh. Nếu cần tương thích SQL/driver rộng, cân nhắc trả NUMBER hoặc VARCHAR2 theo hợp đồng rõ ràng.

### 19.3. Đừng trả quá nhiều trạng thái mơ hồ

Nếu procedure trả `OUT status_code`, hãy định nghĩa rõ:

| Mã | Ý nghĩa |
|---|---|
| `0` | Thành công |
| `1` | Không tìm thấy đối tượng |
| `2` | Trạng thái nghiệp vụ không cho phép |
| `-1` | Lỗi không dự kiến; exception được ném ra |

Đây chỉ là ví dụ quy ước; hệ thống thực tế nên dùng mã lỗi thống nhất. Không vừa trả status code vừa nuốt toàn bộ exception khiến caller không biết transaction đã thay đổi đến đâu.

### 19.4. Xác định cardinality của function

Function tra cứu một hàng bằng khóa duy nhất có thể dùng SELECT INTO và xử lý NO_DATA_FOUND. Nếu function tính tổng hoặc đếm, aggregate có thể trả một hàng. Nếu function cần trả nhiều hàng, hãy cân nhắc pipelined table function, collection return type hoặc procedure trả REF CURSOR theo nhu cầu; không ép một danh sách thành một scalar.

### 19.5. Hạn chế side effect trong function

Function dễ dùng nhất khi cùng đầu vào tạo cùng kết quả theo dữ liệu mà nó đọc và không thay đổi trạng thái. Với function được gọi từ SQL, tính không side effect càng quan trọng. Dùng procedure cho các hành động thay đổi dữ liệu để API phản ánh rõ tác động.

## 20. Những lỗi và nhầm lẫn thường gặp

| Lỗi/hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `PLS-00103` | Sai cú pháp, thiếu `;`, `BEGIN` hoặc `END` | Kiểm tra toàn bộ body và terminator |
| `PLS-00201` | Identifier chưa khai báo hoặc thiếu quyền | Kiểm tra tên, schema, quyền trực tiếp và dependency |
| `PLS-00323` | Package body không triển khai subprogram khai báo trong spec | Đồng bộ chữ ký spec/body |
| `PLS-00306` | Sai số lượng hoặc kiểu tham số khi gọi | Kiểm tra mode, thứ tự, datatype và default |
| `ORA-06503` | Function kết thúc mà không RETURN giá trị | Bảo đảm mọi đường thực thi bình thường đều RETURN |
| `ORA-14551` | Function được gọi từ query cố thực hiện DML | Chuyển thao tác ghi sang procedure hoặc DML riêng |
| `ORA-04063` | Stored object có lỗi hoặc không hợp lệ | Xem USER_ERRORS, sửa và compile |
| `ORA-04068` | Trạng thái package đã bị loại bỏ trong một số tình huống invalidation/recompile | Ứng dụng xử lý retry có kiểm soát; quản lý triển khai package |
| Procedure không trả giá trị | Mong đợi procedure dùng như biểu thức SQL | Dùng OUT parameter hoặc function |
| Function dùng như hành động | Function có DML/side effect khó dự đoán | Chuyển sang procedure nếu mục tiêu là thay đổi dữ liệu |
| Procedure tự COMMIT | Transaction boundary bị giấu trong API | Để caller quản lý hoặc ghi rõ hợp đồng sở hữu transaction |
| Function chạy chậm trong SELECT | Gọi PL/SQL lặp lại cho nhiều hàng | Xem xét SQL set-based, JOIN và runtime plan |
| Không gọi được từ schema khác | Thiếu EXECUTE hoặc gọi sai owner | GRANT EXECUTE và schema-qualify |
| Unit INVALID sau ALTER TABLE | Dependency bị ảnh hưởng | Xem USER_ERRORS/DEPENDENCIES và compile lại |
| Dynamic SQL bị injection | Nối input vào SQL string | Bind giá trị, validate/whitelist tên object |

### 20.1. Đọc lỗi compile

Trong SQL*Plus hoặc SQLcl:

```sql
SHOW ERRORS PROCEDURE create_demo_order;
SHOW ERRORS FUNCTION get_customer_order_total;
```

Hoặc:

```sql
SELECT name, type, line, position, text
FROM user_errors
WHERE name IN (
    'CREATE_DEMO_ORDER',
    'GET_CUSTOMER_ORDER_TOTAL'
)
ORDER BY name, sequence;
```

Không chỉ nhìn thông báo `Warning: Procedure created with compilation errors`; hãy đọc lỗi PLS cụ thể và vị trí.

## 21. Thực hành tổng hợp

Các bước dưới đây tạo bảng và stored units trong schema lab. Chỉ chạy khi có quyền CREATE TABLE/PROCEDURE và không dùng tên trùng với đối tượng nghiệp vụ. Identity column cần Oracle 12c Release 1 trở lên.

### Bước 1. Tạo bảng demo

```sql
CREATE TABLE lab_program_orders (
    order_id NUMBER GENERATED BY DEFAULT AS IDENTITY
        CONSTRAINT pk_lab_program_orders PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    amount NUMBER(12, 2) NOT NULL,
    status VARCHAR2(20) DEFAULT 'NEW' NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);
```

### Bước 2. Tạo procedure thêm đơn hàng

```sql
CREATE OR REPLACE PROCEDURE lab_create_order (
    p_customer_id IN lab_program_orders.customer_id%TYPE,
    p_amount IN lab_program_orders.amount%TYPE,
    p_order_id OUT lab_program_orders.order_id%TYPE
) AS
BEGIN
    IF p_amount < 0 THEN
        RAISE_APPLICATION_ERROR(-20050, 'Amount must be non-negative');
    END IF;

    INSERT INTO lab_program_orders (customer_id, amount, status)
    VALUES (p_customer_id, p_amount, 'NEW')
    RETURNING order_id INTO p_order_id;
END lab_create_order;
/
```

### Bước 3. Gọi procedure và nhận OUT value

```sql
DECLARE
    v_order_id lab_program_orders.order_id%TYPE;
BEGIN
    lab_create_order(501, 100000, v_order_id);
    DBMS_OUTPUT.PUT_LINE('New ID=' || v_order_id);
END;
/
```

### Bước 4. Tạo function tính tổng

```sql
CREATE OR REPLACE FUNCTION lab_customer_total (
    p_customer_id IN lab_program_orders.customer_id%TYPE
) RETURN NUMBER
AS
    v_total NUMBER;
BEGIN
    SELECT NVL(SUM(amount), 0)
    INTO v_total
    FROM lab_program_orders
    WHERE customer_id = p_customer_id
      AND status <> 'CANCELLED';

    RETURN v_total;
END lab_customer_total;
/
```

### Bước 5. Gọi function trong PL/SQL

```sql
DECLARE
    v_total NUMBER;
BEGIN
    v_total := lab_customer_total(501);
    DBMS_OUTPUT.PUT_LINE('Total=' || v_total);
END;
/
```

### Bước 6. Gọi function trong SQL

```sql
SELECT lab_customer_total(501) AS customer_total
FROM dual;
```

### Bước 7. Kiểm tra lỗi biên dịch và trạng thái

```sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name IN ('LAB_CREATE_ORDER', 'LAB_CUSTOMER_TOTAL')
ORDER BY object_type;

SELECT name, type, line, position, text
FROM user_errors
WHERE name IN ('LAB_CREATE_ORDER', 'LAB_CUSTOMER_TOTAL')
ORDER BY name, sequence;
```

### Bước 8. Quan sát transaction

```sql
SELECT *
FROM lab_program_orders
ORDER BY order_id;

ROLLBACK;
```

Procedure không COMMIT nên caller có thể rollback thao tác tạo đơn hàng. Nếu muốn giữ dữ liệu trong schema lab, thay ROLLBACK bằng COMMIT sau khi kiểm tra.

### Bước 9. Cấp quyền EXECUTE (tùy chọn)

Nếu có schema lab khác tên `APP_USER` và được phép cấp quyền:

```sql
GRANT EXECUTE ON lab_create_order TO app_user;
GRANT EXECUTE ON lab_customer_total TO app_user;
```

### Bước 10. Dọn đối tượng thực hành

Chỉ khi chắc chắn đây là đối tượng do bạn tạo và không cần giữ dữ liệu:

```sql
DROP PROCEDURE lab_create_order;
DROP FUNCTION lab_customer_total;
DROP TABLE lab_program_orders PURGE;
```

`DROP TABLE ... PURGE` xóa bảng và dữ liệu, bỏ qua recycle bin theo hành vi lệnh; DDL có commit ngầm. Không chạy các lệnh dọn trên schema nghiệp vụ hoặc đối tượng dùng chung.

## 22. Quy tắc ghi nhớ

| Câu hỏi | Chọn |
|---|---|
| Cần thực hiện hành động hoặc DML | Procedure |
| Cần một giá trị trong biểu thức | Function |
| Cần nhiều kết quả đầu ra | Procedure với OUT parameters hoặc API trả cursor |
| Cần logic được gọi một lần trong script | Anonymous block |
| Nhiều API cùng miền nghiệp vụ | Package |
| Cần tự động phản ứng theo sự kiện database | Trigger, nếu thực sự phù hợp |
| Cần function dùng trong SQL | Function có tham số/kiểu SQL-compatible và không có side effect không được phép |
| Cần thay đổi dữ liệu | Procedure hoặc DML rõ ràng |
| Cần caller kiểm soát transaction | Không COMMIT/ROLLBACK ẩn trong procedure |
| Cần quyền thực thi có kiểm soát | GRANT EXECUTE trên stored unit |
| Cần quyền theo caller | Xem xét AUTHID CURRENT_USER |
| Cần nhóm API và overload | Package specification/body |

## 23. Câu hỏi tự kiểm tra

**Câu 1.** Stored procedure là gì?

**Trả lời:** Chương trình PL/SQL có tên được lưu trong schema, thường dùng để thực hiện hành động hoặc quy trình và có thể nhận/trả dữ liệu qua tham số.

**Câu 2.** Stored function khác procedure ở điểm chính nào?

**Trả lời:** Function khai báo kiểu trả về và phải trả giá trị bằng RETURN; procedure không trả giá trị qua RETURN mà có thể dùng OUT/IN OUT.

**Câu 3.** Mode mặc định của tham số PL/SQL là gì?

**Trả lời:** `IN`.

**Câu 4.** OUT parameter dùng để làm gì?

**Trả lời:** Đưa giá trị do procedure/function tạo ra trở lại caller.

**Câu 5.** IN OUT khác OUT thế nào?

**Trả lời:** IN OUT nhận giá trị ban đầu từ caller rồi có thể sửa và trả lại; OUT chủ yếu dùng để trả kết quả.

**Câu 6.** Function có thể được gọi trong SELECT không?

**Trả lời:** Có, nếu function đáp ứng quy tắc SQL invocation về tham số, kiểu dữ liệu và tác động phụ.

**Câu 7.** Function gọi từ SQL có thể dùng OUT parameter không?

**Trả lời:** Không. Function được gọi trực tiếp từ SQL không được có tham số OUT hoặc IN OUT.

**Câu 8.** Vì sao function gọi từ SELECT không nên thực hiện DML?

**Trả lời:** DML trong query-invoked function bị hạn chế và có thể gây ORA-14551; function có side effect cũng làm hành vi SQL khó dự đoán.

**Câu 9.** Function phải bảo đảm điều gì về RETURN?

**Trả lời:** Mọi đường thực thi bình thường phải trả một giá trị tương thích với kiểu RETURN.

**Câu 10.** Có nên COMMIT bên trong mọi procedure không?

**Trả lời:** Không. Thường để caller quản lý transaction boundary để có thể kết hợp nhiều thao tác trong cùng transaction.

**Câu 11.** AUTHID DEFINER là gì?

**Trả lời:** Chương trình thực thi theo security context của schema sở hữu unit, theo quy tắc definer's rights của Oracle.

**Câu 12.** AUTHID CURRENT_USER có ý nghĩa gì?

**Trả lời:** Chương trình dùng invoker's rights, đánh giá quyền theo current user/caller theo quy tắc Oracle.

**Câu 13.** Package có lợi ích gì so với nhiều standalone procedures?

**Trả lời:** Gom API liên quan, tách public specification và private implementation, hỗ trợ overload và quản lý các thành phần cùng miền nghiệp vụ.

**Câu 14.** Làm sao kiểm tra procedure/function compile lỗi?

**Trả lời:** Dùng `SHOW ERRORS` hoặc truy vấn `USER_ERRORS`, sau đó kiểm tra trạng thái trong `USER_OBJECTS`.

**Câu 15.** Khi nào nên chọn trigger?

**Trả lời:** Khi cần phản ứng tự động theo sự kiện database có lý do rõ ràng; không dùng trigger thay cho API hành động mà ứng dụng cần gọi tường minh.

**Câu 16.** Có thể gọi procedure trực tiếp trong SELECT không?

**Trả lời:** Không. SQL expression cần function trả giá trị; procedure được gọi như một statement trong PL/SQL hoặc qua cơ chế gọi procedure của client.

## 24. Kết luận

`CREATE PROCEDURE` và `CREATE FUNCTION` tạo các chương trình PL/SQL có tên, được lưu trong schema và có thể tái sử dụng. Procedure phù hợp với hành động, DML và quy trình; function phù hợp với tính toán hoặc tra cứu trả một giá trị. Tham số `IN`, `OUT`, `IN OUT` xác định hướng dữ liệu, còn function phải khai báo kiểu trả về và có `RETURN` trên mọi đường thực thi bình thường.

Function có thể được dùng trong SQL nếu tuân thủ các giới hạn về tham số, kiểu dữ liệu và tác động phụ. Hãy giữ function dùng trong SQL đơn giản, dễ dự đoán và không thực hiện DML hoặc transaction control. Dùng procedure cho thao tác thay đổi dữ liệu, và thường để caller quản lý COMMIT/ROLLBACK để giữ transaction boundary rõ ràng.

Khi API lớn lên, package giúp nhóm các procedure/function theo miền nghiệp vụ, công khai giao diện ổn định và ẩn implementation. Anonymous block vẫn phù hợp cho script ngắn; trigger dành cho phản ứng tự động theo sự kiện. Lựa chọn đúng đơn vị chương trình giúp PL/SQL dễ gọi, dễ phân quyền, dễ kiểm thử và dễ bảo trì.
