# SessionConnectEvent, SessionConnectedEvent và các sự kiện đăng ký trong Spring STOMP

## Mục tiêu và phạm vi

Spring Framework phát các sự kiện trong ApplicationContext để thông báo những mốc quan trọng trong vòng đời của một STOMP session chạy trên WebSocket hoặc SockJS. Các event này giúp ứng dụng theo dõi kết nối, trạng thái đăng ký subscription, phiên người dùng và việc ngắt kết nối.

Những event thường gặp gồm:

- **SessionConnectEvent:** Spring nhận được STOMP CONNECT từ một client. Đây là dấu hiệu client bắt đầu quy trình kết nối ở tầng STOMP.
- **SessionConnectedEvent:** broker đã phản hồi STOMP CONNECTED. Tại thời điểm này, STOMP session được xem là đã thiết lập thành công.
- **SessionSubscribeEvent:** Spring nhận được một STOMP SUBSCRIBE.
- **SessionUnsubscribeEvent:** Spring nhận được một STOMP UNSUBSCRIBE.
- **SessionDisconnectEvent:** STOMP session kết thúc.

Cần phân biệt các event này với sự kiện WebSocket handshake. WebSocket có thể đã được nâng cấp thành công nhưng client vẫn chưa gửi STOMP CONNECT. Ngược lại, nhận được CONNECT cũng chưa chứng minh broker đã chấp nhận và gửi CONNECTED. Hai mốc này có ý nghĩa khác nhau khi theo dõi trạng thái và đo lường hiệu năng.

Nội dung tập trung vào Spring Framework STOMP over WebSocket/SockJS, các ApplicationContext event, cách đọc message header và cách quản lý trạng thái session/subscription. Các event này là thông báo vòng đời, không thay thế ChannelInterceptor để xử lý từng message hoặc cơ chế authorization.

## 1. Vòng đời của một STOMP session

Một client thường đi qua các bước sau:

1. Mở kết nối HTTP/WebSocket hoặc SockJS tới ứng dụng Spring.
2. Gửi STOMP CONNECT.
3. Spring phát **SessionConnectEvent** khi nhận CONNECT.
4. Broker hoặc simple broker phản hồi STOMP CONNECTED.
5. Spring phát **SessionConnectedEvent**.
6. Client gửi SUBSCRIBE; Spring phát **SessionSubscribeEvent**.
7. Client có thể gửi UNSUBSCRIBE; Spring phát **SessionUnsubscribeEvent**.
8. Khi client gửi DISCONNECT hoặc transport đóng, Spring phát **SessionDisconnectEvent**.

~~~mermaid
sequenceDiagram
    participant Client
    participant Spring as Spring WebSocket/STOMP
    participant Broker as Simple broker / relay
    participant Listener as Application event listener
    Client->>Spring: WebSocket handshake
    Client->>Spring: STOMP CONNECT
    Spring->>Listener: SessionConnectEvent
    Spring->>Broker: CONNECT
    Broker-->>Spring: CONNECTED
    Spring->>Listener: SessionConnectedEvent
    Spring-->>Client: CONNECTED
    Client->>Spring: SUBSCRIBE
    Spring->>Listener: SessionSubscribeEvent
    Spring->>Broker: SUBSCRIBE
    Client->>Spring: UNSUBSCRIBE
    Spring->>Listener: SessionUnsubscribeEvent
    Spring->>Broker: UNSUBSCRIBE
    Client->>Spring: DISCONNECT / transport close
    Spring->>Listener: SessionDisconnectEvent
~~~

Sơ đồ thể hiện thứ tự khái niệm. Chi tiết thời điểm gửi event có thể phụ thuộc message channel và broker đang dùng; không nên dựa vào listener để điều khiển handshake hoặc chặn message.

## 2. SessionConnectEvent và SessionConnectedEvent

### 2.1. SessionConnectEvent: nhận được yêu cầu CONNECT

