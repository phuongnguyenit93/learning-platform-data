# Replication và GTID

## Đứt kết nối, lỗi apply, giao dịch thiếu/thừa và kế hoạch sửa có kiểm chứng

MySQL replication có thể ngừng tiến triển vì hai nhóm nguyên nhân khác nhau: replica không lấy được sự kiện mới từ source, hoặc đã nhận được sự kiện nhưng không áp dụng được vào dữ liệu cục bộ. Ngoài ra, dữ liệu và lịch sử GTID giữa hai máy chủ có thể lệch nhau dù kết nối hiện đang hoạt động. Muốn sửa đúng, người vận hành cần xác định lỗi nằm ở đường truyền, relay log, applier, dữ liệu hay lịch sử giao dịch.

Trong module `DATABASE_MYSQL`, bạn học cách làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction và kiểm soát đồng thời. Bạn cũng thực hành đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Replication kết nối các kỹ năng này với vận hành phân tán: phải hiểu transaction, constraint, quyền, backup và trạng thái dữ liệu trước khi cho replica chạy tiếp.

Bài này trình bày cách phân loại lỗi kết nối và lỗi apply, thu thập bằng chứng, so sánh GTID để tìm giao dịch thiếu/thừa, chọn phương án sửa hoặc dựng lại replica, rồi xác minh kết quả. Các ví dụ dùng cú pháp MySQL 8.0.22 trở lên; với MySQL 5.7 và các bản 8.0 cũ hơn, tên lệnh còn dùng `SLAVE`/`MASTER`. Hãy đối chiếu phiên bản thực tế trước khi chạy lệnh.

### 1. Hiểu hai luồng replication

Trong replication bất đồng bộ, replica có hai luồng công việc chính:

1. **Receiver (I/O thread):** kết nối đến source, đọc binary log events và ghi chúng vào relay log trên replica.
2. **Applier (SQL thread hoặc worker):** đọc relay log và thực thi các transaction trên replica.

Khi receiver dừng, replica không nhận thêm sự kiện mới. Khi applier dừng, sự kiện có thể vẫn được nhận và tích lũy trong relay log nhưng dữ liệu trên replica không tiến triển. Hai tình trạng này cần cách điều tra khác nhau.

`SHOW REPLICA STATUS` cung cấp ảnh chụp trạng thái tổng quan:

```sql
SHOW REPLICA STATUS\G
```

Các trường quan trọng:

| Trường | Ý nghĩa khi điều tra |
|---|---|
| `Replica_IO_Running` | `Yes` cho biết receiver đang chạy; `Connecting` thường cho thấy đang thử kết nối; `No` cho biết luồng đã dừng |
| `Replica_SQL_Running` | `Yes` cho biết applier đang chạy; `No` thường đi kèm lỗi apply hoặc thao tác dừng có chủ đích |
| `Last_IO_Errno`, `Last_IO_Error` | Mã và nội dung lỗi của receiver gần nhất |
| `Last_SQL_Errno`, `Last_SQL_Error` | Mã và nội dung lỗi của applier gần nhất |
| `Source_Host`, `Source_Port`, `Source_UUID` | Nhận diện source mà replica đang theo dõi |
| `Retrieved_Gtid_Set` | GTID đã được nhận vào relay log trên channel |
| `Executed_Gtid_Set` | Tập GTID đã thực thi trên replica; trường này phản ánh trạng thái máy chủ và có thể bao gồm nhiều nguồn/channel |
| `Seconds_Behind_Source` | Ước lượng độ trễ theo timestamp; không phải bằng chứng duy nhất rằng replica đã đồng bộ |

Trên MySQL 5.7 hoặc bản 8.0 chưa có tên mới, dùng:

```sql
SHOW SLAVE STATUS\G
```

Một số phiên bản hiển thị tên trường với tiền tố `Slave_` thay cho `Replica_`. Nếu có nhiều channel, xem riêng từng channel bằng cú pháp `FOR CHANNEL` được phiên bản hỗ trợ.

