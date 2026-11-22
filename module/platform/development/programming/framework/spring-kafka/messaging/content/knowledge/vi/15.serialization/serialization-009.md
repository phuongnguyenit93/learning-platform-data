# Cấu hình default type

## 1. Default type giải quyết vấn đề gì?

Kafka lưu key và value dưới dạng byte. Khi consumer đọc record, deserializer phải biết kiểu dữ liệu đích để chuyển byte thành object. Với JSON, Spring Kafka cung cấp `JsonSerializer` và `JsonDeserializer` để thực hiện chuyển đổi này.

`JsonDeserializer` có thể lấy thông tin kiểu từ type header do Spring Kafka JSON serializer ghi vào record. Tuy nhiên, không phải producer nào cũng tạo header đó. Một producer viết bằng ngôn ngữ khác, một producer dùng serializer JSON thông thường hoặc một hệ thống đã tắt type header có thể chỉ gửi JSON thuần.

Trong trường hợp consumer biết trước kiểu payload cần nhận, có thể cấu hình **default type** để `JsonDeserializer` sử dụng một lớp mặc định khi không có type header phù hợp. Ví dụ, topic `orders` chỉ chứa sự kiện `OrderCreated`, nên consumer có thể mặc định deserialize value thành `OrderCreated`.

Default type đặc biệt hữu ích khi:

- Consumer nhận JSON từ producer không dùng Spring Kafka.
- Producer không gửi type header.
- Hợp đồng topic quy định một kiểu payload cụ thể.
- Consumer muốn bỏ qua type header và luôn deserialize theo DTO đã chọn.

Default type là cấu hình ở phía consumer. Nó không thay đổi JSON được producer gửi và cũng không tự thêm metadata vào record.

## 2. Type header và default type hoạt động cùng nhau

Mặc định, `JsonSerializer` của Spring Kafka có thể thêm type information vào Kafka record headers. `JsonDeserializer` mặc định sử dụng type header nếu header hiện diện và được bật. Default type đóng vai trò kiểu dự phòng khi không có type information để xác định lớp đích.

Các header type thường gặp gồm:

| Header | Mục đích |
|---|---|
| `__TypeId__` | Kiểu chính của payload/value |
| `__KeyTypeId__` | Kiểu của key khi key cũng được serialize bằng JSON |
| `__ContentTypeId__` | Kiểu phần tử bên trong một cấu trúc có nội dung lồng nhau trong các trường hợp được hỗ trợ |

Có hai cách cấu hình phổ biến:

1. **Ưu tiên type header, dùng default type làm dự phòng:** để `spring.json.use.type.headers=true` (mặc định). Nếu header hợp lệ, deserializer dùng kiểu từ header; nếu không có header, deserializer dùng default type.
2. **Bỏ qua type header, luôn dùng default type:** đặt `spring.json.use.type.headers=false`. Cách này phù hợp khi topic có một kiểu payload cố định hoặc producer gửi JSON thuần và consumer muốn kiểm soát kiểu đích.

Nếu bật sử dụng type header nhưng header chỉ đến một class không tồn tại hoặc không được tin cậy, deserializer có thể báo lỗi. Default type không nên được xem là cơ chế tự động sửa mọi type header sai. Khi muốn cố định kiểu đích, hãy tắt việc sử dụng type header một cách tường minh.

## 3. Cấu hình default type cho value bằng Spring Boot

Giả sử topic `orders` chỉ chứa JSON của lớp:

```java
package com.example.messaging.events;

public record OrderCreated(
        String eventId,
        String orderId,
        BigDecimal total) {}
```

Consumer có thể cấu hình `spring.json.value.default.type` trong `application.yml`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-service
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.example.messaging.events.OrderCreated
        spring.json.use.type.headers: false
        spring.json.trusted.packages: com.example.messaging.events
```

Ý nghĩa:

- `value-deserializer` chọn `JsonDeserializer` cho value.
- `spring.json.value.default.type` chỉ định lớp Java dùng để deserialize value.
- `spring.json.use.type.headers: false` yêu cầu deserializer bỏ qua type header và dùng kiểu mặc định.
- `spring.json.trusted.packages` giới hạn các package được phép dùng khi giải quyết type information.

Trong ví dụ này, key là chuỗi nên dùng `StringDeserializer`; không cần cấu hình default type cho key. Nếu key cũng là JSON object, cần cấu hình key serializer/deserializer tương ứng và xem xét `spring.json.key.default.type`.

### Producer gửi JSON

Producer có thể dùng `JsonSerializer`:

```yaml
spring:
  kafka:
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
```

Service gửi sự kiện:

```java
@Service
public class OrderEventPublisher {
    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {
        return kafkaTemplate.send("orders", event.orderId(), event);
    }
}
```

Consumer dùng default type có thể nhận payload trực tiếp:

```java
@Component
public class OrderCreatedListener {

