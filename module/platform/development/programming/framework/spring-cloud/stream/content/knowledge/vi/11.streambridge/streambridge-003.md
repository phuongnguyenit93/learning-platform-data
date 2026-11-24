# Gửi POJO hoặc Message và chỉ định contentType

`StreamBridge` cho phép một thành phần Java gửi dữ liệu vào output binding của Spring Cloud Stream mà không cần biến thành phần đó thành `Supplier` hoặc `Function`. Dữ liệu gửi có thể là một POJO (Plain Old Java Object) hoặc một Spring `Message<?>`. Khi gửi, ứng dụng cần xác định định dạng nội dung để binder và consumer hiểu đúng payload. Với JSON, có thể khai báo `content-type` ở binding, truyền `MimeType` trực tiếp vào `StreamBridge.send`, hoặc đặt content type trong header của `Message`.

Ba cách này phục vụ những tình huống khác nhau. Cấu hình ở binding phù hợp khi một output luôn dùng cùng định dạng; overload nhận `MimeType` phù hợp khi lệnh gửi cần chỉ định định dạng ngay tại chỗ; header của `Message` phù hợp khi cần gắn định dạng và metadata cùng payload. Hãy chọn một nguồn cấu hình rõ ràng cho mỗi message, tránh để các giá trị content type mâu thuẫn.

## 1. StreamBridge gửi dữ liệu từ mã imperative

Trong mô hình hàm, Spring Cloud Stream kết nối `Supplier`, `Function` hoặc `Consumer` với binding. Nhưng một số luồng gửi sự kiện bắt đầu từ REST controller, service nghiệp vụ, scheduled task hoặc callback. `StreamBridge` cung cấp API để gửi dữ liệu từ những thành phần imperative đó vào output binding.

Ví dụ DTO sự kiện:

```java
public record OrderCreated(
    String eventId,
    String orderId,
    long total
) {}

public record OrderStatusChanged(
    String eventId,
    String orderId,
    String status
) {}
```

Khai báo và inject `StreamBridge`:

```java
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {
    private final StreamBridge streamBridge;

    public OrderEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }
}
```

Phương thức `send` nhận tên output binding và dữ liệu cần gửi. Kết quả boolean cho biết thao tác gửi qua binding/channel trong ứng dụng có được chấp nhận hay không; không nên xem riêng giá trị `true` là xác nhận broker đã lưu bền vững message.

## 2. Gửi POJO trực tiếp

Nếu binding đã được cấu hình `content-type: application/json`, có thể gửi POJO trực tiếp:

```java
public boolean publish(OrderCreated event) {
    return streamBridge.send("orders-out-0", event);
}
```

Cấu hình binding:

```yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.created
          content-type: application/json
```

Trong ví dụ, `orders-out-0` là tên binding trong ứng dụng; `orders.created` là destination mà binder ánh xạ đến topic, exchange hoặc topic tương ứng của broker. `event` là payload POJO. Message converter dùng content type của binding để chuyển đổi payload sang định dạng được cấu hình trước khi gửi.

Khi gửi POJO, Spring Cloud Stream tạo message cho binding. Ứng dụng không cần tự tạo `Message<?>` nếu không cần thêm headers hoặc metadata. Cách này phù hợp khi chỉ gửi payload và mọi message trên binding đều dùng cùng định dạng.

## 3. Chỉ định contentType bằng overload của StreamBridge

Khi cần chọn định dạng ngay tại lệnh gửi, dùng overload nhận `MimeType`:

```java
import org.springframework.util.MimeTypeUtils;

public boolean publishJson(OrderCreated event) {
    return streamBridge.send(
        "orders-out-0",
        MimeTypeUtils.APPLICATION_JSON,
        event
    );
}
```

Tham số thứ hai là `MimeType`, tham số thứ ba là dữ liệu cần gửi. `MimeTypeUtils.APPLICATION_JSON` biểu thị `application/json`. Các hằng số khác trong `MimeTypeUtils` có thể dùng cho định dạng văn bản hoặc dữ liệu nhị phân phù hợp, ví dụ `TEXT_PLAIN` và `APPLICATION_OCTET_STREAM`.

