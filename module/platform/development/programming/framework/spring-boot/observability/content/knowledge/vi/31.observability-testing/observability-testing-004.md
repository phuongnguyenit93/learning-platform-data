# Test low-cardinality key trong Spring Boot

Metrics hữu ích khi có thể nhóm và so sánh theo những dimensions ổn định như operation, outcome hoặc region. Nhưng một tag key có vẻ hợp lý vẫn có thể tạo ra hàng nghìn time series nếu value lấy từ user ID, order ID, URL đầy đủ hoặc dữ liệu tự do. Cardinality cao làm tăng memory, storage, query cost và tải lên metrics backend. Vì vậy, kiểm soát cardinality cần được kiểm thử như một thuộc tính của instrumentation, không chỉ là quy ước trong code review.

Bài học này trình bày cách kiểm tra metric tag keys và values trong Spring Boot/Micrometer: xác định dimensions hữu hạn, dùng MeterRegistry test để kiểm tra meters, áp dụng MeterFilter như giới hạn số values, và kiểm thử rằng dữ liệu động/nhạy cảm không lọt vào tags. Mục tiêu là bảo đảm metrics có thể nhóm theo các category cần thiết mà vẫn giữ chi phí observability trong giới hạn.

Bài **Test low-cardinality key** thuộc chương **Testing observability** của module **SPRING_BOOT_OBSERVABILITY**. Module tập trung thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; học context propagation, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích cardinality và tác động của nó lên metrics backend.
- Phân biệt tag key ổn định với tag value có tập giá trị hữu hạn.
- Thiết kế allow-list cho operation, outcome, channel và region.
- Viết test với SimpleMeterRegistry để kiểm tra tag keys/values.
- Dùng MeterFilter.maximumAllowableTags như hàng rào giới hạn.
- Kiểm tra Observation conventions và custom tags.
- Phát hiện ID, URL động, free-text và PII trong metric dimensions.
- Đặt cardinality budget và kiểm thử dưới nhiều input khác nhau.

## 2. Cardinality là gì?

Một meter được xác định bởi tên và tập tag key-value. Mỗi tổ hợp tag values có thể tạo một meter identity/time series riêng. Nếu một Timer có hai tags:

- operation: 4 giá trị.
- outcome: 3 giá trị.

Thì số tổ hợp tối đa là 4 × 3 = 12 series cho một meter name trong một registry, trước khi tính thêm các dimensions khác, instance labels hoặc histogram buckets.

Ngược lại, nếu thêm customer_id có 100.000 giá trị, số series có thể tăng gần tương ứng với số khách hàng. Nếu thêm request_id gần như duy nhất cho mỗi request, cardinality có thể tăng theo tốc độ traffic.

### Key và value

Tag key là tên dimension, ví dụ operation, region, outcome. Tag value là category cụ thể, ví dụ read, ap-southeast, success. Key ổn định không bảo đảm cardinality thấp: một key customer_id vẫn có thể chứa vô số values.

| Tag | Đánh giá | Lý do |
| --- | --- | --- |
| operation=read/write | Thường phù hợp | Tập operation hữu hạn |
| outcome=success/error | Thường phù hợp | Tập kết quả nhỏ |
| region=ap-southeast/eu-west | Có thể phù hợp | Tập region được quản lý |
| customer_id=... | Không phù hợp | Gần như mỗi customer một value |
| request_id=... | Không phù hợp | Gần như duy nhất mỗi request |
| url=/orders/12345 | Không phù hợp | Path chứa ID động |
| email=... | Không phù hợp | PII và cardinality rất cao |

## 3. Đặt cardinality budget trước khi viết test

Cardinality budget là giới hạn dự kiến cho số tổ hợp tag values của một meter hoặc một nhóm meters. Budget nên phản ánh số operation categories, outcome categories, region/channel/tenant-tier categories, instance/replica được scrape, histogram buckets và label expansion của backend.

