# Chính sách xoay log, lưu log và cảnh báo đầy đĩa

MySQL tạo nhiều loại log để phục vụ chẩn đoán, tối ưu truy vấn, replication và khôi phục dữ liệu. Nếu không có chính sách vòng đời, các file log có thể tăng liên tục, chiếm hết filesystem và khiến MySQL không thể ghi dữ liệu hoặc khởi động bình thường. Vận hành an toàn cần xác định **log nào phải bật, lưu ở đâu, xoay khi nào, giữ trong bao lâu, xóa theo điều kiện nào và cảnh báo trước khi hết dung lượng**.

Bài học thuộc phần **Cấu hình và vận hành** của MySQL. Bạn sẽ phân biệt error log, general log, slow query log, binary log và relay log; cấu hình mức ghi phù hợp; xoay file và yêu cầu MySQL mở lại log; đặt retention; theo dõi dung lượng và inode; xây dựng cảnh báo; và xử lý tình huống filesystem gần đầy mà không làm hỏng trạng thái lưu trữ của InnoDB.

## 1. Phân biệt các loại log của MySQL

Không phải mọi file có chữ `log` đều có cùng mục đích hoặc cùng cách xoay. Cần phân loại trước khi viết chính sách:

| Loại log | Mục đích | Khi nào bật/lưu | Cách quản lý vòng đời |
| --- | --- | --- | --- |
| Error log | Ghi sự kiện khởi động/dừng, lỗi, cảnh báo, sự cố engine và thông tin vận hành. | Luôn cần có một đích ghi phù hợp; thường lưu bền vững hoặc chuyển tới hệ thống log tập trung. | Xoay file theo ngày/kích thước hoặc quản lý bằng journald/syslog/Event Log; yêu cầu MySQL mở lại file sau khi đổi tên. |
| General query log | Ghi kết nối và câu lệnh client gửi tới server. | Chỉ bật trong thời gian chẩn đoán cụ thể vì lượng ghi lớn và có thể chứa dữ liệu nhạy cảm. | Tắt sau khi điều tra; nếu cần lưu thì xoay thường xuyên và retention ngắn. |
| Slow query log | Ghi truy vấn vượt ngưỡng thời gian hoặc thỏa điều kiện log. | Có thể bật dài hạn để tìm truy vấn chậm và theo dõi xu hướng. | Xoay định kỳ, nén và lưu theo nhu cầu phân tích/tuân thủ. |
| Binary log (binlog) | Ghi sự kiện thay đổi dữ liệu để replication và point-in-time recovery. | Bật khi cần replication, PITR hoặc yêu cầu audit theo sự kiện. | Dùng chính sách hết hạn và `PURGE BINARY LOGS`; không xóa file thủ công. |
| Relay log | Lưu sự kiện binlog mà replica nhận từ source trước khi áp dụng. | Có trên replica đang dùng replication. | Để cơ chế replication tự quản lý; kiểm tra `relay_log_purge` và trạng thái replica. |
| Redo/undo log của InnoDB | Phục hồi crash, rollback và dựng phiên bản cũ cho MVCC. | Thành phần nội bộ của InnoDB. | Quản lý bằng cấu hình/cơ chế InnoDB; tuyệt đối không xoay hoặc xóa như log văn bản. |

Audit log có thể được cung cấp bởi plugin hoặc sản phẩm thương mại tùy phiên bản và môi trường. Nếu bật audit, cần đưa dung lượng, retention, quyền đọc và quy trình chuyển log ra hệ thống tập trung vào cùng kế hoạch vận hành.

## 2. Xác định vị trí log và filesystem chứa chúng

Trước khi đặt retention, phải biết từng loại log nằm ở đâu. Chạy các câu lệnh sau trên đúng instance:

```sql
SELECT
    @@hostname AS host_name,
    @@port AS port_number,
    @@datadir AS data_directory,
    @@tmpdir AS temporary_directory,
    @@log_error AS error_log;

SHOW VARIABLES WHERE Variable_name IN (
    'general_log',
    'general_log_file',
    'slow_query_log',
    'slow_query_log_file',
    'log_output',
    'log_bin',
    'log_bin_basename',
    'relay_log',
    'relay_log_basename',
    'innodb_redo_log_capacity'
);
```

Một số biến có thể không tồn tại ở phiên bản cũ hoặc trả về giá trị rỗng nếu chức năng tương ứng không bật. Đọc cấu hình thực tế thay vì giả định mọi instance đều có binlog hoặc relay log.

Kiểm tra cả filesystem chứa `datadir`, thư mục log, `tmpdir`, thư mục redo và vị trí log tập trung. Đặt error log trên filesystem riêng có thể giúp giữ khả năng chẩn đoán khi data volume gặp vấn đề, nhưng chỉ hữu ích nếu volume đó cũng được giám sát và có đủ dung lượng.

Không nên để general log, slow log, binlog, relay log, redo và file tạm cùng phụ thuộc vào một volume nhỏ mà không có quota/cảnh báo. Một truy vấn tạo temporary file lớn cũng có thể làm đầy volume dù log được xoay đúng cách.

## 3. Cấu hình error log

Error log là nguồn thông tin đầu tiên khi MySQL khởi động lỗi, gặp crash, phát hiện vấn đề lưu trữ hoặc có cảnh báo replication. Trên MySQL 8.0, các biến quan trọng gồm:

```sql
SHOW VARIABLES WHERE Variable_name IN (
    'log_error',
    'log_error_verbosity',
    'log_error_services'
);
```

`log_error_verbosity` điều khiển mức độ chi tiết:

| Giá trị | Nội dung khái quát |
| ---: | --- |
| `1` | Chỉ ghi lỗi. |
| `2` | Ghi lỗi và cảnh báo. |
| `3` | Ghi lỗi, cảnh báo và thông báo (notes). |

Mức cao hơn giúp điều tra nhưng có thể tạo thêm log. Chọn mức dựa trên yêu cầu giám sát và dung lượng. `log_error_services` xác định các thành phần lọc/đích ghi error log; cấu hình mặc định và các sink hỗ trợ tùy phiên bản, nền tảng.

Error log có thể được ghi ra file, stderr, system log hoặc Windows Event Log tùy cấu hình. Nếu dùng journald/syslog hoặc Event Log, chính sách rotation/retention thường do hệ điều hành quản lý. Nếu ghi file, cần phối hợp công cụ xoay log với thao tác yêu cầu MySQL mở lại file.

## 4. General log: chỉ bật khi cần thiết

General query log ghi nhận các kết nối và câu lệnh client gửi đến server. Nó hữu ích khi cần xác định ứng dụng thực sự gửi gì, nhưng có thể tăng I/O đáng kể trên workload nhiều truy vấn.

Kiểm tra trạng thái:

```sql
SHOW VARIABLES WHERE Variable_name IN (
    'general_log',
    'general_log_file',
    'log_output'
);
```

Bật tạm trong thời gian điều tra:

```sql
SET GLOBAL log_output = 'FILE';
SET GLOBAL general_log = ON;
```

Sau khi thu thập đủ thông tin, tắt ngay:

```sql
SET GLOBAL general_log = OFF;
```

Thay đổi GLOBAL có thể ảnh hưởng toàn instance. Hãy thông báo cửa sổ điều tra, giới hạn thời gian, theo dõi tốc độ tăng file và chỉ bật khi thực sự cần. General log có thể ghi literal trong câu SQL hoặc thông tin nghiệp vụ nhạy cảm; giới hạn quyền đọc, tránh gửi nguyên file vào ticket/chat và xóa theo retention đã duyệt.

`log_output` điều khiển đích ghi của general log và slow query log (`FILE`, `TABLE` hoặc kết hợp theo phiên bản). Nó không điều khiển error log hay binary log. Ghi vào bảng `mysql.general_log`/`mysql.slow_log` có cách quản lý khác với file và vẫn tiêu thụ dung lượng lưu trữ.

