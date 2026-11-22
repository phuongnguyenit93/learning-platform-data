# MySQL InnoDB: ảnh hưởng của mức cô lập, chỉ mục và autocommit

Trong MySQL InnoDB, mức cô lập (isolation level), chỉ mục (index) và chế độ `autocommit` cùng quyết định cách transaction nhìn thấy dữ liệu, những bản ghi hoặc khoảng khóa có thể bị khóa và thời gian khóa được giữ. Ba yếu tố này liên quan chặt chẽ nhưng giải quyết ba câu hỏi khác nhau:

- **Isolation level:** một transaction được phép nhìn thấy phiên bản dữ liệu nào và InnoDB dùng loại khóa nào để bảo vệ các thao tác nhất định?
- **Index và execution plan:** InnoDB phải quét những entry nào để tìm hàng, và phạm vi record/gap nào có thể bị khóa trong quá trình đó?
- **Autocommit và transaction boundary:** các khóa và snapshot tồn tại đến cuối câu lệnh hay tiếp tục được giữ đến `COMMIT`/`ROLLBACK`?

Một câu `UPDATE` có thể chỉ sửa một hàng nhưng phải quét nhiều index record nếu thiếu index phù hợp. Một câu `SELECT` thông thường có thể không khóa hàng nhưng vẫn dùng snapshot cũ trong transaction `REPEATABLE READ`. Một kết nối đang `Sleep` có thể vẫn giữ khóa vì `autocommit=0` và transaction chưa kết thúc. Muốn điều tra đúng, cần xem đồng thời cả ba yếu tố.

Bài này tập trung vào MySQL InnoDB. Chi tiết có thể khác giữa các phiên bản MySQL và storage engine khác. Ví dụ SQL giả định bảng dùng InnoDB và ứng dụng quản lý transaction rõ ràng.

## 1. Phân biệt ba trục cấu hình

Không nên coi `autocommit`, isolation level và index là ba tên gọi của cùng một cơ chế.

| Yếu tố | Câu hỏi nó trả lời | Ví dụ tác động |
|---|---|---|
| Isolation level | Transaction nhìn thấy phiên bản nào? Range read có cần bảo vệ phantom bằng gap/next-key lock không? | `REPEATABLE READ` thường giữ một read view cho các consistent read trong transaction; range locking read có thể dùng next-key lock. |
| Index/access path | Engine phải đi qua những entry nào để tìm và thay đổi hàng? | Index phù hợp có thể giới hạn range scan; full scan có thể mở rộng tập record bị khóa. |
| Autocommit/transaction boundary | Khi nào transaction kết thúc và khóa được giải phóng? | `autocommit=1` kết thúc transaction sau mỗi statement; transaction tường minh có thể giữ khóa qua nhiều câu lệnh. |

Có thể hình dung:

```text
                  Câu SQL
                     |
          +----------+----------+
          |          |          |
          v          v          v
     Isolation     Index     Autocommit
          |          |          |
          v          v          v
     Snapshot và  Access path  Ranh giới
     quy tắc khóa  và range     transaction
          |          |          |
          +----------+----------+
                     |
                     v
       Dữ liệu nhìn thấy, lock footprint,
       thời gian chờ và thời gian giữ khóa
```

Một thay đổi ở bất kỳ trục nào cũng có thể làm hành vi đồng thời khác đi. Khi phân tích sự cố, ghi lại cả ba thay vì chỉ xem câu SQL.

## 2. Autocommit quyết định ranh giới transaction

MySQL thường bật `autocommit` theo mặc định. Khi `autocommit=1`, mỗi câu lệnh SQL chạy như một transaction riêng nếu không mở transaction tường minh. Khi câu lệnh kết thúc thành công, transaction được commit tự động; nếu câu lệnh lỗi, hành vi rollback phụ thuộc loại lỗi và statement.

Kiểm tra cấu hình:

```sql
SELECT @@autocommit;
SELECT @@transaction_isolation;
```

### Autocommit bật

```sql
SELECT *
FROM accounts
WHERE id = 10;

UPDATE accounts
SET balance = balance - 100
WHERE id = 10;
```

Hai câu lệnh là hai transaction độc lập. Sau khi câu `UPDATE` kết thúc, transaction tự commit và khóa ghi được giải phóng. Ứng dụng không thể giả định rằng một khóa lấy trong câu lệnh trước còn được giữ khi chạy câu lệnh tiếp theo.

