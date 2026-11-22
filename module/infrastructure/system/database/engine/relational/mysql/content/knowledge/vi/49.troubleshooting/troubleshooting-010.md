# Lock wait timeout, deadlock và kiểm tra phạm vi rollback

Trong module `DATABASE_MYSQL`, người học làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Bài học này tập trung vào hai lỗi khóa thường gặp trong InnoDB: lock wait timeout và deadlock. Trọng tâm là tìm transaction đang chặn, xác định phạm vi rollback thực tế và xây dựng cách retry an toàn ở tầng ứng dụng.

Hai lỗi này đều có thể làm một câu lệnh ghi thất bại, nhưng hành vi rollback khác nhau. Với deadlock, InnoDB chọn một transaction làm nạn nhân và rollback toàn bộ transaction đó. Với lock wait timeout, mặc định InnoDB chỉ rollback statement đang chờ; transaction vẫn có thể còn mở và giữ những khóa đã lấy từ các statement trước. Nếu ứng dụng không hiểu khác biệt này, nó có thể vô tình commit một phần công việc hoặc tiếp tục giữ khóa sau khi báo lỗi.

## 1. Khóa InnoDB bảo vệ dữ liệu như thế nào?

InnoDB dùng khóa để điều phối các transaction đọc/ghi đồng thời và bảo đảm ràng buộc dữ liệu. Khóa thường gắn với index record hoặc khoảng index, không đơn giản chỉ gắn với một hàng logic.

Các dạng khóa quan trọng:

| Loại khóa | Vai trò | Tình huống thường gặp |
|---|---|---|
| Record lock | Khóa một record trong index. | `UPDATE` một hàng theo primary key. |
| Gap lock | Khóa khoảng trống giữa các record index để ngăn insert vào khoảng đó trong những trường hợp cần thiết. | Locking read hoặc range scan ở isolation level phù hợp. |
| Next-key lock | Kết hợp record lock và gap lock trên khoảng index. | Một số truy vấn range ở `REPEATABLE READ`. |
| Insert intention lock | Thể hiện ý định chèn vào một vị trí trong gap; các insert ở vị trí khác nhau trong cùng gap có thể không chặn nhau. | `INSERT` đồng thời vào index. |
| Table intention lock | Đánh dấu transaction dự định lấy record lock ở bảng. | InnoDB phối hợp khóa bảng và khóa record. |

`SELECT` thông thường thường đọc bằng consistent read và không khóa record theo cách của `SELECT ... FOR UPDATE`. Các locking read như `SELECT ... FOR UPDATE` hoặc `SELECT ... FOR SHARE`, `UPDATE` và `DELETE` có thể lấy khóa cần thiết cho thao tác. Phạm vi khóa phụ thuộc index được dùng, điều kiện truy vấn, isolation level và phiên bản MySQL.

Ví dụ, nếu truy vấn cập nhật theo một cột không có index phù hợp, InnoDB có thể phải quét và khóa nhiều record hơn dự kiến. Một index đúng cho điều kiện `WHERE` giúp giảm số record cần kiểm tra và thường giảm cả phạm vi khóa, thời gian transaction lẫn nguy cơ xung đột.

## 2. Phân biệt lock wait timeout và deadlock

| Tiêu chí | Lock wait timeout | Deadlock |
|---|---|---|
| Điều kiện | Một transaction chờ khóa lâu hơn thời gian cho phép. | Có chu trình phụ thuộc khóa: mỗi transaction chờ khóa do transaction khác giữ và cuối cùng tạo thành vòng chờ. |
| Error code MySQL | `1205` (`ER_LOCK_WAIT_TIMEOUT`). | `1213` (`ER_LOCK_DEADLOCK`). |
| Phạm vi rollback mặc định | Chỉ statement bị timeout. | Toàn bộ transaction được chọn làm nạn nhân. |
| Cấu hình liên quan | `innodb_lock_wait_timeout`; `innodb_rollback_on_timeout` thay đổi phạm vi rollback. | `innodb_deadlock_detect` điều khiển phát hiện deadlock. |
| Cách xử lý | Tìm blocker, xem transaction còn mở hay không; thường rollback toàn bộ unit of work ở ứng dụng rồi cân nhắc retry. | Retry toàn bộ transaction nạn nhân sau khi xử lý nguyên nhân; không chỉ chạy lại statement thất bại. |