Không chỉ nhìn `Seconds_Behind_Source`. Giá trị có thể là `NULL` khi applier không chạy hoặc chưa có thông tin phù hợp; nó cũng có thể không phản ánh đầy đủ độ trễ khi có transaction dài hoặc nhiều worker. Hãy kết hợp trạng thái hai luồng, GTID, relay log, heartbeat và thời điểm commit.

### 2. Thu thập bằng chứng trước khi sửa

Khi replication lỗi, việc đầu tiên là lưu trạng thái để có thể tái dựng nguyên nhân. Không chạy `RESET REPLICA`, xóa relay log, bỏ qua transaction hay chỉnh GTID trước khi thu thập bằng chứng.

Trên replica, lưu output:

```sql
SELECT VERSION() AS mysql_version,
       @@server_uuid AS server_uuid,
       @@GLOBAL.gtid_mode AS gtid_mode,
       @@GLOBAL.gtid_executed AS gtid_executed,
       @@GLOBAL.gtid_purged AS gtid_purged,
       @@GLOBAL.read_only AS read_only,
       @@GLOBAL.super_read_only AS super_read_only;

SHOW REPLICA STATUS\G
SHOW BINARY LOGS;
```

Trên MySQL có Performance Schema replication tables, kiểm tra lỗi kết nối:

```sql
SELECT
  CHANNEL_NAME,
  SERVICE_STATE,
  LAST_ERROR_NUMBER,
  LAST_ERROR_MESSAGE,
  LAST_ERROR_TIMESTAMP
FROM performance_schema.replication_connection_status;
```

Kiểm tra lỗi của coordinator và các applier worker:

```sql
SELECT
  CHANNEL_NAME,
  SERVICE_STATE,
  LAST_ERROR_NUMBER,
  LAST_ERROR_MESSAGE,
  LAST_ERROR_TIMESTAMP
FROM performance_schema.replication_applier_status_by_coordinator;

SELECT
  CHANNEL_NAME,
  WORKER_ID,
  SERVICE_STATE,
  APPLYING_TRANSACTION,
  LAST_APPLIED_TRANSACTION,
  LAST_ERROR_NUMBER,
  LAST_ERROR_MESSAGE,
  LAST_ERROR_TIMESTAMP
FROM performance_schema.replication_applier_status_by_worker
WHERE LAST_ERROR_NUMBER <> 0
   OR APPLYING_TRANSACTION <> '';
```

Các bảng và cột Performance Schema có thể khác theo phiên bản và cấu hình. Nếu một truy vấn không chạy, kiểm tra schema của phiên bản hiện tại và dùng `SHOW REPLICA STATUS` cùng error log làm nguồn đối chiếu.

Ghi lại tối thiểu:

- Thời điểm bắt đầu sự cố, thời điểm lỗi đầu tiên và thay đổi gần nhất trên source/replica.
- Channel bị lỗi, tên source, trạng thái receiver/applier và các error number/message.
- `Retrieved_Gtid_Set`, `Executed_Gtid_Set`, `gtid_executed`, `gtid_purged` và tọa độ file/position nếu dùng file-position replication.
- Relay log file/position, transaction đang áp dụng và worker phát sinh lỗi nếu có.
- Error log MySQL, log mạng/TLS và thay đổi cấu hình hoặc quyền gần thời điểm sự cố.
- Tình trạng dữ liệu của bảng liên quan, backup gần nhất và binlog/archive còn sẵn.

Lưu các giá trị tại cùng một khoảng thời gian gần nhau. Nếu source tiếp tục ghi transaction trong lúc bạn lấy trạng thái replica, hai GTID set có thể thay đổi giữa các lần truy vấn; hãy ghi timestamp để tránh so sánh hai ảnh chụp không đồng thời.

### 3. Lỗi receiver: mất kết nối hoặc không đọc được binlog

Receiver thường gặp lỗi do mạng, DNS, tường lửa, TLS, tài khoản replication, cấu hình source hoặc binary log không còn tồn tại.

