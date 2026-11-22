# Nhật ký kết nối, lỗi, deadlock và checkpoint trong PostgreSQL

Giám sát PostgreSQL không chỉ là xem CPU, memory và số lượng connection. Khi ứng dụng chậm, không kết nối được hoặc transaction bị treo, server logs và các thống kê runtime là nguồn bằng chứng quan trọng để tìm nguyên nhân.

Bài học tập trung vào bốn nhóm thông tin vận hành:

- **Nhật ký kết nối** cho biết client nào kết nối, ngắt kết nối, dùng database/role nào và session tồn tại bao lâu.
- **Nhật ký lỗi** ghi lại câu lệnh thất bại, SQLSTATE, context và thời điểm xảy ra sự cố.
- **Deadlock và lock waits** giúp nhận diện transaction chặn nhau, thời gian chờ khóa và query gây ra tình trạng đó.
- **Checkpoint logs và statistics** cho biết PostgreSQL ghi dirty buffers xuống storage như thế nào, checkpoint xảy ra vì timeout hay áp lực WAL và có dấu hiệu I/O bottleneck hay không.

Log cần đủ chi tiết để điều tra nhưng cũng phải được kiểm soát về dung lượng, chi phí và dữ liệu nhạy cảm. Một cấu hình ghi mọi câu lệnh cùng mọi parameter có thể làm lộ thông tin và tăng I/O đáng kể. Ngược lại, log quá ít khiến đội vận hành không thể tái dựng sự cố.

~~~mermaid
flowchart TD
    A["PostgreSQL workload"] --> B["Logging configuration"]
    B --> C["Connection / session logs"]
    B --> D["Errors / SQLSTATE / statements"]
    B --> E["Lock waits / deadlocks"]
    B --> F["Checkpoint / WAL logs"]
    C --> G["Log collector / rotation"]
    D --> G
    E --> G
    F --> G
    G --> H["Central log store"]
    H --> I["Correlation and incident analysis"]
    J["pg_stat_activity / pg_locks"] --> I
    K["pg_stat_checkpointer / pg_stat_wal"] --> I
~~~

Bài học thuộc chương **Giám sát**, module **Database Engine Relational PostgreSQL**. Chúng ta sẽ tìm hiểu log destinations, logging collector, connection and error logging, log prefixes, lock diagnostics, deadlock detection, checkpoint behavior, WAL metrics, truy vấn thống kê và quy trình điều tra sự cố.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vai trò của PostgreSQL server logs trong giám sát và troubleshooting.
2. Phân biệt logging collector với log destination.
3. Cấu hình stderr, csvlog, jsonlog và syslog theo môi trường.
4. Thiết lập log directory, filename, rotation và retention.
5. Ghi nhận connection, disconnection và session duration.
6. Dùng log_line_prefix để liên kết log với session, user, database và application.
7. Chọn log_min_messages, log_min_error_statement và log_error_verbosity.
8. Kiểm soát việc ghi SQL statements và thời gian thực thi.
9. Nhận diện lỗi bằng SQLSTATE và context.
10. Phân biệt lock wait với deadlock.
11. Cấu hình deadlock_timeout và log_lock_waits.
12. Truy vấn pg_stat_activity, pg_locks và pg_blocking_pids.
13. Đọc deadlock report và xác định transaction gây xung đột.
14. Giải thích checkpoint, dirty buffers và WAL pressure.
15. Cấu hình log_checkpoints và các tham số checkpoint.
16. Theo dõi checkpoint statistics theo major version.
17. Kết hợp checkpoint, WAL và I/O metrics để tìm bottleneck.
18. Quản lý log volume, retention và dữ liệu nhạy cảm.
19. Xây dựng quy trình điều tra connection, error, deadlock và checkpoint.
20. Đề xuất thay đổi cấu hình dựa trên bằng chứng và kiểm thử.

## 2. PostgreSQL ghi log như thế nào?

PostgreSQL backend tạo các thông điệp log theo mức độ và loại sự kiện. Các thông điệp có thể được gửi tới standard error (stderr), sau đó được logging collector thu thập và ghi thành file, hoặc chuyển tới hệ thống log bên ngoài như syslog.

Luồng tổng quát:

~~~text
Client / SQL / Backend event
          |
          v
PostgreSQL backend
          |
          +-- severity, timestamp, SQLSTATE, context
          |
          v
log destination
          |
          +-- stderr
          +-- csvlog
          +-- jsonlog
          +-- syslog
          +-- eventlog (Windows)
          |
          v
logging collector / OS logging service
          |
          v
log files / central logging
~~~

### Logging collector là gì?

Tham số **logging_collector** bật tiến trình thu thập thông điệp được gửi tới stderr và ghi chúng vào các file log. Collector hỗ trợ quản lý file và rotation theo cấu hình PostgreSQL.

Ví dụ:

~~~conf
logging_collector = on
log_directory = 'log'
log_filename = 'postgresql-%Y-%m-%d_%H%M%S.log'
~~~

logging_collector cần restart server để thay đổi có hiệu lực. Không phải mọi logging setting đều cần restart; nhiều tham số log có thể reload.

### Logging collector không phải log destination

- **log_destination** chọn định dạng/đích log.
- **logging_collector** quyết định PostgreSQL có thu thập stderr vào file hay không.
- Syslog hoặc Windows Event Log là các cơ chế chuyển log tới hệ thống của hệ điều hành.
- Central logging là lớp tiếp nhận, lưu trữ, tìm kiếm và cảnh báo bên ngoài PostgreSQL.

## 3. Chọn log destination

Tham số:

~~~conf
log_destination = 'stderr'
~~~

Các destination phổ biến:

| Destination | Đặc điểm | Khi phù hợp |
| --- | --- | --- |
| stderr | Log dạng text tới standard error | Container, systemd, collector hoặc logging collector |
| csvlog | CSV có các trường riêng | Phân tích bằng công cụ xử lý bảng/log |
| jsonlog | JSON có cấu trúc | Central log pipeline và truy vấn theo field |
| syslog | Chuyển thông điệp tới syslog | Hệ thống Linux/Unix quản lý log tập trung |
| eventlog | Windows Event Log | Môi trường Windows |

Có thể kết hợp nhiều destination theo phiên bản và hệ điều hành, ví dụ:

~~~conf
log_destination = 'stderr,csvlog'
logging_collector = on
~~~

CSV/JSON file logging thông qua logging collector cần collector được bật. Đọc tài liệu đúng major version để biết destination nào được hỗ trợ và cách cấu hình.

### stderr

Text log đơn giản, dễ đọc bằng mắt và thường được dùng trong container. Khi PostgreSQL chạy dưới systemd, stderr có thể được systemd journal thu thập. Trong môi trường khác, service manager hoặc container runtime có thể xử lý stdout/stderr.

### csvlog

CSV log có các cột như timestamp, user, database, process ID, client address, session ID, SQLSTATE, message, detail, hint, query và context. Cấu trúc cột phụ thuộc PostgreSQL version.

Ưu điểm:

- Có field riêng, dễ import.
- Có thể lọc theo SQLSTATE, user, database.
- Hữu ích cho phân tích theo thời gian.

### jsonlog

JSON log cung cấp cấu trúc field cho pipeline hiện đại. Hệ thống log có thể parse JSON trực tiếp mà không cần tách chuỗi message bằng regex.

Ưu điểm:

- Dễ tìm kiếm theo key.
- Dễ liên kết timestamp, process, session và SQLSTATE.
- Phù hợp với OpenSearch, Elasticsearch, Loki hoặc các nền tảng log tương tự khi pipeline hỗ trợ.

### syslog

Khi dùng syslog, PostgreSQL gửi log tới syslog service. Cần cấu hình facility, identifier và mức severity theo môi trường.

~~~conf
log_destination = 'syslog'
syslog_facility = 'LOCAL0'
syslog_ident = 'postgres'
~~~

Không phải mọi hệ điều hành hoặc container runtime đều có syslog daemon. Kiểm tra luồng log end-to-end để tránh nghĩ PostgreSQL đã ghi log trong khi log collector không nhận được.

## 4. Cấu hình file log và rotation

Khi dùng logging collector, có thể cấu hình:

~~~conf
log_directory = 'log'
log_filename = 'postgresql-%Y-%m-%d_%H%M%S.log'
log_file_mode = 0600
log_rotation_age = '1d'
log_rotation_size = '100MB'
log_truncate_on_rotation = on
~~~

Ý nghĩa:

- **log_directory**: thư mục chứa log, tương đối với data directory hoặc đường dẫn tuyệt đối.
- **log_filename**: pattern tên file, hỗ trợ time-based placeholders.
- **log_file_mode**: permission mode cho file log trên hệ thống hỗ trợ.
- **log_rotation_age**: thời gian tối đa trước khi rotation.
- **log_rotation_size**: kích thước tối đa trước khi rotation.
- **log_truncate_on_rotation**: có truncate file cùng tên khi rotation theo thời gian và file đó đã tồn tại hay không.

### Rotation theo thời gian và kích thước

