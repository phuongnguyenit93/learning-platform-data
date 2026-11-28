# Kiểm thử trace correlation

## 1. Vì sao cần kiểm thử trace correlation?

Trong ứng dụng Spring Boot sử dụng **Spring Modulith**, một request có thể đi qua nhiều application module. Ví dụ, module **orders** nhận yêu cầu tạo đơn hàng, gọi component công khai của **inventory**, phát event để **notifications** gửi thông báo, rồi gọi **payments** để xử lý thanh toán. Khi có lỗi, nhóm vận hành cần biết các bước đó thuộc cùng một hành trình hay đang tạo ra những trace rời rạc.

**Trace correlation** là khả năng liên kết các span và log thuộc cùng một hành trình xử lý. Khi một request đi qua nhiều module hoặc service, trace ID được giữ xuyên suốt context đã propagate; mỗi span có span ID riêng để xác định công việc cụ thể. Log trong phạm vi span có thể mang trace ID và span ID qua MDC, giúp tìm từ log sang trace backend.

Chỉ nhìn thấy trace ID trong một log line chưa đủ chứng minh correlation hoạt động đúng. Cần kiểm tra các ranh giới thực tế: request HTTP đi vào ứng dụng, lời gọi HTTP đi ra, module entry observation, event listener, executor bất đồng bộ và logging context.

Bài **“Kiểm thử trace correlation”** thuộc chương **Kiểm thử** của module **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Module này dùng Spring Modulith để sinh tài liệu ranh giới application module và quan sát tương tác giữa các phần trong ứng dụng Spring Boot. Bài học tập trung vào cách kiểm tra trace context qua các ranh giới đó bằng integration test có thể lặp lại.

Sau bài học, bạn có thể:

- Phân biệt trace ID, span ID, parent span và correlation ID.
- Kiểm tra ứng dụng nhận W3C Trace Context từ HTTP request.
- Kiểm tra trace context được inject vào HTTP client request.
- Xác nhận MDC có trace ID/span ID trong đúng scope và được khôi phục sau khi scope đóng.
- Kiểm tra module entry spans của Spring Modulith bằng dữ liệu span được ghi nhận.
- Kiểm thử context propagation qua executor và event listener.
- Thiết kế test không phụ thuộc ID ngẫu nhiên hoặc thứ tự export span.
- Phân biệt lỗi propagation, sampling, logging pattern và exporter.

## 2. Trace correlation gồm những gì?

Một trace có thể chứa nhiều span. Trace ID nhận diện toàn bộ trace; span ID nhận diện một span cụ thể. Một span con thường giữ cùng trace ID với span cha nhưng có span ID khác.

| Thành phần | Vai trò | Điều cần kiểm thử |
| --- | --- | --- |
| traceId | Nhóm các span trong một trace | Giữ nguyên khi context được propagate |
| spanId | Nhận diện span hiện hành | Khác nhau giữa các span độc lập |
| parent span ID | Liên kết span con với span cha | Span con có quan hệ cha/con đúng |
| traceparent | Header W3C truyền trace context qua HTTP | Header được extract/inject đúng |
| MDC | Ngữ cảnh key-value cho logging | ID hiện diện trong span scope và được khôi phục |
| Correlation ID | Format log ghép trace ID và span ID | Log pattern hiển thị đúng các MDC key |
| Baggage | Dữ liệu ngữ cảnh tùy chọn được propagate | Chỉ truyền các key được cho phép và cần thiết |

### 2.1. Ví dụ trace qua các module

Một request tạo đơn hàng có thể tạo hành trình như sau:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant O as orders
    participant I as inventory
    participant N as notifications
    C->>O: POST /orders
    Note over O: Trace T1, span S1
    O->>I: reserve stock
    Note over I: Trace T1, span S2
    O--)N: OrderPlaced
    Note over N: Trace T1, span S3 nếu context được truyền
~~~

Trong ví dụ:
- T1 là trace ID chung khi các bước thuộc cùng trace.
- S1, S2 và S3 là span ID riêng.
- Lời gọi đồng bộ giữa module có thể tạo span lồng nhau trong cùng trace.
- Listener bất đồng bộ chỉ giữ trace context nếu cơ chế propagation ở ranh giới executor/event transport được cấu hình phù hợp.
- Nếu công việc được thiết kế để bắt đầu trace mới, có thể liên kết hai trace bằng correlation nghiệp vụ hoặc span link theo semantics của hệ thống.

