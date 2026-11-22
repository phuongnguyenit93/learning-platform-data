# DeserializationException

## 1. DeserializationException trong Spring Kafka

Kafka lưu key và value của record dưới dạng byte array. Khi consumer đọc record, Kafka client gọi deserializer để chuyển các byte đó thành kiểu dữ liệu mà ứng dụng sử dụng, chẳng hạn String, JSON object, Avro hoặc Protobuf.

Nếu dữ liệu không đúng định dạng, schema không tương thích, thiếu type information hoặc delegate deserializer ném exception, quá trình chuyển đổi có thể thất bại. Trong Spring Kafka, lỗi này thường được biểu diễn bằng `DeserializationException` và được đưa vào cơ chế xử lý lỗi của listener container.

Các nguyên nhân thường gặp:

- JSON sai cú pháp, bị cắt cụt hoặc không đúng encoding.
- Payload không khớp schema hoặc version event mà consumer mong đợi.
- Type header không hợp lệ hoặc không thể ánh xạ sang class.
- Deserializer không hỗ trợ định dạng byte được producer gửi.
- Schema registry không truy cập được hoặc không tìm thấy schema tương ứng.
- Key hoặc value rỗng nhưng ứng dụng/deserializer không chấp nhận.
- Dữ liệu được ghi bởi producer khác có serializer hoặc contract khác.

Điểm quan trọng trong vận hành: lỗi deserialize xảy ra trước khi phương thức listener nhận được payload. Vì vậy, một lỗi deserialize có thể khiến listener không được gọi cho record đó. Cần dùng cơ chế chuyển lỗi từ deserializer đến listener container để error handler có đủ thông tin về record, offset và partition mà phục hồi.

## 2. DeserializationException phát sinh ở đâu trong luồng đọc?

### 2.1. Luồng bình thường

Khi dữ liệu hợp lệ, đường đi cơ bản là:

1. Consumer poll record từ broker.
2. Kafka client lấy byte array của key và value.
3. Key deserializer và value deserializer chuyển bytes thành object.
4. Spring listener container nhận ConsumerRecord đã deserialize.
5. Container chuyển payload đến phương thức `@KafkaListener`.
6. Listener thực hiện nghiệp vụ.
7. Container commit offset theo acknowledgment mode nếu xử lý thành công.

~~~mermaid
sequenceDiagram
    participant B as Kafka broker
    participant C as Kafka consumer
    participant D as Deserializer
    participant LC as Spring listener container
    participant L as Listener

    C->>B: poll/fetch
    B-->>C: Record bytes
    C->>D: deserialize key/value
    D-->>C: Object
    C->>LC: ConsumerRecord
    LC->>L: Invoke listener
    L-->>LC: Success
    LC->>B: Commit offset theo ack mode
~~~

### 2.2. Luồng khi deserialize thất bại

Nếu deserializer ném exception, listener không nhận được object hợp lệ. Nếu dùng deserializer trực tiếp và exception thoát khỏi Kafka consumer poll, container có thể không có một ConsumerRecord bình thường để chuyển cho record-level error handler.

`ErrorHandlingDeserializer` của Spring Kafka giải quyết khoảng trống này: nó bọc deserializer thật (delegate), bắt lỗi deserialize, lưu thông tin lỗi cùng bytes gốc trong header đặc biệt và trả về giá trị null để consumer vẫn có thể chuyển record cùng metadata cho container.

~~~mermaid
sequenceDiagram
    participant B as Kafka broker
    participant C as Kafka consumer
    participant E as ErrorHandlingDeserializer
    participant LC as Spring listener container
    participant EH as Error handler
    participant DLT as Dead-letter topic

    C->>B: poll/fetch
    B-->>C: Record bytes
    C->>E: deserialize
    E->>E: Gọi delegate deserializer
    E-->>E: Exception khi chuyển đổi
    E->>E: Lưu exception và raw bytes vào header
    E-->>C: Record có payload null
    C->>LC: ConsumerRecord và header lỗi
    LC->>EH: Chuyển lỗi deserialize
    EH->>DLT: Publish record nếu recover
~~~

Container/error handler có thể phân loại record lỗi, bỏ qua retry không hữu ích, hoặc chuyển record sang DLT. Record vẫn giữ topic, partition, offset, timestamp và headers để điều tra.

### 2.3. Vì sao listener không được gọi?

