# Kiểm thử metric, span và dữ liệu che bằng registry hoặc exporter thử nghiệm

Custom observability chỉ đáng tin khi có thể kiểm thử. Một Observation có thể ghi Timer với tags sai, một span có thể mất parent context, một metric có thể vô tình mang case ID làm label, hoặc một HTTP instrumentation có thể export API key trong header. Những lỗi này thường không làm unit test nghiệp vụ thất bại, nhưng khiến dashboard sai số liệu hoặc làm lộ dữ liệu khi telemetry rời process.

Bài học thuộc chương **Quan sát tùy chỉnh** của module `SPRING_AI_EVALUATION_OBSERVABILITY`. Module đánh giá chất lượng ứng dụng Spring AI bằng dataset, relevance, fact checking và kiểm thử RAG/tool calling; đồng thời đo metrics, traces, chi phí và độ trễ để phát hiện suy giảm qua các phiên bản prompt, model và pipeline. Vì vậy, test observability cần xác minh cả kỹ thuật ghi nhận lẫn ý nghĩa dữ liệu: số logical calls, số dependency attempts, token usage, verdict, trace relationships và privacy.

Sau bài học, bạn có thể:

- Dùng `SimpleMeterRegistry` và Observation handlers để kiểm thử metrics.
- Dùng `TestObservationRegistry` để kiểm tra Observation lifecycle và metadata.
- Dùng OpenTelemetry SDK cùng `InMemorySpanExporter` để kiểm thử span data.
- Xác minh low-cardinality values đi vào metrics và high-cardinality details chỉ nằm ở traces.
- Kiểm tra trace ID, parent span ID, span kind, status, attributes và events.
- Kiểm tra redaction/allowlist bằng canary secrets trước khi telemetry được export.
- Phân biệt unit tests, integration tests và smoke tests chạy cùng Java agent/Collector.
- Phát hiện duplicate instrumentation, cardinality explosion và metric double counting.

## 1. Vì sao phải test observability như một hợp đồng?

Một bài test business có thể xác nhận API trả đúng answer, nhưng không chứng minh:

- Một logical request chỉ tăng request counter một lần.
- Mỗi outbound model request có đúng một client span.
- Child spans giữ đúng trace ID và parent ID.
- Prompt version được ghi ở trace nhưng không tạo metric series vô hạn.
- Raw prompt, tool arguments, API key hoặc email không xuất hiện trong telemetry.
- Evaluation PASS/FAIL được tách khỏi span status ERROR.
- Tracing sampler không làm giảm metrics hoặc evaluation result count.

Vì vậy, test observability cần kiểm tra **contract** của telemetry, không chỉ kiểm tra code có gọi API instrumentation.

### 1.1. Các lớp cần kiểm thử

| Lớp | Dữ liệu cần xác minh | Công cụ thử nghiệm |
|---|---|---|
| Observation API | Name, lifecycle, key-values, error state | `TestObservationRegistry` |
| Metrics handler | Timer, Counter, tags, count | `SimpleMeterRegistry` |
| Tracing bridge/SDK | Span name, parent, status, attributes | In-memory span exporter |
| Redaction/allowlist | Không có secret/raw content | Exported data assertions |
| Collector pipeline | Transform, filtering, routing, export | Collector integration test |
| Java agent | Auto-instrumentation boundaries | Forked JVM với `-javaagent` |
| Production behavior | Cardinality, drops, sampling, latency | Staging smoke/load test |

### 1.2. Không dùng một test thay cho mọi lớp

- Unit test Observation handler nhanh và cô lập, nhưng không chứng minh Java agent đã instrument đúng thư viện.
- In-memory exporter xác minh SpanData trong SDK test, nhưng không chứng minh Collector redaction config đang chạy.
- Collector integration test xác minh dữ liệu sau pipeline, nhưng không thay thế test business result.
- Production metrics xác minh traffic thật, nhưng không đủ để phát hiện mọi privacy leak ở từng span.

Kết hợp các mức test theo rủi ro và ownership của telemetry.

## 2. Chuẩn bị test dependencies và registry

Ví dụ trong bài dùng các API Micrometer và OpenTelemetry phổ biến. Phiên bản dependency phải đồng bộ với Spring Boot/Spring AI của dự án. Không thêm một SDK production độc lập chỉ để chạy test; test fixture có thể tạo registry/exporter riêng trong test scope.

### 2.1. Micrometer test dependencies

Với Gradle, các dependency thường cần trong test scope:

```kotlin
dependencies {
    testImplementation("io.micrometer:micrometer-observation-test")
    testImplementation("io.micrometer:micrometer-core")
}
```

`micrometer-observation-test` cung cấp `TestObservationRegistry` và assertion helpers ở các phiên bản hỗ trợ. `SimpleMeterRegistry` nằm trong Micrometer core. Nếu Spring Boot dependency management đã quản lý version, không pin một version khác tùy tiện.

### 2.2. OpenTelemetry SDK testing

Để kiểm tra spans bằng exporter trong bộ nhớ:

```kotlin
dependencies {
    testImplementation("io.opentelemetry:opentelemetry-api")
    testImplementation("io.opentelemetry:opentelemetry-sdk")
    testImplementation("io.opentelemetry:opentelemetry-sdk-testing")
}
```

`opentelemetry-sdk-testing` cung cấp `InMemorySpanExporter` trong các phiên bản SDK tương ứng. Dùng cùng version family với OTel API/SDK của ứng dụng.

### 2.3. Tạo test registry tường minh

Không cần Spring context cho mọi unit test. Có thể tạo registry trực tiếp:

```java
SimpleMeterRegistry meters = new SimpleMeterRegistry();
ObservationRegistry observations = ObservationRegistry.create();
observations.observationConfig().observationHandler(
        new DefaultMeterObservationHandler(meters));
```

Khi test qua Spring Boot, có thể inject `ObservationRegistry` và `MeterRegistry` từ application context để xác minh auto-configuration thật. Hai cách kiểm tra hai điều khác nhau:

- Registry tự tạo: kiểm tra semantics của code instrumentation.
- Registry trong Spring context: kiểm tra wiring, handlers, filters và properties của ứng dụng.

### 2.4. Một test phải biết mình đang kiểm tra handler nào

