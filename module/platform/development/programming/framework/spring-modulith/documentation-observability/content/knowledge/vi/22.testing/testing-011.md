# Kiểm thử bằng test registry hoặc exporter giả

## 1. Vì sao nên kiểm thử telemetry ở cấp ứng dụng?

Trong ứng dụng Spring Boot dùng **Spring Modulith**, telemetry giúp xác nhận module được gọi, event được công bố, listener được thực thi và các bước xử lý có thể được truy vết. Khi cấu hình observability thay đổi, ứng dụng vẫn có thể khởi động và xử lý nghiệp vụ bình thường nhưng metric không được đăng ký, span thiếu thuộc tính, hoặc exporter không gửi dữ liệu như mong đợi.

Nếu chỉ kiểm tra bằng dashboard production, lỗi schema hoặc exporter thường được phát hiện muộn. Kiểm thử tự động có thể xác nhận instrumentation ngay trong CI bằng các thành phần chạy trong bộ nhớ:

- **Test registry** ghi nhận meter/observation trong tiến trình test để kiểm tra tên, type, unit và tags.
- **Fake exporter hoặc in-memory exporter** thu các span đã hoàn tất để kiểm tra span name, attributes, status và quan hệ trace.
- **Mock endpoint hoặc collector test** kiểm tra request export qua giao thức thực tế khi cần xác minh transport.

Các cách này giúp kiểm tra contract telemetry mà không cần gửi dữ liệu test lên Prometheus, Tempo hoặc hệ thống logging thật.

Tuy nhiên, một test registry thành công không chứng minh Prometheus scrape được endpoint; in-memory span exporter thành công không chứng minh OTLP network exporter gửi được tới collector. Hãy chọn mức test phù hợp với câu hỏi cần trả lời.

Bài học thuộc chương **Kiểm thử** của module **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Module này hướng dẫn dùng Spring Modulith để sinh tài liệu ranh giới application module và quan sát tương tác giữa các phần trong ứng dụng Spring Boot, gồm module graph, Actuator, event metrics, tracing và context propagation.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt unit test instrumentation, integration test trong Spring context và test đường export.
2. Dùng `SimpleMeterRegistry` để kiểm tra metric name, type, value và tags.
3. Dùng `TestObservationRegistry` để xác nhận observation được tạo và có convention đúng.
4. Dùng `InMemorySpanExporter` hoặc fake exporter để kiểm tra spans.
5. Kiểm thử event metrics và module-entry observations của Spring Modulith.
6. Xác minh output của Actuator Prometheus endpoint.
7. Kiểm tra context propagation cho async listener.
8. Tránh test phụ thuộc vào backend thật hoặc dữ liệu thời gian không ổn định.

## 2. Chọn đúng mức kiểm thử

Không có một loại test duy nhất bao phủ toàn bộ telemetry pipeline. Hãy tách các câu hỏi:

| Mức test | Thành phần | Có thể xác nhận | Không tự xác nhận |
| --- | --- | --- | --- |
| Unit test | `SimpleMeterRegistry`, `TestObservationRegistry`, fake exporter. | Code instrumentation tạo đúng meter/observation/span và metadata. | Spring auto-configuration, network export, backend ingestion. |
| Spring integration test | `@SpringBootTest`, registry thật trong context, test exporter. | Bean wiring, Spring Modulith instrumentation, listener và meter registration. | Hạ tầng collector/backend production. |
| Endpoint test | MockMvc/WebTestClient gọi Actuator. | Metric exposition và endpoint exposure/authorization. | Prometheus scrape định kỳ ngoài môi trường test. |
| Exporter transport test | Fake OTLP receiver hoặc collector test. | Payload được gửi qua giao thức, endpoint và headers dự kiến. | Độ bền và capacity của backend production. |
| End-to-end test | Test environment với collector/backend riêng. | Telemetry đi hết pipeline và truy vấn được. | Hành vi ở mọi tải và mọi failure mode production. |

Nên có nhiều test nhỏ, mỗi test kiểm tra một contract. Chỉ dùng end-to-end test cho những đường đi quan trọng vì nó tốn thời gian và dễ phụ thuộc môi trường.

## 3. Kiểm thử metrics bằng SimpleMeterRegistry

`SimpleMeterRegistry` là registry trong bộ nhớ của Micrometer. Nó phù hợp cho unit test vì không cần Prometheus server hoặc exporter.

### 3.1. Tạo component ghi nhận metric

Ví dụ một component ghi số lần vào module:

~~~java
package com.example.shop.observability;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class ModuleInvocationMetrics {

    private final MeterRegistry registry;

    public ModuleInvocationMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void record(String module, String outcome) {
        registry.counter(
            "shop.module.invocations",
            "module", module,
            "outcome", outcome
        ).increment();
    }
}
~~~

Tên metric và tags ở đây là contract do ứng dụng tự định nghĩa. Giá trị của `module` và `outcome` nên đến từ tập giá trị có giới hạn, không phải ID duy nhất của từng request.

