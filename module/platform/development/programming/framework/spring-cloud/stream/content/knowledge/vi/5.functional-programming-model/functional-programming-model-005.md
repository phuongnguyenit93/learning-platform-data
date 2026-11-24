# Xử lý payload trực tiếp và xử lý Message<T>

## Mục tiêu

Trong mô hình hàm của Spring Cloud Stream, một hàm có thể nhận trực tiếp đối tượng nghiệp vụ như `OrderCreated`, hoặc nhận một `Message<OrderCreated>` gồm payload và metadata. Cả hai cách đều hợp lệ, nhưng chúng phục vụ nhu cầu khác nhau. Chọn đúng chữ ký hàm giúp code dễ đọc, giữ được thông tin cần thiết từ broker và tránh để metadata truyền tin lan vào logic nghiệp vụ.

Bài học này giải thích cấu trúc của `Message<T>`, cách Spring Cloud Stream chuyển đổi payload theo kiểu đích và content type, cách đọc hoặc tạo headers, cũng như cách chọn giữa payload trực tiếp và message đầy đủ khi dùng `Supplier`, `Function` và `Consumer`.

Sau bài học, bạn có thể:

- Phân biệt payload và headers trong một Spring Message.
- Viết Consumer và Function nhận payload trực tiếp hoặc `Message<T>`.
- Đọc metadata như event ID, correlation ID và tenant ID ở biên tích hợp.
- Tạo message đầu ra với headers được chọn lọc.
- Cấu hình content type và kiểm thử việc chuyển đổi payload/header.

## 1. Payload và Message là hai phần khác nhau

Spring Messaging biểu diễn một message bằng hai thành phần:

- **Payload** là dữ liệu chính mà ứng dụng cần xử lý, ví dụ một đơn hàng vừa được tạo.
- **Headers** là metadata đi kèm, ví dụ content type, correlation ID, tenant ID, thời điểm phát sinh hoặc thông tin định tuyến.

Kiểu `Message<T>` giữ payload có kiểu `T` cùng tập headers:

```java
public record OrderCreated(
        String eventId,
        String orderId,
        BigDecimal total
) {}
```

Một message có thể chứa đối tượng này và các header:

```java
Message<OrderCreated> message = MessageBuilder
        .withPayload(new OrderCreated(
                "evt-100", "order-42", new BigDecimal("125.50")
        ))
        .setHeader("correlationId", "corr-900")
        .setHeader("tenantId", "tenant-a")
        .build();
```

Trong ví dụ này, `OrderCreated` là payload. `correlationId` và `tenantId` là metadata. Một số metadata như content type có thể ảnh hưởng đến việc chuyển đổi dữ liệu; một số header khác chỉ phục vụ quan sát, truy vết hoặc định tuyến.

`Message<T>` là abstraction của Spring Messaging. Nó không phải bản sao nguyên trạng của một record Kafka, RabbitMQ hay Pulsar. Binder chuyển đổi giữa message của framework và giao thức của broker, đồng thời có thể ánh xạ hoặc chuẩn hóa headers theo khả năng của binder.

## 2. Nhận trực tiếp payload

Khi nghiệp vụ chỉ cần dữ liệu trong payload, khai báo hàm nhận kiểu payload:

```java
@Bean
Consumer<OrderCreated> orderCreated(OrderService service) {
    return event -> service.createOrder(
            event.orderId(),
            event.total()
    );
}
```

Đây là dạng đơn giản và thường nên dùng. Spring Cloud Stream nhận message từ binding, chuyển payload sang kiểu `OrderCreated` theo content type và kiểu tham số hàm, rồi gọi Consumer. Code xử lý không phải đọc `getPayload()` ở mọi nơi.

Function cũng có thể nhận và trả về payload trực tiếp:

```java
@Bean
Function<OrderCreated, OrderAccepted> acceptOrder(OrderService service) {
    return event -> service.accept(event);
}
```

Với Supplier, ứng dụng tạo dữ liệu đầu ra:

```java
@Bean
Supplier<Heartbeat> heartbeat() {
    return () -> new Heartbeat("inventory-service", Instant.now());
}
```

Khi dùng payload trực tiếp, framework quản lý message envelope và quá trình chuyển đổi. Cách này phù hợp khi:

- Logic chỉ cần các trường trong payload.
- Không cần đọc metadata của lần giao nhận.
- Đầu ra có thể được biểu diễn bằng một đối tượng nghiệp vụ hoặc DTO rõ ràng.
- Muốn giữ chữ ký hàm ngắn gọn và dễ kiểm thử.

Không nên thêm headers vào payload chỉ để thay thế metadata của message. Ví dụ, correlation ID hoặc thông tin định tuyến thường không phải một phần của hợp đồng nghiệp vụ `OrderCreated`.

## 3. Nhận Message<T> khi cần metadata

Khi xử lý cần cả payload lẫn metadata, khai báo tham số là `Message<T>`:

```java
@Bean
Consumer<Message<OrderCreated>> orderCreated(
        OrderService service) {
    return message -> {
        OrderCreated event = message.getPayload();

        String correlationId = message.getHeaders()
                .get("correlationId", String.class);

        service.createOrder(
                event.orderId(),
                event.total(),
                correlationId
        );
    };
}
```

Kiểu generic `Message<OrderCreated>` giúp payload vẫn có kiểu cụ thể. Ứng dụng có thể truy cập:

- `message.getPayload()` để lấy dữ liệu chính.
- `message.getHeaders()` để đọc metadata.
- `message.getHeaders().get(key, Type.class)` để lấy header theo kiểu mong đợi.

Nếu header không bắt buộc, hãy xử lý trường hợp thiếu rõ ràng:

```java
String correlationId = message.getHeaders()
        .get("correlationId", String.class);

if (correlationId == null || correlationId.isBlank()) {
    correlationId = "untracked";
}
```

Giá trị mặc định chỉ phù hợp khi nghiệp vụ và observability cho phép. Nếu header là bắt buộc, chẳng hạn tenant ID dùng để xác định phạm vi dữ liệu, adapter phải từ chối message thiếu hoặc sai giá trị trước khi gọi use case. Không dùng một giá trị mặc định chung để vô tình đưa message vào sai tenant.

### Message<T> vẫn có payload được chuyển đổi

Dùng `Message<OrderCreated>` không có nghĩa payload luôn là byte array hay chuỗi JSON. Spring Cloud Stream vẫn có thể chuyển payload sang kiểu `OrderCreated` dựa trên thông tin content type và chữ ký hàm. Phần khác biệt là hàm nhận cả envelope để đọc metadata.

Ưu tiên kiểu generic cụ thể:

```java
Consumer<Message<OrderCreated>> typedHandler = message -> {
    OrderCreated event = message.getPayload();
};
```

Tránh dùng `Message<?>` hoặc `Message<Object>` nếu không thực sự cần xử lý nhiều kiểu payload. Kiểu quá rộng làm giảm thông tin kiểu đích cho conversion và khiến code phải ép kiểu hoặc kiểm tra kiểu lúc chạy.

## 4. Tạo Message đầu ra và chọn headers cần truyền

Một Function có thể nhận `Message<T>` và trả về `Message<R>`. Cách này hữu ích khi cần giữ một số metadata xuyên suốt quá trình xử lý:

```java
@Bean
Function<Message<OrderCreated>, Message<OrderAccepted>> acceptOrder(
        OrderService service) {
    return input -> {
        OrderCreated event = input.getPayload();
        OrderAccepted accepted = service.accept(event);

        String correlationId = input.getHeaders()
                .get("correlationId", String.class);

        return MessageBuilder
                .withPayload(accepted)
                .setHeader("correlationId", correlationId)
                .setHeader("eventId", event.eventId())
                .build();
    };
}
```

