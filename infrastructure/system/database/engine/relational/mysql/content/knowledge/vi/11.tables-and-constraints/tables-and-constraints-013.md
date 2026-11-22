# Phân biệt DELETE, TRUNCATE, DROP và ảnh hưởng giao dịch

Khi cần loại bỏ dữ liệu khỏi MySQL, có ba lệnh thường được nhắc đến: `DELETE`, `TRUNCATE TABLE` và `DROP TABLE`. Cả ba đều có thể khiến dữ liệu không còn truy cập được, nhưng phạm vi tác động và hành vi giao dịch rất khác nhau. Chọn nhầm lệnh có thể làm mất cấu trúc bảng, bỏ qua trigger, reset bộ đếm `AUTO_INCREMENT` hoặc commit một transaction đang thực hiện.

Trong module **DATABASE_MYSQL**, cần hiểu các lệnh này ở cả hai góc độ: thao tác dữ liệu và thao tác cấu trúc. Bài học tập trung vào MySQL với InnoDB, giải thích khả năng rollback, implicit commit, khóa ngoại, trigger, quyền cần có và cách chọn lệnh phù hợp.

## 1. So sánh nhanh ba lệnh

| Tiêu chí | `DELETE` | `TRUNCATE TABLE` | `DROP TABLE` |
|---|---|---|---|
| Nhóm lệnh | DML | DDL | DDL |
| Mục tiêu | Xóa một số hoặc tất cả các hàng | Xóa toàn bộ hàng, giữ bảng rỗng | Xóa hẳn bảng và định nghĩa của bảng |
| Có `WHERE`? | Có | Không | Không |
| Giữ cấu trúc bảng, index và constraint? | Có | Có | Không |
| Có thể rollback với InnoDB? | Có, nếu chưa commit | Không | Không |
| Có implicit commit? | Không | Có | Có |
| Trigger `DELETE` chạy? | Có, cho từng hàng bị xóa | Không | Không chạy trigger `DELETE` cho từng hàng |
| Tác động `AUTO_INCREMENT` | Không reset bộ đếm chỉ vì xóa hết hàng | Reset về giá trị bắt đầu của bảng | Bảng và bộ đếm bị loại bỏ cùng bảng |
| Quyền chính cần có | `DELETE` | `DROP` | `DROP` |
| Khi dùng | Xóa dữ liệu có điều kiện hoặc cần transaction | Làm rỗng toàn bộ bảng có chủ đích | Loại bỏ bảng không còn cần thiết |

Điểm cần nhớ: `DELETE` tác động lên các hàng; `TRUNCATE` làm rỗng bảng bằng thao tác DDL; `DROP` loại bỏ chính đối tượng bảng.

## 2. `DELETE` — xóa hàng trong bảng

`DELETE` xóa các hàng thỏa điều kiện `WHERE`. Bảng, cột, index và constraint vẫn tồn tại sau khi câu lệnh hoàn tất.

```sql
-- Xóa một đơn hàng cụ thể
DELETE FROM orders
WHERE order_id = 105;

-- Xóa các đơn hàng đã bị hủy trước một mốc ngày
DELETE FROM orders
WHERE status = 'CANCELLED'
  AND created_at < '2025-01-01';
```

Nếu bỏ `WHERE`, MySQL xóa toàn bộ hàng trong bảng:

```sql
DELETE FROM orders;
```

Lệnh trên vẫn giữ bảng `orders` và các định nghĩa của nó. Tuy nhiên, nó có thể xóa một lượng dữ liệu rất lớn, chạy lâu, tạo nhiều undo/redo và ảnh hưởng đến các transaction khác. Hãy kiểm tra điều kiện bằng `SELECT` trước khi chạy lệnh xóa trên dữ liệu thật.

### DELETE có thể rollback với InnoDB

Với bảng InnoDB, `DELETE` là thao tác transactional. Nếu transaction chưa commit, có thể hoàn tác:

```sql
START TRANSACTION;

DELETE FROM orders
WHERE order_id = 105;

-- Kiểm tra trong transaction hiện tại
SELECT *
FROM orders
WHERE order_id = 105;

ROLLBACK;

-- Hàng đã được phục hồi sau rollback
SELECT *
FROM orders
WHERE order_id = 105;
```

Nếu gọi `COMMIT` thay cho `ROLLBACK`, thao tác xóa được xác nhận. Khả năng rollback này phụ thuộc storage engine: với engine không hỗ trợ transaction như MyISAM, `ROLLBACK` không phục hồi các hàng đã xóa.

### DELETE kích hoạt trigger và khóa ngoại