Phương thức listener nhận payload đã deserialize. Khi value deserializer không thể tạo object, không có payload đúng kiểu để gọi phương thức listener thông thường.

Với ErrorHandlingDeserializer, container nhận được record có payload null kèm header chứa thông tin lỗi. Container phát hiện header này và chuyển lỗi đến error handler. Không nên coi payload null trong trường hợp này là một event nghiệp vụ hợp lệ.

Nếu ứng dụng cho phép value null hợp lệ (tombstone của compacted topic), cần phân biệt tombstone thật với null do deserialize thất bại bằng header lỗi. Chỉ kiểm tra payload null là chưa đủ.

## 3. DeserializationException và ErrorHandlingDeserializer

### 3.1. ErrorHandlingDeserializer là lớp bọc

`ErrorHandlingDeserializer` là deserializer của Spring Kafka, không phải serializer thay thế cho JSON, String hay Avro. Nó bọc một delegate deserializer thực hiện chuyển đổi thực tế.

Ví dụ với JSON:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.trusted.packages: com.example.events
~~~

Trong cấu hình này:

- Kafka dùng ErrorHandlingDeserializer cho value.
- ErrorHandlingDeserializer gọi JsonDeserializer làm delegate.
- Nếu JSON hợp lệ, listener nhận object đã deserialize.
- Nếu JSON không hợp lệ, wrapper lưu thông tin lỗi và bytes gốc trong header, rồi trả về null để container xử lý.

Nếu key cũng có thể lỗi deserialize, cần bọc key deserializer tương tự bằng thuộc tính delegate dành cho key. Chỉ bọc value không bảo vệ được trường hợp key deserializer thất bại.

### 3.2. Cấu hình bằng Java

Có thể tạo deserializer bằng Java và bọc delegate:

~~~java
Map<String, Object> consumerProperties = new HashMap<>();

consumerProperties.put(
    ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
    "localhost:9092"
);
consumerProperties.put(
    ConsumerConfig.GROUP_ID_CONFIG,
    "orders-service"
);
consumerProperties.put(
    ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,
    false
);
consumerProperties.put(
    ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
    StringDeserializer.class
);
consumerProperties.put(
    ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
    ErrorHandlingDeserializer.class
);
consumerProperties.put(
    ErrorHandlingDeserializer.VALUE_DESERIALIZER_CLASS,
    JsonDeserializer.class
);

ConsumerFactory<String, OrderCreated> consumerFactory =
    new DefaultKafkaConsumerFactory<>(consumerProperties);
~~~

Đây là ví dụ minh họa. Nếu dùng Spring Boot, nên giữ cấu hình trong một nguồn thống nhất để tránh consumer factory tùy chỉnh ghi đè các thuộc tính Boot. Khi cấu hình trực tiếp, kiểm tra đúng constant và API của phiên bản Spring Kafka đang chạy.

### 3.3. Delegate deserializer

Delegate là thành phần thực hiện deserialize thật. Ví dụ:

| Định dạng | Delegate thường dùng |
|---|---|
| Chuỗi UTF-8 | `StringDeserializer` |
| JSON object | `JsonDeserializer` của Spring Kafka |
| Byte array | `ByteArrayDeserializer` |
| Avro | Deserializer Avro tương ứng với schema registry |
| Protobuf | Deserializer Protobuf của thư viện được chọn |

Lỗi có thể đến từ delegate hoặc thành phần phụ thuộc của nó, ví dụ schema registry. ErrorHandlingDeserializer không tự sửa dữ liệu và không làm cho schema không tương thích trở thành hợp lệ. Nó chỉ chuyển lỗi thành thông tin mà container/error handler có thể xử lý.

## 4. Nội dung và header mang thông tin lỗi

### 4.1. Header lỗi deserialize

Khi delegate thất bại, ErrorHandlingDeserializer lưu thông tin exception vào header đặc biệt của record. Spring Kafka phân biệt lỗi ở key và value, thường dùng các header có tên:

- `springDeserializerExceptionKey`: lỗi khi deserialize key.
- `springDeserializerExceptionValue`: lỗi khi deserialize value.

Header chứa thông tin lỗi đã được serialize để có thể đi qua Kafka ConsumerRecord. Spring Kafka có thể đọc header này và tái tạo exception phù hợp cho error handling.

