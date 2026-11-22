# ORA-00018, ORA-00020 và giới hạn session/process

Oracle Database giới hạn số lượng session và process đồng thời để bảo vệ tài nguyên instance. Khi giới hạn bị chạm, ứng dụng có thể gặp ORA-00018 (maximum number of sessions exceeded) hoặc ORA-00020 (maximum number of processes exceeded). Hai lỗi có liên quan nhưng không giống nhau: session là phiên làm việc logic trong database; process là tiến trình Oracle ở hệ điều hành phục vụ session hoặc công việc nền.

Trong kiến trúc dedicated server, một user session thường cần một server process riêng. Vì vậy, tăng số connection pool có thể đồng thời làm tăng cả sessions lẫn processes. Với shared server, DRCP hoặc các mô hình multiplexing, quan hệ session/process khác đi. Ngoài user connection, instance còn cần process cho background, scheduler, parallel execution, database link và các tác vụ quản trị.

Khắc phục đúng cần bắt đầu bằng việc xác định resource nào chạm giới hạn, instance nào bị ảnh hưởng và nhóm session/process nào đang chiếm capacity. Sau đó mới quyết định dọn session, sửa connection leak/pool sizing, điều chỉnh workload hay tăng parameter. Tăng PROCESSES mà không kiểm tra RAM, OS process limit và tổng tải có thể chỉ chuyển lỗi sang tầng hệ điều hành.

Sau bài học, bạn có thể:

- Phân biệt database session, Oracle process, client process và connection.
- Giải thích nguyên nhân và dấu hiệu của ORA-00018/ORA-00020.
- Đọc V$RESOURCE_LIMIT, V$SESSION, V$PROCESS và các view GV$ trong RAC.
- Phân tích session theo user, status, machine, program, module và service.
- Nhận diện connection pool quá lớn, connection leak và login storm.
- Hiểu PROCESSES, SESSIONS và cách cấu hình parameter.
- Xử lý sự cố khi không thể mở thêm connection.
- Thiết kế capacity cho dedicated/shared server, RAC và CDB/PDB.
- Kiểm thử giới hạn trong môi trường lab an toàn.
- Thiết lập monitoring, alert, runbook và kế hoạch tăng capacity.

> Tên parameter, khả năng cấu hình PDB, view/cột và behavior có thể khác theo Oracle Database release. Các ví dụ dùng SQL*Plus và Oracle JDBC phổ biến. Xác nhận Oracle Database Reference, Licensing Guide và kiến trúc thực tế trước khi thay đổi production.

## 1. Session, process và connection

### 1.1. Database session

Session là trạng thái làm việc của một user hoặc chương trình đã đăng nhập vào database. Session mang theo thông tin như:

- User/schema và quyền hiện hành.
- Session parameters như NLS, timezone và optimizer settings.
- Transaction hiện tại và các lock đang giữ.
- SQL đang chạy hoặc câu lệnh cuối.
- Package state, application context và temporary state.
- Client identifier, module/action và service.

Một ứng dụng có thể mở nhiều session trên cùng database user. Một session cũng có thể tồn tại lâu dù không chạy SQL ở thời điểm quan sát.

### 1.2. Oracle process

Process là tiến trình Oracle ở hệ điều hành. Instance sử dụng process cho:

- Foreground/server process phục vụ user session.
- Background process như DBWn, LGWR, CKPT, SMON, PMON, ARCn và nhiều process khác.
- Job queue/scheduler slave.
- Parallel execution server.
- Một số tác vụ recovery, network, memory và quản trị.

Không phải mọi process đều tương ứng một user session. Một số process phục vụ instance; một số session không có server process độc lập trong shared server architecture.

### 1.3. Client process

Client process là tiến trình ứng dụng bên ngoài Oracle, ví dụ JVM chạy Spring Boot, batch worker, SQL*Plus hoặc monitoring agent. Nó kết nối qua Oracle Net tới listener/service. Client process không phải Oracle server process.

Một JVM có thể có nhiều JDBC connections; mỗi connection có thể tương ứng một session database. Vì vậy, đếm số JVM hoặc pod không đủ để biết số session.

### 1.4. Connection

JDBC Connection là handle ở phía ứng dụng. Với connection pool, một logical connection được mượn/trả từ pool có thể dùng lại physical database session qua nhiều request tuần tự. Khi connection đang được giữ, session thường vẫn tồn tại trên database kể cả ứng dụng không gửi SQL.

Connection pool có 20 connection tối đa thường có thể tạo tới 20 database sessions cho mỗi pool instance nếu dùng dedicated server, nhưng tổng session còn phụ thuộc connection creation, shared pool, DRCP và các pool khác.

### 1.5. Dedicated server

Trong dedicated server, mỗi client session thường được phục vụ bởi một Oracle server process riêng. Mô hình này đơn giản, phổ biến với ứng dụng JDBC và connection pool.

Ưu điểm:

- Mỗi session có server process riêng, dễ theo dõi.
- Workload session được cách ly ở mức process.
- Phù hợp ứng dụng có connection pool được giới hạn hợp lý.

Đổi lại, số session đồng thời có thể kéo theo nhiều server process, memory stack và OS resource.

### 1.6. Shared server

Shared server cho phép nhiều session dùng chung một nhóm shared server process thông qua dispatcher. Nó giảm số server process cần cho nhiều session nhàn rỗi hoặc workload có concurrency cao nhưng thời gian xử lý ngắn.

Shared server không làm session biến mất. Session vẫn chiếm tài nguyên session và có thể giữ transaction/lock. Một số workload cần dedicated server hoặc không phù hợp với shared server; kiểm tra driver/service configuration và feature support trước khi chuyển.

### 1.7. DRCP

Database Resident Connection Pooling (DRCP) quản lý pool server-side để nhiều client connection có thể chia sẻ nhóm pooled server. Nó có thể giảm footprint process/session server trong các ứng dụng có nhiều client connection ngắn hạn, nếu workload và connection class phù hợp.

DRCP không thay thế mọi connection pool ở client và không tự sửa transaction leak. Kiểm tra DRCP support, connection class, purity và lifecycle theo Oracle JDBC/DRCP documentation.

### 1.8. Mối quan hệ tổng quát

```text
CLIENT APPLICATIONS
  JVM A       JVM B       Batch / Admin
    |           |              |
    +-----------+--------------+
                |
          JDBC CONNECTIONS
                |
          Oracle Listener
                |
          DATABASE SERVICE
                |
       +--------+---------+
       |                  |
   DEDICATED            SHARED
   SERVER               SERVER
       |                  |
       v                  v
    SESSION             SESSION
       |                  |
       +------ DATABASE --+

Instance còn có background/parallel/job processes
```

## 2. ORA-00018: maximum number of sessions exceeded

### 2.1. Ý nghĩa

ORA-00018 cho biết database không thể tạo thêm session vì giới hạn session đã đạt. Đây thường là giới hạn do initialization parameter SESSIONS hoặc một resource/session policy tương ứng, tùy thông báo và context.

Khi xảy ra, ứng dụng có thể không đăng nhập được hoặc một thao tác cần tạo session mới thất bại. Các session hiện có vẫn có thể tiếp tục hoạt động; lỗi không nhất thiết làm toàn instance dừng.

### 2.2. Nguyên nhân thường gặp

- Tổng JDBC pool max size trên nhiều JVM/pod quá lớn.
- Connection không được close/trả pool do leak.
- Ứng dụng giữ connection trong lúc gọi service ngoài hoặc chờ người dùng.
- Batch/scheduler tạo nhiều session đồng thời.
- Monitoring, ETL, reporting và DBA tool mở thêm session.
- Login storm sau restart/failover.
- Inactive session lâu vẫn giữ chỗ.
- Một user hoặc service có concurrency tăng đột biến.

### 2.3. Session INACTIVE vẫn tiêu thụ slot

INACTIVE chỉ cho biết session hiện không thực thi SQL; session vẫn được đăng nhập và vẫn chiếm một session slot. Connection pool thường giữ các connection idle để tái sử dụng, vì thế số session có thể cao hơn số request đang chạy.

Không coi mọi INACTIVE session là leak. Cần phân biệt pool idle hợp lệ, session chờ client, session có transaction mở và session thực sự bị bỏ quên.

### 2.4. ORA-00018 và SESSIONS_PER_USER

