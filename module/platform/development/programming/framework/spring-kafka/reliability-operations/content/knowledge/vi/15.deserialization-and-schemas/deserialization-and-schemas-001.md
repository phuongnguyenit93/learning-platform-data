# ErrorHandlingDeserializer

Trong Kafka, lỗi đọc dữ liệu không phải lúc nào cũng xảy ra trong phương thức **@KafkaListener**. Nếu các byte của record không thể được chuyển thành object Java, Kafka consumer có thể ném exception ngay trong bước **poll**, trước khi Spring Kafka gọi listener. Với consumer đọc liên tục, một record hỏng tại offset cố định có thể trở thành **poison pill**: consumer khởi động, poll đến record đó, lỗi, rồi vẫn không xử lý được các record phía sau.

**ErrorHandlingDeserializer** của Spring Kafka giải quyết khoảng trống giữa bước Kafka client deserialize và cơ chế xử lý lỗi của listener container. Nó bọc một deserializer thật (delegate), bắt lỗi từ delegate, giữ thông tin về lỗi và byte gốc trong metadata/header của record, rồi cho phép Spring Kafka container đưa lỗi qua **DefaultErrorHandler** và recovery policy thay vì mắc kẹt ở poll.

Trong chương **Deserialization và schema** của **Spring Kafka Reliability Operations**, đây là cấu hình quan trọng khi đọc JSON, Avro, Protobuf hoặc định dạng khác có schema. Mục tiêu không phải là bỏ qua dữ liệu hỏng bằng mọi giá, mà là **không làm đứng consumer, không âm thầm mất dữ liệu và có đủ bằng chứng để phục hồi**.

## 1. Lỗi xảy ra ở đâu trong consumer pipeline?

Một luồng xử lý record điển hình:

~~~mermaid
flowchart TD
    A["Kafka partition: key bytes + value bytes"] --> B["KafkaConsumer.poll()"]
    B --> C["Key deserializer + value deserializer"]
    C --> D["Spring Kafka listener container"]
    D --> E["Message converter / argument binding (nếu có)"]
    E --> F["@KafkaListener"]
    F --> G["Business service / downstream"]
~~~

Các bước có thể phát sinh những loại lỗi khác nhau:

| Vị trí | Ví dụ | Cơ chế cần xem |
|---|---|---|
| Poll / deserializer | JSON hỏng, Avro writer schema không tương thích, class không được trust | ErrorHandlingDeserializer, consumer error handling |
| Message conversion | Jackson chuyển object, header type mapping, conversion sang listener argument | Converter error handling, listener container |
| Listener invocation | Validation nghiệp vụ, NullPointerException, database timeout | DefaultErrorHandler, BackOff, DLT |
| Downstream | HTTP 503, deadlock database, hết connection pool | Retry có kiểm soát, idempotency, circuit breaker |
| Offset commit | Broker không khả dụng, consumer mất assignment | Commit/rebalance handling, monitoring |

**ErrorHandlingDeserializer giải quyết lỗi do delegate deserializer ném ra.** Nó không tự bắt mọi lỗi xảy ra ở các tầng sau. Nếu deserialization thành công nhưng business validation thất bại trong listener, lỗi đó đi theo luồng listener exception thông thường.

### 1.1 Tình huống không dùng ErrorHandlingDeserializer

Giả sử topic orders có các record sau:

| Partition | Offset | Dữ liệu | Kết quả |
|---|---:|---|---|
| orders-0 | 100 | JSON OrderCreated hợp lệ | Đọc được |
| orders-0 | 101 | JSON bị cắt giữa chừng | JsonDeserializer thất bại |
| orders-0 | 102 | JSON OrderCreated hợp lệ | Chưa tới listener |
| orders-0 | 103 | JSON OrderCreated hợp lệ | Chưa tới listener |

Với JsonDeserializer được Kafka consumer gọi trực tiếp, exception có thể xảy ra ngay trong poll. Container chưa nhận được ConsumerRecord hợp lệ cho offset 101 nên error handler dành cho lỗi listener không có record đầy đủ để xử lý như trường hợp business exception.

Nếu operator chỉ restart consumer, record 101 vẫn nằm trong log và lại có thể làm consumer lỗi tại cùng offset. Nếu operator tự seek sang 102 để thoát lỗi mà không lưu lại record gốc, record 101 có thể bị bỏ qua mà không có khả năng điều tra.

### 1.2 Khi dùng ErrorHandlingDeserializer

Thay vì để delegate exception thoát trực tiếp khỏi poll, wrapper:

1. Nhận byte từ Kafka client.
2. Gọi delegate deserializer đã cấu hình.
3. Nếu thành công, trả về key/value bình thường.
4. Nếu thất bại, giữ metadata lỗi trong Kafka record headers và trả về giá trị thay thế (mặc định thường là null).
5. Spring Kafka container nhận diện header lỗi và chuyển lỗi tới error handler theo cơ chế tương ứng.
6. Recoverer có thể ghi record vào DLT rồi cho consumer tiếp tục, hoặc giữ lại lỗi nếu recovery chưa thành công.

~~~mermaid
flowchart TD
    B["Byte[] từ Kafka"] --> W["ErrorHandlingDeserializer wrapper"]
    W --> D["Delegate: JsonDeserializer, Avro, ..."]
    D --> E{"Deserialize thành công?"}
    E -->|Có| V["Trả giá trị Java"]
    V --> L["Container / listener"]
    E -->|Không| H["Ghi DeserializationException và raw bytes vào header"]
    H --> N["Trả fallback/null"]
    N --> C["Spring Kafka container phát hiện header lỗi"]
    C --> EH["DefaultErrorHandler"]
    EH --> RC["Recoverer / DLT / retry theo policy"]
~~~

Cơ chế này đưa vấn đề vào đường xử lý có offset và metadata, nơi ứng dụng có thể quyết định recovery một cách minh bạch.

## 2. ErrorHandlingDeserializer là wrapper, không phải parser

ErrorHandlingDeserializer không tự biết cách giải mã JSON, Avro hay Protobuf. Nó **ủy quyền** cho một deserializer chuyên trách.

Ví dụ:

~~~text
Kafka key bytes
  -> ErrorHandlingDeserializer
     -> StringDeserializer
        -> String key

Kafka value bytes
  -> ErrorHandlingDeserializer
     -> JsonDeserializer
        -> OrderCreated object
