# CREATE TEMPORARY TABLE và phạm vi nhìn thấy theo kết nối

MySQL cho phép tạo bảng tạm bằng `CREATE TEMPORARY TABLE`. Bảng này tồn tại trong phạm vi một session (một kết nối MySQL), chỉ session tạo ra nó mới nhìn thấy và sử dụng được. Khi kết nối kết thúc, MySQL tự động loại bỏ bảng tạm. Vì vậy, hai kết nối có thể tạo bảng tạm cùng tên mà không nhìn thấy dữ liệu của nhau.

Bảng tạm hữu ích khi cần lưu kết quả trung gian cho nhiều câu SQL, chia một phép xử lý lớn thành các bước, chuẩn bị tập khóa để join, hoặc giữ kết quả báo cáo trong suốt một phiên làm việc. Tuy nhiên, vòng đời của bảng tạm gắn với kết nối vật lý, không nhất thiết gắn với một request của ứng dụng. Điều này đặc biệt quan trọng khi ứng dụng dùng connection pool: kết nối có thể được tái sử dụng sau khi request kết thúc, khiến bảng tạm và dữ liệu cũ vẫn còn.

Bài học thuộc module `DATABASE_MYSQL`, tập trung vào thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn và vận hành cơ sở dữ liệu quan hệ. Mục tiêu là tạo, sử dụng và dọn dẹp bảng tạm đúng vòng đời; hiểu phạm vi nhìn thấy theo connection; đồng thời tránh nhầm bảng tạm do người dùng tạo với temporary table nội bộ do optimizer tạo trong lúc thực thi truy vấn.

Sau bài học, bạn có thể:

- Tạo và xóa bảng tạm bằng `CREATE TEMPORARY TABLE` và `DROP TEMPORARY TABLE`.
- Giải thích vì sao bảng tạm chỉ nhìn thấy trong connection tạo ra nó.
- Phân biệt session scope với database scope và transaction scope.
- Hiểu việc bảng tạm che khuất bảng thường cùng tên trong session hiện tại.
- Dùng `LIKE`, `AS SELECT` hoặc khai báo schema tường minh để tạo bảng tạm.
- Chọn storage engine phù hợp với dữ liệu và transaction.
- Hiểu quyền `CREATE TEMPORARY TABLES` và các giới hạn quan trọng.
- Quản lý bảng tạm an toàn khi ứng dụng dùng connection pool.
- Kiểm tra vòng đời và khả năng nhìn thấy bằng `CONNECTION_ID()`.

## 1. Bảng tạm là gì?

Bảng tạm là một bảng được tạo với từ khóa `TEMPORARY`:

```sql
CREATE TEMPORARY TABLE tmp_customer_ids (
    customer_id BIGINT UNSIGNED NOT NULL PRIMARY KEY
) ENGINE = InnoDB;
```

Điểm khác biệt cốt lõi so với bảng thường:

| Thuộc tính | Bảng thường | Bảng tạm do người dùng tạo |
| --- | --- | --- |
| Phạm vi nhìn thấy | Các session có quyền phù hợp | Chỉ session tạo bảng |
| Vòng đời | Tồn tại đến khi bị DROP | Tự bị DROP khi session kết thúc, hoặc DROP thủ công |
| Tên bảng | Phải duy nhất trong schema | Có thể trùng tên bảng thường; có thể trùng tên temp table ở session khác |
| Dữ liệu giữa các kết nối | Có thể chia sẻ theo quyền | Không chia sẻ giữa các kết nối |
| Mục đích thường gặp | Lưu dữ liệu nghiệp vụ lâu dài | Lưu dữ liệu trung gian trong một phiên xử lý |

`TEMPORARY` không có nghĩa dữ liệu nhất thiết nằm hoàn toàn trong RAM. Storage engine được chọn quyết định cách lưu và các đặc tính transaction. Ví dụ trên dùng InnoDB, dữ liệu có thể được quản lý trên storage của InnoDB và hỗ trợ transaction theo engine.

## 2. Phạm vi nhìn thấy là connection, không phải database

Một session MySQL tương ứng với một kết nối tới server. Bảng tạm được tạo trong session hiện tại và chỉ session đó truy cập được.

Kiểm tra mã kết nối:

```sql
SELECT CONNECTION_ID();
```