Ví dụ meter http.server.requests có 8 route templates, 5 methods và 6 outcomes:

\[
8 \times 5 \times 6 = 240
\]

Nếu có 20 instances và mỗi instance export cùng dimensions, backend có thể quan sát khoảng 4.800 series trước histogram expansion. Con số thực tế phụ thuộc registry/backend labels và aggregation configuration.

Đừng chọn budget chỉ từ dữ liệu hiện tại. Hãy xét growth: thêm route, region, tenant tier hoặc status category có làm tổ hợp tăng đột biến không?

## 4. Kiểm thử tag values bằng SimpleMeterRegistry

SimpleMeterRegistry phù hợp cho unit tests vì giữ meters trong memory và không cần Prometheus/OTLP backend. Ví dụ một service ghi Timer với dimensions hữu hạn:

```java
class OrderMetrics {
    private final MeterRegistry registry;

    OrderMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    void record(String operation, String outcome) {
        Timer.builder("orders.operation")
            .tag("operation", operation)
            .tag("outcome", outcome)
            .register(registry)
            .record(() -> performWork());
    }

    private void performWork() {
        // Business operation
    }
}
```

Test xác minh tags được tạo đúng:

```java
class OrderMetricsTest {
    private final SimpleMeterRegistry registry =
        new SimpleMeterRegistry();

    @Test
    void recordsOnlyExpectedLowCardinalityTags() {
        OrderMetrics metrics = new OrderMetrics(registry);

        metrics.record("read", "success");

        Timer timer = registry.find("orders.operation")
            .tag("operation", "read")
            .tag("outcome", "success")
            .timer();

        assertThat(timer).isNotNull();
        assertThat(timer.count()).isEqualTo(1);
    }
}
```

Ví dụ dùng AssertJ và JUnit. Trong dự án thực tế, dùng MeterRegistry được inject và bảo đảm test đóng registry sau khi hoàn tất nếu registry có resources.

### Kiểm tra tập values thực tế

Có thể lấy các meters cùng tên và xem tags:

```java
List<Meter> meters = registry.getMeters().stream()
    .filter(m -> m.getId().getName().equals("orders.operation"))
    .toList();

Set<String> operations = meters.stream()
    .map(m -> m.getId().getTag("operation"))
    .collect(Collectors.toSet());

assertThat(operations)
    .containsOnly("read", "write");
```

Đoạn kiểm tra tập hợp giúp phát hiện value bất ngờ. Với Java version thấp hơn hỗ trợ Stream.toList(), dùng Collectors.toList().

## 5. Test allow-list cho tag values

Không chỉ kiểm tra một input hợp lệ. Hãy gọi instrumentation với nhiều input và xác minh output vẫn thuộc tập allow-list:

```java
enum Operation {
    READ, WRITE, DELETE
}

String operationTag(Operation operation) {
    return switch (operation) {
        case READ -> "read";
        case WRITE -> "write";
        case DELETE -> "delete";
    };
}
```

Một test parameterized có thể kiểm tra mọi enum value và fallback behavior. Nếu input đến từ request hoặc message payload, map về enum/category trước khi ghi meter. Không truyền chuỗi raw từ caller trực tiếp vào tag().

### Unknown values

Với category không nhận diện, chọn behavior rõ ràng: map về other/unknown, reject input nếu đó là business validation, hoặc không tạo tag nếu API hỗ trợ bỏ dimension.

Không dùng raw unknown value làm fallback, vì attacker hoặc client có thể gửi nhiều giá trị khác nhau để làm tăng cardinality.

## 6. Dùng MeterFilter.maximumAllowableTags

Micrometer cung cấp MeterFilter.maximumAllowableTags để giới hạn số tag values cho một meter name và tag key. Đây là safety guard, không thay thế thiết kế tag đúng.

Ví dụ:

```java
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class MetricsConfiguration {

    @Bean
    MeterFilter orderTagCardinalityGuard() {
        return MeterFilter.maximumAllowableTags(
            "orders.operation",
            "operation",
            10,
            MeterFilter.deny()
        );
    }
}
```

Khi vượt giới hạn, filter deny meter mới theo policy được cung cấp. Hãy chọn fallback filter phù hợp và hiểu rằng behavior áp dụng lúc meter registration; filter không tự xóa các time series đã được export trước đó.

### Kiểm thử filter

Có thể đăng ký filter vào registry test rồi tạo nhiều tag values:

```java
SimpleMeterRegistry registry = new SimpleMeterRegistry();
registry.config().meterFilter(
    MeterFilter.maximumAllowableTags(
        "orders.operation", "operation", 2, MeterFilter.deny()
    )
);

Timer.builder("orders.operation")
    .tag("operation", "read")
    .register(registry);
Timer.builder("orders.operation")
    .tag("operation", "write")
    .register(registry);
Timer.builder("orders.operation")
    .tag("operation", "delete")
    .register(registry);

assertThat(registry.find("orders.operation").meters()).hasSize(2);
```

Kết quả chính xác cần được xác minh theo filter order và registry implementation/version. Test nên xác nhận meter bị deny hoặc filter outcome mong đợi, không chỉ dựa vào số lượng tổng nếu registry có common tags hay filters khác.

## 7. Kiểm thử Observation tags và conventions

Trong Spring Boot, nhiều metrics được tạo từ Micrometer Observation. Tag values có thể đến từ Observation convention, low-cardinality key-values hoặc custom instrumentation.

Một test có thể dùng TestObservationRegistry hoặc registry phù hợp trong Micrometer Observation version của dự án để kiểm tra lifecycle và key-values. Ví dụ khái quát:

```java
Observation observation = Observation
    .createNotStarted("orders.process", observationRegistry)
    .lowCardinalityKeyValue("operation", "create")
    .lowCardinalityKeyValue("outcome", "success");

observation.start();
try {
    processOrder();
} finally {
    observation.stop();
}
```

Test cần xác minh handler nhận các low-cardinality values dự kiến. highCardinalityKeyValue có thể phù hợp cho trace/span attributes trong một số hệ thống, nhưng không được chuyển thành metric labels. Kiểm tra convention/handler thực tế và registry output.

### Kiểm thử custom convention

Nếu custom convention lấy route, tenant tier hoặc operation từ request, test cả route template thay vì raw path chứa ID, tenant tier allow-list thay vì tenant ID, HTTP method/status được normalize, unknown route/value đi vào category fallback, và không có authorization header, cookie hoặc payload trong tags.

## 8. Test phát hiện dữ liệu động và PII

Một kiểm thử hữu ích là đưa vào các input có hình dạng rủi ro và xác minh không xuất hiện trong tag values:

```java
@Test
void doesNotUseCustomerIdAsMetricTag() {
    metrics.recordCustomerOperation(
        "customer-7f3a9d2c",
        "read"
    );

    assertThat(registry.getMeters())
        .noneMatch(m -> m.getId().getTags().stream()
            .anyMatch(tag -> tag.getValue().equals("customer-7f3a9d2c")));
}
```

Đây là ví dụ kiểm tra một giá trị sentinel. Có thể dùng sentinel email, order ID, token giả và raw URL trong test; không dùng dữ liệu thật. Với logs/traces, cần kiểm tra các signal riêng vì test MeterRegistry không kiểm tra logging appenders hoặc span exporters.

## 9. Kiểm thử cardinality dưới nhiều inputs

Test nên sinh nhiều inputs khác nhau để đảm bảo số meters không tăng theo từng request:

```java
@Test
void customerIdsDoNotCreateNewTimeSeries() {
    for (int i = 0; i < 500; i++) {
        service.process("customer-" + i, "read");
    }

    long matchingMeters = registry.getMeters().stream()
        .filter(m -> m.getId().getName().equals("orders.operation"))
        .count();

    assertThat(matchingMeters).isLessThanOrEqualTo(4);
}
```

