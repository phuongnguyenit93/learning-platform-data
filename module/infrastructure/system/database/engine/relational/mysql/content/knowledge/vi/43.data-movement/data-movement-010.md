# Di chuyển dữ liệu lớn khi ứng dụng vẫn đang ghi

Trong module **DATABASE_MYSQL**, di chuyển dữ liệu lớn thường xuất hiện khi nâng cấp máy chủ, thay đổi hạ tầng, tách schema, chuyển vùng triển khai hoặc thay thế cụm cơ sở dữ liệu. Khó khăn lớn nhất là dữ liệu vẫn tiếp tục thay đổi trong lúc sao chép. Nếu chỉ xuất một bản dump rồi nạp sang máy mới, các giao dịch phát sinh sau thời điểm chụp dữ liệu sẽ không có ở đích.

Một quy trình di chuyển trực tuyến thường kết hợp **bản chụp nhất quán ban đầu** với **Change Data Capture (CDC)** từ binary log. Bản chụp đưa dữ liệu nền sang máy đích; replication hoặc một bộ đọc binlog tiếp tục chuyển các thay đổi mới. Khi đích bắt kịp, đội vận hành tạm dừng ghi trong một khoảng ngắn, xác nhận hai phía đồng bộ rồi chuyển ứng dụng sang máy mới.

Bài học này tập trung vào cách lập kế hoạch, chụp snapshot, nạp dữ liệu song song, đồng bộ phần thay đổi còn thiếu và thực hiện cutover an toàn. Mục tiêu là giảm thời gian dừng dịch vụ mà vẫn bảo toàn tính nhất quán của dữ liệu.

## 1. Mục tiêu và mô hình di chuyển

Sau bài học, bạn có thể:

- Giải thích vì sao dump và restore đơn thuần không đủ khi nguồn vẫn nhận ghi.
- Thiết kế snapshot nhất quán và xác định chính xác vị trí binary log tương ứng.
- Chọn công cụ dump/load phù hợp với kích thước dữ liệu.
- Cấu hình replication theo GTID hoặc file/position để đồng bộ thay đổi sau snapshot.
- Theo dõi lag, dung lượng binary log và lỗi applier trong suốt quá trình.
- Lập kế hoạch freeze ghi, kiểm tra cuối và chuyển ứng dụng sang đích.
- Xử lý lỗi thường gặp và chuẩn bị phương án quay lui có kiểm soát.

### 1.1. Vì sao cần hai giai đoạn?

Giả sử nguồn có bảng **orders** với hàng triệu bản ghi. Tại thời điểm bắt đầu dump, ứng dụng vẫn thêm đơn hàng, cập nhật trạng thái và ghi thanh toán. Snapshot chỉ chứa trạng thái tại một mốc nhất định. Nếu nạp snapshot xong rồi mở ứng dụng trên đích ngay, các thay đổi phát sinh trong thời gian dump và load sẽ bị thiếu.

Mô hình phù hợp:

~~~mermaid
flowchart LR
    APP[Ứng dụng] --> SRC[MySQL nguồn]
    SRC -->|Snapshot nhất quán| DUMP[Dump / vùng staging]
    DUMP -->|Bulk load| DST[MySQL đích]
    SRC -->|Binary log / CDC| DST
    DST -->|Đã bắt kịp| CUTOVER[Cutover]
    APP -. sau cutover .-> DST
~~~

Quy trình gồm hai luồng:

1. **Initial load:** chuyển toàn bộ dữ liệu nền tại một snapshot đã xác định.
2. **Catch-up:** phát lại các giao dịch được ghi sau snapshot để đích tiến gần trạng thái nguồn hiện tại.

Trong thời gian này, nguồn vẫn là nơi nhận ghi chính. Đích chỉ nhận dữ liệu qua luồng nạp và replication; ứng dụng chưa được ghi độc lập vào đích. Cách làm này tránh phải hợp nhất hai luồng ghi có thể xung đột.

### 1.2. Chọn phạm vi di chuyển

Trước khi chọn công cụ, xác định rõ phạm vi:

- Toàn bộ instance hay chỉ một schema?
- Có cần chuyển user, role, grant, routine, event và trigger không?
- Có bảng dùng MyISAM hoặc engine không hỗ trợ transaction không?
- Có bảng lớn không có primary key hoặc unique key?
- Có thay đổi DDL thường xuyên trong thời gian di chuyển không?
- Có cần giữ nguyên GTID để đích tiếp tục làm replica hoặc tham gia topology khác không?
- Ứng dụng có thể chịu thời gian dừng ghi bao lâu?

Nếu đích sẽ thay thế toàn bộ instance nguồn và tiếp tục nhận replication từ nguồn trong giai đoạn chuyển, nên ưu tiên một snapshot bao phủ đầy đủ phạm vi dữ liệu và GTID của nguồn. Nếu chỉ di chuyển một schema, cần đặc biệt xem xét các giao dịch chạm nhiều schema, trigger, routine và bảng phụ thuộc; GTID là định danh giao dịch ở phạm vi máy chủ, không phải mã riêng cho từng schema.

## 2. Chuẩn bị nguồn và đích

### 2.1. Kiểm kê tương thích

Ghi nhận trước khi sao chép:

