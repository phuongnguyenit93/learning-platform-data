# Phục hồi khi mất control file, SPFILE hoặc online redo log trong Oracle

Control file, SPFILE và online redo log là ba thành phần quan trọng nhưng có vai trò khác nhau trong Oracle Database. Control file lưu metadata cấu trúc và trạng thái của database; SPFILE lưu initialization parameters dùng khi khởi động instance; online redo log ghi lại các thay đổi để instance recovery và media recovery có thể đưa database về trạng thái nhất quán.

Khi một thành phần bị mất hoặc hỏng, cách phục hồi phụ thuộc vào số bản sao còn dùng được, database đang chạy hay đã dừng, ARCHIVELOG mode, loại redo log bị mất, backup hiện có và thời điểm dữ liệu cần khôi phục. Không có một lệnh duy nhất phù hợp cho mọi tình huống.

Nguyên tắc xử lý:

- Xác định chính xác file, group/member, instance và trạng thái hiện tại trước khi thay đổi.
- Bảo toàn các bản sao còn tốt; không xóa hoặc ghi đè file còn khả năng phục hồi.
- Ưu tiên restore từ RMAN backup/autobackup hoặc bản sao multiplexed hợp lệ.
- Phân biệt complete recovery với incomplete recovery và hiểu khi nào phải OPEN RESETLOGS.
- Không giả định online redo log có thể restore như datafile; online redo thường phải được bảo toàn hoặc tái tạo theo tình huống.
- Sau phục hồi, xác minh database, service, backup chain, archived logs và tạo backup mới khi cần.

Bài học thuộc chủ đề **Sao lưu và phục hồi** của *Database Engine Relational Oracle*. Nội dung tập trung vào:

- Vai trò và multiplexing của control file, SPFILE, online redo log.
- Xác định trạng thái database và mức độ mất file.
- Phục hồi control file từ bản sao hoặc RMAN autobackup.
- Phục hồi SPFILE từ memory, PFILE hoặc RMAN autobackup.
- Xử lý mất một redo log member so với mất toàn bộ group.
- Phân biệt CURRENT, ACTIVE, INACTIVE, archived và unarchived log.
- CLEAR LOGFILE, DROP/ADD LOGFILE MEMBER và giới hạn recovery.
- RESETLOGS, incarnation, backup mới và kiểm tra sau phục hồi.
- Các runbook tình huống, lỗi thường gặp và bài thực hành trong môi trường lab.

## 1. Vai trò của ba loại file

### Control file

Control file là file nhị phân nhỏ nhưng thiết yếu, chứa thông tin như:

- Database name và DBID.
- Database creation timestamp và checkpoint information.
- Danh sách datafiles và tempfile.
- Online redo log groups và members.
- Archived redo log history.
- Backup metadata và RMAN repository records trong phạm vi control file.
- Database incarnation và trạng thái cấu trúc cần cho mount/recovery.

Instance cần control file để mount database. Nếu tất cả control file copies đều mất, database không thể mount theo cách thông thường cho tới khi control file được restore hoặc recreate.

### SPFILE

SPFILE (Server Parameter File) lưu initialization parameters như CONTROL_FILES, DB_NAME, DB_UNIQUE_NAME, MEMORY_TARGET, PROCESSES và các cấu hình startup khác. Instance đọc SPFILE khi startup.

Mất SPFILE không nhất thiết làm instance đang chạy dừng ngay. Nếu instance vẫn chạy, giá trị parameter đang ở memory vẫn có thể được đọc để tạo PFILE hoặc tạo lại SPFILE. Nếu instance đã dừng và không có SPFILE/PFILE, cần khôi phục cấu hình trước khi startup.

### Online redo log

Online redo log ghi lại các thay đổi database theo thứ tự redo. LGWR ghi redo vào các online redo log members thuộc group hiện tại. Oracle luân phiên các group khi log switch. Redo cần cho instance recovery sau crash và media recovery khi restore datafiles.

Online redo log có thể được multiplexed: mỗi group có nhiều members chứa cùng nội dung redo. Nếu một member bị mất nhưng member khác trong group còn tốt, database có thể tiếp tục sử dụng member còn lại và DBA thay member hỏng.

### Sơ đồ quan hệ

~~~text
                 Oracle Instance
                 /      |      \
                /       |       \
          SPFILE     Control     Online redo
        parameters     file       log groups
             |          |             |
          startup    mount/open     LGWR writes
                        |             |
                   datafiles <--- recovery
~~~

## 2. Chuẩn bị trước khi xử lý sự cố

Khi phát hiện mất file, không vội tạo file rỗng cùng tên, xóa group hoặc restart nhiều lần. Trước hết thu thập trạng thái.

### Xác nhận database và instance

~~~sql
SELECT name, dbid, open_mode, log_mode, database_role
FROM v$database;

SELECT instance_name, host_name, status, database_status
FROM v$instance;

SHOW PARAMETER control_files;
SHOW PARAMETER spfile;
SHOW PARAMETER db_name;
~~~

Nếu database không mở, một số view không truy vấn được. Khi đó ghi nhận lỗi startup, alert log, listener và thông tin RMAN trước khi quyết định bước tiếp theo.

### Kiểm tra control files

~~~sql
SELECT name, status, is_recovery_dest_file
FROM v$controlfile;
~~~

View này cho biết các control file paths mà instance đang dùng. Trạng thái có thể không thể hiện mọi lỗi filesystem; xác minh file trên OS/ASM và alert log.

### Kiểm tra online redo log

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

SELECT group#,
       type,
       member,
       status,
       is_recovery_dest_file
FROM v$logfile
ORDER BY group#, member;
~~~

Các trạng thái thường gặp trong V$LOG:

| STATUS | Ý nghĩa khái quát |
| --- | --- |
| CURRENT | Group đang được LGWR ghi hiện tại cho thread. |
| ACTIVE | Group không còn current nhưng redo vẫn cần cho instance recovery/checkpoint. |
| INACTIVE | Redo trong group không còn cần cho instance recovery; có thể được tái sử dụng theo điều kiện archive. |
| UNUSED | Group chưa được sử dụng kể từ khi tạo/reset log history tương ứng. |

ARCHIVED cho biết group đã được archive hay chưa. STATUS và ARCHIVED phải được đọc cùng nhau; không chỉ nhìn một cột để quyết định có thể clear/drop group.

### Kiểm tra archive destination và backup

~~~sql
ARCHIVE LOG LIST;

SELECT dest_id, status, destination, error
FROM v$archive_dest
WHERE status <> 'INACTIVE'
ORDER BY dest_id;
~~~

Trong RMAN:

~~~text
RMAN> LIST BACKUP SUMMARY;
RMAN> LIST BACKUP OF CONTROLFILE;
RMAN> LIST BACKUP OF SPFILE;
RMAN> LIST ARCHIVELOG ALL;
~~~

Nếu database chưa mount, một số lệnh LIST vẫn có thể dùng với recovery catalog hoặc control file repository còn khả dụng. Khi không có catalog và control file mất, cần DBID và thông tin vị trí autobackup để tìm backup.

### Bảo toàn bằng chứng

- Ghi lại lỗi chính xác và thời điểm phát hiện.
- Ghi nhận alert log và trace liên quan.
- Ghi lại file path, ASM disk group, group#/member, thread# và sequence#.
- Không ghi đè file còn tốt bằng bản backup cũ.
- Tránh chạy CLEAR UNARCHIVED LOGFILE hoặc OPEN RESETLOGS khi chưa xác định hậu quả.

## 3. Control file multiplexing và mức độ mất mát

Oracle có thể duy trì nhiều control file copies thông qua tham số CONTROL_FILES. Các bản sao được cập nhật đồng thời và nên đặt trên các disk/device khác nhau để giảm nguy cơ một sự cố storage làm mất tất cả.

Ví dụ:

~~~sql
SHOW PARAMETER control_files;
~~~

Một cấu hình có thể có nhiều path:

~~~text
/u01/oradata/ORCL/control01.ctl
/u02/oradata/ORCL/control02.ctl
~~~

Đây chỉ là ví dụ path; thực tế có thể dùng ASM disk group như +DATA và +RECO.

### Mất một control file copy

Nếu còn một bản control file hợp lệ, dữ liệu metadata vẫn có thể được bảo toàn. Cần xác định instance có còn hoạt động hay đã dừng. Nếu database đã dừng hoặc instance abort do lỗi control file, có thể dùng bản còn tốt để tạo lại copy bị mất, cập nhật CONTROL_FILES và startup.

Không copy một control file đang được ghi bằng lệnh OS tùy tiện khi database đang mở. Hãy dừng database theo quy trình hoặc dùng phương thức backup/restore được hỗ trợ để tạo bản sao nhất quán.

### Mất tất cả control files

Nếu tất cả control file copies mất:

- Database không thể mount bình thường.
- Cần restore control file từ RMAN backup/autobackup hoặc recreate bằng CREATE CONTROLFILE khi không còn backup khả dụng.
- Sau restore control file backup, mount database, restore/recover datafiles theo yêu cầu.
- Database thường phải OPEN RESETLOGS sau recovery dùng backup control file.

### Mất control file khi database đang mở

Nếu một control file path không còn truy cập được, Oracle có thể phát sinh lỗi I/O và instance có thể dừng/abort. Hành vi phụ thuộc file nào bị mất, hệ thống file và số bản sao còn truy cập được. Không giả định database sẽ luôn tiếp tục chạy chỉ vì CONTROL_FILES liệt kê nhiều path.

### Đặt control files trên thiết bị khác nhau

Multiplexing chỉ giúp khi các copies không cùng chịu một điểm lỗi. Đặt nhiều file cùng một filesystem/LUN không bảo vệ khỏi mất toàn bộ storage đó. Dùng failure domains khác nhau hoặc ASM redundancy phù hợp.

## 4. Khôi phục khi mất một control file copy

Tình huống: database dùng hai control files, một file bị xóa/hỏng, file còn lại vẫn hợp lệ.

### Bước 1: xác định copy còn tốt

Kiểm tra CONTROL_FILES, alert log và filesystem/ASM. Xác nhận chính xác một path nào không còn truy cập được và path còn lại là bản hợp lệ.

### Bước 2: shutdown sạch nếu instance còn chạy

Nếu instance còn hoạt động và có thể shutdown có kiểm soát:

~~~sql
SHUTDOWN IMMEDIATE;
~~~

Nếu instance đã abort, không cần lặp lại shutdown; kiểm tra trạng thái OS và alert log.

### Bước 3: tạo lại bản copy

Với filesystem, sau khi instance dừng hoàn toàn, có thể copy bản control file còn tốt sang path bị thiếu bằng công cụ OS, giữ owner/permissions phù hợp với tài khoản Oracle. Không làm bước copy khi database đang mở.

Nếu dùng ASM, dùng phương thức copy/restore được hỗ trợ cho ASM và Grid Infrastructure; không giả định thao tác file OS thông thường áp dụng cho ASM path.

### Bước 4: xác nhận CONTROL_FILES

Nếu cần đổi path hoặc thêm path mới, cập nhật SPFILE/PFILE:

~~~sql
ALTER SYSTEM SET control_files =
  '/u01/oradata/ORCL/control01.ctl',
  '/u02/oradata/ORCL/control02.ctl'
  SCOPE = SPFILE;
~~~

CONTROL_FILES là parameter cần startup để áp dụng; thay đổi yêu cầu restart. Nếu instance không dùng SPFILE, chỉnh đúng PFILE được dùng khi startup.

### Bước 5: startup và xác nhận

~~~sql
STARTUP;

SELECT name, status
FROM v$controlfile;
~~~

Kiểm tra alert log, datafiles, redo groups, database open mode và khả năng thực hiện backup.

### Lưu ý

Nếu bản control file còn lại không chắc chắn hợp lệ hoặc database cần recovery, đừng chỉ copy rồi startup. Dùng RMAN restore/recovery theo quy trình ở các phần sau.

## 5. Khôi phục khi mất toàn bộ control files bằng RMAN

Đây là tình huống nghiêm trọng hơn: mọi control file copies đều mất/hỏng, database không thể mount. Nếu có RMAN control file autobackup hoặc backup set chứa control file, restore bản backup rồi mount và recover database.

### Thông tin cần chuẩn bị

- DBID của database.
- DB_NAME và DB_UNIQUE_NAME nếu có.
- Vị trí RMAN backup/autobackup hoặc recovery catalog.
- Password/wallet cho SBT hoặc storage plugin nếu dùng tape/cloud.
- Danh sách CONTROL_FILES path đích và dung lượng/quyền truy cập.
- PFILE tạm có các tham số tối thiểu để startup NOMOUNT.

Nếu dùng recovery catalog, catalog có thể cung cấp metadata backup khi control file của target bị mất. Nếu không có catalog, DBID giúp RMAN tìm autobackup.

### Bước 1: tạo PFILE tạm

Nếu SPFILE vẫn còn, dùng nó. Nếu SPFILE cũng mất, tạo PFILE tạm từ bản backup cấu hình hoặc từ thông tin đã ghi nhận:

~~~text
*.db_name='ORCL'
*.control_files='/u01/oradata/ORCL/control01.ctl','/u02/oradata/ORCL/control02.ctl'
*.memory_target=2G
*.processes=500
~~~

Đây chỉ là ví dụ. PFILE cần chứa các tham số phù hợp với database, platform, memory configuration và đường dẫn thực tế. Không dùng giá trị ví dụ thay cho cấu hình production.

### Bước 2: kết nối RMAN và chỉ định DBID

~~~text
rman target /
RMAN> SET DBID 1234567890;
~~~

Thay DBID bằng DBID thật đã lưu trong tài liệu backup, alert log, output RMAN hoặc bản backup control file. Nếu dùng recovery catalog, kết nối catalog theo cấu hình được bảo vệ.

### Bước 3: startup NOMOUNT

~~~text
RMAN> STARTUP FORCE NOMOUNT PFILE='/tmp/initORCL.ora';
~~~

Instance ở NOMOUNT chỉ cần parameter file để khởi tạo bộ nhớ/processes. Control file chưa cần tồn tại ở giai đoạn này.

### Bước 4: restore control file từ autobackup

Nếu autobackup nằm ở vị trí mặc định/FRA và RMAN có thể dò tìm:

~~~text
RMAN> RESTORE CONTROLFILE FROM AUTOBACKUP;
~~~

Nếu dùng format hoặc vị trí tùy chỉnh, cấu hình format trước khi restore:

~~~text
RMAN> SET CONTROLFILE AUTOBACKUP FORMAT FOR DEVICE TYPE DISK
      TO '/backup/ORCL/%F';
RMAN> RESTORE CONTROLFILE FROM AUTOBACKUP;
~~~

Đường dẫn và format phải khớp nơi backup thực sự được ghi. Với SBT, cần allocate channel và thông tin media manager phù hợp. Không tự tạo file rỗng mang tên control file để thay thế.

### Bước 5: mount database

~~~text
RMAN> ALTER DATABASE MOUNT;
~~~

Sau khi control file được restore, database có thể mount và RMAN đọc metadata backup trong repository.

### Bước 6: restore/recover database

Nếu chỉ mất control file và datafiles còn tốt, có thể cần recover database để đồng bộ trạng thái theo backup control file. Nếu datafiles cũng mất/hỏng, restore chúng từ backup:

~~~text
RMAN> RESTORE DATABASE;
RMAN> RECOVER DATABASE;
~~~

Không chạy RESTORE DATABASE một cách máy móc khi datafiles còn nguyên; đánh giá file status và recovery requirement trước. Trong môi trường có catalog, datafile copies và archived logs cần được xác định theo DBID/incarnation.

### Bước 7: mở database

Khi phục hồi bằng backup control file, thông thường cần mở database bằng RESETLOGS:

~~~text
RMAN> ALTER DATABASE OPEN RESETLOGS;
~~~

RESETLOGS tạo một database incarnation mới và reset online redo log sequence. Đây là ranh giới quan trọng cho backup/recovery tiếp theo; ghi nhận incarnation mới và thực hiện backup đầy đủ ngay sau khi database được xác nhận hoạt động.

### Bước 8: xác nhận sau phục hồi

~~~sql
SELECT name, dbid, open_mode, log_mode, resetlogs_change#, resetlogs_time
FROM v$database;

SELECT name, status
FROM v$controlfile;

SELECT file#, name, status, checkpoint_change#
FROM v$datafile
ORDER BY file#;

SELECT group#, thread#, sequence#, archived, status
FROM v$log
ORDER BY thread#, group#;
~~~

Kiểm tra alert log, invalid objects, PDB open state, application services, archived log destinations, backup jobs và khả năng tạo backup mới.

### Nếu autobackup không tìm thấy

Kiểm tra DBID, autobackup format, ngày/sequence, FRA, disk path, SBT channel và quyền truy cập storage. Nếu không có autobackup, thử restore control file từ một backup piece đã biết:

~~~text
RMAN> RESTORE CONTROLFILE FROM '/backup/ORCL/cf_backup_piece.bkp';
~~~

Đường dẫn là backup piece thực tế. Nếu backup metadata chỉ nằm trong control file đã mất và không có recovery catalog, có thể cần catalog backup piece hoặc tìm bản backup control file/autobackup khác.

## 6. Recreate control file khi không có backup