Function trả về message mới với payload đầu ra và một số header được chọn. Cách này làm rõ metadata nào được phép đi tiếp.

Có thể dùng `MessageBuilder.fromMessage(input)` để tạo message dựa trên message đầu vào:

```java
Message<OrderAccepted> output = MessageBuilder
        .fromMessage(input)
        .setPayload(accepted)
        .setHeader("processingStage", "validated")
        .build();
```

Cách này giữ lại các headers hiện có trừ khi chúng bị thay thế hoặc xóa. Chỉ dùng khi việc giữ nguyên các headers đó là có chủ đích. Message đầu vào có thể chứa metadata riêng của broker hoặc framework; sao chép tất cả sang message đầu ra có thể làm lộ thông tin nội bộ, mang theo header không còn đúng ngữ cảnh hoặc gây xung đột khi gửi qua binder khác.

Trong nhiều trường hợp, tạo message mới bằng `MessageBuilder.withPayload(...)` và chỉ đặt allowlist headers là lựa chọn dễ kiểm soát hơn. Chẳng hạn correlation ID, event ID và trace context có thể được truyền tiếp nếu chính sách hệ thống cho phép.

### Message đầu ra từ Supplier

Supplier cũng có thể tạo message khi nguồn phát cần gắn metadata:

```java
@Bean
Supplier<Message<Heartbeat>> heartbeat() {
    return () -> MessageBuilder
            .withPayload(new Heartbeat("inventory-service", Instant.now()))
            .setHeader("eventType", "service.heartbeat")
            .build();
}
```

Payload vẫn là dữ liệu heartbeat; `eventType` là metadata. Nếu header là một phần của hợp đồng trao đổi giữa nhiều dịch vụ, hãy ghi rõ tên, kiểu và quy tắc tương thích của nó, đồng thời kiểm tra binder có ánh xạ header đó ra broker như mong muốn hay không.

## 5. Chọn payload hay Message<T>?

| Nhu cầu | Chữ ký nên cân nhắc | Lý do |
|---|---|---|
| Chỉ xử lý dữ liệu nghiệp vụ | `Consumer<OrderCreated>` | Ngắn gọn, không phụ thuộc envelope |
| Cần correlation ID hoặc tenant metadata | `Consumer<Message<OrderCreated>>` | Đọc payload và headers ở biên |
| Biến đổi payload, không cần giữ metadata | `Function<OrderCreated, OrderAccepted>` | Tập trung vào dữ liệu vào/ra |
| Biến đổi payload và chủ động truyền một số headers | `Function<Message<OrderCreated>, Message<OrderAccepted>>` | Kiểm soát metadata đầu ra |
| Phát dữ liệu định kỳ, không cần metadata | `Supplier<Heartbeat>` | Cách khai báo đơn giản |
| Nguồn phát cần gắn event type hoặc correlation metadata | `Supplier<Message<Heartbeat>>` | Tạo cả payload và headers |

Một nguyên tắc thực tế: bắt đầu bằng payload trực tiếp. Chuyển sang `Message<T>` khi có yêu cầu cụ thể về metadata hoặc khi cần kiểm soát envelope đầu ra. Đừng chọn `Message<T>` chỉ vì nó có vẻ tổng quát hơn.

## 6. Headers: quy ước, độ tin cậy và khả năng tương thích

Headers rất hữu ích nhưng cũng là một ranh giới cần quản lý.

### Phân biệt header nghiệp vụ và header vận chuyển

Một số header thường có ý nghĩa xuyên dịch vụ:

- `eventId`: định danh ổn định của sự kiện để deduplication.
- `correlationId`: liên kết các message trong cùng một luồng xử lý.
- `traceparent`: thông tin ngữ cảnh truy vết theo chuẩn W3C Trace Context, nếu hệ thống dùng chuẩn này.
- `tenantId`: định danh tenant khi kiến trúc cần định tuyến hoặc kiểm tra phạm vi tenant.

