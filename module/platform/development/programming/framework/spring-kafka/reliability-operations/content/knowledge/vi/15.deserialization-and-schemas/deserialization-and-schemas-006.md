# Khôi phục original value vào DLT

Khi một Kafka consumer không thể deserialize record, sự cố thường xuất hiện **trước khi business listener nhận được object**. Ví dụ producer gửi JSON lỗi cú pháp, message có schema không tương thích hoặc serializer và deserializer không thống nhất. Nếu hệ thống chỉ ghi nhận exception và chuyển một record có value bằng null sang dead-letter topic (DLT), nhóm vận hành sẽ mất chính những bytes cần thiết để điều tra và sửa dữ liệu.

Trong Spring Kafka, kết hợp **ErrorHandlingDeserializer** với **DeadLetterPublishingRecoverer** cho phép chuyển record không deserialize được sang DLT và **khôi phục original value**, tức là bytes của value nhận từ Kafka trước khi deserialize thất bại. DLT lưu được payload lỗi để phân tích hoặc replay sau khi sửa schema, cấu hình hoặc ứng dụng.

Bài học này tập trung vào tính toàn vẹn payload khi xử lý lỗi deserialization, đồng thời giải thích các yêu cầu về producer serializer, Kafka headers, consumer DLT, offset, idempotency và vận hành.

## 1. Original value là gì?

Một Kafka record ở tầng broker gồm key bytes, value bytes, headers, timestamp và metadata vị trí. Kafka broker không yêu cầu biết Java class của payload. Consumer nhận bytes và dùng deserializer để chuyển thành object.

~~~text
Producer
  |
  | serialize OrderEvent thành bytes
  v
Kafka broker
  |
  | topic=orders, partition=2, offset=105
  | value bytes: 7B 22 6F 72 64 65 72 ...
  v
Kafka Consumer
  |
  | JsonDeserializer<OrderEvent>
  +------ thành công ------> OrderEvent object
  |
  +------ thất bại -------> DeserializationException
~~~

**Original value** trong tình huống lỗi deserialization là chuỗi bytes value đã được ghi trong Kafka và được cung cấp cho deserializer của consumer. Đây không nhất thiết là chuỗi JSON hợp lệ, cũng không nhất thiết có thể biến thành class Java mong muốn.

Ví dụ producer gửi:

~~~text
{"orderId":"O-1001","amount":}
~~~

JSON trên sai cú pháp ở trường amount. Với JsonDeserializer của OrderEvent, không tạo được object. Tuy nhiên, các bytes chứa JSON lỗi vẫn rất có giá trị: người vận hành có thể nhìn ra lỗi và xác định producer hoặc schema nào gây ra.

Phân biệt rõ ba đối tượng:

| Thành phần | Ý nghĩa |
|---|---|
| **Raw value bytes** | Payload đã nhận từ Kafka, trước bước deserialize ở consumer |
| **Deserialized value** | Object Java được tạo khi deserializer thành công |
| **DLT record value** | Dữ liệu được producer của recoverer serialize và ghi vào topic DLT |

Mục tiêu khi khôi phục original value là để record DLT chứa **raw bytes gốc** trong trường hợp deserialize thất bại, thay vì để value rỗng hoặc biến dữ liệu lỗi thành một object giả.

## 2. Vì sao deserialization failure khó xử lý?

Trong đường xử lý bình thường, Kafka client gọi deserializer bên trong consumer.poll(). Với deserializer tiêu chuẩn, nếu deserialize thất bại và exception thoát khỏi poll, listener chưa nhận được ConsumerRecord đã chuyển thành object. Ứng dụng không thể chỉ dùng try/catch trong @KafkaListener để bắt lỗi này.

Ví dụ listener:

~~~java
@KafkaListener(topics = "orders", groupId = "orders-service")
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
~~~

Nếu deserializer ném lỗi trước khi method được gọi, khối xử lý bên trong onOrder() không có cơ hội truy xuất value thô. Một error handler cấu hình không phù hợp còn có thể gặp vòng lặp poll lỗi trên cùng record, khiến partition không tiến.

Các nguồn lỗi phổ biến:

- JSON sai cú pháp hoặc dữ liệu bị cắt cụt.
- Trường số, enum, timestamp có giá trị không thể chuyển sang kiểu Java.
- Schema Avro, Protobuf hoặc JSON Schema không tương thích với consumer.
- Schema registry tạm thời không truy cập được.
- Producer và consumer dùng format hoặc serializer khác nhau.
- Type header không hợp lệ, class không tồn tại hoặc cấu hình trusted packages không phù hợp.
- Key deserialize lỗi, ngay cả khi value hợp lệ.

Một số lỗi là **permanent** (raw bytes thực sự sai), một số có thể là **transient** (schema registry unavailable). Cần phân loại đúng để quyết định retry ngắn, recovery DLT hay xử lý hạ tầng.

## 3. ErrorHandlingDeserializer giải quyết điểm nghẽn nào?

**ErrorHandlingDeserializer** là wrapper deserializer của Spring Kafka. Nó gọi một delegate deserializer thực sự, ví dụ JsonDeserializer. Khi delegate ném exception, wrapper ghi thông tin lỗi và bytes gốc vào một header dạng DeserializationException để listener container/error handler có thể tiếp cận lỗi.

~~~text
Kafka poll
   |
   v
