# Vai trò binary log và phân biệt với redo/undo của InnoDB

Bài học này thuộc module **DATABASE_MYSQL**. Khi làm chủ MySQL, người vận hành cần hiểu cách dữ liệu được ghi nhận, bảo vệ và phục hồi, bên cạnh thiết kế bảng, kiểu dữ liệu, khóa, truy vấn, index và transaction. Binary log là thành phần quan trọng cho replication và point-in-time recovery (PITR). Để sử dụng đúng, cần phân biệt nó với redo log và undo log do InnoDB quản lý.

Ba loại log này cùng tham gia vào vòng đời giao dịch nhưng phục vụ những mục đích khác nhau. Binary log ghi nhận các thay đổi ở cấp máy chủ MySQL để truyền sang máy chủ khác hoặc phát lại về sau. Redo log giúp InnoDB khôi phục các thay đổi đã ghi khi xảy ra crash. Undo log giữ phiên bản dữ liệu cũ để rollback và phục vụ consistent read theo cơ chế MVCC.

## 1. Binary log là gì?

**Binary log (binlog)** là nhật ký do MySQL Server ghi lại những sự kiện làm thay đổi dữ liệu hoặc cấu trúc cơ sở dữ liệu, theo cấu hình binary logging. Các sự kiện được ghi thành định dạng nhị phân, thường nằm trong một chuỗi file như `mysql-bin.000001`, `mysql-bin.000002` và một file chỉ mục `.index`.

Binary log hoạt động ở cấp máy chủ MySQL, không phải là một file log riêng của InnoDB. Nó có thể ghi nhận thay đổi từ nhiều storage engine được MySQL hỗ trợ. Những câu lệnh chỉ đọc như `SELECT` thông thường không được ghi thành thay đổi dữ liệu trong binlog.

Hai mục đích sử dụng quan trọng nhất:

- **Replication:** máy chủ replica đọc các sự kiện từ binary log của source rồi thực thi hoặc áp dụng thay đổi tương ứng để duy trì dữ liệu.
- **Point-in-time recovery (PITR):** sau khi restore một bản backup nền, người vận hành phát lại các sự kiện trong binlog để đưa dữ liệu đến thời điểm mong muốn, chẳng hạn ngay trước một thao tác xóa nhầm.

Binary log chỉ chứa những sự kiện phát sinh trong khoảng thời gian binary logging được bật và các file còn được giữ lại. Nó không tự chứa toàn bộ trạng thái database tại một thời điểm. Vì vậy, muốn phục hồi từ đầu cần có bản backup nền phù hợp cùng chuỗi binlog liên tục kể từ thời điểm backup.

## 2. Ba loại log và trách nhiệm của từng loại

| Tiêu chí | Binary log | InnoDB redo log | InnoDB undo log |
|---|---|---|---|
| Phạm vi quản lý | MySQL Server | Storage engine InnoDB | Storage engine InnoDB |
| Nội dung khái quát | Sự kiện thay đổi dữ liệu/schema theo định dạng binlog | Thông tin cần thiết để tái áp dụng thay đổi lên các page | Thông tin phiên bản cũ để hoàn tác hoặc đọc nhất quán |
| Mục đích chính | Replication, PITR và ghi nhận thay đổi ở cấp server | Crash recovery và hỗ trợ độ bền giao dịch | Rollback và MVCC consistent read |
| Phạm vi storage engine | Không chỉ riêng InnoDB | Chỉ InnoDB | Chỉ InnoDB |
| Cách sử dụng | Đọc bằng `mysqlbinlog`, replica hoặc quy trình phục hồi | InnoDB tự sử dụng khi khởi động và ghi dữ liệu | InnoDB tự quản lý trong transaction và quá trình purge |
| Thay thế backup đầy đủ? | Không | Không | Không |

### 2.1. Binary log: ghi nhận thay đổi ở cấp MySQL Server

