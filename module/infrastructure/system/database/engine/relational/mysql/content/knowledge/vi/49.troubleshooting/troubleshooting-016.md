# Replica lag, lỗi apply và giao dịch không còn trong binary log

MySQL replication chuyển các thay đổi từ source sang replica thông qua binary log và relay log. Replica có thể chậm hơn source vì chưa nhận đủ sự kiện, chưa áp dụng hết sự kiện đã nhận hoặc bị dừng do lỗi. Một tình huống nghiêm trọng hơn xảy ra khi replica cần một giao dịch nhưng binary log chứa giao dịch đó đã bị xóa khỏi source. Khi đó, chỉ khởi động lại replication thường không giải quyết được; cần xác định chính xác phần dữ liệu còn thiếu và chọn cách đồng bộ lại an toàn.

Điều tra phải tách ba trạng thái: luồng I/O đọc binary log từ source, luồng SQL hoặc applier áp dụng relay log, và lịch sử giao dịch đã thực thi. Một replica có thể nhận dữ liệu rất nhanh nhưng apply chậm; cũng có thể apply khỏe nhưng không nhận thêm dữ liệu do mạng hoặc source. Nếu giao dịch cần thiết đã bị purge, cần phục hồi từ một bản sao nhất quán có lịch sử GTID phù hợp hoặc xây dựng lại replica.

Bài học này thuộc phạm vi làm chủ MySQL từ replication, transaction và kiểm soát đồng thời đến xử lý sự cố vận hành. Nội dung tập trung vào cách phân loại lag, đọc trạng thái replication, xử lý lỗi apply và phục hồi khi binary log không còn chứa giao dịch replica cần.

## 1. Phân biệt các giai đoạn của replication

Trong replication bất đồng bộ thông thường, source ghi transaction đã commit vào binary log. Replica có luồng I/O kết nối đến source, đọc sự kiện và ghi chúng vào relay log cục bộ. Luồng SQL hoặc các worker applier đọc relay log rồi thực thi transaction trên replica.

~~~mermaid
flowchart LR
    A["Client ghi transaction"] --> B["Source: binary log"]
    B --> C["Replica I/O thread"]
    C --> D["Replica: relay log"]
    D --> E["SQL thread / applier workers"]
    E --> F["Replica data"]
    C -. "Mạng, TLS, quyền, binlog" .-> X["Lỗi nhận dữ liệu"]
    E -. "SQL, schema, lock, tài nguyên" .-> Y["Lỗi áp dụng"]
~~~

Ba giai đoạn cần phân biệt:

- **Receive:** replica kết nối source và đọc sự kiện từ binary log.
- **Queue:** sự kiện đã được nhận và nằm trong relay log, chờ applier.
- **Apply:** replica thực thi transaction và cập nhật dữ liệu cục bộ.

Replica lag có thể hình thành ở bất kỳ giai đoạn nào:

| Quan sát | Khả năng cần kiểm tra |
|---|---|
| I/O thread dừng hoặc không kết nối | DNS, mạng, firewall, TLS, tài khoản replication, source log đã purge |
| I/O thread chạy nhưng SQL thread dừng | Lỗi SQL apply, schema lệch, duplicate key, row không tồn tại, disk hoặc lock |
| Cả hai thread chạy nhưng lag tăng | Tốc độ ghi source vượt tốc độ apply, transaction lớn, tài nguyên replica thiếu |
| Relay log tăng liên tục | I/O nhận nhanh hơn applier xử lý |
| Không có relay log mới và replica đứng yên | Source không có giao dịch mới, I/O thread bị ngắt hoặc sai vị trí đọc |
| Replica có dữ liệu mới nhưng truy vấn vẫn cũ | Truy vấn đọc nhầm endpoint, transaction snapshot cũ hoặc replica khác chưa bắt kịp |

Trong MySQL 8, thuật ngữ source/replica được dùng trong câu lệnh mới. Một số phiên bản hoặc công cụ cũ vẫn hiển thị master/slave. Hãy dùng đúng cú pháp được phiên bản đang chạy hỗ trợ.

## 2. Đánh giá replica lag đúng cách

### 2.1. Không chỉ dựa vào Seconds_Behind_Source

Lệnh SHOW REPLICA STATUS cung cấp trường Seconds_Behind_Source. Đây là chỉ báo hữu ích nhưng không phải phép đo hoàn hảo về độ trễ dữ liệu.

- Khi I/O thread bị ngắt, giá trị có thể là NULL hoặc không phản ánh chính xác khoảng trễ thực tế.
- Khi source không có giao dịch mới, giá trị thấp không chứng minh replica vừa nhận được heartbeat mới nhất.
- Với parallel applier, transaction có thể được thực thi theo nhiều worker; trạng thái một luồng không thể mô tả đầy đủ mọi giao dịch đang chờ.
- Chênh lệch đồng hồ hệ thống, transaction chạy lâu và thời điểm commit có thể làm cách diễn giải theo giây sai lệch.
- Replica delay được cấu hình có chủ đích cũng làm tăng độ trễ mà không nhất thiết là lỗi.

