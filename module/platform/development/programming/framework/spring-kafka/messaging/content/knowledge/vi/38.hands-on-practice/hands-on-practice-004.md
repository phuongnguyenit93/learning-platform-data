# Cấu hình JSON serialization

Kafka lưu key và value dưới dạng byte, vì vậy một ứng dụng Spring Kafka phải chuyển object Java thành JSON khi publish và chuyển JSON trở lại object khi consume. Spring Kafka cung cấp `JsonSerializer` và `JsonDeserializer` để thực hiện hai chiều này. Cấu hình đúng serializer, deserializer và type metadata giúp producer và consumer trao đổi DTO ổn định, đồng thời tránh lỗi sai kiểu, sai package hoặc không đọc được record cũ.

Trong bài thực hành này, ta xây dựng luồng `OrderCreated`: producer gửi sự kiện bằng `KafkaTemplate<String, OrderCreated>`, Kafka lưu JSON, và `@KafkaListener` nhận lại object `OrderCreated`. Ta cũng xem cách cấu hình type headers, type mapping, trusted packages, `ObjectMapper`, xử lý lỗi deserialize và kiểm thử với Embedded Kafka.

## 1. Luồng chuyển đổi object sang JSON và ngược lại

Quá trình gửi và nhận có hai bước chuyển đổi:

```text
Producer application                         Consumer application

OrderCreated object
       |
       v
JsonSerializer
       |
       v
JSON bytes + optional type headers
       |
       v
      Kafka topic
       |
       v
JSON bytes + headers
       |
       v
JsonDeserializer
       |
       v
OrderCreated object
```

`JsonSerializer` dùng Jackson để serialize object thành JSON bytes. `JsonDeserializer` đọc bytes và tạo object Java. Serializer/deserializer phải thống nhất về cấu trúc JSON, tên field, kiểu dữ liệu và cách xử lý type metadata.

JSON serialization chỉ định dạng payload. Nó không tự tạo schema registry, không xác thực đầy đủ hợp đồng nghiệp vụ và không bảo đảm producer/consumer tương thích khi DTO thay đổi. Nếu cần kiểm soát schema chặt chẽ, hãy kết hợp JSON Schema/Schema Registry hoặc cân nhắc Avro, Protobuf theo yêu cầu hệ thống.

## 2. Tạo DTO sự kiện có hợp đồng rõ ràng

Sự kiện nên biểu diễn một sự kiện nghiệp vụ đã xảy ra, có định danh và phiên bản hợp đồng. Ví dụ:

```java
import java.math.BigDecimal;
import java.time.Instant;

public record OrderCreated(
        String eventId,
        String orderId,
        String customerId,
        BigDecimal totalAmount,
        Instant occurredAt,
        int eventVersion) {
}
```

Các trường trong ví dụ có mục đích riêng:

- `eventId`: định danh duy nhất để truy vết và chống xử lý trùng.
- `orderId`: khóa aggregate, thường được dùng làm Kafka record key để giữ các sự kiện cùng đơn hàng trên một partition.
- `customerId`: thông tin cần thiết cho consumer.
- `totalAmount`: dùng `BigDecimal` cho giá trị tiền tệ thay vì `double`.
- `occurredAt`: thời điểm nghiệp vụ xảy ra; nên thống nhất timezone và định dạng.
- `eventVersion`: phiên bản contract do ứng dụng quản lý.

Không nên serialize trực tiếp JPA entity hoặc object nội bộ có nhiều quan hệ lazy. Hãy tạo DTO sự kiện riêng, chỉ chứa dữ liệu cần công bố và tránh làm lộ thông tin nội bộ.

## 3. Cấu hình JsonSerializer và JsonDeserializer bằng Spring Boot