Recreate control file bằng CREATE CONTROLFILE là phương án cuối cùng khi không có control file backup/autobackup khả dụng. Cần biết chính xác database name, toàn bộ datafile paths, online redo log groups/members, character set, MAXLOGFILES, MAXDATAFILES, ARCHIVELOG mode và các thuộc tính tạo database ban đầu.

Oracle có thể tạo trace script từ control file hiện tại trước khi sự cố xảy ra:

~~~sql
ALTER DATABASE BACKUP CONTROLFILE TO TRACE;
~~~

Trace file chứa script CREATE CONTROLFILE có thể dùng làm tài liệu khi cần recreate. Hãy lưu trace ở nơi an toàn và cập nhật khi cấu trúc database thay đổi.

### Hai lựa chọn RESETLOGS và NORESETLOGS

- NORESETLOGS phù hợp khi tái tạo control file và có thể tiếp tục cùng redo history theo điều kiện Oracle yêu cầu; online redo logs cần đầy đủ/hợp lệ và database phải nhất quán.
- RESETLOGS tạo incarnation mới, thường gắn với tình huống incomplete recovery hoặc khi không thể tiếp tục redo history cũ.

Không tự chọn NORESETLOGS/RESETLOGS theo phỏng đoán. Một danh sách file sai, thiếu redo group hoặc chọn sai chế độ có thể khiến database không mở hoặc mất khả năng recovery.

### Mẫu lệnh chỉ để tham khảo

~~~sql
CREATE CONTROLFILE REUSE DATABASE "ORCL"
    RESETLOGS ARCHIVELOG
    MAXLOGFILES 16
    MAXLOGMEMBERS 3
    MAXDATAFILES 200
    MAXINSTANCES 8
    MAXLOGHISTORY 1000
LOGFILE
  GROUP 1 ('/u01/oradata/ORCL/redo01.log') SIZE 200M,
  GROUP 2 ('/u01/oradata/ORCL/redo02.log') SIZE 200M,
  GROUP 3 ('/u01/oradata/ORCL/redo03.log') SIZE 200M
DATAFILE
  '/u01/oradata/ORCL/system01.dbf',
  '/u01/oradata/ORCL/sysaux01.dbf',
  '/u01/oradata/ORCL/undotbs01.dbf',
  '/u01/oradata/ORCL/users01.dbf';
~~~

Không chạy nguyên mẫu này. Phải thay toàn bộ file list, sizes, options, charset và các thuộc tính đúng với database thật. Thực hiện dưới sự kiểm soát của DBA có kinh nghiệm và có bản sao an toàn của mọi file còn lại.

Sau CREATE CONTROLFILE, Oracle có thể yêu cầu recovery và OPEN RESETLOGS tùy lựa chọn. Nếu database ở ARCHIVELOG mode, kiểm tra lại trạng thái archive và thực hiện backup mới ngay sau khi mở.

## 7. Khôi phục SPFILE

SPFILE chứa initialization parameters, không chứa user data. Mất SPFILE không đồng nghĩa datafiles bị mất. Cách phục hồi phụ thuộc instance còn chạy hay đã dừng và có bản PFILE/RMAN backup hay không.

### Tình huống A: instance vẫn đang chạy

Nếu instance vẫn hoạt động, các parameter đã được nạp trong memory. Có thể tạo PFILE từ memory:

~~~sql
CREATE PFILE = '/tmp/initORCL_recovered.ora' FROM MEMORY;
~~~

PFILE được ghi ở server filesystem. Kiểm tra file, bảo vệ permission và xác nhận các giá trị quan trọng như DB_NAME, CONTROL_FILES, DB_UNIQUE_NAME, memory, processes, archive destinations và cluster settings.

Sau đó tạo lại SPFILE:

~~~sql
CREATE SPFILE = '/u01/app/oracle/product/dbhome_1/dbs/spfileORCL.ora'
FROM PFILE = '/tmp/initORCL_recovered.ora';
~~~

Đường dẫn là ví dụ cho filesystem Oracle Home; trong RAC/ASM, SPFILE thường nằm ở shared location/ASM theo cấu hình Clusterware. Xác nhận vị trí đúng với môi trường.

Có thể tạo PFILE từ SPFILE còn bản sao khác:

~~~sql
CREATE PFILE = '/tmp/initORCL.ora' FROM SPFILE;
~~~

### Không shutdown trước khi lưu cấu hình nếu instance còn chạy

Nếu SPFILE mất nhưng instance còn chạy, đừng shutdown vội khi chưa có bản PFILE/backup cấu hình. Sau shutdown, instance có thể không startup lại được nếu không có parameter file hợp lệ.

### Tình huống B: instance đã dừng, có PFILE backup

Dùng PFILE backup để startup NOMOUNT:

~~~sql
STARTUP NOMOUNT PFILE = '/backup/initORCL.ora';
~~~

Sau đó tạo SPFILE ở vị trí chuẩn:

~~~sql
CREATE SPFILE FROM PFILE = '/backup/initORCL.ora';
~~~

Shutdown/startup lại bằng SPFILE theo quy trình nếu cần xác nhận instance đọc đúng file:

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP;
~~~

Không thực hiện restart nếu database đang phục vụ production mà chưa có maintenance plan.

### Tình huống C: SPFILE mất, có RMAN autobackup

Nếu instance không có SPFILE, cần PFILE tạm tối thiểu để startup NOMOUNT và restore SPFILE. Khi không có recovery catalog, đặt DBID trước:

~~~text
RMAN> SET DBID 1234567890;
RMAN> STARTUP FORCE NOMOUNT PFILE='/tmp/initORCL_minimal.ora';
RMAN> RESTORE SPFILE FROM AUTOBACKUP;
~~~

PFILE tối thiểu cần có DB_NAME và các tham số cần để instance khởi tạo; chi tiết phụ thuộc database. Nếu autobackup format hoặc path tùy chỉnh, đặt CONTROLFILE AUTOBACKUP FORMAT đúng trước khi RESTORE SPFILE.

Có thể restore trực tiếp ra PFILE để kiểm tra:

~~~text
RMAN> RESTORE SPFILE TO PFILE '/tmp/initORCL_from_backup.ora'
      FROM AUTOBACKUP;
~~~

Sau khi kiểm tra PFILE, tạo SPFILE ở vị trí mong muốn bằng SQL CREATE SPFILE hoặc dùng RMAN restore SPFILE trực tiếp theo môi trường. Nếu dùng ASM, xác nhận tên alias/disk group và quy trình Clusterware.

### Tình huống D: SPFILE backup piece đã biết

Nếu biết backup piece chứa SPFILE:

~~~text
RMAN> RESTORE SPFILE FROM '/backup/ORCL/spfile_backup_piece.bkp';
~~~

Nếu không dùng catalog và không tìm được autobackup, DBID và backup piece path là thông tin cần thiết. Với SBT/cloud, cần cấu hình media manager/channel để RMAN đọc backup.

### Xác nhận SPFILE sau restore

~~~sql
SHOW PARAMETER spfile;

SELECT name, value
FROM v$parameter
WHERE name IN (
    'db_name',
    'db_unique_name',
    'control_files',
    'memory_target',
    'processes',
    'remote_login_passwordfile'
)
ORDER BY name;
~~~

V$PARAMETER hiển thị giá trị runtime; SHOW PARAMETER SPFILE cho biết instance đang đọc SPFILE nào. Nếu restore SPFILE trong khi instance đang chạy bằng PFILE, phải restart có kiểm soát để instance dùng SPFILE mới.

## 8. Khôi phục online redo log: hiểu group và member

Online redo log được tổ chức thành groups. Một group có thể có nhiều members; tất cả members trong cùng group là các bản sao tương đương của cùng redo stream.

~~~text
Thread 1
  Group 1 (CURRENT)
    member /redo/redo01a.log
    member /redo_mirror/redo01b.log
  Group 2 (ACTIVE)
    member /redo/redo02a.log
    member /redo_mirror/redo02b.log
  Group 3 (INACTIVE)
    member /redo/redo03a.log
    member /redo_mirror/redo03b.log
~~~

### Mất một member

Nếu một member mất nhưng ít nhất một member khác trong group còn đọc/ghi được, database có thể tiếp tục hoạt động. Thay member bị lỗi càng sớm càng tốt để khôi phục redundancy.

### Mất toàn bộ members của một group

Đây là tình huống khác hẳn mất một member. Khả năng phục hồi phụ thuộc group là CURRENT, ACTIVE hay INACTIVE, đã archived chưa, redo có còn cần cho instance recovery không và database đang ở trạng thái nào.

### Kiểm tra trạng thái

~~~sql
SELECT l.group#,
       l.thread#,
       l.sequence#,
       l.status,
       l.archived,
       f.member,
       f.status AS member_status
FROM v$log l
JOIN v$logfile f
  ON f.group# = l.group#
ORDER BY l.thread#, l.group#, f.member;
~~~

