# Header chứa correlation id

Correlation ID là mã định danh dùng để liên kết các thông điệp và thao tác thuộc cùng một request hoặc workflow xuyên qua nhiều service. Trong Kafka, có thể truyền mã này bằng record header để producer, consumer và các service downstream ghi log, truy vết và đối chiếu các bước xử lý mà không phải nhúng metadata vận hành vào payload nghiệp vụ.

Một correlation ID nên được tạo ở điểm tiếp nhận đầu tiên nếu request chưa có mã hợp lệ, sau đó được giữ nguyên khi event đi qua các topic và service. Mỗi event vẫn có `eventId` riêng; correlation ID chỉ nhóm các event cùng một luồng nghiệp vụ. Correlation ID cũng không đồng nghĩa với trace ID của distributed tracing.

## 1. Correlation ID giải quyết vấn đề gì?

Một workflow có thể đi qua nhiều service và nhiều topic:

```text
HTTP request
    |
    | correlation-id = c-7f91
    v
Order service
    |
    | orders.created
    v
Kafka
    |
    v
Inventory service
    |
    | inventory.reserved
    v
Kafka
    |
    v
Payment service
    |
    | payment.authorized
    v
Kafka
    |
    v
Notification service
```

Nếu mọi event trong workflow giữ cùng correlation ID `c-7f91`, operator có thể tìm log ở các service theo cùng một giá trị để dựng lại đường đi của request. Khi không có mã này, việc điều tra thường phải dựa vào timestamp, business key hoặc nội dung payload; những cách đó khó chính xác khi nhiều request chạy đồng thời.

Correlation ID hữu ích cho:

- Liên kết log giữa producer, consumer và downstream service.
- Theo dõi một workflow kéo dài qua nhiều topic.
- Đối chiếu request với event phát sinh từ request đó.
- Hỗ trợ điều tra retry, duplicate, timeout và DLT.
- Tìm các message liên quan khi một workflow thất bại một phần.

Correlation ID là metadata phục vụ quan sát và liên kết. Nó không tự bảo đảm message được xử lý đúng một lần, không thay thế idempotency key và không phải cơ chế xác thực.

## 2. Vì sao đặt correlation ID trong Kafka header?

Kafka record có key, value, timestamp và headers. Header là tập các cặp tên/giá trị, trong đó tên là chuỗi và value là byte array. Header phù hợp với metadata vận chuyển như correlation ID, trace context, source service hoặc schema-related metadata.

| Vị trí | Khi nào phù hợp |
| --- | --- |
| Kafka header | Metadata phục vụ tracing, logging, routing hoặc kỹ thuật vận chuyển |
| Payload | Dữ liệu nghiệp vụ mà consumer cần để hiểu event và thực hiện business logic |
| Kafka key | Định danh dùng cho partitioning, ordering theo key hoặc log compaction |

Ví dụ một record:

```text
topic: orders.created
key:   order-42
value: { "eventId": "evt-1001", "orderId": "order-42" }
header:
  correlation-id: "c-7f91"
```

Consumer không cần sửa schema payload chỉ để bổ sung một mã theo dõi. Tuy nhiên, nếu correlation ID có ý nghĩa nghiệp vụ mà consumer cần lưu bền vững hoặc hiển thị cho người dùng, hãy cân nhắc đưa nó vào payload theo event contract thay vì chỉ dựa vào header.

## 3. Phân biệt correlation ID, event ID, causation ID và trace ID

Các mã định danh này có phạm vi khác nhau:

| Identifier | Ý nghĩa | Vòng đời |
| --- | --- | --- |
| `correlation-id` | Nhóm các message thuộc cùng request/workflow | Thường được giữ nguyên qua nhiều service và topic |
| `eventId` | Định danh duy nhất của một event | Mỗi event mới có ID riêng |
| `causationId` | Chỉ event trực tiếp gây ra event hiện tại | Thay đổi theo quan hệ nhân quả |
| `traceId` | Định danh distributed trace gồm nhiều span | Do tracing system quản lý |
| `spanId` | Định danh một thao tác/span trong trace | Mỗi span có ID riêng |

Ví dụ request tạo đơn hàng có correlation ID `c-7f91`. Order service phát `OrderCreated` với `eventId=evt-1`. Inventory service nhận event đó và phát `InventoryReserved` với `eventId=evt-2`, `causationId=evt-1`; cả hai event vẫn có `correlation-id=c-7f91`.

