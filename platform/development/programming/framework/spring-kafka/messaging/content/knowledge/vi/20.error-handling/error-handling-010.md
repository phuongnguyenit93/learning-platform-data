# Xử lý lỗi deserialize trước listener

Kafka consumer nhận key và value dưới dạng byte, sau đó gọi deserializer để chuyển chúng thành kiểu dữ liệu mà ứng dụng sử dụng. Quá trình này diễn ra bên trong vòng `poll()` của Kafka consumer, trước khi Spring Kafka gọi phương thức `@KafkaListener`.

Nếu byte không đúng định dạng, JSON không hợp lệ, schema không tương thích hoặc deserializer ném exception, listener method có thể chưa được gọi. Vì vậy, `try/catch` đặt bên trong listener không xử lý được lỗi deserialize xảy ra trước listener. Spring Kafka cung cấp `ErrorHandlingDeserializer` để bọc deserializer thực tế, ghi nhận lỗi vào header của record và cho phép container error handler xử lý theo chính sách retry hoặc dead-letter.

Bài học thuộc chương **Xử lý lỗi** của module **SPRING_KAFKA_MESSAGING**. Module tập trung xây dựng ứng dụng gửi nhận sự kiện bằng Spring Kafka, `KafkaTemplate` và `@KafkaListener`, hiểu topic, partition, offset và consumer group; đồng thời học serialization, retry, dead-letter, transaction, exactly-once, xử lý đồng thời và kiểm thử để vận hành luồng messaging tin cậy.

## 1. Deserialize diễn ra trước khi listener được gọi

Luồng nhận record thường diễn ra theo thứ tự:

1. Consumer gọi `poll()` để lấy dữ liệu từ broker.
2. Kafka client nhận key/value bytes của record.
3. ErrorHandlingDeserializer gọi delegate key/value deserializer để chuyển byte thành kiểu Java.
4. Spring Kafka chuyển record đã deserialize đến listener container.
5. Container gọi phương thức `@KafkaListener`.
6. Listener xử lý nghiệp vụ và container quản lý acknowledgement/commit theo cấu hình.

~~~mermaid
flowchart TD
    A[Kafka broker trả record bytes] --> B[Consumer poll]
    B --> C[ErrorHandlingDeserializer wrapper]
    C --> D[Delegate key/value deserializer]
    D --> E{Deserialize thành công?}
    E -->|Có| F[Spring listener container]
    F --> G[@KafkaListener method]
    G --> H[Xử lý nghiệp vụ]
    E -->|Không| I[Exception và raw bytes]
    I --> J[Metadata trong record header]
    J --> K[Container error handler]
    K --> L[Retry hoặc DLT]
~~~

Nếu không có cơ chế bọc deserializer, exception có thể thoát ra từ `poll()`. Khi đó container không có một record Java bình thường để truyền vào listener method. Đây là khác biệt cốt lõi giữa lỗi deserialize và lỗi nghiệp vụ trong listener.

## 2. Phân biệt deserialize error và listener error

Hai lỗi xảy ra ở hai thời điểm khác nhau và cần cách xử lý khác nhau:

| Loại lỗi | Thời điểm | Listener method được gọi? | Ví dụ |
| --- | --- | --- | --- |
| Deserialization error | Trong poll, khi chuyển byte thành key/value | Thường không | JSON sai cú pháp, schema không tương thích, type header không hợp lệ |
| Message conversion error | Khi chuyển record/payload thành tham số listener | Có thể chưa vào được method | Không chuyển được payload sang kiểu tham số |
| Listener/business error | Trong lúc chạy code listener | Có | Database timeout, validation nghiệp vụ thất bại |
| Downstream error | Trong lời gọi hệ thống ngoài | Có | HTTP 503, connection pool cạn |

Ví dụ listener có try/catch:

~~~java
@KafkaListener(topics = "order-events", groupId = "billing-service")
public void onOrderEvent(OrderEvent event) {
    try {
        billingService.process(event);
    }
    catch (Exception exception) {
        log.error("Không xử lý được order event", exception);
    }
}
~~~

