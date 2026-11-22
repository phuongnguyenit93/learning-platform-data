# Quan sát request bằng log, tracing và metrics trong Spring Data REST

> Phạm vi: ứng dụng Spring Data REST chạy trên Spring MVC, ví dụ cấu hình theo Spring Boot 3.5.x. Spring Boot 4.x và các bản Spring Data khác có thể đổi dependency hoặc chi tiết tag; luôn dùng BOM và tài liệu đúng phiên bản của dự án.

## 1. Ba tín hiệu cần nối với nhau

Observability gồm logging, metrics và distributed tracing. Mỗi loại trả lời một câu hỏi khác nhau:

- **Log** cho biết request hoặc thao tác đã làm gì, kèm thông tin chẩn đoán có thể đọc được.
- **Metric** cho biết hệ thống đang hoạt động ra sao theo thời gian: số request, latency, tỷ lệ lỗi, throughput và mức sử dụng tài nguyên.
- **Trace** nối các bước của cùng một request qua filter, Spring MVC, repository, service và các HTTP client hoặc message broker.

Với Spring Data REST, nên quan sát đồng thời HTTP request do REST exporter xử lý và lời gọi Spring Data repository phía dưới. Một request có thể thành công ở tầng HTTP nhưng chậm ở repository hoặc dịch vụ ngoài; chỉ một loại tín hiệu sẽ khó chỉ ra điểm nghẽn.

## 2. Bật Actuator, metrics và tracing

Với Spring Boot 3.5, thêm các dependency cần thiết. Spring Boot quản lý phiên bản qua dependency management; không tự pin Micrometer hoặc OpenTelemetry version nếu BOM đã quản lý.

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
    runtimeOnly("io.micrometer:micrometer-tracing-bridge-otel")
    runtimeOnly("io.opentelemetry:opentelemetry-exporter-otlp")
}
```

`spring-boot-starter-actuator` cung cấp auto-configuration cho Micrometer. `micrometer-registry-prometheus` xuất metrics theo định dạng Prometheus; tracing bridge và OTLP exporter nối Micrometer Observation với OpenTelemetry Collector hoặc backend nhận OTLP. Nếu dùng Brave/Zipkin, chọn đúng bridge và reporter theo tài liệu Spring Boot.

Ví dụ `application.yml` cho môi trường phát triển hoặc staging:

```yaml
spring:
  application:
    name: spring-data-rest-api

management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics,prometheus"
  tracing:
    sampling:
      probability: 1.0

logging:
  pattern:
    correlation: "[${spring.application.name:},%X{traceId:-},%X{spanId:-}] "
  include-application-name: false