log_rotation_age và log_rotation_size có thể phối hợp. Khi file đạt điều kiện rotation, collector mở file tiếp theo theo tên được cấu hình.

Nếu log_filename chỉ chứa ngày và rotation theo kích thước xảy ra nhiều lần trong cùng ngày, cần cấu hình pattern/rotation cẩn thận để tránh ghi đè file ngoài ý muốn.

log_truncate_on_rotation chỉ ảnh hưởng khi mở file đã tồn tại trong trường hợp rotation theo thời gian; không phải cơ chế retention tổng quát.

### Rotation không phải retention

Rotation tạo file mới. Nó không tự xóa mọi file cũ sau một số ngày theo policy lưu trữ. Retention cần được quản lý bằng:

- Logrotate hoặc OS tooling.
- Central logging retention.
- Object storage lifecycle.
- Quy trình archive/delete có kiểm soát.

Không xóa file log đang được PostgreSQL sử dụng. Nếu dùng công cụ bên ngoài, tuân thủ cơ chế rotation/reopen được PostgreSQL và hệ điều hành hỗ trợ.

### current_logfiles và pg_current_logfile

Khi logging collector đang hoạt động, PostgreSQL có thể duy trì file current_logfiles để cho biết các log files hiện hành. Hàm pg_current_logfile() có thể trả về đường dẫn file log hiện tại cho destination tương ứng, tùy version và cấu hình.

~~~sql
SELECT pg_current_logfile();
~~~

Nếu cần destination cụ thể, kiểm tra signature của phiên bản server đang dùng.

## 5. Thời gian, timezone và log prefix

Thời gian là cơ sở để nối log PostgreSQL với application logs, proxy logs, operating system logs và distributed tracing.

Ví dụ:

~~~conf
log_timezone = 'UTC'
log_line_prefix = '%m [%p] %q%u@%d/%a %r '
~~~

Các placeholder thường dùng:

| Placeholder | Ý nghĩa |
| --- | --- |
| %m | Timestamp với milliseconds |
| %t | Timestamp không có milliseconds |
| %n | Timestamp Unix epoch |
| %p | Process ID |
| %u | User/role |
| %d | Database |
| %r | Remote host và port |
| %h | Remote host |
| %a | Application name |
| %c | Session ID |
| %l | Số thứ tự log line trong session |
| %e | SQLSTATE |
| %i | Command tag |
| %x | Transaction ID |
| %v | Virtual transaction ID |
| %s | Thời điểm bắt đầu session |
| %b | Backend type |

Các placeholder có thể thay đổi theo version; xem tài liệu runtime logging configuration.

### Ví dụ prefix dễ truy vết

~~~conf
log_line_prefix = '%m [%p] session=%c user=%u db=%d app=%a client=%r sqlstate=%e '
~~~

Một dòng log có thể cho biết:

- Thời điểm xảy ra.
- PID backend.
- Session ID.
- Role và database.
- Application name.
- Client address/port.
- SQLSTATE nếu có.

### Application name

Client có thể đặt application_name trong connection string:

~~~text
host=db.example.net dbname=appdb user=app_user application_name=orders-api
~~~

Khi đó log prefix %a và pg_stat_activity.application_name giúp phân biệt ứng dụng, worker, ETL hoặc công cụ quản trị.

Đừng để tất cả services dùng cùng một application_name chung chung nếu cần điều tra từng workload.

## 6. Ghi nhận connection và disconnection

Hai tham số:

~~~conf
log_connections = on
log_disconnections = on
~~~

log_connections ghi thông tin liên quan đến các lần kết nối, bao gồm các bước xác thực/ủy quyền và hoàn tất kết nối theo version. log_disconnections ghi thông tin khi session kết thúc, thường kèm thời gian tồn tại và số liệu session liên quan.

### Khi nào bật?

- Điều tra connection spikes.
- Theo dõi client không mong muốn.
- Phân tích kết nối bị từ chối.
- Xác định service mở quá nhiều session.
- Điều tra connection pool không tái sử dụng connection.
- Xác định session kéo dài hoặc disconnect bất thường.

### Chi phí

Trong môi trường có hàng chục nghìn kết nối ngắn mỗi phút, ghi cả connect và disconnect có thể tạo log volume lớn. Cần đo dung lượng và CPU, kết hợp connection pooling để giảm churn.

### log_hostname

log_hostname yêu cầu PostgreSQL phân giải hostname cho client address trong một số log. Reverse DNS lookup có thể tăng độ trễ xử lý kết nối nếu DNS chậm. Nếu không cần hostname, dùng địa chỉ IP và tra cứu trong inventory/network logs.

## 7. Theo dõi session bằng pg_stat_activity

pg_stat_activity cho biết trạng thái session hiện tại, không phải lịch sử kết nối đã đóng.

~~~sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    client_addr,
    client_port,
    backend_start,
    xact_start,
    query_start,
    state_change,
    state,
    wait_event_type,
    wait_event,
    left(query, 180) AS query_sample
FROM pg_stat_activity
ORDER BY backend_start;
~~~

Các trạng thái thường gặp:

- active: backend đang thực thi query.
- idle: session không có query đang chạy.
- idle in transaction: transaction đang mở nhưng session hiện không thực thi query.
- idle in transaction (aborted): transaction đã lỗi nhưng chưa được rollback/end.

### Đếm session theo database và trạng thái

~~~sql
SELECT
    datname,
    usename,
    application_name,
    state,
    count(*) AS sessions
FROM pg_stat_activity
GROUP BY datname, usename, application_name, state
ORDER BY sessions DESC;
~~~

### Vì sao idle in transaction đáng chú ý?

Transaction mở lâu có thể:

- Giữ locks.
- Giữ snapshot cũ.
- Ngăn vacuum thu hồi tuple versions.
- Làm tăng bloat.
- Chặn DDL hoặc transaction khác.
- Làm replication/maintenance khó tiến triển trong một số tình huống.

Tìm các transaction mở lâu:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    now() - xact_start AS transaction_age,
    state,
    wait_event_type,
    wait_event,
    left(query, 200) AS query_sample
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

pg_stat_activity có thể hiển thị query text nhạy cảm. Quyền xem đầy đủ thông tin session của user khác phụ thuộc quyền giám sát và role.

## 8. Ghi nhận lỗi SQL

Các tham số quan trọng:

~~~conf
log_min_messages = warning
log_min_error_statement = error
log_error_verbosity = default
~~~

### log_min_messages

Điều khiển mức severity tối thiểu được ghi vào server log. Các mức phổ biến:

| Mức | Ý nghĩa khái quát |
| --- | --- |
| DEBUG5 ... DEBUG1 | Thông tin debug, mức thấp hơn ghi nhiều chi tiết hơn |
| INFO | Thông tin |
| NOTICE | Thông báo |
| WARNING | Cảnh báo |
| ERROR | Lỗi câu lệnh/session |
| LOG | Thông điệp vận hành |
| FATAL | Lỗi khiến session kết thúc |
| PANIC | Lỗi nghiêm trọng khiến server shutdown/recovery |

Thứ tự severity và các mức hợp lệ cần đọc theo tài liệu PostgreSQL. Giá trị setting là ngưỡng: chọn mức thấp hơn trong thứ tự severity có thể ghi nhiều thông điệp hơn.

### log_min_error_statement

Điều khiển mức lỗi từ đó PostgreSQL ghi câu SQL liên quan. Ví dụ error ghi statement gây ra lỗi ERROR hoặc nghiêm trọng hơn. Câu lệnh có thể chứa literal hoặc parameter nhạy cảm, nên cần policy phù hợp.

### log_error_verbosity

- terse: giảm detail, hint và context.
- default: mức chi tiết mặc định.
- verbose: bổ sung thông tin như SQLSTATE và vị trí nguồn nội bộ theo khả năng version.

Verbose hữu ích trong debugging nhưng có thể làm log dài hơn.

## 9. SQLSTATE và phân loại lỗi

SQLSTATE là mã chuẩn năm ký tự giúp phân loại lỗi mà không phụ thuộc hoàn toàn vào message text.

Một số mã thường gặp:

| SQLSTATE | Tên | Ý nghĩa |
| --- | --- | --- |
| 23505 | unique_violation | Vi phạm unique constraint |
| 23503 | foreign_key_violation | Vi phạm foreign key |
| 40001 | serialization_failure | Transaction cần retry do serialization conflict |
| 40P01 | deadlock_detected | Phát hiện deadlock |
| 55P03 | lock_not_available | Không lấy được lock theo yêu cầu |
| 57014 | query_canceled | Query bị cancel/timeout theo ngữ cảnh |
| 53300 | too_many_connections | Hết connection slots thông thường |
| 57P01 | admin_shutdown | Server đang shutdown theo yêu cầu quản trị |

SQLSTATE class hai ký tự đầu giúp nhóm loại lỗi. Khi log prefix có %e, có thể lọc và thống kê lỗi theo mã.

Ví dụ lọc lỗi deadlock trong hệ thống log:

~~~text
sqlstate = "40P01"
~~~

Không nên chỉ alert theo message text vì message có thể được bản địa hóa hoặc thay đổi giữa các phiên bản.

## 10. Ghi log câu SQL và thời gian thực thi

Có nhiều mức ghi statement:

~~~conf
log_statement = 'none'
~~~

Các lựa chọn:

- none: không ghi statement theo setting này.
- ddl: ghi các câu DDL.
- mod: ghi DDL và các câu sửa dữ liệu như INSERT/UPDATE/DELETE.
- all: ghi mọi statement.

### Cẩn trọng với log_statement=all

Có thể làm log tăng rất nhanh và ghi dữ liệu nhạy cảm như email, token, PII hoặc nội dung nghiệp vụ. Không bật trên production trong thời gian dài nếu chưa có capacity và data-handling policy.

### log_duration

~~~conf
log_duration = on
~~~

Ghi thời gian thực thi statement theo cách cấu hình, nhưng không nhất thiết ghi query text nếu không có setting khác hỗ trợ.

### log_min_duration_statement

Ví dụ chỉ log statement chạy từ 1 giây:

~~~conf
log_min_duration_statement = '1s'
~~~

Các giá trị:

- -1: tắt threshold logging.
- 0: log mọi statement duration.
- Giá trị dương: log statement đạt/vượt thời lượng đó.

Đây là cách hữu ích để tìm query chậm mà không ghi mọi statement.

### Sampling

Một số PostgreSQL versions cung cấp các setting sampling cho statement logging. Kiểm tra tài liệu version trước khi sử dụng; sampling làm giảm log volume nhưng có thể bỏ qua một số lần query chậm hiếm gặp.

### log_statement và log_min_duration_statement có thể phối hợp

Một setting ghi theo loại statement, setting còn lại ghi theo thời lượng. Cần hiểu log duplication và volume khi kết hợp chúng.

## 11. Ghi parameter và dữ liệu nhạy cảm

Log SQL có thể chứa parameter values. Những giá trị này có thể gồm:

- Password hoặc token bị truyền sai cách.
- Email, số điện thoại, địa chỉ.
- Payment identifiers.
- Nội dung khách hàng.
- Dữ liệu nội bộ.
- Giá trị truy vấn từ ứng dụng.

Một số phiên bản có log_parameter_max_length và log_parameter_max_length_on_error để giới hạn parameter logging. Hành vi và default phụ thuộc version.

Nguyên tắc:

1. Không log secrets rõ nếu không có nhu cầu hợp lệ.
2. Giới hạn người đọc log.
3. Mã hóa log khi truyền và khi lưu.
4. Đặt retention theo chính sách.
5. Xử lý log như dữ liệu có thể chứa PII.
6. Dùng query fingerprint/normalized query khi cần phân tích workload thay vì lưu mọi literal.

## 12. Log query chậm và truy vấn theo thời gian

Một cấu hình thực tế có thể bắt đầu bằng:

~~~conf
log_min_duration_statement = '500ms'
log_line_prefix = '%m [%p] session=%c user=%u db=%d app=%a client=%r sqlstate=%e '
log_error_verbosity = default
~~~

Ngưỡng 500ms chỉ là ví dụ. Một API có SLA 50ms có thể cần threshold thấp hơn; một batch job vài phút có thể cần ngưỡng cao hơn.

Phân tích log query chậm theo:

- Query fingerprint.
- Database/user/application.
- Thời gian thực thi.
- Số lần xuất hiện.
- Thời điểm cao điểm.
- Lock wait.
- Buffer/cache behavior.
- Kế hoạch thực thi bằng EXPLAIN (ANALYZE, BUFFERS) trong môi trường phù hợp.

Log duration không cho biết toàn bộ nguyên nhân. Query chậm có thể do CPU, I/O, lock, network, plan regression hoặc resource contention.

## 13. Log context và vị trí lỗi

Các thông điệp ERROR có thể kèm:

- SQLSTATE.
- DETAIL.
- HINT.
- CONTEXT.
- STATEMENT.
- PL/pgSQL function/line context.
- Process/session metadata.

Ví dụ minh họa:

~~~text
ERROR:  duplicate key value violates unique constraint "orders_pkey"
DETAIL:  Key (order_id)=(42) already exists.
STATEMENT: INSERT INTO orders(order_id) VALUES (42);
~~~

Trong production, query text có thể bị cắt hoặc parameter bị ẩn theo policy. Khi điều tra, ghép session ID, PID, timestamp, application_name và SQLSTATE để tìm các dòng liên quan.

## 14. Deadlock là gì?

Deadlock xảy ra khi hai hoặc nhiều transaction chờ tài nguyên do transaction khác giữ, tạo thành một vòng chờ không thể tự tiến triển.

Ví dụ:

- Transaction A khóa row 1, sau đó chờ row 2.
- Transaction B khóa row 2, sau đó chờ row 1.
- A chờ B và B chờ A.
- Không transaction nào có thể tiếp tục.

PostgreSQL phát hiện cycle trong wait-for graph và hủy một transaction để phá deadlock. Transaction bị hủy nhận lỗi SQLSTATE 40P01.

~~~mermaid
flowchart LR
    A["Transaction A"] -->|"đang giữ lock row 1"| R1["Row 1"]
    B["Transaction B"] -->|"đang giữ lock row 2"| R2["Row 2"]
    A -->|"đang chờ row 2"| R2
    B -->|"đang chờ row 1"| R1
    A -. "waits for B" .-> B
    B -. "waits for A" .-> A
~~~

### Deadlock khác lock wait

Lock wait đơn giản có thể chỉ là một transaction đang chờ transaction khác commit/rollback. Deadlock là một chu trình chờ.

- Lock wait có thể tự kết thúc khi blocker commit.
- Deadlock cần PostgreSQL hủy một transaction để phá cycle.
- Một lock wait dài không tự động có nghĩa deadlock.

## 15. Tái hiện deadlock

Tạo bảng thử nghiệm:

~~~sql
CREATE TABLE account_demo (
    account_id integer PRIMARY KEY,
    balance numeric(12,2) NOT NULL
);

INSERT INTO account_demo VALUES
    (1, 1000),
    (2, 1000);
~~~

Session A:

~~~sql
BEGIN;
UPDATE account_demo SET balance = balance - 10 WHERE account_id = 1;
-- Chờ một chút trước khi chạy câu tiếp theo.
UPDATE account_demo SET balance = balance + 10 WHERE account_id = 2;
COMMIT;
~~~

Session B, chạy xen kẽ sau câu UPDATE đầu tiên của A:

~~~sql
BEGIN;
UPDATE account_demo SET balance = balance - 20 WHERE account_id = 2;
UPDATE account_demo SET balance = balance + 20 WHERE account_id = 1;
COMMIT;
~~~

Nếu A và B giữ hai row theo thứ tự ngược nhau, một transaction có thể bị PostgreSQL hủy với deadlock detected.

Thực hiện ví dụ trong database thử nghiệm và điều phối thời điểm chạy để tạo interleaving. Không cố ý tạo deadlock trên bảng production.

## 16. deadlock_timeout

Tham số:

~~~conf
deadlock_timeout = '1s'
~~~

deadlock_timeout xác định thời gian PostgreSQL chờ trước khi kiểm tra deadlock trên một lock wait. Nó không phải thời gian tối đa một transaction được phép chờ lock.

Khi lock wait kéo dài qua ngưỡng, PostgreSQL thực hiện kiểm tra deadlock. Kiểm tra này có chi phí; không nên đặt quá thấp trên workload có nhiều lock contention mà không benchmark.

### deadlock_timeout không phải lock_timeout

- deadlock_timeout: thời điểm bắt đầu kiểm tra deadlock.
- lock_timeout: giới hạn thời gian một statement chờ lock trước khi bị hủy.
- statement_timeout: giới hạn thời gian thực thi statement.
- idle_in_transaction_session_timeout: giới hạn thời gian session idle trong transaction.

Ví dụ:

~~~conf
deadlock_timeout = '1s'
lock_timeout = '5s'
statement_timeout = '30s'
idle_in_transaction_session_timeout = '60s'
~~~

Các giá trị chỉ minh họa. Nếu lock_timeout ngắn hơn deadlock_timeout, statement có thể bị hủy vì lock timeout trước khi deadlock detector thực hiện lần kiểm tra theo lịch đó.

## 17. Bật log_lock_waits

Ví dụ:

~~~conf
log_lock_waits = on
deadlock_timeout = '1s'
~~~

log_lock_waits yêu cầu PostgreSQL ghi log khi session chờ lock lâu hơn deadlock_timeout.

Điều này giúp tìm các lock waits kéo dài ngay cả khi không xảy ra deadlock.

### Cần đọc log như thế nào?

Thông điệp lock wait thường cho biết:

- Process nào đang chờ.
- Loại lock/mode đang chờ.
- Relation/object liên quan nếu có.
- Transaction hoặc process đang giữ lock theo context có sẵn.
- Thời lượng wait.

