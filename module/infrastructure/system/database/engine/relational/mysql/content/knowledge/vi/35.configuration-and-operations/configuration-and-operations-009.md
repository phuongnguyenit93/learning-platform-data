# Redo, undo, binary log, temporary file và kế hoạch dung lượng

Một MySQL instance có thể hết dung lượng dù kích thước bảng dữ liệu chưa tăng nhiều. Ngoài data file và index, InnoDB còn dùng redo log, undo tablespace và temporary tablespace; server ghi binary log để replication và point-in-time recovery; replica lưu relay log; truy vấn, transaction lớn và DDL có thể tạo file tạm. Mỗi nhóm file có cách tăng trưởng, thời gian lưu và cách dọn dẹp khác nhau.

Quản trị dung lượng vì vậy cần nhìn toàn bộ vòng đời ghi dữ liệu, không chỉ nhìn thư mục chứa bảng. Cần biết file nào được phép tự tăng, file nào phải giữ theo chính sách, file nào có thể tái tạo, file nào cần backup trước khi xóa, và mức dung lượng trống cần dành cho peak workload hoặc phục hồi sự cố.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt vai trò và vòng đời của redo log, undo log, binary log và temporary files.
- Giải thích các yếu tố làm từng vùng lưu trữ tăng trưởng.
- Cấu hình độ bền transaction và retention log phù hợp với RPO/RTO.
- Theo dõi undo history, redo capacity, binary log, relay log và temporary storage.
- Ước tính dung lượng theo tăng trưởng dữ liệu, retention và tải đỉnh.
- Lập cảnh báo, ngưỡng an toàn và runbook khi filesystem gần đầy.
- Dọn log và file tạm bằng cơ chế MySQL hỗ trợ, tránh xóa trực tiếp file đang được server quản lý.

Các ví dụ giả định MySQL 8.0 trở lên, InnoDB và binary logging có thể được bật. Một số biến và cách tổ chức file thay đổi theo phiên bản; luôn kiểm tra cấu hình thực tế trước khi áp dụng trên production.

## 1. Bản đồ các vùng lưu trữ

Một máy chủ MySQL thường sử dụng nhiều nhóm file:

| Nhóm | Nội dung | Tác nhân làm tăng | Vai trò chính |
|---|---|---|---|
| Data và index | Tablespace, clustered/secondary index | INSERT, UPDATE, dữ liệu mới, index mới | Lưu dữ liệu lâu dài |
| Redo log | Log record mô tả thay đổi page | Ghi transaction, tốc độ checkpoint | Crash recovery và write-ahead logging |
| Undo tablespace | Undo record và rollback segment | UPDATE/DELETE, transaction dài, snapshot cũ | Rollback và MVCC |
| Binary log | Sự kiện thay đổi ở cấp server | Transaction được ghi binlog, row image, retention | Replication và point-in-time recovery |
| Relay log | Bản ghi nguồn mà replica nhận được | Replica chậm áp dụng, mất kết nối nguồn | Hàng đợi sự kiện replication |
| Temporary storage | Internal temp table, sort, DDL, transaction cache | GROUP BY, sort, materialization, DDL, transaction lớn | Lưu kết quả trung gian |
| Log vận hành | Error, slow query, general/audit log | Lỗi, truy vấn chậm, cấu hình logging | Chẩn đoán và kiểm toán |
| Backup | Full/incremental backup, binlog archive | Lịch backup và thời gian giữ | Phục hồi khi mất/hỏng dữ liệu |

Không phải tất cả các nhóm phải nằm trên cùng filesystem. Trong triển khai production, có thể tách data, redo, binlog, temporary files và backup sang volume riêng để cô lập mức tăng trưởng và I/O. Tách volume giúp quản lý rủi ro tốt hơn nhưng không thay thế giám sát dung lượng tổng thể.

## 2. Redo log: dung lượng và checkpoint

Redo log ghi lại thông tin cần thiết để InnoDB phát lại thay đổi khi khởi động sau crash. Đây là một phần của cơ chế write-ahead logging: redo phải được ghi bền vững trước khi page dữ liệu tương ứng được ghi về vị trí chính thức.

