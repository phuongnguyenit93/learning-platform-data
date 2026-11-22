# Chẩn đoán bằng dynamic view, trace hoặc Statspack trong phạm vi được phép

Khi Oracle Database chậm, cần xác định vấn đề nằm ở session nào, câu SQL nào, loại chờ nào và khoảng thời gian nào. Oracle cung cấp nhiều nguồn chẩn đoán: dynamic performance views (V$ và GV$), SQL Trace/TKPROF và Statspack. Mỗi công cụ trả lời một nhóm câu hỏi khác nhau.

- **Dynamic views** cho biết trạng thái hiện tại hoặc các bộ đếm tích lũy trong instance/session.
- **SQL Trace** ghi lại hoạt động parse, execute, fetch và wait của workload được chọn; TKPROF giúp đọc trace.
- **Statspack** lưu snapshot thống kê để so sánh tải giữa hai thời điểm.

Chẩn đoán đúng cần giới hạn phạm vi theo quyền được cấp, thu thập trong khoảng thời gian đại diện và bảo vệ dữ liệu nhạy cảm. Không phải mọi view hoặc tính năng chẩn đoán Oracle đều được phép dùng trong mọi hợp đồng license. Đặc biệt, AWR, ASH và ADDM thuộc phạm vi Oracle Diagnostics Pack; SQL Tuning Advisor và Real-Time SQL Monitoring thuộc phạm vi Oracle Tuning Pack theo điều khoản sản phẩm tương ứng. Cần xác nhận quyền sử dụng theo hợp đồng và tài liệu licensing của phiên bản đang triển khai trước khi truy cập hoặc chạy các tính năng đó.

## 1. Bắt đầu từ câu hỏi chẩn đoán

Không nên mở hàng loạt view rồi đọc mọi con số. Hãy xác định triệu chứng và câu hỏi cần trả lời:

| Triệu chứng | Câu hỏi đầu tiên |
|---|---|
| Một request chậm | Session nào thực thi request? SQL_ID là gì? |
| Nhiều request chậm cùng lúc | Có bottleneck CPU, I/O, lock, network hay resource manager? |
| Một SQL chậm bất thường | Execution plan và bind value nào đang chạy? |
| Transaction bị treo | Session nào đang block? Có transaction nào giữ lock lâu? |
| Chậm vào một khung giờ | Tải và wait profile trong khung giờ đó khác bình thường ra sao? |
| TEMP tăng mạnh | SQL nào dùng sort/hash workarea lớn? |
| CPU cao | Session/SQL nào tiêu thụ CPU và trong khoảng thời gian nào? |
| Database vừa thay đổi plan | Có stats refresh, deploy, bind khác hoặc child cursor mới không? |

Một quy trình chẩn đoán thực tế:

1. Ghi nhận thời điểm, service, module/action và phạm vi ảnh hưởng.
2. Xác định session và SQL đang hoạt động bằng dynamic views.
3. Kiểm tra wait, blocking và resource counters.
4. Lấy execution plan và runtime statistics nếu quyền cho phép.
5. Nếu cần chi tiết theo từng call, bật SQL Trace có phạm vi và thời hạn rõ.
6. Nếu cần so sánh tải theo khoảng thời gian, dùng Statspack hoặc công cụ được cấp phép.
7. Đối chiếu kết quả với thay đổi ứng dụng, dữ liệu và cấu hình.

## 2. Dynamic performance views là gì?

Oracle cung cấp các dynamic performance views để xem thông tin hoạt động của instance, session, SQL, lock, memory và nhiều thành phần khác. Tên view thường bắt đầu bằng V$.

Ví dụ:

- V$SESSION: session đang kết nối.
- V$SQL: cursor SQL trong shared pool.
- V$SQLSTATS: thống kê tổng hợp theo SQL.
- V$SESSION_WAIT: thông tin wait của session trong các phiên bản có view này; nhiều trường wait hiện có trong V$SESSION.
- V$SYSTEM_EVENT: tổng hợp thời gian chờ theo event.
- V$SYSSTAT: system statistics tích lũy.
- V$SESSTAT: session statistics.
- V$LOCK: thông tin lock.
- V$TRANSACTION: transaction đang hoạt động.
- V$TEMPSEG_USAGE: sử dụng temporary segment.
- V$PGASTAT: thống kê PGA.
- V$SQL_WORKAREA_ACTIVE: workarea đang hoạt động.
- V$DIAG_INFO: đường dẫn/thông tin diagnostic repository.

Các view này phản ánh cấu trúc bộ nhớ và hoạt động runtime. Chúng không giống bảng nghiệp vụ thông thường và không nên được cập nhật trực tiếp.

### 2.1 V$ và GV$

Trong môi trường một instance, V$ thường là điểm bắt đầu để xem trạng thái instance hiện tại.

Trong Oracle RAC:

- V$ thường hiển thị thông tin của instance mà session đang kết nối.
- GV$ cung cấp dữ liệu global từ các instance, thường có thêm cột INST_ID.

Ví dụ:

~~~sql
SELECT inst_id,
       sid,
       serial#,
       username,
       status,
       sql_id
FROM gv$session
WHERE username IS NOT NULL
ORDER BY inst_id, sid;
~~~

Trong RAC, nên giữ INST_ID khi đối chiếu session, SQL, wait và lock để tránh nhầm SID giữa các instance.

### 2.2 Dynamic view không phải snapshot lịch sử

V$SESSION là trạng thái gần hiện tại. Một session có thể kết thúc trước khi bạn chạy câu query kế tiếp.

V$SYSSTAT và V$SYSTEM_EVENT thường chứa bộ đếm tích lũy kể từ khi instance khởi động hoặc từ mốc reset tương ứng. Một con số lớn không cho biết nó tăng nhanh đến mức nào trong 5 phút vừa qua.

Muốn phân tích một khoảng thời gian, cần:

- Lấy hai lần đọc ở hai thời điểm.
- Tính delta của bộ đếm.
- Ghi nhận startup time và instance.
- So sánh cùng khoảng thời gian và cùng workload.

## 3. Quyền truy cập và nguyên tắc least privilege

Dynamic performance views thường được truy cập qua các synonym V$ trỏ tới fixed view nội bộ, ví dụ V$SESSION tương ứng với V_$SESSION.

Một tài khoản ứng dụng thông thường có thể không được quyền SELECT các view này. DBA có thể cấp quyền đọc tối thiểu cho một số view cần thiết:

~~~sql
GRANT SELECT ON SYS.V_$SESSION TO diag_reader;
GRANT SELECT ON SYS.V_$SQL TO diag_reader;
GRANT SELECT ON SYS.V_$SQL_PLAN TO diag_reader;
GRANT SELECT ON SYS.V_$SYSTEM_EVENT TO diag_reader;
GRANT SELECT ON SYS.V_$SYSSTAT TO diag_reader;
~~~

Tên object và quyền cần cấp phải được DBA xác nhận trong môi trường thực tế. Ví dụ trên chỉ minh họa mô hình quyền đọc có giới hạn.

### 3.1 Không cấp quyền quá rộng chỉ để chẩn đoán

Không mặc định cấp:

- DBA.
- SYSDBA.
- SELECT ANY DICTIONARY.
- Quyền truy cập toàn bộ dữ liệu diagnostic cho ứng dụng.

Thay vào đó, tạo role riêng như DIAG_READER, chỉ cấp các view cần thiết, giới hạn người dùng và theo dõi việc sử dụng.

SELECT_CATALOG_ROLE có thể giúp đọc nhiều dictionary/performance view, nhưng thường rộng hơn nhu cầu của một ứng dụng. Nên đánh giá quyền trực tiếp trên từng object và chính sách bảo mật nội bộ.

### 3.2 Quyền package và trace

