# Session/process limit, số kết nối và giới hạn connection pool

## 1. Phân biệt process, session và connection

Khi một ứng dụng kết nối Oracle Database, các khái niệm process, session và connection thường được nhắc cùng nhau nhưng chúng không đồng nghĩa.

- **Client connection** là kết nối mạng từ ứng dụng hoặc connection pool tới Oracle listener/database service. Nó là kênh giao tiếp mà client sử dụng.
- **Database session** là ngữ cảnh làm việc của một client bên trong Oracle. Session giữ thông tin như user, schema hiện tại, trạng thái transaction, session parameters và các thuộc tính thực thi.
- **Database process** là tiến trình phía máy chủ thực hiện công việc cho database. Trong dedicated server architecture, mỗi session được phục vụ bởi một server process trong thời gian gắn kết thông thường.

Quan hệ giữa chúng phụ thuộc kiến trúc kết nối:

```text
Dedicated server:
Client connection A  <->  Oracle session A  <->  Server process A
Client connection B  <->  Oracle session B  <->  Server process B

Shared server:
Client connections / sessions
          |
          v
       Dispatcher
          |
          v
 Shared server processes (được dùng chung)

Application connection pool:
Application requests -> borrow/release logical connection
                              |
                              v
                     physical DB connections
                              |
                              v
                      Oracle sessions
```

Với dedicated server, số server process thường tăng gần tương ứng với số session dedicated đang được phục vụ. Với shared server, nhiều session có thể luân phiên dùng một nhóm shared server process. Với Database Resident Connection Pooling (DRCP), Oracle còn có thể quản lý một pool server-side để tái sử dụng database server process và session cho nhiều client connection.

Do đó, không nên dùng một con số “connection” duy nhất để suy ra chính xác số session hoặc process trong mọi kiến trúc. Khi điều tra giới hạn, cần biết ứng dụng đang dùng dedicated, shared server hay DRCP, đồng thời kiểm tra session và process trong database.

## 2. PROCESSES và SESSIONS trong Oracle

### 2.1. PROCESSES

`PROCESSES` quy định số lượng tối đa các operating-system user processes có thể đồng thời kết nối tới Oracle instance. Tham số này bao gồm các process nền của Oracle và các process phía server cần cho hoạt động database, không chỉ riêng các kết nối của ứng dụng.

Ví dụ, nếu đặt `PROCESSES=300`, không thể hiểu rằng ứng dụng chắc chắn có thể mở 300 dedicated connections. Một phần năng lực process được sử dụng bởi background processes, job queue, parallel execution và các thành phần nội bộ khác. Cần dự trù headroom cho hoạt động vận hành và tải tăng đột biến.

Xem giá trị hiện tại:

```sql
SHOW PARAMETER processes;

SELECT name, value, isdefault, issys_modifiable
FROM v$parameter
WHERE name = 'processes';
```

`PROCESSES` là tham số khởi tạo tĩnh trong các phiên bản Oracle thông dụng như 19c; thay đổi giá trị cần ghi vào SPFILE và khởi động lại instance để có hiệu lực. Hãy xác nhận trạng thái tham số và quy trình restart của phiên bản/môi trường cụ thể trước khi thay đổi.

### 2.2. SESSIONS

`SESSIONS` giới hạn số session có thể tồn tại trong instance. Session bao gồm user session và các session nội bộ/không phải user session được Oracle quản lý. Không phải toàn bộ số session đều là request đang xử lý tại thời điểm quan sát; nhiều session có thể ở trạng thái `INACTIVE` nhưng vẫn giữ tài nguyên và vẫn tính vào giới hạn.

Trong Oracle 19c, giá trị mặc định của `SESSIONS` được tính từ `PROCESSES` theo công thức:

\[
SESSIONS = (1.5 \times PROCESSES) + 22
\]

Đây là giá trị mặc định được suy ra khi không đặt riêng; nó không phải khuyến nghị rằng ứng dụng nên sử dụng hết số session đó. Nếu đặt `SESSIONS` thủ công, phải bảo đảm phù hợp với số process, kiểu server và nhu cầu thực tế. `SESSIONS` là giới hạn tài nguyên ở cấp instance; trong RAC, cần quan sát từng instance và phân bố kết nối theo service.

