# Trace ID trong Spring Boot: liên kết một request xuyên các service

Trong chương **Tracing** của module **SPRING_BOOT_OBSERVABILITY**, **Trace ID** là định danh dùng để liên kết các bước xử lý thuộc cùng một distributed trace. Khi một yêu cầu đi từ API Gateway tới dịch vụ đơn hàng, dịch vụ thanh toán và database, ta không muốn phải dò từng file log riêng lẻ theo thời gian gần đúng. Một Trace ID được truyền đúng cách giúp tìm các span cùng trace, đặt chúng lên một dòng thời gian và đối chiếu logs để xác định bước nào lỗi hoặc chậm.

Spring Boot có thể tích hợp **Micrometer Observation** với Micrometer Tracing, tracing bridge, context propagation và exporter để tạo distributed traces. Cùng với metrics và logs, Trace ID là một mắt xích để điều tra sự cố, nhưng **Trace ID không thay thế metric, không tự giải thích nguyên nhân lỗi và không bảo đảm trace đã được xuất**.

Sau bài học, người đọc cần phân biệt Trace ID với Span ID và request ID, hiểu W3C Trace Context, biết xem Trace ID trong log/trace, nhận ra lỗi mất propagation khi chạy async hoặc gọi service khác, và tránh đưa Trace ID vào metric tags có cardinality cao.

## 1. Trace, span và Trace ID là gì?

**Trace** biểu diễn một chuỗi hoặc đồ thị các thao tác liên quan trong một giao dịch phân tán. Mỗi **span** là một đơn vị công việc có thời gian bắt đầu/kết thúc, metadata và có thể có quan hệ cha–con với một span khác. **Trace ID** xác định trace mà các span đó thuộc về; **Span ID** xác định một span cụ thể.

Ví dụ một request xác nhận đơn hàng:

```text
Trace ID: 4bf92f3577b34da6a3ce929d0e0e4736

API service
  Span A: POST /orders/confirm              [spanId=a111111111111111]
    |
    +--> Span B: order.confirm               [spanId=b222222222222222]
           |
           +--> Span C: inventory.reserve    [spanId=c333333333333333]
           |       |
           |       +--> Span D: DB call      [spanId=d444444444444444]
           |
           +--> Span E: POST payment-service [spanId=e555555555555555]
                    |
                    +--> Span F: authorize   [spanId=f666666666666666]

Mọi span trên có cùng Trace ID, nhưng mỗi span có Span ID riêng.
```

Các ID trong sơ đồ là ví dụ để minh họa, không phải output đã thu được từ hệ thống.

| Khái niệm | Phạm vi | Dùng để làm gì? |
| --- | --- | --- |
| **Trace ID** | Toàn bộ một trace; có thể đi qua nhiều service/process | Tìm và liên kết các span/logs của cùng giao dịch phân tán |
| **Span ID** | Một span trong trace | Xác định thao tác cụ thể, hỗ trợ quan hệ cha–con |
| **Parent Span ID** | Quan hệ trong cây span | Biết span nào là cha của span hiện tại |
| **Request ID / Correlation ID riêng** | Theo quy ước ứng dụng/gateway | Theo dõi request hoặc một workflow nghiệp vụ; không mặc nhiên bằng Trace ID |
| **Business ID** | Miền nghiệp vụ như order/payment | Truy vấn trạng thái nghiệp vụ; không nên coi là ID của trace |

Điểm cốt lõi: **hai span có cùng Trace ID không có nghĩa chúng là cùng một span**, và hai request HTTP liên quan một workflow không bắt buộc chung Trace ID nếu workflow tạo trace mới theo thiết kế. Nếu muốn nối một chuỗi công việc dài qua nhiều trace, có thể cần message metadata, span links hoặc business correlation được quản lý riêng.

## 2. Hình dạng Trace ID và Span ID theo W3C Trace Context

Trong chuẩn **W3C Trace Context**, Trace ID (`trace-id`) gồm **16 byte = 32 ký tự hexadecimal**, còn Parent ID (ID của span được khai báo trong header) gồm **8 byte = 16 ký tự hexadecimal**. Các định danh toàn số 0 không hợp lệ trong định dạng này. Ví dụ:

```text
trace-id:  4bf92f3577b34da6a3ce929d0e0e4736   (32 hex)
span-id:   00f067aa0ba902b7                   (16 hex)
```

Khi gọi service khác, header HTTP `traceparent` có dạng:

```text
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
             ^^ ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ ^^^^^^^^^^^^^^^^ ^^
             |           trace-id                   parent-id       flags
             version
```

Ở định dạng version `00`:

- **`00`**: phiên bản định dạng `traceparent`.
- **`4bf92f...`**: Trace ID để liên kết các span thuộc cùng trace.
- **`00f067...`**: ID của span **đại diện phía gửi** trong ngữ cảnh được truyền; span nhận có thể được tạo với Span ID mới và dùng đây làm parent.
- **`01`**: trace flags có sampled bit được bật trong ví dụ; `00` thường biểu thị sampled bit không bật. Các bit flags khác không nên bị diễn giải tùy tiện.

Header `tracestate` có thể chứa dữ liệu trạng thái tracing mở rộng theo vendor. **`tracestate` không phải Trace ID** và không nên dùng như nơi đưa payload nghiệp vụ. **Baggage** là cơ chế khác để truyền một số key-value theo context; baggage có rủi ro về dung lượng header và quyền riêng tư.

Một Trace ID theo W3C có độ dài cố định, nhưng khi hiển thị qua backend/bridge khác có thể gặp quy ước lịch sử về độ dài hoặc định dạng. Không tự nối, cắt hoặc tạo lại Trace ID chỉ để “đồng nhất” giao diện. Nên dùng tracer/propagator chuẩn thay vì tự thao tác header bằng chuỗi.

## 3. Trace ID được tạo và truyền qua những bước nào?

Với ứng dụng Spring Boot đã cấu hình tracing instrumentation, trường hợp phổ biến là:

1. **Nhận request:** HTTP server instrumentation đọc trace context từ header hợp lệ (nếu có); nếu không có context phù hợp, tracer có thể khởi tạo trace mới.
2. **Tạo span trong tiến trình:** một HTTP server span, business observation hoặc database/client span có thể chia sẻ Trace ID và có Span ID riêng.
3. **Gọi downstream:** HTTP client instrumentation đưa tracing context vào request outbound qua propagator; downstream tiếp tục trace khi xử lý đúng context.
4. **Ghi logs:** khi log correlation được cấu hình, MDC/logging pipeline có thể gắn `traceId`/`spanId` của context đang hoạt động.
5. **Xuất trace:** exporter gửi các span đã được thu thập tới tracing backend theo sampling, SDK và pipeline cấu hình.

```text
Client
  |
  | traceparent (nếu client đã có tracing context)
  v
orders-service                    payment-service
  |                                      ^
  | HTTP SERVER SPAN                     |
  | traceId=T                            |
  | spanId=A                             |
  |                                      |
  +-- order.confirm                      |
  |    traceId=T, spanId=B                |
  |                                      |
  +-- HTTP client span ------------------+
       traceId=T, spanId=C       traceparent
                                    |
                                    v
                             HTTP SERVER SPAN
                             traceId=T, spanId=D
```

Mỗi bước có thể bị ảnh hưởng bởi instrumentation, propagator, trust boundary, thread context và sampling. Nếu service gọi downstream bằng một HTTP client không được instrument hoặc tự xóa headers, downstream có thể khởi tạo **một Trace ID mới**, làm trace bị chia đoạn.

**Propagation khác exporter.** Propagation giúp những service tham gia cùng context; exporter giúp backend nhìn thấy các span. Có thể propagation đúng nhưng exporter lỗi hoặc sampler không ghi span, nên chưa thấy trace hoàn chỉnh trên dashboard.

## 4. Thiết lập Micrometer Tracing với Spring Boot

