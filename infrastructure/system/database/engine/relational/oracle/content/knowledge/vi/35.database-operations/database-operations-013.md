# Kiểm tra sức khỏe định kỳ và xây dựng sổ tay vận hành (runbook)

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** Vận hành  
> **Mục tiêu:** Xây dựng lịch kiểm tra sức khỏe Oracle Database có thể lặp lại; theo dõi availability, capacity, performance, backup/recovery, high availability, security và job; viết runbook có điều kiện kích hoạt, bước chẩn đoán, hành động, xác minh, escalation và rollback; lưu bằng chứng để phát hiện xu hướng trước khi sự cố ảnh hưởng người dùng.

## 1. Health check và runbook giải quyết hai việc khác nhau

**Health check** là hoạt động quan sát có lịch để xác định database có đang hoạt động bình thường, có dấu hiệu bất thường hoặc có xu hướng cạn tài nguyên hay không.

**Runbook** là hướng dẫn thao tác đã được chuẩn bị trước cho một tình huống cụ thể. Runbook trả lời: khi nào cần kích hoạt, ai chịu trách nhiệm, cần kiểm tra gì, hành động nào được phép, điều kiện dừng, cách xác nhận phục hồi và khi nào phải escalation.

Hai việc bổ trợ nhau:

- Health check phát hiện tín hiệu: FRA tăng nhanh, tablespace gần đầy, job backup thất bại, Data Guard apply lag tăng.
- Runbook biến tín hiệu thành hành động: xác minh nguyên nhân, đánh giá mức độ ảnh hưởng, chọn biện pháp an toàn, xác nhận kết quả và ghi nhận sự cố.

Một dashboard xanh không thay thế được quy trình phục hồi. Một runbook tốt cũng không giúp ích nếu không có monitoring phát hiện đúng thời điểm.

### 1.1. Phạm vi health check

Một bộ kiểm tra vận hành Oracle nên bao phủ ít nhất các nhóm sau:

| Nhóm | Câu hỏi cần trả lời |
|---|---|
| Availability | Instance, database, service và PDB có mở đúng trạng thái không? |
| Capacity | Data tablespace, TEMP, UNDO, FRA, filesystem và process/session có đủ headroom không? |
| Performance | Latency, throughput, CPU, I/O, waits và SQL workload có bất thường không? |
| Backup/recovery | Backup có hoàn tất, còn dùng được và có thể restore/recover không? |
| High availability | RAC, Data Guard, service failover và replication có khỏe không? |
| Database objects | Có object INVALID, job lỗi, constraint/index bất thường không? |
| Security | Account, privilege, audit, credential và database link có đúng chính sách không? |
| Change/patch | Phiên bản, patch, tham số và thay đổi gần đây có được ghi nhận không? |
| Operations | Alert log, incident, batch, scheduler và capacity trend có owner xử lý không? |

Không phải database nào cũng dùng RAC, Data Guard, multitenant, SecureFiles hoặc cùng một công cụ backup. Runbook phải đánh dấu rõ phần áp dụng và phần không áp dụng cho kiến trúc cụ thể.

## 2. Xây lịch kiểm tra theo nhịp

Không nên chạy mọi câu query mỗi ngày. Một số kiểm tra cần liên tục, một số chỉ có ý nghĩa khi so sánh theo tuần hoặc tháng.

| Nhịp | Nội dung điển hình | Mục tiêu |
|---|---|---|
| Liên tục / alert-driven | Instance/service down, tablespace/FRA threshold, failed critical job, Data Guard lag, blocking kéo dài | Phát hiện sớm sự cố |
| Mỗi ca / hằng ngày | Database/PDB status, alert log, backup đêm trước, FRA/TEMP/UNDO, scheduler failures, active blockers | Xác nhận trạng thái đầu ca |
| Hằng tuần | Capacity growth, top SQL trend, invalid objects, job duration, Data Guard transport/apply trend, account review | Nhận diện xu hướng |
| Hằng tháng | Restore validation, DR readiness, patch inventory, privilege review, retention, capacity forecast, runbook review | Giảm rủi ro vận hành |
| Theo sự kiện | Trước/sau patch, migration, data load, switchover, storage change | Xác nhận thay đổi an toàn |

### 2.1. Xác định owner và thời hạn phản hồi

Mỗi kiểm tra cần có:

- Owner chính: DBA, SRE, platform team hoặc application owner.
- Backup owner: người thay thế khi owner chính vắng mặt.
- Tần suất và thời điểm chạy.
- Mức độ nghiêm trọng.
- Thời hạn acknowledge và escalation.
- Nơi lưu kết quả.
- Điều kiện đóng cảnh báo.

Không giao chung chung cho “DBA team”. Mỗi cảnh báo phải có người nhận, nhóm chịu trách nhiệm và đường liên hệ khi vượt SLA.

### 2.2. Baseline và ngưỡng cảnh báo

Không có một ngưỡng % dùng được cho mọi database. Ví dụ tablespace 85% có thể chấp nhận nếu tăng trưởng chậm và còn nhiều dung lượng mở rộng; 70% có thể là nguy cơ nếu tăng hàng chục GB mỗi giờ và datafile không thể autoextend.

Thiết lập threshold dựa trên:

- Mức sử dụng hiện tại.
- Tốc độ tăng trưởng.
- Dung lượng có thể cấp thêm.
- Giới hạn storage/quota/cloud service.
- Thời gian cần để phê duyệt và mở rộng.
- RTO/RPO và business criticality.
- Lịch batch và mùa cao điểm.

Nên có ít nhất hai mức: warning để xử lý chủ động và critical để escalation khẩn cấp. Ghi cả giá trị tuyệt đối, phần trăm và tốc độ tăng.

## 3. Chuẩn bị môi trường và quyền kiểm tra

Các query trong tài liệu dùng các view như V$DATABASE, V$INSTANCE, V$SESSION, V$SYSSTAT, DBA_TABLESPACES và DBA_DATA_FILES. Tài khoản vận hành cần quyền phù hợp.

Nguyên tắc:

- Dùng tài khoản giám sát riêng, chỉ có quyền đọc các view cần thiết.
- Không dùng SYSDBA cho health check định kỳ của ứng dụng.
- Tách quyền quan sát khỏi quyền thực hiện thay đổi.
- Dùng catalog role/quyền đọc dictionary theo chính sách DBA; không cấp SELECT ANY TABLE chỉ để dashboard đọc metadata.
- Ghi nhận container, instance và database role khi chạy query.
- Với RAC, dùng GV$ view và giữ INST_ID để không trộn các instance.
- Với CDB/PDB, ghi CON_ID hoặc container name để biết dữ liệu thuộc container nào.

Ví dụ xác định database và instance:

~~~sql
SELECT name,
       dbid,
       database_role,
       open_mode,
       log_mode,
       protection_mode,
       protection_level
FROM v$database;

SELECT instance_name,
       host_name,
       version,
       startup_time,
       status,
       database_status
FROM v$instance;
~~~

Query V$DATABASE mô tả trạng thái database và role; V$INSTANCE mô tả instance hiện tại. Trong RAC, mỗi instance có trạng thái riêng.

### 3.1. Xác định container hiện tại

