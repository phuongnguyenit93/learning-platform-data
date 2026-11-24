# Serializer của DLT khi sử dụng native decoding

Trong Spring Cloud Stream Kafka binder, consumer có thể để Kafka client giải mã key và value bằng deserializer gốc của Kafka thay vì dùng message conversion của Spring Cloud Stream. Cách này thường được gọi là **native decoding**. Nó phù hợp khi ứng dụng sử dụng Avro, Protobuf, JSON serializer riêng hoặc một định dạng mà Kafka client đã có deserializer tương ứng.

Khi xử lý một record thất bại sau khi đã giải mã thành công, Kafka binder có thể chuyển record lỗi sang dead-letter topic (DLT). Tuy nhiên, payload lúc này có thể là một đối tượng Java như String hoặc OrderCreated, trong khi producer của DLT cần chuyển đối tượng đó thành byte[] để ghi lại vào Kafka. Vì vậy, serializer của DLT phải tương thích với kiểu key và value mà consumer đã giải mã.

Đây là điểm khác biệt quan trọng: **deserializer của consumer** quyết định kiểu dữ liệu ứng dụng nhận được; **serializer của DLT producer** quyết định cách kiểu dữ liệu đó được ghi vào topic lỗi. Hai cấu hình có liên quan nhưng nằm ở hai phía khác nhau.

## 1. Luồng dữ liệu khi bật native decoding

Thông thường, Spring Cloud Stream có thể dùng message converter để chuyển payload giữa byte[] và kiểu dữ liệu ứng dụng dựa trên content type. Khi bật native decoding, Kafka client thực hiện bước giải mã bằng deserializer được cấu hình cho consumer.

~~~mermaid
flowchart TD
    A[Kafka record: key bytes + value bytes] --> B[Kafka consumer deserializer]
    B --> C[Native decoding]
    C --> D[Spring Cloud Stream consumer]
    D --> E{Xử lý thành công?}
    E -->|Có| F[Hoàn tất xử lý và commit theo ack mode]
    E -->|Không| G[Retry theo consumer policy]
    G --> H{Còn lượt thử?}
    H -->|Có| D
    H -->|Không| I[DLT producer]
    I --> J[Key serializer và value serializer]
    J --> K[Dead-letter topic]
~~~

Ví dụ, Kafka lưu value dưới dạng byte[] nhưng consumer dùng StringDeserializer. Khi record đến ứng dụng, payload đã là String. Nếu xử lý thất bại và binder gửi payload sang DLT, producer DLT phải biết cách serialize String. Serializer mặc định của DLT producer mong đợi byte[]; nếu giữ mặc định trong khi payload là String, việc gửi DLT có thể thất bại do không khớp kiểu.

## 2. Phân biệt ba cấu hình serialization

| Cấu hình | Vai trò | Ví dụ |
|---|---|---|
| Consumer key/value deserializer | Giải mã record từ topic nguồn thành kiểu Java mà ứng dụng nhận. | StringDeserializer, KafkaAvroDeserializer, custom deserializer. |
| DLT key/value serializer | Mã hóa key và payload lỗi khi binder gửi sang DLT. | StringSerializer, KafkaAvroSerializer, custom serializer. |
| Spring message converter | Chuyển đổi payload giữa message và kiểu ứng dụng khi không dùng native decoding. | JSON message converter hoặc converter tùy chỉnh. |

Không dùng serializer của producer nghiệp vụ để suy ra DLT producer đã được cấu hình đúng. DLT producer có nhóm thuộc tính riêng là **dlqProducerProperties**. Cấu hình ở đây chỉ tác động đến producer gửi dead-letter record của binding đó.

Trong cấu hình Kafka binder, đường dẫn quan trọng là:

~~~text
spring.cloud.stream.kafka.bindings.<binding-name>.consumer.dlqProducerProperties.configuration.key.serializer
spring.cloud.stream.kafka.bindings.<binding-name>.consumer.dlqProducerProperties.configuration.value.serializer
~~~

Trong YAML có thể viết theo dạng kebab-case:

