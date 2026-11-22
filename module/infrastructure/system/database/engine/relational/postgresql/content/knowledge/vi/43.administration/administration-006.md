# Luân chuyển log và bảo vệ dung lượng lưu nhật ký trong PostgreSQL

PostgreSQL tạo log để ghi lại lỗi, cảnh báo, hoạt động kết nối, câu lệnh chậm, checkpoint, vacuum, lock waits và các sự kiện phục hồi. Nhật ký là nguồn dữ liệu quan trọng khi điều tra sự cố và đánh giá hiệu năng, nhưng log có thể tăng nhanh khi workload lớn hoặc cấu hình ghi quá chi tiết. Nếu filesystem chứa log đầy, hệ thống giám sát mất dữ liệu; nếu log nằm chung filesystem với data hoặc WAL, dung lượng log có thể cạnh tranh trực tiếp với database files và làm gián đoạn dịch vụ.

Quản trị log cần giải quyết đồng thời ba việc: tạo log đủ hữu ích, luân chuyển file có kiểm soát và giữ dung lượng trong giới hạn dự báo được. PostgreSQL có logging collector với cơ chế rotation theo thời gian và kích thước; hệ thống cũng có thể gửi log tới syslog, Windows Event Log hoặc journald để nền tảng bên ngoài quản lý vòng đời. Rotation chỉ tạo file mới. Nó không tự xóa log cũ và không thay thế retention, archive, monitoring hay capacity planning.

~~~text
                 PostgreSQL server
                       |
                log messages
                       |
             +---------+----------+
             |                    |
             v                    v
       logging_collector      syslog / eventlog
             |                    |
             v                    v
       log_directory          OS log service
             |                    |
       +-----+------+        rotation / retention
       |            |
       v            v
   time rotation  size rotation
       |            |
       +------+-----+
              |
              v
       current_logfiles
              |
              v
       log shipper / archive
              |
       +------+--------+
       |               |
       v               v
  Central storage   Retention policy
       |
       v
  Monitoring / alert
       |
       v
  Operator response
~~~

Bài này thuộc chương **Quản trị** của module *Database Engine Relational PostgreSQL*, tập trung vào luân chuyển log và bảo vệ dung lượng lưu nhật ký trong môi trường vận hành.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vai trò của PostgreSQL logging collector và các log destinations.
2. Phân biệt stderr, csvlog, jsonlog, syslog và Windows Event Log.
3. Hiểu quan hệ giữa logging_collector, log_directory và log_filename.
4. Cấu hình rotation theo thời gian và kích thước.
5. Giải thích chính xác tác dụng và giới hạn của log_truncate_on_rotation.
6. Dùng pg_rotate_logfile() hoặc pg_ctl logrotate để yêu cầu rotation.
7. Phân biệt rotation, retention, compression và archival.
8. Hiểu vì sao rotation không tự giới hạn tổng dung lượng log.
9. Thiết kế tên file tránh ghi đè và va chạm.
10. Dùng current_logfiles để xác định file đang hoạt động.
11. Lựa chọn built-in rotation hay hệ thống syslog/journald.
12. Tránh xung đột giữa logging collector và external logrotate.
13. Ước tính log volume và dung lượng retention.
14. Tách filesystem log khỏi data/WAL khi phù hợp.
15. Theo dõi dung lượng, inode, tốc độ tăng và thời gian còn lại.
16. Điều chỉnh log_min_duration_statement và log_statement.
17. Kiểm soát log connections, checkpoints, autovacuum, lock waits và temporary files.
18. Giữ log đủ chi tiết để điều tra mà không ghi quá nhiều dữ liệu nhạy cảm.
19. Triển khai log shipping, compression, archive và cleanup an toàn.
20. Xử lý log filesystem đầy, collector lỗi và mất log.
21. Xây dựng retention policy theo môi trường và yêu cầu audit.
22. Thiết kế dashboard, alert và runbook vận hành log.

## 2. Vì sao phải quản trị log?

Log vừa là công cụ điều tra, vừa là nguồn tiêu thụ storage liên tục.

### 2.1. Điều tra lỗi

Error messages, SQLSTATE, context, application name và timestamp giúp xác định sự cố, kết nối liên quan và thời điểm lỗi xuất hiện.

### 2.2. Điều tra hiệu năng

Slow query logs, lock waits, checkpoint logs, autovacuum logs và temporary file logs giúp tìm các nguyên nhân làm query chậm hoặc tài nguyên tăng.

### 2.3. Audit và vận hành

Một số hệ thống cần giữ log để phục vụ audit, incident review hoặc yêu cầu lưu trữ nội bộ. Retention cần gắn với chính sách của tổ chức.

### 2.4. Log tăng liên tục

Nếu PostgreSQL ghi trung bình 2 MB/s, hệ thống có thể tạo khoảng 172.8 GB mỗi ngày theo đơn vị thập phân. Chỉ một vài ngày cũng có thể chiếm phần lớn filesystem.

### 2.5. Log có thể ảnh hưởng database

Nếu log và PGDATA hoặc pg_wal dùng chung filesystem, log tăng đột biến có thể làm thiếu dung lượng cho database writes, WAL, temporary files hoặc checkpoint.

### 2.6. Log quá ít cũng nguy hiểm

Tắt gần hết logging làm giảm khả năng điều tra. Mục tiêu là chọn đúng sự kiện, đúng ngưỡng và đúng thời gian lưu thay vì ghi mọi thứ hoặc không ghi gì.

## 3. Kiến trúc logging trong PostgreSQL

PostgreSQL có thể ghi log qua nhiều destinations.

| Destination | Đặc điểm | Hệ thống quản lý vòng đời |
| --- | --- | --- |
| stderr | Log dạng text | logging_collector hoặc service manager |
| csvlog | Dòng CSV có các trường cấu trúc | logging_collector |
| jsonlog | Dòng JSON có cấu trúc, tùy version | logging_collector |
| syslog | Gửi tới syslog trên hệ điều hành hỗ trợ | syslog daemon |
| eventlog | Windows Event Log | Windows Event Log service |

### 3.1. stderr

Đây là destination mặc định phổ biến. Nếu logging collector bật, PostgreSQL thu stderr và ghi vào file trong log_directory. Nếu collector tắt, stderr được chuyển cho môi trường khởi chạy server như systemd hoặc container runtime.

### 3.2. csvlog

csvlog ghi log thành các dòng CSV với nhiều trường có cấu trúc như timestamp, user, database, process ID, severity, SQLSTATE, message, detail, query và application name. Trường cụ thể phụ thuộc phiên bản.

### 3.3. jsonlog

Các phiên bản hỗ trợ jsonlog có thể xuất log thành JSON để log pipeline parse dễ hơn. Kiểm tra PostgreSQL version trước khi dùng; không phải mọi bản cài cũ đều có destination này.

### 3.4. syslog

Trên các hệ điều hành hỗ trợ, PostgreSQL có thể gửi log tới syslog. Syslog daemon chịu trách nhiệm tiếp nhận, định tuyến, rotate và retention theo cấu hình của hệ điều hành.

### 3.5. Windows Event Log

Trên Windows, PostgreSQL có thể ghi vào Event Log. Windows service và chính sách event log quản lý dung lượng, retention và export.

### 3.6. Nhiều destinations

Có thể cấu hình nhiều destinations cùng lúc, ví dụ stderr và csvlog. Điều này có thể tạo nhiều bản ghi vật lý cho cùng một sự kiện và làm tăng storage/ingestion volume. Chỉ bật nhiều destination khi có nhu cầu rõ ràng.

## 4. logging_collector

logging_collector là process nền thu thập các thông điệp gửi tới stderr và chuyển chúng vào log files.

### 4.1. Bật collector

~~~conf
logging_collector = on
~~~

Tham số này thường cần restart PostgreSQL để thay đổi có hiệu lực. Reload cấu hình không thể bật collector nếu server được khởi động khi collector đang tắt.

### 4.2. Khi collector bật

PostgreSQL tạo log files trong log_directory theo log_filename và rotation settings. Collector quản lý file descriptors và chuyển file khi tới điều kiện rotation.

### 4.3. Khi collector tắt

stderr có thể được systemd, container runtime hoặc service manager thu thập. Rotation và retention lúc này phụ thuộc hệ thống đó.

### 4.4. Không áp dụng built-in rotation cho syslog

