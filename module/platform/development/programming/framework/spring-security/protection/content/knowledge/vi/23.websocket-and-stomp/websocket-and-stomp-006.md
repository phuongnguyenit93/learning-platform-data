# CSRF token trong STOMP CONNECT

## 1. Vấn đề: WebSocket đã mở không có nghĩa STOMP CONNECT an toàn

Giả sử Alice đăng nhập tại `https://app.example.com`. API ở `https://api.example.com` duy trì phiên qua session cookie; giao diện mở kết nối realtime tới `wss://api.example.com/ws` để nhận thông báo giao dịch. Trong nhiều ứng dụng Spring, principal Alice được kế thừa từ HTTP handshake vào WebSocket session.

Một website không tin cậy có thể thử chạy:

~~~javascript
const socket = new WebSocket("wss://api.example.com/ws");
~~~

Trình duyệt **không thực hiện Fetch CORS preflight OPTIONS** trước native WebSocket như đối với một HTTP `PUT`. Nếu browser tự gửi cookie phiên của Alice và server chấp nhận handshake từ trang lạ, script của trang đó có cơ hội giao tiếp hai chiều với backend. Trong hệ thống dùng STOMP, attacker còn phải đi qua frame `CONNECT` rồi mới `SEND`/`SUBSCRIBE`. Đây là một bề mặt của **Cross-Site WebSocket Hijacking (CSWSH)**.

Spring Security WebSocket Messaging bảo vệ phần kết nối STOMP bằng cách yêu cầu **CSRF token hợp lệ trong inbound STOMP `CONNECT`** khi dùng tích hợp security phù hợp. Token chứng minh client có thể lấy một giá trị gắn với ngữ cảnh tin cậy/phiên từ ứng dụng, thay vì chỉ trông cậy vào việc browser tự đính cookie. Đó là cơ chế bổ sung cho kiểm tra Origin, không phải thay thế authentication hay message authorization.

**Thông điệp cốt lõi của bài:**

- HTTP `GET /ws` (handshake) và STOMP `CONNECT` là **hai sự kiện ở hai lớp giao thức**.
- CSRF token của STOMP `CONNECT` được truyền trong **native STOMP header bên trong WebSocket/SockJS message**, không phải header HTTP của GET Upgrade.
- HTTP `101 Switching Protocols` không chứng minh STOMP CONNECT được chấp nhận.
- Với `@EnableWebSocketSecurity` trong Spring Security Messaging hiện đại, cần cấp và gửi token CONNECT theo đúng security context; một `AuthorizationManager<Message<?>>` không thay nhiệm vụ kiểm tra CSRF.
- Sau CONNECT, `SEND` và `SUBSCRIBE` còn cần phân quyền destination, principal và đối tượng nghiệp vụ.
- Khi dùng SockJS XHR fallback, **HTTP CSRF của transport POST** là một vấn đề riêng với **CSRF trên STOMP CONNECT**.

Bài thuộc chương **WebSocket và STOMP** của mô-đun **SPRING_SECURITY_HTTP_PROTECTION**. Phạm vi học bao gồm các lớp bảo vệ HTTP và trình duyệt (CSRF, CORS, security headers, CSP, HSTS, HTTP firewall, session) và so sánh Servlet với Reactive. Bài ưu tiên ví dụ **Spring MVC/Servlet + Spring WebSocket Message Broker**, đồng thời giải thích WebFlux native WebSocket để tránh sao chép sai cấu hình giữa hai stack.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Mô tả chính xác đường đi từ HTTP handshake tới STOMP CONNECT và vai trò của token.
2. Giải thích mối liên hệ CSWSH, Origin, session cookie, SameSite và CONNECT CSRF.
3. Phân biệt `CsrfTokenRepository`, endpoint HTTP cấp token và `CsrfChannelInterceptor` của Spring Messaging.
4. Cấu hình `@EnableWebSocketSecurity` với các rule message authorization deny-by-default.
5. Lấy token theo đúng phiên qua HTTP, rồi gửi qua `connectHeaders` của `@stomp/stompjs`.
6. Xử lý reconnect, login/logout và token rotation mà không tái sử dụng token sai phiên.
7. Chẩn đoán lỗi HTTP 401/403, handshake 101 nhưng STOMP không CONNECTED, và lỗi SockJS fallback.
8. Kiểm thử CONNECT có token đúng/thiếu/sai/thuộc phiên khác và kiểm tra không có dữ liệu rò rỉ.
9. Hiểu cách thiết kế cơ chế tương đương trên **WebFlux native WebSocket** mà không giả định nó có STOMP security mặc định.

Các domain `example.com` và dữ liệu đơn hàng trong ví dụ chỉ dùng minh họa, không phải hệ thống thực.

## 2. Bốn tầng cần tách bạch

| Tầng | Thời điểm | Dữ liệu kiểm tra | Cơ chế chính |
| --- | --- | --- | --- |
| **HTTP handshake** | `GET /ws`, trước khi mở socket | Session cookie, HTTP credentials, URL | `SecurityFilterChain` / HTTP authentication |
| **WebSocket Origin** | Cùng lúc handshake | `Origin` của website khởi tạo script | `setAllowedOrigins` / `setAllowedOriginPatterns` hoặc handshake guard |
| **STOMP CONNECT** | Sau khi transport WebSocket/SockJS mở | STOMP native headers, principal, CSRF token | Spring Security Messaging; CSRF CONNECT và authorization |
| **STOMP SEND/SUBSCRIBE** | Nhiều lần sau CONNECT | Message type, destination, principal, payload, object ID | `AuthorizationManager<Message<?>>` và business ACL |

Khi backend dùng session cookie, browser có thể tự đính thông tin xác thực vào HTTP handshake. CSRF token trên CONNECT là một lớp phòng vệ giúp phân biệt một client hợp lệ có quyền truy cập token với một trang web lạ chỉ lợi dụng cookie.

**CSRF không xác định user là ai.** Danh tính đến từ authentication. **CSRF cũng không xác định user được xem order nào.** Điều đó thuộc authorization.

### 2.1. Luồng đầy đủ

~~~mermaid
sequenceDiagram
    participant UI as Frontend tin cậy
    participant HTTP as HTTP Security + WebSocket handshake
    participant CSRF as HTTP endpoint cấp CsrfToken
    participant MSG as STOMP inbound security
    participant SVC as Application service / broker
    UI->>CSRF: GET /api/csrf + cookie phiên
    CSRF->>CSRF: Xác thực HTTP; cung cấp token cho phiên
    CSRF-->>UI: {headerName, token} + Cache-Control no-store
    UI->>HTTP: GET /ws + Upgrade + Origin + cookie
    HTTP->>HTTP: Kiểm tra HTTP principal + Origin
    HTTP-->>UI: 101 Switching Protocols
    UI->>MSG: STOMP CONNECT + native X-CSRF-TOKEN
    MSG->>MSG: Kiểm tra token CONNECT và principal
    alt Token sai/thiếu
        MSG-->>UI: Từ chối CONNECT / ERROR / đóng
    else Token đúng
        MSG-->>UI: CONNECTED
        UI->>MSG: SEND /app/orders.lookup
        MSG->>MSG: Kiểm tra destination, role
        MSG->>SVC: Principal + orderId
        SVC->>SVC: Ownership/tenant authorization
        SVC-->>UI: MESSAGE chỉ cho user/subscription hợp lệ
    end
~~~

Thứ tự lấy token và mở WebSocket có thể thay đổi theo client, miễn token có thể dùng được tại thời điểm CONNECT và gắn đúng ngữ cảnh phiên. Sơ đồ mô tả luồng logic, không áp đặt HTTP status cho lỗi STOMP: sau HTTP 101, lỗi CONNECT được biểu diễn bằng frame/đóng kết nối chứ không phải một response HTTP 403 mới.

## 3. HTTP Upgrade và STOMP CONNECT khác nhau về wire format

### 3.1. HTTP WebSocket handshake

Một browser ở `https://app.example.com` mở `wss://api.example.com/ws` có thể gửi:

~~~http
GET /ws HTTP/1.1
Host: api.example.com
Connection: Upgrade
Upgrade: websocket
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13
Origin: https://app.example.com
Cookie: SESSION=<cookie-if-browser-allows>
~~~

Nếu được phép:

~~~http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: <server-generated-value>
~~~

Đây là ví dụ WebSocket qua HTTP/1.1; một số hạ tầng hỗ trợ WebSocket qua HTTP/2 theo cơ chế khác. Điểm bất biến là **HTTP handshake** có nhiệm vụ xác lập transport và xác thực/kiểm tra Origin theo policy server.

Browser WebSocket constructor không cho JavaScript đặt tùy ý một HTTP `X-CSRF-TOKEN` header như Fetch:

~~~javascript
// KHÔNG PHẢI WebSocket constructor chuẩn của browser.
new WebSocket("wss://api.example.com/ws", {
  headers: { "X-CSRF-TOKEN": "..." }
});
~~~

Giữ token trong **STOMP frame**, không tìm cách ép browser gửi arbitrary header ở HTTP Upgrade.

### 3.2. STOMP CONNECT là frame trên transport đã mở

Một frame kết nối STOMP điển hình:

~~~text
CONNECT
accept-version:1.2
host:api.example.com
X-CSRF-TOKEN:<valid-session-csrf-token>

