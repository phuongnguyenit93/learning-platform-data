# HeaderMapper và header mapping

Kafka record có key, value và headers. Key thường tham gia chọn partition; value mang payload nghiệp vụ; headers mang metadata đi kèm record như correlation ID, trace context, content type, event version hoặc nguồn phát event.

Ở tầng Kafka, mỗi header là một cặp tên và byte array. Trong Spring Messaging, header thường được biểu diễn bằng object trong `MessageHeaders`. `KafkaHeaderMapper` là cầu nối chuyển đổi giữa hai mô hình này. Nó quyết định header nào được chuyển, cách chuyển kiểu dữ liệu và cách khôi phục giá trị ở consumer.

Header mapping quan trọng khi ứng dụng dùng `@KafkaListener`, `KafkaTemplate` và message converter. Nếu mapping không đúng, payload có thể vẫn được gửi/nhận thành công nhưng metadata bị thiếu, sai kiểu hoặc không tương thích với service khác.

Bài học thuộc chương **Message conversion** của module **SPRING_KAFKA_MESSAGING**. Module tập trung xây dựng ứng dụng gửi nhận sự kiện bằng Spring Kafka, `KafkaTemplate` và `@KafkaListener`, hiểu topic, partition, offset và consumer group; đồng thời học serialization, retry, dead-letter, transaction, exactly-once, xử lý đồng thời và kiểm thử để vận hành luồng messaging tin cậy.

## 1. Kafka header là gì?

Kafka header là metadata gắn với một record. Mỗi header có tên dạng chuỗi và value dạng byte array hoặc null. Kafka cho phép nhiều header cùng tên trong một record.

Ví dụ record đơn hàng có thể mang các header:

| Header | Giá trị ví dụ | Mục đích |
| --- | --- | --- |
| `correlation-id` | `req-8f31` | Liên kết log và request xuyên nhiều service. |
| `traceparent` | Trace context | Truyền ngữ cảnh distributed tracing. |
| `event-type` | `OrderCreated` | Nhận diện loại event. |
| `event-version` | `2` | Chọn contract/schema phù hợp. |
| `content-type` | `application/json` | Mô tả định dạng payload. |
| `source-service` | `order-service` | Xác định service phát event. |

Header không thay thế key hoặc value. Nó dành cho metadata nhỏ giúp truy vết và diễn giải payload. Header cũng không tự quyết định partition; partitioner mặc định sử dụng record key chứ không tự đọc header.

Một record có thể được hình dung như sau:

~~~text
ProducerRecord
  topic: order-events
  key: order-100
  value: OrderCreated(...)
  headers:
    correlation-id -> UTF-8 bytes
    event-type     -> UTF-8 bytes
    event-version  -> UTF-8 bytes
    traceparent    -> UTF-8 bytes
~~~

Kafka broker lưu headers cùng record. Consumer có quyền đọc record cũng có thể đọc các header đi kèm; không nên đặt bí mật hoặc thông tin xác thực nhạy cảm vào header.

Luồng mapping khi dùng Spring Message:

~~~mermaid
flowchart LR
    A[Spring Message] --> B[Message converter]
    B --> C[Payload conversion]
    B --> D[KafkaHeaderMapper]
    D --> E[Kafka Headers dạng byte]
    C --> F[ProducerRecord]
    E --> F
    F --> G[Kafka broker]
    G --> H[ConsumerRecord]
    H --> I[Message converter]
    I --> J[Payload object và MessageHeaders]
~~~

## 2. Kafka Headers và Spring MessageHeaders

Hai mô hình header có kiểu dữ liệu khác nhau:

| Đặc điểm | Kafka Headers | Spring MessageHeaders |
| --- | --- | --- |
| API | `org.apache.kafka.common.header.Headers` | `org.springframework.messaging.MessageHeaders` |
| Tên | String | String |
| Giá trị | byte[] hoặc null | Object |
| Lặp tên | Có thể có nhiều header cùng tên | Map chỉ có một giá trị cho mỗi key |
| Mục đích | Metadata trên Kafka record | Metadata trong Spring Message |
| Chuyển đổi | Cần mapper khi đi qua Spring Message conversion | Mapper chuyển thành header Kafka |

