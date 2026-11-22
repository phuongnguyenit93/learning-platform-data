# Mapping giữa Kafka record và Spring Message

Spring Kafka kết nối hai mô hình message khác nhau. Kafka client làm việc với record gồm key, value, topic, partition, offset, timestamp và các header dạng byte. Spring Messaging biểu diễn message bằng một payload cùng tập MessageHeaders. Message conversion là lớp cầu nối để ứng dụng có thể dùng @KafkaListener, KafkaTemplate, @Payload và @Header theo cách nhất quán với hệ sinh thái Spring.

Cần phân biệt message conversion với serialization/deserialization. Serializer và deserializer chuyển đổi dữ liệu giữa object và byte khi trao đổi với broker. Message converter chuyển đổi giữa Kafka ProducerRecord/ConsumerRecord và Spring Message<?>; converter cũng có thể thực hiện chuyển đổi payload, chẳng hạn JSON String thành một object Java. Hai lớp này phối hợp nhưng giải quyết hai nhiệm vụ khác nhau.

Trong ứng dụng Spring Kafka, bạn có thể nhận trực tiếp ConsumerRecord khi cần toàn quyền truy cập metadata của Kafka, hoặc nhận Message<T> khi muốn làm việc với payload và header theo mô hình Spring. Ở chiều gửi, KafkaTemplate.send(Message<?>) cho phép tạo ProducerRecord từ payload và các header của Spring Message.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Mô tả cấu trúc Kafka record và Spring Message<?>.
- Phân biệt serializer/deserializer với RecordMessageConverter.
- Giải thích cách MessagingMessageConverter ánh xạ payload và header giữa hai mô hình.
- Đọc topic, partition, offset, key và timestamp từ Spring Message headers.
- Dùng @Payload, @Header và @Headers trong @KafkaListener.
- Gửi message bằng KafkaTemplate.send(Message<?>) với topic, key và custom headers.
- Chọn default converter hoặc JSON message converter phù hợp với serializer/deserializer.
- Cấu hình converter cho listener container factory và KafkaTemplate.
- Hiểu cách xử lý batch message, native Kafka headers và lỗi chuyển đổi.
- Kiểm thử mapping và tránh mất metadata hoặc chuyển đổi payload hai lần.

## 1. Hai mô hình message

Kafka client làm việc với record. Một ConsumerRecord có các thông tin như:

- topic: tên topic chứa record.
- partition: partition chứa record.
- offset: vị trí của record trong partition.
- key: key sau khi deserializer chuyển đổi.
- value: payload sau khi deserializer chuyển đổi.
- timestamp: timestamp của record theo timestamp type.
- headers: tập Kafka Header, mỗi header có tên và giá trị byte.

Spring Messaging dùng interface Message<T>, gồm:

- payload: nội dung chính của message.
- headers: MessageHeaders, một map chỉ đọc chứa metadata và custom header.

Sơ đồ:

~~~text
Kafka ConsumerRecord / ProducerRecord
  topic, partition, offset, key, value, timestamp, Kafka Headers
                       |
                       | RecordMessageConverter
                       v
Spring Message<T>
  payload + MessageHeaders
~~~

Ví dụ cùng một sự kiện đơn hàng:

~~~text
Kafka record:
  topic     = orders
  partition = 2
  offset    = 105
  key       = order-100
  value     = OrderCreated(...)
  headers   = trace-id, event-source

Spring Message:
  payload = OrderCreated(...)
  headers = received topic, partition, offset, key,
            timestamp, trace-id, event-source
~~~

Spring Message không phải một record Kafka mới. Nó là biểu diễn message ở tầng ứng dụng, được tạo từ record hoặc dùng làm đầu vào để tạo record gửi đi.

## 2. Phân biệt serialization và message conversion

Đây là ranh giới quan trọng nhất khi cấu hình Spring Kafka.

| Lớp | Đầu vào | Đầu ra | Thành phần thường dùng |
|---|---|---|---|
| Serialization | Java key/value | byte[] | Serializer |
| Deserialization | byte[] | Java key/value | Deserializer |
| Inbound message conversion | ConsumerRecord | Spring Message<?> hoặc payload theo method signature | RecordMessageConverter |
| Outbound message conversion | Spring Message<?> | ProducerRecord | RecordMessageConverter |
| JSON payload conversion | JSON String/byte[] và kiểu Java đích | Java object hoặc JSON | StringJsonMessageConverter, ByteArrayJsonMessageConverter... |

