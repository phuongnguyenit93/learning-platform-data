# Trace context bị mất trong Spring Boot

Trace context bị mất khi một operation downstream không còn liên kết với trace đã bắt đầu ở upstream. Trong trace backend, biểu hiện thường gặp là một span trở thành root ngoài dự kiến, Trace ID thay đổi giữa hai service, logs thiếu traceId/spanId hoặc trace chỉ có HTTP server span mà không có client/database/consumer spans. Lỗi này làm distributed trace bị chia đoạn và khiến việc điều tra latency, lỗi phụ thuộc hoặc hành vi bất đồng bộ khó hơn.

Trong module SPRING_BOOT_OBSERVABILITY, trace context là nền tảng liên kết metrics, logs và distributed tracing qua HTTP, messaging, executor và database calls. Bài thuộc chương Chẩn đoán sự cố, tập trung vào chẩn đoán trace context bị mất: nhận diện triệu chứng, kiểm tra propagation headers, phân biệt context extraction với sampling, xử lý thread boundaries, Reactor và message headers, xác minh instrumentation, viết integration tests và lập runbook.

## Mục tiêu học tập

1. Giải thích Trace ID, Span ID, parent relationship và active context.
2. Nhận biết trace bị đứt qua HTTP, async executor, messaging hoặc reactive pipeline.
3. Kiểm tra W3C Trace Context và B3 propagation headers.
4. Phân biệt context không được inject/extract với trace bị sampling hoặc export drop.
5. Propagate context qua Executor, CompletableFuture và Spring @Async.
6. Xử lý context trong Reactor và messaging consumers.
7. Xác minh JDBC/client instrumentation và logging correlation.
8. Viết tests chứng minh Trace ID/parent relationship xuyên boundary.
9. Điều tra an toàn mà không log hoặc phát tán dữ liệu nhạy cảm.

## 1. Trace context và propagation

Trace context là metadata cho phép một span biết nó thuộc trace nào và quan hệ với span cha. Các khái niệm chính:

- Trace ID: định danh toàn distributed trace.
- Span ID: định danh một operation trong trace.
- Parent Span ID: span cha của operation hiện tại.
- Trace flags: các flags, bao gồm sampled bit trong W3C Trace Context.
- Trace state: vendor-specific state được truyền cùng context.

~~~text
Trace A
  HTTP server span (traceId=T1, spanId=S1)
    └─ HTTP client span (traceId=T1, spanId=S2, parent=S1)
         └─ Remote server span (traceId=T1, spanId=S3, parent=S2)
~~~

Khi context được propagate đúng, downstream span giữ cùng Trace ID và parent trỏ về span upstream tương ứng. Downstream operation có thể dùng span link thay cho parent-child trong các mô hình batch/async fan-in; điều quan trọng là quan hệ được biểu diễn rõ.

### 1.1. Active context và scope

Tracing SDK giữ current span trong execution context. Khi bắt đầu child operation, instrumentation đọc current context để tạo parent relationship. Scope phải được đóng khi operation kết thúc để current context trước đó được khôi phục.

Nếu scope không được đóng, context có thể rò rỉ sang operation tiếp theo trên cùng thread. Nếu context không được activate trong worker thread, downstream span có thể thành root hoặc không được tạo.

### 1.2. Context propagation không phải log correlation

MDC là map phục vụ logging. Trace context là context được tracing API/SDK sử dụng để tạo spans và parent relationship. Copy traceId/spanId vào MDC có thể làm log hiển thị correlation fields, nhưng không tự tạo active span hoặc propagate parent context.

## 2. Triệu chứng và dấu hiệu nhận biết

| Triệu chứng | Khả năng cần kiểm tra |
| --- | --- |
| Trace ID đổi sau HTTP call | Client không inject header hoặc server không extract |
| Downstream span thành root | Active context không có hoặc parent bị mất |
| Logs có traceId nhưng trace backend không có child span | MDC còn dữ liệu nhưng instrumentation/context không hoạt động, hoặc sampling/export |
| Chỉ có HTTP server span | Client/JDBC instrumentation chưa bật hoặc context boundary bị mất |
| Async task tạo trace mới | Executor không propagate context hoặc task tạo root span |
| Consumer không nối với producer trace | Message headers không mang context hoặc consumer không extract |
| Reactor chain thiếu parent | Context bị đọc từ ThreadLocal ở sai thời điểm |
| Một số spans biến mất | Sampling, Collector routing, exporter drop hoặc late spans |

