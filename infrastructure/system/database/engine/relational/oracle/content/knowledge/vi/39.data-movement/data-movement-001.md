# Phân biệt sao lưu vật lý với xuất nhập dữ liệu logic

Khi bảo vệ hoặc di chuyển Oracle Database, có hai nhóm công cụ thường được dùng nhưng giải quyết những bài toán khác nhau:

- **Sao lưu vật lý (physical backup)** lưu bản sao các file vật lý của database, chẳng hạn datafiles, control files, SPFILE và archived redo logs. RMAN là công cụ tiêu chuẩn để tạo, quản lý, kiểm tra, restore và recover các bản sao này.
- **Xuất nhập dữ liệu logic (logical export/import)** trích xuất metadata và dữ liệu ở mức object thành dump file hoặc truyền trực tiếp giữa hai database. Oracle Data Pump (expdp/impdp) là công cụ chính cho công việc này.

Physical backup phù hợp để khôi phục database hoặc datafile sau sự cố, phục hồi tới SCN/thời điểm mục tiêu và xây dựng disaster recovery. Logical export/import phù hợp để di chuyển schema/table, sao chép một tập object, nâng cấp hoặc chuyển dữ liệu có chọn lọc giữa các môi trường. Một dump Data Pump không thay thế RMAN backup; một RMAN backup cũng không thuận tiện như Data Pump khi chỉ cần chuyển một schema sang database khác.

Bài học này dùng Oracle Database 19c làm mốc, trình bày:
- Khái niệm, phạm vi và mục tiêu của physical backup và logical export.
- RMAN backup/recovery và Data Pump export/import.
- Consistency, SCN, transaction snapshot và archived redo.
- Dump file, DIRECTORY object, parfile, worker và job monitoring.
- Export/import full database, schema, table và metadata.
- Filter, remap, transform, network link và transportable tablespaces.
- Portability, character set, endian, version và dependency.
- Bảo mật, hiệu năng, kiểm tra kết quả và chiến lược kết hợp.
- Lab, troubleshooting và checklist lựa chọn công cụ.

Cú pháp, tùy chọn và giới hạn phụ thuộc Oracle release, edition, platform, CDB/PDB, Data Pump client/server version và storage. Luôn đối chiếu tài liệu đúng phiên bản và thử export/import hoặc restore trên môi trường riêng trước khi triển khai production.

## 1. Hai cách nhìn về dữ liệu Oracle

### 1.1. Physical backup

Physical backup lưu các cấu trúc file mà Oracle sử dụng để vận hành database. Với RMAN, backup có thể là:
- Backup set chứa các block database cần thiết.
- Image copy là bản sao file datafile/control file theo cơ chế RMAN.
- Archived redo log backup để áp dụng thay đổi sau thời điểm backup.
- Control file và SPFILE backup để khởi động, nhận diện cấu trúc và phục hồi.

Khi restore physical backup, Oracle khôi phục file rồi áp dụng redo để đưa các file về một trạng thái nhất quán. Đây là con đường chính cho media recovery, point-in-time recovery và disaster recovery.

### 1.2. Logical export/import

Logical export đọc metadata và dữ liệu ở mức object. Data Pump có thể xuất:
- Database hoặc tập schema.
- Một hay nhiều table/partition.
- Metadata riêng hoặc data riêng.
- Object được chọn bằng INCLUDE/EXCLUDE.
- Dữ liệu được lọc bằng QUERY trong các trường hợp hỗ trợ.

Kết quả thường là một hoặc nhiều dump file (.dmp) cùng log file. Khi import, Data Pump tạo object và nạp dữ liệu vào database đích. Nó không khôi phục control file, online redo log hoặc trạng thái vật lý của instance.

### 1.3. So sánh nhanh

| Tiêu chí | Physical backup | Logical export/import |
| --- | --- | --- |
| Công cụ chính | RMAN | Data Pump expdp/impdp |
| Đơn vị | Datafile, control file, SPFILE, redo | Schema, table, partition, metadata |
| Kết quả | Backup set hoặc image copy | Dump file và log |
| Khôi phục database sau mất storage | Có, khi đủ backup và redo | Không |
| Point-in-time recovery toàn database | Có, qua RMAN recovery | Không |
| Chuyển một schema/object | Có thể nhưng không phải cách thuận tiện | Rất phù hợp |
| Chọn lọc object | Không theo semantics object như Data Pump | Có INCLUDE/EXCLUDE |
| Phụ thuộc platform | Có thể có phụ thuộc endian/storage | Thường linh hoạt hơn |
| Tái tạo cấu trúc instance | Có control file/SPFILE backup | Không |
| Mục tiêu thường gặp | Disaster recovery, media recovery | Migration, refresh, clone object, data movement |

### 1.4. Chọn theo mục tiêu

- Mất disk chứa datafile: dùng physical restore/recovery.
- Muốn khôi phục database về trước một lỗi logic: cân nhắc RMAN point-in-time recovery hoặc kỹ thuật recovery phù hợp; Data Pump chỉ hỗ trợ trích xuất/nạp lại object trong phạm vi đã xuất.
- Chuyển một schema sang database khác: Data Pump thường phù hợp.
- Chuyển một vài table có filter: Data Pump.
- Sao chép database nguyên trạng sang DR: RMAN duplicate/restore hoặc giải pháp physical standby.
- Chuyển tablespace rất lớn với downtime thấp: xem xét transportable tablespaces hoặc full transportable export/import.

## 2. Physical backup với RMAN

RMAN hiểu cấu trúc database và backup metadata, do đó có thể tạo backup online trong ARCHIVELOG mode, incremental backup, backup control file/SPFILE và kiểm tra khả năng restore.

### 2.1. Backup database

Kết nối:

~~~bash
rman target /
~~~

Backup database:

~~~text
BACKUP DATABASE TAG 'WEEKLY_DB';
~~~

Để thu thập archived redo cần thiết cho online backup:

~~~text
BACKUP DATABASE PLUS ARCHIVELOG TAG 'WEEKLY_DB_ARCH';
~~~

Database cần ở ARCHIVELOG mode cho online backup thông thường. RMAN tạo backup pieces và ghi metadata vào control file repository hoặc recovery catalog.

### 2.2. Backup control file và SPFILE

~~~text
CONFIGURE CONTROLFILE AUTOBACKUP ON;
BACKUP CURRENT CONTROLFILE TAG 'CONTROLFILE';
BACKUP SPFILE TAG 'SPFILE';
~~~

Nếu control file autobackup bật và database dùng SPFILE, autobackup thường bảo vệ cả hai. Vẫn cần kiểm tra backup thực tế và biết nơi lưu autobackup.

### 2.3. Incremental backup

~~~text
BACKUP INCREMENTAL LEVEL 0 DATABASE TAG 'L0';
BACKUP INCREMENTAL LEVEL 1 DATABASE TAG 'L1_DIFF';
BACKUP INCREMENTAL LEVEL 1 CUMULATIVE DATABASE TAG 'L1_CUM';
~~~

Level 0 làm baseline cho level 1. Differential và cumulative có trade-off giữa dung lượng backup và số bản incremental cần áp dụng lúc recovery.

### 2.4. Restore và recover

Restore đưa file từ backup về vị trí cần thiết; recover áp dụng redo:

~~~text
STARTUP MOUNT;
RESTORE DATABASE;
RECOVER DATABASE;
ALTER DATABASE OPEN;
~~~

Quy trình cụ thể phụ thuộc control file hiện tại, backup control file, target SCN/time, redo availability và incarnation. Không OPEN RESETLOGS trừ khi recovery path yêu cầu.

### 2.5. Điểm mạnh của physical backup

- Khôi phục database/datafile sau mất hoặc hỏng file.
- Áp dụng archived redo để phục hồi sau thời điểm backup.
- Phù hợp database lớn và yêu cầu disaster recovery.
- Có thể tự động hóa backup, retention, validation và restore.
- Giữ được trạng thái vật lý và cấu trúc database trong phạm vi backup.

## 3. Logical export/import với Data Pump

Data Pump là cơ chế di chuyển object và dữ liệu ở tầng logic. expdp chạy export job; impdp chạy import job. Các client này điều khiển job trên database server.

### 3.1. Kiến trúc Data Pump

Một Data Pump job có thể gồm:
- Master process điều phối job.
- Worker processes đọc/ghi metadata và data.
- Master table lưu trạng thái job trong schema sở hữu.
- DIRECTORY object trỏ tới thư mục trên database server.
- Dump files chứa metadata/data.
- Log file ghi tiến trình và lỗi.

Data Pump thường thực hiện I/O dump file trên máy chủ database, không phải thư mục hiện tại của terminal chạy expdp. Đây là điểm quan trọng khi cấu hình DIRECTORY.

### 3.2. Tạo DIRECTORY object

DBA tạo directory object trỏ tới đường dẫn trên server:

~~~sql
CREATE OR REPLACE DIRECTORY dpump_dir AS '/u03/oracle/dpump';
GRANT READ, WRITE ON DIRECTORY dpump_dir TO app_owner;
~~~

Đường dẫn phải tồn tại trên host database và OS account chạy Oracle có quyền phù hợp. GRANT READ/WRITE trên DIRECTORY object là quyền database; nó không tự cấp quyền filesystem.

Không cấp quyền directory rộng cho mọi user. Dump file có thể chứa dữ liệu nhạy cảm.

### 3.3. Kiểm tra directory

~~~sql
SELECT directory_name, directory_path
FROM dba_directories
WHERE directory_name = 'DPUMP_DIR';
~~~

Nếu dùng RAC, đảm bảo đường dẫn có thể truy cập từ node mà job worker chạy hoặc dùng shared storage phù hợp. Kiểm tra service placement và cấu hình cluster.

### 3.4. Export đơn giản

~~~bash
expdp app_owner@ORCL schemas=APP_OWNER directory=DPUMP_DIR dumpfile=app_owner.dmp logfile=app_owner_exp.log
~~~

Lệnh trên xuất schema APP_OWNER vào dump file trong directory object DPUMP_DIR. Password được hỏi tương tác hoặc lấy từ secret mechanism; không nhúng password thật trong shell history/script.

### 3.5. Import đơn giản

~~~bash
impdp app_owner@TARGET schemas=APP_OWNER directory=DPUMP_DIR dumpfile=app_owner.dmp logfile=app_owner_imp.log
~~~

Import cần dump file nằm ở directory server của database đích. Nếu chuyển file từ host nguồn sang host đích, copy file bằng cơ chế truyền file bảo mật và xác minh checksum trước khi import.

## 4. Consistency và snapshot của logical export

### 4.1. Data Pump đọc dữ liệu như thế nào?

Export dữ liệu table cần đọc các row từ database. Trong khi export chạy, ứng dụng có thể tiếp tục DML. Nếu không kiểm soát snapshot, các table được đọc ở những thời điểm khác nhau và có thể phản ánh các trạng thái không đồng nhất về nghiệp vụ.

Data Pump hỗ trợ tham số FLASHBACK_SCN hoặc FLASHBACK_TIME để đọc dữ liệu theo một điểm nhất quán khi điều kiện database/undo cho phép.

### 4.2. FLASHBACK_SCN

Lấy SCN mục tiêu:

~~~sql
SELECT current_scn FROM v$database;
~~~

Dùng cùng SCN cho export:

~~~bash
expdp app_owner@ORCL schemas=APP_OWNER directory=DPUMP_DIR dumpfile=app_owner.dmp logfile=app_owner_exp.log flashback_scn=123456789
~~~

Thay SCN placeholder bằng giá trị thực tế. Undo retention và lượng undo có sẵn phải đủ để phục vụ consistent read tới SCN đó. Nếu export kéo dài lâu và undo bị overwrite, job có thể gặp snapshot too old.