Xem giá trị hiện tại:

```sql
SHOW PARAMETER sessions;

SELECT name, value, isdefault, issys_modifiable
FROM v$parameter
WHERE name IN ('processes', 'sessions');
```

Không nên thay đổi `PROCESSES` hoặc `SESSIONS` chỉ để xử lý một lỗi pool timeout. Trước hết cần xác định giới hạn nào đang bị chạm tới và thành phần nào đang chiếm tài nguyên.

### 2.3. TRANSACTIONS

`TRANSACTIONS` quy định số transaction đồng thời tối đa mà instance có thể hỗ trợ. Nếu không đặt riêng, Oracle tính giá trị mặc định dựa trên `SESSIONS` (thông thường khoảng `1.1 * SESSIONS`). Đây là giới hạn khác với số connection/session.

Một session có thể không có transaction đang mở; ngược lại, một workload có thể tạo nhiều transaction đồng thời và chịu giới hạn transaction riêng. Khi điều tra `ORA-01574` hoặc vấn đề transaction, cần kiểm tra `TRANSACTIONS` và `V$RESOURCE_LIMIT`, không quy tất cả về connection pool.

## 3. Kiến trúc kết nối ảnh hưởng đến số process/session

### 3.1. Dedicated server

Dedicated server là mô hình phổ biến cho ứng dụng OLTP: một client connection được gắn với một server process phục vụ session tương ứng. Mô hình này đơn giản, phù hợp với workload cần trạng thái session riêng và được nhiều driver/pool sử dụng mặc định.

Ưu điểm là mỗi session có process phục vụ riêng, luồng thực thi tương đối dễ hiểu và cô lập. Nhược điểm là khi có rất nhiều connection nhàn rỗi, số server process và lượng bộ nhớ liên quan vẫn có thể tăng đáng kể.

Một connection pool phía ứng dụng giúp giới hạn số dedicated connections được mở đồng thời. Thay vì mỗi request web tạo một connection mới, ứng dụng mượn connection có sẵn, chạy SQL/transaction rồi trả lại pool.

### 3.2. Shared server

Shared server cho phép nhiều session dùng chung một nhóm server process. Client thường kết nối tới dispatcher; dispatcher chuyển yêu cầu đến shared server process rảnh và trả kết quả qua dispatcher.

Mô hình này có thể giảm số server process cần thiết khi có nhiều session kết nối nhưng phần lớn thời gian nhàn rỗi. Tuy nhiên, nó thêm lớp điều phối và không phải lựa chọn phù hợp cho mọi workload. Các tác vụ dài, thao tác cần server process chuyên dụng hoặc đặc điểm ứng dụng có thể khiến dedicated server phù hợp hơn.

Không được giả định `SESSIONS` giảm theo cùng tỷ lệ với shared server process: shared server chủ yếu thay đổi quan hệ giữa session và server process; session vẫn tồn tại và vẫn tiêu thụ tài nguyên session.

### 3.3. Database Resident Connection Pooling (DRCP)

DRCP là connection pool ở phía database. Thay vì mỗi client connection giữ một server process/session chuyên dụng trong toàn bộ vòng đời kết nối, DRCP cho phép client mượn server-side pooled server để thực hiện công việc rồi trả lại pool.

DRCP có thể hữu ích cho ứng dụng có nhiều client process hoặc môi trường cần giảm số server process được giữ lâu dài. Việc sử dụng cần cấu hình pool, connection string và driver hỗ trợ; cũng phải xem xét cách quản lý session state, transaction và connection class để các lần mượn trả không làm rò rỉ trạng thái giữa người dùng.

DRCP không thay thế connection pool phía ứng dụng trong mọi kiến trúc. Hai lớp có thể được dùng cùng nhau: application pool quản lý kết nối từ ứng dụng, còn DRCP quản lý server-side pooled sessions/processes. Cần thiết kế tổng thể và đo số session/process thực tế.

### 3.4. RAC và service

Trong Oracle Real Application Clusters (RAC), mỗi instance có giới hạn process/session và resource usage riêng. Kết nối được phân phối theo service, load balancing và cấu hình client. Nếu một service dồn nhiều kết nối về một instance, instance đó có thể chạm giới hạn dù instance khác còn dư năng lực.

