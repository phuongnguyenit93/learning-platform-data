# Kiểm thử Observation và tracing bằng công cụ hỗ trợ tương thích

Một thao tác xử lý hóa đơn có thể trả đúng kết quả, trong khi nhóm vận hành lại thiếu số liệu hoặc thấy thao tác xuất hiện thành một trace rời. Bài kiểm thử nghiệp vụ chỉ xác nhận kết quả xử lý. Để kiểm thử khả năng quan sát, cần kiểm tra thêm tín hiệu đã được tạo, các thuộc tính đã được gắn và ngữ cảnh đã được truyền tới đâu.

## Xác định tín hiệu cần kiểm tra

`Observation` mô tả một lần thực thi và vòng đời của nó, như bắt đầu, mở phạm vi ngữ cảnh (scope), ghi nhận lỗi và kết thúc. Các `ObservationHandler` đã đăng ký với `ObservationRegistry` sử dụng vòng đời đó để tạo đầu ra, chẳng hạn số liệu (metrics) hoặc span. Span biểu diễn một phần công việc trong trace. Hai span có thể cùng `traceId`, còn quan hệ trực tiếp cha–con được xác nhận bằng `parentId` của span con và `spanId` của span cha.

| Điều cần chứng minh | Công cụ phù hợp | Khẳng định nên có |
| --- | --- | --- |
| Mã ứng dụng tạo đúng Observation | `TestObservationRegistry` và `TestObservationRegistryAssert` từ `micrometer-observation-test`, hoặc một `ObservationHandler` ghi sự kiện trong bộ nhớ | Tên, thuộc tính, vòng đời thành công và lỗi, scope được đóng. |
| Observation tạo đúng số liệu | `SimpleMeterRegistry` với `DefaultMeterObservationHandler` | Tên timer, số lần ghi và thẻ được phép. |
| Mã gọi đúng giao diện Micrometer Tracing | `SimpleTracer` và `TracerAssert` từ `micrometer-tracing-test` | Span đã được tạo hoặc kết thúc, tên, thẻ hoặc lỗi theo hợp đồng của đoạn mã. |
| Bộ kết nối tracing thực tế tạo đúng span | Bộ kết nối tương ứng với hệ thống, chẳng hạn Brave với `SpanHandler` thu trong bộ nhớ, hoặc OpenTelemetry với bộ xuất span trong bộ nhớ | Quan hệ trace và span, thẻ đã chuyển sang span, scope được khôi phục. |
| Trace đi qua mạng và tới hệ thống thu nhận | Kiểm thử tích hợp với HTTP client đã được gắn công cụ đo và một đích thu nhận dành cho kiểm thử | Header truyền ngữ cảnh đúng định dạng, span phía nhận cùng trace, và đích thu nhận có dữ liệu tương ứng. |

Trong một dự án Spring Boot, dùng phiên bản do BOM của Boot quản lý cho Micrometer, bộ kết nối và các thư viện kiểm thử tương ứng. Ví dụ sau dùng BOM Spring Boot `3.3.5`, Micrometer `1.13.6`, Micrometer Tracing `1.3.5` và Brave `6.0.3`. Chọn công cụ theo lớp đang kiểm tra. Khi cần xác nhận khả năng tương thích với bộ kết nối đang triển khai, hãy chạy phép thử với chính bộ kết nối đó.

## Ví dụ Java 17 với timer và span trong bộ nhớ

`InvoiceProcessor` bọc thao tác xác thực trong `invoice.process`. `operation=validate` có tập giá trị nhỏ nên phù hợp làm thẻ số liệu. `invoice.id` thay đổi theo từng hóa đơn và được khai báo với số lượng giá trị phân biệt cao (high cardinality). Trong ví dụ, mã hóa đơn là dữ liệu giả lập và được dùng để kiểm tra thẻ trên span.

