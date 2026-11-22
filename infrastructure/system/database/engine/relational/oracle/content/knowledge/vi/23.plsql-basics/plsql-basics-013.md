# Quy ước tên, tổ chức khối và viết mã PL/SQL dễ bảo trì

## 1. Vì sao cần quy ước khi viết PL/SQL?

PL/SQL thường bắt đầu từ những anonymous block nhỏ: khai báo biến, chạy SELECT INTO, cập nhật một bảng rồi COMMIT. Khi ứng dụng lớn dần, logic được tách thành procedure, function, package, trigger và nhiều tầng xử lý. Một module có thể được nhiều người sửa trong nhiều năm, chạy trong batch hoặc ứng dụng OLTP.

Nếu mỗi người đặt tên theo một cách, viết block theo một kiểu và xử lý lỗi tùy ý, mã nguồn sẽ khó đọc và khó thay đổi. Những vấn đề thường gặp gồm:

- Không biết biến nào là parameter, biến nào là local variable.
- Tên biến quá ngắn hoặc trùng tên cột khiến câu SQL khó hiểu.
- Một procedure vừa đọc dữ liệu, tính toán, ghi nhiều bảng, gửi thông báo và COMMIT.
- Exception bị bắt rồi bỏ qua, làm ứng dụng tưởng rằng thao tác thành công.
- Một lỗi nhỏ ở giữa block khiến transaction ở trạng thái không rõ ràng.
- Logic lặp lại ở nhiều nơi và mỗi nơi được sửa khác nhau.
- Comment không còn đúng với hành vi thực tế.

Viết mã dễ bảo trì không phải là trang trí code. Mục tiêu là để người đọc hiểu nhanh ý định, xác định được phạm vi thay đổi, dự đoán được tác động và kiểm tra được kết quả.

Bài này tập trung vào ba nền tảng:

1. **Quy ước tên:** đặt tên nhất quán cho schema object, program unit, parameter, variable, constant, cursor và exception.
2. **Tổ chức block:** chia phần khai báo, phần thực thi, phần xử lý ngoại lệ và nested block rõ ràng.
3. **Thiết kế code:** tách trách nhiệm, kiểm soát transaction, xử lý lỗi, dùng SQL an toàn và ghi chú đúng chỗ.

> Nội dung dùng Oracle Database 19c và cú pháp PL/SQL thông dụng. Các prefix trong bài là convention của nhóm phát triển, không phải cú pháp bắt buộc của Oracle. Hãy chọn một convention cho dự án và áp dụng nhất quán.

## 2. Hình dạng cơ bản của một PL/SQL block

Một PL/SQL block có ba phần:

~~~sql
DECLARE
    -- Phần khai báo: biến, hằng, cursor, exception, type...
BEGIN
    -- Phần thực thi: câu lệnh PL/SQL và SQL
EXCEPTION
    -- Phần xử lý lỗi (tùy chọn)
END;
/
~~~

DECLARE và EXCEPTION là tùy chọn; BEGIN và END là bắt buộc. Phần khai báo không có từ khóa END riêng. Một block có thể lồng block khác bên trong.

### 2.1. Anonymous block

Anonymous block không có tên lưu trong database:

~~~sql
DECLARE
    l_total NUMBER := 0;
BEGIN
    SELECT COUNT(*)
    INTO l_total
    FROM employees;

    DBMS_OUTPUT.PUT_LINE('Employee count: ' || l_total);
END;
/
~~~

Anonymous block phù hợp với học cú pháp, script quản trị có kiểm soát, kiểm tra nhanh một đoạn logic hoặc gọi stored program units. Không nên để toàn bộ logic nghiệp vụ dài hạn trong một script anonymous block. Khi logic cần tái sử dụng, kiểm thử và phân quyền, hãy cân nhắc procedure, function hoặc package.

### 2.2. Named procedure

~~~sql
CREATE OR REPLACE PROCEDURE print_employee_count
AS
    l_total PLS_INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO l_total
    FROM employees;

    DBMS_OUTPUT.PUT_LINE('Employee count: ' || l_total);
END print_employee_count;
/
~~~

Procedure có tên và có thể được gọi từ nhiều nơi:

~~~sql
BEGIN
    print_employee_count;
END;
/
~~~

Tên sau END là tùy chọn trong cú pháp, nhưng ghi lại tên block giúp phát hiện nhầm lẫn khi block dài hoặc lồng nhau.

### 2.3. Function

Function trả về một giá trị:

~~~sql
CREATE OR REPLACE FUNCTION calculate_tax (
    p_taxable_amount IN NUMBER
)
RETURN NUMBER
IS
    c_tax_rate CONSTANT NUMBER := 0.10;
BEGIN
    RETURN p_taxable_amount * c_tax_rate;
END calculate_tax;
/
~~~

Tên function nên diễn tả kết quả mà function cung cấp. Function được gọi trong SQL còn chịu các quy tắc và giới hạn riêng về side effects, transaction control và kiểu dữ liệu.

### 2.4. Package

Package gom type, constant, variable, cursor, procedure và function có liên quan thành một API:

~~~sql
CREATE OR REPLACE PACKAGE employee_api AS
    PROCEDURE change_salary (
        p_employee_id IN employees.employee_id%TYPE,
        p_new_salary  IN employees.salary%TYPE
    );
END employee_api;
/

CREATE OR REPLACE PACKAGE BODY employee_api AS
    PROCEDURE change_salary (
        p_employee_id IN employees.employee_id%TYPE,
        p_new_salary  IN employees.salary%TYPE
    ) IS
    BEGIN
        UPDATE employees
        SET salary = p_new_salary
        WHERE employee_id = p_employee_id;

        IF SQL%ROWCOUNT = 0 THEN
            RAISE_APPLICATION_ERROR(-20001, 'Employee not found');
        END IF;
    END change_salary;
END employee_api;
/
~~~

Package specification là giao diện công khai. Package body chứa phần triển khai và có thể có helper private không xuất hiện trong specification.

## 3. Quy tắc cú pháp và cách kết thúc câu lệnh

Một số lỗi cú pháp PL/SQL đến từ việc nhầm dấu kết thúc statement với dấu kết thúc block hoặc lệnh của client.

### 3.1. Dấu chấm phẩy

Các statement PL/SQL kết thúc bằng dấu chấm phẩy:

~~~sql
l_count := 0;
SELECT COUNT(*) INTO l_count FROM employees;
DBMS_OUTPUT.PUT_LINE(l_count);
~~~

END; kết thúc block PL/SQL. Dấu slash trên một dòng riêng là lệnh của các công cụ như SQL*Plus, SQLcl hoặc SQL Developer ở chế độ chạy script; nó yêu cầu client gửi buffer hiện tại tới database. Dấu slash không phải statement PL/SQL và không phải lúc nào cũng cần khi gọi qua driver/API.

### 3.2. Phân biệt dấu chấm phẩy và dấu slash

Ví dụ chạy trong SQL*Plus/SQLcl:

~~~sql
BEGIN
    DBMS_OUTPUT.PUT_LINE('Hello');
END;
/
~~~

Khi ứng dụng JDBC/ODP.NET gửi anonymous block, ứng dụng thường gửi nội dung từ BEGIN đến END; mà không gửi dòng slash. Nếu copy slash vào API như một phần SQL statement, driver có thể báo lỗi cú pháp.

### 3.3. Viết statement nhiều dòng

SQL và PL/SQL không yêu cầu mỗi statement chỉ có một dòng. Hãy xuống dòng theo cấu trúc:

~~~sql
UPDATE orders
SET    status       = 'APPROVED',
       approved_at  = SYSTIMESTAMP,
       approved_by  = p_user_id
