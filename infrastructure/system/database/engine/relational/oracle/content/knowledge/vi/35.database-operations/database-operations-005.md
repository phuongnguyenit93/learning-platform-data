# ARCHIVELOG, NOARCHIVELOG và kế hoạch bảo vệ dữ liệu

Oracle Database ghi nhận thay đổi dữ liệu vào online redo log trước khi các block dữ liệu tương ứng được ghi xuống datafile. Cơ chế redo giúp database phục hồi sau instance failure. Khi database chạy ở chế độ ARCHIVELOG, Oracle lưu các bản sao của online redo log đã đầy vào archived redo log trước khi nhóm redo có thể được tái sử dụng. Các archived redo log cho phép áp dụng lại thay đổi sau một bản backup và phục hồi database tới thời điểm mong muốn trong phạm vi redo còn đầy đủ.

Hai chế độ vận hành chính:

- **ARCHIVELOG:** lưu archived redo log; hỗ trợ media recovery tới thời điểm mới hơn backup, online backup bằng RMAN và các kiến trúc như Data Guard.
- **NOARCHIVELOG:** không lưu archived redo log; khả năng phục hồi sau mất datafile bị giới hạn bởi backup nhất quán gần nhất. Muốn backup database theo cách thông thường, database phải được đóng nhất quán.

Chọn chế độ không chỉ là một tham số kỹ thuật. Nó quyết định RPO/RTO, tần suất backup, dung lượng lưu trữ, quy trình vận hành, khả năng Data Guard và mức độ mất dữ liệu có thể chấp nhận.

## 1. Redo, online redo log và archived redo log

Khi một transaction thay đổi dữ liệu, Oracle tạo redo records mô tả các thay đổi cần thiết để phục hồi. LGWR ghi redo từ redo log buffer xuống online redo log.

Sơ đồ khái quát:

~~~text
Ứng dụng thay đổi dữ liệu
          |
          v
     Redo records
          |
          v
     Redo log buffer
          |
          | LGWR ghi
          v
    Online redo log
          |
          | log switch / log đầy
          v
    Archived redo log
          |
          v
   Backup / off-site storage
~~~

### 1.1 Online redo log

Online redo log là tập các nhóm log (redo log groups) mà Oracle dùng luân phiên để ghi redo. Mỗi group có thể có nhiều member là các bản sao giống nhau của cùng nhóm redo.

- LGWR ghi redo vào group hiện hành.
- Khi group đầy hoặc có log switch, Oracle chuyển sang group khác.
- Group cũ phải đủ điều kiện tái sử dụng sau checkpoint và, ở ARCHIVELOG mode, sau khi đã được archive.

### 1.2 Archived redo log

Archived redo log là bản sao của một online redo log group đã được archive. ARCn hoặc cơ chế archiving tương ứng thực hiện việc ghi bản sao tới archive destination.

Archived redo log thường được nhận diện theo:

- Thread number.
- Sequence number.
- Resetlogs ID/incarnation.
- First change number (SCN).
- Next change number (SCN).

Một database có thể có nhiều thread redo trong RAC. Không được chỉ nhìn sequence number mà bỏ qua thread và incarnation khi quản lý archive log.

### 1.3 Redo log member khác archived redo log

Multiplexing online redo log bằng nhiều member giúp bảo vệ khỏi mất một file redo member. Đây là các bản sao đồng thời của cùng một redo log group.

Archived redo log lại là bản sao lưu trữ của một group đã hoàn tất. Multiplexing redo log không thay thế archive log backup, và archive log backup không thay thế multiplexing online redo log.

## 2. ARCHIVELOG mode

Trong ARCHIVELOG mode, Oracle phải archive redo log group trước khi group đó được tái sử dụng. Archived redo log lưu lại lịch sử redo liên tục để có thể áp dụng vào datafile sau khi restore backup.

### 2.1 Lợi ích

- Có thể backup datafile trong khi database vẫn mở bằng quy trình RMAN phù hợp.
- Có thể phục hồi datafile sau media failure bằng backup cộng archived redo log.
- Có thể phục hồi tới thời điểm trước khi xảy ra lỗi (point-in-time recovery) nếu còn đủ backup và redo.
- Là nền tảng cho physical standby/Data Guard.
- Hỗ trợ chiến lược backup thường xuyên mà không cần dừng database cho mỗi lần backup toàn bộ.

### 2.2 Chi phí và trách nhiệm vận hành

- Archived redo log sinh liên tục và cần dung lượng lưu trữ.
- Phải backup archived redo log và quản lý retention.
- Archive destination đầy có thể ngăn log group tái sử dụng và làm database bị chậm hoặc dừng tiến trình ghi redo.
- Cần giám sát archive lag, destination status, FRA và lỗi ARCn.
- Phải giữ các sequence cần thiết cho recovery/standby.

ARCHIVELOG mode tạo khả năng phục hồi tốt hơn, nhưng đồng thời đòi hỏi quy trình lưu trữ và giám sát nghiêm túc.

## 3. NOARCHIVELOG mode

Trong NOARCHIVELOG mode, Oracle không lưu các online redo log đã hoàn tất thành archived redo log. Online redo log vẫn được sử dụng để ghi redo và phục hồi instance khi sự cố xảy ra, nhưng redo lịch sử không được giữ lại đầy đủ để media recovery sau khi datafile bị mất.

### 3.1 Hệ quả khi mất datafile

Giả sử database được backup nhất quán vào Chủ nhật. Từ Chủ nhật tới thứ Tư có nhiều transaction mới.

- Nếu database chạy ARCHIVELOG và có đầy đủ backup cùng archived redo log, có thể restore backup Chủ nhật rồi apply redo tới thời điểm gần sự cố.
- Nếu database chạy NOARCHIVELOG, sau khi mất datafile, thường chỉ có thể khôi phục về trạng thái backup nhất quán gần nhất. Những thay đổi sau backup có thể bị mất.

### 3.2 Backup trong NOARCHIVELOG

Với RMAN, để tạo backup database nhất quán trong NOARCHIVELOG mode, database phải được đóng sạch và ở trạng thái MOUNT, không mở READ WRITE trong lúc backup database theo cách thông thường.

Quy trình thường là:

1. Dừng ứng dụng và database bằng SHUTDOWN IMMEDIATE.
2. Khởi động database ở MOUNT.
3. Chạy RMAN backup database và control file cần thiết.
4. Mở database lại.

Một bản sao vật lý do OS tạo cũng phải là consistent cold backup, tức toàn bộ file cần thiết được copy sau khi database đã shutdown nhất quán. Không copy tùy tiện một số datafile trong khi database đang mở rồi coi đó là backup hợp lệ.

### 3.3 Khi nào NOARCHIVELOG có thể chấp nhận?

- Database lab có thể tạo lại hoàn toàn.
- Môi trường development/test không chứa dữ liệu quan trọng.
- Database tạm thời, dữ liệu được nạp lại từ nguồn khác.
- Hệ thống nhỏ có RPO cho phép mất mọi thay đổi sau backup và có cửa sổ downtime để backup.

Không nên chọn NOARCHIVELOG cho hệ thống production cần phục hồi tới thời điểm gần sự cố hoặc cần Data Guard.

