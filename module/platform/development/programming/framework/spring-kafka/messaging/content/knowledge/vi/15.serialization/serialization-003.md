# JsonSerializer và JsonDeserializer

Kafka lưu record dưới dạng byte array. Producer phải chuyển key và value từ kiểu Java thành byte trước khi gửi; consumer phải chuyển byte nhận được về kiểu dữ liệu mà ứng dụng có thể sử dụng. Quá trình này gọi là serialization và deserialization.

Trong Spring Kafka, `JsonSerializer` và `JsonDeserializer` giúp trao đổi event dưới dạng JSON mà không phải tự gọi `ObjectMapper` ở mỗi service. Producer có thể gửi một DTO Java, còn consumer nhận lại DTO tương ứng. Để hai phía hiểu cùng một hợp đồng dữ liệu, cần cấu hình serializer/deserializer nhất quán, quản lý type header có chủ đích và kiểm soát các package được phép deserialize.

## 1. Serialization và deserialization trong Kafka

Kafka broker không hiểu object Java. Broker nhận key/value dưới dạng byte và lưu chúng vào partition log. Việc chuyển đổi diễn ra ở phía producer và consumer:

```text
Producer application
  OrderCreatedEvent (Java object)
           |
           v
     JsonSerializer
           |
           v
      JSON bytes
           |
           v
       Kafka broker
           |
           v
      JSON bytes
           |
           v
    JsonDeserializer
           |
           v
  OrderCreatedEvent (Java object)
           |
           v
     Consumer listener
```

`JsonSerializer` dùng Jackson để chuyển object thành JSON. `JsonDeserializer` dùng Jackson để đọc JSON và tạo object Java. Kafka chỉ vận chuyển byte; broker không chuyển JSON thành DTO và cũng không kiểm tra cấu trúc JSON theo class Java của ứng dụng.

Ví dụ event:

```java
package com.example.messaging.event;

import java.math.BigDecimal;
import java.time.Instant;

public record OrderCreatedEvent(
        String eventId,
        String orderId,
        BigDecimal total,
        Instant occurredAt) {
}
```

Record này là hợp đồng payload giữa producer và consumer. Hai service cần thống nhất tên trường, kiểu dữ liệu, ý nghĩa và quy tắc thay đổi schema.

## 2. Cấu hình JsonSerializer và JsonDeserializer bằng Spring Boot

Với Spring Boot, cấu hình serializer/deserializer trong `application.yml`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
    consumer:
      group-id: order-projection
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        "[spring.json.trusted.packages]": com.example.messaging.event
```

Producer dùng `StringSerializer` cho key và `JsonSerializer` cho value. Consumer dùng `StringDeserializer` cho key và `JsonDeserializer` cho value. `trusted.packages` giới hạn các package mà deserializer được phép khởi tạo kiểu theo type header.

Sau khi cấu hình, có thể inject template có kiểu generic tương ứng:

```java
import com.example.messaging.event.OrderCreatedEvent;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderCreatedEvent event) {
        kafkaTemplate.send("orders.created", event.orderId(), event);
    }
}
```

Listener nhận DTO đã deserialize:

```java
import com.example.messaging.event.OrderCreatedEvent;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderProjectionListener {

    @KafkaListener(topics = "orders.created", groupId = "order-projection")
    public void onMessage(OrderCreatedEvent event) {
        // Cập nhật read model từ event.
    }
}
```

`KafkaTemplate<String, OrderCreatedEvent>` và listener DTO giúp mã nghiệp vụ làm việc trực tiếp với object. Kiểu generic không tự cấu hình serializer; kiểu key/value trong code phải khớp với serializer/deserializer được cấu hình cho producer và consumer factory.

## 3. Type headers trong JSON message

Mặc định, Spring Kafka `JsonSerializer` thêm type information vào Kafka headers. Header này cho biết class Java mà producer đã serialize, ví dụ `com.example.messaging.event.OrderCreatedEvent`. `JsonDeserializer` có thể đọc type header để xác định class cần tạo.

Luồng mặc định:

```text
Producer
  Java DTO
     |
     v
  JsonSerializer
     |------------------------------|
     v                              v
  JSON value                 Type information header
     |                              |
     +---------------+--------------+
                     v
                  Kafka
                     |
                     v
              JsonDeserializer
                     |
          đọc type header để chọn class
                     |
                     v
                 Java DTO
