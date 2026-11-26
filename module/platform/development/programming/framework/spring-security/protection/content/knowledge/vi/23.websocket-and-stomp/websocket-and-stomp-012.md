# Giới hạn khi dùng WebSocket thuần hoặc mô hình Reactive khác

## 1. Tình huống mở đầu: đổi STOMP sang WebSocket thuần nhưng quên đổi security

Một ứng dụng Spring Security dùng WebSocket Message Broker với STOMP. Frontend mở `/ws`, gửi STOMP `CONNECT` có CSRF token, sau đó `SEND /app/orders.lookup` hoặc `SUBSCRIBE /user/queue/order-results`. Backend bật `@EnableWebSocketSecurity` cùng `AuthorizationManager<Message<?>>` để kiểm tra những inbound messages này.

Nhóm phát triển chuyển sang native WebSocket để giảm phụ thuộc vào broker và thay client thành:

~~~javascript
const socket = new WebSocket("wss://api.example.com/ws/orders");

socket.onopen = () => {
  socket.send(JSON.stringify({
    type: "orders.lookup",
    orderId: 2002
  }));
};
~~~

HTTP handshake trả `101 Switching Protocols` và các text messages được gửi thành công. Lập trình viên thấy `@EnableWebSocketSecurity` vẫn tồn tại nên nghĩ `CsrfChannelInterceptor` và `simpDestMatchers("/app/**")` tiếp tục bảo vệ request này. **Đó là giả định nguy hiểm:** native WebSocket không tự tạo STOMP `CONNECT`, `SEND`, `SUBSCRIBE`, native STOMP headers hoặc destination semantics. Các matcher và interceptor thuộc Spring Security Messaging dành cho STOMP **không tự can thiệp vào `WebSocketHandler` thuần**.

Tương tự, khi chuyển sang **Spring WebFlux native WebSocket**, HTTP security sử dụng `SecurityWebFilterChain`, còn message handling sử dụng `Flux`/`Mono`. Không thể sao chép nguyên Servlet `SecurityFilterChain` hoặc STOMP security matchers và tuyên bố mỗi frame được phân quyền.

Bài thuộc chương **WebSocket và STOMP** của dịch vụ học tập **SPRING_SECURITY_HTTP_PROTECTION**, có phạm vi áp dụng bảo vệ HTTP và trình duyệt với Spring Security: CSRF, CORS, security headers, CSP, HSTS, HTTP firewall, bảo vệ session cho cả Servlet và Reactive. Trọng tâm bài là **giới hạn khi dùng WebSocket thuần hoặc mô hình Reactive khác**, và cách xây các lớp bảo vệ tương đương.

### Mục tiêu học tập

Sau bài, người học có thể:

1. So sánh Servlet/STOMP broker, Servlet native `TextWebSocketHandler`, WebFlux native `WebSocketHandler` và các mô hình Reactive khác.
2. Giải thích chính xác khi nào `@EnableWebSocketSecurity`/`CsrfChannelInterceptor`/`simpSubscribeDestMatchers` không áp dụng.
3. Tách HTTP handshake security khỏi authentication và authorization ở mức application message.
4. Giữ Origin allowlist, HTTP authentication, cookie protections và chống CSWSH trong native WebSocket.
5. Thiết kế protocol/state machine không xử lý business messages trước khi principal được xác minh.
6. Tự phân quyền action, resource, subscription, outbound data, tenant và object ownership.
7. Viết Spring Servlet native và WebFlux native configuration/handler theo ranh giới tin cậy.
8. Quản lý Reactor Context, backpressure, blocking calls, session expiry, logout và revocation.
9. So sánh RSocket, GraphQL subscriptions, Socket.IO và SSE với STOMP.
10. Kiểm thử handshake/Origin, authentication, message ACL, data leaks và connection lifecycle bằng công cụ phù hợp.

Các host `example.com`, đường dẫn và business entities chỉ mang tính minh họa. Code minh họa hướng đến Spring Framework/Security hiện đại với Java 17+; cần đối chiếu phiên bản và chạy integration tests trong project thực.

## 2. Bản đồ công nghệ: cùng dùng WebSocket không có nghĩa cùng security pipeline

| Mô hình | Protocol ứng dụng | API Spring điển hình | Cơ chế message security |
| --- | --- | --- | --- |
| Spring MVC + STOMP broker | STOMP `CONNECT`/`SEND`/`SUBSCRIBE` | `@EnableWebSocketMessageBroker`, `StompEndpointRegistry`, `@MessageMapping` | `@EnableWebSocketSecurity`, CONNECT CSRF, `AuthorizationManager<Message<?>>` khi cấu hình phù hợp |
| Servlet native WebSocket | Text/binary message do app tự định nghĩa | `@EnableWebSocket`, `WebSocketConfigurer`, `TextWebSocketHandler` | **Ứng dụng tự triển khai per-message security** |
| WebFlux native WebSocket | Reactive `Flux<WebSocketMessage>`; protocol tự định nghĩa | `WebSocketHandler`, `WebSocketSession`, `HandlerMapping` | **Ứng dụng tự triển khai per-message security** |
| RSocket trên WebSocket | RSocket setup/request/stream/channel frames | RSocket framework và RSocket Security integration tương ứng | Theo route/metadata/stream của RSocket, **không phải STOMP** |
| GraphQL qua WebSocket | GraphQL connection/operation/subscription messages | GraphQL server/WS subprotocol implementation | Theo connection, operation, field và dữ liệu |
| Socket.IO hoặc protocol tùy biến | Events, namespaces, rooms | Thư viện/protocol riêng | Theo namespace/event/room/tenant, không phải STOMP |
| SSE | HTTP response stream một chiều | MVC `SseEmitter` hoặc WebFlux stream | HTTP auth + per-event data ACL |

**WebSocket chỉ là transport**. Transport không định nghĩa ai có quyền gửi lệnh nào, nghe topic nào hoặc truy cập order ID nào.

### 2.1. Động từ STOMP không tồn tại tự nhiên trong raw WebSocket

~~~text
STOMP:
  CONNECT -> xác thực/CSRF của STOMP integration
  SEND /app/orders.lookup -> MESSAGE destination authorization
  SUBSCRIBE /topic/orders/2002 -> SUBSCRIBE authorization

WebSocket thuần:
  HTTP Upgrade -> socket mở
  Text frame {"type":"orders.lookup","orderId":2002}
  Text frame {"type":"subscribe","topic":"orders/2002"}
  JSON action/topic do ứng dụng tự nghĩ ra
~~~

Một JSON field `"type":"connect"` **không tự biến thành STOMP CONNECT**. Không có mặc định `SimpMessageType.MESSAGE` hoặc `SUBSCRIBE` để Spring Security Messaging đánh giá nếu không dùng hạ tầng STOMP.

### 2.2. Những lớp vẫn cần ở mọi mô hình

- HTTP authentication, TLS, Origin validation và browser cookie policy tại handshake.
- Schema validation, action allowlist, giới hạn tốc độ/kích thước và principal đáng tin.
- Object/tenant ACL tại hành động nghiệp vụ.
- Kiểm tra subscription/room membership theo resource.
- Bảo vệ outbound data routing và permission changes.
- Session/token revocation, resource cleanup và logging redaction.

**Không được đánh đồng “đã authenticated ở handshake” với “mọi message được authorized”.**

## 3. Cây luồng: security nào còn, security nào phải viết lại?

~~~mermaid
flowchart TD
    A["Browser / non-browser"] --> B["HTTP handshake + Origin"]
    B --> C["HTTP auth, TLS, cookie, firewall"]
    C --> D{"Protocol?"}
    D -- "STOMP Spring broker" --> E["STOMP CONNECT + CSRF + Principal"]
    E --> F["MESSAGE/SUBSCRIBE AuthorizationManager"]
    F --> G["Service object ACL"]
    D -- "Servlet native WebSocket" --> H["TextWebSocketHandler"]
    H --> I["Custom action/subscribe authorization"]
    I --> G
    D -- "WebFlux native WebSocket" --> J["Reactive WebSocketHandler"]
    J --> K["Reactive action/subscribe authorization"]
    K --> G
    G --> L["Outbound filtering / revocation / resource limits"]
~~~

Tích hợp HTTP security vẫn có thể bảo vệ handshake, nhưng không có lý do tự động để một raw text frame đi qua `CsrfChannelInterceptor`, `MessageMatcherDelegatingAuthorizationManager` hay user destination broker. Đó là một **đường xử lý khác**, cần review như một migration security-critical.

## 4. HTTP handshake và application message phải được tách riêng

### 4.1. Handshake minh họa

~~~http
GET /ws/orders HTTP/1.1
Host: api.example.com
Connection: Upgrade
Upgrade: websocket
Sec-WebSocket-Version: 13
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Origin: https://app.example.com
Cookie: SESSION=<cookie-if-browser-allows>
~~~

