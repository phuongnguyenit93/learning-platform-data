# Lưu lịch thực thi, cấu hình và bằng chứng dữ liệu để tái lập

Một thí nghiệm đồng thời với hai session chỉ có giá trị khi người khác có thể hiểu chính xác điều gì đã chạy, chạy theo thứ tự nào, trên cấu hình nào và dữ liệu đã ở trạng thái nào trước khi bắt đầu. Một ảnh chụp màn hình báo “query đang chờ” chưa đủ để giải thích nguyên nhân; một đoạn SQL riêng lẻ cũng chưa đủ để tái tạo cạnh tranh giữa hai transaction.

Muốn tái lập được thí nghiệm, cần lưu ba nhóm thông tin gắn với cùng một mã lần chạy:

1. **Lịch thực thi (execution schedule):** câu lệnh của từng session, thứ tự bắt đầu/kết thúc, điểm đồng bộ và thời điểm giữ hoặc nhả transaction.
2. **Cấu hình môi trường:** hệ quản trị và phiên bản, storage engine, isolation level, autocommit, session variables, schema, index, driver và cách chạy client.
3. **Bằng chứng dữ liệu:** fixture trước thí nghiệm, tham số thực tế, kết quả từng bước, trạng thái hàng sau cùng, lock/wait evidence, execution plan và log có liên quan.

Ba nhóm phải liên kết được với nhau. Khi thấy Session B chờ, người đọc cần biết Session A đã chạy câu nào, khóa nào còn giữ, dữ liệu có key gì và hai session đang dùng isolation level nào. Nếu thiếu một trong các phần đó, cùng câu SQL có thể cho kết quả khác ở lần chạy sau.

Bài này hướng dẫn cách ghi chép thí nghiệm hai session cho chủ đề Database Transaction Concurrency. Ví dụ ưu tiên MySQL InnoDB, đồng thời chỉ ra những nguồn bằng chứng tương ứng ở PostgreSQL. Không chạy thí nghiệm khóa kéo dài trên production; dùng database thử nghiệm và dữ liệu có thể khôi phục.

## 1. Mục tiêu của một hồ sơ thí nghiệm có thể tái lập

Một hồ sơ tốt phải trả lời được các câu hỏi sau:

- Thí nghiệm đang kiểm chứng giả thuyết nào?
- Hệ quản trị, phiên bản, schema và dữ liệu đầu vào là gì?
- Session A, Session B và session quan sát được khởi tạo như thế nào?
- Isolation level, autocommit và các timeout có giá trị gì ở từng session?
- Câu lệnh nào chạy trước, câu lệnh nào chạy sau, và điểm nào cần chờ người thực hiện xác nhận?
- Lệnh nào được kỳ vọng chờ, thành công, thất bại hoặc tạo deadlock?
- Dấu hiệu nào chứng minh kết quả: row count, giá trị dữ liệu, lock record, wait relation hay error code?
- Thí nghiệm kết thúc bằng commit, rollback hay hủy session?
- Dữ liệu đã được kiểm tra và khôi phục ra sao?

Không cần thu thập mọi thông tin có thể có. Hãy lưu những dữ kiện có khả năng làm thay đổi kết quả và những bằng chứng trực tiếp để xác nhận giả thuyết.

## 2. Xác định giả thuyết và kết quả cần quan sát

Trước khi mở hai session, viết một câu giả thuyết có thể kiểm chứng. Tránh mô tả mơ hồ như “thử xem có khóa không”.

Ví dụ:

> Khi Session A cập nhật hàng `id = 10` trong transaction chưa commit, câu `UPDATE` cùng hàng của Session B phải chờ. Sau khi A commit, B tiếp tục và giá trị cuối phản ánh cả hai cập nhật theo thứ tự commit.

Từ giả thuyết này, xác định bằng chứng cần có:

| Nội dung | Bằng chứng cần lưu |
|---|---|
| A đã lấy khóa | SQL của A, transaction ID, lock entry trên hàng/index mục tiêu |
| B đã yêu cầu cùng khóa | SQL của B, thời điểm bắt đầu, trạng thái waiting |
| B thực sự bị chặn | Lock wait relation hoặc process state, thời lượng chờ |
| A nhả khóa | Thời điểm `COMMIT`/`ROLLBACK` và trạng thái transaction sau đó |
| B tiếp tục | Thời điểm hoàn tất, row count hoặc kết quả trả về |
| Dữ liệu cuối đúng | Truy vấn kiểm tra hàng sau khi cả hai transaction kết thúc |

Nếu giả thuyết nói về deadlock, cần chứng minh một chu trình chờ hoặc lưu deadlock report của engine. Chỉ ghi nhận một session đang chờ là chưa đủ để kết luận deadlock.

## 3. Dùng mã run duy nhất để nối các bằng chứng

Mỗi lần chạy nên có một `run_id` riêng. Ví dụ:

```text
run_id: dtc-row274-20261114-001
experiment: same-row-update-blocking
```

Đưa mã này vào tên thư mục, tên file log và comment SQL khi phù hợp:

```sql
/* run=dtc-row274-20261114-001 session=A step=01 */
START TRANSACTION;

/* run=dtc-row274-20261114-001 session=A step=02 */
UPDATE accounts
SET balance = balance - 100
WHERE id = 10;
```

Comment giúp nhận diện câu lệnh trong log hoặc công cụ quan sát nếu hệ thống giữ nguyên query text. Không phải mọi driver, proxy hay log pipeline đều lưu comment; vì vậy vẫn cần ghi connection ID/PID và timestamp.

Không tái sử dụng `run_id` cho nhiều lần chạy khác nhau. Nếu phải lặp lại thí nghiệm sau khi đổi isolation level hoặc index, tạo run ID mới và ghi rõ run nào là baseline, run nào là biến thể.

## 4. Ghi thông tin môi trường trước khi chạy

Một kết quả đồng thời phụ thuộc vào phiên bản database, engine, cấu hình session, schema, index, driver và cách client gửi lệnh. Lưu ít nhất các thông tin sau:

| Nhóm | Thông tin nên ghi |
|---|---|
| Database | Tên hệ quản trị, phiên bản đầy đủ, build/distribution nếu có |
| Storage | Engine của bảng, cấu hình liên quan đến transaction/locking |
| Session | Isolation level, autocommit, lock timeout, statement timeout |
| Schema | `CREATE TABLE`, primary key, unique key, secondary index, foreign key và trigger liên quan |
| Dữ liệu | Fixture hoặc bản xuất tối thiểu tái tạo được điều kiện cạnh tranh |
| Client | Công cụ/CLI/IDE, phiên bản, JDBC driver hoặc thư viện truy cập dữ liệu |
| Kết nối | Connection ID/PID, database, user thử nghiệm, host và cách mở session |
| Thời gian | Time zone, độ chính xác timestamp và đồng hồ máy chạy client |
| Ứng dụng | Commit/version của code, cấu hình transaction manager và connection pool nếu có |

Không ghi password, access token, URL kết nối chứa secret hoặc dữ liệu cá nhân thật vào hồ sơ. Thay bằng tên biến môi trường hoặc giá trị đã che.

## 5. Thu thập cấu hình MySQL InnoDB

Chạy các truy vấn này trong từng session thử nghiệm vì một số giá trị là session-scoped:

```sql
SELECT
    VERSION() AS server_version,
    @@version_comment AS distribution,
    @@hostname AS server_host,
    DATABASE() AS current_database,
    CONNECTION_ID() AS connection_id,
    @@session.transaction_isolation AS isolation_level,
    @@session.autocommit AS autocommit_mode,
    @@session.innodb_lock_wait_timeout AS innodb_lock_wait_timeout,
    @@session.lock_wait_timeout AS metadata_lock_wait_timeout,
    @@session.time_zone AS session_time_zone,
    @@system_time_zone AS system_time_zone;
```

Lưu kết quả nguyên văn cho Session A và Session B. Nếu session được lấy từ connection pool, kiểm tra sau khi lấy connection vì pool hoặc ứng dụng có thể thay đổi isolation level/autocommit so với global default.

Để lưu các biến bổ sung có thể ảnh hưởng đến phép thử, có thể truy vấn có chọn lọc:

```sql
SHOW VARIABLES
WHERE Variable_name IN (
    'transaction_isolation',
    'autocommit',
    'innodb_lock_wait_timeout',
    'lock_wait_timeout',
    'sql_mode',
    'time_zone',
    'transaction_read_only'
);
```

Không cần chép toàn bộ `SHOW VARIABLES` nếu thí nghiệm không liên quan đến chúng. Hãy ghi rõ truy vấn nào đã được dùng để lấy cấu hình.

## 6. Thu thập cấu hình PostgreSQL khi cần đối chiếu

Với PostgreSQL, lưu phiên bản và các tham số session có liên quan:

```sql
SELECT
    version() AS server_version,
    current_database() AS database_name,
    current_user AS database_user,
    pg_backend_pid() AS backend_pid,
    current_setting('transaction_isolation') AS isolation_level,
    current_setting('transaction_read_only') AS transaction_read_only,
    current_setting('lock_timeout') AS lock_timeout,
    current_setting('statement_timeout') AS statement_timeout,
    current_setting('idle_in_transaction_session_timeout')
        AS idle_in_transaction_session_timeout,
    current_setting('TimeZone') AS time_zone;
```

Lưu kết quả theo từng backend. `SHOW` hoặc `current_setting()` cho biết cấu hình hiện tại của session, trong khi `pg_settings` có thêm nguồn gốc và phạm vi của một số giá trị. Đừng ghi giá trị mặc định của server thay cho giá trị session thực sự dùng trong thí nghiệm.

## 7. Lưu schema, index và các đối tượng liên quan

Dữ liệu giống nhau nhưng schema khác nhau có thể tạo execution plan và lock footprint khác nhau. Hãy lưu định nghĩa bảng và index trước khi chạy.

Với MySQL:

```sql
SHOW CREATE TABLE accounts;
SHOW INDEX FROM accounts;
```

Ghi cả engine, primary key, unique index, secondary index, foreign key, collation và trigger nếu chúng có thể tham gia vào thao tác. Nếu thí nghiệm liên quan đến trigger hoặc cascade, lưu định nghĩa của chúng.

Với PostgreSQL, có thể lưu DDL bằng công cụ dump schema hoặc truy vấn catalog phù hợp. Khi dùng `pg_dump --schema-only`, ghi lại phiên bản `pg_dump`, tham số và phạm vi schema được xuất.

Lưu execution plan cho từng câu lệnh quan trọng. Ví dụ MySQL:

```sql
EXPLAIN FORMAT=JSON
SELECT id
FROM accounts
WHERE id = 10
FOR UPDATE;
```

Execution plan cho biết optimizer dự kiến chọn index/access path nào. Nó không phải bằng chứng lock đã được cấp; cần ghép với lock instrumentation trong lúc transaction đang mở.

## 8. Tạo fixture nhỏ, xác định và có thể khôi phục

Thí nghiệm nên dùng dữ liệu tối thiểu đủ tạo ra tình huống cần quan sát. Fixture nhỏ giúp người khác hiểu key nào bị khóa và giảm khả năng kết quả thay đổi do dữ liệu ngoài dự kiến.

Ví dụ bảng:

```sql
CREATE TABLE accounts_lab (
    id BIGINT NOT NULL PRIMARY KEY,
    balance DECIMAL(12,2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    KEY ix_accounts_status (status)
) ENGINE = InnoDB;
```

Fixture:

```sql
INSERT INTO accounts_lab (id, balance, status, version) VALUES
(10, 500.00, 'ACTIVE', 1),
(20, 300.00, 'ACTIVE', 1),
(30, 100.00, 'LOCKED', 1);
```

