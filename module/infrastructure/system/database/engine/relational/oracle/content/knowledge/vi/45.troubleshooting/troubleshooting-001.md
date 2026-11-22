# Quy trình xác định thời điểm, phạm vi, thay đổi gần nhất và bằng chứng

Khi Oracle Database phát sinh sự cố, điều khó nhất thường không phải chạy ngay một lệnh sửa lỗi mà là dựng lại chính xác chuyện gì đã xảy ra: bắt đầu lúc nào, ảnh hưởng đến đâu, thay đổi nào diễn ra ngay trước đó, thành phần nào liên quan và bằng chứng nào đủ tin cậy để xác nhận nguyên nhân.

Một quy trình xử lý sự cố tốt cần đi theo thứ tự:

1. **Chuẩn hóa thời gian:** thống nhất timezone, mốc giờ, SCN và độ lệch đồng hồ.
2. **Khoanh vùng phạm vi:** xác định database, PDB, instance, service, schema, object, session, SQL và nhóm người dùng bị ảnh hưởng.
3. **Dựng lại thay đổi gần nhất:** đối chiếu deployment, DDL, cấu hình, job, quyền, statistics, patch, service và thay đổi hạ tầng.
4. **Thu thập bằng chứng:** lấy trạng thái runtime, audit, alert log, trace, execution plan, transaction metadata và log của ứng dụng.
5. **Lập timeline và kiểm chứng giả thuyết:** liên kết các sự kiện bằng thời gian, SCN, SQL_ID, XID, session và object.
6. **Bảo toàn chứng cứ và chọn hành động:** lưu bản gốc, ghi rõ nguồn, người thu thập, thời điểm và mọi thay đổi được thực hiện trong quá trình xử lý.

Không nên kết luận nguyên nhân chỉ từ một thông báo lỗi hoặc một thay đổi xuất hiện gần thời điểm sự cố. Sự kiện xảy ra trước sự cố là đầu mối để điều tra, chưa phải bằng chứng chứng minh quan hệ nhân quả.

## 1. Mục tiêu và nguyên tắc điều tra

### 1.1 Bốn câu hỏi phải trả lời

| Câu hỏi | Kết quả cần có |
|---|---|
| Thời điểm nào? | Thời điểm bắt đầu, thời điểm phát hiện, khoảng thời gian bị ảnh hưởng, timezone và mốc SCN nếu có |
| Phạm vi nào? | Database/PDB/instance/service, ứng dụng, schema/object, dữ liệu, session và người dùng bị ảnh hưởng |
| Thay đổi gần nhất là gì? | Danh sách thay đổi có timestamp, người/automation thực hiện, nội dung và kết quả |
| Bằng chứng nào? | Log, audit record, SQL/plan, transaction ID, trace, metric, ảnh chụp trạng thái và checksum |

### 1.2 Phân biệt dữ kiện, suy luận và giả thuyết

Trong incident report, nên gắn nhãn rõ:

- **Fact:** quan sát trực tiếp từ nguồn có thể kiểm tra, ví dụ alert log ghi ORA-00600 lúc 10:04:31 UTC.
- **Inference:** kết luận hợp lý từ nhiều facts, ví dụ lỗi bắt đầu sau khi service chuyển instance và các connection cũ bị mất.
- **Hypothesis:** khả năng đang được kiểm chứng, ví dụ thay đổi firewall có thể làm gián đoạn ONS.
- **Unknown:** thông tin chưa có hoặc nguồn dữ liệu không đủ để xác định.

Không biến một hypothesis thành root cause chỉ vì nó phù hợp với câu chuyện ban đầu.

### 1.3 Bảo toàn trước khi thay đổi

Trước khi restart instance, kill session, flush shared pool, clear log, gather statistics, đổi tham số hoặc chạy DDL:

- Ghi lại thời điểm và trạng thái hiện tại.
- Thu thập alert log, error stack và các view runtime cần thiết.
- Lưu SQL_ID, child number, plan hash, session identifiers và wait event.
- Chụp snapshot counters nếu cần so sánh delta.
- Ghi rõ ai đã thực hiện hành động, lệnh nào, ở đâu và lúc nào.

Nếu cần containment khẩn cấp để giảm tác động, ưu tiên an toàn dịch vụ theo runbook; đồng thời ghi lại bằng chứng có thể thu thập trước hành động và thời điểm hành động bắt đầu.

## 2. Chuẩn hóa thời gian

Một timeline sai timezone hoặc đồng hồ lệch có thể khiến DBA liên kết nhầm deployment, log và transaction. Trước tiên phải thống nhất mốc thời gian dùng trong incident.

### 2.1 Chọn một chuẩn thời gian

Nên lưu timestamp theo ISO 8601 kèm UTC offset, và dùng UTC làm chuẩn khi đối chiếu nhiều hệ thống:

~~~text
2026-11-14T10:25:31.482Z
2026-11-14T17:25:31.482+07:00
~~~

Hai giá trị trên biểu diễn cùng một thời điểm. Không lưu chuỗi giờ địa phương mà thiếu timezone vì sau đó không thể biết chính xác offset.

Trong incident report, ghi:

- Timezone chuẩn, ví dụ UTC.
- Timezone của DBA/operator.
- Timezone của database host.
- Timezone của application host.
- Nguồn đồng bộ thời gian (NTP/chrony/Windows Time hoặc dịch vụ hạ tầng).
- Độ lệch đồng hồ được biết tại thời điểm điều tra.

### 2.2 Phân biệt các hàm thời gian Oracle

~~~sql
SELECT SYSTIMESTAMP              AS database_host_time,
       CURRENT_TIMESTAMP         AS session_time,
       LOCALTIMESTAMP            AS session_local_timestamp,
       DBTIMEZONE                AS database_time_zone,
       SESSIONTIMEZONE            AS session_time_zone,
       SYS_EXTRACT_UTC(SYSTIMESTAMP) AS systimestamp_utc
FROM dual;
~~~

| Hàm/giá trị | Ý nghĩa |
|---|---|
| SYSTIMESTAMP | Timestamp của hệ điều hành máy chủ database, có fractional seconds và timezone offset |
| CURRENT_TIMESTAMP | Timestamp hiện tại theo timezone của session |
| LOCALTIMESTAMP | Timestamp theo timezone session nhưng không kèm timezone trong kiểu trả về |
| DBTIMEZONE | Time zone của database, chủ yếu liên quan kiểu dữ liệu có timezone và lưu trữ |
| SESSIONTIMEZONE | Time zone được thiết lập cho session hiện tại |
| SYS_EXTRACT_UTC | Chuyển một timestamp with time zone sang UTC |

Không giả định DBTIMEZONE là timezone của máy chủ. SYSTIMESTAMP phản ánh đồng hồ host; CURRENT_TIMESTAMP phụ thuộc SESSIONTIMEZONE. Khi so sánh log từ ứng dụng và database, phải chuyển chúng về cùng timezone.

### 2.3 Kiểm tra thời gian ở session