Khi thành công trên HTTP/1.1:

~~~http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: <server-generated-value>
~~~

WebSocket qua những HTTP versions khác có thể có handshake khác, nhưng điều cốt lõi giữ nguyên: **HTTP request security diễn ra trước khi transport sẵn sàng**, và dữ liệu gửi sau nâng cấp không phải những HTTP POST/PUT riêng biệt.

### 4.2. HTTP 101 không xác thực từng business action

`SecurityFilterChain` của Servlet hay `SecurityWebFilterChain` của Reactive có thể yêu cầu HTTP request `GET /ws/orders` phải authenticated. Tuy nhiên:

- HTTP `authorizeHttpRequests` hoặc `authorizeExchange` không chạy lại cho từng WebSocket text/binary frame.
- HTTP `CsrfFilter` hoặc Reactive HTTP CSRF không kiểm tra mỗi JSON `orders.cancel` như một REST POST.
- Browser WebSocket không dùng Fetch CORS preflight OPTIONS giống HTTP Fetch.
- HTTP 101 chỉ chứng minh transport mở, **không chứng minh user được xem order của Bob**.
- Một WebSocket session có thể tồn tại lâu sau khi HTTP session/JWT/role đã đổi trạng thái.

### 4.3. HTTP response lỗi khác lỗi protocol

| Quan sát | Giai đoạn |
| --- | --- |
| HTTP 401/302 | Login/auth entry point trước handshake |
| HTTP 403 | HTTP authorization, Origin hoặc firewall trước upgrade |
| CSP `connect-src` chặn | Browser policy trước hoặc trong quá trình mở socket |
| HTTP 101 nhưng frame sau bị từ chối | App protocol, per-message authorization |
| Close code WebSocket `1008` | Policy violation sau handshake |
| Client nhận order của user khác | Service/outbound ACL, không phải HTTP status |

Sau HTTP 101, đừng chờ một HTTP response 403 mới cho từng JSON frame. Xử lý lỗi bằng protocol response/close semantics thích hợp.

## 5. Servlet native WebSocket: đăng ký handler, không dùng STOMP broker

### 5.1. WebSocketConfigurer cơ bản

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration
@EnableWebSocket
class NativeWebSocketConfiguration implements WebSocketConfigurer {

    private final OrderNativeWebSocketHandler handler;

    NativeWebSocketConfiguration(OrderNativeWebSocketHandler handler) {
        this.handler = handler;
    }

    @Override
    public void registerWebSocketHandlers(
        WebSocketHandlerRegistry registry
    ) {
        registry.addHandler(handler, "/ws/orders")
            .setAllowedOrigins("https://app.example.com");
    }
}
~~~

`@EnableWebSocket` cho Servlet native handlers **khác** `@EnableWebSocketMessageBroker` cho STOMP. `setAllowedOrigins` quyết định website browser được phép kết nối, không xác thực Alice hay quyền trên order ID.

Một non-browser client có thể giả Origin nên vẫn cần authentication.

### 5.2. HTTP SecurityFilterChain chỉ bảo vệ handshake và APIs

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ServletHandshakeSecurity {

    @Bean
    SecurityFilterChain chain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/ws/orders")
                    .authenticated()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(form -> form.permitAll())
            // Không tắt HTTP CSRF toàn ứng dụng.
            .build();
    }
}
~~~

Ví dụ chọn HTTP session authentication: browser gửi cookie tại GET handshake, Spring Security xác minh principal. `formLogin` cần user store/login flow thực tế. Những REST POST dùng cookie vẫn được HTTP CSRF bảo vệ theo chính sách; **native WebSocket frames sau handshake không tự được HTTP CsrfFilter xử lý**.

Nếu client chỉ mang bearer token trong first JSON message mà không có HTTP cookie, route `authenticated()` có thể chặn trước khi frame đầu được gửi. Không kết hợp hai mô hình mà thiếu thiết kế.

### 5.3. Handler nhận Principal và kiểm tra object ACL

~~~java
import java.io.IOException;
import java.security.Principal;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

record OrderView(long orderId, String state) {}

interface OrderVisibilityService {
    // Implementation phải kiểm tra ownership/tenant thực sự.
    OrderView findVisible(String username, long orderId);
}

@Component
class OrderNativeWebSocketHandler extends TextWebSocketHandler {

    private final ObjectMapper mapper;
    private final OrderVisibilityService orders;

    OrderNativeWebSocketHandler(
        ObjectMapper mapper,
        OrderVisibilityService orders
    ) {
        this.mapper = mapper;
        this.orders = orders;
    }

    @Override
    protected void handleTextMessage(
        WebSocketSession session,
        TextMessage message
    ) throws IOException {
        Principal principal = session.getPrincipal();

        if (principal == null) {
            session.close(CloseStatus.POLICY_VIOLATION);
            return;
        }

        JsonNode data = mapper.readTree(message.getPayload());

        if (data == null || !data.isObject()
                || !"orders.lookup".equals(data.path("type").asText())
                || !data.path("orderId").isIntegralNumber()
                || !data.path("orderId").canConvertToLong()) {
            session.close(CloseStatus.BAD_DATA);
            return;
        }

        long orderId = data.path("orderId").asLong();

        OrderView result = orders.findVisible(
            principal.getName(),
            orderId
        );

        session.sendMessage(new TextMessage(
            mapper.writeValueAsString(result)
        ));
    }
}
~~~

**Giới hạn ví dụ:** Đây là một handler minh họa, không phải production-ready. Cần error handling, schema validation sâu hơn, payload/rate limits, concurrency-safe writes, close lifecycle, audit, session revocation và kiểm soát đối tượng tại service. `OrderVisibilityService` không được chỉ gọi `findById` và trả mọi order.

### 5.4. Đừng tin role/userId ở JSON

~~~json
{
  "type": "orders.lookup",
  "orderId": 2002,
  "userId": "bob",
  "role": "ADMIN"
}
~~~

Nếu Alice tự gửi payload trên, server vẫn dùng **Principal Alice** từ authentication, không lấy `userId`/`role` làm nguồn danh tính. Order ID 2002 thuộc Bob phải bị từ chối nếu Alice không có quyền dù Alice đã login và WebSocket handshake thành công.

## 6. Servlet native: protocol actions thay thế STOMP SEND/SUBSCRIBE

### 6.1. Định nghĩa command allowlist

~~~text
orders.lookup       -> đọc order có quyền
orders.cancel       -> thay đổi trạng thái có điều kiện
orders.subscribe    -> nhận cập nhật order/tenant có quyền
orders.unsubscribe  -> hủy subscription theo phiên
chat.publish        -> gửi room mà user là thành viên
chat.subscribe      -> nghe room được phép
admin.broadcast     -> chỉ người có quyền quản trị
unknown             -> deny
~~~

Nếu một native handler chỉ kiểm `session.getPrincipal() != null` rồi cho mọi `type`, user thường có thể gửi lệnh admin hoặc nghe tenant khác. Cần quyền riêng theo **action và resource**.

### 6.2. Subscribe là quyền nhận dữ liệu tương lai

~~~json
{"type":"orders.subscribe","orderId":2002}
~~~

Một người có quyền gửi `orders.lookup` không tự có quyền đăng ký theo dõi order 2002. Với subscription phải kiểm:

1. Principal đã được xác minh.
2. ID/resource/tenant hợp lệ.
3. Quyền subscribe tại thời điểm đăng ký.
4. Quota subscriptions và fan-out.
5. Permission changes sau khi subscribe.
6. Đúng target khi server phát dữ liệu.
7. Cleanup khi socket bị đóng/logout.

Đừng lấy một lần `subscribe` thành công làm “quyền vĩnh viễn”.

### 6.3. Native không có user destination broker tự động

Trong STOMP, `/user/queue/...` và `SimpMessagingTemplate#convertAndSendToUser` hỗ trợ routing theo principal/session. Một `TextWebSocketHandler` thuần không tự có registry broker tương đương. Ứng dụng phải tự quản lý mapping user→connections, multi-tab/devices, multi-node broker và kiểm soát data trước outbound.

## 7. WebFlux native: đăng ký WebSocketHandler và adapter

### 7.1. WebFlux không tự là Servlet STOMP

Spring WebFlux native sử dụng:

- `org.springframework.web.reactive.socket.WebSocketHandler`.
- `WebSocketSession` và `WebSocketMessage`.
- `HandlerMapping` ánh xạ URL tới handler.
- `WebSocketHandlerAdapter`/`WebSocketService` cho quá trình upgrade.
- Reactor `Flux`/`Mono` để xử lý messages.

Không có lý do để các frame này tự đi qua `CsrfChannelInterceptor` hoặc `MessageMatcherDelegatingAuthorizationManager` dành cho STOMP.

### 7.2. Mapping + adapter minh họa

