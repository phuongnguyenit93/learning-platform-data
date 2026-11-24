# Truy vết phân tán và truyền ngữ cảnh sang hệ thống ngoài

## 1. Vì sao Spring Cloud Task cần distributed tracing?

Một ứng dụng **Spring Cloud Task** xử lý công việc hữu hạn: nhập dữ liệu, đối soát giao dịch, xuất báo cáo, chạy theo lịch hoặc nhận yêu cầu từ một API. Framework có thể lưu mỗi lần chạy thành **TaskExecution** trong **TaskRepository**, gồm định danh, thời gian bắt đầu/kết thúc và trạng thái kỹ thuật. Nhưng kết quả nghiệp vụ thường đi qua nhiều hệ thống hơn một JVM:

- API điều phối nhận yêu cầu rồi khởi chạy task.
- Task đọc dữ liệu từ database, gọi một dịch vụ phân loại hoặc lưu file trên object storage.
- Task gửi message đến broker để worker khác xử lý.
- Một Spring Batch Job chia dữ liệu thành Step hoặc remote partitions.
- Scheduler chạy lại sau timeout, dù tác động ở một hệ thống ngoài có thể đã được thực hiện.

**Distributed tracing** giúp nối các thao tác thuộc một luồng xử lý thành những **span** trong một hoặc nhiều **trace**, để trả lời: tác vụ chậm ở đâu, downstream nào lỗi, request đã đi qua hệ thống nào, và một lần retry có liên quan đến lần trước như thế nào?

Ví dụ: tác vụ `invoice-sync` nhập 10.000 hóa đơn. `TaskRepository` cho biết TaskExecution 8041 thất bại sau 6 phút, nhưng không tự chỉ ra đã mất 5 phút tại API đối tác hay 1 phút tại database. Trace có thể cho thấy các client span và lỗi/độ trễ của từng downstream.

**Không đồng nhất ba loại dấu vết:**

| Cơ chế | Trả lời câu hỏi gì? | Giới hạn |
|---|---|---|
| `TaskRepository` | Lần chạy ứng dụng nào đã bắt đầu/kết thúc và có exit code gì? | Không phải hệ thống phân tán span, không tự lưu toàn bộ trace |
| Distributed tracing | Tác vụ đã gọi những thành phần nào, mất thời gian ở đâu, lỗi tại span nào? | Có thể bị sampling hoặc mất khi crash; không chứng minh kết quả nghiệp vụ đã commit |
| Business state / checkpoint | Hóa đơn, báo cáo, giao dịch thực sự đã được xử lý đến đâu? | Không tự cung cấp sơ đồ độ trễ hoặc nguyên nhân tại hệ thống ngoài |

Vận hành đáng tin cậy đòi hỏi đối chiếu **cả ba**, cùng với structured logs và trạng thái bộ điều phối.

## 2. Trace, span, context và correlation ID

| Thuật ngữ | Ý nghĩa | Ví dụ sử dụng |
|---|---|---|
| **Trace** | Chuỗi quan hệ nhân quả của một hoạt động phân tán | Một yêu cầu xuất báo cáo từ API đến task, broker và worker |
| **Trace ID** | Định danh toàn trace | Tra một luồng trên Jaeger, Tempo, Zipkin hoặc hệ thống tracing khác |
| **Span** | Một thao tác có bắt đầu/kết thúc, thời lượng, thuộc tính, lỗi | `task.reconcile`, `HTTP POST /payments`, `batch.step.import` |
| **Span ID** | Định danh một span | Phân biệt thao tác cha và con trong cùng trace |
| **Trace context** | Trace ID, current span, sampling decision và thông tin truyền theo | Dùng để tạo downstream span có quan hệ đúng |
| **Baggage** | Dữ liệu phụ có thể được truyền qua ranh giới tiến trình theo chuẩn | Một khóa tương quan được cho phép, **không dùng cho secret** |
| **Correlation ID** | ID nghiệp vụ/vận hành tự định nghĩa, có thể không trùng trace ID | `taskExecutionId`, `businessKey`, `requestId` |

Một trace có thể chứa nhiều span; một lần thực thi task có thể có một **root span** và nhiều span con. Nhưng **trace ID không phải TaskExecution ID**. Khi cùng một business key được retry, thường sẽ có TaskExecution mới và **có thể** có trace mới; liên hệ giữa chúng nên được ghi bằng business key, attempt ID hoặc span link, không cố ép tất cả retry dùng chung một trace.

Ví dụ minh họa:

~~~text
businessKey = tenant-A/INVOICE_SYNC/2026-11-23/revision-1

Attempt 1:
  TaskExecutionId = 8041
  traceId         = 3b0a...9df1
  status          = FAILED

Attempt 2:
  TaskExecutionId = 8056
  traceId         = 7c42...3a12
  status          = COMPLETED

Hai attempt cùng ý định nghiệp vụ nhưng là hai vòng đời khác nhau.
~~~

**Quy tắc:** `TaskExecutionId` định danh attempt, business key định danh ý định nghiệp vụ, `traceId` định danh đường đi quan sát. Dùng cả ba khi cần điều tra chạy lại an toàn.

## 3. Luồng truy vết mẫu của một Spring Cloud Task

~~~mermaid
flowchart TD
    U["Người dùng / Scheduler"] --> API["API điều phối hoặc Data Flow"]
    API --> T["Spring Cloud Task: invoice-sync"]
    T --> DB["Đọc DB nguồn"]
    T --> HTTP["HTTP client gọi dịch vụ đối tác"]
    HTTP --> EXT["Partner API"]
    T --> MQ["Publish event vào broker"]
    MQ --> W["Worker/Consumer hệ thống khác"]
    W --> OUT["DB hoặc Object Storage đích"]
    T --> TR["TaskRepository: TaskExecution"]
    T --> OT["Exporter / OpenTelemetry Collector"]
    API --> OT
    EXT --> OT
    W --> OT
    OT --> V["Tracing backend / UI"]