Đoạn code trên chỉ bắt exception phát sinh sau khi listener method được gọi. Nếu `JsonDeserializer` ném exception trong `poll()`, biến `event` chưa được tạo và method không được gọi. Do đó, cần xử lý ở tầng deserializer/container.

## 3. Vì sao lỗi deserialize có thể làm consumer không tiến triển?

Giả sử partition chứa các record:

~~~text
order-events-0

offset 100: JSON hợp lệ
offset 101: JSON không hợp lệ
offset 102: JSON hợp lệ
~~~

Consumer đọc offset 100 thành công. Khi poll đến record 101, deserializer lỗi. Nếu exception không được chuyển thành record có thể xử lý, consumer không thể đưa record đó vào listener như bình thường.

Nếu lỗi lặp lại ở cùng offset, consumer có thể liên tục gặp lại lỗi và không tiến tới offset 102. Đây là tình huống poison record: một record lỗi có thể chặn tiến độ của partition.

Không nên bỏ qua lỗi một cách tùy tiện. Cần giữ lại thông tin record, xác định nguyên nhân, sau đó chọn retry, DLT, sửa dữ liệu hoặc replay theo quy trình có kiểm soát.

## 4. ErrorHandlingDeserializer giải quyết vấn đề gì?

`ErrorHandlingDeserializer` là wrapper deserializer của Spring Kafka. Nó bọc một deserializer delegate, ví dụ `StringDeserializer` hoặc `JsonDeserializer`.

Khi delegate deserialize thành công, wrapper trả về object bình thường. Khi delegate ném exception, wrapper:

- Ghi nhận thông tin exception và raw bytes của dữ liệu lỗi.
- Đưa metadata lỗi vào Kafka record header theo cơ chế của Spring Kafka.
- Trả về giá trị null cho phần key/value deserialize thất bại, thay vì để exception thoát trực tiếp khỏi poll.
- Cho phép container error handler nhận diện record có lỗi deserialize và thực hiện recovery.

~~~text
Kafka Consumer
    |
    v
ErrorHandlingDeserializer
    |
    +-- delegate deserialize thành công --> Object
    |
    +-- delegate ném exception
            |
            +--> lưu DeserializationException và raw bytes trong header
            |
            +--> trả null cho phần bị lỗi
            |
            v
       Container error handling
            |
            +--> retry / recover / DLT
~~~

Wrapper không tự sửa payload và không làm JSON sai trở thành JSON hợp lệ. Mục tiêu của nó là giữ thông tin lỗi và đưa record vào đường xử lý lỗi mà Spring Kafka có thể quản lý.

## 5. Cấu hình ErrorHandlingDeserializer trong Spring Boot

Cách cấu hình phổ biến là khai báo wrapper cho cả key và value, sau đó chỉ định delegate tương ứng:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: billing-service
      enable-auto-commit: false
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.orders.OrderEvent
        spring.json.trusted.packages: com.example.orders
~~~

Trong cấu hình này:

- `key-deserializer` là ErrorHandlingDeserializer.
- `spring.deserializer.key.delegate.class` chỉ định StringDeserializer để giải mã key.
- `value-deserializer` cũng là ErrorHandlingDeserializer.
- `spring.deserializer.value.delegate.class` chỉ định JsonDeserializer để giải mã value.
- `spring.json.value.default.type` cung cấp kiểu Java mặc định cho JSON value.
- `spring.json.trusted.packages` giới hạn package được phép khi JsonDeserializer xử lý type information.

Nếu ứng dụng chỉ có value cần deserialize phức tạp, vẫn có thể cấu hình wrapper cho value và giữ key deserializer phù hợp. Tuy nhiên, bọc cả hai phía giúp xử lý cả key bytes lỗi định dạng nếu key dùng custom serializer/deserializer.

Không đặt trusted packages thành `*` chỉ để tránh lỗi type. Hãy giới hạn theo event type consumer thực sự nhận và không phụ thuộc type header chứa class nội bộ từ service khác nếu có thể dùng type mapping hoặc contract trung lập.

## 6. Cấu hình delegate bằng Java

Có thể cấu hình wrapper bằng Java khi cần tạo deserializer theo chương trình:

~~~java
@Bean
public ConsumerFactory<String, OrderEvent> consumerFactory() {
    Map<String, Object> props = new HashMap<>();

    props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
    props.put(ConsumerConfig.GROUP_ID_CONFIG, "billing-service");
    props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);

    JsonDeserializer<OrderEvent> jsonDelegate =
        new JsonDeserializer<>(OrderEvent.class);

    ErrorHandlingDeserializer<OrderEvent> valueDeserializer =
        new ErrorHandlingDeserializer<>(jsonDelegate);

    return new DefaultKafkaConsumerFactory<>(
        props,
        new StringDeserializer(),
        valueDeserializer
    );
}
~~~

Ví dụ này bọc value deserializer. Key vẫn dùng StringDeserializer. Nếu cần bọc key, tạo ErrorHandlingDeserializer cho key và truyền vào constructor tương ứng của ConsumerFactory.

Khi cấu hình qua constructor, không đồng thời cấu hình delegate theo cách xung đột qua properties. Hãy chọn một cách tạo delegate rõ ràng và kiểm tra ConsumerFactory thực tế mà listener container đang dùng.

## 7. Exception metadata được lưu ở đâu?

Khi deserialize thất bại, ErrorHandlingDeserializer thêm thông tin exception vào header đặc biệt của record. Spring Kafka cung cấp các constant để truy cập header lỗi cho key và value, thay vì ứng dụng phải tự hard-code tên header.

Hai trường hợp:

- Lỗi key deserialization: metadata lỗi key được gắn vào header tương ứng.
- Lỗi value deserialization: metadata lỗi value được gắn vào header tương ứng.

Thông tin lỗi bao gồm exception và raw bytes cần thiết để phục hồi hoặc gửi record sang DLT. Header này là metadata nội bộ phục vụ Spring Kafka error handling; không nên coi nó là một header nghiệp vụ ổn định để các service khác phụ thuộc.

Nếu listener nhận được record có giá trị null, không nên kết luận ngay producer đã gửi null. Null có thể là kết quả của deserialize failure được ErrorHandlingDeserializer ghi nhận. Cần kiểm tra exception header trước khi xử lý null như dữ liệu nghiệp vụ.

## 8. Phân biệt value null thật và deserialize failure

Có thể có nhiều nguyên nhân khiến record có value null:

1. Producer gửi value null có chủ đích.
2. Topic compacted nhận tombstone với key khác null và value null.
3. ErrorHandlingDeserializer trả null vì value bytes không giải mã được.
4. Một converter hoặc mapping khác tạo ra payload null.

Do đó, null payload không đủ để xác định record có lỗi deserialize.

Khi dùng ErrorHandlingDeserializer cùng container error handler, Spring Kafka có thể phát hiện exception header và chuyển record cho error handler trước khi gọi listener method. Vì vậy, không nên mặc định rằng listener sẽ nhận được record có value null để tự kiểm tra header.

Nếu triển khai custom error handler hoặc recoverer, có thể kiểm tra các header bằng constant `ErrorHandlingDeserializer.VALUE_DESERIALIZER_EXCEPTION_HEADER` và `ErrorHandlingDeserializer.KEY_DESERIALIZER_EXCEPTION_HEADER`. Dùng `ConsumerRecord.headers().lastHeader(...)` để xem metadata lỗi tương ứng. Chỉ tự xử lý null trong listener khi cấu hình thực tế cho phép record đi tới listener và ứng dụng đã định nghĩa rõ acknowledgement, retry, raw-byte retention.

Trong luồng thông thường, hãy để container error handler chịu trách nhiệm recovery record lỗi. Tránh chỉ log rồi return từ listener, vì container có thể coi lần gọi là thành công và tiến offset trong khi raw payload chưa được lưu.

## 9. DefaultErrorHandler xử lý deserialization exception

`DefaultErrorHandler` là error handler phổ biến trong Spring Kafka hiện đại. Nó hỗ trợ retry, backoff và recovery cho record listener; có thể kết hợp với `DeadLetterPublishingRecoverer` để gửi record không thể xử lý sang DLT.

Ví dụ cấu hình:

~~~java
@Bean
public DefaultErrorHandler kafkaErrorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    FixedBackOff backOff = new FixedBackOff(1_000L, 2L);

    DefaultErrorHandler handler =
        new DefaultErrorHandler(recoverer, backOff);

    return handler;
}
~~~