| Hạng mục | Cần kiểm tra |
|---|---|
| Phiên bản | Phiên bản MySQL nguồn, đích và khả năng replication giữa hai phiên bản |
| Engine | InnoDB, MyISAM và các engine khác |
| Schema | Kiểu dữ liệu, generated column, partition, index, constraint |
| Charset/collation | Charset ở cấp server, database, table và column |
| SQL mode | Quy tắc chuyển đổi dữ liệu và xử lý câu lệnh |
| Time zone | time_zone, system_time_zone, dữ liệu TIMESTAMP |
| Đối tượng | View, trigger, routine, function, event và definer |
| Tài khoản | User, role, grant, authentication plugin và quyền ứng dụng |
| Hệ thống | lower_case_table_names, cấu hình InnoDB, dung lượng, IOPS, RAM |
| Bảo mật | TLS, tài khoản replication, secret và quyền truy cập bản dump |

Không giả định hai máy chủ có cấu hình giống nhau chỉ vì cùng phiên bản MySQL. Ví dụ, khác biệt collation có thể làm thay đổi kết quả so sánh chuỗi hoặc tính duy nhất của index. Khác múi giờ có thể làm ứng dụng hiển thị thời điểm khác nhau nếu quy trình chuyển đổi TIMESTAMP không được kiểm tra.

Với migration nâng cấp phiên bản, hãy kiểm tra tính tương thích của DDL, reserved words, authentication plugin, kiểu dữ liệu và tính năng đã thay đổi. Chạy công cụ kiểm tra nâng cấp phù hợp với phiên bản trước khi nạp dữ liệu lớn.

### 2.2. Chuẩn bị binary log và GTID

Nếu dùng replication để bắt kịp thay đổi, nguồn phải lưu binary log đủ lâu để bao phủ toàn bộ khoảng thời gian dump, truyền, load và catch-up.

Kiểm tra cấu hình:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'log_bin';
SHOW GLOBAL VARIABLES LIKE 'binlog_format';
SHOW GLOBAL VARIABLES LIKE 'binlog_row_image';
SHOW GLOBAL VARIABLES LIKE 'gtid_mode';
SHOW GLOBAL VARIABLES LIKE 'enforce_gtid_consistency';
SHOW GLOBAL VARIABLES LIKE 'binlog_expire_logs_seconds';
SHOW BINARY LOG STATUS;
~~~

Với migration dựa trên GTID, hai máy chủ cần được cấu hình GTID theo yêu cầu replication. Nguồn phải có **gtid_mode=ON**; đích cần được cấu hình phù hợp để sử dụng **SOURCE_AUTO_POSITION=1**. Kiểm tra trạng thái GTID thực tế trước khi bắt đầu, không chỉ kiểm tra file cấu hình.

Với replication dựa trên row event, **binlog_format=ROW** thường là lựa chọn phù hợp vì log ghi lại thay đổi hàng. Nó giúp giảm sự phụ thuộc vào schema mặc định và cách diễn giải câu SQL khi phát lại. Cấu hình **binlog_row_image** cần phù hợp với công cụ CDC và yêu cầu phục hồi; kiểm tra tài liệu của công cụ đang dùng trước khi chọn giá trị khác FULL.

Giữ binary log từ mốc snapshot đến khi đích bắt kịp. Nếu nguồn xóa các log cần thiết trước khi đích đọc chúng, replication có thể dừng với lỗi thiếu GTID hoặc không tìm thấy file log. Đừng chạy PURGE BINARY LOGS thủ công trong giai đoạn migration nếu chưa xác nhận mọi replica và tiến trình CDC đã đọc xong phần log đó.

### 2.3. Tài khoản và kết nối

Dùng tài khoản riêng cho tác vụ migration:

- Tài khoản dump chỉ có quyền đọc và quyền cần thiết để lấy metadata snapshot/binlog.
- Tài khoản replication chỉ có quyền replication phù hợp với phiên bản MySQL.
- Tài khoản load có quyền tạo schema, bảng, index và nạp dữ liệu trên đích.
- Kết nối replication qua TLS và xác minh chứng thư máy chủ.
- Lưu mật khẩu trong secret manager hoặc cơ chế bảo vệ tương đương; không ghi mật khẩu vào script, log hoặc kho mã nguồn.

Đối với kết nối replication, tài khoản nguồn cần quyền replication thích hợp. Tài khoản thực hiện dump có thể cần **REPLICATION CLIENT** để lấy tọa độ binary log; một số phương thức lấy snapshot cần thêm quyền như **RELOAD** hoặc **BACKUP_ADMIN**. Hãy cấp đúng quyền theo công cụ và phiên bản.

## 3. Tạo snapshot nhất quán

### 3.1. Snapshot phải đi cùng một mốc log

Snapshot và tọa độ binary log phải đại diện cho cùng một thời điểm logic. Nếu dump dữ liệu tại mốc A nhưng cấu hình replica bắt đầu đọc từ mốc B muộn hơn A, các giao dịch từ A đến B có thể bị bỏ sót. Nếu bắt đầu từ mốc trước A mà không có cơ chế nhận diện giao dịch đã nằm trong snapshot, dữ liệu có thể bị áp dụng lặp.

Vì vậy, hãy dùng công cụ tạo snapshot có khả năng ghi lại GTID set hoặc file/position tương ứng. Không tự chụp dữ liệu bằng một công cụ rồi lấy tọa độ binlog vào thời điểm khác.

### 3.2. Dùng MySQL Shell cho dữ liệu lớn

MySQL Shell cung cấp **util.dumpSchemas()**, **util.dumpInstance()** và **util.loadDump()** với khả năng chia dữ liệu thành nhiều chunk, dump/load song song, nén và theo dõi tiến độ. Với dữ liệu lớn, chunking giúp nhiều worker xử lý các phần dữ liệu độc lập.

