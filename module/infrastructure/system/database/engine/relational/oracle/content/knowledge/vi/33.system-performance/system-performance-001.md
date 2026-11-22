# Đọc V$SESSION, V$SQL, V$SQLSTATS và các bộ đếm tích lũy trong Oracle Database

Khi database chậm, câu hỏi đầu tiên thường là: session nào đang hoạt động, session đó đang chạy câu SQL nào, câu SQL tiêu tốn bao nhiêu CPU/I/O, và mức sử dụng tài nguyên đã tăng bao nhiêu trong khoảng thời gian cần quan sát?

Oracle cung cấp các dynamic performance views để trả lời những câu hỏi này. Bốn view thường được dùng cùng nhau là:

- **V$SESSION:** trạng thái và hoạt động hiện tại của từng session, gồm SQL_ID, wait event, module/action và thông tin blocker.
- **V$SQL:** thống kê của từng child cursor trong shared SQL area, gồm số execution, CPU, elapsed time, logical reads, physical reads và plan hash.
- **V$SQLSTATS:** thống kê tổng quan theo SQL_ID, nhanh và có khả năng giữ số liệu lâu hơn V$SQL khi cursor bị aged out khỏi shared pool.
- **V$SESSTAT và V$SYSSTAT:** các bộ đếm thống kê tích lũy theo session và theo instance; cần kết hợp V$STATNAME để đọc tên statistic.

Ngoài ra, V$SESS_TIME_MODEL và V$SYS_TIME_MODEL cung cấp các bộ đếm thời gian như DB time và DB CPU theo microsecond.

Điểm quan trọng khi đọc các view này là phân biệt **ảnh chụp trạng thái hiện tại**, **số liệu tích lũy từ khi cursor/session/instance bắt đầu**, và **mức tăng trong một khoảng thời gian**. Một giá trị lớn không tự chứng minh hệ thống đang chậm ở thời điểm hiện tại. Muốn đo tốc độ tăng hoặc chi phí trung bình, cần lấy snapshot ở hai thời điểm và tính delta.

## 1. Dynamic performance views là gì?

Các view có tiền tố V$ hiển thị thông tin trạng thái và hiệu năng do Oracle duy trì trong bộ nhớ. Chúng thường được gọi là dynamic performance views hoặc fixed views.

Đặc điểm:

- Phản ánh trạng thái runtime của instance, session, cursor, wait và các thành phần khác.
- Nhiều bộ đếm là tích lũy, không phải giá trị của riêng giây hiện tại.
- Một số thông tin chỉ tồn tại khi session hoặc cursor còn trong bộ nhớ.
- Các view không phải kho lịch sử lâu dài. Muốn phân tích xu hướng dài hạn cần hệ thống snapshot/monitoring hoặc các nguồn lịch sử phù hợp.
- Truy vấn V$ view cũng tiêu tốn tài nguyên; không nên polling quá dày hoặc lấy toàn bộ cột không cần thiết.

### 1.1 V$ và GV$

Trong Oracle RAC:

- V$ thường hiển thị thông tin của instance hiện tại.
- GV$ hiển thị thông tin trên các instance và bổ sung cột INST_ID.

Ví dụ:

~~~sql
SELECT inst_id,
       sid,
       serial#,
       username,
       status
FROM gv$session
WHERE type = 'USER';
~~~

Khi dùng GV$, luôn giữ INST_ID trong khóa nhận diện session và khi join các view toàn cluster. SID có thể trùng giữa các instance.

### 1.2 CDB/PDB và CON_ID

Trong môi trường multitenant, nhiều dynamic performance views có cột CON_ID:

- 0: dữ liệu thuộc toàn CDB hoặc non-CDB.
- 1: dữ liệu thuộc CDB root.
- Giá trị khác: container tương ứng.

Khi tổng hợp số liệu, không gộp các dòng khác CON_ID nếu mục tiêu là phân tích riêng một PDB. Một số view còn có CON_DBID để định danh database của PDB.

### 1.3 Quyền truy cập

Để đọc các dynamic performance views, tài khoản cần quyền phù hợp, thường là SELECT_CATALOG_ROLE hoặc quyền SELECT trực tiếp trên các đối tượng SYS.V_$ tương ứng theo chính sách DBA. Không nên cấp quyền SYSDBA chỉ để chạy các truy vấn giám sát thông thường.

## 2. Bản đồ các view cần biết

| View | Phạm vi | Nội dung chính |
|---|---|---|
| V$SESSION | Session đang kết nối | Status, SQL hiện tại/trước đó, wait, blocker, module/action |
| V$SQL | Từng child cursor | SQL text, child number, plan hash, execution và resource counters |
| V$SQLSTATS | Một dòng cho mỗi SQL_ID | Thống kê SQL tổng quan, hiệu năng tốt và retention lớn hơn V$SQL |
| V$SESSTAT | Từng session | Các statistic tích lũy của session |
| V$SYSSTAT | Instance | Các statistic cấp hệ thống |
| V$STATNAME | Tên statistic | Ánh xạ STATISTIC# sang NAME |
| V$SESS_TIME_MODEL | Từng session | DB time, DB CPU và thời gian theo loại hoạt động |
| V$SYS_TIME_MODEL | Instance | DB time, DB CPU và thời gian tích lũy toàn instance |
| V$SESSION_EVENT | Từng session | Số wait và tổng thời gian wait theo event |
| V$SESSION_LONGOPS | Operation dài | Tiến độ một số operation kéo dài |
| V$SQL_MONITOR | Một lần thực thi được monitor | Runtime metrics của SQL execution; cần xét điều kiện và licensing |

Các view này trả lời câu hỏi ở những phạm vi khác nhau. Không nên cộng V$SESSION, V$SQL và V$SYSSTAT với nhau như thể chúng là ba nguồn độc lập; chúng mô tả các lớp khác nhau của cùng hoạt động database.

## 3. Đọc V$SESSION: ai đang làm gì?

V$SESSION có một dòng cho mỗi session hiện tại. Đây là điểm bắt đầu khi cần biết session nào đang chạy, đang chờ hoặc đang bị chặn.

### 3.1 Các cột quan trọng

| Cột | Ý nghĩa |
|---|---|
| SID | Session identifier trong instance |
| SERIAL# | Số serial để phân biệt một phiên đời session với session khác có thể dùng lại SID |
| USERNAME | Database username |
| STATUS | ACTIVE, INACTIVE, KILLED, SNIPED hoặc trạng thái liên quan |
| TYPE | USER hoặc BACKGROUND |
| MACHINE / PROGRAM / OSUSER | Thông tin client/process kết nối |
| SERVICE_NAME | Database service của session |
| SQL_ID | SQL statement hiện đang thực thi |
| SQL_CHILD_NUMBER | Child cursor của SQL hiện tại |
| PREV_SQL_ID | SQL statement thực thi trước đó |
| SQL_EXEC_START | Thời điểm bắt đầu execution hiện tại |
| SQL_EXEC_ID | Định danh execution, khi có |
| MODULE / ACTION | Tên module và action do ứng dụng đặt |
| CLIENT_IDENTIFIER | Định danh client/user do ứng dụng đặt |
| LAST_CALL_ET | Số giây session ở trạng thái ACTIVE hoặc INACTIVE hiện tại |
| EVENT / WAIT_CLASS | Wait event gần nhất hoặc hiện tại và nhóm wait |
| STATE | Trạng thái wait |
| BLOCKING_SESSION | SID của session đang chặn, nếu được xác định |
| FINAL_BLOCKING_SESSION | Session cuối cùng trong blocker chain, nếu xác định được |

### 3.2 ACTIVE không có nghĩa là đang dùng CPU