~~~

Nếu **trace context được truyền đúng** tại các ranh giới, UI tracing có thể hiển thị cây:

~~~text
reconcile-request (SERVER span tại API)
└─ launch-task (CLIENT / producer span, nếu launcher được instrument)
   └─ invoice-sync-task (task span tại JVM con, nếu context được truyền)
      ├─ db-read (database span nếu có instrumentation)
      ├─ partner-call (HTTP CLIENT span)
      │  └─ partner-api (HTTP SERVER span nếu partner tham gia tracing)
      └─ send-invoice-event (PRODUCER span)
         └─ consume-invoice-event (CONSUMER span khi receiver extract context)
~~~

**Không mặc định mọi kết nối trong sơ đồ sẽ xuất hiện tự động.** Đặc biệt, việc **khởi chạy một JVM/Pod mới** qua scheduler, Spring Cloud Data Flow hoặc TaskLauncher không tự chuyển current span context của JVM cha sang JVM con. Muốn nối trace cần cơ chế chuyển carrier và extract context rõ ràng. Nếu bên ngoài không hỗ trợ tracing, ít nhất phía task vẫn quan sát được thời gian và trạng thái của client span.

## 4. Chuẩn W3C Trace Context: traceparent và tracestate

Với HTTP, quy ước phổ biến để liên thông tracer khác nhau là **W3C Trace Context**. Hai header quan trọng:

- `traceparent`: chứa version, trace ID, **parent span ID** và trace flags.
- `tracestate`: dữ liệu mở rộng do các tracing vendor/công cụ quy định; có thể không hiện diện.

Ví dụ giá trị hợp lệ:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

| Phần | Ý nghĩa |
|---|---|
| `00` | Version của định dạng |
| `4bf92f3577b34da6a3ce929d0e0e4736` | Trace ID 16 byte (32 ký tự hex) |
| `00f067aa0ba902b7` | Parent span ID 8 byte (16 ký tự hex) |
| `01` | Trace flags trong ví dụ, có bit sampled |

Khi dịch vụ nhận HTTP request có `traceparent`:

1. Instrumentation **extract** context từ header.
2. Dịch vụ tạo **server span mới** có trace ID được kế thừa và quan hệ parent phù hợp.
3. Khi gửi request tiếp, instrumentation **inject** context của span hiện tại sang header outbound.
4. Downstream lại extract và tạo span tiếp theo.

**Không sao chép một span ID cố định cho mọi lời gọi.** Mỗi span cần ID riêng; tracer/instrumentation chịu trách nhiệm tạo và truyền context. Cũng không nên tự viết `traceparent` bằng việc nối chuỗi từ MDC nếu đã có instrumentation, vì dễ sinh context sai hoặc xung đột với tracing bridge.

### Baggage khác Trace Context

W3C **Baggage** dùng header `baggage` để truyền các cặp key/value đã được cho phép. Nó không phải bí mật bảo mật và có thể được chuyển tiếp sang nhiều hệ thống. Không đưa vào baggage:

- Token, API key, password hoặc cookie đăng nhập.
- Email, số điện thoại, nội dung hóa đơn hoặc dữ liệu cá nhân không cần thiết.
- SQL, JSON payload lớn hay toàn bộ `ApplicationArguments`.

Nếu cần business correlation, cân nhắc một opaque ID ít nhạy cảm; phải có **allowlist** và quy tắc chặn tại trust boundary. Không mặc định mọi baggage entry được framework tự propagate nếu chưa cấu hình.

## 5. Công cụ phổ biến trong Spring Boot: Micrometer Tracing + OpenTelemetry

Với các dòng **Spring Boot 3.x** có Spring Boot Actuator, một cách thường gặp là **Micrometer Observation/Tracing** kết hợp bridge OpenTelemetry và exporter OTLP.

Vai trò chính:

| Thành phần | Chức năng |
|---|---|
| `ObservationRegistry` | API ghi nhận observation ở tầng ứng dụng, không gắn chặt tracer cụ thể |
| `Micrometer Tracing` | Kết nối observation với trace/span, context propagation và log correlation |
| `micrometer-tracing-bridge-otel` | Bridge sang OpenTelemetry SDK |
| `opentelemetry-exporter-otlp` | Xuất trace qua OTLP theo cấu hình |
| **OpenTelemetry Collector** | Nhận/biến đổi/batch/export telemetry theo pipeline |
| Jaeger / Tempo / tracing backend | Lưu và hiển thị trace, tìm span chậm hoặc lỗi |

Ví dụ dependency **Gradle Groovy DSL, dòng Spring Boot 3.x**; version do Spring Boot BOM quản lý theo ma trận tương thích:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.cloud:spring-cloud-starter-task'

    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'

    // Nếu TaskRepository dùng PostgreSQL:
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

Đây chỉ là nhóm dependency cần quan tâm, chưa phải build file hoàn chỉnh. Khi dùng **Spring Boot 4.x hoặc release khác**, kiểm tra lại starter/auto-configuration, version và property names trong tài liệu release; không mặc định tất cả thuộc tính của Boot 3.x giữ nguyên.

Ví dụ `application.yml` cho **Spring Boot 3.x** trên môi trường thử:

~~~yaml
spring:
  application:
    name: invoice-sync-task
  main:
    web-application-type: none
  cloud:
    task:
      name: invoice-sync-task

management:
  tracing:
    sampling:
      probability: 1.0
  otlp:
    tracing:
      endpoint: http://otel-collector.monitoring.svc:4318/v1/traces
~~~

Giải thích:

- `spring.application.name` giúp gắn tên service/resource để dễ tìm trace.
- `web-application-type: none` phù hợp với JVM task hữu hạn; **không cần mở HTTP server** để gửi OTLP outbound.
- `management.tracing.sampling.probability: 1.0` là **tỷ lệ 100% chỉ phù hợp khi thử nghiệm/khối lượng nhỏ**. Trong production cần chọn sampling phù hợp tải và chi phí, cân nhắc chiến lược ở collector.
- `management.otlp.tracing.endpoint` là URL OTLP/HTTP trong ví dụ; phải có Collector thực sự hoạt động, NetworkPolicy/TLS phù hợp và exporter được cấu hình tương thích.

**Không có guarantee span sẽ xuất hiện** chỉ vì đã thêm dependency: cần một observation/span được tạo, sampling phù hợp, exporter hoạt động, và ứng dụng phải còn thời gian để flush trước khi thoát.

## 6. Tạo một span gốc cho công việc trong ApplicationRunner

Ứng dụng Spring Cloud Task không nhất thiết nhận HTTP request inbound. Vì vậy, **không có server span HTTP tự động** để bao quanh `ApplicationRunner`. Một lựa chọn rõ ràng là tạo observation cho toàn bộ phần việc nghiệp vụ.

Ví dụ Spring Boot 3.x với `ObservationRegistry`:

~~~java
import java.time.LocalDate;
import java.util.List;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class InvoiceSyncRunnerConfiguration {

    @Bean
    ApplicationRunner invoiceSyncRunner(
            ObservationRegistry registry,
            InvoiceSyncService service) {

        return arguments -> {
            List<String> dates = arguments.getOptionValues("date");
            if (dates == null || dates.size() != 1) {
                throw new IllegalArgumentException(
                    "Required: --date=yyyy-MM-dd");
            }

            LocalDate date = LocalDate.parse(dates.get(0));

            Observation.createNotStarted("task.invoice.sync", registry)
                .lowCardinalityKeyValue("task.name", "invoice-sync-task")
                .observe(() -> service.syncForDate(date));
        };
    }
}
~~~

`InvoiceSyncService` là service nghiệp vụ do dự án cung cấp. `Observation.observe(...)` mở scope trong lúc chạy service và đóng observation khi hàm trả về hoặc ném lỗi. Nếu tracing bridge được cấu hình, có thể xuất hiện span cho `task.invoice.sync`. Nếu nghiệp vụ ném exception, **đừng bắt rồi nuốt lỗi** chỉ để log: runner phải để Spring Cloud Task và exit-code policy quan sát thất bại.

### Khi nào nên tạo span con?

Tạo span con cho những đơn vị xử lý đáng quan sát, chẳng hạn `batch.partition.process`, `invoice.calculate` hoặc `result.publish`. Không nhất thiết tạo một span cho **mỗi dòng dữ liệu** nếu có hàng triệu dòng: chi phí lưu trace, cardinality và kích thước payload có thể rất lớn.

~~~java
Observation.createNotStarted("invoice.write.result", registry)
    .lowCardinalityKeyValue("operation", "upsert")
    .observe(() -> resultService.saveOnce(result));
~~~

Nếu `resultService` có instrumented JDBC/HTTP client, các span có thể lồng dưới observation hiện hành. Tuy nhiên, auto-instrumentation **tùy dependency và phiên bản**: `JdbcTemplate` đơn thuần không bảo đảm tự tạo mọi SQL span, và việc dùng Java SDK bên ngoài không bảo đảm có tracing nếu chưa gắn instrumentation.

## 7. Truyền context khi gọi HTTP sang hệ thống ngoài

Ví dụ task cần gọi API xác minh hóa đơn. Với Spring Boot 3.x, dùng **`RestClient.Builder` do Spring Boot quản lý** để tận dụng observation/tracing customization của framework, thay vì tạo HTTP client không qua auto-configuration.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class PartnerClient {

    private final RestClient client;

    public PartnerClient(RestClient.Builder builder) {
        this.client = builder
            .baseUrl("https://partner.internal.example")
            .build();
    }

    public void verify(String invoiceId) {
        client.post()
            .uri("/api/invoices/{id}/verify", invoiceId)
            .retrieve()
            .toBodilessEntity();
    }
}
~~~

Để chạy ví dụ, dự án cần dependency hỗ trợ `RestClient` tương ứng (Spring Framework 6.1+, thường với Spring Boot 3.2+), HTTP client được cấu hình theo nhu cầu, TLS/timeout và endpoint thật. **Không cần web server inbound**; task `WebApplicationType.NONE` vẫn có thể tạo HTTP client.

Khi có observation/span hiện hành và instrumentation phù hợp:

1. Client tạo một **HTTP CLIENT span**.
2. Propagator inject W3C `traceparent` và `tracestate` phù hợp vào request.
3. Partner nhận, extract và tạo span tiếp nối **nếu partner hỗ trợ và tin cậy context**.
4. Task ghi nhận thời lượng/HTTP status/error của request bên mình, kể cả khi partner không phát trace.

**Không đảm bảo tự động chỉ vì dùng `RestClient`.** Cần dùng builder đã được framework instrument, bộ bridge/exporter đúng, observation đang active và kiểm tra header trên môi trường thử. Tạo client bằng `RestClient.create()` hoặc `WebClient.builder()` thủ công có thể không nhận toàn bộ customizer/observation registry của Boot.

Đối với `WebClient`, nguyên tắc tương tự: ưu tiên `WebClient.Builder` được auto-configure, xử lý reactive context đúng cách và không cố dùng MDC `ThreadLocal` làm nguồn duy nhất cho các luồng reactive.

### Không truyền trace context qua URL hoặc payload nghiệp vụ

