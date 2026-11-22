# Backup database, tablespace, datafile, control file và SPFILE
Một chiến lược backup Oracle phải bảo vệ được cả dữ liệu lẫn metadata cần để khởi động và phục hồi database. Backup toàn database giúp khôi phục hệ thống sau sự cố lớn; backup tablespace hoặc datafile hỗ trợ phục hồi có phạm vi nhỏ hơn; control file giữ cấu trúc database và thông tin recovery; SPFILE lưu cấu hình khởi động instance. Archived redo logs cho phép đưa dữ liệu từ thời điểm backup tiến tới SCN hoặc thời điểm mục tiêu.

Oracle Recovery Manager (RMAN) là công cụ chính để quản lý backup và recovery. RMAN hiểu cấu trúc database, theo dõi backup metadata, hỗ trợ backup online trong ARCHIVELOG mode, kiểm tra backup và tự chọn các backup/redo cần thiết khi restore. Bài này tập trung vào RMAN; các ví dụ user-managed chỉ được dùng để giải thích vai trò file và trường hợp cần thiết.

Nội dung dùng Oracle Database 19c làm mốc, gồm:
- Thành phần cần backup và vai trò của từng thành phần.
- Full database, incremental, tablespace và datafile backup.
- Control file, SPFILE, autobackup và backup metadata.
- Archived redo log backup, FRA và retention policy.
- RMAN channel, format, tag, compression và encryption.
- Kiểm tra backup, restore preview, validate và crosscheck.
- Restore/recover toàn database, tablespace, datafile, control file và SPFILE.
- CDB/PDB backup, chiến lược vận hành, lỗi thường gặp và lab.

Cú pháp, option và khả năng của RMAN có thể khác theo release, edition, cấu hình storage, RAC và CDB/PDB. Luôn kiểm tra RMAN Reference đúng phiên bản và diễn tập restore trên môi trường riêng trước khi thay đổi production.

## 1. Vì sao cần backup nhiều loại file?

Một Oracle database không chỉ là tập datafile. Để khôi phục database, cần bảo vệ các thành phần liên quan:

| Thành phần | Nội dung | Vai trò khi recovery |
| --- | --- | --- |
| Datafiles | Table, index, undo và dữ liệu database | Nguồn dữ liệu chính cần restore |
| Control files | Cấu trúc database, tên file, checkpoint, redo history | Mount database và điều phối recovery |
| SPFILE/PFILE | Tham số khởi động instance | Khởi động đúng cấu hình |
| Online redo logs | Redo gần nhất của các redo thread | Instance recovery và một số media recovery |
| Archived redo logs | Bản lưu redo log đã archive | Recover từ backup tới SCN/time mục tiêu |
| Password file | Thông tin xác thực SYSDBA/SYSOPER từ xa | Kết nối quản trị khi cần |
| RMAN repository/catalog | Metadata backup, incarnation, file và log | Tìm backup và lập kế hoạch restore |
| Wallet/keystore | Khóa mã hóa và certificate tùy chức năng | Mở dữ liệu backup/database được mã hóa hoặc kết nối bảo mật |

RMAN backup database thường bao gồm các datafiles thuộc phạm vi database. Control file và SPFILE cần được bảo vệ riêng hoặc qua control file autobackup. Archived redo logs phải được backup theo chiến lược recovery. Online redo logs không được backup như một file thông thường đang hoạt động; phải bảo vệ theo cơ chế Oracle hỗ trợ và giữ multiplexing/standby phù hợp.

### 1.1. Backup và recovery là một cặp

Backup thành công chỉ chứng minh công việc tạo backup hoàn tất theo công cụ. Nó chưa chứng minh có thể phục hồi database trong RTO/RPO yêu cầu.

Một kế hoạch thực tế cần trả lời:
- Có backup nào đủ mới để đạt RPO?
- Có đủ archived redo logs từ backup tới target SCN không?
- Có control file/SPFILE hoặc recovery catalog để tìm backup không?
- Có thể khôi phục tới một host/storage khác không?
- Có đủ wallet/key để mở backup được mã hóa không?
- Restore/recover mất bao lâu?
- Ai có quyền thực hiện và xác nhận ứng dụng hoạt động sau recovery?

## 2. RMAN và repository

RMAN (Recovery Manager) là utility Oracle dùng để backup, restore, recover và quản lý metadata.

### 2.1. Kết nối RMAN

Trên máy có Oracle software và quyền quản trị phù hợp:

~~~bash
rman target /
~~~

Hoặc kết nối target bằng credential theo chính sách bảo mật:

~~~bash
rman target sys@ORCL
~~~

Không ghi password trực tiếp trong command line, script hoặc log chia sẻ. Có thể dùng recovery catalog:

~~~bash
rman target / catalog rman_user@RCVCAT
~~~

### 2.2. Control file repository

Nếu không dùng recovery catalog, RMAN lưu metadata backup trong control file của target database. Control file có thể tái sử dụng các record cũ theo CONTROL_FILE_RECORD_KEEP_TIME và giới hạn dung lượng record section.

Vì vậy phải backup control file thường xuyên. Nếu control file mất và không có recovery catalog, việc tìm backup có thể cần control file autobackup và DBID.

### 2.3. Recovery catalog

Recovery catalog là schema repository riêng, lưu metadata RMAN lâu dài hơn và có thể quản lý nhiều target database. Nó không chứa datafile backup; backup pieces vẫn nằm trên disk, tape hoặc media manager.

Recovery catalog giúp:
- Giữ lịch sử backup lâu hơn record trong control file.
- Quản lý nhiều database.
- Hỗ trợ một số thao tác restore/recovery khi control file bị mất.
- Theo dõi incarnation và backup metadata.

Recovery catalog cũng cần được backup và bảo vệ. Không coi catalog là bản thay thế cho control file hoặc backup datafiles.

### 2.4. Xem cấu hình RMAN

Trong RMAN:

~~~text
SHOW ALL;
SHOW RETENTION POLICY;
SHOW CONTROLFILE AUTOBACKUP;
SHOW DEVICE TYPE;
SHOW CHANNEL;
~~~

Cấu hình được lưu trong control file repository hoặc recovery catalog theo môi trường. Trước khi thay đổi, lưu lại output SHOW ALL để có thể khôi phục cấu hình trước đó.

## 3. Backup toàn database

Backup toàn database là nền tảng của chiến lược backup. Với database ở ARCHIVELOG mode, RMAN có thể backup khi database đang mở.