Profile có giới hạn SESSIONS_PER_USER có thể tạo lỗi ORA-02391 (exceeded simultaneous SESSIONS_PER_USER limit), khác ORA-00018 ở giới hạn instance/session resource. Khi chẩn đoán, kiểm tra profile và user resource limit để không nhầm hai nguyên nhân.

### 2.5. Dấu hiệu ứng dụng

- Pool báo không lấy được connection hoặc chờ tới acquisition timeout.
- Login/connection mới nhận ORA-00018.
- Số session gần limit_value trong V$RESOURCE_LIMIT.
- Connection count tăng theo số replica/pod hoặc sau deploy.
- Số INACTIVE session tăng theo thời gian dù request rate ổn định.

## 3. ORA-00020: maximum number of processes exceeded

### 3.1. Ý nghĩa

ORA-00020 cho biết Oracle không thể tạo thêm process vì đã đạt giới hạn PROCESSES. Lỗi có thể xuất hiện khi tạo server process cho user connection hoặc khi instance cần tạo process cho tác vụ nền/parallel/job.

### 3.2. Nguyên nhân thường gặp

- PROCESSES đặt thấp so với concurrency thực tế.
- Dedicated server connections tăng đột biến.
- Connection pool trên nhiều ứng dụng cộng dồn vượt capacity.
- Parallel query/DML tạo nhiều PX server.
- Scheduler jobs hoặc batch job chạy đồng thời quá nhiều.
- Database link hoặc remote workload mở thêm server process.
- Background process/instance feature cần thêm process.
- Session/process leak hoặc connection storm.

### 3.3. Session count thấp nhưng process limit vẫn có thể đầy

Process pool không chỉ chứa foreground session process. Background, parallel execution, job queue và các process khác cũng tiêu thụ PROCESSES. Vì vậy, V$SESSION count thấp hơn PROCESSES không chứng minh còn đủ process slot.

### 3.4. Dedicated server và shared server

Với dedicated server, mỗi user session thường làm tăng server process count gần tương ứng. Shared server có thể phục vụ nhiều session bằng ít shared server process hơn, nhưng vẫn cần dispatcher/shared server process và session slots. Thay đổi architecture phải dựa trên workload, không chỉ để né ORA-00020.

### 3.5. Dấu hiệu ứng dụng và database

- Listener có thể nhận request nhưng database không tạo được server process.
- Connection mới thất bại, thường kèm ORA-00020.
- V$RESOURCE_LIMIT cho resource processes gần limit.
- V$PROCESS count cao; kiểm tra background/foreground composition.
- Parallel query hoặc job concurrency tăng mạnh.
- Alert log ghi lỗi process limit và thông tin process cần tạo.

## 4. Phân biệt ORA-00018 và ORA-00020

| Tiêu chí | ORA-00018 | ORA-00020 |
| --- | --- | --- |
| Resource chạm giới hạn | Sessions | Processes |
| Parameter trọng tâm | SESSIONS | PROCESSES |
| Đối tượng đếm | Database sessions | Oracle processes |
| Inactive session | Vẫn tiêu thụ session slot | Có thể vẫn gắn với server process |
| Background process | Có session/resource behavior riêng; không đồng nhất với user session | Tiêu thụ process |
| Shared server | Vẫn có session limit | Giảm server process cần cho session, nhưng process vẫn có giới hạn |
| Hướng điều tra đầu tiên | V$RESOURCE_LIMIT sessions, V$SESSION | V$RESOURCE_LIMIT processes, V$PROCESS |

### 4.1. Cả hai lỗi có thể xuất hiện cùng nhau

Trong dedicated server, số session và process có liên hệ chặt. Nếu cả hai resource gần cạn, lỗi xuất hiện có thể phụ thuộc resource nào bị chạm trước. Ví dụ tăng pool có thể làm session count và server process count cùng tăng.

### 4.2. Không chỉ nhìn số connection của một service

Giới hạn thường ở cấp instance, trong khi connection đến từ nhiều service, schema, ứng dụng, batch, admin và background. Tổng tất cả workload mới là số cần so với capacity.

## 5. Kiểm tra parameter và resource limit

### 5.1. SHOW PARAMETER

Trong SQL*Plus:

```sql
SHOW PARAMETER processes;
SHOW PARAMETER sessions;
SHOW PARAMETER transactions;
SHOW PARAMETER shared_servers;
SHOW PARAMETER dispatchers;
SHOW PARAMETER resource_limit;
```

Kiểm tra giá trị đang có hiệu lực. SHOW PARAMETER có thể hiển thị giá trị từ instance/session context; trong RAC cần xác nhận từng instance.

### 5.2. V$PARAMETER

```sql
SELECT
    name,
    value,
    isdefault,
    isses_modifiable,
    issys_modifiable
FROM v$parameter
WHERE name IN (
    'processes',
    'sessions',
    'transactions',
    'shared_servers',
    'dispatchers'
)
ORDER BY name;
```

Các cột metadata cho biết khả năng thay đổi theo session/system; PROCESSES là parameter cần restart khi thay đổi. Kiểm tra đúng release và SPFILE/PFILE đang dùng.

### 5.3. V$RESOURCE_LIMIT

Đây là view quan trọng để theo dõi resource utilization:

```sql
SELECT
    resource_name,
    current_utilization,
    max_utilization,
    initial_allocation,
    limit_value
FROM v$resource_limit
WHERE resource_name IN ('processes', 'sessions', 'transactions')
ORDER BY resource_name;
```

- CURRENT_UTILIZATION: số resource đang được sử dụng tại thời điểm truy vấn.
- MAX_UTILIZATION: mức cao nhất kể từ khi instance khởi động hoặc counter được reset theo cơ chế Oracle.
- INITIAL_ALLOCATION: allocation ban đầu.
- LIMIT_VALUE: giới hạn hiện hành hoặc giá trị không giới hạn tùy resource.

MAX_UTILIZATION là high-water mark, không phải số hiện tại. So sánh cả current và max với limit để hiểu hiện trạng và peak.

### 5.4. Giám sát theo thời gian

Lấy snapshot định kỳ V$RESOURCE_LIMIT vào monitoring repository. Một lần truy vấn sau khi sự cố đã qua có thể không còn thấy current utilization cao, trong khi max_utilization vẫn ghi nhận peak.

### 5.5. RAC: GV$RESOURCE_LIMIT

Trong RAC, xem từng instance:

```sql
SELECT
    inst_id,
    resource_name,
    current_utilization,
    max_utilization,
    initial_allocation,
    limit_value
FROM gv$resource_limit
WHERE resource_name IN ('processes', 'sessions', 'transactions')
ORDER BY inst_id, resource_name;
```

Không chỉ cộng số liệu mọi instance nếu parameter limit áp dụng theo instance. Đánh giá từng instance và service placement.

## 6. Đếm session và phân tích nguồn

### 6.1. Tổng session theo TYPE/STATUS

```sql
SELECT
    type,
    status,
    COUNT(*) AS session_count
FROM v$session
GROUP BY type, status
ORDER BY type, status;
```

TYPE thường phân biệt USER và BACKGROUND. Xem session user/background riêng để tránh coi tất cả session là ứng dụng. STATUS ACTIVE/INACTIVE là trạng thái tại thời điểm snapshot.

### 6.2. Theo username

```sql
SELECT
    username,
    status,
    COUNT(*) AS session_count
FROM v$session
WHERE type = 'USER'
GROUP BY username, status
ORDER BY session_count DESC;
```

### 6.3. Theo machine/program

```sql
SELECT
    username,
    machine,
    program,
    module,
    service_name,
    status,
    COUNT(*) AS session_count
FROM v$session
WHERE type = 'USER'
GROUP BY
    username, machine, program, module,
    service_name, status
ORDER BY session_count DESC;
```

Query giúp nhận diện ứng dụng/pod/agent tạo nhiều session. MACHINE/PROGRAM có thể bị thiếu hoặc do client tự khai báo; kết hợp module/action/client_identifier và pool metrics.

### 6.4. Session đang ACTIVE

```sql
SELECT
    sid,
    serial#,
    username,
    status,
    machine,
    program,
    module,
    action,
    sql_id,
    event,
    last_call_et
FROM v$session
WHERE type = 'USER'
  AND status = 'ACTIVE'
ORDER BY last_call_et DESC;
```

ACTIVE không nhất thiết nghĩa CPU đang chạy; session có thể ACTIVE nhưng đang wait event. Đọc EVENT, WAIT_CLASS, SQL_ID và blocking_session.

### 6.5. Session INACTIVE lâu

