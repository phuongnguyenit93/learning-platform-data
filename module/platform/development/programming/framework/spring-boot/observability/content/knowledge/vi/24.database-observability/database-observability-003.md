# JDBC observation starter

Trong chương **Database observability** của mô-đun **SPRING_BOOT_OBSERVABILITY**, JDBC observation starter là điểm bắt đầu để quan sát truy cập cơ sở dữ liệu qua JDBC trong ứng dụng Spring Boot. Khi DataSource và JDBC instrumentation được cấu hình đúng, thao tác truy vấn có thể tạo Observation/trace spans, giúp nhận diện câu lệnh chậm, lỗi kết nối và dependency database gây ảnh hưởng tới request.

Cần phân biệt ba loại tín hiệu: **JDBC observations/traces** mô tả từng lần thực thi SQL; **DataSource pool metrics** mô tả trạng thái connection pool; **database/server metrics** mô tả sức khỏe database. Chúng bổ sung cho nhau nhưng không thay thế nhau. Pool có active connections cao không chứng minh câu SQL cụ thể nào chậm; JDBC span chậm cũng chưa đủ kết luận database server quá tải.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:
1. Giải thích vai trò JDBC observation trong Spring Boot.
2. Phân biệt database spans, pool metrics và database server metrics.
3. Xác định điều kiện để JDBC operations được instrument.
4. Cấu hình tracing bridge/exporter và kiểm tra dependency compatibility.
5. Hiểu DataSource instrumentation bao quanh connection acquisition và câu lệnh JDBC ra sao.
6. Đọc database spans và liên kết chúng với HTTP/server spans.
7. Nhận diện giới hạn với ORM, R2DBC và custom drivers.
8. Kiểm soát SQL attributes, bind values, cardinality và dữ liệu nhạy cảm.
9. Kiểm tra spans qua trace backend và metrics qua Actuator.
10. Viết integration test và runbook cho database observability.

## 2. JDBC observation starter là gì?

Spring Boot Actuator và Micrometer Tracing cung cấp hạ tầng observability; JDBC instrumentation bổ sung quan sát cho hoạt động qua JDBC DataSource. Tùy Spring Boot version và tracer, dependency starter/bridge sẽ khác nhau. Khi instrumentation được bật, JDBC calls có thể tạo spans đại diện cho thao tác database, với attributes mô tả hệ quản trị, operation và statement theo policy của instrumentation.

Một starter không tự biến mọi database access thành spans nếu ứng dụng không đi qua JDBC path được instrument:
- JDBC qua DataSource được instrument có thể tạo database spans.
- Hibernate thực hiện SQL qua JDBC; spans có thể được tạo ở JDBC layer, nhưng không phải mọi ORM operation đều có span nghiệp vụ riêng.
- R2DBC là reactive database API, không phải JDBC; cần instrumentation tương ứng.
- Native driver API hoặc client riêng có thể nằm ngoài JDBC instrumentation.
- DataSource proxy/pool hoặc custom wrapper có thể ảnh hưởng vị trí instrumentation.

Tên artifact và cách bật phụ thuộc Spring Boot/Spring Framework/Micrometer version. Đọc tài liệu đúng version thay vì thêm dependency có tên gần giống từ tutorial cũ.

## 3. Các lớp database observability

| Tín hiệu | Quan sát điều gì? | Ví dụ |
| --- | --- | --- |
| JDBC observation/span | Một thao tác database qua JDBC mất bao lâu và kết thúc thế nào. | SELECT trên orders mất 420 ms. |
| DataSource pool metrics | Connection pool đang sử dụng tài nguyên ra sao. | Active, idle, max, pending. |
| Database server metrics | Sức khỏe và tải bên trong DB engine. | CPU, locks, buffer cache, replication lag. |
| Application logs | Sự kiện nghiệp vụ/lỗi cụ thể. | Transaction rollback. |
| HTTP/server span | Request inbound bao quanh nhiều dependency calls. | POST /orders gọi JDBC và inventory. |