## 4. So sánh ARCHIVELOG và NOARCHIVELOG

| Tiêu chí | ARCHIVELOG | NOARCHIVELOG |
|---|---|---|
| Archived redo log | Có | Không tạo archive log mới |
| Instance recovery | Có, dùng online redo | Có, dùng online redo |
| Media recovery sau backup | Có thể apply archived redo | Bị giới hạn bởi backup nhất quán |
| Point-in-time recovery | Có thể, nếu đủ backup/redo | Không có chuỗi archived redo để tiến tới thời điểm tùy ý |
| Online RMAN backup | Hỗ trợ quy trình backup khi database mở | Backup database nhất quán thường yêu cầu database đóng và MOUNT |
| Data Guard physical standby | Là yêu cầu nền tảng | Không phù hợp |
| Dung lượng archive | Cần dự trù và giám sát | Không phát sinh archive log mới |
| Vận hành | Phức tạp hơn, cần backup/purge archive | Đơn giản hơn nhưng RPO kém |
| Trường hợp phù hợp | Production và hệ thống cần recover tốt | Lab/dev hoặc dữ liệu có thể tái tạo |

## 5. Kiểm tra chế độ hiện tại

### 5.1 Xem V$DATABASE

~~~sql
SELECT name,
       open_mode,
       log_mode,
       database_role,
       force_logging,
       current_scn
FROM v$database;
~~~

LOG_MODE cho biết ARCHIVELOG hoặc NOARCHIVELOG.

### 5.2 Dùng ARCHIVE LOG LIST

Trong SQL*Plus hoặc SQLcl:

~~~sql
ARCHIVE LOG LIST;
~~~

Lệnh này hiển thị thông tin như:

- Database log mode.
- Automatic archival.
- Archive destination.
- Oldest online log sequence.
- Next log sequence.
- Current log sequence.

ARCHIVE LOG LIST là lệnh của client tool, không phải câu SELECT SQL thông thường.

### 5.3 Kiểm tra redo log group và member

~~~sql
SELECT group#,
       thread#,
       sequence#,
       bytes,
       members,
       archived,
       status
FROM v$log
ORDER BY thread#, group#;
~~~

Xem member:

~~~sql
SELECT group#,
       type,
       member,
       status
FROM v$logfile
ORDER BY group#, member;
~~~

Các trạng thái CURRENT, ACTIVE, INACTIVE và UNUSED có ý nghĩa khác nhau đối với vòng đời redo log. Không xóa hoặc đổi tên redo log member đang được database sử dụng.

## 6. Chuyển từ NOARCHIVELOG sang ARCHIVELOG

Thay đổi log mode cần database ở trạng thái MOUNT, không phải OPEN. Đây là thao tác bảo trì cần kế hoạch downtime.

### 6.1 Quy trình cơ bản trên single instance

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
ALTER DATABASE ARCHIVELOG;
ALTER DATABASE OPEN;
~~~

Sau đó xác nhận:

~~~sql
SELECT log_mode
FROM v$database;
~~~

Và:

~~~sql
ARCHIVE LOG LIST;
~~~

### 6.2 Cấu hình archive destination trước khi chuyển

Trước khi bật ARCHIVELOG, phải xác định nơi lưu archive. Ví dụ dùng Fast Recovery Area (FRA):

~~~sql
ALTER SYSTEM SET DB_RECOVERY_FILE_DEST =
    '/u03/oracle/fra'
    SCOPE = BOTH;

ALTER SYSTEM SET DB_RECOVERY_FILE_DEST_SIZE =
    200G
    SCOPE = BOTH;
~~~

Dung lượng 200G chỉ là ví dụ. Cần tính theo redo generation rate, thời gian backup, retention, Data Guard lag và khoảng thời gian có thể không purge được.

Có thể cấu hình LOG_ARCHIVE_DEST_1 dùng FRA:

~~~sql
ALTER SYSTEM SET LOG_ARCHIVE_DEST_1 =
    'LOCATION=USE_DB_RECOVERY_FILE_DEST'
    SCOPE = BOTH;

ALTER SYSTEM SET LOG_ARCHIVE_DEST_STATE_1 =
    'ENABLE'
    SCOPE = BOTH;
~~~

Nếu dùng filesystem riêng:

~~~sql
ALTER SYSTEM SET LOG_ARCHIVE_DEST_1 =
    'LOCATION=/u04/oracle/arch'
    SCOPE = BOTH;
~~~

Đường dẫn phải tồn tại, được mount ổn định và Oracle software owner có quyền ghi. Với cấu hình production, cần xác nhận tham số có thể thay đổi online hay cần restart trong phiên bản cụ thể.

### 6.3 Backup đầy đủ sau khi chuyển mode

Sau khi bật ARCHIVELOG, nên tạo một full backup mới để thiết lập baseline backup rõ ràng cho chế độ mới:

~~~text
RMAN> BACKUP DATABASE PLUS ARCHIVELOG;
~~~

Kiểm tra backup hoàn tất, archived redo log đã được backup và control file/SPFILE được bảo vệ. Không coi việc ALTER DATABASE ARCHIVELOG thành công là đã có một kế hoạch backup.

## 7. Chuyển từ ARCHIVELOG sang NOARCHIVELOG

Đây là thay đổi làm giảm khả năng phục hồi. Chỉ thực hiện khi đã được phê duyệt và chấp nhận RPO tương ứng.

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
ALTER DATABASE NOARCHIVELOG;
ALTER DATABASE OPEN;
~~~

Kiểm tra:

~~~sql
SELECT log_mode
FROM v$database;
~~~

Sau khi chuyển, tạo consistent backup mới theo quy trình NOARCHIVELOG. Không tiếp tục dựa vào lịch backup online trước đây như thể chế độ phục hồi vẫn giữ nguyên.

## 8. Thay đổi ARCHIVELOG trong RAC

Trong Oracle RAC, mỗi instance có redo thread riêng. Chuyển log mode cần dừng các instance và thực hiện thao tác ở trạng thái database mount theo quy trình RAC của phiên bản.

Quy trình khái quát:

1. Dừng database bằng Clusterware/SRVCTL theo runbook.
2. Đảm bảo không còn instance mở database.
3. Khởi động một instance ở MOUNT.
4. Chuyển ARCHIVELOG hoặc NOARCHIVELOG.
5. Mở database.
6. Khởi động các instance còn lại.
7. Kiểm tra archive destination cho mọi thread.
8. Xác nhận sequence của từng thread được archive.

Không thực hiện ALTER DATABASE ARCHIVELOG khi các instance RAC khác vẫn mở database.

## 9. Cấu hình archive destination

Oracle có thể lưu archived redo log tại nhiều destination. Các tham số thường gặp:

- LOG_ARCHIVE_DEST_n: mô tả destination.
- LOG_ARCHIVE_DEST_STATE_n: ENABLE/DEFER/ALTERNATE tùy cấu hình.
- LOG_ARCHIVE_MIN_SUCCEED_DEST: số destination tối thiểu phải archive thành công trong cấu hình phù hợp.
- LOG_ARCHIVE_FORMAT: định dạng tên file trong các cấu hình filesystem truyền thống; cần lưu ý phiên bản và Oracle Managed Files/FRA.
- DB_RECOVERY_FILE_DEST: vị trí FRA.
- DB_RECOVERY_FILE_DEST_SIZE: giới hạn dung lượng FRA.

