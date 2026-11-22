# Xây dựng ứng dụng cập nhật trực tiếp qua STOMP

> Phạm vi: xây dựng ứng dụng real-time trên Spring Framework bằng STOMP over WebSocket, từ cấu hình endpoint và broker đến controller, server push, browser client, bảo mật, vận hành và kiểm thử.

## 1. Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vai trò của WebSocket và STOMP trong giao tiếp hai chiều.
- Cấu hình STOMP endpoint, application destination và broker destination.
- Xử lý client message bằng `@MessageMapping` và gửi dữ liệu bằng `@SendTo` hoặc `SimpMessagingTemplate`.
- Phân biệt broadcast topic, queue convention và user destination.
- Kết nối browser bằng `@stomp/stompjs`, subscribe, publish, heartbeat và reconnect.
- Bảo vệ WebSocket/STOMP bằng HTTP authentication, CSRF và message authorization.
- Chọn simple broker hay external broker relay.
- Kiểm soát ordering, thread pool, message size, slow client và monitoring.
- Viết controller test và end-to-end WebSocket/STOMP test.

## 2. WebSocket và STOMP

WebSocket tạo một kết nối hai chiều lâu dài giữa client và server sau HTTP handshake. WebSocket chỉ định nghĩa cách truyền frame text/binary; nó không định nghĩa ý nghĩa nghiệp vụ của nội dung frame.

STOMP (Simple Text Oriented Messaging Protocol) là messaging sub-protocol có thể chạy trên WebSocket. STOMP định nghĩa command, header và body để client/server trao đổi các thao tác như CONNECT, SUBSCRIBE, SEND, MESSAGE và DISCONNECT.

Một STOMP frame có dạng khái quát:

```text
COMMAND
header-name:header-value

body
^@
```

Ký tự kết thúc frame là NUL. Frame thực tế có thể có `content-length`, `content-type`, `destination`, `ack` và các header khác tùy command. Không tự parse STOMP bằng cách tách chuỗi tùy tiện; hãy dùng thư viện client/server đã hỗ trợ protocol.

STOMP hữu ích khi ứng dụng cần push update, chat, dashboard, trạng thái tác vụ hoặc thông báo tới nhiều client. Nếu chỉ cần request/response thông thường, HTTP REST có thể đơn giản hơn; WebSocket/STOMP phù hợp khi server cần chủ động gửi message mà không chờ client poll.

## 3. Kiến trúc message flow của Spring

Spring biến STOMP frame thành `Message<?>` và định tuyến qua các channel nội bộ:

```text
Browser -- WebSocket/STOMP --> clientInboundChannel
                                  |
                    /app/**      |      /topic/**, /queue/**
                       v         |             v
                @MessageMapping  |        Message Broker
                       |         |             ^
                       +---- brokerChannel ---+
                                                 |
Browser <-- WebSocket/STOMP -- clientOutboundChannel
```

- `clientInboundChannel`: nhận message từ WebSocket client.
- `brokerChannel`: chuyển message do controller/service phát tới broker.
- `clientOutboundChannel`: gửi message từ broker về WebSocket sessions.
- `@MessageMapping`: xử lý message có destination thuộc application prefix.
- Broker: quản lý subscriptions và phát message tới subscriber phù hợp.

Thông thường, destination bắt đầu bằng `/app` được chuyển tới controller; destination bắt đầu bằng `/topic` hoặc `/queue` được chuyển tới broker. Các prefix này là convention do ứng dụng cấu hình.

## 4. Cấu hình STOMP endpoint và broker

STOMP over WebSocket cần `spring-messaging` và `spring-websocket`. Với Spring Boot, thêm starter WebSocket tương ứng với phiên bản Boot đang dùng; dependency management của Boot quản lý version Spring Framework.

Cấu hình cơ bản:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
                .setAllowedOriginPatterns("https://app.example.com");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.setUserDestinationPrefix("/user");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