### 4.3. FLASHBACK_TIME

Data Pump cũng hỗ trợ FLASHBACK_TIME trong các trường hợp phù hợp:

~~~bash
expdp app_owner@ORCL schemas=APP_OWNER directory=DPUMP_DIR dumpfile=app_owner.dmp logfile=app_owner_exp.log flashback_time="TO_TIMESTAMP('2026-11-14 10:00:00','YYYY-MM-DD HH24:MI:SS')"
~~~

Cú pháp shell quoting cần điều chỉnh theo Windows/Linux và công cụ chạy. Dùng timestamp/timezone rõ ràng; kiểm tra giá trị được chuyển thành SCN và undo coverage.

### 4.4. Consistency không giống physical backup

FLASHBACK_SCN giúp export dữ liệu logic theo snapshot. Nó không biến dump file thành physical backup, không bảo vệ control file/SPFILE/redo và không cung cấp crash recovery. Nó chỉ kiểm soát snapshot của dữ liệu được export trong phạm vi Data Pump hỗ trợ.

### 4.5. Export và transaction đang chạy

Data Pump dùng cơ chế read consistency của Oracle. Nếu cần snapshot thống nhất giữa nhiều bảng có quan hệ nghiệp vụ, chọn một FLASHBACK_SCN cho toàn job và bảo đảm undo đủ lâu. Với bảng external, dữ liệu ngoài database hoặc object không hỗ trợ flashback theo cùng cách, cần thiết kế riêng.

## 5. Export toàn database, schema và table

### 5.1. Full database export

~~~bash
expdp system@ORCL full=YES directory=DPUMP_DIR dumpfile=full_%U.dmp logfile=full_exp.log parallel=4
~~~

FULL=YES xuất metadata và dữ liệu thuộc phạm vi Data Pump full export. Nó không tương đương RMAN whole database backup: một số cấu hình instance, physical file, redo history, password file, listener và wallet vẫn phải được quản lý riêng.

Full export thường yêu cầu quyền phù hợp như DATAPUMP_EXP_FULL_DATABASE. Không dùng SYSTEM/SYS cho công việc ứng dụng thường ngày nếu không cần thiết; cấp quyền đúng vai trò vận hành.

### 5.2. Schema export

~~~bash
expdp app_owner@ORCL schemas=APP_OWNER directory=DPUMP_DIR dumpfile=app_%U.dmp logfile=app_exp.log parallel=4
~~~

Có thể xuất nhiều schema:

~~~bash
expdp system@ORCL schemas=HR,SALES directory=DPUMP_DIR dumpfile=schemas_%U.dmp logfile=schemas_exp.log
~~~

### 5.3. Table export

~~~bash
expdp app_owner@ORCL tables=ORDERS,ORDER_ITEMS directory=DPUMP_DIR dumpfile=orders_%U.dmp logfile=orders_exp.log
~~~

Có thể xuất partition cụ thể hoặc dùng cú pháp table/partition phù hợp. Kiểm tra Data Pump parameter reference đúng phiên bản.

### 5.4. Metadata-only và data-only

~~~bash
expdp app_owner@ORCL schemas=APP_OWNER content=METADATA_ONLY directory=DPUMP_DIR dumpfile=app_meta.dmp logfile=app_meta.log
~~~

~~~bash
expdp app_owner@ORCL tables=ORDERS content=DATA_ONLY directory=DPUMP_DIR dumpfile=orders_data.dmp logfile=orders_data.log
~~~

METADATA_ONLY xuất định nghĩa object; DATA_ONLY xuất dữ liệu trong phạm vi được chọn. Khi import data-only, target cần có cấu trúc tương thích.

### 5.5. INCLUDE và EXCLUDE

Chỉ lấy một số object type:

~~~bash
expdp app_owner@ORCL schemas=APP_OWNER include=TABLE,INDEX directory=DPUMP_DIR dumpfile=app_objects.dmp logfile=app_objects.log
~~~

Loại một object type:

~~~bash
expdp app_owner@ORCL schemas=APP_OWNER exclude=STATISTICS directory=DPUMP_DIR dumpfile=app_no_stats.dmp logfile=app_no_stats.log
~~~

Filter có thể dùng object path và name expression. Cú pháp expression/quote phụ thuộc shell; dùng parfile khi câu lệnh phức tạp để tránh lỗi escape.

## 6. Data Pump parameter file (parfile)

Khi có nhiều tham số, dùng parfile giúp lệnh dễ đọc, quản lý và tái sử dụng.

Ví dụ app_export.par:

~~~text
DIRECTORY=DPUMP_DIR
SCHEMAS=APP_OWNER
DUMPFILE=app_owner_%U.dmp
LOGFILE=app_owner_export.log
PARALLEL=4
FILESIZE=10G
COMPRESSION=ALL
FLASHBACK_SCN=123456789
METRICS=YES
LOGTIME=ALL
~~~

Chạy:

~~~bash
expdp app_owner@ORCL parfile=app_export.par
~~~

Parfile nằm trên máy chạy client và được đọc bởi client process; DIRECTORY path lại trỏ tới server filesystem. Không nhầm hai vị trí này.

Không lưu password trong parfile. Quản lý parfile có filter/query nhạy cảm như cấu trúc bảng hoặc điều kiện dữ liệu theo chính sách nội bộ.

## 7. Dump file, FILESIZE và PARALLEL

### 7.1. Dump file template

~~~text
DUMPFILE=app_export_%U.dmp
~~~

%U cho phép Data Pump tạo nhiều file khi parallel export. FILESIZE giới hạn kích thước mỗi dump file:

~~~text
FILESIZE=20G
~~~

Đảm bảo có đủ dung lượng cho toàn bộ dump set, log file và temporary files.

### 7.2. PARALLEL

~~~text
PARALLEL=4
~~~