Hãy dùng Seconds_Behind_Source cùng trạng thái I/O/applier, GTID, relay log, worker error và các metric theo thời gian. Định nghĩa SLO lag theo nhu cầu nghiệp vụ, ví dụ độ trễ tối đa cho truy vấn báo cáo hoặc read-after-write.

### 2.2. Xem trạng thái tổng thể

Trên replica, chạy:

~~~sql
SHOW REPLICA STATUS\G
~~~

Các trường thường cần lưu vào evidence:

| Trường | Ý nghĩa |
|---|---|
| Replica_IO_Running | Trạng thái luồng nhận sự kiện |
| Replica_SQL_Running | Trạng thái SQL thread/applier |
| Seconds_Behind_Source | Ước lượng độ trễ theo cơ chế của replication |
| Source_Host / Source_Port | Endpoint source đang cấu hình |
| Source_Log_File | Binary log file I/O thread đang đọc |
| Read_Source_Log_Pos | Vị trí đã đọc trong source binlog file |
| Relay_Source_Log_File | Source binlog file chứa sự kiện gần nhất đã apply |
| Exec_Source_Log_Pos | Vị trí source binlog tương ứng sự kiện gần nhất đã apply |
| Relay_Log_File / Relay_Log_Pos | Vị trí đọc hiện tại trong relay log |
| Retrieved_Gtid_Set | GTID đã được nhận về replica |
| Executed_Gtid_Set | GTID đã được thực thi trên replica |
| Last_IO_Error | Lỗi gần nhất của luồng nhận |
| Last_SQL_Error | Lỗi gần nhất của luồng apply |
| Auto_Position | Có sử dụng GTID auto-position hay không |

Không trừ trực tiếp hai giá trị position để suy ra số giây lag. Position thuộc các file khác nhau, kích thước event khác nhau và tốc độ ghi thay đổi theo thời gian.

### 2.3. Theo dõi trạng thái qua Performance Schema

Với MySQL 8, có thể xem trạng thái luồng nhận:

~~~sql
SELECT
  CHANNEL_NAME,
  SERVICE_STATE,
  LAST_ERROR_NUMBER,
  LAST_ERROR_MESSAGE,
  LAST_ERROR_TIMESTAMP,
  RECEIVED_TRANSACTION_SET
FROM performance_schema.replication_connection_status;
~~~

Xem trạng thái applier và worker:

~~~sql
SELECT
  CHANNEL_NAME,
  SERVICE_STATE,
  REMAINING_DELAY,
  COUNT_TRANSACTIONS_RETRIES
FROM performance_schema.replication_applier_status;

SELECT
  CHANNEL_NAME,
  WORKER_ID,
  SERVICE_STATE,
  LAST_ERROR_NUMBER,
  LAST_ERROR_MESSAGE,
  LAST_ERROR_TIMESTAMP,
  APPLYING_TRANSACTION,
  LAST_APPLIED_TRANSACTION
FROM performance_schema.replication_applier_status_by_worker
ORDER BY CHANNEL_NAME, WORKER_ID;
~~~

Cấu trúc bảng và cột có thể khác theo phiên bản MySQL. Nếu hệ thống dùng nhiều replication channel, luôn giữ CHANNEL_NAME trong kết quả; nếu bỏ trường này, có thể nhầm worker của channel này với channel khác.

Xem process list để nhận biết thread đang chờ hoặc chạy:

~~~sql
SHOW FULL PROCESSLIST;
~~~

Trạng thái như đang chờ source gửi event, đang chờ worker xử lý queue hoặc đang chờ transaction phụ thuộc có thể giúp khoanh vùng. Hãy chụp trạng thái nhiều lần cách nhau một khoảng thời gian; một snapshot đơn lẻ không cho biết backlog đang tăng hay giảm.

## 3. Xác định lag ở luồng nhận hay luồng apply

### 3.1. I/O thread không nhận được dữ liệu

Nếu Replica_IO_Running không ở trạng thái Yes, đọc Last_IO_Error và kiểm tra:

- DNS có phân giải đúng source host không?
- Replica có kết nối được source port từ đúng network namespace không?
- Firewall, security group, route hoặc proxy có chặn kết nối không?
- TLS certificate còn hạn, CA được tin cậy và hostname có khớp không?
- Tài khoản replication có đúng host pattern, password và quyền không?
- Source có bật binary logging và còn giữ file/GTID replica cần không?
- Source có bị restart, failover hoặc thay đổi endpoint không?

Trên source, kiểm tra binary logging và file đang có:

~~~sql
SHOW VARIABLES
WHERE Variable_name IN (
  'log_bin',
  'server_id',
  'gtid_mode',
  'enforce_gtid_consistency',
  'binlog_expire_logs_seconds'
);

SHOW BINARY LOGS;
~~~