Tên header và chi tiết serialization là contract nội bộ của Spring Kafka; ứng dụng nên dùng API của framework để truy cập, không tự tạo hoặc chỉnh sửa header này theo cách thủ công. Header có thể bị xóa hoặc thay đổi trong quá trình xử lý, vì vậy cần lưu lại metadata lỗi trước khi thực hiện thao tác làm mất header nếu quy trình yêu cầu.

### 4.2. Raw bytes và dữ liệu gốc

Khi deserialize thất bại, giá trị null mà listener/container nhìn thấy không chứa payload ban đầu. Thông tin exception do ErrorHandlingDeserializer giữ lại có thể chứa bytes gốc, giúp error handler hoặc dead-letter recoverer khôi phục dữ liệu để chuyển sang DLT.

Đây là điểm quan trọng khi xử lý poison pill: record lỗi vẫn cần được bảo toàn để điều tra và replay. Nếu DLT chỉ chứa null mà không giữ raw bytes hoặc metadata gốc, đội vận hành có thể không tái tạo được nguyên nhân.

Không nên log toàn bộ raw bytes một cách mặc định. Payload có thể chứa dữ liệu cá nhân, token hoặc thông tin nhạy cảm. Hãy giới hạn quyền truy cập DLT, áp dụng retention phù hợp và chỉ trích xuất dữ liệu cần thiết cho điều tra.

### 4.3. Metadata hữu ích để chẩn đoán

Khi ghi nhận lỗi, giữ các trường:

- Topic nguồn.
- Partition và offset.
- Timestamp của record.
- Key nếu có thể đọc an toàn.
- Header correlation ID, trace ID hoặc event ID nếu có.
- Loại exception và cause chain.
- Kích thước payload và một fingerprint/hash nếu cần đối chiếu.
- Tên deserializer và schema/version dự kiến.

Nếu key deserialize cũng lỗi, không giả định key đã có dạng String hoặc object. Có thể phải dùng bytes gốc từ exception/header và ghi nhận rằng key không thể chuyển đổi.

## 5. Phân biệt deserialize lỗi với lỗi convert payload

Spring Kafka có nhiều bước chuyển đổi dữ liệu. Cần xác định lỗi xảy ra ở bước nào để chọn cơ chế xử lý phù hợp.

| Bước | Thành phần | Ví dụ lỗi | Listener có thể được gọi? |
|---|---|---|---|
| Bytes thành key/value | Kafka deserializer | JSON malformed, schema không tồn tại | Thường không có payload hợp lệ để gọi listener |
| Spring Message conversion | MessageConverter | Payload không chuyển được sang tham số listener | Listener method có thể chưa được gọi thành công |
| Mapping type | JsonDeserializer/type mapper | Type header không hợp lệ hoặc class không được tin cậy | Thất bại trong bước deserialize |
| Nghiệp vụ | Phương thức listener | Validation, database hoặc service lỗi | Listener đã được gọi |

`DeserializationException` nói đến lỗi chuyển bytes thành object ở tầng deserializer. Một exception do MessageConverter hoặc code nghiệp vụ ném ra là lỗi ở bước khác, dù cả hai đều có thể đi qua error handler.

Ví dụ:

- JSON sai cú pháp: lỗi ở JsonDeserializer.
- JSON hợp lệ nhưng class đích không được phép deserialize: lỗi mapping/type của deserializer.
- JSON đã thành object nhưng trường bắt buộc thiếu theo quy tắc nghiệp vụ: listener có thể nhận object rồi ném validation exception.
- Payload object hợp lệ nhưng database timeout: lỗi trong listener/downstream.

Không nên chuyển mọi exception thành DeserializationException. Hãy phân loại đúng tầng để retry và DLT có hành vi phù hợp.

## 6. Xử lý DeserializationException bằng DefaultErrorHandler

### 6.1. Vai trò của error handler

`DefaultErrorHandler` là error handler phổ biến của Spring Kafka cho record listener. Nó có thể phân loại exception, retry với backoff và gọi recoverer khi hết lượt thử.

Lỗi deserialize thường là lỗi không thể khắc phục bằng cách gửi lại cùng một byte sequence với cùng deserializer và schema. Vì vậy, retry liên tục thường không có ích và chỉ làm partition bị chặn lâu hơn.

Có thể cấu hình lỗi deserialize là fatal/non-retryable và chuyển thẳng đến recoverer. Trong Spring Kafka, các exception deserialize như DeserializationException thường được phân loại không retry bởi default classification của DefaultErrorHandler; hãy kiểm tra phiên bản và cấu hình classification nếu ứng dụng đã tùy chỉnh error handler.

