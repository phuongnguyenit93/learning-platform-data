# Test metrics bằng SimpleMeterRegistry trong Spring Boot

Khi viết code dùng Micrometer, cần kiểm tra metrics được đăng ký đúng, tăng/ghi nhận đúng giá trị và phân biệt đúng theo tags. Không phải test nào cũng cần khởi động toàn bộ Spring Boot application hoặc kết nối Prometheus/OTLP backend. Micrometer cung cấp SimpleMeterRegistry, một registry trong bộ nhớ phù hợp cho unit tests vì không cần network exporter.

**SimpleMeterRegistry giúp kiểm tra hành vi meter trực tiếp và cô lập khỏi hạ tầng export.** Test có thể tạo registry, gọi code nghiệp vụ, đọc Counter/Timer/Gauge và xác minh count, total time hoặc tag identity. Với behavior phụ thuộc Spring AOP, auto-configuration, filters hay exporter, cần bổ sung integration test ở đúng tầng.

Bài **“Test metrics bằng SimpleMeterRegistry”** thuộc chương **Testing observability** của module **SPRING_BOOT_OBSERVABILITY**. Module hướng dẫn thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## 1. SimpleMeterRegistry là gì?

SimpleMeterRegistry là một MeterRegistry lưu measurements trong bộ nhớ. Nó phù hợp để test Counter, Timer, Gauge, DistributionSummary và các meter cơ bản mà không cần exporter/backend.

```java
SimpleMeterRegistry registry = new SimpleMeterRegistry();
```

Test nên tạo registry riêng cho mỗi test hoặc mỗi test fixture. Không dùng global registry dùng chung giữa tests vì meter state có thể rò rỉ từ test này sang test khác.

SimpleMeterRegistry không mô phỏng đầy đủ Prometheus, OTLP hay registry backend cụ thể. Nó kiểm tra semantics của Micrometer meters trong process; không chứng minh scrape format, network export, authentication hoặc backend ingestion.

## 2. Kiểm thử Counter

Counter phù hợp để đếm số lần một sự kiện xảy ra. Test có thể xác minh số lần increment:

```java
@Test
void countsProcessedOrders() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    Counter counter = registry.counter("orders.processed");

    counter.increment();
    counter.increment(2.0);

    assertThat(counter.count()).isEqualTo(3.0);
}
```

Nên kiểm tra code nghiệp vụ thực sự sử dụng registry được inject:

```java
class OrderMetrics {
    private final Counter processed;

    OrderMetrics(MeterRegistry registry) {
        this.processed = registry.counter("orders.processed");
    }

    void recordProcessed() {
        processed.increment();
    }
}

@Test
void serviceRecordsProcessedOrder() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    OrderMetrics metrics = new OrderMetrics(registry);

    metrics.recordProcessed();
    metrics.recordProcessed();

    assertThat(registry.get("orders.processed").counter().count())
            .isEqualTo(2.0);
}
```

Counter là cumulative value. Trong unit test, kiểm tra count trực tiếp; query rate/increase là trách nhiệm của backend query layer và không được SimpleMeterRegistry mô phỏng.

## 3. Kiểm thử tag identity

Tên meter giống nhau nhưng tag values khác nhau tạo meter identities riêng.

```java
@Test
void separatesCounterByOutcomeTag() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();

    registry.counter("orders.processed", "outcome", "success").increment(2);
    registry.counter("orders.processed", "outcome", "failure").increment();

    assertThat(registry.get("orders.processed")
            .tag("outcome", "success")
            .counter()
            .count()).isEqualTo(2.0);

    assertThat(registry.get("orders.processed")
            .tag("outcome", "failure")
            .counter()
            .count()).isEqualTo(1.0);

    assertThat(registry.getMeters()).hasSize(2);
}
```

Test này xác minh tag value tạo identity đúng như dự kiến. Kiểm tra tag keys/values cần thiết và bảo đảm không có identifier động lọt vào tags.

## 4. Kiểm thử cardinality guardrails

Một test có thể phát hiện instrumentation vô tình thêm một meter cho mỗi entity:

```java
@Test
void usesFiniteTagValues() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();

    for (int i = 0; i < 1_000; i++) {
        registry.counter(
                "orders.processed",
                "outcome",
                i % 2 == 0 ? "success" : "failure"
        ).increment();
    }

    assertThat(registry.getMeters()).hasSize(2);
}
```