STATUS = ACTIVE nghĩa session đang thực hiện database call. Session có thể:

- Đang chạy trên CPU.
- Đang chờ đọc I/O.
- Đang chờ lock hoặc enqueue.
- Đang chờ network hoặc một tài nguyên khác.

Để hiểu trạng thái thực tế, phải xem EVENT, WAIT_CLASS, STATE và thời gian wait. ACTIVE chỉ cho biết session đang ở trong một call, không cho biết call đó đang tiêu thụ CPU hay đang chờ.

### 3.3 LAST_CALL_ET không phải tuổi của session

LAST_CALL_ET có đơn vị giây:

- Khi STATUS = ACTIVE: số giây kể từ khi session chuyển sang ACTIVE.
- Khi STATUS = INACTIVE: số giây kể từ khi session chuyển sang INACTIVE.

Không dùng LAST_CALL_ET để kết luận session đã tồn tại bao lâu. LOGON_TIME mới cho biết thời điểm session đăng nhập.

### 3.4 SQL_ID và PREV_SQL_ID

SQL_ID nhận diện statement hiện tại. Khi session không có SQL đang thực thi, SQL_ID có thể NULL hoặc không đại diện cho câu lệnh đang chạy; PREV_SQL_ID giúp xem câu SQL gần nhất trước đó.

Nếu session đang thực thi PL/SQL, SQL_ID có thể đại diện cho SQL đang chạy bên trong PL/SQL. Các cột PLSQL_ENTRY_OBJECT_ID, PLSQL_OBJECT_ID và PLSQL_SUBPROGRAM_ID giúp xác định PL/SQL stack liên quan.

### 3.5 Xem session ACTIVE và SQL hiện tại

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.status,
       s.machine,
       s.program,
       s.module,
       s.action,
       s.sql_id,
       s.sql_child_number AS child_number,
       s.sql_exec_start,
       s.last_call_et,
       s.event,
       s.wait_class,
       s.state,
       q.plan_hash_value,
       SUBSTR(q.sql_text, 1, 120) AS sql_text
FROM v$session s
LEFT JOIN v$sql q
  ON q.sql_id = s.sql_id
 AND q.child_number = s.sql_child_number
WHERE s.type = 'USER'
  AND s.status = 'ACTIVE'
ORDER BY s.last_call_et DESC;
~~~

Join V$SQL bằng cả SQL_ID và SQL_CHILD_NUMBER để lấy đúng child cursor. Chỉ join SQL_ID có thể tạo nhiều dòng nếu SQL có nhiều child cursors.

### 3.6 Xem cả SQL hiện tại và SQL trước đó

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.status,
       s.sql_id,
       s.sql_child_number,
       s.prev_sql_id,
       s.prev_child_number,
       s.last_call_et,
       s.module,
       s.action
FROM v$session s
WHERE s.type = 'USER'
ORDER BY s.logon_time;
~~~

Với session INACTIVE, PREV_SQL_ID thường hữu ích hơn SQL_ID để tìm câu SQL vừa chạy. Cần đối chiếu với trạng thái và thời điểm lấy mẫu.

### 3.7 Tìm session đang chờ và blocker

~~~sql
SELECT w.sid                  AS waiting_sid,
       w.serial#              AS waiting_serial,
       w.username             AS waiting_user,
       w.event,
       w.wait_class,
       w.state,
       w.wait_time_micro,
       w.blocking_session_status,
       w.blocking_instance,
       w.blocking_session,
       b.serial#              AS blocker_serial,
       b.username             AS blocker_user,
       b.status               AS blocker_status,
       b.sql_id               AS blocker_sql_id,
       b.event                AS blocker_event
FROM v$session w
LEFT JOIN v$session b
  ON b.sid = w.blocking_session
WHERE w.blocking_session_status = 'VALID'
ORDER BY w.wait_time_micro DESC;
~~~

BLOCKING_SESSION chỉ có ý nghĩa khi BLOCKING_SESSION_STATUS = VALID. Với RAC, dùng GV$SESSION và join theo cả BLOCKING_INSTANCE/INST_ID. Nếu có nhiều tầng blocker, FINAL_BLOCKING_SESSION giúp tìm session cuối cùng trong wait chain.

### 3.8 Diễn giải wait

Một số nhóm wait thường gặp:

| WAIT_CLASS | Ý nghĩa khái quát |
|---|---|
| User I/O | Chờ đọc/ghi dữ liệu cho user operation |
| Application | Thường liên quan đến lock do ứng dụng hoặc transaction |
| Concurrency | Chờ tài nguyên đồng thời như latch/mutex hoặc enqueue thuộc nhóm này |
| Cluster | Chờ tài nguyên liên instance trong RAC |
| Commit | Chờ hoàn tất commit, ví dụ log file sync |
| Network | Chờ hoạt động truyền nhận qua Oracle Net |
| Idle | Session đang nhàn rỗi, chờ client hoặc một sự kiện không đại diện cho công việc database |

WAIT_CLASS chỉ là nhóm. EVENT mới là tên wait cụ thể. Ví dụ Application có thể gồm enq: TX - row lock contention; Commit có thể gồm log file sync. Không kết luận nguyên nhân chỉ từ tên nhóm.

## 4. Đọc V$SQL: thống kê theo child cursor

V$SQL hiển thị thống kê của các SQL cursor trong shared SQL area. Mỗi dòng tương ứng với một child cursor của SQL text gốc.

Một SQL_ID có thể có nhiều child cursor vì khác bind metadata, optimizer environment, object resolution, authorization, adaptive cursor sharing hoặc các nguyên nhân không share cursor khác.

### 4.1 Các cột quan trọng

| Cột | Ý nghĩa |
|---|---|
| SQL_ID | Định danh parent SQL cursor |
| CHILD_NUMBER | Số thứ tự child cursor |
| PLAN_HASH_VALUE | Hash đại diện cho execution plan |
| SQL_TEXT | 1.000 ký tự đầu của SQL text |
| SQL_FULLTEXT | Toàn bộ SQL text dạng CLOB |
| EXECUTIONS | Số lần execution kể từ khi cursor được load vào library cache |
| END_OF_FETCH_COUNT | Số lần cursor được fetch hoàn tất |
| PARSE_CALLS | Số lần parse call |
| LOADS | Số lần cursor được load hoặc reload |
| INVALIDATIONS | Số lần child cursor bị invalidated |
| BUFFER_GETS | Số logical buffer gets |
| DISK_READS | Số disk reads được ghi nhận |
| ROWS_PROCESSED | Tổng số dòng được xử lý/trả về theo cursor |
| CPU_TIME | CPU time, microsecond |
| ELAPSED_TIME | Elapsed database time, microsecond |
| USER_IO_WAIT_TIME | Thời gian chờ User I/O, microsecond |
| APPLICATION_WAIT_TIME | Thời gian chờ Application, microsecond |
| CONCURRENCY_WAIT_TIME | Thời gian chờ Concurrency, microsecond |
| CLUSTER_WAIT_TIME | Thời gian chờ Cluster trong RAC, microsecond |
| MODULE / ACTION | Module/action lúc statement được parse |
| IS_BIND_SENSITIVE / IS_BIND_AWARE | Trạng thái adaptive cursor sharing |
| IS_REOPTIMIZABLE | Child cursor có thể kích hoạt reoptimization ở lần chạy sau hay không |

### 4.2 V$SQL là số liệu tích lũy của cursor

EXECUTIONS, CPU_TIME, ELAPSED_TIME, BUFFER_GETS và các bộ đếm khác không phải số liệu của một lần chạy đơn lẻ. Chúng tích lũy từ khi cursor được đưa vào library cache.

Vì vậy:

- Một SQL chạy 100.000 lần có thể có tổng elapsed time cao dù mỗi execution rất nhanh.
- Một SQL chỉ chạy một lần nhưng tốn 20 phút có thể có tổng elapsed thấp hơn một SQL chạy thường xuyên.
- Cursor bị aged out hoặc reload có thể làm vòng đời bộ đếm thay đổi.
- Cần dùng số trung bình hoặc delta nếu muốn so sánh chi phí trên mỗi execution hay trong một khoảng thời gian.

### 4.3 Khi nào số liệu được cập nhật?

Thống kê trong V$SQL thường được cập nhật khi query execution kết thúc. Với query chạy lâu, Oracle cập nhật số liệu định kỳ, khoảng mỗi 5 giây, để có thể quan sát tác động khi query vẫn đang chạy.

Không giả định mọi bộ đếm của một câu SQL đang chạy được cập nhật tức thời ở mỗi lần đọc view.

### 4.4 Xem tất cả child cursor của một SQL_ID

~~~sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       end_of_fetch_count,
       parse_calls,
       loads,
       invalidations,
       buffer_gets,
       disk_reads,
       rows_processed,
       ROUND(cpu_time / 1000000, 3) AS cpu_seconds,
       ROUND(elapsed_time / 1000000, 3) AS db_elapsed_seconds,
       ROUND(
           elapsed_time / NULLIF(executions, 0) / 1000,
           3
       ) AS avg_elapsed_ms,
       last_active_time,
       sql_text
FROM v$sql
WHERE sql_id = :p_sql_id
ORDER BY child_number;
~~~

Query này giúp thấy một SQL_ID có bao nhiêu child cursor, plan hash khác nhau ra sao và chi phí tích lũy của từng child.

### 4.5 Vì sao END_OF_FETCH_COUNT quan trọng?

EXECUTIONS đếm số lần cursor được thực thi. END_OF_FETCH_COUNT chỉ tăng khi cursor được fetch hoàn tất. Nếu ứng dụng chỉ fetch một phần kết quả rồi đóng cursor, execution vẫn được tính nhưng không được tính là fully fetched.

Do đó:

- END_OF_FETCH_COUNT nhỏ hơn EXECUTIONS có thể cho biết nhiều execution không fetch hết.
- Điều này không tự động là lỗi; ứng dụng có thể chủ ý chỉ lấy một phần kết quả.
- Khi đánh giá workload trả nhiều rows, cần xem cả EXECUTIONS, END_OF_FETCH_COUNT, FETCHES và ROWS_PROCESSED.

### 4.6 Parse calls không đồng nghĩa hard parses

PARSE_CALLS là số lần parse call, bao gồm các lần parse có thể được xử lý bằng soft parse. Không dùng PARSE_CALLS làm số hard parse.

Để theo dõi hard parse ở phạm vi session hoặc instance, xem statistic parse count (hard) trong V$SESSTAT/V$SYSSTAT. Có thể so với parse count (total) để hiểu tỷ lệ parse.

### 4.7 ELAPSED_TIME không phải lúc nào cũng là wall-clock time

CPU_TIME và ELAPSED_TIME trong V$SQL có đơn vị microsecond. ELAPSED_TIME là database time cho parsing, executing và fetching.

Với parallel execution, ELAPSED_TIME là tổng thời gian của query coordinator cộng các parallel query workers. Vì vậy giá trị có thể lớn hơn thời gian thực tế người dùng chờ trên đồng hồ. Không lấy ELAPSED_TIME của parallel SQL để suy ra trực tiếp wall-clock duration.

## 5. Đọc V$SQLSTATS: thống kê tổng quan theo SQL_ID

V$SQLSTATS cung cấp thống kê hiệu năng cơ bản của SQL cursor và có một dòng cho mỗi giá trị SQL_ID duy nhất.

So với V$SQL và V$SQLAREA:

- Nhanh và có khả năng mở rộng tốt hơn.
- Có nhiều thời gian lưu giữ hơn; thống kê có thể vẫn xuất hiện sau khi cursor đã aged out khỏi shared pool.
- Chỉ chứa một tập con các cột của V$SQL/V$SQLAREA.
- Phù hợp để tìm SQL tốn tài nguyên ở mức tổng quan.

Khi cần phân tích child cursor, bind sensitivity hoặc nhiều plan hash, chuyển sang V$SQL.

### 5.1 Các chỉ số thường dùng

| Cột | Cách đọc |
|---|---|
| SQL_ID | SQL statement |
| PLAN_HASH_VALUE | Plan hash hiện được đại diện trong thống kê |
| EXECUTIONS | Số lần thực thi tích lũy |
| PARSE_CALLS | Parse calls tích lũy |
| BUFFER_GETS | Logical reads tích lũy |
| DISK_READS | Disk reads tích lũy |
| ROWS_PROCESSED | Tổng rows processed |
| CPU_TIME | CPU microseconds |
| ELAPSED_TIME | Database elapsed microseconds |
| USER_IO_WAIT_TIME | User I/O wait microseconds |
| APPLICATION_WAIT_TIME | Application wait microseconds |
| CONCURRENCY_WAIT_TIME | Concurrency wait microseconds |
| CLUSTER_WAIT_TIME | Cluster wait microseconds |
| LAST_ACTIVE_TIME | Thời điểm gần nhất thống kê của cursor đóng góp được cập nhật |
| SQL_TEXT / SQL_FULLTEXT | SQL text |

### 5.2 Tìm SQL có tổng elapsed time cao

~~~sql
SELECT sql_id,
       plan_hash_value,
       executions,
       ROUND(elapsed_time / 1000000, 2) AS total_db_seconds,
       ROUND(cpu_time / 1000000, 2) AS total_cpu_seconds,
       ROUND(
           elapsed_time / NULLIF(executions, 0) / 1000,
           2
       ) AS avg_elapsed_ms,
       ROUND(
           buffer_gets / NULLIF(executions, 0),
           2
       ) AS avg_buffer_gets,
       disk_reads,
       rows_processed,
       parse_calls,
       last_active_time,
       SUBSTR(sql_text, 1, 120) AS sql_text
FROM v$sqlstats
WHERE executions > 0
ORDER BY elapsed_time DESC
FETCH FIRST 20 ROWS ONLY;
~~~

Đây là danh sách SQL có tổng database elapsed time cao trong số liệu còn được view giữ. Nó giúp tìm workload tiêu tốn tổng tài nguyên lớn, không nhất thiết là các execution chậm nhất.

### 5.3 Tìm SQL có CPU time cao

~~~sql
SELECT sql_id,
       executions,
       ROUND(cpu_time / 1000000, 2) AS cpu_seconds,
       ROUND(cpu_time / NULLIF(executions, 0) / 1000, 2)
           AS avg_cpu_ms,
       buffer_gets,
       rows_processed,
       last_active_time,
       SUBSTR(sql_text, 1, 120) AS sql_text
FROM v$sqlstats
WHERE executions > 0
ORDER BY cpu_time DESC
FETCH FIRST 20 ROWS ONLY;
~~~

CPU time cao gợi ý workload tiêu thụ nhiều CPU. Cần xem execution count, CPU per execution, số rows, plan và parallelism để hiểu nguyên nhân.

### 5.4 Tìm SQL có logical reads cao

~~~sql
SELECT sql_id,
       executions,
       buffer_gets,
       ROUND(buffer_gets / NULLIF(executions, 0), 2)
           AS avg_buffer_gets,
       disk_reads,
       rows_processed,
       SUBSTR(sql_text, 1, 120) AS sql_text
FROM v$sqlstats
WHERE executions > 0
ORDER BY buffer_gets DESC
FETCH FIRST 20 ROWS ONLY;
~~~