Kafka cho phép nhiều header cùng tên trong một record. Ví dụ một record có thể chứa nhiều `tag` hoặc nhiều giá trị metadata theo thứ tự. Ngược lại, `MessageHeaders` là map nên không biểu diễn trực tiếp nhiều giá trị cùng tên.

Nếu nghiệp vụ cần giữ nhiều header trùng tên, hãy đọc trực tiếp `ConsumerRecord.headers()` hoặc xây dựng quy tắc gom các giá trị vào một collection. Không nên giả định chuyển qua MessageHeaders sẽ luôn bảo toàn đầy đủ duplicate headers.

Header Kafka luôn là byte. Khi đọc chuỗi UTF-8, cần giải mã byte rõ ràng:

~~~java
Header header = record.headers().lastHeader("correlation-id");

String correlationId = header == null
    ? null
    : new String(header.value(), StandardCharsets.UTF_8);
~~~

Không gọi `toString()` trực tiếp trên byte[] để mong nhận nội dung chuỗi; kết quả sẽ là biểu diễn object của mảng byte, không phải nội dung đã decode.

## 3. HeaderMapper làm nhiệm vụ gì?

`KafkaHeaderMapper` định nghĩa cách chuyển header giữa Spring Message và Kafka record. Nó chỉ xử lý metadata header; việc chuyển payload do message converter và serializer/deserializer đảm nhiệm.

Hai chiều mapping:

1. **Outbound:** Spring MessageHeaders được chuyển thành Kafka Headers trước khi producer gửi record.
2. **Inbound:** Kafka Headers được chuyển thành MessageHeaders khi consumer record được chuyển thành Spring Message.

Các phương thức cốt lõi của mapper có dạng:

~~~java
void fromHeaders(MessageHeaders source, Headers target);
void toHeaders(Headers source, Map<String, Object> target);
~~~

Tên phương thức thể hiện hướng chuyển đổi:

- `fromHeaders`: từ Spring headers sang Kafka headers.
- `toHeaders`: từ Kafka headers sang Spring map headers.

`KafkaHeaderMapper` là abstraction. Ứng dụng thường dùng implementation có sẵn thay vì tự viết mapper từ đầu. Chỉ triển khai mapper tùy chỉnh khi cần wire format hoặc quy tắc mapping riêng mà các implementation tiêu chuẩn không đáp ứng.

## 4. DefaultKafkaHeaderMapper

`DefaultKafkaHeaderMapper` là implementation linh hoạt của Spring Kafka. Nó có thể map header kiểu String và byte[] trực tiếp; các kiểu object khác có thể được chuyển thành JSON bằng Jackson.

Khi cần khôi phục kiểu object, mapper có thể thêm metadata kiểu trong header đặc biệt `spring_json_header_types`. Metadata này cho biết kiểu Java ban đầu của các header được serialize dạng JSON.

Ví dụ Spring Message có header object:

~~~java
Message<OrderCreated> message =
    MessageBuilder.withPayload(event)
        .setHeader("correlation-id", "req-8f31")
        .setHeader("attempt", 2)
        .setHeader("origin", new ServiceOrigin("order-service"))
        .build();
~~~

Khi mapper chuyển sang Kafka:

- `correlation-id` là String, có thể được map như chuỗi.
- `attempt` là Integer, có thể được serialize dạng JSON kèm type metadata.
- `origin` là object, có thể được serialize JSON kèm type metadata.

Khi nhận lại, mapper có thể khôi phục kiểu object dựa trên metadata và cấu hình Jackson/type mapping tương ứng.