Ví dụ local destination:

~~~sql
ALTER SYSTEM SET LOG_ARCHIVE_DEST_1 =
    'LOCATION=/u04/oracle/arch VALID_FOR=(ALL_LOGFILES,ALL_ROLES) DB_UNIQUE_NAME=ORCL'
    SCOPE = BOTH;
~~~

Ví dụ remote service destination trong Data Guard:

~~~sql
ALTER SYSTEM SET LOG_ARCHIVE_DEST_2 =
    'SERVICE=STBY ASYNC VALID_FOR=(ONLINE_LOGFILES,PRIMARY_ROLE) DB_UNIQUE_NAME=STBY'
    SCOPE = BOTH;
~~~

Các thuộc tính VALID_FOR, DB_UNIQUE_NAME, SERVICE, ASYNC/SYNC và cấu hình broker phải phù hợp với Data Guard design. Không copy chuỗi ví dụ nguyên xi vào production.

### 9.1 ENABLE và DEFER

Có thể bật/tạm hoãn một destination bằng:

~~~sql
ALTER SYSTEM SET LOG_ARCHIVE_DEST_STATE_2 = ENABLE SCOPE = BOTH;
~~~

Hoặc:

~~~sql
ALTER SYSTEM SET LOG_ARCHIVE_DEST_STATE_2 = DEFER SCOPE = BOTH;
~~~

DEFER có thể làm ngừng gửi/archive tới destination tương ứng. Nếu destination là standby, phải theo dõi transport lag và bảo đảm có phương án khôi phục sequence bị thiếu.

### 9.2 Nhiều destination không thay thế backup độc lập

Gửi archive tới hai filesystem trên cùng storage array không bảo vệ tốt trước lỗi storage toàn cụm. Một destination local và một bản backup off-site/immutable có mục đích khác nhau.

## 10. Fast Recovery Area (FRA)

Fast Recovery Area là vùng lưu trữ được Oracle quản lý cho các file liên quan recovery. Tùy cấu hình, FRA có thể chứa:

- Archived redo log.
- Flashback log.
- RMAN backup piece.
- Control file autobackup.
- Một số file phục hồi khác.

FRA không phải backup độc lập nếu nó nằm trên cùng hệ thống storage với database. Cần sao chép backup ra storage/domain failure khác.

### 10.1 Cấu hình FRA

~~~sql
ALTER SYSTEM SET DB_RECOVERY_FILE_DEST =
    '/u03/oracle/fra'
    SCOPE = BOTH;

ALTER SYSTEM SET DB_RECOVERY_FILE_DEST_SIZE =
    200G
    SCOPE = BOTH;
~~~

DB_RECOVERY_FILE_DEST_SIZE là giới hạn dung lượng FRA do Oracle quản lý, không nhất thiết bằng dung lượng vật lý còn trống của filesystem.

### 10.2 Theo dõi FRA

~~~sql
SELECT name,
       space_limit,
       space_used,
       space_reclaimable,
       number_of_files
FROM v$recovery_file_dest;
~~~

Tính tỷ lệ sử dụng:

~~~sql
SELECT name,
       ROUND(space_used * 100 / NULLIF(space_limit, 0), 2) AS pct_used,
       ROUND(space_reclaimable * 100 /
             NULLIF(space_limit, 0), 2) AS pct_reclaimable
FROM v$recovery_file_dest;
~~~

SPACE_RECLAIMABLE là phần Oracle ước lượng có thể thu hồi theo quy tắc quản lý file; không phải cam kết mọi byte có thể xóa ngay.

### 10.3 Khi FRA gần đầy

Các triệu chứng có thể gồm:

- Archive destination không ghi thêm được.
- Log switch bị chậm hoặc không hoàn tất.
- Database phát sinh lỗi liên quan không thể archive.
- RMAN backup không thể ghi thêm.
- Flashback log không thể tiếp tục theo yêu cầu.

Không xóa file archive bằng OS để giải phóng dung lượng khi database vẫn quản lý file đó. Dùng RMAN và deletion policy phù hợp.

## 11. Giám sát archive destination

### 11.1 V$ARCHIVE_DEST

~~~sql
SELECT dest_id,
       status,
       binding,
       target,
       destination,
       error
FROM v$archive_dest
WHERE status <> 'INACTIVE'
ORDER BY dest_id;
~~~

### 11.2 V$ARCHIVE_DEST_STATUS

~~~sql
SELECT dest_id,
       status,
       type,
       database_mode,
       recovery_mode,
       destination,
       archived_thread#,
       archived_seq#,
       applied_thread#,
       applied_seq#,
       error
FROM v$archive_dest_status
ORDER BY dest_id;
~~~

Tên cột có thể khác giữa các release. Kiểm tra dictionary view metadata trước khi dùng script monitoring chung.

### 11.3 V$ARCHIVED_LOG

~~~sql
SELECT thread#,
       sequence#,
       first_change#,
       next_change#,
       completion_time,
       archived,
       applied,
       deleted,
       name
FROM v$archived_log
ORDER BY thread#, sequence#;
~~~

V$ARCHIVED_LOG có thể chứa nhiều record cho cùng một thread/sequence vì có nhiều copy/destination hoặc backup/restore history. Không đếm record như thể mỗi record luôn là một archive log duy nhất.

### 11.4 V$LOG_HISTORY

~~~sql
SELECT thread#,
       sequence#,
       first_change#,
       first_time
FROM v$log_history
ORDER BY first_time DESC;
~~~

View này hữu ích để xem lịch sử log switch theo thread trong phạm vi metadata còn lưu.

## 12. Tính tốc độ phát sinh archived redo

Dung lượng archive phụ thuộc workload. Một hệ thống có thể sinh ít redo vào ban đêm nhưng tăng đột biến khi batch import hoặc xử lý giao dịch.

Có thể ước lượng từ archived log:

~~~sql
SELECT TRUNC(completion_time, 'HH24') AS archive_hour,
       thread#,
       COUNT(DISTINCT sequence#) AS log_count
FROM v$archived_log
WHERE completion_time >= SYSDATE - 1
  AND name IS NOT NULL
GROUP BY TRUNC(completion_time, 'HH24'), thread#
ORDER BY archive_hour, thread#;
~~~

Để ước lượng byte, có thể dùng V$ARCHIVED_LOG.BLOCKS và BLOCK_SIZE nếu phiên bản có các cột này:

~~~sql
SELECT TRUNC(completion_time, 'HH24') AS archive_hour,
       thread#,
       SUM(blocks * block_size) AS archived_bytes
FROM v$archived_log
WHERE completion_time >= SYSDATE - 1
  AND name IS NOT NULL
GROUP BY TRUNC(completion_time, 'HH24'), thread#
ORDER BY archive_hour, thread#;
~~~

Các bản ghi có thể đại diện nhiều copy của cùng sequence. Khi tính dung lượng thực tế, cần lọc destination/copy phù hợp hoặc đối chiếu file inventory; không cộng trùng mọi record.

### 12.1 Ước lượng dung lượng

Một cách ước lượng sơ bộ:

~~~text
Required archive capacity
  ≈ peak redo generation per hour
    × hours to retain locally
    + safety margin
~~~

Nếu backup archive mỗi 4 giờ nhưng cần giữ 48 giờ để hỗ trợ standby lag hoặc recovery, capacity phải đủ cho ít nhất khoảng thời gian đó ở mức redo peak hợp lý.

Không chỉ dùng average daily redo. Dùng peak workload, batch window và kịch bản archive backup bị gián đoạn.

## 13. Log switch và archive log

Oracle chuyển redo log group khi log đầy hoặc theo lệnh. Ví dụ:

~~~sql
ALTER SYSTEM SWITCH LOGFILE;
~~~

Lệnh này yêu cầu switch log trong instance/session phù hợp. Trong một số tình huống có thể dùng:

~~~sql
ALTER SYSTEM ARCHIVE LOG CURRENT;
~~~

Lệnh ARCHIVE LOG CURRENT có thể yêu cầu archive current redo log; hành vi liên quan switch và thread phụ thuộc môi trường/phiên bản. Trong RAC, phải hiểu tác động tới các redo thread.

Không chạy log switch liên tục để “ép archive” mà không có lý do. Log switch quá thường xuyên có thể làm tăng overhead và tạo nhiều archive file nhỏ.

### 13.1 Archive process chậm

Nếu ARCn không theo kịp:

- Redo log group có thể chưa được tái sử dụng.
- Database có thể chờ log file switch/archive completion.
- Có thể xuất hiện wait liên quan log switch.

Kiểm tra:

- Archive destination có ghi được không?
- Filesystem/FRA còn dung lượng?
- Network destination/standby có reachable?
- ARCn process và alert log có lỗi?
- Log switch frequency có quá cao?
- Storage throughput có đáp ứng?

## 14. Archive destination đầy có thể ảnh hưởng database

Trong ARCHIVELOG mode, redo log group không thể tái sử dụng cho tới khi archive thành công theo điều kiện destination bắt buộc.

Nếu archive destination đầy:

1. ARCn không thể ghi archived log.
2. Redo log group cũ chưa được archive.
3. Khi các group khác lần lượt đầy, database không còn group đủ điều kiện reuse.
4. Log switch có thể bị chờ hoặc database ngừng ghi redo.

Thông báo lỗi có thể liên quan ORA-00257 (archiver error) hoặc lỗi destination cụ thể.

### 14.1 Xử lý an toàn

- Kiểm tra V$RECOVERY_FILE_DEST.
- Kiểm tra V$ARCHIVE_DEST_STATUS và ERROR.
- Xác nhận storage thực tế và quota.
- Mở rộng dung lượng hoặc khắc phục destination.
- Backup archive log bằng RMAN.
- Xóa archive log chỉ qua RMAN theo deletion policy.
- Xác nhận archive process hoạt động trở lại.

Không xóa file archive đang cần cho standby hoặc recovery bằng thao tác filesystem.

## 15. RMAN và chiến lược backup

RMAN (Recovery Manager) là công cụ Oracle để backup, restore và recover database. RMAN hiểu cấu trúc database và metadata backup, giúp quản lý backup set, image copy, archived redo log và control file.

Một chiến lược backup cần xác định:

- Full/level 0 backup frequency.
- Incremental backup frequency.
- Archived redo log backup frequency.
- Control file và SPFILE backup.
- Retention policy.
- Archive log deletion policy.
- Off-site copy.
- Encryption và access control.
- Restore validation và diễn tập.

### 15.1 Full backup và incremental level 0

RMAN có thể tạo full backup hoặc incremental level 0. Level 0 là nền tảng cho incremental backup chain; nó không giống mọi khía cạnh quản lý với lệnh BACKUP DATABASE thông thường.

Ví dụ:

~~~text
RMAN> BACKUP DATABASE PLUS ARCHIVELOG;
~~~

Hoặc:

~~~text
RMAN> BACKUP INCREMENTAL LEVEL 0 DATABASE PLUS ARCHIVELOG;
~~~

### 15.2 Incremental level 1

~~~text
RMAN> BACKUP INCREMENTAL LEVEL 1 DATABASE PLUS ARCHIVELOG;
~~~

Level 1 có thể là differential hoặc cumulative theo cấu hình/lệnh. Differential level 1 chứa block thay đổi từ level 0 hoặc level 1 gần nhất; cumulative level 1 chứa thay đổi kể từ level 0 gần nhất.

Ví dụ cumulative:

~~~text
RMAN> BACKUP INCREMENTAL LEVEL 1 CUMULATIVE DATABASE;
~~~

Thiết kế chain phải cân bằng thời gian backup, dung lượng lưu trữ và thời gian restore.

### 15.3 Backup archived redo log

~~~text
RMAN> BACKUP ARCHIVELOG ALL;
~~~

Hoặc kết hợp:

~~~text
RMAN> BACKUP DATABASE PLUS ARCHIVELOG;
~~~

Lệnh PLUS ARCHIVELOG thường thực hiện các bước archive current log và backup archived log liên quan để hỗ trợ backup nhất quán. Kiểm tra output RMAN và policy để xác nhận sequence cần thiết đã được backup.

### 15.4 Control file và SPFILE

Nên bật control file autobackup:

~~~text
RMAN> CONFIGURE CONTROLFILE AUTOBACKUP ON;
~~~

Control file chứa metadata quan trọng về database và backup. SPFILE chứa cấu hình instance. Cần bảo vệ cả hai để phục hồi khi mất control file hoặc server.

### 15.5 Backup không chỉ là datafile

Một bộ backup phục hồi được có thể cần:

- Datafile backup/image copy.
- Archived redo log.
- Control file hoặc control file autobackup.
- SPFILE.
- Password file và cấu hình kết nối/cluster phù hợp.
- Keystore/TDE key nếu database có mã hóa.
- RMAN catalog nếu sử dụng recovery catalog.
- Script/runbook và inventory.

Không lưu mọi secret cùng một thư mục backup không kiểm soát.

## 16. Retention policy và archive log deletion policy

RMAN retention policy xác định backup nào cần giữ để đáp ứng recovery window hoặc redundancy.

Ví dụ recovery window:

~~~text
RMAN> CONFIGURE RETENTION POLICY TO RECOVERY WINDOW OF 14 DAYS;
~~~

Ví dụ redundancy:

~~~text
RMAN> CONFIGURE RETENTION POLICY TO REDUNDANCY 2;
~~~

Hai policy diễn đạt mục tiêu khác nhau:

- Recovery window: giữ đủ backup để có thể phục hồi về thời điểm trong khoảng thời gian quy định, theo quy tắc RMAN.
- Redundancy: giữ số bản backup cần thiết theo cấu hình.

### 16.1 Archive log deletion policy

Ví dụ chỉ cho phép xóa archived log sau khi đã backup ít nhất một lần lên disk:

~~~text
RMAN> CONFIGURE ARCHIVELOG DELETION POLICY
     TO BACKED UP 1 TIMES TO DEVICE TYPE DISK;
~~~

Trong Data Guard, có thể cấu hình chính sách chờ log được ship hoặc apply trên standby:

~~~text
RMAN> CONFIGURE ARCHIVELOG DELETION POLICY
     TO APPLIED ON ALL STANDBY;
~~~

Cú pháp và lựa chọn phù hợp phụ thuộc phiên bản, số standby và yêu cầu vận hành. Chính sách APPLIED ON ALL STANDBY có thể khiến archive log được giữ lâu hơn nếu một standby lag hoặc ngừng hoạt động; phải dự trù dung lượng.

### 16.2 BACKUP ARCHIVELOG ... DELETE INPUT

~~~text
RMAN> BACKUP ARCHIVELOG ALL DELETE INPUT;
~~~

RMAN backup archive log rồi xóa input copy theo quy tắc áp dụng. Không dùng lệnh này nếu chưa xác nhận:

- Backup đã hoàn tất.
- Deletion policy phù hợp.
- Standby đã nhận/apply nếu yêu cầu.
- Sequence cần cho recovery vẫn còn bản sao.
- Bản backup có thể đọc/restore.

DELETE INPUT và DELETE ALL INPUT có phạm vi xóa khác nhau đối với các bản copy ở nhiều destination. Đọc kỹ tài liệu RMAN trước khi dùng.

### 16.3 Không xóa archive bằng OS

Nếu xóa file trực tiếp bằng rm/del/PowerShell, repository RMAN và database có thể vẫn nghĩ file tồn tại. Ngược lại, database có thể thiếu archive cần cho recovery hoặc standby.

Hãy dùng RMAN CROSSCHECK, DELETE EXPIRED và DELETE ARCHIVELOG theo quy trình quản lý file. Không chạy DELETE EXPIRED để thay thế backup hoặc xóa file đang cần.

## 17. Backup consistency

Một backup cần đủ nhất quán để restore và recover.

### 17.1 Online backup trong ARCHIVELOG

Trong ARCHIVELOG mode, RMAN hỗ trợ backup khi database mở theo quy trình phù hợp. Archived redo log được dùng để recover datafile backup về trạng thái nhất quán.

Ví dụ:

~~~text
RMAN> BACKUP DATABASE PLUS ARCHIVELOG;
~~~

Không tự copy datafile đang mở bằng OS rồi giả định đó là consistent backup. Nếu dùng user-managed backup, phải tuân theo quy trình BEGIN BACKUP/END BACKUP và backup archived redo log tương ứng; RMAN thường là lựa chọn đơn giản và an toàn hơn.

### 17.2 Offline consistent backup trong NOARCHIVELOG

Trong NOARCHIVELOG, database phải được shutdown sạch, mount và không open khi tạo backup RMAN database nhất quán theo cách thông thường.

Quy trình ví dụ:

~~~text
SQL> SHUTDOWN IMMEDIATE;
SQL> STARTUP MOUNT;

RMAN> BACKUP DATABASE;
RMAN> BACKUP CURRENT CONTROLFILE;
RMAN> BACKUP SPFILE;

SQL> ALTER DATABASE OPEN;
~~~

Tùy cấu hình, RMAN có thể tự backup control file/SPFILE theo autobackup. Cần kiểm tra output và cấu hình, không tạo bản sao dư thừa không kiểm soát.

## 18. Media recovery trong ARCHIVELOG

Media recovery áp dụng redo để đưa datafile đã restore về trạng thái nhất quán.

Kịch bản mất một datafile:

1. Xác định datafile hỏng/mất.
2. Restore datafile từ backup.
3. Apply archived redo log cần thiết.
4. Mở database hoặc đưa tablespace/datafile online theo tình huống.

Ví dụ khái quát:

~~~text
RMAN> RESTORE DATAFILE 7;
RMAN> RECOVER DATAFILE 7;
~~~

Nếu database vẫn mở và các điều kiện cho phép, có thể thực hiện recovery ở cấp datafile/tablespace mà không cần dừng toàn database. Chi tiết phụ thuộc loại failure, tablespace và cấu hình.

### 18.1 Full database restore/recover

~~~text
RMAN> STARTUP MOUNT;
RMAN> RESTORE DATABASE;
RMAN> RECOVER DATABASE;
RMAN> ALTER DATABASE OPEN;
~~~

Đây là khung cho complete recovery với control file và backup phù hợp. Nếu dùng backup control file hoặc incomplete recovery, có thể cần OPEN RESETLOGS theo quy tắc.

### 18.2 Complete recovery và incomplete recovery

- Complete recovery: áp dụng redo đầy đủ tới trạng thái hiện tại hoặc điểm recovery mong muốn mà không bỏ qua redo cần thiết.
- Incomplete recovery: dừng tại một thời điểm/SCN/sequence trước hiện tại, ví dụ trước khi người dùng xóa nhầm dữ liệu.

Incomplete recovery thường cần OPEN RESETLOGS sau khi recovery hoàn tất.

## 19. Point-in-time recovery (PITR)

PITR phục hồi database về một thời điểm trước hiện tại. Nó hữu ích khi:

- Có transaction xóa nhầm dữ liệu.
- Có batch ghi sai hàng loạt.
- Có deploy gây thay đổi dữ liệu không thể đảo ngược.
- Có logical corruption được phát hiện sau đó.

Điều kiện:

- Có backup phù hợp trước thời điểm cần phục hồi.
- Có đầy đủ archived redo log từ backup tới thời điểm đích.
- Có control file/SPFILE và cấu hình cần thiết.
- Có đủ keystore nếu database dùng TDE.

Ví dụ khái quát RMAN:

~~~text
RMAN> RUN {
  SET UNTIL TIME
    "TO_DATE('2026-11-14 10:30:00',
             'YYYY-MM-DD HH24:MI:SS')";
  RESTORE DATABASE;
  RECOVER DATABASE;
}
RMAN> ALTER DATABASE OPEN RESETLOGS;
~~~

