# ORA-03113, ORA-03135, ORA-17002 và mất kết nối từ ứng dụng

Khi ứng dụng Spring Boot hoặc một Java service kết nối Oracle Database, lỗi mất kết nối thường xuất hiện dưới nhiều hình thức: ORA-03113, ORA-03135, ORA-17002, Socket read timed out, Connection reset hoặc The Network Adapter could not establish the connection. Những thông báo này có liên quan nhưng không đồng nghĩa và không chỉ ra cùng một nguyên nhân.

Muốn xử lý đúng, trước hết phải xác định **kết nối chưa từng được thiết lập, kết nối bị đứt trong lúc đang sử dụng, hay connection trong pool đã chết sau một khoảng idle**. Sau đó lần theo exception chain của JDBC và đối chiếu thời điểm lỗi với log ứng dụng, network path, Oracle Listener, server process và database alert log.

| Mã/lỗi | Nơi thường nhìn thấy | Ý nghĩa khái quát |
|---|---|---|
| ORA-03113 | Oracle Net/client hoặc server log | Kênh giao tiếp kết thúc bất ngờ |
| ORA-03135 | Oracle Net/client hoặc server log | Mất liên lạc với peer trong một phiên đã kết nối |
| ORA-17002 | Oracle JDBC driver | JDBC báo lỗi I/O; cần đọc nguyên nhân gốc trong exception chain |
| Socket read timed out | Java/network layer | Không nhận dữ liệu trong thời hạn chờ |
| Connection reset / Broken pipe | TCP/OS/network layer | Socket bị đóng hoặc reset ở một đầu/thiết bị trung gian |

Không kết luận database bị crash chỉ từ ORA-03113; cũng không kết luận firewall là nguyên nhân chỉ từ ORA-03135. Một lỗi JDBC có thể bọc lỗi Oracle Net, và một lỗi Oracle Net có thể do server process, listener, mạng, proxy hoặc client timeout.

## 1. Phân loại sự cố theo thời điểm

### 1.1. Lỗi ngay khi mở kết nối

Ứng dụng không lấy được connection mới từ Oracle. Thường gặp:

- ORA-17002 kèm The Network Adapter could not establish the connection.
- ORA-12541: TNS:no listener.
- ORA-12514: listener does not currently know of service requested.
- ORA-12543: destination host unreachable.
- Connection timed out hoặc Connection refused.
- TLS handshake/certificate error khi dùng TCPS.

Hướng điều tra ưu tiên:

1. DNS/hostname và địa chỉ đích.
2. TCP reachability tới host/port.
3. Listener có chạy và lắng nghe đúng interface/port không.
4. Service name có đăng ký trên listener không.
5. JDBC URL, wallet/TLS và authentication.
6. Network policy, firewall, NAT hoặc load balancer.

Nếu chưa có TCP connection tới listener, việc kiểm tra SQL trong database thường chưa phải bước đầu tiên.

### 1.2. Kết nối đang hoạt động bị đứt

Ứng dụng đã login và thực hiện query/DML, sau đó socket bị đóng. Có thể thấy:

- ORA-03113: end-of-file on communication channel.
- ORA-03135: connection lost contact.
- ORA-17002 kèm Socket read timed out, Connection reset hoặc Socket closed.
- SQLRecoverableException hoặc SQLException với vendor code tương ứng.

Hướng điều tra:

- Alert log và trace của server process tại đúng timestamp.
- Listener log nếu lỗi trùng thời điểm tạo/reconnect session.
- OS log, process termination, memory pressure và database instance events.
- Firewall/NAT/proxy idle timeout hoặc network interruption.
- JDBC read timeout và application cancellation.
- RAC node/service failover hoặc Data Guard role transition.

### 1.3. Chỉ lỗi sau một khoảng idle

Nếu query chạy bình thường nhưng connection trong pool lỗi sau 15, 30 hoặc 60 phút không hoạt động, hãy nghi ngờ idle timeout:

- Firewall hoặc NAT xóa TCP state.
- Load balancer/proxy đóng kết nối nhàn rỗi.
- Database/profile/resource manager có tác động tới session.
- Server/client TCP keepalive chưa được cấu hình phù hợp.
- Pool giữ connection lâu hơn tuổi thọ mà hạ tầng cho phép.

Kiểm tra xem khoảng thời gian trước lỗi có lặp lại ổn định không. Một chu kỳ gần như cố định là manh mối hữu ích để tìm timeout ở thiết bị trung gian.

### 1.4. Chỉ một instance hoặc một vùng mạng bị lỗi

Nếu chỉ một pod, VM, subnet hoặc application node gặp lỗi, ưu tiên so sánh:

- DNS resolution.
- Route, firewall policy và NAT path.
- JDBC driver/configuration.
- Connection pool state.
- Host clock và TLS truststore.
- Network interface/OS resource.

Nếu tất cả application nodes cùng lỗi đúng một thời điểm, kiểm tra database instance, listener, shared network path, storage/OS event và thay đổi vận hành đồng thời.

## 2. ORA-03113: end-of-file on communication channel

### 2.1. Ý nghĩa

ORA-03113 cho biết client không còn nhận được dữ liệu qua communication channel như mong đợi; phía đối tác đã đóng kết nối hoặc đường truyền kết thúc bất ngờ. Đây là triệu chứng ở lớp giao tiếp, không tự xác định nguyên nhân gốc.

### 2.2. Nguyên nhân thường gặp

- Oracle server process bị crash hoặc bị terminate.
- Database instance bị shutdown/abort hoặc restart.
- Lỗi nội bộ như ORA-00600, ORA-07445 hoặc process memory error.
- OS kill process do OOM killer, resource limit hoặc administrator action.
- Network device reset/close TCP connection.
- Client process đóng socket hoặc application bị restart.
- Listener/service failover khiến session cũ bị ngắt.
- Một số lỗi storage/I/O làm server process không thể tiếp tục.

### 2.3. Thông tin cần lấy

Ghi lại:

- Timestamp chính xác và timezone của application host.
- Host, pod, process ID và thread name.
- JDBC URL/service name đã che credential.
- Oracle error code và toàn bộ nested causes.
- Operation đang thực hiện, SQL operation type và transaction phase.
- Database service, instance và session nếu còn xác định được.
- Request/correlation ID và business key liên quan.

### 2.4. Kiểm tra database alert log

Trên database, lấy ADR locations:

§§§sql
SELECT name, value
FROM v$diag_info
ORDER BY name;
§§§