Ví dụ dump một schema:

~~~javascript
util.dumpSchemas(
  ['appdb'],
  '/backup/appdb-dump',
  {
    threads: 8,
    bytesPerChunk: '128M',
    consistent: true,
    checksum: true
  }
);
~~~

Ví dụ này tạo dump nhất quán và chia dữ liệu thành các chunk có kích thước trung bình khoảng 128 MB trước khi nén. **threads** cần được điều chỉnh theo CPU, I/O và tải đọc của nguồn. Tăng số worker không phải lúc nào cũng làm dump nhanh hơn; quá nhiều worker có thể cạnh tranh I/O với workload nghiệp vụ.

Với migration toàn instance, dùng **util.dumpInstance()** và lựa chọn rõ phạm vi schema, user và đối tượng cần chuyển. Với migration một schema, **util.dumpSchemas()** phù hợp hơn nhưng phải hiểu giới hạn GTID toàn cục khi đích sẽ tiếp tục replication.

Dump utility mặc định hướng tới snapshot nhất quán. Khi **consistent: true**, công cụ phối hợp snapshot transaction và cơ chế khóa backup để giữ nhất quán trong lúc các worker đọc dữ liệu. Chỉ các bảng InnoDB mới được bảo đảm snapshot nhất quán theo transaction. Bảng không hỗ trợ transaction cần được xử lý riêng hoặc có kế hoạch khóa phù hợp.

### 3.3. Metadata của dump

Dump do MySQL Shell tạo có file metadata **@.json**. Metadata chứa **gtidExecuted** và có thể chứa tên file/position binary log của nguồn nếu tài khoản dump có quyền **REPLICATION CLIENT**.

Khi load, có thể hiển thị metadata:

~~~javascript
util.loadDump('/backup/appdb-dump', {
  threads: 8,
  showMetadata: true,
  checksum: true
});
~~~

Đọc và lưu lại GTID set cùng tọa độ binlog từ metadata. Đây là thông tin cần thiết để thiết lập luồng replication sau khi initial load hoàn tất.

Lưu ý: **util.loadDump()** không tự động áp GTID set của nguồn lên đích chỉ vì metadata có trường **gtidExecuted**. Nếu cần dùng GTID auto-position, phải áp dụng GTID set theo đúng quy trình của phiên bản MySQL Shell và MySQL Server, thường thông qua **updateGtidSet**. Với MySQL 8.0 đích, tùy trạng thái GTID của đích, có thể dùng **append** hoặc **replace**; hai lựa chọn có điều kiện về tập GTID hiện tại và không được chọn tùy tiện.

Khi sử dụng **updateGtidSet** trên MySQL Server thông thường, cần đặt **skipBinlog: true** trong quá trình load theo yêu cầu của MySQL Shell. Không dùng tùy chọn này khi Group Replication đang chạy trên đích. Hãy đọc điều kiện của phiên bản đích và kiểm tra **gtid_executed**, **gtid_purged** trước khi áp dụng.

**Cảnh báo với migration chỉ một schema:** GTID là tập giao dịch ở phạm vi toàn server. Metadata của một schema dump vẫn có thể chứa GTID set của toàn bộ nguồn. Nếu chỉ nạp **appdb** nhưng áp toàn bộ GTID set của nguồn lên đích, đích có thể tuyên bố đã thực thi các giao dịch thuộc schema khác dù dữ liệu của chúng chưa được nạp. Khi tiếp tục replication, điều này có thể làm bỏ qua thay đổi cần thiết. Chỉ áp toàn bộ GTID set khi snapshot và phạm vi dữ liệu tương ứng thực sự bao phủ các giao dịch đó; nếu chỉ chuyển một schema, phải thiết kế CDC và phạm vi giao dịch riêng, hoặc chọn phương án chuyển toàn instance.

### 3.4. Dùng mysqldump cho quy mô vừa hoặc luồng file/position

Với dữ liệu vừa phải hoặc khi muốn dùng replication theo file/position, có thể dùng **mysqldump**:

~~~bash
mysqldump --login-path=migrate \
  --single-transaction --quick \
  --source-data=2 \
  --set-gtid-purged=OFF \
  --routines --events --triggers --hex-blob \
  --databases appdb \
  > appdb.sql
~~~

**--single-transaction** tạo snapshot nhất quán cho bảng InnoDB mà không khóa ghi trong toàn bộ thời gian dump. **--source-data=2** ghi tên file và vị trí binary log tương ứng vào dump dưới dạng chú thích để quản trị viên dùng khi cấu hình replica. **--set-gtid-purged=OFF** trong ví dụ này chọn quy trình file/position; không trộn nó với quy trình GTID auto-position.

**--source-data** yêu cầu binary log bật và quyền phù hợp để lấy trạng thái binlog; với cách kết hợp **--single-transaction**, máy chủ chỉ cần giữ global read lock trong một khoảng ngắn lúc bắt đầu. Tài khoản thường cần **RELOAD** và quyền xem trạng thái binary log. Kiểm tra mã thoát và phần đầu dump để xác nhận tọa độ đã được ghi.

**--single-transaction** chỉ bảo đảm snapshot nhất quán cho bảng transactional như InnoDB. Trong lúc dump, không chạy **ALTER TABLE**, **CREATE TABLE**, **DROP TABLE**, **RENAME TABLE** hoặc **TRUNCATE TABLE** trên các bảng liên quan; các thay đổi DDL đồng thời có thể khiến dump sai hoặc thất bại. **--quick** giúp đọc hàng theo luồng thay vì tải toàn bộ bảng vào bộ nhớ client.