Không dùng một event ID làm correlation ID cho toàn workflow nếu workflow phát sinh nhiều event. Cũng không tự tạo một trace ID mới cho mỗi message nếu tracing context cần tiếp tục qua ranh giới Kafka.

## 4. Quy ước tên header và encoding

Hãy chọn một tên header ổn định cho metadata correlation của hệ thống, ví dụ:

```text
correlation-id
```

Kafka header value là `byte[]`, vì vậy producer và consumer phải thống nhất encoding. UTF-8 là lựa chọn thông dụng cho UUID hoặc chuỗi định danh:

```java
byte[] value = correlationId.getBytes(StandardCharsets.UTF_8);
```

Khi đọc:

```java
String correlationId = new String(value, StandardCharsets.UTF_8);
```

Không dùng `new String(bytes)` mà bỏ qua charset mặc định của JVM; điều đó có thể khiến các service khác môi trường giải mã khác nhau.

Tên header Kafka phân biệt chữ hoa/chữ thường. Hãy thống nhất một cách viết và không để producer này gửi `Correlation-Id`, producer khác gửi `correlation-id` rồi consumer phải đoán nhiều biến thể.

## 5. Tạo correlation ID tại điểm tiếp nhận đầu tiên

Correlation ID thường được lấy từ request header của HTTP gateway hoặc được tạo khi hệ thống tiếp nhận một workflow mới. Nếu chấp nhận ID do caller gửi lên, cần kiểm tra định dạng và độ dài trước khi đưa vào Kafka/log.

Ví dụ utility:

```java
import java.util.UUID;
import java.util.regex.Pattern;

public final class CorrelationIds {

    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9._:-]{1,128}");

    private CorrelationIds() {
    }

    public static String resolveOrCreate(String supplied) {
        if (supplied == null || supplied.isBlank()) {
            return UUID.randomUUID().toString();
        }

        String candidate = supplied.trim();
        if (!SAFE_ID.matcher(candidate).matches()) {
            throw new IllegalArgumentException("Invalid correlation id");
        }

        return candidate;
    }
}
```

Pattern trên là quy ước minh họa; nếu hệ thống dùng ULID hoặc định dạng khác, hãy điều chỉnh allowlist và giới hạn độ dài. Không chấp nhận chuỗi tùy ý không giới hạn vì nó có thể làm phình header/log hoặc đưa ký tự điều khiển vào log.

Nếu request đến từ bên ngoài, correlation ID do caller cung cấp chỉ là metadata không đáng tin cậy. Có thể giữ ID hợp lệ để hỗ trợ liên kết request, nhưng không dùng nó để xác định danh tính, quyền truy cập hoặc quyết định nghiệp vụ nhạy cảm.

## 6. Gắn correlation ID vào ProducerRecord

Với `KafkaTemplate`, cách trực tiếp và rõ ràng là tạo `ProducerRecord`, thêm `RecordHeader`, rồi gửi record đó:

```java
import java.nio.charset.StandardCharsets;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.header.internals.RecordHeader;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private static final String CORRELATION_ID = "correlation-id";

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderCreatedEvent event, String correlationId) {
        ProducerRecord<String, OrderCreatedEvent> record =
                new ProducerRecord<>(
                        "orders.created",
                        event.orderId(),
                        event);

        record.headers().add(new RecordHeader(
                CORRELATION_ID,
                correlationId.getBytes(StandardCharsets.UTF_8)));

        kafkaTemplate.send(record);
    }
}
```

Ví dụ giả định `OrderCreatedEvent` có phương thức `orderId()`. Correlation ID nên được resolve/validate trước khi gọi publisher. `KafkaTemplate.send()` trả về future; nếu caller cần biết broker đã acknowledge hay chưa, hãy quan sát future/callback thay vì xem việc gọi method là bằng chứng gửi thành công.

Nếu dùng `Message<?>` và `KafkaTemplate.send(Message<?>)`, cần xác minh `KafkaHeaderMapper` đang map custom header sang Kafka record header theo đúng quy ước. Khi cần kiểm soát chính xác byte value và header names, `ProducerRecord` là cách minh bạch.