Binlog trả lời câu hỏi: **những thay đổi nào đã được ghi nhận trên máy chủ, theo thứ tự nào?** Tùy định dạng, nó lưu câu lệnh SQL hoặc các sự kiện mô tả thay đổi trên hàng dữ liệu. Replica và `mysqlbinlog` có thể đọc chuỗi sự kiện này để tái tạo thay đổi.

Binlog không phải bản sao trực tiếp của các page trong tablespace. Nó cũng không phải nơi InnoDB tìm đến để tự hoàn tất crash recovery sau mỗi lần khởi động. Khi MySQL phục hồi sau crash, InnoDB sử dụng redo và undo; binary log có vai trò riêng trong việc đồng bộ transaction với tầng lưu trữ và phục vụ các luồng replication/PITR.

### 2.2. Redo log: tái áp dụng thay đổi khi crash recovery

Redo log là cơ chế ghi lại thông tin cần thiết để InnoDB tái áp dụng các thay đổi lên page dữ liệu. Khi transaction cập nhật một hàng, các page trong buffer pool có thể chưa được ghi ngay xuống data file. Redo log giúp bảo đảm rằng những thay đổi đã commit và được ghi bền vững theo cấu hình có thể được khôi phục sau khi tiến trình hoặc máy chủ gặp sự cố.

Redo log được tổ chức theo cơ chế ghi tuần tự và tái sử dụng theo vòng đời checkpoint. Khi MySQL khởi động sau crash, InnoDB đọc redo log để roll forward những thay đổi cần thiết. Sau đó, InnoDB xử lý các transaction chưa hoàn tất bằng thông tin undo phù hợp.

Redo log không phải lịch sử nghiệp vụ dễ đọc và không được dùng như chuỗi sự kiện để replica phát lại. Nó phục vụ phục hồi nội bộ của InnoDB trên instance tương ứng.

### 2.3. Undo log: hoàn tác và giữ phiên bản cũ

Undo log lưu thông tin cần thiết để đảo ngược thay đổi của transaction hoặc cung cấp phiên bản hàng cũ cho consistent read. Đây là một phần quan trọng của **Multi-Version Concurrency Control (MVCC)**.

Ví dụ, transaction A cập nhật số dư từ 500 thành 650 nhưng chưa commit. Một transaction đọc khác cần nhìn thấy snapshot nhất quán có thể đọc phiên bản cũ phù hợp từ undo chain thay vì nhìn thấy giá trị chưa commit. Nếu transaction A rollback, InnoDB dùng thông tin undo để hoàn tác thay đổi.

Undo record không được giữ vô hạn. Khi không còn transaction hoặc read view nào cần phiên bản cũ, InnoDB có thể purge các undo record đã hết thời gian cần thiết. Nếu transaction đọc kéo dài, lịch sử phiên bản có thể phải được giữ lâu hơn và làm tăng lượng undo cần quản lý.

## 3. Một transaction đi qua các loại log như thế nào?

Xét transaction cập nhật một đơn hàng trong bảng InnoDB:

```sql
START TRANSACTION;

UPDATE orders
SET status = 'PAID'
WHERE order_id = 10025;

COMMIT;
```

Ở mức khái niệm, quá trình có các hoạt động sau:

1. InnoDB thay đổi dữ liệu trong bộ nhớ và tạo undo information để có thể rollback hoặc cung cấp phiên bản cũ cho consistent read.
2. InnoDB tạo redo records để những thay đổi cần thiết có thể được tái áp dụng sau crash.
3. Khi transaction commit, MySQL phối hợp việc commit của InnoDB với việc ghi transaction tương ứng vào binary log.
4. Khi commit hoàn tất theo các bảo đảm durability đã cấu hình, client nhận kết quả thành công.

Redo và undo phục vụ hoạt động nội bộ của InnoDB. Binary log cung cấp bản ghi thay đổi ở cấp server cho replication và PITR. Ba cơ chế bổ sung cho nhau, không phải ba bản sao giống nhau của cùng một dữ liệu.

