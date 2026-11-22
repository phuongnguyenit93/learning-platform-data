# Kafka headers và Spring MessageHeaders

Kafka record không chỉ có key và value. Mỗi record còn có thể mang **headers** để truyền thông tin phụ trợ như correlation ID, trace context, loại sự kiện, phiên bản hợp đồng hoặc nguồn phát. Headers giúp các thành phần phối hợp và truy vết luồng xử lý mà không cần nhồi mọi metadata vào payload nghiệp vụ.

Ở tầng Kafka, header là một cặp tên và giá trị dạng byte. Ở tầng Spring Messaging, ứng dụng thường làm việc với **MessageHeaders**, nơi giá trị header là object Java và có thể được ánh xạ sang Kafka headers thông qua KafkaHeaderMapper. Hai mô hình liên quan nhưng không giống nhau: hiểu cách chuyển đổi giữa chúng giúp tránh lỗi kiểu dữ liệu, mất metadata hoặc gửi nhầm header nội bộ ra broker.

Bài học thuộc chương **Headers và metadata** của module **SPRING_KAFKA_MESSAGING**, tập trung vào cách tạo, gửi, nhận và ánh xạ Kafka headers trong Spring Kafka, đồng thời thiết kế metadata có ích cho tracing, vận hành và tương thích giữa các dịch vụ.

## Kết quả cần đạt

Sau bài học, bạn có thể:

- Giải thích cấu trúc header trong Kafka record và đặc điểm byte[].
- Phân biệt Kafka headers, record metadata và Spring MessageHeaders.
- Tạo headers bằng ProducerRecord và KafkaTemplate.
- Gửi Spring Message qua KafkaTemplate với KafkaHeaders.
- Đọc headers bằng ConsumerRecord, @Header và @Headers.
- Hiểu vai trò của DefaultKafkaHeaderMapper và SimpleKafkaHeaderMapper.
- Xử lý header trùng tên, encoding và kiểu dữ liệu.
- Truyền correlation ID và trace context xuyên các service.
- Thiết kế allowlist, tránh lộ dữ liệu nhạy cảm và kiểm thử mapping.

## 1. Kafka record gồm những thành phần nào?

Một Kafka record có key, value, timestamp và headers. Key/value được serialize thành byte theo serializer cấu hình ở producer; header cũng được lưu dưới dạng tên và giá trị byte.

Có thể hình dung cấu trúc:

~~~text
Kafka record
├── key        -> bytes (có thể null)
├── value      -> bytes (có thể null)
├── timestamp  -> record timestamp
└── headers
    ├── correlation_id -> UTF-8 bytes
    ├── event_type     -> UTF-8 bytes
    └── traceparent    -> UTF-8 bytes
~~~

Ví dụ một sự kiện OrderCreated:

| Thành phần | Ví dụ | Mục đích |
|---|---|---|
| Key | order-1001 | Định tuyến partition và giữ thứ tự theo đơn hàng. |
| Value | JSON OrderCreatedEvent | Nội dung nghiệp vụ. |
| Timestamp | 2026-11-17T03:30:00Z | Thời điểm record theo timestamp policy. |
| correlation_id | corr-82a1 | Liên kết log của một luồng yêu cầu. |
| event_type | OrderCreated | Nhận diện loại sự kiện. |
| event_version | 2 | Hỗ trợ chọn hợp đồng hoặc logic tương thích. |
| traceparent | W3C trace context | Liên kết distributed trace. |

Headers là metadata phụ trợ cho record. Không nên chuyển toàn bộ dữ liệu nghiệp vụ sang header: payload vẫn là nơi chứa nội dung sự kiện có cấu trúc và được version hóa.

## 2. Đặc điểm của Kafka Headers

Kafka sử dụng interface Headers và các implementation như RecordHeaders. Mỗi header có:

- Tên dạng String.
- Giá trị dạng byte[]; giá trị có thể rỗng hoặc null tùy cách tạo record.
- Vị trí trong danh sách header.