Trigger `BEFORE DELETE` và `AFTER DELETE` được kích hoạt cho các hàng bị xóa. Nếu bảng có khóa ngoại, hành động `ON DELETE` được áp dụng theo định nghĩa quan hệ:

- `RESTRICT`/`NO ACTION`: từ chối xóa hàng cha nếu còn hàng con tham chiếu.
- `CASCADE`: xóa các hàng con liên quan.
- `SET NULL`: đặt cột khóa ngoại ở hàng con thành `NULL`, nếu cột cho phép `NULL`.

Ví dụ, nếu `orders.customer_id` tham chiếu `customers.customer_id` với `ON DELETE RESTRICT`, lệnh xóa khách hàng đang có đơn hàng sẽ bị từ chối. Nếu khóa ngoại dùng `ON DELETE CASCADE`, xóa khách hàng có thể kéo theo các đơn hàng. Hãy kiểm tra toàn bộ quan hệ trước khi thực hiện.

### DELETE không tự reset AUTO_INCREMENT

Xóa toàn bộ hàng bằng `DELETE` không đặt lại bộ đếm `AUTO_INCREMENT` của InnoDB:

```sql
DELETE FROM import_queue;
```

Nếu bảng trước đó đã cấp ID đến 500, hàng mới có thể tiếp tục nhận ID lớn hơn 500. Đây thường là hành vi mong muốn vì ID đã phát hành không bị tái sử dụng chỉ do dữ liệu cũ được xóa.

MySQL còn hỗ trợ `DELETE` kết hợp `ORDER BY` và `LIMIT` trong cú pháp single-table, hữu ích khi xóa theo từng đợt:

```sql
DELETE FROM event_logs
WHERE created_at < '2024-01-01'
ORDER BY created_at
LIMIT 1000;
```

Có thể lặp lại theo batch để giảm thời gian giữ khóa và lượng undo trong một transaction. Cần có điều kiện lọc ổn định, index phù hợp và kiểm soát số lần chạy để tránh xóa quá phạm vi.

## 3. `TRUNCATE TABLE` — làm rỗng toàn bộ bảng

`TRUNCATE TABLE` xóa toàn bộ hàng nhưng giữ định nghĩa bảng:

```sql
TRUNCATE TABLE import_queue;
```

Sau lệnh này, bảng `import_queue` vẫn tồn tại cùng cột, index, constraint và trigger. Dữ liệu hàng đã bị loại bỏ. `TRUNCATE` không nhận `WHERE`, nên không thể dùng để xóa một phần dữ liệu.

### Vì sao TRUNCATE thường nhanh hơn DELETE toàn bảng?

Với InnoDB, `TRUNCATE TABLE` được thực hiện như một thao tác DDL làm mới bảng, về bản chất là drop và tạo lại tablespace/bảng theo cơ chế của MySQL. Nó tránh việc xóa từng hàng theo cách của `DELETE`, vì vậy thường hiệu quả hơn khi cần làm rỗng toàn bộ bảng lớn.

Hiệu năng thực tế còn phụ thuộc metadata lock, kích thước bảng, engine, filesystem và hoạt động đồng thời. `TRUNCATE` không đồng nghĩa với việc lệnh luôn hoàn tất tức thì hoặc không ảnh hưởng đến ứng dụng đang dùng bảng.

### TRUNCATE reset AUTO_INCREMENT

Với bảng có `AUTO_INCREMENT`, `TRUNCATE TABLE` đặt lại bộ đếm về giá trị bắt đầu của bảng:

```sql
TRUNCATE TABLE import_queue;

INSERT INTO import_queue (payload)
VALUES ('next message');
```

ID mới sẽ bắt đầu lại theo cấu hình khởi đầu của bảng. Nếu yêu cầu giữ nguyên dãy ID đã phát hành, không dùng `TRUNCATE` chỉ vì muốn xóa dữ liệu.

### TRUNCATE không kích hoạt DELETE trigger

`TRUNCATE TABLE` không xóa hàng theo từng câu lệnh `DELETE`, nên trigger `BEFORE DELETE`/`AFTER DELETE` không được kích hoạt. Nếu hệ thống dựa vào trigger để ghi audit, cập nhật bảng tổng hợp hoặc đồng bộ dữ liệu, `TRUNCATE` có thể bỏ qua các tác động đó.

Ví dụ, nếu `orders` có trigger ghi lịch sử xóa vào `order_audit`, câu `DELETE FROM orders` có thể kích hoạt trigger cho từng hàng; `TRUNCATE TABLE orders` không tạo các bản ghi audit đó.

### TRUNCATE và khóa ngoại

