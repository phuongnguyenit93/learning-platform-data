# @Timed

Trong chương **Annotation observability** của mô-đun **SPRING_BOOT_OBSERVABILITY**, annotation @Timed của Micrometer giúp đo thời gian thực thi của một method và ghi nhận kết quả vào một Timer. Khi ứng dụng Spring Boot được cấu hình Micrometer metrics đúng cách, Timer có thể được export tới registry để theo dõi số lần gọi, tổng thời gian, max và histogram/percentiles nếu được bật.

@Timed phù hợp khi cần đo một method có ý nghĩa vận hành rõ ràng, ví dụ xử lý báo cáo, tính giá hoặc thực hiện một bước nghiệp vụ. Tuy nhiên, annotation không tự đo mọi đoạn code: nó cần cơ chế interception phù hợp, thường là Spring AOP/proxy hoặc instrumentation được cấu hình tương ứng. Self-invocation, method private/final, object tự tạo ngoài Spring context và async execution có thể khiến phép đo không chạy như mong đợi.

Bài này giải thích cách dùng @Timed trong Spring Boot, cách cấu hình metric name/tags/histogram, giới hạn của proxy, khác biệt giữa synchronous và asynchronous methods, cách kiểm thử và cách tránh cardinality cao.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:
1. Giải thích @Timed tạo Timer như thế nào và dữ liệu được ghi nhận ở đâu.
2. Phân biệt method timing với HTTP server/client observations.
3. Cấu hình Micrometer và AOP/instrumentation cần thiết cho @Timed.
4. Đặt metric name và tags ổn định.
5. Bật histogram/percentiles phù hợp với latency analysis.
6. Hiểu giới hạn Spring proxy: self-invocation, private/final methods và object không do Spring quản lý.
7. Đánh giá @Timed với async/reactive methods và completion lifecycle.
8. Kiểm thử count, duration và tags bằng MeterRegistry.
9. Tránh dùng request/user identifiers làm metric tags.
10. Biết khi nào nên dùng Observation API hoặc Timer thủ công thay cho annotation.

## 2. @Timed là gì?

@Timed là annotation của Micrometer dùng để đo thời gian một method được thực thi. Khi được xử lý bởi instrumentation/AOP tương ứng, mỗi lần method được gọi sẽ được ghi nhận vào Timer có tên và tags đã cấu hình.

~~~java
@Service
class PricingService {

    @Timed(value = "pricing.calculate", description = "Time spent calculating price")
    public Price calculate(PriceRequest request) {
        return pricingEngine.calculate(request);
    }
}
~~~

Timer có thể cung cấp:
- count: số lần method được đo.
- totalTime: tổng thời gian của các lần gọi.
- max: thời gian lớn nhất trong cửa sổ/implementation tương ứng.
- Histogram buckets nếu được bật.
- Percentiles nếu registry và cấu hình hỗ trợ.

Không phải mọi registry đều lưu hoặc truy vấn cùng tập thống kê. Prometheus thường dùng histogram buckets để tính quantiles ở server; một số registry có thể tính client-side percentiles. Hiểu semantics của backend trước khi dùng percentile trong alert.

### @Timed khác gì @Observed?

| Annotation/API | Mục đích chính | Tín hiệu |
| --- | --- | --- |
| @Timed | Đo duration/count của method. | Micrometer Timer. |
| @Observed | Mô tả operation để nhiều Observation handlers xử lý. | Metrics và tracing tùy handlers. |
| HTTP Observation | Đo một HTTP exchange ở framework layer. | HTTP metrics và spans. |
| Timer API thủ công | Đo đoạn code có lifecycle tùy chỉnh. | Micrometer Timer. |

Nếu muốn một method vừa có metrics vừa có span/correlation context, Observation thường là abstraction phù hợp hơn. Không thêm @Timed và @Observed quanh cùng method nếu không có chủ đích, vì có thể tạo metrics trùng hoặc hai spans tương tự.

## 3. Dependency và enablement trong Spring Boot