Lưu nguyên văn câu lệnh tạo bảng và insert, cùng kết quả kiểm tra ban đầu:

```sql
SELECT id, balance, status, version
FROM accounts_lab
ORDER BY id;
```

Kết quả trước thí nghiệm là mốc để đối chiếu. Không chỉ ghi “đã có ba hàng”; hãy lưu key và giá trị cần thiết, vì chỉ một thay đổi nhỏ ở dữ liệu có thể làm truy vấn chọn index khác hoặc không còn thỏa điều kiện.

### Tính xác định của fixture

- Dùng khóa chính và giá trị rõ ràng, không dựa vào auto-increment đang bị chia sẻ với workload khác.
- Không dựa vào thứ tự hàng tự nhiên; mọi truy vấn kiểm tra cần `ORDER BY` theo khóa xác định.
- Đặt giá trị sao cho điều kiện query có kết quả rõ ràng, ví dụ có hàng nằm trong và ngoài range.
- Nếu thử duplicate key, gap lock hoặc phantom, ghi chính xác key nằm trước, trong và sau khoảng cần kiểm tra.
- Nếu cần chạy lại, reset fixture về đúng trạng thái ban đầu bằng script riêng.

## 9. Lưu dữ liệu đầu vào và trạng thái trước/sau

Đối với mỗi hàng liên quan, ghi tối thiểu:

| Thời điểm | Session | Truy vấn | Dữ liệu cần lưu |
|---|---|---|---|
| Trước run | Observer | Snapshot fixture | Primary key, các cột lọc/sắp xếp, giá trị nghiệp vụ và version |
| Sau bước A | Observer | Kiểm tra trạng thái nếu có thể quan sát | Hàng đã commit hay vẫn chưa commit; kết quả nhìn thấy theo session observer |
| Trong lúc B chờ | Observer | Lock/wait query | Transaction ID, connection/PID, object, index, lock mode, trạng thái wait |
| Sau khi nhả khóa | Observer | Kiểm tra kết quả | Row count, giá trị cuối, version và trạng thái transaction |

Không dùng một truy vấn observer duy nhất để thay thế mọi góc nhìn. Ở isolation level khác nhau, observer có thể dùng snapshot riêng và không thấy thay đổi chưa commit. Ghi rõ observer đang dùng isolation level nào và có mở transaction trước khi quan sát hay không.

Nếu thí nghiệm phụ thuộc dữ liệu nhạy cảm, dùng fixture giả lập hoặc dữ liệu đã ẩn danh. Không đưa thông tin khách hàng, token, email thật hoặc payload bí mật vào log dùng chung.

## 10. Viết lịch thực thi theo từng session

Lịch thực thi là phần quan trọng nhất của một thí nghiệm hai session. Ghi mỗi thao tác thành một bước riêng, có mã bước, câu lệnh, điều kiện tiếp tục và kết quả cần chờ.

Ví dụ thí nghiệm blocking trên cùng một hàng:

| Thứ tự | Session | Bước | Hành động | Trạng thái mong đợi |
|---:|---|---|---|---|
| 1 | A | A01 | `START TRANSACTION` | Transaction A mở |
| 2 | A | A02 | `UPDATE accounts_lab ... WHERE id=10` | A cập nhật một hàng và giữ X lock |
| 3 | Observer | O01 | Đọc transaction/lock metadata | Thấy lock A đã được cấp |
| 4 | B | B01 | `START TRANSACTION` | Transaction B mở |
| 5 | B | B02 | `UPDATE accounts_lab ... WHERE id=10` | B chờ lock của A |
| 6 | Observer | O02 | Đọc lock wait relation | Thấy B chờ A trên hàng/index liên quan |
| 7 | A | A03 | `COMMIT` | A kết thúc và nhả khóa |
| 8 | B | B02 | Chờ câu lệnh hoàn tất | B tiếp tục sau khi A commit |
| 9 | B | B03 | `COMMIT` | B kết thúc |
| 10 | Observer | O03 | Đọc trạng thái cuối | Giá trị phản ánh cả hai cập nhật theo thứ tự thực tế |

Trong lịch, ghi rõ khi nào người thực hiện cần đợi, không chạy bước tiếp theo trước khi xác nhận bước hiện tại đã đạt trạng thái mong muốn. Với deadlock, lịch cần ghi điểm A chờ B và điểm B chờ A để người khác tái tạo được chu trình.

## 11. Tách script cho Session A, Session B và Observer

Không gom tất cả SQL vào một file rồi yêu cầu người đọc tự đoán câu nào chạy ở cửa sổ nào. Tách script theo vai trò:

```text
experiment/
  README.md
  schema.sql
  fixture.sql
  reset.sql
  session-a.sql
  session-b.sql
  observer.sql
  verify.sql
  evidence/
    environment.txt
    schedule.csv
    session-a.log
    session-b.log
    observer.log
    final-state.csv
    notes.md
```

`session-a.sql` chỉ chứa các bước của A, `session-b.sql` chỉ chứa các bước của B, còn `observer.sql` chứa câu lệnh đọc process list/lock metadata. `README.md` giải thích thứ tự chạy, điểm chờ và cách kết thúc an toàn.

Không để file reset tự động chạy cùng script session. Reset có thể phá hủy trạng thái đang dùng để quan sát; người thực hiện phải chủ động chạy sau khi đã kết thúc mọi transaction.

## 12. Ví dụ script của hai session

### Session A

```sql
/* run=dtc-row274-20261114-001 session=A step=A01 */
SELECT CONNECTION_ID() AS connection_id,
       @@session.transaction_isolation AS isolation_level,
       @@session.autocommit AS autocommit_mode;

/* run=dtc-row274-20261114-001 session=A step=A02 */
START TRANSACTION;

/* run=dtc-row274-20261114-001 session=A step=A03 */
UPDATE accounts_lab
SET balance = balance - 100,
    version = version + 1
WHERE id = 10;

-- Dừng tại đây. Chỉ chạy COMMIT sau khi Observer xác nhận B đang chờ.
```