Ví dụ trên minh họa backoff một giây và tối đa hai lần retry sau lần xử lý đầu tiên trước khi recoverer được gọi. Error handler có thể được gắn vào listener container factory hoặc cấu hình theo cơ chế Spring Kafka của ứng dụng.

Một số exception như DeserializationException được DefaultErrorHandler phân loại là fatal/non-retryable theo mặc định ở các phiên bản hiện đại, vì retry cùng một payload không hợp lệ thường không làm dữ liệu tự sửa. Hãy kiểm tra danh sách phân loại của phiên bản Spring Kafka đang dùng và tùy chỉnh có chủ đích nếu có lỗi deserialize thực chất do dependency tạm thời.

## 10. Gắn DefaultErrorHandler vào listener container factory

Ví dụ factory cho record listener:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        orderListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            DefaultErrorHandler kafkaErrorHandler) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(kafkaErrorHandler);
    return factory;
}
~~~

Listener dùng factory:

~~~java
@KafkaListener(
    id = "orderListener",
    topics = "order-events",
    groupId = "billing-service",
    containerFactory = "orderListenerFactory"
)
public void onOrderEvent(OrderEvent event) {
    billingService.process(event);
}
~~~

`setCommonErrorHandler` gắn error handler cho các listener container được tạo từ factory đó. Nếu ứng dụng có nhiều factory, cần bảo đảm factory đang được listener sử dụng đã được cấu hình đúng.

Không nên chỉ khai báo bean DefaultErrorHandler rồi giả định mọi listener tự động dùng nó nếu dự án có custom container factory hoặc wiring riêng. Hãy xác minh cấu hình thực tế trong application context.

## 11. Chuyển record lỗi sang Dead Letter Topic

`DeadLetterPublishingRecoverer` là recoverer phổ biến để publish record lỗi sang dead-letter topic (DLT). DLT lưu lại record không thể xử lý ở luồng chính để đội vận hành điều tra, sửa dữ liệu hoặc replay.

Ví dụ tạo recoverer:

~~~java
@Bean
public DeadLetterPublishingRecoverer deadLetterPublishingRecoverer(
        KafkaTemplate<Object, Object> dltTemplate) {

    return new DeadLetterPublishingRecoverer(dltTemplate);
}
~~~

Với cấu hình mặc định phổ biến, recoverer tạo topic đích dựa trên tên topic nguồn cộng hậu tố `.DLT` và giữ partition tương ứng. Topic DLT cần được tạo sẵn hoặc có cơ chế tạo topic phù hợp; nếu giữ nguyên partition number, DLT cần đủ partition tương ứng với topic nguồn.

Có thể tùy chỉnh destination resolver để gửi vào tên topic riêng:

~~~java
@Bean
public DeadLetterPublishingRecoverer deadLetterPublishingRecoverer(
        KafkaTemplate<Object, Object> dltTemplate) {

    return new DeadLetterPublishingRecoverer(
        dltTemplate,
        (record, exception) ->
            new TopicPartition("deserialization-errors", record.partition())
    );
}
~~~

Ví dụ này minh họa định tuyến vào một DLT tập trung. Topic đích vẫn phải có partition index tương ứng; nếu số partition không đủ, publish có thể thất bại. Có thể chọn partition khác hoặc dùng resolver phù hợp topology nếu muốn gom lỗi từ nhiều topic.

## 12. DLT cần giữ raw bytes khi deserialize thất bại

Một điểm quan trọng: khi value deserialization thất bại, object value không có sẵn; ErrorHandlingDeserializer trả null và lưu raw bytes cùng exception metadata. Khi recoverer gửi record sang DLT, Spring Kafka có thể khôi phục byte gốc từ metadata lỗi để DLT giữ được payload lỗi.

Vì vậy, producer dùng để publish DLT phải serialize được cả:

- Object đã deserialize bình thường trong các trường hợp recovery khác.
- `byte[]` gốc của record có lỗi deserialize.