Observation có thể được xử lý bởi nhiều handlers. Nếu chỉ tạo `ObservationRegistry` mà không gắn metrics/tracing handler, việc gọi `observe()` không tự tạo Timer hoặc span. Khi assertion thất bại, xác định registry đang có handler nào trước khi kết luận code instrumentation sai.

## 3. Kiểm thử Observation lifecycle bằng TestObservationRegistry

`TestObservationRegistry` giúp kiểm tra Observation được bắt đầu, mở scope, ghi events và kết thúc như mong đợi. Assertion API cụ thể có thể khác giữa các Micrometer releases; khóa dependency version và tham khảo API tương ứng.

### 3.1. Tạo một Observation đơn giản

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.tck.TestObservationRegistry;
import io.micrometer.observation.tck.TestObservationRegistryAssert;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class AnswerObservationTest {

    @Test
    void recordsAnswerObservation() {
        TestObservationRegistry registry =
                TestObservationRegistry.create();

        Observation.createNotStarted("app.ai.answer", registry)
                .lowCardinalityKeyValue(
                        "app.ai.feature", "policy_assistant")
                .lowCardinalityKeyValue(
                        "app.ai.mode", "rag")
                .observe(() -> {
                    // Execute a deterministic fake pipeline.
                });

        TestObservationRegistryAssert.assertThat(registry)
                .hasObservationWithNameEqualTo("app.ai.answer");
    }
}
```

Imports/assertion methods trong ví dụ phản ánh API thường gặp của `micrometer-observation-test`; nếu phiên bản đang khóa có package hoặc fluent assertion khác, điều chỉnh theo Javadoc của chính version đó. Ý nghĩa cần kiểm tra vẫn là observation name và lifecycle.

### 3.2. Kiểm tra error lifecycle

Cho fake operation ném exception có kiểm soát:

```java
Observation.createNotStarted("app.ai.tool.execute", registry)
        .lowCardinalityKeyValue(
                "app.ai.tool.name", "getOrderStatus")
        .observe(() -> {
            throw new IllegalStateException("simulated failure");
        });
```

Test cần xác minh:

- Observation được kết thúc dù callback ném exception.
- Error được chuyển đến handlers theo API/lifecycle.
- Tool outcome được phân loại là `error`.
- Không đưa raw exception message vào attributes nếu message có thể chứa dữ liệu nhạy cảm.

Đừng chỉ assert exception được ném ra; kiểm tra Observation lifecycle và dữ liệu được handler nhận.

### 3.3. Kiểm tra scope và context

Nếu custom code dùng `observation.openScope()`:

- Scope phải được đóng trong `try-with-resources`.
- Current observation phải được khôi phục sau khi scope đóng.
- Exception không được làm rò current context sang operation tiếp theo.
- Async task cần context propagation đúng cơ chế, không dựa vào ThreadLocal tự quản lý thiếu cleanup.

Với async integration, kiểm tra bằng test chạy trên executor thực tế của ứng dụng.

## 4. Kiểm thử metrics bằng SimpleMeterRegistry

Metrics test nên xác minh cả **giá trị đo** và **schema của tags**. Một Timer đúng count nhưng mang `caseId` làm tag vẫn là một lỗi observability nghiêm trọng.

### 4.1. Gắn Observation với MeterRegistry

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;

import static org.assertj.core.api.Assertions.assertThat;

class AnswerMetricTest {

    @Test
    void recordsOneTimerWithLowCardinalityTags() {
        MeterRegistry meters = new SimpleMeterRegistry();
        ObservationRegistry observations = ObservationRegistry.create();
        observations.observationConfig().observationHandler(
                new DefaultMeterObservationHandler(meters));

        Observation.createNotStarted("app.ai.answer", observations)
                .lowCardinalityKeyValue(
                        "app.ai.feature", "policy_assistant")
                .lowCardinalityKeyValue(
                        "app.ai.mode", "rag")
                .highCardinalityKeyValue(
                        "app.ai.evaluation.case_id", "case-017")
                .observe(() -> {
                    // Deterministic work; do not sleep in this test.
                });

        var timer = meters.find("app.ai.answer")
                .tag("app.ai.feature", "policy_assistant")
                .tag("app.ai.mode", "rag")
                .timer();

        assertThat(timer).isNotNull();
        assertThat(timer.count()).isEqualTo(1);
        assertThat(timer.getId().getTags())
                .noneMatch(tag ->
                        tag.getKey().contains("case_id"));
    }
}
```

Import `DefaultMeterObservationHandler` nằm trong Micrometer core ở các version hỗ trợ. Tên timer và tag mapping phụ thuộc Observation convention/config; test nên kiểm tra metric name/tag contract của ứng dụng đang dùng. Không dùng `Thread.sleep` để kiểm tra duration; nếu cần kiểm tra timing, inject clock hoặc chỉ assert count/tags trong unit test.

### 4.2. Kiểm tra Counter cho outcome

Nếu ứng dụng tự ghi Counter:

```java
Counter.builder("app.ai.evaluation.cases")
        .tag("verdict", "PASS")
        .tag("feature", "policy_assistant")
        .register(meters)
        .increment();

assertThat(meters.get("app.ai.evaluation.cases")
        .tag("verdict", "PASS")
        .counter()
        .count()).isEqualTo(1.0);
```

Đây là metric tổng hợp. Không thêm run ID, case ID, trace ID, prompt text hoặc document ID vào tags.

### 4.3. Kiểm tra metric count độc lập trace sampling

Trong test application context, gửi nhiều requests qua instrumentation thật và cấu hình tracing sampler drop spans (nếu test harness hỗ trợ). Counter/Timer vẫn phải ghi nhận mọi logical operation theo semantics của metric handler.

Không suy ra metrics từ số spans export. Metrics handler và tracing handler là hai consumers khác nhau của Observation.

### 4.4. Kiểm tra tag allowlist

Có thể duyệt `MeterRegistry.getMeters()` và assert:

- Chỉ có tag keys được phép.
- Tag values thuộc tập enum/allowlist.
- Không có `trace_id`, `case_id`, `user_id`, raw query hoặc email.
- Số Meter IDs không tăng theo số request/case.

Đây là cách phát hiện cardinality leak ngay trong test.

## 5. Kiểm thử span bằng OpenTelemetry InMemorySpanExporter

Metrics test xác minh Timer/Counter; span test cần quan sát SpanData sau khi span kết thúc. `InMemorySpanExporter` thu spans trong bộ nhớ, không cần chạy Collector hoặc backend.