```sql
SELECT
    sid,
    serial#,
    username,
    machine,
    program,
    module,
    service_name,
    last_call_et,
    sql_id,
    status
FROM v$session
WHERE type = 'USER'
  AND status = 'INACTIVE'
ORDER BY last_call_et DESC
FETCH FIRST 100 ROWS ONLY;
```

LAST_CALL_ET là thời gian kể từ khi session trở thành ACTIVE/INACTIVE theo trạng thái hiện tại, đơn vị giây. Session inactive lâu có thể là pool idle hợp lệ; đối chiếu pool configured max/idle và transaction state trước khi kết luận leak.

### 6.6. Session có transaction mở

```sql
SELECT
    s.sid,
    s.serial#,
    s.username,
    s.status,
    s.machine,
    s.program,
    s.module,
    s.last_call_et,
    t.start_time,
    t.used_ublk,
    t.used_urec
FROM v$session s
JOIN v$transaction t
  ON t.ses_addr = s.saddr
ORDER BY t.start_time;
```

## 7. Đếm process và phân tích server process

### 7.1. Tổng Oracle process

```sql
SELECT
    COUNT(*) AS process_count
FROM v$process;
```

V$PROCESS cho biết các Oracle process hiện có trong instance. So sánh với V$RESOURCE_LIMIT processes; hai view phục vụ hai góc nhìn và có thể thay đổi giữa hai lần lấy snapshot.

### 7.2. Phân loại process

```sql
SELECT
    pname,
    background,
    program,
    COUNT(*) AS process_count
FROM v$process
GROUP BY pname, background, program
ORDER BY process_count DESC;
```

Pname/background giúp nhận diện background process; program thường chứa thông tin executable/client hoặc server process. Không kết luận một process bất thường chỉ từ tên program.

### 7.3. Session gắn với process

```sql
SELECT
    s.sid,
    s.serial#,
    s.username,
    s.status,
    s.server,
    s.machine,
    s.program,
    s.module,
    p.pid AS oracle_pid,
    p.spid AS os_pid,
    p.program AS server_program
FROM v$session s
LEFT JOIN v$process p
  ON p.addr = s.paddr
WHERE s.type = 'USER'
ORDER BY s.username, s.sid;
```

Dedicated server thường có server process gắn với session. Shared server và một số kiến trúc khác có quan hệ khác; không dùng phép join này làm công thức đếm process thay thế V$PROCESS.

### 7.4. Session server mode

```sql
SELECT
    server,
    status,
    COUNT(*) AS session_count
FROM v$session
WHERE type = 'USER'
GROUP BY server, status
ORDER BY server, status;
```

SERVER có thể phản ánh DEDICATED, SHARED hoặc PSEUDO tùy mode/release. Dùng để hiểu session đang được phục vụ theo mô hình nào.

### 7.5. Parallel execution

Parallel query/DML có thể tạo PX server process. Kiểm tra:
```sql
SELECT
    qcsid,
    qcserial#,
    server_group,
    server_set,
    degree,
    req_degree,
    COUNT(*) AS px_servers
FROM v$px_session
GROUP BY
    qcsid, qcserial#, server_group, server_set,
    degree, req_degree
ORDER BY px_servers DESC;
```

V$PX_SESSION hiển thị quan hệ query coordinator và parallel server. Một workload parallel có thể làm process usage tăng đột biến dù số user session không tăng tương ứng.

### 7.6. Scheduler jobs

```sql
SELECT
    owner,
    job_name,
    session_id,
    running_instance,
    elapsed_time,
    cpu_used
FROM dba_scheduler_running_jobs
ORDER BY owner, job_name;
```

Đối chiếu số job đồng thời với scheduler configuration và workload window. Các job queue slave có thể tiêu thụ process; không hủy job chỉ vì thấy process count cao nếu chưa xác định tác động nghiệp vụ.

### 7.7. Background và foreground

Background process là cần thiết cho instance. Không kill process chỉ vì program/name lạ hoặc process count cao. Dùng alert log, V$BGPROCESS, V$PROCESS và tài liệu Oracle để xác định process role.

### 7.8. Vì sao V$SESSION không bằng V$PROCESS?

V$SESSION đếm session, V$PROCESS đếm Oracle process. Background process có thể không tương ứng user session; shared server cho phép nhiều session dùng chung process; parallel execution có thể tạo thêm process. Chênh lệch giữa hai count là bình thường và cần đọc theo architecture.

## 8. PROCESSES và SESSIONS parameter

### 8.1. PROCESSES

PROCESSES đặt giới hạn số process của instance. Nó phải đủ cho foreground server process, background process và các process phát sinh từ workload/feature đang dùng, cộng thêm headroom.
 
PROCESSES là parameter tĩnh trong các release Oracle phổ biến: thay đổi cần ghi SPFILE/PFILE và restart instance để có hiệu lực. Kiểm tra Oracle Database Reference của release trước khi thực hiện.

### 8.2. SESSIONS

SESSIONS đặt giới hạn session đồng thời. Giá trị mặc định thường được Oracle suy ra từ PROCESSES; công thức mặc định được tài liệu hóa phổ biến là:
```text
SESSIONS = (1.5 * PROCESSES) + 22
```

Đây là giá trị mặc định tham khảo, không thay thế việc đọc giá trị thực tế bằng SHOW PARAMETER/ V$PARAMETER. Cấu hình shared server, RAC, release và các yêu cầu ứng dụng có thể làm việc chọn limit cần cân nhắc riêng.

### 8.3. Sessions không phải số pool connection tối đa

SESSIONS phải chứa cả user sessions và các session/resource khác mà Oracle tính vào limit. Không đặt SESSIONS bằng tổng connection pool max mà không cộng DBA, monitoring, scheduler và headroom.

### 8.4. Kiểm tra giá trị có hiệu lực và SPFILE

```sql
SHOW PARAMETER spfile;

SELECT
    name,
    value,
    issys_modifiable,
    isdefault
FROM v$parameter
WHERE name IN ('processes', 'sessions');
```

V$PARAMETER hiển thị giá trị hiệu lực ở instance hiện tại. V$SPPARAMETER có thể dùng để xem cấu hình trong SPFILE nếu database khởi động từ SPFILE.

### 8.5. Xem cấu hình SPFILE

```sql
SELECT
    sid,
    name,
    value,
    isspecified
FROM v$spparameter
WHERE name IN ('processes', 'sessions')
ORDER BY sid, name;
```

Nếu database dùng PFILE, thay đổi phải được ghi vào file cấu hình và dùng đúng file khi restart. Luôn sao lưu SPFILE/PFILE trước khi thay đổi.

### 8.6. Thay đổi PROCESSES

Ví dụ single instance:
```sql
ALTER SYSTEM SET PROCESSES = 800 SCOPE = SPFILE;
```

Ví dụ RAC khi cấu hình chung cho mọi instance:
```sql
ALTER SYSTEM SET PROCESSES = 800
  SCOPE = SPFILE SID = '*';
```

Các con số chỉ minh họa. PROCESSES mới chỉ có hiệu lực sau khi restart instance. Trong RAC, lập kế hoạch restart từng instance/rolling strategy phù hợp và xác nhận yêu cầu parameter đồng nhất theo release/topology.

### 8.7. SESSIONS tự suy ra

Nếu SESSIONS không được đặt tường minh, Oracle thường tự suy ra giá trị mặc định dựa trên PROCESSES. Sau khi thay PROCESSES, đọc lại SESSIONS thực tế. Không đặt SESSIONS thấp hơn concurrency cần thiết hoặc tăng riêng lẻ mà không xét process limit.

### 8.8. TRANSACTIONS

TRANSACTIONS có liên hệ với SESSIONS và transaction concurrency. Nếu thay PROCESSES/SESSIONS, kiểm tra giá trị TRANSACTIONS hiệu lực và tài liệu parameter. Không tăng mọi parameter theo cùng một tỷ lệ nếu chưa có nhu cầu và giới hạn được hiểu rõ.

### 8.9. Restart và xác nhận

Sau khi restart:
```sql
SHOW PARAMETER processes;
SHOW PARAMETER sessions;

SELECT
    resource_name,
    current_utilization,
    max_utilization,
    limit_value
FROM v$resource_limit
WHERE resource_name IN ('processes', 'sessions', 'transactions');
```

Xác nhận instance OPEN, services đăng ký, listener route đúng, background process khỏe, ứng dụng reconnect và monitoring không báo lỗi. Restart có thể gây downtime/role transition; phải theo change plan.

