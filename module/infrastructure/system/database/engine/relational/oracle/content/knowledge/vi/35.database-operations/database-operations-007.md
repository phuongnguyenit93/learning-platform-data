# Fast Recovery Area, archived log và áp lực dung lượng trong Oracle

## 1. Vai trò của Fast Recovery Area

**Fast Recovery Area (FRA)** là vùng lưu trữ do Oracle Database quản lý dành cho các file phục vụ backup và recovery. FRA giúp database quản lý tập trung file khôi phục, theo dõi dung lượng, xác định file có thể reclaim và tự động giải phóng file đủ điều kiện khi cần chỗ cho file recovery mới.

Các loại file thường được đặt trong FRA:

- Archived redo log.
- RMAN backup piece và image copy.
- Flashback log.
- Control file autobackup và SPFILE autobackup.
- Datafile copy.
- Một số file recovery khác được Oracle quản lý, bao gồm foreign archived log trong các cấu hình phù hợp.

FRA thường được đặt trên filesystem hoặc Oracle ASM disk group. Ví dụ ASM disk group +RECO hoặc thư mục riêng trên storage được thiết kế cho recovery.

FRA không phải là một bản backup độc lập và không thay thế chiến lược backup ngoài máy chủ. Nếu database, FRA và backup duy nhất cùng nằm trên một storage array hoặc một failure domain, sự cố storage có thể làm mất cả dữ liệu lẫn khả năng phục hồi.

## 2. Hai tham số cấu hình cốt lõi

Oracle dùng hai initialization parameter chính:

| Parameter | Ý nghĩa |
| --- | --- |
| DB_RECOVERY_FILE_DEST | Vị trí FRA, có thể là filesystem hoặc ASM disk group |
| DB_RECOVERY_FILE_DEST_SIZE | Giới hạn dung lượng FRA mà Oracle được phép sử dụng |

Ví dụ:

~~~sql
ALTER SYSTEM SET DB_RECOVERY_FILE_DEST_SIZE = 200G
SCOPE = BOTH;

ALTER SYSTEM SET DB_RECOVERY_FILE_DEST = '+RECO'
SCOPE = BOTH;
~~~

Oracle yêu cầu cấu hình kích thước FRA trước khi cấu hình vị trí FRA. Giá trị 200G chỉ là ví dụ; chọn dung lượng dựa trên workload, retention và dung lượng storage thực tế.

Kiểm tra:

~~~sql
SHOW PARAMETER db_recovery_file_dest;
SHOW PARAMETER db_recovery_file_dest_size;
~~~

Hoặc:

~~~sql
SELECT name,
       value
FROM v$parameter
WHERE name IN (
    'db_recovery_file_dest',
    'db_recovery_file_dest_size',
    'db_flashback_retention_target'
)
ORDER BY name;
~~~

### 2.1. DB_RECOVERY_FILE_DEST_SIZE là quota, không phải dung lượng vật lý

DB_RECOVERY_FILE_DEST_SIZE là giới hạn Oracle dùng để quản lý FRA. Nó không tạo thêm dung lượng trên filesystem hoặc ASM.

Ví dụ:

- ASM disk group còn 500 GB.
- FRA được cấu hình quota 200 GB.
- Oracle quản lý file recovery trong giới hạn FRA 200 GB.

Nếu quota được nâng lên 400 GB nhưng ASM chỉ còn 50 GB thực tế, database vẫn có thể gặp lỗi hết dung lượng ở tầng storage. Tăng tham số không thay thế việc mở rộng disk group hoặc filesystem.

Ngược lại, không nên đặt quota bằng toàn bộ dung lượng vật lý. Cần chừa chỗ cho online redo log, datafile, control file, archive destination khác, workload khác trên cùng disk group và overhead của storage.

### 2.2. Chọn vị trí FRA

Ví dụ dùng filesystem:

~~~sql
ALTER SYSTEM SET DB_RECOVERY_FILE_DEST_SIZE = 200G
SCOPE = BOTH;

ALTER SYSTEM SET DB_RECOVERY_FILE_DEST = '/u03/oracle/fra'
SCOPE = BOTH;
~~~

Ví dụ dùng ASM:

~~~sql
ALTER SYSTEM SET DB_RECOVERY_FILE_DEST_SIZE = 500G
SCOPE = BOTH;

ALTER SYSTEM SET DB_RECOVERY_FILE_DEST = '+RECO'
SCOPE = BOTH;
~~~

Trong RAC, vị trí FRA phải là storage dùng chung và được các instance truy cập theo kiến trúc RAC. Không đặt FRA trên thư mục local chỉ có một node nhìn thấy nếu database cần truy cập file từ các node khác.

### 2.3. Chuyển vị trí FRA

Thay đổi DB_RECOVERY_FILE_DEST không nên được xem như một thao tác di chuyển file đơn giản. File hiện có, RMAN repository, archived log destination, Data Guard và khả năng truy cập của mọi instance đều cần được xem xét.

Trước khi đổi vị trí:

1. Xác định file nào đang nằm trong FRA.
2. Kiểm tra backup/recovery có còn cần các file đó không.
3. Chuẩn bị storage đích và quyền truy cập.
4. Xây dựng kế hoạch chuyển đổi theo tài liệu Oracle cho phiên bản và kiến trúc đang chạy.
5. Xác nhận RMAN, archive destination và Data Guard sau khi chuyển.

Không tự ý copy hoặc xóa file trong FRA bằng lệnh hệ điều hành rồi giả định repository đã được cập nhật.

## 3. FRA liên quan đến ARCHIVELOG như thế nào?

FRA và ARCHIVELOG mode là hai khái niệm khác nhau:

- ARCHIVELOG mode quy định Oracle giữ các bản archived redo log khi online redo log được archive.
- FRA là một vùng lưu trữ có thể chứa archived redo log, cùng các file backup/recovery khác.

Database có thể ở ARCHIVELOG mode nhưng lưu archived log tại một destination khác FRA. Ngược lại, cấu hình FRA không tự chứng minh archived log đang được ghi vào FRA; cần kiểm tra LOG_ARCHIVE_DEST_n.

### 3.1. Kiểm tra chế độ archive

~~~sql
SELECT name,
       log_mode,
       open_mode,
       database_role
FROM v$database;
~~~

Hoặc trong SQL*Plus:

~~~text
ARCHIVE LOG LIST
~~~

Nếu database ở NOARCHIVELOG mode, các online redo log cũ có thể được tái sử dụng sau checkpoint theo quy trình bình thường mà không có archived copy. Điều này hạn chế khả năng point-in-time recovery và các phương án backup online.

### 3.2. Bật ARCHIVELOG mode

Quy trình khái quát trong maintenance window:

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
ALTER DATABASE ARCHIVELOG;
ALTER DATABASE OPEN;
ARCHIVE LOG LIST;
~~~

