# Tích hợp Micrometer và công cụ quan sát tương thích phiên bản

Một ứng dụng Spring Data Relational R2DBC cần được quan sát ở nhiều lớp: HTTP request, nghiệp vụ, repository/query, connection pool, JVM và database. Micrometer cung cấp API thống nhất để ghi metrics và observations; Spring Boot Actuator tự cấu hình nhiều thành phần quan sát; các registry và tracing bridge đưa dữ liệu tới Prometheus, OpenTelemetry hoặc hệ thống giám sát khác.

Tuy nhiên, khả năng quan sát phụ thuộc phiên bản Spring Boot, Spring Framework, Spring Data Relational, Micrometer, R2DBC SPI và driver. Có metrics HTTP không có nghĩa SQL đã được instrument; có connection pool không có nghĩa mọi query đều có span; thêm một dependency Micrometer mới không bảo đảm tích hợp tương thích với BOM đang dùng.

Bài học này giải thích cách chọn và căn chỉnh phiên bản, phân biệt metrics với observations/traces/logs, bật Actuator, quan sát R2DBC pool và repository, tạo metrics/observations nghiệp vụ, xuất dữ liệu sang Prometheus hoặc OpenTelemetry, bảo vệ dữ liệu nhạy cảm và kiểm chứng instrumentation trên đúng driver/database.

## 1. Observability là gì?

Observability (khả năng quan sát) là khả năng suy luận trạng thái bên trong hệ thống từ dữ liệu mà hệ thống phát ra. Với một API reactive dùng R2DBC, ta cần trả lời được những câu hỏi như:

- Request nào đang chậm?
- Thời gian bị tiêu tốn ở HTTP, service, query hay chờ connection?
- Connection pool có bị cạn hoặc có nhiều request đang chờ không?
- Query lỗi do constraint, timeout hay mất kết nối?
- Một request đi qua những service nào?
- Tỷ lệ lỗi và độ trễ thay đổi sau khi deploy ra sao?
- Database hoặc JVM có đang quá tải không?

Ba loại dữ liệu nền tảng:

| Loại dữ liệu | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Metrics | Tình trạng tổng thể thay đổi thế nào theo thời gian? | Request rate, p95 latency, pool pending |
| Traces | Một request cụ thể đi qua những bước nào? | HTTP span, service span, database span |
| Logs | Sự kiện hoặc lỗi cụ thể đã xảy ra với ngữ cảnh gì? | Constraint violation, timeout, retry |

Ba loại dữ liệu bổ trợ nhau. Metric cho thấy tỷ lệ lỗi tăng; trace giúp tìm request và đoạn xử lý chậm; log chứa chi tiết exception và mã lỗi để chẩn đoán.

~~~text
Client request
     |
     v
HTTP server observation / metric
     |
     v
Business operation observation
     |
     v
Repository / SQL instrumentation (nếu được hỗ trợ)
     |
     v
R2DBC connection pool metrics
     |
     v
Database
     |
     +---- metrics ----> MeterRegistry ----> Prometheus
     |
     +---- traces -----> Micrometer Tracing -> OTLP backend
     |
     +---- logs -------> Logging system (trace/span correlation)
~~~

Không phải mọi lớp đều được instrument tự động. Cần xác định dữ liệu nào được Spring Boot tạo sẵn, dữ liệu nào đến từ Spring Data/driver và dữ liệu nào ứng dụng phải bổ sung.

## 2. Micrometer gồm những thành phần nào?

Micrometer là facade quan sát cho Java. Nó cung cấp API để ứng dụng ghi dữ liệu mà không phải phụ thuộc trực tiếp vào một backend metrics cụ thể.

Các thành phần thường gặp:

- **MeterRegistry:** nơi đăng ký và quản lý meter như Counter, Timer, Gauge và DistributionSummary.
- **ObservationRegistry:** nơi tạo và quản lý Observation; một observation có thể tạo metric và span tùy handler được cấu hình.
- **Micrometer Observation:** mô hình thống nhất cho một thao tác có thời gian bắt đầu/kết thúc, tên, context, key-value và lỗi.
- **Micrometer Tracing:** API tracing thống nhất, kết nối với bridge như Brave hoặc OpenTelemetry.
- **Registry/exporter:** chuyển meter tới Prometheus, OTLP, Graphite hoặc backend khác.
- **Context propagation:** hỗ trợ truyền ngữ cảnh qua các ranh giới thread/reactive khi tích hợp tương ứng được bật.

Metrics và Observation có quan hệ nhưng không phải cùng một khái niệm. Một Observation có thể được xử lý bởi nhiều handler, ví dụ handler tạo Timer và handler tạo span. Một Timer đơn lẻ không tự tạo distributed trace.

## 3. Căn chỉnh phiên bản Spring Boot, Spring Data và Micrometer

Khi tích hợp observability, hãy bắt đầu từ Spring Boot BOM đang dùng. BOM quản lý một tập phiên bản đã được kiểm thử cùng nhau, gồm Spring Framework, Spring Data, Micrometer và nhiều dependency liên quan.

Không tự nâng riêng Micrometer hoặc Spring Data chỉ để lấy một API mới mà không kiểm tra compatibility. Việc trộn các generation có thể dẫn đến lỗi `NoSuchMethodError`, `ClassNotFoundException`, bean không được auto-configure hoặc instrumentation không hoạt động.

### 3.1. Các generation cần phân biệt

| Generation tổng quát | Đặc điểm quan sát | Cách tiếp cận |
|---|---|---|
| Spring Boot 2.x / Spring Framework 5.x | Actuator và Micrometer metrics là nền tảng phổ biến; Observation API không được tích hợp đồng bộ như Boot 3 | Dùng dependency/version do Boot BOM quản lý; kiểm tra tính năng tracing theo stack đang dùng |
| Spring Boot 3.x / Spring Framework 6.x | Micrometer Observation trở thành nền tảng quan sát thống nhất; có tích hợp Micrometer Tracing | Dùng Actuator, registry và bridge tương thích với BOM |
| Spring Boot/Spring Framework generation mới hơn | Có thể thay đổi API, auto-configuration, registry và exporter | Dùng tài liệu đúng release train; không áp dụng cấu hình từ ví dụ cũ một cách máy móc |

