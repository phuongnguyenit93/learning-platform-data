# Deserialize thất bại

Kafka lưu key và value dưới dạng byte. Consumer phải giải mã các byte đó bằng deserializer trước khi Spring Kafka có thể chuyển record cho `@KafkaListener`. Nếu deserializer không hiểu dữ liệu, record chưa đến được listener; vì vậy việc bắt exception trong method listener không xử lý được lỗi này.

Spring Kafka cung cấp `ErrorHandlingDeserializer` để bọc deserializer thực tế. Khi delegate thất bại, wrapper giữ lại raw bytes và exception trong record header, sau đó listener container có thể chuyển record lỗi đến `DefaultErrorHandler` hoặc recoverer như `DeadLetterPublishingRecoverer`. Cách làm này giúp consumer tiếp tục vận hành và giữ được dữ liệu gốc để điều tra hoặc phát lại.

## 1. Deserialize thất bại xảy ra ở đâu?

Luồng nhận record có các bước chính:

```mermaid
flowchart TD
    A[Kafka broker trả record bytes] --> B[Kafka Consumer.poll]
    B --> C[Key / Value Deserializer]
    C --> D{Deserialize thành công?}
    D -->|Có| E[ConsumerRecord đã giải mã]
    E --> F[Spring Message Converter]
    F --> G[@KafkaListener]
    D -->|Không, có ErrorHandlingDeserializer| H[Giữ raw bytes + DeserializationException header]
    H --> I[Listener container ErrorHandler]
    I --> J[Retry / Recoverer / DLT]
    D -->|Không có wrapper| K[Exception thoát khỏi poll]
    K --> L[Record chưa tới listener; container không có ConsumerRecord để recover]
```

Kafka gọi key/value deserializer trong quá trình `poll()`. Nếu delegate ném exception, Kafka chưa trả `ConsumerRecord` đã giải mã cho ứng dụng. Spring không thể gọi `@KafkaListener` với record đó và cũng không thể xử lý như một exception phát sinh bên trong listener.

`ErrorHandlingDeserializer` giải quyết ranh giới này bằng cách:

1. Gọi deserializer delegate để giải mã key hoặc value.
2. Nếu thành công, trả về object đã giải mã như bình thường.
3. Nếu thất bại, trả về `null` cho phần bị lỗi và thêm header chứa `DeserializationException`.
4. Header giữ cause và raw bytes để error handler/recoverer có thể xử lý record lỗi.
5. Với record listener, container nhận ra header lỗi và gọi container error handler; record không được chuyển vào method listener.

Có thể xảy ra lỗi ở key, value hoặc cả hai. Cần kiểm tra đúng header tương ứng thay vì chỉ nhìn `record.value() == null`.

## 2. Phân biệt các loại lỗi gần nhau

Không phải mọi lỗi liên quan dữ liệu đều là deserialization error. Xác định đúng tầng giúp chọn đúng cách sửa.

| Loại lỗi | Thời điểm xảy ra | Ví dụ | Nơi xử lý phù hợp |
|---|---|---|---|
| Key/value deserialization | Trong `Consumer.poll()` | JSON sai cú pháp, bytes không phải UTF-8, schema ID không hợp lệ. | `ErrorHandlingDeserializer`, container error handler, DLT. |
| JSON type resolution | Trong JSON deserializer | Type header trỏ tới class không tồn tại hoặc package chưa được trust. | Sửa type header/mapping/trusted packages; giữ raw bytes và recover nếu cần. |
| Message conversion | Sau khi `ConsumerRecord` đã được deserialize | Converter không chuyển payload sang tham số listener. | Message converter và container error handler. |
| Method argument resolution | Khi Spring chuẩn bị gọi listener | Chữ ký method hoặc annotation/header không tương thích. | Sửa method signature hoặc argument resolver. |
| Business processing | Bên trong `@KafkaListener` | Database timeout, validation nghiệp vụ, service exception. | `DefaultErrorHandler`, retry, recoverer hoặc DLT theo chính sách nghiệp vụ. |

Spring Kafka `DefaultErrorHandler` mặc định xem `DeserializationException`, `MessageConversionException`, `ConversionException`, `MethodArgumentResolutionException`, `NoSuchMethodException` và `ClassCastException` là fatal. Các exception này được chuyển tới recoverer ngay lần thất bại đầu tiên thay vì retry nhiều lần, vì phát lại cùng dữ liệu thường không tự sửa được lỗi định dạng hoặc kiểu.