Budget 4 trong ví dụ phải tương ứng với các tổ hợp operation/outcome đã thiết kế. Test cần xác định rõ meter dimensions nào được phép, nếu không con số có thể quá lỏng hoặc sai khi thêm category hợp lệ.

### Property-based testing

Nếu tag values đến từ input phức tạp, property-based tests có thể sinh nhiều chuỗi ngẫu nhiên và kiểm tra số distinct tag values không vượt allow-list, raw input không xuất hiện trong metric tags, null/blank/unknown được normalize thống nhất, và resolver không tạo exception cho input hợp lệ theo contract.

Không cần tạo hàng triệu meters trong unit test; số lượng lớn vừa đủ để chứng minh metric identity không phụ thuộc ID/request value.

## 10. Test exporter/backend khác với test registry

SimpleMeterRegistry kiểm tra instrumentation và tag identity trong process. Nó không chứng minh Prometheus scrape, OTLP export hoặc remote backend hoạt động.

| Test level | Điều xác minh |
| --- | --- |
| Unit test | Tag keys/values, allow-list, fallback và meter count |
| Spring context test | Auto-configuration, ObservationRegistry, filters và conventions |
| Endpoint test | Actuator /metrics hoặc /prometheus trả đúng meters |
| Integration test | Exporter gửi dữ liệu tới Collector/backend test |
| Load test | Cardinality, memory, scrape/export throughput dưới traffic |

Không đưa remote exporter vào mọi unit test. Dùng in-memory registry cho tests nhanh và ổn định; chỉ integration tests mới cần Collector/backend giả lập hoặc test environment.

## 11. Cardinality và histogram buckets

Timer/distribution summary có thể tạo nhiều series cho mỗi tag combination nếu histogram buckets được bật. Ví dụ một Timer có 12 tag combinations và 10 histogram buckets cộng thêm count/sum có thể tạo số series lớn hơn nhiều so với 12.

Cardinality budget cần tính cả tag value combinations, histogram bucket count, instance/replica labels, registry-specific labels và exporter/backend transformations.

Test có thể xác minh histogram configuration riêng, nhưng không nên giả định số series backend đúng bằng số Meter objects trong SimpleMeterRegistry. Hãy kiểm tra exposition format hoặc scrape output khi cần đánh giá series count thực tế.

## 12. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Meter count tăng theo customer IDs | Raw ID được dùng làm tag value | Kiểm tra custom tags/conventions và normalize |
| Filter deny meter hợp lệ | Budget quá thấp hoặc tag key không phù hợp | Kiểm tra filter order và expected categories |
| Unit test pass nhưng production cardinality cao | Common tags/auto instrumentation thêm dimensions khác | Kiểm tra registry output và backend labels |
| Tag key không xuất hiện | Meter chưa register hoặc convention không chạy | Kiểm tra invocation/Observation lifecycle |
| Tag value là URL đầy đủ | Dùng raw URI thay vì route template | Normalize thành route pattern |
| PII xuất hiện trong metrics | Resolver hoặc instrumentation copy request fields | Redact/allow-list và thêm regression test |
| Test meter count không ổn định | Registry dùng chung giữa tests hoặc state không reset | Tạo registry mới mỗi test và close sau test |
| Filter không giới hạn như mong đợi | Filter áp dụng sai meter name/key hoặc order | Kiểm tra matcher và registration sequence |
| Prometheus series nhiều hơn registry meter count | Histogram buckets hoặc labels được thêm khi export | Kiểm tra scrape exposition và backend labels |
| Test exporter flaky | Unit test phụ thuộc network/Collector | Tách unit test và integration test |
| Unknown values tạo series mới | Fallback trả lại raw input | Map về other hoặc reject |

### Checklist review