SHOW BINARY LOG STATUS có thể dùng để xem trạng thái binary log trên các phiên bản hỗ trợ. Ở phiên bản cũ hơn, cú pháp SHOW MASTER STATUS có thể vẫn được dùng. Không giả định một câu lệnh quản trị có cùng tên trên mọi dòng phiên bản.

Nếu lỗi là xác thực hoặc kết nối, sửa endpoint, network, TLS hoặc account rồi khởi động lại luồng nhận theo runbook. Không xóa relay log hoặc reset metadata chỉ để làm mất thông báo lỗi; thao tác đó có thể loại bỏ bằng chứng và làm mất dữ liệu đã nhận nhưng chưa apply.

### 3.2. SQL thread hoặc worker apply bị dừng

Nếu I/O thread vẫn chạy nhưng Replica_SQL_Running không chạy, xem Last_SQL_Error và các bảng replication_applier_status_by_worker. Các lỗi thường gặp:

| Mã/lỗi thường gặp | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| 1062 Duplicate entry | Replica đã có khóa duy nhất mà transaction muốn insert | Kiểm tra dữ liệu lệch, ghi trực tiếp trên replica, filter hoặc transaction trước đó |
| 1032 Can't find record | UPDATE/DELETE không tìm thấy hàng tương ứng | So sánh row source/replica, kiểm tra replication filter và lịch sử ghi |
| 1146 Table doesn't exist | Schema trên replica thiếu bảng hoặc DDL chưa được áp dụng | So sánh SHOW CREATE TABLE và lịch sử migration |
| 1054 Unknown column | Schema không đồng nhất hoặc DDL/ứng dụng khác phiên bản | Kiểm tra thứ tự DDL, column và rollout |
| 1205 Lock wait timeout | Applier bị chặn bởi transaction hoặc truy vấn trên replica | Tìm blocker, transaction dài và metadata/data lock |
| 1213 Deadlock | Các transaction apply tranh chấp lock | Đọc deadlock report, worker, thứ tự khóa và dependency |
| Lỗi disk hoặc relay log | Thiếu dung lượng, quyền tệp hoặc lỗi lưu trữ | Kiểm tra filesystem, error log và relay log |

Trước khi chạy lại SQL thread, phải xác định transaction nào lỗi và vì sao. Sửa schema hoặc dữ liệu theo hướng làm source và replica nhất quán, sau đó xác minh điều kiện trước khi tiếp tục apply.

Không chạy câu lệnh sửa dữ liệu trực tiếp trên replica chỉ để làm cho transaction hiện tại vượt qua. Ghi trực tiếp trên replica có thể tạo sai lệch mới và khiến transaction tiếp theo tiếp tục lỗi. Nếu buộc phải sửa dữ liệu, cần có kế hoạch đồng bộ được phê duyệt và kiểm tra cả source lẫn replica.

### 3.3. I/O nhận nhanh nhưng applier chậm

Nếu I/O thread chạy bình thường, Retrieved_Gtid_Set tiến lên nhưng Executed_Gtid_Set chậm, backlog nằm ở relay log hoặc applier.

Nguyên nhân phổ biến:

- Source ghi nhiều transaction hơn khả năng apply của replica.
- Transaction lớn cập nhật nhiều hàng hoặc index.
- Một transaction dài tạo điểm nghẽn cho các transaction phụ thuộc.
- Replica thiếu CPU, RAM, IOPS hoặc băng thông lưu trữ.
- Truy vấn báo cáo hoặc batch trên replica tranh chấp CPU, I/O và lock.
- DDL cần metadata lock hoặc chặn worker.
- Parallel applier chưa khai thác được tính độc lập của transaction.
- Replica chạy trên storage chậm hơn source đáng kể.

Kiểm tra độ dài relay log, trạng thái worker, CPU, disk latency, I/O queue, buffer pool, lock wait và truy vấn đang chạy. Đừng tăng số worker ngay lập tức nếu nút thắt là transaction tuần tự, disk I/O hoặc một truy vấn giữ lock.

## 4. Phân tích GTID và phần giao dịch còn thiếu

GTID giúp nhận diện transaction độc lập với tên file và vị trí binary log. Khi bật GTID replication và auto-position, replica thông báo cho source những GTID nó đã thực thi; source gửi các giao dịch còn thiếu mà nó vẫn còn lưu trong binary log.

Trên replica, ghi lại:

~~~sql
SELECT
  @@GLOBAL.gtid_executed AS executed_gtids,
  @@GLOBAL.gtid_purged AS purged_gtids;
~~~

Trường Retrieved_Gtid_Set trong SHOW REPLICA STATUS và RECEIVED_TRANSACTION_SET trong Performance Schema cho biết giao dịch đã nhận, còn Executed_Gtid_Set cho biết giao dịch đã thực thi. Một giao dịch đã nhận nhưng chưa apply vẫn có thể nằm trong relay log; không coi nó là giao dịch đã được replica áp dụng.

Trên source, thu thập:

~~~sql
SELECT
  @@GLOBAL.gtid_executed AS source_executed_gtids,
  @@GLOBAL.gtid_purged AS source_purged_gtids;
~~~

Có thể dùng các hàm GTID để so sánh tập giao dịch. Ví dụ, sau khi sao chép các giá trị từ hai máy vào biến phiên trên một máy kiểm tra:

~~~sql
SET @source_executed = 'SOURCE_GTID_EXECUTED_SET';
SET @replica_executed = 'REPLICA_GTID_EXECUTED_SET';
SET @source_purged = 'SOURCE_GTID_PURGED_SET';

SET @missing = GTID_SUBTRACT(
  @source_executed,
  @replica_executed
);

SELECT
  @missing AS not_executed_on_replica,
  GTID_SUBTRACT(@missing, @source_purged)
    AS missing_and_still_in_source_history,
  GTID_SUBTRACT(@missing, GTID_SUBTRACT(@missing, @source_purged))
    AS missing_and_purged;
~~~

Đây là phép so sánh tập GTID phục vụ phân tích. Giá trị cần được lấy tại các thời điểm được ghi rõ và phải tính đến việc source tiếp tục nhận giao dịch trong khi điều tra. GTID missing nhưng chưa purge có thể còn trong binary log để replica nhận; GTID đã purge không còn được lấy lại từ binary log hiện tại của source.

Nếu topology có nhiều source, channel, failover hoặc giao dịch được tạo ngoài luồng replication, cần phân tích GTID set theo từng server/channel. Không kết luận mất giao dịch chỉ từ một phép so sánh trên các snapshot thu thập ở thời điểm khác nhau.

## 5. Khi giao dịch cần thiết đã bị purge khỏi binary log

### 5.1. Dấu hiệu nhận biết

Một replica có thể dừng nhận dữ liệu với lỗi cho biết source không còn binary log file hoặc GTID mà replica yêu cầu. Mã lỗi 1236 thường xuất hiện trong Last_IO_Error cho các vấn đề đọc binary log, trong đó có trường hợp source đã purge GTID mà replica cần; hãy đọc toàn bộ thông báo để phân biệt với các nguyên nhân 1236 khác. Với GTID auto-position, lỗi thường thể hiện source đã purge một hay nhiều GTID cần thiết. Với replication dùng file/position, lỗi có thể chỉ ra file binlog được yêu cầu không còn trong danh sách binary log.

Kiểm tra:

1. Last_IO_Error và mã lỗi đầy đủ trên replica.
2. Source_Log_File và Read_Source_Log_Pos nếu dùng file/position.
3. Retrieved_Gtid_Set và Executed_Gtid_Set nếu dùng GTID.
4. Danh sách SHOW BINARY LOGS trên source.
5. GTID_PURGED và GTID_EXECUTED trên source.
6. Error log source để xác định thời điểm file bị purge hoặc source đổi vai trò.

Lỗi binlog đã purge khác với lỗi mạng tạm thời. Retry liên tục không thể khôi phục một file đã bị xóa. Nếu source có bản lưu binary log ngoài máy chủ, có thể đánh giá việc phục hồi file theo quy trình riêng; phải xác minh tính liên tục, checksum và đúng thứ tự trước khi cho replication đọc tiếp.

### 5.2. Vì sao không thể chỉ tăng thời gian retry?

Replica cần mọi transaction còn thiếu theo đúng thứ tự và lịch sử GTID. Nếu source đã xóa các binlog chứa giao dịch đó, nó không thể gửi lại sự kiện từ file không còn tồn tại. Tăng connect retry hoặc restart I/O thread chỉ lặp lại cùng yêu cầu và cùng lỗi.

Không tự ý đặt lại vị trí binlog đến file mới nhất hoặc tăng Executed_Gtid_Set bằng cách giả mạo lịch sử. Việc đó có thể khiến replica bỏ qua thay đổi dữ liệu mà nó chưa từng nhận. Replication có thể chuyển sang trạng thái Running nhưng dữ liệu vẫn sai và sai lệch khó phát hiện hơn.

### 5.3. Các lựa chọn phục hồi

Chọn một trong các hướng sau dựa trên bằng chứng:

| Lựa chọn | Khi phù hợp | Điều kiện |
|---|---|---|
| Khôi phục binlog đã lưu trữ | Có bản lưu đầy đủ của các file/GTID bị thiếu | File nguyên vẹn, đúng chuỗi và có thể cung cấp cho replica |
| Dựng lại replica từ backup mới | Không còn binlog cần thiết hoặc dữ liệu replica không đáng tin cậy | Backup nhất quán, có GTID/position chính xác và nằm sau phần lịch sử cần thiết |
| Clone từ một instance khỏe mạnh | Có donor cùng topology/phiên bản tương thích và quy trình clone được hỗ trợ | Donor có dữ liệu và GTID history phù hợp; đánh giá tải và tác động clone |
| Phục hồi từ backup rồi thiết lập replication lại | Replica cần được tái tạo hoàn toàn | Xác định source đúng, GTID continuity, schema và cấu hình replication |