    @KafkaListener(topics = "orders", groupId = "order-service")
    public void onOrderCreated(OrderCreated event) {
        // Xử lý sự kiện đã được deserialize thành OrderCreated.
    }
}
```

Generic type `KafkaTemplate<String, OrderCreated>` giúp Spring wiring và code phía producer rõ kiểu dữ liệu. Kiểu Java generic không được truyền qua Kafka như một phần của payload; việc deserialize ở consumer vẫn phụ thuộc byte, serializer, type header và default type.

## 4. Cấu hình default type bằng Java

Nếu tự tạo `ConsumerFactory`, có thể cấu hình các thuộc tính của `JsonDeserializer` trong map:

```java
@Configuration
public class KafkaConsumerConfiguration {

    @Bean
    ConsumerFactory<String, OrderCreated> orderConsumerFactory() {
        Map<String, Object> props = new HashMap<>();
        props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
        props.put(ConsumerConfig.GROUP_ID_CONFIG, "order-service");
        props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
                JsonDeserializer.class);
        props.put(JsonDeserializer.VALUE_DEFAULT_TYPE,
                OrderCreated.class.getName());
        props.put(JsonDeserializer.USE_TYPE_INFO_HEADERS, false);
        props.put(JsonDeserializer.TRUSTED_PACKAGES,
                "com.example.messaging.events");

        return new DefaultKafkaConsumerFactory<>(props);
    }
}
```

Các hằng số `JsonDeserializer.VALUE_DEFAULT_TYPE`, `USE_TYPE_INFO_HEADERS` và `TRUSTED_PACKAGES` tương ứng với các property `spring.json.value.default.type`, `spring.json.use.type.headers` và `spring.json.trusted.packages`.

Khi tự khai báo `ConsumerFactory`, cần bảo đảm listener container factory sử dụng đúng bean này. Nếu Spring Boot đã auto-configure một `ConsumerFactory` khác, hãy đặt tên bean và wiring rõ ràng để tránh listener vô tình dùng cấu hình mặc định.

Có thể cấu hình trực tiếp deserializer bằng constructor hoặc fluent API thay vì map properties. Khi đã cấu hình `JsonDeserializer` bằng setter/fluent API, không nên trộn thêm cách cấu hình property map cho cùng deserializer; chọn một cách cấu hình nhất quán và kiểm tra hành vi của phiên bản Spring Kafka đang dùng.

## 5. Default type cho key và value

Kafka record có hai phần dữ liệu riêng: key và value. Nếu cả hai đều được serialize bằng JSON, có thể cấu hình default type độc lập:

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.key.default.type: com.example.messaging.OrderKey
        spring.json.value.default.type: com.example.messaging.events.OrderCreated
        spring.json.use.type.headers: false
        spring.json.trusted.packages: com.example.messaging
```

`spring.json.key.default.type` chỉ định kiểu cho key; `spring.json.value.default.type` chỉ định kiểu cho value. Không dùng một default type chung để mong deserializer tự suy ra hai kiểu khác nhau.

Trong nhiều hệ thống, key được giữ ở dạng chuỗi như `orderId`, còn value là JSON DTO. Khi đó nên dùng `StringDeserializer` cho key và `JsonDeserializer` cho value. Cách này đơn giản, dễ quan sát và tránh phức tạp không cần thiết ở phần key.

## 6. Default type khi không tắt type header

Không phải lúc nào cũng cần đặt `spring.json.use.type.headers=false`. Nếu producer Spring Kafka gửi type header hợp lệ, consumer có thể dùng header để xác định lớp. Default type chỉ được dùng khi không có type information cần thiết.

Ví dụ:

```yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.example.messaging.events.OrderCreated
        spring.json.use.type.headers: true
        spring.json.trusted.packages: com.example.messaging.events
```

Với cấu hình này:

- Record có type header hợp lệ: deserializer dùng kiểu được xác định từ header.
- Record không có type header: deserializer dùng `OrderCreated` làm default type.
- Record có type header trỏ tới class không thể nạp hoặc không được tin cậy: quá trình deserialize có thể thất bại; default type không tự động thay thế class header sai.

Chọn `true` khi topic có thể chứa nhiều kiểu payload và producer gửi type information đáng tin cậy. Chọn `false` khi topic có hợp đồng một kiểu cố định và consumer muốn ép mọi record về một DTO cụ thể.

## 7. Phân biệt default type và type mapping

Default type và type mapping đều liên quan đến việc xác định kiểu Java từ JSON, nhưng giải quyết hai nhu cầu khác nhau.