Bảng này mô tả ranh giới generation, không phải ma trận tương thích đầy đủ cho mọi patch release. Spring Boot 3.x cũng có nhiều minor release và các khả năng được bổ sung dần. Ví dụ, một tính năng quan sát repository hoặc client có thể yêu cầu Spring Data/Spring Framework mới hơn mức tối thiểu của Boot 3.0.

Trước khi thêm code, ghi lại:

1. Spring Boot version.
2. Spring Framework version được BOM chọn.
3. Spring Data Relational version.
4. R2DBC SPI và driver version.
5. Micrometer Core/Observation/Tracing version.
6. Registry hoặc exporter version.
7. Java version.

Kiểm tra dependency tree để phát hiện một thư viện kéo vào Micrometer version khác. Nếu dùng Gradle, có thể xem dependency insight cho `micrometer-core`, `micrometer-observation` và registry. Nếu dùng Maven, xem dependency tree và effective POM.

### 3.2. Đừng trộn API metrics cũ với Observation mới tùy tiện

Trong stack cũ, ứng dụng có thể dùng `MeterRegistry`, `Timer`, `Counter` và một tracing integration riêng. Khi chuyển sang Observation, không cần xóa toàn bộ metrics custom ngay lập tức. Có thể giữ metrics có ý nghĩa và thêm Observation cho các ranh giới nghiệp vụ quan trọng.

Tuy nhiên, tránh ghi cùng một thao tác hai lần bằng nhiều aspect hoặc filter khác nhau, tạo metric trùng và đếm sai. Kiểm tra tên meter và span thực tế sau khi bật instrumentation.

### 3.3. Không pin Micrometer độc lập nếu Spring Boot quản lý

Ví dụ Gradle tối thiểu cho ứng dụng dùng Spring Boot dependency management:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")

    // Registry chỉ thêm khi backend yêu cầu.
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
~~~

Không khai báo version riêng nếu Spring Boot BOM đã quản lý artifact đó. Nếu cần một Micrometer feature chỉ có ở release mới, kiểm tra compatibility matrix và cân nhắc nâng Spring Boot đồng bộ.

## 4. Bật Spring Boot Actuator

Actuator cung cấp endpoint và auto-configuration cho health, metrics, info và một số chức năng quản trị/quan sát.

Dependency:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
}
~~~

Cấu hình ví dụ:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus

  endpoint:
    health:
      show-details: when_authorized

  metrics:
    tags:
      application: order-service
~~~

`prometheus` chỉ khả dụng khi có Prometheus registry phù hợp trên classpath. Nếu không thêm registry, endpoint này có thể không được tạo.

Không expose tất cả Actuator endpoint ra Internet. Những endpoint như `env`, `configprops`, `beans`, `heapdump` hoặc `loggers` có thể tiết lộ thông tin cấu hình và trạng thái nội bộ. Chỉ expose những endpoint thực sự cần và giới hạn bằng network policy, authentication, authorization hoặc management port riêng.

### 4.1. Health khác metrics

Health trả lời thành phần có đang sẵn sàng hay không. Metrics đo xu hướng và tải. Một database health check thành công không có nghĩa query latency đang tốt; một endpoint metrics đang hoạt động không chứng minh database sẵn sàng.

Các trạng thái thường được quan tâm:

- **Liveness:** process còn sống và có thể tiếp tục chạy không?
- **Readiness:** instance có sẵn sàng nhận traffic không?
- **Dependency health:** database hoặc hệ thống phụ thuộc có truy cập được không?

Không gắn mọi lỗi dependency vào liveness theo cách khiến orchestrator liên tục restart instance khi database tạm thời mất kết nối. Readiness thường phù hợp hơn để ngừng nhận traffic trong thời gian dependency không sẵn sàng, tùy kiến trúc.

## 5. Những metrics cơ bản của Spring Boot

Khi Actuator và Micrometer được cấu hình, Spring Boot thường cung cấp metrics cho HTTP server, JVM, process, system và các thành phần được hỗ trợ.

| Nhóm | Ví dụ tên meter thường gặp | Ý nghĩa |
|---|---|---|
| HTTP server | `http.server.requests` | Số request, thời gian và kết quả |
| JVM memory | `jvm.memory.used`, `jvm.memory.max` | Bộ nhớ heap/non-heap |
| JVM threads | `jvm.threads.live` | Số thread đang sống |
| Garbage collection | `jvm.gc.*` | Hoạt động GC |
| Process | `process.cpu.usage`, `process.uptime` | CPU và thời gian chạy process |
| System | `system.cpu.usage`, `system.load.average.1m` | Tải hệ điều hành |
| Logback | `logback.events` | Số log theo level nếu binder được bật |
| Repository | Meter/observation theo khả năng Spring Data version | Thời gian gọi repository và kết quả nếu có instrumentation |

Tên meter và tag có thể khác theo Spring Boot/Micrometer generation, registry và cấu hình. Hãy truy vấn endpoint `actuator/metrics` hoặc xem registry thực tế thay vì hardcode dashboard theo một tên chưa được xác nhận.

### 5.1. HTTP server metrics

`http.server.requests` thường cho biết:

- Số request theo route/method/status.
- Thời gian xử lý.
- Phân bố latency.
- Kết quả lỗi/thành công.

Dùng route template như `/api/orders/{id}` thay vì URI thực tế chứa ID. Nếu tag URI chứa từng giá trị ID, metric cardinality có thể tăng theo số request.