### Session B

```sql
/* run=dtc-row274-20261114-001 session=B step=B01 */
SELECT CONNECTION_ID() AS connection_id,
       @@session.transaction_isolation AS isolation_level,
       @@session.autocommit AS autocommit_mode;

/* run=dtc-row274-20261114-001 session=B step=B02 */
START TRANSACTION;

/* run=dtc-row274-20261114-001 session=B step=B03 */
UPDATE accounts_lab
SET balance = balance + 50,
    version = version + 1
WHERE id = 10;

-- Câu lệnh này được kỳ vọng chờ khi A vẫn giữ khóa.
-- Sau khi câu lệnh hoàn tất, ghi lại affected rows và thời gian.
```

### Observer

```sql
/* run=dtc-row274-20261114-001 session=O step=O01 */
SELECT
    trx_id,
    trx_mysql_thread_id AS connection_id,
    trx_started,
    trx_state,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;

/* run=dtc-row274-20261114-001 session=O step=O02 */
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
  AND OBJECT_NAME = 'accounts_lab';

/* run=dtc-row274-20261114-001 session=O step=O03 */
SELECT *
FROM performance_schema.data_lock_waits;
```

Session B có thể bị chặn ngay trong `UPDATE`, vì vậy ghi nhận connection ID trước khi chạy câu lệnh đó. Nếu client hiển thị query đang chạy nhưng không trả prompt, dùng Observer để lấy bằng chứng; đừng gửi thêm SQL vào cùng connection B khi statement vẫn đang chờ.

## 13. Ghi timestamp và thứ tự sự kiện chính xác

Thời gian rất hữu ích nhưng timestamp từ nhiều máy có thể lệch nhau. Khi A, B và Observer chạy trên các máy khác nhau, đồng hồ hệ điều hành không nhất thiết đồng bộ đến mili giây.

Hãy lưu:

- Timestamp bắt đầu và kết thúc theo clock của client.
- Timestamp database khi có thể, kèm time zone và độ chính xác.
- Thứ tự thao tác đã được điều phối bằng barrier hoặc xác nhận thủ công.
- Thời lượng chờ đo từ lúc gửi statement đến lúc nhận kết quả.
- Mốc `COMMIT`/`ROLLBACK` của transaction giữ khóa.

Với MySQL, có thể ghi timestamp database:

```sql
SELECT NOW(6) AS database_time,
       UTC_TIMESTAMP(6) AS database_time_utc,
       CONNECTION_ID() AS connection_id;
```

Với PostgreSQL:

```sql
SELECT clock_timestamp() AS wall_clock_time,
       transaction_timestamp() AS transaction_start_time,
       pg_backend_pid() AS backend_pid;
```

Trong PostgreSQL, `now()`/`transaction_timestamp()` cố định theo thời điểm bắt đầu transaction; `clock_timestamp()` trả thời gian thực tại lúc gọi. Nếu cần ghi mốc thời gian đang diễn ra trong transaction dài, phân biệt hai hàm này.

Timestamp không thay thế thứ tự nhân quả. Nếu A commit trước khi B được chạy, hãy ghi rõ điều đó trong schedule. Đừng suy ra thứ tự chỉ từ hai timestamp có chênh lệch rất nhỏ.

## 14. Ghi lại tham số và câu lệnh thực sự đã chạy

Prepared statement có thể dùng placeholder trong mã nguồn nhưng database nhận giá trị bind riêng. Để tái lập, cần lưu cả SQL template và tham số đã bind (đã che dữ liệu nhạy cảm).

Ví dụ:

```text
SQL template:
UPDATE accounts_lab
SET balance = balance - ?, version = version + 1
WHERE id = ?

Bound parameters:
1 = DECIMAL(100.00)
2 = BIGINT(10)
```

Ghi kiểu dữ liệu tham số nếu nó có thể ảnh hưởng đến implicit cast, index usage hoặc so sánh. Một chuỗi `'10'` và số nguyên `10` đôi khi dẫn đến conversion khác nhau tùy kiểu cột và database.

Nếu câu lệnh được sinh từ ORM, lưu SQL đã phát ra, tham số quan trọng, flush timing và transaction boundary. Chỉ lưu tên method repository là chưa đủ để hiểu câu SQL database thực sự thực thi.

## 15. Lưu kết quả của từng bước

Mỗi câu lệnh nên có kết quả gắn với step ID:

| Trường | Ví dụ |
|---|---|
| `run_id` | `dtc-row274-20261114-001` |
| `session` | `B` |
| `step_id` | `B03` |
| `connection_id` | `812` |
| `started_at` | `2026-11-14T14:30:10.123456Z` |
| `finished_at` | `2026-11-14T14:30:14.987654Z` |
| `statement` | `UPDATE accounts_lab ... WHERE id=10` |
| `parameters` | `id=10`, `delta=+50` |
| `result` | `affected_rows=1` |
| `wait_state` | `Waiting for record lock` |
| `error` | SQLSTATE/vendor code nếu có |

Nếu câu lệnh đang chờ và chưa kết thúc, `finished_at` để trống cho đến khi nó hoàn tất hoặc bị hủy. Không ghi thời gian kết thúc giả định.

Lưu nguyên văn output lỗi và error code. Với deadlock, giữ cả error phía client và deadlock report của server nếu có. Error message đã được ứng dụng dịch hoặc rút gọn có thể làm mất thông tin cần để phân loại lỗi.

## 16. Thu thập lock evidence trong MySQL

Trong MySQL 8.0, `performance_schema.data_locks` cho biết các khóa dữ liệu đang được giữ hoặc chờ, còn `data_lock_waits` liên kết yêu cầu chờ với khóa chặn.

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
  AND OBJECT_NAME = 'accounts_lab'
