# Sao lưu archived redo log và quan hệ với khả năng phục hồi

Archived redo log là thành phần quan trọng của chiến lược backup và recovery trong Oracle Database. Khi database chạy ở chế độ ARCHIVELOG, Oracle sao chép online redo log đã đầy và được chuyển sang log group khác thành các archived redo log. Các file này lưu lại chuỗi thay đổi database theo redo thread và sequence, cho phép khôi phục datafile backup tới một thời điểm sau khi backup được tạo.

Backup datafile mà thiếu archived redo log cần thiết có thể chỉ khôi phục được database tới một SCN cũ. Ngược lại, giữ archived redo log nhưng không có datafile backup phù hợp cũng không đủ để tái tạo database sau khi storage bị mất. Khả năng phục hồi phụ thuộc vào một chuỗi liên tục gồm backup datafile/control file, archived redo log, online redo log còn cần thiết và metadata backup được bảo vệ.

Bài học tập trung vào cách archived redo log được tạo, sao lưu, giữ lại và sử dụng khi recovery. Nội dung cũng giải thích RMAN BACKUP ARCHIVELOG, BACKUP DATABASE PLUS ARCHIVELOG, deletion policy, Fast Recovery Area, RAC redo threads và Data Guard.

Sau bài học, bạn có thể:

- Phân biệt online redo log và archived redo log.
- Hiểu ARCHIVELOG/NOARCHIVELOG và tác động tới online backup.
- Đọc thread, sequence, SCN và thời gian của archived log.
- Giải thích vì sao backup archived redo log quyết định recovery window.
- Sử dụng RMAN để backup archived logs riêng hoặc cùng database backup.
- Hiểu DELETE INPUT, DELETE ALL INPUT, backup optimization và archived log deletion policy.
- Theo dõi archived log destination, FRA và nguy cơ đầy archive destination.
- Xác định chuỗi log cần thiết để recover datafile/database tới một SCN hoặc thời điểm.
- Hiểu khác biệt recovery complete, incomplete và OPEN RESETLOGS.
- Xử lý archived log trong RAC và Data Guard.
- Kiểm tra backup bằng LIST, CROSSCHECK, VALIDATE và restore rehearsal.
- Xây dựng retention, offsite copy, bảo vệ backup và runbook phục hồi.

> Cú pháp RMAN, deletion policy và các view có thể thay đổi theo Oracle release, cấu hình CDB/PDB, RAC và Data Guard. Ví dụ dùng RMAN/SQL*Plus phổ biến; xác nhận với tài liệu đúng phiên bản trước khi đưa vào production.

## 1. Online redo log và archived redo log

### 1.1. Online redo log

Oracle ghi redo records mô tả các thay đổi database vào redo log buffer trong SGA. LGWR ghi redo buffer xuống online redo log files. Online redo log được tổ chức thành các group; mỗi group có một hoặc nhiều member để multiplex nhằm giảm rủi ro mất log do hỏng một member.

Khi một log group đầy, Oracle thực hiện log switch sang group khác. Log group vừa đầy trở thành inactive khi điều kiện cho phép và có thể được tái sử dụng sau khi các yêu cầu checkpoint/recovery liên quan được đáp ứng.

### 1.2. Archived redo log

Trong ARCHIVELOG mode, trước khi một online redo log group được tái sử dụng, ARCn hoặc cơ chế archival phù hợp sẽ sao chép nội dung redo log đã đầy thành archived redo log. File archive giữ redo records của một khoảng sequence/thread để có thể dùng khi media recovery.

Archived log là bản lưu redo đã hoàn tất của một online log sequence. Nó không phải bản sao datafile và không chứa toàn bộ database image.

### 1.3. Luồng tạo archived log

```text
SESSION thay đổi dữ liệu
       |
       v
REDO LOG BUFFER
       |
       v
LGWR ghi ONLINE REDO LOG
       |
       v
LOG SWITCH
       |
       v
ARCn / ARCHIVAL
       |
       v
ARCHIVED REDO LOG
       |
       +--> Backup bằng RMAN
       +--> Chuyển tới standby (Data Guard)
       +--> Giữ trong FRA / archive destination
       |
       v
RESTORE + RECOVER datafile/database
```

### 1.4. Online redo và archive log có vai trò khác nhau

| Thành phần | Vai trò |
| --- | --- |
| Online redo log | Ghi redo hiện tại để instance recovery và durability |
| Archived redo log | Lưu các redo sequence đã đóng để media recovery, backup và standby |
| Datafile backup | Cung cấp bản dữ liệu nền để restore |
| Control file / recovery catalog | Lưu metadata database, backup và redo history cần thiết cho RMAN |

Không thể thay datafile backup bằng archive log. Cũng không thể thay archive log cần thiết bằng một bản backup datafile cũ nếu mục tiêu recovery nằm sau checkpoint của bản backup đó.

## 2. ARCHIVELOG và NOARCHIVELOG

### 2.1. ARCHIVELOG mode

ARCHIVELOG mode cho phép Oracle lưu archived redo log trước khi online redo log được tái sử dụng. Đây là chế độ thường cần cho production database vì hỗ trợ:

- Online backup datafile/database theo quy trình RMAN.
- Media recovery tới SCN hoặc thời điểm cụ thể.
- Recover datafile bị mất/hỏng tới thời điểm gần nhất có đủ redo.
- Data Guard redo transport và apply.
- Point-in-time recovery trong giới hạn backup và log còn có.

ARCHIVELOG mode không tự tạo backup. Nó chỉ tạo archived redo log; DBA vẫn phải backup và bảo vệ các file đó.

### 2.2. NOARCHIVELOG mode

Trong NOARCHIVELOG mode, online redo log không được archive trước khi tái sử dụng. Khi một log group được tái sử dụng, redo cũ có thể bị ghi đè và không còn chuỗi redo để media recovery từ backup cũ tới thời điểm mới hơn.

Thông thường, database NOARCHIVELOG cần cold/consistent backup khi database đã shutdown sạch. Không thể dựa vào một bản sao datafile online không nhất quán cùng archived redo log để recover như ARCHIVELOG mode.

### 2.3. So sánh

| Khả năng | ARCHIVELOG | NOARCHIVELOG |
| --- | --- | --- |
| Archive online redo khi log switch | Có | Không |
| Online backup theo quy trình RMAN thông thường | Có, kèm redo cần thiết | Không theo cách hot backup nhất quán thông thường |
| Media recovery tới thời điểm sau backup | Có nếu đủ backup và redo | Rất hạn chế |
| Data Guard redo transport | Hỗ trợ cấu hình chuẩn | Không đáp ứng yêu cầu standby redo protection thông thường |
| Chi phí storage/archive management | Cao hơn | Thấp hơn |
| Phù hợp | Production cần khả năng phục hồi | Lab/dev hoặc dữ liệu có thể tạo lại, chấp nhận mất thay đổi sau cold backup |

### 2.4. Kiểm tra log mode

Trong SQL*Plus:

```sql
ARCHIVE LOG LIST
```

Hoặc:

```sql
SELECT name, log_mode, open_mode, database_role
FROM v$database;
```

ARCHIVE LOG LIST hiển thị log mode, archival destination và sequence hiện tại theo góc nhìn instance. V$DATABASE cung cấp LOG_MODE và trạng thái database.

### 2.5. Chuyển sang ARCHIVELOG

Thay đổi log mode cần database ở MOUNT và thường yêu cầu exclusive mount; thực hiện trong maintenance window theo runbook:

```sql
SHUTDOWN IMMEDIATE
STARTUP MOUNT
ALTER DATABASE ARCHIVELOG;
ALTER DATABASE OPEN;
ARCHIVE LOG LIST
```

Đảm bảo archive destination đã được cấu hình và đủ dung lượng trước khi mở database. Trong RAC, cần tuân thủ quy trình chuyển log mode cho toàn database và dừng/mount các instance theo hướng dẫn RAC; không chạy lệnh trên một instance theo cách tùy tiện.

### 2.6. Chuyển về NOARCHIVELOG

Đây là quyết định làm giảm khả năng phục hồi. Chỉ thực hiện nếu yêu cầu nghiệp vụ chấp nhận, có backup cold nhất quán và Data Guard/online backup không còn phụ thuộc:

```sql
SHUTDOWN IMMEDIATE
STARTUP MOUNT
ALTER DATABASE NOARCHIVELOG;
ALTER DATABASE OPEN;
ARCHIVE LOG LIST
```

Không chuyển NOARCHIVELOG để xử lý tạm thời FRA đầy. Hãy xử lý archive destination, backup và deletion policy.

## 3. Redo thread, sequence và SCN

### 3.1. Sequence number

Mỗi lần một redo thread chuyển sang online redo log group khác, sequence number tăng. Archived log được nhận diện chủ yếu bởi DBID/database, thread number và sequence number, cùng resetlogs/incarnation context.

Sequence giúp DBA xác định thứ tự log và tìm khoảng trống trong redo stream. Sequence đơn lẻ không đủ nhận diện archived log trong RAC vì mỗi thread có thể có sequence riêng.

### 3.2. Thread

