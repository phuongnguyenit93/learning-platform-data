# Diễn tập xóa nhầm, mất datafile và lựa chọn phương án phục hồi

Một sự cố xóa nhầm trong Oracle Database có thể là một câu DELETE đã COMMIT, một lệnh TRUNCATE, một DROP TABLE, một DROP TABLESPACE hoặc một datafile bị mất khỏi storage. Những tình huống này không thể xử lý bằng cùng một lệnh. Có trường hợp chỉ cần Flashback Table; có trường hợp phải dùng recycle bin; có trường hợp cần RMAN restore/recover; và có trường hợp phải phục hồi cả database hoặc tablespace tới một thời điểm trước lỗi.

Mục tiêu của bài thực hành là giúp DBA nhận diện chính xác phạm vi hỏng, bảo toàn bằng chứng, chọn phương pháp có RPO/RTO phù hợp, thực hiện recovery trong đúng trạng thái database và xác nhận dữ liệu sau phục hồi. Mọi thao tác mô phỏng phá hủy phải thực hiện trên lab hoặc clone cô lập, không thử bằng cách xóa file thật trên production.

## 1. Mô hình tư duy khi xảy ra sự cố

### 1.1. Xác định loại thay đổi đã xảy ra

Trước khi chạy recovery, xác định thao tác gây mất dữ liệu:

| Sự cố | Tác động | Phương án thường xem xét |
|---|---|---|
| DELETE chưa COMMIT | DML còn trong transaction | ROLLBACK transaction |
| DELETE đã COMMIT | Mất một phần hoặc toàn bộ rows | Flashback Table/Query, RMAN table recovery, PITR |
| TRUNCATE TABLE | Dữ liệu bảng bị loại bỏ bằng DDL | RMAN RECOVER TABLE, Flashback Database, PITR |
| DROP TABLE | Object bị drop | Flashback Drop từ recycle bin, RMAN table recovery |
| DROP TABLE PURGE | Object bị loại khỏi recycle bin | RMAN table recovery hoặc PITR |
| DROP TABLESPACE | Metadata và datafiles của tablespace bị loại | TSPITR, database PITR, restore/recover |
| Mất một datafile | File vật lý không còn truy cập được | RMAN RESTORE DATAFILE và RECOVER DATAFILE |
| Mất SYSTEM/UNDO datafile | Database có thể không mở hoặc không hoạt động | Mount/recovery toàn database theo yêu cầu |
| Mất nhiều datafiles/database | Phạm vi physical recovery rộng | RMAN database restore/recovery, Data Guard hoặc DR |
| Block corruption | Một hoặc nhiều block vật lý lỗi | RMAN block media recovery hoặc datafile recovery |

Tên lệnh người dùng nhớ được chưa đủ. Cần xác nhận câu lệnh thực tế, transaction đã commit hay chưa, object nào bị tác động, database ở ARCHIVELOG hay NOARCHIVELOG và backup/redo nào còn sẵn.

### 1.2. Phân biệt logical loss và physical loss

- **Logical loss:** rows hoặc objects bị xóa bằng SQL nhưng datafile vẫn tồn tại và database vẫn đọc được. Flashback/recycle bin có thể phù hợp.
- **Physical loss:** datafile bị xóa, volume không mount, storage hỏng hoặc block không đọc được. Cần media recovery từ backup/redo.
- **Database-wide logical error:** thao tác SQL hợp lệ nhưng gây hỏng dữ liệu trên phạm vi lớn, ví dụ DELETE không có WHERE hoặc DROP TABLESPACE. Có thể cần phục hồi tới một thời điểm trước lỗi.
- **Infrastructure failure:** host, storage, network hoặc instance bị lỗi. Cần xác định database files và redo có còn nhất quán không.

Không dùng Flashback Table để thay thế RMAN khi file vật lý đã mất; cũng không restore toàn database chỉ để khôi phục một bảng nếu có phương án table recovery an toàn hơn.

### 1.3. Recovery luôn có một mốc thời gian

Mỗi phương án cần trả lời:

- Mốc dữ liệu cuối cùng chắc chắn còn đúng là thời điểm nào?
- Có SCN hoặc timestamp xác định được không?
- Backup nào bao phủ mốc đó?
- Archived redo logs có liên tục tới mốc cần recover không?
- Có giao dịch hợp lệ phát sinh sau mốc cần giữ lại không?
- RPO có cho phép mất những giao dịch đó không?

Nếu không xác định được mốc dữ liệu, đừng vội mở lại traffic hoặc xóa bản sao hiện có.

## 2. Trước khi thực hiện recovery

### 2.1. Dừng các thay đổi có thể làm tình hình xấu hơn

Khi phát hiện xóa nhầm hoặc mất datafile:

1. Thông báo incident và ghi thời điểm phát hiện.
2. Tạm dừng batch jobs hoặc luồng ghi liên quan nếu cần.
3. Không chạy thêm DDL/DML trên object bị ảnh hưởng.
4. Không drop/recreate tablespace hoặc datafile để che lỗi.
5. Không xóa backup, archived logs, flashback logs hoặc trace.
6. Giữ lại SQL text, application logs, audit logs và session details.
7. Xác định người có quyền phê duyệt recovery và mức downtime chấp nhận.

Nếu application vẫn ghi dữ liệu liên quan, việc tiếp tục có thể làm khó xác định rows nào cần giữ và rows nào cần khôi phục.

### 2.2. Ghi nhận database identity và trạng thái

§§§sql
SELECT dbid,
       name,
       db_unique_name,
       database_role,
       open_mode,
       log_mode,
       flashback_on,
       current_scn
FROM v$database;

SELECT instance_name,
       host_name,
       status,
       database_status,
       startup_time
FROM v$instance;

SELECT name, value
FROM v$parameter
WHERE name IN (
    'compatible',
    'db_recovery_file_dest',
    'db_recovery_file_dest_size',
    'db_flashback_retention_target'
);
§§§

Lưu output cùng timestamp và timezone. Trong RAC, dùng GV$ views để ghi nhận tất cả instances khi cần.

### 2.3. Kiểm tra ARCHIVELOG và backup

§§§sql
ARCHIVE LOG LIST;

SELECT log_mode,
       open_mode,
       database_role
FROM v$database;
§§§

Trong RMAN:
§§§text
RMAN> SHOW ALL;
RMAN> REPORT SCHEMA;
RMAN> LIST BACKUP SUMMARY;
RMAN> LIST BACKUP OF DATABASE;
RMAN> LIST BACKUP OF ARCHIVELOG ALL;
§§§

Xác nhận backup pieces có thể truy cập, control file/SPFILE có bản sao phù hợp, archived logs không bị thiếu và TDE wallet/keystore còn sẵn. Backup job thành công không thay thế restore validation hoặc restore rehearsal.

### 2.4. Ghi SCN và thời gian sự cố

Lấy current SCN để ghi trạng thái hiện tại:
§§§sql
SELECT current_scn
FROM v$database;
§§§

Nếu audit hoặc application log ghi timestamp của thao tác nhầm, chuyển timestamp đó về timezone thống nhất và xác định SCN gần nhất trước thao tác. Có thể dùng LogMiner, audit trail hoặc Flashback Transaction Query nếu được cấu hình và dữ liệu còn trong thời gian lưu giữ.

Không lấy SCN của một database khác để suy ra trực tiếp SCN trên database này. SCN là mốc nội bộ của database.

### 2.5. Kiểm tra Fast Recovery Area

§§§sql
SELECT name,
       space_limit,
       space_used,
       space_reclaimable,
       number_of_files
FROM v$recovery_file_dest;
§§§