Không kết luận context bị mất chỉ từ việc không tìm thấy trace ở backend. Span có thể chưa được tạo, bị sampling, bị drop trong exporter/Collector, gửi tới tenant khác hoặc query sai thời gian.

## 3. Kiểm tra W3C Trace Context headers

W3C Trace Context thường dùng:
- traceparent: version, trace ID, parent ID và trace flags;
- tracestate: vendor-specific tracing state.

Ví dụ:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
tracestate: vendor=value
~~~

Trace ID trong header phải được downstream extract để tiếp tục trace. Sampled flag không phải Trace ID và không phải bằng chứng duy nhất cho việc span tồn tại ở backend.

### 3.1. Bắt đầu từ ingress

Kiểm tra request đầu tiên đi vào ứng dụng:
1. Caller có gửi traceparent hay format được hệ thống hỗ trợ không?
2. Gateway/proxy có xóa hoặc thay header không?
3. Server instrumentation có extract đúng propagator không?
4. Trace ID trong server span có khớp trace context từ caller không?

Không ghi toàn bộ headers vào application logs để debug; headers có thể chứa cookies, tokens và dữ liệu cá nhân. Chỉ log một correlation identifier đã được xử lý theo policy nếu cần.

### 3.2. Header format không khớp

Một service có thể phát W3C Trace Context trong khi service khác chỉ cấu hình B3, hoặc ngược lại. Khi format không khớp, downstream có thể bắt đầu trace mới. Kiểm tra propagator configuration trên cả hai phía và gateway.

### 3.3. Multiple propagation formats

Hệ thống có thể hỗ trợ W3C và B3 đồng thời trong giai đoạn migration. Cần chọn format ưu tiên và tránh để nhiều headers mâu thuẫn nhau. Nếu traceparent và B3 headers cùng xuất hiện nhưng mang IDs khác nhau, behavior phụ thuộc propagator configuration và implementation.

## 4. Phân biệt context loss với sampling/export loss

Đây là bước quan trọng để không sửa nhầm propagation.

| Quan sát | Context loss | Sampling/export loss |
| --- | --- | --- |
| Downstream Trace ID khác | Có thể | Thường không nếu trace vẫn được nối |
| Child span có trong app/test exporter nhưng không ở backend | Không | Có thể |
| Parent ID không đúng | Có thể | Không nhất thiết |
| Collector báo refused/dropped spans | Không phải context loss | Có |
| Sampling flag là unsampled | Không tự chứng minh context mất | Có thể |
| Logs có traceId nhưng backend không có trace | Có thể hoặc sampling/export | Cần kiểm tra nhiều tầng |

Quy trình:
1. Xác minh current trace context ngay trước boundary.
2. Xác minh header/message metadata được inject.
3. Xác minh downstream extract cùng Trace ID.
4. Kiểm tra child span được tạo trong process hay chưa.
5. Nếu span đã tạo đúng, kiểm tra sampler, exporter, Collector và backend.

## 5. Cấu hình Spring Boot và Micrometer Tracing

Spring Boot Actuator cùng Micrometer Tracing có thể tự cấu hình tracing cho các integration được hỗ trợ. Ví dụ dependency với OpenTelemetry bridge:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'
}
~~~

Giữ dependency versions theo Spring Boot BOM. Với HTTP client/server, JDBC và messaging, cần integration/instrumentation tương ứng; tracing bridge không tự bảo đảm mọi thư viện đều được instrument.

Ví dụ sampling probability:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
~~~

Trong test có thể dùng sampling 100% để tránh trace bị loại do head sampling. Không mặc định dùng 100% trong production nếu volume chưa được tính toán.