Ưu tiên phục hồi từ một bản backup nhất quán có chứa toàn bộ giao dịch trước mốc cần tiếp tục. Nếu dùng backup vật lý hoặc logical, phải lấy kèm thông tin GTID/binlog coordinate được tạo tại cùng snapshot. Chỉ có dữ liệu bảng mà không có mốc replication đáng tin cậy thì chưa đủ để cấu hình lại an toàn.

### 5.4. Quy trình dựng lại replica bằng backup

Một quy trình tổng quát:

1. **Ngăn replica phục vụ dữ liệu sai:** loại endpoint đọc của replica khỏi pool ứng dụng hoặc đánh dấu không sẵn sàng. Nếu cần, dừng replication để giữ nguyên bằng chứng và tránh apply ngoài kế hoạch.
2. **Ghi lại trạng thái trước khi thay đổi:** lưu SHOW REPLICA STATUS, GTID set, lỗi, cấu hình, schema và log liên quan.
3. **Chọn snapshot:** chọn backup từ source hoặc donor khỏe mạnh, nhất quán và có mốc GTID/binlog đi kèm. Snapshot phải bao phủ lịch sử trước phần transaction mà replica cần tiếp tục.
4. **Phục hồi trên instance đích:** restore vào replica mới hoặc môi trường thay thế. Kiểm tra phiên bản, server_id duy nhất, server_uuid, storage engine, schema và quyền.
5. **Xác minh lịch sử:** so sánh GTID trong backup/instance phục hồi với GTID của source. Đảm bảo mọi giao dịch trước mốc bắt đầu đã có trong snapshot và source còn giữ giao dịch sau mốc đó.
6. **Thiết lập kết nối replication:** dùng GTID auto-position nếu topology hỗ trợ và GTID history phù hợp; nếu dùng file/position, lấy đúng tọa độ từ backup. Không suy ra position từ thời điểm file backup được sao chép xong.
7. **Khởi động replication:** dùng START REPLICA theo cấu hình đã xác minh và theo dõi I/O, applier, worker error, GTID và lag.
8. **Đối soát dữ liệu:** kiểm tra checksum hoặc dữ liệu nghiệp vụ quan trọng trước khi đưa replica trở lại pool đọc.

Các câu lệnh cấu hình source có tên khác nhau theo phiên bản. Với MySQL 8 hiện đại, cấu hình GTID auto-position có dạng:

~~~sql
CHANGE REPLICATION SOURCE TO
  SOURCE_HOST = 'mysql-source.internal',
  SOURCE_PORT = 3306,
  SOURCE_USER = 'repl_user',
  SOURCE_PASSWORD = 'REDACTED_SECRET',
  SOURCE_AUTO_POSITION = 1;

START REPLICA;
~~~

Đây là ví dụ cấu hình cho một channel mặc định; không chạy trước khi restore và xác minh GTID history. Nếu thay đổi một channel đang hoạt động, dừng replica trước khi đổi các thuộc tính nguồn hoặc chế độ auto-position theo yêu cầu của phiên bản. Quản lý mật khẩu theo quy trình secret, không lưu giá trị thật vào script hoặc packet. Với phiên bản cũ, cú pháp CHANGE MASTER TO và START SLAVE có thể còn được sử dụng.

Nếu cần thay relay log sau khi đã quyết định dựng lại, RESET REPLICA có thể xóa relay log và reset thông tin trạng thái replication; nó không thay thế việc restore dữ liệu và xác minh GTID. RESET REPLICA ALL còn xóa thông tin kết nối source. Chỉ dùng lệnh reset đúng mục đích và sau khi đã lưu evidence; không chạy RESET REPLICA ALL như một cách xóa lỗi chung.

### 5.5. Không giả mạo GTID để bỏ qua khoảng trống

GTID_PURGED và GTID_EXECUTED là lịch sử giao dịch, không phải biến trạng thái để tùy ý tăng cho replication chạy tiếp. Chỉ thiết lập GTID_PURGED trong quy trình provisioning có điều kiện phù hợp, chẳng hạn instance mới được chuẩn bị và backup có lịch sử xác định. Không chỉnh GTID_PURGED trên replica đang chứa dữ liệu không rõ nguồn gốc để giả vờ rằng giao dịch đã được áp dụng.

Với GTID mode, việc bỏ qua một transaction chỉ có thể được cân nhắc khi đã chứng minh giao dịch đó không cần áp dụng hoặc đã được thay thế chính xác, và có runbook cụ thể cho phiên bản/topology. Một empty transaction mang GTID có thể ảnh hưởng toàn bộ lịch sử đồng bộ; không dùng cách này để xử lý duplicate key hoặc row not found một cách máy móc.

## 6. Khắc phục lỗi apply mà không làm sai lệch dữ liệu

### 6.1. Duplicate key (1062)

