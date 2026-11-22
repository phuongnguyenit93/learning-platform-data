# Correlation ID trong log

## 1. Vì sao cần Correlation ID trong log?

Trong một hệ thống Spring Kafka, một nghiệp vụ có thể đi qua nhiều service và nhiều topic. Ví dụ, API nhận yêu cầu tạo đơn hàng, Order service ghi sự kiện `OrderCreated`, Inventory service giữ hàng, Payment service xử lý thanh toán rồi Notification service gửi thông báo. Mỗi service có log riêng và mỗi consumer xử lý record trên thread riêng.

Khi một bước thất bại, chỉ tìm theo tên topic hoặc timestamp thường không đủ để nối các log thuộc cùng một luồng nghiệp vụ. Correlation ID là định danh được truyền cùng thông điệp qua các service để nhóm log liên quan lại với nhau.

```text
HTTP request
  correlationId = c-8a91
       |
       v
Order service
  log: order accepted, correlationId=c-8a91
       |
       | Kafka record + x-correlation-id=c-8a91
       v
orders topic
       |
       v
Inventory service
  log: stock reserved, correlationId=c-8a91
       |
       | Kafka record + x-correlation-id=c-8a91
       v
payments topic
       |
       v
Payment service
  log: payment declined, correlationId=c-8a91
```

Khi tìm `c-8a91` trong hệ thống log tập trung, người vận hành có thể xem các bước xử lý liên quan dù chúng nằm ở nhiều ứng dụng khác nhau.

Correlation ID đặc biệt hữu ích khi:

- Một request tạo ra nhiều Kafka event hoặc nhiều bước xử lý.
- Nhiều record được xử lý đồng thời và log xen kẽ nhau.
- Consumer retry hoặc chuyển record sang dead-letter topic (DLT).
- Một service nhận event rồi phát event tiếp theo.
- Cần điều tra một giao dịch nghiệp vụ cụ thể qua nhiều service.

## 2. Phân biệt Correlation ID, Trace ID, Request ID và Event ID

Các định danh này có thể cùng xuất hiện trong log nhưng phục vụ những mục đích khác nhau:

| Định danh | Phạm vi | Mục đích |
|---|---|---|
| Correlation ID | Một luồng nghiệp vụ hoặc một request liên quan | Nhóm log và message thuộc cùng luồng xử lý |
| Trace ID | Một distributed trace | Liên kết các span và thể hiện quan hệ thời gian giữa các service |
| Request ID | Một lần gọi API hoặc command | Nhận diện request tại ingress và audit |
| Event ID | Một sự kiện cụ thể | Deduplicate, idempotency và truy vết sự kiện |
| Kafka key | Một Kafka record | Chọn partition và giữ thứ tự theo key trong partition |

Ví dụ, một request tạo đơn hàng có thể phát ra `OrderCreated`, `InventoryReserved` và `PaymentRequested`. Cả ba event có thể dùng cùng correlation ID vì thuộc cùng nghiệp vụ, nhưng mỗi event có event ID riêng. Nếu hệ thống tạo một trace mới cho mỗi message consumer, trace ID có thể khác nhau nhưng vẫn mang cùng correlation ID để nối nghiệp vụ.

Không dùng correlation ID thay cho event ID trong bảng idempotency. Một correlation ID có thể xuất hiện trên nhiều event hợp lệ; nếu deduplicate bằng correlation ID, consumer có thể loại nhầm các event khác nhau trong cùng một luồng.

Correlation ID cũng không phải trace context. Khi cần distributed tracing, hãy propagate W3C Trace Context (`traceparent`, `tracestate`) hoặc định dạng mà tracing system đang sử dụng. Correlation ID hỗ trợ tìm kiếm nghiệp vụ trong log; trace ID hỗ trợ phân tích span, latency và dependency.

## 3. Chọn tên header và quy ước truyền qua Kafka

Với event-driven flow thông thường, có thể dùng header nghiệp vụ riêng, ví dụ:

```text
x-correlation-id
```

Đây là tên header do ứng dụng quy ước. Nên thống nhất tên, encoding và quy tắc tạo ID giữa các service. Dùng UTF-8 cho giá trị chuỗi để các ngôn ngữ khác nhau có thể đọc cùng một header.

Spring Kafka cũng có hằng số `KafkaHeaders.CORRELATION_ID`. Header này được dùng mặc định cho request-reply, đặc biệt với `ReplyingKafkaTemplate`. Nếu dùng request-reply, không ghi đè giá trị mà Spring Kafka đang dùng để ghép response với request. Với correlation ID của luồng event nghiệp vụ, header riêng `x-correlation-id` giúp phân biệt rõ hai mục đích.

