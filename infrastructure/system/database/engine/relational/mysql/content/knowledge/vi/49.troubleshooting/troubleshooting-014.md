# Disk full, table is full và temporary space cạn

MySQL có thể ngừng ghi dữ liệu, không tạo được bảng tạm hoặc thất bại khi chạy `ALTER TABLE`, `CREATE INDEX`, `ORDER BY` hay `GROUP BY` khi không còn đủ dung lượng. Thông báo thường gặp gồm `No space left on device`, `Disk full`, `The table is full`, hoặc lỗi tạo file tạm. Những lỗi này có thể xuất phát từ filesystem chứa data directory, tablespace InnoDB, binary log, relay log, thư mục `tmpdir`, giới hạn kích thước của engine hoặc quota của hệ điều hành.

Không nên xử lý mọi lỗi `Table is full` bằng cách xóa file trong thư mục dữ liệu. Trước tiên cần xác định **filesystem nào đã đầy**, **MySQL đang ghi loại file nào**, và **giới hạn nào đã chạm tới**. Sau đó giải phóng hoặc mở rộng đúng vùng lưu trữ, bảo toàn file phục hồi và xác nhận database có thể ghi trở lại.

## 1. Phân biệt các dạng hết dung lượng

Một server MySQL có nhiều vùng lưu trữ với vòng đời và cách quản lý khác nhau:

| Vùng lưu trữ | Nội dung | Dấu hiệu khi cạn |
|---|---|---|
| Data directory (`datadir`) | File bảng, tablespace, system tables, metadata và dữ liệu InnoDB | INSERT/UPDATE/DDL thất bại; server có thể gặp lỗi khi ghi dữ liệu hoặc khởi động. |
| InnoDB system tablespace | File cấu hình bởi `innodb_data_file_path`, thường có `ibdata1` | Không thể cấp phát thêm page nếu chạm giới hạn autoextend hoặc filesystem đầy. |
| File-per-table tablespace | File `.ibd` của bảng InnoDB khi bật `innodb_file_per_table` | Bảng cụ thể không thể mở rộng nếu filesystem/quota hết chỗ. |
| InnoDB temporary tablespace | Temporary tablespace và session temporary tablespace | Truy vấn cần bảng tạm InnoDB hoặc thao tác tạm thời thất bại. |
| `tmpdir` | File tạm cho một số phép sort, merge, temp operation và công cụ | Query/DDL thất bại với lỗi tạo file tạm dù data volume vẫn còn chỗ. |
| Binary log | Lịch sử transaction phục vụ replication/PITR | Ghi transaction có thể thất bại nếu log không thể mở rộng; replica/PITR cũng bị ảnh hưởng. |
| Relay log | Event nhận từ source trên replica | Receiver không thể ghi relay log và replication ngừng nhận dữ liệu. |
| Backup/archive | Dump, physical backup, log archive | Job backup thất bại hoặc chiếm hết volume dùng chung. |
| Filesystem inode/quota | Metadata file hoặc giới hạn dung lượng theo user/project | Còn byte trống nhưng không tạo thêm file được, hoặc user `mysql` chạm quota. |

`ERROR 1114: The table is full` không nhất thiết có nghĩa toàn bộ ổ đĩa đã đầy. Lỗi có thể do giới hạn kích thước engine/table, giới hạn tablespace, quota hoặc vùng temporary. Ngược lại, filesystem đầy có thể xuất hiện dưới mã lỗi khác như `1021`, `1030` hoặc lỗi hệ điều hành `errno 28`.

## 2. Nhận diện mã lỗi và dấu hiệu

| Thông báo/mã | Ý nghĩa thường gặp | Hướng kiểm tra |
|---|---|---|
| `No space left on device` / `errno: 28` | Hệ điều hành không thể cấp phát thêm block hoặc inode. | `df -h`, `df -i`, quota, mount và thư mục ghi file. |
| `1021: Disk full ...` | MySQL không ghi được file dữ liệu hoặc file tạm. | Đường dẫn được nêu trong lỗi, filesystem và quyền ghi. |
| `1114: The table is full` | Engine hoặc tablespace không thể nhận thêm dữ liệu. | Engine, giới hạn bảng, tablespace và filesystem. |
| `1030: Got error ... from storage engine` | Lỗi storage engine; mã lỗi phụ thuộc nguyên nhân bên dưới. | MySQL error log, InnoDB status và OS error. |
| Lỗi tạo `#sql...` hoặc file tạm | DDL/query không tạo được temporary file/table. | `tmpdir`, temporary tablespace, sort và dung lượng tạm. |
| Replica I/O error khi ghi relay log | Replica không thể lưu event nhận từ source. | Relay log path, disk/inode/quota và source connectivity. |
| Backup job hết chỗ | Destination backup hoặc volume staging đầy. | Backup target, retention, file đang ghi và dung lượng archive. |