**SessionConnectEvent** được phát khi Spring nhận một frame STOMP CONNECT từ client. Event đánh dấu lần thử bắt đầu STOMP session, không phải thời điểm WebSocket handshake vừa hoàn tất.

Event chứa message đại diện cho CONNECT. Từ message có thể đọc:

- Session ID do Spring gắn cho WebSocket session.
- Principal nếu đã có từ HTTP handshake hoặc đã được thiết lập trước đó.
- Các native STOMP header mà client gửi.
- Thông tin message header khác phục vụ tracing.

Đây là mốc thích hợp để ghi nhận một yêu cầu kết nối, thống kê số lần client bắt đầu STOMP handshake hoặc ghi audit metadata an toàn. Nó chưa chứng minh broker đã phản hồi CONNECTED.

### 2.2. SessionConnectedEvent: STOMP session đã thiết lập

**SessionConnectedEvent** được phát ngay sau SessionConnectEvent khi broker gửi frame STOMP CONNECTED để trả lời CONNECT. Tại đây, STOMP session có thể được xem là đã thiết lập đầy đủ.

Đây là mốc phù hợp để:

- Đánh dấu session là ACTIVE.
- Bắt đầu tính thời lượng session đã kết nối.
- Cập nhật presence của user.
- Cho phép tác vụ phụ thuộc vào một STOMP session đã sẵn sàng.
- Ghi nhận thời gian từ CONNECT tới CONNECTED để đo latency handshake.

Nếu chỉ đo số CONNECT nhận được, ứng dụng có thể tính cả các lần kết nối không hoàn tất. Để đo số session STOMP thành công, hãy dựa vào SessionConnectedEvent.

### 2.3. Bảng so sánh

| Tiêu chí | SessionConnectEvent | SessionConnectedEvent |
|---|---|---|
| Thời điểm | Spring nhận CONNECT | Broker trả CONNECTED |
| Ý nghĩa | Client bắt đầu STOMP handshake | STOMP session đã được thiết lập |
| Đảm bảo broker chấp nhận CONNECT? | Chưa | Có, đã có CONNECTED response |
| Dữ liệu hữu ích | Session ID, user, CONNECT headers | Session ID, user, CONNECTED response |
| Use case | Audit attempt, theo dõi kết nối đang chờ | Đánh dấu ACTIVE, đo thời gian handshake |
| Có đồng nghĩa WebSocket handshake? | Không | Không; đây là trạng thái ở tầng STOMP |

## 3. SessionSubscribeEvent và SessionUnsubscribeEvent

### 3.1. SessionSubscribeEvent

**SessionSubscribeEvent** được phát khi Spring nhận một STOMP SUBSCRIBE. Event message chứa các header hữu ích như:

- Session ID của client.
- Principal của session.
- Destination mà client muốn subscribe.
- Subscription ID do client cung cấp.
- Các header STOMP khác có liên quan.

Ví dụ client subscribe:

~~~javascript
client.subscribe("/topic/orders", (message) => {
    console.log(message.body);
}, {
    id: "orders-subscription"
});
~~~

Event tương ứng có thể được dùng để ghi nhận rằng session đã yêu cầu đăng ký destination /topic/orders với subscription ID orders-subscription.

Không nên coi event này là bằng chứng rằng client đã nhận được message hoặc subscription đã được broker xác nhận. Nó là thông báo Spring đã nhận SUBSCRIBE. Với broker relay, nếu cần xác nhận ở cấp giao thức, hãy sử dụng cơ chế STOMP RECEIPT phù hợp với broker/client và kiểm tra receipt frame.

### 3.2. SessionUnsubscribeEvent

**SessionUnsubscribeEvent** được phát khi Spring nhận STOMP UNSUBSCRIBE. Ứng dụng có thể dùng nó để cập nhật trạng thái subscription hoặc giải phóng tài nguyên liên quan tới subscription ID.

Ví dụ:

~~~javascript
const subscription = client.subscribe("/topic/orders", handler, {
    id: "orders-subscription"
});