Đối với dữ liệu rất lớn, một file SQL đơn thường mất nhiều thời gian để nạp và khó khai thác song song. Khi đó, cân nhắc MySQL Shell dump/load utilities hoặc công cụ backup vật lý tương thích với phiên bản và kiến trúc đích.

## 4. Nạp dữ liệu nền vào đích

### 4.1. Chuẩn bị máy đích

Trước khi load:

- Xác nhận đích là instance mới hoặc schema đích đã được dọn theo kế hoạch.
- Cấu hình **server_id** duy nhất, GTID và binary logging nếu đích sẽ trở thành replica.
- Kiểm tra dung lượng data, redo, undo, temporary tablespace, binary log và vùng staging.
- Kiểm tra **max_allowed_packet**, giới hạn kết nối, quyền và plugin cần thiết.
- Xác nhận không có ứng dụng hoặc job ghi vào schema đích.
- Đặt chính sách read-only phù hợp để tránh ghi ngoài luồng migration.

Nếu load sẽ áp GTID set của nguồn, hãy chuẩn bị target theo điều kiện của **updateGtidSet**. Không để target có các giao dịch không liên quan làm giao nhau với GTID set sẽ nhập.

### 4.2. Load song song và tối ưu thời gian

Ví dụ load dump MySQL Shell:

~~~javascript
util.loadDump('/backup/appdb-dump', {
  threads: 8,
  deferTableIndexes: 'all',
  analyzeTables: 'on',
  checksum: true
});
~~~

**deferTableIndexes: 'all'** tạo primary key trước và hoãn các secondary index đến sau khi dữ liệu được nạp. Điều này có thể giảm chi phí cập nhật index cho từng hàng, nhưng phần tạo index sau cùng vẫn cần CPU, I/O và dung lượng tạm. **analyzeTables: 'on'** giúp cập nhật thống kê sau khi load để optimizer có thông tin phù hợp.

Nếu đích sẽ trở thành replica GTID của nguồn, thêm các tùy chọn cập nhật GTID đúng theo kế hoạch, ví dụ:

~~~javascript
util.loadDump('/backup/full-instance-dump', {
  threads: 8,
  deferTableIndexes: 'all',
  checksum: true,
  showMetadata: true,
  updateGtidSet: 'append',
  skipBinlog: true
});
~~~

Đây là ví dụ cho dump instance/schema và target MySQL 8.0 đã được kiểm tra điều kiện GTID. Chỉ dùng **append** khi GTID set trong dump không giao với **gtid_executed** hiện tại của target. **replace** có điều kiện khác và có thể thay thế tập **gtid_purged**; không chọn nếu chưa đối chiếu các tập GTID. Không dùng **updateGtidSet** cho dump table hoặc khi Group Replication đang chạy trên target.

Trong lúc load, theo dõi:

- Số worker đang hoạt động và tốc độ nạp.
- CPU, memory, disk I/O, độ trễ storage và dung lượng còn lại.
- Lỗi chuyển đổi dữ liệu, lỗi index và lỗi constraint.
- Thời gian tạo secondary index.
- Tiến độ theo bảng/chunk và khả năng resume của công cụ.

Điều chỉnh **threads** và chunk size dựa trên phép đo. Nếu nguồn chịu tải cao, giới hạn tốc độ đọc hoặc chạy dump trong khung giờ thấp điểm. Nếu target bị nghẽn I/O, tăng worker có thể làm tổng thời gian tệ hơn.

### 4.3. Nạp bằng mysqldump

Với dump SQL:

~~~bash
mysql --login-path=restore < appdb.sql
~~~

Lệnh này chạy toàn bộ SQL trong file. Kiểm tra mã thoát của client và log để phát hiện lỗi giữa chừng. Nếu nạp lại sau khi lỗi, cần xác định các câu lệnh đã chạy đến đâu và chọn cách làm sạch hoặc khôi phục lại target trước khi chạy lại. Không mặc định rằng file dump có thể chạy lặp an toàn.

## 5. Bắt kịp thay đổi bằng replication hoặc CDC

### 5.1. Tạo tài khoản replication

Ví dụ trên nguồn:

~~~sql
CREATE USER 'migrate_repl'@'target-host'
  IDENTIFIED BY 'REPLACE_WITH_SECRET';

GRANT REPLICATION SLAVE ON *.* TO 'migrate_repl'@'target-host';
~~~

Thay mật khẩu và host bằng giá trị được quản lý an toàn. Quyền replication có thể có tên hoặc yêu cầu khác theo phiên bản MySQL; hãy dùng tên quyền được tài liệu phiên bản đang chạy hỗ trợ. Kết nối replication nên dùng TLS và xác minh chứng thư nguồn.

### 5.2. GTID auto-position

Khi nguồn và đích được cấu hình GTID phù hợp, sau khi nạp snapshot và xử lý GTID set, cấu hình đích:

~~~sql
CHANGE REPLICATION SOURCE TO
  SOURCE_HOST = 'mysql-source.example',
  SOURCE_PORT = 3306,
  SOURCE_USER = 'migrate_repl',
  SOURCE_AUTO_POSITION = 1,
  SOURCE_SSL = 1,
  SOURCE_SSL_CA = '/etc/mysql/ca.pem',
  SOURCE_SSL_VERIFY_SERVER_CERT = 1;

START REPLICA;
~~~

