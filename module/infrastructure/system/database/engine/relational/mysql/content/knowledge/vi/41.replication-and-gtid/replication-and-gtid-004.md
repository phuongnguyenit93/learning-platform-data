# Thiết lập replication bằng file/position hoặc GTID

Bài học này thuộc module **DATABASE_MYSQL**. Trong quá trình làm chủ MySQL, replication giúp duy trì một hoặc nhiều bản sao dữ liệu để hỗ trợ tính sẵn sàng, phân tải đọc và chuyển đổi máy chủ khi cần. Để vận hành replication an toàn, cần cấu hình binary log, định danh máy chủ, tài khoản sao chép, bản dữ liệu khởi tạo và điểm bắt đầu đồng bộ. MySQL hỗ trợ xác định điểm bắt đầu bằng cặp **binlog file/position** hoặc bằng **GTID (Global Transaction Identifier)**.

Replication mặc định của MySQL là bất đồng bộ: source ghi transaction vào binary log; replica lấy sự kiện từ source, lưu vào relay log rồi áp dụng lên dữ liệu của mình. Vì vậy replica có thể trễ so với source. Replication cải thiện khả năng sẵn sàng và hỗ trợ mở rộng một số workload đọc, nhưng không thay thế backup độc lập hay quy trình phục hồi PITR.

## 1. Kiến trúc replication cơ bản

Trong mô hình source/replica:

1. Ứng dụng gửi thao tác ghi tới **source**.
2. MySQL source ghi các thay đổi phù hợp vào binary log.
3. Luồng nhận trên **replica** kết nối đến source bằng tài khoản replication và đọc các sự kiện mới.
4. Replica lưu sự kiện vào relay log.
5. Luồng áp dụng đọc relay log và thực thi các thay đổi trên replica.

Hai luồng trên replica có trách nhiệm khác nhau:

- **Receiver (I/O thread):** kết nối source, lấy binary log events và ghi vào relay log.
- **Applier (SQL thread hoặc worker threads):** đọc relay log và áp dụng transaction vào dữ liệu replica.

Sơ đồ khái quát:

```text
Ứng dụng ghi
    |
    v
+------------------+
| Source MySQL     |
| Binary log       |
+------------------+
    |
    |  replication connection
    v
+------------------+
| Replica MySQL    |
| Receiver / I/O   |
| Relay log        |
| Applier / SQL    |
+------------------+
    |
    v
Ứng dụng đọc (nếu được thiết kế phù hợp)
```

Trong tài liệu MySQL mới, thuật ngữ `SOURCE` và `REPLICA` thay cho `MASTER` và `SLAVE`. Các câu lệnh hiện đại là `CHANGE REPLICATION SOURCE TO`, `START REPLICA`, `STOP REPLICA` và `SHOW REPLICA STATUS`. Một số phiên bản cũ dùng cú pháp tên cũ; hãy chọn câu lệnh tương thích với phiên bản đang chạy. Các ví dụ bên dưới ưu tiên cú pháp MySQL 8.0.23 trở lên.

## 2. Chuẩn bị source và replica

Trước khi thiết lập kết nối, cần cấu hình định danh và binary logging trên các máy chủ.

### 2.1. Cấu hình source

Ví dụ cấu hình trong tệp cấu hình MySQL:

```ini
[mysqld]
server_id=101
log_bin=/var/lib/mysql/mysql-bin
binlog_format=ROW
binlog_expire_logs_seconds=604800
```

- `server_id` là định danh số của máy chủ trong topology replication. Mỗi máy chủ phải có ID riêng, khác 0.
- `log_bin` bật binary logging và đặt tên cơ sở cho các file binlog.
- `binlog_format=ROW` là lựa chọn thường được khuyến nghị cho replication vì ghi nhận thay đổi hàng thực tế. Hành vi và khả năng cấu hình định dạng phụ thuộc phiên bản MySQL.
- `binlog_expire_logs_seconds` đặt thời gian lưu binlog tự động theo giây. Retention phải đủ dài để replica bị gián đoạn có thời gian bắt kịp và để quy trình PITR còn log cần thiết.

Sau khi thay đổi cấu hình khởi động, restart MySQL nếu biến yêu cầu. Xác minh:

```sql
SHOW VARIABLES LIKE 'server_id';
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'binlog_format';
SHOW VARIABLES LIKE 'binlog_expire_logs_seconds';
SHOW BINARY LOGS;
```

### 2.2. Cấu hình replica

Replica cũng cần `server_id` riêng. Nếu replica sẽ cấp binlog cho replica cấp dưới hoặc có thể được promote thành source, bật ghi lại các transaction nhận từ upstream:

```ini
[mysqld]
server_id=102
relay_log=/var/lib/mysql/mysql-relay-bin
log_bin=/var/lib/mysql/mysql-bin
log_replica_updates=ON
read_only=ON
super_read_only=ON
```

`log_replica_updates=ON` giúp các transaction được áp dụng từ source cũng được ghi vào binary log cục bộ, hữu ích cho replication nhiều tầng và một số quy trình chuyển đổi vai trò. `read_only` và `super_read_only` giúp hạn chế ghi trực tiếp từ ứng dụng hoặc người dùng thông thường trên replica; tài khoản quản trị đặc quyền vẫn cần được kiểm soát chặt. Luồng replication có thể áp dụng thay đổi theo cơ chế nội bộ của MySQL.

Không nhất thiết mọi replica đều phải bật `log_bin` nếu chỉ phục vụ đọc và không cần downstream replication hoặc promotion. Hãy xác định trước vai trò dự kiến và thiết kế cấu hình tương ứng. Sau khi restart, kiểm tra `server_id` và các biến đã đặt.

### 2.3. Chuẩn bị mạng và phiên bản

- Source phải cho phép kết nối TCP từ replica tới cổng MySQL, thường là `3306`, theo firewall và network policy.
- Hai máy chủ cần có phiên bản và cấu hình tương thích. Kiểm tra tài liệu nâng cấp/replication của các phiên bản cụ thể, đặc biệt khi source và replica khác nhánh phát hành.
- Đồng bộ thời gian hệ thống giúp log, giám sát và điều tra sự cố dễ hơn. Thời gian không thay thế thứ tự transaction trong binlog.
- Dùng TLS để mã hóa kết nối replication qua mạng không tin cậy.
- Tài khoản replication chỉ nên được phép kết nối từ địa chỉ của replica và chỉ có quyền cần thiết.

## 3. Tạo tài khoản replication

Trên source, tạo tài khoản riêng cho replica. Thay địa chỉ IP và mật khẩu minh họa bằng giá trị của môi trường thực tế:

```sql
CREATE USER 'repl'@'192.0.2.20'
  IDENTIFIED BY 'replace-with-a-strong-secret'
  REQUIRE SSL;

GRANT REPLICATION SLAVE
  ON *.* TO 'repl'@'192.0.2.20';
```

Quyền `REPLICATION SLAVE` cho phép replica đọc binary log của source. Tên quyền này vẫn xuất hiện trong nhiều phiên bản và tài liệu MySQL; kiểm tra cú pháp quyền được hỗ trợ nếu đang dùng phiên bản mới hoặc bản phân phối khác. Không cấp `ALL PRIVILEGES` cho tài khoản replication.

Xác minh tài khoản và quyền:

```sql
SHOW GRANTS FOR 'repl'@'192.0.2.20';
```

Mật khẩu trong ví dụ chỉ là placeholder. Không ghi mật khẩu thật vào mã nguồn, lịch sử shell hoặc tài liệu chia sẻ. Khi chạy `CHANGE REPLICATION SOURCE TO`, thông tin kết nối được lưu trong metadata replication; giới hạn quyền truy cập vào máy chủ và các công cụ có thể đọc metadata này.

## 4. Khởi tạo dữ liệu trên replica

Replication chỉ truyền những thay đổi phát sinh sau điểm bắt đầu đã cấu hình. Nó không tự sao chép toàn bộ dữ liệu hiện có trước thời điểm đó. Vì vậy, trước khi start replication, replica phải có một bản dữ liệu nền nhất quán tương ứng với điểm bắt đầu.