### 5.1. Tạo SDK test độc lập

```java
import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;
import io.opentelemetry.sdk.OpenTelemetrySdk;
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import io.opentelemetry.sdk.trace.data.SpanData;
import io.opentelemetry.sdk.trace.samplers.Sampler;
import io.opentelemetry.sdk.trace.export.SimpleSpanProcessor;
import io.opentelemetry.sdk.testing.exporter.InMemorySpanExporter;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class SpanExportTest {

    @Test
    void exportsParentAndChildSpans() {
        InMemorySpanExporter exporter =
                InMemorySpanExporter.create();
        SdkTracerProvider provider = SdkTracerProvider.builder()
                .setSampler(Sampler.alwaysOn())
                .addSpanProcessor(SimpleSpanProcessor.create(exporter))
                .build();
        OpenTelemetry openTelemetry = OpenTelemetrySdk.builder()
                .setTracerProvider(provider)
                .build();
        Tracer tracer = openTelemetry.getTracer("answer-test");

        Span parent = tracer.spanBuilder("app.ai.answer")
                .setSpanKind(SpanKind.INTERNAL)
                .startSpan();
        String parentSpanId = parent.getSpanContext().getSpanId();
        String traceId = parent.getSpanContext().getTraceId();

        try (Scope ignored = parent.makeCurrent()) {
            Span child = tracer.spanBuilder("app.ai.model.generate")
                    .startSpan();
            child.setAttribute("app.ai.prompt.version", "answer-v7");
            child.end();
        } finally {
            parent.end();
        }

        List<SpanData> spans = exporter.getFinishedSpanItems();
        assertThat(spans).hasSize(2);

        SpanData childData = spans.stream()
                .filter(span -> span.getName()
                        .equals("app.ai.model.generate"))
                .findFirst()
                .orElseThrow();

        assertThat(childData.getSpanContext().getTraceId())
                .isEqualTo(traceId);
        assertThat(childData.getParentSpanContext().getSpanId())
                .isEqualTo(parentSpanId);
        assertThat(childData.getAttributes().get(
                io.opentelemetry.api.common.AttributeKey.stringKey(
                        "app.ai.prompt.version")))
                .isEqualTo("answer-v7");

        provider.close();
    }
}
```

Đây là SDK test riêng để minh họa API OTel. Trong ứng dụng dùng Micrometer Tracing bridge hoặc Java agent, test tích hợp phải lấy spans từ đúng provider/bridge mà process đang sử dụng; không khởi tạo SDK test song song rồi kết luận agent đã được kiểm tra.

### 5.2. Luôn dùng sampler deterministic trong unit test

`Sampler.alwaysOn()` giúp test không phụ thuộc xác suất sampling. Nếu dùng ratio sampler ngẫu nhiên, test có thể chập chờn dù code không đổi. Test sampling policy nên có suite riêng để kiểm tra decision logic.

### 5.3. Kiểm tra span kind, status và events

Ngoài name và parent:

- Span kind: SERVER, CLIENT, INTERNAL, PRODUCER hoặc CONSUMER theo operation.
- Status: UNSET/OK/ERROR theo semantics.
- Attributes: key, type và value.
- Events: tên event và attributes.
- Links: context được liên kết.
- Resource: service name/version/environment.

Một HTTP client span không nên bị ghi thành SERVER; một answer quality FAIL không tự động biến model generation span thành ERROR.

## 6. Kiểm tra low/high cardinality bằng cả metrics và traces

Trong Micrometer Observation, low-cardinality key-values có thể được dùng cho metrics và traces; high-cardinality key-values dành cho trace detail. Đây là điểm quan trọng khi kiểm thử prompt/case metadata.

### 6.1. Một Observation, hai loại metadata

```java
Observation.createNotStarted("app.ai.evaluation.case", observations)
        .lowCardinalityKeyValue(
                "app.ai.feature", "policy_assistant")
        .lowCardinalityKeyValue(
                "app.ai.evaluation.verdict", "PASS")
        .highCardinalityKeyValue(
                "app.ai.evaluation.case_id", "case-017")
        .highCardinalityKeyValue(
                "app.ai.prompt.version", "answer-v7")
        .observe(() -> evaluator.evaluate(testCase));
```

Contract cần kiểm tra:

| Field | Metrics | Trace |
|---|---:|---:|
| Feature | Có thể có | Có |
| Verdict enum | Có thể có | Có |
| Case ID | Không | Có thể có theo privacy policy |
| Prompt version | Chỉ khi version set được giới hạn rõ | Có thể có |
| Raw prompt/answer | Không | Không mặc định |

Không đưa high-cardinality values vào metrics tags chỉ để tiện filter. Nếu cần trend theo prompt version, dùng một tập variant/version có giới hạn và ngân sách series rõ ràng.

### 6.2. Kiểm thử cardinality không tăng theo case count

Chạy 100 hoặc 1.000 case IDs khác nhau với cùng low-cardinality tags:

- Metric series cho feature/verdict vẫn nằm trong tập dự kiến.
- Không có meter tag chứa case ID.
- Span có thể chứa case ID opaque nếu được phép.
- Tổng số spans tăng theo số operations được test là bình thường; metric series không nên tăng theo từng case.

Ví dụ assertion ở mức ý tưởng:

```text
assert meterSeriesCount == expectedFeatureVerdictCombinations
assert noMetricTagKey("case_id")
assert traceFor("case-017") contains caseId when policy allows
assert traceFor("case-018") contains caseId when policy allows
```

Không hardcode một con số series chung cho mọi registry/backend; tính từ tập tag combinations được phép trong test.

### 6.3. Cardinality và privacy là hai kiểm tra khác nhau

Một opaque case ID có thể không nhận diện cá nhân nhưng vẫn tạo cardinality cao. Ngược lại, một tag `feature=policy_assistant` có cardinality thấp nhưng có thể là dữ liệu nội bộ nhạy cảm tùy hệ thống. Test cần có cả allowlist key/value và privacy policy.

## 7. Kiểm thử redaction và dữ liệu không được export

Redaction test nên dùng **canary values** giả, duy nhất và dễ tìm. Không dùng secret thật trong test.

### 7.1. Tạo canary values

Ví dụ:

```text
question = "CANARY_PROMPT_7f31"
toolArgument = "CANARY_TOOL_ARG_2a90"
apiKey = "CANARY_API_KEY_91bc"
email = "canary-user-4d21@example.invalid"
sqlValue = "CANARY_SQL_VALUE_0e42"
```