Kafka header là cặp tên và byte array. Header có thể lặp tên nhiều lần, vì vậy ứng dụng cần quy ước chỉ gửi một giá trị correlation ID cho mỗi record. Ở phía nhận, `lastHeader(name)` lấy giá trị cuối cùng nếu có nhiều header cùng tên. Nếu phát hiện header trùng bất thường, có thể log cảnh báo và áp dụng chính sách từ chối hoặc chọn giá trị theo hợp đồng đã thống nhất.

## 4. Tạo Correlation ID tại điểm tiếp nhận request

Correlation ID nên được tạo tại ingress nếu request chưa có ID đáng tin cậy. Nếu client gửi ID qua HTTP header, ứng dụng có thể tiếp nhận sau khi kiểm tra định dạng và độ dài.

Ví dụ helper đơn giản:

```java
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import java.util.regex.Pattern;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;

public final class CorrelationIds {

    public static final String HEADER = "x-correlation-id";
    public static final String MDC_KEY = "correlationId";
    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9._:-]{1,128}");

    private CorrelationIds() {
    }

    public static String resolve(String supplied) {
        if (supplied != null && SAFE_ID.matcher(supplied).matches()) {
            return supplied;
        }
        return UUID.randomUUID().toString();
    }

    public static String readFrom(ConsumerRecord<?, ?> record) {
        Header header = record.headers().lastHeader(HEADER);
        if (header == null || header.value() == null) {
            return null;
        }
        return new String(header.value(), StandardCharsets.UTF_8);
    }
}
```

Giới hạn ký tự giúp tránh log injection qua ký tự xuống dòng hoặc chuỗi bất thường. Nếu ID do ứng dụng sinh, UUID là lựa chọn đơn giản. Một số hệ thống dùng ULID hoặc ID do API gateway cấp; điều quan trọng là ID duy nhất trong phạm vi tìm kiếm và được truyền nhất quán.

Không dùng email, số điện thoại, access token hoặc dữ liệu cá nhân làm correlation ID. ID nên là giá trị opaque, không chứa bí mật hoặc thông tin nhạy cảm.

Ví dụ tại HTTP controller/service, sau khi resolve ID, ứng dụng thêm nó vào Kafka record:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@Service
public class OrderCommandService {

    private static final Logger log = LoggerFactory.getLogger(OrderCommandService.class);
    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderCommandService(KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event, String incomingCorrelationId) {

        String correlationId = CorrelationIds.resolve(incomingCorrelationId);
        ProducerRecord<String, OrderCreated> record = new ProducerRecord<>(
                "orders", event.orderId(), event);

        record.headers().add(new RecordHeader(
                CorrelationIds.HEADER,
                correlationId.getBytes(StandardCharsets.UTF_8)));

        try (MdcScope ignored = MdcScope.with(CorrelationIds.MDC_KEY, correlationId)) {
            log.info("Publishing order event: orderId={}", event.orderId());
            return kafkaTemplate.send(record);
        }
    }
}
```

Trong hệ thống có nhiều producer path, nên đóng gói thao tác thêm header vào một publisher/helper dùng chung để tránh một số event có correlation ID còn một số event bị thiếu.

Ví dụ khai báo `CompletableFuture` ở trên dùng Spring Kafka 3.0 trở lên. Với Spring Kafka 2.x, `KafkaTemplate.send()` trả về `ListenableFuture`; điều chỉnh kiểu trả về hoặc chuyển đổi future theo API của phiên bản dự án.

Scope MDC ở ví dụ chỉ bao quanh lời gọi `send()` và log đồng bộ trước khi gửi. Việc hoàn tất send là bất đồng bộ; nếu cần log trong callback của future, hãy capture `correlationId` và mở một MDC scope mới bên trong callback vì MDC của thread gọi không tự truyền sang producer callback thread.

## 5. Đọc Correlation ID từ ConsumerRecord

`@KafkaListener` có thể nhận trực tiếp `ConsumerRecord<K,V>`. Đây là cách rõ ràng để đọc native Kafka headers, đặc biệt khi cần xử lý byte array hoặc kiểm tra header bị thiếu.

```java
@Component
public class OrderListener {

