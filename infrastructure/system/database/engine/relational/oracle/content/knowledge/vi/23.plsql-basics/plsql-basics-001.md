# Vai trò PL/SQL và ranh giới với SQL hoặc mã ứng dụng

PL/SQL là ngôn ngữ thủ tục được Oracle tích hợp vào database. Nó kết hợp SQL với biến, điều kiện, vòng lặp, exception, procedure, function, package và trigger. PL/SQL giúp đặt logic xử lý gần dữ liệu, giảm số lần ứng dụng gửi lệnh qua mạng và tạo các API database có thể dùng chung.

PL/SQL không thay thế SQL và cũng không thay thế toàn bộ mã ứng dụng. SQL mô tả dữ liệu cần đọc hoặc thay đổi theo cách khai báo; PL/SQL điều phối nhiều bước xử lý phía database; mã ứng dụng quản lý giao diện, request, xác thực, tích hợp dịch vụ và workflow ở cấp hệ thống.

Các ranh giới chính:

- **SQL:** truy vấn, lọc, join, tổng hợp và thay đổi dữ liệu theo tập hợp.
- **PL/SQL:** đóng gói logic gần dữ liệu, phối hợp nhiều câu SQL, kiểm soát luồng xử lý và xử lý lỗi trong Oracle.
- **Mã ứng dụng:** nhận yêu cầu, xác thực người dùng, điều phối dịch vụ, quản lý phiên, giao diện, tích hợp bên ngoài và transaction ở cấp use case.

## 1. PL/SQL là gì?

PL/SQL (Procedural Language extensions to SQL) là ngôn ngữ lập trình thủ tục của Oracle. Một khối PL/SQL có thể khai báo biến, thực hiện SQL, rẽ nhánh, lặp, xử lý ngoại lệ và gọi chương trình con.

~~~sql
DECLARE
    v_employee_id NUMBER := 101;
    v_salary      NUMBER;
BEGIN
    SELECT salary
    INTO v_salary
    FROM employees
    WHERE employee_id = v_employee_id;

    DBMS_OUTPUT.PUT_LINE('Salary = ' || v_salary);
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('Employee not found');
END;
/
~~~

Một block có phần khai báo tùy chọn, phần thực thi bắt buộc và phần xử lý exception tùy chọn. Dấu gạch chéo trên một dòng riêng là ký hiệu của một số client như SQL*Plus/SQLcl để gửi block tới database; nó không phải câu lệnh nằm trong PL/SQL block.

PL/SQL xuất hiện dưới nhiều hình thức: anonymous block, stored procedure, function, package, trigger và chương trình được gọi bởi scheduler hoặc công cụ quản trị.

## 2. Phân biệt SQL, PL/SQL và mã ứng dụng

| Thành phần | Bản chất | Công việc phù hợp |
|---|---|---|
| SQL | Ngôn ngữ truy vấn và thao tác dữ liệu khai báo | SELECT, INSERT, UPDATE, DELETE, MERGE, join, aggregate |
| PL/SQL | Ngôn ngữ thủ tục chạy trong Oracle Database | Điều phối nhiều câu SQL, kiểm tra dữ liệu, đóng gói xử lý phía database |
| Mã ứng dụng | Ngôn ngữ và runtime bên ngoài database | API, giao diện, authentication, tích hợp dịch vụ, workflow, transaction use case |

### 2.1. SQL mô tả kết quả cần lấy

Ví dụ tính tổng doanh thu theo khách hàng:

~~~sql
SELECT customer_id,
       SUM(amount) AS total_amount
FROM orders
WHERE order_date >= DATE '2026-01-01'
GROUP BY customer_id;
~~~

SQL mô tả tập kết quả mong muốn. Optimizer quyết định execution plan. Người viết không cần tự lặp qua từng khách hàng rồi cộng từng dòng nếu một câu aggregate diễn đạt trực tiếp yêu cầu.

### 2.2. PL/SQL điều phối các bước xử lý

~~~sql
CREATE OR REPLACE PROCEDURE mark_order_ready (
    p_order_id IN orders.order_id%TYPE
) AS
    v_status orders.status%TYPE;
BEGIN
    SELECT status
    INTO v_status
    FROM orders
    WHERE order_id = p_order_id
    FOR UPDATE;

    IF v_status = 'PAID' THEN
        UPDATE orders
        SET status = 'READY'
        WHERE order_id = p_order_id;
    ELSE
        RAISE_APPLICATION_ERROR(-20001, 'Order is not paid');
    END IF;
END;
/
~~~

Procedure dùng SQL để đọc, khóa và cập nhật dữ liệu; PL/SQL điều khiển luồng xử lý. Ví dụ không tự commit, để caller quản lý transaction.

### 2.3. Mã ứng dụng điều phối request

~~~text
Người dùng / hệ thống gọi API
            |
            v
       Application
  - Authentication / Authorization
  - Validate request
  - Điều phối use case
            |
            v
       Repository / DAO
  - Bind parameters
  - Gọi SQL hoặc PL/SQL
  - Quản lý connection
            |
            v
      Oracle Database
  - SQL engine
  - PL/SQL engine
  - Tables / indexes / constraints
            |
            v
       Application
  - Mapping response
  - Logging / tracing
  - Trả API response
~~~

Database không nên phải render giao diện, quản lý phiên đăng nhập hoặc trực tiếp gửi email theo từng thao tác. Những việc này thuộc tầng ứng dụng hoặc dịch vụ chuyên trách.

## 3. SQL là trung tâm của thao tác dữ liệu

SQL được thiết kế để xử lý dữ liệu theo tập hợp (set-based). Một câu lệnh có thể xử lý hàng nghìn hoặc hàng triệu hàng mà không cần ứng dụng gửi từng thao tác riêng lẻ.

### 3.1. Ưu tiên SQL set-based khi có thể

Ví dụ xử lý từng hàng bằng cursor:

~~~sql
BEGIN
    FOR r IN (
        SELECT order_id
        FROM orders
        WHERE status = 'NEW'
    ) LOOP
        UPDATE orders
        SET status = 'REVIEW'
        WHERE order_id = r.order_id;
    END LOOP;
END;
/
~~~

Nếu mục tiêu chỉ là đổi trạng thái cho mọi hàng thỏa điều kiện, một câu SQL đơn giản hơn:

~~~sql
UPDATE orders
SET status = 'REVIEW'
WHERE status = 'NEW';
~~~

Câu UPDATE thứ hai thể hiện trực tiếp mục tiêu theo tập hợp, thường tránh được vòng lặp PL/SQL không cần thiết.

### 3.2. Join và aggregate nên để SQL thực hiện

~~~sql
SELECT o.order_id,
       c.customer_name,
       SUM(oi.quantity * oi.unit_price) AS order_total
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
JOIN order_items oi
  ON oi.order_id = o.order_id
GROUP BY o.order_id, c.customer_name;
~~~

SQL engine được thiết kế để tối ưu join, filter và aggregate. Tự viết vòng lặp ghép dữ liệu có thể tạo nhiều lần truy vấn và logic khó tối ưu.

### 3.3. MERGE cho upsert theo tập hợp

~~~sql
MERGE INTO customer_summary t
USING (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(amount) AS total_amount
    FROM orders
    GROUP BY customer_id
) s
ON (t.customer_id = s.customer_id)
WHEN MATCHED THEN
    UPDATE SET
        t.order_count = s.order_count,
        t.total_amount = s.total_amount