~~~java
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.reactive.handler.SimpleUrlHandlerMapping;
import org.springframework.web.reactive.socket.server.support.WebSocketHandlerAdapter;

@Configuration
class NativeReactiveWebSocketConfig {

    @Bean
    HandlerMapping webSocketMapping(
        AuthorizedReactiveOrderHandler handler
    ) {
        SimpleUrlHandlerMapping mapping =
            new SimpleUrlHandlerMapping();
        mapping.setUrlMap(Map.of("/ws/orders", handler));
        mapping.setOrder(-1);
        return mapping;
    }

    @Bean
    WebSocketHandlerAdapter webSocketHandlerAdapter() {
        return new WebSocketHandlerAdapter();
    }
}
~~~

Đây là routing infrastructure, **không** tự tạo authentication, Origin validation hoặc business authorization. Nếu Spring Boot/framework đã có WebSocketHandlerAdapter phù hợp, không tạo hai beans cùng vai trò một cách tùy tiện; kiểm tra actual HandlerMapping priority.

### 7.3. Reactive WebSocketHandler với permission check

~~~java
import java.security.Principal;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.WebSocketSession;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

interface ReactiveOrderService {
    // Parse/validate message, kiểm action, order/tenant ACL.
    Mono<String> authorizeAndReply(
        Principal user, String rawText
    );
}

@Component
class AuthorizedReactiveOrderHandler implements WebSocketHandler {

    private final ReactiveOrderService orders;

    AuthorizedReactiveOrderHandler(ReactiveOrderService orders) {
        this.orders = orders;
    }

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        return session.getHandshakeInfo()
            .getPrincipal()
            .switchIfEmpty(Mono.error(
                new AccessDeniedException("Unauthenticated")
            ))
            .flatMap(user -> {
                Flux<WebSocketMessage> replies = session.receive()
                    .concatMap(frame -> {
                        if (frame.getType() !=
                                WebSocketMessage.Type.TEXT) {
                            return Mono.error(
                                new IllegalArgumentException(
                                    "Unsupported frame"
                                )
                            );
                        }

                        if (frame.getPayload()
                                .readableByteCount() > 8192) {
                            return Mono.error(
                                new IllegalArgumentException(
                                    "Message too large"
                                )
                            );
                        }

                        return orders.authorizeAndReply(
                                user, frame.getPayloadAsText()
                            )
                            .map(session::textMessage);
                    });

                return session.send(replies);
            });
    }
}
~~~

`ReactiveOrderService` chỉ là interface. Production phải có schema/payload limits ở tầng protocol phù hợp, output queue limits, rate limits, error redaction, cancellation, auth expiry và tenant permission. `concatMap` tuần tự hóa một phần processing nhưng không thay security, quotas hay flow control. Nếu dùng blocking database/API calls trong service, phải chuyển sang nonblocking I/O hoặc cô lập công việc blocking trên scheduler được giới hạn.

### 7.4. Tránh tự subscribe() và return Mono.empty()

Phản ví dụ:

~~~java
// Sai vì unmanaged subscriptions và lifecycle bị tách khỏi handler.
session.receive().subscribe(frame -> {
    service.execute(frame.getPayloadAsText()).subscribe();
});
return Mono.empty();
~~~

Handler có thể kết thúc sớm, mất cancellation, lỗi và Reactor Context, gây resource leaks. **Return một reactive composition** như `session.send(replies)`; không tự tạo nested subscriptions chỉ để xử lý “nhanh hơn”.

## 8. Reactive SecurityWebFilterChain chỉ bảo vệ HTTP handshake

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class NativeReactiveHttpSecurity {

    @Bean
    SecurityWebFilterChain securityChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/ws/orders")
                    .authenticated()
                .pathMatchers("/api/**").authenticated()
                .anyExchange().denyAll()
            )
            .formLogin(Customizer.withDefaults())
            // HTTP CSRF vẫn theo policy của ứng dụng.
            .build();
    }
}
~~~

Ví dụ dùng session-based HTTP authentication. `ServerHttpSecurity` không có nhiệm vụ parse/authorize một JSON frame `orders.lookup`. Reactive HTTP CSRF không thay protocol-level CSRF/Origin protection và object authorization.

Nếu kiến trúc chỉ gửi bearer **sau** khi socket mở, HTTP `authenticated()` sẽ không thể nhận token này tại handshake. Cần handshake policy hẹp cho token-first, với timeouts/connection quotas và không mở business access trước verification.

## 9. Origin policy cho native WebSocket khác HTTP CORS

### 9.1. CORS REST không tự bao phủ WebSocket

Một cross-origin HTTP `fetch` có thể cần CORS và preflight OPTIONS. Native WebSocket browser không chạy Fetch CORS preflight theo cùng cách. Browser có thể gửi `Origin` trong handshake; server phải xác minh Origin khi cần phòng chống website lạ lợi dụng session cookie.

- Same-origin mặc định không nên bị giả định cho mọi raw WebSocket endpoint nếu chưa kiểm handshake implementation.
- `CorsWebFilter` hoặc `http.cors()` cho HTTP API không tự kiểm mọi WebSocket frames.
- CORS không là user authentication.
- Non-browser WebSocket client có thể giả Origin.
- Same-site cookie policy không có nghĩa same-origin Origin validation.

### 9.2. Reactive WebFilter Origin guard cho browser-only endpoint

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.WebFilter;

@Configuration
class NativeReactiveOriginPolicy {

    @Bean
    @Order(Ordered.HIGHEST_PRECEDENCE)
    WebFilter webSocketOriginGuard() {
        return (exchange, chain) -> {
            String path = exchange.getRequest()
                .getPath().pathWithinApplication().value();

            if (!"/ws/orders".equals(path)) {
                return chain.filter(exchange);
            }

            String origin = exchange.getRequest()
                .getHeaders().getOrigin();

            if (!"https://app.example.com".equals(origin)) {
                exchange.getResponse()
                    .setStatusCode(HttpStatus.FORBIDDEN);
                return exchange.getResponse().setComplete();
            }

            return chain.filter(exchange);
        };
    }
}
~~~

Chính sách minh họa **chỉ hỗ trợ browser ở app origin đã định**, nên từ chối Origin vắng mặt/sai cho toàn exact path. Nếu có legitimate non-browser clients, định nghĩa authentication/Origin policy riêng chứ không tin Origin do client khai. Kiểm tra path sau reverse proxy và thứ tự filters; WebFilter trên kiểm mọi HTTP request tới path đó, không riêng WebSocket Upgrade, nên URL phải dành riêng cho WebSocket nếu dùng nguyên mẫu.

### 9.3. Same-site và same-origin khác nhau

| Trang cha | Endpoint | Ghi chú |
| --- | --- | --- |
| `https://app.example.com` | `wss://app.example.com/ws/orders` | Public same-origin deployment hợp lý |
| `https://app.example.com` | `wss://api.example.com/ws/orders` | Khác host, cần Origin policy phù hợp |
| `http://localhost:3000` | `ws://localhost:8080/ws/orders` | Khác port |
| `https://app.example.com` | `ws://app.example.com/ws/orders` | Mixed content/downgrade; không phù hợp production |

Cookie `SameSite=Lax` có thể hoạt động trong những ngữ cảnh same-site giữa subdomain, nhưng không dùng nó thay kiểm tra browser Origin.

## 10. CSRF và Cross-Site WebSocket Hijacking với WebSocket thuần

### 10.1. Threat model cookie phiên

Alice đã login backend bằng HTTP session cookie. Một website không tin cậy thử:

~~~javascript
const socket = new WebSocket("wss://api.example.com/ws/orders");

socket.onopen = () => {
  socket.send(JSON.stringify({
    type: "orders.lookup",
    orderId: 1001
  }));
};
~~~

Nếu browser gửi ambient cookie theo policy, backend cho handshake từ Origin lạ và raw handler chỉ tin session, attacker có thể đọc/ghi dưới identity nạn nhân. Đây là nguy cơ **Cross-Site WebSocket Hijacking (CSWSH)**.

### 10.2. Không có CsrfChannelInterceptor cho JSON raw

Trong Spring Servlet/STOMP, `@EnableWebSocketSecurity` có thể kiểm tra CSRF token ở native STOMP `CONNECT`. Nhưng khi protocol là JSON raw:

- Không có STOMP CONNECT mặc định.
- Không có native STOMP `X-CSRF-TOKEN` header được parse tự động.
- `CsrfChannelInterceptor` không tự tìm JSON `{"type":"auth"}` để xác minh.
- HTTP `CsrfFilter`/Reactive HTTP CSRF không chạy trên từng frame.
- Spring Security không tự tạo một token-binding rule cho custom message.

**Nếu bỏ STOMP, phải đánh giá lại cơ chế chống CSWSH của riêng protocol.**

### 10.3. Các chiến lược cần cân nhắc