Tạo và nạp dữ liệu trong Session A:

```sql
CREATE TEMPORARY TABLE tmp_work_items (
    item_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    item_status VARCHAR(20) NOT NULL
) ENGINE = InnoDB;

INSERT INTO tmp_work_items (item_id, item_status)
VALUES (101, 'READY'), (102, 'READY');

SELECT * FROM tmp_work_items ORDER BY item_id;
```

Trong chính Session A, các câu SELECT, INSERT, UPDATE, DELETE và JOIN tiếp theo có thể sử dụng `tmp_work_items` như một bảng thông thường.

Mở một kết nối khác, Session B, rồi chạy:

```sql
SELECT CONNECTION_ID();
SELECT * FROM tmp_work_items;
```

Nếu không có bảng thường cùng tên, Session B nhận lỗi không tìm thấy bảng. Dữ liệu trong bảng tạm của Session A không được chia sẻ sang Session B. Nếu Session B có một bảng thường tên `tmp_work_items`, truy vấn ở Session B sẽ tham chiếu bảng thường đó, không phải bảng tạm thuộc Session A.

### 2.1. Hai session có thể dùng cùng tên

Session A:

```sql
CREATE TEMPORARY TABLE tmp_stage (
    id INT PRIMARY KEY,
    note VARCHAR(40) NOT NULL
);

INSERT INTO tmp_stage VALUES (1, 'session A');
```

Session B:

```sql
CREATE TEMPORARY TABLE tmp_stage (
    id INT PRIMARY KEY,
    note VARCHAR(40) NOT NULL
);

INSERT INTO tmp_stage VALUES (1, 'session B');
```

Hai session có thể cùng tạo `tmp_stage`. Khi Session A SELECT, nó chỉ thấy `session A`; Session B chỉ thấy `session B`. Tên bảng tạm không phải một tên dùng chung toàn schema.

### 2.2. Không nhầm session với transaction

Bảng tạm không tự biến mất khi `COMMIT` hoặc `ROLLBACK`. Phạm vi tồn tại của nó là connection. Transaction chỉ điều khiển tính nguyên tử của các thay đổi dữ liệu theo storage engine; nó không phải cơ chế đóng vòng đời bảng tạm.

```sql
CREATE TEMPORARY TABLE tmp_numbers (
    n INT PRIMARY KEY
) ENGINE = InnoDB;

START TRANSACTION;
INSERT INTO tmp_numbers VALUES (10), (20);
COMMIT;

SELECT * FROM tmp_numbers;
```

Sau COMMIT, bảng vẫn tồn tại trong session và các hàng vẫn có thể được truy vấn. Muốn kết thúc vòng đời trước khi đóng connection, dùng `DROP TEMPORARY TABLE`.

## 3. Bảng tạm che khuất bảng thường cùng tên

MySQL cho phép một session tạo temporary table có cùng tên với một bảng thường trong cùng schema. Trong session đó, tên được phân giải tới bảng tạm; bảng thường bị che khuất cho tới khi bảng tạm bị xóa.

Tạo bảng thường trong schema lab:

```sql
CREATE TABLE customer_work (
    customer_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL
) ENGINE = InnoDB;

INSERT INTO customer_work VALUES (1, 'Permanent customer');
```

Trong Session A:

```sql
CREATE TEMPORARY TABLE customer_work (
    customer_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL
) ENGINE = InnoDB;

INSERT INTO customer_work VALUES (1, 'Temporary customer');

SELECT * FROM customer_work;
```

Kết quả trong Session A là `Temporary customer`. Session B vẫn truy vấn bảng thường và thấy `Permanent customer`:

```sql
SELECT * FROM customer_work;
```

Khi Session A chạy:

```sql
DROP TEMPORARY TABLE customer_work;
```

tên `customer_work` trong Session A lại tham chiếu bảng thường. Lưu ý: bảng thường không bị xóa bởi `DROP TEMPORARY TABLE`.

Việc che khuất tên rất hữu ích cho một số workflow nhưng cũng có thể gây nhầm lẫn khi debug. Dùng prefix nhất quán như `tmp_`, `work_` hoặc tên theo mục đích để giảm nguy cơ vô tình thao tác trên một bảng tạm đang che bảng thường.

## 4. Tạo bảng tạm bằng các cách khác nhau