~~~

Khi delegate thành công, listener nhận kết quả như khi không có wrapper. Khi delegate thất bại, wrapper cung cấp cơ chế chuyển lỗi về Spring Kafka.

| Thành phần | Vai trò |
|---|---|
| ErrorHandlingDeserializer | Bọc delegate, bắt deserialization exception và lưu thông tin lỗi |
| StringDeserializer | Chuyển key bytes sang String |
| JsonDeserializer | Chuyển JSON bytes sang object Java |
| Avro/Protobuf deserializer | Dùng wire format và schema riêng để đọc record |
| DefaultErrorHandler | Quyết định retry, skip/recover và xử lý offset khi container phát hiện lỗi |
| DeadLetterPublishingRecoverer | Publish record không xử lý được sang topic đích |
| KafkaMessageListenerContainer | Điều phối poll, listener invocation, error handling và offset commit |

Đổi JSON deserializer thành Avro deserializer không làm thay đổi nguyên tắc của wrapper, nhưng class, cấu hình schema registry và các loại exception cụ thể có thể khác nhau.

## 3. Cấu hình Spring Boot với key và value delegates

Cấu hình một consumer đọc String key và JSON value:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092,kafka-3:9092
    consumer:
      group-id: order-projection-prod
      enable-auto-commit: false
      auto-offset-reset: earliest

      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer

      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer

        spring.json.value.default.type: com.example.orders.OrderCreated
        spring.json.trusted.packages: com.example.orders
        spring.json.use.type.headers: false

    listener:
      ack-mode: record
~~~

Trong ví dụ này:

- Kafka consumer gọi ErrorHandlingDeserializer ở **cả key lẫn value**.
- Mỗi wrapper biết delegate cần gọi qua property tương ứng.
- Value delegate là JsonDeserializer.
- Khi producer không cung cấp Spring type headers phù hợp, cấu hình JSON cho phép chỉ định type đích rõ ràng.
- Trusted packages được giới hạn vào package model được phép; không mở rộng tùy tiện thành mọi package.
- Container quản lý offset vì auto commit đã tắt; ack mode được chọn theo mô hình record listener.

Các class **OrderCreated** và package **com.example.orders** chỉ là minh họa, cần thay theo contract ứng dụng thật.

### 3.1 Các property quan trọng

| Property | Ý nghĩa |
|---|---|
| spring.kafka.consumer.key-deserializer | Deserializer Kafka client gọi cho key; dùng ErrorHandlingDeserializer khi cần bọc key |
| spring.kafka.consumer.value-deserializer | Deserializer Kafka client gọi cho value; dùng ErrorHandlingDeserializer khi cần bọc value |
| spring.deserializer.key.delegate.class | Deserializer thật dùng để chuyển key bytes |
| spring.deserializer.value.delegate.class | Deserializer thật dùng để chuyển value bytes |
| spring.json.value.default.type | Type mặc định cho JSON value nếu phù hợp với cách dùng type headers |
| spring.json.trusted.packages | Giới hạn package được phép deserialize theo cấu hình Spring JSON |
| spring.json.use.type.headers | Quyết định sử dụng metadata type headers theo hợp đồng payload |

Các key có dấu chấm nằm trong khối **consumer.properties** được truyền tới deserializer delegate. Chúng không phải cấu hình của broker. Nếu dùng framework version mới có cấu hình Java hoặc type mapping khác, cần ưu tiên contract thực tế của hệ thống.

### 3.2 Chỉ bọc value có đủ không?

Nếu key luôn là String hợp lệ, có thể bọc value trước. Tuy nhiên, key deserialization cũng có thể thất bại, ví dụ khi key dùng một định dạng custom hoặc producer gửi bytes không hợp lệ theo hợp đồng.

Nếu chỉ value được bọc:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
~~~

Lỗi của key delegate không có ErrorHandlingDeserializer bọc sẽ không đi theo cùng cơ chế header recovery. Với hệ thống cần chống poison-pill cho cả key và value, nên đánh giá việc bọc cả hai.

## 4. Cấu hình bằng Java

Khi dự án tự tạo ConsumerFactory, có thể cung cấp delegate trực tiếp thay vì chỉ khai báo class name.

Ví dụ cấu trúc:

~~~java
@Bean
ConsumerFactory<String, OrderCreated> orderConsumerFactory() {

    Map<String, Object> props = new HashMap<>();

    props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
              "kafka-1:9092,kafka-2:9092,kafka-3:9092");
    props.put(ConsumerConfig.GROUP_ID_CONFIG,
              "order-projection-prod");
    props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,
              false);

    ErrorHandlingDeserializer<String> keyDeserializer =
        new ErrorHandlingDeserializer<>(
            new StringDeserializer()
        );

    JsonDeserializer<OrderCreated> jsonDeserializer =
        new JsonDeserializer<>(OrderCreated.class);

    ErrorHandlingDeserializer<OrderCreated> valueDeserializer =
        new ErrorHandlingDeserializer<>(jsonDeserializer);

    return new DefaultKafkaConsumerFactory<>(
        props,
        keyDeserializer,
        valueDeserializer
    );
}
~~~

Ví dụ giả định model OrderCreated đã được định nghĩa. Cấu hình JsonDeserializer có thể cần thêm type mapping, trusted packages và cách xử lý type headers theo hợp đồng producer-consumer.

Một nguyên tắc quan trọng: **chọn một cơ chế cấu hình delegate rõ ràng**. Nếu đã khởi tạo ErrorHandlingDeserializer bằng delegate object ở Java, không nên khai báo thêm delegate class mâu thuẫn trong properties nếu không có chủ đích. Hãy kiểm tra constructors và property binding của Spring Kafka version đang dùng.

### 4.1 Nhiều ConsumerFactory

Một ứng dụng có thể có ConsumerFactory cho JSON, Avro và plain text. Việc bật wrapper ở factory JSON không có nghĩa listener Avro cũng được bảo vệ.

Nên lập bản đồ theo từng listener:

~~~text
ordersListener   -> ordersFactory -> ErrorHandlingDeserializer + JsonDeserializer
paymentsListener -> avroFactory   -> ErrorHandlingDeserializer + AvroDeserializer
auditListener    -> textFactory   -> StringDeserializer (nếu được chấp nhận)
~~~