Gửi canary qua các input paths có nguy cơ bị ghi:

- User prompt và conversation metadata.
- Retrieved document content.
- Tool arguments/result.
- HTTP authorization/header.
- SQL parameters.
- Exception message.

Sau khi request chạy, kiểm tra telemetry đã export ở các lớp liên quan.

### 7.2. Kiểm tra attributes, events, links và resource

Không chỉ kiểm tra span attributes. Canary có thể xuất hiện trong:

- Span name.
- Span attributes.
- Event names/attributes.
- Link attributes.
- Resource attributes.
- Status description/exception event.
- Metric tag values.
- Log message/structured fields.

Một assertion chỉ xem `span.getAttributes()` có thể bỏ sót leak trong exception event hoặc log. Viết helper thu thập toàn bộ fields được phép quan sát trong test.

### 7.3. Allowlist tốt hơn blacklist

Nếu instrumentation chỉ thêm các keys đã được cho phép, một dependency mới khó vô tình export toàn bộ request. Blacklist thường bỏ sót key mới khi library upgrade.

Ví dụ allowlist:

```text
ALLOWED_SPAN_ATTRIBUTES:
  - app.ai.feature
  - app.ai.mode
  - app.ai.prompt.version
  - gen_ai.provider.name
  - gen_ai.request.model
  - app.rag.search.top_k
  - app.ai.tool.name
  - error.type

FORBIDDEN:
  - raw.prompt
  - raw.answer
  - authorization
  - cookie
  - user.email
  - tool.arguments
  - sql.bind.parameters
```

Danh sách thực tế cần theo data classification và semantic conventions của ứng dụng. Allowlist không nên vô tình loại bỏ các attributes chuẩn cần thiết cho diagnostics; review mỗi khi thêm instrumentation.

### 7.4. Kiểm tra dữ liệu ở exporter boundary

Với SDK in-memory exporter, kiểm tra `SpanData` sau khi span kết thúc. Nếu redaction được triển khai ở custom exporter wrapper, test chính wrapper đó và xác nhận payload được chuyển tiếp đã sanitized.

Nếu redaction nằm ở Collector processor, unit test SDK exporter chưa đủ. Phải gửi telemetry qua Collector test pipeline và kiểm tra output sau processor, vì dữ liệu nhạy cảm có thể đã rời process trước khi được redact.

### 7.5. Đừng coi UI masking là redaction

Backend UI có thể ẩn một field nhưng raw value vẫn được lưu và truy vấn qua API. Test phải kiểm tra payload ở điểm export hoặc dữ liệu đầu ra sau collector/backend test, không chỉ chụp màn hình UI.

## 8. Kiểm thử status, events và exception data của span

Một span có thể hoàn tất bình thường về kỹ thuật dù answer không đạt rubric. Ngược lại, timeout của judge là lỗi vận hành dù answer trước đó có thể đúng. Test cần xác minh semantics của status và event.

### 8.1. Kiểm tra ERROR status

Ví dụ tạo một child span lỗi trong test SDK:

```java
import io.opentelemetry.api.trace.StatusCode;

Span toolSpan = tracer.spanBuilder("app.ai.tool.execute")
        .startSpan();
try {
    toolSpan.setAttribute("app.ai.tool.name", "getOrderStatus");
    throw new IllegalStateException("simulated dependency failure");
} catch (RuntimeException error) {
    toolSpan.setAttribute("error.type", "dependency_unavailable");
    toolSpan.setStatus(StatusCode.ERROR);
    toolSpan.addEvent("tool_execution_failed");
} finally {
    toolSpan.end();
}
```

Test cần assert:

- Status code là ERROR.
- `error.type` là enum đã chuẩn hóa.
- Event có tên ổn định.
- Không có raw tool arguments hoặc exception message nhạy cảm.

Không ghi cùng một exception thành status description, event attribute và custom attribute nếu chỉ lặp nội dung. Giữ đủ dữ liệu chẩn đoán nhưng tránh payload dư thừa.

### 8.2. Quality verdict không phải span status

Ví dụ answer được sinh thành công nhưng evaluator chấm FAIL:

| Operation | Span status | Evaluation verdict |
|---|---|---|
| Model generation thành công | UNSET/OK theo convention | Chưa có |
| Judge chạy xong, answer không grounded | Judge operation thành công | FAIL |
| Judge timeout | Judge span ERROR | Không có verdict hợp lệ / ERROR |
| Judge output sai schema | Validation operation error hoặc invalid | INVALID |

Test phải ngăn code đặt model span ERROR chỉ vì evaluation verdict FAIL. Tương tự, không được gán verdict FAIL khi judge timeout hoặc output INVALID.

### 8.3. Kiểm tra event và exception recording

Nếu instrumentation dùng `recordException`, kiểm tra event exception không chứa secret/canary. Exception message và stack trace có thể chứa:

- URL có query parameters.
- SQL và bind values.
- Prompt fragment.
- Tool arguments.
- Header hoặc token.

Chỉ ghi exception data sau khi có redaction/allowlist phù hợp. Với lỗi cần điều tra sâu, lưu sanitized error type và tham chiếu tới artifact bảo vệ thay vì raw payload.

## 9. Kiểm thử redaction ở Collector

Nếu redaction được triển khai ở OpenTelemetry Collector, test cần gửi telemetry qua cùng processor chain như môi trường thật. Một in-memory exporter trong application chỉ cho biết dữ liệu đã rời process như thế nào; nó không chứng minh Collector đã loại bỏ fields.

### 9.1. Pipeline test tối thiểu

```text
Test application
  |
  | OTLP traces + metrics
  v
Test Collector
  ├── receiver
  ├── redaction/transform processor
  ├── batch (nếu production dùng)
  └── test exporter / capture sink
          |
          v
Assertions:
  - allowed attributes remain
  - canary secrets are absent
  - trace and parent IDs are preserved
  - expected spans are still present
```

### 9.2. Test trước và sau processor

Gửi một span có:

- Attribute được phép `app.ai.feature=policy_assistant`.
- Canary secret ở field bị cấm.
- Event chứa một canary khác.
- Resource attributes hợp lệ.

Xác minh:

1. Test input xác nhận canary có mặt trước processor để chứng minh test thực sự tạo tình huống.
2. Output sau processor không còn canary ở span attributes/events/links theo policy.
3. Allowed fields vẫn tồn tại.
4. Span name, trace ID, parent span ID và timestamps vẫn đúng.
5. Không có processor nào vô tình drop toàn bộ span để làm test “pass”.

### 9.3. Kiểm tra metrics và logs riêng

Redaction processor cho traces không tự động bảo vệ metrics hoặc logs. Nếu Collector có pipeline riêng:

- Test metric labels/attributes ở metrics pipeline.
- Test log body/attributes ở logs pipeline.
- Kiểm tra exporter và routing từng signal.
- Xác minh canary không xuất hiện ở bất kỳ output nào.

Một secret bị loại khỏi trace nhưng vẫn có trong log hoặc metric label vẫn là privacy leak.

### 9.4. Kiểm tra cấu hình Collector bị lỗi

Test nên fail nếu:

- Processor redaction không được gắn vào pipeline.
- Config option không được version hiện tại nhận diện.
- Pipeline export bypass processor.
- Output exporter nhận dữ liệu thô.
- Processor drop cả span hợp lệ thay vì chỉ field nhạy cảm.

Kiểm tra startup/config validation của Collector trong integration test. Không chỉ kiểm tra file YAML tồn tại.

## 10. Kiểm thử Java agent và auto-instrumentation

Unit test dùng SDK do test tạo không kiểm tra bytecode instrumentation của Java agent. Agent phải được nạp khi JVM khởi động, vì vậy cần một integration/smoke test chạy trong process riêng có `-javaagent`.

### 10.1. Chạy test JVM với agent

Trong build/test harness:

1. Pin agent artifact/version.
2. Khởi động test application trong forked JVM với `-javaagent:<path-to-agent>`.
3. Đặt sampler deterministic trong test (ví dụ always-on).
4. Trỏ OTLP endpoint tới Collector test hoặc receiver capture.
5. Gửi một HTTP request qua server test.
6. Gọi HTTP client, JDBC hoặc messaging operation mà agent hỗ trợ.
7. Thu output và assert span boundary/parent relation.

Không cố attach agent vào JVM đang chạy nếu agent không hỗ trợ dynamic attach cho mục đích đó. Không dùng test SDK độc lập làm bằng chứng agent đã hoạt động.

### 10.2. Assertions cho agent spans

Với một inbound request:

- Có đúng một server span cho boundary đã chọn.
- Client span tương ứng với số outbound requests thực tế.
- DB span tương ứng với số database operations thực tế.
- Trace context được propagate qua downstream service.
- Instrumentation scope cho biết agent/library tạo span.
- Không có duplicate spans từ Micrometer/custom instrumentation.

### 10.3. Kiểm tra agent options

Nếu test tắt một instrumentation cụ thể:

- Xác nhận startup diagnostics cho biết module đó disabled.
- Xác nhận span tương ứng không còn.
- Xác nhận các instrumentations khác vẫn hoạt động.
- Xác nhận propagation vẫn còn nếu HTTP client boundary khác sở hữu inject/extract.
- Xác nhận metrics không bị mất ngoài dự kiến.

Không chỉ assert biến môi trường đã được set; kiểm tra hành vi thực tế của agent.

### 10.4. Test upgrade

Khi nâng Java agent hoặc Spring Boot:

- Chạy cùng smoke request trước/sau.
- So span count theo operation.
- So instrumentation scopes và attributes.
- So request counts ở mock server/database fixture.
- So metric IDs/tags và collector drops.
- Kiểm tra canary secrets vẫn được loại bỏ.

## 11. Kiểm thử trong Spring Boot application context

Unit tests với registry tự tạo không xác minh auto-configuration. Một integration test nên chạy cùng Spring Boot context, inject registry thật và gọi endpoint hoặc service qua wiring thực tế.

### 11.1. Kiểm tra ObservationRegistry và MeterRegistry được cấu hình

Ví dụ skeleton:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.observation.ObservationRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.actuate.observability.AutoConfigureObservability;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureObservability
class AnswerObservabilityIntegrationTest {

    @Autowired MockMvc mockMvc;
    @Autowired MeterRegistry meters;
    @Autowired ObservationRegistry observations;

    @Test
    void requestRecordsMetricsAndUsesConfiguredRegistry()
            throws Exception {
        assertThat(observations).isNotNull();
        assertThat(meters).isNotNull();

        mockMvc.perform(post("/api/answers")
                        .contentType("application/json")
                        .content("""
                                {"question":"What is the policy?","mode":"rag"}
                                """))
                .andExpect(status().isOk());

        var requestTimer = meters.find("http.server.requests").timer();
        assertThat(requestTimer).isNotNull();
        assertThat(requestTimer.count()).isEqualTo(1);
    }
}
```

Đây là skeleton cần điều chỉnh theo endpoint, response, metric name và Spring Boot test version của dự án. `@AutoConfigureObservability` có sẵn trong các Spring Boot versions hỗ trợ observability test auto-configuration; kiểm tra package và hành vi đúng version đang khóa. Fake model/vector store nên được inject để test không gọi provider thật.

### 11.2. Kiểm tra metrics handler vẫn hoạt động khi tracing không export

Trong một profile test:

1. Giữ Observation metrics handler.
2. Cấu hình tracing sampler drop spans hoặc dùng tracing handler test có thể kiểm soát.
3. Gọi endpoint một lần.
4. Assert request Timer và business Counter tăng đúng.
5. Assert trace exporter không nhận span nếu sampler được cấu hình drop.

Test này chứng minh metrics không bị buộc vào trace sampling.

### 11.3. Không assert metric name mù quáng

Metric names có thể khác theo Spring Boot/framework version, convention và registry. Hãy lấy tên thực tế từ contract/dashboard của dự án. Không đổi code production chỉ để test khớp một tên ví dụ trong bài.

### 11.4. Dọn state giữa các tests

`SimpleMeterRegistry` và test registries có thể giữ meters/observations giữa nhiều operations. Mỗi test nên dùng registry riêng hoặc clear/reset state theo API hỗ trợ. Nếu dùng singleton registry trong Spring context, tránh chạy tests song song cùng mutate cùng meters nếu assertion phụ thuộc count tuyệt đối.

## 12. Kiểm thử instrumentation trong Spring AI evaluation flow

Một test thực tế nên đi qua các operation quan trọng nhưng dùng dependencies giả:

```text
POST /api/answers
  app.ai.answer
    app.rag.retrieve
      vectorStore.fakeSearch
    app.ai.model.generate
      fake ChatModel
    app.ai.tool.execute
      fake tool callback