WHEN NOT MATCHED THEN
    INSERT (customer_id, order_count, total_amount)
    VALUES (s.customer_id, s.order_count, s.total_amount);
~~~

MERGE diễn đạt việc cập nhật hàng đã tồn tại và chèn hàng chưa tồn tại theo một tập nguồn. PL/SQL có thể bao quanh câu MERGE nếu quy tắc nghiệp vụ cần nhiều bước hoặc xử lý lỗi bổ sung.

## 4. PL/SQL bổ sung khả năng thủ tục cho SQL

SQL tập trung mô tả thao tác dữ liệu; PL/SQL bổ sung các cấu trúc điều khiển và tổ chức chương trình.

### 4.1. Biến và kiểu dữ liệu

PL/SQL hỗ trợ kiểu số, ký tự, ngày giờ, boolean, record, collection, cursor và kiểu do người dùng định nghĩa.

~~~sql
DECLARE
    v_order_id orders.order_id%TYPE;
    v_status   orders.status%TYPE;
BEGIN
    v_order_id := 1001;
    v_status := 'NEW';
END;
/
~~~

%TYPE khai báo biến cùng kiểu với cột. %ROWTYPE tạo record có cấu trúc tương ứng một hàng của bảng hoặc cursor. Các thuộc tính này giúp giảm nguy cơ khai báo biến lệch datatype schema.

### 4.2. Rẽ nhánh và vòng lặp

~~~sql
DECLARE
    v_amount NUMBER := 1500;
BEGIN
    IF v_amount >= 1000 THEN
        DBMS_OUTPUT.PUT_LINE('Large order');
    ELSIF v_amount > 0 THEN
        DBMS_OUTPUT.PUT_LINE('Small order');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Invalid amount');
    END IF;
END;
/
~~~

PL/SQL hỗ trợ IF, CASE, LOOP, WHILE, FOR và cursor FOR LOOP. Chúng hữu ích khi có logic điều kiện hoặc xử lý tuần tự thực sự cần thiết. Không nên dùng vòng lặp để thay thế một câu SQL set-based đơn giản.

### 4.3. Procedure và function

Procedure biểu diễn một hành động; function trả về một giá trị.

~~~sql
CREATE OR REPLACE FUNCTION calculate_discount (
    p_amount IN NUMBER
) RETURN NUMBER
IS
BEGIN
    IF p_amount >= 10000000 THEN
        RETURN p_amount * 0.10;
    ELSIF p_amount >= 5000000 THEN
        RETURN p_amount * 0.05;
    END IF;

    RETURN 0;
END;
/
~~~

Function trên chỉ tính toán. Nếu quy tắc giảm giá cần dùng chung cho nhiều chương trình trong database, function có thể được đặt trong package. Nếu chính sách thay đổi thường xuyên theo chiến lược kinh doanh hoặc phụ thuộc dịch vụ ngoài, cần cân nhắc quản lý ở tầng ứng dụng hoặc cấu hình dữ liệu thay vì hard-code vào function.

### 4.4. Package

Package nhóm các khai báo và chương trình con liên quan:

~~~sql
CREATE OR REPLACE PACKAGE order_api AS
    PROCEDURE mark_paid(
        p_order_id IN orders.order_id%TYPE
    );

    FUNCTION get_order_total(
        p_order_id IN orders.order_id%TYPE
    ) RETURN NUMBER;
END order_api;
/
~~~

Package body chứa phần triển khai:

~~~sql
CREATE OR REPLACE PACKAGE BODY order_api AS

    PROCEDURE mark_paid(
        p_order_id IN orders.order_id%TYPE
    ) IS
    BEGIN
        UPDATE orders
        SET status = 'PAID'
        WHERE order_id = p_order_id
          AND status = 'PENDING';

        IF SQL%ROWCOUNT <> 1 THEN
            RAISE_APPLICATION_ERROR(-20002, 'Order cannot be marked paid');
        END IF;
    END mark_paid;

    FUNCTION get_order_total(
        p_order_id IN orders.order_id%TYPE
    ) RETURN NUMBER IS
        v_total NUMBER;
    BEGIN
        SELECT NVL(SUM(quantity * unit_price), 0)
        INTO v_total
        FROM order_items
        WHERE order_id = p_order_id;

        RETURN v_total;
    END get_order_total;

END order_api;
/
~~~

Package tạo API database có tên rõ ràng, giúp nhiều client gọi chung logic. Tuy nhiên, package cũng tạo dependency vào schema và phiên bản database; cần quy trình versioning, deploy và kiểm thử.

## 5. SQL engine và PL/SQL engine phối hợp thế nào?

Oracle có các thành phần thực thi SQL và PL/SQL. Khi một PL/SQL block thực hiện câu SQL, phần PL/SQL điều khiển luồng và chuyển câu SQL sang SQL engine xử lý. Kết quả được trả về PL/SQL để tiếp tục thực thi.

~~~sql
BEGIN
    UPDATE accounts
    SET balance = balance - 100
    WHERE account_id = 1;

    UPDATE accounts
    SET balance = balance + 100
    WHERE account_id = 2;
END;
/
~~~

PL/SQL điều phối hai câu lệnh; mỗi câu DML được SQL engine thực thi.

### 5.1. Context switch

Việc chuyển quyền thực thi giữa PL/SQL engine và SQL engine thường được gọi là context switch. Một lần chuyển đổi có chi phí nhất định. Nếu code chạy một câu SQL cho từng hàng trong vòng lặp lớn, số lần chuyển đổi có thể tăng đáng kể.

~~~sql
BEGIN
    FOR r IN (
        SELECT employee_id
        FROM employees
        WHERE department_id = 10
    ) LOOP
        UPDATE employees
        SET salary = salary * 1.05
        WHERE employee_id = r.employee_id;
    END LOOP;
END;
/
~~~

Với 50.000 nhân viên, logic có thể gây hàng chục nghìn lần gọi SQL từ PL/SQL. Nếu chỉ cần tăng lương cho cả phòng ban, một câu UPDATE phù hợp hơn:

~~~sql
UPDATE employees
SET salary = salary * 1.05
WHERE department_id = 10;
~~~

### 5.2. Context switch không phải network round-trip

Cần phân biệt:

- **PL/SQL ↔ SQL context switch:** chuyển thực thi giữa các engine bên trong Oracle Database.
- **Application ↔ Database round-trip:** ứng dụng gửi request qua network tới database và nhận kết quả.

Một stored procedure có thể giảm số network round-trip bằng cách gom nhiều thao tác vào một lần gọi database, nhưng bên trong procedure vẫn có thể tạo nhiều context switch nếu lặp từng câu SQL.

Ngược lại, một câu SQL lớn gửi từ ứng dụng chỉ cần một lần round-trip nhưng SQL engine vẫn có thể thực hiện execution plan phức tạp.

### 5.3. Bulk processing

Khi không thể diễn đạt toàn bộ logic bằng một câu SQL, PL/SQL hỗ trợ bulk SQL:

- **BULK COLLECT:** lấy nhiều hàng vào collection trong một lần fetch.
- **FORALL:** gửi nhiều lần DML dựa trên collection, giảm số lần chuyển giữa PL/SQL và SQL engine.