Replica báo duplicate key khi transaction insert/update tạo giá trị vi phạm unique hoặc primary key. Các nguyên nhân có thể:

- Ứng dụng hoặc người vận hành đã ghi trực tiếp trên replica.
- Replica đã nhận transaction trước đó theo một nhánh khác.
- Dữ liệu được khôi phục từ backup không cùng mốc với replication position.
- Replication filter hoặc thay đổi schema làm source và replica có trạng thái khác nhau.
- Transaction bị áp dụng một phần do cấu hình hoặc thao tác trước đó.

Thu thập key bị trùng, bảng, index, transaction GTID, dữ liệu hàng trên cả source và replica. Xác định hàng nào đúng theo nghiệp vụ và lịch sử. Sau khi sửa dữ liệu bằng quy trình đồng bộ có kiểm soát, xác minh transaction còn lại có thể apply và các bảng liên quan vẫn nhất quán.

### 6.2. Không tìm thấy hàng (1032)

UPDATE hoặc DELETE trên replica không tìm thấy hàng cần thay đổi. Kiểm tra khóa chính, giá trị trước/sau, replication filter, ghi trực tiếp trên replica và các transaction trước đó. Nếu dùng row-based replication, kiểm tra row image và dữ liệu hiện tại; nếu dùng statement-based, xem xét khác biệt môi trường có thể làm câu lệnh tạo kết quả khác.

### 6.3. Schema không đồng nhất

Lỗi table/column không tồn tại thường liên quan thứ tự triển khai DDL, migration không đồng bộ hoặc replication filter. So sánh SHOW CREATE TABLE trên source và replica, kiểm tra schema version của ứng dụng, DDL đang chờ và metadata lock. Không tự tạo một cột có kiểu đoán được chỉ để SQL thread chạy tiếp; kiểu dữ liệu, nullability, default và index phải khớp schema nguồn hoặc thiết kế tương thích đã được duyệt.

### 6.4. Lock wait và deadlock

Replica có thể bị chặn bởi truy vấn báo cáo, batch hoặc transaction đọc/ghi chạy trực tiếp trên replica. Kiểm tra process list, data_locks, data_lock_waits và SHOW ENGINE INNODB STATUS. Dừng hoặc điều chỉnh workload gây blocker theo quy trình; sau đó xác nhận applier tiến lên.

Không tăng innodb_lock_wait_timeout ngay lập tức để che nguyên nhân. Nếu transaction bị chặn bởi truy vấn kéo dài hoặc DDL, tăng timeout chỉ khiến backlog tồn tại lâu hơn.

## 7. Giảm lag bền vững

Sau khi replication chạy lại, tìm nguyên nhân khiến replica chậm để tránh tái diễn.

### 7.1. Transaction lớn

Một transaction cập nhật hàng trăm nghìn hoặc hàng triệu bản ghi có thể cần thời gian apply dài. Với commit order và dependency giữa transaction, một transaction lớn có thể giữ các giao dịch sau chờ dù các worker khác còn tài nguyên.

Biện pháp:

- Chia batch lớn thành các transaction nhỏ nếu nghiệp vụ cho phép.
- Tránh giữ transaction mở lâu.
- Lên lịch batch và DDL ngoài giờ cao điểm.
- Kiểm tra index để giảm số hàng phải quét và cập nhật.
- Theo dõi thời gian apply theo GTID và worker.

Không chia một transaction nghiệp vụ thành nhiều commit nếu điều đó làm mất tính nguyên tử mà nghiệp vụ yêu cầu.

### 7.2. Tài nguyên replica

So sánh source và replica về CPU, RAM, storage latency, IOPS, throughput, buffer pool và network. Replica có thể cần cấu hình phần cứng tương đương hoặc mạnh hơn source nếu phải xử lý đồng thời workload đọc và apply.

Kiểm tra dung lượng relay log, binary log, temporary file và disk free. Khi disk gần đầy, applier hoặc I/O thread có thể dừng; chỉ tăng dung lượng mà không tìm nguyên nhân log tăng cũng có thể khiến sự cố lặp lại.

### 7.3. Parallel applier

Parallel replication có thể tăng tốc khi transaction độc lập và có thể áp dụng đồng thời. Hiệu quả phụ thuộc dependency tracking, workload, số worker và thứ tự commit.

Trước khi tăng worker:

1. Xác nhận backlog nằm ở apply chứ không phải I/O.
2. Kiểm tra worker nào đang bận, chờ dependency hoặc lock.
3. Đánh giá CPU, I/O và memory còn dư.
4. Đo throughput apply trước/sau thay đổi.
5. Kiểm tra commit order và tính nhất quán theo yêu cầu ứng dụng.

Tăng worker không giúp nhiều nếu tất cả transaction cập nhật cùng một hàng hoặc phụ thuộc tuần tự. Có thể làm contention tăng và khiến hệ thống chậm hơn.

### 7.4. Truy vấn đọc trên replica