Luồng nhận khi dùng JsonDeserializer:

~~~text
Kafka bytes
    |
    v
JsonDeserializer
    |
    v
OrderCreated object
    |
    v
MessagingMessageConverter
    |
    v
Message<OrderCreated>
    |
    v
@KafkaListener
~~~

Luồng nhận khi dùng StringJsonMessageConverter:

~~~text
Kafka bytes
    |
    v
StringDeserializer
    |
    v
JSON String
    |
    v
StringJsonMessageConverter
    |
    v
OrderCreated object / Message<OrderCreated>
    |
    v
@KafkaListener
~~~

Hai cách trên là hai lựa chọn khác nhau. Nếu JsonDeserializer đã tạo OrderCreated, không cần thêm StringJsonMessageConverter để parse lại JSON. Ngược lại, nếu dùng StringJsonMessageConverter, key/value deserializer thường trả về String hoặc byte[] để converter xử lý JSON.

Message converter không thay thế serializer/deserializer của Kafka client. Broker vẫn lưu byte; việc đổi byte thành object ở phía consumer luôn cần deserializer hoặc converter chạy sau deserializer.

## 3. RecordMessageConverter và MessagingMessageConverter

Spring Kafka định nghĩa RecordMessageConverter để chuyển đổi giữa Kafka record và Spring Message.

Hai chiều chính:

- toMessage(...): chuyển ConsumerRecord thành Message<?> cho listener.
- fromMessage(...): chuyển Message<?> thành ProducerRecord để gửi.

MessagingMessageConverter là implementation phổ biến. Nó chuyển payload và ánh xạ metadata/header giữa Kafka record với Spring MessageHeaders.

Trong ứng dụng thông thường, listener container sử dụng converter để tạo đối số cho listener. KafkaTemplate sử dụng converter khi gọi overload send(Message<?>).

Một số implementation và biến thể JSON thường gặp:

| Converter | Mục đích |
|---|---|
| MessagingMessageConverter | Ánh xạ Kafka record và Spring Message; payload thường giữ kiểu do serializer/deserializer cung cấp |
| BatchMessagingMessageConverter | Chuyển đổi một batch ConsumerRecords thành message/list payload phù hợp batch listener |
| StringJsonMessageConverter | Chuyển JSON String và Java object |
| ByteArrayJsonMessageConverter | Chuyển JSON byte[] và Java object |
| BytesJsonMessageConverter | Chuyển Kafka Bytes và Java object |

Tên class và API chi tiết có thể thay đổi theo phiên bản Spring Kafka. Hãy dùng converter tương thích với phiên bản dependency của ứng dụng.

## 4. Inbound conversion: ConsumerRecord thành Spring Message

Khi listener nhận tham số Message<T>, Spring Kafka container chuyển ConsumerRecord thành Message<?> trước khi gọi method.

Ví dụ listener:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-service"
)
public void listen(Message<OrderCreated> message) {
    OrderCreated event = message.getPayload();

    String topic = message.getHeaders()
            .get(KafkaHeaders.RECEIVED_TOPIC, String.class);

    Integer partition = message.getHeaders()
            .get(KafkaHeaders.RECEIVED_PARTITION, Integer.class);

    Long offset = message.getHeaders()
            .get(KafkaHeaders.OFFSET, Long.class);

    orderService.process(event);
}
~~~

Trong ví dụ, payload là OrderCreated đã được deserializer tạo ra hoặc message converter chuyển đổi. Các thông tin về vị trí record được đặt trong Spring Message headers.

Một số header Kafka thường dùng ở chiều nhận:

| KafkaHeaders constant | Ý nghĩa |
|---|---|
| RECEIVED_TOPIC | Topic nhận record |
| RECEIVED_PARTITION | Partition nhận record |
| OFFSET | Offset của record |
| RECEIVED_KEY | Key đã deserialize của record |
| RECEIVED_TIMESTAMP | Timestamp của record |
| ACKNOWLEDGMENT | Đối tượng acknowledgement nếu listener/container mode cung cấp |
| CONSUMER | Kafka Consumer gắn với lần nhận record trong một số kiểu listener |

Header có thể không xuất hiện trong mọi kiểu listener hoặc mọi phiên bản/configuration. Nếu cần metadata chính xác cho logic quan trọng, hãy kiểm tra header có tồn tại và dùng đúng kiểu dữ liệu.