~~~mermaid
flowchart TD
    HTTP["HTTP server request span"]
    HTTP --> Service["Service / repository"]
    Service --> JDBC["JDBC observation / database span"]
    JDBC --> DS["DataSource / connection pool"]
    DS --> DB["Database engine"]
    DS --> PoolMetrics["Pool metrics"]
    DB --> DBMetrics["Database server metrics"]
    JDBC --> TraceBackend["Trace backend"]
    PoolMetrics --> MetricsBackend["Metrics backend"]
    DBMetrics --> MetricsBackend
~~~

Database span cho biết thời gian quan sát ở application boundary. Pool metrics cho biết việc lấy/giữ connections. Database server metrics cho biết điều gì xảy ra bên trong DB engine. Đối chiếu cả ba giúp xác định bottleneck.

## 4. Dependency và version compatibility

Với Spring Boot, ưu tiên starter và dependency management do Boot quản lý. Tracing bridge quyết định tracer implementation; JDBC instrumentation bổ sung khả năng quan sát cho database calls. Không thêm nhiều bridge hoặc auto-instrumentation layers cùng lúc.

Spring Boot 3.x thường dùng Micrometer Tracing với OpenTelemetry như sau:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    implementation 'io.opentelemetry:opentelemetry-exporter-otlp'
    runtimeOnly 'com.mysql:mysql-connector-j'
}
~~~

Hoặc chọn Brave thay OpenTelemetry:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-brave'
    implementation 'io.zipkin.reporter2:zipkin-reporter-brave'
    runtimeOnly 'com.mysql:mysql-connector-j'
}
~~~

Hai ví dụ là lựa chọn thay thế nhau. Không khai báo cả OTel bridge và Brave bridge. Driver MySQL chỉ là ví dụ; dùng driver thực tế của dự án.

Ở Spring Boot major versions mới hơn, starter/module tracing có thể được tổ chức lại. Không suy luận có một artifact tên JDBC observation starter giống nhau cho mọi version. Xác minh dependency tree và reference docs của minor version đang dùng. Nếu dùng OpenTelemetry Java Agent, agent có thể tự instrument JDBC; tránh thêm instrumentation thủ công trùng lặp.

## 5. Bật tracing và export database spans

JDBC instrumentation thường xuất database spans qua tracing pipeline đã cấu hình. Ví dụ Spring Boot 3.x với OTLP:

~~~yaml
spring:
  application:
    name: order-service

management:
  tracing:
    sampling:
      probability: 0.1
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
~~~

Property namespace và endpoint semantics thay đổi theo Spring Boot version. Một số dòng Boot mới tổ chức tracing export dưới namespace khác. Kiểm tra đúng version và protocol của Collector; HTTP/protobuf thường dùng cổng 4318 với signal path, gRPC thường dùng cổng 4317.

Nếu dùng Zipkin/Brave, cấu hình Zipkin reporter và endpoint tương ứng; không đặt Zipkin endpoint vào OTLP property. Sampling probability quyết định tỷ lệ trace được chọn, không phải bật/tắt JDBC instrumentation. Nếu trace bị head-sampled out, database spans của trace đó cũng không xuất hiện trong backend.

Xác nhận có đúng một Micrometer Tracing bridge; ObservationRegistry có tracing handler; tracer/exporter được wire đúng; JDBC instrumentation thực sự bật; exporter endpoint khớp Collector receiver; không có Java agent/custom instrumentation tạo duplicate spans.

## 6. JDBC instrumentation hoạt động ở đâu?

JDBC instrumentation thường quan sát hoạt động tại DataSource/driver boundary, nơi ứng dụng lấy connection và thực thi statement. Tùy implementation, span có thể ghi database system/vendor, operation như SELECT/INSERT/UPDATE/DELETE, database name hoặc connection metadata được phép, statement representation, error status/exception type và duration.

