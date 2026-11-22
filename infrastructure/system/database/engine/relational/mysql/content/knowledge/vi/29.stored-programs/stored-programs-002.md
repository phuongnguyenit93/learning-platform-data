# CREATE PROCEDURE, CREATE FUNCTION và cách gọi

Stored program (chương trình lưu trữ) là mã SQL được định nghĩa và lưu trong MySQL để có thể gọi lại. Hai loại routine thường dùng là **stored procedure** và **stored function**. Procedure được gọi bằng `CALL`, có thể nhận tham số `IN`, `OUT`, `INOUT` và có thể trả result set. Function trả về một giá trị qua `RETURN` và có thể được dùng trong biểu thức SQL như các hàm dựng sẵn.

Bài học thuộc module **DATABASE_MYSQL**. Module hướng tới việc làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction và kiểm soát đồng thời; đồng thời thực hành đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Trong chương **Stored program**, bài này tập trung vào `CREATE PROCEDURE`, `CREATE FUNCTION` và cách gọi. `SPECIAL_NOTE` được cung cấp rỗng, vì vậy không có ràng buộc riêng bổ sung cho bài.

## 1. Stored procedure và stored function

Procedure và function đều được lưu trong database schema và có thể chứa nhiều câu lệnh SQL. Khác biệt lớn nhất nằm ở cách gọi và kết quả:

| Tiêu chí | Stored procedure | Stored function |
|---|---|---|
| Tạo bằng | `CREATE PROCEDURE` | `CREATE FUNCTION` |
| Cách gọi | `CALL schema.procedure(...)` | Dùng trong biểu thức, ví dụ `SELECT function(...)` |
| Giá trị trả về | Có thể trả qua `OUT`/`INOUT` và result set | Bắt buộc trả một giá trị bằng `RETURN` |
| Tham số | `IN`, `OUT`, `INOUT` | Tham số đầu vào; không khai báo mode OUT/INOUT |
| Dùng trong SELECT/WHERE | Không gọi procedure như một biểu thức | Có thể dùng function trong biểu thức SQL |
| Result set | Có thể phát result set bằng `SELECT` thông thường | Không được trả result set trực tiếp |
| Điều khiển transaction | Có thể dùng transaction statement trong procedure, tùy ngữ cảnh gọi | Không được điều khiển transaction tường minh |
| Mục đích điển hình | Thực hiện một thao tác/nghiệp vụ gồm nhiều bước | Tính một giá trị hoặc trả kết quả scalar có thể tái sử dụng |

Không xem function là procedure rút gọn. Cách MySQL cho phép dùng function trong một biểu thức SQL khiến function chịu thêm các giới hạn và yêu cầu về side effect.

## 2. Stored routine được lưu và thực thi ở đâu?

Routine được tạo trong một schema:

```sql
USE shop_db;

DELIMITER $$

CREATE PROCEDURE get_open_orders()
BEGIN
    SELECT order_id, customer_id, order_date
    FROM orders
    WHERE status = 'OPEN';
END$$

DELIMITER ;
```

MySQL lưu định nghĩa routine trong metadata của server. Khi client gọi routine, server thực thi phần thân routine theo security context và quyền đã cấu hình. Ứng dụng không phải gửi lại toàn bộ nội dung các câu lệnh bên trong mỗi lần gọi.

Tên routine có thể được gọi kèm schema để tránh phụ thuộc schema mặc định:

```sql
CALL shop_db.get_open_orders();
```

`USE shop_db` chỉ thay đổi schema mặc định của session. Nó không tạo database và không cấp quyền cho tài khoản.

## 3. Cú pháp CREATE PROCEDURE

Cấu trúc tổng quát:

```sql
CREATE [DEFINER = user]
PROCEDURE procedure_name ([parameter_list])
[characteristic ...]
routine_body
```

Một tham số procedure có dạng:

```sql
[IN | OUT | INOUT] parameter_name data_type
```

Nếu không ghi mode, mặc định là `IN`.

Procedure body có thể là một câu lệnh hoặc một compound statement `BEGIN ... END` gồm nhiều câu lệnh. Khi body có nhiều câu lệnh, client dòng lệnh cần đổi delimiter để dấu chấm phẩy bên trong không bị hiểu là kết thúc toàn bộ câu `CREATE PROCEDURE`.

## 4. DELIMITER trong MySQL client

Ví dụ tạo procedure có nhiều câu lệnh:

```sql
DELIMITER $$

CREATE PROCEDURE get_customer_orders(
    IN p_customer_id BIGINT
)
BEGIN
    SELECT
        order_id,
        order_date,
        total_amount,
        status
    FROM orders
    WHERE customer_id = p_customer_id
    ORDER BY order_date DESC;
END$$

DELIMITER ;
```

`DELIMITER` là chỉ thị của một số client như MySQL command-line client; nó không phải câu lệnh SQL được gửi đến server và không nằm trong body routine đã lưu. Mục đích của nó là yêu cầu client dùng `$$` làm dấu kết thúc câu lệnh trong lúc nhập định nghĩa. Sau khi tạo xong, đổi delimiter về `;`.