### Lấy metadata bằng @Header

Không nhất thiết phải nhận toàn bộ Message<?>. Có thể khai báo payload và từng header riêng:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-service"
)
public void listen(
        @Payload OrderCreated event,
        @Header(KafkaHeaders.RECEIVED_TOPIC) String topic,
        @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
        @Header(KafkaHeaders.OFFSET) long offset,
        @Header(name = KafkaHeaders.RECEIVED_KEY, required = false)
        String key) {

    log.info(
        "Received order {} from {}-{} at offset {} with key {}",
        event.orderId(), topic, partition, offset, key
    );

    orderService.process(event);
}
~~~

Dùng required = false với header có thể không tồn tại, chẳng hạn key null. Với header bắt buộc, có thể để Spring báo lỗi nếu thiếu, nhưng cần bảo đảm record producer luôn gửi metadata đó.

### Lấy tất cả Spring Message headers

Có thể nhận map header:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-service"
)
public void listen(
        @Payload OrderCreated event,
        @Headers Map<String, Object> headers) {

    Object traceId = headers.get("trace-id");
    Object topic = headers.get(KafkaHeaders.RECEIVED_TOPIC);

    orderService.process(event);
}
~~~

@Headers cung cấp các header mà Spring message converter đưa vào MessageHeaders. Đây không phải Kafka Headers nguyên bản; nếu cần đọc mọi native header hoặc header trùng tên, hãy nhận ConsumerRecord và đọc record.headers().

## 5. Khi nào nên nhận Message<T> và khi nào nhận ConsumerRecord?

Cả hai kiểu đều hữu ích, tùy nhu cầu của listener.

| Kiểu tham số | Phù hợp khi | Lợi ích |
|---|---|---|
| Payload trực tiếp, ví dụ OrderCreated | Chỉ cần dữ liệu nghiệp vụ | Method đơn giản, ít phụ thuộc metadata |
| Message<OrderCreated> | Cần payload và Spring headers | Dễ dùng @Header, MessageHeaders và mô hình Spring |
| ConsumerRecord<String, OrderCreated> | Cần toàn bộ metadata Kafka hoặc native headers | Truy cập trực tiếp topic, partition, offset, timestamp, key và headers |
| List<ConsumerRecord<...>> | Batch listener cần metadata từng record | Kiểm soát đầy đủ từng record trong batch |

Ví dụ nhận ConsumerRecord:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-service"
)
public void listen(ConsumerRecord<String, OrderCreated> record) {
    log.info(
        "topic={}, partition={}, offset={}, key={}",
        record.topic(),
        record.partition(),
        record.offset(),
        record.key()
    );

    orderService.process(record.value());
}
~~~

Khi method nhận ConsumerRecord, ứng dụng làm việc trực tiếp với record Kafka. Không cần chuyển metadata qua Spring Message headers. Đây là lựa chọn rõ ràng cho logic cần native metadata, kiểm tra timestamp type hoặc xử lý header có tên lặp.

Không nhận ConsumerRecord chỉ để lấy payload nếu listener không dùng metadata; kiểu payload trực tiếp thường dễ đọc hơn.

## 6. Outbound conversion: Spring Message thành Kafka record

Ở chiều gửi, KafkaTemplate hỗ trợ send(Message<?>). Converter đọc payload và các header đặc biệt để tạo ProducerRecord.

Ví dụ:

~~~java
@Service
public class OrderPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {

        Message<OrderCreated> message = MessageBuilder
                .withPayload(event)
                .setHeader(KafkaHeaders.TOPIC, "orders")
                .setHeader(KafkaHeaders.MESSAGE_KEY, event.orderId())
                .setHeader("trace-id", event.traceId())
                .setHeader("event-source", "checkout")
                .build();

        return kafkaTemplate.send(message);
    }
}
~~~

Ví dụ dùng API Spring Kafka 3.x, trong đó send() trả về CompletableFuture. Với Spring Kafka 2.x, kiểu future của API gửi có thể là ListenableFuture.

Các header điều khiển record gửi đi:

| KafkaHeaders constant | Vai trò |
|---|---|
| TOPIC | Topic đích |
| MESSAGE_KEY | Key của record |
| PARTITION | Partition đích nếu muốn chỉ định tường minh |
| TIMESTAMP | Timestamp gửi cùng record nếu được hỗ trợ/cấu hình |