Các mục quan trọng gồm ADR Base, ADR Home, Diag Trace, Diag Alert và Default Trace File tùy context. Alert log thường chứa dấu hiệu instance restart, process death, ORA-00600, ORA-07445, ORA-04030, ORA-04031 hoặc lỗi I/O gần thời điểm client mất kết nối.

Có thể dùng ADRCI trên host database:

§§§text
adrci
show homes
set home <ADR_HOME>
show alert -tail 100
show alert -tail -f
§§§

Cú pháp và ADR home cần chọn theo database instance thực tế. Không chỉ tìm chuỗi ORA-03113; tìm lỗi server-side xảy ra trước hoặc cùng thời điểm.

### 2.5. Kiểm tra trace

Nếu alert log ghi process ID, incident hoặc trace file, thu thập trace tương ứng. Đối chiếu:

- Oracle process ID/session ID.
- SQL đang chạy và wait event cuối.
- Call stack nếu có incident.
- ORA-00600/ORA-07445 và incident package.
- Dấu hiệu process bị kill hoặc resource exhaustion.

Không xóa trace/incident trước khi lưu evidence. Với lỗi nội bộ Oracle, giữ alert log, trace và incident package để DBA/Oracle Support phân tích.

### 2.6. Kiểm tra instance có restart không

§§§sql
SELECT instance_name,
       host_name,
       startup_time,
       status,
       database_status
FROM v$instance;
§§§

Nếu startup_time thay đổi gần thời điểm lỗi, instance đã restart. Xác minh lý do từ alert log và OS logs. Nếu database vẫn mở nhưng một session cụ thể mất kết nối, không được mặc định là instance restart.

## 3. ORA-03135: connection lost contact

### 3.1. Ý nghĩa

ORA-03135 cho biết Oracle Net đã mất liên lạc với phía còn lại của kết nối. Nó thường xuất hiện trên một session đã thiết lập, đặc biệt khi session idle lâu hoặc TCP path bị đóng. Tuy vậy, lỗi cũng có thể do process/server/network failure; phải đối chiếu bằng chứng.

### 3.2. Idle timeout

Các firewall, NAT gateway, proxy, VPN hoặc load balancer có thể loại bỏ TCP connection không truyền dữ liệu trong một thời gian. Database và application vẫn có thể nghĩ connection còn tồn tại; khi pool tái sử dụng socket, thao tác tiếp theo phát hiện peer đã mất.

Ví dụ:

1. HikariCP tạo connection lúc 09:00.
2. Connection không được sử dụng.
3. Network firewall xóa TCP state lúc 09:30.
4. Pool vẫn giữ connection object.
5. Ứng dụng lấy connection lúc 09:45.
6. Query đầu tiên nhận ORA-03135 hoặc ORA-17002/Connection reset.

Đây là ví dụ minh họa. Thời gian thực tế phụ thuộc timeout cấu hình ở hạ tầng.

### 3.3. SQLNET.EXPIRE_TIME

SQLNET.EXPIRE_TIME trong sqlnet.ora cấu hình probe để kiểm tra connection còn sống. Giá trị thường được biểu diễn bằng phút; giá trị lớn hơn 0 có thể giúp phát hiện connection chết và giảm thời gian giữ connection bị mất.

Ví dụ minh họa:

§§§text
SQLNET.EXPIRE_TIME = 10
§§§

Đây không phải query keepalive và không phải timeout của câu SQL. Chọn giá trị dựa trên Oracle release, network idle timeout và tải hệ thống. Probe quá thường xuyên có thể tạo traffic không cần thiết; cấu hình này cũng không sửa được mọi lỗi network.

Sau khi thay sqlnet.ora, xác định thành phần nào cần reload/restart theo cấu hình và release. Thay đổi phía server có thể áp dụng cho các connection mới hoặc theo behavior của Oracle Net; không giả định mọi session đang tồn tại được cập nhật tức thời.

### 3.4. TCP keepalive

TCP keepalive là cơ chế ở OS/network stack để kiểm tra peer còn sống. Nó khác Oracle Net probe và khác Hikari keepalive. Giá trị OS thường do quản trị viên cấu hình; kiểm tra Windows/Linux host và container/network namespace thực tế.

Keepalive chỉ hữu ích nếu probe được gửi trước khi thiết bị trung gian xóa state và được phép đi qua network path. Nó không thay thế timeout/read timeout hợp lý hoặc pool validation.

### 3.5. Profile IDLE_TIME và resource policy

Kiểm tra profile của user database:

§§§sql
SELECT username, profile
FROM dba_users
WHERE username = 'APP_RUNTIME';

SELECT profile, resource_name, limit
FROM dba_profiles
WHERE profile = (
    SELECT profile
    FROM dba_users
    WHERE username = 'APP_RUNTIME'
)
AND resource_name IN (
    'IDLE_TIME',
    'CONNECT_TIME',
    'SESSIONS_PER_USER'
);
§§§

Resource limits chỉ có tác dụng theo cấu hình RESOURCE_LIMIT và policy tương ứng. IDLE_TIME có thể terminate session sau thời gian idle; nó khác với firewall TCP idle timeout. Xem thêm alert/audit/application logs để xác định session bị Oracle terminate hay network path đóng.

### 3.6. Session idle và transaction

Không giữ transaction mở trong thời gian dài khi chờ người dùng hoặc xử lý bên ngoài. Transaction idle có thể giữ lock, undo và session resources; việc connection bị ngắt khi transaction đang mở có thể làm kết quả nghiệp vụ khó xác định ở phía client.

## 4. ORA-17002 trong Oracle JDBC

### 4.1. Đây là mã của JDBC driver

ORA-17002 là mã lỗi Oracle JDBC driver cho I/O error. Nó không phải một mã Oracle Database server error có một nguyên nhân duy nhất. Message thường chứa thêm chi tiết như:

- The Network Adapter could not establish the connection.
- Socket read timed out.
- Connection reset.
- Socket closed.
- Broken pipe.
- Connection aborted.

Đọc toàn bộ message và nested exception. Chỉ ghi ORA-17002 vào incident report là chưa đủ để khoanh vùng.

### 4.2. Lỗi lúc connect và lỗi giữa phiên khác nhau

Nếu ORA-17002 xảy ra khi tạo connection, kiểm tra DNS, TCP port, listener, service name, connect timeout và TLS.

Nếu xảy ra khi query hoặc commit, kiểm tra read timeout, network reset, server process, instance restart và transaction outcome.

Nếu xảy ra khi lấy connection cũ từ pool, kiểm tra idle timeout, keepalive, maxLifetime và validation.

### 4.3. Exception chain trong Java

JDBC có thể lồng lỗi trong SQLException.getCause(), SQLException.getNextException() hoặc các wrapper của framework. Ghi nhận cả:

- Class name của exception.
- Message.
- SQLState.
- Vendor error code.
- Cause chain.
- Next-exception chain.
- Thread, request ID và thời gian.

Ví dụ helper log chain:

§§§java
import java.sql.SQLException;

public final class JdbcErrorLogger {

    private JdbcErrorLogger() {
    }

    public static void logChain(SQLException exception) {
        SQLException current = exception;
        int index = 0;

        while (current != null) {
            System.err.printf(
                "JDBC[%d] type=%s code=%d state=%s message=%s%n",
                index,
                current.getClass().getName(),
                current.getErrorCode(),
                current.getSQLState(),
                current.getMessage()
            );
            current = current.getNextException();
            index++;
        }

        Throwable cause = exception.getCause();
        while (cause != null) {
            System.err.printf(
                "CAUSE type=%s message=%s%n",
                cause.getClass().getName(),
                cause.getMessage()
            );
            cause = cause.getCause();
        }
    }
}
§§§

Đây là ví dụ minh họa. Trong ứng dụng thật, dùng structured logger thay vì System.err, giới hạn độ dài message và không log password, access token, wallet secret hoặc dữ liệu cá nhân.

### 4.4. SQLRecoverableException

Một số lỗi kết nối được JDBC driver biểu diễn bằng SQLRecoverableException hoặc SQLException khác. Loại exception giúp framework phân loại lỗi nhưng không tự chứng minh transaction có thể retry an toàn.

Sau lỗi connection trong khi commit, client có thể không biết server đã commit hay chưa. Phải kiểm tra transaction outcome bằng business key/idempotency key hoặc cơ chế reconciliation trước khi gửi lại thao tác không idempotent.

### 4.5. Spring exception translation

Spring có thể bọc SQLException thành DataAccessException. Khi điều tra, đi sâu tới root cause và SQL exception chain. Không chỉ log exception class ngoài cùng vì lớp ngoài thường chỉ cho biết repository/JPA operation thất bại.

## 5. Đường đi của một kết nối Oracle

Một connection từ Spring Boot tới Oracle thường đi qua các thành phần:

§§§text
Spring service / transaction
        |
HikariCP connection pool
        |
Oracle JDBC Thin driver
        |
DNS / route / firewall / NAT / proxy
        |
TCP listener endpoint (host:port)
        |
Oracle Listener
        |
Database service / PDB / instance
        |
Oracle server process
        |
SQL execution / transaction
§§§

Mất kết nối có thể xảy ra ở bất kỳ đoạn nào. Listener chủ yếu tham gia quá trình thiết lập kết nối và handoff; một session đã kết nối thường giao tiếp qua server process, vì vậy listener log không nhất thiết ghi mọi lần session đang chạy bị đứt.

### 5.1. DNS

Hostname có thể resolve thành IP sai, IP cũ hoặc nhiều địa chỉ với một số địa chỉ không reachable. So sánh kết quả resolve từ đúng application host/container, không chỉ từ laptop DBA.

### 5.2. TCP

Port listener thường là 1521 nhưng có thể khác. Kiểm tra TCP connect từ cùng network namespace với ứng dụng.

### 5.3. Listener

Listener có thể down, bind sai interface/port hoặc không biết service được yêu cầu. Service registration có thể bị trễ hoặc cấu hình LOCAL_LISTENER/REMOTE_LISTENER chưa đúng.

### 5.4. Database service

Service name có thể trỏ vào PDB, workload hoặc role cụ thể. Khi PDB đóng, service không đăng ký hoặc Data Guard role chuyển đổi, client có thể không kết nối được dù listener process vẫn chạy.

### 5.5. Server process

Server process có thể kết thúc do lỗi nội bộ, OS kill, resource exhaustion hoặc instance shutdown. Alert log và trace thường quan trọng hơn listener log trong tình huống này.

### 5.6. Connection pool

Pool giữ physical JDBC connections để tái sử dụng. Nếu network path đã đóng socket nhưng pool chưa phát hiện, ứng dụng có thể lấy connection stale và lỗi ở query đầu tiên.

## 6. Kiểm tra từ application host

### 6.1. Kiểm tra DNS

Windows PowerShell:

§§§powershell
Resolve-DnsName dbhost.example.internal
§§§

Linux:

§§§bash
getent hosts dbhost.example.internal
nslookup dbhost.example.internal
§§§

Kiểm tra tất cả IP trả về và so sánh với cấu hình network/service. Với RAC SCAN, hostname có thể resolve nhiều IP; cần xác minh mọi địa chỉ được trả về đều có thể sử dụng.

### 6.2. Kiểm tra TCP port

Windows:

§§§powershell
Test-NetConnection -ComputerName dbhost.example.internal -Port 1521
§§§

Linux:

§§§bash
nc -vz dbhost.example.internal 1521
§§§

TCP test thành công chỉ chứng minh bắt tay TCP tới endpoint; không chứng minh listener biết service, database mở hoặc user có quyền đăng nhập.

### 6.3. Kiểm tra TNS alias

§§§text
tnsping APPDB
§§§

tnsping kiểm tra khả năng resolve alias và phản hồi Oracle Net listener ở mức nhất định. Nó không thực hiện login database, không xác minh password, không kiểm tra quyền schema và không chứng minh SQL có thể chạy.

### 6.4. Kiểm tra listener

Trên database host:

§§§text
lsnrctl status
lsnrctl services
§§§

Xác minh:

- Listener name.
- Listening endpoints và port.
- Service name được đăng ký.
- Instance handler status.
- Service có đúng PDB/role không.

Nếu service thiếu, kiểm tra alert log listener, service configuration và dynamic registration thay vì chỉ restart listener theo phản xạ.

### 6.5. Test bằng SQL*Plus hoặc SQLcl

Nếu có Oracle client, thử kết nối bằng đúng host/service/user từ application host:

§§§text
sqlplus APP_RUNTIME@//dbhost.example.internal:1521/APP_SERVICE
§§§

Không đưa password vào command line hoặc shell history. Kết nối thành công từ SQL*Plus không chứng minh JDBC driver, TLS settings, connection pool hoặc application timeout giống nhau; đây chỉ là một phép thử tách lớp.

### 6.6. So sánh từ cùng môi trường

Nếu app chạy trong Kubernetes, chạy kiểm tra từ pod hoặc ephemeral diagnostic container cùng namespace/network policy. Nếu app chạy trong VM, kiểm tra từ đúng VM. Một laptop có thể đi qua VPN hoặc route khác.

## 7. Kiểm tra Oracle Listener và service

### 7.1. Listener status