## 3. Cấu hình ErrorHandlingDeserializer trong Spring Boot

Ví dụ ứng dụng nhận JSON `OrderEvent`, dùng String key và JSON value:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-projection
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.orders.OrderEvent
        spring.json.trusted.packages: com.example.orders
```

Ở đây:

- `key-deserializer` và `value-deserializer` là wrapper `ErrorHandlingDeserializer`.
- `spring.deserializer.key.delegate.class` chỉ định deserializer thật cho key.
- `spring.deserializer.value.delegate.class` chỉ định deserializer thật cho value.
- `spring.json.value.default.type` là kiểu mặc định khi JSON không có type header phù hợp.
- `spring.json.trusted.packages` giới hạn package được phép dùng khi type mapper phân giải class.

Nếu key luôn là String và không cần chuyển lỗi key thành DLT, có thể dùng trực tiếp `StringDeserializer` cho key và chỉ bọc value. Nếu producer bên ngoài gửi key có thể sai định dạng, hãy bọc cả key như ví dụ.

Tên property `spring.deserializer.*.delegate.class` và `spring.json.*` là Kafka/Spring Kafka client property; khi đặt trong `spring.kafka.consumer.properties`, hãy giữ đúng tên đầy đủ. Không lồng `spring.json` thành object tùy ý hoặc đổi dấu chấm thành tên property khác.

### Khi producer gửi type header

`JsonSerializer` của Spring Kafka mặc định có thể ghi type information vào Kafka headers. Nếu consumer nhận event từ một producer Spring tương thích, deserializer có thể dùng type header để chọn class. Khi đó, cần thống nhất type mapping và package được trust ở cả hai phía.

Nếu producer ngoài Spring không gửi type header, cấu hình `spring.json.value.default.type` như ví dụ để chọn class đích. Có thể đặt `spring.json.use.type.headers: false` khi muốn luôn dùng kiểu được cấu hình thay vì type header đến từ producer; chỉ làm vậy khi topic có một hợp đồng payload rõ ràng.

## 4. Dùng ErrorHandlingDeserializer bằng Java configuration

Nếu muốn cấu hình trực tiếp deserializer, có thể tạo wrapper với delegate:

```java
import org.apache.kafka.common.serialization.StringDeserializer;
import org.springframework.kafka.support.serializer.ErrorHandlingDeserializer;
import org.springframework.kafka.support.serializer.JsonDeserializer;

var keyDeserializer = new ErrorHandlingDeserializer<>(
        new StringDeserializer());

var valueDelegate = new JsonDeserializer<>(OrderEvent.class);
valueDelegate.addTrustedPackages("com.example.orders");

var valueDeserializer = new ErrorHandlingDeserializer<>(valueDelegate);
```

Truyền các instance này vào `DefaultKafkaConsumerFactory`:

```java
import java.util.Map;

import org.springframework.kafka.core.DefaultKafkaConsumerFactory;

var consumerFactory = new DefaultKafkaConsumerFactory<String, OrderEvent>(
        consumerProperties,
        keyDeserializer,
        valueDeserializer);
```

Khi đã cung cấp deserializer instance cho factory, cấu hình class qua consumer properties không thay thế instance đã truyền vào. Hãy cấu hình delegate trực tiếp hoặc để factory tạo delegate từ property; không cấu hình hai cách rồi giả định chúng được gộp tự động.

## 5. Cấu hình DefaultErrorHandler và DeadLetterPublishingRecoverer

Với record listener, container nhận ra deserialization exception header và gọi `CommonErrorHandler`. Có thể dùng `DefaultErrorHandler` cùng `DeadLetterPublishingRecoverer` để publish record lỗi sang DLT:

```java
import org.apache.kafka.common.TopicPartition;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.util.backoff.FixedBackOff;