Spring Boot quản lý Micrometer qua Actuator và các registry dependencies. Ví dụ:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Để @Timed được xử lý qua Spring AOP, ứng dụng cần cơ chế AOP phù hợp với phiên bản Boot và cách dùng annotation. Trong cấu hình Micrometer annotation-based truyền thống, cần AspectJ support và đăng ký TimedAspect:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
~~~

TimedAspect là thành phần Micrometer AOP hỗ trợ xử lý @Timed trên Spring beans. Không giả định chỉ thêm Actuator là annotation tự động được intercept trong mọi phiên bản/cấu hình. Kiểm tra reference docs và bean configuration của dự án.

~~~java
@Configuration(proxyBeanMethods = false)
class MetricsAnnotationConfiguration {

    @Bean
    TimedAspect timedAspect(MeterRegistry registry) {
        return new TimedAspect(registry);
    }
}
~~~

Tùy Boot/Micrometer version, có thể có auto-configuration hoặc yêu cầu khai báo aspect thủ công. Tránh đăng ký hai TimedAspect cùng lúc. Kiểm tra application context và metric count để xác nhận chỉ một instrumentation đang chạy.

## 4. Đặt tên Timer và tags

Metric name cần mô tả operation ổn định, không chứa giá trị của từng request.

~~~java
@Timed(
    value = "order.validation",
    description = "Time spent validating an order",
    extraTags = {"operation", "validate"}
)
public ValidationResult validate(OrderRequest request) {
    return validator.validate(request);
}
~~~

Nguyên tắc:
- Dùng tên metric phản ánh operation, ví dụ order.validation.
- Tags có tập giá trị hữu hạn như operation, outcome, channel.
- Không đưa order ID, user ID, email, request ID hoặc raw URL vào tags.
- Không đưa exception message làm tag.
- Tránh đặt tag value từ input do caller kiểm soát.

| Tag | Giá trị ví dụ | Nhận xét |
| --- | --- | --- |
| operation | validate | Tập hữu hạn. |
| outcome | success / failure | Tập hữu hạn. |
| channel | web / batch | Tập hữu hạn nếu được quản lý. |
| order.id | 1001 | Cardinality cao, không phù hợp. |
| customer.email | alice@example.com | PII và cardinality cao. |
| exception.message | Connection timeout to host... | Không ổn định, có thể chứa dữ liệu nhạy cảm. |

extraTags là các cặp key/value cố định được khai báo trên annotation. Nếu cần tag động, hãy xem xét Observation convention hoặc Timer API với allowlist; đừng lấy mọi method arguments làm tags.

## 5. Cấu hình histogram và percentiles

Timer có thể được cấu hình để export histogram buckets hoặc percentiles. Với Spring Boot, cấu hình distribution statistics theo metric name:

~~~yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        order.validation: true
      percentiles:
        order.validation: 0.5, 0.95, 0.99
      slo:
        order.validation: 100ms, 250ms, 500ms
~~~

Property hỗ trợ và cách export phụ thuộc registry/version. Histogram hữu ích khi muốn tính percentile ở backend tập trung; client-side percentiles có thể không aggregate chính xác qua nhiều instances. Với Prometheus, histogram buckets thường là lựa chọn tốt hơn cho aggregate quantiles.

Chọn bucket/SLO boundaries theo latency objective thực tế. Quá nhiều buckets làm tăng series count và storage cost. Không bật histogram cho mọi Timer một cách máy móc.

## 6. Spring AOP proxy và giới hạn của @Timed

Spring AOP thường intercept method invocation thông qua proxy. Điều này tạo ra một số giới hạn quan trọng.

### Self-invocation

~~~java
@Service
class ReportService {

    public void runReport() {
        generate(); // gọi nội bộ trên this, không đi qua proxy
    }

    @Timed("report.generate")
    public void generate() {
        // expensive work
    }
}
~~~

Nếu runReport() gọi generate() trực tiếp trên cùng object, invocation có thể không đi qua proxy nên @Timed không được áp dụng. Cách xử lý:
- Đặt method được đo trong một Spring bean khác và inject bean đó.
- Gọi qua proxy bean từ caller bên ngoài.
- Dùng Timer/Observation API thủ công nếu operation không phù hợp proxy.