~~~yaml
dlq-producer-properties:
  configuration:
    key:
      serializer: ...
    value:
      serializer: ...
~~~

Khi dùng dạng map của Kafka properties, cú pháp trực tiếp với dấu chấm thường rõ ràng hơn:

~~~yaml
dlq-producer-properties:
  configuration:
    key.serializer: org.apache.kafka.common.serialization.StringSerializer
    value.serializer: org.apache.kafka.common.serialization.StringSerializer
~~~

## 3. Điều kiện để Kafka binder gửi record vào DLT

Với regular Kafka binder, consumer cần có group cụ thể và bật DLQ trên input binding. Consumer anonymous không dùng được DLQ facility của binder.

Ví dụ:

~~~yaml
spring:
  cloud:
    function:
      definition: processData
    stream:
      bindings:
        processData-in-0:
          destination: input-topic
          group: processing-service
      kafka:
        bindings:
          processData-in-0:
            consumer:
              enable-dlq: true
              dlq-name: input-topic-dlt
~~~

Nếu không đặt dlq-name, tên mặc định có dạng:

~~~text
error.<destination>.<group>
~~~

Ví dụ với destination input-topic và group processing-service, tên mặc định là error.input-topic.processing-service.

DLQ được bật bằng thuộc tính mở rộng của Kafka binder, đặt dưới consumer của binding. Group là điều kiện cần để binder xác định consumer group và dead-letter destination. Ngoài ra, topic DLT phải có số partition phù hợp với cách binder định tuyến record lỗi.

Mặc định, binder thường gửi record lỗi vào partition cùng số với partition nguồn. Nếu thay đổi số partition DLT, hãy đọc cấu hình dlq-partitions và cơ chế DlqPartitionFunction tương ứng. Bài học này tập trung vào serializer; việc tạo topic, quyền ghi và partition vẫn phải được cấu hình phù hợp.

## 4. Ví dụ đơn giản: consumer nhận byte[]

Kafka binder mặc định mong đợi payload của DLT là byte[]. Nếu function nhận byte[] và không chuyển kiểu trước khi phát sinh lỗi, serializer mặc định có thể serialize payload này.

~~~java
@Bean
public Consumer<byte[]> processData() {
    return value -> {
        // Xử lý dữ liệu nghiệp vụ.
        throw new IllegalStateException("Không thể xử lý record");
    };
}
~~~

~~~yaml
spring:
  cloud:
    function:
      definition: processData
    stream:
      bindings:
        processData-in-0:
          destination: input-topic
          group: processing-service
      kafka:
        bindings:
          processData-in-0:
            consumer:
              enable-dlq: true
              dlq-name: input-topic-dlt
~~~

Trong ví dụ này, consumer nhận byte[] và DLT producer mặc định cũng mong đợi byte[]. Vì vậy, chưa cần khai báo value.serializer riêng chỉ để xử lý kiểu payload này.

Điều đó không có nghĩa mọi trường hợp native decoding đều có thể bỏ qua cấu hình serializer. Nếu deserializer chuyển value thành String, Avro object hoặc kiểu Java khác, serializer mặc định byte[] không còn phù hợp.

## 5. Ví dụ: consumer giải mã String nhưng DLT vẫn mặc định byte[]

Giả sử record nguồn có key và value là chuỗi. Consumer sử dụng StringDeserializer cho cả hai:

~~~java
@Bean
public Consumer<String> processData() {
    return value -> {
        if (value.startsWith("invalid")) {
            throw new IllegalArgumentException(
                    "Payload không hợp lệ");
        }
        // Xử lý payload hợp lệ.
    };
}
~~~

Cấu hình native decoding và DLT:

~~~yaml
spring:
  cloud:
    function:
      definition: processData
    stream:
      bindings:
        processData-in-0:
          destination: input-topic
          group: processing-service
          consumer:
            use-native-decoding: true
      kafka:
        bindings:
          processData-in-0:
            consumer:
              enable-dlq: true
              dlq-name: input-topic-dlt
              configuration:
                key.deserializer: org.apache.kafka.common.serialization.StringDeserializer
                value.deserializer: org.apache.kafka.common.serialization.StringDeserializer
              dlq-producer-properties:
                configuration:
                  key.serializer: org.apache.kafka.common.serialization.StringSerializer
                  value.serializer: org.apache.kafka.common.serialization.StringSerializer