STATUS ở V$LOGFILE có thể là NULL khi member hoạt động bình thường; trạng thái INVALID/STALE/DELETED cần điều tra. Đối chiếu V$LOG group status và alert log.

### Online redo không giống archived redo

- Online redo log là các group hiện đang được database sử dụng để ghi redo.
- Archived redo log là bản đã archive của redo group đã hoàn tất.
- RMAN backup archived logs có thể giúp media recovery.
- Online redo log files không được backup như datafiles theo cách thông thường; không giả định RESTORE DATABASE sẽ tái tạo nội dung redo log hiện tại.

Giữ archived logs và backup hợp lệ là điều kiện quan trọng để phục hồi khi online redo group bị mất.

## 9. Khôi phục khi mất một online redo log member

Tình huống: group có hai hoặc nhiều members, một member bị mất/hỏng nhưng ít nhất một member còn tốt. Vì các members trong cùng group là bản sao, Oracle vẫn có thể ghi redo qua member còn dùng được. Mục tiêu là khôi phục redundancy bằng cách thêm member mới rồi loại bỏ entry hỏng.

### Bước 1: xác nhận member lỗi và member còn tốt

~~~sql
SELECT group#, member, status
FROM v$logfile
ORDER BY group#, member;

SELECT group#, thread#, sequence#, status, archived
FROM v$log
ORDER BY thread#, group#;
~~~

Đối chiếu với alert log và OS/ASM. Đừng nhầm một member không tồn tại trên filesystem với cả group bị mất.

### Bước 2: thêm member thay thế

~~~sql
ALTER DATABASE ADD LOGFILE MEMBER
    '/u03/oradata/ORCL/redo01c.log'
TO GROUP 1;
~~~

Đường dẫn phải nằm trên storage khác failure domain nếu có thể. Oracle tạo member mới; cần quyền filesystem/ASM và dung lượng phù hợp.

### Bước 3: loại bỏ member hỏng

~~~sql
ALTER DATABASE DROP LOGFILE MEMBER
    '/u01/oradata/ORCL/redo01a.log';
~~~

Oracle có thể không cho drop member đang được dùng theo trạng thái group hoặc khi group chỉ còn một member. Nếu group CURRENT, chuyển log sang group khác khi có thể và đợi điều kiện cho phép. Không drop member tốt cuối cùng của group. Với OMF/ASM, việc xóa file vật lý được quản lý theo quy tắc storage; kiểm tra trạng thái sau DDL thay vì xóa thủ công tùy tiện.

### Bước 4: xác nhận redundancy

~~~sql
SELECT group#, type, member, status
FROM v$logfile
ORDER BY group#, member;
~~~

Kiểm tra tất cả groups có số members như thiết kế và nằm trên storage phù hợp. Kiểm tra alert log để xác nhận lỗi I/O đã hết.

### Nếu group có một member duy nhất

Nếu group chỉ có một member và file đó mất, đây là mất toàn bộ group, không phải lỗi một member. Chuyển sang quy trình xử lý group theo STATUS/ARCHIVED và recovery requirement ở các phần kế tiếp.

## 10. Mất toàn bộ members của một group INACTIVE

Group INACTIVE có nghĩa redo trong group không còn cần cho instance recovery theo checkpoint hiện tại. Nếu group đã archived, thường có thể clear group để Oracle khởi tạo lại file log.

### Bước 1: xác nhận INACTIVE và ARCHIVED

~~~sql
SELECT group#, thread#, sequence#, status, archived
FROM v$log
WHERE group# = 3;
~~~

Chỉ áp dụng ví dụ khi group 3 thực sự là INACTIVE và đã archived. Xác nhận không còn member nào đọc được và path mới sẵn sàng.

### Bước 2: clear log group

~~~sql
ALTER DATABASE CLEAR LOGFILE GROUP 3;
~~~

CLEAR LOGFILE khởi tạo lại online redo log group hiện có; nó không drop group khỏi cấu trúc database. Oracle dùng các log member paths đã ghi trong control file để tạo/clear log files.

### Bước 3: xác nhận

~~~sql
SELECT group#, thread#, sequence#, status, archived
FROM v$log
WHERE group# = 3;

SELECT group#, member, status
FROM v$logfile
WHERE group# = 3;
~~~

Kiểm tra file tồn tại, kích thước, quyền truy cập và alert log. Nếu path cũ không còn hợp lệ, thêm/thay member hoặc sửa cấu trúc log group theo quy trình được hỗ trợ.

### CLEAR LOGFILE không phải RESTORE

CLEAR LOGFILE không phục hồi nội dung redo cũ. Chỉ dùng khi redo trong group không còn cần cho recovery. Nếu redo vẫn cần để recover datafiles hoặc instance, clear sẽ làm mất khả năng dùng redo đó.

## 11. Mất group INACTIVE nhưng chưa archived

Nếu group INACTIVE nhưng ARCHIVED='NO', Oracle có thể không cho clear bằng lệnh thường vì redo chưa được archive. Chỉ khi đã đánh giá và chấp nhận mất redo đó mới cân nhắc CLEAR UNARCHIVED LOGFILE.

~~~sql
ALTER DATABASE CLEAR UNARCHIVED LOGFILE GROUP 3;
~~~

### Hậu quả của CLEAR UNARCHIVED LOGFILE

- Redo chưa archived trong group bị loại bỏ.
- Một số backup datafile có thể không còn recoverable qua redo bị mất.
- Recovery tới thời điểm cần sequence đó có thể không thực hiện được.
- Phải đánh giá backup strategy và thường cần tạo full backup database mới ngay sau khi xử lý.

Không chạy lệnh này chỉ để xóa lỗi ORA-00313/ORA-00312 mà chưa xác định group có cần cho recovery không. Nếu database không thể open hoặc cần media recovery, dừng và xác định chính xác SCN/sequence/backup availability trước khi clear.

### Sau khi clear unarchived group

1. Kiểm tra database open mode và alert log.
2. Kiểm tra các datafiles và archive destinations.
3. Chạy backup database mới theo chính sách.
4. Xác nhận backup hoàn tất và có thể restore.
5. Ghi lại redo sequence đã bị bỏ và tác động recovery.

CLEAR UNARCHIVED LOGFILE tự nó không có nghĩa luôn phải OPEN RESETLOGS. RESETLOGS phụ thuộc recovery path và trạng thái database, không chỉ việc clear một group inactive.

## 12. Mất toàn bộ members của group ACTIVE

ACTIVE có nghĩa redo trong group vẫn có thể cần cho instance recovery; nó không còn là group CURRENT nhưng checkpoint chưa đi qua hết nội dung redo cần thiết.

### Không clear group ACTIVE theo thói quen

Không dùng CLEAR LOGFILE cho group ACTIVE khi chưa chứng minh redo không còn cần. Oracle thường từ chối clear group cần cho crash recovery, với lỗi cho biết log cần cho recovery.

### Có thể làm group trở thành INACTIVE không?

Nếu database còn mở và group có thể được archive, DBA có thể:

1. Khắc phục storage/member nếu còn bản copy.
2. Archive log theo trạng thái và cấu hình.
3. Thực hiện checkpoint khi phù hợp.
4. Kiểm tra lại V$LOG xem group đã INACTIVE chưa.

Ví dụ thao tác:

~~~sql
ALTER SYSTEM CHECKPOINT;
~~~

Checkpoint có thể giúp đẩy dirty buffers và cập nhật checkpoint position, nhưng không bảo đảm một group bị mất hoàn toàn sẽ trở thành INACTIVE hoặc có thể archive. Nếu group đã mất và database gặp lỗi I/O/instance abort, cần theo recovery path phù hợp thay vì cố ép checkpoint.

### Nếu redo ACTIVE đã mất và không còn member tốt

Đánh giá:

- Group/sequence có archived copy không?
- Instance còn chạy hay đã abort?
- Datafiles đã checkpoint tới đâu?
- Có backup datafile/control file và archived logs đầy đủ không?
- Redo sequence bị mất có chứa thay đổi cần để recover datafiles không?

Nếu redo cần cho instance/media recovery nhưng không còn bản sao online/archived, có thể phải restore datafiles từ backup và recover tới điểm trước sequence bị mất, sau đó OPEN RESETLOGS. Mức độ mất dữ liệu phụ thuộc backup và redo còn lại.

## 13. Mất toàn bộ members của group CURRENT

CURRENT là group LGWR đang ghi redo. Nếu tất cả members của group CURRENT bị mất/hỏng, database có thể không tiếp tục ghi redo và instance có thể abort hoặc gặp lỗi nghiêm trọng. Không thể coi group này như một inactive group để clear đơn giản.

### Vì sao nguy hiểm?

Current online redo có thể chứa redo chưa được archive và cần để phục hồi các thay đổi đã commit hoặc đưa datafiles về trạng thái nhất quán. Nếu tất cả members mất, Oracle không còn bản online copy của redo stream đó.

