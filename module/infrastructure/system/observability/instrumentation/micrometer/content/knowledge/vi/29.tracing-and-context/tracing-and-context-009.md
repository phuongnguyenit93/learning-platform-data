# Phạm vi tích hợp cần biết trước khi học sâu truyền ngữ cảnh hoặc tracing

Micrometer cung cấp một lớp instrumentation thống nhất để ứng dụng Java ghi nhận metrics và tạo Observation. Khi tích hợp tracing, Observation có thể được xử lý thêm bởi tracing handler để tạo span, truyền trace context qua các service và liên kết log với trace. Trước khi đi sâu vào propagation hoặc tracing backend, cần phân biệt rõ vai trò của Micrometer Metrics, Micrometer Observation, Micrometer Tracing, context propagation và hệ thống export.

Các thành phần này liên kết với nhau nhưng không phải một API duy nhất. Metrics trả lời câu hỏi định lượng như có bao nhiêu request và latency phân bố ra sao. Tracing cho biết một request đi qua những service và dependency nào. Observation là điểm instrumentation chung để một operation có thể tạo metrics, span hoặc các tín hiệu khác thông qua handler.

## Bản đồ các lớp tích hợp

Một ứng dụng thường có luồng dữ liệu như sau:

~~~mermaid
flowchart TD
    A[Mã nghiệp vụ và instrumentation tự động] --> B[Micrometer Observation]
    B --> C[ObservationRegistry]
    C --> D[Metrics handler]
    C --> E[Tracing handler]
    D --> F[MeterRegistry]
    E --> G[Micrometer Tracing]
    F --> H[Metrics registry/exporter]
    G --> I[Tracing bridge]
    I --> J[Tracing exporter/reporter]
    H --> K[Metrics backend]
    J --> L[Trace backend]
    B -.-> M[Context propagation]
    M -.-> N[Thread, executor, Reactor hoặc network boundary]
~~~

Vai trò của từng lớp:

| Thành phần | Trách nhiệm | Ví dụ |
|---|---|---|
| Micrometer Metrics | API meter và registry cho số đo định lượng | Counter, Gauge, Timer, DistributionSummary |
| Micrometer Observation | Mô tả operation và phát lifecycle signal | Observation, ObservationRegistry, ObservationHandler |
| Micrometer Tracing | API tracing độc lập với tracing implementation | Tracer, Span, Baggage |
| Tracing bridge | Nối Micrometer Tracing với thư viện tracing cụ thể | OpenTelemetry bridge hoặc Brave bridge |
| Context Propagation | Chuyển context qua ranh giới thread hoặc execution model | ThreadLocalAccessor, ContextSnapshot, Reactor Context |
| Exporter và backend | Gửi, nhận, lưu trữ và truy vấn telemetry | OTLP Collector, Prometheus, Tempo, Jaeger, Zipkin hoặc nền tảng quan sát khác |

Observation không phải backend tracing. Nó là API instrumentation và lifecycle. Tracing bridge không thay thế metrics registry. Context propagation không tự tạo span; nó giúp context đang hoạt động tiếp tục có mặt khi execution chuyển sang thread hoặc scheduler khác.

## Phân biệt Metrics, Observation và Tracing

Ba lớp thường xuất hiện cùng nhau nhưng trả lời các câu hỏi khác nhau:

| Khái niệm | Câu hỏi | Dữ liệu điển hình |
|---|---|---|
| Metrics | Hệ thống đang hoạt động ở mức tổng thể ra sao? | Request/second, error rate, p95 latency, queue depth |
| Observation | Operation nào đang được instrument và lifecycle của nó ra sao? | Tên operation, low/high-cardinality key values, start, event, error, stop |
| Tracing | Một lần thực thi cụ thể đã đi qua những bước nào? | Trace ID, span ID, parent span, duration, attributes, events |

Một Observation có thể được xử lý bởi nhiều handler. Metrics handler tạo Timer hoặc Counter; tracing handler tạo span. Nhờ vậy, instrumentation nghiệp vụ có thể khai báo một lần rồi phục vụ nhiều tín hiệu telemetry.

Không phải mọi Observation đều nhất thiết tạo span hoặc metric. Predicate có thể loại một số Observation; handler có thể không hỗ trợ context; tracing sampler có thể quyết định không ghi span. Cấu hình và handler đang hoạt động quyết định tín hiệu nào được tạo.