```

Trong ví dụ này, sampling `1.0` gửi 100% trace để dễ kiểm tra. Spring Boot mặc định chỉ sample 10% request nhằm hạn chế tải cho trace backend; production nên chọn tỷ lệ phù hợp với lưu lượng, chi phí và chính sách lưu trữ. Chỉ expose endpoint cần thiết. Actuator mặc định chỉ expose `health` qua HTTP; bảo vệ `metrics` và `prometheus` bằng Spring Security, network policy hoặc firewall.

Kiểm tra sau khi chạy ứng dụng:

```bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/metrics/http.server.requests
curl -i http://localhost:8080/actuator/metrics/spring.data.repository.invocations
curl -i http://localhost:8080/actuator/prometheus
```

`/actuator/metrics` dùng tên meter của Micrometer; tên được chuẩn hóa khi export sang backend có thể khác, ví dụ Prometheus dùng dấu gạch dưới. `/actuator/prometheus` cần registry Prometheus và phải được expose.

## 3. Metrics có sẵn cho Spring Data REST

### 3.1. HTTP request metrics

Spring Boot tự instrument request đi qua Spring MVC bằng meter `http.server.requests`. Spring Data REST chạy trên Spring MVC nên request tới collection, item và association resource cũng đi qua lớp đo request này. Các dimension mặc định của server observation gồm method, URI template, status, outcome và thông tin exception/error tùy phiên bản Spring Framework.

Ví dụ các câu hỏi có thể trả lời từ metric này:

- Request `GET /people` có p95/p99 latency tăng không?
- Tỷ lệ `4xx` hoặc `5xx` của `POST /people` có tăng sau release không?
- Endpoint association nào có thời gian xử lý cao?
- Lưu lượng request thay đổi theo instance hoặc môi trường ra sao?

URI tag nên là route template như `/people/{id}` thay vì URL đã thay ID. Không tạo tag bằng raw URI, query string, email, username hoặc entity ID; mỗi giá trị mới có thể tạo thêm time series và làm backend metrics tăng cardinality.

### 3.2. Repository invocation metrics

Spring Boot 3.5 tự instrument lời gọi method của Spring Data repository bằng meter `spring.data.repository.invocations`. Các tag mặc định gồm:

| Tag | Ý nghĩa |
| --- | --- |
| `repository` | Tên đơn giản của repository interface |
| `method` | Method repository được gọi |
| `state` | `SUCCESS`, `ERROR`, `CANCELED` hoặc `RUNNING` |
| `exception` | Tên class exception nếu invocation lỗi |

Metric này giúp phân biệt request chậm do xử lý HTTP với request chậm do repository. Có thể gắn `@Timed` vào repository interface hoặc method khi cần điều chỉnh cách đo; nếu đã bật auto-time cho mọi repository thì không thêm instrumentation trùng lặp. Có thể tắt auto-time bằng `management.metrics.data.repository.autotime.enabled=false` nếu muốn chỉ đo những method được đánh dấu.

### 3.3. Xem và lọc metrics

Actuator metrics endpoint hỗ trợ lọc theo tag. Ví dụ xem request GET:

```bash
curl "http://localhost:8080/actuator/metrics/http.server.requests?tag=method:GET"
```

Prometheus scrape endpoint thường được cấu hình ở `/actuator/prometheus`. Dashboard nên theo dõi tối thiểu request rate, error rate, p95/p99 latency, repository invocation duration, JVM, connection pool và thread pool. Đặt alert trên SLO hoặc ngưỡng vận hành có ý nghĩa, không alert trên mọi biến động nhỏ.

## 4. Gắn trace ID vào log và nối trace qua service

Khi Micrometer Tracing được cấu hình, Spring Boot tự thêm correlation ID vào log. Mặc định correlation ID được tạo từ `traceId` và `spanId` trong MDC. Có thể tùy chỉnh bằng `logging.pattern.correlation`; ví dụ cấu hình ở phần 2 giữ cả tên ứng dụng, trace ID và span ID trong mỗi dòng log.

Khi gọi dịch vụ khác, tạo HTTP client từ builder do Spring Boot cung cấp để trace context được truyền tự động:

```java
@Configuration
public class HttpClientConfiguration {

    @Bean
    RestClient partnerRestClient(RestClient.Builder builder) {
        return builder
                .baseUrl("https://partner.example")
                .build();
    }
}
```

Không tự tạo `RestTemplate`, `RestClient` hoặc `WebClient` bằng constructor nếu muốn dùng auto-configured observation và trace propagation. Dùng `RestTemplateBuilder`, `RestClient.Builder` hoặc `WebClient.Builder` được inject từ Spring Boot.

Với thao tác nghiệp vụ dài hoặc cần đo riêng ngoài metric HTTP/repository, inject `ObservationRegistry` và tạo observation:

```java
@Component
public class OrderOperations {

    private final ObservationRegistry observationRegistry;
    private final OrderService orderService;

    public OrderOperations(ObservationRegistry observationRegistry, OrderService orderService) {
        this.observationRegistry = observationRegistry;
        this.orderService = orderService;
    }

    public void confirm(Long orderId) {
        Observation.createNotStarted("springdatarest.order.confirm", observationRegistry)
                .lowCardinalityKeyValue("operation", "confirm")
                .observe(() -> orderService.confirm(orderId));
    }
}
```

Observation có thể tạo cả timer metric và span khi registry được cấu hình. Chỉ đưa tag có tập giá trị hữu hạn vào `lowCardinalityKeyValue`, ví dụ `operation`, `result`, `region` hoặc `entityType`. Dữ liệu có nhiều giá trị như order ID chỉ nên là high-cardinality trace attribute khi thật sự cần và đã được đánh giá về quyền riêng tư; không dùng nó làm metric tag.

Spring Boot có thể bật annotation `@Observed`, `@Timed`, `@Counted` qua `management.observations.annotations.enabled=true` và `spring-boot-starter-aop`. Không đánh dấu thêm controller hoặc repository vốn đã được auto-instrument, nếu không sẽ tạo observation trùng.

## 5. Log request và log sự kiện repository

### 5.1. Request log có cấu trúc

Log request nên ghi method, route template, status và thời gian xử lý. Tránh log toàn bộ request/response body, `Authorization`, cookie, token hoặc dữ liệu cá nhân. Một servlet filter có thể bổ sung log request nếu access log của container chưa đủ:

```java
@Component
public class RestRequestLogFilter extends OncePerRequestFilter {