### 3.1. Vì sao MySQL cần phối hợp InnoDB và binary log?

Một transaction có thể đồng thời tạo thay đổi trong InnoDB và sự kiện trong binlog. Nếu một bên commit còn bên kia không ghi nhận transaction, trạng thái dữ liệu và lịch sử replication có thể không đồng nhất. MySQL sử dụng cơ chế **two-phase commit (2PC)** để phối hợp hai phía.

Ở mức khái quát, luồng commit được tổ chức như sau:

1. InnoDB prepare transaction và ghi trạng thái cần thiết vào redo log.
2. MySQL ghi transaction vào binary log.
3. InnoDB commit transaction đã prepare.

Nếu máy chủ crash giữa các bước, InnoDB có thể đối chiếu trạng thái prepared transaction với binlog trong quá trình recovery để quyết định hoàn tất commit hay rollback. Chi tiết nội bộ có thể khác theo phiên bản và cấu hình, nhưng mục tiêu là tránh trạng thái một transaction đã commit ở InnoDB mà không có bản ghi tương ứng trong binlog, hoặc ngược lại.

### 3.2. Durability phụ thuộc cấu hình flush

Hai biến cấu hình thường được xem xét cùng nhau:

```sql
SHOW VARIABLES LIKE 'sync_binlog';
SHOW VARIABLES LIKE 'innodb_flush_log_at_trx_commit';
```

- `sync_binlog` điều khiển tần suất MySQL đồng bộ binary log xuống storage. Giá trị `1` yêu cầu đồng bộ binlog sau mỗi transaction commit theo cơ chế của MySQL.
- `innodb_flush_log_at_trx_commit` điều khiển cách InnoDB ghi và flush redo log. Giá trị `1` yêu cầu ghi và flush redo log tại mỗi lần commit theo thiết kế của InnoDB.

Cấu hình cả hai biến ở mức `1` thường được chọn khi ưu tiên độ bền dữ liệu cao. Đổi lại, có thể tăng số lần đồng bộ storage và ảnh hưởng hiệu năng. Giá trị thực tế cần căn cứ vào RPO, tải ghi, chất lượng storage và khả năng chịu lỗi của hệ thống. Bộ điều khiển, cache thiết bị hoặc hạ tầng lưu trữ cũng ảnh hưởng đến bảo đảm cuối cùng; cấu hình phần mềm không thể bù cho một thiết bị báo hoàn tất ghi sai thực tế.

## 4. Các định dạng binary log

MySQL hỗ trợ những cách biểu diễn sự kiện khác nhau. Khi đọc cấu hình của một hệ thống, cần xác định định dạng đang sử dụng và hành vi theo đúng phiên bản máy chủ.

| Định dạng | Nội dung chính | Ưu điểm | Điểm cần chú ý |
|---|---|---|---|
| `STATEMENT` | Ghi câu lệnh SQL đã thực hiện | Có thể gọn hơn với một số workload | Câu lệnh không xác định hoặc phụ thuộc môi trường có thể cho kết quả khác khi phát lại |
| `ROW` | Ghi sự kiện thay đổi hàng dữ liệu | Phản ánh thay đổi hàng thực tế, thường an toàn hơn cho replication | Có thể tạo lượng log lớn, nhất là với cập nhật nhiều hàng |
| `MIXED` | MySQL lựa chọn statement hoặc row tùy trường hợp | Kết hợp hai cách biểu diễn | Cần hiểu quy tắc chuyển đổi của phiên bản đang chạy |

Với row-based logging, một câu `UPDATE` ảnh hưởng nhiều hàng có thể tạo nhiều row event. `mysqlbinlog -vv` có thể giúp diễn giải row event thành dạng dễ đọc hơn. Tuy nhiên, row event không phải lúc nào cũng chứa toàn bộ cột; điều đó còn phụ thuộc `binlog_row_image` và cấu hình liên quan.