§§§text
lsnrctl status LISTENER
lsnrctl services LISTENER
§§§

Tên listener có thể khác LISTENER mặc định. Dùng output thực tế để xác định endpoint.

### 7.2. Service registration

Trong database:

§§§sql
SELECT name,
       network_name,
       pdb
FROM v$services
ORDER BY name;
§§§

Kiểm tra service mà JDBC URL yêu cầu có xuất hiện và trỏ đúng PDB. Một service có thể tồn tại nhưng chưa active/được listener đăng ký đúng.

### 7.3. Instance status

§§§sql
SELECT inst_id,
       instance_name,
       host_name,
       status,
       database_status,
       startup_time
FROM gv$instance
ORDER BY inst_id;
§§§

Trong môi trường non-RAC, có thể dùng V$INSTANCE. GV$ views cần quyền và có ý nghĩa khi truy vấn RAC.

### 7.4. Listener log

Listener log giúp phát hiện:

- Connection request tới endpoint.
- Service name không được nhận diện.
- Client address.
- Listener restart hoặc lỗi accept.
- Connection bị đóng ở giai đoạn handoff.

Không có entry tương ứng không chứng minh network không lỗi; packet có thể chưa tới listener hoặc session đã được handoff trước đó.

### 7.5. Không restart listener một cách mù quáng

Restart listener có thể làm gián đoạn việc thiết lập connection mới hoặc thay đổi behavior service registration. Nó thường không sửa được socket đã mất giữa application và database server process. Thu thập listener status/log trước khi thay đổi.

## 8. Kiểm tra database session và resource

### 8.1. Session của application user

§§§sql
SELECT inst_id,
       sid,
       serial#,
       username,
       machine,
       program,
       module,
       service_name,
       status,
       logon_time,
       event
FROM gv$session
WHERE username = 'APP_RUNTIME'
ORDER BY inst_id, logon_time;
§§§

Nếu application dùng proxy user, schema owner khác hoặc connection pool đổi username, điều chỉnh predicate. Ghi MODULE/ACTION từ DBMS_APPLICATION_INFO giúp nối session database với request/service ở application.

### 8.2. Resource limits

§§§sql
SELECT inst_id,
       resource_name,
       current_utilization,
       max_utilization,
       limit_value
FROM gv$resource_limit
WHERE resource_name IN (
    'processes',
    'sessions',
    'transactions'
)
ORDER BY inst_id, resource_name;
§§§

Nếu gần chạm giới hạn processes/sessions, database có thể từ chối connection mới. Kiểm tra alert log và các lỗi ORA-00018/ORA-00020 đi kèm.

### 8.3. Process và session mapping

§§§sql
SELECT s.inst_id,
       s.sid,
       s.serial#,
       s.username,
       s.machine,
       s.program,
       p.spid
FROM gv$session s
JOIN gv$process p
  ON p.inst_id = s.inst_id
 AND p.addr = s.paddr
WHERE s.username = 'APP_RUNTIME';
§§§

Mapping giúp DBA xác định server process OS tương ứng khi trace/log cung cấp process ID. Quyền truy cập GV$ views cần được cấp phù hợp.

### 8.4. Session không còn xuất hiện

Sau khi connection bị đứt, session có thể đã bị cleanup hoặc server process kết thúc. Không thấy session hiện tại không chứng minh connection chưa từng tồn tại. Dùng alert log, listener log, audit và application timestamp để tái dựng.

### 8.5. Resource Manager và profile

Kiểm tra profile IDLE_TIME/CONNECT_TIME, Resource Manager consumer group, session kill và policy quản lý session. Phân biệt database chủ động terminate session với network path đóng socket.

## 9. JDBC URL và Oracle Net descriptor

### 9.1. Easy Connect service name

Ví dụ:

§§§text
jdbc:oracle:thin:@//dbhost.example.internal:1521/APP_SERVICE
§§§

Đoạn sau dấu slash là service name. Với multitenant, service thường ánh xạ tới PDB.

### 9.2. TNS alias

§§§text
jdbc:oracle:thin:@APPDB
§§§

Driver cần tìm alias trong cấu hình Oracle Net tương ứng. Trong container, đảm bảo TNS_ADMIN và tnsnames.ora được mount/cấu hình đúng.

### 9.3. Descriptor đầy đủ

§§§text
jdbc:oracle:thin:@(DESCRIPTION=
  (CONNECT_TIMEOUT=10)
  (TRANSPORT_CONNECT_TIMEOUT=3)
  (RETRY_COUNT=3)
  (RETRY_DELAY=2)
  (ADDRESS=(PROTOCOL=TCP)(HOST=dbhost.example.internal)(PORT=1521))
  (CONNECT_DATA=(SERVICE_NAME=APP_SERVICE))
)
§§§

Các tham số trên chỉ là ví dụ. Ý nghĩa, đơn vị và hỗ trợ phụ thuộc Oracle JDBC/Oracle Net version. Chọn timeout theo latency và RTO; retry connect không thay thế retry logic transaction.

### 9.4. SID và SERVICE_NAME

Legacy URL có thể dùng SID:

§§§text
jdbc:oracle:thin:@dbhost.example.internal:1521:ORCL
§§§

Service name:

§§§text
jdbc:oracle:thin:@//dbhost.example.internal:1521/APP_SERVICE
§§§

Không thay SID thành service name hoặc ngược lại theo phỏng đoán. Xác nhận descriptor, listener services và database service configuration.

### 9.5. Connection string nhiều địa chỉ

Oracle Net descriptor có thể chứa ADDRESS_LIST hoặc nhiều ADDRESS cho RAC/HA. Cần kiểm tra LOAD_BALANCE, FAILOVER, RETRY_COUNT, RETRY_DELAY, CONNECT_TIMEOUT và service goal phù hợp topology. Một địa chỉ lỗi trong danh sách có thể làm thời gian connect tăng nếu retry policy không phù hợp.

### 9.6. SCAN và RAC

Với RAC, ứng dụng thường kết nối qua SCAN listener và service. Không hard-code một node VIP nếu thiết kế yêu cầu service-aware load balancing/failover. Xác minh DNS SCAN, tất cả IP, listener và service placement.

## 10. Timeout: phân biệt từng lớp

Các timeout có mục tiêu khác nhau. Đặt một timeout duy nhất không xử lý được toàn bộ connection lifecycle.