Điểm cần lưu ý là metadata kiểu Java có thể làm consumer phụ thuộc vào tên class/package của producer. Nếu producer đổi package hoặc consumer không có class tương ứng, việc khôi phục object có thể thất bại dù JSON payload vẫn hợp lệ.

Với event liên dịch vụ, ưu tiên header có wire format đơn giản và ổn định như String hoặc byte[]. Nếu cần metadata object phức tạp, nên xác định contract độc lập với class nội bộ của một service.

## 5. SimpleKafkaHeaderMapper

`SimpleKafkaHeaderMapper` phù hợp khi ứng dụng chỉ cần map header dạng String và byte[] mà không cần JSON type metadata cho các object tùy ý.

Nó hữu ích khi:

- Trao đổi metadata đơn giản giữa nhiều ngôn ngữ.
- Muốn kiểm soát byte format rõ ràng.
- Không muốn consumer phụ thuộc class Java của producer.
- Chỉ cần correlation ID, trace context, event version hoặc content type dạng chuỗi/byte.

Ví dụ các giá trị metadata có thể dùng:

~~~java
Message<OrderCreated> message =
    MessageBuilder.withPayload(event)
        .setHeader("correlation-id", "req-8f31")
        .setHeader("event-version", "2")
        .setHeader("content-type", "application/json")
        .build();
~~~

Nếu dùng mapper chỉ hỗ trợ String/byte[], các header object như `ServiceOrigin` cần được chuyển thành chuỗi hoặc byte[] trước khi gửi. Đây thường là lựa chọn dễ tương tác với producer/consumer viết bằng ngôn ngữ khác.

## 6. So sánh hai mapper

| Tiêu chí | DefaultKafkaHeaderMapper | SimpleKafkaHeaderMapper |
| --- | --- | --- |
| String | Hỗ trợ | Hỗ trợ |
| byte[] | Hỗ trợ | Hỗ trợ |
| Object khác | Có thể JSON serialize | Cần ứng dụng chuyển về String/byte[] |
| Type metadata | Có thể dùng `spring_json_header_types` | Không dùng cơ chế JSON type mapping |
| Interoperability | Cần chú ý type metadata và class | Đơn giản hơn với wire value rõ ràng |
| Use case | Spring-to-Spring có header object | Header đơn giản, cross-language |

Không có mapper tốt nhất cho mọi trường hợp. Nếu header chỉ là metadata chuẩn dạng chuỗi hoặc byte, SimpleKafkaHeaderMapper giúp wire format rõ ràng. Nếu ứng dụng cần truyền header object giữa các thành phần Spring và chấp nhận type metadata, DefaultKafkaHeaderMapper thuận tiện hơn.

## 7. Mapping patterns: chọn header nào được chuyển?

Không phải mọi Spring Message header đều nên được gửi lên Kafka. MessageHeaders có thể chứa metadata nội bộ của framework như ID và timestamp, trong khi Kafka record chỉ nên mang metadata cần thiết cho consumer.

`DefaultKafkaHeaderMapper` hỗ trợ patterns để chọn header theo tên. Pattern có thể dùng wildcard và tiền tố phủ định `!` để loại trừ header. Các pattern được xét theo thứ tự cấu hình; pattern khớp đầu tiên quyết định header được map hay bị loại. Vì vậy, đặt ngoại lệ cụ thể trước wildcard tổng quát như `*`.

Ví dụ cấu hình chỉ chuyển các header nghiệp vụ và trace:

~~~java
@Bean
public KafkaHeaderMapper kafkaHeaderMapper() {
    return new DefaultKafkaHeaderMapper(
        "!id",
        "!timestamp",
        "correlation-id",
        "event-*",
        "traceparent",
        "tracestate"
    );
}
~~~

Ví dụ trên loại trừ ID/timestamp nội bộ và chỉ cho phép các header đã nêu. Tên pattern cụ thể cần khớp naming convention của ứng dụng.

Nếu muốn map tất cả header ngoại trừ một số header nội bộ, có thể dùng pattern phủ định kết hợp wildcard:

~~~java
@Bean
public KafkaHeaderMapper kafkaHeaderMapper() {
    return new DefaultKafkaHeaderMapper(
        "!id",
        "!timestamp",
        "*"
    );
}
~~~

Không nên dùng wildcard rộng nếu message có thể mang security context, authentication object hoặc metadata nội bộ không dành cho consumer. Allowlist theo nghiệp vụ thường dễ review và an toàn hơn.

## 8. Map raw header và encoding

Với một số header, ứng dụng muốn kiểm soát byte chính xác thay vì JSON serialize object. Ví dụ `traceparent`, `correlation-id` và `event-version` thường có wire value dạng UTF-8.

`DefaultKafkaHeaderMapper` hỗ trợ cấu hình các header được map raw thông qua các API như `addRawMappedHeader` hoặc `setRawMappedHeaders` tùy phiên bản. Cấu hình raw mapping hữu ích khi cần đọc/ghi header dưới dạng chuỗi hoặc byte mà không đi qua JSON type metadata.

Nguyên tắc khi chọn raw mapping:

- Thống nhất charset, thường là UTF-8 cho text.
- Quy định rõ header là text hay binary.
- Không serialize cùng một header theo hai định dạng khác nhau giữa producer.
- Kiểm tra hành vi inbound/outbound của cấu hình raw theo phiên bản Spring Kafka.
- Có test xác nhận byte gửi đi đúng với byte consumer nhận được.

Ví dụ tự tạo raw Kafka header không phụ thuộc mapper:

~~~java
ProducerRecord<String, OrderCreated> record =
    new ProducerRecord<>("order-events", event.orderId(), event);

record.headers().add(
    "correlation-id",
    "req-8f31".getBytes(StandardCharsets.UTF_8)
);

kafkaTemplate.send(record);
~~~

Ở đây ứng dụng ghi trực tiếp Kafka Headers nên không cần mapper để chuyển header đó. Đây là cách phù hợp khi cần kiểm soát byte wire format chính xác.

## 9. Gắn HeaderMapper vào message converter

`MessagingMessageConverter` chuyển đổi giữa Kafka record và Spring Message. Nó xử lý payload conversion và sử dụng `KafkaHeaderMapper` để chuyển metadata header.

Mapper có thể được gắn vào converter:

~~~java
@Bean
public RecordMessageConverter kafkaRecordMessageConverter(
        KafkaHeaderMapper kafkaHeaderMapper) {

    MessagingMessageConverter converter =
        new MessagingMessageConverter();

    converter.setHeaderMapper(kafkaHeaderMapper);
    return converter;
}
~~~

Đối với listener container factory, có thể cấu hình record converter:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        orderKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory,
            RecordMessageConverter kafkaRecordMessageConverter) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setRecordMessageConverter(kafkaRecordMessageConverter);
    return factory;
}
~~~

Với KafkaTemplate, có thể đặt message converter tương ứng khi dùng API gửi Spring Message:

~~~java
@Bean
public KafkaTemplate<String, OrderCreated> orderKafkaTemplate(
        ProducerFactory<String, OrderCreated> producerFactory,
        RecordMessageConverter kafkaRecordMessageConverter) {

    KafkaTemplate<String, OrderCreated> template =
        new KafkaTemplate<>(producerFactory);

    template.setMessageConverter(kafkaRecordMessageConverter);
    return template;
}
~~~

Tên API và cách auto-configuration có thể khác theo phiên bản Spring Kafka/Spring Boot. Nếu ứng dụng dùng factory mặc định, hãy kiểm tra converter đang thực sự được gắn vào template và listener container; chỉ khai báo một bean mapper không bảo đảm mọi converter tự sử dụng nó trong mọi cấu hình.

## 10. Gửi Spring Message có custom headers

Khi dùng KafkaTemplate với message converter, có thể tạo Spring Message bằng MessageBuilder:

~~~java
Message<OrderCreated> message =
    MessageBuilder.withPayload(event)
        .setHeader(KafkaHeaders.TOPIC, "order-events")
        .setHeader(KafkaHeaders.MESSAGE_KEY, event.orderId())
        .setHeader("correlation-id", "req-8f31")
        .setHeader("event-version", "2")
        .setHeader("content-type", "application/json")
        .build();

kafkaTemplate.send(message);
~~~

Message converter lấy topic/key từ các header dành riêng của Spring Kafka và chuyển custom headers qua KafkaHeaderMapper. Tên header hệ thống như `KafkaHeaders.TOPIC` và `KafkaHeaders.MESSAGE_KEY` phục vụ routing của template; chúng không phải custom metadata cần tự map như correlation ID.

Nếu gọi KafkaTemplate.send(topic, key, value) trực tiếp, ứng dụng có thể tạo ProducerRecord để thêm native Kafka headers hoặc dùng API gửi Message với converter. Chọn một cách nhất quán để tránh nhầm giữa header điều khiển gửi và header nghiệp vụ.

## 11. Đọc custom headers trong @KafkaListener

Listener có thể nhận toàn bộ ConsumerRecord để truy cập Kafka Headers:

~~~java
@KafkaListener(
    topics = "order-events",
    groupId = "billing-service"
)
public void onOrderEvent(
        ConsumerRecord<String, OrderCreated> record) {

    Header header =
        record.headers().lastHeader("correlation-id");

    String correlationId = header == null
        ? null
        : new String(header.value(), StandardCharsets.UTF_8);

    billingService.process(record.value(), correlationId);
}
~~~

Cách này cho phép đọc header ở dạng byte và giữ khả năng truy cập duplicate headers.

Nếu listener chỉ cần một vài metadata, có thể bind bằng `@Header`:

~~~java
@KafkaListener(
    topics = "order-events",
    groupId = "billing-service"
)
public void onOrderEvent(
        OrderCreated event,
        @Header(name = "correlation-id", required = false)
        String correlationId,
        @Header(name = "event-version", required = false)
        String eventVersion) {

    billingService.process(event, correlationId, eventVersion);
}
~~~

Việc bind String phụ thuộc message converter và header mapper đã chuyển byte thành kiểu phù hợp. Nếu header được giữ dạng byte[], tham số listener cần dùng kiểu tương ứng hoặc tự decode.

Có thể nhận tất cả Spring Message headers bằng `@Headers Map<String, Object>` khi listener dùng message conversion. Cách này tiện cho xử lý metadata tổng quát nhưng không bảo toàn nhiều header trùng tên như Kafka Headers.

## 12. Header hệ thống của Spring Kafka

Spring Kafka dùng một số header riêng để truyền metadata giữa Kafka record và listener method. Ví dụ:

| Header | Ý nghĩa |
| --- | --- |
| `KafkaHeaders.TOPIC` | Topic đích khi gửi message. |
| `KafkaHeaders.MESSAGE_KEY` | Key của record khi gửi bằng Message API. |
| `KafkaHeaders.PARTITION` | Partition được chỉ định khi gửi. |
| `KafkaHeaders.RECEIVED_TOPIC` | Topic của record consumer nhận. |
| `KafkaHeaders.RECEIVED_PARTITION` | Partition của record nhận. |
| `KafkaHeaders.OFFSET` | Offset của record nhận. |
| `KafkaHeaders.RECEIVED_KEY` | Key của record nhận. |
| `KafkaHeaders.RECEIVED_TIMESTAMP` | Timestamp của record nhận. |

Tên constant và kiểu giá trị có thể khác nhẹ giữa các thế hệ Spring Kafka. Ưu tiên dùng constant thay vì hard-code tên chuỗi khi truy cập header framework.

Không nên tự đặt custom header trùng tên với header framework. Một số header chỉ có ý nghĩa trong Spring Message conversion và không nhất thiết được ghi nguyên dạng vào Kafka record.