### 3.2. Viết unit test

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class ModuleInvocationMetricsTest {

    @Test
    void recordsInvocationWithExpectedTags() {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            ModuleInvocationMetrics metrics =
                new ModuleInvocationMetrics(registry);

            metrics.record("payment", "success");
            metrics.record("payment", "success");

            Counter counter = registry.find("shop.module.invocations")
                .tags("module", "payment", "outcome", "success")
                .counter();

            assertThat(counter).isNotNull();
            assertThat(counter.count()).isEqualTo(2.0);
        }
    }
}
~~~

Test xác nhận ba điều: meter đã được đăng ký, tag values đúng và counter tăng đúng số lần. Nếu đổi tag key hoặc metric name, test sẽ phát hiện contract thay đổi.

### 3.3. Kiểm tra type, unit và cardinality

Không chỉ assert value. Có thể kiểm tra:

- Meter type là Counter, Timer, Gauge hay DistributionSummary theo mục đích.
- Unit và description đã được khai báo đúng.
- Tag keys đúng allowlist.
- Không có tag như `traceId`, `orderId` hoặc `customerId`.
- Tag values thuộc danh mục hữu hạn.

Với Timer, ghi một duration xác định:

~~~java
Timer timer = registry.timer(
    "shop.module.listener.duration",
    "module", "notification"
);

timer.record(Duration.ofMillis(25));

assertThat(timer.count()).isEqualTo(1);
assertThat(timer.totalTime(TimeUnit.MILLISECONDS)).isEqualTo(25.0);
~~~

Không assert thời gian thực thi bằng một ngưỡng quá chặt trong unit test. Hãy ghi duration cố định như ví dụ để test semantics; hiệu năng thật cần benchmark hoặc performance test riêng.

## 4. Kiểm thử Observation bằng TestObservationRegistry

Micrometer Observation cung cấp một abstraction chung cho instrumentation. Một observation có thể được xử lý bởi handlers để tạo metrics, spans hoặc log correlation.

`TestObservationRegistry` thuộc module test của Micrometer Observation, phù hợp xác nhận observation name và key-values mà instrumentation phát ra.

### 4.1. Dependency test

Với Gradle:

~~~kotlin
dependencies {
    testImplementation("io.micrometer:micrometer-observation-test")
}
~~~

Hãy dùng version được quản lý bởi Spring Boot/Micrometer BOM của dự án để tránh lệch phiên bản giữa `micrometer-observation` và test module.

### 4.2. Test một observation

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.tck.TestObservationRegistry;
import io.micrometer.observation.tck.TestObservationRegistryAssert;
import org.junit.jupiter.api.Test;

class ModuleObservationTest {

    @Test
    void recordsModuleIdentity() {
        TestObservationRegistry registry =
            TestObservationRegistry.create();

        Observation.createNotStarted("shop.module.entry", registry)
            .lowCardinalityKeyValue("module.identifier", "payment")
            .lowCardinalityKeyValue("module.invocation-type", "BEAN")
            .observe(() -> {
                // Thực hiện operation được instrument.
            });

        TestObservationRegistryAssert.assertThat(registry)
            .hasObservationWithNameEqualTo("shop.module.entry")
            .that()
            .hasLowCardinalityKeyValue("module.identifier", "payment")
            .hasLowCardinalityKeyValue("module.invocation-type", "BEAN");
    }
}
~~~

Đây là ví dụ kiểm tra một observation do ứng dụng tạo. Tên observation và convention trong ứng dụng thực tế cần khớp với instrumentation đang dùng. Với Spring Modulith, không tự giả định tên observation nếu chưa xác nhận phiên bản và output thực tế.

### 4.3. Phân biệt low-cardinality và high-cardinality values

Low-cardinality key-value có thể được dùng làm dimension cho metrics. High-cardinality key-value phù hợp hơn cho trace/span, chẳng hạn ID của một request hoặc entity. Không chuyển high-cardinality field thành metric tag chỉ vì nó xuất hiện trong observation context.

Nếu convention thay đổi, test nên assert các key quan trọng mà dashboard/alert phụ thuộc, thay vì snapshot mọi key nội bộ của framework. Cách này giữ test có giá trị mà không khóa ứng dụng vào implementation detail.

## 5. Kiểm thử span bằng InMemorySpanExporter

Đối với tracing, một exporter trong bộ nhớ có thể thu thập các span đã kết thúc để test kiểm tra nội dung mà không cần collector.

### 5.1. Dependency test

~~~kotlin
dependencies {
    testImplementation("io.opentelemetry:opentelemetry-sdk")
    testImplementation("io.opentelemetry:opentelemetry-sdk-testing")
}
~~~

Dùng version OpenTelemetry được quản lý thống nhất với bridge/exporter của ứng dụng. Tránh kéo một phiên bản SDK khác vào test classpath.

### 5.2. Tạo tracer provider với exporter trong bộ nhớ

