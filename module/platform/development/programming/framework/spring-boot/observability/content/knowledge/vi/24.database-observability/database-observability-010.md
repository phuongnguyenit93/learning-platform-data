# Trace database call trong Spring Boot

Khi một HTTP request truy cập database, thời gian xử lý có thể bị tiêu tốn ở nhiều đoạn: chờ connection từ pool, gửi SQL qua JDBC driver, chờ database thực thi, đọc result set và mapping dữ liệu. HTTP server span cho biết tổng thời gian request nhưng không tự chỉ ra database call nào chiếm thời gian. **Trace database call** bổ sung span cho thao tác database, đặt nó vào đúng vị trí trong trace, liên kết với request cha và giúp so sánh thời gian ở application, JDBC client và database.

Trong module **SPRING_BOOT_OBSERVABILITY**, database tracing bổ sung cho Micrometer Observation, metrics, logs và distributed tracing. Bài thuộc chương **Database observability**, tập trung vào **Trace database call**: mô hình span cho database operation, cách instrument JDBC, phân biệt agent/framework/proxy/custom Observation, đọc SQL metadata an toàn, liên kết transaction và parent context, kiểm thử và điều tra khi database spans thiếu hoặc sai.

## Mục tiêu học tập

Sau bài này, bạn có thể:
1. Giải thích vị trí database span trong distributed trace.
2. Phân biệt JDBC client span, business Observation và pool metrics.
3. Nhận biết các lựa chọn instrument database call trong Spring Boot.
4. Đọc trace hierarchy, duration, status và database attributes.
5. Hiểu parent context trong transaction, async và nested database calls.
6. Kiểm soát SQL text, bind values, cardinality và dữ liệu nhạy cảm.
7. Kiểm thử database spans bằng test exporter và test database.
8. Điều tra slow query, missing spans, duplicate spans và lỗi propagation.

## 1. Trace database call là gì?

Database span mô tả một thao tác database trong trace. Span thường mang operation name, thời điểm bắt đầu/kết thúc, status, attributes mô tả database system/operation và quan hệ parent với span hiện hành.

~~~text
Trace ID: 4bf92f...

HTTP server span: POST /orders
  └─ Business span: orders.create
       ├─ JDBC span: INSERT orders
       ├─ JDBC span: SELECT inventory
       └─ JDBC span: UPDATE order_status
~~~

Database spans cho biết thao tác nào mất thời gian và phát sinh lỗi. Chúng không nhất thiết phản ánh chính xác thời gian engine chạy SQL; tùy instrumentation boundary, duration có thể bao gồm driver overhead, network, connection handling và result processing.

### 1.1. Database span nằm ở đâu trong trace?

~~~mermaid
flowchart TD
    Request["Incoming HTTP request"] --> Server["HTTP server span"]
    Server --> Business["Business Observation / span"]
    Business --> JdbcA["JDBC client span: SELECT"]
    Business --> JdbcB["JDBC client span: INSERT"]
    JdbcB --> Database["Database server"]
    Server --> Logs["Logs with traceId/spanId"]
    JdbcA --> Export["Tracing exporter"]
    JdbcB --> Export
    Server --> Export
    Export --> Backend["Trace backend"]
~~~

Trong trace viewer, database spans thường nằm dưới server span hoặc business span tùy active context. Nếu code gọi nhiều repository methods, mỗi call được instrument có thể tạo span riêng. Không gộp mọi database activity vào một span nếu cần điều tra từng thao tác.

### 1.2. Database span và HTTP span

HTTP server span bao trùm request handling. JDBC span chỉ bao quanh database operation. Nếu server span kéo dài 900 ms và JDBC spans tổng cộng 500 ms, phần còn lại có thể thuộc controller/service, pool wait không được bao gồm trong JDBC span, remote calls hoặc hoạt động khác. Không cộng duration của mọi child spans rồi mặc định bằng server span: spans có thể lồng nhau hoặc chạy song song.

## 2. Các cách instrument database call

JDBC API không tự đảm bảo tracing spans. Cần một instrumentation mechanism phù hợp.

