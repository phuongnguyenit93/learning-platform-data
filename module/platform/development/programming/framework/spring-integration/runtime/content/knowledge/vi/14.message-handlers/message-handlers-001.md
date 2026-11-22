# MessageHandler và handleMessage contract

## Mục tiêu

Trong Spring Integration, message flow được nối từ channel qua endpoint đến consumer và handler. Endpoint quản lý cách một handler được đăng ký, gọi và dừng theo vòng đời ứng dụng; consumer quyết định nhận message theo kiểu event-driven hay polling; còn MessageHandler định nghĩa hợp đồng xử lý một message.

MessageHandler là abstraction của Spring Messaging, được Spring Integration sử dụng làm điểm thực thi cho nhiều loại endpoint. Hợp đồng của nó tập trung vào một phương thức:

~~~java
void handleMessage(Message<?> message) throws MessagingException;
~~~

Phương thức nhận toàn bộ Message, xử lý và kết thúc bằng cách trả về bình thường hoặc ném exception. Nó không có giá trị trả về. Vì vậy, khi thiết kế handler, cần xác định rõ payload nào được chấp nhận, header nào cần giữ, lỗi được truyền ra sao và kết quả có cần tạo thành reply message hay không.

## 1. MessageHandler nằm ở đâu trong message flow?

Một message flow thường có dạng:

~~~mermaid
flowchart LR
    A[Producer] --> B[MessageChannel]
    B --> C[Endpoint]
    C --> D[Consumer]
    D --> E[MessageHandler]
    E --> F[Business logic]
    E -. reply nếu có .-> G[Output channel]
~~~

Các thành phần có trách nhiệm khác nhau:

| Thành phần | Trách nhiệm |
|---|---|
| **MessageChannel** | Vận chuyển message đến consumer hoặc subscriber |
| **Endpoint** | Kết nối handler với channel, áp dụng cấu hình và quản lý vòng đời |
| **Consumer** | Nhận message theo cơ chế subscribe hoặc poll |
| **MessageHandler** | Thực thi xử lý trên một Message |
| **Reply/output channel** | Nhận kết quả khi flow có bước tạo reply |

Trong Spring Integration, endpoint thường tạo và quản lý việc đăng ký handler. Ví dụ, một endpoint event-driven đăng ký handler làm subscriber trên SubscribableChannel; một polling consumer lấy message từ PollableChannel rồi gọi handler. Nhờ endpoint, handler không cần tự quản lý việc subscribe, lịch poll hay vòng đời của channel.

Ở mức API thấp, MessageHandler chỉ là đối tượng có thể được gọi với một message. Trong ứng dụng thực tế, nên để IntegrationFlow hoặc các endpoint như service activator quản lý việc nối handler vào flow.

## 2. Hợp đồng của MessageHandler

Interface nằm trong package org.springframework.messaging:

~~~java
package org.springframework.messaging;

import org.springframework.messaging.MessagingException;

@FunctionalInterface
public interface MessageHandler {

    void handleMessage(Message<?> message) throws MessagingException;

}
~~~

Các điểm quan trọng của hợp đồng:

- Đầu vào là một Message, bao gồm payload và headers.
- Phương thức trả về void; handler không trả reply bằng return.
- Lỗi xử lý có thể được biểu diễn bằng MessagingException hoặc các unchecked exception.
- Khi phương thức kết thúc bình thường, lời gọi handler được xem là hoàn tất.
- Việc retry, lưu trữ bền vững, transaction và định tuyến lỗi phụ thuộc vào endpoint, channel và cấu hình flow xung quanh.

Message dùng wildcard vì handler có thể nhận message mang nhiều kiểu payload. Handler cần xác định kiểu dữ liệu mà nghiệp vụ của nó chấp nhận, sau đó kiểm tra hoặc chuyển đổi payload phù hợp. Không nên giả định mọi message đi vào channel đều có cùng kiểu nếu channel được chia sẻ bởi nhiều producer.

## 3. Message gồm payload và headers

Message<T> là envelope chứa dữ liệu nghiệp vụ và metadata:

~~~java
public interface Message<T> {

    T getPayload();

    MessageHeaders getHeaders();

}
~~~

Ví dụ một message đơn giản:

~~~java
Message<String> message = MessageBuilder
        .withPayload("order-1001")
        .setHeader("source", "checkout")
        .setHeader("tenantId", "tenant-a")
        .build();
~~~

Trong ví dụ này:

- Payload là chuỗi order-1001.
- Header source cho biết nguồn phát message.
- Header tenantId cung cấp ngữ cảnh tenant cho bước xử lý.

Handler có thể đọc hai phần riêng biệt:

~~~java
@Override
public void handleMessage(Message<?> message) {
    Object payload = message.getPayload();
    MessageHeaders headers = message.getHeaders();

    String source = headers.get("source", String.class);
    String tenantId = headers.get("tenantId", String.class);

    // Xác thực payload và thực thi nghiệp vụ.
}
~~~

### 3.1. Payload

Payload là nội dung mà flow cần xử lý, chẳng hạn Order, String, sự kiện hoặc một DTO. Handler nên xác thực kiểu và trạng thái payload ở ranh giới đầu vào, đặc biệt khi channel có nhiều producer.

Ví dụ:

~~~java
@Override
public void handleMessage(Message<?> message) {
    Object payload = message.getPayload();

    if (!(payload instanceof Order)) {
        throw new IllegalArgumentException(
                "Expected Order payload but received: "
                        + (payload == null
                                ? "null"
                                : payload.getClass().getName()));
    }

    Order order = (Order) payload;
    orderService.process(order);
}
~~~

Đây là kiểm tra kiểu tối thiểu. Trong hệ thống thực tế, cần kiểm tra thêm các trường bắt buộc và quy tắc nghiệp vụ. Nếu payload có thể là null theo hợp đồng riêng của ứng dụng, hãy xử lý trường hợp đó trước khi gọi getClass() hoặc ép kiểu.

### 3.2. Headers

Headers mang metadata điều khiển hoặc mô tả message: ID, timestamp, content type, correlation, sequence, reply channel, error channel và metadata do ứng dụng bổ sung.

MessageHeaders cung cấp giao diện chỉ đọc. Không sửa header bằng cách xem nó như một Map có thể ghi. Khi cần thay đổi metadata hoặc payload, hãy tạo message mới bằng MessageBuilder.

~~~java
Message<Order> enrichedMessage = MessageBuilder
        .fromMessage(originalMessage)
        .setHeader("validated", true)
        .setHeader("handlerVersion", "v2")
        .build();
~~~

Cách tạo message mới giúp giữ rõ ranh giới giữa message đầu vào và message đã được bổ sung metadata. Khi chuyển tiếp message, hãy quyết định header nào cần được bảo toàn. Đặc biệt, không tùy tiện xóa hoặc ghi đè correlation, sequence, reply channel hay error channel vì các thành phần phía sau có thể dựa vào chúng.

Envelope message có tính bất biến ở mức API, nhưng điều đó không có nghĩa payload luôn bất biến. Nếu payload là một object mutable và nhiều consumer hoặc thread cùng tham chiếu object đó, việc thay đổi object có thể tạo race condition. Ưu tiên DTO bất biến hoặc tạo bản sao khi cần biến đổi dữ liệu.

## 4. Cài đặt MessageHandler

Một handler có thể được cài đặt bằng class riêng:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;

public class AuditMessageHandler implements MessageHandler {

    private final AuditService auditService;

    public AuditMessageHandler(AuditService auditService) {
        this.auditService = auditService;
    }

    @Override
    public void handleMessage(Message<?> message) {
        auditService.record(
                message.getPayload(),
                message.getHeaders());
    }
}
~~~

Đưa handler vào một IntegrationFlow:

~~~java
@Bean
public IntegrationFlow auditFlow(AuditMessageHandler auditHandler) {
    return IntegrationFlow.from("auditChannel")
            .handle(auditHandler)
            .get();
}
~~~

Trong ví dụ này, IntegrationFlow tạo endpoint kết nối auditChannel với handler. Khi message đến channel, endpoint gọi handleMessage. Class handler chỉ tập trung vào công việc audit; phần đăng ký và vòng đời endpoint do Spring Integration quản lý.

Vì MessageHandler có một phương thức trừu tượng, có thể dùng lambda cho xử lý ngắn:

~~~java
@Bean
public IntegrationFlow notificationFlow(NotificationService service) {
    MessageHandler handler = message ->
            service.send((Notification) message.getPayload());

    return IntegrationFlow.from("notificationChannel")
            .handle(handler)
            .get();
}
~~~

Với xử lý có nhiều quy tắc, kiểm tra đầu vào, logging và exception mapping, class riêng thường dễ đọc và kiểm thử hơn lambda dài.

## 5. handleMessage không trả reply