## 7. Đọc correlation ID trong ConsumerRecord

Listener có thể nhận `ConsumerRecord` để truy cập trực tiếp headers:

```java
import java.nio.charset.StandardCharsets;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    private static final String CORRELATION_ID = "correlation-id";

    @KafkaListener(topics = "orders.created", groupId = "inventory-service")
    public void onMessage(ConsumerRecord<String, OrderCreatedEvent> record) {
        Header header = record.headers().lastHeader(CORRELATION_ID);

        String correlationId = header == null || header.value() == null
                ? "missing"
                : new String(header.value(), StandardCharsets.UTF_8);

        // Gọi application service với correlationId đã được kiểm tra.
    }
}
```

`lastHeader(name)` trả về header cuối cùng có tên đó. Nếu header không tồn tại hoặc value là `null`, listener cần có chính sách rõ ràng: tạo fallback ID cho luồng legacy, đánh dấu metric thiếu header, hoặc từ chối/quarantine record nếu contract bắt buộc phải có. Không để `NullPointerException` xảy ra ngẫu nhiên trong business logic.

Sau khi đọc, hãy validate định dạng/độ dài trước khi đưa ID vào log hoặc gửi tiếp. Record đến từ Kafka có thể do producer khác tạo; không mặc định mọi header đều hợp lệ.

## 8. Giữ nguyên correlation ID khi phát event downstream

Khi consumer xử lý event và phát event tiếp theo, hãy truyền lại correlation ID của workflow. Không tạo UUID mới ở mỗi service, nếu không chuỗi liên kết sẽ bị đứt.

```java
@Component
public class OrderCreatedListener {

    private static final String CORRELATION_ID = "correlation-id";

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderCreatedListener(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(topics = "orders.created", groupId = "inventory-service")
    public void onMessage(ConsumerRecord<String, String> input) {
        String correlationId = readAndValidateCorrelationId(input);
        String result = "reserved:" + input.value();

        ProducerRecord<String, String> output = new ProducerRecord<>(
                "inventory.reserved",
                input.key(),
                result);

        output.headers().add(new RecordHeader(
                CORRELATION_ID,
                correlationId.getBytes(StandardCharsets.UTF_8)));

        kafkaTemplate.send(output);
    }

    private String readAndValidateCorrelationId(
            ConsumerRecord<String, String> record) {
        Header header = record.headers().lastHeader(CORRELATION_ID);
        if (header == null || header.value() == null) {
            throw new IllegalArgumentException("Missing correlation-id header");
        }

        String value = new String(header.value(), StandardCharsets.UTF_8);
        if (value.isBlank() || value.length() > 128) {
            throw new IllegalArgumentException("Invalid correlation-id header");
        }
        return value;
    }
}
```

Ví dụ minh họa việc truyền ID qua một hop; trong production nên tái sử dụng utility validate chung, xử lý exception theo error handler và không gửi output nếu input contract không hợp lệ. Nếu cần giữ các header khác, hãy copy có chọn lọc những header được phép thay vì vô tình làm mất metadata cần thiết hoặc chuyển tiếp header nội bộ không phù hợp.

## 9. Kafka cho phép nhiều header trùng tên

Kafka `Headers` cho phép nhiều header cùng tên. Ví dụ một record có thể chứa hai `correlation-id` do producer hoặc interceptor thêm lặp. Khi đọc bằng `lastHeader()`, consumer lấy giá trị cuối; các API `headers(name)` cho phép duyệt tất cả header cùng tên.

Hãy quy định chính sách:

- Mỗi record chỉ có một correlation ID canonical.
- Nếu nhận nhiều giá trị khác nhau, từ chối/quarantine hoặc áp dụng quy tắc rõ ràng; không để mỗi service chọn một giá trị khác nhau.
- Khi tạo record mới, có thể loại bỏ header cũ cùng tên rồi thêm một giá trị đã validate.
- Không nối nhiều correlation ID thành một chuỗi nếu không có contract cho quan hệ nhiều workflow.

Ví dụ chuẩn hóa header trước khi gửi:

```java
private static void replaceCorrelationId(Headers headers, String id) {
    headers.remove("correlation-id");
    headers.add(new RecordHeader(
            "correlation-id",
            id.getBytes(StandardCharsets.UTF_8)));
}
```

