# Cấu trúc `Message<T>`: payload, header và tính bất biến

Trong Spring Cloud Stream, một sự kiện có thể được truyền qua hàm dưới dạng payload thuần hoặc dưới dạng `Message<T>`. `Message<T>` là một hợp đồng của Spring Messaging gồm hai phần: **payload** chứa dữ liệu nghiệp vụ và **headers** chứa metadata mô tả thông điệp. Khi dùng `Message<T>`, hàm có thể đọc thông tin như mã tương quan, nguồn phát, loại sự kiện hoặc thời điểm tạo, đồng thời quyết định metadata nào cần được giữ khi tạo message tiếp theo.

Hiểu đúng tính bất biến của message rất quan trọng khi xử lý luồng sự kiện. Spring cung cấp API để tạo message mới và xây dựng header mới thay vì sửa trực tiếp message đã nhận. Tuy nhiên, tính bất biến của cấu trúc message không tự động làm cho object payload hoặc các object được lưu trong header trở thành bất biến.

## 1. Cấu trúc của Message<T>

`org.springframework.messaging.Message<T>` là interface biểu diễn một thông điệp. Nó cung cấp hai thành phần chính:

| Thành phần | API | Vai trò |
| --- | --- | --- |
| Payload | `getPayload()` | Dữ liệu chính mà ứng dụng muốn trao đổi, ví dụ một `OrderCreated` hoặc chuỗi JSON. |
| Headers | `getHeaders()` | Tập hợp cặp khóa/giá trị mô tả message, ví dụ `correlationId`, `contentType` hoặc thông tin nguồn phát. |

Kiểu `T` là kiểu payload. Ví dụ `Message<OrderCreated>` nghĩa là payload có kiểu `OrderCreated`, còn headers vẫn là tập metadata của Spring Messaging.

```java
import org.springframework.messaging.Message;

void handle(Message<String> message) {
    String body = message.getPayload();
    Object correlationId = message.getHeaders().get("correlationId");

    System.out.println("Payload: " + body);
    System.out.println("Correlation: " + correlationId);
}
```

Nếu hàm chỉ cần xử lý dữ liệu nghiệp vụ và không cần đọc hoặc tạo metadata, có thể khai báo tham số là `OrderCreated` hoặc `String`. Spring Cloud Stream chuyển payload vào hàm. Khi cần truy cập header, khai báo tham số hoặc giá trị trả về là `Message<T>`.

## 2. Payload chứa dữ liệu nghiệp vụ

Payload là phần nội dung chính của message. Với một dịch vụ xử lý đơn hàng, payload có thể là một record:

```java
import java.math.BigDecimal;

public record OrderCreated(
        String orderId,
        String customerId,
        BigDecimal total
) {}
```

Một message có thể chứa payload `OrderCreated` và các header mô tả ngữ cảnh truyền tải:

```java
Message<OrderCreated> message = MessageBuilder
        .withPayload(new OrderCreated(
                "ORD-1001",
                "CUS-42",
                new BigDecimal("125000.00")
        ))
        .setHeader("correlationId", "corr-7f2a")
        .setHeader("source", "checkout-service")
        .build();
```

Trong ví dụ, `orderId`, `customerId` và `total` là dữ liệu nghiệp vụ nên nằm trong payload. `correlationId` giúp liên kết các thao tác thuộc cùng một luồng xử lý; `source` mô tả nơi phát sự kiện nên nằm trong header.

Không nên chuyển mọi thông tin thành header. Dữ liệu cần được lưu trữ, kiểm tra theo schema, tái sử dụng bởi consumer hoặc có ý nghĩa nghiệp vụ nên nằm trong payload. Header phù hợp với metadata phục vụ định tuyến, theo dõi, tương quan, định dạng và xử lý message.

## 3. Headers là metadata dạng khóa và giá trị