ORDER BY ENGINE_TRANSACTION_ID, INDEX_NAME, LOCK_DATA;
```

```sql
SELECT
    REQUESTING_ENGINE_TRANSACTION_ID AS waiting_trx,
    BLOCKING_ENGINE_TRANSACTION_ID AS blocking_trx,
    REQUESTING_THREAD_ID AS waiting_thread,
    BLOCKING_THREAD_ID AS blocking_thread,
    REQUESTING_ENGINE_LOCK_ID,
    BLOCKING_ENGINE_LOCK_ID
FROM performance_schema.data_lock_waits;
```

Lưu cả kết quả rỗng nếu truy vấn được chạy đúng thời điểm nhưng không có wait; đó cũng là bằng chứng. Ghi timestamp và connection ID của Observer để biết snapshot lock được lấy lúc nào.

Để liên kết thread với connection:

```sql
SELECT
    THREAD_ID,
    PROCESSLIST_ID,
    PROCESSLIST_USER,
    PROCESSLIST_HOST,
    PROCESSLIST_DB,
    PROCESSLIST_STATE,
    PROCESSLIST_TIME,
    PROCESSLIST_INFO
FROM performance_schema.threads
WHERE TYPE = 'FOREGROUND';
```

Các tên cột và trạng thái có thể khác theo phiên bản. Performance Schema cần được bật và user quan sát phải có quyền đọc các bảng tương ứng.

### Ghi nhận metadata lock riêng

Nếu thí nghiệm liên quan DDL hoặc `Waiting for table metadata lock`, lưu thêm `performance_schema.metadata_locks`. Không dùng `data_locks` làm bằng chứng duy nhất cho metadata lock.

```sql
SELECT
    OWNER_THREAD_ID,
    OBJECT_TYPE,
    OBJECT_SCHEMA,
    OBJECT_NAME,
    LOCK_TYPE,
    LOCK_DURATION,
    LOCK_STATUS
FROM performance_schema.metadata_locks
WHERE OBJECT_SCHEMA = DATABASE();
```

## 17. Thu thập lock evidence trong PostgreSQL

Với PostgreSQL, lưu các backend đang hoạt động và trạng thái chờ:

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    query_start,
    wait_event_type,
    wait_event,
    backend_xmin,
    left(query, 300) AS query_text
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
```

Lưu quan hệ blocker:

```sql
SELECT
    waiting.pid AS waiting_pid,
    waiting.query AS waiting_query,
    blocker.pid AS blocking_pid,
    blocker.query AS blocking_query,
    blocker.state AS blocking_state,
    blocker.xact_start AS blocking_xact_start
FROM pg_stat_activity AS waiting
CROSS JOIN LATERAL unnest(pg_blocking_pids(waiting.pid)) AS p(blocking_pid)
JOIN pg_stat_activity AS blocker
  ON blocker.pid = p.blocking_pid;
```

Lưu lock rows nếu cần phân tích loại khóa và đối tượng:

```sql
SELECT
    pid,
    locktype,
    relation::regclass AS relation_name,
    page,
    tuple,
    virtualxid,
    transactionid,
    mode,
    granted,
    fastpath
FROM pg_locks
ORDER BY pid, granted, locktype;
```

`pg_stat_activity`, `pg_locks` và `pg_blocking_pids()` là các nguồn quan sát bổ sung cho nhau. Một lock row có `granted = false` là request chưa được cấp; `pg_blocking_pids()` giúp xác định backend chặn trực tiếp. Nếu cần deadlock detail, lưu server log với nội dung deadlock report.

## 18. Ghi deadlock report và lỗi phía client

Nếu thí nghiệm tạo deadlock, lưu:

- Error code và SQLSTATE phía client.
- Transaction/session được chọn làm nạn nhân.
- Câu lệnh đang chờ của từng transaction.
- Lock đã được giữ và lock đang được yêu cầu.
- Table/index/record hoặc resource liên quan.
- Thứ tự các bước đã chạy trước khi tạo chu trình.
- Transaction nào bị rollback và trạng thái dữ liệu sau rollback.

MySQL có thể cung cấp deadlock gần nhất qua:

```sql
SHOW ENGINE INNODB STATUS\G
```

PostgreSQL ghi deadlock detail trong server log khi cấu hình logging phù hợp. `pg_stat_database.deadlocks` cho biết bộ đếm nhưng không thay thế report có các câu lệnh và lock resource.

Không chỉ lưu ảnh chụp màn hình thông báo deadlock. Hãy lưu text đầy đủ để có thể tìm kiếm, so sánh và trích xuất SQLSTATE/transaction ID.

## 19. Lưu kết quả dữ liệu sau thí nghiệm

Sau khi tất cả transaction đã commit/rollback, chạy truy vấn kiểm tra có thứ tự ổn định:

```sql
SELECT id, balance, status, version
FROM accounts_lab
WHERE id IN (10, 20, 30)
ORDER BY id;
```

Ghi:

- Giá trị trước thí nghiệm.
- Giá trị sau mỗi transaction commit thành công nếu có thể quan sát.
- Giá trị cuối cùng sau khi mọi session kết thúc.
- Row count của từng `UPDATE`/`DELETE`.
- Transaction nào commit, transaction nào rollback hoặc bị deadlock victim.

Nếu có transaction chưa commit, dữ liệu nhìn từ Observer có thể khác dữ liệu mà chính transaction đó nhìn thấy. Ghi rõ thời điểm lấy snapshot và isolation level của Observer. Không kết luận trạng thái cuối khi vẫn còn transaction đang hoạt động.

Đối với range/phantom test, lưu cả các key nằm trước, trong và sau khoảng, không chỉ những hàng đã trả về. Bằng chứng cần đủ để xác định một hàng mới có được chèn hay bị chặn.

## 20. Phân biệt kết quả mong đợi và kết quả thực tế

Một hồ sơ tái lập cần có cột riêng cho expected và observed. Không sửa giả thuyết sau khi thấy kết quả rồi ghi như thể đã dự đoán từ đầu.

