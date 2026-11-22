# Correlation ID trong MDC

## 1. Vì sao consumer cần Correlation ID?

Trong hệ thống phân tán, một yêu cầu nghiệp vụ có thể đi qua nhiều service trước khi hoàn tất. Ví dụ, Order API ghi event vào Kafka; Order Fulfillment tiêu thụ event, gọi Inventory và Payment. Khi lỗi xảy ra ở một bước, chỉ nhìn log của từng service sẽ khó biết những dòng log nào thuộc cùng một luồng nghiệp vụ.

**Correlation ID** là định danh được truyền xuyên suốt một luồng xử lý để liên kết log và sự kiện liên quan. Với Spring Kafka, producer đặt ID vào Kafka header; consumer đọc header từ ConsumerRecord và đưa giá trị vào **Mapped Diagnostic Context (MDC)** để logging framework tự động thêm nó vào log line trong phạm vi xử lý.

~~~text
HTTP request
   |
   | correlation-id = req-7f31
   v
Order API
   |
   v
Kafka producer
   |
   | header correlation-id=req-7f31
   v
Topic: orders.created
   |
   v
Spring Kafka consumer
   |
   | ConsumerRecord.headers()
   | MDC.put("correlationId", "req-7f31")
   v
Order Fulfillment
~~~

MDC giúp log line có correlation ID mà không phải truyền tham số ID qua mọi câu lệnh logging. Tuy nhiên, MDC là context gắn với thread hiện tại. Nó không tự truyền qua Kafka, không tự đồng bộ giữa thread pool và không thay thế distributed tracing.

## 2. Correlation ID, Trace ID, Message ID và Kafka offset

Các định danh này có thể liên quan nhưng có mục đích khác nhau.

| Định danh | Mục đích | Phạm vi |
|---|---|---|
| Correlation ID | Liên kết log của một luồng nghiệp vụ | Nhiều service và nhiều message liên quan |
| Trace ID | Liên kết spans trong distributed trace | Một trace theo tracing model |
| Message/Event ID | Nhận diện duy nhất một event | Một message, thường dùng deduplication |
| Kafka offset | Vị trí record trong partition | Một topic-partition |

Ví dụ:

~~~text
correlation-id = order-flow-9281
trace-id       = 4bf92f3577b34da6a3ce929d0e0e4736
event-id       = evt-6a91
topic          = orders.created
partition      = 2
offset         = 1842
~~~

Một order flow có thể tạo nhiều event ID và nhiều trace ID nếu các bước chạy bất đồng bộ. Correlation ID có thể được giữ qua toàn bộ vòng đời nghiệp vụ để liên kết chúng.

Không dùng offset làm correlation ID vì offset chỉ có ý nghĩa trong một partition. Không dùng correlation ID làm message ID nếu nhiều event trong cùng flow cần được phân biệt.

## 3. MDC là gì?

**Mapped Diagnostic Context (MDC)** là cơ chế của SLF4J và logging implementations để gắn các cặp key/value vào ngữ cảnh log hiện tại. Logging framework đọc các giá trị này khi render log line.

~~~java
MDC.put("correlationId", "order-flow-9281");

log.info("Validating order");
log.info("Calling inventory");
log.info("Order accepted");

MDC.remove("correlationId");
~~~

Nếu Logback pattern có MDC key, log có thể hiển thị:

~~~text
INFO correlationId=order-flow-9281 Validating order
INFO correlationId=order-flow-9281 Calling inventory
INFO correlationId=order-flow-9281 Order accepted
~~~

MDC thường được triển khai bằng thread-local context. Hai consumer threads có thể giữ hai correlation IDs khác nhau. Nhưng thread pool tái sử dụng thread cho nhiều task; nếu task trước không xóa MDC, task sau có thể ghi log với ID cũ.

**MDC không phải global map và không tự propagate qua Kafka.** Kafka chỉ truyền record và headers. Producer phải ghi ID vào header, consumer phải đọc header và thiết lập MDC trong thread xử lý.

## 4. Chuẩn hóa Kafka header

Một contract phổ biến dùng tên header:

~~~text
correlation-id
~~~

Producer và consumer cần thống nhất tên header, chữ hoa/chữ thường, encoding, độ dài, tập ký tự, quy tắc khi thiếu hoặc có nhiều header trùng tên, khi nào giữ ID cũ và khi nào tạo ID mới, cùng cách giữ header khi republish sang retry topic hoặc DLT.