### 3.1. Backup database cơ bản

~~~text
BACKUP DATABASE;
~~~

RMAN backup các datafiles cần thiết của database theo device/configuration hiện tại. Backup mặc định thường tạo backup set, trừ khi chỉ định AS COPY.

Có thể gắn tag để dễ nhận diện:

~~~text
BACKUP DATABASE TAG 'WEEKLY_FULL';
~~~

Tag là nhãn do DBA chọn, không phải backup ID duy nhất. RMAN vẫn dùng backup key, completion time, checkpoint SCN và metadata để xác định backup.

### 3.2. Backup database và archived logs

Một lệnh thường dùng:

~~~text
BACKUP DATABASE PLUS ARCHIVELOG;
~~~

Lệnh yêu cầu RMAN backup archived redo logs cần thiết cùng database. RMAN thực hiện archive log switching và backup log theo trình tự của lệnh để bảo đảm redo cần cho online backup được thu thập.

Để tăng độ tin cậy, kiểm tra output job, backup list và archived log coverage sau khi chạy. Nếu backup destination hoặc FRA đầy, job có thể thất bại giữa chừng; cần xác định phần nào đã hoàn thành và phần nào phải chạy lại.

### 3.3. Include current control file

~~~text
BACKUP DATABASE INCLUDE CURRENT CONTROLFILE;
~~~

Lệnh này đưa current control file vào backup set cùng database. Nếu CONTROLFILE AUTOBACKUP đã bật, RMAN còn có thể tạo autobackup riêng sau backup. Cần hiểu output thực tế và cấu hình để tránh nghĩ rằng chỉ có một bản control file.

### 3.4. Full backup và level 0 incremental

Trong RMAN, full backup và incremental level 0 không hoàn toàn đồng nghĩa:
- Full backup có thể dùng làm cơ sở restore, nhưng không làm parent cho incremental level 1.
- Incremental level 0 là baseline cho incremental level 1.

Ví dụ:

~~~text
BACKUP INCREMENTAL LEVEL 0 DATABASE TAG 'L0_BASE';
~~~

Nếu dùng chiến lược incremental, cần giữ level 0 cùng các level 1 và archived redo cần thiết theo retention policy.

## 4. Incremental backup

Incremental backup chỉ lưu các block thay đổi kể từ incremental backup level thấp hơn hoặc mốc tương ứng. Nó giúp giảm thời gian và dung lượng backup khi database lớn và lượng thay đổi mỗi ngày nhỏ.

### 4.1. Level 0

~~~text
BACKUP INCREMENTAL LEVEL 0 DATABASE;
~~~

Level 0 chứa các block được RMAN xem là cần thiết để tạo baseline incremental. Đây là điểm bắt đầu cho chuỗi level 1.

### 4.2. Level 1 differential

~~~text
BACKUP INCREMENTAL LEVEL 1 DATABASE;
~~~

Mặc định, level 1 là differential: backup các block thay đổi kể từ incremental backup gần nhất ở level 1 hoặc level 0 phù hợp.

### 4.3. Level 1 cumulative

~~~text
BACKUP INCREMENTAL LEVEL 1 CUMULATIVE DATABASE;
~~~

Cumulative level 1 backup các block thay đổi kể từ level 0 gần nhất. Nó thường lớn hơn differential khi có nhiều lần chạy nhưng có thể đơn giản hóa chuỗi incremental cần áp dụng lúc recovery.

### 4.4. So sánh

| Loại | Phạm vi block | Ưu điểm | Trade-off |
| --- | --- | --- | --- |
| Full backup | Các block cần cho full datafile backup | Dễ quản lý restore | Thời gian/dung lượng lớn |
| Incremental level 0 | Baseline incremental | Làm parent cho level 1 | Thường gần full về khối lượng |
| Level 1 differential | Thay đổi từ level 1/level 0 gần nhất | Backup nhỏ hơn trong nhiều workload | Restore có thể cần nhiều incremental |
| Level 1 cumulative | Thay đổi từ level 0 gần nhất | Ít level 1 hơn cần apply | Mỗi lần có thể lớn hơn |

### 4.5. Block Change Tracking

Block Change Tracking (BCT) giúp RMAN xác định block thay đổi mà không phải scan toàn bộ datafile khi incremental backup. Ví dụ:

~~~sql
ALTER DATABASE ENABLE BLOCK CHANGE TRACKING
USING FILE '/u03/oradata/ORCL/bct01.ctf';
~~~

Kiểm tra:

~~~sql
SELECT status, filename, bytes
FROM v$block_change_tracking;
~~~

BCT có overhead và cần file lưu trữ riêng. Nếu file bị mất, RMAN có thể tiếp tục incremental backup bằng cách đọc nhiều block hơn; BCT không phải dữ liệu duy nhất để recover database.

## 5. Backup tablespace

Tablespace backup giúp bảo vệ hoặc phục hồi một nhóm datafiles có liên quan. RMAN backup các datafiles thuộc tablespace.

### 5.1. Backup một tablespace

~~~text
BACKUP TABLESPACE users TAG 'USERS_WEEKLY';
~~~

Có thể backup nhiều tablespace:

~~~text
BACKUP TABLESPACE users, app_data, app_index;
~~~

Tên tablespace phải đúng với database hiện tại. Dùng REPORT SCHEMA để xem cấu trúc database trước khi chạy.

### 5.2. Xem tablespace và datafile

~~~sql
SELECT
    tablespace_name,
    file_id,
    file_name,
    bytes,
    status
FROM dba_data_files
ORDER BY tablespace_name, file_id;
~~~

Trong RMAN:

~~~text
REPORT SCHEMA;
~~~

REPORT SCHEMA hữu ích để xem datafile thuộc tablespace nào và số file mà RMAN nhận diện.

### 5.3. Khi nào backup riêng tablespace?

- Một tablespace thay đổi nhanh hơn phần còn lại.
- Có yêu cầu recovery phạm vi nhỏ.
- Có thể backup/restore theo lịch riêng.
- Cần thêm bản backup trước thay đổi lớn ở một vùng dữ liệu.

Tuy nhiên, backup một tablespace không tự bảo vệ toàn bộ database. SYSTEM, SYSAUX, undo và các tablespace nghiệp vụ có dependency cần được bảo vệ theo chiến lược tổng thể.

### 5.4. Read-only tablespace