| Cơ chế | Mục đích | Khi nên dùng |
|---|---|---|
| Default type | Chỉ định một kiểu fallback hoặc kiểu cố định cho key/value | Topic có một kiểu payload, hoặc producer không gửi type header |
| Type mapping | Ánh xạ token ngắn trong type header sang class Java | Topic chứa nhiều loại sự kiện và muốn tránh gửi tên class đầy đủ |
| Type header mặc định | Cho serializer ghi type information để deserializer suy ra kiểu | Producer và consumer chia sẻ hợp đồng kiểu hoặc có mapping tương thích |

Ví dụ topic `domain-events` có hai kiểu sự kiện `OrderCreated` và `PaymentReceived`. Một default type duy nhất không đủ để biểu diễn cả hai kiểu nếu consumer cần phân biệt chúng. Có thể dùng type mapping:

```yaml
spring:
  kafka:
    producer:
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        spring.json.type.mapping: orderCreated:com.example.orders.OrderCreated,paymentReceived:com.example.payments.PaymentReceived
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.type.mapping: orderCreated:com.example.consumer.OrderCreated,paymentReceived:com.example.consumer.PaymentReceived
        spring.json.use.type.headers: true
        spring.json.trusted.packages: com.example.consumer
```

Producer ghi token `orderCreated` hoặc `paymentReceived` vào type header thay cho tên class đầy đủ. Consumer ánh xạ token đó sang DTO tương ứng ở phía consumer. Hai phía có thể dùng package/class name khác nhau nhưng phải thống nhất token.

Không đặt `spring.json.use.type.headers=false` trong ví dụ type mapping trên, vì deserializer cần đọc type header để biết record thuộc kiểu nào. Nếu tắt type header, mapping không còn được dùng để chọn kiểu theo token.

## 8. Producer không dùng Spring Kafka

Một lợi ích lớn của default type là hỗ trợ producer ngoài hệ sinh thái Spring. Ví dụ một ứng dụng Python gửi JSON thuần lên topic `orders`:

```python
import json

payload = {
    "eventId": "evt-1001",
    "orderId": "ORD-1001",
    "total": 125.50
}

producer.send(
    "orders",
    key=b"ORD-1001",
    value=json.dumps(payload).encode("utf-8")
)
```

Producer này không tự thêm các type header đặc thù của Spring Kafka. Consumer Java có thể dùng `JsonDeserializer` cùng `spring.json.value.default.type` để chuyển JSON thành `OrderCreated`, miễn là tên field, kiểu dữ liệu và schema tương thích.

Default type chỉ giải quyết việc chọn lớp Java. Nó không tự chuyển đổi schema khác nhau, đổi tên field, chuẩn hóa ngày giờ hoặc xử lý version của event. Với hệ thống đa ngôn ngữ, nên xác định schema trung lập và quy tắc tương thích rõ ràng; có thể dùng JSON Schema, Avro hoặc Protobuf cùng schema registry nếu nhu cầu yêu cầu.

## 9. Bảo mật khi dùng type information

Type header có thể chứa tên class hoặc token ánh xạ. Khi deserializer dùng thông tin này để nạp lớp, cần giới hạn package được tin cậy. `spring.json.trusted.packages` cho phép chỉ định các package mà deserializer được phép giải quyết.

Ví dụ:

```yaml
spring:
  kafka:
    consumer:
      properties:
        spring.json.trusted.packages: com.example.messaging.events,com.example.shared.events
```

Chỉ đưa vào danh sách các package DTO thực sự cần thiết. Tránh cấu hình wildcard `*` trong môi trường production nếu không có lý do và đánh giá bảo mật cụ thể. Không nên coi type header từ producer bên ngoài là dữ liệu đáng tin cậy chỉ vì nó nằm trong Kafka record.

Nếu topic có một kiểu payload cố định, đặt default type và tắt type header có thể giảm phụ thuộc vào tên class do producer gửi. Tuy vậy, vẫn cần validate payload, giới hạn kích thước record và xử lý JSON không hợp lệ.

## 10. Lỗi thường gặp khi cấu hình default type

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra/xử lý |
|---|---|---|
| `No type information in headers and no default type provided` | Record không có type header và consumer chưa cấu hình default type/target type | Đặt `spring.json.value.default.type` hoặc cấu hình target type bằng constructor |
| Không tìm thấy class từ type header | Producer gửi tên class không tồn tại trong consumer hoặc package khác | Dùng type mapping chung token hoặc tắt type header và cấu hình default type nếu topic chỉ có một kiểu |
| `not in the trusted packages` | Package trong type header không nằm trong danh sách trusted | Thêm đúng package DTO cần thiết vào `spring.json.trusted.packages`; tránh mở wildcard tùy tiện |
| JSON parse/deserialization lỗi | Payload không khớp DTO, field hoặc kiểu dữ liệu không tương thích | Kiểm tra byte JSON, schema, naming và kiểu field |
| Consumer luôn nhận sai DTO | Type header đang được ưu tiên thay vì default type | Nếu muốn cố định DTO, đặt `spring.json.use.type.headers=false` |
| Nhiều event type không deserialize được | Chỉ cấu hình một default type cho topic chứa nhiều loại payload | Dùng type mapping/type header hoặc tách topic theo kiểu event |
| Cấu hình YAML không có tác dụng | Sai prefix, sai indent, hoặc custom `ConsumerFactory` không dùng cấu hình Boot | Kiểm tra `spring.kafka.consumer.properties` và bean thực tế được listener sử dụng |