~~~sql
DECLARE
    TYPE t_employee_ids IS TABLE OF employees.employee_id%TYPE;
    l_ids t_employee_ids;
BEGIN
    SELECT employee_id
    BULK COLLECT INTO l_ids
    FROM employees
    WHERE department_id = 10;

    FORALL i IN 1 .. l_ids.COUNT
        UPDATE employees
        SET salary = salary * 1.05
        WHERE employee_id = l_ids(i);
END;
/
~~~

Nếu thao tác có thể viết bằng một câu UPDATE theo điều kiện, câu UPDATE set-based vẫn thường đơn giản hơn và tránh lấy danh sách ID vào bộ nhớ PL/SQL.

### 5.4. LIMIT để kiểm soát collection

Với tập dữ liệu lớn, BULK COLLECT toàn bộ có thể dùng nhiều PGA. Có thể fetch theo batch:

~~~sql
DECLARE
    CURSOR c_emp IS
        SELECT employee_id
        FROM employees
        WHERE department_id = 10;

    TYPE t_ids IS TABLE OF employees.employee_id%TYPE;
    l_ids t_ids;
BEGIN
    OPEN c_emp;

    LOOP
        FETCH c_emp BULK COLLECT INTO l_ids LIMIT 500;
        EXIT WHEN l_ids.COUNT = 0;

        FORALL i IN 1 .. l_ids.COUNT
            UPDATE employees
            SET salary = salary * 1.05
            WHERE employee_id = l_ids(i);
    END LOOP;

    CLOSE c_emp;
END;
/
~~~

Batch size cần được đo. Batch quá nhỏ làm tăng số lần fetch/DML batch; batch quá lớn làm tăng bộ nhớ và có thể kéo dài transaction.

## 6. Đưa logic vào PL/SQL hay ứng dụng?

Không có quy tắc mọi logic phải ở database hoặc mọi logic phải ở ứng dụng. Quyết định phụ thuộc dữ liệu, transaction, khả năng tái sử dụng, bảo mật, vận hành và yêu cầu triển khai.

### 6.1. Logic phù hợp với SQL

- Lọc, join, aggregate và sắp xếp dữ liệu.
- Thay đổi nhiều hàng theo điều kiện.
- Upsert và đồng bộ dữ liệu theo tập.
- Kiểm tra constraint và quan hệ dữ liệu.
- Phép tính dựa trên dữ liệu cùng database.

~~~sql
UPDATE inventory
SET reserved_qty = reserved_qty + :quantity
WHERE product_id = :product_id
  AND available_qty - reserved_qty >= :quantity;
~~~

Điều kiện kiểm tra và cập nhật được thực hiện trong cùng statement, tránh mô hình đọc số lượng ở ứng dụng rồi cập nhật sau mà không có điều kiện bảo vệ.

### 6.2. Logic phù hợp với PL/SQL

- Quy trình có nhiều bước SQL cần chạy gần dữ liệu.
- Kiểm tra và cập nhật dữ liệu trong cùng database session/transaction.
- API database dùng chung cho nhiều ứng dụng.
- Xử lý batch hoặc dữ liệu cần bulk processing.
- Logic quản trị schema hoặc tác vụ database theo lịch.
- Quy tắc cần bảo vệ invariant ở database và không nên để mọi client tự triển khai khác nhau.

~~~sql
CREATE OR REPLACE PROCEDURE approve_order (
    p_order_id IN orders.order_id%TYPE
) AS
    v_status orders.status%TYPE;
BEGIN
    SELECT status
    INTO v_status
    FROM orders
    WHERE order_id = p_order_id
    FOR UPDATE;

    IF v_status <> 'PENDING' THEN
        RAISE_APPLICATION_ERROR(-20010, 'Only pending orders can be approved');
    END IF;

    UPDATE orders
    SET status = 'APPROVED'
    WHERE order_id = p_order_id;
END;
/
~~~

### 6.3. Logic phù hợp với mã ứng dụng

- HTTP/API protocol và mapping request/response.
- Authentication, authorization theo user/session/token.
- Giao diện, localization và định dạng hiển thị.
- Gửi email, SMS, push notification qua dịch vụ chuyên dụng.
- Gọi REST/gRPC hoặc message broker.
- Điều phối nhiều database hoặc microservice.
- Workflow cần human approval hoặc tương tác dài.
- Cấu hình thay đổi thường xuyên theo tenant/feature flag.
- Logic cần chạy trên nhiều loại database hoặc nhiều môi trường.

Ứng dụng có thể gọi procedure để cập nhật dữ liệu, sau đó gửi event qua outbox/worker. Database không cần trực tiếp gọi email provider trong transaction cập nhật đơn hàng.

### 6.4. Bảng cân nhắc

| Tiêu chí | SQL | PL/SQL | Mã ứng dụng |
|---|---|---|---|
| Xử lý tập dữ liệu | Rất phù hợp | Điều phối SQL/bulk | Nên tránh lấy từng hàng nếu không cần |
| Nhiều bước gần dữ liệu | Hạn chế điều khiển | Phù hợp | Có thể điều phối qua API |
| Giao diện và HTTP | Không phù hợp | Không phù hợp | Phù hợp |
| Tích hợp dịch vụ ngoài | Không phải vai trò chính | Có giới hạn và tạo coupling | Phù hợp |
| Logic cần dùng chung giữa nhiều client | Query/view có thể dùng chung | Procedure/package có thể dùng chung | API/service có thể dùng chung |
| Transaction nhiều câu SQL | Một câu SQL có atomicity riêng | Có thể đóng gói bước database | Có thể sở hữu transaction qua connection/transaction manager |
| Khả năng đổi database | SQL dialect vẫn có khác biệt | Gắn chặt Oracle | Có thể trừu tượng hóa qua repository, tùy thiết kế |
| Triển khai | SQL migration/schema | Database object deployment | Application release |

## 7. Giữ transaction boundary ở đúng tầng

Một quyết định quan trọng là xác định ai sở hữu transaction.

Hai mẫu thường gặp:

1. **Application-owned transaction:** ứng dụng mở connection, tắt auto-commit, gọi nhiều câu SQL/procedure, rồi commit hoặc rollback.
2. **Database API-owned transaction:** procedure được thiết kế là một đơn vị nghiệp vụ hoàn chỉnh và có contract transaction riêng.

Cả hai đều có thể hợp lý. Vấn đề xảy ra khi hai tầng cùng nghĩ mình sở hữu transaction hoặc procedure tự commit mà caller không biết.

### 7.1. Procedure thường không nên COMMIT tùy tiện

Ví dụ không tốt cho một procedure dùng chung:

~~~sql
CREATE OR REPLACE PROCEDURE update_customer_status (
    p_customer_id IN customers.customer_id%TYPE
) AS
BEGIN
    UPDATE customers
    SET status = 'ACTIVE'
    WHERE customer_id = p_customer_id;

    COMMIT;
END;
/
~~~

Nếu ứng dụng muốn thực hiện thêm thao tác audit hoặc cập nhật bảng liên quan trong cùng transaction, COMMIT bên trong procedure sẽ xác nhận các thay đổi chưa commit khác của cùng session. Caller không thể rollback chúng nữa.

### 7.2. Procedure để caller quản lý transaction