Ghi lại toàn bộ error message, thời điểm, query/DDL, schema/table, connection id và đường dẫn file nếu có. Đối chiếu với MySQL error log và log hệ điều hành. Một lỗi xảy ra khi chạy `ALTER TABLE` thường cần nhiều dung lượng tạm hơn dung lượng tăng thêm của bảng, vì MySQL có thể phải xây dựng bản sao hoặc index trung gian.

## 3. Xác định filesystem nào đầy

### Linux

Kiểm tra dung lượng theo mount:

```bash
df -hT
df -i
```

- `df -hT` cho biết dung lượng block, phần đã dùng, còn trống, filesystem type và mount point.
- `df -i` cho biết inode đã dùng/còn trống. Filesystem có thể hết inode dù vẫn còn dung lượng byte.

Xác định đường dẫn MySQL dùng:

```bash
sudo du -xhd1 /var/lib/mysql | sort -h
sudo du -xhd1 /var/tmp | sort -h
sudo du -xhd1 /tmp | sort -h
```

Thay đường dẫn theo môi trường thực tế. `-x` giữ phép đo trong cùng filesystem, tránh cộng nhầm các mount khác. Dùng `du` ở cấp thư mục trước để tìm vùng tăng bất thường; không chạy quét sâu liên tục trên volume production đang chịu tải nếu nó gây thêm I/O.

Kiểm tra file đã bị xóa nhưng vẫn được tiến trình giữ mở:

```bash
sudo lsof +L1
```

Một log file bị xóa khỏi directory nhưng tiến trình vẫn mở file có thể tiếp tục chiếm block cho đến khi file descriptor được đóng. Hãy dùng cơ chế log rotation/reopen đúng dịch vụ. Không kill `mysqld` chỉ để giải phóng file descriptor nếu chưa đánh giá tác động và phương án phục hồi.

Nếu tổ chức dùng quota, kiểm tra quota của user `mysql`, project quota hoặc quota của filesystem. Nếu chạy trên cloud volume, kiểm tra cả kích thước volume, giới hạn IOPS/throughput và trạng thái resize.

### Windows

Kiểm tra volume và dung lượng trống:

```powershell
Get-Volume | Select-Object DriveLetter, FileSystemLabel, FileSystem, Size, SizeRemaining
Get-PSDrive -PSProvider FileSystem
```

Xác định đường dẫn `datadir`, `tmpdir` và log trong file cấu hình MySQL. Kiểm tra volume chứa từng đường dẫn, quota và quyền của tài khoản service MySQL. Nếu MySQL chạy như Windows service, tài khoản service có thể có quyền khác với tài khoản quản trị đang mở PowerShell.

### Container và Kubernetes

Trong Docker, phân biệt filesystem writable layer của container, named volume và bind mount. Kiểm tra mount thực tế và dung lượng trên host. `docker system df` có thể giúp kiểm kê image/container/volume; không chạy `docker system prune --volumes` hoặc xóa volume theo phỏng đoán vì có thể xóa dữ liệu database.

Trong Kubernetes, kiểm tra PersistentVolume/PersistentVolumeClaim, node ephemeral storage, `emptyDir`, container ephemeral-storage limit và event `DiskPressure`. `tmpdir` đặt trong filesystem container hoặc `emptyDir` có thể đầy trong khi PVC chứa data directory vẫn còn dung lượng. Đọc event và mount path của Pod trước khi thay đổi storage.

## 4. Kiểm kê đường dẫn lưu trữ MySQL

Nếu vẫn có thể kết nối quản trị, lấy các biến quan trọng:

```sql
SHOW VARIABLES LIKE 'datadir';
SHOW VARIABLES LIKE 'tmpdir';
SHOW VARIABLES LIKE 'socket';
SHOW VARIABLES LIKE 'log_error';
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'log_bin_basename';
SHOW VARIABLES LIKE 'relay_log';
SHOW VARIABLES LIKE 'relay_log_basename';
SHOW VARIABLES LIKE 'innodb_data_home_dir';
SHOW VARIABLES LIKE 'innodb_data_file_path';
SHOW VARIABLES LIKE 'innodb_file_per_table';
SHOW VARIABLES LIKE 'innodb_temp_data_file_path';
SHOW VARIABLES LIKE 'innodb_temp_tablespaces_dir';
```

Không phải mọi biến đều tồn tại trên tất cả phiên bản MySQL. Nếu một truy vấn không trả hàng hoặc báo biến không tồn tại, kiểm tra `SHOW VARIABLES LIKE 'pattern'` và tài liệu đúng phiên bản. `tmpdir` có thể chứa nhiều đường dẫn; cách phân tách tùy hệ điều hành.

Kiểm tra dung lượng bảng theo schema:

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ENGINE,
    TABLE_ROWS,
    DATA_LENGTH,
    INDEX_LENGTH,
    DATA_FREE,
    ROUND((DATA_LENGTH + INDEX_LENGTH) / 1024 / 1024, 1) AS total_mb
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_TYPE = 'BASE TABLE'
  AND TABLE_SCHEMA NOT IN (
      'mysql', 'sys', 'performance_schema', 'information_schema'
  )