@Bean
DefaultErrorHandler kafkaErrorHandler(KafkaTemplate<Object, Object> dltTemplate) {
    var recoverer = new DeadLetterPublishingRecoverer(
            dltTemplate,
            (record, exception) -> new TopicPartition(
                    record.topic() + "-dlt", record.partition()));

    // Lỗi retryable: tối đa 2 lần retry, cách nhau 1 giây.
    // DeserializationException mặc định là fatal nên được recover ngay.
    return new DefaultErrorHandler(recoverer, new FixedBackOff(1_000L, 2L));
}
```

Với `FixedBackOff(1_000L, 2L)`, record có tối đa ba delivery attempt: lần đầu và hai lần retry. Tuy nhiên, `DeserializationException` nằm trong nhóm fatal mặc định của `DefaultErrorHandler`, nên recoverer được gọi ngay lần đầu; retry backoff chủ yếu áp dụng cho các exception retryable khác.

Khi dùng Spring Boot, khai báo `DefaultErrorHandler` như một bean thường được Boot gắn vào listener container factory auto-configured. Nếu tự tạo factory, gọi `factory.setCommonErrorHandler(kafkaErrorHandler)` để bảo đảm listener sử dụng đúng handler.

Topic DLT trong ví dụ dùng cùng partition index với topic nguồn; hãy tạo DLT có ít nhất số partition tương ứng và kiểm tra quyền ghi của principal recoverer. `DeadLetterPublishingRecoverer` thêm các header mô tả exception và vị trí record nguồn. Header exception riêng do `ErrorHandlingDeserializer` tạo không phải nơi lưu trữ duy nhất của dữ liệu gốc; recoverer khôi phục raw bytes vào key/value để DLT có thể giữ payload ban đầu.

### Vì sao DLT producer cần hỗ trợ byte[]?

Khi deserialize thất bại, `DeadLetterPublishingRecoverer` khôi phục raw value dưới dạng `byte[]` để DLT giữ được dữ liệu gốc. Nếu `KafkaTemplate` chỉ có `JsonSerializer<OrderEvent>`, việc publish record lỗi có thể thất bại vì serializer nhận byte array thay vì `OrderEvent`.

Một producer dùng cho DLT nên hỗ trợ cả raw bytes và object bình thường. Ví dụ dùng `DelegatingByTypeSerializer`:

```java
import java.util.Map;

import org.apache.kafka.common.serialization.ByteArraySerializer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.support.serializer.DelegatingByTypeSerializer;
import org.springframework.kafka.support.serializer.JsonSerializer;

@Bean
ProducerFactory<Object, Object> dltProducerFactory(
        Map<String, Object> producerProperties) {

    var keySerializer = new DelegatingByTypeSerializer(Map.of(
            byte[].class, new ByteArraySerializer(),
            String.class, new StringSerializer()));

    var valueSerializer = new DelegatingByTypeSerializer(Map.of(
            byte[].class, new ByteArraySerializer(),
            OrderEvent.class, new JsonSerializer<>()));

    return new DefaultKafkaProducerFactory<>(
            producerProperties, keySerializer, valueSerializer);
}

@Bean
KafkaTemplate<Object, Object> dltTemplate(
        ProducerFactory<Object, Object> dltProducerFactory) {
    return new KafkaTemplate<>(dltProducerFactory);
}
```

Map serializer phải bao phủ mọi kiểu key/value có thể xuất hiện trong DLT. Ví dụ trên hỗ trợ String key, raw byte[] key, `OrderEvent` và raw byte[] value. Nếu topic có nhiều loại event, bổ sung serializer tương ứng hoặc dùng một wire format thống nhất. Không ép raw bytes qua JSON serializer vì sẽ làm thay đổi hoặc làm hỏng payload gốc.

## 6. Đọc exception header và raw bytes

`ErrorHandlingDeserializer` sử dụng header riêng cho key và value. Có thể kiểm tra header trên `ConsumerRecord` khi cần ghi log hoặc xử lý thủ công:

```java
import org.springframework.kafka.support.serializer.SerializationUtils;

var keyFailure = record.headers().lastHeader(
        SerializationUtils.KEY_DESERIALIZER_EXCEPTION_HEADER);

var valueFailure = record.headers().lastHeader(
        SerializationUtils.VALUE_DESERIALIZER_EXCEPTION_HEADER);
```

Các header chứa exception đã serialize theo cơ chế của Spring Kafka. Để lấy exception, dùng tiện ích `SerializationUtils` thay vì tự parse byte array:

```java
var exception = SerializationUtils.getExceptionFromHeader(
        record,
        SerializationUtils.VALUE_DESERIALIZER_EXCEPTION_HEADER,
        logAccessor);