Việc bật trace cho session hiện tại, session khác hoặc service/module có thể yêu cầu quyền package khác nhau. DBA nên thực hiện hoặc cấp quyền package phù hợp theo phạm vi:

- Session hiện tại: package DBMS_SESSION trong session được phép.
- Session khác: DBMS_MONITOR và thông tin SID/SERIAL# chính xác.
- Service/module/action/client identifier: DBMS_MONITOR với bộ lọc phù hợp.

Không cấp quyền bật trace toàn hệ thống cho người dùng ứng dụng nếu không cần thiết.

## 4. Xác định session đang hoạt động bằng V$SESSION

V$SESSION là điểm bắt đầu hữu ích để xem ai đang kết nối và đang thực thi SQL nào.

~~~sql
SELECT sid,
       serial#,
       username,
       status,
       osuser,
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
       state,
       seconds_in_wait,
       blocking_session,
       final_blocking_session
FROM v$session
WHERE username IS NOT NULL
ORDER BY status, sid;
~~~

Các cột quan trọng:

- SID và SERIAL#: định danh session trong instance; dùng cả hai khi thao tác session.
- USERNAME: database user.
- STATUS: ACTIVE hoặc INACTIVE cùng trạng thái session.
- MACHINE/PROGRAM: client/máy/chương trình kết nối.
- MODULE/ACTION: nhãn ứng dụng nếu được thiết lập bằng DBMS_APPLICATION_INFO.
- CLIENT_IDENTIFIER: định danh request/người dùng do ứng dụng đặt.
- SQL_ID: câu SQL hiện tại.
- PREV_SQL_ID: câu SQL trước đó trong một số trạng thái.
- EVENT/WAIT_CLASS/STATE: wait hiện tại hoặc trạng thái gần nhất.
- BLOCKING_SESSION: session đang block trực tiếp nếu được xác định.
- FINAL_BLOCKING_SESSION: blocker cuối cùng trong chuỗi nếu được xác định.

### 4.1 ACTIVE không có nghĩa đang dùng CPU

Một session có STATUS = 'ACTIVE' có thể:

- Đang dùng CPU.
- Đang chờ I/O.
- Đang chờ lock.
- Đang chờ network hoặc tài nguyên khác.

Hãy đọc STATE, EVENT và WAIT_CLASS cùng STATUS. Session ACTIVE không tự động là session gây tải CPU cao.

### 4.2 Idle session và idle wait

Session INACTIVE thường không thực thi SQL. Một số wait như SQL*Net message from client thuộc idle wait: database đang chờ client gửi lệnh tiếp theo.

Không kết luận database có bottleneck chỉ vì một event có số lần chờ lớn. Cần phân biệt idle wait với wait ảnh hưởng thời gian thực thi.

### 4.3 Gắn MODULE/ACTION ở ứng dụng

Ứng dụng có thể đặt nhãn để DBA lọc workload:

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'ORDER_SERVICE',
        action_name => 'CREATE_ORDER'
    );
END;
/
~~~

Đổi action giữa các giai đoạn:

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_ACTION('VALIDATE');
    -- Validate request.

    DBMS_APPLICATION_INFO.SET_ACTION('INSERT_HEADER');
    -- Insert order header.

    DBMS_APPLICATION_INFO.SET_ACTION('INSERT_ITEMS');
    -- Insert order items.
END;
/
~~~

Khi request kết thúc hoặc connection được trả về pool, ứng dụng nên reset module/action/client identifier theo convention đã thống nhất. Nếu không, session tái sử dụng có thể giữ nhãn của request trước.

### 4.4 CLIENT_IDENTIFIER

DBMS_SESSION.SET_IDENTIFIER có thể gắn định danh client:

~~~sql
BEGIN
    DBMS_SESSION.SET_IDENTIFIER('request-7f3a2');
END;
/
~~~

Chỉ dùng mã request hoặc định danh nội bộ không nhạy cảm. Không đưa mật khẩu, token, số thẻ hoặc dữ liệu cá nhân vào MODULE, ACTION hay CLIENT_IDENTIFIER vì các giá trị này có thể xuất hiện trong diagnostic view và trace.

## 5. Xác định SQL đang chạy bằng V$SQL

V$SQL chứa thông tin cursor SQL trong shared pool. Một SQL text có thể có nhiều child cursor, mỗi child có plan hoặc optimizer environment khác nhau.

~~~sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       parse_calls,
       rows_processed,
       elapsed_time,
       cpu_time,
       buffer_gets,
       disk_reads,
       last_active_time,
       is_bind_sensitive,
       is_bind_aware,
       sql_text
FROM v$sql
WHERE sql_id = :sql_id
ORDER BY child_number;
~~~

Các cột elapsed_time và cpu_time trong nhiều dynamic SQL views được tính bằng microsecond. Đây thường là giá trị tích lũy cho child cursor, không phải thời gian của một lần chạy duy nhất.

### 5.1 Tính trung bình chỉ để sàng lọc

Có thể tính:

~~~sql
SELECT sql_id,
       child_number,
       executions,
       ROUND(elapsed_time / 1e6, 3) AS elapsed_seconds_total,
       ROUND(cpu_time / 1e6, 3) AS cpu_seconds_total,
       ROUND(elapsed_time / NULLIF(executions, 0) / 1e6, 4)
           AS avg_elapsed_seconds,
       ROUND(buffer_gets / NULLIF(executions, 0), 1)
           AS avg_buffer_gets
FROM v$sql
WHERE sql_id = :sql_id
ORDER BY child_number;
~~~

Average có thể che khuất outlier. Một SQL chạy 99 lần nhanh và một lần rất chậm vẫn có average có vẻ tốt. Cần kết hợp trace, application latency hoặc công cụ giám sát phù hợp.

### 5.2 V$SQLSTATS

V$SQLSTATS cung cấp thống kê tổng hợp theo SQL_ID và thường có retention tốt hơn so với việc chỉ dựa vào từng child cursor trong V$SQL, nhưng vẫn không phải kho lịch sử vĩnh viễn.

~~~sql
SELECT sql_id,
       plan_hash_value,
       executions,
       ROUND(elapsed_time / 1e6, 3) AS elapsed_seconds,
       ROUND(cpu_time / 1e6, 3) AS cpu_seconds,
       buffer_gets,
       disk_reads,
       rows_processed,
       last_active_time
FROM v$sqlstats
WHERE sql_id = :sql_id;
~~~

Kiểm tra metadata và đơn vị của cột theo phiên bản đang dùng. Không cộng trùng số liệu từ V$SQL và V$SQLSTATS như thể chúng là hai workload độc lập.

### 5.3 SQL_ID không phải định danh duy nhất của một plan

Một SQL_ID có thể có nhiều child cursor và plan_hash_value. Khi điều tra, ghi cả:

- SQL_ID.
- CHILD_NUMBER.
- PLAN_HASH_VALUE.
- Bind context nếu có.
- Module/action và thời gian chạy.

Chỉ ghi SQL_ID có thể chưa đủ để tái hiện đúng plan đã gây vấn đề.

### 5.4 SQL text có thể chứa dữ liệu nhạy cảm

V$SQL.SQL_TEXT/SQL_FULLTEXT có thể chứa literal trong câu SQL. Hãy tránh sao chép SQL text ra ticket/log công khai nếu có dữ liệu cá nhân hoặc bí mật nghiệp vụ.

## 6. Xem execution plan của cursor

Khi đã có SQL_ID và child number, có thể xem plan bằng DBMS_XPLAN:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        sql_id          => :sql_id,
        cursor_child_no => :child_number,
        format          => 'TYPICAL +PREDICATE +ALIAS'
    )
);
~~~

Nếu đã thu thập runtime statistics, có thể dùng:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        sql_id          => :sql_id,
        cursor_child_no => :child_number,
        format          => 'ALLSTATS LAST +PREDICATE +ALIAS'
    )
);
~~~