~~~

Giải thích:

1. Kafka client dùng StringDeserializer để giải mã key và value của record nguồn.
2. Consumer function nhận value là String.
3. Khi function ném exception và retry đã hết, binder cần gửi record sang input-topic-dlt.
4. DLT producer dùng StringSerializer để serialize key/value kiểu String.
5. Record lỗi được ghi vào DLT theo cấu hình của binder.

Hai serializer trong dlq-producer-properties phải khớp với kiểu dữ liệu đã giải mã. Nếu key không phải String, hãy thay key.serializer bằng serializer tương ứng. Nếu value là byte[] thì dùng ByteArraySerializer; nếu value là một Avro SpecificRecord thì dùng serializer Avro tương thích.

## 6. Vì sao phải cấu hình cả key serializer và value serializer?

Kafka record có hai phần dữ liệu độc lập: key và value. Consumer có thể giải mã chúng bằng hai deserializer khác nhau. Khi gửi lại record lỗi, DLT producer phải mã hóa lại cả hai phần theo kiểu dữ liệu đang có.

Ví dụ:

| Dữ liệu nguồn | Consumer deserializer | Kiểu ứng dụng nhận | DLT serializer tương ứng |
|---|---|---|---|
| Key String, value String | StringDeserializer cho cả hai | String / String | StringSerializer / StringSerializer |
| Key String, value byte[] | StringDeserializer và ByteArrayDeserializer | String / byte[] | StringSerializer / ByteArraySerializer |
| Key Long, value String | LongDeserializer và StringDeserializer | Long / String | LongSerializer / StringSerializer |
| Key UUID, value Avro SpecificRecord | UUIDDeserializer và KafkaAvroDeserializer | UUID / SpecificRecord | UUIDSerializer và KafkaAvroSerializer phù hợp |

Nếu chỉ cấu hình value.serializer mà key cũng đã được giải mã thành một kiểu không phải byte[], producer DLT vẫn có thể lỗi khi serialize key. Ngược lại, nếu key null hoặc vẫn là byte[] thì serializer tương ứng cần phản ánh đúng kiểu đó.

Không chọn serializer chỉ dựa trên kiểu khai báo của Consumer<T>. Chữ ký Consumer<T> chỉ mô tả payload value; key được quản lý riêng bởi Kafka deserializer và có thể không xuất hiện trong tham số function. Khi cần xác định key type, hãy xem cấu hình key.deserializer và cách producer nguồn tạo record.

## 7. Ví dụ với Avro hoặc serializer tùy chỉnh

Native decoding thường được chọn khi ứng dụng dùng định dạng có serializer/deserializer chuyên dụng. Ví dụ với Confluent Avro, consumer có thể giải mã value thành SpecificRecord:

~~~yaml
spring:
  cloud:
    function:
      definition: orderConsumer
    stream:
      bindings:
        orderConsumer-in-0:
          destination: orders
          group: order-projection
          consumer:
            use-native-decoding: true
      kafka:
        bindings:
          orderConsumer-in-0:
            consumer:
              enable-dlq: true
              dlq-name: orders-dlt
              configuration:
                key.deserializer: org.apache.kafka.common.serialization.StringDeserializer
                value.deserializer: io.confluent.kafka.serializers.KafkaAvroDeserializer
                schema.registry.url: http://schema-registry:8081
                specific.avro.reader: true
              dlq-producer-properties:
                configuration:
                  key.serializer: org.apache.kafka.common.serialization.StringSerializer
                  value.serializer: io.confluent.kafka.serializers.KafkaAvroSerializer
                  schema.registry.url: http://schema-registry:8081
~~~

Consumer có thể khai báo kiểu payload là lớp SpecificRecord được sinh từ schema:

~~~java
@Bean
public Consumer<OrderCreated> orderConsumer() {
    return event -> {
        if (event.getTotal() < 0) {
            throw new IllegalArgumentException(
                    "Tổng tiền không hợp lệ");
        }
        // Cập nhật projection.
    };
}
~~~

Ví dụ trên minh họa nguyên tắc cấu hình, không thay thế yêu cầu dependency và cấu hình bảo mật của Confluent Schema Registry. Cả consumer deserializer lẫn DLT producer serializer đều phải dùng registry phù hợp, cùng schema compatibility policy và quyền truy cập cần thiết.

Nếu dùng serializer tự viết, lớp serializer phải triển khai Kafka Serializer cho đúng kiểu đối tượng được giải mã. Ví dụ, deserializer trả về OrderCreated thì DLT serializer phải biết mã hóa OrderCreated. Không thể dùng StringSerializer cho một đối tượng OrderCreated chỉ vì JSON của nó có thể biểu diễn dưới dạng chuỗi; cần một serializer thực hiện chuyển đổi đó rõ ràng.

## 8. Phân biệt lỗi xử lý nghiệp vụ và lỗi deserialization

Hai loại lỗi này xảy ra ở những thời điểm khác nhau và cần cơ chế xử lý khác nhau.

### Lỗi sau khi consumer đã nhận payload

Luồng xử lý:

1. Kafka deserializer giải mã thành công.
2. Consumer nhận payload đã giải mã.
3. Logic nghiệp vụ ném exception.
4. Binder áp dụng retry policy.
5. Nếu hết lượt thử, binder có thể gửi record sang DLT.

Đây là trường hợp mà enable-dlq và dlq-producer-properties trong ví dụ trước xử lý. Serializer DLT phải tương thích với key/value đã được giải mã.

### Lỗi xảy ra trong quá trình deserialization

Nếu deserializer ném exception khi Kafka consumer đang poll, record có thể chưa được trả về cho listener. Vì vậy, cơ chế DLQ thông thường của Spring Cloud Stream không thể tự xử lý lỗi này như một lỗi nghiệp vụ trong function.

Với trường hợp đó, Spring for Apache Kafka cung cấp **ErrorHandlingDeserializer**. Nó ủy quyền cho deserializer thực tế; khi giải mã thất bại, nó giữ raw bytes và exception trong header để error handler có thể xử lý record.

Quy trình tổng quát:

~~~mermaid
flowchart TD
    A[Kafka poll] --> B[ErrorHandlingDeserializer]
    B --> C{Giải mã thành công?}
    C -->|Có| D[Consumer function]
    C -->|Không| E[Giữ raw bytes và exception]
    E --> F[CommonErrorHandler]
    F --> G[DeadLetterPublishingRecoverer]
    G --> H[DLT]
~~~

Để xử lý deserialization error, cần cấu hình ErrorHandlingDeserializer và error handler tương ứng, thường thông qua ListenerContainerCustomizer, DefaultErrorHandler và DeadLetterPublishingRecoverer. Serializer của dead-letter publisher phải có khả năng ghi raw bytes hoặc kiểu dữ liệu mà recoverer chuyển vào producer.

Ví dụ cấu hình deserializer bọc:

~~~yaml
spring:
  cloud:
    function:
      definition: orderConsumer
    stream:
      bindings:
        orderConsumer-in-0:
          destination: orders
          group: order-projection
          consumer:
            use-native-decoding: true
      kafka:
        bindings:
          orderConsumer-in-0:
            consumer:
              configuration:
                key.deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
                value.deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
                spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
                spring.deserializer.value.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
~~~

Đây mới là phần cấu hình deserializer. Để gửi deserialization failure sang DLT, ứng dụng còn phải cấu hình CommonErrorHandler/DeadLetterPublishingRecoverer cho listener container và producer template có serializer tương thích với raw bytes hoặc các kiểu key/value thực tế. Không coi ví dụ trên là một cấu hình DLQ hoàn chỉnh.

Điểm cần nhớ:

- **dlq-producer-properties** của Kafka binder giải quyết serializer cho đường DLQ do binder quản lý khi xử lý message thất bại sau khi consumer đã nhận record.
- **ErrorHandlingDeserializer + DefaultErrorHandler + DeadLetterPublishingRecoverer** giải quyết lỗi deserialization xảy ra trước khi listener nhận record.
- Hai cơ chế có thể cùng xuất hiện trong một ứng dụng, nhưng không tự động thay thế nhau.

## 9. DLT không nhất thiết giữ nguyên byte gốc

Khi native decoding thành công, consumer đã chuyển byte[] thành đối tượng Java. Khi DLT producer serialize đối tượng đó, kết quả có thể không giống từng byte của record gốc.

Ví dụ, một JSON deserializer có thể tạo đối tượng OrderCreated; serializer JSON sau đó có thể sắp xếp lại thứ tự thuộc tính, chuẩn hóa khoảng trắng hoặc biểu diễn số theo cách khác. Dữ liệu nghiệp vụ có thể tương đương nhưng byte stream không nhất thiết giống hệt.

Nếu yêu cầu kiểm toán cần lưu nguyên byte gốc:

- Cân nhắc nhận payload dưới dạng byte[] và tự giải mã ở tầng ứng dụng.
- Hoặc giữ raw ConsumerRecord/byte[] qua một adapter phù hợp.
- Với lỗi deserialization, dùng ErrorHandlingDeserializer để giữ raw bytes trong thông tin lỗi.
- Xác định rõ DLT cần lưu payload đã giải mã, payload đã chuẩn hóa hay byte gốc.

Đừng giả định rằng dùng serializer cùng loại với deserializer sẽ tái tạo byte gốc tuyệt đối. Một số định dạng có thể thêm schema ID, metadata, framing hoặc thông tin registry trong quá trình serialization.

## 10. Retry trước khi gửi DLT

DLT thường nhận record sau khi consumer đã thử xử lý theo retry policy. Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processData-in-0:
          consumer:
            max-attempts: 4
            back-off-initial-interval: 1000
            back-off-max-interval: 5000
            back-off-multiplier: 2.0
~~~

Với cấu hình này, binder có thể thử tối đa bốn lần, tính cả lần xử lý đầu tiên. Nếu tất cả lần thử đều thất bại, cơ chế DLQ được kích hoạt nếu đã bật enable-dlq và binding có group hợp lệ.

Retry không sửa được lỗi serializer. Nếu DLT producer dùng serializer sai kiểu, lần gửi DLT vẫn thất bại sau khi retry xử lý đã cạn. Do đó, cần kiểm tra riêng:

1. Consumer deserializer có tạo ra đúng kiểu ứng dụng mong đợi không?
2. Retry policy có số lần thử và phân loại lỗi phù hợp không?
3. DLT producer có serializer cho key và value đã giải mã không?
4. DLT topic có tồn tại, đủ partition và có quyền ghi không?
5. Consumer xử lý DLT có deserializer tương thích với định dạng DLT không?

## 11. Cách đọc lại record trong DLT

DLT chỉ hữu ích khi đội vận hành có thể đọc, điều tra và quyết định phát lại record. Consumer DLT cần biết định dạng key/value mà producer DLT đã ghi.

Nếu DLT producer dùng StringSerializer, consumer DLT có thể dùng StringDeserializer. Nếu producer dùng Avro serializer, consumer DLT cần Avro deserializer và cấu hình registry tương ứng. Nếu DLT giữ byte[] gốc, consumer có thể dùng ByteArrayDeserializer để lưu trữ hoặc phân tích payload.

Ví dụ consumer DLT đọc chuỗi:

~~~java
@Bean
public Consumer<String> inspectFailedOrder() {
    return payload -> {
        log.warn("DLT payload: {}", payload);
        // Ghi nhận lỗi và chuyển tới quy trình điều tra.
    };
}
~~~