Các tham số log_rotation_age, log_rotation_size và log_truncate_on_rotation áp dụng cho log files do logging collector quản lý. Syslog/journald/Event Log có cơ chế riêng.

### 4.5. Kiểm tra trạng thái

~~~sql
SHOW logging_collector;
SHOW log_destination;
~~~

### 4.6. Collector và availability

Nếu collector không thể mở file log, PostgreSQL có thể báo lỗi và chuyển một số thông điệp về stderr tùy tình huống/version. Không nên dựa vào fallback này như một chính sách capacity. Phải giám sát filesystem và collector logs.

### 4.7. Service manager

Khi collector tắt, hãy xác nhận service manager có giữ log, giới hạn retention và export theo policy. Việc chuyển logging destination thay đổi nơi vận hành cần theo dõi.

## 5. log_directory và log_filename

Hai tham số này xác định vị trí và tên log files do collector tạo.

### 5.1. log_directory

~~~conf
log_directory = 'log'
~~~

Đường dẫn tương đối được tính từ data directory. Có thể dùng đường dẫn tuyệt đối để đặt log trên filesystem riêng.

### 5.2. Đường dẫn tuyệt đối

Ví dụ:

~~~conf
log_directory = '/var/log/postgresql'
~~~

Đảm bảo OS account chạy PostgreSQL có quyền tạo và ghi file trong thư mục. Nếu dùng thư mục riêng, cấu hình mount và ownership trước khi restart.

### 5.3. log_filename

Tên mặc định phổ biến có dạng postgresql-%Y-%m-%d_%H%M%S.log. Có thể dùng strftime escape để đưa ngày/giờ vào tên file.

~~~conf
log_filename = 'postgresql-%Y-%m-%d_%H%M%S.log'
~~~

### 5.4. Các escape hữu ích

| Escape | Ý nghĩa thường dùng |
| --- | --- |
| %Y | Năm bốn chữ số |
| %m | Tháng |
| %d | Ngày trong tháng |
| %H | Giờ 00–23 |
| %M | Phút |
| %S | Giây |
| %a | Tên thứ viết tắt |
| %A | Tên thứ đầy đủ |
| %j | Ngày thứ trong năm |

Việc format tuân theo strftime behavior của nền tảng. Kiểm tra timezone và naming thực tế trên hệ điều hành đang dùng.

### 5.5. Tránh tên cố định

Nếu log_filename chỉ là postgresql.log, nhiều lần rotation có thể mở lại cùng tên. Khi đó cần hiểu chính xác append/truncate behavior và tránh mất dữ liệu ngoài ý muốn.

### 5.6. Tên có timestamp

Dùng ngày/giờ trong filename giúp tạo file phân biệt và thuận tiện archive. Nếu rotation size xảy ra nhiều lần trong cùng giây hoặc pattern có độ phân giải thấp, tên file có thể va chạm và collector có thể tiếp tục append vào file hiện có.

### 5.7. CSV và JSON suffix

Khi bật csvlog hoặc jsonlog, collector tạo file tương ứng với phần mở rộng theo định dạng, ví dụ .csv hoặc .json. Kiểm tra file thực tế và current_logfiles thay vì đoán tên.

### 5.8. log_file_mode

~~~conf
log_file_mode = 0600
~~~

Quyền file cần giới hạn phù hợp vì log có thể chứa SQL, usernames, client addresses và thông tin nhạy cảm. Một số OS/group sharing designs có thể cần quyền khác, nhưng phải được phê duyệt.

## 6. Rotation theo thời gian: log_rotation_age

log_rotation_age xác định khoảng thời gian tối đa mà một log file được sử dụng trước khi collector chuyển sang file mới.

~~~conf
log_rotation_age = 1d
~~~

### 6.1. Đơn vị

Tham số được cấu hình theo thời gian. Có thể dùng đơn vị như seconds, minutes, hours hoặc days theo cú pháp PostgreSQL configuration.

### 6.2. Giá trị zero

Đặt log_rotation_age = 0 để vô hiệu hóa rotation theo thời gian.

### 6.3. Rotation không nhất thiết đúng tại giây hết hạn

Collector kiểm tra điều kiện khi có log message cần ghi. Nếu hệ thống im lặng, file có thể chỉ được chuyển khi thông điệp tiếp theo xuất hiện.

### 6.4. Mục đích

Time rotation tạo các file theo ngày/giờ, giúp chia nhỏ log và đơn giản hóa archive/retention.

### 6.5. Daily rotation

Với log_rotation_age = 1d, collector có thể tạo file mới sau khoảng một ngày sử dụng. Đây là khoảng thời gian, không phải bảo đảm file luôn được mở đúng lúc nửa đêm theo timezone.

### 6.6. Time rotation và naming

Nếu log_filename chứa ngày, file thường có tên khác nhau qua ngày. Nếu tên lặp lại theo thứ hoặc tháng, log_truncate_on_rotation có thể ảnh hưởng file cũ cùng tên.

### 6.7. Không phải retention

log_rotation_age không xóa file cũ. Sau 90 ngày, nếu không có cleanup/retention, server vẫn có thể giữ tất cả 90 ngày log.

## 7. Rotation theo kích thước: log_rotation_size

log_rotation_size đặt ngưỡng kích thước file trước khi collector chuyển sang log file mới.

~~~conf
log_rotation_size = 102400
~~~

Giá trị trên là 102400 KB, xấp xỉ 100 MiB.

### 7.1. Đơn vị

Giá trị được tính bằng kilobytes. Kiểm tra đơn vị và cú pháp của version đang chạy khi dùng suffix.

### 7.2. Giá trị zero

Đặt log_rotation_size = 0 để vô hiệu hóa rotation theo kích thước.

### 7.3. Ngưỡng không phải hard cap tuyệt đối

Rotation được kiểm tra khi có thông điệp mới. Một log message lớn hoặc nhiều writes gần nhau có thể khiến file vượt ngưỡng trước khi chuyển.

### 7.4. Size rotation hữu ích khi workload biến động

Một database có thể ghi ít log ban đêm nhưng rất nhiều log khi batch job hoặc incident. Size rotation giúp chia file theo lượng dữ liệu thực tế.

### 7.5. Kết hợp age và size

Có thể bật cả hai điều kiện. Collector chuyển file khi một điều kiện rotation được đáp ứng. Điều này giới hạn kích thước file trong giai đoạn log volume cao và chia file theo thời gian khi volume thấp.

### 7.6. Không dự báo tổng dung lượng từ một ngưỡng

100 MiB mỗi file không có nghĩa tổng log chỉ dùng 100 MiB. Nếu tạo 40 files, tổng dung lượng có thể vượt 4 GiB.

## 8. log_truncate_on_rotation

log_truncate_on_rotation quyết định có truncate file cũ cùng tên khi mở file mới trong một trường hợp rotation cụ thể.

~~~conf
log_truncate_on_rotation = off
~~~

### 8.1. Default an toàn

Giữ off để tránh xóa nội dung của file cũ khi tên file được dùng lại.

### 8.2. Chỉ có tác dụng với time-based rotation

Tham số này chỉ truncate file có cùng tên khi rotation xảy ra do thời gian và collector mở lại filename đã tồn tại. Nó không áp dụng cho size-based rotation.

### 8.3. Không áp dụng như cách xóa log khi restart

Việc PostgreSQL restart và mở lại file không đồng nghĩa time-based rotation. Không dựa vào log_truncate_on_rotation để cleanup file cũ mỗi lần restart.

### 8.4. Filename có thể lặp lại

Ví dụ filename theo thứ trong tuần:

~~~conf
log_filename = 'postgresql-%a.log'
log_rotation_age = 1d
log_truncate_on_rotation = on
~~~

Khi tên file của một thứ được dùng lại ở tuần sau, nội dung cũ có thể bị truncate theo điều kiện time-based rotation. Điều này chỉ phù hợp nếu retention được quản lý riêng và việc ghi đè đã được chấp thuận.

### 8.5. Không bật tùy tiện

Nếu filename có độ phân giải thấp hoặc lặp lại, bật truncate có thể làm mất lịch sử mà operator tưởng vẫn còn.

### 8.6. Không thay thế retention

Truncate không tạo retention policy rõ ràng. Nó chỉ xử lý việc mở lại một filename trùng trong điều kiện cụ thể.

## 9. Cấu hình rotation mẫu