Trong MySQL, không thể `TRUNCATE` một bảng InnoDB đang được bảng khác tham chiếu bằng khóa ngoại. Ví dụ, nếu `orders.customer_id` tham chiếu `customers.customer_id`, lệnh `TRUNCATE TABLE customers` sẽ bị từ chối khi quan hệ đó tồn tại, kể cả khi bảng con hiện không có hàng tham chiếu. Cần xử lý quan hệ theo thiết kế, hoặc dùng cách xóa dữ liệu phù hợp trong schema thử nghiệm.

Không tắt `foreign_key_checks` chỉ để ép truncate. Việc tắt kiểm tra không phải cách thay thế cho thiết kế xóa dữ liệu có kiểm soát; bật lại không tự xác minh toàn bộ dữ liệu được ghi trong thời gian kiểm tra bị tắt.

## 4. `DROP TABLE` — xóa hẳn bảng

`DROP TABLE` loại bỏ bảng khỏi database:

```sql
DROP TABLE import_queue;
```

Sau lệnh này, bảng không còn tồn tại. Định nghĩa cột, dữ liệu, index, trigger gắn với bảng và các constraint thuộc bảng bị loại bỏ cùng đối tượng. Các câu `SELECT`, `INSERT`, `UPDATE` hoặc `DELETE` tham chiếu bảng sau đó sẽ báo lỗi vì bảng không còn.

Có thể kiểm tra trước khi xóa:

```sql
SHOW CREATE TABLE import_queue;
SELECT COUNT(*) FROM import_queue;
```

Sau đó mới chạy `DROP TABLE` khi đã xác nhận bảng thực sự không còn cần thiết. Nếu muốn xóa bảng chỉ khi nó tồn tại, có thể dùng:

```sql
DROP TABLE IF EXISTS import_queue;
```

`IF EXISTS` tránh lỗi khi bảng không tồn tại; nó không biến thao tác thành an toàn hoặc có thể rollback.

### DROP TABLE và khóa ngoại

Nếu bảng đang bị bảng khác tham chiếu bằng khóa ngoại, MySQL thường từ chối `DROP TABLE` khi kiểm tra khóa ngoại được bật. Nếu xóa bảng con, constraint thuộc bảng con sẽ bị loại bỏ cùng bảng. Nếu cần xóa cả một nhóm bảng có quan hệ, hãy lập kế hoạch theo dependency và backup trước; không tùy tiện tắt `foreign_key_checks` để bỏ qua ràng buộc.

`DROP TABLE` khác với `DELETE` ở chỗ nó xóa cả cấu trúc. Muốn sử dụng lại bảng sau `DROP`, phải tạo lại bảng bằng DDL hoặc khôi phục từ backup/migration. Dữ liệu không thể phục hồi bằng `ROLLBACK`.

## 5. Ảnh hưởng đến transaction và implicit commit

Đây là khác biệt quan trọng nhất khi lựa chọn lệnh:

| Lệnh | Có thể nằm trong transaction InnoDB? | Tác động đến transaction đang mở |
|---|---|---|
| `DELETE` | Có | Không tự commit; có thể `COMMIT` hoặc `ROLLBACK` cùng transaction |
| `TRUNCATE TABLE` | Không theo nghĩa DML có thể rollback | Gây implicit commit; thao tác truncate không thể hoàn tác bằng `ROLLBACK` |
| `DROP TABLE` | Không theo nghĩa DML có thể rollback | Gây implicit commit; thao tác drop không thể hoàn tác bằng `ROLLBACK` |

`TRUNCATE` và `DROP` là DDL. MySQL thực hiện implicit commit đối với transaction đang mở trước khi chạy các lệnh này; các lệnh DDL này cũng kết thúc transaction riêng của chúng. Vì vậy, một `ROLLBACK` sau đó không thể phục hồi bảng đã truncate/drop hoặc hoàn tác các thay đổi DML đã bị commit bởi implicit commit.

### Minh họa DELETE có thể rollback

Chạy trong một schema thử nghiệm với bảng InnoDB:

```sql
START TRANSACTION;

DELETE FROM transaction_probe
WHERE id = 10;

ROLLBACK;
```

Hàng `id = 10` được phục hồi nếu transaction chưa bị commit và không có thao tác implicit commit chen vào.

### Minh họa implicit commit của TRUNCATE

Giả sử có hai bảng thử nghiệm InnoDB độc lập: `transaction_probe` và `truncate_probe`. Chạy:

```sql
START TRANSACTION;

INSERT INTO transaction_probe (id, note)
VALUES (9001, 'insert before truncate');

TRUNCATE TABLE truncate_probe;

ROLLBACK;
```

