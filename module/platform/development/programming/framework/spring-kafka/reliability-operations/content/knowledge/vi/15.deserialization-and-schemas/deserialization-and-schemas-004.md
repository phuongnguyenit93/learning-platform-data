# Lỗi deserialize value

Trong Spring Kafka, **lỗi deserialize value** xảy ra khi consumer đã lấy được bytes của một record từ Kafka nhưng **không thể chuyển phần value đó thành kiểu dữ liệu mà ứng dụng cần**. Đây là một trong những lỗi dễ làm consumer không tiến được offset vì bước deserialize thường diễn ra **bên trong lời gọi KafkaConsumer.poll()**, trước khi phương thức được đánh dấu **@KafkaListener** nhận record.

Ví dụ: producer ghi một JSON có trường quantity là chuỗi không hợp lệ, còn consumer được cấu hình dùng JsonDeserializer để tạo OrderCreated. Nếu deserializer ném exception, listener chưa được gọi, nên một try/catch bên trong listener hoàn toàn không có cơ hội bắt lỗi. Cấu hình error handler thông thường mà không chuẩn bị cho lỗi poll cũng có thể khiến cùng record được fetch lặp lại và consumer liên tục báo lỗi.

Trong vận hành đáng tin cậy, mục tiêu không chỉ là “làm cho consumer chạy tiếp”. Hệ thống cần **giữ được record lỗi để điều tra**, xác định lỗi do dữ liệu hay cấu hình/schema, lựa chọn retry/recovery có chủ đích, và chỉ tiến offset sau khi chính sách xử lý lỗi đã hoàn tất.

## 1. Deserialize value nằm ở đâu trong pipeline?

Một Kafka record có key, value, headers, topic, partition và offset. Kafka lưu key và value dưới dạng bytes. Khi consumer đọc record, client deserializer chuyển chúng từ bytes sang object Java.

~~~mermaid
flowchart TD
    A["Producer ghi bytes vào Kafka"] --> B["Kafka topic / partition"]
    B --> C["KafkaConsumer.poll()"]
    C --> D["Key deserializer"]
    D --> E["Value deserializer"]
    E --> F{"Value đọc được?"}
    F -->|Có| G["Spring Kafka listener adapter"]
    G --> H["@KafkaListener xử lý nghiệp vụ"]
    F -->|Không| I["Deserialization failure"]
    I --> J["ErrorHandlingDeserializer / error handling"]
    J --> K["Recovery: DLT, quarantine hoặc dừng có kiểm soát"]
~~~

Phải phân biệt hai loại lỗi dễ nhầm:

- **Deserialization error:** Kafka client/deserializer không chuyển bytes thành object thành công, xảy ra trong hoặc xung quanh poll.
- **Message conversion / listener binding error:** bytes đã được deserializer chấp nhận, nhưng Spring Messaging không chuyển object thành tham số phương thức listener hoặc validation sau đó thất bại.

Hai lỗi có thời điểm phát sinh, exception type và recovery path khác nhau. Việc cấu hình ErrorHandlingDeserializer chủ yếu xử lý lớp lỗi đầu tiên.

## 2. Ví dụ minh họa lỗi value

Producer gửi một record như sau:

~~~json
{
  "eventId": "evt-1001",
  "orderId": 456,
  "quantity": "not-a-number"
}
~~~

Consumer kỳ vọng Java record:

~~~java
package com.example.orders.events;

public record OrderCreated(
        String eventId,
        long orderId,
        int quantity
) {}
~~~

Khi JsonDeserializer không thể tạo object vì trường quantity không phù hợp, lỗi có thể xuất phát từ Jackson và được bọc trong Kafka SerializationException hoặc exception của Spring Kafka.

Một record khác có thể chứa bytes không phải JSON:

~~~text
7B 22 65 76 65 6E 74 49 64 22 3A FF FE 00
~~~

Những bytes đó không bảo đảm tạo được object OrderCreated. Nhưng Kafka broker không kiểm tra JSON/Java type khi lưu record: nó chỉ lưu bytes. Vì vậy, topic có thể chứa record mà phiên bản consumer hiện tại không đọc được.

## 3. Những nguyên nhân thường gặp

| Nhóm nguyên nhân | Ví dụ | Hướng điều tra |
|---|---|---|
| Payload sai định dạng | Chuỗi bị cắt, bytes không phải JSON | Xem raw bytes an toàn và serializer producer |
| Schema không tương thích | Consumer yêu cầu field mới nhưng producer dùng format cũ | Đối chiếu schema/version và quy tắc compatibility |
| Kiểu dữ liệu không hợp lệ | String thay vì integer, enum value không tồn tại | Xem JSON field và object mapping |
| Cấu hình deserializer sai | Dùng StringDeserializer cho bytes Avro | Xác định serializer thực tế ở producer |
| Type header sai/thiếu | Header chỉ tới class không còn tồn tại | Kiểm tra type mappings, JsonDeserializer configuration |
| Trusted packages | JsonDeserializer không tin package từ type header | Cấu hình allowlist đúng package |
| Schema Registry | Không truy xuất được schema ID, registry timeout | Kiểm tra registry, schema ID, credential, network |
| Class/version mismatch | Consumer class không còn field/constructor cần thiết | Đối chiếu artifact deploy và contract |
| Poison record | Một record cố định luôn gây exception | Định vị topic-partition-offset và đưa vào recovery |
| Mixed formats | Topic có cả JSON, String và Avro không có envelope | Thống nhất event contract hoặc dùng deserializer phù hợp |

Không nên gộp mọi lỗi deserialize thành “JSON sai”. Avro, Protobuf, JSON Schema và custom binary format đều có failure mode riêng. Chẩn đoán phải bắt đầu từ encoding/serializer mà producer thực sự sử dụng.