Không dùng self-injection làm giải pháp mặc định nếu có thể thiết kế boundary rõ hơn.

### Private và final methods

Proxy-based AOP chỉ intercept method phù hợp với proxy strategy và khả năng override/interface. Private methods không thể được gọi qua proxy như public service method. Final class/method cũng có thể giới hạn subclass-based proxy. Kiểm tra loại proxy (JDK interface proxy hay class-based proxy) và visibility của method.

### Object không do Spring quản lý

Nếu code tạo object bằng new PricingService(...), Spring AOP không quản lý object đó; annotation không được intercept. Dùng Spring bean lifecycle và dependency injection.

## 7. Đồng bộ và bất đồng bộ

Với method đồng bộ, Timer thường đo từ lúc method được intercept đến khi method trả về hoặc ném exception.

Với async methods trả về CompletableFuture, CompletionStage, Reactor Mono/Flux, cần xác minh instrumentation đo thời gian tới lúc method trả về object hay tới lúc computation hoàn tất. AOP annotation đơn giản có thể không đo đúng thời gian asynchronous completion nếu aspect không hỗ trợ type/lifecycle đó.

~~~java
@Timed("report.generate.async")
public CompletableFuture<Report> generateAsync() {
    return CompletableFuture.supplyAsync(reportGenerator::generate);
}
~~~

Method này có thể trả về CompletableFuture gần như ngay lập tức, trong khi công việc tiếp tục chạy sau đó. Không giả định Timer mặc định bao trọn thời gian future hoàn tất. Với async/reactive work, dùng Observation/Timer API có lifecycle completion rõ ràng hoặc instrumentation hỗ trợ return type đó; kết thúc measurement trong callback/terminal signal.

Đối với Reactor, không chặn pipeline để đo thời gian. Dùng instrumentation/context propagation tương thích reactive stack.

## 8. Exception và outcome

Nếu method ném exception ra khỏi proxy, aspect có thể ghi nhận exception theo semantics của Micrometer version. Nếu method catch exception rồi trả về fallback, aspect có thể coi invocation hoàn tất bình thường.

~~~java
@Timed("inventory.lookup")
public Inventory find(String sku) {
    try {
        return repository.find(sku);
    } catch (DataAccessException ex) {
        log.warn("Inventory lookup failed, errorType={}",
                ex.getClass().getSimpleName());
        throw ex;
    }
}
~~~

Không đưa exception message vào tags. Nếu cần phân biệt success/failure trong metrics, hãy thêm tag outcome với tập giá trị hữu hạn thông qua Observation/custom instrumentation hoặc tách Timer có chủ đích. Không tạo tag riêng cho từng exception instance.

Một HTTP 404 hoặc business rejection không nhất thiết là exception. Định nghĩa outcome theo semantics của operation, không chỉ dựa trên việc Java method có throw hay không.

## 9. @Timed và HTTP/Database observations

Spring Boot đã có framework-level observations cho HTTP server/client và một số database/client integrations. @Timed phù hợp để đo một business method bổ sung, ví dụ order.validation, report.generation, pricing.calculate hoặc inventory.reconciliation.

Không nên thêm @Timed vào mọi controller method nếu http.server.requests đã đo thời gian toàn request. Điều đó có thể hợp lý khi muốn tách riêng một business phase, nhưng metric phải có tên khác và mục đích rõ ràng.

Tương tự, @Timed trên repository method không thay thế JDBC spans. Timer cho biết tổng thời gian method; JDBC spans cho biết từng SQL call. Một method repository có thể thực hiện nhiều queries, nên hai tín hiệu trả lời câu hỏi khác nhau.

~~~mermaid
flowchart TD
    Request["HTTP server observation"]
    Request --> Service["OrderService"]
    Service --> Timed["Business @Timed: order.validation"]
    Timed --> Repo["Repository method"]
    Repo --> JDBC["JDBC/database spans"]
    Request --> Metrics["HTTP timer"]
    Timed --> BusinessMetric["Business method timer"]
    JDBC --> Trace["Trace backend"]
~~~

## 10. Kiểm tra Timer qua Actuator

Nếu Actuator metrics endpoint được expose trong môi trường được bảo vệ, truy vấn:

~~~http
GET /actuator/metrics/order.validation
~~~

Ví dụ response minh họa:

~~~json
{
  "name": "order.validation",
  "measurements": [
    { "statistic": "COUNT", "value": 42.0 },
    { "statistic": "TOTAL_TIME", "value": 1.26 },
    { "statistic": "MAX", "value": 0.084 }
  ],
  "availableTags": [
    { "tag": "operation", "values": ["validate"] }
  ]
}
~~~

Payload thực tế phụ thuộc registry, meter filters và distribution settings. Nếu meter không xuất hiện:
- Kiểm tra TimedAspect bean.
- Kiểm tra method được gọi qua Spring proxy.
- Kiểm tra đúng MeterRegistry.
- Kiểm tra metric name/tag values.
- Kiểm tra meter filters hoặc registry configuration.
- Xác minh annotation import đúng io.micrometer.core.annotation.Timed.

Không expose Actuator metrics endpoint công khai chỉ để kiểm tra; bảo vệ bằng authentication và network policy.

## 11. Kiểm thử @Timed

Có thể dùng SimpleMeterRegistry trong unit/integration test để xác minh Timer được đăng ký:

~~~java
@SpringBootTest
class PricingServiceTimedTest {

    @Autowired
    PricingService pricingService;

    @Autowired
    MeterRegistry meterRegistry;

    @Test
    void recordsMethodExecution() {
        pricingService.calculate(new PriceRequest("SKU-1"));

        Timer timer = meterRegistry.find("pricing.calculate").timer();

        assertThat(timer).isNotNull();
        assertThat(timer.count()).isEqualTo(1);
    }
}
~~~

Test cần gọi Spring bean từ application context để invocation đi qua proxy. Gọi method trên object tự tạo trong test có thể bỏ qua AOP.

Các ca kiểm thử:
1. Method success ghi count và duration.
2. Method ném exception vẫn ghi nhận timer/error theo convention.
3. Self-invocation được phát hiện hoặc thiết kế tránh.
4. Private/final method behavior được xác minh.
5. Tags không chứa dynamic identifiers.
6. Async completion duration được kiểm tra theo semantics thực tế.
7. Không có duplicate Timer do nhiều aspects.
8. Histogram/percentiles được export đúng registry.

## 12. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Không có Timer | Thiếu TimedAspect/AOP hoặc method không qua proxy. | Kiểm tra dependency AOP, bean và call path. |
| Timer count bằng 0 | Method chưa được gọi hoặc test gọi object ngoài Spring context. | Inject bean và gọi qua proxy. |
| Self-invocation không được đo | Gọi nội bộ qua this. | Tách bean hoặc dùng Timer/Observation API. |
| Private/final method không được intercept | Proxy strategy không hỗ trợ method. | Dùng public method phù hợp hoặc instrumentation thủ công. |
| Duration quá ngắn với CompletableFuture | Aspect đo thời điểm method trả future thay vì completion. | Đo lifecycle future/async bằng API phù hợp. |
| Timer xuất hiện hai lần | Có nhiều TimedAspect hoặc custom instrumentation trùng. | Kiểm tra bean và AOP configuration. |
| Tag values tăng liên tục | Dynamic values được thêm vào tags. | Dùng allowlist và loại identifiers. |
| Percentile không aggregate đúng | Dùng client-side percentiles trên nhiều instances. | Dùng histogram buckets và backend aggregation. |
| Timer không có tracing span | @Timed chỉ đo metrics; chưa có Observation/tracing integration. | Dùng @Observed hoặc Observation API nếu cần span. |
| Metric name khác dự kiến | Naming convention/registry đổi tên. | Kiểm tra Actuator và exported series. |

## 13. Runbook: @Timed không tạo metrics