ErrorHandlingDeserializer
   |
   v
Delegate JsonDeserializer
   |
   +-- thành công --> trả về OrderEvent
   |
   +-- thất bại
          |
          +-- lưu DeserializationException vào header
          |     (trong exception có raw bytes)
          |
          +-- trả về null hoặc fallback theo cấu hình
          |
          v
Listener container phát hiện deserialization header
          |
          v
Error handler / recoverer
~~~

Điểm quan trọng: value trong ConsumerRecord ở đường xử lý lỗi có thể là **null** vì không có object được tạo. Nhưng **raw bytes chưa nhất thiết bị mất**; chúng được mang theo qua thông tin exception do ErrorHandlingDeserializer cung cấp.

Spring Kafka sử dụng các header dành cho deserialization exception của key và value. Đây là metadata nội bộ của error-handling, khác với các header DLT_ORIGINAL_TOPIC, DLT_ORIGINAL_OFFSET dùng để truy vết vị trí nguồn sau khi chuyển sang DLT.

Không nên tự parse Java-serialized exception header bằng cách giải mã UTF-8. Đối với các phiên bản dùng định dạng serialized exception, hãy để Spring Kafka xử lý hoặc dùng utility tương ứng trong đúng phiên bản thư viện. Header chứa object exception không phải định dạng trao đổi lâu dài giữa các hệ thống.

## 4. Cơ chế khôi phục original value vào DLT

Khi dùng **DeadLetterPublishingRecoverer** cùng ErrorHandlingDeserializer, các phiên bản Spring Kafka hỗ trợ cơ chế sử dụng raw data từ thông tin deserialization failure để thiết lập value của **ProducerRecord gửi sang DLT**.

Luồng lý tưởng:

~~~text
orders/P2/105
   value bytes = malformed JSON
           |
           v
ErrorHandlingDeserializer
   delegate không tạo được OrderEvent
   ConsumerRecord.value() có thể null
   DeserializationException giữ raw bytes
           |
           v
DefaultErrorHandler
   lỗi không thể retry hoặc đã hết retry
           |
           v
DeadLetterPublishingRecoverer
   phát hiện lỗi deserialize value
   lấy raw bytes từ exception metadata
   đặt ProducerRecord.value() = byte[]
           |
           v
DLT Producer (ByteArraySerializer)
           |
           v
orders.DLT/P2/<offset mới>
   value bytes = malformed JSON gốc
~~~

Với các phiên bản Spring Kafka có hỗ trợ tính năng phục hồi này, recoverer có thể khôi phục bytes gốc vào DLT record value thay vì gửi null. Khả năng, cấu hình headers và xử lý key/value đồng thời cần đối chiếu phiên bản Spring Kafka đang dùng.

Về mặt dữ liệu, hai điều phải được giữ riêng:

1. **Value phục hồi:** raw bytes ban đầu, để có thể quan sát hoặc giải mã lại sau này.
2. **Metadata nguồn:** original topic/partition/offset, exception class/message và thông tin cần truy vết.

Nếu DLT record chỉ có original offset nhưng value là null, chưa đạt mục tiêu khôi phục original value. Ngược lại, nếu value còn nguyên bytes nhưng không có metadata nguồn, việc điều tra provenance cũng sẽ khó khăn.

## 5. Cấu hình ErrorHandlingDeserializer bằng Spring Boot

Ví dụ consumer đọc một topic orders chứa value JSON và key dạng String:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: orders-service
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.value.delegate.class]": org.springframework.kafka.support.serializer.JsonDeserializer
        "[spring.json.value.default.type]": com.example.orders.OrderEvent
        "[spring.json.trusted.packages]": com.example.orders
    listener:
      ack-mode: record
~~~

Ý nghĩa:

- **value-deserializer** là wrapper ErrorHandlingDeserializer.
- **spring.deserializer.value.delegate.class** chỉ định JsonDeserializer thực hiện deserialize thật.
- **spring.json.value.default.type** khai báo kiểu value mặc định khi không có type header cần thiết.
- **spring.json.trusted.packages** giới hạn các package được phép deserialize để tránh tin cậy class không kiểm soát.
- **enable-auto-commit: false** để container quản lý thời điểm commit theo chính sách listener/error handler.

Giá trị com.example.orders.OrderEvent là class ví dụ; đổi theo model thực tế. Với producer đã dùng type header, cấu hình kiểu mặc định và cách sử dụng header cần phù hợp serialization strategy của dự án.

Không nên dùng trusted packages là dấu sao trong production chỉ để vượt qua lỗi deserialize; trước tiên xác minh producer format, class mapping và quy tắc bảo mật.

### Nếu key cũng có thể deserialize lỗi

Để xử lý lỗi key có hệ thống, có thể dùng ErrorHandlingDeserializer cho cả key:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.key.delegate.class]": org.apache.kafka.common.serialization.StringDeserializer
        "[spring.deserializer.value.delegate.class]": org.springframework.kafka.support.serializer.JsonDeserializer
        "[spring.json.value.default.type]": com.example.orders.OrderEvent
        "[spring.json.trusted.packages]": com.example.orders
~~~

Khi key deserialize thất bại, recoverer cũng cần một DLT producer có thể ghi **raw key bytes**. Đừng chỉ cấu hình ByteArraySerializer cho value rồi bỏ qua trường hợp key bị lỗi.