Trong các ứng dụng Spring Boot sử dụng Actuator và Micrometer Tracing, cần có **tracing bridge** (ví dụ OpenTelemetry bridge hoặc Brave bridge) cùng với exporter/back-end tương thích. Ví dụ Maven cho một kiến trúc OpenTelemetry/OTLP (phiên bản thư viện do Spring Boot BOM phù hợp quản lý):

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-tracing-bridge-otel</artifactId>
    </dependency>
    <dependency>
        <groupId>io.opentelemetry</groupId>
        <artifactId>opentelemetry-exporter-otlp</artifactId>
    </dependency>
</dependencies>
```

Đây là một **phương án tham khảo theo thế hệ Spring Boot/Micrometer có hỗ trợ các dependency đó**, không phải yêu cầu dùng đồng thời OpenTelemetry bridge và Brave bridge. Một số phiên bản Spring Boot mới có starter/tracing auto-configuration khác; cần xác minh phiên bản dự án thực tế và giữ các dependency nhất quán theo BOM. Nếu chọn Brave/Zipkin, đổi bridge và đường exporter phù hợp thay vì trộn hai tracer không chủ đích.

Ví dụ cấu hình ứng dụng trong stack Spring Boot hỗ trợ các property sau:

```yaml
spring:
  application:
    name: orders-service

management:
  tracing:
    sampling:
      probability: 0.1
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
```

Giải thích:

- `sampling.probability: 0.1` là ví dụ dùng sampling xác suất, không bảo đảm chính xác **10% của mỗi nhóm request** hay luôn có trace của một request đơn lẻ.
- `management.otlp.tracing.endpoint` phụ thuộc phiên bản Spring Boot và OTLP exporter; đường `/v1/traces` thường dùng với OTLP/HTTP trên cổng 4318. Nếu exporter đang dùng gRPC hoặc có cấu hình riêng, endpoint/protocol sẽ khác.
- Giá trị `localhost` chỉ hợp lý khi collector/backend chạy trên cùng network namespace với ứng dụng. Trong Docker/Kubernetes, `localhost` thường trỏ tới chính container/pod đang chạy, không tự động là collector ở máy khác.
- Để thấy trace trong backend cần có receiver, exporter, kết nối mạng và chính sách ingest phù hợp. Chỉ khai báo property hoặc khởi tạo span không chứng minh trace đã xuất.

**Trước khi test sampling**, cần xác minh dependency, cấu hình tracing, service name, propagation format, log correlation và exporter đang hoạt động trên phiên bản cụ thể. Không hardcode mã trace/span hoặc tự thêm `traceparent` ở controller như một giải pháp thay cho instrumentation.

## 5. Xem Trace ID trong mã Java

Micrometer Tracing cung cấp `Tracer` để đọc span đang hoạt động. Khi một method nằm trong ngữ cảnh HTTP server tracing hoặc một custom observation có tracing handler, ta có thể đọc Trace ID của span hiện tại.

```java
import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class TraceContextReader {
    private static final Logger log =
            LoggerFactory.getLogger(TraceContextReader.class);

    private final Tracer tracer;

    public TraceContextReader(Tracer tracer) {
        this.tracer = tracer;
    }

    public void logCurrentTrace() {
        Span span = tracer.currentSpan();
        if (span == null) {
            log.info("No active tracing span on this execution context");
            return;
        }

        String traceId = span.context().traceId();
        String spanId = span.context().spanId();
        log.info("Working in traceId={} spanId={}", traceId, spanId);
    }
}
```

Điều cần hiểu:

- `tracer.currentSpan()` có thể trả về `null` nếu không có span đang hoạt động; không giả định mọi lần gọi đều có trace.
- Trace ID là định danh của **trace hiện hành**, không phải định danh người dùng hoặc đơn hàng. Nếu không cần gắn log thủ công, ưu tiên sử dụng **MDC/log correlation** đã được framework cấu hình để tránh lặp nội dung.
- Một span chỉ hiện trên backend khi có tracing infrastructure phù hợp, quyết định sampling và exporter thành công. Đọc được Trace ID trong JVM **không phải bằng chứng backend có trace**.

### Custom Observation tạo ranh giới nghiệp vụ

Ví dụ một thao tác xác nhận đơn hàng cần được nhìn rõ giữa HTTP server và HTTP client spans:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class OrderConfirmationService {
    private final ObservationRegistry registry;
    private final TraceContextReader traceContextReader;

    public OrderConfirmationService(
            ObservationRegistry registry,
            TraceContextReader traceContextReader) {
        this.registry = registry;
        this.traceContextReader = traceContextReader;
    }

    public void confirm(Runnable businessAction) {
        Observation.createNotStarted("order.confirm", registry)
                .lowCardinalityKeyValue("operation", "confirm")
                .observe(() -> {
                    traceContextReader.logCurrentTrace();
                    businessAction.run();
                });
    }
}
```