// Khi không còn cần nhận dữ liệu:
subscription.unsubscribe();
~~~

Việc unsubscribe một subscription không đồng nghĩa với việc WebSocket/STOMP session kết thúc. Một client có thể unsubscribe một destination rồi tiếp tục subscribe destination khác trong cùng session.

### 3.3. Subscription ID và destination

Một session có thể có nhiều subscription, kể cả nhiều subscription cùng destination với các ID khác nhau. Khi theo dõi, nên lưu cặp session ID và subscription ID; destination hữu ích cho thống kê và audit.

Không nên chỉ dùng destination làm khóa vì cùng một destination có thể được đăng ký nhiều lần bởi cùng hoặc nhiều session. Cũng không nên giả định subscription ID là duy nhất toàn hệ thống; nó do client chọn và thường chỉ có ý nghĩa trong session tương ứng.

## 4. SessionDisconnectEvent và xử lý lặp an toàn

**SessionDisconnectEvent** được phát khi STOMP session kết thúc. DISCONNECT có thể đến từ client hoặc được Spring tự tạo khi WebSocket session đóng.

Spring cảnh báo rằng trong một số trường hợp, một session có thể phát SessionDisconnectEvent nhiều hơn một lần. Vì vậy, listener phải xử lý idempotent: nhận event lặp lại không được xóa tài nguyên hai lần, trừ tiền hai lần hoặc ghi nhận hai lượt offline độc lập.

Các quy tắc nên áp dụng:

- Dùng session ID để xác định đúng session cần cleanup.
- Chỉ xóa trạng thái nếu session còn tồn tại trong registry của ứng dụng.
- Dùng thao tác remove-if-present hoặc một cờ trạng thái để cleanup chỉ có hiệu lực một lần.
- Không đánh dấu user offline ngay khi một session ngắt nếu user còn session khác.
- Đóng tài nguyên liên quan tới session như subscription metadata, listener hoặc lock theo chính sách đã định.
- Không coi disconnect event là bằng chứng chắc chắn người dùng đã logout khỏi toàn bộ ứng dụng.

Ví dụ, một user mở hai tab có hai WebSocket session. Khi tab thứ nhất đóng, user vẫn còn tab thứ hai. Presence của user chỉ nên chuyển sang offline khi không còn session nào của user.

## 5. Đọc dữ liệu từ event

Các event này kế thừa từ **AbstractSubProtocolEvent**, cung cấp message và user. Có thể dùng **StompHeaderAccessor** để đọc STOMP-specific header.

Các method thường dùng:

| Method | Ý nghĩa |
|---|---|
| getMessage() | Message gốc gắn với event |
| getUser() | Principal của session nếu có |
| getSessionId() | Session ID trong message headers |
| getDestination() | Destination của SUBSCRIBE/UNSUBSCRIBE hoặc message liên quan |
| getSubscriptionId() | Subscription ID |
| getCommand() | STOMP command |
| getSessionAttributes() | Các attribute gắn với WebSocket session nếu có |

Ví dụ listener:

~~~java
package com.example.messaging.events;

import java.security.Principal;
import java.util.logging.Logger;

import org.springframework.context.event.EventListener;
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.messaging.SessionConnectEvent;
import org.springframework.web.socket.messaging.SessionConnectedEvent;
import org.springframework.web.socket.messaging.SessionDisconnectEvent;
import org.springframework.web.socket.messaging.SessionSubscribeEvent;
import org.springframework.web.socket.messaging.SessionUnsubscribeEvent;

@Component
public class StompLifecycleEventListener {

    private static final Logger LOGGER =
            Logger.getLogger(StompLifecycleEventListener.class.getName());

    @EventListener
    public void onConnect(SessionConnectEvent event) {
        logEvent("CONNECT_RECEIVED", event.getMessage(), event.getUser());
    }