Với RAC, ưu tiên kiểm tra `GV$RESOURCE_LIMIT`, `GV$SESSION` và `GV$PROCESS`, có thêm `INST_ID` để thấy phân bố. Không chỉ nhìn tổng số connection từ phía ứng dụng hoặc một instance.

## 4. Connection pool phía ứng dụng

### 4.1. Connection pool giải quyết vấn đề gì?

Mở kết nối database có chi phí: thiết lập TCP, xác thực, tạo session, khởi tạo trạng thái và cấp phát tài nguyên server. Nếu mỗi HTTP request đều mở rồi đóng một kết nối mới, ứng dụng có thể tạo nhiều logon/logoff, tăng CPU và gây áp lực lên Oracle.

Connection pool giữ một số physical connection mở sẵn. Khi request cần truy cập database, nó mượn một connection, thực hiện thao tác, commit/rollback và trả connection về pool.

```text
HTTP request
     |
     v
Borrow connection from pool
     |
     v
Execute SQL / transaction
     |
     v
Commit or rollback
     |
     v
Return connection to pool
```

Pool tạo giới hạn concurrency ở tầng ứng dụng và giảm chi phí tạo kết nối. Nó không tự làm câu SQL nhanh hơn; nếu truy vấn chậm hoặc transaction giữ connection quá lâu, pool vẫn có thể bị cạn.

### 4.2. Các thông số phổ biến

Tên chính xác tùy thư viện, nhưng thường có các khái niệm sau:

| Thông số | Ý nghĩa |
|---|---|
| Minimum/Initial pool size | Số connection tối thiểu hoặc số connection tạo lúc khởi động |
| Maximum pool size | Số physical connection tối đa mà một pool được phép giữ |
| Connection timeout / borrow timeout | Thời gian request chờ mượn được connection trước khi thất bại |
| Idle timeout | Thời gian connection nhàn rỗi trước khi pool có thể đóng bớt |
| Max lifetime | Tuổi thọ tối đa của physical connection trước khi pool thay mới |
| Validation / keepalive | Cách kiểm tra hoặc duy trì connection còn hoạt động |
| Leak detection | Phát hiện connection được mượn nhưng không được trả lại đúng hạn |

Không phải mọi pool đều có cùng cách diễn giải hoặc đơn vị. Hãy đọc tài liệu của driver/pool cụ thể, ví dụ Oracle Universal Connection Pool (UCP), HikariCP, WebLogic JDBC Data Source hoặc pool của framework.

### 4.3. Giới hạn tối đa là theo từng pool/từng process ứng dụng

Một lỗi cấu hình phổ biến là chỉ nhìn `maximumPoolSize` của một instance ứng dụng. Nếu ứng dụng chạy nhiều replica, mỗi replica thường có pool riêng.

Ví dụ:

```text
4 application replicas
Mỗi replica có maximumPoolSize = 30

Tổng kết nối tối đa từ ứng dụng này = 4 x 30 = 120
```

Nếu còn batch jobs, scheduler, reporting, monitoring, migration tools và kết nối DBA, tổng nhu cầu database có thể cao hơn nhiều. Khi autoscaling tăng số replica, tổng connection tối đa cũng tăng theo.

Với nhiều dịch vụ:

\[
Pool\ connections_{max} = \sum_{i=1}^{n}(replicas_i \times maxPool_i)
\]

Đây là số connection tối đa theo cấu hình, không phải số kết nối luôn được mở. Tuy nhiên, để lập capacity plan, cần giả định các pool có thể đồng thời đạt gần mức tối đa trong tình huống tải cao hoặc khi reconnect.

## 5. Tính ngân sách kết nối và chọn max pool size

### 5.1. Không đặt max pool size bằng PROCESSES

Giả sử `PROCESSES=400`. Không thể cấu hình một ứng dụng có pool tối đa 400 connection chỉ vì con số này bằng process limit. Oracle cần process cho background, job queue, parallel execution, monitoring, DBA và các ứng dụng khác. Trong dedicated server, mỗi connection còn có thể cần một server process.

Một capacity budget cần tính:

1. Process/session nền và phần dự phòng cho hoạt động Oracle.
2. Pool của tất cả ứng dụng và tất cả replica.
3. Batch, scheduler, ETL, reporting và integration jobs.
4. Monitoring, backup, DBA, deployment và kết nối khẩn cấp.
5. Tải tăng đột biến, rolling deployment và autoscaling.
6. Kết nối có thể được phân bố không đều giữa các RAC instance.

### 5.2. Ví dụ tính ngân sách

Giả sử database có giới hạn `PROCESSES=400`. Sau khi đo và dự trù cho background/internal processes, vận hành, batch và headroom, nhóm DBA chỉ dành tối đa 220 dedicated connections cho các application pools.

| Ứng dụng | Replica | Max pool mỗi replica | Tổng tối đa |
|---|---:|---:|---:|
| API A | 3 | 30 | 90 |
| API B | 2 | 25 | 50 |
| Worker | 2 | 20 | 40 |
| Reporting | 1 | 15 | 15 |
| **Tổng** | | | **195** |

Tổng pool tối đa là 195, thấp hơn ngân sách 220, còn 25 vị trí dự phòng trong phần ngân sách application pool. Các con số chỉ minh họa; capacity thực tế phải dựa trên process/session high-water mark, workload, bộ nhớ, CPU, I/O và yêu cầu SLA.

### 5.3. Pool quá lớn cũng có thể làm database chậm hơn

Tăng pool size không đồng nghĩa tăng throughput. Khi có quá nhiều session đồng thời:

- Nhiều SQL tranh chấp CPU, buffer cache, I/O và latch/mutex.
- Số process và bộ nhớ server tăng.
- Transaction cạnh tranh lock và tài nguyên.
- Nhiều request có thể cùng chờ một tài nguyên, khiến latency tăng.
- Logon storm và reconnect đồng loạt có thể tạo tải đột biến.

Hãy chọn max pool size theo mức concurrency mà database có thể xử lý hiệu quả. Nếu ứng dụng nhận nhiều request hơn năng lực DB, pool nhỏ hơn kết hợp hàng đợi/backpressure có thể giữ hệ thống ổn định hơn một pool rất lớn.

### 5.4. Pool sizing dựa trên thời gian giữ connection

Một cách ước lượng ban đầu là dùng Little's Law:

\[
Concurrent\ connections \approx Throughput \times Average\ connection\ hold\ time
\]

Ví dụ, workload cần 200 request database mỗi giây và mỗi request giữ connection trung bình 0,05 giây:

\[
200 \times 0.05 = 10
\]

Khoảng 10 connection đồng thời là mức trung bình lý thuyết để phục vụ throughput đó trong điều kiện ổn định. Khi sizing thật cần thêm độ biến động, percentile latency, transaction dài, thời gian chờ lock và headroom. Không nên dùng công thức này như một giới hạn tối đa tuyệt đối.

## 6. Giới hạn theo user: PROFILE và SESSIONS_PER_USER

Ngoài giới hạn instance, Oracle có thể giới hạn số session đồng thời của một database user thông qua profile.

### 6.1. Xem profile của user

```sql
SELECT username, profile, account_status
FROM dba_users
WHERE username = 'APP_USER';

SELECT profile, resource_name, limit
FROM dba_profiles
WHERE profile = 'APP_PROFILE'
  AND resource_name IN (
    'SESSIONS_PER_USER',
    'IDLE_TIME',
    'CONNECT_TIME'
  );
```

`SESSIONS_PER_USER` giới hạn số session đồng thời của user được gán profile. Nếu đặt giá trị thấp hơn nhu cầu của toàn bộ pool và các job dùng chung account, ứng dụng có thể không mở thêm session dù instance vẫn còn capacity.

### 6.2. Resource limit phải được bật

Các resource limits như `SESSIONS_PER_USER`, `IDLE_TIME` và `CONNECT_TIME` được áp dụng khi `RESOURCE_LIMIT=TRUE` ở cấp database. Password limits có cơ chế áp dụng riêng. Kiểm tra:

```sql
SHOW PARAMETER resource_limit;

SELECT name, value
FROM v$parameter
WHERE name = 'resource_limit';
```