BUFFER_GETS là số lần truy cập logical buffer. Giá trị cao có thể do full scan, nested loops nhiều lần, index range scan rộng, hoặc một workload xử lý nhiều rows hợp lệ. Cần xem plan và số rows để phân biệt.

### 5.5 Các cột DELTA_* trong V$SQLSTATS

V$SQLSTATS có các cột như:

- DELTA_EXECUTION_COUNT
- DELTA_BUFFER_GETS
- DELTA_DISK_READS
- DELTA_CPU_TIME
- DELTA_ELAPSED_TIME
- DELTA_ROWS_PROCESSED
- DELTA_USER_IO_WAIT_TIME
- DELTA_PARSE_CALLS

Các cột DELTA_* thể hiện phần tăng kể từ AWR snapshot gần nhất. Chúng không mặc nhiên đại diện cho khoảng thời gian tùy ý mà người đọc vừa chọn. Nếu cần delta giữa hai thời điểm giám sát riêng, hãy tự lưu snapshot ở cả hai thời điểm.

## 6. So sánh V$SQL và V$SQLSTATS

| Tiêu chí | V$SQL | V$SQLSTATS |
|---|---|---|
| Số dòng | Một dòng cho mỗi child cursor | Một dòng cho mỗi SQL_ID duy nhất |
| Mức chi tiết | Child cursor và plan cụ thể | Tổng quan theo SQL_ID |
| Thông tin plan | CHILD_NUMBER, PLAN_HASH_VALUE và nhiều metadata | Có PLAN_HASH_VALUE, nhưng không thay thế chi tiết child cursor |
| Bind/adaptive cursor | Có IS_BIND_SENSITIVE, IS_BIND_AWARE và các cột reoptimization | Không đầy đủ như V$SQL |
| Số liệu | Tích lũy theo child cursor từ lúc load | Thống kê tổng hợp của SQL statement |
| Retention | Cursor có thể aged out khỏi shared pool | Thống kê có thể còn sau khi cursor aged out |
| Dùng khi | Phân tích plan/child cursor | Xếp hạng và tìm SQL tốn tài nguyên |

Một workflow hợp lý là dùng V$SQLSTATS để tìm SQL_ID đáng chú ý, sau đó dùng V$SQL để phân tích child cursor, plan hash, bind-sensitive state và chi tiết execution.

## 7. Bộ đếm tích lũy theo session: V$SESSTAT

V$SESSTAT hiển thị statistic theo từng session. Mỗi dòng có:

- SID: session identifier.
- STATISTIC#: số hiệu statistic.
- VALUE: giá trị statistic.
- CON_ID: container liên quan trong môi trường multitenant.

Để biết tên statistic, join với V$STATNAME:

~~~sql
SELECT s.sid,
       se.serial#,
       n.name,
       s.value
FROM v$sesstat s
JOIN v$statname n
  ON n.statistic# = s.statistic#
JOIN v$session se
  ON se.sid = s.sid
WHERE s.sid = :p_sid
  AND n.name IN (
      'session logical reads',
      'physical reads',
      'parse count (total)',
      'parse count (hard)',
      'execute count',
      'user commits',
      'redo size',
      'sorts (disk)',
      'sorts (memory)',
      'SQL*Net roundtrips to/from client'
  )
ORDER BY n.name;
~~~

### 7.1 Một số statistic thường dùng

| Statistic name | Ý nghĩa |
|---|---|
| session logical reads | Logical reads của session |
| physical reads | Physical read blocks được ghi nhận cho session |
| parse count (total) | Tổng parse calls |
| parse count (hard) | Hard parse calls |
| execute count | Số lần execute |
| user commits | Số commit do user session thực hiện |
| redo size | Số byte redo được tạo |
| sorts (memory) | Số sort hoàn tất trong memory |
| sorts (disk) | Số sort có sử dụng disk |
| SQL*Net roundtrips to/from client | Số lượt trao đổi Oracle Net với client |

VALUE không có một đơn vị chung cho mọi statistic. Ví dụ redo size là byte, một số time counters dùng centisecond hoặc microsecond tùy view/statistic, còn các counter khác là số lần hoặc số block. Luôn tra mô tả statistic tương ứng thay vì tự giả định đơn vị.

### 7.2 Vì sao phải ghép V$STATNAME?

STATISTIC# không được bảo đảm giữ nguyên giữa các release Oracle. Script giám sát nên dựa trên NAME thay vì hard-code số statistic.

V$STATNAME.NAME được Oracle mô tả là ổn định giữa các release; DISPLAY_NAME có thể thay đổi. Vì vậy nên dùng NAME làm khóa trong script.

### 7.3 Vòng đời của session statistics

V$SESSTAT chỉ phản ánh session đang tồn tại. Khi session disconnect:

- Statistic của session được cộng vào V$SYSSTAT.
- Giá trị của session được xóa cho đến khi session mới sử dụng slot tương ứng.

Nếu SID được dùng lại, không thể chỉ dựa vào SID để nhận diện cùng một session qua hai snapshot. Phải kiểm tra SERIAL# và, trong RAC, INST_ID.

## 8. Bộ đếm tích lũy toàn instance: V$SYSSTAT

V$SYSSTAT hiển thị system statistics của instance. Nó có STATISTIC#, NAME, CLASS, VALUE, STAT_ID và CON_ID.

Ví dụ:

~~~sql
SELECT name,
       value,
       class,
       con_id
FROM v$sysstat
WHERE name IN (
    'session logical reads',
    'physical reads',
    'redo size',
    'user commits',
    'execute count',
    'parse count (total)',
    'parse count (hard)',
    'user calls'
)
ORDER BY name;
~~~

V$SYSSTAT là phạm vi instance. Nó không đại diện riêng cho một user hoặc một SQL statement. Một số statistic bao gồm hoạt động của foreground sessions; một số statistic liên quan background process có semantics riêng. Hãy xem mô tả từng statistic.

### 8.1 Tại sao V$SYSSTAT hữu ích?

Nó giúp trả lời các câu hỏi cấp hệ thống:

- Logical reads có tăng nhanh không?
- Redo được tạo ra nhiều không?
- Hard parse có tăng bất thường không?
- Số execute và user calls tăng như thế nào?
- Sort disk có tăng theo workload không?

Đây là những bộ đếm tích lũy. Giá trị 1.000.000 chỉ có ý nghĩa khi biết nó tích lũy từ khi nào và tăng bao nhiêu trong khoảng cần phân tích.

### 8.2 V$SYSSTAT trong RAC

Trong RAC, dùng GV$SYSSTAT để lấy số liệu theo từng instance:

~~~sql
SELECT inst_id,
       name,
       value