~~~java
import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.context.Scope;
import io.opentelemetry.sdk.OpenTelemetrySdk;
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import io.opentelemetry.sdk.trace.export.SimpleSpanProcessor;
import io.opentelemetry.sdk.testing.exporter.InMemorySpanExporter;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class ModuleSpanExportTest {

    @Test
    void capturesModuleEntrySpan() {
        InMemorySpanExporter exporter = InMemorySpanExporter.create();
        SdkTracerProvider provider = SdkTracerProvider.builder()
            .addSpanProcessor(SimpleSpanProcessor.create(exporter))
            .build();

        try {
            var openTelemetry = OpenTelemetrySdk.builder()
                .setTracerProvider(provider)
                .build();

            var tracer = openTelemetry.getTracer("shop-service");
            Span span = tracer.spanBuilder("spring.modulith.module").startSpan();

            try (Scope scope = span.makeCurrent()) {
                span.setAttribute(
                    AttributeKey.stringKey("module.identifier"),
                    "payment"
                );
                span.setAttribute(
                    AttributeKey.stringKey("module.invocation-type"),
                    "BEAN"
                );
                span.setStatus(StatusCode.ERROR, "gateway timeout");
            } finally {
                span.end();
            }

            var spans = exporter.getFinishedSpanItems();
            assertThat(spans).hasSize(1);
            assertThat(spans.get(0).getName())
                .isEqualTo("spring.modulith.module");
            assertThat(spans.get(0).getAttributes().get(
                AttributeKey.stringKey("module.identifier")
            )).isEqualTo("payment");
            assertThat(spans.get(0).getStatus().getStatusCode())
                .isEqualTo(StatusCode.ERROR);
        } finally {
            provider.close();
        }
    }
}
~~~

Test này chứng minh SDK gọi exporter và span có metadata mong đợi. Nó tạo span trực tiếp bằng OpenTelemetry API, nên chưa chứng minh Spring Modulith tự động tạo đúng module-entry span. Để kiểm tra auto-instrumentation, cần chạy lời gọi module qua Spring application context và thu span từ chính tracer provider mà Micrometer Tracing đang sử dụng.

### 5.3. Fake exporter tự ghi nhận SpanData

Nếu muốn kiểm soát assertions hoặc mô phỏng exporter nhận span, có thể viết exporter giả triển khai `SpanExporter`:

~~~java
import io.opentelemetry.sdk.common.CompletableResultCode;
import io.opentelemetry.sdk.trace.data.SpanData;
import io.opentelemetry.sdk.trace.export.SpanExporter;
import java.util.Collection;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

final class RecordingSpanExporter implements SpanExporter {

    private final List<SpanData> exported = new CopyOnWriteArrayList<>();

    @Override
    public CompletableResultCode export(Collection<SpanData> spans) {
        exported.addAll(spans);
        return CompletableResultCode.ofSuccess();
    }

    @Override
    public CompletableResultCode flush() {
        return CompletableResultCode.ofSuccess();
    }

    @Override
    public CompletableResultCode shutdown() {
        return CompletableResultCode.ofSuccess();
    }

    List<SpanData> exportedSpans() {
        return List.copyOf(exported);
    }
}
~~~

Đây là implementation tối thiểu của exporter giả theo API OpenTelemetry SDK; cần dùng đúng phiên bản SDK trong dự án. `RecordingSpanExporter` chỉ ghi nhận dữ liệu trong process, không gửi OTLP qua mạng.

### 5.4. Những điều nên assert trên SpanData

- Span name và kind có đúng convention cần hỗ trợ không?
- Resource có `service.name` và `service.version` như mong đợi không?
- Module identifier và invocation type có mặt không?
- Status ERROR có được đặt khi operation thất bại không?
- Exception event có được ghi nếu chính sách instrumentation yêu cầu không?
- Trace ID và parent span có được giữ qua async boundary không?
- Không có payload, secret hoặc ID nhạy cảm không được phép.

Không assert mọi attribute do SDK tự thêm. Chỉ khóa những field thuộc telemetry contract mà consumer phụ thuộc.

## 6. Kiểm thử Spring Modulith event metrics

Spring Modulith Insight/observability integration có thể đăng ký meter cho event publication. Trong integration test, nên kiểm tra meter được tạo khi event được publish và kiểm tra riêng listener outcome.

### 6.1. Kiểm tra meter trong Spring context

Ví dụ kiểm tra sự tồn tại của meter tổng hợp sau khi publish event:

~~~java
@SpringBootTest
class ModulithEventMetricsIntegrationTest {

    @Autowired
    ApplicationEventPublisher events;

    @Autowired
    MeterRegistry registry;

    @Test
    void registersPublishedEventMetric() {
        events.publishEvent(new OrderPlaced(UUID.randomUUID(), Instant.now()));

        List<Meter> meters = registry.getMeters().stream()
            .filter(meter -> meter.getId().getName()
                .equals("module.events.published"))
            .toList();

        assertThat(meters).isNotEmpty();
    }
}
~~~

Ví dụ giả định ứng dụng có event `OrderPlaced` và Insight Starter tương thích đã được cấu hình. Metric name và tags cần được xác nhận từ Actuator `/metrics` hoặc registry của phiên bản đang dùng. Nếu meter được tạo theo event type hoặc chỉ sau một điều kiện cụ thể, điều chỉnh test theo semantics thực tế.

### 6.2. Kiểm tra tags mà không khóa vào tag order