Không nên bật/tắt `RESOURCE_LIMIT` tùy tiện trong production; thay đổi ảnh hưởng cách Oracle thực thi các resource limit được gán qua profile. Hãy phối hợp với DBA và kiểm tra chính sách user/service.

### 6.3. IDLE_TIME và connection pool

`IDLE_TIME` giới hạn thời gian session không hoạt động. Nếu pool giữ connection nhàn rỗi lâu hơn giới hạn profile, Oracle có thể kết thúc session. Pool phía ứng dụng có thể vẫn giữ một đối tượng connection cũ và chỉ phát hiện lỗi khi request tiếp theo mượn nó.

Vì vậy, cần phối hợp timeout của database profile với idle timeout, validation và keepalive của pool. Không đặt database `IDLE_TIME` ngắn hơn nhiều so với vòng đời connection nhàn rỗi của pool mà không có cơ chế phát hiện connection đã bị server ngắt.

## 7. Theo dõi process, session và resource limit

### 7.1. V$RESOURCE_LIMIT

`V$RESOURCE_LIMIT` cho biết mức sử dụng hiện tại, high-water mark và giới hạn của các tài nguyên instance:

```sql
SELECT resource_name,
       current_utilization,
       max_utilization,
       limit_value
FROM v$resource_limit
WHERE resource_name IN ('processes', 'sessions', 'transactions')
ORDER BY resource_name;
```

Ý nghĩa:

- `CURRENT_UTILIZATION`: số lượng tài nguyên đang được sử dụng tại thời điểm xem.
- `MAX_UTILIZATION`: mức sử dụng cao nhất kể từ khi instance khởi động hoặc kể từ lần reset thống kê phù hợp.
- `LIMIT_VALUE`: giới hạn được cấu hình/áp dụng cho tài nguyên.

Nếu `MAX_UTILIZATION` thường xuyên tiến sát `LIMIT_VALUE`, cần điều tra và lập capacity plan trước khi sự cố xảy ra. High-water mark thấp ở thời điểm hiện tại không loại trừ việc hệ thống từng chạm giới hạn trong giờ cao điểm.

Trong RAC:

```sql
SELECT inst_id,
       resource_name,
       current_utilization,
       max_utilization,
       limit_value
FROM gv$resource_limit
WHERE resource_name IN ('processes', 'sessions', 'transactions')
ORDER BY inst_id, resource_name;
```

### 7.2. Đếm session theo trạng thái và user

```sql
SELECT username,
       status,
       server,
       COUNT(*) AS session_count
FROM v$session
WHERE type = 'USER'
GROUP BY username, status, server
ORDER BY session_count DESC;
```

`STATUS='ACTIVE'` nghĩa là session đang hoạt động theo trạng thái Oracle ghi nhận; `INACTIVE` nghĩa là session hiện không thực thi call. Session inactive vẫn chiếm session slot và có thể giữ state/tài nguyên. Pool thường giữ nhiều session inactive trong thời gian chờ request tiếp theo.

Xem tổng quan theo chương trình và máy khách:

```sql
SELECT username,
       machine,
       program,
       module,
       service_name,
       status,
       COUNT(*) AS session_count
FROM v$session
WHERE type = 'USER'
GROUP BY username, machine, program, module, service_name, status
ORDER BY session_count DESC;
```

Trong RAC, dùng `GV$SESSION` và thêm `INST_ID`. Có thể cần quyền truy cập dynamic performance views hoặc quyền catalog phù hợp.

### 7.3. Đếm process

```sql
SELECT COUNT(*) AS process_count
FROM v$process;

SELECT pname, COUNT(*) AS process_count
FROM v$process
GROUP BY pname
ORDER BY process_count DESC;
```

`V$PROCESS` cho biết các process Oracle đang quản lý. Không nên so sánh số dòng `V$PROCESS` với số user sessions rồi kết luận một-một trong mọi kiến trúc, đặc biệt khi dùng shared server hoặc DRCP.

### 7.4. Kiểm tra thông số cấu hình và giới hạn user

```sql
SELECT name, value
FROM v$parameter
WHERE name IN (
  'processes',
  'sessions',
  'transactions',
  'resource_limit',
  'dispatchers',
  'shared_servers'
)
ORDER BY name;
```