### 4.1. Khai báo schema tường minh

Đây là cách phù hợp khi cần kiểm soát kiểu dữ liệu, NULL, khóa và index:

```sql
CREATE TEMPORARY TABLE tmp_order_summary (
    customer_id BIGINT UNSIGNED NOT NULL,
    order_count BIGINT UNSIGNED NOT NULL,
    total_amount DECIMAL(14, 2) NOT NULL,
    PRIMARY KEY (customer_id),
    KEY idx_tmp_order_summary_total (total_amount)
) ENGINE = InnoDB;
```

Sau đó nạp dữ liệu bằng INSERT ... SELECT:

```sql
INSERT INTO tmp_order_summary
    (customer_id, order_count, total_amount)
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_amount
FROM orders
WHERE order_status = 'PAID'
GROUP BY customer_id;
```

Ưu điểm là schema được xác định rõ, có thể thêm index cần thiết trước hoặc sau khi nạp dữ liệu, và dễ kiểm tra tính tương thích với truy vấn phía sau.

### 4.2. Tạo từ cấu trúc bảng khác bằng LIKE

`CREATE TEMPORARY TABLE ... LIKE ...` tạo bảng tạm rỗng theo cấu trúc của bảng nguồn:

```sql
CREATE TEMPORARY TABLE tmp_orders LIKE orders;
```

Cách này hữu ích khi cần cùng định nghĩa cột và index để thực hiện một bước xử lý riêng. Bảng được tạo không tự sao chép các hàng dữ liệu của bảng nguồn. Nếu cần dữ liệu, phải nạp riêng bằng INSERT ... SELECT.

```sql
INSERT INTO tmp_orders
SELECT *
FROM orders
WHERE order_date >= '2026-11-01'
  AND order_date < '2026-12-01';
```

`LIKE` không nên được hiểu là bản sao đầy đủ mọi quan hệ của bảng nguồn. Kiểm tra `SHOW CREATE TABLE` trên bảng tạm để xác nhận chính xác cột, index và thuộc tính được tạo; các ràng buộc foreign key không được sao chép thành quan hệ hoạt động của bảng tạm.

### 4.3. Tạo và nạp dữ liệu bằng AS SELECT

Có thể tạo bảng tạm từ kết quả truy vấn:

```sql
CREATE TEMPORARY TABLE tmp_recent_orders
ENGINE = InnoDB
AS
SELECT
    order_id,
    customer_id,
    order_date,
    total_amount
FROM orders
WHERE order_date >= '2026-11-01'
  AND order_date < '2026-12-01';
```

MySQL suy ra các cột từ select list và nạp kết quả vào bảng mới. Cách này ngắn gọn khi cần một snapshot dữ liệu trung gian. Tuy nhiên, không giả định rằng index, primary key, unique constraint hoặc toàn bộ thuộc tính của bảng nguồn được sao chép. Nếu truy vấn sau cần index, hãy tạo rõ ràng:

```sql
ALTER TABLE tmp_recent_orders
ADD PRIMARY KEY (order_id),
ADD KEY idx_tmp_recent_customer (customer_id);
```

Với dữ liệu lớn, cân nhắc khai báo schema tường minh trước, rồi INSERT ... SELECT để kiểm soát kiểu dữ liệu, độ dài và index ngay từ đầu.

## 5. Dùng bảng tạm cho quy trình nhiều bước

Một trường hợp phổ biến là tính tập khách hàng có doanh số đủ điều kiện, sau đó dùng tập này trong nhiều truy vấn.

Giả sử bảng thường `orders` có các cột `order_id`, `customer_id`, `order_status`, `order_date` và `total_amount`.

Tạo bảng tạm chứa khách hàng đủ điều kiện:

```sql
DROP TEMPORARY TABLE IF EXISTS tmp_qualified_customers;

CREATE TEMPORARY TABLE tmp_qualified_customers (
    customer_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    paid_total DECIMAL(14, 2) NOT NULL,
    paid_order_count BIGINT UNSIGNED NOT NULL
) ENGINE = InnoDB;

INSERT INTO tmp_qualified_customers
    (customer_id, paid_total, paid_order_count)
SELECT
    customer_id,
    SUM(total_amount),
    COUNT(*)
FROM orders
WHERE order_status = 'PAID'
  AND order_date >= '2026-11-01'
  AND order_date < '2026-12-01'
GROUP BY customer_id
HAVING SUM(total_amount) >= 1000;
```