| Cách | Điểm instrument | Ưu điểm | Lưu ý |
| --- | --- | --- | --- |
| Java agent | JDBC calls qua bytecode hooks | Bao phủ nhiều thư viện mà ít sửa code | Kiểm tra agent/module compatibility và overhead |
| Framework-native instrumentation | Spring/Micrometer/ORM integration | Gắn với framework lifecycle và Observation | Phạm vi phụ thuộc framework/version |
| DataSource proxy/wrapper | Connection/Statement operations | Thêm instrumentation vào DataSource | Dễ trùng với agent/native instrumentation |
| Custom Observation | Business/repository boundary | Tên operation theo nghiệp vụ | Không tự động mô tả mọi SQL statement |
| DB-native monitoring | Trong database engine | Query plan, locks, execution statistics | Không thay distributed trace context |

### 2.1. Không nhầm tracing bridge với JDBC instrumentation

Micrometer Tracing bridge kết nối Micrometer Tracing với OpenTelemetry. Nó cho phép spans được quản lý/export, nhưng không tự bảo đảm mọi JDBC call đều được instrument. OTLP exporter chỉ vận chuyển spans đã được tạo; nếu không có JDBC instrumentation, exporter không tự khám phá SQL statements.

### 2.2. Chọn một instrumentation owner

Nếu Java agent và DataSource proxy cùng instrument một statement, trace có thể chứa hai spans gần giống nhau. Điều này làm timeline khó đọc và tăng telemetry volume. Xác định một cơ chế chính ở JDBC boundary; business Observation ở tầng service có thể là span cha nếu nó mô tả operation riêng.

### 2.3. Kiểm tra phạm vi hỗ trợ

Trước khi bật production, kiểm tra database vendor, JDBC driver version, Spring Boot/Spring Framework version, tracing API/SDK compatibility, agent module và async/transaction behavior. Không giả định cấu hình cho PostgreSQL áp dụng nguyên trạng cho Oracle, SQL Server hoặc MySQL.

## 3. Trace hierarchy từ request đến JDBC

~~~mermaid
sequenceDiagram
    participant Client
    participant App as Spring Boot
    participant Repo as Repository/JdbcTemplate
    participant Driver as JDBC driver
    participant DB as Database
    participant Collector
    Client->>App: POST /orders + traceparent
    Note over App: HTTP server span
    App->>Repo: createOrder()
    Note over App,Repo: Business span orders.create
    Repo->>Driver: PreparedStatement.execute()
    Note over Repo,Driver: JDBC client span
    Driver->>DB: SQL operation
    DB-->>Driver: Result
    Driver-->>Repo: Update count / rows
    Repo-->>App: Return
    App-->>Client: HTTP response
    App->>Collector: Export spans
~~~

Trace ID được chia sẻ trong cùng trace; mỗi span có Span ID riêng. JDBC span nên có parent là span active khi database call bắt đầu. Nếu operation được gọi từ HTTP request, parent chain có thể đi từ server span qua business span tới JDBC span.

### 3.1. Parent-child và nested spans

Ví dụ:
- server span: POST /orders;
- business span: orders.create;
- JDBC span: INSERT orders;
- JDBC span: SELECT inventory.

JDBC spans là children của business span nếu nó active tại thời điểm gọi. Nếu không có business span, chúng có thể là children trực tiếp của server span. Không tạo parent span thủ công bằng cách copy Trace ID/Span ID vào MDC; dùng tracing context/scope API để SDK quản lý quan hệ.

### 3.2. Nhiều JDBC calls song song

Một business operation có thể chạy nhiều database calls trên executor. Context phải được propagate sang worker. Nếu không, spans có thể thành root traces riêng hoặc không có parent. Khi chạy song song, child spans có thể overlap; tổng duration không bằng wall-clock duration của request.

## 4. Database attributes và semantic conventions

Database span cần metadata vừa đủ để nhận diện hệ thống và loại operation. OpenTelemetry semantic conventions có thể dùng các thuộc tính như db.system.name, db.operation.name, db.namespace, server.address và server.port, tùy convention version/instrumentation.

| Attribute | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| db.system.name | Database engine | postgresql |
| db.operation.name | Operation chính | SELECT, INSERT |
| db.namespace | Database/schema namespace | commerce |
| server.address | Host DB | postgres.internal |
| server.port | Port DB | 5432 |
| db.collection.name | Table/collection nếu convention áp dụng | orders |
| db.query.text | Query text nếu được phép | SELECT ... WHERE id = ? |
| error.type | Nhóm lỗi | SQLTransientConnectionException |

