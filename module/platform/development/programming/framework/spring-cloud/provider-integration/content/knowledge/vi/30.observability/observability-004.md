# Liên kết trace qua HTTP, hàng đợi và xử lý nền

## 1. Bối cảnh và mục tiêu

Trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**, chúng ta thực hành tích hợp Spring Boot với các dịch vụ managed của **AWS, Azure và Google Cloud** qua Spring Cloud và SDK tương ứng. Một request thực tế thường không dừng ở một HTTP controller: nó có thể gọi API nội bộ, ghi object storage, gửi message, được worker nhận sau vài giây rồi tiếp tục truy cập database hoặc dịch vụ cloud khác.

Ví dụ, người dùng gửi yêu cầu tạo bản xem trước tài liệu. API xác thực request, lưu file vào Azure Blob Storage, gửi job vào Azure Service Bus và trả HTTP 202. Một worker khác nhận message, đọc file, tạo thumbnail trên object storage rồi cập nhật trạng thái. Nếu worker lỗi, đội vận hành cần biết request ban đầu, lần publish, lần receive, thao tác storage và lỗi xử lý có liên quan với nhau hay không.

**Distributed tracing** giải quyết vấn đề đó bằng cách truyền trace context qua các ranh giới HTTP, message broker và thread bất đồng bộ. Bài học tập trung vào Spring Boot 3.5, Micrometer Tracing và OpenTelemetry, đồng thời so sánh cách truyền context trên Amazon SQS, Azure Service Bus và Google Cloud Pub/Sub.

Sau bài này, bạn có thể:

- Phân biệt trace ID, span ID, correlation ID và message ID.
- Cấu hình Micrometer Tracing/OpenTelemetry trong Spring Boot.
- Tự động truyền trace context qua HTTP client được Spring Boot cấu hình.
- Gắn W3C Trace Context vào message metadata và khôi phục context ở consumer.
- Chọn parent hoặc span link cho consumer, batch và fan-out.
- Giữ trace context khi chuyển sang thread khác hoặc chạy tác vụ nền.
- Bật instrumentation phù hợp cho AWS SDK, Azure SDK và Google Cloud Pub/Sub.
- Thiết kế sampling, baggage, logging và kiểm thử trace end-to-end an toàn.

## 2. Trace, span và correlation ID

Một **trace** biểu diễn toàn bộ hành trình của một công việc qua nhiều thành phần. Trace được tạo thành từ nhiều **span**; mỗi span mô tả một thao tác có thời gian bắt đầu/kết thúc, chẳng hạn HTTP request, gửi message, xử lý message hoặc gọi Blob Storage.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Trace ID | Định danh một hành trình phân tán | Request tạo bản xem trước và các thao tác downstream |
| Span ID | Định danh một thao tác trong trace | Gọi POST /jobs hoặc đọc một blob |
| Parent span | Span trực tiếp sinh ra span hiện tại | HTTP server span là parent của HTTP client span |
| Span link | Liên kết nhân quả với một span khác mà không bắt buộc làm parent | Consumer batch liên kết tới nhiều producer spans |
| Correlation ID | Khóa nghiệp vụ để tìm các log/event liên quan | requestId hoặc jobId |
| Message ID | Định danh message do broker cấp | SQS message ID hoặc Pub/Sub message ID |

Trace ID và correlation ID có mục đích khác nhau. Trace ID phục vụ quan sát kỹ thuật; correlation ID phục vụ tra cứu nghiệp vụ và có thể tồn tại qua nhiều lần retry hoặc nhiều trace. Không dùng correlation ID làm trace ID bằng cách tự tạo header rồi bỏ qua chuẩn tracing.

### 2.1. W3C Trace Context

W3C Trace Context chuẩn hóa cách truyền trace qua HTTP. Hai header quan trọng:

- **traceparent:** chứa version, trace ID, parent span ID và trace flags.
- **tracestate:** mang trạng thái bổ sung của vendor/tracing system nếu có.

Một giá trị traceparent minh họa:

~~~text
00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Không tự tách chuỗi này bằng substring để dựng span. Dùng propagator của Micrometer/OpenTelemetry để inject và extract; propagator xử lý validation, version và các trường hợp không có context hợp lệ.

W3C Baggage là một cơ chế riêng để truyền các cặp key/value xuyên suốt trace. Baggage không thay thế traceparent và không phải nơi lưu credential, token hoặc dữ liệu cá nhân.

## 3. Luồng HTTP → message broker → worker

Một luồng có thể được mô hình hóa như sau:

~~~mermaid
flowchart LR
    U[HTTP client] -->|traceparent| A[Spring Boot API]
    A -->|traceparent| S[Object Storage]
    A -->|message + trace context| Q[(Queue / Topic)]
    Q -->|message + trace context| W[Background worker]
    W -->|traceparent| S2[Object Storage]
    W --> D[(Database)]
    W -->|ack / complete| Q
~~~

Các span thường gặp:

1. HTTP server span bắt đầu khi API nhận request.
2. HTTP client span mô tả lời gọi downstream nếu client được instrument.
3. Producer span mô tả việc tạo/gửi message.
4. Consumer receive/process span mô tả việc nhận và xử lý message.
5. Các client spans mô tả thao tác storage, database hoặc HTTP mà worker thực hiện.
6. Settlement span hoặc thao tác tương ứng ghi nhận ack/delete/complete message.

Trace chỉ nối liền khi context được truyền qua từng ranh giới. Instrumentation tự động có thể tạo span cho HTTP hoặc SDK call nhưng **không thể tự suy ra quan hệ nghiệp vụ giữa producer và consumer nếu message không mang creation context**.

## 4. Cấu hình Spring Boot 3.5 và Micrometer Tracing

Spring Boot 3.5 dùng Micrometer Observation làm facade cho metrics và traces. Với OpenTelemetry và OTLP, các dependency Maven cơ bản:

~~~xml
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
~~~

Để BOM của Spring Boot quản lý version tương thích; không tự nâng riêng Micrometer hoặc OpenTelemetry lên version khác với dependency management của dự án.

Cấu hình ví dụ:

~~~yaml
spring:
  application:
    name: document-api

management:
  tracing:
    sampling:
      probability: 0.1
    propagation:
      produce: W3C
      consume: W3C
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
      transport: http
      timeout: 10s
~~~

Giải thích:

- spring.application.name giúp backend phân biệt service.
- sampling.probability là tỷ lệ trace root mới được lấy mẫu; Spring Boot mặc định 10%.
- propagation.produce xác định format ứng dụng ghi ra header/metadata.
- propagation.consume xác định format ứng dụng chấp nhận khi nhận context.
- OTLP endpoint trỏ tới collector hoặc backend hỗ trợ OTLP.

Nếu hệ thống có service cũ dùng B3, có thể cấu hình consume hỗ trợ cả W3C và B3 trong giai đoạn chuyển đổi, trong khi produce vẫn thống nhất W3C. Hãy thống nhất format giữa các service và kiểm tra cấu hình thực tế của từng runtime.

Spring Boot 3.5 có thể cung cấp bean OpenTelemetry khi tracing bridge và exporter được cấu hình. Trong bài này, OpenTelemetry API được dùng tại lớp adapter để inject/extract context qua message carrier; với instrumentation nghiệp vụ thông thường, ưu tiên Observation/Micrometer Tracing API.

## 5. Tự động truyền trace qua HTTP

Spring Boot tự instrument request HTTP phía server khi có tracing được cấu hình. Đối với HTTP client, hãy dùng builder do Spring Boot auto-configure:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
public class DownstreamClientConfiguration {

    @Bean
    RestClient catalogClient(RestClient.Builder builder) {
        return builder
                .baseUrl("https://catalog.internal")
                .build();
    }
}
~~~

RestClient.Builder được Spring Boot cấu hình có khả năng tự truyền trace context. Tương tự, dùng RestTemplateBuilder hoặc WebClient.Builder được inject từ Spring context.

Nếu tự tạo HTTP client độc lập bằng constructor hoặc builder không được instrument, traceparent có thể không được truyền. Khi đó trace sẽ bị đứt tại HTTP call dù cả hai service đều xuất trace bình thường.

### 5.1. Trace qua nhiều HTTP service

Khi API A gọi API B, client instrumentation tạo client span trong trace hiện tại và gửi context qua HTTP. API B đọc context đó để tạo server span thuộc cùng trace. Nếu B gọi tiếp C bằng builder được cấu hình, trace tiếp tục nối qua C.

Không cần tự thêm traceparent vào request khi HTTP client đã được instrument. Chỉ viết custom propagation khi dùng transport riêng hoặc khi một thư viện không được auto-instrument.

## 6. Truyền trace context qua message metadata

Message broker không phải HTTP server/client thông thường. Dữ liệu message thường có body và một vùng metadata riêng:

| Broker | Nơi lưu trace context |
|---|---|
| Amazon SQS | MessageAttributes |
| Azure Service Bus | ApplicationProperties; SDK có thể dùng Diagnostic-Id cho W3C Trace Context |
| Google Cloud Pub/Sub | Message attributes |

Một message có thể mang các key:

~~~text
traceparent = 00-<trace-id>-<span-id>-01
tracestate  = <vendor-state nếu có>
baggage     = <chỉ các field được cho phép>
correlationId = job-42
~~~

Trace context cần được truyền nguyên vẹn qua broker và intermediary. Nếu hệ thống transform hoặc forward message, hãy giữ metadata tracing theo quy tắc của ứng dụng. Không ghi đè context của producer bằng trace mới tại mỗi hop nếu mục tiêu là theo dõi cùng một công việc.

### 6.1. Vì sao cần propagator?

Propagator chuyển đổi context đang hoạt động thành các key/value phù hợp với carrier, rồi khôi phục context từ carrier khi consumer nhận message. Carrier có thể là Map, SQS message attributes, Service Bus application properties hoặc Pub/Sub attributes.

