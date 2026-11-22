# Thu thập alert log, trace, SQL_ID và ngữ cảnh trước khi khắc phục

Khi Oracle Database phát sinh lỗi, bước đầu tiên là lưu lại bằng chứng đủ để tái hiện và xác định phạm vi sự cố. Một thông báo `ORA-` đơn lẻ thường chưa cho biết nguyên nhân gốc. Cần ghép thời điểm xảy ra lỗi với alert log, trace file, SQL_ID, session, service, PDB, instance, máy chủ và thao tác ứng dụng đang thực hiện.

Thu thập dữ liệu trước khi thay đổi trạng thái database giúp tránh mất dấu vết. Những hành động như restart instance, kill session, flush shared pool, thay đổi tham số, compile lại package hoặc chạy lại giao dịch có thể làm thay đổi bằng chứng. Vì vậy, hãy ghi nhận ngữ cảnh và lưu log trước khi bắt đầu khắc phục, trừ trường hợp cần hành động khẩn cấp để bảo vệ dữ liệu hoặc khôi phục dịch vụ.

## 1. Mục tiêu và nguyên tắc thu thập

Một bộ dữ liệu sự cố tốt phải giúp trả lời:

- Lỗi xảy ra lúc nào, theo múi giờ nào và kéo dài bao lâu?
- Database, instance, host, container/PDB và service nào liên quan?
- Người dùng, ứng dụng, module, action và client nào thực hiện thao tác?
- Session đang chạy SQL nào, SQL_ID và child cursor nào?
- Có session chặn, wait event, lỗi I/O, lỗi bộ nhớ hoặc sự cố hệ điều hành đi kèm không?
- Alert log và trace file nào chứa thông tin tương ứng?
- Lỗi có thể tái hiện không, và các bước tái hiện có làm thay đổi dữ liệu không?

Nên tuân theo các nguyên tắc sau:

1. Ghi lại thời điểm có múi giờ và đồng bộ với đồng hồ của ứng dụng, máy chủ database và hệ điều hành.
2. Ghi nhận định danh môi trường trước khi chạy truy vấn: database, instance, PDB, service và host.
3. Lấy log, SQL_ID, session và trạng thái wait trước khi kết thúc session hoặc restart.
4. Lưu nội dung SQL, bind variable và dữ liệu nhạy cảm theo chính sách bảo mật.
5. Giữ nguyên bản gốc của alert log và trace; phân tích trên bản sao.
6. Ghi rõ ai thu thập, thu thập ở đâu, thời điểm bắt đầu/kết thúc và mọi thay đổi đã thực hiện.
7. Chỉ bật trace có phạm vi và thời hạn rõ ràng; tắt trace ngay khi đã thu đủ dữ liệu.

## 2. Xác định đúng database, instance và PDB

Trước khi đọc log hoặc tra SQL_ID, xác nhận phiên kết nối đang trỏ đến đúng môi trường. Một lỗi có thể được báo từ ứng dụng qua service, trong khi người điều tra lại kết nối vào CDB root hoặc một PDB khác.

### 2.1. Thông tin session hiện tại

Chạy truy vấn sau trong đúng kết nối ứng dụng hoặc kết nối quản trị dùng để tái hiện lỗi:

```sql
SELECT
  SYS_CONTEXT('USERENV', 'DB_NAME')          AS db_name,
  SYS_CONTEXT('USERENV', 'CON_NAME')          AS container_name,
  SYS_CONTEXT('USERENV', 'CON_ID')            AS con_id,
  SYS_CONTEXT('USERENV', 'SERVICE_NAME')      AS service_name,
  SYS_CONTEXT('USERENV', 'INSTANCE_NAME')     AS instance_name,
  SYS_CONTEXT('USERENV', 'SERVER_HOST')       AS server_host,
  SYS_CONTEXT('USERENV', 'SESSION_USER')      AS session_user,
  SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA')    AS current_schema,
  SYS_CONTEXT('USERENV', 'MODULE')            AS module,
  SYS_CONTEXT('USERENV', 'ACTION')            AS action,
  SYS_CONTEXT('USERENV', 'CLIENT_IDENTIFIER') AS client_identifier
FROM dual;
```

Các giá trị `MODULE`, `ACTION` và `CLIENT_IDENTIFIER` có thể rỗng nếu ứng dụng không instrument session. Hãy ghi nhận cả trường hợp rỗng thay vì tự suy ra từ tên chương trình client.

### 2.2. Thông tin database và instance

```sql
SELECT name, dbid, db_unique_name, database_role, open_mode
FROM v$database;

SELECT instance_name,
       host_name,
       version,
       startup_time,
       status,
       thread#
FROM v$instance;
```