Đối chiếu PID với pg_stat_activity và pg_locks tại thời điểm sự cố. Vì session có thể kết thúc trước khi operator chạy query điều tra, log là bằng chứng lịch sử rất quan trọng.

## 18. Tìm session đang chờ lock

Query đơn giản:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    query_start,
    left(query, 200) AS query_sample
FROM pg_stat_activity
WHERE wait_event_type = 'Lock'
ORDER BY query_start;
~~~

Nếu có dòng kết quả, backend đang chờ một lock. Cần tìm blocker.

### Dùng pg_blocking_pids

~~~sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.usename AS blocked_user,
    blocked.application_name AS blocked_app,
    now() - blocked.query_start AS wait_duration,
    left(blocked.query, 160) AS blocked_query,
    blocker.pid AS blocker_pid,
    blocker.usename AS blocker_user,
    blocker.application_name AS blocker_app,
    blocker.state AS blocker_state,
    now() - blocker.xact_start AS blocker_xact_age,
    left(blocker.query, 160) AS blocker_query
FROM pg_stat_activity AS blocked
JOIN LATERAL unnest(pg_blocking_pids(blocked.pid)) AS p(blocker_pid)
    ON true
JOIN pg_stat_activity AS blocker
    ON blocker.pid = p.blocker_pid
WHERE blocked.wait_event_type = 'Lock'
ORDER BY blocked.query_start;
~~~

pg_blocking_pids(pid) trả về các PID đang chặn process được chỉ định. Có thể có nhiều blocker.

### Tại sao blocker có thể ở trạng thái idle?

Một session có thể đã chạy UPDATE rồi chuyển sang idle nhưng transaction vẫn mở và giữ lock. Khi đó query hiện tại có thể là COMMIT, ROLLBACK hoặc rỗng/không phản ánh câu lệnh đã lấy lock. Xem xact_start, application name và log trước đó.

## 19. Kiểm tra pg_locks

pg_locks hiển thị các locks đang được giữ hoặc chờ.

~~~sql
SELECT
    l.pid,
    a.usename,
    a.application_name,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::regclass AS relation_name,
    l.page,
    l.tuple,
    l.transactionid,
    a.state,
    a.wait_event_type,
    a.wait_event,
    left(a.query, 160) AS query_sample
FROM pg_locks AS l
LEFT JOIN pg_stat_activity AS a
    ON a.pid = l.pid
ORDER BY l.granted, l.pid;
~~~

Các cột:

- locktype: loại đối tượng khóa.
- mode: lock mode.
- granted: lock đã được cấp hay đang chờ.
- relation: relation OID khi lock liên quan relation.
- transactionid: transaction ID khi lock liên quan transaction.

Không phải mọi lock đều có relation. Một số lock nội bộ hoặc advisory locks có cấu trúc khác.

### Lock modes

PostgreSQL có nhiều lock modes. Với table locks, ví dụ AccessShareLock, RowShareLock, RowExclusiveLock, ShareLock, ShareRowExclusiveLock, ExclusiveLock, AccessExclusiveLock. Các mode có ma trận xung đột khác nhau.

Không kết luận hai mode xung đột chỉ dựa trên tên. Tham khảo lock compatibility matrix trong tài liệu PostgreSQL.

## 20. Đọc deadlock report

Một deadlock report thường có dạng minh họa:

~~~text
ERROR:  deadlock detected
DETAIL: Process 12345 waits for ShareLock on transaction 67890;
        blocked by process 12346.
        Process 12346 waits for ShareLock on transaction 67891;
        blocked by process 12345.
HINT:  See server log for query details.
CONTEXT: while updating tuple (...) in relation "account_demo"
~~~

Các thành phần:

- PID của các process liên quan.
- Lock mode đang chờ.
- Transaction ID hoặc object bị chặn.
- PID blocker.
- Query/context nếu PostgreSQL có thể cung cấp.
- HINT chỉ dẫn xem log liên quan.

### Phân tích

1. Tìm các PID trong log prefix.
2. Tìm các statement trước thời điểm deadlock.
3. Xác định thứ tự lock object của mỗi transaction.
4. Xác định transaction nào bị PostgreSQL hủy.
5. Tìm các transaction còn lại đã commit/rollback chưa.
6. Sửa thứ tự truy cập hoặc rút ngắn transaction.
7. Kiểm tra retry behavior ở ứng dụng.

## 21. Giảm deadlock

### Truy cập tài nguyên theo thứ tự thống nhất

Nếu nhiều transaction cập nhật account A và B, hãy truy cập theo thứ tự account ID tăng dần ở mọi code path.

Ví dụ:

~~~sql
BEGIN;
SELECT account_id
FROM account_demo
WHERE account_id IN (1, 2)
ORDER BY account_id
FOR UPDATE;
-- Thực hiện updates theo cùng thứ tự.
COMMIT;
~~~

Việc khóa trước theo thứ tự thống nhất có thể giảm khả năng tạo cycle, nhưng vẫn cần xem các locks khác và code path thực tế.

### Giữ transaction ngắn

- Không gọi API bên ngoài trong khi transaction đang giữ lock.
- Không chờ người dùng thao tác giữa transaction.
- Commit/rollback sớm.
- Không để idle-in-transaction kéo dài.
- Chỉ khóa rows cần thiết.

### Index phù hợp

UPDATE/DELETE hoặc SELECT FOR UPDATE quét nhiều rows có thể giữ nhiều locks hơn cần thiết. Index phù hợp giúp giảm phạm vi scan và thời gian giữ lock, dù index không tự loại bỏ mọi deadlock.

### Retry deadlock ở ứng dụng

PostgreSQL hủy một transaction khi phát hiện deadlock. Ứng dụng có thể retry transaction đó nếu thao tác có thể thực hiện lại an toàn.

- Chỉ retry SQLSTATE 40P01 theo policy.
- Retry toàn transaction từ đầu, không tiếp tục giữa transaction đã bị abort.
- Dùng bounded retries, exponential backoff và jitter.
- Bảo đảm thao tác idempotent hoặc có idempotency key.
- Ghi nhận retry count để phát hiện deadlock tăng cao.

Không retry vô hạn vì có thể biến deadlock thành retry storm.

## 22. Checkpoint là gì?

Checkpoint là quá trình PostgreSQL đảm bảo các dirty data pages trong shared buffers đã được ghi xuống data files và ghi checkpoint record vào WAL. Checkpoint tạo một điểm tham chiếu cho crash recovery, giúp PostgreSQL không phải replay WAL vô hạn từ đầu lịch sử.

Checkpoint có thể được kích hoạt bởi:

- Thời gian kể từ checkpoint trước đạt checkpoint_timeout.
- WAL usage đạt ngưỡng liên quan max_wal_size.
- Administrator gọi lệnh CHECKPOINT.
- Các điều kiện vận hành/backup/recovery khác theo version.

### Dirty buffers

Một data page được sửa trong memory trở thành dirty buffer. PostgreSQL có thể ghi dirty pages trong background hoặc trong checkpoint. Checkpoint đảm bảo một tập dữ liệu cần thiết được flush theo quy tắc durability.

### Checkpoint không phải backup

Checkpoint giúp crash recovery. Nó không tạo bản backup độc lập và không thay thế base backup/WAL archive.

## 23. Checkpoint và WAL

Mỗi transaction thay đổi dữ liệu tạo WAL records. PostgreSQL dùng WAL để bảo đảm có thể redo changes sau crash.

Khi checkpoint xảy ra:

1. PostgreSQL xác định checkpoint position.
2. Dirty buffers được ghi xuống data files theo lịch.
3. WAL flush được điều phối.
4. Checkpoint record được ghi vào WAL.
5. Recovery có thể bắt đầu từ checkpoint phù hợp.

WAL segments cũ chỉ được recycle/remove khi không còn cần cho crash recovery, replication slots, WAL archiving, backup hoặc các consumer khác.

### max_wal_size không phải hard cap

max_wal_size là ngưỡng mềm để kiểm soát checkpoint frequency. WAL có thể vượt mức này khi workload, replication slots, archiving hoặc các điều kiện khác giữ WAL lại.

Không dựa vào max_wal_size như một quota cứng cho filesystem.

## 24. Bật log_checkpoints

Cấu hình:

~~~conf
log_checkpoints = on
~~~

Khi bật, PostgreSQL ghi thông tin về checkpoint và restartpoint vào server log. Log có thể gồm:

- Lý do checkpoint.
- Số buffers được ghi.
- Thời gian write.
- Thời gian sync.
- Số file được xử lý hoặc thông tin WAL liên quan.
- Thông tin restartpoint trên standby.

Chi tiết message thay đổi theo major version. Dùng log để xác định checkpoint xảy ra do timeout hay WAL pressure và thời gian thực hiện từng phase.

### Ví dụ log minh họa

~~~text
LOG: checkpoint starting: time
LOG: checkpoint complete: wrote 12000 buffers (...);
     write=... s, sync=... s, total=... s;
     distance=... kB, estimate=... kB
~~~