~~~sql
SELECT sys_context('USERENV', 'SESSION_USER') AS session_user,
       sys_context('USERENV', 'CURRENT_SCHEMA') AS current_schema,
       sys_context('USERENV', 'CON_NAME') AS con_name,
       sys_context('USERENV', 'SERVICE_NAME') AS service_name,
       sys_context('USERENV', 'INSTANCE_NAME') AS instance_name,
       SESSIONTIMEZONE AS session_time_zone,
       CURRENT_TIMESTAMP AS current_timestamp
FROM dual;
~~~

Session có thể dùng ALTER SESSION SET TIME_ZONE để thay đổi SESSIONTIMEZONE. Vì vậy, một session có thể hiển thị timestamp khác với session khác dù cùng chạy trên một database host.

### 2.4 Đối chiếu với hệ điều hành

DBA cần kiểm tra đồng hồ trên đúng host/VM/container chạy database và trên application servers. Ví dụ Linux:

~~~bash
date -u --iso-8601=ns
timedatectl status
chronyc tracking
~~~

Ví dụ Windows PowerShell:

~~~powershell
Get-Date -AsUTC -Format o
Get-TimeZone
w32tm /query /status
~~~

Các lệnh cần chạy trên host tương ứng và theo quyền vận hành. Không coi thời gian trên laptop của DBA là nguồn chuẩn cho timestamp của database server.

### 2.5 Clock drift và log đến trễ

Một hệ thống có thể ghi log theo thời gian nhận ở collector thay vì thời gian phát sinh tại source. Agent log có thể buffer rồi gửi trễ khi mạng khôi phục. Vì vậy cần phân biệt:

- Event time: thời điểm component ghi nhận sự kiện.
- Ingest/receive time: thời điểm hệ thống log nhận sự kiện.
- Processing time: thời điểm hệ thống giám sát xử lý hoặc hiển thị sự kiện.

Nếu các mốc không khớp, kiểm tra clock drift, buffering, queue backlog và timezone conversion trước khi kết luận thứ tự sự kiện.

## 3. Dùng SCN để liên kết thay đổi dữ liệu

Timestamp hữu ích cho con người, nhưng SCN (System Change Number) là mốc logic của Oracle dùng để sắp thứ tự thay đổi trong database.

### 3.1 Lấy SCN hiện tại

~~~sql
SELECT current_scn
FROM v$database;
~~~

Hoặc trong PL/SQL:

~~~sql
SELECT DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER AS current_scn
FROM dual;
~~~

Ghi SCN cùng timestamp, DBID, instance và container trong snapshot điều tra. SCN giúp liên kết Flashback Query, redo/archive logs và các thao tác recovery.

### 3.2 Timestamp và SCN không thay thế lẫn nhau

- Timestamp là thời gian lịch (wall clock), chịu ảnh hưởng timezone và clock synchronization.
- SCN là thứ tự logic của thay đổi trong database.
- Nhiều thay đổi có thể xảy ra trong một khoảng thời gian rất ngắn; timestamp hiển thị có thể không phân biệt đủ chính xác.
- Một SCN có thể ánh xạ gần đúng sang timestamp, nhưng không nên coi đó là timestamp chính xác tuyệt đối.

### 3.3 SCN_TO_TIMESTAMP và TIMESTAMP_TO_SCN

~~~sql
SELECT SCN_TO_TIMESTAMP(:p_scn) AS approximate_time
FROM dual;
~~~

~~~sql
SELECT TIMESTAMP_TO_SCN(
           TO_TIMESTAMP_TZ(
               '2026-11-14 10:00:00 +00:00',
               'YYYY-MM-DD HH24:MI:SS TZH:TZM'
           )
       ) AS approximate_scn
FROM dual;
~~~

Các hàm này cung cấp ánh xạ gần đúng trong phạm vi metadata ánh xạ còn được lưu. Không giả định chúng có thể chuyển đổi mọi SCN/timestamp trong lịch sử dài. Có thể gặp lỗi khi mốc nằm ngoài phạm vi ánh xạ còn khả dụng.

### 3.4 ORA_ROWSCN không phải audit trail

ORA_ROWSCN có thể hỗ trợ xác định SCN liên quan đến thay đổi hàng, nhưng mặc định có thể phản ánh ở mức block thay vì từng row. Nếu bảng được tạo với ROWDEPENDENCIES, Oracle có thể theo dõi ở mức row với overhead lưu trữ bổ sung.

ORA_ROWSCN không cho biết user, câu SQL, giá trị cũ hoặc chính xác thời điểm thay đổi. Không dùng nó thay thế unified auditing, Flashback Version Query hoặc transaction metadata.

### 3.5 Lưu ý khi dùng Flashback Query

~~~sql
SELECT *
FROM app.orders AS OF SCN :p_scn
WHERE order_id = :p_order_id;
~~~

Flashback Query có thể giúp xem trạng thái dữ liệu tại mốc trước đó. Khả năng truy vấn phụ thuộc undo còn khả dụng, quyền và các giới hạn của object. Nếu undo cần thiết đã bị ghi đè, truy vấn có thể thất bại với snapshot too old.

## 4. Xác định phạm vi ảnh hưởng

Không bắt đầu bằng câu hỏi “SQL nào lỗi?” mà hãy xác định lớp nào đang bị ảnh hưởng. Một incident có thể chỉ ảnh hưởng một session, một service, một PDB, một object hoặc toàn bộ cluster.

### 4.1 Các chiều phạm vi cần ghi nhận

| Chiều | Câu hỏi cần trả lời |
|---|---|
| Database | DBID, DB_UNIQUE_NAME, database role, open mode là gì? |
| Container | Sự cố ở CDB root hay PDB nào? |
| Instance/node | Một instance hay tất cả instance? Host nào? |
| Service | Service nào bị lỗi, relocate hoặc quá tải? |
| Application | Ứng dụng, module, endpoint, batch hoặc client nào bị ảnh hưởng? |
| Schema/object | Schema, table, index, package, job hoặc database link nào liên quan? |
| Data | Loại bản ghi, key range, tenant hoặc partition nào bị ảnh hưởng? |
| Session/SQL | SID/SERIAL#, SQL_ID, child cursor, XID nào liên quan? |
| User/tenant | Một người dùng, một nhóm hay tất cả tenant? |
| Time window | Bắt đầu, kết thúc và khoảng có dữ liệu không đáng tin cậy? |

### 4.2 Xác định database và instance

~~~sql
SELECT name,
       dbid,
       db_unique_name,
       database_role,
       open_mode,
       log_mode,
       current_scn
FROM v$database;
~~~

~~~sql
SELECT instance_number,
       instance_name,
       host_name,
       version,
       startup_time,
       status,
       database_status
FROM v$instance;
~~~

Trong RAC:

~~~sql
SELECT inst_id,
       instance_name,
       host_name,
       startup_time,
       status
FROM gv$instance
ORDER BY inst_id;
~~~

STARTUP_TIME rất quan trọng khi đối chiếu cumulative counters: sau restart, nhiều bộ đếm trong memory được khởi tạo lại.

### 4.3 Xác định container/PDB