FRA có thể chứa flashback logs, archived redo logs và backup. Nếu thiếu dung lượng, khả năng duy trì flashback window hoặc archive có thể bị ảnh hưởng. Không xóa file trong FRA bằng thao tác OS; dùng RMAN và chính sách retention phù hợp.

## 3. Khôi phục DROP TABLE bằng Recycle Bin

### 3.1. Recycle bin hoạt động thế nào?

Khi recycle bin được bật và object thuộc loại được hỗ trợ, lệnh DROP TABLE thông thường có thể đổi tên object thành tên dạng BIN$ và giữ object để có thể flashback. Đây không phải backup độc lập; object chỉ còn khả năng phục hồi trong thời gian nó chưa bị purge hoặc bị tái sử dụng dung lượng.

Kiểm tra trạng thái:
§§§sql
SHOW PARAMETER recyclebin;

SELECT original_name,
       object_name,
       type,
       droptime,
       dropscn
FROM user_recyclebin
ORDER BY droptime DESC;
§§§

DBA có thể kiểm tra DBA_RECYCLEBIN nếu có quyền. Tên và các cột hiển thị phụ thuộc view/release.

### 3.2. Khôi phục bảng về trước DROP

Ví dụ:
§§§sql
FLASHBACK TABLE APP.ORDERS
TO BEFORE DROP;
§§§

Nếu tên ORDERS đã được dùng lại, đổi tên object phục hồi:
§§§sql
FLASHBACK TABLE APP.ORDERS
TO BEFORE DROP
RENAME TO ORDERS_RECOVERED;
§§§

Sau đó xác minh object:
§§§sql
SELECT owner, table_name, status
FROM dba_tables
WHERE owner = 'APP'
  AND table_name IN ('ORDERS', 'ORDERS_RECOVERED');
§§§

Nếu có nhiều phiên bản cùng tên trong recycle bin, chọn đúng object theo drop time/object name. Có thể chỉ định tên BIN$ đã ghi nhận trong recycle bin khi cần chọn đúng lần drop.

### 3.3. Giới hạn của Flashback Drop

Flashback Drop không áp dụng cho mọi object và mọi tình huống. Các trường hợp thường không thể dùng gồm:
- DROP TABLE PURGE.
- Object đã bị PURGE RECYCLEBIN hoặc bị purge do áp lực dung lượng.
- Recycle bin bị tắt tại thời điểm drop.
- Object nằm trong nhóm không được recycle bin hỗ trợ.
- Các object phụ thuộc hoặc đặc tính schema có giới hạn riêng.

Nếu bảng đã biến mất khỏi recycle bin, chuyển sang phương án RMAN table recovery, PITR hoặc bản sao backup phù hợp.

### 3.4. Kiểm tra object phụ thuộc sau khi flashback

Không chỉ kiểm tra tên bảng. Xác nhận:
- Dữ liệu và số dòng.
- Index và trạng thái index.
- Constraint và trạng thái ENABLED/VALIDATED.
- Trigger.
- Grants.
- Synonyms.
- Views/packages phụ thuộc.
- Sequence hoặc identity nếu bảng dùng khóa sinh tự động.

Object được flashback không có nghĩa mọi consumer của nó đã hoạt động bình thường. Chạy test ứng dụng trước khi mở traffic.

## 4. Khôi phục DELETE đã COMMIT

### 4.1. Nếu transaction chưa COMMIT

Nếu câu DELETE vẫn nằm trong transaction chưa commit và session còn sống, có thể ROLLBACK:
§§§sql
ROLLBACK;
§§§

Đây là cách đơn giản nhất. Nếu application connection đã mất, không suy luận transaction outcome chỉ từ việc client nhận lỗi. Database có thể đã commit hoặc rollback; kiểm tra transaction/business record trước khi thao tác lại.

### 4.2. Flashback Table về SCN hoặc timestamp

Flashback Table có thể đưa bảng về trạng thái trước một mốc nếu dữ liệu undo còn đủ và object đáp ứng các điều kiện. Ví dụ:
§§§sql
ALTER TABLE APP.ORDERS ENABLE ROW MOVEMENT;

FLASHBACK TABLE APP.ORDERS
TO TIMESTAMP (SYSTIMESTAMP - INTERVAL '10' MINUTE);
§§§

Hoặc dùng SCN:
§§§sql
FLASHBACK TABLE APP.ORDERS
TO SCN 123456789;
§§§

Thay mốc ví dụ bằng SCN/timestamp đã điều tra. Cần quyền phù hợp, đủ undo và kiểm tra giới hạn của Flashback Table trong release đang dùng.

### 4.3. Cẩn thận với các giao dịch hợp lệ sau thời điểm đó

Flashback Table khôi phục trạng thái toàn bảng về mốc cũ. Nếu sau thời điểm đó có giao dịch hợp lệ cần giữ, flashback cả bảng có thể làm mất những thay đổi này.

Trong trường hợp chỉ một nhóm rows bị xóa nhầm, cân nhắc Flashback Query để đọc dữ liệu cũ rồi phục hồi có chọn lọc vào bảng hiện tại. Không thay toàn bảng nếu không có kế hoạch reconcile các giao dịch sau mốc.

### 4.4. Flashback Query để lấy lại dữ liệu

Ví dụ tạo bản sao rows tại SCN trước khi DELETE:
§§§sql
CREATE TABLE APP.ORDERS_RECOVERY AS
SELECT *
FROM APP.ORDERS AS OF SCN 123456789;
§§§

Sau đó so sánh bản sao với bảng hiện tại bằng primary key, xác định chính xác rows cần phục hồi và chèn lại theo business rules. Không INSERT toàn bộ bản sao vào bảng hiện tại nếu sẽ tạo duplicate hoặc ghi đè thay đổi hợp lệ.

Flashback Query phụ thuộc undo còn giữ dữ liệu cần đọc. UNDO_RETENTION là mục tiêu retention, không phải cam kết tuyệt đối nếu không có retention guarantee và đủ dung lượng. Có thể gặp ORA-01555 snapshot too old.

### 4.5. Flashback Transaction Query

Nếu cần hiểu transaction nào đã xóa rows, có thể kiểm tra flashback transaction views khi supplemental logging/undo và quyền cần thiết được cấu hình:
§§§sql
SELECT xid,
       start_scn,
       commit_scn,
       logon_user,
       operation,
       table_name,
       undo_sql
FROM flashback_transaction_query
WHERE table_owner = 'APP'
  AND table_name = 'ORDERS'
ORDER BY commit_scn DESC;
§§§

View và thông tin có sẵn phụ thuộc cấu hình, quyền và thời gian lưu undo. UNDO_SQL là thông tin hỗ trợ điều tra; không chạy hàng loạt câu SQL được sinh ra mà không review.

## 5. Khôi phục TRUNCATE TABLE

### 5.1. Vì sao TRUNCATE khác DELETE?

TRUNCATE là DDL và không tạo undo row-by-row theo cách DELETE thông thường. Nó giải phóng hoặc tái sử dụng segment theo semantics của Oracle và thực hiện implicit commit. Vì vậy không thể dùng ROLLBACK để lấy lại dữ liệu đã truncate.

### 5.2. Flashback Table không phải phương án mặc định cho TRUNCATE

Không giả định Flashback Table có thể quay ngược qua mọi DDL. TRUNCATE thay đổi cấu trúc/metadata segment và thường nằm ngoài khả năng phục hồi trực tiếp bằng Flashback Table. Kiểm tra release và operation cụ thể; với diễn tập chuẩn, chọn RMAN RECOVER TABLE, Flashback Database hoặc PITR phù hợp.

### 5.3. RMAN RECOVER TABLE

RMAN có thể phục hồi một table hoặc table partition tới một thời điểm, sử dụng auxiliary database và Data Pump để đưa object phục hồi trở lại database đích trong các release hỗ trợ.

