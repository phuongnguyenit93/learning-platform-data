# Type header và thông tin kiểu Java

Khi gửi object Java qua Kafka bằng JSON, producer chuyển object thành byte để ghi vào record. Consumer nhận byte và cần biết nên deserialize thành lớp Java nào. Chỉ nhìn JSON thường không đủ để phân biệt các kiểu object có cấu trúc gần giống nhau, đặc biệt khi một topic chứa nhiều loại sự kiện.

Spring Kafka giải quyết việc này bằng **type headers**: `JsonSerializer` có thể thêm metadata kiểu Java vào Kafka headers, còn `JsonDeserializer` đọc metadata đó để chọn kiểu đích. Cơ chế này hữu ích khi một topic chứa nhiều loại sự kiện hoặc khi payload có kiểu cụ thể khác nhau. Tuy nhiên, tên lớp Java không nên trở thành hợp đồng phụ thuộc chặt giữa các dịch vụ; type mapping, trusted packages và default type giúp kiểm soát việc trao đổi kiểu an toàn hơn.

## 1. Vì sao cần thông tin kiểu Java?

Giả sử topic `orders.events` nhận hai loại sự kiện được khai báo trong các file Java riêng:

```java
// OrderCreated.java
package com.example.events;

import java.time.Instant;

public record OrderCreated(String orderId, Instant createdAt) {}
```

```java
// OrderPaid.java
package com.example.events;

import java.math.BigDecimal;
import java.time.Instant;

public record OrderPaid(String orderId, BigDecimal amount, Instant paidAt) {}
```

JSON của hai loại sự kiện có thể có một số field giống nhau, nhưng consumer cần tạo đúng object tương ứng để xử lý nghiệp vụ. Nếu deserialize tất cả thành `Map` hoặc một DTO chung, ứng dụng phải tự kiểm tra field và chuyển đổi thủ công.

Spring Kafka JSON serializer có thể ghi type metadata vào header của record:

```text
Kafka record
  key: order-1001
  value: {"orderId":"order-1001","createdAt":"..."}
  headers:
    __TypeId__: com.example.events.OrderCreated
```

Consumer dùng `__TypeId__` để xác định lớp Java cần tạo. Với ví dụ trên, `JsonDeserializer` có thể deserialize value thành `OrderCreated` thay vì một kiểu chung.

Type header là metadata của Kafka record, không phải field được thêm vào JSON payload. Producer có thể giữ JSON thuần trong value và truyền thông tin kiểu ở headers.

## 2. Các type headers của Spring Kafka

Spring Kafka JSON type mapper sử dụng một số header có tên quy ước:

| Header | Ý nghĩa |
|---|---|
| `__TypeId__` | Kiểu chính của object được serialize, thường là tên lớp hoặc token mapping |
| `__ContentTypeId__` | Kiểu phần tử bên trong container như collection hoặc array |
| `__KeyTypeId__` | Kiểu key của cấu trúc dạng map |

Với một object đơn giản, `__TypeId__` thường là header quan trọng nhất. Với kiểu dữ liệu phức tạp như `List<OrderLine>` hoặc `Map<String, OrderLine>`, metadata content/key type giúp mô tả thêm các kiểu generic mà Java type erasure không thể tự khôi phục chỉ từ tên container.

Giá trị header mặc định có thể là tên lớp đầy đủ, ví dụ `com.example.events.OrderCreated`. Nếu producer và consumer dùng package khác nhau hoặc triển khai bằng ngôn ngữ khác, phụ thuộc vào tên lớp đầy đủ sẽ làm hợp đồng messaging dễ bị phá vỡ khi refactor. Spring Kafka hỗ trợ type mapping để thay tên lớp bằng một token ổn định.

## 3. JsonSerializer và JsonDeserializer phối hợp ra sao?

Trong cấu hình JSON thông thường, `JsonSerializer` thêm type headers và `JsonDeserializer` sử dụng các header này để chọn kiểu Java đích. Cả hai thành phần đều có thể được cấu hình qua Spring Boot.

Luồng xử lý:

```text
Producer
  OrderCreated object
       |
       v
  JsonSerializer
       |
       +---- JSON bytes (record value)
       +---- __TypeId__ (record header)
       |
       v
  Kafka topic
       |
       v
  JsonDeserializer
       |
       +---- đọc __TypeId__ hoặc default type
       +---- kiểm tra trusted packages
       +---- tạo object Java tương ứng
       |
       v
  @KafkaListener
```

Các giá trị mặc định và API chi tiết có thể thay đổi theo phiên bản Spring Kafka. Trong các phiên bản phổ biến, việc thêm type header của JSON serializer và sử dụng type header của JSON deserializer được bật mặc định. Khi thay đổi cấu hình, hãy kiểm tra đúng phiên bản thư viện mà ứng dụng đang dùng.