## 5. Slow query log: thu thập có mục tiêu

Slow query log giúp phát hiện truy vấn có thời gian thực thi hoặc số dòng kiểm tra vượt điều kiện cấu hình. Các biến thường dùng:

```sql
SHOW VARIABLES WHERE Variable_name IN (
    'slow_query_log',
    'slow_query_log_file',
    'long_query_time',
    'min_examined_row_limit',
    'log_queries_not_using_indexes',
    'log_throttle_queries_not_using_indexes',
    'log_output'
);
```

Ví dụ cấu hình:

```sql
SET GLOBAL slow_query_log = ON;
SET GLOBAL long_query_time = 1;
SET GLOBAL min_examined_row_limit = 100;
```

Ví dụ này ghi truy vấn vượt ngưỡng 1 giây và đã kiểm tra tối thiểu 100 dòng. Ngưỡng phù hợp phụ thuộc SLA, workload và tỷ lệ truy vấn; 1 giây không phải giá trị chuẩn cho mọi hệ thống.

`log_queries_not_using_indexes` có thể làm log tăng rất nhanh, đặc biệt khi có nhiều truy vấn quét bảng nhỏ hoặc truy vấn định kỳ. Nếu bật, cân nhắc `log_throttle_queries_not_using_indexes` để hạn chế số bản ghi theo thời gian. Đọc log cùng digest, `EXPLAIN` và số liệu thực tế; không tạo index chỉ vì thấy một truy vấn xuất hiện trong log.

Slow log nên được xoay định kỳ và lưu đủ lâu để nhận diện xu hướng. Nếu cần phân tích tổng hợp, dùng `pt-query-digest` hoặc công cụ tương đương trên bản sao log đã bảo vệ; kiểm soát dữ liệu nhạy cảm trước khi chia sẻ.

## 6. Xoay error log, general log và slow query log

Xoay log file thường gồm ba bước:

1. Đổi tên file hiện tại hoặc chuyển file cũ sang vị trí lưu trữ.
2. Tạo file mới với owner, group và permission phù hợp nếu công cụ rotation yêu cầu.
3. Yêu cầu MySQL đóng handle cũ và mở lại file log.

Với MySQL hỗ trợ các lệnh FLUSH tương ứng:

```sql
FLUSH ERROR LOGS;
FLUSH GENERAL LOGS;
FLUSH SLOW LOGS;
```

`FLUSH LOGS` có phạm vi rộng hơn và có thể xoay cả binary log. Khi chỉ muốn mở lại một log văn bản, dùng lệnh cụ thể nếu phiên bản hỗ trợ. Tài khoản chạy lệnh cần quyền quản trị phù hợp, thường là `RELOAD` hoặc quyền FLUSH tương ứng theo phiên bản.

### Ví dụ phối hợp với logrotate trên Linux

Một cấu hình minh họa cho error log:

```text
/var/log/mysql/error.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0640 mysql adm
    sharedscripts
    postrotate
        mysql --login-path=logrotate -e "FLUSH ERROR LOGS;" >/dev/null 2>&1
    endscript
}
```

Đây là mẫu cần điều chỉnh theo đường dẫn, user/group và cách xác thực trên máy chủ. Tạo login path an toàn bằng `mysql_config_editor` hoặc dùng cơ chế secret của hệ thống; không đặt mật khẩu rõ trong file cấu hình logrotate hay dòng lệnh.

Đối với slow/general log, tạo rule riêng và dùng `FLUSH SLOW LOGS` hoặc `FLUSH GENERAL LOGS` trong bước postrotate tương ứng. Không gộp nhiều file vào một rule nếu mỗi file cần lệnh reopen khác nhau.

Phương án rename rồi reopen thường an toàn hơn `copytruncate`. Với `copytruncate`, log có thể bị mất một phần hoặc lặp trong khoảng thời gian giữa copy và truncate vì MySQL vẫn ghi vào cùng file. Nếu buộc phải dùng, cần hiểu và chấp nhận cửa sổ rủi ro.