Không nên assert thứ tự tags. Hãy kiểm tra key/value theo `Meter.Id`:

~~~java
List<Meter.Id> ids = registry.getMeters().stream()
    .map(Meter::getId)
    .filter(id -> id.getName().equals("module.events.published"))
    .toList();

assertThat(ids).anySatisfy(id -> {
    assertThat(id.getTags())
        .extracting(Tag::getKey)
        .contains("module");
});
~~~

Tên tag `module` trong ví dụ phải được xác nhận ở version Spring Modulith/registry thực tế. Nếu convention upstream đổi, cập nhật test và consumer theo migration có kiểm soát.

### 6.3. Publication metric không thay listener test

Counter event publication chỉ cho biết event được publish theo instrumentation. Nó không chứng minh listener hoàn tất. Hãy kiểm tra listener bằng một fake collaborator:

~~~java
@Test
void listenerInvokesNotificationPort() {
    // Publish OrderPlaced qua ApplicationEventPublisher trong test context.
    // Chờ listener async hoàn tất theo cơ chế đồng bộ hóa của test.
    // Assert fakeNotificationSender đã nhận đúng order ID.
}
~~~

Đây là skeleton vì cách chờ phụ thuộc executor và transaction configuration. Tránh dùng `Thread.sleep()` cố định; dùng latch, Awaitility hoặc test hook có timeout để đồng bộ hóa. Nếu listener dùng `@ApplicationModuleListener`, kiểm tra cả transaction boundary và publication registry khi test recovery.

## 7. Kiểm thử module-entry observations trong Spring context

Unit test với `TestObservationRegistry` xác nhận convention do component tạo. Để xác nhận Spring Modulith thực sự instrument module boundary, cần một integration test gọi bean public qua Spring context.

### 7.1. Cấu trúc integration test

~~~java
@SpringBootTest
class ModuleEntryObservationIntegrationTest {

    @Autowired
    OrderApplicationService orders;

    @Test
    void invokesPublicModuleApi() {
        orders.placeOrder(new PlaceOrderCommand(/* test data */));

        // Thu observation/span từ registry hoặc test exporter
        // được cấu hình trong Spring context.
        // Assert module identifier và invocation type của span.
    }
}
~~~

Đây là skeleton: `OrderApplicationService`, command và test exporter là thành phần của ứng dụng. Test cần gọi qua Spring-managed bean/proxy; gọi trực tiếp constructor hoặc self-invocation có thể bỏ qua instrumentation ở module boundary.

### 7.2. Đừng giả định mọi method đều tạo module span

Spring Modulith quan sát điểm vào phù hợp của module. Một helper method private hoặc lời gọi nội bộ trong cùng bean không nhất thiết tạo một module-entry span mới. Hãy thiết kế test theo public module API và invocation type mà framework hỗ trợ.

### 7.3. Test với ObservationRegistry trong ứng dụng

Nếu cần thu observations thay vì spans, cấu hình test context dùng `TestObservationRegistry` hoặc một custom `ObservationHandler` ghi lại observations. Cần bảo đảm chính `ObservationRegistry` đó được dùng bởi auto-configuration Spring Modulith trong test; tạo một registry độc lập rồi assert nó sẽ không thấy observation phát từ application context.

Với Spring Boot, observability có thể bị giảm/tắt trong một số test slice hoặc cấu hình test. Kiểm tra behavior của phiên bản Boot đang dùng và bật observability test auto-configuration phù hợp trước khi kết luận instrumentation bị lỗi.

## 8. Kiểm thử Actuator metrics endpoint

Registry test xác nhận meter tồn tại trong process. Dashboard và Prometheus lại đọc dữ liệu qua exposition endpoint. Vì vậy, nên có một integration test xác nhận metric được export với tên và labels đúng.

### 8.1. Test endpoint bằng MockMvc

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class PrometheusEndpointTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void exposesExpectedMetric() throws Exception {
        mockMvc.perform(get("/actuator/prometheus"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                containsString("shop_module_invocations")
            ));
    }
}
~~~

Test này giả định endpoint Prometheus được expose và custom meter đã được đăng ký. Có thể kích hoạt operation trước khi gọi endpoint để bảo đảm meter được tạo. Tên trong exposition thường được registry chuẩn hóa, vì vậy hãy xác nhận output thực tế thay vì chỉ đoán cách đổi dấu chấm.

Nếu ứng dụng dùng management port riêng, MockMvc có thể không đại diện đầy đủ cho network path của management server. Khi đó dùng test HTTP client phù hợp với cấu hình ứng dụng.

### 8.2. Kiểm tra endpoint health và modulith

Không cần test mọi Actuator endpoint trong mọi module. Chọn các endpoint là contract vận hành:

- `/actuator/health`: health status được expose theo chính sách.
- `/actuator/prometheus`: metrics cần thiết xuất hiện.
- `/actuator/modulith`: module information có thể truy cập trong môi trường được phép.

Test cả trường hợp unauthorized/forbidden nếu endpoint được bảo vệ. Một endpoint trả 401 vì security policy có thể là hành vi đúng; không coi nó là lỗi exporter.