ALLSTATS LAST cần có runtime plan statistics được thu thập, ví dụ qua GATHER_PLAN_STATISTICS hoặc cấu hình phù hợp. Nếu chưa có, A-Rows và các cột runtime có thể không xuất hiện.

Đọc các thành phần:

- Operation: table access, index access, join, sort, hash.
- E-Rows: số hàng ước lượng.
- A-Rows: số hàng thực tế.
- Starts: số lần operation bắt đầu.
- Buffers: logical reads.
- Reads: physical reads.
- Predicate Information: điều kiện access/filter.
- Alias: query block và row source.

Nếu E-Rows khác A-Rows nhiều lần, hãy xem thống kê, histogram, bind values và correlation giữa các cột.

## 7. Đọc wait event trong V$SESSION

Một truy vấn đơn giản:

~~~sql
SELECT sid,
       serial#,
       username,
       sql_id,
       state,
       wait_class,
       event,
       seconds_in_wait
FROM v$session
WHERE status = 'ACTIVE'
  AND username IS NOT NULL
ORDER BY wait_class, event;
~~~

Wait event mô tả session đang chờ điều gì tại thời điểm lấy mẫu hoặc trạng thái wait được view báo cáo. Một mẫu duy nhất không đủ để kết luận nguyên nhân gốc.

### 7.1 Một số wait event thường gặp

| Wait/event hoặc nhóm | Có thể liên quan | Cần điều tra thêm |
|---|---|---|
| db file sequential read | Đọc block đơn, thường gặp ở index/table lookup | Số lần đọc, object, plan, cache, storage latency |
| db file scattered read | Đọc nhiều block, thường gặp ở full scan | Số block, scan hợp lý hay không, I/O subsystem |
| direct path read/write | Đọc/ghi trực tiếp, có thể liên quan scan, TEMP hoặc LOB | SQL, operation, kích thước dữ liệu, TEMP |
| direct path read temp / write temp | Sort/hash spill ra TEMP | Workarea, cardinality, PGA, TEMP I/O |
| log file sync | Session chờ commit được xác nhận redo | Commit frequency, redo write, log file parallel write |
| log file parallel write | LGWR ghi redo | Storage latency, redo volume, concurrency |
| enq: TX - row lock contention | Chờ transaction/row lock | Blocker, transaction giữ lock, ứng dụng commit |
| enq: TM - contention | Chờ table enqueue trong một số thao tác | DDL, constraint, khóa bảng và concurrency |
| library cache lock/pin | Tranh chấp library cache trong một số hoạt động | Parse/DDL/invalidations và phiên bản |
| latch: shared pool | Tranh chấp latch shared pool | Parse, shared pool pressure và SQL reuse |
| resmgr:cpu quantum | Resource Manager điều tiết CPU | Consumer group, plan và CPU allocation |
| SQL*Net message from client | Thường là idle wait chờ client | Không coi là DB bottleneck nếu session idle |

Tên event chỉ là tín hiệu. Ví dụ db file sequential read không mặc nhiên có nghĩa index thiết kế sai; một truy vấn hợp lệ có thể cần nhiều block đơn. Cần kết hợp số lần chờ, thời gian, SQL, object và plan.

### 7.2 Wait class

Oracle nhóm wait event thành các wait class như User I/O, System I/O, Concurrency, Application, Commit, Network, Configuration và Idle.

Wait class giúp định hướng điều tra, nhưng không phải kết luận. Một session có thể luân phiên giữa CPU và nhiều wait event trong cùng một lần thực thi.

### 7.3 CPU không xuất hiện như một wait event thông thường

Khi session đang chạy trên CPU, V$SESSION có thể cho thấy trạng thái ON CPU trong STATE ở các ngữ cảnh phù hợp hoặc không có wait hiện tại. Không có wait event lớn không chứng minh query nhanh. Hãy xem CPU statistics, SQL elapsed/CPU và delta của session/system stats.

## 8. Tìm session đang block và bị block

V$SESSION có các cột BLOCKING_SESSION, BLOCKING_INSTANCE, FINAL_BLOCKING_SESSION và FINAL_BLOCKING_INSTANCE ở các phiên bản hỗ trợ.

Ví dụ:

~~~sql
SELECT sid,
       serial#,
       username,
       sql_id,
       event,
       blocking_session,
       blocking_instance,
       final_blocking_session,
       final_blocking_instance
FROM v$session
WHERE blocking_session IS NOT NULL
   OR final_blocking_session IS NOT NULL;
~~~

Trong RAC, dùng GV$SESSION và giữ INST_ID.

### 8.1 Xem lock

~~~sql
SELECT l.sid,
       s.serial#,
       s.username,
       s.sql_id,
       l.type,
       l.id1,
       l.id2,
       l.lmode,
       l.request,
       l.block
FROM v$lock l
LEFT JOIN v$session s
  ON s.sid = l.sid
ORDER BY l.sid, l.type;
~~~

Các cột:

- LMODE: mode lock session đang giữ.
- REQUEST: mode session đang yêu cầu.
- BLOCK: chỉ báo có thể block session khác trong một số trường hợp.
- TYPE/ID1/ID2: loại và định danh resource.

Không diễn giải ID1/ID2 như object ID cho mọi loại lock; cách mã hóa phụ thuộc TYPE.

### 8.2 Xem transaction đang mở

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.status,
       s.sql_id,
       t.start_time,
       t.used_ublk,
       t.used_urec
FROM v$transaction t
JOIN v$session s
  ON s.taddr = t.addr;
~~~

Transaction dài có thể giữ lock và tạo undo. Cần xem ứng dụng đang xử lý gì, transaction có cần thiết phải mở lâu không và liệu có một thao tác batch chưa commit.

### 8.3 Không kill session chỉ dựa trên một dòng query

Trước khi yêu cầu DBA terminate session, xác nhận:

- Đúng SID, SERIAL# và INST_ID.
- Session là blocker hay chỉ đang chờ.
- Transaction có công việc chưa commit quan trọng không.
- Rollback có thể kéo dài và gây thêm I/O không.
- Chủ sở hữu ứng dụng và quy trình incident đã được thông báo.

Việc terminate session là hành động vận hành có tác động; chỉ thực hiện bởi người có thẩm quyền theo quy trình.

## 9. Đọc bộ đếm hệ thống và session

V$SYSSTAT chứa system statistics tích lũy. Ví dụ:

~~~sql
SELECT name,
       value
FROM v$sysstat
WHERE name IN (
    'DB time',
    'DB CPU',
    'user calls',
    'execute count',
    'parse count (total)',
    'parse count (hard)',
    'session logical reads',
    'physical reads',
    'physical writes',
    'redo size'
)
ORDER BY name;
~~~

Tên statistic cụ thể có thể thay đổi theo phiên bản. Kiểm tra V$STATNAME để xem tên có tồn tại.

### 9.1 Delta quan trọng hơn tổng tích lũy

Giả sử physical reads hiện tại là 10.000.000. Con số đó không cho biết trong 5 phút gần nhất có phát sinh 100 hay 1.000.000 reads.

Lấy hai mẫu:

~~~sql
SELECT name, value
FROM v$sysstat
WHERE name IN ('physical reads', 'session logical reads', 'redo size');
~~~

Lưu kết quả thời điểm T1, chạy workload, rồi lấy lại tại T2. Delta:

~~~text
Delta = Value(T2) - Value(T1)
Rate  = Delta / elapsed_seconds
~~~

Nếu instance restart giữa hai mẫu hoặc statistic bị reset, delta có thể không còn ý nghĩa. Ghi nhận startup time và instance cùng mỗi mẫu.

### 9.2 DB time và DB CPU