### 5.2. Histogram và percentile

Timer có thể cung cấp count, total time và max; histogram/percentile cần cấu hình phù hợp với registry và workload.

Ví dụ cấu hình phân bố cho HTTP request:

~~~yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
      slo:
        http.server.requests: 100ms,300ms,1s,3s
~~~

Tên thuộc tính và cú pháp SLO cần xác nhận theo Micrometer/Spring Boot version. Histogram tạo thêm time series; chỉ bật cho meter cần theo dõi và cân nhắc chi phí lưu trữ.

Không dùng average latency làm chỉ số duy nhất. Một số request rất chậm có thể bị che khuất bởi số lượng request nhanh. Theo dõi p50/p95/p99 hoặc histogram bucket phù hợp.

## 6. Quan sát connection pool R2DBC

R2DBC thường dùng connection pool để tái sử dụng connection. Khi pool hoạt động, cần biết:

- Bao nhiêu connection đang được cấp cho caller?
- Bao nhiêu connection đang mở/tổng số?
- Bao nhiêu connection đang idle?
- Có bao nhiêu request đang chờ acquire?
- Thời gian chờ acquire có tăng không?
- Có connection bị timeout hoặc validation failure không?

Với `r2dbc-pool`, Spring Boot/Micrometer có thể cung cấp pool metrics tùy phiên bản và cách `ConnectionFactory` được cấu hình.

Các meter thường được gặp trong tích hợp pool có thể gồm:

| Nhóm meter | Ý nghĩa |
|---|---|
| `r2dbc.pool.acquired` | Connection đang được acquire/đang sử dụng |
| `r2dbc.pool.allocated` | Connection đã được cấp phát |
| `r2dbc.pool.idle` | Connection đang nhàn rỗi |
| `r2dbc.pool.pending` | Số yêu cầu đang chờ connection |

Tên cụ thể, đơn vị, tag và việc tự động đăng ký phụ thuộc phiên bản `r2dbc-pool`, Spring Boot và Micrometer. Xác nhận bằng `/actuator/metrics` hoặc registry scrape.

Ví dụ cấu hình pool:

~~~yaml
spring:
  r2dbc:
    pool:
      enabled: true
      initial-size: 5
      max-size: 20
      max-acquire-time: 2s
      max-create-connection-time: 3s
      max-idle-time: 30m
~~~

Các thuộc tính trên là ví dụ; chỉ dùng khi driver và cấu hình Spring Boot có hỗ trợ pool. Không copy giới hạn connection mà không so sánh với giới hạn session của database và số replica ứng dụng.

### 6.1. Diễn giải pool metrics

Một vài tín hiệu thường gặp:

- `pending` tăng liên tục: request phải chờ connection; pool có thể quá nhỏ, query/transaction quá lâu hoặc database không đáp ứng.
- `acquired` gần `max-size` trong thời gian dài: connection pool thường xuyên bão hòa.
- `idle` gần 0 cùng pending tăng: cần kiểm tra thời gian giữ connection và workload.
- `allocated` tăng bất thường: connection creation hoặc validation có thể đang có vấn đề.
- Acquire timeout tăng: caller không lấy được connection trong thời hạn.

Không lập tức tăng `max-size`. Nếu database đã quá tải, thêm connection có thể làm lock contention, CPU và memory tệ hơn. Hãy kiểm tra query duration, transaction duration, database capacity và số replica trước.

### 6.2. Tính tổng connection khi scale out

Nếu mỗi instance có pool tối đa 20 connection và hệ thống chạy 8 replica, ứng dụng có thể yêu cầu tới 160 connection, chưa tính migration, job hoặc dịch vụ khác.

Công thức ước lượng:

\[
\text{Tổng connection tối đa}
=
\text{pool max-size mỗi instance}
\times
\text{số instance}
+
\text{connection ngoài ứng dụng}
\]

Đặt ngân sách theo giới hạn database. Pool size là quyết định toàn hệ thống, không chỉ là một con số trong file YAML.

## 7. Metrics và observations ở tầng repository/R2DBC

Cần phân biệt ít nhất ba ranh giới instrumentation:

1. **Repository invocation:** thời gian gọi method repository và kết quả của lời gọi.
2. **Database client/query:** thời gian thực thi statement, loại operation và thông tin query được phép ghi nhận.
3. **Connection pool:** thời gian chờ và trạng thái tài nguyên connection.

Một phiên bản Spring Data có thể cung cấp repository observation nhưng không tự động tạo span chi tiết cho mọi SQL statement. Spring Framework `DatabaseClient` có thể có instrumentation riêng tùy release và cấu hình `ObservationRegistry`. Raw R2DBC SPI hoặc driver-specific call có thể không đi qua các abstraction đó.

Do đó, không suy luận rằng có metric repository là đã có query trace, hoặc có HTTP trace là database span đã được tạo.

### 7.1. Repository instrumentation phụ thuộc Spring Data version

Spring Data Commons/Relational đã bổ sung observability qua các release khác nhau. Hãy kiểm tra tài liệu đúng phiên bản để xác định:

- Repository method có tạo Observation không?
- Observation có được bật mặc định hay cần registry/configuration?
- Có thể tùy chỉnh observation convention không?
- Tag nào được tạo: repository, method, outcome, exception?
- Reactive repository được đo theo thời gian subscription hay chỉ thời gian method trả publisher?
- Có hỗ trợ tracing span hay chỉ meter?

Điểm đặc biệt với reactive repository là method thường trả `Mono`/`Flux` trước khi query thực sự chạy. Instrumentation đúng cần đo lifecycle publisher khi subscribe tới complete/error/cancel. Một timer chỉ đo thời gian method tạo publisher sẽ không phản ánh database latency.

### 7.2. DatabaseClient và SQL observations