Một điểm dễ nhầm: dùng `ROW` không có nghĩa mọi hoạt động đều được ghi thành row event. Các câu DDL như `CREATE TABLE` hoặc `ALTER TABLE` vẫn được ghi dưới dạng statement event. Hãy đọc binlog thực tế nếu cần xác định chính xác loại sự kiện.

Có thể kiểm tra định dạng và tùy chọn row image:

```sql
SHOW VARIABLES LIKE 'binlog_format';
SHOW VARIABLES LIKE 'binlog_row_image';
```

Giá trị mặc định, khả năng thay đổi động và các định dạng còn được hỗ trợ phụ thuộc phiên bản MySQL. Một số tùy chọn đã được đánh dấu deprecated trong các nhánh phát hành mới, vì vậy hãy kiểm tra tài liệu đúng phiên bản trước khi thiết kế cấu hình mới.

## 5. Bật và kiểm tra binary logging

Binary logging phải được bật trên MySQL Server trước khi các thay đổi cần ghi nhận xảy ra. Tên và đường dẫn file log có thể cấu hình trong tệp cấu hình máy chủ. Ví dụ minh họa:

```ini
[mysqld]
server_id=101
log_bin=/var/lib/mysql/mysql-bin
binlog_format=ROW
sync_binlog=1
binlog_expire_logs_seconds=604800
```

Ý nghĩa các tùy chọn:

- `server_id` định danh máy chủ trong topology replication; mỗi server tham gia cần ID phù hợp và không trùng nhau trong topology.
- `log_bin` bật binary logging và chỉ định tên/đường dẫn cơ sở cho file binlog.
- `binlog_format` chọn định dạng ghi log ở các phiên bản còn hỗ trợ tùy chọn này.
- `sync_binlog` điều khiển việc đồng bộ binlog xuống storage.
- `binlog_expire_logs_seconds` đặt thời gian lưu giữ log theo giây; cần chọn đủ dài cho replica và khoảng PITR cần thiết.

Đây là cấu hình tham khảo, không phải giá trị dùng chung cho mọi hệ thống. Thay đổi các tùy chọn khởi động có thể yêu cầu restart MySQL. Đường dẫn phải tồn tại hoặc có thể được MySQL tạo với quyền filesystem thích hợp; không tự tạo hay di chuyển file log khi máy chủ đang chạy.

Kiểm tra trạng thái:

```sql
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'server_id';
SHOW VARIABLES LIKE 'binlog_format';
SHOW VARIABLES LIKE 'binlog_expire_logs_seconds';
SHOW BINARY LOGS;
```

Để xem vị trí ghi hiện tại, dùng câu lệnh mà phiên bản hỗ trợ. Các bản MySQL mới có `SHOW BINARY LOG STATUS`; nhiều phiên bản trước đó dùng `SHOW MASTER STATUS` (tên cũ có thể đã bị deprecated ở phiên bản mới). Hãy xác minh cú pháp theo phiên bản thực tế thay vì giả định mọi máy chủ đều dùng cùng một tên lệnh.

## 6. Đọc và phát lại binary log bằng `mysqlbinlog`

`mysqlbinlog` là công cụ dòng lệnh để đọc file binlog, lọc theo khoảng thời gian hoặc vị trí và tạo nội dung có thể phát lại bằng MySQL client.

### 6.1. Xem nội dung log

Đọc một file binlog:

```bash
mysqlbinlog /var/lib/mysql/mysql-bin.000123
```

Với row-based logging, có thể dùng chế độ giải mã để xem thông tin row event dễ hiểu hơn:

```bash
mysqlbinlog --base64-output=DECODE-ROWS -vv \
  /var/lib/mysql/mysql-bin.000123
```

Đầu ra có thể chứa giá trị dữ liệu nhạy cảm. Chỉ người có quyền phù hợp mới nên đọc, xuất hoặc lưu bản giải mã này.

