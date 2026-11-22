# Theo dõi wait, stage, transaction và tác vụ theo thread

Khi MySQL chậm, chỉ nhìn `SHOW PROCESSLIST` thường chưa đủ để biết session đang chờ tài nguyên nào, câu lệnh đang ở giai đoạn nào, transaction giữ khóa bao lâu hoặc thread nền đang làm gì. **Performance Schema** cung cấp sự kiện ở cấp thread, wait, stage, statement và transaction; **sys schema** gom nhiều dữ liệu đó thành các view dễ đọc hơn.

Bài học thuộc phần **Quan sát hệ thống** của MySQL. Bạn sẽ liên kết connection với `THREAD_ID`, theo dõi wait và stage đang diễn ra, đọc lịch sử sự kiện, quan sát transaction hiện tại, tìm quan hệ chờ khóa InnoDB và sử dụng số liệu tổng hợp để xác định nút thắt. Mục tiêu là biến một dấu hiệu “database đang chậm” thành bằng chứng cụ thể theo thread và sự kiện.

## 1. Phân biệt connection, thread và event

MySQL có nhiều định danh liên quan nhưng không thể dùng thay thế cho nhau:

| Khái niệm | Ý nghĩa | Nơi quan sát |
| --- | --- | --- |
| Connection ID | ID của kết nối client, thường xuất hiện trong `SHOW PROCESSLIST` và `CONNECTION_ID()`. | `performance_schema.threads.PROCESSLIST_ID`, `SHOW PROCESSLIST`. |
| `THREAD_ID` | ID nội bộ của thread được Performance Schema theo dõi. | `performance_schema.threads.THREAD_ID`. |
| Event | Một hoạt động được instrument, chẳng hạn wait, stage, statement hoặc transaction. | Các bảng `events_*_current`, `events_*_history` và `events_*_summary_*`. |
| Transaction ID | Định danh transaction của storage engine, nếu có. | `events_transactions_*`, `data_locks`, `information_schema.innodb_trx`. |

Một connection foreground thường có `PROCESSLIST_ID` khác NULL và gắn với một `THREAD_ID`. Thread nền của InnoDB hoặc replication có thể không có connection ID. Vì vậy, không lọc mọi quan sát chỉ bằng `PROCESSLIST_ID` nếu đang điều tra hoạt động nền.

Kiểm tra connection hiện tại:

```sql
SELECT CONNECTION_ID();
```

Liệt kê thread và thông tin processlist:

```sql
SELECT
    THREAD_ID,
    PROCESSLIST_ID AS connection_id,
    TYPE,
    NAME,
    PROCESSLIST_USER,
    PROCESSLIST_HOST,
    PROCESSLIST_DB,
    PROCESSLIST_COMMAND,
    PROCESSLIST_STATE,
    PROCESSLIST_TIME
FROM performance_schema.threads
ORDER BY TYPE, THREAD_ID;
```

`TYPE` thường phân biệt `FOREGROUND` và `BACKGROUND`. `PROCESSLIST_STATE` có thể NULL khi thread không có trạng thái processlist tương ứng. `PROCESSLIST_TIME` là thời gian ở trạng thái hiện tại theo processlist, không phải tổng tuổi đời connection.

## 2. Performance Schema và các bảng sự kiện

Performance Schema là cơ chế instrument và lưu số liệu quan sát nội bộ của MySQL. Các bảng quan trọng:

| Nhóm | Bảng ví dụ | Câu hỏi trả lời |
| --- | --- | --- |
| Thread | `threads` | Thread nào thuộc connection nào? Thread foreground hay background? |
| Wait | `events_waits_current`, `events_waits_history`, `events_waits_history_long` | Thread đang chờ mutex, I/O, lock hay tài nguyên nào? |
| Stage | `events_stages_current`, `events_stages_history_long` | Statement đang ở giai đoạn xử lý nào? |
| Statement | `events_statements_current`, `events_statements_history_long` | Câu SQL nào đang chạy hoặc vừa chạy? |
| Transaction | `events_transactions_current`, `events_transactions_history_long` | Transaction đang active, commit hay rollback? Bắt đầu và kéo dài bao lâu? |
| Lock InnoDB | `data_locks`, `data_lock_waits` | Transaction nào đang giữ lock và transaction nào đang chờ? |
| Metadata lock | `metadata_locks` | DDL hoặc truy vấn nào đang chờ metadata lock? |
| Summary | `events_*_summary_*` | Loại event nào tiêu tốn nhiều thời gian nhất trong khoảng thống kê? |