Không nên viết test yêu cầu mọi span luôn có cùng span ID. Điều cần kiểm tra là trace ID và quan hệ parent/child phù hợp với đường đi đã thiết kế.

### 2.2. Trace context khác baggage

Trace context chứa định danh trace/span và cờ sampling theo propagator. Baggage là tập giá trị tùy chọn được truyền kèm context, ví dụ tenant tier hoặc vùng xử lý nếu thật sự cần.

Không dùng baggage để thay thế trace ID, cũng không đưa email, access token, order payload hoặc dữ liệu cá nhân vào baggage. Test trace correlation nên kiểm tra riêng:
- Trace ID có được propagate không?
- Span ID có thay đổi đúng khi tạo span mới không?
- Baggage có được giới hạn theo allowlist không?

## 3. Chuẩn bị tracing cho integration test

Để kiểm thử tracing thực tế, ứng dụng cần Spring Boot Actuator cùng một Micrometer Tracing bridge/tracer tương thích, chẳng hạn OpenTelemetry hoặc Brave. Spring Modulith observability cần được bật nếu bài test kiểm tra module entry spans.

Ví dụ dependency Gradle với Spring Boot 3.5 và OpenTelemetry:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Với Spring Boot phiên bản mới hơn có thể dùng tracing starter do Boot cung cấp. Không thêm nhiều tracer bridge cùng lúc. Hãy quản lý version bằng Spring Boot BOM và chọn đúng starter/bridge cho phiên bản đang dùng.

Trong profile test, cấu hình lấy mẫu 100% để các span được ghi nhận nhất quán:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
    propagation:
      type: w3c
~~~

Giá trị sampling 1.0 chỉ phù hợp với test hoặc môi trường kiểm thử có tải giới hạn. Không copy cấu hình này vào production một cách mặc định vì nó có thể làm tăng chi phí tracing.

Cấu hình W3C giúp các ví dụ dưới đây dùng header traceparent. Nếu ứng dụng sử dụng B3 hoặc propagator khác, đổi header matcher theo cấu hình thực tế.

### 3.1. Chọn cách thu thập span trong test

Để kiểm tra module spans hoặc span hierarchy, test cần một nơi quan sát span đã kết thúc. Có thể chọn:
- OpenTelemetry SDK testing với InMemorySpanExporter.
- Brave test support với TestSpanHandler.
- Một test exporter/collector riêng của tracing backend đang dùng.

Đây là phần phụ thuộc bridge. Không giả định mọi dự án có cùng API exporter. Giữ assertion ở mức ý nghĩa: trace ID, span ID, parent ID, span name và module tags. Không phụ thuộc thứ tự export vì các span có thể kết thúc ở thời điểm khác nhau.

## 4. Kiểm thử extract trace context từ HTTP request

Khi request đi vào Spring Boot web application, instrumentation của server cần đọc trace context từ header và tạo server span mới. Với W3C Trace Context:
- Header traceparent mang trace ID và parent span ID từ client.
- Server span có cùng trace ID.
- Server span có span ID mới, khác parent span ID của client.

Có thể viết một endpoint chỉ tồn tại trong test source để trả về context hiện hành. Endpoint này không nên được đóng gói vào production artifact.

~~~java
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;

@RestController
class TraceProbeController {

    private final Tracer tracer;

    TraceProbeController(Tracer tracer) {
        this.tracer = tracer;
    }

    @GetMapping("/__test/trace")
    Map<String, String> currentTrace() {
        Span span = tracer.currentSpan();

        if (span == null) {
            return Map.of();
        }

        return Map.of(
            "traceId", span.context().traceId(),
            "spanId", span.context().spanId()
        );
    }
}
~~~

Test gửi traceparent có trace ID và parent span ID đã biết:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "management.tracing.sampling.probability=1.0",
        "management.tracing.propagation.type=w3c"
    }
)
@Import(TraceProbeController.class)
class IncomingTraceContextTests {