Ưu tiên header propagation chuẩn. Không chèn trace ID vào query string để “truyền ngữ cảnh”, vì URL dễ vào access log, proxy và cache. Có thể gửi **correlation ID nghiệp vụ riêng** trong header được xác định bằng hợp đồng API nếu cần hỗ trợ tracing giữa các tổ chức, nhưng phải lọc dữ liệu và phân quyền.

## 8. Message broker: ngữ cảnh qua header, không qua ThreadLocal của producer

Với Kafka, RabbitMQ, JMS hoặc broker khác, producer và consumer có thể chạy ở hai JVM và **không chia sẻ thread context**. Truy vết phân tán cần:

1. **Producer span** ghi nhận thao tác publish.
2. Tracer/propagator **inject** context vào message headers/properties của carrier hỗ trợ.
3. Consumer **extract** context từ message khi nhận.
4. Consumer bắt đầu span mới gắn với parent hoặc **link** phù hợp ngữ nghĩa xử lý bất đồng bộ.
5. Consumer xử lý message, ghi lỗi và trạng thái; duplicate delivery được xử lý bằng idempotency riêng.

~~~mermaid
sequenceDiagram
    participant T as Spring Cloud Task
    participant P as Message Producer
    participant Q as Broker
    participant C as Consumer Service
    participant O as Trace Collector

    T->>T: Mở task observation
    T->>P: Publish domain event
    P->>Q: Event + trace context headers
    P->>O: Producer span
    Q->>C: Giao event (có thể giao lại)
    C->>C: Extract context và tạo consumer span
    C->>C: Xử lý idempotent
    C->>O: Consumer span + result
~~~

Không phải mọi message library tự động inject/extract W3C headers. Chẳng hạn, với Spring Kafka/Micrometer, khả năng observation cần được **bật đúng cho KafkaTemplate và listener container** theo version/config; với RabbitMQ hoặc JMS cũng cần instrumentation tương ứng. Nếu một hop không có propagation, backend tracing sẽ có **hai trace rời** dù event được nhận thành công.

Bản thân `messageId` hoặc `eventId` cũng **không phải trace ID**. Khi broker giao lại cùng message, có thể sinh một consumer span/attempt mới. Dedupe theo message/business key để tránh tác động trùng; dùng trace để hiểu các attempt.

### Span parent hay span link?

Với một request/reply nhanh, quan hệ parent–child thường trực quan. Nhưng với queue xử lý hàng giờ, fan-out hoặc scheduled job, nguyên nhân có thể không còn là quan hệ parent thực thi liên tục. **Span links** có thể diễn tả “được kích hoạt bởi một trace trước” mà không kéo dài một trace duy nhất qua toàn bộ thời gian chờ.

Hãy chọn mô hình theo khả năng và semantic conventions của tracer/library, không tự ép toàn bộ thời gian từ publish đến consume thành latency của một HTTP request.

## 9. Truyền ngữ cảnh qua thread pool và @Async

Trace context thường gắn với **current scope** (thread-local hoặc cơ chế context của thư viện). Nếu trong runner dùng `CompletableFuture` hoặc `ExecutorService` mà không propagate, span bên trong worker thread có thể trở thành **root span mới**, không có trace ID giống với task.

Ví dụ cần tránh:

~~~java
CompletableFuture.runAsync(
    () -> partnerClient.verify(invoiceId));
~~~

Lệnh này dùng executor mặc định và không nói gì về propagation, timeout, quản lý lifecycle hoặc lỗi. Trong task hữu hạn, còn có rủi ro runner trả về **trước khi future hoàn tất**.

Với **Spring Framework 6.1+**, một cách phổ biến là dùng `ContextPropagatingTaskDecorator` trong executor được Spring quản lý:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class TracingExecutorConfiguration {

    @Bean("taskWorkerExecutor")
    ThreadPoolTaskExecutor taskWorkerExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        executor.initialize();
        return executor;
    }
}
~~~

Decorator sử dụng khả năng context propagation được cung cấp bởi những thư viện tích hợp trong ứng dụng; cần dependency và thread-local accessors phù hợp với tracing bridge. Không hứa nó sẽ tự propagate mọi context tùy chỉnh nếu chúng chưa được đăng ký.

Sử dụng executor và **chờ toàn bộ future quan trọng**:

~~~java
CompletableFuture<Void> first = CompletableFuture.runAsync(
    () -> service.process("partition-a"), taskWorkerExecutor);

CompletableFuture<Void> second = CompletableFuture.runAsync(
    () -> service.process("partition-b"), taskWorkerExecutor);

CompletableFuture.allOf(first, second).join();
~~~

Nếu một future lỗi, `join()` ném `CompletionException`; không nuốt lỗi, và cần cấu hình timeout/chính sách retry riêng. Phần này minh họa propagation **trong cùng JVM**, không thay thế việc inject/extract context qua HTTP/message/task launch sang một JVM khác.

## 10. Từ API hoặc Data Flow sang một JVM Spring Cloud Task mới

Đây là ranh giới quan trọng nhất đối với Spring Cloud Task: một scheduler hoặc TaskLauncher thường **tạo tiến trình mới**, không gọi trực tiếp một method trong JVM hiện tại.

~~~mermaid
flowchart LR
    A["API / Spring Cloud Data Flow"] --> B["TaskLauncher / Kubernetes Job"]
    B --> C["JVM task mới"]
    C --> D["ApplicationRunner root observation"]
    D --> E["HTTP / Broker / downstream spans"]
    A -. "Context phải được truyền có chủ đích" .-> C
~~~

**Không có propagation tự động chỉ nhờ parentTaskExecutionId.** `parentTaskExecutionId` là quan hệ trong **TaskRepository**, còn `traceparent` là context tracing. Khi TaskLauncher tạo JVM mới, current thread/span của API hoặc manager không tự tồn tại ở worker.