## 6. DefaultErrorHandler và DeadLetterPublishingRecoverer

Với listener container không dùng Kafka transaction, có thể kết hợp DefaultErrorHandler và DeadLetterPublishingRecoverer:

~~~java
@Configuration
public class OrdersErrorHandlingConfiguration {

    @Bean
    DefaultErrorHandler ordersErrorHandler(
            KafkaTemplate<Object, Object> dltKafkaTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(dltKafkaTemplate);

        FixedBackOff backOff = new FixedBackOff(1_000L, 2L);

        DefaultErrorHandler errorHandler =
                new DefaultErrorHandler(recoverer, backOff);

        return errorHandler;
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
            ordersKafkaListenerContainerFactory(
                    ConsumerFactory<String, OrderEvent> consumerFactory,
                    DefaultErrorHandler ordersErrorHandler) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(ordersErrorHandler);
        return factory;
    }
}
~~~

Đây là ví dụ cấu trúc. Ứng dụng cần khai báo dltKafkaTemplate với producer factory và serializer phù hợp; chỉ có error handler chưa đủ để gửi được bytes lỗi.

**DefaultErrorHandler** có cơ chế phân loại một số exception là fatal/non-retryable theo mặc định, trong đó có nhiều trường hợp liên quan đến deserialization hoặc conversion. Với lỗi dữ liệu sai định dạng, retry nhiều lần thường không giúp gì. Với lỗi hạ tầng tạm thời, cần cân nhắc retry có giới hạn và khả năng phục hồi.

Nếu phân loại lỗi thành non-retryable, handler có thể đưa record vào recoverer mà không dùng hết chuỗi FixedBackOff. Không nên hiểu rằng mọi deserialization exception sẽ luôn được gọi lại đúng số lần retry đã cấu hình.

Trong trường hợp container sử dụng Kafka transaction, cơ chế sau rollback thường liên quan đến AfterRollbackProcessor và cần cấu hình riêng. Không áp dụng máy móc ví dụ DefaultErrorHandler của listener không transaction.

## 7. Serializer của DLT producer là điểm quyết định

Đây là điểm thường gây lỗi vận hành: **record bình thường** có value kiểu OrderEvent, còn **record deserialize lỗi** cần ghi sang DLT dưới dạng byte[].

Nếu producer DLT chỉ cấu hình JsonSerializer cho OrderEvent, raw byte[] có thể không được ghi đúng như dự kiến. Nếu producer DLT chỉ cấu hình ByteArraySerializer, record bình thường bị lỗi ở business listener (value là OrderEvent) cũng có thể không publish được.

Producer phục vụ DeadLetterPublishingRecoverer cần hỗ trợ các runtime type mà recoverer có thể gửi:

| Nguồn lỗi | Key ở ProducerRecord DLT | Value ở ProducerRecord DLT | Yêu cầu serializer |
|---|---|---|---|
| Business listener ném exception sau deserialize thành công | String (ví dụ) | OrderEvent | StringSerializer, JsonSerializer |
| Value deserialization thất bại | String (nếu key hợp lệ) | byte[] raw | StringSerializer, ByteArraySerializer |
| Key deserialization thất bại | byte[] raw | OrderEvent hoặc byte[] tùy kết quả value | ByteArraySerializer cho key, serializer tương ứng cho value |
| Cả key và value đều deserialize thất bại | byte[] raw | byte[] raw | ByteArraySerializer cho cả key và value |

**DelegatingByTypeSerializer** của Spring Kafka giúp chọn serializer theo runtime class. Một cách khác là cấu hình recoverer với nhiều KafkaTemplate và chọn template tương ứng theo value type ở phiên bản hỗ trợ.

### Ví dụ producer factory hỗ trợ object và raw bytes

~~~java
@Bean
ProducerFactory<Object, Object> dltProducerFactory() {
    Map<String, Object> props = new HashMap<>();

    props.put(
            ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092");
    props.put(ProducerConfig.ACKS_CONFIG, "all");
    props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);

    Map<Class<?>, Serializer<?>> keySerializers = new LinkedHashMap<>();
    keySerializers.put(byte[].class, new ByteArraySerializer());
    keySerializers.put(String.class, new StringSerializer());

    Map<Class<?>, Serializer<?>> valueSerializers = new LinkedHashMap<>();
    valueSerializers.put(byte[].class, new ByteArraySerializer());
    valueSerializers.put(
            OrderEvent.class,
            new JsonSerializer<OrderEvent>());

    return new DefaultKafkaProducerFactory<>(
            props,
            new DelegatingByTypeSerializer(keySerializers),
            new DelegatingByTypeSerializer(valueSerializers));
}

@Bean
KafkaTemplate<Object, Object> dltKafkaTemplate(
        ProducerFactory<Object, Object> dltProducerFactory) {
    return new KafkaTemplate<>(dltProducerFactory);
}
~~~

Các class và producer properties ở trên minh họa ý tưởng chọn serializer theo type. Cần điều chỉnh class value, map serializer, security, bootstrap servers và các overload API theo phiên bản Spring Kafka cụ thể.

Tại nhánh value deserialization failure:

~~~text
ProducerRecord.value() = byte[]
         |
         v
DelegatingByTypeSerializer
         |
         v
ByteArraySerializer
         |
         v
Kafka DLT chứa lại raw bytes
~~~