Nếu dùng profile, đối chiếu `DBA_USERS` và `DBA_PROFILES`. Nếu dùng RAC, DRCP hoặc shared server, kiểm tra các view chuyên biệt tương ứng và trạng thái service/listener.

## 8. Nhận biết lỗi và xác định lớp bị cạn

| Triệu chứng/lỗi | Ý nghĩa thường gặp | Hướng điều tra |
|---|---|---|
| `ORA-00020: maximum number of processes exceeded` | Instance chạm giới hạn `PROCESSES` | `V$RESOURCE_LIMIT`, `V$PROCESS`, background/job/parallel processes và pool size |
| `ORA-00018: maximum number of sessions exceeded` | Instance chạm giới hạn `SESSIONS` | `V$RESOURCE_LIMIT`, `V$SESSION`, session inactive và các user/service |
| `ORA-00019: maximum number of session licenses exceeded` | Giới hạn session license legacy được cấu hình/áp dụng | Kiểm tra cấu hình licensing liên quan và entitlement thực tế |
| `ORA-02391: exceeded simultaneous SESSIONS_PER_USER limit` | User chạm giới hạn session trong profile | `DBA_USERS`, `DBA_PROFILES`, các pool/job dùng chung user |
| `ORA-12516` / `ORA-12519` | Listener không tìm được handler/service handler phù hợp tại thời điểm kết nối | Service registration, dispatcher/dedicated handler, process/session capacity và trạng thái listener |
| Pool borrow timeout | Ứng dụng không lấy được connection từ pool trong thời gian cho phép | Pool active/idle/pending, connection leak, transaction dài, DB latency và pool max |

Một pool timeout không nhất thiết có nghĩa Oracle đã hết `PROCESSES` hoặc `SESSIONS`. Có thể pool đã dùng hết connection do request giữ connection quá lâu, query chậm, lock wait hoặc connection leak trong khi database vẫn còn capacity. Ngược lại, Oracle chạm giới hạn có thể khiến pool không tạo/thay thế được physical connection.

Không xử lý lỗi bằng cách tăng pool size ngay lập tức. Trước hết xác định lỗi phát sinh ở application pool, listener, user profile, `SESSIONS` hay `PROCESSES`.

## 9. Thiết kế pool để tránh cạn connection

### 9.1. Giữ transaction ngắn và trả connection đúng cách

Ứng dụng nên mượn connection sát thời điểm cần truy cập DB, hoàn tất transaction rồi trả connection về pool. Tránh giữ connection trong lúc gọi HTTP service khác, chờ người dùng hoặc thực hiện xử lý CPU dài.

