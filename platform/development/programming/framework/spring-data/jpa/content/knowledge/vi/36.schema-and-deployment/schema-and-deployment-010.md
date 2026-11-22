# Kiểm tra kết nối, quan sát lỗi và phục hồi sau sự cố cơ sở dữ liệu

## 1. Mục tiêu và phạm vi

Spring Data JPA thường truy cập database qua chuỗi thành phần: service → repository/EntityManager → Hibernate → JDBC driver → connection pool → DBMS. Khi database mất kết nối hoặc phản hồi chậm, lỗi có thể xuất hiện ở bất kỳ điểm nào trong chuỗi này.

Một hệ thống vận hành tốt cần làm được bốn việc:

1. **Kiểm tra kết nối** để biết ứng dụng có thể lấy connection và database có phản hồi hay không.
2. **Quan sát tình trạng** qua health check, metrics, logs và traces để nhận ra lỗi trước khi người dùng báo.
3. **Phân loại sự cố** để phân biệt database ngừng hoạt động, pool cạn, mạng lỗi, query chậm, lock hoặc cấu hình sai.
4. **Phục hồi an toàn** bằng cách giới hạn tải, khôi phục kết nối, retry có kiểm soát và xác minh tính nhất quán dữ liệu.

Không có một health check đơn lẻ nào bảo đảm request tiếp theo chắc chắn thành công. Kết quả health check chỉ phản ánh trạng thái tại thời điểm kiểm tra; kết nối có thể hỏng ngay sau đó. Vì vậy, cần kết hợp kiểm tra nhanh với metrics, log và xử lý exception ở từng thao tác.

## 2. Kiểm tra kết nối từ ứng dụng

### 2.1 Kiểm tra DataSource và JDBC connection

Cách trực tiếp nhất là lấy connection từ DataSource và gọi JDBC `isValid()`:

```java
import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

public class DatabaseConnectionProbe {

    private final DataSource dataSource;

    public DatabaseConnectionProbe(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean isDatabaseReachable() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            return connection.isValid(2);
        }
    }
}
```

`isValid(2)` yêu cầu driver kiểm tra connection trong thời gian chờ tối đa khoảng 2 giây theo hợp đồng JDBC. Khả năng và cách triển khai cụ thể phụ thuộc driver. `getConnection()` cũng có thể chờ pool cấp connection; nếu pool cạn, lỗi có thể xảy ra trước khi gọi `isValid()`.

Không tạo connection mới bằng `DriverManager` trong code nghiệp vụ để kiểm tra database. Hãy kiểm tra chính DataSource mà Spring đang dùng để phép thử phản ánh đúng cấu hình, credentials, pool và driver của ứng dụng.

Nếu cần chẩn đoán DBMS và phiên bản, có thể đọc metadata:

```java
try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData metadata = connection.getMetaData();

    String product = metadata.getDatabaseProductName();
    String version = metadata.getDatabaseProductVersion();

    log.info("Connected database: product={}, version={}", product, version);
}
```

Không log URL có thể chứa credentials hoặc thông tin nội bộ nhạy cảm. Product/version là metadata hữu ích để đối chiếu môi trường test với production.

### 2.2 Phân biệt các loại timeout

Các timeout có ý nghĩa khác nhau và không nên dùng thay thế cho nhau:

| Timeout | Giới hạn điều gì? | Ví dụ cấu hình |
|---|---|---|
| Pool connection timeout | Thời gian chờ lấy connection từ pool | Hikari `connectionTimeout` |
| Connection validation timeout | Thời gian kiểm tra connection | Hikari `validationTimeout` |
| Socket/network timeout | Thời gian chờ I/O từ database qua mạng | JDBC driver hoặc network |
| Query timeout | Thời gian thực thi câu SQL | JPA query hint/JDBC |
| Transaction timeout | Thời gian tối đa của transaction theo transaction manager/provider | `@Transactional(timeout = ...)` |
| Lock timeout | Thời gian chờ khóa database | DBMS hoặc query/transaction setting |

Ví dụ: `connectionTimeout` của Hikari hết hạn thường có nghĩa ứng dụng không lấy được connection từ pool trong thời gian quy định. Nó không chứng minh database server đã ngừng hoạt động. Pool có thể hết connection vì query chậm, transaction giữ connection lâu hoặc số request đồng thời vượt khả năng phục vụ.