    private static final Logger log = LoggerFactory.getLogger(OrderListener.class);

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(topics = "orders", groupId = "inventory-service")
    public void onOrder(ConsumerRecord<String, OrderCreated> record) {
        String correlationId = CorrelationIds.readFrom(record);

        log.info("Received order event: topic={}, partition={}, offset={}, correlationId={}",
                record.topic(), record.partition(), record.offset(), correlationId);

        orderService.reserveStock(record.value());
    }
}
```

Đoạn code minh họa việc đọc và log ID. Trong production, nên đưa correlation ID vào MDC hoặc Observation context để các log bên trong `orderService` tự động có cùng trường, thay vì truyền tham số qua mọi câu lệnh log.

Nếu dùng Spring Message conversion thay vì `ConsumerRecord`, có thể nhận header bằng `@Header`:

```java
@KafkaListener(topics = "orders", groupId = "inventory-service")
public void onOrder(
        OrderCreated event,
        @Header(name = "x-correlation-id", required = false) byte[] correlationHeader) {

    String correlationId = correlationHeader == null
            ? null
            : new String(correlationHeader, StandardCharsets.UTF_8);

    orderService.reserveStock(event, correlationId);
}
```

Khả năng chuyển đổi header phụ thuộc message converter và header mapper. Khi cần kiểm soát chính xác native header bytes, `ConsumerRecord` là lựa chọn trực tiếp hơn.

## 6. Gắn Correlation ID vào MDC

MDC (Mapped Diagnostic Context) là cơ chế của SLF4J để gắn các giá trị ngữ cảnh vào log event. Với Logback, pattern có thể đọc giá trị MDC bằng `%X{correlationId}`.

Nếu chỉ log correlation ID ở một câu lệnh, có thể truyền ID như một field trong log. Nhưng khi service gọi nhiều component và các component đều ghi log, MDC giúp tự động thêm ID vào toàn bộ log đồng bộ trong cùng thread.

Ví dụ helper lưu và khôi phục MDC:

```java
import org.slf4j.MDC;

public final class MdcScope implements AutoCloseable {

    private final String key;
    private final String previousValue;

    private MdcScope(String key, String value) {
        this.key = key;
        this.previousValue = MDC.get(key);

        if (value == null) {
            MDC.remove(key);
        } else {
            MDC.put(key, value);
        }
    }

    public static MdcScope with(String key, String value) {
        return new MdcScope(key, value);
    }

    @Override
    public void close() {
        if (previousValue == null) {
            MDC.remove(key);
        } else {
            MDC.put(key, previousValue);
        }
    }
}
```

Sử dụng trong listener:

```java
@KafkaListener(topics = "orders", groupId = "inventory-service")
public void onOrder(ConsumerRecord<String, OrderCreated> record) {
    String correlationId = CorrelationIds.readFrom(record);

    try (MdcScope ignored = MdcScope.with(CorrelationIds.MDC_KEY, correlationId)) {
        log.info("Start processing orderId={}", record.value().orderId());
        orderService.reserveStock(record.value());
        log.info("Finished processing orderId={}", record.value().orderId());
    }
}
```

`try-with-resources` bảo đảm khôi phục MDC kể cả khi service ném exception. Việc khôi phục giá trị cũ cũng an toàn hơn gọi `MDC.clear()` vì thread có thể đang chứa các MDC key khác do tracing hoặc framework thiết lập.

## 7. Tự động gắn MDC bằng RecordInterceptor

Nếu muốn correlation ID có sẵn trước khi listener method chạy, có thể dùng `RecordInterceptor`. Interceptor được gọi trước listener và có callback sau khi listener kết thúc bình thường hoặc ném exception.

Từ Spring Kafka 2.8, `afterRecord()` được gọi sau `success()` hoặc `failure()`. Đây là vị trí phù hợp để khôi phục MDC cho thread consumer được tái sử dụng.

```java
@Component
public class CorrelationMdcInterceptor
        implements RecordInterceptor<String, OrderCreated> {

    private static final String MDC_KEY = "correlationId";
    private final ThreadLocal<String> previousValue = new ThreadLocal<>();

    @Override
    public ConsumerRecord<String, OrderCreated> intercept(
            ConsumerRecord<String, OrderCreated> record,
            Consumer<String, OrderCreated> consumer) {

        previousValue.set(MDC.get(MDC_KEY));
        String correlationId = CorrelationIds.readFrom(record);

        if (correlationId == null) {
            MDC.remove(MDC_KEY);
        } else {
            MDC.put(MDC_KEY, correlationId);
        }

        return record;
    }

    @Override
    public void afterRecord(
            ConsumerRecord<String, OrderCreated> record,
            Consumer<String, OrderCreated> consumer) {

        String previous = previousValue.get();
        if (previous == null) {
            MDC.remove(MDC_KEY);
        } else {
            MDC.put(MDC_KEY, previous);
        }
        previousValue.remove();
    }

}
```

Đăng ký interceptor vào listener container factory:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated> orderListenerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        CorrelationMdcInterceptor correlationMdcInterceptor) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.setRecordInterceptor(correlationMdcInterceptor);
    return factory;
}
```

Listener dùng factory này:

```java
@KafkaListener(
        topics = "orders",
        groupId = "inventory-service",
        containerFactory = "orderListenerFactory")
public void onOrder(OrderCreated event) {
    log.info("Processing orderId={}", event.orderId());
    orderService.reserveStock(event);
}
```

Trong ví dụ, `ThreadLocal` lưu MDC value trước khi interceptor ghi correlation ID mới. `afterRecord()` khôi phục giá trị cũ và xóa ThreadLocal entry để không giữ dữ liệu giữa các record. Nếu chỉ gọi `MDC.put()` mà không cleanup, record kế tiếp chạy trên cùng consumer thread có thể ghi nhầm correlation ID của record trước.

Với Spring Kafka 2.7, `success()` và `failure()` đã có nhưng `afterRecord()` chưa có; có thể thực hiện cleanup trong cả hai callback. Từ 2.8 trở lên, dùng `afterRecord()` để gom cleanup vào một nơi. Không cấu hình interceptor này để trả `null`; trả `null` có nghĩa bỏ qua record và listener sẽ không chạy.

## 8. MDC và thread reuse trong consumer concurrency

`KafkaMessageListenerContainer` xử lý record trên một consumer thread. `ConcurrentMessageListenerContainer` tạo nhiều child container để xử lý song song; mỗi child có consumer thread riêng.

MDC dựa trên ThreadLocal. Điều đó có nghĩa:

- Trong một lần gọi listener đồng bộ, các log trên cùng thread nhìn thấy cùng correlation ID.
- Với concurrency nhiều consumer, mỗi thread có MDC riêng.
- Consumer thread được tái sử dụng cho nhiều record nên phải xóa hoặc khôi phục MDC sau mỗi record.
- MDC không tự động truyền sang thread pool, `@Async`, `CompletableFuture` callback hoặc scheduler khác.

Nếu service khởi chạy công việc bất đồng bộ, cần truyền correlation ID rõ ràng vào task hoặc dùng Micrometer Context Propagation/Observation để capture và restore context. Không giả định MDC của consumer thread tự xuất hiện trên thread xử lý nền.

Ví dụ truyền ID rõ ràng:

```java
String correlationId = MDC.get("correlationId");
executor.execute(() -> {
    try (MdcScope ignored = MdcScope.with("correlationId", correlationId)) {
        backgroundService.run();
    }
});
```

Nếu dùng executor dùng chung, luôn cleanup MDC trong task bằng scope tương tự. Thread pool cũng tái sử dụng thread nên lỗi context leakage có thể xuất hiện ở đây.

## 9. Cấu hình Logback để in correlation ID

Sau khi đặt MDC, Logback pattern có thể thêm trường correlation ID:

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level [%thread] corr=%X{correlationId:-none} %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE" />
    </root>