```

`logAccessor` ở ví dụ là `org.springframework.core.log.LogAccessor` của ứng dụng. Header exception có thể chứa stack/cause và raw bytes; không ghi toàn bộ header hoặc payload nhạy cảm vào log production. Hãy log topic, partition, offset, exception class và correlation/event ID nếu có.

## 7. Phân biệt null do tombstone với null do deserialize thất bại

Với compacted topic, Kafka cho phép gửi tombstone: record có key nhưng value là `null`. Đây là dữ liệu hợp lệ để biểu thị xóa key trong log compaction.

`ErrorHandlingDeserializer` cũng trả `null` cho phần payload deserialize lỗi. Vì vậy, không được kết luận mọi record có `value() == null` đều là poison record.

| Trường hợp | `record.value()` | Deserialization exception header | Ý nghĩa |
|---|---|---|---|
| Tombstone hợp lệ | `null` | Không có | Event xóa key; xử lý theo semantics compacted topic. |
| JSON value lỗi | `null` | Có value exception header | Deserialize value thất bại. |
| Key lỗi | Có thể vẫn có value hợp lệ | Có key exception header | Không thể giải mã key; cần giữ raw key để điều tra/recover. |
| Listener chủ động nhận nullable payload | `null` | Không có | Kiểm tra hợp đồng topic và converter trước khi xử lý. |

Khi dùng `ErrorHandlingDeserializer`, container record listener kiểm tra exception header. Nếu tự viết batch listener hoặc logic kiểm tra record, hãy kiểm tra header tương ứng chứ không chỉ dựa vào null.

## 8. Deserialize JSON thất bại vì type header hoặc package

Một số lỗi thường không nằm ở JSON syntax mà ở cách chọn Java type:

### Type header chứa class name không tồn tại

Producer Spring có thể ghi tên class vào header. Nếu consumer không có class đó, đổi package hoặc dùng DTO khác, type resolution có thể thất bại.

Giải pháp:

- Dùng `spring.json.type.mapping` để ánh xạ token ổn định sang class ở mỗi service.
- Hoặc tắt sử dụng type header và cấu hình default type khi topic chỉ chứa một kiểu event.
- Duy trì backward compatibility khi đổi package/class; tên class Java không nên trở thành hợp đồng wire format dài hạn.

Ví dụ mapping type:

```yaml
spring:
  kafka:
    producer:
      properties:
        spring.json.type.mapping: order-created:com.example.producer.OrderCreatedEvent
    consumer:
      properties:
        spring.json.type.mapping: order-created:com.example.consumer.OrderCreatedEvent
```

Hai service dùng token `order-created` giống nhau nhưng có thể dùng class Java riêng, miễn là payload tương thích. Khi có nhiều event type, khai báo từng token/class mapping và kiểm thử tương thích giữa producer và consumer.

### Trusted packages bị từ chối

`JsonDeserializer` kiểm tra package được phép trước khi tạo object từ type header. Mặc định chỉ trust các package Java cơ bản như `java.util` và `java.lang`; package event của ứng dụng cần được khai báo rõ:

```yaml
spring:
  kafka:
    consumer:
      properties:
        spring.json.trusted.packages: com.example.orders,com.example.shared.events