`Observation.observe(...)` quản lý vòng đời observation của đoạn đồng bộ. Nếu registry có tracing handler, custom observation **có thể tạo span con** với cùng Trace ID của request cha và Span ID riêng. Nếu không có bridge/tracing handler, observation vẫn có thể hoạt động nhưng không có tracing span tương ứng. Khi thêm observation, hãy đo đúng **một ranh giới nghiệp vụ có giá trị**, tránh đo trùng chính xác cùng HTTP/DB call đã được instrument.

Để gắn outcome/error, nên dùng tag thấp cardinality có tập giá trị hữu hạn như `result=success/declined/error`; không gắn `traceId` vào metric tag. Micrometer Observation có API ghi nhận error khi xảy ra exception; code nghiệp vụ vẫn phải xử lý/lan truyền exception theo hợp đồng bình thường.

## 6. Log correlation: tìm lại các log của cùng Trace ID

Một trong những lợi ích thực tế nhất của Trace ID là tương quan các log từ nhiều service. Khi Micrometer Tracing cùng MDC/logging integration được cấu hình, log event có thể mang `traceId` và `spanId` đang hoạt động.

Ví dụ hai dòng log giả định:

```text
2026-11-22 10:15:02 INFO  orders-service traceId=4bf92f3577b34da6a3ce929d0e0e4736 spanId=00f067aa0ba902b7 Order confirmation started
2026-11-22 10:15:02 WARN  payment-service traceId=4bf92f3577b34da6a3ce929d0e0e4736 spanId=1c42dd674d23ab12 Payment provider timed out
```

Hai dòng có **cùng Trace ID** nhưng Span ID khác nhau. Người trực vận hành có thể tìm Trace ID trong log backend, mở trace tương ứng ở tracing backend và xác định thứ tự các bước.

Trong một số phiên bản Spring Boot, MDC trace/span IDs đã được bổ sung vào log correlation pattern khi tracing được cấu hình đúng. Nếu sử dụng custom JSON encoder hoặc Logback pattern, cần kiểm tra chính xác cách đưa MDC fields vào log và tên khóa mà stack sử dụng. Không tự giả định mọi encoder luôn in `traceId`.

Ví dụ một Logback layout minh họa (chỉ áp dụng nếu app thực sự dùng pattern encoder và MDC keys tương ứng):

```text
%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] traceId=%X{traceId:-} spanId=%X{spanId:-} %logger - %msg%n
```

Không nên log **cả HTTP headers** chỉ để lấy trace context: headers có thể chứa token, cookie hoặc baggage nhạy cảm. Trace ID bản thân không phải mật khẩu nhưng có thể là một chìa khóa truy vấn tới dữ liệu nội bộ; cần quản lý quyền truy cập log/trace backend phù hợp.

**Trường hợp log có Trace ID nhưng không có trace trên backend:** có thể trace bị sampling loại bỏ, exporter bị lỗi, backend chưa ingest hoặc retention đã xóa dữ liệu. Không kết luận Trace ID trong log là sai chỉ từ việc tìm backend không thấy span.

## 7. Propagation qua HTTP: giữ nguyên Trace ID, tạo span mới

