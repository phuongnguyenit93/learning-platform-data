# Xác định tầng chịu trách nhiệm xử lý hoặc chuyển tiếp lỗi trong Spring Messaging

Khi một message thất bại, câu hỏi quan trọng đầu tiên là **lỗi phát sinh ở tầng nào và message đã đi đến đâu**. Spring có nhiều lớp tham gia vào luồng message: transport, giao thức, channel, chuyển đổi dữ liệu, bộ định tuyến, handler nghiệp vụ và broker. Mỗi lớp có phạm vi quan sát và khả năng phản hồi riêng.

Không có một exception handler duy nhất tự động xử lý mọi loại lỗi trong mọi ứng dụng Spring Messaging. Cần đặt xử lý tại đúng ranh giới: lỗi nghiệp vụ ở handler nghiệp vụ, lỗi định tuyến ở tầng messaging, lỗi STOMP ở bộ xử lý sub-protocol, lỗi socket ở tầng WebSocket, còn lỗi trong luồng Spring Integration có thể được chuyển qua `errorChannel`.

## 1. Nhìn luồng message để tìm đúng tầng

Với ứng dụng Spring Messaging, có thể hình dung đường đi tổng quát như sau:

```text
Client / Producer
      |
      v
Transport: TCP / WebSocket
      |
      v
Protocol: STOMP / RSocket / ...
      |
      v
Message decoding, conversion, header mapping, destination routing
      |
      v
MessageChannel / dispatcher
      |
      v
@MessageMapping / MessageHandler
      |
      v
Application service / database / external API
      |
      v
Reply channel / broker / outbound transport
      |
      v
Client / Subscriber
```

Luồng thực tế có thể khác theo transport và protocol. Ví dụ STOMP có các channel inbound, broker và outbound; RSocket dùng các interaction model và reactive publisher. Sơ đồ trên là cách chia trách nhiệm để điều tra lỗi, không phải một pipeline cố định mà mọi ứng dụng đều có.

| Tầng | Ví dụ lỗi | Thành phần nên xử lý đầu tiên |
| --- | --- | --- |
| Transport | Socket đóng, timeout ghi, handshake WebSocket thất bại | WebSocket server, TCP client/server hoặc transport adapter |
| Protocol | STOMP frame sai định dạng, lỗi xử lý frame, lỗi thiết lập RSocket | STOMP sub-protocol handler hoặc RSocket protocol/connection handler |
| Messaging infrastructure | Không tìm được destination, không có subscriber, dispatch thất bại | Destination resolver, channel hoặc message dispatcher |
| Conversion và binding | Payload không đổi được sang DTO, header/argument không hợp lệ | Message converter, argument resolver hoặc validation boundary |
| Handler và nghiệp vụ | Quy tắc nghiệp vụ từ chối lệnh, service hoặc database ném exception | `@MessageMapping` handler hoặc application service |
| Broker/relay | Broker từ chối message, relay mất kết nối | Broker/relay integration và lớp chuyển lỗi tới client |

Nguyên tắc thực tế: **tầng phát hiện lỗi chịu trách nhiệm phân loại và giữ ngữ cảnh; tầng sở hữu chính sách nghiệp vụ quyết định retry, fallback hoặc trả lỗi; tầng giao thức chịu trách nhiệm chuyển lỗi thành dạng mà peer hiểu được**.

## 2. Các exception trong Spring Messaging giúp xác định loại lỗi

Gói `org.springframework.messaging` cung cấp exception cơ sở `MessagingException` cho các lỗi liên quan đến messaging. Exception này có thể giữ message gây lỗi qua `getFailedMessage()`, cùng nguyên nhân gốc trong cause chain.