## Observation là điểm tích hợp chung

Khi viết instrumentation thủ công, có thể tạo Observation quanh một operation nghiệp vụ:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    private final ObservationRegistry observationRegistry;
    private final PaymentGateway paymentGateway;

    public CheckoutService(
            ObservationRegistry observationRegistry,
            PaymentGateway paymentGateway) {
        this.observationRegistry = observationRegistry;
        this.paymentGateway = paymentGateway;
    }

    public PaymentResult pay(PaymentCommand command) {
        Observation observation = Observation.createNotStarted(
                        "checkout.payment", observationRegistry)
                .lowCardinalityKeyValue("provider", normalize(command.provider()))
                .highCardinalityKeyValue("payment.id", command.paymentId());

        return observation.observe(() -> paymentGateway.authorize(command));
    }

    private String normalize(String provider) {
        return switch (provider) {
            case "bank-a", "bank-b", "wallet" -> provider;
            default -> "other";
        };
    }
}
~~~

Ví dụ cho thấy hai loại metadata có mục đích khác nhau:

- Low-cardinality key value provider có tập giá trị hữu hạn, phù hợp làm chiều phân nhóm metric.
- High-cardinality key value payment.id có thể hữu ích trong trace để tìm một operation cụ thể, nhưng không được đưa thành metric label bởi metrics handler mặc định.

Không đưa ID, email, token hoặc dữ liệu thanh toán nhạy cảm vào metric tag. High-cardinality cũng không có nghĩa là dữ liệu đó mặc nhiên an toàn để gửi đi; trace backend, quyền truy cập và retention vẫn cần được kiểm soát.

## Tích hợp tự động và instrumentation thủ công

Spring Boot Actuator cùng các thư viện tích hợp có thể tự động instrument một số ranh giới phổ biến:

- HTTP server request trong Spring MVC hoặc WebFlux.
- HTTP client được hỗ trợ như RestClient, RestTemplate hoặc WebClient tùy phiên bản và dependency.
- Một số client database, messaging và thư viện khác khi có instrumentation tương ứng.
- Meter hệ thống và runtime như JVM, process, executor hoặc web server khi binder phù hợp được bật.

Phạm vi tự động phụ thuộc Spring Boot, Micrometer, web stack và dependency có trong ứng dụng. Không giả định chỉ thêm Actuator là mọi thư viện đều tự tạo span hoặc metric.

Instrumentation thủ công phù hợp với ranh giới nghiệp vụ mà framework không biết, chẳng hạn checkout, import file hoặc xử lý một batch. Trước khi thêm, kiểm tra framework đã instrument cùng operation chưa để tránh đo trùng. Có thể giữ HTTP Observation cho toàn request và tạo Observation riêng cho thao tác payment bên trong request vì chúng có ranh giới khác nhau.

## Các lựa chọn tracing bridge và exporter

Micrometer Tracing cung cấp API chung; bridge nối API đó với một implementation cụ thể. Trong hệ sinh thái Spring Boot, hai lựa chọn phổ biến là:

| Bridge | Nền tảng tracing | Thành phần export thường đi kèm |
|---|---|---|
| micrometer-tracing-bridge-otel | OpenTelemetry | OpenTelemetry OTLP exporter hoặc exporter tương ứng |
| micrometer-tracing-bridge-brave | Brave | Zipkin reporter hoặc thành phần export tương ứng |

Chọn một tracing bridge phù hợp với kiến trúc và backend. Không thêm nhiều bridge chỉ để thử; chúng có thể tạo cấu hình tracing không nhất quán hoặc nhiều handler cùng tham gia ngoài ý muốn.

Ví dụ dependency Gradle cho Spring Boot và OpenTelemetry bridge:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("io.micrometer:micrometer-tracing-bridge-otel")
    runtimeOnly("io.opentelemetry:opentelemetry-exporter-otlp")
}
~~~

Phiên bản nên được quản lý bởi Spring Boot dependency management hoặc BOM tương thích. Không tự ghép các phiên bản Micrometer Tracing, OpenTelemetry API và exporter khác dòng nếu chưa kiểm tra ma trận tương thích.