    @EventListener
    public void onConnected(SessionConnectedEvent event) {
        logEvent("CONNECTED", event.getMessage(), event.getUser());
    }

    @EventListener
    public void onSubscribe(SessionSubscribeEvent event) {
        logEvent("SUBSCRIBE", event.getMessage(), event.getUser());
    }

    @EventListener
    public void onUnsubscribe(SessionUnsubscribeEvent event) {
        logEvent("UNSUBSCRIBE", event.getMessage(), event.getUser());
    }

    @EventListener
    public void onDisconnect(SessionDisconnectEvent event) {
        logEvent("DISCONNECT", event.getMessage(), event.getUser());
    }

    private void logEvent(String type, Message<?> message, Principal user) {
        StompHeaderAccessor headers = StompHeaderAccessor.wrap(message);

        String sessionId = headers.getSessionId();
        String destination = headers.getDestination();
        String subscriptionId = headers.getSubscriptionId();
        String username = user == null ? "anonymous" : user.getName();

        LOGGER.info(() -> type
                + " session=" + sessionId
                + " user=" + username
                + " destination=" + destination
                + " subscriptionId=" + subscriptionId);
    }
}
~~~

Ví dụ dùng java.util.logging để dễ đọc và không phụ thuộc logging facade. Trong ứng dụng thực tế, có thể dùng SLF4J và structured logging. Cần cân nhắc dữ liệu cá nhân trong log; nên dùng user ID nội bộ hoặc giá trị đã pseudonymize nếu không cần tên đăng nhập thật.

Không log toàn bộ native headers hoặc message thô. CONNECT có thể mang bearer token, CSRF token hoặc dữ liệu xác thực tùy ứng dụng. Hãy chỉ ghi các trường cần cho vận hành và loại bỏ bí mật trước khi ghi log.

## 6. Quản lý trạng thái session và subscription

### 6.1. Dùng event để duy trì registry của ứng dụng

Một registry đơn giản có thể lưu session và tập subscription theo session ID. Ví dụ sau minh họa các thao tác cập nhật; ứng dụng production cần xác định phạm vi lưu trữ, đồng bộ và thời gian tồn tại phù hợp.

~~~java
package com.example.messaging.events;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.context.event.EventListener;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.messaging.SessionConnectedEvent;
import org.springframework.web.socket.messaging.SessionDisconnectEvent;
import org.springframework.web.socket.messaging.SessionSubscribeEvent;
import org.springframework.web.socket.messaging.SessionUnsubscribeEvent;

@Component
public class SubscriptionRegistry {

    private final ConcurrentMap<String, Set<String>> subscriptions =
            new ConcurrentHashMap<>();

    @EventListener
    public void onConnected(SessionConnectedEvent event) {
        String sessionId = StompHeaderAccessor.wrap(event.getMessage())
                .getSessionId();

        if (sessionId != null) {
            subscriptions.putIfAbsent(
                    sessionId, ConcurrentHashMap.newKeySet());
        }
    }

    @EventListener
    public void onSubscribe(SessionSubscribeEvent event) {
        StompHeaderAccessor headers =
                StompHeaderAccessor.wrap(event.getMessage());

        String sessionId = headers.getSessionId();
        String subscriptionId = headers.getSubscriptionId();

        if (sessionId != null && subscriptionId != null) {
            subscriptions
                    .computeIfAbsent(
                            sessionId, key -> ConcurrentHashMap.newKeySet())
                    .add(subscriptionId);
        }
    }

    @EventListener
    public void onUnsubscribe(SessionUnsubscribeEvent event) {
        StompHeaderAccessor headers =
                StompHeaderAccessor.wrap(event.getMessage());

        String sessionId = headers.getSessionId();
        String subscriptionId = headers.getSubscriptionId();

        if (sessionId == null || subscriptionId == null) {
            return;
        }

        Set<String> ids = subscriptions.get(sessionId);
        if (ids != null) {
            ids.remove(subscriptionId);
            if (ids.isEmpty()) {
                subscriptions.remove(sessionId, ids);
            }
        }
    }