Nếu phiên bản Spring Framework/Spring Data đang dùng hỗ trợ Observation cho `DatabaseClient`, xác nhận `ObservationRegistry` được gắn vào builder/auto-configuration mà ứng dụng thực sự sử dụng.

Nếu tự tạo `DatabaseClient` riêng, đừng giả định nó tự kế thừa registry từ bean khác. Dùng cấu hình builder hoặc bean do Spring Boot quản lý theo tài liệu phiên bản.

SQL statement và bind value có thể chứa thông tin nhạy cảm. Tránh thêm toàn bộ SQL động, email, token hoặc tham số người dùng thành metric tag hoặc span attribute. Nếu cần query identity, dùng tên operation ổn định hoặc query category đã được chuẩn hóa.

### 7.3. Raw R2DBC driver và instrumentation

Nếu ứng dụng gọi trực tiếp `ConnectionFactory`, `Connection`, `Statement` hoặc dùng wrapper/proxy riêng, instrumentation của repository/DatabaseClient có thể bị bỏ qua.

Có thể cần driver-specific metrics, R2DBC proxy listener hoặc Observation tùy chỉnh. Kiểm tra thứ tự wrapper: pool, proxy, transaction-aware connection factory và Spring Data phải được ghép đúng để không làm mất transaction context hoặc metrics.

Không bọc `ConnectionFactory` tùy tiện rồi kỳ vọng transaction manager, dialect resolver và pool binder đều nhận diện wrapper như driver gốc. Chạy integration test sau khi thay đổi wrapper.

## 8. Thêm metrics nghiệp vụ bằng MeterRegistry

Metrics kỹ thuật cho biết HTTP và database đang hoạt động ra sao; metrics nghiệp vụ cho biết ứng dụng đang xử lý bao nhiêu đơn hàng, thanh toán hoặc reservation.

Ví dụ tăng Counter sau khi tạo đơn thành công:

~~~java
@Service
public class OrderService {

    private final OrderRepository repository;
    private final Counter createdOrders;

    public OrderService(
            OrderRepository repository,
            MeterRegistry meterRegistry) {
        this.repository = repository;
        this.createdOrders = meterRegistry.counter("orders.created");
    }

    public Mono<Order> create(Order order) {
        return repository.save(order)
                .doOnSuccess(saved -> {
                    if (saved != null) {
                        createdOrders.increment();
                    }
                });
    }
}
~~~

`doOnSuccess` của `Mono` cũng có thể nhận `null` khi publisher hoàn tất rỗng, vì vậy ví dụ kiểm tra `saved != null`. Nếu operation chỉ phát entity khi thành công, có thể dùng `doOnNext`.

Counter này chỉ tăng sau khi repository publisher phát thành công. Nếu transaction bên ngoài vẫn chưa commit, metric có thể tăng trước khi transaction commit cuối cùng. Nếu cần đo số đơn thực sự commit, đặt metric ở ranh giới sau transaction commit hoặc dùng event/outbox được phát sau commit.

### 8.1. Đo thời gian hoàn tất reactive publisher

Không đo thời gian bằng cách gọi `Timer.record()` quanh việc tạo `Mono`, vì query chưa chắc đã chạy tại thời điểm đó.

Có thể đo lifecycle publisher bằng `Timer.Sample` bên trong `Mono.defer`:

~~~java
public Mono<Order> create(Order order) {
    return Mono.defer(() -> {
        Timer.Sample sample = Timer.start(meterRegistry);

        return repository.save(order)
                .doFinally(signal -> {
                    String outcome = switch (signal) {
                        case ON_COMPLETE -> "success";
                        case ON_ERROR -> "error";
                        case CANCEL -> "cancelled";
                        default -> "other";
                    };

                    sample.stop(meterRegistry.timer(
                            "orders.create.duration",
                            "outcome",
                            outcome));
                });
    });
}
~~~

Ví dụ dùng switch expression của Java mới; với Java cũ hơn, dùng if/else hoặc helper method. Mỗi subscription tạo một sample riêng, và `doFinally` ghi nhận completion, error hoặc cancellation.

Nếu publisher nằm trong transaction do caller quản lý, thời gian trên chỉ đo đoạn repository trong method này. Nó không nhất thiết bao gồm commit transaction bên ngoài. Chọn đúng ranh giới muốn đo và đặt timer tại đó.

## 9. Tạo Observation cho thao tác nghiệp vụ

Observation phù hợp khi muốn một thao tác có thể tạo cả metric và trace tùy handler được cấu hình.

Ví dụ tạo observation quanh publisher:

~~~java
public Mono<Order> submit(SubmitOrderCommand command) {
    return Mono.defer(() -> {
        Observation observation = Observation.start(
                "orders.submit",
                observationRegistry);

        return orderService.submit(command)
                .doOnError(observation::error)
                .doFinally(signal -> observation.stop());
    });
}
~~~

Observation được tạo bên trong `Mono.defer`, nên mỗi subscription có vòng đời riêng. Nó được dừng khi publisher hoàn tất, phát lỗi hoặc bị hủy.

Đây là ví dụ đo ranh giới nghiệp vụ. Nếu cần truyền parent observation/span và baggage qua toàn bộ Reactor chain, dùng context propagation tích hợp với phiên bản Spring/Micrometer đang chạy; không chỉ tạo Observation rồi giả định mọi downstream operator tự nhận context. Kiểm tra tracing backend để xác nhận quan hệ parent-child thực tế.

### 9.1. Dùng @Observed hoặc @Timed khi phù hợp

Micrometer cung cấp annotation như `@Observed` và `@Timed` trong các generation tương ứng. Nhưng annotation không tự hoạt động trong mọi ứng dụng:

- `@Observed` thường cần `ObservedAspect` và AOP setup phù hợp nếu dùng cách proxy annotation.
- `@Timed` có thể cần `TimedAspect` hoặc auto-configuration tương ứng.
- Self-invocation có thể bỏ qua proxy.
- Với reactive method, cần xác nhận aspect đo tới terminal signal hay chỉ thời gian method trả publisher.
- Không áp dụng aspect đồng thời với filter/repository instrumentation khiến cùng operation bị đo lặp.

Đối với reactive publisher, instrumentation phải gắn với subscription lifecycle. Hãy xem tài liệu Micrometer/Spring Boot đúng phiên bản và test complete/error/cancel.

## 10. Export metrics sang Prometheus

Prometheus registry có thể expose metrics qua Actuator endpoint.

Dependency:

~~~kotlin
dependencies {
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
~~~

Cấu hình expose:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
~~~

Prometheus scrape endpoint thường là:

~~~text
/actuator/prometheus
~~~

Ví dụ cấu hình scrape ở Prometheus:

~~~yaml
scrape_configs:
  - job_name: order-service
    metrics_path: /actuator/prometheus
    static_configs:
      - targets:
          - order-service:8080
~~~

Trong môi trường thật, target và port phải theo network/service discovery của nền tảng triển khai. Bảo vệ endpoint bằng mạng nội bộ hoặc authentication; không mở metrics endpoint công khai nếu nó tiết lộ topology và thông tin vận hành.

### 10.1. Kiểm tra metrics qua Actuator

Các endpoint hữu ích:

- `/actuator/health`
- `/actuator/metrics`
- `/actuator/metrics/http.server.requests`
- `/actuator/metrics/jvm.memory.used`
- `/actuator/prometheus`

Tên meter cụ thể phụ thuộc instrumentation được bật. Nếu `/actuator/metrics` không liệt kê meter mong muốn, kiểm tra registry, binder, auto-configuration và profile thay vì giả định Prometheus sẽ tự tạo dữ liệu.

### 10.2. Tag application và environment

Tag cố định như `application`, `region`, `environment` có thể giúp lọc dashboard. Không thêm tag có số lượng giá trị gần như vô hạn.

Một bộ tag hợp lý có thể gồm:

- `application=order-service`
- `environment=staging`
- `region=ap-southeast-1`
- `operation=create-order`
- `outcome=success|error|cancelled`

Đảm bảo giá trị tag có tập hữu hạn và được kiểm soát.

## 11. Tracing với Micrometer Tracing và OpenTelemetry

Metrics cho biết một endpoint chậm; trace giúp thấy thời gian bị tiêu tốn ở từng bước của một request cụ thể.

Trong Spring Boot generation có hỗ trợ Micrometer Tracing, ứng dụng thường kết hợp:

- Micrometer Tracing API.
- Bridge tới Brave hoặc OpenTelemetry.
- Exporter gửi span tới backend.
- Context propagation qua Reactor.
- Instrumentation HTTP và các client được hỗ trợ.

Ví dụ dependency theo hướng OpenTelemetry trong một stack Boot có quản lý tương ứng:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("io.micrometer:micrometer-tracing-bridge-otel")
    runtimeOnly("io.opentelemetry:opentelemetry-exporter-otlp")
}
~~~

Artifact và version cần được xác nhận theo Spring Boot BOM và tracing generation. Không trộn bridge Brave với bridge OpenTelemetry trong cùng một cấu hình nếu không có thiết kế cụ thể.

### 11.1. Một trace có thể gồm nhiều span

~~~text
Trace: POST /api/orders
 |
 +-- HTTP server span
      |
      +-- order.submit
      |     |
      |     +-- validate order
      |     |
      |     +-- repository.save
      |            |
      |            +-- database query span (nếu được instrument)
      |
      +-- HTTP response
~~~

Không phải mọi node đều tự xuất hiện. Nếu driver/DatabaseClient/repository không có instrumentation, trace có thể chỉ chứa HTTP span hoặc business span. Dùng backend tracing để xác nhận span thực tế, không dựa vào sơ đồ mong muốn.

### 11.2. Sampling

Tracing toàn bộ request có thể tạo chi phí CPU, network và storage đáng kể. Sampling chọn một phần trace để gửi đi.

- Sampling ratio thấp hơn giảm chi phí nhưng có thể bỏ sót lỗi hiếm.
- Tail-based sampling có thể giữ trace lỗi hoặc chậm sau khi biết kết quả, nhưng cần collector hỗ trợ.
- Error/high-latency sampling cần được thiết kế theo backend và privacy policy.
- Không dùng sampling để thay thế metrics; metrics vẫn cần ghi nhận aggregate rate và latency.

Kiểm tra trace context có được truyền qua WebFlux, Reactor và các client downstream hay không. Một lần gọi `subscribe()` độc lập có thể làm đứt context và mất quan hệ trace.

## 12. Context propagation trong Reactor

Ứng dụng reactive có thể chuyển thread giữa các operator. Dựa vào ThreadLocal thuần túy để truyền trace ID hoặc request metadata có thể dẫn tới mất context.

Micrometer Context Propagation và các tích hợp Spring/Reactor giúp bridge giữa Reactor Context và ThreadLocal-based instrumentation. Cấu hình chính xác phụ thuộc Spring Boot, Micrometer Context Propagation và Reactor version.

Nguyên tắc:

- Dùng Spring/Micrometer integration được hỗ trợ trong BOM.
- Không tự copy trace ID vào ThreadLocal ở mỗi service method.
- Không gọi `subscribe()` tách rời trong service.
- Kiểm tra trace xuyên qua `publishOn`, `subscribeOn`, `flatMap` và HTTP client.
- Nếu dùng custom scheduler hoặc thư viện callback, xác nhận context được truyền qua ranh giới đó.
- Không đưa dữ liệu nhạy cảm vào baggage.

Trace ID giúp liên kết log/trace, nhưng không phải ID nghiệp vụ hoặc thông tin xác thực.

## 13. Liên kết logs với trace