    @Autowired
    TestRestTemplate http;

    @Test
    void extractsTraceparentFromIncomingRequest() {
        String remoteTraceId = "4bf92f3577b34da6a3ce929d0e0e4736";
        String remoteParentSpanId = "00f067aa0ba902b7";

        HttpHeaders headers = new HttpHeaders();
        headers.set(
            "traceparent",
            "00-" + remoteTraceId + "-" + remoteParentSpanId + "-01"
        );

        ResponseEntity<TraceInfo> response = http.exchange(
            "/__test/trace",
            HttpMethod.GET,
            new HttpEntity<>(headers),
            TraceInfo.class
        );

        assertThat(response.getStatusCode().is2xxSuccessful()).isTrue();
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().traceId()).isEqualTo(remoteTraceId);
        assertThat(response.getBody().spanId()).isNotBlank();
        assertThat(response.getBody().spanId())
            .isNotEqualTo(remoteParentSpanId);
    }

    record TraceInfo(String traceId, String spanId) {}
}
~~~

Đăng ký TraceProbeController trong test context bằng @Import hoặc test configuration phù hợp với cấu trúc dự án. Nếu endpoint probe được đặt trong một class riêng, bảo đảm class chỉ được nạp trong test.

Test trên xác nhận:
1. Server instrumentation đã extract traceparent.
2. Trace ID của server span trùng trace ID gửi vào.
3. Server span có span ID riêng, không dùng lại remote parent span ID.

Không assert span ID cố định vì server tạo ID mới ở mỗi lần chạy.

### 4.1. Kiểm thử request không có traceparent

Một request không có traceparent thường tạo root trace mới khi tracing được bật. Có thể kiểm tra:
- Response probe có trace ID và span ID khác rỗng.
- Trace ID không bằng một giá trị cũ từ request trước.
- Context không bị rò giữa hai request độc lập.

Không yêu cầu ID phải khác nhau theo cách so sánh ngẫu nhiên duy nhất nếu test có thể chạy đồng thời hoặc dùng fixture tùy chỉnh. Tốt hơn là kiểm tra trace scope độc lập bằng exporter và quan hệ parent rõ ràng.

## 5. Kiểm thử inject trace context vào HTTP client

Khi service gọi một service khác, client instrumentation cần tạo client span và inject trace context vào request header. Với Spring Boot, nên dùng builder được auto-configure như RestClient.Builder, RestTemplateBuilder hoặc WebClient.Builder. Tự khởi tạo HTTP client không có observation/tracing integration có thể làm mất propagation.

Ví dụ dùng RestClient.Builder và MockRestServiceServer:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpMethod;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;

import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;

@SpringBootTest(properties = {
    "management.tracing.sampling.probability=1.0",
    "management.tracing.propagation.type=w3c"
})
class OutgoingTraceContextTests {

    @Autowired
    RestClient.Builder autoConfiguredBuilder;

    @Autowired
    Tracer tracer;

    @Test
    void injectsTraceparentIntoOutgoingRequest() {
        RestClient.Builder builder = autoConfiguredBuilder.clone();

        MockRestServiceServer server =
            MockRestServiceServer.bindTo(builder).build();

        RestClient client = builder
            .baseUrl("https://inventory.test")
            .build();

        Span parent = tracer.nextSpan()
            .name("orders.reserve-stock")
            .start();

        try (Tracer.SpanInScope scope = tracer.withSpan(parent)) {
            server.expect(requestTo(
                    "https://inventory.test/reservations"))
                .andExpect(method(HttpMethod.POST))
                .andExpect(request -> {
                    String header = request.getHeaders()
                        .getFirst("traceparent");

                    assertThat(header).isNotBlank();

                    String[] fields = header.split("-");
                    assertThat(fields).hasSize(4);
                    assertThat(fields[0]).isEqualTo("00");
                    assertThat(fields[1])
                        .isEqualTo(parent.context().traceId());
                    assertThat(fields[2])
                        .isNotEqualTo(parent.context().spanId());
                })
                .andRespond(withSuccess());

            client.post()
                .uri("/reservations")
                .retrieve()
                .toBodilessEntity();
        } finally {
            parent.end();
        }

        server.verify();
    }
}
~~~