Không phải mọi implementation đều ghi mọi attribute. OpenTelemetry semantic conventions và Micrometer instrumentation version có thể khác nhau về tên attribute và mức chi tiết. Hãy xem payload spans thực tế.

### JDBC span và ORM operation

Một lệnh repository có thể thực hiện nhiều SQL statements: lazy loading, N+1 selects, flush hoặc transaction queries. JDBC spans thường phản ánh từng thao tác JDBC được instrument; chúng không nhất thiết tương ứng một-một với method repository.

Ví dụ một repository method gọi 1 SELECT có thể tạo một span; entity graph gây 12 SELECT có thể tạo nhiều spans; transaction có thể chứa nhiều statements; batch update có thể gom nhiều row operations vào một JDBC call. Dùng trace waterfall để nhận diện số lượng database calls. Nếu thấy nhiều spans ngắn lặp lại, kiểm tra N+1 query, ORM fetch strategy và batching.

## 7. DataSource và connection pool metrics

Spring Boot Actuator có thể instrument DataSource và expose pool metrics khi pool implementation được hỗ trợ và registry phù hợp. Với HikariCP, metrics thường liên quan active/idle/max/minimum connections và pending threads chờ connection.

Ví dụ truy vấn:

~~~http
GET /actuator/metrics/jdbc.connections.active
GET /actuator/metrics/jdbc.connections.idle
GET /actuator/metrics/hikaricp.connections.pending
~~~

Tên meter cụ thể phụ thuộc pool, version và binders. Một số pool metrics nằm dưới namespace hikaricp.* thay vì jdbc.*; inspect Actuator /actuator/metrics để xác nhận.

Nếu JDBC spans chậm nhưng pool active connections không cao, bottleneck có thể nằm ở DB execution hoặc network. Nếu pending threads tăng và connection acquisition chậm, pool có thể cạn hoặc connections bị giữ quá lâu. Không tăng maximum pool size máy móc: nhiều connections hơn có thể làm DB server chịu tải nặng hơn và tăng contention. Điều chỉnh pool dựa trên capacity DB và số replicas ứng dụng.

## 8. Liên kết HTTP spans và JDBC spans

Trong request inbound, tracing context được propagate từ server span qua service/repository tới JDBC instrumentation. Database span thường là child span hoặc nằm trong cây trace của request hiện tại.

~~~mermaid
sequenceDiagram
    participant Client
    participant App as order-service
    participant Repo as OrderRepository
    participant DS as Instrumented DataSource
    participant DB as Database
    participant Trace as Trace backend

    Client->>App: POST /orders
    Note over App: HTTP server span
    App->>Repo: save(order)
    Repo->>DS: execute INSERT
    Note over DS: JDBC/database span
    DS->>DB: SQL
    DB-->>DS: Result
    DS-->>Repo: Update count
    Repo-->>App: Saved
    App-->>Client: 201 Created
    DS->>Trace: Export DB span
    App->>Trace: Export server span
~~~

Nếu database span xuất hiện như trace root riêng, kiểm tra context propagation và JDBC instrumentation. Xác minh spans không bị sampling decision hoặc exporter drop.

## 9. SQL statement attributes và dữ liệu nhạy cảm

SQL statements có thể chứa literal values hoặc thông tin schema nhạy cảm:

~~~sql
SELECT * FROM users WHERE email = 'alice@example.com';
UPDATE accounts SET balance = 1000000 WHERE account_id = 'A-9182';
~~~

Một số instrumentation có thể normalize SQL hoặc chỉ ghi operation/statement summary, nhưng không giả định mọi driver/agent tự che literal values.

- Không export bind parameter values nếu chứa PII, secrets hoặc dữ liệu thanh toán.
- Ưu tiên statement summary/normalized query nếu instrumentation hỗ trợ.
- Giới hạn độ dài SQL attributes.
- Không gắn raw database URL/connection string chứa username/password vào span.
- Kiểm tra exception messages có nhúng SQL hoặc parameter values không.
- Dùng database system, operation và query fingerprint đã kiểm soát khi có thể.
- Bảo vệ traces backend bằng RBAC và retention phù hợp.