Performance Schema thường được bật khi khởi động MySQL. Kiểm tra:

```sql
SHOW VARIABLES LIKE 'performance_schema';
```

Nếu giá trị là `OFF`, không thể bật toàn bộ Performance Schema bằng một câu `SET` trong lúc server đang chạy; cần cấu hình khi khởi động và lập kế hoạch restart phù hợp.

## 3. Consumer và instrument: dữ liệu có được thu thập hay không?

Performance Schema có hai lớp điều khiển:

- **Instrument** xác định loại hoạt động nào được đo, ví dụ `wait/io/file/innodb/%`, `wait/lock/metadata/sql/mdl`, `stage/sql/%` hoặc `statement/sql/%`.
- **Consumer** xác định sự kiện nào được đưa vào bảng current/history hoặc bảng tổng hợp.

Xem cấu hình consumer:

```sql
SELECT NAME, ENABLED
FROM performance_schema.setup_consumers
ORDER BY NAME;
```

Xem instrument:

```sql
SELECT NAME, ENABLED, TIMED
FROM performance_schema.setup_instruments
WHERE NAME LIKE 'wait/lock/%'
   OR NAME LIKE 'wait/io/file/innodb/%'
   OR NAME LIKE 'stage/sql/%'
   OR NAME = 'transaction'
ORDER BY NAME;
```

Nếu consumer hoặc instrument liên quan bị tắt, bảng sự kiện tương ứng có thể trống hoặc thiếu số liệu. Trước khi kết luận “không có wait”, hãy xác nhận instrument và consumer đang bật.

### Bật có mục tiêu trong môi trường kiểm thử

Ví dụ bật một số instrument cần cho điều tra lock, I/O InnoDB và stage SQL:

```sql
UPDATE performance_schema.setup_instruments
SET ENABLED = 'YES', TIMED = 'YES'
WHERE NAME = 'wait/lock/metadata/sql/mdl'
   OR NAME = 'wait/io/file/innodb/%'
   OR NAME LIKE 'stage/sql/%';

UPDATE performance_schema.setup_consumers
SET ENABLED = 'YES'
WHERE NAME IN (
    'global_instrumentation',
    'thread_instrumentation',
    'events_waits_current',
    'events_waits_history',
    'events_waits_history_long',
    'events_stages_current',
    'events_stages_history_long',
    'events_statements_current',
    'events_statements_history_long',
    'events_transactions_current',
    'events_transactions_history_long'
);
```

Các tên instrument thực tế phụ thuộc phiên bản và bản dựng; truy vấn `setup_instruments` trước khi cập nhật. Không bật tất cả instrument trên production một cách tùy tiện. Instrumentation có chi phí CPU và bộ nhớ, đặc biệt khi thu thập lịch sử dài cho workload có tần suất event cao.

Các thay đổi trên `setup_instruments` và `setup_consumers` có hiệu lực khi chạy nhưng không nên mặc định là cấu hình bền vững qua restart. Nếu cần duy trì, cấu hình Performance Schema theo hướng dẫn phiên bản MySQL đang dùng và kiểm tra lại sau restart.

## 4. Theo dõi wait đang diễn ra

Wait event cho biết thread đang chờ tài nguyên hoặc hoạt động nội bộ nào. Ví dụ có thể là chờ file I/O, mutex, condition, table lock hoặc metadata lock. Wait hiện tại được lưu trong `events_waits_current` nếu instrument và consumer tương ứng được bật.

```sql
SELECT
    w.THREAD_ID,
    t.PROCESSLIST_ID AS connection_id,
    t.PROCESSLIST_USER,
    t.PROCESSLIST_HOST,
    w.EVENT_NAME,
    w.OPERATION,
    w.OBJECT_SCHEMA,
    w.OBJECT_NAME,
    w.INDEX_NAME,
    ROUND(w.TIMER_WAIT / 1000000000000, 6) AS wait_seconds
FROM performance_schema.events_waits_current AS w
LEFT JOIN performance_schema.threads AS t
  ON t.THREAD_ID = w.THREAD_ID
WHERE w.END_EVENT_ID IS NULL
ORDER BY w.TIMER_WAIT DESC;
```