Trong single instance thường có một redo thread. Trong RAC, mỗi instance thường có thread redo riêng. Archived logs của tất cả thread cần thiết phải có mặt để recovery database RAC nhất quán.

Ví dụ:

| Thread | Sequence | Ý nghĩa |
| ---: | ---: | --- |
| 1 | 120 | Log thứ 120 của thread 1 |
| 2 | 95 | Log thứ 95 của thread 2 |

Không so sánh sequence giữa hai thread như một dãy tăng duy nhất.

### 3.3. SCN

SCN (System Change Number) là logical timestamp Oracle dùng để định vị thứ tự thay đổi database. Archived log có FIRST_CHANGE# và NEXT_CHANGE# để mô tả khoảng SCN được bao phủ.

Để recover tới một target SCN, Oracle cần redo liên tục từ checkpoint của datafile backup tới target. Sequence là đơn vị file; SCN xác định ranh giới logic cần khôi phục.

### 3.4. FIRST_CHANGE# và NEXT_CHANGE#

Trong V$ARCHIVED_LOG:

- FIRST_CHANGE#: SCN đầu tiên của redo trong archived log.
- NEXT_CHANGE#: SCN ngay sau phạm vi redo của log theo metadata.
- FIRST_TIME/NEXT_TIME: mốc thời gian tương ứng theo metadata.

Các log cần có phạm vi SCN liên tục cho thread liên quan. Đừng chỉ kiểm tra sequence min/max; một sequence bị thiếu giữa hai đầu vẫn tạo recovery gap.

### 3.5. RESETLOGS và incarnation

Sau incomplete recovery hoặc một số thao tác mở lại database, OPEN RESETLOGS tạo một incarnation mới và bắt đầu redo branch mới. Archive log từ incarnation cũ và mới có thể có sequence trùng nhau; phải xét RESETLOGS_CHANGE#/RESETLOGS_TIME hoặc RMAN incarnation metadata.

RMAN quản lý incarnation và backup metadata; tránh tự xóa file dựa trên tên/sequence mà không xét incarnation.

## 4. Cấu hình archive destination

### 4.1. LOG_ARCHIVE_DEST_n

LOG_ARCHIVE_DEST_1, LOG_ARCHIVE_DEST_2 và các tham số cùng họ xác định nơi Oracle ghi archived redo log hoặc gửi redo tới destination từ xa. Destination có thể là local filesystem, ASM disk group hoặc remote service tùy cấu hình.

Ví dụ cấu hình local destination:

```sql
ALTER SYSTEM SET LOG_ARCHIVE_DEST_1 =
  'LOCATION=/u02/arch VALID_FOR=(ALL_LOGFILES,ALL_ROLES)'
  SCOPE=BOTH;
```

Đường dẫn chỉ là ví dụ. Thư mục/ASM destination phải tồn tại, có quyền truy cập, đủ dung lượng và được quản lý bởi storage policy.

### 4.2. LOG_ARCHIVE_DEST_STATE_n

Tham số này bật/tắt destination tương ứng. Trước khi thay đổi state, hiểu rõ destination có phục vụ standby, mandatory archival hoặc yêu cầu recovery nào. Disable nhầm destination có thể làm redo transport/archive không hoạt động như mong đợi.

### 4.3. LOG_ARCHIVE_FORMAT

LOG_ARCHIVE_FORMAT quy định tên file archived log trong filesystem destination theo các substitution variable được hỗ trợ. Tên file thường chứa thread, sequence và resetlogs ID để giảm nhầm lẫn.

Khi dùng FRA hoặc ASM, Oracle/RMAN quản lý naming/metadata theo cơ chế riêng. Không tự rename archived log đang được RMAN/Data Guard quản lý.

### 4.4. USE_DB_RECOVERY_FILE_DEST

Có thể chỉ định FRA làm archive destination:

```sql
ALTER SYSTEM SET LOG_ARCHIVE_DEST_1 =
  'LOCATION=USE_DB_RECOVERY_FILE_DEST'
  SCOPE=BOTH;
```

FRA phải được cấu hình bằng DB_RECOVERY_FILE_DEST và DB_RECOVERY_FILE_DEST_SIZE. FRA là vùng quản lý nhiều loại recovery file, không chỉ archived redo log.

### 4.5. Kiểm tra archive destination

```sql
SELECT
    dest_id,
    status,
    target,
    destination,
    error,
    valid_now,
    db_unique_name
FROM v$archive_dest
WHERE status <> 'INACTIVE'
ORDER BY dest_id;
```

V$ARCHIVE_DEST_STATUS cung cấp trạng thái runtime chi tiết hơn cho một số destination. Kiểm tra ERROR, STATUS và các thông tin recovery/transport tương ứng.

## 5. Tạo và theo dõi archived redo log

### 5.1. Log switch

Có thể yêu cầu log switch:

```sql
ALTER SYSTEM SWITCH LOGFILE;
```

Lệnh yêu cầu chuyển sang log group khác; trong ARCHIVELOG mode, log vừa đầy sẽ được archive theo cơ chế Oracle. SWITCH LOGFILE không bảo đảm archive đã hoàn tất tại thời điểm lệnh trả về trong mọi tình huống.

### 5.2. ARCHIVE LOG CURRENT

Lệnh:

```sql
ALTER SYSTEM ARCHIVE LOG CURRENT;
```

yêu cầu archive redo hiện tại tới điểm hiện hành. Lệnh thường được dùng trong backup/recovery runbook để đảm bảo redo mới được archive. Trong RAC, cú pháp/phạm vi có thể liên quan tất cả thread theo release; dùng đúng quy trình cho cluster.

### 5.3. Kiểm tra archived logs

```sql
SELECT
    thread#,
    sequence#,
    first_change#,
    next_change#,
    first_time,
    next_time,
    archived,
    applied,
    deleted,
    status,
    name
FROM v$archived_log
ORDER BY thread#, sequence#, recid;
```

V$ARCHIVED_LOG có thể có nhiều record cho cùng một thread/sequence do nhiều destination/copy hoặc registration. Đừng đếm số row như số sequence duy nhất.

### 5.4. Kiểm tra log history

```sql
SELECT
    thread#,
    sequence#,
    first_time,
    first_change#
FROM v$log_history
ORDER BY thread#, sequence#;
```

V$LOG_HISTORY là lịch sử log switch theo metadata control file; thời gian lưu record phụ thuộc control file record management. Recovery catalog có thể lưu lịch sử lâu hơn khi được đồng bộ.

### 5.5. Kiểm tra online redo group

```sql
SELECT
    thread#,
    group#,
    sequence#,
    bytes,
    members,
    archived,
    status
FROM v$log
ORDER BY thread#, group#;
```

Log group CURRENT chưa phải archived log hoàn chỉnh. Không xóa/di chuyển online redo log để giải phóng archive destination.

## 6. RMAN và backup archived redo log

### 6.1. Vì sao dùng RMAN?

Recovery Manager (RMAN) hiểu cấu trúc database, datafile, control file, redo thread, sequence và incarnation. RMAN ghi metadata backup, biết archived log nào đã được backup và hỗ trợ restore/recover theo SCN hoặc thời gian.

Sao chép file bằng OS có thể tạo thêm một bản copy, nhưng không tự động tạo đầy đủ metadata trong RMAN repository. Nếu cần đưa file copy vào RMAN inventory, phải catalog đúng cách và xác minh file thực sự hợp lệ.

### 6.2. Kết nối RMAN

Ví dụ kết nối target database:

```text
rman target /
```

Hoặc dùng kết nối được bảo vệ theo chính sách DBA. Không ghi password trực tiếp vào command history/script.

### 6.3. Backup toàn bộ archived logs

Lệnh cơ bản:

```sql
BACKUP ARCHIVELOG ALL;
```

RMAN backup archived logs hiện có và ghi backup piece theo device/channel được cấu hình. Nếu backup cần phục vụ recovery, bảo đảm các log cần thiết đã archive và được đưa vào backup set.

### 6.4. Backup kèm format và tag

```sql
BACKUP
  ARCHIVELOG ALL
  FORMAT '/backup/rman/arch_%d_%T_%s_%p.bkp'
  TAG 'ARCHIVE_DAILY';
```

FORMAT là ví dụ đường dẫn disk backup. Trong production, dùng destination có capacity, quyền truy cập, monitoring và bảo vệ độc lập với archive source. TAG giúp nhận diện backup trong LIST/REPORT.

### 6.5. Backup một khoảng sequence

Có thể backup archived log theo sequence/thread khi xử lý gap hoặc yêu cầu cụ thể:

```sql
BACKUP ARCHIVELOG
  FROM SEQUENCE 100
  UNTIL SEQUENCE 120
  THREAD 1;
```

Phải xác nhận sequence/thread tồn tại và thuộc đúng database/incarnation. Với RAC, lặp/điều chỉnh cho từng thread cần thiết.

### 6.6. Backup log chưa được backup đủ số lần

Có thể giới hạn backup optimization theo số lần backup:

```sql
BACKUP ARCHIVELOG ALL
  NOT BACKED UP 1 TIMES;
```

