# convertAndSend, receiveAndConvert và convertSendAndReceive

## Mục tiêu

Trong Spring Messaging, ứng dụng thường làm việc với đối tượng nghiệp vụ như `OrderCreated`, `PaymentRequest` hoặc `StockReply`, trong khi hạ tầng messaging trao đổi các `Message<?>` có payload và headers. Các phương thức `convertAndSend`, `receiveAndConvert` và `convertSendAndReceive` giúp nối hai thế giới đó bằng một `MessageConverter`.

Sau bài này, bạn có thể:

- Chọn đúng phương thức khi chỉ gửi, chỉ nhận hoặc cần request-reply.
- Hiểu dữ liệu được chuyển đổi ở bước nào và vai trò của `MessageConverter`.
- Chọn destination, default destination và loại channel phù hợp.
- Cấu hình send timeout, receive timeout và xử lý trường hợp không có message hoặc không có reply.
- Phân biệt việc gửi thành công vào channel với việc consumer đã xử lý xong.

## 1. Vị trí của các phương thức trong Spring Messaging

Các phương thức này thuộc nhóm template API trong package `org.springframework.messaging.core`:

- `MessageSendingOperations<D>` định nghĩa các thao tác gửi, gồm `send` và `convertAndSend`.
- `MessageReceivingOperations<D>` định nghĩa các thao tác nhận, gồm `receive` và `receiveAndConvert`.
- `MessageRequestReplyOperations<D>` định nghĩa request-reply, gồm `sendAndReceive` và `convertSendAndReceive`.

Các lớp trừu tượng chia sẻ phần xử lý chung:

- `AbstractMessageSendingTemplate<D>` triển khai các biến thể gửi và chuyển đổi payload.
- `AbstractMessageReceivingTemplate<D>` bổ sung nhận message và chuyển đổi payload.
- `AbstractMessagingTemplate<D>` bổ sung request-reply.
- `GenericMessagingTemplate` là triển khai cụ thể dùng `MessageChannel` làm destination và có khả năng phân giải tên destination thành channel.

Trong ứng dụng Spring Messaging thuần, lớp thường dùng là:

~~~java
import org.springframework.messaging.core.GenericMessagingTemplate;

GenericMessagingTemplate template = new GenericMessagingTemplate();
~~~

Đây là API của Spring Framework `spring-messaging`. Các framework tích hợp như Spring Integration, Spring AMQP hoặc Spring JMS cũng có template và phương thức tên tương tự, nhưng destination, converter, timeout và semantics của chúng có thể khác. Hãy kiểm tra đúng kiểu template mà ứng dụng đang dùng.

## 2. Bức tranh tổng thể

Ba phương thức có mục đích khác nhau:

| Phương thức | Đầu vào | Kết quả | Mục đích |
|---|---|---|---|
| `convertAndSend` | Payload Java | Không trả payload | Chuyển payload thành Message rồi gửi |
| `receiveAndConvert` | Destination và target class | Payload Java hoặc `null` | Nhận Message rồi chuyển payload sang kiểu mong muốn |
| `convertSendAndReceive` | Request Java và target class của reply | Reply Java hoặc `null` | Gửi request, đợi reply rồi chuyển payload reply |

Có thể ghi nhớ luồng dữ liệu như sau:

~~~text
convertAndSend
Java payload -> MessageConverter -> Message -> MessageChannel

receiveAndConvert
MessageChannel -> Message -> MessageConverter -> Java payload

convertSendAndReceive
Java request -> MessageConverter -> request Message
             -> MessageChannel -> request handler
             -> reply Message -> MessageConverter -> Java reply
~~~

Nếu ứng dụng đã có sẵn một `Message<?>` và cần giữ quyền kiểm soát headers, có thể dùng `send`, `receive` hoặc `sendAndReceive` để làm việc trực tiếp với message thay vì dùng các phương thức chuyển đổi.

## 3. MessageConverter làm nhiệm vụ gì?

`MessageConverter` là hợp đồng chuyển đổi giữa một payload Java và một `Message<?>`:

- `toMessage(payload, headers)`: tạo Message từ payload và headers.
- `fromMessage(message, targetClass)`: lấy payload từ Message và chuyển sang kiểu đích.