~~~sql
SELECT con_id,
       name,
       open_mode,
       restricted
FROM v$containers
ORDER BY con_id;
~~~

Từ CDB root, các view CDB_*/GV$ có thể chứa nhiều container. Giữ CON_ID khi join hoặc tổng hợp; không gộp dữ liệu cùng tên object từ các PDB khác nhau.

### 4.4 Xác định service

~~~sql
SELECT inst_id,
       name,
       network_name,
       goal,
       clb_goal,
       aq_ha_notification
FROM gv$services
ORDER BY name, inst_id;
~~~

Đối chiếu service name trong connection string của ứng dụng, cấu hình service trên cluster và SERVICE_NAME trong V$SESSION.

### 4.5 Xác định session liên quan

~~~sql
SELECT inst_id,
       sid,
       serial#,
       username,
       status,
       service_name,
       machine,
       program,
       module,
       action,
       client_identifier,
       sql_id,
       sql_child_number,
       prev_sql_id,
       event,
       wait_class,
       blocking_instance,
       blocking_session,
       logon_time
FROM gv$session
WHERE type = 'USER'
ORDER BY inst_id, status, username;
~~~

Đây là snapshot hiện tại. Session đã disconnect sẽ không còn trong V$SESSION; để điều tra lịch sử cần audit, ASH/AWR nếu được cấp phép, application logs hoặc trace đã lưu.

### 4.6 Xác định object và dependency

~~~sql
SELECT owner,
       object_name,
       subobject_name,
       object_type,
       status,
       created,
       last_ddl_time
FROM dba_objects
WHERE owner = UPPER(:p_owner)
  AND object_name = UPPER(:p_object)
ORDER BY object_type, subobject_name;
~~~

LAST_DDL_TIME là dấu hiệu object đã có DDL tác động, nhưng không cho biết chính xác câu DDL, người thực hiện hay mọi thay đổi liên quan. Cần kết hợp audit trail, deployment records và log quản trị.

### 4.7 Xác định data range

Nếu sự cố liên quan dữ liệu, ghi lại:

- Primary key hoặc business key của các row mẫu.
- Partition/subpartition liên quan.
- Khoảng SCN/timestamp trước và sau thay đổi.
- Số row bị ảnh hưởng, số row đã được sửa sau đó.
- Các bảng liên quan qua foreign key hoặc quy trình nghiệp vụ.
- Tenant/customer/account bị ảnh hưởng.

Không chỉ lưu một row mẫu rồi kết luận phạm vi chỉ có một row. Dùng query có điều kiện rõ ràng để đếm phạm vi và lưu kết quả tại thời điểm điều tra.

## 5. Xác định thay đổi gần nhất

Thay đổi gần nhất có thể là DDL, DML, deployment, cấu hình database, thay đổi service, patch, job, statistics, network hoặc OS. Hãy dựng một danh sách thay đổi theo thời gian thay vì chỉ hỏi DBA có chạy lệnh gì hay không.

### 5.1 Nhóm thay đổi cần rà soát

| Nhóm | Ví dụ |
|---|---|
| Application deployment | Release mới, hotfix, migration script, thay đổi connection pool |
| Database DDL | CREATE/ALTER/DROP TABLE, INDEX, VIEW, PACKAGE, TRIGGER |
| DML/data load | Bulk load, ETL, import, batch update/delete |
| Security | GRANT/REVOKE, user/role/profile, password rotation |
| Initialization parameters | SGA/PGA, optimizer, cursor, parallelism, undo, archive |
| Optimizer statistics | DBMS_STATS gather, histogram, extended stats, locked stats |
| Scheduler | Job mới, thay đổi schedule, credential, destination |
| Service/RAC | Start/stop/relocate service, instance maintenance, node eviction |
| Storage | ASM disk group, filesystem, mount, capacity, latency |
| Network | DNS, firewall, load balancer, SCAN/listener, TLS certificate |
| Database patch/upgrade | RU, one-off patch, OPatch, datapatch, COMPATIBLE/OFE |
| External systems | API, message broker, file transfer, identity provider |

### 5.2 Xem thời điểm DDL gần nhất

~~~sql
SELECT owner,
       object_name,
       object_type,
       created,
       last_ddl_time,
       status
FROM dba_objects
WHERE last_ddl_time >= :p_from_time
ORDER BY last_ddl_time DESC;
~~~

Query này tạo danh sách ứng viên, không phải lịch sử DDL đầy đủ. Một object có thể được đánh dấu thay đổi do nhiều loại DDL hoặc thao tác quản trị. Nó không xác định actor.

### 5.3 Xem DDL và audit trail

Nếu Unified Auditing được cấu hình để ghi nhận DDL, có thể tra:

~~~sql
SELECT event_timestamp,
       dbusername,
       action_name,
       object_schema,
       object_name,
       return_code,
       client_program_name,
       userhost,
       sql_text
FROM unified_audit_trail
WHERE event_timestamp >= :p_from_time
  AND action_name IN (
      'CREATE TABLE',
      'ALTER TABLE',
      'DROP TABLE',
      'CREATE INDEX',
      'ALTER INDEX',
      'DROP INDEX',
      'CREATE PROCEDURE',
      'ALTER PROCEDURE',
      'DROP PROCEDURE',
      'GRANT',
      'REVOKE'
  )
ORDER BY event_timestamp;
~~~

Các action name có thể khác theo loại câu lệnh, audit policy và release. Trước khi dùng, kiểm tra cột và policy thực tế. Nếu database dùng traditional auditing hoặc mixed mode, các nguồn audit có thể khác.

Không có audit record không chứng minh rằng không có thay đổi. Có thể policy chưa bật, audit chưa áp dụng cho user/action, record bị purge hoặc sự kiện xảy ra trước khi logging được cấu hình.

### 5.4 Kiểm tra thay đổi tham số

~~~sql
SELECT name,
       value,
       isdefault,
       issys_modifiable,
       isses_modifiable,
       ispdb_modifiable,
       con_id
FROM v$parameter
WHERE name IN (
    'memory_target',
    'sga_target',
    'pga_aggregate_target',
    'processes',
    'sessions',
    'open_cursors',
    'optimizer_features_enable',
    'optimizer_mode',
    'undo_retention',
    'log_buffer',
    'parallel_max_servers'
)
ORDER BY name, con_id;
~~~

V$PARAMETER phản ánh giá trị hiệu lực trong instance/session hiện tại theo phạm vi view. Để biết ai đã thay đổi tham số và lúc nào, cần đối chiếu alert log, audit, SPFILE history/configuration management và change records.

Kiểm tra giá trị lưu trong SPFILE:

~~~sql
SELECT sid,
       name,
       value,
       isspecified,
       update_comment
FROM v$spparameter
WHERE isspecified = 'TRUE'
ORDER BY name, sid;
~~~

V$SPPARAMETER mô tả cấu hình trong SPFILE; nó không phải audit trail về lịch sử sửa đổi.

### 5.5 Kiểm tra thay đổi optimizer statistics

