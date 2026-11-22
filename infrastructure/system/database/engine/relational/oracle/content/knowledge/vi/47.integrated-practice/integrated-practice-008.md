# Mô phỏng pool cạn, timeout, deadlock và khôi phục có kiểm soát trong Oracle Database

Một sự cố ứng dụng kết nối Oracle có thể biểu hiện bằng request chờ lâu, lỗi lấy connection, SQL timeout, session bị block hoặc deadlock. Các triệu chứng này nhìn bề ngoài khá giống nhau: thread không hoàn tất, pool hết connection và người dùng nhận lỗi. Tuy nhiên, nguyên nhân và cách khôi phục khác nhau.

Bài thực hành mô phỏng bốn tình huống liên quan:

1. **Pool cạn (connection pool exhaustion):** ứng dụng không còn connection rảnh để cấp cho request mới.
2. **Timeout:** request hết thời gian chờ ở tầng pool, kết nối, network, lock hoặc SQL statement.
3. **Deadlock:** hai hay nhiều transaction giữ tài nguyên mà transaction kia cần, tạo chu trình chờ.
4. **Khôi phục có kiểm soát:** thu thập bằng chứng, giảm tải, giải phóng tài nguyên đúng phạm vi, khôi phục pool và xác minh ứng dụng/database ổn định.

Bài học lấy Oracle Database 19c, JDBC và HikariCP làm ví dụ. Có thể thay HikariCP bằng pool khác, nhưng cần đối chiếu semantics của từng cấu hình. Thực hiện trên schema test và ứng dụng lab; không cố tình làm cạn pool, tạo deadlock hoặc ngắt kết nối trên production.

## 1. Kiến trúc và các tầng có thể gây chờ

### 1.1. Luồng request tới Oracle

Một request đi qua nhiều tầng trước khi SQL được thực thi:

~~~text
HTTP request / job
       |
       v
Application thread
       |
       v
Connection pool
       |
       | lấy connection rảnh
       v
JDBC connection
       |
       | TCP / Oracle Net / authentication
       v
Oracle listener -> service -> instance
       |
       v
Oracle session
       |
       | parse / execute / wait / fetch
       v
Transaction và data blocks
       |
       v
Commit / rollback -> trả connection về pool
~~~

Một request có thể chờ ở bất kỳ tầng nào:
- Thread chờ pool cấp connection.
- Driver chờ listener hoặc authentication.
- SQL chờ row lock.
- SQL đang chạy nhưng không nhận đủ CPU/I/O.
- Ứng dụng giữ connection trong khi gọi API bên ngoài.
- Connection đã lỗi nhưng pool chưa phát hiện.
- Transaction chưa commit nên session khác bị block.

Chỉ nhìn thời gian response hoặc số connection active không đủ để xác định tầng lỗi.

### 1.2. Phân biệt pool cạn và database hết session

**Pool cạn ở ứng dụng** có nghĩa pool đã cấp hết số connection tối đa và không còn connection idle. Request mới phải đợi hoặc hết acquisition timeout. Database có thể vẫn khỏe.

**Database hết session/process capacity** có nghĩa Oracle không thể tạo thêm session/process theo giới hạn hoặc tài nguyên hiện có. Pool có thể báo lỗi khi cố tạo physical connection mới.

Hai tình huống có thể xảy ra cùng lúc nhưng không đồng nghĩa:
- Pool cạn vì connection đang bị giữ quá lâu, trong khi Oracle còn nhiều capacity.
- Oracle hết session, khiến pool không tạo được connection mới.
- SQL bị block, các connection bị giữ lâu, cuối cùng pool cạn.
- Pool quá lớn trên nhiều replica, làm Oracle chạm giới hạn session.

### 1.3. Phân biệt blocking và deadlock

**Blocking** là một session đang chờ tài nguyên do session khác giữ. Chuỗi có thể kết thúc khi blocker commit hoặc rollback.

**Deadlock** là một chu trình chờ: transaction A giữ tài nguyên mà B cần, đồng thời B giữ tài nguyên mà A cần. Không transaction nào tự tiến triển được nếu không có hành động phá chu trình. Oracle phát hiện deadlock và trả ORA-00060 cho một statement liên quan.

Blocking có thể kéo dài mà không phải deadlock. Deadlock thường được Oracle phát hiện tự động; không cần DBA kill cả hai session chỉ vì thấy ORA-00060.

### 1.4. Sơ đồ nhận diện nhanh

~~~text
Request chậm / lỗi
       |
       v
Pool có connection idle?
       |
   +---+---+
   |       |
  Có      Không
   |       |
   v       v
Lấy được  Active = max?
connection?    |
   |        +--+--+
   |        |     |
   v       Không  Có
Kiểm tra    |     |
SQL/wait    v     v
         Pool đang  Request
         tạo thêm? chờ pool
              |       |
              v       v
         Connect/DB  Kiểm tra
         timeout?   session/SQL
                       |
                       v
                 Lock wait hay
                 query/resource?
                       |
                       v
                 Có chu trình chờ?
                    |       |
                   Có      Không
                    |       |
                    v       v
                ORA-00060  Blocking/
                deadlock   workload chậm
~~~

## 2. Chuẩn bị môi trường lab

### 2.1. Điều kiện

Cần có:
- Oracle Database 19c hoặc môi trường test tương thích.
- Một user schema riêng, ví dụ LAB_APP.
- Quyền tạo bảng và sequence trong schema.
- JDBC driver tương thích JDK.
- HikariCP trong project Java.
- Ít nhất hai SQL session để mô phỏng blocking/deadlock.
- Quyền đọc dynamic performance view nếu muốn quan sát session ở cấp DBA.

Không cần quyền DBA để tạo bài lab cơ bản nếu user có quyền trên schema riêng. Các truy vấn GV$/V$ và DBA_* cần quyền phù hợp; nhờ DBA cấp quyền đọc tối thiểu hoặc chạy truy vấn giám sát bằng tài khoản vận hành.

### 2.2. Xác nhận database và service

Kết nối bằng JDBC URL service name đã được DBA cung cấp:

~~~text
jdbc:oracle:thin:@//dbhost.example.com:1521/labpdb.example.com
~~~

Sau khi kết nối, xác nhận database, PDB, service và user:

~~~sql
SELECT
    sys_context('USERENV', 'DB_NAME')       AS db_name,
    sys_context('USERENV', 'CON_NAME')      AS con_name,
    sys_context('USERENV', 'SERVICE_NAME')  AS service_name,
    sys_context('USERENV', 'SESSION_USER')  AS session_user,
    sys_context('USERENV', 'INSTANCE_NAME') AS instance_name
FROM dual;
~~~

Đừng chạy bài lab trên service production chỉ vì URL đã có sẵn trong cấu hình máy.

### 2.3. Tạo bảng thử nghiệm

Tạo hai bảng tài khoản để thử lock/deadlock:

~~~sql
CREATE TABLE lab_account (
    account_id NUMBER(10) CONSTRAINT pk_lab_account PRIMARY KEY,
    balance    NUMBER(12,2) NOT NULL,
    note       VARCHAR2(100)
);

INSERT INTO lab_account(account_id, balance, note)
VALUES (1, 1000, 'account-1');

INSERT INTO lab_account(account_id, balance, note)
VALUES (2, 1000, 'account-2');

COMMIT;
~~~

Tạo bảng đơn hàng để thử giữ connection và chạy query:

~~~sql
CREATE TABLE lab_work (
    work_id     NUMBER(10) CONSTRAINT pk_lab_work PRIMARY KEY,
    status      VARCHAR2(20) NOT NULL,
    amount      NUMBER(12,2),
    created_at  TIMESTAMP(6) DEFAULT SYSTIMESTAMP NOT NULL
);