Một số header lại gắn với giao thức hoặc binder, ví dụ partition, offset, delivery tag, routing key hoặc thông tin subscription. Các header này hữu ích cho adapter và vận hành, nhưng không nên đưa thẳng vào mô hình domain.

Cùng một khái niệm có thể được biểu diễn khác nhau giữa các broker. Kafka có header record và metadata partition/offset; RabbitMQ có properties, headers và routing key; Pulsar có properties cùng metadata message. Binder có trách nhiệm ánh xạ những giá trị được hỗ trợ. Không giả định mọi header tùy chỉnh hay header riêng broker sẽ tự động đi qua mọi binder hoặc giữ nguyên kiểu dữ liệu.

### Không xem header là dữ liệu đáng tin cậy

Header đến từ hệ thống bên ngoài cần được kiểm tra giống payload:

- Kiểm tra kiểu và định dạng.
- Kiểm tra tenant ID có được phép truy cập hay không.
- Giới hạn độ dài và tập giá trị được chấp nhận.
- Không dùng header do producer tùy ý đặt làm bằng chứng xác thực hoặc phân quyền.
- Không ghi token, mật khẩu hoặc dữ liệu bí mật vào headers.

Nếu cần thông tin tenant để truy cập database, adapter phải xác thực metadata theo cơ chế tin cậy của hệ thống và chuyển một giá trị đã được xác thực vào command/context ứng dụng.

### Header do framework quản lý

Spring Messaging có thể gắn các metadata như ID và timestamp của message. Broker/binder cũng có thể thêm metadata giao nhận. Không dùng ID message do framework sinh ra thay cho event ID nghiệp vụ ổn định: khi message được tạo lại hoặc gửi lại, message ID có thể khác trong khi event ID phải giữ nguyên.

Headers là cấu trúc metadata, không phải nơi chứa toàn bộ dữ liệu nghiệp vụ. Nếu một trường cần được lưu lâu dài, xác thực như một phần của hợp đồng nghiệp vụ hoặc dùng để tái dựng sự kiện, hãy cân nhắc đặt trường đó trong payload.

## 7. Content type và chuyển đổi payload

Khi message đi qua broker, payload thường được tuần tự hóa thành byte. Khi nhận, Spring Cloud Stream cần biết cách chuyển byte đó thành kiểu Java mà hàm yêu cầu.

Content type mô tả định dạng payload, ví dụ:

- `application/json` cho JSON.
- `text/plain` cho nội dung văn bản.
- Một media type riêng nếu hệ thống có định dạng sự kiện chuyên biệt.

Có thể khai báo content type ở binding:

```yaml
spring:
  cloud:
    function:
      definition: orderCreated
    stream:
      bindings:
        orderCreated-in-0:
          destination: orders.created
          group: order-service
          content-type: application/json
```

Với `Consumer<OrderCreated>`, framework dùng kiểu tham số và content type để chọn cơ chế chuyển đổi phù hợp. Với `Consumer<Message<OrderCreated>>`, payload vẫn có thể được chuyển đổi thành `OrderCreated`; message cho phép đọc thêm headers.

Một số nguyên tắc:

1. Producer và consumer cần thống nhất schema và content type.
2. Đặt content type rõ ràng khi hợp đồng không thể suy ra an toàn từ mặc định.
3. Đừng ép kiểu payload từ `Object` nếu có thể khai báo kiểu cụ thể ngay trong chữ ký hàm.
4. Xử lý lỗi chuyển đổi riêng với lỗi nghiệp vụ: payload không giải mã được có thể chưa đến được function handler.
5. Kiểm thử cả JSON thực tế lẫn headers sau khi đi qua binder.

Ví dụ payload JSON:

```json
{
  "eventId": "evt-100",
  "orderId": "order-42",
  "total": 125.50
}
```

Đối tượng `OrderCreated` nhận được phụ thuộc vào DTO và cấu hình converter. Nếu schema thay đổi không tương thích, lỗi có thể xảy ra ở bước conversion trước khi code trong Consumer được gọi. Vì vậy, log và metric ở biên nên phân biệt lỗi deserialize, lỗi validate header và lỗi use case.