~~~sql
SELECT sys_context('USERENV', 'DB_NAME') AS db_name,
       sys_context('USERENV', 'CON_NAME') AS con_name,
       sys_context('USERENV', 'CON_ID') AS con_id,
       sys_context('USERENV', 'SESSION_USER') AS session_user,
       sys_context('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM dual;
~~~

Trong multitenant, chạy query ở root và PDB có thể trả kết quả khác nhau. DBA cần xác định query nào dùng CDB_* view, DBA_* view trong container hiện tại hay CONTAINER_DATA theo quyền. Không kết luận “không có dữ liệu” nếu đang đứng nhầm container.

### 3.2. Xác định phiên bản

~~~sql
SELECT banner
FROM v$version
ORDER BY banner;
~~~

Ghi release, RU/patch level và platform vào báo cáo. Cột dictionary, tính năng và cách quản lý thay đổi theo release.

## 4. Kiểm tra availability

### 4.1. Instance và database open mode

~~~sql
SELECT instance_name,
       status,
       database_status,
       logins,
       active_state,
       startup_time
FROM v$instance;

SELECT name,
       database_role,
       open_mode,
       log_mode,
       switchover_status
FROM v$database;
~~~

Các trạng thái thường cần chú ý:

- Instance OPEN và database READ WRITE trên primary khi kiến trúc yêu cầu.
- Standby có thể READ ONLY WITH APPLY, MOUNTED hoặc trạng thái khác tùy chế độ Data Guard.
- PDB cần ở trạng thái open phù hợp với service/application.
- LOGINS có thể RESTRICTED nếu database đang bảo trì.

Không áp dụng cùng một trạng thái mong đợi cho primary, physical standby, snapshot standby và database lab.

### 4.2. PDB status

~~~sql
SELECT con_id,
       name,
       open_mode,
       restricted
FROM v$pdbs
ORDER BY con_id;
~~~

Đối chiếu từng PDB với danh sách service cần chạy. PDB OPEN không bảo đảm ứng dụng kết nối được qua service; còn phải kiểm tra listener, service registration, network và authentication.

### 4.3. Service và listener

Trên host, kiểm tra bằng công cụ Oracle Net/Clusterware phù hợp:

~~~text
lsnrctl status
lsnrctl services
srvctl status service -db <db_unique_name>
srvctl status database -db <db_unique_name>
~~~

Các lệnh SRVCTL áp dụng môi trường được quản lý bởi Oracle Restart/Grid Infrastructure; cú pháp option có thể khác release. Lệnh trạng thái là bước quan sát. Không dùng START/STOP/RELOCATE trong health check thường kỳ nếu chưa có change/incident authorization.

TNSping chỉ xác minh khả năng phân giải/connect descriptor và phản hồi listener theo cơ chế của nó; nó không chứng minh đăng nhập database hoặc query thành công.

### 4.4. Kiểm tra kết nối ứng dụng

Từ đường đi thật của ứng dụng, xác nhận:

- DNS/connect descriptor.
- Listener và service name.
- Authentication.
- Connection pool có thể mượn connection.
- Một query health nhẹ chạy được.
- PDB/service đúng container.
- TLS/TCPS nếu bắt buộc.
- Không có connection pool wait hoặc login storm.

Không chỉ ping host database rồi đánh dấu service khỏe.

## 5. Kiểm tra alert log và incident

Alert log ghi các sự kiện quan trọng như startup/shutdown, lỗi nội bộ, checkpoint, redo/archive, recovery, tablespace và nhiều cảnh báo vận hành.

Dùng ADRCI trên host:

~~~text
adrci
show homes
set homepath <adr_home>
show alert -tail 100
~~~

ADR home cụ thể có thể được xác định bằng ADRCI và cấu hình Oracle. Có thể dùng Oracle Enterprise Manager hoặc hệ thống log tập trung để tìm theo timestamp, instance và incident.

### 5.1. Những tín hiệu cần chú ý

- ORA-00600, ORA-07445 hoặc lỗi internal nghiêm trọng.
- ORA-01555 snapshot too old.
- ORA-01652 unable to extend temp segment.
- ORA-01653/ORA-01654 unable to extend table/index.
- ORA-19809/ORA-19804 liên quan FRA/recovery area.
- Archive destination lỗi hoặc archive không thể ghi.
- Control file, redo log hoặc datafile error.
- Startup/shutdown ngoài kế hoạch.
- Data Guard gap hoặc apply error.
- Job quan trọng thất bại liên tục.

Một lỗi ORA không phải lúc nào cũng là sự cố diện rộng. Ghi timestamp, container, instance, SQL_ID, trace/incident ID và tác động trước khi escalation.

### 5.2. Alert log không phải nơi duy nhất

Kiểm tra thêm:

- Listener log.
- ASM/Clusterware alert log trong RAC/ASM.
- RMAN job output.
- Scheduler job log.
- Application log và connection pool.
- OS kernel/system log.
- Storage/network telemetry.

Đồng bộ thời gian giữa database host, application host và monitoring. Nếu clock lệch, correlation sự kiện có thể sai.

## 6. Kiểm tra capacity: tablespace và datafile

### 6.1. Tablespace usage

Một query tổng quan cho permanent tablespace:

~~~sql
WITH df AS (
    SELECT tablespace_name,
           SUM(bytes) AS allocated_bytes,
           SUM(CASE
                   WHEN autoextensible = 'YES' THEN maxbytes
                   ELSE bytes
               END) AS configured_max_bytes
    FROM dba_data_files
    GROUP BY tablespace_name
),
fs AS (
    SELECT tablespace_name,
           SUM(bytes) AS free_bytes
    FROM dba_free_space
    GROUP BY tablespace_name
)
SELECT t.tablespace_name,
       ROUND(NVL(df.allocated_bytes, 0) / 1024 / 1024, 1) AS allocated_mb,
       ROUND(NVL(fs.free_bytes, 0) / 1024 / 1024, 1) AS free_mb,
       ROUND(
           (NVL(df.allocated_bytes, 0) - NVL(fs.free_bytes, 0))
           / NULLIF(df.allocated_bytes, 0) * 100,
           1
       ) AS used_pct_of_allocated,
       ROUND(NVL(df.configured_max_bytes, 0) / 1024 / 1024, 1) AS configured_max_mb
FROM dba_tablespaces t
LEFT JOIN df ON df.tablespace_name = t.tablespace_name
LEFT JOIN fs ON fs.tablespace_name = t.tablespace_name
WHERE t.contents = 'PERMANENT'
ORDER BY used_pct_of_allocated DESC NULLS LAST;
~~~

Đây là cách tính tổng quan. Cần xem riêng datafile, autoextend, maxsize, bigfile/smallfile, quota và storage layer. Nếu datafile autoextend được cấu hình nhưng filesystem/ASM diskgroup không còn dung lượng, khả năng mở rộng trên thực tế vẫn có thể thất bại.

### 6.2. Chi tiết datafile và autoextend

~~~sql
SELECT tablespace_name,
       file_id,
       file_name,
       ROUND(bytes / 1024 / 1024, 1) AS current_mb,
       autoextensible,
       ROUND(maxbytes / 1024 / 1024, 1) AS max_mb,
       increment_by
FROM dba_data_files
ORDER BY tablespace_name, file_id;
~~~

Đối chiếu dung lượng datafile với dung lượng filesystem hoặc ASM diskgroup. MAXBYTES là giới hạn cấu hình của datafile, không phải dung lượng storage chắc chắn còn cấp được.

### 6.3. Free space có thể phân mảnh

Tổng FREE_BYTES không bảo đảm có một extent liên tục đủ lớn trong mọi trường hợp quản lý segment/tablespace. Với locally managed tablespace và ASSM, Oracle quản lý extent/block theo cơ chế riêng; cần xem lỗi thực tế, extent requirement, datafile và loại segment trước khi kết luận.

### 6.4. Quota user

~~~sql
SELECT username,
       tablespace_name,
       bytes,
       max_bytes
FROM dba_ts_quotas
ORDER BY username, tablespace_name;
~~~

Một user có thể gặp quota exceeded dù tablespace còn free space. Kiểm tra quota riêng thay vì chỉ xem tổng dung lượng tablespace.

## 7. Kiểm tra TEMP và UNDO

### 7.1. TEMP usage hiện tại

~~~sql
SELECT tablespace_name,
       ROUND(SUM(bytes_used) / 1024 / 1024, 1) AS used_mb,
       ROUND(SUM(bytes_free) / 1024 / 1024, 1) AS free_mb
FROM v$temp_space_header
GROUP BY tablespace_name
ORDER BY tablespace_name;
~~~

Xem session đang dùng temporary segment:

~~~sql
SELECT username,
       session_addr,
       session_num,
       sql_id,
       tablespace,
       segtype,
       blocks,
       extents
FROM v$tempseg_usage
ORDER BY blocks DESC;
~~~

TEMP tăng có thể do sort, hash join, parallel query, temporary table hoặc temporary LOB. Không kết luận leak chỉ từ một snapshot; so sánh SQL_ID, session và xu hướng.

### 7.2. UNDO pressure

~~~sql
SELECT begin_time,
       end_time,
       undoblks,
       txncount,
       maxquerylen,
       tuned_undoretention,
       ssolderrcnt,
       nospaceerrcnt
FROM v$undostat
ORDER BY begin_time DESC
FETCH FIRST 24 ROWS ONLY;
~~~

Các tín hiệu:

- SSOLDERRCNT tăng: có lỗi snapshot too old trong khoảng thống kê.
- NOSPACEERRCNT tăng: có tình huống không đủ undo space theo thống kê.
- MAXQUERYLEN lớn: query dài cần undo để đọc nhất quán.
- TUNED_UNDORETENTION: retention được Oracle điều chỉnh theo điều kiện runtime.

Không tăng UNDO_RETENTION một cách mù quáng; cần xem undo tablespace size, workload, retention guarantee và khả năng mở rộng.

### 7.3. Khi TEMP/UNDO gần đầy

Trước khi thay đổi:

1. Xác định tablespace, tempfile/datafile và mức dùng.
2. Tìm SQL/session tiêu thụ lớn.
3. Xem query plan, sort/hash, parallelism và thời gian chạy.
4. Xác nhận có session/job bất thường hoặc runaway.
5. Kiểm tra filesystem/ASM headroom.
6. Chọn biện pháp theo change policy: tối ưu SQL, điều chỉnh workload, thêm tempfile/space hoặc xử lý session có owner xác nhận.
7. Theo dõi sau thay đổi.

Không xóa tempfile hoặc kill session chỉ để làm dashboard giảm số.

## 8. Fast Recovery Area và archive log

FRA lưu các file recovery như archived redo logs, backup pieces, flashback logs và control file autobackup tùy cấu hình.

~~~sql
SELECT name,
       ROUND(space_limit / 1024 / 1024 / 1024, 2) AS limit_gb,
       ROUND(space_used / 1024 / 1024 / 1024, 2) AS used_gb,
       ROUND(space_reclaimable / 1024 / 1024 / 1024, 2) AS reclaimable_gb,
       ROUND(space_used / NULLIF(space_limit, 0) * 100, 1) AS used_pct,
       number_of_files
FROM v$recovery_file_dest;
~~~

SPACE_RECLAIMABLE không đồng nghĩa có thể xóa file tùy ý ngay lập tức. Oracle quản lý retention, backup status và file eligibility.

### 8.1. Archive destination

~~~sql
SELECT dest_id,
       status,
       target,
       destination,
       error,
       transmit_mode,
       affirm
FROM v$archive_dest
WHERE status <> 'INACTIVE'
ORDER BY dest_id;
~~~

Xem trạng thái runtime:

~~~sql
SELECT dest_id,
       status,
       type,
       database_mode,
       recovery_mode,
       error,
       destination
FROM v$archive_dest_status
WHERE status <> 'INACTIVE'
ORDER BY dest_id;
~~~

Một số cột và giá trị hiển thị phụ thuộc cấu hình/version. Nếu destination lỗi, xác minh storage, network, remote standby, quota và lỗi cụ thể trước khi đổi tham số.

### 8.2. Redo log và archive generation

~~~sql
SELECT thread#,
       group#,
       sequence#,
       bytes,
       members,
       archived,
       status
FROM v$log
ORDER BY thread#, group#;
~~~

Xem archive gần đây:

~~~sql
SELECT thread#,
       sequence#,
       first_time,
       next_time,
       archived,
       applied,
       status,
       deleted
FROM v$archived_log
WHERE first_time >= SYSDATE - 1
ORDER BY thread#, sequence#;
~~~

Trong RAC có nhiều redo thread. Không chỉ xem thread 1 nếu database có nhiều instance.

Tốc độ switch log tăng đột biến có thể do redo generation tăng, batch, index rebuild hoặc transaction thay đổi. Cần đối chiếu workload và archive destination.

### 8.3. Không xóa archive bằng filesystem command

Không xóa archived redo log trực tiếp bằng OS command để giải phóng FRA. Làm vậy có thể làm lệch RMAN repository và phá vỡ khả năng recovery/Data Guard.

Dùng RMAN theo retention policy và quy trình đã phê duyệt. Trước khi delete, xác minh backup, applied status trên standby nếu có, deletion policy và yêu cầu PITR.

## 9. Kiểm tra backup và khả năng phục hồi

Backup job thành công chỉ là một tín hiệu. Database chỉ thực sự được bảo vệ khi có thể khôi phục dữ liệu trong RTO/RPO yêu cầu.

### 9.1. Kiểm tra RMAN repository

Trong RMAN:

~~~text
RMAN> LIST BACKUP SUMMARY;
RMAN> REPORT NEED BACKUP;
RMAN> SHOW ALL;
~~~

Kiểm tra:

- Backup database/datafile.
- Archived redo log backup.
- Control file/SPFILE autobackup.
- Backup status, completion time và device.
- Retention policy.
- Encryption wallet/key availability theo chính sách.
- Offsite/object storage copy nếu yêu cầu.

### 9.2. Kiểm tra backup job

Lưu kết quả của mỗi lần chạy:

- Job ID và thời điểm start/end.
- Database/DBID và DB_UNIQUE_NAME.
- Backup type và level.
- Datafile/archive log coverage.
- RMAN exit status.
- Error stack.
- Dung lượng và tốc độ.
- Nơi lưu và thời hạn retention.

Không coi job scheduler SUCCESS là bằng chứng duy nhất. Kiểm tra RMAN output và backup piece availability.

### 9.3. Validate backup

Có thể dùng RMAN để validate backup:

~~~text
RMAN> RESTORE DATABASE VALIDATE;
~~~

Lệnh này kiểm tra khả năng đọc các backup cần thiết theo lựa chọn RMAN và repository. Nó không thay thế một lần restore hoàn chỉnh sang môi trường độc lập và không chứng minh toàn bộ quy trình ứng dụng sau recovery.

Validate có thể tạo I/O đáng kể. Lập lịch, chọn scope và theo dõi tác động.

### 9.4. Restore test

Theo lịch, restore một bản backup vào môi trường kiểm thử tách biệt:

1. Xác định backup piece và recovery point.
2. Chuẩn bị host/storage và Oracle software tương thích.
3. Restore control file/SPFILE theo runbook.
4. Restore datafiles.
5. Recover tới SCN/time mong muốn.
6. Open database theo chế độ phù hợp.
7. Kiểm tra object, row count và ứng dụng.
8. Đo thời gian thực tế.
9. Ghi lỗi, dependency và thời gian từng bước.

Chỉ restore test mới cho bằng chứng thực tế về RTO và các bước vận hành. Không thử restore đè lên production.

### 9.5. RPO và RTO

- **RPO (Recovery Point Objective):** mức dữ liệu tối đa có thể mất, đo theo thời gian hoặc điểm giao dịch.
- **RTO (Recovery Time Objective):** thời gian tối đa để khôi phục dịch vụ.

Backup schedule, archive log backup frequency, Data Guard protection mode, storage replication và restore procedure phải đáp ứng các mục tiêu này.

## 10. Data Guard health check

Chỉ áp dụng cho kiến trúc Data Guard. Xác định database đang là PRIMARY, PHYSICAL STANDBY, LOGICAL STANDBY hay role khác trước khi đánh giá.

### 10.1. Database role và protection

~~~sql
SELECT database_role,
       open_mode,
       protection_mode,
       protection_level,
       switchover_status
FROM v$database;
~~~

### 10.2. Transport lag và apply lag

~~~sql
SELECT name,
       value,
       unit,
       time_computed,
       datum_time
FROM v$dataguard_stats
WHERE name IN ('transport lag', 'apply lag', 'apply finish time');
~~~

So sánh lag với SLA/RPO và workload. Một giá trị lag cũ hoặc DATUM_TIME không cập nhật có thể cho thấy dữ liệu monitoring không còn mới; không chỉ đọc VALUE.

### 10.3. Archive gap

~~~sql
SELECT thread#,
       low_sequence#,
       high_sequence#
FROM v$archive_gap;
~~~

V$ARCHIVE_GAP có thể chỉ ra gap cần xử lý trên physical standby. Kết quả rỗng không thay thế việc kiểm tra transport/apply status và alert log.

### 10.4. Broker

Nếu dùng Data Guard Broker:

~~~text
DGMGRL> SHOW CONFIGURATION;
DGMGRL> SHOW DATABASE VERBOSE '<db_unique_name>';
~~~

Kiểm tra trạng thái configuration, database, transport/apply, warnings và lỗi. DGMGRL có thể cung cấp thông tin rõ hơn về broker-managed configuration.

Không chạy switchover/failover trong health check. Đó là thao tác thay đổi role, cần runbook riêng, precheck, approval, xác nhận client routing và post-check.

## 11. RAC và Clusterware health check

Chỉ áp dụng nếu database dùng RAC/Oracle Restart/Grid Infrastructure.

### 11.1. Instance theo cluster

~~~sql
SELECT inst_id,
       instance_name,
       host_name,
       status,
       startup_time
FROM gv$instance
ORDER BY inst_id;
~~~

Xem services:

~~~sql
SELECT inst_id,
       name,
       network_name,
       pdb
FROM gv$services
ORDER BY inst_id, name;
~~~

### 11.2. Clusterware resources

Trên host với quyền phù hợp:

~~~text
crsctl stat res -t
srvctl status database -db <db_unique_name>
srvctl status service -db <db_unique_name>
~~~

Kiểm tra database, instance, listener, ASM, diskgroup và service resource. Nếu resource OFFLINE/INTERMEDIATE, xác định dependency và alert log trước khi restart.

### 11.3. ASM capacity

Nếu dùng ASM, kiểm tra diskgroup:

~~~sql
SELECT name,
       state,
       type,
       total_mb,
       free_mb,
       usable_file_mb,
       required_mirror_free_mb
FROM v$asm_diskgroup
ORDER BY name;
~~~

USABLE_FILE_MB có tính tới redundancy và mirror requirements; không chỉ nhìn FREE_MB. Diskgroup có free space vật lý nhưng usable space thấp vẫn có thể không đáp ứng allocation mới.

## 12. Performance health check

Health check performance cần kết hợp snapshot/delta và workload context. Counter tích lũy không thể diễn giải như metric tức thời.

### 12.1. System time model

~~~sql
SELECT stat_name,
       value
FROM v$sys_time_model
WHERE stat_name IN ('DB time', 'DB CPU')
ORDER BY stat_name;
~~~

Lấy snapshot đầu/cuối rồi tính delta. DB time là tổng thời gian foreground database activity; có thể lớn hơn elapsed wall-clock của cửa sổ khi nhiều session hoạt động đồng thời.

### 12.2. System statistics

~~~sql
SELECT name,
       value
FROM v$sysstat
WHERE name IN (
    'session logical reads',
    'physical reads',
    'physical writes',
    'redo size',
    'user commits',
    'execute count',
    'parse count (total)',
    'parse count (hard)'
)
ORDER BY name;
~~~

So sánh delta theo cùng khoảng thời gian và cùng workload. Với RAC, dùng GV$SYSSTAT và group theo INST_ID.

### 12.3. Current active sessions

~~~sql
SELECT sid,
       serial#,
       username,
       sql_id,
       event,
       wait_class,
       state,
       seconds_in_wait,
       blocking_session,
       module,
       action
FROM v$session
WHERE type = 'USER'
  AND status = 'ACTIVE'
ORDER BY seconds_in_wait DESC;
~~~

V$SESSION là snapshot hiện tại, không phải lịch sử đầy đủ. Session query ngắn có thể kết thúc trước khi lấy mẫu.

### 12.4. Resource limits

~~~sql
SELECT resource_name,
       current_utilization,
       max_utilization,
       limit_value
FROM v$resource_limit
WHERE resource_name IN ('processes', 'sessions', 'transactions')
ORDER BY resource_name;
~~~

MAX_UTILIZATION là mức cao nhất kể từ khi instance start hoặc reset tương ứng. So sánh với LIMIT_VALUE và headroom; kiểm tra cấu hình processes/sessions khi tải tăng.

### 12.5. Top SQL theo tài nguyên

~~~sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       ROUND(elapsed_time / 1e6, 2) AS elapsed_seconds,
       ROUND(cpu_time / 1e6, 2) AS cpu_seconds,
       buffer_gets,
       disk_reads,
       rows_processed,
       last_active_time
FROM v$sql
WHERE executions > 0
ORDER BY buffer_gets DESC
FETCH FIRST 20 ROWS ONLY;
~~~

V$SQL statistics thường tích lũy theo child cursor. Không coi elapsed_time là thời gian lần chạy cuối; chia theo executions chỉ cho average thô và có thể che giấu tail latency hoặc bind skew.

### 12.6. Runtime plan

Với SQL mục tiêu, thu thập runtime statistics trong session kiểm thử:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       ...
FROM ...;
~~~

Sau khi fetch hết kết quả:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +ALIAS'
    )
);
~~~