Ví dụ cấu hình cho logging collector ghi stderr và CSV:

~~~conf
# Cần restart nếu thay đổi logging_collector từ off sang on
logging_collector = on

log_destination = 'stderr,csvlog'
log_directory = '/var/log/postgresql'
log_filename = 'postgresql-%Y-%m-%d_%H%M%S.log'
log_file_mode = 0600

# Rotate khi đạt thời gian hoặc kích thước
log_rotation_age = 1d
log_rotation_size = 102400
log_truncate_on_rotation = off
~~~

### 9.1. Chọn filesystem

Đường dẫn /var/log/postgresql chỉ là ví dụ. Trước khi dùng, tạo directory, mount filesystem, đặt owner/group và xác nhận quyền ghi.

### 9.2. Tên file

Tên chứa timestamp giúp dễ archive. Với csvlog, kiểm tra file .csv tương ứng.

### 9.3. Rotation policy

Một ngày hoặc 100 MiB là ví dụ ban đầu, không phải chuẩn chung. Chọn giá trị theo log volume, ingestion pipeline và giới hạn file size của công cụ xử lý.

### 9.4. Reload và restart

logging_collector cần restart khi thay đổi. Các tham số log rotation/destination khác có thể reload theo version. Kiểm tra pg_settings.context và pg_settings.pending_restart để biết chính xác.

~~~sql
SELECT name, setting, unit, context, pending_restart
FROM pg_settings
WHERE name IN (
    'logging_collector',
    'log_destination',
    'log_directory',
    'log_filename',
    'log_rotation_age',
    'log_rotation_size',
    'log_truncate_on_rotation'
)
ORDER BY name;
~~~

### 9.5. Xác nhận sau áp dụng

Sau restart/reload, xem PostgreSQL logs, current_logfiles và file system để xác nhận collector mở đúng file.

## 10. Yêu cầu rotation thủ công

Có thể yêu cầu PostgreSQL chuyển log file ngay mà không cần đợi ngưỡng rotation.

### 10.1. SQL function

~~~sql
SELECT pg_rotate_logfile();
~~~

Hàm gửi yêu cầu cho logging collector rotate log. Nó chỉ có tác dụng khi logging collector đang hoạt động; kết quả boolean cho biết yêu cầu có được gửi thành công hay không.

### 10.2. Quyền

Việc gọi hàm có thể cần quyền quản trị hoặc quyền EXECUTE phù hợp. Không cấp quyền rộng chỉ để cho một user bất kỳ rotate log.

### 10.3. pg_ctl logrotate

Trên các phiên bản hỗ trợ:

~~~bash
pg_ctl -D /var/lib/postgresql/data logrotate
~~~

Lệnh yêu cầu server rotate log file. Cú pháp cụ thể tùy phiên bản pg_ctl.

### 10.4. SIGHUP khác rotation

Reload cấu hình bằng SIGHUP/pg_ctl reload không phải lúc nào cũng đồng nghĩa tạo log file mới. Dùng rotation function/command cho mục đích đó.

### 10.5. Khi nào rotate thủ công?

- Trước khi archive hoặc chuyển log file.
- Sau khi thay đổi log_filename/log_directory.
- Trước khi cleanup có kiểm soát.
- Khi cần tách log theo incident hoặc maintenance window.

### 10.6. Không gọi liên tục

Rotation quá thường xuyên tạo nhiều file nhỏ, làm tăng số file và chi phí ingestion. Dùng age/size policy làm cơ chế chính.

## 11. current_logfiles

Khi logging collector hoạt động, PostgreSQL duy trì file current_logfiles trong data directory để ghi đường dẫn các log files hiện đang được sử dụng cho destinations tương ứng.

### 11.1. Mục đích

Log shipper có thể đọc current_logfiles để biết file hiện tại thay vì đoán bằng glob hoặc chọn file mới nhất theo timestamp.

### 11.2. Nội dung

File có thể liệt kê destination và path, ví dụ stderr hoặc csvlog cùng đường dẫn log file hiện tại. Định dạng chính xác phụ thuộc phiên bản.

### 11.3. Cập nhật khi rotation

Khi collector chuyển file, current_logfiles được cập nhật để chỉ file mới. Consumer cần đọc lại file này và tiếp tục tail đúng path.

### 11.4. Không phải log index

current_logfiles không liệt kê toàn bộ log history. Nó chỉ chỉ ra files hiện hành.

### 11.5. Không dùng như retention inventory

Muốn biết tổng số file và dung lượng lịch sử, cần filesystem inventory hoặc log storage backend.

### 11.6. File có thể vắng mặt

Nếu logging collector tắt hoặc destination không thuộc cơ chế file hiện tại, file này có thể không tồn tại. Không coi việc thiếu file luôn là PostgreSQL lỗi.

## 12. Built-in rotation và external logrotate

Cần phân biệt log files do PostgreSQL logging collector sở hữu với log files do syslog hoặc service manager quản lý.

### 12.1. Collector-owned files

Khi logging_collector bật và ghi file, PostgreSQL giữ file descriptor và tự quản lý rotation. Dùng log_rotation_age, log_rotation_size hoặc pg_rotate_logfile().

### 12.2. External logrotate trên file đang mở

Nếu external utility rename hoặc xóa file trong khi PostgreSQL vẫn giữ file descriptor, process có thể tiếp tục ghi vào file đã rename/unlink. Operator có thể tưởng file mới nhận log trong khi PostgreSQL vẫn ghi vào inode cũ.

### 12.3. copytruncate

copytruncate sao chép nội dung rồi truncate file tại chỗ. Trong khoảng giữa copy và truncate, log message có thể bị mất hoặc nhân đôi. Nó cũng không phải lựa chọn mặc định tốt cho collector-managed files.

### 12.4. Khuyến nghị

Ưu tiên built-in rotation cho collector-owned files. Dùng external logrotate cho files được syslog daemon hoặc service manager tạo ra, theo hướng dẫn của hệ thống đó.

### 12.5. Cleanup khác rotation

Một script retention có thể xóa các log files đã đóng và quá hạn, nhưng cần xác định chính xác active files, archive status và race conditions. Không xóa file chỉ vì timestamp trông cũ.

### 12.6. Log shipper

Filebeat, Fluent Bit, Vector hoặc agent tương tự có thể tail log files. Cấu hình theo dõi rename/rotation, inode reuse và current_logfiles để tránh bỏ sót.

## 13. Syslog, journald và Windows Event Log

Nếu không dùng logging collector file output, rotation/retention được quản lý ở hệ thống tiếp nhận.

### 13.1. Syslog

PostgreSQL gửi message tới syslog daemon. Syslog có thể định tuyến theo facility/severity tới file hoặc remote destination.

### 13.2. syslog_facility

Cấu hình facility giúp phân biệt log PostgreSQL với dịch vụ khác. Chọn facility dành riêng để policy/filters dễ quản lý.

### 13.3. syslog_ident

Đặt identifier giúp nhận diện PostgreSQL trong syslog. Không dùng identifier trùng với ứng dụng khác.

### 13.4. journald

Trên hệ thống dùng systemd, service stdout/stderr có thể được journald thu thập. journald có giới hạn dung lượng, retention và vacuum policy riêng.

### 13.5. journalctl

Có thể xem log PostgreSQL qua journalctl theo service/unit. Cú pháp unit phụ thuộc package và service name.

~~~bash
journalctl -u postgresql --since "1 hour ago"
~~~

### 13.6. journal size limits

Các cấu hình SystemMaxUse, SystemKeepFree, SystemMaxFileSize và RuntimeMaxUse có thể điều khiển dung lượng journal. Tên và semantics cần kiểm tra theo systemd version.

### 13.7. Windows Event Log

Trên Windows, cấu hình log_destination phù hợp và dùng Event Viewer/Windows Event Log retention/export policies. Không áp dụng PostgreSQL file rotation settings cho Event Log.

### 13.8. Remote syslog

Gửi log tới máy chủ tập trung giúp giảm phụ thuộc local disk và giữ log sau khi host mất. Tuy nhiên, cần network resilience, buffering, encryption và capacity của collector.

## 14. Rotation, retention, compression và archival

Bốn khái niệm này giải quyết các vấn đề khác nhau.