Khi service A gọi service B bằng HTTP client được instrument, tracing context có thể được inject vào outgoing request. Service B nhận context và tạo server span con. Trong W3C Trace Context, cả hai service sẽ dùng cùng Trace ID nếu propagation thành công.

```text
orders-service                       payment-service
   |
   | traceId=T
   | spanId=CLIENT_SPAN
   |
   +---- HTTP request ------------------------>
           traceparent: 00-T-CLIENT_SPAN-01
                                        |
                                        v
                               traceId=T
                               spanId=SERVER_SPAN_NEW
                               parentSpanId=CLIENT_SPAN
```

Các ký hiệu `T` và `CLIENT_SPAN` ở sơ đồ là biến khái niệm; **không phải** giá trị header có thể gửi trực tiếp. Trên mạng, `trace-id` và `parent-id` phải tuân thủ định dạng hexadecimal của W3C như mục 2.

Những nguyên nhân thường làm trace bị chia:

1. HTTP client chưa có instrumentation phù hợp với `RestClient`, `RestTemplate`, `WebClient` hay thư viện đang dùng.
2. Tạo client bằng tay hoặc bỏ qua cấu hình/bean builder có tích hợp observation, khiến tracing headers không được inject.
3. Gateway/proxy hoặc security filter xóa hoặc ghi đè `traceparent`.
4. Hệ thống hai phía dùng propagator/format không tương thích hoặc có chính sách trust boundary chủ động khởi tạo trace mới.
5. Downstream nhận context nhưng không mở scope đúng cho xử lý bất đồng bộ.

**Không lấy Trace ID từ header rồi tự gán vào một static variable hoặc ThreadLocal tùy ý.** Micrometer/OTel/Brave tracer và propagator cần đồng bộ Trace ID, Span ID, sampled flag, parent relationship và lifecycle. Tự làm thủ công rất dễ tạo trace không hợp lệ hoặc mất quan hệ cha–con.

## 8. Propagation qua thread, async và message consumer

Vấn đề phức tạp hơn khi công việc được giao sang executor, `@Async`, `CompletableFuture`, message broker hoặc scheduler. Một thread không tự thừa hưởng tracing context của thread khác; vì vậy **đọc `tracer.currentSpan()` ở worker thread có thể trả về null**.

Ví dụ anti-pattern:

```java
// Nếu executor không truyền context, trace trong thread mới có thể bị mất.
CompletableFuture.runAsync(() -> {
    // Công việc nền có thể không còn currentSpan của request cha.
    processOrder();
});
```

Với Spring Framework có `ContextPropagatingTaskDecorator` (ví dụ Spring Framework 6.1+), có thể cấu hình `ThreadPoolTaskExecutor` riêng để chụp/khôi phục context khi submit task:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
class OrderAsyncConfiguration {