Ví dụ cú pháp minh họa:
§§§text
RMAN> RECOVER TABLE APP.ORDERS
      UNTIL TIME "TO_DATE('2026-11-14 10:15:00',
                          'YYYY-MM-DD HH24:MI:SS')"
      AUXILIARY DESTINATION '/u02/rman_aux';
§§§

Cú pháp chi tiết, yêu cầu và khả năng phục hồi table phụ thuộc Oracle release, loại object và cấu hình. Kiểm tra Recovery Manager Reference đúng phiên bản. Cần backup/archived redo đủ tới thời điểm mục tiêu, dung lượng cho auxiliary instance và quyền cần thiết.

Nếu bảng hiện tại vẫn tồn tại, dùng REMAP TABLE hoặc tên đích khác theo syntax release để không ghi đè object hiện tại. Sau import, kiểm tra index, constraint, trigger, grants, dependent objects và dữ liệu.

### 5.4. Flashback Database hoặc database PITR

Nếu thao tác TRUNCATE ảnh hưởng nhiều bảng hoặc cần khôi phục database về trước DDL, có thể cân nhắc Flashback Database hoặc DBPITR. Hai cách này có phạm vi rộng, thường đưa toàn database về mốc cũ và có thể làm mất mọi giao dịch sau mốc. Chỉ chọn khi RPO và data reconciliation cho phép.

## 6. Khôi phục DROP TABLESPACE hoặc DROP USER

### 6.1. DROP TABLESPACE

DROP TABLESPACE có thể xóa metadata và tùy clause có thể xóa datafiles ở hệ điều hành. Recycle bin không phải cơ chế khôi phục tablespace. Nếu cần lấy lại dữ liệu:
- TSPITR nếu phạm vi tablespace và dependencies phù hợp.
- RMAN restore/recover database hoặc tablespace theo thiết kế.
- Khôi phục vào auxiliary/clone rồi Data Pump dữ liệu cần thiết.
- Phục hồi từ backup logic nếu có.

### 6.2. DROP USER CASCADE

DROP USER CASCADE có thể loại bỏ nhiều objects của schema. Không có một thao tác Flashback Drop duy nhất để tái tạo toàn bộ schema như ban đầu. Chọn RMAN RECOVER TABLE cho từng bảng cần thiết, PITR/clone schema/database hoặc import từ backup logic.

### 6.3. Xác định phạm vi phụ thuộc

Trước khi chọn TSPITR hoặc table recovery, lập dependency map:
- Foreign keys giữa tablespaces.
- Indexes và LOB segments ở tablespace khác.
- Materialized views/logs.
- Partitions và subpartitions.
- Procedures/views/triggers.
- Grants, synonyms và jobs.

TSPITR có giới hạn với SYSTEM, SYSAUX, active undo và các tablespace/dependency không thể tách độc lập. Đọc TSPITR restrictions đúng release trước khi chạy.

## 7. Mất datafile: điều tra trước khi restore

### 7.1. Phân biệt file bị xóa với storage không truy cập được

Một datafile có thể báo missing vì:
- File bị xóa/rename ở OS.
- Mount point hoặc ASM disk group không online.
- Storage path/network filesystem bị gián đoạn.
- Permission/ownership thay đổi.
- Control file trỏ tới đường dẫn cũ.
- File header bị corruption hoặc không đọc được.

Nếu storage chỉ tạm thời không truy cập, phục hồi storage/path có thể là phương án ít rủi ro hơn restore. Không tạo file rỗng cùng tên để làm biến mất lỗi; thao tác đó không phục hồi nội dung datafile.

### 7.2. Kiểm tra danh sách datafiles

§§§sql
SELECT file#,
       name,
       status,
       enabled,
       checkpoint_change#
FROM v$datafile
ORDER BY file#;
§§§

Kiểm tra header:
§§§sql
SELECT file#,
       status,
       error,
       recover,
       fuzzy,
       checkpoint_change#,
       creation_change#
FROM v$datafile_header
ORDER BY file#;
§§§

Kiểm tra file cần recovery:
§§§sql
SELECT file#,
       online_status,
       error,
       change#,
       time
FROM v$recover_file
ORDER BY file#;
§§§

Các view này cần quyền truy cập dynamic performance views. Không thấy row trong V$RECOVER_FILE không chứng minh file vật lý chắc chắn tốt; đối chiếu header, OS/storage và RMAN validation.

### 7.3. Xác định tablespace và loại datafile

§§§sql
SELECT d.file_id,
       d.file_name,
       d.tablespace_name,
       d.status,
       t.contents,
       t.status AS tablespace_status
FROM dba_data_files d
JOIN dba_tablespaces t
  ON t.tablespace_name = d.tablespace_name
ORDER BY d.file_id;
§§§

Xác định file thuộc:
- SYSTEM.
- SYSAUX.
- UNDO.
- TEMP.
- User tablespace.
- Read-only tablespace.
- Tablespace chứa dữ liệu ứng dụng trọng yếu.

TEMPFILE không phải datafile và có cách xử lý riêng; không áp dụng lệnh restore datafile cho tempfile như thể chúng giống nhau.

### 7.4. Datafile SYSTEM và UNDO

Không thể tùy ý offline datafile SYSTEM khi database đang mở. Mất SYSTEM hoặc datafile UNDO đang hoạt động có thể khiến database không tiếp tục hoạt động bình thường; recovery thường cần database ở MOUNT và thực hiện restore/recover theo hướng dẫn.

Không dùng ví dụ offline một user datafile cho SYSTEM hoặc active UNDO. Xác định đúng file number và role trước khi chạy lệnh.

### 7.5. Nếu file vẫn tồn tại nhưng path lỗi

Kiểm tra mount, ASM, permissions, owner, symbolic link, storage path và alert log. Khôi phục kết nối storage trước khi chạy RMAN nếu file gốc thực ra còn nguyên. Restore chồng lên file đang có thể ghi đè dữ liệu cần giữ.

## 8. Restore và recover một datafile trong ARCHIVELOG mode

### 8.1. Điều kiện

Thông thường cần:
- Database ở ARCHIVELOG mode.
- Backup datafile phù hợp.
- Archived redo logs liên tục từ checkpoint backup tới thời điểm recovery.
- Control file hoặc recovery catalog có metadata cần thiết.
- Đủ storage để restore.
- TDE wallet/keystore nếu datafile được mã hóa.

Nếu archived redo thiếu, có thể chỉ recover tới SCN cuối cùng còn redo; không tuyên bố database đã được phục hồi tới hiện tại.

### 8.2. Datafile user tablespace bị mất

Ví dụ datafile số 7 thuộc tablespace ứng dụng và database vẫn mở:
1. Xác định file 7 không còn truy cập được.
2. Kiểm tra các session/workload bị ảnh hưởng.
3. Đưa datafile offline theo runbook DBA nếu database cho phép.
4. Restore file bằng RMAN.
5. Apply archived redo bằng RECOVER.
6. Đưa file/tablespace online.
7. Kiểm tra data và application.

Ví dụ lệnh:
§§§sql
ALTER DATABASE DATAFILE 7 OFFLINE IMMEDIATE;
§§§

Lệnh OFFLINE IMMEDIATE có điều kiện và hệ quả media recovery; chỉ dùng theo quy trình đã xác nhận, đặc biệt phải biết database đang ARCHIVELOG và file không phải SYSTEM/active UNDO.

### 8.3. RMAN RESTORE và RECOVER

§§§text
RMAN> RESTORE DATAFILE 7;
RMAN> RECOVER DATAFILE 7;
§§§

RESTORE lấy bản sao datafile từ backup phù hợp. RECOVER apply redo cần thiết để đưa datafile tới consistency point. Hai bước không thay thế nhau.

