# StringSerializer và StringDeserializer

Kafka lưu record dưới dạng byte. Producer phải chuyển key và value từ kiểu Java sang `byte[]` trước khi gửi; consumer chuyển các byte nhận được về kiểu Java để ứng dụng xử lý. Kafka client cung cấp `StringSerializer` và `StringDeserializer` cho trường hợp key hoặc value là chuỗi. Đây là cặp serializer/deserializer đơn giản, thường dùng cho message văn bản, mã định danh, command nhỏ hoặc payload JSON được biểu diễn dưới dạng chuỗi.

Hai class này không tạo thêm cấu trúc dữ liệu hay metadata kiểu Java. `StringSerializer` mã hóa nội dung chuỗi thành byte theo charset đã cấu hình; `StringDeserializer` giải mã byte thành chuỗi theo charset tương ứng. Producer và consumer phải thống nhất định dạng byte. Nếu một bên ghi UTF-8 còn bên kia giải mã bằng charset khác, nội dung có thể bị sai ký tự dù Kafka vẫn truyền record bình thường.

## 1. Vì sao cần serializer và deserializer?

Kafka broker không hiểu trực tiếp `String`, `OrderCreated` hay bất kỳ object Java nào. Record trên wire gồm key/value dạng byte cùng metadata như topic, partition, offset, timestamp và headers. Vì vậy, ứng dụng cần chuyển đổi kiểu dữ liệu ở hai đầu:

```text
Producer application
String key/value
      |
      v
StringSerializer
      |
      v
byte[] -----------------------> Kafka broker
                                  lưu record trong partition
                                      |
                                      v
Consumer application           byte[]
      ^                              |
      |                              v
String key/value <---------- StringDeserializer
```

Với chuỗi, Kafka client cung cấp sẵn:

- `org.apache.kafka.common.serialization.StringSerializer`: chuyển `String` thành `byte[]`.
- `org.apache.kafka.common.serialization.StringDeserializer`: chuyển `byte[]` thành `String`.

Nếu producer và consumer đều dùng cặp này, ứng dụng có thể gửi và nhận văn bản mà không cần tự viết serializer. Tuy nhiên, Kafka không kiểm tra rằng mọi producer ghi vào cùng topic đều dùng cùng định dạng. Quy ước encoding và payload vẫn phải được thống nhất giữa các ứng dụng.

## 2. StringSerializer mã hóa chuỗi như thế nào?

`StringSerializer` nhận một giá trị `String` và chuyển nó thành mảng byte. Charset mặc định là UTF-8. Ví dụ chuỗi `hello` được mã hóa thành các byte tương ứng với UTF-8; chuỗi tiếng Việt như `Xin chào Kafka` cũng được mã hóa thành byte UTF-8 để giữ nguyên ký tự có dấu.

Ví dụ sử dụng trực tiếp:

```java
StringSerializer serializer = new StringSerializer();

byte[] bytes = serializer.serialize("notifications", "Xin chào Kafka");

System.out.println(Arrays.toString(bytes));
```

Trong ví dụ, tham số đầu tiên là tên topic, tham số thứ hai là dữ liệu chuỗi. Serializer trả về `byte[]` để Kafka producer gửi đi. Ứng dụng thông thường không cần tự gọi serializer vì `KafkaProducer` hoặc Spring Kafka sẽ gọi nó dựa trên cấu hình.

`StringSerializer` cũng xử lý giá trị `null`: nếu dữ liệu đầu vào là `null`, serializer trả về `null` thay vì một mảng byte. Chuỗi rỗng `""` là trường hợp khác: nó được mã hóa thành mảng byte có độ dài bằng 0. Sự khác biệt này quan trọng với Kafka compacted topic, nơi record có key và value `null` có thể là tombstone đánh dấu xóa key.

## 3. StringDeserializer giải mã byte thành chuỗi

`StringDeserializer` thực hiện chiều ngược lại. Nó nhận byte từ Kafka và tạo `String` theo charset được cấu hình. Mặc định cũng là UTF-8.

```java
StringDeserializer deserializer = new StringDeserializer();

String value = deserializer.deserialize(
        "notifications",
        "Xin chào Kafka".getBytes(StandardCharsets.UTF_8));

System.out.println(value);
```