Trong MySQL Workbench hoặc công cụ migration, cách thiết lập statement delimiter có thể khác. Hãy theo cú pháp script separator của công cụ đang dùng.

## 5. Tham số IN

`IN` truyền dữ liệu từ caller vào procedure. Procedure có thể đọc giá trị tham số để lọc hoặc tính toán; việc gán lại tham số IN không truyền giá trị mới ngược về caller.

Ví dụ lấy đơn hàng theo khách hàng:

```sql
DELIMITER $$

CREATE PROCEDURE get_orders_by_customer(
    IN p_customer_id BIGINT
)
BEGIN
    SELECT
        order_id,
        order_date,
        total_amount
    FROM orders
    WHERE customer_id = p_customer_id
    ORDER BY order_date DESC;
END$$

DELIMITER ;
```

Gọi procedure:

```sql
CALL get_orders_by_customer(1001);
```

Giá trị `1001` được truyền vào `p_customer_id`. Procedure thực hiện câu `SELECT` và trả result set cho client.

## 6. Tham số OUT

`OUT` dùng để procedure ghi một giá trị trả lại cho caller. Giá trị ban đầu của đối số truyền vào không được dùng như input của procedure; procedure cần gán giá trị cho tham số OUT trước khi trả kết quả.

Ví dụ đếm số đơn hàng của khách hàng:

```sql
DELIMITER $$

CREATE PROCEDURE count_customer_orders(
    IN p_customer_id BIGINT,
    OUT p_order_count INT
)
BEGIN
    SELECT COUNT(*)
    INTO p_order_count
    FROM orders
    WHERE customer_id = p_customer_id;
END$$

DELIMITER ;
```

Gọi procedure bằng user-defined variable:

```sql
CALL count_customer_orders(1001, @order_count);

SELECT @order_count AS order_count;
```

`@order_count` là user-defined session variable. Giá trị OUT được gán vào biến này để caller đọc sau câu `CALL`. Biến user-defined tồn tại trong session hiện tại; một session khác không tự nhìn thấy biến này.

### 6.1. OUT và SELECT ... INTO

`SELECT ... INTO` đưa giá trị truy vấn vào biến local hoặc tham số OUT thay vì gửi một result set cho client:

```sql
SELECT COUNT(*)
INTO p_order_count
FROM orders
WHERE customer_id = p_customer_id;
```

`COUNT(*)` luôn trả một hàng, kể cả khi không có đơn phù hợp; khi đó kết quả là 0. Với một truy vấn không aggregate, nếu không có hàng, `SELECT ... INTO` phát điều kiện NOT FOUND và biến đích giữ giá trị trước đó; nếu có nhiều hơn một hàng thì xảy ra lỗi. Thiết kế truy vấn sao cho số hàng trả về đúng như mong đợi.

## 7. Tham số INOUT

`INOUT` vừa nhận giá trị ban đầu từ caller vừa trả giá trị đã được procedure cập nhật.

Ví dụ giới hạn tỷ lệ chiết khấu và tính số tiền giảm:

```sql
DELIMITER $$

CREATE PROCEDURE calculate_discount(
    IN p_order_id BIGINT,
    INOUT p_discount_rate DECIMAL(5, 4),
    OUT p_discount_amount DECIMAL(12, 2)
)
BEGIN
    DECLARE v_total_amount DECIMAL(12, 2) DEFAULT 0;

    SET p_discount_rate = LEAST(
        GREATEST(p_discount_rate, 0),
        0.2500
    );

    SELECT total_amount
    INTO v_total_amount
    FROM orders
    WHERE order_id = p_order_id;

    SET p_discount_amount = ROUND(
        v_total_amount * p_discount_rate,
        2
    );
END$$

DELIMITER ;
```

Gọi procedure:

```sql
SET @rate = 0.3000;
SET @discount_amount = 0;

CALL calculate_discount(
    5001,
    @rate,
    @discount_amount
);

SELECT
    @rate AS applied_rate,
    @discount_amount AS discount_amount;
```

Nếu tỷ lệ truyền vào là `0.3000`, procedure giới hạn nó ở `0.2500` rồi trả tỷ lệ sau cập nhật và số tiền chiết khấu. Ví dụ giả định `order_id` tồn tại; trong routine production cần xử lý trường hợp không tìm thấy đơn hàng và kiểm tra quy tắc nghiệp vụ.

## 8. Biến cục bộ trong routine

Biến cục bộ được khai báo bằng `DECLARE` bên trong một block `BEGIN ... END`. Biến chỉ có phạm vi trong block đã khai báo:

```sql
DELIMITER $$

CREATE PROCEDURE get_customer_order_total(
    IN p_customer_id BIGINT,
    OUT p_total DECIMAL(14, 2)
)
BEGIN
    DECLARE v_total DECIMAL(14, 2) DEFAULT 0;

    SELECT COALESCE(SUM(total_amount), 0)
    INTO v_total
    FROM orders
    WHERE customer_id = p_customer_id;

    SET p_total = v_total;
END$$

DELIMITER ;

CALL get_customer_order_total(1001, @total);
SELECT @total AS total_amount;
```

Một số quy tắc cần nhớ:

- Khai báo biến local bằng `DECLARE` ở đầu block, trước các câu lệnh thực thi.
- Biến local cần có kiểu dữ liệu; có thể khai báo giá trị mặc định bằng `DEFAULT`.
- Gán giá trị bằng `SET` hoặc `SELECT ... INTO`.
- Biến local không có ký hiệu `@`; ký hiệu `@` dành cho user-defined session variable.
- Biến trong block con có phạm vi riêng và có thể che khuất biến cùng tên ở block ngoài; nên đặt tên có tiền tố rõ ràng để tránh nhầm lẫn.

Trong stored program có nhiều loại khai báo khác như condition, cursor và handler. Thứ tự khai báo của chúng có quy tắc riêng; các bài về điều khiển luồng, cursor và error handling sẽ đi sâu hơn.

## 9. Cú pháp CREATE FUNCTION

Function phải khai báo kiểu dữ liệu trả về bằng `RETURNS`:

```sql
CREATE [DEFINER = user]
FUNCTION function_name ([parameter_list])
RETURNS data_type
[characteristic ...]
routine_body
```

Khác với procedure, tham số function không có mode `IN`, `OUT` hoặc `INOUT`. Tham số function được dùng làm input. Function phải trả về một giá trị bằng câu lệnh `RETURN expression` trên mọi đường thực thi có thể xảy ra.

## 10. Function tính toán không truy cập bảng

Ví dụ function tính thuế từ số tiền và tỷ lệ:

```sql
DELIMITER $$

CREATE FUNCTION calculate_tax(
    p_net_amount DECIMAL(12, 2),
    p_tax_rate DECIMAL(5, 4)
)
RETURNS DECIMAL(12, 2)
DETERMINISTIC
NO SQL
RETURN ROUND(p_net_amount * p_tax_rate, 2)$$

DELIMITER ;
```

Gọi function:

```sql
SELECT calculate_tax(1000000, 0.1000) AS tax_amount;

SET @tax = calculate_tax(2500000, 0.0800);
SELECT @tax;
```

Function trả một giá trị scalar, vì vậy có thể được dùng trong biểu thức:

```sql
SELECT
    order_id,
    total_amount,
    calculate_tax(total_amount, 0.1000) AS estimated_tax
FROM orders
WHERE status = 'PAID';
```

Khi function xuất hiện trong truy vấn nhiều hàng, server có thể cần đánh giá function cho nhiều hàng. Tránh đặt routine có chi phí lớn vào biểu thức chạy lặp theo từng hàng nếu một phép JOIN, biểu thức SQL trực tiếp hoặc phép tính theo tập hợp có thể giải quyết bài toán tốt hơn.

## 11. Function đọc dữ liệu từ bảng

Function có thể đọc dữ liệu và trả về một giá trị. Ví dụ lấy tổng tiền đơn hàng theo khách hàng:

```sql
DELIMITER $$

CREATE FUNCTION customer_order_total(
    p_customer_id BIGINT
)
RETURNS DECIMAL(14, 2)
NOT DETERMINISTIC
READS SQL DATA
BEGIN
    DECLARE v_total DECIMAL(14, 2) DEFAULT 0;

    SELECT COALESCE(SUM(total_amount), 0)
    INTO v_total
    FROM orders
    WHERE customer_id = p_customer_id;

    RETURN v_total;
END$$

DELIMITER ;
```

Gọi function:

```sql
SELECT customer_order_total(1001) AS total_spent;

SELECT
    customer_id,
    customer_order_total(customer_id) AS total_spent
FROM customers;
```

Function này đọc bảng `orders`, nên kết quả phụ thuộc dữ liệu tại thời điểm thực thi. Cùng một tham số có thể cho kết quả khác khi đơn hàng được thêm, sửa hoặc xóa; vì vậy khai báo `NOT DETERMINISTIC` phù hợp với ví dụ này.

Truy vấn thứ hai minh họa cách gọi function trong danh sách cột. Với tập khách hàng lớn, cách gọi function theo từng hàng có thể tạo nhiều lần tra cứu; hãy cân nhắc truy vấn aggregate và JOIN trực tiếp để optimizer xử lý theo tập hợp.

## 12. RETURN và kiểu dữ liệu trả về

`RETURNS data_type` xác định kiểu dữ liệu của kết quả function. Kiểu trả về nên khớp với miền giá trị nghiệp vụ:

| Kết quả | Kiểu dữ liệu có thể cân nhắc |
|---|---|
| Số lượng bản ghi | `INT` hoặc `BIGINT` |
| Tiền, thuế, tỷ lệ quy đổi | `DECIMAL(p,s)` |
| Điểm, hệ số, tỷ lệ | `DECIMAL` hoặc kiểu số phù hợp |
| Trạng thái dạng mã | `TINYINT` hoặc kiểu số/mã được chuẩn hóa |
| Chuỗi định danh/nhãn | `VARCHAR(n)` |
| Thời điểm | `DATE`, `DATETIME` hoặc `TIMESTAMP` tùy ngữ nghĩa |

Ví dụ function trả trạng thái dạng số:

```sql
DELIMITER $$

CREATE FUNCTION is_large_order(
    p_total_amount DECIMAL(14, 2)
)
RETURNS TINYINT
DETERMINISTIC
NO SQL
RETURN IF(p_total_amount >= 100000000, 1, 0)$$

DELIMITER ;

SELECT
    order_id,
    is_large_order(total_amount) AS is_large
FROM orders;
```

`RETURN` kết thúc function và trả giá trị biểu thức. Không nhầm `RETURN` với tham số `OUT` của procedure. Function không có nhiều tham số output theo cách procedure có thể có; nếu cần nhiều kết quả độc lập, cân nhắc procedure với nhiều `OUT` hoặc một cấu trúc dữ liệu phù hợp.

## 13. Các characteristic của routine

MySQL cho phép khai báo các characteristic mô tả routine:

| Characteristic | Ý nghĩa |
|---|---|
| `DETERMINISTIC` | Khai báo routine cho cùng input sẽ cho cùng kết quả trong cùng điều kiện liên quan. |
| `NOT DETERMINISTIC` | Khai báo kết quả có thể thay đổi dù input giống nhau. |
| `NO SQL` | Khai báo routine không chứa câu lệnh SQL. |
| `CONTAINS SQL` | Routine có SQL nhưng không đọc/ghi dữ liệu theo phân loại này. |
| `READS SQL DATA` | Routine có đọc dữ liệu SQL. |
| `MODIFIES SQL DATA` | Routine có thể thay đổi dữ liệu SQL. |
| `SQL SECURITY DEFINER` | Thực thi theo security context của definer. |
| `SQL SECURITY INVOKER` | Thực thi theo security context của caller. |
| `COMMENT '...'` | Gắn mô tả cho routine. |

Các characteristic về truy cập dữ liệu là phần khai báo cho server và công cụ quản trị. Chúng không thay thế việc xem xét câu lệnh thực tế trong body; đặc biệt, `DETERMINISTIC` là lời khai của người tạo routine, MySQL không phân tích toàn bộ logic để chứng minh routine thật sự deterministic.

### 13.1. DETERMINISTIC và NOT DETERMINISTIC

Một function thuần tính toán từ tham số:

```sql
CREATE FUNCTION add_service_fee(
    p_amount DECIMAL(12, 2),
    p_fee_rate DECIMAL(5, 4)
)
RETURNS DECIMAL(12, 2)
DETERMINISTIC
NO SQL
RETURN ROUND(p_amount * (1 + p_fee_rate), 2);
```

Với cùng hai input, phép tính luôn cho cùng kết quả; `DETERMINISTIC` phù hợp.

Ngược lại, function dùng thời gian hiện tại hoặc đọc bảng có thể thay đổi:

```sql
DELIMITER $$

CREATE FUNCTION current_open_order_count()
RETURNS BIGINT
NOT DETERMINISTIC
READS SQL DATA
BEGIN
    DECLARE v_count BIGINT DEFAULT 0;

    SELECT COUNT(*)
    INTO v_count
    FROM orders
    WHERE status = 'OPEN';

    RETURN v_count;
END$$

DELIMITER ;
```

Ví dụ này minh họa tính chất không ổn định theo thời gian và dữ liệu. Cùng một lần gọi function có thể cho kết quả khác ở thời điểm khác vì bảng `orders` có thể thay đổi.

### 13.2. SQL data access characteristics

- Function chỉ tính toán từ tham số, không đọc/ghi bảng: thường khai báo `NO SQL`.
- Routine có câu SQL nhưng không truy cập dữ liệu: `CONTAINS SQL`.
- Function đọc bảng: `READS SQL DATA`.
- Procedure hoặc function có thao tác thay đổi dữ liệu khi được phép: `MODIFIES SQL DATA`.

Không khai báo `NO SQL` cho routine thực sự đọc bảng. Không khai báo `DETERMINISTIC` chỉ để vượt qua kiểm tra tạo function; hãy phản ánh đúng hành vi và chính sách replication.

## 14. Giới hạn của stored function

Function có thể được gọi từ một biểu thức SQL đang đọc hoặc thay đổi dữ liệu. Vì vậy, MySQL đặt ra các giới hạn để tránh routine làm thay đổi cách câu lệnh bên ngoài hoạt động:

- Function không được trả result set trực tiếp. Có thể dùng `SELECT ... INTO` để đưa dữ liệu vào biến local.
- Function không được dùng các câu lệnh điều khiển transaction tường minh như `START TRANSACTION`, `COMMIT` hoặc `ROLLBACK`.
- Function không được dùng SQL prepared statement động thông qua `PREPARE`/`EXECUTE`.
- Function không được thay đổi một bảng mà chính câu lệnh gọi function đang sử dụng. Ví dụ, gọi function từ `UPDATE orders ...` rồi để function cập nhật lại `orders` sẽ gặp giới hạn này.
- Function phải trả một giá trị bằng `RETURN`; không dùng tham số `OUT`/`INOUT` để trả nhiều giá trị.

Các giới hạn này khác procedure. Procedure có thể phát result set và có thể chứa transaction statement, nhưng việc commit/rollback bên trong procedure có thể tác động đến transaction do caller mở. Hãy thống nhất rõ thành phần nào sở hữu transaction.

### 14.1. SELECT ... INTO được phép, SELECT trả result set thì không