Khi `TRUNCATE TABLE` được thực hiện, MySQL implicit commit transaction đang mở trước đó. Vì vậy, dòng `9001` trong `transaction_probe` đã được commit và vẫn còn sau `ROLLBACK`. Bảng `truncate_probe` đã được làm rỗng và thao tác đó cũng không thể rollback.

`DROP TABLE` có cùng rủi ro implicit commit:

```sql
START TRANSACTION;

UPDATE transaction_probe
SET note = 'updated before drop'
WHERE id = 9001;

DROP TABLE drop_probe;

ROLLBACK;
```

Lệnh `DROP TABLE` làm commit thay đổi `UPDATE` trước đó; `ROLLBACK` không hoàn tác cập nhật và cũng không khôi phục bảng `drop_probe`. Chỉ chạy ví dụ trong schema thử nghiệm được phép xóa.

## 6. Atomic DDL không có nghĩa là rollback được

MySQL 8.0 hỗ trợ atomic DDL cho nhiều thao tác DDL với các storage engine được hỗ trợ, trong đó có InnoDB. Atomic DDL giúp thao tác DDL hoàn tất toàn bộ hoặc được phục hồi nhất quán khi server gặp sự cố trong quá trình thực hiện.

Tuy nhiên, **atomic DDL không biến DDL thành một phần có thể rollback của transaction người dùng**. `TRUNCATE TABLE` và `DROP TABLE` vẫn gây implicit commit và không thể được hoàn tác bằng `ROLLBACK` như `DELETE` trên InnoDB.

Hãy phân biệt:

- *Atomicity khi crash*: MySQL bảo vệ tính toàn vẹn của chính thao tác DDL trước sự cố máy chủ.
- *Transactional rollback*: ứng dụng có thể yêu cầu hủy thay đổi chưa commit bằng `ROLLBACK`.

Hai khái niệm giải quyết hai vấn đề khác nhau. Không dựa vào atomic DDL để thay thế backup hoặc kế hoạch phục hồi dữ liệu.

## 7. Quyền cần có

Các lệnh yêu cầu quyền khác nhau:

| Lệnh | Quyền chính |
|---|---|
| `DELETE FROM table ...` | `DELETE` trên bảng hoặc phạm vi tương ứng |
| `TRUNCATE TABLE table` | `DROP` trên bảng |
| `DROP TABLE table` | `DROP` trên bảng |

Một tài khoản chỉ có `DELETE` có thể xóa hàng nhưng không nhất thiết được phép truncate hoặc drop bảng. Đây là một phần của nguyên tắc least privilege: ứng dụng chạy thường xuyên thường chỉ cần quyền DML; quyền DDL nên dành cho tài khoản migration hoặc quản trị được kiểm soát.

Kiểm tra quyền:

```sql
SHOW GRANTS;
```

Không cấp quyền `DROP` rộng cho tài khoản ứng dụng chỉ vì một tác vụ cần làm rỗng bảng. Nếu tác vụ nghiệp vụ cần xóa dữ liệu, hãy dùng `DELETE` với điều kiện và quyền phù hợp.

## 8. Chọn lệnh nào cho đúng?

| Nhu cầu | Lệnh phù hợp | Lý do |
|---|---|---|
| Xóa một khách hàng hoặc một nhóm đơn hàng theo điều kiện | `DELETE ... WHERE ...` | Xóa có chọn lọc, có thể nằm trong transaction InnoDB |
| Xóa dữ liệu theo batch để kiểm soát tải | `DELETE ... ORDER BY ... LIMIT ...` | Có thể chia nhỏ công việc và theo dõi từng batch |
| Làm rỗng toàn bộ bảng staging, không cần trigger xóa từng dòng | `TRUNCATE TABLE` | Giữ cấu trúc, thường nhanh, reset AUTO_INCREMENT; chấp nhận implicit commit |
| Bỏ hẳn bảng cũ không còn dùng | `DROP TABLE` | Xóa cả cấu trúc và dữ liệu; cần DDL/migration để tạo lại |
| Cần khả năng hoàn tác khi kiểm tra kết quả | `DELETE` trong transaction InnoDB | Có thể kiểm tra trước rồi `ROLLBACK` nếu chưa commit |
| Cần audit qua DELETE trigger hoặc áp dụng ON DELETE action | `DELETE` | Trigger và referential action được thực thi theo từng hàng |

Trước khi xóa dữ liệu lớn, hãy xác nhận:

1. Đúng server, database và bảng chưa.
2. Có backup hoặc phương án khôi phục phù hợp với mức độ quan trọng của dữ liệu.
3. Có khóa ngoại, trigger hoặc ứng dụng khác phụ thuộc vào bảng không.
4. Có transaction đang mở mà DDL sẽ commit ngoài dự kiến không.
5. Quyền của tài khoản có đúng với thao tác dự định không.