Trong môi trường RAC, truy vấn `V$INSTANCE` chỉ phản ánh instance hiện tại. Dùng `GV$INSTANCE` để xem các instance mà cluster view trả về:

```sql
SELECT inst_id,
       instance_name,
       host_name,
       version,
       startup_time,
       status,
       thread#
FROM gv$instance
ORDER BY inst_id;
```

Nếu đang điều tra một PDB cụ thể, lưu tên PDB và `CON_ID`. Khi có quyền phù hợp, có thể xem các container:

```sql
SELECT con_id, name, open_mode
FROM v$containers
ORDER BY con_id;
```

Không gộp dữ liệu của nhiều instance thành một sự kiện duy nhất. Trong RAC, cùng một SQL_ID có thể xuất hiện trên nhiều instance, còn session và trace file thuộc một instance cụ thể. Luôn lưu `INST_ID` cùng `SID`, `SERIAL#` và `CON_ID` khi truy vấn các view `GV$`.

## 3. Tìm alert log và ADR

Oracle lưu thông tin chẩn đoán trong Automatic Diagnostic Repository (ADR). ADR có cấu trúc theo sản phẩm, database và instance, bao gồm alert log, trace file, incident và các dữ liệu chẩn đoán liên quan.

### 3.1. Xác định đường dẫn chẩn đoán bằng SQL

Truy vấn `V$DIAG_INFO` để tìm các vị trí ADR:

```sql
SELECT name, value
FROM v$diag_info
ORDER BY name;
```

Các dòng thường cần quan tâm:

| Tên | Nội dung |
|---|---|
| `Diag Enabled` | Cho biết ADR có được bật hay không |
| `ADR Home` | Thư mục ADR của database/instance |
| `Diag Trace` | Thư mục chứa trace file dạng text |
| `Diag Alert` | Thư mục chứa alert log dạng XML |
| `Default Trace File` | Trace file mặc định của session hiện tại |
| `Active Problem Count` | Số problem đang hoạt động trong ADR |
| `Active Incident Count` | Số incident đang hoạt động trong ADR |

Tên và số dòng có thể khác theo release hoặc cấu hình. Dùng giá trị trả về thực tế của database thay vì đoán đường dẫn như `$ORACLE_BASE/diag/rdbms`.

### 3.2. Đọc alert log

Alert log ghi lại các sự kiện quan trọng của instance, ví dụ startup/shutdown, lỗi nội bộ, lỗi process, thay đổi cấu hình, checkpoint, lỗi redo/archive, sự cố tablespace và các thông báo vận hành khác.

Có thể đọc alert log qua ADRCI trên máy chủ database:

```text
adrci
show homes
set homepath diag/rdbms/<db_unique_name>/<instance_name>
show alert -tail 200
```

Thay phần trong dấu ngoặc nhọn bằng ADR home thực tế. Nếu cần xem nội dung cũ hơn, dùng tùy chọn lọc theo thời gian hoặc mở file alert log ở thư mục ADR đã xác định. Không giả định tên thư mục database luôn giống `DB_NAME`; với Data Guard hoặc môi trường nhiều instance, hãy dùng ADR home được hiển thị từ máy chủ.

Trong các release có view này, có thể truy vấn alert log từ SQL:

```sql
SELECT originating_timestamp,
       message_type,
       message_level,
       problem_key,
       message_text
FROM v$diag_alert_ext
WHERE originating_timestamp >=
      SYSTIMESTAMP - INTERVAL '2' HOUR
ORDER BY originating_timestamp;
```

View này giúp lọc sự kiện theo thời gian và nội dung mà không phải đọc toàn bộ file. Dùng khoảng thời gian phù hợp với sự cố, sau đó lưu các dòng trước và sau lỗi để giữ ngữ cảnh. Nếu cần xem nhiều ngày, lưu ý kích thước kết quả và quyền truy cập.

### 3.3. Đọc alert log theo mốc thời gian

Không chỉ lấy đúng dòng chứa `ORA-`. Hãy thu thập một khoảng trước và sau sự kiện:

- Trước lỗi: database vừa startup, có thay đổi tham số, archive destination, tablespace hoặc workload tăng đột biến không?
- Tại thời điểm lỗi: thông báo nào xuất hiện đầu tiên, có mã incident hay process ID không?
- Sau lỗi: instance có tiếp tục hoạt động, process có bị terminate, recovery có chạy hoặc lỗi lặp lại không?