```

Không đặt `*` trong production chỉ để hết lỗi. Wildcard cho phép deserialize class từ mọi package được type header chỉ định và mở rộng bề mặt tấn công. Tốt hơn là giới hạn package hoặc dùng type mapping/target type cố định.

## 9. Deserialize JSON thất bại vì payload không tương thích

Các nguyên nhân thường gặp:

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `Unexpected character` hoặc `JsonParseException` | Producer gửi JSON sai cú pháp, cắt cụt hoặc gửi text không phải JSON. | Kiểm tra raw bytes, encoding và producer serializer. |
| `MismatchedInputException` | JSON có shape khác DTO đích, ví dụ object thay vì array hoặc string thay vì number. | Đối chiếu JSON contract với DTO; version hóa event khi thay đổi cấu trúc. |
| `UnrecognizedPropertyException` | JSON có field mà mapper đang cấu hình không chấp nhận. | Kiểm tra ObjectMapper; quyết định rõ chính sách unknown fields và compatibility. |
| `InvalidDefinitionException` | DTO không có constructor/creator phù hợp, module hoặc serializer cần thiết chưa được đăng ký. | Kiểm tra DTO, Jackson module và ObjectMapper. |
| Lỗi parse ngày giờ | Producer và consumer không thống nhất định dạng hoặc timezone. | Dùng ISO-8601, kiểu thời gian phù hợp và Jackson Java Time module. |
| Value bị đọc thành `String` hoặc `byte[]` | Consumer dùng sai deserializer hoặc producer dùng wire format khác. | Đồng bộ serializer/deserializer hoặc dùng converter theo đúng hợp đồng. |
| Type header không tương thích | Producer gửi class token/FQCN mà consumer không biết. | Dùng type mapping hoặc cấu hình default target type. |

Spring Kafka từ 2.3 cấu hình JSON-aware components với enhanced ObjectMapper có một số thiết lập thân thiện cho tương thích, bao gồm tắt `FAIL_ON_UNKNOWN_PROPERTIES` mặc định. Nếu ứng dụng tự cung cấp ObjectMapper, hành vi có thể khác; hãy kiểm tra cấu hình thật thay vì mặc định giả định mọi unknown field đều gây lỗi.

## 10. Schema Registry và Avro/Protobuf

Với Avro, Protobuf hoặc JSON Schema, deserialize có thể thất bại do schema ID, subject, version hoặc kết nối Schema Registry:

- Payload không có schema ID đúng wire format.
- Producer và consumer dùng serializer/deserializer khác nhau.
- Subject strategy khiến schema được đăng ký dưới subject khác dự kiến.
- Schema mới không tương thích với reader schema hoặc generated class.
- Schema Registry không truy cập được, timeout hoặc trả lỗi authentication/authorization.
- Consumer chưa có dependency/runtime tương ứng với schema format.

Hướng điều tra:

1. Giữ raw bytes và kiểm tra wire format trước khi thay đổi code.
2. Xác định schema ID/subject/version mà producer đã ghi.
3. Kiểm tra subject strategy và compatibility mode của registry.
4. Kiểm tra generated class/runtime library của consumer.
5. Phân biệt lỗi dữ liệu vĩnh viễn với lỗi kết nối Registry tạm thời.
6. Kiểm tra credential, TLS truststore, DNS và timeout khi deserializer gọi Registry.

Nếu Registry tạm thời không truy cập được, exception có thể được bọc trong `DeserializationException` và bị `DefaultErrorHandler` phân loại fatal mặc định. Chỉ cấu hình retry cho trường hợp đã xác nhận là lỗi hạ tầng tạm thời; dữ liệu sai schema hoặc schema ID không tồn tại sẽ không tự sửa sau vài lần retry.

## 11. Lỗi deserialize và retry: khi nào nên retry?

`DefaultErrorHandler` mặc định không retry `DeserializationException` mà chuyển ngay đến recoverer. Đây thường là lựa chọn hợp lý cho malformed JSON, type header sai, package không trust hoặc schema không tương thích: gửi lại cùng bytes thường cho cùng kết quả.

| Loại nguyên nhân | Retry có ích? | Hướng xử lý |
|---|---|---|
| JSON sai cú pháp hoặc payload bị cắt | Không | DLT, điều tra producer/raw bytes. |
| Class/type mapping sai | Không, trừ khi deployment/config sắp được sửa trong cửa sổ retry có chủ đích | DLT hoặc tạm dừng consumer để sửa config; replay sau khi sửa. |
| Trusted package thiếu | Thường không | Sửa allowlist hẹp và replay. |
| Schema không tương thích hoặc schema ID sai | Không | Sửa schema/producer contract, DLT và replay. |
| Schema Registry timeout/connection reset | Có thể | Phân loại cause cụ thể là retryable, dùng backoff hữu hạn và giám sát Registry. |
| Message conversion do DTO contract sai | Thường không | Sửa converter/DTO hoặc version event. |

Nếu muốn retry exception do Registry tạm thời, có thể thay đổi classification của `DefaultErrorHandler` bằng `addRetryableExceptions(...)` hoặc `setClassifications(...)`. Hãy kiểm tra cause chain và bảo đảm chỉ exception thật sự transient được retry; nếu đánh dấu mọi `DeserializationException` là retryable, poison record có thể giữ partition lại lâu dài.

Ví dụ minh họa chỉ khi đã có custom exception riêng đại diện cho lỗi Registry tạm thời:

```java
var handler = new DefaultErrorHandler(recoverer,
        new FixedBackOff(1_000L, 3L));

handler.addRetryableExceptions(SchemaRegistryUnavailableException.class);
```

Trong thực tế, deserializer phải chuyển lỗi Registry transient thành exception có kiểu/cause mà classifier nhận diện được. Không bọc mọi exception thành một custom retryable exception chung.

## 12. Dùng failedDeserializationFunction khi cần sentinel object

`ErrorHandlingDeserializer` hỗ trợ `failedDeserializationFunction`, nhận `FailedDeserializationInfo` và tạo một object thay thế cho listener. Cách này hữu ích khi ứng dụng muốn đưa lỗi vào một luồng xử lý riêng mà vẫn dùng cùng listener method.

```java
import java.util.function.Function;
import org.springframework.kafka.support.serializer.FailedDeserializationInfo;