### Cấu hình producer gửi JSON

Ví dụ Spring Boot dùng String cho key và JSON cho value:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
```

Producer gửi object qua `KafkaTemplate`:

```java
import java.time.Instant;
import com.example.events.OrderCreated;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
class OrderEventPublisher {

    private final KafkaTemplate<String, Object> kafkaTemplate;

    OrderEventPublisher(KafkaTemplate<String, Object> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(String orderId) {
        var event = new OrderCreated(orderId, Instant.now());
        kafkaTemplate.send("orders.events", orderId, event);
    }
}
```

`JsonSerializer` serialize object thành JSON bytes và mặc định thêm type metadata của kiểu runtime vào headers. Key vẫn dùng `StringSerializer`, vì vậy key không cần JSON type header.

### Cấu hình consumer đọc JSON theo type header

```yaml
spring:
  kafka:
    consumer:
      group-id: order-projection
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.example.events
```

Khi consumer nhận record có `__TypeId__` trỏ tới `com.example.events.OrderCreated`, `JsonDeserializer` có thể tạo object `OrderCreated` nếu lớp đó tồn tại và package được tin cậy.

Listener có thể khai báo kiểu cụ thể:

```java
import java.time.Instant;
import com.example.events.OrderCreated;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderCreatedListener {

    @KafkaListener(topics = "orders.events", groupId = "order-created-projection")
    public void consume(OrderCreated event) {
        updateOrderProjection(event.orderId(), event.createdAt());
    }

    private void updateOrderProjection(String orderId, Instant createdAt) {
        // Cập nhật read model của đơn hàng.
    }
}
```

Trong ví dụ minh họa, import `Instant` và các DTO phải có trong project. Nếu một listener cần nhận nhiều loại event khác nhau, hãy chọn một kiểu chung phù hợp hoặc dùng `ConsumerRecord<String, Object>` rồi phân nhánh theo kiểu runtime.

## 4. Type mapping: dùng token thay cho tên lớp đầy đủ

Type mapping cho phép gắn một token ngắn với lớp Java. Ví dụ:

```text
orderCreated:com.example.events.OrderCreated
orderPaid:com.example.events.OrderPaid
```

Khi producer serialize `OrderCreated`, header `__TypeId__` có thể chứa token `orderCreated` thay vì tên lớp đầy đủ. Consumer có mapping tương ứng sẽ chuyển token đó về lớp Java `OrderCreated`.

### Khai báo mapping ở producer và consumer

Producer:

```yaml
spring:
  kafka:
    producer:
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        spring.json.type.mapping: >-
          orderCreated:com.example.events.OrderCreated,
          orderPaid:com.example.events.OrderPaid
```

Consumer:

```yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.example.events
        spring.json.type.mapping: >-
          orderCreated:com.example.events.OrderCreated,
          orderPaid:com.example.events.OrderPaid
```

Hai phía cần thống nhất token, nhưng không bắt buộc phải dùng cùng một lớp Java hoặc cùng package. Producer dùng mapping để chuyển lớp Java phía producer thành token khi ghi header; consumer dùng mapping để chuyển token đó về DTO phía consumer. Nếu consumer không có mapping tương ứng, deserializer có thể không xác định được kiểu đích.

Ví dụ, producer và consumer có thể dùng hai mapping khác nhau nhưng cùng token:

```yaml
# Producer
spring.kafka.producer.properties.spring.json.type.mapping: >-
  orderCreated:com.orders.internal.event.OrderCreated
```

```yaml
# Consumer
spring:
  kafka:
    consumer:
      properties:
        spring.json.type.mapping: >-
          orderCreated:com.reporting.contract.OrderCreatedMessage
        spring.json.trusted.packages: com.reporting.contract
```

Nhờ vậy, hai dịch vụ chia sẻ hợp đồng `orderCreated` mà không cần phụ thuộc vào package nội bộ của nhau.

Token nên biểu diễn loại sự kiện theo hợp đồng, ví dụ `orderCreated`, thay vì tên implementation như `OrderCreatedV2Internal`. Khi đổi package hoặc refactor lớp Java, có thể giữ token ổn định và cập nhật mapping ở từng dịch vụ.

## 5. Một topic chứa nhiều loại event

Type mapping hữu ích khi một topic chứa nhiều loại sự kiện có cấu trúc khác nhau. Mỗi record có type header riêng, vì vậy deserializer có thể tạo đúng kiểu object theo từng record.

Ví dụ khai báo hai event:

```java
package com.example.events;

import java.time.Instant;

public record OrderCreated(String orderId, Instant createdAt) {}
```

```java
package com.example.events;

import java.math.BigDecimal;
import java.time.Instant;

public record OrderPaid(String orderId, BigDecimal amount, Instant paidAt) {}
```

Producer có thể gửi hai loại object vào cùng topic:

```java
import com.example.events.OrderCreated;
import com.example.events.OrderPaid;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
class MixedOrderEventPublisher {