PARALLEL chỉ định mức độ song song của worker. Tăng PARALLEL có thể cải thiện throughput nhưng cũng tiêu thụ CPU, I/O, memory, process và network. Nếu storage hoặc source database đã bận, tăng worker có thể làm workload production chậm hơn.

### 7.3. Dump file không phải backup block-level

Dump file chứa object metadata và row data được Data Pump xuất. Nó không phải byte-for-byte copy của datafile và không thể gắn vào control file như datafile backup.

Dump file có thể dùng để tạo object ở database khác, nhưng không khôi phục được trạng thái instance, redo thread hoặc database checkpoint.

### 7.4. Checksum và truyền file

Sau khi chuyển dump file:
- Tính checksum ở source.
- Copy đủ tất cả file %U.
- Tính lại checksum ở destination.
- So sánh checksum.
- Giữ log export/import.
- Bảo vệ dump file và log theo retention policy.

Một file bị thiếu trong dump set có thể làm import thất bại hoặc thiếu dữ liệu.

## 8. Import schema và remap

### 8.1. Import schema vào schema cùng tên

~~~bash
impdp app_owner@TARGET schemas=APP_OWNER directory=DPUMP_DIR dumpfile=app_owner_%U.dmp logfile=app_import.log
~~~

Schema/user đích cần được tạo trước nếu workflow yêu cầu. Kiểm tra quota, tablespace mặc định, role và privileges.

### 8.2. REMAP_SCHEMA

Chuyển schema nguồn sang schema đích khác:

~~~bash
impdp system@TARGET schemas=APP_OWNER remap_schema=APP_OWNER:APP_OWNER_TEST directory=DPUMP_DIR dumpfile=app_owner_%U.dmp logfile=app_test_import.log
~~~

Tạo user đích và cấp quota/privilege phù hợp trước hoặc dùng quy trình tạo user được phê duyệt.

### 8.3. REMAP_TABLESPACE

Chuyển object từ tablespace nguồn sang tablespace đích:

~~~bash
impdp system@TARGET schemas=APP_OWNER remap_tablespace=APP_DATA:APP_DATA_NEW directory=DPUMP_DIR dumpfile=app_owner_%U.dmp logfile=app_remap_ts.log
~~~

REMAPPING chỉ thay đổi mapping object trong phạm vi Data Pump hỗ trợ. Kiểm tra LOB segments, partition, index và object nằm ở nhiều tablespace.

### 8.4. TABLE_EXISTS_ACTION

Khi table đã tồn tại, có thể chỉ định hành vi:

~~~bash
impdp app_owner@TARGET tables=ORDERS directory=DPUMP_DIR dumpfile=orders.dmp table_exists_action=APPEND logfile=orders_append.log
~~~

Các giá trị thường dùng:
- SKIP: bỏ qua table đã tồn tại.
- APPEND: thêm row vào table hiện có.
- TRUNCATE: xóa row hiện có rồi nạp dữ liệu.
- REPLACE: drop và tạo lại table theo metadata trong dump.

Chọn theo yêu cầu dữ liệu. APPEND có thể tạo duplicate nếu không kiểm soát key; TRUNCATE/REPLACE có thể làm mất dữ liệu đích. Kiểm tra kỹ trước import production.

## 9. SQLFILE, CONTENT và kiểm tra trước import

### 9.1. SQLFILE

Có thể yêu cầu Data Pump tạo file SQL chứa DDL dự kiến mà không thực hiện import object:

~~~bash
impdp system@TARGET schemas=APP_OWNER directory=DPUMP_DIR dumpfile=app_owner.dmp sqlfile=app_ddl_preview.sql logfile=app_sqlfile.log
~~~

SQLFILE hữu ích để xem DDL, tablespace, storage clause và object trước khi triển khai. File được ghi ở server directory object theo cơ chế Data Pump.

### 9.2. CONTENT=METADATA_ONLY

~~~bash
impdp system@TARGET schemas=APP_OWNER content=METADATA_ONLY directory=DPUMP_DIR dumpfile=app_owner.dmp logfile=app_metadata_import.log
~~~

### 9.3. CONTENT=DATA_ONLY

~~~bash
impdp app_owner@TARGET tables=ORDERS content=DATA_ONLY directory=DPUMP_DIR dumpfile=orders_data.dmp logfile=orders_data_import.log
~~~

Target table cần tồn tại và tương thích về cột, datatype, partition và constraint. Xác minh sequence/trigger/identity behavior nếu ứng dụng phụ thuộc.

### 9.4. Kiểm tra trước khi import

- Đọc log export và xác nhận job hoàn tất.
- Xem dump file list và checksum.
- Dùng SQLFILE để xem DDL.
- Kiểm tra target database version/character set.
- Xác nhận user/schema/tablespace/quota.
- Xác định object có tồn tại và TABLE_EXISTS_ACTION.
- Kiểm tra free space, TEMP, UNDO và parallel capacity.
- Chạy thử trên staging và so sánh row counts.

## 10. Data Pump job monitoring và restart

### 10.1. Xem job

~~~sql
SELECT
    owner_name,
    job_name,
    operation,
    job_mode,
    state,
    degree,
    attached_sessions
FROM dba_datapump_jobs
ORDER BY owner_name, job_name;
~~~

Có thể xem worker:

~~~sql
SELECT
    owner_name,
    job_name,
    session_type,
    instance_id
FROM dba_datapump_sessions
ORDER BY owner_name, job_name;
~~~

### 10.2. Attach job

Nếu job còn chạy hoặc stopped:

~~~bash
impdp app_owner@TARGET attach=SYS_IMPORT_SCHEMA_01
~~~

Tên job phải lấy từ DBA_DATAPUMP_JOBS hoặc log. Trong interactive mode có thể dùng STATUS để xem tiến độ và STOP_JOB/START_JOB theo hướng dẫn Data Pump.

### 10.3. Restartable job

Data Pump job có thể được attach và tiếp tục trong nhiều trường hợp nếu job state/dump set còn phù hợp. Không xóa master table hoặc dump files khi job chưa hoàn tất. Nếu job lỗi, đọc log và xác định worker/object gây lỗi trước khi restart.