```

Type header tiện lợi khi nhiều loại event dùng chung topic hoặc consumer cần phân biệt kiểu payload. Tuy nhiên, header mặc định có thể chứa tên class và package của producer. Điều này tạo phụ thuộc giữa các service: nếu producer đổi package hoặc tên class, consumer có thể không còn resolve được kiểu đó.

Với các service độc lập, không nên mặc định xem tên class Java nội bộ là hợp đồng tích hợp ổn định. Có thể dùng type mapping để ánh xạ token ngắn sang class cục bộ, hoặc tắt type headers và khai báo kiểu đích cố định ở consumer.

## 4. Tắt type headers và khai báo kiểu mặc định

Nếu một topic chỉ chứa một loại event, consumer có thể dùng default type thay vì phụ thuộc tên class do producer gửi trong header.

```yaml
spring:
  kafka:
    producer:
      properties:
        "[spring.json.add.type.headers]": false
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        "[spring.json.use.type.headers]": false
        "[spring.json.value.default.type]": com.example.messaging.event.OrderCreatedEvent
        "[spring.json.trusted.packages]": com.example.messaging.event
```

Ở cấu hình này:

- `spring.json.add.type.headers=false` yêu cầu serializer không thêm type information header.
- `spring.json.use.type.headers=false` yêu cầu deserializer không dùng type header để chọn class.
- `spring.json.value.default.type` chỉ định class Java dùng để deserialize value.
- `spring.json.trusted.packages` xác định package được phép khi deserializer xử lý kiểu Java.

Giải pháp này phù hợp khi topic có một schema/event type rõ ràng và consumer biết trước DTO cần nhận. Nếu một topic chứa nhiều loại event, một default type duy nhất sẽ không đủ; hãy dùng type mapping, một envelope có trường `eventType`, hoặc thiết kế topic/schema phù hợp.

## 5. Dùng type mapping để giảm phụ thuộc tên class

Spring Kafka hỗ trợ type mapping: producer gửi một token thay cho tên class đầy đủ; consumer ánh xạ token đó sang class mà chính nó sử dụng. Cách này giúp producer và consumer có thể đặt DTO ở package khác nhau.

Ví dụ producer:

```yaml
spring:
  kafka:
    producer:
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        "[spring.json.type.mapping]": orderCreated:com.example.producer.event.OrderCreatedEvent
```

Consumer:

```yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        "[spring.json.type.mapping]": orderCreated:com.example.consumer.contract.OrderCreated
        "[spring.json.trusted.packages]": com.example.consumer.contract
```

Producer phát token `orderCreated` trong type header. Consumer nhận token đó và ánh xạ sang `com.example.consumer.contract.OrderCreated`. Hai class không cần cùng package hoặc cùng tên, nhưng cấu trúc JSON và ý nghĩa các trường vẫn phải tương thích.

Khi có nhiều loại event, có thể khai báo nhiều cặp token/class trong property `spring.json.type.mapping`, phân tách bằng dấu phẩy. Mỗi token nên ổn định, dễ hiểu và được quản lý như một phần của hợp đồng dữ liệu.

Type mapping chỉ giải quyết việc ánh xạ type identifier sang class. Nó không tự chuyển đổi schema bất kỳ, không đổi tên field và không bảo đảm tương thích giữa hai cấu trúc JSON khác nhau.

## 6. Trusted packages và an toàn khi deserialize

Khi `JsonDeserializer` dùng type header để chọn class, nó cần xác định package đó có được tin cậy hay không. Cấu hình `spring.json.trusted.packages` cho phép giới hạn các package hợp lệ.

Ví dụ:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[spring.json.trusted.packages]": com.example.messaging.event,com.example.shared.contract
```

Chỉ thêm package chứa DTO mà ứng dụng chủ động kiểm soát. Không dùng wildcard `*` một cách tùy tiện để làm mất lỗi trusted package. Với topic nhận dữ liệu từ hệ thống bên ngoài, cần đặc biệt thận trọng vì type metadata và payload đều đến từ nguồn khác.