^@
~~~

`^@` là ký hiệu minh họa cho byte NUL kết thúc frame STOMP. Đây là **native header** do thư viện STOMP gửi bên trong WebSocket message, không phải HTTP header. Browser không thực hiện CORS preflight cho nội dung frame.

Sau khi Spring Security chấp nhận CONNECT, STOMP server có thể gửi:

~~~text
CONNECTED
version:1.2

^@
~~~

Ngược lại, nếu token không hợp lệ, client có thể nhận frame `ERROR` hoặc connection bị đóng tùy cấu hình và cách xử lý lỗi. **HTTP 101 vẫn có thể đã thành công** trước khi CONNECT bị từ chối.

### 3.3. STOMP CONNECT ≠ HTTP CONNECT ≠ HTTP GET Upgrade

Ba từ gần giống nhưng khác nhiệm vụ:

| Tên | Loại giao thức | Khi xảy ra | Có mang CSRF STOMP native header? |
| --- | --- | --- | --- |
| HTTP GET Upgrade | HTTP/1.1 handshake WebSocket | Trước khi socket mở | Không phải nơi gửi token CONNECT chuẩn của browser |
| HTTP CONNECT | HTTP method dùng trong các mục đích khác (ví dụ tunnel) | Không phải STOMP CONNECT | Không |
| STOMP CONNECT | Một STOMP command/frame | **Sau khi** transport mở | **Có**, khi Spring Security yêu cầu |
| STOMP SEND | STOMP command/frame | Sau CONNECT | Phân quyền message/destination, không phải một HTTP POST |
| STOMP SUBSCRIBE | STOMP command/frame | Sau CONNECT | Phân quyền subscription, không phải một HTTP GET mới |

Một lệnh `curl -X OPTIONS` không kiểm thử STOMP CONNECT CSRF. Một test chỉ kiểm tra `GET /ws` trả 101 cũng chưa kiểm thử CONNECT CSRF.

## 4. Vì sao Spring Security yêu cầu CSRF ở STOMP CONNECT?

### 4.1. Threat model: cookie được browser tự quản lý

Alice đăng nhập API, browser có session cookie:

~~~http
Set-Cookie: SESSION=<opaque-id>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Một script từ origin khác có thể thử WebSocket handshake. Nếu cookie được gửi và server cho phép nguồn trang đó, script có thể tương tác với phiên Alice qua kênh realtime. **Cross-Site WebSocket Hijacking** xuất hiện khi backend coi việc có session cookie là đủ để mở đường đọc/ghi dữ liệu mà không có phòng vệ nguồn và message.

CSRF token CONNECT yêu cầu client có một giá trị được ứng dụng cấp trong ngữ cảnh xác thực thích hợp, thay vì chỉ dựa vào ambient cookie. Một trang khác origin không được CORS cho phép đọc endpoint cấp token sẽ không dễ lấy token đó bằng Fetch; nhưng điều này **không thay** kiểm soát Origin ở WebSocket handshake.

### 4.2. SameSite không phải đồng nghĩa same-origin

`https://app.example.com` và `https://api.example.com`:

- Khác **origin** (host khác).
- Thường cùng **site** (cùng scheme HTTPS và registrable domain).
- Có thể gửi cookie same-site theo policy browser.

Một subdomain do user quản lý, như `https://usercontent.example.com`, cũng có thể cùng site. Do đó `SameSite=Lax`/`Strict` không thể được dùng như một cách xác minh frontend cụ thể. Origin allowlist và CSRF CONNECT vẫn có giá trị.

`HttpOnly` ngăn JavaScript đọc cookie, **không** ngăn browser gửi cookie vào handshake nếu điều kiện gửi cookie đáp ứng. `Secure` và TLS/WSS bảo vệ đường truyền; chúng không thay message authorization.

### 4.3. Origin check và CSRF CONNECT bổ sung nhau

| Phòng vệ | Ngăn/giảm nguy cơ | Không thay thế |
| --- | --- | --- |
| `setAllowedOrigins("https://app.example.com")` | Website không tin cậy mở browser WebSocket | Authentication của non-browser client giả Origin |
| CSRF token trong CONNECT | Kẻ tấn công dùng ambient session cookie nhưng không có token hợp lệ | Role và ownership |
| HTTP authentication | Nhận diện user tại handshake (mô hình session) | Message destination ACL |
| STOMP message authorization | SEND/SUBSCRIBE trái type/destination/role | Object ID/tenant ACL nếu rule không xét tài nguyên |
| Business authorization | Truy cập dữ liệu không thuộc quyền | Việc kết nối từ Origin lạ nếu endpoint mở quá rộng |
| CSP `connect-src` | Frontend được kết nối tới những endpoints được chỉ định | Authorization của server |

Một client ngoài browser có thể giả Origin, nhưng vẫn cần identity và token phù hợp nếu backend yêu cầu. CSRF **không phải** cách chặn mọi non-browser clients; authentication/authorization mới xác định họ có quyền gì.

## 5. Spring Security Messaging kiểm tra CONNECT ở đâu?

Trong Spring Security WebSocket Messaging hiện đại, ví dụ với `@EnableWebSocketSecurity`, framework tích hợp những thành phần bảo vệ **client inbound channel** và yêu cầu token CSRF hợp lệ khi nhận **STOMP CONNECT**. Có thể gặp thành phần tên `CsrfChannelInterceptor` trong pipeline. Nó hoạt động **sau HTTP handshake** trên inbound messaging, không phải Servlet `CsrfFilter` xử lý một HTTP POST.

### 5.1. Nguồn token và nơi kiểm tra

Các vai trò:

- `CsrfTokenRepository` (HTTP/Servlet): chịu trách nhiệm lưu/cấp expected token theo cơ chế được cấu hình, ví dụ gắn session.
- `CsrfToken`: mô tả header name, parameter name và token được cung cấp cho client.
- `CsrfTokenRequestHandler`: có thể tham gia cách token được đưa vào request và cách token (đặc biệt masked/deferred token) được xử lý.
- HTTP controller `GET /api/csrf`: **do ứng dụng triển khai**, trả token cho JavaScript của frontend tin cậy.
- Client STOMP `connectHeaders`: chuyển token vào native STOMP CONNECT header.
- Spring Security Messaging CONNECT CSRF handling: kiểm tra token nhận trên inbound STOMP CONNECT với expected token/ngữ cảnh phù hợp.

**Không nhầm hai loại interceptor:** Servlet HTTP `CsrfFilter` bảo vệ HTTP state-changing requests; messaging CSRF áp dụng cho STOMP CONNECT. Việc ghi `X-CSRF-TOKEN` trong một HTTP GET khác **không tự chuyển** giá trị đó sang CONNECT.

### 5.2. @EnableWebSocketSecurity và phạm vi phiên bản

Với cấu hình `@EnableWebSocketSecurity`, không nên giả định có một option trực tiếp giống `http.csrf(csrf -> csrf.disable())` để vô hiệu hóa CONNECT CSRF bằng chính lambda HTTP. Một số cách cấu hình hoặc extension point khác nhau theo phiên bản Spring Security và mô hình legacy; phải đánh giá cẩn thận trước khi đổi mặc định vì đây là lớp chống CSWSH.

Nếu một ứng dụng không dùng Spring STOMP Messaging (chỉ WebFlux native WebSocket hoặc tự triển khai protocol khác), **không có STOMP CONNECT để framework kiểm tra** theo cơ chế trên. Khi đó phải thiết kế bảo vệ cookie-authenticated connection và từng message riêng.

## 6. Cấu hình Spring WebSocket/STOMP trên Servlet

### 6.1. Đăng ký STOMP endpoint và origin allowlist

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
class RealtimeStompConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
            .setAllowedOrigins("https://app.example.com");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.setUserDestinationPrefix("/user");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Giải thích:

1. `/ws` là endpoint HTTP handshake/WebSocket.
2. `setAllowedOrigins` chỉ cho trang tin cậy gửi handshake browser; origin frontend là `https://app.example.com`, không phải `wss://api.example.com/ws`.
3. `/app` định tuyến client SEND tới `@MessageMapping`.
4. `/topic`, `/queue` là broker destinations; client không nên tự phát thẳng vào những nơi cần server kiểm soát.
5. `/user` hỗ trợ user destinations; không tự bảo vệ object ownership.

Chưa có authentication, CSRF CONNECT hoặc message authorization chỉ nhờ đoạn đăng ký endpoint này.

### 6.2. HTTP SecurityFilterChain dùng session/form login

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ServletHttpSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/csrf").authenticated()
                .requestMatchers("/ws", "/ws/**").authenticated()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll())
            .formLogin(Customizer.withDefaults())
            // Không tắt CSRF HTTP mặc định.
            .build();
    }
}
~~~

Trong mô hình trên, Spring Security HTTP nhận session cookie hợp lệ trên `GET /ws`, rồi Spring WebSocket thường kế thừa principal đã xác thực vào WebSocket session/STOMP messages.

**Cần hiểu giới hạn:**