### Redo log tăng và được tái sử dụng như thế nào?

Redo log là vùng log vòng. InnoDB ghi log mới, đồng thời page cleaner flush các dirty page từ buffer pool xuống tablespace. Khi các page đủ cũ đã được flush và checkpoint tiến lên, vùng redo cũ mới có thể được tái sử dụng.

Nếu tốc độ sinh redo cao hơn khả năng flush page, checkpoint có thể bị tụt lại. Khi đó redo space bị chiếm nhiều hơn, hệ thống có thể phải tăng tốc flush hoặc làm chậm transaction để tránh ghi đè phần log chưa an toàn. Vì vậy, redo pressure có thể biểu hiện thành độ trễ ghi tăng ngay cả khi filesystem vẫn còn nhiều dung lượng.

### innodb_redo_log_capacity

Từ MySQL 8.0.30, `innodb_redo_log_capacity` là biến cấu hình chính để điều khiển dung lượng redo log tổng thể. Các phiên bản cũ hơn dùng `innodb_log_file_size` và `innodb_log_files_in_group`. MySQL quản lý các file redo trong thư mục `#innodb_redo` ở các phiên bản hiện đại; không đổi tên hoặc xóa thủ công các file này.

Kiểm tra cấu hình:

```sql
SHOW VARIABLES LIKE 'innodb_redo_log_capacity';
SHOW VARIABLES LIKE 'innodb_log_file_size';
SHOW VARIABLES LIKE 'innodb_log_files_in_group';
```

Các biến cũ có thể không còn phù hợp hoặc không tồn tại trên phiên bản mới. Dùng biến tương ứng với phiên bản đang chạy.

Tăng redo capacity có thể giúp hấp thụ burst ghi và giảm áp lực checkpoint trong ngắn hạn, nhưng không làm tăng tốc độ ghi vật lý của storage. Capacity quá lớn cũng có thể kéo dài thời gian crash recovery và chiếm thêm dung lượng cố định. Hãy chọn theo tốc độ sinh redo, khả năng flush, thời gian recovery chấp nhận được và dung lượng volume.

### Độ bền transaction và flush log

Hai cấu hình thường được đánh giá cùng nhau:

- `innodb_flush_log_at_trx_commit`: điều khiển cách InnoDB ghi và flush redo log.
- `sync_binlog`: điều khiển tần suất đồng bộ binary log xuống storage.

| `innodb_flush_log_at_trx_commit` | Hành vi khái quát | Rủi ro khi hệ điều hành hoặc máy mất điện |
|---|---|---|
| `1` | Ghi và flush redo log tại mỗi lần commit (có thể theo group commit) | Mức bảo vệ transaction đã commit cao nhất theo bảo đảm của storage |
| `2` | Ghi log tại mỗi commit, flush xuống storage định kỳ, thường khoảng mỗi giây | Có thể mất các commit gần nhất nếu OS hoặc máy mất điện |
| `0` | InnoDB ghi và flush log định kỳ, thường khoảng mỗi giây | Có thể mất các commit gần nhất nếu mysqld, OS hoặc máy gặp sự cố trước kỳ ghi/flush tiếp theo |

Với binary log, `sync_binlog = 1` yêu cầu đồng bộ binlog sau mỗi nhóm commit; giá trị lớn hơn 1 đồng bộ theo số nhóm commit, còn 0 để hệ điều hành quyết định thời điểm flush. Nếu cần bảo vệ chặt chẽ cả InnoDB và binlog, cấu hình thường được chọn là `innodb_flush_log_at_trx_commit = 1` cùng `sync_binlog = 1`, với điều kiện thiết bị lưu trữ thực thi đúng yêu cầu flush/fsync.

Độ bền thực tế còn phụ thuộc controller, cache thiết bị, nguồn điện dự phòng và hệ thống file. Không nên giảm mức flush chỉ để cải thiện benchmark khi chưa xác định RPO mà nghiệp vụ chấp nhận.

## 3. Undo log: MVCC, rollback và history list