Sau đó dùng tập trung gian cho nhiều câu truy vấn:

```sql
SELECT customer_id, paid_total
FROM tmp_qualified_customers
ORDER BY paid_total DESC;

SELECT COUNT(*) AS qualified_customer_count
FROM tmp_qualified_customers;

SELECT o.order_id, o.customer_id, o.total_amount
FROM orders AS o
JOIN tmp_qualified_customers AS q
    ON q.customer_id = o.customer_id
WHERE o.order_status = 'PAID';
```

Lợi ích là bước tổng hợp được lưu lại trong session và có thể tái sử dụng. Nhưng bảng tạm cũng tiêu thụ dung lượng và thời gian ghi/đọc. Nếu chỉ dùng kết quả một lần, một CTE hoặc derived table có thể đơn giản hơn; hãy đo workload thay vì mặc định bảng tạm luôn nhanh hơn.

## 6. Storage engine và transaction

Bảng tạm do người dùng tạo có thể chỉ định storage engine. Chọn engine theo yêu cầu dữ liệu:

| Engine | Đặc điểm cần cân nhắc |
| --- | --- |
| InnoDB | Hỗ trợ transaction, rollback DML, row-level locking và phù hợp với tập trung gian cần tính nhất quán |
| MEMORY | Lưu dữ liệu trong RAM, thường phù hợp tập nhỏ; dữ liệu mất khi server khởi động lại và bị giới hạn bởi cấu hình bộ nhớ; không có đầy đủ semantics transaction như InnoDB |

Ví dụ InnoDB:

```sql
CREATE TEMPORARY TABLE tmp_balance_check (
    account_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    calculated_balance DECIMAL(18, 2) NOT NULL
) ENGINE = InnoDB;
```

### 6.1. DDL temporary table và implicit commit

Trong MySQL, `CREATE TEMPORARY TABLE` và `DROP TEMPORARY TABLE` không gây implicit commit như các thao tác CREATE/DROP bảng thường. Tuy vậy, thao tác tạo/xóa định nghĩa bảng tạm không được rollback như một thay đổi DML thông thường.

Ví dụ:

```sql
START TRANSACTION;

CREATE TEMPORARY TABLE tmp_txn_demo (
    id INT PRIMARY KEY
) ENGINE = InnoDB;

INSERT INTO tmp_txn_demo VALUES (1);
ROLLBACK;

SHOW CREATE TABLE tmp_txn_demo;
SELECT * FROM tmp_txn_demo;
```

Sau ROLLBACK, định nghĩa bảng tạm vẫn tồn tại trong session vì thao tác CREATE TEMPORARY TABLE không được rollback. Với InnoDB, hàng được INSERT trong transaction đã rollback sẽ không còn. Ví dụ này minh họa hai vòng đời khác nhau: định nghĩa bảng tạm gắn với session, còn thay đổi dữ liệu InnoDB chịu transaction.

Không dựa vào `ROLLBACK` để xóa bảng tạm đã tạo. Dùng `DROP TEMPORARY TABLE` khi cần dọn dẹp.

### 6.2. DML trên bảng tạm vẫn phụ thuộc engine

Với bảng tạm InnoDB, INSERT/UPDATE/DELETE tham gia transaction hiện tại. Với engine không hỗ trợ transaction, không thể kỳ vọng rollback phục hồi các thay đổi dữ liệu. Hãy chỉ rõ `ENGINE` khi transaction semantics quan trọng thay vì phụ thuộc vào default engine của server.

## 7. Quyền tạo bảng tạm

Để tạo temporary table trong một schema, tài khoản cần quyền `CREATE TEMPORARY TABLES` trên schema đó. Ví dụ minh họa:

```sql
GRANT CREATE TEMPORARY TABLES
ON reporting_db.*
TO 'report_user'@'localhost';
```

Sau khi tạo bảng tạm thành công, MySQL không thực hiện thêm các kiểm tra quyền thông thường đối với chính bảng tạm đó trong suốt session. Vì vậy, quyền tạo bảng tạm cần được cấp có chủ đích cho các tài khoản ứng dụng và báo cáo.