WHERE  order_id     = p_order_id;
~~~

Mục tiêu là để người đọc nhận ra bảng, cột được cập nhật và predicate mà không phải dò một dòng quá dài.

## 4. Quy ước tên identifier

Oracle cho phép tên object và identifier PL/SQL theo quy tắc riêng. Dự án nên chọn một style dễ đọc, ổn định và tránh phụ thuộc vào các tên đặc biệt.

### 4.1. Dùng tên thể hiện ý nghĩa

~~~sql
-- Khó hiểu
x NUMBER;
tmp NUMBER;
v1 VARCHAR2(100);

-- Dễ hiểu hơn
l_order_total NUMBER(12,2);
l_customer_email VARCHAR2(320);
l_retry_count PLS_INTEGER;
~~~

Tên ngắn vẫn hợp lý với biến vòng lặp có phạm vi rất nhỏ như i, j, nhưng không nên dùng tên một ký tự cho dữ liệu nghiệp vụ.

### 4.2. Chọn một kiểu chữ

Tên không đặt trong dấu ngoặc kép của Oracle không phân biệt chữ hoa/chữ thường. Dự án có thể viết UPPER_SNAKE_CASE cho SQL object và keyword, lower_snake_case cho biến PL/SQL, hoặc dùng convention khác miễn nhất quán.

~~~sql
CREATE OR REPLACE PROCEDURE close_expired_orders ...
~~~

~~~sql
l_expired_order_count PLS_INTEGER;
~~~

Không cần viết tên object trong dấu ngoặc kép chỉ để giữ chữ thường:

~~~sql
-- Tránh tạo quoted identifier không cần thiết
CREATE TABLE "SalesOrders" (...);
~~~

Quoted identifiers phân biệt hoa/thường khi tham chiếu và có thể gây phiền khi tích hợp công cụ, SQL và code generator. Dùng tên không quoted trừ khi có yêu cầu đặc biệt.

### 4.3. Tránh từ khóa và tên gây nhầm lẫn

Không đặt identifier trùng từ khóa SQL/PLSQL hoặc tên hàm có ý nghĩa đặc biệt nếu có thể tránh. Ví dụ, dùng order_status thay vì order, user_name thay vì user, created_at thay vì date.

Tránh các tên quá chung như VALUE, TYPE, LEVEL, COMMENT hoặc STATUS nếu có thể dùng tên cụ thể hơn. Một số tên vẫn có thể dùng hợp lệ trong ngữ cảnh nhất định, nhưng tên cụ thể giúp code dễ hiểu và ít xung đột hơn.

### 4.4. Độ dài identifier

Trong Oracle Database 19c với mức COMPATIBLE phù hợp (12.2 trở lên), phần lớn identifier có giới hạn tối đa 128 byte. Một số loại identifier vẫn có giới hạn riêng. Nếu môi trường cần tương thích với phiên bản cũ hơn, giới hạn có thể thấp hơn.

Không nên tận dụng toàn bộ độ dài cho tên. Tên quá dài khiến SQL khó đọc và khó viết. Dùng tên đủ rõ, tránh viết tắt tùy tiện và kiểm tra giới hạn của loại object cụ thể.

### 4.5. Dùng thuật ngữ nhất quán

Tên cột/bảng nên ổn định và không mang ý nghĩa chỉ đúng trong một màn hình hoặc một ngôn ngữ. Ví dụ customer_id, invoice_date, payment_status bền hơn ma_kh, ngay_hd, stt1 nếu codebase dùng tiếng Anh thống nhất.

Điều quan trọng là không trộn cust_id, customerNo, customer_number và c_id cho cùng một khái niệm ở các module khác nhau.

## 5. Quy ước đặt tên theo loại đối tượng

Một convention mẫu có thể dùng:

| Đối tượng | Quy ước minh họa | Ví dụ |
| --- | --- | --- |
| Table | Danh từ số nhiều hoặc danh từ tập hợp | ORDERS, CUSTOMERS |
| Column | Danh từ rõ nghĩa | ORDER_DATE, CUSTOMER_ID |
| Primary key | PK_<TABLE> | PK_ORDERS |
| Foreign key | FK_<CHILD>_<PARENT> | FK_ORDERS_CUSTOMERS |
| Unique constraint | UK_<TABLE>_<KEY> | UK_CUSTOMERS_EMAIL |
| Check constraint | CK_<TABLE>_<RULE> | CK_ORDERS_AMOUNT |
| Index | IX_<TABLE>_<COLUMNS> | IX_ORDERS_CUSTOMER_DATE |
| Sequence | SEQ_<ENTITY> | SEQ_ORDER_ID |
| View | V_<PURPOSE> hoặc VW_<PURPOSE> | VW_OPEN_ORDERS |
| Procedure | Động từ + đối tượng | CLOSE_EXPIRED_ORDERS |
| Function | Động từ/cụm diễn tả kết quả | CALCULATE_TAX |
| Package | Nhóm nghiệp vụ | ORDER_API, CUSTOMER_RULES |
| Trigger | Bảng + sự kiện + mục đích | TRG_ORDERS_AUDIT |

Prefix chỉ là gợi ý. Nếu dự án đã có convention khác, giữ convention của dự án thay vì đổi một phần khiến codebase không đồng nhất.

### 5.1. Tên procedure bắt đầu bằng động từ

Procedure thực hiện hành động: CREATE_ORDER, APPROVE_ORDER, CANCEL_ORDER, RECALCULATE_INVOICE, LOAD_DAILY_SALES. Tên nên nêu được hành động và đối tượng. PROCESS_DATA quá chung; RECONCILE_DAILY_PAYMENTS mô tả rõ hơn.

### 5.2. Tên function mô tả kết quả

Function thường trả một giá trị: GET_CUSTOMER_STATUS, CALCULATE_NET_AMOUNT, IS_VALID_EMAIL, COUNT_OPEN_ORDERS. Tên GET có thể gợi ý thao tác đọc, CALCULATE gợi ý phép tính. Tránh function có tên như một phép đọc nhưng lại ghi dữ liệu hoặc commit transaction.

### 5.3. Tên package theo miền nghiệp vụ

Package nên gom các thao tác có liên quan: ORDER_API, ORDER_VALIDATION, ORDER_REPORTING, PAYMENT_RECONCILIATION. Không tạo một package UTILS hoặc COMMON chứa hàng trăm procedure không liên quan. Package lớn khó phân quyền, kiểm thử và quản lý state.

## 6. Quy ước tên biến, parameter và constant

### 6.1. Prefix cho parameter và biến

Một convention dễ nhận biết:

- p_: parameter.
- l_: local variable.
- c_: constant.
- g_: package/global variable.
- r_: record variable.
- t_: collection/type, nếu dự án dùng quy ước này.
- e_: exception variable.

Ví dụ:

~~~sql
CREATE OR REPLACE PROCEDURE update_order_status (
    p_order_id IN orders.order_id%TYPE,
    p_status   IN orders.status%TYPE
)
IS
    l_updated_at TIMESTAMP;
BEGIN
    l_updated_at := SYSTIMESTAMP;

    UPDATE orders
    SET status = p_status,
        updated_at = l_updated_at
    WHERE order_id = p_order_id;
END update_order_status;
/
~~~

Người đọc có thể phân biệt parameter và local variable ngay tại chỗ sử dụng.

### 6.2. Mode của parameter

PL/SQL hỗ trợ:

- IN: chỉ đọc giá trị truyền vào; đây là mode mặc định.
- OUT: trả giá trị cho caller.
- IN OUT: nhận giá trị đầu vào và trả giá trị đã thay đổi.