Undo log lưu thông tin cần thiết để rollback thay đổi và dựng phiên bản cũ của hàng cho consistent read. InnoDB lưu undo record trong rollback segment thuộc undo tablespace hoặc vùng undo tương ứng theo cấu hình/phiên bản.

### Vì sao undo có thể tăng lâu?

Undo không chỉ tăng theo số transaction đang chạy. Những transaction thay đổi nhiều hàng tạo ra nhiều undo record; các read view cũ có thể buộc purge giữ lại phiên bản cũ lâu hơn. Một transaction mở lâu, kể cả chỉ đọc ở mức `REPEATABLE READ`, có thể giữ snapshot cũ và cản trở purge loại bỏ undo version không còn cần thiết.

Các nguyên nhân thường gặp:

- Transaction dài thực hiện UPDATE/DELETE trên nhiều hàng.
- Session `idle in transaction` không commit/rollback.
- Consistent read giữ read view lâu.
- Purge thread không theo kịp tốc độ sinh undo.
- Workload xóa/cập nhật lớn tạo lượng history cần dọn nhiều.

Khi history list length tăng kéo dài, dung lượng undo có thể tăng, purge tốn tài nguyên và truy vấn phải đi qua nhiều phiên bản hàng hơn. Không nên chỉ tăng undo tablespace để che một transaction đang giữ snapshot quá lâu.

### Theo dõi undo và purge

```sql
SHOW ENGINE INNODB STATUS;
```

Trong phần TRANSACTIONS, chú ý `History list length` và các transaction có thời gian chạy dài. Kết hợp với `information_schema.innodb_trx` để xác định transaction:

```sql
SELECT trx_id,
       trx_state,
       trx_started,
       trx_mysql_thread_id,
       trx_rows_modified,
       trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
```

`History list length` là chỉ số độ dài history list mà InnoDB báo cáo; không phải trực tiếp số byte trên đĩa và không nên quy đổi thẳng thành dung lượng undo. Cần đối chiếu xu hướng của chỉ số với dung lượng undo tablespace, transaction age và tốc độ giảm history sau khi blocker kết thúc.

### Undo tablespace và truncate

MySQL 8.0 thường dùng các undo tablespace riêng. Có thể kiểm tra biến liên quan:

```sql
SHOW VARIABLES LIKE 'innodb_undo%';
```

`innodb_undo_log_truncate` cho phép InnoDB tự truncate undo tablespace đủ điều kiện khi dung lượng vượt ngưỡng `innodb_max_undo_log_size`. Truncate chỉ có thể diễn ra khi undo tablespace được chọn không còn rollback segment đang hoạt động; transaction dài có thể trì hoãn quá trình này. Tên file, số lượng tablespace và khả năng cấu hình phụ thuộc phiên bản.

Không xóa trực tiếp file undo. Trước khi thay đổi cấu hình, kiểm tra phiên bản, trạng thái tablespace và hướng dẫn vận hành; hãy xử lý transaction giữ snapshot trước khi kỳ vọng dung lượng được thu hồi.

## 4. Binary log: replication, PITR và retention

Binary log ghi các sự kiện thay đổi ở cấp server. Replica đọc binlog từ source để tái thực thi hoặc áp dụng row event; công cụ backup dùng binlog cùng full backup để khôi phục đến một thời điểm (point-in-time recovery).

### Điều gì làm binlog tăng?

Dung lượng binlog phụ thuộc vào:

- Số lượng transaction ghi dữ liệu.
- `binlog_format` (`ROW`, `STATEMENT` hoặc `MIXED`).
- `binlog_row_image` và số cột được ghi trong row event.
- Kích thước transaction, bulk update và batch import.
- DDL, metadata event và tần suất rotate log.
- Thời gian retention và tốc độ replica/backup tiêu thụ log.

Với `ROW`, một UPDATE có thể ghi ảnh hàng thay đổi; một transaction cập nhật nhiều hàng có thể tạo binlog lớn hơn nhiều so với kích thước câu SQL ban đầu. Vì vậy, không dự báo dung lượng chỉ bằng số câu lệnh hoặc kích thước query text.