Tablespace read-only ít thay đổi, có thể được backup ít thường xuyên hơn nếu policy cho phép. Nhưng vẫn phải giữ backup có thể restore và metadata phù hợp. Khi tablespace chuyển từ READ ONLY sang READ WRITE, cần cập nhật lịch backup vì dữ liệu có thể thay đổi trở lại.


## 6. Backup datafile

Backup riêng datafile hữu ích khi một file lớn hoặc cần lịch backup riêng.

### 6.1. Backup theo file number

~~~text
BACKUP DATAFILE 4 TAG 'USERS_DF4';
~~~

Có thể backup nhiều file:

~~~text
BACKUP DATAFILE 4, 5, 6;
~~~

File number lấy từ V$DATAFILE/REPORT SCHEMA. Không đoán file number từ tên file.

### 6.2. Backup theo tên file

~~~text
BACKUP DATAFILE '/u02/oradata/ORCL/users01.dbf';
~~~

Tên file phải khớp với file được database/control file nhận diện. Khi dùng ASM hoặc OMF, tên file có thể là dạng alias/ASM path; xem REPORT SCHEMA trước.

### 6.3. Backup datafile mới tạo

Sau khi thêm datafile/tablespace, kiểm tra control file metadata và đảm bảo file mới được đưa vào backup schedule. Control file autobackup giúp lưu metadata thay đổi cấu trúc nhưng không thay thế backup nội dung datafile mới.

~~~sql
SELECT
    file#,
    name,
    status,
    creation_change#
FROM v$datafile
ORDER BY file#;
~~~

### 6.4. Backup một datafile không thay thế archived redo

Datafile backup có checkpoint SCN riêng. Khi restore, Oracle có thể cần archived redo từ checkpoint của file tới SCN mục tiêu. Phải giữ log sequence đầy đủ cho mọi thread cần thiết.

Nếu chỉ backup datafile 4 mà xóa archived logs cũ cần cho file đó, restore có thể không recover được tới thời điểm hiện tại.

## 7. Backup control file

Control file là thành phần quan trọng để mount database và xác định cấu trúc file. Mất control file có thể ngăn database mount hoặc mở đúng cách.

### 7.1. Bật control file autobackup

Trong RMAN:

~~~text
CONFIGURE CONTROLFILE AUTOBACKUP ON;
~~~

Khi bật, RMAN tạo autobackup control file sau các backup job và một số thay đổi cấu trúc database theo hành vi RMAN. Nếu database dùng SPFILE, autobackup control file thường chứa cả SPFILE.

Autobackup giúp khôi phục control file ngay cả khi control file repository hiện tại không còn. Cần kiểm tra format và vị trí autobackup, đặc biệt khi dùng FRA, disk format tùy chỉnh hoặc media manager.

### 7.2. Cấu hình format autobackup

Ví dụ disk:

~~~text
CONFIGURE CONTROLFILE AUTOBACKUP FORMAT
FOR DEVICE TYPE DISK TO '/backup/ORCL/<UNIQUE_RMAN_AUTOBACKUP_NAME>';
~~~

RMAN có quy tắc tên autobackup duy nhất theo DBID/date/sequence. Đảm bảo thư mục tồn tại, có quyền ghi và được backup ra storage phù hợp.

Nếu thay đổi format, ghi lại đường dẫn để restore khi mất control file. Khi control file mất, RMAN không có repository hiện tại để tự biết mọi format custom nếu DBA không chỉ định đúng.

### 7.3. Backup current control file thủ công

~~~text
BACKUP CURRENT CONTROLFILE TAG 'CONTROLFILE_MANUAL';
~~~

Có thể backup control file cùng database:

~~~text
BACKUP DATABASE INCLUDE CURRENT CONTROLFILE;
~~~

Autobackup vẫn nên được cấu hình theo policy. Manual backup hữu ích trước/sau thay đổi cấu trúc quan trọng hoặc khi cần bản control file được gắn tag rõ.

### 7.4. Backup control file to trace

Có thể tạo script mô tả cấu trúc control file:

~~~sql
ALTER DATABASE BACKUP CONTROLFILE TO TRACE
AS '/secure/backup/controlfile_create.sql' REUSE;
~~~

File trace là script CREATE CONTROLFILE, không phải bản binary control file thay thế autobackup. Nó có thể hỗ trợ tái tạo control file trong một số kịch bản, nhưng phải được bảo vệ và cập nhật khi cấu trúc database thay đổi.

### 7.5. Multiplex control files

CONTROL_FILES có thể chỉ định nhiều bản control file trên các vị trí storage khác nhau. Multiplexing giúp database tiếp tục hoạt động khi một bản bị hỏng/mất, nhưng không thay thế backup control file ra nơi độc lập.

## 8. Backup SPFILE

SPFILE là binary server parameter file chứa cấu hình instance. Mất SPFILE có thể làm database không khởi động với cấu hình mong muốn.

### 8.1. Backup SPFILE bằng RMAN

~~~text
BACKUP SPFILE TAG 'SPFILE_DAILY';
~~~

Nếu CONTROLFILE AUTOBACKUP bật và database dùng SPFILE, RMAN có thể đưa SPFILE vào autobackup control file. Backup SPFILE riêng vẫn hữu ích để quản lý rõ ràng và dễ tìm.

### 8.2. Tạo PFILE text để lưu cấu hình

~~~sql
CREATE PFILE='/secure/backup/initORCL.ora' FROM SPFILE;
~~~

PFILE là file text, dễ xem và quản lý version. Bảo vệ file vì có thể chứa tham số nhạy cảm như vị trí wallet, audit destination, encryption configuration hoặc thông tin môi trường.

### 8.3. Khôi phục SPFILE từ autobackup

Nếu control file còn và database có thể mount, RMAN có thể restore SPFILE theo repository. Nếu cả control file và SPFILE mất, khởi động NOMOUNT bằng PFILE tạm tối thiểu hoặc dùng DBID để tìm autobackup.

Ví dụ khái quát:

~~~text
STARTUP NOMOUNT;
RESTORE SPFILE FROM AUTOBACKUP;
SHUTDOWN IMMEDIATE;
STARTUP NOMOUNT;
~~~

Lệnh restore cụ thể phụ thuộc vị trí autobackup, DBID và recovery catalog. Nếu không có control file/recovery catalog, dùng SET DBID trước khi tìm autobackup và chỉ định format nếu cần.

### 8.4. Không sửa SPFILE binary bằng editor

Để thay đổi tham số, dùng ALTER SYSTEM SET với SCOPE phù hợp hoặc tạo PFILE rồi tạo lại SPFILE theo quy trình. Không mở SPFILE binary bằng text editor và không copy một SPFILE từ database khác mà chưa chỉnh DB_NAME, control_files, memory, diagnostic và storage settings.