    private static final Logger log = LoggerFactory.getLogger(RestRequestLogFilter.class);

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain chain) throws ServletException, IOException {
        long started = System.nanoTime();
        try {
            chain.doFilter(request, response);
        } finally {
            Object pattern = request.getAttribute(HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);
            String route = pattern == null ? "unmatched" : pattern.toString();
            long durationMs = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - started);
            log.info("http_request method={} route={} status={} duration_ms={}",
                    request.getMethod(), route, response.getStatus(), durationMs);
        }
    }
}
```

Filter trên là ví dụ cho servlet stack; thêm các import servlet, `OncePerRequestFilter`, `HandlerMapping`, `Logger` và `TimeUnit` tương ứng. Route lấy từ `BEST_MATCHING_PATTERN_ATTRIBUTE` nếu handler đã cung cấp; giá trị `unmatched` dùng cho request không khớp route. Kiểm thử trên embedded server nếu cần xác nhận status cuối cùng của error dispatch hoặc async request. Nếu `http.server.requests` và access log đã đáp ứng nhu cầu, không cần thêm filter trùng lặp.

### 5.2. Repository event log

Spring Data REST phát các event `BeforeCreate`, `AfterCreate`, `BeforeSave`, `AfterSave`, `BeforeLinkSave`, `AfterLinkSave`, `BeforeDelete` và `AfterDelete`. Có thể dùng `@RepositoryEventHandler` để ghi audit event theo domain type:

```java
@Component
@RepositoryEventHandler
public class PersonAuditHandler {

    private static final Logger log = LoggerFactory.getLogger(PersonAuditHandler.class);

    @HandleAfterSave
    public void afterSave(Person person) {
        log.info("repository_event=after_save entity=Person id={}", person.getId());
    }
}
```

Đăng ký handler như Spring bean bằng `@Component` hoặc `@Bean`. Event handler phù hợp để ghi nhận thay đổi domain đã đi qua REST exporter; nó không thay thế request log, metrics hay trace. Log ID hoặc loại thao tác cần thiết, không serialize toàn bộ entity. Các Spring application event này chạy đồng bộ mặc định; nếu chuyển listener sang thread khác hoặc dùng `@Async`, phải cấu hình context propagation để trace ID và MDC tiếp tục được truyền.

## 6. Context propagation và lỗi đã được xử lý

Trace context thường đi cùng thread hiện tại. Khi dùng `@Async` hoặc executor tự cấu hình, context có thể mất nếu đổi thread. Với Spring Boot 3.5, đăng ký `ContextPropagatingTaskDecorator` cho executor tự cấu hình:

```java
@Bean
ContextPropagatingTaskDecorator contextPropagatingTaskDecorator() {
    return new ContextPropagatingTaskDecorator();
}
```

Với `@Async` và `AsyncTaskExecutor` auto-configured, bật `spring.task.execution.propagate-context`; với Reactor, kiểm tra `spring.reactor.context-propagation`. Không tự chuyển event handler sang async chỉ để giảm thời gian request nếu chưa quyết định cách truyền context và cách xử lý lỗi.

Một điểm dễ bỏ sót: HTTP server observation chỉ tự ghi exception là lỗi khi exception chưa được web framework xử lý và đã bubble ra servlet filter. Exception được xử lý trong `@ExceptionHandler` hoặc `ProblemDetail` có thể không xuất hiện trong tag exception/error dù response trả `4xx` hoặc `5xx`. Status và outcome vẫn giúp nhận biết response; nếu cần ghi cả exception đã xử lý, handler tùy chỉnh có thể đặt exception vào observation context bằng `ServerHttpObservationFilter.findObservationContext(request).ifPresent(context -> context.setError(exception))`. Áp dụng cho handler mà ứng dụng kiểm soát và kiểm tra bằng test.

## 7. Kiểm thử observability

Kiểm thử request qua MockMvc và xác nhận meter được tạo sau request. Ví dụ dưới đây giả định `/people` là collection resource đã export và ứng dụng có `MeterRegistry`:

```java
@SpringBootTest
@AutoConfigureMockMvc
class SpringDataRestObservabilityTest {

    @Autowired MockMvc mockMvc;
    @Autowired MeterRegistry meterRegistry;

