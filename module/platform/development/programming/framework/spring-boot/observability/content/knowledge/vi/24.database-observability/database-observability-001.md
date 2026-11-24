# JDBC observability trong Spring Boot

Một API Spring Boot có thể trả response chậm dù controller và HTTP client không có vấn đề. Thời gian có thể bị tiêu tốn khi chờ lấy connection từ pool, thực thi SQL, chờ database lock hoặc truyền dữ liệu qua JDBC. Nếu chỉ quan sát HTTP request duration, đội vận hành biết request chậm nhưng chưa biết thời gian nằm ở application code, connection pool hay database. **JDBC observability** bổ sung góc nhìn đó bằng metrics về DataSource/pool, thông tin về thao tác JDBC và traces giúp liên kết database call với request đã kích hoạt nó.

Trong module **SPRING_BOOT_OBSERVABILITY**, JDBC observability là một phần của thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing. Bài thuộc chương **Database observability**, tập trung vào **JDBC observability**: quan sát connection pool và truy vấn JDBC, phân biệt thời gian chờ connection với thời gian execute, tích hợp metrics/tracing, xử lý SQL metadata an toàn, kiểm soát cardinality, kiểm thử và điều tra sự cố trong production.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt DataSource/pool metrics, JDBC query metrics và database server metrics.
2. Theo dõi active/idle/pending connections, acquisition time và usage time.
3. Hiểu cách Spring Boot/Micrometer instrument DataSource và JDBC operations.
4. Phân biệt JDBC Observation, tracing span và SQL logging.
5. Liên kết database spans với HTTP request bằng trace context.
6. Nhận diện pool saturation, slow query, lock wait và connection leak.
7. Giới hạn SQL attributes, query cardinality và dữ liệu nhạy cảm.
8. Kiểm thử metrics, tracing và pool behavior bằng test database.
9. Điều tra khi JDBC metrics/traces thiếu hoặc có chi phí telemetry quá cao.

## 1. JDBC observability là gì?

JDBC (Java Database Connectivity) là API Java để ứng dụng làm việc với relational databases. Trong Spring Boot, code thường truy cập JDBC thông qua JdbcTemplate, Spring Data JDBC/JPA, Hibernate hoặc thư viện truy cập dữ liệu khác. Dưới các abstraction đó, ứng dụng thường dùng DataSource để lấy Connection và JDBC driver để thực thi câu lệnh.

JDBC observability quan sát các điểm quan trọng trong vòng đời truy cập database:

- lấy connection từ DataSource hoặc connection pool;
- thời gian connection được giữ;
- thực thi PreparedStatement/Statement;
- số lượng và thời lượng database operations;
- exception và SQL error category;
- transaction boundaries;
- trace context liên kết operation với request;
- trạng thái pool như active, idle, pending và timeout.

### 1.1. Các tầng cần quan sát

| Tầng | Câu hỏi | Ví dụ dữ liệu |
| --- | --- | --- |
| Application | Code nào gọi database? | Service/operation name |
| DataSource/pool | Có connection sẵn không? | Active, idle, pending |
| JDBC client | Câu lệnh mất bao lâu? | Query duration, operation type |
| Database server | DB đang làm gì? | Lock wait, execution plan, CPU |
| Trace | DB call thuộc request nào? | Trace ID, span ID, parent |
| Logs | Lỗi nào xảy ra? | SQLState, exception category |

Một metric ở application side không thay thế database-native monitoring. Ví dụ pool pending tăng cho biết ứng dụng đang chờ connection; database CPU/lock metrics mới giúp xác định database engine đang quá tải hay bị contention.

### 1.2. DataSource, connection pool và JDBC driver

~~~mermaid
flowchart TD
    App["Spring service / repository"] --> SpringJDBC["JdbcTemplate / ORM"]
    SpringJDBC --> DataSource["DataSource"]
    DataSource --> Pool["Connection pool"]
    Pool --> Driver["JDBC driver"]
    Driver --> Database["Database server"]
    Pool -. "Pool metrics" .-> Metrics["MeterRegistry"]
    SpringJDBC -. "JDBC Observation / tracing" .-> Telemetry["Metrics / traces"]
    Database -. "DB-native monitoring" .-> DBMetrics["DB metrics / query statistics"]