Thông tin xác thực được cấu hình qua quy trình secret an toàn của tổ chức. Không đưa mật khẩu thật vào tài liệu hoặc lịch sử lệnh được chia sẻ.

Với **SOURCE_AUTO_POSITION=1**, replica gửi tập GTID nó đã nhận hoặc thực thi; nguồn gửi các giao dịch có GTID mà replica còn thiếu. Nguồn phải giữ binary log chứa các GTID cần thiết. Nếu log đã bị purge, replica có thể không bắt đầu được và cần khởi tạo lại từ snapshot mới hoặc một nguồn log lưu trữ đầy đủ.

### 5.3. File/position replication

Nếu dùng **mysqldump --source-data=2** với file/position, lấy tên file và vị trí trong phần chú thích của dump rồi cấu hình:

~~~sql
CHANGE REPLICATION SOURCE TO
  SOURCE_HOST = 'mysql-source.example',
  SOURCE_PORT = 3306,
  SOURCE_USER = 'migrate_repl',
  SOURCE_LOG_FILE = 'mysql-bin.000123',
  SOURCE_LOG_POS = 456789,
  SOURCE_SSL = 1,
  SOURCE_SSL_CA = '/etc/mysql/ca.pem',
  SOURCE_SSL_VERIFY_SERVER_CERT = 1;

START REPLICA;
~~~

Thay **SOURCE_LOG_FILE** và **SOURCE_LOG_POS** bằng tọa độ thực tế trong dump. Không kết hợp **SOURCE_AUTO_POSITION=1** với **SOURCE_LOG_FILE** hoặc **SOURCE_LOG_POS** trong cùng cấu hình. Chọn một cơ chế định vị nhất quán cho channel.

### 5.4. Kiểm tra replication

Trên đích:

~~~sql
SHOW REPLICA STATUS\G
~~~

Theo dõi các trường quan trọng:

- **Replica_IO_Running** và **Replica_SQL_Running**: receiver và applier có đang chạy không.
- **Last_IO_Error** và **Last_SQL_Error**: lỗi kết nối hoặc lỗi áp dụng gần nhất.
- **Seconds_Behind_Source**: chỉ số độ trễ tham khảo, không phải bằng chứng duy nhất về đồng bộ.
- **Retrieved_Gtid_Set** và **Executed_Gtid_Set**: tập GTID đã nhận và đã áp dụng.
- **Relay_Source_Log_File** và **Exec_Source_Log_Pos**: vị trí nguồn đã đọc và vị trí applier đã xử lý khi dùng file/position.

Đồng thời theo dõi dung lượng binary log ở nguồn, relay log ở đích, số worker applier và tải hệ thống. Nếu receiver chạy nhưng applier bị lỗi, log vẫn có thể tiếp tục được nhận trong khi dữ liệu đích không bắt kịp.

Với GTID, có thể chờ đích thực thi hết một tập GTID đã ghi nhận ở nguồn:

~~~sql
SELECT WAIT_FOR_EXECUTED_GTID_SET('SOURCE_GTID_SET', 60);
~~~

Thay **SOURCE_GTID_SET** bằng giá trị GTID set thực tế đã lấy từ nguồn. Kết quả **0** nghĩa là đích đã thực thi hết tập GTID trong thời gian chờ; **1** nghĩa là hết thời gian chờ. Hàm này hữu ích khi chuẩn bị cutover, nhưng phải bảo đảm tập GTID đại diện đúng phạm vi dữ liệu đã di chuyển.

### 5.5. Không lọc replication tùy tiện

Nếu chỉ di chuyển một schema, việc dùng **replicate-do-db**, **replicate-wild-do-table** hoặc bộ lọc CDC cần được thiết kế cẩn thận. Giao dịch có thể cập nhật nhiều schema hoặc ghi sang bảng audit, ledger, outbox và bảng tổng hợp. Bộ lọc có thể khiến một phần thay đổi của giao dịch không được áp dụng.

GTID cũng là phạm vi toàn server. Không đánh dấu toàn bộ GTID của nguồn là đã thực thi trên đích nếu chỉ có dữ liệu của một schema được nạp. Hãy xác định phụ thuộc liên schema và kiểm thử kết quả trên clone. Khi không chứng minh được phạm vi dữ liệu độc lập, hãy chuyển toàn bộ dữ liệu liên quan rồi tách sau.

## 6. Kiểm tra dữ liệu trước cutover

### 6.1. Kiểm tra cấu trúc và đối tượng

Đối chiếu:

- Database, table, column, index, primary key và foreign key.
- View, trigger, stored procedure, function và event.
- Charset, collation, SQL mode và time zone.
- User, role, grant, definer và authentication plugin.
- Partition, generated column và thuộc tính đặc biệt của bảng.

Không chỉ kiểm tra số lượng bảng. Một trigger thiếu có thể khiến dữ liệu đích tiếp tục ghi nhưng không còn tạo audit record; một event thiếu có thể làm job định kỳ không chạy.

### 6.2. Kiểm tra dữ liệu

Dùng nhiều loại phép kiểm tra:

- So sánh số hàng theo bảng hoặc theo partition.
- So sánh tổng tiền, số lượng, min/max và các chỉ số nghiệp vụ.
- Kiểm tra khóa trùng, bản ghi mồ côi và quan hệ giữa bảng.
- So sánh checksum khi công cụ hỗ trợ.
- Lấy mẫu bản ghi ở đầu, giữa và cuối phạm vi khóa.
- Chạy truy vấn nghiệp vụ quan trọng trên đích.