- `authenticated()` trên `/ws` yêu cầu credential được xác minh **ở HTTP handshake**. Nếu SPA chỉ gửi bearer token trong STOMP CONNECT, HTTP request chưa có token và sẽ bị chặn trước CONNECT; đó là mô hình xác thực khác phải thiết kế riêng.
- `http.cors(...)` dành cho HTTP REST/XHR. Native WebSocket handshake phải có origin policy độc lập.
- Ở ví dụ này form login, session management, user store và authentication entry point thực tế cần được hoàn thiện trong project.
- `GET /api/csrf` cần được CORS cho phép khi frontend khác origin với API. Phần CORS này **không** tự có nhờ `setAllowedOrigins` của `/ws`.
- Nếu bật SockJS và dùng HTTP POST fallback, có thể cần xử lý xung đột CSRF HTTP một cách hẹp; không mặc nhiên bỏ CSRF trên tất cả routes.

### 6.3. HTTP CORS chỉ cho API lấy token

Ví dụ cấu hình CORS của Spring MVC dành cho frontend chính thức (không phải CORS của native WebSocket):

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class CsrfEndpointCorsConfiguration implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/csrf")
            .allowedOrigins("https://app.example.com")
            .allowedMethods("GET")
            .allowedHeaders("Content-Type")
            .allowCredentials(true)
            .maxAge(600);
    }
}
~~~

Vì frontend `https://app.example.com` và API `https://api.example.com` khác origin, Fetch cần CORS response header phù hợp để JavaScript đọc token. Với `credentials: "include"`, browser yêu cầu ACAO là origin cụ thể và ACAC nếu response được chia sẻ có credentials; `Access-Control-Allow-Origin: *` không phù hợp.

Chính sách này chỉ dành cho HTTP `/api/csrf`, không tự quyết định quyền handshake ở `/ws`.

## 7. @EnableWebSocketSecurity và message authorization

Bật security cho client inbound STOMP messages bằng cấu hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.socket.EnableWebSocketSecurity;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;

@Configuration
@EnableWebSocketSecurity
class StompInboundSecurityConfiguration {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
        MessageMatcherDelegatingAuthorizationManager.Builder messages
    ) {
        return messages
            // CONNECT và các frame không có destination
            // vẫn cần authenticated principal.
            .nullDestMatcher().authenticated()

            // Không để client subscribe vào application destinations.
            .simpSubscribeDestMatchers("/app/**").denyAll()

            // Cho một subscription theo user.
            .simpSubscribeDestMatchers(
                "/user/queue/order-results"
            ).authenticated()

            // Chỉ cho client gửi lệnh này nếu có role USER.
            .simpDestMatchers("/app/orders.lookup").hasRole("USER")

            // Những MESSAGE/SUBSCRIBE còn lại đều bị chặn.
            .simpTypeMatchers(
                SimpMessageType.MESSAGE,
                SimpMessageType.SUBSCRIBE
            ).denyAll()

            .anyMessage().denyAll()
            .build();
    }
}
~~~

### 7.1. CONNECT CSRF không phải một rule simpDestMatchers

STOMP CONNECT thường không mang destination, nên matcher `simpDestMatchers("/app/**")` không kiểm tra nó. `nullDestMatcher().authenticated()` yêu cầu một principal cho các frame không có destination trong cấu hình này, nhưng **không thay thế** bước xác minh token CSRF.

Khi `@EnableWebSocketSecurity` kích hoạt pipeline bảo vệ CONNECT, một CONNECT thiếu/sai token có thể bị từ chối **ngay cả khi** principal đã được kế thừa từ HTTP handshake và matcher authenticated cho phép principal đó.

### 7.2. Quyền sau CONNECT vẫn phải được kiểm tra

Các lệnh:

~~~text
SEND
destination:/app/orders.lookup
content-type:application/json

{"orderId":2002}
^@
~~~

và:

~~~text
SUBSCRIBE
id:sub-7
destination:/topic/admin

^@
~~~

phải chịu message authorization riêng:

- `SEND /app/orders.lookup` chỉ cho user có role USER và còn phải kiểm tra order ID.
- `SUBSCRIBE /topic/admin` bị fallback deny trong policy trên.
- Client không được `SEND /topic/**` trực tiếp vào broker để giả mạo notification.
- Subscription vào private topic cần ACL theo principal/tenant, không chỉ authenticated.
- Khi quyền đổi giữa chừng, server cần revalidate hoặc thu hồi connection/subscriptions theo thiết kế.

## 8. Cấp CSRF token cho JavaScript bằng HTTP

### 8.1. Endpoint HTTP minh họa

Một controller Spring MVC có thể trả token hiện hành:

~~~java
import java.util.Map;

import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CsrfTokenEndpoint {

    @GetMapping("/api/csrf")
    ResponseEntity<Map<String, String>> getToken(
        @RequestAttribute("_csrf") CsrfToken csrf
    ) {
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(Map.of(
                "headerName", csrf.getHeaderName(),
                "token", csrf.getToken()
            ));
    }
}
~~~

**Lưu ý triển khai:**

- Endpoint `/api/csrf` do **ứng dụng tự định nghĩa**; Spring không tự cung cấp HTTP URL này cho mọi dự án.
- Cấu hình HTTP Security phải bảo vệ endpoint theo mô hình login/token của ứng dụng. Với ví dụ này, `authenticated()` yêu cầu session hợp lệ.
- Response chứa token không nên để proxy/CDN/shared cache lưu dùng chung; `Cache-Control: no-store` giúp giảm rủi ro đó.
- Không ghi token, cookie hoặc JSON đầy đủ vào access logs/monitoring công khai.
- Nếu frontend khác origin, cấu hình CORS ở mục 6.3 phải cho đúng origin tin cậy đọc response.
- Dùng `csrf.getHeaderName()` thay vì hardcode header vì tên có thể được custom.
- Nếu dùng custom `CsrfTokenRepository` hoặc `CsrfTokenRequestHandler`, nhất là token masked/deferred, phải bảo đảm giá trị trả về phù hợp cách Spring Messaging kiểm tra CONNECT; kiểm thử tích hợp bằng client STOMP thật.

### 8.2. Mẫu HTTP request/response

Frontend gửi:

~~~http
GET /api/csrf HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Cookie: SESSION=<alice-session>
~~~

Server trả dữ liệu minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin

{"headerName":"X-CSRF-TOKEN","token":"<session-csrf-token>"}
~~~

Đây là **HTTP JSON response**. JavaScript lấy token rồi tự chuyển sang **STOMP native CONNECT header**. Không trông chờ browser làm bước chuyển này tự động.

### 8.3. Vì sao không đưa token vào URL/query?

Ví dụ không nên dùng:

~~~javascript
// Tránh: token nhạy cảm nằm trên URL có thể bị ghi log.
const url = "wss://api.example.com/ws?csrf=" + csrfToken;
const socket = new WebSocket(url);
~~~

URLs dễ bị lưu ở reverse proxy access logs, tracing, diagnostics và hệ thống giám sát. STOMP native header không đảm bảo “vô hình” với mọi log, nhưng tránh tạo URL chứa token ngay từ đầu. Cần redaction nhạy cảm cho cả STOMP frames khi bật debug logging.

### 8.4. Lấy token trước hay sau khi mở socket?

Không có yêu cầu rằng HTTP `GET /api/csrf` phải luôn chạy **trước** handshake. Điều bắt buộc là **trước khi STOMP CONNECT được kiểm tra**, client đã có token hợp lệ theo cơ chế Spring.

Cách dễ hiểu:

1. Login HTTP → cookie phiên được tạo.
2. Fetch `/api/csrf` với cookie.
3. Tạo WebSocket/SockJS transport.
4. Gửi STOMP CONNECT kèm token.
5. Chỉ khi CONNECTED, cho phép SEND/SUBSCRIBE.

Cách này giúp giảm số lần mở socket rồi nhận lỗi vì thiếu token và dễ chẩn đoán khi session chưa hợp lệ.

## 9. Frontend @stomp/stompjs: cách gửi token đúng

### 9.1. Client kết nối lần đầu

~~~javascript
import { Client } from "@stomp/stompjs";

async function startRealtime() {
  const response = await fetch(
    "https://api.example.com/api/csrf",
    { credentials: "include" }
  );

  if (!response.ok) {
    throw new Error("Không lấy được CSRF token");
  }

  const { headerName, token } = await response.json();

  const client = new Client({
    brokerURL: "wss://api.example.com/ws",

    // Đây là NATIVE HEADER của STOMP CONNECT.
    connectHeaders: {
      [headerName]: token
    },

    reconnectDelay: 3000,

    onConnect: () => {
      client.subscribe(
        "/user/queue/order-results",
        message => {
          const result = JSON.parse(message.body);
          console.log("Kết quả đơn hàng:", result);
        }
      );

      client.publish({
        destination: "/app/orders.lookup",
        body: JSON.stringify({ orderId: 1001 })
      });
    },

    onStompError: frame => {
      console.error("STOMP CONNECT/message error:",
        frame.headers.message);
    },

    onWebSocketClose: () => {
      console.log("WebSocket đã đóng");
    }
  });

  client.activate();
  return client;
}
~~~

**Quan trọng:** `connectHeaders` không thêm một HTTP request header tùy ý vào `GET /ws`. Nó đưa token vào STOMP CONNECT sau khi `new WebSocket` đã mở transport.

Nếu client `fetch` dùng `credentials: "include"` nhưng browser không gửi cookie vì `SameSite`/third-party policy, có thể nhận 401/redirect ở `/api/csrf`; không nên chuyển sang bỏ authentication chỉ để lấy token.