Với Spring Boot, có thể khai báo serializer và deserializer qua `application.yml`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        spring.json.add.type.headers: true
    consumer:
      group-id: order-projection
      auto-offset-reset: earliest
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.example.orders.events
```

Trong ví dụ, producer gửi key dạng string và value dạng JSON. Consumer deserialize value thành kiểu được suy ra từ type header hoặc được cấu hình mặc định. `trusted.packages` giới hạn package chứa kiểu Java mà deserializer được phép tạo object khi xử lý type metadata.

Hãy thay `com.example.orders.events` bằng package DTO thực tế. Không cấu hình wildcard `*` cho trusted packages trong production nếu không có lý do bảo mật đã được đánh giá.

`auto-offset-reset` và `enable-auto-commit` là cấu hình consumer độc lập với JSON. Chúng được đưa vào để ví dụ có thể dùng trong ứng dụng listener thông thường; Spring Kafka container thường quản lý offset và tự đặt `enable.auto.commit=false` nếu ứng dụng chưa cấu hình khác.

## 4. Gửi JSON bằng KafkaTemplate

Khi producer factory dùng `JsonSerializer`, `KafkaTemplate` có thể gửi DTO trực tiếp:

```java
import java.time.Instant;
import java.util.UUID;
import java.math.BigDecimal;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(String orderId, String customerId,
                        BigDecimal totalAmount) {
        OrderCreated event = new OrderCreated(
                UUID.randomUUID().toString(),
                orderId,
                customerId,
                totalAmount,
                Instant.now(),
                1);

        kafkaTemplate.send("orders", orderId, event);
    }
}
```

Producer không cần tự gọi `ObjectMapper.writeValueAsBytes()` trong mỗi service. Serializer được cấu hình ở producer factory sẽ thực hiện chuyển đổi khi `KafkaTemplate.send()` gửi record.

Trong code production, nên xử lý kết quả bất đồng bộ của `send()`: ghi nhận callback/future khi broker xác nhận hoặc khi gửi thất bại. Nếu cần bảo đảm publish đi cùng transaction database, hãy dùng Outbox hoặc cơ chế phối hợp transaction phù hợp; JSON serializer không giải quyết dual write.

## 5. Nhận JSON bằng @KafkaListener

Khi consumer factory dùng `JsonDeserializer`, listener có thể nhận trực tiếp DTO:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    private final OrderProjectionService projectionService;

    public OrderCreatedListener(OrderProjectionService projectionService) {
        this.projectionService = projectionService;
    }

    @KafkaListener(topics = "orders", groupId = "order-projection")
    public void onOrderCreated(OrderCreated event) {
        projectionService.apply(event);
    }
}
```

Nếu producer và consumer dùng chung contract class, type header có thể giúp deserializer xác định kiểu. Nếu không muốn phụ thuộc package Java của producer, nên dùng type mapping hoặc cấu hình kiểu đích rõ ràng.

## 6. Type headers: producer gửi kiểu Java nào?

Theo cấu hình mặc định phổ biến của Spring Kafka, `JsonSerializer` thêm type information vào Kafka headers. `JsonDeserializer` có thể dùng header này để quyết định class cần tạo. Các header type metadata thường bao gồm thông tin type ID, và với cấu trúc phức tạp có thể có thông tin key/content type.

Điều này thuận tiện khi producer và consumer cùng hiểu một kiểu Java. Tuy nhiên, nếu header chứa tên class đầy đủ như `com.producer.contract.OrderCreated`, consumer ở package khác có thể không tìm thấy class tương ứng hoặc không nên phụ thuộc vào tên package của producer.

Có ba hướng thường dùng:

1. Dùng chung contract artifact và giữ class/package ổn định giữa producer và consumer.
2. Dùng type mapping để ánh xạ một token ổn định sang class tương ứng ở mỗi ứng dụng.
3. Tắt việc dùng type headers và cấu hình kiểu đích mặc định cho consumer.

Hãy chọn một chiến lược rõ ràng. Không để producer thay đổi package DTO mà không kiểm tra consumer đang dựa vào type header.

## 7. Type mapping để tách contract khỏi package Java

Type mapping cho phép serializer ghi một token ngắn vào header thay cho tên class đầy đủ. Consumer ánh xạ token đó sang class của chính consumer.

Producer:

```yaml
spring:
  kafka:
    producer:
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        spring.json.type.mapping: orderCreated:com.example.producer.events.OrderCreated
```

Consumer:

```yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.type.mapping: orderCreated:com.example.consumer.contract.OrderCreated
        spring.json.trusted.packages: com.example.consumer.contract
```

Hai ứng dụng dùng cùng token `orderCreated` nhưng có thể dùng class Java ở package khác nhau. Cấu trúc JSON của hai class vẫn phải tương thích. Type mapping chỉ ánh xạ type ID; nó không tự chuyển đổi tên field hoặc sửa payload.