    @EventListener
    public void onDisconnect(SessionDisconnectEvent event) {
        String sessionId = StompHeaderAccessor.wrap(event.getMessage())
                .getSessionId();

        if (sessionId != null) {
            // remove() chỉ trả dữ liệu ở lần đầu; event lặp không gây cleanup lặp.
            subscriptions.remove(sessionId);
        }
    }

    public int subscriptionCount(String sessionId) {
        Set<String> ids = subscriptions.get(sessionId);
        return ids == null ? 0 : ids.size();
    }
}
~~~

Registry trên chỉ là minh họa trong bộ nhớ cho một instance ứng dụng. Nếu triển khai nhiều instance, dữ liệu session local không tự chia sẻ giữa các instance. Cần dùng cơ chế phân tán hoặc **SimpUserRegistry**/user registry phù hợp nếu cần tổng hợp trạng thái toàn cụm.

### 6.2. Presence của user có nhiều session

Một user có thể kết nối từ nhiều tab, cửa sổ, thiết bị hoặc trình duyệt. Vì vậy, mô hình presence nên ánh xạ một user tới một tập session ID:

~~~text
alice -> {session-1, session-2}
bob   -> {session-3}
~~~

Khi session-1 disconnect, Alice vẫn online vì session-2 còn hoạt động. Khi session cuối cùng của Alice disconnect, ứng dụng mới có thể đánh dấu Alice offline.

Trong triển khai thực tế, cần xử lý đồng thời: hai session có thể connect/disconnect gần như cùng lúc. Dùng thao tác nguyên tử, khóa phù hợp hoặc lưu trữ có tính nhất quán cần thiết để tránh trạng thái presence sai.

### 6.3. SimpUserRegistry

Spring cung cấp **SimpUserRegistry** để truy vấn user, session và subscription mà message infrastructure đang theo dõi. Nếu chỉ cần xem trạng thái hiện tại, hãy cân nhắc dùng registry có sẵn thay vì xây dựng lại toàn bộ dữ liệu từ ApplicationContext event.

Event listener vẫn hữu ích khi cần audit, metrics, cleanup tài nguyên nghiệp vụ hoặc đồng bộ trạng thái ra hệ thống khác. Registry có sẵn và event listener phục vụ hai nhu cầu bổ sung nhau.

## 7. Event listener và ChannelInterceptor khác nhau thế nào?

ApplicationContext event thông báo các mốc vòng đời STOMP. Chúng không được phát cho mọi message client gửi. Nếu cần quan sát hoặc can thiệp từng frame/message, dùng **ChannelInterceptor**.

| Cơ chế | Phạm vi | Use case |
|---|---|---|
| SessionConnectEvent | Nhận CONNECT | Theo dõi lần bắt đầu STOMP handshake |
| SessionConnectedEvent | Nhận phản hồi CONNECTED | Đánh dấu session đã sẵn sàng |
| SessionSubscribeEvent | Nhận SUBSCRIBE | Theo dõi đăng ký destination |
| SessionUnsubscribeEvent | Nhận UNSUBSCRIBE | Theo dõi hủy subscription |
| SessionDisconnectEvent | Session kết thúc | Cleanup và cập nhật presence |
| ChannelInterceptor | Mỗi message đi qua channel | Authentication, authorization, validation, tracing, metrics |

Ví dụ đăng ký interceptor inbound:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration implements WebSocketMessageBrokerConfigurer {

    private final ChannelInterceptor auditInterceptor;

    public WebSocketConfiguration(ChannelInterceptor auditInterceptor) {
        this.auditInterceptor = auditInterceptor;
    }

    @Override
    public void configureClientInboundChannel(ChannelRegistration registration) {
        registration.interceptors(auditInterceptor);
    }
}
~~~

Interceptor có thể dùng **StompHeaderAccessor** để đọc command, destination, session ID và user. Nó có thể kiểm tra, từ chối hoặc bổ sung thông tin trước khi message tiếp tục trong channel.