## 9. Backup archived redo logs

Archived redo logs là điều kiện để recover từ backup tới một SCN/time sau thời điểm backup.

### 9.1. Backup toàn bộ archived logs

~~~text
BACKUP ARCHIVELOG ALL TAG 'ARCH_DAILY';
~~~

### 9.2. Backup archived logs chưa được backup

~~~text
BACKUP ARCHIVELOG ALL NOT BACKED UP 1 TIMES;
~~~

Có thể dùng DEVICE TYPE DISK/SBT hoặc cấu hình channel để lưu vào đúng media.

### 9.3. Backup và xóa archived logs

Ví dụ:

~~~text
BACKUP ARCHIVELOG ALL DELETE INPUT TAG 'ARCH_BACKUP';
~~~

DELETE INPUT xóa các archived log input đã backup theo lệnh và device context. Phải hiểu bản sao nào đã được tạo và chính sách giữ nhiều bản trước khi dùng. Không dùng DELETE INPUT để thay thế retention policy hoặc xóa log khi chưa xác nhận bản backup đã an toàn.

Có thể dùng DELETE ALL INPUT trong một số chiến lược backup nhiều bản copy; kiểm tra cú pháp RMAN và số bản backup mong muốn.

### 9.4. Archived log theo sequence/thread

Trong RAC, redo được chia theo thread. Ví dụ:

~~~text
BACKUP ARCHIVELOG FROM SEQUENCE 120 UNTIL SEQUENCE 145 THREAD 1;
~~~

Phải xác định sequence/thread đúng. Không giả định sequence liên tục toàn cluster mà không xét thread.

### 9.5. Kiểm tra archive mode và destination

~~~sql
ARCHIVE LOG LIST;
~~~

~~~sql
SELECT
    dest_id,
    status,
    destination,
    error
FROM v$archive_dest
WHERE status <> 'INACTIVE';
~~~

Nếu archive destination đầy, database có thể bị ảnh hưởng khi cần archive redo log để tái sử dụng log group. Theo dõi FRA, archive destination và backup jobs.

## 10. Fast Recovery Area (FRA)

FRA là vùng lưu trữ được Oracle quản lý cho recovery-related files như archived logs, flashback logs, control file autobackup và RMAN backup pieces tùy cấu hình.

### 10.1. Cấu hình FRA

Ví dụ:

~~~sql
ALTER SYSTEM SET db_recovery_file_dest_size = 200G SCOPE=BOTH;
ALTER SYSTEM SET db_recovery_file_dest = '/u04/oracle/fra' SCOPE=BOTH;
~~~

Thứ tự thực tế cần tuân theo yêu cầu tham số của release; trong một số trường hợp đặt size trước khi đặt destination. Kiểm tra giá trị hiện tại:

~~~sql
SHOW PARAMETER db_recovery_file_dest;
SHOW PARAMETER db_recovery_file_dest_size;
~~~

### 10.2. Theo dõi FRA

~~~sql
SELECT
    name,
    space_limit,
    space_used,
    space_reclaimable,
    number_of_files
FROM v$recovery_file_dest;
~~~

Theo dõi tỷ lệ sử dụng, file có thể reclaim và tốc độ tăng archived logs. FRA đầy có thể làm archive không tiến triển và ảnh hưởng hoạt động database.

### 10.3. FRA không phải backup độc lập

Nếu FRA nằm trên cùng storage failure domain với database, sự cố storage có thể làm mất cả datafiles và backup. Với yêu cầu DR, cần copy backup/archived logs ra storage hoặc site độc lập theo policy.

## 11. RMAN channels, backup sets và image copies

### 11.1. Channel

Channel là RMAN session/process dùng để đọc/ghi backup. Có thể cấu hình channel cho DISK hoặc SBT (tape/media manager).

Ví dụ:

~~~text
CONFIGURE DEVICE TYPE DISK PARALLELISM 2;
CONFIGURE CHANNEL DEVICE TYPE DISK FORMAT '/backup/ORCL/backup_%d_%T_%U.bkp';
~~~

PARALLELISM tạo nhiều channel tự động cho device type. Khi dùng media manager, cấu hình SBT library và channel parameters theo hướng dẫn nhà cung cấp.

### 11.2. Backup set

Backup set là định dạng RMAN chứa một hoặc nhiều backup piece. Backup piece là file vật lý trên disk/tape. RMAN quản lý metadata để biết backup set chứa block/file nào.

Ví dụ:

~~~text
BACKUP AS BACKUPSET DATABASE;
~~~

Backup set thường lưu các block cần thiết, có thể nén và mã hóa theo cấu hình.

### 11.3. Image copy

Image copy là bản sao file datafile/control file tương tự file gốc:

~~~text
BACKUP AS COPY DATABASE;
~~~

Image copy có thể được dùng với SWITCH DATAFILE/TABLESPACE TO COPY trong một số quy trình để chuyển sang bản copy. Nó thường chiếm dung lượng gần bằng file gốc nhưng có thể giảm thời gian restore vì không cần giải nén backup set theo cách thông thường.

### 11.4. Compression

Ví dụ:

~~~text
BACKUP AS COMPRESSED BACKUPSET DATABASE;
~~~

Compression giảm dung lượng nhưng tiêu thụ CPU và có thể ảnh hưởng throughput. Chọn thuật toán/mức compression theo license, edition, release và cấu hình. Đo thời gian backup, CPU, bytes và restore time trước khi áp dụng rộng.

### 11.5. Encryption

RMAN có thể mã hóa backup set. Có thể dùng transparent encryption dựa trên Oracle keystore hoặc password-based encryption theo chính sách. Ví dụ bật encryption cho database backup theo cấu hình RMAN:

~~~text
CONFIGURE ENCRYPTION FOR DATABASE ON;
~~~

Trong password-based workflow, cú pháp SET ENCRYPTION cần dùng đúng RMAN Reference và password phải được quản lý riêng. Nếu mất password hoặc keystore key cần thiết, backup mã hóa có thể không restore được.

Bảo vệ keystore/wallet cùng backup metadata. Không lưu password encryption trong script, source control hoặc cùng thư mục backup mà không có kiểm soát.

## 12. Retention policy và quản lý backup cũ

Retention policy xác định backup nào cần được giữ để đáp ứng recovery window hoặc redundancy.

### 12.1. Recovery window