Tạo dự án Gradle riêng và dùng JDK 17 trở lên. Trong `settings.gradle`, đặt `rootProject.name = 'invoice-observability-test'`.

Tệp `build.gradle`

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')
    implementation 'io.micrometer:micrometer-observation'

    testImplementation 'io.micrometer:micrometer-core'
    testImplementation 'io.micrometer:micrometer-tracing-bridge-brave'
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Tệp `src/main/java/demo/observability/InvoiceProcessor.java`

```java
package demo.observability;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public class InvoiceProcessor {

    private final ObservationRegistry registry;

    public InvoiceProcessor(ObservationRegistry registry) {
        this.registry = registry;
    }

    public String process(String invoiceId, boolean valid) {
        return Observation.createNotStarted("invoice.process", registry)
                .lowCardinalityKeyValue("operation", "validate")
                .highCardinalityKeyValue("invoice.id", invoiceId)
                .observe(() -> {
                    if (!valid) {
                        throw new IllegalArgumentException("invalid invoice");
                    }
                    return "accepted";
                });
    }
}
```

Tệp `src/test/java/demo/observability/InvoiceObservabilityTest.java`

```java
package demo.observability;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import brave.Tracing;
import brave.handler.MutableSpan;
import brave.handler.SpanHandler;
import brave.propagation.ThreadLocalCurrentTraceContext;
import brave.propagation.TraceContext;
import brave.sampler.Sampler;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.tracing.Tracer;
import io.micrometer.tracing.brave.bridge.BraveBaggageManager;
import io.micrometer.tracing.brave.bridge.BraveCurrentTraceContext;
import io.micrometer.tracing.brave.bridge.BraveTracer;
import io.micrometer.tracing.handler.DefaultTracingObservationHandler;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;

class InvoiceObservabilityTest {

    @Test
    void completesObservationAndRecordsLowCardinalityMetric() {
        ObservationRegistry registry = ObservationRegistry.create();
        ObservationProbe probe = new ObservationProbe();

        SimpleMeterRegistry meters = new SimpleMeterRegistry();
        try {
            registry.observationConfig()
                    .observationHandler(probe)
                    .observationHandler(new DefaultMeterObservationHandler(meters));

            assertEquals("accepted", new InvoiceProcessor(registry).process("inv-42", true));
            assertEquals(List.of("start", "stop"), probe.events);
            assertEquals("invoice.process", probe.finished.getName());
            assertEquals("validate", probe.finished.getLowCardinalityKeyValue("operation").getValue());
            assertEquals("inv-42", probe.finished.getHighCardinalityKeyValue("invoice.id").getValue());
            assertNull(registry.getCurrentObservation());

            Timer timer = meters.find("invoice.process").tag("operation", "validate").timer();
            assertNotNull(timer);
            assertEquals(1L, timer.count());
            assertNull(timer.getId().getTag("invoice.id"));
        } finally {
            meters.close();
        }
    }

    @Test
    void recordsFailureAndStillStopsObservation() {
        ObservationRegistry registry = ObservationRegistry.create();
        ObservationProbe probe = new ObservationProbe();
        registry.observationConfig().observationHandler(probe);

        var failure = assertThrows(IllegalArgumentException.class,
                () -> new InvoiceProcessor(registry).process("inv-42", false));

        assertEquals(List.of("start", "error", "stop"), probe.events);
        assertSame(failure, probe.finished.getError());
        assertNull(registry.getCurrentObservation());
    }

    @Test
    void createsAChildSpanInTheSameTrace() {
        ObservationRegistry registry = ObservationRegistry.create();
        List<RecordedSpan> spans = new ArrayList<>();
        var current = ThreadLocalCurrentTraceContext.newBuilder().build();

        try (Tracing tracing = Tracing.newBuilder()
                .currentTraceContext(current)
                .sampler(Sampler.ALWAYS_SAMPLE)
                .addSpanHandler(new SpanHandler() {
                    @Override
                    public boolean end(TraceContext context, MutableSpan span, Cause cause) {
                        spans.add(new RecordedSpan(span.name(), context.traceIdString(),
                                context.spanIdString(), context.parentIdString(),
                                Map.copyOf(span.tags())));
                        return true;
                    }
                })
                .build()) {
            Tracer tracer = new BraveTracer(tracing.tracer(),
                    new BraveCurrentTraceContext(current), new BraveBaggageManager());
            registry.observationConfig()
                    .observationHandler(new DefaultTracingObservationHandler(tracer));

            Observation.createNotStarted("invoice.batch", registry)
                    .observe(() -> new InvoiceProcessor(registry).process("inv-42", true));

            assertEquals(2, spans.size());
            RecordedSpan parent = findSpan(spans, "invoice.batch");
            RecordedSpan child = findSpan(spans, "invoice.process");
            assertEquals(parent.traceId(), child.traceId());
            assertEquals(parent.spanId(), child.parentId());
            assertEquals("validate", child.tags().get("operation"));
            assertEquals("inv-42", child.tags().get("invoice.id"));
            assertNull(tracer.currentSpan());
            assertNull(registry.getCurrentObservation());
        }
    }

    private static RecordedSpan findSpan(List<RecordedSpan> spans, String name) {
        return spans.stream().filter(span -> span.name().equals(name)).findFirst().orElseThrow();
    }

    private record RecordedSpan(
            String name, String traceId, String spanId, String parentId, Map<String, String> tags) {
    }

    private static class ObservationProbe implements ObservationHandler<Observation.Context> {

        private final List<String> events = new ArrayList<>();
        private Observation.Context finished;

        @Override
        public boolean supportsContext(Observation.Context context) {
            return true;
        }

        @Override
        public void onStart(Observation.Context context) {
            events.add("start");
        }

        @Override
        public void onError(Observation.Context context) {
            events.add("error");
        }

        @Override
        public void onStop(Observation.Context context) {
            events.add("stop");
            finished = context;
        }
    }
}
```