Sau khi hoàn tất:
§§§sql
ALTER DATABASE DATAFILE 7 ONLINE;
§§§

Nếu toàn tablespace đã offline, kiểm tra trạng thái các datafiles và đưa tablespace online theo runbook. Không online file trước khi media recovery hoàn tất.

### 8.4. Khôi phục sang đường dẫn khác

Nếu đường dẫn cũ không còn hoặc muốn đặt file ở storage mới:
§§§text
RMAN> RUN {
  SET NEWNAME FOR DATAFILE 7
    TO '/u02/oradata/APPDB/users07.dbf';
  RESTORE DATAFILE 7;
  SWITCH DATAFILE 7;
  RECOVER DATAFILE 7;
}
§§§

Thay đường dẫn bằng path hợp lệ và kiểm tra quyền, dung lượng, ASM/filesystem và naming convention. Sau SWITCH, control file sẽ tham chiếu tên mới. Kiểm tra DBA_DATA_FILES/V$DATAFILE trước khi online.

### 8.5. Kiểm tra backup trước khi restore

Có thể xem backup:
§§§text
RMAN> LIST BACKUP OF DATAFILE 7;
RMAN> RESTORE VALIDATE DATAFILE 7;
§§§

RESTORE VALIDATE kiểm tra khả năng đọc backup cần thiết mà không ghi datafile phục hồi ra vị trí đích. Tùy backup type, RMAN configuration và release, phạm vi validation khác nhau; đọc output đầy đủ.

### 8.6. Không dùng OPEN RESETLOGS cho media recovery một datafile thông thường

Sau khi phục hồi một datafile trong database đang ở cùng incarnation và apply đủ redo, thông thường chỉ cần đưa datafile/tablespace online. OPEN RESETLOGS thường gắn với incomplete database recovery, backup control file recovery hoặc một số quy trình khác. Không chạy RESETLOGS theo thói quen sau mỗi RESTORE DATAFILE.

## 9. Mất SYSTEM, UNDO hoặc nhiều datafiles

### 9.1. SYSTEM datafile

Nếu SYSTEM datafile mất, database không thể hoạt động như bình thường. DBA thường cần shutdown/đưa database về MOUNT, restore và recover datafile, sau đó mở database khi recovery hoàn tất. Thực hiện theo đúng release và trạng thái control file.

### 9.2. UNDO datafile

Mất datafile chứa active undo có thể ảnh hưởng transaction recovery và khả năng mở database. Không tạo undo tablespace mới rồi bỏ qua datafile cũ mà không có kế hoạch được Oracle hỗ trợ. Xác định undo tablespace hiện tại, trạng thái transaction và hướng dẫn recovery cho release.

### 9.3. Nhiều datafiles bị mất

Nếu nhiều file hoặc cả disk group bị mất, cân nhắc restore/recover tablespace hoặc database từ RMAN, Data Guard hoặc storage backup. Tính lại RTO; phục hồi nhiều datafiles riêng lẻ có thể không đơn giản hơn full database recovery.

### 9.4. NOARCHIVELOG mode

Trong NOARCHIVELOG, archived redo logs không được tạo để roll forward qua các log switch. Nếu một datafile read-write bị mất sau khi database đã thay đổi kể từ backup, thường không thể phục hồi riêng file đó tới hiện tại bằng redo đầy đủ.

Phương án chuẩn thường là restore một backup consistent của toàn database và chấp nhận mất các thay đổi sau backup, trừ các trường hợp đặc biệt đã được Oracle tài liệu hóa như datafile/tablespace offline sạch và không có thay đổi sau đó. Không giả định có thể restore một datafile cũ rồi mở database cùng các datafiles mới hơn.

### 9.5. Restore toàn database từ consistent backup

Ở mức khái quát:
1. Dừng database và xác định backup consistent.
2. Khôi phục control file/SPFILE nếu cần.
3. Restore toàn bộ datafiles từ cùng consistent backup.
4. Recover theo phạm vi redo có sẵn và đúng chế độ.
5. Mở database theo yêu cầu của recovery path, có thể cần RESETLOGS.
6. Kiểm tra toàn database và chấp nhận RPO thực tế.

Ví dụ lệnh phụ thuộc DBID, control file, backup location và trạng thái:
§§§text
RMAN> STARTUP MOUNT;
RMAN> RESTORE DATABASE;
RMAN> RECOVER DATABASE;
§§§

Không chạy đoạn này như một script chung trên production. Cần runbook cụ thể cho control file autobackup, DBID, channels, catalog, backup pieces, archived logs, TDE và OPEN RESETLOGS.

## 10. Lựa chọn recovery method

### 10.1. Flashback Drop

Dùng khi:
- DROP TABLE thông thường.
- Recycle bin còn object.
- Object được hỗ trợ.
- Chỉ cần phục hồi table vừa drop.

Ưu điểm: nhanh, phạm vi hẹp. Giới hạn: không cứu được PURGE hoặc object đã biến mất khỏi recycle bin.

### 10.2. Flashback Table/Query

Dùng khi:
- DML nhầm đã commit.
- Undo còn đủ.
- Cần phục hồi một bảng hoặc trích dữ liệu cũ.
- Không có DDL phá vỡ khả năng flashback.
- Có thể xử lý các thay đổi hợp lệ sau mốc.

Flashback Table đưa cả table về mốc cũ; Flashback Query đọc dữ liệu cũ để reconcile có chọn lọc.

### 10.3. RMAN RECOVER TABLE

Dùng khi:
- Table đã DROP PURGE hoặc TRUNCATE.
- Cần phục hồi một table/partition mà không muốn đưa toàn database về quá khứ.
- Backup/archived redo và auxiliary space đáp ứng điều kiện.
- Oracle release hỗ trợ object recovery này.

RMAN tạo auxiliary recovery environment và dùng Data Pump để import table đã phục hồi. Cần kiểm tra constraints, indexes, grants và dependencies sau đó.

### 10.4. Tablespace Point-in-Time Recovery (TSPITR)

Dùng khi:
- Lỗi logic nằm trong phạm vi một hoặc một nhóm tablespaces.
- Có thể đưa tablespace set về thời điểm trước lỗi.
- Tablespace và dependencies đáp ứng TSPITR restrictions.
- Không muốn phục hồi toàn database.

TSPITR dùng auxiliary instance và có yêu cầu về tablespace set, dependencies, SYSTEM/UNDO/SYSAUX và các object liên quan. Không chọn chỉ vì object bị mất nằm trong một tablespace; cần phân tích dependency trước.

### 10.5. Database Point-in-Time Recovery (DBPITR)

Dùng khi:
- Database-wide logical error hoặc mất nhiều object.
- Cần đưa toàn database về trước mốc sự cố.
- RPO chấp nhận mất mọi thay đổi sau mốc hoặc có thể replay chúng.

DBPITR tác động toàn database, thường kết thúc bằng OPEN RESETLOGS và tạo database incarnation mới. Các giao dịch hợp lệ sau recovery point sẽ không còn trong database đã phục hồi.

### 10.6. Flashback Database

Dùng khi:
- Flashback Database đã bật trước sự cố.
- Flashback logs còn bao phủ mốc cần quay lại.
- Recovery scope toàn database phù hợp.
- Có thể chấp nhận mất thay đổi sau mốc hoặc có kế hoạch replay.

Flashback Database thường nhanh hơn restore toàn database trong một số tình huống, nhưng không thay thế backup. Không dùng nó như công cụ phục hồi riêng một datafile bị xóa mà không kiểm tra điều kiện.

### 10.7. Block Media Recovery