DB time là tổng thời gian database foreground sessions dành cho xử lý và chờ liên quan tới database; DB CPU là phần CPU được tính cho foreground database work theo định nghĩa Oracle. Các số liệu này thường được dùng trong workload analysis.

Không cộng DB time và DB CPU như hai phần độc lập: CPU time nằm trong DB time. Tỷ lệ DB CPU/DB time có thể giúp định hướng workload thiên CPU hay wait, nhưng phải xét cùng khoảng đo và phạm vi session.

### 9.3 Session statistics

V$SESSTAT kết hợp V$STATNAME để xem bộ đếm của một session:

~~~sql
SELECT s.sid,
       n.name,
       st.value
FROM v$sesstat st
JOIN v$statname n
  ON n.statistic# = st.statistic#
JOIN v$session s
  ON s.sid = st.sid
WHERE s.sid = :sid
  AND n.name IN (
      'session logical reads',
      'physical reads',
      'physical writes',
      'CPU used by this session',
      'execute count',
      'parse count (total)'
  )
ORDER BY n.name;
~~~

Các giá trị cũng thường tích lũy trong vòng đời session. Muốn đo riêng một thao tác, lấy snapshot trước và sau trong cùng session rồi tính delta.

## 10. System event statistics

V$SYSTEM_EVENT tổng hợp số lần và thời gian chờ theo event:

~~~sql
SELECT event,
       wait_class,
       total_waits,
       time_waited_micro,
       average_wait
FROM v$system_event
WHERE wait_class <> 'Idle'
ORDER BY time_waited_micro DESC;
~~~

Các cột và đơn vị có thể khác theo phiên bản; kiểm tra metadata. TIME_WAITED_MICRO là tổng thời gian chờ theo microsecond trong view có cột này.

### 10.1 Không chỉ sắp xếp theo TOTAL_WAITS

Một event có hàng triệu lần chờ rất ngắn chưa chắc quan trọng hơn một event có ít lần chờ nhưng mỗi lần kéo dài. Hãy xem:

- Tổng thời gian chờ.
- Số lần chờ.
- Average wait.
- Delta trong khoảng thời gian quan tâm.
- Session/SQL liên quan.

### 10.2 Lấy delta wait theo khoảng

Tương tự V$SYSSTAT, lấy snapshot V$SYSTEM_EVENT tại T1 và T2 rồi so sánh TOTAL_WAITS và TIME_WAITED_MICRO. Có thể lưu vào bảng chẩn đoán riêng hoặc spool file theo quy trình vận hành.

Không trừ hai mẫu nếu instance restart, counter reset hoặc khác INST_ID.

## 11. Xem TEMP và workarea

Sort, hash join và một số operation khác có thể sử dụng TEMP khi workarea không đủ bộ nhớ.

~~~sql
SELECT username,
       session_addr,
       session_num,
       sql_id,
       tablespace,
       segtype,
       blocks
FROM v$tempseg_usage
ORDER BY blocks DESC;
~~~

View có thể có cột khác nhau tùy phiên bản. Có thể join SESSION_ADDR với V$SESSION.SADDR để lấy SID, SERIAL# và SQL_ID.

### 11.1 Workarea đang hoạt động

~~~sql
SELECT sid,
       sql_id,
       operation_type,
       operation_id,
       policy,
       actual_mem_used,
       max_mem_used,
       number_passes,
       tempseg_size
FROM v$sql_workarea_active
ORDER BY tempseg_size DESC NULLS LAST;
~~~

Các cột cụ thể cần kiểm tra theo phiên bản. View này phản ánh workarea đang hoạt động tại thời điểm query; operation có thể kết thúc trước khi lấy mẫu.

### 11.2 TEMP lớn không tự chứng minh thiếu TEMP

TEMP usage có thể tăng do:

- Hash join spill.
- Sort lớn.
- Group by hoặc distinct.
- Temporary LOB.
- Một số thao tác xử lý dữ liệu khác.

Tìm SQL_ID và operation liên quan trước khi tăng TEMP hoặc PGA. Tăng dung lượng TEMP không làm operation trở nên rẻ hơn; nó chỉ có thể tránh lỗi hết dung lượng nếu dung lượng thực sự là giới hạn.

## 12. PGA và memory statistics

V$PGASTAT cung cấp các thống kê PGA tổng hợp:

~~~sql
SELECT name,
       value,
       unit
FROM v$pgastat
ORDER BY name;
~~~

Các metric đáng chú ý có thể gồm:

- aggregate PGA target parameter.
- aggregate PGA auto target.
- total PGA allocated.
- total PGA inuse.
- maximum PGA allocated.
- over allocation count.
- extra bytes read/written.

Tên metric có thể thay đổi theo phiên bản. Đọc cùng workarea và SQL đang chạy.

PGA là tài nguyên quan trọng cho sort/hash workarea. Nhưng không nên tăng PGA chỉ vì một query spill TEMP. Cần xem tổng tải đồng thời, giới hạn memory, cardinality và kích thước row source.

## 13. SQL Trace là gì?

SQL Trace ghi hoạt động của SQL trong session hoặc phạm vi được chọn. Trace có thể ghi:

- Parse.
- Execute.
- Fetch.
- CPU time.
- Elapsed time.
- Disk reads.
- Query/current buffer gets.
- Rows processed.
- Wait events khi bật waits.
- Bind values khi bật binds.

Trace hữu ích khi dynamic views chưa giải thích đủ vì cần biết một SQL được gọi bao nhiêu lần, mỗi call tốn bao lâu, fetch bao nhiêu hàng và chờ event nào.

SQL Trace có overhead. Chỉ bật trong phạm vi cần thiết, trong khoảng thời gian ngắn và tắt ngay sau khi thu thập.

## 14. Trace session hiện tại bằng DBMS_SESSION

Nếu có quyền phù hợp, có thể trace chính session đang chạy:

~~~sql
ALTER SESSION SET TRACEFILE_IDENTIFIER = 'ORDER_DIAG';

BEGIN
    DBMS_SESSION.SESSION_TRACE_ENABLE(
        waits => TRUE,
        binds => FALSE
    );
END;
/

-- Chạy đúng workload cần điều tra ở đây.

BEGIN
    DBMS_SESSION.SESSION_TRACE_DISABLE;
END;
/
~~~

Ý nghĩa:

- TRACEFILE_IDENTIFIER giúp nhận diện trace file.
- waits => TRUE ghi thông tin wait.
- binds => FALSE tránh ghi giá trị bind nhạy cảm trong ví dụ.

Nếu trace block bị ngắt do exception hoặc thao tác client bị hủy, cần bảo đảm session trace được disable. Không để trace bật kéo dài ngoài khoảng điều tra.

### 14.1 Lấy vị trí trace file

Có thể xem diagnostic trace directory và file hiện tại:

~~~sql
SELECT name,
       value
FROM v$diag_info
WHERE name IN (
    'Diag Trace',
    'Default Trace File'
);
~~~

Đường dẫn là phía database server, không phải đường dẫn local của máy client. Quyền đọc file thuộc DBA/OS account và chính sách quản trị máy chủ.

## 15. Trace một session khác bằng DBMS_MONITOR

Khi cần trace session ứng dụng đang chạy, DBA có thể lấy SID và SERIAL# từ V$SESSION rồi bật trace có mục tiêu:

~~~sql
BEGIN
    DBMS_MONITOR.SESSION_TRACE_ENABLE(
        session_id => :sid,
        serial_num => :serial_number,
        waits      => TRUE,
        binds      => FALSE
    );
END;
/
~~~

Sau khi thu thập xong:

~~~sql
BEGIN
    DBMS_MONITOR.SESSION_TRACE_DISABLE(
        session_id => :sid,
        serial_num => :serial_number
    );
