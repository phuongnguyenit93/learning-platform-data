# Khoanh vùng thời điểm, phạm vi, thay đổi gần nhất và bằng chứng

Khi MySQL gặp sự cố, triệu chứng đầu tiên thường chưa chỉ ra nguyên nhân. Ứng dụng báo timeout có thể do truy vấn chậm, lock wait, pool hết connection, mạng lỗi hoặc server quá tải. Một replica bị trễ có thể do source tăng tải ghi, SQL applier bị lỗi, I/O chậm hoặc một transaction lớn. Nếu thay đổi cấu hình hay khởi động lại ngay khi chưa thu thập dữ liệu, dấu vết quan trọng có thể biến mất và phạm vi ảnh hưởng khó xác định hơn.

Cách xử lý hiệu quả bắt đầu bằng bốn câu hỏi: **sự cố bắt đầu khi nào, ảnh hưởng đến đâu, điều gì vừa thay đổi và bằng chứng nào xác nhận giả thuyết?** Bài học này thuộc chương **Xử lý sự cố** của module **DATABASE_MYSQL**. Trong lộ trình làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và vận hành, kỹ năng khoanh vùng giúp biến triệu chứng rời rạc thành một hướng điều tra có thể kiểm chứng.

## 1. Bốn trục điều tra

Không bắt đầu bằng việc đoán một nguyên nhân. Ghi nhận bốn trục trước:

| Trục | Câu hỏi | Ví dụ bằng chứng |
|---|---|---|
| Thời điểm | Bắt đầu lúc nào? Có liên tục hay theo đợt? Lần cuối hoạt động bình thường là khi nào? | Timeline, timestamp log, deploy time, server uptime |
| Phạm vi | Ai và thành phần nào bị ảnh hưởng? Tất cả truy vấn hay một endpoint, tenant, node hoặc loại thao tác? | Tỷ lệ request lỗi, host, connection ID, query digest |
| Thay đổi gần nhất | Điều gì thay đổi ngay trước thời điểm lỗi? | Deploy, DDL, index, cấu hình, traffic, failover, driver |
| Bằng chứng | Dữ liệu nào quan sát trực tiếp được và có thể tái kiểm tra? | Error log, metrics, Performance Schema, EXPLAIN, replication status |

Mỗi giả thuyết nên được ghi riêng với bằng chứng ủng hộ, bằng chứng phản bác và phép kiểm tra tiếp theo. Ví dụ: “p95 tăng sau khi thêm index” là một tương quan theo thời gian; cần xem query plan, rows examined, I/O và workload trước khi kết luận index gây chậm.

## 2. Ghi nhận triệu chứng và thời điểm

Mở một incident record ngắn ngay khi nhận thông báo. Tối thiểu ghi:

- Thời điểm phát hiện và thời điểm bắt đầu ước tính.
- Thời điểm gần nhất hệ thống được xác nhận hoạt động bình thường.
- Timezone của timestamp; ưu tiên chuẩn hóa timeline về UTC.
- Triệu chứng cụ thể: connection refused, timeout, SQL error, dữ liệu sai, query chậm, replica lag hay mất khả năng ghi.
- Tỷ lệ ảnh hưởng: số request lỗi trên tổng request, số tenant hoặc người dùng bị ảnh hưởng.
- Thành phần: ứng dụng, MySQL instance, primary/replica, Router, proxy, connection pool hoặc mạng.
- Người/tiến trình đã thực hiện thay đổi hoặc thao tác khắc phục, kèm thời điểm.

Đừng ghi “database chậm từ sáng” nếu có thể ghi “p95 của endpoint tạo đơn tăng từ 120 ms lên 2,4 s trong khoảng 09:12–09:18 UTC; request đọc vẫn bình thường, request ghi timeout tăng”. Một mô tả định lượng giúp nhóm khác xác minh cùng một hiện tượng.

### Chuẩn hóa thời gian

Ứng dụng, MySQL, hệ điều hành, proxy và monitoring có thể dùng timezone khác nhau. Kiểm tra timezone MySQL:

~~~sql
SELECT
  UTC_TIMESTAMP(6) AS observed_utc,
  NOW(6) AS session_now,
  @@GLOBAL.time_zone AS global_time_zone,
  @@SESSION.time_zone AS session_time_zone,
  @@system_time_zone AS system_time_zone;
