# Dead letter cho lỗi định dạng

Trong hệ thống Spring Kafka, một record không nhất thiết đi tới `@KafkaListener` dưới dạng một đối tượng Java hợp lệ. Kafka lưu **key và value dưới dạng byte**, còn consumer phải deserialize, chuyển đổi kiểu dữ liệu và kiểm tra schema trước khi gọi nghiệp vụ. Nếu payload bị cắt, JSON không hợp lệ, thiếu type information hoặc schema không tương thích, lỗi có thể phát sinh **ngay trong `poll()` hoặc trong tầng chuyển đổi message**, trước cả khi phương thức listener được thực thi.

**Dead letter cho lỗi định dạng** là cơ chế cô lập record không thể đọc hoặc không tuân thủ hợp đồng dữ liệu vào Dead Letter Topic (DLT), giữ được payload và thông tin nguồn để điều tra. Khi thiết kế đúng, một poison record không làm toàn bộ consumer mắc kẹt ở cùng offset, nhưng cũng không bị loại bỏ âm thầm khiến dữ liệu không còn truy vết được.

Trọng tâm của bài là phối hợp `ErrorHandlingDeserializer`, `DefaultErrorHandler`, `DeadLetterPublishingRecoverer` và serializer của DLT. Retry hay DLT chỉ là một phần: còn phải quyết định lỗi nào có thể phục hồi, cách giữ nguyên raw bytes và quy trình sửa lỗi/replay.

## 1. Lỗi định dạng xảy ra ở những tầng nào?

Luồng tiêu thụ thông thường có các bước:

```text
Kafka broker lưu key/value bytes
           |
           v
KafkaConsumer.poll()
           |
           v
KeyDeserializer / ValueDeserializer
           |
           v
Spring Kafka message converter / argument resolver
           |
           v
@KafkaListener method
           |
           v
Validation và xử lý nghiệp vụ
```

Không phải mọi lỗi có tên “format” đều xảy ra ở cùng một vị trí. Nơi phát sinh lỗi quyết định framework có `ConsumerRecord` và raw payload để chuyển vào DLT hay chưa.

| Tầng | Ví dụ lỗi | Biện pháp cần xem xét |
|---|---|---|
| Kafka deserializer | Byte không phải JSON hợp lệ, Avro framing lỗi, enum không chuyển được | Dùng `ErrorHandlingDeserializer` để lỗi có thể đi vào container error handler |
| Schema/serialization registry | Schema ID không tồn tại, schema không tương thích, registry timeout | Phân biệt lỗi payload vĩnh viễn với lỗi dependency tạm thời |
| Spring message conversion | Header type sai, converter không chuyển sang tham số listener | `DefaultErrorHandler` và recoverer; lưu metadata type/schema |
| Listener argument resolution | Payload không khớp method signature | Sửa contract/method và lưu record lỗi để điều tra |
| Bean validation hoặc domain validation | Trường bắt buộc thiếu, giá trị ngoài miền hợp lệ | Phân loại rõ lỗi dữ liệu, business rejection và lỗi tạm thời |

Ví dụ value là chuỗi byte `{"orderId":` bị thiếu dấu đóng. `JsonDeserializer` có thể ném exception ngay khi consumer poll. Một payload JSON có thể hợp lệ về cú pháp nhưng `orderId` không có trong domain model; khi đó lỗi có thể chỉ xuất hiện khi converter hoặc listener validation chạy. Vì vậy, xử lý lỗi định dạng phải bao phủ **cả lỗi trước và sau deserialization**.

## 2. Vì sao consumer có thể mắc kẹt trước listener?

Nếu cấu hình Kafka consumer dùng thẳng `JsonDeserializer` hoặc một deserializer tự định nghĩa, lỗi trong `deserialize()` có thể làm `KafkaConsumer.poll()` ném exception. Container chưa nhận được record đã deserialize để giao cho listener. Chỉ thêm `try/catch` bên trong `@KafkaListener` sẽ không giải quyết được lỗi này, vì method có thể chưa được gọi.

Ví dụ cấu hình dễ gặp vấn đề:

```properties
spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.consumer.value-deserializer=org.springframework.kafka.support.serializer.JsonDeserializer
```

Khi một record chứa byte lỗi, container có thể liên tục gặp lại lỗi tại vị trí đọc đó. Error handler không thể luôn xử lý bằng seek thông thường nếu không có một `ConsumerRecord` hợp lệ để định danh record thất bại. Một record độc hại như vậy có thể cản trở tiến độ xử lý các record phía sau.

Spring Kafka cung cấp `ErrorHandlingDeserializer` để **bọc deserializer thật**. Nó bắt `DeserializationException` từ delegate, lưu thông tin lỗi trong header và cho container có cơ hội xử lý record thất bại qua cơ chế error handler thay vì chỉ nhận một exception từ `poll()`.

## 3. Cấu hình `ErrorHandlingDeserializer`

Ví dụ consumer nhận key dạng chuỗi và value JSON ánh xạ vào `OrderCreated`. Value deserializer được bọc bằng `ErrorHandlingDeserializer`, còn `JsonDeserializer` là delegate:

```properties
spring.kafka.consumer.enable-auto-commit=false

spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.consumer.value-deserializer=org.springframework.kafka.support.serializer.ErrorHandlingDeserializer

spring.kafka.consumer.properties[spring.deserializer.value.delegate.class]=org.springframework.kafka.support.serializer.JsonDeserializer
spring.kafka.consumer.properties[spring.json.value.default.type]=com.example.events.OrderCreated
spring.kafka.consumer.properties[spring.json.trusted.packages]=com.example.events
```

Trong ví dụ, `com.example.events.OrderCreated` là class ứng dụng giả định. Class thực tế, trusted packages, type headers và schema phải khớp producer. Không dùng `spring.json.trusted.packages=*` một cách tùy tiện trong production; chỉ cho phép các package cần thiết và kiểm soát nguồn dữ liệu.

Khi delegate deserialize thất bại, `ErrorHandlingDeserializer` ghi nhận exception trong header của record. Container nhận diện header liên quan rồi đưa record lỗi vào error handler. Với `DeadLetterPublishingRecoverer`, payload thô của record lỗi có thể được khôi phục để publish vào DLT thay vì chỉ publish một value `null` mất dữ liệu.

### 3.1. Lỗi deserialization ở key

Key cũng có thể lỗi, chẳng hạn producer dùng key dạng binary nhưng consumer kỳ vọng một JSON key hoặc UUID. Nếu key deserializer có thể thất bại, cần bọc **cả key và value**, không chỉ value:

```properties
spring.kafka.consumer.key-deserializer=org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
spring.kafka.consumer.value-deserializer=org.springframework.kafka.support.serializer.ErrorHandlingDeserializer

spring.kafka.consumer.properties[spring.deserializer.key.delegate.class]=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.consumer.properties[spring.deserializer.value.delegate.class]=org.springframework.kafka.support.serializer.JsonDeserializer
```

`StringDeserializer` nhận nhiều chuỗi byte UTF-8 mà không ném lỗi với mọi dữ liệu có ký tự bất thường; ví dụ trên minh họa cách bọc key chứ không chứng minh mọi chuỗi key sai định dạng sẽ bị phát hiện. Muốn kiểm tra quy tắc key cụ thể, cần custom deserializer/validator phù hợp.

Nếu key deserialize thất bại, DLT publisher có thể phải ghi **raw key `byte[]`**, không phải `String`. Vì vậy, thiết kế serializer DLT phải xem xét cả key lẫn value lỗi.

### 3.2. Lỗi xuất phát từ schema registry

Khi dùng Avro, Protobuf hoặc JSON Schema với registry, delegate của `ErrorHandlingDeserializer` có thể là deserializer từ thư viện registry thay vì `JsonDeserializer`. Về nguyên tắc:

```text
ErrorHandlingDeserializer
          |
          v
Deserializer thực tế (Avro / Protobuf / JSON Schema)
          |
          +--> decode thành công --> listener
          |
          +--> lỗi -------------> exception header --> error handler
```

Cấu hình delegate, schema registry URL, authentication và subject naming strategy phụ thuộc thư viện serialization được chọn. Không áp dụng các property dành riêng cho `JsonDeserializer` của Spring Kafka như thể chúng điều khiển Avro hay Protobuf. Cần phân biệt **schema ID thực sự sai/không còn tồn tại** với **schema registry tạm thời mất kết nối**: lỗi dependency có thể cần retry hoặc tạm dừng consumer thay vì đưa một lượng lớn event hợp lệ vào DLT.

## 4. Từ exception tới DLT với `DefaultErrorHandler`

Sau khi `ErrorHandlingDeserializer` làm cho lỗi deserialization đi qua cơ chế error handling của container, `DefaultErrorHandler` quyết định retry và recovery. Với dữ liệu sai cú pháp hoặc schema xác định không hỗ trợ, retry lại cùng byte thường không có ích. Trong các phiên bản Spring Kafka hiện đại, một số exception như `DeserializationException`, `MessageConversionException`, `ConversionException`, `MethodArgumentResolutionException`, `NoSuchMethodException` và `ClassCastException` được phân loại là fatal/not-retryable theo mặc định; danh sách chính xác cần đối chiếu phiên bản.

Một cấu hình minh họa:

```java
@Bean
DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> dltKafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(
                    dltKafkaTemplate,
                    (record, exception) -> new TopicPartition(
                            record.topic() + ".DLT",
                            record.partition()));

    // Recoverer báo lỗi nếu gửi DLT không thành công.
    recoverer.setFailIfSendResultIsError(true);

    DefaultErrorHandler handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L));

    // Đối với lỗi contract do ứng dụng tự định nghĩa:
    handler.addNotRetryableExceptions(
            UnsupportedMessageSchemaException.class,
            InvalidMessageFormatException.class);

    return handler;
}
```

Trong ví dụ, lỗi còn retryable có tối đa hai lần retry sau lần xử lý đầu tiên; lỗi được đánh dấu not-retryable đi trực tiếp tới recoverer. Các exception domain là class minh họa của ứng dụng. `DeadLetterPublishingRecoverer` publish record lỗi sang `<source-topic>.DLT` với partition đích bằng partition nguồn; DLT phải có **ít nhất số partition tương ứng** để resolver không gửi tới partition không tồn tại.

`setFailIfSendResultIsError(true)` yêu cầu recoverer báo lỗi khi Kafka send đến DLT thất bại ở các phiên bản hỗ trợ, thay vì xem thao tác recovery đã thành công. Cần cấu hình timeout gửi hợp lý, quan sát broker acknowledgment và bảo đảm topic/ACL/serializer hợp lệ. Nếu recovery thất bại, offset nguồn không được đối xử như record đã recover thành công.