Dùng khi một số block bị corrupt và database/backup/redo hỗ trợ block recovery. Nó phục hồi block vật lý, không hoàn tác một câu DELETE hoặc DROP hợp lệ về mặt SQL.

## 11. Flashback Database và Restore Point

### 11.1. Kiểm tra Flashback Database

§§§sql
SELECT flashback_on
FROM v$database;

SELECT name,
       guarantee_flashback_database,
       time,
       scn,
       storage_size
FROM v$restore_point
ORDER BY time DESC;
§§§

Kiểm tra trạng thái flashback, restore points và FRA capacity. Restore point thường không có nghĩa là có đủ flashback logs nếu không được guarantee; cần xác nhận chính xác trạng thái.

### 11.2. Tạo Guaranteed Restore Point trước thay đổi

Ví dụ trong maintenance plan:
§§§sql
CREATE RESTORE POINT BEFORE_CHANGE
GUARANTEE FLASHBACK DATABASE;
§§§

Guaranteed restore point cần Flashback Database prerequisites và dung lượng FRA đủ. Giữ restore point càng lâu, flashback logs cần giữ càng nhiều; theo dõi FRA liên tục.

### 11.3. Flashback về restore point

Một quy trình tổng quát có thể yêu cầu:
§§§sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
FLASHBACK DATABASE TO RESTORE POINT BEFORE_CHANGE;
ALTER DATABASE OPEN RESETLOGS;
§§§

Lệnh thực tế phụ thuộc database architecture, release, RAC/CDB/PDB và trạng thái recovery. Chỉ thực hiện sau khi DBA xác nhận target restore point và tác động mất dữ liệu. Sau khi open resetlogs, database tạo incarnation mới; cần backup theo chính sách ngay sau recovery.

### 11.4. Xóa restore point

Chỉ drop GRP khi rollback window đã đóng và có phê duyệt:
§§§sql
DROP RESTORE POINT BEFORE_CHANGE;
§§§

Không xóa GRP trong lúc đang cần fallback. Không để GRP tồn tại vô thời hạn mà không giám sát FRA.

## 12. RMAN RECOVER TABLE và TSPITR

### 12.1. RMAN table recovery hoạt động ra sao?

RMAN phục hồi bản sao database phụ trợ tới thời điểm trước lỗi, export table từ auxiliary database rồi import vào database đích. Database production không cần quay toàn bộ về thời điểm cũ.

Các bước logic:
1. Chọn table/partition và recovery time.
2. Xác nhận backup/archived redo.
3. Chuẩn bị auxiliary destination và dung lượng.
4. Chạy RECOVER TABLE.
5. RMAN tạo auxiliary instance, restore/recover.
6. RMAN export table và import về database target.
7. Kiểm tra object và dữ liệu phục hồi.

### 12.2. Cú pháp minh họa

§§§text
RMAN> RECOVER TABLE APP.ORDERS
      UNTIL SCN 123456789
      AUXILIARY DESTINATION '/u02/rman_aux';
§§§

Thay SCN, schema/table và đường dẫn theo môi trường. Nếu cần đổi tên bảng phục hồi, dùng REMAP TABLE theo syntax của release. Xác minh hỗ trợ đối với partition, object type, encrypted tablespace và multitenant.

### 12.3. RMAN table recovery không phải backup logic

RMAN cần backup và redo để dựng auxiliary database. Kết quả import table cần được kiểm tra lại về:
- Row counts và business totals.
- Primary/unique/foreign keys.
- Indexes và index status.
- Triggers.
- Grants và synonyms.
- LOB data.
- Dependencies và application behavior.

### 12.4. TSPITR

TSPITR phục hồi tablespace set về một mốc thời gian bằng auxiliary instance. Sau đó tablespace set được tích hợp trở lại database theo quy trình Oracle. Kiểm tra:
- Tablespace set cần phục hồi.
- Objects có dependency qua tablespaces khác.
- Referential integrity và foreign keys.
- Tablespace có chứa SYSTEM/UNDO/SYSAUX hay không.
- Read-only tablespace và transportable dependencies.
- Backup/redo và auxiliary destination.

### 12.5. Khi nào chọn RMAN RECOVER TABLE thay vì TSPITR?

Nếu chỉ một table bị TRUNCATE hoặc DROP PURGE, RMAN RECOVER TABLE thường có phạm vi hẹp hơn. Nếu nhiều object trong một tablespace bị thay đổi và cần khôi phục đồng bộ, TSPITR có thể phù hợp hơn. Nếu lỗi lan ra toàn database, cân nhắc DBPITR/Flashback Database.

## 13. Data Guard có thay thế backup không?

### 13.1. Physical standby nhận redo

Physical standby apply redo từ primary. Nếu người dùng thực hiện DROP TABLE hoặc DELETE hợp lệ trên primary, redo tương ứng cũng được apply sang standby. Vì vậy standby không tự động bảo vệ khỏi logical deletion.
 
### 13.2. Delayed apply

Một số kiến trúc có thể cấu hình apply delay để giữ standby ở trạng thái cũ hơn trong một khoảng thời gian. Khi phát hiện lỗi, có thể dừng apply trước khi redo lỗi được áp dụng. Tuy nhiên cần hiểu lag, role transition và quy trình khôi phục standby; delayed standby không thay thế backup.

### 13.3. Snapshot standby

Snapshot standby có thể được mở read-write trong một thời gian và sau đó chuyển lại physical standby theo quy trình hỗ trợ. Đây là một mô hình kiểm thử/khai thác riêng, không phải bản backup độc lập.

### 13.4. Thiết kế DR

Kết hợp:
- RMAN backup.
- Archived redo và offsite/immutable copy.
- Data Guard.
- Flashback Database/restore point nếu phù hợp.
- Logical export cho object trọng yếu.
- Restore rehearsal định kỳ.
- Runbook và RPO/RTO đã kiểm chứng.

## 14. Quy trình diễn tập chuẩn

### Giai đoạn A — Chuẩn bị lab

1. Dùng database lab/clone riêng, không phải production.
2. Tạo tablespace chuyên dụng RECOVERY_LAB.
3. Tạo bảng mẫu và nạp dữ liệu có khóa nghiệp vụ.
4. Tạo index, constraint, trigger và sequence cần thiết.
5. Bật ARCHIVELOG nếu lab cần diễn tập media recovery.
6. Cấu hình backup và archived log.
7. Ghi SCN/time baseline.
8. Xác nhận RMAN restore validation và đủ dung lượng.

### Giai đoạn B — Diễn tập logical deletion

Thực hiện DROP TABLE thông thường và phục hồi bằng recycle bin. Lặp lại với PURGE để chứng minh recycle bin không còn tác dụng. Tạo một bảng khác và DELETE có COMMIT để thực hành Flashback Table hoặc Flashback Query.

### Giai đoạn C — Diễn tập TRUNCATE

Tạo một bản sao bảng test, ghi mốc SCN, backup database và thực hiện TRUNCATE trên bảng lab. Thực hành RMAN RECOVER TABLE vào tên mới. So sánh dữ liệu phục hồi với baseline.

### Giai đoạn D — Diễn tập mất datafile

Chỉ sử dụng datafile thuộc tablespace lab không quan trọng:
1. Backup tablespace/datafile và archived logs.
2. Đưa tablespace offline bình thường theo runbook.
3. Đóng/move file trong lab theo cách an toàn, giữ bản sao quarantine.
4. Thử online để ghi nhận lỗi missing file.
5. Dùng RMAN RESTORE DATAFILE và RECOVER DATAFILE.
6. Đưa file/tablespace online.
7. Xác nhận header, row counts và application access.

Không xóa datafile đang online bằng OS. Không mô phỏng bằng SYSTEM hoặc active UNDO datafile.