    private final KafkaTemplate<String, Object> kafkaTemplate;

    MixedOrderEventPublisher(KafkaTemplate<String, Object> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderCreated created, OrderPaid paid) {
        kafkaTemplate.send("orders.events", created.orderId(), created);
        kafkaTemplate.send("orders.events", paid.orderId(), paid);
    }
}
```

Với mapping đã cấu hình, các header tương ứng có thể là:

```text
Record 1: __TypeId__ = orderCreated
Record 2: __TypeId__ = orderPaid
```

Listener nhận kiểu chung `Object` và xử lý theo kiểu runtime:

```java
import com.example.events.OrderCreated;
import com.example.events.OrderPaid;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderEventRouter {

    @KafkaListener(topics = "orders.events", groupId = "order-event-router")
    public void consume(Object event) {
        if (event instanceof OrderCreated created) {
            handleCreated(created);
        } else if (event instanceof OrderPaid paid) {
            handlePaid(paid);
        } else {
            throw new IllegalArgumentException(
                    "Unsupported event type: "
                            + (event == null ? "null" : event.getClass().getName())
            );
        }
    }

    private void handleCreated(OrderCreated event) {
        // Xử lý OrderCreated.
    }

    private void handlePaid(OrderPaid event) {
        // Xử lý OrderPaid.
    }
}
```

Đây là cách định tuyến theo lớp Java sau deserialize. Với hệ thống nhiều dịch vụ, cũng có thể thiết kế một interface event hoặc discriminator nghiệp vụ trong payload. Hãy tránh để consumer phụ thuộc vào tên implementation nội bộ của producer.

## 6. Default type khi record không có type header

Không phải producer nào cũng gửi Spring Kafka type headers. Record có thể đến từ producer khác, dữ liệu được tạo trước khi bật type header, hoặc producer đã tắt header metadata.

Nếu consumer biết trước kiểu payload, có thể cấu hình default type:

```yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.example.events.OrderCreated
        spring.json.trusted.packages: com.example.events
```

Khi record không có type header và consumer không có kiểu đích được xác định theo cách khác, `JsonDeserializer` có thể dùng default type đã cấu hình để tạo `OrderCreated`. Default type đặc biệt hữu ích khi một topic chỉ chứa một loại payload và producer không cần gửi type metadata.

Nếu cần luôn dùng kiểu mặc định và bỏ qua type header, cấu hình:

```yaml
spring:
  kafka:
    consumer:
      properties:
        spring.json.use.type.headers: false
        spring.json.value.default.type: com.example.events.OrderCreated
        spring.json.trusted.packages: com.example.events
```

Khi `spring.json.use.type.headers` là `false`, deserializer không dùng type header để chọn kiểu đích. Hãy bảo đảm tất cả record mà consumer đọc có thể deserialize thành default type; cấu hình này không phù hợp nếu topic chứa nhiều loại event khác nhau.

Có thể cấu hình kiểu mặc định cho key bằng `spring.json.key.default.type` khi key cũng được deserialize bằng JSON. Trong nhiều hệ thống, key là chuỗi hoặc số đơn giản nên dùng StringDeserializer hoặc deserializer tương ứng sẽ dễ quản lý hơn.

## 7. Trusted packages và an toàn khi deserialize

Type header có thể chứa tên lớp hoặc token do producer gửi. Consumer không nên tự động tin mọi tên lớp từ nguồn dữ liệu không kiểm soát. Spring Kafka JSON deserializer sử dụng trusted packages để giới hạn package được phép tạo object.

Ví dụ chỉ tin package chứa event contract:

```yaml
spring:
  kafka:
    consumer:
      properties:
        spring.json.trusted.packages: com.example.events,com.example.shared.contract
```

Không nên cấu hình wildcard `*` trong môi trường production nếu không có lý do và kiểm soát phù hợp. Tin toàn bộ package làm rộng phạm vi kiểu mà deserializer có thể khởi tạo. Hãy chỉ cho phép package chứa DTO/event contract cần thiết.

Một số lỗi thường gặp:

- Header chứa tên lớp không tồn tại trên classpath consumer.
- Token trong `__TypeId__` không có mapping tương ứng.
- Package của lớp đích chưa được thêm vào trusted packages.
- Producer và consumer không thống nhất cấu trúc JSON hoặc phiên bản event.
- Consumer ép mọi record thành một default type trong khi topic chứa nhiều loại event.

Khi gặp lỗi deserialize, kiểm tra type header, mapping, classpath và trusted packages trước khi thay đổi cấu hình rộng hơn.

## 8. Giữ hoặc loại bỏ type headers

Type headers là metadata hữu ích nhưng không phải consumer nào cũng cần. Một số hệ thống muốn JSON payload độc lập với Java class, đặc biệt khi có consumer viết bằng Python, Go hoặc một nền tảng khác.

Producer có thể tắt việc thêm type headers:

```yaml
spring:
  kafka:
    producer:
      properties:
        spring.json.add.type.headers: false
```

Consumer có thể bỏ qua type headers và dùng default type hoặc kiểu do ứng dụng xác định:

```yaml
spring:
  kafka:
    consumer:
      properties:
        spring.json.use.type.headers: false
        spring.json.value.default.type: com.example.events.OrderCreated
        spring.json.trusted.packages: com.example.events
```

Ngoài ra, `JsonDeserializer` mặc định có thể loại bỏ type headers sau khi dùng chúng để deserialize. Nếu ứng dụng cần đọc lại các header này trong listener, có thể cấu hình:

```yaml
spring:
  kafka:
    consumer:
      properties:
        spring.json.remove.type.headers: false
```

Khi giữ header, listener có thể truy cập chúng qua `ConsumerRecord.headers()`. Nếu header đã bị deserializer loại bỏ, không nên giả định chúng vẫn còn ở đó chỉ vì producer đã gửi. Việc bật giữ header cần được cân nhắc nếu downstream sẽ xử lý hoặc forward metadata này.

## 9. Type header không thay thế versioning của event

Type header cho biết record cần được deserialize thành kiểu Java nào. Nó không tự mô tả đầy đủ version của schema, quy tắc tương thích field hoặc ý nghĩa nghiệp vụ của payload.

Ví dụ, `OrderCreated` có thể thay đổi qua nhiều phiên bản:

```text
orderCreated
  version 1: orderId, createdAt
  version 2: orderId, createdAt, channel
```

Cả hai vẫn có thể dùng cùng type token `orderCreated`, nhưng consumer cần hiểu field mới là tùy chọn hay bắt buộc và cách xử lý record cũ. Có thể thêm `schemaVersion` trong payload hoặc header riêng, duy trì tương thích ngược và triển khai producer/consumer theo thứ tự phù hợp.

Với hệ thống dùng Avro, Protobuf hoặc JSON Schema cùng Schema Registry, schema ID/version và cơ chế tương thích của registry là nguồn metadata schema riêng. Spring Kafka type headers không thay thế các cơ chế đó.

## 10. Những nhầm lẫn thường gặp

1. **Cho rằng `__TypeId__` là field trong JSON.** Đây là Kafka header, nằm ngoài record value.
2. **Cho rằng mọi producer đều gửi type header.** Producer không dùng Spring Kafka hoặc đã tắt type headers có thể không gửi chúng.
3. **Cho rằng type mapping chỉ cần cấu hình ở producer.** Consumer cần mapping tương ứng để chuyển token thành lớp Java.
4. **Dùng tên lớp đầy đủ làm hợp đồng lâu dài giữa dịch vụ.** Refactor package có thể làm consumer không deserialize được; token mapping ổn định giúp giảm phụ thuộc.
5. **Tin mọi package bằng wildcard.** Hãy giới hạn trusted packages ở các DTO/event contract cần thiết.
6. **Cho rằng default type xử lý được topic đa hình.** Một default type chỉ phù hợp khi payload có cùng kiểu hoặc consumer có chiến lược chuyển đổi riêng.
7. **Cho rằng type header cũng là schema version.** Kiểu Java và phiên bản hợp đồng là hai khái niệm riêng.
8. **Cho rằng header chắc chắn còn trong listener.** JsonDeserializer có thể loại bỏ type headers sau khi dùng; cấu hình `spring.json.remove.type.headers` nếu cần giữ lại.

Type headers giúp Spring Kafka chuyển JSON bytes thành đúng kiểu Java mà không phải nhúng tên lớp vào payload. Hãy dùng type mapping để ổn định hợp đồng giữa producer và consumer, cấu hình trusted packages theo nguyên tắc tối thiểu và chọn default type hoặc tắt type headers khi topic có một kiểu payload cố định. Với topic chứa nhiều loại sự kiện, cần thống nhất mapping và versioning để các dịch vụ deserialize được dữ liệu một cách an toàn qua nhiều lần triển khai.
