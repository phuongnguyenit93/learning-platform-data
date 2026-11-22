# Vai trò stored procedure/function và ranh giới với mã Java

MySQL stored program là mã SQL được lưu trong database và thực thi trên server. Hai loại routine thường dùng là **stored procedure** và **stored function**. Procedure được gọi bằng `CALL`, có thể nhận tham số `IN`, `OUT`, `INOUT` và có thể trả result set. Function trả về một giá trị vô hướng và có thể được gọi trong biểu thức SQL như một hàm tích hợp.

Stored routine phù hợp khi một phần logic gắn chặt với dữ liệu và cần được dùng thống nhất từ nhiều client. Java vẫn nên giữ vai trò điều phối use case, xác thực nghiệp vụ ở cấp ứng dụng, gọi dịch vụ bên ngoài, quản lý API và kết nối các thành phần. Đưa mọi logic vào database làm tăng coupling với MySQL, khó kiểm thử/triển khai độc lập và có thể tạo nút thắt CPU hoặc concurrency ở database. Ngược lại, để Java tự thực hiện hàng loạt bước đọc-sửa-ghi rời rạc có thể tăng round-trip và làm yếu tính nhất quán nếu transaction boundary không được thiết kế đúng.

Mục tiêu là chọn đúng ranh giới: đặt thao tác dữ liệu cần gần database vào routine khi lợi ích rõ ràng; giữ orchestration và logic không phụ thuộc database ở Java; xác định rõ bên nào sở hữu transaction.

## 1. Stored program là gì?

Stored program là chương trình được lưu trong schema MySQL thay vì nằm hoàn toàn trong source code ứng dụng. MySQL hỗ trợ một số loại stored program như:

- **Stored procedure:** một routine được gọi bằng `CALL`; có thể nhận nhiều tham số, thực hiện nhiều câu lệnh và trả một hoặc nhiều result set.
- **Stored function:** một routine trả về một giá trị và có thể xuất hiện trong biểu thức SQL, ví dụ trong `SELECT`, `WHERE` hoặc biểu thức tính toán.
- **Trigger:** routine được tự động kích hoạt khi một sự kiện DML xảy ra trên bảng.
- **Event:** tác vụ được MySQL Event Scheduler chạy theo lịch.

Bài này tập trung vào procedure/function và cách phân chia trách nhiệm với Java. Trigger và event có cách kích hoạt, vòng đời và rủi ro vận hành riêng; không nên dùng chúng chỉ để thay thế một lời gọi ứng dụng mà chưa xác định rõ yêu cầu.

Stored routine được lưu dưới dạng metadata trong database. Khi ứng dụng gọi routine, MySQL thực thi phần thân routine trên server, dùng connection/session hiện tại và quyền theo `SQL SECURITY` của routine.

## 2. Stored procedure và stored function khác nhau thế nào?

| Tiêu chí | Stored procedure | Stored function |
| --- | --- | --- |
| Cách gọi | `CALL procedure_name(...)` | Dùng như biểu thức SQL, ví dụ `SELECT function_name(...)` |
| Giá trị trả về | Có thể trả result set, tham số `OUT`/`INOUT` hoặc nhiều kết quả | Phải trả một giá trị qua `RETURN` |
| Tham số | `IN`, `OUT`, `INOUT` | Chỉ tham số đầu vào `IN` |
| Mục đích điển hình | Thực hiện một thao tác hoặc quy trình dữ liệu | Tính toán một giá trị vô hướng |
| Dùng trong `SELECT`/`WHERE` | Không thể đặt procedure trực tiếp như một biểu thức | Có thể gọi function trong biểu thức SQL |
| Điều khiển transaction | Có thể chứa lệnh điều khiển transaction, nhưng phải phối hợp rõ với transaction của caller | Không được dùng các lệnh bắt đầu/kết thúc transaction như `START TRANSACTION`, `COMMIT`, `ROLLBACK` |
| Result set | Có thể trả result set trực tiếp | Không được trả result set trực tiếp |
| Dynamic SQL | Stored procedure có thể dùng prepared statement động trong phạm vi được hỗ trợ | Stored function không được dùng câu lệnh prepared statement động |

Procedure phù hợp với hành động có nhiều bước hoặc cần trả một tập hàng. Function phù hợp với phép tính trả về một giá trị có ngữ nghĩa rõ ràng. Không chọn function chỉ vì muốn cú pháp gọi ngắn hơn; function được gọi trong SQL có thể chạy nhiều lần theo số hàng và tạo chi phí lớn.

## 3. Khi nào nên cân nhắc stored procedure?

Procedure có thể hữu ích khi:

1. Một thao tác dữ liệu gồm nhiều câu SQL cần thực thi gần database.
2. Nhiều ứng dụng hoặc service cần dùng chung một quy trình dữ liệu đã chuẩn hóa.
3. Muốn cấp quyền `EXECUTE` trên routine mà không cấp quyền trực tiếp rộng trên bảng nền.
4. Cần trả nhiều hàng hoặc nhiều tập kết quả cho caller.
5. Muốn gom một số round-trip thành một lời gọi database.
6. Quy trình có thể diễn đạt rõ bằng SQL và không cần gọi dịch vụ ngoài trong lúc xử lý.

Ví dụ, một procedure có thể nhận `customer_id`, kiểm tra điều kiện dữ liệu, ghi một yêu cầu và trả thông tin kết quả. Nếu quy trình cần gửi email, gọi cổng thanh toán hoặc gọi HTTP, các hành động đó vẫn thuộc orchestration ở Java hoặc một worker khác.