Mỗi factory cần kiểm tra key/value delegates, error handler, recoverer và DLT producer tương ứng.

## 5. Header chứa DeserializationException

Khi delegate ném exception, ErrorHandlingDeserializer lưu thông tin lỗi trong headers của record. Header được dùng để Spring Kafka container nhận diện việc deserialize thất bại và có thể bao gồm:

- Loại exception và nguyên nhân.
- Topic, key/value context.
- Byte dữ liệu gốc không chuyển được thành object.
- Metadata cần thiết cho error handling.

Header lỗi có thể tồn tại cho **key**, **value**, hoặc cả hai. Tên header và cách mã hóa được Spring Kafka định nghĩa bằng API nội bộ/public constants theo phiên bản; không nên tự tạo tên header theo phỏng đoán.

### 5.1 Value mặc định là null có phải tombstone?

Không nhất thiết.

Kafka compacted topic có thể chứa **tombstone**: record có value null hợp lệ để biểu thị xóa key. ErrorHandlingDeserializer cũng có thể trả về null khi value không deserialize được.

Phân biệt hai trường hợp:

| Trường hợp | Value ở ứng dụng | Có deserialization exception header? |
|---|---|---|
| Tombstone hợp lệ | null | Không, nếu delegate không lỗi |
| JSON null hợp lệ theo contract | Có thể null tùy delegate | Không, nếu deserialize thành công |
| Value deserialize thất bại | null theo fallback mặc định | Có |
| Failed-deserialization function trả object thay thế | Object tùy function | Vẫn cần xem metadata lỗi theo policy |

Với record listener thông thường, Spring Kafka container có thể chặn record lỗi trước khi gọi listener và đưa vào error handler. Với batch hoặc một số cách xử lý tùy biến, lập trình viên phải đặc biệt chú ý tránh nhầm null lỗi thành tombstone.

**Không dùng điều kiện value == null để kết luận record là hỏng** và cũng không dùng null để tự động xóa dữ liệu nếu chưa kiểm tra contract/metadata.

### 5.2 Metadata lỗi không phải business schema

Headers do ErrorHandlingDeserializer thêm vào phục vụ hạ tầng consumer. Chúng không nên trở thành một phần cố định của business event schema hoặc được copy bừa bãi qua mọi topic.

Khi forward message hoặc replay DLT:

- Giữ metadata nguồn để truy vết khi cần.
- Không để Java-serialized exception header bị một service khác tự deserialize không kiểm soát.
- Không phụ thuộc vào format header nội bộ giữa các phiên bản framework.
- Đảm bảo không lộ raw payload, stack trace hay thông tin nhạy cảm qua log/monitoring.

## 6. Kết hợp DefaultErrorHandler và DLT

ErrorHandlingDeserializer **không tự quyết định bỏ record hay gửi DLT**. Nó làm cho lỗi deserialize đi vào hệ thống error handling của Spring Kafka. Phải có recovery policy rõ ràng, đặc biệt khi record không thể xử lý hợp lệ.

Ví dụ dùng DefaultErrorHandler và DeadLetterPublishingRecoverer:

~~~java
@Configuration
public class OrderConsumerErrorConfiguration {

    @Bean
    DefaultErrorHandler orderErrorHandler(
            KafkaTemplate<Object, Object> dltKafkaTemplate) {

        DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(
                dltKafkaTemplate,
                (record, exception) -> new TopicPartition(
                    record.topic() + ".DLT",
                    record.partition()
                )
            );

        DefaultErrorHandler handler =
            new DefaultErrorHandler(
                recoverer,
                new FixedBackOff(0L, 0L)
            );

        return handler;
    }
}
~~~

Trong ví dụ trên, **FixedBackOff(0L, 0L)** nghĩa là không retry trước khi thử recovery theo handler. Chính sách này thường phù hợp cho payload hỏng cố định, vì gửi lại cùng bytes cho cùng delegate thường tiếp tục thất bại.

Tuy nhiên, nếu delegate thất bại vì một dependency tạm thời như schema registry không khả dụng, **không nên mặc định mọi lỗi đều là poison payload**. Cần phân loại và điều chỉnh chính sách để tránh flood DLT khi hạ tầng đang gặp sự cố.

### 6.1 Gắn error handler vào listener container factory

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
ordersListenerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        DefaultErrorHandler orderErrorHandler) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(orderErrorHandler);

    return factory;
}
~~~

Listener:

~~~java
@KafkaListener(
    id = "orders-consumer",
    topics = "orders",
    groupId = "order-projection-prod",
    containerFactory = "ordersListenerFactory"
)
public void onOrder(OrderCreated order) {
    projectionService.apply(order);
}
~~~

Nếu record không deserialize được và header lỗi được container nhận diện, listener không xử lý object hỏng như event hợp lệ. Error handler quyết định recovery. Nếu record hợp lệ nhưng projectionService.apply() ném exception, cùng handler có thể xử lý lỗi business theo classifier/backoff riêng.

### 6.2 Không coi log rồi bỏ qua là recovery đầy đủ

Nếu không cấu hình recoverer phù hợp, một số mặc định của handler có thể log exception và kết thúc xử lý lỗi theo policy. Điều này có thể giúp offset tiến triển nhưng khiến raw payload không còn được giữ ở một kênh điều tra dễ truy cập.

Với event quan trọng, hãy xác định rõ:

1. Record hỏng được lưu ở đâu?
2. Ai nhận cảnh báo?
3. Làm sao tìm raw bytes và contract/schema nguồn?
4. Làm sao replay khi sửa lỗi?
5. Recovery thất bại có ngăn offset tiến triển không?

Đừng xem “consumer không còn bị kẹt” là tiêu chí thành công duy nhất.

## 7. DLT producer phải serialize được raw bytes

Đây là điểm dễ sai nhất khi kết hợp ErrorHandlingDeserializer với DeadLetterPublishingRecoverer.

Khi lỗi value deserialization, payload lỗi không phải OrderCreated object hợp lệ. Để điều tra hoặc replay, Spring Kafka có thể publish **raw bytes của value gốc** sang DLT. Khi lỗi key, raw key bytes cũng có thể cần được giữ.

Do đó, DLT producer có thể phải gửi nhiều kiểu dữ liệu:

- **byte[]** cho key hoặc value không deserialize được.
- **String** cho key deserialize thành công.
- **OrderCreated** hoặc object hợp lệ cho record lỗi ở listener/business logic.