### Xoay log trên Windows hoặc hệ thống log tập trung

Nếu error log ghi ra file trên Windows, dùng cơ chế rotation phù hợp của hệ điều hành hoặc agent quản lý log, sau đó thực hiện `FLUSH ERROR LOGS` để MySQL mở lại file khi cần. Nếu log được chuyển sang Event Log, journald hoặc syslog, retention do dịch vụ đó quản lý; phải cấu hình giới hạn dung lượng và thời gian lưu ở chính dịch vụ nhận log.

Không xóa file đang được MySQL mở bằng thao tác filesystem rồi cho rằng dung lượng đã được giải phóng. Trên một số hệ điều hành, file đã xóa vẫn chiếm dung lượng cho đến khi process đóng handle; trên hệ thống khác, việc xóa file đang mở có thể gây lỗi hoặc làm mất khả năng ghi log.

## 7. Binary log: retention phải gắn với replication và PITR

Binary log chứa các sự kiện thay đổi dữ liệu. Nó có thể là nguồn dữ liệu để replica áp dụng và là thành phần cần thiết khi phục hồi tới một thời điểm sau khi restore backup. Xóa binlog quá sớm có thể làm replica không còn lấy được sự kiện hoặc khiến PITR không thể đi tới thời điểm mong muốn.

Kiểm tra cấu hình:

```sql
SHOW VARIABLES WHERE Variable_name IN (
    'log_bin',
    'log_bin_basename',
    'binlog_expire_logs_seconds',
    'sync_binlog',
    'server_id',
    'gtid_mode'
);
```

Trong MySQL 8.0, `binlog_expire_logs_seconds` đặt thời gian hết hạn tự động của binary log theo giây. Ví dụ giữ khoảng 14 ngày:

```sql
SET PERSIST binlog_expire_logs_seconds = 1209600;
```

`SET PERSIST` ghi cấu hình để áp dụng cho lần khởi động sau và cập nhật biến động nếu biến hỗ trợ. Nếu dùng phiên bản không hỗ trợ `SET PERSIST`, cấu hình trong file cấu hình dưới `[mysqld]` và khởi động lại theo quy trình.

Retention phải dài hơn khoảng thời gian replica có thể ngừng hoạt động và khoảng PITR cần hỗ trợ, cộng thêm biên an toàn. Đừng đặt 14 ngày chỉ vì ví dụ; tính theo lịch backup, thời gian lưu backup, độ trễ replica, yêu cầu khôi phục và dung lượng thực tế.

### Kiểm tra binlog trước khi purge

Liệt kê các file và dung lượng:

```sql
SHOW BINARY LOGS;
```

Trên source MySQL 8.0, kiểm tra replica đang đọc/áp dụng tới đâu bằng trạng thái replication phù hợp phiên bản, ví dụ trên các bản hỗ trợ cú pháp mới:

```sql
SHOW REPLICA STATUS\G
```

Ở các bản MySQL cũ, lệnh có thể là `SHOW SLAVE STATUS\G`. Đối chiếu vị trí/GTID đã thực thi trên tất cả replica, kể cả replica đang offline, cùng với metadata của backup và chính sách PITR.

Nếu cần xóa binlog thủ công, dùng câu lệnh quản trị:

```sql
PURGE BINARY LOGS TO 'binlog.000250';
```

Lệnh xóa các file đứng trước file được nêu, không xóa file đích. Có thể purge theo thời gian:

```sql
PURGE BINARY LOGS BEFORE '2026-11-01 00:00:00';
```

Chỉ purge sau khi xác nhận không replica nào còn cần các file đó và backup/PITR không cần chúng. Không xóa binlog bằng `rm`, PowerShell `Remove-Item` hoặc thao tác file trực tiếp; phải để MySQL cập nhật binlog index và metadata tương ứng.

### Xoay binary log

Có thể chủ động đóng file hiện tại và mở file binlog mới:

```sql
FLUSH BINARY LOGS;
```