### 8.3. Kiểm tra schema, không snapshot toàn bộ output

Prometheus exposition có thể thêm meter hoặc đổi thứ tự dòng. Thay vì so sánh toàn bộ response như snapshot cứng, hãy kiểm tra:

- Metric name quan trọng tồn tại.
- Type/comment nếu contract yêu cầu.
- Label keys/values cần thiết.
- Giá trị tăng sau thao tác test.
- Không có label cardinality cao hoặc dữ liệu nhạy cảm.

Điều này giảm false positive khi framework thêm meter nội bộ.

## 9. Kiểm thử transport với fake OTLP receiver

In-memory exporter kiểm tra span trước network. Nếu cần xác nhận OTLP exporter thực sự gửi request tới endpoint, dựng một receiver giả hoặc collector test trong môi trường integration.

### 9.1. Khi nào cần fake receiver?

Fake receiver hữu ích khi cần kiểm tra:

- Endpoint URL và protocol đúng (OTLP/gRPC hoặc OTLP/HTTP).
- Request được gửi tới đúng path/port.
- TLS, headers hoặc authentication metadata được cấu hình.
- Batch export xảy ra sau flush/shutdown.
- Exporter phản ứng đúng với HTTP error hoặc receiver unavailable.

Không cần fake receiver cho mọi unit test. Dùng nó cho cấu hình export quan trọng và các thay đổi có thể làm hỏng transport.

### 9.2. Mô hình test

~~~mermaid
sequenceDiagram
    participant T as Test
    participant A as Spring Boot app
    participant E as OTLP exporter
    participant F as Fake OTLP receiver
    T->>F: start local test endpoint
    T->>A: invoke module API
    A->>E: finish span
    E->>F: POST OTLP payload
    F-->>E: success response
    T->>F: inspect captured request
    F-->>T: request and decoded spans
~~~

Có thể dùng MockWebServer/WireMock hoặc OpenTelemetry Collector chạy trong test container. Với OTLP/HTTP, receiver phải hiểu đúng content type và protobuf/JSON encoding mà exporter gửi. Với OTLP/gRPC, dùng server gRPC giả hoặc collector thật trong container test.

### 9.3. Những điều cần assert

- Request tới đúng endpoint/path.
- Payload chứa span dự kiến, trace ID và attributes cần thiết.
- Resource attributes có service identity.
- Exporter flush hoàn tất trước khi test kết thúc.
- Receiver trả response thành công.
- Khi receiver lỗi, ứng dụng/exporter ghi nhận failure theo behavior đã cấu hình.

Không chỉ assert HTTP request được gửi. Một request có thể tới receiver nhưng payload rỗng, thiếu span hoặc không decode được.

### 9.4. Giới hạn của fake receiver

Fake receiver không mô phỏng đầy đủ batching, backpressure, tail sampling, queue persistence hoặc khả năng chịu tải của production collector. Những đặc tính đó cần test riêng với collector/backend tương thích, thường trong staging hoặc performance environment.

## 10. Kiểm thử context propagation cho async listener

Spring Modulith có thể xử lý event qua listener bất đồng bộ. Khi task chuyển sang executor thread khác, thread-local context như observation scope, trace context hoặc MDC có thể bị mất nếu executor không truyền context.

### 10.1. Cấu hình executor có context propagation

Trong Spring Framework, có thể dùng `ContextPropagatingTaskDecorator` cho executor phù hợp:

~~~java
@Bean
ThreadPoolTaskExecutor applicationTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("module-event-");
    executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
    executor.initialize();
    return executor;
}
~~~

Đây là cấu hình minh họa. Cần xác nhận listener thực sự dùng executor này; việc khai báo bean không tự bảo đảm mọi asynchronous listener dùng nó. Một số phiên bản hoặc cấu hình Spring Modulith có cơ chế executor riêng.

### 10.2. Kiểm tra parent-child relationship

Test nên tạo một operation có parent span, thực hiện công việc async qua executor và thu spans bằng exporter giả. Sau đó kiểm tra:

- Listener span có được export không?
- Span có trace ID giống parent không?
- Parent span ID của listener có trỏ tới span dự kiến không, hoặc có link phù hợp theo semantics của message processing?
- Module attributes và invocation type vẫn tồn tại?
- Scope được đóng sau khi task kết thúc, tránh rò context sang task tiếp theo?

Với message broker hoặc process boundary, không kỳ vọng thread-local context tự truyền qua mạng. Cần inject trace context vào message headers ở producer và extract ở consumer; test phải xác nhận header propagation riêng.

### 10.3. Tránh test chỉ dựa trên log text

Log MDC là một cách quan sát correlation, nhưng test span parent/child trực tiếp đáng tin cậy hơn để xác nhận trace continuity. Có thể thêm test log để kiểm tra traceId/spanId xuất hiện trong structured log, nhưng không dùng regex log làm bằng chứng duy nhất về quan hệ trace.

## 11. Test failure và exporter behavior

Một fake exporter có thể mô phỏng nhiều kết quả để kiểm tra cách instrumentation ứng xử.