Nếu HTTP gateway nhận X-Correlation-ID, service đầu tiên có thể chuẩn hóa giá trị đó thành Kafka header correlation-id.

## 5. Producer ghi Correlation ID vào Kafka header

Có thể tạo ProducerRecord để gắn header tường minh:

~~~java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.clients.producer.ProducerRecord;

public void publish(
        String topic,
        String key,
        OrderCreated event,
        String correlationId) {

    ProducerRecord<String, OrderCreated> record =
        new ProducerRecord<>(topic, key, event);

    record.headers().add(
        "correlation-id",
        correlationId.getBytes(StandardCharsets.UTF_8)
    );

    kafkaTemplate.send(record);
}
~~~

Nếu producer đang xử lý một request đã có correlation ID, hãy truyền cùng ID đó sang event liên quan. Nếu request chưa có ID, service đầu tiên có thể tạo ID mới bằng UUID hoặc định dạng opaque đã thống nhất.

~~~java
String correlationId = incomingHeader;

if (correlationId == null || correlationId.isBlank()) {
    correlationId = UUID.randomUUID().toString();
}
~~~

ID đến từ bên ngoài phải được validate và giới hạn độ dài. Không đưa email, access token, session secret hoặc dữ liệu cá nhân không cần thiết vào correlation ID.

Không tự tạo ID mới ở mọi service, vì chuỗi log sẽ bị đứt. Chỉ tạo mới khi không có ID hợp lệ hoặc business flow chủ động bắt đầu correlation scope mới.

## 6. Consumer đọc header từ ConsumerRecord

Spring Kafka có thể cung cấp ConsumerRecord trực tiếp cho listener:

~~~java
@KafkaListener(
    id = "orders-consumer",
    topics = "orders.created",
    groupId = "order-fulfillment"
)
public void consume(ConsumerRecord<String, OrderCreated> record) {
    String correlationId = CorrelationIds.from(record);
    orderService.process(record.value());
}
~~~

Kafka header có value dạng byte[]. Consumer decode theo encoding contract, thường là UTF-8.

~~~java
import java.nio.charset.StandardCharsets;
import java.util.regex.Pattern;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;

public final class CorrelationIds {

    private static final String HEADER = "correlation-id";

    private static final Pattern ALLOWED =
        Pattern.compile("[A-Za-z0-9._:-]{1,128}");

    private CorrelationIds() {
    }

    public static String from(ConsumerRecord<?, ?> record) {
        Header header = record.headers().lastHeader(HEADER);

        if (header == null || header.value() == null) {
            return null;
        }

        byte[] bytes = header.value();

        if (bytes.length == 0 || bytes.length > 128) {
            return null;
        }

        String value = new String(bytes, StandardCharsets.UTF_8);

        if (!ALLOWED.matcher(value).matches()) {
            return null;
        }

        return value;
    }
}
~~~

Allowlist phải phù hợp với ID format thực tế. Ví dụ trên chấp nhận UUID dạng hex có dấu gạch ngang, dấu chấm, gạch dưới và dấu hai chấm trong giới hạn 128 ký tự.

### 6.1. Header thiếu hoặc không hợp lệ

Record cũ có thể không có correlation-id. Producer bên ngoài có thể gửi header sai định dạng. Consumer cần policy nhất quán:

- Tạo ID cục bộ mới để liên kết log từ consumer trở đi.
- Dùng marker missing để phát hiện producer chưa tuân thủ contract.
- Reject/recover record nếu correlation ID là điều kiện bắt buộc của nghiệp vụ.

Nếu tạo ID mới, có thể ghi thêm source=generated để tránh hiểu nhầm ID đã được propagate từ request gốc.

### 6.2. Nhiều headers cùng tên

Kafka cho phép nhiều header trùng tên. lastHeader(name) trả header cuối cùng khớp tên. Nếu contract chỉ cho phép một header, hãy đếm và reject/fallback khi có duplicates. Không âm thầm chọn một giá trị nếu gateway hoặc producer có thể thêm header trùng ngoài ý muốn.

## 7. Đặt MDC trong try/finally

Thiết lập MDC trước business logic và cleanup trong finally:

~~~java
@KafkaListener(
    id = "orders-consumer",
    topics = "orders.created",
    groupId = "order-fulfillment"
)
public void consume(ConsumerRecord<String, OrderCreated> record) {
    String correlationId = CorrelationIds.from(record);

    if (correlationId == null) {
        correlationId = UUID.randomUUID().toString();
    }

    String previous = MDC.get("correlationId");
    MDC.put("correlationId", correlationId);

    try {
        orderService.process(record.value());
        log.info("Order event processed");
    }
    finally {
        if (previous == null) {
            MDC.remove("correlationId");
        }
        else {
            MDC.put("correlationId", previous);
        }
    }
}
~~~

Đoạn code lưu giá trị trước đó và khôi phục sau xử lý. Điều này tốt hơn việc luôn clear toàn bộ MDC nếu scope bên ngoài còn có các keys khác.

**finally phải chạy cả khi business service ném exception.** Nếu chỉ remove ở cuối happy path, exception có thể để correlation ID tồn tại trên consumer thread và rò sang record tiếp theo.

### 7.1. Helper scope bằng AutoCloseable

Có thể đóng gói setup/cleanup để tránh lặp code:

~~~java
public final class CorrelationMdcScope implements AutoCloseable {

    private final String previous;

    private CorrelationMdcScope(String correlationId) {
        this.previous = MDC.get("correlationId");

        if (correlationId == null) {
            MDC.remove("correlationId");
        }
        else {
            MDC.put("correlationId", correlationId);
        }
    }

    public static CorrelationMdcScope open(String correlationId) {
        return new CorrelationMdcScope(correlationId);
    }

    @Override
    public void close() {
        if (previous == null) {
            MDC.remove("correlationId");
        }
        else {
            MDC.put("correlationId", previous);
        }
    }
}
~~~

Sử dụng:

~~~java
@KafkaListener(topics = "orders.created")
public void consume(ConsumerRecord<String, OrderCreated> record) {
    try (CorrelationMdcScope ignored =
             CorrelationMdcScope.open(CorrelationIds.from(record))) {

        orderService.process(record.value());
        log.info("Order event processed");
    }
}
~~~

Try-with-resources bảo đảm close() được gọi khi method kết thúc bình thường hoặc ném exception.

## 8. Cấu hình logging để hiển thị MDC

Logback có thể đọc MDC key bằng pattern converter:

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSS} %-5level [%thread] correlationId=%X{correlationId:-missing} %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Phần **%X{correlationId:-missing}** đọc MDC key correlationId và hiển thị missing nếu không có.

Ví dụ:

~~~text
2026-11-15T11:20:00.012 INFO [orders-consumer-1] correlationId=order-flow-9281 Order event received
2026-11-15T11:20:00.018 INFO [orders-consumer-1] correlationId=order-flow-9281 Inventory reservation started
2026-11-15T11:20:00.045 INFO [orders-consumer-1] correlationId=order-flow-9281 Order event processed
~~~

Với Log4j2, dùng ThreadContext và pattern converter tương ứng thay cho cú pháp Logback.

### 8.1. Structured JSON logging

Nếu ứng dụng xuất JSON logs, MDC có thể được xuất thành field riêng:

~~~json
{
  "timestamp": "2026-11-15T11:20:00.012Z",
  "level": "INFO",
  "service": "order-fulfillment",
  "thread": "orders-consumer-1",
  "correlationId": "order-flow-9281",
  "message": "Inventory reserved"
}
~~~

Tên field nên thống nhất giữa các service. Nếu một service dùng correlationId, service khác dùng correlation_id, log backend cần mapping hoặc normalization.

Không ghi nguyên header khi validation thất bại; chỉ log trạng thái invalid để tránh rò rỉ dữ liệu đầu vào.

## 9. MDC cleanup và thread reuse

Consumer thread sống lâu và xử lý nhiều record liên tiếp. Nếu record A đặt correlationId=A nhưng không remove, record B không có header vẫn có thể log với ID A.

~~~text
Consumer thread-1

Record A:
  MDC.put(correlationId=A)
  xử lý xong
  quên cleanup

Record B:
  không có correlation-id
  log processing
  MDC vẫn chứa A
~~~

Đây là lỗi khó phát hiện vì log vẫn có correlation ID hợp lệ về hình thức nhưng liên kết sai request.

Quy tắc:

1. Lưu context cũ nếu cần nested scope.
2. Đặt correlation ID hiện tại.
3. Chạy business logic trong try.
4. Khôi phục/remove trong finally.
5. Không cleanup trước các log cuối cùng thuộc scope.