### Kiểm tra binlog

```sql
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'binlog_format';
SHOW VARIABLES LIKE 'binlog_row_image';
SHOW VARIABLES LIKE 'binlog_expire_logs_seconds';
SHOW BINARY LOGS;
```

`SHOW BINARY LOGS` hiển thị danh sách file và kích thước. Lấy mẫu định kỳ để tính lượng binlog phát sinh theo giờ/ngày. Nếu binary logging tắt, các lệnh binlog và cơ chế PITR dựa trên binlog không có dữ liệu để sử dụng.

### Retention và purge an toàn

`binlog_expire_logs_seconds` cấu hình thời gian tự hết hạn của binlog trên các phiên bản MySQL hỗ trợ biến này; `binlog_expire_logs_auto_purge` điều khiển việc tự động purge. Không giả định auto purge sẽ bảo vệ mọi replica đang chậm hoặc mọi bản backup ngoài server. Retention phải dài hơn khoảng thời gian cần cho replica bắt kịp và cửa sổ point-in-time recovery/backup; vận hành cần chủ động xác minh trước khi log hết hạn.

Có thể purge log cũ bằng lệnh MySQL:

```sql
PURGE BINARY LOGS BEFORE '2026-10-01 00:00:00';
```

Hoặc purge đến một file cụ thể (file chỉ định không bị xóa):

```sql
PURGE BINARY LOGS TO 'binlog.000125';
```

Trước khi purge, xác nhận:

1. Tất cả replica cần các file đó đã đọc và áp dụng đến vị trí an toàn.
2. Backup và quy trình PITR không còn cần đoạn binlog sắp xóa.
3. Có bản sao binlog ngoài server nếu chính sách yêu cầu lưu trữ lâu dài.
4. Thời gian retention mới vẫn đáp ứng RPO và thời gian khôi phục.

Không xóa file binlog bằng lệnh filesystem khi MySQL đang quản lý chúng. Dùng `PURGE BINARY LOGS` hoặc cơ chế tự hết hạn để MySQL cập nhật cả file index và trạng thái nội bộ. Không dùng lệnh reset log như một cách dọn dung lượng thông thường vì có thể ảnh hưởng replication và GTID.

### Binlog cache và transaction lớn

MySQL giữ transaction cache trong bộ nhớ theo các biến như `binlog_cache_size` và `binlog_stmt_cache_size`. Khi transaction vượt cache memory, phần dữ liệu có thể spill sang temporary file. Các counter `Binlog_cache_disk_use` và `Binlog_stmt_cache_disk_use` giúp nhận biết trường hợp này:

```sql
SHOW GLOBAL STATUS LIKE 'Binlog_cache%';
SHOW GLOBAL STATUS LIKE 'Binlog_stmt_cache%';
SHOW VARIABLES LIKE 'binlog_cache_size';
SHOW VARIABLES LIKE 'binlog_stmt_cache_size';
```

Transaction quá lớn có thể đồng thời làm tăng undo, redo, binlog cache file và độ trễ replica. Chia batch có thể giảm peak resource, nhưng cần giữ đúng tính nguyên tử và quy tắc nghiệp vụ.

## 5. Relay log trên replica

Replica nhận binlog từ source và lưu vào relay log trước khi applier thực thi. Nếu replica ngừng apply hoặc chậm hơn tốc độ source phát sinh binlog, relay log có thể tăng nhanh và chiếm đầy filesystem.

Kiểm tra trạng thái replication:

```sql
SHOW REPLICA STATUS\G
```

Chú ý các trường như `Relay_Log_Space`, `Relay_Log_File`, `Relay_Source_Log_File`, trạng thái receiver/applier và lỗi SQL thread. Tên trường có thể khác trên phiên bản cũ dùng thuật ngữ `SHOW SLAVE STATUS`.

`relay_log_space_limit` có thể giới hạn tổng dung lượng relay log trên các cấu hình hỗ trợ. Khi đạt giới hạn, receiver có thể phải chờ cho đến khi applier giải phóng không gian. Đây là cơ chế backpressure, không phải cách xử lý nguyên nhân replica chậm.

