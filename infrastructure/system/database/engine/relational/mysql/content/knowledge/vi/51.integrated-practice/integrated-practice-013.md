# Dựng replica, quan sát lag và kiểm thử chuyển vai trò

Một MySQL replica chỉ hữu ích khi được khởi tạo đúng từ một bản dữ liệu nhất quán, nhận được binary log liên tục và áp dụng transaction theo đúng thứ tự. Khi hệ thống gặp sự cố, việc chuyển replica thành primary còn đòi hỏi xác định node nào đã nhận đủ dữ liệu, ngăn primary cũ tiếp tục ghi và cập nhật endpoint mà ứng dụng sử dụng. Nếu bỏ qua các bước này, hệ thống có thể mất giao dịch đã xác nhận, tạo hai primary cùng nhận ghi hoặc làm các replica còn lại phân kỳ.

Bài thực hành này thuộc module **DATABASE_MYSQL**, chương **Thực hành tổng hợp**. Bạn sẽ dựng topology source–replica bằng GTID, kiểm tra replication thread và độ trễ, mô phỏng replica lag, thực hiện planned switchover, diễn tập failover có kiểm soát và đưa node cũ trở lại topology. Mục tiêu là hiểu cả lệnh MySQL lẫn bằng chứng cần có trước mỗi bước thay đổi vai trò.

## 1. Mục tiêu và topology phòng lab

Sau bài thực hành, bạn cần có thể:

1. Cấu hình source có binary logging và GTID.
2. Tạo replication account với quyền tối thiểu.
3. Khởi tạo replica từ snapshot nhất quán.
4. Cấu hình GTID auto-position và bắt đầu replication.
5. Xác minh dữ liệu, trạng thái I/O/applier và GTID set.
6. Đo lag bằng nhiều tín hiệu thay vì chỉ dựa vào một con số.
7. Mô phỏng replica chậm hoặc dừng applier và khôi phục.
8. Chuyển vai trò primary/replica trong một planned switchover.
9. Thực hiện failover có fencing và đánh giá RPO/RTO.
10. Đưa node cũ trở lại topology mà không tạo split-brain.

Topology mẫu:

~~~text
                    Application
                         |
                  DB endpoint / proxy
                         |
                         v
                mysql-source (A)
                server_id = 101
                GTID + binlog
                         |
                 asynchronous GTID
                  replication
                         |
                         v
                mysql-replica (B)
                server_id = 102
                read_only
                super_read_only
~~~

Trong bài lab, A ban đầu là source và B là replica. Sau khi chuyển vai trò, B trở thành primary mới và A được cấu hình làm replica của B.

### Yêu cầu môi trường

- Hai máy chủ MySQL cùng major version, ưu tiên cùng minor/patch trong bài lab.
- MySQL 8.0.23 trở lên hoặc MySQL 8.4 để dùng cú pháp SOURCE/REPLICA hiện hành.
- Mỗi server có hostname/IP ổn định và kết nối TCP hai chiều theo topology.
- Đồng bộ thời gian giữa các máy bằng NTP/chrony.
- Mỗi server có server_id duy nhất.
- Đủ dung lượng cho data directory, binary log và relay log.
- Tài khoản quản trị để cấu hình replication và read-only.
- Một môi trường thử nghiệm có thể dừng dịch vụ hoặc chặn mạng để mô phỏng sự cố.

Các lệnh trong bài dùng thuật ngữ **source** và **replica**. Trên MySQL cũ hơn, một số tên lệnh và cột trạng thái vẫn dùng MASTER/SLAVE, ví dụ START SLAVE và SHOW SLAVE STATUS. Kiểm tra tài liệu đúng phiên bản trước khi áp dụng.

Không chạy thử failover, STOP REPLICA, RESET REPLICA hoặc thay đổi read_only trên production nếu chưa có quy trình vận hành được phê duyệt, fencing và kế hoạch phục hồi.

## 2. Cấu hình source

Trên máy A, cấu hình các thuộc tính trong file cấu hình MySQL, thường ở nhóm mysqld:

~~~ini
[mysqld]
server_id=101
log_bin=mysql-bin
binlog_format=ROW
gtid_mode=ON
enforce_gtid_consistency=ON
log_replica_updates=ON
binlog_expire_logs_seconds=604800
~~~

Ý nghĩa:

| Tham số | Mục đích |
|---|---|
| server_id | Định danh duy nhất của server trong replication topology |
| log_bin | Bật binary log để ghi nhận thay đổi |
| binlog_format=ROW | Ghi row event, phù hợp cho replication và CDC |
| gtid_mode=ON | Gán GTID cho transaction được ghi vào binlog |
| enforce_gtid_consistency=ON | Ngăn các thao tác không tương thích với GTID |
| log_replica_updates=ON | Ghi lại các transaction được áp dụng từ upstream vào binlog của node này, cần cho topology trung gian/cascading và một số tình huống promotion |
| binlog_expire_logs_seconds | Thời gian giữ binlog; phải đủ dài cho replica và quy trình phục hồi |

Khởi động lại MySQL nếu thay đổi tham số yêu cầu restart. Sau đó kiểm tra:

~~~sql
SELECT
  @@server_id,
  @@log_bin,
  @@binlog_format,
  @@gtid_mode,
  @@enforce_gtid_consistency,
  @@log_replica_updates;