Ví dụ giữ khả năng recover trong 14 ngày:

~~~text
CONFIGURE RETENTION POLICY TO RECOVERY WINDOW OF 14 DAYS;
~~~

### 12.2. Redundancy

Ví dụ giữ ít nhất hai bản backup phù hợp theo policy:

~~~text
CONFIGURE RETENTION POLICY TO REDUNDANCY 2;
~~~

Recovery window và redundancy có semantics khác nhau. Chọn theo RPO/RTO và dung lượng storage; không đặt theo cảm tính.

### 12.3. REPORT OBSOLETE và DELETE OBSOLETE

~~~text
REPORT OBSOLETE;
~~~

Sau khi xác nhận:

~~~text
DELETE OBSOLETE;
~~~

Obsolete là backup không còn cần theo retention policy. RMAN không nhất thiết xóa ngay sau khi một backup mới hoàn tất.

### 12.4. CROSSCHECK và EXPIRED

~~~text
CROSSCHECK BACKUP;
CROSSCHECK ARCHIVELOG ALL;
~~~

CROSSCHECK so sánh repository với media thực tế. Backup không tìm thấy có thể được đánh dấu EXPIRED.

Sau khi xác minh:

~~~text
LIST EXPIRED BACKUP;
DELETE EXPIRED BACKUP;
~~~

Phân biệt:
- EXPIRED: RMAN không tìm thấy file/media tại vị trí được ghi nhận khi crosscheck.
- OBSOLETE: backup không còn cần theo retention policy.

Không dùng DELETE EXPIRED để xóa file còn cần; lệnh chủ yếu cập nhật repository record sau khi media không tồn tại. Không xóa file backup bằng OS trước khi crosscheck/retention logic được hiểu rõ.

## 13. Lập lịch backup mẫu

Lịch cụ thể phụ thuộc RPO/RTO, lượng thay đổi, dung lượng và thời gian backup. Một mô hình tham khảo cho database ARCHIVELOG:

| Lịch | Công việc ví dụ | Mục tiêu |
| --- | --- | --- |
| Hàng tuần | Incremental level 0 hoặc full | Baseline |
| Hàng ngày | Incremental level 1 | Giảm lượng backup |
| Mỗi 15–60 phút | Backup archived logs theo workload | Giảm redo loss window |
| Hàng ngày | Control file/SPFILE autobackup | Bảo vệ metadata |
| Hàng ngày/tuần | Crosscheck và report | Kiểm tra repository/media |
| Hàng tháng | Restore validation/restore drill | Chứng minh khả năng phục hồi |
| Định kỳ | Offsite copy và recovery test | Disaster recovery |

Đây chỉ là ví dụ lịch. Nếu yêu cầu RPO 5 phút, backup archived logs mỗi giờ có thể không đáp ứng; cần thiết kế archive/transport/backup phù hợp. RPO không chỉ phụ thuộc backup interval mà còn phụ thuộc redo shipping, storage durability và quy trình failover.


## 14. Restore và recover database

Restore là chép datafile/control file/SPFILE từ backup về vị trí cần thiết. Recover là áp dụng redo để đưa file về SCN mục tiêu.

### 14.1. Complete database recovery

Ví dụ database cần restore toàn bộ datafiles, control file hiện tại còn dùng được:

~~~text
STARTUP MOUNT;
RESTORE DATABASE;
RECOVER DATABASE;
ALTER DATABASE OPEN;
~~~

Các lệnh này chạy trong RMAN. Nếu database đã MOUNT, không cần STARTUP MOUNT lần nữa.

RMAN chọn backup phù hợp và áp dụng archived/online redo theo repository và target. Đảm bảo có đủ media, password/keystore nếu backup encrypted và archive log sequence cần thiết.

### 14.2. Restore một datafile

Ví dụ file 4 bị mất/hỏng, database ở ARCHIVELOG mode:

~~~text
SQL 'ALTER DATABASE DATAFILE 4 OFFLINE';
RESTORE DATAFILE 4;
RECOVER DATAFILE 4;
SQL 'ALTER DATABASE DATAFILE 4 ONLINE';
~~~

Cần xác định file number/path, tablespace và trạng thái database. Một số file quan trọng như SYSTEM/undo có giới hạn offline và yêu cầu quy trình recovery khác. Không offline file khi chưa hiểu ảnh hưởng ứng dụng.

### 14.3. Restore một tablespace

~~~text
SQL 'ALTER TABLESPACE users OFFLINE IMMEDIATE';
RESTORE TABLESPACE users;
RECOVER TABLESPACE users;
SQL 'ALTER TABLESPACE users ONLINE';
~~~

Ví dụ cần điều chỉnh theo database mode, tablespace status và dependencies. Với tablespace SYSTEM, undo hoặc tablespace quan trọng, không áp dụng quy trình offline thông thường.

### 14.4. Restore control file từ autobackup

Nếu control file mất và không dùng recovery catalog, cần DBID để tìm autobackup. Trong RMAN:

~~~text
SET DBID 1234567890;
STARTUP NOMOUNT;
RESTORE CONTROLFILE FROM AUTOBACKUP;
ALTER DATABASE MOUNT;
~~~

DBID ở ví dụ chỉ là placeholder. Lấy DBID từ backup log, RMAN output, database inventory hoặc nơi lưu metadata. Nếu autobackup format được tùy chỉnh, chỉ định đúng format/đường dẫn.

Sau mount, có thể restore/recover database theo tình huống và mở RESETLOGS nếu recovery path yêu cầu.

### 14.5. Restore SPFILE từ autobackup

Khi control file và SPFILE mất, có thể khởi động NOMOUNT bằng PFILE tối thiểu hoặc dùng RMAN với DBID để tìm autobackup:

~~~text
SET DBID 1234567890;
STARTUP FORCE NOMOUNT;
RESTORE SPFILE FROM AUTOBACKUP;
SHUTDOWN IMMEDIATE;
STARTUP NOMOUNT;
~~~

Cú pháp và yêu cầu PFILE/DBID/autobackup format phụ thuộc tình trạng thực tế. Sau khi restore SPFILE, xác nhận tham số CONTROL_FILES, DB_NAME, DB_UNIQUE_NAME, memory và đường dẫn storage trước khi mount.

### 14.6. Restore control file và OPEN RESETLOGS