INSERT INTO lab_work(work_id, status, amount)
SELECT LEVEL,
       CASE WHEN MOD(LEVEL, 2) = 0 THEN 'READY' ELSE 'NEW' END,
       LEVEL * 10
FROM dual
CONNECT BY LEVEL <= 1000;

COMMIT;
~~~

### 2.4. Gắn MODULE và ACTION cho session lab

Khi ứng dụng dùng DBMS_APPLICATION_INFO, DBA có thể nhận diện connection theo module/action:

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'OraclePoolLab',
        action_name => 'PoolExhaustion'
    );
END;
/
~~~

JDBC cũng có thể đặt module/action bằng API Oracle JDBC hoặc gọi package qua callable statement. Việc gắn module hữu ích khi nhiều ứng dụng cùng dùng database service.

### 2.5. Ghi nhận baseline

Trước mỗi kịch bản, ghi:
- Số request/thread đang chạy.
- Pool maximum, active, idle và waiting.
- Thời gian chờ lấy connection.
- Số session Oracle của module lab.
- SQL_ID và wait event.
- CPU, memory, I/O nếu có.
- Error count và latency p50/p95/p99.

Không thể kết luận bài lab thành công chỉ vì thấy một exception. Cần chứng minh trạng thái pool/database trước, trong và sau sự cố.

## 3. Cấu hình connection pool

### 3.1. Pool quản lý điều gì?

Connection pool giữ một tập physical database connection và cấp chúng cho thread khi cần. Khi code gọi close trên connection được mượn từ pool, thông thường connection được trả về pool thay vì đóng TCP/database session ngay lập tức.

Pool thường quản lý:
- Maximum pool size.
- Minimum idle connections.
- Acquisition timeout.
- Validation timeout.
- Idle timeout.
- Maximum lifetime.
- Keepalive.
- Connection validation.
- Metrics và leak detection.

Pool không quản lý transaction business thay cho ứng dụng. Ứng dụng vẫn phải commit/rollback và đóng resource đúng cách.

### 3.2. Ví dụ Spring Boot với HikariCP

~~~properties
spring.datasource.url=jdbc:oracle:thin:@//dbhost.example.com:1521/labpdb.example.com
spring.datasource.username=LAB_APP
spring.datasource.password=SET_FROM_SECRET_STORE
spring.datasource.driver-class-name=oracle.jdbc.OracleDriver

spring.datasource.hikari.pool-name=OracleLabPool
spring.datasource.hikari.maximum-pool-size=5
spring.datasource.hikari.minimum-idle=2
spring.datasource.hikari.connection-timeout=3000
spring.datasource.hikari.validation-timeout=1000
spring.datasource.hikari.idle-timeout=600000
spring.datasource.hikari.max-lifetime=1800000
spring.datasource.hikari.keepalive-time=120000
spring.datasource.hikari.leak-detection-threshold=10000
~~~

Đây là cấu hình lab để thấy timeout rõ ràng. Không sao chép các con số này vào production mà chưa tính số replica, database capacity, network timeout và SLA.

### 3.3. Ý nghĩa các thông số HikariCP

| Thông số | Đơn vị | Ý nghĩa |
| --- | --- | --- |
| maximumPoolSize | connection | Số physical connection tối đa trong pool |
| minimumIdle | connection | Số connection idle mục tiêu |
| connectionTimeout | ms | Thời gian chờ lấy connection từ pool |
| validationTimeout | ms | Thời gian tối đa kiểm tra connection |
| idleTimeout | ms | Thời gian idle trước khi pool có thể loại connection dư |
| maxLifetime | ms | Tuổi tối đa connection trước khi recycle |
| keepaliveTime | ms | Chu kỳ kiểm tra/giữ connection idle nếu được cấu hình |
| leakDetectionThreshold | ms | Ngưỡng ghi log connection được mượn quá lâu |

Một số quy tắc:
- maximumPoolSize giới hạn concurrency ở pool, không phải số request tối đa của ứng dụng.
- connectionTimeout là thời gian chờ connection trong pool; nó không thay thế connect timeout của Oracle JDBC.
- leakDetectionThreshold chỉ cảnh báo connection được giữ lâu hơn ngưỡng. Một transaction hợp lệ chạy lâu cũng có thể bị cảnh báo.
- maxLifetime nên thấp hơn giới hạn lifetime do database, firewall hoặc network infrastructure áp đặt nếu môi trường có giới hạn đó.
- validationTimeout phải nhỏ hơn connectionTimeout theo yêu cầu HikariCP.
- keepaliveTime phải nhỏ hơn maxLifetime và chỉ áp dụng với connection idle theo semantics của pool.

### 3.4. Tính pool size theo toàn hệ thống

Không chỉ tính một JVM. Nếu có nhiều replica:

~~~text
Tổng connection tối đa
= số application replica × maximumPoolSize
  + batch/worker pool
  + admin/monitoring
  + các client khác
~~~

Ví dụ 8 replica, mỗi replica maximumPoolSize=20:

~~~text
8 × 20 = 160 connection tối đa từ web application
~~~

Cộng thêm batch, scheduler, BI, monitoring và dự phòng DBA. Tổng này phải nằm trong database capacity với headroom phù hợp.

Không đặt pool size bằng số thread của web server. Một ứng dụng có 200 thread không nhất thiết cần 200 connection Oracle; connection giữ lâu có thể làm DB contention tăng và throughput giảm.

### 3.5. Đo pool bằng MXBean

Hikari cung cấp PoolMXBean để đọc trạng thái:

~~~java
HikariPoolMXBean poolBean = dataSource.getHikariPoolMXBean();

int active = poolBean.getActiveConnections();
int idle = poolBean.getIdleConnections();
int total = poolBean.getTotalConnections();
int waiting = poolBean.getThreadsAwaitingConnection();
~~~

Các metric quan trọng:
- Active: connection đang được ứng dụng mượn.
- Idle: connection đang rảnh.
- Total: tổng connection pool hiện có.
- Threads awaiting connection: số thread đang chờ pool.

Nếu active luôn bằng maximum, idle bằng 0 và waiting tăng, pool đang bị bão hòa. Cần tìm nguyên nhân connection được giữ lâu trước khi tăng maximumPoolSize.

### 3.6. Quan sát từ Oracle

DBA có thể đếm session theo service/module:

~~~sql
SELECT inst_id,
       service_name,
       module,
       status,
       COUNT(*) AS session_count
FROM   gv$session
WHERE  type = 'USER'
GROUP  BY inst_id, service_name, module, status
ORDER  BY inst_id, service_name, module, status;
~~~

Nếu MODULE chưa được đặt, phân nhóm theo username, machine, program và service. So sánh số session database với metric pool. Chênh lệch có thể đến từ nhiều datasource, pool, admin connection hoặc connection chưa được trả.

## 4. Lab A — Mô phỏng pool cạn

### 4.1. Mục tiêu

Tạo pool tối đa 3 connection và chạy 8 worker cùng lúc. Ba worker đầu lấy connection và giữ trong vài giây; worker còn lại chờ. Với connectionTimeout ngắn, một số worker sẽ hết thời gian chờ lấy connection.

Đây là mô phỏng có chủ đích. Trong production, không giữ connection khi sleep, chờ người dùng hoặc gọi dịch vụ bên ngoài.

### 4.2. Dependency Maven

Ví dụ dùng HikariCP và Oracle JDBC driver đã được tổ chức phê duyệt:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.zaxxer</groupId>
        <artifactId>HikariCP</artifactId>
        <version>YOUR_APPROVED_HIKARI_VERSION</version>
    </dependency>
    <dependency>
        <groupId>com.oracle.database.jdbc</groupId>
        <artifactId>ojdbc11</artifactId>
        <version>YOUR_APPROVED_OJDBC_VERSION</version>
    </dependency>