Headers cung cấp ngữ cảnh đi kèm payload mà không cần thay đổi cấu trúc dữ liệu nghiệp vụ. Một số header thường gặp:

| Header | Mục đích |
| --- | --- |
| `id` | Định danh message do Spring Messaging quản lý; message mới thường có ID mới. |
| `timestamp` | Thời điểm tạo message theo cơ chế của Spring Messaging, nếu có. |
| `contentType` | Gợi ý định dạng nội dung, ví dụ `application/json`; Spring Cloud Stream cũng có cấu hình content type ở binding. |
| `correlationId` | Liên kết message với request, workflow hoặc chuỗi sự kiện liên quan. |
| `traceparent` | Mang thông tin trace theo chuẩn W3C Trace Context khi hệ thống tích hợp tracing. |
| `source` hoặc `eventType` | Metadata do ứng dụng quy ước để mô tả nguồn phát hoặc loại sự kiện. |

`id` và `timestamp` là các header chuẩn của Spring Messaging. Những header như `correlationId`, `source` hoặc `eventType` thường là quy ước của ứng dụng; các dịch vụ tham gia luồng phải thống nhất tên, kiểu dữ liệu và ý nghĩa của chúng.

Header có thể được dùng để hỗ trợ định tuyến hoặc quan sát hệ thống, nhưng không nên trở thành nơi duy nhất lưu thông tin cần thiết để hiểu sự kiện. Consumer cần đọc payload theo schema đã thống nhất và chỉ phụ thuộc vào header khi hợp đồng sự kiện quy định rõ điều đó.

## 4. Tạo Message bằng MessageBuilder

Không nên tự triển khai `Message<T>` hoặc tự tạo một map header để thay thế API của Spring. `MessageBuilder` là cách thông dụng để tạo message mới.

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> message = MessageBuilder
        .withPayload("ORDER_CREATED")
        .setHeader("eventType", "OrderCreated")
        .setHeader("correlationId", "corr-7f2a")
        .build();
```

Các thao tác quan trọng của builder:

| API | Công dụng |
| --- | --- |
| `withPayload(payload)` | Bắt đầu tạo message với payload mới. |
| `setHeader(name, value)` | Đặt hoặc thay giá trị của một header. |
| `setHeaderIfAbsent(name, value)` | Chỉ đặt header nếu header đó chưa có. |
| `copyHeaders(map)` | Sao chép các header từ map vào builder. |
| `copyHeadersIfAbsent(map)` | Chỉ sao chép các header chưa được đặt. |
| `removeHeader(name)` | Loại bỏ một header khỏi message đang xây dựng. |
| `build()` | Tạo đối tượng `Message<T>` mới. |

Ví dụ, tạo message có header mặc định nếu upstream chưa cung cấp:

```java
Message<String> message = MessageBuilder
        .withPayload("ORDER_CREATED")
        .setHeaderIfAbsent("source", "order-service")
        .setHeaderIfAbsent("eventType", "OrderCreated")
        .build();
```

`setHeaderIfAbsent` hữu ích khi một thành phần trung gian bổ sung metadata mặc định mà vẫn giữ giá trị do thành phần trước đó cung cấp.

## 5. Tính bất biến của Message và MessageHeaders

`Message<T>` được thiết kế như một đối tượng message đã hình thành, còn `MessageHeaders` cung cấp tập header không cho phép thay đổi trực tiếp qua map API. Vì vậy, thao tác sau không phải cách cập nhật header hợp lệ:

```java
message.getHeaders().put("source", "new-service"); // Không hỗ trợ sửa trực tiếp
```

Map header của `MessageHeaders` là bất biến; thao tác sửa trực tiếp thường dẫn tới `UnsupportedOperationException`. Muốn thay đổi metadata, hãy tạo một message mới bằng builder:

```java
Message<String> updated = MessageBuilder
        .fromMessage(message)
        .setHeader("source", "new-service")
        .build();
