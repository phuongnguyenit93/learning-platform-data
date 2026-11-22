# Snapshot nhất quán, Clone plugin và khởi tạo replica

Một replica mới cần bắt đầu từ bộ dữ liệu nhất quán với source. Nếu bản sao ban đầu thiếu một số giao dịch, chứa dữ liệu ở những thời điểm khác nhau hoặc có lịch sử GTID không khớp, replication có thể báo lỗi hoặc âm thầm tạo ra dữ liệu lệch. Vì vậy, bước quan trọng trước khi chạy replica là tạo snapshot đúng cách, khôi phục snapshot và thiết lập vị trí bắt đầu replication.

MySQL có hai hướng phổ biến để cấp dữ liệu ban đầu: tạo bản dump logic bằng `mysqldump` hoặc sao chép vật lý bằng Clone plugin. Dump logic linh hoạt, dễ di chuyển và cho phép xem nội dung SQL; Clone plugin thường nhanh hơn với bộ dữ liệu InnoDB lớn vì sao chép dữ liệu vật lý. Sau khi có dữ liệu, replica cần cấu hình replication bằng GTID auto-position hoặc bằng binary log file/position.

Bài học sử dụng cú pháp replication mới từ MySQL 8.0.23 trở lên và MySQL 8.4. Các tên lệnh cũ như `CHANGE MASTER TO`, `START SLAVE` và `SHOW SLAVE STATUS` đã được thay bằng cú pháp `SOURCE`/`REPLICA` trong các bản phát hành mới. Tùy chọn `mysqldump --source-data` có từ MySQL 8.0.26; trên bản cũ hơn, dùng `--master-data` tương ứng. Khi vận hành phiên bản khác, hãy đối chiếu tài liệu đúng phiên bản.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích snapshot nhất quán và giới hạn của `--single-transaction`.
- Tạo logical dump có metadata binlog/GTID phù hợp để khởi tạo replica.
- Cài đặt Clone plugin, phân quyền donor/recipient và chạy remote clone.
- Chọn GTID auto-position hoặc file/position khi kết nối replica với source.
- Kiểm tra replica sau khi khởi tạo và xử lý các lỗi thường gặp.
- Tránh các lỗi làm mất GTID history, thiếu binary log hoặc tạo dữ liệu không nhất quán.

## 1. Vì sao replica cần snapshot nhất quán?

Replication truyền các thay đổi từ source sang replica. Replica phải có một điểm xuất phát đại diện cho trạng thái dữ liệu tại một thời điểm xác định. Giả sử source có các bảng `customers`, `orders` và `order_items`. Nếu backup đọc `customers` trước một giao dịch nhưng đọc `orders` sau giao dịch đó, dữ liệu được khôi phục có thể không phản ánh cùng một trạng thái logic.

Một snapshot nhất quán đảm bảo các lần đọc trong quá trình backup nhìn thấy cùng một ảnh dữ liệu theo cơ chế snapshot của storage engine. Với InnoDB, consistent read trong transaction `REPEATABLE READ` cho phép `mysqldump --single-transaction` đọc dữ liệu tại cùng một snapshot trong suốt quá trình dump.

Snapshot dữ liệu cần đi kèm thông tin xác định nơi tiếp tục replication:

- Với file/position replication: tên binary log và byte position trên source tại thời điểm snapshot.
- Với GTID replication: tập GTID đã được thực thi và phản ánh trong snapshot.

Nếu chỉ có file SQL hoặc bản sao data directory mà không có metadata về điểm xuất phát, việc chọn giao dịch đầu tiên để áp dụng sẽ khó xác định và có thể gây bỏ sót hoặc áp dụng lặp giao dịch.

## 2. Tạo logical snapshot bằng mysqldump

### 2.1. Snapshot nhất quán với InnoDB

Ví dụ tạo dump toàn bộ database trên source MySQL 8.0.26 trở lên:

```bash
mysqldump \
  --all-databases \
  --single-transaction \
  --quick \
  --routines \
  --events \
  --triggers \
  --source-data=2 \
  --set-gtid-purged=ON \
  --user=backup_user \
  --password \
  > seed.sql
```

Ý nghĩa các tùy chọn:

| Tùy chọn | Tác dụng |
|---|---|
| `--all-databases` | Dump tất cả database mà tài khoản có quyền đọc. |
| `--single-transaction` | Tạo một consistent snapshot cho các bảng transactional như InnoDB. |
| `--quick` | Đọc và ghi từng phần dữ liệu để giảm bộ nhớ cần dùng. |
| `--routines` | Bao gồm stored procedure và function. |
| `--events` | Bao gồm Event Scheduler events. |
| `--triggers` | Bao gồm trigger; tùy chọn này thường đã bật mặc định nhưng ghi rõ giúp dễ đọc lệnh. |
| `--source-data=2` | Ghi thông tin binary log file/position của source dưới dạng câu lệnh được chú thích trong dump. |
| `--set-gtid-purged=ON` | Ghi GTID set của source vào dump để có thể thiết lập GTID history trên máy đích. |

`--source-data` được đổi tên từ `--master-data` trong các phiên bản MySQL mới. Giá trị `2` khiến câu lệnh `CHANGE REPLICATION SOURCE TO` chứa file/position được ghi dưới dạng comment để người vận hành xem và lựa chọn. Khi dùng `--source-data` cùng `--single-transaction`, `mysqldump` cần một global read lock ngắn ở đầu quá trình để chụp tọa độ log đồng bộ với snapshot; phần đọc dữ liệu sau đó tiếp tục trên consistent snapshot.

Tài khoản dump cần đủ quyền trên các đối tượng được xuất. `--source-data` cần binary log đang bật, quyền `REPLICATION CLIENT` để đọc trạng thái binary log và quyền `RELOAD`; khi `gtid_mode=ON` và dump đặt `--set-gtid-purged=ON|AUTO` cùng `--single-transaction`, máy chủ cũng yêu cầu `RELOAD` hoặc `FLUSH_TABLES`. Hãy cấp đúng quyền cần thiết cho tài khoản backup thay vì dùng tài khoản quản trị toàn quyền.

`--set-gtid-purged=ON` phù hợp khi đang xây dựng replica trong topology GTID và máy đích được chuẩn bị để nhận GTID set từ source. Nếu không sử dụng GTID, bỏ tùy chọn này và dùng file/position. Trên máy đích đã có GTID history, không áp dụng một dump có `GTID_PURGED` một cách máy móc: tập GTID có thể xung đột hoặc chồng lấp với trạng thái hiện tại.

Với GTID bật, dump cũng chứa `SET @@SESSION.sql_log_bin=0` để các câu lệnh nạp dữ liệu không sinh GTID mới trên máy đích; thay vào đó, máy đích ghi nhận GTID gốc từ source qua `GTID_PURGED`. Tài khoản restore cần quyền phù hợp để tắt binary logging ở phạm vi session. Điều này giúp GTID history của replica phản ánh đúng các giao dịch đã có trong snapshot.

### 2.2. Giới hạn của --single-transaction

`--single-transaction` tạo snapshot nhất quán cho InnoDB. Nó không đảm bảo snapshot nhất quán cho các bảng dùng storage engine không transactional như MyISAM hoặc MEMORY. Nếu database có các bảng này, cần một phương án backup phù hợp, chẳng hạn khóa ghi trong thời gian cần thiết hoặc dùng giải pháp backup vật lý hỗ trợ storage engine liên quan.

Trong lúc dump đang chạy, tránh các thao tác DDL trên các bảng được dump như `ALTER TABLE`, `DROP TABLE`, `RENAME TABLE` hoặc `TRUNCATE TABLE`. DDL có thể làm dump lỗi hoặc làm kết quả không còn phản ánh một snapshot nhất quán. Ngoài ra, `--single-transaction` không tự khóa ứng dụng khỏi thay đổi schema.

Dump toàn bộ database có thể chứa dữ liệu nhạy cảm, tài khoản và thông tin cấu hình hệ thống. Lưu file ở nơi có quyền truy cập giới hạn, mã hóa khi lưu trữ và kiểm tra dung lượng đĩa trước khi bắt đầu.

### 2.3. Khôi phục dump lên replica mới

Trước khi nạp dump, chuẩn bị một MySQL instance sạch hoặc một máy đích có trạng thái GTID đã được kiểm tra. Với GTID, bật các cấu hình cần thiết trước khi thiết lập replication:

```ini
[mysqld]
server_id=102
log_bin=replica-bin
gtid_mode=ON
enforce_gtid_consistency=ON
```

`server_id` phải duy nhất trong topology. Source và replica đều phải bật `gtid_mode=ON` và `enforce_gtid_consistency=ON` để sử dụng GTID auto-position. Nếu replica sẽ làm source cho replica khác, bật thêm `log_replica_updates=ON` để ghi các giao dịch nhận từ upstream vào binary log cục bộ.

Khôi phục dump:

```bash
mysql --user=restore_user --password < seed.sql
```

Khi dump có `SET @@GLOBAL.GTID_PURGED`, máy đích cần thỏa điều kiện để thiết lập tập GTID đó. Cách an toàn và dễ dự đoán nhất là dùng instance mới, đã bật GTID nhưng chưa có lịch sử giao dịch xung đột. Nếu dump được nạp vào server đã có dữ liệu hoặc GTID history, phải kiểm tra `@@GLOBAL.gtid_executed` và `@@GLOBAL.gtid_purged` trước khi quyết định cách hợp nhất; không xóa GTID history chỉ để làm cho lệnh import chạy qua.

## 3. Clone plugin: sao chép vật lý từ donor

Clone plugin sao chép dữ liệu vật lý từ một MySQL donor sang recipient. Cách này phù hợp khi cần cấp dữ liệu ban đầu nhanh cho một replica với bộ dữ liệu InnoDB lớn. Khác với dump logic, clone chuyển dữ liệu và metadata ở mức server/storage engine; nó không tạo một file SQL để chỉnh sửa từng câu lệnh.

Clone plugin được giới thiệu từ MySQL 8.0.17. Plugin cần được cài trên cả donor và recipient. Ví dụ trên Linux:

```sql
INSTALL PLUGIN clone SONAME 'mysql_clone.so';
```

Trên Windows, tên thư viện plugin có thể là `mysql_clone.dll`. Nếu plugin đã được cấu hình tự nạp khi khởi động, không cần cài lặp lại. Kiểm tra trạng thái:

```sql
SELECT PLUGIN_NAME, PLUGIN_STATUS
FROM INFORMATION_SCHEMA.PLUGINS
WHERE PLUGIN_NAME = 'clone';
```

Remote clone yêu cầu donor và recipient thuộc cùng MySQL server series và chạy cùng hệ điều hành/nền tảng. Ví dụ, không thể clone trực tiếp giữa MySQL 8.0 và 8.4, nhưng có thể clone giữa các bản phát hành trong cùng series 8.4. Kiểm tra yêu cầu về phiên bản, kiến trúc, cấu hình InnoDB và dung lượng lưu trữ trong tài liệu đúng phiên bản trước khi thực hiện.

### 3.1. Quyền trên donor và recipient

Tài khoản được recipient dùng để kết nối donor cần quyền `BACKUP_ADMIN` trên donor. Người thực hiện lệnh `CLONE INSTANCE` trên recipient cần quyền `CLONE_ADMIN`.

Trên donor, tạo tài khoản chỉ cho phép kết nối từ recipient:

```sql
CREATE USER 'clone_user'@'replica.example.internal'
IDENTIFIED BY 'replace_with_secret';

GRANT BACKUP_ADMIN ON *.*
TO 'clone_user'@'replica.example.internal';
```

Trên recipient, cấp quyền chạy clone cho tài khoản quản trị phù hợp:

```sql
GRANT CLONE_ADMIN ON *.*
TO 'replica_admin'@'localhost';
```

Hãy thay host bằng địa chỉ thực tế mà donor nhìn thấy từ recipient. Không dùng `%` nếu có thể giới hạn host cụ thể. Bảo vệ mật khẩu và ưu tiên TLS khi truyền dữ liệu qua mạng.

### 3.2. Cho phép donor và chạy clone

Trên recipient, thêm donor vào danh sách được phép:

```sql
SET GLOBAL clone_valid_donor_list = 'donor.example.internal:3306';
```

Sau đó chạy remote clone trên recipient:

```sql
CLONE INSTANCE FROM
  'clone_user'@'donor.example.internal':3306
IDENTIFIED BY 'replace_with_secret'
REQUIRE SSL;
```