Một câu `SELECT` consistent read thông thường cũng kết thúc transaction autocommit khi hoàn tất. Snapshot của câu đọc đó không được giữ để tái sử dụng cho câu `SELECT` kế tiếp.

### Autocommit tắt

Khi chạy:

```sql
SET autocommit = 0;

SELECT balance
FROM accounts
WHERE id = 10;

UPDATE accounts
SET balance = balance - 100
WHERE id = 10;

-- Transaction vẫn mở cho đến khi COMMIT hoặc ROLLBACK.
COMMIT;
```

Mỗi câu lệnh bắt đầu một transaction mới nếu chưa có transaction đang hoạt động, nhưng transaction không tự kết thúc sau mỗi câu. Các thao tác tiếp theo thuộc cùng transaction cho đến khi `COMMIT` hoặc `ROLLBACK`.

Nếu ứng dụng quên kết thúc transaction, kết nối có thể nằm `Sleep` nhưng vẫn giữ khóa hoặc read view đã lấy. Đây là một nguồn blocking và giữ undo history phổ biến.

### Transaction tường minh với autocommit bật

Không cần tắt autocommit toàn session để nhóm nhiều câu lệnh thành một transaction:

```sql
START TRANSACTION;

SELECT balance
FROM accounts
WHERE id = 10;

UPDATE accounts
SET balance = balance - 100
WHERE id = 10;

COMMIT;
```

`START TRANSACTION` mở transaction tường minh dù `autocommit=1`. Các câu lệnh bên trong transaction dùng chung ranh giới commit. Sau `COMMIT`, session quay về chế độ autocommit đã cấu hình.

### Xem transaction đang mở

```sql
SELECT
    trx_id,
    trx_mysql_thread_id AS connection_id,
    trx_started,
    TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS age_seconds,
    trx_state,
    trx_rows_locked,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
```

Kết hợp `connection_id` với `SHOW FULL PROCESSLIST`. Một transaction có thể vẫn mở khi `trx_query` rỗng và process list báo `Sleep`.

## 3. Isolation level ảnh hưởng snapshot và locking read

InnoDB hỗ trợ bốn mức cô lập chuẩn:

- `READ UNCOMMITTED`
- `READ COMMITTED`
- `REPEATABLE READ`
- `SERIALIZABLE`

Mức mặc định của MySQL InnoDB thường là `REPEATABLE READ`, nhưng ứng dụng và session có thể cấu hình khác. Xem giá trị thực tế thay vì giả định mặc định:

```sql
SELECT @@global.transaction_isolation;
SELECT @@session.transaction_isolation;
```

Isolation level điều khiển cách đọc dữ liệu và một số quy tắc khóa. Cần phân biệt **consistent read** với **current/locking read**:

- `SELECT` thông thường thường là consistent read: đọc theo read view và có thể dựng phiên bản cũ bằng undo.
- `SELECT ... FOR UPDATE`, `SELECT ... FOR SHARE`, `UPDATE` và `DELETE` cần dữ liệu hiện tại để khóa hoặc ghi; đây là các thao tác current read theo quy tắc của InnoDB.

Không nên suy luận rằng mọi câu `SELECT` đều dùng cùng snapshot hoặc rằng mọi câu đọc đều khóa hàng.

## 4. READ UNCOMMITTED

`READ UNCOMMITTED` cho phép transaction đọc thay đổi chưa commit của transaction khác. Đây là dirty read.

Ví dụ:

```text
Session A                         Session B
---------                         ---------
BEGIN
UPDATE accounts
SET balance = 0
WHERE id = 10
                                  SET SESSION TRANSACTION
                                  ISOLATION LEVEL READ UNCOMMITTED;
                                  SELECT balance FROM accounts
                                  WHERE id = 10;
                                  Có thể thấy 0
ROLLBACK
```

Nếu A rollback, giá trị 0 chưa từng được commit nhưng B đã có thể đọc thấy. Điều này thường không phù hợp với số dư, tồn kho hoặc trạng thái nghiệp vụ cần dữ liệu đã xác nhận.

InnoDB vẫn sử dụng khóa cho các thao tác ghi và locking read. `READ UNCOMMITTED` không có nghĩa mọi khóa đều biến mất; nó chủ yếu nới lỏng quy tắc visibility của consistent read.