## 4. Vì sao try/catch trong @KafkaListener không đủ?

Một listener có thể chứa:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "inventory-service"
)
public void onOrder(OrderCreated event) {
    try {
        inventoryService.reserve(event);
    } catch (RuntimeException ex) {
        log.error("Business processing failed", ex);
        throw ex;
    }
}
~~~

Code này chỉ chạy **sau khi listener container đã nhận một value tương thích**. Nếu KafkaConsumer.poll() ném lỗi do deserializer trước đó, phương thức onOrder không được gọi.

Một cấu hình chưa phù hợp có thể tạo chuỗi:

~~~text
poll -> deserializer throws -> poll fails
poll -> same record -> deserializer throws -> poll fails
poll -> same record -> deserializer throws -> poll fails
...
~~~

Offset của record gây lỗi chưa được xử lý theo chính sách mong muốn. Tăng số lần retry một cách mù quáng cũng không sửa được bytes hoặc schema.

Hướng xử lý phổ biến trong Spring Kafka là đặt **ErrorHandlingDeserializer** làm lớp bọc cho value deserializer. Khi delegate deserializer thất bại, lớp bọc có thể giữ thông tin lỗi trong header để container/error handler nhận diện record lỗi thay vì chỉ để lỗi thoát ra khỏi poll mà không có record context phù hợp.

## 5. ErrorHandlingDeserializer hoạt động thế nào?

**ErrorHandlingDeserializer** là một deserializer wrapper của Spring Kafka. Nó giao bytes cho **delegate deserializer** đã cấu hình. Nếu delegate thành công, nó trả object bình thường. Nếu delegate thất bại, nó ghi nhận dữ liệu và thông tin exception vào header tương ứng, đồng thời cho container biết record cần được xử lý theo error path.

~~~mermaid
flowchart TD
    A["Value bytes từ Kafka"] --> B["ErrorHandlingDeserializer"]
    B --> C["Delegate: JsonDeserializer"]
    C --> D{"Deserialize thành công?"}
    D -->|Có| E["Trả OrderCreated cho listener"]
    D -->|Không| F["Ghi thông tin DeserializationException vào header"]
    F --> G["Value có thể là null / đối tượng fallback"]
    G --> H["Container và error handler nhận diện failed record"]
    H --> I["Recovery / DLT theo cấu hình"]
~~~

Với cấu hình record listener phổ biến, container có thể phát hiện header lỗi deserialize và đưa record qua error handler, không gọi listener nghiệp vụ với value hỏng. Điều này cho phép **DefaultErrorHandler** và **DeadLetterPublishingRecoverer** xử lý record lỗi theo policy.

Các điểm quan trọng:

- ErrorHandlingDeserializer **không tự sửa payload**.
- Nó **không tự publish DLT** nếu recoverer chưa được cấu hình.
- Nó có thể trả null khi delegate thất bại; không nên hiểu mọi null là một event nghiệp vụ hợp lệ.
- Nó giúp error handler có đủ ngữ cảnh record và exception.
- Khi cần DLT cho raw bytes, producer recovery phải serialize được byte array.

## 6. Cấu hình ErrorHandlingDeserializer cho value với Spring Boot

Ví dụ ứng dụng nhận JSON OrderCreated:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: inventory-service
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.trusted.packages: com.example.orders.events
        spring.json.value.default.type: com.example.orders.events.OrderCreated
        spring.json.use.type.headers: false
    listener:
      ack-mode: record
~~~

Ý nghĩa:

- **value-deserializer** chọn ErrorHandlingDeserializer làm lớp ngoài.
- **spring.deserializer.value.delegate.class** chỉ định JsonDeserializer thực hiện chuyển bytes thành object.
- **spring.json.trusted.packages** chỉ cho phép các package cần thiết nếu type metadata được dùng.
- **spring.json.value.default.type** xác định class đích khi không sử dụng type headers.
- **spring.json.use.type.headers: false** cho phép ví dụ này thống nhất type đích thay vì phụ thuộc header được producer gửi.
- **enable-auto-commit: false** để listener container quản lý tiến độ offset theo acknowledgement semantics.

Cần điều chỉnh class name, package, serializers và Kafka bootstrap settings theo ứng dụng. Cú pháp dotted keys nằm dưới **consumer.properties** để chuyển xuống cấu hình Kafka client/delegate. Nếu một file YAML khác hoặc ConsumerFactory viết bằng Java ghi đè các giá trị này, cấu hình thực tế có thể khác.

Không nên đặt **spring.json.trusted.packages: '*'** chỉ để “hết lỗi” khi chưa hiểu loại type headers và mức độ tin cậy của producer. Chọn allowlist package hoặc type mappings rõ ràng. Type header và class deserialization là một phần của bề mặt dữ liệu đầu vào cần kiểm soát.

## 7. Cấu hình bằng Java ConsumerFactory

Nếu ứng dụng quản lý consumer properties và deserializer bằng code, có thể dùng ErrorHandlingDeserializer bọc trực tiếp delegate:

~~~java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.support.serializer.ErrorHandlingDeserializer;
import org.springframework.kafka.support.serializer.JsonDeserializer;

@Configuration
public class ConsumerConfiguration {

    @Bean
    ConsumerFactory<String, OrderCreated> orderConsumerFactory() {

        Map<String, Object> properties = new HashMap<>();
        properties.put(
                ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
                "localhost:9092"
        );
        properties.put(
                ConsumerConfig.GROUP_ID_CONFIG,
                "inventory-service"
        );
        properties.put(
                ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,
                false
        );

        JsonDeserializer<OrderCreated> delegate =
                new JsonDeserializer<>(OrderCreated.class);

        delegate.addTrustedPackages(
                "com.example.orders.events"
        );

        ErrorHandlingDeserializer<OrderCreated> safeValue =
                new ErrorHandlingDeserializer<>(delegate);

        return new DefaultKafkaConsumerFactory<>(
                properties,
                new StringDeserializer(),
                safeValue
        );
    }
}
~~~