Quyền này không biến temporary table thành dữ liệu dùng chung. Một session khác vẫn không nhìn thấy bảng tạm. Đồng thời, khi temporary table che khuất bảng thường cùng tên, session tạo bảng tạm sẽ làm việc với bảng tạm cho đến khi DROP hoặc session kết thúc.

Kiểm tra quyền hiện tại:

```sql
SHOW GRANTS FOR CURRENT_USER();
```

Không cấp quyền rộng hơn nhu cầu chỉ để tránh lỗi tạo bảng tạm. Trong môi trường nhiều ứng dụng dùng chung tài khoản, xác định rõ ứng dụng nào được phép tạo temporary table và có quy tắc cleanup phù hợp.

## 8. Vòng đời và dọn dẹp

Bảng tạm kết thúc vòng đời theo một trong hai cách:

1. Session chủ động xóa bảng bằng `DROP TEMPORARY TABLE`.
2. Connection kết thúc; MySQL tự động xóa các temporary table thuộc session đó.

Lệnh xóa rõ ràng:

```sql
DROP TEMPORARY TABLE IF EXISTS tmp_qualified_customers;
```

Có thể xóa nhiều bảng tạm:

```sql
DROP TEMPORARY TABLE IF EXISTS
    tmp_qualified_customers,
    tmp_recent_orders,
    tmp_order_summary;
```

`IF EXISTS` giúp cleanup an toàn khi một nhánh xử lý chưa tạo bảng hoặc bảng đã được xóa trước đó. Không nên dùng `DROP TABLE` chung chung trong script cleanup nếu mục tiêu chính xác là bảng tạm; `DROP TEMPORARY TABLE` thể hiện rõ ý định và bảo vệ bảng thường cùng tên.

### 8.1. CREATE TEMPORARY TABLE IF NOT EXISTS

Cú pháp này tránh lỗi nếu bảng tạm đã tồn tại:

```sql
CREATE TEMPORARY TABLE IF NOT EXISTS tmp_stage (
    id BIGINT UNSIGNED NOT NULL PRIMARY KEY
) ENGINE = InnoDB;
```

Nếu bảng tạm cùng tên đã tồn tại trong session, MySQL không thay thế cấu trúc hoặc xóa dữ liệu cũ của bảng đó. Vì vậy, `IF NOT EXISTS` không phải cách reset trạng thái. Khi cần schema sạch, chủ động DROP rồi CREATE:

```sql
DROP TEMPORARY TABLE IF EXISTS tmp_stage;

CREATE TEMPORARY TABLE tmp_stage (
    id BIGINT UNSIGNED NOT NULL PRIMARY KEY
) ENGINE = InnoDB;
```

### 8.2. Kiểm tra bảng tạm đang dùng

Trong session hiện tại, có thể dùng các câu lệnh thông thường:

```sql
SHOW CREATE TABLE tmp_stage;
DESCRIBE tmp_stage;
SELECT COUNT(*) FROM tmp_stage;
```

`SHOW CREATE TABLE` và `DESCRIBE` giúp xác minh schema thực tế. Đừng dựa vào một truy vấn từ session khác để kiểm tra bảng tạm vì session khác không có quyền nhìn thấy đối tượng này.

## 9. Connection pool: lỗi vòng đời thường gặp trong ứng dụng

Trong ứng dụng backend, connection pool giữ một số kết nối vật lý mở và cho nhiều request mượn dùng lần lượt. Khi request trả connection về pool, kết nối MySQL có thể vẫn tồn tại. Vì temporary table gắn với connection vật lý, bảng tạm cũng tồn tại qua ranh giới các request nếu ứng dụng không DROP nó.

Một tình huống lỗi:

1. Request A mượn connection 42.
2. Request A tạo `tmp_report_rows`, nạp dữ liệu và trả connection về pool mà quên DROP.
3. Request B mượn lại connection 42.
4. Request B chạy `CREATE TEMPORARY TABLE tmp_report_rows ...` và gặp lỗi bảng đã tồn tại, hoặc `IF NOT EXISTS` khiến dữ liệu/schema cũ vẫn được dùng.

Một request khác dùng connection 57 không thấy bảng của connection 42, nên lỗi có thể chỉ xuất hiện không ổn định tùy connection pool cấp kết nối nào.

### 9.1. Quy tắc triển khai an toàn