Template gọi converter ở đúng chiều cần thiết. `convertAndSend` dùng chiều Java object sang Message; `receiveAndConvert` dùng chiều Message sang Java object; `convertSendAndReceive` dùng cả hai chiều.

### 3.1. Chú ý converter mặc định

Các template kế thừa từ `AbstractMessageSendingTemplate` mặc định sử dụng `SimpleMessageConverter`.

`SimpleMessageConverter` chỉ bọc payload vào Message và lấy payload ra nếu nó đã tương thích với kiểu đích. Nó không tự biến POJO thành JSON, không giải mã JSON thành POJO và bỏ qua thông tin content type trong headers.

Ví dụ, nếu gửi một object `OrderCreated` qua channel trong cùng tiến trình, converter đơn giản có thể giữ nguyên object đó làm payload. Điều này không đồng nghĩa object đã được serialize để truyền qua mạng hoặc lưu thành JSON.

Nếu cần chuyển đổi định dạng thực sự:

- Cấu hình một `MessageConverter` phù hợp với định dạng trao đổi, chẳng hạn JSON hoặc byte array.
- Đảm bảo sender và receiver thống nhất định dạng và kiểu dữ liệu.
- Thiết lập `MessageHeaders.CONTENT_TYPE` phù hợp khi converter sử dụng MIME type để lựa chọn cách chuyển đổi.
- Kiểm tra cách adapter hoặc broker chuyển tiếp payload và headers.

Nếu converter không hỗ trợ payload hoặc không thể chuyển đổi sang kiểu đích, thao tác có thể phát sinh `MessageConversionException`. Đừng nhầm lỗi chuyển đổi với trường hợp không có message trước timeout.

## 4. convertAndSend: chuyển payload thành Message rồi gửi

### 4.1. Cách hoạt động

`convertAndSend` nhận một object Java, chuyển object thành Message bằng converter đã cấu hình, sau đó gửi Message tới destination.

Các dạng sử dụng phổ biến:

~~~java
template.convertAndSend(destination, payload);

template.convertAndSend(destination, payload, headers);

template.convertAndSend(destination, payload, postProcessor);

template.convertAndSend(destination, payload, headers, postProcessor);
~~~

Nếu template đã cấu hình default destination, có thể bỏ tham số destination:

~~~java
template.setDefaultDestination(defaultChannel);
template.convertAndSend(payload);
~~~

Nếu không truyền destination và cũng không có default destination, template không thể xác định nơi gửi và sẽ báo lỗi.

### 4.2. Headers và MessagePostProcessor

Headers bổ sung metadata cho Message, ví dụ:

- `eventType`: loại sự kiện.
- `correlationId`: mã liên kết các message trong cùng một luồng xử lý.
- `traceId`: mã truy vết.
- `tenantId`: phạm vi tenant.
- `contentType`: định dạng payload.

`MessagePostProcessor` được gọi sau bước tạo Message, cho phép chỉnh sửa message trước khi gửi. Ví dụ:

~~~java
import java.util.Map;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.core.GenericMessagingTemplate;
import org.springframework.messaging.support.MessageBuilder;

void publish(
        GenericMessagingTemplate template,
        MessageChannel events,
        OrderCreated event) {

    template.convertAndSend(
        events,
        event,
        Map.of("eventType", "OrderCreated"),
        message -> MessageBuilder.fromMessage(message)
            .setHeader("traceId", "trace-1001")
            .build()
    );
}
~~~

Đây là method minh họa trong service; `events` là MessageChannel do ứng dụng cấu hình và `OrderCreated` là kiểu payload của domain. Ví dụ không phải một chương trình độc lập để chạy trực tiếp bằng `javac`.

### 4.3. Kết quả và giới hạn

Phương thức trả về `void`. Khi dùng `GenericMessagingTemplate`, nếu channel từ chối gửi hoặc hết send timeout, template ném `MessageDeliveryException`.

Gửi thành công có nghĩa là channel chấp nhận message theo hợp đồng của channel đó. Nó không chứng minh một consumer đã xử lý xong, một transaction nghiệp vụ đã commit, hoặc một broker bên ngoài đã lưu message bền vững. Các bảo đảm đó phụ thuộc channel implementation và adapter.

