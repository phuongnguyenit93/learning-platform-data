# Đường đi của SUBSCRIBE tới bộ môi giới

> Mục tiêu: lần theo một STOMP `SUBSCRIBE` từ WebSocket client qua các channel và handler của Spring đến simple broker hoặc external STOMP broker; hiểu cách broker lưu subscription, chọn message phù hợp và gửi `MESSAGE` ngược về client; cấu hình ACK, receipt, user destination và authorization đúng với từng loại broker.

## 1. SUBSCRIBE làm nhiệm vụ gì?

Trong STOMP, `SUBSCRIBE` đăng ký một client để nhận message từ một destination. Client gửi frame có `destination` và `id`; server tạo subscription và từ đó có thể gửi các frame `MESSAGE` phù hợp về client. `SUBSCRIBE` không gửi payload nghiệp vụ như `SEND`; nó khai báo nơi client muốn nghe.

Ví dụ:

```text
SUBSCRIBE
id:prices-sub-1
destination:/topic/prices
ack:auto

^@
```

`id` là mã subscription duy nhất trong một STOMP connection. `destination` là tên đích mà broker hiểu. `ack` chọn cách client xác nhận message được giao; nếu bỏ qua, STOMP mặc định là `auto`. `^@` trong ví dụ biểu diễn byte NULL (`0x00`) kết thúc frame.

STOMP xem destination là chuỗi opaque. `/topic` thường được dùng cho publish-subscribe và `/queue` thường được dùng cho point-to-point, nhưng semantics thực tế do broker và cấu hình quyết định. Không suy ra bảo đảm delivery chỉ từ tên prefix.

## 2. Toàn bộ đường đi trong Spring

Khi client đã mở WebSocket và STOMP session, một frame `SUBSCRIBE` đi qua các thành phần chính sau:

```text
WebSocket client
      |
      | STOMP SUBSCRIBE
      v
WebSocket transport / STOMP decoder
      |
      v
clientInboundChannel
      |
      +--> ChannelInterceptor / Spring Security
      |
      |
      +--> UserDestinationMessageHandler (/user/...)
      |
      |
      +--> SimpAnnotationMethodMessageHandler (@SubscribeMapping)
      |
      +--> SimpleBrokerMessageHandler
      |          hoặc
      +--> StompBrokerRelayMessageHandler
                         |
                         v
                 External STOMP broker

Broker phát message phù hợp
      |
      v
clientOutboundChannel
      |
      v
STOMP encoder / WebSocket session
      |
      v
WebSocket client nhận MESSAGE
```

Ở tầng transport, Spring giải mã frame STOMP thành một Spring `Message<?>`, chuyển các header protocol thành message headers rồi gửi message vào `clientInboundChannel`. Các handler đăng ký trên channel xử lý message theo loại (`SUBSCRIBE`, `MESSAGE`, `UNSUBSCRIBE`) và destination.

Với destination broker thông thường như `/topic/prices`, message đi tới broker handler. Với destination `/user/...`, Spring có bước phân giải user destination. Với destination ứng dụng được ánh xạ bằng `@SubscribeMapping`, controller có thể trả một response trực tiếp cho client. Các nhánh này cần được phân biệt khi đọc log hoặc debug.

## 3. Bước 1 — giải mã frame và tạo Spring Message

Client gửi `SUBSCRIBE` trên WebSocket. Spring chuyển frame thành message có các thông tin quan trọng như:

- Message type tương ứng `SUBSCRIBE`.
- Destination, ví dụ `/topic/prices`.
- Subscription ID, ví dụ `prices-sub-1`.
- WebSocket session ID để xác định kết nối.
- `Principal`/user nếu HTTP handshake đã được xác thực.
- Các header STOMP khác như `ack`, `receipt` và header mở rộng của broker.

Các header nội bộ Spring thường được truy cập qua `SimpMessageHeaderAccessor` hoặc `StompHeaderAccessor`. Application code nên dùng accessor thay vì tự đoán tên header nội bộ.