Có thể khởi tạo bằng logical backup, physical backup hoặc MySQL Clone Plugin tùy quy mô và phiên bản. Dù chọn công cụ nào, cần giữ metadata chỉ ra chính xác vị trí binlog hoặc tập GTID đã được bao gồm trong bản dữ liệu nền.

Ví dụ logical dump trên source với InnoDB:

```bash
mysqldump \
  --host=source.example.net \
  --user=backup_user \
  --password \
  --single-transaction \
  --source-data=2 \
  --routines \
  --events \
  --all-databases \
  > initial-backup.sql
```

`--single-transaction` tạo consistent snapshot cho các bảng transactional như InnoDB. `--source-data=2` ghi thông tin binary log file/position vào dump dưới dạng comment để người vận hành lấy điểm bắt đầu replication. Tùy chọn và tên mới này phụ thuộc phiên bản; các bản cũ có thể dùng `--master-data=2`. Kiểm tra `mysqldump --help` và tài liệu đúng phiên bản trước khi chạy.

Với bảng không transactional, các thay đổi DDL trong lúc dump hoặc workload ghi phức tạp, snapshot có thể không nhất quán như mong đợi. Cần lên lịch cửa sổ bảo trì, khóa ghi phù hợp hoặc dùng công cụ backup có cơ chế snapshot nhất quán. Tài khoản backup cũng phải có đủ quyền cho phạm vi dump.

Sau khi dump hoàn tất, chuyển tệp đến replica qua kênh an toàn và restore lên replica đã chuẩn bị. Trước khi import, bảo đảm replica chưa có dữ liệu xung đột hoặc GTID không tương thích. Kiểm tra schema, đối tượng, số lượng dữ liệu quan trọng và metadata backup trước khi cấu hình luồng replication.

## 5. Thiết lập replication bằng file/position

Phương thức file/position chỉ rõ file binary log và vị trí byte nơi replica bắt đầu đọc sự kiện. Đây là cách định vị truyền thống, dễ quan sát và hữu ích khi hệ thống chưa bật GTID.

### 5.1. Lấy file và position từ bản backup

Với dump tạo bằng `--source-data=2`, mở phần đầu tệp và tìm dòng comment có câu lệnh `CHANGE REPLICATION SOURCE TO` hoặc cú pháp tương đương theo phiên bản. Ví dụ minh họa:

```sql
-- CHANGE REPLICATION SOURCE TO
--   SOURCE_LOG_FILE='mysql-bin.000145',
--   SOURCE_LOG_POS=782;
```

Hai giá trị trên chỉ là ví dụ. Dùng đúng tên file và position được ghi trong bản backup đang restore. Nếu dùng physical backup, lấy tọa độ từ metadata do công cụ backup tạo ra. Không chạy `SHOW BINARY LOG STATUS` ở một thời điểm bất kỳ rồi dùng position đó với một snapshot được tạo ở thời điểm khác; hai mốc phải tương ứng với cùng một trạng thái dữ liệu.

### 5.2. Cấu hình source trên replica

Sau khi restore dữ liệu nền, chạy trên replica:

```sql
CHANGE REPLICATION SOURCE TO
  SOURCE_HOST='source.example.net',
  SOURCE_PORT=3306,
  SOURCE_USER='repl',
  SOURCE_PASSWORD='replace-with-a-strong-secret',
  SOURCE_LOG_FILE='mysql-bin.000145',
  SOURCE_LOG_POS=782,
  SOURCE_CONNECT_RETRY=10,
  SOURCE_SSL=1;

START REPLICA;
```

Thay host, thông tin xác thực, file và position bằng dữ liệu thực tế. Chỉ định TLS theo cấu hình chứng thư của môi trường; `SOURCE_SSL=1` yêu cầu kết nối SSL/TLS nhưng hệ thống production nên xác minh CA, chứng thư máy chủ và chính sách xác minh danh tính peer phù hợp. Tránh tắt xác minh chứng thư chỉ để làm cho kết nối chạy được.

Với MySQL cũ, các thuộc tính có thể dùng tiền tố `MASTER_` và câu lệnh `CHANGE MASTER TO`; các phiên bản mới ưu tiên `SOURCE_`. Không trộn cú pháp cũ và mới trong cùng một lệnh.