Lock wait timeout không chứng minh có deadlock. Một transaction có thể giữ khóa hợp lệ trong lúc thực hiện công việc dài, khiến transaction khác chờ đến timeout mà không tạo vòng chờ. Deadlock là một chu trình; InnoDB có thể phát hiện và phá chu trình bằng cách rollback một transaction.

## 3. Lock wait timeout và phạm vi rollback

Biến `innodb_lock_wait_timeout` đặt thời gian InnoDB chờ khóa record trước khi trả lỗi timeout. Giá trị mặc định thường là 50 giây; hãy kiểm tra giá trị trên đúng phiên bản và môi trường:

```sql
SHOW GLOBAL VARIABLES LIKE 'innodb_lock_wait_timeout';
SHOW SESSION VARIABLES LIKE 'innodb_lock_wait_timeout';
```

Có thể đặt timeout riêng cho session:

```sql
SET SESSION innodb_lock_wait_timeout = 10;
```

Timeout ngắn giúp request không chờ quá lâu, nhưng cũng có thể tạo nhiều lỗi tạm thời hơn khi hệ thống có transaction dài hợp lệ. Không giảm timeout chỉ để che một vấn đề khóa kéo dài; trước hết phải xác định transaction giữ khóa và lý do nó chưa kết thúc.

### Mặc định: rollback statement bị timeout

Xét transaction gồm hai statement:

```sql
START TRANSACTION;

UPDATE account
SET balance = balance - 100
WHERE id = 1;

UPDATE account
SET balance = balance + 100
WHERE id = 2;
```

Giả sử statement thứ hai chờ khóa rồi nhận lỗi 1205. Với cấu hình mặc định `innodb_rollback_on_timeout=OFF`, InnoDB rollback statement thứ hai. Statement đầu tiên vẫn thuộc transaction đang mở; transaction có thể vẫn giữ khóa mà nó đã lấy. Nếu ứng dụng bắt lỗi rồi gọi `COMMIT`, thay đổi ở statement đầu tiên có thể được commit dù toàn bộ nghiệp vụ chuyển tiền chưa hoàn tất.

Kiểm tra cấu hình:

```sql
SHOW GLOBAL VARIABLES LIKE 'innodb_rollback_on_timeout';
```

Nếu `innodb_rollback_on_timeout=ON`, InnoDB rollback toàn bộ transaction khi xảy ra lock wait timeout. Đây là hành vi khác với mặc định. Không giả định cấu hình của môi trường này giống môi trường khác; kiểm tra runtime value và test trên đúng cấu hình production.

### Cách xử lý an toàn ở ứng dụng

Với unit of work gồm nhiều statement, cách đơn giản và an toàn thường là rollback toàn bộ transaction khi nhận lỗi 1205, sau đó chỉ retry toàn bộ nghiệp vụ nếu lỗi được đánh giá là tạm thời và thao tác có thể chạy lại an toàn.

```java
try {
    connection.setAutoCommit(false);

    debitAccount(connection, sourceId, amount);
    creditAccount(connection, targetId, amount);

    connection.commit();
} catch (SQLException ex) {
    try {
        connection.rollback();
    } catch (SQLException rollbackError) {
        ex.addSuppressed(rollbackError);
    }
    throw ex;
} finally {
    connection.setAutoCommit(true);
}
```

Ví dụ này minh họa ranh giới transaction; trong code thực tế cần quản lý connection theo pool và xử lý lỗi khi `setAutoCommit()` hoặc rollback thất bại. Nếu connection không còn đáng tin cậy sau lỗi giao tiếp, không tái sử dụng nó một cách mù quáng.

Với Spring `@Transactional`, lỗi được dịch thành runtime exception thường kích hoạt rollback theo mặc định nếu exception thoát khỏi phương thức transactional. Nếu bắt exception bên trong rồi trả về bình thường, framework có thể không tự rollback theo cách bạn mong đợi. Hãy gọi cơ chế rollback phù hợp hoặc để exception đi qua transaction boundary; không nuốt lỗi 1205 rồi tiếp tục commit phần còn lại.

## 4. Deadlock: vòng chờ khóa

Deadlock xảy ra khi các transaction giữ khóa mà transaction khác cần, tạo thành vòng phụ thuộc. Ví dụ hai transaction cập nhật hai tài khoản theo thứ tự ngược nhau.

**Session A:**