`clone_valid_donor_list` là danh sách host và port mà recipient chấp nhận làm donor cho remote clone. Donor phải có trong danh sách này. Dùng `REQUIRE SSL` khi donor được kết nối qua mạng và đã cấu hình TLS phù hợp.

Clone thay thế dữ liệu của recipient bằng dữ liệu từ donor và recipient sẽ khởi động lại khi thao tác hoàn tất. Với remote clone mặc định, dữ liệu do người dùng tạo và binary log hiện có trên recipient bị xóa trước khi dữ liệu donor được sao chép. Vì vậy, chỉ chạy trên instance được dành riêng để làm replica mới; dữ liệu hiện có trên recipient có thể bị ghi đè. Đảm bảo đủ dung lượng đĩa, kết nối mạng ổn định, `max_allowed_packet` ít nhất 2 MB trên cả hai máy và donor có tài nguyên phục vụ quá trình sao chép. Clone plugin chỉ sao chép dữ liệu InnoDB; bảng MyISAM và CSV được tạo thành bảng rỗng trên recipient, còn dữ liệu của storage engine khác cần được xử lý bằng phương án riêng. Plugin cũng không sao chép cấu hình máy chủ hoặc file binary log/relay log; recipient giữ cấu hình riêng của nó.

Trong quy trình replication, donor phải là source hoặc replica thuộc topology mà recipient sẽ tham gia. Clone plugin trích xuất và chuyển cả binary log file/position lẫn tập `gtid_executed` từ donor sang recipient để xác định điểm tiếp tục. Các file binary log và relay log không được sao chép. Mặc định, các bảng metadata replication được sao chép cùng dữ liệu; vì vậy channel của donor có thể xuất hiện trên recipient. Hãy kiểm tra channel trước khi khởi động replication để xác định có thể tiếp tục channel hiện có hay phải cấu hình lại.

### 3.3. Theo dõi clone

Có thể theo dõi trạng thái và tiến độ qua Performance Schema:

```sql
SELECT * FROM performance_schema.clone_status\G

SELECT * FROM performance_schema.clone_progress;
```

`clone_status` cho biết trạng thái của thao tác clone gần nhất, còn `clone_progress` cung cấp tiến độ theo từng stage. Khi clone thất bại, đọc mã lỗi và thông báo lỗi tại đây cùng error log của máy chủ. Không khởi chạy lặp lại ngay khi chưa xác định nguyên nhân, vì thao tác có thể đã thay đổi trạng thái dữ liệu recipient.

Sau khi clone, có thể kiểm tra tọa độ được chuyển từ donor:

```sql
SELECT BINLOG_FILE, BINLOG_POSITION
FROM performance_schema.clone_status;

SELECT @@GLOBAL.gtid_executed;
```

Nếu dùng file/position, lấy đúng `BINLOG_FILE` và `BINLOG_POSITION` này để cấu hình channel mới. Nếu dùng GTID auto-position, kiểm tra `gtid_executed` và bảo đảm GTID mode phù hợp ở cả hai phía. Source phải giữ các binary log cần thiết cho replica bắt kịp từ thời điểm clone đến khi kết nối replication; nếu log đã bị purge, cần provision lại từ snapshot mới hoặc nguồn log lưu trữ.

## 4. Chọn logical dump hay Clone plugin

| Tiêu chí | Logical dump (`mysqldump`) | Clone plugin |
|---|---|---|
| Cách sao chép | Đọc dữ liệu và xuất câu lệnh SQL | Sao chép vật lý dữ liệu InnoDB |
| Tính linh hoạt | Có thể lọc database/table, xem hoặc chỉnh sửa dump | Sao chép instance theo phạm vi plugin hỗ trợ |
| Tốc độ với dữ liệu lớn | Thường chậm hơn do xuất và nạp SQL | Thường nhanh hơn vì sao chép vật lý |
| Storage engine | Có thể dump dữ liệu từ nhiều engine được hỗ trợ bởi mysqldump | Clone plugin tập trung vào InnoDB; engine khác cần xử lý riêng |
| Metadata replication | Có thể ghi file/position và GTID vào dump | Cần kiểm tra GTID history và metadata sau clone |
| Phiên bản/nền tảng | Dễ chuyển đổi hơn giữa các môi trường tương thích SQL | Có yêu cầu tương thích phiên bản và nền tảng nghiêm ngặt hơn |
| Phù hợp | Di chuyển linh hoạt, database nhỏ/vừa, chọn lọc dữ liệu | Provisioning nhanh cho replica có dữ liệu InnoDB lớn |