Nếu control file được restore từ backup, database thường cần media recovery theo backup control file procedure và OPEN RESETLOGS. RESETLOGS tạo incarnation mới. Sau đó:
- Backup database ngay theo chính sách.
- Xác nhận incarnation trong RMAN.
- Tiếp tục backup archived logs.
- Kiểm tra standby/replication nếu có.
- Cập nhật recovery documentation.

Không chạy OPEN RESETLOGS tùy tiện cho complete recovery với current control file nếu không có yêu cầu recovery path.

## 15. Backup và restore CDB/PDB

Trong multitenant architecture, CDB chứa root, seed và một hoặc nhiều PDB. RMAN có thể backup toàn CDB hoặc phạm vi PDB/tablespace tùy nhu cầu.

### 15.1. Backup toàn CDB

Kết nối RMAN tới CDB root:

~~~text
BACKUP DATABASE PLUS ARCHIVELOG;
~~~

Lệnh backup toàn database bao gồm các file thuộc phạm vi CDB theo RMAN. Kiểm tra báo cáo RMAN và backup list để xác nhận PDBs/datafiles được bao phủ.

### 15.2. Backup một PDB

Ví dụ:

~~~text
BACKUP PLUGGABLE DATABASE salespdb;
~~~

PDB phải ở trạng thái và điều kiện phù hợp với thao tác. Kết nối vào CDB root theo quy trình RMAN và dùng tên PDB chính xác.

### 15.3. Backup tablespace trong PDB

Cú pháp phạm vi PDB/tablespace phụ thuộc RMAN version và container context. Dùng REPORT SCHEMA, RMAN Reference và xác định tên tablespace thuộc PDB mục tiêu trước khi backup. Không dùng nhầm tablespace cùng tên trong PDB khác.

### 15.4. Restore/recover PDB

RMAN hỗ trợ restore/recover PDB và các datafile thuộc PDB. Quy trình phụ thuộc PDB state, control file, root metadata và mục tiêu recovery. Một số thao tác cần PDB đóng hoặc ở trạng thái phù hợp; hãy dùng cú pháp chính thức cho release và thử trên bản sao lab.

### 15.5. CDB/PDB backup strategy

- Backup root/control file/SPFILE theo lịch CDB.
- Bảo vệ archived redo cho các redo thread/container liên quan.
- Backup PDB riêng nếu có RPO/RTO khác nhau.
- Kiểm tra plug/unplug, relocation và file name conversion.
- Giữ DBID, DB_UNIQUE_NAME, PDB GUID và metadata cần thiết.
- Test restore PDB mà không ảnh hưởng PDB khác.

## 16. Backup database với RMAN: script mẫu

Ví dụ script đơn giản cho backup daily trên disk:

~~~text
RUN {
  ALLOCATE CHANNEL c1 DEVICE TYPE DISK;
  BACKUP AS COMPRESSED BACKUPSET
    DATABASE
    TAG 'DAILY_DB';
  BACKUP ARCHIVELOG ALL NOT BACKED UP 1 TIMES
    TAG 'DAILY_ARCH';
  BACKUP CURRENT CONTROLFILE
    TAG 'DAILY_CONTROLFILE';
  BACKUP SPFILE
    TAG 'DAILY_SPFILE';
  RELEASE CHANNEL c1;
}
~~~

Nếu CONTROLFILE AUTOBACKUP đã bật, backup control file có thể được tạo thêm theo policy. Script mẫu cần điều chỉnh:
- Destination/format.
- Channel parallelism.
- Compression.
- Encryption.
- Archived log deletion policy.
- Retention policy.
- Error handling và monitoring.
- CDB/PDB scope.

Không đưa password trực tiếp vào script. Dùng wallet/secret store hoặc cơ chế RMAN encryption được quản lý.

## 17. Kiểm tra chất lượng backup

### 17.1. LIST BACKUP

~~~text
LIST BACKUP SUMMARY;
LIST BACKUP OF DATABASE;
LIST BACKUP OF TABLESPACE users;
LIST BACKUP OF DATAFILE 4;
LIST BACKUP OF CONTROLFILE;
LIST BACKUP OF SPFILE;
LIST BACKUP OF ARCHIVELOG ALL;
~~~

Các lệnh LIST giúp xác định RMAN repository có record nào và backup nào sẵn sàng theo metadata.

### 17.2. RESTORE PREVIEW

~~~text
RESTORE DATABASE PREVIEW;
RESTORE TABLESPACE users PREVIEW;
RESTORE DATAFILE 4 PREVIEW;
~~~

PREVIEW cho biết RMAN dự kiến dùng backup nào, không thực hiện restore.

### 17.3. RESTORE VALIDATE

~~~text
RESTORE DATABASE VALIDATE;
RESTORE TABLESPACE users VALIDATE;
RESTORE DATAFILE 4 VALIDATE;
~~~

VALIDATE đọc backup pieces cần thiết để xác minh khả năng đọc và tính phù hợp theo RMAN. Nó không thay thế restore thật trên host khác, kiểm tra database open và ứng dụng.

### 17.4. BACKUP VALIDATE

~~~text
BACKUP VALIDATE DATABASE;
~~~

BACKUP VALIDATE đọc datafiles và kiểm tra block mà không tạo backup piece thông thường. Nó có thể tạo I/O đáng kể; chọn thời điểm và phạm vi phù hợp.

### 17.5. Restore drill

Một restore drill nên:
1. Dùng host/storage độc lập.
2. Lấy control file/SPFILE và backup pieces.
3. Khôi phục keystore/wallet nếu cần.
4. Restore database.
5. Apply archived redo tới target.
6. Mở database theo recovery path.
7. Kiểm tra object, row count, application smoke test.
8. Đo thời gian thực tế.
9. Ghi lại vấn đề và cập nhật runbook.

## 18. Những lưu ý vận hành quan trọng

### 18.1. RPO và RTO

- RPO: lượng dữ liệu tối đa có thể chấp nhận mất.
- RTO: thời gian tối đa để khôi phục dịch vụ.

Backup full mỗi ngày có thể đáp ứng RTO nhưng không đáp ứng RPO nếu archived redo không được bảo vệ thường xuyên. Tăng tần suất backup cũng không tự bảo đảm RTO nếu restore datafile quá lâu hoặc thiếu media.

### 18.2. Backup retention và offsite

Giữ bản backup theo retention policy và copy ra failure domain khác. Nếu ransomware hoặc lỗi operator xóa backup cùng host database, bản backup cùng storage có thể mất theo.

### 18.3. Backup encryption