### 4.1. Gắn handler đúng listener factory

```java
@Bean(name = "orderListenerContainerFactory")
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
orderListenerContainerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        DefaultErrorHandler orderErrorHandler) {

    ConcurrentKafkaListenerContainerFactory<String, OrderCreated> factory =
            new ConcurrentKafkaListenerContainerFactory<>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(orderErrorHandler);
    factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.RECORD);

    return factory;
}

@KafkaListener(
        topics = "orders",
        groupId = "order-processing",
        containerFactory = "orderListenerContainerFactory")
public void handleOrder(OrderCreated event) {
    orderService.processIdempotently(event);
}
```

Listener `handleOrder()` không cần tự bắt một JSON deserialization exception. Với payload không thể deserialize, method thường không được gọi; container/error handler sẽ xử lý record qua exception header. Listener vẫn chịu trách nhiệm validation nghiệp vụ, idempotency và ném exception cụ thể nếu dữ liệu đã decode nhưng không hợp lệ.

Không cấu hình `acknowledge()` trong `finally` như cách "bỏ qua" record lỗi. Việc commit offset phải theo chính sách acknowledgment và recovery của container; hoàn tất recovery không có nghĩa yêu cầu nghiệp vụ đã thành công.

## 5. DLT serializer: giữ nguyên raw bytes khi payload hỏng

Đây là điểm dễ sai nhất khi triển khai dead letter cho lỗi định dạng. Trong luồng xử lý thông thường, producer gửi một object `OrderCreated` và `JsonSerializer` chuyển nó thành byte. Khi deserialization của consumer thất bại, `DeadLetterPublishingRecoverer` có thể khôi phục **raw bytes của payload lỗi** từ thông tin mà `ErrorHandlingDeserializer` lưu lại.

Nếu DLT `KafkaTemplate` luôn dùng `JsonSerializer<OrderCreated>`, nó có thể không xử lý raw `byte[]` theo cách mong muốn. Ngược lại, nếu luôn dùng `ByteArraySerializer`, nó sẽ không phù hợp khi record thất bại ở tầng listener nhưng value vẫn là một object domain đã deserialize. Vì vậy, DLT có thể nhận ít nhất hai dạng value:

| Nguồn lỗi | Dữ liệu đưa tới DLT publisher | Serializer thường cần |
|---|---|---|
| Value deserialization thất bại | Raw value `byte[]` được khôi phục | `ByteArraySerializer` |
| Key deserialization thất bại | Raw key `byte[]` được khôi phục | `ByteArraySerializer` cho key |
| Exception trong listener sau deserialize | Value là object Java hợp lệ | `JsonSerializer`, Avro serializer hoặc serializer của contract tương ứng |
| Record có key/value hỗn hợp nhiều kiểu | Key hoặc value tùy runtime type | Serializer phân loại theo kiểu hoặc nhiều template |

Trong Spring Kafka, `DelegatingByTypeSerializer` có thể chọn serializer theo **runtime type**. Ví dụ sau minh họa DLT template hỗ trợ raw bytes cho record hỏng và JSON cho object đã deserialize (cần bổ sung import thông thường):

```java
@Bean
ProducerFactory<Object, Object> dltProducerFactory(
        KafkaProperties kafkaProperties) {

    Map<String, Object> props =
            new HashMap<>(kafkaProperties.buildProducerProperties());

    Map<Class<?>, Serializer<?>> keySerializers = new LinkedHashMap<>();
    keySerializers.put(byte[].class, new ByteArraySerializer());
    keySerializers.put(String.class, new StringSerializer());

    Map<Class<?>, Serializer<?>> valueSerializers = new LinkedHashMap<>();
    valueSerializers.put(byte[].class, new ByteArraySerializer());
    valueSerializers.put(Object.class, new JsonSerializer<>());

    return new DefaultKafkaProducerFactory<>(
            props,
            new DelegatingByTypeSerializer(keySerializers, true),
            new DelegatingByTypeSerializer(valueSerializers, true));
}

@Bean
KafkaTemplate<Object, Object> dltKafkaTemplate(
        @Qualifier("dltProducerFactory")
        ProducerFactory<Object, Object> producerFactory) {
    return new KafkaTemplate<>(producerFactory);
}
```

Ở đây, `byte[]` được chọn trước `Object.class`; tham số `true` cho phép match kiểu có khả năng gán được. `Object.class` là fallback minh họa cho object JSON và không phù hợp nếu ứng dụng dùng nhiều serialization format khác nhau. Với Avro/Protobuf/Schema Registry, cần serializer tương ứng hoặc các DLT template riêng. Khi dự án có producer config bảo mật/tính bền vững từ Spring Boot, bảo đảm `KafkaProperties` thật sự kế thừa đủ TLS/SASL, acks, retries và thông số khác; API `buildProducerProperties` có thể thay đổi overload theo phiên bản Spring Boot.

Với key không phải String hay `byte[]`, cần bổ sung serializer của key tương ứng. DLT publisher phải xử lý được *cả hai trường hợp* key/value hỏng và không hỏng. Nếu chọn sai serializer, chính recovery sẽ thất bại và record lỗi vẫn làm consumer bị chặn.