### 10.4. Kill job

Không kill OS process tùy tiện. Dùng Data Pump attach và lệnh quản lý job theo tài liệu. Nếu cần dừng ngay, hiểu ảnh hưởng master table, worker session và cleanup.

## 11. Export/import bằng NETWORK_LINK

Data Pump có thể chuyển dữ liệu trực tiếp từ database nguồn sang database đích qua database link mà không cần dump file trung gian cho data movement thông thường.

### 11.1. Tạo database link

Ví dụ link từ database đích tới source:

~~~sql
CREATE DATABASE LINK source_link
CONNECT TO export_user IDENTIFIED BY "<SECRET>"
USING 'SOURCE_DB';
~~~

Trong production, không ghi password thật vào script hoặc source control. Dùng credential policy và quyền tối thiểu. Database link phải resolve service và network đúng.

### 11.2. Import qua network link

~~~bash
impdp import_user@TARGET schemas=APP_OWNER network_link=SOURCE_LINK logfile=network_import.log
~~~

NETWORK_LINK đọc object/data từ database nguồn qua link. Một số tùy chọn và loại object không hỗ trợ giống import từ dump file; kiểm tra Data Pump reference.

### 11.3. Trade-off

Ưu điểm:
- Không cần staging dump file lớn.
- Hữu ích cho schema transfer trực tiếp.
- Có thể giảm bước copy file.

Hạn chế:
- Phụ thuộc network throughput/latency.
- Tải lên source database và database link.
- Phải quản lý credential và network security.
- Khó tách biệt source load khỏi target import.
- Khả năng restart/diagnostic khác workflow dump file.

## 12. Transportable tablespaces và full transportable export/import

Với dữ liệu rất lớn, Data Pump transportable có thể giảm thời gian vì datafile được copy vật lý còn metadata được export/import logic.

### 12.1. Transportable tablespaces

Khái niệm:
1. Đưa tablespace về READ ONLY để bảo đảm dữ liệu ổn định.
2. Export metadata tablespace bằng Data Pump.
3. Copy datafiles sang host/database đích.
4. Import metadata với TRANSPORT_DATAFILES.
5. Đưa tablespace về READ WRITE theo kế hoạch.

Ví dụ export metadata:

~~~bash
expdp system@ORCL tablespaces=APP_DATA directory=DPUMP_DIR dumpfile=app_ts_meta.dmp logfile=app_ts_exp.log transportable=ALWAYS
~~~

Import metadata cùng file data:

~~~bash
impdp system@TARGET directory=DPUMP_DIR dumpfile=app_ts_meta.dmp logfile=app_ts_imp.log transport_datafiles='/u02/oradata/TARGET/app_data01.dbf'
~~~

Cú pháp, yêu cầu self-contained và cách copy file cần đối chiếu đúng release. Kiểm tra DBMS_TTS.TRANSPORT_SET_CHECK để xác định tablespace set có self-contained theo yêu cầu hay không.

### 12.2. Full transportable export/import

Full transportable export/import kết hợp Data Pump metadata với transportable datafiles cho phần tablespace phù hợp, còn một số thành phần được xử lý qua conventional Data Pump. Đây là kỹ thuật migration, không phải thay thế physical backup.

### 12.3. Cross-platform transport

Khi chuyển datafile giữa platform có endian khác nhau, có thể cần RMAN CONVERT hoặc cơ chế chuyển đổi được hỗ trợ. Kiểm tra:
- Platform source/target.
- Endian format.
- Character set.
- Database version.
- TDE encryption.
- ASM/OMF path.
- Datafile compatibility.

## 13. Portability và tương thích phiên bản

### 13.1. Physical backup portability

Physical backup thường gắn với database/platform/file format. Một số trường hợp cross-platform cần RMAN CONVERT hoặc transportable technology. Không copy datafile giữa platform khác endian rồi mở database như file cùng platform.

### 13.2. Logical export portability

Data Pump thường linh hoạt hơn khi chuyển schema/object giữa database versions và platforms. Tuy nhiên vẫn phải kiểm tra:
- Source/target version và Data Pump compatibility.
- Character set và national character set.
- Datatype, timezone file version.
- Object feature/option có trên target không.
- SQL syntax/PLSQL package dependency.
- Collation, identity, sequence và partition behavior.

### 13.3. VERSION parameter

Data Pump hỗ trợ VERSION để kiểm soát metadata format/compatibility trong một số hướng export. Ví dụ:

~~~bash
expdp app_owner@ORCL schemas=APP_OWNER directory=DPUMP_DIR dumpfile=app_compat.dmp logfile=app_compat.log version=19.0
~~~

Giá trị hợp lệ và khả năng downgrade phụ thuộc release. VERSION không biến tính năng mới thành tính năng có trên target; object sử dụng feature không hỗ trợ vẫn có thể lỗi khi import.

### 13.4. Character set

Logical export/import chuyển dữ liệu qua character set conversion theo khả năng Oracle. Kiểm tra NLS_CHARACTERSET và NLS_NCHAR_CHARACTERSET ở hai database, dữ liệu có ký tự ngoài BMP, CLOB/NCLOB và độ dài cột. Conversion có thể gây mất ký tự nếu target không biểu diễn được toàn bộ source data.

## 14. Bảo mật dump file và backup

### 14.1. Dump file chứa dữ liệu nhạy cảm

Dump file có thể chứa dữ liệu nghiệp vụ, PII, credential trong metadata hoặc DDL. Bảo vệ như dữ liệu production:
- Thư mục server có quyền OS hạn chế.
- DIRECTORY object chỉ grant cho user cần thiết.
- Mã hóa dump nếu policy yêu cầu.
- Truyền file qua kênh bảo mật.
- Lưu checksum và audit access.
- Xóa bản tạm theo retention.
- Không commit dump vào Git hoặc gửi qua email/chat.