Nếu dùng định dạng văn bản, payload cũng cần có kiểu phù hợp:

```java
public boolean publishStatus(String status) {
    return streamBridge.send(
        "status-out-0",
        MimeTypeUtils.TEXT_PLAIN,
        status
    );
}
```

Định dạng được chỉ định phải phù hợp với kiểu payload và converter có sẵn. Gắn `application/json` vào một chuỗi văn bản không chứa JSON hợp lệ không tự biến chuỗi đó thành JSON object. Tương tự, `application/octet-stream` thường phù hợp với payload `byte[]` hoặc dữ liệu nhị phân mà consumer biết cách đọc.

Overload có `MimeType` hữu ích khi cùng một thành phần gửi nhiều kiểu dữ liệu hoặc khi định dạng cần được quyết định tại thời điểm chạy. Nếu một binding luôn dùng JSON, khai báo `content-type` tại binding thường dễ quản lý hơn và tránh lặp lại ở mọi lời gọi.

## 4. Gửi Message để mang theo headers

Khi cần event ID, correlation ID hoặc metadata riêng, tạo Spring `Message<T>` bằng `MessageBuilder`:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageBuilder;
import org.springframework.messaging.MessageHeaders;
import org.springframework.util.MimeTypeUtils;

public boolean publishWithHeaders(OrderCreated event) {
    Message<OrderCreated> message = MessageBuilder
        .withPayload(event)
        .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
        .setHeader("eventId", event.eventId())
        .setHeader("correlationId", "corr-42")
        .build();

    return streamBridge.send("orders-out-0", message);
}
```

`Message<T>` gồm hai phần:

- `payload`: dữ liệu nghiệp vụ, ở đây là `OrderCreated`.
- `headers`: metadata đi kèm, ở đây có content type, event ID và correlation ID.

`MessageHeaders.CONTENT_TYPE` là tên header chuẩn của Spring Messaging dành cho content type. Giá trị nên là `MimeType`, chẳng hạn `MimeTypeUtils.APPLICATION_JSON`. Các header tùy chỉnh cần dùng tên ổn định và kiểu dữ liệu mà binder có thể ánh xạ.

Khi gửi `Message<?>`, hãy chỉ thêm các header cần thiết. Không sao chép toàn bộ header từ HTTP request hoặc một message bên ngoài nếu chưa lọc, vì chúng có thể chứa token, cookie, dữ liệu cá nhân hoặc metadata nội bộ không phù hợp để phát tán qua broker.

## 5. Chọn cách đặt contentType

Ba cách phổ biến có thể so sánh như sau:

| Cách | Ví dụ | Khi nên dùng |
|---|---|---|
| Cấu hình binding | `content-type: application/json` | Mọi message trên binding dùng cùng định dạng |
| Overload `StreamBridge.send` | `send(binding, MimeTypeUtils.APPLICATION_JSON, event)` | Định dạng được quyết định tại điểm gửi |
| Header trong `Message` | `setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)` | Message cần mang content type cùng các headers khác |

Không nên cấu hình ba nguồn khác nhau với các giá trị không thống nhất. Ví dụ, binding khai báo JSON nhưng message header lại khai báo `text/plain` sẽ khiến người đọc khó biết hợp đồng dự kiến và có thể làm converter chọn cách xử lý khác với mong đợi. Hãy đặt content type nhất quán và kiểm thử hành vi thực tế của phiên bản Spring Cloud Stream/binder đang dùng.

Một quy tắc dễ bảo trì là:

- Dùng content type ở binding cho output chuyên biệt, có định dạng cố định.
- Dùng overload nhận `MimeType` khi một điểm gửi có nhiều loại payload/định dạng.
- Dùng header trong `Message` khi message cần mang metadata tường minh và caller chịu trách nhiệm xây dựng message.

## 6. Binding tĩnh và destination động

Tên truyền vào `StreamBridge.send` là tên output binding. Nếu binding đã khai báo, Spring Cloud Stream sử dụng binding đó và các thuộc tính như destination, binder, content type, partitioning và producer settings.

Ví dụ binding tĩnh:

```yaml
spring:
  cloud:
    stream:
      bindings:
        audit-out-0:
          destination: audit.events
          content-type: application/json