    @Bean(name = "orderTaskExecutor")
    ThreadPoolTaskExecutor orderTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setThreadNamePrefix("order-worker-");
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        executor.initialize();
        return executor;
    }
}
```

Đây là cách minh họa cho **executor được cấu hình rõ ràng**, không có nghĩa tất cả lời gọi `CompletableFuture.runAsync()` mặc định sẽ sử dụng executor đó. Muốn propagation có hiệu lực, phải thực sự submit task vào executor phù hợp (hoặc dùng `@Async("orderTaskExecutor")` theo cơ chế Spring hỗ trợ), có dependency Micrometer Context Propagation và tracing integration tương ứng.

Với messaging, cần kiểm tra producer có inject trace context vào message headers và consumer có extract/open scope trước khi xử lý hay không. Một bước xử lý hàng giờ sau có thể cố ý tạo trace mới kèm **span link** tới trace trước, tùy thiết kế queue và semantics giao dịch; không phải mọi trường hợp đều bắt buộc giữ một trace vô hạn.

## 9. Sampling ảnh hưởng thế nào đến Trace ID?

**Sampling** kiểm soát những trace/span nào được ghi nhận hoặc xuất, nhằm giảm chi phí tracing. Nó khác với việc tạo và truyền trace context.

| Trường hợp | Trace ID trong tiến trình/log | Span xuất sang backend |
| --- | --- | --- |
| Trace được lấy mẫu, exporter hoạt động | Thường có khi span context hoạt động | Có thể xuất và tìm thấy |
| Trace không được lấy mẫu | Có thể vẫn có context/Trace ID phục vụ propagation và log correlation, tùy implementation | Thường không có span tương ứng trong backend |
| Exporter bị lỗi/đứt mạng | Context vẫn có thể tồn tại trong ứng dụng | Có thể mất hoặc trễ ingest |
| Không có tracing bridge/handler | Custom Observation vẫn có thể hoạt động cho metrics | Không có tracing spans từ observation đó |
| Context propagation bị mất | Thread/downstream có thể không có span hoặc khởi tạo trace mới | Trace bị đứt hoặc tách thành nhiều trace |

Ví dụ `sampling.probability: 0.1` không có nghĩa luôn giữ “cứ 10 request thì 1 request”. Quyết định sampling có thể phụ thuộc parent context, tracer/sampler và cấu hình service. Khi cần chắc chắn một giao dịch lỗi được giữ để điều tra, phải xem chiến lược sampling phù hợp như head/tail sampling, chính sách theo lỗi và khả năng collector/backend; không chỉ tăng một tỷ lệ rồi xem là đủ.

Metrics từ Micrometer Observation có thể vẫn được ghi qua metric handler trong khi trace bị sampled out. **Không dùng Trace ID làm tag của Counter/Timer** để “ghép” metrics với trace: Trace ID có cardinality cực lớn và làm bùng số time series. Hãy dùng metrics với low-cardinality tags để phát hiện vấn đề, sau đó lấy logs/traces ở khoảng thời gian tương ứng để điều tra chi tiết.

## 10. Trace ID có phải thông tin nhạy cảm không?

Trace ID không phải credential hay token xác thực, và tự nó không chứng minh danh tính người dùng. Tuy nhiên, nếu trace/log backend cho phép truy vấn theo ID, việc công khai Trace ID có thể giúp người khác **tham chiếu tới bản ghi vận hành**. Vì thế cần phân biệt:

- **Không dùng Trace ID để xác thực hoặc phân quyền.** Biết ID không có nghĩa được quyền đọc dữ liệu liên quan.
- **Kiểm soát truy cập log/trace backend.** Dữ liệu trong spans/logs có thể chứa tên endpoint, service hoặc thông tin chẩn đoán nội bộ.
- **Không ghi PII/secrets vào span attributes hoặc baggage.** Dù Trace ID không phải dữ liệu cá nhân, thông tin liên kết với nó vẫn có thể nhạy cảm.
- **Không tin mọi incoming trace context vô điều kiện.** Tại ranh giới không tin cậy cần validator, propagator và chính sách bảo vệ tài nguyên/sampling; tránh để client ép sinh telemetry quá lớn hoặc làm nhiễu correlation.
- **Không dùng Trace ID thay order ID.** Một đơn hàng có thể được chạm tới bởi nhiều trace (request tạo đơn, retry, batch reconciliation). Cần business correlation riêng khi truy vấn vòng đời đơn.

Về cardinality, Trace ID thường gần như khác nhau cho từng trace. Gắn `traceId` vào label của metric có thể tạo hàng triệu series dù chỉ có một tên metric. Tracing/logging systems phù hợp hơn để lưu tham chiếu high-cardinality có kiểm soát.

## 11. Quy trình điều tra: “trace bị mất giữa hai service”

Giả sử ứng dụng nhận yêu cầu `POST /checkout`, ghi log:

```text
orders-service  traceId=4bf92f3577b34da6a3ce929d0e0e4736  Payment request started
payment-service traceId=9d4c12e8bc974f32a1a5de33e478c001  Payment request failed
```

Vì hai Trace ID khác nhau, chưa thể kết luận payment service không được gọi. Đây là **dấu hiệu** rằng hai logs có thể thuộc trace khác nhau, hoặc propagation đã bị đứt, hoặc một service cố ý bắt đầu trace mới. Hãy điều tra theo thứ tự:

1. **Khớp giao dịch:** xác nhận logs thực sự thuộc cùng một lần gọi bằng thời gian, endpoint, mã kết quả và business correlation được phép. Không dựa duy nhất vào timestamp gần nhau.
2. **Kiểm tra outgoing client:** `orders-service` có HTTP client observation/instrumentation và propagator được cấu hình đúng không?
3. **Kiểm tra header qua ranh giới:** ở môi trường thử nghiệm an toàn, xác nhận `traceparent` có được inject/extract hợp lệ không; tránh log các headers chứa secrets.
4. **Kiểm tra gateway/service mesh:** proxy có xóa, biến đổi hoặc tạo lại trace context không? Có chính sách cố ý tạo trace mới tại trust boundary không?
5. **Kiểm tra thread/message context:** service có chuyển công việc sang executor/queue mà không propagation không?
6. **Kiểm tra sampling/exporter:** có thể propagation đã đúng ở một số bước nhưng các span không được xuất; không kết luận chỉ từ một trace viewer.
7. **Kiểm tra tên trace ID trong logs:** JSON encoder có đọc đúng MDC key/active scope không? Có log được ghi **ngoài scope** sau khi task đã hoàn tất không?
8. **Đối chiếu metrics:** khi payment provider timeout tăng, xem rate lỗi, HTTP/client latency và pool saturation; xác nhận sự cố có ảnh hưởng thực tế tới nhiều request.

### Bảng chẩn đoán nhanh

| Dấu hiệu | Khả năng cần xét | Bước kiểm chứng |
| --- | --- | --- |
| Một Trace ID xuất hiện ở nhiều service, Span ID khác nhau | Propagation và span creation có thể đúng | Mở trace, xem parent-child và timeline |
| Log service A có Trace ID, service B có ID mới | Header propagation, gateway, async, trust boundary | So client instrumentation, propagator và ingress |
| Cùng Trace ID nhưng không thấy span B ở backend | Sampling, exporter, collector, missing instrumentation | Kiểm tra sampled flag, exporter và SDK telemetry |
| `tracer.currentSpan() == null` trên worker thread | Không có active scope hoặc không propagate context | Dùng context-aware executor; kiểm tra thời điểm submit |
| Trace có span nhưng log không có trace ID | MDC/correlation pattern hoặc log ghi ngoài scope | Kiểm tra logging integration và lifecycle |
| Metrics có lỗi nhưng không tìm được trace | Sampling hoặc đường tracing bị thiếu | Kiểm tra ratio sampling, exporter; không gắn traceId vào metric |
| Một order ID gắn với nhiều Trace ID | Nhiều request, retry hoặc workflow bất đồng bộ | Dùng business correlation/links thích hợp |

## 12. Ví dụ kịch bản end-to-end

Một hệ thống gồm `orders-service`, `inventory-service` và `payment-service`. Trong giờ cao điểm, tỷ lệ lỗi thanh toán tăng từ 0,1% lên 3%. Nhóm vận hành có:

```text
Metrics:
  payment.authorize{provider="bank_a",outcome="error"} tăng
  http.server.requests latency p95 tăng