## 13. Duplicate headers và thứ tự header

Kafka cho phép một record có nhiều header cùng tên. Ví dụ:

~~~java
record.headers().add("tag", "priority".getBytes(StandardCharsets.UTF_8));
record.headers().add("tag", "customer".getBytes(StandardCharsets.UTF_8));
~~~

Đọc tất cả giá trị:

~~~java
for (Header header : record.headers().headers("tag")) {
    String value =
        new String(header.value(), StandardCharsets.UTF_8);
    log.info("tag={}", value);
}
~~~

`lastHeader("tag")` chỉ lấy header cuối cùng có tên đó. Nếu nghiệp vụ cần tất cả tag, phải duyệt collection thay vì chỉ đọc lastHeader.

Khi chuyển sang `MessageHeaders`, map không thể biểu diễn trực tiếp nhiều giá trị cùng tên. Nếu duplicate header là một phần của contract, giữ ConsumerRecord hoặc quy ước chuyển thành List<String> trong mapper/converter tùy chỉnh.

## 14. Header mapping giữa các ngôn ngữ và service

Kafka thường là nền tảng tích hợp nhiều service viết bằng Java, Go, Python, Node.js hoặc .NET. Header nên dùng wire format đơn giản để mọi client có thể đọc.

Một contract header có thể quy định:

| Header | Wire format | Quy tắc |
| --- | --- | --- |
| `correlation-id` | UTF-8 string | ID của luồng request/event. |
| `event-type` | UTF-8 string | Tên event ổn định, không phải tên class Java. |
| `event-version` | UTF-8 string hoặc số dạng text | Phiên bản contract. |
| `content-type` | UTF-8 string | MIME type của payload. |
| `traceparent` | W3C Trace Context string | Ngữ cảnh trace chuẩn. |
| `source-service` | UTF-8 string | Tên service phát event. |

Không nên gửi object Java tùy ý trong header nếu consumer đa ngôn ngữ cần đọc. Một mapper JSON có thể serialize object nhưng không có nghĩa consumer Go/Python hiểu metadata kiểu Java hoặc special type header của Spring.

Nếu cần object metadata, hãy định nghĩa JSON schema nhỏ và đặt bytes JSON trong header, hoặc chuyển dữ liệu đó vào envelope payload khi nó mang ý nghĩa nghiệp vụ quan trọng.

## 15. Bảo mật và giới hạn kích thước header

Header được lưu cùng record và có thể được consumer có quyền đọc topic truy cập. Do đó:

- Không đặt password, access token hoặc secret vào header.
- Không coi header là kênh bảo mật riêng với payload.
- Giới hạn metadata ở mức nhỏ và cần thiết.
- Tránh đặt payload nghiệp vụ lớn vào header.
- Không cho phép mọi header nội bộ tự động đi qua mapper.
- Kiểm soát type metadata nếu dùng DefaultKafkaHeaderMapper.
- Không log toàn bộ headers nếu có thể chứa thông tin nhạy cảm.

Header góp phần vào kích thước record/batch và chịu các giới hạn message size của Kafka/broker/client. Nhiều header lớn làm tăng network, memory và chi phí xử lý. Payload chính nên nằm trong value; header chỉ mang thông tin hỗ trợ.

## 16. Kiểm thử header mapping

Nên kiểm thử mapping ở cả hai chiều và kiểm tra wire format thực tế.

### 16.1. Test mapper outbound

Tạo Spring Message có String, byte[] và object header, sau đó gọi mapper để chuyển sang Kafka Headers. Xác nhận:

- Header nằm trong allowlist được chuyển.
- Header bị exclude không xuất hiện.
- String/byte[] giữ đúng giá trị.
- Object header được serialize theo chính sách đã chọn.
- Type metadata chỉ xuất hiện khi cấu hình cần.

### 16.2. Test mapper inbound

Tạo Kafka Headers với các byte value rồi map sang Spring headers. Kiểm tra:

- Header cần nhận được khôi phục.
- Charset decode đúng.
- Header không được phép không xuất hiện.
- Metadata type được xử lý đúng.
- Duplicate headers được xử lý theo contract đã định.

### 16.3. Integration test với Kafka

Dùng Embedded Kafka hoặc Testcontainers để gửi record có custom headers và nhận qua @KafkaListener. Kiểm tra topic, partition, offset, payload và metadata. Test này xác nhận converter, mapper và Kafka client thực sự được wiring đúng trong application context.

Nếu hệ thống có producer đa ngôn ngữ, hãy dùng fixture byte header do client khác tạo và xác nhận Spring consumer đọc đúng; đồng thời kiểm tra header do Spring producer tạo có thể được client kia hiểu.

## 17. Lỗi thường gặp khi mapping headers

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Header không tới consumer | Pattern không match hoặc converter không dùng mapper mong muốn | Kiểm tra mapper, converter và allowlist patterns |
| Header object bị chuyển thành JSON byte | DefaultKafkaHeaderMapper serialize kiểu object theo JSON | Dùng String/byte[] hoặc cấu hình raw mapping |
| Consumer không khôi phục được kiểu header | Thiếu type metadata, class không tồn tại hoặc mapping type sai | Dùng contract trung lập, type mapping hoặc raw header |
| Header String nhận về là byte[] | Mapper giữ raw bytes hoặc converter không decode theo mong muốn | Cấu hình raw mapping/charset và kiểm tra kiểu tham số |
| Mất một số header trùng tên | Spring MessageHeaders là map, không giữ duplicate key | Đọc ConsumerRecord.headers() hoặc gom thành collection |
| Header id/timestamp xuất hiện ngoài ý muốn | Pattern mapping cho phép header framework-generated | Exclude header nội bộ bằng patterns |
| Custom header ghi đè header hệ thống | Trùng tên KafkaHeaders | Dùng namespace custom riêng và Spring constants |
| Header tăng kích thước record | Gửi metadata lớn hoặc lặp lại nhiều lần | Giữ header nhỏ, chuyển payload vào value |
| Service khác không đọc được type metadata | Phụ thuộc special header/type Java của Spring | Dùng wire value String/byte[] trung lập |

## 18. Checklist thiết kế HeaderMapper

Trước khi phát hành luồng event, hãy xác nhận:

1. Header nào là metadata nghiệp vụ, header nào là metadata nội bộ framework?
2. Tên header có ổn định và dùng quy ước nhất quán không?
3. Giá trị header là String, byte[] hay object JSON?
4. Có cần DefaultKafkaHeaderMapper hay SimpleKafkaHeaderMapper?
5. Mapping patterns có loại trừ ID/timestamp và header nhạy cảm không?
6. Type metadata có tạo phụ thuộc class/package giữa producer và consumer không?
7. Raw mapping có quy định charset và wire format rõ không?
8. Converter của KafkaTemplate và listener container đã dùng mapper mong muốn chưa?
9. Có cần giữ duplicate headers hay map sang Spring MessageHeaders?
10. Header có nhỏ, không chứa secret và không trùng tên header hệ thống không?
11. Có test inbound/outbound và integration test với broker không?
12. Consumer đa ngôn ngữ có thể hiểu wire format mà producer gửi không?

`KafkaHeaderMapper` giúp Spring Kafka chuyển metadata giữa Kafka Headers và Spring MessageHeaders. `DefaultKafkaHeaderMapper` phù hợp khi cần map object header qua JSON và type metadata; `SimpleKafkaHeaderMapper` phù hợp với String/byte[] đơn giản, dễ tương tác liên ngôn ngữ. Khi chọn mapping patterns, raw format và converter một cách có chủ đích, ứng dụng có thể truyền correlation, trace và event metadata ổn định mà không làm header trở thành phụ thuộc vào class nội bộ hoặc nơi chứa payload lớn.