Một frame hợp lệ phải có `destination` và `id`. Nếu thiếu header bắt buộc, dùng subscription ID đã tồn tại trong cùng connection hoặc broker không thể tạo subscription, server có thể trả `ERROR` theo STOMP protocol. Mỗi connection được phép có nhiều subscription, nhưng ID của chúng phải khác nhau.

## 4. Bước 2 — clientInboundChannel và interceptor

`clientInboundChannel` là đường vào chung cho message từ WebSocket client. Đây là nơi ứng dụng có thể áp dụng các xử lý trước khi message đến broker:

- Xác thực và authorization theo user, message type và destination.
- Kiểm tra subscription có nằm trong phạm vi tenant hoặc room mà user được phép truy cập.
- Ghi log/audit với session ID, subscription ID và destination.
- Đo số lượng subscription, tần suất subscribe/unsubscribe và lỗi.
- Chặn destination không hợp lệ hoặc header vượt giới hạn.

Một `ChannelInterceptor` có thể kiểm tra message trong `preSend`. Nếu interceptor trả về `null`, message không được chuyển tiếp qua channel. Khi từ chối, ứng dụng nên ghi nhận lý do an toàn để vận hành có thể điều tra mà không làm lộ token hoặc dữ liệu nhạy cảm.

Không coi việc client gửi được một destination là bằng chứng họ có quyền đọc destination đó. Subscription là quyền đọc dữ liệu; cần kiểm tra quyền trước khi broker lưu subscription.

## 5. Bước 3 — định tuyến theo destination prefix

Với cấu hình STOMP phổ biến, Spring dùng các prefix để phân biệt destination dành cho controller và destination dành cho broker:

| Destination | Thành phần xử lý | Mục đích |
|---|---|---|
| `/app/...` | `SimpAnnotationMethodMessageHandler` khi có `@SubscribeMapping` phù hợp | Response một lần khi client subscribe vào endpoint ứng dụng |
| `/topic/...` | Simple broker hoặc broker relay | Subscription nhận broadcast từ publisher |
| `/queue/...` | Simple broker hoặc broker relay | Subscription theo semantics queue do broker cung cấp |
| `/user/...` | `UserDestinationMessageHandler` | Chuyển tên đích tổng quát thành destination riêng cho user/session |

Prefix `/topic` và `/queue` là quy ước thường dùng. STOMP không bắt buộc mọi broker phải định nghĩa chúng giống nhau. Hãy kiểm tra destination syntax, wildcard, queue semantics và subscription options của broker thực tế.

Ví dụ cấu hình simple broker:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
class StompConfiguration implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
```

Trong cấu hình này, `/ws` là endpoint HTTP dùng cho WebSocket handshake. `/app` dành cho message đi vào controller; `/topic` và `/queue` được chuyển đến simple broker. Một `SUBSCRIBE` đến `/topic/prices` đi đến broker handler, còn `SUBSCRIBE` đến `/app/...` chỉ được xử lý nếu có mapping như `@SubscribeMapping`.

## 6. Nhánh `@SubscribeMapping`: response một lần từ ứng dụng

`@SubscribeMapping` ánh xạ một STOMP `SUBSCRIBE` vào method controller. Nó hữu ích khi client cần lấy snapshot ban đầu, ví dụ trạng thái hiện tại của một bảng giá hoặc nội dung một phòng chat.

Ví dụ:

```java
import org.springframework.messaging.handler.annotation.DestinationVariable;
import org.springframework.messaging.simp.annotation.SubscribeMapping;
import org.springframework.stereotype.Controller;

@Controller
class RoomSnapshotController {

    private final RoomService roomService;

    RoomSnapshotController(RoomService roomService) {
        this.roomService = roomService;
    }