Đây chỉ là ví dụ minh họa, không phải format cố định. Hãy đọc log thực tế theo version.

### Checkpoint và restartpoint

Primary thực hiện checkpoint. Standby trong recovery có thể thực hiện restartpoints, giúp giới hạn lượng WAL cần replay nếu standby crash. Log và statistics có thể phân biệt checkpoint với restartpoint.

## 25. Theo dõi checkpoint statistics theo version

PostgreSQL đã thay đổi cách tổ chức các statistics views.

### PostgreSQL 17 trở lên

Checkpoint statistics nằm trong pg_stat_checkpointer.

~~~sql
SELECT *
FROM pg_stat_checkpointer;
~~~

View cung cấp số lượng checkpoint theo thời gian/yêu cầu, buffers written và thời gian write/sync cùng thông tin thống kê khác theo version.

### PostgreSQL 16 trở xuống

Checkpoint statistics nằm trong pg_stat_bgwriter.

~~~sql
SELECT *
FROM pg_stat_bgwriter;
~~~

Ở các version này, view có các trường như checkpoints_timed, checkpoints_req, checkpoint_write_time, checkpoint_sync_time, buffers_checkpoint và các số liệu background writer.

Từ PostgreSQL 17, checkpoint-related statistics được tách sang pg_stat_checkpointer; không copy nguyên query cột của PostgreSQL 16 vào server 17+ mà không kiểm tra schema view.

### Kiểm tra server version

~~~sql
SHOW server_version;
SHOW server_version_num;
~~~

Khi xây dựng monitoring dashboard, nên có query/metric mapping riêng theo major version.

## 26. Đọc checkpoint metrics

Các metric thường được quan tâm:

- Số checkpoint theo timeout.
- Số checkpoint được yêu cầu do WAL pressure.
- Số buffers được ghi bởi checkpointer.
- Thời gian write.
- Thời gian sync.
- Tổng thời gian checkpoint.
- Khoảng cách WAL giữa các checkpoint.
- Checkpoint/restartpoint đang diễn ra.

### Timed và requested checkpoints

- Timed checkpoint xảy ra theo checkpoint_timeout.
- Requested checkpoint có thể xảy ra khi WAL vượt ngưỡng hoặc có yêu cầu khác.

Nếu requested checkpoints tăng liên tục, có thể max_wal_size quá nhỏ so với WAL generation rate, hoặc workload tạo WAL cao. Cần xem log và disk/replication conditions trước khi tăng tham số.

### Checkpoint write time và sync time

Write time phản ánh thời gian ghi pages theo checkpoint metrics. Sync time phản ánh thời gian đồng bộ file xuống storage theo cơ chế PostgreSQL. Hai số liệu này có thể giúp nhận diện storage latency, nhưng cần đọc cùng OS I/O metrics.

Không cộng hoặc so sánh các counters như thể chúng là latency của một transaction đơn lẻ; đây là thống kê tích lũy từ nhiều checkpoint.

## 27. Điều chỉnh checkpoint

Các tham số thường gặp:

~~~conf
checkpoint_timeout = '15min'
max_wal_size = '4GB'
min_wal_size = '1GB'
checkpoint_completion_target = 0.9
log_checkpoints = on
~~~

Các con số chỉ là ví dụ, không phải cấu hình khuyến nghị chung.

### checkpoint_timeout

Thời gian tối đa giữa các checkpoint theo cơ chế timeout. Tăng timeout có thể giảm tần suất checkpoint do thời gian, nhưng crash recovery có thể cần replay WAL dài hơn.

### max_wal_size

Ngưỡng WAL để PostgreSQL quyết định cần checkpoint sớm hơn. Tăng giá trị có thể giảm requested checkpoints trong workload WAL-intensive, nhưng tăng nhu cầu disk/WAL retention và cần tính đến replication/archive.

### min_wal_size

Lượng WAL PostgreSQL cố gắng giữ lại để tái sử dụng theo cơ chế quản lý WAL. Giá trị phù hợp có thể giảm việc tạo/xóa segment liên tục.

### checkpoint_completion_target

Mục tiêu trải đều công việc ghi checkpoint trong khoảng thời gian giữa các checkpoint. Giá trị cao giúp phân tán I/O, giảm burst, nhưng cần theo dõi checkpoint duration và storage throughput.

### Không tắt durability để tăng tốc

Không tắt fsync hoặc full_page_writes trong production chỉ để giảm I/O checkpoint. Những setting này liên quan trực tiếp tới durability và khả năng phục hồi sau crash. Mọi thay đổi phải dựa trên hiểu biết rõ về rủi ro và policy.

## 28. Checkpoint và full-page writes

Sau checkpoint, lần đầu một page được sửa trong một số điều kiện PostgreSQL có thể ghi full-page image vào WAL khi full_page_writes bật. Cơ chế này giúp bảo vệ khỏi torn page khi crash.

Điều này có nghĩa:

- Checkpoint thường xuyên có thể làm tăng lượng full-page images trong WAL.
- WAL volume có thể tăng sau checkpoint khi workload ghi nhiều page khác nhau.
- wal_compression có thể giảm kích thước full-page images trong một số workload, nhưng tiêu tốn CPU.
- Không tắt full_page_writes chỉ để giảm WAL nếu không có storage guarantees phù hợp.

Khi thấy WAL volume tăng sau checkpoint, xem pg_stat_wal, workload và full-page image counts trước khi kết luận.

## 29. Theo dõi WAL statistics

View pg_stat_wal cung cấp thống kê WAL trên các PostgreSQL versions hiện đại.

~~~sql
SELECT *
FROM pg_stat_wal;
~~~

Các trường có thể gồm:

- wal_records: số WAL records.
- wal_fpi: số full-page images.
- wal_bytes: lượng WAL được tạo.
- wal_buffers_full: số lần WAL buffers đầy theo thống kê.
- wal_write: số lần ghi WAL.
- wal_sync: số lần sync WAL.
- wal_write_time: thời gian ghi WAL khi timing được bật.
- wal_sync_time: thời gian sync WAL khi timing được bật.
- stats_reset: thời điểm reset statistics.

Các cột phụ thuộc version. track_wal_io_timing cần bật để có timing fields hữu ích theo cấu hình/version.

### Đo WAL generation rate

Counters là tích lũy. Có thể lấy hai mẫu cách nhau một khoảng thời gian rồi tính delta:

\[
WAL\ rate = \frac{wal\_bytes_{t2} - wal\_bytes_{t1}}{t2 - t1}
\]

Đây là cách ước lượng tốc độ tạo WAL trung bình trong khoảng lấy mẫu. Lưu ý statistics reset, server restart và counter reset khi tính delta.

## 30. Theo dõi I/O

track_io_timing bật việc thu thập thời gian I/O trong các statistics liên quan.

~~~conf
track_io_timing = on
track_wal_io_timing = on
~~~

Khả năng và chi phí phụ thuộc version/hardware. Bật timing có thể tạo overhead nhỏ do đo thời gian; benchmark trên workload thực tế.

### pg_stat_io

PostgreSQL 16 trở lên cung cấp pg_stat_io để xem thống kê I/O theo backend/object/context.

~~~sql
SELECT *
FROM pg_stat_io
ORDER BY backend_type, object, context;
~~~

View này giúp phân tích read/write/extend/fsync và timing theo loại hoạt động. Không phải mọi cột đều tồn tại ở mọi major version; dùng schema view của server hiện tại.

### Kết hợp OS metrics

PostgreSQL metrics cần kết hợp với:

- Disk utilization và queue depth.
- Read/write throughput.
- Latency p95/p99.
- Filesystem free space.
- WAL volume.
- CPU iowait.
- Storage service metrics.
- Cloud volume burst credits nếu có.

Checkpoint logs cho biết hoạt động phía PostgreSQL; OS metrics cho biết storage thực tế có bị bão hòa hay không.

## 31. Phân biệt checkpoint pressure và WAL retention

WAL directory lớn không nhất thiết có nghĩa checkpoint chậm.

Các nguyên nhân khác:

- Replication slot giữ WAL.
- WAL archiving bị lỗi.
- Standby lag.
- Backup process cần WAL.
- Logical decoding consumer không tiến.
- max_wal_size được cấu hình cao.
- Workload tạo WAL đột biến.

Kiểm tra slots:

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    wal_status
FROM pg_replication_slots
ORDER BY slot_type, slot_name;
~~~

Kiểm tra archiver:

~~~sql
SELECT *
FROM pg_stat_archiver;
~~~

Các view/columns phụ thuộc version. Nếu archive failure tăng, WAL có thể tích tụ dù checkpoint vẫn hoạt động bình thường.

## 32. Điều tra connection spike

Khi số connection tăng đột biến:

1. Xem session count theo database, role, application.
2. Xem connection logs quanh thời điểm spike.
3. Xác định client IP, application_name và session start time.
4. Phân biệt pool connections với kết nối ngắn liên tục.
5. Kiểm tra idle-in-transaction.
6. Xem max_connections và reserved connection slots.
7. Kiểm tra lỗi authentication hoặc retry storm.
8. Đánh giá connection pool sizing và timeout.