| Step | Expected | Observed | Evidence reference | Kết luận |
|---|---|---|---|---|
| A02 | A cập nhật 1 hàng và giữ X lock | Ghi row count, lock mode thực tế | `observer.log#O01` | Khớp/không khớp |
| B03 | B chờ lock của A | Ghi wait state và duration | `observer.log#O02` | Khớp/không khớp |
| A03 | Commit giải phóng khóa | Ghi thời điểm commit | `session-a.log#A03` | Khớp/không khớp |
| B03 | B tiếp tục sau A commit | Ghi thời điểm hoàn tất và row count | `session-b.log#B03` | Khớp/không khớp |
| O03 | Giá trị cuối phản ánh hai cập nhật | Ghi dữ liệu thực tế | `final-state.csv` | Khớp/không khớp |

Nếu kết quả khác kỳ vọng, không xóa log hoặc chỉ chạy lại đến khi có kết quả mong muốn. Ghi lại sự khác biệt, giữ nguyên evidence, rồi tạo run mới sau khi điều chỉnh giả thuyết hoặc điều kiện.

## 21. Tái lập bằng barrier thay vì chỉ dựa vào thao tác nhanh tay

Khi hai người thao tác thủ công, rất dễ chạy nhầm thứ tự hoặc B bắt đầu trước khi A lấy khóa. Có thể dùng barrier đơn giản:

1. Session A chạy `START TRANSACTION` và câu lệnh lấy khóa.
2. Observer xác nhận lock A đã `GRANTED`.
3. Chỉ sau xác nhận đó mới cho Session B chạy câu lệnh cạnh tranh.
4. Observer xác nhận B đang `WAITING`.
5. A commit hoặc rollback theo kịch bản.
6. Ghi nhận B tiếp tục hoặc nhận lỗi.

Nếu dùng script tự động, barrier có thể là file signal, semaphore, lệnh điều phối hoặc callback trong test harness. Lưu mã nguồn script, phiên bản và tham số. Không dùng `sleep(1)` làm bằng chứng rằng A chắc chắn đã lấy khóa; thời gian cố định phụ thuộc tải máy và có thể tạo race condition.

Với một thí nghiệm cần so sánh nhiều isolation level, mỗi run nên reset fixture và dùng barrier giống nhau. Chỉ thay đổi một yếu tố mỗi lần để biết nguyên nhân của khác biệt.

## 22. Kiểm soát biến số giữa các lần chạy

Khi so sánh hai cấu hình, thay đổi một biến chính trong mỗi cặp run:

| Run | Isolation | Index | Autocommit | Biến đang kiểm chứng |
|---|---|---|---|---|
| R1 | `REPEATABLE READ` | Có index range | Tường minh | Baseline |
| R2 | `READ COMMITTED` | Có index range | Tường minh | Isolation level |
| R3 | `REPEATABLE READ` | Bỏ index range | Tường minh | Access path/index |
| R4 | `REPEATABLE READ` | Có index range | Autocommit | Transaction boundary |

Không thay isolation, index, dữ liệu và autocommit cùng lúc rồi kết luận yếu tố nào tạo ra kết quả. Nếu phải đổi nhiều thứ để tái tạo môi trường production, ghi rõ từng thay đổi và giới hạn của so sánh.

Các biến số khác cần giữ ổn định khi phù hợp: số hàng, phân bố dữ liệu, thống kê optimizer, query parameters, connection pool, client version, load nền và thời điểm chạy.

## 23. Lưu execution plan và thống kê dữ liệu

Execution plan có thể đổi khi thống kê hoặc phân bố dữ liệu đổi. Lưu plan gần thời điểm thí nghiệm, cùng số hàng và thống kê có liên quan.

Với MySQL, lưu:

- `EXPLAIN FORMAT=JSON` của câu lệnh quan trọng.
- `SHOW CREATE TABLE` và `SHOW INDEX`.
- Ước lượng `rows`, `filtered`, access type và key được chọn.
- Nếu dùng `EXPLAIN ANALYZE`, ghi rõ câu lệnh đã thực thi và môi trường chạy; không chạy tùy tiện locking statement trên hệ thống thật.

Với PostgreSQL, có thể lưu `EXPLAIN (FORMAT JSON)`; `EXPLAIN (ANALYZE, BUFFERS)` thực thi câu lệnh và có thể tạo tác động. Nếu câu lệnh ghi dữ liệu hoặc lấy khóa, chỉ thực hiện trong môi trường thử nghiệm và có kế hoạch rollback.

Không chỉ lưu ảnh chụp plan. Lưu output text hoặc JSON nguyên văn để có thể diff giữa các lần chạy.

## 24. Tổ chức thư mục và định dạng bằng chứng

Một cấu trúc thực tế:

```text
experiments/
  same-row-blocking/
    README.md
    schema.sql
    fixture.sql
    reset.sql
    session-a.sql
    session-b.sql
    observer-mysql.sql
    verify.sql
    runs/
      dtc-row274-20261114-001/
        environment.txt
        schema-output.sql
        schedule.csv
        explain-a.json
        session-a.log
        session-b.log
        observer-locks.txt
        deadlock-report.txt
        final-state.csv
        conclusion.md
```

Không phải file nào cũng cần có trong mọi run. Nếu không xảy ra deadlock, có thể ghi rõ `deadlock-report: not-applicable`; không tạo file giả hoặc để người đọc tưởng rằng đã thu thập.

### Ghi chú README của thí nghiệm

README nên nêu:

- Mục tiêu và giả thuyết.
- Yêu cầu môi trường và cách tạo database test.
- Cách chạy schema/fixture.
- Cách mở A, B và Observer.
- Thứ tự thực hiện và điểm chờ.
- Kết quả kỳ vọng và câu lệnh xác minh.
- Cách kết thúc transaction và reset dữ liệu.
- Những giới hạn đã biết của thí nghiệm.

## 25. Lưu output nguyên văn và bảo toàn tính toàn vẹn