Không xóa relay log trực tiếp. Hãy xử lý lỗi applier, dung lượng I/O, transaction dài hoặc độ trễ mạng; sau đó để replication quản lý việc purge relay log theo trạng thái đã áp dụng.

## 6. Temporary files và temporary tablespace

MySQL tạo nhiều loại file tạm:

- Memory-mapped files do TempTable dùng khi ngân sách RAM đạt ngưỡng.
- Internal temporary tables trên đĩa do InnoDB quản lý.
- File sort/merge và file tạm khác trong `tmpdir`.
- File tạm khi thực hiện một số thao tác DDL hoặc import/export.
- File transaction cache khi binlog cache vượt bộ nhớ.

### tmpdir

`tmpdir` là thư mục MySQL dùng cho một số file tạm ở cấp server. Kiểm tra:

```sql
SHOW VARIABLES LIKE 'tmpdir';
```

Trên các nền tảng hỗ trợ unlink file đang mở, TempTable có thể tạo file mmap trong `tmpdir`, mở file rồi xóa tên file ngay; vì vậy file không nhất thiết xuất hiện khi liệt kê thư mục, dù dung lượng vẫn được giữ bởi file descriptor đang mở. Kiểm tra filesystem và dung lượng thực tế thay vì chỉ tìm tên file.

Nếu `tmpdir` có nhiều đường dẫn, MySQL có thể chọn một thư mục phù hợp theo nền tảng/cấu hình. Mọi thư mục phải có đủ dung lượng, quyền ghi và cùng đáp ứng yêu cầu vận hành. Không đặt `tmpdir` trên filesystem dễ bị đầy bởi log hoặc file không liên quan.

### InnoDB temporary tablespace

InnoDB sử dụng temporary tablespace cho internal temporary tables trên đĩa và các temporary object liên quan. Có global temporary tablespace và session temporary tablespaces tùy phiên bản. File global thường được biết đến là `ibtmp1`; file/session tablespace được quản lý theo vòng đời connection hoặc server.

Temporary tablespace có thể tăng trong workload lớn. Dung lượng file có thể không giảm ngay sau khi một truy vấn kết thúc; cách thu hồi phụ thuộc loại tablespace và phiên bản. Một số file được tái sử dụng cho truy vấn sau; global temporary tablespace được khởi tạo lại khi server restart theo quy tắc của phiên bản. Không xóa `ibtmp1` hoặc session temporary file khi mysqld đang chạy.

### innodb_tmpdir

`innodb_tmpdir` điều khiển vị trí một số file tạm do InnoDB tạo trong quá trình online ALTER TABLE, ví dụ file sort tạm trong một số thao tác rebuild index. Nó không thay thế `tmpdir` cho mọi loại file tạm. Kiểm tra:

```sql
SHOW VARIABLES LIKE 'innodb_tmpdir';
SHOW VARIABLES LIKE 'tmpdir';
```

Nếu tách thư mục cho DDL, cần bảo đảm filesystem đích có đủ dung lượng cho thao tác rebuild, quyền truy cập của mysqld và khả năng chịu I/O. DDL lớn còn cần dung lượng cho bảng/index mới trong khi dữ liệu cũ vẫn tồn tại.

## 7. Dung lượng cho DDL và thay đổi schema

Một số thao tác `ALTER TABLE` phải tạo cấu trúc mới rồi xây index trước khi thay thế cấu trúc cũ. Trong thời gian đó, dung lượng có thể tăng đáng kể vì cùng lúc tồn tại dữ liệu cũ, bản sao mới, index, sort file và log phát sinh từ workload đang chạy.

Trước DDL lớn, cần ước lượng:

- Kích thước bảng và index hiện tại.
- Dung lượng cấu trúc mới dự kiến, gồm index bổ sung.
- Temporary sort files và vùng staging của engine.
- Redo/undo/binlog phát sinh trong suốt thời gian DDL.
- Dung lượng cho replica và backup nếu DDL được replicate hoặc snapshot.
- Phần trống để workload bình thường tiếp tục ghi trong lúc DDL chạy.