Query đếm:

~~~sql
SELECT
    datname,
    usename,
    application_name,
    client_addr,
    state,
    count(*) AS sessions
FROM pg_stat_activity
GROUP BY datname, usename, application_name, client_addr, state
ORDER BY sessions DESC;
~~~

Không tăng max_connections ngay khi gặp too_many_connections. Mỗi connection có resource overhead; tăng giới hạn mà không tính memory/CPU có thể làm server kém ổn định hơn. Kiểm tra pooling và connection leaks trước.

## 33. Điều tra lỗi SQL tăng cao

Quy trình:

1. Lọc log theo severity và SQLSTATE.
2. Nhóm theo database/user/application.
3. Tìm statement/context liên quan.
4. So sánh thời điểm deploy hoặc config change.
5. Kiểm tra constraint/schema changes.
6. Xác định lỗi do client input, concurrency, timeout hay server resource.
7. Đo tỷ lệ lỗi trước/sau thay đổi.
8. Sửa nguyên nhân và theo dõi lại.

Một số mã hữu ích:

- 23505: duplicate key.
- 23503: foreign key violation.
- 40001: serialization failure.
- 40P01: deadlock.
- 55P03: lock unavailable.
- 57014: query canceled.
- 53300: too many connections.

Không gộp mọi ERROR thành một alert duy nhất. Các mã lỗi cần action khác nhau; ví dụ 40001 có thể retry, còn 23503 thường cần sửa logic/dữ liệu.

## 34. Điều tra deadlock trong production

Khi log có SQLSTATE 40P01:

1. Ghi nhận timestamp, PID, session ID và application_name.
2. Tìm toàn bộ deadlock report cùng thời điểm.
3. Xác định các relation/transaction ID và lock modes.
4. Tìm query của các PID trong log.
5. Xác định thứ tự truy cập resource.
6. Kiểm tra transaction duration và idle-in-transaction.
7. Tái hiện trong staging với cùng thứ tự thao tác.
8. Sửa code/lock order/index hoặc transaction boundaries.
9. Thêm retry có giới hạn.
10. Theo dõi deadlock rate sau deploy.

Không chỉ tăng deadlock_timeout để làm biến mất log. Điều đó có thể trì hoãn detection và không giải quyết cycle.

## 35. Điều tra checkpoint quá thường xuyên

Dấu hiệu:

- Checkpoint log xuất hiện dày đặc.
- Nhiều checkpoint reason là requested.
- WAL generation rate cao.
- Disk write burst.
- Latency query tăng quanh checkpoint.
- pg_stat_checkpointer/pg_stat_bgwriter counters tăng nhanh.

Các bước:

1. Xác định checkpoint timed hay requested.
2. Đo WAL bytes/second.
3. Xem max_wal_size, checkpoint_timeout, checkpoint_completion_target.
4. Kiểm tra replication slots và archiver.
5. Đối chiếu disk throughput/latency.
6. Xem số buffers ghi và checkpoint duration.
7. Thử thay đổi một tham số trong staging.
8. So sánh WAL, I/O và latency trước/sau.

Nếu requested checkpoints tăng do WAL volume cao, tăng max_wal_size có thể giúp giảm tần suất, nhưng cần dung lượng disk và retention headroom. Nếu storage đã bão hòa, chỉ tăng size có thể kéo dài burst hoặc trì hoãn vấn đề.

## 36. Log rotation và log retention trong production

Một chính sách vận hành cần định nghĩa:

- File naming và timestamp timezone.
- Rotation theo thời gian/kích thước.
- Retention theo ngày hoặc dung lượng.
- Compression.
- Upload tới central logging.
- Access control.
- Encryption at rest/in transit.
- Backup và audit.
- Cách xử lý khi disk log đầy.
- Cách bảo đảm log không bị mất khi collector/restart.

### Disk riêng cho logs

Tách log storage khỏi data/WAL storage có thể giảm nguy cơ log volume làm đầy filesystem chứa database. Tuy nhiên, cần bảo đảm logging collector vẫn ghi được khi disk riêng đầy và có alert cho tình trạng này.

### Log pipeline bị chậm

Nếu central collector ngừng nhận, local logs có thể tích tụ. Cần giới hạn queue/buffer và có policy fallback. Không để một pipeline log lỗi làm PostgreSQL mất khả năng ghi log hoặc làm đầy disk mà không có cảnh báo.

## 37. Những tham số logging cần biết

Bảng sau là nhóm setting thường gặp. Context/reloadability có thể thay đổi theo version và một số setting cần restart.

| Tham số | Mục đích |
| --- | --- |
| logging_collector | Thu thập stderr vào file |
| log_destination | Chọn stderr/csvlog/jsonlog/syslog/eventlog |
| log_directory | Thư mục log |
| log_filename | Pattern tên file |
| log_rotation_age | Rotation theo thời gian |
| log_rotation_size | Rotation theo kích thước |
| log_truncate_on_rotation | Truncate file cùng tên trong trường hợp rotation theo thời gian |
| log_line_prefix | Metadata prefix mỗi dòng |
| log_timezone | Timezone của log timestamp |
| log_connections | Ghi thông tin kết nối |
| log_disconnections | Ghi thông tin ngắt kết nối |
| log_min_messages | Severity tối thiểu |
| log_min_error_statement | Ngưỡng ghi SQL gây lỗi |
| log_error_verbosity | Mức detail của error |
| log_statement | Ghi DDL/mod/all |
| log_duration | Ghi duration |
| log_min_duration_statement | Ngưỡng duration để log statement |
| log_lock_waits | Ghi lock waits dài |
| deadlock_timeout | Thời gian trước khi kiểm tra deadlock |
| log_checkpoints | Ghi checkpoint/restartpoint |
| log_temp_files | Ghi temporary files theo ngưỡng |
| log_autovacuum_min_duration | Ghi autovacuum duration theo ngưỡng |

Không bật tất cả setting ở mức chi tiết cao mà không đo log volume và overhead.

## 38. Kiểm tra cấu hình hiệu lực

Dùng pg_settings để xem giá trị, nguồn và context:

~~~sql
SELECT
    name,
    setting,
    unit,
    source,
    context,
    pending_restart
FROM pg_settings
WHERE name LIKE 'log_%'
   OR name IN (
       'logging_collector',
       'deadlock_timeout',
       'checkpoint_timeout',
       'checkpoint_completion_target',
       'max_wal_size',
       'min_wal_size',
       'track_io_timing',
       'track_wal_io_timing'
   )
ORDER BY name;
~~~

Các cột hữu ích:

- setting: giá trị hiện tại.
- source: nguồn cấu hình.
- context: loại context, giúp biết thay đổi cần restart/reload hay có thể set runtime.
- pending_restart: có thay đổi đang chờ restart hay không.

Xem một setting:

~~~sql
SHOW log_line_prefix;
SHOW log_connections;
SHOW log_lock_waits;
SHOW log_checkpoints;
~~~

### Reload cấu hình

Với setting hỗ trợ reload:

~~~sql
SELECT pg_reload_conf();
~~~

logging_collector cần restart khi bật/tắt. Hãy kiểm tra context và pending_restart thay vì giả định reload đã áp dụng mọi thay đổi.

## 39. Ví dụ cấu hình logging thực tế

Một cấu hình khởi đầu có thể là:

~~~conf
# Log destination and collection
logging_collector = on
log_destination = 'stderr,csvlog'
log_directory = 'log'
log_filename = 'postgresql-%Y-%m-%d_%H%M%S.log'
log_rotation_age = '1d'
log_rotation_size = '100MB'
log_truncate_on_rotation = on

# Session context
log_timezone = 'UTC'
log_line_prefix = '%m [%p] session=%c user=%u db=%d app=%a client=%r sqlstate=%e '

# Connections and errors
log_connections = on
log_disconnections = on
log_min_messages = warning
log_min_error_statement = error
log_error_verbosity = default

# Slow statements and lock waits
log_min_duration_statement = '1s'
log_lock_waits = on
deadlock_timeout = '1s'

# Checkpoints
log_checkpoints = on
~~~

Đây là ví dụ để thảo luận, không phải cấu hình tối ưu chung. Hãy cân nhắc volume kết nối, mức nhạy cảm của query parameters, log retention, storage capacity và yêu cầu bảo mật.

## 40. Kết hợp logs với monitoring dashboard

Một dashboard vận hành nên có các nhóm:

### Connections

- Current sessions.
- Connections theo database/user/application.
- Connection failures.
- Connection/disconnection rate.
- Idle-in-transaction count.
- Số session gần max_connections.

### Errors

- Error count theo SQLSTATE.
- Error rate theo application.
- FATAL/PANIC events.
- Authentication failures.
- Query cancellations/timeouts.
- Top error messages/fingerprints.

### Locks

- Current lock waits.
- Longest wait duration.
- Blocking PID count.
- Deadlocks per time window.
- Long-running transactions.
- Idle-in-transaction sessions.