Phạm vi “đã backup” phụ thuộc device type và cấu hình RMAN. Kiểm tra CONFIGURE BACKUP OPTIMIZATION, backup history và yêu cầu bản copy độc lập trước khi dùng trong job.

### 6.7. Backup archived logs lên tape/SBT

Ví dụ:

```sql
BACKUP DEVICE TYPE SBT
  ARCHIVELOG ALL
  TAG 'ARCH_TO_TAPE';
```

SBT cần media management library, channel và cấu hình tape/cloud vendor tương ứng. Lệnh minh họa không thay thế cấu hình vendor. Kiểm tra backup piece được ghi thành công và catalog/metadata được cập nhật.

### 6.8. Backup archived logs theo lịch

Một job thường gồm:

1. Xác nhận archive destination đang hoạt động.
2. Backup archived logs mới phát sinh.
3. Kiểm tra RMAN output và backup piece.
4. Xác nhận bản copy đã ra storage khác/FRA theo policy.
5. Chỉ sau đó mới cho phép xóa input theo deletion policy.
6. Ghi log job, số sequence, dung lượng và lỗi.

Không chạy lệnh xóa archive theo lịch độc lập với backup job mà không kiểm tra backup đã hoàn tất.

## 7. BACKUP DATABASE PLUS ARCHIVELOG

### 7.1. Mục đích

BACKUP DATABASE PLUS ARCHIVELOG kết hợp backup datafile với archived redo log cần thiết để khôi phục backup online. Đây là pattern thông dụng cho database ARCHIVELOG mode.

Ví dụ:

```sql
BACKUP DATABASE PLUS ARCHIVELOG;
```

RMAN điều phối archive log hiện tại và backup archived logs quanh quá trình backup database để có redo cần thiết cho recovery của bản backup online. Cơ chế chi tiết có thể khác theo cấu hình/channel/device.

### 7.2. Vì sao cần archive log quanh thời điểm backup?

Online backup có thể đọc các datafile ở những thời điểm khác nhau. Trong lúc backup, database vẫn có thể thay đổi. Redo ghi nhận thay đổi đó; khi restore, RMAN cần redo liên tục để đưa các datafile backup về trạng thái nhất quán.

Nếu chỉ backup datafile online mà không giữ archived redo log cần thiết, backup có thể không recover được tới trạng thái nhất quán.

### 7.3. Backup database và archive logs riêng

Có thể tách job:

```sql
BACKUP DATABASE;
BACKUP ARCHIVELOG ALL;
```

Nhưng phải thiết kế thứ tự, log switch và thời điểm bao phủ để bảo đảm chuỗi redo cần thiết được backup. PLUS ARCHIVELOG giúp RMAN phối hợp quy trình trong một lệnh rõ ràng.

### 7.4. Backup control file và SPFILE

RMAN có thể tự động backup control file khi backup database/archivelog theo cấu hình autobackup; bật rõ:

```sql
CONFIGURE CONTROLFILE AUTOBACKUP ON;
```

Control file chứa metadata quan trọng về database và backup. Nếu control file mất, autobackup có thể giúp restore control file và catalog backup. SPFILE autobackup cũng quan trọng để khôi phục tham số startup.

### 7.5. Backup incremental

Incremental backup lưu block thay đổi kể từ level/SCN tham chiếu. Archived redo log vẫn cần để recover incremental backup tới target và xử lý thay đổi sau checkpoint. Incremental không thay thế toàn bộ archived redo log cần thiết cho recovery.

Ví dụ:

```sql
BACKUP INCREMENTAL LEVEL 0 DATABASE PLUS ARCHIVELOG;
BACKUP INCREMENTAL LEVEL 1 DATABASE PLUS ARCHIVELOG;
```

Thiết kế level 0/1, cumulative/differential và archived log backup theo retention/recovery objective của tổ chức.

## 8. DELETE INPUT và archived log deletion

### 8.1. DELETE INPUT

Ví dụ:

```sql
BACKUP ARCHIVELOG ALL DELETE INPUT;
```

DELETE INPUT yêu cầu RMAN xóa input archived log được backup thành công sau khi backup hoàn tất, theo phạm vi copy/input mà RMAN xử lý. Nó không phải lệnh “xóa mọi archive log trong mọi destination”.

### 8.2. DELETE ALL INPUT

```sql
BACKUP ARCHIVELOG ALL DELETE ALL INPUT;
```

DELETE ALL INPUT có phạm vi xóa tất cả các bản copy archived log phù hợp với input specification sau khi backup thành công. Cần đặc biệt cẩn thận nếu cùng archived log có nhiều bản copy ở các destination.

### 8.3. Khi nào dùng?

Chỉ dùng DELETE INPUT/DELETE ALL INPUT khi:

- Backup archived log đã hoàn tất và kiểm tra thành công.
- Backup piece nằm trên storage độc lập với source archive.
- Deletion policy cho phép xóa.
- Data Guard standby đã nhận/apply log theo yêu cầu.
- Retention và recovery window vẫn được đáp ứng.

### 8.4. Vì sao không nên xóa thủ công?

Xóa file bằng OS có thể khiến RMAN repository vẫn ghi nhận file AVAILABLE dù file không còn. Recovery catalog/control file metadata và file system bị lệch nhau; sau đó restore/recover có thể thất bại khi cần log.

Sử dụng RMAN DELETE/CROSSCHECK theo quy trình để cập nhật metadata và quản lý file.

### 8.5. Backup optimization

CONFIGURE BACKUP OPTIMIZATION ON có thể giúp RMAN bỏ qua backup của file đã có đủ bản copy theo logic/device type. Điều này hữu ích cho archived log được backup lặp, nhưng phải hiểu device type, số lần backup và trạng thái backup piece.

Không bật backup optimization rồi giả định mọi log luôn có bản copy offsite. Xác nhận policy và kết quả LIST BACKUP.

### 8.6. Deletion policy

RMAN ARCHIVELOG DELETION POLICY quy định điều kiện archived log đủ điều kiện bị xóa. Ví dụ policy có thể yêu cầu log được backup một số lần tới device type nhất định hoặc đã được apply trên standby. Policy này phối hợp với DELETE INPUT, DELETE ARCHIVELOG và FRA reclaim.

Deletion policy không thay retention policy cho toàn bộ database backup; hai chính sách phục vụ mục đích khác nhau.

## 9. Cấu hình archived log deletion policy

### 9.1. Backup-based deletion policy

Ví dụ yêu cầu archive log được backup ít nhất một lần tới disk trước khi xóa:

```sql
CONFIGURE ARCHIVELOG DELETION POLICY
  TO BACKED UP 1 TIMES TO DEVICE TYPE DISK;
```

Nếu backup được ghi sang SBT/tape, chọn device type đúng với chiến lược. Không cấu hình policy chỉ dựa vào lệnh backup đang chạy hôm nay; hãy tính cả recovery requirement và bản copy ngoài site.

### 9.2. Data Guard deletion policy

Trong Data Guard, có thể cấu hình deletion policy để archived logs không bị xóa trước khi được chuyển hoặc apply trên standby theo yêu cầu:

```sql
CONFIGURE ARCHIVELOG DELETION POLICY
  TO APPLIED ON ALL STANDBY;
```

Policy cụ thể tùy số standby, role, transport/apply mode và release. Có lựa chọn liên quan shipped/applied; hiểu rõ điều kiện của từng policy trước khi dùng.

### 9.3. Vì sao cần policy?

Nếu xóa log trước khi standby nhận/apply, standby có thể bị archive gap và không thể tiếp tục apply redo từ chuỗi hiện tại nếu không có bản copy khác. Nếu xóa log trước khi backup, recovery của primary cũng có thể mất đoạn redo cần thiết.

### 9.4. Xem policy hiện tại

Trong RMAN:

```text
SHOW ARCHIVELOG DELETION POLICY;
SHOW ALL;
```

Lưu output cấu hình RMAN trong runbook. Một policy có thể được kế thừa từ cấu hình trước; không giả định database mới có policy mặc định giống database khác.

### 9.5. Thay đổi policy cần đánh giá toàn hệ thống

Trước khi thay policy:

- Xác định tất cả standby và role transition.
- Xác nhận backup device/copy count.
- Kiểm tra archive retention và recovery window.
- Tính dung lượng archive destination/FRA.
- Xác nhận backup job có hoàn tất đúng lịch.
- Kiểm thử deletion trên lab hoặc bằng REPORT/preview phù hợp.

Không tắt policy để giải phóng FRA khi chưa xác định vì sao log chưa đủ điều kiện xóa.

## 10. Fast Recovery Area (FRA)

### 10.1. FRA là gì?

Fast Recovery Area là vùng lưu trữ do Oracle quản lý cho các file phục vụ backup/recovery, có thể bao gồm archived redo log, backup piece, image copy, flashback log và control file/online redo log multiplex copy tùy cấu hình.

FRA giúp quản lý dung lượng và khả năng reclaim file theo retention/deletion policy. FRA không thay thế backup ngoài site hoặc bản copy chống ransomware.

### 10.2. Tham số FRA

| Tham số | Vai trò |
| --- | --- |
| DB_RECOVERY_FILE_DEST | Vị trí FRA |
| DB_RECOVERY_FILE_DEST_SIZE | Giới hạn dung lượng FRA |