Ví dụ kiểm tra số lượng và tổng tiền:

~~~sql
SELECT COUNT(*) AS order_count,
       SUM(total_amount) AS total_amount,
       MIN(created_at) AS first_order,
       MAX(created_at) AS last_order
FROM appdb.orders;
~~~

Chạy cùng truy vấn trên nguồn và đích tại cùng mốc dữ liệu. Nếu nguồn vẫn tiếp tục ghi, hai kết quả có thể khác nhau do thời điểm truy vấn khác nhau. Hãy thực hiện so sánh chính xác sau khi đã tạm dừng ghi ở giai đoạn cutover hoặc dùng một mốc GTID nhất quán.

### 6.3. Kiểm tra tải ứng dụng

Trước cutover, chạy smoke test trên đích:

- Đăng nhập bằng tài khoản ứng dụng.
- Chạy các truy vấn đọc thường dùng.
- Thử ghi trong môi trường kiểm thử hoặc transaction có thể rollback.
- Kiểm tra truy vấn có dùng index như mong đợi.
- Kiểm tra connection pool, TLS, quyền và thời gian phản hồi.
- Xác nhận job nền, event scheduler và dịch vụ phụ thuộc.

Đừng mở traffic production chỉ vì replication không báo lỗi. Cần xác nhận ứng dụng hoạt động với schema và quyền trên đích.

## 7. Cutover với thời gian dừng ngắn

### 7.1. Chuẩn bị trước giờ chuyển

Trước cutover:

1. Hoàn tất initial load và để replication bắt kịp gần nguồn.
2. Xác minh không có lỗi receiver/applier và binary log chưa bị purge.
3. Chạy kiểm tra cấu trúc, checksum và truy vấn nghiệp vụ.
4. Chuẩn bị endpoint mới, DNS, Router hoặc cấu hình connection pool.
5. Thông báo cửa sổ chuyển đổi và chuẩn bị chế độ maintenance.
6. Xác định rõ người có quyền cho phép mở ghi trên đích.

Không chờ đến lúc dừng ghi mới phát hiện target thiếu index, user hoặc quyền truy cập.

### 7.2. Quy trình cutover

Một trình tự điển hình cho migration toàn instance theo GTID:

**Bước 1 — Ngừng phát sinh ghi mới.** Bật maintenance mode, tạm dừng worker, scheduler, consumer và các luồng ghi từ dịch vụ phụ. Drain request đang chạy và chờ transaction mở hoàn tất.

**Bước 2 — Fencing nguồn.** Đặt nguồn ở chế độ chỉ đọc để ngăn ghi ngoài dự kiến:

~~~sql
SET GLOBAL super_read_only = ON;
~~~

Giữ nguồn hoạt động để đích đọc nốt binary log. Không cho ứng dụng tự động chuyển về nguồn trong lúc cutover.

**Bước 3 — Chụp mốc cuối.** Lấy GTID set cuối cùng sau khi mọi giao dịch ghi đã dừng:

~~~sql
SELECT @@GLOBAL.gtid_executed;
~~~

**Bước 4 — Chờ đích bắt kịp.** Trên đích, chờ toàn bộ GTID set vừa lấy:

~~~sql
SELECT WAIT_FOR_EXECUTED_GTID_SET('FINAL_SOURCE_GTID_SET', 120);
~~~

Nếu hết thời gian chờ, không mở ghi trên đích. Kiểm tra receiver/applier, lỗi SQL, GTID còn thiếu và dung lượng log.

**Bước 5 — Dừng luồng replication.** Khi xác nhận đích đã thực thi hết mốc cuối, dừng channel:

~~~sql
STOP REPLICA;
~~~

Giữ trạng thái và metadata replication để phục vụ kiểm tra hoặc phương án tiếp theo. Chỉ reset channel khi đã xác định không còn cần thông tin cấu hình và relay log.

**Bước 6 — Chuyển ứng dụng.** Chuyển endpoint, DNS hoặc Router đến đích. Kiểm tra kết nối mới và truy vấn đọc trước.

**Bước 7 — Mở ghi trên đích.** Đặt chế độ ghi trên đích theo chính sách:

~~~sql
SET GLOBAL read_only = OFF;
~~~

Đặt `read_only` về OFF sẽ đồng thời tắt `super_read_only`, cho phép ứng dụng ghi trên đích sau khi endpoint đã được chuyển và kiểm tra.

Chỉ sau đó mới tắt maintenance mode và mở lại worker/consumer theo thứ tự đã chuẩn bị.

**Bước 8 — Giữ nguồn ở trạng thái fenced.** Duy trì nguồn read-only và cô lập khỏi luồng ghi ứng dụng. Ghi nhận thời điểm chuyển, GTID cuối và kết quả xác minh.

Thứ tự trên giúp bảo đảm không có hai primary cùng nhận ghi trong thời điểm chuyển. Điều chỉnh lệnh và quyền theo phiên bản, topology và cơ chế replication cụ thể.

### 7.3. Đối với migration một schema

Nếu chỉ di chuyển một schema, việc so sánh **gtid_executed** toàn server có thể không chứng minh schema đích đã đủ dữ liệu. GTID set có thể bao gồm các giao dịch của schema không được dump. Hãy dùng bộ CDC có khả năng xác định đúng bảng và giữ ranh giới giao dịch cần thiết, hoặc thực hiện cutover theo một mốc đối soát ứng dụng được thiết kế riêng. Không dùng một GTID set toàn cục như bằng chứng duy nhất cho dữ liệu của một schema được lọc.