### 6.2. Giới hạn theo file position

Binlog có vị trí byte (position) để đánh dấu ranh giới sự kiện. Có thể chọn phạm vi bằng `--start-position` và `--stop-position`:

```bash
mysqlbinlog \
  --start-position=154 \
  --stop-position=9821 \
  /var/lib/mysql/mysql-bin.000123 > replay.sql
```

Các giá trị trên chỉ minh họa cú pháp. Khi phục hồi, phải lấy position thực tế từ metadata của backup, output của lệnh kiểm tra hoặc điểm đã xác minh trong binlog. Cần bảo đảm điểm bắt đầu và kết thúc nằm đúng ranh giới sự kiện/transaction; cắt giữa một transaction có thể dẫn đến nội dung phát lại không hợp lệ hoặc không đạt trạng thái mong muốn.

### 6.3. Giới hạn theo thời gian

Có thể lọc theo timestamp:

```bash
mysqlbinlog \
  --start-datetime="2026-11-19 01:00:00" \
  --stop-datetime="2026-11-19 10:14:59" \
  /var/lib/mysql/mysql-bin.000123 \
  /var/lib/mysql/mysql-bin.000124 > replay.sql
```

Thời gian chỉ là cách chọn phạm vi thuận tiện. Cần xác minh múi giờ, timestamp của sự kiện và ranh giới transaction. Khi cần phục hồi chính xác, file position hoặc GTID thường là cơ sở kiểm soát tốt hơn so với việc chỉ dựa trên giây hiển thị.

### 6.4. Phát lại trên máy chủ phục hồi

Sau khi kiểm tra file `replay.sql`, có thể phát lại vào instance phục hồi:

```bash
mysql --host=db-restore.example.net \
  --user=recovery_user --password < replay.sql
```

Quy trình an toàn thường restore backup nền vào máy chủ cô lập trước, rồi mới phát lại binlog đến điểm mục tiêu. Không nên chuyển thẳng output chưa kiểm tra vào production. Cần xác minh file log, thứ tự, phạm vi, tài khoản thực thi và tác động của các câu lệnh DDL/DML trước khi phát lại.

## 7. GTID và file/position

MySQL có hai cách phổ biến để xác định điểm tiến triển của transaction trong replication và phục hồi:

- **File/position:** xác định tên file binlog cùng vị trí byte trong file, ví dụ `mysql-bin.000123` tại position `9821`.
- **GTID (Global Transaction Identifier):** định danh transaction bằng một mã duy nhất theo server UUID và số thứ tự transaction, ví dụ `3E11FA47-71CA-11E1-9E33-C80AA9429562:57`.

GTID giúp nhận diện transaction đã thực thi mà không phải quản lý thủ công từng cặp file/position trong nhiều tình huống replication. Tuy vậy, GTID không phải một loại log thay thế binlog. Binlog vẫn chứa các sự kiện; GTID gắn định danh transaction và giúp theo dõi, định vị tiến trình.

Trong môi trường dùng GTID, cần lưu metadata GTID tại thời điểm backup và bảo đảm chuỗi transaction cần thiết còn sẵn. Khi restore, trạng thái GTID của instance phục hồi phải phù hợp với quy trình áp dụng transaction, tránh phát lại trùng hoặc bỏ sót thay đổi. Không chỉnh sửa `gtid_purged` hay trạng thái GTID theo phỏng đoán.

## 8. Rotation, retention và purge binary log

MySQL ghi binlog thành nhiều file. Khi file hiện tại đạt điều kiện rotate hoặc có thao tác flush, máy chủ chuyển sang file mới và cập nhật file index. Retention xác định thời gian log được giữ trước khi hết hạn hoặc bị xóa theo cơ chế quản trị.

Binary log cần được giữ đủ lâu cho cả hai nhóm nhu cầu:

1. Replica chậm hoặc tạm mất kết nối vẫn cần các log chưa đọc.
2. Quy trình PITR cần chuỗi log liên tục từ backup nền đến hết khoảng thời gian có thể xảy ra sự cố.

Không được xóa file binlog thủ công khỏi filesystem khi MySQL đang quản lý chúng. Dùng câu lệnh quản trị để purge theo mốc phù hợp:

```sql
-- Xem danh sách file hiện có
SHOW BINARY LOGS;

-- Ví dụ: xóa các file cũ hơn mốc file chỉ định
PURGE BINARY LOGS TO 'mysql-bin.000120';

-- Hoặc xóa các file có timestamp trước thời điểm chỉ định
PURGE BINARY LOGS BEFORE '2026-11-01 00:00:00';
```

`PURGE BINARY LOGS TO` xóa các file đứng trước file đích, không xóa file đích. Trước khi purge, phải kiểm tra replica đã đọc các file cần thiết hay chưa và backup/PITR đã lưu chúng ở nơi khác chưa. Nếu purge quá sớm, replica có thể không còn log để bắt kịp và PITR có thể bị đứt chuỗi.

Có thể xem thời gian lưu cấu hình:

```sql
SHOW VARIABLES LIKE 'binlog_expire_logs_seconds';
```

Thời gian retention nên dài hơn khoảng backup và phục hồi dự kiến, có tính đến thời gian phát hiện sự cố, điều tra, phê duyệt và thực hiện restore. Nếu log được chuyển sang kho lưu trữ ngoài, cần kiểm tra tính toàn vẹn và khả năng truy xuất của bản lưu đó.

## 9. Binary log trong quy trình PITR

PITR kết hợp một bản backup nền với chuỗi binlog liên tục sau thời điểm backup. Ví dụ:

- 01:00: tạo full backup và lưu lại file/position hoặc GTID tương ứng.
- 10:15: một thao tác xóa nhầm xảy ra.
- 10:30: đội vận hành phát hiện sự cố.

Các bước phục hồi:

1. Chọn full backup lúc 01:00 và xác minh backup có thể restore.
2. Restore lên một instance cô lập, tương thích với môi trường nguồn.
3. Lấy điểm bắt đầu phát lại từ metadata của backup.
4. Thu thập toàn bộ binlog liên tục từ điểm đó đến thời điểm ngay trước thao tác xóa nhầm.
5. Kiểm tra các sự kiện và ranh giới transaction, sau đó phát lại trên instance phục hồi.
6. Đối chiếu dữ liệu nghiệp vụ và quyết định phục hồi toàn instance hay trích xuất phần dữ liệu cần thiết.

Binlog không thể phục hồi một thay đổi xảy ra trước khi binary logging được bật, một log đã bị mất, hoặc một khoảng log không còn trong bất kỳ bản lưu nào. Vì vậy, cần giám sát trạng thái logging và chuyển log ra nơi độc lập với máy chủ nguồn.

Replication cũng không thay thế backup. Một lệnh xóa nhầm hoặc dữ liệu hỏng có thể được ghi vào binlog rồi truyền đến replica. Replica giúp tăng tính sẵn sàng và có thể giảm thời gian gián đoạn, nhưng bản backup độc lập cùng binlog được lưu giữ vẫn cần thiết để quay về trạng thái trước sự cố.