evaluation worker
  app.ai.evaluation.case
    judge.fakeModel
    evaluation.result.persist
```

### 12.1. Fake dependencies để kiểm tra semantics

Fake ChatModel, VectorStore, tool callback và judge giúp test:

- Model call được instrument đúng một lần cho mỗi invocation.
- Vector search ghi topK/hit count đúng.
- Tool span chỉ tồn tại khi callback thực sự chạy.
- Judge timeout tạo operation ERROR nhưng không biến answer verdict thành FAIL.
- Result persistence được gọi đúng số lần.

Không cần gọi provider thật để kiểm tra Observation names/tags hoặc span parentage.

### 12.2. Kiểm tra RAG attributes

Một test retrieval có thể assert:

- Strategy là `semantic` hoặc `hybrid`.
- topK là integer/giá trị được chuẩn hóa theo convention.
- hit count bằng số fake documents trả về.
- index/filter version đúng.
- Raw query và document content không có trong exported attributes.

Nếu source IDs được ghi ở result artifact, test trace không được vô tình thêm chúng vào metric labels.

### 12.3. Kiểm tra model usage

Dùng fake model trả usage metadata xác định:

- Input token count và output token count được ghi một lần.
- Mỗi model turn có invocation span tương ứng.
- Retry HTTP attempts không bị tính thành logical model turns.
- Không có raw prompt/answer trong trace.
- Cost metric dùng giá/version policy đã định nghĩa, không tự suy từ span count.

### 12.4. Kiểm tra tool calling

Test hai tình huống:

1. Policy deny: dispatch span/event có outcome denied; callback và downstream HTTP span không xuất hiện.
2. Policy allow: callback chạy; tool execution span và đúng một downstream client span xuất hiện.

Nếu tool có side effect, test idempotency và duplicate execution riêng với trace assertions.

### 12.5. Kiểm tra evaluation result

Với dataset test nhỏ, xác minh:

- Mỗi case có result record đúng run/case/variant/rubric version.
- PASS/FAIL/INVALID/ERROR được phân loại đúng.
- Judge execution ERROR không được ghi thành quality FAIL.
- Metrics verdict counts đúng số case.
- Trace sampling không làm mất result records.

## 13. Kiểm thử duplicate spans và instrumentation ownership

Khi ứng dụng dùng cả Micrometer và Java agent, test phải xác minh mỗi operation boundary có một owner chính.

### 13.1. Assertions theo boundary

| Boundary | Assertion |
|---|---|
| Inbound HTTP | Một SERVER span cho một request |
| Business answer | Một `app.ai.answer` span |
| Model logical call | Một span logical nếu framework/instrumentation cung cấp |
| Outbound HTTP | Một CLIENT span cho mỗi request thực tế |
| JDBC | Một DB span cho mỗi SQL execution |
| Tool callback | Một execution span cho mỗi callback thực tế |

Các spans cha-con có semantics khác nhau vẫn hợp lệ. Không dùng tổng span count cố định nếu framework version bổ sung spans hữu ích.

### 13.2. Phân biệt duplicate span với retry thật

Một logical model call có hai HTTP attempts vì retry là hai transport requests thực tế, không phải duplicate instrumentation. Để phân biệt:

- Đếm requests tại mock provider.
- Kiểm tra attempt index/retry event.
- So span IDs và instrumentation scopes.
- Xác minh timestamps có biểu diễn hai request liên tiếp hay hai spans overlap cùng request.

### 13.3. Kiểm tra exporter duplicate

Nếu cùng Span ID được backend nhận hai lần:

- Kiểm tra SDK có hai exporters gửi tới cùng backend không.
- Kiểm tra Collector có route/fan-out hai lần không.
- Kiểm tra retry/replay ở ingestion pipeline.
- Kiểm tra backend deduplication behavior.

Test exporter path bằng capture sink có thể giúp xác định dữ liệu đã được gửi qua bao nhiêu tuyến.

## 14. Kiểm thử cardinality và budget

Cardinality nên được test bằng tập dữ liệu có kiểm soát, không chỉ review bằng mắt.

### 14.1. Kiểm tra 100 case IDs

Chạy 100 cases với:

- Cùng feature.
- Cùng operation.
- Cùng một trong vài verdict enums.
- Case IDs khác nhau.
- Prompt versions trong một tập version có giới hạn.

Assert:

- Không có metric tag key chứa `case_id`.
- Meter IDs không tăng theo 100 case IDs.
- Trace detail có thể chứa opaque case ID nếu policy cho phép.
- Không có raw input hoặc user identifier.

### 14.2. Đặt budget theo tag combinations

Nếu metric có 3 features, 4 outcomes và 2 environments, số series lý thuyết tối đa từ ba dimensions này là:

\[
3 \times 4 \times 2 = 24
\]

Đây là phép tính cho tổ hợp dimensions đã nêu, chưa tính histogram buckets, các tags khác hoặc registry-specific series expansion. Test nên tính theo schema thật và giới hạn budget có chủ đích.

### 14.3. Test chống cardinality regression

Sau mỗi lần thêm tag:

1. Cập nhật metric catalog và owner.
2. Thêm allowlist value.
3. Chạy test với nhiều IDs/versions.
4. Assert series count trong budget.
5. Xem xét query/dashboard có thực sự cần dimension đó không.

Không đưa request IDs, trace IDs, case IDs, document IDs hoặc raw model names do user cung cấp vào labels.

## 15. Kiểm tra redaction với helper và log capture

Một test redaction tốt cần tìm canary ở nhiều nơi, thay vì chỉ assert một attribute cụ thể.

### 15.1. Helper kiểm tra SpanData

Ví dụ helper đơn giản để tìm canary trong các phần chính của SpanData:

```java
import io.opentelemetry.sdk.trace.data.SpanData;

static String searchableSpanData(SpanData span) {
    return String.join(" ",
            span.getName(),
            span.getAttributes().toString(),
            span.getEvents().toString(),
            span.getLinks().toString(),
            span.getResource().getAttributes().toString(),
            span.getStatus().getDescription());
}