- Tạo tên bảng tạm có prefix rõ ràng và chỉ dùng trong một workflow.
- Dùng `DROP TEMPORARY TABLE IF EXISTS` trước khi khởi tạo nếu cần trạng thái sạch.
- Luôn cleanup trong khối `finally` hoặc cơ chế tương đương, kể cả khi câu SQL ở giữa thất bại.
- Không trả connection về pool trước khi cleanup hoàn tất.
- Không giả định kết thúc transaction hoặc request sẽ tự xóa bảng tạm.
- Nếu connection bị hủy hoặc mất, để pool loại bỏ connection lỗi; khi server đóng session, temporary table được dọn tự động.
- Tránh lưu dữ liệu nhạy cảm trong temporary table lâu hơn cần thiết.

Pseudocode minh họa:

```text
connection = pool.borrow()
try:
    DROP TEMPORARY TABLE IF EXISTS tmp_request_rows
    CREATE TEMPORARY TABLE tmp_request_rows (...)
    INSERT INTO tmp_request_rows ...
    run_queries_using_tmp_request_rows(connection)
finally:
    try:
        DROP TEMPORARY TABLE IF EXISTS tmp_request_rows
        pool.release(connection)
    catch cleanup_error:
        pool.invalidate(connection)
```

Điểm quan trọng là cleanup và release phải dùng cùng một connection vật lý đã tạo bảng tạm. Chỉ trả connection về pool khi cleanup thành công; nếu không thể xác nhận đã xóa bảng tạm, hãy loại connection khỏi pool thay vì tái sử dụng nó. Không chạy DROP qua một connection khác rồi cho rằng bảng của connection ban đầu đã được xóa.

## 10. Giới hạn và lỗi thường gặp

### 10.1. Không thể mở lại cùng một temporary table nhiều lần trong một query

MySQL có giới hạn khi tham chiếu cùng một temporary table nhiều hơn một lần trong cùng câu query. Ví dụ sau có thể phát sinh lỗi `Can't reopen table`:

```sql
SELECT a.id, b.id
FROM tmp_stage AS a
JOIN tmp_stage AS b
    ON b.id = a.id + 1;
```

Đây là giới hạn khi mở lại cùng một temporary table dưới nhiều alias trong một query block. Nếu cần tự join dữ liệu tạm, cân nhắc tạo một bản sao tạm thứ hai với tên khác, hoặc viết lại phép xử lý bằng một cấu trúc truy vấn phù hợp.

```sql
CREATE TEMPORARY TABLE tmp_stage_copy LIKE tmp_stage;
INSERT INTO tmp_stage_copy SELECT * FROM tmp_stage;

SELECT a.id, b.id
FROM tmp_stage AS a
JOIN tmp_stage_copy AS b
    ON b.id = a.id + 1;
```

### 10.2. Temporary table không hỗ trợ foreign key

Không thiết kế temporary table như một bảng quan hệ có foreign key constraint tới bảng thường. Temporary table không hỗ trợ foreign key constraints; kiểm tra toàn vẹn cần được thực hiện bằng truy vấn, logic ứng dụng hoặc bảng thường phù hợp.

### 10.3. Dữ liệu cũ do connection được tái sử dụng

Nếu không DROP bảng tạm hoặc không xóa dữ liệu cũ trước khi nạp lại, request tiếp theo có thể đọc dữ liệu của request trước. Dùng cleanup rõ ràng và thiết kế thao tác nạp dữ liệu có tính lặp an toàn.

### 10.4. Nhầm temporary table của người dùng với internal temporary table

MySQL có thể tạo internal temporary table trong quá trình thực thi một số truy vấn như GROUP BY, DISTINCT, UNION hoặc xử lý derived table. Đây là đối tượng nội bộ do server quản lý; ứng dụng không tạo và không cần DROP nó bằng SQL.

`CREATE TEMPORARY TABLE` trong bài này là bảng tạm do người dùng chủ động tạo và quản lý theo session. Hai khái niệm khác nhau dù cùng có từ temporary.

### 10.5. Chọn engine hoặc kiểu dữ liệu không phù hợp

Một temporary table lớn với nhiều cột VARCHAR/TEXT/BLOB có thể tiêu tốn đáng kể dung lượng. MEMORY có giới hạn và đặc tính lưu trữ riêng; InnoDB phù hợp hơn nếu cần transaction hoặc tập dữ liệu có thể lớn. Chọn kiểu dữ liệu, index và engine theo workload thực tế.