Nếu dữ liệu byte là `null`, deserializer trả về `null`. Nếu dữ liệu là mảng byte rỗng, kết quả là chuỗi rỗng. Vì vậy, khi xử lý message, cần phân biệt:

| Giá trị nhận được | Ý nghĩa |
|---|---|
| `null` | Kafka record có key/value null ở vị trí tương ứng; với value trên compacted topic có thể là tombstone |
| `""` | Có record và payload là chuỗi rỗng |
| `"hello"` | Có record và payload là văn bản `hello` |

Nếu byte được tạo bằng charset khác UTF-8 nhưng deserializer dùng UTF-8, ký tự có thể bị thay thế hoặc hiển thị sai. Deserializer không thể tự đoán chính xác charset mà producer đã dùng. Cách tốt nhất là thống nhất UTF-8 ở tất cả producer và consumer.

## 4. Cấu hình StringSerializer và StringDeserializer trong Spring Boot

Spring Boot cho phép khai báo class serializer/deserializer trong `application.yml`. Ví dụ producer và consumer đều gửi/nhận chuỗi:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all
    consumer:
      group-id: notification-reader
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      auto-offset-reset: earliest
      enable-auto-commit: false
```

Trong cấu hình này:

- Key và value của producer đều có kiểu Java `String`.
- Key và value của consumer đều được giải mã thành `String`.
- `group-id` xác định consumer group đọc topic.
- `auto-offset-reset: earliest` chỉ được áp dụng khi group chưa có committed offset hợp lệ hoặc offset nằm ngoài phạm vi log; nó không khiến group đã có offset hợp lệ tự đọc lại từ đầu.
- `acks: all` là chính sách xác nhận ghi của producer, không liên quan đến cách chuỗi được mã hóa.

Nếu key là chuỗi nhưng value là object hoặc byte array, hãy cấu hình serializer cho từng phía độc lập. Không bắt buộc key và value phải dùng cùng một kiểu dữ liệu.

## 5. Gửi và nhận chuỗi bằng KafkaTemplate và @KafkaListener

Sau khi cấu hình serializer/deserializer, có thể dùng `KafkaTemplate<String, String>` để gửi chuỗi:

```java
@Service
public class NotificationPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public NotificationPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(String userId, String message) {
        kafkaTemplate.send("notifications", userId, message);
    }
}
```

`userId` là key, `message` là value. Key có thể giúp các thông báo của cùng một người dùng được định tuyến vào cùng partition theo partitioner đang dùng. Điều này hữu ích nếu cần giữ thứ tự sự kiện theo user trong một partition.

Consumer có thể nhận chuỗi trực tiếp:

```java
@Component
public class NotificationListener {

    @KafkaListener(
            topics = "notifications",
            groupId = "notification-reader")
    public void onMessage(String message) {
        notificationService.handle(message);
    }
}
```

Nếu cần key, partition và offset để truy vết, nhận `ConsumerRecord`:

```java
@KafkaListener(
        topics = "notifications",
        groupId = "notification-reader")
public void onMessage(ConsumerRecord<String, String> record) {
    log.info("key={}, partition={}, offset={}, value={}",
            record.key(),
            record.partition(),
            record.offset(),
            record.value());
}
```

Trong Spring Kafka 3.x, `KafkaTemplate.send()` trả về `CompletableFuture<SendResult<K, V>>`. Ứng dụng nên theo dõi kết quả gửi nếu cần xác nhận publish thành công; API ở các phiên bản Spring Kafka cũ có thể trả về `ListenableFuture`.

## 6. Cấu hình bằng KafkaProducer và KafkaConsumer thuần

Nếu không dùng Spring Boot, có thể cấu hình trực tiếp Kafka client. Producer:

```java
Properties producerProps = new Properties();
producerProps.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
producerProps.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class.getName());
producerProps.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class.getName());

try (KafkaProducer<String, String> producer =
             new KafkaProducer<>(producerProps)) {
    ProducerRecord<String, String> record =
            new ProducerRecord<>("notifications", "user-42", "Xin chào");
    producer.send(record, (metadata, exception) -> {
        if (exception != null) {
            log.error("Gửi message thất bại", exception);
        } else {
            log.info("partition={}, offset={}",
                    metadata.partition(), metadata.offset());
        }
    });
}
```

Consumer:

```java
Properties consumerProps = new Properties();
consumerProps.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
consumerProps.put(ConsumerConfig.GROUP_ID_CONFIG, "notification-reader");
consumerProps.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName());
consumerProps.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName());
consumerProps.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
consumerProps.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