```

```java
streamBridge.send("audit-out-0", auditEvent);
```

Nếu tên binding chưa tồn tại, `StreamBridge` có thể tạo dynamic output binding. Trong trường hợp đó, tên đích được dùng để tạo binding động theo cơ chế của framework. Ví dụ:

```java
streamBridge.send("tenant-events", MimeTypeUtils.APPLICATION_JSON, event);
```

Dynamic destination hữu ích khi đích gửi được xác định tại runtime, nhưng không nên cho phép dữ liệu đầu vào tùy ý quyết định tên topic/queue. Hãy kiểm soát danh sách destination được phép và cấu hình binder tương ứng. Với đích biết trước, binding tĩnh giúp cấu hình, phân quyền, quan sát và triển khai dễ dự đoán hơn.

Có thể tạo binding động trước khi gửi bằng cấu hình `spring.cloud.stream.output-bindings` nếu ứng dụng cần khởi tạo output binding xác định lúc startup. Cú pháp và cách kết hợp với các binding khác cần được xác nhận theo phiên bản framework đang dùng.

## 7. Message conversion và native encoding

Chỉ định `contentType` chủ yếu cung cấp thông tin cho message conversion của Spring Cloud Stream. Nó không tự cấu hình Kafka serializer, RabbitMQ converter native hoặc Pulsar schema nếu binding đang sử dụng native encoding.

Phân biệt hai trường hợp:

**Dùng message conversion:** POJO được chuyển đổi theo content type, ví dụ JSON. Producer và consumer cần thống nhất content type và converter/schema tương ứng.

**Dùng native encoding:** binder/client sử dụng serializer riêng của broker. Khi đó phải cấu hình serializer/deserializer tương ứng ở phần mở rộng binder. Chỉ đặt `contentType` không thay thế được cấu hình serializer native.

Ví dụ output binding dùng native encoding với Kafka:

```yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.created
          producer:
            use-native-encoding: true
      kafka:
        bindings:
          orders-out-0:
            producer:
              configuration:
                key.serializer: org.apache.kafka.common.serialization.StringSerializer
                value.serializer: org.apache.kafka.common.serialization.StringSerializer
```

Ví dụ này giả định producer gửi giá trị dạng chuỗi phù hợp với `StringSerializer`; nếu gửi POJO, cần serializer hỗ trợ kiểu POJO hoặc chuyển payload thành dạng tương ứng trước khi gửi. Không dùng `StringSerializer` cho một object tùy ý.

Với RabbitMQ và Pulsar, native conversion/schema có cấu hình riêng. Hãy kiểm tra tài liệu binder và phiên bản client. `MimeType` không làm cho một serializer native không tương thích trở nên tương thích.

## 8. Ví dụ hoàn chỉnh: gửi sự kiện đơn hàng

Một publisher có thể hỗ trợ cả cách gửi POJO và `Message`:

```java
import java.util.UUID;
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageBuilder;
import org.springframework.messaging.MessageHeaders;
import org.springframework.stereotype.Service;
import org.springframework.util.MimeTypeUtils;

@Service
public class OrderEventPublisher {
    private final StreamBridge streamBridge;

    public OrderEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(OrderCreated event) {
        return streamBridge.send("orders-out-0", event);
    }

    public boolean publishWithMetadata(OrderCreated event, String correlationId) {
        Message<OrderCreated> message = MessageBuilder
            .withPayload(event)
            .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
            .setHeader("eventId", event.eventId())
            .setHeader("correlationId", correlationId)
            .setHeader("publisher", "order-service")
            .build();

        return streamBridge.send("orders-out-0", message);
    }

    public boolean publishStatus(String orderId, String status) {
        OrderStatusChanged event = new OrderStatusChanged(
            UUID.randomUUID().toString(), orderId, status);

        return streamBridge.send(
            "order-status-out-0",
            MimeTypeUtils.APPLICATION_JSON,
            event
        );
    }
}
```

Cấu hình tương ứng:

```yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.created
          content-type: application/json
        order-status-out-0:
          destination: orders.status
          content-type: application/json