### Các bước đánh giá

1. Xác nhận group/thread/sequence nào là CURRENT.
2. Xác nhận có member nào còn đọc được không.
3. Kiểm tra archived log cùng sequence hoặc backup archived log có tồn tại không.
4. Kiểm tra alert log và trạng thái instance.
5. Xác định datafile backup, control file backup và SCN/time có thể phục hồi.
6. Không chạy CLEAR UNARCHIVED LOGFILE cho CURRENT group như một thao tác chữa lỗi mặc định.

### Nếu còn member khác trong group

Nếu chỉ một member mất nhưng member khác vẫn tốt, xử lý như lỗi member: giữ database ổn định, thêm member thay thế và loại bỏ member hỏng khi Oracle cho phép.

### Nếu tất cả members của CURRENT group mất

Nếu database đã abort và redo không thể khôi phục từ bản online member khác, hướng phục hồi thường là:

- Restore control file/datafiles từ backup phù hợp nếu cần.
- Mount database.
- Recover bằng archived redo logs còn có thể áp dụng, dừng trước redo gap.
- Thực hiện incomplete recovery tới SCN/time trước điểm redo bị mất.
- OPEN RESETLOGS để tạo incarnation mới.
- Backup database ngay sau khi xác nhận hoạt động.

Ví dụ RMAN theo SCN:

~~~text
RMAN> STARTUP MOUNT;
RMAN> RUN {
  SET UNTIL SCN 123456789;
  RESTORE DATABASE;
  RECOVER DATABASE;
}
RMAN> ALTER DATABASE OPEN RESETLOGS;
~~~

SCN chỉ là ví dụ. Chọn SCN/time/sequence phải dựa trên redo thực sự có thể phục hồi, datafile checkpoint và yêu cầu nghiệp vụ. Nếu datafiles hiện tại không cần restore, quy trình có thể khác; DBA phải xác định trạng thái file và control file trước khi chạy.

### Incomplete recovery bằng SQL*Plus

Trong một số quy trình dùng backup control file:

~~~sql
STARTUP MOUNT;
RECOVER DATABASE UNTIL CANCEL USING BACKUP CONTROLFILE;
~~~

Apply archived logs theo thứ tự tới điểm cuối có thể phục hồi. Khi Oracle yêu cầu redo không còn, dừng recovery theo quy trình đã xác định và:

~~~sql
ALTER DATABASE OPEN RESETLOGS;
~~~

Không nhập CANCEL theo phỏng đoán. Cần biết sequence/SCN bị mất và chấp nhận rõ ràng điểm dữ liệu sẽ bị mất.

### Nếu database ở NOARCHIVELOG mode

Trong NOARCHIVELOG mode, không có archived redo logs để phục hồi media recovery theo chuỗi archive. Nếu online redo cần thiết đã mất, khả năng phục hồi thường bị giới hạn ở consistent backup gần nhất. Có thể phải restore consistent database backup và chấp nhận mất các thay đổi sau backup. Đây là lý do production database quan trọng thường dùng ARCHIVELOG mode cùng backup archived logs và kiểm tra restore định kỳ.

### Không thể tạo lại redo đã mất từ tên file

Tạo một file rỗng với cùng path hoặc kích thước không khôi phục redo contents. Oracle cần redo bytes hợp lệ với đúng sequence/thread/checkpoint. Nếu redo cần cho recovery đã mất, chỉ bản sao redo hợp lệ hoặc backup/archived copy mới có thể cung cấp nó.

## 14. CLEAR LOGFILE, DROP LOGFILE và ADD LOGFILE

Các lệnh này có mục đích khác nhau:

| Lệnh | Mục đích | Lưu ý |
| --- | --- | --- |
| CLEAR LOGFILE GROUP | Khởi tạo lại nội dung một group hiện có | Chỉ dùng khi redo không còn cần cho recovery; không clear CURRENT. |
| CLEAR UNARCHIVED LOGFILE GROUP | Clear group chưa archived | Có thể làm mất khả năng recover qua redo đó; thường cần full backup mới. |
| ADD LOGFILE MEMBER | Thêm một bản sao vào group hiện có | Dùng để khôi phục multiplexing. |
| DROP LOGFILE MEMBER | Loại một member khỏi group | Không bỏ member cuối cùng; cần thỏa điều kiện trạng thái group. |
| ADD LOGFILE GROUP | Tạo group mới | Bảo đảm số group phù hợp và mỗi group có multiplexing theo thiết kế. |
| DROP LOGFILE GROUP | Xóa group khỏi cấu trúc database | Không drop CURRENT/ACTIVE hoặc group cần recovery; không làm khi không đủ group thay thế. |

### Tạo group mới

~~~sql
ALTER DATABASE ADD LOGFILE GROUP 4 (
    '/u03/oradata/ORCL/redo04a.log',
    '/u04/oradata/ORCL/redo04b.log'
) SIZE 200M;
~~~

Trong OMF/ASM, có thể dùng cú pháp phù hợp để Oracle tự đặt tên file. Không tạo log group trên cùng failure domain nếu mục tiêu là multiplexing.

### Xóa group cũ

~~~sql
ALTER DATABASE DROP LOGFILE GROUP 4;
~~~

Chỉ drop group khi group không CURRENT, không ACTIVE và không cần cho recovery; Oracle sẽ kiểm tra các điều kiện và từ chối nếu không an toàn. Bảo đảm còn đủ log groups cho từng redo thread. Không xóa group cuối cùng hoặc làm gián đoạn RAC thread.

### Kiểm tra redo thread trong RAC

~~~sql
SELECT thread#, group#, sequence#, status, archived
FROM v$log
ORDER BY thread#, group#;

SELECT group#, thread#, member, status
FROM v$logfile
ORDER BY group#, member;
~~~

Mỗi enabled thread cần số online redo groups phù hợp. Khi thêm/drop group trong RAC, chỉ định thread khi cú pháp yêu cầu và phối hợp với cấu hình instance/thread.

## 15. RESETLOGS và database incarnation

OPEN RESETLOGS mở database sau một số tình huống recovery và tạo một redo branch mới (incarnation). Nó reset online redo log sequence và ghi nhận resetlogs SCN/time mới.

### Khi nào cần RESETLOGS?

Các trường hợp thường gặp:

- Incomplete recovery tới SCN/time/cancel.
- Recovery sử dụng backup control file theo quy trình yêu cầu resetlogs.
- Recreate control file với lựa chọn RESETLOGS.
- Một số tình huống phục hồi đặc biệt theo hướng dẫn Oracle.

Không phải mọi lỗi control file/redo log đều yêu cầu RESETLOGS. Ví dụ thay một member bị hỏng hoặc clear một inactive group không tự động có nghĩa phải open resetlogs.

### OPEN NORESETLOGS

Nếu recovery hoàn tất và database có thể tiếp tục cùng redo history, có thể mở theo cách không resetlogs trong các tình huống được Oracle cho phép. Quyết định phụ thuộc loại control file, recovery mode và redo history; không chọn NORESETLOGS chỉ vì muốn tránh incarnation mới.

### Kiểm tra incarnation

~~~sql
SELECT dbid,
       name,
       resetlogs_change#,
       resetlogs_time,
       prior_resetlogs_change#
FROM v$database;
~~~

Trong RMAN:

~~~text
RMAN> LIST INCARNATION OF DATABASE;
~~~

Sau RESETLOGS, RMAN ghi nhận incarnation mới. Khi phục hồi về incarnation cũ, có thể cần RESET DATABASE TO INCARNATION với đúng DBID/incarnation và catalog/control file metadata. Chỉ thực hiện theo kế hoạch recovery cụ thể.

### Backup sau RESETLOGS

Ngay sau khi database mở và đã xác nhận:

- Tạo full backup database mới.
- Backup control file và SPFILE.
- Backup archived redo logs theo policy.
- Kiểm tra RMAN LIST BACKUP và crosscheck theo quy trình.
- Xác nhận recovery catalog đồng bộ nếu có.
- Ghi lại resetlogs SCN/time và incarnation.

Không dựa vào backup trước RESETLOGS như thể nó thuộc cùng redo branch mà không xem xét incarnation.

## 16. Khi mất đồng thời nhiều thành phần

Trong sự cố storage, có thể mất cả SPFILE, control file và một hoặc nhiều redo members. Hãy khôi phục theo dependency:

~~~text
PFILE tối thiểu hoặc SPFILE backup
              |
              v
       STARTUP NOMOUNT
              |
              v
       RESTORE CONTROLFILE
              |
              v
        MOUNT DATABASE
              |
              v
 RESTORE/RECOVER DATAFILES
              |
              v
   OPEN [RESETLOGS as required]
              |
              v
  VERIFY + NEW BACKUP