</dependencies>
~~~

Chọn artifact JDBC theo JDK và Oracle driver compatibility matrix. Không lấy version placeholder đưa thẳng vào build.

### 4.3. Java program mô phỏng

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import com.zaxxer.hikari.HikariPoolMXBean;

import java.sql.Connection;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class PoolExhaustionLab {
    public static void main(String[] args) throws Exception {
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(System.getenv("LAB_JDBC_URL"));
        config.setUsername(System.getenv("LAB_DB_USER"));
        config.setPassword(System.getenv("LAB_DB_PASSWORD"));
        config.setPoolName("PoolExhaustionLab");
        config.setMaximumPoolSize(3);
        config.setMinimumIdle(3);
        config.setConnectionTimeout(1500);
        config.setValidationTimeout(1000);

        try (HikariDataSource dataSource = new HikariDataSource(config)) {
            int workers = 8;
            CountDownLatch start = new CountDownLatch(1);
            ExecutorService executor = Executors.newFixedThreadPool(workers);
            List<Future<?>> tasks = new ArrayList<>();

            for (int i = 0; i < workers; i++) {
                final int workerId = i;
                tasks.add(executor.submit(() -> {
                    try {
                        start.await();

                        try (Connection connection = dataSource.getConnection()) {
                            System.out.println(
                                "worker-" + workerId + " acquired connection"
                            );

                            // Chỉ dùng để giữ connection trong bài lab.
                            Thread.sleep(5000);

                            System.out.println(
                                "worker-" + workerId + " returning connection"
                            );
                        }
                    } catch (SQLException e) {
                        System.out.println(
                            "worker-" + workerId + " failed: "
                            + e.getClass().getSimpleName() + ": "
                            + e.getMessage()
                        );
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    }
                }));
            }

            start.countDown();

            HikariPoolMXBean pool = dataSource.getHikariPoolMXBean();
            for (int i = 0; i < 6; i++) {
                Thread.sleep(500);
                System.out.printf(
                    "active=%d idle=%d total=%d waiting=%d%n",
                    pool.getActiveConnections(),
                    pool.getIdleConnections(),
                    pool.getTotalConnections(),
                    pool.getThreadsAwaitingConnection()
                );
            }

            for (Future<?> task : tasks) {
                task.get();
            }

            executor.shutdown();
        }
    }
}
~~~

Đặt LAB_JDBC_URL, LAB_DB_USER và LAB_DB_PASSWORD qua môi trường lab an toàn. Chạy program và quan sát log cùng MXBean.

### 4.4. Kết quả mong đợi

Với pool size 3, có thể quan sát:
- Tối đa 3 worker giữ connection cùng lúc.
- Các worker còn lại tăng số thread chờ.
- Một số worker nhận lỗi acquisition timeout sau khoảng connectionTimeout.
- Khi worker đầu tiên trả connection, worker đang chờ có thể lấy được connection nếu chưa timeout.
- Sau khi toàn bộ task kết thúc, active về 0 và idle tiến về pool minimum.

Thứ tự worker thành công/thất bại không được bảo đảm tuyệt đối vì scheduling và thời gian khởi tạo connection có thể khác nhau.

### 4.5. Quan sát trên Oracle

Trong lúc lab chạy, thực hiện:

~~~sql
SELECT inst_id,
       sid,
       serial#,
       username,
       status,
       service_name,
       module,
       machine,
       event,
       sql_id,
       logon_time
FROM   gv$session
WHERE  username = 'LAB_APP'
ORDER  BY inst_id, sid;
~~~

Nếu không thấy module, chương trình chưa gắn module hoặc driver chưa gửi metadata. Số session có thể không đúng bằng pool size ngay tại mọi thời điểm do pool startup, validation và connection lifecycle.

### 4.6. Phân tích nguyên nhân

Pool cạn không tự cho biết connection bị giữ vì:
- Query chậm.
- Lock wait.
- Transaction không commit.
- Connection leak.
- Thread chờ API bên ngoài trong transaction.
- Pool size thấp hơn concurrency hợp lệ.
- Database/network chậm khiến connection trả về muộn.

Bước kế tiếp là tìm connection owner và SQL/session tương ứng, không tăng pool ngay lập tức.

## 5. Lab B — Mô phỏng connection leak và connection giữ quá lâu

### 5.1. Leak thật và connection đang bận

**Connection leak** xảy ra khi code mượn connection nhưng không trả lại pool. Ví dụ thiếu close trong một nhánh exception hoặc giữ connection trong object sống lâu.

**Connection giữ lâu** có thể là transaction/query hợp lệ nhưng chiếm pool slot quá lâu. Leak detection có thể cảnh báo cả hai; cần xem stack trace và thời gian thực tế để phân biệt.

### 5.2. Ví dụ code dễ gây leak

~~~java
public void updateOrder(DataSource dataSource, long orderId)
        throws SQLException {
    Connection connection = dataSource.getConnection();

    PreparedStatement statement = connection.prepareStatement(
        "UPDATE lab_work SET status = 'DONE' WHERE work_id = ?"
    );
    statement.setLong(1, orderId);
    statement.executeUpdate();

    // Nếu có exception trước close, resource có thể bị giữ.
    statement.close();
    connection.close();
}
~~~

Nếu executeUpdate ném exception, lệnh close phía dưới có thể không chạy. Dùng try-with-resources để bảo đảm close:

~~~java
public void updateOrder(DataSource dataSource, long orderId)
        throws SQLException {
    String sql =
        "UPDATE lab_work SET status = 'DONE' WHERE work_id = ?";

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {

        statement.executeUpdate();
    }
}
~~~

Trong ứng dụng quản lý transaction bằng Spring, để transaction manager quản lý connection lifecycle. Không tự đóng connection do framework đang quản lý trong một transaction.

### 5.3. Leak detection của HikariCP

~~~properties
spring.datasource.hikari.leak-detection-threshold=20000
~~~

Nếu connection được mượn lâu hơn ngưỡng, Hikari ghi log stack trace nơi connection được lấy. Khi connection cuối cùng được trả, log có thể cho biết leak đã được phục hồi.

Threshold phải đủ lớn để tránh cảnh báo false positive do query/transaction hợp lệ. Đây là công cụ chẩn đoán, không phải cơ chế tự thu hồi connection.

### 5.4. Những pattern dễ giữ connection quá lâu

- Mở transaction trước khi gọi HTTP service.
- Giữ connection trong khi người dùng nhập liệu.
- Dùng synchronized/lock ứng dụng trong lúc đang giữ transaction.
- Stream ResultSet lâu nhưng không đóng.
- Không đóng Statement/ResultSet.
- Gọi nested service tạo thêm transaction/connection không cần thiết.
- Batch xử lý quá nhiều hàng trong một transaction.
- Catch exception rồi bỏ qua rollback.

Thiết kế transaction ngắn, chỉ giữ connection trong phần cần truy cập database và đóng mọi resource đúng lifecycle.

## 6. Timeout: xác định timeout xảy ra ở tầng nào

### 6.1. Bảng phân biệt timeout

| Timeout | Tầng | Đơn vị thường gặp | Điều khiển |
| --- | --- | --- | --- |
| Request/deadline timeout | HTTP/RPC/application | ms hoặc s | Framework/gateway/client |
| Pool acquisition timeout | Connection pool | ms | Hikari connectionTimeout |
| Login/connect timeout | JDBC/Oracle Net | driver-specific | JDBC/Oracle Net properties |
| Network read timeout | Socket/JDBC | ms | Oracle JDBC ReadTimeout hoặc JDBC network timeout |
| Lock wait timeout | Oracle transaction | s | DML_LOCK_TIMEOUT hoặc SELECT FOR UPDATE WAIT |
| Statement query timeout | JDBC statement | s | Statement.setQueryTimeout |
| Transaction timeout | Transaction manager | s | Spring/JTA/container |
| Validation timeout | Connection pool | ms | Hikari validationTimeout |