| Exception | Ý nghĩa | Hướng điều tra |
| --- | --- | --- |
| `MessagingException` | Lỗi tổng quát liên quan đến messaging | Xem message thất bại, cause và stack trace để tìm tầng sâu nhất phát sinh lỗi |
| `MessageDeliveryException` | Lỗi trong quá trình chuyển hoặc giao message | Kiểm tra channel, subscriber, dispatcher, destination và trạng thái consumer |
| `MessageHandlingException` | Lỗi trong lúc một handler xử lý message | Kiểm tra `MessageHandler`, controller hoặc component được gọi |
| `MessageConversionException` | Không chuyển đổi được message/payload | Kiểm tra content type, converter, kiểu dữ liệu và cấu trúc payload |
| `DestinationResolutionException` | Không giải quyết được destination | Kiểm tra destination header, prefix, route và cấu hình broker/controller |
| `MethodArgumentResolutionException` | Không phân giải được tham số của handler method | Kiểm tra `@Payload`, `@Header`, kiểu tham số, converter và validation |

Các kiểu exception là manh mối để khoanh vùng, không thay thế việc đọc cause chain. Một lỗi database có thể được bọc trong `MessageHandlingException`; một lỗi gửi outbound có thể xuất hiện dưới dạng `MessageDeliveryException`. Luôn xem `getCause()` hoặc `getMostSpecificCause()` để tìm nguyên nhân gốc.

Ví dụ đọc ngữ cảnh từ một `MessagingException`: 

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;

void logMessagingFailure(MessagingException ex) {
    Message<?> failed = ex.getFailedMessage();

    if (failed != null) {
        Object destination = failed.getHeaders().get("simpDestination");
        Object messageId = failed.getHeaders().getId();
        logger.error("Message failed: id={}, destination={}",
                messageId, destination, ex);
    } else {
        logger.error("Messaging failed before a Message was available", ex);
    }
}
```

Đây là đoạn mã minh họa cho logging; header destination phụ thuộc protocol. Với STOMP, có thể dùng `StompHeaderAccessor` hoặc `SimpMessageHeaderAccessor` để đọc header có kiểu rõ ràng. Với RSocket, route thường được ánh xạ thành metadata/header theo cấu hình `MetadataExtractor`.

Khi ghi log, ưu tiên message id, destination/route, session hoặc connection id, correlation id, loại exception và root cause. Không ghi toàn bộ payload nếu payload có token, dữ liệu cá nhân hoặc thông tin bí mật.

## 3. Phân biệt lỗi giao message và lỗi xử lý message

Đây là một phân biệt hữu ích khi đọc stack trace:

- **Delivery failure** xảy ra khi framework không giao được message tới nơi nhận dự kiến. Hãy kiểm tra channel, subscriber, destination, broker và thời điểm gửi.
- **Handling failure** xảy ra sau khi một handler đã nhận message nhưng quá trình xử lý thất bại. Hãy kiểm tra controller, service, converter/argument binding và dependency mà handler gọi.

Ví dụ: client gửi tới `/app/orders.create`, nhưng destination không được cấu hình để tới controller. Đây là vấn đề định tuyến hoặc dispatch. Nếu `OrderController.create()` đã chạy rồi `OrderService` ném `InventoryUnavailableException`, đây là lỗi trong tầng handler/nghiệp vụ. Hai tình huống có thể cùng xuất hiện như một lỗi messaging ở phía gọi, nhưng cách phục hồi hoàn toàn khác nhau.

Với channel đồng bộ, lỗi có thể truyền ngược về thread gọi `send()`. Với channel hoặc broker xử lý bất đồng bộ, producer có thể đã gửi xong trước khi consumer xử lý. Khi đó producer không thể nhận lỗi consumer bằng một `try/catch` thông thường; cần cơ chế phản hồi bất đồng bộ như error flow, reply, acknowledgement, broker retry hoặc dead-letter policy của nền tảng.

## 4. Xử lý lỗi trong STOMP over WebSocket

Spring STOMP sử dụng nhiều channel có vai trò riêng:

| Channel | Hướng và vai trò |
| --- | --- |
| `clientInboundChannel` | Message từ WebSocket client đi vào ứng dụng Spring |
| `brokerChannel` | Message từ code phía server được gửi tới message broker |
| `clientOutboundChannel` | Message từ broker/ứng dụng được gửi ra WebSocket client |

Thông thường, destination bắt đầu bằng `/app` được định tuyến tới các method `@MessageMapping`; destination `/topic` và `/queue` được xử lý bởi broker. Khi controller trả kết quả, message được đưa qua `brokerChannel`, broker tìm subscriber và gửi tới `clientOutboundChannel`.

### 4.1. Exception từ `@MessageMapping`: dùng `@MessageExceptionHandler`

Khi method `@MessageMapping` ném exception trong quá trình xử lý message, tầng annotated controller là nơi phù hợp để chuyển exception thành response nghiệp vụ. Spring hỗ trợ `@MessageExceptionHandler` với các kiểu tham số và giá trị trả về tương tự `@MessageMapping`.

- Đặt `@MessageExceptionHandler` trong cùng `@Controller` để xử lý lỗi của controller đó.
- Đặt handler trong class có `@ControllerAdvice` nếu cần áp dụng xuyên nhiều controller.
- Trả về một error DTO ổn định để client xử lý theo mã lỗi; không gửi stack trace hoặc chi tiết nội bộ ra ngoài.
- Dùng `@SendToUser` nếu response lỗi chỉ dành cho người gửi message.

```java
@Controller
public class OrderMessageController {