### 8.10. Tăng limit không phải cách sửa leak

Nếu session/process count tăng liên tục sau mỗi request hoặc deploy, tìm leak trước. Tăng limit có thể trì hoãn lỗi nhưng tăng memory/process pressure và làm incident lớn hơn khi leak tiếp diễn.

## 9. Capacity planning cho sessions và processes

### 9.1. Cộng pool theo toàn hệ thống

Không tính một pool riêng lẻ. Tổng demand có thể ước lượng:
```text
Tổng JDBC connection demand
  = Σ (maximumPoolSize của mỗi pool × số replica tối đa)
  + batch/job connections
  + admin/monitoring connections
  + integration/DB link workload
  + operational headroom
```

Nếu mỗi pod có nhiều DataSource, cộng tất cả pool. Nếu rolling deployment chạy song song old/new pods, tính cả giai đoạn overlap. Autoscaling phải dùng replica max chứ không dùng replica trung bình.

### 9.2. Dedicated server process budget

Ước lượng process budget:
```text
PROCESSES demand
  = dedicated foreground server processes
  + background processes
  + parallel execution processes
  + scheduler/job processes
  + database link/feature processes
  + peak operational headroom
```

Không lấy SESSIONS làm thay thế PROCESSES. Lấy V$RESOURCE_LIMIT và V$PROCESS peak thực tế để hiệu chỉnh estimate.

### 9.3. Headroom

Giữ headroom cho:
- DBA và emergency login.
- Monitoring/backup/maintenance.
- Login burst sau restart/failover.
- Parallel query/job peak.
- Scale-out hoặc rolling deployment.
- Background process mới khi bật feature.
- Connection retry sau network recovery.

Headroom phải dựa trên peak đã đo và mức tăng workload dự kiến, không chọn tỷ lệ tùy tiện.

### 9.4. Ví dụ pool budget

Một hệ thống có 6 pod API, mỗi pod có pool max 30, 2 pod worker mỗi pod max 12 và batch pool max 20:
```text
API:       6 × 30 = 180
WORKER:    2 × 12 =  24
BATCH:     1 × 20 =  20
-----------------------
Configured client maximum = 224
```

224 chưa bao gồm admin, monitoring, background, PX, scheduler và các ứng dụng khác. Đây là upper bound cấu hình của các pool, không nhất thiết số session hiện tại.

### 9.5. Rolling deploy và autoscaling

Nếu 6 pod cũ và 6 pod mới cùng tồn tại trong quá trình rollout, API pool demand tạm thời có thể gần gấp đôi. Tính thêm autoscaling surge/unavailable settings và số pool trong từng pod.
 
### 9.6. Pool size không nên bằng số thread

Một ứng dụng có hàng trăm request thread không nhất thiết cần hàng trăm DB connections. Database concurrency tối ưu phụ thuộc CPU, I/O, lock contention và SQL workload. Pool lớn có thể tăng context switching, session count và contention mà không tăng throughput.
 
### 9.7. Đo pool utilization

Thu thập:
- Active connections.
- Idle connections.
- Pending/waiting threads.
- Acquisition latency/timeout.
- Connection creation/validation failure.
- Usage duration và leak detection.
- Max pool size và số replica hiện tại.
 
Đối chiếu pool metrics với V$SESSION theo MODULE/SERVICE/MACHINE.
 
### 9.8. Sizing theo concurrency thực tế

Tìm concurrency database cần thiết qua load test và production telemetry. Điều chỉnh pool từng bước, đo throughput/latency/DB CPU/wait events. Không tăng pool chỉ để hết acquisition timeout nếu nguyên nhân là SQL chậm hoặc lock wait.
 
## 10. Nguyên nhân session/process tăng bất thường

### 10.1. Connection leak

Ứng dụng lấy connection nhưng không close trong mọi nhánh thành công/lỗi. Session vẫn tồn tại và pool không thể cấp lại connection. Dấu hiệu là active connection/pending tăng, pool utilization không trở về baseline và request duration tăng.

### 10.2. Transaction leak

Connection được trả về hoặc giữ lại trong khi transaction vẫn mở. Session có thể INACTIVE nhưng giữ row lock/undo và làm transaction duration tăng. Kiểm tra V$TRANSACTION, V$LOCK và application transaction manager.

### 10.3. Pool cấu hình quá lớn

Mỗi pod có max pool lớn, replica tăng theo autoscaling, cộng thêm worker/batch DataSource khiến tổng sessions vượt capacity. Tính tổng pool max toàn hệ thống.

### 10.4. Login storm

Sau restart hoặc failover, nhiều JVM đồng thời mở lại tất cả connection. Nếu retry không có jitter và pool warm-up không giới hạn, số connection tạo trong thời gian ngắn có thể đẩy process/session tới trần.

### 10.5. Session không được trả từ code

Các pattern dễ gây leak:
- Không dùng try-with-resources.
- Exception xảy ra trước Connection.close().
- ResultSet/Statement giữ connection lâu.
- Connection giữ qua HTTP/RPC call hoặc file I/O.
- Thread bị block nhưng vẫn giữ transaction.
- Async task không kết thúc hoặc cancellation không cleanup.
 
### 10.6. Scheduler và batch overlap

Job chạy lâu hơn chu kỳ schedule có thể chồng nhiều execution. Mỗi execution mở connection riêng. Kiểm tra running jobs, job queue configuration, batch concurrency và cơ chế không chạy trùng.

### 10.7. Parallel execution

Một query parallel có thể yêu cầu nhiều PX servers. Nhiều query đồng thời tạo process spike. Kiểm tra degree, parallel statement queue, Resource Manager và workload window trước khi thay PROCESSES.

### 10.8. Database link và integration

Remote query/database link, gateway và integration workload có thể tạo thêm process/session ở database local hoặc remote. Điều tra cả hai phía thay vì chỉ nhìn application pool.

### 10.9. Session idle hợp lệ

Connection pool giữ idle connection để tái sử dụng. Số INACTIVE ổn định, có giới hạn và tương ứng pool size có thể là bình thường. Leak thường có xu hướng tăng không kiểm soát, giữ transaction hoặc vượt cấu hình pool.

### 10.10. Profile và resource policy

## 11. RAC và giới hạn theo instance

### 11.1. Resource limit trong RAC

PROCESSES và các resource limit cần được xem theo từng instance. Một node có thể chạm limit trong khi node khác còn capacity. Client load balancing không đảm bảo phân bố session/process hoàn hảo, nhất là khi service preferred/available instance hoặc connection pool giữ connection lâu.

### 11.2. Dùng GV$ thay V$

```sql
SELECT
    inst_id,
    resource_name,
    current_utilization,
    max_utilization,
    limit_value
FROM gv$resource_limit
WHERE resource_name IN ('processes', 'sessions')
ORDER BY inst_id, resource_name;
```

### 11.3. Session theo instance/service

```sql
SELECT
    inst_id,
    service_name,
    username,
    machine,
    program,
    status,
    COUNT(*) AS session_count
FROM gv$session
WHERE type = 'USER'
GROUP BY
    inst_id, service_name, username,
    machine, program, status
ORDER BY inst_id, session_count DESC;
```

Xác định service/pool nào dồn nhiều session vào một instance. So sánh với load balancing goal, service configuration và connection lifetime.

### 11.4. Process theo instance

```sql
SELECT
    inst_id,
    COUNT(*) AS process_count
FROM gv$process
GROUP BY inst_id
ORDER BY inst_id;
```

Đọc process count cùng GV$RESOURCE_LIMIT. Không lấy tổng process toàn cluster so với limit của một instance.

### 11.5. Kill session trên RAC

Khi cần terminate một session trong RAC, phải xác định instance:
```sql
ALTER SYSTEM KILL SESSION 'sid,serial#,@inst_id' IMMEDIATE;
```

SID và SERIAL# phải lấy từ cùng một snapshot với INST_ID. Không copy một SID đơn lẻ rồi kill trên instance khác.

### 11.6. Service failover

Khi instance lỗi, service có thể chuyển sang instance khác. Các client reconnect đồng loạt có thể làm instance còn lại chạm PROCESSES/SESSIONS. Capacity plan phải tính peak failover khi một instance nhận workload của nhiều instance.

### 11.7. Rolling maintenance

Khi patch/maintenance theo rolling fashion, session distribution và service placement có thể thay đổi. Xác nhận capacity trên từng node trước khi relocate service; tránh dồn toàn bộ connection pool vào node đang có ít headroom.