### 9.2. Không nhầm with SockJS

Khi bật SockJS ở Spring:

~~~java
registry.addEndpoint("/ws")
    .setAllowedOrigins("https://app.example.com")
    .withSockJS();
~~~

frontend dùng URL **HTTP(S)** của SockJS:

~~~javascript
import SockJS from "sockjs-client";
import { Client } from "@stomp/stompjs";

function createStompClient(csrfHeaderName, csrfToken) {
  return new Client({
    webSocketFactory: () =>
      new SockJS("https://api.example.com/ws"),
    connectHeaders: {
      [csrfHeaderName]: csrfToken
    }
  });
}
~~~

SockJS tự chọn WebSocket hoặc HTTP/XHR fallback transport. Dù transport là gì, STOMP CONNECT cần native header đúng theo policy Spring Messaging. HTTP POST fallback có thể cần xử lý **HTTP CSRF riêng** — không phải truyền token STOMP vào cùng chỗ với header HTTP.

### 9.3. Reconnect và token có thể đổi

Một ví dụ tạo client rồi tự reconnect sau 3 giây với **token cũ** có thể thất bại khi:

- Session hết hạn hoặc được tái tạo.
- User logout rồi login lại.
- `CsrfTokenRepository` thay đổi token.
- Security config đổi token handler/repository.
- Browser thay đổi cookie policy.
- Backend thu hồi phiên hoặc reconnect qua node khác với session store khác.

Với thư viện STOMP có hook `beforeConnect`, có thể làm mới token mỗi lần CONNECT:

~~~javascript
import { Client } from "@stomp/stompjs";

const client = new Client({
  brokerURL: "wss://api.example.com/ws",
  reconnectDelay: 3000
});

client.beforeConnect = async () => {
  const response = await fetch(
    "https://api.example.com/api/csrf",
    { credentials: "include" }
  );

  if (!response.ok) {
    throw new Error("Phiên hoặc CSRF token không hợp lệ");
  }

  const { headerName, token } = await response.json();

  // STOMP sẽ sử dụng headers mới cho lần CONNECT tiếp theo.
  client.connectHeaders = {
    [headerName]: token
  };
};

client.onConnect = () => {
  client.subscribe("/user/queue/order-results", frame => {
    console.log(frame.body);
  });
};

client.activate();
~~~

Hook/khả năng xử lý async cần được xác minh theo **phiên bản @stomp/stompjs** dự án dùng. Trên production còn cần backoff, ngăn reconnect vô hạn khi logout, refresh auth đúng cách, lifecycle cleanup và xử lý lỗi lấy token.

### 9.4. Logout nên ngắt kết nối có chủ đích

Khi user chủ động logout:

1. Gọi `client.deactivate()` để ngắt kết nối theo API thư viện.
2. Gọi HTTP logout theo chính sách ứng dụng để invalidate/revoke session.
3. Xóa state/identity phía frontend.
4. Không tái sử dụng token hoặc subscription state của user cũ.
5. Nếu application server cần thu hồi socket của cùng session ở những tab khác, phải có cơ chế đóng/revalidate phía server.

**Đóng socket ở frontend không đủ** để đảm bảo một session khác vẫn tồn tại ở tab khác không được tiếp tục truy cập khi quyền đã bị thu hồi.

## 10. CONNECT sai token: điều gì xảy ra?

### 10.1. Những kịch bản quan trọng

| Trường hợp | HTTP handshake | STOMP CONNECT | Kỳ vọng |
| --- | --- | --- | --- |
| Session hợp lệ, Origin hợp lệ, token hợp lệ | Có thể HTTP 101 | Token đúng phiên | CONNECTED |
| Session hợp lệ, Origin hợp lệ, **thiếu token** | HTTP 101 vẫn có thể xảy ra | Không có CSRF header | CONNECT bị từ chối |
| Session hợp lệ, token sai | HTTP 101 | Header có token không khớp | CONNECT bị từ chối |
| Session Alice, token của session Bob | HTTP 101 với Alice | Token không thuộc Alice | CONNECT bị từ chối trong cơ chế token gắn session phù hợp |
| Cookie session hết hạn | Bị HTTP auth từ chối nếu `/ws` đòi login | Không tới CONNECT | Không được sử dụng socket |
| Origin lạ, session hợp lệ | Handshake bị Origin policy chặn | Không tới CONNECT | Không mở connection |
| HTTP handshake anonymous được phép (theo kiến trúc khác) | Transport có thể mở | Phải có auth/CSRF strategy riêng | Không nhận message riêng trước xác thực |
| STOMP token hợp lệ nhưng role thiếu | Có thể CONNECTED | SEND/SUBSCRIBE bị ACL chặn | Không truy cập nội dung trái quyền |

Một request bị chặn ở HTTP handshake **không chứng minh** CONNECT CSRF hoạt động. Cần test riêng mỗi tầng.

### 10.2. Header name/case và masked token

Thông thường token được gửi qua tên header như `X-CSRF-TOKEN`, nhưng ứng dụng có thể đổi `CsrfTokenRepository`, token handler hoặc cách trình bày token. Để giảm sai sót:

- API trả đồng thời `headerName` và `token`.
- Client dùng đúng `headerName` trong `connectHeaders`.
- Token được lấy từ **đúng phiên**.
- Không trim/encode/escape token một cách tự ý gây thay đổi giá trị.
- Không so sánh token từ hai sessions như thể chúng phải giống nhau.
- Nếu Spring Security dùng token masked/deferred hoặc thay handler, chạy integration test thực tế thay vì suy ra từ một unit test `CsrfTokenRepository`.

Khi chẩn đoán, ghi nhận “CSRF mismatch” mà **không ghi token thô** trong log.

### 10.3. Browser nhận thông báo lỗi gì?

Sau HTTP 101, có thể quan sát:

- Frame `ERROR` với thông điệp từ STOMP server.
- Callback `onStompError` được gọi, tùy client.
- WebSocket đóng và `onWebSocketClose` chạy.
- Không bao giờ nhận `CONNECTED`.
- Client tự reconnect rồi lặp lỗi khi dùng token cũ.

Không khẳng định Spring luôn trả đúng cùng một status/code/reason cho mọi phiên bản hay interceptor order. Assertion quan trọng là **CONNECT bị từ chối và không có SEND/SUBSCRIBE/dữ liệu riêng tư được xử lý**.

## 11. Không nhầm HTTP CSRF với STOMP CONNECT CSRF

### 11.1. HTTP CSRF trong Spring Security

Với một HTTP form POST/PUT dùng session cookie, Spring Security Servlet `CsrfFilter` có thể yêu cầu token theo `CsrfTokenRepository` và request handler. Một HTTP request thay đổi trạng thái có thể mang `X-CSRF-TOKEN` trong **HTTP header**.

Đối với **native WebSocket**, STOMP SEND không phải HTTP POST mới; nó là frame trong connection. Vì vậy HTTP `CsrfFilter` không tự chạy lại cho từng STOMP frame.

### 11.2. CONNECT CSRF ở Messaging

STOMP CONNECT có thể chứa:

~~~text
CONNECT
X-CSRF-TOKEN:<valid-token>

^@
~~~

Header này được xử lý ở **Spring Messaging inbound**, không bởi HTTP `CsrfFilter` như thể frame là một POST. Với Spring Security Messaging hiện đại, CONNECT CSRF là lớp phòng vệ trọng yếu cho kênh mang phiên browser.

Một `.csrf(csrf -> csrf.disable())` ở `HttpSecurity` ảnh hưởng HTTP CSRF, **không phải thao tác đúng để giải quyết kiểm tra token CONNECT**. Ngoài ra, tắt CSRF HTTP bừa bãi có thể tạo lỗ hổng trên REST/form endpoints.

### 11.3. CORS của endpoint cấp token là lớp khác

`GET /api/csrf` từ `https://app.example.com` đến `https://api.example.com` là một **HTTP Fetch cross-origin**. Browser kiểm tra CORS headers của HTTP response trước khi cho JavaScript đọc token.

`new WebSocket("wss://api.example.com/ws")` không có Fetch CORS preflight/ACAO tương tự; server bảo vệ handshake bằng kiểm tra Origin. Khi mở transport rồi gửi STOMP CONNECT, token được kiểm tra riêng.

Nên vẽ ba câu hỏi:

~~~text
GET /api/csrf:
  HTTP Authentication + HTTP CORS + cấp CsrfToken cho app được phép?

GET /ws:
  HTTP Authentication + WebSocket Origin validation + TLS?

STOMP CONNECT:
  Principal hợp lệ + native CSRF token đúng + message security?
~~~

Chỉ khi cả ba đáp ứng mới có cơ sở để bắt đầu hoạt động realtime an toàn.

## 12. SockJS fallback: HTTP POST transport có thể gây xung đột CSRF

Nếu dùng `.withSockJS()`, client không luôn dùng native WebSocket. Trong vài môi trường, SockJS dùng XHR streaming/polling:

~~~text
GET  /ws/info
GET  /ws/<server-id>/<session-id>/xhr_streaming
POST /ws/<server-id>/<session-id>/xhr_send
...
~~~