### 6.2. Ví dụ dùng DefaultErrorHandler

~~~java
@Bean
public DefaultErrorHandler kafkaErrorHandler(
    DeadLetterPublishingRecoverer recoverer
) {
    var backOff = new FixedBackOff(1_000L, 2L);

    var errorHandler = new DefaultErrorHandler(recoverer, backOff);

    errorHandler.addNotRetryableExceptions(
        DeserializationException.class
    );

    return errorHandler;
}
~~~

Ví dụ minh họa cách khai báo. DefaultErrorHandler có thể đã phân loại lỗi deserialize là non-retryable theo mặc định; khai báo tường minh giúp chính sách của ứng dụng dễ đọc nhưng cần tránh đăng ký trùng hoặc ghi đè classification không chủ ý. Số lần retry và backoff phải dựa trên loại lỗi thực tế.

Đối với lỗi tạm thời ở downstream, retry có backoff có thể phù hợp. Đối với payload malformed, retry cùng bytes thường chỉ lặp lại cùng lỗi. Có thể chuyển record ngay đến DLT để giữ dữ liệu và tiếp tục xử lý các record phía sau theo chính sách.

### 6.3. Khi nào cần retry?

Phân loại theo nguyên nhân:

| Loại lỗi | Retry có ích? | Hướng xử lý |
|---|---|---|
| JSON sai cú pháp | Thường không | DLT, sửa producer hoặc dữ liệu |
| Schema ID không tồn tại | Có thể nếu schema registry tạm thời không truy cập được; nếu schema thực sự thiếu thì không | Phân biệt lỗi kết nối với schema không tồn tại |
| Type header không hợp lệ | Thường không | Kiểm tra producer contract và type mapping |
| Class đích không có trong ứng dụng | Không nếu artifact hiện tại không thay đổi | Sửa dependency hoặc mapping |
| Lỗi database sau deserialize | Có thể | Retry có backoff theo chính sách downstream |
| Timeout service ngoài | Có thể | Retry giới hạn, circuit breaker và DLT nếu thất bại |
| Payload quá lớn hoặc vượt giới hạn | Không với cùng payload | Điều chỉnh producer/broker hoặc thiết kế payload |

Một số exception của thư viện schema có thể đại diện cho lỗi mạng tạm thời hoặc lỗi contract vĩnh viễn. Không phân loại tất cả thành một nhóm chỉ dựa trên tên wrapper exception; hãy xem cause chain và mã lỗi cụ thể.

## 7. Chuyển record lỗi sang Dead Letter Topic

### 7.1. DeadLetterPublishingRecoverer

`DeadLetterPublishingRecoverer` là recoverer thường dùng để publish record không thể xử lý sang dead-letter topic (DLT). Nó giữ thông tin nguồn như topic, partition, offset và exception trong các dead-letter headers do Spring Kafka quản lý.

Ví dụ tạo recoverer:

~~~java
@Bean
public DeadLetterPublishingRecoverer deadLetterPublishingRecoverer(
    KafkaTemplate<Object, Object> dltTemplate
) {
    return new DeadLetterPublishingRecoverer(
        dltTemplate,
        (record, exception) ->
            new TopicPartition(
                record.topic() + ".DLT",
                record.partition()
            )
    );
}
~~~

Ví dụ định tuyến record `orders` sang `orders.DLT`, giữ partition number tương ứng. Nếu DLT có ít partition hơn topic nguồn hoặc không có partition tương ứng, việc publish có thể thất bại. Cần tạo DLT với số partition phù hợp hoặc chọn chiến lược định tuyến khác.

Với nhiều topic, có thể định tuyến theo tên topic, loại lỗi hoặc nhóm nghiệp vụ. Tránh tạo topic DLT không kiểm soát cho từng exception message vì có thể tạo quá nhiều topic và tăng chi phí vận hành.

### 7.2. DLT phải giữ được raw bytes khi deserialize thất bại

Với record deserialize thất bại, payload object không có giá trị hợp lệ. ErrorHandlingDeserializer giữ raw bytes và exception trong header; recoverer của Spring Kafka có thể khôi phục payload gốc khi publish DLT.