| Dấu hiệu | Nguyên nhân cần kiểm tra |
|---|---|
| `Replica_IO_Running: Connecting` kéo dài | Source không truy cập được, sai host/port, DNS, firewall hoặc source không lắng nghe |
| Lỗi xác thực như `Access denied` | Sai mật khẩu, tài khoản replication không khớp host, thiếu quyền `REPLICATION SLAVE`/quyền tương ứng |
| Lỗi TLS/SSL | CA, certificate, hostname, expiry hoặc cấu hình TLS hai phía không khớp |
| Source UUID hoặc server identity bất thường | Replica đang kết nối nhầm instance, clone máy chủ không đổi `server_uuid` đúng cách hoặc topology bị cấu hình sai |
| Lỗi 1236 / không tìm thấy binlog | Source đã purge/reset file replica cần, tên file/position sai hoặc archive không đầy đủ |
| Receiver chạy nhưng relay log không tăng | Source không phát sinh sự kiện mới, receiver bị nghẽn hoặc có vấn đề lưu trữ/ghi relay log |

Quy trình điều tra:

1. Xác nhận `Source_Host`, `Source_Port`, `Source_UUID` là đúng source dự kiến.
2. Kiểm tra kết nối TCP từ replica đến source, DNS, route, firewall và trạng thái MySQL listener.
3. Kiểm tra tài khoản replication trên source, host pattern, quyền và phương thức xác thực.
4. Kiểm tra TLS hai phía: CA tin cậy, certificate còn hạn, tên máy chủ và yêu cầu mã hóa.
5. Đối chiếu danh sách binlog trên source với file/position hoặc GTID replica cần nhận.
6. Xem log source và replica để phân biệt lỗi mạng với việc source đã xóa log cần thiết.

Nếu source vẫn giữ đủ binlog và GTID, khắc phục mạng/quyền/TLS rồi receiver thường có thể tiếp tục từ vị trí đã lưu. Nếu source đã purge file replica cần, kết nối trở lại không thể tự tạo ra phần lịch sử đã mất. Tìm bản archive binlog đã xác minh hoặc chuẩn bị dựng lại replica từ một backup nhất quán mới.

Sau khi khắc phục, có thể khởi động riêng receiver nếu cần:

```sql
START REPLICA IO_THREAD;
```

Với phiên bản cũ, cú pháp tương ứng là `START SLAVE IO_THREAD`. Chỉ chạy sau khi đã xác định nguyên nhân và bảo đảm source/file cần thiết có sẵn. Không liên tục restart thread khi chưa sửa lỗi gốc; việc đó chỉ làm log nhiễu và che thời điểm lỗi thật.

### 4. Lỗi applier: đã nhận nhưng không áp dụng được

Applier có thể dừng khi transaction từ source vi phạm trạng thái dữ liệu hoặc schema trên replica. Hai mã lỗi phổ biến khi dùng row-based replication là:

- **1032 — Can't find record:** sự kiện `UPDATE` hoặc `DELETE` cần một hàng nhưng replica không tìm thấy hàng tương ứng.
- **1062 — Duplicate entry:** sự kiện `INSERT` tạo khóa đã tồn tại trên replica.

Hai lỗi này thường báo hiệu dữ liệu hai bên đã lệch trước khi transaction gặp lỗi. Nguyên nhân có thể là ghi trực tiếp vào replica, sửa dữ liệu thủ công, filter replication, restore không đúng thời điểm, thiếu transaction trước đó hoặc schema khác nhau.

Các nguyên nhân khác gồm table/column không tồn tại, khác kiểu dữ liệu, khác collation, constraint hoặc foreign key không tương thích, thiếu storage engine/plugin và câu lệnh DDL không chạy được. Với statement-based replication, hành vi không xác định hoặc khác môi trường cũng có thể tạo kết quả khác.

Khi `Replica_SQL_Running` là `No`:

1. Lưu `Last_SQL_Error`, worker ID, `APPLYING_TRANSACTION` và GTID của transaction gây lỗi nếu có.
2. Kiểm tra schema nguồn/replica bằng `SHOW CREATE TABLE`; đối chiếu column, index, constraint, engine, charset và collation.
3. Dùng `mysqlbinlog` để xem transaction nguồn. Với row-based event, có thể giải mã để xem dữ liệu trước/sau ở dạng dễ đọc.
4. Kiểm tra hàng liên quan trên cả source và replica bằng khóa chính hoặc unique key.
5. Xác định vì sao trạng thái dữ liệu khác nhau và liệu có transaction trước đó bị thiếu hay ghi ngoài replication.
6. Chọn phương án sửa dữ liệu, bỏ qua một transaction đã được chứng minh là không cần áp dụng, hoặc dựng lại replica.

Ví dụ đọc binlog trên file đã lưu:

```bash
mysqlbinlog --base64-output=DECODE-ROWS -vv binlog.000123
```

Nếu đã xác định GTID gây lỗi, có thể lọc để xem phạm vi transaction bằng `mysqlbinlog --include-gtids='uuid:transaction_number'` trên file binlog tương ứng. Tên file và GTID phải lấy từ bằng chứng thật; không suy đoán từ thời gian hoặc số thứ tự lỗi.

Với multi-threaded applier, lỗi có thể xuất hiện ở một worker trong khi coordinator quản lý thứ tự và dependency giữa các transaction. Hãy xem `replication_applier_status_by_worker` và coordinator table; đừng chỉ đọc một dòng tổng quát rồi bỏ qua worker đang lỗi. Việc xử lý gap của MTS phải theo đúng thủ tục của phiên bản và trạng thái worker.

### 5. So sánh giao dịch thiếu và thừa bằng GTID

GTID giúp so sánh tập giao dịch đã thực thi. Giả sử:

- `S` là `gtid_executed` của source tại thời điểm chụp.
- `R` là `gtid_executed` của replica tại thời điểm tương ứng.

Khi đó:

- `GTID_SUBTRACT(S, R)` cho biết giao dịch source đã thực thi nhưng replica chưa có trong tập executed của nó.
- `GTID_SUBTRACT(R, S)` cho biết giao dịch replica đã thực thi nhưng không có trong tập executed của source được so sánh.

Ví dụ:

```sql
-- Lấy hai giá trị từ cùng một khoảng thời gian đối chiếu.
SET @source_gtids = 'uuid-a:1-1200';
SET @replica_gtids = 'uuid-a:1-1190';

SELECT
  GTID_SUBTRACT(@source_gtids, @replica_gtids)
    AS missing_on_replica,
  GTID_SUBTRACT(@replica_gtids, @source_gtids)
    AS extra_on_replica;
```

Trong ví dụ, replica thiếu `uuid-a:1191-1200` và không có GTID thừa so với tập source. Đây là phép so sánh tập GTID, không phải kiểm tra nội dung từng hàng.

Nếu `missing_on_replica` không rỗng, cần xác định các GTID đó:

- Đã được receiver nhận vào relay log chưa? Đối chiếu `Retrieved_Gtid_Set`.
- Applier đang chờ hay đã dừng ở một transaction trước đó?
- Source còn giữ binlog chứa các giao dịch này không?
- Các giao dịch đã bị purge nhưng còn archive không?
- Replica có đang theo đúng source/channel không?

Nếu `extra_on_replica` không rỗng, đừng tự động xóa hoặc đánh dấu các GTID đó là đã xử lý. Chúng có thể là giao dịch ghi trực tiếp trên replica, giao dịch từ source khác trong topology nhiều nguồn, hoặc dữ liệu hợp lệ từ một lần phục hồi trước. Cần xác định origin UUID, channel, thời điểm và tác động dữ liệu của từng nhóm.

GTID set toàn cục của một máy chủ có thể hợp nhiều channel. Với multi-source replication, so sánh global set không đủ để kết luận channel nào thiếu transaction. Phải xem trạng thái từng channel, nguồn gốc GTID và topology thực tế.