Timeout ở một tầng không tự động hủy công việc ở mọi tầng khác. Ví dụ HTTP request hết deadline có thể làm client ngừng chờ, trong khi JDBC statement vẫn chạy nếu ứng dụng không cancel/rollback đúng cách.

### 6.2. Pool acquisition timeout

Hikari:

~~~properties
spring.datasource.hikari.connection-timeout=3000
~~~

Request chờ tối đa khoảng 3 giây để lấy connection từ pool. Nếu pool hết connection và không có connection được trả, Hikari ném lỗi lấy connection.

Lỗi này thường khác với lỗi listener hoặc authentication. Xem exception cause, pool metrics và log tạo physical connection để biết request đã chờ pool hay driver đang mở kết nối.

### 6.3. JDBC login timeout

JDBC DriverManager hỗ trợ login timeout theo giây:

~~~java
DriverManager.setLoginTimeout(10);
~~~

Login timeout là một thiết lập cấp DriverManager và có thể ảnh hưởng các connection được mở qua DriverManager trong JVM. Với DataSource/pool, kiểm tra cách driver và pool sử dụng timeout property. Không giả định nó thay thế mọi timeout Oracle Net.

### 6.4. Oracle Net connect timeout

Oracle Net có các tham số timeout cho quá trình kết nối tới listener/endpoint, ví dụ CONNECT_TIMEOUT và TRANSPORT_CONNECT_TIMEOUT trong connect descriptor/Easy Connect Plus theo phiên bản hỗ trợ.

Ví dụ descriptor minh họa:

~~~text
jdbc:oracle:thin:@(DESCRIPTION=
  (CONNECT_TIMEOUT=10)
  (TRANSPORT_CONNECT_TIMEOUT=3)
  (ADDRESS=(PROTOCOL=TCP)(HOST=dbhost.example.com)(PORT=1521))
  (CONNECT_DATA=(SERVICE_NAME=labpdb.example.com))
)
~~~

Đơn vị và phạm vi áp dụng phụ thuộc tham số/driver. Kiểm tra tài liệu Oracle JDBC và Oracle Net đúng version. Đây là timeout mở kết nối, không phải thời gian chạy query.

### 6.5. JDBC network/read timeout

Oracle JDBC hỗ trợ thuộc tính network read timeout theo driver, thường được cấu hình bằng oracle.jdbc.ReadTimeout với đơn vị milliseconds.

Ví dụ DataSource property:

~~~java
Properties properties = new Properties();
properties.setProperty("oracle.jdbc.ReadTimeout", "30000");
~~~

Cách truyền property phụ thuộc DriverManager, OracleDataSource hoặc pool. Kiểm tra đúng API driver đang dùng.

JDBC cũng có Connection.setNetworkTimeout(Executor, milliseconds) từ JDBC 4.1. Phương thức này đặt thời gian tối đa cho một lần chờ phản hồi network theo JDBC contract; driver phải hỗ trợ và executor phải phù hợp.

~~~java
connection.setNetworkTimeout(networkExecutor, 30000);
~~~

Network timeout không phải query timeout. Khi hết hạn, connection có thể bị đánh dấu không còn usable; pool cần loại bỏ và tạo connection mới.

### 6.6. Statement query timeout

JDBC:

~~~java
try (PreparedStatement statement =
         connection.prepareStatement(
             "SELECT work_id, status FROM lab_work WHERE work_id = ?")) {

    statement.setLong(1, 10L);
    statement.setQueryTimeout(5);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            System.out.println(resultSet.getLong("work_id"));
        }
    }
}
~~~

setQueryTimeout dùng giây. Khi hết thời gian, driver cố gắng hủy statement theo JDBC semantics. Kiểm tra driver/database behavior và trạng thái transaction sau cancel.

### 6.7. Lock wait timeout

Có thể giới hạn DML lock wait theo session:

~~~sql
ALTER SESSION SET DML_LOCK_TIMEOUT = 5;
~~~

DML cần lock có thể chờ tối đa theo thiết lập này trước khi trả lỗi resource busy nếu lock chưa được giải phóng.

Đối với SELECT FOR UPDATE, có thể ghi rõ:

~~~sql
SELECT account_id, balance
FROM   lab_account
WHERE  account_id = 1
FOR UPDATE WAIT 5;
~~~

Hoặc không chờ:

~~~sql
SELECT account_id, balance
FROM   lab_account
WHERE  account_id = 1
FOR UPDATE NOWAIT;
~~~

Lock timeout là chính sách chờ lock. Nó không thay thế deadlock detection; deadlock cycle được Oracle phát hiện và trả ORA-00060.

### 6.8. Timeout phải theo một deadline tổng

Ví dụ request có deadline 8 giây:
- Pool acquisition: tối đa 1 giây.
- Kết nối mới nếu cần: tối đa 2 giây.
- SQL statement: tối đa 4 giây.
- Còn thời gian cho xử lý kết quả và trả response.

Không cấu hình mọi tầng 30 giây trong khi HTTP gateway chỉ chờ 5 giây. Nếu timeout trong tầng dưới dài hơn deadline request, ứng dụng có thể tiếp tục làm việc sau khi client đã bỏ cuộc.

Cũng không đặt tất cả timeout bằng nhau một cách máy móc; tính thời gian setup, retry, fetch và cleanup.

## 7. Lab C — Mô phỏng lock wait và timeout

### 7.1. Chuẩn bị hai SQL session

Mở Session A và Session B trên cùng schema LAB_APP.

Session A:

~~~sql
ALTER SESSION SET DML_LOCK_TIMEOUT = 30;

UPDATE lab_account
SET    balance = balance - 100
WHERE  account_id = 1;

-- Giữ transaction, chưa COMMIT.
~~~

Session A giữ row lock trên account 1.

Session B:

~~~sql
ALTER SESSION SET DML_LOCK_TIMEOUT = 5;

UPDATE lab_account
SET    balance = balance + 50
WHERE  account_id = 1;
~~~

Session B chờ lock của Session A. Sau khoảng thời gian timeout theo cấu hình, Session B nhận lỗi resource busy nếu lock chưa được giải phóng.

### 7.2. Quan sát wait event

Trong session DBA:

~~~sql
SELECT inst_id,
       sid,
       serial#,
       username,
       status,
       event,
       wait_class,
       seconds_in_wait,
       blocking_instance,
       blocking_session,
       sql_id
FROM   gv$session
WHERE  username = 'LAB_APP'
ORDER  BY inst_id, sid;
~~~

Session B thường có wait liên quan enqueue/transaction khi đang đợi row lock. Tên wait event cụ thể phụ thuộc loại lock và release.

### 7.3. Giải phóng lock

Session A:

~~~sql
ROLLBACK;
~~~

Sau khi rollback hoàn tất, Session B có thể tiếp tục nếu chưa timeout. Nếu Session B đã nhận timeout error, statement đó đã kết thúc; ứng dụng phải quyết định có thử lại transaction hay không.

### 7.4. So sánh NOWAIT, WAIT và DML_LOCK_TIMEOUT

- NOWAIT: không chờ, trả lỗi ngay nếu lock không có sẵn.
- WAIT n: chờ tối đa số giây được chỉ định cho SELECT FOR UPDATE.
- DML_LOCK_TIMEOUT: điều khiển DML lock wait theo session/system scope được hỗ trợ.

Không nhầm với DDL_LOCK_TIMEOUT, vốn dành cho DDL lock wait. Timeout không giải phóng blocker và không sửa logic giữ transaction lâu.