Thao tác này cần downtime và phải có kế hoạch backup, archive destination, dung lượng và kiểm thử recovery. Không chuyển chế độ archive trên production chỉ để thử một câu lệnh.

### 3.3. Đưa archived log vào FRA

Để dùng FRA làm local archive destination:

~~~sql
ALTER SYSTEM SET LOG_ARCHIVE_DEST_1 =
    'LOCATION=USE_DB_RECOVERY_FILE_DEST'
SCOPE = BOTH;
~~~

USE_DB_RECOVERY_FILE_DEST yêu cầu Oracle sử dụng FRA đã cấu hình. Kiểm tra lại:

~~~sql
SELECT dest_id,
       status,
       target,
       destination,
       error
FROM v$archive_dest
WHERE status <> 'INACTIVE'
ORDER BY dest_id;
~~~

Không thay đổi một LOG_ARCHIVE_DEST_n đang phục vụ Data Guard hoặc destination bắt buộc nếu chưa hiểu cấu hình hiện tại. Một database có thể có nhiều local/remote archive destination với vai trò khác nhau.

### 3.4. Luồng archived redo log

~~~text
Online Redo Log
      |
      | redo log switch / archive
      v
ARCn process
      |
      v
LOG_ARCHIVE_DEST_n
      |
      +---- LOCATION=USE_DB_RECOVERY_FILE_DEST
      |              |
      |              v
      |             FRA
      |
      +---- filesystem / ASM destination khác
      |
      +---- SERVICE=... (remote Data Guard destination)
                     |
                     v
                Standby database

Archived log
      |
      v
RMAN backup / apply at standby / retention policy
      |
      v
Eligible for deletion when all configured requirements are met
~~~

Archived log là một phần của chuỗi recovery. Không xóa chỉ vì file đã cũ hoặc đã được copy sang một thư mục khác.

## 4. Vì sao archived log quan trọng?

Archived redo log lưu redo đã được archive từ online redo log. Chúng được dùng để:

- Recover datafile sau khi restore backup.
- Recover database đến một thời điểm hoặc SCN phù hợp.
- Thực hiện media recovery.
- Gửi redo tới physical standby trong Data Guard.
- Hỗ trợ backup/recovery và một số thao tác bảo trì.

Nếu database chạy ARCHIVELOG mode mà archive destination không thể ghi, Oracle không thể archive online redo log cần thiết. Khi đó redo log không thể được tái sử dụng theo tiến trình bình thường, và database có thể bị ảnh hưởng nghiêm trọng.

### 4.1. Archive log được tạo theo redo thread và sequence

Trong database single-instance, thường có một redo thread. RAC có nhiều redo thread, mỗi instance có thread riêng.

Định danh archived log cần xét ít nhất:

- DBID/database identity.
- RESETLOGS incarnation.
- THREAD#.
- SEQUENCE#.
- SCN range và thời gian.

Không nên chỉ nhìn SEQUENCE# mà bỏ qua THREAD# hoặc RESETLOGS_CHANGE#. Sequence có thể lặp lại giữa các thread hoặc incarnation.

### 4.2. Log switch và archive

Khi online redo log switch, ARCn process archive redo log đã đầy đủ điều kiện. Có thể theo dõi:

~~~sql
SELECT thread#,
       sequence#,
       first_time,
       next_time,
       archived,
       status
FROM v$log
ORDER BY thread#, group#;
~~~

Thông tin archived log:

~~~sql
SELECT thread#,
       sequence#,
       first_time,
       next_time,
       completion_time,
       archived,
       deleted,
       status,
       name
FROM v$archived_log
WHERE completion_time >= SYSDATE - 1
ORDER BY completion_time DESC;
~~~

V$ARCHIVED_LOG có thể có nhiều record cho cùng thread/sequence do nhiều destination, copy hoặc lần đăng ký. Khi phân tích cần xét DEST_ID, NAME, REGISTRAR, STANDBY_DEST và trạng thái phù hợp, không mặc định mỗi sequence chỉ có một row.

### 4.3. Tốc độ tạo archive log

Để ước tính lượng redo/archive phát sinh theo giờ:

~~~sql
SELECT TO_CHAR(completion_time, 'YYYY-MM-DD HH24') AS archive_hour,
       COUNT(*) AS log_count,
       ROUND(SUM(blocks * block_size) / 1024 / 1024, 2) AS size_mb
FROM v$archived_log
WHERE completion_time >= SYSDATE - 2
  AND name IS NOT NULL
GROUP BY TO_CHAR(completion_time, 'YYYY-MM-DD HH24')
ORDER BY archive_hour;
~~~

Một số môi trường có thể có nhiều bản copy cho cùng sequence trong view. Nếu cộng tất cả row, số liệu có thể bị đếm trùng. Với báo cáo chính xác, chọn destination/registrar phù hợp hoặc tổng hợp theo thread, sequence và bản copy được quản lý.

Để xem dung lượng log theo thread/sequence duy nhất, có thể bắt đầu bằng:

~~~sql
SELECT thread#,
       sequence#,
       MAX(blocks * block_size) AS bytes_per_sequence,
       MAX(completion_time) AS completion_time
FROM v$archived_log
WHERE completion_time >= SYSDATE - 2
  AND name IS NOT NULL
GROUP BY thread#, sequence#
ORDER BY completion_time;
~~~

Đây là số liệu ước tính dựa trên các record nhìn thấy trong control file; thời gian giữ record và cấu hình repository ảnh hưởng kết quả.

## 5. FRA quản lý dung lượng như thế nào?

Oracle theo dõi các file trong FRA và phân loại file theo khả năng cần thiết cho recovery. Khi cần thêm chỗ, Oracle có thể reclaim file đủ điều kiện theo chính sách retention và deletion.

Điểm quan trọng:

- File đang cần cho recovery không thể bị xóa tùy tiện.
- Backup còn cần theo retention policy không phải file obsolete.
- Archived log chưa đáp ứng archivelog deletion policy không đủ điều kiện bị xóa theo policy đó.
- Flashback log được giữ để đáp ứng flashback retention hoặc guaranteed restore point có thể chiếm chỗ lâu.
- File được đánh dấu KEEP hoặc có yêu cầu giữ đặc biệt có thể không reclaim được như backup thông thường.

### 5.1. SPACE_USED và SPACE_RECLAIMABLE

V$RECOVERY_FILE_DEST cung cấp các số liệu tổng quan:

| Cột | Ý nghĩa |
| --- | --- |
| NAME | Vị trí FRA |
| SPACE_LIMIT | Giới hạn FRA |
| SPACE_USED | Dung lượng file recovery đang được tính trong FRA |
| SPACE_RECLAIMABLE | Dung lượng Oracle ước tính có thể reclaim |
| NUMBER_OF_FILES | Số file trong FRA |

