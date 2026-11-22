# Chuyển engine và kiểm tra lại dữ liệu, ràng buộc, chỉ mục

## Mục tiêu

Sau bài này, bạn có thể:

- Chuyển một bảng MySQL từ storage engine này sang engine khác bằng DDL phù hợp.
- Đánh giá ảnh hưởng của việc chuyển engine tới dữ liệu, transaction, khóa, index và các ràng buộc.
- Kiểm tra trước dữ liệu có thể gây lỗi khi thêm `NOT NULL`, `UNIQUE` hoặc foreign key.
- Đối chiếu định nghĩa bảng, số lượng và nội dung dữ liệu trước/sau chuyển đổi.
- Lập kế hoạch chuyển đổi có backup, kiểm soát ghi đồng thời, thời gian bảo trì và phương án khôi phục.

## 1. Vì sao phải kiểm tra sau khi chuyển engine?

Storage engine quyết định cách MySQL lưu trữ và xử lý dữ liệu của bảng. Chuyển từ MyISAM sang InnoDB, chẳng hạn, có thể mang lại transaction, khóa dòng và foreign key. Tuy nhiên, thao tác chuyển đổi có thể dựng lại cấu trúc vật lý của bảng, tạo lại index và làm thay đổi hành vi về khóa, phục hồi hoặc cập nhật đồng thời.

Một lệnh `ALTER TABLE` thành công chỉ cho biết server đã hoàn thành thao tác DDL. Nó chưa chứng minh rằng:

- Mọi giá trị được chuyển đổi mà không bị cắt, làm tròn hoặc ép kiểu ngoài ý muốn.
- Các index và unique constraint cần thiết vẫn tồn tại đúng thứ tự cột.
- Các quan hệ tham chiếu đã được tạo và không có bản ghi mồ côi.
- Ứng dụng vẫn hoạt động đúng với transaction, isolation level và hành vi khóa mới.
- Hiệu năng truy vấn vẫn đáp ứng yêu cầu.

Vì vậy, chuyển engine phải được xem là một thay đổi dữ liệu và vận hành. Hãy ghi nhận trạng thái ban đầu, thực hiện chuyển đổi có kiểm soát, rồi xác minh lại cả cấu trúc lẫn dữ liệu.

## 2. Khảo sát bảng trước khi chuyển đổi

### 2.1. Xác định engine và định nghĩa hiện tại

Chọn đúng database và kiểm tra engine:

```sql
SELECT DATABASE();

SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ENGINE,
    TABLE_ROWS,
    DATA_LENGTH,
    INDEX_LENGTH,
    TABLE_COLLATION
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders';
```

`TABLE_ROWS` có thể là ước lượng, nhất là với InnoDB. Dùng `COUNT(*)` khi cần số lượng bản ghi chính xác. Các giá trị dung lượng trong `information_schema.TABLES` cũng được báo cáo theo cách engine cung cấp.

Lấy DDL đầy đủ:

```sql
SHOW CREATE TABLE orders\G
```

Định nghĩa này là cơ sở để kiểm tra cột, kiểu dữ liệu, default, `AUTO_INCREMENT`, primary key, unique key, index, foreign key, charset, collation, comment và engine. Lưu kết quả vào hồ sơ thay đổi để có thể so sánh sau chuyển đổi.

### 2.2. Kiểm tra cột và kiểu dữ liệu

```sql
SELECT
    COLUMN_NAME,
    ORDINAL_POSITION,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    EXTRA,
    CHARACTER_SET_NAME,
    COLLATION_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders'
ORDER BY ORDINAL_POSITION;
```

Chú ý các cột có thể bị ảnh hưởng khi đổi engine hoặc chuẩn hóa schema:

- Cột chuỗi có độ dài gần giới hạn, charset hoặc collation khác nhau.
- Cột số có `UNSIGNED`, độ chính xác hoặc scale của `DECIMAL` cần giữ nguyên.
- Cột ngày giờ có giá trị mặc định, biểu thức mặc định hoặc cách xử lý zero date phụ thuộc `sql_mode`.
- Cột `BLOB`/`TEXT`, JSON, generated column và kiểu dữ liệu đặc thù.
- Cột `AUTO_INCREMENT` và giá trị kế tiếp.
- Cột cho phép `NULL` hoặc có default ngầm định.