Không dùng event listener để chặn SUBSCRIBE trái phép sau khi event đã được phát. Authorization cần được thực hiện trong chuỗi xử lý inbound message trước khi message được chấp nhận.

## 8. Theo dõi broker availability riêng với session events

**BrokerAvailabilityEvent** khác với các event theo session. Nó cho biết system connection của broker relay đang khả dụng hay không. Khi broker ngoài bị restart, relay có thể tự kết nối lại system connection và phát event khi trạng thái thay đổi.

Điều này không có nghĩa mọi client connection đã được khôi phục. Kết nối TCP thay mặt client có vòng đời riêng; client cần tự reconnect STOMP/WebSocket khi mất kết nối.

Service gửi message qua **SimpMessagingTemplate** nên theo dõi broker availability và vẫn phải xử lý **MessageDeliveryException** khi gửi. Không nên lấy số SessionConnectedEvent làm chỉ báo broker system connection đang sẵn sàng cho mọi thao tác server-to-broker.

## 9. Đo lường hiệu năng và vận hành

Các event cho phép xây dựng metrics có ý nghĩa:

- **CONNECT attempts:** số SessionConnectEvent.
- **STOMP sessions established:** số SessionConnectedEvent.
- **Handshake latency:** thời gian từ SessionConnectEvent tới SessionConnectedEvent theo session ID.
- **Subscription activity:** số SessionSubscribeEvent và SessionUnsubscribeEvent.
- **Active sessions:** số session đã kết nối thành công trừ số session đã disconnect, có xử lý event lặp.
- **Session duration:** thời gian từ CONNECTED đến DISCONNECT.
- **Disconnect rate:** số SessionDisconnectEvent duy nhất chia cho số session đã thiết lập.

Không dùng số CONNECT nhận được làm số kết nối thành công. Một client có thể mở WebSocket nhưng không gửi CONNECT, hoặc gửi CONNECT nhưng broker không trả CONNECTED.

Không coi mỗi SessionDisconnectEvent là một lần disconnect mới vì Spring có thể phát event lặp. Với metrics, hãy đếm session ID duy nhất hoặc chỉ tăng counter khi registry thực sự chuyển trạng thái từ active sang removed.

### 9.1. Giữ listener nhẹ

Các listener ApplicationContext thường chạy đồng bộ trong luồng phát event trừ khi ứng dụng cấu hình async event handling. Không thực hiện truy vấn mạng chậm, gọi API ngoài hoặc xử lý báo cáo lớn ngay trong listener, vì có thể làm chậm luồng messaging.

Nếu cần xử lý nặng, hãy ghi nhận event tối thiểu rồi đẩy tác vụ sang executor/queue phù hợp. Khi chuyển async, cần lưu ý thứ tự sự kiện có thể không còn được bảo đảm như khi xử lý tuần tự; việc cập nhật trạng thái session nên dùng thao tác idempotent và có kiểm soát cạnh tranh.

### 9.2. Không lưu bí mật từ event

CONNECT event có thể chứa custom header mà client gửi. Những header này có thể là access token, CSRF token hoặc dữ liệu nhận dạng. Chỉ trích xuất session ID, Principal, destination, subscription ID và metadata cần thiết. Không ghi nguyên message/header map vào log.

## 10. Lỗi thường gặp và cách xử lý