    @SubscribeMapping("/room/{roomId}/snapshot")
    public RoomSnapshot snapshot(@DestinationVariable String roomId) {
        return roomService.currentSnapshot(roomId);
    }
}
```

Client subscribe vào `/app/room/42/snapshot`. Mặc định, giá trị trả về được gửi trực tiếp qua `clientOutboundChannel` tới client đó; response không đi qua broker và không tạo subscription broadcast lâu dài. Nếu muốn gửi kết quả qua broker, có thể dùng `@SendTo` hoặc `@SendToUser`.

Một pattern phổ biến là dùng hai subscription: `/app/room/42/snapshot` để lấy trạng thái ban đầu và `/topic/room/42/events` để nhận cập nhật liên tục. Không ánh xạ cùng một prefix cho controller và broker nếu không chủ ý cho cả hai xử lý cùng message; các handler có thể chạy song song và không có bảo đảm thứ tự xử lý giữa chúng.

## 7. Nhánh `/user`: phân giải destination theo người dùng

Spring nhận diện destination bắt đầu bằng `/user/` và chuyển qua `UserDestinationMessageHandler`. Ví dụ client subscribe:

```text
SUBSCRIBE
id:private-updates
destination:/user/queue/position-updates

^@
```

Spring chuyển destination tổng quát thành destination vật lý riêng cho user session, chẳng hạn `/queue/position-updates-user123`. Tên vật lý là chi tiết nội bộ; client chỉ cần biết destination `/user/queue/position-updates`.

Cách này tránh việc hai user subscribe cùng một tên tổng quát rồi nhận nhầm message riêng của nhau. Khi gửi đến user, server có thể dùng `SimpMessagingTemplate.convertAndSendToUser(username, "/queue/position-updates", payload)` hoặc `@SendToUser`.

Nếu một user có nhiều WebSocket session, mặc định message có thể được gửi đến tất cả session đang subscribe destination đó. Với `@SendToUser(broadcast = false)`, Spring chỉ gửi về session đã tạo message. Trong môi trường nhiều application node, cần cấu hình broadcast cho user destination chưa phân giải nếu user có thể đang kết nối ở node khác.

Khi dùng external broker, kiểm tra cơ chế dọn các queue vật lý không còn hoạt động. Broker có thể cần auto-delete hoặc policy purge destination sau khi WebSocket session kết thúc.

## 8. Nhánh simple broker: lưu subscription trong bộ nhớ

`SimpleBrokerMessageHandler` là broker tích hợp trong Spring. Khi nhận `SUBSCRIBE`, nó ghi nhận subscription trong registry nội bộ, gắn destination với session ID và subscription ID. Broker giữ thông tin này trong bộ nhớ của application process.

Khi có message được gửi tới destination, simple broker tìm các subscription khớp destination rồi tạo message outbound cho từng session phù hợp. Nó hỗ trợ destination dạng path và Ant-style pattern, ví dụ `/topic/prices.*` hoặc `/topic/room/**` tùy `PathMatcher` và cấu hình.

Simple broker phù hợp để bắt đầu, demo hoặc ứng dụng nhỏ có yêu cầu broadcast cơ bản. Nó lưu subscription trong bộ nhớ, chỉ phục vụ các kết nối mà instance đó quản lý và không phù hợp làm broker phân tán cho nhiều node.

Simple broker chỉ hỗ trợ một phần STOMP protocol; nó không hỗ trợ ACK, RECEIPT và một số tính năng broker đầy đủ. Nếu ứng dụng cần xác nhận message, semantics queue nâng cao, durability hoặc clustering, hãy dùng external STOMP broker qua broker relay.

## 9. Nhánh broker relay: chuyển SUBSCRIBE đến broker bên ngoài

Khi bật `enableStompBrokerRelay`, `StompBrokerRelayMessageHandler` nhận các message dành cho broker và chuyển chúng qua TCP đến broker hỗ trợ STOMP như RabbitMQ hoặc ActiveMQ.

Ví dụ cấu hình:

```java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableStompBrokerRelay("/topic", "/queue")
            .setRelayHost("broker.internal")
            .setRelayPort(61613);
}
```

Relay chuyển frame `SUBSCRIBE` đến broker. Broker bên ngoài chịu trách nhiệm tạo subscription, lưu trạng thái cần thiết, chọn message và phát `MESSAGE` theo semantics của destination. Spring relay nhận frame broker trả về và định tuyến chúng về đúng WebSocket client/session.

Relay duy trì một TCP connection hệ thống cho message phát sinh từ server-side application và một TCP connection riêng cho mỗi WebSocket client. Các connection đại diện client được relay gắn credential cấu hình. Broker quản lý subscription thực tế, còn Spring duy trì liên kết giữa kết nối client và connection TCP tương ứng.

Nếu broker mất kết nối, relay tự thử kết nối lại system connection. Các client connection không tự được khôi phục như một session cũ; client cần phát hiện lỗi, kết nối lại và gửi lại các subscription. Hãy dùng `BrokerAvailabilityEvent` để theo dõi trạng thái system connection và chuẩn bị xử lý `MessageDeliveryException` khi broker không sẵn sàng.

## 10. Bước 4 — broker khớp destination và phát MESSAGE

Khi publisher gửi message đến destination đã có subscription, broker chọn các subscription phù hợp theo semantics của destination và policy broker. Với STOMP, message gửi về client dùng frame `MESSAGE`.

Ví dụ:

```text
MESSAGE
subscription:prices-sub-1
message-id:msg-9081
destination:/topic/prices
content-type:application/json

{"symbol":"ABC","price":125.50}
^@
```

Các header quan trọng:

- `subscription`: phải khớp với `id` của subscription client đã tạo.
- `message-id`: định danh message do server/broker cung cấp.
- `destination`: destination mà message được gửi đến.
- `ack`: có mặt khi subscription dùng `client` hoặc `client-individual`; giá trị này được dùng trong frame ACK/NACK.

Broker cũng có thể chuyển tiếp các header ứng dụng từ message gốc và thêm header riêng. Không giả định header mở rộng của một broker có mặt ở broker khác.

## 11. Bước 5 — clientOutboundChannel trả message về WebSocket

Message do broker phát được Spring đưa vào `clientOutboundChannel`. Channel này chuyển message đến WebSocket session tương ứng; STOMP encoder tạo frame `MESSAGE` và gửi qua kết nối WebSocket.

Vì `clientOutboundChannel` thường được hỗ trợ bởi thread pool, thứ tự message client nhận có thể khác thứ tự broker publish. Nếu nghiệp vụ cần giữ thứ tự publish trong cùng client session, có thể bật `registry.setPreservePublishOrder(true)`. Tùy chọn này tăng chi phí xử lý nên chỉ bật khi cần.

Spring Security tập trung bảo vệ `clientInboundChannel`; nó không kiểm tra từng message trên `clientOutboundChannel` vì một message đầu vào có thể tạo nhiều message đầu ra. Do đó, quyền subscribe cần được kiểm tra chặt chẽ trước khi broker lưu subscription. Một subscription được phép đọc có thể khiến client nhận nhiều message về sau.

## 12. Subscription ID và vòng đời subscription

STOMP 1.2 yêu cầu `id` trong `SUBSCRIBE`. Trong cùng một connection, mỗi subscription phải có ID riêng. ID này liên kết:

- Frame `SUBSCRIBE` ban đầu.
- Header `subscription` trong các frame `MESSAGE` tương ứng.
- Frame `UNSUBSCRIBE` dùng để xóa subscription.

Ví dụ unsubscribe:

```text
UNSUBSCRIBE
id:prices-sub-1

^@
```

Một client có thể subscribe cùng destination nhiều lần với ID khác nhau; tùy broker, mỗi subscription có thể tạo một luồng giao riêng. Tránh đăng ký lặp ngoài ý muốn khi reconnect hoặc khi UI component được mount nhiều lần. Client nên lưu handle subscription và gọi unsubscribe khi không còn cần nhận dữ liệu.

Khi WebSocket session đóng, Spring/broker dọn các subscription gắn với connection đó. Với external broker, queue vật lý hoặc durable subscription có thể có vòng đời riêng do broker cấu hình; cần đọc tài liệu provider.

## 13. ACK mode: client xác nhận message sau khi subscribe

Header `ack` trong `SUBSCRIBE` quyết định cách xác nhận message nhận được:

| Giá trị | Ý nghĩa |
|---|---|
| `auto` | Client không cần gửi ACK; server xem message đã được nhận ngay khi gửi. Đây là mặc định nếu bỏ header và có thể làm mất message khi client chưa xử lý xong. |
| `client` | Client gửi ACK; xác nhận có tính cộng dồn cho message được chỉ định và các message trước đó trên subscription. |
| `client-individual` | Client gửi ACK riêng cho từng message; ACK một message không xác nhận các message trước. |

Với `client` hoặc `client-individual`, frame `MESSAGE` có header `ack` để client dùng trong `ACK` hoặc `NACK`. `NACK` báo client không xử lý message; broker có thể giao lại, loại bỏ hoặc đưa vào DLQ theo khả năng và policy của broker.

Ví dụ client-individual:

```text
SUBSCRIBE
id:orders-sub-1
destination:/queue/orders
ack:client-individual

^@

MESSAGE
subscription:orders-sub-1
message-id:broker-message-55
ack:ack-token-55
destination:/queue/orders

{"orderId":"ORD-55"}
^@

ACK
id:ack-token-55

^@
```

Giá trị trong `ACK.id` của STOMP 1.2 phải khớp với header `ack` của frame `MESSAGE`. ACK xác nhận việc client đã xử lý message theo giao thức; nó không tự động commit database hoặc bảo đảm side effect nghiệp vụ đã hoàn tất. Client vẫn cần xử lý duplicate và lưu trạng thái nghiệp vụ bền vững.

Simple broker của Spring không hỗ trợ ACK/NACK. Nếu ứng dụng cần client acknowledgement, redelivery hoặc dead-letter behavior theo broker, hãy dùng broker relay và xác nhận provider hỗ trợ đúng semantics.

## 14. Receipt: xác nhận broker đã xử lý SUBSCRIBE

Client có thể thêm header `receipt` vào `SUBSCRIBE` để yêu cầu server trả frame `RECEIPT` sau khi xử lý frame đó:

```text
SUBSCRIBE
id:prices-sub-1
destination:/topic/prices
receipt:prices-sub-ready

^@

RECEIPT
receipt-id:prices-sub-ready

^@
```

Receipt hữu ích khi client cần biết subscription đã được server xử lý trước khi thực hiện bước tiếp theo. Nó xác nhận xử lý frame ở tầng protocol; nó không xác nhận rằng message nghiệp vụ đã được gửi hoặc consumer đã xử lý message.

Simple broker không hỗ trợ RECEIPT. Với simple broker, `SessionSubscribeEvent` cho biết Spring đã nhận frame SUBSCRIBE; nếu cần biết broker handler đã xử lý subscription xong, Spring cung cấp lựa chọn server-side là `ExecutorChannelInterceptor` trên `brokerChannel` và callback `afterMessageHandled`. Với external broker, hãy kiểm tra receipt support và semantics trong tài liệu broker.

Không nhầm `SessionSubscribeEvent` với receipt xác nhận subscription đã sẵn sàng. Event là tín hiệu lifecycle trong Spring; receipt là phản hồi protocol từ server/broker.

## 15. `SessionSubscribeEvent` và quan sát subscription

Spring phát `SessionSubscribeEvent` khi nhận một frame `SUBSCRIBE`. Event có thể dùng để audit hoặc ghi nhận session, user, destination và subscription ID.

Ví dụ:

```java
import org.springframework.context.event.EventListener;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.messaging.SessionSubscribeEvent;

@Component
class SubscriptionAuditListener {

    @EventListener
    public void onSubscribe(SessionSubscribeEvent event) {
        SimpMessageHeaderAccessor headers =
                SimpMessageHeaderAccessor.wrap(event.getMessage());

        String sessionId = headers.getSessionId();
        String subscriptionId = headers.getSubscriptionId();
        String destination = headers.getDestination();

        // Ghi audit/metrics; kiểm tra quyền đã được xử lý ở inbound channel.
    }
}
```

Không ghi token, cookie hoặc toàn bộ payload nhạy cảm vào audit log. Có thể kết hợp `SessionUnsubscribeEvent` để theo dõi việc client hủy subscription và `SessionDisconnectEvent` để dọn trạng thái gắn với session. Disconnect event có thể xuất hiện nhiều hơn một lần; logic cleanup cần idempotent.

## 16. Bảo vệ quyền SUBSCRIBE bằng Spring Security

Spring Security phân biệt message type `MESSAGE` (thường tương ứng client gửi `SEND`) và `SUBSCRIBE`. Hai quyền này phải được xét riêng:

- Cho phép user subscribe `/topic/system/notifications` để đọc thông báo.
- Không cho client gửi `MESSAGE` trực tiếp vào `/topic/system/notifications`, nếu không client có thể giả mạo message hệ thống.
- Chỉ cho user subscribe `/user/**` hoặc `/topic/private/**` khi đã đăng nhập và có quyền phù hợp.
- Kiểm tra quyền theo tenant/room/resource khi destination chứa mã tài nguyên.

Ví dụ authorization manager cho Spring Security hiện đại:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.socket.EnableWebSocketSecurity;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;
import org.springframework.messaging.simp.SimpMessageType;

@Configuration
@EnableWebSocketSecurity
class WebSocketSecurityConfiguration {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {
        messages
                .nullDestMatcher().authenticated()
                .simpSubscribeDestMatchers("/topic/announcements").permitAll()
                .simpSubscribeDestMatchers("/topic/private/**", "/user/**").hasRole("USER")
                .simpSubscribeDestMatchers("/app/**").denyAll()
                .simpDestMatchers("/app/**").hasRole("USER")
                .simpTypeMatchers(SimpMessageType.MESSAGE, SimpMessageType.SUBSCRIBE).denyAll()
                .anyMessage().denyAll();
        return messages.build();
    }
}
```

Các rule được xét theo thứ tự khai báo. Ví dụ cho phép đọc thông báo công khai, yêu cầu role `USER` với topic riêng và user destination, chặn subscribe vào `/app/**`, chỉ cho user gửi message vào `/app/**`, rồi từ chối các loại message còn lại. Điều chỉnh matcher theo destination và role thực tế của ứng dụng.

`@EnableWebSocketSecurity` cũng yêu cầu CSRF token cho STOMP `CONNECT` theo cấu hình mặc định. HTTP handshake phải được xác thực; `Principal` được Spring truyền vào WebSocket messaging. Authorization trên `SUBSCRIBE` đặc biệt quan trọng vì Spring Security không lọc riêng từng message outbound.

## 17. `SUBSCRIBE` khác `SEND` và `@MessageMapping` thế nào?

| Frame / mapping | Vai trò | Đường đi phổ biến |
|---|---|---|
| `SUBSCRIBE /topic/...` | Đăng ký nhận message lặp lại | `clientInboundChannel` → broker → subscription registry |
| `SEND /app/...` | Gửi yêu cầu nghiệp vụ vào ứng dụng | `clientInboundChannel` → `@MessageMapping` |
| `SUBSCRIBE /app/...` với `@SubscribeMapping` | Lấy response một lần từ controller | `clientInboundChannel` → `@SubscribeMapping` → `clientOutboundChannel` |
| `SUBSCRIBE /user/...` | Đăng ký nhận message riêng của user/session | `clientInboundChannel` → `UserDestinationMessageHandler` → broker |

Một `@MessageMapping` thông thường xử lý message gửi đến application destination; nó không phải handler mặc định cho subscription. `@SubscribeMapping` mới là mapping dành cho frame SUBSCRIBE.

## 18. Destination pattern, selector và giới hạn theo broker

STOMP cho phép server hỗ trợ header mở rộng trên `SUBSCRIBE` để điều chỉnh delivery semantics, ví dụ selector hoặc durable subscription. Các header đó không phải tính năng portable của mọi broker.

Simple broker hỗ trợ path-like destination và Ant-style pattern theo cấu hình Spring. External broker có thể dùng cú pháp destination, wildcard, selector, durable subscription hoặc shared subscription riêng. Hãy đối chiếu tài liệu broker trước khi đưa extension header vào client.

Nếu destination là `/queue/orders`, không thể kết luận mọi broker sẽ phân phối message theo cùng một cách. Có broker dùng competing consumers, có broker hỗ trợ subscription riêng, durable consumer hoặc policy khác. Semantics queue/topic là trách nhiệm của broker.

## 19. Thứ tự message và concurrency

Spring dùng executor-backed channel cho inbound và outbound messaging. Khi nhiều message được xử lý song song, thứ tự xử lý hoặc thứ tự client nhận có thể khác thứ tự chúng đi vào channel hoặc được broker publish.

Nếu cần giữ thứ tự outbound trong cùng session, dùng `MessageBrokerRegistry.setPreservePublishOrder(true)`. Nếu cần giữ thứ tự nhận inbound theo session, có thể cấu hình `StompEndpointRegistry.setPreserveReceiveOrder(true)`. Cả hai lựa chọn có chi phí hiệu năng; chỉ bật khi yêu cầu nghiệp vụ cần.

Subscription nhiều session cũng có thể nhận cùng message trên topic. Với queue, cách phân phối cho nhiều consumer do broker định nghĩa. Hãy kiểm thử ordering, duplicate, concurrency và khả năng chịu tải với đúng broker.

## 20. Lỗi thường gặp khi lần theo SUBSCRIBE

- **Nhầm `/app` với broker prefix:** `/app` thường được dành cho controller; `/topic` và `/queue` mới được chuyển đến broker theo cấu hình ví dụ.
- **Dùng `@MessageMapping` để xử lý subscription:** dùng `@SubscribeMapping` cho response gắn với SUBSCRIBE.
- **Nghĩ rằng `@SubscribeMapping` tạo subscription lâu dài:** response mặc định đi thẳng về client và không được lưu trong broker registry.
- **Không gửi subscription ID hoặc dùng ID trùng:** `MESSAGE`, `ACK` và `UNSUBSCRIBE` không thể liên kết đúng subscription.
- **Tin `/topic` luôn có semantics giống nhau:** STOMP để destination semantics cho broker quyết định.
- **Dùng simple broker nhưng kỳ vọng ACK/RECEIPT:** simple broker không hỗ trợ các tính năng này.
- **Chỉ bảo vệ SEND mà bỏ qua SUBSCRIBE:** client có thể đọc dữ liệu riêng nếu được phép đăng ký destination không phù hợp.
- **Cho phép client MESSAGE trực tiếp vào broker topic:** có thể tạo khả năng giả mạo message hệ thống.
- **Coi SessionSubscribeEvent là xác nhận broker đã lưu subscription:** event cho biết Spring nhận frame; dùng receipt khi broker hỗ trợ hoặc theo dõi broker handler hoàn tất.
- **Cho rằng broker relay tự phục hồi mọi client session:** relay tự khôi phục system connection; client cần reconnect và subscribe lại.
- **Quên hủy subscription khi component không còn dùng:** có thể tiếp tục nhận message và giữ tài nguyên không cần thiết.
- **Giả định outbound channel được Spring Security lọc từng message:** cần bảo vệ subscription ở inbound channel.

## 21. Kiểm thử đường đi của SUBSCRIBE

Nên kiểm thử với WebSocket/STOMP client và broker thực tế:

1. Client CONNECT thành công rồi SUBSCRIBE destination hợp lệ; xác nhận broker nhận đăng ký.
2. Publisher gửi message vào đúng destination; client nhận `MESSAGE` có `subscription` khớp ID đã đăng ký.
3. Publisher gửi vào destination khác; client không nhận message ngoài subscription.
4. Client gửi nhiều SUBSCRIBE với ID khác nhau; xác nhận mỗi subscription được phân biệt.
5. Client gửi ID trùng hoặc thiếu destination/id; xác nhận lỗi theo protocol/server.
6. Client UNSUBSCRIBE; các message tiếp theo không còn được gửi qua subscription đó.
7. Client disconnect; subscription gắn với session được dọn theo broker policy.
8. Kiểm tra `/user/queue/...`: user nhận message riêng và user khác không đọc được.
9. Kiểm tra `@SubscribeMapping`: response snapshot về đúng session và không tạo broadcast ngoài ý muốn.
10. Kiểm tra `ack:auto`, `ack:client`, `ack:client-individual`, ACK/NACK nếu broker hỗ trợ.
11. Kiểm tra receipt trên SUBSCRIBE; xác nhận simple broker không hỗ trợ và external broker phản hồi đúng nếu có.
12. User không có quyền subscribe private topic bị từ chối; user không thể SEND trực tiếp vào broker topic bị cấm.
13. Restart broker relay; client phát hiện disconnect, reconnect và đăng ký lại subscription.
14. Gửi nhiều message đồng thời; kiểm tra ordering, duplicate, latency và queue depth.

Khi debug, ghi nhận STOMP command, destination, session ID, subscription ID, user, broker type, thời điểm nhận SUBSCRIBE, thời điểm receipt (nếu có), message ID và kết quả authorization. Không ghi credential hoặc payload nhạy cảm.

## 22. Quy trình triển khai subscription

1. Chọn destination và xác định nó thuộc controller, user destination hay broker.
2. Định nghĩa broker/application prefixes nhất quán trong `MessageBrokerRegistry`.
3. Chọn simple broker cho broadcast cơ bản hoặc broker relay cho ACK, receipt, durability, clustering và tính năng broker đầy đủ.
4. Gửi SUBSCRIBE với ID duy nhất, destination đúng và ACK mode phù hợp.
5. Bảo vệ SUBSCRIBE theo Principal, role, tenant và resource; chặn client SEND vào destination chỉ dành cho broker.
6. Dùng `/user` cho message riêng và `@SubscribeMapping` cho response snapshot một lần.
7. Xác nhận subscription đã sẵn sàng bằng receipt nếu broker hỗ trợ; phân biệt event lifecycle với receipt protocol.
8. Theo dõi MESSAGE outbound, ACK/NACK, UNSUBSCRIBE và disconnect; cleanup idempotent.
9. Kiểm thử routing, authorization, user isolation, broker restart, ordering và provider-specific semantics.

## 23. Kết luận

Một frame `SUBSCRIBE` đi từ WebSocket qua STOMP decoder vào `clientInboundChannel`, qua interceptor và authorization, rồi được định tuyến theo destination. Destination broker được xử lý bởi `SimpleBrokerMessageHandler` hoặc `StompBrokerRelayMessageHandler`; destination `/user` được Spring phân giải theo user/session; destination ứng dụng có thể được xử lý bằng `@SubscribeMapping`.

Broker lưu subscription, khớp message publish với destination và phát frame `MESSAGE` qua `clientOutboundChannel` về đúng WebSocket session. Subscription ID liên kết SUBSCRIBE, MESSAGE và UNSUBSCRIBE; ACK mode quyết định cách client xác nhận message. Hãy chọn broker theo tính năng cần thiết, xác thực quyền đọc ngay tại SUBSCRIBE, và kiểm thử cả chiều đăng ký lẫn chiều message trả về.

## Tài liệu tham khảo

- [STOMP Protocol Specification 1.2 — SUBSCRIBE, ACK, NACK and MESSAGE](https://stomp.github.io/stomp-specification-1.2.html)
- [Spring Framework Reference — Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [Spring Framework Reference — Simple Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html)
- [Spring Framework Reference — External Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html)
- [Spring Framework Reference — User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html)
- [Spring Framework Reference — Annotated Controllers and @SubscribeMapping](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html)
- [Spring Security Reference — WebSocket Authorization](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html)
- [Spring Framework Reference — Application Context Events](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html)
- [Spring Framework Reference — Order of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/ordered-messages.html)