| Timeout | Lớp | Kiểm soát |
|---|---|---|
| DNS timeout | Resolver/network | Thời gian phân giải hostname |
| TCP connect timeout | JDBC/OS | Thời gian bắt tay tới endpoint |
| Oracle Net CONNECT_TIMEOUT | Oracle Net | Thời gian thiết lập kết nối theo descriptor |
| Pool connectionTimeout | HikariCP | Thời gian chờ lấy connection từ pool |
| JDBC ReadTimeout | Oracle JDBC socket | Thời gian chờ dữ liệu trả về từ socket |
| SQLNET.RECV_TIMEOUT | Oracle Net server/client | Thời gian chờ dữ liệu nhận theo cấu hình |
| SQLNET.SEND_TIMEOUT | Oracle Net | Thời gian chờ gửi dữ liệu |
| SQLNET.EXPIRE_TIME | Oracle Net probe | Kiểm tra connection còn sống theo chu kỳ |
| Firewall idle timeout | Network device | Thời gian giữ TCP state khi idle |
| Hikari maxLifetime | Connection pool | Tuổi thọ tối đa của physical connection trong pool |
| Hikari keepaliveTime | Connection pool | Kiểm tra/giữ alive connection idle |
| Query/statement timeout | JDBC/JPA/application | Giới hạn thời gian thực thi hoặc chờ statement |

### 10.1. Connect timeout

Giới hạn thời gian mở socket và thiết lập Oracle Net session. Nếu quá thấp, kết nối hợp lệ qua mạng có latency cao có thể bị fail; nếu quá cao, request thread có thể bị giữ lâu khi endpoint không reachable.

### 10.2. Read timeout

Giới hạn thời gian chờ đọc dữ liệu từ socket theo JDBC driver. Nếu đặt quá thấp, query hợp lệ nhưng lâu có thể bị client timeout. Timeout ở client có thể đóng connection trong khi server vẫn đang thực hiện công việc; cần xác định server-side outcome.

### 10.3. SQLNET.RECV_TIMEOUT và SEND_TIMEOUT

Các tham số Oracle Net điều khiển thời gian chờ ở phía nhận/gửi theo cấu hình. Chúng không tương đương statement timeout. Thay đổi phải được áp dụng có chủ đích và kiểm thử cho cả client/server.

### 10.4. SQLNET.EXPIRE_TIME

Đây là probe theo chu kỳ để phát hiện dead peer; không phải timeout của query hoặc thời gian chờ connect.

### 10.5. Pool connectionTimeout

HikariCP connectionTimeout là thời gian thread chờ lấy connection từ pool. Nếu pool cạn do tất cả connection đang bận hoặc bị treo, request có thể timeout dù database listener vẫn khỏe.

### 10.6. maxLifetime và firewall timeout

Đặt Hikari maxLifetime thấp hơn giới hạn tuổi thọ connection do database/proxy/hạ tầng áp dụng để pool chủ động loại connection trước khi thiết bị đóng nó. Hikari không thể biết mọi network timeout nếu không có traffic hoặc keepalive phù hợp.

### 10.7. Không đặt mọi timeout thành một giây

Timeout quá thấp có thể biến tải cao hoặc query hợp lệ thành lỗi giả. Timeout quá cao làm request thread, pool slot và transaction bị giữ lâu. Đặt theo SLO, latency percentile, transaction profile và failure detection target.

## 11. Cấu hình HikariCP trong Spring Boot

### 11.1. Ví dụ cấu hình

§§§yaml
spring:
  datasource:
    hikari:
      pool-name: OracleAppPool
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 30000
      validation-timeout: 5000
      idle-timeout: 600000
      max-lifetime: 1740000
      keepalive-time: 300000
§§§

Các giá trị trên là ví dụ minh họa bằng milliseconds. Hãy tính lại theo giới hạn database, firewall, số replica và capacity Oracle. Không sao chép nguyên xi vào production.

### 11.2. maxLifetime

HikariCP chủ động retire physical connection khi đạt maxLifetime; connection đang được sử dụng không bị đóng giữa transaction chỉ vì chạm tuổi thọ. Đặt maxLifetime thấp hơn giới hạn của hạ tầng nếu có một giới hạn cố định.

### 11.3. keepaliveTime

Keepalive của Hikari chỉ áp dụng cho connection đang idle trong pool và phải nhỏ hơn maxLifetime. Nó mượn connection, kiểm tra liveness rồi trả lại pool. Nó không giữ alive connection đang bận và không thay thế TCP keepalive hay SQLNET.EXPIRE_TIME.

### 11.4. validationTimeout

validationTimeout là thời gian tối đa kiểm tra connection. Nó phải nhỏ hơn connectionTimeout. Nếu validation timeout quá dài, request lấy connection có thể bị trì hoãn.

### 11.5. connectionTestQuery

Với JDBC4 driver hỗ trợ Connection.isValid(), HikariCP thường có thể dùng JDBC validation mà không cần custom test query. Chỉ cấu hình connectionTestQuery khi driver/compatibility thực tế yêu cầu. Nếu dùng query, kiểm tra nó không tạo side effect và không tốn chi phí đáng kể.

### 11.6. maximumPoolSize

Tăng pool size không tự sửa lỗi network. Nếu có 10 application replicas, mỗi replica pool 20 connection, database có thể nhận tới 200 physical connections cộng thêm các client khác. Tính tổng connection budget theo toàn bộ deployment, không chỉ một pod.

### 11.7. Leak detection

Hikari leakDetectionThreshold có thể cảnh báo connection bị giữ lâu hơn ngưỡng; đây là công cụ chẩn đoán, không tự thu hồi transaction bị treo. Đặt ngưỡng phù hợp và tránh nhầm cảnh báo leak với network disconnect.

## 12. JDBC driver và TLS/TCPS

### 12.1. Driver version

Kiểm tra Oracle JDBC driver version được resolve thực tế và tương thích với JDK, Oracle Database release và Spring Boot/Hibernate stack. Dependency tree có thể cho biết driver khác với version khai báo trực tiếp do dependency management.

### 12.2. Driver mismatch

Driver cũ có thể thiếu fix cho TLS, network, protocol hoặc database feature. Driver mới cũng cần tương thích với JDK và môi trường. Thu thập:

- JDBC driver class/version.
- JDK vendor/version.
- Oracle Database release/patch.
- Thin/OCI mode.
- Connection URL và properties đã che secrets.

### 12.3. TCPS

Nếu dùng TCPS, kiểm tra:

- Wallet/truststore có mount đúng trên mọi pod không.
- Certificate chain có đầy đủ không.
- Certificate chưa hết hạn và hostname/SAN phù hợp.
- TLS protocol/cipher có tương thích không.
- TNS_ADMIN và wallet location đúng.
- Password/keystore secret được cấp đúng.

TLS handshake failure thường có exception chain riêng; không xử lý bằng cách tắt certificate validation trên production.

