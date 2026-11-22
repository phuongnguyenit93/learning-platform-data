# Correlation ID trong header

## 1. Tại sao cần Correlation ID khi sử dụng Spring Kafka?

Trong kiến trúc event-driven, một yêu cầu nghiệp vụ thường đi qua nhiều service và nhiều Kafka topics. Ví dụ, khách hàng đặt hàng qua HTTP API; service tạo đơn publish `OrderCreated`, inventory service nhận rồi publish `StockReserved`, payment service tiếp tục publish `PaymentConfirmed`, và notification service cuối cùng gửi thông báo.

Mỗi service có logs, metrics và traces riêng. Khi một bước thất bại, người vận hành cần biết các log và event nào thực sự thuộc cùng một luồng nghiệp vụ. **Correlation ID** là định danh dùng để nối các bước liên quan đó.

Ví dụ:

~~~text
HTTP POST /orders
  correlationId: 5e85d52f-5a98-44f4-b29c-635a8994643f
       |
       v
orders.created
  header x-correlation-id = 5e85d52f-5a98-44f4-b29c-635a8994643f
       |
       v
Inventory listener
  log correlationId=5e85...
  publish stock.reserved cùng correlationId
       |
       v
Payment listener
  log correlationId=5e85...
  publish payment.confirmed cùng correlationId
       |
       v
Notification listener
  log correlationId=5e85...
~~~

**Correlation ID trong header** nghĩa là đưa ID vào phần metadata của Kafka record, chứ không bắt buộc đặt nó vào payload của từng business event.

Kafka không tự tạo và propagate một correlation ID nghiệp vụ cho mọi event. Ứng dụng phải có quy ước về tên header, encoding, điểm sinh ID, cách đọc, cách forward và cách xử lý khi header thiếu hoặc sai.

## 2. Kafka headers lưu dữ liệu như thế nào?

Kafka record gồm topic, partition, offset (sau khi ghi), key, value, timestamp và headers. Header là các cặp tên và **giá trị dạng byte[]**.

~~~text
ProducerRecord
  topic: orders.created
  key: order-42
  value: OrderCreated(...)
  headers:
    x-correlation-id: [UTF-8 bytes]
    x-event-id:       [UTF-8 bytes]
    traceparent:      [bytes do tracing instrumentation quản lý]
~~~

Kafka client cung cấp các API:

| API | Vai trò |
|---|---|
| `ProducerRecord.headers()` | Thêm/đọc headers trước khi publish |
| `ConsumerRecord.headers()` | Đọc headers của record nhận được |
| `Header.key()` | Tên header |
| `Header.value()` | Giá trị byte array |
| `Headers.lastHeader(name)` | Lấy header cuối cùng cùng tên |
| `Headers.headers(name)` | Lấy tất cả headers cùng tên |
| `RecordHeader` | Một implementation để tạo header |

Kafka có thể cho phép **nhiều header có cùng tên**. Vì vậy producer nên chuẩn hóa cách ghi để không tạo các `x-correlation-id` mâu thuẫn, còn consumer cần chọn rõ policy khi đọc duplicate headers.

Header không thuộc business payload schema. JSON message có thể là:

~~~json
{
  "eventId": "cb7fa3fa-bdfc-4dfa-8a24-121746bfd181",
  "orderId": "order-42",
  "amountCents": 99000
}
~~~

Trong khi Correlation ID riêng nằm ở Kafka header:

~~~text
x-correlation-id = 5e85d52f-5a98-44f4-b29c-635a8994643f
~~~

Tuy nhiên, một Kafka Streams/Connect pipeline, bridge hoặc custom republisher có thể **tạo ProducerRecord mới**. Không mặc định mọi thành phần trung gian luôn bảo toàn custom headers; phải kiểm tra propagation thực tế.

## 3. Phân biệt correlation ID, event ID, causation ID và trace ID

Các định danh có mục đích khác nhau:

| ID | Phạm vi | Mục đích |
|---|---|---|
| **Correlation ID** | Một workflow/request trải qua nhiều bước | Tập hợp log và events thuộc cùng luồng |
| **Event ID** | Một business event riêng biệt | Audit, inbox/idempotency, deduplication |
| **Causation ID** | Event/command trực tiếp dẫn đến event hiện tại | Tái dựng quan hệ nhân quả |
| **Trace ID** | Một distributed trace | Kết nối các spans trong hệ tracing |
| **Span ID** | Một operation trong distributed trace | Theo dõi từng khoảng xử lý |

Ví dụ:

~~~text
Workflow tạo đơn
  correlationId = C1

OrderCreated
  eventId = E1
  correlationId = C1

StockReserved
  eventId = E2
  correlationId = C1
  causationId = E1

PaymentConfirmed
  eventId = E3
  correlationId = C1
  causationId = E2
~~~

Ba sự kiện hợp lệ có **cùng correlation ID** nhưng ba event IDs khác nhau. Nếu dùng correlation ID làm khóa duy nhất của inbox table, listener có thể xử lý E1 rồi bỏ qua E2/E3 một cách sai lầm.

**Correlation ID không phải Kafka record key.** Kafka key có thể là `order-42` nhằm bảo đảm routing/ordering theo aggregate trong một topic; correlation ID có thể nối nhiều aggregates hoặc nhiều topics. Không thay Kafka key bằng correlation ID nếu nghiệp vụ cần partitioning theo order/account.

Trace ID cũng không bắt buộc trùng correlation ID. Một workflow có thể được replay sau nhiều ngày với trace mới nhưng vẫn giữ cùng business correlation ID.

## 4. Quy định một hợp đồng header rõ ràng

Nên thống nhất tên header giữa các dịch vụ:

~~~text
x-correlation-id
x-event-id
x-causation-id
~~~

Đây là **tên do ứng dụng lựa chọn**, không phải header bắt buộc của Kafka. Một contract production cần nêu:

1. Tên header chính xác, ví dụ `x-correlation-id`.
2. Encoding UTF-8, không dùng platform default charset.
3. Dạng dữ liệu: UUID canonical string hoặc định dạng opaque ID có giới hạn.
4. Độ dài tối đa và tập ký tự cho phép.
5. Entry point nào được quyền sinh ID mới.
6. Khi nào propagate ID cũ.
7. Policy thiếu header: tạo ID mới, cảnh báo hay reject.
8. Policy sai header/duplicate headers.
9. Propagation qua retries, DLT, outbox, bridges, fan-out và replay.
10. Cách ghi structured logs, traces và metrics.
11. Giới hạn bảo mật khi giá trị đến từ nguồn không tin cậy.

Một contract ví dụ:

~~~text
Name:           x-correlation-id
Encoding:       UTF-8
Format:         UUID dạng string
Max length:     128 bytes
Creation:       HTTP/API hoặc nguồn event mới tại entry boundary
Propagation:    giữ nguyên trên các downstream events cùng workflow
Missing:        cho phép fallback trong migration nhưng đo tỷ lệ missing
Invalid:        không đưa raw data vào log, xử lý theo policy
Security:       không phải authentication token
~~~

Nếu consumer ở nhiều ngôn ngữ (Java, Python, Go), nên kiểm tra cùng một record header raw bytes để chắc các bên decode giống nhau.

## 5. Khi nào tạo Correlation ID mới?

Chỉ nên tạo một ID mới khi thực sự bắt đầu **một luồng nghiệp vụ mới**. Ví dụ tại HTTP endpoint:

~~~text
External request
    |
    v
Validation/trust boundary
    |
    +-- Có correlation ID hợp lệ -> giữ hoặc map theo policy
    |
    +-- Không có -> sinh UUID
    |
    v
Business service
    |
    v
ProducerRecord có x-correlation-id
~~~

Khi Kafka consumer đọc một record thuộc flow C1 và sinh downstream event, nó nên giữ C1. Nếu mọi consumer tự tạo UUID mỗi lần nhận record, traceability sẽ bị đứt ở từng hop.

### 5.1. Correlation ID từ HTTP client có đáng tin?

Không mặc định. Header do external client gửi có thể là chuỗi quá dài, chứa newline, payload nhạy cảm hoặc một ID được cố ý dùng lại để trộn logs của nhiều request.

Có thể lựa chọn:

- Chỉ chấp nhận UUID canonical string có giới hạn độ dài.
- Tạo ID nội bộ mới và lưu external request ID ở field khác.
- Nếu business contract bắt buộc giữ external ID, dùng validation và tách rõ trust boundary.

Correlation ID không có giá trị xác minh quyền truy cập. Không dùng ID này để chọn tenant hay bỏ qua kiểm tra authorization.

### 5.2. Legacy record thiếu header

Một consumer cũ có thể đã ghi records không có `x-correlation-id`. Có hai policy:

- **Compatibility:** ở lần xử lý đầu tiên sau khi phát hiện thiếu, tạo C2 để theo dõi các bước từ thời điểm đó; ghi log/metric missing correlation và propagate C2 về sau.
- **Strict contract:** coi thiếu header là lỗi dữ liệu; đưa record qua recovery/DLT phù hợp nếu không thể tiếp tục.

Không nên tạo ID mới mà không ghi nhận, vì điều đó che khuất việc upstream đang phá contract.

## 6. Gửi Correlation ID với KafkaTemplate và ProducerRecord

Cách minh bạch là tạo `ProducerRecord` rồi thêm `RecordHeader`:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CompletableFuture;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.header.internals.RecordHeader;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OrderPublisher {

    public static final String CORRELATION_HEADER =
        "x-correlation-id";

    private final KafkaTemplate<String, OrderCreated> template;

    public OrderPublisher(
        KafkaTemplate<String, OrderCreated> template
    ) {
        this.template = template;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
        OrderCreated event,
        String correlationId
    ) {
        ProducerRecord<String, OrderCreated> record =
            new ProducerRecord<>(
                "orders.created",
                event.orderId(),
                event
            );

        record.headers().add(
            new RecordHeader(
                CORRELATION_HEADER,
                correlationId.getBytes(StandardCharsets.UTF_8)
            )
        );

        record.headers().add(
            new RecordHeader(
                "x-event-id",
                event.eventId().toString()
                    .getBytes(StandardCharsets.UTF_8)
            )
        );

        return template.send(record);
    }
}
~~~

Đoạn ví dụ giả định `OrderCreated` có `orderId()` và `eventId()`; dự án cần Kafka serializers thực tế.

Trong Spring Kafka 3.x, `KafkaTemplate.send(ProducerRecord)` trả về `CompletableFuture<SendResult<...>>`. Các phiên bản cũ có thể có kiểu future khác. Không dùng snippet Java mà không khớp dependency version.

### 6.1. Send thành công chưa chắc transaction commit

Nếu producer chạy trong Kafka transaction, future gửi record thành công **không** chứng minh transaction cuối cùng đã commit. Transaction vẫn có thể abort do exception, timeout hoặc fencing.

Correlation ID giúp liên kết producer/transaction logs với downstream events, nhưng không thay thế Kafka transaction, idempotent producer hay retry policy.

### 6.2. Giữ kích thước header hợp lý

Header bytes làm tăng kích thước Kafka record. Không gửi nguyên cả HTTP headers, JSON request hay một trace object lớn vào `x-correlation-id`. Một UUID string chỉ vài chục bytes thường đủ cho mục tiêu correlation.

## 7. Đọc Correlation ID từ ConsumerRecord

Một record listener có thể nhận `ConsumerRecord` để truy cập raw Kafka headers:

~~~java
import java.nio.charset.StandardCharsets;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class InventoryConsumer {

    @KafkaListener(
        topics = "orders.created",
        groupId = "inventory-service"
    )
    public void onOrder(
        ConsumerRecord<String, OrderCreated> record
    ) {
        Header header =
            record.headers().lastHeader("x-correlation-id");

        String correlationId =
            header == null || header.value() == null
                ? null
                : new String(
                    header.value(),
                    StandardCharsets.UTF_8
                );

        inventoryService.reserve(
            record.value(),
            correlationId
        );
    }
}
~~~