Ngược lại, query timeout xảy ra sau khi đã lấy connection và gửi câu SQL. Khi chẩn đoán, hãy xác định timeout xuất hiện ở bước nào.

### 2.3 Cấu hình HikariCP có chủ đích

Spring Boot thường dùng HikariCP khi có dependency phù hợp. Một cấu hình ví dụ:

```yaml
spring:
  datasource:
    hikari:
      pool-name: application-db-pool
      maximum-pool-size: 12
      minimum-idle: 2
      connection-timeout: 3000
      validation-timeout: 1000
      max-lifetime: 1740000
      keepalive-time: 120000
```

Các giá trị thời gian trong cấu hình Hikari ở ví dụ này tính bằng milliseconds. Đây là các con số minh họa, không phải giá trị phù hợp cho mọi hệ thống. Điều chỉnh dựa trên giới hạn connection của database, số instance ứng dụng, concurrency, thời gian query và timeout của proxy/load balancer:

- `maximum-pool-size`: giới hạn số connection đồng thời của một instance. Tổng connection của mọi instance, job và công cụ quản trị phải nằm trong ngân sách DBMS.
- `minimum-idle`: số connection nhàn rỗi pool cố gắng duy trì.
- `connection-timeout`: thời gian chờ connection từ pool; phải phù hợp với latency và SLA của request.
- `validation-timeout`: thời gian tối đa kiểm tra connection; phải nhỏ hơn `connection-timeout`.
- `max-lifetime`: tuổi tối đa của connection trong pool. Đặt thấp hơn giới hạn tuổi connection của database/proxy/network một khoảng hợp lý để pool chủ động thay connection.
- `keepalive-time`: chu kỳ kiểm tra/giữ sống connection nhàn rỗi; phải nhỏ hơn `max-lifetime` và chỉ có ý nghĩa khi connection đang idle.

Với JDBC 4 driver hỗ trợ `Connection.isValid()`, Hikari thường không cần cấu hình `connectionTestQuery`. Chỉ dùng câu test query khi driver cũ không hỗ trợ JDBC4 hoặc có lý do cụ thể được xác nhận từ tài liệu driver.

Không tăng `maximum-pool-size` chỉ vì thấy request chờ connection. Pool lớn hơn có thể làm database quá tải và tăng lock contention. Trước hết hãy kiểm tra query chậm, transaction kéo dài, connection leak, số request đồng thời và giới hạn connection của DBMS.

## 3. Health check với Spring Boot Actuator

Spring Boot Actuator cung cấp endpoint health và các health indicator. Khi có DataSource, health indicator database (thường là `DataSourceHealthIndicator`) có thể kiểm tra khả năng truy cập database thông qua DataSource.

Thêm Actuator dependency phù hợp với phiên bản Spring Boot, sau đó bật health probes:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,db
      show-details: never