### 5.3. Kiểm tra replication

Trên replica:

```sql
SHOW REPLICA STATUS\G
```

Các trường quan trọng:

| Trường | Ý nghĩa |
|---|---|
| `Replica_IO_Running` | Luồng receiver có đang chạy hay không |
| `Replica_SQL_Running` | Luồng applier có đang chạy hay không |
| `Source_Host` | Source mà replica đang kết nối |
| `Source_Log_File` | File binlog source mà receiver đang đọc |
| `Read_Source_Log_Pos` | Position đã đọc từ source |
| `Relay_Source_Log_File` | File source tương ứng với relay log đang được áp dụng |
| `Exec_Source_Log_Pos` | Position source đã được applier thực thi đến |
| `Seconds_Behind_Source` | Ước lượng độ trễ theo trạng thái replication, không phải phép đo đầy đủ cho mọi tình huống |
| `Last_IO_Error` | Lỗi gần nhất của receiver |
| `Last_SQL_Error` | Lỗi gần nhất của applier |

Thông thường, hai luồng cần ở trạng thái `Yes` và không có lỗi gần nhất. `Seconds_Behind_Source` bằng 0 không tự chứng minh dữ liệu đã được đối chiếu hoàn toàn; giá trị `NULL` cũng có thể xuất hiện khi luồng chưa chạy hoặc không xác định được độ trễ. Cần kết hợp trạng thái thread, vị trí log, metric lag và kiểm tra dữ liệu ứng dụng.

## 6. Thiết lập replication bằng GTID

**GTID** định danh transaction bằng một mã duy nhất, thường có dạng `server_uuid:transaction_number`. Thay vì cấu hình replica đọc từ một cặp file/position cụ thể, GTID auto-position cho phép replica thông báo tập transaction nó đã thực thi. Source gửi những transaction còn thiếu mà nó vẫn giữ trong binary log.

GTID giảm thao tác quản lý vị trí thủ công khi chuyển source, dựng replica mới hoặc tổ chức topology nhiều máy chủ. Tuy nhiên, nó đòi hỏi các máy chủ trong topology có cấu hình GTID nhất quán và dữ liệu nền mang theo metadata GTID chính xác.

### 6.1. Bật GTID trên topology mới

Với topology mới, có thể cấu hình trên source và tất cả replica:

```ini
[mysqld]
server_id=101
log_bin=/var/lib/mysql/mysql-bin
gtid_mode=ON
enforce_gtid_consistency=ON
binlog_format=ROW
```

Trên mỗi replica, đặt `server_id` khác nhau và thêm các tùy chọn cần cho vai trò replica, ví dụ `log_replica_updates=ON` nếu cần ghi lại transaction nhận từ source. `gtid_mode=ON` yêu cầu giao dịch trong topology đáp ứng điều kiện GTID; `enforce_gtid_consistency=ON` ngăn các thao tác không tương thích với GTID được thực thi theo cấu hình.

Sau khi khởi động, kiểm tra trên từng máy chủ:

```sql
SHOW VARIABLES LIKE 'gtid_mode';
SHOW VARIABLES LIKE 'enforce_gtid_consistency';
SELECT @@GLOBAL.server_uuid, @@GLOBAL.gtid_executed;
```

Không dùng cùng một `server_uuid` cho nhiều instance. Khi sao chép data directory vật lý để tạo replica, cần tuân thủ hướng dẫn của công cụ để instance mới có định danh phù hợp; không nhân bản nguyên trạng identity của source.

### 6.2. Chuyển hệ thống đang chạy sang GTID

Với topology đang hoạt động, không bật `gtid_mode=ON` một cách tùy tiện. MySQL cung cấp quy trình chuyển trạng thái qua các bước permissive để hệ thống có thời gian xử lý transaction cũ. Thực hiện trên tất cả máy chủ trong topology theo đúng thứ tự và tài liệu của phiên bản:

1. Bật `enforce_gtid_consistency=ON` sau khi xác minh workload không dùng các thao tác không tương thích.
2. Chuyển `gtid_mode` từ `OFF` sang `OFF_PERMISSIVE` trên tất cả máy chủ.
3. Chuyển tất cả máy chủ sang `ON_PERMISSIVE`.
4. Chờ các transaction anonymous đã bắt đầu hoàn tất; kiểm tra `ONGOING_ANONYMOUS_TRANSACTION_COUNT` trên từng máy chủ.
5. Chỉ khi số transaction anonymous đang chạy bằng 0 trên toàn topology, chuyển tất cả máy chủ sang `ON`.

Ví dụ kiểm tra trạng thái:

```sql
SHOW GLOBAL VARIABLES LIKE 'gtid_mode';
SHOW GLOBAL STATUS LIKE 'ONGOING_ANONYMOUS_TRANSACTION_COUNT';
```

Các bước thay đổi động có thể thực hiện bằng `SET GLOBAL` nếu phiên bản và quyền cho phép, đồng thời cần cập nhật cấu hình bền vững để trạng thái không bị mất sau restart. Nếu có nhiều source/replica hoặc channel phức tạp, lập kế hoạch chuyển đổi theo tài liệu chính thức và thử nghiệm trước trên môi trường tương đương.

### 6.3. Chuẩn bị dữ liệu nền có GTID

Khi dùng logical dump, có thể dùng `mysqldump` với `--set-gtid-purged=ON` để ghi thông tin GTID đã thực thi vào dump:

```bash
mysqldump \
  --host=source.example.net \
  --user=backup_user \
  --password \
  --single-transaction \
  --set-gtid-purged=ON \
  --routines \
  --events \
  --all-databases \
  > gtid-seed.sql
```

Tùy chọn này có thể đưa câu lệnh thiết lập `GTID_PURGED` vào dump. Chỉ restore kiểu dump này lên instance được chuẩn bị phù hợp, thường là instance mới chưa có tập GTID xung đột. Không nạp lại phần thiết lập GTID vào một replica đang hoạt động hoặc đã có lịch sử transaction riêng nếu chưa phân tích trạng thái. Với physical backup, dùng metadata GTID mà công cụ backup ghi lại.

### 6.4. Cấu hình auto-position

Sau khi restore dữ liệu nền và xác minh GTID, chạy trên replica:

```sql
CHANGE REPLICATION SOURCE TO
  SOURCE_HOST='source.example.net',
  SOURCE_PORT=3306,
  SOURCE_USER='repl',
  SOURCE_PASSWORD='replace-with-a-strong-secret',
  SOURCE_AUTO_POSITION=1,
  SOURCE_CONNECT_RETRY=10,
  SOURCE_SSL=1;

START REPLICA;
```

Khi `SOURCE_AUTO_POSITION=1`, không đồng thời chỉ định `SOURCE_LOG_FILE` hoặc `SOURCE_LOG_POS` trong cùng cấu hình kết nối. Replica gửi tập GTID đã thực thi; source tính toán những GTID replica còn thiếu và gửi các transaction tương ứng nếu binlog cần thiết vẫn còn.

Kiểm tra:

```sql
SHOW REPLICA STATUS\G
```

Quan sát `Auto_Position`, `Retrieved_Gtid_Set`, `Executed_Gtid_Set`, trạng thái hai luồng và các trường lỗi. Tên trường cụ thể có thể khác theo phiên bản. Tập GTID đã nhận và đã thực thi cần tiến triển phù hợp với tải ghi của source.

## 7. So sánh file/position và GTID

| Tiêu chí | File/position | GTID auto-position |
|---|---|---|
| Điểm bắt đầu | Tên file binlog và byte position | Tập transaction GTID đã thực thi |
| Cấu hình replica | `SOURCE_LOG_FILE`, `SOURCE_LOG_POS` | `SOURCE_AUTO_POSITION=1` |
| Metadata cần giữ | Tọa độ binlog chính xác tại snapshot | GTID set tại snapshot và dữ liệu nền tương ứng |
| Khi chuyển source | Phải xác định lại file/position phù hợp trên source mới | Có thể tự yêu cầu các GTID còn thiếu nếu topology và log đáp ứng điều kiện |
| Độ phức tạp | Dễ hiểu ở topology nhỏ, nhưng quản lý tọa độ thủ công | Thuận tiện hơn khi failover và quản lý nhiều transaction |
| Điều kiện | Binlog liên tục từ vị trí bắt đầu | GTID được bật và nhất quán trên các máy chủ liên quan; log chứa GTID còn sẵn |