~~~

Spring Boot thường cấu hình HikariCP làm connection pool mặc định khi dependency phù hợp có mặt. Ứng dụng cũng có thể dùng pool khác hoặc DataSource do tổ chức tự cung cấp. Tên metric và các khả năng instrument phụ thuộc implementation/version.

## 2. Connection pool metrics

Connection pool giữ một tập connections có thể tái sử dụng. Pool giúp tránh mở/đóng physical database connection cho mọi operation, nhưng pool có giới hạn. Khi mọi connection đều bận, request mới phải chờ hoặc timeout.

### 2.1. Các pool measurements quan trọng

| Measurement | Ý nghĩa | Cách diễn giải |
| --- | --- | --- |
| Active connections | Connection đang được ứng dụng mượn | Gần max lâu có thể là saturation |
| Idle connections | Connection sẵn sàng được mượn | Bằng 0 không luôn là lỗi, cần xem pending |
| Pending/waiting threads | Số thread đang chờ connection | Tăng kéo dài là dấu hiệu pool pressure |
| Max connections | Giới hạn pool | Cần cân đối với DB capacity |
| Min idle | Số idle connections mục tiêu | Ảnh hưởng warm-up và resource use |
| Connection acquisition time | Thời gian chờ lấy connection | Cao thường gợi ý pool pressure hoặc DB/connectivity |
| Connection usage time | Thời gian giữ connection | Cao có thể do query chậm hoặc giữ connection quá lâu |
| Timeout count | Số lần không lấy được connection đúng hạn | Tín hiệu rõ về pool exhaustion |

Tên meter có thể khác nhau giữa HikariCP và pool khác. Với HikariCP, Micrometer có thể cung cấp meter thuộc nhóm hikaricp.connections và các measurements liên quan; kiểm tra registry thật.

### 2.2. Vì sao active connections cao chưa đủ kết luận?

Active connections cao có thể bình thường nếu traffic tăng. Cần đọc đồng thời:
- active so với max;
- idle;
- pending threads;
- acquisition latency;
- usage duration;
- request rate và DB latency.

Nếu active gần max nhưng pending bằng 0 và acquisition latency thấp, pool có thể đang sử dụng hiệu quả. Nếu active gần max, pending tăng và acquisition latency tăng kéo dài, pool đang chịu áp lực.

### 2.3. Connection acquisition time và usage time

Acquisition time là thời gian ứng dụng chờ pool cấp connection. Usage time là khoảng connection được giữ sau khi mượn. Hai chỉ số giúp phân biệt:

- Acquisition cao, usage bình thường: pool thiếu capacity, connection bị giữ bởi request khác, hoặc connection creation chậm.
- Acquisition bình thường, usage cao: SQL chậm, lock wait, result set lớn, transaction kéo dài hoặc code giữ connection lâu.
- Cả hai cao: có thể có overload tổng thể hoặc database/pool đang gặp sự cố.

Không tăng max pool size ngay khi thấy pending. Database có giới hạn số connections và việc tăng pool có thể làm database chịu nhiều concurrency hơn, khiến latency tệ hơn.

## 3. Spring Boot và Actuator cho DataSource metrics

Với Spring Boot Actuator và Micrometer, DataSource có thể được instrument tự động khi DataSource/pool được nhận diện và meter registry hiện diện.

Ví dụ Gradle cho ứng dụng Spring Boot JDBC:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'com.h2database:h2'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Trong production, thay H2 bằng JDBC driver/database thật. Giữ version dependency theo Spring Boot BOM.

### 3.1. Bật endpoint metrics

Ví dụ cấu hình Actuator:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      show-details: never
~~~

Chỉ expose các endpoint cần thiết và bảo vệ bằng network/security policy. Không mở endpoint metrics ra internet công khai nếu không có kiểm soát truy cập phù hợp.

### 3.2. Kiểm tra meter qua Actuator

Các endpoint hỗ trợ có thể liệt kê meter names và chi tiết meter. Ví dụ kiểm tra:

~~~text
GET /actuator/metrics
GET /actuator/metrics/hikaricp.connections.active
GET /actuator/metrics/hikaricp.connections.idle
GET /actuator/metrics/hikaricp.connections.pending
~~~