### 12.4. Connection reset sau certificate rotation

Khi rotate certificate/wallet, application instances có thể giữ connection TLS đã mở từ trước trong khi connection mới dùng trust material khác. Lập kế hoạch reload/restart pool, overlap certificate nếu cần và test reconnect từ tất cả replicas.

## 13. RAC, Data Guard và HA events

### 13.1. RAC node failure

Nếu một RAC instance/node lỗi, session đang nằm trên node đó có thể bị ngắt. Service có thể được chạy lại trên node khác; application cần reconnect và xử lý transaction outcome.

### 13.2. FAN và Fast Connection Failover

Oracle Fast Application Notification (FAN) và Fast Connection Failover (FCF) giúp application pool biết sự kiện service/instance. UCP và Oracle integration có hỗ trợ HA event; HikariCP không tự động có mọi hành vi FCF như UCP.

Nếu yêu cầu RAC HA nâng cao, đánh giá UCP/Oracle JDBC HA integration, service configuration và FAN/ONS theo release thay vì giả định mọi JDBC pool xử lý như nhau.

### 13.3. Data Guard role transition

Khi Data Guard switchover/failover, service có thể relocate hoặc start trên primary mới. Ứng dụng cần kết nối qua service phù hợp role, reconnect pool và xác nhận database role trước khi ghi.

### 13.4. Transaction đang chạy khi failover

Session mất kết nối trong failover không có nghĩa transaction tự động được replay an toàn. Transaction Guard/Application Continuity có thể hỗ trợ xác định outcome/replay trong topology và driver/service được hỗ trợ. Phải xác minh cấu hình và giới hạn trước khi dựa vào tính năng này.

### 13.5. UCP và Application Continuity

Oracle Universal Connection Pool (UCP) tích hợp với các tính năng HA Oracle như FAN/FCF và có thể tham gia Application Continuity/Transaction Guard khi cấu hình phù hợp. Các tính năng này có yêu cầu về database, service, driver, replay eligibility và application behavior; không phải mọi statement đều replay an toàn.

## 14. Retry và transaction safety

### 14.1. Không retry mù mọi SQLException

Khi connection mất giữa một transaction, client có thể không biết server đã thực hiện statement hoặc commit hay chưa. Ví dụ:

1. Ứng dụng gửi COMMIT.
2. Oracle commit thành công.
3. Network bị đứt trước khi response tới ứng dụng.
4. Ứng dụng nhận ORA-03113/ORA-17002.

Nếu ứng dụng retry toàn bộ request, có thể tạo giao dịch thứ hai dù giao dịch đầu đã commit.

### 14.2. Phân biệt retry connect và retry transaction

- Retry mở connection mới thường an toàn hơn vì chưa gửi business operation.
- Retry read-only query có thể an toàn nếu semantics và snapshot chấp nhận.
- Retry write transaction cần biết outcome hoặc dùng idempotency.
- Retry commit khi kết quả không rõ phải dựa vào transaction outcome mechanism hoặc business reconciliation.

### 14.3. Idempotency key

Với request tạo payment/order, dùng idempotency key duy nhất theo business operation. Database enforce unique constraint trên key để lần retry không tạo bản ghi thứ hai.

Ví dụ:

§§§sql
CREATE TABLE APP.PAYMENT_REQUEST (
    REQUEST_KEY VARCHAR2(100 CHAR) NOT NULL,
    PAYMENT_ID NUMBER(19),
    STATUS VARCHAR2(20 CHAR) NOT NULL,
    CONSTRAINT PK_PAYMENT_REQUEST PRIMARY KEY (REQUEST_KEY)
);
§§§

Ứng dụng phải xử lý duplicate request key bằng cách đọc kết quả hiện có và trả response nhất quán; không chỉ catch ORA-00001 rồi coi mọi trường hợp là thành công.

### 14.4. Exponential backoff và jitter

Khi retry connection, dùng backoff tăng dần và random jitter để nhiều application instances không đồng loạt reconnect vào database sau outage.

Ví dụ chính sách minh họa: 0.5s, 1s, 2s, 4s, 8s với jitter và giới hạn tổng thời gian. Thời gian thực tế phải phù hợp SLO và incident policy.

### 14.5. Circuit breaker

Nếu database endpoint liên tục thất bại, circuit breaker có thể tạm ngừng request mới để bảo vệ thread pool và database. Khi half-open, chỉ cho số request thử nhỏ. Circuit breaker không thay thế pool validation hoặc HA service.

### 14.6. Evict connection lỗi

Connection đã gặp lỗi I/O thường không nên trả lại pool để tái sử dụng. Framework/pool có thể nhận diện một số SQLRecoverableException và evict connection; xác minh behavior của driver/pool version và không giữ connection lỗi trong application cache.

### 14.7. Không retry lỗi nghiệp vụ

Không retry constraint violation, invalid SQL, authentication failure hoặc schema error theo cùng chính sách retry network. Phân loại lỗi theo SQLState/vendor code và root cause.

## 15. Logging và observability trong ứng dụng

### 15.1. Những trường cần log

- Timestamp có timezone.
- Service name, pod/host và deployment version.
- Request/correlation ID.
- Database service/endpoint đã che thông tin nhạy cảm.
- JDBC driver version.
- SQLState, Oracle vendor code, exception class.
- Root cause và nested exceptions.
- Operation/transaction phase.
- Thời gian chờ lấy connection.
- Thời gian query/commit nếu đo được.

### 15.2. Không log secrets

Không ghi password, full wallet path chứa secret, token, private key, bind values có PII hoặc connection string có credential. Mask host/service nếu chính sách bảo mật yêu cầu.

### 15.3. Metrics của pool

Theo dõi:

- Active connections.
- Idle connections.
- Total connections.
- Threads awaiting connection.
- Connection acquisition latency.
- Connection creation failures.
- Timeout count.
- Connection usage duration.

Nếu active = max pool size và pending threads tăng, có thể pool exhaustion hoặc transaction giữ connection quá lâu. Đây là triệu chứng khác với listener down.

### 15.4. Database observability

Theo dõi session count, process count, resource limits, service availability, listener logs, alert log, wait events, CPU, I/O, FRA và network errors. Đồng bộ NTP/timezone giữa app, database và network appliances để correlate timestamp.

### 15.5. Correlation

Dùng request ID ở application logs và DBMS_APPLICATION_INFO MODULE/ACTION/CLIENT_IDENTIFIER để nối request với database session. Không dùng username đơn thuần nếu nhiều service share cùng schema user.

## 16. Quy trình xử lý incident

### Bước 1 — Xác định phạm vi