| Kịch bản | Cách mô phỏng | Điều cần xác nhận |
| --- | --- | --- |
| Export thành công | In-memory/recording exporter trả success. | Span được thu thập đúng một lần. |
| Export lỗi | Fake exporter trả failure result. | Lỗi được ghi nhận theo SDK/bridge; test không nhầm với span không được tạo. |
| Exporter shutdown | Đóng provider sau khi kết thúc span. | Flush/shutdown được gọi và test không bỏ mất span do kết thúc quá sớm. |
| Collector unavailable | Fake receiver trả lỗi hoặc không lắng nghe. | Retry/timeout và logging theo cấu hình thực tế. |
| Payload không hợp lệ | Receiver test từ chối request. | Lỗi protocol/schema được quan sát, không bị coi là success. |
| Sampling loại trace | Dùng sampler có tỷ lệ loại rõ ràng. | Test phân biệt intentional drop với export failure. |

Không giả định OpenTelemetry SDK retry mọi lỗi theo cùng cách. Behavior phụ thuộc span processor, exporter, retry layer và bridge. Nếu cần test retry, đặt retry ở lớp có contract cụ thể và kiểm tra chính sách của lớp đó.

### 11.1. Fake exporter trả failure

Một exporter giả có thể trả failure result để kiểm tra nhánh lỗi:

~~~java
import io.opentelemetry.sdk.common.CompletableResultCode;
import io.opentelemetry.sdk.trace.data.SpanData;
import io.opentelemetry.sdk.trace.export.SpanExporter;
import java.util.Collection;

final class FailingSpanExporter implements SpanExporter {

    @Override
    public CompletableResultCode export(Collection<SpanData> spans) {
        return CompletableResultCode.ofFailure();
    }

    @Override
    public CompletableResultCode flush() {
        return CompletableResultCode.ofSuccess();
    }

    @Override
    public CompletableResultCode shutdown() {
        return CompletableResultCode.ofSuccess();
    }
}
~~~

Test với exporter này nên xác nhận lỗi được ghi nhận ở đúng tầng (SDK/exporter/bridge) và không khẳng định span đã tới backend. Không viết test giả định retry nếu processor đang dùng không retry.

### 11.2. Sampling và exporter là hai điểm quyết định khác nhau

Nếu sampler trả DROP, exporter có thể không nhận span nào. Nếu sampler trả RECORD_AND_SAMPLE nhưng exporter thất bại, span được tạo nhưng không gửi thành công. Test cần quan sát cả sampling decision và exporter invocation để phân biệt hai trường hợp.

## 12. Cô lập test và tránh flaky tests

Telemetry thường dùng registry, executor và context có vòng đời dài. Nếu test dùng chung state, kết quả có thể phụ thuộc thứ tự chạy.

### 12.1. Tạo registry mới cho mỗi test

- Dùng registry riêng cho mỗi unit test.
- Đóng registry sau khi test kết thúc.
- Không giữ static MeterRegistry hoặc exporter có state dùng chung giữa test.
- Reset exporter và fake receiver khi tái sử dụng fixture.
- Không assert counter value nếu test khác có thể ghi cùng registry.

### 12.2. Đóng tracer provider và exporter

Provider cần được flush/close khi test kết thúc để span được chuyển tới exporter trước khi assertions chạy. Với batch processor, có thể cần gọi force flush hoặc chờ completion có timeout; với simple processor, export thường đồng bộ hơn nhưng vẫn nên quản lý lifecycle.

Không để thread hoặc exporter tồn tại qua nhiều test class. Điều này có thể làm test suite treo hoặc tạo span thừa.

### 12.3. Không dùng Thread.sleep cố định

Async listener, batch exporter và collector có độ trễ biến động. Dùng:

- CountDownLatch hoặc CompletableFuture với timeout.
- Awaitility để chờ điều kiện cụ thể.
- Test hook để biết listener đã hoàn tất.
- Flush API khi cần đồng bộ exporter.

Nếu điều kiện không đạt trước timeout, test nên fail với thông tin hữu ích thay vì tăng sleep đến một giá trị tùy ý.

### 12.4. Dùng Clock cố định cho timestamp

Khi test event metadata hoặc log timestamp, inject Clock và dùng `Clock.fixed` để không phụ thuộc thời gian máy chạy CI. Với duration, ghi một Duration cố định vào Timer; không so sánh elapsed time thực của test bằng ngưỡng quá nhỏ.

## 13. Ma trận kiểm thử đề xuất

| Contract | Unit test | Spring integration | Export/transport |
| --- | --- | --- | --- |
| Metric name/type/tags | `SimpleMeterRegistry` | Kiểm tra MeterRegistry trong context | Kiểm tra exposition `/actuator/prometheus` |
| Observation name/convention | `TestObservationRegistry` | Thu observation từ app registry | Không cần network nếu chỉ kiểm tra convention |
| Module-entry span | Test span convention riêng | Gọi public module API qua Spring context | In-memory exporter hoặc fake OTLP receiver |
| Event publication metric | Kiểm tra custom meter | Publish event và kiểm tra Modulith meter | Kiểm tra Prometheus exposition |
| Listener outcome | Test listener/collaborator | Publish event, chờ listener và kiểm tra side effect | Không cần exporter trừ khi test trace |
| Trace propagation | Test context API | Async listener với executor thật trong test context | Thu parent/child spans từ exporter |
| OTLP transport | Không phù hợp | App context với exporter test | Fake receiver/collector test |
| Log correlation | Test formatter/encoder | Ghi log qua app context | Log appender/agent/backend test khi cần |