Ví dụ tạo deserializer programmatically và truyền trực tiếp vào factory, vì vậy không cần thêm value deserializer class vào properties. Khi dùng API constructor với target type, hãy chú ý cấu hình có dùng type headers hay không; nếu producer gửi type metadata khác, mapping cần thống nhất.

Không đồng thời cấu hình các thuộc tính programmatic và properties ở nhiều nơi mà không kiểm tra thứ tự ưu tiên. Khi triển khai trong Spring Boot, có thể sử dụng KafkaProperties/auto-configuration hoặc build properties từ môi trường thay vì hard-code bootstrap servers như ví dụ học tập.

## 8. Key deserialization và value deserialization là hai đường riêng

Mỗi Kafka record có thể có key và value, và mỗi phần được deserialize độc lập.

| Khía cạnh | Key | Value |
|---|---|---|
| Thuộc tính consumer | key-deserializer | value-deserializer |
| ErrorHandlingDeserializer delegate | spring.deserializer.key.delegate.class | spring.deserializer.value.delegate.class |
| Nguồn lỗi | Key bytes | Value bytes |
| Error header | Header lỗi key | Header lỗi value |
| Recovery payload | Key gốc cần serializer phù hợp | Value gốc cần serializer phù hợp |

Nếu producer dùng StringSerializer cho key và JsonSerializer cho value, có thể giữ StringDeserializer cho key và chỉ bọc value bằng ErrorHandlingDeserializer. Nhưng nếu key cũng có nguy cơ deserialize lỗi, hãy xem xét bọc cả key:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.orders.events.OrderCreated
        spring.json.trusted.packages: com.example.orders.events
        spring.json.use.type.headers: false
~~~

Bọc cả hai không có nghĩa cả hai luôn hỏng. Nó làm cho lỗi deserialize ở key hoặc value có đường recovery rõ ràng. Tuy nhiên, DLT producer sẽ phải hỗ trợ key/value gốc khi tương ứng bị lỗi.

## 9. DefaultErrorHandler và DLT cho value lỗi

ErrorHandlingDeserializer giúp container nhận diện record có lỗi; error handler quyết định xử lý. Một lựa chọn phổ biến là **DefaultErrorHandler** kết hợp **DeadLetterPublishingRecoverer**.

~~~java
import org.apache.kafka.common.TopicPartition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
public class RecoveryConfiguration {

    @Bean
    DeadLetterPublishingRecoverer deadLetterRecoverer(
            KafkaTemplate<Object, Object> recoveryTemplate) {

        return new DeadLetterPublishingRecoverer(
                recoveryTemplate,
                (record, exception) -> new TopicPartition(
                        record.topic() + ".DLT",
                        record.partition()
                )
        );
    }

    @Bean
    DefaultErrorHandler errorHandler(
            DeadLetterPublishingRecoverer recoverer) {

        var handler = new DefaultErrorHandler(
                recoverer,
                new FixedBackOff(1_000L, 2L)
        );

        return handler;
    }
}
~~~

Đây là ví dụ wiring recovery. **KafkaTemplate<Object,Object>** phải được tạo với producer serializer phù hợp; nếu không, record lỗi có thể không publish DLT được.

Khi record value deserialize thất bại, lỗi thường không thể được giải quyết bằng việc đưa cùng bytes qua cùng delegate deserializer nhiều lần. Các phiên bản DefaultErrorHandler hiện đại coi nhiều lỗi liên quan deserialization/conversion là lỗi không retryable theo default classification, nhưng không nên dựa vào mặc định mà không xác minh phiên bản và policy của ứng dụng.

Nên ghi rõ nguyên tắc:

- Dữ liệu/schema hỏng vĩnh viễn → quarantine/DLT, sửa producer hoặc contract.
- Schema Registry tạm unavailable → có thể cần retry với chiến lược khác hoặc dừng có kiểm soát, tùy exception classification và thời gian outage.
- Lỗi cấu hình deserializer của toàn deployment → sửa cấu hình; đẩy toàn bộ topic vào DLT có thể là lựa chọn sai.
- Lỗi dữ liệu một record riêng lẻ → recovery theo record, giữ bằng chứng và tiếp tục consumer khi an toàn.

### Gắn handler vào container factory

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
orderListenerContainerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        DefaultErrorHandler errorHandler) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(errorHandler);

    return factory;
}
~~~

Listener cần chọn factory này bằng tên hoặc dùng bean mặc định phù hợp. Nếu listener đang sử dụng factory khác, error handler ở trên không giúp xử lý record đó.

## 10. DLT của lỗi deserialize cần giữ raw bytes

Đây là điểm quan trọng: record bị lỗi value deserialize không nhất thiết có một object domain để publish lại. Khi dùng ErrorHandlingDeserializer, Spring Kafka có thể cung cấp **raw value bytes** của record lỗi cho DeadLetterPublishingRecoverer để gửi tới DLT.

Nếu recovery producer chỉ có JsonSerializer cho OrderCreated, nó có thể không xử lý đúng byte array của record lỗi. DLT publisher cần hỗ trợ cả trường hợp object hợp lệ (lỗi nghiệp vụ) và raw bytes (lỗi deserialize).

Giải pháp là dùng serializer phân luồng theo kiểu value. Với phiên bản Spring Kafka hỗ trợ **DelegatingByTypeSerializer**, có thể tạo mapping:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