</configuration>
```

Log có thể hiển thị như sau:

```text
2026-11-17T10:15:22.105+07:00 INFO  [org.springframework.kafka.KafkaListenerEndpointContainer#0-0-C-1] corr=c-8a91 OrderService - Start processing orderId=ORD-42
2026-11-17T10:15:22.143+07:00 INFO  [org.springframework.kafka.KafkaListenerEndpointContainer#0-0-C-1] corr=c-8a91 InventoryService - Stock reserved for orderId=ORD-42
```

`%X{correlationId:-none}` in `none` khi MDC không có key. Nhờ vậy log không bị trống trường và người vận hành nhận biết được message chưa mang correlation ID.

Nếu dùng JSON encoder, cấu hình MDC key thành field JSON `correlationId` thay vì chỉ nối vào message text. Structured logging giúp hệ thống log tìm kiếm và lọc theo field chính xác hơn.

## 10. Dùng @Header thay cho ConsumerRecord

Nếu listener chỉ cần payload và correlation ID, không cần toàn bộ native record, có thể nhận header trực tiếp:

```java
@KafkaListener(topics = "orders", groupId = "inventory-service")
public void onOrder(
        OrderCreated event,
        @Header(name = "x-correlation-id", required = false) byte[] rawCorrelationId) {

    String correlationId = rawCorrelationId == null
            ? null
            : new String(rawCorrelationId, StandardCharsets.UTF_8);

    try (MdcScope ignored = MdcScope.with("correlationId", correlationId)) {
        log.info("Received orderId={}", event.orderId());
        orderService.reserveStock(event);
    }
}
```

Khi dùng `@Header`, header mapper/converter tham gia quá trình chuyển native Kafka header sang Spring Message header. Nếu ứng dụng cần byte chính xác hoặc cần xem header lặp, nhận `ConsumerRecord` trực tiếp dễ kiểm soát hơn.

Các metadata record khác cũng có thể nhận qua `@Header`, ví dụ `KafkaHeaders.RECEIVED_TOPIC`, `KafkaHeaders.RECEIVED_PARTITION` và `KafkaHeaders.OFFSET`. Những metadata này hữu ích để log vị trí Kafka cùng correlation ID.

## 11. Ghi correlation ID khi publish event tiếp theo

Khi consumer nhận một event rồi publish event mới, correlation ID nên được truyền tiếp. Không tạo correlation ID mới ở mỗi hop nếu các event vẫn thuộc cùng luồng nghiệp vụ.

Ví dụ:

```java
public void publishInventoryReserved(
        ConsumerRecord<String, OrderCreated> inbound,
        InventoryReserved event) {

    Header inboundHeader = inbound.headers().lastHeader(CorrelationIds.HEADER);
    String correlationId = inboundHeader == null || inboundHeader.value() == null
            ? UUID.randomUUID().toString()
            : new String(inboundHeader.value(), StandardCharsets.UTF_8);

    ProducerRecord<String, InventoryReserved> outbound = new ProducerRecord<>(
            "inventory.reserved", event.orderId(), event);
    outbound.headers().add(new RecordHeader(
            CorrelationIds.HEADER,
            correlationId.getBytes(StandardCharsets.UTF_8)));

    kafkaTemplate.send(outbound);
}
```

Nếu correlation ID đã được resolve ở listener/interceptor, có thể lấy từ context hiện tại hoặc truyền thành tham số. Truyền tường minh thường dễ kiểm thử hơn khi service xử lý bất đồng bộ. Dù chọn cách nào, cần đảm bảo ID không bị thay đổi giữa các hop.

Nếu tạo một luồng nghiệp vụ con độc lập, có thể sinh correlation ID mới và lưu ID cha trong header riêng như `causation-id` hoặc `parent-correlation-id`, theo hợp đồng event của tổ chức. Không tự ý đổi ID nếu event vẫn thuộc cùng một giao dịch.

## 12. Correlation ID trong retry và dead-letter topic

Khi listener thất bại, cùng một record có thể được giao lại nhiều lần. Correlation ID phải tiếp tục có mặt trong log ở mỗi lần thử để người vận hành nối được lần xử lý ban đầu, retry và recovery.

Ví dụ log:

```text
INFO  corr=c-8a91 orderId=ORD-42 attempt=1 Processing order
WARN  corr=c-8a91 orderId=ORD-42 attempt=1 Inventory service unavailable
INFO  corr=c-8a91 orderId=ORD-42 attempt=2 Retrying order
ERROR corr=c-8a91 orderId=ORD-42 attempt=2 Sending record to orders.DLT
```

Có thể đọc delivery attempt header do Spring Kafka cung cấp khi bật `deliveryAttemptHeader` trên listener container. Correlation ID và delivery attempt có vai trò khác nhau: correlation ID nối luồng nghiệp vụ; delivery attempt cho biết lần listener được giao record trong cơ chế retry tương ứng.

Khi dùng `DefaultErrorHandler` và `DeadLetterPublishingRecoverer`, cần xác minh custom correlation header vẫn được giữ trên DLT record bằng integration test. Nếu custom recoverer tạo `ProducerRecord` mới, phải copy header correlation ID sang record đích. Không giả định một publisher tùy chỉnh tự bảo toàn mọi header.

Với retry topic (`@RetryableTopic`), header nghiệp vụ nên được giữ khi record được chuyển qua các retry topic. Kiểm thử cả header gốc, retry metadata và DLT để đảm bảo dashboard/log tìm được cùng correlation ID xuyên suốt chuỗi.

## 13. Correlation ID trong request-reply

Spring Kafka dùng `KafkaHeaders.CORRELATION_ID` mặc định để `ReplyingKafkaTemplate` ghép response với request đang chờ. Responder cần echo đúng header này trong reply. Header có kiểu native `byte[]`.

Nếu request-reply cũng cần correlation ID nghiệp vụ trong log, có thể:

- Dùng cùng một ID nghiệp vụ trong custom header `x-correlation-id` và giữ nguyên `KafkaHeaders.CORRELATION_ID` riêng cho giao thức reply.
- Hoặc dùng `KafkaHeaders.CORRELATION_ID` làm ID duy nhất nếu hợp đồng ứng dụng xác định rõ giá trị này đồng thời là correlation ID nghiệp vụ.

Không ghi đè `KafkaHeaders.CORRELATION_ID` khi `ReplyingKafkaTemplate` đang quản lý Future. Nếu thay đổi giá trị, response có thể không khớp với request và Future timeout.

Ví dụ listener nhận cả hai:

```java
import java.util.Base64;

@KafkaListener(topics = "order.requests", groupId = "order-query")
@SendTo
public OrderReply handle(
        OrderRequest request,
        @Header(KafkaHeaders.CORRELATION_ID) byte[] requestReplyId,
        @Header(name = "x-correlation-id", required = false) byte[] businessCorrelationId) {

    String correlationId = businessCorrelationId == null
            ? Base64.getUrlEncoder().withoutPadding().encodeToString(requestReplyId)
            : new String(businessCorrelationId, StandardCharsets.UTF_8);

    try (MdcScope ignored = MdcScope.with("correlationId", correlationId)) {
        log.info("Handling requestId={}", request.requestId());
        return orderQueryService.handle(request);
    }
}
```

Trong ví dụ, `KafkaHeaders.CORRELATION_ID` được coi là opaque bytes và chỉ mã hóa Base64 URL-safe khi cần dùng làm giá trị fallback để log. Không giả định byte array do `ReplyingKafkaTemplate` tạo ra luôn là UTF-8 text; nếu cần ID nghiệp vụ dễ đọc, hãy dùng custom header riêng.

Với request-reply, Spring Kafka listener infrastructure echo correlation header phục vụ định tuyến response. Khi dùng header custom, cần cấu hình echo/propagation theo phiên bản và giao thức; không giả định custom header tự động được dùng thay header mặc định.

## 14. Correlation ID và Micrometer Observation/Tracing

Spring Kafka hỗ trợ Micrometer Observation cho `KafkaTemplate` và listener containers từ phiên bản 3.0. Có thể bật observation để ghi nhận hoạt động gửi và nhận message:

```java
@Bean
KafkaTemplate<String, OrderCreated> kafkaTemplate(
        ProducerFactory<String, OrderCreated> producerFactory) {

    KafkaTemplate<String, OrderCreated> template =
            new KafkaTemplate<>(producerFactory);
    template.setObservationEnabled(true);
    return template;
}
```

Với listener container factory:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated> orderListenerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setObservationEnabled(true);
    return factory;
}
```

Khi Micrometer Tracing và propagator phù hợp được cấu hình, Observation có thể tạo span cho thao tác producer/consumer và truyền trace context qua message headers. Đây là cơ chế tracing riêng với custom `x-correlation-id` của nghiệp vụ. Có thể dùng cả hai: trace ID để mở distributed trace, correlation ID để tìm log theo luồng nghiệp vụ.

Khi bật Observation trên `KafkaTemplate` hoặc container, Micrometer timers truyền thống cho thành phần đó được quản lý qua observation thay vì timer cũ. Với batch listener, hành vi observation phụ thuộc phiên bản; trong Spring Kafka 4.1, mặc định không tạo observation nếu chỉ có batch listener, có thể bật `recordObservationsInBatch` để tạo observation theo từng record.

Các observation convention mặc định thêm tag có cardinality thấp như `bean.name` cho template và `listener.id` cho listener. Có thể tùy chỉnh convention để thêm metadata cần thiết. Không thêm correlation ID, event ID, order ID hoặc offset làm metric tag; các giá trị này có cardinality cao và nên nằm trong log hoặc trace.

## 15. Correlation ID trong batch listener

Một batch có thể chứa nhiều record với correlation ID khác nhau. Vì vậy không đặt một correlation ID duy nhất vào MDC cho toàn bộ batch rồi xử lý tất cả record; log của record khác có thể mang sai ID.

Thay vào đó, lặp từng record và mở MDC scope riêng:

```java
@KafkaListener(
        topics = "orders",
        groupId = "inventory-service",
        containerFactory = "batchOrderListenerFactory")
public void onOrders(List<ConsumerRecord<String, OrderCreated>> records) {
    for (ConsumerRecord<String, OrderCreated> record : records) {
        String correlationId = CorrelationIds.readFrom(record);

        try (MdcScope ignored = MdcScope.with("correlationId", correlationId)) {
            log.info("Processing batch record orderId={}, partition={}, offset={}",
                    record.value().orderId(), record.partition(), record.offset());
            orderService.reserveStock(record.value());
        }
    }
}
```

Nếu xử lý batch song song bằng executor, mỗi task phải nhận correlation ID của record tương ứng và mở MDC scope trên thread thực thi. Không dùng chung một MDC map giữa các record.

## 16. Correlation ID và structured logging

Trong production, log nên là structured data thay vì chỉ nối correlation ID vào câu text. Một event log có thể chứa:

```json
{
  "timestamp": "2026-11-17T10:15:22.105+07:00",
  "level": "INFO",
  "service": "inventory-service",
  "message": "Stock reserved",
  "correlationId": "c-8a91",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "eventId": "evt-10042",
  "topic": "orders",
  "partition": 2,
  "offset": 108,
  "consumerGroup": "inventory-service"
}
```

Những field này cho phép tìm kiếm theo correlation ID, kiểm tra đúng event ID, hoặc đi sâu đến vị trí record trong Kafka. Chỉ ghi những field thật sự có sẵn trong context; không tự suy ra partition/offset khi log từ tầng service không có metadata.

Một số nguyên tắc:

- Dùng cùng tên field (`correlationId`) ở tất cả service.
- Ghi `service`, `environment`, `topic`, `partition`, `offset` và `consumerGroup` khi có ích cho điều tra.
- Giữ `eventId` riêng với correlation ID.
- Không ghi toàn bộ payload nếu chứa dữ liệu nhạy cảm.
- Chuẩn hóa exception class và error code; stack trace chỉ ghi ở nơi phù hợp.
- Tránh nhúng ID vào `message` text nếu có thể ghi thành field riêng.

## 17. Correlation ID và metrics: tránh cardinality cao

Correlation ID thường gần như duy nhất cho mỗi request. Nếu đưa ID này vào Micrometer tag, mỗi request có thể tạo một time series mới. Điều đó làm tăng bộ nhớ, chi phí scrape và dung lượng lưu trữ metrics.

Không làm như sau:

```java
Counter.builder("app.kafka.processed")
        .tag("correlationId", correlationId)
        .register(meterRegistry)
        .increment();
```

Hãy dùng tag có tập giá trị hữu hạn:

```java
Counter.builder("app.kafka.processed")
        .tag("topic", record.topic())
        .tag("listener", "orders")
        .tag("result", "success")
        .register(meterRegistry)
        .increment();
```

Correlation ID dành cho log và trace; metrics dành cho tổng hợp theo topic, listener, result, exception class hoặc môi trường.

## 18. Bảo mật và độ tin cậy của Correlation ID

Correlation ID có thể đến từ HTTP client hoặc service bên ngoài nên phải coi là dữ liệu đầu vào không đáng tin cậy.

- Giới hạn độ dài, charset và format.
- Không dùng ID để xác thực người gọi hoặc cấp quyền truy cập.
- Không chứa token, password, thông tin thanh toán hoặc dữ liệu cá nhân.
- Tránh ký tự điều khiển, newline và ký tự có thể làm giả nhiều dòng log.
- Nếu một gateway có trách nhiệm tạo ID chuẩn, các service phía sau nên tuân theo chính sách tin cậy của gateway.
- Không ghi giá trị header chưa kiểm tra trực tiếp vào log.

Correlation ID không nhất thiết phải bí mật, nhưng phải tránh cho phép người ngoài kiểm soát log format hoặc tạo cardinality vô hạn trong hệ thống tìm kiếm.

## 19. Kiểm thử Correlation ID trong log

Kiểm thử cần xác nhận header được truyền, MDC được thiết lập và cleanup đúng khi listener thành công lẫn thất bại.

1. **Producer thêm header:** gửi record và xác nhận `x-correlation-id` tồn tại với UTF-8 bytes đúng.
2. **Consumer đọc header:** xác nhận listener nhận đúng correlation ID.
3. **Log trong service:** dùng Logback ListAppender hoặc appender test để xác nhận MDC field xuất hiện trong log.
4. **Header thiếu:** xác nhận log hiển thị `none` hoặc ID fallback theo chính sách.
5. **Record liên tiếp:** xử lý hai record có ID khác nhau trên cùng consumer thread và xác nhận ID không bị rò từ record trước.
6. **Listener ném exception:** xác nhận interceptor `afterRecord()` vẫn khôi phục MDC.
7. **Retry:** xác nhận mỗi lần giao lại vẫn có cùng correlation ID và delivery attempt thay đổi đúng.
8. **DLT:** xác nhận custom header được giữ hoặc được copy sang record DLT.
9. **Forward event:** xác nhận producer ở service downstream truyền nguyên correlation ID sang topic tiếp theo.
10. **Batch:** xác nhận từng record log đúng ID riêng, không dùng chung ID cho cả batch.
11. **Async task:** xác nhận context được truyền rõ ràng sang executor và cleanup sau task.
12. **Invalid ID:** xác nhận header quá dài hoặc có newline bị thay bằng ID mới/từ chối theo chính sách.
13. **Metrics:** xác nhận correlation ID không xuất hiện trong tag.

Với `spring-kafka-test` hoặc Testcontainers Kafka, có thể kiểm tra end-to-end header. Với log, dùng appender test để đọc MDC map của từng `ILoggingEvent`; không chỉ assert chuỗi message vì pattern console có thể che mất MDC field.

## 20. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Log ở consumer không có correlation ID | Producer không thêm header hoặc header mapper không expose header | Kiểm tra native record headers và thống nhất tên header |
| Tất cả record có cùng correlation ID | MDC không được cleanup trên consumer thread | Dùng `try/finally`, `MdcScope` hoặc interceptor `afterRecord()` |
| Log service có ID nhưng log async không có | MDC không tự truyền sang thread khác | Truyền ID vào task hoặc dùng Micrometer Context Propagation |
| ReplyingKafkaTemplate timeout | Ghi đè `KafkaHeaders.CORRELATION_ID` làm reply không khớp | Giữ nguyên header request-reply của Spring Kafka |
| Correlation ID thay đổi giữa service | Publisher tạo ID mới ở mỗi hop | Propagate ID gốc; chỉ tạo ID mới cho workflow con độc lập |
| DLT không tìm được log gốc | Custom recoverer không copy header hoặc log không ghi ID | Bảo toàn header và kiểm thử DLT path |
| Metrics tăng cardinality | Correlation ID được dùng làm tag | Chuyển ID sang log/trace; dùng tag hữu hạn |
| Header có nhiều giá trị | Producer thêm trùng header cùng tên | Chỉ ghi một header; định nghĩa chính sách khi nhận duplicate |
| Log injection hoặc field quá dài | Tin tưởng ID từ caller mà không validate | Giới hạn format/length và sanitize trước khi log |
| Batch log mang sai ID | Đặt MDC một lần cho toàn bộ batch | Tạo MDC scope riêng cho từng record |

## 21. Quy trình triển khai

1. Xác định correlation ID được tạo tại API gateway hay service ingress.
2. Thống nhất header name, encoding, format và giới hạn độ dài.
3. Phân biệt correlation ID với trace ID, request ID, event ID và Kafka key.
4. Thêm correlation header vào mọi producer path, kể cả retry, DLT và event forwarding.
5. Đọc header ở consumer bằng `ConsumerRecord` hoặc `@Header`.
6. Đưa ID vào MDC bằng scope `try/finally` hoặc `RecordInterceptor` có cleanup.
7. Cấu hình Logback/JSON encoder để xuất `correlationId` thành field riêng.
8. Nếu dùng async hoặc batch, truyền context riêng cho từng task/record.
9. Bật Micrometer Observation/Tracing nếu cần distributed trace; giữ correlation ID nghiệp vụ riêng.
10. Không dùng correlation ID làm metric tag và không log dữ liệu nhạy cảm.
11. Kiểm thử thành công, exception, retry, DLT, forwarding, batch và thread reuse.
12. Tạo dashboard/log query để tra cứu toàn bộ log theo correlation ID.

## 22. Tổng kết

- Correlation ID giúp nhóm log của cùng một luồng nghiệp vụ qua nhiều service và topic.
- Với event flow thông thường, có thể dùng custom Kafka header `x-correlation-id`; `KafkaHeaders.CORRELATION_ID` mặc định phục vụ request-reply.
- Kafka header là byte array; dùng UTF-8 nhất quán và tránh header trùng tên.
- Đọc correlation ID từ `ConsumerRecord` hoặc `@Header`, sau đó đặt vào MDC để log ở các component đồng bộ cùng thread tự mang ID.
- Consumer thread được tái sử dụng nên phải khôi phục/xóa MDC sau mỗi record; `RecordInterceptor.afterRecord()` có từ Spring Kafka 2.8.
- MDC không tự truyền sang executor hoặc async task; phải propagate context rõ ràng.
- Giữ correlation ID qua retry, DLT và event forwarding; giữ event ID riêng để idempotency.
- Micrometer Observation/Tracing hỗ trợ distributed tracing; trace ID và correlation ID phục vụ mục đích khác nhau.
- Không đưa correlation ID vào metric tag vì cardinality cao; hãy dùng log và trace.
- Validate ID đầu vào, tránh PII, secret và log injection.

Khi correlation ID được truyền nhất quán trong Kafka headers và được đưa vào MDC đúng vòng đời, log từ nhiều service có thể được truy vấn như một luồng nghiệp vụ xuyên suốt. Điều này giúp điều tra lỗi, retry và sự kiện đến muộn nhanh hơn mà không làm lẫn correlation ID giữa các record chạy trên cùng consumer thread.

## Tài liệu tham khảo

- [Spring Kafka Reference — Message Listener Containers and RecordInterceptor](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring Kafka Reference — Sending Messages and Request/Reply Headers](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html)
- [Spring Kafka Reference — Micrometer Observation and Monitoring](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html)
- [Spring Kafka API — KafkaHeaders](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/support/KafkaHeaders.html)
- [Micrometer Tracing — Context Propagation](https://docs.micrometer.io/tracing/reference/configuring.html)