SPACE_RECLAIMABLE là ước tính theo trạng thái/policy hiện tại, không phải cam kết mọi byte sẽ được giải phóng ngay lập tức. Hãy xem thêm file type, RMAN policy, Data Guard và restore point.

### 5.2. Kiểm tra dung lượng tổng

~~~sql
SELECT name,
       space_limit,
       space_used,
       space_reclaimable,
       number_of_files,
       ROUND(space_used / NULLIF(space_limit, 0) * 100, 2)
           AS pct_used,
       ROUND(space_reclaimable / NULLIF(space_limit, 0) * 100, 2)
           AS pct_reclaimable
FROM v$recovery_file_dest;
~~~

Ví dụ minh họa:

| Chỉ số | Giá trị |
| --- | ---: |
| SPACE_LIMIT | 200 GB |
| SPACE_USED | 185 GB |
| SPACE_RECLAIMABLE | 30 GB |
| PCT_USED | 92.5% |
| PCT_RECLAIMABLE | 15% |

Không cộng SPACE_USED và SPACE_RECLAIMABLE; phần reclaimable là một phần trong lượng đang được sử dụng, không phải một vùng dung lượng cộng thêm.

### 5.3. Kiểm tra theo loại file

~~~sql
SELECT file_type,
       percent_space_used,
       percent_space_reclaimable,
       number_of_files
FROM v$flash_recovery_area_usage
ORDER BY percent_space_used DESC;
~~~

Các nhóm file có thể bao gồm:

- CONTROL FILE.
- REDO LOG.
- ARCHIVED LOG.
- BACKUP PIECE.
- IMAGE COPY.
- FLASHBACK LOG.
- FOREIGN ARCHIVED LOG.

Tên nhóm và số liệu phụ thuộc loại file đang tồn tại. View này giúp xác định loại file nào đang chiếm nhiều dung lượng và phần nào có khả năng reclaim.

### 5.4. Dung lượng FRA khác dung lượng storage

Cần theo dõi đồng thời:

1. Quota FRA (SPACE_LIMIT).
2. Mức dùng FRA (SPACE_USED).
3. Dung lượng có thể reclaim (SPACE_RECLAIMABLE).
4. Dung lượng trống thực tế trên filesystem hoặc ASM.
5. Mức sử dụng của disk group hoặc mount point được chia sẻ với workload khác.

Với ASM:

~~~sql
SELECT name,
       total_mb,
       free_mb,
       usable_file_mb
FROM v$asm_diskgroup_stat;
~~~

View này cần quyền phù hợp và thường được truy vấn trong môi trường có ASM. USABLE_FILE_MB phản ánh dung lượng có thể dùng sau khi xét redundancy của disk group; không chỉ nhìn FREE_MB để kết luận có thể chứa thêm bao nhiêu file.

## 6. Retention policy và archived log deletion policy

Hai policy này thường bị nhầm lẫn.

### 6.1. RMAN retention policy

Retention policy xác định backup nào còn cần thiết để đáp ứng mục tiêu phục hồi.

Hai dạng phổ biến:

- REDUNDANCY n: giữ số lượng backup cần thiết theo mức redundancy đã cấu hình.
- RECOVERY WINDOW OF n DAYS: giữ backup cần thiết để có thể recover về bất kỳ thời điểm nào trong cửa sổ n ngày.

Ví dụ:

~~~text
RMAN> CONFIGURE RETENTION POLICY TO RECOVERY WINDOW OF 7 DAYS;
~~~

Hoặc:

~~~text
RMAN> CONFIGURE RETENTION POLICY TO REDUNDANCY 2;
~~~

Hai policy là hai cách biểu đạt mục tiêu retention khác nhau. Một cấu hình retention policy hiện hành sẽ được áp dụng; không coi hai ví dụ là hai lớp tự động cộng dồn.

### 6.2. REPORT OBSOLETE và DELETE OBSOLETE

Xem backup không còn cần theo retention policy:

~~~text
RMAN> REPORT OBSOLETE;
~~~

Sau khi xác nhận:

~~~text
RMAN> DELETE OBSOLETE;
~~~

DELETE OBSOLETE xóa backup/copy mà RMAN xác định không còn cần theo retention policy. Nó không phải lệnh thay thế cho việc cấu hình archived log deletion policy.

### 6.3. Archived log deletion policy

Archived log deletion policy xác định khi nào archived redo log đủ điều kiện để bị xóa bởi RMAN và các cơ chế quản lý FRA.

Ví dụ chỉ cho phép xóa archived log sau khi đã backup ít nhất một lần lên disk:

~~~text
RMAN> CONFIGURE ARCHIVELOG DELETION POLICY
      TO BACKED UP 1 TIMES TO DEVICE TYPE DISK;
~~~

Nếu backup lên tape/SBT:

~~~text
RMAN> CONFIGURE ARCHIVELOG DELETION POLICY
      TO BACKED UP 1 TIMES TO DEVICE TYPE SBT;
~~~

Chọn device type phải khớp kiến trúc backup thực tế. Không cấu hình policy BACKED UP TO SBT nếu không có quy trình backup archived log tới SBT.

### 6.4. Data Guard và điều kiện applied

Trong môi trường Data Guard, primary có thể cần giữ archived log cho đến khi standby đã nhận hoặc apply log theo yêu cầu vận hành.

Ví dụ cấu hình yêu cầu log được apply trên tất cả standby:

~~~text
RMAN> CONFIGURE ARCHIVELOG DELETION POLICY
      TO APPLIED ON ALL STANDBY;
~~~

Điều kiện thực tế phải phù hợp topology, vai trò database, standby nào bắt buộc phải bảo vệ và chính sách vận hành. Nếu standby lag hoặc mất kết nối, log có thể tiếp tục được giữ và FRA tăng dung lượng.

Không đặt policy APPLIED ON ALL STANDBY theo mẫu nếu có standby tùy chọn, standby tạm ngừng hoặc kiến trúc cascade mà yêu cầu deletion khác. Kiểm tra RMAN documentation và Data Guard design trước khi chọn.

### 6.5. Backup archived log và DELETE INPUT

Một tác vụ phổ biến:

~~~text
RMAN> BACKUP ARCHIVELOG ALL DELETE INPUT;
~~~

RMAN backup archived log rồi xóa input copy đã được backup theo semantics của DELETE INPUT và deletion policy.

Nếu một archived log có nhiều bản copy ở các archive destination:

- DELETE INPUT xóa input copy được backup.
- DELETE ALL INPUT yêu cầu xóa tất cả input copies của archived log đã backup, theo điều kiện và policy áp dụng.

DELETE ALL INPUT có tác động rộng hơn. Chỉ dùng khi đã xác định mọi bản copy không còn cần cho recovery/standby và policy bảo vệ đúng yêu cầu.

### 6.6. Retention policy không đồng nghĩa deletion policy