Procedure không tự động nhanh hơn Java. Nếu procedure thực hiện cùng số lần đọc/ghi và cùng execution plan, chi phí database vẫn tồn tại. Lợi ích có thể đến từ giảm round-trip, giảm truyền dữ liệu trung gian hoặc thực hiện set-based operation gần dữ liệu.

## 4. Khi nào nên cân nhắc stored function?

Function phù hợp với phép tính vô hướng có đầu vào/đầu ra rõ ràng, ví dụ:

- Chuẩn hóa hoặc tính một giá trị từ tham số.
- Tính một biểu thức nghiệp vụ nhỏ, ổn định và được tái sử dụng trong SQL.
- Trả về một giá trị tổng hợp đơn giản khi cách gọi trong biểu thức thực sự thuận tiện.
- Đóng gói phép tính SQL để nhiều truy vấn dùng cùng định nghĩa.

Ví dụ function tính tổng tiền của một đơn hàng:

```sql
DELIMITER //

CREATE FUNCTION fn_order_total(p_order_id BIGINT UNSIGNED)
RETURNS DECIMAL(13, 2)
READS SQL DATA
SQL SECURITY INVOKER
BEGIN
    DECLARE v_total DECIMAL(13, 2);

    SELECT COALESCE(SUM(oi.quantity * oi.unit_price), 0.00)
    INTO v_total
    FROM order_items AS oi
    WHERE oi.order_id = p_order_id;

    RETURN v_total;
END//

DELIMITER ;
```

Gọi function:

```sql
SELECT fn_order_total(1001) AS order_total;
```

Function trả một giá trị `DECIMAL`, vì vậy có thể dùng trong biểu thức SQL. Nếu cần trả nhiều cột hoặc nhiều hàng, hãy dùng procedure hoặc truy vấn `SELECT` thông thường.

## 5. Ví dụ schema dùng trong bài

Các ví dụ tiếp theo dùng bảng đơn hàng và chi tiết đơn hàng:

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer_created (customer_id, created_at)
) ENGINE=InnoDB;

CREATE TABLE order_items (
    order_item_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(13, 2) NOT NULL,
    PRIMARY KEY (order_item_id),
    KEY idx_order_items_order (order_id),
    CONSTRAINT fk_order_items_order
        FOREIGN KEY (order_id) REFERENCES orders (order_id)
) ENGINE=InnoDB;
```

Trong hệ thống thật, các bảng có thể có thêm ràng buộc, currency, discount, tax và quy tắc làm tròn. Ví dụ chỉ minh họa ranh giới gọi routine.

Các khối SQL có `BEGIN ... END` thường chứa dấu chấm phẩy bên trong. Khi nhập bằng MySQL command-line client, dùng lệnh client `DELIMITER` để tạm đổi ký tự kết thúc, như `//`, rồi khôi phục `DELIMITER ;` sau khi tạo routine. `DELIMITER` không phải câu lệnh SQL gửi đến server; khi tạo routine qua JDBC hoặc migration framework, gửi câu `CREATE PROCEDURE`/`CREATE FUNCTION` theo cách công cụ đó yêu cầu, không gửi dòng `DELIMITER`.

## 6. Procedure với tham số IN

`IN` là tham số đầu vào. Procedure có thể đọc giá trị này nhưng không trả thay đổi của biến cho caller:

```sql
DELIMITER //

CREATE PROCEDURE sp_get_customer_orders(
    IN p_customer_id BIGINT UNSIGNED,
    IN p_limit INT
)
BEGIN
    SELECT
        order_id,
        status,
        created_at
    FROM orders
    WHERE customer_id = p_customer_id
    ORDER BY created_at DESC, order_id DESC
    LIMIT p_limit;
END//

DELIMITER ;
```

Gọi:

```sql
CALL sp_get_customer_orders(42, 20);
```

Procedure trả một result set gồm các hàng đơn hàng. Caller cần đọc và đóng result set trước khi tái sử dụng connection.

## 7. Procedure với tham số OUT và INOUT

`OUT` dùng để trả một giá trị cho caller. Trong thân procedure, tham số được gán; giá trị đầu vào của biến truyền vào không được dùng như giá trị ban đầu.

```sql
DELIMITER //

CREATE PROCEDURE sp_count_customer_orders(
    IN p_customer_id BIGINT UNSIGNED,
    OUT p_order_count BIGINT
)
BEGIN
    SELECT COUNT(*)
    INTO p_order_count
    FROM orders
    WHERE customer_id = p_customer_id;
END//

DELIMITER ;
```

Gọi trong SQL client:

```sql
CALL sp_count_customer_orders(42, @order_count);
SELECT @order_count AS order_count;
```

`INOUT` vừa nhận giá trị ban đầu vừa trả giá trị đã thay đổi:

```sql
DELIMITER //

CREATE PROCEDURE sp_add_tax(
    INOUT p_amount DECIMAL(13, 2),
    IN p_tax_rate DECIMAL(7, 4)
)
BEGIN
    SET p_amount = ROUND(p_amount * (1 + p_tax_rate), 2);
END//

DELIMITER ;
```

```sql
SET @amount = 100.00;
CALL sp_add_tax(@amount, 0.1000);
SELECT @amount AS amount_with_tax;
```

Biến `@amount` là user-defined session variable của connection hiện tại. Trong ứng dụng, driver hỗ trợ đăng ký tham số OUT/INOUT để nhận kết quả có kiểu dữ liệu rõ ràng.