~~~

Ghi timezone khi xuất log từ từng hệ thống. Nếu đồng hồ host lệch nhau, timeline có thể khiến một thay đổi dường như xảy ra sau sự cố dù thực tế nó xảy ra trước. Kiểm tra đồng bộ thời gian của host và dịch vụ log.

### Xác định lần cuối hoạt động bình thường

So sánh dữ liệu monitoring với thời điểm triển khai gần nhất. Tìm điểm thay đổi đầu tiên ở latency, error rate, throughput, CPU, I/O, connection count hoặc replication lag. Đừng chỉ lấy thời điểm người dùng đầu tiên báo lỗi; sự cố có thể đã bắt đầu trước đó nhưng chưa vượt ngưỡng cảnh báo.

## 3. Xác định phạm vi ảnh hưởng

Phạm vi thường giúp thu hẹp nguyên nhân nhanh hơn một thông báo lỗi đơn lẻ. Hãy hỏi theo từng lớp:

| Phạm vi | Cách phân biệt |
|---|---|
| Toàn hệ thống hay một ứng dụng | Nhiều service cùng lỗi hay chỉ một service dùng MySQL? |
| Tất cả người dùng hay một nhóm | Có tập trung theo tenant, region, tài khoản hoặc loại dữ liệu không? |
| Tất cả database hay một schema | Các truy vấn tới schema khác có bình thường không? |
| Đọc hay ghi | SELECT có chạy nhưng INSERT/UPDATE timeout không? |
| Một truy vấn hay nhiều truy vấn | Một digest tăng thời gian hay toàn bộ query latency cùng tăng? |
| Một node hay cả topology | Primary lỗi, replica lỗi, Router lỗi hay mọi member đều bị ảnh hưởng? |
| Kết nối mới hay kết nối đang mở | Lỗi xác thực khi connect, hay session đang dùng bị timeout? |
| Mọi thời điểm hay theo đợt | Lỗi trùng giờ batch, backup, báo cáo hoặc traffic peak không? |

Ví dụ:

- Chỉ request ghi bị chậm trong khi đọc bình thường: kiểm tra lock, transaction dài, index maintenance, binlog và I/O.
- Chỉ một tenant bị lỗi: kiểm tra dữ liệu, khóa unique, phân vùng truy vấn, quyền hoặc tham số của tenant đó.
- Tất cả service không mở được connection mới nhưng session cũ còn chạy: kiểm tra mạng, DNS, TLS, xác thực, max_connections và pool.
- Chỉ replica bị trễ: kiểm tra receiver/applier, relay log, transaction lớn và tài nguyên replica.
- Nhiều truy vấn không liên quan cùng tăng latency: nghi ngờ tài nguyên hoặc contention dùng chung trước khi tối ưu riêng từng câu SQL.

Không mở rộng phạm vi kết luận vượt quá bằng chứng. Nếu chỉ một endpoint được đo, hãy nói “endpoint này bị ảnh hưởng”; chưa đủ cơ sở nói “toàn bộ MySQL bị chậm”.

## 4. Lập timeline thay đổi gần nhất

Tạo một dòng thời gian kết hợp sự kiện ứng dụng và database. Các thay đổi nên kiểm tra gồm:

- Deploy ứng dụng, thay đổi ORM, JDBC driver hoặc Connector/J.
- Migration DDL: thêm/xóa cột, index, constraint, partition hoặc thay đổi kiểu dữ liệu.
- Thay đổi SQL, query plan, prepared statement hoặc batch size.
- Thay đổi SQL mode, timezone, isolation level, charset/collation hoặc optimizer settings.
- Thay đổi connection pool: maximum pool size, timeout, lifetime, init SQL.
- Thay đổi MySQL version, patch, plugin, authentication hoặc cấu hình server.
- Failover, restart, thay primary, thêm/bớt replica hoặc thay Router.
- Backup, restore, ANALYZE TABLE, import/export, purge log hoặc batch job.
- Tăng đột biến traffic, dữ liệu, số kết nối hoặc kích thước transaction.
- Thay đổi hạ tầng: CPU, RAM, disk, filesystem, network, DNS, firewall, TLS certificate và secret.