GTID thường phù hợp cho topology mới và môi trường cần failover có kiểm soát. File/position vẫn hữu ích khi tương thích với hệ thống cũ hoặc khi cần cấu hình thủ công một điểm đọc cụ thể. Cả hai cách đều cần một bản dữ liệu nền nhất quán và retention binlog phù hợp.

## 8. Vận hành và giám sát replica

Sau khi replication chạy, cần theo dõi liên tục:

- Trạng thái receiver và applier; cảnh báo khi một luồng dừng.
- Lỗi kết nối, xác thực, TLS, quyền truy cập và lỗi đọc binlog.
- Độ trễ áp dụng transaction, tốc độ tạo relay log và dung lượng đĩa.
- Khoảng cách giữa vị trí đã đọc và đã áp dụng; với GTID, theo dõi tập GTID đã nhận và đã thực thi.
- Khả năng bắt kịp sau khi replica bị ngắt kết nối, đặc biệt khi source có retention ngắn.
- Tính nhất quán của dữ liệu bằng truy vấn kiểm tra hoặc công cụ đối chiếu phù hợp.

Có thể bật chế độ chỉ đọc trên replica để hạn chế ứng dụng ghi nhầm:

```sql
SET PERSIST read_only = ON;
SET PERSIST super_read_only = ON;
```

`SET PERSIST` phụ thuộc phiên bản MySQL. Nếu phiên bản không hỗ trợ, đặt các biến trong tệp cấu hình và restart theo quy trình. Quản trị viên có quyền cao vẫn có thể thay đổi dữ liệu khi chế độ này được tắt; vì vậy quyền DBA cần được kiểm soát.

Không chạy `RESET REPLICA` hoặc `RESET REPLICA ALL` chỉ để thử khắc phục lỗi. Các lệnh reset có thể xóa relay log hoặc metadata kết nối; cần hiểu rõ tác động và ghi lại cấu hình hiện tại trước khi thực hiện. Tương tự, không purge binlog trên source khi replica còn cần các file đó.

## 9. Xử lý lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `Replica_IO_Running: Connecting` hoặc `No` | Sai host/port, firewall, DNS, mật khẩu, TLS hoặc thiếu quyền replication | Kiểm tra kết nối từ replica, tài khoản, `Last_IO_Error` và error log source |
| Receiver báo không tìm thấy binlog | Source đã purge file replica cần đọc | Kiểm tra retention và vị trí; nếu thiếu log, dựng lại replica từ backup mới có tọa độ/GTID phù hợp |
| `Replica_SQL_Running: No` | Transaction áp dụng bị lỗi, xung đột khóa hoặc schema khác nhau | Đọc `Last_SQL_Error`, kiểm tra dữ liệu/schema và xác định transaction gây lỗi trước khi sửa |
| Duplicate key khi applier chạy | Replica đã có ghi cục bộ, dữ liệu seed sai hoặc transaction bị áp dụng không đúng điểm | Dừng thay đổi ghi ngoài dự kiến, xác định nguồn sai lệch và cân nhắc seed lại từ snapshot nhất quán |
| GTID auto-position không bắt kịp | GTID cần thiết không còn trong binlog source hoặc tập GTID không tương thích | Đối chiếu `gtid_executed`, binlog retention và metadata backup; thường cần seed lại nếu thiếu transaction |
| Replica có độ trễ tăng | Tải ghi cao, truy vấn áp dụng chậm, I/O hoặc CPU thiếu | Theo dõi worker, relay log, tài nguyên và transaction dài; tối ưu nguyên nhân gốc |

Không bỏ qua transaction lỗi bằng cách tăng bộ đếm skip hoặc chỉnh sửa GTID theo phỏng đoán. Bỏ qua một sự kiện có thể làm dữ liệu replica lệch vĩnh viễn so với source. Trước khi xử lý, xác định transaction, đánh giá tác động nghiệp vụ và có bản backup/snapshot để quay lại nếu cần.