## 8. Rollback và giai đoạn ổn định

### 8.1. Không thể quay lui đơn giản sau khi đích nhận ghi

Trước khi mở ghi trên đích, có thể hủy cutover và đưa ứng dụng trở lại nguồn nếu nguồn vẫn giữ nguyên dữ liệu và chưa có giao dịch mới trên đích.

Sau khi ứng dụng đã ghi vào đích, nguồn trở thành bản cũ. Chuyển ứng dụng trở lại nguồn ngay sẽ làm mất các giao dịch đã phát sinh trên đích. Khi đó cần một trong các phương án:

- Thiết lập replication ngược từ đích về nguồn theo kế hoạch đã kiểm thử.
- Đồng bộ phần dữ liệu phát sinh sau cutover bằng quy trình CDC/reconciliation.
- Khôi phục lại từ backup mới và thực hiện migration lại nếu dữ liệu đã phân nhánh.

Không để ứng dụng ghi đồng thời ở cả hai nơi để “dễ rollback”. Dual-write cần thiết kế riêng về idempotency, thứ tự giao dịch, xử lý lỗi một nửa và đối soát; nếu không, nó tạo thêm rủi ro mất nhất quán.

### 8.2. Theo dõi sau chuyển đổi

Trong giai đoạn ổn định, theo dõi:

- Lỗi kết nối, timeout và tỷ lệ retry của ứng dụng.
- Latency và throughput truy vấn trên đích.
- CPU, memory, IOPS, dung lượng và tốc độ tăng binary log.
- Deadlock, lock wait, lỗi constraint và lỗi SQL.
- Kết quả đối soát nghiệp vụ.
- Các job nền, event, trigger và luồng tích hợp.
- Những truy vấn có execution plan khác biệt đáng kể so với nguồn.

Giữ nguồn cũ ở trạng thái read-only theo thời hạn rollback đã thống nhất. Không xóa dữ liệu nguồn, backup hoặc binary log cho đến khi chủ hệ thống xác nhận migration ổn định và chính sách lưu giữ cho phép dọn dẹp.

## 9. Sự cố thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Snapshot chậm hơn dự kiến | Bảng lớn, I/O nguồn thấp, chunk quá lớn hoặc ít worker | Điều chỉnh chunk/thread, giới hạn tải và đo lại |
| Load bị nghẽn ở index | Tạo nhiều secondary index cùng lúc hoặc storage chậm | Dùng deferred index nếu phù hợp, tăng IOPS và theo dõi dung lượng tạm |
| Replication không bắt đầu | Sai tọa độ, thiếu quyền, TLS hoặc GTID set không tương thích | Kiểm tra trạng thái replication, tài khoản và metadata snapshot |
| Nguồn đã purge log cần thiết | Thời gian dump/load dài hơn retention hoặc log bị xóa thủ công | Dùng snapshot mới hoặc kho binlog đầy đủ; tăng retention cho lần sau |
| Applier dừng vì duplicate key | Snapshot và vị trí bắt đầu replication không khớp, hoặc đích có dữ liệu ghi riêng | Khởi tạo lại target từ snapshot và tọa độ đúng; không bỏ qua lỗi tùy tiện |
| Applier lỗi do thiếu bảng/cột | DDL thay đổi trong lúc dump hoặc schema nguồn/đích lệch | Kiểm tra lịch sử DDL và đồng bộ schema trước khi phát lại |
| Checksum khác nhau | Dump thiếu dữ liệu, chuyển đổi kiểu/charset hoặc load lỗi | Dừng cutover, xác định bảng/chunk sai và nạp lại có kiểm soát |
| Đích chưa bắt kịp | Tải ghi cao, network hoặc applier không đủ năng lực | Giảm tải, tăng tài nguyên, tăng worker theo phép đo và kéo dài cửa sổ |
| Sau cutover truy vấn chậm | Index/statistics khác, collation hoặc cấu hình optimizer khác | Chạy ANALYZE TABLE, đọc EXPLAIN ANALYZE và tối ưu trên đích |
| Rollback làm mất giao dịch mới | Nguồn cũ chưa nhận các giao dịch mới ở đích | Dừng chuyển ngược; dùng replication ngược hoặc đối soát dữ liệu |

Khi replication dừng, thu thập **Last_IO_Error**, **Last_SQL_Error**, log máy chủ, GTID set, tọa độ binlog và thời điểm lỗi. Không dùng **SQL_SLAVE_SKIP_COUNTER** hoặc tự bỏ giao dịch chỉ để làm cho trạng thái replication chuyển sang Running. Bỏ qua giao dịch có thể tạo ra dữ liệu không nhất quán mà khó phát hiện ngay.

## 10. Checklist vận hành

### Trước khi dump

- [ ] Kiểm kê schema, đối tượng, engine, charset, collation và phiên bản.
- [ ] Xác nhận binary log/GTID và thời gian lưu log đủ dài.
- [ ] Kiểm tra tài khoản, TLS, dung lượng staging và quyền truy cập.
- [ ] Đóng băng DDL trên các đối tượng đang di chuyển.
- [ ] Chọn công cụ snapshot có metadata tọa độ tương ứng.

### Trong khi load và catch-up