Ví dụ bảng timeline:

| Thời điểm UTC | Sự kiện | Phạm vi | Nguồn xác nhận |
|---|---|---|---|
| 08:55 | Deploy API version mới | service orders | deployment record |
| 09:02 | p95 ghi tăng | endpoint create-order | APM |
| 09:04 | lock wait tăng | MySQL primary | Performance Schema |
| 09:06 | rollback deploy bắt đầu | service orders | deployment record |
| 09:12 | lock wait và p95 giảm | endpoint create-order | APM + DB metrics |

Bảng này chỉ là ví dụ cách ghi. Không điền sự kiện giả định vào incident thật; mọi mốc phải có log hoặc người xác nhận. Tương quan thời gian giúp xếp ưu tiên kiểm tra, nhưng vẫn cần bằng chứng kỹ thuật để xác định nguyên nhân.

### Thay đổi có thể không được ghi trong deploy log

Một thay đổi thủ công trên production, cron job, event scheduler, script DBA hoặc thao tác từ console có thể không nằm trong lịch sử CI/CD. Hỏi rõ ai đã chạy lệnh, trên instance nào, bằng tài khoản nào và thời điểm nào. Đối chiếu audit log nếu hệ thống đã bật và chính sách lưu giữ cho phép.

## 5. Bảo toàn bằng chứng trước khi thay đổi trạng thái

Trước khi restart, kill session, purge log, reset replication hoặc thay đổi optimizer settings, thu thập bằng chứng còn tồn tại. Những thao tác này có thể xóa trạng thái đang giúp xác định nguyên nhân.

Gói bằng chứng cơ bản nên có:

1. Timeline và phạm vi ảnh hưởng.
2. Phiên bản MySQL, cấu hình liên quan và uptime.
3. Error log cùng application/proxy log trong cửa sổ sự cố.
4. Snapshot metrics và status counters.
5. Active sessions, query digest và lock waits.
6. InnoDB status nếu nghi ngờ lock/deadlock.
7. Replication status nếu có replica.
8. Query plan và tham số đại diện nếu một truy vấn cụ thể bị chậm.
9. Thay đổi gần nhất và kết quả từng bước mitigation.

Lưu timestamp, nguồn, host/instance và cách thu thập cho mỗi mẫu. Che password, token, email, dữ liệu cá nhân và literal nhạy cảm trước khi chia sẻ log. SQL_TEXT có thể chứa giá trị do người dùng nhập; chỉ lưu nội dung cần thiết theo chính sách bảo mật.

## 6. Kiểm tra trạng thái instance ban đầu

Bắt đầu bằng những câu lệnh chỉ đọc:

~~~sql
SELECT
  VERSION() AS mysql_version,
  @@version_comment AS version_comment,
  @@hostname AS hostname,
  @@port AS port,
  @@server_id AS server_id,
  @@server_uuid AS server_uuid;

SHOW GLOBAL STATUS LIKE 'Uptime';
SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Threads_running';
SHOW GLOBAL STATUS LIKE 'Max_used_connections';
SHOW GLOBAL STATUS LIKE 'Aborted_connects';
SHOW GLOBAL STATUS LIKE 'Connections';
SHOW GLOBAL STATUS LIKE 'Slow_queries';
~~~

Các giá trị status thường là bộ đếm tích lũy từ lần khởi động hoặc lần reset status gần nhất. Một giá trị đơn lẻ chưa đủ cho biết tốc độ tăng. Chụp hai snapshot cách nhau một khoảng thời gian đã biết rồi tính delta; đồng thời kiểm tra Uptime để phát hiện server vừa restart.

Ví dụ: nếu `Connections` tăng 12.000 trong 5 phút, đó là khoảng 40 lần mở connection mỗi giây trong cửa sổ đó. Cần đối chiếu với pool behavior và traffic trước khi kết luận connection churn bất thường.

### Process list

~~~sql
SHOW FULL PROCESSLIST;
~~~

Hoặc xem session qua Performance Schema:

~~~sql
SELECT
  PROCESSLIST_ID,
  PROCESSLIST_USER,
  PROCESSLIST_HOST,
  PROCESSLIST_DB,
  PROCESSLIST_COMMAND,
  PROCESSLIST_TIME,
  PROCESSLIST_STATE,
  LEFT(PROCESSLIST_INFO, 300) AS statement_sample