Một điểm dễ nhầm là handleMessage trả về void. Handler có thể ghi dữ liệu, gọi API, gửi notification hoặc thực hiện side effect, nhưng giá trị trả về của phương thức không được dùng để tạo reply.

Nếu handler cần gửi kết quả đến bước kế tiếp, có hai cách thiết kế phổ biến:

1. Dùng một reply-producing endpoint, ví dụ service activator gọi phương thức nghiệp vụ có giá trị trả về.
2. Chủ động gửi một message mới đến output channel từ logic xử lý.

Với Java DSL, có thể khai báo một bước biến đổi payload và tạo message kết quả như sau:

~~~java
@Bean
public IntegrationFlow normalizeOrderFlow(OrderService orderService) {
    return IntegrationFlow.from("rawOrders")
            .<Order, NormalizedOrder>transform(orderService::normalize)
            .channel("normalizedOrders")
            .get();
}
~~~

Ở đây, transform là một bước tạo message mới từ kết quả hàm. Nó khác với việc cài đặt trực tiếp MessageHandler.handleMessage.

Một cách khác là dùng service activator để gọi phương thức nghiệp vụ có reply:

~~~java
@Bean
public IntegrationFlow enrichOrderFlow(OrderService orderService) {
    return IntegrationFlow.from("orders")
            .handle(orderService, "enrich")
            .channel("enrichedOrders")
            .get();
}
~~~

Phương thức enrich của OrderService có thể trả về object kết quả; endpoint service activator chịu trách nhiệm chuyển kết quả đó thành reply message và gửi tiếp trong flow. Hãy chọn abstraction theo mục đích: MessageHandler cho xử lý một chiều, reply-producing handler cho bước xử lý tạo kết quả.

## 6. Xử lý exception trong handleMessage

Interface khai báo MessagingException để biểu diễn lỗi liên quan đến xử lý message. Implementation cũng có thể ném unchecked exception như IllegalArgumentException, IllegalStateException hoặc exception nghiệp vụ kế thừa RuntimeException.

Ví dụ giữ lại message và nguyên nhân khi chuyển một lỗi nghiệp vụ thành MessagingException:

~~~java
@Override
public void handleMessage(Message<?> message) {
    try {
        orderService.process((Order) message.getPayload());
    }
    catch (OrderRejectedException exception) {
        throw new MessagingException(
                message,
                "Cannot process rejected order",
                exception);
    }
}
~~~

Khi tạo exception, hãy giữ nguyên cause để log và công cụ quan sát có thể lần theo lỗi gốc. Nếu handler bắt exception chỉ để ghi log rồi kết thúc bình thường, dispatcher sẽ hiểu lời gọi đã thành công và không thể tự kích hoạt failover dựa trên exception đó.

### 6.1. Lỗi đi tiếp như thế nào?

Đường đi của exception phụ thuộc cách channel và consumer thực thi:

- Với DirectChannel, handler thường được gọi đồng bộ trong thread gửi message. Exception có thể truyền ngược về lời gọi send().
- Với ExecutorChannel, handler thường chạy trong thread do TaskExecutor quản lý. Sender có thể đã nhận kết quả submit trước khi handler phát sinh lỗi.
- Với polling consumer, exception xảy ra trong lần poll và được xử lý theo cấu hình poller, transaction và error handling.
- Endpoint có thể kết hợp error channel, advice hoặc retry interceptor để xử lý lỗi.

MessageHandler không tự đảm bảo retry, dead-letter queue hay giao nhận exactly-once. Hãy thiết kế error flow tại tầng endpoint/channel phù hợp với yêu cầu vận hành.

## 7. Thread safety và tính idempotent

Một handler có thể được gọi nhiều lần và từ nhiều thread tùy channel, executor và cấu hình consumer. Do đó, hãy xem handler là đối tượng có khả năng được gọi đồng thời trừ khi cấu hình thực thi đảm bảo tuần tự.

Một số nguyên tắc thực tế:

- Tránh lưu dữ liệu của từng message vào field mutable dùng chung.
- Nếu cần cache hoặc bộ đếm dùng chung, chọn cấu trúc thread-safe và xác định rõ vòng đời.
- Không giữ tham chiếu payload mutable rồi thay đổi nó sau khi chuyển message cho bước khác.
- Không giả định message chỉ được xử lý đúng một lần; retry, redelivery hoặc failover có thể khiến cùng một nghiệp vụ được gọi lại.
- Dùng business key hoặc idempotency key để ngăn side effect bị lặp.