## 5. receiveAndConvert: nhận Message rồi chuyển payload

### 5.1. Cách hoạt động

`receiveAndConvert` nhận một Message từ destination, sau đó dùng converter để chuyển payload sang kiểu được yêu cầu.

~~~java
OrderCreated event =
    template.receiveAndConvert(inboundChannel, OrderCreated.class);
~~~

Có thể dùng default destination:

~~~java
template.setDefaultDestination(inboundChannel);

OrderCreated event =
    template.receiveAndConvert(OrderCreated.class);
~~~

Tham số `OrderCreated.class` cho biết kiểu Java mong muốn sau chuyển đổi. Phương thức trả về payload, không trả lại toàn bộ Message. Nếu cần kiểm tra headers như correlation ID, content type hoặc timestamp, hãy dùng `receive` để lấy `Message<?>` trước.

### 5.2. Destination phải hỗ trợ polling

Với `GenericMessagingTemplate`, channel dùng cho thao tác nhận phải triển khai `PollableChannel`. Một `MessageChannel` bất kỳ chưa chắc nhận được message bằng cách polling.

`PollableChannel` cung cấp:

- `receive()`: đợi message mà không đặt giới hạn thời gian.
- `receive(timeout)`: đợi tối đa số mili giây được chỉ định.

Nếu truyền một channel chỉ hỗ trợ gửi hoặc chỉ hỗ trợ subscriber, `GenericMessagingTemplate` sẽ báo `IllegalStateException` với nội dung yêu cầu một `PollableChannel`.

### 5.3. Khi nào kết quả là null?

Nếu không có message trước khi receive timeout kết thúc, phương thức trả về `null`. Hãy kiểm tra null trước khi sử dụng payload:

~~~java
OrderCreated event =
    template.receiveAndConvert(inboundChannel, OrderCreated.class);

if (event == null) {
    // Chưa có message trong khoảng thời gian chờ.
    return;
}

handle(event);
~~~

Kết quả `null` ở đây biểu thị không nhận được message, ví dụ do timeout hoặc bị interrupt. Nếu đã nhận message nhưng converter không thể chuyển payload sang kiểu đích, đó là lỗi chuyển đổi và cần xử lý exception tương ứng.

## 6. convertSendAndReceive: request-reply có chuyển đổi

### 6.1. Cách hoạt động

`convertSendAndReceive` gộp ba bước:

1. Chuyển request object thành Message.
2. Gửi request tới destination và chờ một reply.
3. Chuyển payload của reply sang target class.

Ví dụ:

~~~java
PriceReply reply = template.convertSendAndReceive(
    priceRequestChannel,
    new PriceRequest("SKU-100"),
    PriceReply.class
);
~~~

Các tham số lần lượt là destination, request object và kiểu Java mong muốn cho reply. Có thể truyền thêm headers hoặc `MessagePostProcessor` nếu cần metadata hoặc chỉnh sửa request sau khi chuyển đổi.

### 6.2. Reply channel

Request-reply cần một đường trả lời. Với `GenericMessagingTemplate`, template tạo một reply channel tạm thời cho lần trao đổi, gắn channel đó vào request message rồi chờ reply. Handler nhận request phải gửi reply về reply channel được cung cấp trong headers của request.

Luồng khái quát:

~~~text
Caller
  -> convertSendAndReceive(request)
  -> template tạo request Message và reply channel tạm
  -> gửi request tới MessageChannel
  -> handler nhận request
  -> handler tạo reply Message và gửi về replyChannel
  -> template nhận reply
  -> converter chuyển payload sang targetClass
  -> trả kết quả cho caller
~~~

Nếu handler chỉ xử lý request mà không gửi reply, caller sẽ chờ đến khi receive timeout kết thúc. `convertSendAndReceive` là thao tác đồng bộ: thread gọi phương thức bị giữ trong lúc chờ reply.

### 6.3. Timeout và reply đến muộn

Nếu không có reply trước receive timeout, phương thức trả về `null`. Reply có thể đến sau khi caller đã timeout. Mặc định, `GenericMessagingTemplate` ghi log cảnh báo khi gặp late reply. Có thể cấu hình:

~~~java
template.setThrowExceptionOnLateReply(true);
~~~

Khi bật tùy chọn này, việc gửi một reply muộn sẽ phát sinh `MessageDeliveryException` ở phía gửi reply. Tùy chọn này giúp phát hiện handler xử lý chậm hoặc timeout được cấu hình quá ngắn.

Không nên coi timeout là bằng chứng request chưa được xử lý. Request có thể đã đến handler và nghiệp vụ có thể đã chạy xong, nhưng reply không đến kịp. Nếu caller retry, nghiệp vụ có thể bị thực hiện lặp lại; hãy dùng correlation ID và idempotency key khi request có tác động nghiệp vụ.

## 7. Cấu hình timeout

`GenericMessagingTemplate` có hai timeout cấu hình theo mili giây:

- `setSendTimeout(long)`: thời gian tối đa cho thao tác gửi trên channel hỗ trợ timeout.
- `setReceiveTimeout(long)`: thời gian tối đa cho thao tác nhận và chờ reply.

Ví dụ:

~~~java
GenericMessagingTemplate template = new GenericMessagingTemplate();
template.setSendTimeout(1_000);
template.setReceiveTimeout(3_000);
~~~

Trong triển khai hiện tại, giá trị mặc định của hai timeout là `-1`, nghĩa là không đặt giới hạn thời gian ở template. Khi đó, thao tác gửi hoặc nhận có thể chờ vô hạn tùy channel. Ứng dụng nên cân nhắc đặt timeout hữu hạn để tránh giữ thread không cần thiết.

Với `GenericMessagingTemplate`, hai header mặc định `sendTimeout` và `receiveTimeout` có thể ghi đè timeout cấu hình cho từng message trong thao tác request-reply. Template loại bỏ hai header điều khiển này trước khi gửi để chúng không bị truyền tiếp như metadata ứng dụng. Không nên dùng chúng như header nghiệp vụ.

## 8. Chọn đúng phương thức

| Nhu cầu | Phương thức nên dùng | Lý do |
|---|---|---|
| Đã có `Message<?>`, muốn gửi nguyên message | `send` | Giữ quyền kiểm soát payload và headers |
| Có object Java và muốn gửi | `convertAndSend` | Template tạo Message qua converter |
| Muốn nhận toàn bộ Message và headers | `receive` | Không loại bỏ metadata |
| Muốn nhận payload đã chuyển sang kiểu Java | `receiveAndConvert` | Chỉ lấy payload theo target class |
| Request và reply đều cần giữ nguyên Message | `sendAndReceive` | Caller tự xử lý payload và headers |
| Gửi object request và nhận object reply | `convertSendAndReceive` | Template chuyển đổi cả request và reply |

Các phương thức không thay thế lẫn nhau. Chọn phương thức dựa trên việc code cần làm việc với toàn bộ Message hay chỉ cần payload, và có cần chờ reply hay không.

## 9. Ví dụ sử dụng trong service

Ví dụ sau minh họa ba thao tác trong một service. Các channel và template được cấu hình, quản lý bởi Spring; ví dụ là đoạn tích hợp, không phải ứng dụng độc lập.

~~~java
import java.util.Optional;

import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.core.GenericMessagingTemplate;

record OrderCreated(String orderId, int version) {}
record PriceRequest(String sku) {}
record PriceReply(String sku, long priceInCents) {}

final class OrderMessagingService {

    private final GenericMessagingTemplate template;
    private final MessageChannel orderEvents;
    private final PollableChannel inboundOrders;
    private final MessageChannel priceRequests;

    OrderMessagingService(
            GenericMessagingTemplate template,
            MessageChannel orderEvents,
            PollableChannel inboundOrders,
            MessageChannel priceRequests) {
        this.template = template;
        this.orderEvents = orderEvents;
        this.inboundOrders = inboundOrders;
        this.priceRequests = priceRequests;
    }

    void publish(OrderCreated event) {
        template.convertAndSend(orderEvents, event);
    }

    Optional<OrderCreated> pollNextOrder() {
        return Optional.ofNullable(
            template.receiveAndConvert(inboundOrders, OrderCreated.class)
        );
    }