Các timer của Performance Schema được biểu diễn theo picosecond; chia cho (10^{12}) để đổi sang giây. `TIMER_WAIT` có thể NULL nếu instrument không đo thời gian (`TIMED = NO`). Wait event hiện tại chỉ là ảnh chụp tại thời điểm truy vấn; một wait ngắn có thể kết thúc trước khi câu quan sát chạy.

### Phân biệt wait với trạng thái processlist

`SHOW PROCESSLIST` hiển thị trạng thái tổng quát của connection, chẳng hạn `Sending data`, `Waiting for table metadata lock` hoặc `Sleep`. `events_waits_current` cung cấp sự kiện được instrument ở mức chi tiết hơn. Một connection có thể không nằm trong wait tại thời điểm chụp nhưng vẫn đang thực hiện CPU work hoặc chuyển giữa nhiều stage.

Không diễn giải mọi wait là lỗi. Chờ I/O hoặc mutex trong thời gian ngắn là một phần bình thường của hoạt động. Cần so sánh thời gian, tần suất, loại event và ảnh hưởng lên latency của workload.

## 5. Đọc lịch sử wait và tổng hợp theo loại event

`events_waits_history` lưu một số event gần nhất theo từng thread; `events_waits_history_long` lưu lịch sử dùng chung với dung lượng giới hạn. Khi vòng đệm đầy, event cũ bị ghi đè.

Xem các wait gần đây:

```sql
SELECT
    THREAD_ID,
    EVENT_ID,
    EVENT_NAME,
    OPERATION,
    OBJECT_SCHEMA,
    OBJECT_NAME,
    ROUND(TIMER_WAIT / 1000000000000, 6) AS wait_seconds
FROM performance_schema.events_waits_history_long
ORDER BY TIMER_START DESC
LIMIT 100;
```

Tổng hợp theo loại wait:

```sql
SELECT
    EVENT_NAME,
    COUNT_STAR,
    ROUND(SUM_TIMER_WAIT / 1000000000000, 3) AS total_wait_seconds,
    ROUND(AVG_TIMER_WAIT / 1000000000000, 6) AS avg_wait_seconds,
    ROUND(MAX_TIMER_WAIT / 1000000000000, 6) AS max_wait_seconds
FROM performance_schema.events_waits_summary_global_by_event_name
WHERE COUNT_STAR > 0
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
```

Bảng summary tích lũy từ lúc khởi động hoặc lần reset thống kê gần nhất. Để đo tác động của một thay đổi, chụp số liệu trước/sau và tính delta; không so sánh tổng tích lũy của hai server có uptime khác nhau.

### Kích thước history

Kiểm tra giới hạn history:

```sql
SHOW VARIABLES WHERE Variable_name IN (
    'performance_schema_events_waits_history_size',
    'performance_schema_events_waits_history_long_size'
);
```

Các bảng history có dung lượng cố định theo cấu hình và có thể ghi đè dữ liệu cũ. History không phải kho log lâu dài. Nếu cần lưu xu hướng qua nhiều ngày, hãy thu thập định kỳ ra hệ thống observability bên ngoài.

## 6. Theo dõi stage: statement đang ở giai đoạn nào?

Stage là các giai đoạn nội bộ của quá trình thực thi statement. Ví dụ có thể gồm mở bảng, tối ưu truy vấn, thực thi, sắp xếp hoặc gửi kết quả; tên và độ chi tiết phụ thuộc phiên bản/instrument.

Xem stage hiện tại:

```sql
SELECT
    s.THREAD_ID,
    t.PROCESSLIST_ID AS connection_id,
    t.PROCESSLIST_USER,
    s.EVENT_NAME AS stage_name,
    ROUND(s.TIMER_WAIT / 1000000000000, 6) AS stage_seconds,
    s.WORK_COMPLETED,
    s.WORK_ESTIMATED
FROM performance_schema.events_stages_current AS s
LEFT JOIN performance_schema.threads AS t
  ON t.THREAD_ID = s.THREAD_ID
WHERE s.END_EVENT_ID IS NULL
ORDER BY s.TIMER_WAIT DESC;
```

`WORK_COMPLETED` và `WORK_ESTIMATED` chỉ có ý nghĩa với những stage instrument cung cấp thông tin tiến độ; chúng có thể NULL. Không phải mọi stage đều có tỷ lệ hoàn thành đáng tin cậy.

Lịch sử stage:

```sql
SELECT
    THREAD_ID,
    EVENT_ID,
    EVENT_NAME,
    ROUND(TIMER_WAIT / 1000000000000, 6) AS stage_seconds
FROM performance_schema.events_stages_history_long
ORDER BY TIMER_START DESC
LIMIT 100;
```

Tổng hợp stage theo loại:

```sql
SELECT
    EVENT_NAME,
    COUNT_STAR,
    ROUND(SUM_TIMER_WAIT / 1000000000000, 3) AS total_seconds,
    ROUND(AVG_TIMER_WAIT / 1000000000000, 6) AS avg_seconds
FROM performance_schema.events_stages_summary_global_by_event_name
WHERE COUNT_STAR > 0
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
```

Nếu một statement dành phần lớn thời gian ở stage liên quan sort, có thể cần xem `ORDER BY`, index và temporary table. Nếu thời gian nằm ở stage gửi dữ liệu, kiểm tra lượng kết quả, tốc độ client tiêu thụ và mạng. Stage giúp định hướng điều tra; hãy kết hợp `EXPLAIN ANALYZE` và số liệu wait để xác định nguyên nhân.

## 7. Theo dõi statement gắn với thread

`events_statements_current` cho biết statement đang chạy trên từng thread. Có thể nối với `threads` để tìm connection và SQL text:

```sql
SELECT
    t.THREAD_ID,
    t.PROCESSLIST_ID AS connection_id,
    t.PROCESSLIST_USER,
    t.PROCESSLIST_HOST,
    t.PROCESSLIST_STATE,
    es.EVENT_NAME,
    ROUND(es.TIMER_WAIT / 1000000000000, 6) AS statement_seconds,
    es.ROWS_EXAMINED,
    es.ROWS_SENT,
    es.SQL_TEXT
FROM performance_schema.threads AS t
JOIN performance_schema.events_statements_current AS es
  ON es.THREAD_ID = t.THREAD_ID
WHERE t.TYPE = 'FOREGROUND'
  AND es.END_EVENT_ID IS NULL
ORDER BY es.TIMER_WAIT DESC;
```

SQL text có thể chứa literal nhạy cảm. Chỉ cấp quyền xem cho người cần điều tra; khi chia sẻ kết quả ra ngoài, che thông tin cá nhân, token, email hoặc dữ liệu nghiệp vụ.

Để xem statement gần đây của một thread, dùng `events_statements_history` hoặc `events_statements_history_long`:

```sql
SELECT
    THREAD_ID,
    EVENT_ID,
    EVENT_NAME,
    ROUND(TIMER_WAIT / 1000000000000, 6) AS statement_seconds,
    ROWS_EXAMINED,
    ROWS_SENT,
    SQL_TEXT
FROM performance_schema.events_statements_history_long
WHERE THREAD_ID = 12345
ORDER BY EVENT_ID DESC
LIMIT 20;
```

Thay `12345` bằng `THREAD_ID` cần điều tra, không phải connection ID. `EVENT_ID` có thứ tự trong thread; history long có thể bị ghi đè và không bảo đảm lưu đầy đủ mọi statement.

## 8. Theo dõi transaction đang mở

Transaction kéo dài có thể giữ row lock, metadata hoặc snapshot lâu, làm tăng lock wait và cản purge. Bảng `events_transactions_current` cho biết transaction hiện tại của các thread được instrument:

```sql
SELECT
    trx.THREAD_ID,
    t.PROCESSLIST_ID AS connection_id,
    t.PROCESSLIST_USER,
    t.PROCESSLIST_HOST,
    trx.EVENT_ID,
    trx.STATE,
    trx.TRX_ID,
    trx.ACCESS_MODE,
    trx.ISOLATION_LEVEL,
    trx.AUTOCOMMIT,
    ROUND(trx.TIMER_WAIT / 1000000000000, 3) AS transaction_seconds
FROM performance_schema.events_transactions_current AS trx
LEFT JOIN performance_schema.threads AS t
  ON t.THREAD_ID = trx.THREAD_ID
ORDER BY trx.TIMER_WAIT DESC;
```

Các transaction event có thể không xuất hiện nếu transaction instrumentation hoặc consumer tương ứng bị tắt. `TIMER_WAIT` đo thời gian của event transaction được Performance Schema ghi nhận; không phải mọi transaction đều có đủ thông tin nếu instrumentation chưa được bật từ trước.