Cleanup phải chạy cả trên exception, timeout và recovery path. Không chỉ xử lý happy path.

## 10. Record listener và batch listener

Với **record listener**, một invocation thường tương ứng một ConsumerRecord. Đặt một MDC scope quanh toàn bộ method là phù hợp.

Với **batch listener**, một invocation có thể nhận nhiều record với nhiều correlation IDs. Một MDC context chỉ chứa một correlation ID tại một thời điểm.

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-fulfillment",
    containerFactory = "batchFactory"
)
public void consume(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (ConsumerRecord<String, OrderCreated> record : records) {
        try (CorrelationMdcScope ignored =
                 CorrelationMdcScope.open(CorrelationIds.from(record))) {

            orderService.process(record.value());
            log.info("Processed offset {}", record.offset());
        }
    }
}
~~~

Mỗi record được xử lý trong scope riêng. Sau mỗi vòng lặp, MDC được khôi phục để record tiếp theo không kế thừa ID trước.

### 10.1. Batch-level logs

Không chọn correlation ID của record đầu tiên rồi gắn cho toàn batch. Nếu batch có nhiều flows, log batch-level nên dùng batch ID riêng, batch size, listener ID và duration. Log per-record nên được phát trong scope riêng.

Nếu listener ném exception, finally của record lỗi cleanup trước khi exception tới error handler. Log của error handler có thể không còn MDC; khi cần correlation ID ở đó, hãy đọc trực tiếp từ ConsumerRecord trong handler/recoverer.

## 11. Concurrency của Spring Kafka

Với concurrency lớn hơn một, Spring Kafka thường tạo nhiều child containers và consumer threads:

~~~text
ConcurrentMessageListenerContainer
        |
        +-- Consumer thread 0: MDC correlationId=A
        |
        +-- Consumer thread 1: MDC correlationId=B
        |
        +-- Consumer thread 2: MDC correlationId=C
~~~

MDC thông thường được gắn với thread, nên các consumer threads có context độc lập. Tuy nhiên, cùng một thread sẽ xử lý record tiếp theo; cleanup vẫn bắt buộc.

Không dùng một static mutable String để lưu correlation ID vì các consumer threads sẽ ghi đè lẫn nhau.

## 12. Async processing và TaskDecorator

Nếu listener submit công việc sang executor:

~~~java
@KafkaListener(topics = "orders.created")
public void consume(ConsumerRecord<String, OrderCreated> record) {
    try (CorrelationMdcScope ignored =
             CorrelationMdcScope.open(CorrelationIds.from(record))) {

        executor.execute(() -> orderService.process(record.value()));
    }
}
~~~

MDC trong consumer thread **không tự xuất hiện** trong thread pool task. Khi listener trả về, scope được cleanup trong khi task có thể chạy sau đó.

Một TaskDecorator có thể capture context lúc submit và restore trên worker thread:

~~~java
import java.util.Map;
import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

public class MdcTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable delegate) {
        Map<String, String> captured = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previous = MDC.getCopyOfContextMap();

            try {
                if (captured == null) {
                    MDC.clear();
                }
                else {
                    MDC.setContextMap(captured);
                }

                delegate.run();
            }
            finally {
                if (previous == null) {
                    MDC.clear();
                }
                else {
                    MDC.setContextMap(previous);
                }
            }
        };
    }
}
~~~

Cấu hình executor:

~~~java
@Bean
public ThreadPoolTaskExecutor orderExecutor() {
    var executor = new ThreadPoolTaskExecutor();

    executor.setCorePoolSize(8);
    executor.setMaxPoolSize(16);
    executor.setQueueCapacity(500);
    executor.setThreadNamePrefix("order-worker-");
    executor.setTaskDecorator(new MdcTaskDecorator());
    executor.initialize();

    return executor;
}
~~~

Decorator khôi phục context trước đó trong finally vì worker thread được tái sử dụng.

**Truyền MDC không giải quyết Kafka acknowledgment.** Nếu listener submit task rồi trả về ngay, container có thể commit offset trước khi async business processing hoàn tất tùy AckMode và thiết kế. Phải điều phối ack/transaction sao cho record chỉ được coi là hoàn tất sau business outcome cần thiết.

## 13. CompletableFuture và callback

Callback của CompletableFuture có thể chạy trên thread khác tùy executor và nơi future hoàn tất:

~~~java
service.callAsync()
    .thenApply(result -> {
        log.info("Received downstream response");
        return result;
    });
~~~

Không giả định thenApply hoặc thenAccept luôn chạy trên consumer thread. Nếu callback chạy trên worker khác, MDC có thể thiếu.

Các lựa chọn:

- Dùng executor đã cấu hình MdcTaskDecorator.
- Capture/restore MDC map khi tạo callback.
- Dùng context propagation library phù hợp.
- Tránh tự copy context thủ công rải rác không có quy ước chung.

## 14. Retry, error handler và DLT

Khi listener ném exception, Spring Kafka error handler có thể retry record hoặc recover sang DLT.

~~~text
ConsumerRecord
     |
     v
Listener đặt MDC
     |
     v
Business processing fails
     |
     v
finally khôi phục MDC
     |
     v
Exception tới error handler
     |
     +--> retry
     |
     +--> recover / DLT
~~~

MDC scope trong listener kết thúc trước khi exception được xử lý bên ngoài method. Vì vậy, log của error handler có thể không còn correlation ID.

Để giữ context:

- Log correlation ID ngay trước khi ném exception.
- Trong custom error handler/recoverer, đọc ID trực tiếp từ ConsumerRecord.
- Dùng interceptor/wrapper nếu cần một scope bao trùm đúng lifecycle.
- Giữ correlation-id header khi republish sang retry topic và DLT.

Không dựa vào thread-local MDC để truyền context qua nhiều lần retry.

### 14.1. Retry topic

Với retry-topic pattern, event có thể được publish sang retry topic rồi tiêu thụ lại sau backoff. Producer gửi retry record phải giữ correlation-id header.

~~~text
orders.created
     |
     v
Listener failure
     |
     v
orders.created-retry
     |
     v
Retry consumer đọc header
     |
     v
MDC được thiết lập lại
~~~

Nếu header bị mất khi republish, log retry attempt không còn liên kết với flow ban đầu. Hãy kiểm tra header propagation bằng integration test.

### 14.2. Dead-letter topic

DLT record nên giữ correlation ID gốc cùng metadata nguồn như original topic/partition/offset do recovery mechanism cung cấp. Consumer DLT cũng phải thiết lập MDC từ header.

Không thay correlation ID gốc bằng ID mới ở mỗi lần recover. Nếu cần theo dõi lần recovery, thêm attempt ID riêng.

## 15. RecordInterceptor và MDC

Spring Kafka cung cấp **RecordInterceptor** cho record listener để thực hiện logic trước/sau listener invocation. Nó có thể hữu ích cho cross-cutting behavior như log context.

Tuy nhiên, cleanup phải tuân theo đúng lifecycle và API của phiên bản. Interceptor có callback liên quan success/failure/afterRecord tùy version; không giả định một callback luôn chạy trong mọi tình huống.

Với listener đơn giản, try/finally ngay trong method dễ hiểu và dễ xác minh. Nếu dùng interceptor cho toàn endpoint, cần test:

- Listener trả bình thường.
- Listener ném exception.
- Record bị lọc/bỏ qua.
- Error handler retry/recover.
- Container stop trong lúc xử lý.
- Batch listener nếu interceptor đó hỗ trợ.

Không setup MDC trong interceptor rồi chỉ cleanup trong callback không được gọi khi exception xảy ra.

## 16. Đọc custom header qua @Header

Spring Kafka có thể map Kafka headers sang method arguments:

~~~java
@KafkaListener(topics = "orders.created")
public void consume(
        @Header(name = "correlation-id", required = false)
        String correlationId,
        OrderCreated event) {

    try (CorrelationMdcScope ignored =
             CorrelationMdcScope.open(correlationId)) {

        orderService.process(event);
    }
}
~~~

Cách này tiện khi chỉ cần một header và message converter đã map đúng kiểu. Nếu cần kiểm soát bytes, duplicates, length hoặc validation chặt chẽ, nhận ConsumerRecord trực tiếp thường rõ ràng hơn.

Không giả định mọi converter map custom header sang String theo cùng một cách. Hãy xác nhận converter và kiểm thử integration.

## 17. MDC khác distributed tracing

MDC phục vụ log correlation. Distributed tracing dùng trace/span context và propagation standards như W3C Trace Context.