```

`/ws` là URL HTTP dùng cho WebSocket handshake, không phải destination để publish. Sau khi kết nối, client gửi STOMP frame qua connection đó.

`setApplicationDestinationPrefixes("/app")` khiến message gửi tới `/app/chat.send` được định tuyến tới `@MessageMapping("/chat.send")`. `/topic` và `/queue` được broker xử lý. `/user` được Spring dùng để phân giải destination theo user/session.

Chỉ cho phép origin của frontend thực tế. Tránh `*` khi ứng dụng dùng cookie hoặc credential; kiểm tra origin là một lớp bảo vệ chống website lạ mở kết nối tới endpoint.

### 4.1. Simple broker

`enableSimpleBroker("/topic", "/queue")` bật broker đơn giản chạy trong memory của application instance. Nó lưu subscriptions đang hoạt động và phát message tới các session phù hợp.

Simple broker phù hợp cho demo, development hoặc ứng dụng nhỏ một instance. Nó hỗ trợ một phần STOMP protocol; không hỗ trợ đầy đủ ACK, receipts và một số tính năng khác, và không phù hợp cho clustering. Khi process restart, subscription trong memory bị mất và client phải kết nối/subscribe lại.

Tên `/topic` thường biểu thị publish-subscribe, còn `/queue` thường biểu thị point-to-point. Với simple broker, hai prefix này không có semantics đặc biệt ở protocol; chúng chỉ là convention. Với external broker, ý nghĩa cụ thể phụ thuộc broker và cấu hình.

### 4.2. External broker relay

Khi cần nhiều application instance hoặc broker có tính năng đầy đủ hơn, dùng STOMP broker relay:

```java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.setUserDestinationPrefix("/user");
    registry.enableStompBrokerRelay("/topic", "/queue")
            .setRelayHost("rabbitmq")
            .setRelayPort(61613);
}
```

Ví dụ trên giả định broker đã bật STOMP listener ở host/port tương ứng và credential được cấu hình an toàn theo môi trường. Không hard-code username/password trong source. Cấu hình relay có thể đặt client/system login riêng.

Broker relay tạo TCP connection tới external STOMP broker, chuyển message từ Spring tới broker và chuyển message broker phát về các WebSocket sessions. Nhờ vậy, một instance có thể phát message tới client đang kết nối instance khác thông qua broker chung.

Relay không tự làm mọi destination durable. Persistence, queue durability, ACK mode, retention, redelivery và dead-letter behavior phụ thuộc broker và cách khai báo destination. Hãy kiểm tra tài liệu broker.

## 5. Xây dựng message contract

Dùng DTO rõ ràng thay vì gửi entity trực tiếp:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record ChatRequest(
        @NotBlank
        @Size(max = 2000)
        String content) {
}

public record ChatEvent(
        String sender,
        String content,
        java.time.Instant sentAt) {
}
```

`ChatRequest` là dữ liệu client được phép gửi. `ChatEvent` là dữ liệu server phát ra. Server lấy sender từ `Principal`, không tin tên người gửi do client tự khai báo.

Giữ payload gọn, giới hạn độ dài và xác thực dữ liệu. Với update lớn, gửi ID hoặc reference để client tải chi tiết qua HTTP/API phù hợp thay vì broadcast object quá lớn.

## 6. Nhận message bằng @MessageMapping

Controller nhận message gửi tới `/app/chat.send`:

```java
import java.security.Principal;
import java.time.Instant;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.simp.annotation.SendTo;
import org.springframework.stereotype.Controller;
import jakarta.validation.Valid;

@Controller
public class ChatController {

    @MessageMapping("/chat.send")
    @SendTo("/topic/public")
    public ChatEvent send(
            @Valid @Payload ChatRequest request,
            Principal principal) {
        return new ChatEvent(
                principal.getName(),
                request.content(),
                Instant.now());
    }
}
```

Client gửi `SEND` tới `/app/chat.send`. Spring bỏ application prefix `/app`, tìm mapping `/chat.send`, chuyển payload JSON thành `ChatRequest`, gọi method và serialize giá trị trả về thành message gửi tới `/topic/public`.

`@SendTo` chỉ định destination đầu ra. Nếu không chỉ định destination, Spring có quy tắc mặc định dựa trên destination đầu vào; trong ứng dụng thực tế nên khai báo rõ để contract dễ đọc.