Test này giả định RestClient.Builder được inject từ Spring Boot auto-configuration và có ObservationRegistry/tracing instrumentation. MockRestServiceServer bind vào builder trước khi build RestClient để quan sát request sau khi interceptor của client đã chạy.

Assertion kiểm tra:
- Header traceparent tồn tại.
- Version W3C là 00.
- Trace ID bằng trace ID của span cha.
- Span ID outbound khác span ID cha vì HTTP client tạo một span mới.

Nếu test nhận được HTTP request nhưng không có traceparent, kiểm tra builder được dùng, ObservationRegistry có được gắn vào client, sampling/propagator và tracer bridge.

## 6. Kiểm thử MDC trong span scope

Spring Boot kết hợp Micrometer Tracing để đưa trace ID và span ID vào MDC khi span hiện hành được kích hoạt. Với cấu hình mặc định, hai key thường là traceId và spanId.

Test sau kiểm tra MDC trong scope và việc khôi phục giá trị sau khi scope đóng:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;

@SpringBootTest
class MdcTraceCorrelationTests {

    @Autowired
    Tracer tracer;

    @Test
    void putsTraceAndSpanIdsIntoMdcWithinScope() {
        String previousTraceId = MDC.get("traceId");
        String previousSpanId = MDC.get("spanId");

        Span span = tracer.nextSpan()
            .name("mdc-correlation-test")
            .start();

        try (Tracer.SpanInScope scope = tracer.withSpan(span)) {
            assertThat(MDC.get("traceId"))
                .isEqualTo(span.context().traceId());
            assertThat(MDC.get("spanId"))
                .isEqualTo(span.context().spanId());
        } finally {
            span.end();
        }

        assertThat(MDC.get("traceId")).isEqualTo(previousTraceId);
        assertThat(MDC.get("spanId")).isEqualTo(previousSpanId);
    }
}
~~~

Nếu ứng dụng tùy chỉnh MDC key, thay traceId/spanId trong assertion theo cấu hình đang dùng. Test này kiểm tra MDC integration, không kiểm tra logging pattern có thực sự in các giá trị đó hay không.

### 6.1. Kiểm tra correlation ID trong log output

Muốn kiểm tra log format, dùng OutputCaptureExtension của Spring Boot Test hoặc log appender dành cho test. Trong một span scope:
1. Ghi một log message có marker duy nhất, ví dụ trace-correlation-probe.
2. Chụp log output.
3. Xác nhận log line có trace ID và span ID mong đợi.
4. Xác nhận pattern không in chuỗi null hoặc key rỗng khi không có active span.

Không so sánh toàn bộ log line vì timestamp, thread name, logger name và format có thể thay đổi theo môi trường. Chỉ assert phần correlation cần bảo vệ.

## 7. Kiểm thử context propagation qua executor

MDC thường gắn với thread. Khi một task chuyển từ request thread sang executor thread, tracing context không tự động được bảo đảm nếu executor không truyền context.

Spring Framework cung cấp ContextPropagatingTaskDecorator để capture và restore context khi task được thực thi. Cấu hình này cần Micrometer Context Propagation và tracing bridge đã đăng ký accessor cho context cần truyền. Ví dụ executor dưới đây nằm trong test source:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.TaskExecutor;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.boot.test.context.TestConfiguration;

@TestConfiguration(proxyBeanMethods = false)
class TraceExecutorConfiguration {

    @Bean
    TaskExecutor traceTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setThreadNamePrefix("trace-test-");
        executor.setTaskDecorator(
            new ContextPropagatingTaskDecorator()
        );
        executor.initialize();
        return executor;
    }
}
~~~

Test có thể mở một parent span trên test thread, submit task, rồi đọc context ở worker:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.task.TaskExecutor;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Import;

import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;

@SpringBootTest
@Import(TraceExecutorConfiguration.class)
class ExecutorTracePropagationTests {

    @Autowired
    @Qualifier("traceTaskExecutor")
    TaskExecutor traceTaskExecutor;

    @Autowired
    Tracer tracer;