~~~sql
SELECT owner,
       table_name,
       object_type,
       last_analyzed,
       stale_stats,
       stattype_locked
FROM dba_tab_statistics
WHERE last_analyzed >= :p_from_time
ORDER BY last_analyzed DESC;
~~~

Đối chiếu với log DBMS_STATS, scheduler job, maintenance window và deployment. Statistics mới có thể làm execution plan thay đổi, nhưng LAST_ANALYZED không tự chứng minh statistics change là nguyên nhân.

### 5.6 Kiểm tra các object mới hoặc thay đổi

~~~sql
SELECT owner,
       object_name,
       object_type,
       created,
       last_ddl_time,
       status
FROM dba_objects
WHERE created >= :p_from_time
   OR last_ddl_time >= :p_from_time
ORDER BY GREATEST(created, last_ddl_time) DESC;
~~~

Đây là cách tìm nhanh các object có dấu thời gian mới. Cần kết hợp DBA_DEPENDENCIES, source control và audit để biết nội dung và tác động thực tế.

### 5.7 Kiểm tra Scheduler jobs

~~~sql
SELECT owner,
       job_name,
       enabled,
       state,
       job_type,
       job_action,
       repeat_interval,
       last_start_date,
       next_run_date
FROM dba_scheduler_jobs
ORDER BY owner, job_name;
~~~

Lịch sử run:

~~~sql
SELECT log_date,
       owner,
       job_name,
       status,
       error#,
       actual_start_date,
       run_duration,
       additional_info
FROM dba_scheduler_job_run_details
WHERE log_date >= :p_from_time
ORDER BY log_date DESC;
~~~

Kiểm tra cả job bị disable, job mới thêm, job chạy lâu bất thường và job trùng thời điểm incident. Job action có thể gọi package hoặc external procedure; cần lần theo dependency.

### 5.8 Kiểm tra deployment và thay đổi ứng dụng

Database không thể tự biết toàn bộ release của ứng dụng. Lấy thông tin từ:

- CI/CD deployment history: release ID, commit SHA, pipeline run, start/end time.
- Migration tool: version schema trước/sau, script đã chạy, checksum và kết quả.
- Application logs: build/version, pod/container, endpoint, request ID.
- Configuration management: thay đổi datasource URL, pool size, timeout, retry, TLS, feature flags.
- Secret manager: thời điểm rotate credential hoặc certificate, không đưa secret value vào incident evidence.

Đối chiếu thời điểm deploy với database DDL, package invalidation, connection errors và SQL plan changes.

## 6. Thu thập bằng chứng runtime trong Oracle

Runtime views phản ánh trạng thái hiện tại hoặc counters tích lũy. Phải ghi rõ loại dữ liệu và thời điểm snapshot.

### 6.1 Session đang hoạt động

~~~sql
SELECT inst_id,
       sid,
       serial#,
       username,
       status,
       service_name,
       module,
       action,
       client_identifier,
       sql_id,
       sql_child_number,
       sql_exec_start,
       last_call_et,
       event,
       wait_class,
       state,
       blocking_instance,
       blocking_session
FROM gv$session
WHERE type = 'USER'
  AND status = 'ACTIVE'
ORDER BY last_call_et DESC;
~~~

STATUS ACTIVE không có nghĩa session đang dùng CPU; session có thể đang chờ. Đọc EVENT, WAIT_CLASS, STATE và blocker information cùng SQL_ID.

### 6.2 SQL cursor và plan

~~~sql
SELECT inst_id,
       sql_id,
       child_number,
       plan_hash_value,
       executions,
       parse_calls,
       buffer_gets,
       disk_reads,
       rows_processed,
       cpu_time,
       elapsed_time,
       last_active_time,
       module,
       action,
       sql_text
FROM gv$sql
WHERE sql_id = :p_sql_id
ORDER BY inst_id, child_number;
~~~

CPU_TIME và ELAPSED_TIME trong các view SQL là microseconds. Đây thường là counters tích lũy theo cursor, không phải số liệu riêng của một execution. Parallel execution có thể làm tổng elapsed database time lớn hơn wall-clock duration.

Xem plan thực tế:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        :p_sql_id,
        :p_child_number,
        'ALLSTATS LAST +PEEKED_BINDS +PREDICATE +NOTE'
    )
);
~~~

Chỉ xem bind values nếu được phép; bind có thể chứa PII, credential, token hoặc dữ liệu nhạy cảm. Redact trước khi đưa vào ticket hoặc chia sẻ ra ngoài nhóm được ủy quyền.

### 6.3 Wait events và blocker

~~~sql
SELECT inst_id,
       sid,
       serial#,
       event,
       wait_class,
       total_waits,
       time_waited_micro,
       average_wait
FROM gv$session_event
WHERE time_waited_micro > 0
ORDER BY time_waited_micro DESC;
~~~

V$SESSION_EVENT/GV$SESSION_EVENT là số liệu tích lũy theo session. Để biết wait đang xảy ra, xem GV$SESSION.EVENT/STATE; để biết phần tăng trong khoảng incident, lấy hai snapshot.

### 6.4 Transaction đang mở

~~~sql
SELECT s.inst_id,
       s.sid,
       s.serial#,
       s.username,
       s.sql_id,
       t.xidusn,
       t.xidslot,
       t.xidsqn,
       t.start_scn,
       t.start_time,
       t.used_ublk,
       t.used_urec
FROM gv$session s
JOIN gv$transaction t
  ON t.inst_id = s.inst_id
 AND t.ses_addr = s.saddr
ORDER BY t.start_time;
~~~

Transaction đang mở có thể giữ lock hoặc tạo undo/redo lớn. XID trong GV$TRANSACTION giúp liên kết với Flashback Transaction Query khi các điều kiện cấu hình và quyền đáp ứng.

### 6.5 Cumulative counters: luôn lấy snapshot

V$SYSSTAT, V$SESSTAT, V$SQL và wait views thường chứa counters tích lũy. Lấy snapshot T0 và T1, sau đó tính:

\[
\Delta C = C_{T1} - C_{T0}
\]

\[
\text{Rate} = \frac{\Delta C}{\text{seconds between samples}}
\]

Khi so sánh, giữ cùng INST_ID, CON_ID, SID/SERIAL#, SQL_ID/CHILD_NUMBER và cùng vòng đời instance/cursor. Nếu instance restart hoặc cursor bị aged out/reload, delta có thể âm hoặc không còn liên tục.

## 7. Log và audit là bằng chứng theo thời gian

### 7.1 Alert log

Alert log ghi lại sự kiện quan trọng của instance/database như startup/shutdown, checkpoint, archive error, ORA errors, recovery, parameter change và một số sự kiện quản trị.

Truy vấn alert log qua ADR view:

~~~sql
SELECT originating_timestamp,
       normalized_timestamp,
       message_type,
       message_level,
       process_id,
       message_text
FROM v$diag_alert_ext
WHERE originating_timestamp >=
      TO_TIMESTAMP_TZ(
          '2026-11-14 09:00:00 +00:00',
          'YYYY-MM-DD HH24:MI:SS TZH:TZM'
      )