    private final OrderService orderService;

    public OrderMessageController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("/orders.create")
    public OrderAccepted create(@Payload CreateOrder command) {
        return orderService.create(command);
    }

    @MessageExceptionHandler(OrderRejectedException.class)
    @SendToUser("/queue/errors")
    public ClientError handleOrderRejected(OrderRejectedException ex) {
        return new ClientError("ORDER_REJECTED", ex.getSafeMessage());
    }
}
```

Các class `OrderService`, `CreateOrder`, `OrderAccepted`, `OrderRejectedException` và `ClientError` là kiểu do ứng dụng định nghĩa. Đoạn mã minh họa ranh giới xử lý: lỗi nghiệp vụ được chuyển thành thông báo dành cho client. Không nên trả `ex.getMessage()` trực tiếp nếu message có thể chứa SQL, tên bảng, đường dẫn nội bộ hoặc dữ liệu nhạy cảm; dùng một thông điệp an toàn hoặc mã lỗi đã chuẩn hóa.

`@MessageExceptionHandler` giải quyết exception trong annotated message handler. Nó không phải bộ xử lý chung cho lỗi WebSocket handshake, lỗi parse STOMP frame, lỗi broker relay hoặc mọi lỗi xảy ra trước khi controller được gọi.

### 4.2. Lỗi STOMP protocol hoặc xử lý message ở mức sub-protocol

Với lỗi phát sinh khi Spring xử lý message STOMP từ client, hoặc khi có error message từ phía server/broker gửi tới client, có thể tùy chỉnh `StompSubProtocolErrorHandler` thông qua `StompEndpointRegistry.setErrorHandler(...)`.

```java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
        registry.setErrorHandler(new SafeStompErrorHandler());
    }
}