Kiểm tra:

```sql
SHOW PARAMETER db_recovery_file_dest
SHOW PARAMETER db_recovery_file_dest_size
```

### 10.3. Theo dõi FRA

```sql
SELECT
    name,
    space_limit,
    space_used,
    space_reclaimable,
    number_of_files
FROM v$recovery_file_dest;

SELECT
    file_type,
    percent_space_used,
    percent_space_reclaimable,
    number_of_files
FROM v$flash_recovery_area_usage;
```

Tên view/cột có thể thay đổi theo release; V$RECOVERY_FILE_DEST là nguồn tổng quan. Đối chiếu dung lượng thật của ASM/filesystem.

### 10.4. FRA đầy

Khi FRA hết dung lượng, Oracle có thể không lưu thêm recovery file và việc archival có thể bị ảnh hưởng. Lỗi thường gặp gồm ORA-19809 và ORA-19804. Nếu archive destination đầy và không thể archive redo, database có thể bị đình trệ khi cần log switch.

### 10.5. Xử lý FRA đầy

1. Kiểm tra space_limit, space_used và reclaimable.
2. Kiểm tra archived logs chưa backup hoặc chưa apply standby.
3. Kiểm tra backup job lỗi hoặc bị chậm.
4. Kiểm tra retention/deletion policy.
5. Backup archive logs sang storage đủ dung lượng.
6. Dùng RMAN để xóa file đủ điều kiện theo policy.
7. Tăng FRA size hoặc thêm storage nếu host/ASM có capacity.

Không xóa file thủ công trong FRA để “làm trống nhanh”. Điều đó có thể phá metadata và recovery chain.

### 10.6. Tăng DB_RECOVERY_FILE_DEST_SIZE

Có thể tăng quota FRA nếu storage có dung lượng thực:

```sql
ALTER SYSTEM SET DB_RECOVERY_FILE_DEST_SIZE = 200G
  SCOPE=BOTH;
```

Giá trị chỉ minh họa. DB_RECOVERY_FILE_DEST_SIZE là quota quản lý, không tự tạo thêm dung lượng vật lý. Xác nhận filesystem/ASM capacity và các workload khác trước khi tăng.

## 11. Retention policy và archived log deletion policy

### 11.1. Hai policy khác nhau

RMAN retention policy xác định backup nào còn cần thiết để đáp ứng recovery window hoặc redundancy. Archived log deletion policy xác định khi nào archived redo log đủ điều kiện bị xóa khỏi archive destination/FRA.

Không đồng nhất hai policy:

| Policy | Trả lời câu hỏi |
| --- | --- |
| Backup retention policy | Backup nào còn cần để khôi phục theo mục tiêu đã đặt? |
| Archived log deletion policy | Archived log nào đã đủ điều kiện xóa theo backup/standby requirement? |

### 11.2. Recovery window

Ví dụ cấu hình retention policy:

```sql
CONFIGURE RETENTION POLICY
  TO RECOVERY WINDOW OF 7 DAYS;
```

Recovery window 7 ngày yêu cầu RMAN giữ đủ backup cần thiết để có thể khôi phục database tới bất kỳ thời điểm nào trong khoảng window đó, dựa trên backup và redo còn khả dụng. Không có nghĩa mọi archived log cũ hơn 7 ngày tự động bị xóa ngay.

### 11.3. Redundancy

Có thể cấu hình số bản backup:

```sql
CONFIGURE RETENTION POLICY TO REDUNDANCY 2;
```

Redundancy 2 giữ số bản backup cần thiết theo logic RMAN. Đây không phải số bản copy archived log độc lập ngoài site và không thay thế yêu cầu Data Guard.

### 11.4. REPORT OBSOLETE và DELETE OBSOLETE

Trước khi xóa backup obsolete, xem báo cáo:

```sql
REPORT OBSOLETE;
```

Sau khi xác minh retention policy, có thể dùng:

```sql
DELETE OBSOLETE;
```

DELETE OBSOLETE áp dụng với backup được RMAN đánh giá không còn cần theo retention policy. Không dùng nó như lệnh dọn mọi archived log chưa backup; archived log deletion policy và file status vẫn cần được hiểu.

### 11.5. Backup archived log không có nghĩa có thể xóa ngay

Một archived log có thể đã được backup một lần nhưng vẫn cần cho:

- Recovery window hiện tại.
- Data Guard standby chưa apply.
- Restore database backup cũ hơn.
- Point-in-time recovery hoặc clone/duplicate.
- Một bản copy backup ngoài site chưa được xác nhận.

Chỉ backup success không phải điều kiện duy nhất để xóa. Deletion policy phải phản ánh yêu cầu recovery thực tế.

### 11.6. REPORT NEED BACKUP

RMAN có thể báo database/datafile cần backup theo recovery window:

```sql
REPORT NEED BACKUP RECOVERY WINDOW OF 7 DAYS DATABASE;
```

Kết quả giúp nhận diện datafile không có backup đủ mới cho window. Nó không thay thế restore test hoặc xác nhận archived log chain.

## 12. Metadata backup và bảo vệ recovery catalog

### 12.1. Control file repository

Nếu không dùng recovery catalog riêng, RMAN lưu metadata backup trong control file. Control file có dung lượng record hữu hạn; metadata cũ có thể bị tái sử dụng theo cơ chế record management.

CONTROL_FILE_RECORD_KEEP_TIME ảnh hưởng thời gian giữ record có thể tái sử dụng, nhưng không thay thế backup control file và không bảo đảm mọi metadata được giữ vô hạn.

### 12.2. Recovery catalog

Recovery catalog là schema repository riêng lưu metadata RMAN lâu dài và hỗ trợ quản lý nhiều target database. Với môi trường lớn, catalog có thể giúp lưu lịch sử backup lâu hơn control file.

Recovery catalog cũng cần được backup và bảo vệ. Mất catalog không nhất thiết làm mất backup piece, nhưng có thể làm việc tìm kiếm/restore metadata khó hơn; control file autobackup và catalog resync strategy rất quan trọng.

### 12.3. Control file autobackup

Nên cấu hình:

```sql
CONFIGURE CONTROLFILE AUTOBACKUP ON;
```

RMAN có thể tự tạo autobackup control file (và SPFILE khi dùng SPFILE) sau các thao tác backup phù hợp. Đặt format rõ nếu cần lưu ở vị trí độc lập:

```sql
CONFIGURE CONTROLFILE AUTOBACKUP FORMAT
  FOR DEVICE TYPE DISK TO '/backup/rman/cf_%F';
```

Đường dẫn là ví dụ. Đảm bảo format/đường dẫn phù hợp device type và runbook restore control file khi database chưa mount.

### 12.4. Backup metadata và cataloging

Khi backup piece được copy bằng storage replication hoặc OS, RMAN có thể không biết vị trí mới. Sau khi copy, catalog file vào repository theo đúng database/incarnation:

```sql
CATALOG START WITH '/backup/received/';
```

CATALOG chỉ đăng ký file có định dạng backup mà RMAN nhận diện; nó không xác minh toàn bộ nội dung có thể restore. Thực hiện validation riêng.

### 12.5. Bảo vệ DBID và thông tin backup

Khi control file mất hoàn toàn, DBID và autobackup format/location có thể cần để restore control file. Lưu DBID, DB_NAME, DB_UNIQUE_NAME, incarnation và hướng dẫn restore ngoài database host, theo policy bảo mật.

## 13. Chuỗi archived redo cần cho recovery

### 13.1. Backup datafile có checkpoint SCN

Mỗi datafile backup có checkpoint SCN/metadata chỉ ra trạng thái datafile được backup. Để khôi phục tới target SCN mới hơn, Oracle cần redo liên tục từ checkpoint cần thiết tới target.

Ví dụ:

```text
Datafile backup checkpoint SCN: 1000
Archived log A: SCN 1000 - 1100
Archived log B: SCN 1100 - 1200
Archived log C: SCN 1200 - 1300
Target recovery SCN: 1250

=> Cần redo liên tục bao phủ từ checkpoint tới SCN 1250.
```

Đây là ví dụ khái niệm; recovery thực tế xét checkpoint của từng datafile, redo thread và database metadata.

### 13.2. Liên tục quan trọng hơn số lượng file

Có 100 archived log không có nghĩa recovery chain đầy đủ. Nếu thiếu một sequence bắt buộc giữa hai log, recovery có thể dừng tại gap. Một bản copy khác của sequence bị thiếu có thể khôi phục khả năng tiếp tục.

### 13.3. Các thread trong RAC

Với RAC, mỗi thread ghi redo riêng. Recovery database cần redo từ tất cả thread có thay đổi liên quan trong khoảng SCN cần thiết. Một thread có sequence gap có thể chặn recovery dù thread khác có đủ log.

### 13.4. Incarnation

Sau OPEN RESETLOGS, database tạo redo branch mới. Recovery target ở incarnation mới thường không dùng sequence chỉ dựa vào tên file của incarnation cũ. RMAN quản lý incarnation metadata và chọn log phù hợp.

### 13.5. Online redo log còn hiện hữu