Lệnh này tạo ranh giới file mới, không phải lệnh xóa log cũ. Đừng dùng `FLUSH LOGS` trong script xoay error log nếu không muốn vô tình tạo thêm binlog mới. Theo dõi dung lượng binlog tăng theo giờ/ngày để dự báo retention.

## 8. Relay log trên replica

Replica nhận sự kiện từ source và lưu trong relay log trước khi SQL applier xử lý. Kiểm tra:

```sql
SHOW VARIABLES WHERE Variable_name IN (
    'relay_log',
    'relay_log_basename',
    'relay_log_purge',
    'relay_log_space_limit',
    'relay_log_recovery'
);
```

Thông thường `relay_log_purge` được bật để MySQL tự xóa relay log đã dùng xong. `relay_log_recovery` giúp replica phục hồi relay log khi khởi động trong cấu hình phù hợp. `relay_log_space_limit`, nếu được đặt, có thể làm luồng nhận log tạm dừng khi vượt giới hạn.

Khi relay log tăng bất thường, kiểm tra SQL applier có bị lỗi hoặc chậm, replica lag, I/O thread, dung lượng đĩa và trạng thái kết nối source. Không xóa relay log thủ công để giải phóng đĩa; việc đó có thể làm hỏng tiến trình replication. Hãy xử lý nguyên nhân khiến replica không áp dụng được log, sau đó để replication tự quản lý purge.

## 9. Redo, undo và file tạm không phải log văn bản

Redo log và undo tablespace là thành phần nội bộ của InnoDB. Chúng không được xoay bằng logrotate hay `FLUSH SLOW LOGS`.

Trên MySQL 8.0.30 trở lên, có biến `innodb_redo_log_capacity` để quản lý dung lượng redo log mục tiêu:

```sql
SHOW VARIABLES LIKE 'innodb_redo_log_capacity';
```

Ở các phiên bản cũ hơn, cấu hình redo có thể liên quan đến `innodb_log_file_size` và số file log. Không thay đổi/xóa redo file trực tiếp khi server đang chạy. Undo history tăng có thể liên quan transaction dài hoặc purge chậm; cần kiểm tra transaction và InnoDB status thay vì xóa undo file.

`tmpdir` cũng cần được giám sát. Sort, join, temporary table nội bộ hoặc truy vấn lớn có thể tạo file tạm. Nếu volume này đầy, truy vấn có thể thất bại dù binlog và error log còn đủ chỗ.

## 10. Xây dựng chính sách retention

Retention cần gắn với mục đích sử dụng, không chỉ chọn một số ngày giống nhau cho mọi log:

| Log | Chính sách tham khảo | Điều kiện phải xác minh |
| --- | --- | --- |
| Error log | Giữ 14–30 ngày hoặc chuyển log tập trung theo yêu cầu vận hành. | Có đủ lịch sử để điều tra crash và sự cố định kỳ; không mất log trước khi agent thu thập. |
| General log | Tắt mặc định; khi bật chỉ giữ trong thời gian điều tra ngắn. | Có phê duyệt, kiểm soát dữ liệu nhạy cảm và giới hạn dung lượng. |
| Slow query log | Giữ 7–30 ngày hoặc chuyển sang hệ thống phân tích. | Đủ dữ liệu nhận diện xu hướng; có giới hạn khi log truy vấn không dùng index. |
| Binary log | Theo nhu cầu replica và PITR, ví dụ 7–30 ngày hoặc lâu hơn. | Mọi replica đã nhận log cần thiết; backup có binlog/GTID position phù hợp. |
| Relay log | Để MySQL tự purge sau khi áp dụng. | Replication thread hoạt động bình thường và không có lỗi cần điều tra. |
| Audit log | Theo chính sách bảo mật/tuân thủ của tổ chức. | Quyền truy cập, tính toàn vẹn, vị trí lưu và thời hạn phải được phê duyệt. |