```

`fromMessage(message)` khởi tạo builder từ message hiện có. Sau khi thay header và gọi `build()`, ứng dụng nhận được message mới; message ban đầu vẫn giữ nguyên header cũ.

Tính bất biến ở đây là tính bất biến của cấu trúc message và tập header. Nó không đồng nghĩa với deep immutability:

- Nếu payload là một object mutable, code vẫn có thể thay đổi trạng thái bên trong object đó sau khi message được tạo.
- Nếu một header chứa object mutable, object đó vẫn có thể bị thay đổi thông qua tham chiếu khác.
- Việc tạo message mới không tự động sao chép sâu payload hoặc mọi giá trị header.

Do đó, nên ưu tiên payload dạng immutable như Java record hoặc value object không có setter. Với metadata, ưu tiên chuỗi, số, enum hoặc kiểu giá trị ổn định. Nếu buộc phải dùng object mutable, cần quản lý quyền sở hữu và tránh chia sẻ tham chiếu có thể bị sửa đồng thời.

## 6. Biến đổi payload và giữ lại header cần thiết

Khi một hàm nhận message và tạo một payload có kiểu khác, hãy tạo message mới và chủ động chọn header cần chuyển tiếp. Không nên mặc định rằng mọi header nội bộ của Spring hoặc binder đều cần được phát ra destination tiếp theo.

Ví dụ, chuyển `OrderCreated` thành `OrderAccepted` và giữ lại `correlationId`:

```java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public record OrderAccepted(String orderId, String status) {}

@Bean
public Function<Message<OrderCreated>, Message<OrderAccepted>> acceptOrder() {
    return input -> {
        OrderCreated order = input.getPayload();
        Object correlationId = input.getHeaders().get("correlationId");

        OrderAccepted result = new OrderAccepted(
                order.orderId(),
                "ACCEPTED"
        );

        return MessageBuilder.withPayload(result)
                .setHeader("correlationId", correlationId)
                .setHeader("eventType", "OrderAccepted")
                .setHeader("source", "order-service")
                .build();
    };
}
```

Hàm đọc payload bằng `getPayload()`, lấy metadata cần giữ từ `getHeaders()` và tạo message mới. Cách làm này làm rõ hợp đồng của message đầu ra: chỉ có `correlationId`, `eventType` và `source` được chủ động đưa vào message mới.

Nếu muốn giữ nhiều header từ message cũ, có thể dùng `copyHeaders(input.getHeaders())`, sau đó ghi đè hoặc loại bỏ những header không phù hợp. Hãy cân nhắc kỹ trước khi sao chép toàn bộ header, vì một số header chỉ có ý nghĩa trong context nội bộ hoặc chứa kiểu dữ liệu không thể serialize sang broker.

## 7. Đọc, thêm, thay thế và loại bỏ header

Đọc header:

```java
Object value = message.getHeaders().get("correlationId");
String correlationId = value instanceof String text ? text : null;
```

Đặt hoặc thay header bằng builder:

```java
Message<String> updated = MessageBuilder.fromMessage(message)
        .setHeader("source", "billing-service")
        .build();
```

Chỉ thêm nếu chưa tồn tại:

```java
Message<String> updated = MessageBuilder.fromMessage(message)
        .setHeaderIfAbsent("source", "billing-service")
        .build();
```

Loại bỏ header:

```java
Message<String> sanitized = MessageBuilder.fromMessage(message)
        .removeHeader("temporaryDebugInfo")
        .build();