FROM gv$sysstat
JOIN gv$statname
  USING (inst_id, statistic#)
WHERE name IN (
    'session logical reads',
    'physical reads',
    'redo size',
    'user commits'
)
ORDER BY inst_id, name;
~~~

Giữ INST_ID khi lấy snapshot. Không trừ giá trị của instance này cho giá trị instance khác.

## 9. Time model: DB time và DB CPU

V$SESSTAT/V$SYSSTAT có nhiều counter, nhưng khi cần thời gian tiêu tốn cho database calls, time model thường dễ diễn giải hơn.

- V$SESS_TIME_MODEL: thời gian tích lũy theo session.
- V$SYS_TIME_MODEL: thời gian tích lũy toàn instance.

Các giá trị time model được lưu theo microsecond.

### 9.1 DB time

DB time là tổng elapsed time spent performing database user-level calls. Nó bao gồm CPU time và non-idle wait time của user calls; không bao gồm thời gian của background processes như PMON trừ statistic dành riêng cho background.

DB time là tổng trên các user sessions. Vì nhiều session chạy đồng thời, DB time trong một phút có thể lớn hơn 60 giây.

### 9.2 DB CPU

DB CPU là CPU time tiêu thụ bởi database user-level calls. Nó không bao gồm CPU của background processes như PMON.

So sánh DB CPU với DB time:

- DB CPU gần DB time: workload có tỷ trọng CPU lớn.
- DB time cao hơn DB CPU đáng kể: có nhiều thời gian chờ non-idle waits.

Đây là chỉ báo tổng quan; cần xem wait class/event để biết chờ ở đâu.

### 9.3 Xem time model toàn instance

~~~sql
SELECT stat_name,
       value,
       ROUND(value / 1000000, 2) AS seconds
FROM v$sys_time_model
WHERE stat_name IN (
    'DB time',
    'DB CPU',
    'sql execute elapsed time',
    'parse time elapsed',
    'PL/SQL execution elapsed time'
)
ORDER BY stat_name;
~~~

### 9.4 Xem time model của một session

~~~sql
SELECT sid,
       stat_name,
       value,
       ROUND(value / 1000000, 3) AS seconds
FROM v$sess_time_model
WHERE sid = :p_sid
  AND stat_name IN (
      'DB time',
      'DB CPU',
      'sql execute elapsed time',
      'parse time elapsed',
      'PL/SQL execution elapsed time'
  )
ORDER BY stat_name;
~~~

### 9.5 Độ trễ cập nhật

Time model counters có thể được buffer trước khi hiển thị. Với timed operation kéo dài, view có thể thiếu tối đa khoảng 5 giây số liệu vừa phát sinh. Vì vậy không nên xem time model như đồng hồ realtime có độ chính xác tuyệt đối ở từng giây.

## 10. Cumulative counter, snapshot và delta

Đây là nguyên tắc quan trọng nhất khi đọc các bộ đếm tích lũy.

Giả sử một counter có:

| Thời điểm | BUFFER_GETS |
|---|---:|
| 10:00:00 | 1.000.000 |
| 10:05:00 | 1.250.000 |

Giá trị hiện tại là 1.250.000, nhưng số logical reads trong 5 phút vừa qua là:

\[
\Delta = 1.250.000 - 1.000.000 = 250.000
\]

Tốc độ tăng trung bình:

\[
\text{Rate} = \frac{\Delta}{\text{elapsed seconds}}
= \frac{250.000}{300}
\approx 833,33 \text{ gets/second}
\]

### 10.1 Công thức cơ bản

Với counter C:

\[
\Delta C = C_{after} - C_{before}
\]

\[
\text{Rate} = \frac{\Delta C}{t_{after}-t_{before}}
\]

Nếu có số execution:

\[
\text{Average per execution}
= \frac{\Delta C}{\Delta executions}
\]

### 10.2 Lấy hai snapshot V$SYSSTAT

Chạy truy vấn sau ở thời điểm T0 và lưu kết quả:

~~~sql
SELECT SYSTIMESTAMP AS sample_time,
       n.name,
       s.value
FROM v$sysstat s
JOIN v$statname n
  ON n.statistic# = s.statistic#
WHERE n.name IN (
    'session logical reads',
    'physical reads',
    'redo size',
    'user commits',
    'execute count',
    'parse count (hard)'
)
ORDER BY n.name;
~~~

Sau khoảng thời gian cần đo, chạy lại đúng truy vấn ở T1. Lấy VALUE tại T1 trừ VALUE tại T0 cho cùng statistic, cùng instance và cùng CON_ID.

### 10.3 Lấy hai snapshot V$SESSTAT

Với session cụ thể:

~~~sql
SELECT SYSTIMESTAMP AS sample_time,
       s.sid,
       se.serial#,
       n.name,
       s.value
FROM v$sesstat s
JOIN v$statname n
  ON n.statistic# = s.statistic#
JOIN v$session se
  ON se.sid = s.sid
WHERE s.sid = :p_sid
  AND n.name IN (
      'session logical reads',
      'physical reads',
      'execute count',
      'parse count (total)',
      'parse count (hard)',
      'redo size'
  )
ORDER BY n.name;
~~~

Khi trừ hai snapshot, phải chắc chắn SID và SERIAL# giống nhau. Nếu session disconnect hoặc SID được tái sử dụng, không tính delta giữa hai session khác nhau.

### 10.4 Những điều kiện để delta có ý nghĩa

- Hai snapshot cùng phạm vi: cùng SID/SERIAL#, cùng INST_ID, cùng CON_ID hoặc cùng SQL_ID/child cursor.
- Cùng statistic name.
- Cùng vòng đời instance/session/cursor.
- Thời gian giữa hai snapshot được ghi chính xác.
- Nếu counter giảm, phải điều tra reset/restart/reload hoặc thay đổi vòng đời trước khi diễn giải.

Không lấy giá trị cumulative từ hai instance khác nhau hoặc hai child cursor khác nhau để tính một delta.

## 11. Snapshot SQL statistics để đo một khoảng thời gian

V$SQLSTATS có các cột DELTA_* tính từ AWR snapshot gần nhất, nhưng nếu cần khoảng đo do ứng dụng tự chọn, có thể lưu snapshot của V$SQLSTATS vào một bảng giám sát.

### 11.1 Tạo bảng snapshot ví dụ

~~~sql
CREATE TABLE perf_sql_snapshot (
    sample_time     TIMESTAMP WITH TIME ZONE,
    inst_id         NUMBER,
    con_id          NUMBER,
    sql_id          VARCHAR2(13),
    plan_hash_value NUMBER,
    executions      NUMBER,
    buffer_gets     NUMBER,
    disk_reads      NUMBER,
    cpu_time        NUMBER,
    elapsed_time    NUMBER,
    rows_processed  NUMBER
);
~~~

Bảng này chỉ là ví dụ cho schema monitoring/lab. Trong hệ thống thật, cần đặt retention, quyền truy cập và dung lượng phù hợp.

### 11.2 Chụp snapshot lần đầu

~~~sql
INSERT INTO perf_sql_snapshot
SELECT SYSTIMESTAMP,
       inst_id,
       con_id,
       sql_id,
       plan_hash_value,
       executions,
       buffer_gets,
       disk_reads,
       cpu_time,
       elapsed_time,
       rows_processed
FROM gv$sqlstats
WHERE sql_id = :p_sql_id;

COMMIT;
~~~

Sau khoảng thời gian muốn đo, chạy lại INSERT tương tự. Hai dòng snapshot sẽ có thời điểm khác nhau.

### 11.3 Tính delta giữa hai snapshot liên tiếp

~~~sql
WITH samples AS (
    SELECT p.*,
           LAG(sample_time) OVER (
               PARTITION BY inst_id, con_id, sql_id, plan_hash_value
               ORDER BY sample_time
           ) AS previous_time,
           LAG(executions) OVER (
               PARTITION BY inst_id, con_id, sql_id, plan_hash_value
               ORDER BY sample_time
           ) AS previous_executions,
           LAG(buffer_gets) OVER (
               PARTITION BY inst_id, con_id, sql_id, plan_hash_value
               ORDER BY sample_time
           ) AS previous_buffer_gets,
           LAG(disk_reads) OVER (
               PARTITION BY inst_id, con_id, sql_id, plan_hash_value
               ORDER BY sample_time
           ) AS previous_disk_reads,
           LAG(cpu_time) OVER (
               PARTITION BY inst_id, con_id, sql_id, plan_hash_value
               ORDER BY sample_time
           ) AS previous_cpu_time,
           LAG(elapsed_time) OVER (
               PARTITION BY inst_id, con_id, sql_id, plan_hash_value
               ORDER BY sample_time
           ) AS previous_elapsed_time,
           LAG(rows_processed) OVER (
               PARTITION BY inst_id, con_id, sql_id, plan_hash_value
               ORDER BY sample_time
           ) AS previous_rows_processed
    FROM perf_sql_snapshot p
)
SELECT inst_id,
       con_id,
       sql_id,
       plan_hash_value,
       sample_time,
       executions - previous_executions AS delta_executions,
       buffer_gets - previous_buffer_gets AS delta_buffer_gets,
       disk_reads - previous_disk_reads AS delta_disk_reads,
       ROUND((cpu_time - previous_cpu_time) / 1000000, 3)
           AS delta_cpu_seconds,
       ROUND((elapsed_time - previous_elapsed_time) / 1000000, 3)
           AS delta_db_elapsed_seconds,
       rows_processed - previous_rows_processed AS delta_rows,
       ROUND(
           (buffer_gets - previous_buffer_gets)
           / NULLIF(executions - previous_executions, 0),
           2
       ) AS avg_buffer_gets_per_exec,
       ROUND(
           (elapsed_time - previous_elapsed_time)
           / NULLIF(executions - previous_executions, 0)
           / 1000,
           2
       ) AS avg_db_elapsed_ms_per_exec,
       ROUND(
           (CAST(sample_time AS DATE) - CAST(previous_time AS DATE))
           * 86400,
           2
       ) AS interval_seconds
FROM samples
WHERE previous_time IS NOT NULL
ORDER BY sample_time DESC;
~~~

Partition theo INST_ID, CON_ID, SQL_ID và PLAN_HASH_VALUE để không trộn số liệu của các instance, PDB hoặc plan khác nhau. Nếu SQL đổi plan, nó tạo một chuỗi snapshot riêng cho plan hash mới.

### 11.4 Giới hạn của snapshot SQL

- V$SQLSTATS là thống kê theo SQL_ID, không phải một dòng cho mỗi execution.
- Nếu cần phân tích child cursor cụ thể, snapshot V$SQL với khóa gồm INST_ID, CON_ID, SQL_ID và CHILD_NUMBER.
- Nếu cursor bị aged out/reload hoặc counter reset, delta có thể không còn liên tục.
- Khi plan hash thay đổi, không tính chênh lệch giữa hai plan như một chuỗi cùng plan.
- Elapsed time trong parallel execution là tổng database time của coordinator và workers, có thể lớn hơn wall-clock duration.

## 12. Đọc counter theo góc nhìn đúng

### 12.1 Tổng thời gian và trung bình mỗi execution

Tổng elapsed time giúp tìm SQL tiêu thụ nhiều tài nguyên trong toàn workload. Average elapsed time giúp tìm SQL chậm trên từng lần chạy.

Ví dụ:

| SQL | Executions | Total elapsed | Average |
|---|---:|---:|---:|
| A | 100.000 | 10.000 s | 100 ms |
| B | 10 | 2.000 s | 200 s |

SQL A chiếm tổng database time lớn hơn. SQL B có từng execution rất chậm hơn. Hai câu hỏi tối ưu khác nhau sẽ cho thứ tự ưu tiên khác nhau.

### 12.2 Logical reads và physical reads

- BUFFER_GETS: số lần Oracle truy cập logical buffers trong buffer cache.
- DISK_READS: số disk reads được ghi nhận.
- PHYSICAL_READ_REQUESTS: số request đọc vật lý; request có thể được phục vụ từ Database Smart Flash Cache và không nhất thiết là disk read.
- PHYSICAL_READ_BYTES: số byte được đọc từ disk.

Logical reads cao có thể gây CPU/buffer contention ngay cả khi physical reads thấp. Physical reads cao có thể phản ánh working set lớn hơn cache hoặc truy vấn cần đọc nhiều dữ liệu.

### 12.3 CPU time và elapsed time

CPU_TIME đo thời gian CPU. ELAPSED_TIME đo database elapsed time cho parse/execute/fetch, có thể gồm CPU và waits. Nếu elapsed lớn hơn CPU nhiều, xem wait-time columns và wait events.

### 12.4 Rows processed và fetch count

ROWS_PROCESSED là số rows xử lý/trả về tích lũy theo cursor. FETCHES là số lần fetch call, không phải số rows. END_OF_FETCH_COUNT đếm execution đã fetch hết kết quả.

Một ứng dụng fetch từng batch nhỏ có thể tạo nhiều fetch calls. Một ứng dụng chỉ lấy một phần kết quả có thể có EXECUTIONS tăng nhưng END_OF_FETCH_COUNT không tăng tương ứng.

### 12.5 Parse calls và executions

Nếu PARSE_CALLS gần bằng hoặc lớn hơn EXECUTIONS, có thể ứng dụng parse SQL thường xuyên. Nhưng parse_calls không đồng nghĩa hard parses. Hãy kiểm tra parse count (hard) ở session/system stats và xem cursor sharing.

### 12.6 Wait time categories

V$SQL có các bộ đếm Application, Concurrency, Cluster và User I/O wait time. Chúng được lưu theo microsecond và tích lũy trên cursor. Các giá trị này giúp phân biệt SQL tiêu tốn CPU với SQL tiêu tốn thời gian chờ.

Không cộng các wait categories một cách máy móc để suy ra elapsed time nếu không hiểu cách Oracle phân loại và các quan hệ giữa waits.

## 13. Định danh SQL và child cursor

### 13.1 SQL_ID

SQL_ID nhận diện parent cursor của SQL text trong library cache. Các câu SQL khác text thường có SQL_ID khác. SQL_ID không định danh một execution cụ thể.

### 13.2 CHILD_NUMBER

Một SQL_ID có thể có nhiều child cursor. Mỗi child có thể khác plan hoặc khác điều kiện share cursor. Khi đọc V$SQL, cần giữ CHILD_NUMBER và PLAN_HASH_VALUE.

### 13.3 PLAN_HASH_VALUE

PLAN_HASH_VALUE giúp so sánh nhanh plan của cursor. Cùng SQL_ID có thể xuất hiện nhiều plan hash qua child cursors hoặc theo thời gian. Khi plan hash đổi, cần xem execution plan để hiểu thay đổi thực sự.

### 13.4 SQL_EXEC_START và SQL_EXEC_ID

Trong V$SESSION, SQL_EXEC_START và SQL_EXEC_ID giúp nhận diện execution hiện tại. Đây là thông tin có ích khi cần đối chiếu một session đang chạy với V$SQL_MONITOR hoặc SQL plan monitor, nếu tính năng đó được sử dụng và có quyền phù hợp.

## 14. Module, action và client identifier

Ứng dụng có thể đặt tên hoạt động bằng DBMS_APPLICATION_INFO:

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'ORDER_API',
        action_name => 'CONFIRM_ORDER'
    );

    DBMS_APPLICATION_INFO.SET_CLIENT_INFO(
        client_info => 'batch-worker-03'
    );