~~~

### Mất SPFILE và control file

1. Tạo PFILE tối thiểu hoặc restore SPFILE từ autobackup.
2. Startup NOMOUNT.
3. Restore control file từ autobackup/backup piece.
4. Mount database.
5. Restore/recover datafiles và archived logs theo SCN có thể phục hồi.
6. Open RESETLOGS nếu recovery path yêu cầu.
7. Tạo backup mới và xác minh.

### Mất control file và online redo

Control file backup cung cấp metadata cấu trúc; archived redo/online redo hợp lệ cung cấp redo để recover. Restore control file không tái tạo nội dung online redo bị mất. Nếu sequence cần thiết đã mất, chọn recovery point trước redo gap và chấp nhận incomplete recovery theo nghiệp vụ.

### Mất cả SPFILE, control file và redo

PFILE tạm cho phép khởi động NOMOUNT; control file autobackup cho phép mount; datafile backup và archived redo còn lại quyết định điểm recover. Nếu không có redo cần thiết, không thể phục hồi các thay đổi chỉ tồn tại trong redo bị mất. Ghi rõ RPO thực tế và dữ liệu có thể mất trước khi mở database.

### Không dùng các file backup khác DBID

Backup control file, SPFILE và datafiles phải thuộc đúng database/DBID và incarnation tương ứng. Không restore control file của một database khác chỉ vì DB_NAME giống nhau. Xác nhận DBID, DB_NAME, DB_UNIQUE_NAME và resetlogs history.

## 17. Phòng ngừa: multiplexing và backup

Phục hồi nhanh nhất thường là tránh để một lỗi đơn lẻ làm mất tất cả bản sao.

### Control file

- Cấu hình nhiều control file copies trong CONTROL_FILES.
- Đặt copies trên failure domains khác nhau.
- Bật CONTROLFILE AUTOBACKUP trong RMAN.
- Backup control file sau thay đổi cấu trúc quan trọng.
- Lưu DBID, DB_NAME, DB_UNIQUE_NAME và path trong tài liệu recovery.
- Kiểm tra control file restore định kỳ trên môi trường thử nghiệm.

RMAN:

~~~text
RMAN> CONFIGURE CONTROLFILE AUTOBACKUP ON;
RMAN> SHOW ALL;
RMAN> BACKUP DATABASE PLUS ARCHIVELOG;
RMAN> LIST BACKUP OF CONTROLFILE;
~~~

### SPFILE

- Backup SPFILE rõ ràng trong RMAN.
- Bật control file autobackup để SPFILE có thể được lưu cùng autobackup khi cấu hình hỗ trợ.
- Export PFILE text định kỳ để có bản cấu hình dễ kiểm tra.
- Lưu bản sao ở storage ngoài database server.
- Bảo vệ permission vì parameter file có thể chứa thông tin nhạy cảm.

~~~text
RMAN> BACKUP SPFILE;
RMAN> LIST BACKUP OF SPFILE;
~~~

PFILE snapshot:

~~~sql
CREATE PFILE = '/backup/initORCL_snapshot.ora' FROM SPFILE;
~~~

### Online redo log

- Multiplex mỗi group với ít nhất hai members nếu kiến trúc yêu cầu.
- Đặt members trên các disk/device/failure domains khác nhau.
- Dùng ASM redundancy hoặc storage protection phù hợp.
- Giám sát lỗi I/O, alert log và trạng thái V$LOGFILE.
- Giữ đủ log groups cho mỗi thread; tránh log switch quá thường xuyên.
- Đảm bảo archived logs được backup và retention đủ dài.

### Archived redo log

- Dùng ARCHIVELOG mode cho database cần media recovery tới thời điểm gần hiện tại.
- Kiểm tra archive destinations, FRA space và archive failures.
- Backup archived logs theo chính sách và xác minh backup.
- Không xóa archived logs chỉ dựa vào file age; dùng RMAN retention/deletion policy.

### Test restore

Backup chỉ đáng tin khi đã thử restore. Thực hiện định kỳ:

- Restore control file từ autobackup.
- Restore SPFILE/PFILE.
- Restore database và recover archived logs trên clone.
- Kiểm tra OPEN RESETLOGS/incarnation nếu scenario yêu cầu.
- Đo thời gian restore và xác nhận RTO/RPO.

## 18. Giám sát và kiểm tra sau phục hồi

Sau khi database mở, không dừng ở thông báo OPEN. Xác minh toàn bộ đường phục vụ ứng dụng và backup.

### Database status

~~~sql
SELECT name, open_mode, log_mode, database_role,
       resetlogs_change#, resetlogs_time
FROM v$database;

SELECT instance_name, status, database_status
FROM v$instance;
~~~

### Datafile status

~~~sql
SELECT file#, name, status, enabled, checkpoint_change#
FROM v$datafile
ORDER BY file#;

SELECT file#, error, change#, time
FROM v$recover_file;
~~~

V$RECOVER_FILE có thể không còn hàng khi không có file cần recovery. Kiểm tra alert log và RMAN validation theo kế hoạch.

### Control file và redo

~~~sql
SELECT name, status
FROM v$controlfile;

SELECT group#, thread#, sequence#, status, archived, members
FROM v$log
ORDER BY thread#, group#;

SELECT group#, member, status
FROM v$logfile
ORDER BY group#, member;
~~~

### Archive status

~~~sql
ARCHIVE LOG LIST;

SELECT thread#, sequence#, first_time, next_time, archived, applied, status
FROM v$archived_log
ORDER BY thread#, sequence#;
~~~

Trong Data Guard, kiểm tra thêm transport lag/apply lag, standby role và broker status. Không coi archived log local là bằng chứng standby đã apply redo.

### RMAN

~~~text
RMAN> CROSSCHECK BACKUP;
RMAN> LIST BACKUP SUMMARY;
RMAN> REPORT NEED BACKUP;
RMAN> BACKUP DATABASE PLUS ARCHIVELOG;
~~~

CROSSCHECK đồng bộ repository với backup pieces thực tế; không xóa file backup. DELETE EXPIRED hoặc DELETE OBSOLETE là thao tác khác và cần retention policy/approval riêng.

### Ứng dụng và dữ liệu

- Xác nhận listener/service đăng ký và ứng dụng kết nối được.
- Kiểm tra PDB đã open đúng trạng thái.
- Kiểm tra invalid objects và job failures.
- Chạy smoke tests cho nghiệp vụ quan trọng.
- Đối chiếu dữ liệu theo recovery point đã công bố.
- Kiểm tra sequence, scheduler, replication và downstream integrations.

## 19. Lỗi thường gặp khi phục hồi

| Lỗi | Ý nghĩa thường gặp | Hướng xử lý |
| --- | --- | --- |
| ORA-00205 | Oracle không xác định được control file | Kiểm tra CONTROL_FILES, file path, ASM/disk và alert log. |
| ORA-00210 | Không mở được control file được chỉ định | Kiểm tra file tồn tại, permission, storage và bản copy còn tốt. |
| ORA-00227 | Corrupt block trong control file | Dùng bản control file multiplexed/backup hợp lệ; xác định mức hỏng. |
| ORA-01103 | Database name trong control file không khớp DB_NAME | Kiểm tra đúng control file/parameter file và DBID; không đổi DB_NAME tùy tiện. |
| ORA-00312 | Thông báo tên file online log member liên quan lỗi | Xác định group/member qua V$LOGFILE và alert log. |
| ORA-00313 | Không mở được một hoặc nhiều online log members | Phân biệt mất một member với toàn bộ group; kiểm tra path, storage và quyền. |
| ORA-00368 | Checksum error trong redo log block | Kiểm tra member còn lại/archived redo và recovery options. |
| ORA-01624 | Log cần cho crash recovery | Không clear/drop; tìm member/redo hợp lệ hoặc restore/recover theo backup. |
| ORA-01623 | Log hiện là current và không thể drop | Switch/recover theo trạng thái; không drop current group. |
| ORA-00313/ORA-00312 lặp lại | Group/member mất hoặc storage I/O failure | Kiểm tra OS/ASM, multiplexed members và V$LOG status. |
| ORA-32001 | Yêu cầu ghi SPFILE nhưng instance không dùng SPFILE | Startup bằng PFILE hoặc tạo SPFILE theo kế hoạch. |
| ORA-01078 | Lỗi xử lý initialization parameters lúc startup | Đọc alert log, kiểm tra PFILE/SPFILE và parameter values. |
| RMAN-06172 | Không tìm thấy autobackup phù hợp hoặc không có backup piece theo yêu cầu | Xác nhận DBID, format, path, date, device type và catalog. |
| RMAN-06054 | RMAN yêu cầu archived log chưa biết trong repository | Tìm log sequence/backup piece, catalog log hoặc xác định redo gap. |