Nếu backup được mã hóa:
- Bảo vệ wallet/keystore hoặc password.
- Có backup key/keystore độc lập.
- Kiểm thử restore khi không còn host ban đầu.
- Ghi rõ ai có quyền mở backup.
- Không đặt password backup trong cùng backup directory.

### 18.4. Compression và parallelism

Compression tiết kiệm storage nhưng dùng CPU. Parallelism tăng throughput nhưng có thể làm storage/CPU quá tải. Đo với workload thật, theo dõi wait/I/O và chọn số channel hợp lý.

### 18.5. Backup khi database đang thay đổi cấu trúc

Khi add/drop datafile, tablespace hoặc rename file, control file metadata thay đổi. Control file autobackup và RMAN repository giúp giữ metadata. Trước thao tác DDL lớn, có thể tạo backup/tag hoặc backup control file theo change procedure.

### 18.6. Backup password file và wallet

RMAN backup database không nhất thiết bao gồm mọi file ngoài database như password file, listener config, wallet, TDE keystore, scripts và external config. Lập inventory riêng cho các file này, bảo vệ chúng theo policy và test recovery trên host khác.

## 19. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| RMAN không tìm thấy backup | Repository/control file khác, backup expired hoặc sai DBID | LIST, CATALOG START WITH, kiểm tra catalog và DBID |
| ORA-19504/ORA-27040 | Không tạo được backup piece | Kiểm tra path, permission, space và storage |
| ORA-19809/ORA-19804 | FRA vượt quota/không reclaim được | Kiểm tra FRA, backup/archive policy và dung lượng |
| Backup database chạy nhưng thiếu archive logs | Backup archived log không đầy đủ hoặc destination lỗi | Kiểm tra thread/sequence coverage và alert log |
| Restore dừng do thiếu archived log | Log sequence cần thiết không có | Tìm backup log, media khác hoặc chọn target phù hợp |
| Control file mất | Không thể mount bằng control file hiện tại | Restore autobackup/recovery catalog, cần DBID nếu phù hợp |
| SPFILE mất | Instance không khởi động theo cấu hình cũ | Restore SPFILE hoặc tạo PFILE tạm |
| Backup piece bị đánh dấu EXPIRED | CROSSCHECK không tìm thấy media | Kiểm tra storage/media manager trước DELETE EXPIRED |
| Backup OBSOLETE bị xóa | Retention policy không phù hợp | Xem REPORT OBSOLETE và điều chỉnh policy |
| Restore validate thành công nhưng DR thất bại | Chưa test control file, wallet, network hoặc application | Thực hiện full restore drill độc lập |
| Backup encrypted không restore được | Mất password/keystore key | Khôi phục đúng key/wallet và kiểm tra trước |
| Tablespace backup không đủ để restore | Thiếu archived redo hoặc file phụ thuộc | Backup và giữ redo cần thiết |
| Datafile mới không có backup | Job scope/filter bỏ qua file mới | REPORT SCHEMA và cập nhật backup policy |
| PDB restore sai container | Nhầm tên tablespace/PDB hoặc connection context | Xác nhận CDB/PDB và RMAN scope |
| Backup quá chậm | Channel ít, storage chậm, compression CPU | Đo throughput, CPU, wait và channel |
| Backup thành công nhưng RPO không đạt | Archived log backup interval quá dài | Điều chỉnh archive backup/transport cadence |

## 20. Runbook backup hàng ngày

Một runbook vận hành nên gồm:

### Trước backup
- Xác nhận database open và LOG_MODE.
- Kiểm tra FRA/archive destination.
- Kiểm tra RMAN SHOW ALL và retention.
- Kiểm tra backup storage/media manager.
- Kiểm tra lỗi backup job gần nhất.
- Xác nhận control file autobackup và SPFILE protection.

### Thực hiện backup
- Chạy database/incremental backup theo lịch.
- Backup archived redo logs.
- Backup control file/SPFILE hoặc xác nhận autobackup.
- Ghi tag, start/end time, bytes và output log.
- Theo dõi channel, throughput, errors và storage.

### Sau backup
- LIST BACKUP SUMMARY.
- CROSSCHECK theo lịch.
- RESTORE PREVIEW/VALIDATE theo phạm vi.
- REPORT OBSOLETE trước khi DELETE OBSOLETE.
- Xác nhận archived logs cần thiết đã được backup.
- Gửi kết quả monitoring theo quy trình tổ chức.
- Lập lịch restore drill.

Không đánh dấu backup job thành công chỉ từ exit code nếu log có warning/error hoặc phần archive/control file bị bỏ qua.

## 21. Lab: backup từng thành phần bằng RMAN

Thực hiện trong Oracle lab có quyền RMAN và storage riêng.

### 21.1. Khám phá cấu trúc

Trong SQL*Plus:

~~~sql
SELECT name, open_mode, log_mode, current_scn
FROM v$database;

SELECT file#, name, status
FROM v$datafile
ORDER BY file#;

SELECT name
FROM v$tablespace
ORDER BY name;
~~~

Trong RMAN:

~~~text
REPORT SCHEMA;
SHOW ALL;
~~~

### 21.2. Backup toàn database

~~~text
BACKUP DATABASE TAG 'LAB_FULL';
~~~

Nếu lab ở ARCHIVELOG:

~~~text
BACKUP DATABASE PLUS ARCHIVELOG TAG 'LAB_DB_ARCH';
~~~

### 21.3. Backup tablespace

~~~text
BACKUP TABLESPACE USERS TAG 'LAB_USERS';
~~~

Thay USERS bằng tablespace lab thực tế.

### 21.4. Backup datafile

~~~text
BACKUP DATAFILE 4 TAG 'LAB_DF4';
~~~

Chỉ dùng file number đã xác nhận từ REPORT SCHEMA/V$DATAFILE.

### 21.5. Backup control file và SPFILE

~~~text
CONFIGURE CONTROLFILE AUTOBACKUP ON;
BACKUP CURRENT CONTROLFILE TAG 'LAB_CONTROLFILE';
BACKUP SPFILE TAG 'LAB_SPFILE';
~~~

Kiểm tra:

~~~text
LIST BACKUP OF CONTROLFILE;
LIST BACKUP OF SPFILE;
~~~

### 21.6. Backup archived logs

~~~text
BACKUP ARCHIVELOG ALL TAG 'LAB_ARCH';
LIST BACKUP OF ARCHIVELOG ALL;
~~~

### 21.7. Validate

~~~text
RESTORE DATABASE PREVIEW;
RESTORE DATABASE VALIDATE;
RESTORE TABLESPACE USERS VALIDATE;
RESTORE DATAFILE 4 VALIDATE;
~~~