## 12. CDB/PDB và giới hạn session/process

### 12.1. Cấp instance và cấp PDB

PROCESSES là tài nguyên process của instance/container database. PDB không có một OS process pool hoàn toàn độc lập với CDB. Session từ nhiều PDB cùng sử dụng tài nguyên instance; cần xem cả toàn CDB lẫn phân bố theo PDB.

### 12.2. Xem session theo container

```sql
SELECT
    con_id,
    username,
    service_name,
    status,
    COUNT(*) AS session_count
FROM gv$session
WHERE type = 'USER'
GROUP BY con_id, username, service_name, status
ORDER BY con_id, session_count DESC;
```

CON_ID giúp nhận diện PDB. Trong CDB root, cần quyền phù hợp để xem session xuyên container; kiểm tra container hiện tại và common/local user.

### 12.3. CDB views

Các CDB_ views có thể cung cấp metadata xuyên PDB khi kết nối CDB root và có quyền thích hợp. Không chạy query từ một PDB rồi giả định kết quả đại diện toàn CDB.

### 12.4. Resource Manager

CDB Resource Manager có thể giới hạn/điều phối tài nguyên giữa PDB, consumer group và workload. Dùng plan/directive được hỗ trợ trong release để ngăn một PDB hoặc service chiếm quá nhiều CPU, parallel server hay session capacity được quản lý.

Resource Manager không thay thế instance PROCESSES sizing. Xác nhận directive và khả năng quản lý session theo release; không tự áp dụng tham số chưa được kiểm chứng.

### 12.5. PDB service

Ứng dụng nên kết nối bằng service thuộc PDB đúng workload. Theo dõi session theo SERVICE_NAME/CON_ID để biết PDB nào tạo connection. Tách service giúp quan sát và quản trị, nhưng không tạo process limit độc lập ở OS.

### 12.6. PDB close/open và pool

Khi PDB đóng hoặc relocate, các connection của PDB có thể mất hoặc không dùng được. Pool cần xử lý invalid connection và reconnect khi service sẵn sàng. Sau relocation, kiểm tra tổng session/process trên instance đích.

## 13. Xử lý sự cố khi gần/chạm giới hạn

### 13.1. Xác nhận lỗi cụ thể

Thu thập:
- ORA code đầy đủ và timestamp.
- Service, database, instance và container.
- Ứng dụng/pod/client tạo request.
- Pool acquisition/connection error.
- Alert log và listener log.
- V$RESOURCE_LIMIT current/max/limit.

Không bắt đầu bằng việc tăng parameter hoặc kill session hàng loạt.

### 13.2. Chẩn đoán resource nào cạn

Chạy:
```sql
SELECT
    resource_name,
    current_utilization,
    max_utilization,
    limit_value
FROM v$resource_limit
WHERE resource_name IN ('sessions', 'processes', 'transactions');
```

Nếu sessions chạm limit, phân tích V$SESSION theo user/program/status. Nếu processes chạm limit, phân tích V$PROCESS, background, PX và scheduler. Có thể cả hai cùng gần trần.

### 13.3. Xác định nhóm chiếm nhiều nhất

```sql
SELECT
    username,
    machine,
    program,
    module,
    service_name,
    COUNT(*) AS total_sessions,
    SUM(CASE WHEN status = 'ACTIVE' THEN 1 ELSE 0 END) AS active_sessions,
    SUM(CASE WHEN status = 'INACTIVE' THEN 1 ELSE 0 END) AS inactive_sessions
FROM v$session
WHERE type = 'USER'
GROUP BY username, machine, program, module, service_name
ORDER BY total_sessions DESC;
```

Tìm nhóm tăng bất thường, nhưng xác minh MACHINE/PROGRAM/MODULE có được client khai báo đúng hay không.

### 13.4. Xác định blocker/transaction lâu

```sql
SELECT
    s.sid,
    s.serial#,
    s.username,
    s.status,
    s.machine,
    s.module,
    s.event,
    s.blocking_session,
    s.last_call_et,
    t.start_time,
    t.used_ublk,
    t.used_urec
FROM v$session s
LEFT JOIN v$transaction t
  ON t.ses_addr = s.saddr
WHERE s.type = 'USER'
ORDER BY t.start_time NULLS LAST, s.last_call_et DESC;
```

Một session giữ transaction lâu có thể giữ lock và connection pool slot. Điều tra application request/thread trước khi kết thúc session.

### 13.5. Ưu tiên phục hồi dịch vụ

Khi không thể mở connection mới:
1. Giữ một kênh DBA đang hoạt động nếu có.
2. Xác định instance/resource đã chạm trần.
3. Tạm dừng scale-out/retry storm hoặc batch không thiết yếu.
4. Giảm connection creation rate ở ứng dụng.
5. Xác định session idle/leak/transaction bất thường.
6. Chỉ terminate session có owner và tác động đã hiểu.
7. Xác nhận resource utilization giảm và connection mới hoạt động.
8. Lập kế hoạch sửa pool/capacity sau khi dịch vụ ổn định.

### 13.6. Khi không thể đăng nhập DBA

Tùy cấu hình, có thể dùng local administrative connection/OS authentication hoặc reserved administrative capability. Tuy nhiên, nếu process limit đã đầy, khả năng tạo server process mới có thể bị ảnh hưởng. Không giả định SYSDBA luôn đăng nhập được bằng một slot không giới hạn.

Chuẩn bị sẵn emergency access/runbook, giám sát trước khi chạm trần và hiểu cách truy cập được hỗ trợ trong môi trường cụ thể. Không kill Oracle OS process trực tiếp để cố lấy slot nếu chưa có hướng dẫn Oracle Support/runbook đã kiểm chứng.

### 13.7. Kiểm tra listener và service

Listener có thể vẫn chạy khi database không tạo thêm session/process. Xem listener status/log và database service registration; phân biệt lỗi listener, service unknown, network connect timeout với ORA-00018/ORA-00020 từ database.

### 13.8. Không xóa process bằng OS kill

Không dùng kill/taskkill để terminate server/background process trong tình huống bình thường. OS kill có thể gây cleanup/recovery phức tạp hoặc ảnh hưởng instance. Dùng SQL/Oracle-supported administration để kết thúc session; nếu process không phản hồi, theo escalation/runbook của Oracle.

## 14. Kết thúc session an toàn

### 14.1. Xác định chính xác session

Trước khi terminate, thu thập SID, SERIAL#, USERNAME, MACHINE, PROGRAM, MODULE, SERVICE_NAME, SQL_ID, STATUS, LOGON_TIME, LAST_CALL_ET, transaction và blocker. Trong RAC phải có INST_ID.

### 14.2. KILL SESSION

Ví dụ single instance:
```sql
ALTER SYSTEM KILL SESSION '123,4567' IMMEDIATE;
```

Ví dụ RAC:
```sql
ALTER SYSTEM KILL SESSION '123,4567,@2' IMMEDIATE;
```

Các giá trị chỉ minh họa. Câu lệnh cần quyền ALTER SYSTEM và phải trỏ đúng session. IMMEDIATE yêu cầu Oracle kết thúc session; rollback/cleanup transaction có thể tiếp tục sau đó.

### 14.3. DISCONNECT SESSION

Oracle cũng hỗ trợ:
```sql
ALTER SYSTEM DISCONNECT SESSION '123,4567' IMMEDIATE;
```

DISCONNECT SESSION có behavior khác KILL SESSION tùy server mode và option. Đọc Oracle SQL Language Reference trước khi chọn POST_TRANSACTION/IMMEDIATE.

### 14.4. Trạng thái KILLED

Sau KILL SESSION, V$SESSION có thể hiển thị trạng thái KILLED trong một thời gian khi Oracle hoàn tất cleanup. Session row không nhất thiết biến mất ngay lập tức. Theo dõi resource count, transaction rollback và alert log; không lặp kill vô hạn.

### 14.5. Chọn session để terminate

Chỉ terminate khi:
- Xác định được owner/application.
- Biết transaction đang giữ và tác động rollback.
- Không phải background/internal session.
- Có căn cứ rằng session idle/leak hoặc workload không thiết yếu.
- Có thông báo/approval theo incident process của tổ chức.

### 14.6. Không kill theo STATUS=INACTIVE đơn thuần

INACTIVE có thể là connection pool idle hợp lệ, session đang chờ client hoặc session giữ transaction. Kiểm tra V$TRANSACTION, lock, module, pool configuration và last activity trước khi terminate.