| Hoạt động | Mục tiêu | Có xóa log cũ không? |
| --- | --- | --- |
| Rotation | Tách file đang ghi thành file mới | Không |
| Retention | Giữ log trong một khoảng thời gian/số lượng nhất định | Có thể |
| Compression | Giảm dung lượng file đã đóng | Không tự xóa |
| Archival | Chuyển bản log tới storage dài hạn/central | Không nhất thiết |

### 14.1. Rotation

Tạo file mới để tiếp tục ghi. File cũ vẫn tồn tại.

### 14.2. Retention

Ví dụ giữ local 7 ngày, central storage 90 ngày và archive lạnh 1 năm. Thời hạn thực tế phải theo yêu cầu pháp lý, audit và nội bộ.

### 14.3. Compression

Nén các file đã đóng để giảm storage. Không nén file đang được PostgreSQL hoặc shipper ghi/đọc nếu pipeline không hỗ trợ.

### 14.4. Archival

Copy hoặc ship log tới object storage, log platform hoặc backup repository. Xác nhận upload hoàn tất và checksum trước khi xóa local copy nếu policy yêu cầu.

### 14.5. Lifecycle

Remote storage có thể áp dụng lifecycle rules để chuyển dữ liệu sang tier rẻ hơn hoặc xóa sau retention. Bảo đảm policy phù hợp legal hold và incident investigations.

### 14.6. Rotation không giới hạn tổng log

Nếu mỗi ngày tạo 10 GB và giữ vô thời hạn, rotation chỉ tạo nhiều file 10 GB; tổng dung lượng vẫn tăng vô hạn.

## 15. Capacity planning cho log

Ước tính dung lượng cần dựa trên volume thực tế và peak behavior.

### 15.1. Đo log rate

Đo bytes được tạo trong một khoảng thời gian đại diện, chẳng hạn một giờ hoặc một ngày làm việc. Bao gồm giờ cao điểm, batch jobs và maintenance.

### 15.2. Công thức cơ bản

Nếu log rate trung bình là R bytes/second và thời gian giữ local là D ngày:

\[
S_{\text{raw}} = R \times 86400 \times D
\]

### 15.3. Ví dụ

Nếu trung bình 500 KB/s và giữ 7 ngày:

\[
500 \times 1024 \times 86400 \times 7
\approx 309.4\ \text{GB}
\]

Đây là dung lượng thập phân gần đúng trước compression, metadata và headroom.

### 15.4. Peak factor

Dùng peak factor cho batch/incident. Nếu peak volume gấp 3 lần baseline, capacity plan phải tính đến burst kéo dài chứ không chỉ average.

### 15.5. Compression ratio

Không mặc định compression luôn đạt một tỷ lệ cố định. SQL text, JSON, repeated prefixes và CSV có thể nén tốt, nhưng đo bằng dữ liệu thật.

### 15.6. Headroom

Không phân bổ 100% filesystem cho log. Giữ free space cho file đang mở, rotation, temporary archive copy, log shipper buffer và hoạt động của OS.

### 15.7. Inodes và số lượng files

Nhiều file nhỏ có thể làm cạn inode dù còn bytes. Theo dõi cả file count/inode usage.

### 15.8. Storage isolation

Đặt log trên filesystem riêng có thể bảo vệ PGDATA/WAL khỏi log bursts. Tuy nhiên, mount riêng vẫn cần monitoring, backup và capacity; nếu mount mất, logging pipeline bị ảnh hưởng.

### 15.9. Không dùng cùng filesystem cho mọi thứ khi rủi ro cao

Data files, WAL, temporary files và logs có pattern growth khác nhau. Tách volume giúp giới hạn blast radius, nhưng phải tránh tạo nhiều volume nhỏ khó quản lý.

## 16. Theo dõi dung lượng filesystem

PostgreSQL statistics views không cung cấp đầy đủ dung lượng filesystem log. Cần kết hợp OS monitoring.

### 16.1. Linux df

~~~bash
df -h /var/log/postgresql
df -i /var/log/postgresql
~~~

### 16.2. Kiểm tra file sizes

~~~bash
du -sh /var/log/postgresql
du -ah /var/log/postgresql | sort -h | tail -20
~~~

### 16.3. Windows

Dùng Get-Volume hoặc công cụ monitoring của hệ điều hành để xem free space và dung lượng thư mục log.

### 16.4. Node exporter

Thu thập filesystem free bytes, available bytes, size và inode metrics. Alert theo mountpoint riêng cho log volume.

### 16.5. Growth rate

Đo dung lượng tăng theo giờ/ngày để ước lượng time-to-full:

\[
T_{\text{full}} =
\frac{\text{free bytes}}
{\text{bytes generated per second}}
\]

Công thức là ước lượng; cần dùng peak rate và reserve margin khi thiết kế alert.

### 16.6. Monitor log file count

Số file tăng bất thường có thể báo rotation quá nhỏ, naming collision hoặc cleanup không chạy.

### 16.7. Alert thresholds

Ví dụ cảnh báo warning ở 75%, critical ở 90% hoặc khi time-to-full thấp hơn thời gian phản ứng. Điều chỉnh theo dung lượng, tốc độ tăng và khả năng mở rộng volume.

## 17. Kiểm soát log volume bằng logging parameters

Rotation chỉ chia file. Để kiểm soát tốc độ tăng, cần chọn sự kiện nào được ghi.

### 17.1. log_min_messages

Điều khiển mức message tối thiểu được ghi. Thay đổi mức log có thể ảnh hưởng cả error reporting và diagnostic detail; không nâng ngưỡng một cách mù quáng.

### 17.2. log_min_error_statement

Quyết định mức severity mà statement gây lỗi được log. Cân nhắc nhu cầu điều tra và privacy.

### 17.3. log_statement

Các giá trị phổ biến:
- none: không log statement theo cơ chế này.
- ddl: log DDL statements.
- mod: log DDL và data-modifying statements.
- all: log tất cả statements.

Bật all có thể tạo lượng log rất lớn và ghi nội dung nhạy cảm.

### 17.4. log_min_duration_statement

Log statement hoàn tất có duration lớn hơn hoặc bằng threshold. Ví dụ:

~~~conf
log_min_duration_statement = 500ms
~~~

Đây là ngưỡng thời gian, khác với planner cost. Giá trị -1 tắt tính năng này; 0 log mọi statement duration theo semantics của tham số.

### 17.5. log_duration

Ghi duration của statement. Nếu kết hợp với log_min_duration_statement hoặc statement logging, có thể tạo thông tin trùng lặp. Hiểu output và volume trước khi bật.

### 17.6. Sampling

Một số phiên bản hỗ trợ log_min_duration_sample và log_statement_sample_rate để lấy mẫu query chậm. Dùng sampling khi cần quan sát workload lớn mà không log mọi query đủ điều kiện.

### 17.7. log_connections và log_disconnections

Ghi sự kiện kết nối/ngắt kết nối. Hữu ích khi điều tra connection churn, nhưng workload có nhiều short-lived connections có thể tạo nhiều log lines.

### 17.8. log_checkpoints

Ghi thông tin checkpoint. Hữu ích cho chẩn đoán I/O/WAL nhưng volume phụ thuộc checkpoint frequency.

### 17.9. log_lock_waits

Ghi thông tin lock wait vượt deadlock_timeout. Có thể giúp tìm blocking nhưng volume tăng khi contention cao.

### 17.10. log_temp_files

Log temporary files lớn hơn threshold; giá trị -1 tắt và 0 log mọi temporary file. Chọn threshold để điều tra sort/hash spills.

### 17.11. log_autovacuum_min_duration

Ghi các autovacuum actions kéo dài hơn threshold. Có thể dùng để theo dõi vacuum chậm hoặc log mọi autovacuum theo cấu hình.

### 17.12. auto_explain

Extension auto_explain có thể ghi execution plans cho query vượt ngưỡng. Bật analyze/buffers/timing có overhead và có thể tăng log volume đáng kể. Dùng sample rate, duration threshold và role/scope phù hợp.

## 18. Cấu hình logging thực tế theo mục tiêu

### 18.1. Baseline production

Ví dụ:

~~~conf
log_min_messages = warning
log_min_error_statement = error
log_min_duration_statement = 500ms
log_checkpoints = on
log_lock_waits = on
log_temp_files = 64MB
log_line_prefix = '%m [%p] %q%u@%d %r app=%a '
~~~

Đây chỉ là baseline tham khảo. Điều chỉnh threshold theo SLA, workload và yêu cầu incident.