public class SafeStompErrorHandler extends StompSubProtocolErrorHandler {
    // Override handleClientMessageProcessingError(...)
    // and/or handleErrorMessageToClient(...) to build a safe STOMP ERROR frame
    // or return null when the application intentionally suppresses that frame.
}
```

`SafeStompErrorHandler` là lớp tùy chỉnh của ứng dụng; phần override cần tạo message STOMP phù hợp với hợp đồng client. Hai điểm mở rộng chính:

- `handleClientMessageProcessingError(clientMessage, ex)`: xử lý lỗi khi xử lý message từ client. `clientMessage` có thể là `null` nếu lỗi xảy ra trước khi parse được message.
- `handleErrorMessageToClient(errorMessage)`: xử lý error message từ phía server trước khi gửi tới client, ví dụ lỗi relay hoặc lỗi được broker gửi về.

STOMP yêu cầu server đóng connection sau khi gửi frame `ERROR`. Nếu muốn giữ connection và gửi thông báo theo một destination khác, handler có thể trả `null` để không gửi frame `ERROR`, sau đó ứng dụng có thể chủ động gửi notification qua broker, chẳng hạn user destination. Chỉ làm vậy khi lỗi có thể được biểu diễn an toàn và session vẫn còn dùng được.

### 4.3. Lỗi transport WebSocket

Lỗi ở tầng WebSocket khác với lỗi trong method `@MessageMapping`. Ví dụ: lỗi đọc/ghi frame, socket đã đóng hoặc exception không được xử lý trong `WebSocketHandler`. Spring cung cấp `ExceptionWebSocketHandlerDecorator`; trong cấu hình WebSocket tiêu chuẩn, decorator này bắt exception không được xử lý từ các method của `WebSocketHandler` và đóng session với status `1011` (server error).

Vì connection có thể đã hỏng, không nên giả định có thể gửi một message lỗi STOMP tới client. Ghi log với session id và nguyên nhân, giải phóng tài nguyên và để client thực hiện reconnect theo chính sách của ứng dụng.

### 4.4. Broker hoặc broker relay gặp lỗi

Khi dùng broker ngoài như RabbitMQ hoặc ActiveMQ, Spring relay message qua TCP tới broker và nhận message từ broker để chuyển tiếp xuống client. Nếu broker từ chối publish, mất kết nối hoặc gửi error message, lỗi thuộc đường broker/relay. `@MessageExceptionHandler` của controller nghiệp vụ không phải nơi bao quát lỗi này. Dùng broker/relay monitoring và `StompSubProtocolErrorHandler` để kiểm soát cách error message được chuyển tới client.

## 5. Xử lý lỗi trong RSocket

RSocket có các interaction model `Request-Response`, `Request-Stream`, `Channel` và `Fire-and-Forget`. Hai phía có thể đóng vai requester hoặc responder. Trong Spring, `@MessageMapping` xử lý request; `@ConnectMapping` xử lý sự kiện ở cấp connection như `SETUP` và `METADATA_PUSH`.

- Lỗi trong `@ConnectMapping` khi xử lý một connection mới khiến connection bị từ chối. Đây là ranh giới thiết lập connection.
- Lỗi trong một request được xử lý tại responder/request handler. Các method có thể trả về `Mono` hoặc `Flux`; vì vậy lỗi bất đồng bộ phải được xử lý trong reactive chain.
- Khi gọi `RSocketRequester`, xử lý error signal trên `Mono`/`Flux` mà `retrieveMono`, `retrieveFlux` hoặc API tương ứng trả về.
- `Fire-and-Forget` chỉ xác nhận việc gửi message thành công; completion của `send()` không xác nhận remote handler đã xử lý message. Nếu nghiệp vụ cần biết kết quả xử lý, chọn request-response hoặc thiết kế acknowledgement riêng.

Ví dụ ánh xạ lỗi dịch vụ trong reactive handler:

```java
@Controller
public class OrderRSocketController {

    private final OrderService orderService;