Producer dùng để gửi DLT vì vậy cần serialize được cả object bình thường và byte[] gốc. Nếu template DLT chỉ có JsonSerializer cho một kiểu object, việc gửi raw bytes có thể thất bại hoặc bị chuyển thành JSON không mong muốn.

Có thể dùng serializer hỗ trợ nhiều kiểu, ví dụ `DelegatingByTypeSerializer`, với mapping cho byte[] và các kiểu event hợp lệ. Cấu hình chính xác phụ thuộc generic type của KafkaTemplate và phiên bản Spring Kafka/Kafka client.

~~~java
Map<Class<?>, Serializer<?>> delegates = new LinkedHashMap<>();
delegates.put(byte[].class, new ByteArraySerializer());
delegates.put(OrderCreated.class, new JsonSerializer<>());

Serializer<Object> valueSerializer =
    new DelegatingByTypeSerializer(delegates);
~~~

Đoạn code là minh họa cho ý tưởng serializer theo kiểu payload. Hãy đối chiếu constructor và generic signature trong version đang dùng; một số cấu hình cần serializer mặc định cho các class khác hoặc mapping theo superclass.

### 7.3. DLT headers

Khi publish DLT, Spring Kafka bổ sung metadata giúp điều tra:

- Original topic, partition và offset.
- Timestamp nguồn.
- Exception class và exception message.
- Stack trace hoặc thông tin exception tùy cấu hình header.
- Các header gốc còn được giữ lại theo chính sách framework.

Cần tránh làm mất header deserialize exception trước khi recoverer có cơ hội khôi phục raw bytes. Nếu ứng dụng tự xóa headers hoặc tạo record mới chỉ từ payload null, DLT có thể không còn dữ liệu gốc.

### 7.4. Xử lý lỗi khi publish DLT

DLT publish cũng có thể thất bại do broker, authorization, serializer hoặc network. Khi đó không được giả định record nguồn đã được phục hồi thành công.

Cần quyết định:

- Recoverer có ném exception khi DLT publish thất bại hay không.
- Error handler có retry việc phục hồi không.
- Offset nguồn chỉ được commit sau khi publish DLT thành công theo cấu hình hay không.
- Có metric/cảnh báo khi DLT publish lỗi không.
- Quy trình vận hành sẽ xử lý record bị kẹt như thế nào.

Một DLT chỉ hữu ích nếu dữ liệu gốc được bảo toàn và đội vận hành có thể phát hiện, phân tích và replay record.

## 8. Cấu hình ErrorHandlingDeserializer trong Spring Boot

Ví dụ cấu hình JSON value:

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
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.trusted.packages: com.example.events
    listener:
      ack-mode: record
~~~

Cấu hình này bọc value deserializer. Nếu key cũng dùng deserializer có thể thất bại, cấu hình key bằng ErrorHandlingDeserializer và delegate key tương ứng.

Một số điểm cần chú ý:

- Tên class của ErrorHandlingDeserializer phải đúng package của Spring Kafka.
- Delegate class phải nằm trong dependency runtime.
- Trusted packages của JsonDeserializer cần giới hạn ở các package được phép.
- Nếu không dùng type headers, cấu hình default type hoặc type mapping phù hợp.
- Producer và consumer phải thống nhất schema, encoding và contract.
- Nếu dùng nhiều consumer factory, áp dụng cấu hình vào đúng factory mà listener container sử dụng.

### 8.1. Cấu hình delegate bằng constructor hoặc supplier

Spring Kafka hỗ trợ tạo ErrorHandlingDeserializer với delegate được cung cấp bằng cấu hình hoặc code. Khi cần cấu hình delegate phức tạp, có thể tạo bean deserializer hoặc supplier theo API phiên bản hiện tại.

Không tạo một delegate dùng chung không an toàn cho nhiều consumer nếu implementation giữ state mutable. Deserializer thường được tạo theo consumer; tuân thủ vòng đời và thread-safety của thư viện delegate.

### 8.2. Key và value phải được xử lý riêng

Có thể value hợp lệ nhưng key lỗi, hoặc ngược lại. Nếu chỉ cấu hình value ErrorHandlingDeserializer, lỗi ở key vẫn có thể làm poll thất bại.

Ví dụ cấu hình cả hai:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.trusted.packages: com.example.events
~~~

Trong cấu hình này, key được chuyển thành String và value thành event JSON. Nếu key lỗi, listener cũng không nên được gọi như thể record có key hợp lệ. Error handler cần nhận được thông tin lỗi và DLT phải giữ raw key bytes nếu muốn điều tra.