## 5. READ COMMITTED

Ở `READ COMMITTED`, mỗi consistent read thông thường lấy một read view mới khi câu đọc bắt đầu. Hai câu `SELECT` trong cùng transaction có thể thấy các trạng thái đã commit khác nhau nếu transaction khác commit giữa hai câu.

```text
Transaction A (READ COMMITTED)       Transaction B
------------------------------       -------------
BEGIN
SELECT balance -> 500
                                     UPDATE balance = 700
                                     COMMIT
SELECT balance -> 700
COMMIT
```

Điều này tạo non-repeatable read: cùng một truy vấn đọc lại có thể trả về giá trị mới.

### Ảnh hưởng đến gap lock

Trong InnoDB, `READ COMMITTED` thường tắt gap locking cho các search và index scan thông thường. Vì vậy, range locking read có thể giữ record lock trên các hàng tìm được nhưng ít bảo vệ khoảng trống hơn so với `REPEATABLE READ`.

Gap lock vẫn có thể xuất hiện cho mục đích kiểm tra khóa ngoại và duplicate-key. Không nên diễn giải `READ COMMITTED` là “không bao giờ có gap lock”.

### Khóa của hàng không khớp điều kiện

Trong một số thao tác `UPDATE` ở `READ COMMITTED`, InnoDB có thể dùng semi-consistent read để trả phiên bản đã commit mới nhất cho MySQL kiểm tra điều kiện `WHERE`. Nếu hàng không khớp, khóa trên hàng đó có thể được giải phóng. Hành vi này giúp giảm blocking so với việc giữ mọi khóa trên các hàng quét qua, nhưng chi tiết phụ thuộc câu lệnh và execution path.

## 6. REPEATABLE READ

`REPEATABLE READ` là mức mặc định thường gặp của InnoDB. Với consistent read, read view thường được tạo ở lần đọc nhất quán đầu tiên trong transaction và được dùng lại cho các consistent read tiếp theo.

```text
Transaction A (REPEATABLE READ)      Transaction B
--------------------------------      -------------
BEGIN
SELECT balance -> 500
(read view được tạo)
                                      UPDATE balance = 700
                                      COMMIT
SELECT balance -> 500
(dùng read view cũ)
COMMIT
```

Các câu đọc thông thường của A tiếp tục thấy snapshot cũ, dù B đã commit. InnoDB dùng undo record để dựng lại phiên bản mà read view của A được phép nhìn thấy.

### Phantom và next-key locking

Với locking read hoặc thao tác ghi theo range, InnoDB có thể dùng next-key lock: record lock trên index record kết hợp gap lock trên khoảng trước record. Cơ chế này giúp ngăn transaction khác chèn một key mới vào khoảng đang được bảo vệ và hạn chế phantom trong các thao tác range có khóa.

Ví dụ:

```sql
START TRANSACTION;

SELECT id, amount
FROM orders
WHERE amount BETWEEN 100 AND 200
FOR UPDATE;

-- Transaction khác có thể bị chặn khi chèn key vào gap được khóa.
```

Phạm vi thực tế phụ thuộc index được dùng, range scan, giá trị biên và execution plan. `REPEATABLE READ` không có nghĩa mọi `SELECT` thường đều khóa gap; consistent read thông thường dùng MVCC snapshot. Gap/next-key locking đặc biệt quan trọng với locking reads, `UPDATE` và `DELETE` theo range.

### WITH CONSISTENT SNAPSHOT

Nếu cần tạo read view ngay khi bắt đầu transaction, có thể dùng:

```sql
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION WITH CONSISTENT SNAPSHOT;

SELECT COUNT(*) FROM orders;
SELECT SUM(total_amount) FROM orders;

COMMIT;
```

`WITH CONSISTENT SNAPSHOT` có ý nghĩa với `REPEATABLE READ`. Nó tạo snapshot nhất quán ngay khi bắt đầu transaction thay vì đợi consistent read đầu tiên. Snapshot vẫn được giữ theo vòng đời transaction; transaction mở lâu có thể giữ undo history lâu hơn.

## 7. SERIALIZABLE

`SERIALIZABLE` yêu cầu kết quả các transaction đồng thời tương đương với một thứ tự thực thi tuần tự. InnoDB tăng mức bảo vệ bằng cách khiến các consistent read thông thường trở thành locking reads trong điều kiện transaction phù hợp.