| Chiến lược | Bối cảnh | Bảo vệ và giới hạn |
| --- | --- | --- |
| HTTP authentication + exact Origin allowlist | Browser session/cookie | Giảm cross-origin browser attack, cần business ACL và bảo vệ XSS |
| Session-bound proof ở first message | Cookie-based custom protocol | Kiểm expected token từ server/session, không tự tin giá trị client khai |
| Bearer verified ở first message | Token-only, không ambient cookie | Không tự thay Origin guard, token expiry/revocation, object ACL |
| HTTP Authorization ở handshake | Non-browser client hỗ trợ custom headers | Browser `new WebSocket` không hỗ trợ arbitrary headers như Fetch |
| Short-lived one-time connection ticket | Khi browser token-only không truyền HTTP header | TTL ngắn, audience/scope, replay prevention và logging redaction |

Không lấy access token dài hạn làm query string cho WebSocket nếu tránh được. URL có thể bị log bởi proxy/tracing. `Sec-WebSocket-Protocol` cũng không phải nơi chứa credentials phổ dụng; nó dùng để thương lượng subprotocol.

### 10.4. CSRF token không phải bearer token

Một CSRF token hợp lệ không xác thực Alice là admin và không cho phép truy cập order Bob. Một bearer access token hợp lệ không tự bật CSRF token verification trên native handler. Hai cơ chế cần mục tiêu rõ và phải được kiểm thử độc lập.

## 11. Token-first authentication: state machine không được xử lý lệnh trước verify

### 11.1. Protocol định nghĩa rõ first message

Nếu backend cho phép HTTP handshake anonymous trên **một path hẹp**, frontend có thể gửi:

~~~json
{"type":"auth","accessToken":"<short-lived-token>"}
~~~

Chỉ sau server-side verification mới cho:

~~~json
{"type":"orders.lookup","orderId":1001}
~~~

Một state machine an toàn:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING_AUTH
    PENDING_AUTH --> AUTHENTICATED: auth token verified
    PENDING_AUTH --> CLOSED: invalid/missing auth or deadline
    PENDING_AUTH --> CLOSED: business action before verification
    AUTHENTICATED --> AUTHENTICATED: permitted action + object ACL
    AUTHENTICATED --> CLOSED: expired/revoked/forbidden/close
    CLOSED --> [*]
~~~

### 11.2. Pseudocode cho first-message gate

~~~text
onOpen:
    state = PENDING_AUTH
    arm short authentication deadline
    do not subscribe private topics

onMessage(frame):
    reject malformed/oversized payload

    if state == PENDING_AUTH:
        if frame.type != "auth": close policy violation
        auth = verify(frame.accessToken)
        if invalid: close policy violation
        atomically set server principal and state = AUTHENTICATED
        send minimal auth.ok
        return

    if state == AUTHENTICATED:
        decision = authorize(principal, frame.action, objectId)
        if denied: reject without side effect
        else: execute and route only permitted data

onClose:
    cancel subscriptions/timers
    release resources
    clear session-bound state
~~~

**Quan trọng:** khi client gửi `auth` và business message ngay sau nhau, verifier có thể bất đồng bộ. Handler không được để message thứ hai chạy trước khi auth hoàn tất. Cần serialize/gate state transitions, bounded queue hoặc từ chối các messages đến sớm; không có race giữa authenticated state và side effects.

### 11.3. Token verifier không phải parser claims

Verifier phải đánh giá chữ ký, issuer, audience, token type, expiration/not-before, revocation/scopes và user/tenant state phù hợp. Không lấy `{"role":"ADMIN"}` hoặc `{"userId":"bob"}` tự khai trong JSON làm quyền.

### 11.4. Pending-auth handshake cần được giới hạn tài nguyên

Một unauthenticated client có thể mở socket rồi không gửi auth. Cần authentication deadline, max connections, per-IP/user rate limits, message size limits và idle timeout. Không mở `permitAll()` cho toàn bộ HTTP APIs chỉ vì một endpoint token-first cần handshake trước authentication.

## 12. Quyền trên từng action, subscription, object và outbound

### 12.1. Ví dụ bảng policy

| Raw action | Quyền ở mức action | Quyền ở mức tài nguyên |
| --- | --- | --- |
| `orders.lookup` | ROLE_USER hoặc scope READ | Order thuộc tenant/ACL của principal |
| `orders.cancel` | Scope CANCEL | Ownership, trạng thái đơn, business rule |
| `orders.subscribe` | Scope LISTEN | Quyền nghe order/tenant lúc subscribe và sau đó |
| `chat.publish` | Member role | Thành viên của room, input moderation |
| `chat.subscribe` | Member role | Room membership/tenant hiện hành |
| `admin.broadcast` | ADMIN | Đúng tenant và giới hạn nội dung |
| Unknown action | **DENY** | Không xử lý |

Một user đã được HTTP authentication không tự có quyền vào mọi action.

### 12.2. Object-level authorization là bắt buộc

Alice gửi:

~~~json
{"type":"orders.lookup","orderId":2002,"userId":"bob"}
~~~

Server phải dùng verified Principal Alice rồi kiểm ownership/tenant của order 2002; không lấy `userId` hay `tenantId` client tự khai để vượt quyền. Nếu service trả order Bob chỉ vì Alice có ROLE_USER, đó là lỗi BOLA/IDOR.

### 12.3. Subscription tạo quyền nhận dữ liệu trong tương lai

~~~json
{"type":"orders.subscribe","orderId":2002}
~~~

Cần kiểm quyền khi subscribe và có cơ chế thu hồi/revalidate khi user rời tenant, order đổi owner hoặc logout. Với một raw WebSocket, không có STOMP broker tự động quản lý `/user/queue`; ứng dụng phải sở hữu connection registry và routing/ACL.

### 12.4. Inbound và outbound là hai lớp khác nhau

Một handler có thể kiểm chặt incoming commands nhưng publisher vẫn phát thông tin riêng vào public topic. Quyền gửi, quyền subscribe và quyền server publish đều phải được xác minh. Không coi một `authorized subscribe` trong quá khứ là quyền vĩnh viễn khi data hoặc vai trò đã thay đổi.


## 13. Reactor Context và bất đồng bộ: Principal có thể mất ở ranh giới nào?

### 13.1. Servlet thread-local không phải Reactor Context

Trong Servlet, Spring Security thường cung cấp `SecurityContextHolder` gắn với luồng xử lý HTTP request; khi chuyển sang executor hoặc callback khác, không được cho rằng thread-local security context luôn còn. Spring WebSocket/STOMP có cơ chế duy trì principal ở messaging context theo integration, nhưng một custom native handler không mặc định kế thừa mọi messaging interceptor.

Trong WebFlux, Spring Security hoạt động với **Reactor Context**; `ReactiveSecurityContextHolder` có thể cung cấp reactive security context khi pipeline được thiết lập đúng. Nó không tương đương việc đọc `SecurityContextHolder.getContext()` từ một event loop thread bất kỳ.

### 13.2. Truyền Principal một cách minh bạch vào service

Ví dụ:

~~~java
interface ReactiveOrderPolicy {
    Mono<Boolean> canRead(
        Principal principal, long orderId
    );
}

interface ReactiveOrderService {
    Mono<String> authorizeAndReply(
        Principal principal, String rawText
    );
}
~~~

Handler lấy principal từ HTTP handshake và truyền xuống service theo tham số. Điều này giảm phụ thuộc vào implicit context propagation khi code chuyển scheduler hoặc callback. Service phải kiểm tenant, role và ownership tại thời điểm thao tác; principal có thể là snapshot và không đồng nghĩa user vẫn còn mọi quyền.

### 13.3. Tránh nested subscribe()

Phản ví dụ:

~~~java
// Anti-pattern: tách xử lý khỏi lifecycle của WebSocket.
session.receive().subscribe(message -> {
    service.handle(message.getPayloadAsText()).subscribe();
});
return Mono.empty();
~~~

Vấn đề: unmanaged subscriptions, mất cancellation/error propagation, có thể kết thúc handler quá sớm, thiếu backpressure, và có rủi ro mất context. Compose `receive()`, `concatMap()`/`flatMap()` có concurrency bound, và `session.send(...)` thành reactive pipeline được return để framework sở hữu vòng đời.

### 13.4. Không block event loop

Một handler WebFlux gọi JPA/HTTP blocking:

~~~java
// Không đưa trực tiếp I/O blocking vào event-loop path:
Order order = blockingRepository.findById(orderId).orElseThrow();
~~~

có thể khiến nhiều connections cùng bị nghẽn. Ưu tiên reactive database/client APIs và nonblocking permission checks; nếu không thể, cô lập blocking work trên scheduler có giới hạn và theo dõi tải. Tránh gọi `block()` trong `WebSocketHandler#handle`.

### 13.5. Security context không tự cập nhật permission changes