So sánh E-Rows, A-Rows, Starts, Buffers, Reads và A-Time. Với Starts lớn hơn 1, xem A-Rows/Starts trước khi kết luận estimate sai.

### 12.7. AWR, ASH và SQL Monitor

AWR, ASH, ADDM và một số tính năng SQL Monitor thuộc các gói Diagnostics/Tuning theo điều khoản Oracle licensing tương ứng. Xác nhận entitlement trước khi bật hoặc sử dụng chúng trong production.

Nếu không có license phù hợp, dùng dynamic performance views, SQL Trace/TKPROF, OS metrics, application telemetry và snapshot/delta được phê duyệt. Quyền SELECT view không tự động chứng minh quyền sử dụng tính năng theo license.

## 13. Scheduler jobs và maintenance windows

### 13.1. Job status

~~~sql
SELECT owner,
       job_name,
       enabled,
       state,
       last_start_date,
       next_run_date,
       failure_count,
       run_count
FROM dba_scheduler_jobs
ORDER BY owner, job_name;
~~~

### 13.2. Job run failures

~~~sql
SELECT owner,
       job_name,
       status,
       error#,
       actual_start_date,
       run_duration,
       additional_info
FROM dba_scheduler_job_run_details
WHERE log_date >= SYSTIMESTAMP - INTERVAL '7' DAY
  AND status <> 'SUCCEEDED'