Khi dùng mapping, kiểm tra cả key và value nếu ứng dụng serialize object cho cả hai. Mapping token phải thống nhất giữa producer và consumer; thay đổi token cần được rollout có kế hoạch.

## 8. Cấu hình kiểu mặc định và tắt type headers

Nếu topic chỉ chứa một loại payload, consumer có thể dùng kiểu đích cố định thay vì đọc type header:

```yaml
spring:
  kafka:
    producer:
      properties:
        spring.json.add.type.headers: false
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.use.type.headers: false
        spring.json.value.default.type: com.example.orders.events.OrderCreated
        spring.json.trusted.packages: com.example.orders.events
```

Ở chế độ này, producer không thêm type headers; consumer bỏ qua type headers và deserialize value thành `OrderCreated`. Đây là lựa chọn đơn giản cho topic có một schema payload cố định.

Nếu cùng topic chứa nhiều event type, một kiểu mặc định duy nhất không đủ. Khi đó cần type mapping, một envelope có trường `eventType`, hoặc nhiều topic theo loại event. Không nên dựa vào suy luận kiểu tùy tiện từ nội dung JSON.

## 9. Trusted packages và an toàn khi deserialize

Khi `JsonDeserializer` dùng type headers để tạo object, cần giới hạn những package được phép. `spring.json.trusted.packages` là allowlist cho các kiểu được deserialize.

Ví dụ chỉ tin cậy package contract:

```yaml
spring:
  kafka:
    consumer:
      properties:
        spring.json.trusted.packages: com.example.orders.contract
```

Tránh `spring.json.trusted.packages: '*'` trong production nếu không thực sự cần. Topic có thể nhận dữ liệu từ producer khác hoặc môi trường không tin cậy; không nên cho phép type metadata tùy ý dẫn đến khởi tạo class ngoài phạm vi hợp đồng.

Nếu consumer dùng kiểu đích cố định và tắt type headers, có thể cấu hình deserializer theo class cụ thể. Dù vậy, vẫn cần kiểm tra nguồn dữ liệu, kích thước payload và validation nghiệp vụ. Deserialize thành công không đồng nghĩa record hợp lệ.

## 10. ObjectMapper và định dạng ngày giờ

Jackson `ObjectMapper` quyết định cách serialize/deserialize field, enum, số, ngày giờ, naming strategy và null. Producer và consumer cần có quy ước nhất quán.

Ví dụ JSON mong đợi:

```json
{
  "eventId": "b3e2c0d0-1234-4567-890a-123456789abc",
  "orderId": "order-42",
  "customerId": "customer-7",
  "totalAmount": 125000.50,
  "occurredAt": "2026-11-17T04:30:00Z",
  "eventVersion": 1
}
```

Với `Instant`, nên dùng định dạng ISO-8601 UTC để tránh phụ thuộc timezone mặc định của máy. Với tiền tệ, dùng `BigDecimal` và thống nhất scale/rounding theo nghiệp vụ. Không đổi `BigDecimal` thành chuỗi ở một phía nếu consumer phía kia đang mong đợi JSON number.

Spring Boot thường cung cấp `ObjectMapper` đã được cấu hình qua Jackson auto-configuration. Spring Kafka cũng có cơ chế tạo enhanced mapper trong các cấu hình mặc định. Nếu cần tùy chỉnh, hãy bảo đảm serializer và deserializer dùng cùng quy ước. Ví dụ, khi thêm module Java Time, kiểm tra module đó đã được đăng ký và kiểm thử định dạng thực tế.

Không tạo một `ObjectMapper` khác biệt riêng trong từng service mà không có contract kiểm thử. Khác biệt về `PropertyNamingStrategy`, enum representation, null handling hoặc unknown properties có thể khiến payload không đọc được hoặc bị hiểu sai.

## 11. Xử lý lỗi JSON bằng ErrorHandlingDeserializer

Nếu JSON không hợp lệ hoặc không deserialize được thành DTO, `JsonDeserializer` có thể ném exception ngay trong quá trình poll. Khi muốn container error handler xử lý lỗi deserialize và đưa record vào recovery/DLT, hãy bọc delegate bằng `ErrorHandlingDeserializer`.

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.orders.events.OrderCreated
        spring.json.use.type.headers: false
        spring.json.trusted.packages: com.example.orders.events