END;
/
~~~

V$SESSION phản ánh module/action hiện tại của session. V$SQL lưu module/action của session tại thời điểm SQL statement được parse lần đầu cho cursor đó. Vì vậy module/action trong V$SQL không nhất thiết phản ánh action hiện tại nếu cursor được share giữa nhiều lần gọi.

CLIENT_IDENTIFIER có thể dùng để nhận diện user/request trong ứng dụng connection pool. Nên thiết lập và reset giá trị khi mượn/trả connection để tránh gắn nhầm request.

## 15. RAC: dùng GV$ và giữ INST_ID

Trong RAC, một SID chỉ có ý nghĩa trong một instance. Khi query nhiều instance:

~~~sql
SELECT s.inst_id,
       s.sid,
       s.serial#,
       s.username,
       s.status,
       s.sql_id,
       s.sql_child_number,
       s.event,
       s.wait_class,
       q.plan_hash_value,
       SUBSTR(q.sql_text, 1, 100) AS sql_text
FROM gv$session s
LEFT JOIN gv$sql q
  ON q.inst_id = s.inst_id
 AND q.sql_id = s.sql_id
 AND q.child_number = s.sql_child_number
WHERE s.type = 'USER'
  AND s.status = 'ACTIVE'
ORDER BY s.inst_id, s.last_call_et DESC;
~~~