~~~yaml
spring:
  cloud:
    function:
      definition: inspectFailedOrder
    stream:
      bindings:
        inspectFailedOrder-in-0:
          destination: input-topic-dlt
          group: dlt-inspector
      kafka:
        bindings:
          inspectFailedOrder-in-0:
            consumer:
              configuration:
                key.deserializer: org.apache.kafka.common.serialization.StringDeserializer
                value.deserializer: org.apache.kafka.common.serialization.StringDeserializer
~~~

Đây là ví dụ cho DLT chứa String key/value. Nếu DLT dùng serializer khác, hãy thay deserializer tương ứng. Không dùng cùng consumer config cho mọi DLT nếu các binding có payload type khác nhau.

## 12. Kiểm thử serializer của DLT

Kiểm thử phải chạy qua Kafka broker thử nghiệm vì chỉ unit test RetryTemplate không chứng minh DLT producer serialize đúng.

### Kiểm thử cơ bản với String

1. Tạo topic nguồn và DLT.
2. Khởi động consumer có native decoding và StringDeserializer.
3. Gửi một record có key String và value String.
4. Cho function ném exception để kích hoạt retry.
5. Sau khi hết attempts, đọc record từ DLT.
6. Xác nhận key/value có thể deserialize bằng StringDeserializer.
7. Kiểm tra các header dead-letter như x-original-topic, x-exception-message và x-exception-stacktrace nếu phiên bản binder đang dùng cung cấp chúng.

### Ma trận kiểm thử

| Tình huống | Cấu hình | Kết quả cần xác nhận |
|---|---|---|
| Consumer byte[] | Native decoding với ByteArrayDeserializer hoặc payload byte[]. | DLT producer mặc định serialize payload byte[] thành công. |
| Consumer String | StringDeserializer và StringSerializer cho DLT value. | Record lỗi được ghi vào DLT và đọc lại thành String. |
| Key String | StringDeserializer và StringSerializer cho DLT key. | Key không gây lỗi serialization khi chuyển DLT. |
| Key/value khác kiểu | Deserializer và serializer riêng cho từng kiểu. | Cả key lẫn value đều được ghi đúng. |
| Serializer không khớp | Consumer trả String nhưng DLT dùng ByteArraySerializer. | Test phát hiện lỗi kiểu khi gửi DLT. |
| Avro SpecificRecord | Avro deserializer/serializer cùng registry. | Record lỗi được ghi và đọc lại đúng schema. |
| Retry hết lượt | Handler luôn ném exception. | DLT nhận record sau số lần thử đã cấu hình. |
| Deserialization error | Dữ liệu wire sai và dùng ErrorHandlingDeserializer. | CommonErrorHandler/DeadLetterPublishingRecoverer xử lý đường lỗi trước listener. |
| DLT consumer | Dùng deserializer tương ứng serializer DLT. | Consumer đọc được key/value và metadata lỗi. |
| Quyền ghi DLT | Tài khoản consumer thiếu quyền produce tới DLT. | Lỗi quyền được phát hiện qua log/metric, không coi record đã được lưu. |

### Những gì cần quan sát

- Log lỗi serialization từ Kafka producer DLT.
- Số lần retry của consumer trước khi chuyển DLT.
- Số record thực tế được ghi vào DLT.
- Key và value có thể deserialize lại bằng cấu hình consumer DLT.
- Partition và offset của record trong DLT.
- Các dead-letter headers được tạo theo phiên bản binder.
- Lỗi quyền truy cập, topic không tồn tại hoặc partition không tương thích.