for (SpanData span : exporter.getFinishedSpanItems()) {
    assertThat(searchableSpanData(span))
            .doesNotContain("CANARY_API_KEY_91bc")
            .doesNotContain("CANARY_PROMPT_7f31")
            .doesNotContain("CANARY_TOOL_ARG_2a90")
            .doesNotContain("CANARY_SQL_VALUE_0e42");
}
```

Đây là helper phục vụ test, không phải sanitizer production. `toString()` chỉ là cách tìm chuỗi thuận tiện trong fixture; nếu cần contract chặt, duyệt từng AttributeKey, event, link và resource field theo type/schema.

### 15.2. Kiểm tra metric tags

Với tất cả Meter IDs:

```java
for (var meter : meters.getMeters()) {
    for (var tag : meter.getId().getTags()) {
        assertThat(tag.getValue())
                .doesNotContain("CANARY_API_KEY_91bc")
                .doesNotContain("canary-user-4d21@example.invalid")
                .doesNotContain("CANARY_PROMPT_7f31");
    }
}
```

Đồng thời kiểm tra tag keys theo allowlist. Canary absence không thay thế allowlist: một dữ liệu nhạy cảm mới có thể không trùng canary đã chọn.

### 15.3. Kiểm tra log bằng appender test

Nếu ứng dụng dùng Logback, có thể gắn `ListAppender` trong test để thu log events:

```java
ListAppender<ILoggingEvent> appender =
        new ListAppender<>();
appender.start();
Logger logger = (Logger) LoggerFactory.getLogger(
        AnswerOrchestrator.class);
logger.addAppender(appender);

// Execute the test request with canary values.

String capturedLogs = appender.list.stream()
        .map(ILoggingEvent::getFormattedMessage)
        .collect(java.util.stream.Collectors.joining("\n"));

assertThat(capturedLogs)
        .doesNotContain("CANARY_API_KEY_91bc")
        .doesNotContain("CANARY_PROMPT_7f31")
        .doesNotContain("CANARY_TOOL_ARG_2a90");