```

Các ví dụ trên đều tạo message mới. Hãy tránh gọi `put`, `remove` hoặc các thao tác thay đổi trực tiếp trên `message.getHeaders()`.

## 8. Sử dụng Message<T> trong Supplier, Function và Consumer

Spring Cloud Stream cho phép các hàm làm việc trực tiếp với `Message<T>` khi cần điều khiển payload và header.

### Supplier phát message có metadata

```java
import java.util.UUID;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Bean
public Supplier<Message<String>> orderEvents() {
    return () -> MessageBuilder.withPayload("ORDER_CREATED")
            .setHeader("eventType", "OrderCreated")
            .setHeader("correlationId", UUID.randomUUID().toString())
            .build();
}
```

Mỗi lần supplier tạo message, payload và metadata được đóng gói cùng nhau. Với ứng dụng thực tế, payload thường là một DTO hoặc record thay vì chuỗi minh họa.

### Function đọc và tạo message mới

```java
@Bean
public Function<Message<OrderCreated>, Message<OrderAccepted>> acceptOrder() {
    return input -> {
        OrderCreated order = input.getPayload();
        return MessageBuilder.withPayload(
                    new OrderAccepted(order.orderId(), "ACCEPTED"))
                .setHeader("correlationId",
                        input.getHeaders().get("correlationId"))
                .build();
    };
}
```

### Consumer đọc payload và header

```java
import java.util.function.Consumer;

@Bean
public Consumer<Message<OrderCreated>> auditOrder() {
    return message -> {
        OrderCreated order = message.getPayload();
        Object correlationId = message.getHeaders().get("correlationId");

        System.out.printf("Order %s, correlation %s%n",
                order.orderId(), correlationId);
    };
}
```

Nếu consumer không cần metadata, có thể nhận trực tiếp `OrderCreated`. Dùng `Message<T>` khi header là một phần thực sự cần thiết của xử lý.

## 9. Header khi đi qua broker

Header trong `Message<T>` là metadata ở tầng Spring Messaging. Khi message được gửi qua Kafka, RabbitMQ hoặc Pulsar, binder phải ánh xạ header sang metadata mà broker hỗ trợ. Cách ánh xạ, kiểu dữ liệu được hỗ trợ và những header được truyền qua có thể khác nhau giữa binder và phiên bản.

Một số điểm cần lưu ý:

- Header có giá trị là chuỗi hoặc kiểu scalar thường dễ ánh xạ và tương thích hơn object Java tùy chỉnh.
- Header chứa object không serialize được có thể bị loại bỏ, gây lỗi gửi message hoặc không thể đọc ở consumer, tùy binder.
- Một số header là nội bộ của Spring Integration, Spring Messaging hoặc binder; chúng không nhất thiết là metadata nghiệp vụ để gửi qua broker.
- Broker có giới hạn riêng về kích thước header hoặc metadata. Không nên đưa payload lớn vào header.
- Header như `contentType`, partition key hoặc correlation metadata có thể được binder xử lý đặc biệt; cần dùng đúng quy ước của binder.

Không nên giả định rằng mọi header trong message đầu vào sẽ tự động xuất hiện nguyên vẹn ở message đầu ra hoặc ở consumer thuộc một dịch vụ khác. Nếu hợp đồng sự kiện cần một metadata cụ thể, hãy kiểm thử việc ánh xạ header qua đúng broker và cấu hình binder.

## 10. Payload schema và content type

Payload và header phối hợp để consumer diễn giải dữ liệu. Payload xác định nội dung, còn content type mô tả định dạng để framework hoặc consumer chuyển đổi đúng cách. Ví dụ, JSON có thể được khai báo bằng cấu hình binding:

```yaml
spring:
  cloud:
    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders.created
          content-type: application/json
        acceptOrder-out-0:
          destination: orders.accepted
          content-type: application/json