import org.apache.kafka.common.serialization.ByteArraySerializer;
import org.apache.kafka.common.serialization.Serializer;
import org.springframework.kafka.support.serializer.DelegatingByTypeSerializer;
import org.springframework.kafka.support.serializer.JsonSerializer;

// Minh họa cấu hình value serializer cho recovery producer.
Map<Class<?>, Serializer<?>> delegates = new LinkedHashMap<>();
delegates.put(byte[].class, new ByteArraySerializer());
delegates.put(OrderCreated.class, new JsonSerializer<OrderCreated>());

Serializer<Object> recoveryValueSerializer =
        new DelegatingByTypeSerializer(delegates, true);
~~~

Giá trị recoveryValueSerializer cần được đưa vào ProducerFactory/KafkaTemplate dành cho DLT. Đoạn code minh họa riêng phần value serialization, không phải một bean producer hoàn chỉnh.

Cần kiểm tra thêm key serializer: nếu key có thể bị lỗi deserialize và cần gửi raw key bytes sang DLT, producer cũng cần mapping cho key. Nếu key luôn là String hợp lệ, StringSerializer có thể đủ.

Đừng chuyển bytes lỗi sang JSON string giả, Base64 hoặc object placeholder mà không lưu metadata gốc. Việc chuyển format có thể làm mất khả năng điều tra nguyên nhân thực sự và làm khó replay sau khi sửa schema.

## 11. Metadata trong record DLT

Khi publish DLT, DeadLetterPublishingRecoverer có thể thêm headers mô tả record gốc và exception. Những thông tin cần giữ bao gồm:

- Original topic.
- Original partition.
- Original offset.
- Original timestamp và timestamp type khi có.
- Consumer group đã xử lý.
- Exception class, message và thông tin chẩn đoán được cho phép.
- Event ID hoặc correlation ID nghiệp vụ nếu có.

Ví dụ:

~~~text
DLT topic: orders.created.DLT
DLT partition: 2
DLT offset: 501

Original topic: orders.created
Original partition: 2
Original offset: 128
Failure type: DeserializationException
Underlying cause: MismatchedInputException
~~~

DLT offset là offset mới, **không phải** original offset. Khi điều tra, kết hợp DLT metadata với original topic-partition-offset để xác định bytes của record lỗi.

Tên và định dạng header cụ thể thay đổi theo phiên bản Spring Kafka. Khi code đọc headers, ưu tiên các constant/API có sẵn của KafkaHeaders hoặc SerializationUtils ở đúng dependency thay vì hard-code một tên header suy đoán.

Exception headers có thể chứa stack trace, class names và nội dung nhạy cảm. Cần kiểm soát ACL, retention và hệ thống log/export cho DLT; không công khai toàn bộ raw payload hoặc exception message trong dashboard.

## 12. DLT partition count và quyền ghi

Nếu recoverer chọn destination cùng partition index với record nguồn:

~~~java
(record, exception) -> new TopicPartition(
        record.topic() + ".DLT",
        record.partition()
)
~~~

DLT phải có đủ partition. Ví dụ topic nguồn có partition 0–7, nhưng DLT chỉ có partition 0–3 thì những record từ partition 4–7 không thể được publish đúng index.

Có thể chọn partition âm trong destination resolver để DeadLetterPublishingRecoverer không gán partition tường minh và để producer chọn partition, nếu phù hợp với yêu cầu vận hành:

~~~java
(record, exception) -> new TopicPartition(
        "shared-deserialization.DLT",
        -1
)
~~~

Phải xác nhận hành vi này theo phiên bản và kiểm thử với topic thật. Khi không giữ index, DLT headers phải giúp truy lại original partition.

Quyền tối thiểu thường gồm:

| Principal | Quyền liên quan |
|---|---|
| Consumer source | READ topic nguồn, quyền consumer group |
| DLT producer | WRITE DLT topic |
| DLT consumer/recovery service | READ DLT topic, quyền consumer group |
| Topic provisioning | CREATE/ALTER chỉ nếu được phân công |

Một value deserialization failure không thể được khắc phục bằng việc cấp ALL trên toàn cluster. ACL phải được cấp đúng resource, và DLT publishing cần được giám sát độc lập với việc listener nghiệp vụ lỗi.

## 13. Value null: bản thân null không chứng minh lỗi deserialize

Trong một số topic, **null value** là hợp lệ. Ví dụ tombstone trong compacted topic có value null để biểu diễn thao tác xóa theo key.

Ngược lại, ErrorHandlingDeserializer cũng có thể trả null value khi delegate deserialize lỗi và gắn exception header.

Vì vậy, ứng dụng không nên dùng quy tắc:

~~~java
if (record.value() == null) {
    // Chắc chắn value deserialize bị lỗi.
}
~~~

Quy tắc trên sai trong hệ thống có tombstone, null payload hợp lệ hoặc record fallback. Muốn nhận diện lỗi deserialize, cần xem **exception header** hoặc đối tượng/exception mà Spring Kafka container cung cấp.

Khi xử lý null value ở listener, xác định domain contract: nếu topic compacted, tombstone thường là điều kiện nghiệp vụ cần xử lý riêng; nếu topic cấm null value, việc validation có thể là một bước sau deserialization. Không gộp hai trường hợp vào cùng một chính sách DLT.

## 14. JSON type headers và class mapping

JsonDeserializer có nhiều cách xác định class đích:

1. Class mục tiêu được cấu hình tường minh.
2. Type header do producer gửi.
3. Type mappings hoặc custom type resolver.
4. Deserializer tùy chỉnh.

Các lỗi thường gặp:

- Producer gửi type header trỏ đến class package cũ sau khi refactor.
- Consumer không tin package trong type header.
- Một consumer đọc nhiều event types nhưng được cố định một target class.
- Producer/consumer dùng version thư viện khác với type metadata không tương thích.
- Event schema đã thay đổi nhưng không duy trì khả năng đọc dữ liệu cũ.

Nếu một topic chỉ chứa OrderCreated, có thể cấu hình target type tường minh và không phụ thuộc type headers. Nếu topic chứa nhiều loại event, cần một envelope ổn định hoặc type mappings được kiểm soát.

Không đặt trusted packages bằng wildcard như một cách sửa triệt để lỗi. Wildcard chỉ mở rộng phạm vi type có thể được xử lý; nó không bảo đảm schema compatibility và có thể làm tăng rủi ro xử lý dữ liệu không tin cậy.

## 15. Schema Registry, Avro, Protobuf và JSON Schema

Với các hệ thống dùng Schema Registry, bytes có thể chứa định danh schema. Deserializer sẽ truy xuất hoặc cache schema, sau đó tạo object hoặc dữ liệu generic theo format.

Lỗi có thể nằm ở nhiều tầng:

| Tầng | Triệu chứng | Điều cần xác minh |
|---|---|---|
| Wire format | Magic byte/schema ID không đúng | Producer serializer, topic contract |
| Registry access | Timeout, 401/403, DNS lỗi | Registry URL, auth, network |
| Schema not found | Schema ID không tồn tại hoặc không truy xuất được | Registry cluster, retention/schema catalog |
| Compatibility | Reader/writer schema không tương thích | Version và compatibility policy |
| Specific class | Không tìm được generated class | Classpath, artifact version |
| Logical type | Timestamp/decimal mapping lỗi | Conversion và runtime version |

Trong tình huống registry tạm thời không khả dụng, chỉ chuyển mọi record vào DLT có thể tạo một lượng lớn bản ghi không cần thiết. Cần phân biệt **lỗi dữ liệu của từng record** với **outage hạ tầng ảnh hưởng cả consumer**. Với outage chung, dừng hoặc pause có kiểm soát, cảnh báo và phục hồi hạ tầng có thể phù hợp hơn.

ErrorHandlingDeserializer vẫn hữu ích khi bọc deserializer tương ứng, nhưng chỉ giúp chuyển lỗi sang recovery path. Nó không thay thế quản trị schema và compatibility.

## 16. ErrorHandlingDeserializer không chữa lỗi schema

Một số đội ngũ cấu hình ErrorHandlingDeserializer rồi coi vấn đề schema đã giải quyết. Thực tế nó chỉ đảm bảo lỗi được **quan sát và chuyển đúng đường xử lý**.

Cần xử lý nguyên nhân gốc:

- Định nghĩa event contract và versioning.
- Chọn backward/forward/full compatibility theo nhu cầu consumer/producer.
- Dùng schema validation trong CI/CD.
- Có test producer/consumer compatibility trước deploy.
- Duy trì khả năng đọc record cũ còn nằm trong topic.
- Với breaking change, cân nhắc topic mới hoặc event version có migration rõ ràng.
- Tránh phụ thuộc tên Java class nội bộ như một contract dài hạn giữa dịch vụ.

Ví dụ producer triển khai version mới rồi gửi field mà consumer cũ không hiểu. Consumer cũ có thể DLT nhiều record; nhưng đưa vào DLT không khôi phục được tính tương thích của hai dịch vụ. Cần rollback producer, nâng cấp consumer hoặc thiết kế format hợp tác được giữa các version.

## 17. Khi nào retry và khi nào đưa DLT?

Một nguyên tắc quan trọng: **cùng bytes + cùng deserializer config + cùng schema thường cho cùng kết quả**. Vì vậy, một payload thực sự sai format thường sẽ thất bại lại nếu retry ngay.

Hãy phân loại:

| Nguyên nhân | Cách xử lý thường phù hợp |
|---|---|
| JSON malformed / bytes hỏng | Non-retryable, DLT/quarantine |
| Unsupported event version | DLT hoặc dừng để triển khai consumer tương thích |
| Type header/class không còn tồn tại | Sửa mapping/classpath; cân nhắc pause nếu ảnh hưởng hàng loạt |
| Json trusted packages bị cấu hình sai | Sửa allowlist, có thể dừng consumer thay vì DLT hàng loạt |
| Schema Registry outage | Điều tra hạ tầng, retry có giới hạn hoặc pause |
| Schema ID không tồn tại | Kiểm tra registry/source; DLT khi là lỗi dữ liệu cố định |
| Một record poisoned | Recovery riêng theo record, giữ bytes |
| Serializer producer sai cho toàn topic | Sửa producer/contract và xem xét replay |

Không có một rule đúng cho mọi hệ thống. Quan trọng là chọn chính sách theo **root cause** và tác động tới backlog, DLT capacity, SLA.

## 18. Batch listener cần xử lý cẩn thận hơn

Với record listener, Spring Kafka container thường có thể phát hiện deserialization exception header và đưa record lỗi qua error handler.

Với **batch listener**, một poll chứa nhiều records. ErrorHandlingDeserializer có thể tạo một record có value null và header lỗi, nhưng batch listener/application có thể cần **xác định vị trí record lỗi trong batch** và báo lỗi theo cách mà batch error handler hiểu.

Khái niệm:

~~~java
@KafkaListener(
    topics = "orders.created",
    containerFactory = "orderBatchFactory"
)
public void onBatch(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (int index = 0; index < records.size(); index++) {

        ConsumerRecord<String, OrderCreated> record =
                records.get(index);

        // Kiểm tra deserialization-exception header bằng
        // constant/API của phiên bản Spring Kafka đang dùng.
        // Nếu record lỗi, báo cho batch error handler biết index.
    }

    batchService.process(records);
}
~~~