Tên attributes và yêu cầu semantic conventions có thể thay đổi theo phiên bản. Kiểm tra instrumentation version và convention đang phát ra; không tự đổi key nếu backend/dashboard chưa tương thích.

### 4.1. Operation name và query text

Operation name nên mô tả thao tác ổn định, ví dụ SELECT hoặc INSERT. Không đưa customer ID/order ID vào span name. Query text có thể giúp xác định câu SQL nhưng phải được sanitize/parameterize. Trong nhiều hệ thống, operation name và statement summary đã chuẩn hóa là đủ.

### 4.2. SQL bind parameters

Không thu thập bind parameter values mặc định. Parameters có thể là email, access token, payment data, personal identifiers hoặc secrets. Nếu điều tra cần giá trị cụ thể, dùng công cụ database có kiểm soát quyền và quy trình dữ liệu phù hợp, không đưa hàng loạt values vào traces.

## 5. Cấu hình tracing trong Spring Boot

Ví dụ dependency để Spring Boot dùng Micrometer Tracing bridge OpenTelemetry và OTLP exporter:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'
}
~~~

Giữ phiên bản theo Spring Boot BOM. Các dependencies này thiết lập tracing bridge/export path, không phải cam kết JDBC statement instrumentation tự động được bật.

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.10
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
~~~

Endpoint phải trỏ tới Collector có thể truy cập từ ứng dụng. Trong container/Kubernetes, dùng DNS/service address thích hợp thay vì localhost nếu Collector ở container/pod khác.

### 5.1. Bật JDBC instrumentation bằng cơ chế đã chọn

Nếu dùng Java agent, cấu hình agent và module JDBC tương ứng theo version. Nếu dùng DataSource proxy, cấu hình wrapper làm DataSource được Spring inject và xác minh transaction managers/repositories dùng wrapper đó. Nếu framework version có native JDBC observation, kiểm tra property và điều kiện auto-configuration trong tài liệu đúng version.

Không thêm property đoán mò hoặc tạo proxy thứ hai khi chưa xác định instrumentation đang hoạt động.

### 5.2. Custom business Observation quanh repository

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class InvoiceRepository {
    private final JdbcTemplate jdbcTemplate;
    private final ObservationRegistry registry;

    public InvoiceRepository(
            JdbcTemplate jdbcTemplate,
            ObservationRegistry registry
    ) {
        this.jdbcTemplate = jdbcTemplate;
        this.registry = registry;
    }

    public Integer countUnpaidInvoices() {
        return Observation.createNotStarted("invoice.repository.count-unpaid", registry)
                .lowCardinalityKeyValue("db.operation", "SELECT")
                .observe(() -> jdbcTemplate.queryForObject(
                        "select count(*) from invoice where status = ?",
                        Integer.class,
                        "UNPAID"
                ));
    }
}
~~~

Observation này mô tả repository operation và tạo span/metrics theo handlers đang cấu hình. Nó không nhất thiết là span cho từng JDBC statement. Nếu JDBC agent cũng tạo span bên trong, hierarchy business → JDBC có thể hữu ích. Đừng thêm business span để thay thế JDBC instrumentation khi cần timing từng statement.

## 6. Phân biệt pool wait, JDBC span và database execution

~~~text
Application requests connection
  ├─ Wait for pool connection
  ├─ Obtain JDBC Connection
  ├─ Prepare/bind statement
  ├─ Execute over network
  ├─ Database execution / lock waits
  ├─ Transfer result
  ├─ Map rows
  └─ Return connection
~~~

Instrumentation ở JDBC Statement có thể chỉ bao quanh prepare/execute/result operation; nó không nhất thiết bao gồm thời gian chờ DataSource connection. Pool metrics cung cấp acquisition/usage measurements riêng.