Chỉ dùng thao tác `remove()` khi producer thực sự muốn thay thế header canonical. Nếu record chứa nhiều metadata khác, không xóa toàn bộ headers.

## 10. Phân biệt correlation ID nghiệp vụ và Spring Kafka request/reply

Spring Kafka có header dành cho request/reply, gồm `KafkaHeaders.CORRELATION_ID`, `KafkaHeaders.REPLY_TOPIC` và `KafkaHeaders.REPLY_PARTITION`. `ReplyingKafkaTemplate` dùng correlation metadata để ghép reply với request đang chờ.

Đây là mục đích framework request/reply. Nếu ứng dụng dùng `ReplyingKafkaTemplate`, không tự ý ghi đè hoặc xóa correlation header mà template dùng để match response. Một correlation ID nghiệp vụ dùng xuyên workflow có thể được lưu bằng header riêng như `correlation-id` để tránh nhầm lẫn với cơ chế ghép request/reply.

| Header | Mục đích |
| --- | --- |
| `correlation-id` (custom) | Liên kết workflow/request trong hệ thống |
| `KafkaHeaders.CORRELATION_ID` | Metadata Spring Kafka dùng để tương quan request và reply |
| `KafkaHeaders.REPLY_TOPIC` | Topic mà responder gửi reply tới |
| `KafkaHeaders.REPLY_PARTITION` | Partition reply nếu được chỉ định |

Nếu dự án chủ động dùng `KafkaHeaders.CORRELATION_ID` làm correlation ID nghiệp vụ, cần thống nhất rõ cách quản lý với `ReplyingKafkaTemplate` và mọi producer/consumer tham gia.

## 11. Correlation ID không thay thế distributed tracing

Distributed tracing theo dõi request qua các span, ghi nhận quan hệ cha-con và thời gian thực thi. W3C Trace Context thường truyền các header `traceparent` và `tracestate`; baggage có thể truyền thêm context theo chính sách tracing.

Correlation ID thường là một mã workflow nghiệp vụ có thể tồn tại lâu hơn một trace. Ví dụ một đơn hàng có thể phát sinh event trong nhiều phút hoặc nhiều giờ, tạo nhiều trace khác nhau qua các consumer/retry; các event vẫn có thể giữ cùng correlation ID.

| Tiêu chí | Correlation ID | Trace ID |
| --- | --- | --- |
| Phạm vi | Request/workflow nghiệp vụ | Một distributed trace |
| Mục tiêu | Liên kết event/log theo workflow | Phân tích span, latency và dependency |
| Vòng đời | Có thể kéo dài qua nhiều trace | Theo lifecycle của trace context |
| Quản lý | Application contract | Tracing instrumentation/system |

Khi dùng Micrometer Tracing hoặc OpenTelemetry instrumentation tương thích, context propagation có thể tự inject/extract trace headers khi gửi/nhận Kafka. Không tự tạo `traceparent` thủ công nếu tracing layer đã quản lý context, vì có thể làm đứt parent-child relationship.

Một record có thể đồng thời mang `correlation-id` nghiệp vụ và trace context. Hai loại metadata bổ sung cho nhau.

## 12. Đưa correlation ID vào log bằng MDC

Mapped Diagnostic Context (MDC) giúp logger tự thêm correlation ID vào mọi log line trên thread hiện tại. Với listener, cần đặt và xóa MDC trong `try/finally` vì consumer thread được tái sử dụng cho nhiều record.

```java
@KafkaListener(topics = "orders.created", groupId = "inventory-service")
public void onMessage(ConsumerRecord<String, String> record) {
    String correlationId = readCorrelationId(record);
    String previous = MDC.get("correlationId");
    MDC.put("correlationId", correlationId);

    try {
        log.info("Processing order event, topic={}, partition={}, offset={}",
                record.topic(), record.partition(), record.offset());
        orderService.process(record.value());
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
```

Ví dụ giả định logger và `readCorrelationId()` đã được khai báo. Khôi phục giá trị MDC trước đó giúp tránh ghi đè context bên ngoài nếu listener được gọi trong một execution context có sẵn.

MDC thường dựa trên thread-local. Nếu listener chuyển công việc sang executor hoặc `@Async`, MDC không tự động truyền sang thread khác trong mọi cấu hình. Cần truyền correlation ID như tham số tường minh hoặc cấu hình context propagation phù hợp. Không dựa vào MDC như nơi lưu dữ liệu nghiệp vụ.