Không dùng kích thước file hiện tại làm toàn bộ ước lượng. Một rebuild index có thể cần thêm không gian gần bằng kích thước dữ liệu/index liên quan, tùy thuật toán và loại thay đổi. Thử nghiệm trên bản sao có kích thước tương đương; kiểm tra khả năng dùng `ALGORITHM` và `LOCK` phù hợp trong `ALTER TABLE` theo phiên bản, engine và loại thay đổi. `EXPLAIN` truy vấn SELECT không dự báo trực tiếp dung lượng DDL.

## 8. Lập kế hoạch dung lượng tổng thể

### Công thức dự báo

Với mỗi nhóm lưu trữ, ước lượng:

```text
Dung lượng cần giữ
  = dung lượng nền
  + tốc độ tăng trung bình mỗi ngày × số ngày retention
  + phần tăng trong workload đỉnh
  + headroom cho bảo trì và phục hồi
```

Ví dụ, nếu binlog phát sinh trung bình 18 GB/ngày và cần giữ 10 ngày để replica/backup có thể bắt kịp, mức cơ sở là khoảng 180 GB. Sau đó cộng thêm biên cho ngày cao điểm, transaction lớn và thời gian xử lý sự cố. Đây là phép ước lượng; phải dùng số liệu đo trong thời gian đủ dài và tính đến peak, không chỉ dùng một ngày yên tĩnh.

### Bảng kế hoạch theo nhóm

| Nhóm | Cách dự báo | Dữ liệu cần đo | Chính sách |
|---|---|---|---|
| Data/index | Tăng hàng/ngày × thời gian giữ | Tablespace size, index size, growth rate | Archive/partition/retention |
| Redo | `innodb_redo_log_capacity` và tốc độ sinh redo | Redo capacity, checkpoint age, write throughput | Dành đủ capacity và headroom recovery |
| Undo | Peak update/delete và thời gian transaction/snapshot dài | Undo tablespace, history list length, transaction age | Giới hạn transaction, purge và truncate |
| Binary log | GB binlog/ngày × retention days | `SHOW BINARY LOGS`, binlog generation rate | Retention, backup archive, replica lag |
| Relay log | Tốc độ nhận log × thời gian replica bị chậm | `Relay_Log_Space`, applier lag | Sửa nguyên nhân lag, giới hạn và cảnh báo |
| Temporary | Peak concurrent temp workload và DDL | tmpdir, temp tablespace, Created_tmp counters, mmap | Tách volume, tối ưu query, giới hạn tài nguyên |
| Backup | Kích thước full + incremental + binlog archive | Backup catalog, compression ratio, retention | Lưu ngoài volume dữ liệu chính |

### Headroom

Không vận hành filesystem ở sát 100%. Cần để lại phần trống cho burst ghi, DDL, crash recovery, log rotate và thao tác khẩn cấp. Mức 20-30% dung lượng trống có thể dùng làm điểm bắt đầu cho một số hệ thống, nhưng không phải quy tắc của MySQL; workload biến động mạnh hoặc DDL lớn có thể cần nhiều hơn.

Nếu các loại file nằm trên nhiều volume, lập kế hoạch riêng cho từng volume. Tổng dung lượng còn trống trên toàn server không giúp được nếu riêng volume binlog hoặc `tmpdir` đã đầy.

## 9. Monitoring và cảnh báo

### Kiểm tra nhanh biến và status

```sql
SHOW VARIABLES LIKE 'innodb_redo_log_capacity';
SHOW VARIABLES LIKE 'innodb_undo%';
SHOW VARIABLES LIKE 'binlog_expire_logs_seconds';
SHOW VARIABLES LIKE 'binlog_expire_logs_auto_purge';
SHOW VARIABLES LIKE 'tmpdir';
SHOW VARIABLES LIKE 'innodb_tmpdir';

SHOW GLOBAL STATUS LIKE 'Created_tmp%';
SHOW GLOBAL STATUS LIKE 'Binlog_cache%';
SHOW GLOBAL STATUS LIKE 'Binlog_stmt_cache%';
SHOW BINARY LOGS;
SHOW ENGINE INNODB STATUS;
```