Nếu không có TOPIC trong message, KafkaTemplate cần có default topic được cấu hình để xác định đích. Để code dễ đọc và tránh gửi nhầm, nên đặt topic tường minh trong message hoặc dùng default topic có chủ đích.

Không tự đặt header RECEIVED_TOPIC để chọn topic gửi đi. Dùng KafkaHeaders.TOPIC cho outbound và KafkaHeaders.RECEIVED_TOPIC để đọc metadata inbound.

### Chỉ định partition và timestamp

Có thể chỉ định partition khi nghiệp vụ cần định tuyến tường minh:

~~~java
Message<OrderCreated> message = MessageBuilder
        .withPayload(event)
        .setHeader(KafkaHeaders.TOPIC, "orders")
        .setHeader(KafkaHeaders.PARTITION, 2)
        .setHeader(KafkaHeaders.MESSAGE_KEY, event.orderId())
        .build();

kafkaTemplate.send(message);
~~~

Khi đặt partition, ứng dụng chịu trách nhiệm bảo đảm partition tồn tại và mapping này phù hợp với yêu cầu ordering. Thông thường nên để partitioner chọn partition từ key, trừ khi có lý do rõ ràng để chỉ định trực tiếp.

Timestamp có thể đặt bằng KafkaHeaders.TIMESTAMP nếu cần gửi timestamp do ứng dụng quản lý. Broker/topic có thể sử dụng CreateTime hoặc LogAppendTime; vì vậy timestamp nhận được cần được hiểu theo timestamp type thực tế của record.

## 7. Custom Kafka headers và header mapper

Kafka record header lưu tên header và giá trị byte[]. Spring MessageHeaders có thể lưu String, số, object hoặc kiểu Java khác. KafkaHeaderMapper chuyển đổi giữa hai mô hình header này.

Sơ đồ:

~~~text
Spring MessageHeaders
  trace-id = "trace-123"
  retry-count = 2
  event-source = "checkout"
           |
           v
      KafkaHeaderMapper
           |
           v
Kafka Headers
  trace-id      -> bytes
  retry-count   -> bytes
  event-source  -> bytes
~~~

Ở chiều nhận, mapper chuyển Kafka Headers trở lại các giá trị trong MessageHeaders. Kiểu dữ liệu được khôi phục phụ thuộc mapper, metadata kiểu và cấu hình mapping.

DefaultKafkaHeaderMapper hỗ trợ ánh xạ header có chuyển đổi kiểu. SimpleKafkaHeaderMapper phù hợp khi muốn làm việc gần với byte[] hơn. Hãy chọn mapper dựa trên cách các hệ thống producer/consumer trao đổi header.

Ví dụ cấu hình mapper cho converter:

~~~java
@Bean
public RecordMessageConverter recordMessageConverter() {
    MessagingMessageConverter converter =
            new MessagingMessageConverter();

    converter.setHeaderMapper(new DefaultKafkaHeaderMapper());

    return converter;
}
~~~

Trong hệ thống nhiều ngôn ngữ hoặc producer không dùng Spring, custom header có thể đến dưới dạng byte[] thay vì kiểu Java ban đầu. Hãy định nghĩa encoding rõ ràng, ví dụ UTF-8 cho trace-id, và kiểm tra kiểu dữ liệu trước khi cast.

### Không gửi mọi header nội bộ của Spring một cách tùy tiện

Spring MessageHeaders có các header nội bộ như id và timestamp. Không phải mọi header của Spring đều có ý nghĩa với consumer Kafka. Header mapper thường có quy tắc lọc và mapping riêng; nếu tự cấu hình pattern, hãy tránh vô tình gửi metadata nội bộ hoặc dữ liệu nhạy cảm.

Chỉ đưa vào Kafka những header cần thiết cho tracing, correlation, routing hoặc nghiệp vụ. Tránh đưa token, thông tin xác thực, dữ liệu cá nhân hoặc object tùy ý vào header. Kafka header là metadata đi cùng record và có thể được nhiều consumer đọc.

### Kafka headers có thể trùng tên

Kafka Headers cho phép nhiều header cùng tên. Spring MessageHeaders là map nên một key chỉ có một giá trị. Nếu cần giữ mọi giá trị trùng tên hoặc thứ tự native headers, hãy đọc trực tiếp ConsumerRecord.headers() thay vì dựa vào map Spring đã chuyển đổi.

## 8. JSON message conversion

Khi ứng dụng dùng JSON, có hai cách phổ biến để chuyển payload.