## 8. Biến cục bộ và phạm vi trong routine

Biến cục bộ được khai báo bằng `DECLARE` bên trong một block `BEGIN ... END`. Các lệnh khai báo phải đứng đầu block, trước câu lệnh thực thi thông thường:

```sql
DELIMITER //

CREATE PROCEDURE sp_order_summary(
    IN p_order_id BIGINT UNSIGNED,
    OUT p_item_count BIGINT,
    OUT p_total DECIMAL(13, 2)
)
BEGIN
    SELECT
        COUNT(*),
        COALESCE(SUM(quantity * unit_price), 0.00)
    INTO p_item_count, p_total
    FROM order_items
    WHERE order_id = p_order_id;
END//

DELIMITER ;
```

`v_status` chỉ tồn tại trong block routine. Tên biến nên có prefix nhất quán để phân biệt tham số (`p_`), biến cục bộ (`v_`) và cột bảng. Điều này tránh nhầm lẫn khi tên tham số trùng tên cột trong điều kiện SQL.

## 9. Function trả về một giá trị

Function cần khai báo kiểu trả về bằng `RETURNS` và kết thúc bằng `RETURN` trên mọi nhánh thực thi có thể đi tới:

```sql
DELIMITER //

CREATE FUNCTION fn_line_total(
    p_quantity INT,
    p_unit_price DECIMAL(13, 2)
)
RETURNS DECIMAL(13, 2)
DETERMINISTIC
NO SQL
BEGIN
    RETURN ROUND(p_quantity * p_unit_price, 2);
END//

DELIMITER ;
```

Gọi:

```sql
SELECT fn_line_total(3, 12500.00) AS line_total;
```

`DETERMINISTIC` khai báo rằng cùng đầu vào sẽ cho cùng kết quả; `NO SQL` khai báo routine không đọc/ghi dữ liệu SQL. Đây là đặc tính do người viết khai báo và phải đúng với phần thân thực tế. Không gắn `DETERMINISTIC` cho function phụ thuộc dữ liệu bảng, thời gian hiện tại, trạng thái session hoặc nguồn thay đổi khác.

## 10. Các đặc tính SQL DATA ACCESS

Routine có thể khai báo mức truy cập SQL:

| Đặc tính | Ý nghĩa khai báo |
| --- | --- |
| `NO SQL` | Routine không chứa câu SQL truy cập dữ liệu |
| `CONTAINS SQL` | Có câu SQL nhưng không đọc/ghi dữ liệu |
| `READS SQL DATA` | Có thể đọc dữ liệu SQL |
| `MODIFIES SQL DATA` | Có thể thay đổi dữ liệu SQL |

Ví dụ function tính toán thuần có thể khai báo `NO SQL`; function đọc bảng tổng tiền có thể khai báo `READS SQL DATA`; procedure ghi đơn hàng có thể khai báo `MODIFIES SQL DATA`.

Các đặc tính này mô tả hành vi mà routine cam kết. MySQL không phân tích toàn bộ thân routine để bảo đảm khai báo luôn đúng. Khai báo sai làm người vận hành và công cụ dựa trên metadata hiểu nhầm routine.

## 11. Dùng function trong SELECT có thể tạo chi phí theo số hàng

Function có thể xuất hiện trong biểu thức của truy vấn:

```sql
SELECT
    o.order_id,
    fn_order_total(o.order_id) AS order_total
FROM orders AS o
WHERE o.customer_id = 42;
```

Nếu truy vấn trả về 10.000 đơn hàng, function có thể được gọi cho từng hàng. Nếu function lại chạy một `SELECT` bên trong để tính tổng chi tiết, ứng dụng có thể vô tình tạo mô hình N+1 ở phía database: một truy vấn ngoài cộng với nhiều lần truy vấn nội bộ của function.

Với báo cáo nhiều hàng, truy vấn set-based thường phù hợp hơn:

```sql
SELECT
    o.order_id,
    COALESCE(SUM(oi.quantity * oi.unit_price), 0.00) AS order_total
FROM orders AS o
LEFT JOIN order_items AS oi
  ON oi.order_id = o.order_id
WHERE o.customer_id = 42
GROUP BY o.order_id;
```

Function có thể tiện cho một giá trị đơn lẻ hoặc một biểu thức nhỏ. Khi xử lý tập dữ liệu lớn, hãy đo số lần gọi, actual rows và execution plan; đừng mặc định routine được lưu trong database thì sẽ nhanh hơn JOIN/aggregate.

## 12. Vì sao procedure/function không thay thế lẫn nhau?

Procedure được thiết kế cho một hành động hoặc quy trình; function được thiết kế để trả một giá trị trong biểu thức. Không thể gọi procedure trực tiếp trong `SELECT` như function:

```sql
-- Hợp lệ nếu fn_line_total đã được tạo:
SELECT fn_line_total(2, 100.00);

-- Không hợp lệ: procedure không phải biểu thức SQL:
-- SELECT sp_count_customer_orders(42);
```

Procedure có thể trả result set và nhiều tham số OUT. Function trả một giá trị và không trả result set trực tiếp. Nếu cần trả nhiều cột/hàng, cân nhắc procedure hoặc viết SELECT trực tiếp.

Không nên tạo function chỉ để bọc một truy vấn đơn giản mà caller có thể viết rõ ràng. Routine có giá trị khi nó tạo ra hợp đồng dùng chung, giảm lặp logic hoặc cung cấp quyền truy cập có kiểm soát.