```

Import/package của Logback test appender phụ thuộc logging backend đang dùng. Nếu ứng dụng dùng Log4j2 hoặc backend khác, chọn test appender tương ứng. Kiểm tra cả structured arguments/MDC nếu logger ghi fields ngoài formatted message.

### 15.4. Test exception paths

Canary thường bị lộ trong error paths nhiều hơn success paths. Hãy test:

- HTTP client exception có URL chứa query string.
- SQL exception có thể kèm statement/parameter.
- Tool callback exception chứa arguments.
- Model provider error body có prompt fragment.
- Judge parser exception chứa raw output.

Xác minh exception events, logs và metric labels không chứa payload.

## 16. Kiểm tra custom ObservationConvention và naming

Nếu ứng dụng dùng `ObservationConvention` để đặt tên/metadata, test convention như một hợp đồng riêng.

### 16.1. Những gì cần kiểm tra

- Observation name ổn định theo operation.
- Context được phân loại đúng feature/mode.
- Low-cardinality keys chỉ có giá trị allowlist.
- High-cardinality keys không bị đưa vào metric tags.
- Không ghi version hoặc case ID vào span name.
- Error/outcome mapping đúng semantics.

### 16.2. Không để raw values quyết định span name

Không dùng:

```text
app.ai.answer.user-123
app.ai.answer.prompt-v7
app.ai.answer.query-what-is-policy
```

Nên dùng span name ổn định `app.ai.answer` và attributes có schema riêng. Test có thể tạo nhiều request với raw values khác nhau rồi assert số span names distinct không tăng theo request content.

### 16.3. Kiểm thử custom convention bằng input biến thể

Chạy cùng operation với:

- Hai prompt versions.
- Hai feature modes.
- Nhiều case IDs.
- Input chứa canary secret.

Assert:

- Span name vẫn ổn định.
- Feature/mode tags nằm trong allowlist.
- Case ID chỉ nằm trong trace detail khi được phép.
- Raw input không xuất hiện ở attributes/events/logs.

## 17. Ma trận test observability theo mức độ

Không phải mọi thay đổi cần chạy toàn bộ hệ thống. Chọn test theo phần code và pipeline bị ảnh hưởng.

| Test level | Kiểm tra | Khi nên chạy |
|---|---|---|
| Unit: Observation | Name, lifecycle, tags, error | Mỗi thay đổi custom instrumentation |
| Unit: MeterRegistry | Timer/Counter, tag allowlist, cardinality | Mỗi thay đổi metric |
| Unit: in-memory exporter | Span tree, attributes, status, events | Mỗi thay đổi tracing |
| Unit: redaction helper | Canary absent, allowlist retained | Mỗi thay đổi privacy policy |
| Spring context integration | Auto-config, handlers, actual registries | Thay đổi Spring Boot/Actuator |
| Spring AI integration | ChatClient/RAG/tool/judge spans | Thay đổi Spring AI hoặc pipeline |
| Collector integration | Redaction/transform/routing/export | Thay đổi Collector config |
| Agent smoke test | Servlet/HTTP/JDBC auto-instrumentation | Nâng Java agent hoặc client libraries |
| Staging load test | Cardinality, exporter drops, overhead | Thay đổi sampling/volume/config lớn |

### 17.1. Bộ test tối thiểu cho pull request

Với thay đổi custom Observation:

1. Unit test name và low/high cardinality.
2. Meter test count/tags.
3. Span test parent/attributes/status.
4. Redaction test với canary.

Nếu thay đổi Spring Boot/agent/Collector, bổ sung integration suite tương ứng. Không bắt mọi PR chạy agent container nếu code không đụng instrumentation runtime.

## 18. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Chỉ test business response | Không phát hiện telemetry sai | Test observation/metrics/spans |
| Tạo ObservationRegistry nhưng không gắn handler | Không có Timer/span | Gắn handler hoặc dùng registry của Spring context |
| Dùng registry singleton giữa các tests | Counts bị cộng dồn, test chập chờn | Registry riêng hoặc reset đúng cách |
| Dùng sleep để test duration | Test chậm và flaky | Inject clock/scheduler hoặc chỉ assert lifecycle |
| Test span với sampler ngẫu nhiên | Kết quả chập chờn | Sampler deterministic trong unit test |
| Chỉ kiểm tra span attributes | Bỏ sót event/resource/exception leak | Kiểm tra mọi telemetry fields |
| Chỉ kiểm tra UI đã ẩn dữ liệu | Raw data vẫn được export/lưu | Kiểm tra exporter/Collector output |
| Chỉ test SDK, bỏ qua Collector redaction | Leak ở Collector pipeline không bị phát hiện | Collector integration test |
| Chỉ test SDK, cho rằng Java agent đã hoạt động | Không kiểm tra bytecode instrumentation | Forked JVM với agent |
| Test high-cardinality chỉ bằng một case | Không phát hiện series explosion | Chạy nhiều case IDs/versions |
| Assert tổng span count cố định | Test vỡ khi framework thêm span hợp lệ | Assert theo operation boundary |
| Đếm evaluation từ sampled traces | Sai coverage/pass rate | Result store độc lập sampling |
| Không test exception paths | Secret rò qua exception event/log | Canary trong failure scenarios |
| Dùng blacklist vài key cố định | Dependency mới có thể thêm field nhạy cảm | Allowlist và schema review |
| Không kiểm tra metric tags | Case/user IDs làm nổ cardinality | Tag allowlist và series budget |
| Test Observation nhưng không test Spring context | Bỏ sót wiring/auto-config sai | Integration test theo version |

## 19. Bài thực hành: xây bộ test cho custom observability

**Bối cảnh:** Một Spring AI answer service dùng Spring Boot Actuator, Micrometer Observation, OpenTelemetry exporter, RAG qua VectorStore và tool tra cứu đơn hàng. Evaluation worker chạy judge model bất đồng bộ. Nhóm muốn xác minh metrics, spans và dữ liệu che trước khi rollout.

### Phần A — Metrics

1. Tạo `SimpleMeterRegistry` riêng cho unit test.
2. Gắn `DefaultMeterObservationHandler`.
3. Chạy một answer observation với feature/mode và case ID.
4. Assert Timer count bằng một.
5. Assert case ID không xuất hiện trong meter tags.
6. Chạy 100 case IDs và kiểm tra series count không tăng theo case.

### Phần B — Spans

1. Tạo OTel SDK test với `InMemorySpanExporter`.
2. Dùng sampler always-on.
3. Tạo parent `app.ai.answer` và child `app.ai.model.generate`.
4. Assert trace ID/parent span ID.
5. Assert prompt version và model attributes đúng.
6. Assert model quality FAIL không tự biến span thành ERROR.

### Phần C — Redaction

1. Tạo canary prompt, tool argument, API key, email và SQL value.
2. Đưa canary qua success và failure paths.
3. Thu span attributes/events/links/resource.
4. Thu metric tags và log events.
5. Assert canary không xuất hiện ở output.
6. Nếu Collector chịu trách nhiệm redact, gửi qua test Collector và assert sau processor.

### Phần D — Integration và agent

1. Khởi chạy Spring Boot test context với fake ChatModel/VectorStore/tool.
2. Gọi endpoint một lần và kiểm tra registry thật được dùng.
3. Chạy một smoke JVM với Java agent nếu thay đổi auto-instrumentation.
4. Kiểm tra mỗi HTTP/JDBC boundary chỉ có một instrumentation owner.
5. Kiểm tra context propagation và metrics không bị ảnh hưởng bởi trace sampling.
6. Lưu versions/config để tái lập test.

### Câu hỏi tự kiểm tra

**1. `SimpleMeterRegistry` xác minh điều gì?**  
Nó cho phép kiểm tra Timer, Counter, tags và meter identity trong bộ nhớ. Nó không chứng minh Collector hoặc Prometheus production đang hoạt động.

**2. Vì sao cần `TestObservationRegistry`?**  
Nó giúp quan sát Observation lifecycle và metadata mà không cần backend tracing/metrics thật.

**3. `InMemorySpanExporter` có kiểm tra Java agent không?**  
Không tự động. Nó kiểm tra spans do SDK/provider được test cấu hình. Java agent cần JVM khởi động với `-javaagent` và một capture/export path riêng.

**4. High-cardinality case ID có thể xuất hiện ở đâu?**  
Có thể ở trace detail nếu policy cho phép; không nên là metric tag. Cần kiểm tra cả privacy và cardinality.

**5. Vì sao redaction test phải chạy qua Collector nếu Collector thực hiện redaction?**  
Vì exporter trong process quan sát dữ liệu trước Collector. Chỉ output sau processor mới chứng minh Collector đã loại bỏ field.

**6. Có thể dùng `span.isRecording()` để quyết định có lưu evaluation result không?**  
Không. Trace sampling chỉ điều khiển telemetry. Evaluation result phải được lưu theo run contract, bất kể span có được sample hay không.

## 20. Ghi nhớ

- **Observation test** xác minh operation name, lifecycle, scope, tags và error mapping.
- **SimpleMeterRegistry** kiểm tra Timer/Counter, tag schema và cardinality trong unit tests.
- **TestObservationRegistry** giúp kiểm tra Observation mà không cần backend.
- **InMemorySpanExporter** cho phép assert SpanData, parent-child, attributes, events, status và resource.
- **Low-cardinality values** có thể đi vào metrics; **high-cardinality values** chỉ nên nằm ở traces theo policy.
- **Redaction tests** cần canary values và kiểm tra span name/attributes/events/links/resource, metric tags và logs.
- **Collector redaction** cần integration test sau processor; test SDK không đủ.
- **Java agent** cần smoke test trong forked JVM có agent, không thể được xác minh bằng SDK test độc lập.
- **Spring Boot context tests** xác minh auto-configuration và handler wiring.
- **Spring AI fake dependencies** giúp kiểm tra RAG/model/tool/judge instrumentation mà không gọi provider thật.
- **Duplicate spans và metrics** cần được kiểm tra theo operation boundary và request counts thực tế.
- **Trace sampling không được thay đổi metrics hoặc evaluation result coverage.**
- **Test cardinality bằng nhiều case IDs/versions** và kiểm tra series budget.
- **Test privacy trên failure paths** vì exception/event/log có thể chứa dữ liệu nhạy cảm.

Kiểm thử metric, span và dữ liệu che bằng registry hoặc exporter thử nghiệm giúp custom observability trở thành hợp đồng có thể xác minh. Khi registry, exporter, Collector và Java agent được kiểm tra ở đúng tầng, nhóm phát triển có thể tin vào request counts, latency, token/cost, trace relationships và evaluation provenance mà không vô tình tạo cardinality explosion hoặc đưa prompt, tool arguments và secrets vào telemetry.