```sql
START TRANSACTION;
UPDATE account SET balance = balance - 10 WHERE id = 1;
-- Giữ khóa hàng id=1.
UPDATE account SET balance = balance + 10 WHERE id = 2;
-- Chờ Session B nếu B đang giữ id=2.
```

**Session B:**

```sql
START TRANSACTION;
UPDATE account SET balance = balance - 20 WHERE id = 2;
-- Giữ khóa hàng id=2.
UPDATE account SET balance = balance + 20 WHERE id = 1;
-- Chờ Session A nếu A đang giữ id=1.
```

Session A chờ khóa của B; Session B chờ khóa của A. InnoDB phát hiện vòng chờ, chọn một transaction làm victim, rollback transaction đó và trả lỗi 1213 cho client tương ứng. Transaction còn lại có thể tiếp tục sau khi khóa được giải phóng.

InnoDB thường chọn victim dựa trên chi phí rollback, chẳng hạn kích thước transaction và số hàng đã thay đổi. Ứng dụng không nên giả định transaction mới hơn hoặc session cụ thể nào luôn bị chọn.

Deadlock không nhất thiết cần hai câu `UPDATE` đơn giản. Nó có thể xuất hiện qua nhiều bảng, secondary index, khóa ngoại, unique index, range lock hoặc các thao tác insert/update đồng thời. Điều quan trọng là thứ tự và phạm vi khóa mà mỗi transaction nắm giữ.

## 5. Tìm nguyên nhân deadlock

### Xem deadlock gần nhất

```sql
SHOW ENGINE INNODB STATUS\G
```

Tìm phần `LATEST DETECTED DEADLOCK`. Báo cáo thường cho biết:

- Các transaction tham gia và thời gian bắt đầu.
- Câu lệnh đang chạy hoặc thông tin transaction.
- Index và record/gap mà mỗi transaction đang giữ.
- Khóa mà mỗi transaction đang chờ.
- Transaction được chọn làm victim.

Đây là snapshot của deadlock gần nhất, nên có thể bị thay thế khi deadlock khác xảy ra. Hãy lưu lại báo cáo ngay khi điều tra sự cố.

Để ghi mọi deadlock vào error log trong thời gian điều tra, có thể bật:

```sql
SET GLOBAL innodb_print_all_deadlocks = ON;
```

Sau khi thu thập đủ bằng chứng, cân nhắc tắt lại nếu chính sách logging yêu cầu:

```sql
SET GLOBAL innodb_print_all_deadlocks = OFF;
```

Không bật logging chi tiết vô thời hạn mà không xem xét dung lượng và quy trình thu thập log. Cần quyền phù hợp để thay đổi biến hệ thống.

### Kiểm tra transaction đang chờ khóa

View `sys.innodb_lock_waits` có thể giúp tìm transaction chờ và transaction đang chặn:

```sql
SELECT
    waiting_pid,
    waiting_query,
    waiting_trx_started,
    waiting_trx_age,
    waiting_lock_type,
    waiting_lock_mode,
    blocking_pid,
    blocking_query,
    blocking_trx_started,
    blocking_trx_age,
    blocking_lock_type,
    blocking_lock_mode
FROM sys.innodb_lock_waits
ORDER BY waiting_trx_age DESC;
```

View này mô tả các lock wait đang tồn tại. Deadlock đã được phát hiện và rollback có thể kết thúc rất nhanh, nên không phải lúc nào cũng còn xuất hiện trong view khi DBA truy vấn. Với deadlock đã xảy ra, `SHOW ENGINE INNODB STATUS` và error log thường hữu ích hơn.

Nếu cần xem trực tiếp Performance Schema, có thể nối `data_lock_waits` với hai bản ghi trong `data_locks`:

```sql
SELECT
    req.ENGINE_TRANSACTION_ID AS waiting_trx,
    req.OBJECT_SCHEMA,
    req.OBJECT_NAME,
    req.INDEX_NAME AS waiting_index,
    req.LOCK_TYPE AS waiting_lock_type,
    req.LOCK_MODE AS waiting_lock_mode,
    req.LOCK_DATA AS waiting_lock_data,
    blk.ENGINE_TRANSACTION_ID AS blocking_trx,
    blk.INDEX_NAME AS blocking_index,
    blk.LOCK_MODE AS blocking_lock_mode,
    blk.LOCK_DATA AS blocking_lock_data
FROM performance_schema.data_lock_waits AS w
JOIN performance_schema.data_locks AS req
    ON req.ENGINE = w.ENGINE
   AND req.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS blk
    ON blk.ENGINE = w.ENGINE
   AND blk.ENGINE_LOCK_ID = w.BLOCKING_ENGINE_LOCK_ID;
```