### 18.2. Điều tra ngắn hạn

Có thể tạm thời giảm log_min_duration_statement hoặc bật thêm connection/statement logs cho một cửa sổ có kiểm soát. Ghi thời gian bắt đầu/kết thúc và kế hoạch hoàn nguyên.

### 18.3. Tránh log_statement=all kéo dài

Chỉ bật khi có lý do rõ ràng, ước lượng volume và đánh giá dữ liệu nhạy cảm. Một ứng dụng chatty có thể tạo log lớn hơn nhiều lần so với database data growth.

### 18.4. Log slow query và pg_stat_statements

Dùng slow query logs để thấy các execution cụ thể; dùng pg_stat_statements để tổng hợp workload theo query identity. Hai công cụ bổ sung nhau và có thể giảm nhu cầu log mọi statement.

### 18.5. Prefix hữu ích

log_line_prefix có thể đưa timestamp, PID, user, database, remote address và application_name vào mỗi dòng. Điều này giúp correlation nhưng tăng một ít dung lượng mỗi record.

### 18.6. Sampling và threshold

Tăng threshold hoặc sampling rate thấp hơn để kiểm soát volume trong workload rất lớn. Luôn bảo đảm vẫn giữ đủ thông tin cho sự cố cần điều tra.

## 19. Bảo vệ dữ liệu nhạy cảm trong log

Log có thể chứa SQL text, bind values, user names, database names, client IPs và nội dung lỗi.

### 19.1. Statement logging

log_statement và log_min_duration_statement có thể ghi query text. Query text đôi khi chứa literal credentials, tokens, personal data hoặc business information.

### 19.2. Bind parameters

Các tham số log_parameter_max_length và log_parameter_max_length_on_error trên phiên bản hỗ trợ điều khiển mức parameter data được ghi. Kiểm tra default và semantics của version trước khi áp dụng.

### 19.3. Passwords

Không ghi password trực tiếp trong SQL hoặc connection strings. Dùng secret mechanisms và tránh đưa credentials vào error messages.

### 19.4. File permissions

Giữ log_file_mode chặt, ownership đúng và hạn chế nhóm có thể đọc file.

### 19.5. Transport encryption

Log shipper gửi tới central storage qua TLS hoặc kênh bảo mật tương đương.

### 19.6. Access control

Phân quyền log viewer theo vai trò. Không cấp quyền đọc raw SQL logs cho mọi người chỉ vì họ có quyền xem dashboard tổng hợp.

### 19.7. Retention và privacy

Giữ log đủ thời gian cần thiết, nhưng tránh lưu vô thời hạn nếu không có yêu cầu. Thực hiện deletion theo policy và legal hold.

### 19.8. Redaction

Dùng application logging/redaction hoặc log pipeline filters nếu cần mask dữ liệu. Kiểm thử filters để không vô tình xóa SQLSTATE, query context hay thông tin cần thiết cho điều tra.

## 20. Log format và phân tích

### 20.1. stderr text

Text dễ đọc trực tiếp và thuận tiện cho operator, nhưng parser cần xử lý multiline messages và prefix.

### 20.2. csvlog

CSV có fields rõ ràng, thuận tiện import vào hệ thống phân tích. Query text/detail có thể chứa dấu phẩy, newline và quoting; dùng CSV parser chuẩn thay vì split chuỗi thủ công.

### 20.3. jsonlog

JSON thuận tiện cho log platforms và structured search. Kiểm tra schema field theo PostgreSQL version.

### 20.4. Multiline entries

Error detail, context và statement có thể trải qua nhiều dòng. Log shipper cần multiline parser phù hợp.

### 20.5. Correlation

Dùng log_line_prefix và application_name để liên kết logs với session/request traces. Session ID, PID và transaction ID giúp điều tra nhưng không nên dùng làm high-cardinality metrics labels.

### 20.6. Timezone

Cấu hình log_timezone nhất quán với hệ thống log platform. Đồng bộ clocks bằng NTP/chrony để correlation giữa database, application và OS chính xác.

### 20.7. Timestamp precision

Dùng timestamp có timezone/precision phù hợp. Khi parse, tránh giả định log timestamp luôn là UTC nếu cấu hình đang dùng local timezone.

## 21. Log shipping và central storage

Log shipping giúp lưu log ngoài database host, giảm rủi ro mất log khi host/volume gặp sự cố.

### 21.1. Agent

Có thể dùng Fluent Bit, Vector, Filebeat hoặc agent tương đương để tail file và chuyển log.

### 21.2. current_logfiles

Với collector-managed files, agent có thể dùng current_logfiles để xác định file hiện tại. Kiểm tra agent xử lý rename, rotation và file reopen đúng.

### 21.3. Buffer

Agent thường cần buffer khi network hoặc central storage tạm thời unavailable. Buffer cũng dùng disk; giới hạn kích thước và theo dõi backlog.

### 21.4. Delivery semantics

Một số pipeline có thể gửi at-least-once và tạo duplicates khi retry. Dùng timestamp, host, instance, PID/session metadata và event fields để deduplicate khi cần.

### 21.5. Central retention

Đặt retention ở central storage theo policy. Local retention có thể ngắn hơn nếu central copy đã được xác minh.

### 21.6. Archive checksum

Nếu archive dài hạn, tạo checksum và lưu metadata về cluster, instance, PostgreSQL version, time range và log format.

### 21.7. Failure behavior

Xác định điều gì xảy ra khi central endpoint mất kết nối: buffer bao lâu, drop khi nào, alert nào firing và local disk có đủ chỗ không.

## 22. Compression và cleanup an toàn

### 22.1. Chỉ nén file đã đóng

Không nén hoặc đổi tên file mà PostgreSQL collector đang ghi. Dùng current_logfiles hoặc log pipeline state để xác định active file.

### 22.2. Nén theo batch

Nén log đã rotate theo lịch, ưu tiên pipeline stream/central storage nếu phù hợp.

### 22.3. Kiểm tra thành công

Chỉ xóa source file sau khi compression/archive thành công, file output có size hợp lý và checksum/verification đạt yêu cầu.

### 22.4. Retention cleanup

Cleanup nên dựa trên age, archive status và policy. Trước khi xóa, loại trừ active files và files chưa được ship.

### 22.5. Dry run

Trước khi bật job xóa, liệt kê những files sẽ bị xóa và review. Dùng dry-run mode nếu script/tool hỗ trợ.

### 22.6. Tránh xóa theo wildcard rộng

Không chạy lệnh xóa chung trong /var/log hoặc PGDATA. Giới hạn đúng thư mục, pattern và ownership của log files.

### 22.7. Race conditions

Một file vừa rotate có thể vẫn đang được shipper đọc. Retention phải cho shipper đủ thời gian hoàn tất và không xóa file đang mở/đang retry.

### 22.8. Disk emergency

Khi filesystem gần đầy, ưu tiên giữ database hoạt động và log pipeline có thể phục hồi. Xác định active files, archive status và cleanup candidates; không xóa bừa current log hoặc WAL.

## 23. Phân tách log, data và WAL

### 23.1. Separate log filesystem

Đặt log_directory trên volume riêng có thể ngăn log bursts chiếm dung lượng của PGDATA và pg_wal.

### 23.2. Giới hạn riêng

Filesystem riêng cho phép quota, alert và capacity planning độc lập.

### 23.3. Mount dependencies

Đảm bảo mount có trước khi PostgreSQL start. Nếu mount không tồn tại, server có thể ghi vào thư mục mountpoint trên root filesystem, tạo log ngoài dự kiến.

### 23.4. Mount validation

Service startup có thể dùng dependency/preflight để xác nhận volume đúng mount source và đủ free space.

### 23.5. Không đặt log trên tmpfs tùy tiện

Log trên volatile storage có thể mất khi reboot và có giới hạn dung lượng. Chỉ dùng nếu có thiết kế ship/retention rõ ràng.

### 23.6. PGDATA/WAL safety

Không để cleanup log script có thể đi vào PGDATA, pg_wal hoặc tablespace paths. Dùng path allowlist và canonical path checks.

## 24. Monitoring log pipeline

Theo dõi cả PostgreSQL logging và hệ thống nhận log.