```

Hai binding đều dùng JSON. Phương thức `publish` gửi POJO và dựa vào content type của binding. `publishWithMetadata` gửi `Message<OrderCreated>` để mang theo headers. `publishStatus` chỉ định content type bằng overload của `StreamBridge.send`. Trong ứng dụng thực tế, có thể chọn một phong cách nhất quán thay vì giữ nhiều cách gửi nếu không có nhu cầu rõ ràng.

## 9. Kiểm tra kết quả gửi và xử lý lỗi

`StreamBridge.send` trả về boolean. Hãy kiểm tra kết quả và ghi log có ngữ cảnh khi binding không chấp nhận message:

```java
boolean accepted = streamBridge.send("orders-out-0", event);
if (!accepted) {
    throw new IllegalStateException("Output binding did not accept the order event");
}
```

Kết quả `true` cho biết message đã được chấp nhận qua đường gửi của ứng dụng. Với gửi bất đồng bộ, lỗi publish ở broker có thể được báo qua cơ chế lỗi của binder sau thời điểm lời gọi trả về. Cần cấu hình quan sát và xử lý lỗi phù hợp; không trả lời API gọi vào rằng nghiệp vụ đã được broker lưu bền vững chỉ dựa vào boolean.

Nếu gửi message sau khi cập nhật cơ sở dữ liệu, cân nhắc transactional outbox để tránh trường hợp database commit nhưng publish thất bại. Nếu producer retry có thể phát trùng, gắn event ID ổn định và thiết kế consumer idempotent.

## 10. Kiểm thử POJO, Message và contentType

Kiểm thử cần xác nhận cả payload lẫn metadata:

- Gửi POJO qua binding có `content-type: application/json` và xác nhận consumer nhận đúng DTO.
- Gửi POJO bằng overload `send(binding, MimeType, data)` và xác nhận định dạng được xử lý đúng.
- Gửi `Message<T>` có `MessageHeaders.CONTENT_TYPE` và các header nghiệp vụ; xác nhận header cần thiết được giữ qua binder.
- Thử content type không phù hợp với payload để bảo đảm lỗi conversion được phát hiện.
- Kiểm tra một message có header content type xung đột với cấu hình binding và xác định quy tắc thực tế của phiên bản đang dùng.
- Kiểm thử destination động với danh sách destination được phép; xác nhận không thể gửi đến destination ngoài chính sách.
- Kiểm thử với Kafka, RabbitMQ hoặc Pulsar thật khi cần xác minh native encoding, header mapping, durability và lỗi broker.

Test Binder hữu ích để kiểm tra logic function và binding trong phạm vi ứng dụng. Nó không chứng minh mọi serializer, converter hoặc header mapper của broker thật hoạt động giống nhau. Với luồng quan trọng, hãy bổ sung integration test bằng đúng binder và broker production.

## 11. Checklist trước khi gửi message

- [ ] Đã chọn đúng tên output binding và destination.
- [ ] Payload POJO có kiểu rõ ràng và có thể serialize.
- [ ] Content type ở binding, overload hoặc message header được chọn nhất quán.
- [ ] Nếu gửi `Message<?>`, chỉ đưa các header cần thiết và đã kiểm tra.
- [ ] Đã xác định binding dùng message conversion hay native encoding.
- [ ] Nếu dùng native encoding, serializer của binder phù hợp với kiểu payload.
- [ ] Consumer có converter/deserializer và schema tương thích.
- [ ] Đã kiểm tra boolean trả về và cấu hình quan sát lỗi publish bất đồng bộ.
- [ ] Đã kiểm thử payload, content type và headers với binder thực tế.

`StreamBridge` giúp gửi POJO hoặc `Message<?>` từ bất kỳ thành phần imperative nào của ứng dụng. Khi chọn content type đúng ở binding, overload `MimeType` hoặc header của message, producer và consumer có thể thống nhất cách diễn giải payload. Hãy giữ wire contract rõ ràng, chỉ truyền metadata cần thiết và kiểm thử qua binder thực tế để message đến được consumer dưới đúng định dạng mong đợi.