Payload conversion dựa trên `MessageConverter` được cấu hình. JSON là lựa chọn phổ biến với browser client; hai phía cần thống nhất field names, date format và schema.

## 7. Gửi update từ service hoặc HTTP request

Không phải mọi message đều bắt nguồn từ STOMP client. Một scheduled job, service hoặc REST controller cũng có thể phát update qua `SimpMessagingTemplate`:

```java
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
public class LiveUpdatePublisher {

    private final SimpMessagingTemplate messaging;

    public LiveUpdatePublisher(SimpMessagingTemplate messaging) {
        this.messaging = messaging;
    }

    public void publishOrderStatus(OrderStatusUpdate update) {
        messaging.convertAndSend("/topic/orders", update);
    }

    public void publishPrivateUpdate(String username, AccountUpdate update) {
        messaging.convertAndSendToUser(
                username, "/queue/updates", update);
    }
}
```

`convertAndSend` phát tới destination chung. `convertAndSendToUser` gửi tới user destination; client tương ứng subscribe `/user/queue/updates`. Spring ánh xạ `/user` thành destination riêng cho user/session, giúp nhiều user subscribe cùng tên logic mà không nhận nhầm message của nhau.

User destination cần principal/session mapping phù hợp. Nếu cùng một user đăng nhập nhiều session, mặc định message có thể được gửi tới các session của user đó; có thể điều chỉnh broadcast behavior theo nhu cầu.

## 8. SubscribeMapping cho dữ liệu khởi tạo

`@SubscribeMapping` phù hợp khi client subscribe và cần một response ban đầu trực tiếp, ví dụ snapshot hiện tại:

```java
@Controller
class DashboardController {

    @SubscribeMapping("/dashboard.initial")
    DashboardSnapshot initialSnapshot() {
        return dashboardService.currentSnapshot();
    }
}
```

Client subscribe `/app/dashboard.initial`. Mặc định, return value được gửi trực tiếp về client đã subscribe, không broadcast qua broker tới mọi subscriber. Sau snapshot ban đầu, các thay đổi tiếp theo có thể được publish tới `/topic/dashboard`.

Mẫu này tránh phải gọi HTTP snapshot riêng rồi mới mở subscription, nhưng cần xử lý race giữa lúc lấy snapshot và lúc nhận update. Nếu cần không bỏ sót event, dùng version/sequence trong snapshot và update để client phát hiện gap.

## 9. Browser client với @stomp/stompjs

Cài STOMP client JavaScript:

```bash
npm install @stomp/stompjs
```

Ví dụ kết nối, subscribe và publish:

```javascript
import { Client } from '@stomp/stompjs';

const client = new Client({
  brokerURL: 'wss://api.example.com/ws',
  reconnectDelay: 5000,
  heartbeatIncoming: 10000,
  heartbeatOutgoing: 10000,
  onConnect: () => {
    client.subscribe('/topic/public', (frame) => {
      const event = JSON.parse(frame.body);
      renderChatEvent(event);
    });

    client.subscribe('/user/queue/updates', (frame) => {
      renderPrivateUpdate(JSON.parse(frame.body));
    });
  },
  onStompError: (frame) => {
    console.error('STOMP broker error:', frame.headers['message']);
  },
  onWebSocketError: (event) => {
    console.error('WebSocket error:', event);
  }
});

client.activate();

export function sendChat(content) {
  if (!client.connected) {
    throw new Error('STOMP client is not connected');
  }

  client.publish({
    destination: '/app/chat.send',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ content })
  });
}

export async function disconnect() {
  await client.deactivate();
}
```

`reconnectDelay` cho phép client tự kết nối lại sau khi mất mạng. Mỗi lần `onConnect` chạy, hãy đăng ký subscription lại vì session mới có thể không giữ subscriptions cũ. Heartbeat giúp phát hiện connection chết hoặc proxy đã đóng kết nối.

Nếu dùng SockJS fallback, server đăng ký `registry.addEndpoint("/ws").withSockJS()` và client dùng SockJS làm `webSocketFactory`. Không bật SockJS chỉ vì STOMP; chỉ thêm khi cần fallback cho môi trường client/network không hỗ trợ WebSocket đầy đủ.