Nếu DLT KafkaTemplate chỉ cấu hình JsonSerializer hoặc StringSerializer cứng mà không xử lý byte[], việc publish DLT có thể thất bại hoặc làm biến đổi payload gốc.

### 7.1 Dùng serializer phân nhánh theo type

Một hướng triển khai là dùng **DelegatingByTypeSerializer** với ByteArraySerializer cho raw bytes và serializer tương ứng cho object hợp lệ.

Ví dụ minh họa:

~~~java
@Bean
ProducerFactory<Object, Object> dltProducerFactory() {

    Map<String, Object> props = new HashMap<>();
    props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
              "kafka-1:9092,kafka-2:9092,kafka-3:9092");
    props.put(ProducerConfig.ACKS_CONFIG, "all");

    Map<Class<?>, Serializer<?>> keySerializers =
        new LinkedHashMap<>();
    keySerializers.put(byte[].class, new ByteArraySerializer());
    keySerializers.put(String.class, new StringSerializer());

    Map<Class<?>, Serializer<?>> valueSerializers =
        new LinkedHashMap<>();
    valueSerializers.put(byte[].class, new ByteArraySerializer());
    valueSerializers.put(OrderCreated.class, new JsonSerializer<>());

    return new DefaultKafkaProducerFactory<>(
        props,
        new DelegatingByTypeSerializer(keySerializers),
        new DelegatingByTypeSerializer(valueSerializers)
    );
}

@Bean
KafkaTemplate<Object, Object> dltKafkaTemplate(
        ProducerFactory<Object, Object> dltProducerFactory) {

    return new KafkaTemplate<>(dltProducerFactory);
}
~~~

Đây là cấu trúc mẫu cho một contract chỉ có String key, OrderCreated value và raw byte[] khi deserialize thất bại. Trong ứng dụng thật, có thể cần thêm serializer cho các event type khác, null values, headers hoặc schema-aware serializer theo contract.

Khả năng khởi tạo DelegatingByTypeSerializer và type matching phải được kiểm tra theo Spring Kafka version cụ thể. Nếu ứng dụng đã có nhiều KafkaTemplates, cũng có thể thiết kế recoverer chọn template theo loại record.

### 7.2 Vì sao cần giữ raw bytes?

Raw bytes giúp:

- Xác định producer đã gửi những gì thật sự.
- So sánh payload với writer schema và reader schema.
- Khôi phục dữ liệu nếu bản sửa chỉ nằm ở consumer.
- Reprocess sau khi cập nhật type mapping hoặc schema registry.
- Phân biệt lỗi mạng/registry với payload cố định không hợp lệ.

Nếu DLT chỉ ghi một JSON chứa message “deserialize failed”, bản gốc có thể bị mất. Việc giữ raw bytes cần đi kèm ACL và quản lý dữ liệu nhạy cảm phù hợp.

### 7.3 DLT publish thất bại là lỗi nghiêm trọng

DLT topic cần đủ partition nếu recoverer giữ nguyên partition number:

~~~text
orders partition 3
       -> orders.DLT partition 3
~~~

Nếu orders.DLT chỉ có hai partition, publish vào partition 3 không hợp lệ.

Ngoài ra cần:

- Broker và DLT topic khả dụng.
- Quyền WRITE cho recovery producer.
- Serializer đúng cho type thực tế.
- Message size đủ cho raw payload và headers.
- ACK/durability phù hợp.
- Cơ chế nhận biết DLT send thất bại.

Đối với phiên bản hỗ trợ, có thể cấu hình recoverer kiểm tra kết quả send, chẳng hạn cơ chế **failIfSendResultIsError**, để tránh coi recovery thành công khi broker không xác nhận ghi DLT. Xác nhận semantics và timeout của API theo version dự án.

## 8. Lỗi key và lỗi value khác nhau thế nào?

Kafka record có key và value độc lập về mặt serialization. Cả hai có thể dùng schema hoặc serializer khác nhau.

### 8.1 Lỗi value deserialization

Ví dụ:

~~~text
topic: orders
partition: 0
offset: 501
key bytes: "order-1001"
value bytes: {"orderId":"order-1001","amount":
~~~

Key String có thể đọc được, nhưng JSON value bị cắt.

Khi value delegate thất bại:

- ErrorHandlingDeserializer cho value lưu metadata lỗi.
- Key vẫn có thể là String hợp lệ.
- Container có thể chuyển lỗi tới DefaultErrorHandler.
- Recoverer cần publish value gốc dạng byte[] nếu muốn giữ bản gốc.

### 8.2 Lỗi key deserialization

Ví dụ producer gửi binary key theo format riêng nhưng consumer cấu hình String hoặc schema-aware key deserializer không tương thích.

Nếu key delegate thất bại:

- Key Java có thể null theo fallback mặc định.
- Metadata lỗi key được lưu.
- Value Java có thể vẫn hợp lệ.
- Recoverer cần cân nhắc giữ raw key bytes để truy vết partitioning và business key.

Đừng chỉ cấu hình value ErrorHandlingDeserializer rồi giả định mọi lỗi deserialize đã được quản lý.

### 8.3 Nếu cả key và value lỗi

Một record có thể có cả hai metadata lỗi. Khi thu thập thông tin, cần ghi rõ trường nào thất bại, tránh chỉ log “value is null” rồi bỏ qua lỗi key.

Ở DLT, cần bảo toàn raw key/raw value theo khả năng của recoverer và serializers. Việc tái tạo business key phải được thực hiện cẩn thận; không được suy đoán key từ dữ liệu đã deserialize thất bại.

## 9. Lỗi schema: payload hỏng hay contract không tương thích?

Với JSON, Avro, Protobuf và các định dạng schema-aware, deserialization failure có thể đến từ nhiều nguyên nhân.

| Nhóm | Triệu chứng | Cách điều tra |
|---|---|---|
| Bytes hỏng | JSON thiếu dấu đóng, payload bị cắt | So sánh raw bytes, producer serializer và transport |
| Type mapping sai | Header chỉ tới class không tồn tại | Kiểm tra type headers, mapping và version consumer |
| Writer/reader schema không tương thích | Delegate không chuyển được field hoặc type | So sánh schema ID, versions, compatibility policy |
| Schema Registry không khả dụng | Deserializer không tải được schema | Kiểm tra network, registry health, cache và auth |
| JSON trusted package | Class type header bị từ chối | Kiểm tra allowed packages và producer contract |
| Dữ liệu hợp lệ về cú pháp nhưng sai nghiệp vụ | Amount âm, thiếu business key theo rule | Bean validation/business validation, không nhất thiết là deserialize failure |
| Cấu hình sai | Delegate class hoặc format mismatch | Kiểm tra ConsumerFactory và producer format |

**Không biến mọi schema error thành bài toán retry vô hạn.**

Nếu bytes vĩnh viễn không tương thích với schema consumer, thử lại cùng bytes với cùng cấu hình không giải quyết được. Recovery/DLT rồi sửa contract có thể phù hợp hơn.

Nếu lỗi do registry outage, lỗi có thể phục hồi khi registry trở lại. Chính sách route DLT ngay lập tức có thể gây flood DLT và không giúp dịch vụ hồi phục. Cần biết class/cause cụ thể và khả năng của deserializer để phân loại đúng.

### 9.1 ErrorHandlingDeserializer không thay Schema Registry

Với Avro/Protobuf hoặc JSON Schema từ một registry, ErrorHandlingDeserializer chỉ bọc deserializer schema-aware. Nó không:

- Đăng ký schema mới thay producer.
- Bỏ qua schema compatibility policy.
- Tự sửa writer/reader schema.
- Tự xác định business version đúng.
- Tự tải schema khi delegate không được cấu hình.
- Thay đổi wire format của topic.

Cần quản lý schema compatibility và rollout producer-consumer riêng. ErrorHandlingDeserializer là **cơ chế phát hiện và phục hồi khi giải mã thất bại**, không phải một công cụ migration schema.

### 9.2 Rollout schema an toàn

Một số thực hành:

1. Xác định format và schema của record đang tồn tại trong topic.
2. Kiểm tra compatibility cho cả producer mới và consumer cũ.
3. Deploy consumer có thể đọc cả phiên bản dữ liệu cũ/mới trước khi producer đổi format, nếu contract yêu cầu.
4. Kiểm tra deserialization metrics và DLT trước, trong, sau rollout.
5. Giữ raw data/event id để điều tra nếu xuất hiện record không tương thích.
6. Có kế hoạch rollback, vì rollback code không tự xóa record format mới đã được ghi vào Kafka.

## 10. Record listener: tránh gọi business logic cho payload lỗi

Với record listener thông thường, Spring Kafka container có thể phát hiện deserialization exception header và chuyển record tới error handler trước khi invoke listener.

Ví dụ:

~~~java
@Component
public class OrderProjectionListener {

    private final OrderProjectionService service;

    public OrderProjectionListener(OrderProjectionService service) {
        this.service = service;
    }

    @KafkaListener(
        topics = "orders",
        groupId = "order-projection-prod",
        containerFactory = "ordersListenerFactory"
    )
    public void handle(OrderCreated event) {
        service.apply(event);
    }
}
~~~

Nếu record hợp lệ, listener nhận OrderCreated. Nếu value delegate thất bại, đừng dựa vào việc listener sẽ nhận null rồi tự bỏ qua record; cơ chế container/error handler phải chịu trách nhiệm và cần được xác nhận trong integration test.

### 10.1 Không gộp lỗi dữ liệu và tombstone

Nếu topic compacted có tombstone hợp lệ, listener cần contract riêng cho null values. Null không tự đồng nghĩa với lỗi.

Với Spring Kafka, cơ chế binding argument của @KafkaListener khi xử lý null/tombstone có yêu cầu annotation/type riêng tùy phiên bản; ví dụ framework có KafkaNull để biểu thị value null trong một số conversion flow.

Hãy phân biệt:

- Null hợp lệ theo topic contract.
- Null do EHD thất bại và có exception header.
- Null do business mapping trả về.

Không silently acknowledge một record lỗi chỉ vì payload null.

## 11. Batch listener: cần đọc metadata lỗi có chủ đích

Với batch listener, một lần gọi có thể nhận nhiều records. Một số flow batch cho phép listener nhận danh sách có phần tử null và headers lỗi tại đúng index thay vì phát exception đơn lẻ trước khi gọi listener.

Ví dụ listener nhận ConsumerRecord để kiểm tra raw header:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-batch",
    containerFactory = "ordersBatchFactory"
)
public void handle(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (int i = 0; i < records.size(); i++) {
        ConsumerRecord<String, OrderCreated> record = records.get(i);

        Header failure = record.headers().lastHeader(
            SerializationUtils.VALUE_DESERIALIZER_EXCEPTION_HEADER
        );

        if (failure != null) {
            throw new BatchListenerFailedException(
                "Value deserialization failed at batch index " + i,
                i
            );
        }

        batchService.processOne(record.value());
    }
}
~~~

Đây là ví dụ khái niệm; import classes, constructor BatchListenerFailedException và cách framework đưa headers tới batch phụ thuộc Spring Kafka version. Một số batch listener nhận payload list và danh sách converted headers riêng qua KafkaHeaders.BATCH_CONVERTED_HEADERS.

**Batch index không phải Kafka offset.** Nếu batch có records từ nhiều partition, index là vị trí record trong list. Khi thông báo lỗi, cần dùng index đúng theo danh sách ban đầu để DefaultErrorHandler biết phần nào đã xử lý và phần nào cần recover.

### 11.1 Tránh lỗi thầm lặng ở batch

Một anti-pattern:

~~~java
for (OrderCreated order : orders) {
    if (order == null) {
        continue;
    }
    service.apply(order);
}
~~~

Đoạn code trên có thể bỏ qua một record không deserialize được mà không ghi DLT, không cảnh báo và không bảo toàn raw bytes. Nếu batch trả về thành công, container có thể commit offset của batch khiến record lỗi bị vượt qua.

Đối với batch chứa lỗi deserialize, cần chính sách rõ: ném BatchListenerFailedException kèm vị trí, hoặc dùng một recovery flow đúng với phiên bản framework đang chạy.

### 11.2 Phân biệt lỗi batch thường với deserialization failure

Nếu listener ném RuntimeException chung, DefaultErrorHandler có thể phải retry toàn batch khi không biết record lỗi. Khi biết record lỗi bằng index, BatchListenerFailedException giúp giảm phạm vi retry/recovery.