Với các phiên bản hỗ trợ **BatchListenerFailedException**, listener có thể báo vị trí record lỗi để batch error handler xử lý đúng phần dữ liệu. Tên header/API và semantics khác nhau giữa phiên bản nên cần đối chiếu Javadoc/ tài liệu của dependency đang chạy.

Không để batch listener lặng lẽ bỏ qua record có value null và trả về thành công nếu null thật ra là value deserialization failure. Điều đó có thể khiến offset được commit mà record lỗi không được ghi nhận hoặc recover đúng cách.

Cần xác định rõ:

- Batch có các record khác nhau trong nhiều partition hay không.
- Index record lỗi được báo như thế nào.
- Những record trước/sau lỗi được retry hay commit ra sao.
- Có dùng transactional listener container hay không.
- DLT publishing có giữ raw bytes và original metadata không.

## 19. Message conversion failure khác deserialize failure

Một số trường hợp value deserializer trả về String hoặc byte[] hợp lệ, nhưng @KafkaListener mong đợi OrderCreated. Spring MessageConverter cố biến giá trị thành đối tượng domain và thất bại ở tầng adapter.

Ví dụ:

~~~java
@KafkaListener(topics = "orders.created")
public void onOrder(OrderCreated order) {
    // ...
}
~~~

Nếu deserializer trả String chứa JSON nhưng không có message converter thích hợp, lỗi không nhất thiết do Kafka JsonDeserializer. Chỉ thêm ErrorHandlingDeserializer quanh StringDeserializer sẽ không tạo ra một OrderCreated object.

Với message conversion failure, cần kiểm tra:

- Consumer value deserializer thực tế trả kiểu Java nào.
- Listener parameter type.
- RecordMessageConverter hoặc BatchMessageConverter có cấu hình phù hợp không.
- Các header type, content type và conversion hints.
- Exception type từ listener adapter và error handler.

Không nhầm **DeserializationException** với **MessageConversionException** hoặc **MethodArgumentResolutionException**. Cả ba có thể khiến listener không xử lý được record nhưng cần sửa ở các tầng khác nhau.

## 20. Lỗi deserialize khi dùng @RetryableTopic

**@RetryableTopic** là cơ chế non-blocking retry chuyển record lỗi qua retry topics. Tuy nhiên, lỗi deserialize xảy ra trước listener và có thể không thích hợp với cùng pipeline retry dành cho lỗi nghiệp vụ.

Một record JSON malformed sẽ không tự trở thành JSON hợp lệ sau khi được gửi qua retry topic. Nếu error handler/recovery infrastructure định tuyến nó sang DLT ngay, hành vi đó thường hợp lý hơn retry nhiều phút vô ích.

Nếu dùng @RetryableTopic:

- Xác định consumer nào đọc source/retry topics và deserializer của từng container.
- Kiểm tra deserialization error được ErrorHandlingDeserializer chuyển vào error path nào.
- Đảm bảo DLT/retry producer có thể gửi raw bytes.
- Không đánh đồng attempts của retry-topic topology với blocking retry count của DefaultErrorHandler.
- Nếu lỗi là Schema Registry outage, thiết kế lựa chọn retry/pause theo hạ tầng.
- Kiểm thử record malformed trong topology thực tế, không chỉ test exception do listener ném ra.

Việc chuyển record sang topic mới còn làm thay đổi ordering. Nếu domain yêu cầu thứ tự theo key, phải đánh giá trước khi dùng non-blocking retry cho một lớp lỗi rộng.

## 21. Offset commit và nguy cơ mất record

Sau khi listener/container xử lý một record lỗi, committed offset có thể tiến lên nếu chính sách recovery xem record đã được xử lý. Điều đó có thể đúng nếu raw bytes đã được lưu bền vững vào DLT, nhưng sai nếu recovery publish thất bại hoặc record bị bỏ qua mà không có dấu vết.

Các trạng thái cần phân biệt:

1. **Poll thành công:** consumer nhận được dữ liệu.
2. **Deserialize thành công:** value Java được tạo.
3. **Listener thành công:** nghiệp vụ hoàn tất.
4. **Recovery thành công:** record lỗi được chuyển đến nơi phục hồi theo policy.
5. **Offset commit thành công:** broker lưu checkpoint tiến độ của consumer group.

Năm trạng thái không đồng nhất. Một record có thể deserialize thất bại, được gửi DLT thành công rồi mới commit offset. Một record khác có thể được listener xử lý thành công nhưng process dừng trước commit và được giao lại.

Với recoverer publish bất đồng bộ, phải cấu hình quan sát kết quả gửi phù hợp. DeadLetterPublishingRecoverer có tùy chọn trong các phiên bản hỗ trợ để báo lỗi nếu send result thất bại, ví dụ **setFailIfSendResultIsError(true)**. Cần kiểm tra semantics phiên bản và timeout để không báo recovered khi record thực tế chưa được lưu.

Không dùng consumer.seek() hoặc commitSync() thủ công để nhảy qua record lỗi nếu chưa có quy trình bảo toàn dữ liệu và quyền thực hiện. Đó có thể là data loss được che giấu dưới dạng “consumer đã hết lỗi”.

## 22. Quarantine và replay sau khi sửa schema

Một DLT hoặc quarantine topic nên giữ được giá trị raw bytes, metadata nguồn và nguyên nhân lỗi. Sau khi sửa deserializer/schema, có thể replay có kiểm soát.

Một quy trình:

1. Tìm record lỗi theo original topic, partition, offset và event ID.
2. Lưu hoặc truy xuất raw bytes và headers để kiểm tra định dạng.
3. Xác định producer version và consumer schema liên quan.
4. Sửa serializer/deserializer, schema compatibility hoặc mapping.
5. Kiểm tra parsing trên bản sao dữ liệu trong môi trường an toàn.
6. Chọn topic đích để replay và xác định offset/key semantics.
7. Giữ event ID nghiệp vụ để idempotency hoạt động.
8. Replay có giới hạn tốc độ, quan sát success/failure.
9. Đánh dấu record đã được xử lý hoặc lưu vết replay.
10. Theo dõi DLT backlog và lỗi lặp lại.

Không replay toàn bộ DLT nếu dữ liệu gồm nhiều loại lỗi khác nhau. Một số record có thể chứa bytes không hợp lệ vĩnh viễn hoặc event đã được thực hiện nghiệp vụ qua đường khác.

Replay là một hành động nghiệp vụ và vận hành, không chỉ thao tác copy bytes. Nếu hệ thống cần ordering tuyệt đối, replay một record cũ vào cuối topic có thể không khôi phục được thứ tự xử lý ban đầu.

## 23. Logging và metrics

Khi consumer gặp lỗi deserialize value, log nên phân biệt source record với recovery outcome.

Ví dụ log có cấu trúc:

~~~text
event=kafka_value_deserialization_failed
service=inventory-service
consumer_group=inventory-service
topic=orders.created
partition=3
offset=824
delegate_deserializer=JsonDeserializer
exception_class=DeserializationException
root_cause=MismatchedInputException
recovery_target=orders.created.DLT
~~~

Không nên log nguyên payload nếu chứa PII, payment details hoặc secret. Khi cần lưu raw bytes, giữ trong DLT/quarantine được kiểm soát ACL và retention, thay vì log cả nội dung ra centralized logging.

Các metric nên theo dõi:

| Metric | Ý nghĩa |
|---|---|
| Value deserialization failure rate | Lỗi parse value theo service/topic |
| Root cause class | Lỗi JSON/schema/registry/config |
| DLT publish success/failure | Xác định lỗi đã được lưu recovery chưa |
| DLT ingress rate | Số record vào DLT |
| DLT lag và oldest record age | Tồn đọng xử lý recovery |
| Consumer lag | Topic source có đang tiến không |
| Rebalance count | Thay đổi assignment do consumer lỗi/restart |
| Recovery publisher latency | Độ trễ publish DLT |
| Schema Registry error rate | Phát hiện outage toàn hệ thống |
| ErrorHandlingDeserializer error count | Phát hiện lỗi trước listener |

Metric tags nên dùng giá trị cardinality thấp: service, topic, nhóm exception, environment. Không đưa event ID, offset, key, raw payload hoặc exception message vào metric tags. Đưa các giá trị cần truy vết từng record vào log có kiểm soát.

### Nhận diện sự cố hàng loạt

Nếu vài record riêng lẻ malformed, DLT theo record có thể đủ. Nếu sau deploy consumer đột ngột báo lỗi deserialize cho phần lớn record trên nhiều partition, nên xem là **sự cố tương thích hoặc cấu hình toàn deployment**. Tiếp tục DLT hàng loạt có thể làm mất tiến độ nghiệp vụ hữu ích và gây ngập recovery pipeline.

Cần alert theo **tỷ lệ** lỗi, thời gian bắt đầu, version deploy, topic/schema ID và ảnh hưởng tới SLA.

## 24. Kiểm thử với Kafka broker

Để chứng minh đường recovery hoạt động, nên có integration test dùng EmbeddedKafka hoặc Testcontainers tương thích. Unit test của JsonDeserializer hoặc service không chứng minh poll/error-handler/DLT wiring.

Kịch bản cơ bản:

1. Tạo topic source có nhiều partition và DLT có số partition phù hợp.
2. Cấu hình ErrorHandlingDeserializer với delegate JsonDeserializer.
3. Gửi một record JSON hợp lệ và xác nhận listener nghiệp vụ được gọi.
4. Gửi một value có bytes malformed vào partition cụ thể.
5. Xác nhận listener không xử lý record malformed như OrderCreated hợp lệ.
6. Xác nhận error handler nhận diện DeserializationException.
7. Xác nhận record đến DLT và payload raw bytes được giữ.
8. Kiểm tra header original topic/partition/offset và exception.
9. Xác nhận consumer có thể tiếp tục với record hợp lệ sau lỗi nếu recovery thành công.
10. Tạo một bài test DLT producer không thể publish và xác nhận không xem recovery đã thành công.
11. Thử tombstone/null value hợp lệ nếu topic hỗ trợ.
12. Kiểm tra offset/rebalance/replay behavior theo AckMode.

Không chỉ sử dụng Thread.sleep với thời gian cố định. Dùng polling assertion có timeout để chờ DLT record hoặc xử lý listener. Với test đồng thời nhiều partition, dùng event ID hoặc topic-partition-offset để ghép kết quả chính xác.

### Test schema compatibility

Ngoài integration test container, nên có contract tests với dữ liệu serialized thực tế của producer versions cũ và mới:

- Producer mới → consumer cũ.
- Producer cũ → consumer mới.
- Field optional bị thiếu.
- Field lạ được thêm.
- Null/missing field.
- Enum value chưa biết.
- Schema Registry unavailable.
- Generated class thiếu trên classpath.
- Type header có class package không được tin cậy.

Các test này giúp ngăn lỗi production trước khi record malformed được ghi vào Kafka.

## 25. Runbook khi consumer kẹt ở value deserialization failure

Khi log báo consumer không thể deserialize value:

1. Xác định service, consumer group, topic, partition, offset và thời điểm bắt đầu.
2. Kiểm tra lỗi xảy ra trước listener hay trong message conversion.
3. Thu thập exception class, root cause, delegate deserializer và schema ID nếu có.
4. Xác định consumer đang dùng ErrorHandlingDeserializer hay delegate trực tiếp.
5. Kiểm tra lỗi xuất hiện ở một record hay hàng loạt record sau deploy.
6. Kiểm tra producer serializer, event version và type headers.
7. Nếu dùng Schema Registry, kiểm tra URL, auth, schema ID và health.
8. Kiểm tra DefaultErrorHandler, classification, recoverer và topic DLT.
9. Xác nhận KafkaTemplate/serializer hỗ trợ raw bytes nếu value hỏng.
10. Kiểm tra DLT tồn tại, partition count, retention và producer WRITE ACL.
11. Kiểm tra DLT publish success/failure và committed offset.
12. Không seek/skip thủ công nếu chưa có quyết định bảo toàn dữ liệu.
13. Nếu lỗi do deploy/schema chung, cân nhắc pause hoặc rollback theo runbook thay vì DLT hàng loạt.
14. Sau khi sửa, replay có kiểm soát với idempotency.
15. Theo dõi source lag, DLT backlog và tỷ lệ lỗi sau khôi phục.

Trong sự cố ảnh hưởng nhiều consumer, hãy ưu tiên xác định producer/dependency/schema version vừa thay đổi. Một lỗi cấu hình chung không nên được xử lý bằng cách tăng retry vô hạn hoặc xóa mọi record lỗi.

## 26. Những sai lầm thường gặp

**Chỉ bọc try/catch trong @KafkaListener.** Listener không chạy khi poll deserialize value thất bại trước đó.

**Dùng ErrorHandlingDeserializer nhưng quên delegate.** Lớp bọc cần biết deserializer thực sự để chuyển bytes.

**Cho rằng value null là deserialize failure.** Tombstone/null hợp lệ cần được phân biệt bằng header exception.

**Tăng retry cho malformed bytes.** Cùng dữ liệu và cùng schema thường sẽ thất bại lại; retry không sửa payload.

**Cho mọi exception vào DLT mà không phân loại outage.** Registry downtime hoặc cấu hình sai hàng loạt có thể làm DLT bùng nổ.

**Bỏ qua serializer của DLT.** Raw byte[] từ record lỗi có thể không gửi được bằng serializer chỉ dành cho object domain.

**Đưa original offset vào Kafka record mới như offset DLT.** Kafka gán offset mới; phải giữ original metadata qua headers.

**Đặt trusted packages bằng wildcard để né lỗi.** Cần xác định đúng target type/type mapping, không mở rộng không cần thiết.

**Commit hoặc seek qua lỗi trước khi recovery bền vững.** Có thể làm mất khả năng replay record.

**Chỉ quan sát consumer lag topic nguồn.** DLT có thể đang chứa nhiều record lỗi chưa được giải quyết.

**Dùng batch listener mà không kiểm tra exception headers.** Record có value null do deserialize thất bại có thể bị bỏ qua hoặc được xem là hợp lệ.

**Replay DLT không có idempotency.** Event có thể đã được xử lý một phần hoặc trùng với event khác.

## 27. Checklist trước production

**Deserializer và schema**

- [ ] Consumer có value deserializer tương thích format của producer.
- [ ] ErrorHandlingDeserializer được cấu hình khi cần recovery lỗi poll.
- [ ] Delegate value deserializer được chỉ định đúng.
- [ ] Type headers, target type và trusted packages được xác minh.
- [ ] Có test tương thích schema và dữ liệu versions cũ.

**Recovery**

- [ ] DefaultErrorHandler và DeadLetterPublishingRecoverer gắn với listener container thực sự.
- [ ] DLT producer hỗ trợ raw bytes và object domain khi cần.
- [ ] DLT topic/partition/replication/retention và ACL được provision.
- [ ] Recovery publish failures được phát hiện và báo lỗi.
- [ ] Không tiến offset nếu recovery chưa đáp ứng điều kiện của policy.

**Nghiệp vụ và vận hành**

- [ ] Tombstone/null hợp lệ được phân biệt với deserialization failure.
- [ ] Có quy trình xử lý lỗi schema/configuration hàng loạt.
- [ ] DLT có owner, dashboard và replay runbook.
- [ ] Consumer có idempotency khi record được giao lại.
- [ ] Log/metric có đủ topic-partition-offset, exception và schema metadata.
- [ ] Có integration test malformed bytes, raw DLT payload và producer failure.

## 28. Nguyên tắc thiết kế

**Lỗi deserialize value** xảy ra ở ranh giới giữa bytes trong Kafka và object Java của consumer. Khi lỗi phát sinh trong KafkaConsumer.poll(), listener nghiệp vụ không thể tự xử lý bằng try/catch. ErrorHandlingDeserializer bọc delegate giúp Spring Kafka đưa lỗi và raw data vào error/recovery path, nơi DefaultErrorHandler và DeadLetterPublishingRecoverer có thể xử lý theo chính sách.

Hãy phân biệt lỗi dữ liệu riêng lẻ với sự cố schema/configuration của cả deployment; không retry vô hạn một payload không hợp lệ; bảo toàn raw bytes và metadata DLT; bảo đảm producer recovery hỗ trợ serializer phù hợp; và chỉ tiến offset sau khi recovery hoàn tất theo semantics đã chọn. Khi kết hợp contract testing, observability, DLT replay và idempotency, hệ thống có thể vừa tiếp tục xử lý record hợp lệ vừa giữ đầy đủ bằng chứng để sửa những record không deserialize được.
