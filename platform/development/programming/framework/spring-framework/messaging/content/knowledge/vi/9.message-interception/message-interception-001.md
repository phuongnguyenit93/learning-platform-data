# MessageHandler và trách nhiệm xử lý một thông điệp

> Mục tiêu: hiểu hợp đồng `MessageHandler` của Spring Messaging, phân biệt handler với channel và endpoint, biết cách đọc payload/headers, xác thực dữ liệu, xử lý lỗi và thiết kế handler an toàn khi có retry hoặc xử lý đồng thời.

## 1. MessageHandler là gì?

`MessageHandler` là interface cốt lõi của Spring Messaging đại diện cho một thành phần nhận và xử lý message. Nó định nghĩa một phương thức:

```java
void handleMessage(Message<?> message) throws MessagingException;
```

Handler nhận một `Message<?>` gồm payload và headers, thực hiện công việc phù hợp rồi kết thúc hoặc ném exception nếu không thể xử lý. Interface không quy định message phải đến từ queue, topic, HTTP hay channel nội bộ; nơi gửi và cách dispatch do channel, endpoint hoặc adapter quyết định.

Một handler thường chịu trách nhiệm cho một bước xử lý rõ ràng, ví dụ cập nhật trạng thái đơn hàng, kiểm tra một sự kiện, gọi application service hoặc chuyển tiếp dữ liệu đã được xác thực. Handler không nên ôm toàn bộ quy trình nghiệp vụ, quản lý kết nối broker hay tự triển khai lại cơ chế retry.

## 2. Phân biệt message, channel, endpoint và handler

Bốn thành phần này phối hợp với nhau nhưng có vai trò khác nhau:

| Thành phần | Trách nhiệm |
|---|---|
| `Message<T>` | Mang payload và headers của một lần truyền dữ liệu |
| `MessageChannel` | Cung cấp điểm gửi message và hợp đồng dispatch hoặc nhận |
| Endpoint | Kết nối một handler với channel, poller hoặc transport |
| `MessageHandler` | Thực hiện công việc khi nhận một message |

Luồng xử lý điển hình trong Spring Integration:

```text
Producer / Inbound Adapter
          |
          v
     MessageChannel
          |
          v
   Endpoint / Dispatcher
          |
          v
     MessageHandler
          |
          v
 Application Service / Domain
```

Channel quyết định message được chuyển đến subscriber nào hoặc được lưu để poll. Endpoint kết nối channel với handler và có thể bổ sung chuyển đổi tham số, transaction, advice hoặc error handling. Handler tập trung vào xử lý nội dung message.

Một `DirectChannel` thường dispatch đến một subscriber được chọn trong luồng gửi. `PublishSubscribeChannel` có thể gửi cùng message đến nhiều subscriber. `QueueChannel` lưu message trong buffer để consumer poll. Vì vậy, handler không nên giả định mỗi channel đều có cùng cách phân phối, thứ tự hoặc thời điểm gọi.

## 3. Đọc payload và headers

Payload là dữ liệu chính cần xử lý. Headers chứa metadata như message ID, timestamp, correlation ID, content type, reply channel hoặc thông tin định tuyến. Handler có thể nhận toàn bộ message khi cần kiểm tra cả hai phần.

Ví dụ:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.MessagingException;
import org.springframework.stereotype.Component;

record OrderCreated(String orderId, int itemCount) {}

@Component
class OrderCreatedMessageHandler implements MessageHandler {
    private final OrderApplicationService orderService;

    OrderCreatedMessageHandler(OrderApplicationService orderService) {
        this.orderService = orderService;
    }