Không có một lựa chọn tối ưu cho mọi hệ thống. Hãy dựa trên kích thước dữ liệu, storage engine, yêu cầu downtime, tính tương thích phiên bản, chính sách bảo mật và khả năng kiểm tra snapshot.

## 5. Cấu hình replication bằng GTID auto-position

GTID (Global Transaction Identifier) gán một định danh duy nhất cho mỗi giao dịch được commit và ghi vào binary log trên source. Khi replica dùng `SOURCE_AUTO_POSITION=1`, nó gửi tập GTID đã thực thi cho source; source chỉ gửi các giao dịch mà replica còn thiếu. Nhờ đó, không cần tự chọn file/position khi replica đã có GTID history chính xác.

### 5.1. Chuẩn bị source

Trên source, bảo đảm binary log và GTID được bật. Tạo tài khoản replication:

```sql
CREATE USER 'repl'@'replica.example.internal'
IDENTIFIED BY 'replace_with_secret';

GRANT REPLICATION SLAVE ON *.*
TO 'repl'@'replica.example.internal';
```

Tên quyền `REPLICATION SLAVE` vẫn được dùng trong MySQL 8.0/8.4 cho tài khoản đọc binary log phục vụ replication, dù các lệnh quản lý đã chuyển sang thuật ngữ `SOURCE` và `REPLICA`. Giới hạn host của tài khoản, dùng mật khẩu riêng và bật TLS cho kết nối replication theo yêu cầu bảo mật.

### 5.2. Kết nối replica với source

Sau khi dữ liệu ban đầu đã được nạp và GTID history đúng, cấu hình channel mặc định trên replica:

```sql
CHANGE REPLICATION SOURCE TO
  SOURCE_HOST = 'source.example.internal',
  SOURCE_PORT = 3306,
  SOURCE_USER = 'repl',
  SOURCE_PASSWORD = 'replace_with_secret',
  SOURCE_AUTO_POSITION = 1;

START REPLICA;
```

Trong môi trường production, cân nhắc cấu hình SSL cho channel và lưu thông tin xác thực theo quy trình quản lý bí mật của hệ thống. Nếu replica đang có cấu hình channel cũ, hãy dừng và kiểm tra trạng thái trước khi thay đổi. `RESET REPLICA ALL` xóa metadata kết nối và relay log của channel; chỉ dùng khi chủ đích loại bỏ cấu hình cũ. Lệnh này không phải cách để xóa GTID execution history.

### 5.3. GTID history quyết định giao dịch nào được gửi

Khi `SOURCE_AUTO_POSITION=1`, source so sánh GTID set của chính nó với `gtid_executed` do replica báo. Các GTID đã được thực thi trên replica sẽ không được gửi lại. Vì vậy, snapshot phải phản ánh chính xác dữ liệu và GTID set tương ứng tại cùng một thời điểm.

Nếu máy đích có GTID ngoài luồng (errant transactions), hoặc `GTID_PURGED` được thiết lập sai, auto-position có thể bỏ qua giao dịch cần thiết, gặp lỗi hoặc tạo ra trạng thái không tương thích. Không chạy `RESET MASTER` hoặc lệnh xóa binary log/GTID history để xử lý một cách tùy tiện. Trước khi sửa GTID set, phải xác định giao dịch nào đã được áp dụng và đối chiếu dữ liệu thực tế.

## 6. Cấu hình replication bằng file/position

Nếu topology không dùng GTID, hoặc cần tiếp tục từ tọa độ được ghi trong dump, có thể cấu hình bằng binary log file và position:

```sql
CHANGE REPLICATION SOURCE TO
  SOURCE_HOST = 'source.example.internal',
  SOURCE_PORT = 3306,
  SOURCE_USER = 'repl',
  SOURCE_PASSWORD = 'replace_with_secret',
  SOURCE_LOG_FILE = 'binlog.000123',
  SOURCE_LOG_POS = 456789;

START REPLICA;
```