Nếu ứng dụng chỉ cần metrics, không cần thêm tracing bridge. Nếu cần tracing, phải có bridge và cấu hình exporter/reporter phù hợp; chỉ có ObservationRegistry không tự gửi span đến backend.

## Cấu hình export là một phần riêng

Có ba quyết định khác nhau:

1. Instrumentation nào tạo Observation hoặc meter?
2. Handler nào chuyển Observation thành metrics hoặc span?
3. Exporter gửi tín hiệu đến endpoint nào và bằng giao thức nào?

Ví dụ, metrics có thể được scrape qua Prometheus endpoint trong khi traces được push qua OTLP đến Collector. Hai tín hiệu có thể dùng cùng Observation nhưng có đường export khác nhau.

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
  tracing:
    sampling:
      probability: 1.0
~~~

Đây là cấu hình minh họa cho môi trường phát triển: expose endpoint Prometheus và lấy mẫu toàn bộ trace để thuận tiện kiểm tra. Không nên mặc định dùng sampling probability 1.0 trong production có lưu lượng lớn; chọn sampling policy dựa trên throughput, chi phí, yêu cầu điều tra và khả năng backend.

Để gửi trace qua OTLP, cấu hình endpoint tracing exporter theo phiên bản Spring Boot và tracing bridge đang dùng. Endpoint OTLP trace thường kết thúc bằng /v1/traces khi dùng OTLP/HTTP; OTLP/gRPC dùng endpoint và protocol tương ứng. Không dùng endpoint metrics /v1/metrics cho trace.

## Trace context và quan hệ parent-child

Trace mô tả một hành trình phân tán. Trace ID nhận diện toàn bộ trace; span ID nhận diện một đoạn công việc; parent span ID liên kết span con với span đã khởi tạo nó.

Ví dụ một request checkout đi qua gateway, order service và payment service:

~~~mermaid
flowchart TD
    A[Trace: checkout request] --> B[Gateway span]
    B --> C[Order service span]
    C --> D[Payment service span]
    D --> E[Payment provider client span]
~~~

Các span cùng trace ID nhưng có span ID riêng. Quan hệ cha-con thể hiện luồng gọi. Khi context được truyền đúng qua network boundary, service tiếp theo có thể tạo span con thuộc cùng trace thay vì bắt đầu trace độc lập.

Không tự tạo trace ID hoặc span ID bằng UUID trong business code. Dùng tracing API và propagator của implementation để tạo, trích xuất và inject context theo chuẩn.

## Truyền context qua ranh giới mạng

Khi service A gọi service B qua HTTP, tracing instrumentation thường inject trace context vào request header. Với W3C Trace Context, các header phổ biến là:

| Header | Vai trò |
|---|---|
| traceparent | Mang trace ID, parent span ID và trace flags |
| tracestate | Mang thông tin vendor-specific bổ sung theo chuẩn |
| baggage | Mang các cặp key/value cần truyền xuyên service nếu được cấu hình |

Service nhận trích xuất context từ header và dùng nó làm parent cho span tiếp theo. Khi dùng HTTP client được instrument tự động, việc inject/extract thường do instrumentation đảm nhiệm. Với client tự viết hoặc protocol riêng, cần cấu hình propagator hoặc instrumentation tương ứng.

Không tự copy toàn bộ header tùy tiện giữa các request. Hãy dùng propagator chuẩn để tránh làm sai parent span, trace flags hoặc định dạng header. Cũng cần quyết định có tin cậy trace context đến từ bên ngoài hay không; hệ thống public có thể cần tạo trace mới tại trust boundary hoặc lọc baggage không được phép.

## Truyền context trong cùng tiến trình

Trong một thread đồng bộ, Observation có thể mở Scope để đặt Observation hiện tại vào execution context:

~~~java
Observation observation = Observation.createNotStarted(
        "report.generate", observationRegistry);

observation.start();
try (Observation.Scope scope = observation.openScope()) {
    reportGenerator.generate();
} finally {
    observation.stop();
}
~~~

Scope thường dựa trên ThreadLocal. Nó có hiệu lực trong thread đang mở và phải được đóng đúng cách. Không giữ Scope mở rồi chuyển sang thread khác; ThreadLocal của thread ban đầu không tự đi theo task được submit vào executor.

Context Propagation của Micrometer cung cấp cơ chế capture và restore các context đã đăng ký accessor. Với executor thủ công, có thể dùng ContextSnapshot để bọc Runnable hoặc Callable:

~~~java
import io.micrometer.context.ContextSnapshot;
import io.micrometer.context.ContextSnapshotFactory;

ContextSnapshotFactory snapshotFactory =
        ContextSnapshotFactory.builder().build();
ContextSnapshot snapshot = snapshotFactory.captureAll();

executor.execute(snapshot.wrap(() -> {
    // Observation/trace context đã được khôi phục trong task
    reportGenerator.generate();
}));
~~~

Ví dụ giả định các ThreadLocal cần truyền đã có ThreadLocalAccessor đăng ký trong ContextRegistry. Nếu accessor không được đăng ký, captureAll không thể tự biết cách đọc và khôi phục ThreadLocal tùy ý. Trong Spring Boot, một số tích hợp có thể tự cấu hình context propagation; tránh đăng ký accessor lặp và kiểm tra phiên bản đang dùng.

Khi task kết thúc, wrapper khôi phục context trước đó để tránh rò rỉ context giữa các task chạy trên cùng worker thread. Nếu tự quản lý snapshot thủ công, phải bảo đảm scope/snapshot được đóng trong mọi nhánh.

## Context propagation trong Reactor

Reactive pipeline có thể đổi thread giữa các operator. Reactor Context là cơ chế gắn dữ liệu với subscription, trong khi nhiều thư viện quan sát truyền trạng thái hiện tại qua ThreadLocal. Micrometer Context Propagation cung cấp cầu nối giữa các context đã đăng ký và Reactor Context.

Điều cần nhớ:

- ThreadLocal không phải nguồn context đáng tin cậy xuyên suốt reactive chain.
- Reactor Context gắn với subscription và đi theo pipeline qua các operator.
- Context Propagation chỉ chuyển những giá trị có accessor phù hợp.
- Chế độ automatic context propagation và behavior của operator phụ thuộc phiên bản Reactor/Spring Boot.
- Không tự bật nhiều cơ chế propagation chồng lấn nếu chưa hiểu thứ tự capture/restore.

Khi dùng WebFlux, WebClient hoặc Reactor, ưu tiên tích hợp được Spring Boot hỗ trợ. Với custom scheduler hoặc operator, kiểm thử trace parent và MDC ở cả trước/sau thread switch. Đừng chỉ kiểm tra một log line trên cùng thread rồi kết luận propagation đã đúng.

## Baggage, span attributes và MDC không giống nhau

Các khái niệm này thường bị dùng lẫn:

| Khái niệm | Phạm vi | Dùng cho |
|---|---|---|
| Span attribute | Thuộc một span cụ thể | Mô tả operation hoặc dependency |
| Baggage | Context có thể truyền xuyên nhiều service | Truyền metadata được cho phép giữa các service |
| MDC | Ngữ cảnh logging của thread | Đưa trace ID/span ID hoặc correlation field vào log |
| Metric tag | Nhãn của time series | Nhóm dữ liệu với tập giá trị hữu hạn |

Baggage có thể được truyền qua network header nếu propagator và cấu hình cho phép. Điều này khiến baggage có chi phí và rủi ro dữ liệu lớn hơn một span attribute chỉ lưu ở một service. Chỉ truyền những key thật sự cần thiết; không dùng baggage để mang payload nghiệp vụ hoặc bí mật.

MDC thường được đồng bộ từ tracing context để log có trace ID và span ID. Vì MDC thường gắn với thread, nó cũng cần context propagation khi chuyển executor hoặc reactive scheduler. MDC không phải cơ chế truyền trace context qua HTTP; việc đó do propagator thực hiện.

Không đưa baggage tùy ý thành metric tag. Một baggage value có thể thay đổi theo từng request và tạo cardinality không giới hạn. Nếu cần phân nhóm metrics, ánh xạ metadata thành một tập low-cardinality values được kiểm soát.

## Sampling của trace không đồng nghĩa sampling metrics

Tracing sampler quyết định span nào được ghi/export. Metrics handler là một pipeline khác và thường vẫn ghi metrics cho Observation ngay cả khi trace không được lấy mẫu, miễn là Observation không bị predicate loại bỏ và meter handler hoạt động.

Điều này quan trọng khi phân tích dữ liệu:

- Dashboard metrics có thể cho thấy toàn bộ request hoặc phần lớn request theo meter instrumentation.
- Trace backend chỉ lưu một mẫu request theo sampling policy.
- Không nên kỳ vọng mỗi điểm tăng counter đều có một trace tương ứng.
- Khi điều tra sự cố, sampling policy có thể ưu tiên error, latency cao hoặc một nhóm operation theo khả năng của tracing implementation.

Nếu dùng ObservationPredicate để loại operation, predicate có thể ảnh hưởng đến cả handler metrics và tracing cho Observation đó. Đừng nhầm predicate với trace sampler. Một bên quyết định có tạo Observation hay không; bên kia quyết định có ghi trace hay không.

## Kiểm soát cardinality và dữ liệu nhạy cảm

Metrics và tracing có khả năng chịu cardinality khác nhau. Trace có thể mang các span attribute có độ chi tiết cao hơn metric, nhưng vẫn phải kiểm soát kích thước, retention và dữ liệu nhạy cảm. Metrics nên dùng low-cardinality dimensions.

Ví dụ:

| Giá trị | Metric tag | Span attribute hoặc log |
|---|---|---|
| provider = bank-a | Phù hợp nếu số provider hữu hạn | Có thể dùng |
| operation = authorize | Phù hợp | Có thể dùng |
| payment.id = p-123 | Không phù hợp | Chỉ dùng nếu chính sách dữ liệu cho phép |
| customer.email | Không phù hợp | Không nên đưa vào telemetry |
| trace ID | Không phù hợp làm metric tag | Có thể dùng correlation field trong log/trace |

Không đưa password, access token, session cookie, số thẻ hoặc nội dung request vào Observation metadata, baggage, span attribute hay log. Dữ liệu được gửi sang Collector/backend có thể được lưu trữ và truy cập bởi nhiều thành phần vận hành.

## Kiểm tra tích hợp theo từng ranh giới

Không cần bắt đầu bằng một hệ thống tracing lớn. Có thể xác minh từng lớp theo thứ tự:

1. **Observation:** dùng SimpleMeterRegistry hoặc test handler để xác nhận operation tạo đúng meter và lifecycle callback.
2. **Metrics handler:** xác nhận Timer/Counter được tạo từ Observation.
3. **Tracing handler:** xác nhận span được tạo và có trace ID/span ID.
4. **Context propagation:** chuyển operation qua executor hoặc reactive scheduler rồi xác nhận span con giữ đúng trace ID và parent.
5. **Network propagation:** gọi một service khác và xác nhận request header được inject/extract theo chuẩn.
6. **Exporter:** xác nhận Collector hoặc backend nhận đúng signal.
7. **Log correlation:** xác nhận log ở các thread/service có trace ID/span ID tương ứng nếu MDC integration được bật.

Một test context propagation nên kiểm tra cả task thành công và task ném exception để xác nhận context được khôi phục/dọn dẹp sau khi callback kết thúc. Với test reactive, thêm bước đổi scheduler để kiểm tra context không phụ thuộc thread hiện tại.

## Ví dụ kiểm thử Observation cơ bản

Test metrics độc lập có thể xác nhận Observation tạo Timer mà không cần tracing backend:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.junit.jupiter.api.Test;

class ObservationMetricsIntegrationTest {
    @Test
    void recordsObservationAsTimer() {
        SimpleMeterRegistry meters = new SimpleMeterRegistry();
        ObservationRegistry observations = ObservationRegistry.create();
        observations.observationConfig().observationHandler(
                DefaultMeterObservationHandler.builder(meters).build());

        Observation.createNotStarted("checkout.payment", observations)
                .lowCardinalityKeyValue("provider", "bank-a")
                .observe(() -> {
                    // Thực hiện operation giả lập.
                });

        Timer timer = meters.get("checkout.payment")
                .tag("provider", "bank-a")
                .tag("error", "none")
                .timer();

        assertThat(timer.count()).isEqualTo(1);
        meters.close();
    }
}
~~~

Test này chỉ xác nhận Observation-to-metrics path. Nó không chứng minh tracing bridge, context propagation hoặc exporter đã hoạt động. Các lớp đó cần test riêng theo ranh giới tương ứng.