Online redo log hiện tại có thể chứa redo chưa archive. Trong một số recovery path, Oracle có thể cần online redo log hoặc redo hiện tại để hoàn tất recovery. Không xóa/move online redo log để thay thế cho backup archived logs.

### 13.6. Kiểm tra khoảng SCN

```sql
SELECT
    thread#,
    sequence#,
    first_change#,
    next_change#,
    name,
    status,
    deleted
FROM v$archived_log
WHERE resetlogs_change# = (
    SELECT resetlogs_change# FROM v$database
)
ORDER BY thread#, first_change#;
```

Đây là một góc nhìn cho incarnation hiện tại. Để điều tra recovery target cũ, phải xét incarnation và metadata backup tương ứng, không chỉ lọc incarnation hiện tại.

## 14. Restore và recover bằng RMAN

### 14.1. RESTORE và RECOVER khác nhau

RESTORE chép backup datafile/control file về vị trí database cần dùng. RECOVER áp dụng incremental backup và redo (archived/online) để đưa datafile tới target consistency.

Một database restore thành công nhưng không có đủ redo vẫn có thể chưa mở được ở target yêu cầu.

### 14.2. Restore/recover database hoàn chỉnh

Trong tình huống datafile cần restore và database có đủ backup/log:

```sql
RUN {
  RESTORE DATABASE;
  RECOVER DATABASE;
}
```

Đây là mẫu khái niệm; trạng thái database, control file và datafile cần được chuẩn bị đúng theo scenario. RMAN có thể yêu cầu archived logs cụ thể để tiếp tục.

### 14.3. Restore/recover một datafile

Ví dụ phục hồi datafile số 7:

```sql
RUN {
  RESTORE DATAFILE 7;
  RECOVER DATAFILE 7;
}
```

Sau khi recovery thành công và trạng thái database cho phép, đưa datafile online theo runbook. Không thực hiện OFFLINE/ONLINE tùy tiện trên datafile SYSTEM hoặc file critical.

### 14.4. Archived log được restore tự động

Khi RMAN recover datafile/database, nó có thể tự restore archived log cần thiết từ backup nếu repository biết backup piece và device khả dụng. Nếu không tìm thấy log, kiểm tra backup piece, catalog, channel, incarnation và thread/sequence.

### 14.5. Restore archived log riêng

Ví dụ:

```sql
RESTORE ARCHIVELOG
  FROM SEQUENCE 100
  UNTIL SEQUENCE 120
  THREAD 1;
```

Đường dẫn restore mặc định theo cấu hình RMAN/log destination. Có thể dùng SET ARCHIVELOG DESTINATION trong RUN block để restore tới vị trí tạm phù hợp, sau đó catalog hoặc sử dụng theo recovery runbook.

### 14.6. Preview trước restore

RMAN hỗ trợ PREVIEW để hiển thị backup cần dùng mà không thực hiện restore:

```sql
RESTORE DATABASE PREVIEW;
```

Dùng PREVIEW để kiểm tra backup selection, sau đó mới thực hiện restore trong môi trường recovery đã chuẩn bị.

## 15. Complete recovery và incomplete recovery

### 15.1. Complete recovery

Complete recovery áp dụng toàn bộ redo cần thiết để đưa database/datafile tới trạng thái mới nhất có thể theo redo hiện có và mục tiêu recovery. Nếu có đủ backup và log liên tục, có thể phục hồi mà không bỏ các transaction đã commit trong phạm vi redo.

### 15.2. Incomplete recovery

Incomplete recovery dừng tại một target sớm hơn current point, ví dụ:

- SCN cụ thể.
- Timestamp cụ thể.
- Log sequence cụ thể.
- Một restore point.

Các thay đổi sau target sẽ không có trong database sau recovery. Sau incomplete database recovery, thường cần OPEN RESETLOGS để tạo incarnation mới.

### 15.3. Point-in-time recovery theo SCN

Ví dụ RMAN:

```sql
RUN {
  SET UNTIL SCN 123456789;
  RESTORE DATABASE;
  RECOVER DATABASE;
}
```

Sau khi recovery hoàn tất, mở database theo hướng dẫn, thường:

```sql
ALTER DATABASE OPEN RESETLOGS;
```

SCN chỉ là số minh họa. Trước khi thực hiện, xác định target SCN, incarnation, backup phù hợp và ảnh hưởng mất dữ liệu sau target.

### 15.4. Point-in-time recovery theo thời gian

Ví dụ:

```sql
RUN {
  SET UNTIL TIME
    "TO_DATE('2026-11-14 10:00:00',
             'YYYY-MM-DD HH24:MI:SS')";
  RESTORE DATABASE;
  RECOVER DATABASE;
}
```

Thời gian target phải được hiểu theo timezone/clock và semantics RMAN của môi trường. Với giao dịch quan trọng, SCN hoặc restore point có thể xác định ranh giới chính xác hơn timestamp.

### 15.5. OPEN RESETLOGS

OPEN RESETLOGS tạo incarnation mới và reset redo sequence branch. Sau đó:

- Xác nhận database open và role.
- Kiểm tra backup/archivelog destinations.
- Backup database mới theo baseline.
- Đồng bộ recovery catalog/incarnation metadata.
- Kiểm tra Data Guard/standby và quy trình role/flashback nếu có.

Không dùng RESETLOGS sau complete recovery bình thường nếu không có yêu cầu của recovery scenario.

## 16. Archived redo log trong RAC

### 16.1. Mỗi instance có redo thread

Trong RAC, mỗi instance thường ghi vào redo thread riêng. Khi instance chuyển log, archived log tương ứng thuộc thread đó. Database-wide backup/recovery phải xét tất cả thread có redo cần thiết.

### 16.2. Kiểm tra thread

```sql
SELECT
    thread#,
    enabled,
    status,
    instance
FROM v$thread
ORDER BY thread#;
```

Trong RAC, có thể xem trạng thái instance/thread trên cluster bằng GV$INSTANCE và view liên quan. Thread disabled vẫn có lịch sử sequence/archived log trong control file.

### 16.3. Kiểm tra sequence theo thread

```sql
SELECT
    thread#,
    MAX(sequence#) AS max_archived_sequence,
    MAX(next_change#) AS max_next_scn
FROM v$archived_log
WHERE archived = 'YES'
  AND deleted = 'NO'
GROUP BY thread#
ORDER BY thread#;
```

Truy vấn max sequence chỉ cho biết đầu mút; không chứng minh không có gap. Cần kiểm tra chuỗi sequence và SCN liên tục, cùng backup piece thực sự chứa log.

### 16.4. Backup archive logs trên RAC

RMAN kết nối target database có thể backup archived logs từ các thread theo cấu hình. Nếu archived logs nằm trên local filesystem chỉ thấy từ node tạo log, channel chạy trên node khác có thể không truy cập được file.

Các cách triển khai thường gặp:

- Dùng ASM/shared storage để các instance/channel nhìn thấy cùng archive files.
- Dùng shared filesystem được mount đúng trên các node.
- Cấu hình channel/node affinity và archive destination theo kiến trúc được hỗ trợ.

Không giả định một đường dẫn local trên node 1 cũng tồn tại trên node 2.

### 16.5. Recovery và thread gap

Khi restore database RAC, RMAN/Oracle cần redo từ mọi thread liên quan. Nếu thiếu một archived log của thread 2, recovery có thể dừng dù thread 1 có đủ sequence. Tìm bản copy khác, backup piece, standby hoặc archive destination cũ để khôi phục sequence bị thiếu.

### 16.6. Thread và incarnation

Sau RESETLOGS, sequence có thể bắt đầu lại trong incarnation mới. Khi xử lý archive file từ nhiều node hoặc backup cũ, nhận diện bằng DBID, thread, sequence và resetlogs metadata, không chỉ filename.

## 17. Archived redo log và Data Guard

### 17.1. Redo transport

Data Guard chuyển redo từ primary tới standby. Redo có thể được truyền qua network theo chế độ transport và được lưu/áp dụng tại standby. Archived logs là đơn vị quan trọng để xử lý transport/apply và gap resolution.

### 17.2. Standby redo logs

Standby redo logs (SRL) cho phép standby nhận redo stream, đặc biệt trong real-time apply. SRL không giống archived log; sau khi redo được archive tại standby, archived log có thể được apply hoặc giữ theo policy.

### 17.3. Transport và apply

Phân biệt:

- Shipped: redo/archive đã được chuyển tới standby.
- Received: standby đã nhận log/redo.
- Applied: redo đã được apply vào standby database.

Một log được shipped chưa chắc đã applied. Deletion policy phải phù hợp với mục tiêu cần standby apply trước khi xóa log trên primary.

### 17.4. Kiểm tra archive destination Data Guard

```sql
SELECT
    dest_id,
    status,
    target,
    destination,
    error,
    recovery_mode,
    synchronization_status
FROM v$archive_dest_status
WHERE status <> 'INACTIVE'
ORDER BY dest_id;
```

Các cột có thể khác theo release/role. Xem cả V$ARCHIVE_DEST, V$ARCHIVE_DEST_STATUS và Data Guard Broker status khi dùng Broker.