`SOURCE_LOG_FILE` và `SOURCE_LOG_POS` phải là tọa độ được ghi nhận tại đúng thời điểm tạo snapshot. Không lấy vị trí hiện tại của source sau khi dump hoàn tất, vì source có thể đã phát sinh thêm giao dịch trong lúc dump. Với `mysqldump --source-data=2`, tọa độ được ghi trong phần comment của file dump; hãy đọc và dùng đúng giá trị đó.

File/position đơn giản để hiểu nhưng cần quản lý tọa độ chính xác khi khôi phục hoặc chuyển source. Nếu source purge file log chứa vị trí replica cần đọc, replica sẽ không thể bắt kịp từ tọa độ đó; cần tạo snapshot mới hoặc khôi phục từ nguồn log lưu trữ khác.

## 7. Hoàn tất và xác minh replica

Sau khi `START REPLICA`, kiểm tra trạng thái:

```sql
SHOW REPLICA STATUS\G
```

Các trường cần đọc:

| Trường | Cách diễn giải |
|---|---|
| `Source_Host` | Source mà replica đang kết nối. |
| `Replica_IO_Running` | Luồng nhận binary log từ source; thường cần là `Yes`. |
| `Replica_SQL_Running` | Luồng áp dụng relay log; thường cần là `Yes`. |
| `Auto_Position` | `1` khi channel dùng GTID auto-position. |
| `Retrieved_Gtid_Set` | GTID đã nhận từ source. |
| `Executed_Gtid_Set` | GTID đã thực thi trên replica. |
| `Last_IO_Error` / `Last_SQL_Error` | Lỗi gần nhất của luồng nhận hoặc luồng áp dụng. |
| `Seconds_Behind_Source` | Ước lượng độ trễ; `NULL` có thể xuất hiện khi luồng SQL không chạy hoặc chưa có thông tin phù hợp. |

Hai luồng I/O và SQL chạy không đồng nghĩa dữ liệu đã bắt kịp hoàn toàn. Hãy kiểm tra lỗi, GTID set, lag, số lượng worker và dữ liệu nghiệp vụ. `Seconds_Behind_Source=0` tại một thời điểm cũng không phải bằng chứng duy nhất rằng replica luôn đồng bộ.

Có thể xem thêm trạng thái worker trong Performance Schema:

```sql
SELECT *
FROM performance_schema.replication_applier_status_by_worker;

SELECT *
FROM performance_schema.replication_connection_status;
```

Đối chiếu một số truy vấn chỉ đọc giữa source và replica, chẳng hạn số bản ghi theo khoảng thời gian hoặc checksum theo bảng. Chọn phép kiểm tra không gây tải quá lớn và tính đến độ trễ replication trong lúc so sánh.

Sau khi xác minh, cấu hình replica chỉ đọc để giảm nguy cơ ghi nhầm dữ liệu trực tiếp:

```sql
SET PERSIST read_only = ON;
SET PERSIST super_read_only = ON;
```

`super_read_only` chặn cả các ghi từ tài khoản có quyền `SUPER` (hoặc quyền tương đương trong phiên bản cụ thể), trong khi replication applier vẫn có thể áp dụng giao dịch từ source. Chỉ bật nếu vai trò của instance là replica đọc; ứng dụng quản trị hoặc failover có thể cần quy trình thay đổi chế độ rõ ràng.

## 8. Lỗi thường gặp khi khởi tạo replica

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Replica báo thiếu binary log | Source đã purge log cần thiết | Tạo snapshot mới hoặc lấy log từ kho lưu trữ; kiểm tra retention. |
| `SOURCE_AUTO_POSITION=1` báo lỗi GTID | GTID mode chưa bật, GTID set xung đột hoặc thiếu giao dịch cần thiết | Kiểm tra `gtid_mode`, `enforce_gtid_consistency`, `gtid_executed` và `gtid_purged` ở hai phía. |
| Replica kết nối source thất bại | Sai host, port, mật khẩu, quyền hoặc TLS | Kiểm tra tài khoản replication, host match, firewall và chứng thư. |
| Dump bị lỗi khi đang chạy | DDL thay đổi bảng trong lúc snapshot hoặc quyền backup không đủ | Xem error log, kiểm soát DDL trong thời gian dump và rà soát quyền. |
| Dữ liệu source/replica khác nhau | Snapshot không nhất quán, bỏ sót bảng/engine hoặc có ghi trực tiếp trên replica | Xác định thời điểm snapshot, storage engine, GTID history và log ứng dụng. |
| Clone plugin không chạy | Plugin chưa cài, donor không được allowlist hoặc thiếu quyền | Kiểm tra `INFORMATION_SCHEMA.PLUGINS`, `clone_valid_donor_list`, `CLONE_ADMIN` và `BACKUP_ADMIN`. |
| Clone thất bại do môi trường | Phiên bản/nền tảng không tương thích hoặc thiếu dung lượng | Kiểm tra điều kiện clone, không gian đĩa, network và `performance_schema.clone_status`. |
| Replica SQL thread dừng | Giao dịch gây lỗi, schema không khớp hoặc dữ liệu đã bị sửa cục bộ | Đọc `Last_SQL_Error`, kiểm tra worker status và xử lý nguyên nhân trước khi chạy lại. |