Đối với blocker:

~~~sql
SELECT w.inst_id AS waiting_inst_id,
       w.sid AS waiting_sid,
       w.serial# AS waiting_serial,
       w.event,
       w.blocking_instance,
       w.blocking_session,
       b.serial# AS blocker_serial,
       b.username AS blocker_username,
       b.sql_id AS blocker_sql_id
FROM gv$session w
LEFT JOIN gv$session b
  ON b.inst_id = w.blocking_instance
 AND b.sid = w.blocking_session
WHERE w.blocking_session_status = 'VALID';
~~~

Không join GV$SESSION chỉ bằng SID; phải dùng cả INST_ID. Tương tự, khi tính delta GV$SYSSTAT hoặc GV$SQLSTATS, phải phân tách theo INST_ID.

## 16. Multitenant: giữ CON_ID khi tổng hợp

Nếu query từ CDB root, view có thể trả dữ liệu của nhiều container. Để thống kê riêng một PDB, lọc CON_ID hoặc truy vấn trong đúng container theo quyền và phạm vi mong muốn.

Ví dụ:

~~~sql
SELECT con_id,
       sql_id,
       executions,
       buffer_gets,
       cpu_time,
       elapsed_time,
       SUBSTR(sql_text, 1, 100) AS sql_text
FROM v$sqlstats
WHERE con_id = :p_con_id
ORDER BY elapsed_time DESC
FETCH FIRST 20 ROWS ONLY;
~~~

Không gộp các SQL_ID cùng text từ các PDB nếu mục tiêu là đo riêng từng tenant. Giữ CON_ID và, nếu cần, CON_DBID trong bảng snapshot.

## 17. Kết hợp V$SESSION, V$SQL và V$SQLSTATS trong quy trình chẩn đoán

Một quy trình thường dùng:

1. Dùng V$SESSION để xác định session đang ACTIVE, chờ event nào, có blocker không và SQL_ID hiện tại là gì.
2. Join SQL_ID + SQL_CHILD_NUMBER sang V$SQL để xem child cursor, plan hash và thống kê execution.
3. Dùng V$SQLSTATS để xếp hạng SQL theo tổng elapsed, CPU, buffer gets hoặc average per execution.
4. Dùng V$SESSTAT/V$SESS_TIME_MODEL để hiểu mức sử dụng tài nguyên của một session trong khoảng thời gian.
5. Dùng V$SYSSTAT/V$SYS_TIME_MODEL để hiểu toàn instance đang tăng bộ đếm như thế nào.
6. Lấy snapshot hai thời điểm, tính delta/rate và so sánh cùng điều kiện workload.
7. Nếu tìm được SQL đáng chú ý, dùng DBMS_XPLAN.DISPLAY_CURSOR để đọc plan và runtime row-source statistics.

### 17.1 Ví dụ: một session đang chậm

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.sql_id,
       s.sql_child_number,
       s.sql_exec_start,
       s.last_call_et,
       s.event,
       s.wait_class,
       s.state,
       s.blocking_session_status,
       s.blocking_session,
       q.plan_hash_value,
       q.executions,
       q.buffer_gets,
       q.disk_reads,
       ROUND(q.cpu_time / 1000000, 2) AS cpu_seconds,
       ROUND(q.elapsed_time / 1000000, 2) AS elapsed_db_seconds,
       q.sql_text
FROM v$session s
LEFT JOIN v$sql q
  ON q.sql_id = s.sql_id
 AND q.child_number = s.sql_child_number
WHERE s.sid = :p_sid;
~~~

Trước tiên đọc wait event và blocker. Sau đó xem cursor và plan. Nếu session đang chạy PL/SQL, SQL_ID có thể là câu SQL bên trong PL/SQL; hãy xem thêm PLSQL_ENTRY_OBJECT_ID và MODULE/ACTION.

### 17.2 Ví dụ: tìm SQL có chi phí tích lũy cao

~~~sql
SELECT sql_id,
       executions,
       ROUND(elapsed_time / 1000000, 2) AS db_seconds,
       ROUND(cpu_time / 1000000, 2) AS cpu_seconds,
       ROUND(buffer_gets / NULLIF(executions, 0), 2)
           AS avg_gets_per_exec,
       ROUND(elapsed_time / NULLIF(executions, 0) / 1000, 2)
           AS avg_db_ms,
       plan_hash_value,
       last_active_time,
       SUBSTR(sql_text, 1, 120) AS sql_text
FROM v$sqlstats
WHERE executions > 0
ORDER BY elapsed_time DESC
FETCH FIRST 30 ROWS ONLY;
~~~

Chọn SQL_ID cần điều tra, rồi xem tất cả child cursors bằng V$SQL.

### 17.3 Ví dụ: so sánh session trước và sau một workload

Trước workload, lưu các giá trị trong V$SESSTAT và V$SESS_TIME_MODEL cho SID/SERIAL# mục tiêu. Chạy workload, sau đó đọc lại cùng các statistic.

Ví dụ lấy time model:

~~~sql
SELECT stat_name,
       value / 1000000 AS seconds
FROM v$sess_time_model
WHERE sid = :p_sid
  AND stat_name IN ('DB time', 'DB CPU');
~~~

Lấy hai lần và tính delta cho DB time/DB CPU. Nếu delta DB time lớn hơn DB CPU nhiều, xem V$SESSION_EVENT hoặc V$SESSION để tìm wait classes/events liên quan.

## 18. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
|---|---|
| STATUS = ACTIVE nghĩa là đang dùng CPU | Session ACTIVE có thể đang chờ wait event |
| LAST_CALL_ET là tuổi session | Nó là thời gian ở trạng thái ACTIVE/INACTIVE hiện tại |
| SQL_ID định danh một execution | SQL_ID định danh SQL statement; execution còn có SQL_EXEC_START/SQL_EXEC_ID |
| V$SQL có một dòng cho mỗi SQL_ID | V$SQL có một dòng cho mỗi child cursor |
| V$SQLSTATS có một dòng cho mỗi child cursor | V$SQLSTATS có một dòng cho mỗi SQL_ID duy nhất |
| ELAPSED_TIME là wall-clock duration | Với parallel SQL, đây là tổng DB time của coordinator và workers |
| PARSE_CALLS là hard parses | Parse calls gồm soft parse; xem parse count (hard) riêng |
| END_OF_FETCH_COUNT bằng EXECUTIONS | Execution không fetch hết có thể không tăng END_OF_FETCH_COUNT |
| BUFFER_GETS là physical reads | BUFFER_GETS là logical buffer gets |
| DISK_READS giống PHYSICAL_READ_REQUESTS | Request đọc vật lý có thể được phục vụ từ flash cache; các cột đo khác nhau |
| V$SQLSTATS là lịch sử vĩnh viễn | Retention tốt hơn V$SQL nhưng vẫn là dynamic performance data, không thay thế kho lịch sử |
| Giá trị VALUE trong V$SESSTAT luôn cùng đơn vị | Đơn vị phụ thuộc từng statistic |
| STATISTIC# ổn định qua các release | Dùng NAME từ V$STATNAME thay cho hard-code statistic number |
| Có thể trừ mọi snapshot | Chỉ trừ khi cùng instance/session/cursor và cùng vòng đời counter |
| SID đủ nhận diện session trong RAC | Phải giữ INST_ID; cũng cần SERIAL# để phân biệt session reuse |