Ví dụ chỉ minh họa cú pháp. Thời điểm đích phải được xác định theo timezone và clock của database. Nếu database dùng CDB/PDB hoặc có Data Guard, cần chọn loại PITR và phạm vi phù hợp.

### 19.1 RESETLOGS tạo incarnation mới

Sau incomplete recovery và OPEN RESETLOGS, database bắt đầu một incarnation mới. Backup và archived redo log thuộc incarnation cũ vẫn có thể cần cho các thao tác phục hồi khác, nhưng phải quản lý theo metadata RMAN.

Sau PITR, nên tạo backup mới theo chiến lược đã định để thiết lập recovery baseline cho incarnation hiện tại.

### 19.2 PITR không phải Flashback Database

Flashback Database dùng flashback logs để đưa database về một thời điểm trước đó trong giới hạn retention. PITR dùng backup và redo recovery. Hai cơ chế có thể bổ sung nhưng không thay thế hoàn toàn cho nhau.

Flashback Database cần cấu hình và dung lượng FRA; nó cũng không thay thế backup độc lập.

## 20. Data Guard và ARCHIVELOG

Physical standby/Data Guard dựa vào redo transport và redo apply để duy trì bản sao database. ARCHIVELOG là nền tảng của quy trình này.

Các thành phần:

- Primary database tạo redo.
- Log transport gửi redo tới standby.
- Standby nhận redo qua standby redo log hoặc archived log tùy chế độ.
- Redo Apply áp dụng redo để cập nhật standby.

### 20.1 Standby redo log

Standby redo log (SRL) nhận redo từ primary trong real-time apply hoặc transport. SRL nên được cấu hình đủ group/size theo thread và quy tắc Oracle cho kiến trúc Data Guard.

Không nhầm SRL với archived redo log. SRL là log nhận redo ở standby; archived redo log là log đã được archive để lưu trữ/apply.

### 20.2 Theo dõi archive gap

Trên standby:

~~~sql
SELECT thread#,
       low_sequence#,
       high_sequence#
FROM v$archive_gap;
~~~

Nếu view trả về hàng, có thể có archive gap cần xử lý. Không có hàng không tự chứng minh mọi khía cạnh Data Guard đều khỏe; cần xem transport/apply lag và broker status.

### 20.3 Theo dõi Data Guard lag

~~~sql
SELECT name,
       value,
       unit,
       time_computed,
       datum_time
FROM v$dataguard_stats
WHERE name IN (
    'transport lag',
    'apply lag',
    'apply finish time'
);
~~~

V$DATAGUARD_STATS có ý nghĩa ở database role phù hợp. Kiểm tra thêm V$ARCHIVE_DEST_STATUS, V$MANAGED_STANDBY hoặc view tương ứng của release.

### 20.4 Deletion policy phải tính tới standby

Nếu xóa archive trước khi standby nhận/apply, có thể tạo gap và làm chậm hoặc dừng recovery. Cấu hình RMAN deletion policy phải phản ánh yêu cầu standby.

Không xóa archive log chỉ vì backup local đã thành công nếu chính sách Data Guard yêu cầu standby apply trước.

## 21. RAC và redo thread

Trong RAC, mỗi instance có redo thread riêng. Vì vậy:

- Archive log phải được quản lý cho mọi thread.
- Sequence number có thể trùng giữa các thread.
- Backup/recovery phải giữ đủ archive cho các thread cần thiết.
- Monitoring phải nhóm theo THREAD# và INST_ID khi thích hợp.

Ví dụ:

~~~sql
SELECT thread#,
       sequence#,
       first_time,
       next_time,
       archived
FROM v$log
ORDER BY thread#, sequence#;
~~~

Để xem archived log:

~~~sql
SELECT thread#,
       sequence#,
       completion_time,
       name
FROM v$archived_log
WHERE name IS NOT NULL
ORDER BY thread#, sequence#;
~~~

Một sequence 500 ở thread 1 không phải cùng log với sequence 500 ở thread 2. Khi xử lý gap hoặc backup, luôn giữ thread.

## 22. Force logging và supplemental logging

### 22.1 FORCE LOGGING

FORCE LOGGING yêu cầu database tạo redo cho các thao tác mà nếu không có cấu hình này có thể được thực hiện NOLOGGING trong một số trường hợp.

Kiểm tra:

~~~sql
SELECT force_logging
FROM v$database;
~~~

Bật ở cấp database:

~~~sql
ALTER DATABASE FORCE LOGGING;
~~~

FORCE LOGGING thường được xem xét trong môi trường Data Guard để giảm nguy cơ standby thiếu dữ liệu do thao tác NOLOGGING. Nó có thể làm tăng redo generation và I/O.

### 22.2 Supplemental logging

Supplemental logging bổ sung thông tin redo cần thiết cho một số giải pháp như logical replication/LogMiner/GoldenGate. Nó không giống ARCHIVELOG mode và không thay thế backup.

Kiểm tra:

~~~sql
SELECT supplemental_log_data_min,
       supplemental_log_data_pk,
       supplemental_log_data_ui,
       supplemental_log_data_fk,
       supplemental_log_data_all
FROM v$database;
~~~

Chỉ bật supplemental logging theo yêu cầu replication/audit và tài liệu của sản phẩm liên quan.

## 23. Thiết kế kế hoạch bảo vệ dữ liệu

Một kế hoạch tốt phải bắt đầu từ yêu cầu nghiệp vụ:

- **RPO (Recovery Point Objective):** chấp nhận mất tối đa bao nhiêu dữ liệu theo thời gian?
- **RTO (Recovery Time Objective):** database phải hoạt động trở lại trong bao lâu?
- Retention: cần giữ backup bao lâu?
- Failure domain: cần sống sót trước lỗi file, disk, server, site hay ransomware?
- Data sensitivity: backup có chứa dữ liệu nhạy cảm không?
- Recovery scope: cần phục hồi một datafile, tablespace, database, PDB hay toàn site?

### 23.1 RPO và chế độ log

| Nhu cầu | Hướng thiết kế |
|---|---|
| Chấp nhận mất mọi thay đổi sau backup gần nhất | Có thể xem xét NOARCHIVELOG cho môi trường phù hợp |
| Chấp nhận mất vài giờ dữ liệu | ARCHIVELOG + backup archive theo chu kỳ đáp ứng RPO |
| Cần phục hồi gần thời điểm lỗi | ARCHIVELOG + backup/transport archive liên tục và monitoring |
| Cần site DR | ARCHIVELOG + Data Guard hoặc giải pháp DR tương đương |
| Cần khôi phục nhanh sau thao tác sai | Backup + archived redo; cân nhắc Flashback theo yêu cầu |

RPO thực tế còn phụ thuộc tần suất backup archive, redo transport, archive destination và khả năng restore.

### 23.2 RTO và kiến trúc backup

RTO phụ thuộc:

- Kích thước database.
- Tốc độ đọc backup.
- Số lượng incremental.
- Khả năng song song RMAN.
- Tốc độ apply redo.
- Thời gian khôi phục control file/SPFILE/keystore.
- Thời gian validation và mở ứng dụng.

Chỉ có backup không có nghĩa phục hồi nhanh. Phải đo restore/recover trên dữ liệu có kích thước đại diện.

## 24. Mô hình backup 3-2-1 và bản sao bất biến

Một nguyên tắc thường dùng:

- Có ít nhất 3 bản dữ liệu/backup.
- Lưu trên ít nhất 2 loại media hoặc failure domain.
- Có ít nhất 1 bản off-site.

Với ransomware và xóa nhầm:

- Dùng immutable/object-lock backup nếu chính sách và nền tảng hỗ trợ.
- Tách quyền database admin khỏi quyền xóa backup.
- Không dùng cùng credential cho database và backup repository.
- Có bản offline hoặc air-gapped nếu yêu cầu.
- Kiểm tra backup catalog và inventory.

Đây là nguyên tắc thiết kế, không thay thế RPO/RTO và kiểm thử restore.

## 25. Backup control file, SPFILE và metadata

Control file lưu metadata về datafile, redo log, checkpoint và backup history. SPFILE lưu cấu hình instance.

Trong RMAN:

~~~text
RMAN> CONFIGURE CONTROLFILE AUTOBACKUP ON;
~~~