Khi công cụ trả output, lưu nguyên văn thay vì chỉ ghi lại kết luận bằng lời. Output cần có nguồn và thời điểm:

- File nào đến từ Session A, B hay Observer?
- Lệnh nào tạo ra output?
- Thời điểm thu thập là trước hay sau commit?
- Có bị cắt bớt, ẩn cột hoặc lọc dòng không?
- Công cụ có chuyển đổi timezone hoặc định dạng số không?

Nếu phải che dữ liệu nhạy cảm, giữ một bản gốc ở nơi được kiểm soát theo chính sách nội bộ và tạo bản sanitized để chia sẻ. Ghi rõ trường nào đã được ẩn danh; không thay đổi khóa theo cách làm mất quan hệ giữa các bảng nếu quan hệ đó cần để tái lập.

Với bộ fixture và log quan trọng, có thể lưu checksum (ví dụ SHA-256) để phát hiện file bị thay đổi sau khi thu thập. Checksum chứng minh file hiện tại khớp với digest đã ghi, không chứng minh nội dung ban đầu là đúng hay thí nghiệm đã chạy như mô tả.

## 26. Dọn dẹp và khôi phục sau thí nghiệm

Một thí nghiệm khóa có thể để lại transaction mở, connection đang chờ hoặc dữ liệu đã thay đổi. Kết thúc có kiểm soát:

1. Ghi lại bằng chứng cuối cùng trước khi giải phóng khóa.
2. Commit hoặc rollback Session A theo kịch bản đã định.
3. Chờ Session B hoàn tất hoặc hủy câu lệnh theo cách đã ghi.
4. Commit/rollback Session B; không để connection trả về pool trong trạng thái transaction mở.
5. Xác nhận không còn transaction thử nghiệm hoặc lock wait.
6. Kiểm tra dữ liệu cuối cùng.
7. Chạy `reset.sql` hoặc tái tạo database fixture để đưa môi trường về trạng thái ban đầu.
8. Lưu output xác nhận reset thành công.

Nếu một session bị treo, xác định đúng connection ID/PID trước khi `KILL` hoặc terminate. Ghi lại lệnh can thiệp và kết quả. Không kết thúc nhầm connection của ứng dụng khác.

## 27. Mẫu hồ sơ run có thể sao chép

Mẫu sau có thể đặt trong `README.md` hoặc `conclusion.md` của từng run:

```markdown
# Experiment run

## Identity
- Run ID:
- Experiment name:
- Hypothesis:
- Date/time (UTC):
- Operator:

## Environment
- Database/version:
- Storage engine:
- Client/driver version:
- Host/database:
- Session A connection ID:
- Session B connection ID:
- Observer connection ID:
- Isolation level per session:
- Autocommit per session:
- Lock/statement timeouts:
- Time zone:

## Schema and fixture
- Schema file:
- Fixture file:
- Index definitions:
- Initial data evidence:
- Reset procedure:

## Schedule
- Step A01:
- Step A02:
- Step B01:
- Step B02:
- Observer checkpoints:
- Commit/rollback order:

## Evidence
- Session A log:
- Session B log:
- Observer lock output:
- Wait/blocker output:
- Execution plan:
- Deadlock report:
- Final data output:

## Expected vs observed
- Expected:
- Observed:
- Differences:
- Conclusion:

## Cleanup
- Transactions closed:
- Connections closed/reset:
- Fixture restored:
- Remaining artifacts:

## Limitations
- Load/background activity:
- Version-specific behavior:
- Missing evidence:
```

Để dễ so sánh, dùng cùng cấu trúc cho mọi run và thay đổi `run_id`, cấu hình hoặc biến thử nghiệm. Nếu một trường không áp dụng, ghi `N/A` cùng lý do thay vì bỏ trống không giải thích.

## 28. Mẫu schedule CSV

CSV hữu ích khi muốn lọc và so sánh nhiều lần chạy:

```csv
run_id,sequence,session,step_id,connection_id,action,started_at,finished_at,expected_state,observed_state,evidence_file
dtc-row274-001,1,A,A01,812,START TRANSACTION,2026-11-14T14:30:00.000Z,2026-11-14T14:30:00.002Z,transaction_open,transaction_open,session-a.log
dtc-row274-001,2,A,A02,812,UPDATE id=10,2026-11-14T14:30:01.000Z,2026-11-14T14:30:01.005Z,lock_granted,lock_granted,session-a.log
dtc-row274-001,3,B,B01,813,START TRANSACTION,2026-11-14T14:30:02.000Z,2026-11-14T14:30:02.001Z,transaction_open,transaction_open,session-b.log
dtc-row274-001,4,B,B02,813,UPDATE id=10,2026-11-14T14:30:03.000Z,,waiting,waiting,observer-locks.txt
dtc-row274-001,5,A,A03,812,COMMIT,2026-11-14T14:30:05.000Z,2026-11-14T14:30:05.004Z,lock_released,lock_released,session-a.log
```

Các timestamp trong ví dụ chỉ minh họa định dạng, không phải số liệu thực nghiệm. Trong run thật, điền thời gian được đo và không để lại kết quả giả định như thể đã quan sát.

## 29. Các sai lầm làm thí nghiệm không thể tái lập