- [ ] Kiểm tra dump hoàn tất và metadata không thiếu.
- [ ] Nạp dữ liệu theo chunk/worker phù hợp.
- [ ] Theo dõi CPU, I/O, disk, index build và lỗi load.
- [ ] Cấu hình replication đúng GTID hoặc file/position.
- [ ] Theo dõi receiver, applier, lag, GTID và binary log retention.
- [ ] Kiểm tra checksum, số hàng và invariant nghiệp vụ.

### Trước và sau cutover

- [ ] Chạy thử ứng dụng và xác nhận endpoint đích.
- [ ] Dừng ghi, drain transaction và fencing nguồn.
- [ ] Chờ đích thực thi hết mốc dữ liệu cuối.
- [ ] Dừng replication và chuyển endpoint.
- [ ] Mở ghi trên đích sau khi xác minh.
- [ ] Giữ nguồn read-only và có kế hoạch rollback.
- [ ] Theo dõi lỗi, latency, dữ liệu và job nền sau chuyển đổi.

## 11. Tự kiểm tra

**Tình huống 1:** Dump mất 4 giờ và load mất 5 giờ. Trong thời gian đó ứng dụng vẫn ghi vào nguồn. Vì sao không thể mở ứng dụng trên đích ngay sau khi load xong?

**Gợi ý:** Snapshot chỉ chứa dữ liệu tại một mốc. Các giao dịch phát sinh sau mốc snapshot chưa có ở đích; cần replication hoặc CDC bắt kịp trước cutover.

**Tình huống 2:** Nguồn dùng GTID và đích chỉ được nạp một schema từ util.dumpSchemas(). Có nên áp toàn bộ gtidExecuted trong metadata lên đích không?

**Gợi ý:** Không áp dụng một cách máy móc. GTID set là toàn cục của nguồn, có thể chứa giao dịch thuộc schema không được nạp. Cần bảo đảm phạm vi dữ liệu và giao dịch tương ứng hoặc thiết kế CDC riêng.

**Tình huống 3:** Đích báo Replica_IO_Running=Yes nhưng Replica_SQL_Running=No. Điều đó có nghĩa migration đã bắt kịp chưa?

**Gợi ý:** Chưa. Receiver có thể nhận log nhưng applier không thực thi được. Kiểm tra Last_SQL_Error, xử lý lỗi dữ liệu/schema rồi mới tiếp tục.

**Tình huống 4:** Sau khi chuyển ứng dụng sang đích, có một số giao dịch mới đã commit. Đội vận hành muốn quay lại nguồn cũ ngay. Rủi ro là gì?

**Gợi ý:** Nguồn chưa có các giao dịch mới trên đích. Chuyển về nguồn sẽ làm mất hoặc phân nhánh dữ liệu. Cần replication ngược hoặc đối soát phần thay đổi trước khi quay lui.

**Tình huống 5:** Vì sao phải đóng băng DDL trong lúc dùng snapshot transaction?

**Gợi ý:** Snapshot transaction bảo đảm nhất quán dữ liệu InnoDB, nhưng DDL đồng thời có thể làm metadata hoặc cấu trúc bảng thay đổi giữa lúc dump các bảng, dẫn đến lỗi hoặc dump không nhất quán.

## 12. Điểm cần ghi nhớ

- Di chuyển trực tuyến cần snapshot nhất quán và luồng CDC để bắt kịp thay đổi sau snapshot.
- Tọa độ binary log hoặc GTID phải khớp chính xác với snapshot; không lấy hai mốc độc lập.
- MySQL Shell dump/load utilities hỗ trợ chunking, parallelism, checksum và metadata hữu ích cho dữ liệu lớn.
- mysqldump --single-transaction --source-data=2 có thể tạo snapshot InnoDB kèm tọa độ binlog, với global read lock ngắn lúc bắt đầu.
- Chỉ dùng SOURCE_AUTO_POSITION=1 khi GTID trên nguồn/đích và GTID set của snapshot được thiết lập đúng.
- GTID là phạm vi toàn server; không đánh dấu toàn bộ GTID nguồn là đã thực thi nếu chỉ chuyển một phần dữ liệu mà không xử lý các phụ thuộc.
- Giữ binary log đủ lâu, theo dõi receiver/applier và không bỏ qua lỗi replication tùy tiện.
- Cutover cần dừng ghi, drain giao dịch, fencing nguồn, chờ đích bắt kịp rồi mới chuyển endpoint và mở ghi.
- Sau khi đích nhận ghi, rollback cần đồng bộ ngược hoặc đối soát; không thể chỉ trỏ ứng dụng về nguồn cũ.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual: mysqldump](https://dev.mysql.com/doc/refman/8.4/en/mysqldump.html) — single-transaction, source-data, quick và giới hạn snapshot.
- [MySQL Shell 8.4 API: Dump and Load Utilities](https://dev.mysql.com/doc/dev/mysqlsh-api-python/8.4/group__util.html) — dump/load song song, consistent snapshot và tùy chọn chunk.
- [MySQL Shell 8.4 Reference: Dump Loading Utility](https://dev.mysql.com/doc/mysql-shell/8.4/en/mysql-shell-utilities-load-dump.html) — metadata GTID, showMetadata, updateGtidSet và checksum.
- [MySQL 8.4 Reference Manual: CHANGE REPLICATION SOURCE TO](https://dev.mysql.com/doc/refman/8.4/en/change-replication-source-to.html) — cấu hình replication theo GTID hoặc file/position.
- [MySQL 8.4 Reference Manual: GTID Auto-Positioning](https://dev.mysql.com/doc/refman/8.4/en/replication-gtids-auto-positioning.html) — cơ chế đồng bộ giao dịch theo GTID.