try (KafkaConsumer<String, String> consumer =
             new KafkaConsumer<>(consumerProps)) {
    consumer.subscribe(List.of("notifications"));

    while (running) {
        ConsumerRecords<String, String> records =
                consumer.poll(Duration.ofMillis(1000));

        for (ConsumerRecord<String, String> record : records) {
            process(record.key(), record.value());
        }

        consumer.commitSync();
    }
}
```

Các ví dụ lược bớt import, logger, biến `running` và phần xử lý shutdown. `try-with-resources` giúp đóng client khi thoát khỏi scope. Trong ứng dụng thực tế, chỉ commit sau khi các record tương ứng đã được xử lý thành công; nếu xử lý lỗi mà vẫn commit, record có thể bị bỏ qua ở lần chạy tiếp theo.

## 7. Encoding và cấu hình charset

Mặc định `StringSerializer` và `StringDeserializer` dùng UTF-8. Kafka client có các thuộc tính cấu hình encoding cho key/value riêng biệt và thuộc tính chung làm fallback:

| Phía | Thuộc tính riêng | Thuộc tính chung |
|---|---|---|
| Serializer | `key.serializer.encoding`, `value.serializer.encoding` | `serializer.encoding` |
| Deserializer | `key.deserializer.encoding`, `value.deserializer.encoding` | `deserializer.encoding` |

Thông thường nên giữ UTF-8 ở cả hai phía thay vì dùng charset khác. Nếu hệ thống cũ bắt buộc dùng một encoding khác, phải cấu hình cùng charset cho producer và consumer của trường tương ứng, đồng thời kiểm thử dữ liệu có dấu và ký tự ngoài ASCII.

Ví dụ tự chuyển chuỗi sang byte bằng UTF-8 khi cần tương tác với hệ thống byte-level:

```java
byte[] payload = message.getBytes(StandardCharsets.UTF_8);
String restored = new String(payload, StandardCharsets.UTF_8);
```

Không dùng `new String(bytes)` hoặc `message.getBytes()` không chỉ rõ charset trong code tích hợp, vì chúng phụ thuộc default charset của JVM/môi trường và có thể gây khác biệt giữa máy phát triển, container và production. Khi dùng Kafka `StringSerializer`/`StringDeserializer`, để client xử lý theo UTF-8 mặc định thường là lựa chọn đơn giản và nhất quán nhất.

## 8. StringSerializer không tự chuyển object thành JSON

Một nhầm lẫn phổ biến là nghĩ `StringSerializer` có thể gửi trực tiếp một object Java. Serializer này chỉ nhận `String`. Nếu muốn gửi object như `OrderCreated`, cần chuyển object thành chuỗi JSON trước, hoặc dùng serializer chuyên dụng như Spring Kafka `JsonSerializer`, Avro, Protobuf hay serializer theo schema registry.

Ví dụ chuyển object thành JSON string bằng Jackson:

```java
String json = objectMapper.writeValueAsString(orderCreated);
kafkaTemplate.send("orders.events", orderCreated.orderId(), json);
```

Consumer nhận chuỗi rồi parse JSON:

```java
@KafkaListener(topics = "orders.events", groupId = "order-reader")
public void onOrder(String json) throws JsonProcessingException {
    OrderCreated event = objectMapper.readValue(json, OrderCreated.class);
    orderService.handle(event);
}
```

Trong mô hình này, Kafka chỉ biết value là byte được tạo từ chuỗi JSON. `StringDeserializer` khôi phục JSON text; Jackson mới là thành phần chuyển JSON thành object Java. Vì `StringSerializer` không thêm type header hay schema metadata, producer và consumer phải thống nhất cấu trúc JSON, tên field, kiểu dữ liệu và chính sách versioning.

Nếu payload cần schema rõ ràng, kiểm tra tương thích giữa các phiên bản hoặc dùng nhiều ngôn ngữ, cân nhắc Avro/Protobuf/JSON Schema cùng schema registry thay vì tự quản lý JSON string không có contract.

## 9. Key và value có thể dùng serializer khác nhau

Kafka cho phép key và value có kiểu khác nhau. Ví dụ key là chuỗi `orderId`, còn value là JSON object được serialize bởi `JsonSerializer`:

```yaml
spring:
  kafka:
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
```

Khi đó generic type của `KafkaTemplate` có thể là `KafkaTemplate<String, OrderCreated>`, không phải `KafkaTemplate<String, String>`. Hãy bảo đảm deserializer phía consumer tương thích với serializer phía producer. Việc đổi value serializer từ String sang JSON object là thay đổi contract dữ liệu; các consumer cũ đang mong đợi chuỗi có thể không đọc được đúng cách.

## 10. Null, chuỗi rỗng và tombstone

Với String serializer/deserializer, cần phân biệt null và chuỗi rỗng:

```java
serializer.serialize("customer-state", null); // trả về null
serializer.serialize("customer-state", "");  // byte[] độ dài 0
```

Trong topic có `cleanup.policy=compact`, record có key khác null và value null thường được dùng làm tombstone để đánh dấu xóa key. Consumer nhận tombstone dưới dạng `record.value() == null`. Nếu ứng dụng parse JSON hoặc gọi `isBlank()` mà không kiểm tra null trước, có thể phát sinh `NullPointerException`.

Ví dụ xử lý rõ ràng:

```java
@KafkaListener(topics = "customer-state", groupId = "customer-indexer")
public void onCustomer(ConsumerRecord<String, String> record) {
    if (record.value() == null) {
        customerIndex.delete(record.key());
        return;
    }

    if (record.value().isBlank()) {
        log.warn("Payload rỗng tại partition={}, offset={}",
                record.partition(), record.offset());
        return;
    }

    customerIndex.update(record.key(), record.value());
}
```

Không coi mọi value null là tombstone trong mọi topic. Ý nghĩa null phụ thuộc contract của topic và nghiệp vụ producer. Với topic thông thường, null có thể là dữ liệu không hợp lệ hoặc một quy ước riêng; hãy xác định rõ contract trước khi xử lý.

## 11. Lỗi serialization và deserialization

Lỗi ở phía producer có thể xuất hiện khi serializer không xử lý được dữ liệu đầu vào hoặc cấu hình không đúng. Với `StringSerializer`, lỗi thường gặp là ứng dụng truyền kiểu không phải `String` vào `KafkaTemplate` có generic type không phù hợp, hoặc cấu hình class serializer sai. Ngoài lỗi chuyển đổi, việc gửi tới broker còn có thể thất bại do network, authorization, timeout hoặc topic.

Lỗi ở phía consumer có thể xảy ra khi cấu hình deserializer sai hoặc byte dữ liệu không theo encoding/format mà ứng dụng mong đợi. Nếu producer ghi JSON string nhưng consumer dùng `JsonDeserializer` với type mapping không phù hợp, lỗi không nằm ở `StringDeserializer`; hai phía đang không thống nhất contract.

Một số biểu hiện thường gặp:

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `ClassCastException` hoặc lỗi generic/serializer | Kiểu dữ liệu gửi không khớp serializer đã cấu hình | Kiểm tra `KafkaTemplate<K, V>` và key/value serializer |
| Ký tự tiếng Việt bị lỗi | Charset hai phía khác nhau hoặc dữ liệu được encode không thống nhất | Chuẩn hóa UTF-8 và kiểm thử chuỗi Unicode |
| Consumer nhận `null` | Record có null value, tombstone hoặc producer gửi null | Kiểm tra contract, key, topic cleanup policy và producer |
| Consumer nhận chuỗi JSON nhưng parse thất bại | JSON không hợp lệ hoặc schema/version khác | Kiểm tra payload, contract và versioning |
| `SerializationException`/`RecordDeserializationException` | Deserializer không đọc được byte hoặc cấu hình sai | Kiểm tra serializer producer, deserializer consumer và byte thực tế |
| Listener dừng khi gặp record lỗi | Deserialization exception xảy ra trước khi listener xử lý | Cân nhắc `ErrorHandlingDeserializer` và error handler của Spring Kafka |

Với Spring Kafka, có thể bọc deserializer bằng `ErrorHandlingDeserializer` để chuyển lỗi deserialize vào cơ chế xử lý lỗi của container thay vì làm consumer dừng ngoài luồng listener như cách xử lý mặc định của client. Ví dụ:

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.key.delegate.class]": org.apache.kafka.common.serialization.StringDeserializer
        "[spring.deserializer.value.delegate.class]": org.apache.kafka.common.serialization.StringDeserializer
```