Trong Java, nên dùng `try-with-resources` hoặc transaction management của framework để bảo đảm connection được trả về pool kể cả khi có exception:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    try {
        // Execute SQL and perform database work.
        connection.commit();
    } catch (SQLException ex) {
        connection.rollback();
        throw ex;
    }
}
```

Khi dùng Spring transaction manager, không tự đóng hoặc commit connection mà framework đang quản lý. Ví dụ trên chỉ minh họa JDBC thuần.

### 9.2. Thiết lập timeout ở nhiều lớp

Cần phân biệt:

- Pool acquisition timeout: thời gian chờ mượn connection.
- SQL/query timeout: thời gian chờ câu SQL.
- Transaction timeout: thời gian tối đa cho transaction.
- Network/socket timeout: thời gian chờ I/O mạng.
- Database profile `IDLE_TIME`/`CONNECT_TIME`: giới hạn session theo profile.
- Pool idle timeout/max lifetime: vòng đời physical connection trong pool.

Các timeout cần phối hợp để request lỗi có kiểm soát và connection được trả về. Một query timeout không tự động bảo đảm transaction đã rollback hoặc connection đã được trả pool; ứng dụng cần xử lý exception và cleanup đúng cách.

### 9.3. Phát hiện connection leak

Connection leak xảy ra khi code mượn connection nhưng không trả lại pool. Dấu hiệu gồm active connections tăng dần, idle connections gần 0, pending borrowers tăng và pool timeout xuất hiện dù throughput không tăng tương ứng.

Bật leak detection theo khả năng của pool ở ngưỡng hợp lý; log stack trace để tìm vị trí mượn connection. Leak detection là công cụ chẩn đoán, không phải cơ chế tự sửa mọi đường code.

### 9.4. Tránh logon storm

Khi database restart hoặc network gián đoạn, nhiều application replica có thể cùng lúc tạo lại toàn bộ pool. Điều này tạo logon storm ngay khi database vừa khởi động.

Có thể giảm rủi ro bằng:

- Cấu hình pool initialization và minimum idle hợp lý.
- Dùng retry có exponential backoff và jitter.
- Giới hạn tốc độ reconnect đồng thời.
- Rolling restart/rolling deployment thay vì khởi động mọi replica cùng lúc.
- Theo dõi số connection mới mỗi giây, logon rate và process/session high-water mark.

## 10. Quy trình capacity planning và xử lý sự cố

1. Xác định kiến trúc: dedicated, shared server hay DRCP; single instance hay RAC; ứng dụng có bao nhiêu replica và bao nhiêu pool.
2. Thu thập `PROCESSES`, `SESSIONS`, `TRANSACTIONS`, `V$RESOURCE_LIMIT` và high-water mark ở giờ cao điểm.
3. Đếm session theo user, service, machine, program, module và trạng thái; phân biệt user/background session.
4. Đếm process và xác định nhóm background, job queue, parallel execution, server process.
5. Tính tổng max pool theo tất cả replica/service; cộng batch, reporting, monitoring và DBA connections.
6. Kiểm tra profile `SESSIONS_PER_USER`, `IDLE_TIME`, `CONNECT_TIME` và `RESOURCE_LIMIT`.
7. Đối chiếu lỗi thực tế: pool timeout, `ORA-00018`, `ORA-00020`, `ORA-02391` hay lỗi listener.
8. Nếu cần tăng giới hạn database, đánh giá bộ nhớ, CPU, OS process limit, cấu hình listener, workload và thời gian restart; không chỉ tăng tham số trong isolation.
9. Nếu pool cạn nhưng DB còn capacity, tìm query chậm, transaction dài, lock wait, leak hoặc timeout chưa hợp lý trước khi tăng max pool.
10. Thiết lập cảnh báo theo tỷ lệ sử dụng và high-water mark, giữ headroom cho deployment, batch và hoạt động DBA.

## 11. Nguyên tắc vận hành

- `PROCESSES` là giới hạn process của instance; `SESSIONS` là giới hạn session. Hai tham số liên quan nhưng không thay thế nhau.
- Dedicated server thường có quan hệ gần một session với một server process; shared server và DRCP thay đổi quan hệ này.
- Application pool giới hạn số physical connection theo từng pool/replica; tổng số phải được tính trên toàn bộ ứng dụng và workload.
- Session `INACTIVE` vẫn có thể chiếm session slot; không đồng nghĩa đã được giải phóng.
- Pool lớn không luôn làm tăng throughput; quá nhiều concurrent sessions có thể làm database chậm hơn.
- `SESSIONS_PER_USER` và các resource profile limits có thể chặn user trước khi instance hết capacity.
- Chẩn đoán bằng `V$RESOURCE_LIMIT`, `V$SESSION`, `V$PROCESS`, `DBA_PROFILES` và số liệu pool trước khi thay đổi giới hạn.
- Tăng `PROCESSES` cần đánh giá tài nguyên hệ điều hành và thường cần restart instance; thay đổi phải theo kế hoạch vận hành.

## Tài liệu Oracle tham khảo

- [Oracle Database 19c Reference — PROCESSES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/PROCESSES.html)
- [Oracle Database 19c Reference — SESSIONS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/SESSIONS.html)
- [Oracle Database 19c Reference — V$RESOURCE_LIMIT](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-RESOURCE_LIMIT.html)
- [Oracle Database 19c Administrator's Guide — Configuring and Managing the Database](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/)
- [Oracle Database 19c Net Services Administrator's Guide — Dedicated and Shared Server](https://docs.oracle.com/en/database/oracle/oracle-database/19/netag/)
- [Oracle Database 19c Database Reference — DBA_PROFILES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_PROFILES.html)