Kafka cho phép nhiều header trùng tên trên cùng record. Điều này hữu ích khi một record cần mang nhiều giá trị cùng loại, nhưng consumer phải xác định cách đọc chúng.

Ví dụ:

~~~java
ProducerRecord<String, String> record =
        new ProducerRecord<>(
                "orders.created",
                "order-1001",
                "{\"orderId\":\"order-1001\"}"
        );

record.headers()
        .add("correlation_id", "corr-82a1".getBytes(StandardCharsets.UTF_8))
        .add("event_type", "OrderCreated".getBytes(StandardCharsets.UTF_8))
        .add("event_version", "2".getBytes(StandardCharsets.UTF_8));

kafkaTemplate.send(record);
~~~

Đoạn code dùng Kafka ProducerRecord và thêm header trước khi gửi. Với header dạng text, nên quy ước encoding UTF-8 ở cả producer và consumer.

Đọc header từ ConsumerRecord:

~~~java
Header header = record.headers().lastHeader("correlation_id");

String correlationId = header == null
        ? null
        : new String(header.value(), StandardCharsets.UTF_8);
~~~

Các API thường dùng:

| API | Ý nghĩa |
|---|---|
| add(key, value) | Thêm một header; không tự thay thế header trùng tên. |
| lastHeader(key) | Lấy header cuối cùng có tên đó. |
| headers(key) | Lấy tất cả header trùng tên theo thứ tự. |
| remove(key) | Xóa các header có tên tương ứng. |
| toArray() | Lấy các header thành mảng để duyệt. |

Nếu header trùng tên, lastHeader chỉ trả về một giá trị cuối. Khi hợp đồng cho phép nhiều giá trị, hãy dùng headers(name) và xử lý toàn bộ danh sách.

## 3. Headers khác record metadata như thế nào?

Kafka headers do producer gắn vào record. Một số thông tin khác được Kafka broker hoặc consumer cung cấp như metadata của record, không phải custom header.

| Thông tin | Nằm ở đâu | Ví dụ |
|---|---|---|
| correlation_id | Kafka record header | corr-82a1 |
| event_type | Kafka record header | OrderCreated |
| topic | Record metadata / ConsumerRecord | orders.created |
| partition | Record metadata / ConsumerRecord | 2 |
| offset | Record metadata / ConsumerRecord | 145 |
| timestamp | Record metadata / ConsumerRecord | Timestamp của record |
| consumer group | Consumer configuration và group metadata | orders-fulfillment |

Producer có thể đặt timestamp khi tạo ProducerRecord, nhưng broker có thể áp dụng timestamp policy của topic để xác định timestamp lưu trữ. Topic, partition và offset được xác định trong quá trình gửi/ghi record; chúng không phải custom header do ứng dụng tùy ý đặt để thay thế metadata thật.

Trong Spring Kafka, một số record metadata được ánh xạ thành Spring MessageHeaders khi nhận message, ví dụ KafkaHeaders.RECEIVED_TOPIC, RECEIVED_PARTITION, OFFSET và RECEIVED_TIMESTAMP. Tên header Spring này là cách framework trình bày metadata cho ứng dụng; chúng không có nghĩa broker đã lưu các trường đó như custom Kafka headers.

## 4. Spring Message và MessageHeaders

Spring Messaging biểu diễn message bằng payload và headers:

~~~text
org.springframework.messaging.Message
├── payload
└── MessageHeaders
    ├── id
    ├── timestamp
    ├── kafka_topic
    ├── kafka_messageKey
    └── correlation_id
~~~

MessageHeaders là một map bất biến sau khi message được tạo. Nếu cần xây dựng message mới hoặc thêm header, dùng MessageBuilder thay vì sửa trực tiếp map.

Ví dụ:

~~~java
Message<OrderCreatedEvent> message = MessageBuilder
        .withPayload(event)
        .setHeader("correlation_id", "corr-82a1")
        .setHeader("event_type", "OrderCreated")
        .setHeader("event_version", "2")
        .build();
~~~