## 6. Khi record đi vào DLT, cần giữ những thông tin nào?

Record DLT cần mang đủ provenance để trả lời: record lỗi đến từ đâu, byte gốc là gì, lỗi ở tầng nào và có thể replay bằng cách nào. `DeadLetterPublishingRecoverer` bổ sung các header chỉ nguồn và exception. Các hằng như `KafkaHeaders.DLT_ORIGINAL_TOPIC`, `KafkaHeaders.DLT_ORIGINAL_PARTITION`, `KafkaHeaders.DLT_ORIGINAL_OFFSET` giúp truy xuất một phần thông tin này; hệ thống cũng có thể sử dụng các header lỗi và timestamp tương ứng.

Ví dụ một bản ghi DLT:

```text
Kafka record hiện tại:
  topic: orders.DLT
  partition: 3
  offset: 824
  value: 7b 22 6f 72 64 65 72 49 64 22 3a ... (bytes lỗi)

Thông tin nguồn:
  original topic: orders
  original partition: 3
  original offset: 241
  exception class: ...DeserializationException

Thông tin nghiệp vụ (nếu producer cung cấp):
  event-id: evt-7b82
  schema-version: 5
  correlation-id: req-4902
```

Offset 824 thuộc **DLT**, còn offset 241 thuộc topic nguồn; cả hai là tọa độ khác nhau. DLT cũng có retention độc lập nên không thể giả định bản ghi lỗi sẽ tồn tại mãi mãi.

Các exception header nội bộ của `ErrorHandlingDeserializer` có thể chứa dữ liệu exception được serialization theo cơ chế Spring Kafka. `DeadLetterPublishingRecoverer` có quy tắc riêng về việc khôi phục payload và giữ/xóa các header lỗi nội bộ trước khi publish DLT, tùy phiên bản và cấu hình. Đừng xây hệ thống vận hành phụ thuộc vào việc có thể đọc được mọi header nội bộ bằng UTF-8. Hãy dùng metadata DLT được hỗ trợ, bảo lưu event ID và khi cần có thể bổ sung header ứng dụng rõ nghĩa.

Không log toàn bộ raw payload hoặc stack trace chứa thông tin cá nhân, token hay secret. Truy cập DLT phải được phân quyền; retention phù hợp thời gian điều tra và quy định bảo mật.

## 7. Lỗi JSON sai cú pháp so với schema không tương thích

Hai loại lỗi này thường cùng tạo ra deserialization/conversion exception nhưng cách khắc phục khác nhau.

### 7.1. JSON sai cú pháp

Payload:

```json
{"orderId": "ORD-100", "amount":
```

Đây là JSON chưa hoàn chỉnh. Retry lại cùng bytes sẽ không làm nó hợp lệ. DLT cần giữ raw bytes để producer owner tìm nguyên nhân: lỗi serialization, truncation trước khi publish hay một producer gửi sai contract.

Nếu dữ liệu quan trọng và có thể tái tạo từ nguồn đáng tin cậy, nhóm vận hành có thể sửa nguồn hoặc phát event mới đúng format. Không tự “chắp vá” bytes trên production nếu chưa rõ ý nghĩa nghiệp vụ và quy trình audit.

### 7.2. JSON hợp lệ nhưng không khớp Java model

Payload:

```json
{"orderId": "ORD-100", "amount": "not-a-number"}
```

JSON hợp lệ về cú pháp nhưng có thể không chuyển được sang `BigDecimal` hoặc object domain theo cấu hình. Nguyên nhân có thể là producer đổi contract hoặc consumer thiếu một mapping. Khắc phục bằng sửa producer/schema, cập nhật consumer tương thích hoặc quy trình chuyển đổi được kiểm soát.

### 7.3. Schema ID/version không còn tương thích

Với Avro/Protobuf/JSON Schema qua registry, payload có thể được mã hóa đúng nhưng consumer không thể giải mã vì schema ID bị thiếu, phiên bản không tương thích hoặc registry không sẵn sàng. Các trường hợp này **không đồng nghĩa nhau**:

- Schema ID không tồn tại hoặc framing bị hỏng: thường không thể tự hết chỉ bằng retry.
- Consumer chưa hỗ trợ phiên bản event mới: cần nâng cấp consumer hoặc áp dụng chiến lược schema compatibility.
- Registry tạm thời mất kết nối: có thể phục hồi sau khi dependency trở lại; cần backoff/circuit breaker thay vì mặc định gửi tất cả vào DLT.
- Credential/ACL registry sai: cần sửa vận hành; retry liên tục có thể gây storm.

Đừng gộp tất cả exception của schema registry thành “dữ liệu hỏng vĩnh viễn”. Nếu một outage registry khiến hàng nghìn event hợp lệ bị gửi vào DLT, hệ thống sẽ tạo backlog khổng lồ và cần replay không đáng có. Classification phải dựa trên nguyên nhân và hậu quả nghiệp vụ.

## 8. Khi nào không retry, khi nào tạm dừng consumer?

`DefaultErrorHandler` hỗ trợ phân loại retryable/not-retryable. Đối với payload sai cú pháp đã được xác nhận, non-retry và DLT thường phù hợp. Đối với lỗi network tới registry hoặc dependency còn khả năng phục hồi, retry có backoff hoặc tạm dừng luồng có thể tốt hơn.