Ví dụ, khi ghi nhận thanh toán, handler nên kiểm tra mã giao dịch đã được xử lý trước khi tạo một giao dịch mới. Việc handleMessage kết thúc bình thường chỉ nói rằng lời gọi hiện tại không ném lỗi; nó không tự chứng minh toàn bộ hệ thống đã lưu kết quả bền vững hoặc message sẽ không bao giờ được gửi lại.

## 8. Kiểm thử hợp đồng handleMessage

Có thể kiểm thử handler độc lập bằng cách tạo một message và gọi trực tiếp phương thức:

~~~java
@Test
void recordsOrderWithMessageContext() {
    Message<Order> message = MessageBuilder
            .withPayload(new Order("order-1001"))
            .setHeader("tenantId", "tenant-a")
            .build();

    handler.handleMessage(message);

    verify(orderService).process(
            message.getPayload(),
            message.getHeaders());
}
~~~

Một số trường hợp nên kiểm thử:

| Trường hợp | Điều cần xác nhận |
|---|---|
| Payload hợp lệ | Logic nghiệp vụ được gọi với payload mong đợi |
| Sai kiểu payload | Handler từ chối đầu vào với lỗi rõ ràng |
| Header bắt buộc bị thiếu | Hành vi từ chối hoặc giá trị mặc định đúng quy tắc |
| Nghiệp vụ phát sinh lỗi | Exception được truyền ra hoặc ánh xạ đúng |
| Payload được biến đổi | Message đầu ra có payload và header cần thiết |
| Gọi đồng thời | Handler không làm hỏng trạng thái dùng chung |
| Gọi lặp cùng business key | Side effect được bảo vệ bằng idempotency |

Unit test trực tiếp xác nhận logic của handler. Để xác nhận việc nối channel, endpoint, poller, executor và error channel, cần thêm integration test khởi tạo Spring context và gửi message qua chính channel đầu vào của flow.

## 9. Lỗi thiết kế thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Handler không nhận message | Endpoint chưa được tạo, channel sai tên hoặc flow chưa được đăng ký | Kiểm tra IntegrationFlow và cấu hình endpoint |
| Ép kiểu payload thất bại | Producer gửi kiểu dữ liệu khác với handler mong đợi | Xác thực payload hoặc thêm bước transform |
| Header biến mất ở bước sau | Tạo message mới nhưng không copy metadata cần thiết | Dùng MessageBuilder.fromMessage và kiểm tra header |
| Thay đổi header không có tác dụng | Cố sửa MessageHeaders trực tiếp | Tạo message mới bằng MessageBuilder |
| Sender không nhận được lỗi | Handler chạy qua executor hoặc consumer bất đồng bộ | Kiểm tra error channel và logging của worker |
| Flow không có reply | Dùng handler void nhưng kỳ vọng giá trị trả về | Dùng reply-producing handler hoặc transform |
| Cùng nghiệp vụ chạy hai lần | Retry/redelivery/failover và thiếu idempotency | Dùng business key và cơ chế chống trùng |
| Lỗi bị che khuất | Handler bắt exception rồi không ném lại | Chuyển lỗi sang error flow hoặc ném exception phù hợp |

## 10. Checklist khi triển khai một MessageHandler

Trước khi đưa handler vào flow, hãy xác định:

1. Payload đầu vào có kiểu gì và cần xác thực những trường nào?
2. Handler cần đọc các header nào, có cần giữ correlation hoặc reply metadata không?
3. Xử lý là một chiều hay cần tạo reply?
4. Exception nào được ném ra, exception nào cần chuyển thành lỗi nghiệp vụ?
5. Handler chạy đồng bộ, qua executor hay trong poller?
6. Có thể có nhiều lần gọi đồng thời hoặc redelivery không?
7. Unit test và integration test nào chứng minh được hợp đồng xử lý?

Một MessageHandler tốt có ranh giới đầu vào rõ ràng, xử lý một trách nhiệm dễ kiểm thử, bảo toàn metadata cần thiết và để lỗi đi theo chính sách đã thiết kế của flow. Khi nắm chắc hợp đồng handleMessage, việc đọc và xây dựng endpoint, consumer, poller và executor trong Spring Integration trở nên dễ dự đoán hơn.

## Tài liệu tham khảo

- [Spring Integration — Endpoint](https://docs.spring.io/spring-integration/reference/endpoint.html)
- [Spring Integration — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
- [Spring Framework API — MessageHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHandler.html)
- [Spring Framework API — Message](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/Message.html)
- [Spring Framework API — MessageBuilder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageBuilder.html)