SELECT @@GLOBAL.gtid_executed;
~~~

Không chọn binlog retention chỉ theo dung lượng hiện tại. Cần tính thời gian outage tối đa, tốc độ sinh binlog cao điểm và thời gian replica/CDC cần để bắt kịp. Nếu binlog bị purge trước khi replica đọc đến, replica có thể phải dựng lại từ snapshot.

## 3. Tạo tài khoản replication

Trên source A, tạo user chỉ được kết nối từ địa chỉ của replica:

~~~sql
CREATE USER 'repl_user'@'10.20.0.12'
  IDENTIFIED BY 'REPLACE_WITH_SECRET'
  REQUIRE SSL;

GRANT REPLICATION SLAVE ON *.*
  TO 'repl_user'@'10.20.0.12';
~~~

Thay địa chỉ, mật khẩu và chính sách TLS theo môi trường. Lưu credential trong secret manager hoặc file cấu hình được bảo vệ; không commit mật khẩu vào source control và không ghi credential vào log.

Kiểm tra quyền:

~~~sql
SHOW GRANTS FOR 'repl_user'@'10.20.0.12';
~~~

Replication account cần quyền replication phù hợp, không cần quyền SELECT/INSERT/UPDATE trên toàn bộ bảng nghiệp vụ chỉ để đọc binary log. Giới hạn host, dùng TLS và luân chuyển secret theo chính sách bảo mật.

Trong MySQL hiện đại, tên privilege vẫn là REPLICATION SLAVE dù thuật ngữ quản trị đã chuyển sang source/replica.

## 4. Chuẩn bị replica

Trên máy B, cấu hình:

~~~ini
[mysqld]
server_id=102
relay_log=relay-bin
log_bin=mysql-bin
binlog_format=ROW
gtid_mode=ON
enforce_gtid_consistency=ON
log_replica_updates=ON
read_only=ON
super_read_only=ON
~~~

Replica có binary log và log_replica_updates hữu ích khi cần promote nó thành source hoặc xây cascading replication. Nếu replica chỉ là leaf và không bao giờ được promote, yêu cầu có thể khác; trong bài lab này ta bật để chuẩn bị cho chuyển vai trò.

read_only hạn chế ghi từ client thông thường. super_read_only siết chặt hơn, ngăn cả user có quyền SUPER ghi trực tiếp, trong khi replication applier vẫn có thể áp dụng transaction. Tài khoản quản trị đặc quyền cao vẫn phải được kiểm soát; đây không phải ranh giới bảo mật thay thế quyền SQL.

Khởi động MySQL B, xác nhận server_id khác A và các biến GTID đã bật. Đảm bảo firewall cho phép B kết nối TCP đến A trên port MySQL và A không bị chặn các luồng cần thiết.

## 5. Khởi tạo dữ liệu replica từ snapshot nhất quán

Replica phải bắt đầu từ một bản dữ liệu phù hợp với GTID/binlog position mà nó sẽ dùng để nhận phần thay đổi tiếp theo. Không thể chỉ cài MySQL trống rồi bật START REPLICA; nếu dữ liệu ban đầu thiếu hoặc lệch, replication có thể dừng hoặc dữ liệu hai node không đồng nhất.

### Phương án snapshot cho bài lab nhỏ

Với dataset nhỏ, có thể dùng mysqldump từ source:

~~~bash
mysqldump \
  --host=SOURCE_HOST \
  --user=BACKUP_USER \
  --single-transaction \
  --source-data=2 \
  --set-gtid-purged=ON \
  --routines \
  --events \
  --triggers \
  --databases appdb \
  --result-file=appdb-seed.sql
~~~

Lệnh này minh họa cho MySQL 8.0 hiện đại. --single-transaction tạo consistent snapshot cho bảng InnoDB; nó không bảo đảm snapshot nhất quán cho nontransactional tables. Trong lúc dump, tránh DDL làm thay đổi cấu trúc bảng. --source-data=2 ghi thông tin tọa độ binlog vào dump dưới dạng comment; GTID set được xử lý qua --set-gtid-purged=ON.

Nếu dump chứa GTID_PURGED, target phải được chuẩn bị phù hợp, thường là instance sạch hoặc đã được kiểm tra GTID set. Không import dump này lên một server đã có lịch sử GTID khác mà chưa đối chiếu. Với database lớn, ưu tiên physical backup, MySQL Clone Plugin hoặc công cụ backup phù hợp để giảm thời gian seed.

Chuyển file dump đến B qua kênh bảo mật và kiểm tra checksum:

~~~bash
sha256sum appdb-seed.sql
~~~

Import vào replica:

~~~bash
mysql --host=REPLICA_HOST --user=ADMIN_USER \
  < appdb-seed.sql
~~~

Sau import, xác minh database, bảng, số hàng đại diện và GTID set. Không tiếp tục cấu hình replication nếu snapshot hoặc GTID state chưa rõ.

### Vì sao snapshot và GTID phải khớp?

Giả sử snapshot chứa dữ liệu đến transaction T. Replica phải nhận đúng các transaction sau T. Nếu snapshot cũ hơn nhưng replica được cấu hình bỏ qua các GTID đã nằm trong snapshot mới hơn, dữ liệu có thể thiếu. Nếu snapshot đã chứa transaction nhưng replica lại áp dụng lại một phần theo file/position không phù hợp, có thể gặp duplicate key hoặc dữ liệu bị áp dụng sai.