Nếu code gắn order ID vào tag, số meter sẽ tăng theo số order. Có thể viết test regression để khẳng định tag schema không chứa user/order/request IDs. Không cần tạo hàng triệu identities trong test thường; một bộ dữ liệu nhỏ cũng đủ phát hiện pattern.

## 5. Kiểm thử Timer

Timer ghi nhận count và total time. Test cần tránh phụ thuộc thời gian thực không ổn định.

```java
@Test
void recordsTimerSamples() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    Timer timer = registry.timer("orders.processing");

    timer.record(Duration.ofMillis(120));
    timer.record(Duration.ofMillis(80));

    assertThat(timer.count()).isEqualTo(2);
    assertThat(timer.totalTime(TimeUnit.MILLISECONDS)).isEqualTo(200.0);
}
```

Đây là test deterministic vì truyền duration trực tiếp. Nếu production code dùng Timer.Sample hoặc clock, inject Clock phù hợp hoặc dùng mock/step clock theo API Micrometer version để điều khiển thời gian.

Không assert elapsed time bằng một khoảng quá chặt trên wall clock; CI scheduling, GC và CPU load có thể làm test flaky.

## 6. Kiểm thử Timer.Sample

Timer.Sample cho phép bắt đầu đo rồi dừng ở một điểm sau đó. Khi cần test sample duration, hãy kiểm soát clock thay vì dùng sleep dài.

Ý tưởng:

1. Tạo registry với clock kiểm soát được.
2. Bắt đầu Timer.Sample.
3. Tiến clock theo khoảng xác định.
4. Stop sample vào Timer.
5. Assert count và total time.

API cụ thể của MockClock/Clock phụ thuộc Micrometer version. Giữ test ngắn và deterministic; tránh Thread.sleep vì làm suite chậm và không đảm bảo chính xác.

## 7. Kiểm thử Gauge

Gauge quan sát giá trị hiện tại của object được tham chiếu. Test có thể thay đổi state object rồi đọc gauge:

```java
@Test
void observesQueueSize() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    Queue<String> queue = new ConcurrentLinkedQueue<>();

    Gauge.builder("worker.queue.size", queue, Queue::size)
            .register(registry);

    queue.add("job-1");
    queue.add("job-2");

    assertThat(registry.get("worker.queue.size").gauge().value())
            .isEqualTo(2.0);
}
```

Gauge không phải counter: nó phản ánh giá trị hiện tại, có thể tăng hoặc giảm. Giữ strong reference tới object trong test để tránh object bị garbage-collected nếu gauge implementation dùng weak reference.

Test cần xác minh gauge đăng ký một lần cho resource ổn định, không tạo gauge mới theo mỗi request/entity.

## 8. Kiểm thử DistributionSummary

DistributionSummary đo phân phối các giá trị không phải thời gian, ví dụ payload size hoặc số records trong batch.

```java
@Test
void recordsPayloadSizes() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    DistributionSummary summary =
            registry.summary("message.payload.bytes");

    summary.record(100);
    summary.record(300);

    assertThat(summary.count()).isEqualTo(2);
    assertThat(summary.totalAmount()).isEqualTo(400.0);
}
```

Nếu bật histogram/percentiles, cần test cấu hình distribution riêng và hiểu rằng SimpleMeterRegistry không xác minh export format của backend.

## 9. Kiểm thử meter name, description và unit

Meter name là một phần của contract quan sát được. Test có thể xác minh meter name và tag schema, đặc biệt với metrics được dashboard/alert sử dụng.

```java
Meter meter = registry.get("orders.processed")
        .tag("outcome", "success")
        .meter();

assertThat(meter.getId().getName()).isEqualTo("orders.processed");
assertThat(meter.getId().getTag("outcome")).isEqualTo("success");
```

Description và base unit có thể được kiểm tra qua Meter.Id metadata nếu code đăng ký chúng. Không kiểm tra tên đã được backend chuẩn hóa khi đang test registry thuần; naming convention có thể thay đổi ở exporter registry.

## 10. Kiểm thử MeterFilter

MeterFilter có thể deny, rename hoặc điều chỉnh meter configuration. SimpleMeterRegistry cho phép kiểm tra policy ở registry config.