### 17.5. Kiểm tra applied logs ở standby

Trên standby, có thể xem:

```sql
SELECT
    thread#,
    sequence#,
    first_time,
    next_time,
    applied,
    name
FROM v$archived_log
ORDER BY thread#, sequence#;
```

Giá trị APPLIED có thể có semantics khác nhau theo role và view; kiểm tra tài liệu release. Đối chiếu với managed recovery process, apply lag và broker output.

### 17.6. Archive gap

Archive gap xảy ra khi standby thiếu một hoặc nhiều redo log cần để tiếp tục apply. Oracle có thể tự yêu cầu/nhận log từ primary nếu transport/configuration cho phép. Nếu log không còn trên primary, DBA cần tìm backup/archive copy khác hoặc xử lý gap theo Data Guard runbook.

### 17.7. Deletion policy trong Data Guard

Không xóa archived logs trên primary chỉ vì đã backup nếu standby chưa nhận/apply theo policy cần thiết. Policy TO APPLIED ON ALL STANDBY là một lựa chọn thường gặp khi cần chờ mọi standby apply, nhưng phải đánh giá tất cả standby và trạng thái role transition.

Nếu một standby bị offline dài ngày, policy chờ apply có thể làm primary giữ archive lâu và FRA tăng. Đó là tín hiệu cần xử lý standby/retention/capacity, không phải lý do tự động bỏ policy.

### 17.8. Sau failover/switchover

Sau role transition, xác định database nào là primary mới, thread/sequence mới và các archived log còn cần cho standby cũ. Kiểm tra incarnation, transport destination, apply state và deletion policy. Không xóa log chỉ dựa trên role cũ.

## 18. Missing archived log và recovery gap

### 18.1. Dấu hiệu

Recovery có thể dừng vì thiếu archived log cần thiết, RMAN báo không tìm thấy log/backup piece, hoặc standby báo archive gap. Database không thể tiếp tục tới target nếu thiếu đoạn redo bắt buộc.

### 18.2. Tìm sequence bị thiếu

Kiểm tra metadata theo thread và sequence:

```sql
SELECT
    thread#,
    sequence#,
    first_change#,
    next_change#,
    name,
    status,
    deleted
FROM v$archived_log
WHERE thread# = 1
  AND sequence# BETWEEN 100 AND 120
ORDER BY sequence#, recid;
```

Nhiều record cùng sequence có thể là nhiều copy. Kiểm tra file tồn tại và backup metadata, không chỉ dựa vào record AVAILABLE.

### 18.3. Tìm backup chứa archived log

Trong RMAN:

```text
LIST BACKUP OF ARCHIVELOG
  FROM SEQUENCE 100
  UNTIL SEQUENCE 120;
```

Điều chỉnh thread theo syntax/selection phù hợp release. Kiểm tra backup piece có sẵn và device có thể đọc.

### 18.4. Nguồn thay thế

Nếu archive file bị thiếu tại destination chính, tìm:

- Bản copy tại destination khác.
- Backup set trên disk/tape/cloud.
- FRA hoặc storage snapshot được quản lý.
- Standby database/archive destination.
- Backup từ node RAC khác/shared storage.
- Bản copy offsite được catalog đúng DBID/incarnation.

Không tự tạo file giả hoặc đổi tên log khác sequence để lấp gap.

### 18.5. Nếu không thể lấy log bị thiếu

Nếu không có bản copy redo bắt buộc, recovery có thể chỉ thực hiện tới SCN trước gap hoặc phải dùng phương án disaster recovery khác. Đánh giá mức mất dữ liệu, business transaction và restore point; không bỏ qua log để ép database mở ở trạng thái không nhất quán.

### 18.6. Recover tới trước gap

Trong một số trường hợp có thể chọn incomplete recovery tới SCN/time trước log thiếu, sau đó OPEN RESETLOGS. Điều này bỏ mọi thay đổi sau target, kể cả transaction hợp lệ. Cần phê duyệt business/data loss và backup mới trước khi thực hiện.

## 19. Kiểm tra backup archived log

### 19.1. LIST ARCHIVELOG

Trong RMAN:

```text
LIST ARCHIVELOG ALL;
LIST BACKUP OF ARCHIVELOG ALL;
```

Hai lệnh cho góc nhìn khác nhau: file archived log đã biết và backup set chứa archived log. Kiểm tra cả hai khi điều tra.

### 19.2. CROSSCHECK ARCHIVELOG

```text
CROSSCHECK ARCHIVELOG ALL;
```

CROSSCHECK so sánh metadata RMAN với sự tồn tại của file ở storage/device. File không tìm thấy có thể được đánh dấu EXPIRED trong repository.

### 19.3. DELETE EXPIRED

Sau crosscheck và xác minh file thực sự không còn:

```text
DELETE EXPIRED ARCHIVELOG ALL;
```

Lệnh này dọn metadata của file đã được đánh dấu EXPIRED; nó không phục hồi file bị mất. Không chạy để che lỗi storage hoặc để xóa file còn cần thiết.

### 19.4. VALIDATE

RMAN có thể kiểm tra khả năng đọc backup:

```text
RESTORE ARCHIVELOG
  FROM SEQUENCE 100
  UNTIL SEQUENCE 110
  THREAD 1
  VALIDATE;
```

Kiểm tra syntax cụ thể trong release và backup device. VALIDATE đọc/kiểm tra backup data nhưng không tạo bản restore phục vụ production.

### 19.5. Restore rehearsal

Validation không thay thế restore test. Một backup set đọc được vẫn có thể thiếu control file, catalog metadata, encryption wallet, channel/media library hoặc archived log kế tiếp. Hãy định kỳ restore archived logs và recover một database clone ở môi trường riêng.

### 19.6. Kiểm tra backup piece

Xác nhận:

- Backup piece tồn tại trên storage.
- RMAN repository nhận diện piece.
- Piece không bị truncate/corrupt.
- Encryption wallet/key khả dụng.
- Compression/media management tương thích.
- Có đủ datafile backup và redo để tới target.
- Có control file/SPFILE metadata cần thiết.

## 20. Bảo vệ archived redo log và backup

### 20.1. Storage độc lập

Không giữ bản archived log duy nhất trên cùng volume với datafile/redo log nếu một lỗi storage có thể phá hủy tất cả. Backup archived log nên có bản copy trên storage độc lập và theo chiến lược offsite.

### 20.2. Immutable/offline copy

Ransomware hoặc lỗi quản trị có thể xóa đồng thời database và backup nếu cùng dùng credential/storage. Dùng immutable/object lock, offline tape hoặc repository tách quyền để bảo vệ bản backup theo chính sách.

### 20.3. Encryption

Archived redo log có thể chứa dữ liệu nhạy cảm trong redo records. Bảo vệ khi truyền và lưu trữ; cân nhắc RMAN backup encryption và bảo vệ wallet/keystore. Nếu backup mã hóa mà mất wallet/key, backup có thể không sử dụng được.

### 20.4. Compression

RMAN có thể dùng backup compression để giảm storage/network. Compression tiêu tốn CPU và hiệu quả phụ thuộc dữ liệu. Đo throughput, CPU và thời gian restore; không chọn mức compression chỉ theo dung lượng.

### 20.5. Checksums và corruption detection

Oracle/RMAN có các cơ chế checksum/validation để phát hiện lỗi block/backup. Bật và sử dụng các cơ chế được hỗ trợ; kiểm tra output validation. Một file tồn tại trên filesystem không có nghĩa nội dung backup hợp lệ.

### 20.6. Backup access control

Giới hạn ai có quyền đọc/xóa backup, FRA và archived log. Tách quyền vận hành database khỏi quyền xóa backup nếu có thể; log audit các thao tác DELETE, crosscheck và thay đổi RMAN configuration.

## 21. Monitoring và cảnh báo archive

### 21.1. Archive destination status

Theo dõi định kỳ:

```sql
SELECT
    dest_id,
    status,
    binding,
    target,
    destination,
    error
FROM v$archive_dest
WHERE status <> 'INACTIVE'
ORDER BY dest_id;
```

STATUS/ERROR giúp phát hiện destination bị lỗi. Một destination có thể là LOCAL hoặc SERVICE tùy cấu hình. Xem cả trạng thái destination và transport.

### 21.2. Archive processes

```sql
SELECT *
FROM v$archive_processes;
```

View cung cấp thông tin về archiver process theo release. Đối chiếu alert log và archive destination nếu archiver không tiến triển.

### 21.3. Log switch rate

Có thể thống kê log switch theo giờ:

```sql
SELECT
    TRUNC(first_time, 'HH24') AS hour_start,
    thread#,
    COUNT(*) AS switches
FROM v$log_history
WHERE first_time >= SYSDATE - 1
GROUP BY TRUNC(first_time, 'HH24'), thread#
ORDER BY hour_start, thread#;
```

Log switch quá thường xuyên có thể tạo nhiều archive files và tăng workload archiver/backup. Tần suất cao không tự động là lỗi; so sánh redo generation, log size và workload.

### 21.4. FRA usage