Điều này đặc biệt quan trọng nếu các record đứng trước đã tạo side effect. Retry cả batch có thể chạy lại những record đã xử lý thành công. Idempotency vẫn cần ngay cả với partial batch handling.

## 12. failedDeserializationFunction: trả giá trị fallback

ErrorHandlingDeserializer có cơ chế tùy chọn để cung cấp **failedDeserializationFunction**. Khi delegate thất bại, function có thể tạo một object đại diện cho thất bại dựa trên thông tin như topic, raw bytes và exception.

Cách dùng có thể hữu ích khi ứng dụng cần chuyển dữ liệu lỗi thành một domain envelope đặc biệt để xử lý có kiểm soát. Tuy nhiên, đây là lựa chọn có rủi ro.

Nếu function trả về một **OrderCreated giả** chỉ để tránh null, listener có thể:

- Tưởng rằng payload đã được deserialize hợp lệ.
- Tạo business side effect dựa trên dữ liệu không đáng tin cậy.
- Commit offset mà không gửi raw bytes vào DLT.
- Làm mất dấu hiệu dữ liệu bị hỏng nếu không kiểm tra metadata lỗi.

Vì vậy:

- Không dùng fallback để “sửa hộ” payload mơ hồ.
- Nếu chọn fallback object, nó nên là kiểu biểu diễn lỗi rõ ràng, không giả dạng event hợp lệ.
- Vẫn phải định nghĩa việc bảo toàn raw bytes và exception.
- Đảm bảo consumer/lifecycle thực sự xử lý header lỗi theo cách mong muốn.
- Kiểm thử với payload hỏng thật, không chỉ unit test function.

Với phần lớn consumer nghiệp vụ cần quarantine record lỗi, **ErrorHandlingDeserializer + DefaultErrorHandler + DLT** đơn giản và dễ kiểm toán hơn việc tự tạo fallback business object.

## 13. Validation sau deserialization

Deserialization thành công không có nghĩa event hợp lệ về nghiệp vụ.

Ví dụ JSON:

~~~json
{
  "orderId": "",
  "amount": -100,
  "currency": "USD"
}
~~~

JSON trên có thể parse thành OrderCreated thành công, nhưng không đạt validation rule của ứng dụng.

Cần phân biệt ba lớp:

1. **Wire format / schema parsing**: bytes có thể chuyển thành type mong đợi không?
2. **Structural validation**: các field bắt buộc và ràng buộc format có hợp lệ không?
3. **Business validation**: trạng thái/giá trị có được nghiệp vụ chấp nhận không?

Trong một số Spring Kafka version, ErrorHandlingDeserializer hỗ trợ tích hợp validator sau delegate; nếu validation thất bại, framework có thể lưu thông tin lỗi tương tự deserialization failure. Khả năng này tùy version và cần cấu hình chính xác.

Cách phổ biến hơn là validation trong service/listener:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-projection-prod"
)
public void onOrder(OrderCreated event) {

    orderValidator.validate(event);
    projectionService.apply(event);
}
~~~

Khi validation ném exception, DefaultErrorHandler áp dụng classifier và recoverer của listener. Ví dụ InvalidOrderPayloadException nên được phân loại non-retryable nếu payload tự nó không thể trở nên hợp lệ bằng retry.

Không trộn lẫn lỗi schema, lỗi validation và lỗi dependency; chúng thường cần policy khác nhau.

## 14. Retry có giúp deserialization error tự hết không?

Phần lớn payload hỏng cố định không tự thay đổi khi consumer retry. Nếu lỗi là:

~~~text
Invalid JSON at offset 501
~~~

thì đọc lại cùng byte[] ở offset 501 với cùng JsonDeserializer thường lại gặp lỗi tương tự.

Retry nhiều lần có thể làm:

- Consumer giữ partition lâu.
- Lag tăng.
- DLT chỉ nhận record sau nhiều delay vô ích.
- Log lặp lại gây nhiễu.
- Tăng tải schema registry hoặc các dependency khác.

Nhưng một số lỗi phụ thuộc trạng thái bên ngoài có thể là transient, ví dụ Schema Registry tạm thời timeout. Khi đó cần tìm root cause trước khi quyết định skip retry.

| Lỗi | Có nên retry? | Lý do |
|---|---|---|
| JSON hỏng cố định | Thường không | Bytes không đổi |
| Type không nằm trong trusted packages | Thường không | Cần sửa cấu hình/contract |
| Không tìm thấy reader class do deploy nhầm | Không thể tự sửa bằng retry đơn lẻ | Cần rollout code đúng |
| Schema Registry timeout | Có thể | Dependency có thể phục hồi |
| Registry trả về schema ID không tồn tại | Cần điều tra | Có thể sai registry/cluster hoặc dữ liệu hỏng |
| Network outage tạm thời | Có thể | Có cơ hội phục hồi khi kết nối trở lại |

Cần nhớ trong Spring Kafka, một số loại exception liên quan deserialization được classifier mặc định xem là fatal/non-retryable. Chính sách thực tế phải được xác minh trên version đang dùng. Nếu muốn retry lỗi registry tạm thời, đừng chỉ bật retry cho tất cả DeserializationException; nên có chiến lược phân loại nguyên nhân hoặc xử lý dependency phù hợp.

## 15. Offset commit sau khi record lỗi được recover

Một record không deserialize được vẫn chiếm offset trong Kafka log. Sau khi recovery thành công, ứng dụng thường cần tiến qua offset đó để xử lý record phía sau.

Giả sử:

~~~text
orders-0 offset 100: hợp lệ
orders-0 offset 101: JSON hỏng
orders-0 offset 102: hợp lệ
~~~

Một flow mong muốn:

1. Xử lý offset 100 thành công.
2. Khi đọc 101, ErrorHandlingDeserializer giữ lỗi.
3. DefaultErrorHandler gọi recoverer.
4. DLT được ghi thành công với raw bytes và metadata của 101.
5. Container áp dụng ack/commit policy để tiếp tục từ vị trí sau 101.
6. Listener xử lý offset 102.

Không tự giả định việc gọi recoverer đồng nghĩa offset chắc chắn đã commit ngay lập tức. AckMode, commitSync/commitAsync, container lifecycle và các tùy chọn như commitRecovered (khi áp dụng) ảnh hưởng commit timing.

### 15.1 DLT và committed offset là hai thao tác khác nhau