Logs:
  orders-service: "Payment call started" (traceId=T)
  payment-service: "Provider timeout"   (traceId=T)

Traces (một request được lấy mẫu):
  POST /checkout              [traceId=T, spanId=A]
    order.confirm             [traceId=T, spanId=B]
      payment.authorize       [traceId=T, spanId=C]
        HTTP POST provider    [traceId=T, spanId=D, duration cao]
```

Nhờ **Trace ID chung**, nhóm có thể mở trace của một request tiêu biểu, xác định provider HTTP call là nơi chậm, rồi đối chiếu với logs mô tả timeout. Tuy nhiên, không được chỉ dựa trên **một trace** để kết luận mọi request đều mắc cùng lỗi; metrics và số liệu backend cho thấy phạm vi, tỷ lệ và xu hướng. Nếu sampling không giữ một giao dịch lỗi cụ thể, logs vẫn có thể hữu ích cho chẩn đoán, và metrics vẫn cần bao phủ lưu lượng.

Phương pháp phối hợp các tín hiệu:

1. **Metrics:** phát hiện *khi nào*, *bao nhiêu*, *provider nào* gặp lỗi; chỉ dùng tags có số giá trị hữu hạn.
2. **Traces:** thấy *đường đi* và *nơi tốn thời gian* của request được ghi nhận; Trace ID liên kết các spans.
3. **Logs:** giải thích *loại lỗi* và quyết định nghiệp vụ; sử dụng Trace ID/Span ID để tìm đúng ngữ cảnh.
4. **Propagation và exporter:** bảo đảm Trace ID tiếp tục qua service, có spans trên backend khi được sampled và không bị mất vì cấu hình hay network.

## 13. Bài tập củng cố

Xét ba log sau (giả định):

```text
10:00:00.100 orders-service   traceId=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa spanId=1111111111111111 Checkout started
10:00:00.220 inventory-service traceId=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa spanId=2222222222222222 Inventory reserved
10:00:00.450 payment-service   traceId=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb spanId=3333333333333333 Payment declined
```

Trả lời các câu hỏi:

1. Có thể chắc chắn ba log thuộc một distributed trace không?
2. Vì sao hai log đầu có Span ID khác nhau nhưng Trace ID giống nhau?
3. Nếu payment-service thực sự xử lý lời gọi từ orders-service, hãy nêu ít nhất ba nguyên nhân khiến Trace ID của nó khác.
4. Khi biết Trace ID của một request chậm, vì sao không nên gắn nó làm tag của `http.server.requests`?
5. Nếu log có Trace ID nhưng tracing backend không tìm thấy trace, cần kiểm tra các tầng nào?

**Đáp án tham khảo:** Hai log đầu có cùng Trace ID và Span ID khác nhau, phù hợp với các bước khác nhau của một trace; còn log payment-service có Trace ID khác nên không thể khẳng định nó thuộc cùng trace nếu không có bằng chứng liên kết bổ sung. Có thể header propagation bị mất, service chủ động tạo trace mới, quá trình chuyển thread/message không khôi phục context hoặc hai logs không thuộc cùng một giao dịch. Trace ID là high-cardinality identifier, không phù hợp làm metric label. Khi thiếu trace ở backend, kiểm tra active span, sampling, propagator, exporter/collector và retention trước khi kết luận instrumentation sai.

### Checklist thực hành

| Bước | Kỳ vọng |
| --- | --- |
| Gọi một endpoint HTTP có tracing instrumentation | Có context/span hoạt động trong phạm vi xử lý thích hợp |
| Đọc `Tracer.currentSpan()` trong phạm vi đó | Có thể lấy Trace ID/Span ID; xử lý được trường hợp `null` |
| Gọi downstream qua HTTP client được instrument | Trace ID được giữ, span con/parent phù hợp |
| Chuyển task qua executor có propagation | Context được khôi phục trong worker, log correlation hoạt động |
| Gửi/nhận message có trace propagation | Producer/consumer xử lý header đúng stack hoặc sử dụng span links theo thiết kế |
| Giảm sampling | Không nhầm span thiếu trên backend với lỗi metric hoặc lỗi nghiệp vụ |
| Kiểm tra logs | Có trace/span correlation khi logging integration hoạt động, không làm lộ secrets |
| Kiểm tra metrics | Có lỗi/latency được tổng hợp theo provider/outcome, **không** gắn traceId vào tags |

**Ghi nhớ:** **Trace ID liên kết các spans và logs của cùng một trace**, còn Span ID xác định từng thao tác. Muốn Trace ID có ích trên Spring Boot, cần tracing bridge, propagation qua HTTP/async/messaging, log correlation và exporter/sampling được cấu hình đúng. Metrics dùng tags thấp cardinality để phát hiện sự cố; tracing và logs dùng Trace ID để điều tra chi tiết, nhưng sự xuất hiện của một ID trong ứng dụng không tự bảo đảm dữ liệu đã được lưu trên tracing backend.