FROM performance_schema.threads
WHERE TYPE = 'FOREGROUND'
ORDER BY PROCESSLIST_TIME DESC;
~~~

Tìm session đang chạy lâu, chờ lock, chờ I/O hoặc có trạng thái bất thường. Một session có TIME lớn không nhất thiết là lỗi; nó có thể đang chạy truy vấn batch hợp lệ hoặc idle trong transaction. Đọc STATE, câu SQL, transaction và blocker trước khi hành động.

## 7. Tìm lỗi trong error log và slow query log

Lấy vị trí error log:

~~~sql
SHOW VARIABLES LIKE 'log_error';
~~~

Đường dẫn và cách truy cập phụ thuộc cách cài MySQL hoặc dịch vụ managed. Với dịch vụ cloud, log có thể được xuất qua console/monitoring thay vì đọc file trực tiếp. Tìm các thông báo cùng cửa sổ sự cố như crash recovery, InnoDB error, disk full, access denied, aborted connection, replication error, plugin/TLS failure hoặc shutdown/restart.

Kiểm tra slow query log:

~~~sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
  'slow_query_log',
  'long_query_time',
  'log_output',
  'log_queries_not_using_indexes'
);
~~~

Slow log giúp xác định truy vấn vượt ngưỡng ghi log, nhưng không ghi lại mọi loại latency ở ứng dụng. Một request có thể chậm do chờ connection pool, DNS, TLS, network hoặc lock trước khi câu SQL được thực thi. Vì vậy, ghép slow log với APM và Performance Schema.

Không bật `log_queries_not_using_indexes` hoặc đặt `long_query_time` quá thấp trên production mà chưa đánh giá lượng log, dung lượng đĩa và overhead. Nếu cần bật tạm, xác định cửa sổ, người chịu trách nhiệm, nơi lưu log và thời điểm tắt/khôi phục cấu hình.

## 8. Khoanh vùng query chậm bằng Performance Schema

Bảng digest tổng hợp câu lệnh tương tự theo cấu trúc SQL. Ví dụ lấy các digest tiêu tốn tổng thời gian cao:

~~~sql
SELECT
  SCHEMA_NAME,
  DIGEST,
  LEFT(DIGEST_TEXT, 200) AS query_sample,
  COUNT_STAR,
  ROUND(AVG_TIMER_WAIT / 1000000000000, 6) AS avg_seconds,
  ROUND(MAX_TIMER_WAIT / 1000000000000, 6) AS max_seconds,
  SUM_ROWS_EXAMINED,
  SUM_ROWS_SENT,
  SUM_ERRORS,
  SUM_WARNINGS
FROM performance_schema.events_statements_summary_by_digest
WHERE SCHEMA_NAME IS NOT NULL
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
~~~

Timer trong Performance Schema được biểu diễn bằng picosecond; chia cho (10^{12}) để đổi sang giây. Các summary là số liệu tích lũy trong khoảng từ khi server khởi động hoặc từ lần reset summary gần nhất. Chụp snapshot đầu/cuối và tính delta nếu cần phân tích một cửa sổ cụ thể.

Cách đọc:

- `COUNT_STAR` cao: digest được gọi thường xuyên.
- `AVG_TIMER_WAIT` cao: thời gian trung bình mỗi lần chạy lớn.
- `SUM_ROWS_EXAMINED` cao so với `SUM_ROWS_SENT`: có thể phải đọc nhiều hàng để trả ít hàng.
- `SUM_ERRORS` hoặc `SUM_WARNINGS` tăng: có lỗi hoặc cảnh báo SQL cần phân loại.
- `MAX_TIMER_WAIT` cao: có lần chạy bất thường; cần tìm timestamp và request cụ thể ở log/telemetry chi tiết hơn.

Digest summary không cung cấp p95/p99 của từng request. Dùng APM hoặc histogram ở tầng ứng dụng cho percentile; dùng digest để xác định nhóm câu SQL có chi phí lớn.

Nếu Performance Schema consumer/instrument chưa bật hoặc bảng không có dữ liệu, ghi nhận giới hạn đó. Không reset toàn bộ summary trên production chỉ để bắt đầu lại phép đo nếu các nhóm vận hành khác đang phụ thuộc số liệu hiện tại.