Các khoảng ngày trên chỉ là điểm bắt đầu để thảo luận. Hệ thống có yêu cầu tuân thủ, điều tra bảo mật hoặc RPO/RTO khác nhau phải có retention riêng. Log tập trung cũng cần chính sách retention và cảnh báo dung lượng; chuyển log khỏi máy MySQL không làm mất nhu cầu quản lý vòng đời.

### Ước lượng dung lượng cần thiết

Ước lượng cơ bản cho một loại log:

\[
\text{Dung lượng dự kiến} =
\text{log phát sinh mỗi ngày} \times
\text{số ngày lưu} \times
\text{hệ số an toàn}
\]

Ví dụ binlog trung bình 18 GB/ngày, cần giữ 7 ngày và dùng hệ số an toàn 1,3:

\[
18 \times 7 \times 1.3 = 163.8\ \text{GB}
\]

Đây là dung lượng dự kiến cho binlog, chưa tính data file, redo, relay log, temporary file, backup hoặc tốc độ tăng trưởng. Dùng số liệu peak theo ngày thay vì chỉ trung bình; workload cuối tháng hoặc batch ETL có thể tạo log nhiều hơn đáng kể.

## 11. Cảnh báo đầy đĩa: theo dõi phần trăm, byte và tốc độ tăng

Chỉ cảnh báo theo phần trăm trống là chưa đủ. Một volume 10 GB còn 20% chỉ còn 2 GB; volume 10 TB còn 5% vẫn còn 500 GB. Theo dõi đồng thời:

- Phần trăm dung lượng còn trống.
- Số byte/GB còn trống tuyệt đối.
- Tốc độ tăng dung lượng theo giờ/ngày.
- Thời gian dự kiến đến khi đầy (time to exhaustion).
- Inode còn trống trên Linux nếu log tạo nhiều file nhỏ.
- Dung lượng theo từng thư mục/loại log và các volume chứa datadir/tmpdir.

Ngưỡng minh họa, cần điều chỉnh theo tốc độ ghi và khả năng mở rộng:

| Mức | Ví dụ điều kiện | Hành động |
| --- | --- | --- |
| Warning | Dung lượng trống dưới 25% hoặc dự báo đầy trong 7 ngày. | Kiểm tra tốc độ tăng, retention và kế hoạch mở rộng. |
| High | Dung lượng trống dưới 15% hoặc dự báo đầy trong 72 giờ. | Tạo ticket xử lý sớm, xác định log/file tăng nhanh, kiểm tra replica và backup. |
| Critical | Dung lượng trống dưới 8% hoặc dự báo đầy trong 24 giờ. | Kích hoạt on-call, giảm/tạm dừng workload không thiết yếu và giải phóng dung lượng theo quy trình an toàn. |

Các ngưỡng phần trăm chỉ là ví dụ. Nếu filesystem nhỏ, đặt thêm ngưỡng byte tuyệt đối; nếu log tăng rất nhanh, cảnh báo theo thời gian dự báo đầy phải kích hoạt trước ngưỡng phần trăm.

### Kiểm tra dung lượng trên Linux

```bash
df -h
df -i
du -sh /var/log/mysql/*
du -sh /var/lib/mysql/*
```

`df -h` cho biết dung lượng filesystem; `df -i` cho biết inode; `du` giúp tìm thư mục/file lớn. Cần có quyền đọc phù hợp và tránh chạy quét `du` quá thường xuyên trên volume rất lớn.

### Kiểm tra trên Windows

```powershell
Get-Volume | Select-Object DriveLetter, FileSystemLabel, Size, SizeRemaining
```

Đối chiếu drive chứa `datadir`, log directory và `tmpdir`. Nếu MySQL chạy trong container hoặc volume mount, kiểm tra cả filesystem bên trong container và storage host.

## 12. Theo dõi log bằng SQL và giám sát hệ thống

Một số truy vấn giúp xác định cấu hình và dung lượng binlog:

```sql
SHOW BINARY LOGS;
```

Theo dõi trạng thái replication trên replica:

```sql
SHOW REPLICA STATUS\G
```

Các trường như `Replica_IO_Running`, `Replica_SQL_Running`, `Seconds_Behind_Source`, vị trí source và relay log giúp đánh giá tiến độ. `Seconds_Behind_Source` có thể là `NULL` khi replica không chạy hoặc không xác định được độ trễ; cần đọc cùng trạng thái thread và lỗi gần nhất.

Kiểm tra bộ đếm slow query:

```sql
SHOW GLOBAL STATUS LIKE 'Slow_queries';
```

Đây là bộ đếm tích lũy từ khi server khởi động hoặc trạng thái được reset; lấy delta theo thời gian để xem xu hướng. Nó không thay thế phân tích nội dung slow log.

Một dashboard vận hành nên có:

1. Dung lượng trống và inode theo từng filesystem liên quan.
2. Dung lượng và tốc độ tăng của error/general/slow/binlog/relay log.
3. Số binlog hiện tại, kích thước file mới nhất và retention còn lại.
4. Replication lag, trạng thái I/O/SQL applier và lỗi replication.
5. Trạng thái log rotation gần nhất và số file cũ chưa được nén/xóa.
6. Dự báo time to exhaustion theo tốc độ tăng gần đây và peak.
7. Tình trạng backup/PITR để xác nhận binlog cũ đã an toàn để purge.

Đặt cảnh báo ở hệ thống giám sát bên ngoài MySQL. Nếu chính filesystem chứa log đã đầy, không nên phụ thuộc vào việc MySQL ghi thêm một dòng error để cảnh báo; agent giám sát host cần phát hiện độc lập.

## 13. Xử lý sự cố filesystem gần đầy hoặc đã đầy

Khi cảnh báo xuất hiện, ưu tiên giữ MySQL hoạt động và bảo toàn khả năng phục hồi:

1. Xác định filesystem nào gần đầy: datadir, log, redo, relay, tmpdir hay volume backup.
2. Xác định file tăng nhanh bằng công cụ hệ điều hành và đối chiếu biến MySQL để biết file nào đang được server sử dụng.
3. Nếu general log đang bật ngoài kế hoạch, tắt sau khi xác nhận không cần tiếp tục thu thập.
4. Xoay và nén error/slow/general log theo đúng quy trình reopen; chuyển bản cũ sang storage khác nếu cần giữ lại.
5. Với binlog, xác minh replica và backup/PITR trước khi dùng `PURGE BINARY LOGS`; không xóa file trực tiếp.
6. Với relay log, xử lý lỗi/độ trễ replica và để MySQL tự purge sau khi áp dụng.
7. Nếu temporary file tăng, xác định truy vấn/job tạo file; giới hạn hoặc tạm dừng workload không thiết yếu.
8. Mở rộng volume hoặc chuyển log sang storage có giám sát nếu dung lượng dự báo vẫn không đủ.
9. Sau khi giải phóng đủ dung lượng, kiểm tra error log, trạng thái MySQL, replication, backup và dữ liệu nghiệp vụ.

Không xóa `ibdata1`, redo log, undo tablespace, binlog hoặc relay log bằng thao tác filesystem để chữa đầy đĩa. Không xóa file log đang được process mở mà không thực hiện quy trình reopen. Nếu data volume đã đầy, ưu tiên dừng/giảm workload ghi không thiết yếu và nhờ DBA/on-call xử lý theo runbook thay vì chạy hàng loạt lệnh purge không kiểm tra.

## 14. Ví dụ chính sách cấu hình và lịch vận hành

Một cấu hình khởi đầu minh họa trong file cấu hình MySQL:

```ini
[mysqld]
log_error_verbosity=2
slow_query_log=ON
long_query_time=1
min_examined_row_limit=100
general_log=OFF
log_output=FILE
binlog_expire_logs_seconds=1209600
```

Các giá trị phải điều chỉnh theo phiên bản, workload, yêu cầu bảo mật và PITR. Không sao chép cấu hình lên production mà chưa xác nhận vị trí file, quyền, dung lượng và tác động ghi.