### 14.7. Cleanup sau terminate

Xác nhận:
- Session đã kết thúc hoặc cleanup đang tiến triển.
- Transaction/locks đã được giải phóng.
- Pool phát hiện connection bị kill và loại khỏi pool.
- Ứng dụng không retry storm.
- Resource count giảm.
- Business operation được reconcile nếu client mất response.

## 15. Connection pool và cách tránh session leak

### 15.1. Dùng try-with-resources

```java
String sql = "SELECT status FROM orders WHERE order_id = ?";

try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, orderId);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            return rs.getString(1);
        }
    }
}
```

Đóng logical connection trả connection về pool. Đóng Statement/ResultSet để giải phóng cursor/resource.

### 15.2. Transaction cleanup

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    try {
        updateOrder(connection);
        insertAudit(connection);
        connection.commit();
    } catch (SQLException | RuntimeException e) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            e.addSuppressed(rollbackError);
        }
        throw e;
    }
}
```

Với framework transaction manager, để framework quản lý commit/rollback. Không trộn transaction boundary thủ công với @Transactional nếu không hiểu propagation và connection binding.

### 15.3. Không giữ connection khi gọi service ngoài

Không làm các bước sau trong cùng transaction/connection nếu có thể tránh:
- Gọi HTTP/REST service chậm.
- Gửi email hoặc message broker.
- Chờ user input.
- Đọc file/network stream lớn.
- Sleep hoặc chờ lock ở tầng ứng dụng.

Chuẩn bị dữ liệu trước transaction, giữ transaction ngắn, ghi outbox cho side effect cần publish sau commit.

### 15.4. Đặt maximum pool size có tổng ngân sách

Tính tổng max pool size của tất cả DataSource × số replica tối đa. Trừ headroom cho admin, monitoring, scheduler và workload khác. Không đặt max pool size theo số CPU application node hoặc số request thread một cách máy móc.

### 15.5. Pool acquisition timeout

Pool acquisition timeout giới hạn thời gian ứng dụng chờ connection trong pool; nó không giảm session count trực tiếp. Khi pool hết connection, timeout giúp fail fast thay vì tạo thêm connection vô hạn. Điều tra vì sao connection bị giữ lâu trước khi tăng pool.

### 15.6. Idle timeout và max lifetime

Pool có thể đóng connection idle hoặc hết lifetime để quản lý resource/stale connection. Chọn giá trị phù hợp firewall/NAT/DB idle policy. Khi pool đóng physical connection, Oracle session được giải phóng sau khi disconnect/cleanup hoàn tất.

### 15.7. Leak detection

Một số pool hỗ trợ leak detection threshold hoặc log connection borrow stack. Bật có kiểm soát trong staging/production theo policy; threshold quá thấp tạo false positive với query hợp lệ dài. Dùng stack trace để tìm code path không close connection.

### 15.8. Reset connection state

Trước khi trả connection về pool, transaction phải kết thúc và session state phải được reset theo pool/framework. AutoCommit, isolation, schema, NLS, timezone, client identifier và module/action có thể ảnh hưởng request kế tiếp.

### 15.9. Không tạo pool trong từng request

DataSource/pool phải được tạo và quản lý ở application lifecycle, không tạo pool mới cho mỗi request. Nhiều pool nhỏ có tổng max size lớn vẫn có thể làm cạn sessions/processes.

### 15.10. Giới hạn pool theo service

Tách pool cho API, batch và reporting nếu cần isolation, nhưng cộng capacity toàn bộ. Dùng service/consumer group/Resource Manager để quản lý workload; không để một batch pool chiếm toàn bộ connection budget.

## 16. Login storm và retry storm

### 16.1. Login storm

Login storm xảy ra khi nhiều client cùng tạo connection mới trong thời gian ngắn, thường sau database restart, network recovery, deployment hoặc failover. Nó có thể tạo đỉnh process/session và CPU cho authentication/logon.

### 16.2. Exponential backoff và jitter

Retry connection theo exponential backoff có giới hạn và random jitter. Nếu tất cả pod retry mỗi 1 giây đúng cùng nhịp, chúng tiếp tục dồn tải vào listener/database khi dịch vụ vừa phục hồi.

### 16.3. Circuit breaker

Khi connect failure vượt threshold, circuit breaker có thể tạm ngừng tạo connection/request mới, chờ cooldown rồi thử lại một số request thăm dò. Nó giảm retry storm nhưng cần giới hạn thời gian và fallback phù hợp.

### 16.4. Pool warm-up

Không nhất thiết mở toàn bộ maximumPoolSize cùng lúc khi ứng dụng khởi động. Tăng dần connection creation, giới hạn initialization concurrency và tránh tất cả replica deploy cùng lúc nếu không cần thiết.

### 16.5. Connection lifetime jitter

Nếu mọi connection cùng được tạo lúc pod startup và maxLifetime giống nhau, chúng có thể hết hạn đồng thời, gây reconnect spike. Một số pool có lifetime attenuation/jitter; kiểm tra implementation và cấu hình.

### 16.6. Sau failover RAC/Data Guard

Nhiều pool có thể đồng thời loại connection cũ và tạo connection mới tới service đã chuyển role/instance. Đảm bảo service ready trước khi mở flood reconnect, retry có jitter và application continuity behavior được kiểm thử.

### 16.7. Autoscaling

Scale-out application làm tăng số pool. Capacity controller phải xét database headroom; autoscaling theo CPU application mà không có giới hạn connection có thể làm database quá tải. Có thể dùng admission control hoặc giới hạn concurrency DB-bound ở application.

### 16.8. Không retry ORA-00018/ORA-00020 vô hạn

Khi database đã báo resource limit, mở connection mới liên tục không giải quyết nguyên nhân. Dừng/giảm connection attempts, chờ resource được giải phóng hoặc capacity được phục hồi. Retry phải bounded và có circuit breaker.
## 17. OS resource và Oracle process capacity

### 17.1. PROCESSES không phải giới hạn duy nhất

Ngay cả khi PROCESSES còn headroom, hệ điều hành vẫn có giới hạn process/task, memory, file descriptor và user resource. Oracle process cần OS resource để chạy; nếu OS không thể tạo process hoặc cấp memory, database có thể gặp lỗi khác trước khi PROCESSES đạt trần.

### 17.2. Linux process/user limits

Trên Linux, DBA/OS admin có thể kiểm tra giới hạn user và service:
```bash
ulimit -u
ulimit -n
cat /proc/<oracle_pid>/limits
ps -u oracle -o pid,ppid,stat,comm | wc -l
```

Các lệnh là ví dụ Linux; thay oracle_pid bằng PID instance process phù hợp. Kiểm tra cả systemd TasksMax, cgroup pids.max, PAM limits và OS policy. Shell ulimit của phiên DBA không nhất thiết là limit của service Oracle đã chạy.

### 17.3. Windows

Trên Windows, process/thread/resource limits và Oracle service account khác Linux. Dùng Windows performance counters, Task Manager/Process Explorer và Oracle documentation cho platform. Không áp dụng ulimit Linux vào Windows.

### 17.4. Memory

Mỗi process có memory footprint riêng, gồm process stack và các vùng memory liên quan. Tăng PROCESSES có thể làm tăng memory cần thiết và OS resource. Đánh giá PGA, SGA, OS RAM, huge pages và peak workload trước khi tăng limit.

### 17.5. File descriptors và network

Mỗi server/client connection có thể dùng socket/file descriptor và các OS resource khác. Kiểm tra giới hạn descriptor, ephemeral ports, firewall/NAT state và network backlog khi có connection spike. Không quy mọi lỗi kết nối thành ORA-00018/ORA-00020.

### 17.6. Đối chiếu Oracle và OS

Nếu V$RESOURCE_LIMIT cho thấy process utilization chưa chạm limit nhưng OS không tạo được process, điều tra OS limits, memory, process table và Oracle alert/trace. Ngược lại, OS còn nhiều capacity nhưng PROCESSES đã đạt limit thì cần xử lý Oracle parameter/workload.

## 18. Listener và lỗi kết nối liên quan

### 18.1. ORA-00018/ORA-00020 khác TNS listener error

ORA-00018/ORA-00020 được database trả về khi session/process resource không đủ. Listener errors có thể xuất hiện trước khi database tạo session hoặc khi listener không tìm được handler phù hợp. Cần đọc error stack đầy đủ.

### 18.2. ORA-12516

Listener không tìm thấy handler phù hợp với protocol stack tại thời điểm yêu cầu. Có thể liên quan handler/service state hoặc khả năng tiếp nhận connection. Kiểm tra listener services, registered handlers, database resource limits và alert log.

### 18.3. ORA-12519

Listener không tìm thấy service handler phù hợp với loại yêu cầu. Kiểm tra service registration, handler state, dedicated/shared server configuration và resource capacity. Không mặc định lỗi này luôn là PROCESSES.

### 18.4. ORA-12520

Listener không tìm thấy available handler cho requested server type. Kiểm tra listener status, dynamic registration, service configuration, dedicated/shared server handlers và instance resource limits.

### 18.5. ORA-12514

Listener không biết service được yêu cầu. Đây thường là vấn đề SERVICE_NAME/registration/registration timing, không đồng nghĩa session/process limit. Kiểm tra lsnrctl services, LOCAL_LISTENER/REMOTE_LISTENER và service startup.

### 18.6. TNS-12518

Listener không thể hand off client connection. Có thể liên quan lỗi tạo server process hoặc OS resource; xem listener log và database alert log để biết nguyên nhân gốc.

### 18.7. Quy trình phân biệt

- Nếu listener không nhận/không biết service: kiểm tra network, listener, service name và registration.
- Nếu listener nhận request nhưng handler không có capacity: kiểm tra handler, shared/dedicated config và process/session limits.
- Nếu database trả ORA-00018/ORA-00020: tập trung vào V$RESOURCE_LIMIT và session/process composition.
- Nếu client timeout trước response: kiểm tra tầng timeout và server outcome.

## 19. Monitoring và alerting

### 19.1. Snapshot resource limit

Lưu định kỳ:
```sql
SELECT
    SYSTIMESTAMP AS sample_time,
    resource_name,
    current_utilization,
    max_utilization,
    initial_allocation,
    limit_value