Dù principal được propagate đúng, Alice có thể rời tenant hoặc bị gỡ role sau khi socket mở. Cần object ACL hiện tại, revocation signals, subscription cleanup hoặc buộc reconnect. **Context propagation không phải authorization revalidation.**

## 14. Backpressure, bounded queues và bảo vệ tài nguyên

### 14.1. Reactive stream không tự ngăn flood

Reactor hỗ trợ composition và backpressure, nhưng không có nghĩa một client WebSocket độc hại không thể tiêu tốn tài nguyên. Một attacker có thể:

- Mở nhiều WebSocket connections không authenticating.
- Gửi hàng nghìn JSON frames/giây.
- Gửi payload quá lớn hoặc malformed JSON làm parser tiêu tốn CPU/memory.
- Tạo hàng nghìn subscriptions hoặc room joins.
- Đọc chậm và làm outbound buffering tích tụ.
- Gây nhiều DB queries ACL tốn kém.
- Reconnect liên tục sau khi bị từ chối.

`concatMap` trong ví dụ tuần tự hóa một phần xử lý inbound, nhưng cần giới hạn queue, tốc độ và concurrent operations ở những tầng phù hợp. Không dùng `onBackpressureBuffer()` không giới hạn như một “giải pháp” cho burst traffic.

### 14.2. Các giới hạn cần có

| Bề mặt | Rủi ro | Bảo vệ cần cân nhắc |
| --- | --- | --- |
| Handshake | Connection flood | Rate limits, max concurrent connections/IP/user |
| Pending-auth | Socket chưa xác thực giữ tài nguyên | Deadline rất ngắn, connection caps |
| Inbound frame | Payload/JSON abuse | Max frame/message size, schema validation |
| Application commands | Flood DB/service | Per-user/action rate limits, quotas |
| Permission checks | N+1 ACL queries | Bounded concurrency, cache có invalidation đúng |
| Subscriptions | Fan-out và memory bloat | Max subscriptions/connection, membership ACL |
| Outbound queue | Slow consumer | Bounded buffer + drop/close policy có chủ đích |
| Ping/pong/idle | Zombie connections | Heartbeats, idle timeouts |
| Authentication retries | Reconnect storm | Backoff, jitter, stop khi revoked |
| Multi-node | Excess broker traffic | Per-tenant quotas và observability |

### 14.3. Close codes không phải HTTP status

Sau HTTP 101, lỗi không còn là HTTP 403 mới trên một JSON frame. Một server có thể dùng WebSocket close code `1008` cho policy violation, `1009` cho message quá lớn, hoặc gửi JSON error theo protocol rồi đóng. Không đưa stack trace, token, quyền chi tiết của object hay user secrets vào close reason.

### 14.4. Hạn chế dữ liệu outbound

Nếu một user nhận thông báo realtime chậm, không nên để buffered messages tăng mãi. Cân nhắc bounded buffering, conflation của những trạng thái có thể bỏ qua, hoặc đóng connection khi quá tải. Chính sách drop phải xét nghiệp vụ: những lệnh quan trọng cần REST/transaction + reconciliation thay vì hy vọng mọi WebSocket event tới đúng thứ tự.

## 15. Authentication expiry, logout và revocation trên socket sống lâu

### 15.1. Một lần handshake hợp lệ không cấp quyền vĩnh viễn

Ví dụ:

~~~text
09:00 Alice đăng nhập và mở WebSocket.
09:20 Alice subscribe vào room của tenant A.
10:00 Alice logout trong tab khác.
10:05 Admin loại Alice khỏi tenant A.
10:10 Một node khác phát thông báo riêng của tenant A.
~~~

Nếu server chỉ kiểm quyền lúc 09:00 và 09:20, socket cũ có thể tiếp tục nhận dữ liệu dù quyền đã thay đổi. Đây không phải lỗi có thể sửa chỉ bằng HTTP CSRF hoặc `Origin`.

### 15.2. Các cách xử lý

- Đóng socket khi HTTP session bị invalidated, access token hết hạn hoặc bị thu hồi (theo mô hình hỗ trợ).
- Xác định max connection lifetime và periodic/triggered revalidation.
- Kiểm membership tại thời điểm subscribe và trước publish dữ liệu nhạy cảm.
- Phát revocation event tới connection registry/broker khi quyền đổi.
- Hủy subscriptions và tasks khi socket đóng, user đổi tenant hoặc logout.
- Không gửi dữ liệu riêng sau khi session đã trở nên anonymous.
- Kiểm trường hợp nhiều tabs/devices; logout một nơi có thể yêu cầu đóng tất cả sessions liên quan.

### 15.3. JWT hết hạn sau first-message auth

Một JWT được xác minh lúc mở socket không tự khiến framework đóng socket đúng tại `exp`. Custom protocol phải định nghĩa chính sách: đóng khi hết hạn, yêu cầu reauth có kiểm chứng, hoặc giới hạn socket TTL. Với dữ liệu riêng, nên từ chối khi user state/tenant membership không còn hợp lệ dù principal snapshot vẫn tồn tại.

### 15.4. Không dùng auth refresh tự khai

~~~json
{"type":"auth.refresh","userId":"admin","role":"ADMIN"}
~~~

không phải reauthentication. Nếu cho refresh trong cùng socket, phải xác minh credential mới, bảo đảm transition nguyên tử và không cho message tiếp tục với principal sai. Cách đơn giản dễ audit hơn có thể là đóng socket cũ rồi kết nối lại với credential hợp lệ.

## 16. Những lớp bảo vệ HTTP và trình duyệt vẫn quan trọng

### 16.1. CORS khác WebSocket Origin

Một HTTP Fetch khác origin có thể chịu CORS/OPTIONS preflight. Native WebSocket không dùng cơ chế Fetch CORS preflight theo cùng cách. Server WebSocket cần Origin policy riêng nếu dựa vào cookie session/browser clients. `Access-Control-Allow-Origin` không thay message authentication hoặc authorization.

### 16.2. HTTP CSRF không kiểm text frames

`CsrfFilter`/Reactive HTTP CSRF áp dụng trên HTTP requests theo policy. Sau upgrade, một native `orders.cancel` không tự biến thành HTTP POST để được HTTP CSRF validation. Khi dùng ambient browser credentials, hãy đánh giá CSWSH và cân nhắc session-bound proof ở first message nếu yêu cầu threat model.

### 16.3. CSP connect-src

~~~http
Content-Security-Policy: connect-src 'self' wss://api.example.com
~~~

CSP trên frontend có thể giới hạn endpoints script được kết nối. Đây là **browser-side control**, không phải server-side ACL. XSS trong frontend tin cậy vẫn có thể dùng socket/token theo quyền user; cần chống XSS, CSP và server-side authorization.

### 16.4. TLS, HSTS và cookie

Dùng HTTPS/WSS và HSTS khi phù hợp. Cookies nên có `Secure`, `HttpOnly`, `SameSite`, Domain/Path đúng kiến trúc. Same-site không đồng nghĩa same-origin; các subdomains có thể cùng site nhưng không có cùng mức độ tin cậy.

### 16.5. Framing headers và SockJS iframe

`X-Frame-Options`, CSP `frame-ancestors` và `frame-src` kiểm soát HTML iframe embedding. Với native WebSocket không dùng iframe, nới XFO/CSP thường không sửa một lỗi protocol JSON. Chỉ với legacy SockJS iframe transports mới có nhu cầu đánh giá riêng framing.

### 16.6. HTTP firewall không thay message parser

Spring Security HTTP firewall có thể chặn HTTP URL/headers bất thường trước handshake, nhưng không tự kiểm format JSON, quyền `orderId` hoặc rate limits của raw WebSocket frames. Protocol parser và business ACL vẫn thuộc app.

## 17. RSocket, GraphQL WS, Socket.IO và SSE khác STOMP như thế nào?

### 17.1. RSocket over WebSocket

RSocket có semantics như `request-response`, `fire-and-forget`, `request-stream`, `request-channel` cùng setup/metadata. Nó có thể dùng WebSocket làm transport nhưng **không phải STOMP CONNECT/SEND/SUBSCRIBE**.

Yêu cầu bảo mật:

- Xác thực RSocket setup/metadata theo integration và version của stack.
- Route/method authorization cho từng request/stream.
- Quyền object/tenant và scope.
- Stream cancellation, backpressure, rate/concurrency limits.
- Authentication expiry và revocation cho connection dài hạn.
- HTTP handshake Origin policy khi giao tiếp qua browser WebSocket.

Không thể đổi tên `simpDestMatchers` rồi áp vào RSocket routes; cần cơ chế **RSocket Security** và service authorization phù hợp.

### 17.2. GraphQL subscriptions qua WebSocket

Một GraphQL WebSocket implementation có thể dùng subprotocol như `graphql-transport-ws` với messages `connection_init`, `subscribe`, `next` và `complete`. Những names/protocol semantics phụ thuộc thư viện.