Nếu DLT template chỉ dùng JsonSerializer cho mọi value, việc publish raw byte[] có thể không đúng định dạng hoặc thất bại. Cần cấu hình serializer hỗ trợ cả byte[] và object thông thường, ví dụ dùng `DelegatingByTypeSerializer` với delegate ByteArraySerializer cho byte[] và JsonSerializer cho object.

Ví dụ khung cấu hình value serializer:

~~~java
Map<Class<?>, Serializer<?>> delegates = new LinkedHashMap<>();
delegates.put(byte[].class, new ByteArraySerializer());
delegates.put(Object.class, new JsonSerializer<>());

DelegatingByTypeSerializer valueSerializer =
    new DelegatingByTypeSerializer(delegates);
~~~

Đặt byte[] trước Object trong map để loại dữ liệu cụ thể được chọn trước delegate tổng quát. Cấu hình key serializer cũng cần hỗ trợ kiểu key thực tế và raw byte[] nếu key deserialization có thể thất bại.

Hãy kiểm thử DLT bằng payload byte lỗi thật, rồi đọc DLT dưới dạng byte[] để xác nhận raw payload được bảo toàn. Không chỉ kiểm tra DLT có record; cần kiểm tra key/value bytes và exception headers.

## 13. Retry có phù hợp với mọi lỗi deserialize không?

Không phải lỗi deserialize nào cũng nên retry.

| Nguyên nhân | Retry có ích? | Hướng xử lý |
| --- | --- | --- |
| JSON sai cú pháp | Thường không | DLT, điều tra producer hoặc sửa dữ liệu. |
| Field đổi kiểu không tương thích | Thường không | Kiểm tra schema evolution và version contract. |
| Type header trỏ tới class không tồn tại | Thường không | Dùng type mapping/contract ổn định. |
| Schema Registry tạm thời không truy cập được | Có thể | Retry có backoff và giới hạn; theo dõi dependency. |
| Custom deserializer lỗi do cấu hình tạm thời | Có thể | Khôi phục dependency/configuration rồi retry có kiểm soát. |
| Payload bị cắt hoặc bytes hỏng | Thường không | DLT và điều tra nguồn phát hoặc đường truyền. |

DefaultErrorHandler có phân loại exception mặc định; nếu muốn thay đổi, hãy cấu hình retryable/non-retryable theo nguyên nhân thực tế. Không nên đánh dấu mọi DeserializationException là retryable vì poison record có thể chặn partition trong thời gian dài.

Nếu exception wrapper che mất nguyên nhân cụ thể, có thể inspect cause chain hoặc metadata DeserializationException để phân loại. Hãy giữ số lần retry hữu hạn và backoff phù hợp.

## 14. Offset và poison record

Nếu record lỗi được retry blocking, partition có thể chưa tiến qua record đó cho đến khi xử lý thành công hoặc recoverer hoàn tất. Khi recoverer gửi record sang DLT thành công và error handler ghi nhận recovery, container có thể tiến offset theo semantics của handler và AckMode.

Điều này giúp partition tiếp tục xử lý record sau, nhưng có một số điều cần lưu ý:

- DLT publish phải thành công trước khi record nguồn được coi là recovered.
- Nếu DLT publish thất bại, error handler có thể tiếp tục retry recovery theo cấu hình.
- Commit offset cần theo đúng semantics container và transaction.
- Record chưa commit có thể được đọc lại sau crash/rebalance.
- Không được bỏ qua record chỉ để làm lag giảm nếu chưa lưu raw bytes hoặc có quyết định nghiệp vụ rõ.

DLT là vùng lưu record lỗi để điều tra, không phải nơi tự động sửa schema. Muốn replay, cần sửa consumer/producer contract hoặc chuyển đổi record sang định dạng được hỗ trợ rồi gửi lại luồng phù hợp.

## 15. Lỗi key deserialization và value deserialization

Kafka key và value có deserializer riêng, nên lỗi có thể xảy ra ở một trong hai phía.

**Lỗi key:**

- Key có thể trở thành null sau khi wrapper ghi nhận lỗi.
- Raw key bytes được giữ trong exception metadata.
- Partitioner không còn liên quan vì record đã nằm trong partition; consumer đang đọc key từ log.
- DLT cần serializer hỗ trợ raw byte[] cho key.