Ngoài ra, `Retrieved_Gtid_Set` khác `Executed_Gtid_Set`: một transaction có thể đã nhận vào relay log nhưng chưa được applier áp dụng. Vì vậy, phần chênh lệch giữa source và replica không luôn có nghĩa transaction đã mất; có thể nó đang chờ trong relay log hoặc bị chặn sau một lỗi apply trước đó.

### 6. Chọn cách sửa có kiểm chứng

Không có một thao tác skip phù hợp cho mọi lỗi. Chọn phương án dựa trên bằng chứng về transaction, dữ liệu và khả năng khôi phục.

#### 6.1. Khắc phục kết nối rồi tiếp tục

Chọn cách này khi source còn đủ binlog, dữ liệu replica chưa bị thay đổi ngoài luồng và lỗi nằm ở mạng, DNS, TLS hoặc quyền. Sửa cấu hình, khởi động receiver, xác nhận relay log tăng và applier tiếp tục xử lý. Sau đó kiểm tra GTID và dữ liệu.

#### 6.2. Sửa dữ liệu replica rồi chạy lại applier

Chọn khi đã chứng minh được hàng nào sai và giá trị đúng phải là gì. Ví dụ, lỗi 1032 có thể cần phục hồi hàng bị thiếu trên replica; lỗi 1062 có thể cần xác minh hàng trùng là cùng một thay đổi hay là dữ liệu nghiệp vụ khác.

Quy trình tối thiểu:

1. Dừng applier để tránh trạng thái thay đổi trong lúc kiểm tra:

   ```sql
   STOP REPLICA SQL_THREAD;
   ```

2. Lưu transaction lỗi và dữ liệu trước khi sửa; xác nhận source là chuẩn dữ liệu cần theo.
3. Sửa đúng hàng/schema trên replica bằng một kế hoạch đã kiểm tra, bảo đảm thao tác không tạo ra transaction ngoài luồng làm lệch GTID hoặc lan sang các downstream.
4. Đối chiếu lại hàng đã sửa với source và kiểm tra các ràng buộc liên quan.
5. Khởi động applier:

   ```sql
   START REPLICA SQL_THREAD;
   ```

6. Theo dõi worker, error log, GTID set và dữ liệu của các transaction kế tiếp.

Việc sửa trực tiếp trên replica trong GTID mode cần kế hoạch cụ thể để không tạo errant transaction. Không mặc định rằng `SET sql_log_bin=0` là giải pháp áp dụng được cho mọi phiên bản hoặc mọi trạng thái GTID. Xác minh cơ chế ghi log và quyền theo đúng phiên bản trước khi thực hiện.

#### 6.3. Bỏ qua transaction chỉ khi đã chứng minh là an toàn

Bỏ qua transaction nghĩa là replica sẽ không thực hiện hiệu ứng của transaction đó. Chỉ cân nhắc nếu đã xác minh dữ liệu trên replica đã tương đương với trạng thái sau transaction, hoặc transaction thực sự không cần thiết theo quyết định nghiệp vụ. Ghi lại GTID, nội dung, lý do, người duyệt và bằng chứng so sánh.

Với GTID mode, một cách xử lý transaction cụ thể là tạo một empty transaction mang đúng GTID cần bỏ qua để applier nhận diện GTID đó đã được thực thi. Mẫu minh họa sau chỉ dành cho lab hoặc runbook đã xác minh, khi applier đã dừng và GTID chưa nằm trong `gtid_executed`:

```sql
STOP REPLICA SQL_THREAD;

SET GTID_NEXT = 'source_uuid:transaction_number';
BEGIN;
COMMIT;
SET GTID_NEXT = 'AUTOMATIC';

START REPLICA SQL_THREAD;
```

Thay `source_uuid:transaction_number` bằng GTID thực tế của transaction lỗi. Empty transaction không tái tạo dữ liệu; nó chỉ ghi nhận GTID đó đã được xử lý. Khi applier gặp transaction cùng GTID trong relay log, MySQL có thể bỏ qua vì GTID đã được thực thi. Nếu dữ liệu replica chưa tương đương, cách này tạo khoảng trống dữ liệu có chủ đích và có thể gây lỗi nghiệp vụ về sau.