END;
/
~~~

SID có thể được tái sử dụng sau khi session kết thúc; SERIAL# giúp phân biệt session incarnation. Trong RAC, cần xác định đúng instance và dùng API/định danh phù hợp phiên bản.

### 15.1 Trace theo service, module và action

Nếu ứng dụng đã gắn service/module/action bằng DBMS_APPLICATION_INFO, DBA có thể trace theo phạm vi đó thay vì một SID đơn lẻ.

Ví dụ khung:

~~~sql
BEGIN
    DBMS_MONITOR.SERV_MOD_ACT_TRACE_ENABLE(
        service_name => 'APP_SERVICE',
        module_name  => 'ORDER_SERVICE',
        action_name  => 'CREATE_ORDER',
        waits        => TRUE,
        binds        => FALSE
    );
END;
/
~~~

Tắt:

~~~sql
BEGIN
    DBMS_MONITOR.SERV_MOD_ACT_TRACE_DISABLE(
        service_name => 'APP_SERVICE',
        module_name  => 'ORDER_SERVICE',
        action_name  => 'CREATE_ORDER'
    );
END;
/
~~~

Đây là trace theo nhóm session khớp bộ lọc. Nếu module/action quá rộng hoặc request volume lớn, có thể tạo nhiều trace file và overhead đáng kể. Hãy giới hạn service/module/action chính xác và thời gian bật.

### 15.2 Client identifier tracing

Khi ứng dụng gắn CLIENT_IDENTIFIER, DBMS_MONITOR có thể trace theo client identifier trong môi trường hỗ trợ:

~~~sql
BEGIN
    DBMS_MONITOR.CLIENT_ID_TRACE_ENABLE(
        client_id => 'request-7f3a2',
        waits     => TRUE,
        binds     => FALSE
    );
END;
/
~~~

Tắt bằng CLIENT_ID_TRACE_DISABLE với cùng client_id. Cú pháp, quyền và khả năng phân tán trace trong RAC cần xác nhận theo phiên bản.

## 16. Bảo vệ bind values và dữ liệu trong trace

Bind tracing có thể hữu ích để hiểu giá trị đầu vào ảnh hưởng plan, nhưng trace có thể chứa:

- Email, số điện thoại, địa chỉ.
- Mã khách hàng hoặc đơn hàng.
- Dữ liệu tài chính.
- Token hoặc thông tin xác thực nếu ứng dụng bind sai loại dữ liệu.
- Nội dung nghiệp vụ bí mật.

Vì vậy:

- Mặc định ưu tiên binds => FALSE.
- Chỉ bật bind tracing khi có phê duyệt và nhu cầu rõ.
- Chọn một session/request cụ thể.
- Lưu trace ở vị trí có ACL phù hợp.
- Không đính kèm trace thô vào ticket công khai.
- Xóa hoặc lưu trữ theo retention policy.
- Che dữ liệu trước khi chia sẻ báo cáo.

Trace file là dữ liệu chẩn đoán nhạy cảm, không phải file log vô hại.

## 17. TKPROF: chuyển trace thành báo cáo dễ đọc

TKPROF là công cụ định dạng trace file thành báo cáo theo SQL statement.

Ví dụ chạy từ máy/server có Oracle client/tool phù hợp:

~~~text
tkprof input.trc output.prf sys=no
~~~

Trong đó:

- input.trc: trace file.
- output.prf: báo cáo đầu ra.
- sys=no: không hiển thị các SQL recursive của SYS trong báo cáo theo cách thông thường.

Đường dẫn và câu lệnh cụ thể phụ thuộc môi trường cài Oracle client/server. TKPROF thường chạy ở OS shell, không chạy như câu SQL trong SQL Developer.

### 17.1 Các cột trong báo cáo TKPROF

Một SQL statement có thể hiển thị:

- count: số lần parse/execute/fetch.
- cpu: CPU time.
- elapsed: elapsed time.
- disk: số physical reads.
- query: consistent gets.
- current: current-mode gets.
- rows: số hàng xử lý.

TKPROF có thể tách parse, execute và fetch. Điều này giúp nhận ra:

- Parse quá nhiều.
- SQL execute nhiều lần theo từng hàng.
- Fetch kéo dài vì client đọc chậm hoặc kết quả lớn.
- SQL tiêu thụ CPU.
- SQL chờ I/O hoặc wait event.

### 17.2 Phân biệt parse, execute và fetch

| Giai đoạn | Ý nghĩa |
|---|---|
| Parse | Oracle kiểm tra cú pháp, resolve object, kiểm tra quyền và tối ưu hóa khi cần |
| Execute | Thực thi statement, có thể đọc/ghi dữ liệu |
| Fetch | Trả các hàng kết quả cho client |

Một SELECT có thể execute một lần nhưng fetch nhiều lần. Nếu client fetch chậm, elapsed của toàn bộ thao tác có thể tăng mà database không nhất thiết đang dùng CPU liên tục.

### 17.3 TKPROF không thay thế actual execution plan đầy đủ

TKPROF có thể hiển thị execution plan nếu trace chứa dữ liệu cần thiết và tùy tùy chọn. Để xem plan của cursor và runtime statistics trong shared pool, dùng DBMS_XPLAN.DISPLAY_CURSOR khi quyền và dữ liệu còn sẵn.

Trace và DISPLAY_CURSOR bổ sung cho nhau:

- Trace cho biết chuỗi call và wait.
- DBMS_XPLAN cho biết operation tree và thống kê plan.

## 18. Trace waits và đọc thời gian

Khi bật waits, trace có thể ghi các wait call với event, thời gian và tham số liên quan.

Một SQL có thể:

- Dùng CPU.
- Chờ đọc block.
- Chờ redo/commit.
- Chờ lock.
- Chờ TEMP I/O.
- Chờ network hoặc client fetch.

Không chỉ nhìn elapsed tổng. Đối chiếu CPU và wait time để tìm phần thời gian chủ yếu.

Ví dụ:

| Metric | SQL A | SQL B |
|---|---:|---:|
| Elapsed | 12 s | 12 s |
| CPU | 11 s | 1 s |
| Wait time | 1 s | 11 s |

Hai SQL có elapsed giống nhau nhưng hướng điều tra khác:

- SQL A có thể CPU-bound: plan, số hàng, thuật toán, parse hoặc biểu thức.
- SQL B có thể wait-bound: I/O, lock, commit, TEMP hoặc network.

Các con số là ví dụ minh họa, không phải kết quả đo.

## 19. Statspack là gì?

Statspack là bộ công cụ Oracle cung cấp để chụp và lưu snapshot thống kê hiệu năng, sau đó tạo báo cáo so sánh hai snapshot.

Statspack hữu ích khi:

- Cần xem tải database trong một khoảng thời gian.
- Muốn biết top wait events.
- Muốn so sánh SQL tiêu thụ CPU/elapsed/buffer gets.
- Cần phân tích xu hướng mà không dùng AWR.
- Môi trường không được cấp quyền sử dụng Diagnostic Pack nhưng vẫn có thể cài và dùng Statspack theo chính sách/license phù hợp.

Statspack không phải bản sao hoàn toàn của AWR và không cung cấp mọi tính năng của AWR/ASH/ADDM.

## 20. Cài đặt Statspack

Việc cài đặt thường do DBA thực hiện bằng script Oracle trong Oracle Home. Script phổ biến là:

~~~text
@?/rdbms/admin/spcreate.sql
~~~

Script có thể hỏi:

- Mật khẩu user PERFSTAT.
- Default tablespace.
- Temporary tablespace.

Sau khi cài, schema PERFSTAT sở hữu các bảng và package Statspack.

### 20.1 Trước khi cài

DBA cần xác nhận:

- Đúng Oracle Home và database.
- Tablespace đủ dung lượng.
- Tên tablespace và quota.
- Quyền tạo user/package/object.
- Quy trình backup và retention.
- Có cài Statspack trước đó hay chưa.

Không chạy lại script cài đặt tùy tiện trên production đang có PERFSTAT. Kiểm tra trạng thái hiện tại và hướng dẫn phiên bản trước.

### 20.2 Không chạy script cài bằng tài khoản ứng dụng

Statspack installation tạo schema và objects quản trị. Đây là công việc DBA theo change management. Ứng dụng chỉ nên có quyền đọc báo cáo cần thiết, không nên sở hữu schema PERFSTAT.

## 21. Tạo Statspack snapshot

Sau khi cài, có thể tạo snapshot bằng package PERFSTAT.STATSPACK:

~~~sql
EXEC perfstat.statspack.snap;
~~~

Mỗi snapshot ghi nhận thống kê tại một thời điểm. Báo cáo so sánh hai snapshot để tính chênh lệch trong khoảng đó.

Có thể truyền mức snapshot nếu đã hiểu cấu hình và quyền:

~~~sql
EXEC perfstat.statspack.snap(i_snap_level => 5);
~~~

Mức snapshot cao hơn có thể thu thập thêm thông tin và tăng chi phí lưu trữ/thu thập. Các level và nội dung cụ thể cần đối chiếu tài liệu Statspack của phiên bản đang chạy; không tăng level chỉ để “có nhiều dữ liệu hơn”.

### 21.1 Chọn khoảng snapshot

Một quy trình đơn giản:

1. Tạo snapshot trước khi workload bắt đầu.
2. Chạy workload trong khoảng thời gian đại diện.
3. Tạo snapshot sau khi workload kết thúc.
4. Tạo report giữa hai snapshot.

Khoảng snapshot quá dài có thể làm loãng một đợt spike ngắn. Khoảng quá ngắn có thể không đủ dữ liệu hoặc làm overhead snapshot chiếm tỷ lệ đáng kể.

### 21.2 Snapshot định kỳ

DBA có thể lập lịch tạo snapshot định kỳ bằng scheduler theo chính sách vận hành. Cần:

- Chọn interval phù hợp.
- Theo dõi dung lượng PERFSTAT.
- Có retention/purge.
- Tránh tạo snapshot quá dày.
- Ghi chú thời gian deploy, batch, backup hoặc incident.

## 22. Tạo Statspack report

Script phổ biến để tạo report:

~~~text
@?/rdbms/admin/spreport.sql
~~~

Script sẽ yêu cầu chọn:

- Begin snapshot.
- End snapshot.
- Tên file report.

Report được ghi ra file ở phía client/session chạy script theo môi trường SQL*Plus/SQLcl. DBA nên lưu cùng incident ID và khoảng thời gian đã chọn.

### 22.1 Nội dung report thường gặp

Statspack report có thể có các phần:

- Database/instance information.
- Snapshot interval.
- Load Profile.
- Instance Efficiency Percentages.
- Top Timed Events.
- Wait Events.
- SQL ordered by elapsed time.
- SQL ordered by CPU time.
- SQL ordered by buffer gets.
- SQL ordered by physical reads.
- Tablespace/segment statistics tùy level.

Không phải mọi section xuất hiện trong mọi level/cấu hình.

### 22.2 Load Profile

Load Profile trình bày các chỉ số theo đơn vị thời gian hoặc transaction, ví dụ:

- DB time.
- DB CPU.
- Logical reads.
- Physical reads.
- Parses.
- Executes.
- User calls.
- Redo size.

Các rate giúp so sánh workload giữa hai khoảng có độ dài khác nhau, nhưng vẫn cần xem tổng thời gian, số transaction và loại workload.

### 22.3 Top Timed Events

Top Timed Events giúp xác định nhóm wait hoặc CPU chiếm thời gian nổi bật trong khoảng snapshot.

Đọc theo thứ tự:

1. Xem DB CPU và wait event lớn.
2. Xác định wait class.
3. So sánh total waits và time waited.
4. Kiểm tra SQL/segment hoặc session liên quan nếu report cung cấp.
5. Đối chiếu với thời điểm ứng dụng chậm.

Một event đứng đầu không tự động là lỗi. Cần biết event đó có idle không, có nằm trong workload mục tiêu không và có tăng bất thường so với baseline không.

### 22.4 SQL ordered by elapsed/CPU/buffer gets

Các phần SQL ordered by giúp xác định statement tiêu thụ tài nguyên:

- Elapsed time: SQL chiếm thời gian tổng lớn.
- CPU time: SQL tiêu thụ CPU.
- Buffer gets: SQL đọc nhiều block logical.
- Physical reads: SQL gây nhiều physical reads.

Một SQL có elapsed cao có thể do chạy rất nhiều lần, mỗi lần hơi chậm, hoặc một lần chạy rất lâu. Cần đọc executions và per-execution metrics nếu có.

## 23. Purge và quản lý Statspack data

Statspack lưu snapshot trong schema PERFSTAT. Nếu không purge, dữ liệu có thể tăng theo thời gian.

Script thường dùng để purge:

~~~text
@?/rdbms/admin/sppurge.sql
~~~

Script sẽ yêu cầu chọn phạm vi snapshot cần xóa. DBA phải xác định retention, bảo đảm không xóa snapshot đang cần cho incident hoặc audit.

Không xóa trực tiếp hàng từ các bảng PERFSTAT theo suy đoán nếu chưa hiểu quan hệ và quy trình package/script.

## 24. Statspack khác AWR như thế nào?

| Tiêu chí | Statspack | AWR |
|---|---|---|
| Mục đích | Thu thập snapshot thống kê hiệu năng | Kho workload repository tích hợp sâu hơn |
| Cài đặt | DBA cài schema PERFSTAT | Tích hợp trong Oracle database |
| Snapshot | Gọi package/scheduler theo cấu hình | Cơ chế snapshot tự động theo cấu hình |
| Báo cáo | spreport và report Statspack | AWR reports và các công cụ liên quan |
| ASH/ADDM | Không cung cấp bộ tính năng tương đương | Có tích hợp các tính năng liên quan |
| Licensing | Dùng theo phạm vi sản phẩm/quyền được cấp | AWR/ASH/ADDM thuộc Diagnostics Pack |

Statspack là lựa chọn hữu ích nhưng không có đầy đủ dữ liệu, độ phân giải và khả năng phân tích của AWR/ASH. Không coi Statspack report là bản thay thế hoàn toàn cho mọi báo cáo AWR.

## 25. Phạm vi licensing: Diagnostics Pack và Tuning Pack

Oracle phân chia một số tính năng quản trị hiệu năng theo pack. Trước khi sử dụng, cần kiểm tra điều khoản licensing áp dụng cho phiên bản, edition, deployment và hợp đồng của tổ chức.

### 25.1 Diagnostics Pack

Các tính năng thường gắn với Diagnostics Pack gồm:

- Automatic Workload Repository (AWR).
- Active Session History (ASH).
- Automatic Database Diagnostic Monitor (ADDM).
- Các view/report lịch sử AWR/ASH tương ứng.

Các view như DBA_HIST_* thường thuộc nhóm dữ liệu AWR. Không truy vấn hoặc xuất dữ liệu này chỉ vì tài khoản có quyền SELECT; quyền kỹ thuật không đồng nghĩa quyền license.

### 25.2 Tuning Pack

Các tính năng thường gắn với Tuning Pack gồm:

- SQL Tuning Advisor.
- SQL Access Advisor.
- Real-Time SQL Monitoring và các chức năng SQL monitoring liên quan.
- Một số chức năng tuning tích hợp khác.

Tuning Pack thường có điều kiện phụ thuộc Diagnostics Pack theo chính sách Oracle. Kiểm tra điều khoản hiện hành và hợp đồng của tổ chức.