Một hợp đồng khởi chạy cần phân tách:

| Dữ liệu | Mục đích | Nơi chuyển |
|---|---|---|
| `businessDate`, `tenant`, `revision` | Đầu vào nghiệp vụ, thường xác định idempotency | Arguments/JobParameters hoặc repository nghiệp vụ |
| `parentTaskExecutionId` | Lineage giữa TaskExecution cha–con | Cơ chế parent-execution-id của Spring Cloud Task nếu dùng |
| `traceparent`, `tracestate` | Ngữ cảnh tracing, nếu tổ chức cho phép truyền | Carrier an toàn được launcher/worker hỗ trợ |
| `correlationId` / `requestId` | Nối log và các lần chạy, có chính sách dữ liệu riêng | Request/command metadata không nhạy cảm |
| DB/API credentials | Quyền truy cập runtime | Secret manager/environment được bảo vệ |

Nếu task được kích hoạt từ API, có hai chiến lược:

**A. Trace mới tại mỗi task; liên kết bằng correlation ID.** Đơn giản, an toàn với task lâu và scheduled task. Lưu một opaque request ID/biz key ở log của API và task, tìm hai trace riêng qua metadata liên quan. Đây thường là lựa chọn tốt khi Job chờ trong queue lâu hoặc có nhiều retry.

**B. Truyền W3C context qua carrier có kiểm soát.** API/launcher inject context vào launch request metadata; worker extract khi khởi động và tạo span trong context đó. Nếu là task launch qua Kubernetes, việc đưa `traceparent` vào env/args phải cân nhắc quyền đọc Pod/command line, validation và retention. Đừng mở đường đưa giá trị header tùy ý từ người ngoài thành parent đáng tin cậy.

Với job có độ trễ hàng giờ, **span link hoặc correlation ID** có thể biểu diễn quan hệ tốt hơn việc buộc một trace kéo dài bất thường.

## 11. Gắn TaskExecution, Spring Batch và trace với nhau

`TaskExecution` có ID mỗi lần chạy. `JobExecution` và `StepExecution` là metadata **khác** của Spring Batch. Muốn điều tra toàn bộ luồng, nên log có cấu trúc các ID đúng cấp:

~~~text
event=task.started
task.name=invoice-sync-task
task.execution.id=8041
business.key=tenant-A/INVOICE_SYNC/2026-11-23/revision-1
trace.id=3b0a...9df1

event=batch.step.finished
task.execution.id=8041
job.execution.id=912
step.execution.id=1007
step.name=importInvoices:partition2
trace.id=3b0a...9df1
~~~

Đây là **định dạng log đề xuất**, không phải output mặc định của Spring Cloud Task hoặc Spring Batch. Spring Boot + tracing có thể đưa `traceId` và `spanId` vào MDC/log pattern **khi có current span**, nhưng các key nghiệp vụ và ID framework cần được gắn từ nguồn đáng tin cậy.

### Dùng TaskExecutionListener để ghi nhận ID

Một listener có thể nhận `TaskExecution` và log định danh:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.task.listener.TaskExecutionListener;
import org.springframework.cloud.task.repository.TaskExecution;
import org.springframework.stereotype.Component;

@Component
class TaskLifecycleLogger implements TaskExecutionListener {

    private static final Logger log =
        LoggerFactory.getLogger(TaskLifecycleLogger.class);

    @Override
    public void onTaskStartup(TaskExecution execution) {
        log.info("task.started taskName={} taskExecutionId={}",
            execution.getTaskName(), execution.getExecutionId());
    }

    @Override
    public void onTaskFailed(
            TaskExecution execution, Throwable throwable) {
        log.error("task.failed taskExecutionId={} errorType={}",
            execution.getExecutionId(),
            throwable.getClass().getSimpleName());
    }

    @Override
    public void onTaskEnd(TaskExecution execution) {
        log.info("task.ending taskExecutionId={} exitCode={}",
            execution.getExecutionId(), execution.getExitCode());
    }
}
~~~

**Không mặc định trace ID tồn tại trong cả ba callback.** Nếu root observation chỉ được mở bên trong `ApplicationRunner` thì nó không nhất thiết active trong `onTaskStartup` hoặc `onTaskEnd`. Muốn log có trace ID tại các điểm này, cần thiết kế scope/correlation riêng phù hợp với lifecycle và version.

Có thể lưu liên kết `taskExecutionId ↔ traceId` trong hệ thống audit/monitoring của dự án, nhưng không cần biến một trace ID thành khóa duy nhất của `TASK_EXECUTION`. Nếu tạo custom table, cần bảo vệ quyền đọc, retention và tránh làm callback listener thất bại do gọi hệ thống tracing chậm.

## 12. Tracing trong Spring Batch và remote partitioning

Trong ứng dụng task khởi chạy Spring Batch:

- `TaskExecutionId` là một lần chạy ứng dụng.
- `JobInstance` nhận diện công việc Batch theo tên Job và identifying JobParameters.
- `JobExecutionId` là một lần chạy/restart JobInstance.
- `StepExecutionId` định danh Step execution hoặc partition.
- `traceId`/`spanId` thuộc hệ thống tracing và có vòng đời riêng.

Khi dùng **remote partitioning**, manager có thể launch nhiều worker JVM. Context tracing của manager **không tự chuyển sang worker** bằng `JobRepository` hoặc `ExecutionContext`. Thay vào đó, cần carrier/giao thức propagation được thiết kế rõ hoặc dùng trace mới, liên kết bằng StepExecution ID và business key.

Không lưu raw credentials hoặc toàn bộ tracing baggage vào `JobParameters`/`ExecutionContext`: những dữ liệu đó được serialize/lưu vào metadata, có thể bị nhiều dịch vụ đọc. Nếu cần lưu opaque correlation ID trong metadata Batch, đánh giá cardinality, bảo mật và thời gian retention.