```

Với `Message<T>`, header `contentType` có thể tham gia quá trình chuyển đổi message. Tuy nhiên, nên quản lý content type qua cấu hình binding hoặc quy ước của framework thay vì tự đặt một giá trị mâu thuẫn với cấu hình. Schema của payload vẫn cần được thiết kế có phiên bản và có quy tắc tương thích khi producer và consumer được triển khai độc lập.

Không nên dùng header `eventType` thay cho schema payload. `eventType` có thể giúp phân loại sự kiện, nhưng consumer vẫn cần hiểu cấu trúc payload và cách xử lý khi schema thay đổi.

## 11. Quy tắc thiết kế header an toàn

Một bộ quy ước header rõ ràng giúp các dịch vụ phối hợp tốt hơn:

1. **Đặt tên nhất quán:** dùng tên dễ hiểu và thống nhất cách viết, ví dụ `correlationId`, `eventType`, `source`.
2. **Quy định kiểu dữ liệu:** thống nhất `String`, số hoặc kiểu scalar cho từng header; tránh để producer gửi kiểu tùy ý.
3. **Tách metadata khỏi dữ liệu nghiệp vụ:** thông tin cần lưu trữ hoặc xác thực theo schema nên thuộc payload.
4. **Giữ metadata cần thiết:** khi biến đổi message, chỉ sao chép header có ý nghĩa với luồng tiếp theo.
5. **Tránh thông tin nhạy cảm:** không đưa access token, mật khẩu hoặc dữ liệu cá nhân không cần thiết vào header vì metadata có thể xuất hiện trong log và công cụ quan sát.
6. **Không dựa vào thứ tự header:** header là tập khóa/giá trị; ứng dụng không nên dựa vào thứ tự khi duyệt.
7. **Giới hạn kích thước:** metadata nên nhỏ để tránh vượt giới hạn broker và làm tăng chi phí truyền tải.
8. **Kiểm thử khả năng truyền qua broker:** xác nhận header thực sự được giữ và có kiểu dữ liệu như hợp đồng yêu cầu.

Đặc biệt, không dùng một header có thể bị producer tùy ý thay đổi làm căn cứ duy nhất cho quyết định phân quyền hoặc xác thực. Những quyết định bảo mật cần dựa trên nguồn danh tính đáng tin cậy và cơ chế xác thực phù hợp.

## 12. Kiểm thử tính bất biến và header

Kiểm thử nên xác nhận payload, header và hành vi tạo message mới. Ví dụ với JUnit:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class MessageHeaderTest {

    @Test
    void createsNewMessageWhenHeaderChanges() {
        Message<String> original = MessageBuilder.withPayload("ORDER_CREATED")
                .setHeader("source", "checkout")
                .build();

        Message<String> updated = MessageBuilder.fromMessage(original)
                .setHeader("source", "order-service")
                .build();

        assertEquals("checkout", original.getHeaders().get("source"));
        assertEquals("order-service", updated.getHeaders().get("source"));
        assertEquals("ORDER_CREATED", updated.getPayload());
        assertNotEquals(original, updated);
    }
}
```

Kiểm thử này xác nhận message ban đầu vẫn giữ header cũ trong khi message mới có header đã thay đổi. Có thể bổ sung kiểm thử cho trường hợp header vắng mặt, `setHeaderIfAbsent`, loại bỏ header và chuyển tiếp `correlationId`.

Test binder giúp kiểm tra luồng message trong ứng dụng mà không cần broker thật. Để xác nhận header được ánh xạ đúng qua Kafka, RabbitMQ hoặc Pulsar, cần có kiểm thử tích hợp với binder và broker tương ứng. Những khác biệt về header mapping, serialization và giới hạn metadata chỉ có thể được xác nhận đầy đủ ở tầng tích hợp.

## Kết luận

`Message<T>` kết hợp payload chứa dữ liệu nghiệp vụ với headers chứa metadata. `MessageHeaders` không cho phép sửa map trực tiếp; `MessageBuilder` tạo message mới để đặt, sao chép hoặc loại bỏ header. Tính bất biến này áp dụng cho cấu trúc message, không tự động bảo vệ trạng thái bên trong payload hay object header mutable. Khi dùng Spring Cloud Stream, hãy chọn header có ý nghĩa, kiểm soát việc chuyển tiếp metadata và kiểm thử ánh xạ qua binder để message giữ đúng hợp đồng giữa các dịch vụ.