### Cách A: Kafka JsonSerializer và JsonDeserializer

Producer dùng JsonSerializer để biến Java object thành byte[]. Consumer dùng JsonDeserializer để tạo lại object. Default MessagingMessageConverter sau đó bọc object cùng metadata vào Spring Message.

Cấu hình minh họa:

~~~yaml
spring:
  kafka:
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        "[spring.json.value.default.type]": com.example.events.OrderCreated
        "[spring.json.trusted.packages]": com.example.events
~~~

Listener:

~~~java
@KafkaListener(topics = "orders", groupId = "order-service")
public void listen(Message<OrderCreated> message) {
    OrderCreated event = message.getPayload();
    orderService.process(event);
}
~~~

Trong cách này, JSON được xử lý bởi Kafka JsonSerializer/JsonDeserializer. Message converter chủ yếu ánh xạ ConsumerRecord thành Spring Message và chuyển header.

### Cách B: StringJsonMessageConverter

Producer serialize payload thành JSON String qua message converter; Kafka client dùng StringSerializer để ghi String thành byte[]. Consumer dùng StringDeserializer để nhận String, sau đó StringJsonMessageConverter chuyển JSON thành kiểu Java listener yêu cầu.

Cấu hình serializer/deserializer:

~~~yaml
spring:
  kafka:
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
~~~

Cấu hình converter cho listener factory:

~~~java
@Bean
public RecordMessageConverter jsonMessageConverter() {
    return new StringJsonMessageConverter();
}

@Bean
public ConcurrentKafkaListenerContainerFactory<String, String>
        orderListenerFactory(
                ConsumerFactory<String, String> consumerFactory,
                RecordMessageConverter jsonMessageConverter) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, String>();

    factory.setConsumerFactory(consumerFactory);
    factory.setRecordMessageConverter(jsonMessageConverter);

    return factory;
}
~~~

Cấu hình converter cho KafkaTemplate:

~~~java
@Bean
public KafkaTemplate<String, String> orderKafkaTemplate(
        ProducerFactory<String, String> producerFactory,
        RecordMessageConverter jsonMessageConverter) {

    KafkaTemplate<String, String> template =
            new KafkaTemplate<>(producerFactory);

    template.setMessageConverter(jsonMessageConverter);

    return template;
}
~~~

Gửi payload Java object bằng Spring Message:

~~~java
Message<OrderCreated> message = MessageBuilder
        .withPayload(event)
        .setHeader(KafkaHeaders.TOPIC, "orders")
        .setHeader(KafkaHeaders.MESSAGE_KEY, event.orderId())
        .build();

orderKafkaTemplate.send(message);
~~~

Listener nhận object:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-service",
    containerFactory = "orderListenerFactory"
)
public void listen(OrderCreated event) {
    orderService.process(event);
}
~~~

Ở chiều gửi, StringJsonMessageConverter chuyển payload object thành JSON String trước khi Kafka StringSerializer chạy. Ở chiều nhận, StringDeserializer tạo String rồi converter chuyển String thành OrderCreated theo kiểu đích của listener.

Không cấu hình JsonDeserializer cùng StringJsonMessageConverter cho cùng value path nếu không có thiết kế đặc biệt. Nếu JsonDeserializer đã chuyển JSON thành object, StringJsonMessageConverter không còn đầu vào String để parse.

### Chọn cách nào?

| Tiêu chí | JsonSerializer/JsonDeserializer | StringJsonMessageConverter |
|---|---|---|
| JSON bytes được tạo/parse bởi | Kafka serializer/deserializer | Spring message converter kết hợp String serializer/deserializer |
| Listener nhận object | Có | Có |
| Dùng KafkaTemplate.send(Message<?>) | Có, với converter mặc định bọc payload object | Có, converter biến payload thành JSON String |
| Phù hợp khi | Muốn cấu hình serialization ở Kafka client | Muốn conversion gắn với Spring Message và listener method |
| Tương tác với producer không dùng Spring | Theo định dạng JSON và type metadata đã thống nhất | Theo định dạng JSON String đã thống nhất |

Điều quan trọng là producer và consumer phải thống nhất wire format. Một producer ngoài Spring có thể gửi JSON UTF-8 mà consumer dùng StringDeserializer + StringJsonMessageConverter đọc được, miễn schema và kiểu payload tương thích.

## 9. Chọn kiểu payload đích cho listener