Backup SPFILE:

~~~text
RMAN> BACKUP SPFILE;
~~~

Backup current control file:

~~~text
RMAN> BACKUP CURRENT CONTROLFILE;
~~~

Nếu control file mất, có thể cần DBID để restore control file autobackup. Hãy lưu DBID, database name, DB_UNIQUE_NAME và thông tin kết nối trong recovery runbook.

### 25.1 Recovery catalog

RMAN recovery catalog là repository riêng lưu metadata backup. Nó có thể hữu ích khi control file record bị mất hoặc cần quản lý nhiều database. Catalog không thay thế backup file và phải được backup/đảm bảo khả dụng riêng.

Nếu không dùng catalog, control file repository có retention và giới hạn record riêng. Bảo đảm control file autobackup được bảo vệ.

## 26. Kiểm tra backup và diễn tập phục hồi

Một backup job thành công chỉ chứng minh lệnh backup hoàn tất theo output. Nó không chứng minh có thể phục hồi database trong RTO.

Các bước kiểm tra:

- Xem RMAN LIST BACKUP.
- CROSSCHECK backup/archive theo repository.
- RESTORE VALIDATE hoặc VALIDATE theo nhu cầu.
- Kiểm tra archived log sequence continuity.
- Restore trên môi trường riêng.
- Recover tới thời điểm mục tiêu.
- Mở database và chạy smoke test.
- Đo thời gian thực tế.

Ví dụ:

~~~text
RMAN> LIST BACKUP SUMMARY;
RMAN> CROSSCHECK BACKUP;
RMAN> CROSSCHECK ARCHIVELOG ALL;
RMAN> RESTORE DATABASE VALIDATE;
~~~

RESTORE VALIDATE kiểm tra khả năng đọc các backup cần thiết theo phạm vi lệnh, nhưng không thay thế một lần restore/recover/open đầy đủ.

### 26.1 Kiểm tra archived log sequence

Theo dõi sequence theo thread và SCN. Một khoảng thiếu archive có thể khiến recovery không tiến qua được mốc cần thiết.

### 26.2 Restore drill

Nên có lịch diễn tập:

- Restore database toàn phần.
- Restore một datafile.
- Point-in-time recovery.
- Restore control file.
- Khôi phục keystore nếu dùng TDE.
- Switchover/failover nếu có Data Guard.

Mỗi bài diễn tập cần ghi thời gian, bước thủ công, lỗi gặp phải và thời gian ứng dụng hoạt động trở lại.

## 27. Ví dụ kế hoạch backup cho production

Ví dụ giả định:

- RPO tối đa 15 phút.
- RTO mục tiêu 2 giờ.
- Database 2 TB.
- Có Data Guard standby.
- Backup full/level 0 hàng tuần và incremental hàng ngày.
- Archived redo log được backup mỗi 15 phút hoặc theo dung lượng/redo rate.

Một lịch minh họa:

| Công việc | Chu kỳ ví dụ | Mục tiêu |
|---|---|---|
| Level 0/full baseline | Hàng tuần | Baseline restore |
| Level 1 incremental | Hàng ngày | Giảm thời gian backup |
| Backup archived log | 15 phút hoặc ngưỡng phù hợp | Giảm mất redo khi backup repository |
| Control file autobackup | Sau thay đổi backup/structural theo RMAN | Bảo vệ metadata |
| Copy off-site/immutable | Theo RPO của backup repository | Chống mất site/ransomware |
| Restore validate | Hàng ngày/tuần tùy policy | Phát hiện backup hỏng |
| Full restore drill | Theo lịch DR | Xác nhận RTO thực tế |

Đây chỉ là ví dụ. Lịch thật phải dựa vào redo generation rate, storage, cửa sổ batch, retention, Data Guard lag và RPO/RTO được business phê duyệt.

## 28. NOARCHIVELOG backup plan cho môi trường có thể tái tạo

Nếu môi trường thật sự chấp nhận NOARCHIVELOG:

1. Xác định cửa sổ downtime.
2. Dừng ứng dụng ghi dữ liệu.
3. Shutdown database bằng SHUTDOWN IMMEDIATE.
4. Khởi động MOUNT.
5. Tạo consistent RMAN backup.
6. Backup control file/SPFILE.
7. Sao chép backup off-host.
8. Mở database.
9. Chỉ khởi động ứng dụng sau khi kiểm tra.
10. Diễn tập restore về backup gần nhất.

Nếu database không thể dừng đủ lâu, NOARCHIVELOG có thể không đáp ứng yêu cầu vận hành.

## 29. Sự cố thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| ORA-00257 archiver error | Archive destination đầy hoặc không ghi được | V$ARCHIVE_DEST_STATUS, FRA, filesystem |
| Log switch chờ | Archive/checkpoint chưa hoàn tất hoặc group không reuse được | V$LOG, V$ARCHIVE_DEST, alert log |
| FRA gần đầy | Archive/backup/flashback giữ dung lượng | V$RECOVERY_FILE_DEST, RMAN retention |
| RMAN không tìm thấy archive | Sequence chưa backup, đã xóa hoặc thiếu metadata | LIST/CROSSCHECK, V$ARCHIVED_LOG |
| Recovery dừng ở sequence | Archive gap hoặc thiếu file | Thread/sequence/SCN và backup |
| Standby lag tăng | Network, transport, apply hoặc archive gap | V$DATAGUARD_STATS, V$ARCHIVE_DEST_STATUS |
| Restore không mở được database | Thiếu redo, control file hoặc backup không nhất quán | RMAN output, alert log, incarnation |
| NOARCHIVELOG không backup khi OPEN | Chế độ yêu cầu consistent closed backup | Shutdown sạch, MOUNT rồi backup |
| Sau PITR phải OPEN RESETLOGS | Incomplete recovery tạo incarnation mới | RMAN catalog/incarnation và backup mới |
| Archive log bị xóa ngoài RMAN | Repository không khớp filesystem | CROSSCHECK và recovery impact assessment |

## 30. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách làm đúng |
|---|---|---|
| Nghĩ ARCHIVELOG tự động là backup | Archive có thể chỉ nằm trên cùng disk và mất cùng database | Backup archive ra failure domain khác |
| Nghĩ online redo và archived redo giống nhau | Mất lịch sử redo cần cho media recovery | Phân biệt redo group, member và archive |
| Dùng NOARCHIVELOG cho production cần PITR | Không thể apply chuỗi archive sau backup | Chọn ARCHIVELOG và thiết kế backup |
| Chuyển mode khi database OPEN | Lệnh yêu cầu trạng thái MOUNT | Shutdown, startup mount, alter mode |
| Không backup sau khi bật ARCHIVELOG | Thiếu baseline backup rõ ràng | Tạo full/level 0 backup sau chuyển đổi |
| Xóa archive bằng OS | Mất sequence cần cho RMAN/standby | Dùng RMAN deletion policy |
| Xóa archive ngay sau backup local | Standby có thể chưa apply | Cấu hình deletion policy cho Data Guard |
| Đặt FRA quá nhỏ | Archive không ghi được, log switch bị ảnh hưởng | Tính redo peak và retention |
| Chỉ đo redo trung bình | Không chịu được batch peak | Dùng peak generation và safety margin |
| Không backup control file/SPFILE | Khó phục hồi cấu hình/metadata | Bật autobackup và lưu runbook |
| Chỉ chạy RESTORE VALIDATE | Chưa chứng minh open/recover thành công | Thực hiện restore drill |
| Không tính key TDE | Restore datafile không giải mã được | Backup/restore keystore cùng database |
| Nhầm sequence giữa RAC threads | Thiếu hoặc xóa nhầm archive | Theo dõi THREAD# + SEQUENCE# |
| Chuyển NOARCHIVELOG nhưng giữ lịch online backup | Backup job có thể không còn hợp lệ | Thiết kế lại quy trình cold backup |
| Coi Flashback thay backup | FRA/flashback log có thể mất cùng storage | Duy trì backup độc lập |