Trong MySQL, khi `autocommit` bị tắt, các câu `SELECT` thông thường trong transaction `SERIALIZABLE` được xử lý như `SELECT ... FOR SHARE` nếu không chỉ định locking clause khác. Khi `autocommit=1`, mỗi câu `SELECT` là transaction riêng và có thể được xử lý như consistent read riêng lẻ. Vì vậy, ảnh hưởng của `SERIALIZABLE` phải được hiểu cùng với transaction boundary.

Ví dụ:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL SERIALIZABLE;
SET autocommit = 0;

SELECT balance
FROM accounts
WHERE id = 10;

-- SELECT trong transaction serializable có thể lấy shared lock.
COMMIT;
```

Shared lock có thể chặn transaction muốn ghi cùng hàng và có thể tạo deadlock nếu các transaction lấy shared lock rồi nâng cấp sang exclusive lock theo thứ tự xung đột. `SERIALIZABLE` thường có chi phí đồng thời cao hơn; chỉ chọn khi yêu cầu nghiệp vụ cần bảo đảm đó.

## 8. Index quyết định đường quét và phạm vi khóa

InnoDB thường khóa các index record mà câu lệnh cần truy cập để thực hiện locking read hoặc ghi. Vì vậy, index được optimizer chọn có ảnh hưởng trực tiếp đến phạm vi khóa.

Giả sử:

```sql
CREATE TABLE inventory (
    id BIGINT PRIMARY KEY,
    warehouse_id BIGINT NOT NULL,
    sku VARCHAR(50) NOT NULL,
    quantity INT NOT NULL,
    status VARCHAR(20) NOT NULL,
    KEY ix_inventory_wh_sku (warehouse_id, sku)
) ENGINE = InnoDB;
```

Truy vấn:

```sql
START TRANSACTION;

SELECT id, quantity
FROM inventory
WHERE warehouse_id = 5
  AND sku = 'SKU-100'
FOR UPDATE;
```

Index `(warehouse_id, sku)` phù hợp với điều kiện equality. InnoDB có thể tìm phạm vi nhỏ trong secondary index rồi tra về clustered record. Nếu bỏ index và engine phải quét toàn bảng, nhiều record hơn có thể bị truy cập và khóa.

### Index không phù hợp làm phạm vi scan rộng

Ví dụ chỉ có index trên `warehouse_id`:

```sql
KEY ix_inventory_wh (warehouse_id)
```

Truy vấn lọc thêm `sku` có thể quét tất cả entry thuộc warehouse 5 rồi mới lọc SKU. Nếu warehouse có hàng trăm nghìn SKU, locking read có thể phải đi qua nhiều entry trước khi tìm hàng mục tiêu.

Index phù hợp không chỉ giúp giảm thời gian query. Nó còn có thể giảm số record được quét, thời gian giữ khóa và xác suất blocking.

## 9. Unique lookup và range lookup tạo lock khác nhau

### Tìm đúng một hàng bằng toàn bộ unique key

```sql
SELECT *
FROM users
WHERE email = 'an@example.test'
FOR UPDATE;
```

Nếu `email` là unique index và truy vấn dùng toàn bộ unique key để tìm một hàng tồn tại, InnoDB thường chỉ cần record lock trên record được tìm, không cần gap lock bao quanh nó.

### Tìm bằng non-unique key hoặc range

```sql
SELECT *
FROM orders
WHERE status = 'PENDING'
FOR UPDATE;
```

Nếu `status` không unique, engine có thể quét nhiều entry. Ở `REPEATABLE READ`, các record và khoảng liên quan có thể được bảo vệ bằng next-key lock. Các transaction khác có thể bị chặn khi cập nhật những hàng đó hoặc chèn vào gap được khóa.

Một equality predicate không tự động đồng nghĩa với record-only lock. Điều quan trọng là điều kiện có dùng đầy đủ unique index hay không và record có tồn tại hay không. Tìm kiếm theo prefix của composite unique index hoặc điều kiện không xác định duy nhất có thể cần range locking.

## 10. Secondary index và clustered index

Trong InnoDB, clustered index thường là PRIMARY KEY và leaf page chứa dữ liệu hàng. Secondary index lưu các cột index cùng khóa chính để tìm về clustered record.

Khi locking read đi qua secondary index, InnoDB có thể đặt khóa trên entry secondary và record tương ứng trong clustered index. Một hàng logic vì thế có thể xuất hiện qua nhiều lock entry trong `performance_schema.data_locks`.

Ví dụ:

```sql
CREATE TABLE users (
    id BIGINT PRIMARY KEY,
    email VARCHAR(200) NOT NULL,
    status VARCHAR(20) NOT NULL,
    KEY ix_users_status (status)
) ENGINE = InnoDB;