~~~sql
CREATE OR REPLACE PROCEDURE update_customer_status (
    p_customer_id IN customers.customer_id%TYPE
) AS
BEGIN
    UPDATE customers
    SET status = 'ACTIVE'
    WHERE customer_id = p_customer_id;

    IF SQL%ROWCOUNT <> 1 THEN
        RAISE_APPLICATION_ERROR(-20020, 'Customer not found or status not updated');
    END IF;
END;
/
~~~

Caller quyết định commit hoặc rollback sau khi tất cả bước nghiệp vụ hoàn tất.

### 7.3. Application quản lý transaction qua JDBC

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        orderRepository.insert(connection, order);
        orderRepository.insertItems(connection, items);
        inventoryRepository.reserve(connection, items);
        auditRepository.insert(connection, order);

        connection.commit();
    } catch (SQLException | RuntimeException ex) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            ex.addSuppressed(rollbackError);
        }
        throw ex;
    }
}
~~~

Các repository phải sử dụng cùng connection được truyền vào. Nếu mỗi repository tự mở connection mới, các câu SQL có thể thuộc các transaction độc lập.

### 7.4. Khi nào procedure sở hữu transaction?

Một procedure có thể sở hữu transaction nếu contract được thiết kế rõ: nó thực hiện một tác vụ độc lập, tự commit hoặc rollback, và caller không mong ghép nó vào transaction lớn hơn. Cần tài liệu hóa hành vi và tránh gọi procedure đó từ các luồng cần transaction chung.

Autonomous transaction là transaction độc lập trong Oracle, có ngữ nghĩa khác transaction chính. Không dùng cơ chế này thay cho transaction nghiệp vụ cần nguyên tử.

## 8. Exception handling: chia trách nhiệm lỗi

PL/SQL có phần EXCEPTION để xử lý lỗi phát sinh trong block. Ứng dụng cũng có cơ chế exception riêng. Cần quyết định lỗi nào được xử lý ở database, lỗi nào truyền lên caller và lỗi nào được ánh xạ thành response.

### 8.1. Xử lý lỗi có ý nghĩa tại database

~~~sql
CREATE OR REPLACE PROCEDURE reserve_product (
    p_product_id IN inventory.product_id%TYPE,
    p_quantity   IN NUMBER
) AS
BEGIN
    IF p_quantity IS NULL OR p_quantity <= 0 THEN
        RAISE_APPLICATION_ERROR(-20030, 'Quantity must be positive');
    END IF;

    UPDATE inventory
    SET reserved_qty = reserved_qty + p_quantity
    WHERE product_id = p_product_id
      AND available_qty - reserved_qty >= p_quantity;

    IF SQL%ROWCOUNT <> 1 THEN
        RAISE_APPLICATION_ERROR(-20031, 'Product not found or insufficient inventory');
    END IF;
END;
/
~~~

Procedure dùng một UPDATE có điều kiện để tránh tách kiểm tra số lượng và cập nhật thành hai bước có thể cạnh tranh.

### 8.2. Không nuốt exception

Không nên viết:

~~~sql
BEGIN
    UPDATE orders
    SET status = 'APPROVED'
    WHERE order_id = 1001;
EXCEPTION
    WHEN OTHERS THEN
        NULL;
END;
/
~~~

Cách này che giấu mọi lỗi. Caller có thể tưởng procedure chạy thành công trong khi dữ liệu không được cập nhật.

Nếu cần ghi log rồi truyền lỗi lên:

~~~sql
BEGIN
    UPDATE orders
    SET status = 'APPROVED'
    WHERE order_id = 1001;
EXCEPTION
    WHEN OTHERS THEN
        -- Ghi nhận thông tin lỗi qua cơ chế logging đã thiết kế.
        RAISE;
END;
/
~~~

RAISE truyền lại exception hiện tại. Khi ghi log trong transaction độc lập, cần hiểu rõ autonomous transaction và hậu quả log vẫn tồn tại ngay cả khi transaction nghiệp vụ rollback.

### 8.3. Ánh xạ lỗi ở tầng ứng dụng

Ứng dụng có thể nhận Oracle error code/SQLState và ánh xạ thành lỗi nghiệp vụ hoặc response phù hợp. Không nên để database trả stack trace nội bộ, câu SQL nhạy cảm hoặc thông tin schema ra API công khai.

~~~java
try {
    orderService.approve(orderId);
} catch (SQLException ex) {
    if (isKnownBusinessError(ex)) {
        throw new OrderConflictException("Order cannot be approved", ex);
    }
    throw new DataAccessException("Database operation failed", ex);
}
~~~

Mã lỗi nghiệp vụ cần được thống nhất giữa PL/SQL package và ứng dụng; không phân loại mọi lỗi database thành cùng một HTTP status.

## 9. Bảo mật: quyền database và quyền ứng dụng

Đưa logic vào PL/SQL có thể tạo một API database có quyền rõ ràng. Oracle hỗ trợ hai mô hình quyền quan trọng cho stored program unit:

- **AUTHID DEFINER:** chương trình chạy theo quyền của owner/definer trong phạm vi quy tắc quyền của Oracle.
- **AUTHID CURRENT_USER:** chương trình chạy theo quyền của invoker/current user trong phạm vi ngữ nghĩa invoker-rights.

### 9.1. Definer rights

~~~sql
CREATE OR REPLACE PROCEDURE app_api.read_customer (
    p_customer_id IN NUMBER
)
AUTHID DEFINER
AS
    v_name customers.customer_name%TYPE;
BEGIN
    SELECT customer_name
    INTO v_name
    FROM customers
    WHERE customer_id = p_customer_id;

    DBMS_OUTPUT.PUT_LINE(v_name);
END;
/
~~~

Với definer rights, caller có thể được cấp quyền EXECUTE trên procedure mà không cần được cấp trực tiếp mọi quyền đọc bảng bên trong procedure, tùy cách cấp quyền và object reference.

Mô hình này hữu ích khi muốn cung cấp API database giới hạn, nhưng cần kiểm soát chặt SQL động, object resolution và quyền của owner.

### 9.2. Invoker rights

~~~sql
CREATE OR REPLACE PROCEDURE shared_api.process_data
AUTHID CURRENT_USER
AS
BEGIN
    NULL;
END;
/
~~~

Invoker rights có thể phù hợp với utility dùng trong nhiều schema và cần hành vi theo quyền của người gọi. Cần hiểu name resolution, role privilege và quyền runtime theo quy tắc PL/SQL của Oracle.

### 9.3. SQL động và injection

Không nối trực tiếp dữ liệu người dùng vào chuỗi SQL:

~~~sql
-- Không an toàn:
l_sql := 'SELECT * FROM customers WHERE customer_name = '''
         || p_name || '''';
~~~

Dùng bind variable:

~~~sql
l_sql := 'SELECT customer_id FROM customers WHERE customer_name = :name';

EXECUTE IMMEDIATE l_sql
    INTO v_customer_id
    USING p_name;
~~~

Bind variable bảo vệ giá trị dữ liệu khỏi bị diễn giải thành cú pháp SQL và hỗ trợ tái sử dụng cursor. Với tên bảng, tên cột hoặc từ khóa không thể bind như giá trị, cần whitelist và xác thực identifier; có thể xem xét DBMS_ASSERT cho trường hợp phù hợp.

### 9.4. Tầng ứng dụng vẫn cần authorization

Procedure kiểm tra dữ liệu không tự thay thế authentication. Database user của connection pool thường là service account dùng chung cho nhiều người dùng cuối. Database không tự biết danh tính end user trừ khi ứng dụng truyền context theo cơ chế được thiết kế và kiểm soát.

Ứng dụng vẫn phải xác thực người dùng/service caller, kiểm tra quyền tài nguyên/tenant, không tin dữ liệu user gửi lên, chỉ cấp quyền cần thiết cho database account và không trả lỗi nội bộ nhạy cảm ra bên ngoài.

## 10. Transaction nhiều database hoặc dịch vụ ngoài

Một transaction Oracle chỉ quản lý các thay đổi trong phạm vi transaction/resource được hỗ trợ. Nếu procedure cần gọi REST API, gửi email hoặc ghi message tới hệ thống khác, transaction Oracle không tự rollback hành động đã xảy ra ở hệ thống ngoài.

Không nên gửi email hoặc gọi dịch vụ thanh toán trực tiếp từ trigger/procedure trong lúc transaction chính đang mở nếu hệ thống ngoài không tham gia cùng một distributed transaction có thiết kế rõ.

### 10.1. Outbox pattern

Một mẫu phổ biến là ghi dữ liệu nghiệp vụ và sự kiện outbox trong cùng transaction Oracle:

~~~sql
INSERT INTO orders (
    order_id, status, total_amount
) VALUES (
    :order_id, 'CREATED', :total_amount
);

INSERT INTO outbox_events (
    event_id, aggregate_id, event_type, payload, status
) VALUES (
    :event_id, :order_id, 'ORDER_CREATED', :payload, 'PENDING'
);

COMMIT;
~~~

Worker ở tầng ứng dụng đọc outbox đã commit và gửi message/email/API. Nếu worker gửi thành công nhưng chết trước khi đánh dấu sự kiện đã gửi, sự kiện có thể được gửi lại; consumer cần idempotency.

### 10.2. Saga và thao tác bù

Một workflow nhiều dịch vụ có thể gồm nhiều transaction ngắn. Nếu bước sau thất bại, hệ thống thực hiện hành động bù để đưa nghiệp vụ về trạng thái chấp nhận được. Đây là saga/compensation, khác với rollback một transaction Oracle.

### 10.3. Autonomous transaction không phải distributed transaction

PRAGMA AUTONOMOUS_TRANSACTION tạo transaction độc lập trong Oracle. Nó không tự tham gia transaction với HTTP service hoặc message broker. Log được commit độc lập có thể còn lại dù transaction nghiệp vụ chính rollback. Chỉ dùng khi cần ngữ nghĩa độc lập đã xác định, chẳng hạn một số loại audit/log.

## 11. Trigger: logic tự động nhưng cần ranh giới rõ

Trigger là PL/SQL được Oracle gọi khi xảy ra sự kiện trên bảng, view, schema hoặc database theo loại trigger. Trigger có thể kiểm tra/chuẩn hóa dữ liệu, ghi audit thay đổi trong cùng transaction, thực hiện logic kỹ thuật gắn với bảng hoặc duy trì invariant mà mọi client phải tuân thủ.

Nhưng trigger có thể khiến logic trở nên khó nhìn thấy đối với ứng dụng. Một câu INSERT có thể kích hoạt nhiều trigger và làm phát sinh thay đổi khác.

### 11.1. Trigger không nên che giấu workflow lớn

Trigger gửi email trực tiếp khi đơn hàng được insert sẽ gắn database transaction với dịch vụ ngoài. Nếu email gửi thành công nhưng transaction rollback, người nhận đã nhận thông báo cho đơn hàng không tồn tại. Nếu email lỗi, DML có thể bị ảnh hưởng ngoài mong muốn.

Một cách dễ kiểm soát hơn là trigger hoặc procedure ghi event outbox trong cùng transaction, còn worker gửi thông báo sau commit.

### 11.2. Trigger và logic ở application

Nếu quy tắc chỉ áp dụng cho một giao diện hoặc một use case, đặt nó trong ứng dụng thường rõ hơn. Nếu quy tắc bảo vệ dữ liệu bất kể client nào ghi bảng, có thể cân nhắc constraint, trigger hoặc API database. Ưu tiên constraint khai báo như NOT NULL, CHECK, UNIQUE, foreign key khi có thể diễn đạt bằng constraint.

## 12. Function PL/SQL gọi từ SQL và giới hạn

PL/SQL function có thể được gọi trong SQL khi đáp ứng các quy tắc của Oracle:

~~~sql
SELECT employee_id,
       calculate_discount(salary) AS discount_amount
FROM employees;
~~~

Tuy nhiên, function gọi từ SQL có các hạn chế về side effect và transaction. Không nên dùng function có DML tùy tiện trong một SELECT. Function được gọi từ SQL cần tuân thủ các quy tắc purity/SQL-callable của Oracle; một số thao tác thay đổi trạng thái database có thể gây lỗi runtime hoặc hành vi khó dự đoán.

### 12.1. Không dùng function để thay thế join/aggregate

Nếu function truy vấn bảng phụ cho từng hàng:

~~~sql
SELECT order_id,
       get_customer_name(customer_id)
FROM orders;
~~~

Nếu có hàng trăm nghìn order, function có thể bị gọi rất nhiều lần. Một join thường rõ ràng và có thể tối ưu tốt hơn:

~~~sql
SELECT o.order_id,
       c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id;
~~~

Function trong SELECT list có thể tiện khi logic nhỏ, ổn định và chi phí thấp; nhưng không nên che giấu truy vấn lặp lớn.

### 12.2. DETERMINISTIC không phải lời hứa cache kết quả vĩnh viễn

Từ khóa DETERMINISTIC là cam kết của lập trình viên rằng cùng input sẽ tạo cùng output theo điều kiện của function. Không khai báo deterministic cho function phụ thuộc bảng thay đổi, session context, thời gian hoặc trạng thái ngoài nếu không bảo đảm tính xác định.

Không dùng DETERMINISTIC chỉ để hy vọng Oracle tự cache mọi kết quả. Việc tối ưu và caching phụ thuộc loại function, feature và ngữ cảnh sử dụng.

## 13. SQL động: khi cần cấu trúc câu lệnh thay đổi

PL/SQL có thể thực hiện SQL động bằng EXECUTE IMMEDIATE hoặc DBMS_SQL. SQL động cần thiết khi tên bảng/cột hoặc cấu trúc câu lệnh chỉ được biết tại runtime.

Ví dụ bind giá trị:

~~~sql
DECLARE
    l_count NUMBER;
BEGIN
    EXECUTE IMMEDIATE
        'SELECT COUNT(*) FROM orders WHERE status = :status'
        INTO l_count
        USING 'PENDING';

    DBMS_OUTPUT.PUT_LINE(l_count);
END;
/
~~~

### 13.1. Bind value, whitelist identifier

Không thể bind tên bảng bằng placeholder như một giá trị thông thường. Nếu tên bảng do người dùng chọn, cần ánh xạ qua whitelist:

~~~sql
DECLARE
    l_table_name VARCHAR2(30);
    l_count      NUMBER;
BEGIN
    IF :requested_type = 'ORDERS' THEN
        l_table_name := 'ORDERS';
    ELSIF :requested_type = 'CUSTOMERS' THEN
        l_table_name := 'CUSTOMERS';
    ELSE
        RAISE_APPLICATION_ERROR(-20040, 'Unsupported object');
    END IF;

    EXECUTE IMMEDIATE
        'SELECT COUNT(*) FROM ' || l_table_name
        INTO l_count;
END;
/
~~~

Tên identifier được chọn từ danh sách cho phép; giá trị dữ liệu vẫn nên dùng bind variable. Không nối chuỗi trực tiếp từ input không tin cậy.

### 13.2. Khi nào nên dùng SQL tĩnh?

SQL tĩnh được compiler PL/SQL kiểm tra sớm hơn về cú pháp, object và datatype trong nhiều tình huống, dễ đọc và dễ quản lý dependency hơn. Chỉ dùng SQL động khi thực sự cần thay đổi cấu trúc câu lệnh hoặc object được tham chiếu.

## 14. Hiệu năng: đặt logic gần dữ liệu hay ở application?

Đặt logic trong database có thể giảm round-trip, nhưng không phải lúc nào cũng nhanh hơn. Cần đo cả chi phí database, network và application.

### 14.1. Nhiều round-trip từ application

~~~java
for (Long orderId : orderIds) {
    Order order = repository.findById(orderId);
    repository.updateStatus(orderId, "REVIEW");
}
~~~

Với 10.000 order, ứng dụng có thể phát sinh hàng chục nghìn network round-trip và query execution. Nếu thao tác giống nhau theo điều kiện, một SQL UPDATE set-based hoặc một procedure xử lý batch có thể hiệu quả hơn.

### 14.2. Stored procedure không tự động nhanh hơn

Một procedure chứa vòng lặp và SELECT/UPDATE từng hàng vẫn có thể tạo nhiều context switch. Một câu SQL duy nhất từ application có thể nhanh hơn procedure làm cùng công việc theo kiểu row-by-row.

Hiệu năng phụ thuộc:
- Số network round-trip.
- Số PL/SQL/SQL context switch.
- Execution plan và statistics.
- Kích thước dữ liệu và selectivity.
- Index, partition và locking.
- PGA/SGA, CPU, I/O, redo/undo.
- Khối lượng xử lý ở application và network latency.

### 14.3. Bulk processing và batch size

Nếu logic phải xử lý từng record vì mỗi record có quy tắc riêng, có thể dùng BULK COLLECT/FORALL hoặc batch JDBC. Chọn batch size dựa trên đo đạc, memory, transaction duration và khả năng rollback.

Không giữ transaction mở trong khi chờ người dùng, gọi dịch vụ mạng chậm, tải file lớn, chờ message từ queue hoặc thực hiện tính toán dài không cần khóa dữ liệu. Tách phần chuẩn bị ngoài transaction khi an toàn, rồi mở transaction ngắn cho bước kiểm tra và cập nhật cần tính nguyên tử.

## 15. Kiểm thử PL/SQL và application

Logic trong database cần được kiểm thử như mã ứng dụng. Có thể kiểm thử bằng:
- Unit test PL/SQL, ví dụ framework utPLSQL nếu dự án sử dụng.
- Integration test từ JDBC/application.
- Test dữ liệu biên, null, duplicate và constraint.
- Test transaction rollback khi một bước thất bại.
- Test quyền definer/invoker và SQL injection.
- Test concurrency cho các cập nhật xung đột.
- Test performance với dữ liệu đại diện.

### 15.1. Test procedure trong SQL client

~~~sql
SET SERVEROUTPUT ON;

BEGIN
    order_api.mark_paid(1001);
    DBMS_OUTPUT.PUT_LINE('Procedure completed');
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(
            'Error ' || SQLCODE || ': ' || SQLERRM
        );
        RAISE;
END;
/
~~~

Nếu test DML trong môi trường lab và procedure không tự commit, người chạy cần quyết định commit/rollback sau khi kiểm tra kết quả. Không mặc định rằng chạy xong block PL/SQL đồng nghĩa database đã commit.

### 15.2. Test transaction rollback

~~~sql
BEGIN
    UPDATE orders
    SET status = 'PROCESSING'
    WHERE order_id = 1001;

    RAISE_APPLICATION_ERROR(-20050, 'Simulated failure');
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
~~~

Sau khi lỗi được truyền ra, thay đổi chưa commit trong transaction bị rollback. Khi thiết kế test thực tế, phải tính tới các procedure được gọi bên trong có tự commit, DDL implicit commit hoặc autonomous transaction hay không.

### 15.3. Test application contract

Integration test cần xác nhận:
- Procedure/function có tên và signature đúng.
- Input/output datatype và null semantics.
- Mã lỗi nghiệp vụ được ánh xạ đúng.
- Connection được trả về pool sau commit/rollback.
- Nhiều repository cùng tham gia một transaction khi cần.
- Không có SQL động dễ bị injection.
- Hành vi sau timeout/mất kết nối và retry có idempotent.

## 16. Triển khai và versioning logic PL/SQL

PL/SQL stored object là một phần của schema. Thay đổi package, procedure, function, view hoặc trigger cần được triển khai đồng bộ với application code phụ thuộc.

### 16.1. Database migration

~~~sql
CREATE OR REPLACE PACKAGE app_order_api AS
    PROCEDURE approve_order(p_order_id NUMBER);
END app_order_api;
/
~~~

Migration cần được quản lý bằng công cụ versioning của dự án, không sửa thủ công production mà không có lịch sử.

### 16.2. Tương thích ngược

Nếu application version cũ và mới cùng chạy trong quá trình rolling deployment, thay đổi signature procedure có thể làm phiên bản cũ lỗi. Một số nguyên tắc:
- Ưu tiên thêm parameter có default khi tương thích được.
- Không xóa/đổi tên API database đang được client dùng ngay.
- Có thể tạo API version mới rồi chuyển dần caller.
- Triển khai database object theo thứ tự tương thích.
- Chạy integration test với version ứng dụng đang tồn tại.

### 16.3. Invalid object và dependency

Khi object được tham chiếu thay đổi, stored program unit phụ thuộc có thể trở thành INVALID và cần recompile. Có thể kiểm tra:

~~~sql
SELECT object_name,
       object_type,
       status
FROM user_objects
WHERE status = 'INVALID'
ORDER BY object_type, object_name;
~~~

Compile lại object phù hợp bằng ALTER COMPILE hoặc quy trình quản trị schema. Không chạy compile toàn schema trên production tùy tiện khi chưa hiểu dependency và workload.

### 16.4. Đừng nhúng bí mật vào source PL/SQL

Không hard-code password, API key, token hoặc thông tin kết nối trong package body. Secret nên được quản lý bởi secret manager/credential store phù hợp. Database code chỉ nên nhận quyền và dữ liệu cần thiết, không lưu bí mật dạng plaintext trong source.

## 17. Lựa chọn kiến trúc theo tình huống

### Tình huống A: Tính tổng doanh thu theo khách hàng

Nên dùng SQL aggregate:

~~~sql
SELECT customer_id, SUM(amount)
FROM orders
GROUP BY customer_id;
~~~

Không cần PL/SQL loop qua từng order.

### Tình huống B: Cập nhật nhiều bảng trong một transaction

Có thể dùng procedure để đóng gói các DML gần dữ liệu, hoặc application transaction gọi nhiều repository. Chọn một tầng sở hữu transaction và bảo đảm các bước dùng cùng connection/session.

### Tình huống C: Gửi email sau khi đơn hàng được tạo

Application/worker nên gửi email sau commit. Database có thể ghi outbox event trong cùng transaction; không nên để trigger gửi email trực tiếp.

### Tình huống D: Nhiều ứng dụng cùng cần một quy tắc kiểm tra dữ liệu

Có thể đặt invariant ở constraint hoặc database API. Nếu quy tắc là dữ liệu toàn cục phải luôn đúng, database constraint thường là lựa chọn mạnh hơn. Nếu đó là chính sách của một ứng dụng cụ thể, service layer có thể phù hợp hơn.

### Tình huống E: Import hàng triệu dòng

Dùng SQL set-based hoặc direct/bulk load theo yêu cầu. Nếu cần logic theo lô, PL/SQL bulk processing hoặc application batch có thể phù hợp. Thiết kế checkpoint, commit chunk và idempotency để có thể chạy lại.

### Tình huống F: Workflow cần người phê duyệt

Application/workflow engine nên điều phối trạng thái dài hạn và tương tác người dùng. Database lưu trạng thái và bảo đảm invariant bằng constraint/API. Không giữ transaction mở trong lúc chờ phê duyệt.

## 18. Những lỗi thiết kế thường gặp

| Triệu chứng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Procedure chạy chậm khi xử lý nhiều hàng | Row-by-row SQL trong vòng lặp | Dùng SQL set-based hoặc bulk processing |
| Ứng dụng không rollback được toàn nghiệp vụ | Procedure tự COMMIT hoặc dùng connection khác | Xác định transaction owner và loại bỏ commit không cần thiết |
| Một SELECT gọi function rất chậm | Function truy vấn bảng lặp theo từng hàng | Dùng join/aggregate hoặc giảm số lần gọi |
| DML chạy xong nhưng ứng dụng báo thành công sai | Không kiểm tra SQL%ROWCOUNT | Kiểm tra số hàng bị tác động theo contract |
| Lỗi database bị che giấu | WHEN OTHERS rồi NULL | Ghi log có kiểm soát và RAISE lại |
| SQL injection trong PL/SQL | Nối input vào SQL động | Bind value, whitelist identifier, DBMS_ASSERT khi phù hợp |
| Stored procedure khó deploy | Không version hóa schema object | Dùng migration và kiểm thử tương thích |
| Trigger tạo side effect khó dự đoán | Logic workflow nằm ẩn trong trigger | Giữ trigger nhỏ; dùng outbox/service cho side effect |
| Commit chậm hoặc lock lâu | Transaction dài, gọi network trong transaction | Rút ngắn transaction và tách bước ngoài |
| Quy tắc ở app và database không thống nhất | Nhiều client tự triển khai cùng invariant | Đặt invariant ở constraint hoặc API chung |
| Database phụ thuộc dịch vụ ngoài | PL/SQL gọi dịch vụ trực tiếp trong luồng DML | Outbox, worker hoặc saga |
| Dùng PL/SQL cho phép tính đơn giản | Thủ tục hóa một biểu thức SQL | Để SQL thực hiện phép tính set-based |

## 19. Checklist xác định ranh giới SQL, PL/SQL và application

Trước khi quyết định nơi đặt logic, hãy hỏi:

1. Logic có thể diễn đạt bằng một câu SQL set-based không?
2. Có cần điều phối nhiều câu SQL gần dữ liệu trong một database session không?
3. Nhiều ứng dụng có cần dùng chung logic này không?
4. Quy tắc là invariant của dữ liệu hay chỉ là hành vi của một use case?
5. Có cần gọi API, gửi message, email hoặc tương tác người dùng không?
6. Ai sở hữu transaction và ai chịu trách nhiệm commit/rollback?
7. Tất cả statement có dùng cùng connection/session không?
8. Có SQL động, input không tin cậy hoặc quyền definer/invoker không?
9. Có nguy cơ context switch hoặc network round-trip quá nhiều không?
10. Logic có cần chạy trên database khác hoặc được deploy độc lập với schema không?
11. Có cần versioning, backward compatibility và integration test không?
12. Khi lỗi giữa chừng hoặc retry, dữ liệu và side effect có còn đúng không?

## 20. Bài thực hành có kiểm soát

Các bài thực hành dưới đây dùng bảng lab LAB_PL_SQL_ORDERS. Chỉ tạo object trong schema DEV/TEST được cấp quyền và xác nhận đúng PDB/service. Không chạy DDL hoặc DML mẫu trên bảng nghiệp vụ production.

### 20.1. Tạo dữ liệu lab

~~~sql
CREATE TABLE lab_plsql_orders (
    order_id    NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    amount      NUMBER(12, 2) NOT NULL,
    status      VARCHAR2(20 CHAR) NOT NULL
);

INSERT ALL
    INTO lab_plsql_orders VALUES (1, 101, 1000, 'NEW')
    INTO lab_plsql_orders VALUES (2, 101, 2000, 'NEW')
    INTO lab_plsql_orders VALUES (3, 102, 1500, 'PAID')
    INTO lab_plsql_orders VALUES (4, 103, 3000, 'NEW')
SELECT 1 FROM dual;

COMMIT;
~~~

### Bài 1 — SQL set-based và PL/SQL row-by-row

Viết một block cursor FOR LOOP để đổi tất cả đơn NEW thành REVIEW. Sau đó viết một câu UPDATE tương đương. So sánh độ dài code và cách database xử lý.

~~~sql
UPDATE lab_plsql_orders
SET status = 'REVIEW'
WHERE status = 'NEW';

ROLLBACK;
~~~

### Bài 2 — Tạo procedure kiểm tra trạng thái

Viết procedure mark_order_paid(p_order_id):
- Đọc trạng thái đơn hàng.
- Chỉ cho phép chuyển từ NEW sang PAID.
- Nếu không tồn tại, trả lỗi nghiệp vụ phù hợp.
- Nếu trạng thái không hợp lệ, trả lỗi khác.
- Không tự commit; để caller quyết định transaction.

### Bài 3 — Kiểm tra SQL%ROWCOUNT

Viết procedure cập nhật trạng thái với điều kiện:

~~~sql
UPDATE lab_plsql_orders
SET status = 'REVIEW'
WHERE order_id = p_order_id
  AND status = 'NEW';
~~~

Dùng SQL%ROWCOUNT để phân biệt cập nhật đúng một hàng, không tìm thấy đơn hoặc trạng thái không còn NEW.

### Bài 4 — So sánh function và join

Tạo function trả tên khách hàng theo customer ID (có thể tạo bảng khách hàng lab). Gọi function trong SELECT trên nhiều đơn hàng. Sau đó viết truy vấn JOIN tương đương. Quan sát số lần gọi và execution plan; giải thích khi nào function tiện và khi nào join phù hợp hơn.

### Bài 5 — JDBC transaction

Viết một method Java nhận Connection và gọi hai thao tác repository trên cùng connection. Tắt auto-commit ở tầng sở hữu transaction. Cố ý làm bước thứ hai thất bại rồi xác nhận bước đầu được rollback. Kiểm tra procedure được gọi không tự commit.

### Bài 6 — SQL injection và bind variable

Viết ví dụ SQL động không an toàn nối input vào WHERE. Sau đó sửa thành EXECUTE IMMEDIATE ... USING. Nếu input là tên bảng, dùng whitelist identifier và giải thích vì sao không thể bind tên bảng như một giá trị.

### Bài 7 — Outbox

Tạo bảng outbox lab. Viết procedure tạo đơn và ghi event outbox trong cùng transaction. Không gửi email trong procedure. Mô tả worker application đọc event đã commit, gửi thông báo và đánh dấu trạng thái idempotent.

### Bài 8 — Kiểm thử exception

Tạo một procedure phát sinh RAISE_APPLICATION_ERROR sau DML. Gọi từ SQL client với transaction chưa commit. Quan sát DML còn trong transaction hay đã rollback, rồi tự quyết định rollback. Thử lại với một procedure có COMMIT để thấy khác biệt transaction contract.

### Thu dọn dữ liệu lab

Chỉ khi xác nhận đúng object do mình tạo trong DEV/TEST và không có người khác sử dụng:

~~~sql
DROP TABLE lab_plsql_orders PURGE;
~~~

Nếu đã tạo thêm bảng hoặc package trong bài tập, xóa đúng object lab tương ứng theo dependency. DDL có implicit commit trong Oracle; không chạy trên production hoặc object ngoài phạm vi thực hành.

## 21. Câu hỏi ôn tập

**Câu 1.** SQL và PL/SQL khác nhau ở điểm cốt lõi nào?

**Đáp án:** SQL mô tả thao tác dữ liệu theo kiểu khai báo; PL/SQL bổ sung biến, điều kiện, vòng lặp, exception và chương trình con để điều phối xử lý.

**Câu 2.** Vì sao nên ưu tiên SQL set-based thay vì loop từng hàng?

**Đáp án:** SQL engine được tối ưu cho xử lý tập hợp; row-by-row có thể tạo nhiều lần chuyển giữa PL/SQL và SQL engine và nhiều công việc lặp.

**Câu 3.** Stored procedure có tự động nhanh hơn SQL gửi từ application không?

**Đáp án:** Không. Procedure có thể giảm network round-trip nhưng vẫn có thể viết row-by-row và tạo nhiều context switch. Cần đo execution plan và workload.

**Câu 4.** Context switch giữa PL/SQL engine và SQL engine có giống network round-trip không?

**Đáp án:** Không. Context switch diễn ra bên trong database; network round-trip là giao tiếp giữa application và database qua kết nối.

**Câu 5.** Khi nào nên dùng BULK COLLECT và FORALL?

**Đáp án:** Khi cần xử lý collection nhiều hàng và không thể biểu đạt hợp lý bằng một câu SQL set-based; bulk processing giảm số lần chuyển giữa PL/SQL và SQL engine.

**Câu 6.** Ai nên sở hữu transaction?

**Đáp án:** Có thể là application hoặc một database API được thiết kế rõ contract. Không để nhiều tầng cùng commit tùy tiện; tất cả bước cần nguyên tử phải dùng cùng transaction/session.

**Câu 7.** Vì sao procedure dùng chung thường không nên COMMIT?

**Đáp án:** COMMIT bên trong có thể commit cả thay đổi khác của caller trong cùng session, làm caller mất khả năng rollback toàn bộ use case.

**Câu 8.** Khi nào nên đặt invariant ở constraint?

**Đáp án:** Khi quy tắc có thể diễn đạt bằng constraint như NOT NULL, CHECK, UNIQUE hoặc foreign key và phải đúng bất kể client nào ghi dữ liệu.

**Câu 9.** Tại sao không nên gửi email trong trigger?

**Đáp án:** Email là side effect ngoài transaction Oracle; email có thể đã gửi dù transaction rollback, hoặc lỗi email có thể làm DML thất bại ngoài ý muốn. Outbox/worker giúp tách side effect sau commit.

**Câu 10.** Bind variable bảo vệ điều gì trong SQL động?

**Đáp án:** Giá trị input được truyền như dữ liệu thay vì cú pháp SQL, giúp giảm SQL injection và hỗ trợ cursor reuse. Identifier cần whitelist/xác thực riêng.

**Câu 11.** Definer rights và invoker rights khác nhau thế nào?

**Đáp án:** Definer rights thực thi theo quyền của owner/definer; invoker rights sử dụng quyền của caller theo quy tắc Oracle. Chọn theo API và mô hình bảo mật.

**Câu 12.** WHEN OTHERS THEN NULL có rủi ro gì?

**Đáp án:** Nó nuốt lỗi và khiến caller tưởng xử lý thành công. Cần xử lý có chủ đích, ghi nhận phù hợp và thường truyền lại exception bằng RAISE.

**Câu 13.** Function gọi từ SQL có nên thực hiện DML tùy tiện không?

**Đáp án:** Không. SQL-callable function có các giới hạn về side effect và transaction; nên giữ function thuần tính toán/đọc dữ liệu phù hợp và không dùng nó thay join hoặc aggregate.

**Câu 14.** Outbox pattern giải quyết điều gì?

**Đáp án:** Nó ghi dữ liệu nghiệp vụ và event trong cùng transaction database; worker gửi event sau commit. Consumer vẫn cần idempotency vì có thể nhận lại event.

## Kết luận

**SQL, PL/SQL và mã ứng dụng có vai trò bổ sung cho nhau.** SQL nên xử lý truy vấn và thay đổi dữ liệu theo tập hợp; PL/SQL nên điều phối các bước gần dữ liệu, đóng gói database API và xử lý logic cần dùng chung trong Oracle; ứng dụng nên sở hữu giao tiếp người dùng, API, xác thực, tích hợp dịch vụ và workflow ở cấp hệ thống.

Khi thiết kế, ưu tiên câu SQL set-based thay cho vòng lặp row-by-row; dùng bulk processing khi cần thao tác nhiều hàng qua collection. Xác định rõ tầng sở hữu transaction, tránh procedure tự commit ngoài contract và bảo đảm các bước cần nguyên tử dùng cùng connection/session. Giữ side effect bên ngoài như email hoặc message ở tầng ứng dụng/worker, có thể dùng outbox để ghi event cùng transaction database. Cuối cùng, kiểm thử hiệu năng, quyền, exception, concurrency và tương thích phiên bản trước khi triển khai logic PL/SQL cùng application release.

## Tài liệu Oracle tham khảo

- [Oracle Database 19c PL/SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/index.html): cấu trúc block, biến, control flow, procedure, function, package và exception.
- [Oracle Database 19c SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/index.html): câu lệnh SQL, query, DML và SQL động.
- [Oracle Database 19c PL/SQL Optimization and Tuning](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/plsql-optimization-and-tuning.html): bulk SQL, context switching và tối ưu PL/SQL.
- [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_ASSERT](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_ASSERT.html): xác thực SQL identifier trong các tình huống SQL động phù hợp.
- [Oracle Database 19c PL/SQL Language Reference — Invoker's Rights and Definer's Rights](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/invokers-rights-and-definers-rights-authid-property.html): AUTHID DEFINER và AUTHID CURRENT_USER.