| Cấu hình | Trả lời câu hỏi |
| --- | --- |
| RMAN retention policy | Backup nào còn cần để đáp ứng recovery window/redundancy? |
| Archivelog deletion policy | Archived log đã đủ điều kiện xóa chưa, ví dụ đã backup hoặc đã apply ở standby? |
| Flashback retention target | Oracle cố gắng duy trì khả năng flashback trong khoảng thời gian nào? |
| Guaranteed restore point | Flashback log cần được giữ để bảo đảm có thể flashback về restore point đó |

Một backup có thể obsolete nhưng archived log liên quan vẫn cần cho standby. Ngược lại, archived log có thể đã backup nhưng backup database vẫn phải được giữ theo retention policy. Phải kiểm tra từng policy theo mục tiêu recovery.

## 7. Các lệnh RMAN thường dùng khi quản lý FRA

### 7.1. Xem cấu hình

~~~text
RMAN> SHOW ALL;
~~~

Chú ý các mục:

- RETENTION POLICY.
- ARCHIVELOG DELETION POLICY.
- CONTROLFILE AUTOBACKUP.
- DEFAULT DEVICE TYPE.
- CHANNEL configuration.
- BACKUP OPTIMIZATION.

### 7.2. Xem backup và archived log

~~~text
RMAN> LIST BACKUP SUMMARY;
RMAN> LIST BACKUP OF ARCHIVELOG ALL;
RMAN> LIST ARCHIVELOG ALL;
~~~

Các lệnh này giúp xác định backup set, archived log và trạng thái repository.

### 7.3. Crosscheck

~~~text
RMAN> CROSSCHECK BACKUP;
RMAN> CROSSCHECK ARCHIVELOG ALL;
~~~

CROSSCHECK đối chiếu record trong RMAN repository với file thực tế có thể truy cập. File không còn tồn tại hoặc không thể tìm thấy có thể được đánh dấu EXPIRED.

CROSSCHECK không xóa file hợp lệ đang chiếm chỗ. Nó cũng không tự động backup file còn thiếu.

### 7.4. Delete expired

~~~text
RMAN> DELETE EXPIRED BACKUP;
RMAN> DELETE EXPIRED ARCHIVELOG ALL;
~~~

DELETE EXPIRED loại bỏ record expired khỏi repository sau khi RMAN đã xác nhận file không còn hiện diện. Lệnh này thường không giải phóng dung lượng cho một file còn tồn tại trên storage, vì file expired là file RMAN không tìm thấy.

### 7.5. Delete obsolete

~~~text
RMAN> REPORT OBSOLETE;
RMAN> DELETE OBSOLETE;
~~~

Chỉ xóa sau khi xem danh sách và xác nhận retention policy đúng với mục tiêu phục hồi.

### 7.6. Backup database và archived log

Ví dụ:

~~~text
RMAN> BACKUP DATABASE PLUS ARCHIVELOG;
~~~

Lệnh này minh họa backup database kèm archived log. Lịch backup thực tế cần được thiết kế theo RPO, RTO, dung lượng, throughput, incremental strategy và nơi lưu bản backup.

Backup archived log định kỳ:

~~~text
RMAN> BACKUP ARCHIVELOG ALL DELETE INPUT;
~~~

Trước khi dùng DELETE INPUT, xác nhận backup hoàn tất, device type đúng, deletion policy đúng và standby đã nhận/apply theo yêu cầu.

### 7.7. Không dùng OS delete để thay RMAN

Không nên xóa file trong FRA bằng rm, del hoặc thao tác file manager. Xóa ngoài RMAN có thể làm control file/RMAN repository vẫn ghi nhận file còn tồn tại, khiến backup/recovery khó kiểm soát và tạo record stale.

Hãy dùng RMAN để quản lý backup và archived log. Nếu một file phải được xử lý bằng công cụ storage do tình huống đặc biệt, cần có quy trình DBA được phê duyệt và đồng bộ metadata/repository theo tài liệu Oracle.

## 8. Flashback log và restore point giữ dung lượng FRA

### 8.1. Flashback Database

Flashback Database dùng flashback log để đưa database về một thời điểm trước đó mà không phải restore toàn bộ datafile rồi apply toàn bộ archived redo log như media recovery truyền thống.

Các thành phần liên quan:

- DB_FLASHBACK_RETENTION_TARGET: mục tiêu retention flashback theo phút.
- Flashback log: lưu thông tin cần cho Flashback Database.
- FRA: nơi Oracle lưu flashback log khi tính năng được cấu hình theo cơ chế FRA.

Kiểm tra:

~~~sql
SHOW PARAMETER db_flashback_retention_target;

SELECT flashback_on,
       log_mode
FROM v$database;
~~~

DB_FLASHBACK_RETENTION_TARGET là mục tiêu, không phải bảo đảm Oracle luôn giữ đủ đúng số phút. Khả năng thực tế phụ thuộc tốc độ tạo flashback log và dung lượng FRA.

### 8.2. Guaranteed restore point

Guaranteed restore point bảo đảm database có thể flashback về restore point đó, miễn là các điều kiện vận hành và file cần thiết còn nguyên. Oracle phải giữ flashback log cần thiết cho guaranteed restore point; vì vậy restore point có thể làm FRA không reclaim được nhiều dung lượng.

Kiểm tra:

~~~sql
SELECT name,
       scn,
       time,
       guarantee_flashback_database,
       storage_size
FROM v$restore_point
ORDER BY time;
~~~

Tìm restore point có:

~~~text
GUARANTEE_FLASHBACK_DATABASE = YES
~~~

Nếu guaranteed restore point được tạo để phục vụ một đợt nâng cấp, migration hoặc thay đổi lớn, cần có người chịu trách nhiệm và thời điểm kết thúc rõ ràng. Khi không còn cần khả năng quay lại, DBA có thể drop restore point theo quy trình đã phê duyệt:

~~~sql
DROP RESTORE POINT before_upgrade;
~~~

Không drop guaranteed restore point chỉ để lấy lại dung lượng khi chưa xác nhận hệ thống đã qua giai đoạn cần rollback.

### 8.3. Kiểm tra flashback log usage

~~~sql
SELECT oldest_flashback_scn,
       oldest_flashback_time,
       retention_target,
       flashback_size,
       estimated_flashback_size
FROM v$flashback_database_log;
~~~

Các cột cho biết tuổi flashback log cũ nhất, mục tiêu retention, dung lượng hiện có và ước tính. Giá trị có thể thay đổi theo workload và trạng thái Flashback Database.

### 8.4. Flashback log và archived log là hai loại file khác nhau

Xóa archived log không giải phóng flashback log. Nếu FLASHBACK LOG chiếm phần lớn FRA, cần điều tra retention target, guaranteed restore point và workload tạo flashback.

Tương tự, giảm DB_FLASHBACK_RETENTION_TARGET không đồng nghĩa flashback log được xóa ngay lập tức; Oracle cần đánh giá khả năng reclaim và yêu cầu restore point.