## 13. Dùng correlation ID trong retry và DLT

Correlation ID đặc biệt hữu ích khi record đi qua retry topic hoặc dead-letter topic. Hãy giữ correlation ID qua các lần retry để log của lần xử lý đầu, các lần retry và DLT vẫn thuộc cùng workflow.

Khi cấu hình error handler/recoverer:

- Xác minh header `correlation-id` được giữ lại khi publish retry/DLT.
- Nếu tạo record mới, copy correlation ID đã validate vào record đích.
- Giữ metadata gốc như topic, partition, offset và exception theo quy ước DLT.
- Không tạo correlation ID mới chỉ vì record được chuyển sang retry topic.
- Khi replay DLT, quyết định rõ giữ correlation ID cũ để tiếp tục điều tra hay tạo correlation ID mới cho một workflow replay riêng; nếu cần, lưu cả hai bằng `original-correlation-id` và `replay-correlation-id`.

Correlation ID hỗ trợ tìm kiếm log nhưng không tự deduplicate retry. Dùng event ID/idempotency key và transaction semantics phù hợp để kiểm soát side effect.

## 14. Correlation ID trong fan-out và workflow dài

Một event có thể tạo nhiều event downstream. Nếu tất cả cùng thuộc một request, có thể giữ cùng correlation ID:

```text
OrderCreated (corr=c-7f91, event=evt-1)
       |
       +----> InventoryCheck (corr=c-7f91, event=evt-2)
       |
       +----> FraudCheck     (corr=c-7f91, event=evt-3)
       |
       +----> CustomerNotify (corr=c-7f91, event=evt-4)
```

Mỗi event có `eventId` riêng và có thể có `causationId` riêng. Correlation ID chung giúp gom nhánh workflow; `causationId` giúp xác định event trực tiếp tạo ra một event khác.

Với workflow kéo dài nhiều ngày, cân nhắc phạm vi duy nhất của correlation ID và chính sách retention của log/observability backend. Tránh tái sử dụng một correlation ID cho các workflow độc lập.

## 15. Bảo mật và giới hạn của correlation header

Kafka header là dữ liệu của record. Nó được truyền cùng record và có thể được consumer đọc; không xem header là vùng bí mật.

Các nguyên tắc:

- Không đưa password, access token, session cookie hoặc private data vào correlation header.
- Giới hạn độ dài và ký tự hợp lệ.
- Không dùng correlation ID do caller cung cấp để xác thực hoặc phân quyền.
- Cẩn trọng khi log giá trị do bên ngoài cung cấp; loại bỏ ký tự điều khiển và log injection.
- Không dùng correlation ID làm metric label có cardinality cao; dùng log/trace cho lookup chi tiết và metric tổng hợp theo service/topic/result.
- Xác định retention và quyền truy cập log vì correlation ID có thể liên kết nhiều hoạt động của cùng một người dùng/workflow.

TLS bảo vệ header trên đường truyền, nhưng không biến header thành secret hoặc bảo đảm chỉ service tin cậy mới có thể tạo giá trị đó.

## 16. Kiểm thử correlation ID

Integration test nên kiểm tra cả việc gắn header ở producer và giữ nguyên qua consumer-forwarder:

1. Gửi record với correlation ID xác định.
2. Consume bằng test consumer và xác minh header bytes giải mã UTF-8 đúng giá trị.
3. Để listener phát output sang topic khác.
4. Consume output và xác minh correlation ID vẫn giữ nguyên.
5. Gửi record không có header và xác minh chính sách fallback/validation.
6. Gửi header rỗng, quá dài, sai ký tự hoặc trùng tên để kiểm tra xử lý.
7. Kiểm tra MDC được xóa/khôi phục sau khi listener hoàn tất hoặc ném exception.
8. Nếu dùng retry/DLT, xác minh correlation ID tồn tại trên record retry/DLT.

Ví dụ assertion:

```java
Header header = received.headers().lastHeader("correlation-id");

assertThat(header).isNotNull();
assertThat(new String(header.value(), StandardCharsets.UTF_8))
        .isEqualTo(expectedCorrelationId);
```