## 8. Lab D — Tạo deadlock có kiểm soát

### 8.1. Nguyên nhân deadlock

Deadlock xảy ra khi các transaction khóa tài nguyên theo thứ tự khác nhau.

Ví dụ:
- Transaction A khóa account 1 rồi cần account 2.
- Transaction B khóa account 2 rồi cần account 1.

Cả hai đều đang giữ một row lock và đợi row còn lại. Oracle phát hiện chu trình chờ và một statement nhận ORA-00060.

### 8.2. Chuẩn bị lại dữ liệu

~~~sql
UPDATE lab_account
SET balance = 1000
WHERE account_id IN (1, 2);

COMMIT;
~~~

### 8.3. Session A — khóa hàng thứ nhất

~~~sql
UPDATE lab_account
SET balance = balance - 10
WHERE account_id = 1;

-- Chưa COMMIT.
~~~

### 8.4. Session B — khóa hàng thứ hai

~~~sql
UPDATE lab_account
SET balance = balance - 20
WHERE account_id = 2;

-- Chưa COMMIT.
~~~

### 8.5. Session A — yêu cầu hàng Session B đang giữ

~~~sql
UPDATE lab_account
SET balance = balance + 20
WHERE account_id = 2;
~~~

Session A sẽ chờ Session B.

### 8.6. Session B — tạo chu trình deadlock

~~~sql
UPDATE lab_account
SET balance = balance + 10
WHERE account_id = 1;
~~~

Session B yêu cầu row 1 đang bị Session A giữ. Oracle phát hiện deadlock và một statement nhận ORA-00060. Session được chọn làm victim phụ thuộc tình trạng thực tế; không giả định luôn là Session B.

### 8.7. Oracle làm gì khi phát hiện deadlock?

Oracle phát hiện deadlock và rollback statement gây ra deadlock ở một transaction, sau đó trả ORA-00060 cho client. Việc rollback statement không đồng nghĩa toàn bộ transaction đã được rollback.

Các statement trước đó trong transaction có thể vẫn chưa commit và vẫn giữ lock. Ứng dụng nên rollback toàn bộ transaction nếu business operation là một đơn vị nguyên tử, sau đó mới cân nhắc retry từ đầu.

Không tiếp tục commit transaction một cách mù quáng sau ORA-00060. Xác định transaction state và business semantics trước.

### 8.8. Hoàn tất lab và khôi phục dữ liệu

Ở cả hai session, kiểm tra transaction state rồi rollback rõ ràng:

~~~sql
ROLLBACK;
~~~

Sau đó xác nhận dữ liệu:

~~~sql
SELECT account_id, balance
FROM   lab_account
ORDER  BY account_id;
~~~

Đặt lại giá trị ban đầu nếu cần và commit trong lab. Không dùng số dư sau deadlock làm kết quả nghiệp vụ mong đợi; mục tiêu của lab là quan sát lock cycle và cách Oracle báo lỗi.

## 9. Phân tích ORA-00060 và deadlock graph

### 9.1. Đọc lỗi từ ứng dụng

ORA-00060 thường được bọc trong SQLException hoặc exception framework. Ghi lại:
- SQL operation và transaction boundary.
- SQL_ID nếu lấy được.
- Request/correlation ID.
- Module/action/client identifier.
- Instance và service.
- Thời điểm lỗi.
- Exception chain đầy đủ.

Không log password, bind value nhạy cảm hoặc dữ liệu cá nhân chỉ để điều tra deadlock.

### 9.2. Tìm trace file

DBA có thể xác định vị trí trace/diagnostic:

~~~sql
SELECT name, value
FROM   v$diag_info
WHERE  name IN (
    'Diag Trace',
    'Diag Alert',
    'Default Trace File'
);
~~~

Deadlock graph thường được ghi trong trace/alert diagnostics. Nội dung giúp xác định object, row/resource và transaction tham gia chu trình. Cú pháp và đường dẫn cụ thể tùy ADR configuration.

### 9.3. Tìm session liên quan

~~~sql
SELECT inst_id,
       sid,
       serial#,
       username,
       sql_id,
       prev_sql_id,
       event,
       blocking_instance,
       blocking_session,
       module,
       action,
       client_identifier
FROM   gv$session
WHERE  username = 'LAB_APP'
ORDER  BY inst_id, sid;
~~~

Deadlock có thể đã kết thúc trước khi DBA chạy truy vấn, vì Oracle phát hiện và phá chu trình nhanh. Khi đó trace file và application log là bằng chứng quan trọng hơn snapshot session hiện tại.

### 9.4. Đối chiếu object và SQL

Dùng DBA_OBJECTS/ALL_OBJECTS để tìm object ID từ deadlock graph:

~~~sql
SELECT owner,
       object_name,
       object_type,
       object_id
FROM   dba_objects
WHERE  object_id = :object_id;
~~~

Nếu graph chứa ROWID, có thể phân tích row trong môi trường phù hợp, nhưng không giả định mọi lock type đều ánh xạ đơn giản tới một row. Đọc đầy đủ graph và SQL trace.

### 9.5. Deadlock khác với lock timeout

| Tình huống | Kết quả thường thấy | Cách xử lý |
| --- | --- | --- |
| Một session chờ blocker | Chờ tới khi blocker kết thúc hoặc timeout | Xác định blocker, transaction và wait policy |
| SELECT FOR UPDATE NOWAIT | Lỗi ngay nếu row bị khóa | Retry/return busy theo business rule |
| SELECT FOR UPDATE WAIT n | Lỗi khi vượt thời gian chờ | Điều chỉnh wait policy và transaction duration |
| DML_LOCK_TIMEOUT hết hạn | Resource busy/lock wait timeout | Xử lý blocker và retry có giới hạn |
| Deadlock cycle | ORA-00060 | Rollback transaction phù hợp, sửa lock ordering |

## 10. Ngăn deadlock trong ứng dụng

### 10.1. Khóa hàng theo cùng thứ tự

Nếu nhiều transaction cần cập nhật account 1 và account 2, luôn khóa theo thứ tự tăng dần account_id:

~~~sql
SELECT account_id, balance
FROM   lab_account
WHERE  account_id IN (:id1, :id2)
ORDER  BY account_id
FOR UPDATE;
~~~

Đối với nhiều câu UPDATE riêng lẻ, đảm bảo mọi code path tuân thủ cùng một thứ tự. Không dựa vào thứ tự ngẫu nhiên của input collection hoặc execution plan nếu thứ tự khóa là yêu cầu nghiệp vụ.

### 10.2. Giữ transaction ngắn

Không giữ transaction trong khi:
- Gọi HTTP/REST.
- Chờ message queue.
- Chờ người dùng.
- Thực hiện file I/O lâu.
- Chạy batch lớn không có checkpoint.
- Chờ lock ứng dụng khác.

Đọc/ghi cần thiết, commit/rollback sớm rồi thực hiện công việc bên ngoài transaction.

### 10.3. Cập nhật theo một đơn vị nghiệp vụ

Nếu transfer tiền cần trừ tài khoản nguồn và cộng tài khoản đích, thực hiện trong một transaction với lock order nhất quán. Dùng constraint và validation để bảo vệ invariant. Không commit giữa hai thao tác nếu business yêu cầu atomicity.

### 10.4. Index và foreign key

Index phù hợp có thể giảm thời gian tìm hàng và một số dạng contention. Với foreign key, đánh giá index trên cột child trong workload có update/delete parent; thiếu index có thể làm Oracle cần lock rộng hơn trong một số thao tác parent key.

Không tạo index mọi foreign key một cách máy móc. Đo workload, cardinality, DML overhead và execution plan.

### 10.5. Pessimistic và optimistic locking