Không hardcode việc tự tạo trace ID/span ID. Không dùng một correlation ID tùy ý rồi đặt vào trường traceparent; format W3C có cấu trúc và semantics riêng.

## 7. Tạo producer span và inject context

Ví dụ sau dùng OpenTelemetry API và bean OpenTelemetry do Spring Boot cấu hình. Sender được truyền vào dưới dạng adapter để cùng một logic có thể dùng với SQS, Service Bus hoặc Pub/Sub.

~~~java
import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.Scope;
import io.opentelemetry.context.propagation.TextMapPropagator;
import java.util.HashMap;
import java.util.Map;
import java.util.function.BiConsumer;
import org.springframework.stereotype.Component;

@Component
public class MessageTracePublisher {
    private final io.opentelemetry.api.trace.Tracer tracer;
    private final TextMapPropagator propagator;

    public MessageTracePublisher(OpenTelemetry openTelemetry) {
        this.tracer = openTelemetry.getTracer("provider-integration.messaging");
        this.propagator =
                openTelemetry.getPropagators().getTextMapPropagator();
    }

    public void publish(
            String body,
            BiConsumer<String, Map<String, String>> sender) {

        Span span = tracer.spanBuilder("send document-jobs")
                .setSpanKind(SpanKind.PRODUCER)
                .startSpan();

        Context messageContext = Context.current().with(span);
        Map<String, String> attributes = new HashMap<>();

        propagator.inject(
                messageContext,
                attributes,
                (carrier, key, value) -> carrier.put(key, value));

        try (Scope ignored = messageContext.makeCurrent()) {
            sender.accept(body, attributes);
        } catch (RuntimeException ex) {
            span.recordException(ex);
            span.setStatus(StatusCode.ERROR);
            throw ex;
        } finally {
            span.end();
        }
    }
}
~~~

Ví dụ tạo producer span, inject trace context vào Map rồi gọi sender. Adapter của từng provider chuyển các key/value này sang metadata thật của broker. Trong production, nên bổ sung thuộc tính span có giá trị hữu ích và ổn định như provider, system, destination và operation theo semantic conventions mà instrumentation đang sử dụng.

Một lần gửi batch có thể chứa nhiều message. Nếu mỗi message có creation context riêng, cần tạo context cho từng message và giữ mapping message-context tương ứng; không giả định cả batch có chung một parent.

## 8. Extract context và tạo consumer span cho một message

Khi consumer nhận một message, lấy metadata carrier rồi extract context trước khi chạy handler:

~~~java
import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.Scope;
import io.opentelemetry.context.propagation.TextMapPropagator;
import java.util.Map;
import java.util.concurrent.Callable;
import org.springframework.stereotype.Component;

@Component
public class MessageTraceConsumer {
    private final io.opentelemetry.api.trace.Tracer tracer;
    private final TextMapPropagator propagator;

    public MessageTraceConsumer(OpenTelemetry openTelemetry) {
        this.tracer = openTelemetry.getTracer("provider-integration.messaging");
        this.propagator =
                openTelemetry.getPropagators().getTextMapPropagator();
    }

    public <T> T process(
            Map<String, String> attributes,
            Callable<T> handler) throws Exception {

        Context extracted = propagator.extract(
                Context.root(),
                attributes,
                (carrier, key) -> carrier.get(key));

        Span span = tracer.spanBuilder("process document-jobs")
                .setParent(extracted)
                .setSpanKind(SpanKind.CONSUMER)
                .startSpan();

        try (Scope ignored = span.makeCurrent()) {
            return handler.call();
        } catch (Exception ex) {
            span.recordException(ex);
            span.setStatus(StatusCode.ERROR);
            throw ex;
        } finally {
            span.end();
        }
    }
}
~~~

Đây là cách đơn giản cho trường hợp một message được xử lý độc lập và muốn dùng message creation context làm parent. Khi metadata không có trace context hợp lệ, propagator trả về context không có parent; consumer bắt đầu một trace mới thay vì tự dựng ID.

Trong ứng dụng thật, chỉ ack/delete/complete message sau khi handler hoàn tất theo đúng semantics của broker. Span processing nên bao phủ phần nghiệp vụ; thao tác settlement có thể được instrument riêng hoặc để SDK instrumentation ghi nhận.

## 9. Batch, fan-out và span links

Một consumer có thể nhận nhiều message cùng lúc. Một span chỉ có một parent, nên không thể biểu diễn chính xác một batch được tạo từ nhiều producer spans bằng cách chọn một message làm parent duy nhất.

OpenTelemetry messaging conventions khuyến nghị dùng **span links** để liên kết consumer span với creation context của từng message, đặc biệt trong batch và fan-out. Với một message đơn lẻ, instrumentation có thể chọn message context làm parent; hãy giữ một quy tắc nhất quán trong toàn hệ thống.

Ví dụ tạo consumer span cho batch và liên kết tới từng producer:

~~~java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanContext;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.Scope;
import java.util.List;
import java.util.Map;

public void processBatch(
        List<Map<String, String>> messageAttributes,
        Runnable handler) {

    var builder = tracer.spanBuilder("process document-jobs batch")
            .setNoParent()
            .setSpanKind(SpanKind.CONSUMER);

    for (Map<String, String> attributes : messageAttributes) {
        Context extracted = propagator.extract(
                Context.root(),
                attributes,
                (carrier, key) -> carrier.get(key));

        SpanContext messageContext =
                Span.fromContext(extracted).getSpanContext();
        if (messageContext.isValid()) {
            builder.addLink(messageContext);
        }
    }

    Span span = builder.startSpan();
    try (Scope ignored = span.makeCurrent()) {
        handler.run();
    } catch (RuntimeException ex) {
        span.recordException(ex);
        span.setStatus(StatusCode.ERROR);
        throw ex;
    } finally {
        span.end();
    }
}
~~~

Khi một producer publish tới topic có nhiều subscriber, mỗi consumer có thể tạo span riêng và link về cùng message creation context. Nhờ đó trace backend thể hiện quan hệ fan-out mà không ép các consumer độc lập thành một chuỗi parent-child giả tạo.

## 10. Giữ context khi chạy nền và chuyển thread

Trace context trong ứng dụng Spring thường được lưu trong execution context/ThreadLocal. Khi code chuyển sang thread khác, context có thể bị mất nếu executor không truyền nó.

### 10.1. Dùng ContextPropagatingTaskDecorator

Với executor tùy chỉnh, gắn ContextPropagatingTaskDecorator:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class BackgroundExecutorConfiguration {

    @Bean("applicationTaskExecutor")
    ThreadPoolTaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("background-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        return executor;
    }
}
~~~

Nếu dùng @Async hoặc AsyncTaskExecutor, phải bảo đảm executor đang chạy task được cấu hình để propagate context. Với Reactor, có thể bật spring.reactor.context-propagation=auto để khôi phục ThreadLocal context trong reactive operators.

Context propagation giữa các thread chỉ xử lý ranh giới **bên trong cùng process**. Nó không thay thế việc inject/extract trace context qua message broker hoặc HTTP.

### 10.2. Scheduled job không có HTTP parent

Một tác vụ chạy theo lịch thường không bắt nguồn từ request HTTP. Hãy tạo một root span mới cho mỗi lần chạy, ví dụ generate-daily-report, rồi tạo child spans cho các giai đoạn đọc dữ liệu, xử lý và ghi kết quả.

Nếu một background task được khởi chạy bởi message, hãy tiếp tục từ message context đã extract. Nếu task được khởi chạy độc lập bởi scheduler, không tự gắn trace của một request cũ chỉ vì thread pool đã từng xử lý request đó.

Với job kéo dài nhiều giờ, tránh giữ một span duy nhất mở trong suốt toàn bộ vòng đời nếu nó gây khó khăn cho export, sampling hoặc vận hành. Tạo span cho từng stage/batch và liên kết chúng bằng job ID, event hoặc span links phù hợp.

## 11. Khác biệt propagation giữa AWS, Azure và Google Cloud

### 11.1. Amazon SQS và AWS SDK for Java 2.x

Với SQS, message metadata nằm trong **MessageAttributes**. Một adapter có thể ghi W3C traceparent và tracestate thành String attributes:

~~~java
Map<String, MessageAttributeValue> attributes = new HashMap<>();
attributes.put(
        "traceparent",
        MessageAttributeValue.builder()
                .dataType("String")
                .stringValue(traceHeaders.get("traceparent"))
                .build());
~~~

Khi nhận message, đọc lại các message attributes rồi đưa vào propagator.extract. Nếu dùng instrumentation hỗ trợ SQS, hãy xác minh nó có inject/extract message context tự động ở đúng phiên bản và cấu hình hay không; không giả định span của SDK call SendMessage tự động nối tới consumer.

AWS còn có trường system attribute AWSTraceHeader phục vụ định dạng trace của AWS X-Ray. Đây là cơ chế AWS-specific, không đồng nhất với W3C traceparent. Khi hệ thống dùng OpenTelemetry xuyên nhiều cloud, chọn rõ format propagation và tránh ghi cùng một ý nghĩa vào nhiều header khác nhau mà không có quy tắc ưu tiên.

Đối với các lời gọi AWS SDK v2 như S3, SQS hoặc DynamoDB, có thể dùng AWS Distro for OpenTelemetry (ADOT) Java agent hoặc OpenTelemetry Java agent để tự instrument các thư viện được hỗ trợ. AWS X-Ray SDK/Daemon đã bước vào maintenance từ ngày 25-02-2026; với hệ thống mới, ưu tiên lộ trình OpenTelemetry/ADOT.

### 11.2. Azure Service Bus và Azure SDK for Java