MessageHeaders có thể chứa nhiều loại giá trị Java như String, Integer, UUID hoặc object khác. Kafka headers chỉ lưu byte[], vì vậy khi gửi message qua Spring Kafka cần có cơ chế ánh xạ và chuyển đổi.

Các header nội bộ của Spring như id và timestamp không nhất thiết được gửi sang Kafka. Header mapper áp dụng quy tắc lọc và chuyển đổi; không giả định mọi phần tử trong MessageHeaders đều trở thành header của record.

## 5. KafkaHeaders là gì?

Spring Kafka định nghĩa lớp KafkaHeaders chứa các tên header chuẩn để truyền thông tin giữa Spring Message và Kafka.

Một số hằng số thường gặp:

| Hằng số | Vai trò |
|---|---|
| KafkaHeaders.TOPIC | Topic đích khi gửi message. |
| KafkaHeaders.PARTITION | Partition đích nếu ứng dụng chỉ định. |
| KafkaHeaders.MESSAGE_KEY | Key của record gửi đi. |
| KafkaHeaders.TIMESTAMP | Timestamp gửi đi nếu được thiết lập. |
| KafkaHeaders.RECEIVED_TOPIC | Topic của record nhận được. |
| KafkaHeaders.RECEIVED_PARTITION | Partition của record nhận được. |
| KafkaHeaders.OFFSET | Offset của record nhận được. |
| KafkaHeaders.RECEIVED_TIMESTAMP | Timestamp của record nhận được. |
| KafkaHeaders.RECEIVED_KEY | Key của record nhận được. |

Các hằng số này giúp code tránh hardcode tên transport header. Tên và API cụ thể cần được đối chiếu với phiên bản Spring Kafka mà dự án sử dụng.

KafkaHeaders.TOPIC, MESSAGE_KEY và PARTITION là header điều khiển gửi message. RECEIVED_TOPIC, RECEIVED_PARTITION, OFFSET và RECEIVED_KEY là metadata được framework đưa vào message khi nhận record.

Không nhầm KafkaHeaders với tên custom header mà ứng dụng tự định nghĩa, ví dụ correlation_id hoặc event_type.

## 6. Gửi message bằng KafkaTemplate và Spring Message

KafkaTemplate hỗ trợ gửi Spring Message. Ứng dụng có thể đặt topic, key, partition và custom metadata trong MessageHeaders.

Ví dụ:

~~~java
@Service
public class OrderPublisher {

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    public OrderPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreatedEvent>> publish(
            OrderCreatedEvent event,
            String correlationId) {

        Message<OrderCreatedEvent> message = MessageBuilder
                .withPayload(event)
                .setHeader(KafkaHeaders.TOPIC, "orders.created")
                .setHeader(KafkaHeaders.MESSAGE_KEY, event.orderId())
                .setHeader("correlation_id", correlationId)
                .setHeader("event_type", "OrderCreated")
                .setHeader("event_version", "2")
                .build();

        return kafkaTemplate.send(message);
    }
}
~~~

Trong ví dụ:

- Payload là OrderCreatedEvent.
- KafkaHeaders.TOPIC xác định topic đích.
- KafkaHeaders.MESSAGE_KEY đặt key của record.
- correlation_id giúp liên kết log giữa các service.
- event_type và event_version mô tả loại và phiên bản hợp đồng.

Nếu cần chỉ định partition hoặc timestamp, có thể thêm KafkaHeaders.PARTITION và KafkaHeaders.TIMESTAMP theo API phiên bản đang dùng. Chỉ định partition thủ công làm producer bỏ qua chiến lược phân phối key thông thường, vì vậy chỉ dùng khi có yêu cầu kiến trúc rõ ràng.

## 7. Gửi bằng ProducerRecord khi cần kiểm soát header trực tiếp

Nếu cần kiểm soát byte[] chính xác, nhiều header trùng tên hoặc tương tác trực tiếp với Kafka API, dùng ProducerRecord.

~~~java
ProducerRecord<String, OrderCreatedEvent> record =
        new ProducerRecord<>(
                "orders.created",
                event.orderId(),
                event
        );