### Giai đoạn E — Đo kết quả

Ghi:
- Detection time.
- Decision time.
- Recovery start/end.
- Data loss hoặc transaction replay.
- RTO thực tế.
- RPO thực tế.
- Lỗi phát sinh trong quá trình recovery.
- Evidence và owner phê duyệt.

## 15. Lab 1: DROP TABLE và Flashback Drop

### Bước 1 — Tạo bảng mẫu

§§§sql
CREATE TABLE APP.RECOVERY_DROP_LAB (
    ID NUMBER PRIMARY KEY,
    DESCRIPTION VARCHAR2(100 CHAR),
    CREATED_AT TIMESTAMP DEFAULT SYSTIMESTAMP
);

INSERT INTO APP.RECOVERY_DROP_LAB (ID, DESCRIPTION)
VALUES (1, 'before drop');

COMMIT;
§§§

### Bước 2 — Ghi baseline

§§§sql
SELECT COUNT(*) AS row_count,
       MIN(id) AS min_id,
       MAX(id) AS max_id
FROM app.recovery_drop_lab;

SELECT current_scn
FROM v$database;
§§§

### Bước 3 — Drop không purge

§§§sql
DROP TABLE APP.RECOVERY_DROP_LAB;
§§§

### Bước 4 — Kiểm tra recycle bin

§§§sql
SELECT original_name, object_name, droptime
FROM user_recyclebin
WHERE original_name = 'RECOVERY_DROP_LAB';
§§§

### Bước 5 — Flashback

§§§sql
FLASHBACK TABLE APP.RECOVERY_DROP_LAB
TO BEFORE DROP;
§§§

### Bước 6 — Xác minh

§§§sql
SELECT * FROM APP.RECOVERY_DROP_LAB;
§§§

Kiểm tra constraint/index/grant và ghi thời gian phục hồi. Lặp lại với DROP TABLE ... PURGE trong một object test khác để so sánh.

## 16. Lab 2: DELETE đã COMMIT và Flashback

### Bước 1 — Tạo dữ liệu

§§§sql
CREATE TABLE APP.RECOVERY_DELETE_LAB (
    ID NUMBER PRIMARY KEY,
    AMOUNT NUMBER(12,2),
    STATUS VARCHAR2(20 CHAR)
);

INSERT INTO APP.RECOVERY_DELETE_LAB VALUES (1, 100, 'NEW');
INSERT INTO APP.RECOVERY_DELETE_LAB VALUES (2, 200, 'NEW');
INSERT INTO APP.RECOVERY_DELETE_LAB VALUES (3, 300, 'NEW');
COMMIT;
§§§

### Bước 2 — Ghi SCN

§§§sql
SELECT current_scn
FROM v$database;
§§§

Lưu SCN trước thao tác DELETE.

### Bước 3 — Xóa nhầm

§§§sql
DELETE FROM APP.RECOVERY_DELETE_LAB;
COMMIT;
§§§

### Bước 4 — Flashback Table

§§§sql
ALTER TABLE APP.RECOVERY_DELETE_LAB ENABLE ROW MOVEMENT;

FLASHBACK TABLE APP.RECOVERY_DELETE_LAB
TO SCN 123456789;
§§§

Dùng SCN thực tế đã ghi trong lab. Nếu có DML hợp lệ sau mốc, thử phương án Flashback Query vào bảng recovery riêng rồi insert lại các key cần thiết.

### Bước 5 — Xác minh

§§§sql
SELECT COUNT(*) AS row_count,
       SUM(amount) AS amount_total
FROM app.recovery_delete_lab;
§§§

Đối chiếu với baseline. Ghi nhận undo retention và thời gian từ khi delete tới khi flashback.

## 17. Lab 3: TRUNCATE và RMAN RECOVER TABLE

### Bước 1 — Chuẩn bị backup

Tạo bảng lab và ghi baseline. Chạy RMAN backup database cùng archived logs theo chính sách lab. Xác nhận backup có thể đọc.

### Bước 2 — Ghi recovery point

Ghi SCN hoặc timestamp ngay trước TRUNCATE.

### Bước 3 — TRUNCATE

§§§sql
TRUNCATE TABLE APP.RECOVERY_TRUNCATE_LAB;
§§§

### Bước 4 — RMAN recover table

Ví dụ:
§§§text
RMAN> RECOVER TABLE APP.RECOVERY_TRUNCATE_LAB
      UNTIL SCN 123456789
      AUXILIARY DESTINATION '/u02/rman_aux'
      REMAP TABLE 'APP'.'RECOVERY_TRUNCATE_LAB':'RECOVERY_TRUNCATE_RESTORED';
§§§

Kiểm tra cú pháp REMAP TABLE đúng với Oracle release. Dùng tên đích khác để bảo toàn bảng hiện tại và tránh ghi đè.

### Bước 5 — So sánh

§§§sql
SELECT COUNT(*) AS row_count,
       SUM(amount) AS amount_total
FROM app.recovery_truncate_restored;
§§§

Kiểm tra index, constraint, grants, triggers và dependent objects sau import.

## 18. Lab 4: Mất một datafile

### Bước 1 — Tạo tablespace lab

§§§sql
CREATE TABLESPACE RECOVERY_LAB
DATAFILE '/u02/oradata/APPDB/recovery_lab01.dbf'
SIZE 200M
AUTOEXTEND ON NEXT 20M MAXSIZE 1G;
§§§

Đường dẫn là ví dụ. Dùng đường dẫn hợp lệ trên host lab.

### Bước 2 — Tạo dữ liệu

§§§sql
CREATE TABLE APP.RECOVERY_FILE_LAB (
    ID NUMBER PRIMARY KEY,
    DESCRIPTION VARCHAR2(100 CHAR)
) TABLESPACE RECOVERY_LAB;

INSERT INTO APP.RECOVERY_FILE_LAB
VALUES (1, 'file recovery test');

COMMIT;
§§§

### Bước 3 — Xác định file number

§§§sql
SELECT file_id, file_name, tablespace_name
FROM dba_data_files
WHERE tablespace_name = 'RECOVERY_LAB';
§§§

Ghi file number. Backup datafile/tablespace và archived logs.

### Bước 4 — Offline sạch

§§§sql
ALTER TABLESPACE RECOVERY_LAB OFFLINE NORMAL;
§§§

Xác nhận tablespace đã offline và checkpoint hoàn tất. Trong lab, move file sang thư mục quarantine sau khi offline. Không xóa file; giữ bản sao để có thể hoàn nguyên nếu bài thực hành bị lỗi.

### Bước 5 — Thử online

§§§sql
ALTER TABLESPACE RECOVERY_LAB ONLINE;
§§§

Ghi lại lỗi missing file. Đưa trạng thái về đúng theo runbook trước khi restore.

### Bước 6 — Restore/recover

§§§text
RMAN> RESTORE DATAFILE 7;
RMAN> RECOVER DATAFILE 7;
§§§

Thay 7 bằng file number thực tế. Nếu file ở đường dẫn mới, dùng SET NEWNAME và SWITCH DATAFILE theo runbook.

### Bước 7 — Online và xác minh

§§§sql
ALTER TABLESPACE RECOVERY_LAB ONLINE;

SELECT COUNT(*)
FROM APP.RECOVERY_FILE_LAB;

SELECT file_id, file_name, tablespace_name, status
FROM dba_data_files
WHERE tablespace_name = 'RECOVERY_LAB';
§§§

Kiểm tra datafile header, RMAN output và application query. Không chỉ dựa vào trạng thái ONLINE.

## 19. Kiểm tra sau recovery

### 19.1. Kiểm tra datafile và header

§§§sql
SELECT file#,
       name,
       status,
       enabled,
       checkpoint_change#