Chỉ cần dùng wrapper này khi ứng dụng muốn tích hợp lỗi deserialize với error handler/recoverer. Nếu dữ liệu luôn là chuỗi và contract được kiểm soát, `StringDeserializer` trực tiếp là cấu hình đơn giản hơn. Cách truy cập exception và chuyển record lỗi sang dead-letter topic cần cấu hình tương thích với phiên bản Spring Kafka.

## 12. Kiểm thử StringSerializer và StringDeserializer

Có thể kiểm thử round-trip độc lập mà không cần broker: serialize một chuỗi thành byte rồi deserialize lại, kết quả phải bằng chuỗi ban đầu.

```java
class StringSerializationTest {

    private final StringSerializer serializer = new StringSerializer();
    private final StringDeserializer deserializer = new StringDeserializer();

    @Test
    void shouldRoundTripVietnameseText() {
        String input = "Xin chào Kafka – tiếng Việt";

        byte[] bytes = serializer.serialize("test-topic", input);
        String actual = deserializer.deserialize("test-topic", bytes);

        assertEquals(input, actual);
    }

    @Test
    void shouldPreserveEmptyString() {
        byte[] bytes = serializer.serialize("test-topic", "");

        assertEquals(0, bytes.length);
        assertEquals("", deserializer.deserialize("test-topic", bytes));
    }

    @Test
    void shouldPreserveNull() {
        assertNull(serializer.serialize("test-topic", null));
        assertNull(deserializer.deserialize("test-topic", null));
    }
}
```