Truy vấn phân tích dài có thể chiếm CPU, I/O hoặc giữ snapshot/lock, ảnh hưởng applier. Tách workload báo cáo sang replica chuyên dụng, giới hạn truy vấn nặng và tránh dùng replica lagged cho thao tác cần read-after-write.

Ứng dụng cần biết endpoint đọc có độ trễ. Với luồng vừa ghi vừa đọc, có thể đọc từ primary/source, chờ GTID đã commit được thực thi trên replica hoặc dùng session affinity theo thiết kế. Không giả định mọi replica đều đã có transaction vừa commit.

## 8. Ngăn mất binary log trong tương lai

### 8.1. Chọn retention theo thời gian phục hồi

Binary log retention phải dài hơn thời gian tối đa mà replica có thể mất kết nối cộng thời gian phát hiện, điều tra và khôi phục. Tính thêm biên an toàn cho tải ghi tăng đột biến, backup/restore kéo dài và bảo trì.

Một cách lập kế hoạch:

~~~text
binlog retention
  >= thời gian outage tối đa dự kiến
   + thời gian phát hiện và xử lý
   + thời gian dựng lại replica nếu cần
   + biên an toàn vận hành
~~~

Ước lượng dung lượng binlog theo tốc độ phát sinh thực tế trong giờ cao điểm, không chỉ theo mức trung bình ngày. Theo dõi dung lượng đĩa để retention dài hơn không làm đầy filesystem.

Kiểm tra cấu hình:

~~~sql
SHOW VARIABLES LIKE 'binlog_expire_logs_seconds';
SHOW VARIABLES LIKE 'log_bin';
SHOW BINARY LOGS;
~~~

binlog_expire_logs_seconds là thời gian hết hạn tự động theo giây ở các phiên bản hỗ trợ. Một số phiên bản cũ có cấu hình expire_logs_days. Xác minh tên và default theo phiên bản thực tế.

### 8.2. Giữ bản lưu binary log ngoài source

Với hệ thống có yêu cầu phục hồi nghiêm ngặt, cân nhắc lưu trữ binary log ra hệ thống lưu trữ riêng. Bản lưu cần có thứ tự, checksum, thời gian, nguồn server UUID và chính sách retention. Thử khôi phục file lưu trữ định kỳ; một bản copy chưa từng được đọc lại không chứng minh có thể dùng khi sự cố.

### 8.3. Giám sát replica và retention

Thiết lập cảnh báo cho:

- I/O thread hoặc applier dừng.
- Lag vượt SLO trong thời gian xác định.
- Retrieved GTID tiến nhưng Executed GTID đứng yên.
- Relay log tăng nhanh hoặc dung lượng đĩa thấp.
- Khoảng cách GTID giữa source và replica tăng bất thường.
- Binary log sắp hết hạn trong khi replica còn thiếu giao dịch.
- Worker apply có lỗi lặp lại hoặc retry tăng.

Theo dõi từng channel nếu dùng multi-source replication. Cảnh báo phải gắn với endpoint, channel, server UUID và thời điểm để người trực xác định đúng luồng.

## 9. Runbook điều tra và phục hồi

### Giai đoạn A: Bảo toàn bằng chứng

1. Ghi thời điểm sự cố, source/replica endpoint và channel.
2. Thu thập SHOW REPLICA STATUS, error log và các bảng Performance Schema liên quan.
3. Lưu GTID_EXECUTED, GTID_PURGED, Retrieved_Gtid_Set và danh sách binary log.
4. Ghi phiên bản MySQL, server_id, server_uuid, cấu hình GTID và replication filter.
5. Kiểm tra replica có bị ứng dụng ghi trực tiếp hay không.

### Giai đoạn B: Phân loại

1. I/O thread có chạy không?
2. SQL thread và mọi worker có chạy không?
3. GTID nhận có tiến nhưng GTID thực thi đứng không?
4. Relay log có tăng không?
5. Last_IO_Error hay Last_SQL_Error chứa mã lỗi nào?
6. Source còn giữ file/GTID cần thiết không?
7. Lag là backlog thật, delay có chủ đích hay chỉ là số đo không đáng tin?

### Giai đoạn C: Chọn hướng sửa

- **Lỗi kết nối tạm thời:** sửa network/TLS/account rồi khởi động I/O thread.
- **Lỗi apply có thể giải thích:** sửa nguyên nhân schema/data/lock theo kế hoạch, xác minh dữ liệu rồi tiếp tục applier.
- **Apply chậm:** giảm workload cạnh tranh, xử lý transaction dài, tăng năng lực hoặc tune parallel applier dựa trên đo đạc.
- **Binlog còn đủ:** khôi phục kết nối và để replica nhận phần GTID/file-position còn thiếu.
- **Binlog đã purge:** phục hồi từ binlog archive đầy đủ hoặc dựng lại replica từ backup/clone có mốc GTID phù hợp.

### Giai đoạn D: Xác minh sau phục hồi