## 9. Control file autobackup và các file recovery khác

RMAN có thể tự động backup control file và SPFILE sau backup hoặc thay đổi cấu trúc database nếu bật control file autobackup:

~~~text
RMAN> CONFIGURE CONTROLFILE AUTOBACKUP ON;
~~~

Control file autobackup rất quan trọng khi cần phục hồi control file hoặc dựng lại database. Không xóa chỉ vì file nhỏ nhưng đã tồn tại lâu.

Kiểm tra cấu hình:

~~~text
RMAN> SHOW CONTROLFILE AUTOBACKUP;
~~~

FRA có thể chứa backup piece, image copy, control file, SPFILE, flashback log và archived log. Khi tìm nguyên nhân đầy FRA, phải phân loại theo file type trước khi xóa.

## 10. Theo dõi FRA và archive destination

### 10.1. Dashboard FRA

~~~sql
SELECT name,
       ROUND(space_limit / 1024 / 1024 / 1024, 2) AS limit_gb,
       ROUND(space_used / 1024 / 1024 / 1024, 2) AS used_gb,
       ROUND(space_reclaimable / 1024 / 1024 / 1024, 2)
           AS reclaimable_gb,
       ROUND(
           space_used / NULLIF(space_limit, 0) * 100,
           2
       ) AS pct_used,
       number_of_files
FROM v$recovery_file_dest;
~~~

Theo dõi xu hướng theo thời gian quan trọng hơn một lần chụp số liệu. Nếu FRA tăng đều mỗi ngày mà không có file được reclaim, cần tìm policy hoặc workload đang giữ file.

### 10.2. Phân loại file

~~~sql
SELECT file_type,
       ROUND(percent_space_used, 2) AS pct_used,
       ROUND(percent_space_reclaimable, 2) AS pct_reclaimable,
       number_of_files
FROM v$flash_recovery_area_usage
ORDER BY percent_space_used DESC;
~~~

Nếu ARCHIVED LOG chiếm phần lớn, điều tra backup và Data Guard. Nếu FLASHBACK LOG chiếm phần lớn, kiểm tra flashback retention/restore point. Nếu BACKUP PIECE chiếm nhiều, xem RMAN retention và lịch backup.

### 10.3. Kiểm tra archive destination

~~~sql
SELECT dest_id,
       status,
       target,
       destination,
       error
FROM v$archive_dest
WHERE status <> 'INACTIVE'
ORDER BY dest_id;
~~~

ERROR có thể chứa lỗi gần nhất liên quan destination. Kiểm tra cả STATUS, TARGET và DESTINATION; không chỉ nhìn một destination.

### 10.4. Archive destination status

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

Một số cột có thể NULL hoặc không có ý nghĩa với local destination. Với remote standby, so sánh archived và applied sequence theo thread và trạng thái transport/apply.

### 10.5. Data Guard lag

Trên standby, có thể xem:

~~~sql
SELECT name,
       value,
       unit,
       time_computed,
       datum_time
FROM v$dataguard_stats
WHERE name IN ('transport lag', 'apply lag');
~~~

Lag tăng có thể khiến archived log chưa đủ điều kiện xóa theo policy APPLIED ON STANDBY. Điều tra cả network, redo transport, managed recovery process và lỗi apply.

### 10.6. Alert log

Tìm các cảnh báo FRA và archive:

~~~sql
SELECT originating_timestamp,
       message_text
FROM v$diag_alert_ext
WHERE originating_timestamp >= SYSTIMESTAMP - INTERVAL '1' DAY
  AND (
      message_text LIKE '%ORA-198%'
      OR message_text LIKE '%ORA-00257%'
      OR message_text LIKE '%ORA-160%'
  )
ORDER BY originating_timestamp DESC;
~~~

View cần quyền phù hợp. Có thể dùng ADRCI hoặc công cụ quản trị để đọc alert log nếu tài khoản không có quyền truy vấn view.

## 11. Áp lực dung lượng FRA: triệu chứng và nguyên nhân

### 11.1. Các lỗi thường gặp

| Mã lỗi | Ý nghĩa thường gặp |
| --- | --- |
| ORA-19815 | Cảnh báo FRA đã dùng gần/hết giới hạn cấu hình |
| ORA-19809 | Vượt giới hạn dung lượng recovery file destination |
| ORA-19804 | Oracle không reclaim được dung lượng cần thiết từ FRA |
| ORA-00257 | Archiver error; cần xử lý archive destination trước khi database bị ảnh hưởng thêm |
| ORA-16014 | Không thể archive log vì không có destination phù hợp/khả dụng |
| ORA-16038 | Một online redo log không thể được archive |

Thông báo thực tế phụ thuộc trạng thái database, destination, quota FRA và dung lượng storage. Đọc đầy đủ alert log và error stack, không chỉ nhìn mã lỗi đầu tiên.

### 11.2. Nguyên nhân thường gặp

1. RMAN backup thất bại hoặc lịch backup không chạy.
2. Archived log được tạo nhanh hơn tốc độ backup/xóa.
3. Archivelog deletion policy yêu cầu backup nhưng log chưa được backup.
4. Data Guard standby chưa nhận hoặc chưa apply redo.
5. Guaranteed restore point giữ flashback log.
6. Flashback retention target lớn so với dung lượng FRA.
7. Backup retention quá dài hoặc có backup KEEP.
8. Nhiều bản copy archived log cùng nằm trong FRA.
9. FRA quota quá nhỏ so với peak redo và backup overlap.
10. Filesystem/ASM disk group hết chỗ dù quota FRA còn.
11. Archive destination khác bị lỗi, làm archive operation thất bại.
12. Một workload bulk DML tạo redo lớn bất thường.

### 11.3. Vì sao FRA đầy có thể làm database ngừng tiến triển?

Trong ARCHIVELOG mode, Oracle cần archive online redo log trước khi tái sử dụng log đó. Nếu không thể ghi archived log vì destination hết chỗ hoặc lỗi, redo log switch tiếp theo có thể bị chặn. Database có thể phát sinh lỗi archive và các transaction mới bị ảnh hưởng.

Không phải mọi trường hợp FRA đầy đều làm database dừng ngay lập tức. Tác động phụ thuộc log group, archive destination, trạng thái switch và cấu hình mandatory/optional. Nhưng cần xử lý như một sự cố vận hành ưu tiên cao.

## 12. Quy trình xử lý khi FRA tăng nhanh hoặc gần đầy

### Bước 1. Xác định quota và storage thật

~~~sql
SELECT name,
       space_limit,
       space_used,
       space_reclaimable,
       number_of_files
FROM v$recovery_file_dest;
~~~

Đối chiếu dung lượng filesystem/ASM. Xác định vấn đề là quota FRA hay storage vật lý.

### Bước 2. Tìm file type chiếm nhiều dung lượng