record.headers().add(
        new RecordHeader(
                "correlation_id",
                correlationId.getBytes(StandardCharsets.UTF_8)
        )
);

record.headers().add(
        new RecordHeader(
                "event_type",
                "OrderCreated".getBytes(StandardCharsets.UTF_8)
        )
);

kafkaTemplate.send(record);
~~~

ProducerRecord cho phép ứng dụng tự thêm, duyệt hoặc xóa header trước khi gửi. Cách này cũng phù hợp khi cần đảm bảo giá trị header là byte sequence cụ thể, không qua chuyển đổi JSON của Spring mapper.

Không dùng lẫn hai cách gửi trong cùng một luồng mà không thống nhất quy ước. Nếu một producer dùng MessageHeaders với mapper và producer khác ghi byte trực tiếp, consumer cần biết cách giải mã header tương ứng.

## 8. Nhận headers bằng @Header và @Headers

Với @KafkaListener, Spring Kafka có thể ánh xạ metadata và custom headers vào tham số listener.

Ví dụ:

~~~java
@Component
public class OrderCreatedListener {

    @KafkaListener(
            topics = "orders.created",
            groupId = "orders-fulfillment"
    )
    public void consume(
            @Payload OrderCreatedEvent event,
            @Header(value = KafkaHeaders.RECEIVED_KEY, required = false) String key,
            @Header(KafkaHeaders.RECEIVED_TOPIC) String topic,
            @Header(KafkaHeaders.RECEIVED_PARTITION) Integer partition,
            @Header(KafkaHeaders.OFFSET) Long offset,
            @Header(name = "correlation_id", required = false)
                    String correlationId,
            @Headers MessageHeaders headers) {

        log.info(
                "Received eventId={}, key={}, topic={}, partition={}, " +
                "offset={}, correlationId={}",
                event.eventId(),
                key,
                topic,
                partition,
                offset,
                correlationId
        );

        orderService.handle(event);
    }
}
~~~

Giải thích:

- @Payload nhận object đã deserialize.
- @Header lấy một header cụ thể theo tên.
- required=false cho phép header tùy chọn không tồn tại.
- @Headers nhận tập MessageHeaders để truy cập nhiều metadata.
- KafkaHeaders.RECEIVED_* là các header do Spring Kafka tạo khi nhận record.

Nếu key có thể null, hãy để tham số key là optional hoặc dùng kiểu phù hợp với hợp đồng. Không giả định mọi record đều có key.

Một cách khác là nhận trực tiếp ConsumerRecord:

~~~java
@KafkaListener(
        topics = "orders.created",
        groupId = "orders-fulfillment"
)
public void consume(ConsumerRecord<String, OrderCreatedEvent> record) {
    Header header = record.headers().lastHeader("correlation_id");

    String correlationId = header == null
            ? null
            : new String(header.value(), StandardCharsets.UTF_8);

    orderService.handle(
            record.value(),
            record.topic(),
            record.partition(),
            record.offset(),
            correlationId
    );
}
~~~

ConsumerRecord cho phép truy cập trực tiếp Kafka headers và metadata mà không cần ánh xạ thành Spring MessageHeaders. Chọn cách nhận phù hợp với nhu cầu: MessageHeaders thuận tiện cho Spring Messaging; ConsumerRecord hữu ích khi cần kiểm soát Kafka API chi tiết.

## 9. KafkaHeaderMapper chuyển đổi hai mô hình

KafkaHeaderMapper chịu trách nhiệm ánh xạ giữa Spring MessageHeaders và Kafka Headers. Khi dùng message converter, mapper chuyển các giá trị Java thành byte[] để gửi và chuyển byte[] nhận được thành giá trị trong Spring MessageHeaders.

Hai mapper thường gặp:

| Mapper | Đặc điểm | Khi phù hợp |
|---|---|---|
| DefaultKafkaHeaderMapper | Hỗ trợ chuyển đổi nhiều kiểu object, có thể dùng JSON và metadata kiểu | Ứng dụng cần truyền header có kiểu Java qua Spring Message. |
| SimpleKafkaHeaderMapper | Tập trung vào String và byte[] | Hợp đồng header đơn giản, muốn kiểm soát byte rõ ràng. |