```

Các endpoint thường dùng trong môi trường có orchestrator:

- `/actuator/health`: tổng quan health.
- `/actuator/health/liveness`: ứng dụng còn sống và có thể tiếp tục chạy không.
- `/actuator/health/readiness`: ứng dụng có sẵn sàng nhận traffic không.

**Liveness và readiness có mục đích khác nhau:**

- Liveness nên phản ánh ứng dụng có bị kẹt hoặc ở trạng thái không thể tự phục hồi hay không. Không đưa database vào liveness một cách máy móc. Nếu DB tạm ngừng mà liveness cũng DOWN, Kubernetes có thể restart hàng loạt pod, tạo thêm áp lực lên database khi nó đang phục hồi.
- Readiness có thể bao gồm database nếu ứng dụng không thể phục vụ request chính khi DB không truy cập được. Khi readiness DOWN, orchestrator ngừng gửi traffic mới đến instance đó nhưng vẫn để process chạy để nó tự phục hồi.

Việc đưa `db` vào readiness là quyết định theo kiến trúc. Một ứng dụng có thể vẫn phục vụ một số endpoint chỉ đọc từ cache hoặc trang trạng thái khi DB lỗi; khi đó cần xác định rõ nhóm endpoint nào thực sự phụ thuộc database. Health group mặc định và cú pháp cấu hình có thể thay đổi theo phiên bản Spring Boot, hãy đối chiếu phiên bản dự án.

Health check không nên thực hiện query nặng hoặc chạy quá thường xuyên. Nó tiêu thụ connection từ pool và chính nó có thể góp phần làm pool quá tải. Cần đặt timeout hợp lý, bảo vệ endpoint bằng network policy/authentication và không công khai chi tiết nội bộ như hostname, schema hoặc exception cho người dùng bên ngoài.

### 3.1 Readiness không phải cam kết giao dịch thành công

Một lần `/actuator/health/readiness` trả UP chỉ chứng minh indicator kiểm tra thành công ở thời điểm đó. Request kế tiếp vẫn có thể gặp failover, network reset, pool timeout hoặc deadlock.

Vì vậy:

- Dùng health check để quyết định nhận traffic.
- Dùng metrics để theo dõi xu hướng và phát hiện nghẽn.
- Dùng log/trace để xác định request cụ thể bị lỗi ở đâu.
- Dùng exception handling và transaction boundary để xử lý request đã vào ứng dụng.

## 4. Quan sát pool connection và database

### 4.1 Các metrics quan trọng

Khi dùng Actuator/Micrometer và HikariCP, theo dõi các metrics pool thường có tiền tố `hikaricp.connections`:

| Metric | Ý nghĩa | Dấu hiệu cần chú ý |
|---|---|---|
| `hikaricp.connections.active` | Connection đang được sử dụng | Tăng liên tục và không giảm |
| `hikaricp.connections.idle` | Connection đang nhàn rỗi | Luôn bằng 0 khi có tải có thể cho thấy pool thiếu |
| `hikaricp.connections.pending` | Số thread đang chờ connection | Tăng kéo dài là dấu hiệu nghẽn |
| `hikaricp.connections.max` | Giới hạn connection của pool | So với active/pending |
| `hikaricp.connections.min` | Mức idle tối thiểu cấu hình | Đối chiếu với tải thực tế |

Tên metric chính xác và cách export phụ thuộc phiên bản Boot/Micrometer. Kiểm tra danh sách metrics thực tế qua `/actuator/metrics` hoặc Prometheus scrape endpoint.

Một số mẫu cần phân tích:

- **Active chạm max, pending tăng**: pool đang bão hòa. Tìm query lâu, transaction giữ connection, connection leak hoặc traffic tăng đột biến.
- **Active cao kéo dài, query latency tăng**: database có thể đang chậm, lock nhiều hoặc thiếu tài nguyên.
- **Idle bằng 0 nhưng pending thấp**: pool có thể đang hoạt động gần hết công suất nhưng chưa gây chờ đáng kể.
- **Active giảm, pending vẫn tăng**: xem xét pool không thể tạo connection mới, database giới hạn connection hoặc network lỗi.
- **Pool timeout tăng cùng DB latency**: có thể là triệu chứng chung của sự cố database hoặc query, không nhất thiết pool size quá nhỏ.

Theo dõi thêm số connection trên DBMS, số session đang chạy/idle, slow query, lock wait, deadlock, CPU, memory, disk I/O, transaction age, replication lag và sự kiện failover. Chỉ metrics ứng dụng không đủ giải thích database đang gặp vấn đề gì.

### 4.2 Query latency và transaction duration

Đo ít nhất:

- Thời gian lấy connection.
- Thời gian thực thi query.
- Thời gian transaction từ begin đến commit/rollback.
- Số hàng đọc/ghi khi có thể đo an toàn.
- Tỷ lệ lỗi theo loại exception và SQLState.
- Số lần retry và tổng thời gian chờ retry.

Transaction kéo dài có thể giữ connection và lock lâu hơn cần thiết. Không gọi API bên ngoài, gửi email hoặc chờ người dùng trong một transaction database dài nếu có thể tách chúng khỏi transaction.

Với thao tác ghi nhiều bước, đặt transaction ở tầng service cho phần cần tính nguyên tử. Đảm bảo transaction kết thúc sớm sau khi database work hoàn tất.

## 5. Log và trace để quan sát lỗi

### 5.1 Log đủ ngữ cảnh nhưng không lộ dữ liệu

Một log sự cố hữu ích nên có:

- Timestamp và timezone rõ ràng.
- Correlation ID/trace ID để nối các log của một request.
- Tên operation/service và repository hoặc use case liên quan.
- DBMS, pool name và instance/pod nếu cần.
- Loại exception, root cause, SQLState và vendor error code.
- Thời gian lấy connection, query hoặc transaction nếu có.
- Retry attempt và kết quả cuối cùng.

Không ghi password, access token, connection string có credentials, dữ liệu thanh toán, PII hoặc toàn bộ bind parameter tùy tiện. Nếu cần nhận diện query, ưu tiên query name hoặc SQL fingerprint đã loại giá trị nhạy cảm.

Không chỉ log `exception.getMessage()` rồi bỏ stack trace và cause chain. Cần giữ root cause trong log nội bộ có quyền truy cập phù hợp. Không trả stack trace, SQL nội bộ hoặc hostname database cho client.

### 5.2 Bật SQL log trong môi trường phù hợp

Trong môi trường development/test có thể bật:

```yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
    org.springframework.orm.jpa: DEBUG
    org.springframework.transaction: DEBUG