### Chọn span cho batch dài

Không nên tạo một span cho từng item trong hàng triệu bản ghi. Nên chọn cấp hạt phù hợp:

| Cấp độ | Span/observation gợi ý | Thuộc tính |
|---|---|---|
| Toàn task | `task.invoice.sync` | `task.name`, `operation` |
| Toàn Job | `batch.job.import` | Job name, status |
| Từng Step | `batch.step.validate` / `batch.step.import` | Step name, status, attempt |
| Từng partition | `batch.partition.process` | partition name hoặc shard có số lượng hữu hạn |
| Outbound HTTP | Client span tự động nếu instrumented | URL template, method, status (không raw sensitive URL) |
| Message publish/consume | Producer/consumer span | Destination đã được giới hạn cardinality |

**Tránh dùng `taskExecutionId`, user ID, file path duy nhất, invoice ID hoặc business key làm low-cardinality metric tag.** Trong tracing, các ID này có thể là span attributes ở mức có kiểm soát nếu không nhạy cảm, nhưng không nên tạo hàng triệu time series metrics.

## 13. Error, retry và thời gian xử lý: diễn giải trace đúng

Ví dụ TaskExecution 8041 chạy lần đầu và gọi partner API bị timeout:

~~~mermaid
sequenceDiagram
    participant O as Scheduler
    participant T as Task Attempt 1
    participant P as Partner API
    participant DB as Business DB
    O->>T: Chạy invoice-sync ngày 23
    T->>P: POST verify invoice
    P--xT: Timeout / mất phản hồi
    T->>DB: Đối chiếu trạng thái đã lưu
    T-->>O: FAILED theo exit policy
    O->>T: Retry tạo TaskExecution mới
    T->>DB: Kiểm tra idempotency key
    T->>P: Gọi lại nếu xác minh chưa xử lý
~~~

Một client span có trạng thái lỗi hoặc timeout cho biết **caller không nhận được kết quả mong đợi**. Nó **không chứng minh** partner chưa thực hiện giao dịch. Nếu partner đã commit rồi response bị mất, retry mù quáng có thể gây tác động trùng.

Do đó khi phân tích:

1. Đọc trace để biết endpoint, latency và exception.
2. Đọc TaskExecution để biết attempt và mã thoát.
3. Đọc business state, outbox hoặc trạng thái ở đối tác bằng **idempotency key**.
4. Quyết định retry, reconcile hoặc dừng theo chính sách nghiệp vụ.

Mỗi retry có thể là trace riêng; có thể ghi **attempt number**, **business key đã che dữ liệu nhạy cảm** và **link tới trace trước** ở hệ thống audit. Không dùng trace sampling làm tiêu chí “không có lỗi”: span có thể bị bỏ lấy mẫu hoặc mất khi exporter không sẵn sàng.

## 14. Sampling, cardinality và chi phí quan sát

Spring Cloud Task thường chạy trong những đợt ngắn nhưng có thể gọi hàng nghìn request. Nếu mở span cho mỗi item và sampling 100%, số span có thể vượt ngân sách.

| Quyết định | Lợi ích | Rủi ro |
|---|---|---|
| Sampling mọi trace trên staging | Dễ kiểm tra propagation, đầy đủ dữ liệu thử | Không nên áp nguyên vào tải production |
| Head-based sampling ở ứng dụng | Giảm lưu lượng và chi phí exporter | Có thể bỏ lỡ trace của lỗi hiếm |
| Tail-based sampling ở Collector/backend | Có thể ưu tiên trace lỗi/chậm sau khi quan sát kết quả | Cần buffer/memory, topology phù hợp và không khôi phục được span đã không gửi |
| Ít span, bao các bước trọng yếu | Giảm overhead, dễ đọc cây trace | Thiếu chi tiết item-level nếu thiết kế quá thô |
| Log cấu trúc + task metadata | Dấu vết điều tra cả khi trace bị sample | Cần retention, bảo mật và correlation rõ |

**Không dùng business key có cardinality cao làm metric label** như `tenantId` có hàng trăm nghìn giá trị, `invoiceId`, `taskExecutionId` hay raw URL chứa ID. Có thể ghi một số trường vào span attributes ở mức cần thiết và được kiểm soát; trace vẫn chịu giới hạn kích thước.

Nếu cần phát hiện mọi job thất bại, **alert dựa vào TaskRepository, scheduler/Job status hoặc metric tổng hợp**, không chỉ dựa vào số trace lỗi đã được sample.

## 15. Flush telemetry trước khi JVM task thoát

Đây là khác biệt quan trọng của ứng dụng **hữu hạn**: exporter thường gửi span **bất đồng bộ hoặc theo batch**. Một JVM kết thúc quá nhanh có thể thoát trước khi Collector nhận đủ dữ liệu.

Vòng đời mong muốn:

~~~mermaid
flowchart TD
    A["Mở observation task"] --> B["Thực thi nghiệp vụ"]
    B --> C["Stop observations/spans"]
    C --> D["Đóng Spring context có kiểm soát"]
    D --> E["Exporter/SDK shutdown hoặc flush theo integration"]
    E --> F["JVM trả exit code cho scheduler"]
    B --> G{"SIGKILL, crash, node mất điện"}
    G --> H["Không bảo đảm flush hoặc TaskRepository end"]
~~~

Khuyến nghị:

- Không gọi `System.exit(0)` hoặc `Runtime.halt(...)` từ giữa runner.
- Dùng shutdown lifecycle của Spring Boot: khi cần exit code tường minh, mẫu `SpringApplication.exit(context)` rồi `System.exit(code)` ở entrypoint, sau khi nghiệp vụ đã kết thúc.
- Dùng integration/exporter được Spring quản lý để có cơ hội close/flush theo lifecycle; nếu tự tạo SDK, phải tự quản lý `forceFlush`/`shutdown` đúng API và timeout.
- Không phát hàng loạt future rồi kết thúc JVM; runner phải chờ những việc bắt buộc hoàn tất.
- Giới hạn network timeout khi export; **không để sự cố telemetry làm treo vô hạn Job nghiệp vụ**.
- Với Kubernetes, có `terminationGracePeriodSeconds` và signal forwarding đúng, nhưng không hứa `SIGKILL` hoặc OOMKill sẽ chạy callback.

**Không có bảo đảm 100% dữ liệu trace đã xuất khi Job thành công** nếu Collector không sẵn sàng, batch exporter bị đầy hoặc tiến trình bị kill. Vì thế TaskRepository/logs vẫn cần tồn tại ngoài tracing backend.

## 16. Bảo mật và trust boundaries khi propagate trace

Distributed tracing truyền dữ liệu qua biên giới ứng dụng. Những header đến từ người ngoài hoặc đối tác không phải lúc nào cũng đáng tin.

Nguyên tắc:

1. **Không lấy trace ID làm bằng chứng xác thực.** Header `traceparent` là dữ liệu quan sát có thể bị client tự đặt, không thay thế `Authorization` hay JWT.
2. **Kiểm tra/giới hạn incoming baggage.** Không để arbitrary baggage tạo metric tags, log fields hoặc header outbound không kiểm soát.
3. **Chỉ propagate qua endpoint tin cậy theo chính sách.** Có thể cần tạo root trace mới tại trust boundary và giữ một correlation ID nội bộ thay vì kế thừa trace bên ngoài.
4. **Không ghi PII, token hoặc raw business payload vào span attributes.** Dùng code/mã loại lỗi và request size/status phù hợp.
5. **Bảo vệ Collector:** TLS, authentication, NetworkPolicy, retention, RBAC và quyền truy cập tracing UI.
6. **Đánh giá quan hệ xuyên tenant:** trace data không được cho phép một tenant tra hoạt động của tenant khác.
7. **Tránh raw URL chứa ID hoặc query string nhạy cảm:** gắn `http.route`/URL template thay vì mọi URI đầy đủ khi có thể.

Trong task đa tenant, business key cần đủ để idempotency nhưng không nhất thiết ghi nguyên vào tracing. Dùng opaque correlation token hoặc hash theo chính sách lưu trữ và quyền truy cập.

## 17. Lỗi thường gặp và cách chẩn đoán

| Biểu hiện | Nguyên nhân có thể | Kiểm tra |
|---|---|---|
| Không thấy span của task dù có TaskExecution | Chưa tạo observation/root span; thiếu tracing bridge/exporter | Xem dependency, code Observation, sampling, exporter logs |
| Trace dừng tại API, không nối tới task JVM | TaskLauncher không propagate context qua process boundary | Thiết kế carrier, extract hoặc correlation/span link |
| HTTP downstream hiện trace khác | Dùng client builder không instrumented, mất active scope, propagation bị proxy xóa | Kiểm tra `traceparent` outbound/inbound trên môi trường thử |
| Consumer có trace ID khác producer | Chưa instrument producer/consumer hoặc headers bị mất | Kiểm tra message carrier, propagation và instrumentation |
| `@Async` span thành root mới | Mất thread-local context khi đổi executor | ContextPropagatingTaskDecorator hoặc snapshot/context propagation |
| Trace biến mất khi JVM thoát nhanh | SDK/exporter chưa flush, Collector không nhận | Xem shutdown lifecycle, timeout, exporter và collector logs |
| Trace có nhưng không có TaskExecution ID | Chưa log/gắn correlation riêng | TaskExecutionListener, structured logs và audit mapping |
| TaskExecution còn `END_TIME IS NULL` | Process có thể vẫn chạy hoặc chết trước commit metadata | Đối chiếu JVM/Pod, logs và business state |
| Metrics tăng cardinality bất thường | Gắn invoiceId/taskExecutionId vào low-cardinality tags | Loại ID khỏi metric labels, kiểm soát span attributes |
| Trace chứa password hoặc PII | Ghi headers, raw exception, payload hoặc baggage không lọc | Sanitization, allowlist, RBAC, retention |
| HTTP timeout nhưng partner có kết quả | Request đã xử lý nhưng response thất lạc | Reconcile theo idempotency key trước retry |
| Span rất dài hoặc hàng triệu spans | Observation quá thô hoặc span mỗi item | Chọn span theo bước/chunk, sampling và giới hạn |
| Tracing hoạt động trên localhost, hỏng ở Kubernetes | Endpoint/TLS/NetworkPolicy/Collector config sai | Test kết nối OTLP, quyền network, resource limits |
| Chỉ có trace cho một số lần chạy | Sampling, batch buffer, restart/crash | Đối chiếu TaskRepository và scheduler status |

### Quy trình chẩn đoán ngắn

1. Xác nhận **task nghiệp vụ đã thực sự chạy**, có TaskExecution/JobExecution và log tương ứng.
2. Xác nhận có root observation/span tại runner, tracing bridge, exporter và Collector.
3. Trên staging, tạm dùng sampling 100% và bật log exporter thích hợp **không lộ secret**.
4. Kiểm tra HTTP/message headers thực tế qua điểm quan sát an toàn; xác minh **trace ID giống nhau, span ID khác nhau đúng quan hệ**.
5. Với async executor, kiểm tra current span khi vào worker thread và sau khi chuyển qua client.
6. Với TaskLauncher/JVM mới, phân biệt propagation thực sự với correlation ID chỉ để nối log.
7. Khi task kết thúc, xác minh span đã stop và exporter có thời gian flush; đối chiếu trace backend.
8. Nếu thiếu telemetry, không kết luận nghiệp vụ chưa chạy: dùng business DB, TaskRepository và scheduler.