DefaultKafkaHeaderMapper có thể ghi metadata kiểu cho header được serialize để phía nhận khôi phục kiểu Java. Việc khôi phục phụ thuộc type mapping, trusted packages và cấu hình mapper. Không nên tin cậy mọi class được khai báo trong header từ nguồn không đáng tin.

SimpleKafkaHeaderMapper phù hợp khi các service thống nhất header là String hoặc byte[]. Cách này giảm phụ thuộc vào class Java giữa các ứng dụng viết bằng ngôn ngữ hoặc phiên bản khác nhau.

Nếu ứng dụng cần cấu hình mapper rõ ràng, có thể tạo MessagingMessageConverter và gắn KafkaHeaderMapper tương ứng vào listener container factory hoặc KafkaTemplate theo cấu hình của phiên bản Spring Kafka đang dùng. Nhiều cấu hình mặc định đã tạo converter và mapper; chỉ tùy chỉnh khi có yêu cầu mapping cụ thể.

## 10. Header type mapping và tương thích giữa service

Một header trong MessageHeaders có thể là Integer, UUID hoặc object, nhưng khi đi qua Kafka nó trở thành byte[]. Nếu phía gửi dùng DefaultKafkaHeaderMapper, mapper có thể kèm metadata kiểu để phía nhận chuyển đổi về object tương ứng.

Điều này thuận tiện khi hai service cùng hệ sinh thái Java, nhưng tạo coupling nếu service phụ thuộc vào tên class hoặc package cụ thể của service phát.

Ví dụ không nên truyền object nội bộ phức tạp:

~~~java
.setHeader("customer_context", internalCustomerContext)
~~~

Một service khác có thể không có class InternalCustomerContext hoặc class đã đổi package. Việc deserialize header có thể thất bại dù payload nghiệp vụ vẫn hợp lệ.

Ưu tiên hợp đồng header đơn giản:

- String cho correlation ID, event type, tenant reference.
- Byte[] cho dữ liệu nhị phân cần định nghĩa rõ.
- Chuỗi số hoặc timestamp theo định dạng chuẩn nếu cần trao đổi giữa ngôn ngữ.
- W3C trace context cho distributed tracing.

Nếu cần header có kiểu, hãy công bố schema và quy tắc encoding độc lập với tên class Java. Tránh coi type metadata của mapper là một schema registry cho toàn bộ event contract.

## 11. Correlation ID và distributed tracing

Correlation ID giúp liên kết các log hoặc event thuộc cùng một yêu cầu nghiệp vụ. Ví dụ API nhận yêu cầu tạo đơn hàng, producer gửi OrderCreatedEvent với correlation_id; fulfillment và notification tiếp tục truyền ID này trong log và event đầu ra.

~~~mermaid
flowchart LR
    API[Order API] -->|correlation_id| K[Kafka topic]
    K --> F[Fulfillment service]
    K --> A[Analytics service]
    F -->|propagate context| N[Notification service]
    A -->|propagate context| R[Reporting]
~~~

Correlation ID là mã liên kết nghiệp vụ hoặc yêu cầu. Distributed tracing thường dùng traceparent và tracestate theo chuẩn W3C để liên kết span qua các tiến trình.

Nếu ứng dụng dùng Micrometer Tracing, OpenTelemetry hoặc instrumentation tương thích Kafka, hãy để thư viện tracing quản lý việc inject/extract context theo cấu hình. Không tự tạo trace ID ngẫu nhiên ở mỗi hop nếu mục tiêu là giữ một trace xuyên suốt.

Khi tạo event mới từ một event đã nhận, hãy xác định rõ context nào cần tiếp tục truyền và context nào cần tạo mới. Một nghiệp vụ mới có thể có correlation ID mới nhưng vẫn được liên kết với trace hoặc parent context trước đó theo quy tắc tracing.