- Một pod hay toàn bộ application?
- Một service hay nhiều database service?
- Chỉ connect mới hay cả connection đang chạy?
- Lỗi bắt đầu lúc nào và có lặp theo idle interval không?
- Có deploy, patch, firewall, DNS, certificate hoặc role transition gần đó không?

### Bước 2 — Thu thập exception đầy đủ

Lấy ORA code, message, SQLState, vendor code, nested cause và thời điểm. Phân biệt ORA-03113/03135 trong cause chain với ORA-17002 wrapper.

### Bước 3 — Kiểm tra application pool

- Active/idle/total/pending.
- Connection acquisition timeout.
- Connection age/idle duration.
- Hikari keepalive/maxLifetime.
- Driver version.
- Pool evict behavior.

### Bước 4 — Kiểm tra network từ đúng host

- DNS resolve.
- TCP connect tới listener port.
- Route/firewall/NAT/proxy.
- Idle timeout.
- TLS/TCPS handshake.
- So sánh node tốt và node lỗi.

### Bước 5 — Kiểm tra listener/service

- lsnrctl status/services.
- Listener log.
- Service registration.
- PDB open mode và database role.
- SCAN/service placement nếu RAC.

### Bước 6 — Kiểm tra database

- V$DIAG_INFO và alert log.
- Trace/incident.
- Instance startup time/status.
- Session/process/resource limits.
- OS logs, OOM, process kill, storage/network events.

### Bước 7 — Xác định transaction outcome

Nếu lỗi xảy ra khi DML/commit:

- Xác định business key/idempotency key.
- Kiểm tra bản ghi đã tồn tại chưa.
- Kiểm tra audit/outbox/ledger.
- Xác định commit outcome trước khi retry.

### Bước 8 — Khôi phục có kiểm soát

- Nếu listener/service down: xử lý đúng thành phần và xác minh service.
- Nếu stale pool connections: evict/recycle theo kế hoạch và điều chỉnh timeout.
- Nếu instance crash: xử lý root cause database/OS trước khi mở traffic.
- Nếu firewall timeout: phối hợp network team chỉnh policy/keepalive.
- Nếu TLS: sửa certificate/wallet/trust chain.
- Nếu resource exhausted: xác định session leak/connection storm và capacity.

### Bước 9 — Xác minh

Chạy connection test bằng runtime user, query read-only, transaction test có kiểm soát, kiểm tra pool metrics và theo dõi đủ thời gian để vượt qua idle interval đã gây lỗi.

### Bước 10 — Ghi RCA

Ghi root cause, timeline, affected requests/transactions, data impact, fix, preventive actions và evidence. Không kết thúc incident chỉ bằng việc restart app hoặc listener.

## 17. Decision tree chẩn đoán

§§§text
Connection error
|
|-- Không mở được connection mới?
|   |
|   |-- DNS/TCP không tới được host: DNS, route, firewall, port
|   |
|   |-- TCP tới được nhưng listener/service lỗi: listener, service, PDB
|   |
|   |-- TLS handshake lỗi: wallet, certificate, protocol
|
|-- Connection đã mở rồi mới đứt?
|   |
|   |-- Instance/process lỗi: alert log, trace, OS logs
|   |
|   |-- Chỉ sau idle interval: firewall/NAT, keepalive, pool lifetime
|   |
|   |-- Trong query lâu: read timeout, network reset, server wait/health
|   |
|   |-- Trong RAC/role transition: service, FAN/FCF, reconnect behavior
|
|-- Chỉ lỗi khi lấy connection từ pool?
|   |
|   |-- Pool cạn: active/pending, leak, long transaction
|   |
|   |-- Connection stale: validation, keepalive, maxLifetime
|
|-- Lỗi xảy ra trong COMMIT?
    |
    |-- Outcome chưa rõ: không retry mù; kiểm tra idempotency/reconciliation
§§§

## 18. Case study

### 18.1. ORA-03135 sau 30 phút idle

Triệu chứng: mọi query đều chạy bình thường, nhưng request đầu tiên sau thời gian idle cố định nhận ORA-03135.

Điều tra:

1. So sánh idle duration với firewall/NAT timeout.
2. Kiểm tra Hikari keepaliveTime và maxLifetime.
3. Kiểm tra SQLNET.EXPIRE_TIME và OS TCP keepalive.
4. Xác nhận pool có trả connection cũ sau khi firewall đã xóa TCP state không.
5. Thử thay đổi một cấu hình ở staging và chờ vượt qua idle interval.

Khắc phục có thể là điều chỉnh pool lifetime/keepalive, network idle policy hoặc Oracle Net probe. Chọn theo kiến trúc và xác nhận bằng test lặp lại.

### 18.2. ORA-03113 đồng loạt khi database restart

Triệu chứng: nhiều pod nhận ORA-03113 trong cùng phút.

Điều tra:

1. So sánh timestamp với V$INSTANCE.STARTUP_TIME.
2. Đọc alert log để tìm shutdown/startup và lỗi trước đó.
3. Kiểm tra OS logs và maintenance events.
4. Kiểm tra listener/service sau restart.
5. Xác định các transaction đang chạy và outcome.
6. Evict connection chết và reconnect có backoff.

Khắc phục gốc có thể là database/OS event; tăng pool timeout không sửa được instance crash.

### 18.3. ORA-17002: Network Adapter could not establish connection

Triệu chứng: app vừa deploy không thể mở connection, SQL*Plus từ laptop DBA vẫn kết nối được.

Điều tra:

1. Kiểm tra hostname resolution trong pod.
2. Test TCP port từ pod.
3. So sánh TNS_ADMIN/JDBC URL giữa app và laptop.
4. Kiểm tra network policy/security group.
5. Kiểm tra service name và listener registration.
6. Kiểm tra TCPS wallet nếu app dùng TLS còn laptop dùng TCP.

Không dùng thành công từ laptop để kết luận network path từ pod tốt.

### 18.4. ORA-17002 trong lúc commit

Triệu chứng: ứng dụng ghi payment, nhận lỗi I/O trong COMMIT; client không biết commit đã thành công chưa.

Xử lý:

1. Không retry ngay request thanh toán.
2. Tra cứu theo idempotency key/business request key.
3. Kiểm tra payment ledger/outbox hoặc trạng thái phía gateway.
4. Xác định transaction đã commit hay chưa.
5. Chỉ thực hiện lại khi kết quả và quy tắc idempotency cho phép.

### 18.5. Một pod lỗi, pod khác bình thường

Triệu chứng: chỉ pod ở một node nhận Connection reset.

Điều tra:

- DNS cache và resolved IP.
- Node route/NAT/security policy.
- Container network namespace.
- Driver/config secret khác nhau.
- TLS truststore mount.
- Pool metrics và connection age.

Khắc phục theo node/path lỗi; không restart toàn database nếu chỉ một node application bị ảnh hưởng.

## 19. Phòng ngừa

### 19.1. Thiết kế kết nối

- Dùng service name ổn định thay vì hard-code instance host nếu topology yêu cầu HA.
- Dùng connection descriptor có timeout/retry hợp lý.
- Quản lý JDBC driver version có kiểm soát.
- Đồng bộ TLS/wallet trên mọi application instance.
- Tính connection budget toàn hệ thống.

### 19.2. Pool management

- Đặt maxLifetime phù hợp network/database connection lifetime.
- Dùng keepalive cho idle connections nếu phù hợp.
- Validation timeout nhỏ hơn pool connection timeout.
- Theo dõi active/idle/pending và acquisition latency.
- Đóng connection/statement/result set đúng cách.
- Không giữ transaction qua network call hoặc user interaction.

### 19.3. Database/Oracle Net

- Theo dõi alert log và listener logs.
- Đặt SQLNET.EXPIRE_TIME theo network policy khi cần.
- Kiểm tra process/session limits.
- Theo dõi instance/node/service availability.
- Bảo vệ ADR/trace và OS logs.

### 19.4. Network

- Thống nhất idle timeout với pool/keepalive.
- Kiểm tra DNS, route, NAT và firewall rules.
- Đảm bảo mọi RAC SCAN IP/service endpoint reachable.
- Theo dõi packet loss, reset và connection tracking pressure.
- Đồng bộ clock để correlate logs.

### 19.5. Application resilience

- Phân loại connect retry và transaction retry.
- Dùng idempotency cho request ghi.
- Backoff và jitter.
- Circuit breaker có giới hạn.
- Evict connection lỗi.
- Có reconciliation cho outcome không xác định.

## 20. Checklist incident

- [ ] Đã ghi timestamp có timezone và correlation ID.
- [ ] Đã thu thập toàn bộ exception chain, SQLState và vendor code.
- [ ] Đã xác định lỗi lúc connect, lúc query/commit hay sau idle.
- [ ] Đã xác định phạm vi pod/node/service bị ảnh hưởng.
- [ ] Đã kiểm tra DNS từ application host/container.
- [ ] Đã kiểm tra TCP port từ cùng network path.
- [ ] Đã kiểm tra JDBC URL, service name và TNS_ADMIN.
- [ ] Đã kiểm tra listener status/services và listener log.
- [ ] Đã kiểm tra database role, PDB và instance status.
- [ ] Đã đọc alert log và trace tại đúng thời điểm.
- [ ] Đã kiểm tra OS/OOM/process kill/storage/network events.
- [ ] Đã kiểm tra SQLNET.EXPIRE_TIME và profile idle policy.
- [ ] Đã kiểm tra firewall/NAT/proxy idle timeout.
- [ ] Đã kiểm tra Hikari active/idle/pending, maxLifetime và keepalive.
- [ ] Đã kiểm tra JDBC driver/JDK/TLS wallet.
- [ ] Đã kiểm tra session/process resource limits.
- [ ] Đã xác định transaction outcome trước khi retry DML/COMMIT.
- [ ] Đã kiểm tra idempotency/business key và external side effects.
- [ ] Đã xác minh bằng đúng runtime user và application path.
- [ ] Đã ghi root cause, data impact và preventive actions.

## 21. Câu hỏi tự kiểm tra

1. ORA-03113 mô tả điều gì ở communication channel?
2. Vì sao ORA-03113 không tự chứng minh database instance bị crash?
3. ORA-03135 khác ORA-03113 ở thông điệp khái quát nào?
4. ORA-17002 là mã lỗi của lớp nào?
5. Vì sao cần đọc nested cause và SQLException.getNextException()?
6. Làm sao phân biệt lỗi connect mới với lỗi giữa phiên?
7. Những nguyên nhân nào gây ORA-03135 sau một khoảng idle cố định?
8. SQLNET.EXPIRE_TIME dùng để làm gì?
9. SQLNET.EXPIRE_TIME khác TCP keepalive và Hikari keepalive ra sao?
10. Vì sao tnsping thành công chưa chứng minh ứng dụng login/query được?
11. Test-NetConnection hoặc nc xác nhận điều gì và không xác nhận điều gì?
12. ORA-12514 và ORA-12541 gợi ý kiểm tra thành phần nào?
13. V$DIAG_INFO giúp tìm các đường dẫn diagnostic nào?
14. Khi ORA-03113 xảy ra, cần tìm những lỗi server-side nào trong alert log?
15. V$INSTANCE.STARTUP_TIME giúp xác định điều gì?
16. Vì sao listener log có thể không ghi mọi lần session đã kết nối bị đứt?
17. Hikari connectionTimeout khác JDBC ReadTimeout như thế nào?
18. maxLifetime và keepaliveTime nên phối hợp với network idle timeout ra sao?
19. Vì sao tăng maximumPoolSize có thể làm database quá tải?
20. TCPS connection cần kiểm tra wallet và certificate gì?
21. Vì sao một pod lỗi trong khi pod khác bình thường gợi ý network path/config riêng?
22. RAC service failover ảnh hưởng các session đang chạy ra sao?
23. FAN/FCF và UCP hỗ trợ HA như thế nào?
24. Vì sao SQLRecoverableException không tự chứng minh retry transaction an toàn?
25. Điều gì có thể xảy ra nếu network đứt ngay sau khi Oracle commit?
26. Idempotency key giúp ngăn duplicate business operation ra sao?
27. Vì sao retry cần exponential backoff và jitter?
28. Pool metrics nào giúp nhận biết pool exhaustion?
29. Khi nào cần kiểm tra DBA_PROFILES và RESOURCE_LIMIT?
30. Những bằng chứng nào cần có để đóng incident ORA-03113/03135/17002?

**Nguyên tắc cần nhớ:** Phân loại lỗi theo thời điểm: connect, đang dùng hay idle. ORA-03113 là communication channel kết thúc bất ngờ; ORA-03135 là mất liên lạc; ORA-17002 là JDBC I/O wrapper nên phải đọc root cause. Đối chiếu application exception, pool metrics, DNS/TCP, listener/service, alert log, trace và OS/network events tại cùng timestamp. Phối hợp pool lifetime/keepalive với firewall timeout, nhưng không nhầm chúng với query timeout. Khi lỗi xảy ra trong DML hoặc COMMIT, không retry mù: xác định transaction outcome hoặc dùng idempotency/reconciliation trước khi thực hiện lại.