Kafka không tự bảo đảm atomicity giữa ghi DLT và commit offset consumer nếu chúng không được phối hợp trong một transaction thích hợp.

Các khoảng lỗi cần xét:

- DLT ghi xong, process chết trước offset commit: record 101 có thể được đọc lại và gửi DLT lần nữa.
- DLT publish thất bại nhưng handler xem là recovered: offset có thể tiến lên và record gốc không được quarantine như mong muốn.

Vì vậy phải bảo đảm recoverer phát hiện send failure và thiết kế DLT consumer/replay idempotent. Không tuyên bố exactly-once chỉ vì đã bật ErrorHandlingDeserializer.

### 15.2 Manual acknowledgment

Nếu listener dùng AckMode.MANUAL hoặc MANUAL_IMMEDIATE, recovery và commit offset cần được phối hợp theo semantics riêng. Không tự acknowledge record lỗi trong listener nếu listener không hề được gọi.

Với phiên bản/cấu hình hỗ trợ, DefaultErrorHandler có tùy chọn commit recovered record trong một số ack mode. Hãy kiểm tra contract và integration test trước khi bật.

## 16. Quan sát và cảnh báo

Tín hiệu quan trọng nhất là **tỷ lệ record không deserialize được**, nhưng riêng một metric không đủ để kết luận.

| Tín hiệu | Điều cần tìm |
|---|---|
| Deserialization failure rate | Mức lỗi theo topic, partition và consumer group |
| Exception class/root cause | JSON parse, schema mismatch, registry timeout, trusted package |
| DLT publish success/failure | Recovery thực sự có ghi được raw bytes không |
| Consumer lag | Partition có bị chặn bởi poison record không |
| Offset progression | Offset sau record lỗi có được xử lý không |
| Schema versions | Lỗi bắt đầu sau rollout producer/consumer nào |
| Retry attempts | Có retry vô ích hoặc retry storm không |
| Broker/registry availability | Có lỗi dependency diện rộng không |
| Recovery latency | Mất bao lâu từ lỗi deserialize đến lúc quarantine thành công |

Log nên chứa metadata, không cần full payload:

~~~text
listenerId=orders-consumer
groupId=order-projection-prod
topic=orders
partition=0
offset=501
errorStage=VALUE_DESERIALIZATION
exception=SerializationException
action=DLT_PUBLISH
dltTopic=orders.DLT
~~~

Nếu payload có dữ liệu cá nhân, tài chính hoặc bí mật, không ghi raw bytes vào application log. Lưu raw bytes trong DLT có chính sách ACL, retention, audit và quyền truy cập tương ứng.

### 16.1 Phân biệt một poison record với outage diện rộng

Nếu một offset duy nhất liên tục lỗi trong khi các partition khác khỏe, khả năng cao là payload/contract cụ thể có vấn đề.

Nếu hàng nghìn record trên nhiều topic cùng lỗi một lúc, hãy kiểm tra:

- Schema Registry.
- Security credentials/ACL.
- Producer vừa đổi format.
- Consumer vừa deploy class/schema mới.
- Environment profile hoặc registry URL bị sai.
- Broker/network health.

Không để một outage registry biến thành hàng nghìn DLT records trước khi operator phát hiện chính sách phân loại lỗi không phù hợp.

### 16.2 Kiểm tra DLT có thể replay

Một DLT có record nhưng không thể replay vì serializer đã biến đổi raw bytes hoặc schema ID đã mất cũng là một dạng thất bại phục hồi.

Nên ghi nhận:

- Original topic/partition/offset.
- Key/value raw bytes khi cần.
- Schema ID hoặc version nếu wire format có thông tin đó.
- Exception type.
- Thời điểm lỗi và phiên bản service.
- Kết quả replay hoặc trạng thái quarantine.

## 17. Quy trình điều tra khi gặp poison pill

Khi consumer báo lỗi deserialization hoặc không tiến qua một offset:

1. Xác định group id, topic, partition và offset đang lỗi.
2. Kiểm tra lỗi xảy ra trong poll, delegate deserializer, converter hay listener.
3. Xác nhận ConsumerFactory thực tế có cấu hình ErrorHandlingDeserializer ở key/value tương ứng.
4. Kiểm tra delegate class và cấu hình JSON/schema registry.
5. Thu thập exception class, nguyên nhân và metadata record.
6. Xác định record có thể phục hồi bằng retry hay là payload hỏng cố định.
7. Kiểm tra DefaultErrorHandler và recoverer/DLT của listener factory.
8. Xác nhận DLT producer serialize được byte[] khi value/key không deserialize được.
9. Kiểm tra topic DLT, partition, ACL, ACK và publish success.
10. Sau khi recovery, theo dõi committed offset và việc xử lý record phía sau.
11. Nếu nhiều record lỗi cùng lúc, kiểm tra rollout schema và registry/network trước khi chuyển hàng loạt dữ liệu vào DLT.
12. Lập kế hoạch sửa payload hoặc consumer và replay record đã quarantine.

Không sửa group offset trực tiếp trong production khi chưa biết dữ liệu nào đã bị bỏ qua. Một thao tác seek/reset có thể làm consumer chạy tiếp nhưng loại record khỏi quy trình audit và phục hồi.

## 18. Kiểm thử bằng payload hỏng thật

Cần có integration test qua Kafka broker thực tế hoặc Testcontainers. Unit test gọi trực tiếp @KafkaListener không đi qua deserializer của KafkaConsumer nên không chứng minh ErrorHandlingDeserializer hoạt động.

### 18.1 Test value JSON bị hỏng

Kịch bản:

1. Tạo topic orders và orders.DLT với partition phù hợp.
2. Cấu hình consumer dùng ErrorHandlingDeserializer + JsonDeserializer.
3. Dùng producer với ByteArraySerializer gửi bytes JSON hỏng vào value.
4. Giữ key hợp lệ.
5. Xác nhận listener business không xử lý record hỏng.
6. Xác nhận handler/recoverer được kích hoạt.
7. Đọc DLT bằng ByteArrayDeserializer, đối chiếu raw value bytes với dữ liệu gửi.
8. Xác nhận record hợp lệ phía sau vẫn được xử lý.
9. Kiểm tra offset và metadata nguồn.

Ví dụ dữ liệu test:

~~~text
key: order-1001
value bytes: {"orderId":"order-1001","amount":
~~~

### 18.2 Test key hỏng

- Dùng key serializer phát bytes không phù hợp với key delegate.
- Cấu hình key ErrorHandlingDeserializer.
- Xác nhận key exception được nhận diện.
- Xác nhận recovery lưu raw key bytes theo cấu hình.
- Xác nhận không mất value hợp lệ khi lỗi chỉ ở key.

### 18.3 Test tombstone hợp lệ

- Gửi record value null hợp lệ tới compacted topic hoặc test topic.
- Xác nhận không xuất hiện deserialization exception header.
- Xác nhận listener/tombstone handler xử lý null đúng contract.
- So sánh với record có JSON value hỏng.

### 18.4 Test lỗi Schema Registry

- Dùng schema-aware delegate.
- Giả lập registry không khả dụng trong môi trường cô lập.
- Xác nhận exception và chính sách retry/recovery như thiết kế.
- Khôi phục registry.
- Xác nhận record có thể xử lý hoặc quarantine theo policy.
- Không bật retry vô hạn vì lỗi hạ tầng.

### 18.5 Test DLT producer serializer

- Gửi payload hỏng.
- Cố ý cấu hình serializer DLT không hỗ trợ byte[] trong môi trường test.
- Xác nhận recovery failure được phát hiện.
- Sửa serializer/DelegatingByTypeSerializer.
- Xác nhận DLT nhận đúng raw bytes.
- Xác nhận không mất record khi DLT publish thất bại.

### 18.6 Test batch listener

- Poll batch có record hợp lệ và một record lỗi deserialize.
- Xác nhận listener nhận hoặc nhận diện exception metadata theo cơ chế batch của version đang dùng.
- Ném BatchListenerFailedException với index chính xác khi phù hợp.
- Xác nhận record trước lỗi không bị xử lý lại ngoài policy.
- Xác nhận record lỗi được recover và record phía sau tiếp tục.
- Kiểm tra duplicate side effect và commit offset theo partition.

## 19. Các hiểu nhầm cần tránh

**“ErrorHandlingDeserializer sửa được JSON hỏng.”** Không. Nó giữ thông tin lỗi và đưa record tới error handling; nó không tự thay đổi payload thành hợp lệ.

**“Bật ErrorHandlingDeserializer thì mọi lỗi listener đều được giải quyết.”** Không. Lỗi sau deserialize vẫn cần DefaultErrorHandler, BackOff và recovery policy.

**“Record lỗi sẽ tự động vào DLT.”** Không tự động. Cần cấu hình recoverer, KafkaTemplate, DLT topic và serializer phù hợp.

**“Value null luôn là tombstone.”** Sai. Value null có thể là fallback của một deserialization failure; cần phân biệt qua exception metadata.

**“Bọc value là đủ cho mọi trường hợp.”** Sai nếu key deserializer cũng có thể lỗi.

**“Gửi DLT bằng JsonSerializer luôn giữ nguyên raw bytes.”** Không bảo đảm. Cần serializer phù hợp byte[] và object hợp lệ.

**“Mọi deserialization error đều nên retry vài chục lần.”** Không. Payload không hợp lệ cố định thường không tự sửa sau retry.

**“Nếu consumer chạy tiếp nghĩa dữ liệu được bảo toàn.”** Không. Có thể record bị skip khi recovery chỉ log mà không lưu lại raw bytes.

**“Schema Registry outage giống payload hỏng.”** Không. Registry outage có thể là lỗi tạm thời của dependency và cần chính sách riêng.

**“Một lần DLT publish thành công nghĩa exactly-once.”** Không. Crash giữa DLT publish và offset commit vẫn có thể tạo duplicate DLT record.

**“Batch listener tự biết record nào lỗi giống record listener.”** Không luôn đúng. Cần kiểm tra header và failed index theo cách batch listener hoạt động.

## 20. Checklist thiết kế và vận hành

**Deserializer và schema**

- [ ] ConsumerFactory thật sự bọc key/value delegates cần bảo vệ.
- [ ] Delegate class và schema/type mapping được cấu hình đúng.
- [ ] Trusted packages được giới hạn đúng contract.
- [ ] Cấu hình schema registry được kiểm tra trên đúng môi trường.
- [ ] Phân biệt lỗi parse, lỗi registry và validation nghiệp vụ.

**Error handler và recovery**

- [ ] Listener container dùng DefaultErrorHandler/recoverer đúng factory.
- [ ] Lỗi không thể tự phục hồi không bị retry vô ích.
- [ ] Lỗi dependency tạm thời có policy phù hợp.
- [ ] DLT routing, ACL, partition và durability được thiết kế rõ.
- [ ] DLT producer hỗ trợ raw byte[] cho key/value lỗi.
- [ ] DLT publish failure không bị coi là recovery thành công.
- [ ] Committed offset và recovery outcome được đối chiếu.

**Dữ liệu và bảo mật**

- [ ] Raw bytes được bảo toàn khi cần replay.
- [ ] Exception headers không bị lạm dụng thành business contract.
- [ ] Không log payload nhạy cảm.
- [ ] DLT có retention, access control và quy trình xóa phù hợp.
- [ ] Có event id và metadata nguồn để đối chiếu duplicate.

**Kiểm thử và quan sát**

- [ ] Đã kiểm thử JSON/Avro/Protobuf bytes hỏng theo format thực tế.
- [ ] Đã kiểm thử lỗi key và lỗi value.
- [ ] Đã kiểm thử tombstone hợp lệ.
- [ ] Đã kiểm thử DLT serializer và send failure.
- [ ] Đã kiểm thử batch listener nếu ứng dụng dùng batch.
- [ ] Có metrics cho deserialize failures, DLT, lag và offset progression.
- [ ] Có runbook sửa schema, restore dependency và replay DLT.

**ErrorHandlingDeserializer** là ranh giới phục hồi giữa Kafka deserialization và Spring Kafka container error handling. Bằng cách bọc delegate, lưu exception cùng raw bytes trong metadata và cho phép handler xử lý record lỗi có kiểm soát, nó giúp giảm nguy cơ một poison pill làm đứng consumer. Độ tin cậy chỉ trọn vẹn khi kết hợp cấu hình schema đúng, recoverer/DLT bền vững, serializer hỗ trợ raw bytes, offset commit đúng thời điểm, idempotency và khả năng điều tra/replay trong production.