### Theo dõi file I/O qua Performance Schema

Nếu instrument file được bật, có thể xem các file đang có nhiều I/O:

```sql
SELECT FILE_NAME,
       EVENT_NAME,
       COUNT_READ,
       COUNT_WRITE,
       SUM_NUMBER_OF_BYTES_READ,
       SUM_NUMBER_OF_BYTES_WRITE
FROM performance_schema.file_summary_by_instance
ORDER BY SUM_NUMBER_OF_BYTES_WRITE DESC
LIMIT 30;
```

Bảng này là thống kê I/O theo file, không phải bảng đo dung lượng hiện tại trên filesystem. Dùng nó để tìm file có hoạt động đọc/ghi cao; dùng công cụ hệ điều hành hoặc hệ thống giám sát storage để đo bytes used, free space và tốc độ tăng file.

### Bộ cảnh báo nên có

- Filesystem còn dưới ngưỡng vận hành, ví dụ 25%, 15% và 10% free; ngưỡng thực tế dựa trên tốc độ tăng và thời gian phản ứng.
- Binlog phát sinh mỗi giờ/ngày vượt baseline hoặc retention dự kiến.
- Replica lag tăng và `Relay_Log_Space` tăng liên tục.
- `History list length` tăng kéo dài, transaction lâu chưa kết thúc.
- Temp tablespace hoặc `tmpdir` tăng bất thường.
- Redo checkpoint pressure hoặc tốc độ flush không theo kịp workload.
- DDL/backup đang chạy nhưng volume không còn đủ headroom.

## 10. Runbook khi dung lượng gần đầy

Khi cảnh báo filesystem gần đầy, ưu tiên xác định loại file và tốc độ tăng trước khi xóa bất cứ thứ gì:

1. Xác định volume đầy và thư mục chiếm dung lượng bằng công cụ hệ điều hành.
2. Đối chiếu file với data, redo, undo, binlog, relay log, temporary tablespace, `tmpdir`, log vận hành hoặc backup.
3. Kiểm tra MySQL còn hoạt động và có transaction/DDL/replication nào đang tạo file nhanh không.
4. Nếu binlog tăng, kiểm tra replica và backup/PITR trước khi purge bằng SQL.
5. Nếu undo tăng, tìm transaction dài và snapshot cũ; xử lý nguyên nhân giữ history, sau đó theo dõi purge/truncate.
6. Nếu temporary storage tăng, xác định query/DDL tạo temp, cân nhắc dừng hoặc điều phối workload theo quy trình vận hành.
7. Nếu relay log tăng, kiểm tra applier error, replication lag và tốc độ apply; không xóa relay log thủ công.
8. Nếu data/redo volume thiếu chỗ, bổ sung storage hoặc điều phối ghi theo kế hoạch khẩn cấp; không xóa file InnoDB để giải phóng chỗ.
9. Sau khi ổn định, cập nhật dự báo tăng trưởng, retention, cảnh báo và runbook.

**Không xóa trực tiếp** file redo, undo, binlog, relay log, `ibtmp1` hoặc file tablespace khi mysqld đang quản lý chúng. Xóa nhầm có thể làm server không khởi động, mất khả năng crash recovery, phá replication hoặc khiến dữ liệu không thể khôi phục.

## 11. Thiết kế retention và backup đồng bộ

Retention của binlog phải liên kết với backup. Ví dụ, nếu full backup chạy mỗi tuần và cần PITR trong 14 ngày, phải bảo đảm có đầy đủ binlog từ thời điểm backup phù hợp đến thời điểm cần khôi phục. Xóa binlog trước khi bản backup tương ứng và chuỗi log được lưu an toàn có thể làm mất khả năng PITR.

Tương tự, relay log cần tồn tại đủ để replica tiếp tục sau gián đoạn. Nếu replica ngừng nhiều ngày, source có thể hết binlog cần thiết trước khi replica bắt kịp; khi đó cần resync từ backup hoặc snapshot mới.