## 11. Quan sát phạm vi session bằng hai cửa sổ SQL

Thực hiện bài lab sau với hai kết nối độc lập.

**Session A**

```sql
SELECT CONNECTION_ID() AS session_a_id;

CREATE TEMPORARY TABLE tmp_visibility (
    marker VARCHAR(30) NOT NULL
) ENGINE = InnoDB;

INSERT INTO tmp_visibility VALUES ('created in A');
SELECT * FROM tmp_visibility;
```

**Session B**

```sql
SELECT CONNECTION_ID() AS session_b_id;
SELECT * FROM tmp_visibility;
```

Nếu không có bảng thường tên `tmp_visibility`, câu SELECT ở Session B báo không tìm thấy bảng. Quay lại Session A, chạy:

```sql
DROP TEMPORARY TABLE tmp_visibility;
```

Sau đó đóng Session A. Bảng tạm đã được xóa rõ ràng; nếu bỏ qua DROP, MySQL vẫn tự dọn khi session A thực sự kết thúc.

## 12. Quy trình khuyến nghị cho một workflow dùng bảng tạm

1. Xác định tập dữ liệu trung gian và thời gian cần giữ nó.
2. Chọn tên bảng tạm có prefix riêng, tránh trùng với bảng nghiệp vụ.
3. Chọn engine, kiểu dữ liệu, khóa và index phù hợp.
4. Tạo bảng trên connection sẽ thực hiện toàn bộ workflow.
5. Nạp dữ liệu và kiểm tra số hàng/giá trị đại diện.
6. Dùng bảng tạm trong các câu JOIN, UPDATE hoặc báo cáo của cùng connection.
7. Kiểm tra kết quả trước khi ghi dữ liệu cuối cùng vào bảng thường.
8. DROP bảng tạm trong cleanup trước khi trả connection về pool.
9. Nếu connection kết thúc bất thường, xác nhận pool loại connection đó; server sẽ dọn temporary table khi session kết thúc.

Không dùng temporary table để thay thế cơ chế lưu trữ bền vững. Dữ liệu cần được chia sẻ giữa session, cần tồn tại qua lần restart hoặc cần được quản lý như dữ liệu nghiệp vụ phải nằm trong bảng thường với quyền và chính sách lưu trữ phù hợp.

## 13. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Session B không thấy bảng tạm của Session A | Temporary table thuộc session tạo ra nó | Chạy mọi thao tác trên cùng connection |
| Request sau báo table already exists | Connection pool tái sử dụng session còn bảng tạm | DROP trước khi tạo và cleanup trước khi release |
| Request khác đọc nhầm dữ liệu cũ | Bảng tạm còn dữ liệu từ lần mượn connection trước | Xóa/nạp lại dữ liệu theo workflow và cleanup trong finally |
| Bảng thường cùng tên bị che khuất | Temporary table trong session có độ ưu tiên phân giải tên | Dùng prefix riêng; DROP TEMPORARY TABLE sau khi dùng |
| ROLLBACK nhưng bảng tạm vẫn tồn tại | Định nghĩa temporary table không rollback như DML | DROP TEMPORARY TABLE tường minh |
| `CREATE TEMPORARY TABLE IF NOT EXISTS` giữ schema cũ | Câu lệnh không thay thế bảng đã tồn tại | DROP trước rồi CREATE khi cần schema sạch |
| `Can't reopen table` | Cùng temporary table được tham chiếu nhiều lần trong một query | Dùng bản sao tạm khác tên hoặc viết lại query |
| Không tạo được bảng tạm | Thiếu quyền CREATE TEMPORARY TABLES | Xin cấp đúng quyền trên schema cần dùng |
| Mong đợi foreign key hoạt động | Temporary table không hỗ trợ foreign key constraints | Kiểm tra tính toàn vẹn bằng cách khác |
| Bảng tạm quá lớn hoặc thiếu bộ nhớ | Chọn engine/kiểu dữ liệu không phù hợp | Đánh giá InnoDB, kích thước dữ liệu và index |

## 14. Bài tập thực hành