ORDER BY log_date DESC;
~~~

Kiểm tra:

- Job critical có ENABLED và lịch chạy đúng không?
- Last run có thành công?
- Duration có tăng bất thường?
- Failure_count có tích lũy?
- Job có overlap với batch khác?
- Credential, external job và destination có còn hợp lệ?
- Job có chạy trong đúng PDB/service không?

### 13.3. Maintenance tasks

Xem maintenance window và automatic tasks theo chính sách Oracle. Không tắt auto stats, advisor hoặc maintenance window chỉ vì thấy chúng dùng tài nguyên; xác định task, lịch và tác động trước.

Nếu job chạy chồng giờ cao điểm, điều chỉnh lịch theo change process và xác minh ảnh hưởng đến optimizer statistics/maintenance coverage.

## 14. Database objects và cấu trúc

### 14.1. Invalid objects

~~~sql
SELECT owner,
       object_type,
       object_name,
       status,
       last_ddl_time
FROM dba_objects
WHERE status = 'INVALID'
ORDER BY owner, object_type, object_name;
~~~

Xem lỗi compile:

~~~sql
SELECT owner,
       name,
       type,
       line,
       position,
       text
FROM dba_errors
ORDER BY owner, name, sequence;
~~~

Không compile hàng loạt object invalid trong giờ cao điểm nếu chưa hiểu dependency và tác động. Xác định object thuộc ứng dụng nào và có được deploy gần đây không.