    @Test
    void getPeopleRecordsHttpAndRepositoryMetrics() throws Exception {
        mockMvc.perform(get("/people"))
                .andExpect(status().isOk());

        Timer httpTimer = meterRegistry.find("http.server.requests")
                .tag("method", "GET")
                .tag("uri", "/people")
                .timer();
        assertThat(httpTimer).isNotNull();
        assertThat(httpTimer.count()).isGreaterThan(0);

        Timer repositoryTimer = meterRegistry.find("spring.data.repository.invocations")
                .tag("repository", "PersonRepository")
                .tag("method", "findAll")
                .timer();
        assertThat(repositoryTimer).isNotNull();
        assertThat(repositoryTimer.count()).isGreaterThan(0);
    }
}
```

Điều chỉnh `uri`, repository name và method theo endpoint thực tế; có thể cần tạo fixture để request thực sự gọi method repository dự kiến. Test tracing nên dùng test exporter hoặc span handler trong bộ test, không phụ thuộc backend OTLP/Zipkin đang chạy ngoài máy. Spring Boot lưu ý các tracing reporter không được auto-configure để gửi dữ liệu khi dùng `@SpringBootTest`; cấu hình reporter test riêng nếu cần assert span.

Các kiểm thử nên bao gồm:

- Một request thành công và một request `4xx`/`5xx`, kiểm tra count, status và outcome.
- Repository method được gọi, kiểm tra meter `spring.data.repository.invocations` và tag state.
- Custom observation bao quanh thao tác nghiệp vụ, kiểm tra timer hoặc span được tạo.
- Trace ID được giữ trong log qua request và lời gọi HTTP client; nếu có `@Async`, kiểm tra cả context propagation.
- Metrics tag dùng URI template và tập giá trị hữu hạn; không có ID, email hoặc token trong metric label.
- Actuator chỉ expose endpoint cần thiết và request không có quyền bị từ chối.

## 8. Troubleshooting

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `/actuator/metrics` trả `404` | Endpoint chưa được expose hoặc chưa có Actuator | Thêm starter Actuator và `management.endpoints.web.exposure.include` phù hợp |
| `/actuator/prometheus` trả `404` | Thiếu Prometheus registry hoặc endpoint chưa expose | Thêm `micrometer-registry-prometheus`, expose `prometheus` và kiểm tra security |
| Không thấy `http.server.requests` | Request không đi qua instrumentation/filter hoặc `ObservationRegistry` không hoạt động | Kiểm tra Spring MVC stack, Actuator auto-configuration và custom filter registration |
| Không thấy `spring.data.repository.invocations` | Repository invocation chưa xảy ra hoặc auto-time đã bị tắt | Kiểm tra request có gọi repository; xem `management.metrics.data.repository.autotime.enabled` |
| Log không có trace ID/span ID | Chưa có tracing bridge, sampling bằng 0 hoặc log pattern bị thay thế | Kiểm tra tracing dependency, `management.tracing.sampling.probability` và MDC pattern |
| Trace dừng ở một service | HTTP client được tạo thủ công hoặc context mất khi đổi thread | Dùng builder auto-configured; cấu hình context propagation cho executor/Reactor |
| Metric có quá nhiều time series | Tag chứa raw URL, ID hoặc giá trị không giới hạn | Dùng URI template và low-cardinality tag; chuyển dữ liệu cần thiết sang trace attribute |
| Dashboard không có exception tag cho response lỗi | Exception đã được `@ExceptionHandler` xử lý trước khi tới servlet filter | Dựa vào status/outcome hoặc đặt error vào observation context trong handler tùy chỉnh |
| Log cùng request xuất hiện nhiều lần | Filter, container access log và middleware cùng ghi một sự kiện | Chọn một nguồn request log chính; giữ event log riêng cho domain action |

Khi điều tra một request, tìm theo trace ID trước, đọc các log cùng correlation ID, mở trace để xem thời gian từng span, rồi đối chiếu metric theo route/status và repository/method. Cách này giúp tách lỗi ứng dụng, truy vấn dữ liệu chậm và dependency bên ngoài.

## 9. Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Observability](https://docs.spring.io/spring-boot/3.5/reference/actuator/observability.html): logging, Micrometer Observation, low/high cardinality và context propagation.
- [Spring Boot 3.5 — Tracing](https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html): tracing bridge, OTLP, sampling, correlation ID, trace propagation và custom observation.
- [Spring Boot 3.5 — Metrics](https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html): `http.server.requests`, `spring.data.repository.invocations`, `@Timed`, MeterRegistry và Prometheus.
- [Spring Boot — Actuator endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): expose endpoint, access control và yêu cầu bảo vệ thông tin vận hành.
- [Spring Data REST — Events](https://docs.spring.io/spring-data/rest/reference/events.html): tám repository lifecycle events, annotated handler và cách đăng ký bean.
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html): HTTP server observation, semantic convention, exception đã được xử lý và context trong event listener.
- [Micrometer — Observation](https://docs.micrometer.io/micrometer/reference/observation.html): API observation và mô hình metrics/tracing.
- [Micrometer — Prometheus](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html): registry và cách export metrics sang Prometheus.