Tên chính xác phụ thuộc pool và Spring Boot/Micrometer version. Trước khi xây dashboard, kiểm tra danh sách meter thực tế ở môi trường đang chạy.

### 3.3. HikariCP metrics

Khi dùng HikariCP, Micrometer có thể bind pool metrics thông qua Hikari metrics integration. Spring Boot auto-configuration thường thực hiện phần này khi điều kiện phù hợp. Nếu DataSource được tự tạo hoặc wrap, kiểm tra HikariDataSource có được nhận diện và bind đúng không.

Không tạo một binder cho cùng pool nhiều lần; có thể dẫn tới meter registration trùng hoặc số liệu không nhất quán.

## 4. JDBC operations và Micrometer Observation

Pool metrics mô tả trạng thái pool; chúng không nhất thiết cho biết từng SQL operation nào chậm. Để quan sát JDBC operation, ứng dụng cần instrumentation ở lớp JDBC/ORM hoặc custom Observation bao quanh operation nghiệp vụ.

Micrometer Observation cung cấp lifecycle thống nhất: start, event/error và stop. Observation handlers có thể tạo metrics và tracing spans nếu được cấu hình.

### 4.1. JDBC Observation không phải SQL logger

| Cơ chế | Vai trò | Nội dung |
| --- | --- | --- |
| DataSource pool metrics | Sức khỏe pool | Active/idle/pending/timeouts |
| JDBC Observation | Lifecycle operation | Tên operation, duration, outcome/context |
| JDBC tracing span | Liên kết operation trong trace | Parent, timing, selected attributes |
| SQL logging | Debug câu lệnh | SQL text/parameters nếu được cấu hình |
| Database query statistics | Góc nhìn engine | Execution stats, locks, plans |

Không bật SQL logging toàn bộ chỉ để có query metrics. SQL text và bind parameters có thể chứa PII, secrets hoặc dữ liệu thanh toán.

### 4.2. Custom Observation quanh operation nghiệp vụ

Nếu JDBC instrumentation cụ thể chưa có, có thể thêm business Observation quanh repository operation:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderRepository {
    private final JdbcTemplate jdbcTemplate;
    private final ObservationRegistry observationRegistry;

    public OrderRepository(
            JdbcTemplate jdbcTemplate,
            ObservationRegistry observationRegistry
    ) {
        this.jdbcTemplate = jdbcTemplate;
        this.observationRegistry = observationRegistry;
    }

    public Integer countOpenOrders() {
        return Observation.createNotStarted(
                        "orders.repository.count-open",
                        observationRegistry)
                .lowCardinalityKeyValue("db.operation", "SELECT")
                .observe(() -> jdbcTemplate.queryForObject(
                        "select count(*) from orders where status = ?",
                        Integer.class,
                        "OPEN"
                ));
    }
}
~~~

Observation này mô tả operation nghiệp vụ và bao quanh lời gọi JdbcTemplate. Nếu framework/agent đã instrument JDBC call bên dưới, có thể có một business span bên ngoài và một JDBC span bên trong; đó là hierarchy có chủ đích nếu tên và vai trò rõ ràng. Không tạo thêm span trùng cùng một operation ở cùng tầng.

### 4.3. Low-cardinality và high-cardinality metadata

Các metadata phù hợp cho metrics thường là:
- db.system: postgresql, mysql;
- db.operation.name: SELECT, INSERT, UPDATE;
- repository/operation name ổn định;
- outcome/error category có tập giá trị hữu hạn.

Các giá trị không nên thành metric tags:
- raw SQL;
- SQL bind values;
- customer ID/order ID;
- table name nếu dynamic và không kiểm soát;
- exception message tự do;
- connection URL có credentials.

High-cardinality attributes trong traces vẫn cần kiểm soát kích thước, privacy và indexing cost.

## 5. JDBC tracing và distributed trace

Một HTTP request có thể gọi service, thực thi JDBC và trả response. Nếu tracing instrumentation bao quanh JDBC call, database span có thể là child của server span hoặc business span hiện hành.