Khi dùng JSON message converter, converter cần biết kiểu Java đích để parse JSON. Spring Kafka có thể suy ra kiểu từ tham số listener, ví dụ:

~~~java
@KafkaListener(topics = "orders", groupId = "order-service")
public void listen(OrderCreated event) {
    orderService.process(event);
}
~~~

Hoặc:

~~~java
@KafkaListener(topics = "orders", groupId = "order-service")
public void listen(Message<OrderCreated> message) {
    orderService.process(message.getPayload());
}
~~~

Nếu listener chỉ nhận Object hoặc generic type không cụ thể, converter có thể không đủ thông tin để suy ra kiểu đích. Khi đó, hãy dùng type metadata, cấu hình target type phù hợp hoặc một listener method có kiểu cụ thể.

Với topic chứa nhiều loại event, không nên giả định mọi record đều là OrderCreated. Có thể dùng type header, event type discriminator trong payload hoặc tách topic/listener theo loại sự kiện. Hãy validate type trước khi gọi nghiệp vụ.

## 10. Batch message conversion

Khi listener container chạy batch mode, một lần poll có thể trả về nhiều ConsumerRecord. Spring Kafka có BatchMessagingMessageConverter để chuyển đổi batch thành payload dạng danh sách và cung cấp metadata theo batch.

Ví dụ batch listener nhận payload list:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-batch-service",
    containerFactory = "batchOrderListenerFactory"
)
public void listen(List<OrderCreated> events) {
    orderService.processBatch(events);
}
~~~

Nếu cần metadata cho từng record, có thể dùng List<ConsumerRecord<String, OrderCreated>> để giữ đầy đủ record gốc hoặc dùng cấu trúc header dành cho batch conversion như KafkaHeaders.BATCH_CONVERTED_HEADERS khi làm việc với Message<List<?>>.

Batch conversion có một số khác biệt so với record listener:

- Payload thường là danh sách.
- Metadata của từng record cần được giữ theo từng phần tử, không chỉ một header đơn cho cả batch.
- Một batch có thể chứa record từ nhiều partition.
- Khi xử lý lỗi một phần, cần xác định record nào thành công và offset nào an toàn để commit.

Nếu ứng dụng cần native header và offset chính xác cho từng record, nhận danh sách ConsumerRecord thường dễ kiểm soát hơn.

## 11. Mapping header và metadata trong thực tế

Một số metadata thường được sử dụng trong listener:

~~~java
@KafkaListener(topics = "orders", groupId = "order-service")
public void listen(
        @Payload OrderCreated event,
        @Header(KafkaHeaders.RECEIVED_TOPIC) String topic,
        @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
        @Header(KafkaHeaders.OFFSET) long offset,
        @Header(name = KafkaHeaders.RECEIVED_KEY, required = false)
        String key,
        @Header(name = "trace-id", required = false) String traceId) {

    log.info(
        "topic={}, partition={}, offset={}, key={}",
        topic, partition, offset, key
    );

    orderService.process(event, traceId);
}
~~~

Các giá trị này hữu ích cho log và tracing:

- topic + partition + offset xác định duy nhất vị trí record trong một topic-partition.
- key cho biết record được định tuyến theo thực thể nào.
- timestamp hỗ trợ phân tích thời gian tạo/ghi record.
- trace-id nối log producer, broker và consumer.
- eventId hỗ trợ deduplicate nghiệp vụ.

Không dùng offset làm event ID toàn cục. Offset chỉ duy nhất trong một partition; cùng số offset có thể xuất hiện ở partition khác hoặc topic khác. Nếu cần định danh record theo vị trí Kafka, kết hợp topic, partition và offset. Nếu cần định danh nghiệp vụ, dùng eventId.

## 12. Lỗi xảy ra ở tầng nào?

Cần xác định lỗi xuất hiện trước hay sau message conversion để chọn cách xử lý.

| Tầng lỗi | Ví dụ | Nơi thường xử lý |
|---|---|---|
| Deserialization | Byte không hợp lệ, JSON không parse được bởi JsonDeserializer | ErrorHandlingDeserializer và listener container error handler |
| Message conversion | StringJsonMessageConverter không chuyển được JSON sang kiểu listener | Listener container error handler |
| Header mapping | Header có kiểu không hỗ trợ hoặc metadata không đúng định dạng | Header mapper/custom conversion và error handling |
| Listener method | Business exception khi xử lý payload | CommonErrorHandler/retry/DLT theo cấu hình |
| Outbound conversion | Thiếu topic header hoặc payload không chuyển đổi được | Producer call/application error handling |
| Kafka serialization | Serializer không chuyển object thành byte | Kafka producer callback/future hoặc exception khi send |