Không cần thực hiện mọi ô trong mọi pull request. Chọn test theo phần schema hoặc pipeline bị thay đổi; giữ ít nhất một integration test cho những điểm auto-configuration quan trọng.

## 14. Những lỗi thường gặp khi test telemetry

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Counter luôn bằng 0 | Test query sai tag, dùng registry khác với component hoặc code chưa gọi instrumentation. | Dùng cùng registry instance; kiểm tra meter IDs và gọi operation trước assertion. |
| Meter không xuất hiện trong Spring test | Auto-configuration không bật, registry không được tạo hoặc test slice loại dependency. | Kiểm tra application context và dependency; dùng integration test đầy đủ khi cần. |
| TestObservationRegistry không thấy observation | Component đang dùng ObservationRegistry khác. | Inject cùng registry vào component và test; không tạo registry độc lập. |
| Không có span trong InMemorySpanExporter | Span chưa end, sampler drop, provider khác đang được dùng hoặc processor chưa flush. | Kiểm tra sampling, tracer provider, span lifecycle và flush. |
| Test thấy span nhưng thiếu module attributes | Test tạo span thủ công thay vì đi qua module instrumentation. | Gọi public module API qua Spring context và kiểm tra auto-instrumentation. |
| Span parent ID bị mất ở listener async | Executor không propagate context hoặc message headers không được inject/extract. | Kiểm tra task decorator và propagation tại boundary. |
| Prometheus endpoint trả 404 | Endpoint chưa expose hoặc thiếu registry dependency. | Kiểm tra Actuator, registry và management exposure config. |
| Metric test qua nhưng endpoint không có metric | Registry có meter nhưng exporter filter/endpoint không xuất nó. | Kiểm tra naming convention, filters và exposition output. |
| Test chạy đơn lẻ pass, chạy cả suite fail | Registry/exporter static hoặc executor dùng chung state. | Tạo fixture riêng, reset và đóng resource sau mỗi test. |
| Async test lúc pass lúc fail | Dùng sleep cố định hoặc không chờ listener/exporter hoàn tất. | Dùng latch/Awaitility/flush với timeout. |
| OTLP fake receiver không nhận request | Exporter chưa flush, sai protocol/path/port hoặc sampler không phát span. | Kiểm tra exporter config, sampling, endpoint và shutdown lifecycle. |
| Export failure test vẫn pass | Test chỉ kiểm tra span được tạo, không quan sát exporter result/error. | Assert failure ở đúng lớp exporter/SDK và không suy ra backend đã nhận. |

### 14.1. Đừng mock toàn bộ Micrometer

Mock MeterRegistry hoặc ObservationRegistry có thể hữu ích cho một unit test rất hẹp, nhưng mock thường không giữ semantics thật của registry, meter identity, tag matching hoặc handler lifecycle. Với contract metric/observation, registry test thật trong bộ nhớ thường mang lại bằng chứng tốt hơn.

### 14.2. Đừng biến test thành bản sao implementation

Nếu production code đổi cách tạo Counter nhưng metric contract vẫn giữ nguyên, test chỉ nên quan tâm name/type/tags/value. Tránh assert thứ tự gọi method nội bộ hoặc toàn bộ object graph nếu consumer không phụ thuộc.

### 14.3. Không kiểm tra network bằng in-memory exporter

In-memory exporter chứng minh SDK gọi exporter trong process. Nó không kiểm tra DNS, TLS, OTLP protocol, authentication, collector pipeline hoặc backend ingestion. Khi transport là mục tiêu, dùng fake receiver/collector test.

## 15. Checklist trước khi merge

1. **Chọn đúng mức test:** unit, Spring integration, endpoint hay transport.
2. **Metric contract:** name, type, unit, description và tags được kiểm tra.
3. **Observation contract:** observation name và low-cardinality keys quan trọng được xác nhận.
4. **Trace contract:** span name, attributes, status, resource và parent/link được kiểm tra.
5. **Spring Modulith:** module-entry observation được tạo khi gọi public module API.
6. **Event metrics:** publication meter được đăng ký; listener outcome được test riêng.
7. **Actuator:** endpoint cần thiết trả dữ liệu đúng và security behavior được kiểm tra.
8. **Exporter:** in-memory/fake exporter được dùng cho assertions phù hợp.
9. **Transport:** fake OTLP receiver hoặc collector test được dùng khi thay đổi protocol/config.
10. **Async context:** trace context được truyền đúng qua executor hoặc message boundary.
11. **Isolation:** registry, exporter, executor và fake server có lifecycle rõ.
12. **Determinism:** dùng Clock.fixed, duration cố định và synchronization có timeout.
13. **Cardinality/privacy:** không phát ID duy nhất hoặc dữ liệu nhạy cảm vào metric labels.
14. **Consumer:** dashboard/alert queries quan trọng vẫn match schema.
15. **CI:** test không cần credentials hoặc backend production.