Không gửi message trước khi `client.connected` là true. UI nên thể hiện trạng thái connecting/connected/reconnecting và xử lý lỗi publish. Với thao tác quan trọng, STOMP SEND không tự đảm bảo nghiệp vụ đã commit; thiết kế ACK/receipt hoặc response application-level phù hợp.

## 10. Authentication và authorization

### 10.1. Authentication từ HTTP handshake

STOMP over WebSocket bắt đầu bằng HTTP handshake. Trong ứng dụng dùng cookie/session và Spring Security, principal đã xác thực trên HTTP request được chuyển sang WebSocket session và gắn với các STOMP message sau đó.

Đây là cách đơn giản cho browser app cùng domain: bảo vệ HTTP handshake bằng Spring Security, dùng cookie/session và lấy `Principal` trong `@MessageMapping`.

### 10.2. Token trong STOMP CONNECT

Browser WebSocket API không cho phép tùy ý thêm HTTP header vào handshake. Với ứng dụng không dùng cookie session, có thể gửi token trong STOMP CONNECT header và xử lý bằng `ChannelInterceptor`. Interceptor xác thực token, sau đó gọi `StompHeaderAccessor.setUser(authentication)` trên CONNECT message. Spring gắn user đó với các message tiếp theo của session.

Spring mặc định bỏ qua STOMP `login` và `passcode` headers cho STOMP over WebSocket; không dựa vào chúng để xác thực browser client. Tránh truyền token qua query string vì URL thường xuất hiện trong access log, proxy log hoặc analytics.

Nếu dùng custom authentication interceptor cùng Spring Security, đăng ký interceptor trước interceptor bảo mật theo thứ tự được Spring Security hướng dẫn; nếu không, authorization có thể chạy trước khi user được gắn vào message.

### 10.3. CSRF cho CONNECT

Khi bật `@EnableWebSocketSecurity`, Spring Security yêu cầu CSRF token trên inbound STOMP `CONNECT` để bảo vệ Same Origin Policy. Browser cần lấy token từ HTTP endpoint hoặc request attribute và gửi đúng header name/value trong `connectHeaders` của STOMP client.

Ví dụ client:

```javascript
const csrf = await fetch('/csrf', { credentials: 'same-origin' })
  .then(response => response.json());

const client = new Client({
  brokerURL: 'wss://api.example.com/ws',
  connectHeaders: {
    [csrf.headerName]: csrf.token
  }
});
```

Endpoint `/csrf` cần được ứng dụng cung cấp để trả `CsrfToken`. Không tắt CSRF cho toàn bộ ứng dụng chỉ để làm WebSocket connect dễ hơn. Nếu cần điều chỉnh, chỉ giới hạn ngoại lệ ở handshake/SockJS transport URL phù hợp và giữ các lớp bảo vệ khác.

### 10.4. Authorization theo message type và destination

Bảo vệ cả `MESSAGE` và `SUBSCRIBE`. Nếu chỉ kiểm tra message gửi vào controller mà không kiểm tra subscription, client có thể subscribe destination mà nó không được phép đọc. Ngược lại, nếu cho phép client SEND trực tiếp tới `/topic/**`, client có thể giả mạo broadcast.

Ví dụ Spring Security:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.socket.EnableWebSocketSecurity;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;

import static org.springframework.messaging.simp.SimpMessageType.MESSAGE;
import static org.springframework.messaging.simp.SimpMessageType.SUBSCRIBE;

@Configuration
@EnableWebSocketSecurity
class WebSocketSecurityConfig {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {
        messages
            .nullDestMatcher().authenticated()
            .simpDestMatchers("/app/**").hasRole("USER")
            .simpSubscribeDestMatchers("/topic/public", "/user/**")
                .hasRole("USER")
            .simpTypeMatchers(MESSAGE, SUBSCRIBE).denyAll()
            .anyMessage().denyAll();