Pessimistic locking dùng SELECT FOR UPDATE để khóa trước khi cập nhật. Cần kiểm soát thứ tự và thời gian giữ lock.

Optimistic locking dùng version column để phát hiện concurrent update. Trong JPA, @Version có thể giúp phát hiện stale write, nhưng không loại bỏ mọi deadlock do transaction còn truy cập nhiều object theo thứ tự khác nhau.

### 10.6. Retry đúng cách

ORA-00060 có thể là lỗi transient, nhưng retry cần:
1. Rollback toàn transaction nếu business unit phải atomic.
2. Trả/loại connection theo trạng thái driver/pool.
3. Đợi backoff ngắn có jitter.
4. Bắt đầu transaction mới.
5. Giới hạn số lần retry.
6. Ghi metrics để phát hiện deadlock lặp lại.

Không retry statement riêng lẻ khi các statement trước đã thay đổi transaction state. Không retry vô hạn vì có thể tạo retry storm.

### 10.7. Idempotency và commit outcome

Timeout mạng có thể xảy ra sau khi Oracle đã commit nhưng trước khi ứng dụng nhận phản hồi. Khi đó client không biết chắc transaction thành công hay chưa.

Dùng:
- Request ID hoặc idempotency key.
- Unique constraint chống tạo bản ghi trùng.
- Trạng thái nghiệp vụ có thể tra cứu.
- Transaction boundary rõ ràng.
- Cơ chế đối soát khi commit outcome không xác định.

Retry một thao tác thanh toán hoặc tạo đơn hàng mà không có idempotency có thể tạo giao dịch trùng.

## 11. Khôi phục pool cạn có kiểm soát

### 11.1. Thu thập trạng thái trước

Ghi:
- Pool active/idle/total/waiting.
- Acquisition timeout count.
- Connection creation failure.
- Leak detection log.
- Thread dump của ứng dụng nếu cần.
- Session theo module/service.
- SQL_ID, wait event và blocker.
- Số request đang chờ và error rate.

Không restart ứng dụng trước khi lưu bằng chứng; restart có thể xóa dấu vết connection owner và thread stack.

### 11.2. Giảm admission và bảo vệ hệ thống

Nếu pool đang cạn:
- Giảm concurrency ở endpoint/job gây tải.
- Tạm dừng batch có thể trì hoãn.
- Dùng queue/backpressure hoặc trả lỗi busy có kiểm soát.
- Giới hạn retry ở client.
- Giữ capacity cho health check/admin nếu kiến trúc yêu cầu.
- Không tăng pool size vượt DB capacity.

Mục tiêu là ngăn request mới làm hàng đợi dài hơn trong khi xử lý connection đang bị giữ.

### 11.3. Tìm connection đang bị giữ

Đối chiếu:
- Hikari active connection.
- Thread dump và stack trace leak detection.
- GV$SESSION theo username/service/module/machine.
- SQL hiện tại và previous SQL.
- Transaction start time và undo.
- Wait event/blocker.

Nếu active connection đang chờ row lock, giải quyết blocker hoặc transaction. Nếu connection idle trong database nhưng vẫn active ở pool, xem ứng dụng đang giữ connection mà không chạy SQL hay không.

### 11.4. Trả connection bằng đường nghiệp vụ

Ưu tiên:
- Cho transaction hợp lệ hoàn tất.
- Sửa code path thiếu close.
- Rollback transaction bị bỏ quên theo owner/runbook.
- Cancel statement runaway.
- Giảm workload đang chiếm pool.
- Đóng session stale đã xác định rõ.

Không kill tất cả session của user ứng dụng để làm pool trống. Việc đó có thể làm mọi request lỗi đồng thời, kích hoạt reconnect storm và rollback hàng loạt transaction.

### 11.5. Khi nào cần recycle pool hoặc restart ứng dụng?

Có thể cần recycle datasource/process nếu pool state bị hỏng hoặc connection không thể phục hồi, nhưng chỉ sau khi:
- Đã thu thập pool metrics và thread dump.
- Đã xác định transaction/session cần xử lý.
- Đã đánh giá request in-flight.
- Có cơ chế drain traffic.
- Có capacity database cho reconnect burst.
- Có cách xác minh connection mới hoạt động.

Restart ứng dụng có thể giải phóng connection ở phía client nhưng không bảo đảm rollback trên Oracle hoàn tất tức thì. Database có thể vẫn đang cleanup transaction cũ.

### 11.6. Tránh reconnect storm

Sau khi pool bị recycle, tất cả replica có thể đồng thời tạo connection mới. Điều này tạo burst authentication/session creation.

Kiểm soát bằng:
- Staggered restart/rolling deployment.
- MinimumIdle vừa phải.
- Retry backoff có jitter.
- Connection creation rate limit nếu có.
- Database session capacity và process headroom.
- Service health check trước khi nhận traffic.

## 12. Khôi phục sau timeout

### 12.1. Xác định timeout nào đã hết

Ghi exception class/message và tầng phát sinh:
- Hikari acquisition timeout.
- Driver connect/login timeout.
- Socket/read timeout.
- Statement query timeout.
- Lock wait timeout.
- HTTP/request deadline.
- Transaction timeout.

Không ánh xạ mọi lỗi timeout thành ORA-00060 hoặc connection failure. Đọc nested SQLException và SQLState/vendor code.

### 12.2. Hủy statement và transaction đúng cách

Nếu query timeout:
- Xác định statement có thực sự bị cancel không.
- Kiểm tra connection còn usable không.
- Rollback transaction nếu business operation không hoàn chỉnh.
- Đóng ResultSet/Statement.
- Trả connection về pool theo API.
- Không tái sử dụng connection nếu driver báo trạng thái lỗi.

Nếu request timeout xảy ra ở tầng HTTP, code xử lý cancellation phải truyền xuống tầng JDBC khi phù hợp. Client ngừng chờ không tự động hủy SQL.

### 12.3. Kiểm tra commit outcome

Nếu lỗi xảy ra quanh COMMIT hoặc network mất phản hồi:
- Không tự kết luận transaction rollback.
- Tra cứu bằng request ID/business key.
- Kiểm tra dữ liệu đã commit chưa.
- Dùng idempotency để retry an toàn.
- Đối soát các thao tác không thể xác định kết quả.

Đây là điểm đặc biệt quan trọng với thanh toán, đặt hàng và các operation có side effect.

### 12.4. Timeout lặp lại là tín hiệu quá tải

Nếu timeout tăng:
- Kiểm tra pool waiting và DB active sessions.
- Kiểm tra CPU, I/O, storage và wait class.
- Kiểm tra SQL plan và bind values.
- Kiểm tra lock chain.
- Kiểm tra network/listener.
- Kiểm tra số retry và request concurrency.

Tăng timeout chỉ làm request chờ lâu hơn. Tăng pool chỉ làm tăng concurrency. Cả hai có thể khiến database chịu tải nặng hơn nếu nguyên nhân là resource saturation.

## 13. Runbook khôi phục sau deadlock

### 13.1. Giữ bằng chứng

Thu thập:
- ORA-00060 stack.
- Deadlock graph/trace file.
- SQL_ID và SQL text theo quyền.
- Module/action/client identifier.
- Transaction boundary và request ID.
- Object/row/resource trong graph.
- Application retry log.
- Thời điểm và tần suất deadlock.

### 13.2. Xử lý transaction lỗi

Ứng dụng nên rollback transaction theo business boundary. Trong JDBC:

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        performBusinessOperation(connection);
        connection.commit();
    } catch (SQLException e) {
        connection.rollback();
        throw e;
    }
}
~~~

Ví dụ đơn giản này minh họa rollback khi lỗi. Với Spring @Transactional, để transaction manager điều khiển commit/rollback; kiểm tra rollback rules, đặc biệt khi exception được catch và không rethrow.