**Lỗi value:**

- Value có thể trở thành null sau khi wrapper ghi nhận lỗi.
- Raw value bytes được giữ trong exception metadata.
- Listener không nên xử lý null như payload bình thường nếu có exception header.
- DLT cần giữ raw value để có thể phân tích/replay.

Không nên chỉ bọc value deserializer nếu key cũng có thể chứa dữ liệu không hợp lệ và cần được xử lý có kiểm soát. Ngược lại, không cần bọc key nếu contract key đơn giản, đáng tin cậy và lỗi key không thuộc phạm vi xử lý.

## 16. Batch listener và lỗi deserialize

Với batch listener, một lần poll có thể trả nhiều record. Nếu một record trong batch không deserialize được, ErrorHandlingDeserializer có thể giữ lỗi trong header của record đó và trả null cho phần key/value lỗi. Cách ứng dụng xử lý cần phù hợp với batch converter và error handler.

Nếu listener nhận `List<ConsumerRecord<K,V>>`, có thể kiểm tra từng record và header lỗi trước khi xử lý nghiệp vụ. Không nên giả định mọi phần tử đều có payload hợp lệ.

Nếu listener nhận `List<V>` đã convert, cần xác định converter có giữ được metadata lỗi và raw record hay không. Với batch cần recovery chính xác theo record, nhận ConsumerRecord thường giúp quan sát topic/partition/offset và header lỗi tốt hơn.

Khi batch listener thất bại, có thể dùng `BatchListenerFailedException` để chỉ ra index record lỗi cho DefaultErrorHandler. Tuy nhiên, lỗi deserialize phát sinh trước khi listener chạy có semantics riêng; hãy kiểm thử với phiên bản Spring Kafka và batch factory cụ thể, đặc biệt khi cần DLT cho từng record.

## 17. Quan sát và điều tra deserialization failure

Khi record bị đưa sang DLT, log và metric nên đủ để truy ra nguồn:

- Topic, partition, offset nguồn.
- Consumer group và client ID.
- Lỗi ở key hay value.
- Exception class và cause chain.
- Event ID hoặc correlation ID nếu đọc được từ metadata.
- Kích thước raw payload và schema/type version nếu có.
- Số lần retry và thời điểm recovery.
- DLT topic, partition và offset mới.

Không log toàn bộ raw bytes mặc định vì payload có thể chứa dữ liệu nhạy cảm hoặc quá lớn. Có thể log payload length, hash hoặc một đoạn đã được kiểm soát theo chính sách bảo mật.

Theo dõi thêm:

- Số lỗi deserialize theo topic/group.
- DLT publish success/failure.
- Retry count và recovery count.
- Consumer lag của topic nguồn.
- Số record nằm trong DLT.
- Lỗi schema registry hoặc dependency liên quan.

Nếu lỗi tăng đột ngột sau deploy producer, kiểm tra serializer, schema version, type header và payload fixture mới. Nếu nhiều topic cùng lỗi, điều tra dependency chung như schema registry hoặc cấu hình deserializer.

## 18. Kiểm thử lỗi deserialize trước listener

Kiểm thử cần xác nhận listener không bị gọi với payload lỗi và record được xử lý theo chính sách.

Các kịch bản quan trọng:

1. Gửi JSON hợp lệ và xác nhận listener nhận đúng object.
2. Gửi JSON sai cú pháp và xác nhận ErrorHandlingDeserializer ghi nhận exception.
3. Xác nhận listener không xử lý payload lỗi như event hợp lệ.
4. Xác nhận DefaultErrorHandler áp dụng retry/recovery theo cấu hình.
5. Xác nhận record cuối cùng được gửi vào DLT.
6. Đọc DLT dạng byte[] và so sánh raw bytes với payload gửi ban đầu.
7. Kiểm tra lỗi key và lỗi value riêng biệt.
8. Kiểm tra DLT publish failure không làm offset nguồn bị commit sai.
9. Kiểm tra record tiếp theo trong partition có thể tiếp tục sau recovery.
10. Kiểm tra batch listener nếu ứng dụng có sử dụng batch mode.

Ví dụ unit test cho delegate deserializer:

~~~java
@Test
void invalidJsonShouldBeCapturedByErrorHandlingDeserializer() {
    JsonDeserializer<OrderEvent> delegate =
        new JsonDeserializer<>(OrderEvent.class);

    ErrorHandlingDeserializer<OrderEvent> deserializer =
        new ErrorHandlingDeserializer<>(delegate);

    Headers headers = new RecordHeaders();
    byte[] invalidJson = "{invalid-json".getBytes(StandardCharsets.UTF_8);

    OrderEvent result =
        deserializer.deserialize("order-events", headers, invalidJson);

    assertThat(result).isNull();
    assertThat(headers.lastHeader(
        ErrorHandlingDeserializer.VALUE_DESERIALIZER_EXCEPTION_HEADER
    )).isNotNull();
}
~~~

Đây là khung unit test minh họa. Cần khởi tạo/configure deserializer theo phiên bản Spring Kafka đang dùng và xác nhận header exception được ghi đúng. Integration test với broker mới chứng minh được container error handler và DLT recoverer đã được wiring đầy đủ.

## 19. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| try/catch trong listener không bắt được lỗi JSON | Exception xảy ra trong poll trước khi listener được gọi | Bọc delegate bằng ErrorHandlingDeserializer |
| Consumer lặp lại cùng offset | Deserialization exception không được chuyển vào container error handling | Kiểm tra EHD và container error handler |
| Listener nhận value null | Deserialize failure hoặc producer gửi null/tombstone | Kiểm tra exception header trước khi xử lý null |
| DLT không giữ payload gốc | DLT template không hỗ trợ byte[] hoặc raw bytes không được khôi phục | Dùng serializer theo kiểu và test raw bytes |
| DLT publish lỗi | Topic đích/partition không tồn tại hoặc serializer không tương thích | Kiểm tra DLT topology, ACL và template |
| Retry vô ích nhiều lần | Payload sai schema/format là lỗi không thể tự hết | Phân loại non-retryable và chuyển DLT |
| Consumer bị chặn bởi poison record | Recovery không hoàn tất hoặc handler không tiến offset | Kiểm tra retry, recoverer và commit semantics |
| Type header làm deserialize thất bại | Consumer không có class hoặc package không được tin cậy | Dùng default type/type mapping và contract ổn định |
| Key null ngoài dự kiến | Key deserializer lỗi hoặc key thật sự null | Kiểm tra key exception header |
| Batch xử lý sai record lỗi | Không giữ ConsumerRecord/header hoặc không xác định failed index | Kiểm thử batch converter và error handling riêng |

## 20. Checklist vận hành

Trước khi triển khai consumer production, hãy xác nhận:

1. Key/value deserializer được bọc bằng ErrorHandlingDeserializer khi cần quản lý lỗi deserialize.
2. Delegate class được cấu hình đúng cho từng phía key/value.
3. JsonDeserializer có default type/type mapping và trusted packages giới hạn.
4. Exception header được nhận diện trước khi coi null là dữ liệu hợp lệ.
5. DefaultErrorHandler được gắn vào đúng listener container factory.
6. Retry/backoff hữu hạn và phân loại lỗi có chủ đích.
7. DeadLetterPublishingRecoverer có destination resolver phù hợp.
8. DLT topic có đủ partition, retention và ACL.
9. DLT producer serializer hỗ trợ raw byte[] cùng object cần thiết.
10. DLT giữ được raw key/value và metadata điều tra.
11. Offset chỉ tiến sau khi recovery thành công theo semantics đã chọn.
12. Có metric/log cho deserialize failure, retry, DLT và consumer lag.
13. Có integration test với payload sai thật và broker.
14. Có quy trình điều tra, sửa contract và replay record lỗi.

Lỗi deserialize xảy ra trước listener nên cần được xử lý ở tầng deserializer và listener container. ErrorHandlingDeserializer biến exception thành metadata gắn với record, giúp DefaultErrorHandler và DeadLetterPublishingRecoverer retry hoặc chuyển record sang DLT. Khi cấu hình đúng cả raw bytes, serializer DLT, offset và chính sách retry, consumer có thể vượt qua poison record mà vẫn giữ dữ liệu cần thiết để điều tra và phục hồi.