    @Test
    void propagatesCurrentTraceToExecutorTask() throws Exception {
        Span parent = tracer.nextSpan()
            .name("parent-operation")
            .start();

        try (Tracer.SpanInScope scope = tracer.withSpan(parent)) {
            CompletableFuture<String> result = new CompletableFuture<>();

            traceTaskExecutor.execute(() -> {
                Span current = tracer.currentSpan();
                result.complete(
                    current == null ? null : current.context().traceId()
                );
            });

            assertThat(result.get(5, TimeUnit.SECONDS))
                .isEqualTo(parent.context().traceId());
        } finally {
            parent.end();
        }
    }
}
~~~

Ví dụ dùng Future/CompletableFuture để chờ task hoàn tất, không dùng Thread.sleep. Trong test thực tế có thể thêm timeout cho result.get để tránh treo pipeline nếu executor không chạy.

Nếu task cần tạo một span con riêng, hãy tạo span mới trong worker và assert trace ID bằng parent nhưng span ID khác. Test trên chỉ xác nhận context hiện hành được truyền qua executor, vì task không tạo span mới.

### 7.1. Kiểm thử trường hợp không propagate

Một negative test có thể dùng executor không có TaskDecorator. Trong task, kiểm tra tracer.currentSpan() không có context được truyền từ parent. Kết quả cụ thể phụ thuộc các accessor và cấu hình context propagation khác trong ứng dụng, vì vậy test phải cô lập executor và xác nhận không có decorator/propagator khác can thiệp.

Không dùng negative test này để kết luận mọi executor trong ứng dụng đều mất context. Chỉ kết luận về executor được cấu hình trong fixture test đó.

## 8. Kiểm thử module entry spans của Spring Modulith

Spring Modulith observability có thể tạo module entry observations/spans khi lời gọi đi qua component API của application module. Span có thể mang metadata nhận diện module, ví dụ:

| Tag | Mục đích |
| --- | --- |
| module.identifier | Technical name của module |
| module.name | Tên hiển thị |
| module.invocation-type | Kiểu invocation, ví dụ bean hoặc event listener |
| module.method | Method được gọi tại module boundary |

Để kiểm thử:
1. Bật Spring Modulith observability và Micrometer Tracing trong test context.
2. Cấu hình sampling 100% cho test.
3. Gọi public API của module orders từ một parent span.
4. Để orders gọi public component của inventory.
5. Thu thập span đã export bằng in-memory exporter phù hợp với tracer bridge.
6. Tìm module entry span có module.identifier tương ứng.
7. Kiểm tra trace ID của module span bằng parent trace ID.
8. Kiểm tra span ID của module span khác parent span ID.
9. Kiểm tra module.method và invocation type nếu version đang dùng export các tag đó.

Không nên assert toàn bộ span list theo thứ tự cố định. Nhiều span có thể kết thúc theo thứ tự khác nhau, đặc biệt khi có async processing. Lọc span theo name và module tags trước khi kiểm tra.

### 8.1. Kiểm thử event listener span

Nếu module notifications lắng nghe event do orders phát:
- Publish event trong một trace đang active.
- Xác nhận listener được gọi và có module entry observation nếu instrumentation hỗ trợ.
- Với synchronous listener, kiểm tra quan hệ trace/span theo execution scope.
- Với asynchronous listener, xác minh cơ chế propagation cụ thể qua executor hoặc message transport.
- Nếu thiết kế tạo trace mới, kiểm tra link/correlation theo semantics đã chọn thay vì ép trace ID phải giống.

Một event publication counter chỉ chứng minh event đã được công bố. Nó không chứng minh listener đã chạy, đã tạo span hoặc đã hoàn thành thành công. Cần assertion riêng cho listener invocation và exported span.

## 9. Kiểm thử propagation qua message broker

HTTP propagation thường dùng traceparent header. Với message broker, trace context thường được inject/extract trong message headers bởi instrumentation hoặc producer/consumer code.

Một integration test nên kiểm tra:
- Producer ghi trace context vào message headers.
- Consumer extract context trước khi xử lý message.
- Consumer span giữ liên hệ với trace được truyền theo semantics của instrumentation.
- Correlation ID trong log consumer trỏ tới trace/span tương ứng.
- Message không có header tracing được xử lý theo chính sách root trace mới hoặc không có trace.