Đây là cách đọc cơ bản. Trong production, cần validate bytes và format trước khi sử dụng. Không được đưa raw header không kiểm soát vào structured logs.

### 7.1. @Header thay cho ConsumerRecord

Spring Kafka cũng hỗ trợ binding header vào listener parameter thông qua Spring Messaging:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "inventory-service"
)
public void onOrder(
    OrderCreated event,
    @Header(
        name = "x-correlation-id",
        required = false
    ) byte[] correlationBytes
) {
    String correlationId = correlationBytes == null
        ? null
        : new String(
            correlationBytes,
            StandardCharsets.UTF_8
        );

    inventoryService.reserve(event, correlationId);
}
~~~

Kiểu giá trị bind được và converter phụ thuộc header mapper/message converter của endpoint. Khi cần byte[] gốc và kiểm soát duplicate header names, `ConsumerRecord.headers()` là cách ít phụ thuộc mapping hơn.

## 8. Helper dùng chung để encode và decode headers

Khi nhiều producer/consumer cùng sử dụng một contract, nên đặt logic vào một helper để tránh mỗi nơi chọn encoding và validation khác nhau.

~~~java
import java.nio.charset.StandardCharsets;
import java.util.regex.Pattern;

import org.apache.kafka.common.header.Header;
import org.apache.kafka.common.header.Headers;
import org.apache.kafka.common.header.internals.RecordHeader;

public final class CorrelationHeaders {

    public static final String NAME = "x-correlation-id";

    private static final int MAX_BYTES = 128;

    private static final Pattern SAFE_ID = Pattern.compile(
        "[A-Za-z0-9][A-Za-z0-9._:-]{0,127}"
    );

    private CorrelationHeaders() {
    }

    public static void put(Headers headers, String id) {
        validate(id);

        // Không để lại nhiều values cùng tên khi republish.
        headers.remove(NAME);
        headers.add(new RecordHeader(
            NAME,
            id.getBytes(StandardCharsets.UTF_8)
        ));
    }

    public static String read(Headers headers) {
        Header header = headers.lastHeader(NAME);

        if (header == null || header.value() == null) {
            return null;
        }

        byte[] bytes = header.value();

        if (bytes.length == 0 || bytes.length > MAX_BYTES) {
            throw new IllegalArgumentException(
                "Invalid correlation header length"
            );
        }

        String id = new String(bytes, StandardCharsets.UTF_8);
        validate(id);
        return id;
    }

    public static void validate(String id) {
        if (id == null || !SAFE_ID.matcher(id).matches()) {
            throw new IllegalArgumentException(
                "Invalid correlation ID format"
            );
        }

        if (id.getBytes(StandardCharsets.UTF_8).length > MAX_BYTES) {
            throw new IllegalArgumentException(
                "Correlation ID exceeds byte limit"
            );
        }
    }
}
~~~

Regex trên minh họa một format có giới hạn, không phải chuẩn Kafka. Nếu hợp đồng chỉ cho UUID, có thể validate canonical UUID string nghiêm ngặt hơn.

### 8.1. Header trùng tên

Kafka cho phép nhiều headers cùng tên. `lastHeader` lấy value cuối, nhưng nếu một record đến từ untrusted source có hai correlation IDs khác nhau, consumer nên có policy rõ ràng:

- Reject/đưa DLT nếu có nhiều giá trị mâu thuẫn.
- Chấp nhận last value và ghi metric duplicate headers.
- Chỉ accept một giá trị nếu integration contract quy định duy nhất.

Helper `put()` đã `remove(NAME)` trước khi thêm để tránh tạo duplicate ở phía producer. Reader cần tùy yêu cầu bổ sung logic kiểm tra `headers.headers(NAME)`.

### 8.2. Encoding không hợp lệ

`new String(bytes, UTF_8)` có thể thay thế malformed bytes bằng replacement character. Nếu yêu cầu strict UTF-8, dùng `CharsetDecoder` cấu hình `CodingErrorAction.REPORT`. Không nên tự sửa một correlation ID sai encoding vì điều đó có thể tạo ID khác với upstream.

### 8.3. Lỗi header không được retry vô hạn

Nếu ID sai format là lỗi vĩnh viễn, retry cùng record hàng nghìn lần không làm nó hợp lệ. Nên phân loại exception và đưa vào recovery/DLT hoặc fallback có đánh dấu theo chính sách migration.

## 9. Truyền ID qua luồng consume–process–produce

Mẫu phổ biến là nhận ID từ input rồi truyền tường minh sang producer output:

~~~mermaid
flowchart LR
    A[orders.created] -->|C1| B[Inventory Consumer]
    B --> C[Reserve Inventory]
    C --> D[stock.reserved]
    D -->|C1| E[Payment Consumer]
    E --> F[payment.confirmed]
~~~

Ví dụ:

~~~java
@Component
public class StockConsumer {

    private final StockService stockService;
    private final StockPublisher publisher;

    public StockConsumer(
        StockService stockService,
        StockPublisher publisher
    ) {
        this.stockService = stockService;
        this.publisher = publisher;
    }

    @KafkaListener(
        topics = "orders.created",
        groupId = "inventory-service"
    )
    public void onOrder(
        ConsumerRecord<String, OrderCreated> record
    ) {
        String correlationId =
            CorrelationHeaders.read(record.headers());

        if (correlationId == null) {
            // Fallback cho legacy data, không nên im lặng.
            correlationId = UUID.randomUUID().toString();
        }

        StockReserved output =
            stockService.reserveIdempotently(record.value());

        publisher.publish(output, correlationId);
    }
}
~~~

Các domain classes, logger và imports liên quan phải được cung cấp bởi project. `StockPublisher.publish` cần add `x-correlation-id` vào output record theo cùng helper.

**Lưu ý về reliability:** nếu service vừa ghi database vừa gửi Kafka output, hai side effects không tự commit nguyên tử vì có correlation ID. Cần inbox/outbox, transaction hoặc thiết kế consistency phù hợp.

### 9.1. Fan-out giữ cùng correlation ID

Một event E1 có thể tạo E2 và E3:

~~~text
Input E1 / correlation C1
    |
    +--- Output E2 / correlation C1 / causation E1
    |
    +--- Output E3 / correlation C1 / causation E1
~~~

Các output event IDs khác nhau nhưng vẫn thuộc business flow C1.

### 9.2. Fan-in từ nhiều correlation IDs

Nếu batch aggregate nhận dữ liệu từ C1 và C2 rồi tạo một report mới, không phải lúc nào cũng có một correlation ID cũ duy nhất thích hợp.

~~~text
Input A / correlation C1
Input B / correlation C2
           |
           v
     Aggregate report
           |
           v
     New workflow correlation C3
     Provenance: parents C1, C2
~~~

Có thể dùng một ID mới cho report và lưu parent IDs trong audit/provenance. Không tùy tiện chọn C1 rồi bỏ mất quan hệ với C2.

## 10. Đưa correlation ID vào log bằng MDC

MDC (Mapped Diagnostic Context) của SLF4J giúp log trong cùng thread mang thêm metadata mà không phải truyền ID vào từng câu log.

~~~java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.MDC;
import org.springframework.kafka.annotation.KafkaListener;

@KafkaListener(
    topics = "orders.created",
    groupId = "inventory-service"
)
public void onOrder(
    ConsumerRecord<String, OrderCreated> record
) {
    String correlationId =
        CorrelationHeaders.read(record.headers());

    if (correlationId == null) {
        correlationId = "missing";
    }

    try (MDC.MDCCloseable ignored =
             MDC.putCloseable("correlationId", correlationId)) {

        log.info(
            "Processing order, topic={}, partition={}, offset={}",
            record.topic(),
            record.partition(),
            record.offset()
        );

        inventoryService.reserveIdempotently(record.value());

        log.info("Order processed");
    }
}
~~~

Biến `log` là logger SLF4J của class. `MDC.putCloseable` giúp cleanup sau callback kể cả khi service ném exception.

Với Logback, pattern có thể là:

~~~xml
<pattern>
  %d{ISO8601} %-5level [%thread]
  trace=%X{traceId} correlation=%X{correlationId}
  %logger - %msg%n
</pattern>
~~~

Hoặc cấu hình JSON logger để xuất field `correlationId`. Dùng một tên field thống nhất trên các services để tìm log xuyên JVM.

### 10.1. Vì sao phải cleanup MDC?

Spring Kafka consumer threads được tái sử dụng cho nhiều records. Nếu listener đặt `MDC.put("correlationId", "C1")` nhưng không remove, record tiếp theo có thể log với C1 dù thuộc workflow C2.

Bởi vậy dùng `try/finally` hoặc `MDC.MDCCloseable`. Không để context của một record rò sang record kế tiếp.

### 10.2. Log trong error handler có còn MDC không?

Nếu listener ném exception, try-with-resources đã cleanup MDC khi exception rời listener. Error handler/container có thể ghi log **sau đó**, nên log này không được bảo đảm mang C1 từ MDC của listener.

Muốn error handler/recoverer logs có correlation ID, đọc ID từ `ConsumerRecord.headers()` trong recovery path hoặc dùng một interceptor/context lifecycle được thiết kế phù hợp. Không cố giữ MDC vô hạn ở consumer thread.

## 11. Bất đồng bộ: MDC không tự chạy qua thread mới

Một lỗi hay gặp:

~~~java
@KafkaListener(topics = "orders.created")
public void onOrder(ConsumerRecord<String, OrderCreated> record) {
    String id = CorrelationHeaders.read(record.headers());
    MDC.put("correlationId", id);

    CompletableFuture.runAsync(() -> {
        // Worker thread có thể không có MDC correlationId.
        log.info("Async stock processing");
    });

    MDC.remove("correlationId");
}
~~~

MDC thường thread-local. Cách đơn giản và rõ ràng là truyền ID thành tham số rồi đặt MDC trong worker:

~~~java
public CompletableFuture<Void> processAsync(
    OrderCreated event,
    String correlationId,
    Executor executor
) {
    return CompletableFuture.runAsync(() -> {
        try (MDC.MDCCloseable ignored =
                 MDC.putCloseable("correlationId", correlationId)) {
            stockService.reserveIdempotently(event);
        }
    }, executor);
}
~~~

Trong hệ thống dùng Micrometer Context Propagation, có thể dùng cơ chế chụp và khôi phục context phù hợp với executor; vẫn cần kiểm tra context có được propagate thực tế không.

**Lưu ý:** đúng MDC chưa bảo đảm đúng Kafka offset. Nếu listener trả về khi task còn chạy và container commit theo listener return, process crash có thể làm mất side effect. Cần hỗ trợ acknowledgment bất đồng bộ đúng version hoặc chuyển task vào durable queue/inbox trước khi hoàn tất listener.

## 12. Batch listener và correlation ID

Một lần batch callback có thể chứa nhiều records thuộc nhiều workflows:

~~~text
Record A -> correlation C1
Record B -> correlation C2
Record C -> correlation C1
Record D -> correlation C3
~~~

Không lấy correlation ID của record đầu rồi dùng cho cả batch. Nếu xử lý tuần tự:

~~~java
@KafkaListener(
    topics = "orders.created",
    containerFactory = "batchListenerFactory"
)
public void onBatch(
    List<ConsumerRecord<String, OrderCreated>> records
) {
    for (ConsumerRecord<String, OrderCreated> record : records) {
        String correlationId =
            CorrelationHeaders.read(record.headers());

        try (MDC.MDCCloseable ignored =
                 MDC.putCloseable(
                     "correlationId",
                     correlationId == null ? "missing" : correlationId
                 )) {

            stockService.reserveIdempotently(record.value());
        }
    }
}
~~~

Nếu batch processing có một database transaction chung, có thể thêm một `batchId` để liên kết logs của lần xử lý batch, trong khi vẫn giữ correlation ID riêng cho mỗi record.

Nếu một record gây lỗi giữa batch, offset commit và retry cần được xử lý theo cơ chế batch listener, ví dụ `DefaultErrorHandler`/`BatchListenerFailedException` khi phù hợp. Correlation ID chỉ giúp điều tra record lỗi; nó không tự giải quyết partial commit.