public interface Thing {
}

public record BadThing(FailedDeserializationInfo failure) implements Thing {
}

public class FailedThingProvider implements Function<FailedDeserializationInfo, Thing> {

    @Override
    public Thing apply(FailedDeserializationInfo info) {
        return new BadThing(info);
    }
}
```

Gắn provider vào wrapper khi tự tạo deserializer:

```java
ErrorHandlingDeserializer<Thing> wrapper =
        new ErrorHandlingDeserializer<>(delegateDeserializer);
wrapper.setFailedDeserializationFunction(new FailedThingProvider());
```

`delegateDeserializer` ở đây là một `Deserializer<Thing>` đã được cấu hình cho wire format và target type thực tế của ứng dụng.

Đây là mẫu minh họa; kiểu sentinel phải phù hợp với model của ứng dụng. Listener cần nhận diện sentinel trước khi xử lý nghiệp vụ. Nếu listener coi sentinel như event bình thường, lỗi deserialize có thể bị biến thành dữ liệu nghiệp vụ giả. Với hầu hết consumer cần DLT, để container error handler xử lý record lỗi thường đơn giản và an toàn hơn.

## 13. Validator cho dữ liệu đã deserialize

Từ Spring Kafka 3.1, `ErrorHandlingDeserializer` có thể dùng `Validator`. Delegate deserialize thành công nhưng object không đạt validation thì wrapper vẫn tạo deserialization failure tương tự và giữ raw data để error handler xử lý.

```java
import org.springframework.kafka.support.serializer.ErrorHandlingDeserializer;
import org.springframework.validation.Validator;

var deserializer = new ErrorHandlingDeserializer<>(
        new JsonDeserializer<>(OrderEvent.class));