**connection_init không phải STOMP CONNECT.** Payload authorization chỉ có giá trị khi server thực sự xác minh. Khi client authenticated, mỗi operation/field/selection vẫn cần ACL: user không được lấy dữ liệu tenant khác chỉ vì có một WebSocket session hợp lệ.

Các GraphQL subscriptions có thể kéo dài rất lâu và phát dữ liệu liên tục: phải xét operation authorization, per-emission filtering, revocation, depth/complexity limits và quota subscriptions.

### 17.3. Socket.IO

Socket.IO có protocol riêng cho events, namespaces, rooms và transports. Dù có thể dùng WebSocket, một raw `new WebSocket` gửi JSON không tự nói đúng Socket.IO protocol.

Nếu dùng Socket.IO-compatible stack, quyền room membership, event types, namespace middleware, JWT/session và server publish routing thuộc framework đó. Spring STOMP `@EnableWebSocketSecurity` không bảo vệ các Socket.IO events nếu chúng không đi qua STOMP pipeline.

### 17.4. Server-Sent Events

SSE dùng HTTP response stream **một chiều server → client**. Nếu ứng dụng chủ yếu cần server push notifications, SSE có thể đơn giản hơn một full-duplex WebSocket.

- Authentication/authorization của SSE GET là HTTP.
- Cross-origin EventSource có CORS/credential considerations.
- Server vẫn phải filter events theo user/tenant và kiểm tra quyền khi stream kéo dài.
- Client commands đổi trạng thái dùng HTTP POST/PUT/DELETE riêng; áp dụng HTTP CSRF khi dùng cookie authentication.
- Event IDs/replay/reconnect và caching phải được kiểm soát.

SSE không tự thay toàn bộ STOMP SEND hoặc native bidirectional messaging.

### 17.5. So sánh nhanh

| Công nghệ | Client actions | Nơi phân quyền |
| --- | --- | --- |
| Spring Servlet STOMP | SEND/SUBSCRIBE destinations | Message AuthorizationManager + service ACL |
| Servlet native WS | Custom text/binary commands | Handler và service |
| WebFlux native WS | Reactive custom commands | Reactive handler/service |
| RSocket | Routes/request streams | RSocket security integration + service |
| GraphQL WebSocket | Operations/subscriptions/fields | GraphQL connection + operation/data ACL |
| Socket.IO | Events/rooms/namespaces | Protocol middleware và business ACL |
| SSE | Nhận server events | HTTP endpoint + per-event data ACL |

## 18. Chọn kiến trúc authentication nhất quán

### 18.1. HTTP session inheritance

~~~text
HTTP login -> authenticated session cookie
GET /ws/orders + cookie -> HTTP Principal Alice
Origin guard -> trusted browser origin
Native handler -> uses Principal Alice
Every command -> action + resource authorization
Logout/revocation -> close/revalidate socket
~~~

Đây là mô hình dùng session cookie; HTTP handshake có thể yêu cầu authenticated. Rủi ro ambient cookie/CSWSH đòi Origin policy và có thể proof ở custom protocol tùy threat model. Session principal không bảo đảm còn quyền hiện thời sau nhiều giờ.

### 18.2. First-message bearer

~~~text
GET /ws/orders -> hẹp, có thể chưa authenticated
state = PENDING_AUTH
first frame -> verify bearer -> authenticated principal
business frames -> action/object/tenant ACL
expiry/revocation -> close/revalidate
~~~

Model này đòi state gate, timeout, token signature/issuer/audience verification và quotas. HTTP handshake `authenticated()` không phù hợp nếu credential chỉ đến sau khi socket đã mở.

### 18.3. HTTP bearer ở non-browser client

Một client Java/Node.js có thể đặt HTTP Authorization header trên WebSocket handshake nếu client library hỗ trợ. Browser WebSocket constructor chuẩn không cho đặt arbitrary Authorization header như Fetch; không giả định hai client có cùng khả năng.

### 18.4. Không tin những thông tin identity tự khai

~~~json
{"type":"auth","userId":"alice","role":"ADMIN","tenantId":"other"}
~~~

Không được coi là verified identity. Server phải kiểm credentials và xây principal/authorities từ nguồn tin cậy, đồng thời kiểm tenant/object ACL trong business logic.

## 19. Reverse proxy, multi-node và outbound routing

### 19.1. WebSocket qua reverse proxy

Đảm bảo proxy:

- Hỗ trợ HTTP/1.1 Upgrade hoặc cơ chế WebSocket tương ứng.
- Route chính xác public URL đến backend.
- Giữ hoặc xử lý đúng Origin, Cookie và authentication headers.
- Không tin `X-Forwarded-Host`/`X-Forwarded-Proto` tự khai từ client; chỉ tin proxy đáng tin.
- Không log bearer/CSRF tokens hoặc session IDs.
- Có connection idle timeout phù hợp, TLS/WSS và size limits.
- Không biến một WS endpoint thành HTTP GET controller vì route rewrite sai.

Nếu không có HTTP 101, kiểm proxy/TLS/auth/Origin trước khi nhìn application JSON policy.

### 19.2. Nhiều nodes cần connection registry

Native WebSocket connections thường gắn với một backend node. Khi event của Alice phát sinh ở node khác, app cần biết connection nào đang lắng nghe:

- Redis/pub-sub/broker hoặc một distributed event bus khi cần.
- Per-user/per-tenant connection registry được xác thực.
- Đồng bộ role/membership/revocation.
- Session store/token verifier keys nhất quán giữa nodes.
- Khống chế fan-out và bounded output queues.
- Cleanup subscriptions khi node/socket mất kết nối.
- Không dùng sticky routing làm authorization.

STOMP broker/user destination infrastructure đã có những abstractions riêng; native handler **không tự có `SimpUserRegistry` tương đương**.

### 19.3. Logging và metrics không chứa token

Theo dõi handshake accept/reject, Origin mismatch, active connections, auth failures, close codes, message rate, permission denials, outbound queue size, subscription count và reconnect storms.

Không ghi raw `Cookie`, `Authorization`, CSRF token, private JSON payload hoặc query URL chứa credential; dùng identifiers không nhạy cảm và redact khi debug.

## 20. Test đúng tool, không lấy HTTP test thay WebSocket test

### 20.1. Phạm vi công cụ

| Công cụ | Có ích | Không đủ cho |
| --- | --- | --- |
| `MockMvc` | Servlet HTTP auth, CSRF, CORS, routes | WebSocket frames end-to-end |
| `WebTestClient` | Reactive HTTP SecurityWebFilterChain | Toàn bộ custom WS message authorization |
| `WebSocketClient` / `ReactorNettyWebSocketClient` | Real upgrade và text/binary frames | Browser CSP/SOP/cookie behavior |
| Browser DevTools/automation | Origin/cookie/CSP, WS frames | Server-side ACL nếu không assert data/state |
| Service/handler unit tests | Action policy, object/tenant checks, malformed input | Real handshake/filters/proxy |
| Load/chaos integration | Buffering, revocation, multi-node, reconnect | Credential cryptographic verification nếu chưa test |

### 20.2. Reactive WebSocketClient test skeleton

~~~java
import java.net.URI;

import org.springframework.http.HttpHeaders;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;

// Chỉ là setup cho một integration test với server thật:
ReactorNettyWebSocketClient client =
    new ReactorNettyWebSocketClient();

HttpHeaders headers = new HttpHeaders();
headers.setOrigin("https://app.example.com");
headers.add(HttpHeaders.COOKIE, "SESSION=" + aliceSessionCookie);

URI endpoint = URI.create(
    "ws://localhost:" + port + "/ws/orders"
);

// Mono<Void> testSession = client.execute(
//     endpoint,
//     headers,
//     session -> {
//         // Send frames hợp lệ và trái quyền; nhận response/close.
//         // Assert trong bounded timeout.
//         return ...;
//     }
// );
~~~

Mã chưa là unit test chạy độc lập; phải có test server, session cookie/auth, handler, StepVerifier/await assertions và timeouts. Non-browser client có thể giả Origin hoặc custom headers nên không thay browser tests.

### 20.3. Test handshake tách khỏi message

~~~text
HTTP handshake:
  - Session Alice + Origin hợp lệ -> accept
  - Thiếu session khi handshake đòi login -> reject
  - Session Alice hợp lệ + Origin evil -> reject
  - HTTPS frontend, URL WSS đúng CSP -> browser được kết nối

Protocol:
  - Correct identity -> allowed action + owned object -> allowed
  - Correct identity -> other tenant object -> deny
  - Custom bearer missing/invalid -> no business messages accepted
  - Message trước first-message verification -> deny
  - Unknown message type -> deny
  - Session/token revoked -> no more protected outbound
~~~