ByteArraySerializer ghi lại bytes nhận được, không tự chuyển JSON lỗi thành JSON mới. Điều này quan trọng nếu muốn giữ chính xác nội dung bytes để chẩn đoán.

### Chỉ có một loại DLT record

Nếu DLT được dành riêng cho lỗi deserialization và mọi value đều là bytes, có thể chọn ByteArraySerializer trực tiếp. Tuy nhiên, nếu cùng DLT cũng nhận lỗi nghiệp vụ với value là object, cần một đường producer khác hoặc serializer hỗ trợ nhiều runtime type.

Không nên cấu hình một serializer áp dụng cho tất cả chỉ dựa vào việc listener gốc khai báo OrderEvent. Kiểu Java mà recoverer gửi sang DLT có thể khác kiểu mà listener nhận.

## 8. Đọc DLT bằng ByteArrayDeserializer

Một consumer DLT phục vụ điều tra thường nên lấy được **raw bytes**, kể cả khi payload sai schema. Dùng cùng JsonDeserializer<OrderEvent> của topic gốc cho DLT là một sai lầm dễ gặp: record đã deserialize lỗi một lần lại tiếp tục lỗi ở DLT.

Ví dụ cấu hình một consumer độc lập đọc bytes:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        "[spring.json.trusted.packages]": com.example.orders
~~~

Trong thực tế, nên tạo riêng một ConsumerFactory hoặc listener container factory cho DLT, sử dụng ByteArrayDeserializer cho value, thay vì thay đổi cấu hình consumer chính của toàn ứng dụng.

Ví dụ:

~~~java
@Bean
ConsumerFactory<byte[], byte[]> rawDltConsumerFactory() {
    Map<String, Object> props = new HashMap<>();
    props.put(
            ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092");
    props.put(
            ConsumerConfig.GROUP_ID_CONFIG,
            "orders-dlt-investigation");
    props.put(
            ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,
            "earliest");

    return new DefaultKafkaConsumerFactory<>(
            props,
            new ByteArrayDeserializer(),
            new ByteArrayDeserializer());
}

@Bean
ConcurrentKafkaListenerContainerFactory<byte[], byte[]>
        rawDltListenerFactory(
                ConsumerFactory<byte[], byte[]> rawDltConsumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<byte[], byte[]>();
    factory.setConsumerFactory(rawDltConsumerFactory);
    return factory;
}
~~~

DLT listener:

~~~java
@KafkaListener(
        topics = "orders.DLT",
        groupId = "orders-dlt-investigation",
        containerFactory = "rawDltListenerFactory")
public void investigate(ConsumerRecord<byte[], byte[]> record) {
    byte[] rawValue = record.value();

    log.warn(
            "DLT record topic={}, partition={}, offset={}, bytes={}",
            record.topic(),
            record.partition(),
            record.offset(),
            rawValue == null ? -1 : rawValue.length);

    failureStore.persistRawRecord(
            record.topic(),
            record.partition(),
            record.offset(),
            record.key(),
            rawValue,
            record.headers());
}
~~~

Với DLT chứa cả các record business listener lỗi và deserialization lỗi, ByteArrayDeserializer vẫn có thể đọc bytes được Kafka lưu. Tuy nhiên, định dạng bytes của record business listener lỗi do DLT producer quyết định (chẳng hạn JSON), và bytes của record deserialize lỗi là bản gốc đã khôi phục. Consumer DLT cần biết cách phân biệt hoặc giữ raw bytes mà chưa ép chúng vào một schema duy nhất.

Không in toàn bộ raw payload vào log production. Payload có thể chứa thông tin nhạy cảm, bytes không phải UTF-8, hoặc dữ liệu rất lớn. Nên lưu an toàn và chỉ hiển thị ở công cụ điều tra có phân quyền.

## 9. Header cho biết đây là lỗi deserialization

Sau khi recoverer publish sang DLT, record có thể mang thông tin lỗi và nguồn:

| Nhóm header | Ý nghĩa |
|---|---|
| DLT_ORIGINAL_TOPIC | Topic nguồn được ghi nhận trong cơ chế recovery |
| DLT_ORIGINAL_PARTITION | Partition nguồn |
| DLT_ORIGINAL_OFFSET | Offset nguồn |
| DLT_EXCEPTION_FQCN | Class của exception tại thời điểm recovery |
| DLT_EXCEPTION_MESSAGE | Message lỗi nếu được cung cấp |
| Các header exception liên quan đến key/value | Phân biệt lỗi deserialize key và value khi phiên bản hỗ trợ |

Tên constant, việc giữ exception header và giá trị mặc định của recoverer phụ thuộc Spring Kafka version. Với các phiên bản hiện đại, DeadLetterPublishingRecoverer có thể bổ sung DLT metadata mà không cần giữ nguyên Java-serialized DeserializationException header như một phần payload lâu dài.

Khi điều tra, nên lưu riêng:

~~~text
current:
  topic: orders.DLT
  partition: 2
  offset: 18

original:
  topic: orders
  partition: 2
  offset: 105

payload:
  type: raw-bytes
  size: 31

failure:
  phase: value-deserialization
  exception: RecordDeserializationException
~~~

Định dạng trên là ví dụ bản ghi audit do ứng dụng tự tạo, không phải định dạng Kafka tự sinh. Exception class thực tế có thể là DeserializationException hoặc wrapper khác tùy đường xử lý.

Không trộn original offset với DLT offset; chúng thuộc các log khác nhau. Original offset chỉ là vị trí tham chiếu, không phải idempotency key nghiệp vụ.

## 10. Khôi phục bytes có giữ nguyên dữ liệu tuyệt đối không?

Khi pipeline cấu hình đúng và không có custom transformation, raw byte[] mà ErrorHandlingDeserializer giữ có thể được ByteArraySerializer publish sang DLT để lưu lại các bytes ban đầu.

Tuy nhiên, cần hiểu giới hạn:

- Nếu producer gốc đã serialize sai ngay trước khi gửi Kafka, original bytes chỉ là **dữ liệu đã được ghi lên Kafka**, không phải object ban đầu trong bộ nhớ producer.
- Nếu application hoặc custom recoverer sửa bytes, payload DLT có thể khác raw bytes nguồn.
- Nếu DLT producer dùng serializer khác ByteArraySerializer cho byte[], dữ liệu có thể bị đổi hoặc publish thất bại.
- Nếu dữ liệu bị bỏ vì Kafka record quá lớn, quá thời gian retention hoặc publish lỗi, việc có header không bảo đảm bytes đã được giữ.
- Nếu key lỗi, key bytes cũng phải được giữ đúng; việc chỉ khôi phục value chưa đủ cho một số nghiệp vụ.

Để xác nhận tính toàn vẹn, có thể so sánh raw bytes của record nguồn và DLT bằng Arrays.equals hoặc mã băm cryptographic hash phù hợp:

~~~java
assertThat(dltRecord.value())
        .containsExactly(sourceBytes);
~~~

Một phép so sánh bytes trực tiếp tốt hơn so sánh chuỗi JSON vì sự khác biệt whitespace, encoding hoặc thứ tự field có thể bị che lấp nếu parse rồi serialize lại.

## 11. Phân biệt lỗi deserialize và lỗi business listener

Hai tình huống này đòi hỏi xử lý DLT khác nhau.

### Case A: deserialization failure

~~~text
Kafka bytes
   |
   v
JsonDeserializer
   |
   +-- lỗi, không tạo được OrderEvent
   |
   v
ErrorHandlingDeserializer giữ raw bytes
   |
   v
DeadLetterPublishingRecoverer
   |
   v
DLT value = byte[] gốc
~~~

Listener nghiệp vụ chưa xử lý được record. Sau khi sửa schema hoặc deserializer, có thể giải mã lại raw bytes từ DLT.

### Case B: business listener failure

~~~text
Kafka bytes
   |
   v
JsonDeserializer thành công
   |
   v
OrderEvent object
   |
   v
Business listener lỗi database
   |
   v
DeadLetterPublishingRecoverer
   |
   v
DLT value = OrderEvent (được serializer DLT ghi lại)
~~~

Ở Case B, không có lý do tự động để recoverer thay value bằng original raw bytes từ deserializer, vì deserialize đã thành công và không có deserialization exception metadata. Nếu ứng dụng yêu cầu giữ bytes nguồn **trong mọi loại lỗi**, kể cả lỗi nghiệp vụ, phải thiết kế thêm cơ chế giữ bytes hoặc payload envelope ngay từ lúc consume; không nên nhầm đây là hành vi mặc định của DLT recoverer.

## 12. Nếu key deserialize lỗi thì sao?

Key cũng đi qua deserializer của consumer. Một key không hợp lệ có thể khiến listener không nhận được record dù value đúng.

Với ErrorHandlingDeserializer cho key:

~~~text
key raw bytes:   FF FE 00
value raw bytes: JSON hợp lệ

StringDeserializer key -> thất bại

DLT:
  key   = original key bytes
  value = OrderEvent hoặc bytes theo trạng thái value
~~~

Trong cấu hình này, key của ProducerRecord DLT có thể là byte[] dù business listener thông thường dùng String. Producer serializer phải hỗ trợ byte[] cho key, như đã trình bày trong phần DelegatingByTypeSerializer.

Nếu cả key và value lỗi, cần hỗ trợ byte[] cho cả hai. Một recoverer chỉ xử lý value failure nhưng giả định key luôn là String có thể thất bại ở bước publish DLT.

Đừng dùng String.valueOf(key) để khôi phục key bytes. Nếu key đã hỏng encoding, việc chuyển thành String có thể thay thế hoặc mất byte gốc.

## 13. Deserialization exception có nên retry không?

Không phải mọi lỗi deserialize đều thuộc cùng nhóm.

| Loại lỗi | Khả năng tự phục hồi | Hướng xử lý thường cân nhắc |
|---|---|---|
| JSON sai cú pháp | Rất thấp | DLT sớm, giữ original bytes |
| Enum/value không được hỗ trợ | Thấp nếu không đổi code/schema | DLT hoặc sửa consumer rồi replay |
| Event schema không tương thích | Thấp cho lần xử lý hiện tại | DLT, triển khai schema phù hợp |
| Schema registry tạm unavailable | Có thể phục hồi | Retry có giới hạn, quan sát dependency |
| Type header trỏ class không tồn tại | Thường cần sửa cấu hình | DLT hoặc sửa class mapping |
| Lỗi bảo mật hoặc trusted package | Cần điều tra trước | Không mở rộng trust tùy tiện |

DefaultErrorHandler thường xem các lỗi deserialize và conversion thuộc nhóm fatal/non-retryable theo classifier mặc định. Cần kiểm tra chính sách cụ thể của phiên bản Spring Kafka và quy tắc bổ sung của ứng dụng.

Không retry mãi một record sai cú pháp. Nó có thể chặn partition và làm consumer lag tăng mà không có cơ hội xử lý thành công. Ngược lại, nếu lỗi do dependency bên ngoài tạm thời unavailable, một chính sách retry ngắn hoặc non-blocking retry có kiểm soát có thể hợp lý.

## 14. Record lỗi đi qua retry topic và DLT

Nếu ứng dụng dùng non-blocking retry, record có thể được forward qua nhiều topic trước khi đến DLT. Với lỗi deserialization, cần đặc biệt thận trọng vì payload có thể không bao giờ trở thành object Java trên chặng chính.

Các vấn đề cần xác minh:

- Retry infrastructure của phiên bản Spring Kafka có hỗ trợ đường lỗi đang dùng hay không.
- Forwarder có giữ raw bytes và metadata deserialization failure xuyên suốt các chặng hay không.
- Producer của mọi chặng có thể serialize byte[] không.
- Consumer của retry topic có tiếp tục gặp cùng lỗi và có thể recovery đúng hay không.
- DLT đích có giữ original topic, partition, offset và event correlation hay không.

Không nên giả định cứ gắn @RetryableTopic lên listener là mọi deserialization failure trước listener sẽ đi đúng qua toàn bộ retry topology. Khả năng phục hồi phụ thuộc vào cách ErrorHandlingDeserializer, listener container và recoverer tương tác trong phiên bản và cấu hình đang dùng.

Nếu mục tiêu chính là giữ raw bytes của record sai schema, một đường DLT trực tiếp qua DefaultErrorHandler và DeadLetterPublishingRecoverer thường dễ kiểm soát hơn việc retry nhiều lần cùng dữ liệu lỗi.

## 15. Replay original value từ DLT

DLT giúp lưu dữ liệu bị lỗi để xử lý sau khi sửa consumer, schema hoặc producer. Khi replay, nên giữ nguyên raw bytes nếu mục tiêu là thử lại cách deserialize đã sửa.

Một quy trình an toàn:

1. Xác định record DLT bằng current topic/partition/offset.
2. Đọc original topic/partition/offset headers và event ID nếu có.
3. Lưu raw bytes để đối chiếu; không tự sửa payload trước khi biết nguyên nhân lỗi.
4. Kiểm tra phiên bản schema, serializer và deserializer đã được sửa.
5. Xác định record đã tạo side effect nào chưa ở các lần xử lý khác.
6. Chọn topic replay hoặc công cụ xử lý thủ công được kiểm soát.
7. Publish bytes với ByteArraySerializer nếu muốn giữ đúng payload nguyên thủy.
8. Ghi replay ID, người thực hiện, lý do và thời điểm; giới hạn số lần replay.
9. Quan sát kết quả và kiểm tra không phát sinh vòng DLT → replay → DLT vô hạn.

Ví dụ publish raw bytes sang một topic replay:

~~~java
ProducerRecord<byte[], byte[]> replayRecord =
        new ProducerRecord<>(
                "orders-replay",
                originalKeyBytes,
                originalValueBytes);

rawKafkaTemplate.send(replayRecord);
~~~

Ví dụ giả định rawKafkaTemplate có serializer phù hợp với byte[] cho cả key và value. Không sao chép nguyên lệnh vào production khi chưa xác định partition strategy và ordering.

Khi replay sang topic khác, offset mới tiếp tục do broker cấp. Original offset header chỉ dùng để truy vết và không được lấy làm offset để commit cho consumer group trên topic replay.

Nếu bản thân payload bị lỗi không thể sửa bằng cách đổi consumer schema, có thể cần một bước chuẩn hóa dữ liệu riêng, tạo payload mới và lưu provenance của bản lỗi. Đây là **data repair**, khác với replay raw bytes nguyên trạng; cần ghi nhận rõ phiên bản trước và sau để phục vụ kiểm toán.

## 16. Những tình huống dễ làm mất original value

### Consumer dùng trực tiếp JsonDeserializer

Nếu exception thoát từ poll trước khi ErrorHandlingDeserializer đóng gói thông tin, listener container có thể không có record phục hồi đầy đủ. Không nên chỉ thêm DeadLetterPublishingRecoverer mà bỏ qua cấu hình wrapper.

### DLT producer chỉ dùng JsonSerializer

Recoverer chuẩn bị gửi byte[] nhưng producer chọn serializer chỉ dành cho OrderEvent. Record có thể không được publish hoặc bị biến đổi. Cần hỗ trợ byte[] ở producer DLT.

### Recoverer tùy biến dùng record.value() để tạo bản ghi DLT

Khi deserialize thất bại, record.value() có thể null. Nếu custom recoverer không dùng exception metadata, DLT nhận null và mất raw bytes. Hãy dùng cơ chế phục hồi của Spring Kafka hoặc xử lý raw bytes từ metadata một cách có chủ đích.

### DLT consumer lại dùng JsonDeserializer<OrderEvent>

DLT consumer gặp lại lỗi deserialize và có thể không đọc được record. Với luồng điều tra, dùng ByteArrayDeserializer và chỉ parse theo schema khi cần.

### Hệ thống copy record mà không copy headers

Raw bytes có thể còn, nhưng original topic/offset hoặc exception metadata mất. Dùng event ID và preserve headers theo chính sách rõ ràng.

### Producer DLT ghi thiếu acknowledgement

Ứng dụng có thể tưởng rằng đã gửi DLT nhưng publish thực sự thất bại. Cần quan sát kết quả send, retry/recovery failure và commit offset nguồn.

### DLT retention quá ngắn

Payload được ghi đúng nhưng đã hết hạn trước khi nhóm vận hành điều tra. Cần cấu hình retention đáp ứng quy trình xử lý sự cố.

## 17. DLT publish failure và commit offset

Chuyển record lỗi sang DLT là một thao tác Kafka produce. Nó có thể thất bại do broker unavailable, ACL thiếu, partition đích không tồn tại, serializer lỗi, record quá lớn hoặc timeout.

Khi publish DLT thất bại, không được tự coi record đã recovery thành công. Cần xác định phiên bản Spring Kafka có chờ send result và phát hiện lỗi publish theo cấu hình recoverer hay không; có thể cần bật tùy chọn fail-on-send-error hoặc kiểm soát send result tương ứng.

Nếu record DLT đã được publish nhưng offset nguồn chưa commit trước khi ứng dụng crash, record gốc có thể được giao lại và được publish lần nữa. Hai record DLT có thể chứa cùng raw bytes và cùng original topic/partition/offset nhưng có DLT offset khác nhau.

~~~text
orders/P2/105
   |
   +--> orders.DLT/P2/18
   |
   | crash trước commit nguồn
   |
   +--> orders.DLT/P2/19

Hai DLT record có thể cùng nguồn.
~~~

Vì vậy, giữ original value giúp điều tra, **không tự bảo đảm exactly-once**. Khi xử lý lỗi hoặc replay, cần dùng event ID, content hash hoặc tổ hợp provenance phù hợp để phát hiện bản ghi trùng; quyết định deduplicate phải dựa trên semantics của nghiệp vụ.

## 18. Kiểm thử phục hồi bytes bằng Kafka integration test

Một bài kiểm thử hữu ích nên gửi **bytes thực sự không hợp lệ** vào Kafka và xác nhận DLT giữ nguyên bytes đó.

Ví dụ ý tưởng test:

~~~java
byte[] invalidJson =
        "{\"orderId\":\"O-1001\",\"amount\":}".getBytes(
                StandardCharsets.UTF_8);

rawProducer.send(
        new ProducerRecord<>(
                "orders",
                "O-1001".getBytes(StandardCharsets.UTF_8),
                invalidJson));

// Chờ consumer chính xử lý lỗi và recoverer publish DLT.
// DLT consumer dùng ByteArrayDeserializer.
ConsumerRecord<byte[], byte[]> dltRecord =
        awaitDltRecord("orders.DLT");

assertThat(dltRecord.value())
        .containsExactly(invalidJson);
~~~

Trong ví dụ, rawProducer và awaitDltRecord là hạ tầng test do ứng dụng cung cấp, không phải API có sẵn. Có thể dùng EmbeddedKafka hoặc Testcontainers Kafka để chạy kiểm thử tích hợp. Nên chờ theo điều kiện có timeout thay vì sleep cố định dài.

Các trường hợp nên kiểm thử:

1. Value JSON sai: value DLT là bytes ban đầu, không phải null.
2. Value hợp lệ nhưng business listener lỗi: DLT producer serialize object đúng.
3. Key deserialize lỗi: DLT có key bytes tương ứng.
4. Cả key và value đều lỗi: DLT giữ được hai phần raw bytes khi cấu hình hỗ trợ.
5. DLT producer thiếu serializer byte[]: test phát hiện publish failure thay vì âm thầm bỏ record.
6. DLT consumer dùng ByteArrayDeserializer: đọc được payload lỗi.
7. Original topic/partition/offset headers: metadata phục vụ điều tra được giữ đúng.
8. Crash/restart: không giả định chỉ có một record DLT duy nhất.
9. Payload chứa bytes không phải UTF-8: giữ nguyên bytes, không tự decode rồi encode lại.
10. DLT publish không thành công: error handler có hành vi thất bại/retry phù hợp, không commit sai.

Nếu test chỉ gửi JSON hợp lệ rồi cố tình throw RuntimeException trong listener, test đó **không chứng minh** đường khôi phục raw bytes khi deserialization thất bại. Phải tạo lỗi ngay tại delegate deserializer để kiểm tra đúng tính năng.

## 19. Vận hành và quan sát

Khi phát sinh lỗi deserialize ở production, những thông tin quan trọng nhất là:

- Topic/partition/offset nguồn.
- Topic/partition/offset trên DLT.
- Key có deserialize thành công không.
- Value có deserialize thành công không.
- Số bytes được lưu vào DLT.
- Exception class, root cause và schema/version liên quan.
- Producer application hoặc producer client ID nếu có.
- Kết quả publish DLT và các lần recovery thất bại.
- Số record đang tồn tại ở DLT và thời gian chờ điều tra.

Ví dụ log được khuyến nghị:

~~~text
eventId=unknown
original=orders/P2/105
dlt=orders.DLT/P2/18
failurePhase=value-deserialization
exception=JsonParseException
originalValueSize=31
dltValueSize=31
recovery=published
~~~

Không log toàn bộ raw bytes chỉ để tạo dashboard. Với dữ liệu lỗi có thể chứa PII hoặc credentials, nên lưu trong hệ thống có retention và quyền truy cập phù hợp. Nếu cần hiển thị một phần payload, áp dụng masking và giới hạn kích thước.

Metric nên thống kê số lỗi theo topic và exception category, số lần DLT publish thành công/thất bại, số record DLT chưa giải quyết và tuổi backlog. Tránh đưa offset, event ID hoặc full payload vào metric label vì cardinality rất cao.

## 20. Bảo mật khi lưu dữ liệu chưa deserialize

Raw bytes có thể chứa dữ liệu không mong đợi hoặc cố ý độc hại. Việc giữ nguyên chúng trên DLT hữu ích cho điều tra nhưng cần bảo vệ:

- DLT có ACL hạn chế hơn topic chính nếu payload chứa dữ liệu nhạy cảm.
- Không tự động parse hoặc thực thi nội dung từ DLT trong công cụ điều tra thiếu sandbox.
- Giới hạn kích thước hiển thị, tải xuống và lưu trữ.
- Áp dụng retention theo chính sách bảo mật và tuân thủ.
- Không chấp nhận type header tùy ý từ record không tin cậy chỉ để replay thành công.
- Tránh log serialized exception chứa thông tin môi trường, stack trace hoặc nội dung payload ngoài phạm vi cần thiết.

DLT không phải nơi miễn trừ kiểm tra dữ liệu đầu vào. Một record bị lỗi deserialize vẫn phải được coi là dữ liệu không tin cậy cho đến khi được kiểm chứng và xử lý bởi cơ chế phù hợp.

## 21. Những hiểu nhầm thường gặp

**Listener có thể bắt mọi lỗi deserialize bằng try/catch.** Không đúng. Lỗi thường xuất hiện trước khi listener được gọi, trong consumer deserializer.

**Record có value=null nghĩa là original bytes đã mất.** Không nhất thiết. Với ErrorHandlingDeserializer, raw bytes có thể được giữ trong DeserializationException header để recoverer sử dụng.

**Chỉ dùng DeadLetterPublishingRecoverer là đủ để giữ original bytes.** Không đúng cho mọi cấu hình. Consumer phải bảo toàn thông tin lỗi deserialize, producer DLT phải hỗ trợ byte[].

**JsonSerializer có thể ghi mọi raw bytes đúng như broker nhận.** Không nên giả định. Nếu mục tiêu là giữ nguyên byte[], dùng ByteArraySerializer hoặc serializer lựa chọn đúng theo runtime type.

**DLT consumer nên dùng cùng JsonDeserializer như topic chính.** Không phù hợp cho mọi record. Payload đã sai có thể tiếp tục deserialize lỗi; ByteArrayDeserializer giúp đọc raw bytes để điều tra.

**Original value là object Java trước khi producer serialize.** Không đúng. Nó là bytes của Kafka record trước khi consumer deserialize, vốn có thể đã khác object gốc ở producer.

**Mọi lỗi deserialize nên retry nhiều lần.** Không đúng. Lỗi payload sai hoặc schema không tương thích thường cần sửa dữ liệu hoặc code; retry không tự khắc phục.

**Đã publish DLT thành công nghĩa là không có record trùng.** Không đúng. Nếu offset nguồn chưa commit, record có thể được xử lý và chuyển DLT lại.

**Có original topic và offset là replay sẽ luôn thành công.** Không đúng. Record nguồn có thể hết retention và payload có thể vẫn sai; replay phải có quy trình xử lý lỗi và idempotency.

## 22. Hướng dẫn triển khai

Để khôi phục original value vào DLT một cách đáng tin cậy:

1. Dùng ErrorHandlingDeserializer bọc delegate của key/value cần bảo vệ.
2. Phân loại lỗi deserialize, chuyển các lỗi dữ liệu permanent sang DLT phù hợp.
3. Cấu hình DeadLetterPublishingRecoverer với topic/partition đích đã provision.
4. Chuẩn bị KafkaTemplate của recoverer hỗ trợ cả object bình thường và raw byte[].
5. Với key có thể lỗi, hỗ trợ ByteArraySerializer cho key trong DLT producer.
6. Dùng ByteArrayDeserializer ở consumer DLT phục vụ điều tra, không ép payload lỗi thành object.
7. Giữ original topic/partition/offset và exception metadata tách biệt với current DLT metadata.
8. Kiểm thử bằng raw bytes cố ý sai cú pháp và so sánh byte-for-byte ở DLT.
9. Giám sát publish failure, DLT backlog, retention và quyền truy cập.
10. Thiết kế replay và data repair có kiểm soát, giữ event correlation và idempotency.

**Khôi phục original value vào DLT** không có nghĩa sửa dữ liệu lỗi ngay lập tức. Nó là cơ chế **không làm mất bằng chứng gốc** khi consumer không thể deserialize record. Khi ErrorHandlingDeserializer giữ raw bytes và DeadLetterPublishingRecoverer gửi chúng qua producer có serializer phù hợp, đội vận hành có thể xem lại payload chính xác, tìm nguyên nhân schema/format, sửa hệ thống rồi replay an toàn. Để đạt reliability end-to-end, vẫn phải xử lý offset, publish failure, duplicates, bảo mật và quy trình khôi phục nghiệp vụ.