~~~mermaid
sequenceDiagram
    participant Client
    participant App as Spring Boot
    participant JDBC as JDBC instrumentation
    participant DB as Database
    participant Exporter as OTLP Collector
    Client->>App: POST /orders
    Note over App: HTTP server span
    App->>JDBC: INSERT order
    Note over JDBC: JDBC client span
    JDBC->>DB: SQL execution
    DB-->>JDBC: Result
    JDBC-->>App: Update count
    App-->>Client: HTTP 201
    App->>Exporter: Export server/business spans
    JDBC->>Exporter: Export JDBC span
~~~

Trace backend có thể cho thấy:
- HTTP server span tổng thời gian request;
- business span cho orders.create;
- JDBC span cho thao tác DB;
- dependency spans nếu request gọi service khác.

Nếu HTTP span mất 800 ms và JDBC span mất 650 ms, database operation có thể chiếm phần lớn request latency. Nhưng JDBC span duration không luôn bằng pure database execution time; nó có thể bao gồm driver/client overhead, network, result processing hoặc instrumentation boundary.

### 5.1. Không phải mọi JDBC driver đều tự tạo span

JDBC API không tự động bảo đảm spans. Cần một integration phù hợp, ví dụ instrumentation agent, framework integration hoặc datasource/JDBC instrumentation cụ thể. Việc có Micrometer Tracing bridge và OTLP exporter chưa đủ để kết luận mọi JDBC statement đã được instrument.

Kiểm tra spans thực tế trong test và trace backend; không giả định chỉ vì pool metrics xuất hiện thì JDBC spans cũng có.

### 5.2. Parent context và async database work

Nếu database operation chạy trong async worker, context phải được truyền tới worker bằng cơ chế phù hợp. Nếu không, JDBC span có thể thành root span riêng hoặc không có parent như mong đợi. Với reactive database stack như R2DBC, đó là một API/instrumentation khác, không thuộc JDBC.

## 6. Query duration, slow query và database lock

JDBC client timing hữu ích để tìm operation chậm, nhưng không giải thích nguyên nhân bên trong database. Khi thấy query duration tăng, cần kết hợp:
- JDBC span/Observation duration;
- pool acquisition/usage time;
- database-native query statistics;
- lock/wait events;
- CPU, IO, buffer/cache;
- transaction duration;
- query plan và index usage.

### 6.1. Phân biệt chờ pool và chờ database

| Dấu hiệu | Khả năng | Hướng điều tra |
| --- | --- | --- |
| Acquisition cao, JDBC span ngắn | Chờ connection trước khi execute | Pool capacity, connection leak, concurrency |
| Acquisition thấp, JDBC span cao | DB/driver/network/result processing | Slow query, lock, network, result size |
| Pool usage cao, DB query nhanh | Connection bị giữ ngoài query | Transaction scope, application processing khi giữ connection |
| DB lock waits cao, JDBC duration cao | Contention trong DB | Transaction isolation, lock order, query |
| Pending cao, active=max | Pool saturation | Traffic, concurrency, query duration, pool config |

Đừng quy tất cả latency database về SQL execution. Connection acquisition và transaction scope cũng có thể là nguồn chậm.

### 6.2. Transaction kéo dài

Connection thường được giữ trong transaction. Nếu code thực hiện remote HTTP call hoặc xử lý nặng bên trong transaction, connection có thể bị giữ lâu dù SQL nhanh. Tránh transaction scope quá rộng; không gọi dependency mạng khi đang giữ transaction/connection nếu không cần thiết.

### 6.3. N+1 queries

Một request có thể phát hàng trăm JDBC spans ngắn do ORM phát query trong loop. Mỗi query riêng lẻ không chậm nhưng tổng thời gian và database load cao. Tracing giúp thấy số lượng spans; ORM/database statistics giúp tìm N+1. Metrics nên tổng hợp query count/duration theo operation, không gắn entity ID thành tag.

## 7. SQL metadata và bảo vệ dữ liệu

SQL có thể chứa literals hoặc dữ liệu nhạy cảm. Không đưa raw SQL hoặc bind parameter vào metrics. Với traces, chỉ thu thập statement metadata đã chuẩn hóa và theo policy của tổ chức.