FROM v$resource_limit
WHERE resource_name IN ('processes', 'sessions', 'transactions');
```

Đưa dữ liệu vào monitoring repository để xem peak theo giờ/ngày và capacity trend.

### 19.2. Tính phần trăm utilization

LIMIT_VALUE thường được trả dưới dạng text; kiểm tra giá trị trước khi chuyển numeric:
```sql
SELECT
    resource_name,
    current_utilization,
    max_utilization,
    limit_value,
    CASE
      WHEN REGEXP_LIKE(limit_value, '^[0-9]+$')
      THEN ROUND(
        current_utilization / TO_NUMBER(limit_value) * 100,
        1
      )
    END AS current_pct
FROM v$resource_limit
WHERE resource_name IN ('processes', 'sessions');
```

Nếu limit_value không phải số hữu hạn, phần trăm có thể NULL. Đặt threshold theo service SLA và headroom, không dựa một ngưỡng chung.

### 19.3. Cảnh báo nhiều mức

Một mô hình minh họa:
| Mức | Điều kiện | Hành động |
| --- | --- | --- |
| Notice | Current utilization tăng nhanh so với baseline | Theo dõi trend |
| Warning | Current hoặc peak vượt ngưỡng capacity đã đặt | Tìm nguồn session/process tăng |
| Critical | Gần limit và connection failures bắt đầu xuất hiện | Kích hoạt incident runbook |
| Recovery | Utilization giảm ổn định và connection mới thành công | Xác nhận backlog/request phục hồi |

Các ngưỡng phần trăm cụ thể cần dựa trên instance size, workload peak và headroom cần cho background/admin. Không chờ tới 100% mới cảnh báo.

### 19.4. Alert theo tốc độ tăng

Một resource ở 70% và tăng 1% mỗi giờ khác với resource tăng 20% trong một phút. Theo dõi slope, rate of change, peak và số connection failures để phát hiện login storm/leak sớm.

### 19.5. Session source dashboard

Hiển thị session count theo:
- Instance và container.
- Service và username.
- Machine/program/module.
- Active/inactive.
- Dedicated/shared.
- Có/không transaction.
- Application pool name/replica.

### 19.6. Process source dashboard

Hiển thị process count theo instance, foreground/background, program/pname và parallel execution. Kết hợp scheduler jobs, PX activity và V$RESOURCE_LIMIT.

### 19.7. Alert log

Theo dõi alert log cho ORA-00018, ORA-00020, lỗi process creation, listener handoff và background process failures. Giữ timestamp đồng bộ với application log và monitoring system.

### 19.8. Monitoring không nên tạo thêm sự cố

Monitoring agent cũng mở session. Giới hạn connection của exporter/agent, reuse connection và tránh poll quá dày bằng query nặng. Cộng session của monitoring vào capacity budget.

## 20. Quy trình xử lý ORA-00018

### 20.1. Immediate triage

1. Xác nhận ORA-00018 và database/instance/container/service.
2. Xem V$RESOURCE_LIMIT sessions current/max/limit.
3. Xem V$SESSION theo username, machine, program, module và status.
4. Xác định pool/service đang tạo nhiều session.
5. Kiểm tra session có transaction mở hoặc lock.
6. Tạm dừng nguồn tạo connection mới nếu đang tăng nhanh.

### 20.2. Giải phóng slot

Nếu có session bỏ quên hoặc workload không thiết yếu, phối hợp owner để đóng logical connection ở ứng dụng hoặc terminate session đã xác minh. Ưu tiên dừng batch/job gây burst và giảm pool acquisition/reconnect. Không kill hàng loạt inactive session.

### 20.3. Xác nhận phục hồi

Sau cleanup, đọc lại V$RESOURCE_LIMIT, thử một connection mới từ ứng dụng bị ảnh hưởng và xác nhận pool metrics trở về bình thường. Kiểm tra transaction rollback và business operation bị ảnh hưởng.

### 20.4. Root cause

So sánh session count theo pool/replica với configured maximum; kiểm tra leak detection, rolling deployment, retry storm, scheduler overlap và session profile. Nếu concurrency hợp lệ đã tăng, lập capacity change thay vì chỉ kill session định kỳ.

## 21. Quy trình xử lý ORA-00020

### 21.1. Immediate triage

1. Xác nhận ORA-00020 và instance.
2. Xem V$RESOURCE_LIMIT processes.
3. Đếm V$PROCESS và phân loại background/foreground.
4. Xem session-to-process mapping.
5. Kiểm tra PX servers, scheduler jobs và database links.
6. Đọc alert log/listener log và OS resource metrics.

### 21.2. Giảm process demand

Tạm dừng job/batch không thiết yếu hoặc giới hạn parallel workload nếu đó là nguồn tăng process và có owner xác nhận. Giảm pool creation/retry storm. Không terminate background process.

### 21.3. Giải phóng session process

Nếu process gắn với session ứng dụng bất thường, xác minh session và terminate bằng SQL khi cần. Với process không có session hoặc background, tìm nguyên nhân theo Oracle diagnostics; không kill PID từ OS như thao tác thường quy.

### 21.4. Đánh giá OS capacity

Kiểm tra OS process/task limit, memory và service manager. Nếu Oracle PROCESSES còn headroom nhưng OS không tạo process, tăng PROCESSES không giải quyết lỗi gốc.

### 21.5. Tăng PROCESSES khi có căn cứ

Nếu workload hợp lệ vượt capacity đã thiết kế, tính lại foreground/background/PX/job demand, headroom, memory và OS limits. Ghi parameter vào SPFILE và lập kế hoạch restart; không kỳ vọng thay đổi có hiệu lực ngay.

## 22. Lab: quan sát session và process

Chỉ chạy trên database lab có quyền và capacity riêng. Không cố tình chạm limit trên production hoặc shared development instance.

### 22.1. Baseline

Chạy:
```sql
SELECT resource_name, current_utilization, max_utilization, limit_value
FROM v$resource_limit
WHERE resource_name IN ('sessions', 'processes');

SELECT type, status, COUNT(*)
FROM v$session
GROUP BY type, status;