ORDER BY originating_timestamp;
~~~

Điều chỉnh mốc thời gian theo incident thực tế. V$DIAG_ALERT_EXT có thể đọc alert log dạng XML trong ADR; quyền truy cập phụ thuộc quyền dictionary/diagnostic của tài khoản.

### 7.2 ADRCI

ADRCI có thể xem alert log và quản lý incident/trace:

~~~text
adrci
show homes
set home diag/rdbms/<db_unique_name>/<instance_name>
show alert -tail 200
show incident
show problem
~~~

Tên ADR home thay đổi theo database, instance và host. Không giả định cùng một ADR home trên mọi RAC node.

### 7.3 Trace files

Khi có ORA-00600, ORA-07445, process crash hoặc lỗi nội bộ, Oracle có thể tạo trace file trong ADR. Ghi lại:

- Timestamp và process ID.
- Incident ID/problem key nếu có.
- File path và kích thước.
- Stack/error arguments.
- SQL_ID/session nếu trace cung cấp.
- Tên host, instance, database và version/RU.

Không chỉnh sửa trace gốc. Nếu cần redact dữ liệu nhạy cảm, tạo bản sao đã redact và giữ bản gốc theo chính sách bảo mật.

### 7.4 Unified Audit Trail

~~~sql
SELECT event_timestamp,
       dbusername,
       action_name,
       object_schema,
       object_name,
       system_privilege_used,
       return_code,
       userhost,
       client_program_name,
       client_identifier,
       sql_text
FROM unified_audit_trail
WHERE event_timestamp >= :p_from_time
ORDER BY event_timestamp;
~~~

Audit record chỉ tồn tại nếu action/user/object nằm trong audit policy có hiệu lực và audit record chưa bị purge. Không có record không đồng nghĩa không có sự kiện.

### 7.5 Fine-Grained Auditing

Fine-Grained Auditing (FGA) có thể ghi nhận truy cập dữ liệu theo policy trên bảng/view, điều kiện và cột. Kiểm tra DBA_FGA_AUDIT_TRAIL hoặc view tương ứng khi ứng dụng có policy FGA.

FGA hữu ích khi cần biết truy cập một nhóm dữ liệu nhạy cảm, nhưng không tự động bật cho mọi bảng. Kiểm tra policy và phạm vi predicate trước khi dùng làm bằng chứng.

### 7.6 Listener và network logs

Khi ứng dụng không kết nối được database, đối chiếu:

- Listener log: connection request, service registration, refused connection.
- SCAN listener và local listener trong RAC.
- ONS client/server logs: FAN notification, SSL, topology.
- Firewall/load balancer logs: reset, timeout, deny, route change.
- DNS logs và certificate/TLS rotation.
- Application pool logs: borrow timeout, validation failure, reconnect.

Lỗi kết nối có thể xuất phát từ mạng, DNS, TLS, service registration hoặc pool; không mặc định là database engine failure.

## 8. Flashback và transaction evidence

Khi nghi ngờ dữ liệu bị thay đổi hoặc xóa, có thể dùng Flashback để tìm row versions và transaction.

### 8.1 Flashback Version Query

~~~sql
SELECT versions_startscn,
       versions_endscn,
       versions_starttime,
       versions_endtime,
       versions_xid,
       versions_operation,
       order_id,
       status,
       total_amount
FROM app.orders
VERSIONS BETWEEN TIMESTAMP
    TO_TIMESTAMP('2026-11-14 09:00:00', 'YYYY-MM-DD HH24:MI:SS')
AND TO_TIMESTAMP('2026-11-14 11:00:00', 'YYYY-MM-DD HH24:MI:SS')
WHERE order_id = :p_order_id
ORDER BY versions_startscn;
~~~

VERSIONS_XID liên kết row version với transaction. Version Query cần undo còn khả dụng; UNDO_RETENTION là mục tiêu và không bảo đảm tuyệt đối nếu undo tablespace thiếu chỗ.

### 8.2 Flashback Transaction Query

~~~sql
SELECT xid,
       start_scn,
       start_timestamp,
       commit_scn,
       commit_timestamp,
       logon_user,
       operation,
       table_owner,
       table_name,
       row_id,
       undo_sql
FROM flashback_transaction_query
WHERE xid = :p_xid
ORDER BY undo_change#;
~~~

View cung cấp metadata và SQL logic ngược. Điều kiện cấu hình/quyền gồm COMPATIBLE phù hợp, minimal supplemental logging và SELECT ANY TRANSACTION. UNDO_SQL không phải bản phục hồi hoàn hảo; review trước khi thực thi.

### 8.3 Redo logs và archived logs

~~~sql
SELECT thread#,
       sequence#,
       first_time,
       next_time,
       archived,
       status
FROM v$log_history
WHERE first_time BETWEEN :p_from_time AND :p_to_time
ORDER BY thread#, sequence#;
~~~

~~~sql
SELECT thread#,
       sequence#,
       first_time,
       completion_time,
       archived,
       deleted,
       status,
       name
FROM v$archived_log
WHERE first_time BETWEEN :p_from_time AND :p_to_time
ORDER BY thread#, sequence#;
~~~

Redo/archive evidence giúp liên kết thời gian và SCN. Nếu cần phân tích redo chi tiết, LogMiner có thể hỗ trợ nhưng phải có archive/online redo cần thiết, supplemental logging phù hợp, quyền và quy trình riêng.

## 9. AWR, ASH và lịch sử hiệu năng

Các dynamic performance views cho biết trạng thái hiện tại và một số counters trong memory. Để điều tra lịch sử, DBA có thể cần AWR, ASH hoặc monitoring repository.

### 9.1 AWR

AWR lưu snapshot thống kê hiệu năng định kỳ, hỗ trợ so sánh workload, top SQL, wait events, load profile và resource usage theo thời gian.

Các view thường gặp:

- DBA_HIST_SNAPSHOT
- DBA_HIST_SQLSTAT
- DBA_HIST_SYSSTAT
- DBA_HIST_SYSTEM_EVENT
- DBA_HIST_ACTIVE_SESS_HISTORY

Đối chiếu DBID, INSTANCE_NUMBER, SNAP_ID và thời gian snapshot. Một report AWR bao phủ khoảng thời gian rộng có thể làm mờ một spike rất ngắn; cần kết hợp log và snapshot chi tiết hơn.

### 9.2 ASH

Active Session History lấy mẫu các session đang active theo thời gian, hữu ích để phân tích session, SQL_ID, wait event, module và blocking trong quá khứ.

Nguồn:

- V$ACTIVE_SESSION_HISTORY: dữ liệu ASH trong memory.
- DBA_HIST_ACTIVE_SESS_HISTORY: dữ liệu ASH đã lưu trong AWR.

ASH là sampled data, không phải bản ghi đầy đủ từng thao tác SQL. Một sự kiện rất ngắn có thể không được lấy mẫu.

### 9.3 Licensing