Deserializer chạy trước RecordMessageConverter. Nếu JsonDeserializer thất bại, converter không thể sửa payload vì ConsumerRecord chưa có value Java hợp lệ. Với lỗi deserialization, cân nhắc ErrorHandlingDeserializer để chuyển lỗi thành metadata mà container error handler có thể xử lý.

Nếu converter nhận được String nhưng JSON không hợp lệ, đó là lỗi message conversion. Nếu converter tạo payload thành công nhưng nghiệp vụ thất bại, đó là lỗi listener. Phân biệt các tầng này giúp log và retry đúng nơi.

### Không che giấu lỗi bằng payload Object

Nhận payload Object có thể giúp một listener xử lý nhiều kiểu event, nhưng cũng làm lỗi kiểu dữ liệu xuất hiện muộn ở runtime. Nếu topic có schema xác định, hãy dùng kiểu cụ thể hoặc validate event type trước khi xử lý.

## 13. Raw record và tombstone/null payload

Kafka compacted topic có thể chứa tombstone: record có key nhưng value là null để biểu thị việc xóa trạng thái của key trong quá trình compaction.

Spring Message thông thường yêu cầu payload không null. Vì vậy, nếu consumer phải phân biệt tombstone với event có payload, nhận ConsumerRecord là lựa chọn rõ ràng:

~~~java
@KafkaListener(topics = "customer-state", groupId = "customer-state-reader")
public void listen(ConsumerRecord<String, CustomerState> record) {
    if (record.value() == null) {
        customerService.deleteState(record.key());
        return;
    }

    customerService.updateState(record.key(), record.value());
}
~~~

Đừng giả định một Message<T> thông thường luôn biểu diễn được mọi trường hợp null value của Kafka. Hãy kiểm thử tombstone theo converter và listener signature đang sử dụng.

## 14. Cấu hình converter theo listener container factory

Mỗi listener container factory có thể sử dụng RecordMessageConverter riêng. Điều này hữu ích khi một ứng dụng có nhiều topic với wire format khác nhau.

Ví dụ factory mặc định dùng converter cơ bản:

~~~java
@Bean
public RecordMessageConverter defaultRecordMessageConverter() {
    return new MessagingMessageConverter();
}
~~~

Factory dùng JSON String conversion:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, String>
        jsonStringListenerFactory(
                ConsumerFactory<String, String> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, String>();

    factory.setConsumerFactory(consumerFactory);
    factory.setRecordMessageConverter(new StringJsonMessageConverter());

    return factory;
}
~~~

Listener chọn factory phù hợp:

~~~java
@KafkaListener(
    id = "orders-json-listener",
    topics = "orders",
    groupId = "order-service",
    containerFactory = "jsonStringListenerFactory"
)
public void listen(OrderCreated event) {
    orderService.process(event);
}
~~~

Factory cần có ConsumerFactory với deserializer phù hợp. Trong ví dụ JSON String, value deserializer cần trả về String. Nếu dùng JsonDeserializer, hãy chọn converter tương ứng với object đã deserialize.

Không dùng chung một converter cho nhiều wire format nếu converter đó giả định kiểu payload cụ thể. Đặt tên factory và converter theo định dạng hoặc domain giúp cấu hình dễ hiểu hơn.

## 15. Kiểm thử mapping Kafka record và Spring Message

Kiểm thử cần xác nhận cả payload lẫn metadata.

Các kịch bản hữu ích:

- Gửi một record và nhận Message<T>; xác nhận payload đúng kiểu.
- Xác nhận RECEIVED_TOPIC, RECEIVED_PARTITION, OFFSET, RECEIVED_KEY và RECEIVED_TIMESTAMP được map đúng.
- Gửi custom header trace-id và event-source; xác nhận consumer đọc được giá trị và kiểu mong muốn.
- Gửi Message<?> bằng KafkaTemplate.send(Message<?>) và xác nhận TOPIC, MESSAGE_KEY, PARTITION được áp dụng đúng.
- Dùng StringJsonMessageConverter với StringSerializer/StringDeserializer và xác nhận JSON thành object.
- Dùng JsonSerializer/JsonDeserializer với MessagingMessageConverter mặc định và xác nhận không parse payload hai lần.
- Kiểm tra header trùng tên qua ConsumerRecord.headers().
- Kiểm tra batch listener giữ metadata theo từng record.
- Gửi tombstone/null value và xác nhận listener xử lý đúng.
- Gửi JSON sai định dạng để phân biệt deserialization error với message conversion error.
- Kiểm tra producer ngoài Spring gửi JSON UTF-8 và Spring consumer đọc được theo wire format đã thống nhất.