### 25.3 CONTROL_MANAGEMENT_PACK_ACCESS không phải bằng chứng license

Có thể xem tham số:

~~~sql
SHOW PARAMETER control_management_pack_access
~~~

Tham số này điều khiển khả năng truy cập một số tính năng management pack trong database. Giá trị cho phép tính năng hoạt động không chứng minh tổ chức đã mua hoặc được cấp quyền license.

Không tự thay đổi tham số để bật/tắt tính năng trên production. DBA/license owner phải xác nhận phạm vi sử dụng.

### 25.4 Dynamic views và SQL Trace

Nhiều dynamic performance views cơ bản và SQL Trace/TKPROF là công cụ chẩn đoán tiêu chuẩn, nhưng một số view, report hoặc tính năng bổ sung có thể thuộc pack riêng. Hãy kiểm tra tài liệu licensing cho đúng tính năng, không suy luận rằng mọi thứ bắt đầu bằng V$ đều miễn phí hoặc mọi tính năng chẩn đoán đều yêu cầu cùng một pack.

## 26. Chẩn đoán trong Oracle RAC

Trong RAC, một dịch vụ có thể chạy trên nhiều instance. Session SID chỉ duy nhất trong phạm vi instance.

Sử dụng GV$ khi cần xem toàn cluster:

~~~sql
SELECT inst_id,
       sid,
       serial#,
       username,
       status,
       sql_id,
       event,
       wait_class
FROM gv$session
WHERE username IS NOT NULL
ORDER BY inst_id, sid;
~~~

### 26.1 Session blocker ở instance khác

Khi điều tra blocking, phải giữ:

- INST_ID.
- SID.
- SERIAL#.
- Blocking instance/session.

Không dùng SID đơn lẻ để kết luận blocker trong RAC.

### 26.2 Trace trong RAC

Trace file được ghi trên node/instance nơi session chạy. Nếu trace theo service/module/client identifier, cần hiểu phạm vi instance và cách gom trace file. DBA có thể dùng ADRCI hoặc cơ chế quản trị diagnostic tập trung phù hợp.

## 27. Multitenant: CDB và PDB

Trong môi trường multitenant:

- CDB có root container và các PDB.
- Session có CON_ID.
- Một số view có dữ liệu ở phạm vi container.
- CDB_* dictionary views cung cấp thông tin nhiều container theo quyền.

Ví dụ:

~~~sql
SELECT con_id,
       sid,
       serial#,
       username,
       status,
       sql_id,
       module
FROM v$session
WHERE username IS NOT NULL
ORDER BY con_id, sid;
~~~

Khi phân tích, ghi lại CON_ID và container hiện tại. Không gộp thống kê của nhiều PDB mà không phân biệt phạm vi.

## 28. Quy trình kết hợp dynamic views, trace và Statspack

Ba công cụ bổ sung cho nhau:

| Công cụ | Phạm vi | Câu hỏi phù hợp |
|---|---|---|
| V$SESSION/V$SQL | Hiện tại và cursor còn trong memory | Session/SQL nào đang chạy? |
| V$SYSTEM_EVENT/V$SYSSTAT | Bộ đếm tích lũy | Wait và resource tăng ra sao trong khoảng đo? |
| SQL Trace/TKPROF | Session/request được chọn | SQL parse/execute/fetch/wait chi tiết thế nào? |
| Statspack | Hai snapshot trong một khoảng | Tải database và top SQL/wait thay đổi thế nào? |

Một incident có thể xử lý như sau:

1. Ghi thời gian bắt đầu và service bị ảnh hưởng.
2. Query V$SESSION để xác định session ACTIVE và SQL_ID.
3. Kiểm tra EVENT, WAIT_CLASS, blocking session và module/action.
4. Xem V$SQL/V$SQLSTATS và plan cursor.
5. Lấy delta V$SYSSTAT/V$SYSTEM_EVENT trong cửa sổ ngắn.
6. Nếu cần, trace một session hoặc module/action có giới hạn.
7. Dùng TKPROF đọc parse/execute/fetch/wait.
8. Nếu cần bức tranh theo khoảng dài hơn, tạo Statspack report giữa hai snapshot.
9. Đối chiếu thời gian với deploy, batch, thay đổi dữ liệu và tải ứng dụng.
10. Lưu kết luận, SQL_ID, plan hash, metric và thời gian lấy mẫu.

## 29. Ví dụ điều tra: request tạo đơn hàng chậm

Giả sử API CREATE_ORDER tăng latency từ 200 ms lên 8 giây.

### Bước 1: Lọc session theo module/action

~~~sql
SELECT sid,
       serial#,
       username,
       module,
       action,
       client_identifier,
       sql_id,
       status,
       event,
       wait_class,
       blocking_session
FROM v$session
WHERE module = 'ORDER_SERVICE'
  AND action = 'CREATE_ORDER';
~~~

### Bước 2: Xem SQL_ID

~~~sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       ROUND(elapsed_time / 1e6, 2) AS elapsed_seconds,
       ROUND(cpu_time / 1e6, 2) AS cpu_seconds,
       buffer_gets,
       disk_reads
FROM v$sql
WHERE sql_id = :sql_id
ORDER BY child_number;
~~~

### Bước 3: Kiểm tra blocking

~~~sql
SELECT sid,
       serial#,
       sql_id,
       event,
       blocking_session,
       final_blocking_session
FROM v$session
WHERE sid IN (:target_sid, :blocking_sid);
~~~

### Bước 4: Lấy plan

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        :sql_id,
        :child_number,
        'ALLSTATS LAST +PREDICATE +ALIAS'
    )
);
~~~

### Bước 5: Trace có phạm vi

Nếu cần phân tích một request/session tái hiện được, DBA bật DBMS_MONITOR trace cho SID/SERIAL# hoặc client identifier đã được phê duyệt. Sau khi tái hiện, disable trace và dùng TKPROF.

### Bước 6: Kết luận từ bằng chứng

Ví dụ các hướng kết luận có thể là:

- SQL chờ row lock do transaction khác giữ lâu.
- Một statement được gọi hàng nghìn lần từ vòng lặp.
- CPU tăng do execution plan đọc quá nhiều hàng.
- Commit chậm do redo write latency.
- Fetch kéo dài vì response/client chậm.

Không chọn một nguyên nhân trước khi xem số liệu.

## 30. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách làm đúng |
|---|---|---|
| Chỉ xem STATUS = ACTIVE | Nhầm wait session với CPU session | Xem EVENT, WAIT_CLASS, STATE và CPU |
| Đọc tổng V$SYSSTAT như tốc độ hiện tại | Không biết metric tăng trong khoảng nào | Lấy hai snapshot và tính delta |
| Dùng SID mà bỏ SERIAL# | Có thể nhầm session sau khi SID được tái sử dụng | Ghi SID + SERIAL# + INST_ID |
| Không lọc INST_ID trong RAC | Ghép nhầm session khác instance | Dùng GV$ và giữ INST_ID |
| Coi mọi wait event là lỗi | Idle wait hoặc wait bình thường bị hiểu sai | Xem thời gian, wait class và workload |
| Kill blocker ngay | Rollback dài hoặc mất transaction quan trọng | Xác nhận blocker và quy trình vận hành |
| Bật trace cho toàn hệ thống | Overhead, file lớn và dữ liệu nhạy cảm | Trace một session/module/client cụ thể |
| Bật bind tracing mặc định | Có thể lộ dữ liệu bí mật | Mặc định binds FALSE, chỉ bật khi được duyệt |
| Quên disable trace | Trace kéo dài và tăng dung lượng | Có thời hạn, disable và xác nhận |
| Chỉ xem SQL elapsed tổng | Không phân biệt parse/execute/fetch | Dùng trace/TKPROF khi cần |
| Dùng V$SQL như lịch sử vĩnh viễn | Cursor có thể bị aged out | Lấy mẫu đúng lúc và lưu theo quy trình |
| Coi Statspack là AWR | Kỳ vọng sai về dữ liệu/công cụ | Hiểu phạm vi và giới hạn từng công cụ |
| Dùng DBA_HIST_* khi chưa xác nhận license | Rủi ro vi phạm điều khoản | Xác nhận Diagnostics Pack trước |
| Dựa vào CONTROL_MANAGEMENT_PACK_ACCESS để kết luận license | Tham số không chứng minh quyền sử dụng | Kiểm tra hợp đồng/licensing owner |
| Cấp SELECT ANY DICTIONARY cho ứng dụng | Quyền quá rộng | Cấp view tối thiểu qua role riêng |
| Chỉ nhìn Top Timed Event | Không biết SQL/session nào tạo wait | Đối chiếu SQL, session, thời gian |
| Snapshot Statspack quá dày | Tăng overhead và dữ liệu lưu | Chọn interval phù hợp, purge định kỳ |