```java
@Test
void deniesLegacyMeters() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    registry.config().meterFilter(
            MeterFilter.denyNameStartsWith("legacy.")
    );

    registry.counter("orders.processed").increment();
    registry.counter("legacy.debug.calls").increment();

    assertThat(registry.find("orders.processed").counter()).isNotNull();
    assertThat(registry.find("legacy.debug.calls").counter()).isNull();
}
```

Cấu hình filter trước khi meter được đăng ký. Nếu meter đã được đăng ký trước, filter mới có thể không xóa meter cũ. Test nên tạo registry mới cho từng policy scenario.

## 11. Kiểm thử code dùng ObservationRegistry và handlers

SimpleMeterRegistry kiểm tra meters, nhưng Observation còn có lifecycle và handlers. Có thể kết hợp SimpleMeterRegistry với ObservationRegistry và MeterObservationHandler để xác minh Observation tạo ra metric mong đợi.

Ý tưởng test:

1. Tạo SimpleMeterRegistry.
2. Tạo ObservationRegistry.
3. Đăng ký MeterObservationHandler tương ứng.
4. Tạo Observation và thêm low-cardinality KeyValues.
5. Start/stop Observation.
6. Assert meter được ghi vào SimpleMeterRegistry.

Constructor và handler class có thể khác theo Micrometer version. Dùng API đúng dependency được Spring Boot quản lý; không giả định mọi project có cùng constructor.

Nếu chỉ test một Counter/Timer trực tiếp, không cần tạo ObservationRegistry. Test nên giữ phạm vi nhỏ nhất cần thiết.

## 12. SimpleMeterRegistry và Spring Boot integration test

Hai tầng test trả lời hai câu hỏi khác nhau:

| Test type | Xác minh |
| --- | --- |
| Unit test + SimpleMeterRegistry | Code ghi meter đúng tên, tags và value |
| Spring context test | Bean wiring, MeterRegistry injection, customizers, filters, AOP |
| Actuator endpoint test | Endpoint exposure, security và response |
| Exporter integration test | Format, network, authentication và backend ingestion |

Service constructor inject MeterRegistry có thể được unit test bằng SimpleMeterRegistry. Nhưng @Counted phụ thuộc CountedAspect/AOP proxy; cần Spring context test để xác minh aspect intercept bean method.

Không kết luận exporter hoạt động chỉ vì counter trong SimpleMeterRegistry tăng.

## 13. Dùng registry cô lập và cleanup

Tạo registry mới cho mỗi test giúp tránh shared state. Nếu test fixture giữ registry lâu hơn, đóng registry sau test:

```java
@AfterEach
void tearDown() {
    registry.close();
}
```

Khi registry được tạo trong từng test method, có thể dùng try/finally hoặc test fixture lifecycle. Không thêm meters vào global Metrics.globalRegistry rồi kỳ vọng test độc lập; global registry có thể giữ state giữa test classes.

Nếu ứng dụng dùng composite/global registry, kiểm tra test không vô tình ghi cùng event vào cả registry test và global registry.

## 14. Kiểm thử annotation-based metrics

@Counted và @Timed thường dựa trên AOP aspect. SimpleMeterRegistry là nơi đọc kết quả, nhưng không tự kích hoạt AOP.

Trong Spring integration test:

1. Đăng ký CountedAspect/TimedAspect theo cấu hình ứng dụng.
2. Inject service từ ApplicationContext.
3. Gọi method qua injected bean.
4. Đọc counter/timer từ registry.
5. Kiểm tra self-invocation behavior nếu có.
6. Ném exception và xác minh semantics.

Không tạo service bằng new trong test khi mục tiêu là xác minh Spring proxy.

## 15. Những điều SimpleMeterRegistry không kiểm tra

SimpleMeterRegistry không chứng minh:

- Prometheus exposition format và label naming.
- OTLP metric export, temporality hoặc resource attributes.
- Scrape endpoint được expose/security đúng.
- Exporter retry, batching, queue và shutdown flush.
- TLS/authentication tới Collector/backend.
- Backend retention, indexing và alert queries.
- Sampling hoặc distributed trace propagation.

Các behavior này cần integration tests với exporter/Collector/backend hoặc test environment tương ứng.