| Sai lầm | Vì sao gây khó tái lập | Cách khắc phục |
|---|---|---|
| Không ghi phiên bản database | Optimizer và locking behavior có thể thay đổi giữa phiên bản | Lưu version/build đầy đủ |
| Chỉ lưu SQL, không lưu fixture | Dữ liệu khác có thể tạo plan hoặc lock khác | Lưu schema và dữ liệu tối thiểu |
| Không ghi isolation level của từng session | Hai session có thể dùng semantics khác nhau | Query session settings trước khi chạy |
| Dựa vào `sleep()` để đồng bộ | Tải máy làm thứ tự thực tế thay đổi | Dùng barrier và xác nhận trạng thái lock |
| Chỉ chụp ảnh màn hình | Khó tìm kiếm, diff và kiểm tra output bị cắt | Lưu log text/JSON/CSV nguyên văn |
| Không lưu connection ID | Không nối được process list với Session A/B | Ghi ID ngay khi mở session |
| Không ghi bind parameters | Câu SQL template không thể tái tạo input | Lưu giá trị/kiểu tham số đã che dữ liệu nhạy cảm |
| Không ghi trạng thái dữ liệu cuối | Không biết hiệu ứng nghiệp vụ đã xảy ra chưa | Chạy truy vấn verify có `ORDER BY` |
| Chạy lại trên dữ liệu cũ đã bị biến đổi | Kết quả mới không cùng điều kiện ban đầu | Reset fixture và tạo run ID mới |
| Chỉ ghi kết quả mong đợi | Không phân biệt giả thuyết với quan sát | Lưu expected và observed riêng |
| Không ghi lệnh cleanup | Có thể để transaction hoặc lock tồn tại | Ghi commit/rollback/terminate và kết quả xác nhận |

## 30. Bảo đảm an toàn và chất lượng bằng chứng

Thí nghiệm hai session thường cố ý giữ transaction mở để tạo blocking. Hãy thực hiện trên database test, giới hạn thời gian giữ khóa và chuẩn bị lệnh giải phóng trước khi bắt đầu.

- Dùng user và schema dành riêng cho thí nghiệm.
- Không chạy `UPDATE`, `DELETE`, `KILL` hoặc DDL thử nghiệm trên dữ liệu production.
- Không dùng dữ liệu cá nhân hoặc bí mật thật trong fixture có thể chia sẻ.
- Đặt timeout hợp lý để session không chờ vô hạn.
- Giữ một Observer connection riêng để thu thập bằng chứng mà không làm thay đổi transaction A/B.
- Hạn chế polling quá dày; truy vấn giám sát cũng tiêu thụ tài nguyên và có thể làm nhiễu phép đo.
- Lưu cả kết quả rỗng và lỗi quyền truy cập; đừng biến “không thu thập được” thành “không có lock”.

Nếu cần chứng minh hiệu năng, chạy nhiều lần với dữ liệu và tải tương đương, ghi median/percentile và điều kiện máy. Một lần chạy thủ công chỉ chứng minh một lịch thực thi cụ thể, không đủ để khẳng định hiệu năng tổng quát.

## 31. Quy trình tái lập một thí nghiệm từ đầu

1. Đọc giả thuyết và xác định biến duy nhất đang được kiểm chứng.
2. Chuẩn bị database test đúng phiên bản và engine.
3. Chạy `schema.sql`, sau đó `fixture.sql`.
4. Chạy truy vấn kiểm tra dữ liệu ban đầu và lưu output.
5. Mở Session A, B và Observer; ghi connection ID/PID và session settings của từng session.
6. Lưu `SHOW CREATE TABLE`/index và execution plan của câu lệnh liên quan.
7. Chạy từng bước theo schedule, dùng barrier để xác nhận điểm đồng bộ.
8. Lưu output câu lệnh, row count, timestamp, lock state và wait relation ở từng checkpoint.
9. Commit/rollback theo kịch bản và lưu kết quả dữ liệu cuối.
10. Đóng transaction, giải phóng mọi lock wait và reset fixture.
11. So sánh expected với observed, ghi sai khác và giới hạn của run.
12. Nếu thay đổi điều kiện, tạo run ID mới thay vì ghi đè bằng chứng của lần trước.

## 32. Tự kiểm tra

**Vì sao chỉ lưu hai câu SQL của Session A và B chưa đủ?**

Vì kết quả còn phụ thuộc phiên bản database, schema/index, dữ liệu đầu vào, isolation level, autocommit, tham số, thứ tự chạy và thời điểm commit/rollback. Cần lưu các điều kiện đó cùng bằng chứng thực tế.

**Vì sao cần connection ID của từng session?**

Connection ID giúp liên kết cửa sổ SQL với process list, transaction metadata và lock instrumentation. Không có ID, khó xác định dòng lock thuộc A hay B.

**Làm sao chứng minh B bị chặn bởi A?**

Lưu trạng thái chờ của B và quan hệ lock wait chỉ ra transaction/lock của A là blocker, cùng object/index/mode liên quan. Một ảnh chụp B đang chạy lâu không đủ.

**Timestamp có thể thay thế schedule không?**

Không. Đồng hồ giữa máy có thể lệch và hai sự kiện có timestamp gần nhau. Schedule cùng barrier chứng minh thứ tự nhân quả; timestamp bổ sung thời lượng và mốc thời gian.

**Vì sao phải lưu dữ liệu trước và sau thí nghiệm?**

Fixture chứng minh điều kiện ban đầu; trạng thái cuối chứng minh transaction nào đã commit/rollback và hiệu ứng dữ liệu thực tế. Chỉ lưu kết luận bằng lời không đủ để kiểm tra.

**Khi đổi isolation level hoặc index, có nên ghi đè run cũ không?**

Không. Tạo run ID mới và giữ nguyên bằng chứng cũ để có thể so sánh biến thể với baseline.

**Nếu Observer không thấy lock row, có thể kết luận không có blocking không?**

Không. Có thể lấy mẫu sai thời điểm, thiếu quyền hoặc đang xem nhầm loại lock. Cần ghi thời điểm truy vấn, trạng thái session và nguồn instrumentation; metadata lock, data lock và các wait khác có nguồn quan sát riêng.

Một thí nghiệm đồng thời chỉ có thể được người khác tái lập khi hồ sơ nối được **môi trường, dữ liệu, lịch từng session và bằng chứng quan sát**. Hãy giữ nguyên output, phân biệt dự đoán với kết quả thực tế, tạo run ID mới cho mỗi biến thể và kết thúc bằng kiểm tra dữ liệu cùng trạng thái transaction. Cách ghi chép này biến một lần thử thủ công thành một bằng chứng kỹ thuật có thể kiểm tra, so sánh và chạy lại.