```

`ErrorHandlingDeserializer` gọi deserializer delegate. Nếu delegate thất bại, Spring Kafka lưu thông tin exception vào header của record để container error handler có thể xử lý. Cần cấu hình `DefaultErrorHandler`/recoverer phù hợp để retry hoặc gửi record lỗi sang DLT.

Không nên biến mọi lỗi deserialize thành giá trị null rồi xử lý như record hợp lệ. Hãy phân biệt rõ payload null hợp lệ, tombstone và deserialize failure. Với compacted topic, tombstone là record có key nhưng value null và có ý nghĩa xóa state; không được nhầm nó với JSON hỏng.

## 12. JSON schema evolution và versioning

JSON không tự mang quy tắc tương thích schema. Khi thêm field, consumer cũ có thể bỏ qua field mới nếu deserializer/validator cho phép. Khi đổi tên hoặc xóa field, consumer mới có thể không đọc được record cũ nếu không có fallback hoặc default trong code.

Một số nguyên tắc:

- Ưu tiên thêm field optional trước khi yêu cầu producer cung cấp field mới.
- Consumer nên xử lý field có thể vắng mặt hoặc null theo quy tắc nghiệp vụ.
- Không tái sử dụng tên field với ý nghĩa khác.
- Khi đổi tên, triển khai consumer đọc cả tên mới và cũ, sau đó producer dual-write trong thời gian chuyển tiếp nếu phù hợp.
- Có thể thêm `eventVersion` hoặc header version để quản lý thay đổi contract.
- Nếu cần validation tương thích tự động, dùng JSON Schema và Schema Registry thay vì chỉ dựa vào DTO Jackson.

Không bật chế độ bỏ qua mọi field không biết mà không đánh giá. Consumer bỏ qua field mới có thể giúp forward compatibility, nhưng cũng có thể che lỗi contract hoặc khiến mất thông tin cần thiết.

## 13. Kiểm thử JSON serialization với Embedded Kafka

Integration test nên dùng serializer/deserializer thật để xác minh object đi qua broker vẫn giữ đúng dữ liệu. Ví dụ dùng `@EmbeddedKafka` với topic riêng:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.stereotype.Component;

@SpringBootTest
@EmbeddedKafka(
        topics = "orders-json-it",
        partitions = 1,
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
class OrderJsonSerializationTest {

    @Autowired
    KafkaTemplate<String, OrderCreated> kafkaTemplate;

    @Autowired
    TestOrderListener listener;

    @Test
    void serializesAndDeserializesOrderCreated() throws Exception {
        OrderCreated event = new OrderCreated(
                "event-1", "order-42", "customer-7",
                new BigDecimal("125000.50"),
                Instant.parse("2026-11-17T04:30:00Z"), 1);

        kafkaTemplate.send("orders-json-it", event.orderId(), event)
                .get(10, TimeUnit.SECONDS);

        OrderCreated received = listener.received()
                .poll(10, TimeUnit.SECONDS);

        assertNotNull(received);
        assertEquals(event.eventId(), received.eventId());
        assertEquals(event.orderId(), received.orderId());
        assertEquals(event.totalAmount(), received.totalAmount());
        assertEquals(event.occurredAt(), received.occurredAt());
        assertEquals(event.eventVersion(), received.eventVersion());
    }
}

@Component
class TestOrderListener {

    private final BlockingQueue<OrderCreated> received =
            new LinkedBlockingQueue<>();

    @KafkaListener(
            topics = "orders-json-it",
            groupId = "orders-json-it-group")
    void listen(OrderCreated event) {
        received.add(event);
    }

    BlockingQueue<OrderCreated> received() {
        return received;
    }
}
```

Ví dụ giả định ứng dụng test có producer/consumer JSON properties tương ứng và `TestOrderListener` được component scan hoặc khai báo bean. Nếu dùng `@SpringBootTest`, hãy bảo đảm test không vô tình kết nối broker local ngoài Embedded Kafka. Dùng `bootstrapServersProperty` để đưa địa chỉ broker nhúng vào cấu hình Spring Boot.

Không chỉ assert object bằng nhau; nên kiểm tra cả header type ID nếu ứng dụng phụ thuộc type headers. Nếu dùng type mapping hoặc tắt headers, thêm test xác nhận đúng kiểu mặc định/token được áp dụng.