Ghi output và backup keys để làm bài tập restore.

## 22. Lab: restore trong môi trường riêng

Không restore đè database đang dùng. Dùng auxiliary host/database hoặc bản lab độc lập.

### 22.1. Restore database

Dựa trên backup lab:
- Chuẩn bị Oracle Home và storage.
- Chuẩn bị PFILE/SPFILE và control file.
- Kết nối RMAN.
- Restore control file nếu cần.
- Mount database.
- Restore database.
- Recover database tới target.
- Open theo recovery path.
- Kiểm tra datafiles và application.

### 22.2. Restore tablespace/datafile

Mô phỏng mất một file lab:
- Đưa file offline theo điều kiện database.
- Restore datafile/tablespace từ backup.
- Recover bằng archived redo.
- Online lại file/tablespace.
- Kiểm tra object và dữ liệu.

### 22.3. Restore control file/SPFILE

Mô phỏng bằng database lab khác hoặc clone:
- Khởi động NOMOUNT.
- Dùng DBID và autobackup format nếu cần.
- Restore SPFILE/control file.
- Khởi động lại với SPFILE đúng.
- Mount, restore/recover datafiles.
- Mở database theo yêu cầu.

Không xóa control file hoặc SPFILE duy nhất của database đang dùng để luyện tập.

## 23. Bài tập thực hành

### Bài 1 — Full database backup

Chạy BACKUP DATABASE và đọc LIST BACKUP SUMMARY. Ghi backup set, piece, tag, completion time và checkpoint SCN.

### Bài 2 — Level 0/Level 1

Tạo level 0, chạy một số DML, sau đó tạo differential và cumulative level 1. So sánh bytes và thời gian backup.

### Bài 3 — Tablespace backup

Backup một tablespace lab. Liệt kê các datafile thuộc tablespace và kiểm tra RESTORE TABLESPACE PREVIEW.

### Bài 4 — Datafile backup

Backup một datafile riêng. Ghi file number, checkpoint và archived redo cần thiết để recover.

### Bài 5 — Control file autobackup

Bật CONTROLFILE AUTOBACKUP, chạy backup và tìm autobackup piece. Thử xác định DBID/format cần cho restore khi control file mất.

### Bài 6 — SPFILE

Backup SPFILE và tạo PFILE text. So sánh các tham số quan trọng; không chia sẻ secret/credential trong PFILE.

### Bài 7 — Archived redo

Backup archived logs theo interval, kiểm tra sequence/thread và thử RESTORE ARCHIVELOG PREVIEW/VALIDATE theo RMAN release.

### Bài 8 — Retention

Đặt recovery window trong lab, chạy REPORT OBSOLETE và giải thích vì sao backup nào được giữ/xóa.

### Bài 9 — Compression/encryption

So sánh backup compressed và uncompressed. Nếu có wallet/keystore lab, bật backup encryption và diễn tập restore với key phù hợp.

### Bài 10 — Restore drill

Khôi phục database lab trên môi trường độc lập. Ghi RTO thực tế, SCN phục hồi, archive logs đã dùng, lỗi gặp phải và các bước cần bổ sung vào runbook.

## 24. Dọn dẹp và khôi phục môi trường lab

- Kiểm tra database lab OPEN và datafiles ONLINE.
- Giữ backup lab cần cho bài restore; xóa theo RMAN policy khi đã hoàn tất.
- Không xóa archived logs còn cần cho recovery.
- Khôi phục cấu hình RMAN trước lab nếu đã thay đổi.
- Tắt BCT hoặc xóa file BCT chỉ khi có kế hoạch và không còn cần.
- Xác nhận FRA còn dung lượng.
- Không xóa backup piece trực tiếp bằng OS khi RMAN repository vẫn tham chiếu.
- Không xóa control file, SPFILE hoặc wallet duy nhất của database.

## Tổng kết

RMAN có thể backup toàn database, tablespace và datafile; control file và SPFILE được bảo vệ bằng backup riêng hoặc control file autobackup; archived redo logs cho phép recover từ checkpoint backup tới SCN/time mục tiêu. Incremental level 0/1 giúp cân bằng dung lượng và thời gian backup; backup set, image copy, channel, compression và encryption cung cấp các lựa chọn vận hành khác nhau.

Restore và recover là hai bước riêng: RESTORE lấy file từ backup, RECOVER áp dụng redo. Backup database không thay thế backup control file/SPFILE và archived logs. Backup riêng tablespace/datafile cũng phải đi cùng redo coverage. Kiểm tra bằng LIST, CROSSCHECK, RESTORE PREVIEW và VALIDATE, nhưng chỉ restore drill độc lập mới chứng minh được quy trình phục hồi end-to-end.

Xây dựng lịch backup dựa trên RPO/RTO, giữ backup ở failure domain độc lập, bảo vệ encryption keys, theo dõi FRA và archived log sequence, đồng thời ghi runbook cho restore toàn database và từng thành phần. Không đánh giá thành công chỉ từ backup job; mục tiêu cuối cùng là khôi phục được dữ liệu và dịch vụ trong thời gian đã cam kết.

## Tài liệu Oracle tham khảo

- [Oracle Database Backup and Recovery User's Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/) — chiến lược RMAN, backup database/tablespace/datafile và restore/recovery.
- [Oracle Database Backup and Recovery Reference (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/rcmrf/) — cú pháp RMAN BACKUP, RESTORE, RECOVER, CONFIGURE, LIST và VALIDATE.
- [Oracle Database Administrator's Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/) — control files, SPFILE, redo, archive mode và cấu trúc database.
- [Oracle Database Reference — V$DATAFILE (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-DATAFILE.html) — metadata datafile.
- [Oracle Database Reference — V$RECOVERY_FILE_DEST (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-RECOVERY_FILE_DEST.html) — dung lượng và tình trạng Fast Recovery Area.
- [Oracle Database Reference — V$BLOCK_CHANGE_TRACKING (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-BLOCK_CHANGE_TRACKING.html) — trạng thái block change tracking.
- [Oracle Database Backup and Recovery User's Guide — Multitenant Backup and Recovery (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/) — backup/recovery CDB và PDB theo release.

Khi triển khai trên Oracle release khác 19c, hãy đối chiếu RMAN Reference và Backup and Recovery User's Guide đúng phiên bản, đặc biệt cú pháp PDB backup, autobackup format, encrypted backup, retention, media manager và restore/recover control file.