## 13. RecordInterceptor và xử lý context tập trung

Trong Spring Kafka, `RecordInterceptor` có thể quan sát record trước listener. Điều này hữu ích khi nhiều listener cần logic giống nhau:

~~~java
public class CorrelationLoggingInterceptor<K, V>
        implements RecordInterceptor<K, V> {

    @Override
    public ConsumerRecord<K, V> intercept(
        ConsumerRecord<K, V> record,
        Consumer<K, V> consumer
    ) {
        String correlationId =
            CorrelationHeaders.read(record.headers());

        log.debug(
            "Received record correlation={}, topic={}, partition={}, offset={}",
            correlationId,
            record.topic(),
            record.partition(),
            record.offset()
        );

        return record;
    }
}
~~~

Ví dụ cần imports `RecordInterceptor`, `ConsumerRecord`, `Consumer` và logger. Đây chỉ là interceptor ghi log. Nếu muốn đặt MDC ở interceptor, phải dùng thêm các lifecycle callbacks tương ứng (`success`, `failure`, `afterRecord` tùy Spring Kafka version) và bảo đảm cleanup chính xác.

Không chỉ gọi `MDC.put()` trong `intercept()` mà không có cleanup. Với concurrent listener và retry/error path, điều đó có thể làm correlation ID bị rò hoặc gắn sai record.

## 14. Correlation ID và distributed tracing khác nhau thế nào?

Một ID giúp tìm logs, nhưng **distributed tracing** còn lưu timing, parent/child spans, sampling và trace propagation qua service boundary.

Trong Spring Boot hiện đại, các thành phần thường dùng là Micrometer Observation, Micrometer Tracing và OpenTelemetry hoặc tracer bridge phù hợp.

~~~mermaid
flowchart LR
    A[HTTP API span] --> B[Kafka producer span]
    B --> C[Kafka consumer span]
    C --> D[Database span]
    C --> E[Kafka producer span]
    E --> F[Downstream consumer span]
~~~

Tracing context có thể đi qua Kafka headers theo chuẩn như W3C `traceparent`. Không tự ghi đè `traceparent` bằng một business ID tùy ý:

~~~text
Không hợp lệ:
  traceparent = order-42
~~~

Nếu cần business correlation ID, dùng custom `x-correlation-id` độc lập. Trace ID có thể thay đổi khi hệ thống replay workflow, còn business correlation ID vẫn được giữ để phục vụ audit và support.

### 14.1. Vì sao logs cần cả traceId lẫn correlationId?

- `traceId` dẫn đến trace của một lần execution cụ thể.
- `correlationId` liên kết nhiều executions hoặc business events thuộc cùng workflow.
- `eventId` giúp nhận ra một event bị replay/retry.
- Topic/partition/offset giúp tìm Kafka record cụ thể.

Một structured log có thể chứa đủ cả bốn loại thông tin, nhưng chỉ khi mỗi loại có semantics rõ ràng.

## 15. Spring Kafka Observation

Spring Kafka 3.x có thể tích hợp Micrometer Observation cho KafkaTemplate và listener container khi cấu hình đúng registry và instrumentation dependencies.

Ví dụ producer template:

~~~java
@Bean
public KafkaTemplate<String, OrderCreated> observedTemplate(
    ProducerFactory<String, OrderCreated> factory
) {
    KafkaTemplate<String, OrderCreated> template =
        new KafkaTemplate<>(factory);

    template.setObservationEnabled(true);
    return template;
}
~~~

Ví dụ container factory:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        observedListenerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory
        ) {
    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
        .setObservationEnabled(true);

    return factory;
}
~~~

Cần cấu hình `ObservationRegistry`, tracing bridge/exporter và listener factory wiring phù hợp với Spring Boot/Spring Kafka version thực tế. Một số cấu hình có thể đã được Boot tự động hóa, nhưng không mặc định mọi phiên bản đều có cùng property names.

**Bật Observation không đồng nghĩa framework tự sinh business `x-correlation-id`.** Tracing context và correlation header là hai phần tích hợp khác nhau cần được kiểm thử độc lập.

### 15.1. Test tracing propagation

Một integration test nên xác nhận producer thực sự ghi tracing headers, consumer nhận context và logs có traceId/spanId, đồng thời custom C1 vẫn được giữ qua các downstream events. Đừng chỉ kiểm tra trace exporter có kết nối rồi coi messaging propagation đã hoàn tất.

## 16. Đừng ghi đè KafkaHeaders.CORRELATION_ID của request/reply

Spring Kafka có `ReplyingKafkaTemplate` cho Kafka request/reply. Framework dùng một correlation token, thường được truy cập bằng `KafkaHeaders.CORRELATION_ID`, để biết reply tương ứng request đang chờ nào.

Token đó **không nhất thiết là business correlation ID**.

~~~text
Business workflow:
  x-correlation-id = C1

Kafka request/reply A:
  framework correlation token = T1

Kafka request/reply B:
  framework correlation token = T2

Hai requests A và B có thể cùng C1 nhưng cần T1/T2 khác nhau
để ReplyingKafkaTemplate match reply chính xác.
~~~

Không dùng `x-correlation-id` thay thế request/reply correlation token, và không tự ghi đè `KafkaHeaders.CORRELATION_ID` bằng C1 khi framework đang quản lý field đó.

Nếu application tự tạo reply ProducerRecord, cần preserve những reply headers mà request/reply protocol đòi hỏi (ví dụ reply topic/partition và token), đồng thời copy custom business correlation ID nếu cần.

## 17. Correlation ID khi blocking retry

Với Spring Kafka `DefaultErrorHandler`, listener có thể thử lại cùng record sau khi gặp lỗi transient.

~~~text
orders.created, partition 1, offset 220
  x-correlation-id = C1

Attempt 1 -> database timeout
Attempt 2 -> database timeout
Attempt 3 -> success
~~~

Mọi attempt thuộc cùng business event nên dùng C1. Không sinh C2/C3 chỉ vì listener đang retry.