1. Replica_IO_Running và Replica_SQL_Running ở trạng thái hoạt động.
2. Không có Last_IO_Error hoặc Last_SQL_Error mới.
3. Retrieved và Executed GTID tiến theo kỳ vọng.
4. Lag giảm và duy trì trong SLO qua một khoảng quan sát.
5. Đối soát dữ liệu nghiệp vụ hoặc checksum theo phạm vi đã chọn.
6. Replica được đưa trở lại read pool sau khi đạt điều kiện sẵn sàng.
7. Cập nhật retention, alert và runbook để ngăn lặp lại.

## 10. Những thao tác cần tránh

- Không đặt lại source log file/position về vị trí mới nhất để bỏ qua khoảng giao dịch chưa nhận.
- Không giả mạo GTID_EXECUTED hoặc GTID_PURGED trên instance đang có dữ liệu chưa được kiểm chứng.
- Không dùng skip counter hoặc empty transaction để vượt lỗi mà chưa xác định transaction có thể bỏ qua hay không.
- Không xóa relay log trước khi lưu trạng thái và xác định phần giao dịch đã nhận nhưng chưa apply.
- Không chạy RESET REPLICA ALL nếu chỉ muốn restart thread; lệnh này xóa thông tin kết nối source.
- Không ghi trực tiếp trên replica đang nhận replication trừ khi kiến trúc và quy trình cho phép rõ ràng.
- Không tăng worker, timeout hoặc max_connections chỉ dựa trên một metric mà chưa xác định nút thắt.
- Không đưa replica trở lại read pool chỉ vì hai thread đang chạy; phải xác minh GTID, lag và dữ liệu.

## 11. Tình huống thực hành

Một replica MySQL bị ngắt mạng trong hai ngày. Trong thời gian đó, source tiếp tục ghi giao dịch và tự động purge binary log theo retention hiện tại. Khi mạng phục hồi, replica báo lỗi rằng source không còn file hoặc GTID cần thiết. Ứng dụng vẫn đang dùng replica này để chạy báo cáo.

Hãy xử lý theo trình tự:

1. Loại replica khỏi read pool để tránh báo cáo dùng dữ liệu cũ mà không biết.
2. Lưu SHOW REPLICA STATUS, error log, GTID set của source và replica, danh sách binlog còn lại.
3. Xác định transaction còn thiếu và kiểm tra chúng đã bị purge khỏi source hay chưa.
4. Nếu có bản lưu binlog đầy đủ, xác minh chuỗi file/GTID rồi đánh giá cách cung cấp lại cho replication.
5. Nếu không có binlog archive, chọn backup/clone nhất quán từ source khỏe mạnh, lấy mốc GTID cùng snapshot và dựng lại replica.
6. Cấu hình auto-position hoặc file/position theo đúng mốc backup; khởi động replication và theo dõi worker.
7. Đối soát các bảng nghiệp vụ quan trọng, chờ lag đạt SLO rồi mới đưa replica trở lại read pool.
8. Tăng retention dựa trên thời gian outage và restore thực tế; bổ sung cảnh báo sớm khi replica ngắt kết nối.

Không thể chỉ restart replica hoặc chuyển vị trí đọc đến binlog mới nhất, vì làm vậy có thể bỏ qua toàn bộ giao dịch trong hai ngày mất kết nối. Cần tái tạo dữ liệu từ một mốc nhất quán rồi tiếp tục đồng bộ phần giao dịch còn được lưu.

## 12. Câu hỏi tự kiểm tra

1. I/O thread và SQL/applier thread làm hai nhiệm vụ nào khác nhau?
2. Vì sao Seconds_Behind_Source không đủ để kết luận replica đã bắt kịp?
3. Retrieved_Gtid_Set khác Executed_Gtid_Set ở điểm nào?
4. Những trường nào trong SHOW REPLICA STATUS giúp phân biệt receive lag và apply lag?
5. Duplicate key 1062 và row not found 1032 thường chỉ ra loại sai lệch nào?
6. Vì sao tăng số parallel worker không luôn làm replica nhanh hơn?
7. Điều gì xảy ra khi replica cần GTID đã bị purge khỏi binary log source?
8. Khi dựng lại replica từ backup, vì sao cần backup snapshot và GTID/binlog coordinate nhất quán?
9. Vì sao không được tùy tiện tăng GTID_PURGED hoặc đặt vị trí binlog mới nhất?
10. Cần kiểm tra những gì trước khi đưa replica trở lại read pool?

Điều tra replica lag cần tách luồng nhận, hàng đợi relay log và luồng apply. Nếu giao dịch còn trong binary log, sửa kết nối hoặc nút thắt apply để replica bắt kịp. Nếu giao dịch đã bị purge và không có bản lưu đầy đủ, phải dựng lại replica từ snapshot nhất quán có mốc GTID phù hợp. Bảo toàn lịch sử giao dịch và xác minh dữ liệu quan trọng hơn việc làm cho trạng thái replication hiển thị Running.