### Checkpoints/WAL

- Timed/requested checkpoint count.
- Checkpoint write/sync time.
- Buffers written.
- WAL bytes per second.
- WAL archive failures.
- Replication slot retention.
- Disk free space and I/O latency.

Đặt alert theo trend và ngưỡng SLO. Ví dụ, một deadlock đơn lẻ có thể được ứng dụng retry thành công; deadlock rate tăng liên tục là tín hiệu cần điều tra.

## 41. Correlation giữa PostgreSQL log và application log

Để nối log hai phía, nên thống nhất:

- UTC hoặc timezone policy.
- Request ID/correlation ID.
- Application name.
- Database user/service account.
- Client address.
- Session ID/PID.
- Timestamp có milliseconds.

PostgreSQL không tự nhận mọi application trace ID. Ứng dụng có thể truyền application_name theo service/instance, hoặc dùng session-level metadata có kiểm soát. Không nhét secret hoặc thông tin người dùng nhạy cảm vào application_name.

Khi điều tra một request:

1. Tìm request ID trong application log.
2. Xác định thời gian, service và database connection.
3. Tìm session/app/client trong PostgreSQL logs.
4. Đối chiếu PID/session ID và SQLSTATE.
5. Xem lock/checkpoint/I/O metrics cùng thời điểm.
6. Xác định lỗi ở ứng dụng, database, network hay storage.

## 42. Quy trình xử lý sự cố: connection failures

**Triệu chứng:** ứng dụng không thể kết nối hoặc nhận lỗi too many connections.

- Kiểm tra PostgreSQL process/listener.
- Kiểm tra network/DNS/firewall.
- Tìm FATAL logs theo thời điểm.
- Kiểm tra HBA/authentication nếu có lỗi xác thực.
- Đếm session trong pg_stat_activity.
- Nhóm theo application/user/client.
- Kiểm tra connection pool và retry storm.
- Kiểm tra max_connections và reserved slots.
- Khắc phục client leak/pooling trước khi tăng connection capacity.

## 43. Quy trình xử lý sự cố: query errors

**Triệu chứng:** tỷ lệ SQL errors tăng.

- Nhóm theo SQLSTATE.
- Xác định application và database.
- Xem statement/context liên quan.
- So sánh với deployment/migration.
- Kiểm tra constraint, type và schema.
- Xác định lỗi có retry được hay không.
- Sửa logic hoặc dữ liệu.
- Theo dõi error rate sau thay đổi.

## 44. Quy trình xử lý sự cố: deadlock

**Triệu chứng:** application nhận SQLSTATE 40P01.

- Bật log_lock_waits và bảo đảm log prefix có PID/session/app.
- Đọc deadlock report.
- Xác định transaction cycle.
- Xem thứ tự khóa rows/tables.
- Kiểm tra transaction dài và idle-in-transaction.
- Chuẩn hóa thứ tự lock.
- Rút ngắn transaction và thêm index khi phù hợp.
- Retry transaction có giới hạn.
- Đo deadlock rate sau sửa.

## 45. Quy trình xử lý sự cố: checkpoint và I/O

**Triệu chứng:** latency tăng theo chu kỳ, checkpoint log xuất hiện dày, WAL/disk tăng.

- Xem checkpoint reason trong logs.
- Đọc checkpoint statistics theo version.
- Đo WAL generation rate.
- Kiểm tra max_wal_size và checkpoint_timeout.
- Kiểm tra replication slots và archiver.
- Đối chiếu storage throughput/latency.
- Xem pg_stat_io nếu version hỗ trợ.
- Thử thay đổi một tham số trong staging.
- So sánh latency, WAL và checkpoint frequency.

## 46. Bảo mật và quyền truy cập log

Log có thể chứa:

- SQL statements.
- Parameter values.
- Client IP/hostname.
- User/database names.
- Error context.
- Business identifiers.
- PII hoặc secrets bị truyền nhầm.

Cần:

- Giới hạn quyền đọc log theo role/team.
- Không cho ứng dụng ghi hoặc sửa log PostgreSQL tùy tiện.
- Bảo vệ log bằng encryption at rest/in transit.
- Có retention/deletion policy.
- Mask/redact dữ liệu nhạy cảm ở pipeline nếu cần.
- Audit quyền truy cập log.
- Không gửi log thô tới hệ thống bên ngoài nếu chưa được phép.
- Bảo vệ password trong connection strings và query parameters.

Log đầy đủ không có nghĩa mọi người đều được đọc. Quản lý log phải theo chính sách dữ liệu của tổ chức.

## 47. Những sai lầm thường gặp

1. **Bật log_statement = all lâu dài mà không tính log volume**, khiến disk đầy và tăng overhead.
2. **Bật log_connections/log_disconnections trên hệ thống connection churn cao mà không có retention**, tạo log quá lớn.
3. **Dùng log prefix thiếu PID/session/application**, khiến khó nối các dòng log của cùng một request.
4. **Dùng timezone không thống nhất**, làm correlation với application/OS logs sai lệch.
5. **Cho rằng logging collector là destination**, dẫn tới cấu hình file/syslog sai.
6. **Bật logging_collector rồi chỉ reload**, dù setting này cần restart.
7. **Nhầm rotation với retention**, để file cũ tích tụ tới khi đầy disk.
8. **Dùng log_truncate_on_rotation như cơ chế xóa file cũ**, có thể ghi đè file ngoài ý muốn.
9. **Không kiểm soát quyền file log**, làm lộ SQL và thông tin khách hàng.
10. **Bật reverse DNS logging mà không đánh giá DNS latency**, làm tăng thời gian kết nối.
11. **Nhìn một ERROR message mà không xem SQLSTATE/context**, bỏ qua loại lỗi và nguyên nhân.
12. **Nhầm lock wait với deadlock**, dẫn tới điều chỉnh sai timeout.
13. **Tăng deadlock_timeout để giảm deadlock**, trong khi tham số này chỉ điều khiển thời điểm kiểm tra.
14. **Không bật log_lock_waits**, bỏ lỡ bằng chứng về lock waits kéo dài.
15. **Chỉ xem pg_stat_activity sau khi sự cố kết thúc**, dù session đã đóng và thông tin runtime không còn.
16. **Không dùng pg_blocking_pids**, khiến tìm blocker thủ công khó và sai.
17. **Retry deadlock vô hạn**, gây retry storm.
18. **Không giữ transaction order nhất quán**, khiến deadlock lặp lại.
19. **Coi checkpoint là backup**, không có bản backup độc lập.
20. **Tăng max_wal_size mà không tính disk/slot retention**, làm WAL sử dụng nhiều dung lượng.
21. **Đổ lỗi checkpoint cho storage mà không đọc checkpoint reason**, bỏ qua WAL pressure hoặc slot retention.
22. **Nhầm pg_stat_bgwriter chứa checkpoint stats ở mọi version**, dùng query sai trên PostgreSQL 17+.
23. **Đọc counters tích lũy như latency tức thời**, diễn giải sai trend.
24. **Tắt fsync/full_page_writes để giảm I/O**, làm suy giảm durability.
25. **Không giám sát log disk và pipeline**, mất log trong lúc incident.
26. **Không kiểm tra parameter logging**, vô tình ghi secret/PII vào log.
27. **Alert trên mọi ERROR như cùng mức độ**, tạo noise và bỏ sót lỗi quan trọng.
28. **Không liên kết application_name và request context**, kéo dài thời gian điều tra.

## 48. Bài tập thực hành có đáp án

### Bài 1. Server logs có vai trò gì?

**Đáp án:** Ghi lại sự kiện kết nối, lỗi, câu lệnh, lock waits, deadlocks, checkpoints và context phục vụ điều tra.

### Bài 2. logging_collector khác log_destination thế nào?

**Đáp án:** logging_collector thu thập stderr vào file; log_destination chọn nơi/định dạng phát log.

### Bài 3. logging_collector có thể thay đổi chỉ bằng reload không?

**Đáp án:** Không. Thay đổi setting này cần restart PostgreSQL.

### Bài 4. Chọn CSV log bằng setting nào?

~~~conf
log_destination = 'stderr,csvlog'
logging_collector = on
~~~

**Đáp án:** log_destination bao gồm csvlog; collector cần bật để ghi CSV file.

### Bài 5. Bật JSON log?

~~~conf
log_destination = 'jsonlog'
logging_collector = on
~~~

**Đáp án:** Dùng jsonlog trên PostgreSQL version hỗ trợ và cấu hình collector.

### Bài 6. log_connections và log_disconnections dùng làm gì?

**Đáp án:** Ghi sự kiện kết nối và ngắt kết nối/session duration theo version.

### Bài 7. Placeholder nào ghi application name?

**Đáp án:** %a.

### Bài 8. Placeholder nào ghi SQLSTATE?

**Đáp án:** %e.

### Bài 9. Placeholder nào ghi PID?

**Đáp án:** %p.

### Bài 10. log_min_duration_statement=1s có nghĩa gì?