START TRANSACTION;

SELECT id
FROM users
WHERE status = 'ACTIVE'
FOR UPDATE;
```

Nếu optimizer dùng `ix_users_status`, engine tìm hàng qua secondary index và bảo vệ clustered row tương ứng. Nếu range scan rộng, lock footprint có thể bao gồm nhiều entry hơn số hàng cuối cùng ứng dụng quan tâm.

## 11. UPDATE và DELETE cũng chịu ảnh hưởng của index

Điều kiện `WHERE` của `UPDATE`/`DELETE` quyết định đường tìm hàng. Nếu thiếu index phù hợp, engine có thể phải quét nhiều record.

```sql
UPDATE orders
SET status = 'EXPIRED'
WHERE created_at < '2026-01-01'
  AND status = 'PENDING';
```

Nếu không có index phù hợp cho điều kiện, engine có thể quét một vùng lớn. Với locking statement, các record được truy cập có thể bị khóa trong quá trình thực thi. Một câu lệnh chỉ cập nhật một số ít hàng cuối cùng vẫn có thể gây blocking rộng hơn dự kiến nếu access path không chọn lọc.

Khi câu lệnh thay đổi cột nằm trong secondary index, InnoDB còn phải duy trì index entry cũ và mới. Ví dụ đổi `status` làm thay đổi entry trong index `(status, created_at)`. Việc kiểm tra unique key và foreign key cũng có thể lấy các khóa bổ sung.

## 12. Kết hợp isolation level và index: ví dụ range locking

Giả sử bảng `orders` có index:

```sql
CREATE INDEX ix_orders_status_created
ON orders (status, created_at, id);
```

Truy vấn lấy các đơn hàng pending trong một khoảng thời gian:

```sql
SELECT id
FROM orders
WHERE status = 'PENDING'
  AND created_at >= '2026-11-01'
  AND created_at < '2026-11-08'
ORDER BY created_at, id
FOR UPDATE;
```

Với `REPEATABLE READ`, InnoDB có thể dùng range scan trên index và next-key lock để bảo vệ record cùng gap trong phạm vi quét. Một transaction khác chèn đơn hàng mới có `status='PENDING'` và `created_at` thuộc khoảng đó có thể phải chờ.

Với `READ COMMITTED`, gap locking cho search/index scan thông thường được giảm/tắt, nên thao tác insert vào khoảng có thể không bị chặn bởi gap lock của truy vấn này. Nhưng row lock trên các hàng đã tìm được vẫn có thể tồn tại; kiểm tra unique/foreign key vẫn có thể dùng gap lock.

Nếu index không tồn tại hoặc optimizer chọn index không phù hợp, scan có thể rộng hơn và lock footprint thay đổi. `LIMIT` hoặc số hàng trả về không đủ để suy ra phạm vi khóa.

## 13. Autocommit thay đổi thời gian giữ khóa

Hãy xét cùng một locking read:

```sql
SELECT id, balance
FROM accounts
WHERE id = 10
FOR UPDATE;
```

Để khóa được giữ qua một thao tác đọc/ghi tiếp theo, ứng dụng cần transaction tường minh hoặc cấu hình autocommit phù hợp. Nếu mỗi câu lệnh là một transaction autocommit riêng, transaction kết thúc khi câu lệnh hoàn tất; ứng dụng không thể dựa vào khóa để bảo vệ khoảng giữa hai câu lệnh.

Mẫu an toàn cho read-modify-write:

```sql
START TRANSACTION;

SELECT balance
FROM accounts
WHERE id = 10
FOR UPDATE;

UPDATE accounts
SET balance = balance - 100
WHERE id = 10;