Không chỉ mock `KafkaTemplate` rồi xác minh method được gọi. Integration test với broker giúp xác minh header thực sự được serialize, lưu trên record và đọc lại đúng cách.

## 17. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Log service đầu có ID, service sau không có | Consumer không đọc hoặc producer downstream không copy header | Chuẩn hóa helper đọc/ghi và kiểm tra từng hop |
| Correlation ID thay đổi ở mỗi service | Mỗi consumer tự sinh UUID mới | Chỉ tạo ở ingress khi thiếu; các hop sau giữ nguyên |
| Header đọc ra ký tự lỗi | Producer/consumer dùng charset khác nhau | Quy định UTF-8 rõ ràng |
| Header có nhiều giá trị | Nhiều interceptor hoặc code path cùng add header | Quy định một giá trị canonical và xử lý duplicate |
| Log có correlation ID của message trước | MDC không được clear khi listener thread tái sử dụng | Dùng `try/finally` để restore/remove MDC |
| `ReplyingKafkaTemplate` không nhận đúng reply | Correlation header framework bị ghi đè hoặc loại bỏ | Giữ nguyên `KafkaHeaders.CORRELATION_ID` do request/reply flow quản lý |
| Trace không liên kết dù correlation ID giống nhau | Trace context `traceparent` không được propagate | Cấu hình tracing instrumentation; không nhầm trace ID với correlation ID |
| DLT không có correlation ID | Recoverer tạo record mới nhưng không copy custom header | Kiểm tra DLT recoverer/header mapper và test thực tế |
| Correlation ID gây log/metric phình lớn | Dùng ID làm metric tag hoặc nhận giá trị không giới hạn | Giới hạn độ dài; không dùng ID làm label cardinality cao |

## 18. Checklist triển khai

- [ ] Chọn tên header ổn định, ví dụ `correlation-id`.
- [ ] Dùng UTF-8 cho giá trị header.
- [ ] Tạo ID ở ingress khi request chưa có ID hợp lệ.
- [ ] Validate độ dài và ký tự của ID bên ngoài cung cấp.
- [ ] Giữ nguyên correlation ID qua các service/topic.
- [ ] Mỗi event có `eventId` riêng; dùng `causationId` nếu cần quan hệ nhân quả.
- [ ] Phân biệt correlation ID với trace ID và Spring request/reply correlation header.
- [ ] Copy header khi publish output, retry hoặc DLT.
- [ ] Đặt và dọn MDC trong `try/finally`.
- [ ] Không đưa secret/PII vào header.
- [ ] Không dùng correlation ID làm metric label có cardinality cao.
- [ ] Có integration test kiểm tra header qua nhiều hop.

## 19. Kết luận

Correlation ID trong Kafka header giúp liên kết các record thuộc cùng request hoặc workflow qua nhiều producer, consumer và topic. Hãy tạo ID ở điểm tiếp nhận đầu tiên nếu thiếu, validate giá trị, encode bằng UTF-8 và giữ nguyên khi phát event downstream. Mỗi event vẫn cần event ID riêng; causation ID mô tả quan hệ nhân quả, còn trace ID do distributed tracing quản lý.

Trong Spring Kafka, có thể thêm header bằng `ProducerRecord`/`RecordHeader` và đọc bằng `ConsumerRecord.headers()`. Nếu dùng `ReplyingKafkaTemplate`, tôn trọng `KafkaHeaders.CORRELATION_ID` dành cho request/reply; correlation nghiệp vụ có thể dùng header riêng. Kết hợp MDC để đưa ID vào log nhưng luôn dọn context trên consumer thread. Correlation ID hỗ trợ quan sát và điều tra, không thay thế idempotency, authorization hay distributed tracing.

## Tài liệu tham khảo

- [Apache Kafka — Record Headers API](https://kafka.apache.org/40/javadoc/org/apache/kafka/common/header/Headers.html)
- [Apache Kafka — ProducerRecord API](https://kafka.apache.org/40/javadoc/org/apache/kafka/clients/producer/ProducerRecord.html)
- [Spring for Apache Kafka — Message Headers](https://docs.spring.io/spring-kafka/reference/kafka/headers.html)
- [Spring for Apache Kafka — Request/Reply](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html#replying-template)
- [W3C — Trace Context](https://www.w3.org/TR/trace-context/)