Không giả định mọi broker client tự động propagate. Kiểm tra tài liệu và instrumentation của Kafka, RabbitMQ hoặc broker đang dùng. Nếu tự inject/extract, dùng propagator của tracer thay vì tự parse chuỗi traceparent bằng code nghiệp vụ.

## 10. Sampling và test determinism

Sampling quyết định span nào được ghi/export. Trong production, sampling probability thường thấp hơn 1 để giới hạn chi phí. Điều đó có nghĩa test dựa trên exporter có thể không nhìn thấy span nếu cấu hình test không kiểm soát sampling.

Quy tắc:
- Đặt sampling probability = 1.0 trong test profile khi cần assert exported spans.
- Không dùng cấu hình test đó cho production.
- Phân biệt context propagation với span export: trace context có thể được truyền dù span không được ghi lại/export.
- Không coi việc không thấy span trong backend là bằng chứng request không có trace context.
- Khi kiểm thử sampling, tạo test riêng cho sampler thay vì để sampling ngẫu nhiên ảnh hưởng integration test khác.

Test cần deterministic: kiểm soát sampling, exporter, executor và request fixture. Tránh phụ thuộc vào backend từ xa nếu mục tiêu chỉ là xác minh trace context trong application.

## 11. Những assertion nên và không nên dùng

| Nên kiểm tra | Tránh kiểm tra |
| --- | --- |
| Trace ID giữ nguyên qua ranh giới được propagate | Một trace ID random cố định trong mọi lần chạy |
| Span ID mới khi một span mới được tạo | Span ID giống nhau giữa mọi module |
| Parent/child relation đúng với execution | Thứ tự export span cố định |
| traceparent header hợp lệ | So sánh nguyên chuỗi header có ID random |
| MDC được set trong scope và restore sau scope | MDC giữ nguyên sau khi request kết thúc |
| Module tags đúng với module entry span | Mọi span đều phải có module tags |
| Consumer span xuất hiện khi listener thực sự được instrument | Event publication counter đồng nghĩa listener success |
| Context không rò giữa hai task/request | Dùng Thread.sleep để chờ async task |
| Sampling được kiểm soát trong test | Dựa vào sampling production ngẫu nhiên |

## 12. Troubleshooting khi test correlation thất bại

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Incoming traceparent bị bỏ qua | Propagation type không khớp hoặc server instrumentation không bật | Kiểm tra management.tracing.propagation.type và tracing dependency |
| Trace ID outbound khác parent | HTTP client không dùng auto-configured builder hoặc context không active | Kiểm tra RestClient/RestTemplate/WebClient builder và span scope |
| Không có traceparent header | Client observation/tracing instrumentation chưa gắn vào request | Kiểm tra ObservationRegistry và client instrumentation |
| MDC không có traceId/spanId | Không có span active, MDC integration bị tắt hoặc key đã đổi | Kiểm tra current span và MDC configuration |
| MDC còn giá trị sau scope | Scope cleanup/context restoration không đúng hoặc code tự MDC.put | Kiểm tra scope close và thread reuse |
| Module entry span không xuất hiện | Modulith observability chưa bật, lời gọi không đi qua module API boundary hoặc sampling/exporter | Kiểm tra instrumentation và span exporter |
| Listener span có trace ID khác | Async context không được propagate hoặc listener tạo root trace riêng | Kiểm tra executor/message headers và semantics tracing |
| Test lúc pass lúc fail | Sampling, async wait hoặc exporter chưa deterministic | Set sampling 1.0, dùng Future/latch và in-memory exporter |
| Trace ID có trong log nhưng không tìm thấy trace backend | Span không được sample/export, exporter lỗi hoặc retention | Kiểm tra sampling, exporter và backend |
| Trace backend có span nhưng log thiếu correlation | Logging pattern/MDC key hoặc log pipeline parser sai | Kiểm tra raw log và correlation pattern |

## 13. Tích hợp test vào CI

Một bộ test trace correlation có thể chia thành các nhóm:

1. **Unit test:** kiểm tra code tạo span hoặc sử dụng Tracer đúng scope.
2. **HTTP integration test:** xác nhận extract traceparent và inject context cho outbound client.
3. **MDC test:** xác nhận trace/span IDs hiện diện trong scope và được restore.
4. **Async test:** xác nhận executor truyền context và không rò context giữa task.
5. **Modulith test:** xác nhận module entry span có module tags phù hợp.
6. **Event test:** xác nhận listener thực sự chạy và tracing context theo đúng semantics.
7. **Architecture test:** ApplicationModules.verify() bảo vệ module boundary; đây là kiểm tra kiến trúc riêng, không thay thế trace correlation test.

Trong CI:
- Dùng test profile với sampling và exporter deterministic.
- Dùng in-memory exporter hoặc mock HTTP server thay vì phụ thuộc tracing backend bên ngoài.
- Chạy test async với timeout rõ ràng.
- Giữ các test độc lập để tránh MDC hoặc context rò giữa test case.
- Không chạy test dựa trên production sampling hoặc retention.
- Lưu span dump/log output khi test thất bại để hỗ trợ chẩn đoán.

## 14. Checklist trước khi hoàn tất trace correlation tests

| Hạng mục | Điều kiện đạt |
| --- | --- |
| Tracing setup | Actuator và đúng Micrometer Tracing bridge/starter |
| Sampling | 100% trong test khi cần kiểm tra exported spans |
| Propagator | Test dùng cùng propagation format với ứng dụng |
| Incoming HTTP | traceparent được extract; trace ID giữ nguyên |
| Outgoing HTTP | traceparent được inject; client span có ID riêng |
| MDC | traceId/spanId đúng trong scope và được restore |
| Log output | Correlation pattern hiển thị đúng MDC keys |
| Async | Context được truyền qua executor có cấu hình rõ |
| Module spans | Module identifier và invocation metadata được xác minh |
| Event listener | Listener invocation được assert riêng với publication |
| Exporter | Dùng in-memory/test exporter và không phụ thuộc backend từ xa |
| Determinism | Không hard-code ID random hoặc dùng Thread.sleep |
| CI | Test có timeout, cleanup và failure diagnostics |

## 15. Ghi nhớ

**Trace correlation phải được kiểm tra tại từng ranh giới nơi context có thể bị mất hoặc thay đổi.** Incoming HTTP cần extract traceparent; outgoing HTTP cần inject context; executor và message listener cần propagation phù hợp; MDC phải được set trong span scope và restore sau đó.

Trong Spring Modulith, kiểm tra module entry spans bằng trace ID, span ID và module tags giúp xác nhận các điểm vào module xuất hiện trong trace như mong đợi. Event publication, listener invocation và listener completion là các sự kiện khác nhau, nên cần assertion riêng cho từng điều kiện.

Hãy kiểm soát sampling và exporter trong test, dùng ID động nhưng assert quan hệ giữa chúng, và tránh phụ thuộc thứ tự span hoặc timing ngẫu nhiên. Bộ integration test deterministic giúp phát hiện sớm lỗi correlation trước khi nhóm vận hành phải điều tra trace bị đứt trong production.

## Tài liệu tham khảo

- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): Micrometer Tracing, sampling, propagation và log correlation.
- [Micrometer Tracing — API](https://docs.micrometer.io/tracing/reference/api.html): Tracer, Span và SpanInScope.
- [Micrometer Tracing — Sampling](https://docs.micrometer.io/tracing/reference/sampling.html): sampling decision và cấu hình sampler.
- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): module observations/spans và event publication metrics.
- [Spring Framework — Context Propagation](https://docs.spring.io/spring-framework/reference/integration/observability.html): observation context và propagation trong ứng dụng Spring.
- [Spring Framework — ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html): truyền context qua executor task.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/): định dạng traceparent và trace context propagation.
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): integration testing và test support.

> **Giới hạn phiên bản:** Ví dụ dùng RestClient.Builder và MockRestServiceServer phù hợp với Spring Framework 6.1+; dự án cũ hơn có thể dùng RestTemplateBuilder/MockRestServiceServer. Tên property sampling/propagation và MDC key cần được xác minh theo Spring Boot version đang dùng. Việc thu thập span trong test phụ thuộc tracer bridge; chọn exporter tương ứng và không giả định mọi bridge có cùng API.