COMMIT;
```

Khóa được giữ trong phạm vi transaction, từ locking read đến commit. Không gọi dịch vụ ngoài hoặc chờ người dùng giữa hai câu lệnh trong khi vẫn giữ transaction.

Với một câu `UPDATE` đơn lẻ trong autocommit, InnoDB vẫn cần khóa trong lúc thực hiện câu lệnh để bảo đảm tính nguyên tử. Khóa được giải phóng sau khi statement transaction commit. Autocommit không có nghĩa thao tác ghi không dùng khóa; nó chỉ làm transaction boundary ngắn hơn.

## 14. Bảng tương tác giữa ba yếu tố

| Isolation level | Index/access path | Autocommit/transaction | Hệ quả thường gặp |
|---|---|---|---|
| `READ COMMITTED` | Unique equality lookup | Một statement autocommit | Tìm hàng nhanh; row lock của DML chỉ giữ đến cuối statement transaction. |
| `READ COMMITTED` | Range scan trên index không unique | Transaction tường minh | Các record tìm được có thể bị khóa; gap lock thông thường ít hơn `REPEATABLE READ`; khóa được giữ đến commit. |
| `REPEATABLE READ` | Range scan trên index không unique | Transaction tường minh | Consistent read dùng snapshot lặp lại; locking read/range DML có thể dùng next-key lock và giữ đến commit. |
| `REPEATABLE READ` | Full scan do thiếu index | Transaction tường minh | Engine có thể quét và khóa nhiều record hơn cần thiết; transaction dài làm thời gian blocking tăng. |
| `SERIALIZABLE` | Index chọn lọc | Autocommit tắt/transaction tường minh | Plain SELECT có thể trở thành shared locking read; có thể tăng xung đột đọc/ghi. |
| Bất kỳ mức nào | Index phù hợp | `autocommit=0`, quên COMMIT | Transaction nhàn rỗi vẫn có thể giữ khóa/snapshot và chặn phiên khác. |

Bảng mô tả xu hướng, không thay thế execution plan và lock instrumentation. Loại câu lệnh, unique predicate, gap, foreign key, trigger và trạng thái dữ liệu vẫn có thể làm kết quả khác đi.

## 15. Chẩn đoán: kiểm tra isolation, autocommit và index

### Bước 1: xác nhận cấu hình session

```sql
SELECT
    @@session.transaction_isolation AS isolation_level,
    @@session.autocommit AS autocommit_mode,
    @@session.innodb_lock_wait_timeout AS innodb_lock_wait_timeout,
    @@session.lock_wait_timeout AS metadata_lock_wait_timeout;
```

Đừng chỉ xem global setting. Một connection pool có thể đặt session isolation hoặc autocommit khác nhau khi lấy connection.

### Bước 2: tìm transaction đang mở

```sql
SELECT
    trx_id,
    trx_mysql_thread_id AS connection_id,
    trx_started,
    TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS transaction_age_seconds,
    trx_state,
    trx_rows_locked,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
```

Đối chiếu connection id với:

```sql
SHOW FULL PROCESSLIST;
```

Một kết nối `Sleep` có transaction mở vẫn có thể giữ khóa. Kiểm tra code path nào đã mở transaction và có nhánh nào quên commit/rollback.

### Bước 3: xem execution plan

```sql
EXPLAIN FORMAT=JSON
SELECT id
FROM orders
WHERE status = 'PENDING'
  AND created_at >= '2026-11-01'
  AND created_at < '2026-11-08'
ORDER BY created_at, id
FOR UPDATE;
```

Quan sát `key`, `access_type`, `rows`, `filtered`, `used_key_parts`, `attached_condition` và dấu hiệu filesort. Kế hoạch là ước lượng của optimizer, không phải danh sách khóa thực tế.

### Bước 4: xem khóa dữ liệu

```sql
SELECT
    ENGINE_TRANSACTION_ID,
    THREAD_ID,
    OBJECT_SCHEMA,
    OBJECT_NAME,
    INDEX_NAME,
    LOCK_TYPE,
    LOCK_MODE,
    LOCK_STATUS,
    LOCK_DATA
FROM performance_schema.data_locks
WHERE OBJECT_SCHEMA = DATABASE()
  AND OBJECT_NAME = 'orders';
```

Xem cả secondary index và `PRIMARY`, mode record/gap/next-key, trạng thái granted/waiting và key liên quan. Kết hợp:

```sql
SELECT *
FROM performance_schema.data_lock_waits;
```

để tìm transaction chờ và transaction chặn.

### Bước 5: xác định metadata lock nếu DDL bị chờ

```sql
SELECT
    OBJECT_SCHEMA,
    OBJECT_NAME,
    LOCK_TYPE,
    LOCK_DURATION,
    LOCK_STATUS,
    OWNER_THREAD_ID