Không bỏ qua một giao dịch lỗi bằng cách nhảy GTID hoặc tăng file/position chỉ để làm replica chạy tiếp. Trước hết cần xác định giao dịch có thể bỏ qua an toàn hay không, dữ liệu nào sẽ bị thiếu và cách tái đồng bộ nếu đã lệch.

## 9. Quy trình thực hành: tạo replica mới

Giả sử có source `db-source` và máy đích `db-replica`. Chọn một trong hai phương pháp cấp dữ liệu ban đầu, sau đó dùng chung quy trình cấu hình replication.

### Phương án A: logical dump

1. Kiểm tra `log_bin`, GTID mode và binary log retention trên source.
2. Dừng hoặc kiểm soát DDL trong cửa sổ dump; xác nhận các bảng cần sao chép dùng InnoDB nếu chọn `--single-transaction`.
3. Chạy `mysqldump` với `--single-transaction`, `--source-data=2` và `--set-gtid-purged=ON` nếu topology dùng GTID.
4. Chuẩn bị instance replica mới với `server_id` duy nhất và cấu hình GTID phù hợp.
5. Khôi phục dump, kiểm tra `gtid_executed` và metadata binlog trong file dump.
6. Cấu hình `CHANGE REPLICATION SOURCE TO` bằng `SOURCE_AUTO_POSITION=1` hoặc tọa độ file/position.
7. Chạy `START REPLICA`, kiểm tra hai luồng và đối chiếu dữ liệu.

### Phương án B: Clone plugin

1. Xác nhận donor có dữ liệu InnoDB nhất quán và có GTID history phù hợp với source dự kiến.
2. Cài Clone plugin trên donor và recipient; tạo donor user có `BACKUP_ADMIN` và recipient user có `CLONE_ADMIN`.
3. Thêm donor vào `clone_valid_donor_list` trên recipient và xác nhận TLS.
4. Chạy `CLONE INSTANCE` trên recipient; theo dõi `clone_status` và `clone_progress`.
5. Chờ recipient khởi động lại; kiểm tra `server_id`, `server_uuid`, plugin, dữ liệu và GTID history.
6. Kiểm tra channel được sao chép từ donor; channel GTID auto-position có thể tiếp tục nếu donor là replica trong cùng topology và cấu hình vẫn phù hợp. Nếu cần channel khác, dừng và cấu hình lại có chủ đích.
7. Nếu tạo channel mới, dùng `@@GLOBAL.gtid_executed` cho GTID auto-position hoặc `BINLOG_FILE`/`BINLOG_POSITION` trong `performance_schema.clone_status` cho file/position.
8. Chạy `START REPLICA` và xác minh luồng nhận, luồng áp dụng cùng dữ liệu nghiệp vụ.

Trong cả hai phương án, source phải giữ binary log đủ lâu để replica mới bắt kịp. Nếu thời gian tạo snapshot, truyền dữ liệu và khởi tạo kéo dài hơn thời gian lưu log, source có thể purge mất các giao dịch replica cần nhận. Hãy tính cửa sổ provisioning vào chính sách `binlog_expire_logs_seconds` và kho lưu trữ binary log.

## 10. Nguyên tắc vận hành an toàn