Backup nên được lưu trên storage độc lập với volume dữ liệu chính và cần kiểm tra restore định kỳ. Một file backup nằm cùng volume với data không bảo vệ được khi volume hoặc thiết bị bị mất.

## 12. Checklist thiết kế dung lượng

Trước khi đưa MySQL vào production, xác nhận:

- [ ] Data, redo, undo, binlog, relay log, temporary files và backup đã được phân loại.
- [ ] Biết rõ filesystem chứa từng nhóm file và tốc độ tăng theo ngày.
- [ ] Redo capacity phù hợp với write burst và thời gian crash recovery.
- [ ] `innodb_flush_log_at_trx_commit` và `sync_binlog` đáp ứng yêu cầu durability/RPO.
- [ ] Transaction có giới hạn thời gian; theo dõi history list length và purge.
- [ ] Binlog retention đủ cho replica và PITR; có quy trình purge được phê duyệt.
- [ ] Relay log và replication lag có cảnh báo.
- [ ] `tmpdir`, InnoDB temporary tablespace và `innodb_tmpdir` có đủ dung lượng.
- [ ] DDL lớn có ước lượng dung lượng tạm và cửa sổ bảo trì.
- [ ] Backup nằm ngoài volume dữ liệu chính và đã thử restore.
- [ ] Mỗi filesystem có headroom và ngưỡng cảnh báo theo tốc độ tăng thực tế.
- [ ] Runbook đầy đĩa chỉ dùng cơ chế MySQL hỗ trợ, không xóa file đang được server quản lý.

## 13. Bài thực hành

Trên instance thử nghiệm hoặc môi trường staging:

1. Ghi nhận `innodb_redo_log_capacity`, `innodb_flush_log_at_trx_commit`, `sync_binlog` và mô tả ảnh hưởng của từng cấu hình đến durability.
2. Chạy một workload UPDATE lớn, theo dõi `SHOW ENGINE INNODB STATUS`, history list length và transaction age.
3. Mở một transaction đọc lâu ở `REPEATABLE READ`, chạy UPDATE/DELETE từ session khác và quan sát undo history/purge. Kết thúc transaction rồi theo dõi history giảm.
4. Bật binary logging trên môi trường thử nghiệm, tạo workload ghi và dùng `SHOW BINARY LOGS` để tính binlog GB/ngày.
5. Kiểm tra `binlog_expire_logs_seconds`, mô phỏng replica lag và xác định thời điểm an toàn để purge log cũ.
6. Tạo một transaction ghi lớn để quan sát `Binlog_cache_disk_use` và temporary file nếu cache memory bị vượt.
7. Chạy truy vấn GROUP BY/sort lớn, lấy delta `Created_tmp%` và theo dõi filesystem chứa `tmpdir` cùng InnoDB temporary tablespace.
8. Lập bảng dự báo 30 ngày cho data, redo, undo, binlog, relay log, temporary storage và backup; tính headroom riêng cho từng volume.
9. Viết runbook khi binlog volume đạt 90% và một runbook khác khi `tmpdir` gần đầy. Nêu rõ dữ liệu nào được phép purge và dữ liệu nào phải giữ.

## Ghi nhớ

- Redo phục vụ crash recovery; undo phục vụ rollback và MVCC; binary log phục vụ replication/PITR; relay log là hàng đợi sự kiện trên replica.
- Transaction dài và read view cũ có thể giữ undo, khiến purge chậm và tablespace tăng.
- Binlog retention phải khớp với nhu cầu replica và chuỗi backup/PITR; purge bằng SQL, không xóa file trực tiếp.
- Temporary files có thể nằm ở `tmpdir`, memory-mapped storage hoặc InnoDB temporary tablespace; các counter không phản ánh mọi đường spill.
- DDL lớn cần headroom cho dữ liệu cũ, cấu trúc mới, index, temporary sort và log phát sinh.
- Dự báo theo tốc độ tăng và retention, cộng peak workload cùng headroom; lập kế hoạch riêng cho từng filesystem.
- Khi gần đầy đĩa, xác định đúng loại file và xử lý theo runbook; không xóa file InnoDB/binlog/relay log mà MySQL đang quản lý.