## 16. Chẩn đoán khi metric test thất bại

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Counter không tồn tại | Code không gọi increment hoặc dùng registry khác | Kiểm tra dependency injection và execution path |
| Count lớn hơn mong đợi | Shared registry hoặc test chạy song song | Tạo registry riêng cho test |
| Tag query không tìm thấy meter | Tag key/value khác hoặc thiếu tag | Kiểm tra Meter.Id |
| Meter count tăng theo entity | Dynamic tag tạo identities mới | Kiểm tra tag schema |
| Timer count đúng nhưng total time sai | Unit conversion hoặc timing boundary | Assert đúng TimeUnit và deterministic clock |
| Gauge trả NaN/không có value | Object bị GC hoặc gauge registration sai | Giữ reference và kiểm tra supplier |
| MeterFilter không có tác dụng | Filter thêm sau meter registration | Tạo registry mới, cấu hình filter trước |
| @Counted không tăng | Aspect/proxy không chạy | Dùng Spring integration test |
| Actuator không thấy meter | Endpoint/exposure/registry khác | Test Actuator context riêng |
| Backend không nhận metrics | Exporter/network/auth issue | Integration test pipeline |

## 17. Bài thực hành: xây metric test suite

Thực hiện trong local/test:

1. Tạo service dùng MeterRegistry để ghi orders processed.
2. Viết unit test bằng SimpleMeterRegistry cho Counter.
3. Thêm outcome tags success/failure và xác minh hai meter identities.
4. Viết test cardinality với 1.000 operations nhưng chỉ hai tag values.
5. Thêm Timer và record duration xác định bằng Duration.
6. Thêm Gauge cho queue size và thay đổi queue state.
7. Thêm DistributionSummary cho payload size.
8. Thêm MeterFilter deny một prefix và xác minh meter bị từ chối.
9. Tạo Spring integration test cho @Counted aspect.
10. Tạo ObservationRegistry test nếu cần kiểm tra Observation handlers.
11. Kiểm tra registry cleanup và không dùng global shared state.
12. Viết exporter integration test riêng nếu cần xác minh Prometheus/OTLP.

Kết quả mong đợi: unit tests deterministic xác minh meter behavior; integration tests xác minh wiring/AOP/Actuator/exporter ở đúng tầng.

## 18. Câu hỏi tự kiểm tra

1. SimpleMeterRegistry phù hợp loại test nào?
2. Vì sao nên tạo registry riêng cho mỗi test?
3. Counter count khác rate query thế nào?
4. Cùng meter name nhưng tag values khác nhau tạo điều gì?
5. Làm sao test cardinality bằng finite tag values?
6. Vì sao Timer test nên dùng duration xác định?
7. Gauge khác Counter thế nào?
8. Gauge có thể bị ảnh hưởng bởi object lifecycle ra sao?
9. DistributionSummary phù hợp đo dữ liệu nào?
10. MeterFilter cần được cấu hình khi nào?
11. ObservationRegistry khác MeterRegistry thế nào?
12. Vì sao @Counted cần Spring integration test?
13. SimpleMeterRegistry có kiểm tra Prometheus/OTLP export không?
14. Khi nào cần test Actuator endpoint/security?
15. Làm sao tránh test state rò rỉ qua global registry?

## Tài liệu tham khảo

- [Micrometer — MeterRegistry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html): registry abstraction và SimpleMeterRegistry.
- [Micrometer — Meters](https://docs.micrometer.io/micrometer/reference/concepts/meters.html): Counter, Timer, Gauge, DistributionSummary và meter identity.
- [Micrometer — Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html): filter configuration.
- [Micrometer — Observation](https://docs.micrometer.io/micrometer/reference/observation.html): ObservationRegistry và handlers.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): MeterRegistry auto-configuration và Actuator metrics.
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): Spring application integration testing.

## Kết luận

**SimpleMeterRegistry là công cụ gọn nhẹ để kiểm tra hành vi metrics trong unit tests mà không cần exporter hoặc backend.** Nó phù hợp xác minh Counter, Timer, Gauge, DistributionSummary, tags, meter identity và MeterFilter bằng state trong bộ nhớ.

Tạo registry cô lập, dùng thời gian xác định, kiểm tra cardinality và cleanup để test ổn định. Khi cần xác minh AOP, Spring bean wiring, Observation handlers, Actuator security hoặc Prometheus/OTLP export, bổ sung integration tests tương ứng. Phân chia test theo đúng boundary giúp phát hiện lỗi metrics sớm mà không làm unit suite phụ thuộc hạ tầng telemetry bên ngoài.