### 5.1. Propagator configuration

Micrometer Tracing bridge và tracing implementation có thể hỗ trợ W3C/B3 propagators. Property names và default formats phụ thuộc Spring Boot/Micrometer version. Kiểm tra reference đúng version và xác minh headers thực tế được phát/đọc. Không thêm property phỏng đoán rồi kết luận đã bật propagation.

### 5.2. Instrumentation boundary

Kiểm tra các integration cần thiết:
- HTTP server instrumentation;
- HTTP client instrumentation;
- JDBC/DataSource instrumentation;
- messaging producer/consumer instrumentation;
- executor/async context propagation;
- Reactor context propagation.

Một trace chỉ có server span có thể là do instrumentation của downstream boundary chưa được bật, không nhất thiết do W3C header bị mất.

## 6. Context bị mất qua HTTP client/server

Khi service A gọi service B, client instrumentation cần inject current context vào request headers; server instrumentation của B extract context trước khi tạo server span.

~~~mermaid
sequenceDiagram
    participant Caller
    participant A as Service A
    participant Client as HTTP client instrumentation
    participant B as Service B
    Caller->>A: Request
    Note over A: Server span T1/S1
    A->>Client: Call B under active span
    Client->>B: HTTP request + traceparent
    Note over B: Extract T1/S2 as remote parent
    B-->>A: Response
    A-->>Caller: Response
~~~

### 6.1. Dùng HTTP client được instrument

Dùng Spring Boot-managed RestClient, WebClient hoặc HTTP client integration tương thích với version và tracing setup. Một HTTP client tự tạo ngoài application context có thể không nhận observation/tracing customizers.

### 6.2. Kiểm tra request interceptor

Nếu dùng custom interceptor, không tự ghi đè traceparent bằng Trace ID tự sinh. Để tracing instrumentation inject headers. Nếu gateway thay headers, kiểm tra cấu hình propagation và header allowlist tại gateway.

### 6.3. Kiểm tra server extraction

Server B cần server instrumentation hỗ trợ framework đang dùng. Nếu B nhận header nhưng tạo trace mới, kiểm tra propagator format, server filter chain, custom tracing configuration và việc có tạo root span thủ công trước extraction hay không.

## 7. Context bị mất qua Executor, @Async và CompletableFuture

ThreadLocal context không tự động được sao chép sang worker thread. Đây là nguyên nhân phổ biến khi code đồng bộ chuyển sang bất đồng bộ.

### 7.1. TaskDecorator và Context Propagation

Với Spring Framework 6.1+ và Micrometer Context Propagation, ContextPropagatingTaskDecorator có thể capture/restore các context accessor đã đăng ký:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class AsyncConfiguration {
    @Bean
    ThreadPoolTaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("app-async-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        return executor;
    }
}
~~~

Decorator chỉ propagate context có accessor tương ứng. Kiểm tra tracing/MDC accessors và version integration thực tế. Không giả định mọi ThreadLocal được tự động truyền.

### 7.2. @Async

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
class InvoiceAsyncService {
    @Async("applicationTaskExecutor")
    public void generateInvoice() {
        // Current trace context should be available through configured propagation.
    }
}
~~~

Bật async processing và gọi bean qua Spring proxy. Self-invocation trong cùng bean có thể bỏ qua @Async. Xác minh method thực sự chạy trên executor được cấu hình.

### 7.3. CompletableFuture

Chỉ rõ executor cho async continuations:

~~~java
CompletableFuture.supplyAsync(this::load, applicationExecutor)
        .thenApplyAsync(this::transform, applicationExecutor);
~~~

Các overload không chỉ định executor có thể chạy trên common ForkJoinPool, nơi context propagation của ứng dụng không được cấu hình như mong muốn. Mỗi continuation boundary cần được kiểm thử riêng.

### 7.4. Không tự copy MDC như giải pháp tracing

Copy MDC map có thể làm log hiển thị traceId, nhưng không khôi phục Span context. Dùng Micrometer Context Propagation/tracing scope để propagate active context; logging integration chịu trách nhiệm đưa IDs vào MDC.