### 14.2. Data Pump encryption

Data Pump hỗ trợ ENCRYPTION và ENCRYPTION_PASSWORD theo phiên bản/license/cấu hình. Ví dụ khái niệm trong parfile:

~~~text
ENCRYPTION=ALL
ENCRYPTION_PASSWORD=<SECRET_FROM_SECRET_STORE>
~~~

Cú pháp thực tế phụ thuộc release và mode. Tránh để password trong process listing, shell history hoặc log. Bảo vệ password riêng với dump file; nếu mất password có thể không import được.

### 14.3. RMAN backup encryption

RMAN có thể mã hóa backup set bằng transparent encryption dựa trên keystore hoặc password-based encryption. Phải backup và kiểm tra khả năng khôi phục keystore/password cùng physical backup.

### 14.4. Quyền truy cập

- Không cấp DATAPUMP_EXP_FULL_DATABASE/DATAPUMP_IMP_FULL_DATABASE rộng rãi.
- Không dùng SYSDBA cho Data Pump thường lệ nếu không cần.
- Cấp quyền READ/WRITE trên DIRECTORY có phạm vi cụ thể.
- Dùng account migration riêng, có expiry và audit.
- Xác nhận dump không chứa schema/object ngoài phạm vi.

## 15. Hiệu năng và dung lượng

### 15.1. RMAN

RMAN performance phụ thuộc:
- Số channel và parallelism.
- Storage throughput và latency.
- Compression/encryption CPU.
- Block Change Tracking cho incremental.
- Backup piece size và media manager.
- Archived log generation rate.
- Workload đồng thời trên database.

### 15.2. Data Pump

Data Pump performance phụ thuộc:
- PARALLEL và số worker.
- Dump file nằm trên storage nào.
- I/O source/target.
- Network nếu dùng NETWORK_LINK.
- Metadata dependency và object count.
- Index creation, LOB, partition và constraint.
- Undo/consistent read.
- TEMP, PGA và CPU.

### 15.3. Không tăng PARALLEL tùy tiện

Tăng worker có thể gây:
- I/O contention trên source hoặc target.
- CPU saturation.
- Thiếu process/session.
- Nhiều dump file đồng thời và áp lực filesystem.
- Tăng network load.

Đo thời gian, throughput, CPU, I/O và wait trước/sau. Chọn mức parallel phù hợp với cửa sổ migration.

## 16. Kiểm tra tính đầy đủ sau export/import

### 16.1. Export log

Đọc log để xác nhận:
- Job hoàn tất với trạng thái thành công.
- Object được xử lý.
- Object bị bỏ qua hoặc lỗi.
- Dump file được tạo đủ.
- Warning về privilege, unsupported object hoặc metadata.

### 16.2. Import log

Kiểm tra:
- Object create thành công.
- Row data được nạp.
- Constraint/index/trigger được tạo.
- Object invalid.
- Grants, synonyms, database links và directory dependencies.
- Lỗi tablespace/quota/privilege.
- Lỗi do version/character set.

### 16.3. Đối chiếu dữ liệu

Có thể so sánh row count:

~~~sql
SELECT COUNT(*) FROM app_owner.orders;
~~~

Với dữ liệu lớn, row count đơn thuần chưa đủ. Có thể so sánh theo partition/date range, aggregate checksum nghiệp vụ, key range hoặc reconciliation query. Không dùng COUNT(*) trên bảng rất lớn trong giờ cao điểm nếu tác động chưa được đánh giá.

### 16.4. Object validity

~~~sql
SELECT owner, object_type, object_name, status
FROM dba_objects
WHERE owner = 'APP_OWNER'
  AND status <> 'VALID'
ORDER BY object_type, object_name;
~~~

Kiểm tra invalid objects, compile theo dependency, xác minh grants và chạy application smoke test.

### 16.5. Physical backup validation

RMAN:

~~~text
LIST BACKUP SUMMARY;
RESTORE DATABASE PREVIEW;
RESTORE DATABASE VALIDATE;
~~~

Validation đọc backup piece cần thiết nhưng không thay thế restore drill độc lập và kiểm tra ứng dụng.

## 17. Khi nào chọn công cụ nào?

| Nhu cầu | Lựa chọn phù hợp | Lý do |
| --- | --- | --- |
| Mất datafile hoặc disk | RMAN restore/recover | Cần file vật lý và redo |
| Khôi phục toàn database sau disaster | RMAN hoặc physical standby | Giữ trạng thái database và phục hồi |
| Khôi phục tới SCN/time | RMAN point-in-time recovery | Áp dụng redo tới target |
| Chuyển một schema sang môi trường mới | Data Pump | Chọn schema/object |
| Chuyển vài table có filter | Data Pump | Table selection và QUERY |
| Refresh dữ liệu test | Data Pump hoặc clone/refresh giải pháp khác | Chọn phạm vi và consistency |
| Di chuyển tablespace rất lớn | Transportable tablespaces | Datafile copy + metadata |
| Clone nguyên database | RMAN DUPLICATE/restore | Giữ database-level structure |
| Tạo bản dump để lưu trữ logic | Data Pump | Có thể import object về sau |
| Bảo vệ database để DR | RMAN + archive/standby strategy | Có redo và recovery metadata |

Không chọn Data Pump chỉ vì dump file dễ copy. Nếu mục tiêu là phục hồi sau mất storage, dump file không chứa toàn bộ cấu trúc vật lý cần thiết. Cũng không chọn RMAN chỉ để chuyển một table có filter khi Data Pump giải quyết trực tiếp và linh hoạt hơn.

## 18. Chiến lược kết hợp physical và logical

Một hệ thống production thường cần cả hai:

### 18.1. Physical backup làm nền tảng recovery

- RMAN full hoặc incremental theo lịch.
- Archived redo log backup đủ thường xuyên.
- Control file autobackup và SPFILE.
- Backup encryption/keystore protection.
- Copy offsite/immutable nếu policy yêu cầu.
- Restore validation và DR drill.