Mã lỗi có thể đi kèm lỗi OS/ASM hoặc lỗi RMAN khác. Ghi nhận đầy đủ stack, alert log và command; không chỉ xử lý dòng lỗi đầu tiên.

## 20. Bài thực hành: kiểm tra backup và diễn tập phục hồi

Bài thực hành cần một database lab riêng, RMAN backup destination riêng và quyền SYSDBA. Không xóa control file, SPFILE hoặc online redo log trên database dùng chung để mô phỏng sự cố.

### Bước 1: ghi nhận cấu hình hiện tại

~~~sql
SELECT name, dbid, open_mode, log_mode, database_role
FROM v$database;

SELECT instance_name, host_name, status
FROM v$instance;

SHOW PARAMETER spfile;
SHOW PARAMETER control_files;

SELECT group#, thread#, sequence#, status, archived, members
FROM v$log
ORDER BY thread#, group#;

SELECT group#, member, status
FROM v$logfile
ORDER BY group#, member;
~~~

Lưu DBID, DB_NAME, CONTROL_FILES, SPFILE path và các log groups để dùng khi diễn tập.

### Bước 2: bật control file autobackup

Trong RMAN:

~~~text
RMAN> CONFIGURE CONTROLFILE AUTOBACKUP ON;
RMAN> SHOW ALL;
~~~

Nếu dùng disk path riêng:

~~~text
RMAN> CONFIGURE CONTROLFILE AUTOBACKUP FORMAT FOR DEVICE TYPE DISK
      TO '/backup/ORCL/%F';
~~~

Đảm bảo path tồn tại, có dung lượng và Oracle server process có quyền ghi. Với ASM/SBT, dùng cấu hình device type phù hợp.

### Bước 3: tạo backup

~~~text
RMAN> BACKUP DATABASE PLUS ARCHIVELOG;
RMAN> BACKUP SPFILE;
RMAN> LIST BACKUP OF CONTROLFILE;
RMAN> LIST BACKUP OF SPFILE;
RMAN> LIST BACKUP OF ARCHIVELOG ALL;
~~~

Autobackup có thể chứa control file và SPFILE theo cấu hình; BACKUP SPFILE riêng giúp có bản backup tường minh. Xác nhận RMAN báo hoàn tất và backup pieces có thể truy cập.

### Bước 4: kiểm tra PFILE snapshot

~~~sql
CREATE PFILE = '/backup/initORCL_lab.ora' FROM SPFILE;
~~~

Đọc PFILE snapshot ở server và bảo vệ permission. Ghi chú path là server-side, không phải client path.

### Bước 5: kiểm tra multiplexing redo

~~~sql
SELECT l.group#,
       l.thread#,
       l.status,
       l.archived,
       f.member
FROM v$log l
JOIN v$logfile f ON f.group# = l.group#
ORDER BY l.thread#, l.group#, f.member;
~~~

Trong lab có thể thêm một member trên storage khác:

~~~sql
ALTER DATABASE ADD LOGFILE MEMBER
    '/u03/oradata/ORCL/redo01b.log'
TO GROUP 1;
~~~

Thay group/path theo cấu hình thật. Xác nhận số members sau DDL. Không thêm path không tồn tại hoặc trùng failure domain.

### Bước 6: diễn tập mất một member trên clone

1. Clone/restore database lab từ backup.
2. Xác định group có ít nhất một member khỏe.
3. Dừng instance nếu cần thao tác OS trên file trong clone.
4. Mô phỏng member bị thiếu bằng cách cô lập file trên clone theo quy trình lab.
5. Startup và xác nhận lỗi member trong alert log/V$LOGFILE.
6. ADD LOGFILE MEMBER mới, rồi DROP LOGFILE MEMBER lỗi khi Oracle cho phép.
7. Kiểm tra database và multiplexing.

Không thực hiện bước mô phỏng bằng cách xóa file trên production.

### Bước 7: diễn tập restore control file trên clone

1. Dùng bản clone riêng, không đụng database nguồn.
2. Xác nhận DBID và autobackup format.
3. Dùng PFILE tạm startup NOMOUNT.
4. RMAN restore control file từ autobackup.
5. Mount database.
6. Restore/recover theo trạng thái clone và backup.
7. Open RESETLOGS nếu recovery bằng backup control file yêu cầu.
8. Kiểm tra incarnation và backup mới.

Ví dụ chuỗi RMAN minh họa:

~~~text
RMAN> SET DBID 1234567890;
RMAN> STARTUP FORCE NOMOUNT PFILE='/backup/initORCL_lab.ora';
RMAN> RESTORE CONTROLFILE FROM AUTOBACKUP;
RMAN> ALTER DATABASE MOUNT;
RMAN> RESTORE DATABASE;
RMAN> RECOVER DATABASE;
RMAN> ALTER DATABASE OPEN RESETLOGS;
~~~

DBID, PFILE, backup location và database name trong lab phải khớp. Nếu chỉ restore control file mà datafiles hiện tại còn hợp lệ, đánh giá recovery requirement thay vì chạy RESTORE DATABASE máy móc.

### Bước 8: diễn tập SPFILE restore

Trên clone khác hoặc sau khi đã tạo snapshot có thể phục hồi:

~~~text
RMAN> SET DBID 1234567890;
RMAN> STARTUP FORCE NOMOUNT PFILE='/backup/initORCL_minimal.ora';
RMAN> RESTORE SPFILE FROM AUTOBACKUP;
~~~

Kiểm tra SPFILE path và parameter values sau startup có kiểm soát. Không làm mất file parameter duy nhất của lab trước khi xác nhận backup restore được.

### Bước 9: kiểm tra kết quả và backup lại

~~~sql
SELECT name, open_mode, log_mode, resetlogs_change#, resetlogs_time
FROM v$database;

SELECT name, status FROM v$controlfile;

SELECT group#, thread#, sequence#, status, archived
FROM v$log
ORDER BY thread#, group#;
~~~

RMAN:

~~~text
RMAN> LIST INCARNATION OF DATABASE;
RMAN> BACKUP DATABASE PLUS ARCHIVELOG;
RMAN> BACKUP SPFILE;
~~~

### Bước 10: ghi nhận diễn tập

Ghi lại:

- Scenario và file/group bị mô phỏng.
- DBID, incarnation và backup piece được dùng.
- Recovery point/SCN và archived sequence cuối cùng.
- Thời gian restore/recover (RTO).
- Dữ liệu có thể mất hoặc redo gap (RPO).
- Các lỗi và bước xử lý.
- Kết quả application smoke test.
- Thời điểm backup mới hoàn tất.

## 21. Câu hỏi tự kiểm tra

1. **Control file lưu gì?** Metadata database, datafiles, redo groups, checkpoint, archive và backup information.
2. **SPFILE lưu gì?** Initialization parameters dùng khi startup instance.
3. **Online redo log dùng để làm gì?** Ghi redo cho instance recovery và media recovery.
4. **Multiplex control files có tác dụng gì?** Bảo vệ khi một control file copy hoặc storage path bị mất.
5. **Mất một control file copy khác gì mất tất cả?** Một copy còn tốt có thể tạo lại bản mất; mất tất cả cần restore/recreate control file.
6. **Tại sao cần DBID khi restore autobackup không có catalog?** RMAN dùng DBID để tìm đúng autobackup của database.
7. **Vì sao startup NOMOUNT trước restore control file?** Instance cần parameter file nhưng chưa cần control file để khởi tạo.
8. **Sau restore backup control file có thể cần gì?** Mount, recover datafiles và OPEN RESETLOGS theo recovery path.
9. **SPFILE mất nhưng instance còn chạy thì làm gì trước?** Tạo PFILE từ MEMORY hoặc lưu cấu hình trước khi shutdown.
10. **SCOPE nào không liên quan tới SPFILE recovery?** Không áp dụng; SPFILE được khôi phục như file cấu hình, không phải bằng ALTER SYSTEM SCOPE.
11. **Một redo group có nhiều members nghĩa là gì?** Các members là bản sao của cùng redo stream.
12. **Mất một member khi còn member tốt có cần incomplete recovery không?** Thường không; thay member lỗi để khôi phục multiplexing.
13. **V$LOG STATUS CURRENT có ý nghĩa gì?** Group đang được LGWR ghi cho thread.
14. **ACTIVE khác INACTIVE thế nào?** ACTIVE redo còn cần cho instance recovery; INACTIVE không còn cần theo checkpoint hiện tại.
15. **CLEAR LOGFILE có phục hồi redo cũ không?** Không; nó khởi tạo lại group và bỏ nội dung redo cũ.
16. **Khi nào cần CLEAR UNARCHIVED LOGFILE?** Khi group đủ điều kiện nhưng chưa archived và DBA chấp nhận hậu quả mất redo/recoverability.
17. **Tại sao không clear CURRENT group?** Nó đang được ghi và có thể chứa redo cần thiết; mất toàn bộ current redo cần recovery plan khác.
18. **Online redo log có được RMAN backup như datafile không?** Không theo cách thông thường; cần bảo toàn online members và backup archived logs.
19. **Mất ACTIVE group cần làm gì?** Xác định redo còn cần cho crash recovery, archived copy và backup; không clear theo thói quen.
20. **Mất CURRENT group không có bản sao có thể dẫn tới gì?** Restore/recover tới điểm trước redo gap và OPEN RESETLOGS, có thể mất thay đổi sau điểm đó.
21. **CLEAR UNARCHIVED LOGFILE có luôn yêu cầu RESETLOGS không?** Không; RESETLOGS phụ thuộc recovery path, không chỉ lệnh clear.
22. **OPEN RESETLOGS làm gì?** Tạo database incarnation/redo branch mới và reset online redo sequence.
23. **Sau RESETLOGS cần làm gì?** Xác nhận incarnation, backup database/control file/SPFILE và archived logs mới.
24. **Vì sao phải thử restore?** Backup chưa được restore thử chưa chứng minh có thể đáp ứng RTO/RPO.
25. **Mất SPFILE và control file đồng thời thì thứ tự nào?** Khôi phục parameter file/PFILE, startup NOMOUNT, restore control file, mount, restore/recover datafiles rồi open theo yêu cầu.