## 31. Bài thực hành tự kiểm tra

Các bài tập chỉ chạy trong database lab hoặc môi trường được DBA phê duyệt.

### Bài 1 — Kiểm tra log mode

Dùng V$DATABASE và ARCHIVE LOG LIST. Ghi nhận LOG_MODE, archive destination và current sequence.

### Bài 2 — Xem redo log groups

Query V$LOG và V$LOGFILE. Xác định group hiện hành, thread, số member và trạng thái.

### Bài 3 — Chuyển sang ARCHIVELOG

Trong lab, shutdown sạch, startup mount, ALTER DATABASE ARCHIVELOG rồi open. Xác nhận mode và tạo backup baseline.

### Bài 4 — Tạo archive log

Thực hiện một số transaction, switch log trong lab, xem V$ARCHIVED_LOG và xác định thread/sequence.

### Bài 5 — Cấu hình FRA

Đặt DB_RECOVERY_FILE_DEST và SIZE trong lab. Query V$RECOVERY_FILE_DEST và theo dõi usage sau backup.

### Bài 6 — Backup database plus archive

Dùng RMAN BACKUP DATABASE PLUS ARCHIVELOG. Đọc output, LIST BACKUP và xác nhận archive log được backup.

### Bài 7 — Incremental backup

Tạo level 0, thay đổi dữ liệu, tạo level 1 differential và cumulative. So sánh dung lượng và restore chain.

### Bài 8 — Deletion policy

Trong lab không có standby, cấu hình backup count policy. Thử BACKUP ARCHIVELOG ALL DELETE INPUT và kiểm tra metadata RMAN.

### Bài 9 — Media recovery

Trong môi trường riêng, mô phỏng mất một datafile, restore và recover bằng archived redo.

### Bài 10 — PITR

Tạo dữ liệu, backup, thực hiện thay đổi sai, rồi phục hồi về thời điểm trước thay đổi. Xác nhận OPEN RESETLOGS và incarnation mới.

### Bài 11 — Stat/monitor archive

Theo dõi V$ARCHIVE_DEST_STATUS, V$RECOVERY_FILE_DEST và V$ARCHIVED_LOG. Mô phỏng destination không khả dụng trong lab.

### Bài 12 — Data Guard/RAC review

Đọc thread/sequence và archive gap trên môi trường có sẵn. Lập checklist đồng bộ archive, standby redo log và deletion policy.

## 32. Checklist bảo vệ dữ liệu

**Chế độ**

- LOG_MODE đã được xác nhận?
- RPO/RTO có yêu cầu ARCHIVELOG?
- Có Data Guard hoặc PITR không?
- NOARCHIVELOG có thật sự chấp nhận mất dữ liệu sau backup?

**Redo/archive**

- Online redo log có multiplexing hợp lý?
- Archive destination có đủ dung lượng và redundancy?
- Tất cả RAC threads được theo dõi?
- Archive log generation peak đã được đo?
- FRA có cảnh báo ngưỡng?

**RMAN**

- Có full/level 0 và incremental phù hợp?
- Archived redo log được backup đủ thường xuyên?
- Control file autobackup và SPFILE được bảo vệ?
- Retention policy và deletion policy rõ?
- Không xóa archive bằng OS?

**DR/recovery**

- Có off-site/immutable copy?
- Có keystore nếu dùng TDE?
- Có DBID và runbook restore?
- Đã restore validate?
- Đã diễn tập restore/recover/open?
- Đã đo RTO thực tế?

**Data Guard/RAC**

- Transport/apply lag được giám sát?
- Standby redo log đã cấu hình?
- Archive gap được xử lý?
- Deletion policy chờ standby theo yêu cầu?
- Key và backup được đồng bộ sau rotation?

## 33. Ghi nhớ

| Khái niệm | Điều cần nhớ |
|---|---|
| Redo | Thông tin thay đổi phục vụ recovery |
| Online redo log | Nhóm log đang được LGWR ghi luân phiên |
| Redo log member | Bản sao của một member trong cùng group |
| Archived redo log | Bản sao redo log group đã hoàn tất |
| ARCHIVELOG | Giữ lịch sử redo, hỗ trợ media recovery/PITR |
| NOARCHIVELOG | Không archive redo mới; media recovery bị giới hạn |
| LOG_MODE | Trạng thái hiện tại trong V$DATABASE |
| ARCHIVE LOG LIST | Xem chế độ và thông tin archive từ SQL*Plus/SQLcl |
| FRA | Vùng Oracle quản lý cho file recovery |
| RMAN | Backup, restore và recover database |
| Level 0 | Baseline cho incremental backup strategy |
| Level 1 | Backup block thay đổi từ baseline/backup trước |
| Retention policy | Quy định backup cần giữ |
| Deletion policy | Quy định khi nào archive log đủ điều kiện xóa |
| CROSSCHECK | Đối chiếu repository với file thực tế |
| Media recovery | Restore backup rồi apply redo |
| PITR | Phục hồi về thời điểm/SCN trước hiện tại |
| RESETLOGS | Mở database sau một số dạng incomplete recovery, tạo incarnation mới |
| Data Guard | Vận chuyển và apply redo sang standby |
| Standby redo log | Nhận redo tại standby |
| FORCE LOGGING | Buộc ghi redo cho các thao tác có thể NOLOGGING trong phạm vi áp dụng |
| RPO | Mức mất dữ liệu tối đa chấp nhận |
| RTO | Thời gian mục tiêu để phục hồi dịch vụ |
| Restore drill | Diễn tập restore/recover thực tế |

ARCHIVELOG giữ lại redo cần thiết để phục hồi database sau backup và là nền tảng cho Data Guard; NOARCHIVELOG chỉ phù hợp khi tổ chức chấp nhận phục hồi về backup nhất quán gần nhất và có cửa sổ downtime. Dù chọn chế độ nào, kế hoạch bảo vệ dữ liệu phải bao gồm backup datafile, control file, SPFILE, archive log nếu có, keystore TDE, bản sao off-site và diễn tập restore. Hãy giám sát archive destination/FRA, quản lý retention bằng RMAN và không xóa archive log trực tiếp ở hệ điều hành. RPO/RTO chỉ được xác nhận khi đã thực hiện restore/recovery drill và đo thời gian thực tế.