## 14. Kiểm tra JSON bytes và headers khi cần

Khi cần xác định lỗi nằm ở serializer hay deserializer, hãy kiểm tra record thô bằng consumer dùng `ByteArrayDeserializer` hoặc dùng Kafka CLI để đọc payload. So sánh:

- JSON bytes có đúng tên field và kiểu dữ liệu không.
- Payload có field bắt buộc hoặc `eventVersion` không.
- Type headers có xuất hiện và token/type ID có đúng không.
- Header correlation ID, trace ID và event type có được giữ không.
- Consumer có dùng đúng default type, trusted package và type mapping không.

Nếu JSON bytes đã sai, kiểm tra producer `ObjectMapper` và DTO. Nếu bytes đúng nhưng deserialize thất bại, kiểm tra consumer deserializer, classpath, type headers, trusted packages và schema version. Cách tách hai bước này giúp tránh sửa consumer khi lỗi thực tế nằm ở producer.

## 15. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `ClassNotFoundException` khi consume | Type header chứa class name không tồn tại ở consumer | Dùng contract chung, type mapping hoặc default type |
| `IllegalArgumentException` về trusted packages | Package DTO chưa nằm trong allowlist | Thêm đúng package cần thiết; không mở wildcard tùy tiện |
| Consumer nhận sai DTO type | Type header hoặc mapping không đúng | Kiểm tra `spring.json.type.mapping` và use-type-headers |
| JSON parse error | Payload sai định dạng, producer serialize sai hoặc record bị hỏng | Đọc raw bytes, cấu hình ErrorHandlingDeserializer và DLT |
| Field mới bị null | Record cũ không có field hoặc producer chưa dual-write | Consumer dùng fallback/default phù hợp và rollout theo giai đoạn |
| Ngày giờ lệch timezone | ObjectMapper hoặc producer dùng timezone không thống nhất | Dùng ISO-8601 UTC và kiểm thử Instant/OffsetDateTime |
| Enum deserialize thất bại | Tên enum không còn tồn tại hoặc representation thay đổi | Giữ contract enum tương thích hoặc viết mapping rõ ràng |
| Consumer bỏ qua type header ngoài ý muốn | `spring.json.use.type.headers=false` hoặc default type cố định | Kiểm tra cấu hình deserializer và topic có nhiều event type không |
| Listener nhận null value | Tombstone hoặc deserialize failure được xử lý qua ErrorHandlingDeserializer | Phân biệt tombstone với lỗi bằng headers/error handler |

## 16. Checklist triển khai

- [ ] Producer dùng `JsonSerializer` cho DTO và consumer dùng `JsonDeserializer` tương ứng.
- [ ] `KafkaTemplate` khai báo generic type đúng với payload thực tế.
- [ ] DTO sự kiện có contract ổn định, event ID và version khi cần.
- [ ] Đã chọn rõ dùng type headers, type mapping hay default type.
- [ ] Nếu dùng type headers, consumer có class/mapping tương ứng và trusted packages giới hạn.
- [ ] Không dùng trusted packages wildcard tùy tiện trong production.
- [ ] Producer/consumer thống nhất cách xử lý ngày giờ, enum, decimal, null và unknown fields.
- [ ] Lỗi deserialize được chuyển qua ErrorHandlingDeserializer và error handler/DLT phù hợp.
- [ ] Tombstone được phân biệt với payload JSON lỗi.
- [ ] Đã kiểm thử round-trip JSON bằng serializer/deserializer thật.
- [ ] Đã kiểm tra JSON bytes và headers khi cần chẩn đoán.
- [ ] Có chiến lược schema evolution khi thêm, đổi tên hoặc xóa field.

JSON serialization trong Spring Kafka được cấu hình tại producer và consumer factory: `JsonSerializer` chuyển DTO thành JSON bytes, còn `JsonDeserializer` khôi phục object. Type headers và type mapping quyết định cách chọn class; trusted packages giới hạn kiểu được phép deserialize; `ObjectMapper` quyết định định dạng dữ liệu. Khi các phần này được thống nhất và kiểm thử qua broker, producer và consumer có thể trao đổi event JSON ổn định, đồng thời có đường xử lý rõ ràng cho payload lỗi và thay đổi contract.