## 8. Context trong Reactor và WebFlux

Reactive execution có thể chuyển thread trong pipeline. ThreadLocal không phải nguồn context đáng tin cậy cho reactive chain. Reactor dùng Context gắn với subscriber; instrumentation phải tích hợp context propagation để current span được khôi phục khi operator chạy.

Các điểm cần kiểm tra:
- Reactor instrumentation/observation được bật theo stack/version;
- context được ghi vào Reactor Context tại boundary;
- operator async như publishOn/subscribeOn không làm mất context;
- custom callbacks không đọc ThreadLocal tùy tiện;
- cancellation/error terminal signals đóng observation/span;
- blocking bridge không làm mất context khi chuyển qua executor.

### 8.1. Test qua scheduler boundary

Tạo một WebFlux request, đi qua publishOn/subscribeOn và gọi downstream client đã instrument. Assert Trace ID giống nhau và parent relationship hợp lệ. Test chỉ chạy một operator trên cùng thread có thể bỏ sót lỗi context propagation.

## 9. Context trong messaging

Với Kafka, RabbitMQ hoặc message broker khác, producer cần inject trace context vào message headers; consumer cần extract headers trước khi tạo processing span. Consumer có thể được mô hình hóa bằng parent-child hoặc span link tùy messaging semantics, batch processing và nhiều parent messages.

~~~text
Producer service
  └─ Produce span (traceId=T1)
       └─ Message headers: traceparent, tracestate

Broker

Consumer service
  └─ Extract context
       └─ Process span (traceId=T1 or linked context)
~~~

### 9.1. Kiểm tra headers

Xác minh producer inject trace context, broker/client không loại bỏ headers, serializer/deserializer giữ metadata, consumer extract trước processing span và retry/dead-letter flow có policy context rõ.

Không copy toàn bộ message payload vào trace attributes để kiểm tra propagation. Chỉ dùng trace context headers và metadata đã allowlist.

### 9.2. Batch và fan-in

Một consumer xử lý batch messages có thể nhận nhiều trace contexts. Chọn một parent duy nhất có thể gây hiểu sai quan hệ; span links thường biểu diễn nhiều causal contexts tốt hơn. Kiểm tra trace model theo messaging instrumentation version.

## 10. Context trong JDBC và database calls

JDBC call thường chạy đồng bộ trên thread hiện hành. Nếu parent context còn active và JDBC instrumentation được bật, database span sẽ là child span. Nếu repository call chạy trong executor hoặc reactive bridge, context cần được propagate tới nơi thực thi.

Kiểm tra JDBC instrumentation có thực sự tạo spans; DataSource proxy/agent có duplicate hoặc xung đột; transaction/repository call có chạy trên thread khác; span được tạo trước hay sau khi context bị đóng; database span có cùng Trace ID và parent phù hợp.

Pool metrics không phải database spans. Có Hikari metrics nhưng không có JDBC spans không chứng minh context bị mất; có thể JDBC instrumentation chưa được cài.

## 11. Logs và correlation IDs

Spring Boot/Micrometer Tracing có thể tích hợp traceId/spanId vào logging MDC tùy logging setup. Log correlation giúp tìm trace tương ứng nhưng không thay thế span hierarchy.

Ví dụ log đã được format:

~~~text
INFO traceId=4bf92f3577b34da6a3ce929d0e0e4736 spanId=00f067aa0ba902b7
InvoiceService - Invoice generation started
~~~

Khi logs thiếu traceId:
1. Xác minh current span tồn tại tại log statement.
2. Kiểm tra logging correlation integration và MDC format.
3. Nếu log ở async worker, kiểm tra context propagation.
4. Nếu log sau khi span scope đã đóng, điều chỉnh log boundary hoặc tạo operation context phù hợp.

Không tự tạo traceId ngẫu nhiên chỉ để lấp field trong logs; điều đó tạo correlation giả.

## 12. Kiểm thử trace context propagation

Test cần chứng minh cùng Trace ID và quan hệ parent, không chỉ kiểm tra một MDC string.