Một số transports có HTTP POST và có thể bị Spring Security HTTP CSRF filter chặn nếu request transport không mang token HTTP như một form submission. Vì vậy có thể gặp:

~~~text
Native WebSocket: HTTP 101, STOMP CONNECTED.
SockJS XHR: HTTP POST /ws/.../xhr_send trả 403 trước CONNECT.
~~~

### 12.1. Phân biệt nguyên nhân

HTTP 403 trên XHR POST **không nhất thiết** là CONNECT CSRF mismatch. Nếu HTTP transport bị từ chối, STOMP CONNECT chưa tới messaging pipeline hoặc chưa hoàn tất.

Trong DevTools hãy kiểm tra:

- Transport SockJS thực tế đang được chọn.
- HTTP method và URL `/ws/...`.
- CORS preflight OPTIONS nếu có.
- HTTP response status và body của transport.
- Header Origin và cookie.
- HTTP CSRF matcher trong SecurityFilterChain.
- Có STOMP `CONNECT` frame/`CONNECTED` hoặc `ERROR` sau khi transport mở không.

### 12.2. Nếu phải loại trừ CSRF HTTP cho SockJS transport

Khi framework/transport yêu cầu, có thể cấu hình **ngoại lệ HTTP CSRF hẹp** cho các SockJS POST transport paths được kiểm chứng. Nhưng:

- Không tắt toàn bộ `http.csrf` cho ứng dụng.
- Không bỏ CSRF cho các REST POST/PUT nghiệp vụ.
- Không coi mọi `/ws/**` là an toàn nếu cùng namespace đó chứa HTTP endpoints nghiệp vụ.
- Không loại bỏ CONNECT CSRF ở messaging.
- Test toàn bộ paths thật của SockJS transport, kể cả reverse-proxy rewrite.
- Nếu có thể chỉ dùng native WebSocket cho những browser mục tiêu, cân nhắc tránh fallback không cần thiết.

Một matcher ví dụ dạng **chính sách khái niệm**, không dùng nguyên văn trước khi xác minh transport routes:

~~~text
HTTP CSRF exception:
  chỉ POST tới những SockJS transport URLs được framework tạo
  và được nhận diện bằng request matcher chặt.

HTTP CSRF vẫn bắt buộc:
  POST/PUT/PATCH/DELETE của REST API hoặc business endpoints.

STOMP CONNECT CSRF:
  vẫn xác minh native header trong inbound STOMP CONNECT.
~~~

### 12.3. Framing headers, CORS và iframe transports

Một số SockJS iframe-based transports cũ có thể bị `X-Frame-Options` hoặc CSP `frame-ancestors` hạn chế. XHR fallback chịu CORS; native WebSocket lại chịu Origin handshake policy riêng. Không nới lỏng toàn bộ security headers hay mở Origin wildcard để sửa một transport cũ nếu nó không thực sự cần cho sản phẩm.

## 13. Authentication bằng bearer token tại CONNECT: không đánh đồng với CSRF

Một SPA có thể chỉ giữ access token trong JavaScript mà không có session cookie. Browser không cho đặt arbitrary HTTP `Authorization` header qua WebSocket constructor, nên một kiến trúc khác là gửi bearer token trong native STOMP `CONNECT`:

~~~text
CONNECT
accept-version:1.2
Authorization:Bearer <access-token>

^@
~~~

**Header STOMP tự khai không tự xác thực.** Application cần `ChannelInterceptor` xác minh token và gắn `Authentication` vào message/session theo cơ chế chính thức.

### 13.1. Hai mô hình cần chọn nhất quán

| Mô hình | Principal từ đâu? | Chính sách HTTP handshake | CONNECT |
| --- | --- | --- | --- |
| **Session-based / HTTP inheritance** | Authenticated HTTP `GET /ws`, WebSocket session kế thừa | `/ws` yêu cầu authenticated | Token CSRF gắn với session và message security |
| **Bearer trong STOMP CONNECT** | Token verifier trong messaging inbound interceptor | Có thể phải cho một phạm vi handshake hẹp đi qua trước khi biết principal | Bắt buộc xác thực token trước SEND/SUBSCRIBE; CSRF strategy cần đánh giá theo phiên bản/framework/threat model |
| **Non-browser client đã authenticated ở HTTP** | HTTP credentials/mTLS/token được xác minh ở handshake | Yêu cầu HTTP auth | Messaging policy tùy mô hình; không mặc nhiên bỏ CONNECT security |

Nếu HTTP `/ws` bắt buộc authenticated nhưng token chỉ đến trong STOMP CONNECT, handshake sẽ bị từ chối **trước khi token được gửi**. Không phải lỗi của Spring; đó là thiết kế chưa nhất quán.

### 13.2. Interceptor xác thực CONNECT phải chạy đúng thứ tự

Một custom `ChannelInterceptor` có thể:

1. Chỉ bắt `StompCommand.CONNECT`.
2. Đọc native `Authorization` header.
3. Kiểm tra signature/issuer/audience/expiry/revocation/scopes của bearer token.
4. Tạo `Authentication` đã được xác minh.
5. Gọi `StompHeaderAccessor#setUser(authentication)`.
6. Được đăng ký **trước** Spring Security authorization interceptors.
7. Từ chối token thiếu/sai.
8. Xử lý hết hạn/thu hồi token khi connection dài hạn.

Ví dụ skeleton:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageHeaderAccessor;
import org.springframework.security.core.Authentication;

interface StompBearerVerifier {
    Authentication verify(String authorization);
}

class ConnectAuthenticationInterceptor implements ChannelInterceptor {

    private final StompBearerVerifier verifier;

    ConnectAuthenticationInterceptor(StompBearerVerifier verifier) {
        this.verifier = verifier;
    }

    @Override
    public Message<?> preSend(Message<?> message, MessageChannel channel) {
        StompHeaderAccessor accessor =
            MessageHeaderAccessor.getAccessor(
                message, StompHeaderAccessor.class
            );

        if (accessor != null
                && StompCommand.CONNECT.equals(accessor.getCommand())) {
            String raw =
                accessor.getFirstNativeHeader("Authorization");

            Authentication principal = verifier.verify(raw);
            accessor.setUser(principal);
        }

        return message;
    }
}
~~~

Đây là **skeleton**, chưa có `StompBearerVerifier` thực, cách đăng ký, thứ tự interceptors, error handling hoặc reconnect/revocation. Quan trọng nhất: **bearer CONNECT không tự tắt CSRF CONNECT mặc định của `@EnableWebSocketSecurity`**. Nếu chọn mô hình stateless-token chỉ cho non-browser hoặc SPA, cần xác định policy phù hợp theo Spring Security version, không nới bảo mật ngầm định.

### 13.3. CSRF threat model thay đổi nhưng không tự biến mất

Nếu server **không sử dụng ambient browser credentials**, và mọi CONNECT đều bắt buộc một bearer token mà website lạ không thể lấy, nguy cơ CSWSH khác với session-cookie model. Tuy nhiên:

- Origin validation vẫn hữu ích để giới hạn browser website được phép.
- XSS trong frontend chính thức vẫn có thể dùng token trong JavaScript.
- Token phải được xác minh và bảo vệ khỏi logs/leaks.
- Với `@EnableWebSocketSecurity`, yêu cầu CSRF CONNECT có thể vẫn đang bật; không thể chỉ giả định “dùng JWT thì không cần gửi CSRF header”.
- Thay đổi/chấm dứt kiểm tra CSRF cần có đánh giá bảo mật và cách cấu hình được framework hỗ trợ rõ ràng.

## 14. Phân quyền SEND/SUBSCRIBE và object ownership sau CONNECT

### 14.1. Ví dụ handler sử dụng principal

Khi STOMP CONNECTED, Alice gửi:

~~~text
SEND
destination:/app/orders.lookup
content-type:application/json

{"orderId":2002}
^@
~~~

Server dùng `Principal` đã được xác thực, không tin trường `userId` trong payload:

~~~java
import java.security.Principal;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Controller;

record OrderLookup(long orderId) {}
record OrderResult(long orderId, String status) {}

interface OrderService {
    // Kiểm tra principal có quyền đối với orderId/tenant.
    OrderResult findVisible(String username, long orderId);
}

@Controller
class OrderRealtimeController {

    private final OrderService orders;
    private final SimpMessagingTemplate messaging;

    OrderRealtimeController(
        OrderService orders,
        SimpMessagingTemplate messaging
    ) {
        this.orders = orders;
        this.messaging = messaging;
    }

    @MessageMapping("/orders.lookup")
    void lookup(@Payload OrderLookup input, Principal principal) {
        OrderResult order = orders.findVisible(
            principal.getName(), input.orderId()
        );

        messaging.convertAndSendToUser(
            principal.getName(),
            "/queue/order-results",
            order
        );
    }
}
~~~

`OrderService` là giao diện minh họa; implementation phải kiểm tra ownership/tenant/role thật. Dù CONNECT có CSRF token đúng, Alice không được đọc order của Bob. **CSRF ≠ authorization.**

### 14.2. SUBSCRIBE cũng là bề mặt nhạy cảm

Nếu Alice được `SUBSCRIBE /topic/orders/2002` chỉ vì authenticated, cô có thể nhận dữ liệu Bob. Quyền phải được kiểm tra khi subscription tạo và/hoặc trước khi server phát dữ liệu, tùy kiến trúc.