Để chứng minh Origin guard hoạt động, test **origin lạ với cookie session hợp lệ**; một HTTP 401 không cookie chưa chứng minh Origin validation.

## 21. Ma trận kiểm thử message, subscription và lifecycle

| Ca | Principal / state | Hành động | Kỳ vọng |
| --- | --- | --- | --- |
| A1 | Alice authenticated | `orders.lookup` order 1001 Alice sở hữu | Được phép |
| A2 | Alice authenticated | `orders.lookup` order 2002 Bob sở hữu | Deny, không leak |
| A3 | Alice authenticated | `orders.cancel` order Bob | Deny, không side effect |
| A4 | Alice ROLE_USER | `admin.broadcast` | Deny |
| A5 | PENDING_AUTH | `orders.lookup` trước auth | Deny/close, không execute |
| A6 | Alice | Unknown `type` hoặc malformed JSON | Reject |
| A7 | Alice | JSON vượt size budget | Reject/close phù hợp |
| S1 | Alice thuộc tenant A | Subscribe order tenant A | Cho nếu ACL đúng |
| S2 | Alice không thuộc tenant B | Subscribe order tenant B | Deny |
| S3 | Alice rời tenant A sau subscribe | New outbound private event | Không nhận dữ liệu trái quyền |
| S4 | Alice tự khai `tenantId:"tenantB"` | Subscribe room tenant B | Không thay server identity |
| O1 | Publisher phát private data vào public channel | Bất kỳ inbound state | Phải bị kiểm thử phát hiện và ngăn |
| L1 | JWT hết hạn sau first-message auth | Business request | Close/revalidate theo policy |
| L2 | Logout từ tab khác | Socket cũ nhận event | Không được lộ dữ liệu |
| C1 | Valid Alice session, Origin evil | Open socket | Reject |
| C2 | Non-browser giả Origin app, token sai | First-message auth | Reject |
| C3 | Proxy rewrite sai route | HTTP handshake | Chẩn đoán ở HTTP/proxy, không nới ACL |

**Assertion quan trọng:** error frame sau khi đã gửi private data hoặc đã đổi trạng thái order trái quyền **không phải** test PASS. Phải kiểm tra cả output lẫn side effects.

## 22. Troubleshooting: giả định STOMP cũ gây lỗi ở native/Reactive

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Giữ `@EnableWebSocketSecurity` nhưng native JSON vẫn vượt quyền | Native handler không dùng STOMP inbound pipeline | Per-message auth trong handler/service |
| HTTP 101 rồi lookup order Bob thành công | Chỉ kiểm handshake | Object/tenant ACL |
| Không thấy STOMP CONNECTED trong DevTools | Protocol là raw WebSocket, không có STOMP | Xem custom auth/state response |
| Browser WS không gửi HTTP Authorization object | Constructor không hỗ trợ custom headers | Session handshake hoặc verified first-message |
| `/ws` HTTP 401 trước token-first message | HTTP chain bắt authenticated quá sớm | Handshake path hẹp và first-message gate |
| HTTP CORS đúng nhưng WS mở từ Origin lạ | REST CORS không phải WebSocket Origin guard | Exact Origin policy |
| `ReactiveSecurityContextHolder` null | Pipeline/context bị tách | Compose Mono/Flux, explicit Principal |
| Event loop nghẽn | Blocking I/O trong Reactive chain | Nonblocking service hoặc bounded scheduler |
| Pending-auth sockets chiếm hết tài nguyên | Không có deadline/caps | Timeout và connection limits |
| JWT hết hạn nhưng socket vẫn nhận dữ liệu | Không có expiry/revocation policy | Revalidate/close |
| Alice subscribe dữ liệu tenant B | Thiếu per-subscription ACL | Principal/tenant checks |
| Public topic phát private data | Outbound routing sai | Filter data trước publish |
| Multi-node không gửi đúng user | Missing distributed registry | Broker/registry/revocation propagation |
| RSocket route mở toàn bộ dù setup auth | Thiếu route authorization | Security theo RSocket |
| GraphQL connection_init pass, subscriptions lộ data | Thiếu operation/data ACL | Authorize mỗi operation/field |
| Socket.IO client không nói chuyện với raw WebSocket server | Khác protocol | Dùng đúng implementation |
| SSE stream rò event | Chỉ auth lúc GET, thiếu per-event ACL | Outbound checks |
| SockJS XHR POST 403 | HTTP CSRF/CORS fallback | Không nhầm với native WebSocket |
| CSP `connect-src` chặn WSS | Browser policy | Cho đúng WSS endpoint |
| XFO DENY ở iframe legacy | Framing policy của SockJS iframe | Không nới cho native WS |
| Proxy không trả 101 | Upgrade/TLS/auth/routing | Kiểm tra HTTP handshake trước |
| Logs lộ tokens | Raw headers/messages được log | Redact credential/payload |

### 22.1. Sơ đồ chẩn đoán

~~~mermaid
flowchart TD
    A["Native/Reactive WS thất bại"] --> B{"HTTP handshake được chấp nhận?"}
    B -- "Không" --> C["TLS, CSP, Origin, cookie, HTTP Security, proxy"]
    B -- "Có" --> D{"Principal hay first-message auth hợp lệ?"}
    D -- "Không" --> E["Verifier, deadline, state gate, session"]
    D -- "Có" --> F{"Action/resource ACL đúng?"}
    F -- "Không" --> G["Handler/service authorization"]
    F -- "Có nhưng data sai" --> H["Outbound routing, tenant ACL, revocation"]
    F -- "Có nhưng kết nối mất ổn định" --> I["Backpressure, blocking, quotas, proxy, multi-node"]
~~~

Đừng sửa lỗi JSON business permissions bằng cách tắt CSRF HTTP hoặc `permitAll()` toàn ứng dụng. Đừng sửa lỗi Origin bằng cách tin `userId` trong payload.

## 23. Nên chọn STOMP, native WebSocket hay Reactive protocol khác?

### 23.1. Khi giữ Spring Servlet STOMP

Ưu tiên nếu cần broker destinations, nhiều subscriptions, user destinations và tích hợp `@EnableWebSocketSecurity` cho STOMP inbound. STOMP giúp giảm chi phí tự viết protocol nhưng vẫn cần object ACL, outbound routing, CSRF/cookie strategy và session revocation.

### 23.2. Khi chọn Servlet native

Phù hợp nếu chỉ vài command hoặc có binary payload/protocol chuyên biệt. Đội phát triển phải sở hữu parser, action allowlist, authentication state (nếu token-first), object/tenant ACL, subscriptions, concurrency-safe sending, quotas, error semantics và revocation.

### 23.3. Khi chọn WebFlux native

Phù hợp nếu project đã dùng reactive I/O, cần luồng data tự nhiên với Reactor và chấp nhận quản lý nonblocking services/backpressure. **Reactive không tự cung cấp bảo mật application-message**; cần xây security equivalent.

### 23.4. Khi dùng RSocket/GraphQL/SSE

- RSocket khi cần stream/channel semantics rõ, có security integration RSocket phù hợp.
- GraphQL subscription khi API/domain dùng GraphQL, nhưng vẫn phải kiểm operation/field/data.
- SSE khi chủ yếu cần push server→client và muốn dùng HTTP authorization dễ quản lý.
- Socket.IO nếu thật sự cần những features/protocol đó và có client/server tương thích.

Một sơ đồ quyết định:

~~~mermaid
flowchart TD
    A["Cần cập nhật realtime"] --> B{"Chỉ server -> client?"}
    B -- "Có" --> C["Cân nhắc SSE"]
    B -- "Không" --> D{"Cần STOMP broker/destination semantics?"}
    D -- "Có" --> E["Spring Servlet STOMP + Messaging Security"]
    D -- "Không" --> F{"Ứng dụng Reactive sẵn có?"}
    F -- "Có" --> G["WebFlux native hoặc RSocket/GraphQL theo protocol"]
    F -- "Không" --> H["Servlet native WebSocket"]
    G --> I["Custom message auth + ACL + lifecycle"]
    H --> I
~~~

Đây là hướng chọn ban đầu; quyết định cuối cần xét browser support, proxy, scale, team expertise và threat model.

## 24. Checklist migration bảo mật từ STOMP sang native/Reactive