| Đặc điểm | Correlation ID trong MDC | Trace context |
|---|---|---|
| Mục đích | Liên kết log lines | Liên kết spans |
| Context | MDC/thread-local | Observation/Tracing context |
| Qua Kafka | Custom header contract | Propagator inject/extract |
| Parent/child spans | Không | Có |
| Timing/dependency graph | Không tự có | Có |
| Log integration | Logging pattern đọc MDC | Tracing integration có thể thêm trace/span IDs |

Một ứng dụng có thể dùng cả hai: correlation ID cho luồng nghiệp vụ lâu dài, trace ID cho một trace cụ thể.

Nếu dùng Micrometer Tracing/Spring Observation, hãy để tracing propagator extract trace context từ headers được hỗ trợ. Không tự parse traceparent rồi gọi MDC.put("traceId", ...) thay cho tracing library; làm vậy có thể phá parent/child relationship, sampling và baggage semantics.

## 18. Fallback khi header không có

Có ba policy thường gặp.

**Tạo ID mới:** mọi log phía consumer có ID, nhưng ID chỉ bắt đầu từ consumer và không liên kết request upstream.

~~~java
String id = CorrelationIds.from(record);

if (id == null) {
    id = UUID.randomUUID().toString();
}
~~~

**Dùng marker missing:** dễ phát hiện producer contract violation; logs không có ID để liên kết.

**Validation failure:** chỉ phù hợp nếu correlation ID thực sự là điều kiện bắt buộc của business event contract, không nên biến yêu cầu observability thành validation bắt buộc nếu upstream chưa thống nhất.

Nếu tạo ID mới, log thêm source=generated. Không tuyên bố ID đó đã được propagate từ request ban đầu.

## 19. Trust boundary và log injection

Correlation ID có thể đến từ HTTP client, producer ngoài tổ chức hoặc message replay. Hãy coi nó là dữ liệu đầu vào không đáng tin cậy.

Không chấp nhận password, access token, JWT hoặc session cookie; email, số điện thoại hay PII không cần thiết; newline/carriage return có thể tạo log injection; chuỗi rất dài gây log flooding; control characters hoặc binary bytes tùy ý.

Một allowlist như [A-Za-z0-9._:-]{1,128} phù hợp với ID opaque do hệ thống phát hành. Nếu tổ chức có format khác, dùng validator chính thức.

Không dùng correlation ID làm authorization identity. Biết một ID không chứng minh caller có quyền truy cập dữ liệu.

## 20. Structured JSON logs

Nếu ứng dụng dùng JSON encoder, MDC có thể được xuất thành field riêng:

~~~json
{
  "timestamp": "2026-11-15T11:20:00.012Z",
  "level": "INFO",
  "service": "order-fulfillment",
  "thread": "orders-consumer-1",
  "correlationId": "order-flow-9281",
  "message": "Inventory reserved"
}
~~~

Tên field nên thống nhất giữa các service. Nếu một service dùng correlationId, service khác dùng correlation_id, log backend cần mapping hoặc normalization.

Không ghi nguyên header khi validation thất bại; chỉ log trạng thái invalid để tránh rò rỉ dữ liệu đầu vào.

## 21. Không dùng Correlation ID làm metric label

Correlation ID gần như có một giá trị mới cho mỗi request/message. Vì vậy nó **không phù hợp làm Prometheus/Micrometer metric label**.

Không nên:

~~~java
meterRegistry.counter(
    "orders.processed",
    "correlationId",
    correlationId
).increment();
~~~

Nên dùng low-cardinality dimensions:

~~~text
event.family=order
result=success
topic=orders.created
listener=orders-consumer
~~~

Nếu cần điều tra một request, dùng logs/traces với correlation ID. Metrics dùng để tổng hợp tỷ lệ, latency và throughput.

## 22. Kiểm thử MDC cleanup

Một unit test cần chứng minh scope khôi phục MDC sau khi hoàn tất:

~~~java
@Test
void restoresPreviousCorrelationId() {
    MDC.put("correlationId", "outer");

    try (CorrelationMdcScope ignored =
             CorrelationMdcScope.open("inner")) {
        assertThat(MDC.get("correlationId")).isEqualTo("inner");
    }

    assertThat(MDC.get("correlationId")).isEqualTo("outer");
    MDC.remove("correlationId");
}