Trusted packages không thay thế xác thực producer, Kafka ACL hoặc kiểm tra dữ liệu nghiệp vụ. Sau deserialize, ứng dụng vẫn cần validate trường bắt buộc, giới hạn kích thước, miền giá trị và quyền thực hiện thao tác.

## 7. Type header được giữ hay xóa sau deserialize?

Theo cấu hình mặc định của Spring Kafka, `JsonDeserializer` loại bỏ type information headers sau khi deserialize. Điều này tránh để metadata nội bộ của producer tự động lan sang lần publish tiếp theo nếu ứng dụng nhận rồi gửi lại record.

Có thể điều khiển hành vi bằng property:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[spring.json.remove.type.headers]": false
```

Chỉ giữ type headers nếu ứng dụng thực sự cần chúng cho bước xử lý tiếp theo. Nếu republish event, hãy quyết định rõ type metadata nào thuộc hợp đồng công khai; không chuyển tiếp mù quáng header nội bộ hoặc header có thể chứa thông tin không phù hợp.

## 8. Cấu hình bằng Java thay cho application.yml

Khi cần tạo serializer/deserializer theo cấu hình riêng, có thể khai báo trực tiếp trong Java:

```java
import java.util.HashMap;
import java.util.Map;

import com.example.messaging.event.OrderCreatedEvent;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.DefaultKafkaConsumerFactory;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.support.serializer.JsonSerializer;
import org.springframework.kafka.support.serializer.JsonDeserializer;

@Configuration
public class JsonKafkaConfiguration {

    @Bean
    public ProducerFactory<String, OrderCreatedEvent> orderProducerFactory() {
        Map<String, Object> properties = new HashMap<>();
        properties.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
                "localhost:9092");
        return new DefaultKafkaProducerFactory<>(
                properties,
                new StringSerializer(),
                new JsonSerializer<>());
    }

    @Bean
    public ConsumerFactory<String, OrderCreatedEvent> orderConsumerFactory() {
        Map<String, Object> properties = new HashMap<>();
        properties.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
                "localhost:9092");
        properties.put(ConsumerConfig.GROUP_ID_CONFIG,
                "order-projection");

        JsonDeserializer<OrderCreatedEvent> valueDeserializer =
                new JsonDeserializer<>(OrderCreatedEvent.class);
        valueDeserializer.addTrustedPackages(
                "com.example.messaging.event");

        return new DefaultKafkaConsumerFactory<>(
                properties,
                new StringDeserializer(),
                valueDeserializer);
    }
}
```

Đoạn code minh họa việc tạo serializer/deserializer tường minh, không phải cấu hình hoàn chỉnh cho production. Trong ứng dụng thực tế, bổ sung các thuộc tính bảo mật, client ID, bean template/listener factory và cấu hình môi trường phù hợp.

Khi cấu hình serializer/deserializer bằng constructor hoặc setter, tránh đồng thời cấu hình lại cùng đối tượng bằng property map nếu API của phiên bản Spring Kafka đang dùng không cho phép trộn hai cách. Chọn một cách cấu hình nhất quán để tránh giá trị bị ghi đè hoặc lỗi khởi tạo.

## 9. Lỗi thường gặp khi serialize và deserialize

| Lỗi | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `SerializationException` khi gửi | Value không serialize được hoặc kiểu dữ liệu không phù hợp | Kiểm tra DTO, Jackson module và serializer đã cấu hình |
| `DeserializationException` khi nhận | JSON sai định dạng, field không tương thích hoặc class không resolve được | Kiểm tra payload, type header, default type và DTO |
| `ClassNotFoundException` | Type header chứa class name không tồn tại ở consumer | Dùng type mapping hoặc default type |
| Lỗi trusted package | Package của type header chưa được cho phép | Chỉ thêm package DTO đáng tin cậy vào allowlist |
| Producer gửi được nhưng consumer không đọc được DTO | Serializer và deserializer không thống nhất hoặc type mapping khác token | Đồng bộ cấu hình và hợp đồng JSON |
| Field mới làm consumer cũ lỗi | Schema thay đổi không tương thích | Dùng field optional/default, versioning và kiểm thử compatibility |
| Consumer nhận `null` | Record có value null, thường gặp với tombstone trong compacted topic | Xử lý null rõ ràng và phân biệt tombstone với payload JSON |

## 10. Xử lý lỗi deserialize trước khi listener được gọi

Deserialization diễn ra trước khi phương thức `@KafkaListener` nhận được object. Nếu JSON lỗi hoặc type không hợp lệ, listener có thể không được gọi; exception phát sinh trong consumer poll/adapter trước khi đi vào code nghiệp vụ.

Spring Kafka cung cấp `ErrorHandlingDeserializer` để bọc deserializer thực tế và chuyển lỗi deserialize thành thông tin lỗi mà container/error handler có thể xử lý. Ví dụ:

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.key.delegate.class]": org.apache.kafka.common.serialization.StringDeserializer
        "[spring.deserializer.value.delegate.class]": org.springframework.kafka.support.serializer.JsonDeserializer
        "[spring.json.value.default.type]": com.example.messaging.event.OrderCreatedEvent
        "[spring.json.trusted.packages]": com.example.messaging.event
```