## 9. Quy trình an toàn trước thao tác phá hủy dữ liệu

Với `DELETE` có điều kiện, hãy chạy câu `SELECT` dùng cùng điều kiện để xem chính xác các hàng sẽ bị ảnh hưởng:

```sql
SELECT order_id, customer_id, status, created_at
FROM orders
WHERE status = 'CANCELLED'
  AND created_at < '2025-01-01'
ORDER BY created_at;
```

Nếu phạm vi đúng, thực hiện trong transaction InnoDB:

```sql
START TRANSACTION;

DELETE FROM orders
WHERE status = 'CANCELLED'
  AND created_at < '2025-01-01';

SELECT ROW_COUNT() AS deleted_rows;

-- Kiểm tra các bảng liên quan và kết quả trước khi xác nhận.
COMMIT;
-- Hoặc dùng ROLLBACK nếu kết quả không đúng.
```

`ROW_COUNT()` trả số hàng bị ảnh hưởng bởi câu lệnh gần nhất trong session. Sau khi chạy câu lệnh khác, giá trị này có thể thay đổi; hãy đọc ngay sau `DELETE`.

Với `TRUNCATE` hoặc `DROP`, không có bước `ROLLBACK` để cứu dữ liệu. Hãy xác nhận tên bảng, schema, môi trường, backup và dependency trước khi thực hiện. Nếu chỉ cần xóa dữ liệu trong môi trường kiểm thử, vẫn nên kiểm tra đúng database đang kết nối:

```sql
SELECT DATABASE(), @@hostname, @@port;
```

Lệnh này giúp tránh thao tác nhầm vào production khi đang mở nhiều connection profile.

## 10. Ví dụ tổng hợp trên bảng InnoDB

Tạo bảng thử nghiệm:

```sql
CREATE TABLE cleanup_demo (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    note VARCHAR(100) NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;

INSERT INTO cleanup_demo (note)
VALUES ('keep'), ('remove'), ('remove');
```

Xóa có điều kiện và hoàn tác:

```sql
START TRANSACTION;

DELETE FROM cleanup_demo
WHERE note = 'remove';

SELECT * FROM cleanup_demo;

ROLLBACK;

SELECT * FROM cleanup_demo;
```

Làm rỗng bảng nhưng giữ cấu trúc:

```sql
TRUNCATE TABLE cleanup_demo;

SHOW CREATE TABLE cleanup_demo;
SELECT COUNT(*) FROM cleanup_demo;
```

Xóa hẳn bảng:

```sql
DROP TABLE cleanup_demo;

SHOW TABLES LIKE 'cleanup_demo';
```

Sau lệnh cuối, bảng không còn trong schema. Hãy chạy toàn bộ ví dụ trong database lab, không chạy trên bảng nghiệp vụ đang chứa dữ liệu cần giữ.

## 11. Bài tập thực hành

1. Tạo bảng InnoDB có khóa `AUTO_INCREMENT`, chèn vài dòng và ghi lại ID được cấp.
2. Xóa một dòng bằng `DELETE` trong transaction rồi `ROLLBACK`; xác nhận dòng trở lại.
3. Dùng `DELETE` xóa toàn bộ dòng và chèn thêm một dòng; quan sát bộ đếm `AUTO_INCREMENT` tiếp tục như thế nào.
4. Tạo lại dữ liệu thử nghiệm, chạy `TRUNCATE TABLE`; xác nhận cấu trúc vẫn còn, bảng rỗng và bộ đếm được reset.
5. Thêm một `DELETE` trigger để ghi audit, so sánh số bản ghi audit khi dùng `DELETE` và `TRUNCATE`.
6. Mở transaction, thay đổi một bảng rồi chạy `TRUNCATE` trên bảng lab khác; sau `ROLLBACK`, xác nhận thay đổi trước DDL đã được implicit commit.
7. Thử tạo quan hệ FK giữa hai bảng, sau đó quan sát việc `TRUNCATE` bảng cha bị từ chối khi còn được bảng con tham chiếu.
8. Dùng `DROP TABLE` trên bảng lab và giải thích vì sao không thể phục hồi bằng `ROLLBACK`.

Bạn hoàn thành bài khi chọn đúng giữa xóa hàng, làm rỗng bảng và loại bỏ bảng; giải thích được tác động lên transaction, trigger, khóa ngoại và `AUTO_INCREMENT`; đồng thời biết cách kiểm tra môi trường và dependency trước thao tác phá hủy dữ liệu.