@Test
void removesCorrelationIdWhenThereWasNoPreviousValue() {
    MDC.remove("correlationId");

    try (CorrelationMdcScope ignored =
             CorrelationMdcScope.open("record-1")) {
        assertThat(MDC.get("correlationId")).isEqualTo("record-1");
    }

    assertThat(MDC.get("correlationId")).isNull();
}
~~~

Test exception path:

1. Business service log trong khi MDC đã được đặt.
2. Service ném exception.
3. Xác nhận exception vẫn đi tới error handler.
4. Xác nhận MDC được khôi phục sau invocation.
5. Xử lý record tiếp theo trên cùng consumer thread.
6. Xác nhận ID của record trước không xuất hiện.

### 22.1. Test thread reuse

Dùng executor một thread:

- Submit task có correlation ID A.
- Task hoàn tất và cleanup.
- Submit task không có ID.
- Xác nhận task thứ hai không thấy A.

Đây là test hữu ích để bắt lỗi MDC leak do thread pool reuse.

## 23. Integration test qua Kafka

Dùng Embedded Kafka hoặc Testcontainers để kiểm tra propagation thực tế:

1. Producer tạo correlation ID ổn định.
2. Producer gửi record có header correlation-id.
3. Listener nhận record và đọc header.
4. Listener thiết lập MDC.
5. Test appender thu log trong business service.
6. Xác nhận log có đúng correlation ID.
7. Gửi record tiếp theo với ID khác và xác nhận không lẫn.
8. Gửi record thiếu header và xác nhận fallback policy.
9. Gây exception để kiểm tra cleanup.
10. Nếu có retry topic/DLT, xác nhận header được giữ.
11. Nếu có async executor, xác nhận TaskDecorator truyền và cleanup context.

Mock ConsumerRecord rồi gọi helper chưa chứng minh header thực sự đi qua serializer, broker và deserializer/converter theo cấu hình production.

## 24. Correlation ID trong error handler

MDC trong listener thường được cleanup khi method unwind. Error handler có thể log sau đó, khi MDC đã trở về trạng thái trước invocation.

Nếu cần correlation ID trong log recovery:

- Đọc header trực tiếp từ ConsumerRecord trong custom recoverer.
- Đưa ID vào structured log field của recovery operation.
- Không phụ thuộc MDC của listener đã kết thúc.
- Giữ header qua retry và DLT republish.
- Dùng một recovery/attempt ID riêng nếu cần phân biệt các lần thử.

Đây là ranh giới quan trọng giữa **context trong listener method** và **context của container/error handler**.

## 25. Runbook khi correlation ID bị thiếu hoặc sai

1. Xác định service đầu tiên trong flow.
2. Kiểm tra request/gateway có nhận hoặc tạo correlation ID không.
3. Xác nhận producer gửi đúng Kafka header name.
4. Kiểm tra encoding và header bytes.
5. Kiểm tra retry/DLT republish có giữ header không.
6. Xác nhận listener đọc ConsumerRecord hoặc mapped header đúng.
7. Kiểm tra MDC setup xảy ra trước business logs.
8. Kiểm tra finally/try-with-resources cleanup.
9. Với async processing, xác nhận TaskDecorator/context propagation.
10. Kiểm tra Logback pattern hoặc JSON encoder có xuất MDC field.
11. Tìm service dùng tên field không thống nhất.
12. Xác minh ID không chứa PII/secrets và không thể gây log injection.
13. Dùng integration test để tái hiện qua Kafka.
14. Ghi rõ fallback policy khi header missing/invalid.

Nếu chỉ một service thiếu ID, so sánh header contract ở producer và listener mapping. Nếu mọi service đều thiếu, kiểm tra gateway hoặc propagation ở đầu luồng.

## 26. Những lỗi thường gặp

**Chỉ gọi MDC.put mà không remove.** Consumer thread được tái sử dụng, ID cũ có thể xuất hiện trong log record mới.

**Chỉ cleanup trên happy path.** Exception path vẫn để rò MDC; luôn dùng finally hoặc try-with-resources.

**Cho rằng MDC tự đi qua Kafka.** Kafka cần header propagation rõ ràng.

**Cho rằng MDC tự đi qua executor.** Thread pool cần TaskDecorator hoặc context propagation.

**Dùng một correlation ID cho toàn batch.** Batch có thể chứa nhiều message thuộc các flows khác nhau.

**Dùng event ID hoặc offset làm correlation ID.** Chúng có semantics khác.

**Dùng correlation ID làm metric label.** Cardinality tăng mạnh.