FROM v$datafile
ORDER BY file#;

SELECT file#,
       status,
       error,
       recover,
       fuzzy,
       checkpoint_change#
FROM v$datafile_header
ORDER BY file#;

SELECT *
FROM v$recover_file;
§§§

Mục tiêu là xác nhận file đúng đường dẫn, header đọc được và không còn yêu cầu media recovery chưa xử lý.

### 19.2. Kiểm tra object

§§§sql
SELECT owner, object_type, object_name, status
FROM dba_objects
WHERE owner = 'APP'
  AND status <> 'VALID'
ORDER BY object_type, object_name;
§§§

Kiểm tra thêm constraints, indexes, triggers, grants, synonyms và materialized views liên quan. Một bảng phục hồi được không tự động có nghĩa toàn bộ dependency đã sẵn sàng.

### 19.3. Đối soát dữ liệu

So sánh:
- Exact row counts.
- Min/max key.
- Business aggregates.
- Null counts.
- Duplicate keys.
- Orphan references.
- LOB length/content khi liên quan.
- Dữ liệu phát sinh sau recovery point.

Dùng snapshot và business cutoff rõ ràng. Không so sánh source live với target đã phục hồi về quá khứ mà không tính delta.

### 19.4. Kiểm tra ứng dụng

- Kết nối bằng đúng runtime user.
- Chạy truy vấn đọc trọng yếu.
- Thử ghi có kiểm soát nếu được phê duyệt.
- Kiểm tra sequence/identity.
- Kiểm tra batch jobs và integrations.
- Kiểm tra error rate và latency.
- Xác nhận không có hai writer ngoài thiết kế.

### 19.5. Backup sau recovery

Sau incomplete recovery hoặc OPEN RESETLOGS, database có incarnation mới. Chạy backup mới theo chính sách và xác nhận archived redo/backup strategy tiếp tục hoạt động. Ghi lại incarnation, recovery SCN/time và trạng thái Data Guard.

## 20. Các lỗi và bẫy thường gặp

### 20.1. Chạy CREATE DATAFILE để thay file đã mất

Tạo file rỗng không khôi phục block data cũ. Dùng RMAN restore từ backup đúng; không tạo file rỗng cùng tên để làm database mở lại.

### 20.2. Đưa datafile ONLINE trước khi recover

Nếu file cần media recovery, online sớm có thể thất bại hoặc làm phức tạp recovery. Thực hiện RESTORE, RECOVER, rồi mới ONLINE.

### 20.3. Dùng Flashback Table cho TRUNCATE

Không giả định Flashback Table quay qua được mọi DDL. Với TRUNCATE, dùng phương án đã được xác nhận như RMAN RECOVER TABLE, Flashback Database hoặc PITR.

### 20.4. Nhầm DROP với DROP PURGE

DROP thông thường có thể đưa object vào recycle bin. PURGE bỏ qua hoặc loại object khỏi recycle bin. Kiểm tra recycle bin trước khi chọn recovery.

### 20.5. Chỉ restore datafile mà không apply redo

RESTORE chỉ đưa file về backup image. RECOVER apply redo để đồng bộ tới recovery target. Thiếu bước recover có thể khiến file không nhất quán với database.

### 20.6. Dùng backup cũ trong NOARCHIVELOG với datafiles mới

Một datafile cũ có thể không đồng nhất với các datafiles khác. Trong NOARCHIVELOG, thường phải restore consistent whole-database backup để đảm bảo consistency.

### 20.7. Dùng OPEN RESETLOGS sau mọi recovery

RESETLOGS không phải lệnh kết thúc chung cho mọi media recovery. Dùng đúng theo recovery path; phục hồi một datafile thông thường thường không yêu cầu RESETLOGS.

### 20.8. Không tính giao dịch sau mốc

Flashback/PITR có thể xóa giao dịch hợp lệ sau recovery point. Lập danh sách giao dịch cần replay hoặc reconcile trước khi chọn mốc.

### 20.9. Coi Data Guard là backup

Logical deletion có thể được apply sang standby. Cần backup độc lập, delayed apply hoặc cơ chế bảo vệ khác theo thiết kế.

### 20.10. Xóa file trong FRA bằng OS

Không xóa flashback logs/archived logs/backup bằng thao tác filesystem. Dùng RMAN retention policy và lệnh quản lý phù hợp.

### 20.11. Không bảo vệ TDE wallet

Backup datafile mã hóa mà thiếu keystore/wallet có thể không phục hồi được. Kiểm tra wallet backup, password và quyền truy cập trước incident.

### 20.12. Không diễn tập

Một runbook chưa được chạy thử có thể thiếu quyền, đường dẫn, dung lượng, archived logs hoặc thời gian. Đo RTO thực tế trong lab/clone định kỳ.

## 21. Decision matrix lựa chọn phương án

| Tình huống | Recovery ưu tiên | Phạm vi | Cần lưu ý |
|---|---|---|---|
| DELETE chưa commit | ROLLBACK | Transaction | Kiểm tra session còn hoạt động |
| DELETE đã commit, undo còn | Flashback Table/Query | Table/rows | Reconcile thay đổi sau mốc |
| DROP TABLE, recycle bin còn | Flashback Drop | Table | Chọn đúng lần drop |
| DROP TABLE PURGE | RMAN RECOVER TABLE | Table | Auxiliary, backup, redo |
| TRUNCATE TABLE | RMAN RECOVER TABLE hoặc PITR | Table/database | Không dựa vào rollback |
| DROP TABLESPACE | TSPITR hoặc database recovery | Tablespace/database | Dependency restrictions |
| Một user datafile mất, ARCHIVELOG | RESTORE + RECOVER DATAFILE | Datafile | Backup và redo liên tục |
| SYSTEM/UNDO file mất | Mount-level database recovery | Database-critical file | Không offline tùy tiện |
| Một vài block corrupt | Block media recovery | Blocks | Cần backup và redo |
| Database-wide logical error | Flashback Database/DBPITR | Whole database | Mất thay đổi sau mốc |
| NOARCHIVELOG và file read-write mất | Restore consistent database backup | Whole database | RPO thường tới backup |
| Primary hỏng, standby sẵn sàng | Data Guard failover | Database role | Không thay thế logical recovery |

Ma trận chỉ là điểm khởi đầu. Chọn cuối cùng phải dựa trên Oracle release, database architecture, backup/redo thực tế, RPO/RTO và tác động nghiệp vụ.

## 22. Runbook phục hồi production

### Trước khi chạy lệnh

- Xác nhận database identity và environment.
- Xác nhận object/file number bị ảnh hưởng.
- Chụp trạng thái hiện tại và log.
- Dừng workload có thể làm tăng data divergence.
- Kiểm tra backup, redo, FRA và wallet.
- Xác định recovery point.
- Chọn recovery method và đánh giá blast radius.
- Lấy phê duyệt từ DBA lead/change owner.
- Ghi lệnh, expected result và stop condition.

### Trong recovery

1. Chạy lệnh theo từng bước, không gộp thành một script mù.
2. Lưu RMAN output và SQL output.
3. Dừng nếu backup piece/archived log thiếu.
4. Dừng nếu SCN/time không đúng.
5. Không mở traffic khi chưa xác minh recovery hoàn tất.
6. Ghi thời điểm bắt đầu/kết thúc và người thực hiện.

### Sau recovery

1. Kiểm tra file/object state.
2. Đối soát dữ liệu.
3. Xác minh constraints/indexes/dependencies.
4. Kiểm thử application.
5. Xác định giao dịch cần replay.
6. Chạy backup mới nếu cần.
7. Xác nhận standby/replication.
8. Business owner ký xác nhận.
9. Lưu evidence và cập nhật RCA.