## 10. Các lỗi vận hành thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Không có file binlog | Binary logging chưa bật hoặc đường dẫn/cấu hình chưa đúng | Kiểm tra `log_bin`, cấu hình khởi động và error log |
| Replica báo thiếu binlog | Source đã purge file mà replica chưa đọc | Kiểm tra trạng thái replica, retention và chuỗi log; có thể cần dựng lại replica từ backup mới |
| PITR dừng trước thời điểm mong muốn | Thiếu file, chuỗi log bị đứt hoặc backup metadata không chính xác | Kiểm tra danh sách file, position/GTID và bản lưu ngoài máy chủ |
| Phát lại gặp lỗi câu lệnh | Sai thứ tự, sai schema, môi trường đích khác hoặc sự kiện không phù hợp | Kiểm tra đầu ra `mysqlbinlog`, schema và điểm bắt đầu/kết thúc |
| Binlog tăng dung lượng nhanh | Tải ghi lớn, row event nhiều hoặc retention dài | Đo tốc độ phát sinh log, kiểm tra workload và kế hoạch lưu trữ |
| Sau crash có khác biệt cần điều tra | Cấu hình durability, lỗi storage hoặc trạng thái commit cần phân tích | Kiểm tra error log, redo recovery, `sync_binlog` và `innodb_flush_log_at_trx_commit` |

Binlog có thể chứa dữ liệu nhạy cảm, bao gồm giá trị được ghi trong câu lệnh hoặc row event. Hãy giới hạn quyền đọc, mã hóa khi truyền/lưu trữ và áp dụng retention phù hợp. Bản giải mã từ `mysqlbinlog` cũng cần được bảo vệ như dữ liệu nguồn.

## 11. Quy trình kiểm tra nhanh trên một máy chủ

Người vận hành có thể bắt đầu bằng các câu lệnh sau:

```sql
-- Binary logging có được bật không?
SHOW VARIABLES LIKE 'log_bin';

-- Máy chủ có định danh phù hợp không?
SHOW VARIABLES LIKE 'server_id';

-- Định dạng và độ bền binlog
SHOW VARIABLES LIKE 'binlog_format';
SHOW VARIABLES LIKE 'sync_binlog';

-- Độ bền redo và retention binlog
SHOW VARIABLES LIKE 'innodb_flush_log_at_trx_commit';
SHOW VARIABLES LIKE 'binlog_expire_logs_seconds';

-- Các file binlog còn trên máy chủ
SHOW BINARY LOGS;
```

Sau đó, kiểm tra file/position hiện tại bằng câu lệnh trạng thái phù hợp với phiên bản MySQL, kiểm tra replica nếu có, và đối chiếu vị trí binlog đã ghi trong metadata của backup gần nhất. Đừng kết luận hệ thống sẵn sàng PITR chỉ vì `log_bin=ON`; cần chứng minh các file log đã được lưu đủ, liên tục và có thể đọc/phát lại.

## 12. Tự kiểm tra

1. Binary log được dùng cho hai mục đích vận hành quan trọng nào?
2. Vì sao redo log và binary log không thể thay thế nhau trong crash recovery và replication?
3. Undo log hỗ trợ rollback và MVCC consistent read như thế nào?
4. Khi một transaction InnoDB commit, vì sao MySQL cần phối hợp trạng thái InnoDB với việc ghi binlog?
5. Khác biệt chính giữa `STATEMENT` và `ROW` logging là gì? Vì sao DDL vẫn có thể được ghi dưới dạng statement event khi dùng row-based logging?
6. `sync_binlog` và `innodb_flush_log_at_trx_commit` kiểm soát hai cơ chế nào?
7. Vì sao cần lưu file/position hoặc GTID cùng metadata của backup?
8. Điều gì có thể xảy ra nếu purge binlog trước khi replica đọc xong hoặc trước khi hết khoảng PITR cần thiết?
9. Vì sao replica không thay thế được backup độc lập?
10. Hãy mô tả cách restore một backup nền và phát lại binlog để phục hồi ngay trước một transaction gây xóa dữ liệu.

Khi trả lời, hãy luôn xác định log thuộc tầng MySQL Server hay InnoDB, nó ghi loại thông tin nào và được dùng ở bước nào của vòng đời transaction. Phân biệt đúng ba vai trò này giúp thiết kế replication, backup, PITR và xử lý sự cố mà không nhầm lẫn giữa phục hồi nội bộ của storage engine với phát lại lịch sử thay đổi ở cấp máy chủ.