Không dùng rule rộng:

~~~java
// Rủi ro nếu mỗi topic là dữ liệu riêng tư:
messages.simpSubscribeDestMatchers("/topic/orders/**")
    .authenticated();
~~~

Ưu tiên user destinations hoặc custom AuthorizationManager cho topic theo object/tenant. **Spring Security Messaging bảo vệ inbound**, không tự bảo đảm mọi outbound message chỉ đến đúng người nếu server routing sai.

## 15. WebFlux native WebSocket: không có STOMP CONNECT mặc định

Đây là chỗ dễ sao chép cấu hình sai giữa Servlet và Reactive.

Spring WebFlux có `WebSocketHandler`/`WebSocketSession` để xử lý text/binary frames. Một ứng dụng dùng native WebFlux WebSocket **không tự có** STOMP broker, `@EnableWebSocketMessageBroker` hoặc CONNECT CSRF interceptor của Spring Security Messaging Servlet.

Nếu hệ thống WebFlux native dùng session cookie, cần tự thiết kế bảo vệ tương đương theo threat model:

- Authentication tại HTTP handshake bằng `ServerHttpSecurity`.
- Origin validation chặt.
- Khi cần, token hoặc ràng buộc phiên ở handshake/first application message theo protocol đã chọn.
- Per-message authorization và ownership checks.
- Connection/session revocation và rate limits.

### 15.1. ServerHttpSecurity bảo vệ handshake

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ReactiveHandshakeConfiguration {

    @Bean
    SecurityWebFilterChain webSocketHttpSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/ws").authenticated()
                .anyExchange().denyAll())
            .build();
    }
}
~~~

Code này chỉ yêu cầu principal ở HTTP handshake; nó **không tự kiểm tra Origin hoặc từng WebSocket frame**.

### 15.2. Một Origin guard ở WebFlux

~~~java
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.WebFilter;

@Configuration
class ReactiveWebSocketOriginConfiguration {

    private static final Set<String> ALLOWED =
        Set.of("https://app.example.com");

    @Bean
    @Order(Ordered.HIGHEST_PRECEDENCE)
    WebFilter originGuard() {
        return (exchange, chain) -> {
            if (!"/ws".equals(
                    exchange.getRequest().getPath().value())) {
                return chain.filter(exchange);
            }

            String origin = exchange.getRequest()
                .getHeaders().getOrigin();

            if (origin == null || !ALLOWED.contains(origin)) {
                exchange.getResponse()
                    .setStatusCode(HttpStatus.FORBIDDEN);
                return exchange.getResponse().setComplete();
            }

            return chain.filter(exchange);
        };
    }
}
~~~

Guard này minh họa policy **chỉ phục vụ browser** nên cố ý từ chối Origin vắng mặt. Với non-browser clients hợp lệ, thiết kế riêng authentication và Origin policy, không chỉ bỏ kiểm tra. Ứng dụng thật cần xét proxy path rewrite, request upgrade detection và thứ tự filters.

### 15.3. Handler kiểm tra từng message

~~~java
import java.security.Principal;

import reactor.core.publisher.Mono;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.reactive.socket.WebSocketHandler;

interface RealtimeCommandService {
    // Kiểm tra loại lệnh, payload, principal, object/tenant ACL.
    Mono<Void> validateAuthorizeAndHandle(
        Principal principal, String payload
    );
}

class SecureReactiveSocketHandler {

    static WebSocketHandler create(RealtimeCommandService commands) {
        return session -> session.getHandshakeInfo()
            .getPrincipal()
            .switchIfEmpty(Mono.error(
                new AccessDeniedException("Unauthenticated")))
            .flatMap(principal ->
                session.receive()
                    .concatMap(frame ->
                        commands.validateAuthorizeAndHandle(
                            principal, frame.getPayloadAsText()
                        ))
                    .then()
            );
    }
}
~~~

Ví dụ là skeleton chưa gồm handler mapping, sending/backpressure hoặc token-check cho first message. **Không gọi một JSON message là STOMP CONNECT** nếu application không hề dùng STOMP. Với WebFlux native, authorization per-message là việc của handler/service hoặc một security pipeline được triển khai riêng.

## 16. Ma trận kiểm thử CONNECT CSRF

Một bộ test nên tách ba điều kiện: **HTTP handshake/Origin**, **STOMP CONNECT token**, **message authorization**.

### 16.1. Handshake

| Mã | HTTP/WebSocket request | Kỳ vọng |
| --- | --- | --- |
| H1 | Origin app + session Alice hợp lệ | HTTP handshake được phép theo policy |
| H2 | Origin lạ + session Alice hợp lệ | Bị Origin policy từ chối |
| H3 | Origin app + không có session | HTTP authentication từ chối nếu `/ws` yêu cầu login |
| H4 | Origin app + session hết hạn | Không được xem là authenticated |
| H5 | Client ngoài browser giả Origin app, không auth | Không vượt qua HTTP authentication |

**Để chứng minh H2 là Origin check**, thử với session hợp lệ. Một 401 do thiếu cookie chưa xác nhận allowlist đã hoạt động.

### 16.2. STOMP CONNECT

| Mã | Principal từ HTTP | Native CSRF header | Kỳ vọng |
| --- | --- | --- | --- |
| C1 | Alice | Token đúng session, đúng header name | CONNECTED |
| C2 | Alice | Không có token | CONNECT bị từ chối |
| C3 | Alice | Token ngẫu nhiên/sai | CONNECT bị từ chối |
| C4 | Alice | Token lấy từ session khác (Bob) | Bị từ chối với repository gắn session đúng |
| C5 | Alice | Token cũ sau khi session được đổi/rotate | Bị từ chối khi expected token đã thay đổi |
| C6 | Alice | Token đúng nhưng không có quyền ở SEND sau đó | CONNECT có thể hợp lệ; SEND bị từ chối |
| C7 | Không có authenticated principal trong mô hình bắt buộc HTTP login | Token có vẻ đúng | Không coi token là authentication thay principal |
| C8 | Token gửi trên HTTP request khác nhưng không có trong STOMP CONNECT | Missing native header | CONNECT bị từ chối |
| C9 | Đúng token nhưng client khai `login:admin` | Native header tự khai | Không tự cấp role ADMIN |
| C10 | Reconnect sau logout/login mà dùng token phiên cũ | Token không thuộc phiên mới | Không CONNECTED nếu expected token khác |

### 16.3. Sau CONNECT

| Mã | Message | Kỳ vọng |
| --- | --- | --- |
| M1 | SEND `/app/orders.lookup` với order Alice | Được xử lý nếu principal có role và quyền |
| M2 | SEND thẳng `/topic/public` | Bị message authorization từ chối |
| M3 | SUBSCRIBE `/topic/admin` khi chỉ role USER | Bị từ chối |
| M4 | SEND lookup order Bob với Alice | Service từ chối, không phát dữ liệu Bob |
| M5 | Logout/role revocation nhưng socket cũ tồn tại | Không tiếp tục thực hiện/nhận dữ liệu trái quyền |

Nếu chỉ kiểm tra CONNECTED mà không có M2–M5, bài test chưa chứng minh các lớp phòng vệ của realtime application.

## 17. Chiến lược kiểm thử tích hợp thực tế

### 17.1. MockMvc kiểm tra endpoint cấp token

Trong Servlet, `MockMvc` có thể kiểm tra `GET /api/csrf` có authenticated access, trả JSON `headerName`/`token` và `Cache-Control` phù hợp. Nhưng **MockMvc không mô phỏng đầy đủ WebSocket Upgrade và STOMP CONNECT**.

Các assertions nên có:

~~~text
Given user alice đã authenticated qua HTTP:
  GET /api/csrf
Then:
  HTTP 200
  JSON có headerName và token không rỗng
  Cache-Control: no-store (hoặc policy tương đương)
  CORS chỉ cho Origin app khi cross-origin

Given request không authenticated:
  GET /api/csrf
Then:
  Bị authentication entry point từ chối theo chính sách
  (401, redirect login... tùy cấu hình)
~~~

Không đưa token thực vào ảnh chụp/CI logs khi test.

### 17.2. WebSocketStompClient kiểm tra CONNECT thật

Trong tích hợp Spring WebSocket/STOMP Servlet, có thể dùng `WebSocketStompClient` cùng `StandardWebSocketClient`:

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.messaging.simp.stomp.StompHeaders;
import org.springframework.web.socket.WebSocketHttpHeaders;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.messaging.WebSocketStompClient;

// Skeleton để minh họa test setup (chưa phải một test hoàn chỉnh):
WebSocketStompClient client = new WebSocketStompClient(
    new StandardWebSocketClient()
);

WebSocketHttpHeaders handshakeHeaders = new WebSocketHttpHeaders();
handshakeHeaders.setOrigin("https://app.example.com");
handshakeHeaders.add(
    HttpHeaders.COOKIE,
    "SESSION=" + validTestSessionCookie
);

StompHeaders connectHeaders = new StompHeaders();
connectHeaders.add(csrfHeaderName, validCsrfToken);

// client.connectAsync(uri, handshakeHeaders, connectHeaders, handler);
// Sau đó chờ CONNECTED/ERROR/close và assert trong timeout.
~~~