### 13.3. Retry có giới hạn

Ví dụ pseudocode:

~~~java
int maxAttempts = 3;

for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
        executeWholeTransaction();
        break;
    } catch (SQLException e) {
        rollbackCurrentTransaction();

        if (!isOracleDeadlock(e) || attempt == maxAttempts) {
            throw e;
        }

        sleepWithExponentialBackoffAndJitter(attempt);
    }
}
~~~

isOracleDeadlock phải kiểm tra vendor error code 60 trong SQLException chain, không chỉ so khớp message. Retry phải bắt đầu transaction mới và operation phải an toàn khi chạy lại.

### 13.4. Khắc phục nguyên nhân

Từ deadlock graph:
- Liệt kê object và thứ tự lock.
- Xác định code path tạo thứ tự ngược nhau.
- Chuẩn hóa lock ordering.
- Giảm transaction duration.
- Thêm index khi có bằng chứng phù hợp.
- Chia batch.
- Xem xét SELECT FOR UPDATE WAIT/NOWAIT.
- Bổ sung idempotency và bounded retry.

Không dùng kill session để sửa deadlock sau khi Oracle đã trả ORA-00060; deadlock cycle đã được phá. Hãy xử lý transaction state và nguyên nhân tạo chu trình.

## 14. Bộ truy vấn quan sát trong lúc sự cố

### 14.1. Session theo service/module

~~~sql
SELECT inst_id,
       service_name,
       module,
       action,
       status,
       COUNT(*) AS sessions
FROM   gv$session
WHERE  type = 'USER'
GROUP  BY inst_id, service_name, module, action, status
ORDER  BY sessions DESC;
~~~

### 14.2. Session đang chờ

~~~sql
SELECT inst_id,
       sid,
       serial#,
       username,
       sql_id,
       event,
       wait_class,
       seconds_in_wait,
       state,
       blocking_instance,
       blocking_session,
       module,
       action
FROM   gv$session
WHERE  state = 'WAITING'
  AND  wait_class <> 'Idle'
ORDER  BY seconds_in_wait DESC;
~~~

### 14.3. Transaction lâu

~~~sql
SELECT s.inst_id,
       s.sid,
       s.serial#,
       s.username,
       s.module,
       s.sql_id,
       t.start_time,
       t.used_ublk,
       t.used_urec
FROM   gv$transaction t
JOIN   gv$session s
       ON s.inst_id = t.inst_id
      AND s.taddr = t.addr
ORDER  BY t.start_time;
~~~

### 14.4. Resource limit

~~~sql
SELECT inst_id,
       resource_name,
       current_utilization,
       max_utilization,
       limit_value
FROM   gv$resource_limit
WHERE  resource_name IN ('sessions', 'processes')
ORDER  BY inst_id, resource_name;
~~~

So sánh current/max utilization với limit_value. Một đỉnh lịch sử có thể cho thấy workload burst, nhưng không tự xác định nguyên nhân pool exhaustion.

### 14.5. Lock waiter và blocker

~~~sql
SELECT inst_id,
       sid,
       serial#,
       username,
       event,
       blocking_instance,
       blocking_session,
       final_blocking_instance,
       final_blocking_session,
       sql_id,
       module
FROM   gv$session
WHERE  blocking_session IS NOT NULL
   OR  final_blocking_session IS NOT NULL
ORDER  BY inst_id, sid;
~~~

### 14.6. Alert log và diagnostic trace

~~~sql
SELECT name, value
FROM   v$diag_info
WHERE  name IN (
    'Diag Trace',
    'Diag Alert',
    'Default Trace File'
);
~~~

Dùng ADRCI hoặc công cụ monitoring theo quyền vận hành để đọc trace deadlock và alert log. Không xóa trace/alert file để dọn lỗi trước khi lưu evidence.

## 15. Kiểm tra sức khỏe sau khôi phục

### 15.1. Pool metrics

Sau khi xử lý:
- Active connection giảm về mức bình thường.
- Idle connection được tạo lại theo policy.
- Waiting threads về 0.
- Acquisition timeout không tiếp tục tăng.
- Connection creation failure không lặp.
- Leak warning không còn tái diễn.

Theo dõi đủ lâu để bao phủ một chu kỳ workload, không chỉ một lần request thành công.

### 15.2. Database sessions

Xác nhận:
- Session count ổn định.
- Không còn blocker ngoài dự kiến.
- Transaction cũ đã kết thúc/rollback.
- Không còn session KILLED kéo dài bất thường.
- Service/PDB/instance đúng trạng thái.
- Resource limit còn headroom.

### 15.3. Ứng dụng

Kiểm tra:
- Request success rate.
- p95/p99 latency.
- HTTP 5xx và database exception.
- Queue depth.
- Retry count.
- Thread pool saturation.
- Connection pool pending.
- Business data consistency.

Một endpoint trả HTTP 200 chưa đủ chứng minh dữ liệu nghiệp vụ đã đúng sau timeout/deadlock.

### 15.4. Đối soát dữ liệu lab

Sau khi hoàn tất kịch bản, kiểm tra:

~~~sql
SELECT account_id, balance, note
FROM   lab_account
ORDER  BY account_id;

SELECT status, COUNT(*) AS row_count
FROM   lab_work
GROUP  BY status
ORDER  BY status;
~~~

Đặt lại dữ liệu lab theo trạng thái ban đầu nếu bài thực hành yêu cầu và commit có chủ đích.

## 16. Thiết kế timeout và pool cho production

### 16.1. Một deadline xuyên suốt

Thiết kế một request deadline ở tầng API, rồi chia ngân sách cho:
- Pool acquisition.
- Kết nối mới nếu cần.
- SQL execution.
- Fetch/serialization.
- Commit/cleanup.
- Response.

Tầng dưới nên có timeout phù hợp với deadline tầng trên để ứng dụng còn thời gian hủy, rollback và trả lỗi có kiểm soát.

### 16.2. Pool size và database capacity

Tính tổng pool trên mọi replica, worker, scheduler và client. Để headroom cho:
- DBA/admin.
- Monitoring.
- Batch critical.
- Failover khi một RAC instance mất.
- Rolling deploy khi replica tạm thời tăng.
- Background/maintenance sessions.

Nếu RAC có service preferred/available instances, đánh giá worst-case connection distribution khi một instance không còn phục vụ.

### 16.3. Backpressure thay vì tăng pool vô hạn

Khi pool bão hòa:
- Giới hạn concurrency theo endpoint.
- Queue có giới hạn.
- Reject sớm request không thể phục vụ trong deadline.
- Dùng circuit breaker cho dependency chậm.
- Không giữ JDBC connection khi chờ external service.
- Giới hạn retry.

Pool lớn hơn không nhất thiết tăng throughput; nó có thể tăng số session tranh CPU, latch, buffer và lock.

### 16.4. Metrics và cảnh báo

Nên theo dõi:
- Hikari active/idle/total/pending.
- Acquisition timeout.
- Connection creation/validation failure.
- Connection usage duration.
- Transaction duration.
- Oracle session count theo service/module.
- Wait event và blocking session.
- ORA-00060 rate.
- SQL latency/DB time.
- Database process/session utilization.
- Application request latency và error rate.

Cảnh báo khi pending/active tăng liên tục, acquisition timeout xuất hiện, hoặc deadlock rate vượt baseline. Không chỉ cảnh báo khi pool đã cạn hoàn toàn.

## 17. Những hiểu nhầm thường gặp

**“Pool cạn nghĩa là Oracle hết session.”** Không. Pool có thể hết connection trong khi database còn capacity lớn.