Khi điều tra lỗi, nên kiểm tra theo thứ tự: deserializer đang được dùng, payload JSON thực tế, type headers, default type, trusted packages và schema DTO. Không nên sửa lỗi bằng cách thêm wildcard package hoặc ép mọi payload về một class mà không xác minh hợp đồng topic.

## 11. Kiểm thử default type

Kiểm thử cần bao phủ trường hợp có header, không có header và header không phù hợp:

1. **Không có type header:** gửi JSON thuần vào topic và xác nhận consumer tạo được `OrderCreated` từ default type.
2. **Có type header và `use.type.headers=true`:** xác nhận header hợp lệ được dùng để chọn kiểu payload.
3. **Có type header nhưng `use.type.headers=false`:** xác nhận consumer bỏ qua header và deserialize theo default type.
4. **Header trỏ tới class không hợp lệ:** xác nhận lỗi được ghi nhận và xử lý theo error handler; không mong default type tự sửa header sai khi đang bật type header.
5. **Trusted packages:** xác nhận class ngoài package cho phép bị từ chối và package hợp lệ được deserialize.
6. **Key và value khác kiểu:** kiểm tra `key.default.type` và `value.default.type` độc lập nếu cả hai dùng JSON.
7. **Nhiều loại event:** kiểm tra type mapping để token của từng loại ánh xạ đến DTO đúng.
8. **Tương thích đa ngôn ngữ:** gửi JSON từ producer không dùng Spring và xác nhận consumer Java deserialize đúng theo hợp đồng schema.

Có thể dùng `spring-kafka-test` hoặc Kafka test starter tương ứng với phiên bản Spring Boot. Nên có ít nhất một test dùng record không chứa type header, vì đây là trường hợp default type được sử dụng trực tiếp.

## 12. Quy trình chọn cấu hình

Trước khi đặt default type, hãy xác định cấu trúc topic:

1. Nếu topic chỉ chứa một kiểu value, cấu hình `spring.json.value.default.type` theo DTO của topic.
2. Nếu producer không gửi type header, default type có thể được dùng làm fallback; đặt `use.type.headers=false` nếu muốn ép kiểu cố định.
3. Nếu topic chứa nhiều kiểu event và producer có thể gửi type header, dùng type mapping để quản lý tên kiểu và tương thích package.
4. Nếu key cũng là JSON object, cấu hình key deserializer và `spring.json.key.default.type` riêng.
5. Giới hạn trusted packages theo package DTO thực sự cần dùng.
6. Kiểm thử record không header, record có header và record có schema sai trước khi triển khai.

Không nên dùng một default type chung cho topic có nhiều kiểu event khác nhau nếu consumer cần phân biệt các loại đó. Hãy chọn type header/type mapping hoặc tách topic theo hợp đồng nghiệp vụ.

## 13. Tổng kết

- Default type là kiểu Java mặc định mà `JsonDeserializer` dùng khi không có type information phù hợp.
- `spring.json.value.default.type` cấu hình kiểu mặc định cho value; `spring.json.key.default.type` cấu hình riêng cho key.
- `spring.json.use.type.headers=true` cho phép type header quyết định kiểu khi header hiện diện; default type làm fallback khi thiếu header.
- `spring.json.use.type.headers=false` bỏ qua type header và dùng default type/target type đã cấu hình.
- Type mapping phù hợp với topic chứa nhiều loại event; default type đơn lẻ phù hợp với topic có một kiểu payload.
- `spring.json.trusted.packages` giới hạn package được phép dùng khi giải quyết type information.
- Default type không thay thế schema compatibility, validation hoặc versioning cho hệ thống đa ngôn ngữ.

Khi cấu hình đúng default type, consumer Spring Kafka có thể đọc JSON từ cả producer Spring và producer bên ngoài mà không phụ thuộc bắt buộc vào type header của Spring. Hợp đồng payload, kiểu dữ liệu, mapping và chính sách tin cậy vẫn cần được thống nhất giữa các hệ thống gửi và nhận.