Khai báo mode tường minh giúp API dễ đọc:

~~~sql
PROCEDURE calculate_invoice (
    p_invoice_id IN  invoices.invoice_id%TYPE,
    p_total      OUT invoices.total_amount%TYPE
);
~~~

Không dùng OUT hoặc IN OUT chỉ để tránh return value. Hãy thiết kế interface sao cho caller hiểu rõ giá trị nào là input, output và trạng thái lỗi được truyền ra thế nào.

### 6.3. Constant thay cho magic number

~~~sql
DECLARE
    c_max_retry_count CONSTANT PLS_INTEGER := 5;
BEGIN
    IF l_retry_count > c_max_retry_count THEN
        ...
    END IF;
END;
/
~~~

Constant làm rõ ý nghĩa của giá trị và giúp thay đổi chính sách ở một nơi. Nếu giá trị là cấu hình vận hành, nên lưu trong configuration table hoặc cơ chế cấu hình phù hợp thay vì compile vào code.

### 6.4. Dùng subtype để diễn đạt miền giá trị

~~~sql
DECLARE
    SUBTYPE t_order_id IS orders.order_id%TYPE;
    l_order_id t_order_id;
BEGIN
    ...
END;
/
~~~

Subtype không tạo kiểu dữ liệu hoàn toàn mới; nó tạo tên cho một subtype của kiểu cơ sở và có thể giới hạn precision/range theo khai báo.

### 6.5. Tránh tên biến trùng tên cột

Tên parameter trùng cột có thể làm câu SQL mơ hồ:

~~~sql
-- Dễ gây nhầm lẫn
PROCEDURE find_order (order_id IN NUMBER) IS
BEGIN
    SELECT ...
    FROM orders
    WHERE order_id = order_id;
END;
~~~

Predicate order_id = order_id không diễn tả rõ cột hay biến được tham chiếu. Dùng prefix:

~~~sql
PROCEDURE find_order (p_order_id IN orders.order_id%TYPE) IS
BEGIN
    SELECT order_id
    INTO l_order_id
    FROM orders o
    WHERE o.order_id = p_order_id;
END;
~~~

Luôn qualify cột bằng table alias trong query có nhiều bảng hoặc khi có khả năng trùng tên với PL/SQL identifier.

## 7. Dùng %TYPE và %ROWTYPE để giảm phụ thuộc kiểu dữ liệu

### 7.1. %TYPE

%TYPE khai báo biến có kiểu tương thích với một cột hoặc biến khác:

~~~sql
DECLARE
    l_employee_id employees.employee_id%TYPE;
    l_salary      employees.salary%TYPE;
BEGIN
    ...
END;
/
~~~

Nếu kiểu dữ liệu của cột thay đổi, khai báo dựa trên %TYPE được đồng bộ khi compile lại program unit. Điều này giảm nguy cơ biến local dùng NUMBER(8) trong khi cột đã đổi thành NUMBER(12).

### 7.2. %ROWTYPE

%ROWTYPE khai báo record có cấu trúc tương ứng với row của table hoặc cursor:

~~~sql
DECLARE
    l_employee employees%ROWTYPE;
BEGIN
    SELECT *
    INTO l_employee
    FROM employees
    WHERE employee_id = 100;

    DBMS_OUTPUT.PUT_LINE(l_employee.last_name);
END;
/
~~~

%ROWTYPE tiện cho thao tác lấy nguyên row. Nếu chỉ cần vài cột, khai báo record riêng hoặc biến riêng thường giúp dependency rõ hơn và tránh kéo dữ liệu không cần thiết.

### 7.3. Dùng kiểu theo schema thay vì đoán độ dài

Thay vì khai báo VARCHAR2(100) cho email, nếu cột đã có định nghĩa thì dùng customers.email%TYPE. Điều này tránh lệch độ dài giữa code và schema. Tuy nhiên, %TYPE không tự thay thế mọi validation nghiệp vụ; dữ liệu vẫn cần kiểm tra theo quy tắc domain.

## 8. Tổ chức phần DECLARE

Phần khai báo nên được nhóm theo mục đích để người đọc tìm nhanh:

1. Constants và subtype/type.
2. Cursor declarations.
3. Exceptions.
4. Variables và records.
5. Collection variables.

Ví dụ:

~~~sql
DECLARE
    -- Constants and types
    c_batch_size CONSTANT PLS_INTEGER := 500;
    SUBTYPE t_order_id IS orders.order_id%TYPE;

    -- Exceptions
    e_order_not_found EXCEPTION;

    -- Variables
    l_order_id    t_order_id;
    l_order_total orders.total_amount%TYPE;
    l_processed   PLS_INTEGER := 0;
BEGIN
    ...
END;
/
~~~

Không bắt buộc phải dùng đúng thứ tự trên, nhưng nên có thứ tự thống nhất trong dự án.

Biến PL/SQL chưa được gán giá trị có giá trị NULL. Nếu logic yêu cầu giá trị mặc định, hãy khởi tạo ngay:

~~~sql
l_processed_count PLS_INTEGER := 0;
l_started_at      TIMESTAMP := SYSTIMESTAMP;
~~~

Với biến cần luôn có giá trị, có thể dùng NOT NULL cùng initializer:

~~~sql
l_batch_size PLS_INTEGER NOT NULL := 500;
~~~

Biến NOT NULL phải được khởi tạo; không thể để trạng thái NULL. Không khai báo biến thừa và không dùng package global thay cho parameter nếu không có yêu cầu state rõ ràng.

## 9. Tổ chức phần BEGIN: một luồng xử lý dễ theo dõi

Phần thực thi nên thể hiện rõ các bước nghiệp vụ:

1. Kiểm tra input.
2. Đọc dữ liệu cần thiết.
3. Kiểm tra điều kiện nghiệp vụ.
4. Thực hiện thay đổi.
5. Trả kết quả hoặc kết thúc.

Ví dụ:

~~~sql
CREATE OR REPLACE PROCEDURE approve_order (
    p_order_id IN orders.order_id%TYPE,
    p_user_id  IN orders.approved_by%TYPE
)
IS
    l_status orders.status%TYPE;
BEGIN
    IF p_order_id IS NULL THEN
        RAISE_APPLICATION_ERROR(-20001, 'Order ID is required');
    END IF;

    SELECT status
    INTO l_status
    FROM orders
    WHERE order_id = p_order_id;

    IF l_status <> 'PENDING' THEN
        RAISE_APPLICATION_ERROR(-20002, 'Order is not pending');
    END IF;

    UPDATE orders
    SET status = 'APPROVED',
        approved_by = p_user_id,
        approved_at = SYSTIMESTAMP
    WHERE order_id = p_order_id;
END approve_order;
/
~~~

Đoạn code cho thấy thứ tự kiểm tra, đọc và cập nhật. Trong hệ thống có nhiều session, cần bổ sung cơ chế khóa hoặc UPDATE có điều kiện để bảo vệ trạng thái giữa SELECT và UPDATE; ví dụ này tập trung vào cách tổ chức block.

### 9.1. Dùng alias và liệt kê cột

~~~sql
SELECT o.order_id,
       c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.status = p_status;
~~~

Trong code ứng dụng, tránh SELECT * nếu chỉ cần một số cột. Danh sách cột rõ ràng giảm phụ thuộc vào thay đổi schema và làm ý định dễ thấy hơn. %ROWTYPE là ngoại lệ hợp lý khi thật sự cần cả row.

### 9.2. Dùng SQL%ROWCOUNT

Sau DML, kiểm tra số row bị ảnh hưởng nếu nghiệp vụ phụ thuộc vào kết quả:

~~~sql
UPDATE orders
SET status = 'CANCELLED'
WHERE order_id = p_order_id
  AND status = 'PENDING';

IF SQL%ROWCOUNT = 0 THEN
    RAISE_APPLICATION_ERROR(-20003, 'Order not found or not pending');
END IF;
~~~

SQL%ROWCOUNT là implicit cursor attribute của câu SQL gần nhất trong session hiện tại. Hãy đọc nó ngay sau statement cần kiểm tra; một câu SQL khác có thể thay đổi giá trị implicit cursor attribute.

## 10. Tổ chức nested block và scope

Nested block giúp giới hạn scope của biến và xử lý exception cục bộ:

~~~sql
DECLARE
    l_total PLS_INTEGER := 0;
BEGIN
    DECLARE
        l_department_count PLS_INTEGER;
    BEGIN
        SELECT COUNT(*)
        INTO l_department_count
        FROM departments;

        l_total := l_department_count;
    END;

    DBMS_OUTPUT.PUT_LINE('Total: ' || l_total);
END;
/
~~~

l_department_count chỉ tồn tại trong nested block. Sau END của block trong, biến không còn trong scope.

- Biến khai báo ở block ngoài có thể được block trong tham chiếu.
- Biến khai báo ở block trong không thể được block ngoài tham chiếu.
- Nếu hai block khai báo identifier cùng tên, identifier ở block trong che khuất identifier cùng tên ở block ngoài.

Tránh shadowing nếu nó khiến người đọc không biết đang dùng biến nào. Có thể đặt label cho block:

~~~sql
<<order_processing>>
DECLARE
    l_order_id NUMBER := 100;
BEGIN
    DECLARE
        l_order_id NUMBER := 200;
    BEGIN
        DBMS_OUTPUT.PUT_LINE(order_processing.l_order_id);
        DBMS_OUTPUT.PUT_LINE(l_order_id);
    END;
END order_processing;
/
~~~

Label giúp tham chiếu identifier của block ngoài khi bị che khuất. Tuy nhiên, cách tốt hơn thường là tránh khai báo cùng tên ở các scope lồng nhau.

Nên dùng nested block khi một thao tác nhỏ có exception riêng, một nhóm biến chỉ cần tồn tại trong phạm vi ngắn hoặc một phần logic cần scope riêng. Không lồng quá nhiều tầng; nếu block dài và có trách nhiệm độc lập, tách thành procedure/function private thường dễ bảo trì hơn.

## 11. Xử lý exception có trách nhiệm

Phần EXCEPTION là một phần của hợp đồng hành vi. Nó cần làm rõ lỗi nào được xử lý tại chỗ, lỗi nào được chuyển lên caller và transaction còn ở trạng thái nào.

### 11.1. Bắt exception cụ thể

~~~sql
BEGIN
    SELECT salary
    INTO l_salary
    FROM employees
    WHERE employee_id = p_employee_id;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE_APPLICATION_ERROR(-20010, 'Employee not found');
    WHEN TOO_MANY_ROWS THEN
        RAISE_APPLICATION_ERROR(-20011, 'Employee key is not unique');
END;
~~~

Các predefined exceptions phổ biến:

| Exception | Ý nghĩa |
| --- | --- |
| NO_DATA_FOUND | SELECT INTO không trả row |
| TOO_MANY_ROWS | SELECT INTO trả nhiều hơn một row |
| ZERO_DIVIDE | Chia cho 0 |
| DUP_VAL_ON_INDEX | Vi phạm unique index/constraint |
| INVALID_NUMBER | Chuyển đổi chuỗi sang số không hợp lệ |
| VALUE_ERROR | Lỗi chuyển đổi hoặc giới hạn giá trị |
| CURSOR_ALREADY_OPEN | Mở cursor đã mở |
| INVALID_CURSOR | Thao tác cursor không hợp lệ |

### 11.2. WHEN OTHERS phải được dùng cẩn thận

Không viết:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        NULL;
END;
~~~

Code trên nuốt lỗi. Caller có thể tin rằng thao tác đã thành công dù dữ liệu chưa được xử lý.

Nếu cần bắt lỗi chung để ghi log rồi chuyển tiếp:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        log_error(
            p_module  => 'APPROVE_ORDER',
            p_code    => SQLCODE,
            p_message => SQLERRM
        );
        RAISE;
END;
~~~

RAISE trong handler phát lại exception hiện tại và giữ ngữ cảnh lỗi. Nếu không có lý do nghiệp vụ để xử lý, để exception tự truyền lên caller cũng là lựa chọn rõ ràng.

### 11.3. Định nghĩa exception riêng

~~~sql
DECLARE
    e_invalid_order_state EXCEPTION;
BEGIN
    IF l_status NOT IN ('PENDING', 'APPROVED') THEN
        RAISE e_invalid_order_state;
    END IF;
EXCEPTION
    WHEN e_invalid_order_state THEN
        RAISE_APPLICATION_ERROR(-20020, 'Invalid order state');
END;
/
~~~

### 11.4. Ánh xạ Oracle error bằng PRAGMA EXCEPTION_INIT

~~~sql
DECLARE
    e_resource_busy EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_resource_busy, -54);
BEGIN
    ...
EXCEPTION
    WHEN e_resource_busy THEN
        RAISE_APPLICATION_ERROR(-20030, 'Resource is busy; retry later');
END;
/
~~~

Mã lỗi cần được lấy từ tài liệu Oracle và tình huống thực tế. Không dùng exception name tự đặt để che mất lỗi gốc mà caller cần biết.

### 11.5. RAISE_APPLICATION_ERROR

RAISE_APPLICATION_ERROR cho phép trả lỗi nghiệp vụ trong khoảng mã -20000 đến -20999:

~~~sql
RAISE_APPLICATION_ERROR(-20001, 'Order ID is required');
~~~

Thông điệp nên nói rõ điều kiện không được đáp ứng, không chứa password/token/dữ liệu nhạy cảm, có mã ổn định để ứng dụng nhận diện và không biến mọi lỗi kỹ thuật thành một thông báo chung chung.

### 11.6. Giữ thông tin lỗi gốc

Khi log lỗi, có thể dùng SQLCODE, SQLERRM, DBMS_UTILITY.FORMAT_ERROR_STACK, DBMS_UTILITY.FORMAT_ERROR_BACKTRACE và DBMS_UTILITY.FORMAT_CALL_STACK.

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        log_error(
            p_code      => SQLCODE,
            p_message   => DBMS_UTILITY.FORMAT_ERROR_STACK,
            p_backtrace => DBMS_UTILITY.FORMAT_ERROR_BACKTRACE
        );
        RAISE;
END;
~~~

FORMAT_ERROR_BACKTRACE giúp xác định vị trí nơi exception phát sinh, kể cả khi exception được bắt ở một block khác. Logging routine phải được thiết kế để không che lỗi gốc.

## 12. Transaction và COMMIT trong PL/SQL

Một quyết định thiết kế quan trọng là procedure có tự COMMIT hay để caller quản lý transaction.

### 12.1. Tránh COMMIT tùy tiện trong procedure nghiệp vụ

Ví dụ khó phối hợp:

~~~sql
PROCEDURE update_order IS
BEGIN
    UPDATE orders ...;
    COMMIT;
END;
~~~

Nếu caller muốn cập nhật ORDER, PAYMENT và INVENTORY trong cùng transaction, COMMIT bên trong UPDATE_ORDER phá vỡ ranh giới transaction mà caller mong muốn.

Một convention phổ biến:

- Procedure nghiệp vụ thực hiện DML nhưng không tự COMMIT.
- Tầng service hoặc caller quyết định COMMIT/ROLLBACK khi toàn bộ use case thành công/thất bại.
- Batch job có thể tự quản lý commit theo từng batch nếu đây là yêu cầu thiết kế được ghi rõ.

Không có quy tắc cứng rằng mọi procedure đều cấm COMMIT; điều quan trọng là transaction ownership phải rõ ràng.

### 12.2. Exception không tự động rollback toàn transaction

Khi exception xảy ra, Oracle không tự động rollback mọi thay đổi đã thực hiện trong transaction. Caller có thể quyết định ROLLBACK toàn bộ hoặc xử lý theo savepoint.

~~~sql
SAVEPOINT before_order_update;

BEGIN
    UPDATE orders
    SET status = 'APPROVED'
    WHERE order_id = p_order_id;

    UPDATE inventory
    SET reserved_quantity = reserved_quantity + 1
    WHERE product_id = p_product_id;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK TO before_order_update;
        RAISE;
END;
~~~

Savepoint cho phép hoàn tác phần công việc sau điểm đánh dấu mà vẫn giữ các thay đổi trước đó trong transaction. Chỉ dùng khi semantics nghiệp vụ cho phép.

### 12.3. Autonomous transaction cho logging

PRAGMA AUTONOMOUS_TRANSACTION tạo transaction độc lập với transaction gọi. Nó có thể hữu ích khi cần lưu log lỗi ngay cả khi transaction nghiệp vụ rollback:

~~~sql
CREATE OR REPLACE PROCEDURE log_error (
    p_message IN VARCHAR2
)
IS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO application_error_log(message, logged_at)
    VALUES (p_message, SYSTIMESTAMP);

    COMMIT;
END log_error;
/
~~~

Autonomous transaction commit/rollback độc lập; log có thể tồn tại dù transaction nghiệp vụ rollback. Không truy cập row đang bị transaction cha khóa theo cách tạo vòng chờ và không dùng autonomous transaction để lách transaction design.

## 13. Chia module thành procedure, function và package

### 13.1. Mỗi routine có một trách nhiệm chính

Một procedure dài hàng nghìn dòng thường khó kiểm tra. Có thể tách luồng:

~~~text
PROCESS_ORDER
  |
  +-- VALIDATE_ORDER
  |
  +-- CALCULATE_ORDER_TOTAL
  |
  +-- RESERVE_INVENTORY
  |
  +-- WRITE_ORDER_AUDIT
~~~

Mỗi routine có input/output và side effect rõ ràng. Không tách thành hàng chục procedure một dòng nếu việc đó làm luồng xử lý khó theo dõi hơn.

### 13.2. Package specification là API

~~~sql
CREATE OR REPLACE PACKAGE order_api AS
    PROCEDURE approve_order (
        p_order_id IN orders.order_id%TYPE,
        p_user_id  IN orders.approved_by%TYPE
    );

    FUNCTION get_order_total (
        p_order_id IN orders.order_id%TYPE
    ) RETURN NUMBER;
END order_api;
/
~~~

Private helper nằm trong package body:

~~~sql
CREATE OR REPLACE PACKAGE BODY order_api AS
    PROCEDURE validate_order_state (
        p_order_id IN orders.order_id%TYPE
    ) IS
        l_status orders.status%TYPE;
    BEGIN
        SELECT status
        INTO l_status
        FROM orders
        WHERE order_id = p_order_id;

        IF l_status <> 'PENDING' THEN
            RAISE_APPLICATION_ERROR(-20040, 'Order is not pending');
        END IF;
    END validate_order_state;

    PROCEDURE approve_order (
        p_order_id IN orders.order_id%TYPE,
        p_user_id  IN orders.approved_by%TYPE
    ) IS
    BEGIN
        validate_order_state(p_order_id);

        UPDATE orders
        SET status = 'APPROVED',
            approved_by = p_user_id,
            approved_at = SYSTIMESTAMP
        WHERE order_id = p_order_id;
    END approve_order;

    FUNCTION get_order_total (
        p_order_id IN orders.order_id%TYPE
    ) RETURN NUMBER IS
        l_total orders.total_amount%TYPE;
    BEGIN
        SELECT total_amount
        INTO l_total
        FROM orders
        WHERE order_id = p_order_id;

        RETURN l_total;
    END get_order_total;
END order_api;
/
~~~

Caller chỉ thấy hai API công khai; VALIDATE_ORDER_STATE được giữ private trong body.

### 13.3. Hạn chế package state

Biến khai báo ở package specification hoặc body có thể tồn tại theo session (package state). Điều này có thể gây lỗi khó tìm trong connection pool vì request sau có thể dùng lại cùng database session.

Nếu cần state, định nghĩa rõ thời điểm khởi tạo và reset; tránh lưu dữ liệu nhạy cảm lâu hơn cần thiết; không giả định mỗi request nhận session mới; xem xét package initialization section và DBMS_SESSION.RESET_PACKAGE khi kiến trúc yêu cầu.

Ưu tiên parameter và bảng cấu hình khi dữ liệu cần tồn tại rõ ràng qua nhiều lời gọi hoặc nhiều session.

### 13.4. Tách query khỏi quy tắc nghiệp vụ khi hợp lý

Có thể tạo helper private cho đọc dữ liệu, kiểm tra trạng thái, tính toán hoặc ghi audit. Nhưng không nhất thiết tạo một function chỉ bọc một SELECT đơn giản nếu việc đó không làm tăng khả năng tái sử dụng hoặc độ rõ ràng.

## 14. Cursor và xử lý tập dữ liệu

### 14.1. Cursor FOR loop

Cursor FOR loop tự quản lý OPEN, FETCH và CLOSE:

~~~sql
BEGIN
    FOR r_order IN (
        SELECT order_id, status
        FROM orders
        WHERE status = 'PENDING'
        ORDER BY order_id
    ) LOOP
        DBMS_OUTPUT.PUT_LINE(
            r_order.order_id || ': ' || r_order.status
        );
    END LOOP;
END;
/
~~~

Đây thường là lựa chọn ngắn gọn, an toàn cho việc duyệt kết quả. Không cần khai báo explicit cursor nếu không cần điều khiển lifecycle đặc biệt.

### 14.2. Explicit cursor

~~~sql
DECLARE
    CURSOR c_orders (p_status VARCHAR2) IS
        SELECT order_id, status
        FROM orders
        WHERE status = p_status;
BEGIN
    FOR r_order IN c_orders('PENDING') LOOP
        DBMS_OUTPUT.PUT_LINE(r_order.order_id);
    END LOOP;
END;
/
~~~

Dùng explicit cursor khi cần truyền parameter, điều khiển OPEN/FETCH/CLOSE rõ ràng, dùng FOR UPDATE/WHERE CURRENT OF hoặc kiểm soát trạng thái cursor. Cursor FOR loop trên explicit cursor vẫn tự quản lý vòng đời cursor.

### 14.3. Không dùng row-by-row khi có thể dùng SQL set-based

Thay vì:

~~~sql
FOR r_order IN (
    SELECT order_id
    FROM orders
    WHERE status = 'EXPIRED'
) LOOP
    UPDATE orders
    SET status = 'CLOSED'
    WHERE order_id = r_order.order_id;
END LOOP;
~~~

Có thể viết một câu SQL:

~~~sql
UPDATE orders
SET status = 'CLOSED'
WHERE status = 'EXPIRED';
~~~

SQL set-based thường hiệu quả hơn vì Oracle xử lý nhiều row trong một statement. Dùng PL/SQL loop khi mỗi row thật sự cần logic riêng hoặc gọi API/side effect riêng.

### 14.4. BULK COLLECT và FORALL