### 12.1. Test parent-child bằng in-memory exporter

Với tracing SDK test setup:
1. Tạo parent span và activate scope.
2. Gọi operation qua boundary cần kiểm tra.
3. Thu child span từ in-memory exporter.
4. Assert child có cùng Trace ID.
5. Assert parent Span ID đúng.
6. Kết thúc parent và kiểm tra scope được restore.

API cụ thể phụ thuộc Micrometer Tracing/OpenTelemetry SDK version. Test phải chạy cùng instrumentation thực tế của boundary.

### 12.2. Test HTTP propagation

Dùng hai application contexts hoặc MockWebServer/WireMock:
- service A nhận request;
- A gọi B qua HTTP client instrumented;
- B ghi nhận server span;
- test exporter xác minh trace IDs và parent relationship;
- test header format và sampling flags.

Mock một HTTP client method mà không chạy instrumentation interceptor không chứng minh propagation hoạt động.

### 12.3. Test executor thread reuse

Dùng executor một worker:
1. Caller có parent span T1.
2. Submit task A và assert worker thấy T1.
3. Hoàn tất task A.
4. Submit task B không có context.
5. Assert task B không thấy T1.
6. Cho task C ném exception và xác minh scope vẫn được restore.

Test thread reuse phát hiện context leakage mà test một task đơn lẻ thường bỏ sót.

### 12.4. Test messaging propagation

Dùng embedded broker hoặc test container nếu cần xác minh client integration. Assert producer inject headers và consumer extract đúng Trace ID. Với batch/fan-in, assert span links theo thiết kế thay vì ép một parent không phù hợp.

### 12.5. Test sampling riêng

Trong propagation tests, dùng sampler deterministic hoặc sampling 100% để tránh trace bị loại ngẫu nhiên. Sau khi propagation test pass, viết test riêng cho sampling policy và exporter behavior.

## 13. Troubleshooting theo boundary

| Boundary | Triệu chứng | Kiểm tra đầu tiên |
| --- | --- | --- |
| Ingress → Spring MVC | Server span thành root mới | traceparent, gateway, server propagator |
| Spring MVC → HTTP client | Client span không có parent | Active Observation/Tracing scope |
| Service A → Service B | Trace ID khác | Inject/extract headers và format |
| Caller → Executor | Task span thành root | TaskDecorator/context accessor |
| @Async | Context thiếu hoặc self-invocation | Proxy, executor bean, propagation |
| CompletableFuture | Chỉ continuation sau cùng mất trace | Executor của từng async stage |
| Reactor | Context mất sau scheduler switch | Reactor Context/instrumentation |
| Producer → Broker → Consumer | Consumer trace mới | Message headers và extraction |
| Service → JDBC | Không có DB span | JDBC instrumentation và thread boundary |
| Span → Log | Log thiếu IDs | MDC integration và active scope |
| App → Collector | Span tạo đúng nhưng backend thiếu | Sampling, queue, exporter, Collector |

### 13.1. Quy trình điều tra chuẩn

1. Chọn một request có trace ID nguồn đã biết.
2. Kiểm tra server span đầu tiên và parent context.
3. Đi từng boundary: HTTP, executor, messaging, Reactor, JDBC.
4. Ở mỗi boundary, kiểm tra context trước khi rời và sau khi vào.
5. Xác minh Trace ID, Span ID, parent hoặc span link.
6. Nếu context đúng trong process, kiểm tra sampling và exporter.
7. Xem Collector refused/dropped spans, exporter queue và backend tenant.
8. Kiểm tra MDC riêng với tracing context.
9. Viết regression test cho boundary gây lỗi.

### 13.2. Phân biệt các lớp lỗi

- Không có span được tạo: instrumentation hoặc Observation chưa bật.
- Span có nhưng Trace ID khác: extraction/parent context có vấn đề hoặc tạo root có chủ đích.
- Trace ID đúng nhưng parent không đúng: scope/parent selection hoặc async semantics.
- Span đúng trong exporter test nhưng mất ở backend: sampling/export/Collector/backend.
- Trace đúng nhưng log thiếu IDs: logging correlation/MDC.
- Metrics có nhưng spans thiếu: metrics handlers hoạt động độc lập với tracing context.