    Optional<PriceReply> requestPrice(String sku) {
        return Optional.ofNullable(
            template.convertSendAndReceive(
                priceRequests,
                new PriceRequest(sku),
                PriceReply.class
            )
        );
    }
}
~~~

Trong ví dụ:

- `publish` gửi payload mà không yêu cầu reply.
- `pollNextOrder` nhận từ `PollableChannel`; `Optional.empty()` nghĩa là không có message trong khoảng chờ.
- `requestPrice` gửi request và chờ reply; `Optional.empty()` nghĩa là không nhận được reply trong thời gian chờ.

Nếu ứng dụng trao đổi payload qua định dạng JSON hoặc qua adapter bên ngoài tiến trình, hãy cấu hình converter tương ứng và xác định content type thay vì dựa vào `SimpleMessageConverter`.

## 10. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không tìm thấy destination | Chưa cấu hình default destination hoặc tên channel không phân giải được | Truyền channel trực tiếp hoặc cấu hình destination resolver |
| `MessageDeliveryException` khi gửi | Channel từ chối message hoặc send timeout hết hạn | Kiểm tra channel capacity, subscriber và send timeout |
| `IllegalStateException` khi nhận | Destination không triển khai `PollableChannel` | Dùng channel hỗ trợ polling hoặc thiết kế luồng nhận theo subscriber |
| `receiveAndConvert` trả `null` | Không có message trước receive timeout | Kiểm tra producer, channel và thời gian chờ |
| `convertSendAndReceive` trả `null` | Handler không reply hoặc reply đến muộn | Kiểm tra replyChannel, handler và receive timeout |
| `MessageConversionException` | Converter không hỗ trợ payload hoặc target class | Cấu hình converter phù hợp và kiểm tra content type |
| Caller bị giữ thread quá lâu | Timeout mặc định không giới hạn hoặc được đặt quá lớn | Đặt timeout hữu hạn và cân nhắc xử lý bất đồng bộ |
| Reply đến sau timeout | Handler xử lý lâu hoặc timeout không phù hợp | Đo độ trễ, điều chỉnh timeout và xử lý late reply |
| Nghiệp vụ chạy hai lần sau retry | Caller hiểu timeout là request chưa chạy | Dùng correlation ID, idempotency key và xử lý idempotent |

## 11. Nguyên tắc sử dụng an toàn

- Dùng `convertAndSend` khi chỉ cần gửi payload; dùng `send` khi đã tạo Message và muốn giữ nguyên headers.
- Cấu hình converter theo định dạng thực tế; tên phương thức có chữ convert không có nghĩa mặc định sẽ serialize thành JSON.
- Dùng `PollableChannel` cho thao tác nhận đồng bộ của `GenericMessagingTemplate`.
- Đặt send timeout và receive timeout phù hợp với SLA của ứng dụng.
- Xử lý `null` từ thao tác nhận và request-reply trước khi sử dụng kết quả.
- Dùng `MessagePostProcessor` để bổ sung hoặc điều chỉnh headers sau chuyển đổi.
- Dùng `receive` hoặc `sendAndReceive` khi cần kiểm tra headers của message.
- Thiết kế request-reply với correlation ID và idempotency nếu request có tác động nghiệp vụ.
- Không xem việc gửi thành công vào channel là bằng chứng consumer đã commit nghiệp vụ.
- Không dùng thao tác đồng bộ chờ reply trên thread xử lý event hoặc request có yêu cầu không bị block lâu.

## 12. Tài liệu tham khảo

- [Spring Framework — GenericMessagingTemplate](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/GenericMessagingTemplate.html)
- [Spring Framework — AbstractMessageSendingTemplate](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/AbstractMessageSendingTemplate.html)
- [Spring Framework — AbstractMessageReceivingTemplate](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/AbstractMessageReceivingTemplate.html)
- [Spring Framework — AbstractMessagingTemplate](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/AbstractMessagingTemplate.html)
- [Spring Framework — MessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/MessageConverter.html)
- [Spring Framework — SimpleMessageConverter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/SimpleMessageConverter.html)
- [Spring Framework — PollableChannel](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/PollableChannel.html)
- [Spring Framework — MessagePostProcessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/MessagePostProcessor.html)