Ở cấu hình không dùng GTID, một số phiên bản hỗ trợ biến skip counter như `sql_slave_skip_counter` hoặc tên mới `sql_replica_skip_counter`. Các biến này có giới hạn theo phiên bản, không dùng được khi `gtid_mode=ON` và có thể tương tác phức tạp với multi-threaded applier. Chỉ dùng theo tài liệu phiên bản và runbook đã thử; không biến việc skip event thành cách xử lý mặc định.

#### 6.4. Dựng lại replica từ backup khi lệch rộng

Nếu có nhiều transaction thiếu/thừa, dữ liệu khác nhau trên nhiều bảng, source đã purge log cần thiết hoặc không thể chứng minh an toàn cho từng sửa chữa, dựng lại replica thường là phương án có thể kiểm soát hơn.

Quy trình tổng quát:

1. Ghi lại cấu hình source/channel, GTID, filter, TLS, replication user và tọa độ backup hiện tại.
2. Chuẩn bị backup nhất quán từ source phù hợp với phiên bản và topology.
3. Khôi phục replica từ backup theo đúng quy trình; áp dụng metadata GTID hoặc file/position do backup cung cấp.
4. Cấu hình source và channel. Với GTID auto-position trên phiên bản hỗ trợ:

   ```sql
   CHANGE REPLICATION SOURCE TO
     SOURCE_HOST = 'mysql-source.example.net',
     SOURCE_PORT = 3306,
     SOURCE_USER = 'repl_user',
     SOURCE_AUTO_POSITION = 1;
   ```

   Ví dụ lược bỏ mật khẩu và tùy chọn TLS; dùng secret management và cấu hình bảo mật đã phê duyệt. Trên phiên bản cũ, cú pháp là `CHANGE MASTER TO` và `MASTER_AUTO_POSITION=1`.

5. Khởi động replication và xác minh receiver/applier, GTID, độ trễ và dữ liệu.
6. Chỉ đưa replica trở lại phục vụ sau khi các kiểm tra chấp nhận đều đạt.

Không chạy `RESET REPLICA ALL` như bước mặc định trước khi lưu cấu hình: lệnh này có thể xóa thông tin kết nối source của channel. Chỉ reset metadata khi runbook dựng lại yêu cầu và bạn đã lưu đủ thông tin để cấu hình lại.

### 7. Kiểm chứng sau sửa chữa

Một thread báo `Yes` chưa chứng minh replica đã đồng bộ hoặc dữ liệu đã đúng. Sau khi sửa, kiểm tra theo nhiều lớp:

**Trạng thái luồng.** Receiver và applier phải chạy theo thiết kế. `Last_IO_Error` và `Last_SQL_Error` không còn lỗi mới. Kiểm tra cả từng worker nếu bật parallel applier.

**GTID.** So sánh `gtid_executed` giữa source và replica sau khi source tạm ngừng ghi hoặc tại một mốc chụp có thể đối chiếu. Nếu source tiếp tục nhận giao dịch, ghi timestamp và xác định phần chênh lệch dự kiến. Xác minh `Retrieved_Gtid_Set` không còn backlog ngoài dự kiến.

**Dữ liệu.** So sánh số lượng hàng chỉ là bước sơ bộ. Kiểm tra checksum hoặc đối chiếu theo khóa, các bảng liên quan, foreign key, tổng tiền, số lượng đơn hàng, tồn kho và các bất biến nghiệp vụ. Với hệ thống lớn, có thể dùng công cụ checksum bảng phù hợp, nhưng phải đánh giá tải và phạm vi khóa.

**Read-only và quyền ghi.** Nếu replica chỉ phục vụ đọc, xác minh `read_only` và `super_read_only` theo thiết kế, đồng thời kiểm tra ứng dụng không gửi ghi nhầm sang replica. Các tài khoản quản trị vẫn cần được kiểm soát.