        return messages.build();
    }
}
```

Rule cụ thể được khai báo trước fallback. Ví dụ trên yêu cầu user authenticated cho message không có destination, cho phép role USER gửi tới `/app/**`, subscribe vào các destination được chỉ định, rồi từ chối các MESSAGE/SUBSCRIBE còn lại và mọi message khác. Điều chỉnh các destination theo API thực tế.

Không cho client SEND tới `/topic/**` hoặc `/queue/**` nếu chỉ server được quyền broadcast. Kiểm tra quyền theo tenant/resource trong service nghiệp vụ; role chung không đủ để chứng minh user sở hữu một tài nguyên cụ thể.

## 11. Xử lý lỗi và validation

Có thể dùng `@MessageExceptionHandler` để chuyển lỗi nghiệp vụ thành user-specific error message:

```java
public record ChatError(String code, String message) {}

@MessageExceptionHandler
@SendToUser(destinations = "/queue/errors", broadcast = false)
public ChatError handleInvalidMessage(IllegalArgumentException ex) {
    return new ChatError("INVALID_MESSAGE", ex.getMessage());
}
```

Không gửi stack trace, SQL detail hoặc secret cho client. Log exception ở server với correlation/session id và trả error code ổn định.

Validate DTO, giới hạn payload, rate-limit command nhạy cảm và kiểm tra quyền trên từng action. STOMP connection lâu dài không có nghĩa client được phép gửi message không giới hạn.

## 12. Ordering, thread pool và backpressure

Spring sử dụng executor-backed channel cho inbound/outbound message. Nhiều thread có thể xử lý message song song, vì vậy thứ tự hoàn tất có thể khác thứ tự nhận/phát.

Nếu nghiệp vụ yêu cầu giữ thứ tự trong một client session, có thể bật:

```java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/ws").setAllowedOriginPatterns("https://app.example.com");
    registry.setPreserveReceiveOrder(true);
}

@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setPreservePublishOrder(true);
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue");
}
```

Các tùy chọn này có overhead; chỉ bật khi yêu cầu nghiệp vụ cần ordering. Chúng không tạo ordering toàn cục giữa nhiều user hoặc nhiều application instance.

Có thể cấu hình inbound/outbound executor:

```java
@Override
public void configureClientInboundChannel(ChannelRegistration registration) {
    registration.taskExecutor()
            .corePoolSize(8)
            .maxPoolSize(32)
            .queueCapacity(1000);
}

@Override
public void configureClientOutboundChannel(ChannelRegistration registration) {
    registration.taskExecutor()
            .corePoolSize(8)
            .maxPoolSize(32)
            .queueCapacity(1000);
}
```

Đây là điểm khởi đầu để benchmark, không phải giá trị tối ưu cố định. Nếu queue capacity không giới hạn, executor có thể tiếp tục queue task thay vì mở rộng thread như kỳ vọng. Với inbound CPU-bound, số thread gần số CPU có thể phù hợp; I/O blocking cần đánh giá riêng.

Slow client có thể làm outbound queue và buffer tăng. Cấu hình giới hạn send time và send buffer:

```java
@Override
public void configureWebSocketTransport(WebSocketTransportRegistration registration) {
    registration.setSendTimeLimit(15_000)
            .setSendBufferSizeLimit(512 * 1024)
            .setMessageSizeLimit(128 * 1024);
}
```

Các con số trên là ví dụ. Chọn giới hạn theo kích thước message, số session đồng thời, tốc độ client và ngân sách memory. Kiểm tra giới hạn của WebSocket server, reverse proxy và broker; một lớp có thể từ chối message trước lớp khác.

## 13. Lifecycle và sự kiện session

Spring phát các application event liên quan WebSocket/STOMP, ví dụ `SessionConnectEvent`, `SessionConnectedEvent`, `SessionSubscribeEvent`, `SessionUnsubscribeEvent`, `SessionDisconnectEvent` và `BrokerAvailabilityEvent`.

Có thể lắng nghe để cập nhật presence, thống kê session, dọn resource hoặc quan sát broker availability. `SessionDisconnectEvent` có thể xuất hiện nhiều hơn một lần trong một số luồng đóng kết nối; cleanup cần idempotent.

Không dùng số session trong memory của một instance làm số user toàn cluster nếu không tổng hợp qua shared store hoặc broker. Khi dùng external broker relay, theo dõi thêm broker connection và availability.

## 14. Monitoring và vận hành

Khi bật `@EnableWebSocketMessageBroker`, Spring tạo `WebSocketMessageBrokerStats` để tổng hợp thông tin hạ tầng. Bean này mặc định log thống kê định kỳ và có thể export qua JMX.

Theo dõi:

- Số WebSocket/SockJS sessions hiện tại và tổng số session đã mở.
- Connect failures, abnormal close, transport errors và send-limit exceeded.
- Số STOMP CONNECT/CONNECTED/DISCONNECT frames.
- TCP connections của STOMP broker relay.
- Queue depth và active threads của `clientInboundChannel`.
- Queue depth và active threads của `clientOutboundChannel`.
- Message throughput, payload size, error rate và send latency.
- Số subscription theo destination, reconnect rate và heartbeat timeout.

Inbound channel queue tăng có thể cho thấy application xử lý message chậm. Outbound channel queue tăng có thể cho thấy client chậm đọc hoặc network kém. Phân biệt hai chiều này trước khi tăng thread pool.

Không log toàn bộ payload hoặc token. Dùng session id/correlation id đã được kiểm soát để điều tra; tránh metric tag có cardinality cao như user id hoặc message id.

## 15. Scale nhiều instance

Simple broker giữ subscriptions trong memory của một application instance và không hỗ trợ clustering. Nếu client A kết nối instance 1 và client B kết nối instance 2, broadcast qua simple broker của instance 1 không tự động tới subscription nằm ở instance 2.

Khi chạy nhiều instance, dùng external broker relay hoặc kiến trúc messaging phân tán phù hợp. Mỗi application instance kết nối broker chung; broker phân phối message tới các session liên quan trên các instance.

Cần cân nhắc thêm:

- WebSocket connection thường gắn với backend đã chọn trong handshake; load balancer không chuyển một connection đang mở sang pod khác.
- Khi reconnect, client phải subscribe lại và đồng bộ trạng thái hiện tại.
- Dùng broker relay và user destination registry phù hợp khi user có thể kết nối qua nhiều application instance.
- Presence/session registry trong memory chỉ là local view; cần chia sẻ hoặc tổng hợp nếu tính năng yêu cầu toàn cluster.
- Với update quan trọng, persist business state/event trước khi broadcast; WebSocket push không thay thế durable event log.
- Client nên có sequence/version để phát hiện mất message và lấy snapshot mới qua API.

## 16. Kiểm thử

Có hai lớp kiểm thử chính:

1. **Server-side message test:** nạp Spring context, gửi `Message<?>` vào `clientInboundChannel` hoặc dùng `SimpAnnotationMethodMessageHandler` để kiểm tra routing, validation, controller và outbound result. Unit test gọi trực tiếp method không đủ để kiểm tra annotation mapping.
2. **End-to-end test:** chạy embedded WebSocket server, kết nối bằng STOMP client như `WebSocketStompClient`, gửi CONNECT/SUBSCRIBE/SEND và xác minh MESSAGE nhận được.

Test cases nên có:

- Kết nối STOMP thành công với origin và authentication hợp lệ.
- CONNECT thiếu hoặc sai CSRF token bị từ chối khi Spring Security bật.
- User không đủ quyền không thể SEND tới `/app/**` hoặc SUBSCRIBE destination riêng tư.
- Client không thể giả mạo sender bằng field trong payload.
- `/topic` broadcast tới subscriber phù hợp.
- `/user/queue/**` chỉ gửi tới user/session mục tiêu.
- `@SubscribeMapping` trả snapshot trực tiếp.
- Validation và `@MessageExceptionHandler` trả lỗi đúng contract.
- Reconnect đăng ký lại subscriptions và tải snapshot để đồng bộ.
- Slow client bị giới hạn send buffer/time mà không làm cạn tài nguyên server.
- External broker relay truyền message giữa client kết nối các instance khác nhau.

## 17. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| WebSocket handshake 404 | URL client không trùng endpoint đăng ký | Kiểm tra `/ws`, context path và proxy route |
| Kết nối WebSocket được nhưng STOMP không CONNECTED | Subprotocol, frame format hoặc security CONNECT bị từ chối | Xem STOMP ERROR frame, CSRF và server log |
| Client SEND nhưng controller không chạy | Destination thiếu `/app` hoặc mapping sai | Đối chiếu application prefix và `@MessageMapping` |
| Controller chạy nhưng không ai nhận | Client chưa SUBSCRIBE hoặc destination prefix sai | Kiểm tra broker prefix và session subscription |
| Client nhận duplicate update | Reconnect subscribe lặp hoặc producer phát trùng | Dùng subscription lifecycle rõ ràng và event id để deduplicate |
| User nhận update của người khác | Dùng topic chung cho dữ liệu riêng hoặc user mapping sai | Dùng `/user/**`, principal đã xác thực và authorization |
| Message bị đảo thứ tự | Inbound/outbound channel xử lý song song | Xem yêu cầu ordering; cân nhắc preserve receive/publish order |
| Server memory tăng khi client chậm | Outbound buffer/queue không giới hạn hoặc payload lớn | Giới hạn send buffer/time, message size và tốc độ publish |
| Broadcast không qua instance khác | Đang dùng simple broker in-memory | Chuyển sang external broker relay |
| Session không được dọn | Disconnect không bình thường hoặc cleanup không idempotent | Theo dõi session events và timeout/heartbeat |

## 18. Checklist triển khai

- [ ] Endpoint WebSocket có URL rõ ràng và origin allowlist cụ thể.
- [ ] Application destination prefix và broker prefix không bị nhầm lẫn.
- [ ] DTO payload được validate và giới hạn kích thước.
- [ ] Controller lấy identity từ Principal đã xác thực, không tin sender trong payload.
- [ ] Client subscribe đúng topic, queue hoặc user destination.
- [ ] Client có reconnect, heartbeat và subscribe lại sau reconnect.
- [ ] CONNECT được bảo vệ bằng CSRF khi dùng Spring Security mặc định.
- [ ] Authorization kiểm tra cả MESSAGE và SUBSCRIBE.
- [ ] Client không được publish trực tiếp vào destination broker nội bộ.
- [ ] Simple broker chỉ dùng khi phạm vi một instance phù hợp; cluster dùng broker relay.
- [ ] Thread pool, queue capacity, send time, send buffer và message size có giới hạn.
- [ ] Ordering chỉ bật khi nghiệp vụ yêu cầu và đã đo overhead.
- [ ] Session lifecycle, monitoring, logs và metrics được thiết lập.
- [ ] Có test server-side và end-to-end cho connect, subscribe, send, security và reconnect.

## 19. Tài liệu tham khảo

- [Spring Framework — STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp.html): tổng quan STOMP over WebSocket, destination, controller, broker, user destinations và client.
- [Spring Framework — Enable STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html): `@EnableWebSocketMessageBroker`, endpoint và broker prefix.
- [Spring Framework — Message Flow](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html): `clientInboundChannel`, `brokerChannel`, `clientOutboundChannel` và route message.
- [Spring Framework — Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html): `@MessageMapping`, `@SubscribeMapping`, `@SendTo` và `@SendToUser`.
- [Spring Framework — Sending Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-send.html): `SimpMessagingTemplate` và server-side publish.
- [Spring Framework — External Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html): STOMP broker relay và external broker.
- [Spring Framework — User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html): `/user/` destination và per-user session routing.
- [Spring Security — WebSocket Security](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html): handshake authentication, CSRF CONNECT và message authorization.
- [Spring Framework — Token Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication-token-based.html): token trong STOMP CONNECT và ChannelInterceptor.
- [Spring Framework — Performance](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/configuration-performance.html): executor, ordering, message size và send limits.
- [Spring Framework — Monitoring](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/stats.html): `WebSocketMessageBrokerStats`, session và channel statistics.
- [Spring Framework — Testing](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/testing.html): server-side message test và end-to-end WebSocket test.

Các API và cấu hình cụ thể phụ thuộc phiên bản Spring Framework, Spring Boot, Spring Security và broker. Hãy dùng dependency management tương thích và kiểm tra tài liệu đúng phiên bản trước khi triển khai.