Với cấu hình này, `ErrorHandlingDeserializer` ủy quyền phần key cho `StringDeserializer` và phần value cho `JsonDeserializer`. Khi deserialize lỗi, ứng dụng cần cấu hình error handler/recoverer phù hợp, chẳng hạn chuyển record lỗi sang DLT. Hãy kiểm thử cả lỗi key lẫn lỗi value vì chúng có thể được xử lý khác nhau.

Không nên bắt lỗi deserialize rồi thay payload lỗi bằng object rỗng mà không ghi nhận nguyên nhân. Điều đó có thể biến dữ liệu hỏng thành event có vẻ hợp lệ và làm sai trạng thái nghiệp vụ.

## 11. Thiết kế JSON event để tương thích giữa các service

JSON giúp các service không phụ thuộc vào định dạng byte riêng của Java, nhưng không tự bảo đảm schema compatibility. Cần thiết kế event như một hợp đồng công khai:

- Dùng tên field ổn định và có ý nghĩa nghiệp vụ.
- Ưu tiên thêm field mới theo cách consumer cũ có thể bỏ qua hoặc dùng giá trị mặc định.
- Tránh đổi kiểu dữ liệu hoặc đổi nghĩa field đang được sử dụng.
- Dùng `eventId`, `eventType`, `occurredAt` và aggregate ID khi cần truy vết.
- Không serialize trực tiếp JPA entity hoặc object nội bộ có quan hệ lazy/circular.
- Quản lý version event khi thay đổi lớn về cấu trúc.

Ví dụ một envelope:

```json
{
  "eventId": "evt-8f4c2a",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "occurredAt": "2026-11-17T03:00:00Z",
  "aggregateId": "ORD-1042",
  "data": {
    "total": 125000.00,
    "currency": "VND"
  }
}
```

Envelope làm rõ metadata và payload nghiệp vụ. Với hệ thống có nhiều ngôn ngữ lập trình hoặc yêu cầu quản lý schema nghiêm ngặt, cân nhắc Avro/Protobuf cùng schema registry thay vì chỉ dựa vào class Java và Jackson type headers.

## 12. Kiểm thử JsonSerializer và JsonDeserializer

Kiểm thử nên xác minh cả cấu trúc JSON và object sau deserialize. Ví dụ unit test dùng hai thành phần trực tiếp:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.Instant;

import com.example.messaging.event.OrderCreatedEvent;
import org.apache.kafka.common.header.internals.RecordHeaders;
import org.junit.jupiter.api.Test;
import org.springframework.kafka.support.serializer.JsonSerializer;
import org.springframework.kafka.support.serializer.JsonDeserializer;

class OrderJsonSerializationTest {