Không chỉ kiểm tra rằng consumer không còn ném exception. Cần đọc record thực tế từ DLT để chứng minh serializer đã ghi dữ liệu đúng định dạng.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Consumer xử lý được nhưng DLT publish thất bại | DLT producer vẫn dùng ByteArraySerializer trong khi payload đã giải mã thành String hoặc object. | Khai báo value.serializer tương ứng trong dlq-producer-properties. |
| DLT gửi được value nhưng lỗi key | Key đã được giải mã thành kiểu khác byte[] nhưng key.serializer không tương thích. | Cấu hình key.serializer theo key.deserializer. |
| ClassCastException khi gửi DLT | Serializer nhận kiểu đối tượng không đúng. | Đối chiếu kiểu thực tế của key/value và serializer. |
| DLT consumer không đọc được record | Deserializer phía DLT không khớp serializer đã dùng. | Thống nhất wire format và serializer/deserializer hai phía. |
| Bật enable-dlq nhưng không thấy DLT | Consumer anonymous hoặc chưa có group hợp lệ. | Đặt group trên input binding. |
| Deserialization exception làm ứng dụng dừng | Lỗi xảy ra trong poll trước khi binder nhận message để xử lý theo DLQ thông thường. | Dùng ErrorHandlingDeserializer và cấu hình CommonErrorHandler/DeadLetterPublishingRecoverer. |
| DLT có payload khác byte gốc | Consumer giải mã thành object rồi serializer tạo lại wire representation. | Giữ byte[]/raw record nếu cần bảo toàn byte gốc. |
| DLT producer không ghi được topic | Thiếu quyền, topic chưa tồn tại hoặc partition không phù hợp. | Kiểm tra ACL, topic provisioning và partition selection. |
| Chỉ value được cấu hình serializer | Key vẫn dùng serializer mặc định không tương thích. | Cấu hình cả key.serializer và value.serializer khi cả hai cần chuyển kiểu. |

Khi điều tra, hãy xem lỗi xảy ra ở đâu: trong function sau khi nhận payload, trong deserializer khi poll, hay trong DLT producer lúc serialize. Ba vị trí này có error handler và cấu hình khác nhau.

## 14. Checklist trước khi triển khai

- [ ] Consumer binding có group cụ thể.
- [ ] enable-dlq được bật trên đúng Kafka input binding.
- [ ] dlq-name được chọn rõ ràng hoặc đã xác nhận tên mặc định.
- [ ] use-native-decoding được bật đúng binding nếu muốn Kafka client giải mã.
- [ ] key.deserializer và value.deserializer phản ánh đúng wire format nguồn.
- [ ] key.serializer và value.serializer trong dlq-producer-properties tương thích với kiểu đã giải mã.
- [ ] Nếu value là byte[], đã xác nhận serializer mặc định phù hợp.
- [ ] Nếu dùng Avro/Protobuf/serializer riêng, DLT producer có dependency và cấu hình tương ứng.
- [ ] DLT consumer dùng deserializer khớp với định dạng được ghi.
- [ ] Đã phân biệt application processing error với deserialization error.
- [ ] Đường xử lý deserialization error có ErrorHandlingDeserializer và error handler riêng nếu cần.
- [ ] Retry, DLT topic, partition, ACL và retention đã được kiểm thử.
- [ ] Integration test đã đọc record thực tế từ DLT.

Khi dùng native decoding, Kafka client giải mã key/value trước khi payload đến function. Nếu xử lý nghiệp vụ thất bại và binder cần gửi record sang DLT, DLT producer phải serialize lại các kiểu dữ liệu đã giải mã. Cấu hình **dlq-producer-properties.configuration.key.serializer** và **value.serializer** để khớp với deserializer của consumer; mặc định DLT producer mong đợi payload byte[]. Đồng thời, hãy phân biệt lỗi xử lý sau khi nhận payload với lỗi deserialization xảy ra trong poll, vì trường hợp thứ hai cần ErrorHandlingDeserializer và error handler phù hợp. Kiểm thử bằng cách đọc lại record từ DLT là bước xác nhận cuối cùng rằng serializer đã được chọn đúng.

## Tài liệu tham khảo

- [Spring Cloud Stream Kafka Binder — Retry and Dead Letter Processing](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka_overview.html)
- [Spring Cloud Stream Kafka Binder — Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Cloud Stream Kafka Binder — Handling Deserialization Errors with DLQ](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-kafka.html)
- [Spring for Apache Kafka — Serialization, Deserialization and Error Handling](https://docs.spring.io/spring-kafka/reference/kafka/serdes.html)
- [Apache Kafka — Producer Configuration](https://kafka.apache.org/documentation/#producerconfigs)