Azure Service Bus dùng ApplicationProperties để mang metadata message. Distributed tracing của Service Bus dựa trên W3C Trace Context và sử dụng thuộc tính **Diagnostic-Id** để mang trace parent trong các luồng được SDK hỗ trợ.

Nếu tự xây adapter, cần:

- Giữ Diagnostic-Id theo format W3C traceparent khi tích hợp theo contract Service Bus.
- Không ghi đè giá trị do SDK đã tạo nếu SDK đang tự instrument message.
- Khi nhận message, khôi phục context từ metadata trước khi chạy handler.
- Giữ correlation ID nghiệp vụ trong một thuộc tính riêng.

Azure SDK for Java có thể tạo spans qua Azure Monitor Java agent hoặc OpenTelemetry Java agent. Khi dùng OpenTelemetry SDK trực tiếp, Azure SDK có package azure-core-tracing-opentelemetry; hướng tích hợp thủ công này được tài liệu Microsoft đánh dấu preview. Với lời gọi bất đồng bộ, context ngầm có thể không còn hiện diện trên thread callback; Azure SDK hỗ trợ truyền context tường minh qua com.azure.core.util.Context với key trace-context. Hãy kiểm tra version của client library và API đang dùng trước khi áp dụng.

### 11.3. Google Cloud Pub/Sub

Pub/Sub tổ chức trace theo vòng đời message từ publish tới acknowledge. Java client hỗ trợ bật OpenTelemetry tracing trên Publisher và Subscriber:

~~~java
Publisher publisher = Publisher.newBuilder(topicName)
        .setOpenTelemetry(openTelemetry)
        .setEnableOpenTelemetryTracing(true)
        .build();
~~~

~~~java
Subscriber subscriber = Subscriber.newBuilder(subscriptionName, receiver)
        .setOpenTelemetry(openTelemetry)
        .setEnableOpenTelemetryTracing(true)
        .build();
~~~

Khi bật tracing, client library tạo các spans liên quan đến publish, batching, flow control, lease management và subscribe. Client library cũng thêm tracing-specific attributes có prefix googclient_ để truyền context giữa publish và subscriber.

Nếu ứng dụng cần liên kết thêm một trace nghiệp vụ xuyên nhiều provider, hãy xác định rõ cách kết hợp trace context chuẩn W3C của ứng dụng với tracing attributes do Pub/Sub SDK quản lý. Không xóa hoặc ghi đè metadata googclient_ do SDK tạo.

## 12. Tạo business spans bằng Micrometer Observation

Instrumentation tự động cho biết HTTP/SDK hoạt động ra sao. Để thấy giai đoạn nghiệp vụ như validate document, generate preview hoặc reconcile job, tạo custom observation:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Component;

@Component
public class PreviewService {
    private final ObservationRegistry observationRegistry;