## 18. Bài thực hành: trace từ task sang HTTP và message consumer

### Mục tiêu

Xây ứng dụng `invoice-sync-task` không có web server, chạy hữu hạn qua Spring Cloud Task, gọi một REST API và phát message sau khi lưu dữ liệu; quan sát được trace/spans mà không dùng ID framework thay cho tracing context.

### Các bước

1. **Chuẩn bị backend:** chạy OpenTelemetry Collector và một tracing UI phù hợp. Bảo đảm endpoint OTLP có thể được JVM task gọi tới.
2. **Bật instrumentation:** thêm Actuator, Micrometer Tracing bridge và OTLP exporter tương thích; cấu hình `management.otlp.tracing.endpoint`.
3. **Tạo root observation:** wrap phần nghiệp vụ trong `ApplicationRunner` bằng `Observation.createNotStarted(...).observe(...)`.
4. **Gọi HTTP:** dùng `RestClient.Builder` instrumented, xác minh outbound `traceparent` và downstream span nếu dịch vụ nhận hỗ trợ.
5. **Publish message:** bật producer observation/propagation theo thư viện đang dùng; consumer phải extract context và tạo span. Kiểm tra span bị đứt khi tắt instrumentation để hiểu ranh giới.
6. **Thử thread pool:** chạy một partition qua executor chưa được decorate, so với executor dùng `ContextPropagatingTaskDecorator`.
7. **Ghi correlation:** log `taskExecutionId`, business key đã giảm nhạy cảm và trace ID trong nơi có scope; không ép cùng trace ID cho retry.
8. **Thử lỗi:** cho API trả timeout/5xx, xác minh client span lỗi, TaskExecution thất bại theo exit policy và business state không bị nhân đôi khi retry.
9. **Thử shutdown:** cho JVM thoát ngay sau khi runner hoàn tất; xem span có đủ trên tracing backend, điều chỉnh graceful close/flush và timeout theo nhu cầu.
10. **Thử process boundary:** launch một worker JVM khác từ task; xác minh không tự có parent trace; sau đó triển khai carrier hoặc correlation strategy và so kết quả.

Bảng đối chiếu:

| Kiểm tra | Kỳ vọng |
|---|---|
| TaskExecution và trace ID | Là hai ID riêng, liên kết bằng log/audit khi cần |
| Observation của runner | Có span đại diện công việc hữu hạn |
| HTTP client → server | Header/context được truyền nếu cả hai phía instrumented |
| Producer → consumer | Message header được inject/extract nếu broker integration hỗ trợ |
| Executor task | Context được bảo toàn nếu có propagation đúng |
| Worker JVM mới | Cần propagation/correlation qua process boundary |
| Task retry | Business key ổn định; trace/attempt ID có thể khác |
| Telemetry failure | Không được làm sai kết quả nghiệp vụ; TaskRepository vẫn truy vết được |
| Security | Không xuất secret/PII qua span attributes và baggage |

## 19. Checklist triển khai production

- Xác định một **root observation/span rõ ràng** cho công việc Spring Cloud Task non-web.
- Chọn Micrometer Tracing/OpenTelemetry và exporter theo đúng phiên bản Spring Boot/Cloud.
- Dùng **HTTP client builder có instrumentation**; kiểm tra W3C `traceparent`/`tracestate` qua từng hop.
- Với broker, bật và kiểm thử **producer inject + consumer extract**; không coi message ID là trace ID.
- Với `@Async`/thread pool, dùng context propagation và chờ mọi future bắt buộc.
- Với task con/JVM khác, thiết kế **carrier hoặc span link/correlation ID**, không dựa vào parent TaskExecution ID để propagate trace.
- Phân biệt TaskExecution, JobExecution, StepExecution, trace ID và business key trong logs/dashboards.
- Không dùng ID cardinality cao làm low-cardinality metric labels.
- Lựa chọn sampling, span granularity và retention phù hợp chi phí; không dùng traces làm nguồn alert duy nhất.
- Không đưa secret, PII, raw payload/arguments hoặc arbitrary baggage sang hệ thống ngoài.
- Cho exporter/SDK cơ hội flush khi đóng Spring context; kiểm tra graceful shutdown và giới hạn timeout.
- Đối chiếu TaskRepository, scheduler/container và business state trước khi retry sau crash.
- Kiểm thử cả đường thành công, downstream timeout, message redelivery, worker JVM mới và SIGTERM/SIGKILL.

**Kết luận:** Distributed tracing bổ sung **đường đi và độ trễ liên hệ giữa các hệ thống** cho metadata vòng đời mà Spring Cloud Task đã ghi trong TaskRepository. Để hoạt động hiệu quả, cần **tạo span cho runner hữu hạn**, **propagate context theo W3C qua những carrier được hỗ trợ**, và **xử lý rõ ràng các ranh giới thread, broker, scheduler và JVM mới**. Trace giúp điều tra sự cố, nhưng không thay thế exit code, checkpoint, idempotency hay dữ liệu nghiệp vụ. Khi ba lớp đó được liên kết bằng correlation an toàn, các task chạy theo lịch hoặc theo yêu cầu mới có thể quan sát và phục hồi một cách đáng tin cậy.

### Tài liệu tham khảo

- [Spring Cloud Task Reference](https://docs.spring.io/spring-cloud-task/reference/)
- [Spring Boot Reference — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/)
- [Micrometer Context Propagation Reference](https://docs.micrometer.io/context-propagation/reference/)
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/)
- [W3C Trace Context Specification](https://www.w3.org/TR/trace-context/)