### 14.2. Index unusable hoặc trạng thái bất thường

~~~sql
SELECT owner,
       index_name,
       table_name,
       status,
       visibility,
       last_analyzed
FROM dba_indexes
WHERE status <> 'VALID'
ORDER BY owner, table_name, index_name;
~~~

Partitioned index cần kiểm tra trạng thái partition/subpartition:

~~~sql
SELECT index_owner,
       index_name,
       partition_name,
       status
FROM dba_ind_partitions
WHERE status <> 'USABLE'
ORDER BY index_owner, index_name, partition_name;
~~~

Tên/giá trị trạng thái có thể khác theo loại index và release. Không rebuild mọi index bất thường một cách tự động; trước hết tìm nguyên nhân và xác định thao tác cần thiết.

### 14.3. Constraint disabled/validated

~~~sql
SELECT owner,
       table_name,
       constraint_name,
       constraint_type,
       status,
       validated
FROM dba_constraints
WHERE status <> 'ENABLED'
   OR validated <> 'VALIDATED'
ORDER BY owner, table_name, constraint_name;
~~~

Một số constraint có thể được disable có chủ đích trong ETL. So sánh với deployment baseline và xác nhận owner trước khi enable/validate.

## 15. Security và access review

Health check bảo mật nên tập trung vào thay đổi và sai lệch so với chính sách.

### 15.1. Account status

~~~sql
SELECT username,
       account_status,
       lock_date,
       expiry_date,
       profile,
       authentication_type
FROM dba_users
ORDER BY username;
~~~

Không tự unlock account hoặc reset password chỉ vì account bị LOCKED. Kiểm tra owner, lý do, audit trail và quy trình identity trước.

### 15.2. Quyền hệ thống rộng

~~~sql
SELECT grantee,
       privilege,
       admin_option
FROM dba_sys_privs
WHERE privilege LIKE '%ANY%'
   OR privilege IN (
       'DBA',
       'SELECT ANY DICTIONARY',
       'BECOME USER',
       'EXEMPT ACCESS POLICY'
   )
ORDER BY grantee, privilege;
~~~

Đây là danh sách cần review, không phải khẳng định mọi quyền trong kết quả đều sai. So sánh với approved access matrix và kiểm tra user/role nhận quyền gián tiếp.

### 15.3. Role và object grant

~~~sql
SELECT grantee,
       granted_role,
       admin_option,
       default_role
FROM dba_role_privs
ORDER BY grantee, granted_role;
~~~

~~~sql
SELECT owner,
       table_name,
       grantee,
       privilege,
       grantable
FROM dba_tab_privs
WHERE grantee IN ('PUBLIC', 'APP_USER', 'APP_READ', 'APP_WRITE')
ORDER BY grantee, owner, table_name, privilege;
~~~

Review quyền PUBLIC, ANY privileges, GRANT OPTION và role lồng nhau theo chính sách.

### 15.4. Audit

Nếu dùng Unified Auditing, kiểm tra policy đang enable và audit records theo phạm vi quyền:

~~~sql
SELECT event_timestamp,
       dbusername,
       action_name,
       object_schema,
       object_name,
       return_code
FROM unified_audit_trail
WHERE event_timestamp >= SYSTIMESTAMP - INTERVAL '1' DAY
ORDER BY event_timestamp DESC;
~~~

Audit view có thể chứa dữ liệu nhạy cảm; giới hạn người đọc và retention. Không bật policy rộng hoặc ghi toàn bộ SQL bind values nếu chưa đánh giá dung lượng và privacy.

## 16. Patch, configuration và change inventory

Một health report nên lưu:

- Oracle Database version và RU.
- OPatch inventory từ host.
- SQL patch registry.
- Parameter khác default.
- Component/option registry.
- Thay đổi DDL, index, statistics và service.
- Thời điểm deploy và người thực hiện.

### 16.1. SQL patch registry

~~~sql
SELECT patch_id,
       patch_type,
       action,
       status,
       action_time,
       description
FROM dba_registry_sqlpatch
ORDER BY action_time DESC;
~~~

Kiểm tra STATUS, ACTION và thời điểm để đối chiếu patch đã áp dụng ở SQL layer. Kết hợp OPatch inventory trên Oracle Home; SQL registry không thay thế inventory binary.

### 16.2. Parameter khác default

~~~sql
SELECT name,
       value,
       isdefault,
       issys_modifiable,
       ispdb_modifiable
FROM v$parameter
WHERE isdefault = 'FALSE'
ORDER BY name;
~~~

Lưu snapshot trước/sau thay đổi. Một tham số khác default có thể là cấu hình đúng của hệ thống; không tự reset về default khi không biết lý do.

### 16.3. Component registry

~~~sql
SELECT comp_id,
       comp_name,
       version,
       status
FROM dba_registry
ORDER BY comp_id;
~~~

INVALID component hoặc version không nhất quán cần được DBA điều tra trước khi chạy script sửa chữa.

## 17. Xây cấu trúc runbook chuẩn

Mỗi runbook nên có cùng cấu trúc để người trực ca có thể sử dụng khi chịu áp lực.

| Phần | Nội dung |
|---|---|
| ID và title | Mã duy nhất, tên sự cố/thao tác |
| Purpose | Mục tiêu và kết quả mong đợi |
| Scope | Database, instance, PDB, service, môi trường |
| Trigger | Alert, metric, ticket hoặc sự kiện kích hoạt |
| Severity | Mức độ và tác động nghiệp vụ |
| Owner | Primary, backup, approver, escalation contact |
| Preconditions | Quyền, backup, capacity, maintenance window |
| Diagnostics | Query/lệnh chỉ đọc và cách diễn giải |
| Actions | Các bước thao tác theo thứ tự |
| Guardrails | Điều kiện không được tiếp tục |
| Validation | Bằng chứng xác nhận phục hồi |
| Rollback | Cách hoàn nguyên và điều kiện sử dụng |
| Communication | Ai cần được thông báo và thời điểm |
| Evidence | Log, SQL output, timestamp, ticket, change ID |
| Revision | Version, ngày review, người phê duyệt |

### 17.1. Phân biệt bước quan sát và bước thay đổi

Đánh dấu mỗi lệnh:

- **READ:** chỉ đọc trạng thái.
- **CHANGE:** thay đổi cấu hình hoặc metadata.
- **DISRUPTIVE:** có thể làm gián đoạn session/service hoặc ảnh hưởng người dùng.
- **RECOVERY:** thao tác phục hồi dữ liệu/instance/role.

Người trực ca phải biết lệnh nào chỉ quan sát và lệnh nào làm thay đổi hệ thống. Không trộn các câu SELECT và ALTER SYSTEM vào một script health check tự động.

### 17.2. Preconditions bắt buộc cho hành động rủi ro

Trước hành động CHANGE/DISRUPTIVE/RECOVERY, runbook phải ghi:

1. Xác nhận đúng DB_UNIQUE_NAME, DBID, host, instance và PDB.
2. Xác nhận incident/change ticket và người phê duyệt.
3. Xác nhận backup/recovery point cần thiết.
4. Kiểm tra role primary/standby và RAC topology.
5. Kiểm tra dependency và người dùng bị ảnh hưởng.
6. Ghi snapshot trạng thái trước thao tác.
7. Xác định stop condition và rollback.
8. Có người thứ hai review nếu chính sách yêu cầu.

Không thực hiện lệnh có tác động chỉ vì một alert đơn lẻ.

## 18. Runbook mẫu: database/service không truy cập được

<badge color="warning">Incident runbook</badge>

**Trigger:** Application health check thất bại, listener/service không phản hồi hoặc database không ở trạng thái mong đợi.

**Mục tiêu:** Xác định lớp lỗi và khôi phục kết nối theo đúng kiến trúc.

### Bước 1 — Xác nhận phạm vi

- Chỉ một application hay mọi consumer?
- Một PDB/service hay toàn database?
- Một instance hay toàn RAC?
- Chỉ một vùng mạng hay mọi nơi?
- Có deploy, patch, failover hoặc network change gần đây không?

### Bước 2 — Kiểm tra từ application

- Connection pool state và timeout.
- DNS/connect descriptor.
- Service name và credentials.
- Network/TLS.
- Một request health nhẹ.
- Timestamp và error stack.

### Bước 3 — Kiểm tra host/listener

~~~text
lsnrctl status
lsnrctl services
~~~

Với cluster, kiểm tra SRVCTL/CRSCTL status theo môi trường.

### Bước 4 — Kiểm tra database

Nếu có thể kết nối bằng tài khoản vận hành:

~~~sql
SELECT instance_name, status, database_status
FROM v$instance;

SELECT name, open_mode, database_role
FROM v$database;
~~~

Nếu database không mở, lấy alert log, trace và host/storage status. Không chạy STARTUP/SHUTDOWN hoặc restart resource trước khi xác định trạng thái hiện tại và quy trình recovery phù hợp.

### Bước 5 — Hành động và xác minh

Hành động start/restart/relocate thuộc người có thẩm quyền theo kiến trúc. Sau khi service trở lại:

- Xác nhận database/PDB open mode đúng.
- Xác nhận listener service registration.
- Thử kết nối từ application path.
- Chạy query health nhẹ.
- Kiểm tra error rate và connection pool.
- Theo dõi alert log và session load.
- Ghi thời gian bắt đầu, phục hồi và nguyên nhân.

## 19. Runbook mẫu: tablespace hoặc FRA gần đầy

**Trigger:** Warning/critical threshold, lỗi unable to extend hoặc FRA gần chạm limit.

### Bước 1 — Xác định tài nguyên

- Permanent tablespace, TEMP, UNDO hay FRA?
- Tăng đều hay đột biến?
- Một datafile/tempfile hay toàn storage?
- Autoextend có bật không?
- Filesystem/ASM còn usable space không?
- Có batch, load, index rebuild hoặc archive backlog không?

### Bước 2 — Thu thập bằng chứng

Dùng query ở phần tablespace, TEMP/UNDO và FRA. Lấy hai hoặc nhiều snapshot để tính growth rate.

### Bước 3 — Tìm consumer

- Segment lớn nhất và tốc độ tăng.
- SQL/session dùng TEMP.
- UNDO transaction dài.
- Archive generation và destination error.
- Backup/retention policy.
- Datafile maxsize và storage headroom.

### Bước 4 — Chọn hành động

Các lựa chọn có thể gồm tối ưu SQL, dừng/điều chỉnh batch theo owner, mở rộng storage/datafile/tempfile, xử lý archive destination hoặc thay retention theo quy trình.

Không xóa file archive/backup bằng OS command. Không resize xuống hoặc drop datafile chỉ để giảm cảnh báo. Mọi thay đổi storage cần xác nhận capacity, filesystem/ASM và backup.

### Bước 5 — Xác minh

- Dung lượng đã tăng hoặc tốc độ tiêu thụ đã giảm.
- Không còn lỗi unable to extend.
- FRA có headroom và archive destination VALID.
- Backup/recovery vẫn đáp ứng retention.
- Không gây ảnh hưởng ứng dụng.
- Ghi lại dung lượng trước/sau và nguyên nhân gốc.

## 20. Runbook mẫu: blocking và SQL chậm

**Trigger:** p95/p99 tăng, request timeout, blocking session kéo dài hoặc CPU/I/O tăng bất thường.

### Bước 1 — Xác định phạm vi và SQL

Ghi SQL_ID, module/action, service, user, instance, plan hash và thời điểm.

### Bước 2 — Xem blocker

~~~sql
SELECT sid,
       serial#,
       username,
       sql_id,
       event,
       wait_class,
       seconds_in_wait,
       blocking_instance,
       blocking_session,
       module,
       action
FROM gv$session
WHERE blocking_session IS NOT NULL
ORDER BY seconds_in_wait DESC;
~~~

Nếu không dùng RAC, có thể dùng V$SESSION và BLOCKING_SESSION. Xác định blocker chain, transaction age và SQL đang giữ lock.

### Bước 3 — Xem SQL và plan

- Kiểm tra V$SQL elapsed/CPU/buffer gets/disk reads.
- Thu thập DBMS_XPLAN runtime statistics khi phù hợp.
- So sánh E-Rows/A-Rows/Starts.
- Xem access/filter predicates.
- Đối chiếu wait event và application trace.

### Bước 4 — Hành động

Ưu tiên xác định transaction owner, query, lock scope và tác động. Liên hệ application owner trước khi kết thúc session. Kill/disconnect session là thao tác disruptive; chỉ dùng theo policy, có phê duyệt và hiểu rollback/transaction impact.

Không kill session chỉ vì nó đứng đầu danh sách active hoặc có thời gian chạy dài.

### Bước 5 — Xác minh

- Blocking chain đã hết.
- Request latency/error rate trở về baseline.
- Transaction được hoàn tất hoặc rollback.
- Không có session mới tiếp tục tạo cùng contention.
- Ghi SQL_ID, blocker, root cause và hành động.

## 21. Runbook mẫu: backup thất bại hoặc restore chưa được chứng minh

**Trigger:** RMAN job failed, backup không có trong repository, archive backup trễ hoặc restore test thất bại.

### Bước 1 — Xác định mục tiêu recovery

- Database và DBID.
- RPO/RTO.
- Recovery point cần giữ.
- Primary/standby role.
- Backup destination và encryption dependencies.

### Bước 2 — Kiểm tra repository/output

~~~text
RMAN> LIST BACKUP SUMMARY;
RMAN> REPORT NEED BACKUP;
RMAN> SHOW ALL;
~~~

Đọc job log và error stack. Xác nhận datafile, control file, SPFILE và archived redo coverage.

### Bước 3 — Kiểm tra nguyên nhân

- Storage/object store/network.
- Credential/secret expiry.
- RMAN channel/device configuration.
- FRA full.
- Archive destination error.
- Backup piece expired/missing.
- Encryption wallet/key.
- Retention/deletion policy.

### Bước 4 — Retry có kiểm soát

Không retry vô hạn. Xác nhận nguyên nhân đã xử lý, capacity còn đủ và retry không tạo tải ảnh hưởng production. Ghi job ID và backup pieces mới.

### Bước 5 — Xác minh recoverability

Chạy validate phù hợp trong cửa sổ được phê duyệt và duy trì restore test định kỳ. Nếu restore test thất bại, mở incident, đánh giá RPO/RTO thực tế và khắc phục trước khi tuyên bố database được bảo vệ.

## 22. Runbook mẫu: Data Guard lag hoặc archive gap