| Metric | Ý nghĩa |
| --- | --- |
| Filesystem free bytes | Dung lượng còn lại |
| Filesystem usage ratio | Tỷ lệ đã dùng |
| Inode free ratio | Khả năng tạo thêm files |
| Log bytes generated | Tốc độ tạo log |
| Log file count | Số file hiện có |
| Oldest local log age | Log cũ nhất còn local |
| Archive success/failure | Trạng thái archive |
| Shipper backlog | Log chưa gửi |
| Dropped events | Log bị mất ở pipeline |
| Collector errors | Lỗi ghi/mở file |
| Rotation count | Tần suất rotate |
| Time to full | Ước lượng thời gian tới khi hết dung lượng |

### 24.1. Filesystem metrics

Dùng node_exporter hoặc OS agent để theo dõi mount chứa log.

### 24.2. PostgreSQL metrics

Có thể theo dõi logging settings, collector process và database workload, nhưng dung lượng file thường cần OS-level metrics.

### 24.3. Log shipper metrics

Theo dõi queue size, retries, output errors, dropped records và processing lag.

### 24.4. Central storage

Theo dõi ingest rate, indexing latency, retention capacity và query availability của log platform.

### 24.5. Alert ownership

Mỗi alert cần có owner: DBA, platform/infra hoặc observability team. Disk full và log shipping failure có thể thuộc các nhóm khác nhau.

## 25. Alert và ngưỡng capacity

### 25.1. Disk usage

Ví dụ:
- Warning khi log filesystem vượt 75%.
- Critical khi vượt 90%.
- Emergency khi free bytes thấp hơn reserve tối thiểu.

Ngưỡng thực tế cần dựa trên tốc độ tăng và thời gian phản ứng.

### 25.2. Time-to-full

Alert nếu dự báo dung lượng còn lại thấp hơn thời gian cần mở rộng volume hoặc xử lý log burst.

### 25.3. Shipper backlog

Alert khi backlog vượt thời gian chịu đựng hoặc local buffer sắp đầy.

### 25.4. Archive failures

Alert khi archive/ship không thành công liên tục hoặc oldest unshipped log vượt policy.

### 25.5. No new logs

Nếu workload có hoạt động nhưng không có log/heartbeat trong thời gian dài, kiểm tra collector/destination. Tuy nhiên, không có log mới trên hệ thống idle có thể bình thường.

### 25.6. Rotation failure

Theo dõi current_logfiles không thay đổi khi dự kiến rotation, collector errors hoặc file size vượt ngưỡng quá lâu.

### 25.7. Inode pressure

Cảnh báo inode riêng, đặc biệt khi size rotation tạo rất nhiều file nhỏ.

## 26. Troubleshooting các vấn đề thường gặp

### Lỗi 1. Log không xuất hiện trong log_directory

Kiểm tra logging_collector, log_destination, log_directory, file permissions và startup logs. Nếu collector tắt, log có thể nằm ở systemd/container stderr.

### Lỗi 2. logging_collector không bật sau reload

Tham số này cần restart. Kiểm tra pg_settings.context và pending_restart rồi restart theo maintenance procedure.

### Lỗi 3. Log file không rotate theo thời gian

Kiểm tra log_rotation_age, collector state, filename, log destination và việc có log messages mới sau khi age threshold đạt hay không.

### Lỗi 4. File không rotate theo size

Kiểm tra log_rotation_size có bằng zero không, file size thực tế, destination và collector logs. Rotation được kiểm tra khi có log message mới.

### Lỗi 5. File cũ bị truncate

Kiểm tra log_truncate_on_rotation và filename pattern có tái sử dụng tên không. Tắt truncate nếu cần giữ lịch sử.

### Lỗi 6. Tổng dung lượng vẫn tăng

Rotation không xóa files. Thiết lập retention, compression, archive và cleanup cho log đã đóng.

### Lỗi 7. External logrotate tạo file rỗng

PostgreSQL có thể vẫn ghi vào file descriptor cũ sau rename/unlink. Dùng built-in rotation cho collector-owned files và điều chỉnh logrotate architecture.

### Lỗi 8. current_logfiles không tồn tại

Kiểm tra logging_collector và file destinations. Với syslog/journald, không kỳ vọng file này.

### Lỗi 9. CSV logs không xuất hiện

Kiểm tra log_destination có csvlog, logging_collector bật, restart/reload phù hợp và quyền thư mục.

### Lỗi 10. Disk đầy

Kiểm tra active files, log rate, shipper backlog, archive status và filesystem. Cleanup có kiểm soát các log đã đóng/đã archive; không xóa WAL hoặc active log tùy tiện.

### Lỗi 11. Log shipper bỏ sót records

Kiểm tra rotation handling, file identity/inode tracking, multiline parser, buffer limits và permissions.

### Lỗi 12. Log volume tăng đột biến

Tìm log_statement, log_min_duration_statement, log_connections, log_disconnections, log_temp_files, auto_explain và application retry storms.

### Lỗi 13. Không có query chậm trong log

Kiểm tra log_min_duration_statement, sample settings, role/database overrides và timezone/time range.

### Lỗi 14. Log chứa thông tin nhạy cảm

Điều chỉnh statement/parameter logging, giới hạn access, áp dụng redaction và review log retention.

### Lỗi 15. Rotation tạo quá nhiều file nhỏ

Tăng log_rotation_size hoặc log_rotation_age, cải thiện filename pattern và giảm log noise.

### Lỗi 16. Log filesystem không mount

Kiểm tra mount dependency, service startup order, mountpoint permissions và alert. Xác nhận PostgreSQL không ghi nhầm vào root filesystem.

### Lỗi 17. Syslog log không được rotate

Kiểm tra syslog daemon rules và external rotation policy; PostgreSQL log_rotation settings không điều khiển file do syslog sở hữu.

### Lỗi 18. Journald chiếm nhiều disk

Kiểm tra journald retention/vacuum settings và persistent journal policy. Không xóa journal files trực tiếp khi daemon đang quản lý.

### Lỗi 19. Archive thành công nhưng local disk vẫn đầy

Kiểm tra retention cleanup có chạy, archive verification status và active-file exclusion. Archive không tự xóa local files.

### Lỗi 20. Không thể ghi log khi volume read-only

Kiểm tra filesystem state, kernel/storage errors và mount status. Xử lý storage trước khi thay đổi PostgreSQL logging policy.

## 27. Runbook khi log filesystem gần đầy

1. Xác nhận mountpoint và phần trăm dung lượng/inode đang dùng.
2. Kiểm tra tốc độ tăng và ước lượng time-to-full.
3. Xác định log directory, active log files và current_logfiles.
4. Kiểm tra PostgreSQL collector errors và server logs.
5. Kiểm tra log shipper backlog, archive failures và central storage availability.
6. Tìm nguyên nhân tăng volume: statement logging, retry storm, connection churn hoặc error burst.
7. Nếu cần, tạm điều chỉnh logging verbosity theo incident owner và ghi nhận thời điểm.
8. Không tắt logging toàn bộ nếu vẫn cần error/security records.
9. Rotate log bằng cơ chế PostgreSQL hoặc destination owner.
10. Xác nhận file cũ đã đóng và shipper đã hoàn tất đọc.
11. Archive/compress log cũ theo policy.
12. Chỉ xóa log đã đủ điều kiện retention và archive verification.
13. Mở rộng volume hoặc tăng capacity nếu cần.
14. Xác nhận PGDATA và pg_wal còn đủ headroom.
15. Theo dõi filesystem và log rate sau xử lý.
16. Ghi incident timeline, dung lượng giải phóng và nguyên nhân gốc.

## 28. Runbook điều chỉnh logging trong incident

### 28.1. Xác định câu hỏi điều tra

Ví dụ cần tìm query chậm, lock waits, connection churn hay checkpoint stalls.

### 28.2. Chọn tham số tối thiểu

Chỉ bật những log categories liên quan. Tránh bật log_statement=all nếu slow-query threshold hoặc targeted diagnostics đủ dùng.

### 28.3. Xác định time window

Ghi rõ thời điểm bắt đầu, thời gian giữ cấu hình và người chịu trách nhiệm hoàn nguyên.

### 28.4. Ước tính volume

Dựa trên workload và log rate hiện tại, tính dung lượng tăng thêm trong cửa sổ điều tra.

### 28.5. Kiểm tra privacy

Đánh giá query text, parameter values, credentials và personal data có thể xuất hiện.

### 28.6. Hoàn nguyên