Chuyển engine không phải là lúc tự ý đổi kiểu dữ liệu. Nếu cần sửa schema cùng lúc, hãy tách thành thay đổi có chủ đích để có thể xác định nguyên nhân khi dữ liệu hoặc ứng dụng gặp lỗi.

### 2.3. Kiểm tra index và ràng buộc

Liệt kê index:

```sql
SHOW INDEX FROM orders;
```

Hoặc đọc metadata:

```sql
SELECT
    INDEX_NAME,
    NON_UNIQUE,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    SUB_PART,
    INDEX_TYPE,
    COLLATION
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
```

`SEQ_IN_INDEX` cho biết thứ tự cột trong index ghép; `SUB_PART` thể hiện prefix length nếu có. Khi so sánh, cần giữ đúng thứ tự cột, unique/non-unique, prefix và loại index. Chỉ so tên index là chưa đủ.

Kiểm tra constraint và foreign key:

```sql
SELECT
    tc.CONSTRAINT_NAME,
    tc.CONSTRAINT_TYPE,
    kcu.COLUMN_NAME,
    kcu.ORDINAL_POSITION,
    kcu.REFERENCED_TABLE_SCHEMA,
    kcu.REFERENCED_TABLE_NAME,
    kcu.REFERENCED_COLUMN_NAME
FROM information_schema.TABLE_CONSTRAINTS AS tc
LEFT JOIN information_schema.KEY_COLUMN_USAGE AS kcu
  ON tc.CONSTRAINT_SCHEMA = kcu.CONSTRAINT_SCHEMA
 AND tc.TABLE_NAME = kcu.TABLE_NAME
 AND tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
WHERE tc.TABLE_SCHEMA = DATABASE()
  AND tc.TABLE_NAME = 'orders'
ORDER BY tc.CONSTRAINT_NAME, kcu.ORDINAL_POSITION;
```

Kiểm tra quy tắc cập nhật/xóa của foreign key:

```sql
SELECT
    CONSTRAINT_NAME,
    UNIQUE_CONSTRAINT_SCHEMA,
    REFERENCED_TABLE_NAME,
    UPDATE_RULE,
    DELETE_RULE
FROM information_schema.REFERENTIAL_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders';
```

Ngoài constraint, cần ghi nhận trigger và view phụ thuộc vào bảng nếu chúng có liên quan đến nghiệp vụ:

```sql
SHOW TRIGGERS FROM app_db LIKE 'orders';
```

Thay `app_db` bằng database thực tế. Trigger không thay thế constraint và không nên được dùng để suy luận rằng mọi quan hệ dữ liệu đã được bảo đảm.

## 3. Kiểm tra dữ liệu trước khi chuyển đổi

### 3.1. Ghi nhận số lượng và phạm vi dữ liệu

Lấy số hàng chính xác và một số mốc dữ liệu quan trọng:

```sql
SELECT
    COUNT(*) AS row_count,
    MIN(order_id) AS min_order_id,
    MAX(order_id) AS max_order_id,
    MIN(created_at) AS first_created_at,
    MAX(created_at) AS last_created_at
FROM orders;
```

Với bảng lớn, `COUNT(*)` có thể tốn thời gian. Hãy lên kế hoạch lấy số liệu trong cửa sổ phù hợp và cân nhắc tải lên hệ thống. Nếu dữ liệu tiếp tục thay đổi trong lúc kiểm tra, các con số lấy ở những thời điểm khác nhau có thể không so sánh trực tiếp được.

### 3.2. Tìm giá trị NULL trước khi thêm NOT NULL

Nếu dự định thay đổi cột `customer_id` thành `NOT NULL`, hãy tìm dữ liệu vi phạm trước:

```sql
SELECT COUNT(*) AS null_customer_ids
FROM orders
WHERE customer_id IS NULL;
```

Nếu kết quả lớn hơn 0, cần quyết định cách xử lý từng trường hợp: bổ sung giá trị đúng từ nguồn nghiệp vụ, chuyển bản ghi sang vùng cách ly hoặc giữ khả năng `NULL` nếu đó là trạng thái hợp lệ. Không tự điền một giá trị giả chỉ để DDL chạy được.