## 9. Phân loại lỗi và thiết kế phục hồi

Một chiến lược thực tế nên tách lỗi không thể sửa bằng retry khỏi lỗi tạm thời.

### 9.1. Lỗi dữ liệu không retry

Ví dụ JSON malformed:

~~~json
{"orderId": "O-100", "amount":
~~~

Deserializer không thể chuyển bytes này thành object. Gửi lại cùng record không làm JSON trở nên hợp lệ. Cách xử lý phù hợp thường là:

1. Ghi nhận DeserializationException và vị trí record.
2. Chuyển record cùng raw bytes sang DLT.
3. Tiếp tục consumer theo chính sách recoverer.
4. Cảnh báo producer owner hoặc nhóm quản lý contract.
5. Sửa nguồn dữ liệu hoặc xây dựng quy trình sửa và replay.

### 9.2. Lỗi hạ tầng có thể tạm thời

Ví dụ delegate cần truy cập schema registry nhưng registry tạm thời không phản hồi. Tùy exception gốc, lỗi có thể là tạm thời và retry có ích.

Tuy nhiên, retry phải có giới hạn và backoff. Nếu schema ID không tồn tại thật sự, retry vô hạn chỉ làm consumer lag tăng.

Nên phân loại dựa trên cause chain, exception type và error code của thư viện delegate, không chỉ dựa trên việc wrapper ngoài cùng là DeserializationException.

### 9.3. Poison pill

Poison pill là record mà consumer liên tục không thể xử lý, ví dụ payload malformed hoặc schema không tương thích. Nếu không có cơ chế phục hồi, record có thể giữ partition tại cùng offset và ngăn các record phía sau tiến lên tùy cách error handler xử lý.

Với poison pill:

- Xác định record bằng topic, partition, offset và event ID nếu đọc được.
- Giữ raw bytes và header lỗi.
- Tránh retry lặp vô hạn cùng dữ liệu.
- Chuyển DLT sau chính sách retry phù hợp.
- Cảnh báo khi DLT rate tăng.
- Chỉ replay sau khi đã sửa contract hoặc dữ liệu.

Không được âm thầm bỏ qua lỗi mà không ghi nhận vì điều đó làm mất dấu record không xử lý được.

## 10. Phân biệt lỗi deserialize và tombstone

Kafka compacted topic có thể chứa tombstone: record có key nhưng value là null, dùng để biểu thị xóa key trong luồng compacted.

Tombstone không phải DeserializationException. Nó là một record hợp lệ có value null theo semantics của Kafka.

Với ErrorHandlingDeserializer, lỗi deserialize cũng có thể dẫn đến value null nhưng kèm header lỗi. Vì vậy:

| Trường hợp | Value | Header lỗi deserialize | Ý nghĩa |
|---|---|---|---|
| Tombstone | null | Không có | Record xóa key hợp lệ |
| Deserialize lỗi | null theo cơ chế wrapper | Có | Payload bytes không thể chuyển đổi |
| Event có value null hợp lệ theo contract | null | Không có | Phụ thuộc semantics ứng dụng |

Listener hoặc error handler cần kiểm tra header lỗi khi phân biệt. Không gửi mọi record null sang DLT mà không xác định đó là tombstone hay lỗi deserialize.

Nếu ứng dụng dùng tombstone để xóa cache hoặc read model, bỏ qua nhầm tombstone có thể làm dữ liệu stale. Ngược lại, xử lý record deserialize lỗi như tombstone có thể xóa nhầm dữ liệu nghiệp vụ.

## 11. Quan sát và chẩn đoán DeserializationException

### 11.1. Log cần có

Khi error handler nhận lỗi deserialize, log các thông tin sau:

- Topic, partition, offset.
- Key/value có trường nào lỗi.
- Exception class và cause chain.
- Deserializer delegate đang sử dụng.
- Event type hoặc schema ID nếu đọc được từ header/bytes.
- Kích thước raw payload.
- Correlation ID hoặc trace ID nếu có.
- Đích DLT và kết quả publish.

Không ghi toàn bộ payload theo mặc định. Với dữ liệu nhạy cảm, chỉ log hash, kích thước hoặc một đoạn đã được che dữ liệu nếu quy trình bảo mật cho phép.

### 11.2. Metrics cần theo dõi

| Metric | Ý nghĩa |
|---|---|
| Deserialization error count | Số record lỗi deserialize |
| Error rate by topic | Topic nào có tỷ lệ lỗi cao |
| Key deserialization failures | Lỗi ở key |
| Value deserialization failures | Lỗi ở value |
| DLT publish success/failure | Khả năng phục hồi record |
| DLT record rate | Số record chuyển sang DLT |
| Consumer lag | Tác động của lỗi đến tiến độ group |
| Error class distribution | Nhóm lỗi malformed, schema, type mapping hoặc hạ tầng |

Metric label cần có cardinality thấp. Topic, key/value và nhóm exception phù hợp hơn event ID hoặc raw message. Không dùng offset, key hay payload làm label metric vì số lượng giá trị có thể tăng không giới hạn.

### 11.3. Kiểm tra record trong DLT

Khi lấy một record từ DLT, đối chiếu:

- Dead-letter topic và partition.
- Original topic, partition và offset.
- Raw key/value bytes.
- Header deserialize exception.
- Schema/type metadata.
- Thời điểm producer gửi và consumer xử lý.
- Version ứng dụng consumer.

Nếu record DLT đã bị deserialize bằng cùng delegate lỗi, có thể tiếp tục gặp exception khi đọc DLT. Đối với DLT chứa raw bytes, nên dùng consumer riêng đọc byte[] hoặc deserializer an toàn để điều tra.

## 12. Quy trình xử lý một DeserializationException trong production

1. **Xác định vị trí record:** lấy topic, partition, offset, group ID và timestamp từ log/error handler.
2. **Xác định key hay value:** đọc header lỗi tương ứng và cause chain.
3. **Bảo toàn payload:** xác nhận ErrorHandlingDeserializer giữ raw bytes và recoverer không làm mất chúng.
4. **Phân loại nguyên nhân:** malformed JSON, schema mismatch, type header, classpath, encoding hoặc lỗi hạ tầng.
5. **Quyết định retry:** chỉ retry khi nguyên nhân có khả năng tự phục hồi; tránh retry vô hạn lỗi dữ liệu.
6. **Phục hồi:** publish sang DLT với raw bytes và metadata nguồn; xác nhận DLT publish thành công.
7. **Theo dõi offset:** xác nhận group tiến qua record sau khi phục hồi theo chính sách error handler.
8. **Sửa nguồn:** cập nhật producer contract, schema, type mapping hoặc dữ liệu.
9. **Replay có kiểm soát:** đọc DLT bằng consumer phù hợp, sửa payload nếu cần và gửi lại vào topic đích theo quy trình.
10. **Đóng sự cố:** ghi nhận nguyên nhân gốc, số record ảnh hưởng và kết quả replay.

Không nên reset offset toàn group chỉ vì một record deserialize lỗi. Cần xử lý record cụ thể theo partition và chính sách recoverer, tránh tạo replay diện rộng ngoài ý muốn.

## 13. Kiểm thử ErrorHandlingDeserializer và DLT

Có thể dùng Embedded Kafka hoặc Kafka test broker để kiểm tra cả record hợp lệ và record lỗi.

### 13.1. Record hợp lệ

1. Tạo topic thử nghiệm.
2. Cấu hình ErrorHandlingDeserializer với JsonDeserializer delegate.
3. Gửi JSON hợp lệ tương ứng với event class.
4. Xác nhận listener nhận đúng object.
5. Xác nhận không có header lỗi deserialize.
6. Xác nhận offset được commit theo acknowledgment mode.

### 13.2. JSON malformed

1. Gửi raw bytes không phải JSON hợp lệ.
2. Xác nhận ErrorHandlingDeserializer bắt exception của delegate.
3. Xác nhận listener nghiệp vụ không nhận object giả.
4. Xác nhận container/error handler nhận thông tin lỗi.
5. Xác nhận record được chuyển sang DLT theo chính sách.
6. Đọc DLT bằng ByteArrayDeserializer và xác nhận raw bytes bằng payload nguồn.
7. Kiểm tra metadata nguồn và header exception.

### 13.3. Key deserialize thất bại

1. Cấu hình key bằng ErrorHandlingDeserializer với delegate phù hợp.
2. Gửi key bytes không hợp lệ theo encoding hoặc contract.
3. Xác nhận lỗi key được nhận diện riêng.
4. Xác nhận DLT giữ được key bytes gốc.
5. Xác nhận record không bị hiểu nhầm là key null hợp lệ.

### 13.4. DLT publish thất bại

1. Cấu hình DLT producer với serializer không tương thích hoặc quyền ghi bị từ chối trong môi trường test.
2. Gửi record deserialize lỗi.
3. Xác nhận recoverer báo lỗi publish DLT.
4. Xác nhận offset nguồn không bị tiến qua theo cách làm mất record.
5. Khôi phục quyền/serializer và kiểm tra retry/recovery theo chính sách.

### 13.5. Tombstone

1. Gửi record có key hợp lệ và value null vào compacted topic thử nghiệm.
2. Xác nhận ErrorHandlingDeserializer không tạo header lỗi nếu đây là tombstone hợp lệ.
3. Xác nhận listener hoặc luồng xử lý tombstone hoạt động đúng contract.
4. So sánh với một record có bytes value malformed.

Kiểm thử nên xác nhận cả raw payload, metadata, DLT và committed offset. Chỉ kiểm tra exception được log không đủ để chứng minh record được phục hồi an toàn.

## 14. Những lỗi triển khai thường gặp

**Không dùng ErrorHandlingDeserializer:** deserializer ném exception trong poll, listener không nhận record và record-level error handler thiếu ConsumerRecord để phục hồi rõ ràng.

**Chỉ bọc value deserializer:** key có thể deserialize lỗi và làm poll thất bại trước khi listener được gọi.

**Retry vô hạn payload malformed:** cùng bytes và cùng delegate sẽ tiếp tục lỗi, làm partition bị chặn và lag tăng.

**Không giữ raw bytes:** DLT chỉ chứa null, khiến đội vận hành không thể tái tạo hoặc sửa payload.

**DLT serializer không hỗ trợ byte[]:** recoverer không thể publish dữ liệu gốc sau deserialize failure.

**Tin cậy package quá rộng:** JsonDeserializer có thể tạo object từ type header không mong muốn. Giới hạn trusted packages và dùng type mapping rõ ràng.

**Nhầm tombstone với deserialize failure:** value null có thể là record xóa hợp lệ; kiểm tra header lỗi trước khi xử lý.

**Nuốt exception trong listener:** nếu listener được gọi và bắt lỗi rồi trả về bình thường, container có thể commit dù nghiệp vụ chưa hoàn tất.

**Không phân biệt schema registry outage và schema mismatch:** hai lỗi có chính sách retry khác nhau.

**Replay DLT không có idempotency:** gửi lại record đã từng được xử lý một phần có thể tạo side effect trùng.

## 15. Nguyên tắc vận hành

- Dùng ErrorHandlingDeserializer bọc delegate khi muốn listener container xử lý lỗi deserialize ở cấp record.
- Bọc cả key và value nếu cả hai deserializer có thể thất bại.
- Cấu hình delegate, serializer và schema contract nhất quán giữa producer và consumer.
- Phân biệt DeserializationException với lỗi message conversion và lỗi nghiệp vụ.
- Xác định lỗi malformed/type mapping thường không retry; lỗi hạ tầng chỉ retry khi có căn cứ.
- Dùng DefaultErrorHandler với phân loại exception, backoff có giới hạn và recoverer rõ ràng.
- Cấu hình DLT producer có thể serialize cả object thông thường và raw byte[].
- Giữ raw bytes, exception metadata, topic, partition và offset khi phục hồi.
- Phân biệt tombstone hợp lệ với payload null do deserialize lỗi bằng header.
- Giới hạn quyền truy cập và retention của DLT vì payload có thể chứa dữ liệu nhạy cảm.
- Theo dõi error rate, DLT rate, publish failure và consumer lag.
- Chỉ replay sau khi đã sửa nguyên nhân và có cơ chế idempotent ở downstream.

DeserializationException cho biết consumer không thể chuyển bytes của record thành object theo contract hiện tại. ErrorHandlingDeserializer giúp đưa lỗi cùng dữ liệu gốc đến Spring listener container, nơi DefaultErrorHandler và DeadLetterPublishingRecoverer có thể retry có kiểm soát hoặc lưu record vào DLT. Giữ raw bytes, phân loại đúng nguyên nhân và bảo đảm offset chỉ tiến sau khi phục hồi theo chính sách là nền tảng để xử lý poison pill mà không âm thầm mất dữ liệu.