```

Logger bind parameter thay đổi theo phiên bản Hibernate. TRACE có thể làm lộ dữ liệu thực tế và tăng lượng log rất lớn; không bật rộng rãi ở production nếu chưa có quy trình che dữ liệu và kiểm soát truy cập. Chỉ bật trong thời gian ngắn, trên một instance hoặc một nhóm request có kiểm soát khi điều tra.

### 5.3 Trace qua các lớp

Distributed tracing giúp nối request từ HTTP controller đến service, JDBC và database nếu instrumentation hỗ trợ. Khi phân tích trace:

- Tìm span có latency dài nhất.
- Phân biệt thời gian chờ connection với thời gian query.
- Kiểm tra request có retry nhiều lần không.
- Đối chiếu trace ID với application log và database log.
- Kiểm tra query bị gọi lặp (N+1) hoặc transaction mở quá lâu.

Trace không phải lúc nào cũng chứa SQL đầy đủ; tránh bật capture câu SQL và tham số nhạy cảm nếu không cần.

## 6. Phân loại sự cố kết nối và database

| Dấu hiệu | Nhóm nguyên nhân | Kiểm tra đầu tiên |
|---|---|---|
| Connection refused | Database không listen, sai host/port, service chưa lên | DB status, DNS, network, endpoint |
| Connection timed out | Firewall, network partition, route hoặc DB quá tải | Network path, latency, server load |
| Authentication failed | Credentials/secret sai, user bị khóa hoặc hết hạn | Secret version, account status, grants |
| Pool connection timeout | Không lấy được connection trong thời gian chờ | Active/idle/pending, query duration, leak |
| Connection is closed/broken | Connection bị DB/proxy đóng, failover hoặc network reset | DB event, pool lifecycle, driver log |
| Query timeout | Query lâu, lock wait hoặc server chậm | Execution plan, wait events, indexes, lock |
| Deadlock | Các transaction khóa tài nguyên theo thứ tự xung đột | DB deadlock report, transaction flow |
| Too many connections | Tổng connection vượt giới hạn DBMS | Tổng pool mọi instance, job và client |
| SQL syntax/object missing | Migration, schema hoặc query sai | DDL, migration history, DB version |
| Data integrity violation | Dữ liệu hoặc constraint không hợp lệ | Constraint name, input và dữ liệu liên quan |

Phân biệt lỗi tạm thời và lỗi cấu hình:

- Network reset, failover, server restart, deadlock hoặc serialization conflict có thể là transient tùy DBMS và operation.
- Sai password, thiếu quyền, thiếu bảng/cột, sai cú pháp SQL và mapping không tương thích thường không tự hết khi retry.
- Pool exhaustion có thể là hậu quả của query chậm hoặc connection leak; retry thêm request có thể làm tình trạng nặng hơn.

Đừng gắn mọi SQLException vào nhóm “database down”. Dùng SQLState, vendor code, health indicator và DB monitoring để xác định nguyên nhân.

## 7. Phản ứng khi database tạm thời không truy cập được

Một quy trình phản ứng thực tế:

1. **Phát hiện**: alert khi readiness DOWN, connection timeout tăng, error rate tăng hoặc pool pending tăng kéo dài.
2. **Khoanh vùng**: xác định một instance hay toàn hệ thống; kiểm tra DNS/network, DB endpoint, credentials, DB process và sự kiện failover.
3. **Giảm tải**: ngừng nhận request cần DB qua readiness, áp dụng rate limit/backpressure và tránh tạo hàng đợi không giới hạn.
4. **Bảo vệ dữ liệu**: để transaction thất bại rollback theo đúng ranh giới; không trả thành công khi chưa biết kết quả commit.
5. **Khôi phục dịch vụ**: chờ DB sẵn sàng, xác minh endpoint/role primary, quyền, schema và kết nối mới.
6. **Kiểm tra ứng dụng**: xác minh pool có thể tạo connection mới, health indicator ổn định và thao tác đọc/ghi kiểm tra hoạt động.
7. **Mở lại traffic**: đưa instance về readiness UP khi dependency đủ điều kiện; theo dõi error rate, latency và backlog.
8. **Đối soát**: xử lý request có kết quả không chắc chắn, kiểm tra dữ liệu trùng/thiếu và chạy reconciliation nếu cần.

Nếu database failover sang node/endpoint khác, cần bảo đảm JDBC URL, DNS, driver và topology connection phù hợp. Một số driver hỗ trợ failover/cluster URL; cách cấu hình tùy vendor. Không giả định mọi connection đang mở tự chuyển sang primary mới.

## 8. Phục hồi connection pool sau sự cố

HikariCP quản lý vòng đời connection. Khi connection được xác định là broken hoặc không còn hợp lệ, pool có thể loại bỏ connection đó và tạo connection mới khi database phục hồi và có thể kết nối. Connection đang được request sử dụng tại thời điểm network failure có thể vẫn ném exception; request đó không được tự động làm cho thành công chỉ vì database đã lên lại.

Cách xử lý:

- Xác minh database đã nhận kết nối mới từ đúng endpoint.
- Theo dõi active/idle/pending và connection creation failure.
- Để pool thay connection hỏng theo cơ chế quản lý của nó.
- Không restart toàn bộ ứng dụng hoặc tự tạo DataSource mới chỉ vì một vài connection lỗi.
- Chỉ cân nhắc thao tác quản trị pool khi có bằng chứng pool không tự phục hồi và đã đánh giá tác động tới request đang chạy.
- Nếu credentials/secret thay đổi, xác nhận cơ chế refresh của datasource/pool; không giả định pool đang chạy sẽ tự đọc lại secret mới.

`maxLifetime` và `keepaliveTime` giúp giảm nguy cơ connection nhàn rỗi bị hạ tầng đóng mà pool không biết. Chúng không thay thế khả năng phục hồi sau network partition hoặc database failover.

## 9. Retry an toàn trong Spring Data JPA

### 9.1 Chỉ retry lỗi transient và có giới hạn

Retry phù hợp khi lỗi có khả năng tự hết, ví dụ một số lỗi network tạm thời, failover hoặc deadlock. Không retry mù quáng các lỗi:

- Sai SQL, thiếu bảng/cột hoặc mapping sai.
- Sai credentials hoặc thiếu quyền.
- Vi phạm validation/constraint do dữ liệu đầu vào.
- Lỗi nghiệp vụ không thể thành công khi chạy lại.
- Connection pool đã cạn do tải kéo dài mà hệ thống chưa giảm tải.

Dùng số lần thử hữu hạn, exponential backoff và jitter. Có thể đặt timeout tổng cho operation để retry không vượt SLA. Không để hàng nghìn request đồng loạt retry cùng thời điểm; jitter giúp giảm retry storm.

### 9.2 Mỗi lần retry cần transaction mới

Khi một transaction đã rollback hoặc bị đánh dấu rollback-only, không tiếp tục dùng transaction đó để thử lại. Retry nên bao quanh lời gọi đi qua Spring proxy tạo transaction mới cho mỗi attempt.

Ví dụ với Spring Retry, `OrderRetryFacade` không có `@Transactional`; nó gọi `TransactionalOrderWriter` là bean riêng. Worker dùng `REQUIRES_NEW` để mỗi attempt luôn có transaction độc lập, kể cả khi facade được gọi từ một transaction bên ngoài:

```java
import org.springframework.retry.support.RetryTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderRetryFacade {

    private final RetryTemplate retryTemplate;
    private final TransactionalOrderWriter writer;

    public OrderRetryFacade(
            RetryTemplate retryTemplate,
            TransactionalOrderWriter writer) {
        this.retryTemplate = retryTemplate;
        this.writer = writer;
    }

    public Long save(OrderCommand command) {
        return retryTemplate.execute(
                context -> writer.saveOnce(command)
        );
    }
}