### Đối chiếu với InnoDB transaction

`information_schema.innodb_trx` cung cấp thông tin transaction ở tầng InnoDB:

```sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_wait_started,
    trx_mysql_thread_id AS connection_id,
    trx_operation_state,
    trx_rows_locked,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
```

Đây là nguồn hữu ích để tìm transaction bắt đầu lâu, đang chờ lock hoặc sửa nhiều dòng. `trx_mysql_thread_id` tương ứng connection ID của client; có thể nối sang `performance_schema.threads.PROCESSLIST_ID` để tìm `THREAD_ID`.

```sql
SELECT
    t.THREAD_ID,
    t.PROCESSLIST_ID AS connection_id,
    t.PROCESSLIST_USER,
    t.PROCESSLIST_STATE,
    trx.trx_id,
    trx.trx_started,
    trx.trx_state,
    trx.trx_rows_locked,
    trx.trx_rows_modified,
    trx.trx_query
FROM information_schema.innodb_trx AS trx
LEFT JOIN performance_schema.threads AS t
  ON t.PROCESSLIST_ID = trx.trx_mysql_thread_id
ORDER BY trx.trx_started;
```

Transaction lâu không nhất thiết là lỗi: có thể là batch hợp lệ hoặc tác vụ bảo trì. Cần xem mục đích, thời gian, số dòng khóa/sửa và tác động tới session khác trước khi quyết định can thiệp.

## 9. Tìm transaction đang chờ và giữ row lock

MySQL 8.0 cung cấp `performance_schema.data_locks` và `data_lock_waits` để quan sát lock InnoDB. Đây là cách hiện đại thay cho việc dựa vào các bảng `INFORMATION_SCHEMA.INNODB_LOCKS`/`INNODB_LOCK_WAITS` cũ.

### Xem lock hiện có

```sql
SELECT
    ENGINE_TRANSACTION_ID,
    THREAD_ID,
    EVENT_ID,
    OBJECT_SCHEMA,
    OBJECT_NAME,
    INDEX_NAME,
    LOCK_TYPE,
    LOCK_MODE,
    LOCK_STATUS,
    LOCK_DATA
FROM performance_schema.data_locks
ORDER BY OBJECT_SCHEMA, OBJECT_NAME, THREAD_ID;
```

`LOCK_STATUS` thường cho biết lock đang `GRANTED` hay `WAITING`. `LOCK_DATA` có thể chứa giá trị khóa và có thể NULL tùy loại lock hoặc khả năng xác định record. Không xuất dữ liệu khóa nhạy cảm ra nơi không được phép.

### Ghép waiter và blocker

```sql
SELECT
    req.THREAD_ID AS waiting_thread_id,
    wt.PROCESSLIST_ID AS waiting_connection_id,
    wt.PROCESSLIST_USER AS waiting_user,
    req.ENGINE_TRANSACTION_ID AS waiting_trx_id,
    req.OBJECT_SCHEMA,
    req.OBJECT_NAME,
    req.INDEX_NAME,
    req.LOCK_TYPE,
    req.LOCK_MODE AS waiting_lock_mode,
    blk.THREAD_ID AS blocking_thread_id,
    bt.PROCESSLIST_ID AS blocking_connection_id,
    bt.PROCESSLIST_USER AS blocking_user,
    blk.ENGINE_TRANSACTION_ID AS blocking_trx_id,
    blk.LOCK_MODE AS blocking_lock_mode,
    req.LOCK_DATA
FROM performance_schema.data_lock_waits AS w
JOIN performance_schema.data_locks AS req
  ON req.ENGINE = w.ENGINE
 AND req.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS blk
  ON blk.ENGINE = w.ENGINE
 AND blk.ENGINE_LOCK_ID = w.BLOCKING_ENGINE_LOCK_ID
LEFT JOIN performance_schema.threads AS wt
  ON wt.THREAD_ID = req.THREAD_ID
LEFT JOIN performance_schema.threads AS bt
  ON bt.THREAD_ID = blk.THREAD_ID;
```

Kết quả cho biết thread/connection đang chờ, thread/connection đang chặn, bảng/index và chế độ lock. Một blocker có thể không chạy statement ngay lúc quan sát nhưng vẫn giữ transaction mở và lock đã lấy trước đó.

### Dùng sys.innodb_lock_waits