## 13. Ranh giới trách nhiệm: MySQL routine và Java

Một cách phân chia thường hợp lý:

| Trách nhiệm | Nơi phù hợp thường gặp | Lý do |
| --- | --- | --- |
| HTTP/API, authentication và authorization theo người dùng | Java/service | Gắn với giao thức, identity và policy ứng dụng |
| Điều phối nhiều dịch vụ, message broker, email, thanh toán | Java/service hoặc worker | MySQL routine không nên gọi mạng ngoài hoặc giữ transaction chờ phản hồi |
| Quy tắc nghiệp vụ nhiều bước liên quan trực tiếp dữ liệu trong cùng database | Java transaction hoặc procedure, tùy kiến trúc | Cần chọn một nơi sở hữu luồng và transaction rõ ràng |
| Truy vấn set-based, aggregate, JOIN lớn | SQL trực tiếp hoặc routine | Database tối ưu thao tác gần dữ liệu |
| Phép tính scalar nhỏ, ổn định, cần dùng trong SQL | Function hoặc biểu thức SQL | Có thể tái sử dụng cùng ngữ nghĩa |
| Quy tắc domain phức tạp, thay đổi thường xuyên | Java domain/service layer | Dễ unit test, review, triển khai và quan sát theo ứng dụng |
| Ràng buộc dữ liệu cơ bản | Constraint trong schema | Được bảo vệ cho mọi client, không phụ thuộc caller |
| Logging, tracing, retry policy và orchestration | Java/platform | Cần context request và hệ thống quan sát của ứng dụng |

Đây là hướng dẫn lựa chọn, không phải luật cứng. Một hệ thống có nhiều client ghi trực tiếp vào database có thể cần nhiều logic tập trung ở stored procedure. Một hệ thống chỉ có một service Java quản lý schema có thể giữ hầu hết orchestration trong Java và chỉ dùng SQL cho truy vấn/ghi dữ liệu.

## 14. Tránh chia một use case thành nhiều round-trip không cần thiết

Giả sử một use case cần đọc trạng thái đơn hàng, kiểm tra điều kiện và cập nhật trạng thái. Nếu Java thực hiện nhiều câu SQL tuần tự, mỗi câu có thể tạo một round-trip:

```text
Java -> SELECT order
Java -> validate
Java -> UPDATE order
Java -> INSERT audit row
```

Nếu các bước cần cùng trạng thái dữ liệu, Java phải giữ cùng connection và transaction trong suốt quá trình. Một procedure có thể gom các bước SQL thành một lần gọi, giảm round-trip và tập trung quy tắc cập nhật.

Tuy nhiên, nếu Java cần gọi một dịch vụ ngoài giữa các bước, không nên chuyển toàn bộ luồng vào procedure. Hãy xác định phần database atomic, commit, rồi phát outbox/event để worker xử lý side effect.

Không tối ưu round-trip bằng cách tạo một procedure rất lớn không có ranh giới rõ. Routine cần có input/output, lỗi và hợp đồng ổn định.

## 15. Ai sở hữu transaction: Java hay procedure?

Một quy tắc quan trọng: **một đơn vị nghiệp vụ nên có một chủ sở hữu transaction rõ ràng**.

Có hai mô hình phổ biến:

### 15.1. Java sở hữu transaction

Java lấy connection, bắt đầu transaction, gọi procedure thực hiện các câu DML nhưng procedure không tự commit/rollback. Java quyết định commit khi toàn bộ use case thành công hoặc rollback khi có lỗi.

Mô hình này phù hợp khi transaction còn bao gồm các câu SQL khác ngoài procedure hoặc nhiều routine cần tham gia cùng một đơn vị công việc.

### 15.2. Procedure sở hữu transaction

Procedure bắt đầu transaction, thực hiện toàn bộ thao tác database và commit/rollback bên trong. Java gọi procedure như một lệnh nghiệp vụ độc lập và không mở transaction bao quanh với kỳ vọng tự quản lý commit.

Mô hình này phù hợp khi procedure là ranh giới hoàn chỉnh, không cần ghép với các thao tác transaction khác do Java quản lý.

Không để cả Java và procedure cùng tự ý `COMMIT`. Nếu Java đã mở transaction rồi procedure chạy `START TRANSACTION`, MySQL có thể commit transaction đang hoạt động trước khi bắt đầu transaction mới. Một `COMMIT` trong procedure cũng có thể commit các thay đổi trước đó của caller trên cùng connection.

Stored procedure có thể chứa điều khiển transaction; stored function và trigger không được dùng các lệnh transaction control như `COMMIT`, `ROLLBACK` hoặc `START TRANSACTION`. Hãy xác định transaction owner trước khi thiết kế routine.

## 16. Ví dụ procedure sở hữu transaction

Ví dụ procedure ghi một audit event và cập nhật trạng thái đơn hàng. Bảng dùng InnoDB:

```sql
CREATE TABLE order_audit (
    audit_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    old_status VARCHAR(20) NOT NULL,
    new_status VARCHAR(20) NOT NULL,
    changed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (audit_id),
    KEY idx_order_audit_order (order_id)
) ENGINE=InnoDB;
```

Procedure có handler rollback khi SQL exception:

```sql
DELIMITER //

CREATE PROCEDURE sp_mark_order_paid(IN p_order_id BIGINT UNSIGNED)
MODIFIES SQL DATA
SQL SECURITY INVOKER
BEGIN
    DECLARE v_old_status VARCHAR(20);
    DECLARE v_found BOOLEAN DEFAULT TRUE;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_found = FALSE;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    SELECT status
    INTO v_old_status
    FROM orders
    WHERE order_id = p_order_id
    FOR UPDATE;

    IF NOT v_found THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Order does not exist';
    END IF;

    IF v_old_status <> 'pending' THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Order is not pending';
    END IF;

    UPDATE orders
    SET status = 'paid'
    WHERE order_id = p_order_id;

    INSERT INTO order_audit (order_id, old_status, new_status)
    VALUES (p_order_id, v_old_status, 'paid');

    COMMIT;
END//

DELIMITER ;
```

Gọi:

```sql
CALL sp_mark_order_paid(1001);
```

Procedure này sở hữu transaction. Caller không nên bọc lời gọi bằng một transaction lớn hơn nếu mong muốn kiểm soát commit/rollback ở Java. Handler `NOT FOUND` đặt cờ khi không tìm thấy đơn; câu `SIGNAL` sau đó tạo lỗi nghiệp vụ, được handler `SQLEXCEPTION` rollback và ném lại cho caller. Ví dụ minh họa transaction boundary và handler exception, không phải mẫu duy nhất cho mọi schema.

Nếu quy trình cần gọi payment gateway, hãy thực hiện phần database transaction phù hợp, ghi outbox event rồi commit. Worker xử lý gateway sau commit; procedure không nên giữ khóa trong lúc chờ mạng.

## 17. Error handling trong routine và ở Java

MySQL hỗ trợ `DECLARE ... HANDLER` để xử lý điều kiện trong stored program. Một handler có thể xử lý exception, warning, `NOT FOUND` hoặc SQLSTATE cụ thể.

Ví dụ handler tổng quát:

```sql
DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
    ROLLBACK;
    RESIGNAL;
END;
```

`EXIT` rời khỏi block hiện tại sau khi handler chạy. `CONTINUE` xử lý điều kiện rồi tiếp tục câu lệnh tiếp theo trong block. `RESIGNAL` ném lại lỗi hiện tại để caller vẫn nhận được lỗi SQL.

Không bắt mọi lỗi rồi trả về một giá trị thành công giả. Nếu routine nuốt exception, Java có thể tưởng thao tác đã thành công và commit hoặc trả response sai.

Ở Java, cần phân loại lỗi SQLSTATE/vendor code, rollback nếu ứng dụng sở hữu transaction, ghi log có correlation/request ID và chỉ retry lỗi tạm thời phù hợp. Deadlock có thể yêu cầu retry toàn bộ transaction; lỗi validation hoặc duplicate key thường cần xử lý nghiệp vụ thay vì retry mù quáng.

## 18. Gọi stored procedure từ Java bằng JDBC

Dùng `CallableStatement` và bind tham số, không nối chuỗi SQL từ input:

```java
String sql = "{call app_db.sp_count_customer_orders(?, ?)}";

try (CallableStatement statement = connection.prepareCall(sql)) {
    statement.setLong(1, customerId);
    statement.registerOutParameter(2, Types.BIGINT);

    statement.execute();

    long orderCount = statement.getLong(2);
    // Dùng orderCount trong use case.
}
```

Với procedure trả result set, đọc result set từ `CallableStatement`:

```java
String sql = "{call app_db.sp_get_customer_orders(?, ?)}";

try (CallableStatement statement = connection.prepareCall(sql)) {
    statement.setLong(1, customerId);
    statement.setInt(2, 20);

    boolean hasResultSet = statement.execute();
    if (hasResultSet) {
        try (ResultSet rs = statement.getResultSet()) {
            while (rs.next()) {
                long orderId = rs.getLong("order_id");
                String status = rs.getString("status");
                // Map dữ liệu sang object ở tầng repository.
            }
        }
    }
}
```

Procedure có thể trả nhiều result set hoặc update count. Khi routine có nhiều kết quả, JDBC caller cần lặp `getMoreResults()` và kiểm tra update count cho đến khi hết; đồng thời đóng mọi result set trước khi tái sử dụng connection. OUT parameter thường được đọc sau khi các result set đã được xử lý theo yêu cầu của driver.

Tên schema trong lời gọi giúp tránh phụ thuộc vào `USE` hoặc default database của connection pool.

## 19. Gọi stored function từ Java bằng PreparedStatement

Function được gọi như một biểu thức SQL thông thường:

```java
String sql = "SELECT app_db.fn_line_total(?, ?) AS line_total";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setInt(1, quantity);
    statement.setBigDecimal(2, unitPrice);

    try (ResultSet rs = statement.executeQuery()) {
        if (rs.next()) {
            BigDecimal lineTotal = rs.getBigDecimal("line_total");
        }
    }
}
```

Bind parameter giữ kiểu dữ liệu rõ ràng và giảm nguy cơ SQL injection. Không nối trực tiếp giá trị người dùng vào câu `SELECT` hoặc tên routine động. Tên routine/schema thường phải là identifier cố định do ứng dụng kiểm soát; placeholder JDBC dành cho giá trị, không thay thế tên bảng hoặc tên cột.

## 20. Java sở hữu transaction khi gọi procedure

Nếu procedure chỉ thực hiện DML và không tự `START TRANSACTION`/`COMMIT`, Java có thể quản lý transaction:

```java
try (Connection connection = dataSource.getConnection()) {
    boolean previousAutoCommit = connection.getAutoCommit();
    connection.setAutoCommit(false);

    try {
        try (CallableStatement statement = connection.prepareCall(
                "{call app_db.sp_update_order_details(?, ?)}")) {
            statement.setLong(1, orderId);
            statement.setString(2, newStatus);
            statement.execute();
        }

        // Các câu SQL khác cùng use case chạy trên connection này.
        connection.commit();
    } catch (SQLException | RuntimeException ex) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            ex.addSuppressed(rollbackError);
        }
        throw ex;
    } finally {
        try {
            connection.setAutoCommit(previousAutoCommit);
        } catch (SQLException resetError) {
            // Ghi log; pool có thể cần loại bỏ connection không reset được.
        }
    }
}
```

Ví dụ trên giả định procedure không tự commit/rollback và mọi câu lệnh chạy trên cùng connection. Trong ứng dụng thực tế, nên dùng transaction manager của framework nếu có; tránh tự viết nhiều lớp quản lý transaction chồng lấn.

Nếu connection bị mất trong lúc gửi `COMMIT`, Java có thể không biết transaction đã commit hay chưa. Dùng idempotency key hoặc mã nghiệp vụ duy nhất để tra cứu kết quả trước khi thử lại. Không tạo request mới với key khác rồi thực hiện lại mù quáng.

## 21. Quyền EXECUTE và SQL SECURITY

Stored routine có thể chạy theo quyền của definer hoặc invoker:

- `SQL SECURITY DEFINER`: kiểm tra quyền đối với đối tượng nền theo tài khoản định nghĩa routine.
- `SQL SECURITY INVOKER`: kiểm tra quyền theo người gọi routine.

Mặc định của routine là `DEFINER` nếu không chỉ định. Ví dụ tạo procedure với invoker:

```sql
CREATE PROCEDURE sp_read_customer_summary(IN p_customer_id BIGINT UNSIGNED)
SQL SECURITY INVOKER
READS SQL DATA
BEGIN
    SELECT customer_id, customer_name, status
    FROM customers
    WHERE customer_id = p_customer_id;
END;
```

Cấp quyền gọi procedure:

```sql
GRANT EXECUTE ON PROCEDURE app_db.sp_read_customer_summary
TO 'app_runtime'@'%';
```

Với `DEFINER`, ứng dụng có thể chỉ cần quyền `EXECUTE` trên routine thay vì quyền trực tiếp trên mọi bảng nền, tùy cách routine được tạo và quyền definer. Đây là một cách tạo API dữ liệu hẹp. Definer cần được quản lý như một principal bảo mật: quyền tối thiểu, tài khoản tồn tại và quy trình migration không để routine phụ thuộc vào tài khoản cá nhân.

Không cấp quyền `EXECUTE` rộng trên mọi routine nếu ứng dụng chỉ cần một số thao tác. Kiểm tra quyền bằng đúng user/role runtime, không chỉ bằng tài khoản DBA.

## 22. Stored routine và SQL injection

Routine không tự động loại bỏ SQL injection. Nếu procedure ghép chuỗi input vào dynamic SQL, nó vẫn có thể tạo lỗ hổng:

```sql
-- Không an toàn: nối input trực tiếp vào câu SQL động.
-- SET @sql = CONCAT('SELECT ... WHERE name = ''', p_name, '''');
```

Ưu tiên static SQL với parameter routine. Ở Java, dùng `PreparedStatement`/`CallableStatement` và bind giá trị. Nếu procedure thực sự cần dynamic SQL, dùng prepared statement, kiểm soát identifier bằng allowlist và không cho input tự do quyết định tên bảng/cột.

Placeholder chỉ bind giá trị, không bind identifier. Ví dụ `ORDER BY ?` không có nghĩa MySQL sẽ sắp xếp theo tên cột do người dùng truyền; nó thường được hiểu là một giá trị biểu thức. Hãy ánh xạ lựa chọn sort của người dùng qua danh sách identifier được phép ở ứng dụng.

## 23. Đặc tính DETERMINISTIC và binary logging

Stored function có thể khai báo `DETERMINISTIC` hoặc `NOT DETERMINISTIC`, cùng đặc tính SQL data access. `DETERMINISTIC` nghĩa là cùng đầu vào luôn cho cùng kết quả trong cùng điều kiện; function phụ thuộc bảng, `NOW()`, `RAND()`, biến session hoặc trạng thái thay đổi thường không nên khai báo deterministic.

Khi binary logging được bật, việc tạo function có thể chịu điều kiện về khai báo tính xác định/quyền tạo routine tùy cấu hình, chẳng hạn `log_bin_trust_function_creators`. Không khai báo `DETERMINISTIC` giả chỉ để vượt kiểm tra. DBA cần đánh giá replication/binlog format, quyền tạo routine và tính đúng đắn của routine.

Các đặc tính `DETERMINISTIC`, `NO SQL`, `READS SQL DATA` là metadata do người viết cam kết; MySQL không chứng minh toàn bộ logic thực sự thỏa các khai báo đó. Cấu hình và quy định cụ thể phụ thuộc phiên bản MySQL.

## 24. Những giới hạn quan trọng của stored function

Stored function bị giới hạn hơn procedure vì được gọi như biểu thức SQL:

- Phải trả một giá trị scalar qua `RETURN`.
- Không trả result set trực tiếp.
- Không dùng transaction control như `START TRANSACTION`, `COMMIT` hoặc `ROLLBACK`.
- Không dùng prepared statement động (`PREPARE`/`EXECUTE`).
- Không được gọi stored procedure theo cách dùng `CALL` từ function.
- Không được thay đổi bảng đã được statement gọi function sử dụng theo các hạn chế của MySQL.
- Có thể bị gọi nhiều lần trong một truy vấn; function đọc dữ liệu có thể tạo chi phí lớn.