FROM performance_schema.metadata_locks
WHERE OBJECT_SCHEMA = DATABASE()
  AND OBJECT_NAME = 'orders';
```

`data_locks` tập trung vào lock dữ liệu InnoDB; DDL có thể bị chặn bởi metadata lock. Hai loại chờ cần xem ở nguồn phù hợp.

## 16. Thử nghiệm thay đổi isolation level và autocommit

Có thể dùng bảng nhỏ trong database test để quan sát sự khác biệt. Không chạy thử nghiệm giữ khóa trên production.

```sql
CREATE TABLE isolation_demo (
    id INT PRIMARY KEY,
    category INT NOT NULL,
    value INT NOT NULL,
    KEY ix_category_value (category, value)
) ENGINE = InnoDB;

INSERT INTO isolation_demo VALUES
(1, 10, 100),
(2, 10, 200),
(3, 10, 300),
(4, 20, 100);
```

### Thử snapshot READ COMMITTED và REPEATABLE READ

Session A:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT value FROM isolation_demo WHERE id = 1;
```

Session B:

```sql
UPDATE isolation_demo
SET value = 150
WHERE id = 1;
COMMIT;
```

Session A đọc lại:

```sql
SELECT value FROM isolation_demo WHERE id = 1;
COMMIT;
```

Ở `REPEATABLE READ`, consistent read thứ hai thường vẫn thấy snapshot cũ. Lặp lại với `READ COMMITTED`; câu đọc thứ hai có thể thấy giá trị đã commit mới.

### Thử gap lock với range locking read

Session A:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT *
FROM isolation_demo
WHERE category = 10
  AND value BETWEEN 100 AND 250
FOR UPDATE;
```

Session B thử chèn một hàng có key nằm trong vùng tương ứng:

```sql
INSERT INTO isolation_demo(id, category, value)
VALUES (5, 10, 180);
```

Quan sát Session B có chờ hay không, rồi lặp lại với Session A dùng `READ COMMITTED`. Gap locking cho search/index scan thông thường khác nhau giữa hai mức; kết quả cụ thể còn phụ thuộc index và cách optimizer thực hiện truy vấn.

### Thử autocommit và thời gian giữ khóa

Session A:

```sql
SET autocommit = 0;

UPDATE isolation_demo
SET value = value + 1
WHERE id = 1;