### 18.2. Logical export cho migration và object recovery

- Export schema/table trước thay đổi lớn.
- Dùng FLASHBACK_SCN khi cần snapshot nhất quán.
- Giữ dump file và log theo retention ngắn, kiểm soát quyền.
- Import vào staging trước khi production.
- Reconcile dữ liệu, grants, sequence, constraint và object validity.

### 18.3. Ví dụ lịch kết hợp

| Thời điểm | Physical | Logical |
| --- | --- | --- |
| Hàng ngày | RMAN incremental + archived logs | Không nhất thiết chạy full schema export |
| Hàng tuần | RMAN level 0/full và controlfile/SPFILE | Export schema quan trọng nếu có nhu cầu |
| Trước release | RMAN backup/tag theo change plan | Export schema/object bị thay đổi |
| Trước migration | Backup RMAN đầy đủ | Data Pump export hoặc transportable |
| Sau migration | Backup database đích | Import log, reconciliation và smoke test |
| Hàng tháng | Restore drill physical | Import thử dump file vào staging |

Lịch thực tế phải theo RPO/RTO, data volume, migration cadence và retention policy.

## 19. Troubleshooting thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| ORA-39002 | Tham số/job Data Pump không hợp lệ | Đọc log và kiểm tra parameter syntax |
| ORA-39070 | Không mở được log file | Kiểm tra DIRECTORY object và OS permission |
| ORA-39087 | DIRECTORY object không hợp lệ | Kiểm tra tên directory và quyền |
| ORA-31640 | Không mở được dump file | Kiểm tra server path, file name, permission |
| ORA-39151 | Table tồn tại và bị skip | Chọn TABLE_EXISTS_ACTION phù hợp |
| ORA-39126 | Worker Data Pump gặp lỗi | Xem worker error trước đó và trace |
| ORA-01555 | Snapshot too old khi export consistent | Đánh giá UNDO, thời lượng job và FLASHBACK_SCN |
| ORA-39083 | Tạo object thất bại | Đọc DDL/error cụ thể, privilege/tablespace/version |
| Import thiếu object | INCLUDE/EXCLUDE hoặc mode export giới hạn | Kiểm tra parfile và export log |
| Import lỗi character | Character set conversion hoặc datatype | So sánh NLS settings và dữ liệu |
| RMAN không thấy backup | Repository/control file khác hoặc backup expired | LIST, CROSSCHECK, CATALOG và DBID |
| RMAN restore thiếu redo | Archived log sequence không có | Tìm log backup/media khác hoặc chọn target phù hợp |
| RMAN backup chậm | Channel/storage/CPU bottleneck | Đo throughput, I/O, compression và parallelism |
| Data Pump job đứng lâu | Worker chờ I/O, lock, network hoặc object lớn | Attach job, STATUS, xem wait/session |
| Dump file chuyển sang target bị lỗi | Thiếu piece hoặc copy corruption | So checksum và kiểm tra toàn bộ %U files |

## 20. Lab: physical backup với RMAN

Thực hiện trong database lab có quyền RMAN và storage riêng.

### 20.1. Kiểm tra database

~~~sql
SELECT name, open_mode, log_mode, current_scn
FROM v$database;
~~~

Trong RMAN:

~~~text
SHOW ALL;
REPORT SCHEMA;
~~~

### 20.2. Tạo backup

~~~text
CONFIGURE CONTROLFILE AUTOBACKUP ON;
BACKUP DATABASE PLUS ARCHIVELOG TAG 'LAB_PHYSICAL';
BACKUP SPFILE TAG 'LAB_SPFILE';
LIST BACKUP SUMMARY;
~~~

### 20.3. Validate

~~~text
RESTORE DATABASE PREVIEW;
RESTORE DATABASE VALIDATE;
~~~

Ghi backup key, piece, checkpoint SCN và archived log coverage. Không restore đè database lab đang dùng.

## 21. Lab: logical export/import với Data Pump

### 21.1. Chuẩn bị directory

DBA:

~~~sql
CREATE OR REPLACE DIRECTORY dpump_lab AS '/u03/oracle/dpump_lab';
GRANT READ, WRITE ON DIRECTORY dpump_lab TO app_owner;
~~~

Đảm bảo thư mục tồn tại trên server và Oracle OS account có quyền.

### 21.2. Export schema

Tạo parfile app_export.par:

~~~text
DIRECTORY=DPUMP_LAB
SCHEMAS=APP_OWNER
DUMPFILE=app_owner_%U.dmp
LOGFILE=app_owner_exp.log
PARALLEL=2
METRICS=YES
LOGTIME=ALL
~~~

Chạy:

~~~bash
expdp app_owner@ORCL parfile=app_export.par
~~~

Nếu cần consistent snapshot, thêm FLASHBACK_SCN với SCN đã ghi nhận và bảo đảm undo retention phù hợp.

### 21.3. Xem dump metadata trước import

~~~bash
impdp app_owner@TARGET directory=DPUMP_LAB dumpfile=app_owner_%U.dmp sqlfile=app_ddl.sql logfile=app_ddl.log
~~~

Đọc DDL để xác định tablespace, quota, grants và dependency.

### 21.4. Import sang schema mới

~~~bash
impdp system@TARGET schemas=APP_OWNER remap_schema=APP_OWNER:APP_OWNER_TEST directory=DPUMP_LAB dumpfile=app_owner_%U.dmp logfile=app_test_imp.log
~~~

Tạo user đích và tablespace/quota cần thiết trước khi import theo chính sách.

### 21.5. Xác minh

- Đọc export/import log.
- Kiểm tra object count và invalid objects.
- So sánh row count hoặc reconciliation query.
- Kiểm tra sequence, trigger, grants và synonym.
- Chạy smoke test ứng dụng trong staging.

## 22. Bài tập thực hành

### Bài 1 — Phân loại mục tiêu