1. Mở hai connection. Tạo cùng tên `tmp_visibility` ở cả hai và chứng minh mỗi session chỉ thấy dữ liệu của chính nó.
2. Tạo bảng thường `customer_work`, sau đó tạo temporary table cùng tên trong Session A. So sánh kết quả SELECT ở Session A và Session B.
3. DROP temporary table và xác nhận Session A lại nhìn thấy bảng thường.
4. Dùng `CREATE TEMPORARY TABLE ... LIKE ...`; kiểm tra schema bằng `SHOW CREATE TABLE` và xác nhận bảng mới rỗng.
5. Dùng `CREATE TEMPORARY TABLE ... AS SELECT`; kiểm tra cột/index và tự bổ sung index cần thiết.
6. Tạo bảng tạm InnoDB, INSERT trong transaction rồi ROLLBACK. Xác nhận định nghĩa bảng còn nhưng hàng vừa INSERT không còn.
7. Thử `CREATE TEMPORARY TABLE IF NOT EXISTS` hai lần với định nghĩa khác nhau. Quan sát vì sao lệnh không thay thế schema hiện tại.
8. Tạo hai bảng tạm khác tên rồi thực hiện self-join giữa chúng; so sánh với việc tham chiếu một temp table dưới hai alias.
9. Dùng `SHOW GRANTS FOR CURRENT_USER()` để kiểm tra quyền và thử tạo bảng tạm trong schema được cấp quyền.
10. Mô phỏng connection pool: tạo bảng tạm, giữ nguyên connection, kết thúc transaction rồi chạy lại workflow. Kiểm tra bảng có còn không và viết cleanup phù hợp.
11. Viết một workflow báo cáo nhiều bước, trong đó bảng tạm được tạo, nạp, join, kiểm tra kết quả và DROP trước khi connection được trả về pool.

## 15. Checklist trước khi đưa bảng tạm vào ứng dụng

- [ ] Bảng tạm chỉ cần được sử dụng trong một connection.
- [ ] Mọi câu SQL trong workflow dùng đúng connection vật lý đã tạo bảng.
- [ ] Tên bảng có prefix riêng và không vô tình che bảng nghiệp vụ.
- [ ] Engine phù hợp với kích thước dữ liệu và yêu cầu transaction.
- [ ] Kiểu dữ liệu, primary key và secondary index đã được xác định.
- [ ] Đã kiểm tra quyền `CREATE TEMPORARY TABLES`.
- [ ] Không giả định CREATE/DROP temporary table có thể rollback.
- [ ] Đã biết giới hạn `Can't reopen table` và giới hạn foreign key.
- [ ] Đã có DROP trong cleanup kể cả khi workflow lỗi.
- [ ] Connection chỉ được trả về pool sau khi cleanup hoàn tất.
- [ ] Đã kiểm tra hành vi khi request tiếp theo tái sử dụng cùng connection.
- [ ] Không dùng temporary table cho dữ liệu cần chia sẻ hoặc lưu bền vững.

## 16. Tiêu chí hoàn thành

Bạn hoàn thành bài khi có thể tạo và xóa temporary table, chứng minh phạm vi nhìn thấy chỉ thuộc connection tạo ra bảng, giải thích name shadowing, phân biệt session scope với transaction scope, chọn cách tạo bảng từ schema hoặc SELECT, xử lý cleanup khi dùng connection pool và nhận biết các giới hạn như `Can't reopen table` cùng việc không hỗ trợ foreign key. Bạn cũng cần biết khi nào bảng tạm phù hợp cho dữ liệu trung gian và khi nào nên dùng bảng thường hoặc một truy vấn CTE/derived table.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual — CREATE TEMPORARY TABLE Statement](https://dev.mysql.com/doc/refman/8.4/en/create-table.html)
- [MySQL 8.4 Reference Manual — TEMPORARY Table Problems](https://dev.mysql.com/doc/refman/8.4/en/temporary-table-problems.html)
- [MySQL 8.4 Reference Manual — DROP TABLE Statement](https://dev.mysql.com/doc/refman/8.4/en/drop-table.html)
- [MySQL 8.4 Reference Manual — Statements That Cause an Implicit Commit](https://dev.mysql.com/doc/refman/8.4/en/implicit-commit.html)
- [MySQL 8.4 Reference Manual — GRANT Statement](https://dev.mysql.com/doc/refman/8.4/en/grant.html)