## 16. Bài tập thực hành

### Bài 1 — Unit test metric

Viết component ghi counter số lần gọi module theo module và outcome. Dùng SimpleMeterRegistry để xác nhận metric name, counter value và tags. Thêm một test đảm bảo ID duy nhất không được dùng làm tag.

### Bài 2 — Test Observation convention

Tạo observation cho một operation của module payment. Dùng TestObservationRegistry để kiểm tra observation name, module identifier và invocation type. Thử đổi một key rồi quan sát test phát hiện schema drift.

### Bài 3 — Test span bằng exporter giả

Dùng InMemorySpanExporter để thu span. Assert span name, module identifier, service resource và status ERROR. Sau đó thay sampler để drop span và giải thích vì sao exporter không nhận dữ liệu.

### Bài 4 — Kiểm thử Spring Modulith event metrics

Publish OrderPlaced trong SpringBootTest. Kiểm tra event publication meter được đăng ký. Làm listener thất bại trong môi trường test và xác nhận publication metric không thể đại diện cho listener completion.

### Bài 5 — Kiểm thử module-entry span

Gọi public API của một module qua Spring-managed bean. Thu observations/spans từ registry/exporter của application context. Xác nhận module identifier và invocation type. So sánh với lời gọi trực tiếp constructor để hiểu vì sao proxy boundary quan trọng.

### Bài 6 — Test OTLP transport

Khởi động fake OTLP/HTTP receiver hoặc collector test. Gửi một span từ application context, flush exporter và kiểm tra payload được receiver giải mã. Cho receiver trả lỗi để kiểm tra error path.

### Bài 7 — Async context propagation

Tạo parent span, publish event qua listener async và thu span listener. Kiểm tra trace ID, parent span ID hoặc link theo semantics. Tắt context propagation trong test để quan sát khác biệt.

### Câu hỏi tự kiểm tra

**Câu 1.** Khi nào nên dùng SimpleMeterRegistry?

**Đáp án:** Khi cần kiểm tra metric trong bộ nhớ như name, type, tags và value mà không cần Prometheus hoặc network exporter.

**Câu 2.** TestObservationRegistry kiểm tra điều gì?

**Đáp án:** Nó giúp xác nhận observation được tạo với tên và key-values mong đợi; registry phải là instance thực sự được component sử dụng.

**Câu 3.** InMemorySpanExporter có chứng minh OTLP export hoạt động không?

**Đáp án:** Không. Nó thu span trong process; cần fake OTLP receiver hoặc collector test để kiểm tra transport.

**Câu 4.** Vì sao test module-entry span phải gọi public API qua Spring context?

**Đáp án:** Vì instrumentation của Spring Modulith gắn với module boundary và Spring-managed invocation; gọi trực tiếp object có thể bỏ qua proxy/observation.

**Câu 5.** Event publication counter có chứng minh listener thành công không?

**Đáp án:** Không. Cần kiểm tra side effect/outcome của listener và publication state riêng.

**Câu 6.** Vì sao không dùng Thread.sleep trong async test?

**Đáp án:** Thời gian thực thi biến động; sleep không chứng minh điều kiện đã hoàn tất và tạo flaky test. Dùng latch, Awaitility hoặc flush với timeout.

**Câu 7.** Khi nào cần fake OTLP receiver?

**Đáp án:** Khi cần kiểm tra endpoint, protocol, headers, payload và error behavior của exporter qua network boundary.

## 17. Tài liệu tham khảo

- [Micrometer — Testing](https://docs.micrometer.io/micrometer/reference/observation/testing.html): kiểm thử Observation với test registry.
- [Micrometer — SimpleMeterRegistry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html): registry trong bộ nhớ và meter lifecycle.
- [Micrometer — Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): Observation API, handlers và conventions.
- [OpenTelemetry Java — In-memory exporter](https://github.com/open-telemetry/opentelemetry-java/tree/main/sdk/testing): test exporter và utilities cho SDK.
- [OpenTelemetry Java — Trace SDK](https://opentelemetry.io/docs/languages/java/sdk/): tracer provider, span processor và exporter.
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): test application context và auto-configuration.
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): metrics endpoint và Prometheus exposition.
- [Spring Framework — Context Propagation](https://docs.spring.io/spring-framework/reference/integration/observability.html): context propagation và observability integration.
- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): module-entry observations và event metrics.
- [Spring Modulith — Application Events](https://docs.spring.io/spring-modulith/reference/events.html): event publication registry và listener behavior.

**Ghi nhớ:** dùng test registry để kiểm tra meter và observation contract; dùng in-memory/fake exporter để kiểm tra span data; dùng fake receiver hoặc collector test khi cần xác minh transport. Với Spring Modulith, hãy gọi public module API qua Spring context để xác nhận auto-instrumentation, và kiểm tra event publication tách biệt với listener outcome. Test cần cô lập registry, quản lý lifecycle exporter và đồng bộ async bằng điều kiện có timeout.