deserializer.setValidator(orderEventValidator);
```

Validation này phù hợp với điều kiện cấu trúc ở ranh giới deserialize, ví dụ field bắt buộc hoặc version payload. Quy tắc nghiệp vụ phụ thuộc database/trạng thái hiện tại vẫn nên nằm trong service layer và được xử lý theo retry policy nghiệp vụ. Không nhầm `Validator` của ErrorHandlingDeserializer với việc validate mọi side effect của listener.

## 14. Batch listener cần xử lý deserialize failure tường minh

Với record listener, container có thể phát hiện exception header và gọi error handler tự động. Với batch listener, ứng dụng cần kiểm tra header trong batch và xác định record lỗi bằng `BatchListenerFailedException`.

Ví dụ listener nhận `ConsumerRecord` để giữ metadata và kiểm tra header:

```java
import java.util.List;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.commons.logging.LogFactory;
import org.springframework.core.log.LogAccessor;
import org.springframework.kafka.listener.BatchListenerFailedException;
import org.springframework.kafka.support.serializer.SerializationUtils;
import org.springframework.kafka.support.serializer.DeserializationException;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrdersBatchListener {

    private final LogAccessor logAccessor =
            new LogAccessor(LogFactory.getLog(getClass()));

    @KafkaListener(topics = "orders.events", containerFactory = "batchFactory")
    public void listen(List<ConsumerRecord<String, OrderEvent>> records) {
        for (ConsumerRecord<String, OrderEvent> record : records) {
            DeserializationException failure = SerializationUtils.getExceptionFromHeader(
                    record, SerializationUtils.VALUE_DESERIALIZER_EXCEPTION_HEADER, logAccessor);
            if (failure == null) {
                failure = SerializationUtils.getExceptionFromHeader(
                        record, SerializationUtils.KEY_DESERIALIZER_EXCEPTION_HEADER, logAccessor);
            }

            if (failure != null) {
                throw new BatchListenerFailedException(
                        "Kafka record cannot be deserialized", failure, record);
            }

            process(record.value());
        }
    }

    private void process(OrderEvent event) {
        // Xử lý event hợp lệ.
    }
}
```

Trong batch, cần chỉ ra record lỗi để `DefaultErrorHandler` biết offset nào cần retry/recover. Nếu chỉ ném exception thông thường, fallback behavior có thể retry cả batch. Với DLT, cấu hình `DefaultErrorHandler` cùng `DeadLetterPublishingRecoverer`; `@RetryableTopic` không hỗ trợ batch listener.

Nếu listener nhận `List<OrderEvent>` thay vì `ConsumerRecord`, cần đọc danh sách `KafkaHeaders.BATCH_CONVERTED_HEADERS` tương ứng để kiểm tra deserialization exception theo index. Dùng `SerializationUtils.byteArrayToDeserializationException()` hoặc `SerializationUtils.getExceptionFromHeader()` thay vì tự deserialize header.

## 15. Chẩn đoán theo log, topic, partition và offset

Khi phát hiện lỗi, thu thập thông tin theo thứ tự:

1. **Xác định record:** topic, partition, offset, timestamp, key và consumer group.
2. **Xác định trường lỗi:** key hay value exception header.
3. **Đọc exception chain:** class, message và root cause của Jackson, schema registry hoặc custom deserializer.
4. **Giữ raw bytes:** xuất record lỗi sang DLT hoặc công cụ điều tra có thể lưu byte nguyên bản.
5. **Đối chiếu producer:** serializer, content type, schema ID, type headers và phiên bản event.
6. **Đối chiếu consumer:** delegate deserializer, target type, trusted packages, type mapping và ObjectMapper.
7. **Kiểm tra offset:** xác định record có bị retry tại cùng offset hay đã được recover/commit.
8. **Khắc phục và replay:** sửa nguyên nhân trước, sau đó replay theo phạm vi và tốc độ có kiểm soát.

Không log raw payload nếu nó chứa thông tin cá nhân, token hoặc dữ liệu nhạy cảm. Có thể log hex prefix hoặc kích thước bytes, checksum, event ID và vị trí Kafka để truy vết; lưu raw payload trong DLT có ACL/retention phù hợp.

## 16. Kiểm thử deserialization failure

Nên có test riêng cho từng tầng và từng dạng record lỗi.

| Kịch bản | Kết quả cần xác minh |
|---|---|
| JSON hợp lệ | Listener nhận đúng `OrderEvent`. |
| JSON malformed | Listener không được gọi; error handler nhận record có exception header. |
| Value deserialize thất bại | Raw value được giữ và DLT nhận đúng bytes gốc. |
| Key deserialize thất bại | Key failure header được nhận diện; raw key không bị mất. |
| Tombstone hợp lệ | `null` value không bị nhầm thành deserialize failure. |
| Type header không tồn tại | Lỗi type resolution được đưa tới error handler/DLT. |
| Trusted package bị từ chối | Consumer không tạo object; raw bytes còn trong DLT. |
| Schema Registry tạm thời không truy cập | Retry chỉ xảy ra nếu exception transient được phân loại retryable. |
| DLT nhận cả event bình thường và raw bytes | Serializer định tuyến đúng `OrderEvent` và `byte[]`. |
| Batch có một record lỗi | Batch handler xác định đúng record/index và xử lý offset theo policy. |

Ví dụ kiểm thử integration nên đọc DLT bằng `ByteArrayDeserializer` để so sánh payload gốc:

```java
import java.nio.charset.StandardCharsets;