| Metadata | Khuyến nghị |
| --- | --- |
| db.system | Có thể dùng, giá trị chuẩn hóa |
| db.operation.name | Có thể dùng, SELECT/INSERT/UPDATE/DELETE |
| db.namespace/database name | Cân nhắc, tránh credentials |
| Server address/port | Cân nhắc theo topology/privacy |
| SQL query text | Không mặc định; cần sanitization và policy |
| Bind parameter values | Không thu thập mặc định |
| Customer/order identifiers | Không dùng làm metric tags |
| Exception message | Redact; ưu tiên SQLState/category |

### 7.1. SQL statement sanitization

Nếu cần query text cho traces, ưu tiên statement đã parameterize và sanitization để không giữ literal values. Ví dụ:

~~~sql
SELECT * FROM orders WHERE customer_id = ?
~~~

Không export câu đã thay literal bằng dữ liệu thật:

~~~sql
SELECT * FROM orders WHERE customer_id = 'customer-938274'
~~~

Ngay cả query đã sanitize vẫn có thể tiết lộ schema hoặc business logic; chỉ bật khi cần và giới hạn quyền truy cập.

### 7.2. Database URL và credentials

Không ghi JDBC URL chứa username/password vào logs, spans hoặc Resource attributes. Dùng secret management và cấu hình redaction. Connection pool name có thể được dùng để phân biệt pool nhưng không nên chứa tenant/customer identifier động.

## 8. Connection leak và pool exhaustion

Một connection được mượn nhưng không được trả lại sẽ làm active connections tăng theo thời gian. Khi pool cạn, request mới chờ rồi timeout.

Các dấu hiệu:
- active connections giữ ở max;
- idle bằng 0;
- pending threads tăng;
- acquisition timeout tăng;
- request latency tăng;
- số connection đang dùng không giảm sau khi traffic hạ.

### 8.1. Nguyên nhân phổ biến

1. Connection/Statement/ResultSet tự quản lý không được đóng.
2. Transaction không kết thúc do exception hoặc lifecycle sai.
3. Code giữ connection trong lúc gọi remote service.
4. Long-running query hoặc lock giữ connection lâu.
5. Pool max quá thấp so với concurrency hợp lý.
6. DB chậm hoặc network làm operation giữ connection lâu.

Ưu tiên try-with-resources khi tự quản lý JDBC resources:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
             "select id from orders where status = ?")) {
    statement.setString(1, "OPEN");
    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            // Process a row.
        }
    }
}
~~~

Với Spring JdbcTemplate/JPA, framework thường quản lý resource lifecycle; không tự đóng connection do transaction manager quản lý.

### 8.2. Leak detection threshold

HikariCP có leak detection threshold để log connection được giữ quá lâu. Đây là công cụ chẩn đoán, không phải cơ chế tự thu hồi connection. Threshold quá thấp tạo false positives; quá cao có thể không giúp phát hiện sớm. Dùng tạm thời trong điều tra, theo dõi log và tắt/điều chỉnh sau khi hiểu nguyên nhân.

## 9. Transaction observability

Transaction bao quanh một nhóm database operations. Quan sát transaction duration và outcome giúp phát hiện:
- transaction quá dài;
- rollback rate tăng;
- lock contention;
- exception khiến rollback;
- connection bị giữ qua nhiều thao tác.

### 9.1. Transaction span hay business Observation?

Không phải mọi transaction đều cần một span riêng. Nếu HTTP server span và JDBC spans đã mô tả đủ lifecycle, thêm một business Observation có thể giúp nhìn thấy operation quan trọng như orders.checkout. Giữ tên ổn định và tránh trùng với tên JDBC operation.

### 9.2. Rollback và exception

Một transaction rollback có thể do business validation, deadlock, timeout hoặc connection failure. Log SQLState/error category và trace exception đã redacted. Không ghi toàn bộ bind parameters để giải thích rollback.

## 10. Kiểm thử JDBC observability

Test nên tách pool metrics, JDBC operation và tracing export vì mỗi test chứng minh một lớp khác nhau.