**Tin mọi header do producer gửi.** Header cần validation và giới hạn chiều dài/ký tự.

**Không giữ ID qua retry/DLT.** Log lần xử lý sau không còn liên kết với flow ban đầu.

**Nhầm correlation ID với trace ID.** Một cái liên kết business logs; một cái liên kết tracing spans.

**Tự parse traceparent để set MDC.** Hãy dùng tracing propagator cho trace context.

**Dựa vào MDC trong error handler sau khi listener unwind.** Listener finally có thể đã cleanup; error handler nên lấy ID trực tiếp từ record.

## 27. Checklist triển khai

- [ ] Chuẩn hóa Kafka header name, encoding và format.
- [ ] Producer giữ correlation ID qua các message liên quan.
- [ ] Consumer đọc header từ ConsumerRecord hoặc mapped message header.
- [ ] Validate độ dài và ký tự.
- [ ] Xác định policy khi header thiếu hoặc trùng.
- [ ] Thiết lập MDC trước business logs.
- [ ] Cleanup/restore MDC trong finally hoặc try-with-resources.
- [ ] Batch listener dùng MDC scope riêng cho mỗi record.
- [ ] Async executor có TaskDecorator/context propagation.
- [ ] Retry topic và DLT giữ correlation header.
- [ ] Error handler/recoverer lấy ID từ record khi cần.
- [ ] Logging pattern hoặc JSON encoder xuất MDC key.
- [ ] Không đưa correlation ID vào metric labels.
- [ ] Không log secrets/PII hoặc dữ liệu gây log injection.
- [ ] Phân biệt correlation ID, trace ID, event ID và offset.
- [ ] Test success, exception, missing header, thread reuse, retry và DLT.

## 28. Ví dụ tổng hợp: Order Fulfillment

Order API nhận request tạo đơn hàng với correlation ID **order-flow-9281**. API publish event:

~~~java
ProducerRecord<String, OrderCreated> record =
    new ProducerRecord<>(
        "orders.created",
        orderId,
        event
    );

record.headers().add(
    "correlation-id",
    "order-flow-9281".getBytes(StandardCharsets.UTF_8)
);

kafkaTemplate.send(record);
~~~

Consumer:

~~~java
@KafkaListener(
    id = "order-fulfillment",
    topics = "orders.created",
    groupId = "fulfillment-workers"
)
public void consume(ConsumerRecord<String, OrderCreated> record) {
    String id = CorrelationIds.from(record);

    try (CorrelationMdcScope ignored =
             CorrelationMdcScope.open(id)) {

        log.info("Order event received");
        inventoryService.reserve(record.value());
        paymentService.authorize(record.value());
        log.info("Order fulfilled");
    }
}
~~~

Log:

~~~text
INFO correlationId=order-flow-9281 Order event received
INFO correlationId=order-flow-9281 Inventory reserved
INFO correlationId=order-flow-9281 Payment authorized
INFO correlationId=order-flow-9281 Order fulfilled
~~~

Nếu payment service chạy async, context phải được capture và restore ở executor. Nếu listener lỗi và record được retry, retry record cần giữ correlation-id header. Consumer thiết lập lại MDC từ header ở mỗi attempt.

Correlation ID giúp tìm log thuộc cùng order flow. Event ID vẫn dùng để deduplicate từng event; trace ID vẫn dùng để điều tra spans và quan hệ parent/child.

## 29. Ghi nhớ

**Correlation ID trong MDC** giúp log của cùng một luồng xử lý Kafka có thể được tìm kiếm cùng nhau. Producer truyền ID qua Kafka header; Spring Kafka consumer đọc header từ ConsumerRecord, validate rồi thiết lập MDC trước business logic.

MDC gắn với thread, nên phải **cleanup hoặc restore trong finally**. Với batch listener, tạo scope riêng cho từng record; với async executor, capture/restore context qua TaskDecorator hoặc cơ chế propagation phù hợp. Retry và DLT cần giữ correlation header để log ở các lần xử lý sau còn liên kết với flow ban đầu.

Correlation ID khác trace ID, message ID và Kafka offset. Dùng nó cho logs/traces theo policy, không dùng làm metric label, không chứa PII/secrets và không coi nó là cơ chế authorization. Một triển khai tin cậy cần contract header rõ ràng, validation, logging configuration, idempotency và integration tests qua Kafka.