Chạy từ thư mục dự án.

```bash
gradle test --tests demo.observability.InvoiceObservabilityTest
```

Lần kiểm chứng trực tiếp bằng JUnit Platform trên Java 17 cho kết quả **3 ca đạt, 0 ca thất bại**.

- **Ca thành công** kiểm tra Observation mang cả hai thuộc tính và kết thúc đúng vòng đời. Timer `invoice.process` tăng đúng một lần với thẻ `operation=validate`. Tập thẻ timer loại trừ `invoice.id`, qua đó kiểm tra định danh có nhiều giá trị vẫn ở đúng loại tín hiệu.
- **Ca thất bại** kiểm tra mã nghiệp vụ vẫn ném ngoại lệ. Observation giữ chính ngoại lệ đó, phát sự kiện lỗi rồi kết thúc. Việc kiểm tra scope sau khi gọi giúp phát hiện ngữ cảnh bị giữ lại trên luồng hiện tại.
- **Ca tracing** đặt `invoice.process` trong phạm vi của Observation `invoice.batch`. `DefaultTracingObservationHandler` kết nối vòng đời Observation với tracer. Brave gọi `SpanHandler` khi span kết thúc và bộ thu lưu ảnh chụp các trường cần kiểm tra. Phép thử xác nhận hai span có cùng trace và span con trỏ tới đúng span cha. Tên span và quan hệ giữa các ID là các giá trị cần đối chiếu vì ID được sinh khi chạy.

`Sampler.ALWAYS_SAMPLE` giúp ca tracing chạy xác định. Khi kiểm thử ứng dụng dùng cấu hình tự động của Spring Boot, có thể đặt `management.tracing.sampling.probability=1.0` trong cấu hình kiểm thử để tránh ca lúc có span, lúc bị loại do lấy mẫu. Tỷ lệ lấy mẫu của môi trường triển khai được quyết định riêng theo lưu lượng và nhu cầu thu nhận.