1. **Chốt điểm snapshot và tọa độ replication cùng lúc.** Dữ liệu và metadata GTID/file-position phải mô tả cùng một trạng thái source.
2. **Biết giới hạn storage engine.** `--single-transaction` phù hợp với InnoDB; Clone plugin sao chép dữ liệu InnoDB. Xử lý riêng các bảng engine khác.
3. **Kiểm soát DDL trong lúc dump.** Snapshot transaction không bảo vệ dump khỏi mọi thay đổi schema.
4. **Giữ binary log đủ lâu.** Thời gian retention phải bao phủ thời gian tạo, truyền, khôi phục snapshot và replica catch-up.
5. **Không trộn GTID history.** Tránh nạp dump lên máy đã có giao dịch riêng hoặc xóa GTID set để chữa lỗi một cách tùy tiện.
6. **Dùng tài khoản riêng và quyền tối thiểu.** Tách quyền backup/clone khỏi tài khoản ứng dụng và giới hạn host kết nối.
7. **Kiểm tra phiên bản và nền tảng.** Đặc biệt quan trọng khi dùng Clone plugin.
8. **Xác minh sau khi chạy.** Kiểm tra luồng I/O, SQL, GTID, lỗi worker và dữ liệu nghiệp vụ.
9. **Giới hạn ghi trên replica.** Dùng `read_only` và `super_read_only` khi phù hợp với vai trò của máy.

## 11. Bài tập tự kiểm tra

1. Vì sao `mysqldump --single-transaction` không đảm bảo snapshot nhất quán cho bảng MyISAM?
2. `--source-data=2` và `--set-gtid-purged=ON` cung cấp hai loại metadata nào khác nhau?
3. Trên Clone plugin, quyền `BACKUP_ADMIN` thuộc về tài khoản trên máy nào và `CLONE_ADMIN` thuộc về tài khoản trên máy nào?
4. Vì sao phải kiểm tra `gtid_executed` trên replica trước khi bật `SOURCE_AUTO_POSITION=1`?
5. Nếu `Replica_IO_Running=Yes` nhưng `Replica_SQL_Running=No`, cần kiểm tra trường nào trước?
6. Vì sao không nên dùng `RESET REPLICA ALL` để xóa GTID history?

**Gợi ý đáp án:** (1) MyISAM không hỗ trợ consistent snapshot theo transaction; cần khóa ghi hoặc phương án backup khác. (2) `--source-data=2` ghi binary log file/position; `--set-gtid-purged=ON` ghi GTID set đã thực thi. (3) Donor cấp `BACKUP_ADMIN` cho tài khoản mà recipient dùng để kết nối; recipient cấp `CLONE_ADMIN` cho người chạy lệnh clone. (4) GTID set quyết định source sẽ gửi giao dịch nào; GTID sai có thể làm bỏ qua giao dịch hoặc gây lỗi. (5) `Last_SQL_Error` và trạng thái trong `replication_applier_status_by_worker`. (6) `RESET REPLICA ALL` xóa metadata channel/relay log, không xóa lịch sử GTID đã thực thi.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual: mysqldump](https://dev.mysql.com/doc/refman/8.4/en/mysqldump.html)
- [MySQL 8.4 Reference Manual: Consistent Nonlocking Reads](https://dev.mysql.com/doc/refman/8.4/en/innodb-consistent-read.html)
- [MySQL 8.4 Reference Manual: Clone Plugin](https://dev.mysql.com/doc/refman/8.4/en/clone-plugin.html)
- [MySQL 8.4 Reference Manual: Remote Cloning](https://dev.mysql.com/doc/refman/8.4/en/clone-plugin-remote.html)
- [MySQL 8.4 Reference Manual: Cloning for Replication](https://dev.mysql.com/doc/refman/8.4/en/clone-plugin-replication.html)
- [MySQL 8.4 Reference Manual: Clone Plugin Limitations](https://dev.mysql.com/doc/refman/8.4/en/clone-plugin-limitations.html)
- [MySQL 8.4 Reference Manual: Setting Up Replication with Existing Data](https://dev.mysql.com/doc/refman/8.4/en/replication-setup-replicas.html)
- [MySQL 8.4 Reference Manual: Replication with Global Transaction Identifiers](https://dev.mysql.com/doc/refman/8.4/en/replication-gtids.html)
- [MySQL 8.4 Reference Manual: CHANGE REPLICATION SOURCE TO](https://dev.mysql.com/doc/refman/8.4/en/change-replication-source-to.html)