## 14. Production checklist

| Tiêu chí | Bằng chứng cần có |
| --- | --- |
| Propagation format được thống nhất | W3C/B3 config và ingress policy |
| HTTP client/server instrumented | Integration test xuyên service |
| Async context được propagate | Executor thread reuse test |
| Reactor context được kiểm tra | Scheduler boundary test |
| Messaging headers được inject/extract | Producer/consumer integration test |
| JDBC instrumentation có mặt | Trace chứa database span khi expected |
| Scope được restore | Success/error/cancel tests |
| Sampling được tách khỏi propagation | Deterministic propagation tests |
| Collector/export được giám sát | Dropped/refused/exporter metrics |
| Logs correlation đúng | MDC fields khớp active span |
| Privacy được kiểm soát | Không log raw headers/payload/secrets |
| Regression tests có trong CI | Boundary tests chạy khi nâng version |

## 15. Bài thực hành: sửa trace bị đứt trong order-service

**Bối cảnh:** API order-service nhận request và tạo server span. Khi gọi inventory-service qua HTTP, trace ID thay đổi. Một bước ghi audit chạy bằng CompletableFuture cũng tạo trace độc lập; log trong worker thiếu traceId. Metrics HTTP vẫn hoạt động bình thường.

**Nhiệm vụ:**
1. Xác minh Trace ID và parent span ở incoming server span.
2. Kiểm tra traceparent được inject vào HTTP request tới inventory-service.
3. Xác minh inventory-service extract cùng Trace ID.
4. Kiểm tra HTTP client có được Spring Boot tracing instrumentation cấu hình không.
5. Chỉ định executor rõ ràng cho CompletableFuture async stages.
6. Cấu hình TaskDecorator/context propagation cho executor.
7. Xác minh worker có active span và logs có MDC correlation.
8. Test thread reuse để bảo đảm context không rò rỉ giữa tasks.
9. Kiểm tra JDBC instrumentation riêng nếu audit persistence cần database span.
10. Dùng deterministic sampler trong propagation tests.
11. Nếu spans tạo đúng nhưng backend thiếu, kiểm tra Collector/export pipeline.
12. Thêm regression tests và runbook cho HTTP/async context loss.

**Kết quả mong đợi:** trace liên tục từ incoming request tới inventory call và async operation theo parent/link semantics phù hợp; logs có correlation đúng; test chứng minh context propagation và cleanup.

## 16. Ghi nhớ

Trace context bị mất thường xuất hiện ở boundary nơi execution chuyển từ HTTP sang client call, thread pool, CompletableFuture, Reactor hoặc message consumer. Kiểm tra Trace ID và parent relationship tại cả hai phía boundary. W3C traceparent/tracestate phải được inject/extract bởi instrumentation tương thích; đừng tự tạo hoặc ghi đè headers tùy tiện.

ThreadLocal không tự propagate sang worker; dùng context propagation và TaskDecorator/accessors phù hợp. Reactor cần context-aware instrumentation, messaging cần inject/extract headers, JDBC cần instrumentation riêng. Phân biệt context loss với sampling/export drop và log correlation failure. Dùng test exporter/integration tests để xác minh cùng Trace ID, parent/link và scope restoration. Metrics vẫn có thể hoạt động khi tracing context bị lỗi; kết hợp logs, metrics, traces và Collector diagnostics để xác định đúng tầng hỏng.

**Tài liệu tham khảo:**
- [W3C Trace Context](https://www.w3.org/TR/trace-context/)
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/)
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Micrometer Tracing — Reference](https://docs.micrometer.io/tracing/reference/)
- [Micrometer Context Propagation](https://docs.micrometer.io/context-propagation/reference/)
- [Spring Framework — Context Propagation](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [OpenTelemetry — Trace SDK Sampling](https://opentelemetry.io/docs/specs/otel/trace/sdk/#sampling)