## 9. Kiểm tra lock wait và deadlock

Nếu request ghi chậm hoặc timeout, kiểm tra transaction đang chờ và transaction đang chặn.

~~~sql
SELECT
  w.REQUESTING_ENGINE_TRANSACTION_ID,
  w.BLOCKING_ENGINE_TRANSACTION_ID,
  r.OBJECT_SCHEMA,
  r.OBJECT_NAME,
  r.INDEX_NAME,
  r.LOCK_TYPE,
  r.LOCK_MODE AS requesting_lock_mode,
  b.LOCK_MODE AS blocking_lock_mode
FROM performance_schema.data_lock_waits AS w
JOIN performance_schema.data_locks AS r
  ON r.ENGINE = w.ENGINE
 AND r.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS b
  ON b.ENGINE = w.ENGINE
 AND b.ENGINE_LOCK_ID = w.BLOCKING_ENGINE_LOCK_ID;
~~~

Kết hợp với `performance_schema.threads`, `events_transactions_current` và `events_statements_current` để xác định connection, câu SQL và transaction liên quan. Cấu trúc cột cụ thể cần đối chiếu với phiên bản MySQL đang chạy.

Lấy trạng thái InnoDB:

~~~sql
SHOW ENGINE INNODB STATUS\G
~~~

Phần TRANSACTIONS cho biết transaction đang hoạt động và lock wait; phần LATEST DETECTED DEADLOCK ghi deadlock gần nhất được InnoDB phát hiện. Đây là snapshot tại thời điểm truy vấn, không phải lịch sử đầy đủ của mọi deadlock. Nếu cần lịch sử, dùng error log/monitoring hoặc cấu hình ghi deadlock phù hợp.

Một deadlock được InnoDB phát hiện thường khiến một transaction bị rollback để phá vòng chờ. Ứng dụng cần xử lý lỗi deadlock bằng retry có giới hạn và có backoff phù hợp. Không retry vô hạn một transaction chắc chắn xung đột.

**Không kill session chỉ vì PROCESSLIST_TIME lớn.** Trước khi can thiệp, xác định session đang chặn hay đang chờ, chủ sở hữu, câu lệnh, transaction đã sửa dữ liệu gì và tác động khi rollback. Kill sai session có thể làm tăng thời gian rollback hoặc gây gián đoạn thêm.

## 10. Kiểm tra kết nối và connection pool

Nếu ứng dụng báo không lấy được connection, phân biệt các lớp:

1. Ứng dụng không phân giải được hostname hoặc không tới được port.
2. TLS handshake hoặc chứng thư thất bại.
3. Authentication/authorization bị từ chối.
4. MySQL đạt giới hạn connection.
5. Connection pool hết connection do request giữ quá lâu hoặc leak.
6. Connection được tạo nhưng query bị chờ lock/tài nguyên.

Các status cần xem:

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
  'Threads_connected',
  'Threads_running',
  'Max_used_connections',
  'Aborted_connects',
  'Connections'
);

SHOW VARIABLES LIKE 'max_connections';
~~~

So sánh `Max_used_connections` với `max_connections`, theo dõi `Threads_connected` theo thời gian và kiểm tra pool active/idle/pending ở phía ứng dụng. `Threads_connected` là số session đang kết nối; `Threads_running` là số thread không ở trạng thái ngủ. Chúng không thay thế số đo pool wait hoặc request latency.

Nếu `Threads_connected` cao nhưng `Threads_running` thấp, có thể ứng dụng giữ nhiều connection idle hoặc pool lớn. Nếu pool pending tăng nhưng MySQL còn nhiều connection trống, kiểm tra pool sizing, leak, timeout và giới hạn ở proxy. Nếu MySQL chạm max_connections, tìm nguồn mở connection và tốc độ tăng trước khi nâng giới hạn; tăng max_connections có thể làm tăng bộ nhớ và contention.

Ở ứng dụng, thu thập HikariCP metrics như active, idle, pending, maximum pool size và connection acquisition time. Đừng chỉ nhìn số connection phía MySQL để kết luận pool khỏe.

## 11. Kiểm tra replication khi phạm vi chỉ ảnh hưởng replica