Sau khi thu thập đủ dữ liệu, khôi phục settings baseline và xác nhận bằng SHOW/current_setting.

### 28.7. Lưu artifact

Ship/archive logs liên quan incident, ghi metadata và access control phù hợp.

## 29. Thiết kế retention policy

Retention cần phân loại theo môi trường, loại log và mục đích sử dụng.

| Nhóm | Ví dụ policy cần xác định |
| --- | --- |
| Local active logs | Giữ đủ để xử lý khi central storage tạm lỗi |
| Local rotated logs | Giữ ngắn hạn theo dung lượng volume |
| Central searchable logs | Giữ thời gian phục vụ vận hành/incident |
| Cold archive | Giữ dài hạn theo audit/legal policy |
| Debug/temporary logs | Giữ ngắn và có cleanup rõ ràng |
| Security/audit logs | Theo chính sách riêng và access controls |

### 29.1. Local retention

Local storage cần đủ buffer khi shipper bị gián đoạn. Không dùng local disk làm archive vô hạn.

### 29.2. Central retention

Central log platform có thể giữ dữ liệu searchable trong thời gian cần thiết, sau đó chuyển sang archive.

### 29.3. Legal hold

Nếu có legal hold hoặc incident investigation, bảo đảm retention job không xóa các artifacts được bảo toàn.

### 29.4. Retention theo severity

Một số tổ chức giữ error/security logs lâu hơn debug/statement logs. Phải định nghĩa dựa trên policy và khả năng phân loại.

### 29.5. Review định kỳ

Review log volume, retention duration, compression ratio, central storage cost và access patterns.

## 30. Kiểm tra cấu hình hiện tại bằng SQL

### 30.1. Xem logging settings

~~~sql
SELECT name, setting, unit, context, source, pending_restart
FROM pg_settings
WHERE name LIKE 'log%'
   OR name = 'logging_collector'
ORDER BY name;
~~~

### 30.2. Xem đường dẫn log hiện tại

Đọc file current_logfiles trên filesystem nếu collector đang hoạt động. SQL không thay thế việc xác minh file path thực tế.

### 30.3. Xem config source

pg_settings.source cho biết setting đến từ đâu, chẳng hạn default, configuration file, command line, database/role hoặc session.

### 30.4. Xem config file errors

~~~sql
SELECT *
FROM pg_file_settings
WHERE error IS NOT NULL;
~~~

View này giúp phát hiện lỗi trong cấu hình file mà server đọc được; quyền truy cập phụ thuộc role.

### 30.5. Xem reload time

~~~sql
SELECT pg_conf_load_time();
~~~

Thời điểm load config giúp đối chiếu thay đổi gần đây. Với parameter cần restart, kiểm tra pending_restart.

## 31. Thử nghiệm rotation trong môi trường lab

### 31.1. Chuẩn bị

Dùng PostgreSQL lab riêng, bật logging_collector và đặt log_directory vào thư mục test có dung lượng đủ.

### 31.2. Cấu hình size nhỏ

Đặt log_rotation_size thấp để quan sát rotation nhanh. Không áp dụng giá trị test này lên production.

### 31.3. Tạo log messages

Sinh một số statement/notice phù hợp để tạo log. Tránh tạo vòng lặp vô hạn hoặc tải lớn.

### 31.4. Kiểm tra file

Quan sát file names, sizes và current_logfiles sau khi rotation.

### 31.5. Thử age rotation

Giảm log_rotation_age trong lab và tạo message sau khi threshold đạt để quan sát behavior.

### 31.6. Thử truncate

Dùng filename pattern lặp lại trên lab, quan sát log_truncate_on_rotation=off/on để hiểu nguy cơ ghi đè. Giữ bản backup test.

### 31.7. Test shipper

Rotate trong khi shipper đang tail file. Xác nhận không mất/nhân đôi records và shipper theo file mới.

### 31.8. Cleanup

Kiểm tra retention dry run và xác nhận active files được loại trừ.

## 32. Bài tập thực hành

Các bài tập thực hiện trong PostgreSQL lab hoặc môi trường observability riêng. Không thử xóa log đang hoạt động hoặc làm đầy filesystem production.

### Bài 1. Logging collector

logging_collector có nhiệm vụ gì?

### Bài 2. Destination

Kể năm log destinations PostgreSQL có thể hỗ trợ tùy hệ điều hành/version.

### Bài 3. CSV

Vì sao csvlog thuận tiện cho log analysis?

### Bài 4. JSON

Có thể dùng jsonlog trên mọi major version không?

### Bài 5. Restart

Vì sao thay logging_collector thường cần restart?

### Bài 6. Directory

log_directory tương đối được tính từ đâu?

### Bài 7. Filename

log_filename hỗ trợ loại pattern nào?

### Bài 8. Age rotation

Tham số nào điều khiển rotation theo thời gian?

### Bài 9. Size rotation

Tham số nào điều khiển rotation theo kích thước?

### Bài 10. Zero

Đặt log_rotation_size=0 có ý nghĩa gì?

### Bài 11. Truncate

log_truncate_on_rotation có áp dụng cho size rotation không?

### Bài 12. Filename reuse

Vì sao filename chỉ chứa thứ trong tuần có thể làm mất log cũ khi truncate được bật?

### Bài 13. Retention

Rotation có tự xóa log cũ không?

### Bài 14. Manual rotation

Viết SQL yêu cầu PostgreSQL rotate log.

### Bài 15. pg_ctl

Lệnh pg_ctl nào yêu cầu log rotation?

### Bài 16. current_logfiles

File current_logfiles dùng để làm gì?

### Bài 17. External logrotate

Vì sao external logrotate có thể khiến PostgreSQL tiếp tục ghi vào file đã rename?

### Bài 18. Syslog

Ai quản lý rotation khi PostgreSQL gửi log tới syslog?

### Bài 19. Journald

Công cụ nào xem log của systemd service?

### Bài 20. Capacity

Viết công thức ước tính raw log storage theo bytes/second và retention days.

### Bài 21. Inodes

Vì sao cần theo dõi inode ngoài disk bytes?

### Bài 22. Filesystem isolation

Lợi ích của log filesystem riêng là gì?

### Bài 23. Slow query

Tham số nào đặt ngưỡng duration để log statement chậm?

### Bài 24. Statement logging

Kể các mức phổ biến của log_statement.

### Bài 25. Connections

Tham số nào ghi log connect/disconnect?

### Bài 26. Lock waits

Tham số nào bật logging cho lock waits đủ lâu?

### Bài 27. Temp files

Tham số nào điều khiển log temporary files?

### Bài 28. Checkpoints

Tham số nào bật checkpoint logging?

### Bài 29. Sensitive data

Vì sao log_statement=all có thể gây rủi ro bảo mật và dung lượng?

### Bài 30. Compression

Khi nào nên nén log files?

### Bài 31. Archive

Vì sao cần xác nhận archive thành công trước khi xóa local log?

### Bài 32. Monitoring

Nêu bốn metrics cần theo dõi cho log filesystem/pipeline.

### Bài 33. Time-to-full

Viết công thức ước tính thời gian tới khi hết dung lượng.

### Bài 34. Disk full

Nêu ba bước đầu tiên khi log volume gần đầy.

### Bài 35. CSV parser

Vì sao không nên parse csvlog bằng cách split theo dấu phẩy?

### Bài 36. Log shipper

Nêu hai rủi ro cần kiểm thử khi file rotation diễn ra.

### Bài 37. Config inspection

View nào giúp xem logging settings và pending_restart?

### Bài 38. File settings

View nào hiển thị lỗi khi parse configuration files?

### Bài 39. Lab

Thiết kế một bài lab thử time rotation, size rotation và truncate behavior.

### Bài 40. Production policy

Đề xuất policy rotation, retention, archive và alert cho production PostgreSQL.

## 33. Lời giải tham khảo

### Bài 1–7. Collector và destinations

logging_collector thu stderr messages và ghi vào log files. Destinations gồm stderr, csvlog, jsonlog (tùy version), syslog và eventlog trên Windows. csvlog có fields cấu trúc nên dễ parse bằng CSV parser. jsonlog không có trên mọi major version. logging_collector cần restart khi thay đổi trạng thái vì đây là startup parameter. log_directory tương đối tính từ PGDATA. log_filename hỗ trợ strftime patterns.

### Bài 8–13. Rotation semantics