```sql
SELECT
    ROUND(space_limit / 1024 / 1024 / 1024, 2) AS limit_gb,
    ROUND(space_used / 1024 / 1024 / 1024, 2) AS used_gb,
    ROUND(space_reclaimable / 1024 / 1024 / 1024, 2) AS reclaimable_gb,
    number_of_files
FROM v$recovery_file_dest;
```

Thiết lập cảnh báo trước khi FRA chạm giới hạn, ví dụ theo percent used và tốc độ tăng dung lượng. Ngưỡng cần dựa trên archive generation peak và thời gian DBA cần để phản ứng.

### 21.5. Archive generation rate

Ước lượng lượng archive sinh theo khoảng thời gian bằng kích thước archived log:

```sql
SELECT
    TRUNC(first_time, 'HH24') AS hour_start,
    thread#,
    COUNT(*) AS log_count,
    ROUND(SUM(blocks * block_size) / 1024 / 1024, 1) AS archive_mb
FROM v$archived_log
WHERE first_time >= SYSDATE - 1
  AND name IS NOT NULL
GROUP BY TRUNC(first_time, 'HH24'), thread#
ORDER BY hour_start, thread#;
```

Một sequence có thể có nhiều record/copy trong V$ARCHIVED_LOG; nếu cộng trực tiếp có thể đếm trùng. Với báo cáo chính xác, chọn một destination/copy hoặc deduplicate theo DBID, RESETLOGS_ID, THREAD#, SEQUENCE#.

### 21.6. Cảnh báo archive destination đầy

Đặt alert cho:

- Destination STATUS không VALID hoặc có ERROR.
- FRA usage tăng nhanh và reclaimable thấp.
- Backup archived log không hoàn tất theo SLA.
- Archive generation vượt capacity dự kiến.
- Standby apply lag hoặc archive gap.
- Không có bản backup/offsite copy mới trong thời gian quy định.

Alert phải chỉ rõ database, instance, destination, error và runbook liên quan.

## 22. Lỗi thường gặp và cách xử lý

| Lỗi/triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| ORA-00257 archiver error | Archive destination đầy hoặc không ghi được | Kiểm tra destination/FRA, backup log, giải phóng theo RMAN policy |
| ORA-19809 | FRA vượt DB_RECOVERY_FILE_DEST_SIZE | Kiểm tra reclaimable, backup/deletion policy, tăng quota khi storage đủ |
| ORA-19804 | Không thể reclaim đủ dung lượng FRA | Tìm file không đủ điều kiện xóa, backup/archive backlog, storage capacity |
| ORA-16014 | Log sequence không được archive tới destination cần thiết | Kiểm tra LOG_ARCHIVE_DEST, destination state và lỗi storage/network |
| ORA-16038 | Log không thể archive | Kiểm tra destination, permission, space và alert log |
| ORA-00308 | Không thể mở archived log | Tìm file ở destination/backup khác, kiểm tra path và permission |
| ORA-00279/ORA-00289 | Recovery yêu cầu redo/archived log cụ thể | Xác định thread/sequence/SCN, restore log đúng incarnation |
| RMAN-06025 | Không tìm thấy backup archived log phù hợp | Kiểm tra LIST BACKUP, device, catalog và retention |
| RMAN-06054 | Recovery yêu cầu archived log chưa biết trong repository | Tìm archive file, catalog đúng hoặc xác định target recovery |
| Standby archive gap | Standby thiếu sequence/thread | Tìm và chuyển log bị thiếu, xử lý transport/apply |
| Backup job báo thành công nhưng restore thiếu log | Backup selection/retention không bao phủ chain | Kiểm tra backup metadata, sequence/thread, restore test |
| FRA reclaimable thấp | Log chưa backup/applied hoặc policy giữ lại | Kiểm tra deletion policy, standby và backup SLA |

### 22.1. ORA-00257

Khi archiver không thể ghi archive log, Oracle có thể ngăn thêm transaction khi cần log switch mà không thể archive log group. Xử lý:

1. Kết nối bằng phương thức quản trị phù hợp; trong một số tình huống chỉ administrative connection hoạt động.
2. Kiểm tra alert log, V$ARCHIVE_DEST và V$RECOVERY_FILE_DEST.
3. Xác định destination đầy, permission sai, mount lỗi hay network remote.
4. Backup archived logs còn cần tới storage khác.
5. Xóa file đủ điều kiện bằng RMAN theo deletion policy.
6. Xác nhận archiver hoạt động và database tiếp tục log switch.

Không xóa file archive thủ công để khôi phục dịch vụ.

### 22.2. ORA-19809 và ORA-19804

Các lỗi này thường liên quan FRA đã dùng hết quota hoặc không thể reclaim file đủ điều kiện. Kiểm tra loại file chiếm dung lượng và policy giữ lại. Có thể tăng DB_RECOVERY_FILE_DEST_SIZE nếu storage thật còn capacity, nhưng đó không phải giải pháp nếu volume vật lý đã đầy.

### 22.3. ORA-00308

Recovery hoặc process archive không mở được archived log tại đường dẫn được chỉ ra. Kiểm tra:

- File có tồn tại không?
- File có bị rename/move/xóa thủ công không?
- Permission/owner/mount/ASM disk group có đúng không?
- Có bản copy ở destination khác hoặc backup set không?
- Metadata RMAN/control file có trỏ đúng file không?

### 22.4. RMAN-06025 và RMAN-06054

Kiểm tra database DBID, incarnation, thread và sequence. Dùng LIST BACKUP OF ARCHIVELOG, LIST INCARNATION và CROSSCHECK khi phù hợp. Nếu file nằm ngoài repository, CATALOG file hợp lệ rồi thử lại restore/recover.

Nếu không có bản copy cần thiết, xác định target recovery trước gap và đánh giá data loss. Không ép recover bỏ qua redo bắt buộc.

## 23. Runbook backup archived redo log

### 23.1. Trước khi chạy job

- [ ] Database ở ARCHIVELOG mode.
- [ ] Archive destination hoạt động và còn dung lượng.
- [ ] RMAN target/recovery catalog kết nối được.
- [ ] Backup device/channel sẵn sàng.
- [ ] Retention và archived log deletion policy đã được xác nhận.
- [ ] Standby transport/apply state được kiểm tra nếu có.
- [ ] Storage backup độc lập với source archive.

### 23.2. Chạy backup

Một mẫu job cơ bản:

```sql
BACKUP ARCHIVELOG ALL
  TAG 'ARCHIVE_DAILY';
```

Hoặc trong backup job database:

```sql
BACKUP DATABASE PLUS ARCHIVELOG
  TAG 'DB_FULL_PLUS_ARCH';
```

Lệnh thực tế phải phù hợp với channel, device, compression, encryption và storage policy.

### 23.3. Xác minh backup

```text
LIST BACKUP OF ARCHIVELOG ALL;
REPORT OBSOLETE;
```

Đối chiếu thread/sequence, thời gian, tag, backup piece và trạng thái job. Kiểm tra job log không có warning/error bị bỏ qua.

### 23.4. Dọn dẹp

Nếu deletion policy đã được kiểm chứng và backup hoàn tất:

```sql
BACKUP ARCHIVELOG ALL DELETE INPUT;
```

Hoặc dùng DELETE theo policy/runbook. Không dùng DELETE ALL INPUT nếu chưa xác nhận có thể xóa mọi copy.

### 23.5. Ghi nhận

Lưu:

- Thời gian job bắt đầu/kết thúc.
- DBID, DB_UNIQUE_NAME và incarnation.
- Các thread/sequence được backup.
- Backup piece, device và tag.
- Dung lượng archive/backup.
- Kết quả validation.
- Số file đã xóa và policy áp dụng.
- Lỗi, retry và người xử lý.

## 24. Runbook phục hồi cần archived redo log

### 24.1. Xác định recovery objective

Trước restore/recover, xác định:

- Database hay chỉ một datafile cần phục hồi?
- Target là current/latest, SCN, timestamp hay restore point?
- Database đang ở incarnation nào?
- Data Guard standby có thể cung cấp redo không?
- RPO/RTO cho phép mất bao nhiêu dữ liệu và downtime bao lâu?

### 24.2. Kiểm tra backup chain

Xác định datafile backup phù hợp, control file/SPFILE, incremental backup và archived logs từ checkpoint tới target. Kiểm tra thread/sequence/SCN continuity.

### 24.3. Kiểm tra khả năng đọc

Dùng RMAN PREVIEW/VALIDATE khi phù hợp. Xác nhận media manager, wallet, password file, storage mount và quyền truy cập. Không bắt đầu restore lớn khi chưa biết backup piece nằm ở đâu.

### 24.4. Thực hiện restore/recover

Chạy trong recovery environment theo runbook:

```sql
RUN {
  RESTORE DATABASE;
  RECOVER DATABASE;
}
```

Nếu là incomplete recovery, đặt target trước RESTORE/RECOVER và chuẩn bị OPEN RESETLOGS theo scenario. Không trộn lệnh complete recovery với incomplete target.

### 24.5. Xác nhận database sau recovery