AWR, ASH, ADDM và một số chức năng SQL Tuning/SQL Monitor có thể thuộc Oracle Diagnostics Pack hoặc Tuning Pack tùy tính năng và phiên bản. Trước khi sử dụng trong production, xác minh quyền license của tổ chức. Việc view tồn tại hoặc truy vấn được không tự chứng minh quyền sử dụng feature.

Nếu không có quyền dùng pack, dùng dynamic performance views, alert log, audit trail, application logs và monitoring tool được cấp phép phù hợp.

## 10. Dựng timeline từ nhiều nguồn

Timeline là danh sách sự kiện đã chuẩn hóa theo một timezone, mỗi dòng có timestamp, source, object/session liên quan và độ tin cậy.

### 10.1 Cấu trúc timeline

| UTC time | Source | Event | Scope | Evidence ID | Confidence |
|---|---|---|---|---|---|
| 09:48:12Z | CI/CD | Release R2026.11.14.2 completed | API service | DEP-1821 | Verified |
| 09:52:04Z | Unified Audit | ALTER TABLE APP.ORDERS | APP.ORDERS | AUD-771 | Verified |
| 10:01:18Z | App log | Error rate begins to rise | orders-api | APP-2201 | Verified |
| 10:02:07Z | Alert log | ORA-00060 detected | DB instance 1 | ADR-031 | Verified |
| 10:04:30Z | DBA observation | Blocking chain captured | PDB SALES | SNAP-009 | Verified |

Các thời gian trong bảng chỉ minh họa. Thực tế phải lấy từ nguồn tương ứng và ghi rõ timezone.

### 10.2 Xác định điểm bắt đầu

Có thể xác định nhiều mốc:

- First known bad: thời điểm đầu tiên có bằng chứng lỗi.
- First customer impact: thời điểm người dùng đầu tiên bị ảnh hưởng.
- Detection time: hệ thống monitoring hoặc người vận hành phát hiện.
- Start of degradation: thời điểm metric bắt đầu lệch khỏi baseline.
- Change time: thời điểm deployment/configuration/DDL thay đổi.

Các mốc này có thể khác nhau. Không dùng detection time thay cho thời điểm sự cố thực sự bắt đầu.

### 10.3 Correlation IDs

Ưu tiên các định danh liên kết giữa hệ thống:

- Request ID/trace ID từ application logs.
- DB session SID/SERIAL# và INST_ID.
- SQL_ID/CHILD_NUMBER/PLAN_HASH_VALUE.
- Transaction XID/LTXID nếu có.
- Service, module, action và client identifier.
- DBID, CON_ID, instance, host.
- SCN và redo thread/sequence.

Một timestamp gần nhau nhưng không có định danh liên kết chưa đủ để khẳng định hai sự kiện cùng một request hoặc transaction.

### 10.4 Phân loại độ tin cậy

| Mức | Tiêu chí |
|---|---|
| High | Nguồn trực tiếp, timestamp/identity rõ, có thể tái kiểm tra |
| Medium | Nguồn gián tiếp nhưng được hỗ trợ bởi ít nhất một nguồn độc lập |
| Low | Suy luận từ metric tổng hợp, timestamp không chắc hoặc thiếu identity |
| Unknown | Chưa có dữ liệu hoặc log đã hết retention |

## 11. Bảo toàn bằng chứng và chain of custody

Bằng chứng điều tra cần có thể tái kiểm tra. Không chỉnh sửa file log gốc, không copy đè và không chỉ dán một phần log vào chat mà bỏ mất metadata.

### 11.1 Lập evidence register

Mỗi artifact nên có:

| Trường | Nội dung |
|---|---|
| Evidence ID | Mã duy nhất |
| Source | Database view, ADR, listener, app log, CI/CD, OS |
| Original path/query | Đường dẫn hoặc câu SQL đã dùng |
| Host/DB/instance/PDB | Nơi dữ liệu được lấy |
| Collected by | Người hoặc service account thu thập |
| Collected at | Timestamp UTC và offset gốc nếu có |
| Time range | Khoảng thời gian nội dung bao phủ |
| Size/row count | Kích thước file hoặc số dòng |
| SHA-256 | Hash của artifact gốc |
| Redaction | Nội dung đã redact và lý do |
| Storage location | Vị trí lưu trữ có kiểm soát |

### 11.2 Hash file để xác nhận tính toàn vẹn

Linux:

~~~bash
sha256sum alert.log listener.log incident-trace.trc
~~~

Windows PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 -LiteralPath 'C:\evidence\alert.log'
~~~

Ghi hash, thời điểm lấy và đường dẫn vào evidence register. Nếu tạo bản redact, hash bản gốc và bản redact riêng; không ghi đè bản gốc.

### 11.3 Lưu kết quả truy vấn database

Khi spool SQL output:

- Ghi nguyên văn câu SQL, bind values đã redact, user, container và thời điểm chạy.
- Lưu column headings và row count.
- Ghi timezone/session settings.
- Ghi lỗi SQL nếu có; không bỏ qua phần output lỗi.
- Ghi DBID, instance, startup time và current SCN.

Ví dụ SQL*Plus:

~~~sql
SET ECHO ON
SET FEEDBACK ON
SET TIMING ON
SET LINESIZE 250
SET PAGESIZE 500
SPOOL incident_session_snapshot.txt

SELECT SYSTIMESTAMP AS collected_at,
       SYS_CONTEXT('USERENV', 'DB_NAME') AS db_name,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name,
       SYS_CONTEXT('USERENV', 'INSTANCE_NAME') AS instance_name
FROM dual;

SELECT current_scn FROM v$database;

SPOOL OFF
~~~

Không ghi password, token, private key hoặc dữ liệu cá nhân không cần thiết vào spool.

### 11.4 Redaction và dữ liệu nhạy cảm

SQL text, bind values, trace, audit trail và application logs có thể chứa:

- Email, phone, địa chỉ hoặc thông tin định danh.
- Access token, session token, credential.
- Dữ liệu tài chính hoặc dữ liệu khách hàng.
- Literal nghiệp vụ nhạy cảm trong SQL.

Chỉ chia sẻ với nhóm được phép. Khi cần gửi ra ngoài nhóm incident, tạo bản đã redact và giữ nguyên bản gốc trong kho evidence có kiểm soát.

### 11.5 Retention và quyền truy cập

Đặt quyền đọc hạn chế, retention period, encryption at rest/in transit và quy trình xóa có phê duyệt. Incident evidence có thể chứa thông tin nhạy cảm hơn log vận hành thông thường.

## 12. Quy trình xử lý theo từng giai đoạn

### Giai đoạn A — Stabilize và mở incident

1. Gán incident ID và người điều phối.
2. Ghi thời điểm phát hiện, hệ thống báo lỗi và symptom người dùng.
3. Xác định mức độ ảnh hưởng và service đang degraded/down.
4. Ghi lại hành động containment đã thực hiện hoặc đang đề xuất.
5. Chỉ định một nguồn timeline chuẩn (UTC).

### Giai đoạn B — Capture trạng thái ban đầu