-- Không commit; giữ session mở.
```

Session B:

```sql
UPDATE isolation_demo
SET value = value + 1
WHERE id = 1;
```

Session B phải chờ khóa do A giữ. Khi A chạy `COMMIT` hoặc `ROLLBACK`, B có thể tiếp tục. Lặp lại với một câu `UPDATE` độc lập khi `autocommit=1`; khóa ghi được giữ trong lúc statement chạy và giải phóng sau khi statement transaction kết thúc.

## 17. Những lỗi thiết kế thường gặp

### Tắt autocommit ở connection pool nhưng không quản lý transaction

Nếu pool trả connection có `autocommit=0` và code quên commit/rollback, transaction có thể tồn tại qua nhiều request hoặc bị trả lại pool trong trạng thái không sạch. Cần bảo đảm mỗi lần mượn connection đều có ranh giới transaction và reset cấu hình trước khi trả connection.

### Giữ transaction trong khi gọi dịch vụ ngoài

Một transaction đọc/ghi xong dữ liệu rồi gọi HTTP trong khi chưa commit sẽ tiếp tục giữ khóa. Nếu dịch vụ ngoài chậm, thời gian blocking cũng kéo dài. Hãy giới hạn transaction vào phần database cần tính nguyên tử; dùng outbox cho event cần gửi sau commit.

### Chỉ nhìn số hàng kết quả để suy ra lock footprint

`LIMIT 1` không bảo đảm chỉ quét/khóa một record. Nếu index không phù hợp hoặc điều kiện lọc được đánh giá sau khi scan, engine có thể truy cập nhiều entry. Kiểm tra execution plan và `data_locks`.

### Đổi isolation level để chữa mọi blocking

Chuyển sang `READ COMMITTED` có thể giảm gap locking cho một số range scan, nhưng thay đổi snapshot semantics và không loại bỏ row lock, metadata lock hay transaction dài. Cần xác định loại chờ trước khi thay đổi.

### Dùng index mà không xem chi phí ghi

Thêm nhiều secondary index có thể làm truy vấn đọc chọn lọc hơn, nhưng INSERT/UPDATE/DELETE phải duy trì nhiều cấu trúc index hơn. Index dư thừa có thể tăng I/O, chi phí ghi và cơ hội xung đột. Thiết kế dựa trên workload và đo lường.

## 18. Cách chọn cấu hình và thiết kế phù hợp

1. Xác định yêu cầu visibility: có cần cùng snapshot xuyên suốt transaction hay mỗi câu đọc có thể thấy dữ liệu mới?
2. Chọn isolation level theo yêu cầu đó; không chỉ chọn theo thói quen hoặc vì một lỗi lock vừa xảy ra.
3. Xác định câu lệnh nào cần locking read và dùng `FOR UPDATE`/`FOR SHARE` trong transaction tường minh.
4. Thiết kế index theo equality predicate, range predicate và thứ tự cần thiết; kiểm tra access path bằng `EXPLAIN`.
5. Đánh giá unique lookup so với range/non-unique lookup để hiểu gap/next-key locking.
6. Giữ transaction ngắn và kết thúc mọi transaction bằng commit/rollback.
7. Kiểm tra `autocommit` thực tế ở session do connection pool cấp.
8. Theo dõi `data_locks`, `data_lock_waits`, `innodb_trx` và metadata locks khi có blocking.
9. Kiểm thử cạnh tranh bằng nhiều session trên dữ liệu đại diện.
10. Sau khi thay đổi isolation, index hoặc autocommit, kiểm tra lại cả kết quả nghiệp vụ lẫn lock footprint.

## 19. Tự kiểm tra

**Autocommit có quyết định transaction nhìn thấy phiên bản nào không?**

Autocommit chủ yếu quyết định ranh giới transaction. Isolation level quyết định visibility và quy tắc đồng thời bên trong transaction. Tuy vậy, ranh giới transaction quyết định snapshot tồn tại bao lâu và có được dùng lại giữa các câu lệnh hay không.

**Vì sao cùng một câu SELECT có thể thấy dữ liệu khác nhau ở READ COMMITTED và REPEATABLE READ?**

READ COMMITTED thường tạo read view mới cho mỗi consistent read. REPEATABLE READ thường tái sử dụng read view được tạo ở lần đọc đầu tiên của transaction.

**Vì sao index phù hợp có thể giảm blocking?**

Index giúp engine tìm đúng vùng dữ liệu với ít entry phải quét hơn. Với locking read hoặc DML, scan hẹp hơn thường làm giảm số record và khoảng khóa liên quan cũng như thời gian giữ khóa.

**REPEATABLE READ có nghĩa mọi SELECT đều khóa hàng không?**

Không. SELECT thông thường là consistent read dùng MVCC snapshot. Locking read và thao tác ghi mới dùng row/gap/next-key locking theo access path.

**READ COMMITTED có loại bỏ mọi gap lock không?**

Không. Gap locking cho search/index scan thông thường thường được tắt, nhưng vẫn có thể xuất hiện cho kiểm tra foreign key và duplicate-key.

**Một connection Sleep có thể giữ khóa không?**

Có. Nếu transaction được mở bằng `autocommit=0` hoặc `START TRANSACTION` mà chưa commit/rollback, connection có thể idle nhưng vẫn giữ khóa đã lấy.

**Vì sao LIMIT 1 không bảo đảm chỉ một hàng bị khóa?**

LIMIT giới hạn số hàng trả về. Index được quét, điều kiện lọc, gap/next-key locking và execution plan quyết định phạm vi truy cập/khóa thực tế.

Khi điều tra InnoDB, hãy nối ba câu hỏi: **transaction nhìn thấy dữ liệu nào, index khiến engine quét và khóa vùng nào, và transaction kết thúc khi nào**. Isolation level giải thích snapshot và quy tắc khóa; index giải thích đường truy cập; autocommit giải thích thời gian sống của transaction. Chỉ khi xem cả ba, ta mới giải thích được vì sao một truy vấn có thể chặn phiên khác hoặc vì sao cùng câu SQL lại có hành vi khác nhau giữa hai môi trường.