Nếu record được redeliver, header của original record vẫn là nguồn metadata để log. Cần bảo đảm error handler/recoverer có thể đọc header khi MDC listener đã được cleanup.

Log mong muốn:

~~~text
correlation=C1 event=E1 attempt=1 failed
correlation=C1 event=E1 attempt=2 failed
correlation=C1 event=E1 attempt=3 completed
~~~

Kafka headers không thay thế metadata retry; nên giữ attempt index, exception category và timing riêng khi cần.

## 18. Correlation ID qua retry topics và DLT

Với non-blocking retry topic của record listener, failed record được publish sang retry topic và tiêu thụ sau khoảng chờ. Nếu hết lượt, record có thể chuyển DLT.

~~~text
orders.created
  x-correlation-id = C1
       |
       v
orders.created-retry-...
  x-correlation-id = C1
       |
       v
orders.created-dlt
  x-correlation-id = C1
~~~

Đây là **hành vi mong muốn của propagation contract**. Kafka retry infrastructure có thể copy original headers và bổ sung metadata, nhưng custom producer, recoverer, message converter hoặc bridge có thể thay đổi headers.

Nên kiểm thử thật rằng:

1. Input record có C1.
2. Retry record vẫn có C1.
3. DLT record vẫn có C1.
4. Event ID vẫn đại diện cho same business event.
5. Retry topic có thể có topic/partition/offset mới, nên không dùng chúng thay cho event identity.
6. Log recovery có topic nguồn, offset nguồn và correlation ID.
7. DLT replay giữ C1 theo policy và có replay attempt identity riêng nếu cần.

Non-blocking retry của Spring Kafka có giới hạn kết hợp listener modes; đặc biệt không coi `@RetryableTopic` là tính năng hỗ trợ trực tiếp batch listener.

### 18.1. DeadLetterPublishingRecoverer

`DeadLetterPublishingRecoverer` có thể chuyển record lỗi sang DLT, bổ sung các thông tin nguồn và exception. Không mặc định mọi custom header luôn được giữ nguyên nếu có cấu hình custom header mapping hoặc record creator.

Nếu incident không tìm thấy C1 ở DLT, kiểm tra recoverer/template trước khi kết luận producer gốc không có ID.

## 19. Correlation ID, Kafka transaction và Idempotency

Correlation ID là metadata. Nó **không** bảo đảm:

- Exactly-once processing.
- Atomic commit của các records.
- Ordering xuyên Kafka topics.
- Consumer group offset commit thành công.
- Database transaction commit.
- Không duplicate side effect.
- Mọi record cùng ID nằm trong cùng Kafka transaction.

Ví dụ hai Kafka transactions:

~~~text
Transaction T1:
  E2 StockReserved, correlation C1
  E3 StockAudit, correlation C1

Transaction T2:
  E4 PaymentConfirmed, correlation C1
~~~

Cùng C1 nhưng T1 và T2 vẫn là hai transactions khác nhau.

Nếu producer/consumer retry làm E2 được giao lại, cần `eventId=E2` và inbox/unique constraint để chống duplicate. Không sử dụng C1 làm inbox unique key nếu có nhiều events E1, E2, E3 thuộc workflow đó.

## 20. Inbox và Outbox phải lưu ID đúng cách

### 20.1. Inbox

Với Kafka → database:

~~~text
Consumer nhận E1, C1
  |
  v
Database transaction
  INSERT inbox(event_id=E1)
  UPDATE business tables
  COMMIT
~~~

Inbox nên unique theo event ID hoặc business operation ID thích hợp, không phải correlation ID. Nếu C1 được dùng làm unique key, các events khác nhau của cùng workflow có thể bị bỏ qua.

### 20.2. Outbox

Khi business service ghi outbox row để Kafka publisher phát event sau database commit, correlation ID cần được lưu **bền vững** trong outbox:

~~~text
outbox_row:
  event_id       = E2
  aggregate_id   = order-42
  event_type     = StockReserved
  correlation_id = C1
  payload        = ...
~~~

Publisher chạy ở thread/process khác sẽ đọc C1 từ row rồi add vào Kafka header. Không lấy ID chỉ từ MDC của HTTP thread lúc tạo đơn: thread context không tồn tại xuyên job boundary.

### 20.3. Crash window

Nếu database commit thành công nhưng Kafka publish/offset commit chưa hoàn tất, Kafka record có thể được gửi lại. Correlation ID giúp trace các lần thử nhưng không tự loại bỏ duplicate. Cần outbox publisher idempotency và consumer inbox/unique constraint phù hợp.

## 21. HTTP ↔ Kafka boundary

### 21.1. HTTP → Kafka

~~~text
HTTP request
  X-Correlation-ID: C1
        |
        v
HTTP filter/controller
  validate hoặc sinh C1
        |
        v
Business service truyền C1
        |
        v
Kafka ProducerRecord
  x-correlation-id: C1
~~~

Nếu event được publish ngay trong HTTP thread, có thể log C1 qua MDC. Nếu publish bằng outbox/job khác, phải lưu C1 trong dữ liệu bền vững để publisher lấy lại.

### 21.2. Kafka → HTTP

~~~text
Kafka input record header x-correlation-id=C1
        |
        v
Listener/business service
        |
        v
External HTTP request
  X-Correlation-ID: C1, nếu external API contract cho phép
~~~

External API có thể cấp request ID riêng. Khi đó lưu mapping giữa C1 nội bộ và external request ID thay vì thay ID tùy tiện.

Với external service, kiểm tra PII/trust policy trước khi forward bất cứ header nào.

## 22. Bảo mật: không tin correlation header một cách mù quáng

Một correlation header có thể được tự do tạo bởi producer có quyền ghi topic hoặc client phía ngoài tại entry boundary.

Các biện pháp:

- Validate format, ký tự, byte length.
- Loại bỏ newline/control characters để hạn chế log injection.
- Không dùng email/phone/token/session cookie làm ID.
- Không dùng correlation ID làm authentication token.
- Không cấp quyền tenant dựa trên header này.
- Không log toàn bộ header collection nếu có thông tin nhạy cảm khác.
- Bảo vệ quyền truy cập log, traces và DLT.
- Tách external ID khỏi internal ID nếu trust boundary yêu cầu.
- Có policy duplicate header names.
- Không tự tạo correlation string từ toàn bộ payload.