log_rotation_age điều khiển time rotation; log_rotation_size điều khiển size rotation. Size=0 tắt size rotation. log_truncate_on_rotation không áp dụng cho size-based rotation; nó truncate filename trùng trong trường hợp time-based rotation. Filename theo thứ lặp lại hàng tuần, nếu truncate bật, có thể làm mất nội dung cũ. Rotation chỉ tạo file mới, không xóa file cũ.

### Bài 14–19. Rotation thủ công và external systems

~~~sql
SELECT pg_rotate_logfile();
~~~

pg_ctl logrotate yêu cầu collector rotate file. current_logfiles chỉ ra file đang hoạt động cho destinations do collector quản lý. External logrotate có thể rename/unlink inode nhưng PostgreSQL vẫn giữ descriptor cũ. Syslog daemon quản lý syslog output. Dùng journalctl để xem systemd service logs.

### Bài 20–22. Capacity

Raw storage bằng bytes/second nhân 86400 nhân retention days. Inodes cần theo dõi vì rất nhiều file có thể làm hết inode dù còn bytes. Filesystem riêng giảm khả năng log bursts chiếm dung lượng PGDATA/WAL.

### Bài 23–29. Volume và bảo mật

log_min_duration_statement đặt duration threshold. log_statement có none, ddl, mod, all. log_connections/log_disconnections ghi sự kiện connection. log_lock_waits ghi lock waits. log_temp_files ghi temporary files. log_checkpoints bật checkpoint logs. log_statement=all có thể tạo volume lớn và ghi query literals/secrets hoặc dữ liệu nhạy cảm.

### Bài 30–38. Pipeline và monitoring

Nén file đã đóng, sau khi PostgreSQL không còn ghi. Chỉ xóa local file sau khi archive/ship đã xác minh. Theo dõi filesystem free bytes/usage, inode free, log generation rate, shipper backlog và archive failures. Time-to-full = free bytes / bytes generated per second. Khi disk gần đầy, xác định active files, shipper/archive status và log burst trước khi cleanup có kiểm soát. CSV cần parser chuẩn vì field có quoting, dấu phẩy và newline. Rotation có thể gây file rename/inode changes, mất/nhân đôi records nếu shipper không xử lý đúng. pg_settings hiển thị settings/context/pending_restart; pg_file_settings hiển thị configuration errors.

### Bài 39–40. Lab và policy

Lab bật collector trên instance riêng, đặt size threshold nhỏ, sinh log có kiểm soát, kiểm tra file/current_logfiles, thử age threshold rồi phát sinh message, sau đó dùng filename lặp lại để quan sát truncate off/on. Test shipper và cleanup dry run.

Production policy cần:
- Chọn destination và format phù hợp.
- Rotate theo age và size dựa trên measured volume.
- Giữ truncate off trừ khi có yêu cầu ghi đè được kiểm soát.
- Dùng local retention ngắn và central/archive retention theo policy.
- Chỉ compress/delete file đã đóng và archive verified.
- Theo dõi disk, inode, log rate, backlog và time-to-full.
- Alert theo headroom và thời gian phản ứng.
- Review statement logging và privacy định kỳ.

## 34. Bảng tra cứu nhanh

| Nhu cầu | Tham số / công cụ |
| --- | --- |
| Bật logging collector | logging_collector |
| Chọn destination | log_destination |
| Chọn thư mục | log_directory |
| Đặt tên file | log_filename |
| Quyền file | log_file_mode |
| Rotate theo thời gian | log_rotation_age |
| Rotate theo kích thước | log_rotation_size |
| Truncate file trùng tên | log_truncate_on_rotation |
| Xem active log paths | current_logfiles |
| Rotate ngay bằng SQL | pg_rotate_logfile() |
| Rotate bằng command | pg_ctl logrotate |
| Gửi syslog | log_destination = syslog |
| Gửi Windows Event Log | log_destination = eventlog |
| Giới hạn statement duration | log_min_duration_statement |
| Log DDL/DML/all | log_statement |
| Log connection events | log_connections / log_disconnections |
| Log checkpoint | log_checkpoints |
| Log lock waits | log_lock_waits |
| Log temp files | log_temp_files |
| Log autovacuum | log_autovacuum_min_duration |
| Giảm parameter logging | log_parameter_max_length* |
| Kiểm tra settings | pg_settings |
| Kiểm tra config errors | pg_file_settings |
| Xem config load time | pg_conf_load_time() |
| Xem systemd logs | journalctl |
| Kiểm tra dung lượng Linux | df / du |
| Theo dõi filesystem | node_exporter |
| Central log shipping | Fluent Bit / Vector / Filebeat |

## 35. Checklist luân chuyển log và bảo vệ dung lượng

1. Chọn destination phù hợp với log platform.
2. Xác nhận logging_collector có bật hay không.
3. Xác định log_directory và filesystem thực tế.
4. Tách log volume khỏi PGDATA/WAL khi phù hợp.
5. Xác nhận owner, group và log_file_mode.
6. Dùng log_filename có timestamp đủ phân giải.
7. Chọn log_rotation_age theo retention/ingestion workflow.
8. Chọn log_rotation_size theo file size tối đa mong muốn.
9. Giữ log_truncate_on_rotation=off trừ khi có policy ghi đè rõ ràng.
10. Xác nhận rotation age/size semantics trên version đang chạy.
11. Kiểm tra current_logfiles sau khi collector start.
12. Kiểm thử pg_rotate_logfile() hoặc pg_ctl logrotate.
13. Không dùng external logrotate để rename collector-owned files tùy tiện.
14. Nếu dùng syslog/journald, cấu hình rotation/retention tại service owner.
15. Đo log rate trong giờ bình thường và peak.
16. Tính capacity theo retention, peak factor và headroom.
17. Theo dõi bytes, inodes, file count và time-to-full.
18. Kiểm tra log shipper backlog và dropped events.
19. Archive/compress file đã đóng.
20. Xác minh archive/checksum trước khi xóa local copy.
21. Cleanup theo age và allowlisted path.
22. Loại trừ active files và files chưa ship.
23. Kiểm soát log_statement và slow query threshold.
24. Review connection, checkpoint, lock, temp file và autovacuum logging.
25. Bảo vệ query text, bind parameters, credentials và personal data.
26. Phân quyền người đọc log và central dashboards.
27. Đồng bộ timezone/clock giữa PostgreSQL và log platform.
28. Alert khi filesystem/inode gần đầy hoặc time-to-full thấp.
29. Alert khi archive/shipper/collector thất bại.
30. Có runbook disk emergency và logging incident.
31. Kiểm thử rotation khi shipper đang tail file.
32. Review retention và storage cost định kỳ.

## 36. Tổng kết

PostgreSQL có thể quản lý log files qua logging_collector với rotation theo thời gian và kích thước. log_rotation_age chia file theo thời gian, log_rotation_size chia file theo dung lượng, còn log_truncate_on_rotation chỉ truncate file trùng tên trong trường hợp time-based rotation. current_logfiles giúp log shipper xác định file đang hoạt động. Nếu dùng syslog, journald hoặc Windows Event Log, chính hệ thống tiếp nhận chịu trách nhiệm rotation và retention.

Rotation không phải retention. Nó không xóa file cũ và không giới hạn tổng dung lượng. Muốn bảo vệ storage, cần đo log rate, tính dung lượng theo retention days và peak factor, giữ headroom, theo dõi bytes/inodes/time-to-full, ship/archive log ra ngoài và cleanup các file đã đóng theo policy. External logrotate không nên rename collector-owned files tùy tiện vì PostgreSQL có thể tiếp tục ghi vào file descriptor cũ.

Tốc độ tăng log cũng phụ thuộc logging verbosity. Hãy chọn slow query thresholds, statement categories, connection/checkpoint/lock/temp/autovacuum logging theo mục tiêu điều tra. Log có thể chứa SQL và parameter values nhạy cảm, nên cần giới hạn quyền, bảo vệ transport và áp dụng retention phù hợp.

Một quy trình vận hành đáng tin cậy kết hợp rotation, retention, compression, archival, capacity alerts và runbooks. Kiểm thử rotation khi log shipper đang hoạt động, xác minh archive trước cleanup và luôn có kế hoạch xử lý khi volume gần đầy. Như vậy log vẫn hữu ích cho điều tra mà không trở thành rủi ro làm cạn dung lượng database host.