Khi Micrometer Tracing và logging integration được cấu hình, log có thể mang trace ID và span ID để tìm trace tương ứng.

Ví dụ log:

~~~text
INFO  traceId=... spanId=... Order created
ERROR traceId=... spanId=... Database operation failed
~~~

Định dạng thực tế tùy logging framework và cấu hình. Không tự thêm một trace ID mới cho mỗi log; hãy dùng context propagation và correlation integration.

Log nên có:

- Operation hoặc route ổn định.
- Trace/correlation ID nếu có.
- Exception class và cause phù hợp.
- SQLState/vendor code nếu an toàn.
- Outcome và duration khi hữu ích.

Không log password, access token, connection URL có credential, bind values nhạy cảm hoặc toàn bộ payload request. Trace attribute và log field đều có thể được nhiều người hoặc hệ thống truy cập.

## 14. Cardinality và privacy

Một sai lầm phổ biến là thêm ID người dùng, order ID hoặc SQL đầy đủ vào metric tag. Mỗi giá trị mới có thể tạo một time series riêng, làm Prometheus tốn memory và backend trở nên khó truy vấn.

Ví dụ không nên:

~~~java
meterRegistry.counter(
        "orders.created",
        "orderId",
        order.getId().toString(),
        "email",
        customer.getEmail())
        .increment();
~~~

Nên dùng tag có tập giá trị hữu hạn:

~~~java
meterRegistry.counter(
        "orders.created",
        "channel",
        normalizedChannel,
        "outcome",
        "success")
        .increment();
~~~

Quy tắc:

- **Low-cardinality key:** operation, status, method, outcome, region cố định.
- **High-cardinality data:** order ID, user ID, trace ID, request ID.
- High-cardinality data có thể phù hợp trong trace/log khi được kiểm soát, nhưng không tự động an toàn.
- Không đưa email, phone, token, SQL parameter hoặc PII vào metric tag.
- Không đưa raw SQL hoặc query parameter vào span nếu chưa có chính sách bảo vệ.
- Giới hạn số giá trị của exception/message tag; không dùng error message động làm tag.

Observation API phân biệt low-cardinality và high-cardinality key-value để giúp backend xử lý đúng loại dữ liệu. Không khai báo ID duy nhất như low-cardinality tag.

## 15. Theo dõi lỗi R2DBC và retry

Metrics/observations cần giúp phân biệt các nhóm lỗi:

- Vi phạm constraint.
- SQL grammar hoặc API usage.
- Connection acquisition failure.
- Query timeout.
- Lock/optimistic locking conflict.
- Serialization failure.
- Driver/network failure.
- Cancellation.

Không dùng exception message làm metric tag vì nội dung có thể chứa dữ liệu động và tạo cardinality cao. Có thể dùng exception class hoặc một nhóm lỗi đã chuẩn hóa.

Nếu có retry, đo riêng:

- Số lần retry.
- Số retry thành công.
- Số lần retry hết giới hạn.
- Nhóm nguyên nhân retry.
- Tổng thời gian của operation bao gồm backoff.

Đặt tên metric rõ ràng, ví dụ `database.operation.retry` với tag `operation` và `reason` thuộc tập giá trị hữu hạn. Không ghi một counter mỗi lần retry bằng tag SQLState tùy ý nếu mã đó có thể có quá nhiều giá trị.

Retry toàn transaction có thể làm một request có nhiều lần thực thi SQL. Trace nên giúp nhận diện lần thử và operation tổng thể; tránh tạo quá nhiều span hoặc log lặp không cần thiết.

## 16. Health indicator và trạng thái database

Actuator có thể cung cấp health contributor cho R2DBC khi auto-configuration và connection factory được hỗ trợ.

Health check thường kiểm tra khả năng truy cập database hoặc connection. Nó không thay thế:

- Query latency metrics.
- Pool saturation metrics.
- Replication lag.
- Lock wait metrics.
- Disk/storage capacity.
- Database-specific monitoring.

Có thể xem `/actuator/health` trong môi trường được bảo vệ. Chi tiết component nên chỉ hiển thị cho người được ủy quyền. Không công khai hostname, schema, connection URL hoặc exception nội bộ.

Nếu ứng dụng dùng nhiều `ConnectionFactory`, kiểm tra mỗi health contributor có được đặt tên và phân loại đúng. Một database phụ không sẵn sàng có thể không nên làm toàn bộ ứng dụng unready nếu use case chính vẫn hoạt động; quyết định này thuộc health policy của ứng dụng.

## 17. Cấu hình ObservedAspect và TimedAspect

Nếu muốn dùng annotation, cần cấu hình aspect phù hợp.

Ví dụ tạo `ObservedAspect` trong stack có Micrometer Observation:

~~~java
@Configuration
public class ObservationConfiguration {

    @Bean
    ObservedAspect observedAspect(ObservationRegistry registry) {
        return new ObservedAspect(registry);
    }
}
~~~

Tương tự, `TimedAspect` có thể được đăng ký khi dùng `@Timed`:

~~~java
@Bean
TimedAspect timedAspect(MeterRegistry registry) {
    return new TimedAspect(registry);
}
~~~

Các class và package phải có trong dependency/version đang dùng. Một số Spring Boot generation hoặc starter có thể auto-configure một phần; tránh đăng ký bean trùng. Kiểm tra condition report hoặc application context trước khi tự tạo bean.

Ví dụ annotation:

~~~java
@Observed(name = "orders.submit")
public Mono<Order> submit(SubmitOrderCommand command) {
    return orderRepository.save(map(command));
}
~~~

Với reactive return type, kiểm tra aspect có theo dõi publisher đến khi terminal signal hay không. Nếu aspect chỉ đo thời gian method tạo publisher, metric sẽ quá nhỏ và không phản ánh thời gian database. Nếu không chắc, dùng instrumentation reactive rõ ràng như `Mono.defer` kết hợp `doFinally`, hoặc cơ chế observation reactive được Spring hỗ trợ trong release cụ thể.