Một UUID opaque có thể không chứa thông tin cá nhân trực tiếp, nhưng khi tra cứu được vào hồ sơ order/payment qua logs, nó vẫn cần được bảo vệ theo chính sách dữ liệu của hệ thống.

## 23. Metrics và structured logs

Những metrics nên theo dõi:

| Metric | Công dụng |
|---|---|
| Missing correlation header count | Phát hiện producer/bridge không tuân thủ contract |
| Invalid correlation header count | Phát hiện sai encoding/format/length |
| Duplicate correlation header count | Phát hiện ambiguity |
| Producer propagation success | Đo tỷ lệ output có header hợp lệ |
| Retry/DLT propagation coverage | Bảo đảm khả năng truy vết lỗi |
| Listener processing duration | Phát hiện bước chậm |
| Consumer lag | Theo dõi backlog |
| DLT count | Đo lỗi không xử lý được |
| Trace sampling/export errors | Phát hiện mất thông tin tracing |

Đừng đưa correlation ID thành **Prometheus label**. Mỗi workflow có một ID, cardinality tăng rất nhanh. Labels nên gồm service, topic, consumer group và trạng thái header như `present`, `missing`, `invalid`.

Một log JSON mẫu:

~~~json
{
  "service": "inventory-service",
  "groupId": "inventory-service",
  "topic": "orders.created",
  "partition": 2,
  "offset": 1045,
  "eventId": "cb7fa3fa-bdfc-4dfa-8a24-121746bfd181",
  "correlationId": "5e85d52f-5a98-44f4-b29c-635a8994643f",
  "traceId": "00112233445566778899aabbccddeeff",
  "stage": "reserve-stock",
  "outcome": "success"
}
~~~

Log nên có event ID và topic/partition/offset để tìm đúng record. Một correlation ID có thể xuất hiện ở hàng trăm events; thiếu event ID sẽ khó phân biệt retry của một event với nhiều events mới cùng workflow.

## 24. Runbook khi một flow mất Correlation ID

Nếu Order API có C1 nhưng Payment Consumer không tìm thấy log theo C1:

1. Xác định record đầu tiên theo event ID/topic/partition/offset.
2. Kiểm tra producer có add `x-correlation-id=C1` vào `ProducerRecord` không.
3. Xác nhận Kafka producer send và transaction commit thành công khi áp dụng.
4. Đọc record từ topic qua tool/test consumer có quyền phù hợp để xem raw headers.
5. Kiểm tra Inventory Consumer nhận đúng C1.
6. Kiểm tra header validation có reject hoặc overwrite ID không.
7. Kiểm tra publisher của `stock.reserved` có copy C1 sang output không.
8. Xác định có outbox, bridge, Kafka Streams, Connect hoặc converter tạo record mới không.
9. Kiểm tra retry topics/DLT có preserve header không.
10. Phân biệt ID bị mất trong Kafka record với MDC bị mất ở async thread.
11. Kiểm tra log schema có dùng `correlationId` thống nhất không.
12. Nếu tracing có bật, dùng traceId của bước trước để tìm lỗi context propagation.
13. Kiểm tra request/reply framework correlation header có bị ghi đè không.
14. Sửa đúng boundary và bổ sung integration test cho trường hợp bị mất.
15. Không tự reset Kafka offsets hoặc replay production data chỉ để tìm correlation ID.

Log tracing nên phục vụ điều tra; các thao tác recovery/replay trên production cần runbook và kiểm soát side effect riêng.

## 25. Unit test header helper

Một unit test không cần Kafka broker:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import org.apache.kafka.common.header.internals.RecordHeaders;
import org.junit.jupiter.api.Test;

class CorrelationHeadersTest {

    @Test
    void roundTripUtf8() {
        var headers = new RecordHeaders();

        String id = "5e85d52f-5a98-44f4-b29c-635a8994643f";

        CorrelationHeaders.put(headers, id);

        assertEquals(
            id,
            CorrelationHeaders.read(headers)
        );

        assertArrayEquals(
            id.getBytes(StandardCharsets.UTF_8),
            headers.lastHeader(CorrelationHeaders.NAME).value()
        );
    }

    @Test
    void rejectsControlCharacters() {
        var headers = new RecordHeaders();

        assertThrows(
            IllegalArgumentException.class,
            () -> CorrelationHeaders.put(headers, "bad\nid")
        );
    }

    @Test
    void overwritesExistingCorrelationHeader() {
        var headers = new RecordHeaders();

        CorrelationHeaders.put(headers, "flow-1");
        CorrelationHeaders.put(headers, "flow-2");

        assertEquals(
            "flow-2",
            CorrelationHeaders.read(headers)
        );
    }
}
~~~

Test có thể bổ sung assert chỉ còn đúng một header name, byte length giới hạn, missing policy và duplicate input policy.

## 26. Integration test Kafka propagation

Với EmbeddedKafka, Testcontainers Kafka hoặc cluster test:

1. Tạo E1 với C1.
2. Publish E1 vào `orders.created` với header.
3. Đợi Inventory Consumer nhận.
4. Xác nhận consumer đọc C1 và tạo E2 mới.
5. Đọc output record E2 ở `stock.reserved` bằng test consumer.
6. Xác nhận `E2 != E1` nhưng correlation ID vẫn C1.
7. Cho downstream listener publish E3 và xác nhận C1 vẫn được giữ.
8. Tạo lỗi retryable; xác nhận các attempts giữ C1.
9. Cho hết retry và đọc DLT, xác nhận custom header vẫn có C1.
10. Kiểm tra record thiếu header và invalid header theo compatibility/strict policy.
11. Test duplicate header names; xác nhận policy không mơ hồ.
12. Test MDC leak bằng hai records có C1 và C2.
13. Test async executor không làm mất log context.
14. Test outbox publisher restart vẫn lấy được C1 từ DB row.
15. Nếu bật Observation, xác nhận trace context hoạt động độc lập với business correlation ID.