Không dùng correlation ID thay cho eventId. Event ID nhận diện một sự kiện cụ thể; correlation ID liên kết nhiều thao tác trong cùng một luồng.

## 12. Chuyển tiếp headers khi tạo event mới

Một service thường nhận event rồi phát event khác. Việc chuyển tiếp headers có thể giữ correlation ID, trace context và một số thông tin nguồn, nhưng không nên sao chép toàn bộ header một cách mù quáng.

Ví dụ whitelist các header được phép truyền:

~~~java
Set<String> allowedHeaders = Set.of(
        "correlation_id",
        "traceparent",
        "tracestate",
        "tenant_reference"
);

ProducerRecord<String, OrderProcessedEvent> outbound =
        new ProducerRecord<>(
                "orders.processed",
                processed.orderId(),
                processed
        );

record.headers().forEach(header -> {
    if (allowedHeaders.contains(header.key())) {
        byte[] value = header.value();
        outbound.headers().add(
                new RecordHeader(
                        header.key(),
                        value == null ? null : Arrays.copyOf(value, value.length)
                )
        );
    }
});

kafkaTemplate.send(outbound);
~~~

Whitelist giúp kiểm soát metadata nào được đưa qua ranh giới service. Không chuyển tiếp tự động các header nội bộ như thông tin exception deserialize, DLT metadata, header quản lý retry hoặc header kỹ thuật chỉ có ý nghĩa trong một container.

Nếu header chứa tenant hoặc security context, hãy xác thực giá trị từ nguồn đáng tin và không dùng header do producer tùy ý đặt làm bằng chứng cấp quyền. Header Kafka là dữ liệu do bên gửi cung cấp; consumer phải coi chúng là input có thể sai hoặc giả mạo.

## 13. Quy ước đặt tên và encoding

Một quy ước header rõ ràng giúp các service trao đổi metadata ổn định.

Ví dụ:

| Header | Encoding | Quy ước |
|---|---|---|
| correlation_id | UTF-8 | ID liên kết luồng yêu cầu. |
| event_type | UTF-8 | Tên loại event theo hợp đồng. |
| event_version | UTF-8 | Phiên bản schema hoặc event contract. |
| traceparent | ASCII/UTF-8 theo W3C | Distributed trace context. |
| tenant_reference | UTF-8 | Mã tham chiếu tenant đã được xác thực theo nghiệp vụ. |
| source_service | UTF-8 | Tên dịch vụ phát event. |

Nguyên tắc:

- Chọn tên nhất quán, tránh nhiều alias cho cùng một ý nghĩa.
- Quy định encoding rõ ràng, thường là UTF-8 cho text.
- Quy định giá trị bắt buộc và tùy chọn.
- Quy định độ dài tối đa và cách xử lý giá trị thiếu.
- Dùng event_version cho hợp đồng sự kiện, không dựa duy nhất vào tên class.
- Tránh đặt payload lớn vào header.
- Không dùng header làm nơi lưu password, token hoặc dữ liệu cá nhân không cần thiết.

Kafka headers là một phần của record và làm tăng kích thước dữ liệu truyền/lưu. Header quá lớn có thể góp phần làm record vượt giới hạn message/request của broker hoặc producer. Hãy giữ header nhỏ, có mục đích rõ ràng.

## 14. Headers và bảo mật

Headers thường được xem là metadata phụ, nhưng chúng có thể chứa thông tin nhạy cảm hoặc ảnh hưởng tới cách consumer định tuyến và xử lý.

Các rủi ro cần kiểm soát:

- Header chứa access token, session token hoặc credential.
- Header chứa email, số điện thoại hoặc dữ liệu cá nhân.
- Producer giả mạo tenant_reference hoặc source_service.
- Type header dẫn consumer tới class không được phép deserialize.
- Consumer tin event_type hoặc version mà không xác thực payload.
- Log toàn bộ headers làm lộ dữ liệu hoặc trace context nhạy cảm.

Biện pháp:

- Chỉ truyền metadata tối thiểu cần thiết.
- Không đặt secret vào Kafka headers.
- Xác thực quyền dựa trên cơ chế bảo mật đáng tin, không dựa vào custom header.
- Giới hạn trusted packages và type mapping khi dùng DefaultKafkaHeaderMapper.
- Dùng ACL để giới hạn producer/consumer truy cập topic.
- Lọc header trước khi log và trước khi forward sang service khác.
- Định nghĩa allowlist header cho từng luồng sự kiện.
- Áp dụng retention và quyền truy cập phù hợp với topic có metadata nhạy cảm.

Header không thay thế TLS, SASL, ACL hoặc schema validation.

## 15. Kiểm thử Kafka headers và Spring MessageHeaders

Kiểm thử cần xác minh cả byte header ở Kafka record và giá trị sau khi Spring ánh xạ thành MessageHeaders.

Các lớp kiểm thử:

| Kiểm thử | Điều cần xác minh |
|---|---|
| ProducerRecord test | Header name và byte[] được tạo đúng. |
| Duplicate header test | Nhiều header cùng tên được giữ và đọc đúng thứ tự. |
| KafkaTemplate Message test | KafkaHeaders.TOPIC và MESSAGE_KEY điều khiển đúng record. |
| ConsumerRecord test | Header raw bytes và record metadata được đọc chính xác. |
| MessageHeaders mapping test | String/object được mapper chuyển đổi đúng. |
| Type mapping test | Header typed được giải mã theo cấu hình và allowlist. |
| Forwarding test | Chỉ header trong allowlist được chuyển tiếp. |
| Trace propagation test | traceparent/correlation ID được giữ xuyên service. |
| Security test | Secret hoặc header không tin cậy không được dùng làm quyền truy cập. |

Ví dụ kiểm thử gửi và đọc header bằng consumer:

~~~java
ProducerRecord<String, String> record =
        new ProducerRecord<>(
                "orders.created",
                "order-1001",
                "payload"
        );

record.headers().add(
        "correlation_id",
        "corr-82a1".getBytes(StandardCharsets.UTF_8)
);

kafkaTemplate.send(record).get(10, TimeUnit.SECONDS);

ConsumerRecord<String, String> received =
        KafkaTestUtils.getSingleRecord(
                consumer,
                "orders.created",
                Duration.ofSeconds(10)
        );

Header receivedHeader =
        received.headers().lastHeader("correlation_id");

assertThat(receivedHeader).isNotNull();
assertThat(new String(
        receivedHeader.value(),
        StandardCharsets.UTF_8
)).isEqualTo("corr-82a1");
~~~

Test này xác minh byte header thực sự được ghi và đọc lại. Nếu kiểm thử MessageHeaders mapper, hãy gửi bằng KafkaTemplate.send(Message<?>) rồi nhận bằng listener nhận Message<?> hoặc tham số @Header để xác minh kiểu và tên header sau mapping.

Có thể dùng EmbeddedKafka cho integration test nhanh hoặc Testcontainers khi cần kiểm tra cấu hình broker gần production. Không dùng Thread.sleep cố định; hãy dùng timeout và điều kiện đồng bộ rõ ràng.

## 16. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Gửi String nhưng consumer đọc như byte[] hoặc ngược lại mà không thống nhất | Giải mã header sai | Quy định encoding và mapper ở hai phía. |
| Nghĩ MessageHeaders và Kafka Headers giống nhau | Mất hoặc sai kiểu header khi gửi | Hiểu mapper và quy tắc chuyển đổi. |
| Dùng lastHeader khi header có nhiều giá trị | Chỉ đọc được giá trị cuối | Dùng headers(name) nếu hợp đồng cho phép nhiều giá trị. |
| Dùng class Java trong header làm hợp đồng liên dịch vụ | Coupling package/version giữa service | Dùng tên event và version ổn định. |
| Forward mọi header nhận được | Rò rỉ metadata nội bộ hoặc dữ liệu nhạy cảm | Dùng allowlist. |
| Tin tenant hoặc role từ custom header | Có thể tạo lỗ hổng phân quyền | Xác thực bằng cơ chế bảo mật đáng tin. |
| Đưa payload lớn vào header | Record phình to và tăng chi phí truyền tải | Đưa dữ liệu nghiệp vụ vào payload. |
| Nhầm KafkaHeaders.OFFSET với custom Kafka header | Hiểu sai metadata record | Phân biệt Spring header ánh xạ metadata với Kafka record headers. |
| Log toàn bộ header | Lộ token hoặc dữ liệu nhạy cảm | Lọc và che giá trị trước khi log. |