@Service
public class TransactionalOrderWriter {

    private final OrderRepository repository;

    public TransactionalOrderWriter(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public Long saveOnce(OrderCommand command) {
        Order order = new Order(command.idempotencyKey(), command.amount());
        return repository.save(order).getId();
    }
}
```

Cấu hình RetryTemplate minh họa:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.retry.support.RetryTemplate;

@Configuration
public class DatabaseRetryConfig {

    @Bean
    RetryTemplate databaseRetryTemplate() {
        return RetryTemplate.builder()
                .maxAttempts(3)
                .exponentialBackoff(100, 2.0, 1000)
                .retryOn(TransientDataAccessException.class)
                .build();
    }
}
```

Ví dụ cần dependency Spring Retry tương thích với phiên bản Spring đang dùng, repository/entity Order và record OrderCommand. `RetryTemplate` chỉ retry exception được chỉ định; việc phân loại exception cần kiểm chứng với JDBC driver và DBMS thực tế. Vì worker dùng `REQUIRES_NEW`, transaction ghi của mỗi attempt commit/rollback độc lập với transaction gọi facade. Chỉ dùng cách này khi nghiệp vụ chấp nhận tính độc lập đó. Nếu thao tác phải nguyên tử cùng transaction của caller, hãy đặt retry bên ngoài toàn bộ use case và tạo transaction mới cho toàn bộ use case ở mỗi attempt.

Nếu dùng `@Retryable` thay cho RetryTemplate, hãy kiểm tra thứ tự advisor/proxy để retry bao ngoài transaction và mỗi lần thử có transaction mới. Tách facade và transactional worker giúp ranh giới này rõ ràng.

### 9.3 Retry có thể tạo dữ liệu trùng

Một tình huống nguy hiểm: database đã commit nhưng network bị đứt trước khi ứng dụng nhận xác nhận. Client thấy lỗi và retry, trong khi lần đầu thực tế đã thành công. Vì vậy, operation ghi dữ liệu cần idempotency key hoặc cơ chế chống trùng ở database.

Ví dụ:

- Client gửi `request_id` duy nhất.
- Database đặt UNIQUE constraint trên request_id.
- Mỗi lần retry dùng lại cùng request_id.
- Ứng dụng đọc kết quả đã ghi nếu request_id đã tồn tại thay vì tạo bản ghi mới.

Không tạo idempotency key mới ở mỗi attempt; như vậy không còn bảo vệ được việc gửi lặp.

Với side effect ngoài database như gửi email, gọi cổng thanh toán hoặc publish message, không thực hiện lại tùy tiện trong vòng retry transaction. Cân nhắc transactional outbox, idempotent consumer và quy trình reconciliation.

## 10. Khi nào nên dùng cache hoặc graceful degradation?

Khi DB tạm thời không sẵn sàng, có thể giữ một số chức năng không phụ thuộc DB hoạt động:

- Phục vụ nội dung công khai hoặc dữ liệu cache còn hạn.
- Trả thông báo dịch vụ tạm thời không khả dụng cho thao tác ghi.
- Từ chối sớm request cần DB thay vì để request chờ connection lâu.
- Đưa công việc vào queue bền vững nếu kiến trúc hỗ trợ và có chính sách xử lý trùng.
- Trả HTTP 503 kèm Retry-After khi phù hợp.

Không dùng in-memory queue không giới hạn để giữ request trong lúc DB ngừng hoạt động; ứng dụng có thể hết memory khi outage kéo dài. Cache chỉ dùng khi chấp nhận được độ cũ dữ liệu và có quy tắc invalidation rõ ràng. Không trả dữ liệu cache như thể đó là trạng thái mới nhất nếu nghiệp vụ yêu cầu tính nhất quán tức thời.

## 11. Phục hồi sau mất dữ liệu hoặc sự cố nghiêm trọng

Nếu sự cố liên quan đến mất dữ liệu, corruption hoặc cần restore backup, đây là quy trình vận hành database và cần phối hợp DBA/DevOps:

1. Xác định phạm vi ảnh hưởng, thời điểm bắt đầu và các thao tác có thể đã commit.
2. Chọn backup/snapshot và log phục hồi theo chính sách RPO/RTO.
3. Khôi phục vào môi trường cô lập để xác minh trước.
4. Kiểm tra schema, migration version, sequence/identity, index, constraint, grants và extension.
5. Kiểm tra consistency giữa các bảng, outbox, message và hệ thống bên ngoài.
6. Chỉ chuyển traffic sau khi xác nhận database đúng role, endpoint và dữ liệu.
7. Chạy reconciliation cho các giao dịch có kết quả không chắc chắn.

Không tự động chạy DDL sửa schema hoặc restore backup từ application startup. Không xóa migration history hoặc tạo lại schema chỉ để làm ứng dụng khởi động được. Những thao tác này có thể làm mất dữ liệu hoặc khiến trạng thái migration không còn phản ánh database thực tế.

## 12. Kiểm thử khả năng phục hồi

Integration test và chaos/fault-injection test có thể kiểm tra cách ứng dụng phản ứng khi database lỗi. Thực hiện trong môi trường cô lập, có kiểm soát:

| Kịch bản | Điều cần xác minh |
|---|---|
| Database dừng trước request | Readiness chuyển DOWN, request thất bại có kiểm soát |
| Network reset khi query | Exception được phân loại, transaction rollback đúng |
| Database phục hồi | Pool tạo connection mới, readiness trở lại UP |
| Pool cạn | Request timeout theo cấu hình, metrics pending tăng và alert hoạt động |
| Query/lock timeout | Transaction kết thúc, connection được trả về pool |
| Deadlock | Một transaction thất bại; retry có giới hạn nếu operation an toàn |
| Commit acknowledgment bị mất | Idempotency ngăn ghi trùng |
| Failover sang primary mới | Connection mới trỏ đúng endpoint/role và quyền vẫn đúng |
| Restore backup | Dữ liệu, schema, migration và constraint được xác minh |

Không chạy thử dừng database production để kiểm tra nếu chưa có kế hoạch diễn tập được phê duyệt. Có thể mô phỏng bằng Testcontainers, proxy gây lỗi mạng hoặc môi trường staging tương đương.

## 13. Checklist vận hành

**Kết nối và pool**

- [ ] Ứng dụng dùng đúng DataSource, JDBC driver và endpoint.
- [ ] Pool có giới hạn phù hợp tổng số instance và connection budget của DBMS.
- [ ] Connection, query, transaction và lock timeout được cấu hình riêng.
- [ ] maxLifetime/keepaliveTime phù hợp timeout của database/proxy.
- [ ] Có metrics active, idle, pending, max và connection creation failure.

**Health và quan sát**

- [ ] Actuator health được bật và endpoint được bảo vệ.
- [ ] Liveness không phụ thuộc database một cách máy móc.
- [ ] Readiness phản ánh đúng khả năng phục vụ request cần DB.
- [ ] Alert theo error rate, latency, pool pending, DB connections, lock và replication lag.
- [ ] Log có correlation ID, exception cause, SQLState và vendor code; không lộ credentials/PII.
- [ ] Trace có thể nối request với các thao tác persistence quan trọng.

**Phục hồi và tính đúng đắn**

- [ ] Có runbook khi DB down, failover, pool exhaustion và restore.
- [ ] Retry chỉ áp dụng cho lỗi transient, có giới hạn và backoff.
- [ ] Mỗi retry dùng transaction mới.
- [ ] Ghi dữ liệu có idempotency key hoặc chống trùng.
- [ ] Không retry side effect bên ngoài một cách mù quáng.
- [ ] Có kiểm thử database outage và recovery trên môi trường phù hợp.
- [ ] Có backup, RPO/RTO và quy trình reconciliation được xác nhận.

## 14. Ghi nhớ

- Kiểm tra connection qua đúng DataSource và driver của ứng dụng.
- Phân biệt pool timeout, network timeout, query timeout, transaction timeout và lock timeout.
- Actuator readiness giúp ngừng gửi traffic mới khi database không sẵn sàng; liveness không nên phụ thuộc database theo mặc định.
- Theo dõi Hikari active/idle/pending, query latency, transaction duration và database-side metrics.
- Đọc cause chain, SQLState và vendor code; không coi mọi SQLException là database down.
- Khi database phục hồi, request đang chạy có thể đã thất bại; pool tạo connection mới không tự sửa kết quả nghiệp vụ.
- Retry phải hữu hạn, chỉ áp dụng lỗi transient, chạy trong transaction mới và bảo vệ bằng idempotency.
- Phục hồi dữ liệu cần kiểm tra consistency, migration, quyền và các side effect liên quan.

## 15. Tài liệu tham khảo

- [Spring Boot Actuator — Health](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot Actuator — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [HikariCP — Configuration](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby)
- [Spring Framework — Data Access and Exception Translation](https://docs.spring.io/spring-framework/reference/data-access/dao.html)
- [Spring Retry — Reference](https://github.com/spring-projects/spring-retry)
- [Spring Data JPA — Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html)