GTID auto-position giúp hai server trao đổi các GTID đã thực thi và xác định transaction còn thiếu. Nó không tự sửa một snapshot ban đầu không nhất quán.

## 6. Cấu hình GTID auto-position và khởi động replication

Trên B, cấu hình nguồn replication:

~~~sql
CHANGE REPLICATION SOURCE TO
  SOURCE_HOST = '10.20.0.11',
  SOURCE_PORT = 3306,
  SOURCE_USER = 'repl_user',
  SOURCE_PASSWORD = 'REPLACE_WITH_SECRET',
  SOURCE_AUTO_POSITION = 1,
  SOURCE_SSL = 1;

START REPLICA;
~~~

Trong bài lab, credential là placeholder. Với production, dùng secret handling và cấu hình TLS có xác minh CA/hostname theo phiên bản MySQL. Không truyền mật khẩu trong script có thể bị lưu vào shell history hoặc log.

SOURCE_AUTO_POSITION=1 yêu cầu MySQL dùng GTID thay cho file/position thủ công. Hai server phải được cấu hình GTID tương thích và replica phải có tập GTID ban đầu đúng. Nếu server dùng chứng thư CA riêng, cấu hình SOURCE_SSL_CA và các thuộc tính xác minh TLS tương ứng theo tài liệu phiên bản.

Kiểm tra trạng thái:

~~~sql
SHOW REPLICA STATUS\G
~~~

Kỳ vọng:

- Replica_IO_Running = Yes.
- Replica_SQL_Running = Yes.
- Last_IO_Error rỗng.
- Last_SQL_Error rỗng.
- Source_Host trỏ đến A.
- Retrieved_Gtid_Set tăng khi source có transaction mới.
- Executed_Gtid_Set tiến gần Retrieved_Gtid_Set.

Tên cột có thể khác giữa các bản MySQL. Nếu replication chưa chạy, không chỉ nhìn Seconds_Behind_Source; đọc Last_IO_Error, Last_SQL_Error và trạng thái từng thread.

## 7. Xác minh dữ liệu được replicate

Trên source A, tạo bảng kiểm thử riêng:

~~~sql
CREATE DATABASE IF NOT EXISTS replication_lab;