Với integration test, nên dùng EmbeddedKafka hoặc Testcontainers để xác nhận record thật qua broker. Unit test converter có thể kiểm tra mapping cục bộ nhưng không thay thế kiểm thử serializer/deserializer và header trên wire.

## 16. Các lỗi thường gặp

**Nhầm serializer với message converter.** JsonSerializer tạo byte; MessagingMessageConverter tạo Spring Message từ record. Chọn đúng lớp cho nhiệm vụ.

**Dùng JsonDeserializer cùng StringJsonMessageConverter.** Deserializer đã tạo object nhưng converter lại mong đợi JSON String. Dùng một chiến lược chuyển đổi nhất quán.

**Quên đặt KafkaHeaders.TOPIC khi gửi Message.** KafkaTemplate không biết đích gửi nếu không có default topic. Đặt topic rõ ràng hoặc cấu hình default topic.

**Dùng RECEIVED_TOPIC để gửi.** Đây là metadata inbound. Dùng TOPIC cho outbound.

**Ép kiểu header không an toàn.** Header từ producer khác có thể là byte[] hoặc kiểu khác. Kiểm tra kiểu và encoding trước khi cast.

**Cho rằng mọi Kafka header đều nằm nguyên vẹn trong MessageHeaders.** Mapper có thể chuyển kiểu hoặc gộp header trùng tên. Dùng ConsumerRecord.headers() khi cần native headers.

**Dùng Object cho mọi payload.** Listener mất kiểm tra kiểu ở compile time và có thể lỗi muộn. Dùng kiểu cụ thể hoặc validate discriminator.

**Bỏ qua tombstone.** Null value có ý nghĩa trong compacted topic. Nhận raw ConsumerRecord nếu cần phân biệt key và null value.

**Không phân biệt lỗi deserializer và converter.** Mỗi lỗi xảy ra ở một giai đoạn khác nhau. Chọn ErrorHandlingDeserializer hoặc container error handler đúng vị trí.

## 17. Checklist thiết kế message conversion

- [ ] Đã xác định wire format và serializer/deserializer của producer/consumer.
- [ ] Đã phân biệt serialization với RecordMessageConverter.
- [ ] Listener nhận payload, Message<T> hay ConsumerRecord theo nhu cầu thực tế.
- [ ] Metadata inbound dùng đúng KafkaHeaders.RECEIVED_* và OFFSET.
- [ ] Outbound message dùng TOPIC, MESSAGE_KEY và các header tùy chọn đúng kiểu.
- [ ] Custom header có encoding và chính sách mapping rõ ràng.
- [ ] Header nhạy cảm hoặc header nội bộ không bị phát tán ngoài ý muốn.
- [ ] Converter tương thích với kiểu value mà deserializer trả về.
- [ ] JSON conversion không bị thực hiện hai lần.
- [ ] Batch listener giữ metadata theo từng record.
- [ ] Tombstone/null payload được xử lý có chủ đích.
- [ ] Deserialization, message conversion và business error có cách xử lý riêng.
- [ ] Có integration test xác nhận payload, headers và metadata qua broker.

## Kết luận

Message conversion là cầu nối giữa Kafka record và Spring Message<?>. RecordMessageConverter chuyển ConsumerRecord thành Spring Message ở chiều nhận và Spring Message thành ProducerRecord ở chiều gửi. MessagingMessageConverter thường dùng để ánh xạ payload và metadata; các JSON message converter có thể chuyển JSON String/byte[] thành kiểu Java. Hãy phân biệt rõ serializer/deserializer với message converter, dùng đúng KafkaHeaders cho inbound và outbound, chọn listener signature theo nhu cầu metadata, và kiểm thử cả payload lẫn headers. Khi cần raw Kafka metadata, duplicate headers hoặc tombstone, ConsumerRecord vẫn là lựa chọn phù hợp để giữ đầy đủ ngữ nghĩa của record gốc.