`validTestSessionCookie`/`validCsrfToken` phải được test setup lấy từ **cùng session**. Skeleton chưa có test server, bean configuration, STOMP session handler, asynchronous assertions hay protocol message converter. API client cần đối chiếu phiên bản Spring hiện có.

### 17.3. Kịch bản kiểm thử end-to-end

~~~text
Setup:
  - Test server chạy random port.
  - HTTP login user Alice, lưu session cookie.
  - GET /api/csrf với cookie Alice, lấy token và header name.
  - Spring endpoint /ws yêu cầu authenticated, chỉ cho Origin app.
  - @EnableWebSocketSecurity bật CONNECT CSRF + message ACL.

Positive:
  1) HTTP handshake Origin app + cookie Alice.
  2) STOMP CONNECT có native CSRF token Alice.
  3) Chờ CONNECTED.
  4) SUBSCRIBE /user/queue/order-results.
  5) SEND /app/orders.lookup với order Alice được sở hữu.
  6) Assert có phản hồi đúng Alice.

Negative:
  A) Kết nối giống hệt nhưng bỏ CSRF native header.
  B) Đổi token thành một chuỗi sai.
  C) Gửi token từ session Bob.
  D) Reconnect với token cũ sau khi đổi session.
  E) CONNECT đúng rồi SEND trực tiếp /topic/public.
  F) CONNECT đúng rồi SUBSCRIBE /topic/admin.
  G) CONNECT đúng nhưng Alice yêu cầu order của Bob.
  H) Origin evil + cookie Alice bị handshake chặn.

Assertions:
  - A–D không nhận CONNECTED; không xử lý business messages.
  - E–G không phát dữ liệu trái quyền; không có side effect.
  - H không mở transport.
~~~

Vì xử lý bất đồng bộ, phải quản lý timeout, `ERROR` frame, connection close, và kiểm tra message **không** được phát. Đừng dùng một HTTP `101` để kết luận các negative cases đã pass.

### 17.4. Thử trong browser DevTools

Với frontend thử nghiệm:

1. Network → xem HTTP `GET /api/csrf` và response CORS, status, cookie.
2. Network → WS → xem request `GET /ws`, header `Origin`, Cookie và HTTP status.
3. Frames/Messages → tìm STOMP `CONNECT` và native `X-CSRF-TOKEN`.
4. Xác nhận có `CONNECTED` khi token đúng; `ERROR`/close khi token sai.
5. Gửi SEND/SUBSCRIBE đúng và sai policy.
6. Test logout và reconnect.
7. Nếu SockJS fallback, xem HTTP `/ws/info` và các XHR POST/OPTIONS riêng.

Không dùng session/token thật của người dùng production. Khi chụp hình/thu thập traces, hãy che token và cookie.

## 18. Bảng chẩn đoán lỗi phổ biến

| Triệu chứng | Nguyên nhân có thể | Cần kiểm tra |
| --- | --- | --- |
| HTTP handshake 401/302 | Không có session, cookie bị browser chặn, auth chain sai | Cookie, SameSite/Domain/Path, SecurityFilterChain |
| HTTP handshake 403 từ website lạ | Origin policy từ chối | `setAllowedOrigins` và Origin thực |
| Browser báo `connect-src` | CSP chặn trước khi gửi request | CSP frontend, đích `wss://` |
| HTTP 101 nhưng không CONNECTED | CONNECT CSRF, principal hoặc protocol/frames | Native STOMP header và server messaging logs |
| Token trong HTTP GET được trả nhưng CONNECT vẫn thiếu | Client không truyền qua `connectHeaders` | Kiểm tra STOMP frame thực |
| CONNECT header là `X-CSRF-TOKEN` nhưng server đòi header khác | Custom `CsrfTokenRepository` | Dùng `csrf.getHeaderName()` từ response |
| Token đúng dạng nhưng vẫn mismatch | Sai session, masked/deferred token handler, token rotation | So repository/request handler và cookie, test same-session |
| CONNECT thành công lần đầu, reconnect liên tục thất bại | Session/token thay đổi nhưng client reuse token cũ | Refresh token trong beforeConnect |
| Browser có cookie nhưng server không nhận user | Cookie sai domain/path, backend session store khác, proxy | HTTP authentication principal và Spring Session |
| Lấy token trả 401 hoặc redirect | Chưa login, cookie không gửi | Authentication và CORS HTTP `/api/csrf` |
| Fetch `/api/csrf` lỗi CORS | Origin/credentials HTTP CORS sai | ACAO cụ thể, ACAC, `Vary: Origin` |
| Native WS 101 nhưng frontend bị CORS error trên token fetch | Hai cơ chế khác nhau | CORS ở GET token, Origin guard ở WS |
| STOMP CONNECT từ non-browser bị từ chối | Thiếu token/CSRF CONNECT đúng policy | Phân biệt với HTTP Origin/auth |
| SockJS XHR POST 403 trước CONNECT | HTTP CSRF transport hoặc gateway | XHR transport path, HTTP filter, CORS |
| Tắt CSRF HTTP nhưng CONNECT vẫn bị từ chối | CONNECT được kiểm ở Messaging | Đừng vô hiệu hóa toàn hệ thống; cấp đúng STOMP token |
| STOMP CONNECTED nhưng SEND trả lỗi | Destination/role hoặc business authorization | `AuthorizationManager<Message<?>>` và handler/service |
| User nhận dữ liệu người khác | ACL subscription/outbound routing yếu | Kiểm tra object/tenant trước phát |
| Sau logout socket cũ còn nhận message | Chưa thu hồi connection/subscriptions | Session lifecycle và revalidation |
| Gateway thêm ACAO trùng ở SockJS XHR | Chồng CORS policies | Quy định một nơi phát chính sách phù hợp |
| Nhiều nodes gây mismatch token | Session store/affinity không đồng nhất | Spring Session/shared store, LB routing |
| Client khai `login:admin` nhưng không được auth | Native STOMP login không phải application auth mặc định | Principal HTTP hoặc verifier ở CONNECT |
| Debug logs lộ token | Logging raw STOMP frames/headers | Redact token/cookie/Authorization |
| WebFlux native không có CONNECT CSRF | Không có STOMP broker protocol | Thiết kế Origin/first-message auth riêng |

### 18.1. Chẩn đoán theo trạng thái kết nối

~~~mermaid
flowchart TD
    A["Không kết nối realtime"] --> B{"Có HTTP handshake thành công?"}
    B -- "Không" --> C["TLS/CSP/Origin/Cookie/HTTP authentication"]
    B -- "Có" --> D{"Nhận STOMP CONNECTED?"}
    D -- "Không" --> E["Native CSRF header, session, @EnableWebSocketSecurity, interceptor order"]
    D -- "Có" --> F{"SEND/SUBSCRIBE được phép?"}
    F -- "Không" --> G["Message matcher, role/destination, business ACL"]
    F -- "Có nhưng sai dữ liệu" --> H["Object/tenant ownership, outbound routing, lifecycle"]
~~~

Đừng điều chỉnh HTTP `CorsFilter` khi nguyên nhân là STOMP CONNECT thiếu token. Đừng nới CSRF CONNECT khi nguyên nhân là client chưa có session cookie.

## 19. Vận hành production: token, session, proxy và giới hạn tài nguyên

### 19.1. Quản lý token và log an toàn

- Giữ CSRF token trong bộ nhớ frontend cần thiết, không đưa vào URL hoặc lưu lâu dài không cần.
- Tránh log raw STOMP CONNECT frames, `Authorization`, `X-CSRF-TOKEN` hay session cookies.
- Dùng HTTPS cho endpoint cấp token và WSS cho WebSocket qua TLS.
- Không cache response chứa token trên shared CDN hoặc public proxy.
- Với multi-node, token repository và session store phải nhất quán; hoặc thiết kế sticky sessions phù hợp.
- Có cơ chế theo dõi lỗi CONNECT theo **loại lỗi**, không cần ghi token thực.

### 19.2. Kết nối dài hạn và quyền thay đổi

CSRF CONNECT chỉ kiểm tra tại thời điểm client kết nối STOMP. Sau CONNECT, socket có thể tồn tại lâu:

- User logout hoặc session bị invalidate.
- Token access hết hạn.
- Role/tenant membership thay đổi.
- User bị khóa hoặc bị thu hồi quyền đối tượng.
- Subscription vẫn còn tồn tại sau khi user không còn được phép.

Cần chiến lược đóng connection, hủy subscription, revalidate quyền khi SEND/SUBSCRIBE và khi phát message nhạy cảm. **Token CSRF đúng lúc CONNECT không cấp quyền vĩnh viễn cho mọi message về sau.**

### 19.3. Quotas và xử lý lạm dụng

Bổ sung giới hạn:

- Số WebSocket connections đồng thời mỗi user/IP.
- Kích thước STOMP frame/payload.
- Số subscription mỗi session.
- Tốc độ SEND/CONNECT/reconnect.
- Heartbeat, inactivity timeout và send buffers.
- Giới hạn broker fan-out.
- Kiểm soát thông báo lỗi để không lộ chi tiết phiên/token.

Đây là những kiểm soát **ngoài CSRF**, nhưng cần thiết cho hệ thống realtime production.

## 20. Checklist triển khai