Trong function, cách đọc dữ liệu phù hợp là:

```sql
BEGIN
    DECLARE v_customer_name VARCHAR(150) DEFAULT NULL;

    SELECT customer_name
    INTO v_customer_name
    FROM customers
    WHERE customer_id = p_customer_id;

    RETURN v_customer_name;
END
```

Đây là phần thân bên trong một function có tham số `p_customer_id` và kiểu trả về `VARCHAR(150)`. Với trường hợp không tìm thấy hàng, routine cần có chính sách xử lý NOT FOUND phù hợp với nghiệp vụ.

Không viết một câu `SELECT customer_name FROM customers ...` để phát result set từ function. Nếu nghiệp vụ cần trả nhiều hàng, hãy dùng procedure hoặc một truy vấn SELECT trực tiếp.

### 14.2. Không dùng function để ẩn side effect trong SELECT

Không nên thiết kế function được gọi trong `SELECT` nhưng âm thầm thực hiện cập nhật, gửi thông báo hoặc thay đổi trạng thái nghiệp vụ. Ngoài các giới hạn của MySQL, cách làm này khiến tác động của một truy vấn khó dự đoán, khó đo hiệu năng và khó retry an toàn.

Hãy dùng procedure cho thao tác có side effect rõ ràng, ví dụ tạo đơn hàng, ghi nhận thanh toán hoặc cập nhật trạng thái. Dùng function cho giá trị tính toán có hợp đồng đầu vào/đầu ra rõ ràng.

## 15. Procedure có thể trả result set và OUT cùng lúc

Procedure có thể trả một hoặc nhiều result set qua các câu `SELECT` thông thường, đồng thời trả thêm dữ liệu qua `OUT`:

```sql
DELIMITER $$

CREATE PROCEDURE get_customer_summary(
    IN p_customer_id BIGINT,
    OUT p_order_count INT,
    OUT p_total_spent DECIMAL(14, 2)
)
BEGIN
    SELECT
        COUNT(*),
        COALESCE(SUM(total_amount), 0)
    INTO
        p_order_count,
        p_total_spent
    FROM orders
    WHERE customer_id = p_customer_id;

    SELECT
        order_id,
        order_date,
        total_amount,
        status
    FROM orders
    WHERE customer_id = p_customer_id
    ORDER BY order_date DESC;
END$$

DELIMITER ;
```

Gọi procedure:

```sql
CALL get_customer_summary(
    1001,
    @order_count,
    @total_spent
);

SELECT
    @order_count AS order_count,
    @total_spent AS total_spent;
```

Client nhận result set đơn hàng từ câu `SELECT` thứ hai, đồng thời có thể đọc hai output variable. Với driver ứng dụng, cần tiêu thụ hết result set do procedure trả về trước khi tái sử dụng connection; API cụ thể phụ thuộc driver.

## 16. Chọn PROCEDURE hay FUNCTION?

| Câu hỏi | Chọn procedure khi... | Chọn function khi... |
|---|---|---|
| Mục tiêu chính | Thực hiện một hành động hoặc quy trình nhiều bước | Tính và trả một giá trị |
| Cách gọi | Caller chủ động chạy `CALL` | Cần nhúng kết quả vào `SELECT` hoặc biểu thức |
| Số đầu ra | Cần nhiều `OUT`/`INOUT` hoặc nhiều result set | Cần một giá trị scalar |
| Thay đổi dữ liệu | Cần thực hiện DML có chủ đích | Chỉ nên dùng khi phù hợp giới hạn và hợp đồng dữ liệu của function |
| Transaction | Có thể điều phối transaction theo thiết kế | Không điều khiển transaction tường minh |
| Đọc nhiều hàng | Có thể trả result set | Không trả result set trực tiếp |
| Dùng trong WHERE/SELECT | Không gọi trực tiếp như biểu thức | Có thể gọi như một hàm SQL |

Ví dụ chọn procedure:

- Tạo đơn hàng, thêm các dòng chi tiết và ghi audit.
- Chạy một quy trình cập nhật nhiều bảng.
- Trả danh sách bản ghi cùng một số thống kê qua OUT.
- Thực hiện một tác vụ quản trị được cấp quyền EXECUTE.

Ví dụ chọn function:

- Tính thuế từ giá trị và tỷ lệ.
- Chuẩn hóa hoặc phân loại một mã đầu vào.
- Trả một giá trị tổng hợp scalar khi chi phí và giới hạn truy vấn được kiểm soát.

Nếu chỉ cần một câu truy vấn, không nhất thiết phải bọc nó trong routine. Routine có giá trị khi nó tạo hợp đồng gọi lại rõ ràng, gom logic dùng chung hoặc cung cấp ranh giới quyền phù hợp.

## 17. SQL SECURITY và DEFINER

Stored procedure và stored function có security context. Hai lựa chọn chính:

- `SQL SECURITY DEFINER`: routine chạy với quyền của tài khoản definer đã gắn với routine. Đây là mặc định nếu không khai báo.
- `SQL SECURITY INVOKER`: routine chạy với quyền của tài khoản đang gọi routine.

Ví dụ procedure dùng quyền definer:

```sql
DELIMITER $$

CREATE
    DEFINER = 'routine_owner'@'localhost'
    SQL SECURITY DEFINER
PROCEDURE get_sensitive_customer_summary(
    IN p_customer_id BIGINT
)
BEGIN
    SELECT customer_id, COUNT(*) AS order_count
    FROM orders
    WHERE customer_id = p_customer_id
    GROUP BY customer_id;
END$$

DELIMITER ;
```

Tài khoản ứng dụng có thể được cấp quyền `EXECUTE` trên procedure mà không cần cấp trực tiếp quyền đọc tất cả bảng nền, nếu security model và definer privilege được thiết kế đúng.

### 17.1. Khi nào dùng DEFINER hoặc INVOKER?

**DEFINER** phù hợp khi routine được thiết kế như một API database có quyền hạn giới hạn. Caller chỉ được thực hiện hành động mà routine cho phép. Cần bảo vệ tài khoản definer, giữ quyền tối thiểu và quản lý vòng đời tài khoản.

**INVOKER** phù hợp khi muốn quyền truy cập bảng nền vẫn phụ thuộc tài khoản caller. Caller cần có các quyền cần thiết trên đối tượng được routine truy cập.

Không dùng DEFINER để né quy trình phân quyền. Một routine có quyền definer quá rộng có thể trở thành đường truy cập vượt quyền nếu input không được kiểm tra hoặc routine cho phép thao tác ngoài ý muốn.

## 18. Quyền tạo, sửa và gọi routine

Các quyền thường gặp:

| Privilege | Mục đích |
|---|---|
| `CREATE ROUTINE` | Tạo stored procedure hoặc stored function trong schema được cấp quyền. |
| `ALTER ROUTINE` | Thay đổi characteristic hoặc xóa routine theo quyền được cấp. |
| `EXECUTE` | Gọi routine. |
| Quyền trên bảng nền | Cần khi routine thực thi theo quyền caller (INVOKER); với DEFINER, definer phải có các quyền cần thiết. |

Ví dụ cấp quyền:

```sql
GRANT CREATE ROUTINE
ON shop_db.*
TO 'routine_developer'@'localhost';

GRANT EXECUTE
ON PROCEDURE shop_db.get_customer_orders
TO 'shop_app'@'localhost';

GRANT EXECUTE
ON FUNCTION shop_db.calculate_tax
TO 'shop_app'@'localhost';
```

Kiểm tra quyền của tài khoản hiện tại:

```sql
SHOW GRANTS;
```

Không cấp `CREATE ROUTINE` cho tài khoản ứng dụng runtime nếu ứng dụng chỉ cần gọi routine. Tách tài khoản migration/deployment khỏi tài khoản ứng dụng và chỉ cấp các quyền cần thiết.

### 18.1. Quyền khi dùng DEFINER và INVOKER

Với `SQL SECURITY DEFINER`, MySQL kiểm tra quyền truy cập đối tượng theo security context của definer khi routine thực thi. Caller vẫn cần quyền `EXECUTE` trên routine. Với `SQL SECURITY INVOKER`, quyền truy cập đối tượng được kiểm tra theo caller; chỉ có `EXECUTE` có thể chưa đủ để đọc/ghi bảng nền.

Tài khoản definer cần tồn tại và có đúng các quyền mà routine yêu cầu. Nếu tài khoản definer bị xóa hoặc mất quyền, routine có thể lỗi khi thực thi. Hãy quản lý definer như một phần của deployment và lifecycle database.

### 18.2. Binary logging và stored function

Khi binary logging được bật, việc tạo stored function có thể chịu thêm điều kiện về quyền và khai báo characteristic để bảo đảm an toàn replication. Cấu hình `log_bin_trust_function_creators` ảnh hưởng cách server áp dụng các điều kiện này.

Có thể kiểm tra cấu hình:

```sql
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'log_bin_trust_function_creators';
```

Không bật trust setting chỉ để bỏ qua lỗi tạo function. Hãy kiểm tra chính sách replication, quyền của tài khoản tạo routine và tính đúng đắn của `DETERMINISTIC`/SQL data access characteristic theo phiên bản server đang dùng.

## 19. Tra cứu và quản lý routine

### 19.1. Xem định nghĩa procedure/function

```sql
SHOW CREATE PROCEDURE get_customer_orders;
SHOW CREATE FUNCTION calculate_tax;
```

Hai câu lệnh trả định nghĩa đã lưu, cùng thông tin characteristic và security context liên quan.

### 19.2. Liệt kê routine trong schema

```sql
SHOW PROCEDURE STATUS
WHERE Db = 'shop_db';

SHOW FUNCTION STATUS
WHERE Db = 'shop_db';
```

Hoặc dùng `INFORMATION_SCHEMA.ROUTINES`:

```sql
SELECT
    ROUTINE_SCHEMA,
    ROUTINE_NAME,
    ROUTINE_TYPE,
    DATA_TYPE,
    IS_DETERMINISTIC,
    SQL_DATA_ACCESS,
    SECURITY_TYPE,
    DEFINER,
    CREATED,
    LAST_ALTERED
FROM INFORMATION_SCHEMA.ROUTINES
WHERE ROUTINE_SCHEMA = 'shop_db'
ORDER BY ROUTINE_TYPE, ROUTINE_NAME;
```