### 3.3. Tìm dữ liệu trùng trước khi thêm UNIQUE

Ví dụ dự định tạo unique index trên `external_ref`:

```sql
SELECT external_ref, COUNT(*) AS duplicate_count
FROM orders
WHERE external_ref IS NOT NULL
GROUP BY external_ref
HAVING COUNT(*) > 1;
```

Nếu unique key gồm nhiều cột, nhóm theo đầy đủ các cột của key:

```sql
SELECT tenant_id, external_ref, COUNT(*) AS duplicate_count
FROM orders
GROUP BY tenant_id, external_ref
HAVING COUNT(*) > 1;
```

MySQL cho phép nhiều giá trị `NULL` trong unique index theo quy tắc của nó. Nếu nghiệp vụ yêu cầu mỗi bản ghi phải có giá trị duy nhất và không rỗng, cần kiểm tra cả `NULL` và trùng lặp.

### 3.4. Kiểm tra dữ liệu mồ côi trước khi thêm foreign key

Giả sử `orders.customer_id` sẽ tham chiếu `customers.customer_id`. Tìm đơn hàng không có khách hàng tương ứng:

```sql
SELECT o.order_id, o.customer_id
FROM orders AS o
LEFT JOIN customers AS c
  ON c.customer_id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.customer_id IS NULL;
```

Nếu truy vấn trả về hàng, không thể thêm foreign key mà vẫn bảo đảm toàn vẹn tham chiếu. Cần xác định đây là dữ liệu lỗi, khách hàng đã bị xóa, hay quy tắc nghiệp vụ cho phép thiếu tham chiếu. Sửa dữ liệu theo quyết định nghiệp vụ rồi chạy lại kiểm tra.

### 3.5. Kiểm tra giá trị có thể bị chuyển đổi

Nếu thay đổi kiểu dữ liệu cùng lúc, hãy tìm giá trị vượt giới hạn hoặc không chuyển đổi được trước khi chạy DDL. Ví dụ, khi muốn chuyển một cột chuỗi thành số:

```sql
SELECT order_id, legacy_amount
FROM orders
WHERE legacy_amount IS NOT NULL
  AND TRIM(legacy_amount) NOT REGEXP '^-?[0-9]+([.][0-9]+)?$';
```

Đây chỉ là kiểm tra định dạng số thập phân đơn giản; dữ liệu tiền tệ còn cần xác định precision và scale. Không dùng một biểu thức kiểm tra tổng quát thay cho quy tắc nghiệp vụ của từng cột.

Đối với chuỗi, kiểm tra độ dài trước khi giảm kích thước cột:

```sql
SELECT MAX(CHAR_LENGTH(external_ref)) AS max_char_length,
       MAX(OCTET_LENGTH(external_ref)) AS max_byte_length
FROM orders;
```

`CHAR_LENGTH` đếm ký tự; `OCTET_LENGTH` đếm byte. Với charset nhiều byte như `utf8mb4`, hai giá trị có thể khác nhau đáng kể.

## 4. Chuyển engine bằng ALTER TABLE

### 4.1. Kiểm tra engine đích

Trước tiên, xác nhận engine đích được hỗ trợ:

```sql
SHOW ENGINES;
```

Nếu chuyển sang InnoDB, xác nhận InnoDB có trạng thái hỗ trợ phù hợp. Không dựa vào `default_storage_engine` vì biến này chỉ là mặc định cho bảng mới không chỉ định engine.

### 4.2. Thực hiện chuyển đổi

Ví dụ chuyển bảng `orders` sang InnoDB:

```sql
ALTER TABLE orders ENGINE = InnoDB;
```

Kiểm tra ngay kết quả và cảnh báo của DDL:

```sql
SHOW WARNINGS;

SELECT TABLE_NAME, ENGINE
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders';
```

`ALTER TABLE ... ENGINE = ...` có thể dựng lại bảng và index theo định dạng của engine đích. Thời gian chạy phụ thuộc kích thước bảng, số index, tốc độ I/O, hoạt động đồng thời và cách triển khai của phiên bản MySQL.

### 4.3. Chuyển engine không phải thao tác rollback thông thường