| Quan sát | Có thể chỉ ra | Cần đối chiếu |
| --- | --- | --- |
| Pool acquisition time cao | Chờ connection | Active/idle/pending/max |
| JDBC span duration cao | Operation phía client chậm | DB query stats, network, result size |
| DB execution time cao | Engine thực thi/lock chậm | Explain plan, locks, DB CPU/IO |
| Connection usage cao nhưng JDBC spans ngắn | Giữ connection ngoài execute | Transaction/application code |
| HTTP span cao, JDBC spans thấp | Thời gian nằm ở tầng khác | Business spans, remote calls, serialization |

Không diễn giải JDBC span duration là thời gian engine thuần túy nếu instrumentation không đo trực tiếp database server.

## 7. Transaction boundaries và database spans

Spring transaction management thường quản lý connection lifecycle qua transaction manager. Nhiều JDBC operations có thể nằm trong một transaction.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InvoiceService {
    private final InvoiceRepository repository;

    public InvoiceService(InvoiceRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void settleInvoice() {
        repository.markPaid();
        repository.writeAuditRecord();
    }
}
~~~

Database spans có thể là children trong transaction/business context, nhưng không phải mọi transaction đều tự động trở thành một span. Instrumentation quyết định span boundaries. Nếu cần đo transaction duration, tạo business Observation có tên ổn định quanh use case và tránh ghi thêm span trùng với từng JDBC call.

### 7.1. Rollback và exception

Database span có thể kết thúc với error status khi JDBC operation ném exception. Transaction có thể rollback sau đó. Phân biệt SQL operation thất bại, transaction rollback do lỗi ở operation sau, rollback theo business rule và lỗi commit/connection khi hoàn tất transaction.

Không gán lỗi cho câu SQL cuối cùng nếu rollback phát sinh từ logic khác. Đọc span events/status, application logs và transaction outcome.

### 7.2. Transaction quá dài

Transaction dài có thể giữ connection trong lúc ứng dụng gọi remote service hoặc xử lý business logic. Database spans riêng lẻ có thể ngắn nhưng connection usage vẫn cao. Tracing business span và pool metrics giúp thấy khoảng thời gian ngoài SQL.

## 8. Cardinality, privacy và query capture

| Dữ liệu | Metrics | Traces | Chính sách |
| --- | --- | --- | --- |
| db.system.name | Có thể | Có | Giá trị chuẩn hóa |
| db.operation.name | Có | Có | Tập operation nhỏ |
| database/schema name | Cân nhắc | Có thể | Không chứa tenant động |
| server.address/port | Không mặc định làm label | Có thể | Kiểm soát topology |
| raw SQL text | Không | Không mặc định | Sanitize và review |
| bind parameter values | Không | Không | Có thể chứa secrets/PII |
| customer/order ID | Không | Không mặc định | High cardinality |
| exception message | Không | Không mặc định | Redact, ưu tiên error category |
| JDBC URL credentials | Không | Không | Secret |

### 8.1. Không dùng SQL text làm metric tag

SQL text có thể khác nhau theo literals, whitespace hoặc generated query. Dùng nó làm tag có thể tạo series vô hạn. Metrics nên nhóm theo operation hoặc query name ổn định đã được kiểm soát.

### 8.2. Query normalization và redaction

Nếu cần nhận diện query shape, dùng query fingerprint hoặc normalized statement name từ instrumentation/backend đã được kiểm tra. Fingerprint vẫn có thể tiết lộ cấu trúc schema và cần policy. Redact trước khi telemetry rời process; backend masking chỉ che giao diện, payload có thể đã được lưu ở Collector/queue/storage.

Không ghi credentials vào Resource, span attributes, MDC hay exception message.

## 9. Logs và database spans

Log event có thể mang traceId/spanId qua MDC. Khi database operation thất bại, log exception trong active span context để người vận hành tìm trace tương ứng.

~~~text
ERROR traceId=4bf92f... spanId=8a31c2...
  InvoiceRepository - Database operation failed
  error.type=SQLTransientConnectionException
~~~

Không log raw bind values hoặc full SQL nếu chưa sanitization. Dùng SQLState, error category và operation name đã chuẩn hóa.

### 9.1. Từ log tới database span

1. Tìm log event theo traceId.
2. Mở trace backend theo cùng Trace ID.
3. Tìm JDBC span theo spanId nếu log được ghi trong span đó.
4. Đọc operation, duration, status và database attributes.
5. Xem parent business/server span để hiểu request context.
6. Đối chiếu pool metrics và database-native query stats cùng thời điểm.

Log có traceId không bảo đảm database span được tạo hoặc export. Sampling có thể drop trace; JDBC instrumentation có thể chưa bật; exporter hoặc Collector có thể drop spans. Điều tra từng tầng riêng.

## 10. Kiểm thử database tracing

| Test type | Mục tiêu | Không tự chứng minh |
| --- | --- | --- |
| Repository integration test | JDBC operation thực thi | JDBC span tồn tại |
| Observation test | Custom business Observation | Driver instrumentation |
| In-memory span exporter | Span name/context/attributes | OTLP network export |
| Agent integration test | Agent instrument JDBC calls | Production DB performance |
| Collector smoke test | OTLP spans được nhận | SQL execution plan |
| DB-native test | Query/lock behavior | Trace propagation |

### 10.1. Test custom Observation

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.tck.TestObservationRegistry;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class InvoiceObservationTest {
    @Test
    void recordsRepositoryOperation() {
        TestObservationRegistry registry = TestObservationRegistry.create();
        Observation.createNotStarted("invoice.repository.count-unpaid", registry)
                .lowCardinalityKeyValue("db.operation", "SELECT")
                .observe(() -> { });
        assertThat(registry.getCompletedObservationContexts()).hasSize(1);
    }
}
~~~

API assertion có thể thay đổi theo Micrometer version. Test này chỉ chứng minh business Observation lifecycle, không chứng minh JDBC driver tự tạo span.

### 10.2. Test parent-child span

Với tracing SDK test setup và in-memory exporter:
1. Tạo parent span.
2. Đặt parent vào scope.
3. Thực thi JDBC operation qua instrumentation đang kiểm tra.
4. Kết thúc parent.
5. Thu spans từ exporter.
6. Assert JDBC span cùng Trace ID và có parent span ID phù hợp.
7. Kiểm tra operation/attributes không chứa bind values.

Nếu dùng agent, test phải chạy với agent được gắn vào JVM test process; unit test không gắn agent không chứng minh agent instrumentation.

### 10.3. Test lỗi và transaction rollback

Tạo test database, thực hiện statement lỗi có kiểm soát và xác minh exception, span status/error convention, transaction rollback, dữ liệu nhạy cảm không xuất hiện và context parent được restore sau exception. Không dùng production database để cố tình tạo deadlock hoặc connection exhaustion trong test.

## 11. Troubleshooting database spans

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Trace chỉ có HTTP span | JDBC instrumentation chưa bật | Xác định agent/native/proxy đang dùng |
| Có pool metrics nhưng không có JDBC span | Pool binder không instrument statements | Bổ sung JDBC instrumentation |
| Có hai spans cho một statement | Agent và proxy cùng instrument | Chọn một instrumentation owner |
| JDBC span thành root trace | Parent context không active/propagate | Kiểm tra current span và async context |
| Span không có db.system | Instrumentation thiếu database metadata | Kiểm tra driver/semantic convention |
| Span chứa raw SQL literals | Statement capture chưa sanitize | Redact/disable query text |
| JDBC span ngắn nhưng request chậm | Pool wait hoặc thời gian ngoài JDBC execute | Đối chiếu acquisition/usage và business spans |
| JDBC span dài | DB, network, driver hoặc result mapping | DB-native query stats, locks, result size |
| Span không báo lỗi dù transaction rollback | Rollback sau operation hoặc business rule | Kiểm tra transaction outcome riêng |
| Span count tăng bất thường | Duplicate instrumentation hoặc N+1 | Xem hierarchy và query count |
| Database span mất trong async | Context không được propagate | Kiểm tra executor/context propagation |
| Exporter không gửi span | Sampling, queue, endpoint hoặc Collector | Kiểm tra tracing pipeline |

### 11.1. Quy trình điều tra

1. Xác định cơ chế JDBC instrumentation đang chạy: agent, native integration hay DataSource wrapper.
2. Kiểm tra một query test có tạo span hay không.
3. Xem span parent, Trace ID và Span ID.
4. Kiểm tra operation name và database attributes.
5. So sánh JDBC span duration với pool acquisition/usage.
6. Nếu query chậm, đối chiếu DB-native execution stats, lock waits và query plan.
7. Kiểm tra duplicate spans, N+1 và transaction duration.
8. Xem SQL capture, bind values, credentials và PII đã được lọc.
9. Nếu span đã tạo nhưng backend không có, điều tra sampler/exporter/Collector.

## 12. Production checklist

| Tiêu chí | Bằng chứng cần có |
| --- | --- |
| JDBC instrumentation được chọn rõ | Agent/native/proxy được ghi nhận |
| Không duplicate instrumentation | Một statement không tạo spans trùng |
| Span hierarchy đúng | JDBC span có parent request/business span |
| Database attributes chuẩn hóa | db.system/operation phù hợp convention |
| Query capture an toàn | Không bind values, secrets hoặc PII |
| Pool metrics độc lập | Active/idle/pending/acquisition được theo dõi |
| DB-native monitoring bổ sung | Query stats, locks, CPU/IO có thể đối chiếu |
| Transaction outcome rõ | Commit/rollback/error được quan sát |
| Async context được kiểm tra | Worker spans có parent phù hợp |
| Cardinality thấp | Không SQL/customer IDs làm metric labels |
| Sampling/export được giám sát | Dropped spans và exporter errors có cảnh báo |
| Regression tests có ý nghĩa | Parent-child, error, rollback và redaction |

## 13. Bài thực hành: trace một database call

**Bối cảnh:** order-service nhận HTTP request, tạo đơn trong transaction và ghi dữ liệu vào PostgreSQL. HTTP trace hiện chỉ có server span; đội vận hành muốn xác định từng database operation.

**Nhiệm vụ:**
1. Bật Spring Boot Actuator và Micrometer Tracing bridge theo BOM.
2. Chọn một JDBC instrumentation mechanism (agent, native integration hoặc DataSource proxy) và ghi rõ version.
3. Dùng test database để tạo request đi qua repository/JdbcTemplate.
4. Thu trace và xác minh database spans xuất hiện dưới server/business span.
5. Kiểm tra Trace ID, Span ID, parent relationship và operation name.
6. Thực hiện SELECT/INSERT/UPDATE và so sánh span durations.
7. Tạo statement lỗi có kiểm soát và kiểm tra span status/exception.
8. Thực hiện rollback và phân biệt lỗi statement với transaction outcome.
9. So sánh JDBC span duration với Hikari acquisition/usage metrics.
10. Xác minh SQL text/bind values/credentials không bị export ngoài policy.
11. Chạy test với instrumentation thứ hai để nhận diện duplicate spans, sau đó giữ một cơ chế.
12. Viết runbook cho missing JDBC span, root span, slow database call và SQL leakage.

**Kết quả mong đợi:** trace có database spans, hierarchy rõ ràng, metadata an toàn, test chứng minh instrumentation đã chọn và runbook điều tra.

## 14. Ghi nhớ

**Trace database call** đặt database operation vào đúng distributed trace để giải thích request đã thực hiện thao tác JDBC nào, mất bao lâu và phát sinh lỗi ở đâu. Micrometer Tracing bridge/exporter vận chuyển spans đã được tạo; JDBC instrumentation riêng (agent, framework integration hoặc DataSource wrapper) mới quyết định statement nào được instrument. Custom business Observation bổ sung operation nghiệp vụ và không thay thế JDBC span khi cần timing từng statement.

Đọc database span cùng HTTP/business spans, pool acquisition/usage metrics và DB-native query statistics. Không đồng nhất JDBC duration với engine execution time; không nhầm pool metrics với query spans. Giữ parent context đúng, tránh instrumentation trùng, sanitize SQL và không thu bind values/credentials/PII. Dùng metrics cho xu hướng và pool health, traces để điều tra request cụ thể, logs để xem lỗi đã được redaction.

**Tài liệu tham khảo:**
- [Micrometer Observation — Reference](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Micrometer Tracing — Reference](https://docs.micrometer.io/tracing/reference/)
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot — JDBC Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [OpenTelemetry — Database Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/db/)
- [OpenTelemetry — Java Instrumentation](https://opentelemetry.io/docs/zero-code/java/agent/)
- [HikariCP — Configuration](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby)
- [JDBC — Java Documentation](https://docs.oracle.com/javase/8/docs/technotes/guides/jdbc/)