Trigger có một số giới hạn tương tự function, nên không nên giả định có thể dùng mọi khả năng của procedure bên trong function/trigger.

## 25. Quản lý routine như schema code

Stored routine là một phần của schema và cần được quản lý như code:

1. Lưu `CREATE PROCEDURE`/`CREATE FUNCTION` trong source control.
2. Triển khai bằng migration có thứ tự và có thể tái lập.
3. Đặt tên có quy ước, ví dụ `sp_` cho procedure và `fn_` cho function.
4. Ghi rõ input, output, lỗi, quyền và transaction owner.
5. Review SQL, access path và các trường hợp NULL/duplicate/biên.
6. Kiểm tra routine sau khi thay đổi bảng nền.
7. Quản lý definer và quyền `EXECUTE` theo least privilege.
8. Theo dõi latency, số lần gọi và lỗi routine từ ứng dụng.
9. Tránh để logic cùng một quy tắc bị nhân đôi không kiểm soát giữa Java và SQL.

MySQL không cung cấp cú pháp `CREATE OR REPLACE PROCEDURE`/`FUNCTION` tương tự view trong các phiên bản thông dụng. Migration thường dùng `DROP ... IF EXISTS` rồi `CREATE` lại hoặc công cụ triển khai routine có kiểm soát. Việc thay routine có thể ảnh hưởng consumer đang chạy; hãy triển khai theo thứ tự tương thích và kiểm tra quyền/definer sau migration.

## 26. Versioning và compatibility giữa Java với routine

Khi Java gọi routine theo tên và thứ tự tham số, thay đổi signature có thể làm ứng dụng cũ lỗi. Ví dụ đổi thứ tự hai tham số cùng kiểu có thể không gây lỗi compile ở Java nhưng đổi ngữ nghĩa.

Các nguyên tắc:

- Không đổi thứ tự/ý nghĩa tham số một cách âm thầm.
- Ưu tiên kiểu dữ liệu rõ ràng và nhất quán với Java (`BIGINT`/`Long`, `DECIMAL`/`BigDecimal`, `DATETIME`/quy ước thời gian).
- Khi cần thay đổi không tương thích, cân nhắc tạo routine version mới, triển khai consumer rồi mới loại routine cũ.
- Kiểm tra NULL và giá trị mặc định rõ ràng; đừng dựa vào giá trị mặc định ngầm.
- Đảm bảo migration tạo routine trước khi phiên bản ứng dụng mới bắt đầu gọi.
- Kiểm thử bằng tài khoản runtime thực tế để phát hiện thiếu `EXECUTE` hoặc quyền nền.

Routine cũng lưu một số môi trường tạo như SQL mode và thông tin charset/collation liên quan. Khi deploy giữa môi trường khác nhau, cần kiểm tra cấu hình và tạo routine bằng migration có kiểm soát để tránh hành vi khác biệt ngoài ý muốn.

## 27. Khi nào không nên đưa logic vào stored routine?

Nên giữ logic ở Java khi:

- Logic thay đổi thường xuyên theo product requirement và cần triển khai độc lập với schema.
- Cần gọi API, message broker, email, file system hoặc dịch vụ ngoài.
- Logic cần thư viện domain/crypto/serialization mà SQL không phù hợp.
- Cần unit test phong phú, dependency injection hoặc orchestration nhiều aggregate/service.
- Quy tắc có nhiều nhánh phức tạp và đội phát triển không có quy trình review/versioning stored routine tốt.
- Nhiều routine gọi lồng nhau khiến luồng xử lý khó theo dõi.

Nên cân nhắc SQL/routine khi:

- Công việc chủ yếu là thao tác set-based trên dữ liệu MySQL.
- Nhiều client cần cùng một thao tác dữ liệu chuẩn.
- Giảm round-trip mang lại lợi ích đo được.
- Cần cung cấp bề mặt quyền hẹp qua `EXECUTE` và `SQL SECURITY`.
- Logic tương đối ổn định và đội có thể kiểm thử/migrate routine an toàn.

Không có quy tắc “business logic luôn ở Java” hoặc “logic dữ liệu luôn ở stored procedure”. Hãy phân chia theo tính sở hữu, khả năng kiểm thử, hiệu năng và yêu cầu nhất quán.

## 28. Checklist quyết định procedure, function hay Java

| Câu hỏi | Hướng lựa chọn ban đầu |
| --- | --- |
| Cần trả nhiều hàng hoặc thực hiện nhiều bước? | Procedure hoặc SQL qua Java |
| Cần một giá trị scalar trong biểu thức SQL? | Function hoặc biểu thức SQL trực tiếp |
| Logic cần gọi dịch vụ ngoài? | Java/service/worker |
| Nhiều client phải dùng cùng một quy tắc dữ liệu? | Cân nhắc routine và constraint |
| Cần một transaction bao trùm nhiều repository call? | Java transaction owner hoặc một procedure boundary rõ ràng |
| Cần quyền chỉ gọi một thao tác mà không đọc trực tiếp bảng? | Procedure với quyền `EXECUTE` và security phù hợp |
| Function sẽ chạy cho hàng triệu dòng? | Đánh giá set-based SQL thay cho function theo từng hàng |
| Logic thay đổi liên tục và cần unit test/domain model? | Java |
| Cần quản lý schema code bằng migration/versioning? | Routine chỉ phù hợp nếu pipeline hỗ trợ đầy đủ |