| Test | Mục tiêu | Không chứng minh |
| --- | --- | --- |
| DataSource binder test | Pool meters được đăng ký | DB query instrumentation |
| JdbcTemplate integration test | SQL operation chạy đúng | OTLP export |
| Observation test | Custom Observation lifecycle/tags | JDBC driver tự instrument |
| Tracing test | Span context/parent relationship | Database server execution plan |
| Pool saturation test | Pending/acquisition behavior | Production capacity tuyệt đối |
| DB integration test | SQL/transaction behavior | Mọi database engine giống nhau |

### 10.1. Test với H2 và JdbcTemplate

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class JdbcRepositoryIntegrationTest {
    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void executesQuery() {
        Integer result = jdbcTemplate.queryForObject(
                "select 1",
                Integer.class
        );

        assertThat(result).isEqualTo(1);
    }
}
~~~

Test này xác minh JdbcTemplate kết nối và thực thi query trong test context. Nó không chứng minh Hikari pool metrics hoặc JDBC spans đã được export.

### 10.2. Test pool metrics

Có thể inject MeterRegistry, thực hiện mượn/trả connection và kiểm tra meter tương ứng được đăng ký. Tên meter và cách đọc measurements phụ thuộc pool implementation. Tránh assert giá trị active tuyệt đối trong test nhiều thread vì trạng thái có thể thay đổi giữa các lần đọc.

### 10.3. Test tracing context

Khi JDBC tracing integration đã được cấu hình, tạo operation trong một parent span và xác minh:
- JDBC span có cùng Trace ID;
- span có parent relationship phù hợp;
- operation name/attributes đã được chuẩn hóa;
- lỗi JDBC được biểu diễn theo convention;
- không có SQL bind values hoặc credentials trong exported attributes.

Nếu chỉ custom Observation quanh repository, test xác minh business span đó; không kết luận driver đã tự tạo span.

### 10.4. Test pool pressure có kiểm soát

Dùng pool nhỏ trong test và một operation giữ connection có chủ đích. Quan sát active, pending và acquisition time; giải phóng connection trong finally. Không chạy test saturation trên database dùng chung hoặc production. Đây là test behavior, không phải cách chọn pool size cuối cùng.

## 11. Troubleshooting JDBC observability

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không có Hikari metrics | DataSource không được bind hoặc pool khác | Kiểm tra DataSource type, registry và binders |
| Active luôn bằng max | Pool saturation hoặc connection leak | Xem pending, acquisition, usage và transaction |
| Pending tăng | Không có connection rảnh đủ nhanh | Điều tra query latency, concurrency và pool limit |
| Acquisition time cao | Chờ pool hoặc tạo connection chậm | Kiểm tra active/max, idle, DB connectivity |
| Usage time cao | Query/transaction giữ connection lâu | Kiểm tra JDBC spans, DB locks và transaction scope |
| HTTP request chậm nhưng không có JDBC span | JDBC chưa được instrument | Xác minh agent/framework integration |
| Có pool metrics nhưng không có query metrics | Pool binder chỉ đo pool | Thêm JDBC instrumentation phù hợp hoặc custom Observation |
| Trace không có parent | Context không được truyền vào worker | Kiểm tra async context propagation |
| SQL xuất hiện trong logs/traces | SQL logging/instrumentation capture quá chi tiết | Sanitize, allowlist và tắt bind values |
| Meter count tăng theo customer ID | ID/query value bị dùng làm tag | Bỏ dynamic tags |
| Connection timeout | Pool cạn hoặc DB/connectivity lỗi | Xem pending, DB health và timeout |
| N+1 query | ORM phát nhiều query nhỏ | Dùng trace/query statistics và tối ưu fetch |
| Deadlock/lock wait | Transaction contention | Kiểm tra DB-native locks và transaction order |
| Span duration khác DB execution time | Span bao gồm driver/network/result processing | Đối chiếu DB-native query timing |

### 11.1. Quy trình điều tra request database chậm

1. Tìm HTTP request có latency cao trong metrics.
2. Mở trace tương ứng và xác định business/JDBC spans.
3. So sánh thời gian server span, JDBC span và các dependency spans.
4. Kiểm tra pool active/idle/pending và acquisition time tại cùng thời điểm.
5. Nếu JDBC span dài, xem DB-native query statistics, locks và execution plan.
6. Kiểm tra transaction scope và connection usage duration.
7. Kiểm tra exception/SQLState, timeout và retry.
8. Xác minh telemetry không chứa SQL literals, credentials hoặc business identifiers.