~~~sql
SELECT file_type,
       percent_space_used,
       percent_space_reclaimable,
       number_of_files
FROM v$flash_recovery_area_usage
ORDER BY percent_space_used DESC;
~~~

Đừng xóa file trước khi biết nó thuộc nhóm nào và đang được policy nào giữ lại.

### Bước 3. Kiểm tra RMAN configuration và job gần nhất

~~~text
RMAN> SHOW ALL;
RMAN> REPORT OBSOLETE;
RMAN> LIST BACKUP SUMMARY;
RMAN> LIST BACKUP OF ARCHIVELOG ALL;
~~~

Kiểm tra scheduler/backup logs để xác định backup có thất bại, bị treo hoặc không theo kịp tốc độ sinh archived log không.

### Bước 4. Kiểm tra archive destination

~~~sql
SELECT dest_id,
       status,
       target,
       destination,
       error
FROM v$archive_dest
WHERE status <> 'INACTIVE';
~~~

Nếu destination bị lỗi, sửa nguyên nhân storage/network/permission trước khi chỉ tăng quota.

### Bước 5. Kiểm tra Data Guard

Trên primary và standby, kiểm tra transport/apply lag, sequence bị thiếu và managed recovery. Nếu deletion policy chờ APPLIED ON STANDBY, log chưa apply là lý do hợp lệ để Oracle giữ file.

### Bước 6. Kiểm tra guaranteed restore point và flashback

~~~sql
SELECT name,
       time,
       guarantee_flashback_database,
       storage_size
FROM v$restore_point
ORDER BY time;
~~~

Nếu restore point còn phục vụ rollback, phải giữ. Nếu đợt thay đổi đã kết thúc và chủ sở hữu hệ thống xác nhận không cần quay lại, thực hiện drop theo quy trình.

### Bước 7. Reclaim backup obsolete bằng RMAN

~~~text
RMAN> REPORT OBSOLETE;
~~~

Sau khi xác nhận retention policy:

~~~text
RMAN> DELETE OBSOLETE;
~~~

Không bỏ qua bước REPORT. Nếu retention policy sai, DELETE OBSOLETE có thể xóa backup cần thiết cho mục tiêu recovery.

### Bước 8. Backup archived log rồi xóa input đủ điều kiện

Nếu log chưa được backup:

~~~text
RMAN> BACKUP ARCHIVELOG ALL DELETE INPUT;
~~~

Chỉ thực hiện khi backup destination hoạt động, backup hoàn tất và archivelog deletion policy phù hợp. Trong Data Guard, bảo đảm log đã được apply theo yêu cầu.

### Bước 9. Crosscheck khi repository có file stale

~~~text
RMAN> CROSSCHECK BACKUP;
RMAN> CROSSCHECK ARCHIVELOG ALL;
RMAN> DELETE EXPIRED BACKUP;
RMAN> DELETE EXPIRED ARCHIVELOG ALL;
~~~

Đây là thao tác đồng bộ repository với file thực tế. Nó không thay thế backup hay xóa các file hợp lệ đang chiếm dung lượng.

### Bước 10. Tăng FRA quota hoặc mở rộng storage khi cần

Nếu workload và retention hợp lệ nhưng quota nhỏ, và storage còn đủ chỗ:

~~~sql
ALTER SYSTEM SET DB_RECOVERY_FILE_DEST_SIZE = 300G
SCOPE = BOTH;
~~~

Nếu storage vật lý không đủ, cần mở rộng filesystem/ASM theo quy trình hạ tầng trước hoặc đồng thời với thay đổi quota. Không tăng quota vượt khả năng storage.

### Bước 11. Theo dõi sau xử lý

Lặp lại query FRA, file type usage, archive destination và alert log. Xác nhận:

- FRA usage giảm hoặc tăng theo tốc độ dự kiến.
- Archive destination trở lại trạng thái hợp lệ.
- Archived log mới tiếp tục được archive.
- Backup job thành công.
- Standby tiếp tục nhận/apply redo.
- Không có lỗi recovery mới.

## 13. Những hành động nguy hiểm cần tránh

### 13.1. Không xóa archived log bằng hệ điều hành

Không dùng rm hoặc del để xóa file archived log trong FRA. Làm vậy có thể khiến RMAN repository và file thực tế không đồng bộ. Nếu file đã mất ngoài RMAN, cần crosscheck và đánh giá khả năng recovery.

### 13.2. Không xóa mọi archived log chỉ để giải phóng chỗ

Archived log có thể là phần duy nhất giúp recover backup đến thời điểm cần thiết hoặc giúp standby bắt kịp primary. Không chạy lệnh xóa hàng loạt nếu chưa xác nhận backup, retention và Data Guard.

### 13.3. Không dùng DELETE FORCE như biện pháp chữa cháy mặc định

FORCE có thể bỏ qua một số kiểm tra/policy thông thường. Chỉ dùng khi DBA hiểu rõ file, recovery requirement và tác động tới repository. Không đưa FORCE vào cron/job để giữ FRA trống.

### 13.4. Không tắt ARCHIVELOG để né lỗi FRA

Chuyển sang NOARCHIVELOG làm thay đổi khả năng phục hồi. Đây không phải cách xử lý dung lượng thông thường và có thể yêu cầu backup mới sau khi chuyển chế độ.

### 13.5. Không drop guaranteed restore point tùy tiện

Guaranteed restore point có thể là phương án rollback duy nhất cho một thay đổi lớn. Xóa nó trước khi xác nhận hoàn tất có thể loại bỏ khả năng quay lại trạng thái trước đó.

### 13.6. Không giảm retention chỉ vì biểu đồ đang đỏ

Giảm retention có thể làm mất khả năng phục hồi tới thời điểm mà nghiệp vụ yêu cầu. Trước khi thay đổi, đối chiếu RPO, RTO, yêu cầu audit, backup ngoài FRA và khả năng Data Guard.

## 14. Capacity planning cho FRA

FRA cần đủ chỗ cho file recovery trong giai đoạn đỉnh tải và thời gian overlap giữa các backup. Không chỉ lấy dung lượng database nhân một hệ số cố định.

### 14.1. Các thành phần cần ước lượng

1. Archived redo log sinh ra trong khoảng thời gian cao điểm.
2. Thời gian archived log cần giữ trước khi backup/apply và đủ điều kiện xóa.
3. Kích thước full/incremental backup và số bản backup overlap.
4. Flashback log generation theo workload và retention target.
5. Guaranteed restore point đang tồn tại.
6. Image copy/datafile copy và control file/SPFILE autobackup.
7. Dung lượng cần cho thao tác backup đang chạy cùng lúc.
8. Headroom cho batch lớn, index rebuild, bulk load hoặc sự cố standby.

### 14.2. Mô hình ước tính ban đầu