Khi cần xử lý dữ liệu bằng PL/SQL nhưng muốn giảm chuyển đổi qua lại giữa SQL engine và PL/SQL engine, dùng BULK COLLECT và FORALL:

~~~sql
DECLARE
    TYPE t_order_ids IS TABLE OF orders.order_id%TYPE;
    l_order_ids t_order_ids;
BEGIN
    SELECT order_id
    BULK COLLECT INTO l_order_ids
    FROM orders
    WHERE status = 'EXPIRED';

    FORALL i IN 1 .. l_order_ids.COUNT
        UPDATE orders
        SET status = 'CLOSED'
        WHERE order_id = l_order_ids(i);
END;
/
~~~

Với tập dữ liệu lớn, dùng BULK COLLECT ... LIMIT để giới hạn bộ nhớ và xử lý theo batch. FORALL là bulk binding, không phải vòng lặp PL/SQL thông thường.

## 15. SQL động và bảo vệ khỏi SQL injection

### 15.1. Ưu tiên static SQL

Nếu tên bảng/cột và cấu trúc câu SQL đã biết khi compile, dùng static SQL:

~~~sql
SELECT salary
INTO l_salary
FROM employees
WHERE employee_id = p_employee_id;
~~~

Static SQL được kiểm tra cú pháp và dependency khi compile, dễ đọc và dễ tối ưu hơn.

### 15.2. Khi nào cần dynamic SQL?

Dùng dynamic SQL khi cấu trúc statement thực sự thay đổi lúc runtime, ví dụ tên bảng được chọn từ danh sách cho phép hoặc câu DDL được sinh theo metadata.

~~~sql
DECLARE
    l_sql VARCHAR2(1000);
    l_count PLS_INTEGER;
BEGIN
    l_sql := 'SELECT COUNT(*) FROM employees WHERE department_id = :dept_id';

    EXECUTE IMMEDIATE l_sql
        INTO l_count
        USING p_department_id;
END;
/
~~~

Giá trị dữ liệu phải được truyền bằng bind variables. Không nối chuỗi input của người dùng vào SQL:

~~~sql
-- Không an toàn
l_sql := 'SELECT * FROM employees WHERE last_name = '''
         || p_last_name || '''';
~~~

### 15.3. Bind variable không thay thế identifier

Bind variable dùng cho giá trị, không dùng để thay tên bảng hoặc tên cột. Nếu identifier cần thay đổi, dùng whitelist và DBMS_ASSERT phù hợp:

~~~sql
l_table_name := DBMS_ASSERT.SIMPLE_SQL_NAME(p_table_name);
l_sql := 'SELECT COUNT(*) FROM ' || l_table_name;
EXECUTE IMMEDIATE l_sql INTO l_count;
~~~

DBMS_ASSERT giúp xác thực dạng identifier nhưng không thay thế whitelist nghiệp vụ. Một tên hợp lệ về cú pháp vẫn có thể là object mà caller không được phép chọn. Kiểm tra danh sách bảng được phép trước khi thực thi.

## 16. Comment và tài liệu hóa

Comment nên giải thích lý do hoặc quy tắc nghiệp vụ mà code không thể hiện trực tiếp.

### 16.1. Comment hữu ích

~~~sql
-- Keep the last 90 days online because the reconciliation team
-- must compare current transactions with recent settlement files.
~~~

Comment này giải thích lý do retention 90 ngày.

### 16.2. Comment không hữu ích

~~~sql
-- Increase retry count by one
l_retry_count := l_retry_count + 1;
~~~

Comment chỉ lặp lại code và dễ trở thành thông tin thừa.

### 16.3. Header cho module dài hạn

~~~sql
/*
  Module : ORDER_API
  Purpose: Public operations for order lifecycle.
  Owner  : Data Applications
  Notes  : Caller owns the transaction; routines do not COMMIT.
*/
~~~

Tránh ghi lịch sử thay đổi dài trong header nếu dự án đã quản lý source control. Git history và pull request phù hợp hơn cho lịch sử ai sửa gì.

### 16.4. Tài liệu hóa API

Package specification nên có comment mô tả routine làm gì, ý nghĩa parameter, điều kiện đầu vào, side effects, exception có thể phát sinh và transaction ownership.

~~~sql
/*
  Approves a pending order.
  The caller owns COMMIT/ROLLBACK.
  Raises -20001 when the order does not exist.
*/
PROCEDURE approve_order (
    p_order_id IN orders.order_id%TYPE,
    p_user_id  IN orders.approved_by%TYPE
);
~~~

Comment sai còn nguy hiểm hơn không có comment vì nó dẫn người bảo trì đi sai hướng. Khi đổi điều kiện hoặc nghiệp vụ, cập nhật cả tài liệu, tên biến, test và comment liên quan.

## 17. Quy ước định dạng để đọc nhanh

Một style nhất quán nên quy định:

- Indent 2 hoặc 4 spaces, không trộn tab và spaces.
- Keyword SQL viết hoa hoặc viết theo một style thống nhất.
- Mỗi parameter một dòng khi danh sách dài.
- IS/AS, BEGIN, EXCEPTION, END đặt rõ ràng.
- Predicate dài tách thành nhiều dòng.
- Mỗi block có END label khi hữu ích.
- Không viết nhiều statement trên một dòng.

Ví dụ:

~~~sql
CREATE OR REPLACE PROCEDURE transfer_balance (
    p_source_account_id IN account_balance.account_id%TYPE,
    p_target_account_id IN account_balance.account_id%TYPE,
    p_amount             IN account_balance.balance%TYPE
)
IS
    l_source_balance account_balance.balance%TYPE;
BEGIN
    IF p_amount <= 0 THEN
        RAISE_APPLICATION_ERROR(-20050, 'Amount must be positive');
    END IF;

    SELECT balance
    INTO l_source_balance
    FROM account_balance
    WHERE account_id = p_source_account_id
    FOR UPDATE;

    IF l_source_balance < p_amount THEN
        RAISE_APPLICATION_ERROR(-20051, 'Insufficient balance');
    END IF;

    UPDATE account_balance
    SET balance = balance - p_amount
    WHERE account_id = p_source_account_id;

    UPDATE account_balance
    SET balance = balance + p_amount
    WHERE account_id = p_target_account_id;
END transfer_balance;
/
~~~

Ví dụ này minh họa cách định dạng, không phải API chuyển tiền hoàn chỉnh: triển khai thực tế cần khóa cả hai account theo thứ tự nhất quán, kiểm tra target tồn tại, kiểm tra currency/precision và để caller quản lý transaction.

## 18. Ghi log và quan sát khi vận hành

### 18.1. DBMS_OUTPUT chỉ phù hợp phát triển

DBMS_OUTPUT.PUT_LINE hữu ích trong lab và debug thủ công. Ứng dụng production không nên phụ thuộc DBMS_OUTPUT như cơ chế log chính vì output cần được client bật và đọc, không phải hệ thống log tập trung.

### 18.2. DBMS_APPLICATION_INFO

Có thể gắn module/action để DBA quan sát session:

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'ORDER_BATCH',
        action_name => 'CLOSE_EXPIRED'
    );

    -- Business work

    DBMS_APPLICATION_INFO.SET_ACTION(NULL);
    DBMS_APPLICATION_INFO.SET_MODULE(NULL, NULL);
END;
/
~~~

Module và action giúp truy vết workload trong session views và công cụ giám sát. Nên reset context khi hoàn tất, đặc biệt khi session được tái sử dụng trong connection pool.

### 18.3. Logging có cấu trúc

Một error log hữu ích có thể lưu timestamp, module/action, application request ID hoặc correlation ID, SQLCODE, error stack/backtrace, business key không nhạy cảm và người dùng/service account theo chính sách audit.

Không log password, access token, số thẻ hoặc dữ liệu cá nhân vượt quá nhu cầu.

## 19. Compile warnings và công cụ hỗ trợ

### 19.1. Kiểm tra compile errors

~~~sql
SHOW ERRORS PROCEDURE approve_order;
~~~

Hoặc:

~~~sql
SELECT line, position, text
FROM user_errors
WHERE name = 'APPROVE_ORDER'
  AND type = 'PROCEDURE'
ORDER BY sequence;
~~~

### 19.2. Bật PL/SQL warnings

~~~sql
ALTER SESSION SET PLSQL_WARNINGS = 'ENABLE:ALL';
~~~

Khi compile, xem USER_ERRORS hoặc ALL_ERRORS để nhận warning. Một số warning chỉ ra unreachable code, biến chưa dùng hoặc vấn đề có thể dẫn đến lỗi. Không phải warning nào cũng là bug, nhưng cần được xem xét thay vì bỏ qua mặc định.

### 19.3. PL/Scope

PL/Scope có thể thu thập metadata về identifier và câu SQL trong PL/SQL source, hỗ trợ phân tích usage và dependency ở mức source.

~~~sql
ALTER SESSION SET PLSCOPE_SETTINGS = 'IDENTIFIERS:ALL, STATEMENTS:ALL';
~~~

Sau đó compile lại program unit và truy vấn các dictionary views tương ứng như USER_IDENTIFIERS hoặc USER_STATEMENTS nếu phiên bản và quyền hỗ trợ. PL/Scope không thay thế test runtime hoặc review logic nghiệp vụ.

## 20. Ví dụ hoàn chỉnh: package xử lý đơn hàng có tổ chức

Ví dụ dưới đây kết hợp naming, package API, %TYPE, validation, DML có điều kiện và exception handling. Tên bảng giả định đã tồn tại.

### 20.1. Package specification

~~~sql
CREATE OR REPLACE PACKAGE order_api AS
    /*
      Approves an order in PENDING state.
      Caller owns transaction control.
    */
    PROCEDURE approve_order (
        p_order_id IN orders.order_id%TYPE,
        p_user_id  IN orders.approved_by%TYPE
    );

    FUNCTION get_order_total (
        p_order_id IN orders.order_id%TYPE
    ) RETURN orders.total_amount%TYPE;
END order_api;
/
~~~

### 20.2. Package body

~~~sql
CREATE OR REPLACE PACKAGE BODY order_api AS
    c_order_pending  CONSTANT orders.status%TYPE := 'PENDING';
    c_order_approved CONSTANT orders.status%TYPE := 'APPROVED';

    PROCEDURE approve_order (
        p_order_id IN orders.order_id%TYPE,
        p_user_id  IN orders.approved_by%TYPE
    ) IS
    BEGIN
        IF p_order_id IS NULL THEN
            RAISE_APPLICATION_ERROR(-20060, 'Order ID is required');
        END IF;

        UPDATE orders
        SET status = c_order_approved,
            approved_by = p_user_id,
            approved_at = SYSTIMESTAMP
        WHERE order_id = p_order_id
          AND status = c_order_pending;

        IF SQL%ROWCOUNT = 0 THEN
            DECLARE
                l_exists PLS_INTEGER;
            BEGIN
                SELECT COUNT(*)
                INTO l_exists
                FROM orders
                WHERE order_id = p_order_id;

                IF l_exists = 0 THEN
                    RAISE_APPLICATION_ERROR(-20061, 'Order not found');
                ELSE
                    RAISE_APPLICATION_ERROR(-20062, 'Order is not pending');
                END IF;
            END;
        END IF;
    END approve_order;

    FUNCTION get_order_total (
        p_order_id IN orders.order_id%TYPE
    ) RETURN orders.total_amount%TYPE IS
        l_total orders.total_amount%TYPE;
    BEGIN
        SELECT total_amount
        INTO l_total
        FROM orders
        WHERE order_id = p_order_id;

        RETURN l_total;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RAISE_APPLICATION_ERROR(-20063, 'Order not found');
    END get_order_total;
END order_api;
/
~~~

### 20.3. Gọi package

~~~sql
BEGIN
    order_api.approve_order(
        p_order_id => 1001,
        p_user_id  => 501
    );

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
~~~

Caller chịu trách nhiệm transaction. Nếu approve thất bại, caller rollback rồi chuyển lỗi lên tầng gọi. Trong ứng dụng thật, không nên trả stack kỹ thuật thô trực tiếp cho end user; tầng service có thể ánh xạ mã lỗi sang thông báo phù hợp trong khi vẫn lưu diagnostic details.

Ví dụ package tập trung vào tổ chức code. Khi có cạnh tranh trạng thái, UPDATE với predicate status = 'PENDING' giúp thao tác chuyển trạng thái có tính điều kiện nguyên tử. Nếu cần phân biệt chính xác giữa không tồn tại và trạng thái không hợp lệ dưới concurrency cao, thiết kế response semantics và locking theo yêu cầu nghiệp vụ.

## 21. Các anti-pattern thường gặp

| Anti-pattern | Vấn đề | Cách cải thiện |
| --- | --- | --- |
| Biến tên x, a1, tmp2 cho dữ liệu nghiệp vụ | Không hiểu ý nghĩa khi đọc code | Dùng tên theo domain |
| Parameter và column trùng tên | SQL dễ tham chiếu nhầm | Dùng prefix p_ và table alias |
| Một procedure làm mọi thứ | Khó test và thay đổi | Tách theo trách nhiệm |
| WHEN OTHERS THEN NULL | Nuốt lỗi | Bắt lỗi cụ thể hoặc log rồi RAISE |
| COMMIT trong helper procedure | Caller mất quyền điều khiển transaction | Xác định transaction owner |
| SELECT * ở mọi nơi | Phụ thuộc schema và kéo dữ liệu thừa | Chọn cột cần thiết |
| Row-by-row UPDATE | Tốn context switch và round-trip nội bộ | Dùng set-based SQL hoặc FORALL |
| Nối input vào dynamic SQL | SQL injection | Bind values, whitelist identifier |
| Package global giữ state không reset | Request khác dùng lại state cũ | Dùng parameter hoặc reset có chủ đích |
| Comment lặp lại từng dòng code | Nhiễu và dễ lỗi thời | Giải thích lý do và quy tắc |
| DBMS_OUTPUT làm production logging | Không có log bền vững/tập trung | Logging table/service có cấu trúc |
| Package COMMON khổng lồ | API không có cohesion | Chia package theo domain |
| Tên routine không thể hiện side effect | Caller không biết dữ liệu bị thay đổi | Đặt tên hành động và tài liệu hóa transaction |

## 22. Quy trình viết và thay đổi một module PL/SQL

Một quy trình thực tế có thể gồm:

1. Đọc schema và hợp đồng nghiệp vụ liên quan.
2. Xác định API public và dữ liệu vào/ra.
3. Chọn tên theo convention dự án.
4. Khai báo %TYPE, constant và exception cần thiết.
5. Viết luồng xử lý ngắn, có điều kiện rõ ràng.
6. Đặt transaction ownership và quy tắc rollback.
7. Xử lý exception cụ thể; không nuốt lỗi.
8. Dùng static SQL và bind variable khi cần dynamic SQL.
9. Compile với warnings phù hợp.
10. Kiểm thử success, boundary, no-data, duplicate và lỗi hệ thống.
11. Ghi lại side effect, quyền cần thiết và transaction behavior.
12. Triển khai qua source control và migration script có thể lặp lại theo quy trình dự án.

## 23. Checklist đọc và bảo trì code PL/SQL

1. **Tên có nói rõ ý nghĩa không?** Procedure là hành động; function mô tả kết quả; biến thể hiện domain.
2. **Parameter có dễ nhận diện không?** Dùng prefix hoặc convention thống nhất.
3. **Tên có trùng column không?** Qualify column bằng alias và đặt tên parameter rõ.
4. **Kiểu dữ liệu có phụ thuộc schema không?** Ưu tiên %TYPE/%ROWTYPE khi phù hợp.
5. **Biến có được khởi tạo đúng không?** Nhớ biến chưa gán có giá trị NULL.
6. **Block có tách rõ DECLARE, BEGIN, EXCEPTION không?** Dùng nested block có mục đích.
7. **Routine có một trách nhiệm chính không?** Tách helper khi làm rõ luồng.
8. **SQL có set-based được không?** Tránh row-by-row nếu một câu SQL làm được.
9. **Dynamic SQL có an toàn không?** Bind value và whitelist identifier.
10. **Exception có bị nuốt không?** WHEN OTHERS phải xử lý có chủ đích.
11. **Transaction owner là ai?** Không COMMIT tùy tiện trong helper.
12. **Logging có giữ lỗi gốc không?** Ghi backtrace và tránh dữ liệu nhạy cảm.
13. **Package state có được kiểm soát không?** Đặc biệt khi dùng connection pool.
14. **Comment có giải thích lý do không?** Cập nhật khi logic đổi.
15. **Compile warnings và test đã được xem chưa?** Kiểm tra cả success và failure paths.

## 24. Câu hỏi tự kiểm tra

**Câu 1.** Một PL/SQL block có những phần nào? Phần nào bắt buộc?

**Câu 2.** DECLARE và EXCEPTION có bắt buộc không?

**Câu 3.** Dấu slash sau END; là cú pháp PL/SQL hay lệnh của SQL*Plus/SQLcl?

**Câu 4.** Vì sao không nên dùng quoted identifier nếu không có yêu cầu đặc biệt?

**Câu 5.** Convention p_, l_, c_ có ý nghĩa gì?

**Câu 6.** IN, OUT và IN OUT khác nhau thế nào?

**Câu 7.** %TYPE và %ROWTYPE giúp giảm loại phụ thuộc nào?

**Câu 8.** Vì sao WHERE order_id = order_id dễ gây lỗi thiết kế?

**Câu 9.** Nested block ảnh hưởng scope của biến ra sao?

**Câu 10.** Vì sao không nên viết WHEN OTHERS THEN NULL?

**Câu 11.** RAISE khác RAISE_APPLICATION_ERROR thế nào?

**Câu 12.** Vì sao procedure helper thường không tự COMMIT?

**Câu 13.** Khi nào dùng package specification và package body?

**Câu 14.** Vì sao package global state có thể gây lỗi với connection pool?

**Câu 15.** Khi nào dùng BULK COLLECT và FORALL?

**Câu 16.** Vì sao dynamic SQL cần bind variable và whitelist identifier?

**Câu 17.** Comment tốt nên giải thích điều gì?

**Câu 18.** PL/SQL warnings và PL/Scope hỗ trợ hoạt động bảo trì ra sao?

<details>
<summary>Gợi ý đáp án</summary>

1. DECLARE (tùy chọn), BEGIN (bắt buộc), EXCEPTION (tùy chọn), END (bắt buộc).
2. Không. DECLARE và EXCEPTION là tùy chọn.
3. Là lệnh của client tool để gửi buffer; không phải statement PL/SQL.
4. Vì quoted identifiers phân biệt hoa/thường và gây khó khi tham chiếu/tích hợp.
5. Parameter, local variable và constant theo convention.
6. IN nhận input; OUT trả output; IN OUT nhận và trả giá trị.
7. Giảm việc khai báo kiểu/độ dài trùng lặp với table column hoặc row structure.
8. Không rõ một vế là column hay PL/SQL variable; có thể thành predicate luôn đúng hoặc sai ý định.
9. Biến trong block chỉ hiển thị trong block đó và các nested block bên trong; block ngoài không thấy biến nội bộ.
10. Vì nó che lỗi và khiến caller tưởng thao tác thành công.
11. RAISE phát exception hiện tại hoặc exception đã khai báo; RAISE_APPLICATION_ERROR tạo application error trong dải -20000 đến -20999.
12. Vì caller cần kiểm soát transaction gồm nhiều thao tác nghiệp vụ.
13. Specification công bố API; body triển khai API và giữ helper private.
14. Session được tái sử dụng nên state từ request trước có thể còn tồn tại trong request sau.
15. Khi phải xử lý dữ liệu bằng PL/SQL nhưng muốn giảm context switch và xử lý theo batch.
16. Bind bảo vệ giá trị và tăng khả năng reuse cursor; identifier không bind được nên phải xác thực và giới hạn bằng whitelist.
17. Lý do nghiệp vụ, quyết định thiết kế, side effect hoặc điều kiện không thể hiện rõ trong code.
18. Warnings cảnh báo vấn đề compile; PL/Scope cung cấp metadata identifier/statement để phân tích source.

</details>

## 25. Tài liệu Oracle chính thức

1. [Oracle Database 19c PL/SQL Language Reference — PL/SQL Language Fundamentals](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/plsql-language-fundamentals.html): block structure, lexical units, declarations, scope và identifiers.
2. [Oracle Database 19c PL/SQL Language Reference — PL/SQL Collections and Records](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/plsql-collections-and-records.html): records, collections và cách tổ chức dữ liệu trong PL/SQL.
3. [Oracle Database 19c PL/SQL Language Reference — Error Handling](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/plsql-error-handling.html): exception, propagation và exception handlers.
4. [Oracle Database 19c PL/SQL Language Reference — Subprograms](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/plsql-subprograms.html): procedure, function, parameter modes và subprogram design.
5. [Oracle Database 19c PL/SQL Language Reference — Packages](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/plsql-packages.html): package specification, body, initialization và package state.
6. [Oracle Database 19c PL/SQL Language Reference — Static SQL](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/static-sql.html): SQL statements trong PL/SQL.
7. [Oracle Database 19c PL/SQL Language Reference — Native Dynamic SQL](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/native-dynamic-sql.html): EXECUTE IMMEDIATE, bind variables và dynamic SQL.
8. [Oracle Database 19c PL/SQL Language Reference — Bulk SQL and Bulk Binding](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/bulk-sql-and-bulk-binding.html): BULK COLLECT và FORALL.
9. [Oracle Database 19c PL/SQL Language Reference — Conditional Compilation and Warnings](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/conditional-compilation1.html): compiler settings và PL/SQL warnings.
10. [Oracle Database 19c PL/SQL Language Reference — PL/Scope](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/plscope.html): thu thập metadata source code cho phân tích identifier và statement.
11. [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_APPLICATION_INFO](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_APPLICATION_INFO.html): gắn module/action cho giám sát session.
12. [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_ASSERT](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_ASSERT.html): xác thực tên SQL object và identifier trong dynamic SQL.

**Nguyên tắc cần nhớ:** Đặt tên để người đọc hiểu vai trò của dữ liệu và hành động; tổ chức mỗi block thành phần khai báo, luồng thực thi và xử lý lỗi rõ ràng; tách routine theo trách nhiệm; dùng %TYPE/%ROWTYPE, static SQL và bind variables khi phù hợp; không nuốt exception và không để transaction ownership mơ hồ. Một convention chỉ có giá trị khi cả nhóm áp dụng nhất quán và cập nhật cùng code khi nghiệp vụ thay đổi.