**Trigger:** Transport/apply lag vượt SLA, standby không apply redo hoặc broker báo WARNING/ERROR.

### Bước 1 — Xác định role và thời điểm dữ liệu

~~~sql
SELECT database_role, open_mode, protection_mode
FROM v$database;

SELECT name, value, unit, time_computed, datum_time
FROM v$dataguard_stats
WHERE name IN ('transport lag', 'apply lag');
~~~

### Bước 2 — Kiểm tra transport và gap

- V$ARCHIVE_DEST_STATUS.
- V$ARCHIVE_GAP.
- Alert log primary và standby.
- DGMGRL SHOW CONFIGURATION nếu dùng broker.
- Network, storage và archive destination.

### Bước 3 — Phân loại

- Transport lag: redo chưa được chuyển tới standby.
- Apply lag: redo đã tới nhưng chưa apply kịp.
- Archive gap: thiếu sequence cần thiết.
- Stale datum: metric không được cập nhật gần đây.

### Bước 4 — Hành động

Không xóa archive, đổi protection mode, defer destination hoặc failover theo suy đoán. Dùng runbook Data Guard cụ thể cho phiên bản, transport mode, broker và topology. Escalate tới DBA chịu trách nhiệm HA khi vượt RPO.

### Bước 5 — Xác minh

- Transport/apply lag trở về ngưỡng.
- Gap được xử lý.
- Broker configuration SUCCESS nếu áp dụng.
- Standby role/open mode đúng.
- Client/service routing và protection level được xác nhận.

## 23. Runbook mẫu: job quan trọng thất bại

**Trigger:** Scheduler job critical không chạy, thất bại hoặc vượt thời lượng dự kiến.

1. Xác định owner, job name, schedule, last start, next run và failure_count.
2. Đọc DBA_SCHEDULER_JOB_RUN_DETAILS và additional_info.
3. Kiểm tra credential, destination, privilege, dependency và resource pressure.
4. Xác nhận job có chạy trùng với batch khác hay maintenance window không.
5. Kiểm tra dữ liệu đầu vào và checkpoint/idempotency.
6. Chỉ retry sau khi xác định retry an toàn và không tạo duplicate side effect.
7. Nếu cần disable/enable/run job, ghi change/incident và owner approval theo policy.
8. Xác nhận job success, row count, business reconciliation và downstream completion.

Không coi trạng thái SUCCEEDED là đủ nếu job không xử lý đúng số hàng hoặc dữ liệu nghiệp vụ.

## 24. Severity, escalation và communication

Một ma trận ví dụ:

| Mức | Ví dụ | Phản hồi |
|---|---|---|
| SEV1 / Critical | Database production down, data corruption nghi ngờ, RPO bị đe dọa, primary/standby mất khả năng bảo vệ | Kích hoạt incident bridge, DBA lead và service owner ngay |
| SEV2 / High | Service quan trọng suy giảm mạnh, FRA/tablespace sắp đầy, backup critical thất bại, lag vượt RPO guardrail | Acknowledge khẩn, chỉ định owner và cập nhật thường xuyên |
| SEV3 / Medium | Job lỗi có workaround, capacity warning còn headroom, SQL regression có phạm vi hạn chế | Xử lý trong ca, theo dõi và lên kế hoạch |
| SEV4 / Low | Cảnh báo xu hướng, invalid object không được dùng, cleanup/review định kỳ | Ghi ticket và xử lý theo lịch |

Ngưỡng và thời hạn phản hồi phải được tổ chức định nghĩa theo SLA. Không dùng bảng ví dụ này thay thế incident policy chính thức.

### 24.1. Nội dung cập nhật sự cố

Mỗi update nên có:

- Tác động người dùng và hệ thống.
- Thời điểm bắt đầu/phát hiện.
- Phạm vi database/service/PDB/instance.
- Điều đã xác nhận và điều còn giả thuyết.
- Hành động đang thực hiện và owner.
- Rủi ro/RPO/RTO.
- Thời điểm cập nhật tiếp theo.

Tránh ghi credential, secret, raw personal data hoặc bind values nhạy cảm vào ticket/chat.

### 24.2. Điều kiện đóng incident

Chỉ đóng khi:

- Dịch vụ được xác nhận hoạt động từ góc nhìn ứng dụng.
- Error rate và latency trở về mức chấp nhận.
- Backup/HA protection được xác nhận nếu liên quan.
- Không còn cảnh báo critical chưa xử lý.
- Root cause hoặc next investigation owner được ghi.
- Evidence và timeline được lưu.
- Follow-up action có owner và due date.

## 25. Lưu bằng chứng và xây dashboard

Mỗi lần health check nên lưu snapshot có timestamp, database, instance, container và người/automation chạy.

Gợi ý bộ trường:

| Trường | Ví dụ |
|---|---|
| captured_at | 2026-11-14T20:00:00+07:00 |
| db_unique_name | PRODDB |
| dbid | Giá trị DBID |
| instance | PRODDB1 |
| con_name | APP_PDB |
| check_id | FRA_CAPACITY |
| status | OK / WARN / CRITICAL |
| observed_value | 72.4 |
| threshold | 80 |
| unit | percent |
| trend | +3.2 percentage points/day |
| owner | DBA_ON_CALL |
| ticket | Incident/change reference |

Không chỉ lưu giá trị mới nhất. Trend giúp phát hiện FRA hoặc tablespace sẽ đầy trước khi chạm threshold.

### 25.1. Dashboard theo vai trò

- DBA: instance, tablespace, FRA, backup, wait, SQL, jobs.
- Application owner: endpoint latency, error, throughput, connection pool.
- Service owner: availability, RTO/RPO, incident, capacity forecast.
- Security: account/privilege/audit drift, patch status.
- Management: SLA, trend, risk, remediation due date.

### 25.2. Data retention và bảo vệ telemetry

Giữ đủ dữ liệu để so sánh xu hướng và điều tra sự cố, nhưng có retention policy. Giới hạn quyền truy cập vì SQL text, module, client identifier và audit records có thể chứa thông tin nhạy cảm.

## 26. Báo cáo health check hằng ngày mẫu

~~~text
ORACLE DAILY HEALTH REPORT
Date/time:
Database / DB_UNIQUE_NAME:
DBID:
Instance(s):
PDB / Service:
Role: PRIMARY / STANDBY
Oracle version / RU:
Operator / Automation run ID:

1. AVAILABILITY
   Instance status:
   Database open mode / role:
   PDB status:
   Listener / service:
   Application connectivity:
   Result: OK / WARN / CRITICAL

2. CAPACITY
   Permanent tablespace:
   TEMP:
   UNDO:
   FRA:
   ASM/filesystem:
   Processes/sessions headroom:
   Growth trend:
   Result:

3. PERFORMANCE
   DB time / DB CPU delta:
   Throughput:
   p95 / p99 application latency:
   Top SQL:
   Wait/blocking:
   I/O and redo:
   Result:

4. BACKUP / RECOVERY
   Last full/incremental backup:
   Archived redo coverage:
   RMAN status:
   Validation / restore-test date:
   RPO/RTO status:
   Result:

5. HIGH AVAILABILITY
   RAC resources:
   Data Guard transport/apply lag:
   Archive gap:
   Broker status:
   Result:

6. JOBS / OBJECTS
   Critical scheduler failures:
   Invalid objects:
   Unusable indexes/partitions:
   Maintenance task:
   Result:

7. SECURITY / CHANGE
   Account/privilege drift:
   Audit alerts:
   Patch/config change:
   Result:

OPEN ITEMS
- Finding:
- Impact:
- Owner:
- Ticket:
- Due date:
- Escalation:
~~~

## 27. Checklist vận hành theo tần suất

### Liên tục / alert-driven