## 19. Lỗi thường gặp khi viết truy vấn giám sát

| Vấn đề | Nguyên nhân | Cách xử lý |
|---|---|---|
| Một session xuất hiện nhiều dòng khi join V$SQL | Chỉ join bằng SQL_ID, không join child number | Join SQL_ID + SQL_CHILD_NUMBER |
| Blocker không tìm thấy | BLOCKING_SESSION_STATUS không phải VALID hoặc blocker đã kết thúc | Kiểm tra status và lấy snapshot lại |
| Delta âm | Instance restart, session reuse, cursor reload hoặc counter reset | Kiểm tra STARTUP_TIME, SID/SERIAL#, child cursor và plan |
| Tổng elapsed lớn hơn thời gian đồng hồ | Parallel execution cộng DB time của workers | Phân biệt database time với wall-clock |
| SQL có nhiều executions nhưng END_OF_FETCH_COUNT thấp | Ứng dụng fetch một phần hoặc lỗi trước khi fetch hết | Xem cách client fetch và ROWS_PROCESSED |
| V$SQL không còn SQL_ID | Cursor đã aged out khỏi shared pool | Thử V$SQLSTATS; dùng nguồn lịch sử nếu đã được cấu hình |
| Top SQL thay đổi giữa hai lần đọc | Counters tích lũy tiếp tục tăng hoặc cursor mới xuất hiện | Lấy snapshot và tính delta trong cùng khoảng |
| Cộng GV$ thành một tổng không đúng | Gộp instance hoặc container | Giữ INST_ID và CON_ID |
| Wait time không khớp elapsed time | Wait categories có semantics riêng và không bao phủ mọi thời gian | Đọc wait event/time model và tránh cộng máy móc |
| Truy vấn monitor gây overhead | Polling dày, quét toàn bộ V$ view | Chỉ chọn cột, lọc SQL_ID/SID và giảm tần suất |

## 20. Lưu ý về dữ liệu lịch sử và licensing

V$SESSION, V$SQL, V$SQLSTATS, V$SESSTAT và V$SYSSTAT chủ yếu phục vụ quan sát runtime. Nếu cần phân tích lịch sử qua nhiều giờ/ngày, cần một cơ chế lưu snapshot hoặc repository phù hợp.

Các nguồn thường gặp:

- Bảng monitoring do ứng dụng/DBA tự tạo để lưu snapshot định kỳ.
- Automatic Workload Repository (AWR) và DBA_HIST_SQLSTAT cho lịch sử SQL statistics.
- Active Session History (ASH) để phân tích lịch sử hoạt động/waits theo mẫu.
- SQL Monitor và DBMS_SQL_MONITOR cho một số execution dài hoặc parallel.

Một số tính năng lịch sử và monitoring thuộc Oracle Diagnostics Pack hoặc Tuning Pack. Trước khi dùng AWR, ASH, SQL Monitor hoặc các báo cáo liên quan trong production, kiểm tra quyền sử dụng và licensing của môi trường. Không giả định một view có thể truy vấn được đồng nghĩa tổ chức được quyền sử dụng mọi tính năng liên quan.

## 21. Checklist khi đọc các view hiệu năng

Trước khi kết luận một SQL hoặc session đang có vấn đề, hãy xác định:

1. Phạm vi đang quan sát là session, child cursor, SQL_ID hay toàn instance?
2. Nếu là RAC, đã giữ INST_ID chưa?
3. Nếu là CDB, đã lọc hoặc phân tách CON_ID chưa?
4. Session có STATUS ACTIVE không, và đang CPU hay chờ event?
5. SQL_ID và SQL_CHILD_NUMBER có được join chính xác sang V$SQL không?
6. Có nhiều child cursors hoặc plan hash khác nhau không?
7. EXECUTIONS và END_OF_FETCH_COUNT có khác nhau đáng kể không?
8. PARSE_CALLS có bị nhầm với hard parse không?
9. CPU_TIME và ELAPSED_TIME đã đổi từ microsecond đúng cách chưa?
10. Parallel execution có làm elapsed database time lớn hơn wall-clock không?
11. BUFFER_GETS có bị nhầm thành physical reads không?
12. Counter đang là cumulative hay delta?
13. Hai snapshot có cùng session/cursor/instance/container không?
14. Có instance restart, session reuse hoặc cursor reload giữa hai snapshot không?
15. Đã tính average per execution và rate per second khi cần chưa?
16. Có dùng V$SQLSTATS để overview và V$SQL để phân tích child cursor không?
17. Đã xem wait class/event và blocker chain chưa?
18. Đã kiểm tra nguồn lịch sử/licensing nếu cần phân tích dài hạn chưa?

## 22. Tổng kết

Để đọc hiệu năng Oracle đúng cách:

- **V$SESSION** cho biết session nào đang hoạt động, SQL hiện tại, wait event, module/action và blocker. ACTIVE không đồng nghĩa với đang dùng CPU.
- **V$SQL** cung cấp thống kê từng child cursor, hữu ích khi cần so sánh child number, plan hash, bind sensitivity và counters.
- **V$SQLSTATS** cung cấp một dòng theo SQL_ID, nhanh hơn và có retention tốt hơn V$SQL; phù hợp để tìm SQL tiêu tốn tổng tài nguyên.
- **V$SESSTAT** và **V$SYSSTAT** là bộ đếm theo session và instance. Join V$STATNAME bằng NAME thay vì hard-code STATISTIC#.
- **V$SESS_TIME_MODEL** và **V$SYS_TIME_MODEL** giúp phân tích DB time và DB CPU theo microsecond.
- Các counters như executions, buffer gets, CPU time và elapsed time thường tích lũy theo vòng đời session/cursor/instance. Muốn đo một khoảng thời gian, lấy hai snapshot và tính delta.
- Khi tính delta, giữ đúng INST_ID, CON_ID, SID/SERIAL#, SQL_ID/CHILD_NUMBER và plan hash; kiểm tra reset/reload trước khi diễn giải.
- Luôn phân biệt tổng tài nguyên tích lũy, chi phí trung bình mỗi execution, tốc độ tăng theo giây và thời gian thực tế người dùng chờ.

Một quy trình chẩn đoán tốt bắt đầu từ V$SESSION để xác định hoạt động hiện tại, dùng V$SQL/V$SQLSTATS để tìm SQL tiêu tốn tài nguyên, rồi dùng các bộ đếm tích lũy và snapshot delta để xác định vấn đề có đang tăng lên trong khoảng thời gian cần quan sát hay không.

## 23. Tài liệu Oracle tham khảo

- Oracle Database 19c Database Reference, “V$SESSION”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SESSION.html
- Oracle Database 19c Database Reference, “V$SQL”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQL.html
- Oracle Database 19c Database Reference, “V$SQLSTATS”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQLSTATS.html
- Oracle Database 19c Database Reference, “V$SESSTAT”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SESSTAT.html
- Oracle Database 19c Database Reference, “V$SYSSTAT”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SYSSTAT.html
- Oracle Database 19c Database Reference, “V$STATNAME”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-STATNAME.html
- Oracle Database 19c Database Reference, “V$SESS_TIME_MODEL”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SESS_TIME_MODEL.html
- Oracle Database 19c Database Reference, “V$SYS_TIME_MODEL”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SYS_TIME_MODEL.html
- Oracle Database 19c Database Reference, “Displaying Statistics”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/displaying-statistics.html
- Oracle Database 19c Database Reference, “Statistics Descriptions”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/statistics-descriptions-2.html
- Oracle Database 19c SQL Tuning Guide, “Monitoring Database Operations”: https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/monitoring-database-operations.html