Nếu sys schema có sẵn, view `sys.innodb_lock_waits` cung cấp cách đọc gọn hơn:

```sql
SELECT
    wait_started,
    wait_age,
    waiting_pid,
    waiting_query,
    waiting_trx_id,
    blocking_pid,
    blocking_query,
    blocking_trx_id,
    locked_table,
    locked_index
FROM sys.innodb_lock_waits
ORDER BY wait_age_secs DESC;
```

View này tổng hợp thông tin từ Performance Schema và InnoDB. Nếu view không tồn tại hoặc tài khoản không có quyền, dùng truy vấn `data_lock_waits` ở trên.

## 10. Theo dõi metadata lock

Metadata lock (MDL) bảo vệ định nghĩa bảng và đối tượng schema khi truy vấn hoặc DDL đang sử dụng chúng. Ví dụ, một transaction mở lâu có thể giữ metadata lock trên bảng; một câu `ALTER TABLE` cần lock độc quyền phải chờ.

Xem lock metadata:

```sql
SELECT
    ml.OBJECT_TYPE,
    ml.OBJECT_SCHEMA,
    ml.OBJECT_NAME,
    ml.LOCK_TYPE,
    ml.LOCK_DURATION,
    ml.LOCK_STATUS,
    ml.OWNER_THREAD_ID,
    t.PROCESSLIST_ID AS connection_id,
    t.PROCESSLIST_USER,
    t.PROCESSLIST_STATE
FROM performance_schema.metadata_locks AS ml
LEFT JOIN performance_schema.threads AS t
  ON t.THREAD_ID = ml.OWNER_THREAD_ID
WHERE ml.LOCK_STATUS = 'PENDING'
   OR ml.LOCK_STATUS = 'GRANTED'
ORDER BY ml.OBJECT_SCHEMA, ml.OBJECT_NAME, ml.LOCK_STATUS;
```

Tập trung vào các dòng `PENDING` để tìm yêu cầu lock đang chờ, rồi đối chiếu các dòng `GRANTED` trên cùng đối tượng. Không phải mọi lock granted đều chặn DDL; cần xét loại lock và thứ tự tương thích.

Khi DDL chờ metadata lock, đừng vội kill query đang chờ. Tìm transaction hoặc session giữ lock lâu, xác định chủ sở hữu và tác động nghiệp vụ. Kết thúc connection blocker có thể khiến transaction rollback và tạo tải đáng kể.

## 11. Dùng sys schema để đọc thread và session nhanh hơn

Sys schema cung cấp view tổng hợp từ Performance Schema. Một view hữu ích là `sys.processlist`:

```sql
SELECT
    thd_id,
    conn_id,
    user,
    db,
    command,
    state,
    time,
    statement_latency,
    lock_latency,
    rows_examined,
    rows_sent,
    tmp_tables,
    tmp_disk_tables,
    full_scan,
    current_statement,
    last_wait
FROM sys.processlist
ORDER BY statement_latency DESC;
```

View này trình bày connection/thread, statement latency, lock latency, số dòng và wait gần nhất trong một giao diện dễ đọc. Tên cột và view có thể khác theo phiên bản sys schema; kiểm tra bằng `DESCRIBE sys.processlist` nếu truy vấn không tương thích.

Để tìm session đang chạy câu lệnh lâu, `sys.processlist` thường dễ dùng hơn việc ghép nhiều bảng thủ công. Tuy nhiên, khi cần phân tích event cụ thể hoặc background thread, truy vấn trực tiếp Performance Schema vẫn cần thiết.

## 12. Thí nghiệm hai session: quan sát row-lock wait

Tạo bảng lab và một dòng dữ liệu:

```sql
CREATE TABLE observability_lock_lab (
    item_id INT PRIMARY KEY,
    quantity INT NOT NULL
) ENGINE = InnoDB;

INSERT INTO observability_lock_lab (item_id, quantity)
VALUES (1, 10);
```

Mở ba kết nối: session A, session B và session C dùng để quan sát.

**Session A — lấy lock và giữ transaction mở:**

```sql
START TRANSACTION;

UPDATE observability_lock_lab
SET quantity = quantity + 1
WHERE item_id = 1;

-- Chưa COMMIT; row lock vẫn được giữ.
```

**Session B — yêu cầu cập nhật cùng dòng:**