- [ ] Instance/database/service down.
- [ ] Critical PDB closed hoặc restricted ngoài kế hoạch.
- [ ] Tablespace/FRA/TEMP/ASM threshold.
- [ ] Archive destination error.
- [ ] Data Guard lag/gap vượt guardrail.
- [ ] Backup critical thất bại.
- [ ] Blocking/deadlock kéo dài.
- [ ] Application error/latency vượt SLO.

### Hằng ngày

- [ ] Xác nhận database role và open mode.
- [ ] Xác nhận PDB/service/listener và kết nối ứng dụng.
- [ ] Đọc alert log và incident mới.
- [ ] Kiểm tra RMAN job và archived redo coverage.
- [ ] Kiểm tra FRA, tablespace, TEMP, UNDO.
- [ ] Kiểm tra scheduler failures.
- [ ] Kiểm tra active blockers và resource limits.
- [ ] Kiểm tra Data Guard/RAC nếu áp dụng.
- [ ] Ghi health report và giao owner cho cảnh báo.

### Hằng tuần

- [ ] Phân tích capacity growth và forecast.
- [ ] Xem top SQL theo elapsed, CPU và buffer gets.
- [ ] Xem p95/p99 và throughput trend.
- [ ] Kiểm tra invalid objects/index state.
- [ ] Review job duration/failure trend.
- [ ] Review Data Guard lag và standby health.
- [ ] Kiểm tra user/role/privilege drift.
- [ ] Review alert noise và threshold effectiveness.

### Hằng tháng / theo maintenance cycle

- [ ] Restore/validate backup theo kế hoạch.
- [ ] Kiểm tra RTO/RPO bằng diễn tập.
- [ ] Review patch/RU inventory và vulnerability advisory.
- [ ] Review capacity forecast và storage procurement.
- [ ] Review quyền đặc quyền, database link và credential rotation.
- [ ] Review audit policy và log retention.
- [ ] Review runbook, contact và escalation tree.
- [ ] Kiểm tra change record và post-change performance.
- [ ] Xác nhận monitoring coverage và alert delivery.

## 28. Nguyên tắc an toàn khi vận hành

1. Xác minh đúng database, DBID, DB_UNIQUE_NAME, host, instance, PDB và role trước mọi thao tác.
2. Bắt đầu bằng quan sát và thu thập bằng chứng; không sửa trạng thái chỉ để làm alert biến mất.
3. Không chạy lệnh disruptive nếu chưa xác định impact, owner, approval và rollback.
4. Không xóa datafile, redo log, archive log, backup piece hoặc FRA file bằng OS command.
5. Không kill session chỉ vì thời gian chạy dài; xác định transaction và application owner.
6. Không restart database/listener/ASM hoặc relocate service trong health check thường kỳ.
7. Không đổi protection mode, switchover hoặc failover Data Guard ngoài runbook HA.
8. Không disable constraint, trigger, audit hoặc maintenance task để xử lý triệu chứng tạm thời.
9. Không cấp quyền rộng để làm monitoring query chạy được; cấp quyền đọc đúng phạm vi.
10. Không đưa password, wallet secret, token hoặc dữ liệu nhạy cảm vào script, ticket và báo cáo.
11. Dùng maintenance window và change record cho thao tác có tác động.
12. Sau mỗi hành động, xác nhận cả trạng thái database và trải nghiệm ứng dụng.

## 29. Thiết kế runbook để người khác có thể thực hiện

Một runbook tốt phải đủ rõ để một DBA trực ca khác có thể thực hiện mà không cần đoán.

- Dùng tên database/service/PDB thực tế trong bản runbook của môi trường.
- Đặt biến cấu hình ở đầu, không hardcode host/credential rải rác.
- Ghi quyền tối thiểu cần có cho từng bước.
- Đánh dấu lệnh read-only và lệnh thay đổi.
- Đưa expected output hoặc tiêu chí đánh giá.
- Nêu rõ trường hợp không tiếp tục.
- Đặt checkpoint sau mỗi bước quan trọng.
- Ghi rollback command và tác dụng phụ.
- Đính kèm link monitoring/dashboard/ticket phù hợp trong tài liệu nội bộ.
- Ghi version Oracle và ngày kiểm thử runbook.
- Review sau mỗi incident, patch hoặc thay đổi topology.

### 29.1. Kiểm thử runbook

Trước khi đánh dấu runbook sẵn sàng:

1. Một người không phải tác giả đọc và thực hiện trên môi trường lab.
2. Kiểm tra mọi query và lệnh có đúng release/privilege.
3. Mô phỏng điều kiện kích hoạt.
4. Xác nhận expected output.
5. Kiểm tra bước dừng/escalation.
6. Thử rollback hoặc restore trong môi trường an toàn.
7. Ghi thời gian thực hiện.
8. Sửa các chỗ mơ hồ.
9. Định kỳ review lại owner/contact và dependency.

Không kiểm thử runbook bằng cách cố ý gây outage hoặc làm đầy production.

## 30. Ghi nhớ cốt lõi

- Health check phát hiện trạng thái và xu hướng; runbook hướng dẫn hành động có kiểm soát.
- Kiểm tra availability, capacity, performance, backup/recovery, HA, jobs, objects, security và change inventory.
- Chia lịch thành continuous alerts, daily, weekly, monthly và event-driven.
- Mỗi check cần owner, tần suất, threshold, escalation và evidence.
- Không dùng một threshold phần trăm chung cho mọi database; xét growth rate, headroom, storage limit và thời gian phản ứng.
- Phân biệt primary/standby, RAC/non-RAC và CDB/PDB khi diễn giải trạng thái.
- V$SYSSTAT, V$SYS_TIME_MODEL và V$SQL có counter tích lũy; dùng snapshot/delta cùng workload context.
- Tablespace, TEMP, UNDO, FRA và ASM là các loại tài nguyên khác nhau; tìm consumer trước khi mở rộng hoặc dọn dẹp.
- Backup SUCCESS không đồng nghĩa restore đã được chứng minh; phải validate và restore test theo lịch.
- Không xóa archive/backup bằng OS command; dùng RMAN và retention/deletion policy.
- Data Guard transport lag khác apply lag; kiểm tra datum freshness, archive gap và broker status.
- AWR/ASH/SQL Monitor và một số tính năng tuning có yêu cầu license; xác nhận entitlement.
- Scheduler job SUCCESS cần được đối chiếu với business result và số hàng xử lý.
- Security review cần xem account, privilege, role, audit và database link theo least privilege.
- Runbook phải có trigger, preconditions, diagnostics, actions, guardrails, validation, rollback, owner và evidence.
- Bắt đầu bằng read-only diagnostics; mọi thao tác disruptive cần approval và change/incident procedure.
- Sau thay đổi, xác nhận database, service và application cùng phục hồi; lưu timeline và root cause.

### Tài liệu Oracle nên đối chiếu

- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/) — Database lifecycle, tablespaces, datafiles, redo, archive, users and maintenance.
- [Oracle Database Backup and Recovery User's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/) — RMAN backup, validation, restore, recovery and retention.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/) — V$DATABASE, V$INSTANCE, V$SESSION, V$RECOVERY_FILE_DEST, V$UNDOSTAT and dictionary views.
- [Oracle Data Guard Concepts and Administration](https://docs.oracle.com/en/database/oracle/oracle-database/19/sbydb/) — Transport/apply, role transition, broker and standby monitoring.
- [Oracle Real Application Clusters Administration and Deployment Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/racad/) — RAC, services, instances and Clusterware operations.
- [Oracle Database Security Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/) — Users, roles, auditing and privilege management.
- [Oracle Database Licensing Information User Manual](https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/) — Diagnostics Pack and Tuning Pack licensing.

Dictionary columns, utility syntax, HA features and licensing terms can vary by release and deployment. Confirm the exact Oracle version, topology, privileges and support contract; test operational commands and restore procedures in a representative non-production environment before relying on them during an incident.