    public PreviewService(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    public void generatePreview(String documentType) {
        Observation.createNotStarted(
                        "document.preview.generate",
                        observationRegistry)
                .lowCardinalityKeyValue("document.type", documentType)
                .observe(() -> {
                    // Validate document, read source and generate preview.
                });
    }
}
~~~

Observation có thể tạo cả metrics và spans khi TracingObservationHandler được cấu hình. Dùng low-cardinality key/value cho những giá trị có tập hữu hạn như document.type hoặc provider. Nếu cần job ID hoặc message ID để điều tra, đưa chúng vào span attribute/log có kiểm soát, không dùng làm metric label.

Không thêm @Observed hoặc custom Observation lên method đã được auto-instrument cùng một ý nghĩa, nếu không trace có thể xuất hiện span lồng nhau hoặc metric trùng. Chỉ instrument những ranh giới nghiệp vụ thực sự cần nhìn thấy.

## 13. Baggage và dữ liệu nghiệp vụ

Baggage cho phép truyền một số metadata xuyên suốt trace, ví dụ tenant tier hoặc workflow class. Tuy nhiên baggage thường được gửi qua nhiều service và có thể xuất hiện trong log/trace backend.

Ví dụ cấu hình chỉ truyền một field đã được duyệt:

~~~yaml
management:
  tracing:
    baggage:
      remote-fields:
        - workflow-class
      correlation:
        fields:
          - workflow-class
~~~

Chỉ đưa vào baggage những giá trị:

- Có tập giá trị nhỏ và được kiểm soát.
- Không chứa password, access token, SAS URL, account key hoặc secret.
- Không chứa thông tin cá nhân hoặc dữ liệu nhạy cảm không cần thiết.
- Có thể được chia sẻ qua tất cả service tham gia trace.

Không đưa customer ID, email, số điện thoại hoặc nội dung tài liệu vào baggage chỉ để tiện debug. Với dữ liệu cần truy tìm, dùng correlation ID đã được kiểm soát và hệ thống log có quyền truy cập phù hợp.

## 14. Sampling và xuất trace

Spring Boot 3.5 mặc định lấy mẫu khoảng 10% trace root mới. Khi phát triển local, có thể đặt probability bằng 1.0 để nhìn thấy toàn bộ luồng:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
~~~

Không nên mặc định 100% sampling trên production có lưu lượng lớn. Sampling cao làm tăng số spans, chi phí lưu trữ và tải exporter/backend. Một số nguyên tắc:

- Dùng parent-based sampling để các service downstream tôn trọng quyết định sampling của trace cha.
- Giữ sampling policy nhất quán trên các service tham gia cùng một trace.
- Có thể cân nhắc tail sampling ở OpenTelemetry Collector nếu cần giữ trace lỗi hoặc latency cao; collector phải nhận đủ spans liên quan trước khi quyết định.
- Theo dõi exporter queue, timeout, dropped spans và collector availability.
- Đảm bảo ứng dụng flush/shutdown telemetry đúng cách để không mất spans còn trong buffer.

Sampling không thay thế metrics. Metrics cần phản ánh toàn bộ traffic; traces thường được lấy mẫu để điều tra chi tiết.

## 15. Liên kết log với trace

Khi Micrometer Tracing được cấu hình, Spring Boot thêm traceId và spanId vào MDC để log có thể được tìm lại trong trace backend.

Ví dụ Logback pattern:

~~~yaml
logging:
  pattern:
    correlation: "[%X{traceId:-},%X{spanId:-}] "
~~~

Một log có thể trông như sau:

~~~text
[4bf92f3577b34da6a3ce929d0e0e4736,00f067aa0ba902b7] INFO PreviewWorker - Preview created
~~~

Khi xử lý một message, log thêm message ID, job ID, destination và delivery attempt ở dạng field có cấu trúc. Những giá trị này hữu ích trong log, nhưng không nên đưa vào metric labels có cardinality cao.

Trace ID trong log giúp tìm trace; correlation ID giúp tìm job; message ID giúp tìm delivery cụ thể. Giữ ba loại định danh riêng để không làm mất khả năng truy vết.

## 16. Bảo mật và độ tin cậy của trace context

Trace context là metadata quan sát, **không phải bằng chứng xác thực hoặc phân quyền**. Không dùng traceparent, tracestate, baggage hoặc correlation ID để quyết định user có quyền truy cập resource.

Các nguyên tắc bảo vệ:

- Không truyền secret, access token hoặc SAS URL trong baggage/message attributes.
- Chỉ cho phép những baggage field được whitelist.
- Xem trace context đến từ Internet hoặc tenant khác là dữ liệu đầu vào không đáng tin cậy.
- Có thể loại bỏ hoặc tạo trace mới tại trust boundary nếu chính sách bảo mật yêu cầu; ghi rõ hành vi này để đội vận hành hiểu vì sao trace bị tách.
- Không log toàn bộ message payload chỉ để kiểm tra context propagation.
- Giới hạn quyền đọc trace backend vì span attributes có thể chứa metadata nội bộ.
- Không dùng message header do caller tự cung cấp để thay thế identity đã xác thực.

Một trace bị đứt không làm request mất an toàn; một trace nối được cũng không chứng minh authorization đã đúng.

## 17. Kiểm thử trace end-to-end

Kiểm thử cần xác minh trace ID và quan hệ span, không chỉ xác minh ứng dụng trả HTTP 200.

| Kịch bản | Kết quả mong đợi |
|---|---|
| HTTP request đi vào Spring Boot | Có server span và trace ID |
| API gọi downstream qua RestClient.Builder | Có client span cùng trace |
| API gửi message | Có producer/send span và context được inject vào metadata |
| Worker nhận một message | Consumer/process span được liên kết với producer context |
| Worker gọi Blob/S3/GCS | Có dependency span thuộc trace của worker |
| Consumer xử lý batch | Span batch liên kết tới context của từng message |
| @Async chuyển thread | Trace/MDC context vẫn hiện diện trong task |
| Scheduled job độc lập | Mỗi lần chạy có root trace mới |
| Message không có trace headers | Consumer bắt đầu trace mới, không lỗi |
| Message chứa context sai định dạng | Propagator xử lý như context không hợp lệ; handler vẫn có thể chạy theo policy |
| Handler ném exception | Span được đánh dấu error và exception được ghi nhận |
| Sampling bỏ trace | Không giả định mọi request đều xuất hiện trên backend |

### 17.1. Unit test cho inject/extract

Có thể test việc inject rồi extract context qua Map mà không cần broker thật:

~~~java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.propagation.W3CTraceContextPropagator;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.propagation.ContextPropagators;
import io.opentelemetry.sdk.OpenTelemetrySdk;
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TracePropagationTest {
    @Test
    void preservesTraceIdAcrossMessageCarrier() {
        SdkTracerProvider tracerProvider =
                SdkTracerProvider.builder().build();
        var openTelemetry = OpenTelemetrySdk.builder()
                .setTracerProvider(tracerProvider)
                .setPropagators(ContextPropagators.create(
                        W3CTraceContextPropagator.getInstance()))
                .build();

        try {
            var tracer = openTelemetry.getTracer("test");
            var propagator =
                    openTelemetry.getPropagators().getTextMapPropagator();

            Span producer = tracer.spanBuilder("send")
                    .setSpanKind(SpanKind.PRODUCER)
                    .startSpan();

            try {
                Map<String, String> carrier = new HashMap<>();
                propagator.inject(
                        Context.current().with(producer),
                        carrier,
                        (map, key, value) -> map.put(key, value));

                Context extracted = propagator.extract(
                        Context.root(),
                        carrier,
                        (map, key) -> map.get(key));

                var extractedSpan = Span.fromContext(extracted);
                assertTrue(extractedSpan.getSpanContext().isValid());
                assertEquals(
                        producer.getSpanContext().getTraceId(),
                        extractedSpan.getSpanContext().getTraceId());
            } finally {
                producer.end();
            }
        } finally {
            tracerProvider.close();
        }
    }
}
~~~

Ví dụ tạo SDK test độc lập và dùng W3C propagator; thêm dependency io.opentelemetry:opentelemetry-sdk ở test scope nếu project chưa có. Test này xác minh carrier giữ trace ID; integration test vẫn cần kiểm tra adapter đã chuyển đúng key/value vào MessageAttributes, ApplicationProperties hoặc Pub/Sub attributes. Khi dùng Spring Boot Test, lưu ý exporter/reporting components có thể không được auto-configure như lúc chạy ứng dụng.

### 17.2. Integration test với broker

Trong môi trường test:

1. Gửi một HTTP request có traceparent đã biết.
2. Chạy API, producer và consumer qua broker test.
3. Thu trace qua OTLP/Zipkin/Cloud Trace.
4. Kiểm tra các span có trace ID và links/parents đúng.
5. Gây lỗi trong handler để xác minh exception và error status.
6. Chạy batch/fan-out để xác minh nhiều producer contexts không bị ép vào một parent duy nhất.

Với AWS, dùng SQS test queue và kiểm tra message attributes; với Azure, dùng Service Bus namespace test và ApplicationProperties; với Google Cloud, dùng topic/subscription test và bật Pub/Sub OpenTelemetry tracing. Không kiểm thử propagation bằng mock Map rồi kết luận SDK/broker đã giữ metadata đúng.

## 18. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| HTTP request có trace nhưng downstream không có | Tạo HTTP client bằng builder không được Spring Boot auto-configure | Dùng RestTemplateBuilder, RestClient.Builder hoặc WebClient.Builder từ context |
| Producer và consumer có trace ID khác nhau | Message không mang trace context hoặc consumer không extract | Kiểm tra MessageAttributes/ApplicationProperties/Pub/Sub attributes |
| Consumer span nối vào trace không liên quan | Dùng context của thread đang chạy thay vì message context | Extract context từ đúng message; dùng links cho batch/fan-out |
| Trace mất khi gọi @Async | Executor không propagate Observation context | Đăng ký ContextPropagatingTaskDecorator |
| Reactive pipeline mất trace | ThreadLocal context không được khôi phục trong Reactor | Cấu hình spring.reactor.context-propagation=auto |
| Azure SDK span tách khỏi application span khi async | Context ngầm không theo callback thread | Dùng agent hỗ trợ hoặc truyền trace context tường minh theo Azure SDK |
| Pub/Sub có trace SDK nhưng thiếu business span | Client instrumentation chỉ mô tả transport/lifecycle | Thêm business Observation và correlation metadata |
| AWS SQS trace không nối sang consumer | SDK call span có nhưng message attributes không chứa context | Kiểm tra SQS message attribute propagation và agent support |
| Trace không xuất hiện trên backend | Sampling loại trace, exporter sai endpoint hoặc shutdown không flush | Kiểm tra sampling, OTLP endpoint, exporter queue và shutdown |
| Một operation có quá nhiều spans | Auto instrumentation và manual instrumentation trùng nhau | Chỉ giữ một instrumentation cho cùng ranh giới |
| Trace backend tốn chi phí cao | Sampling 100%, spans quá chi tiết hoặc payload attributes lớn | Giảm sampling, lọc spans và giới hạn attributes |
| Trace chứa thông tin nhạy cảm | Baggage/span attributes được thêm tùy tiện | Whitelist fields và redaction ở collector/backend |

## 19. Bài tập thực hành và câu hỏi tự kiểm tra

**Tình huống A — HTTP tới SQS:** API nhận request, lưu file vào S3 rồi gửi message vào SQS. Hãy vẽ trace gồm server span, S3 client span, producer span và consumer span; xác định metadata nào cần được gửi trong SQS MessageAttributes.

**Tình huống B — Azure Service Bus:** Producer và worker dùng Azure SDK for Java. Hãy xác minh Diagnostic-Id theo W3C Trace Context, kiểm tra ApplicationProperties và xử lý context khi worker chuyển sang thread khác.

**Tình huống C — Pub/Sub fan-out:** Một message được gửi tới topic có hai subscription. Hãy thiết kế consumer spans có links về message creation context và giải thích vì sao không nên dùng cùng một consumer span làm parent cho cả hai worker độc lập.

**Tình huống D — @Async mất trace:** Controller tạo job rồi gọi service qua @Async. Log trong task không có traceId. Hãy kiểm tra executor và cấu hình ContextPropagatingTaskDecorator.

**Tình huống E — Scheduled report:** Một báo cáo chạy lúc nửa đêm, không bắt nguồn từ HTTP request. Hãy tạo root span cho mỗi lần chạy và các child spans cho đọc dữ liệu, xử lý và ghi kết quả.

**Tình huống F — Baggage không an toàn:** Một service đưa email người dùng và access token vào baggage để tiện debug. Hãy loại bỏ dữ liệu nhạy cảm, chọn correlation ID phù hợp và xác định field nào được phép propagate.

**Tình huống G — Sampling:** Trace của producer được lấy mẫu nhưng consumer không xuất span. Hãy kiểm tra parent-based sampling, context injection/extraction và exporter trước khi tăng sampling lên 100%.

### Câu hỏi tự kiểm tra

1. **Trace ID khác span ID thế nào?** Trace ID định danh toàn bộ hành trình; span ID định danh một thao tác trong hành trình đó.
2. **Correlation ID có thay thế trace ID không?** Không; correlation ID là định danh nghiệp vụ, trace ID là định danh quan sát.
3. **HTTP context được truyền qua header nào?** W3C Trace Context dùng traceparent và có thể có tracestate.
4. **Vì sao producer phải inject context vào message?** Consumer không thể tự liên kết với producer nếu message không mang creation context.
5. **Khi nào nên dùng span links?** Batch, fan-out hoặc khi consumer span có nhiều nguồn nhân quả.
6. **Spring Boot truyền trace qua RestClient bằng cách nào?** Dùng RestClient.Builder auto-configure từ Spring context.
7. **SQS lưu context ở đâu?** Trong MessageAttributes, theo adapter và propagation format được chọn.
8. **Azure Service Bus dùng thuộc tính tracing nào?** Diagnostic-Id theo W3C Trace Context trong luồng SDK hỗ trợ.
9. **Pub/Sub Java có tracing tích hợp không?** Có; cấu hình OpenTelemetry trên Publisher/Subscriber và bật enableOpenTelemetryTracing.
10. **Vì sao phải propagate context qua thread?** Nếu executor không truyền context, span/log trong task nền có thể tách khỏi trace ban đầu.
11. **Baggage có nên chứa token hoặc PII không?** Không; chỉ truyền các field đã whitelist và không nhạy cảm.
12. **Sampling 100% có nên bật mặc định production không?** Không; cần cân bằng độ chi tiết, chi phí và tải backend.

## 20. Tổng kết

Để liên kết trace qua HTTP, hàng đợi và xử lý nền, ứng dụng phải truyền **trace context** qua mọi ranh giới. Spring Boot 3.5 và Micrometer Tracing tự instrument HTTP request và HTTP client được tạo từ builder auto-configure. Với message broker, producer cần inject context vào metadata, còn consumer phải extract context trước khi chạy handler.

AWS SQS dùng MessageAttributes; Azure Service Bus hỗ trợ Diagnostic-Id theo W3C Trace Context; Google Cloud Pub/Sub có OpenTelemetry tracing tích hợp và metadata tracing riêng của client library. Với batch và fan-out, span links thường mô tả quan hệ nhân quả chính xác hơn một parent-child đơn lẻ. Khi chuyển thread, dùng context propagation; với scheduler độc lập, tạo root trace mới.

Giữ baggage ở mức tối thiểu, không dùng trace context cho authorization, chọn sampling phù hợp và liên kết log bằng traceId/spanId. Kết hợp instrumentation tự động của provider với business spans, kiểm thử qua broker thật và kiểm tra trace end-to-end để tìm được điểm đứt trong luồng xử lý phân tán.

### Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Tracing](https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html)
- [Spring Boot 3.5 — Observability and Context Propagation](https://docs.spring.io/spring-boot/3.5/reference/actuator/observability.html)
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/)
- [OpenTelemetry — Messaging Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/messaging/messaging-spans/)
- [OpenTelemetry — Java Instrumentation](https://opentelemetry.io/docs/languages/java/instrumentation/)
- [AWS — Migrating Java applications to OpenTelemetry](https://docs.aws.amazon.com/xray/latest/devguide/xray-migration-opentelemetry.html)
- [AWS — OpenTelemetry compatibility considerations for AWS](https://opentelemetry.io/docs/specs/semconv/non-normative/compatibility/aws/)
- [Microsoft Learn — Configure tracing in Azure SDK for Java](https://learn.microsoft.com/azure/developer/java/sdk/tracing)
- [Microsoft Learn — Distributed tracing through Azure Service Bus](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-end-to-end-tracing)
- [Google Cloud — Pub/Sub OpenTelemetry tracing](https://docs.cloud.google.com/pubsub/docs/open-telemetry-tracing)