Database span có thể có statement attribute cardinality cao. Không dùng full SQL text làm metric tag. Metrics dimensions nên ổn định như datasource name, operation và outcome.

## 10. Transactions và connection lifecycle

Transaction có thể kéo dài lâu hơn một câu SQL. Database spans thường phản ánh từng thao tác JDBC được instrument; không nhất thiết bao trọn business transaction hoặc toàn bộ thời gian connection bị giữ.

Một transaction có thể lấy connection, bắt đầu transaction, thực hiện SELECT/UPDATE, commit/rollback và trả connection về pool. Trace có thể chứa nhiều spans cho statements, trong khi pool metrics phản ánh connection đang được giữ. Nếu transaction mở lâu nhưng SQL spans ngắn, kiểm tra application logic giữa queries, lock wait, transaction propagation và connection leak.

Không suy ra transaction duration chỉ bằng cách cộng durations của database spans nếu có thời gian xử lý nằm giữa statements.

## 11. Sampling và chi phí database tracing

Mỗi request có thể tạo nhiều JDBC spans. Ước lượng:

~~~text
database_spans_per_second =
    inbound_requests_per_second
    * average_jdbc_calls_per_request
    * trace_sampling_ratio
~~~

Ví dụ 300 request/giây, trung bình 6 JDBC calls/request và sampling 10%:

~~~text
300 * 6 * 0.1 = 180 database spans/second
~~~

Đây là ước lượng; retry, batch, async operations và spans không gắn với inbound request có thể làm số thực tế khác.

Sampling giảm số traces được lưu, nhưng không thay thế kiểm soát statement attributes/cardinality. Dùng parent-based sampling để giữ quyết định nhất quán xuyên services. Nếu dùng tail sampling tại Collector, ứng dụng phải gửi đủ spans cần thiết; spans đã bị head sampler loại không thể được tail sampler khôi phục.

## 12. Cấu hình datasource và tên database

Spring Boot cấu hình DataSource qua properties hoặc bean. Ví dụ:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://postgres:5432/orders
    username: DB_USERNAME_FROM_SECRET
    password: DB_PASSWORD_FROM_SECRET
    hikari:
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 3s
~~~

Không log URL/username/password nguyên bản. Connection string có thể chứa host, database name và credentials. Nếu database name được gắn vào telemetry, kiểm tra policy và cardinality.

Nếu ứng dụng có nhiều DataSources, đặt tên/qualifier rõ ràng, kiểm tra mỗi pool có metrics riêng, xác minh spans chỉ rõ datasource/database phù hợp nếu instrumentation hỗ trợ, và tránh gắn tenant database name động làm metric tag.

## 13. Kiểm tra database spans và metrics

Thực hiện request có thao tác JDBC rồi tìm trace theo service name. Kiểm tra HTTP/server span, database/JDBC spans bên dưới, parent-child relationship, duration/operation, error status/exception type và SQL literals/credentials/PII.

Actuator:

~~~http
GET /actuator/metrics
GET /actuator/metrics/http.server.requests
GET /actuator/metrics/jdbc.connections.active
~~~

Tên metric pool có thể khác. Chỉ expose endpoint cần thiết và bảo vệ bằng Spring Security/network policy.

Trace backend trả lời "request này đã thực hiện thao tác nào và mất bao lâu ở application boundary?". Database monitoring trả lời "database engine đang chịu tải, lock hoặc replication lag ra sao?". Đối chiếu query latency với DB CPU, lock waits, slow query logs và connection pool metrics.

## 14. Kiểm thử JDBC observation

Integration test nên dùng database test thật hoặc Testcontainers khi cần xác minh JDBC path, DataSource instrumentation và spans. H2 phù hợp test đơn giản nhưng khác driver/SQL semantics so với production database.