~~~text
FRA capacity
  >= archived redo required during retention/backup lag
   + backup pieces retained in FRA
   + flashback logs retained
   + guaranteed restore point requirement
   + image copies and control-file backups
   + concurrent backup/maintenance overlap
   + operational safety margin
~~~

Các thành phần có thể phụ thuộc lẫn nhau. Ví dụ archived log đã được backup và đủ điều kiện xóa không cần cộng thêm toàn bộ vào thời gian giữ như một bản copy riêng. Hãy mô hình hóa theo lifecycle thực tế thay vì cộng trùng.

### 14.3. Ước tính archived log

Nếu redo/archive trung bình 80 GB/ngày và log có thể phải giữ 2.5 ngày trước khi backup và standby apply hoàn tất:

~~~text
80 GB/day × 2.5 days = 200 GB
~~~

Đây chỉ là lượng archived log dự kiến trong cửa sổ đó. Dùng peak theo ngày/giờ và mùa cao điểm thay vì chỉ dùng trung bình dài hạn.

### 14.4. Ước tính flashback

Flashback log generation phụ thuộc thay đổi dữ liệu, workload và thời gian retention. Dùng số liệu thực tế từ V$FLASHBACK_DATABASE_LOG, FRA usage và monitoring trong các giai đoạn tải cao.

Guaranteed restore point có thể làm lượng flashback log giữ lại tăng đáng kể. Phải tính thời gian tồn tại của restore point vào kế hoạch dung lượng.

### 14.5. Headroom

Không thiết kế FRA chạy sát 100% liên tục. Cần khoảng dự phòng cho:

- Đợt bulk DML.
- Backup full hoặc incremental lớn.
- Standby mất kết nối tạm thời.
- Backup destination bị chậm.
- Thời gian DBA xử lý sự cố.

Ngưỡng cảnh báo nên thấp hơn mức có thể làm archive bị chặn. Tùy hệ thống, có thể cảnh báo theo phần trăm FRA, tốc độ tăng GB/giờ và số giờ còn lại trước khi đầy.

### 14.6. Theo dõi xu hướng

Lưu định kỳ:

- SPACE_LIMIT.
- SPACE_USED.
- SPACE_RECLAIMABLE.
- File type usage.
- Archived log generation per hour/day.
- RMAN backup duration và throughput.
- Data Guard transport/apply lag.
- Flashback log size và restore point age.

Một FRA đang dùng 70% nhưng tăng 10% mỗi giờ nguy hiểm hơn FRA 90% ổn định và có reclaimable space thực sự.

## 15. Ví dụ thiết kế vận hành

Giả sử database OLTP:

- Chạy ARCHIVELOG mode.
- Có primary và physical standby.
- Backup database hằng ngày.
- Backup archived log mỗi giờ.
- Standby cần apply redo trước khi log được xóa.
- Flashback Database được bật với mục tiêu 24 giờ.

Một cấu hình chính sách có thể gồm:

~~~sql
ALTER SYSTEM SET DB_RECOVERY_FILE_DEST_SIZE = 500G
SCOPE = BOTH;

ALTER SYSTEM SET DB_RECOVERY_FILE_DEST = '+RECO'
SCOPE = BOTH;

ALTER SYSTEM SET LOG_ARCHIVE_DEST_1 =
    'LOCATION=USE_DB_RECOVERY_FILE_DEST'
SCOPE = BOTH;

ALTER SYSTEM SET DB_FLASHBACK_RETENTION_TARGET = 1440
SCOPE = BOTH;
~~~

Trong RMAN:

~~~text
RMAN> CONFIGURE RETENTION POLICY TO RECOVERY WINDOW OF 7 DAYS;
RMAN> CONFIGURE ARCHIVELOG DELETION POLICY TO APPLIED ON ALL STANDBY;
RMAN> CONFIGURE CONTROLFILE AUTOBACKUP ON;
~~~

Job backup:

~~~text
RMAN> BACKUP DATABASE PLUS ARCHIVELOG;
RMAN> BACKUP ARCHIVELOG ALL DELETE INPUT;
~~~

Đây là ví dụ để ghép các thành phần, không phải cấu hình áp dụng nguyên xi cho mọi hệ thống. Nếu backup database nằm trong FRA, cần tính cả backup piece vào quota. Nếu có nhiều standby, standby tùy chọn hoặc backup tới SBT, deletion policy cần được thiết kế đúng topology.

## 16. Checklist vận hành FRA và archived log

1. **FRA đã cấu hình đúng chưa?** Kiểm tra DB_RECOVERY_FILE_DEST và DB_RECOVERY_FILE_DEST_SIZE.
2. **Quota có phù hợp storage không?** Đối chiếu filesystem/ASM usable capacity.
3. **Archived log có đi vào FRA không?** Kiểm tra LOG_ARCHIVE_DEST_n và USE_DB_RECOVERY_FILE_DEST.
4. **Database có ARCHIVELOG mode không?** Kiểm tra V$DATABASE.
5. **FRA đang tăng do loại file nào?** Xem V$FLASH_RECOVERY_AREA_USAGE.
6. **Có file reclaimable không?** Xem SPACE_RECLAIMABLE nhưng không coi đây là bảo đảm.
7. **RMAN retention policy có đúng RPO/RTO không?** Kiểm tra SHOW ALL và REPORT OBSOLETE.
8. **Archived log deletion policy có đúng không?** Kiểm tra backup count/device và Data Guard apply requirement.
9. **Backup job có chạy đều không?** Kiểm tra log, duration, throughput và lỗi.
10. **Standby có lag không?** Kiểm tra V$ARCHIVE_DEST_STATUS và V$DATAGUARD_STATS.
11. **Có guaranteed restore point không?** Kiểm tra V$RESTORE_POINT.
12. **Flashback log có chiếm nhiều không?** Kiểm tra V$FLASHBACK_DATABASE_LOG.
13. **Control file autobackup có bật không?** Kiểm tra RMAN SHOW ALL.
14. **Repository có stale record không?** Dùng CROSSCHECK rồi xử lý EXPIRED.
15. **Có backup obsolete không?** REPORT OBSOLETE trước khi DELETE OBSOLETE.
16. **Có archive log đã backup đủ điều kiện xóa không?** Kiểm tra deletion policy trước DELETE INPUT.
17. **Có xóa file ngoài RMAN không?** Tránh thao tác filesystem trực tiếp trên FRA.
18. **Có headroom cho peak workload không?** Theo dõi GB/giờ và giờ còn lại trước khi đầy.
19. **Có backup ngoài failure domain không?** FRA không thay thế off-host/off-site backup.
20. **Đã kiểm tra khả năng restore chưa?** Backup chỉ có giá trị khi quy trình restore/recovery được kiểm thử.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Fast Recovery Area là gì và chứa những loại file nào?

**Câu 2.** DB_RECOVERY_FILE_DEST khác DB_RECOVERY_FILE_DEST_SIZE như thế nào?