    @Override
    public void handleMessage(Message<?> message) throws MessagingException {
        Object payload = message.getPayload();

        if (!(payload instanceof OrderCreated event)) {
            throw new MessagingException(message,
                    "Expected an OrderCreated payload");
        }

        if (event.orderId() == null || event.orderId().isBlank()) {
            throw new MessagingException(message,
                    "Order ID must not be blank");
        }

        orderService.process(event);
    }
}
```

Đây là ví dụ minh họa một handler; `OrderApplicationService` là service nghiệp vụ do ứng dụng cung cấp. Handler kiểm tra kiểu payload và dữ liệu tối thiểu trước khi gọi service. Trong ứng dụng thực tế, validation có thể được tách thành validator hoặc thực hiện ở tầng application/domain tùy quy tắc.

Khi cần metadata, handler có thể đọc từ `message.getHeaders()`. Ví dụ, `MessageHeaders.ID` định danh message, `MessageHeaders.TIMESTAMP` ghi thời điểm tạo message và `MessageHeaders.CONTENT_TYPE` mô tả kiểu nội dung. Header tùy chỉnh như `correlationId` hoặc `tenantId` cần được producer và consumer thống nhất.

Không nên coi header là dữ liệu nghiệp vụ đáng tin cậy chỉ vì nó nằm trong message. Nếu header ảnh hưởng đến tenant, quyền truy cập hoặc định tuyến nhạy cảm, cần xác thực nguồn gửi và kiểm tra giá trị ở ranh giới tin cậy. Tránh đưa secret hoặc dữ liệu cá nhân không cần thiết vào headers.

## 4. Triển khai trực tiếp MessageHandler

Implement `MessageHandler` phù hợp khi cần kiểm soát trực tiếp đối tượng message, chẳng hạn khi xử lý metadata, xây dựng một adapter hoặc viết một handler cấp thấp.

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.MessagingException;

class AuditMessageHandler implements MessageHandler {
    private final AuditService auditService;

    AuditMessageHandler(AuditService auditService) {
        this.auditService = auditService;
    }

    @Override
    public void handleMessage(Message<?> message) throws MessagingException {
        try {
            auditService.record(
                    message.getHeaders().getId(),
                    message.getPayload()
            );
        } catch (RuntimeException ex) {
            throw new MessagingException(message,
                    "Could not record message audit", ex);
        }
    }
}
```

Ví dụ giữ nguyên message gây lỗi trong `MessagingException` để hạ tầng hoặc error handler có thể truy vết. Chỉ nên bọc exception khi cần bổ sung ngữ cảnh; giữ `cause` gốc để không mất stack trace và nguyên nhân thực sự.

Không nên bắt `Exception` hoặc `Throwable` rồi bỏ qua. Nếu handler ghi log nhưng vẫn trả về bình thường, hạ tầng có thể xem message đã xử lý thành công và xác nhận nó, dù nghiệp vụ chưa hoàn tất. Với lỗi không thể xử lý, hãy ném exception phù hợp để endpoint hoặc adapter áp dụng chính sách lỗi đã cấu hình.

## 5. Dùng Service Activator trong Spring Integration

Trong nhiều ứng dụng, không cần tự implement `MessageHandler`. Spring Integration có thể chuyển một phương thức Java thông thường thành message handler thông qua `@ServiceActivator`.

```java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
class OrdersServiceActivator {
    private final OrderApplicationService orderService;

    OrdersServiceActivator(OrderApplicationService orderService) {
        this.orderService = orderService;
    }

    @ServiceActivator(inputChannel = "orders.created")
    public void handle(OrderCreated event) {
        orderService.process(event);
    }
}
```

Spring Integration tạo endpoint cho phương thức và kết nối nó với channel `orders.created`. Framework có thể chuyển payload thành tham số `OrderCreated` nếu message và converter/configuration phù hợp. Phương thức có thể nhận `Message<OrderCreated>` nếu cần cả payload lẫn headers, hoặc nhận một số header cụ thể bằng annotation `@Header`.

Ví dụ nhận payload và correlation ID:

```java
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@ServiceActivator(inputChannel = "orders.created")
public void handle(
        @Payload OrderCreated event,
        @Header("correlationId") String correlationId) {
    orderService.process(event, correlationId);
}
```

Đây là các đoạn mã minh họa; ứng dụng cần có Spring Integration, channel bean tương ứng và cấu hình endpoint. Nếu header bắt buộc không tồn tại hoặc không chuyển đổi được, invocation có thể thất bại trước khi vào thân phương thức.

### Handler trả về kết quả

Phương thức được dùng làm service activator có thể trả về một object hoặc message. Khi có kết quả, endpoint có thể tạo reply message và gửi đến output channel hoặc reply channel theo cấu hình. Phương thức `MessageHandler.handleMessage` ở mức interface trả về `void`; mô hình trả lời được quản lý bởi endpoint/gateway và reply channel.

Nếu phương thức không có kết quả (`void` hoặc `null`), không có reply payload được phát ra từ service activator. Hãy cấu hình output channel rõ ràng nếu flow cần chuyển kết quả sang bước kế tiếp.

## 6. Trách nhiệm của một handler tốt

Một handler nên thực hiện một bước có mục đích rõ ràng và giữ hợp đồng đầu vào/đầu ra ổn định:

1. **Kiểm tra message:** xác nhận payload có kiểu và dữ liệu cần thiết; kiểm tra headers bắt buộc.
2. **Áp dụng quy tắc ở đúng tầng:** gọi application service hoặc domain logic thay vì nhồi toàn bộ nghiệp vụ vào handler.
3. **Giữ ngữ cảnh:** chuyển correlation ID, message ID hoặc metadata cần thiết sang log và lời gọi tiếp theo.
4. **Quản lý kết quả:** nếu cần reply, tạo kết quả có kiểu và để endpoint/gateway định tuyến theo hợp đồng.
5. **Báo lỗi đúng cách:** không nuốt exception; phân biệt lỗi nghiệp vụ dự kiến với lỗi kỹ thuật.
6. **Bảo đảm an toàn khi chạy lặp:** xử lý duplicate hoặc redelivery theo chính sách idempotency.
7. **Giữ khả năng quan sát:** ghi log có cấu trúc và metrics cần thiết mà không làm lộ payload nhạy cảm.

Handler nên tránh các trách nhiệm không thuộc bước xử lý của nó như tự quản lý vòng đời broker connection, tự poll queue, tự quyết định retry vô hạn hoặc giữ state thay đổi theo từng message trong field của singleton bean.

## 7. Exception và luồng xử lý lỗi

`MessageHandler.handleMessage` có thể ném `MessagingException`. Cách exception được quan sát phụ thuộc channel và endpoint:

- Với `DirectChannel`, handler thường chạy trong luồng gửi; exception có thể truyền ngược về producer/caller.
- Với executor hoặc endpoint bất đồng bộ, sender có thể đã kết thúc trước khi handler lỗi; cần error handler hoặc error channel để nhận lỗi.
- Với broker adapter, transaction, acknowledgement, retry, requeue hoặc dead-letter phụ thuộc adapter và cấu hình broker.

Không nên giả định mọi exception đều tự động được chuyển đến một `errorChannel`. Cần xác định endpoint nào phát lỗi, error channel nào được cấu hình và lỗi handler có được ném lại hay được chuyển tiếp.

### Lỗi nghiệp vụ và lỗi kỹ thuật

Không phải mọi kết quả không thành công đều nên là exception:

| Tình huống | Cách xử lý thường phù hợp |
|---|---|
| Đơn hàng không đủ điều kiện theo quy tắc nghiệp vụ | Trả kết quả từ chối có kiểu hoặc phát event nghiệp vụ tương ứng |
| Payload sai định dạng hoặc thiếu field bắt buộc | Báo lỗi validation/conversion và áp dụng chính sách reject hoặc dead-letter |
| Database tạm thời mất kết nối | Ném exception để retry có giới hạn nếu thao tác an toàn |
| Handler gặp lỗi lập trình | Để lỗi được quan sát, sửa nguyên nhân và tránh retry vô hạn |

Nếu handler đã ghi database nhưng chưa xác nhận message, message có thể được giao lại. Vì vậy, handler cần phối hợp transaction và acknowledgement đúng với transport, đồng thời bảo đảm thao tác có thể xử lý an toàn khi lặp.

## 8. Idempotency và xử lý message trùng

Broker có thể giao lại message khi consumer mất kết nối, không xác nhận đúng hạn hoặc gặp lỗi. Một handler được gọi nhiều lần với cùng message là tình huống cần được dự liệu.

Idempotency nghĩa là xử lý cùng một yêu cầu lặp lại không tạo thêm tác dụng phụ ngoài kết quả mong muốn. Một số cách thường dùng:

- Dùng message ID hoặc command ID ổn định để nhận diện lần xử lý.
- Lưu dấu message đã xử lý cùng kết quả trong database.
- Dùng unique constraint hoặc business key để ngăn tạo bản ghi trùng.
- Thực hiện kiểm tra duplicate và cập nhật trạng thái trong cùng transaction phù hợp.
- Với side effect bên ngoài như thanh toán, dùng idempotency key mà nhà cung cấp hỗ trợ nếu có.

Không nên chỉ lưu một cờ `processed=true` tách rời khỏi cập nhật nghiệp vụ nếu hai thao tác có thể thất bại độc lập. Khi đó hệ thống có thể đánh dấu đã xử lý nhưng chưa ghi kết quả, hoặc ngược lại.

## 9. Xử lý đồng thời và thread safety

Spring bean thường có scope singleton. Một handler singleton có thể được gọi đồng thời bởi nhiều thread tùy channel, executor, listener container và concurrency setting.

Vì vậy:

- Tránh lưu dữ liệu tạm của từng message vào mutable instance field.
- Dùng biến cục bộ cho trạng thái chỉ thuộc một lần gọi.
- Nếu phải chia sẻ state, dùng cơ chế đồng bộ hoặc cấu trúc thread-safe phù hợp; tốt hơn là lưu state nghiệp vụ trong service/database.
- Không giả định thứ tự hoàn tất bằng thứ tự nhận nếu endpoint xử lý song song.
- Đặt giới hạn concurrency dựa trên CPU, connection pool, broker và downstream service.

Transaction gắn với thread thường không tự truyền sang thread executor khác. Nếu cần transaction, hãy đặt ranh giới transaction trong handler/service đang thực thi trên thread xử lý và cấu hình transaction manager tương ứng.

## 10. Kiểm thử MessageHandler

Có thể kiểm thử handler ở cấp đơn vị bằng cách tạo message và gọi trực tiếp `handleMessage`. Kiểm thử nên tập trung vào hợp đồng của handler:

- Payload hợp lệ gọi application service đúng một lần.
- Payload sai kiểu hoặc thiếu dữ liệu bị từ chối theo hợp đồng.
- Headers bắt buộc được đọc và truyền đúng.
- Exception từ service được giữ cause và message gây lỗi.
- Duplicate message không tạo side effect lặp khi idempotency là yêu cầu.

Ví dụ tạo message trong test:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<OrderCreated> message = MessageBuilder
        .withPayload(new OrderCreated("ORD-100", 2))
        .setHeader("correlationId", "corr-100")
        .build();

handler.handleMessage(message);
```

Đây là đoạn mã minh họa chuẩn bị đầu vào cho unit test; `handler` là instance đã được tạo với dependency giả hoặc mock. Ngoài unit test, nên có integration test để kiểm tra channel dispatch, endpoint, converter, error flow và adapter thực tế.

## 11. Lỗi thường gặp

- **Nhầm handler với channel:** handler xử lý message; channel chuyển message đến subscriber hoặc lưu message để poll.
- **Đưa toàn bộ nghiệp vụ vào `handleMessage`:** khiến handler khó kiểm thử và khó tái sử dụng; nên ủy quyền cho application/domain service.
- **Ép mọi payload bằng cast không kiểm tra:** message sai kiểu có thể gây `ClassCastException`; hãy xác thực hợp đồng đầu vào.
- **Bỏ qua headers quan trọng:** mất correlation ID hoặc tenant context làm khó truy vết và có thể ảnh hưởng định tuyến.
- **Nuốt exception rồi trả về bình thường:** hạ tầng có thể xác nhận message dù xử lý thất bại.
- **Cho rằng `send` thành công nghĩa là handler đã hoàn tất:** với dispatch bất đồng bộ, `send` có thể chỉ xác nhận đã nhận công việc.
- **Không thiết kế idempotency:** redelivery có thể tạo đơn hàng, thanh toán hoặc thông báo trùng.
- **Lưu state theo message trong singleton handler:** nhiều thread có thể ghi đè dữ liệu của nhau.
- **Giả định mọi lỗi được gửi vào `errorChannel`:** error routing phụ thuộc endpoint và cấu hình cụ thể.
- **Dùng handler làm nơi poll broker:** việc nhận từ transport thuộc adapter/container; handler chỉ xử lý message đã được chuyển đến.

## 12. Quy trình xây dựng handler

1. Xác định loại message, payload type, headers bắt buộc và điều kiện hợp lệ.
2. Xác định channel và endpoint nào dispatch message đến handler.
3. Viết handler nhỏ, ưu tiên gọi application service qua constructor injection.
4. Phân biệt kết quả nghiệp vụ bình thường với exception kỹ thuật.
5. Xác định reply contract nếu flow cần kết quả trả về.
6. Thiết kế idempotency, transaction, acknowledgement và retry phù hợp transport.
7. Bảo đảm handler thread-safe với concurrency thực tế.
8. Viết unit test cho hợp đồng handler và integration test cho channel/endpoint/error flow.
9. Theo dõi số message xử lý, thời gian xử lý, lỗi, retry và duplicate.

## 13. Kết luận

`MessageHandler` là điểm thực thi công việc khi một message được dispatch đến consumer. Nó nhận `Message<?>`, đọc payload và headers, thực hiện một bước xử lý có trách nhiệm rõ ràng rồi kết thúc hoặc ném `MessagingException` khi thất bại.

Spring Integration có thể kết nối handler bằng endpoint như `@ServiceActivator`, trong khi channel quyết định cách message được dispatch hoặc buffer. Handler tốt cần kiểm tra hợp đồng đầu vào, ủy quyền nghiệp vụ cho service phù hợp, xử lý lỗi minh bạch, an toàn khi chạy đồng thời và idempotent khi message được giao lại.