Ghi rõ thời gian theo múi giờ và cách chuyển đổi. Alert log có thể lưu timestamp với thông tin timezone; trace và log ứng dụng có thể dùng định dạng khác. Khi đối chiếu, thống nhất một mốc, thường là UTC hoặc timezone đã được nhóm vận hành quy định.

## 4. Tìm trace file

Trace file chứa chi tiết kỹ thuật của process/session, ví dụ lỗi nội bộ, stack, wait, SQL trace và thông tin chẩn đoán. Một sự kiện có thể tạo nhiều trace file: trace của server process, background process, incident hoặc session được bật SQL trace.

### 4.1. Trace file của session hiện tại

Trong session đang điều tra:

```sql
SELECT value AS default_trace_file
FROM v$diag_info
WHERE name = 'Default Trace File';
```

Kết quả là đường dẫn trace mặc định của session hiện tại trên máy chủ database. Người dùng client không nhất thiết có quyền đọc trực tiếp file này; cần nhờ DBA hoặc nhóm vận hành thu thập file từ máy chủ.

### 4.2. Tìm trace file của một session khác

Khi đã biết `SID` và `SERIAL#`, có thể tra server process:

```sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.status,
       s.machine,
       s.program,
       s.module,
       s.action,
       s.client_identifier,
       s.sql_id,
       s.prev_sql_id,
       p.spid,
       p.tracefile
FROM v$session s
JOIN v$process p
  ON p.addr = s.paddr
WHERE s.sid = :sid
  AND s.serial# = :serial_no;
```

Trong RAC, cần chỉ rõ instance:

```sql
SELECT s.inst_id,
       s.sid,
       s.serial#,
       s.username,
       s.module,
       s.action,
       s.sql_id,
       s.prev_sql_id,
       p.spid,
       p.tracefile
FROM gv$session s
JOIN gv$process p
  ON p.inst_id = s.inst_id
 AND p.addr = s.paddr
WHERE s.inst_id = :inst_id
  AND s.sid = :sid
  AND s.serial# = :serial_no;
```

Các cột `TRACEFILE` và quyền truy cập có thể phụ thuộc release, privilege và loại process. Nếu truy vấn không trả về đường dẫn, dùng `V$DIAG_INFO`, ADRCI và thông tin process ID để DBA tìm trace trong đúng ADR home.

### 4.3. Trace của incident và process nền

Với lỗi nghiêm trọng như `ORA-00600`, `ORA-07445`, process crash hoặc lỗi background process, trace có thể được tạo tự động. Alert log thường ghi đường dẫn hoặc mã incident. Lưu cả trace liên quan, incident ID và các file phụ trợ trong cùng khoảng thời gian.

Không chỉ lấy trace của foreground session. Một lỗi I/O, redo, archive hoặc recovery có thể được ghi trong trace của background process như DBWn, LGWR, ARCn hoặc process khác. Tìm theo timestamp, process ID và incident ID trong ADR.

## 5. Sử dụng ADRCI và Incident Packaging

ADRCI cho phép duyệt ADR homes, lọc alert, liệt kê problem/incident và đóng gói dữ liệu phục vụ điều tra.

Một phiên thao tác thường dùng:

```text
adrci
show homes
set homepath diag/rdbms/<db_unique_name>/<instance_name>
show problem
show incident
show alert -tail 200
```

Khi Oracle tạo incident, ghi lại incident ID và problem key. Với incident cần gửi Oracle Support, IPS có thể tạo gói chẩn đoán:

```text
ips create package incident <incident_id>
ips show packages
ips generate package <package_id> in <output_directory>
```

Tên lệnh và tùy chọn IPS có thể khác theo release. Xác nhận cú pháp bằng trợ giúp ADRCI trên máy chủ đang chạy. Gói chẩn đoán có thể chứa SQL, tên schema, đường dẫn, thông tin hệ thống và dữ liệu nhạy cảm; cần kiểm soát nơi lưu, người được truy cập và quy trình chia sẻ.

Không xóa incident hoặc purge ADR chỉ để giải phóng dung lượng trước khi đã xác nhận gói cần thiết được tạo và lưu an toàn. Chính sách retention/purge ADR nên do DBA vận hành theo dung lượng và yêu cầu hỗ trợ.

## 6. Thu thập SQL_ID và câu SQL liên quan

### 6.1. SQL_ID là gì?

`SQL_ID` là định danh của câu SQL trong shared SQL area. Nó giúp tìm cursor và kế hoạch thực thi liên quan. Tuy nhiên, SQL_ID không xác định một lần thực thi duy nhất:

- Một SQL_ID có thể có nhiều child cursor.
- Mỗi child có thể có plan hash, bind metadata hoặc lý do chia sẻ cursor khác nhau.
- Cùng SQL_ID có thể được thực thi bởi nhiều session và trên nhiều instance.
- Cursor có thể bị aged out khỏi shared pool trước khi người điều tra truy vấn.
- SQL_ID không thay thế timestamp, SID/SERIAL#, instance, PDB hoặc execution ID.

Khi ghi nhận SQL, lấy cả SQL_ID, child number, plan hash value, thời gian hoạt động, parsing schema và session thực thi nếu có.

### 6.2. Lấy SQL_ID từ session đang chạy

Truy vấn session hiện tại:

```sql
SELECT sid,
       serial#,
       username,
       status,
       sql_id,
       sql_child_number,
       sql_exec_start,
       sql_exec_id,
       prev_sql_id,
       prev_child_number,
       event,
       wait_class,
       seconds_in_wait,
       blocking_session,
       blocking_instance
FROM v$session
WHERE sid = :sid;
```

`SQL_ID` thường là SQL hiện tại của session; `PREV_SQL_ID` là SQL trước đó. Nếu lỗi xảy ra ngay sau một câu lệnh đã hoàn tất, `PREV_SQL_ID` có thể hữu ích hơn. Các trường execution có thể rỗng khi session không chạy SQL tại thời điểm truy vấn.

Với RAC:

```sql
SELECT inst_id,
       sid,
       serial#,
       username,
       status,
       sql_id,
       sql_child_number,
       sql_exec_start,
       sql_exec_id,
       prev_sql_id,
       event,
       wait_class,
       blocking_session,
       blocking_instance,
       con_id
FROM gv$session
WHERE inst_id = :inst_id
  AND sid = :sid;
```

Nếu chưa biết session, tìm theo username, module, machine, client identifier hoặc thời điểm:

```sql
SELECT inst_id,
       sid,
       serial#,
       username,
       machine,
       program,
       service_name,
       module,
       action,
       client_identifier,
       sql_id,
       prev_sql_id,
       event,
       wait_class,
       logon_time,
       con_id
FROM gv$session
WHERE username = UPPER(:username)
ORDER BY inst_id, logon_time DESC;
```

Thu hẹp theo đúng tiêu chí đã biết. Không đưa thông tin xác thực hoặc dữ liệu cá nhân vào điều kiện tìm kiếm hay log thu thập.

### 6.3. Lấy SQL text và child cursor

Khi đã có SQL_ID:

```sql
SELECT inst_id,
       sql_id,
       child_number,
       plan_hash_value,
       parsing_schema_name,
       module,
       action,
       executions,
       last_active_time,
       sql_fulltext
FROM gv$sql
WHERE sql_id = :sql_id
ORDER BY inst_id, child_number;
```

`SQL_FULLTEXT` là nội dung SQL dạng CLOB. Nếu quyền hoặc công cụ client không hiển thị đầy đủ, xuất CLOB ra file theo cách an toàn. Với SQL_ID không còn trong shared pool, thử tìm trong trace đã thu thập hoặc nguồn lịch sử được tổ chức cho phép sử dụng.

Không kết luận chỉ từ SQL text. Ghi lại child cursor, plan hash và session thực thi. Nếu có nhiều child, xác định child nào session đã dùng bằng `SQL_CHILD_NUMBER` hoặc `PREV_CHILD_NUMBER`.

### 6.4. Lấy execution plan

Có thể xem plan của cursor còn trong shared pool:

```sql
SELECT *
FROM TABLE(
  DBMS_XPLAN.DISPLAY_CURSOR(
    sql_id          => :sql_id,
    cursor_child_no => :child_no,
    format          => 'TYPICAL'
  )
);
```

Nếu đã thu thập runtime statistics phù hợp, có thể dùng format `ALLSTATS LAST` để xem số liệu thực tế của lần chạy gần nhất. Chỉ dùng các tùy chọn hiển thị bind khi có nhu cầu điều tra rõ ràng và đã kiểm soát dữ liệu nhạy cảm. Bind có thể chứa thông tin khách hàng, token, email hoặc dữ liệu nghiệp vụ.

Plan có thể thay đổi theo child cursor, bind peeking, statistics, optimizer parameter, schema và thời điểm. Lưu plan hash cùng plan text, SQL_ID, child number, thời điểm và instance để so sánh chính xác.

### 6.5. SQL_ID và dữ liệu lịch sử