**Câu 3.** Vì sao DB_RECOVERY_FILE_DEST_SIZE không phải dung lượng vật lý?

**Câu 4.** FRA có tự động đưa mọi archived log vào đó không?

**Câu 5.** ARCHIVELOG mode khác FRA như thế nào?

**Câu 6.** Vì sao archive destination đầy có thể ảnh hưởng redo log reuse?

**Câu 7.** V$RECOVERY_FILE_DEST cung cấp các chỉ số nào?

**Câu 8.** SPACE_RECLAIMABLE có phải dung lượng chắc chắn được giải phóng ngay không?

**Câu 9.** V$FLASH_RECOVERY_AREA_USAGE dùng để làm gì?

**Câu 10.** RMAN retention policy và archivelog deletion policy khác nhau thế nào?

**Câu 11.** REPORT OBSOLETE có tác dụng gì?

**Câu 12.** CROSSCHECK khác DELETE EXPIRED thế nào?

**Câu 13.** DELETE INPUT khác DELETE ALL INPUT thế nào?

**Câu 14.** Vì sao Data Guard standby lag có thể khiến archived log tích tụ?

**Câu 15.** Guaranteed restore point ảnh hưởng FRA ra sao?

**Câu 16.** DB_FLASHBACK_RETENTION_TARGET có bảo đảm giữ đủ thời gian không?

**Câu 17.** Vì sao không xóa file FRA bằng lệnh hệ điều hành?

**Câu 18.** ORA-19809 và ORA-19804 thường chỉ tình huống gì?

**Câu 19.** Vì sao tăng FRA quota khi ASM đã đầy không giải quyết được vấn đề?

**Câu 20.** Capacity planning FRA cần tính những thành phần nào?

<details>
<summary>Gợi ý đáp án</summary>

1. Vùng Oracle quản lý cho backup/recovery, có thể chứa archived log, backup piece, image copy, flashback log, control file/SPFILE autobackup và file recovery khác.
2. DEST là vị trí; DEST_SIZE là quota.
3. Nó giới hạn mức Oracle quản lý, không tạo thêm filesystem/ASM capacity.
4. Không. Phải cấu hình archive destination dùng FRA, ví dụ LOCATION=USE_DB_RECOVERY_FILE_DEST.
5. ARCHIVELOG là chế độ ghi archived redo; FRA là vùng lưu file recovery.
6. Online redo log cần được archive trước khi tái sử dụng; archive failure có thể chặn log switch/reuse.
7. Name, space limit, used, reclaimable và number of files.
8. Không. Đó là ước tính theo policy/trạng thái hiện tại.
9. Phân loại mức dùng và reclaimable theo file type.
10. Retention policy xác định backup còn cần; deletion policy xác định archived log đã đủ điều kiện xóa chưa.
11. Liệt kê backup/copy obsolete theo retention policy.
12. CROSSCHECK đối chiếu repository với file thực tế; DELETE EXPIRED xóa record đã được xác định là expired.
13. DELETE INPUT xóa input copy được backup; DELETE ALL INPUT xóa mọi input copy của log đã backup theo điều kiện áp dụng.
14. Policy có thể yêu cầu log được apply trước khi xóa; standby chậm khiến log tiếp tục được giữ.
15. Giữ flashback log cần thiết để bảo đảm flashback về restore point, làm giảm khả năng reclaim.
16. Không. Đây là mục tiêu; khả năng thực tế phụ thuộc workload và dung lượng.
17. Repository có thể không đồng bộ với file thật, làm khó backup/recovery.
18. ORA-19809 báo vượt giới hạn recovery destination; ORA-19804 báo không reclaim được dung lượng cần.
19. Vì quota tăng không tạo thêm dung lượng vật lý.
20. Archived redo, backup retention/overlap, flashback, restore point, image copies, control file backup và safety margin.

</details>

## 18. Tài liệu Oracle chính thức

1. [Oracle Database 19c Backup and Recovery User's Guide — Managing the Fast Recovery Area](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/): cấu hình FRA, quản lý dung lượng và file recovery.
2. [Oracle Database 19c Backup and Recovery User's Guide — Configuring the Recovery Area](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/configuring-rman-client-basic.html): các thành phần cấu hình RMAN và recovery area.
3. [Oracle Database 19c Reference — DB_RECOVERY_FILE_DEST](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DB_RECOVERY_FILE_DEST.html): tham số vị trí FRA.
4. [Oracle Database 19c Reference — DB_RECOVERY_FILE_DEST_SIZE](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DB_RECOVERY_FILE_DEST_SIZE.html): giới hạn dung lượng FRA.
5. [Oracle Database 19c Reference — V$RECOVERY_FILE_DEST](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-RECOVERY_FILE_DEST.html): tổng dung lượng FRA.
6. [Oracle Database 19c Reference — V$FLASH_RECOVERY_AREA_USAGE](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-FLASH_RECOVERY_AREA_USAGE.html): dung lượng theo loại file.
7. [Oracle Database 19c Backup and Recovery User's Guide — Archived Redo Log Deletion Policy](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/configuring-rman-client-basic.html): cấu hình retention/deletion policy và quản lý archived log.
8. [Oracle Database 19c Backup and Recovery Reference — BACKUP](https://docs.oracle.com/en/database/oracle/oracle-database/19/rcmrf/BACKUP.html): backup database và archived redo log.
9. [Oracle Database 19c Backup and Recovery Reference — DELETE](https://docs.oracle.com/en/database/oracle/oracle-database/19/rcmrf/DELETE.html): DELETE OBSOLETE, EXPIRED và archived log.
10. [Oracle Database 19c Backup and Recovery User's Guide — Flashback Database](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/using-flasback-database-restore-points.html): flashback log và restore point.
11. [Oracle Database 19c Data Guard Concepts and Administration](https://docs.oracle.com/en/database/oracle/oracle-database/19/sbydb/): redo transport, apply và standby operations.
12. [Oracle Database 19c Reference — V$ARCHIVED_LOG](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-ARCHIVED_LOG.html): thông tin archived redo log.
13. [Oracle Database 19c Reference — V$ARCHIVE_DEST_STATUS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-ARCHIVE_DEST_STATUS.html): trạng thái archive destination.

**Nguyên tắc cần nhớ:** FRA là vùng Oracle quản lý cho file recovery; DB_RECOVERY_FILE_DEST_SIZE là quota chứ không phải dung lượng vật lý. Archived log chỉ nên được xóa khi backup, recovery retention và Data Guard đã đáp ứng yêu cầu. Flashback log và guaranteed restore point cũng có thể giữ dung lượng lâu dài. Khi FRA chịu áp lực, hãy phân loại file, kiểm tra RMAN policy, archive destination, standby lag và restore point trước khi reclaim hoặc tăng quota. Không xóa file FRA bằng hệ điều hành và luôn giữ bản backup trong failure domain độc lập.