## 29. Những lỗi và hiểu nhầm thường gặp

| Hiểu nhầm / lỗi | Thực tế | Cách xử lý |
| --- | --- | --- |
| Procedure và function giống nhau | Procedure được gọi bằng `CALL`; function trả scalar trong biểu thức | Chọn theo kiểu input/output và cách gọi |
| Function có thể trả nhiều hàng | Function trả một giá trị; procedure có thể trả result set | Dùng procedure hoặc SELECT |
| Stored routine luôn nhanh hơn Java | SQL vẫn chịu chi phí access path, I/O và CPU; function theo từng hàng có thể rất tốn kém | Đo round-trip và execution plan |
| Routine tự bảo đảm transaction | Transaction boundary phụ thuộc cách routine và caller điều khiển | Chỉ định một transaction owner |
| Procedure có thể commit mà không ảnh hưởng caller | COMMIT trong procedure có thể commit transaction trên cùng connection | Không trộn transaction ownership |
| Có thể gọi API ngoài trong procedure | MySQL routine không phải nơi orchestration network phù hợp | Dùng Java/worker và outbox |
| SQL SECURITY DEFINER là mặc định an toàn | Definer có thể có quyền rộng và tồn tại lâu | Least privilege, quản lý definer và GRANT EXECUTE |
| Dùng stored procedure là hết SQL injection | Dynamic SQL nối input vẫn nguy hiểm | Static SQL, bind parameter và allowlist identifier |
| DETERMINISTIC chỉ là tối ưu hóa vô hại | Đây là cam kết về kết quả; khai báo sai có thể ảnh hưởng binlog/replication | Khai báo đúng hành vi thực tế |
| Bắt mọi exception rồi không báo lại là an toàn | Caller có thể nhận thành công giả | Dùng RESIGNAL hoặc trả mã lỗi hợp đồng rõ |
| Java và procedure đều tự commit được | Hai bên có thể kết thúc transaction của nhau | Chọn một nơi sở hữu commit/rollback |

## 30. Bài tập thực hành

1. Tạo `sp_get_customer_orders` nhận `IN customer_id` và `IN limit`; gọi bằng `CALL` và đọc result set.
2. Tạo `sp_count_customer_orders` trả `OUT order_count`; gọi bằng user variable và bằng JDBC `CallableStatement`.
3. Tạo procedure có tham số `INOUT` để cập nhật một giá trị tiền; kiểm tra kiểu `DECIMAL` và quy tắc làm tròn.
4. Tạo `fn_line_total` trả `DECIMAL`; gọi trong `SELECT` và so sánh với biểu thức SQL trực tiếp.
5. Tạo `fn_order_total` đọc bảng chi tiết; gọi cho một đơn và cho nhiều đơn; đo số lần thực thi/chi phí so với JOIN + GROUP BY.
6. Viết procedure có `EXIT HANDLER FOR SQLEXCEPTION`, rollback và `RESIGNAL`; thử gây lỗi trong môi trường lab.
7. Viết procedure có `SQL SECURITY INVOKER`, cấp `EXECUTE` và kiểm tra quyền của user runtime.
8. So sánh `DEFINER` và `INVOKER` bằng hai tài khoản có quyền khác nhau.
9. Gọi procedure từ Java bằng `CallableStatement`; bind tham số, đăng ký OUT parameter và đóng result set.
10. Gọi function từ Java bằng `PreparedStatement` và `BigDecimal`.
11. Thử mô hình Java-owned transaction với procedure không commit; xác minh Java rollback được toàn bộ thay đổi.
12. Thử procedure-owned transaction và xác minh Java không bọc nó trong transaction khác.
13. Thiết kế một use case tạo đơn hàng có outbox; xác định phần nào thuộc procedure/database và phần nào thuộc Java worker.
14. Viết migration tạo routine, thay đổi signature theo version mới và kiểm tra consumer cũ/mới.

## 31. Ghi nhớ

Stored procedure là routine được gọi bằng `CALL`, phù hợp với thao tác nhiều bước, result set và tham số `IN`/`OUT`/`INOUT`. Stored function trả một giá trị scalar qua `RETURN`, có thể dùng trong biểu thức SQL và chỉ nhận tham số đầu vào. Function cần được giữ nhỏ, rõ ngữ nghĩa; nếu được gọi theo từng hàng và truy vấn dữ liệu bên trong, chi phí có thể tăng mạnh so với một truy vấn set-based.

Stored routine có thể gom logic dữ liệu, giảm round-trip và tạo bề mặt quyền hẹp, nhưng không tự động nhanh hơn hoặc thay thế Java. Java phù hợp với API, orchestration, domain logic phức tạp, gọi dịch vụ ngoài, tracing và retry policy. MySQL phù hợp với constraint và thao tác set-based; procedure/function được dùng khi lợi ích tái sử dụng, transaction hoặc quyền truy cập được xác định rõ.

Đặc biệt, chỉ một nơi nên sở hữu transaction cho một đơn vị nghiệp vụ: Java hoặc procedure. Procedure có thể điều khiển transaction; function không được commit/rollback hoặc trả result set. Dùng JDBC `CallableStatement` cho procedure, `PreparedStatement` cho function, bind tham số và quản lý result set/connection cẩn thận. Quản lý routine bằng source control và migration, chọn `SQL SECURITY` theo least privilege, khai báo `DETERMINISTIC`/SQL data access trung thực và kiểm tra execution plan trước khi đưa routine vào đường đi tải lớn.