- [ ] Xác định chính xác protocol và security pipeline hiện tại.
- [ ] Không giả định `@EnableWebSocketSecurity` bảo vệ `WebSocketHandler` thuần.
- [ ] Không giả định `CsrfChannelInterceptor` kiểm raw JSON khi không có STOMP CONNECT.
- [ ] HTTP handshake xác thực phù hợp, WebSocket Origin allowlist được enforce.
- [ ] HTTP CORS không được dùng thay Origin validation.
- [ ] TLS/WSS, HSTS và cookie `Secure`/`HttpOnly`/`SameSite` được đánh giá.
- [ ] Kiến trúc rõ: authenticated HTTP session hay verified first-message token.
- [ ] Nếu token-first, state `PENDING_AUTH` có timeout, race-safe gating và resource quotas.
- [ ] Không gửi long-lived credentials trong URL hoặc tin role/userId tự khai.
- [ ] Parser có schema, action allowlist, size/rate limits, deny unknown.
- [ ] Mỗi action kiểm role/scope và object/tenant ownership.
- [ ] Subscribe/room joins có ACL và revoke khi quyền đổi.
- [ ] Publisher kiểm data/tenant trước khi gửi outbound, không leak public.
- [ ] Authentication expiry/logout/revocation xử lý sockets đang mở.
- [ ] WebFlux không block event loop, không nested subscribe, context được compose đúng.
- [ ] Bounded queues, connection quotas, subscription counts, heartbeat và idle timeout.
- [ ] Proxy Upgrade/Origin/cookie/TLS/forwarded headers đúng trust boundary.
- [ ] Multi-node có connection registry/broker routing và revocation propagation.
- [ ] Không log raw bearer, CSRF token, session cookie, payload riêng tư.
- [ ] Browser CSP `connect-src` chỉ mở trusted HTTP/WSS endpoints.
- [ ] HTTP CSRF còn được giữ cho REST unsafe requests khi dùng cookie.
- [ ] Nếu có SockJS fallback, tách HTTP XHR CSRF/CORS và iframe XFO/CSP.
- [ ] Có HTTP security tests bằng MockMvc/WebTestClient.
- [ ] Có WebSocket client E2E tests cho cả handshake và message.
- [ ] Có browser tests cho Origin/CSP/cookie behaviors.
- [ ] Negative tests chứng minh không business side effects/data leaks.
- [ ] Với RSocket/GraphQL/SSE/Socket.IO, review integration theo protocol thực thay vì dùng STOMP assumptions.

## 25. Câu hỏi vận dụng và đáp án

**Tình huống 1 — Giữ annotation cũ.** Nhóm đổi STOMP client sang raw WebSocket JSON nhưng vẫn bật `@EnableWebSocketSecurity`. `simpDestMatchers` có tự kiểm JSON không?

**Đáp án:** Không. Raw handler không thuộc STOMP inbound pipeline. Phải triển khai per-message authorization ở handler/service hoặc security integration của protocol mới.

**Tình huống 2 — Không thấy CONNECTED.** Client chỉ dùng `new WebSocket`, không nhận STOMP `CONNECTED`. Đây có chắc là lỗi không?

**Đáp án:** Không. Native WebSocket không có STOMP CONNECT/CONNECTED. Phải xem custom protocol và state machine nếu có.

**Tình huống 3 — HTTP 101.** Alice nhận HTTP 101, vậy có được đọc order Bob không?

**Đáp án:** Không. HTTP handshake chỉ mở transport theo điều kiện HTTP/Origin. Object ACL phải kiểm mỗi request.

**Tình huống 4 — CSRF HTTP.** WebFlux `ServerHttpSecurity` vẫn bật CSRF. JSON frame `orders.cancel` có tự bị HTTP CSRF kiểm không?

**Đáp án:** Không. Nó không phải HTTP POST mới. Cần Origin/CSWSH strategy và per-message authorization.

**Tình huống 5 — CORS.** REST CORS chặt nhưng WebSocket cho Origin lạ. Có đủ chống CSWSH chưa?

**Đáp án:** Chưa. Cần WebSocket Origin validation và authentication/ACL server-side.

**Tình huống 6 — Browser Authorization.** Frontend đặt `headers:{Authorization:"Bearer ..."}` trong `new WebSocket`. Có giống Fetch không?

**Đáp án:** Không. Browser WebSocket constructor không hỗ trợ arbitrary HTTP headers; chọn session handshake hoặc token-first protocol được bảo vệ.

**Tình huống 7 — Race auth.** Client gửi auth token rồi orders.lookup ngay trước khi verifier hoàn thành. Server được xử lý lookup không?

**Đáp án:** Không. `PENDING_AUTH` phải khóa business messages đến khi verified principal được thiết lập nguyên tử.

**Tình huống 8 — Payload khai role.** Client gửi `{"role":"ADMIN"}`. Có được dùng đó làm authority?

**Đáp án:** Không. Server lấy role từ verified token hoặc dữ liệu tin cậy; không tin client fields.

**Tình huống 9 — JWT hết hạn.** Socket đã auth từ 2 giờ trước và JWT đã expired. Framework có tự đóng raw socket không?

**Đáp án:** Không mặc định. Cần TTL/revalidation/revocation policy.

**Tình huống 10 — Reactor context.** Nested `subscribe()` làm context không còn. Sửa thế nào?

**Đáp án:** Compose Mono/Flux, tránh unmanaged subscriptions; truyền Principal trực tiếp và kiểm Reactor Context khi cần.

**Tình huống 11 — Blocking DB.** WebFlux handler gọi JPA blocking trực tiếp. Tác hại?

**Đáp án:** Có thể nghẽn event loop, tăng latency, cạn tài nguyên. Dùng reactive I/O hoặc giới hạn scheduler cho blocking calls.

**Tình huống 12 — Order subscribe.** Alice đã login nhưng muốn subscribe order của Bob. Có được không?

**Đáp án:** Không nếu thiếu object/tenant permission. Phải kiểm quyền subscribe và trước phát dữ liệu nhạy cảm.

**Tình huống 13 — Outbound public.** App chặn unauthorized inbound nhưng publisher phát private order vào public topic. An toàn chưa?

**Đáp án:** Chưa. Outbound routing/ACL là lớp riêng, phải chặn data leak trước publish.

**Tình huống 14 — RSocket.** App dùng RSocket over WebSocket, copy `CsrfChannelInterceptor` của STOMP. Có bảo vệ tự động không?

**Đáp án:** Không. RSocket có setup/metadata/route security riêng; phải tích hợp và kiểm thử theo RSocket.

**Tình huống 15 — GraphQL.** GraphQL `connection_init` hợp lệ, có được subscribe tất cả tenant không?

**Đáp án:** Không. Mỗi operation/field/data source còn cần authorization.

**Tình huống 16 — Socket.IO.** Socket.IO client không tương thích raw WebSocket handler. Đây chắc chắn lỗi auth?

**Đáp án:** Không. Protocol wire format có thể khác; trước hết phải dùng đúng client/server implementation.

**Tình huống 17 — SSE.** App chỉ muốn push trạng thái. SSE có là kênh hai chiều thay thế SEND không?

**Đáp án:** Không. SSE server→client; business commands vẫn qua HTTP API hoặc kênh khác.

**Tình huống 18 — Logout.** Alice logout ở tab A, socket tab B còn nhận data. Vì sao?

**Đáp án:** Thiếu session/connection revocation hoặc revalidation; không đủ chỉ xác thực lúc handshake.

**Tình huống 19 — Proxy.** Không có HTTP 101. Có nên sửa JSON message ACL trước?

**Đáp án:** Không. Kiểm HTTP auth, Origin, Upgrade, proxy và TLS trước.

**Tình huống 20 — Test 401.** Unauthenticated client bị chặn nhưng chưa test Origin evil có cookie hợp lệ. Đã chứng minh Origin guard chưa?

**Đáp án:** Chưa. Cần tách authentication khỏi Origin bằng test với session hợp lệ.

**Tình huống 21 — ERROR nhưng side effect.** Server trả lỗi sau khi đã hủy order Bob. Test pass không?

**Đáp án:** Không. Phải chứng minh không data leak và không có side effect trái quyền.

**Tình huống 22 — WebTestClient.** Toàn bộ HTTP tests pass. Có chứng minh native WS messages an toàn chưa?

**Đáp án:** Chưa. Cần real WebSocket E2E, browser tests và service ACL tests.

---

**Ghi nhớ:** **WebSocket thuần và WebFlux native WebSocket không tự kế thừa cơ chế Spring Security Messaging dành riêng cho STOMP.** `@EnableWebSocketSecurity`, `CsrfChannelInterceptor` và `simpDestMatchers` chỉ có ý nghĩa ở pipeline STOMP tương ứng, không tự kiểm raw text/binary frames. Phải tách **HTTP handshake authentication/Origin** khỏi **protocol-level authentication**, **per-message action/object authorization**, **outbound isolation** và **session/revocation lifecycle**. Reactive code còn cần nonblocking I/O, Reactor context đúng, backpressure/quotas và cancellation. Khi chuyển sang RSocket, GraphQL WebSocket, Socket.IO hoặc SSE, chọn bảo vệ theo protocol thật. Một hệ thống chỉ an toàn khi negative tests chứng minh người dùng hợp lệ **không thể gửi lệnh hoặc nhận dữ liệu vượt quyền**, kể cả sau khi socket đã mở thành công.