ORDER BY DATA_LENGTH + INDEX_LENGTH DESC
LIMIT 30;
```

Với InnoDB, `TABLE_ROWS` thường là ước lượng và `DATA_FREE` không phải phép đo chính xác dung lượng có thể thu hồi ngay. Dùng các giá trị này để tìm bảng lớn, sau đó đối chiếu filesystem và tablespace thực tế. Không cộng `DATA_FREE` của mọi bảng rồi coi đó là dung lượng chắc chắn có thể giải phóng.

Kiểm tra binary log:

```sql
SHOW BINARY LOGS;
SHOW BINARY LOG STATUS;
```

Trên phiên bản cũ, `SHOW MASTER STATUS` có thể là tên lệnh tương ứng. Kiểm tra kích thước log, retention, replica đang đọc đến đâu và nhu cầu PITR trước khi xóa log cũ.

## 5. Kiểm tra giới hạn InnoDB tablespace

### System tablespace

`innodb_data_file_path` xác định file system tablespace, thường có dạng:

```text
ibdata1:12M:autoextend
```

Nếu cấu hình có giới hạn `max`, ví dụ `autoextend:max:...`, system tablespace có thể chạm giới hạn đó dù filesystem vẫn còn chỗ. Cần kiểm tra cấu hình thực tế và phiên bản, không suy luận chỉ từ tên file `ibdata1`.

### File-per-table

Khi `innodb_file_per_table=ON`, bảng InnoDB thường có tablespace riêng trong file `.ibd`. File có thể tăng theo dữ liệu/index và cần chỗ trên filesystem chứa data directory hoặc tablespace path tùy cấu hình. Việc xóa hàng không nhất thiết làm file `.ibd` nhỏ lại ngay; phần không còn dùng có thể được tái sử dụng bên trong tablespace.

### Temporary tablespace

InnoDB dùng temporary tablespace cho một số hoạt động tạm. `innodb_temp_data_file_path` điều khiển shared temporary tablespace trên các phiên bản có biến này. Nếu cấu hình giới hạn kích thước tối đa, tác vụ cần thêm temporary space có thể thất bại khi chạm ngưỡng. Temporary tablespace có vòng đời riêng; không xóa file của nó bằng tay khi server đang chạy.

Xem trạng thái InnoDB:

```sql
SHOW ENGINE INNODB STATUS\G
```

Đọc các phần liên quan đến transaction, history list, file I/O, pending I/O và lỗi gần đây. Nếu có quyền, kiểm tra metadata tablespace trong `INFORMATION_SCHEMA.FILES` và các bảng InnoDB/Performance Schema phù hợp phiên bản.

## 6. Temporary space cạn khi chạy query hoặc DDL

MySQL có thể cần không gian tạm cho:

- `ORDER BY`, `GROUP BY`, `DISTINCT` và một số phép sort/merge.
- Derived table, CTE, window function hoặc truy vấn cần materialize kết quả trung gian.
- Join không có index phù hợp hoặc xử lý tập kết quả trung gian lớn.
- `ALTER TABLE`, tạo/rebuild index, đổi kiểu cột hoặc một số online DDL.
- Internal temporary table vượt ngưỡng lưu trong memory.
- Temporary table do ứng dụng tạo và giữ lâu trong session.

Kiểm tra các biến liên quan:

```sql
SHOW VARIABLES LIKE 'tmp_table_size';
SHOW VARIABLES LIKE 'max_heap_table_size';
SHOW VARIABLES LIKE 'temptable_max_ram';
SHOW VARIABLES LIKE 'temptable_max_mmap';
SHOW VARIABLES LIKE 'temptable_use_mmap';
SHOW VARIABLES LIKE 'tmpdir';
```

Các biến `temptable_*` và hành vi internal temporary table phụ thuộc phiên bản MySQL. Một số biến đã thay đổi hoặc deprecated qua các bản 8.0; chỉ điều chỉnh biến được phiên bản hiện tại hỗ trợ. `tmp_table_size` và `max_heap_table_size` có vai trò khác nhau tùy internal temporary table engine và loại bảng tạm. Tăng giới hạn memory có thể làm tăng RAM tiêu thụ trên nhiều connection đồng thời, không phải cách xử lý mặc định khi disk tạm đầy.

Theo dõi counter tạm:

```sql
SHOW GLOBAL STATUS LIKE 'Created_tmp%';
```

Các counter như `Created_tmp_tables` và `Created_tmp_disk_tables` giúp quan sát xu hướng internal temporary table. Chúng không chỉ ra một mình truy vấn nào gây đầy disk và không nhất thiết phản ánh toàn bộ file tạm theo cùng cách trên mọi phiên bản. Kết hợp slow query log, Performance Schema statement history, processlist và thời điểm lỗi.

Để tìm truy vấn tốn temporary space:

1. Xác định query/DDL đang chạy tại thời điểm dung lượng tăng.
2. Đọc `EXPLAIN` và kiểm tra sort, temporary table, join order, index và số hàng ước lượng.
3. Kiểm tra truy vấn có materialize tập dữ liệu quá lớn hoặc trả nhiều cột không cần thiết không.
4. Thử thêm index phù hợp hoặc viết lại query trên staging với dữ liệu đại diện.
5. Nếu query hợp lệ nhưng cần dung lượng lớn, cấp temporary filesystem đủ lớn và giám sát mức tăng.

Không kết luận mọi `Using temporary` hoặc `Using filesort` đều là lỗi. Đây là dấu hiệu về cách thực thi; cần đo dung lượng, thời gian và tác động thực tế.

## 7. Vì sao ALTER TABLE có thể cần nhiều dung lượng hơn dự kiến?

Một thay đổi schema có thể tạo bảng hoặc index trung gian, ghi dữ liệu mới, giữ bản cũ cho đến khi hoàn tất và dùng file tạm trên filesystem. Vì vậy, thêm một cột hoặc index có thể cần nhiều dung lượng trống hơn phần kích thước cuối cùng tăng thêm.

Trước khi chạy DDL lớn:

- Ước lượng kích thước bảng, index và số hàng cần rebuild.
- Xác định thuật toán DDL khả dụng (`INSTANT`, `INPLACE` hoặc `COPY`) trên đúng phiên bản và loại thay đổi.
- Xác định `tmpdir`, data directory và tablespace nằm trên filesystem nào.
- Dự trù dung lượng cho bản sao tạm, sort file, redo/undo và binary log phát sinh.
- Kiểm tra replica lag, thời gian giữ metadata lock và cửa sổ bảo trì.
- Thử trên bản sao dữ liệu có kích thước đại diện.

Không ép `ALGORITHM=INPLACE` hoặc `LOCK=NONE` nếu thao tác không hỗ trợ. Hãy dùng `EXPLAIN ALTER TABLE` khi phiên bản MySQL hỗ trợ để xem kế hoạch DDL; nếu không, thử trên staging và đọc tài liệu đúng phiên bản. `OPTIMIZE TABLE` cũng có thể rebuild bảng và cần thêm dung lượng đáng kể; không dùng nó như thao tác dọn disk khẩn cấp.

## 8. Kiểm tra binary log và relay log chiếm dung lượng

Binary log có thể tăng nhanh khi workload ghi lớn, retention dài hoặc replica/PITR cần giữ log. Kiểm tra:

```sql
SHOW BINARY LOGS;
SHOW VARIABLES LIKE 'binlog_expire_logs_seconds';
SHOW VARIABLES LIKE 'max_binlog_size';
SHOW REPLICA STATUS\G
```

Nếu có nhiều replica/channel, kiểm tra từng channel và xác nhận replica đã nhận/applied đến vị trí phù hợp. Đối chiếu backup/PITR policy để xác định log nào còn cần giữ.

Khi đã xác minh một dải log không còn cần cho replica, recovery hoặc audit, dùng lệnh MySQL để purge theo chính sách:

```sql
PURGE BINARY LOGS TO 'binlog.000125';
```

Lệnh trên xóa các binary log cũ hơn file được chỉ định, không xóa file đích. Tên file chỉ là ví dụ; phải lấy danh sách thật từ `SHOW BINARY LOGS` và kiểm tra replica/backup trước khi chạy. Không purge file mà replica còn cần hoặc PITR vẫn phụ thuộc.

Không dùng `rm`/Explorer để xóa binary log trong data directory. Xóa file trực tiếp khiến index và metadata log của MySQL không đồng bộ. Relay log cũng do replica quản lý; không xóa thủ công khi server đang chạy. Nếu cần khôi phục relay log, dùng quy trình replication recovery phù hợp.

Thiết lập retention có chủ đích bằng `binlog_expire_logs_seconds` theo yêu cầu backup, replication, audit và thời gian xử lý sự cố. Không giảm retention trong lúc đang điều tra một replica bị chậm hoặc backup chưa xác nhận.

## 9. Xác định session hoặc tác vụ đang làm tăng dung lượng

Khi server còn hoạt động, xem các session và câu lệnh:

```sql
SHOW FULL PROCESSLIST;
```

Tìm query chạy lâu, trạng thái `Creating sort index`, `Copying to tmp table`, `altering table`, `Creating index` hoặc session giữ temporary table. Các trạng thái có thể thay đổi theo phiên bản và không tự chứng minh session đó là nguyên nhân.

Nếu Performance Schema được bật, có thể tìm statement đang chạy và lịch sử gần đây qua các bảng `events_statements_current`/`events_statements_history_long`, kết hợp `performance_schema.threads` để lấy connection id. Tên cột và dữ liệu có sẵn phụ thuộc cấu hình consumer/instrumentation.

Chỉ dừng query khi đã xác định owner, tác động và cách ứng dụng phục hồi. `KILL QUERY` dừng câu lệnh hiện tại; `KILL CONNECTION` đóng session. Với DML InnoDB, rollback có thể cần thời gian và vẫn dùng undo/log I/O; không kỳ vọng disk được giải phóng ngay lập tức. Với DDL, hành vi dừng/cleanup tùy loại DDL và giai đoạn thực thi.

Nếu truy vấn tạm thời gây đầy `tmpdir`, hủy query có thể giải phóng file tạm sau khi MySQL dọn dẹp. Xác nhận filesystem sau khi cleanup hoàn tất, không xóa file đang mở bằng tay.

## 10. Runbook xử lý khi disk gần đầy hoặc đã đầy

### Bước 1: Dừng tăng trưởng có kiểm soát

Xác định ứng dụng, batch, ETL, backup hoặc DDL nào đang tạo tải ghi/tạm bất thường. Tạm hoãn job không thiết yếu hoặc dừng đợt triển khai đang tạo file lớn nếu được phép. Tránh restart MySQL theo phản xạ: server có thể cần thêm disk để crash recovery hoặc khởi động lại.

### Bước 2: Xác định filesystem và loại file

Chạy `df -hT`, `df -i`, kiểm tra mount của `datadir`, `tmpdir`, binary log và backup. Dùng `du` để tìm thư mục tăng bất thường. Xác định block đã hết hay inode/quota đã hết.

### Bước 3: Ưu tiên tăng dung lượng hoặc mở rộng đúng mount

Nếu filesystem chứa data directory gần đầy, mở rộng volume/filesystem theo runbook hạ tầng thường an toàn hơn xóa file dữ liệu. Xác nhận hệ thống file đã nhận dung lượng mới bằng `df`/`Get-Volume`. Với container/Kubernetes, mở rộng PVC hoặc xử lý ephemeral storage theo cơ chế platform.

### Bước 4: Giải phóng dữ liệu không còn cần, theo đúng chủ sở hữu

- Dọn backup cũ ở backup target sau khi xác nhận bản backup khác còn hợp lệ và retention cho phép.
- Dọn application log qua log rotation hoặc công cụ quản lý log.
- Chuyển file export/staging không còn dùng khỏi volume MySQL.
- Purge binary log bằng SQL sau khi xác nhận replica, PITR và audit không còn cần.
- Xử lý temporary query/session sau khi xác định được owner và đã dừng an toàn.

Không xóa thủ công file `.ibd`, `ibdata*`, redo log, undo tablespace, `ibtmp1`, binary log, relay log hoặc file đang mở trong data directory. Không chạy `docker system prune --volumes` trên host có volume database.

### Bước 5: Xác nhận MySQL ghi được trở lại

Kiểm tra filesystem có khoảng trống dự phòng, error log không còn lỗi ghi, replica/receiver hoạt động và một thao tác ghi thử trên schema kiểm thử hoặc transaction an toàn thành công. Theo dõi dung lượng vài chu kỳ để xác nhận không tăng trở lại ngay.

### Bước 6: Tìm nguyên nhân gốc và ngăn tái diễn

Xác định growth rate, job/query gây tăng, retention sai, index/DDL bất thường, giới hạn tablespace hoặc sizing thiếu. Đặt alert theo cả phần trăm lẫn dung lượng tuyệt đối, inode, tốc độ tăng và thời gian còn lại ước tính theo xu hướng.

## 11. Những thao tác không nên làm khi hết disk

| Thao tác rủi ro | Vì sao nguy hiểm | Hướng xử lý đúng |
|---|---|---|
| Xóa file `.ibd` khi MySQL đang chạy | Làm mất tablespace và phá metadata InnoDB. | Dùng SQL/DDL hoặc restore theo quy trình được hỗ trợ. |
| Xóa `ibdata1`, redo/undo hoặc `ibtmp1` bằng tay | Có thể làm server không khởi động hoặc mất khả năng recovery. | Xử lý theo cấu hình tablespace và tài liệu phiên bản; chỉ thao tác offline trong runbook đã kiểm chứng. |
| Xóa binary log bằng filesystem command | MySQL vẫn giữ metadata/index trỏ đến file đã mất; replication/PITR có thể hỏng. | Dùng `PURGE BINARY LOGS` sau khi kiểm tra phụ thuộc. |
| Xóa relay log thủ công | Làm lệch relay log index và metadata applier. | Dùng quy trình replication recovery. |
| Chạy `OPTIMIZE TABLE` để lấy lại chỗ ngay | Có thể tạo bản sao và cần thêm disk trước khi thu hồi. | Ước lượng dung lượng, thử staging và lên lịch bảo trì. |
| Tăng `tmp_table_size`/`max_heap_table_size` tùy tiện | Chuyển áp lực từ disk sang RAM; nhiều session có thể tiêu thụ memory lớn. | Phân tích query và điều chỉnh theo giới hạn tổng thể. |
| Tăng `max_connections` khi disk đầy | Không giải quyết nguyên nhân và có thể tăng temporary/log workload. | Xử lý nguồn tăng trưởng và connection pressure riêng. |
| Kill mọi query đang chạy | Có thể gây rollback dài, gián đoạn nghiệp vụ và không giải phóng chỗ ngay. | Xác định session gây tăng và đánh giá trước khi dừng. |
| Restart MySQL liên tục | Không giải phóng dữ liệu bền vững; có thể làm recovery thất bại khi thiếu disk. | Kiểm tra error log, mở rộng storage và restart theo runbook khi cần. |

## 12. Phân biệt giới hạn của storage engine

### InnoDB

Kiểm tra tablespace, autoextend, filesystem, quota và temporary tablespace. Nếu system tablespace có `max` hoặc temporary tablespace có giới hạn cấu hình, tăng dung lượng filesystem đơn thuần có thể không giải quyết được giới hạn nội bộ. Cần lập thay đổi cấu hình và kế hoạch mở rộng đúng loại tablespace.

### MyISAM

MyISAM có giới hạn kích thước file phụ thuộc filesystem và cấu hình như `MAX_ROWS`, `AVG_ROW_LENGTH`, `myisam_data_pointer_size` hoặc giới hạn của nền tảng. `ERROR 1114` có thể xảy ra dù filesystem vẫn còn dung lượng nếu table chạm giới hạn cấu hình/engine. Kiểm tra `SHOW CREATE TABLE`, `SHOW TABLE STATUS` và cấu hình MySQL trước khi thay đổi.

### MEMORY

Bảng `MEMORY` lưu dữ liệu trong RAM và chịu giới hạn `max_heap_table_size` (cùng các giới hạn liên quan của phiên bản). Bảng có thể báo full khi vượt giới hạn dù disk còn rất nhiều. Xem engine của bảng và biến giới hạn trước khi tăng cấu hình; tăng giới hạn đồng nghĩa tăng rủi ro RAM.

### Partition và quota

Bảng partition có thể đặt file/tablespace trên nhiều đường dẫn hoặc filesystem tùy cấu hình. Một partition hoặc mount cụ thể có thể hết chỗ trước các vùng khác. Quota của user/project cũng có thể làm thao tác thất bại dù `df -h` báo còn trống. Luôn xác định đúng file và mount phát sinh lỗi.

## 13. Thiết kế capacity và cảnh báo

Không nên đợi filesystem chạm 100% mới cảnh báo. Dự trù dung lượng theo:

- Kích thước dữ liệu và index hiện tại.
- Tốc độ tăng hàng/ngày và tăng dung lượng thực tế.
- Binary log retention, replica lag và thời gian cần cho PITR.
- Dung lượng backup tạm và backup song song.
- Temporary space đỉnh khi chạy DDL, sort, report và batch.
- Redo/undo, crash recovery và không gian vận hành dự phòng.
- Log hệ điều hành, container overlay và inode.

Dashboard nên theo dõi ít nhất:

| Chỉ số | Cảnh báo nên dựa vào |
|---|---|
| Filesystem used/free bytes | Phần trăm sử dụng và số GB còn trống tuyệt đối. |
| Inode used/free | Tỷ lệ inode và tốc độ tạo file. |
| Data directory growth | Tốc độ tăng theo ngày/tuần và dự báo ngày chạm ngưỡng. |
| Binary log size/count | Tổng dung lượng, retention và replica/PITR dependency. |
| Relay log space | Tăng kéo dài hoặc receiver không thể ghi. |
| Temporary space | Mức đỉnh, thời gian giữ file và query gây tăng. |
| Tablespace usage | Mức tăng file-per-table, system tablespace và temporary tablespace. |
| Backup target | Dung lượng còn lại, tuổi backup gần nhất và kết quả job. |

Thiết lập cảnh báo theo nhiều mức, ví dụ cảnh báo sớm khi dung lượng còn dưới ngưỡng vận hành đã định và cảnh báo khẩn khi không còn đủ chỗ cho workload/DDL dự kiến. Ngưỡng phải dựa trên tốc độ tăng và thời gian đội vận hành cần để mở rộng storage, không dùng một tỷ lệ chung cho mọi hệ thống.

## 14. Checklist xử lý và xác nhận phục hồi

- [ ] Đã lưu nguyên văn error message, thời điểm, query/DDL và MySQL error log liên quan.
- [ ] Đã xác định filesystem/mount cụ thể và phân biệt hết block, inode hay quota.
- [ ] Đã kiểm tra `datadir`, `tmpdir`, tablespace, binary log, relay log và backup target.
- [ ] Đã xác định engine/table/tablespace hoặc session tạo ra lỗi `Table is full`.
- [ ] Đã kiểm tra processlist, temporary query, DDL và tốc độ tăng file.
- [ ] Đã dừng hoặc hoãn tác vụ gây tăng trưởng theo cách có kiểm soát.
- [ ] Đã mở rộng đúng volume hoặc giải phóng file không còn cần theo đúng chủ sở hữu.
- [ ] Không xóa thủ công file dữ liệu, redo/undo, binary log hoặc relay log.
- [ ] Đã xác minh MySQL ghi được, error log sạch và replication/backup hoạt động.
- [ ] Đã theo dõi dung lượng sau xử lý và tìm nguyên nhân gốc.
- [ ] Đã cập nhật capacity forecast, retention hoặc alert để ngăn tái diễn.

Khi MySQL báo hết disk, điều quan trọng là tìm đúng vùng lưu trữ và loại giới hạn đã chạm tới. Filesystem có thể đầy, inode/quota có thể cạn, tablespace có thể chạm max, engine có thể đạt giới hạn riêng hoặc query/DDL có thể cần temporary space lớn. Mở rộng đúng mount, quản lý log bằng cơ chế MySQL, xử lý query có kiểm soát và giữ nguyên file dữ liệu cốt lõi sẽ giúp phục hồi an toàn mà không làm hỏng khả năng recovery hoặc replication.