- Kiểm tra alert log và recovery messages.
- Xác nhận database open mode và role.
- Kiểm tra datafile status và read/write access.
- Chạy kiểm tra nghiệp vụ và đối soát dữ liệu.
- Xác nhận backup mới sau RESETLOGS nếu có.
- Kiểm tra Data Guard/standby và archive destinations.

## 25. Bài lab: backup archived redo log bằng RMAN

Chỉ chạy trên database lab có quyền RMAN và storage riêng. Điều chỉnh path cho OS/ASM hiện có.

### 25.1. Kiểm tra mode

Trong SQL*Plus:

```sql
ARCHIVE LOG LIST
SELECT log_mode FROM v$database;
```

Nếu database là NOARCHIVELOG, không chuyển mode trên database dùng chung chỉ để làm lab. Dùng một instance lab riêng.

### 25.2. Tạo archived log mới

```sql
ALTER SYSTEM SWITCH LOGFILE;
ALTER SYSTEM ARCHIVE LOG CURRENT;
```

Đợi archive process hoàn tất và kiểm tra V$ARCHIVED_LOG.

### 25.3. Backup log

Trong RMAN:

```text
BACKUP ARCHIVELOG ALL
  FORMAT '/backup/lab/arch_%d_%T_%s_%p.bkp'
  TAG 'LAB_ARCH';
```

Đường dẫn là ví dụ; tạo thư mục và cấp quyền trước khi chạy.

### 25.4. Xem backup

```text
LIST BACKUP OF ARCHIVELOG ALL;
```

Xác định thread, sequence, start/end SCN và backup piece được ghi.

### 25.5. Validate

```text
RESTORE ARCHIVELOG ALL VALIDATE;
```

Nếu cú pháp/selection khác theo release, dùng RESTORE ARCHIVELOG với phạm vi cụ thể và VALIDATE theo tài liệu phiên bản.

### 25.6. Backup rồi delete input trên lab

Sau khi xác nhận backup piece và deletion policy:

```text
BACKUP ARCHIVELOG ALL DELETE INPUT;
```

Kiểm tra file source đã được xóa theo phạm vi input và RMAN repository phản ánh trạng thái đúng. Không chạy lệnh này trên production chỉ để thử nghiệm.

## 26. Bài lab: xem recovery chain và gap

### 26.1. Xem archive theo thread/sequence

```sql
SELECT
    thread#,
    sequence#,
    first_change#,
    next_change#,
    first_time,
    next_time,
    name
FROM v$archived_log
WHERE name IS NOT NULL
ORDER BY thread#, sequence#;
```

### 26.2. Xem backup metadata

```text
LIST BACKUP OF DATABASE;
LIST BACKUP OF ARCHIVELOG ALL;
LIST INCARNATION;
```

Đối chiếu datafile backup và archive backup cùng incarnation.

### 26.3. Thử restore preview

```text
RESTORE DATABASE PREVIEW;
```

Quan sát backup pieces và archived logs RMAN dự định sử dụng. PREVIEW không thay thế restore test.

### 26.4. Mô phỏng archive gap an toàn

Không xóa archived log production. Trong một bản clone/lab, có thể tạo một archive copy thiếu có kiểm soát hoặc dùng metadata test để hiểu recovery báo missing log. Quan sát RMAN yêu cầu thread/sequence nào và xác định nguồn backup cần thiết.

### 26.5. Phục hồi bản clone

Restore/recover một database clone vào vị trí riêng theo runbook. Xác nhận database open và dữ liệu tại target SCN. Lab hoàn tất khi có bằng chứng log chain đã được dùng và ứng dụng test đọc được dữ liệu.

## 27. Nguyên tắc thực hành tốt

1. **Dùng ARCHIVELOG cho production cần media recovery.** ARCHIVELOG mode tự nó không phải backup.
2. **Backup datafile và archived redo log như một recovery chain.** Phải có redo liên tục từ checkpoint tới target.
3. **Theo dõi thread và sequence.** RAC có nhiều redo thread; không chỉ kiểm tra sequence lớn nhất.
4. **Xét SCN và incarnation.** Filename/sequence không đủ để xác định log thuộc recovery branch nào.
5. **Dùng RMAN làm công cụ chính.** Quản lý metadata, backup selection, restore và deletion theo policy.
6. **Dùng PLUS ARCHIVELOG cho online database backup phù hợp.** Hiểu log switch và redo bao phủ quanh datafile backup.
7. **Backup control file/SPFILE.** Bật control file autobackup và bảo vệ metadata cần cho restore.
8. **Tách retention policy khỏi deletion policy.** Một policy quản lý backup cần giữ, policy kia điều kiện xóa archive log.
9. **Không xóa thủ công.** Dùng RMAN CROSSCHECK/DELETE theo runbook.
10. **Giữ bản copy độc lập/offsite.** Không để backup duy nhất cùng failure domain với database.
11. **Kiểm tra FRA trước khi đầy.** Theo dõi space used, reclaimable, archive generation và backup backlog.
12. **Tôn trọng Data Guard apply.** Không xóa log trước khi standby nhận/apply theo policy.
13. **Validate và restore test định kỳ.** Backup job thành công không chứng minh recovery thành công.
14. **Bảo vệ encryption wallet.** Backup mã hóa không dùng được nếu mất key.
15. **Kiểm soát backup deletion.** Phân quyền, audit và immutable/offline copy.
16. **Đặt recovery objective rõ.** RPO/RTO quyết định retention, archive storage và backup frequency.
17. **Theo dõi alert log.** ORA-00257, ORA-19809 và archive gap cần xử lý trước khi ảnh hưởng production.
18. **Lập runbook theo release/topology.** RAC, CDB/PDB, ASM và Data Guard có yêu cầu riêng.

## 28. Câu hỏi tự kiểm tra

1. Online redo log và archived redo log khác nhau như thế nào?
2. Vì sao archived log chỉ được tạo sau log switch/archive operation?
3. ARCHIVELOG mode cho phép những khả năng recovery nào?
4. NOARCHIVELOG mode hạn chế online backup ra sao?
5. Thread, sequence và SCN có vai trò gì?
6. Vì sao RAC cần archived redo từ nhiều thread?
7. FIRST_CHANGE# và NEXT_CHANGE# mô tả điều gì?
8. Vì sao sequence max không chứng minh log chain không có gap?
9. RESETLOGS tạo incarnation mới có ý nghĩa gì?
10. RMAN BACKUP ARCHIVELOG ALL thực hiện việc gì?
11. BACKUP DATABASE PLUS ARCHIVELOG giúp online backup thế nào?
12. Vì sao online datafile backup cần archived redo log?
13. DELETE INPUT khác DELETE ALL INPUT ra sao?
14. Vì sao không nên xóa archived log bằng OS?
15. Backup optimization ảnh hưởng archived log backup thế nào?
16. Retention policy khác archived log deletion policy ra sao?
17. Deletion policy TO APPLIED ON ALL STANDBY bảo vệ điều gì?
18. FRA chứa những loại recovery file nào?
19. ORA-19809 và ORA-19804 thường liên quan vấn đề gì?
20. Vì sao tăng DB_RECOVERY_FILE_DEST_SIZE không tạo thêm storage?
21. Control file autobackup giúp ích gì khi mất control file?
22. Recovery catalog khác metadata trong control file ra sao?
23. Restore khác recover thế nào?
24. Complete recovery khác incomplete recovery ra sao?
25. Khi nào cần OPEN RESETLOGS?
26. Làm thế nào tìm archived log bị thiếu?
27. Vì sao thiếu một sequence có thể chặn recovery dù các sequence khác còn đủ?
28. Shipped và applied trong Data Guard khác nhau thế nào?
29. VALIDATE khác restore rehearsal ra sao?
30. Cần kiểm tra gì trước khi cho phép RMAN DELETE INPUT?

## 29. Mô hình ghi nhớ

```text
DATAFILE BACKUP
     |
     |  checkpoint SCN
     v
ARCHIVED REDO LOG CHAIN
     |
     +-- Thread 1: sequence / SCN
     +-- Thread 2: sequence / SCN (RAC)
     +-- Incarnation / RESETLOGS branch
     |
     v
RMAN BACKUP AND RETENTION
     |
     +-- BACKUP ARCHIVELOG
     +-- BACKUP DATABASE PLUS ARCHIVELOG
     +-- Control file / SPFILE autobackup
     +-- Retention policy
     +-- Archived log deletion policy
     |
     v
PROTECTED STORAGE
     |
     +-- FRA / archive destination
     +-- Independent backup repository
     +-- Offsite / immutable copy
     +-- Encryption wallet and metadata
     |
     v
RESTORE + RECOVER
     |
     +-- Complete recovery
     +-- Incomplete / PITR
     +-- RAC thread continuity
     +-- Data Guard gap resolution
     |
     v
VALIDATE + RESTORE TEST
```

**Điểm cần nhớ:** Archived redo log nối datafile backup với thời điểm recovery mục tiêu. Khả năng phục hồi phụ thuộc backup nền, redo liên tục theo SCN/thread/incarnation và metadata đủ để tìm đúng file. Dùng RMAN để backup, kiểm tra và xóa theo policy; giữ bản copy độc lập, theo dõi FRA/Data Guard và thường xuyên diễn tập restore/recover.