Để liên kết transaction với connection ID, tiếp tục nối `performance_schema.threads` qua `THREAD_ID`. Các bảng Performance Schema phản ánh lock đang tồn tại tại thời điểm truy vấn; chúng không thay thế báo cáo deadlock đã được ghi lại.

## 6. Phân biệt row lock với metadata lock

Không phải mọi thông báo có chữ “lock” đều do InnoDB record lock.

| Hiện tượng | Loại chờ | Biến timeout liên quan |
|---|---|---|
| `UPDATE` chờ transaction khác sửa cùng record | InnoDB row/index lock | `innodb_lock_wait_timeout` |
| `SELECT ... FOR UPDATE` chờ record/gap lock | InnoDB row/index lock | `innodb_lock_wait_timeout` |
| `ALTER TABLE` báo `Waiting for table metadata lock` | Metadata lock (MDL) | `lock_wait_timeout` |
| `CREATE INDEX` hoặc `RENAME TABLE` chờ metadata | Metadata lock (MDL) | `lock_wait_timeout` |

Tăng `innodb_lock_wait_timeout` không giải quyết DDL đang chờ metadata lock. Ngược lại, tăng `lock_wait_timeout` không giải quyết transaction chờ record lock. Hãy đọc trạng thái session và loại lock trước khi thay đổi timeout.

## 7. Các nguyên nhân deadlock thường gặp

### Thứ tự cập nhật không nhất quán

Một transaction cập nhật tài khoản A rồi B, transaction khác cập nhật B rồi A. Đây là nguyên nhân dễ tái hiện và có thể giảm bằng cách luôn truy cập tài nguyên theo một thứ tự xác định.

### Truy vấn khóa quá nhiều hàng

Một câu lệnh thiếu index phù hợp có thể quét nhiều record và lấy phạm vi khóa lớn. Kiểm tra execution plan và index:

```sql
EXPLAIN UPDATE orders
SET status = 'PROCESSING'
WHERE customer_id = 1001
  AND status = 'PENDING';
```

Đánh giá access type, key được chọn, ước lượng số hàng và điều kiện lọc. Nếu cần, tạo composite index phù hợp với điều kiện truy vấn sau khi kiểm tra chi phí ghi và dung lượng index.

### Range scan và gap lock

Ở `REPEATABLE READ`, một số locking read hoặc DML theo range có thể dùng next-key/gap lock để ngăn phantom insert. Hai transaction chèn hoặc cập nhật trong cùng khoảng có thể xung đột dù chúng không nhắm đến cùng một giá trị khóa chính.

Không tắt gap lock hoặc đổi isolation level chỉ để giảm deadlock mà chưa đánh giá semantics. `READ COMMITTED` thường giảm một số gap lock, nhưng thay đổi tính nhất quán đọc và hành vi transaction. Phải kiểm thử logic nghiệp vụ và replication trước khi thay đổi.

### Unique index và khóa ngoại

Kiểm tra unique constraint hoặc foreign key có thể khiến transaction cần khóa trên record liên quan. Hai transaction thao tác các bảng cha/con theo thứ tự khác nhau cũng có thể tạo vòng chờ. Hãy thống nhất thứ tự thao tác giữa các service và giữ transaction ngắn.

### Transaction dài và thao tác bên ngoài

Gọi HTTP, gửi email, chờ người dùng hoặc xử lý file lớn trong lúc transaction còn mở làm khóa tồn tại lâu. Thực hiện công việc bên ngoài transaction nếu có thể; chỉ mở transaction cho phần đọc/ghi database cần tính nguyên tử.

## 8. Ngăn ngừa deadlock và giảm lock wait

Các biện pháp thường có hiệu quả:

1. **Giữ thứ tự khóa nhất quán.** Nếu nhiều transaction cập nhật cùng nhóm tài nguyên, luôn sắp xếp theo cùng khóa chính hoặc cùng thứ tự bảng.
2. **Giữ transaction ngắn.** Không chờ mạng, người dùng hoặc hệ thống ngoài trong transaction.
3. **Dùng index phù hợp.** Giảm số record phải quét và khóa; kiểm tra execution plan thay vì đoán.
4. **Cập nhật theo lô nhỏ.** Chia batch lớn thành các batch vừa phải và commit theo ranh giới nghiệp vụ đã xác định.
5. **Khóa rõ ràng khi cần.** Dùng `SELECT ... FOR UPDATE` để lấy khóa trước khi cập nhật nếu cần kiểm tra rồi thay đổi; truy vấn phải dùng index phù hợp.
6. **Truy cập bảng theo thứ tự cố định.** Các service thao tác nhiều bảng nên dùng cùng thứ tự để giảm vòng phụ thuộc.
7. **Không giữ transaction khi xử lý ngoài DB.** Chuẩn bị dữ liệu trước, mở transaction ngắn, commit, sau đó thực hiện side effect qua cơ chế phù hợp.
8. **Theo dõi và đo lường.** Ghi error code, thời gian transaction, bảng/index liên quan và tỷ lệ retry.

Không thể bảo đảm hệ thống InnoDB không bao giờ có deadlock. Deadlock là kết quả có thể xảy ra khi các transaction cạnh tranh tài nguyên; ứng dụng cần xử lý retry đúng cách ngay cả sau khi đã tối ưu thứ tự khóa.

## 9. Retry transaction an toàn

Với lỗi 1213, transaction nạn nhân đã bị rollback toàn bộ. Ứng dụng phải chạy lại toàn bộ unit of work, không chỉ chạy lại statement cuối. Với lỗi 1205, mặc định chỉ statement lỗi bị rollback; ứng dụng nên chủ động rollback toàn bộ unit of work trước khi retry, trừ khi có thiết kế phục hồi từng statement được kiểm chứng rõ ràng.

Một chính sách retry cần có:

- Chỉ retry lỗi tạm thời đã nhận diện, ví dụ SQLState/vendor error tương ứng với deadlock hoặc lock timeout.
- Giới hạn số lần retry; tránh vòng lặp vô hạn.
- Dùng backoff có jitter để các transaction không đồng loạt thử lại cùng thời điểm.
- Mỗi lần retry phải tạo transaction mới và đọc lại trạng thái cần thiết.
- Bảo đảm thao tác idempotent hoặc có idempotency key/unique constraint để tránh thực hiện side effect hai lần.
- Ghi log số lần retry và lỗi cuối cùng; nếu vượt giới hạn thì trả lỗi có thể xử lý ở tầng trên.

Pseudocode:

```text
for attempt from 1 to MAX_ATTEMPTS:
    begin a new transaction
    try:
        execute the entire business operation
        commit
        return success
    catch lock timeout or deadlock:
        rollback the whole transaction
        if attempt == MAX_ATTEMPTS:
            return/report failure
        wait for bounded exponential backoff with jitter
```

Ví dụ Java thuần cần để ý transaction phải được tạo lại ở mỗi vòng lặp:

```java
int maxAttempts = 3;

for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);
        try {
            transfer(connection, fromId, toId, amount);
            connection.commit();
            return;
        } catch (SQLException ex) {
            connection.rollback();
            if (!isRetryableLockError(ex) || attempt == maxAttempts) {
                throw ex;
            }
        }
    }

    sleepWithJitter(attempt);
}
```

`isRetryableLockError()` cần kiểm tra vendor error code và/hoặc SQLState theo driver; không retry mọi `SQLException`. `sleepWithJitter()` phải có giới hạn và không được giữ transaction hoặc connection trong lúc chờ. Ví dụ minh họa cần bổ sung xử lý exception khi rollback, interruption và khôi phục trạng thái connection theo quy ước của connection pool.

### Side effect ngoài database

Không gửi email, gọi cổng thanh toán hoặc phát message không thể thu hồi bên trong một transaction sẽ được retry. Nếu transaction rollback sau khi side effect đã xảy ra, lần retry có thể thực hiện side effect lần thứ hai. Dùng transactional outbox, idempotency key hoặc cơ chế xử lý sự kiện có thể lặp an toàn.

## 10. NOWAIT và SKIP LOCKED

Trong các phiên bản MySQL hỗ trợ locking read với `NOWAIT` và `SKIP LOCKED`, ứng dụng có thể chọn cách xử lý khác khi record đang bị khóa:

```sql
SELECT id, status
FROM job_queue
WHERE status = 'READY'
ORDER BY id
LIMIT 10
FOR UPDATE SKIP LOCKED;
```

`SKIP LOCKED` bỏ qua các record đang bị transaction khác khóa, phù hợp với một số mô hình worker lấy việc từ hàng đợi. Nó không tạo ra một snapshot đầy đủ và có thể trả về tập kết quả không liên tục; không dùng cho truy vấn nghiệp vụ cần nhìn thấy mọi hàng phù hợp.

`NOWAIT` khiến locking read trả lỗi ngay nếu không lấy được khóa, thay vì chờ đến timeout. Cách này phù hợp khi ứng dụng muốn báo “đang được xử lý” hoặc chuyển sang xử lý khác. Hãy kiểm tra hỗ trợ của phiên bản MySQL và thử trên đúng isolation level.

## 11. Bài thực hành tái hiện và kiểm tra rollback

Thực hiện trên MySQL thử nghiệm với bảng:

```sql
CREATE TABLE account (
    id BIGINT NOT NULL PRIMARY KEY,
    balance DECIMAL(19,2) NOT NULL
) ENGINE=InnoDB;

INSERT INTO account (id, balance)
VALUES (1, 1000.00), (2, 1000.00);
```

### Bài A — Tái hiện lock wait timeout

**Session A:**

```sql
START TRANSACTION;
UPDATE account SET balance = balance - 10 WHERE id = 1;
-- Giữ transaction mở.
```

**Session B:**

```sql
SET SESSION innodb_lock_wait_timeout = 5;
START TRANSACTION;
UPDATE account SET balance = balance + 10 WHERE id = 1;
-- Chờ rồi nhận lỗi 1205.
```

Sau lỗi, kiểm tra trạng thái transaction của Session B và thử `SELECT`/`COMMIT` trong môi trường thử nghiệm. Với mặc định `innodb_rollback_on_timeout=OFF`, statement B bị rollback nhưng transaction B có thể vẫn mở. Chủ động chạy `ROLLBACK` để kết thúc transaction. Session A chạy `COMMIT` hoặc `ROLLBACK` để nhả khóa.

Lặp lại sau khi kiểm tra `innodb_rollback_on_timeout=ON` trong môi trường thử nghiệm để so sánh phạm vi rollback. Ghi nhận giá trị cấu hình, lỗi, dữ liệu cuối cùng và session nào còn giữ transaction.

### Bài B — Tái hiện deadlock

Khởi tạo lại số dư nếu cần. Chạy Session A và B theo ví dụ ở phần 4, xen kẽ hai câu `UPDATE` để mỗi session giữ một hàng và chờ hàng còn lại. Một session sẽ nhận lỗi 1213.

Sau đó:

1. Chạy `SHOW ENGINE INNODB STATUS\G` để đọc deadlock report.
2. Kiểm tra session bị rollback và session còn lại.
3. Xác minh dữ liệu cuối cùng sau khi transaction còn lại commit.
4. Chạy lại bài tập với cả hai session cập nhật theo thứ tự `id` tăng dần.
5. So sánh số deadlock và thời gian chờ.

### Bài C — Quan sát lock wait

Trong lúc Session B đang chờ ở bài A, mở Session C:

```sql
SELECT * FROM sys.innodb_lock_waits;
SHOW FULL PROCESSLIST;
```

Ghi lại `waiting_pid`, `blocking_pid`, tuổi transaction, câu lệnh và bảng/index liên quan. Không kill blocker ngay; trước hết xác định chủ sở hữu và đánh giá transaction đang làm gì.

## 12. Checklist điều tra sự cố

Khi nhận lỗi 1205 hoặc 1213 từ ứng dụng, ghi nhận tối thiểu:

| Thông tin | Mục đích |
|---|---|
| Error code, SQLState, câu lệnh và thời điểm | Phân biệt timeout, deadlock và lỗi SQL khác. |
| Transaction boundary và autocommit | Xác định phạm vi công việc có thể còn tồn tại sau lỗi. |
| `innodb_lock_wait_timeout`, `innodb_rollback_on_timeout` | Hiểu thời gian chờ và hành vi rollback timeout. |
| Isolation level | Giải thích record/gap/next-key lock. |
| Transaction ID, connection ID, thời gian bắt đầu | Tìm transaction chờ và blocker. |
| Bảng, index, record/range liên quan | Xác định phạm vi cạnh tranh và index cần xem xét. |
| Deadlock report/error log | Phục dựng chu trình chờ đã xảy ra. |
| Số lần retry và kết quả cuối | Đánh giá retry có hiệu quả hay chỉ khuếch đại tải. |
| Side effect ngoài DB | Kiểm tra khả năng thực hiện trùng khi retry. |