`ROUTINE_TYPE` phân biệt `PROCEDURE` và `FUNCTION`. `DATA_TYPE` mô tả kiểu trả về của function; procedure không có kiểu trả về scalar như function.

### 19.3. ALTER và DROP

`ALTER PROCEDURE`/`ALTER FUNCTION` dùng để thay đổi một số characteristic của routine; chúng không dùng để viết lại toàn bộ body hoặc danh sách tham số. Khi cần thay body, thường phải triển khai lại định nghĩa routine bằng quy trình drop/create có kiểm soát.

Xóa routine:

```sql
DROP PROCEDURE IF EXISTS shop_db.get_customer_orders;
DROP FUNCTION IF EXISTS shop_db.calculate_tax;
```

Trước khi drop hoặc tạo lại, xác định caller, quyền đã cấp, definer, dependency và thời điểm triển khai. Nếu drop/create tách rời, có thể tồn tại khoảng thời gian ứng dụng không gọi được routine.

## 20. Transaction khi gọi procedure

Procedure có thể chứa nhiều câu lệnh DML. Nếu nghiệp vụ yêu cầu các bước phải thành công hoặc thất bại cùng nhau, cần xác định ranh giới transaction rõ ràng.

Một thiết kế thường gặp là để ứng dụng/caller quản lý transaction. Ví dụ giả định procedure `create_order_for_customer` đã được tạo:

```sql
START TRANSACTION;

CALL create_order_for_customer(
    1001,
    '2026-11-19'
);

COMMIT;
```

Nếu procedure phát sinh lỗi, caller cần xử lý lỗi và rollback theo hợp đồng transaction đã thiết kế. Các bài về handler/error handling sẽ trình bày cách bắt lỗi và rollback trong stored program.

Procedure cũng có thể chứa `START TRANSACTION`, `COMMIT` hoặc `ROLLBACK`. Tuy nhiên, không nên vừa để caller quản lý transaction vừa để procedure tự commit mà không có thỏa thuận rõ ràng. Commit bên trong procedure có thể kết thúc transaction mà caller đang kỳ vọng tiếp tục kiểm soát.

Stored function không được dùng các câu lệnh điều khiển transaction tường minh. Nếu nghiệp vụ cần cập nhật nhiều bảng hoặc có ranh giới commit/rollback, procedure phù hợp hơn.

## 21. Lab thực hành: tạo và gọi procedure/function

Lab dùng schema thử nghiệm có bảng `customers` và `orders`. Chạy phần tạo bảng và dữ liệu một lần trong schema lab mới; nếu bảng đã tồn tại, kiểm tra cấu trúc và dữ liệu trước khi chạy lại. Không chạy DDL mẫu này trực tiếp trên production.

### 21.1. Chuẩn bị bảng mẫu

```sql
CREATE TABLE customers (
    customer_id BIGINT NOT NULL PRIMARY KEY,
    customer_name VARCHAR(150) NOT NULL
) ENGINE = InnoDB;

CREATE TABLE orders (
    order_id BIGINT NOT NULL PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    order_date DATE NOT NULL,
    total_amount DECIMAL(14, 2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    KEY idx_orders_customer_date (customer_id, order_date)
) ENGINE = InnoDB;

INSERT INTO customers (customer_id, customer_name)
VALUES
    (1001, 'An Nguyen'),
    (1002, 'Binh Tran');

INSERT INTO orders
    (order_id, customer_id, order_date, total_amount, status)
VALUES
    (5001, 1001, '2026-11-01', 1200000, 'PAID'),
    (5002, 1001, '2026-11-05', 800000, 'OPEN'),
    (5003, 1002, '2026-11-06', 2500000, 'PAID');
```

### 21.2. Tạo và gọi procedure với IN

```sql
DELIMITER $$

CREATE PROCEDURE list_customer_orders(
    IN p_customer_id BIGINT
)
BEGIN
    SELECT
        order_id,
        order_date,
        total_amount,
        status
    FROM orders
    WHERE customer_id = p_customer_id
    ORDER BY order_date DESC;
END$$

DELIMITER ;

CALL list_customer_orders(1001);
```

Kết quả gồm các đơn hàng của khách hàng `1001`.

### 21.3. Tạo và gọi procedure với OUT

```sql
DELIMITER $$

CREATE PROCEDURE get_customer_order_count(
    IN p_customer_id BIGINT,
    OUT p_count BIGINT
)
BEGIN
    SELECT COUNT(*)
    INTO p_count
    FROM orders
    WHERE customer_id = p_customer_id;
END$$

DELIMITER ;

CALL get_customer_order_count(1001, @order_count);
SELECT @order_count AS order_count;
```

### 21.4. Tạo và gọi function

```sql
DELIMITER $$

CREATE FUNCTION order_amount_with_tax(
    p_amount DECIMAL(14, 2),
    p_rate DECIMAL(5, 4)
)
RETURNS DECIMAL(14, 2)
DETERMINISTIC
NO SQL
RETURN ROUND(p_amount * (1 + p_rate), 2)$$

DELIMITER ;

SELECT
    order_id,
    total_amount,
    order_amount_with_tax(total_amount, 0.1000) AS amount_with_tax
FROM orders;
```