CREATE TABLE replication_lab.replication_probe (
    probe_id BIGINT NOT NULL PRIMARY KEY,
    payload VARCHAR(100) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB;

INSERT INTO replication_lab.replication_probe
    (probe_id, payload)
VALUES
    (1, 'first transaction'),
    (2, 'second transaction');
~~~

Trên replica B, kiểm tra:

~~~sql
SELECT *
FROM replication_lab.replication_probe
ORDER BY probe_id;
~~~

Thực hiện thêm INSERT, UPDATE và DELETE trên source rồi xác minh kết quả ở replica. Không ghi dữ liệu thử vào bảng nghiệp vụ thật.

### Xác minh bằng GTID

Trên source:

~~~sql
SELECT @@GLOBAL.gtid_executed;
~~~

Trên replica:

~~~sql
SELECT
  @@GLOBAL.gtid_executed,
  @@GLOBAL.gtid_purged;
~~~

GTID set trên replica phải bao gồm các transaction cần áp dụng từ source. Không yêu cầu chuỗi GTID giống hệt trong mọi topology phức tạp; replica có thể có transaction riêng nếu đã cấu hình sai hoặc được dùng cho mục đích khác. Trong topology lab một nguồn, tránh ghi trực tiếp lên replica để giữ tập GTID dễ đối chiếu.

### Chờ một GTID cụ thể được áp dụng

Sau khi ghi trên source, lấy GTID set cần chờ. Trên replica, dùng:

~~~sql
SELECT WAIT_FOR_EXECUTED_GTID_SET(
  'SOURCE_UUID:TRANSACTION_INTERVAL',
  10
);
~~~

Thay chuỗi bằng GTID set thật lấy từ source. Kết quả 0 nghĩa là replica đã thực thi tập GTID được yêu cầu trong thời hạn; 1 nghĩa là hết timeout; NULL biểu thị lỗi. Đây là cách kiểm tra read-after-write cho một transaction cụ thể tốt hơn việc sleep một số giây cố định.

## 8. Quan sát replication lag

Replication lag là độ trễ giữa lúc transaction được commit ở source và lúc transaction tương ứng có thể đọc được trên replica. Lag có thể phát sinh ở bước truyền binlog, xếp hàng relay log hoặc áp dụng transaction.

### Kiểm tra trạng thái tổng quát

~~~sql
SHOW REPLICA STATUS\G
~~~

Các trường cần theo dõi:

| Trường | Ý nghĩa |
|---|---|
| Replica_IO_Running | Receiver thread có đang nhận binlog không |
| Replica_SQL_Running | Applier thread có đang áp dụng transaction không |
| Seconds_Behind_Source | Ước lượng độ trễ theo timestamp event |
| Last_IO_Error | Lỗi khi đọc binlog từ source |
| Last_SQL_Error | Lỗi khi áp dụng relay log |
| Retrieved_Gtid_Set | GTID đã nhận |
| Executed_Gtid_Set | GTID đã thực thi |
| Relay_Log_Space | Dung lượng relay log |
| Source_Server_Id | Định danh source hiện tại |

Seconds_Behind_Source là một chỉ số hữu ích nhưng không phải phép đo hoàn hảo. Nó có thể NULL khi thread dừng hoặc trạng thái không xác định; clock skew giữa các máy cũng làm số đo sai. Một transaction lớn có thể làm lag tăng đột ngột dù receiver thread vẫn hoạt động bình thường.

### Quan sát receiver và applier trong Performance Schema

Trên replica:

~~~sql
SELECT
  CHANNEL_NAME,
  SERVICE_STATE,
  LAST_ERROR_NUMBER,
  LAST_ERROR_MESSAGE,
  LAST_QUEUED_TRANSACTION,
  RECEIVED_TRANSACTION_SET
FROM performance_schema.replication_connection_status;
~~~

Kiểm tra worker applier:

~~~sql
SELECT
  CHANNEL_NAME,
  WORKER_ID,
  SERVICE_STATE,
  LAST_ERROR_NUMBER,
  LAST_ERROR_MESSAGE,
  LAST_APPLIED_TRANSACTION,
  APPLYING_TRANSACTION
FROM performance_schema.replication_applier_status_by_worker;
~~~

Các cột có thể khác theo phiên bản MySQL. Dùng DESCRIBE performance_schema.replication_connection_status và DESCRIBE performance_schema.replication_applier_status_by_worker để xác nhận schema trên server đang chạy.

### Đo lag bằng heartbeat

Seconds_Behind_Source có thể không phản ánh đầy đủ độ trễ người dùng nhìn thấy. Có thể tạo một heartbeat row trên source:

~~~sql
CREATE TABLE replication_lab.replication_heartbeat (
    heartbeat_id TINYINT NOT NULL PRIMARY KEY,
    source_time_utc DATETIME(6) NOT NULL
) ENGINE=InnoDB;

INSERT INTO replication_lab.replication_heartbeat
    (heartbeat_id, source_time_utc)
VALUES
    (1, UTC_TIMESTAMP(6))
ON DUPLICATE KEY UPDATE
    source_time_utc = UTC_TIMESTAMP(6);
~~~

Một job trên source cập nhật hàng này theo chu kỳ, ví dụ mỗi giây hoặc vài giây. Trên replica:

~~~sql
SELECT
  TIMESTAMPDIFF(
    MICROSECOND,
    source_time_utc,
    UTC_TIMESTAMP(6)
  ) / 1000000 AS observed_lag_seconds
FROM replication_lab.replication_heartbeat
WHERE heartbeat_id = 1;
~~~

Heartbeat phải được cập nhật và commit thường xuyên. Đồng bộ đồng hồ giữa source và replica; nếu không, phép đo dựa trên thời gian tường có thể âm hoặc sai. Heartbeat đo độ trễ quan sát được của luồng cập nhật định kỳ, không chứng minh mọi transaction trước đó đã được áp dụng nếu có transaction lớn hoặc nhiều worker chạy song song.

### Theo dõi GTID gap

Có thể so sánh GTID set source và replica để biết replica còn thiếu transaction nào. Trong topology một source, dùng các hàm GTID_SUBSET và GTID_SUBTRACT:

~~~sql
SELECT
  GTID_SUBSET(
    'REPLICA_EXECUTED_GTID_SET',
    'SOURCE_EXECUTED_GTID_SET'
  ) AS replica_is_subset,
  GTID_SUBTRACT(
    'SOURCE_EXECUTED_GTID_SET',
    'REPLICA_EXECUTED_GTID_SET'
  ) AS missing_from_replica;
~~~

Thay placeholder bằng hai GTID set đã thu thập. Nếu replica là subset của source và phần thiếu rỗng sau khi chờ, replica đã bắt kịp tập transaction đó. Trong topology nhiều nguồn hoặc có transaction local, cần phân tích GTID theo từng UUID và không kết luận chỉ từ một phép so sánh tổng quát.

## 9. Mô phỏng replica lag và khôi phục

Chỉ thực hiện phần này trong phòng lab.

### Dừng applier thread

Trên replica B:

~~~sql
STOP REPLICA SQL_THREAD;
~~~

Trên source A, tạo nhiều transaction kiểm thử:

~~~sql
INSERT INTO replication_lab.replication_probe
    (probe_id, payload)
VALUES
    (100, 'lag test 100'),
    (101, 'lag test 101'),
    (102, 'lag test 102');
~~~

Trên B, kiểm tra:

- Receiver thread có thể vẫn chạy và tiếp tục nhận binlog.
- Applier thread đã dừng.
- Retrieved_Gtid_Set có thể tăng trong khi Executed_Gtid_Set không tiến thêm.
- Dữ liệu probe mới chưa xuất hiện trên B.
- Relay log có thể tăng dung lượng.

Khôi phục applier:

~~~sql
START REPLICA SQL_THREAD;
~~~

Chờ GTID được áp dụng, sau đó xác minh dữ liệu. Nếu relay log có lỗi SQL, đọc Last_SQL_Error và worker status trước khi xử lý. Không dùng SQL_SLAVE_SKIP_COUNTER hoặc bỏ qua transaction tùy tiện trong topology GTID; bỏ qua một transaction có thể làm dữ liệu lệch vĩnh viễn.

### Phân biệt receiver lag và applier lag

- Receiver không chạy: replica không lấy được binlog từ source; kiểm tra DNS, network, credential, TLS, source availability và binlog retention.
- Receiver chạy, applier dừng: relay log có thể vẫn được nhận nhưng không áp dụng; kiểm tra SQL error, duplicate key, schema drift và worker.
- Cả hai chạy nhưng lag tăng: workload ghi quá lớn, transaction dài, applier thiếu năng lực hoặc I/O bị giới hạn.
- Lag giảm về 0 nhưng ứng dụng vẫn đọc dữ liệu cũ: kiểm tra routing, cache, transaction snapshot và endpoint thực tế.

Không tăng số applier worker ngay lập tức mà chưa xác định bottleneck. Multi-threaded applier có thể cải thiện throughput trong một số workload nhưng cũng làm tăng cạnh tranh tài nguyên và có các ràng buộc về dependency/order.

## 10. Chuẩn bị chuyển vai trò: planned switchover

Planned switchover là chuyển primary có lịch, trong đó source cũ vẫn hoạt động để ta có thể dừng ghi và chờ replica bắt kịp. Mục tiêu là giảm hoặc loại bỏ mất dữ liệu đã commit.

### Checklist trước switchover

- B đã có receiver và applier thread hoạt động bình thường.
- Không có Last_IO_Error hoặc Last_SQL_Error.
- B đã áp dụng đến GTID set cần chuyển.
- Không còn transaction ghi nghiệp vụ đang mở trên A.
- Ứng dụng có thể tạm dừng ghi hoặc vào maintenance mode.
- Endpoint/proxy/DNS có kế hoạch chuyển sang B.
- Có người vận hành xác nhận fencing và rollback plan.
- Backup/restore và quyền truy cập quản trị đã được kiểm tra.

### Trình tự planned switchover

**Bước 1 — Dừng nhận ghi mới**

Đưa ứng dụng vào maintenance/read-only mode hoặc dừng luồng ghi. Drain request đang xử lý và chờ transaction đang mở hoàn tất. Không chỉ bật read_only rồi giả định mọi transaction đang chạy đã kết thúc.

**Bước 2 — Ghi lại GTID cuối trên source**

Trên A, sau khi đã dừng ghi và drain transaction:

~~~sql
SELECT @@GLOBAL.gtid_executed;
~~~

Lưu GTID set này làm mốc chuyển vai trò.

**Bước 3 — Chờ replica áp dụng hết GTID**

Trên B:

~~~sql
SELECT WAIT_FOR_EXECUTED_GTID_SET(
  'GTID_SET_CAPTURED_FROM_SOURCE',
  60
);
~~~

Chỉ tiếp tục khi kết quả là 0. Nếu timeout, giữ ứng dụng ở trạng thái không ghi, tìm nguyên nhân lag và chờ/khắc phục. Không promote replica khi chưa biết transaction nào còn thiếu.

**Bước 4 — Fence source cũ**

Trên A, bật chế độ chỉ đọc:

~~~sql
SET GLOBAL super_read_only = ON;
SET GLOBAL read_only = ON;
~~~

Đồng thời ngăn ứng dụng và các writer khác kết nối ghi vào A qua proxy, firewall hoặc cơ chế điều phối. Fencing phải có hiệu lực với mọi đường ghi, bao gồm job nền và tài khoản đặc quyền. read_only/super_read_only là lớp bảo vệ bổ sung, không thay thế fencing hạ tầng.

**Bước 5 — Dừng replication trên B và promote**

Trên B:

~~~sql
STOP REPLICA;
RESET REPLICA ALL;
SET GLOBAL super_read_only = OFF;
SET GLOBAL read_only = OFF;
~~~

RESET REPLICA ALL xóa cấu hình kết nối source và relay log metadata của replica; không dùng lệnh này trước khi xác nhận B đã bắt kịp và đã quyết định promote. Không chạy RESET MASTER hoặc RESET BINARY LOGS AND GTIDS để xử lý chuyển vai trò; các lệnh đó có thể phá hủy lịch sử binlog/GTID cần thiết.

**Bước 6 — Xác minh B nhận ghi**

Tạo một transaction probe mới trên B, xác minh dữ liệu và GTID. Kiểm tra quyền, read-only flags và endpoint thực tế.

**Bước 7 — Chuyển endpoint ứng dụng**

Cập nhật proxy, service discovery hoặc DNS theo cơ chế của hệ thống. Làm mới connection pool để ứng dụng không tiếp tục dùng connection cũ trỏ tới A. Mở lại ghi sau khi xác nhận chỉ B nhận ghi.

## 11. Diễn tập failover khi source gặp sự cố

Failover ngoài kế hoạch khó hơn switchover vì source có thể không phản hồi và không thể xác nhận transaction cuối đã được replica áp dụng hay chưa.

### Nguy cơ split-brain

Split-brain xảy ra khi A và B cùng được coi là primary và cùng nhận ghi. Khi mạng bị phân vùng, ứng dụng ở hai phía có thể ghi vào hai node độc lập. Sau khi kết nối trở lại, GTID set có thể phân kỳ; MySQL không tự hợp nhất hai lịch sử ghi khác nhau thành một lịch sử đúng.

Fencing là bước bắt buộc trước khi mở ghi trên candidate:

- Tắt hoặc cô lập source cũ ở tầng hạ tầng.
- Thu hồi route ghi đến source cũ.
- Dừng mysqld hoặc cách ly network khi có thể.
- Xác minh mọi writer, scheduler và job nền không còn ghi vào node cũ.

Nếu không thể chứng minh source cũ đã bị fence, không mở ghi trên replica mới.

### Chọn candidate

Nếu có nhiều replica:

1. Thu thập Retrieved_Gtid_Set và Executed_Gtid_Set của từng replica.
2. Xác định node đã áp dụng nhiều transaction nhất trong tập giao dịch có thể khôi phục.
3. Kiểm tra applier error, transaction đang chạy và relay log.
4. Đánh giá transaction đã được source xác nhận với client nhưng chưa replicate có thể bị mất.
5. Chọn candidate theo chính sách RPO và bằng chứng GTID, không chỉ theo Seconds_Behind_Source.

Nếu source đã mất vĩnh viễn và replica bất đồng bộ còn thiếu transaction, failover có thể có RPO lớn hơn 0. Ghi nhận rõ phạm vi mất dữ liệu có thể xảy ra và thực hiện đối soát nghiệp vụ sau khi phục hồi.

### Trình tự failover có kiểm soát

1. Tuyên bố sự cố và khóa thay đổi topology để chỉ một người/automation điều phối.
2. Fence source cũ bằng hạ tầng độc lập với MySQL nếu cần.
3. Xác minh candidate không còn lỗi applier và chọn node có GTID set phù hợp nhất.
4. Nếu còn relay log đã nhận nhưng chưa áp dụng, đánh giá khả năng áp dụng hết trước khi promote.
5. Dừng replica và xóa cấu hình upstream khi đã quyết định promote.
6. Tắt read_only/super_read_only trên candidate.
7. Kiểm tra dữ liệu, GTID và khả năng ghi.
8. Chuyển endpoint ứng dụng và làm mới pool.
9. Theo dõi lỗi, latency, duplicate và giao dịch thiếu.
10. Giữ source cũ bị fence cho đến khi có kế hoạch rebuild/rejoin.

Không tự động chọn replica chỉ vì nó trả lời ping hoặc có Seconds_Behind_Source bằng 0. Chỉ số đó không chứng minh node có đầy đủ mọi giao dịch đã commit trước sự cố.

## 12. Đưa source cũ trở lại topology

Sau failover, A không được tự khởi động lại và tiếp tục nhận ghi. Nó có thể chứa transaction riêng mà B chưa có hoặc có GTID set phân kỳ.

Quy trình an toàn:

1. Giữ A ở trạng thái fenced/read-only.
2. Thu thập GTID set của A và B.
3. Xác định A có transaction riêng hay không.
4. Nếu hai node phân kỳ, không cố tự động merge dữ liệu.
5. Ưu tiên dựng lại A từ backup/snapshot của B rồi cấu hình A làm replica.
6. Nếu muốn rejoin dựa trên GTID hiện có, phải đánh giá transaction errant, dữ liệu khác biệt và khả năng phục hồi trước.
7. Sau khi A replicate từ B, xác minh GTID set, row count/checksum và trạng thái thread.
8. Chỉ đưa A vào pool đọc sau khi đã kiểm thử consistency; không chuyển nó thành writer.

Không dùng RESET MASTER hoặc xóa GTID history như một thao tác sửa lỗi chung. Các thao tác này có thể làm mất bằng chứng lịch sử và khiến việc xác định dữ liệu bị thiếu khó hơn.

Sau khi đã dựng lại A từ snapshot nhất quán của B, cấu hình A làm replica bằng thông tin endpoint mới:

~~~sql
-- Thực hiện trên A sau khi đã seed dữ liệu và xác minh GTID.
SET GLOBAL super_read_only = ON;
SET GLOBAL read_only = ON;

CHANGE REPLICATION SOURCE TO
  SOURCE_HOST = '10.20.0.12',
  SOURCE_PORT = 3306,
  SOURCE_USER = 'repl_user',
  SOURCE_PASSWORD = 'REPLACE_WITH_SECRET',
  SOURCE_AUTO_POSITION = 1,
  SOURCE_SSL = 1;

START REPLICA;
~~~

Thay endpoint, tài khoản và TLS options theo môi trường. Không chạy lệnh này trên A còn chứa dữ liệu phân kỳ chưa được xử lý; việc cấu hình GTID auto-position không tự loại bỏ transaction riêng hoặc sửa các hàng khác nhau.

## 13. Kiểm thử vai trò và tính nhất quán

Trong lab, tạo một bảng kiểm tra transaction:

~~~sql
CREATE TABLE replication_lab.role_switch_test (
    request_id CHAR(36) NOT NULL PRIMARY KEY,
    note VARCHAR(100) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB;
~~~

Trước switchover:

1. Ghi một số request ID trên A.
2. Chờ B áp dụng bằng GTID.
3. So sánh số hàng và các request ID ở hai node.
4. Thực hiện planned switchover.
5. Ghi request ID mới trên B.
6. Sau khi A được cấu hình lại làm replica của B, xác minh A nhận request ID mới.

Trường hợp failover không kế hoạch:

- Dừng A trong môi trường lab sau khi tạo một số transaction.
- Tạo lag có chủ đích để B thiếu một phần transaction.
- Thử quy trình đánh giá candidate và ghi nhận transaction có thể mất.
- Fence A trước khi promote B.
- Sau khi B nhận ghi, không khởi động A như một primary độc lập.
- Rebuild hoặc rejoin A từ B và đối soát dữ liệu.

Kết quả cần ghi:

| Hạng mục | Kết quả cần quan sát |
|---|---|
| Receiver/applier | Thread chạy hay dừng, lỗi cuối cùng |
| GTID | Tập đã nhận, đã thực thi và còn thiếu |
| Lag | Seconds_Behind_Source, heartbeat và backlog |
| Data consistency | Row count, request ID và checksum |
| Role | Node nào được phép ghi |
| Endpoint | Ứng dụng đang kết nối node nào |
| Recovery | Node cũ đã được rebuild/rejoin hay vẫn fenced |

## 14. RPO, RTO và lựa chọn replication mode

Hai chỉ số giúp đánh giá chất lượng failover:

- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa có thể mất, đo theo thời gian hoặc phạm vi transaction.
- **RTO (Recovery Time Objective):** thời gian tối đa để khôi phục dịch vụ.

Asynchronous replication có thể có RPO lớn hơn 0 vì source có thể xác nhận commit trước khi replica nhận và áp dụng transaction. Semi-synchronous replication có thể giảm cửa sổ mất dữ liệu trong một số điều kiện, nhưng không tự bảo đảm zero data loss cho mọi sự cố hoặc mọi cấu hình. Cần đọc chính sách ACK, timeout, fallback và hành vi khi replica mất kết nối theo đúng phiên bản.

Group Replication/InnoDB Cluster hoặc giải pháp điều phối HA có thể cung cấp cơ chế membership, quorum và failover tự động hơn, nhưng vẫn cần thiết kế fencing, network partition handling, client routing và kiểm thử. Một cặp source–replica thủ công không tự trở thành HA chỉ vì có thể chạy START REPLICA.

### Bảng lựa chọn khái quát

| Mô hình | Đặc điểm | Rủi ro/cân nhắc |
|---|---|---|
| Asynchronous replication | Source commit độc lập với replica | Có thể mất transaction cuối khi source hỏng |
| Semisynchronous replication | Source chờ ít nhất một replica ACK theo chính sách | ACK không đồng nghĩa replica đã áp dụng transaction; timeout/fallback ảnh hưởng RPO |
| Group Replication / InnoDB Cluster | Membership, quorum và cơ chế failover tích hợp | Phức tạp hơn, cần số node/quorum và network ổn định |
| External orchestrator | Điều phối topology và promotion theo chính sách | Cần fencing, quyền và kiểm thử failure mode |

Không tuyên bố zero RPO nếu chưa chứng minh bằng cấu hình, failure model và thử nghiệm thực tế. RPO/RTO phải được đo trong diễn tập, không chỉ ghi trong tài liệu thiết kế.

## 15. Checklist vận hành và cảnh báo

### Trước khi đưa replica vào sử dụng

- [ ] Source có binary log và GTID được cấu hình đúng.
- [ ] server_id của mọi node là duy nhất.
- [ ] Snapshot ban đầu nhất quán và GTID state được đối chiếu.
- [ ] Replication user chỉ có quyền cần thiết và kết nối bảo mật.
- [ ] Receiver và applier thread đều chạy.
- [ ] Last_IO_Error và Last_SQL_Error rỗng.
- [ ] Dữ liệu mẫu, row count hoặc checksum đã được đối chiếu.
- [ ] read_only và super_read_only được bật trên replica.
- [ ] Binlog retention đủ cho outage và thời gian catch-up.

### Giám sát liên tục

- [ ] Receiver/applier state.
- [ ] Seconds_Behind_Source và heartbeat lag.
- [ ] Retrieved/Executed GTID set và transaction gap.
- [ ] Relay log space và disk free.
- [ ] Last_IO_Error/Last_SQL_Error.
- [ ] Tốc độ sinh binlog và thời gian giữ log.
- [ ] CPU, I/O, network và applier throughput.
- [ ] Tỷ lệ lỗi đọc từ replica và freshness của báo cáo.

### Trước khi chuyển vai trò

- [ ] Có kế hoạch maintenance và drain writer.
- [ ] Đã chụp GTID set cuối của source.
- [ ] Candidate đã áp dụng đến GTID set yêu cầu.
- [ ] Source cũ được fence trên mọi đường ghi.
- [ ] Chỉ một candidate được promote.
- [ ] Endpoint và connection pool có kế hoạch cập nhật.
- [ ] Có đối soát dữ liệu sau chuyển vai trò.
- [ ] Có kế hoạch rebuild/rejoin node cũ.

## 16. Sự cố thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Replica_IO_Running = No | Network, DNS, credential, TLS hoặc source không hoạt động | Last_IO_Error, kết nối TCP, grants và chứng thư |
| Replica_SQL_Running = No | SQL applier gặp lỗi, schema drift hoặc duplicate key | Last_SQL_Error, worker status và dữ liệu liên quan |
| Seconds_Behind_Source = NULL | Thread dừng hoặc không đủ thông tin đo | Kiểm tra receiver/applier và Performance Schema |
| Lag tăng liên tục | Transaction lớn, write rate cao, I/O chậm hoặc applier thiếu năng lực | Relay log, worker, CPU/I/O và workload |
| GTID gap không giảm | Replica không nhận hoặc không áp dụng transaction | Retrieved/Executed set, thread state và binlog retention |
| Replica thiếu dữ liệu sau seed | Snapshot không nhất quán hoặc GTID/coordinate sai | Kiểm tra nguồn dump, GTID_PURGED và phạm vi dữ liệu |
| Duplicate key trên replica | Có ghi trực tiếp vào replica hoặc dữ liệu seed lệch | Dừng xử lý tự động, so sánh GTID và dữ liệu; không skip tùy tiện |
| Source cũ nhận ghi sau failover | Thiếu fencing hoặc endpoint cũ còn mở | Cô lập ngay source cũ, dừng writer và đánh giá phân kỳ |

Khi applier dừng vì lỗi dữ liệu, không xóa hàng hoặc bỏ qua event chỉ để thread chạy lại. Xác định nguyên nhân gốc, đánh giá transaction bị ảnh hưởng và lập kế hoạch sửa dữ liệu có đối soát.

## 17. Kịch bản thực hành cuối bài

Thực hiện lần lượt và lưu lại bằng chứng:

**Kịch bản A — Dựng replication**

1. Cấu hình A và B với server_id khác nhau, GTID và binary log.
2. Tạo replication user.
3. Seed B từ snapshot nhất quán.
4. Cấu hình SOURCE_AUTO_POSITION và START REPLICA.
5. Xác minh hai thread, GTID và dữ liệu probe.

**Kịch bản B — Tạo và xử lý lag**

1. Dừng SQL_THREAD trên B.
2. Ghi nhiều transaction trên A.
3. Quan sát Retrieved_Gtid_Set, Executed_Gtid_Set và relay log.
4. Chạy heartbeat để đo lag quan sát.
5. Start SQL_THREAD và chờ GTID bắt kịp.
6. Xác minh dữ liệu cuối cùng.

**Kịch bản C — Planned switchover**

1. Dừng ghi và drain transaction trên A.
2. Chụp GTID set cuối.
3. Chờ B áp dụng hết GTID.
4. Fence A.
5. Promote B và chuyển endpoint.
6. Ghi probe mới trên B.
7. Reconfigure A thành replica của B.
8. Xác minh A nhận transaction mới.

**Kịch bản D — Failover ngoài kế hoạch**

1. Tạo một số transaction và cố ý làm B lag.
2. Dừng A trong lab.
3. Đánh giá GTID và xác định dữ liệu có thể mất.
4. Fence A trước khi mở ghi trên B.
5. Promote B theo quyết định RPO.
6. Đối soát dữ liệu và ghi nhận khoảng transaction bị thiếu.
7. Rebuild/rejoin A từ B.

### Tiêu chí hoàn thành

- Replication chạy ổn định và không có lỗi I/O/applier.
- Bạn giải thích được khác biệt giữa transaction đã nhận và đã áp dụng.
- Bạn chứng minh được replica bắt kịp một GTID set cụ thể.
- Bạn đo được lag và giải thích giới hạn của Seconds_Behind_Source.
- Bạn chuyển vai trò mà không để hai node cùng nhận ghi.
- Bạn đưa node cũ trở lại topology mà không xóa GTID history tùy tiện.
- Bạn mô tả được RPO/RTO quan sát trong từng kịch bản.

## Tài liệu tham khảo

- [MySQL Reference Manual — Replication](https://dev.mysql.com/doc/refman/8.4/en/replication.html)
- [MySQL Reference Manual — GTID Concepts](https://dev.mysql.com/doc/refman/8.4/en/replication-gtids-concepts.html)
- [MySQL Reference Manual — GTID Auto-Positioning](https://dev.mysql.com/doc/refman/8.4/en/replication-gtids-auto-positioning.html)
- [MySQL Reference Manual — SHOW REPLICA STATUS](https://dev.mysql.com/doc/refman/8.4/en/show-replica-status.html)
- [MySQL Reference Manual — WAIT_FOR_EXECUTED_GTID_SET](https://dev.mysql.com/doc/refman/8.4/en/gtid-functions.html)
- [MySQL Reference Manual — Replication Performance Schema Tables](https://dev.mysql.com/doc/refman/8.4/en/performance-schema-replication-tables.html)
- [MySQL Reference Manual — Semisynchronous Replication](https://dev.mysql.com/doc/refman/8.4/en/replication-semisync.html)

## Kết luận

Dựng replica là bài toán về snapshot nhất quán, GTID, binary log và khả năng áp dụng transaction; chuyển vai trò còn là bài toán về dữ liệu cuối cùng, fencing và định tuyến ứng dụng. Hãy quan sát cả receiver, applier, GTID gap, heartbeat và lỗi thay vì dựa riêng vào Seconds_Behind_Source. Planned switchover cần dừng ghi, chờ replica áp dụng GTID cuối rồi mới promote. Failover ngoài kế hoạch phải fence source cũ trước khi mở ghi trên candidate và chấp nhận RPO theo bằng chứng thực tế. Cuối cùng, node cũ chỉ được đưa lại làm replica sau khi đối chiếu GTID và dữ liệu, thường bằng cách rebuild từ primary mới.