Các ca kiểm thử:
1. Query thành công tạo database span.
2. SQL exception được ghi nhận với error status/type phù hợp.
3. Nhiều statements tạo số spans mong đợi.
4. Span được gắn vào trace hiện tại.
5. DataSource pool metrics được đăng ký.
6. SQL attributes không chứa test canary PII/secret.
7. Transaction commit/rollback không làm mất context.
8. Instrumentation không tạo duplicate spans khi có agent.

Có thể dùng in-memory exporter/test exporter tương thích tracer version để kiểm tra spans mà không cần backend thật. Integration test end-to-end có thể dùng Collector/backend test để xác minh export. Không assert chính xác tên mọi span attributes nếu convention thay đổi giữa versions; kiểm tra contract quan trọng như có span, trace relationship, operation và không rò dữ liệu.

## 15. Những trường hợp không được JDBC instrumentation bao phủ

JDBC observation starter không phải universal database instrumentation:
- R2DBC dùng reactive protocol và cần instrumentation riêng.
- MongoDB, Redis, Elasticsearch có client instrumentation riêng.
- Native driver APIs có thể không đi qua JDBC.
- Một số ORM/cache operations không tạo JDBC call nên không có JDBC span.
- Stored procedure/batch operations có thể được thể hiện khác theo driver.
- Async database calls có thể cần context propagation riêng.

Nếu backend không có database span, xác định API thực tế mà ứng dụng dùng trước khi thêm JDBC dependency. Không instrument DataSource không nằm trên đường truy cập database thực.

## 16. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| HTTP spans có nhưng không có JDBC spans | JDBC instrumentation thiếu/tắt hoặc query đi qua client khác. | Kiểm tra DataSource path, starter/agent và tracer setup. |
| JDBC spans không nằm trong HTTP trace | Context propagation mất hoặc instrumentation tạo SDK riêng. | Kiểm tra ObservationRegistry, current span và DataSource instrumentation. |
| Có spans trùng | OTel agent và Micrometer/JDBC instrumentation cùng instrument. | Kiểm tra dependency/agent extensions và tắt một lớp trùng. |
| Pool active cao, query spans ngắn | Connection bị giữ trong application/transaction hoặc leak. | Kiểm tra transaction lifecycle và pool usage. |
| Query spans dài, pool không cạn | DB execution, lock, network hoặc driver delay. | Đối chiếu slow query logs, DB metrics và span timing. |
| Không có pool metrics | Pool binder/Actuator/registry không được cấu hình hoặc pool không hỗ trợ. | Kiểm tra meter list và DataSource implementation. |
| SQL text lộ literals | Instrumentation ghi statement raw hoặc exception chứa SQL. | Kiểm tra span payload, statement sanitizer và exporter processors. |
| Datasource name không rõ | Nhiều DataSources không được đặt tên/qualifier. | Đặt bean identity ổn định và kiểm tra attributes. |
| H2 test có spans nhưng production DB không | Driver/proxy/connection pool production khác. | Test bằng cùng database family và driver tương ứng. |
| Không thấy lỗi SQL trong trace | Exception bị catch/translate hoặc span status convention không đánh dấu. | Kiểm tra error recording và exception mapping. |

## 17. Runbook xác minh JDBC observability

1. Xác định database access dùng JDBC, R2DBC hay native client.
2. Kiểm tra Spring Boot version và dependencies/tracing bridge.
3. Kiểm tra DataSource bean và connection pool implementation.
4. Phát request thực hiện một câu SQL đơn giản.
5. Tìm trace và xác minh database span dưới HTTP/server span.
6. Kiểm tra operation, duration, datasource identity và error status.
7. Kiểm tra pool metrics active/idle/pending và giới hạn connections.
8. Thử SQL error và xác minh exception/error handling.
9. Rà soát statement attributes, connection strings, credentials và PII.
10. Kiểm tra sampling/exporter/Collector drops nếu spans không đến backend.
11. So sánh span timing với database slow query logs và server metrics.
12. Ghi lại versions, driver, pool, instrumentation source và kết quả kiểm thử.