**Replication sau phục hồi.** Theo dõi ít nhất một chu kỳ workload thực tế; kiểm tra transaction dài, DDL, event và tác vụ nền. Ghi lại GTID set, độ trễ, thời điểm đạt trạng thái đồng bộ và kết quả kiểm tra dữ liệu.

### 8. Tình huống thực hành

Một hệ thống có source `db-primary` và replica `db-read-1`, dùng GTID và row-based replication. Sau khi một quản trị viên sửa trực tiếp bảng `orders` trên replica, applier dừng với lỗi 1062 khi nhận một transaction insert từ source. Receiver vẫn chạy và relay log tiếp tục tăng.

Hãy lập kế hoạch xử lý và trả lời:

1. Bạn cần lưu những trường nào từ `SHOW REPLICA STATUS` và bảng Performance Schema nào để xác định worker, transaction và channel gây lỗi?
2. Vì sao receiver vẫn chạy trong khi applier dừng? Điều đó nói gì về `Retrieved_Gtid_Set` và `Executed_Gtid_Set`?
3. Bạn sẽ so sánh hàng `orders` trên source và replica bằng khóa nào? Cần kiểm tra các bảng liên quan nào trước khi sửa?
4. Trong trường hợp nào có thể sửa hàng trên replica rồi tiếp tục applier? Bằng chứng nào chứng minh sửa chữa đã đúng?
5. Vì sao không nên tạo empty GTID transaction ngay khi thấy lỗi 1062?
6. Nếu phát hiện nhiều GTID thừa do ghi trực tiếp trên replica và dữ liệu lệch trên nhiều bảng, vì sao dựng lại replica có thể an toàn hơn sửa từng hàng?
7. Viết checklist nghiệm thu trước khi cho ứng dụng đọc lại từ `db-read-1`.

### 9. Checklist ứng phó replication lỗi

- [ ] Xác định đúng source, replica, channel và phiên bản MySQL.
- [ ] Thu thập `SHOW REPLICA STATUS` cùng lỗi receiver/applier và worker trước khi thay đổi.
- [ ] Lưu GTID set, file/position, relay log metadata và trạng thái backup/archive.
- [ ] Phân biệt lỗi kết nối, lỗi apply, transaction chưa nhận và transaction đã nhận nhưng chưa áp dụng.
- [ ] Đối chiếu dữ liệu/schema liên quan; tìm nguyên nhân gây drift.
- [ ] Xác định GTID thiếu/thừa bằng `GTID_SUBTRACT` và phân tích nguồn gốc từng nhóm.
- [ ] Chọn sửa dữ liệu, skip có kiểm chứng hoặc re-seed theo bằng chứng và phê duyệt.
- [ ] Không xóa relay log, reset channel hoặc thay GTID metadata trước khi lưu trạng thái và hiểu tác động.
- [ ] Xác minh receiver/applier, GTID, backlog, dữ liệu và bất biến nghiệp vụ sau sửa.
- [ ] Lưu change record, bằng chứng, người thực hiện và thời điểm replica được chấp nhận trở lại.

### 10. Nguyên tắc vận hành

Khi replication dừng, hãy xác định transaction đang thiếu ở đường truyền hay đang bị chặn ở applier. Khi GTID lệch, phân biệt giao dịch chưa nhận, đã nhận nhưng chưa áp dụng và giao dịch chỉ tồn tại trên một phía. Lỗi 1032 hoặc 1062 thường là tín hiệu dữ liệu đã lệch; bỏ qua transaction có thể làm lỗi biến mất nhưng giữ nguyên sai lệch. Chỉ sửa khi biết trạng thái đúng, và chỉ skip khi đã chứng minh hiệu ứng transaction không còn cần áp dụng. Nếu không thể chứng minh tính đúng đắn của sửa chữa cục bộ, dựng lại replica từ backup nhất quán rồi kiểm chứng GTID và dữ liệu trước khi đưa trở lại phục vụ.