1. Ghi DBID, DB_UNIQUE_NAME, role, open mode, version/RU.
2. Ghi instance, host, startup time và PDB.
3. Ghi current SCN và timestamp.
4. Chụp V$SESSION/GV$SESSION, wait events, blockers và SQL_ID.
5. Chụp V$SQL/GV$SQL cho các SQL liên quan.
6. Lưu alert log, listener log, ONS log và trace hiện có.
7. Lấy snapshot counters nếu cần so sánh delta.

### Giai đoạn C — Khoanh vùng

1. Xác định service, instance, PDB, schema và object.
2. So sánh node/instance bị ảnh hưởng với node còn khỏe.
3. Xác định tenant, user, request, data range và time window.
4. Kiểm tra transaction đang mở, blocker và dependency.
5. Định lượng số request lỗi, số row bị ảnh hưởng và mức độ lan rộng.

### Giai đoạn D — Dựng lại thay đổi gần nhất

1. Lấy deployment/migration history.
2. Tra audit DDL, GRANT/REVOKE và thay đổi user.
3. So sánh parameters/SPFILE và service configuration.
4. Kiểm tra object LAST_DDL_TIME, invalid objects và dependency.
5. Kiểm tra statistics, scheduler jobs và data loads.
6. Đối chiếu OS, storage, DNS, firewall, listener và certificate changes.
7. Ghi mỗi thay đổi cùng nguồn, actor và mức tin cậy.

### Giai đoạn E — Kiểm chứng giả thuyết

1. Chọn giả thuyết giải thích được nhiều facts nhất.
2. Tìm bằng chứng độc lập ủng hộ.
3. Tìm bằng chứng phản bác hoặc giải thích thay thế.
4. So sánh với baseline và node/service không bị ảnh hưởng.
5. Thử nghiệm trên môi trường an toàn nếu cần.
6. Chỉ kết luận root cause khi evidence đủ mạnh.

### Giai đoạn F — Khắc phục và xác nhận

1. Chọn hành động có phạm vi nhỏ nhất đáp ứng mục tiêu.
2. Ghi pre-change snapshot và người phê duyệt.
3. Thực hiện theo runbook/change control.
4. Đo lại error rate, latency, waits, resource usage và data correctness.
5. Kiểm tra không có regression ở workload khác.
6. Lưu post-change snapshot và ghi kết quả.

### Giai đoạn G — Đóng incident

1. Ghi root cause hoặc trạng thái chưa xác định.
2. Ghi timeline đã xác minh.
3. Ghi phạm vi ảnh hưởng và dữ liệu cần kiểm tra/phục hồi.
4. Ghi hành động khắc phục, rollback và kết quả.
5. Ghi follow-up action, owner và deadline.
6. Bảo toàn evidence theo retention policy.

## 13. Mẫu incident report

~~~text
Incident ID:
Severity:
Incident commander:
Database / DBID / DB_UNIQUE_NAME:
Database role / open mode:
Version / RU:
PDB / CON_ID:
RAC instances / service:
Application / module:

Time standard:
Database host timezone:
Application timezone:
Known clock drift:

First known bad (UTC):
First customer impact (UTC):
Detection time (UTC):
Containment time (UTC):
Recovery time (UTC):

Symptoms:
Scope:
Affected users / tenants:
Affected objects / data range:
SQL_ID / child / plan hash:
Session / XID / SCN:

Recent changes:
1.
2.
3.

Verified facts:
1.
2.
3.

Hypotheses:
1.
Evidence supporting:
Evidence against:

Containment:
Remediation:
Validation:
Data integrity check:

Evidence register:
1.
2.
3.

Root cause:
Contributing factors:
Unknowns:
Follow-up actions / owners / due dates:
~~~

## 14. Các sai lầm thường gặp khi điều tra

| Sai lầm | Vì sao nguy hiểm | Cách làm tốt hơn |
|---|---|---|
| Dùng giờ laptop làm mốc chung | Host/session có thể khác timezone hoặc clock drift | Chuẩn hóa UTC và ghi nguồn đồng hồ |
| Chỉ dựa vào timestamp | Timestamp có thể thiếu độ chính xác hoặc log đến trễ | Kết hợp SCN, XID, SQL_ID và request ID |
| Coi LAST_DDL_TIME là audit trail | Không xác định actor và nội dung DDL đầy đủ | Kết hợp Unified Audit, deployment và source control |
| Coi ORA_ROWSCN là thời điểm chính xác từng row | Có thể ở mức block và không ghi actor/SQL | Dùng Flashback Version Query và audit |
| Coi V$SESSION là lịch sử | Session đã disconnect không còn trong view | Dùng ASH/audit/application logs nếu được phép |
| Coi V$SQL counters là số của lần chạy cuối | Counters tích lũy theo cursor | Lấy snapshot và tính delta |
| Coi không có audit record là không có thay đổi | Policy có thể chưa ghi hoặc record đã purge | Kiểm tra policy, retention và nguồn khác |
| Chỉ điều tra database | Sự cố có thể do app, network, DNS, storage hoặc certificate | Đối chiếu toàn bộ dependency |
| Restart trước khi thu thập | Mất session state và counters trong memory | Capture trước, containment theo runbook |
| Chạy sửa dữ liệu trước khi xác định phạm vi | Có thể ghi đè evidence hoặc làm mất dữ liệu hợp lệ | Dựng timeline và data range trước |
| Chạy UNDO_SQL ngay | SQL đảo ngược có thể không còn đúng với trạng thái hiện tại | Review transaction, dependency và test |
| Gửi trace/log nguyên bản ra ngoài | Có thể lộ dữ liệu và credential | Giữ bản gốc có kiểm soát, tạo bản redact |
| Gộp số liệu RAC/PDB | Có thể gán sai instance hoặc tenant | Giữ INST_ID, CON_ID và service |

## 15. Bài lab: dựng timeline từ DDL và dữ liệu

Lab minh họa cách lưu mốc thời gian/SCN, thay đổi một bảng, quan sát LAST_DDL_TIME và row versions. Chạy trong schema lab và database đã đáp ứng điều kiện Flashback Version Query.

### 15.1 Ghi mốc ban đầu

~~~sql
SELECT SYSTIMESTAMP AS captured_at,
       DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER AS captured_scn,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name,
       SYS_CONTEXT('USERENV', 'INSTANCE_NAME') AS instance_name
FROM dual;
~~~

Ghi kết quả ra file evidence cùng thời điểm lấy.

### 15.2 Tạo bảng và dữ liệu

~~~sql
CREATE TABLE incident_timeline_lab (
    id          NUMBER PRIMARY KEY,
    status      VARCHAR2(20),
    amount      NUMBER
);
~~~

Chờ ít nhất 15 giây sau khi tạo table trước transaction cần quan sát bằng Flashback Version Query.

~~~sql
INSERT INTO incident_timeline_lab VALUES (1, 'NEW', 100);
INSERT INTO incident_timeline_lab VALUES (2, 'NEW', 200);
COMMIT;
~~~

### 15.3 Ghi SCN trước và sau DML