| Điều kiện | Chính sách đề xuất | Vì sao |
|---|---|---|
| Raw bytes không thể parse lặp lại | DLT ngay, không retry cùng payload | Lỗi dữ liệu không tự đổi |
| Unknown message type/version xác định | DLT/quarantine; cập nhật consumer rồi replay | Cần triển khai schema/code mới |
| Registry timeout vài giây | Retry hữu hạn, backoff và cảnh báo | Dependency có thể tự phục hồi |
| Registry outage kéo dài | Tạm giảm tải/pause có kiểm soát, đánh giá ngưỡng DLT | Tránh DLT bùng nổ với event hợp lệ |
| Credential/schema registry ACL sai | Cảnh báo và sửa cấu hình | Retry không sửa được quyền truy cập |
| Validation nghiệp vụ từ chối hợp lệ | Xử lý như kết quả nghiệp vụ thay vì DLT mù quáng | Không phải mọi từ chối là message hỏng |

Lưu ý: lỗi mà `ErrorHandlingDeserializer` biến thành `DeserializationException` có thể được classifier coi là fatal mặc định. Nếu lỗi gốc là sự cố registry tạm thời, việc override retry classification cần được thiết kế và kiểm thử cẩn thận; không chỉ thêm `RetryableException` bất kỳ rồi tin rằng tất cả lỗi delegate sẽ trở nên retryable. Có thể cần cấu trúc deserializer/custom handling để bảo tồn nguyên nhân và tránh retry sai kiểu lỗi.

## 9. Commit offset sau khi recovery

Sau khi DLT publish thành công, container có thể tiến qua record lỗi theo ack mode và chính sách error handler. **Lưu record ở DLT là một kết quả recovery, không phải xử lý nghiệp vụ thành công.**

Ví dụ topic `orders-3`:

| Offset | Kết quả |
|---:|---|
| 240 | Listener xử lý bình thường |
| 241 | Value deserialize lỗi, recover sang `orders.DLT` |
| 242 | Record hợp lệ tiếp theo |

Để consumer tiến qua offset 241, committed offset cuối cùng của group phải vượt record đó (thường là 242 sau khi xử lý/recovery tương ứng). Trong các tình huống dùng `DefaultErrorHandler`, sự tương tác giữa `ackAfterHandle`, acknowledgment mode và recovery quyết định khi nào commit diễn ra. Với `setCommitRecovered(true)`, `DefaultErrorHandler` yêu cầu `AckMode.MANUAL_IMMEDIATE`; đây là cấu hình riêng và không tự được bật bằng cách thêm DLT recoverer.

Nếu DLT publisher báo lỗi (ví dụ topic không tồn tại, serialization sai hoặc broker không xác nhận), **không** được xem record là đã recover và commit nó như thể đã lưu thành công ở DLT. Cần log/cảnh báo rõ ràng và giữ khả năng retry/recover lại khi sự cố được khắc phục.

Không có atomicity mặc định giữa publish DLT và commit offset consumer nguồn. Có thể xảy ra crash sau khi DLT nhận record nhưng trước commit, dẫn tới một record nguồn được đưa vào DLT nhiều lần sau restart. Dùng stable event ID hoặc `(originalTopic, originalPartition, originalOffset)` để deduplicate khi điều tra/replay. Nếu cần nguyên tử trong phạm vi Kafka, xem xét transactional recovery với `DefaultAfterRollbackProcessor` và Kafka transaction được cấu hình đúng; transaction đó không tự bao gồm database hoặc HTTP side effect.

## 10. Những rủi ro của retry topic đối với lỗi định dạng

Với `@RetryableTopic`, một record lỗi có thể được chuyển qua các retry topic trước khi đi tới DLT. Tuy nhiên, record không deserialize được có thể lại gây lỗi tại consumer của retry topic nếu cùng deserializer được áp dụng và payload vẫn giữ nguyên. Chỉ đổi tên topic không sửa được dữ liệu.

Đối với lỗi định dạng không thể khắc phục bằng retry, nên hướng tới DLT/quarantine trực tiếp để tránh tạo nhiều bản sao poison message. Nếu dùng non-blocking retry cho các lỗi có thể phục hồi, cần kiểm tra:

- Retry topic listener có thể đọc key/value và metadata của record lỗi hay không.
- Serializer dùng khi publish retry topic có xử lý raw bytes và object thường hay không.
- Exception classification có tách lỗi schema/registry tạm thời khỏi payload sai vĩnh viễn hay không.
- Thứ tự xử lý theo key có thể bị thay đổi vì record nằm trên retry topic trong khi main topic tiếp tục chạy.
- DLT cuối cùng có đủ retention và metadata để replay sau khi sửa nguyên nhân.

Không cấu hình nhiều tầng retry mà không biết tổng số attempts và thời gian giữ record. Retry storm từ một schema incompatibility sau release có thể gây tải lớn hơn chính luồng xử lý bình thường.

## 11. Batch listener, conversion error và key hỏng

Với batch listener, một lần poll chứa nhiều record. Một value không deserialize được cần được cô lập mà không làm những record khác bị mất hoặc lặp vô kiểm soát. `ErrorHandlingDeserializer` vẫn là lớp quan trọng cho lỗi ở tầng Kafka deserializer; thông tin lỗi có thể gắn với record trong batch.