## 17. Bài tập tổng hợp: truyền metadata cho OrderCreatedEvent

Hãy xây dựng producer và consumer cho topic orders.created.

Yêu cầu:

1. Gửi OrderCreatedEvent bằng KafkaTemplate.
2. Đặt key bằng orderId.
3. Thêm correlation_id, event_type và event_version.
4. Gửi một lần bằng ProducerRecord và một lần bằng Spring Message.
5. Nhận event bằng ConsumerRecord và đọc raw Kafka headers.
6. Nhận event bằng @KafkaListener với @Header và @Headers.
7. Kiểm tra KafkaHeaders.RECEIVED_TOPIC, RECEIVED_PARTITION, OFFSET và RECEIVED_KEY.
8. Thêm hai header trùng tên và xác minh lastHeader cùng headers(name).
9. Cấu hình header mapper cho String và object header nếu use case cần.
10. Forward correlation_id và trace context theo allowlist sang orders.processed.
11. Thử gửi một header không hợp lệ hoặc sai encoding và kiểm tra consumer xử lý.
12. Xác minh header không được dùng làm cơ chế cấp quyền.
13. Viết integration test với EmbeddedKafka hoặc Testcontainers để kiểm tra round-trip.
14. Theo dõi correlation ID xuyên producer, consumer và service tiếp theo.

Bài tập hoàn thành khi metadata được gửi, nhận và ánh xạ nhất quán; consumer có thể truy vết record bằng correlation ID; các header nội bộ và nhạy cảm được kiểm soát.

## 18. Thứ tự học và tiêu chí hoàn thành

| Chặng | Nội dung trọng tâm | Tiêu chí tự kiểm tra |
|---|---|---|
| 1. Kafka Headers | Header name và byte[] | Tạo và đọc được header ở ProducerRecord/ConsumerRecord. |
| 2. Record metadata | Topic, partition, offset, timestamp | Phân biệt metadata broker với custom headers. |
| 3. Spring Message | Message và MessageHeaders | Xây dựng message bằng MessageBuilder. |
| 4. KafkaHeaders | Topic, key, partition và received metadata | Gửi/nhận qua các header chuẩn của Spring Kafka. |
| 5. Header mapper | DefaultKafkaHeaderMapper và SimpleKafkaHeaderMapper | Hiểu chuyển đổi String, byte[] và object. |
| 6. Tracing | Correlation ID và trace context | Truy vết được một luồng qua nhiều service. |
| 7. Forwarding | Allowlist và header propagation | Chỉ chuyển tiếp metadata cần thiết. |
| 8. Security | Trusted types, secret và untrusted headers | Không dùng custom header làm bằng chứng cấp quyền. |
| 9. Testing | Header round-trip và mapping | Kiểm thử được byte, kiểu dữ liệu và header trùng. |

Bài học hoàn thành khi bạn có thể tạo Kafka headers, gửi chúng bằng KafkaTemplate, đọc bằng ConsumerRecord hoặc Spring MessageHeaders, phân biệt custom header với record metadata và thiết kế propagation an toàn giữa các service.

Kafka headers giúp bổ sung context cho record mà không thay đổi payload nghiệp vụ. Spring MessageHeaders giúp ứng dụng làm việc thuận tiện với các giá trị Java; KafkaHeaderMapper chịu trách nhiệm chuyển đổi chúng thành byte headers. Khi hợp đồng tên, encoding, type mapping và chính sách bảo mật được thống nhất, metadata sẽ hỗ trợ tracing và vận hành mà không tạo coupling không cần thiết giữa các dịch vụ.