SELECT COUNT(*) AS process_count FROM v$process;
```

Ghi lại baseline và thời gian lấy mẫu.

### 22.2. Mở một session giữ kết nối

Từ SQL*Plus hoặc Java test client, mở một connection, chạy query nhỏ rồi để connection mở. Quan sát V$SESSION trước/sau. Trong dedicated server, kiểm tra process tương ứng qua V$PROCESS.

### 22.3. Mở nhiều connection có giới hạn

Java harness:
```java
List<Connection> held = new ArrayList<>();
try {
    for (int i = 0; i < connectionCount; i++) {
        held.add(dataSource.getConnection());
    }
    // Giữ connection để DBA quan sát V$SESSION/V$PROCESS.
    new CountDownLatch(1).await();
} finally {
    for (Connection connection : held) {
        try {
            connection.close();
        } catch (SQLException ignored) {
            // ghi log trong test harness thực tế
        }
    }
}
```

connectionCount phải nhỏ, được cấu hình cho lab và có cleanup/finally. Không đặt vòng lặp vô hạn hoặc dùng connection storm để thử trên môi trường chia sẻ.

### 22.4. Quan sát session inactive

Giữ connection nhưng không execute SQL. Quan sát STATUS=INACTIVE và xác nhận session vẫn chiếm slot. Đóng connection và chờ pool/server cleanup; kiểm tra count giảm.

### 22.5. Quan sát transaction mở

Trong lab, bắt đầu transaction, update row rồi chưa commit. Quan sát session INACTIVE/ACTIVE và V$TRANSACTION. Rollback, xác nhận lock/transaction được giải phóng.

### 22.6. So sánh dedicated và shared server

Nếu lab được cấu hình cả hai mode, kết nối qua service dedicated và shared. So sánh số session, process, server mode và throughput. Không thay đổi production service chỉ để làm bài lab.

## 23. Lab: tái hiện giới hạn trên instance dùng riêng

### 23.1. Chuẩn bị instance

Dùng disposable Oracle instance với PROCESSES/SESSIONS nhỏ đã được đặt trong cấu hình lab. Lập kế hoạch startup/shutdown và đảm bảo có đường truy cập DBA. Không hạ parameter trên instance đang dùng chung.

### 23.2. Test ORA-00018

Tạo nhiều client connection và giữ mở cho tới khi session limit lab đạt. Ghi nhận error code, V$RESOURCE_LIMIT, V$SESSION và pool behavior. Dừng tạo connection ngay khi lỗi xuất hiện.

### 23.3. Test ORA-00020

Trong dedicated server lab, đặt process budget thấp có chủ đích, tính cả background process. Mở connection từ từ và quan sát V$PROCESS/V$RESOURCE_LIMIT cho tới khi process creation thất bại. Không giả định ORA-00020 sẽ xuất hiện trước ORA-00018; resource nào chạm trước tùy cấu hình.

### 23.4. Cleanup

Đóng toàn bộ client connections, rollback transaction lab, xác nhận session/process count giảm. Nếu instance cần restart để phục hồi parameter/test state, làm theo runbook lab.

### 23.5. Ghi bằng chứng

Lưu:
- Database/instance/version.
- PROCESSES/SESSIONS.
- Server mode.
- Số connection mở.
- Resource limit trước/trong/sau test.
- ORA code và exception chain.
- Pool behavior và cleanup time.

## 24. Checklist vận hành và capacity review

### 24.1. Trước khi triển khai ứng dụng

- [ ] Tổng pool max size được tính trên số replica tối đa.
- [ ] Có tính rolling deployment/autoscaling surge.
- [ ] Có headroom cho DBA, monitoring, scheduler và background.
- [ ] Pool có acquisition timeout và bounded connection creation.
- [ ] Connection/statement/result set được đóng đúng lifecycle.
- [ ] Transaction cleanup hoạt động khi exception/cancel.
- [ ] Retry có backoff/jitter và không retry ORA-00018/ORA-00020 vô hạn.
- [ ] Module/action/client identifier được gán phù hợp để điều tra.

### 24.2. Review database capacity

- [ ] PROCESSES/SESSIONS hiệu lực được ghi nhận.
- [ ] V$RESOURCE_LIMIT current/max được lưu theo thời gian.
- [ ] Peak session/process theo instance đã được đo.
- [ ] PX/job/background process demand đã được tính.
- [ ] OS process/task/memory limits có headroom.
- [ ] RAC failover capacity được tính theo instance còn lại.
- [ ] PDB/service distribution được theo dõi.
- [ ] Có emergency access/runbook.

### 24.3. Khi có ORA-00018/ORA-00020

- [ ] Xác định đúng resource và instance.
- [ ] Thu thập alert/listener/application logs.
- [ ] Xác định top session/process source.
- [ ] Kiểm tra pool leak, transaction và retry storm.
- [ ] Chỉ terminate session đã xác minh.
- [ ] Không OS kill Oracle background/server process tùy tiện.
- [ ] Xác nhận resource count và connection recovery.
- [ ] Ghi root cause và action item.

### 24.4. Sau thay đổi parameter

- [ ] Backup SPFILE/PFILE.
- [ ] Đánh giá memory/OS capacity.
- [ ] Có maintenance/change plan và rollback.
- [ ] Restart đúng instance/topology.
- [ ] Xác nhận PROCESSES/SESSIONS có hiệu lực.
- [ ] Kiểm tra listener/service/connection pool.
- [ ] Theo dõi peak utilization sau deploy.

## 25. Câu hỏi tự kiểm tra

1. Session khác process như thế nào?
2. Client process khác Oracle server process ra sao?
3. Vì sao một INACTIVE session vẫn tiêu thụ session slot?
4. Dedicated server liên hệ session/process như thế nào?
5. Shared server thay đổi quan hệ session/process ra sao?
6. ORA-00018 biểu thị resource nào đã đạt giới hạn?
7. ORA-00020 biểu thị resource nào đã đạt giới hạn?
8. Vì sao V$SESSION count không bằng V$PROCESS count?
9. V$RESOURCE_LIMIT current_utilization và max_utilization khác nhau thế nào?
10. Vì sao phải xem GV$RESOURCE_LIMIT trong RAC?
11. PROCESSES thay đổi có cần restart không?
12. SESSIONS mặc định được suy ra từ PROCESSES như thế nào?
13. Vì sao không đặt SESSIONS bằng tổng pool max?
14. Parallel execution có thể làm process count tăng ra sao?
15. Scheduler job có thể ảnh hưởng process limit thế nào?
16. Làm sao phát hiện session INACTIVE có transaction mở?
17. Vì sao không kill mọi INACTIVE session?
18. Khi nào ORA-02391 khác ORA-00018?
19. ORA-12516/12519/12520 khác ORA-00020 ra sao?
20. Pool max size cần tính trên số replica nào?
21. Vì sao rolling deployment có thể tăng session peak tạm thời?
22. Làm thế nào giảm login storm sau failover?
23. Khi nào cần tăng PROCESSES?
24. Vì sao cần kiểm tra OS process/memory limits?
25. Cách xử lý session trong RAC cần thêm thông tin nào?
26. PDB có process pool OS độc lập với CDB không?
27. Vì sao tăng pool size có thể làm database chậm hơn?
28. Khi nào nên dùng shared server hoặc DRCP?
29. Vì sao không OS kill Oracle process như cách cleanup thông thường?
30. Lab nào chứng minh được ứng dụng cleanup connection sau exception?

## 26. Mô hình ghi nhớ

```text
APPLICATION / CONNECTION POOLS
       |
       +-- Pool max × replica count
       +-- Batch / monitoring / admin
       +-- Retry / reconnect burst
       |
       v
ORACLE DATABASE INSTANCE
       |
       +-- SESSIONS
       |      ORA-00018
       |      V$SESSION / V$RESOURCE_LIMIT
       |
       +-- PROCESSES
       |      ORA-00020
       |      V$PROCESS / V$RESOURCE_LIMIT
       |
       +-- Background / PX / Scheduler / DB links
       |
       v
CAPACITY AND DIAGNOSTICS
       |
       +-- V$ / GV$ per instance
       +-- Session source and transaction state
       +-- OS process / memory limits
       +-- Listener and service state
       |
       v
REMEDIATION
       |
       +-- Stop connection storm
       +-- Fix pool/leak/transaction
       +-- Safely end confirmed sessions
       +-- Increase PROCESSES with restart plan
       +-- Verify recovery and headroom
```

**Điểm cần nhớ:** ORA-00018 là giới hạn session; ORA-00020 là giới hạn Oracle process. V$RESOURCE_LIMIT cho biết mức sử dụng và high-water mark; V$SESSION cho biết ai đang đăng nhập, V$PROCESS cho biết process của instance. Hãy cộng pool trên toàn bộ replica và workload, giữ headroom, sửa leak/retry storm trước khi tăng parameter, và chỉ terminate session sau khi hiểu transaction/tác động.