Nếu lỗi xảy ra sau deserialization ở tầng conversion/binding, batch listener có thể cần `BatchListenerFailedException` kèm index/record phù hợp để error handler biết phần nào đã hoàn tất. Nếu chỉ ném exception chung mà không xác định record lỗi, framework có thể retry cả batch; side effect đã thực hiện trên những record trước vị trí lỗi có thể bị lặp.

Ví dụ một batch listener kiểm tra schema version sau khi đã decode thành object:

```java
@KafkaListener(
        topics = "orders",
        groupId = "orders-batch",
        containerFactory = "batchOrderContainerFactory")
public void consumeBatch(List<ConsumerRecord<String, OrderCreated>> records) {
    for (int i = 0; i < records.size(); i++) {
        OrderCreated event = records.get(i).value();
        try {
            schemaValidator.assertSupported(event);
            orderService.processIdempotently(event);
        }
        catch (UnsupportedMessageSchemaException ex) {
            throw new BatchListenerFailedException(
                    "Unsupported schema at index " + i, ex, i);
        }
    }
}
```

Trong ví dụ, factory phải bật batch listener mode và có error handler phù hợp. Cần kiểm thử riêng hành vi batch khi `ErrorHandlingDeserializer` đặt value lỗi thành `null`, khi key deserialize lỗi và khi message converter không tạo được object. Không nên tự xử lý `null` như một event hợp lệ nếu nó thực chất biểu thị deserialization failure.

## 12. Thiết kế DLT topic cho payload lỗi

DLT chứa dữ liệu có khả năng sai format, chưa xác minh hoặc khó decode; nó cần chính sách lưu trữ và quyền truy cập rõ ràng.

| Thành phần | Yêu cầu vận hành |
|---|---|
| Topic naming | Có quy ước và ownership rõ, ví dụ `<source>.DLT`; không nhầm với retry topic |
| Partition | Resolver đích chỉ định partition hợp lệ; nếu giữ partition gốc, DLT cần đủ partition |
| Replication và durability | `acks=all`, replication factor và `min.insync.replicas` phù hợp |
| Retention | Đủ thời gian phát hiện, điều tra, sửa lỗi, replay; tránh hết hạn trước khi xử lý xong |
| ACL | Chỉ service recovery được ghi, nhóm vận hành/triage được đọc theo quyền cần thiết |
| Key/value serializer | Chấp nhận raw `byte[]` và kiểu object đã deserialize nếu các luồng có thể cùng ghi DLT |
| Schema provenance | Giữ original topic, offset, event ID, schema ID/version nếu có |
| Observability | Theo dõi publish failure, DLT backlog, exception class và tỷ lệ lỗi theo phiên bản |

Một DLT dùng chung nhiều luồng khác schema cần đặc biệt cẩn thận. Nếu billing và audit cùng gửi lỗi vào một DLT nhưng có nhiều consumer group tự replay, có thể xảy ra xử lý nhầm nghiệp vụ. Tách DLT theo luồng hoặc thiết kế một dispatcher có ownership rõ ràng. DLT không phải topic “rác” để bỏ qua kiểm soát dữ liệu.

## 13. Đọc DLT để điều tra mà không gặp lại lỗi deserialize

Một consumer điều tra DLT thường nên **đọc raw bytes** hoặc dùng deserializer có khả năng chịu payload lỗi, thay vì tái sử dụng nguyên bộ deserializer đã thất bại ở topic nguồn.

Ví dụ tạo consumer factory phục vụ triage:

```java
@Bean("dltTriageConsumerFactory")
ConsumerFactory<byte[], byte[]> dltTriageConsumerFactory(
        KafkaProperties kafkaProperties) {

    Map<String, Object> props =
            new HashMap<>(kafkaProperties.buildConsumerProperties());

    props.put(ConsumerConfig.GROUP_ID_CONFIG, "orders-dlt-triage");
    props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
    props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            ByteArrayDeserializer.class);
    props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            ByteArrayDeserializer.class);

    return new DefaultKafkaConsumerFactory<>(props);
}
```

Đây là minh họa cho một consumer triage chỉ đọc byte, không phải một listener tự động xử lý mọi DLT record. Khi nguồn DLT có thể chứa object đã được serialize bằng nhiều kiểu khác nhau, muốn giải nghĩa payload phải dựa vào content type/schema metadata và contract tương ứng. Raw bytes giúp tránh lặp lỗi format khi mở record, nhưng không làm payload tự trở nên đáng tin cậy.

Triage nên lưu tọa độ DLT, original topic/partition/offset, exception, event ID, schema version và lỗi kỹ thuật. Chỉ xuất payload ở dạng hex/base64 hoặc giải mã có giới hạn và đã được kiểm soát, nhất là khi dữ liệu có thể chứa nội dung nhạy cảm.

## 14. Replay sau khi sửa lỗi format hoặc schema

Khi đã tìm nguyên nhân và có phiên bản consumer/producer phù hợp, record từ DLT có thể được replay về topic nguồn hoặc đi qua một luồng reprocessing riêng. Replay **không tự sửa** payload lỗi. Nếu bytes bị cắt và không thể tái tạo nội dung chính xác, có thể cần phát event mới từ source of truth thay vì gửi lại payload hỏng.

Một quy trình có kiểm soát:

1. Xác định tập record DLT bằng topic, partition, offset và/hoặc event ID đã đối soát.
2. Phân loại: lỗi format vĩnh viễn, schema mismatch, dependency tạm thời hay bug consumer.
3. Sửa nguyên nhân, kiểm thử một mẫu có đại diện các lớp lỗi.
4. Quyết định giữ nguyên raw bytes hay cần chuyển đổi sang schema mới có audit trail.
5. Đặt giới hạn replay count, rate limit, owner và change approval.
6. Phát lại một số record canary, theo dõi topic gốc, kết quả nghiệp vụ và DLT re-entry.
7. Tăng tốc dần, đối soát published count với business processed count.

Replay tạo một **record mới có offset mới** ở topic đích. Nó không làm record quay về vị trí offset cũ trong partition, vì vậy thứ tự nghiệp vụ có thể thay đổi. Consumer cần idempotency và thường cần state version check nếu event cũ được xử lý sau event mới.

Không tạo listener DLT chạy liên tục để tự động gửi mọi record về topic gốc. Nếu lỗi chưa được sửa, sẽ hình thành vòng lặp `orders -> orders.DLT -> orders -> ...`. Metadata replay count và một khu cách ly cuối cùng giúp giới hạn vòng lặp, nhưng cần chắc chắn metadata vẫn tồn tại qua mỗi lần recovery.

## 15. Quan sát lỗi định dạng trên production

Các chỉ số nên có:

- Tổng số deserialization/conversion failures theo topic, exception class và phiên bản consumer.
- Tỷ lệ record được chuyển DLT vì lỗi format, lỗi schema và lỗi registry.
- DLT publish success/failure/timeout; số record DLT và tuổi record cũ nhất cần xử lý.
- Consumer lag topic nguồn, rebalance count, commit failure, throughput thực tế.
- Số lỗi schema theo producer version/schema ID nếu metadata có sẵn.
- Tốc độ xuất hiện lại trong DLT sau replay, số record vượt giới hạn replay.

Các log cần có tọa độ nguồn, tọa độ DLT khi gửi thành công, exception class, root cause, schema metadata, listener/group và correlation ID. Không dùng event ID/offset riêng lẻ làm metric label vì cardinality cao; giữ chúng trong structured logs hoặc audit. Đặc biệt, không ghi toàn bộ payload lỗi lên log mặc định vì payload có thể chứa dữ liệu không đáng tin cậy hoặc thông tin nhạy cảm.

Nếu lỗi format tăng đột ngột sau deploy, cần so sánh phiên bản producer, consumer và schema. Nếu nhiều consumer cùng gặp lỗi chỉ trong một thời điểm nhưng payload có vẻ hợp lệ, xem xét schema registry/network outage trước khi quyết định replay hàng loạt. Khi DLT backlog tăng, có thể tạm dừng deployment hoặc giảm throughput để tránh lấp đầy storage.

## 16. Các lỗi triển khai thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `@KafkaListener` không được gọi, consumer liên tục lỗi tại `poll()` | Delegate deserializer ném exception trực tiếp, chưa dùng `ErrorHandlingDeserializer` | Bọc deserializer phù hợp và gắn `DefaultErrorHandler` có recoverer |
| DLT chứa `null` thay vì payload lỗi | Không khôi phục raw bytes đúng cách hoặc serializer/recoverer tùy biến bỏ mất payload | Kiểm tra `ErrorHandlingDeserializer`, `DeadLetterPublishingRecoverer` và dữ liệu DLT thực tế |
| Publish DLT tiếp tục lỗi serialization | DLT template chỉ hỗ trợ object hoặc chỉ hỗ trợ byte array | Dùng serializer phân loại theo kiểu hoặc template riêng phù hợp |
| Key lỗi làm DLT publish thất bại | DLT key serializer không nhận `byte[]` | Thêm nhánh `ByteArraySerializer` cho key và kiểm thử key deserialization failure |
| Payload hợp lệ bị đưa DLT hàng loạt | Schema registry outage, sai type mapping hoặc consumer chưa tương thích | Kiểm tra root cause, schema/config và giảm tải trước khi replay |
| Recoverer ghi log thành công nhưng DLT không có record | Send future thất bại mà không được báo lại | Bật fail-on-send-error phù hợp, kiểm tra timeout/acks, xác minh topic và offset |
| DLT topic không nhận record từ partition cao | DLT có ít partition hơn nguồn nhưng resolver giữ cùng partition index | Tăng partition DLT hoặc chọn resolver hợp lệ |
| DLT replay tiếp tục gặp cùng lỗi | Nguyên nhân chưa được sửa hoặc raw bytes không thể parse | Dừng replay, phân loại lỗi và sửa hợp đồng dữ liệu |
| Duplicate record trong DLT | Crash sau publish DLT nhưng trước commit offset nguồn | Dùng original topic/partition/offset hoặc event ID để deduplicate |
| Batch listener xử lý sai record sau format error | Không xác định đúng index hoặc cấu hình batch/converter không phù hợp | Kiểm thử `BatchListenerFailedException`, header lỗi và acknowledgment mode |

Khi điều tra, hãy bắt đầu bằng topic/partition/offset gốc và xác định lỗi xảy ra ở **Kafka deserializer**, **message conversion** hay **business validation**. Thứ tự này giúp tránh sửa error handler khi nguyên nhân thực tế nằm ở schema/serializer, hoặc ngược lại.