## 12. Production checklist

| Tiêu chí | Bằng chứng cần có |
| --- | --- |
| DataSource/pool được nhận diện | Pool metrics xuất hiện trong registry |
| Pool saturation được giám sát | Active/max, idle, pending, acquisition và timeout |
| JDBC operation được instrument | Có spans/Observation nếu mục tiêu yêu cầu |
| Parent context đúng | JDBC spans liên kết với request trace |
| Query metadata an toàn | Không bind values, PII hoặc credentials |
| Transaction duration hợp lý | Có metrics/trace hoặc DB-native evidence |
| Cardinality thấp | Không dynamic SQL/IDs thành metric tags |
| DB-native monitoring bổ sung | Locks, query stats, CPU/IO có thể đối chiếu |
| Connection lifecycle đúng | Resource được trả về pool |
| Leak detection có chủ đích | Threshold được cân nhắc và không tạo noise |
| Export pipeline được giám sát | Export errors/dropped spans được theo dõi |
| Tests phân biệt đúng tầng | Pool, JDBC, Observation, tracing, DB integration |

## 13. Bài thực hành: điều tra pool saturation và slow JDBC

**Bối cảnh:** order-service dùng Spring Boot, HikariCP và PostgreSQL. Khi traffic tăng, HTTP p95 latency tăng, pool active chạm max và pending threads xuất hiện. Nhóm vận hành cần xác định thời gian bị mất ở pool, SQL hay transaction.

**Nhiệm vụ:**

1. Bật Actuator và xác minh Hikari pool metrics.
2. Tạo dashboard active/max, idle, pending, acquisition time, usage time và timeout.
3. Gửi tải kiểm soát tới endpoint tạo đơn và ghi lại HTTP request latency.
4. Bật tracing integration phù hợp để thấy database operation trong request trace.
5. Thêm custom business Observation nếu cần phân biệt orders.create với JDBC operation.
6. Tạo tình huống query chậm và so sánh acquisition time với JDBC span duration.
7. Tạo tình huống giữ connection lâu; quan sát pending và timeout.
8. Kiểm tra transaction scope có gọi HTTP dependency khi đang giữ connection hay không.
9. Kiểm tra SQL telemetry không chứa bind values, token hoặc PII.
10. Chạy test với pool nhỏ và chứng minh connection được trả lại trong finally.
11. Dùng DB-native query statistics/lock view để đối chiếu một slow JDBC span.
12. Viết runbook phân biệt pool saturation, connection leak, slow query và database lock.

**Kết quả mong đợi:** dashboard pool metrics, trace có database operation nếu instrumentation được cấu hình, test JDBC/pool, ví dụ metadata an toàn và runbook điều tra latency.

## 14. Ghi nhớ

**JDBC observability** cần nhìn cả pool lẫn database operations. Pool metrics cho biết connection availability, pending, acquisition và usage; JDBC Observation/tracing mô tả operation và liên kết nó với request; database-native monitoring giải thích execution plan, locks, CPU và IO. Các tầng này bổ sung cho nhau nhưng không thay thế nhau.

Không kết luận database query chậm chỉ từ HTTP duration hoặc active connections. So sánh acquisition time, connection usage, JDBC span và DB-native statistics. Dùng Observation names và low-cardinality tags ổn định; không đưa raw SQL, bind parameters, credentials hoặc customer IDs vào metrics/traces. Kiểm thử từng tầng riêng, theo dõi pool pressure và bảo đảm transaction/resource lifecycle ngắn, rõ ràng.

**Tài liệu tham khảo:**
- [Spring Boot — JDBC Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot — Data Access](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Micrometer — JVM and DataSource Metrics](https://docs.micrometer.io/micrometer/reference/reference/jvm.html)
- [Micrometer Observation — Reference](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Micrometer Tracing — Reference](https://docs.micrometer.io/tracing/reference/)
- [HikariCP — Configuration](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby)
- [OpenTelemetry — Database Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/db/)
- [JDBC — Java Documentation](https://docs.oracle.com/javase/8/docs/technotes/guides/jdbc/)