| Vấn đề | Nguyên nhân | Cách xử lý |
|---|---|---|
| WebSocket đã mở nhưng không có SessionConnectedEvent | Client chưa gửi CONNECT hoặc broker chưa phản hồi CONNECTED | Theo dõi riêng handshake và STOMP CONNECT; kiểm tra broker |
| SessionConnectEvent xuất hiện nhưng client chưa sẵn sàng | Event chỉ đánh dấu CONNECT nhận được | Chờ SessionConnectedEvent để đánh dấu STOMP session active |
| SessionSubscribeEvent không có nghĩa message đã tới client | Event chỉ cho biết SUBSCRIBE đã được nhận | Kiểm tra broker receipt và luồng message thực tế |
| Presence user bị offline quá sớm | User có nhiều session nhưng ứng dụng chỉ đếm theo user | Theo dõi tập session ID trên mỗi user |
| Tài nguyên bị cleanup hai lần | SessionDisconnectEvent có thể lặp | Dùng remove-if-present và cleanup idempotent |
| Metrics session bị âm hoặc sai | Event lặp, race condition hoặc CONNECT không thành công | Chỉ cập nhật trạng thái theo session ID và chuyển trạng thái hợp lệ |
| Listener làm chậm xử lý message | Listener đồng bộ gọi tác vụ chậm | Giữ listener ngắn, đẩy việc nặng sang executor/queue |
| Không tìm thấy subscription sau reconnect | Session mới có session ID mới; subscription cũ thuộc session cũ | Client subscribe lại sau reconnect và registry cập nhật theo session mới |

## 11. Checklist kiểm thử

1. Kết nối WebSocket nhưng không gửi STOMP CONNECT: không tính là STOMP session đã thiết lập.
2. Gửi CONNECT thành công: quan sát SessionConnectEvent rồi SessionConnectedEvent.
3. Từ chối hoặc làm thất bại CONNECT: không đánh dấu session active nếu chưa nhận CONNECTED.
4. Subscribe nhiều destination: mỗi SUBSCRIBE được quan sát với đúng session ID và subscription ID.
5. Unsubscribe một subscription: session vẫn active và các subscription khác vẫn tồn tại.
6. Disconnect bình thường: cleanup toàn bộ subscription metadata của session.
7. Đóng WebSocket bất ngờ: cleanup vẫn diễn ra khi Spring phát disconnect event.
8. Gửi disconnect hoặc đóng transport theo các đường khác nhau: event lặp không làm cleanup/metrics sai.
9. Một user mở hai session: disconnect một session không đánh dấu user offline khi session còn lại hoạt động.
10. Broker relay mất rồi phục hồi: kiểm tra BrokerAvailabilityEvent riêng và xác nhận client tự reconnect.
11. Tạo tải với nhiều session/subscription: đo thời gian listener và bảo đảm listener không làm nghẽn inbound/outbound channel.

## 12. Nguyên tắc thiết kế

1. **Phân biệt WebSocket và STOMP lifecycle.** Handshake thành công chưa có nghĩa STOMP CONNECTED.
2. **Dùng đúng event cho đúng mốc.** SessionConnectEvent là CONNECT nhận được; SessionConnectedEvent là CONNECTED phản hồi.
3. **Theo dõi theo session ID.** Một user có thể có nhiều session và mỗi session có nhiều subscription.
4. **Cleanup idempotent.** SessionDisconnectEvent có thể được phát nhiều lần.
5. **Không biến event thành cơ chế authorization.** Dùng ChannelInterceptor hoặc Spring Security để kiểm tra từng message.
6. **Giữ listener nhẹ.** Đẩy tác vụ nặng sang executor/queue và kiểm soát thứ tự nếu cần.
7. **Không log bí mật.** Event message có thể chứa native headers do client gửi.
8. **Đo đúng trạng thái.** Phân biệt CONNECT attempt, STOMP session established, subscription request và broker availability.

## 13. Tài liệu tham khảo

- [Spring Framework – Application Context Events](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html)
- [SessionConnectEvent Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/messaging/SessionConnectEvent.html)
- [SessionConnectedEvent Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/messaging/SessionConnectedEvent.html)
- [SessionSubscribeEvent Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/messaging/SessionSubscribeEvent.html)
- [SessionUnsubscribeEvent Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/messaging/SessionUnsubscribeEvent.html)
- [SessionDisconnectEvent Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/messaging/SessionDisconnectEvent.html)
- [Spring Framework – Interception](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/interceptors.html)