1. Xác nhận annotation import từ Micrometer.
2. Kiểm tra Spring Boot/Micrometer version và dependency management.
3. Kiểm tra starter AOP và TimedAspect bean.
4. Xác nhận service là Spring bean.
5. Xác nhận caller đi qua proxy; kiểm tra self-invocation.
6. Xác nhận method visibility và proxy strategy.
7. Gọi method một lần trong test.
8. Truy vấn Actuator /actuator/metrics/{metric-name}.
9. Kiểm tra tags và meter filters.
10. Nếu method async, xác minh Timer kết thúc khi computation hoàn tất.
11. Kiểm tra duplicate aspects/custom instrumentation.
12. Nếu cần distributed trace, kiểm tra Observation/Tracing integration riêng; Timer không tự đảm bảo có span.

## 14. Bài tập tự kiểm tra

### Bài 1 — Self-invocation

Method run() gọi method calculate() có @Timed trong cùng class. Vì sao Timer có thể không được tạo?

**Đáp án:** Lời gọi nội bộ qua this không đi qua Spring proxy, nên AOP advice có thể không chạy. Tách method sang bean khác hoặc đo thủ công bằng Timer/Observation.

### Bài 2 — Async duration

Method có @Timed trả về CompletableFuture ngay lập tức, nhưng computation chạy 5 giây. Timer có thể ghi nhận gì?

**Đáp án:** Nếu aspect chỉ đo invocation đồng bộ, Timer có thể chỉ đo thời gian tạo future/return, không phải 5 giây completion. Cần instrumentation bao quanh async completion.

### Bài 3 — Cardinality

Có nên thêm orderId vào extraTags động để tìm một order cụ thể?

**Đáp án:** Không. Metric tag tạo time series theo từng order và làm cardinality tăng. Dùng logs/traces với identifier được kiểm soát.

### Bài 4 — Có Timer nhưng không có span

Một method có @Timed xuất hiện trong Actuator nhưng không thấy span. Có nhất thiết tracing bị lỗi không?

**Đáp án:** Không. @Timed tập trung vào Timer metrics. Nếu cần span, dùng @Observed hoặc Observation API và cấu hình tracing handler.

### Bài 5 — HTTP request đã có timer

Một controller có @Timed trong khi http.server.requests đã đo toàn request. Có nên giữ cả hai?

**Đáp án:** Chỉ khi timer bổ sung đo một business operation riêng có ý nghĩa. Nếu đo cùng toàn bộ request, có thể tạo metric trùng và gây nhầm dashboard.

### Bài 6 — Percentile

Một nhóm bật percentiles trên mỗi application instance rồi cộng các giá trị P95 của replicas để tính P95 toàn hệ thống. Cách này có đúng không?

**Đáp án:** Không. Percentiles không thể cộng/trung bình đơn giản để ra percentile tổng. Dùng histogram buckets và backend aggregation phù hợp.

## 15. Checklist triển khai

- [ ] @Timed được import từ Micrometer.
- [ ] Micrometer registry và AOP/TimedAspect được cấu hình đúng version.
- [ ] Chỉ có một TimedAspect xử lý annotation.
- [ ] Method nằm trong Spring bean và invocation đi qua proxy.
- [ ] Tránh self-invocation hoặc đo bằng API thủ công.
- [ ] Method visibility/final behavior phù hợp proxy strategy.
- [ ] Metric name và extraTags ổn định, cardinality thấp.
- [ ] Không đưa request/user/order IDs, PII hoặc exception message vào tags.
- [ ] Histogram/percentiles/SLO buckets được bật có chủ đích.
- [ ] Async/reactive method được đo tới completion theo đúng semantics.
- [ ] Không tạo metrics trùng với HTTP/Database observations nếu không có mục tiêu rõ.
- [ ] Dùng @Observed/Observation khi cần cả metrics và tracing span.
- [ ] Test gọi Spring bean qua proxy và xác minh Timer count/duration.
- [ ] Actuator metrics endpoint được bảo vệ.
- [ ] Dashboard/alert dùng histogram semantics đúng với registry/backend.

**Ghi nhớ:** @Timed đo duration/count của method khi instrumentation có thể intercept invocation. Trong Spring Boot, kiểm tra AOP/TimedAspect, proxy path và loại method; đặt metric name/tags ổn định; đặc biệt xác minh async completion và histogram semantics. Dùng @Timed cho business timing bổ sung, còn Observation/@Observed phù hợp khi cần liên kết metrics với tracing và các tín hiệu khác.