### 21.5. Xác minh định nghĩa và quyền

```sql
SHOW CREATE PROCEDURE list_customer_orders;
SHOW CREATE PROCEDURE get_customer_order_count;
SHOW CREATE FUNCTION order_amount_with_tax;

SELECT
    ROUTINE_NAME,
    ROUTINE_TYPE,
    DATA_TYPE,
    IS_DETERMINISTIC,
    SQL_DATA_ACCESS,
    SECURITY_TYPE
FROM INFORMATION_SCHEMA.ROUTINES
WHERE ROUTINE_SCHEMA = DATABASE();

SHOW GRANTS;
```

## 22. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Client báo lỗi gần dấu `;` trong body | Client coi dấu chấm phẩy đầu tiên là kết thúc câu CREATE | Đổi delimiter trong client khi gửi định nghĩa nhiều câu lệnh. |
| Gọi procedure bằng SELECT | Procedure không phải biểu thức SQL | Dùng `CALL`. |
| Gọi function bằng CALL | Function trả scalar trong biểu thức | Dùng `SELECT function(...)` hoặc biểu thức SQL phù hợp. |
| Dùng OUT/INOUT trong function | Function không hỗ trợ mode tham số này | Dùng procedure nếu cần nhiều output. |
| Function phát result set | Stored function không được trả result set trực tiếp | Dùng `SELECT ... INTO` hoặc chuyển sang procedure. |
| Function chứa COMMIT/ROLLBACK | Function không được điều khiển transaction tường minh | Chuyển nghiệp vụ sang procedure/caller transaction. |
| SELECT ... INTO trả nhiều hàng | Truy vấn không bảo đảm một hàng | Dùng aggregate, điều kiện unique hoặc giới hạn đúng theo nghiệp vụ. |
| Procedure có OUT nhưng caller không đọc | Output chỉ được gán vào đối số truyền vào | Dùng user variable hoặc local variable làm đối số và đọc sau CALL. |
| Function khai báo DETERMINISTIC sai | Khai báo không phản ánh dữ liệu/thời gian thực tế | Đánh giá lại dữ liệu phụ thuộc và replication. |
| EXECUTE bị từ chối | Caller thiếu quyền EXECUTE hoặc security context không đủ quyền | Kiểm tra GRANT, DEFINER/INVOKER và quyền trên đối tượng. |
| Routine lỗi sau khi thay đổi definer | Definer không tồn tại hoặc thiếu quyền | Quản lý definer account và quyền trong migration. |

## 23. Checklist thiết kế routine

- [ ] Đã chọn procedure hay function theo cách caller cần sử dụng kết quả.
- [ ] Procedure có mode tham số IN/OUT/INOUT đúng mục đích.
- [ ] Function khai báo RETURNS đúng kiểu dữ liệu và mọi đường thực thi đều RETURN.
- [ ] Biến local được DECLARE đúng vị trí và có kiểu dữ liệu phù hợp.
- [ ] SELECT ... INTO bảo đảm số hàng phù hợp hoặc có cách xử lý NOT FOUND.
- [ ] Client delimiter được cấu hình đúng khi tạo body nhiều câu lệnh.
- [ ] Function không phát result set, không dùng prepared statement động và không điều khiển transaction.
- [ ] Function không sửa bảng đang được câu lệnh gọi function sử dụng.
- [ ] DETERMINISTIC và SQL data access characteristics phản ánh đúng hành vi.
- [ ] Đã chọn SQL SECURITY DEFINER/INVOKER và definer account có quyền tối thiểu.
- [ ] Caller chỉ có các quyền cần thiết, đặc biệt là EXECUTE.
- [ ] Đã kiểm tra ảnh hưởng binary logging/replication khi tạo function.
- [ ] Đã xem SHOW CREATE và INFORMATION_SCHEMA.ROUTINES sau deployment.
- [ ] Đã xác định rõ ai sở hữu transaction và cách xử lý lỗi.
- [ ] Đã kiểm tra hiệu năng khi function được gọi lặp theo từng hàng.

## 24. Ghi nhớ

`CREATE PROCEDURE` định nghĩa một routine được gọi bằng `CALL`. Procedure hỗ trợ tham số `IN`, `OUT`, `INOUT`, có thể trả result set và phù hợp với quy trình nghiệp vụ nhiều bước.

`CREATE FUNCTION` định nghĩa routine có kiểu trả về `RETURNS` và kết thúc bằng `RETURN`. Function nhận tham số input và có thể được gọi trong biểu thức SQL. Function chịu giới hạn về result set, prepared statement động và transaction control; hãy dùng nó cho giá trị scalar có hợp đồng rõ ràng.

Khi triển khai cả hai loại routine, cần chú ý delimiter của client, characteristic, quyền `EXECUTE`, security context `DEFINER`/`INVOKER`, binary logging và cách quản lý transaction. Luôn xác minh định nghĩa đã lưu và thử gọi routine bằng tài khoản có đúng quyền như ứng dụng thực tế.