Không tăng timeout hoặc kill session trước khi hiểu nguyên nhân. Nếu blocker là một transaction bất thường, xử lý đúng chủ sở hữu; nếu deadlock lặp lại, sửa thứ tự khóa, index hoặc phạm vi transaction. Sau khi thay đổi, theo dõi tỷ lệ 1205/1213 và thời gian transaction để xác minh hiệu quả.

## 13. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Ứng dụng nhận 1205 rồi vẫn commit một phần dữ liệu | Mặc định timeout chỉ rollback statement, transaction vẫn mở. | Rollback toàn bộ unit of work trước khi retry hoặc trả lỗi. |
| Ứng dụng retry statement cuối sau 1213 | Deadlock victim đã bị rollback toàn bộ transaction. | Tạo transaction mới và chạy lại toàn bộ nghiệp vụ. |
| Tăng `innodb_lock_wait_timeout` nhưng request vẫn treo lâu | Transaction blocker kéo dài hoặc đang chờ loại khóa khác. | Xác định loại lock, blocker và transaction age; dùng timeout phù hợp. |
| `ALTER TABLE` chờ dù đã tăng `innodb_lock_wait_timeout` | Đang chờ metadata lock. | Kiểm tra `lock_wait_timeout` và MDL blocker. |
| Deadlock vẫn xuất hiện sau khi thêm index | Thứ tự khóa, nhiều bảng, unique/FK hoặc range lock vẫn tạo chu trình. | Đọc deadlock report, chuẩn hóa thứ tự truy cập và xem phạm vi khóa thực tế. |
| Retry làm hệ thống tải cao hơn | Nhiều client retry đồng thời, không có backoff/jitter hoặc retry quá nhiều. | Giới hạn retry, backoff có jitter và theo dõi tỷ lệ thành công. |
| Gửi email/thanh toán hai lần sau retry | Side effect nằm trong transaction có thể chạy lại. | Dùng outbox, idempotency key hoặc consumer idempotent. |

## 14. Bài tập thực hành tổng hợp

Một ứng dụng chuyển tiền có hai bảng `account` và `transfer_log`. Hai request đồng thời chuyển tiền giữa cùng hai tài khoản theo thứ tự ngược nhau. Hãy:

1. Tạo schema thử nghiệm với khóa chính và index phù hợp.
2. Viết transaction chuyển tiền có kiểm tra số dư, ghi hai tài khoản và thêm transfer log.
3. Dùng hai session để tái hiện deadlock và lưu báo cáo `LATEST DETECTED DEADLOCK`.
4. Sửa code để khóa tài khoản theo thứ tự ID nhất quán; chạy lại workload và so sánh deadlock.
5. Giảm `innodb_lock_wait_timeout`, tái hiện lỗi 1205 và chứng minh statement rollback khác transaction rollback.
6. Bật `innodb_rollback_on_timeout` trong môi trường thử nghiệm, lặp lại và ghi nhận thay đổi.
7. Viết retry wrapper chỉ retry lỗi 1205/1213 đã nhận diện, rollback toàn bộ transaction và dùng backoff có jitter.
8. Mô phỏng retry sau khi side effect được phát ra; thiết kế outbox hoặc idempotency key để không ghi nhận chuyển tiền hai lần.
9. Kiểm tra transaction duration, số lock wait, deadlock rate và kết quả dữ liệu sau khi chạy đồng thời.
10. Viết runbook gồm truy vấn chẩn đoán, điều kiện rollback, retry policy và tiêu chí cần DBA can thiệp.

Sau bài tập, người học cần giải thích được vì sao timeout 1205 mặc định không giống deadlock 1213, vì sao phải kiểm tra transaction còn mở sau timeout, vì sao retry phải chạy lại toàn bộ unit of work và vì sao tối ưu thứ tự khóa vẫn cần một chính sách retry. Đây là nền tảng để xử lý cạnh tranh transaction trong MySQL mà không làm sai lệch dữ liệu nghiệp vụ.