Với MySQL 8.0.22 trở lên, dùng:

~~~sql
SHOW REPLICA STATUS\G
~~~

Ở các phiên bản cũ hơn, cú pháp là `SHOW SLAVE STATUS\G`. Ghi nhận tối thiểu:

- Trạng thái receiver và applier thread.
- Last_IO_Error và Last_SQL_Error.
- GTID đã nhận và đã thực thi.
- Relay log còn chờ.
- Seconds_Behind_Source nếu được cung cấp.
- Thời điểm lần cuối nhận/applied transaction.

Không dùng riêng `Seconds_Behind_Source` để kết luận replica đã đồng bộ. Giá trị có thể NULL hoặc không phản ánh đầy đủ tình trạng khi receiver/applier dừng, khi source idle hoặc khi có vấn đề về timestamp. Đối chiếu GTID, relay log, worker status và lỗi cụ thể.

Với parallel applier, kiểm tra worker và coordinator trong Performance Schema. Một worker lỗi có thể làm applier dừng hoặc gây backlog. Xác định transaction gây lỗi trước khi skip hoặc reset replication; bỏ qua transaction có thể làm dữ liệu replica lệch source.

## 12. Kiểm tra query plan khi chỉ một truy vấn bị ảnh hưởng

Nếu một digest hoặc endpoint nổi bật, lấy câu SQL đại diện cùng bộ tham số đã gây sự cố. Kiểm tra plan:

~~~sql
EXPLAIN FORMAT=JSON
SELECT
  id,
  customer_id,
  created_at,
  total_amount
FROM orders
WHERE customer_id = 1001
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 50;
~~~

Xem access type, key, estimated rows, join order, temporary table, filesort và partition pruning. Nếu cần actual rows và thời gian iterator, dùng `EXPLAIN ANALYZE` trên môi trường an toàn hoặc truy vấn SELECT đã được đánh giá:

~~~sql
EXPLAIN ANALYZE
SELECT
  id,
  total_amount
FROM orders
WHERE customer_id = 1001
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 50;
~~~

EXPLAIN ANALYZE thực thi câu truy vấn. Không dùng nó một cách mù quáng trên truy vấn rất nặng hoặc trên production đang quá tải. Đối chiếu estimated rows với actual rows, kiểm tra thống kê index/histogram và dữ liệu tham số. Không thêm index hoặc ép optimizer trước khi biết chi phí đọc, ghi và dung lượng của thay đổi đó.

## 13. Phân loại triệu chứng và hướng điều tra đầu tiên

| Triệu chứng | Hướng điều tra ưu tiên |
|---|---|
| Không kết nối được MySQL | DNS, network, TLS, auth, port, max_connections, pool pending |
| Nhiều query cùng chậm | CPU, RAM, disk I/O, network, connection pool, backup/batch, global lock |
| Một query chậm | Digest, tham số, EXPLAIN, rows examined, index, statistics |
| Ghi chậm nhưng đọc bình thường | Lock waits, transaction dài, index maintenance, redo/binlog, I/O |
| Deadlock tăng | Transaction boundary, thứ tự cập nhật hàng, index và retry logic |
| Replica lag | Receiver/applier, worker error, relay log, transaction lớn, I/O |
| Dữ liệu sai hoặc thiếu | Migration/import, transaction boundary, duplicate handling, timezone/collation, replication |
| Chỉ một tenant lỗi | Dữ liệu và cardinality tenant, tham số, quyền, unique key và truy vấn phân vùng |
| Lỗi sau deploy | Diff code, SQL, driver, migration, config và thời điểm rollout |
| Lỗi sau restart | Error log, crash recovery, config/plugin, connection pool reconnect, replication rejoin |

Bảng này là điểm bắt đầu, không phải kết luận tự động. Một triệu chứng có thể có nhiều nguyên nhân; luôn xác minh bằng dữ liệu của instance và request bị ảnh hưởng.

## 14. Thử nghiệm giả thuyết có kiểm soát

Sau khi thu thập bằng chứng, lập danh sách giả thuyết theo thứ tự xác suất và mức tác động. Mỗi giả thuyết cần một phép thử phân biệt được nó với các nguyên nhân khác.

Ví dụ:

| Giả thuyết | Bằng chứng cần tìm | Phép kiểm tra tiếp theo |
|---|---|---|
| Một index mới làm query chậm | Plan đổi, rows examined hoặc I/O tăng sau migration | So sánh EXPLAIN và benchmark trên snapshot trước/sau |
| Transaction dài gây lock wait | Có blocker lâu, transaction mở lâu, request ghi chờ | Xác định owner và câu SQL của blocker; đối chiếu transaction log |
| Pool cạn connection | Hikari pending/active chạm giới hạn, acquisition time tăng | Đối chiếu pool metrics với Threads_connected/running |
| Replica không theo kịp | Relay log backlog, worker bận hoặc có lỗi | Xem replica status, worker status và tài nguyên |
| SQL mode thay đổi | @@SESSION.sql_mode khác baseline, lỗi chuyển đổi mới | So sánh config và session trên connection gây lỗi |

Thay đổi từng yếu tố trong môi trường thử nghiệm khi có thể. Nếu phải mitigation trên production, ghi lại giá trị trước thay đổi, người thực hiện, thời điểm, phạm vi và tiêu chí đánh giá kết quả. Không đồng thời đổi index, pool size, isolation level và optimizer settings vì sau đó khó biết thay đổi nào tác động.

## 15. Chọn hành động giảm ảnh hưởng

Tách rõ **thu thập bằng chứng**, **mitigation** và **sửa nguyên nhân gốc**. Mitigation nhằm khôi phục dịch vụ; nó không tự chứng minh nguyên nhân.

Một số hành động thường cần cân nhắc:

- Giảm hoặc tạm dừng batch/reporting gây cạnh tranh tài nguyên, sau khi xác nhận chủ sở hữu và tác động nghiệp vụ.
- Hạn chế traffic hoặc bật backpressure nếu connection pool/server quá tải.
- Rollback ứng dụng hoặc migration chỉ khi tương thích schema và có kế hoạch dữ liệu rõ.
- Chuyển traffic sang replica/primary khác chỉ theo quy trình failover đã kiểm thử.
- Kill transaction chặn chỉ sau khi xác minh chủ sở hữu, câu SQL, dữ liệu đã thay đổi và thời gian rollback có thể phát sinh.
- Tăng giới hạn tài nguyên chỉ khi có số liệu chứng minh giới hạn đó là nút thắt và host còn headroom.

Tránh các thao tác phá hủy bằng phản xạ như `RESET MASTER`, xóa relay log, skip transaction, drop index, xóa dữ liệu, flush/reset status hoặc restart liên tục. Một số thao tác làm mất bằng chứng hoặc thay đổi trạng thái replication và dữ liệu. Chỉ thực hiện khi đã xác định rõ mục tiêu, hậu quả, backup/restore path và người phê duyệt theo quy trình vận hành.

## 16. Mẫu ghi nhận incident và handoff

Có thể dùng mẫu sau trong ticket hoặc incident channel:

~~~text
Incident ID:
Môi trường / cluster / instance:
Thời điểm bắt đầu (UTC):
Thời điểm phát hiện (UTC):
Lần cuối hoạt động bình thường (UTC):

Triệu chứng quan sát được:
Phạm vi ảnh hưởng:
- Ứng dụng / endpoint:
- Tenant / nhóm người dùng:
- Read / write:
- Primary / replica / Router:
- Tỷ lệ lỗi và latency:

Thay đổi gần nhất:
- Deploy / migration / config:
- Traffic / batch / backup:
- Hạ tầng / network / certificate:
- Người thực hiện và thời điểm:

Bằng chứng:
- Error/application log:
- MySQL version, uptime và status delta:
- Processlist / digest:
- Lock wait / InnoDB status:
- Replication status:
- Query plan:
- Host và pool metrics:

Giả thuyết:
Bằng chứng ủng hộ:
Bằng chứng phản bác:
Phép kiểm tra tiếp theo:

Mitigation đã thực hiện:
Kết quả sau mitigation:
Rủi ro còn lại / người phụ trách:
~~~

Khi handoff, phân biệt rõ ba loại thông tin:

- **Fact:** quan sát trực tiếp, có timestamp và nguồn.
- **Hypothesis:** giải thích đang được kiểm tra.
- **Decision/action:** thao tác đã thực hiện hoặc quyết định được người có thẩm quyền xác nhận.