Lịch vận hành tham khảo:

| Tần suất | Công việc |
| --- | --- |
| Liên tục | Cảnh báo disk free, inode, tốc độ tăng log, time to exhaustion và replication lag. |
| Hằng ngày | Kiểm tra binlog/relay log tăng bất thường, general log ngoài kế hoạch và lỗi rotation. |
| Hằng tuần | Xem slow log/digest, kiểm tra retention, dung lượng từng loại log và khả năng PITR. |
| Hằng tháng | Diễn tập phục hồi backup + binlog, rà soát thời hạn lưu, quyền truy cập log và dự báo dung lượng. |
| Khi thay đổi | Đánh giá lại retention, filesystem, volume, replication topology và cấu hình log. |

Mỗi lần thay đổi retention cần ghi lại lý do, thời điểm, người phê duyệt, các replica/backup bị ảnh hưởng và cách rollback. Chính sách log là một phần của RPO/RTO và quy trình ứng cứu, không chỉ là công việc dọn file.

## 15. Lỗi vận hành thường gặp

- **Xóa binlog cũ chỉ dựa vào tuổi file.** Có thể làm replica offline không thể bắt kịp hoặc phá vỡ PITR.
- **Dùng logrotate nhưng quên reopen log.** MySQL tiếp tục ghi vào file đã đổi tên hoặc handle cũ, khiến file mới không nhận log.
- **Dùng `copytruncate` mà không hiểu rủi ro.** Có thể mất hoặc lặp dòng trong khoảng copy/truncate.
- **Bật general log liên tục.** Dễ tạo I/O và dung lượng lớn, đồng thời ghi lại dữ liệu nhạy cảm.
- **Bật `log_queries_not_using_indexes` không giới hạn.** Có thể tạo log rất lớn với truy vấn quét bảng nhỏ hoặc workload nhiều câu.
- **Nhầm `FLUSH LOGS` với purge.** Flush chủ yếu đóng/mở file log; không đồng nghĩa xóa log cũ và có thể tạo binlog mới.
- **Xóa relay log bằng tay.** Có thể phá trạng thái replication; để replica tự quản lý purge.
- **Coi redo/undo như file log văn bản.** Đây là thành phần nội bộ của InnoDB, không được xoay bằng logrotate.
- **Chỉ cảnh báo theo phần trăm dung lượng.** Có thể bỏ lỡ volume nhỏ sắp hết hoặc tốc độ tăng đột biến.
- **Không thử PITR.** Retention binlog không có ý nghĩa nếu backup/restore và replay chưa được diễn tập.

## 16. Bài tập tự kiểm tra

1. Phân biệt error log, general log, slow query log và binary log theo mục đích.
2. Vì sao general log thường chỉ nên bật trong thời gian điều tra?
3. `log_output` ảnh hưởng loại log nào và không ảnh hưởng loại log nào?
4. Mô tả các bước rename, create và reopen khi xoay error log.
5. Vì sao `copytruncate` có thể làm mất log?
6. `binlog_expire_logs_seconds` phải được chọn dựa trên những yêu cầu nào?
7. Trước khi chạy `PURGE BINARY LOGS`, cần kiểm tra những replica và backup nào?
8. Vì sao không được xóa relay log hoặc redo/undo file bằng thao tác filesystem?
9. Thiết kế cảnh báo đầy đĩa kết hợp phần trăm, byte còn trống, inode và time to exhaustion.
10. Khi filesystem data directory đã đầy, hãy nêu thứ tự xử lý để bảo toàn dữ liệu và replication.

Chính sách log tốt phải nối được **mục đích ghi → vị trí lưu → tốc độ phát sinh → rotation → retention → điều kiện purge → cảnh báo dung lượng → kiểm chứng phục hồi**. Khi các bước này được định nghĩa và diễn tập, log vừa hỗ trợ điều tra và khôi phục, vừa không trở thành nguyên nhân làm gián đoạn MySQL.