## 17. Kiểm thử tích hợp cần có

Với một môi trường Kafka kiểm thử, nên gửi có chủ đích các record:

1. JSON hợp lệ đúng kiểu: listener được gọi và hoàn tất bình thường.
2. JSON sai cú pháp: listener nghiệp vụ không được gọi; record tới DLT và giữ raw bytes.
3. JSON hợp lệ nhưng không khớp model: quan sát lỗi conversion/deserialization và đường DLT tương ứng.
4. Key deserialize lỗi: DLT producer xử lý raw key bytes thành công.
5. Value object đã deserialize nhưng validation fail: DLT template serialize object thường đúng định dạng.
6. Lỗi schema version không hỗ trợ: record được cách ly theo policy và giữ provenance.
7. Registry timeout: ứng dụng không tạo DLT storm ngoài chính sách đã định.
8. DLT topic không tồn tại hoặc ACL bị từ chối: recoverer báo lỗi, không coi record đã recover thành công.
9. Restart trước/sau commit offset: không mất record; duplicate có thể xảy ra nhưng được xử lý an toàn.
10. Replay một record canary sau khi sửa nguyên nhân: record được xử lý, không tạo vòng lặp DLT.

Kiểm tra cả key/value bytes, headers nguồn, exception class, committed offset và số lần gọi listener. Chỉ kiểm tra "DLT có một record" chưa đủ vì DLT có thể chứa value bị đổi format hoặc thiếu dữ liệu gốc.

## 18. Runbook xử lý sự cố lỗi định dạng

Khi DLT tăng đột ngột vì lỗi deserialization/schema, có thể thực hiện theo thứ tự:

1. **Khoanh vùng:** xác định cluster, topic nguồn, partition, group, listener, phiên bản triển khai và thời điểm lỗi bắt đầu.
2. **Xác nhận đường lỗi:** tìm xem exception đến từ delegate deserializer, Spring message converter hay listener validation.
3. **Kiểm tra payload:** lấy một mẫu DLT được cấp quyền, xem raw bytes, header nguyên bản, type/schema ID và event ID.
4. **Đánh giá mức độ:** số record bị ảnh hưởng, consumer lag, outage registry và phụ thuộc downstream.
5. **Ngăn bùng nổ:** nếu lỗi do release/schema registry, rollback hoặc tạm giảm tốc trước khi backlog DLT lan rộng.
6. **Sửa nguyên nhân:** cập nhật serializer/deserializer, schema compatibility, producer contract hoặc cấu hình registry.
7. **Kiểm thử:** phát lại một tập nhỏ trong môi trường thử nghiệm hoặc canary có kiểm soát.
8. **Replay:** chọn record đã được phê duyệt, có replay cap, rate limit và idempotency.
9. **Đối soát:** so số record DLT xử lý, published replay, business processed và phần còn lỗi.
10. **Phòng ngừa:** bổ sung contract test, schema evolution policy, alert và runbook theo owner.

Đừng sửa committed offset thủ công chỉ để "đi qua" một record lỗi chưa được giữ trong DLT hoặc chưa có quyết định nghiệp vụ. Reset offset tiến lên có thể làm mất quyền xử lý record; reset lùi có thể phát lại hàng loạt dữ liệu đã hoàn tất.

## 19. Nguyên tắc cốt lõi

Để dead letter cho lỗi định dạng hoạt động tin cậy trong Spring Kafka:

1. Phân biệt lỗi xảy ra tại deserializer, converter và business validation.
2. Dùng `ErrorHandlingDeserializer` để đưa lỗi trong Kafka deserializer vào cơ chế xử lý lỗi của container.
3. Dùng `DefaultErrorHandler` với exception classification hợp lý; không retry vô ích payload sai cú pháp.
4. Dùng `DeadLetterPublishingRecoverer` có kiểm tra kết quả gửi DLT, không âm thầm coi recovery thất bại là thành công.
5. Thiết kế DLT serializer hỗ trợ cả raw `byte[]` khi decode lỗi và object bình thường khi listener xử lý lỗi; xét cả key lẫn value.
6. Giữ provenance gốc, schema metadata và event ID để điều tra và replay.
7. Phân biệt lỗi payload vĩnh viễn với dependency/schema registry outage có thể phục hồi.
8. Quản lý commit offset, duplicate, idempotency và replay loop riêng với việc publish DLT.
9. Theo dõi DLT backlog, publish error, schema version và consumer lag; hạn chế log dữ liệu nhạy cảm.
10. Chỉ replay sau khi nguyên nhân được sửa và kết quả đã được kiểm chứng bằng canary và đối soát nghiệp vụ.

**Kết luận:** dead letter cho lỗi định dạng không chỉ là thêm một DLT topic. Cần bảo đảm consumer có thể biểu diễn lỗi xảy ra *trước listener* thành một record phục hồi được, DLT giữ nguyên dữ liệu đủ để điều tra, publisher có serializer đúng kiểu, và quy trình retry/replay không làm mất dữ liệu hoặc tạo vòng lặp. Khi các ranh giới này được thiết kế rõ, Spring Kafka có thể tiếp tục tiêu thụ dù gặp poison record, đồng thời giữ lại bằng chứng để sửa hợp đồng dữ liệu và khôi phục có kiểm soát.