## 18. Tạo custom ObservationConvention

Khi instrumentation framework cung cấp observation nhưng tag mặc định chưa đủ, có thể dùng convention tùy chỉnh nếu extension point của thành phần đó hỗ trợ.

Convention nên thêm thuộc tính ổn định, có ý nghĩa vận hành:

- Tên repository/operation.
- Loại command như SELECT/INSERT/UPDATE.
- Outcome success/error.
- Loại entity ở mức không nhạy cảm.
- Database system cố định.

Không thêm:

- Entity ID.
- Email/username.
- Raw SQL chứa giá trị.
- Bind parameter.
- Token.
- Request body.

Trước khi viết convention, kiểm tra API của đúng thành phần và phiên bản. `ObservationConvention` của HTTP, repository và database client có context type khác nhau; không thể dùng một convention bất kỳ cho mọi observation.

## 19. Dashboard và cảnh báo

Một dashboard R2DBC có thể kết hợp các nhóm:

| Nhóm | Chỉ số cần theo dõi |
|---|---|
| HTTP | Request rate, 4xx/5xx, p95/p99 latency |
| Service | Duration và outcome của nghiệp vụ chính |
| Repository/database | Query/operation duration, error rate nếu được instrument |
| Pool | Acquired, allocated, idle, pending, acquire timeout |
| JVM | Heap, GC pause, thread count |
| Process | CPU, uptime |
| Database | Active session, lock wait, slow query, connection limit |
| Tracing | Trace lỗi, trace chậm, downstream dependency |

Một vài cảnh báo có ý nghĩa:

- HTTP 5xx tăng vượt ngưỡng trong một khoảng thời gian.
- p95/p99 latency tăng liên tục.
- Pool pending tăng và acquire timeout xuất hiện.
- Database connection gần giới hạn.
- Query timeout hoặc lock conflict tăng đột biến.
- JVM heap gần giới hạn hoặc GC pause kéo dài.
- Tỷ lệ retry tăng mạnh.

Dùng cửa sổ thời gian và điều kiện kéo dài để tránh alert theo một spike ngắn. Alert cần có runbook chỉ rõ bước kiểm tra tiếp theo.

## 20. Tối ưu chi phí metrics và tracing

Observability có chi phí:

- Meter và time series.
- Histogram bucket.
- Span volume.
- Export network traffic.
- Storage/retention.
- CPU và allocation khi instrument.
- Log volume.

Một số cách kiểm soát:

1. Chỉ bật histogram cho metric cần percentile/SLO.
2. Giới hạn tag cardinality.
3. Sampling trace theo traffic và yêu cầu chẩn đoán.
4. Không ghi SQL/bind values mặc định.
5. Giảm log trùng ở nhiều tầng.
6. Dùng tên meter/observation ổn định.
7. Kiểm tra số time series trước khi rollout.
8. Theo dõi lỗi exporter để observability backend không làm ảnh hưởng request path.

Không để exporter hoặc collector chậm làm chặn reactive event loop. Dùng registry/exporter chính thức và cấu hình phù hợp.

## 21. Kiểm tra instrumentation bằng integration test

Test không chỉ cần xác nhận API trả 200. Có thể kiểm tra rằng metrics/observations được phát khi thực hiện một operation.

Với Micrometer, `SimpleMeterRegistry` phù hợp cho unit test metrics custom:

~~~java
@Test
void incrementsCreatedOrderCounter() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    OrderMetrics metrics = new OrderMetrics(registry);

    metrics.orderCreated();

    assertThat(registry.get("orders.created").counter().count())
            .isEqualTo(1.0);
}
~~~

Với Observation, dùng registry/test handler phù hợp phiên bản Micrometer để ghi nhận observation bắt đầu, kết thúc và error. Không chỉ assert method được gọi; xác nhận observation có đúng name và outcome.

### 21.1. Kiểm tra reactive lifecycle

Test cần cover:

- Publisher hoàn tất thành công.
- Publisher phát lỗi.
- Subscriber hủy subscription.
- Publisher được subscribe nhiều lần.
- Retry tạo nhiều lần thực thi.
- Transaction commit/rollback ở đúng boundary.

Ví dụ `doFinally` phải chạy cho complete, error và cancel. Nếu sample được tạo ngoài `Mono.defer`, nhiều subscription có thể dùng chung một sample và cho duration sai.

### 21.2. Kiểm tra Actuator endpoint

Trong integration test, gọi `/actuator/metrics` hoặc `/actuator/prometheus` nếu endpoint được expose trong test profile.

Xác nhận:

- Endpoint có tồn tại khi registry được thêm.
- Meter dự kiến xuất hiện sau operation.
- Tag không chứa dữ liệu nhạy cảm.
- Histogram/bucket được bật đúng.
- Endpoint bị bảo vệ nếu yêu cầu authentication.
- Metrics được tạo sau khi publisher thực sự hoàn tất, không chỉ sau khi method được gọi.

Không assert toàn bộ text scrape vì format và order có thể thay đổi. Tập trung vào meter name, count, tag và contract cần thiết.

## 22. Kiểm tra version compatibility trong CI

Một thay đổi Spring Boot, Spring Data, Micrometer hoặc R2DBC driver có thể làm thay đổi instrumentation. Nên có kiểm tra trong pipeline:

1. Resolve dependency tree và kiểm tra version convergence.
2. Khởi động application context với profile test.
3. Xác nhận `MeterRegistry` và `ObservationRegistry` được tạo.
4. Xác nhận R2DBC `ConnectionFactory` và pool đúng bean.
5. Thực hiện repository operation thật trên database test.
6. Xác nhận pool metrics được đăng ký nếu pool đang dùng.
7. Xác nhận repository/DatabaseClient observation nếu release hỗ trợ.
8. Xác nhận trace context đi qua WebFlux/Reactor.
9. Gọi Actuator metrics/prometheus endpoint.
10. Kiểm tra metric tags không chứa ID hoặc PII.
11. So sánh meter/span name sau khi nâng version.
12. Chạy smoke/load test để đo overhead nếu instrumentation thay đổi.