- [ ] Nắm được HTTP handshake và STOMP CONNECT là hai bước khác nhau.
- [ ] `@EnableWebSocketSecurity` đang áp dụng cho đúng Spring STOMP Messaging stack/phiên bản.
- [ ] Origin allowlist của WebSocket endpoint chỉ cho frontend tin cậy, không dùng wildcard với session riêng tùy tiện.
- [ ] HTTP `/ws` bảo vệ authentication theo đúng kiến trúc.
- [ ] HTTP `/api/csrf` do ứng dụng triển khai và chỉ cho user/frontend hợp lệ lấy token.
- [ ] Endpoint cấp token trả `headerName` và `token` đúng theo `CsrfTokenRepository`/handler của ứng dụng.
- [ ] Response token có cache policy an toàn và không bị log.
- [ ] HTTP CORS cho `/api/csrf` được cấu hình riêng với ACAO origin cụ thể khi có credentials.
- [ ] STOMP client gửi token trong **native CONNECT header**, không ở URL hoặc tưởng là HTTP GET header.
- [ ] CONNECT thiếu token, sai token, token phiên khác đều bị từ chối khi policy yêu cầu.
- [ ] CONNECT hợp lệ đi với principal đã được xác thực; không dùng token CSRF thay identity.
- [ ] Khi reconnect/login/logout/token rotation, client lấy token phù hợp với phiên hiện tại.
- [ ] Inbound SEND/SUBSCRIBE được phân quyền deny-by-default và không cho SEND trực tiếp vào broker destinations.
- [ ] Service kiểm tra object/tenant ACL trước khi trả dữ liệu, không tin userId trong payload.
- [ ] User destinations và outbound routing không phát dữ liệu trái quyền.
- [ ] SockJS XHR fallback, nếu sử dụng, được kiểm tra **HTTP CSRF/CORS** riêng với **CONNECT CSRF**.
- [ ] Không tắt HTTP CSRF cho toàn ứng dụng chỉ để SockJS transport hoạt động.
- [ ] Browser cookie `Secure`/`HttpOnly`/`SameSite`/Domain/Path phù hợp.
- [ ] CSP `connect-src`, TLS/HSTS và HTTP firewall không bị nới lỏng để che lỗi CSRF.
- [ ] Multi-node session/token repository và broker routing được kiểm thử.
- [ ] WebFlux native WebSocket không bị nhầm với STOMP CONNECT security của Servlet.
- [ ] Có test end-to-end xác minh **không nhận CONNECTED, không data leak và không side effect** khi bị từ chối.
- [ ] Logs/metrics không chứa token/session IDs và có tỷ lệ lỗi CONNECT/reconnect để cảnh báo.

## 21. Câu hỏi vận dụng và đáp án

**Tình huống 1 — HTTP 101 đã thành công.** Browser thấy `101 Switching Protocols`. Có thể kết luận CSRF token STOMP CONNECT đã được xác minh chưa?

**Đáp án:** Chưa. HTTP 101 thuộc transport. STOMP CONNECT và CSRF native header được kiểm tra sau đó.

**Tình huống 2 — Gửi token trong fetch trước đó.** Frontend đã gọi `GET /api/csrf` thành công nhưng STOMP CONNECT không có token. Có được CONNECTED không?

**Đáp án:** Không khi CONNECT CSRF được bật và yêu cầu token. Client phải đặt token vào `connectHeaders` để nó xuất hiện trên STOMP CONNECT.

**Tình huống 3 — Token ở URL.** Lập trình viên đưa token vào `wss://api.example.com/ws?csrf=...` để khỏi dùng STOMP native headers. Có nên không?

**Đáp án:** Không nên. URL dễ bị logging/tracing; Spring Messaging không mặc nhiên lấy query parameter để kiểm tra CSRF CONNECT. Dùng native header và API được hỗ trợ.

**Tình huống 4 — Token của Bob.** Alice mở socket bằng cookie của Alice nhưng gửi token Bob. Có hợp lệ không?

**Đáp án:** Không với mô hình repository token gắn theo phiên/ngữ cảnh Alice. Test cross-session để chứng minh.

**Tình huống 5 — Origin đúng.** Browser ở frontend tin cậy, cookie đúng, nhưng CONNECT thiếu token. Origin allowlist có thay CSRF không?

**Đáp án:** Không. Origin validation và CONNECT CSRF là hai lớp bổ sung.

**Tình huống 6 — SameSite=Lax.** Một user-controlled subdomain cũng same-site với API. Có thể bỏ Origin/CSRF CONNECT vì cookie SameSite không?

**Đáp án:** Không. Same-site không phải same-origin. Cookie có thể được gửi trong ngữ cảnh same-site; cần Origin allowlist hẹp và bảo vệ CONNECT.

**Tình huống 7 — Bearer token ở CONNECT.** Gửi native `Authorization: Bearer ...` có tự xác thực và tắt CSRF mặc định không?

**Đáp án:** Không. Phải có token verifier/interceptor thực và policy CONNECT CSRF được xác định rõ theo framework/threat model.

**Tình huống 8 — Socket kết nối trước login.** User login HTTP sau khi WebSocket đã mở anonymous. Socket có tự mang principal mới và CSRF token mới không?

**Đáp án:** Không nên giả định như vậy. Thường phải reconnect hoặc dùng một reauthentication flow được thiết kế riêng.

**Tình huống 9 — SockJS POST 403.** Native WebSocket hoạt động nhưng SockJS XHR POST bị 403 trước CONNECT. Đây chắc chắn là CONNECT CSRF thất bại không?

**Đáp án:** Không. Đó có thể là HTTP CSRF/CORS hoặc auth trên transport POST. Kiểm tra request path/method, xem đã tới Messaging chưa.

**Tình huống 10 — Tắt http.csrf.** Dev tắt CSRF HTTP toàn ứng dụng để sửa CONNECT error. Kết quả bảo mật?

**Đáp án:** Rủi ro mở các HTTP POST/PUT nghiệp vụ; CONNECT có thể vẫn bị Spring Messaging kiểm tra. Phải sửa cơ chế cấp/truyền token và tạo exception SockJS hẹp nếu cần.

**Tình huống 11 — Reconnect lỗi.** CONNECT đầu thành công, sau logout/login lại client auto-reconnect với token cũ rồi lỗi. Vì sao?

**Đáp án:** Token và session đã thay đổi. Làm mới token theo phiên trước mỗi CONNECT và xử lý reconnect/logout phù hợp.

**Tình huống 12 — CONNECTED nhưng Alice đọc order Bob.** CSRF hoạt động đúng nhưng dữ liệu vẫn bị lộ. Thiếu gì?

**Đáp án:** Object/tenant authorization và subscription/outbound routing. CSRF không thay kiểm tra quyền trên tài nguyên.

**Tình huống 13 — Client tự gửi login:admin.** Có thể lấy username từ STOMP header `login` thay cho principal được xác thực ở HTTP không?

**Đáp án:** Không. Header client tự khai không phải authentication của ứng dụng nếu không được xác minh bằng một cơ chế server-side.

**Tình huống 14 — CSRF endpoint CORS lỗi.** WebSocket `/ws` cho đúng Origin, nhưng Fetch `/api/csrf` bị browser chặn CORS. Có nên sửa `setAllowedOrigins` của `/ws` không?

**Đáp án:** Không phải hướng chính. Cần cấu hình HTTP CORS riêng cho endpoint cấp token, cùng cookie/authentication và credentials mode thích hợp.

**Tình huống 15 — WebFlux native.** Ứng dụng chỉ có `WebSocketHandler` text/binary của WebFlux, không có STOMP. Thêm `@EnableWebSocketSecurity` có tự tạo CONNECT CSRF không?

**Đáp án:** Không. Không có STOMP CONNECT theo mô hình native này. Phải bảo vệ HTTP handshake, Origin và protocol/message riêng của ứng dụng.

**Tình huống 16 — Lộ token qua debug log.** Server log toàn bộ CONNECT frame để điều tra CSRF. Đây có phải cách tốt không?

**Đáp án:** Không. Token có thể bị lộ qua log; chỉ ghi tên lỗi/trạng thái và metadata không nhạy cảm, redact native headers.

**Tình huống 17 — Kết quả âm chưa đủ.** Test thấy CONNECT bị từ chối nhưng vẫn có thông báo của Bob được gửi cho Alice trong lúc race. Có pass không?

**Đáp án:** Không. Phải chứng minh không có data leak/side effect, kể cả khi có xử lý bất đồng bộ và nhiều subscriptions.

---

**Ghi nhớ:** **STOMP CONNECT CSRF được kiểm tra sau HTTP handshake** và yêu cầu **token hợp lệ trong native STOMP CONNECT header**, không phải HTTP GET Upgrade header. Với Spring WebSocket Messaging/`@EnableWebSocketSecurity`, hãy cấp token qua một HTTP endpoint được bảo vệ, truyền bằng `connectHeaders`, kiểm thử đúng session và làm mới khi reconnect. Giữ **Origin allowlist, HTTP authentication, CSRF HTTP của API, message authorization và object/tenant ACL** như những lớp riêng. Nếu dùng SockJS, phân biệt HTTP POST fallback CSRF với CONNECT CSRF; nếu dùng WebFlux native WebSocket, tự thiết kế bảo vệ tương ứng vì không có STOMP CONNECT mặc định.