**“Tăng maximumPoolSize luôn sửa pool exhaustion.”** Không. Nếu connection bị leak, lock hoặc query chậm, pool lớn hơn chỉ trì hoãn sự cố và tăng tải database.

**“Hikari connectionTimeout là Oracle connect timeout.”** Không. Nó chủ yếu giới hạn thời gian chờ lấy connection từ pool; driver/Oracle Net có timeout riêng.

**“HTTP timeout tự hủy SQL.”** Không. Ứng dụng phải truyền cancellation xuống JDBC và xử lý transaction state.

**“Statement query timeout luôn rollback toàn transaction.”** Không. Kiểm tra driver, statement và transaction; rollback business transaction khi cần.

**“Session inactive không giữ lock.”** Không. Session inactive có thể vẫn có transaction chưa commit.

**“Deadlock là một session chờ quá lâu.”** Không. Deadlock là chu trình chờ; blocking đơn lẻ không nhất thiết là deadlock.

**“ORA-00060 rollback toàn bộ transaction.”** Không. Oracle rollback statement gây deadlock; transaction còn lại cần được ứng dụng xử lý theo business boundary.

**“Có ORA-00060 thì phải kill hai session.”** Không. Oracle đã phá chu trình. Hãy rollback transaction phù hợp và sửa lock ordering.

**“Retry statement lỗi là đủ.”** Không. Với transaction nguyên tử, rollback và retry toàn transaction trong transaction mới.

**“Leak detection chứng minh có leak.”** Không. Connection hợp lệ nhưng giữ lâu cũng có thể phát cảnh báo; xem stack trace và lifecycle.

**“Restart database sẽ giải phóng mọi vấn đề pool.”** Restart có thể ngắt session nhưng không sửa code leak, retry storm, SQL chậm hoặc transaction design.

## 18. Bài thực hành tổng hợp

Thực hiện theo thứ tự trên schema và application lab riêng. Ghi lại input, metric trước/trong/sau và expected result.

### Bài 1 — Baseline pool

Cấu hình pool size 5. Chạy workload nhẹ, ghi active/idle/total/waiting và số session Oracle.

### Bài 2 — Pool exhaustion

Dùng Java program ở Lab A với 8 worker, pool size 3 và connectionTimeout ngắn. Chụp log timeout và MXBean.

### Bài 3 — Connection leak

Tạo một nhánh code cố tình không close connection trong lab. Quan sát active tăng và leak warning. Sửa bằng try-with-resources và chạy lại.

### Bài 4 — Long transaction

Mở transaction update một hàng và giữ chưa commit. Quan sát session inactive/active, transaction và lock.

### Bài 5 — Lock timeout

Session A giữ row lock. Session B dùng DML_LOCK_TIMEOUT=5 hoặc SELECT FOR UPDATE WAIT 5. Ghi mã lỗi và thời gian chờ.

### Bài 6 — NOWAIT

Dùng SELECT FOR UPDATE NOWAIT trên hàng đang bị khóa. Quan sát lỗi trả về ngay và so sánh với WAIT.

### Bài 7 — Deadlock

Thực hiện chuỗi Session A/B ở Lab D để tạo ORA-00060. Thu thập trace/deadlock graph nếu có quyền.

### Bài 8 — Transaction rollback

Sau deadlock, kiểm tra các thay đổi trước statement lỗi. Thực hiện rollback toàn transaction và xác nhận dữ liệu.

### Bài 9 — Retry bounded

Viết retry tối đa 3 lần cho transaction idempotent. Thêm backoff/jitter và metrics; xác nhận không retry vô hạn.

### Bài 10 — Timeout statement

Dùng PreparedStatement.setQueryTimeout trong môi trường lab. Kiểm tra statement cancel, connection usability và transaction state.

### Bài 11 — Pool sau timeout

Làm một số connection bị timeout theo kịch bản test có kiểm soát. Xác nhận pool loại connection không usable và tạo lại.

### Bài 12 — Recovery runbook

Giả lập pool waiting tăng, xác định session SQL/lock, giảm admission, giải phóng transaction đúng cách và xác nhận metrics phục hồi.

### Bài 13 — Multi-replica pool budget

Tính tổng maximumPoolSize cho 6 replica, 2 worker pool và admin reserve. So sánh với sessions/processes capacity của database test.

### Bài 14 — Incident report

Viết báo cáo gồm:
- Triệu chứng và thời gian.
- Blast radius.
- Bằng chứng pool/database.
- Nguyên nhân gốc.
- Hành động khôi phục.
- Transaction/data validation.
- Metric sau khôi phục.
- Thay đổi phòng ngừa.

## 19. Mẫu incident runbook

### Trạng thái ban đầu

- Incident ID:
- Thời điểm:
- Database / DB unique name:
- Role / instance / service / PDB:
- Application version / replica count:
- Pool maximum / active / idle / waiting:
- Oracle sessions / processes:
- Error rate / p95 / p99:
- SQL_ID / wait event / blocker:
- Transaction start / undo:
- Alert/trace location:

### Phân loại sự cố

- [ ] Pool acquisition timeout.
- [ ] Physical connection creation timeout.
- [ ] Network/read timeout.
- [ ] Statement/query timeout.
- [ ] Lock wait timeout.
- [ ] ORA-00060 deadlock.
- [ ] Database session/process capacity.
- [ ] Connection leak hoặc connection giữ quá lâu.
- [ ] Khác.

### Hành động đã chọn

- Hành động:
- Phạm vi:
- Lý do và bằng chứng:
- Người phê duyệt/incident commander:
- Thời điểm bắt đầu:
- Điều kiện dừng:
- Rollback/forward-fix:

### Xác minh sau khôi phục

- Pool active/idle/waiting:
- Connection acquisition timeout:
- Oracle session/transaction:
- Blocking/deadlock:
- Application error rate:
- p95/p99 latency:
- Business data reconciliation:
- Hành động phòng ngừa:
- Người xác nhận và thời điểm:

## 20. Tài liệu tham khảo

- [Oracle Database 19c Concepts — Transactions and Data Concurrency](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/transactions.html): transaction, lock và concurrency.
- [Oracle Database 19c Administrator's Guide — Managing Processes](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-processes.html): session/process và resource management.
- [Oracle Database 19c Database Reference — V$SESSION](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SESSION.html): session state, wait event và blocker.
- [Oracle Database 19c Database Reference — V$LOCK](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-LOCK.html): enqueue lock.
- [Oracle Database 19c Database Reference — V$TRANSACTION](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-TRANSACTION.html): transaction và undo.
- [Oracle Database 19c SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): SELECT FOR UPDATE, WAIT và NOWAIT.
- [Oracle Database 19c SQL Language Reference — ALTER SESSION](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-SESSION.html): session parameter như DML_LOCK_TIMEOUT.
- [Oracle Database JDBC Developer's Guide 19c](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/): JDBC connection, timeout và statement behavior.
- [HikariCP Documentation](https://github.com/brettwooldridge/HikariCP): pool configuration, metrics, leak detection và lifecycle.
- [JDBC API — Connection](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Connection.html): transaction, close và network timeout.
- [JDBC API — Statement](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Statement.html): query timeout và cancel.

Pool cạn, timeout và deadlock đều có thể khiến request chờ hoặc lỗi, nhưng cần chẩn đoán ở đúng tầng. Pool exhaustion cần xem active/idle/waiting và thời gian giữ connection; timeout cần phân biệt pool, connect, network, lock và statement; deadlock cần đọc ORA-00060/deadlock graph và xử lý transaction theo business boundary. **Khôi phục an toàn bắt đầu bằng lưu bằng chứng, giảm admission, tìm session/transaction gây chờ, giải phóng tài nguyên đúng phạm vi và xác minh cả pool lẫn dữ liệu sau khi hệ thống ổn định.**