```sql
START TRANSACTION;

UPDATE observability_lock_lab
SET quantity = quantity + 5
WHERE item_id = 1;
-- Statement sẽ chờ lock do session A giữ.
```

**Session C — quan sát lock wait:**

```sql
SELECT
    req.THREAD_ID AS waiting_thread_id,
    wt.PROCESSLIST_ID AS waiting_connection_id,
    blk.THREAD_ID AS blocking_thread_id,
    bt.PROCESSLIST_ID AS blocking_connection_id,
    req.OBJECT_NAME,
    req.INDEX_NAME,
    req.LOCK_MODE AS waiting_mode,
    blk.LOCK_MODE AS blocking_mode,
    req.LOCK_DATA
FROM performance_schema.data_lock_waits AS w
JOIN performance_schema.data_locks AS req
  ON req.ENGINE = w.ENGINE
 AND req.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS blk
  ON blk.ENGINE = w.ENGINE
 AND blk.ENGINE_LOCK_ID = w.BLOCKING_ENGINE_LOCK_ID
LEFT JOIN performance_schema.threads AS wt
  ON wt.THREAD_ID = req.THREAD_ID
LEFT JOIN performance_schema.threads AS bt
  ON bt.THREAD_ID = blk.THREAD_ID;
```

Kết quả phải chỉ ra session B đang chờ và session A đang chặn trên dòng của `observability_lock_lab`. Nếu bảng không có dòng, xác nhận session B thực sự đang chờ, consumer/instrument liên quan hoạt động và truy vấn chạy đúng thời điểm.

Kết thúc ở **session A**:

```sql
COMMIT;
```

Session B sẽ tiếp tục khi lock được giải phóng. Sau khi câu UPDATE ở B hoàn tất:

```sql
COMMIT;
```

Kiểm tra dữ liệu cuối cùng và đóng các transaction. Trong môi trường lab, có thể xóa bảng sau khi hoàn tất:

```sql
DROP TABLE observability_lock_lab;
```

Không chạy thí nghiệm giữ lock lâu trên bảng production. Nếu thực hiện trên môi trường dùng chung, chọn bảng thử riêng và giới hạn thời gian chờ.

## 13. Chẩn đoán thread nền và tác vụ dài

Không phải mọi hoạt động đều gắn với một connection client. InnoDB có thread nền cho purge, page cleaner, I/O và các công việc nội bộ; replication có thread nhận và áp dụng sự kiện. Các thread này có thể xuất hiện trong `performance_schema.threads` với `TYPE = 'BACKGROUND'` và `PROCESSLIST_ID` NULL.

Liệt kê thread nền:

```sql
SELECT
    THREAD_ID,
    NAME,
    TYPE,
    PROCESSLIST_STATE
FROM performance_schema.threads
WHERE TYPE = 'BACKGROUND'
ORDER BY NAME, THREAD_ID;
```

Kết hợp với wait hiện tại:

```sql
SELECT
    t.THREAD_ID,
    t.NAME,
    w.EVENT_NAME,
    w.OPERATION,
    w.OBJECT_NAME,
    ROUND(w.TIMER_WAIT / 1000000000000, 6) AS wait_seconds
FROM performance_schema.threads AS t
JOIN performance_schema.events_waits_current AS w
  ON w.THREAD_ID = t.THREAD_ID
WHERE t.TYPE = 'BACKGROUND'
  AND w.END_EVENT_ID IS NULL
ORDER BY w.TIMER_WAIT DESC;
```

Thread nền chờ event không nhất thiết có vấn đề; có thể đang idle chờ công việc. Cần xem event name, tần suất, thời gian và các chỉ số hệ thống liên quan trước khi kết luận thread bị treo.

## 14. Giới hạn, overhead và quyền truy cập

Performance Schema được thiết kế để quan sát với overhead tương đối thấp, nhưng bật quá nhiều instrument và lưu history dài vẫn có chi phí CPU, bộ nhớ và truy vấn đọc dữ liệu quan sát.

Các nguyên tắc:

1. Chỉ bật instrument cần thiết cho câu hỏi đang điều tra.
2. Bật history long có chủ đích; các bảng có dung lượng giới hạn và ghi đè dữ liệu cũ.
3. Tránh truy vấn quét toàn bộ history liên tục trên server tải cao; giới hạn thời gian, thread và số dòng.
4. Lấy delta của summary thay vì reset thống kê trên production chỉ để tạo biểu đồ.
5. Không thu thập hoặc chia sẻ SQL text, lock data hay thông tin user nếu không có quyền và mục đích phù hợp.
6. Kiểm tra trạng thái instrumentation sau restart và sau nâng cấp phiên bản.