Không viết giả thuyết như thể đó là root cause. Nếu chưa đủ dữ liệu, ghi “chưa xác định” và nêu chính xác mẫu dữ liệu còn thiếu.

## 17. Quy trình triage theo thứ tự

1. **Mô tả triệu chứng:** viết bằng chỉ số, SQL error hoặc hành vi người dùng quan sát được.
2. **Chuẩn hóa timeline:** UTC, first seen, last known good, server uptime và thời điểm deploy.
3. **Xác định blast radius:** ứng dụng, tenant, schema, query, read/write, node và kết nối mới/cũ.
4. **Lập danh sách thay đổi:** deploy, DDL, config, traffic, backup, failover, hạ tầng.
5. **Bảo toàn bằng chứng:** log, status snapshots, processlist, digest, lock waits và replication.
6. **Phân loại triệu chứng:** connectivity, resource, query, locking, replication, correctness hoặc compatibility.
7. **Đặt giả thuyết có thể kiểm chứng:** nêu bằng chứng ủng hộ/phản bác và bước kiểm tra tiếp theo.
8. **Mitigate có kiểm soát:** ghi lại trạng thái trước/sau và tác động.
9. **Xác minh phục hồi:** latency, error rate, throughput, dữ liệu và replica state trở lại ngưỡng.
10. **Ghi root cause và phòng ngừa:** chỉ kết luận khi bằng chứng đủ; bổ sung alert, test hoặc runbook còn thiếu.

## 18. Ghi nhớ

- Bốn câu hỏi đầu tiên là thời điểm, phạm vi, thay đổi gần nhất và bằng chứng.
- Chuẩn hóa timestamp về UTC và xác định last known good.
- Phân biệt lỗi toàn hệ thống với lỗi một endpoint, tenant, node hoặc loại thao tác.
- Timeline deploy/migration/config giúp ưu tiên điều tra nhưng không tự chứng minh nguyên nhân.
- Bảo toàn error log, status delta, processlist, digest, lock wait và replication state trước khi thay đổi.
- Status counters là bộ đếm tích lũy; cần snapshot và delta, đồng thời kiểm tra Uptime.
- Performance Schema digest giúp tìm nhóm SQL đáng chú ý; APM cần thiết để đo p95/p99.
- Lock wait phải xác định cả requester và blocker; không kill session chỉ dựa trên thời gian chạy.
- Replication lag cần đối chiếu receiver, applier, GTID, relay log và worker error.
- Test giả thuyết từng bước, ghi rõ fact/hypothesis/action và xác minh sau mitigation.

Một cuộc điều tra MySQL tốt tạo ra chuỗi bằng chứng có thể bàn giao: triệu chứng định lượng, timeline chuẩn, phạm vi rõ, thay đổi liên quan và phép kiểm tra đã thực hiện. Khi mỗi hành động dựa trên bằng chứng và có kết quả đo sau đó, nhóm vận hành có thể khôi phục dịch vụ mà vẫn giữ được khả năng tìm nguyên nhân gốc.

## Tài liệu tham khảo

- [MySQL 8.0 Reference Manual: MySQL Server Logs](https://dev.mysql.com/doc/refman/8.0/en/server-logs.html)
- [MySQL 8.0 Reference Manual: The Slow Query Log](https://dev.mysql.com/doc/refman/8.0/en/slow-query-log.html)
- [MySQL 8.0 Reference Manual: SHOW PROCESSLIST](https://dev.mysql.com/doc/refman/8.0/en/show-processlist.html)
- [MySQL 8.0 Reference Manual: Performance Schema Statement Summary Tables](https://dev.mysql.com/doc/refman/8.0/en/performance-schema-statement-summary-tables.html)
- [MySQL 8.0 Reference Manual: InnoDB Standard Monitor and Lock Monitor](https://dev.mysql.com/doc/refman/8.0/en/innodb-standard-monitor.html)
- [MySQL 8.0 Reference Manual: InnoDB Locking](https://dev.mysql.com/doc/refman/8.0/en/innodb-locking.html)
- [MySQL 8.0 Reference Manual: Replication Monitoring](https://dev.mysql.com/doc/refman/8.0/en/replication-monitoring.html)