## 18. Bài tập tự kiểm tra

### Bài 1 — Phân biệt các tín hiệu

Một request có HTTP span và JDBC span. HikariCP cũng báo active connections cao. Ba dữ liệu này nói điều gì?

**Đáp án:** HTTP span mô tả request tổng thể; JDBC span mô tả database exchange; active connections mô tả pool usage. Đối chiếu duration và pending/idle metrics để xác định bottleneck.

### Bài 2 — Không có JDBC span

Ứng dụng dùng R2DBC nhưng đã thêm JDBC observation dependency. Vì sao không thấy database spans?

**Đáp án:** R2DBC không đi qua JDBC DataSource/driver path. Cần instrumentation phù hợp với R2DBC thay vì JDBC.

### Bài 3 — SQL cardinality

Có nên dùng full SQL text làm metric tag để lọc query chậm không?

**Đáp án:** Không. SQL literals và dynamic statements tạo cardinality lớn, có thể lộ dữ liệu. Dùng operation/query fingerprint ổn định hoặc trace attributes đã kiểm soát.

### Bài 4 — N+1 queries

Một request tạo 40 database spans ngắn. Điều gì cần kiểm tra?

**Đáp án:** N+1 queries, lazy loading, fetch strategy, ORM flush và repository loop. Trace waterfall cho thấy số lượng/quan hệ calls; database metrics bổ sung tải server.

### Bài 5 — Pool cạn

Pending threads tăng, active connections chạm max, JDBC spans có thời gian dài. Có nên chỉ tăng max pool size?

**Đáp án:** Không. Kiểm tra query/transaction duration, connection leak, DB capacity và số replicas. Tăng pool có thể làm database quá tải hơn.

### Bài 6 — SQL exception không hiện error

Ứng dụng catch SQLException và trả response lỗi nghiệp vụ. Trace span không có error status. Điều đó có nhất thiết là instrumentation hỏng?

**Đáp án:** Không. Exception đã được xử lý có thể không tự đánh dấu span error theo convention. Cần ghi nhận error có chủ đích trong observation/span context theo API/version phù hợp.

## 19. Checklist triển khai

- [ ] Xác nhận ứng dụng truy cập database qua JDBC.
- [ ] Spring Boot, Micrometer Tracing bridge và instrumentation versions tương thích.
- [ ] Chỉ có một tracer bridge và không có duplicate Java agent instrumentation.
- [ ] DataSource/connection pool được quản lý và instrument đúng.
- [ ] Database spans xuất hiện trong trace hiện tại.
- [ ] HTTP/server span và JDBC spans có quan hệ parent-child hợp lý.
- [ ] Operation, duration và error status được kiểm tra trên payload thực tế.
- [ ] Pool metrics active/idle/pending/max được theo dõi.
- [ ] SQL text, bind values, credentials và connection strings được bảo vệ.
- [ ] Không dùng full SQL hoặc tenant IDs làm metric tags.
- [ ] Sampling được chọn theo volume/cost và yêu cầu điều tra.
- [ ] Có dashboard đối chiếu traces, pool metrics và database server metrics.
- [ ] Integration tests dùng database/driver phù hợp.
- [ ] Có test cho success, SQL exception, transaction và context propagation.
- [ ] R2DBC/native clients được nhận diện và dùng instrumentation riêng.
- [ ] Runbook có bước kiểm tra exporter, Collector và backend drops.

**Ghi nhớ:** JDBC observation starter giúp quan sát database calls đi qua JDBC, nhưng không thay thế metrics của connection pool hay monitoring bên trong database. Hãy chọn dependency theo Spring Boot/tracer version, dùng một tracing pipeline nhất quán, kiểm tra database spans nằm trong HTTP trace, và bảo vệ SQL attributes khỏi literals/PII. Kết hợp spans, pool metrics và database server metrics để phân biệt query chậm, chờ connection và database overload.