**Không chỉ test helper encode/decode.** Nếu hệ thống dùng custom DLT recoverer/bridge, phải test record thực sự đi qua Kafka để xác định header có được preserve hay không.

### 26.1. Batch test

Gửi batch chứa các records C1/C2 và xác nhận listener sử dụng correlation ID riêng từng record, không gán C1 cho toàn batch.

### 26.2. Replay test

Replay E1 từ DLT với correlation C1 rồi kiểm tra business idempotency và traceability. Có thể sinh một `replayExecutionId` riêng để phân biệt lần vận hành mới; không thay business event ID chỉ để dễ đếm retry.

## 27. Những lỗi triển khai thường gặp

**Chỉ đặt MDC ở HTTP entry point, không add Kafka header:** consumer ở process khác không thể đọc thread-local của HTTP thread.

**Mỗi hop sinh correlation mới:** logs không nối được giữa các service.

**Dùng correlation ID làm event ID hoặc inbox unique key:** bỏ qua nhiều events hợp lệ cùng workflow.

**Dùng correlation ID làm Kafka key bất chấp ordering requirement:** có thể phá partitioning theo aggregate.

**Đọc header như String mà không kiểm tra encoding:** Kafka header value là bytes.

**Không xử lý multiple headers cùng tên:** có thể chọn sai ID hoặc chấp nhận giá trị không đáng tin.

**Tự truyền KafkaHeaders.CORRELATION_ID của request/reply như business ID:** có thể phá response matching.

**Tự đặt traceparent bằng UUID tùy ý:** sai W3C tracing format.

**Không copy ID khi tạo ProducerRecord mới:** outbox, Kafka Streams, Connect hoặc bridge làm mất metadata.

**Không preserve ID qua DLT:** incident không thể nối log giữa failure và recovery.

**Đặt MDC nhưng không cleanup:** consumer thread tái sử dụng gây log gắn sai ID.

**Dùng async executor mà không propagate context:** logs không còn correlation ID.

**Bật MDC rồi nghĩ offset commit đã an toàn:** correctness và observability là hai vấn đề khác nhau.

**Gắn correlation ID làm Prometheus label:** tạo cardinality rất lớn.

**Dùng correlation ID làm quyền truy cập:** header không có tính xác thực.

**Log toàn bộ headers/payload:** có thể lộ PII hoặc secrets.

**Cho rằng cùng correlation ID nghĩa cùng Kafka transaction:** header không quyết định transaction boundary.

**Không lưu ID trong outbox table:** publisher chạy ngoài thread gốc làm đứt propagation.

## 28. Bảng quyết định nhanh

| Mục tiêu | Cách làm | Điều cần tránh |
|---|---|---|
| Liên kết một workflow qua nhiều events | `x-correlation-id` | Tạo ID mới cho mỗi hop |
| Deduplicate một event | `eventId`/inbox unique key | Unique theo correlation ID |
| Tái dựng quan hệ nhân quả | `x-causation-id` | Nhầm với trace/span ID |
| Kafka producer add header | `ProducerRecord.headers().add` | Giả định tự sinh custom header |
| Consumer đọc header | `ConsumerRecord.headers()` | Bỏ qua byte encoding/multiple headers |
| Logging | MDC có cleanup, structured logs | Leak thread-local |
| Async tasks | Truyền ID/context propagation | Commit offset sớm |
| Distributed tracing | Micrometer/OpenTelemetry | Ghi đè `traceparent` |
| Request/reply | Giữ framework correlation token | Ghi đè `KafkaHeaders.CORRELATION_ID` |
| Retry/DLT | Preserve custom header qua đường recovery | Coi mọi mapper tự copy |
| Outbox | Lưu ID bền vững trong outbox row | Dựa vào MDC của thread cũ |
| Monitoring | Đếm missing/invalid header theo topic/service | Metric label theo từng ID |
| External input | Validate và đặt trust boundary | Dùng header như auth |
| Production diagnosis | Event ID + C1 + topic/partition/offset | Reset offset khi thiếu trace |

## 29. Nguyên tắc vận hành production

- Chọn một tên header ổn định, encoding và format rõ ràng.
- Sinh Correlation ID tại entry boundary; preserve qua downstream Kafka events.
- Phân biệt correlation ID, event ID, causation ID và trace ID.
- Validate data untrusted; giới hạn kích thước và tránh PII.
- Dùng helper encode/decode để thống nhất hành vi.
- Đọc raw Kafka headers nếu cần tránh phụ thuộc message converters.
- Dùng MDC/structured logs nhưng cleanup sau mỗi record.
- Với async worker, truyền ID rõ ràng, không phụ thuộc thread-local.
- Bảo đảm retry/DLT và outbox preserve correlation ID qua lifecycle.
- Giữ `KafkaHeaders.CORRELATION_ID` cho Spring Kafka request/reply khi framework sử dụng.
- Bật Observation/Tracing theo đúng version và để tracing instrumentation sở hữu trace context.
- Không dùng correlation ID thay cho Kafka transaction, business idempotency hoặc offset correctness.
- Không gắn correlation ID thành metric label.
- Test nhiều hops, retry, DLT, async, batch, replay và restart.
- Tạo runbook điều tra khi một bước mất correlation header.

## 30. Kết luận

**Correlation ID trong Kafka header** là một cơ chế nền tảng để quan sát chuỗi xử lý event-driven trong Spring Kafka. Header chứa bytes nên cần contract rõ ràng về tên, encoding, format và validation. Producer phải add ID, consumer phải đọc và truyền tiếp; các bước retry/DLT, batch, outbox và async cần preserve ID theo đúng phạm vi nghiệp vụ.

Correlation ID giúp nối logs qua nhiều process và nhiều topics, nhưng không tự tạo distributed tracing, ordering, exactly-once hoặc database idempotency. Khi kết hợp header propagation với structured logging, Micrometer/OpenTelemetry, error handling và transaction boundaries phù hợp, hệ thống sẽ dễ truy vết và phục hồi hơn trước các sự cố production.