## 8. Header mapping và khác biệt giữa Kafka, RabbitMQ, Pulsar

Spring Cloud Stream cung cấp abstraction chung, nhưng khả năng ánh xạ headers ra broker có khác biệt:

| Broker | Dữ liệu gắn với message | Điều cần kiểm tra |
|---|---|---|
| Kafka | Record headers, key, partition, offset và timestamp | Header tùy chỉnh được serialize/deserialize thế nào; partition/offset là metadata của record chứ không phải payload |
| RabbitMQ | Message properties, headers, routing key, exchange và delivery metadata | Kiểu giá trị header được broker/client hỗ trợ; routing key không đồng nghĩa custom header |
| Pulsar | Message properties, key, event time và metadata subscription | Header/property nào được binder ánh xạ; key và subscription metadata có vai trò riêng |

Khi chuyển binder, hãy kiểm tra ít nhất các header ứng dụng đang sử dụng: tên, kiểu dữ liệu, khả năng truyền qua broker, quy tắc ghi đè và hành vi khi header thiếu. Một ứng dụng có thể dùng cùng `Message<T>` ở cấp Spring nhưng nhận tập metadata khác nhau từ từng binder.

Không phụ thuộc vào header riêng broker trong use case. Nếu một use case thực sự cần một giá trị như partition key để quyết định phân phối, hãy cân nhắc biến nó thành một cổng hoặc chính sách rõ ràng ở application boundary; tránh đọc trực tiếp header kỹ thuật trong domain entity.

## 9. Lỗi, retry và acknowledgment không nằm trong payload

Dùng `Message<T>` không tự động thay đổi bảo đảm giao nhận. Message vẫn đi qua binding và binder, vì vậy retry, ack, offset commit, transaction và DLQ phụ thuộc cấu hình cùng broker.

Cần phân biệt:

- **Lỗi conversion:** framework không thể chuyển payload sang kiểu đích. Function có thể chưa được gọi.
- **Lỗi header validation:** adapter nhận được message nhưng metadata không hợp lệ; cần từ chối hoặc đưa vào luồng xử lý lỗi theo chính sách.
- **Lỗi nghiệp vụ:** use case không thể hoàn tất, ví dụ đơn hàng không hợp lệ.
- **Lỗi hạ tầng:** database hoặc broker tạm thời không sẵn sàng.

Không bắt exception rồi trả về bình thường chỉ để tránh retry nếu nghiệp vụ chưa hoàn tất. Việc function hoàn tất bình thường thường được framework/binder xem là xử lý thành công theo cấu hình; nếu lỗi bị nuốt, message có thể được xác nhận trong khi dữ liệu chưa được xử lý.

Một số binder cung cấp metadata hoặc header đặc thù để điều khiển acknowledgment thủ công. Chỉ dùng khi có yêu cầu rõ ràng và theo đúng tài liệu phiên bản binder; không đưa đối tượng ack hoặc delivery tag vào domain/application. `Message<T>` không phải cơ chế xác nhận thủ công và không tạo ra exactly-once.

Với message đầu vào có thể được giao lại, hãy dùng event ID ổn định và xử lý idempotent. Nếu phát message mới từ một thay đổi database, cân nhắc transactional outbox để không tạo khoảng trống giữa commit database và gửi broker.

## 10. Kiểm thử payload và headers

Có thể kiểm thử theo ba tầng.

### Unit test cho logic nghiệp vụ

Nếu use case chỉ nhận command hoặc payload, unit test không cần tạo Spring Message. Điều này giúp test tập trung vào quy tắc nghiệp vụ.

### Unit test cho adapter nhận Message<T>

Dùng `GenericMessage` để tạo payload cùng headers:

```java
@Test
void shouldPassPayloadAndCorrelationIdToUseCase() {
    var event = new OrderCreated(
            "evt-100", "order-42", new BigDecimal("125.50")
    );

    Message<OrderCreated> message = new GenericMessage<>(
            event,
            Map.of("correlationId", "corr-900")
    );

    var captured = new AtomicReference<String>();

    Consumer<Message<OrderCreated>> handler = input -> {
        String correlationId = input.getHeaders()
                .get("correlationId", String.class);
        captured.set(correlationId);
    };

    handler.accept(message);

    assertEquals("corr-900", captured.get());
}
```

Test này xác minh code adapter đọc đúng header. Trong test use case, hãy kiểm tra command hoặc dữ liệu đã xác thực được truyền vào; không buộc domain test phải tạo `Message`.

### Integration test qua binder

Dùng Spring Cloud Stream Test Binder để kiểm tra luồng binding ở mức framework, hoặc Testcontainers với broker tương ứng để xác minh hành vi thực tế. Nên kiểm tra:

- JSON được chuyển thành đúng kiểu payload.
- `Message<T>` nhận được headers ứng dụng dự kiến.
- Header đầu ra được ánh xạ và truyền qua broker.
- Header không hợp lệ được xử lý theo chính sách.
- Lỗi conversion và lỗi handler tạo kết quả retry/DLQ phù hợp.
- Khi chuyển binder, các header quan trọng vẫn có cùng ý nghĩa và kiểu dữ liệu.

Test Binder hữu ích để kiểm tra code với abstraction của Spring Cloud Stream, nhưng không mô phỏng đầy đủ mọi quy tắc header mapping, serialization và metadata riêng của Kafka, RabbitMQ hoặc Pulsar. Các cam kết liên quan đến broker phải được kiểm thử trên binder/broker đích.

## 11. Quy tắc chọn chữ ký hàm trong dự án

Trước khi khai báo một function bean, hãy tự hỏi:

1. Hàm có cần metadata của message không? Nếu không, nhận payload trực tiếp.
2. Metadata nào thực sự cần cho use case? Chỉ chuyển những giá trị đã được xác thực và có ý nghĩa nghiệp vụ.
3. Hàm có tạo message đầu ra với headers tùy chỉnh không? Nếu có, trả về `Message<R>` và tạo headers theo allowlist.
4. Payload có kiểu cụ thể không? Ưu tiên `Message<DomainEventDto>` thay cho `Message<?>`.
5. Header có được hỗ trợ trên mọi binder mục tiêu không? Kiểm tra header mapping và viết integration test.
6. Giá trị nào phải tồn tại sau khi message được lưu hoặc replay? Đặt dữ liệu cần bền vững trong payload hoặc kho dữ liệu nghiệp vụ, không dựa duy nhất vào metadata tạm thời.

Đối với ứng dụng Spring Cloud Stream hỗ trợ Kafka, RabbitMQ hoặc Pulsar, giữ DTO và mapping tại adapter giúp hợp đồng broker có thể thay đổi mà không buộc use case phụ thuộc vào API truyền tin. Dùng payload trực tiếp cho luồng đơn giản; dùng `Message<T>` ở những điểm cần đọc hoặc tạo metadata.

## Kết luận

Payload chứa dữ liệu chính của sự kiện; headers mang metadata đi kèm. Spring Cloud Stream có thể chuyển đổi payload thành kiểu Java trong cả hai trường hợp `T` và `Message<T>`. Chữ ký nhận payload trực tiếp phù hợp với phần lớn xử lý nghiệp vụ đơn giản; `Message<T>` phù hợp khi adapter cần đọc metadata hoặc kiểm soát headers đầu ra.

Hãy giữ headers ở biên tích hợp, xác thực các giá trị đến từ bên ngoài và chỉ truyền tiếp metadata cần thiết. Content type, header mapping, retry và acknowledgment còn phụ thuộc binder cụ thể. Kiểm thử trên broker đích để bảo đảm message giữ đúng payload và metadata khi triển khai với Kafka, RabbitMQ hoặc Pulsar.