## 10. Chuyển đổi vai trò và giới hạn của replication

Khi source gặp sự cố, replica có thể được chọn làm source mới nếu dữ liệu đã bắt kịp và quy trình failover cho phép. Trước khi promote:

1. Ngăn các client tiếp tục ghi vào source cũ hoặc cô lập source cũ để tránh split-brain.
2. Xác minh replica đã nhận và áp dụng hết transaction cần thiết theo mục tiêu RPO.
3. Xác định source mới duy nhất, cấu hình quyền ghi và cập nhật endpoint của ứng dụng.
4. Nếu dùng GTID, xác minh tập GTID và cấu hình auto-position cho các replica còn lại.
5. Theo dõi lỗi, độ trễ và dữ liệu sau chuyển đổi; lập kế hoạch tái tạo hoặc đưa source cũ trở lại topology.

Replication bất đồng bộ có thể mất các transaction chưa kịp truyền hoặc áp dụng khi source hỏng đột ngột. Nếu yêu cầu RPO gần bằng 0, cần đánh giá các cơ chế bổ sung như semi-synchronous replication, thiết kế quorum/failover và hạ tầng lưu trữ phù hợp. Không giả định replication bất đồng bộ bảo đảm không mất dữ liệu.

Một thao tác xóa nhầm hoặc dữ liệu hỏng có thể được ghi vào binlog và truyền sang replica. Do đó, vẫn cần full backup, lưu binlog ngoài máy chủ và diễn tập PITR. Replica là một thành phần của kiến trúc sẵn sàng, không phải bản backup lịch sử độc lập.

## 11. Checklist triển khai

- [ ] Đã xác định phiên bản MySQL và cú pháp replication tương thích.
- [ ] Mỗi source/replica có `server_id` duy nhất.
- [ ] Source đã bật binary logging và retention đủ dài.
- [ ] Tài khoản replication riêng, giới hạn host và dùng TLS.
- [ ] Replica đã được khởi tạo từ snapshot nhất quán.
- [ ] Metadata file/position hoặc GTID khớp với snapshot.
- [ ] Đã cấu hình đúng một phương thức định vị: file/position hoặc GTID auto-position.
- [ ] `START REPLICA` thành công; receiver và applier đều chạy.
- [ ] Không có `Last_IO_Error` hoặc `Last_SQL_Error` chưa xử lý.
- [ ] Đã cấu hình read-only phù hợp và giám sát lag/dung lượng relay log.
- [ ] Đã thử khôi phục hoặc dựng lại replica từ backup để xác nhận runbook.

## 12. Tự kiểm tra

1. Receiver và applier trên replica có nhiệm vụ gì? Relay log nằm ở đâu trong luồng dữ liệu?
2. Vì sao cần restore dữ liệu nền trước khi start replication?
3. `SOURCE_LOG_FILE` và `SOURCE_LOG_POS` phải lấy từ đâu, và vì sao không được lấy tọa độ ở một thời điểm khác snapshot?
4. `SOURCE_AUTO_POSITION=1` sử dụng GTID như thế nào để tìm transaction còn thiếu?
5. Vì sao GTID không loại bỏ yêu cầu giữ binary log?
6. Khi chuyển topology đang chạy sang GTID, vì sao phải qua các trạng thái permissive?
7. `log_replica_updates` có ích trong topology nhiều tầng như thế nào?
8. Nếu receiver chạy nhưng applier dừng, cần kiểm tra trường trạng thái và lỗi nào?
9. Vì sao không nên bỏ qua transaction replication lỗi mà chưa xác định nguyên nhân?
10. Hãy mô tả cách dựng một replica mới bằng file/position và cách làm tương tự bằng GTID auto-position.

Khi thiết kế, hãy bắt đầu từ bản backup nền và metadata của nó, sau đó chọn phương thức định vị phù hợp với topology. Sau khi start replication, xác minh cả luồng nhận lẫn luồng áp dụng, kiểm tra độ trễ và thử quy trình dựng lại. Một cấu hình chỉ được xem là vận hành tốt khi có thể duy trì đồng bộ, phát hiện lỗi và phục hồi replica trong giới hạn RPO/RTO đã đặt ra.