**Đáp án:** Ghi statement có thời gian thực thi đạt/vượt một giây.

### Bài 11. log_statement=all có rủi ro gì?

**Đáp án:** Log volume lớn và có thể lộ SQL literals/parameter nhạy cảm.

### Bài 12. SQLSTATE 40P01 là lỗi gì?

**Đáp án:** Deadlock detected.

### Bài 13. SQLSTATE 23505 là lỗi gì?

**Đáp án:** Unique violation.

### Bài 14. SQLSTATE 53300 là lỗi gì?

**Đáp án:** Too many connections.

### Bài 15. Deadlock khác lock wait thế nào?

**Đáp án:** Lock wait là đang chờ lock; deadlock là vòng chờ giữa các transaction không thể tự tiến triển.

### Bài 16. deadlock_timeout có tác dụng gì?

**Đáp án:** Xác định thời gian chờ trước khi PostgreSQL kiểm tra deadlock; không phải giới hạn thời gian chờ lock.

### Bài 17. log_lock_waits ghi gì?

**Đáp án:** Các lock waits kéo dài hơn deadlock_timeout.

### Bài 18. pg_blocking_pids dùng để làm gì?

**Đáp án:** Trả về PID của các backend đang chặn PID được chỉ định.

### Bài 19. pg_locks cho biết gì?

**Đáp án:** Lock type, mode, trạng thái granted và object/transaction liên quan.

### Bài 20. PostgreSQL xử lý deadlock thế nào?

**Đáp án:** Phát hiện cycle và hủy một transaction để phá vòng chờ.

### Bài 21. Một cách giảm deadlock hiệu quả?

**Đáp án:** Truy cập tài nguyên theo thứ tự nhất quán và giữ transaction ngắn.

### Bài 22. Checkpoint là gì?

**Đáp án:** Quá trình ghi dirty buffers và checkpoint record để tạo điểm bắt đầu phù hợp cho crash recovery.

### Bài 23. log_checkpoints dùng để làm gì?

**Đáp án:** Ghi thông tin checkpoint/restartpoint vào server logs.

### Bài 24. max_wal_size có phải hard limit?

**Đáp án:** Không. Đây là ngưỡng mềm; WAL có thể vượt do workload, slots và archiving.

### Bài 25. PostgreSQL 17 xem checkpoint statistics ở đâu?

**Đáp án:** pg_stat_checkpointer.

### Bài 26. PostgreSQL 16 trở xuống xem checkpoint statistics ở đâu?

**Đáp án:** pg_stat_bgwriter.

### Bài 27. pg_stat_wal dùng để làm gì?

**Đáp án:** Theo dõi WAL records, bytes, writes, syncs và các thống kê WAL liên quan.

### Bài 28. Vì sao WAL directory lớn dù checkpoint vẫn chạy?

**Đáp án:** Replication slots, archiving failure, standby lag hoặc logical decoding có thể giữ WAL.

### Bài 29. Vì sao rotation không thay retention?

**Đáp án:** Rotation tạo file log mới; retention quyết định thời điểm archive/xóa file cũ.

### Bài 30. Khi nào nên bật log_statement=all?

**Đáp án:** Chủ yếu trong điều tra có thời hạn và kiểm soát chặt; cần đánh giá volume, overhead và dữ liệu nhạy cảm.

## 49. Checklist giám sát và troubleshooting

- [ ] Chọn log destination phù hợp với OS/container/log pipeline.
- [ ] Xác định logging_collector và yêu cầu restart.
- [ ] Đặt log_directory, filename và file permissions.
- [ ] Cấu hình rotation theo thời gian/kích thước.
- [ ] Có retention policy và cảnh báo disk.
- [ ] Dùng log_timezone thống nhất.
- [ ] Thiết lập log_line_prefix có PID/session/user/database/application/client.
- [ ] Đặt application_name rõ ràng cho từng service.
- [ ] Bật connection/disconnection logs khi cần.
- [ ] Chọn log_min_messages và log_min_error_statement phù hợp.
- [ ] Dùng SQLSTATE để phân loại lỗi.
- [ ] Đặt threshold query chậm theo SLA.
- [ ] Không log mọi statement lâu dài nếu chưa đánh giá.
- [ ] Kiểm soát parameter logging và PII/secrets.
- [ ] Bật log_lock_waits khi cần phân tích lock contention.
- [ ] Hiểu deadlock_timeout khác lock_timeout.
- [ ] Dùng pg_stat_activity, pg_locks và pg_blocking_pids để tìm blocker.
- [ ] Xem deadlock report và chuẩn hóa thứ tự lock.
- [ ] Có bounded retry cho SQLSTATE 40P01.
- [ ] Bật log_checkpoints.
- [ ] Theo dõi checkpoint statistics đúng major version.
- [ ] Đo WAL generation và replication/archive retention.
- [ ] Theo dõi pg_stat_wal, pg_stat_archiver và slots.
- [ ] Dùng pg_stat_io khi version hỗ trợ.
- [ ] Đối chiếu PostgreSQL logs với OS/storage metrics.
- [ ] Kiểm tra pg_settings và pending_restart sau thay đổi.
- [ ] Test logging pipeline và retention trước production.
- [ ] Có runbook cho connection spike, SQL errors, deadlocks và checkpoint pressure.

## 50. Tài liệu PostgreSQL chính thức

Đọc tài liệu theo major version đang triển khai:

- [Error Reporting and Logging](https://www.postgresql.org/docs/current/runtime-config-logging.html) — log destinations, collector, prefix, connection/error/statement logging và rotation.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — pg_stat_activity, pg_locks, pg_stat_wal và các statistics views.
- [Viewing Locks](https://www.postgresql.org/docs/current/monitoring-locks.html) — pg_locks, lock waits và blocking sessions.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html) — lock modes, deadlocks và cách tránh.
- [Lock Management](https://www.postgresql.org/docs/current/runtime-config-locks.html) — deadlock_timeout và lock-related settings.
- [Write Ahead Log](https://www.postgresql.org/docs/current/wal.html) — WAL và crash recovery.
- [WAL Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html) — checkpoint_timeout, max_wal_size, checkpoint_completion_target và durability settings.
- [Background Writer](https://www.postgresql.org/docs/current/runtime-config-resource.html) — background writer và related resource settings.
- [ALTER SYSTEM](https://www.postgresql.org/docs/current/sql-altersystem.html) — quản lý cấu hình persistent.
- [Configuration File](https://www.postgresql.org/docs/current/config-setting.html) — setting context, reload và restart behavior.

Các URL /current/ trỏ tới tài liệu PostgreSQL hiện hành. Tên/cột statistics views, log destinations, parameter defaults và setting context có thể khác theo major version; kiểm tra tài liệu đúng phiên bản server trước khi áp dụng.

## 51. Tổng kết

**PostgreSQL logs và runtime statistics bổ sung cho nhau: logs lưu bằng chứng lịch sử, còn system views cho biết trạng thái đang diễn ra.** Kết hợp hai nguồn giúp điều tra connection failures, SQL errors, deadlocks và checkpoint pressure có hệ thống.

1. **Logging collector và log destination là hai khái niệm khác nhau.** Chọn destination và pipeline phù hợp môi trường.
2. **Connection logs và log_line_prefix giúp truy vết session.** application_name, PID, session ID và client address là các khóa liên kết hữu ích.
3. **SQLSTATE giúp phân loại lỗi ổn định.** Không chỉ dựa vào message text.
4. **Statement logging cần kiểm soát.** Log volume, overhead và PII/secrets đều phải được tính đến.
5. **Deadlock khác lock wait.** deadlock_timeout kiểm tra cycle; log_lock_waits ghi các wait kéo dài.
6. **pg_stat_activity, pg_locks và pg_blocking_pids giúp tìm blocker.** Deadlock report cung cấp bằng chứng về vòng chờ đã xảy ra.
7. **Giảm deadlock bằng transaction ngắn và thứ tự lock thống nhất.** Retry phải có giới hạn và bảo đảm an toàn.
8. **Checkpoint tạo điểm hỗ trợ crash recovery.** Nó không phải backup.
9. **log_checkpoints, pg_stat_checkpointer/pg_stat_bgwriter và pg_stat_wal giúp phân tích checkpoint/WAL.** Chọn view theo PostgreSQL major version.
10. **max_wal_size là ngưỡng mềm.** Replication slots và archiving có thể giữ WAL lâu hơn dự kiến.
11. **Rotation không thay retention.** Cần quản lý dung lượng, quyền đọc và vòng đời log.
12. **Monitoring phải kết hợp database, OS và application.** Chỉ số riêng lẻ không đủ kết luận nguyên nhân.
13. **Mọi thay đổi logging/checkpoint cần kiểm tra hiệu lực và đo trước/sau.** Không tắt durability để xử lý I/O pressure.

Một quy trình giám sát tốt giúp đội vận hành biết client nào tạo tải, lỗi nào lặp lại, transaction nào đang chặn nhau và checkpoint/WAL có đang gây áp lực lên storage hay không.