byte[] original = "{not-valid-json".getBytes(StandardCharsets.UTF_8);
// Gửi raw bytes vào topic nguồn bằng producer test dùng ByteArraySerializer.
// Chờ DLT record xuất hiện bằng consumer dùng ByteArrayDeserializer.
assertThat(dltRecord.value()).isEqualTo(original);
```

Đây là assertion minh họa. Test hoàn chỉnh cần topic/group riêng, chờ DLT bằng polling có timeout hữu hạn và xác minh header exception, source topic, partition, offset. Không dùng `Thread.sleep` cố định để đoán record đã được recover.

## 17. Lỗi thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
|---|---|---|
| Listener không được gọi và consumer lặp lỗi poll | Dùng deserializer trực tiếp, không có `ErrorHandlingDeserializer`. | Bọc key/value deserializer bằng ErrorHandlingDeserializer. |
| `record.value()` null nhưng không có exception header | Có thể là tombstone hợp lệ hoặc null payload theo hợp đồng. | Kiểm tra header và semantics topic; không suy luận chỉ từ null. |
| DLT publish thất bại khi deserialize lỗi | DLT producer chỉ serialize DTO, không hỗ trợ raw `byte[]`. | Dùng `DelegatingByTypeSerializer` cho bytes và object. |
| Type header trỏ class không tồn tại | Producer và consumer lệch package/version. | Dùng type mapping ổn định hoặc target type cố định. |
| `The class ... is not in the trusted packages` | Package của event chưa được trust. | Thêm package cụ thể; tránh wildcard rộng. |
| JSON có field mới làm consumer lỗi | ObjectMapper custom bật strict unknown-property hoặc DTO không tương thích. | Kiểm tra ObjectMapper, compatibility và schema evolution. |
| Avro/Protobuf không tìm thấy schema | Schema ID, subject hoặc Registry connection không hợp lệ. | Kiểm tra wire format, subject strategy, schema version và registry. |
| Retry lặp lại cùng một payload sai | DeserializationException bị retry như lỗi tạm thời do classification tùy chỉnh. | Đưa lỗi dữ liệu về non-retryable; recover sang DLT. |
| Batch listener không chuyển đúng record lỗi sang DLT | Không kiểm tra exception header hoặc không ném `BatchListenerFailedException`. | Kiểm tra từng record/header và chỉ rõ failed record/index. |
| DLT có payload khác bytes gốc | Raw bytes bị serialize lại như JSON/string. | Publish raw byte[] bằng ByteArraySerializer. |

## 18. Checklist vận hành

- Key/value deserializer được bọc bằng `ErrorHandlingDeserializer` ở các luồng cần recover dữ liệu lỗi.
- Delegate deserializer và target type khớp với wire format của producer.
- Trusted packages được giới hạn theo package thực tế.
- Type headers và type mappings có hợp đồng rõ giữa producer/consumer.
- `DefaultErrorHandler` phân loại lỗi dữ liệu vĩnh viễn là non-retryable.
- DLT topic đã được tạo, đủ partition và có retention/ACL phù hợp.
- DLT producer hỗ trợ raw byte[] lẫn object bình thường.
- Batch listener kiểm tra deserialization exception headers theo từng record.
- Tombstone được phân biệt với lỗi deserialize bằng exception header.
- Log có topic/partition/offset và root cause nhưng không lộ payload nhạy cảm.
- Có test xác minh raw bytes tới DLT không bị thay đổi.
- Có quy trình sửa producer/schema rồi replay record đã recover.

## 19. Ghi nhớ

- Deserialize xảy ra trong `Consumer.poll()`, trước khi `@KafkaListener` nhận record.
- `ErrorHandlingDeserializer` bọc delegate, trả `null` cho phần lỗi và lưu `DeserializationException` cùng raw bytes trong header.
- Record listener được container chuyển tới error handler; listener không nhận record lỗi đó.
- `DefaultErrorHandler` mặc định xem `DeserializationException` là fatal và gọi recoverer ngay, không retry lặp dữ liệu sai.
- `DeadLetterPublishingRecoverer` có thể giữ raw bytes trong DLT; producer cần serializer hỗ trợ `byte[]` và object bình thường.
- JSON type header, trusted packages, type mapping, DTO và ObjectMapper là các điểm cần kiểm tra khi JSON deserialize lỗi.
- Schema Registry lỗi có thể là dữ liệu sai vĩnh viễn hoặc hạ tầng tạm thời; chỉ retry trường hợp transient đã được phân loại rõ.
- Batch listener phải kiểm tra exception headers và báo failed record/index bằng `BatchListenerFailedException`.
- `null` value không tự động là lỗi; tombstone hợp lệ không có deserialization exception header.
- Giữ raw bytes và metadata Kafka để điều tra, sửa nguyên nhân rồi replay an toàn.

Khi deserialize thất bại, mục tiêu đầu tiên là giữ lại record và xác định chính xác lỗi xảy ra ở key, value, type mapping, schema hay message conversion. `ErrorHandlingDeserializer` đưa lỗi xảy ra trước `poll()` vào luồng error handling của Spring Kafka; `DefaultErrorHandler` phân loại lỗi, còn `DeadLetterPublishingRecoverer` lưu record lỗi để điều tra. Khi DLT giữ được raw bytes và hệ thống phân biệt rõ lỗi vĩnh viễn với lỗi hạ tầng tạm thời, consumer có thể tiếp tục xử lý mà không làm mất bằng chứng của event lỗi.

## Tài liệu tham khảo

- [Spring for Apache Kafka — Serialization, Deserialization, and Message Conversion](https://docs.spring.io/spring-kafka/reference/kafka/serdes.html)
- [Spring for Apache Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring Kafka — ErrorHandlingDeserializer API](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/support/serializer/ErrorHandlingDeserializer.html)
- [Spring Kafka — DeserializationException API](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/support/serializer/DeserializationException.html)
- [Spring Kafka — DeadLetterPublishingRecoverer API](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/listener/DeadLetterPublishingRecoverer.html)