## 23. RPO, RTO và tác động nghiệp vụ

### 23.1. RPO

Recovery Point Objective là lượng dữ liệu tối đa được phép mất. Ví dụ:
- Flashback Table về 10 phút trước có thể làm mất thay đổi hợp lệ của bảng trong 10 phút đó.
- DBPITR về SCN trước lỗi có thể làm mất toàn bộ transaction database sau SCN.
- Restore NOARCHIVELOG từ consistent backup có thể mất mọi giao dịch sau backup.

### 23.2. RTO

Recovery Time Objective là thời gian mục tiêu để hệ thống hoạt động trở lại. Đo:
- Phát hiện sự cố.
- Quyết định recovery.
- Tìm backup/redo.
- Restore/auxiliary setup.
- Apply redo.
- Validation và reconciliation.
- Application reconnect.
- Business sign-off.

### 23.3. Blast radius

Ước lượng phạm vi ảnh hưởng:
- Một bảng.
- Một schema.
- Một tablespace.
- Một PDB.
- Toàn CDB/database.
- Nhiều database hoặc hệ thống ngoài.

Chọn phương án có phạm vi nhỏ nhất đáp ứng được tính nhất quán. Không chọn full database PITR nếu chỉ một bảng có thể được phục hồi an toàn bằng RMAN RECOVER TABLE.

### 23.4. Giao dịch ngoài database

Payment, email, message queue, file và API side effects không tự biến mất khi database được flashback. Cần idempotency, outbox/inbox, compensation và reconciliation. Trước khi replay, xác định giao dịch nào đã được xử lý ở hệ thống ngoài.

## 24. Bài tập tổng hợp

Cho một database ứng dụng có:
- APP.ORDERS trong tablespace APP_DATA.
- APP.CUSTOMER trong cùng tablespace.
- Một datafile chứa APP_DATA.
- RMAN backup hàng đêm và archived redo logs.
- Flashback Database đang bật.
- Một Spring Boot application có connection pool.

Thực hiện các tình huống trên lab:
1. DROP APP.ORDERS không PURGE.
2. DROP một bảng khác với PURGE.
3. DELETE tất cả rows của một bảng rồi COMMIT.
4. TRUNCATE một bảng.
5. Mất datafile của APP_DATA khi tablespace đã offline trong lab.
6. Tạo một transaction hợp lệ sau recovery point rồi đánh giá nguy cơ mất transaction.
7. Giả lập database-wide logical error và so sánh Flashback Database với DBPITR.
8. Thực hiện restore validation trước recovery.
9. Ghi RPO/RTO cho từng phương án.
10. Trình bày lý do chọn recovery method và người phê duyệt.

Mỗi tình huống phải lưu command log, start/end time, SCN, backup identifiers, kết quả đối soát và lesson learned.

## 25. Checklist diễn tập

- [ ] Lab/clone cô lập được xác nhận.
- [ ] Không sử dụng production datafile cho thao tác phá hủy.
- [ ] Database identity, release, ARCHIVELOG và role đã ghi.
- [ ] Backup database/datafile và archived logs có thể đọc.
- [ ] Control file/SPFILE/TDE wallet có bản sao.
- [ ] FRA và auxiliary destination đủ dung lượng.
- [ ] Recovery SCN/timestamp được ghi.
- [ ] Đã phân biệt DELETE, TRUNCATE, DROP và DROP PURGE.
- [ ] Recycle bin đã được kiểm tra.
- [ ] Flashback Table/Query prerequisites đã được xác nhận.
- [ ] RMAN RECOVER TABLE đã được diễn tập nếu release hỗ trợ.
- [ ] TSPITR dependencies/restrictions đã được xem xét.
- [ ] Datafile number, tablespace và file type đã được xác định.
- [ ] SYSTEM/UNDO datafile không bị offline tùy tiện.
- [ ] RMAN RESTORE và RECOVER được thực hiện đúng thứ tự.
- [ ] Đã hiểu khác biệt ARCHIVELOG và NOARCHIVELOG.
- [ ] Không dùng OPEN RESETLOGS cho media recovery đơn file thông thường.
- [ ] Đã kiểm tra datafile header và V$RECOVER_FILE.
- [ ] Đã đối soát rows, keys, totals và dependencies.
- [ ] Đã xác định transaction sau recovery point.
- [ ] Đã kiểm tra Data Guard/standby không bị logical error apply.
- [ ] RPO/RTO thực tế được đo.
- [ ] Có business sign-off và recovery evidence.
- [ ] Backup mới được thực hiện sau recovery nếu cần.

## 26. Câu hỏi tự kiểm tra

1. Logical data loss khác physical datafile loss ở điểm nào?
2. Vì sao cần xác định transaction đã COMMIT hay chưa trước khi recovery?
3. Recycle bin giúp phục hồi DROP TABLE như thế nào?
4. DROP TABLE PURGE khác DROP TABLE thông thường ra sao?
5. Vì sao Flashback Drop không thay thế RMAN backup?
6. Flashback Table cần điều kiện nào về undo và row movement?
7. Vì sao Flashback Table toàn bảng có thể làm mất thay đổi hợp lệ sau mốc?
8. Flashback Query hỗ trợ phục hồi có chọn lọc như thế nào?
9. Vì sao TRUNCATE không thể phục hồi bằng ROLLBACK?
10. Khi nào nên dùng RMAN RECOVER TABLE?
11. RMAN RECOVER TABLE sử dụng auxiliary database và Data Pump ra sao?
12. TSPITR phù hợp với loại sự cố nào?
13. Vì sao TSPITR cần kiểm tra tablespace dependencies?
14. DBPITR ảnh hưởng dữ liệu toàn database như thế nào?
15. Flashback Database khác RMAN restore/recover ra sao?
16. Guaranteed restore point cần theo dõi tài nguyên nào?
17. Vì sao Data Guard physical standby có thể nhận cả thao tác DROP nhầm?
18. Làm sao phân biệt datafile thực sự bị xóa với storage mount bị mất?
19. V$DATAFILE_HEADER và V$RECOVER_FILE cung cấp thông tin gì?
20. Vì sao không được tạo datafile rỗng để thay file bị mất?
21. Tại sao cần RESTORE rồi mới RECOVER?
22. Khi nào một datafile có thể được phục hồi online và khi nào cần MOUNT?
23. Vì sao không thể tùy tiện offline SYSTEM hoặc active UNDO datafile?
24. ARCHIVELOG và NOARCHIVELOG khác nhau ra sao khi mất datafile?
25. Khi nào cần restore consistent whole-database backup?
26. Vì sao media recovery một datafile thông thường không cần OPEN RESETLOGS?
27. Block media recovery khác phục hồi logical deletion như thế nào?
28. Những điều kiện nào phải kiểm tra trước khi RMAN RECOVER TABLE?
29. RPO/RTO ảnh hưởng lựa chọn recovery method ra sao?
30. Sau recovery cần xác nhận những gì trước khi mở lại traffic?

**Nguyên tắc cần nhớ:** Chọn recovery theo loại sự cố và phạm vi ảnh hưởng. DROP TABLE có thể dùng recycle bin; DELETE đã commit có thể dùng Flashback Table/Query nếu undo còn; TRUNCATE hoặc DROP PURGE thường cần RMAN table recovery hoặc PITR; mất datafile cần RESTORE và RECOVER từ backup/redo. ARCHIVELOG cho phép roll forward khi redo đầy đủ, còn NOARCHIVELOG thường buộc phục hồi từ consistent whole-database backup nếu datafile read-write bị mất. Luôn xác định recovery point, RPO/RTO, transaction sau mốc, kiểm tra dependencies và chỉ mở traffic sau khi validation cùng business sign-off hoàn tất.