Không kiểm tra bằng cách chỉ xác nhận compile thành công. Auto-configuration có thể bị điều kiện classpath/property chi phối và không tạo bean dù code compile.

## 23. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Pin Micrometer version ngoài Spring Boot BOM | Dependency không tương thích | Dùng BOM và kiểm tra dependency tree |
| Thêm Actuator nhưng không thêm registry | Không có Prometheus exporter | Thêm registry tương ứng |
| Expose mọi Actuator endpoint | Lộ cấu hình và trạng thái nội bộ | Chỉ expose endpoint cần thiết, bảo vệ access |
| Cho rằng HTTP metric đã bao gồm SQL | Không biết query nào chậm | Kiểm tra repository/client/driver instrumentation |
| Cho rằng mọi R2DBC driver có tracing | Trace thiếu database span | Kiểm tra driver và instrumentation cụ thể |
| Đo Mono bằng Timer quanh lời gọi method | Đo thời gian tạo publisher thay vì thực thi | Đặt Timer trong defer và dừng ở terminal signal |
| Tạo Timer.Sample dùng chung nhiều subscription | Duration sai hoặc race | Tạo sample theo subscription |
| Tăng pool max-size khi pending cao | Database có thể quá tải hơn | Kiểm tra query, transaction và tổng connection |
| Dùng ID/email làm metric tag | Cardinality tăng và rò rỉ dữ liệu | Dùng tag có tập giá trị hữu hạn |
| Ghi raw SQL/bind value vào trace | Lộ dữ liệu nhạy cảm | Dùng operation name và metadata đã chuẩn hóa |
| Bật histogram cho mọi meter | Tăng số time series | Chỉ bật cho SLO cần thiết |
| Dùng @Observed nhưng không có aspect | Annotation không tạo observation | Cấu hình aspect hoặc dùng API trực tiếp |
| Aspect đo method return thay vì publisher lifecycle | Latency reactive thấp giả tạo | Kiểm tra reactive support hoặc instrument publisher |
| Gọi subscribe() độc lập | Mất trace/context và lifecycle tách rời | Nối publisher trong cùng chain |
| Thêm nhiều instrumentation cho cùng thao tác | Metric/span bị đếm trùng | Chọn một ranh giới đo rõ ràng |
| Tin rằng SimpleMeterRegistry chứng minh exporter hoạt động | Test pass nhưng Prometheus không scrape được | Integration test registry và endpoint thật |
| Không kiểm tra version khi nâng Boot | Mất meter/span hoặc đổi tên | Chạy compatibility test trong CI |

## 24. Quy trình tích hợp Micrometer với R2DBC

Một trình tự triển khai thực tế:

1. Xác định Spring Boot, Spring Framework, Spring Data, R2DBC SPI và driver version.
2. Dùng Spring Boot BOM để chọn Micrometer và registry tương thích.
3. Thêm Actuator.
4. Thêm registry/exporter cần dùng, ví dụ Prometheus.
5. Expose các endpoint cần thiết và bảo vệ chúng.
6. Kiểm tra HTTP/JVM/system metrics.
7. Bật pool và xác nhận R2DBC pool metrics.
8. Kiểm tra repository/DatabaseClient observation có được hỗ trợ trong release không.
9. Thêm metrics/observations cho các thao tác nghiệp vụ quan trọng.
10. Cấu hình tracing bridge và exporter nếu cần distributed tracing.
11. Xác nhận Reactor context propagation và log correlation.
12. Kiểm soát tag cardinality, privacy, histogram và sampling.
13. Kiểm tra metric/span bằng integration test trên database thật.
14. Đưa dashboard và alert theo SLO vào vận hành.
15. Chạy lại compatibility test khi nâng Spring Boot, Spring Data, Micrometer hoặc driver.

## 25. Ghi nhớ

- Metrics, traces và logs trả lời các câu hỏi khác nhau và cần được kết hợp.
- Micrometer cung cấp API thống nhất; MeterRegistry quản lý meter và ObservationRegistry quản lý observation.
- Dùng Spring Boot BOM để căn chỉnh Spring Framework, Spring Data, Micrometer, registry và tracing bridge.
- Spring Boot 2.x và 3.x thuộc các generation observability khác nhau; kiểm tra đúng minor/patch release thay vì áp dụng cấu hình chung.
- Actuator cung cấp health/metrics endpoint; Prometheus cần registry tương ứng.
- HTTP metrics không đồng nghĩa SQL hoặc R2DBC query đã được instrument.
- R2DBC pool metrics giúp phát hiện pending acquire, pool saturation và connection pressure; tên meter phụ thuộc phiên bản.
- Reactive timing phải đo từ subscription tới complete/error/cancel, không chỉ thời gian tạo Mono/Flux.
- Repository observation, DatabaseClient observation và driver tracing là các lớp riêng, có thể có mức hỗ trợ khác nhau.
- Observation có thể tạo metrics và traces tùy handler; Timer đơn lẻ không tự tạo distributed span.
- Micrometer Tracing cần bridge/exporter tương thích và Reactor context propagation đúng.
- Dùng low-cardinality tag; không đưa user ID, order ID, email, token hoặc SQL parameter vào metrics.
- Histogram, tracing sampling và log volume cần được kiểm soát để giới hạn chi phí.
- Bảo vệ Actuator endpoint và không công khai chi tiết hạ tầng.
- Kiểm tra instrumentation trong CI bằng dependency tree, application context, database test, meter/observation và endpoint scrape.