DDL như `ALTER TABLE` có quy tắc implicit commit; không thể bọc chuyển engine trong transaction ứng dụng rồi gọi `ROLLBACK` để hoàn tác như một nhóm `UPDATE` InnoDB. Hãy xem đây là thay đổi cấu trúc cần backup và phương án khôi phục độc lập.

Khả năng online DDL và mức khóa phụ thuộc engine nguồn/đích, loại thay đổi, phiên bản và cấu trúc bảng. Không mặc định rằng chuyển engine luôn chạy `ALGORITHM=INPLACE` hoặc `LOCK=NONE`. Có thể kiểm tra tài liệu phiên bản và thử trước trên bản sao có kích thước tương đương. Nếu chỉ định một algorithm/lock không được hỗ trợ, server có thể từ chối thay đổi; không nên ép tùy chọn online mà chưa xác minh.

Trong thời gian chuyển đổi, cần tính đến:

- Metadata lock có thể làm các truy vấn DDL hoặc DML khác phải chờ.
- Có thể cần thêm dung lượng đĩa tạm để dựng bảng mới và index.
- CPU và I/O tăng có thể ảnh hưởng workload production.
- DDL có thể chờ transaction dài đang giữ metadata lock.
- Với bảng lớn, thời gian khóa và thời gian hoàn tất có thể đáng kể.

### 4.4. Chuyển nhiều bảng có quan hệ

Nếu các bảng liên kết bằng foreign key, hãy lập danh sách parent và child. InnoDB yêu cầu các bảng tham gia quan hệ foreign key đều sử dụng engine hỗ trợ phù hợp; trong MySQL thông dụng, cả hai phía dùng InnoDB.

Thực hiện chuyển đổi theo kế hoạch cho toàn bộ nhóm bảng liên quan. Sau mỗi bước, kiểm tra constraint và dữ liệu. Không cho rằng chỉ chuyển bảng con hoặc bảng cha là đủ để tạo quan hệ tham chiếu hợp lệ.

## 5. Kiểm tra lại dữ liệu sau khi chuyển engine

### 5.1. Kiểm tra số lượng và các mốc dữ liệu

Chạy lại truy vấn đếm và tổng hợp đã lưu trước chuyển đổi:

```sql
SELECT
    COUNT(*) AS row_count,
    MIN(order_id) AS min_order_id,
    MAX(order_id) AS max_order_id,
    MIN(created_at) AS first_created_at,
    MAX(created_at) AS last_created_at
FROM orders;
```

Đối chiếu với baseline. Với bảng nghiệp vụ, nên kiểm tra thêm tổng tiền, số hàng theo trạng thái, theo ngày hoặc theo tenant:

```sql
SELECT
    DATE(created_at) AS order_date,
    status,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_amount
FROM orders
GROUP BY DATE(created_at), status
ORDER BY order_date, status;
```

Các tổng hợp phải được chạy trên cùng một phạm vi dữ liệu hoặc tại một thời điểm nhất quán. Nếu ứng dụng vẫn ghi trong khi chuyển đổi hoặc giữa hai lần đo, chênh lệch có thể đến từ giao dịch mới chứ không phải mất dữ liệu.

### 5.2. Kiểm tra nội dung theo khóa

Với dữ liệu quan trọng, đối chiếu theo khóa chính theo từng khoảng nhỏ. Ví dụ kiểm tra một khoảng `order_id`:

```sql
SELECT
    order_id,
    customer_id,
    status,
    total_amount,
    created_at
FROM orders
WHERE order_id BETWEEN 100000 AND 109999
ORDER BY order_id;
```

Trong quy trình migration lớn, có thể xuất dữ liệu theo batch và tạo hash xác định ở tầng ứng dụng hoặc công cụ ETL. Cần chuẩn hóa cách biểu diễn `NULL`, charset, timezone và kiểu số trước khi tính hash. Không chỉ dựa vào `COUNT(*)` hoặc một tổng duy nhất để kết luận hai tập dữ liệu giống hệt nhau.

### 5.3. Kiểm tra giá trị NULL, độ dài và miền giá trị

Chạy lại các truy vấn kiểm tra dữ liệu ở bước preflight. Ví dụ:

```sql
SELECT COUNT(*) AS null_customer_ids
FROM orders
WHERE customer_id IS NULL;

SELECT MAX(CHAR_LENGTH(external_ref)) AS max_external_ref_length
FROM orders;

SELECT COUNT(*) AS invalid_amounts
FROM orders
WHERE total_amount < 0;
```