Để xem session của người dùng khác qua processlist, tài khoản có thể cần quyền `PROCESS`; quyền đọc Performance Schema và sys schema cũng cần được cấp theo chính sách least privilege. Không cấp quyền quản trị rộng chỉ để một dashboard đọc được vài bảng quan sát.

Một số history size được điều khiển bằng biến cấu hình khi khởi động, ví dụ:

```sql
SHOW VARIABLES WHERE Variable_name IN (
    'performance_schema_events_waits_history_size',
    'performance_schema_events_waits_history_long_size',
    'performance_schema_events_stages_history_long_size',
    'performance_schema_events_statements_history_long_size',
    'performance_schema_events_transactions_history_long_size'
);
```

Tăng history size có thể tăng bộ nhớ sử dụng. Hãy xác định thời gian cần lưu và event rate để chọn dung lượng, thay vì đặt tất cả lên mức lớn nhất.

## 15. Quy trình điều tra một sự cố chậm

Khi nhận cảnh báo latency tăng hoặc ứng dụng báo timeout, có thể đi theo trình tự:

1. **Xác định phạm vi:** một connection, một query digest, một schema hay toàn instance?
2. **Liệt kê thread:** dùng `performance_schema.threads` hoặc `sys.processlist` để xác định connection, user, state và statement.
3. **Kiểm tra statement:** đọc SQL text, thời gian, rows examined/sent và execution plan nếu truy vấn còn chạy hoặc có thể tái hiện.
4. **Kiểm tra wait:** xem `events_waits_current` và history để biết thread đang chờ I/O, mutex, lock hay tài nguyên nào.
5. **Kiểm tra stage:** xem `events_stages_current` để biết statement đang ở giai đoạn xử lý nào.
6. **Kiểm tra transaction:** tìm transaction dài, số row lock/modified và snapshot đang giữ.
7. **Kiểm tra blocker:** dùng `data_lock_waits`, `data_locks`, `metadata_locks` hoặc `sys.innodb_lock_waits`.
8. **Đối chiếu summary:** xác định loại wait/stage/statement nào tiêu tốn thời gian nhiều nhất trong khoảng đo.
9. **Can thiệp có kiểm soát:** tối ưu truy vấn, điều chỉnh index, xử lý transaction blocker hoặc giảm tải theo runbook.
10. **Đo lại:** so sánh latency, wait time, throughput và lock wait sau thay đổi.

Nếu cân nhắc dừng một query, phân biệt `KILL QUERY connection_id` (dừng statement hiện tại) với `KILL CONNECTION connection_id` (đóng connection và có thể khiến transaction rollback). Xác minh đúng connection, chủ sở hữu và tác động trước khi thực hiện; rollback transaction lớn có thể tiếp tục tiêu thụ tài nguyên trong một khoảng thời gian.

## 16. Bài tập tự kiểm tra

1. Phân biệt `PROCESSLIST_ID` và `THREAD_ID`. Vì sao cần nối qua `performance_schema.threads`?
2. Instrument và consumer khác nhau như thế nào?
3. `events_waits_current` trả lời câu hỏi gì? Vì sao bảng trống không chứng minh không có wait?
4. Stage khác wait ở điểm nào? `WORK_COMPLETED` có luôn có giá trị không?
5. Làm thế nào xem lịch sử wait và tổng thời gian theo loại event?
6. So sánh `events_transactions_current` với `information_schema.innodb_trx`.
7. Dùng `data_lock_waits` và `data_locks` để xác định waiter và blocker như thế nào?
8. Metadata lock có thể khiến DDL chờ ra sao khi transaction khác mở lâu?
9. Vì sao background thread có thể có `PROCESSLIST_ID` là NULL?
10. Thiết kế quy trình điều tra từ cảnh báo latency tới thread, wait, stage, transaction và blocker.

Quan sát hiệu quả cần nối được **thread → statement → stage/wait → transaction → lock hoặc tài nguyên → tác động lên workload**. Khi định danh và thời điểm được liên kết chính xác, DBA có thể phân biệt query tốn CPU, query chờ I/O, transaction giữ lock và thread nền đang thực hiện công việc hợp lệ.