Khi mất control file, SPFILE hoặc online redo log, hãy phân loại chính xác file nào mất, còn bản sao nào và redo có còn cần cho recovery hay không. SPFILE có thể được tái tạo từ memory/PFILE/RMAN; control file được restore từ autobackup hoặc recreate trong tình huống cuối cùng; online redo phải được bảo toàn qua multiplexing hoặc clear chỉ khi group không còn cần cho recovery. Mất CURRENT/ACTIVE redo toàn bộ có thể buộc incomplete recovery và OPEN RESETLOGS. Sau mọi recovery, kiểm tra database/instance, datafiles, redo, archive, incarnation, ứng dụng và tạo backup mới.

## 7. Khôi phục SPFILE

SPFILE chứa initialization parameters, không chứa user data. Mất SPFILE không đồng nghĩa datafiles bị mất. Cách phục hồi phụ thuộc instance còn chạy hay đã dừng và có bản PFILE/RMAN backup hay không.

### Tình huống A: instance vẫn đang chạy

Nếu instance vẫn hoạt động, các parameter đã được nạp trong memory. Có thể tạo PFILE từ memory:

~~~sql
CREATE PFILE = '/tmp/initORCL_recovered.ora' FROM MEMORY;
~~~

PFILE được ghi ở server filesystem. Kiểm tra file, bảo vệ permission và xác nhận các giá trị quan trọng như DB_NAME, CONTROL_FILES, DB_UNIQUE_NAME, memory, processes, archive destinations và cluster settings.

Sau đó tạo lại SPFILE:

~~~sql
CREATE SPFILE = '/u01/app/oracle/product/dbhome_1/dbs/spfileORCL.ora'
FROM PFILE = '/tmp/initORCL_recovered.ora';
~~~

Đường dẫn là ví dụ cho filesystem Oracle Home; trong RAC/ASM, SPFILE thường nằm ở shared location/ASM theo cấu hình Clusterware. Xác nhận vị trí đúng với môi trường.

Có thể tạo PFILE từ SPFILE còn bản sao khác:

~~~sql
CREATE PFILE = '/tmp/initORCL.ora' FROM SPFILE;
~~~

### Không shutdown trước khi lưu cấu hình nếu instance còn chạy

Nếu SPFILE mất nhưng instance còn chạy, đừng shutdown vội khi chưa có bản PFILE/backup cấu hình. Sau shutdown, instance có thể không startup lại được nếu không có parameter file hợp lệ.

### Tình huống B: instance đã dừng, có PFILE backup

Dùng PFILE backup để startup NOMOUNT:

~~~sql
STARTUP NOMOUNT PFILE = '/backup/initORCL.ora';
~~~

Sau đó tạo SPFILE ở vị trí chuẩn:

~~~sql
CREATE SPFILE FROM PFILE = '/backup/initORCL.ora';
~~~

Shutdown/startup lại bằng SPFILE theo quy trình nếu cần xác nhận instance đọc đúng file:

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP;
~~~

Không thực hiện restart nếu database đang phục vụ production mà chưa có maintenance plan.

### Tình huống C: SPFILE mất, có RMAN autobackup

Nếu instance không có SPFILE, cần PFILE tạm tối thiểu để startup NOMOUNT và restore SPFILE. Khi không có recovery catalog, đặt DBID trước:

~~~text
RMAN> SET DBID 1234567890;
RMAN> STARTUP FORCE NOMOUNT PFILE='/tmp/initORCL_minimal.ora';
RMAN> RESTORE SPFILE FROM AUTOBACKUP;
~~~

PFILE tối thiểu cần có DB_NAME và các tham số cần để instance khởi tạo; chi tiết phụ thuộc database. Nếu autobackup format hoặc path tùy chỉnh, đặt CONTROLFILE AUTOBACKUP FORMAT đúng trước khi RESTORE SPFILE.

Có thể restore trực tiếp ra PFILE để kiểm tra:

~~~text
RMAN> RESTORE SPFILE TO PFILE '/tmp/initORCL_from_backup.ora'
      FROM AUTOBACKUP;
~~~

Sau khi kiểm tra PFILE, tạo SPFILE ở vị trí mong muốn bằng SQL CREATE SPFILE hoặc dùng RMAN restore SPFILE trực tiếp theo môi trường. Nếu dùng ASM, xác nhận tên alias/disk group và quy trình Clusterware.

### Tình huống D: SPFILE backup piece đã biết

Nếu biết backup piece chứa SPFILE:

~~~text
RMAN> RESTORE SPFILE FROM '/backup/ORCL/spfile_backup_piece.bkp';
~~~

Nếu không dùng catalog và không tìm được autobackup, DBID và backup piece path là thông tin cần thiết. Với SBT/cloud, cần cấu hình media manager/channel để RMAN đọc backup.

### Xác nhận SPFILE sau restore

~~~sql
SHOW PARAMETER spfile;

SELECT name, value
FROM v$parameter
WHERE name IN (
    'db_name',
    'db_unique_name',
    'control_files',
    'memory_target',
    'processes',
    'remote_login_passwordfile'
)
ORDER BY name;
~~~

V$PARAMETER hiển thị giá trị runtime; SHOW PARAMETER SPFILE cho biết instance đang đọc SPFILE nào. Nếu restore SPFILE trong khi instance đang chạy bằng PFILE, phải restart có kiểm soát để instance dùng SPFILE mới.

## 8. Khôi phục online redo log: hiểu group và member

Online redo log được tổ chức thành groups. Một group có thể có nhiều members; tất cả members trong cùng group là các bản sao tương đương của cùng redo stream.

~~~text
Thread 1
  Group 1 (CURRENT)
    member /redo/redo01a.log
    member /redo_mirror/redo01b.log
  Group 2 (ACTIVE)
    member /redo/redo02a.log
    member /redo_mirror/redo02b.log
  Group 3 (INACTIVE)
    member /redo/redo03a.log
    member /redo_mirror/redo03b.log
~~~

### Mất một member

Nếu một member mất nhưng ít nhất một member khác trong group còn đọc/ghi được, database có thể tiếp tục hoạt động. Thay member bị lỗi càng sớm càng tốt để khôi phục redundancy.

### Mất toàn bộ members của một group

Đây là tình huống khác hẳn mất một member. Khả năng phục hồi phụ thuộc group là CURRENT, ACTIVE hay INACTIVE, đã archived chưa, redo có còn cần cho instance recovery không và database đang ở trạng thái nào.

### Kiểm tra trạng thái

~~~sql
SELECT l.group#,
       l.thread#,
       l.sequence#,
       l.status,
       l.archived,
       f.member,
       f.status AS member_status
FROM v$log l
JOIN v$logfile f
  ON f.group# = l.group#
ORDER BY l.thread#, l.group#, f.member;
~~~

STATUS ở V$LOGFILE có thể là NULL khi member hoạt động bình thường; trạng thái INVALID/STALE/DELETED cần điều tra. Đối chiếu V$LOG group status và alert log.

### Online redo không giống archived redo

- Online redo log là các group hiện đang được database sử dụng để ghi redo.
- Archived redo log là bản đã archive của redo group đã hoàn tất.
- RMAN backup archived logs có thể giúp media recovery.
- Online redo log files không được backup như datafiles theo cách thông thường; không giả định RESTORE DATABASE sẽ tái tạo nội dung redo log hiện tại.

Giữ archived logs và backup hợp lệ là điều kiện quan trọng để phục hồi khi online redo group bị mất.