Điều kiện `total_amount < 0` chỉ phù hợp nếu nghiệp vụ không cho phép số âm; với hoàn tiền hoặc điều chỉnh, số âm có thể là hợp lệ. Mọi phép kiểm tra phải xuất phát từ quy tắc dữ liệu của hệ thống.

## 6. Kiểm tra lại index

### 6.1. Đối chiếu định nghĩa index

Sau chuyển đổi, chạy:

```sql
SHOW INDEX FROM orders;
SHOW CREATE TABLE orders\G
```

So sánh với kết quả trước chuyển đổi:

- Primary key có còn đúng không?
- Unique index có giữ nguyên tính duy nhất và thứ tự cột không?
- Index ghép có đúng thứ tự cột và prefix length không?
- Index `FULLTEXT`, `SPATIAL`, functional hoặc index đặc thù có còn được hỗ trợ không?
- Index có tên, loại và thuộc tính mong đợi không?

Khả năng hỗ trợ index phụ thuộc engine và phiên bản. Một index hợp lệ ở engine nguồn có thể không được engine đích hỗ trợ hoặc cần định nghĩa lại. Hãy xem DDL thực tế sau chuyển đổi, không chỉ nhìn câu lệnh cũ.

### 6.2. Kiểm tra index unique và dữ liệu trùng

Nếu cần tạo lại unique index, kiểm tra trùng trước:

```sql
SELECT external_ref, COUNT(*) AS duplicate_count
FROM orders
WHERE external_ref IS NOT NULL
GROUP BY external_ref
HAVING COUNT(*) > 1;
```

Sau khi xử lý dữ liệu và xác nhận yêu cầu nghiệp vụ, có thể tạo unique index:

```sql
ALTER TABLE orders
ADD CONSTRAINT uq_orders_external_ref UNIQUE (external_ref);
```

Đừng tạo constraint chỉ vì dữ liệu hiện tại tình cờ không trùng. Unique key phải phản ánh quy tắc nghiệp vụ và cách xử lý `NULL`.

### 6.3. Cập nhật thống kê và kiểm tra kế hoạch truy vấn

Sau khi chuyển engine và tạo lại index cần thiết, cập nhật thống kê:

```sql
ANALYZE TABLE orders;
```

Sau đó kiểm tra các truy vấn quan trọng:

```sql
EXPLAIN
SELECT order_id, total_amount
FROM orders
WHERE customer_id = 101
  AND created_at >= '2026-01-01'
ORDER BY created_at DESC;
```

So sánh access type, key được chọn, số hàng ước lượng và thứ tự join với baseline. Engine mới có thể dùng cơ chế optimizer, thống kê và khóa khác nhau. Không kết luận hiệu năng tốt hơn chỉ vì bảng đã chuyển sang InnoDB; hãy benchmark bằng dữ liệu và tải gần production.

## 7. Kiểm tra lại constraint và quan hệ tham chiếu

### 7.1. Xác nhận constraint tồn tại

```sql
SELECT
    CONSTRAINT_NAME,
    CONSTRAINT_TYPE
FROM information_schema.TABLE_CONSTRAINTS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders'
ORDER BY CONSTRAINT_TYPE, CONSTRAINT_NAME;
```

Đối chiếu danh sách primary key, unique key, check constraint (nếu phiên bản hỗ trợ) và foreign key với DDL đã lưu. Không giả định engine đích tự tạo các constraint vốn không được engine nguồn thực thi.

### 7.2. Thêm foreign key sau khi xác minh dữ liệu

Ví dụ thêm quan hệ `orders.customer_id` tới `customers.customer_id`:

```sql
ALTER TABLE orders
ADD CONSTRAINT fk_orders_customer
FOREIGN KEY (customer_id)
REFERENCES customers (customer_id)
ON UPDATE RESTRICT
ON DELETE RESTRICT;
```

Trước khi chạy, kiểm tra:

- Hai bảng đều dùng engine hỗ trợ foreign key.
- Cột tham chiếu và cột được tham chiếu có kiểu dữ liệu tương thích, gồm kích thước và signedness đối với kiểu số.
- Với cột chuỗi, charset và collation phù hợp.
- Cột được tham chiếu có index phù hợp và thỏa quy tắc của MySQL.
- Không có hàng mồ côi trong bảng con.
- Hành vi `ON UPDATE` và `ON DELETE` đúng với nghiệp vụ.

Kiểm tra lại orphan sau khi thêm constraint:

```sql
SELECT o.order_id, o.customer_id
FROM orders AS o
LEFT JOIN customers AS c
  ON c.customer_id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.customer_id IS NULL;
```

Kết quả rỗng là dấu hiệu tốt cho quan hệ đang kiểm tra, nhưng vẫn cần xác nhận constraint tồn tại trong `information_schema` và ứng dụng xử lý đúng lỗi vi phạm.

### 7.3. Không dùng foreign_key_checks để bỏ qua kiểm tra dữ liệu

MySQL có biến `foreign_key_checks` để điều khiển kiểm tra foreign key trong một số thao tác. Tắt biến này không phải cách sửa dữ liệu mồ côi. Khi bật lại, MySQL không tự quét và xác thực toàn bộ dữ liệu đã được nạp trong thời gian kiểm tra bị tắt.

Vì vậy, không dùng `SET foreign_key_checks = 0` như một cách làm cho migration “chạy qua” rồi kết luận dữ liệu hợp lệ. Nếu quy trình đặc biệt cần tắt kiểm tra, phải có bước kiểm tra tham chiếu độc lập trước khi cho ứng dụng sử dụng dữ liệu.

## 8. Kiểm tra hành vi ứng dụng sau chuyển engine

Chuyển từ engine không hỗ trợ transaction sang InnoDB có thể làm ứng dụng thay đổi hành vi theo hướng tích cực, nhưng cũng có thể làm lộ ra giả định cũ về khóa hoặc thứ tự cập nhật. Hãy kiểm tra:

- **Transaction:** commit, rollback, savepoint và xử lý lỗi giữa nhiều câu lệnh.
- **Isolation:** mức cô lập và kết quả đọc khi có nhiều transaction đồng thời.
- **Locking:** khóa dòng, gap/next-key lock, deadlock và thời gian chờ khóa.
- **Constraint:** ứng dụng có xử lý lỗi duplicate key, foreign key và giá trị `NOT NULL` đúng cách không?
- **AUTO_INCREMENT:** giá trị kế tiếp có phù hợp với dữ liệu và quy trình ghi không?
- **SQL mode, charset, collation:** so sánh chuỗi, ép kiểu và giá trị ngày giờ có thay đổi không?
- **Backup/restore:** công cụ backup hiện tại có hỗ trợ engine đích và khôi phục được dữ liệu không?
- **Replication/HA:** cấu hình binlog, replica, failover và giám sát có tiếp tục hoạt động đúng không?

Đặc biệt, khi chuyển từ MyISAM sang InnoDB, cơ chế khóa thay đổi từ khóa bảng sang các cơ chế khóa của InnoDB. Truy vấn đọc/ghi đồng thời có thể có mức song song khác, nhưng deadlock và lock wait vẫn có thể xảy ra. Ứng dụng cần xử lý retry có giới hạn cho các lỗi transaction có thể thử lại.

## 9. Kế hoạch chuyển đổi an toàn cho production

### 9.1. Chuẩn bị

1. Xác định phiên bản MySQL, engine nguồn/đích và khả năng hỗ trợ DDL.
2. Lưu `SHOW CREATE TABLE`, metadata cột, index, constraint, trigger và các truy vấn nghiệp vụ quan trọng.
3. Kiểm tra dữ liệu `NULL`, trùng lặp, orphan, độ dài và miền giá trị.
4. Đo kích thước bảng/index, tốc độ ghi, thời gian truy vấn và dung lượng đĩa khả dụng.
5. Tạo backup có thể khôi phục và thử restore trên môi trường tương đương.
6. Thử chuyển đổi trên bản sao dữ liệu có kích thước gần production.

### 9.2. Thực hiện