    @Test
    void serializesAndDeserializesOrderEvent() {
        OrderCreatedEvent original = new OrderCreatedEvent(
                "evt-1",
                "ORD-42",
                new BigDecimal("125000.00"),
                Instant.parse("2026-11-17T03:00:00Z"));

        JsonSerializer<OrderCreatedEvent> serializer =
                new JsonSerializer<>();
        byte[] bytes = serializer.serialize("orders.created", original);

        JsonDeserializer<OrderCreatedEvent> deserializer =
                new JsonDeserializer<>(OrderCreatedEvent.class);
        deserializer.addTrustedPackages("com.example.messaging.event");
        OrderCreatedEvent restored = deserializer.deserialize(
                "orders.created", new RecordHeaders(), bytes);

        assertThat(restored).isEqualTo(original);
    }
}
```

Vì ví dụ gọi overload serialize không truyền headers, deserializer dùng `OrderCreatedEvent.class` làm kiểu đích cố định. Nếu kiểm thử luồng có type header, hãy truyền cùng headers mà producer đã tạo để xác minh cả type mapping. Trong integration test, nên dùng broker kiểm thử và xác minh record đi qua đúng producer/consumer factory của ứng dụng.

Các trường hợp nên kiểm thử:

1. DTO hợp lệ được serialize thành JSON và deserialize đúng giá trị.
2. Producer và consumer dùng type mapping token tương thích.
3. Consumer hoạt động khi type headers bị tắt và default type được khai báo.
4. JSON sai định dạng được chuyển qua `ErrorHandlingDeserializer` và error handler.
5. Payload có field mới hoặc thiếu field optional được xử lý theo chính sách schema.
6. Tombstone/null value được xử lý rõ ràng.

## 13. Khi nào dùng JSON và khi nào chọn định dạng khác?

| Định dạng | Điểm mạnh | Cân nhắc |
| --- | --- | --- |
| JSON với `JsonSerializer`/`JsonDeserializer` | Dễ đọc, dễ debug, tích hợp Jackson và DTO Java | Payload có thể lớn hơn nhị phân; cần quản lý schema và type metadata |
| String/byte array | Đơn giản, kiểm soát hoàn toàn format | Ứng dụng tự parse và validate |
| Avro | Schema rõ, hỗ trợ evolution và biểu diễn nhị phân gọn | Thường cần schema registry và quy trình quản lý schema |
| Protobuf | Hợp đồng message rõ, hiệu quả và đa ngôn ngữ | Cần quản lý `.proto`, generated code và compatibility |

JSON phù hợp cho nhiều hệ thống Spring cần bắt đầu nhanh và ưu tiên khả năng đọc. Khi số lượng service, ngôn ngữ hoặc yêu cầu schema governance tăng lên, định dạng có schema như Avro hoặc Protobuf có thể phù hợp hơn.

## 14. Kết luận

`JsonSerializer` chuyển object Java thành JSON bytes khi producer gửi record; `JsonDeserializer` chuyển JSON bytes thành DTO khi consumer nhận record. Spring Kafka có thể truyền type information qua Kafka headers, dùng default type cho topic có một kiểu payload hoặc dùng type mapping để tránh phụ thuộc tên class giữa các service.

Hãy cấu hình key/value serializer đúng kiểu, giới hạn trusted packages, thống nhất type mapping và thiết kế JSON event như hợp đồng độc lập với class nội bộ. Với payload lỗi, dùng `ErrorHandlingDeserializer` cùng error handler/DLT để quản lý rõ ràng. Serialization đúng chỉ là bước đầu; schema compatibility, validation, idempotency và kiểm thử tích hợp mới giúp luồng messaging hoạt động tin cậy.

## Tài liệu tham khảo

- [Spring for Apache Kafka — Serialization, Deserialization, and Message Conversion](https://docs.spring.io/spring-kafka/reference/kafka/serdes.html)
- [Spring for Apache Kafka — Serialization/Deserialization Properties](https://docs.spring.io/spring-kafka/reference/kafka/serdes.html#serdes-json-config)
- [Spring for Apache Kafka — ErrorHandlingDeserializer](https://docs.spring.io/spring-kafka/reference/kafka/serdes.html#error-handling-deserializer)
- [Jackson — Annotations and Databinding](https://github.com/FasterXML/jackson-databind)