Nếu cursor đã biến mất khỏi shared pool, dữ liệu lịch sử có thể giúp tìm lại SQL và thông tin thực thi. Tuy nhiên, AWR, ASH, ADDM, SQL Monitor và các view/package liên quan có yêu cầu cấp phép theo Oracle Diagnostics Pack hoặc Tuning Pack tùy tính năng và release.

Không truy vấn `DBA_HIST_*`, `V$ACTIVE_SESSION_HISTORY`, AWR report, SQL Monitor hoặc gọi API của các pack nếu tổ chức chưa xác nhận quyền sử dụng. Hãy kiểm tra tài liệu licensing và hợp đồng hiện hành. Khi không có quyền sử dụng, dựa trên alert log, trace, `V$SESSION`, `V$SQL` và dữ liệu quan sát được thu thập hợp lệ.

## 7. Thu thập session, wait event và blocking

SQL_ID cho biết câu SQL; trạng thái session giúp xác định vì sao câu lệnh chậm hoặc bị treo.

### 7.1. Trạng thái session

Lưu tối thiểu:

- `SID`, `SERIAL#`, `INST_ID`, `CON_ID`.
- Username, machine, program, service, module, action và client identifier.
- SQL_ID, child number, previous SQL_ID.
- Event, wait class, thời gian chờ và blocking session.
- Thời điểm logon, trạng thái session và thời điểm SQL bắt đầu nếu có.

Không chỉ lấy một snapshot khi sự cố kéo dài. Với vấn đề intermittent, cần ghi nhận theo chu kỳ có kiểm soát để thấy session chuyển từ active sang waiting, blocking hoặc idle.

### 7.2. Tìm blocker và waiter

Truy vấn ví dụ:

```sql
SELECT inst_id,
       sid,
       serial#,
       username,
       blocking_instance,
       blocking_session,
       event,
       wait_class,
       seconds_in_wait,
       sql_id,
       module,
       action
FROM gv$session
WHERE blocking_session IS NOT NULL
   OR status = 'ACTIVE'
ORDER BY inst_id, seconds_in_wait DESC;
```

Một session ở trạng thái `ACTIVE` không nhất thiết bị lỗi; nó có thể đang xử lý bình thường hoặc chờ tài nguyên. Ghi nhận event và wait class cùng blocker. Trước khi kill session, xác định giao dịch đang mở, người dùng bị ảnh hưởng và hậu quả rollback.

### 7.3. Lock và object liên quan

Khi sự cố liên quan khóa, có thể kết hợp `GV$LOCK`, `GV$SESSION` và `DBA_OBJECTS` để xác định loại lock và object liên quan. Mã object trong `V$LOCKED_OBJECT` có thể nối với `DBA_OBJECTS.OBJECT_ID`:

```sql
SELECT lo.inst_id,
       lo.session_id AS sid,
       s.serial#,
       s.username,
       o.owner,
       o.object_name,
       o.object_type,
       lo.locked_mode
FROM gv$locked_object lo
JOIN gv$session s
  ON s.inst_id = lo.inst_id
 AND s.sid = lo.session_id
JOIN dba_objects o
  ON o.object_id = lo.object_id
ORDER BY lo.inst_id, lo.session_id;
```

View và quyền truy cập có thể khác theo release. Nếu truy vấn trả về nhiều dòng, phân biệt session giữ lock và session chờ lock; không kết luận mọi lock đều là deadlock. Oracle thường tự phát hiện deadlock và ghi lỗi liên quan vào trace/alert.

## 8. Bật SQL trace có kiểm soát

SQL trace ghi nhận câu SQL, parse/execute/fetch, wait event và thông tin thời gian. Trace hữu ích khi cần biết session thực hiện câu lệnh nào và thời gian bị tiêu tốn ở đâu. Trace có thể tạo lượng dữ liệu lớn và chứa SQL text hoặc bind values nhạy cảm.

### 8.1. Trace session hiện tại

Có thể bật trace cho session hiện tại bằng `DBMS_MONITOR`:

```sql
BEGIN
  DBMS_MONITOR.SESSION_TRACE_ENABLE(
    waits => TRUE,
    binds => FALSE
  );
END;
/
```

Sau khi tái hiện đủ một lần lỗi, tắt trace:

```sql
BEGIN
  DBMS_MONITOR.SESSION_TRACE_DISABLE;
END;
/
```

Tham số `waits => TRUE` ghi nhận wait event. `binds => FALSE` tránh ghi giá trị bind trong ví dụ mặc định. Chỉ bật binds khi cần, đã có phê duyệt và có biện pháp bảo vệ file trace.

### 8.2. Trace session khác

DBA có thể bật trace cho session đã xác định bằng SID và SERIAL#:

```sql
BEGIN
  DBMS_MONITOR.SESSION_TRACE_ENABLE(
    session_id => :sid,
    serial_num => :serial_no,
    waits      => TRUE,
    binds      => FALSE
  );
END;
/
```

Khi hoàn tất, gọi `SESSION_TRACE_DISABLE` với cùng SID và SERIAL#. Trong RAC, xác định đúng instance trước khi bật trace và dùng overload/đối số phù hợp với phiên bản Oracle. Nếu session kết thúc hoặc được tạo lại, SID có thể được tái sử dụng; luôn kiểm tra lại SERIAL# và định danh session trước khi thao tác.

### 8.3. Trace theo client identifier, service, module hoặc action

Trong hệ thống có connection pool, session có thể thay đổi giữa các request. Trace theo client identifier hoặc service/module/action giúp theo dõi một luồng ứng dụng mà không phải đoán session nào sẽ nhận request tiếp theo.

Oracle cung cấp các thủ tục trong `DBMS_MONITOR` như:

- `CLIENT_ID_TRACE_ENABLE` và `CLIENT_ID_TRACE_DISABLE`.
- `SERV_MOD_ACT_TRACE_ENABLE` và `SERV_MOD_ACT_TRACE_DISABLE`.

Các thủ tục này cho phép giới hạn trace theo client identifier hoặc tổ hợp service, module và action. Kiểm tra signature đúng với release đang chạy trước khi dùng, đồng thời chọn giá trị đủ cụ thể để không trace toàn bộ workload production.

Ứng dụng nên thiết lập thông tin nhận diện bằng `DBMS_APPLICATION_INFO.SET_MODULE`, `DBMS_APPLICATION_INFO.SET_ACTION` và `DBMS_SESSION.SET_IDENTIFIER` khi bắt đầu xử lý request. Khi kết thúc, reset các giá trị theo quy ước connection pool để request tiếp theo không thừa ngữ cảnh của request trước.

Ví dụ:

```sql
BEGIN
  DBMS_APPLICATION_INFO.SET_MODULE(
    module_name => 'ORDER_API',
    action_name => 'CREATE_ORDER'
  );
  DBMS_SESSION.SET_IDENTIFIER('request-20261114-00042');
END;
/
```

Giá trị client identifier phải là mã tương quan không chứa bí mật. Không dùng access token, mật khẩu hoặc dữ liệu cá nhân làm identifier.

### 8.4. Phân tích trace bằng TKPROF

Trace file dạng raw có thể được định dạng bằng TKPROF trên máy chủ có Oracle client/tool tương ứng:

```text
tkprof input_trace.trc output_trace.txt waits=yes sort=exeela,fchela
```

TKPROF tổng hợp số lần parse/execute/fetch, CPU, elapsed time, logical reads, physical reads và wait tùy nội dung trace. Giữ lại raw trace cùng file TKPROF đã tạo để người khác có thể kiểm tra cách phân tích.

Trace không tự động cho biết toàn bộ nguyên nhân gốc. Ví dụ, thời gian elapsed cao có thể do wait I/O, lock, network hoặc CPU; cần ghép với alert log, session snapshot và số liệu hệ điều hành.

## 9. Ghi nhận lỗi từ ứng dụng và PL/SQL

Khi ứng dụng bắt lỗi rồi chỉ ghi `ORA-xxxxx`, phần ngữ cảnh thường bị mất. Nên log cả stack, backtrace và thông tin request ở lớp ứng dụng hoặc PL/SQL.

Trong PL/SQL, có thể ghi nhận:

```sql
EXCEPTION
  WHEN OTHERS THEN
    DBMS_OUTPUT.PUT_LINE('SQLCODE=' || SQLCODE);
    DBMS_OUTPUT.PUT_LINE('SQLERRM=' || SQLERRM);
    DBMS_OUTPUT.PUT_LINE(DBMS_UTILITY.FORMAT_ERROR_STACK);
    DBMS_OUTPUT.PUT_LINE(DBMS_UTILITY.FORMAT_ERROR_BACKTRACE);
    DBMS_OUTPUT.PUT_LINE(DBMS_UTILITY.FORMAT_CALL_STACK);
    RAISE;
```

Đây là ví dụ minh họa; trong ứng dụng thật, gửi thông tin vào logger có cấu trúc thay vì phụ thuộc `DBMS_OUTPUT`. Không nuốt ngoại lệ bằng `WHEN OTHERS THEN NULL`. Nếu cần bổ sung context, hãy giữ lại mã lỗi và backtrace gốc rồi phát sinh lại lỗi phù hợp.

Log ứng dụng nên có:

- Timestamp có timezone hoặc UTC.
- Correlation/request ID.
- Tên service, module, action và client identifier.
- Tên thao tác nghiệp vụ và phiên bản ứng dụng.
- Database service, PDB nếu ứng dụng biết, và connection pool identity.
- SQL_ID nếu driver hoặc tầng quan sát có thể lấy được an toàn.
- ORA error code, stack, backtrace và thời gian xử lý.

Không ghi password, access token, dữ liệu thẻ, thông tin định danh cá nhân hoặc bind values nhạy cảm vào log. Nếu cần lưu SQL/bind để điều tra, áp dụng masking, mã hóa, phân quyền và thời hạn lưu trữ.

## 10. Thu thập ngữ cảnh hệ điều hành và mạng

Database trace chỉ phản ánh một phần sự cố. Với lỗi kết nối, process crash, I/O hoặc độ trễ, cần lấy thêm thông tin từ máy chủ:

| Nhóm | Bằng chứng nên lưu |
|---|---|
| Hệ điều hành | Hostname, thời gian, uptime, CPU, memory, swap, process và log hệ thống |
| Storage | Dung lượng filesystem, IOPS/latency, lỗi mount, multipath hoặc storage path |
| Network | Packet loss, reset, timeout, DNS, listener log và firewall/load balancer event |
| Oracle process | PID/SPID, trace file, trạng thái process và thời điểm process kết thúc |
| Client | Driver/JDBC version, connect descriptor, timeout, pool metrics và stack exception |
| Cluster | Node/instance, service relocation, resource restart và clusterware event |

Với lỗi kết nối, thu thập listener log và log phía client trong cùng khoảng thời gian với alert log. Không gửi toàn bộ file cấu hình kết nối nếu trong đó có mật khẩu hoặc secret. Có thể che thông tin nhạy cảm nhưng phải giữ lại host/service/port cần thiết để phân tích.

## 11. Mẫu quy trình thu thập trước khi khắc phục

### Bước 1: Ghi nhận sự kiện

Tạo mã sự cố và ghi thời điểm bắt đầu, thời điểm phát hiện, người báo lỗi, môi trường, mức ảnh hưởng, thao tác nghiệp vụ và bước tái hiện. Ghi rõ lỗi xảy ra một lần hay lặp lại.

### Bước 2: Chụp ngữ cảnh database

Lấy database name/DBID/DB_UNIQUE_NAME, instance, host, PDB/CON_ID, service, session user, schema, module, action và client identifier. Trong RAC, ghi INST_ID cho từng session.

### Bước 3: Lưu alert log và incident

Xác định ADR home từ `V$DIAG_INFO`. Lưu alert log trong khoảng trước/sau sự kiện, problem key, incident ID và thông báo liên quan. Với incident nghiêm trọng, tạo diagnostic package theo quy trình hỗ trợ.

### Bước 4: Tìm session và SQL

Ghi SID/SERIAL#, SQL_ID/PREV_SQL_ID, child number, plan hash, execution start/ID, event, wait class và blocker. Lưu SQL text nếu còn trong shared pool, kèm instance và thời điểm.

### Bước 5: Thu trace khi cần

Chọn đúng session hoặc client/module/action. Bật trace có thời hạn, tái hiện một lần, tắt trace và ghi lại đường dẫn file. Nếu lỗi đã qua, kiểm tra trace tự động trong ADR trước khi bật trace mới.

### Bước 6: Bảo toàn dữ liệu

Sao chép alert log, trace, listener log, log ứng dụng và kết quả truy vấn vào thư mục sự cố có phân quyền. Giữ bản gốc, ghi checksum nếu quy trình yêu cầu và ghi rõ nguồn của từng file.

### Bước 7: Bắt đầu khắc phục

Sau khi có đủ bằng chứng cần thiết, phân tích nguyên nhân và chọn hành động có phạm vi nhỏ nhất. Ghi lại mọi thay đổi, thời điểm thực hiện, người thực hiện và kết quả sau thay đổi. Nếu cần restart hoặc kill session khẩn cấp, lưu những dữ liệu có thể lấy được trước hành động đó.

## 12. Mẫu phiếu thu thập sự cố

Có thể dùng mẫu sau trong ticket hoặc hồ sơ vận hành:

```text
Incident ID:
Mô tả ngắn:
Mức ảnh hưởng:
Thời điểm bắt đầu (timezone/UTC):
Thời điểm kết thúc:
Tần suất/tái hiện:

Database / DBID / DB_UNIQUE_NAME:
Release / RU / patch:
Instance / host:
PDB / CON_ID:
Service:
Schema / user:
Application version / driver:
Module / action / client identifier:

ORA error / full error stack:
SID / SERIAL# / INST_ID:
SQL_ID / PREV_SQL_ID:
Child number / plan hash:
SQL execution start / ID:
Wait event / wait class:
Blocking session / instance:

ADR home:
Alert log path / time range:
Incident ID / problem key:
Trace file path:
Listener log:
Application log / correlation ID:
OS / storage / network evidence:

Các thao tác đã thực hiện:
Kết quả sau từng thao tác:
Người thu thập / thời điểm:
Vị trí lưu bằng chứng:
```

Không để mẫu phiếu chứa mật khẩu, secret hoặc dữ liệu cá nhân không cần thiết. Với SQL text và trace, áp dụng cùng chính sách bảo vệ như dữ liệu production.

## 13. Sai lầm thường gặp khi điều tra

| Sai lầm | Vì sao gây khó điều tra | Cách làm phù hợp |
|---|---|---|
| Chỉ chụp một dòng ORA error | Mất stack, timestamp và lỗi đi trước | Lưu full error stack, alert log và trace liên quan |
| Không ghi timezone | Không ghép được log ứng dụng và database | Ghi UTC hoặc offset rõ ràng |
| Chỉ lưu SQL_ID | Không biết child cursor, instance hay execution nào | Lưu SQL_ID, child, plan hash, SID/SERIAL#, INST_ID và thời gian |
| Truy vấn V$SESSION sau khi session đã kết thúc | Session không còn trong view | Thu snapshot ngay khi lỗi còn xảy ra và lưu trace |
| Restart ngay trước khi lấy log | Có thể mất session state và bằng chứng tạm thời | Thu alert, trace và session context trước nếu tình huống cho phép |
| Bật trace toàn hệ thống | Tạo overhead và lượng file lớn | Giới hạn theo session, client, service, module hoặc action |
| Bật trace binds không kiểm soát | Có thể lộ dữ liệu nhạy cảm | Mặc định tắt binds; chỉ bật khi được phê duyệt |
| Dùng AWR/ASH mà không xác nhận license | Có thể vi phạm điều kiện sử dụng | Kiểm tra quyền Diagnostics/Tuning Pack trước |
| Chỉ lấy trace foreground | Bỏ sót lỗi background, I/O hoặc recovery | Tìm thêm trace theo incident, process và alert log |
| Chạy repair hoặc thay tham số trước khi lưu trạng thái | Làm thay đổi metadata hoặc dấu vết | Ghi lại trạng thái ban đầu và log trước khi thao tác |

## 14. Bảo vệ và lưu trữ bằng chứng

Alert log và trace có thể chứa SQL text, schema/object name, đường dẫn máy chủ, hostname, client identifier, bind value và thông tin vận hành. Cần coi chúng là dữ liệu nội bộ có thể nhạy cảm.

- Lưu bằng chứng trong vùng có phân quyền theo vai trò.
- Dùng mã hóa khi lưu trữ hoặc truyền file ra khỏi máy chủ database.
- Không đính kèm trace nguyên bản vào ticket công khai hoặc chat không được phê duyệt.
- Mask thông tin nhạy cảm trên bản dùng để chia sẻ, đồng thời giữ bản gốc ở kho bảo mật.
- Đặt thời hạn lưu và quy trình xóa theo chính sách tổ chức.
- Ghi lại người truy cập hoặc tải gói diagnostic khi yêu cầu kiểm toán áp dụng.
- Khi gửi Oracle Support, dùng kênh hỗ trợ được tổ chức phê duyệt và kiểm tra nội dung gói trước khi tải lên.

## 15. Nguyên tắc điều tra

Alert log cho biết diễn biến của database; trace cung cấp chi tiết của process hoặc session; SQL_ID giúp định vị cursor; còn session, service, PDB, instance, host và correlation ID nối những dữ liệu đó thành một sự kiện có thể phân tích. Không một nguồn nào đứng riêng đủ để kết luận nguyên nhân.

Trước khi khắc phục, hãy thu thập dữ liệu trong cùng khoảng thời gian, xác định đúng instance và container, lưu SQL cùng child cursor, giữ trace gốc và ghi lại những hành động đã xảy ra. Khi có đầy đủ ngữ cảnh, nhóm vận hành mới có thể phân biệt lỗi SQL, vấn đề concurrency, kế hoạch thực thi, cấu hình, tài nguyên, mạng hoặc lỗi nội bộ Oracle, từ đó chọn cách xử lý có kiểm soát và có thể kiểm chứng.