    public OrderRSocketController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("orders.create")
    public Mono<OrderAccepted> create(OrderCommand command) {
        return orderService.create(command)
                .onErrorMap(InventoryUnavailableException.class,
                        ex -> new OrderServiceUnavailableException(
                                "Order service is temporarily unavailable", ex));
    }
}
```

Đoạn mã là ví dụ cho Spring RSocket responder; các kiểu nghiệp vụ do ứng dụng định nghĩa. `onErrorMap` giữ nguyên bản chất thất bại nhưng đổi exception sang loại có ý nghĩa ở ranh giới service. Nếu dùng `onErrorResume` để trả fallback như `Mono.just(...)`, response đó trở thành kết quả thành công; chỉ làm vậy khi hợp đồng API định nghĩa rõ trạng thái fallback.

Đối với lỗi reactive, `try/catch` quanh lời gọi tạo `Mono` thường không bắt được exception xảy ra sau đó khi publisher được subscribe. Dùng `onErrorMap`, `onErrorResume` hoặc `doOnError` ở đúng vị trí trong pipeline. `doOnError` phù hợp để quan sát/log; nó không tự khôi phục hoặc thay thế lỗi.

## 6. Spring Integration có errorChannel riêng

Không nên nhầm cơ chế của Spring Integration với `spring-messaging` core. Spring Integration bổ sung flow xử lý lỗi dựa trên message channel:

- Exception từ một task bất đồng bộ có thể được đóng thành `ErrorMessage` và gửi tới channel.
- Nếu message gốc có header `errorChannel`, lỗi được gửi tới channel đó; nếu không, Spring Integration dùng global channel bean tên `errorChannel`.
- Với `DirectChannel`, handler chạy cùng thread gửi message nên exception có thể truyền ngược về caller. Với `ExecutorChannel` hoặc `QueueChannel`, producer có thể đã tiếp tục; lỗi cần được xử lý bất đồng bộ qua error flow.

Ví dụ cấu hình một error channel trong Spring Integration:

```java
@Bean
PublishSubscribeChannel errorChannel() {
    return new PublishSubscribeChannel();
}
```

Đây là cấu hình thuộc Spring Integration và chỉ hữu ích khi flow của ứng dụng thực sự dùng cơ chế error publishing của module đó. Một ứng dụng chỉ dùng `MessageChannel`, `MessageHandler` hoặc STOMP trong Spring Framework không tự động có một global `errorChannel` xử lý mọi exception.

## 7. Quyết định retry, fallback hay chuyển lỗi

Không phải exception nào cũng nên retry. Chọn chính sách theo tính chất lỗi và nơi có thể quan sát kết quả:

| Loại lỗi | Hành động thường phù hợp | Lý do |
| --- | --- | --- |
| Payload sai định dạng, thiếu field, lỗi binding | Trả lỗi validation/conversion có thể sửa; không retry tự động | Gửi lại cùng payload thường thất bại tiếp |
| Lỗi nghiệp vụ như hết hàng hoặc trạng thái không hợp lệ | Trả mã lỗi nghiệp vụ; client quyết định bước tiếp theo | Không phải lỗi hạ tầng tạm thời |
| Timeout hoặc lỗi mạng tạm thời | Retry có giới hạn và backoff nếu thao tác an toàn | Phụ thuộc dịch vụ có phục hồi hay không |
| Broker/consumer tạm thời không sẵn sàng | Dùng retry/acknowledgement theo khả năng của broker hoặc integration flow | Producer có thể không còn giữ call stack ban đầu |
| Message không có route/handler | Sửa cấu hình hoặc trả lỗi destination rõ ràng | Retry không sửa được route sai |
| Lỗi không xác định hoặc lỗi lập trình | Ghi nhận đầy đủ context, phát cảnh báo và chuyển tới cơ chế vận hành | Retry vô hạn có thể làm hệ thống quá tải |

Khi retry một command có side effect, cần idempotency key hoặc cơ chế chống xử lý trùng. Một lần timeout không chứng minh rằng thao tác chưa được thực hiện: server có thể đã commit dữ liệu nhưng response bị mất trên đường về. Retry thiếu kiểm soát có thể tạo đơn hàng hoặc thanh toán hai lần.

Khi chuyển lỗi tới client, nên trả error contract ổn định gồm mã lỗi, thông điệp an toàn và correlation id. Log nội bộ giữ cause chain, stack trace và failed message metadata cần thiết. Không biến exception thành response thành công chỉ để tránh lỗi xuất hiện ở client.

## 8. Quy trình điều tra một lỗi message

1. **Xác định protocol và transport.** Ứng dụng dùng STOMP/WebSocket, RSocket hay Spring Integration channel? Lỗi xảy ra khi kết nối, parse frame, route, xử lý handler hay gửi response?
2. **Tìm điểm cuối cùng đã chạy thành công.** Dùng log theo connection/session id, message id, destination/route và correlation id. Kiểm tra controller có được gọi hay chưa.
3. **Đọc exception ngoài cùng và cause chain.** Ghi nhận loại `MessagingException`, `MessageDeliveryException`, `MessageHandlingException` hoặc exception chuyên biệt; tìm root cause và failed message.
4. **Xác định đồng bộ hay bất đồng bộ.** Nếu cùng thread, caller có thể nhận exception trực tiếp. Nếu qua executor, queue, broker hoặc reactive publisher, cần error flow hoặc signal bất đồng bộ.
5. **Chọn đúng handler.** Lỗi nghiệp vụ của STOMP controller dùng `@MessageExceptionHandler`; lỗi STOMP sub-protocol dùng `StompSubProtocolErrorHandler`; lỗi WebSocket transport xử lý ở WebSocket layer; lỗi RSocket xử lý trong reactive request/connection boundary; lỗi Spring Integration async flow dùng `errorChannel`.
6. **Kiểm tra khả năng phản hồi.** Session/connection còn mở không? Message có reply channel hoặc requester chờ response không? Với Fire-and-Forget, sender không có application acknowledgement mặc định.
7. **Chọn chính sách phục hồi.** Retry có giới hạn cho lỗi transient và thao tác idempotent; trả lỗi nghiệp vụ cho lỗi có thể sửa; đưa message lỗi sang flow vận hành phù hợp nếu xử lý async.
8. **Kiểm tra bằng một tình huống lỗi có chủ đích.** Xác nhận client nhận đúng contract, connection được giữ/đóng đúng quy tắc protocol, lỗi không bị nuốt và không có retry trùng side effect.

## 9. Các lỗi thiết kế thường gặp

- Đặt mọi xử lý vào một `@MessageExceptionHandler` rồi kỳ vọng nó bắt được cả lỗi parse frame, broker hoặc socket.
- Dùng `catch (Exception)` và trả về response rỗng, khiến client không phân biệt được thành công với thất bại.
- Chỉ log exception mà không lưu message id, destination/route hoặc correlation id, khiến không thể nối lỗi giữa các service.
- Retry tất cả lỗi như nhau, kể cả lỗi validation, authorization hoặc command không idempotent.
- Cho rằng gửi vào channel hoặc gọi `send()` đồng nghĩa consumer đã xử lý thành công.
- Dùng `errorChannel` của Spring Integration như thể đó là tính năng global mặc định của mọi ứng dụng Spring Messaging.
- Gửi nguyên stack trace, SQL hoặc thông tin nội bộ về client.

## 10. Ghi nhớ

- `MessagingException` là gốc của nhiều lỗi messaging và có thể giữ `failedMessage`.
- `MessageDeliveryException` gợi ý lỗi giao message; `MessageHandlingException` gợi ý lỗi trong handler.
- STOMP: `@MessageExceptionHandler` dành cho lỗi từ `@MessageMapping`; `StompSubProtocolErrorHandler` dành cho lỗi ở ranh giới sub-protocol và lỗi chuyển tới client.
- WebSocket transport có cơ chế xử lý exception riêng; session có thể bị đóng thay vì nhận error message.
- RSocket: phân biệt lỗi connection (`@ConnectMapping`) với lỗi request (`@MessageMapping`), và xử lý lỗi bất đồng bộ trong `Mono`/`Flux`.
- Spring Integration `errorChannel` là error flow của module Integration, đặc biệt quan trọng với task bất đồng bộ.
- Retry, fallback và error response là chính sách của ứng dụng; chọn theo nguyên nhân, semantics của protocol và khả năng idempotent.

## Tài liệu tham khảo

- [Spring Framework Reference — Flow of Messages (STOMP)](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [Spring Framework Reference — Annotated Controllers and `@MessageExceptionHandler`](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html)
- [Spring Framework API — `MessagingException`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessagingException.html)
- [Spring Framework API — `MessageDeliveryException`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageDeliveryException.html)
- [Spring Framework API — `MessageHandlingException`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHandlingException.html)
- [Spring Framework API — `StompSubProtocolErrorHandler`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/messaging/StompSubProtocolErrorHandler.html)
- [Spring Framework API — `StompEndpointRegistry.setErrorHandler`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/config/annotation/StompEndpointRegistry.html)
- [Spring Framework Reference — WebSockets](https://docs.spring.io/spring-framework/reference/web/websocket.html)
- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/7.0/error-handling.html)