1. Chọn cửa sổ bảo trì hoặc cơ chế migration phù hợp với yêu cầu downtime.
2. Nếu cần dữ liệu nhất quán đơn giản, tạm dừng ghi vào bảng trong thời gian chuyển đổi và thông báo các thành phần phụ thuộc.
3. Chạy DDL chuyển engine; theo dõi thời gian, metadata lock, CPU, I/O và dung lượng đĩa.
4. Đọc cảnh báo/lỗi và xác nhận engine đích đã được áp dụng.
5. Tạo hoặc khôi phục các index, constraint chưa được bảo toàn theo kế hoạch.

Nếu không thể dừng ghi, cần một phương án online migration có cơ chế đồng bộ thay đổi trong lúc copy, kiểm tra độ trễ và chuyển đổi endpoint có kiểm soát. Công cụ như `pt-online-schema-change` hoặc `gh-ost` có giới hạn riêng về foreign key, trigger, loại DDL và phiên bản; phải thử trước, không mặc định chúng hỗ trợ mọi ca chuyển engine.

### 9.3. Xác minh và đưa ứng dụng trở lại

1. So sánh số hàng, min/max key, tổng hợp nghiệp vụ và dữ liệu theo batch.
2. Đối chiếu DDL, index, constraint và trigger với baseline.
3. Chạy kiểm tra orphan, duplicate và các quy tắc dữ liệu quan trọng.
4. Chạy smoke test và integration test trên ứng dụng.
5. Benchmark truy vấn trọng yếu và theo dõi lock, deadlock, CPU, I/O.
6. Mở lại luồng ghi khi các kiểm tra bắt buộc đạt yêu cầu.
7. Theo dõi sau chuyển đổi và lưu lại kết quả để phục vụ rollback hoặc điều tra.

### 9.4. Phương án khôi phục

Nếu kết quả xác minh không đạt, dừng rollout và dùng phương án đã chuẩn bị. Với thay đổi DDL, không dựa vào `ROLLBACK` của transaction để quay lại engine cũ. Phương án có thể là khôi phục backup, chuyển traffic về bản dữ liệu cũ hoặc chạy một migration ngược đã được thử nghiệm. Nếu ứng dụng đã ghi dữ liệu mới vào bảng sau chuyển đổi, cần xác định cách đồng bộ các thay đổi đó trước khi quay lại bản cũ.

## 10. Checklist sau chuyển engine

| Hạng mục | Điều kiện xác nhận |
|---|---|
| Engine | `information_schema.TABLES.ENGINE` là engine đích |
| DDL | Cột, kiểu dữ liệu, default, charset/collation và thuộc tính bảng đúng như kế hoạch |
| Số lượng dữ liệu | `COUNT(*)` hoặc đối soát batch khớp tại cùng phạm vi dữ liệu |
| Giá trị dữ liệu | Các tổng hợp nghiệp vụ, khóa và hash theo batch không có sai lệch chưa giải thích |
| Index | Primary, unique, index ghép, prefix và index đặc thù được xác minh |
| Constraint | Primary key, unique, check và foreign key tồn tại đúng như yêu cầu |
| Tham chiếu | Không có bản ghi mồ côi trong các quan hệ đã kiểm tra |
| AUTO_INCREMENT | Giá trị kế tiếp phù hợp với khóa hiện có và quy trình ghi |
| Truy vấn | `EXPLAIN` và benchmark của truy vấn quan trọng đạt yêu cầu |
| Ứng dụng | Transaction, locking, retry và xử lý constraint hoạt động đúng |
| Vận hành | Backup/restore, replication, giám sát và phương án khôi phục đã được xác nhận |

## 11. Kết luận

Chuyển storage engine bằng `ALTER TABLE ... ENGINE = ...` có thể dựng lại bảng và index, thay đổi hành vi transaction, khóa và khả năng ràng buộc. Vì vậy, cần khảo sát DDL và dữ liệu trước chuyển đổi, kiểm tra giới hạn của engine đích, rồi xác minh lại số lượng, giá trị, index, constraint và hành vi ứng dụng.

Một lần chuyển đổi chỉ nên được xem là hoàn tất khi dữ liệu được đối soát, cấu trúc bảng đáp ứng yêu cầu, truy vấn quan trọng đã được kiểm tra và phương án backup/restore hoạt động. Với production, hãy thử trên bản sao tương đương, kiểm soát ghi đồng thời và chuẩn bị phương án khôi phục trước khi bắt đầu.