1. Liệt kê mọi tag keys cho meter cần kiểm thử.
2. Xác định allow-list values và cardinality budget.
3. Kiểm tra nguồn value: enum, request, database, message hay custom resolver.
4. Test valid, unknown, null, dynamic ID và PII sentinel.
5. Kiểm tra MeterRegistry meters và tag sets.
6. Thử MeterFilter guard cho giới hạn đã chọn.
7. Kiểm tra Observation conventions/custom tags.
8. Kiểm tra histogram buckets và exported series nếu cần.
9. Xác nhận registry được reset giữa các tests.

## 13. Thực hành: kiểm soát cardinality cho order metrics

**Bối cảnh:** order-service ghi Timer orders.operation. Ban đầu metric có tags operation và outcome, nhưng một thay đổi thêm customerId khiến số series tăng mạnh. Nhóm cần viết tests ngăn lỗi tái diễn.

### Phần A — Chuẩn bị

1. Dùng SimpleMeterRegistry cho unit tests.
2. Xác định operation allow-list: read, write, delete.
3. Xác định outcome allow-list: success, error.
4. Đặt budget tối đa 3 × 2 = 6 meter identities.
5. Cấu hình resolver map unknown operation/outcome về category đã chọn.
6. Thêm MeterFilter giới hạn tag values như safety guard.

### Phần B — Kiểm chứng

| Ca | Input | Kết quả cần quan sát |
| --- | --- | --- |
| A — Valid | read/success | Meter có đúng hai tags |
| B — All categories | Mọi operation/outcome hợp lệ | Không quá 6 identities |
| C — Unknown | Operation tùy ý từ caller | Normalize hoặc reject, không tạo series mới |
| D — Dynamic ID | 500 customer IDs khác nhau | Meter count không tăng theo customer count |
| E — PII sentinel | Email/token giả | Không xuất hiện trong metric tags |
| F — Filter guard | Vượt tag value budget | Meter mới bị deny theo policy |
| G — Observation | Tạo Observation với low-cardinality keys | Handler/registry nhận đúng values |
| H — Histogram | Bật percentile histogram trong test tích hợp | Đánh giá series expansion ở scrape output |

### Phần C — Câu hỏi tự đánh giá

1. Cardinality của một meter được quyết định bởi những yếu tố nào?
2. Vì sao tag key ổn định vẫn có thể có cardinality cao?
3. SimpleMeterRegistry giúp kiểm tra điều gì?
4. MeterFilter.maximumAllowableTags bảo vệ hệ thống như thế nào?
5. Vì sao filter không thay thế allow-list ở instrumentation?
6. Làm sao kiểm thử unknown values không tạo series mới?
7. Vì sao test registry không chứng minh exporter/backend đã nhận metrics?
8. Histogram buckets ảnh hưởng series count ra sao?
9. Làm thế nào phát hiện PII trong tag values bằng sentinel test?
10. Vì sao cardinality budget cần xét số replicas và dimensions kết hợp?

## 14. Ghi nhớ

**Test low-cardinality key** xác minh metric dimensions có tập values hữu hạn và không phụ thuộc dữ liệu riêng của từng request/user. Dùng SimpleMeterRegistry để kiểm tra meter identity, tag keys/values và số meters; dùng MeterFilter.maximumAllowableTags như hàng rào bổ sung, không thay thế allow-list và normalization trong instrumentation.

Kiểm thử cả inputs hợp lệ, unknown, null, dynamic IDs và PII sentinels. Đối với Observation, kiểm tra conventions và low-cardinality key-values trước khi handler tạo meters. Cardinality budget cần tính tích các dimensions, replicas và histogram buckets; exported series có thể nhiều hơn số Meter objects trong registry. Tách unit tests khỏi endpoint/integration/load tests để kiểm tra đúng từng lớp. Khi các tests này chạy trong CI, thay đổi instrumentation có thể bị phát hiện trước khi làm tăng memory, chi phí metrics backend hoặc rò rỉ dữ liệu.