Cho 8 tình huống: mất datafile, chuyển schema, clone database, lọc một nhóm row, PITR, chuyển tablespace lớn, refresh test và backup trước release. Chọn RMAN/Data Pump/transportable và giải thích.

### Bài 2 — RMAN full backup

Tạo backup database và archived logs. Ghi backup piece, tag, checkpoint SCN và thời gian.

### Bài 3 — RMAN incremental

Tạo level 0, thay đổi dữ liệu, chạy level 1 differential/cumulative. So sánh dung lượng và restore chain.

### Bài 4 — Data Pump schema export

Export một schema với PARALLEL và %U. Đọc log, checksum các dump file và ghi object count.

### Bài 5 — Snapshot consistency

Lấy FLASHBACK_SCN, export schema tại SCN đó, thay đổi dữ liệu trong một session khác và so sánh dump khi import vào lab.

### Bài 6 — Object filtering

Export một số table bằng TABLES và dùng INCLUDE/EXCLUDE. Kiểm tra SQLFILE trước import.

### Bài 7 — Remap schema/tablespace

Import schema sang user và tablespace mới. Kiểm tra object ownership, quota và invalid objects.

### Bài 8 — Network link

Tạo database link lab, chạy import qua NETWORK_LINK và đo network/source load so với dump file workflow.

### Bài 9 — Transportable tablespace

Kiểm tra self-contained set, export metadata, copy datafile và import tablespace trong môi trường riêng. Nếu cross-platform, xác định có cần convert endian không.

### Bài 10 — Recovery/migration runbook

Viết hai runbook độc lập: một cho mất datafile bằng RMAN, một cho chuyển schema bằng Data Pump. Ghi prerequisite, credential, files, consistency point, validation và rollback.

## 23. Checklist trước khi chạy

### Chọn công cụ
- Mục tiêu là disaster recovery hay object migration?
- Có cần khôi phục database tới SCN/time không?
- Cần toàn database, tablespace, schema hay một vài table?
- Có yêu cầu chuyển platform/version không?

### Physical backup
- Database ARCHIVELOG nếu cần online backup.
- Backup datafiles, control file, SPFILE và archived redo.
- Biết backup destination, DBID và recovery catalog.
- Bảo vệ wallet/keystore nếu backup encrypted.
- Validate backup và diễn tập restore.

### Logical export/import
- DIRECTORY object trỏ đúng server path.
- OS permission và database READ/WRITE grant đúng.
- Dump file đủ tất cả pieces và checksum.
- FLASHBACK_SCN/TIME khi cần consistent snapshot.
- Target version/character set/tablespace/quota phù hợp.
- INCLUDE/EXCLUDE, REMAP và TABLE_EXISTS_ACTION đã được review.
- Export/import log và data reconciliation thành công.

### Sau thao tác
- Kiểm tra database/object status.
- Kiểm tra row count và nghiệp vụ.
- Xác nhận grants, synonyms, sequence, trigger và job.
- Bảo vệ/xóa dump file theo retention.
- Cập nhật runbook và lịch backup.

## 24. Dọn dẹp môi trường lab

- Dừng Data Pump job theo cách được hỗ trợ và chỉ khi cần.
- Xóa đúng dump/log files của lab sau khi xác nhận không còn cần.
- Thu hồi quyền DIRECTORY đã cấp cho user lab nếu không dùng nữa.
- Xóa database link/credential lab theo policy.
- Xóa schema/table lab có kiểm soát.
- Giữ RMAN backup cần cho bài restore; xóa bằng RMAN theo retention, không xóa trực tiếp bằng OS khi repository còn tham chiếu.
- Không xóa archived redo logs cần cho database dùng chung.

## Tổng kết

Physical backup và logical export/import giải quyết hai mục tiêu khác nhau. RMAN lưu các file vật lý và redo cần để restore/recover database, datafile và trạng thái database tới một SCN/time. Data Pump xuất metadata và row data ở mức object để chuyển schema/table, lọc dữ liệu, refresh môi trường hoặc migration. FLASHBACK_SCN/TIME giúp Data Pump đọc một snapshot logic nhất quán nhưng không biến dump file thành physical backup.

Chọn RMAN khi cần disaster recovery, media recovery hoặc point-in-time recovery. Chọn Data Pump khi cần di chuyển object/dữ liệu có chọn lọc hoặc chuyển schema giữa database. Transportable tablespaces kết hợp metadata export với datafile copy cho một số workload lớn. Trong production, thường dùng RMAN làm nền tảng bảo vệ dữ liệu và Data Pump cho migration/refresh; kiểm tra dump, backup, consistency, version, character set, keys và restore/import end-to-end trước khi kết luận thành công.

## Tài liệu Oracle tham khảo

- [Oracle Database Backup and Recovery User's Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/) — RMAN backup, restore, recovery và chiến lược physical backup.
- [Oracle Database Backup and Recovery Reference (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/rcmrf/) — cú pháp RMAN BACKUP, RESTORE, RECOVER và validation.
- [Oracle Database Utilities — Data Pump Export (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/oracle-data-pump-export-utility.html) — expdp parameters, export modes và dump files.
- [Oracle Database Utilities — Data Pump Import (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/oracle-data-pump-import-utility.html) — impdp, remap, filters và import modes.
- [Oracle Database Utilities (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/) — Data Pump, transportable tablespaces và database utilities.
- [Oracle Database Reference — DBA_DATAPUMP_JOBS (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_DATAPUMP_JOBS.html) — theo dõi Data Pump jobs.
- [Oracle Database Reference — DBA_DIRECTORIES (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_DIRECTORIES.html) — directory object và server path.

Khi triển khai trên Oracle release khác 19c, hãy đối chiếu Backup and Recovery User's Guide, Data Pump Export/Import Reference và Database Utilities đúng phiên bản, đặc biệt FLASHBACK_SCN/TIME, VERSION, encryption, transportable tablespaces, PDB scope và giới hạn cross-platform.