~~~sql
SELECT SYSTIMESTAMP AS before_change_time,
       DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER AS before_change_scn
FROM dual;

UPDATE incident_timeline_lab
SET status = 'SHIPPED',
    amount = 125
WHERE id = 1;

COMMIT;

SELECT SYSTIMESTAMP AS after_change_time,
       DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER AS after_change_scn
FROM dual;
~~~

### 15.4 Xem lịch sử row version

~~~sql
SELECT versions_startscn,
       versions_endscn,
       versions_starttime,
       versions_endtime,
       versions_xid,
       versions_operation,
       id,
       status,
       amount
FROM incident_timeline_lab
VERSIONS BETWEEN SCN MINVALUE AND MAXVALUE
WHERE id = 1
ORDER BY versions_startscn;
~~~

Kết quả cho biết row versions còn khả dụng trong undo. Ghi lại XID, operation và SCN của version cần điều tra.

### 15.5 Xem object metadata

~~~sql
SELECT owner,
       object_name,
       object_type,
       created,
       last_ddl_time,
       status
FROM user_objects
WHERE object_name = 'INCIDENT_TIMELINE_LAB';
~~~

LAST_DDL_TIME minh họa thời điểm DDL gần nhất của object. DML UPDATE ở bước trước không làm LAST_DDL_TIME thành thời điểm UPDATE. Điều này cho thấy object metadata không phải lịch sử thay đổi dữ liệu.

### 15.6 Dọn lab

~~~sql
DROP TABLE incident_timeline_lab PURGE;
~~~

Chỉ chạy DROP nếu đây là bảng lab vừa tạo và không chứa dữ liệu cần giữ.

## 16. Checklist điều tra sự cố

### Thời gian

1. Đã ghi first known bad, detection và customer impact chưa?
2. Timestamp có timezone/UTC offset chưa?
3. Đã đối chiếu database host, application host và collector clock chưa?
4. Có clock drift hoặc log ingest delay không?
5. Đã ghi current SCN và startup time chưa?

### Phạm vi

1. Đã xác định DBID, DB_UNIQUE_NAME, role và open mode chưa?
2. Đã xác định PDB/CON_ID và RAC INST_ID chưa?
3. Đã xác định service, host, application version và module chưa?
4. Đã xác định schema, object, partition và data range chưa?
5. Đã xác định SQL_ID, child cursor, plan hash, session và XID chưa?
6. Đã định lượng user/tenant/request bị ảnh hưởng chưa?

### Thay đổi gần nhất

1. Đã lấy deployment và migration history chưa?
2. Đã kiểm tra DDL/audit trail chưa?
3. Đã xem parameter/SPFILE/service changes chưa?
4. Đã kiểm tra statistics và scheduler jobs chưa?
5. Đã kiểm tra grants, users, roles và credentials rotation chưa?
6. Đã đối chiếu OS, storage, DNS, firewall, listener và TLS changes chưa?

### Bằng chứng

1. Đã lưu alert log và trace chưa?
2. Đã chụp runtime sessions, waits, blockers và SQL cursor chưa?
3. Đã lấy snapshot counters ở hai thời điểm khi cần delta chưa?
4. Đã kiểm tra audit/FGA và nguồn lịch sử được cấp phép chưa?
5. Đã lưu query, output, row count, timezone và collection time chưa?
6. Đã tạo evidence register và SHA-256 chưa?
7. Đã redact dữ liệu nhạy cảm trên bản chia sẻ chưa?

### Kết luận và hành động

1. Fact, inference, hypothesis và unknown đã được tách riêng chưa?
2. Có bằng chứng độc lập ủng hộ root cause không?
3. Có bằng chứng phản bác giả thuyết không?
4. Đã bảo toàn evidence trước hành động phá hủy trạng thái chưa?
5. Đã phê duyệt containment/remediation chưa?
6. Đã xác nhận data integrity sau khắc phục chưa?
7. Đã lưu post-change evidence và follow-up owner chưa?

## 17. Tổng kết

Một quy trình điều tra Oracle hiệu quả bắt đầu bằng việc thống nhất thời gian và SCN, sau đó xác định phạm vi database/PDB/instance/service/application/object/data. Tiếp theo, đối chiếu deployment, DDL, parameters, statistics, jobs, security và thay đổi hạ tầng. Bằng chứng cần được thu thập từ runtime views, alert/trace, audit, Flashback, redo/archive, application và infrastructure logs.

- Timestamp phải kèm timezone; SCN giúp liên kết thứ tự thay đổi logic.
- Phạm vi phải giữ DBID, CON_ID, INST_ID, service, schema, object, SQL_ID và XID khi có.
- LAST_DDL_TIME, V$SESSION và V$SQL là nguồn chỉ báo hữu ích nhưng không phải lịch sử đầy đủ.
- Audit chỉ chứng minh những sự kiện đã được policy ghi nhận; thiếu record không chứng minh không có sự kiện.
- AWR/ASH có giá trị cho lịch sử hiệu năng nhưng cần xác minh licensing.
- Cumulative counters phải được so sánh bằng snapshot/delta trong cùng vòng đời.
- Evidence gốc cần được bảo toàn, lập register và kiểm tra integrity bằng hash.
- Root cause chỉ được xác nhận khi timeline và các nguồn độc lập hỗ trợ; phần chưa biết phải được ghi rõ.

Kết quả của điều tra không chỉ là một câu trả lời “vì sao database lỗi”, mà là một timeline có thể tái kiểm tra, phạm vi ảnh hưởng được định lượng, bằng chứng có nguồn gốc rõ ràng và kế hoạch khắc phục có thể kiểm chứng.

## 18. Tài liệu Oracle tham khảo

- Oracle Database 19c Database Reference, “V$DATABASE”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-DATABASE.html
- Oracle Database 19c Database Reference, “V$INSTANCE”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-INSTANCE.html
- Oracle Database 19c Database Reference, “V$SESSION”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SESSION.html
- Oracle Database 19c Database Reference, “V$DIAG_ALERT_EXT”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-DIAG_ALERT_EXT.html
- Oracle Database 19c Database Reference, “UNIFIED_AUDIT_TRAIL”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/UNIFIED_AUDIT_TRAIL.html
- Oracle Database 19c Database Reference, “SCN_TO_TIMESTAMP”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/SCN_TO_TIMESTAMP.html
- Oracle Database 19c Database Reference, “TIMESTAMP_TO_SCN”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/TIMESTAMP_TO_SCN.html
- Oracle Database 19c Database Reference, “V$UNDOSTAT”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-UNDOSTAT.html
- Oracle Database 19c Development Guide, “Using Oracle Flashback Technology”: https://docs.oracle.com/en/database/oracle/oracle-database/19/adfns/flashback.html
- Oracle Database 19c Administrator's Guide, “Managing Diagnostic Data”: https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-diagnostic-data.html
- Oracle Database 19c Database Reference, “V$ACTIVE_SESSION_HISTORY”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-ACTIVE_SESSION_HISTORY.html
- Oracle Database Licensing Information User Manual: https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/Licensing-Information.html