## 31. Bài thực hành tự kiểm tra

Các bài tập nên chạy trong schema thử nghiệm hoặc môi trường được DBA cho phép.

### Bài 1 — Liệt kê session

Query V$SESSION và lọc theo username. Ghi SID, SERIAL#, SQL_ID, MODULE, ACTION, EVENT và WAIT_CLASS.

### Bài 2 — Gắn module/action

Dùng DBMS_APPLICATION_INFO.SET_MODULE/SET_ACTION trong một session. Query V$SESSION để xác nhận nhãn xuất hiện.

### Bài 3 — Xem SQL cursor

Chạy một SELECT có SQL_ID. Đọc V$SQL và V$SQLSTATS, so sánh executions, elapsed, CPU và buffers.

### Bài 4 — Đọc actual plan

Chạy query có GATHER_PLAN_STATISTICS, fetch hết kết quả và xem DBMS_XPLAN.DISPLAY_CURSOR với ALLSTATS LAST.

### Bài 5 — Quan sát wait

Tạo workload đọc dữ liệu trong schema thử nghiệm. Lấy mẫu V$SESSION nhiều lần và phân biệt ON CPU, User I/O và idle wait.

### Bài 6 — Quan sát blocking

Trong hai session thử nghiệm, session A cập nhật một hàng và chưa commit; session B cập nhật cùng hàng. Xem blocker qua V$SESSION/V$LOCK rồi rollback cả hai theo đúng thứ tự.

### Bài 7 — Tính delta system stats

Lấy hai mẫu V$SYSSTAT cách nhau một khoảng có workload. Tính delta và rate cho logical reads, physical reads và redo size.

### Bài 8 — Session trace

Trong session thử nghiệm, đặt TRACEFILE_IDENTIFIER, bật DBMS_SESSION.SESSION_TRACE_ENABLE với waits TRUE và binds FALSE, chạy một câu SQL, disable trace và tìm file bằng V$DIAG_INFO.

### Bài 9 — TKPROF

Dùng TKPROF định dạng trace file. So sánh parse, execute, fetch, CPU, elapsed, disk, query và rows.

### Bài 10 — Trace session khác

DBA bật DBMS_MONITOR.SESSION_TRACE_ENABLE cho SID/SERIAL# thử nghiệm. Chạy một request rồi disable trace. Xác nhận trace chỉ áp dụng cho session đã chọn.

### Bài 11 — Statspack

Trong môi trường được DBA cài sẵn, tạo hai snapshot, chạy workload giữa hai mốc và tạo spreport. Xác định Top Timed Events và SQL ordered by elapsed.

### Bài 12 — Phạm vi quyền

Liệt kê các view/package cần cho bài chẩn đoán. Đề xuất role DIAG_READER với quyền tối thiểu. Phân biệt dynamic view cơ bản, Statspack và các tính năng thuộc Diagnostics/Tuning Pack.

## 32. Checklist trước khi chẩn đoán production

**Phạm vi**

- Đã xác định service, module, action, thời gian và SQL_ID?
- Đang điều tra một session, một service hay toàn instance?
- Có cần dùng GV$ trong RAC?
- Có cần lọc CON_ID trong multitenant?

**Quyền**

- User có quyền đọc đúng các V$ view cần thiết?
- Có tránh cấp quyền quá rộng?
- Trace session khác do DBA hoặc người có thẩm quyền bật?
- Tính năng AWR/ASH/ADDM/SQL Monitoring đã được xác nhận license?

**Thu thập**

- Đã ghi SID, SERIAL#, INST_ID?
- Đã phân biệt current state với cumulative counters?
- Có hai mẫu để tính delta?
- Trace có phạm vi và thời hạn rõ?
- Bind tracing đã được đánh giá bảo mật?
- Statspack snapshot interval phù hợp?

**Phân tích**

- Đã xem SQL_ID, child cursor và plan?
- Đã phân biệt CPU với wait?
- Đã kiểm tra blocker và transaction?
- Đã xem TEMP/PGA khi có sort/hash?
- Đã đối chiếu thời gian với workload/deploy?

**Kết thúc**

- Trace đã được disable?
- File trace/report được lưu ở vị trí có quyền phù hợp?
- Dữ liệu nhạy cảm đã được bảo vệ?
- Statspack retention/purge có kế hoạch?
- Kết luận có bằng chứng, phạm vi và thời gian rõ ràng?

## 33. Ghi nhớ

| Công cụ/khái niệm | Vai trò |
|---|---|
| V$SESSION | Session hiện tại, SQL, wait, blocker |
| GV$SESSION | Session toàn RAC, có INST_ID |
| V$SQL | Cursor và thống kê theo child cursor |
| V$SQLSTATS | Thống kê tổng hợp theo SQL_ID |
| V$SYSTEM_EVENT | Wait statistics tích lũy |
| V$SYSSTAT | System counters tích lũy |
| V$SESSTAT | Session counters |
| V$LOCK/V$TRANSACTION | Lock và transaction |
| V$TEMPSEG_USAGE | Temporary segment usage |
| V$PGASTAT | PGA statistics |
| V$DIAG_INFO | Diagnostic directory/file information |
| DBMS_XPLAN.DISPLAY_CURSOR | Execution plan của cursor thực tế |
| DBMS_SESSION.SESSION_TRACE_ENABLE | Trace session hiện tại |
| DBMS_MONITOR | Trace session/service/module/action/client ID |
| SQL Trace | Parse, execute, fetch, CPU, waits và bind nếu bật |
| TKPROF | Định dạng và tổng hợp trace |
| Statspack | Snapshot và report thống kê theo khoảng |
| AWR/ASH/ADDM | Các tính năng thuộc Diagnostics Pack |
| SQL Tuning Advisor/SQL Monitoring | Các tính năng thuộc Tuning Pack theo điều khoản áp dụng |
| Least privilege | Chỉ cấp quyền cần thiết cho đúng người và phạm vi |

Dynamic views giúp nhìn trạng thái hiện tại và bộ đếm tích lũy; SQL Trace/TKPROF giải thích chi tiết một workload được chọn; Statspack cho bức tranh thống kê giữa hai snapshot. Hãy xác định câu hỏi trước, giữ đúng phạm vi session/instance/container, tính delta khi dùng bộ đếm tích lũy và bảo vệ trace file. Quyền SELECT không đồng nghĩa quyền license: trước khi dùng AWR, ASH, ADDM hoặc SQL Tuning/Monitoring, cần xác nhận pack và hợp đồng tương ứng. Chẩn đoán tốt dựa trên bằng chứng có thời điểm, SQL_ID, plan, wait/resource metrics và quyền truy cập được phê duyệt.