## Khi đưa phép thử vào Spring Boot Actuator

Trong mã ứng dụng, truyền `ObservationRegistry` do Spring quản lý vào thành phần cần đo. Trong kiểm thử đơn vị, một registry mới cho từng ca giúp tách dữ liệu giữa các ca. Trong kiểm thử tích hợp, nếu cần xác nhận cấu hình tự động, hãy lấy registry và tracer từ context để bài thử đi qua các handler thực sự được đăng ký.

Spring Boot 3.3 mặc định bỏ qua việc tự cấu hình các thành phần báo cáo tracing trong `@SpringBootTest`. Nếu mục tiêu là kiểm tra xuất dữ liệu, dùng `@AutoConfigureObservability` cho kiểm thử tích hợp đầy đủ và cấu hình đích thu riêng cho bài thử. Với kiểm thử một lát cắt ứng dụng (test slice), annotation này cung cấp registry cho Observation, meter trong bộ nhớ và tracer không thực hiện ghi nhận (no-op) khi áp dụng cơ chế tự cấu hình của Boot. Để kiểm tra span thật trong lát cắt, cấp rõ tracer và handler có thể ghi nhận, hoặc chuyển ca đó sang kiểm thử tích hợp với cấu hình cần xác minh.

### Khi kết quả thiếu số liệu hoặc span

1. **Khoanh vùng Observation trước.** Kiểm tra mã đang dùng đúng registry, có handler hỗ trợ context, có gọi thao tác thật và có kết thúc vòng đời. Nếu mã dựa vào `@Observed`, kiểm thử qua thành phần đã được cấu hình aspect, vì gọi trực tiếp một đối tượng tự tạo sẽ bỏ qua đường xử lý đó.
2. **Tách số liệu khỏi span.** Với timer, kiểm tra tên, thẻ và mức tăng của bộ đếm sau một thao tác. Với span, kiểm tra handler tracing, bộ lấy mẫu và trạng thái đã kết thúc. Đọc `/actuator/metrics` có thể xác minh số liệu mà Actuator công bố, còn đường thu span được xác minh qua bộ thu span hoặc hệ thống tracing.
3. **Kiểm tra đúng ranh giới truyền ngữ cảnh.** Quan hệ cha–con trong ví dụ chạy trên một luồng. Khi đi qua HTTP, dùng client tạo từ builder đã được Boot cấu hình, chẳng hạn `RestClient.Builder`, và kiểm tra header theo định dạng đã chọn, ví dụ `traceparent` với W3C Trace Context. Khi qua executor hoặc xử lý phản ứng, kiểm tra ở chính ranh giới bất đồng bộ nơi ngữ cảnh cần được mang theo.
4. **Chờ theo điều kiện nếu xuất bất đồng bộ.** Chờ tới khi bộ thu thấy span theo tên và trace cần kiểm tra, với thời gian tối đa rõ ràng. Tạo bộ thu riêng hoặc làm sạch dữ liệu giữa các ca. Kiểm tra thuộc tính có ý nghĩa thay vì so toàn bộ payload chứa ID và thời điểm thay đổi theo lần chạy.

## Tài liệu đối chiếu

- [Micrometer 1.13 · Kiểm thử Observation với registry dành cho kiểm thử](https://docs.micrometer.io/micrometer/reference/1.13/observation/testing.html)
- [Micrometer 1.13 · Observation handler và số liệu](https://docs.micrometer.io/micrometer/reference/1.13/observation/components.html)
- [Micrometer Tracing · Công cụ kiểm thử tracer](https://docs.micrometer.io/tracing/reference/1.5/testing.html)
- [Spring Boot 3.3 · Observation, metrics và tracing trong kiểm thử](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.3 · Bộ kết nối tracing, lấy mẫu và truyền ngữ cảnh](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html)