Đây là unit test cho hành vi chuyển đổi của serializer/deserializer. Để kiểm thử tích hợp, hãy gửi record qua broker thử nghiệm hoặc Embedded Kafka/Testcontainers, sau đó xác minh key, value, partition và offset ở consumer. Nên có test cho Unicode, chuỗi rỗng, null/tombstone nếu topic hỗ trợ compact, và payload JSON nếu ứng dụng dùng JSON string.

## 13. Các nguyên tắc khi dùng StringSerializer/StringDeserializer

1. Dùng UTF-8 mặc định và giữ cùng encoding ở tất cả producer/consumer.
2. Khai báo rõ serializer cho key và value; không giả định hai trường luôn cùng kiểu.
3. Dùng `KafkaTemplate<String, String>` khi cả key và value thực sự là chuỗi.
4. Nếu gửi JSON, serialize object thành JSON string trước và parse ở consumer; `StringSerializer` không tự xử lý object.
5. Xác định contract cho null, chuỗi rỗng và tombstone.
6. Kiểm tra kết quả future/callback gửi và cấu hình error handler cho lỗi deserialize nếu cần.
7. Khi thay đổi serializer hoặc format payload, xem đó là thay đổi contract giữa producer và consumer.
8. Với dữ liệu cần schema evolution hoặc nhiều ngôn ngữ, cân nhắc serializer có schema như Avro/Protobuf/JSON Schema.

## Checklist

- Producer dùng `StringSerializer` cho đúng key/value kiểu `String`.
- Consumer dùng `StringDeserializer` tương ứng với dữ liệu producer ghi.
- Hai phía thống nhất UTF-8 hoặc charset đã chọn.
- Phân biệt `null` với chuỗi rỗng và hiểu ý nghĩa tombstone nếu dùng compacted topic.
- Không gửi object trực tiếp qua `StringSerializer`; chuyển sang JSON string hoặc serializer phù hợp.
- Listener xử lý null an toàn và có logging metadata khi cần truy vết.
- Có kiểm thử round-trip với Unicode, chuỗi rỗng và null.
- Có kiểm thử tích hợp cho contract producer-consumer nếu topic được chia sẻ giữa nhiều dịch vụ.

`StringSerializer` và `StringDeserializer` là lựa chọn đơn giản, hiệu quả khi dữ liệu Kafka thực sự là văn bản. Khi thống nhất encoding, kiểu key/value và contract payload, ứng dụng Spring Kafka có thể trao đổi chuỗi ổn định. Với object có cấu trúc, hãy chọn cách serialize rõ ràng để consumer có thể đọc và tiến hóa dữ liệu an toàn.