## Lỗi tích hợp thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Có metric nhưng không có trace | Chưa thêm tracing bridge/exporter, sampler loại span hoặc tracing handler chưa được cấu hình | Kiểm tra dependency, ObservationRegistry và sampling |
| Có span ở service đầu nhưng trace bị tách ở service sau | Trace context không được inject/extract hoặc client không được instrument | Kiểm tra traceparent và HTTP client instrumentation |
| Trace ID mất sau khi submit executor | ThreadLocal không được truyền sang worker | Dùng Context Propagation/accessor hoặc executor được cấu hình |
| MDC trống sau thread switch | Logging context không được propagate | Kiểm tra MDC accessor và context propagation |
| Baggage không đến service đích | Key chưa được cấu hình để propagate hoặc propagator không hỗ trợ | Kiểm tra baggage configuration và header |
| Metrics cardinality tăng đột biến | Trace ID, user ID hoặc baggage được đưa vào metric tag | Chuyển về low-cardinality key values |
| Span bị tạo trùng | Auto instrumentation và manual span cùng bọc một operation | Kiểm tra ranh giới instrumentation và handler |
| Không thấy trace ở backend | Exporter sai endpoint, protocol, TLS hoặc Collector pipeline | Kiểm tra log exporter và Collector receiver |
| Metrics thiếu khi trace bị sample out | Nhầm trace sampler với ObservationPredicate hoặc meter handler không chạy | Kiểm tra từng pipeline riêng |

## Phạm vi nên học tiếp

Sau khi nắm bản đồ tích hợp, có thể đi sâu theo thứ tự:

1. **Tracing model:** trace, span, parent-child, link, status và event.
2. **Propagation:** W3C Trace Context, baggage, inject/extract và trust boundary.
3. **In-process context:** Observation.Scope, ThreadLocalAccessor, ContextSnapshot và executor.
4. **Reactive context:** Reactor Context, scheduler switch và context propagation mode.
5. **Sampling:** probability sampling, parent-based sampling và policy theo lỗi/latency nếu implementation hỗ trợ.
6. **Export pipeline:** OTLP, Collector, retry, queue, TLS, authentication và backend.
7. **Correlation:** liên kết metrics, traces và logs mà không làm tăng cardinality hoặc rò rỉ dữ liệu.

Mỗi chủ đề nên được kiểm thử độc lập trước khi kết hợp. Khi trace bị mất sau executor, không cần điều chỉnh exporter trước khi xác nhận context còn tồn tại ở worker. Khi có span nhưng backend không thấy, kiểm tra exporter và Collector. Chia theo ranh giới giúp tìm đúng lớp gây lỗi.

## Checklist tích hợp

- [ ] Đã phân biệt Metrics, Observation và Tracing.
- [ ] Đã xác định instrumentation tự động nào đang hoạt động.
- [ ] Chỉ thêm instrumentation thủ công cho operation chưa được đo hoặc có ranh giới riêng.
- [ ] Chọn một tracing bridge và exporter tương thích với phiên bản Spring Boot.
- [ ] Metrics và traces có cấu hình export riêng, đúng endpoint và protocol.
- [ ] Trace context được inject/extract qua network bằng propagator chuẩn.
- [ ] Context được truyền đúng qua executor và reactive boundary.
- [ ] Scope/ThreadLocal được đóng hoặc khôi phục sau task.
- [ ] Baggage và span attributes không chứa bí mật hoặc dữ liệu nhạy cảm.
- [ ] Metric tags chỉ dùng giá trị có cardinality thấp.
- [ ] Trace sampling được phân biệt với ObservationPredicate và metrics pipeline.
- [ ] Đã kiểm thử riêng metrics, tracing, context propagation và exporter.

## Tài liệu tham khảo

- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/)
- [Micrometer Context Propagation Reference](https://docs.micrometer.io/context-propagation/reference/)
- [Micrometer Observation Reference](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Spring Boot Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [W3C Trace Context](https://www.w3.org/TR/trace-context/)

Micrometer Observation là điểm instrumentation chung; metrics và tracing là hai cách xử lý tín hiệu từ điểm đó. Tracing bridge kết nối API tracing với implementation, exporter chuyển span đến backend, còn context propagation giữ liên kết khi execution chuyển thread, reactive scheduler hoặc service khác. Nắm rõ từng ranh giới này giúp chọn đúng dependency, cấu hình và phép kiểm thử trước khi học sâu tracing hoặc propagation.
