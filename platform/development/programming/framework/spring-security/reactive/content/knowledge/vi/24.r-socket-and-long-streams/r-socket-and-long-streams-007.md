# Bảo vệ bước bắt tay WebSocket và kiểm tra Origin

## 1. Vì sao handshake WebSocket là ranh giới bảo mật?

WebSocket tạo một kênh hai chiều và sống lâu giữa client với server. Trước khi có WebSocket frames, hai bên cần một **HTTP handshake**; ở WebSocket HTTP/1.1 thông dụng, browser gửi GET có headers `Upgrade: websocket`, `Connection: Upgrade`, `Sec-WebSocket-Key` và thường có `Origin`. Server xác thực, kiểm tra policy, chấp nhận hoặc từ chối nâng cấp. Khi thành công, response thông dụng là **HTTP 101 Switching Protocols**.

```http
GET /ws/echo HTTP/1.1
Host: ws.example.invalid
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: <random-key>
Sec-WebSocket-Version: 13
Origin: https://app.example.invalid
Cookie: SESSION=<browser-session-if-present>
```

```http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: <server-computed-value>
```

Đây là **HTTP/1.1 minh họa**, không phải chuỗi request dùng nguyên để thử; kết nối dùng HTTP/2 extended CONNECT có handshake khác. Sau khi chuyển thành WebSocket, các messages **không đi qua một lần HTTP request/response độc lập** cho mỗi frame, do đó `SecurityWebFilterChain` không tự được thực thi lại với mỗi message.

**Chủ đề:** Bảo vệ bước bắt tay WebSocket và kiểm tra Origin.  
**Ngữ cảnh cha:** RSocket và luồng dài.  
**Module:** Spring Security - reactive.  
**Phiên bản ví dụ:** Java 17+, Spring Boot 3.5.x, Spring Framework 6.2.x, Spring Security 6.5.x.

### Mục tiêu học tập

1. Hiểu các lớp WebSocket handshake, security authentication, Origin validation và frame authorization.
2. Nhận biết **Cross-Site WebSocket Hijacking (CSWSH)** khi trình duyệt tự mang cookie đến WebSocket endpoint.
3. Biết vì sao trình duyệt **không tự thi hành Same-Origin Policy để chặn WebSocket** giống cách CORS hạn chế việc đọc HTTP response của `fetch`.
4. Kiểm tra `Origin` phía server bằng **allowlist scheme + host + port chính xác**; phân biệt `Origin` là `https://app.example.invalid`, còn target WebSocket là `wss://ws.example.invalid`.
5. Sử dụng `SecurityWebFilterChain` để yêu cầu authentication/role trong HTTP handshake trước upgrade.
6. Áp `WebFilter` chặn Origin sai, thiếu, `null` hoặc không khớp; biết WebFlux `WebSocketHandler`/`SimpleUrlHandlerMapping` hỗ trợ `CorsConfigurationSource`.
7. Không coi Origin là phương thức xác thực: non-browser clients có thể tự giả Origin.
8. Phân biệt cách browser dùng HttpOnly session cookie với non-browser client tự thêm Authorization header; không đưa Bearer token vào query hoặc subprotocol vô tội vạ.
9. Xây dựng ví dụ WebFlux Java 17+ có strict Origin guard, authentication và echo socket, cùng HTTP + WebSocket handshake tests.
10. Đặt quyền từng message, timeouts, quotas, lifecycle, re-auth khi token hết hạn và quản lý kết nối dài.
11. Liên hệ RSocket-over-WebSocket: cùng ranh giới HTTP/Origin nhưng **RSocket SETUP/route security khác** raw WebSocket frames.
12. Review TLS/WSS, proxies, load balancers, trusted forwarded headers, CORS/CSRF và observability.

**Giới hạn ví dụ:** `ws://127.0.0.1` cùng credentials demo chỉ phục vụ môi trường localhost. Production phải dùng `wss://` với TLS và cơ chế xác thực phù hợp. Domain `example.invalid` trong tài liệu là domain ví dụ, không có dịch vụ thật.

## 2. Luồng bảo mật từ HTTP sang WebSocket

```text
Browser ở Origin https://app.example.invalid
             |
             | new WebSocket("wss://ws.example.invalid/ws/echo")
             |
             | GET /ws/echo + Upgrade + Origin + Cookie (nếu có)
             v
Server WebFlux
  1. Ingress/TLS/proxy: route chỉ tới trusted backend
  2. Origin guard: origin phải thuộc allowlist
  3. Spring Security SecurityWebFilterChain:
       lấy Authentication từ Basic/Bearer/WebSession...
       yêu cầu authenticated/role/scope
  4. HandlerMapping + WebSocketHandlerAdapter
  5. WebSocketService/RequestUpgradeStrategy:
       validate handshake và upgrade
             |
             +-- reject -> HTTP 400/401/403 (tùy layer)
             |
             +-- accept -> HTTP 101, WebSocketSession
                               |
                               v
                      Application WebSocketHandler
                      mỗi inbound frame:
                        - validate message type/size/schema
                        - authorize action/resource
                        - enforce tenant/owner/quotas
                        - control backpressure/lifetime
```

**Hai giai đoạn không thay nhau:**
- **Handshake** quyết định client có được mở kênh tại thời điểm kết nối hay không.
- **Message-level policy** quyết định trong kênh đã mở client có được subscribe room, truy xuất tenant, phát lệnh hoặc xem dữ liệu ở mỗi thời điểm không.

Origin cho biết **nguồn trang Web mà browser đang chạy**, không chứng minh user là ai. Session cookie/JWT/mTLS là cơ chế khác. HTTP 101 chỉ chứng minh handshake được chấp nhận, không cho quyền làm mọi action tiếp theo.

### 2.1. Header Origin thực sự là gì?

Với page `https://app.example.invalid/chat` mở WebSocket đến `wss://ws.example.invalid/stream`, header thường là:

```http
Origin: https://app.example.invalid
```

Không phải:

```http
Origin: wss://ws.example.invalid/stream
```

Origin được mô tả bằng **scheme + host + port**, không có URL path/query/fragment. Khi website chạy HTTPS, Origin có `https://`; với local frontend `http://localhost:3000`, Origin có `http://` dù target là `ws://localhost:8080`. Một giá trị `null` có thể xuất hiện ở một số opaque origins (sandbox, file URLs); **không mặc định cho phép** khi endpoint mang session/credential.

Các Origin sau khác nhau:

```text
https://app.example.invalid             trusted production page
https://app.example.invalid:443         explicit port; policy phải xác định
http://app.example.invalid              downgrade, không cùng origin
https://evil.example.invalid            host khác
https://app.example.invalid.evil.invalid  suffix giả
https://app.example.invalid:444         port khác
null                                    opaque origin, từ chối theo policy
```

Nên cấu hình allowed origins rõ ràng, thường một tập nhỏ do server quản lý. **Không** check `contains("app.example.invalid")`, `endsWith("example.invalid")` hoặc tùy ý bật `*` cho endpoint cookie-authenticated.

### 2.2. Vì sao Browser Same-Origin Policy chưa đủ?

Đối với `fetch`, browser quản lý cross-origin access theo CORS; với **WebSocket API**, browser có thể gửi cross-origin handshake, kèm `Origin`, còn **server** có trách nhiệm từ chối nếu Origin ngoài tập cho phép. Không được trông chờ browser chặn request chỉ vì page attacker khác origin.

Một kịch bản CSWSH:

1. User đã đăng nhập vào `https://ws.example.invalid` bằng session cookie.
2. User mở `https://attacker.example.invalid`.
3. JavaScript trang attacker chạy `new WebSocket("wss://ws.example.invalid/ws/account")`.
4. Nếu browser gửi cookie và server tin cookie nhưng **không kiểm Origin**, kết nối có thể được tạo dưới danh nghĩa user.
5. Attacker có thể gửi/nhận frames và thực hiện các hành động mà user được phép.

Việc cookie có đi kèm phụ thuộc SameSite, Secure, browser context và chính sách hiện hành; **không lấy SameSite làm biện pháp duy nhất**. Một số browser/cấu hình/session models vẫn có thể tạo cross-site credentialed request. Server phải kiểm Origin.

### 2.3. Origin không phải authentication

Một CLI/non-browser client có thể tự đặt:

```http
Origin: https://app.example.invalid
```

dù nó không chạy từ trang ấy. Vì vậy Origin allowlist là **phòng vệ browser cross-site**, không phải identity proof. Phải xác thực user/service bằng session/Bearer/mTLS/trusted client certificate, và phân quyền độc lập.

Nếu ứng dụng có machine clients cần kết nối không có Origin, nên tạo **endpoint/policy riêng**, dùng mTLS/JWT và kiểm soát network. Không mở rộng endpoint cookie-authenticated thành “missing Origin = trusted client” vì attacker có thể dùng non-browser tools hoặc proxy.

## 3. Spring WebFlux xử lý handshake bằng gì?

### 3.1. Raw WebSocket trong Spring Framework

Các class WebFlux chính:

| Thành phần | Vai trò |
|---|---|
| `WebSocketHandler` | Xử lý WebSocketSession và inbound/outbound messages |
| `WebSocketSession` | `receive()`/`send()`, handshakeInfo, close status |
| `SimpleUrlHandlerMapping` | Map URL `/ws/echo` tới WebSocketHandler |
| `WebSocketHandlerAdapter` | Kết nối HandlerMapping với WebSocketService |
| `HandshakeWebSocketService` | Kiểm tra HTTP handshake cơ bản và dùng RequestUpgradeStrategy |
| `RequestUpgradeStrategy` | Nâng cấp theo Reactor Netty/Tomcat/Jetty |
| `CorsConfigurationSource` (reactive) | Cấu hình origins cho WebSocket handler |
| `WebFilter` | Chặn request ở lớp HTTP trước handler/upgrade |
| `SecurityWebFilterChain` | Authentication/authorization ở HTTP handshake |
| `ReactiveSecurityContextHolder` | Security Context cho reactive execution |
| `HandshakeInfo` | Headers, URI, principal và metadata của handshake |

Spring Framework tài liệu WebFlux hướng dẫn dùng `WebSocketHandler` implement `org.springframework.web.cors.reactive.CorsConfigurationSource` hoặc cấu hình `corsConfigurations` trên `SimpleUrlHandlerMapping`. Đây là API của **reactive stack**; không copy `OriginHandshakeInterceptor` của **Servlet** `org.springframework.web.socket.server.support` sang WebFlux raw WebSocket.

Trong tài liệu Servlet WebSocket có API `WebSocketHandlerRegistration#setAllowedOrigins(...)`. Điều đó **không phải** method bạn gọi trực tiếp trên `HandshakeWebSocketService` reactive. Tránh nhầm Servlet `WebSocketHandler` với `org.springframework.web.reactive.socket.WebSocketHandler`.

### 3.2. CORS config của HandlerMapping và Origin guard

WebFlux `HandlerMapping` có hỗ trợ CORS; tài liệu WebSocket gợi ý cung cấp `CorsConfigurationSource` ở handler. Một số HTTP/CORS xử lý phụ thuộc mapping và handshake, nên bài demo dùng **hai lớp rõ ràng**:

1. `WebSocketHandler` triển khai `CorsConfigurationSource` cho Spring Framework, liệt kê origins hữu hạn.
2. `WebFilter` chạy trước các bước authentication/upgrade, **tự reject** Origin không đúng một cách fail-closed ở endpoint có browser credentials.

Đây không phải yêu cầu mọi app phải viết hai lớp giống nhau; mục đích là minh họa **một chính sách Origin có thể test được**, không phụ thuộc browser-side CORS response headers. Dù dùng một hay hai lớp, cần integration test **HTTP Upgrade thật**.

### 3.3. HTTP authentication được áp khi nào?

Một `SecurityWebFilterChain` có thể dùng:

```java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers(HttpMethod.GET, "/ws/echo").authenticated()
    .anyExchange().denyAll())
```

Đây là snippet, cần nằm trong Security config. Trước khi chấp nhận handshake, Spring Security xử lý HTTP request và Authentication đã được thiết lập từ mechanism được cấu hình. Một HTTP 401 hoặc 403 ngăn upgrade; request chưa thành WebSocketSession.

Đối với WebFlux raw `WebSocketHandler`, việc xác thực ở handshake **không tự biến thành một authorization engine cho mọi text/binary frame**. Nếu frame mang `joinRoom("tenant-b")` hoặc `deleteDocument("id")`, handler/service phải kiểm permission của operation/resource, tránh lấy user-supplied destination/tenant làm quyền.

### 3.4. Session cookie so với Bearer token

**Browser dùng native WebSocket API**:

```javascript
// Browser page chạy tại https://app.example.invalid
const socket = new WebSocket("wss://ws.example.invalid/ws/echo");

socket.onopen = () => socket.send("ping");
socket.onmessage = event => console.log(event.data);
socket.onclose = event => console.log(event.code);
```

Trình duyệt tự thiết lập những handshake headers theo API. Native `new WebSocket(url[, protocols])` **không cho JavaScript đặt một Authorization HTTP header tùy ý**. Với browser SSO, lựa chọn thường là cookie `HttpOnly`/`Secure`/`SameSite` phù hợp và server-side session auth. Khi đó Origin check càng quan trọng.

**Non-browser client** có thể cung cấp HTTP Basic hoặc Bearer header khi handshake. Demo runnable ở phần 8 dùng HTTP Basic chỉ để minh họa thứ tự Origin + authentication, không coi Basic là giao thức tối ưu cho browser production.

Các thiết kế khác:
- Short-lived, one-time WebSocket ticket được cấp qua HTTPS trong session đã xác thực, bound với user/Origin/endpoint và tiêu thụ một lần. Cần quản lý replay/expiry và không log ticket.
- Token qua `Sec-WebSocket-Protocol` phải có protocol negotiation hợp lệ; không nhét access token sống lâu vào header subprotocol/echo response một cách tiện tay.
- Access token trong URL query dễ rò vào proxy/access logs/history/traces; nên tránh.
- Khi đăng nhập browser bằng cookie, CSRF cho HTTP login hoặc unsafe requests vẫn phải làm. Mặc định CSRF của Spring Security tập trung unsafe HTTP methods; GET WebSocket upgrade **không tự được bảo vệ bởi một CSRF token**.
- SameSite cookie, HttpOnly, Secure và Origin là các lớp khác nhau; không lớp nào tự thay server-side authentication.

## 4. Ranh giới handshake so với message/connection lifecycle

### 4.1. Handshake chỉ xét tại thời điểm t0

```text
t0: Bearer token/session hợp lệ -> WebSocket accepted
t1: subscription notifications/tenant-a -> kiểm quyền
t2: user bị khóa hoặc token hết hạn
t3: client tiếp tục gửi frames
t4: logout/permission revoke
```

Nếu chỉ validate tại t0, kết nối đã mở có thể vẫn hoạt động ở t3. HTTP Security filters **không tự chạy lại mỗi frame**. Ứng dụng cần quyết định:

- Maximum connection lifetime và idle timeout.
- Khi access token expiry/logout/revocation: đóng kết nối, yêu cầu re-auth hoặc giảm quyền; triển khai cơ chế theo threat model.
- Tại các operation nhạy cảm, kiểm quyền hiện thời từ trusted authorization store hoặc identity context.
- Tenant/room membership changes có được cập nhật ngay không?
- Buffer/queue/stream credits/backpressure, outbound fan-out quotas.
- Kiểm tra schema và kích thước message trước khi dùng trong business.
- Chỉ gửi dữ liệu cho tenant/subject đã được cấp quyền, không theo room name tự khai.

### 4.2. CSRF, CORS và WebSocket không đồng nhất

| Cơ chế | Bảo vệ gì? | Không tự bảo vệ |
|---|---|---|
| CORS | Browser policy cho cross-origin HTTP responses/preflight | Không tự chặn raw WebSocket handshake ở mọi browser |
| Origin allowlist | Cross-site browser WebSocket connection attempts | CLI clients giả Origin; kiểm quyền từng message |
| CSRF token | Browser có session cookie gửi unsafe HTTP requests | GET Upgrade không tự buộc CSRF theo default WebFlux |
| Authentication | Principal ở handshake | Thay đổi quyền sau kết nối/tất cả frames |
| Message authorization | Quyền mỗi event/route/resource | TLS, DoS, malformed handshake |
| HTTPS/WSS | Confidentiality/integrity transport | Quyền của user và Origin tin cậy |
| SameSite/HttpOnly cookie | Giảm credential exposure/CSRF một phần | Không thay strict Origin + authorization |
| mTLS | Danh tính workload hoặc client | Quyền user/tenant/record nếu không có policy khác |

**Lưu ý khác stack:** Spring Security Servlet `@EnableWebSocketSecurity` và STOMP message broker có tích hợp authorization, thường yêu cầu CSRF ở STOMP CONNECT. Không suy ra raw Spring WebFlux `WebSocketHandler` tự có hành vi tương tự. RSocket dùng `RSocketSecurity`, không phải STOMP.

### 4.3. Limits và backpressure

WebSocket là long-lived; kẻ xấu có thể:
- Mở hàng nghìn kết nối mà không gửi dữ liệu.
- Gửi frames rất lớn hoặc binary payload sai format.
- Gửi message tốc độ cao, yêu cầu fan-out vô hạn.
- Tạo subscription nhiều room hoặc request stream tốn CPU.
- Ngừng đọc response khiến server buffer tăng.
- Gửi fragment frames để làm đầy memory hoặc giữ parser bận.

Cần connection limits theo identity/IP, idle timeout, maximum lifetime, size limits ở gateway/server/`RequestUpgradeStrategy`, validation per message, bounded queues, backpressure, cancellation và rate quotas. `Flux` không đồng nghĩa tự an toàn trước mọi memory/transport exhaustion.

### 4.4. Multitenant subscriptions

Một authenticated user có tenant `acme` không được chỉ gửi:

```json
{"action":"subscribe","tenant":"globex","channel":"private-events"}
```

và được join `globex`. Backend phải so tenant/request resource với verified principal/membership/ACL. Nếu quyền thay đổi trong khi socket mở, cần revoke subscription hoặc close connection. Không lấy tenant từ `Origin` hay `X-Tenant` thay vì trusted authorization.

## 5. Origin validation: các trường hợp pass/fail

Giả sử endpoint production chỉ nhận page `https://app.example.invalid`, dev nhận `http://localhost:3000`.

| Origin header | Kỳ vọng | Vì sao |
|---|---|---|
| `https://app.example.invalid` | Allow nếu đã xác thực | Production browser origin exact |
| `http://localhost:3000` | Allow trong cấu hình dev | Local frontend origin |
| `https://attacker.example.invalid` | Deny | Host không thuộc allowlist |
| `https://app.example.invalid.attacker.invalid` | Deny | Suffix spoof |
| `http://app.example.invalid` | Deny | Scheme downgrade |
| `https://app.example.invalid:444` | Deny | Port khác |
| `Origin: null` | Deny | Opaque origin ngoài policy |
| Không có Origin | Deny ở endpoint browser demo | Không mặc nhiên tin non-browser |
| Hai header Origin | Deny | Ambiguous/duplicate input |
| `https://app.example.invalid, https://evil.invalid` | Deny | Không phải một Origin hợp lệ theo allowlist |
| `https://app.example.invalid/path` | Deny | Origin không bao gồm path |
| `ws://app.example.invalid` | Deny | Origin dùng http/https, không ws |
| `https://app.example.invalid/` | Deny trong strict string policy | Trailing slash không thuộc serialized Origin được allowlist |

Một ứng dụng production có thể chuẩn hóa default ports/IDN và parser một cách chặt chẽ để hỗ trợ nhiều browser clients; **đừng vô tình nới policy** khi normalize. Cách đơn giản nhất với các origins hữu hạn đã xác định là compare **exact full Origin strings**.

### 5.1. Vì sao không kiểm bằng request Host?

`Host` của WebSocket là **target server**, còn Origin là **trang gọi WebSocket**. Nếu target `ws.example.invalid`, bạn không thể chỉ so Origin host == Host rồi kết luận an toàn; một app frontend hợp lệ có thể chạy tại `app.example.invalid`. Ngược lại, nếu bạn lấy Host hoặc `X-Forwarded-Host` do caller có thể giả để “tính expected origin”, attacker có thể tác động policy.

Trusted proxies/reverse proxies phải normalize/strip forwarded headers ở boundary và backend phải dùng trusted config, không lấy arbitrary request headers làm allowlist.

### 5.2. Không bật allowOrigins("*") cho cookie WebSocket

Khi dùng credentialed WebSocket, wildcard `*` rất dễ làm mất lớp phòng vệ CSWSH. CORS cũng không cho phép wildcard origins kết hợp `allowCredentials=true` theo cách thông thường. Dùng danh sách origins cố định, review khi thêm tenant domains. Nếu có nhiều origins theo tenant, dựng allowlist từ **trusted registration** và buộc tenant của socket khớp principal; không lấy raw Origin tự tuyên bố tenant.

## 6. Project Java 17+ chạy được: OriginGuard + HTTP auth + WebSocket Echo

Đây là một project Spring Boot 3.5.x, Spring Security 6.5.x, Spring WebFlux/Netty. Demo dùng Basic auth cho Java test client (không phải browser pattern), **strict Origin filter** và WebSocketHandler có reactive CORS config.

Cấu trúc:

```text
src/main/java/demo/ws/
  SecureWebSocketApplication.java
  SecurityConfig.java
  OriginGuardFilter.java
  EchoSocketHandler.java
  WebSocketRoutes.java
  HealthController.java
src/test/java/demo/ws/
  WebSocketHandshakeTests.java
```

### 6.1. Dependencies

Tạo dự án Gradle Groovy bằng Spring Initializr, Java 17+, Spring Boot 3.5.x. Phần `dependencies` của `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
```

Đây là block dependencies, **không** phải toàn bộ `build.gradle`. Giữ plugins, repositories, Java toolchain và Gradle wrapper do Spring Initializr tạo. Không thêm `spring-boot-starter-web` vì demo cần inbound **WebFlux**, không phải Servlet MVC.

### 6.2. SecureWebSocketApplication.java

```java
package demo.ws;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecureWebSocketApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecureWebSocketApplication.class, args);
    }
}
```

### 6.3. OriginGuardFilter.java: fail-closed trước upgrade

```java
package demo.ws;

import java.util.List;
import java.util.Set;

import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public final class OriginGuardFilter implements WebFilter {

    private static final Set<String> TRUSTED_ORIGINS = Set.of(
        "http://localhost:3000",
        "https://app.example.invalid");

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        String path = exchange.getRequest().getPath()
            .pathWithinApplication().value();

        if (!"/ws/echo".equals(path)) {
            return chain.filter(exchange);
        }

        List<String> origins = exchange.getRequest()
            .getHeaders().getOrEmpty(HttpHeaders.ORIGIN);

        if (origins.size() != 1
                || !TRUSTED_ORIGINS.contains(origins.get(0))) {
            exchange.getResponse().setStatusCode(
                HttpStatus.FORBIDDEN);
            return exchange.getResponse().setComplete();
        }

        return chain.filter(exchange);
    }
}
```

**Giải thích chính xác:**

- Filter chỉ tác động endpoint `/ws/echo`, không ảnh hưởng `/health` hoặc routes khác.
- `@Order(Ordered.HIGHEST_PRECEDENCE)` chạy rất sớm trong WebFlux filter chain, trước HTTP security/handler mapping theo cấu hình demo.
- Chỉ một Origin header và exact Origin value được cho phép. Không có Origin (kể cả CLI) → 403; điều này là **policy cố ý** cho endpoint browser-facing, không là yêu cầu mọi WebSocket endpoint phải làm vậy.
- Origin sai → HTTP 403, không gọi `chain.filter(exchange)`, nên không vào handler và không upgrade.
- Origin đúng → request vẫn phải đi qua **authentication/authorization**; Origin không tự cấp 101.
- Không dùng `Host`/`Forwarded` hay query param làm allowed origin.
- Nếu triển khai dưới context path hoặc gateway rewrite, phải kiểm tra path `pathWithinApplication()` trên request **thực sự tới service** và match rules tương ứng.
- Trong production, allowed origins nên đến từ cấu hình server đáng tin (dev/prod tách riêng), không hardcode local insecure origin cùng production.

### 6.4. SecurityConfig.java: chặn handshake chưa authenticated

```java
package demo.ws;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    MapReactiveUserDetailsService users() {
        PasswordEncoder encoder =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();

        UserDetails user = User.withUsername("learner")
            .password(encoder.encode("study-pass"))
            .roles("WS")
            .build();

        return new MapReactiveUserDetailsService(user);
    }

    @Bean
    SecurityWebFilterChain chain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/health").permitAll()
                .pathMatchers(HttpMethod.GET, "/ws/echo")
                    .hasRole("WS")
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }
}
```

**Phân biệt trách nhiệm:**

- `OriginGuardFilter` xác minh **trang browser origin**, không cấp quyền.
- `SecurityWebFilterChain` xác minh user bằng HTTP Basic demo và yêu cầu `ROLE_WS` để mở socket.
- `PasswordEncoderFactories` tạo encoder có prefix `{bcrypt}` trong password đã hash (tùy factory defaults ở Security version); không lưu plaintext trong `UserDetails`. Password demo chỉ để test, **không triển khai credential tĩnh trong production**.
- `.formLogin(...disable())` chỉ dành cho ví dụ Basic/non-browser, vì native JS WebSocket API không thể chủ động thêm Authorization Basic header. Browser production nên dùng login/session cookie hoặc token/ticket flow được thiết kế riêng.
- GET handshake không yêu cầu CSRF token theo Spring Security default vì GET là HTTP safe method; để chống CSWSH cần **strict Origin** và có thể thêm one-time connection ticket cho nghiệp vụ nhạy cảm.
- Không mở `/ws/**.permitAll()` rồi hy vọng `WebSocketHandler` tự xác thực.
- Nếu đổi sang cookie login, cần cấu hình session security và HTTPS/Secure/HttpOnly/SameSite cookie, CSRF trên login/unsafe HTTP operations cùng Origin allowlist.

### 6.5. EchoSocketHandler.java: WebSocketHandler + reactive CORS config

```java
package demo.ws;

import java.util.List;

import org.springframework.http.HttpMethod;
import org.springframework.stereotype.Component;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.WebSocketSession;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Component
public final class EchoSocketHandler
        implements WebSocketHandler, CorsConfigurationSource {

    private final CorsConfiguration corsConfiguration;

    public EchoSocketHandler() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of(
            "http://localhost:3000",
            "https://app.example.invalid"));
        cors.setAllowCredentials(true);
        cors.setAllowedMethods(List.of(HttpMethod.GET.name()));
        cors.setAllowedHeaders(List.of("*"));
        this.corsConfiguration = cors;
    }

    @Override
    public CorsConfiguration getCorsConfiguration(
            ServerWebExchange exchange) {
        return corsConfiguration;
    }

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        return session.send(
            session.receive()
                .take(4)
                .filter(message ->
                    message.getType() == WebSocketMessage.Type.TEXT)
                .map(message -> session.textMessage(
                    "echo:" + message.getPayloadAsText()))
        );
    }
}
```

**Giải thích:**

- `CorsConfigurationSource` ở đây thuộc `org.springframework.web.cors.reactive`; nó cung cấp origin allowlist cho WebFlux HandlerMapping theo cơ chế Spring Framework.
- `setAllowCredentials(true)` đi kèm **origins hữu hạn**, không dùng wildcard. Demo HTTP Basic, nhưng cấu hình này còn minh họa policy khi tích hợp browser cookie session.
- `handle` chỉ echo **text frames**, tối đa bốn inbound messages trong một phiên demo; đây không phải chat room permission system.
- Không dùng `subscribe()`/`block()` trong handler; publisher do WebFlux/WebSocket infrastructure quản lý.
- Binary frames bị bỏ qua, nhưng production phải có frame size cap, schema validation, quotas và close policy rõ; đơn thuần `filter` không thay data validation.
- `session.receive()` và `session.send()` là reactive streams. Completion của handler sẽ kết thúc lifecycle WebSocket session theo infrastructure.
- Không tự suy ra mọi message được phép vì user đã được xác thực khi handshake. Với action nhạy cảm, lấy principal đã verified trong connection context và thực thi authorization trong service.

### 6.6. WebSocketRoutes.java: map handler

```java
package demo.ws;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.reactive.handler.SimpleUrlHandlerMapping;

@Configuration
public class WebSocketRoutes {

    @Bean
    HandlerMapping webSocketMapping(EchoSocketHandler handler) {
        SimpleUrlHandlerMapping mapping =
            new SimpleUrlHandlerMapping();
        mapping.setUrlMap(Map.of("/ws/echo", handler));
        mapping.setOrder(-1);
        return mapping;
    }
}
```

Spring WebFlux configuration trong Spring Boot cung cấp `WebSocketHandlerAdapter` hỗ trợ `WebSocketHandler`/WebSocketService mặc định; không cần tự viết Servlet handshake interceptor. `SimpleUrlHandlerMapping` ánh xạ chính xác `/ws/echo` vào EchoSocketHandler.

Ở production, nếu có nhiều routes/mappings, phải áp strict Origin và authentication cho **từng WebSocket endpoint**, tránh tạo route khác không được bảo vệ.

### 6.7. HealthController.java

```java
package demo.ws;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class HealthController {
    @GetMapping("/health")
    public Mono<String> health() {
        return Mono.just("ok");
    }
}
```

### 6.8. Chạy local

Từ project root, dùng Gradle wrapper của Initializr:

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Thử health:

```bash
curl -i http://localhost:8080/health
```

Kỳ vọng HTTP 200, body `ok`. Phản hồi có thể khác chi tiết headers/charset theo server.

Thử Origin sai (không cần WebSocket upgrade để thấy pre-handshake filter từ chối):

```bash
curl -i -H "Origin: https://evil.example.invalid" \
  http://localhost:8080/ws/echo
```

Kỳ vọng HTTP 403. Với Origin đúng nhưng thiếu Basic auth:

```bash
curl -i -H "Origin: http://localhost:3000" \
  http://localhost:8080/ws/echo
```

Kỳ vọng HTTP 401 từ Spring Security Basic auth (request này chưa có Upgrade). Kết nối WebSocket **thành công** cần WebSocket client gửi đúng handshake headers, Origin và Authentication; test phần 7 dùng `ReactorNettyWebSocketClient` để làm điều đó.

**Không** gửi password demo qua remote `ws://` hoặc public HTTP; production chỉ dùng WSS/TLS và credentials managed.

## 7. Kiểm thử tự động WebFlux và WebSocket handshake thật

`WebTestClient` thích hợp kiểm HTTP filter outcomes (403 Origin/401 auth) nhưng nó **không thay thế** một handshake WebSocket thực. Để kiểm 101/Upgrade, dùng `ReactorNettyWebSocketClient` trên random port của `@SpringBootTest`.

Các tests sau chạy offline với loopback Netty, không dùng external Identity Provider. Basic credentials chỉ có trong process test.

File `src/test/java/demo/ws/WebSocketHandshakeTests.java`:

```java
package demo.ws;

import java.net.URI;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;
import reactor.core.publisher.Mono;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(webEnvironment =
    SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class WebSocketHandshakeTests {

    @LocalServerPort
    int port;

    @Autowired
    WebTestClient http;

    private URI socketUrl() {
        return URI.create(
            "ws://127.0.0.1:" + port + "/ws/echo");
    }

    private HttpHeaders headers(String origin) {
        HttpHeaders headers = new HttpHeaders();
        if (origin != null) {
            headers.setOrigin(origin);
        }
        headers.setBasicAuth("learner", "study-pass");
        return headers;
    }

    private Mono<Void> connect(HttpHeaders headers) {
        return new ReactorNettyWebSocketClient()
            .execute(socketUrl(), headers, session -> {
                AtomicReference<String> message =
                    new AtomicReference<>();

                Mono<Void> outgoing = session.send(
                    Mono.just(session.textMessage("ping")));
                Mono<Void> incoming = session.receive()
                    .next()
                    .doOnNext(frame ->
                        message.set(frame.getPayloadAsText()))
                    .then();

                return Mono.when(outgoing, incoming)
                    .doOnSuccess(ignored -> assertEquals(
                        "echo:ping", message.get()));
            });
    }

    @Test
    void healthIsPublic() {
        http.get().uri("/health")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("ok");
    }

    @Test
    void missingOriginRejectedBeforeHandler() {
        http.get().uri("/ws/echo")
            .headers(h -> h.setBasicAuth("learner", "study-pass"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void evilOriginIsRejectedEvenWithBasicCredential() {
        http.get().uri("/ws/echo")
            .headers(h -> h.setBasicAuth("learner", "study-pass"))
            .header(HttpHeaders.ORIGIN,
                "https://evil.example.invalid")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void suffixSpoofingIsRejected() {
        http.get().uri("/ws/echo")
            .headers(h -> h.setBasicAuth("learner", "study-pass"))
            .header(HttpHeaders.ORIGIN,
                "https://app.example.invalid.evil.invalid")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void portMismatchIsRejected() {
        http.get().uri("/ws/echo")
            .headers(h -> h.setBasicAuth("learner", "study-pass"))
            .header(HttpHeaders.ORIGIN,
                "https://app.example.invalid:444")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void nullOriginIsRejected() {
        http.get().uri("/ws/echo")
            .headers(h -> h.setBasicAuth("learner", "study-pass"))
            .header(HttpHeaders.ORIGIN, "null")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void validOriginWithoutAuthenticationIsUnauthorized() {
        http.get().uri("/ws/echo")
            .header(HttpHeaders.ORIGIN,
                "http://localhost:3000")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void validOriginButBadCredentialIsUnauthorized() {
        http.get().uri("/ws/echo")
            .headers(h -> h.setBasicAuth("learner", "wrong"))
            .header(HttpHeaders.ORIGIN,
                "http://localhost:3000")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void allowedOriginAndAuthenticatedWebSocketCanExchangeText() {
        connect(headers("http://localhost:3000"))
            .block(Duration.ofSeconds(10));
    }

    @Test
    void untrustedOriginCausesActualHandshakeFailure() {
        assertThrows(Exception.class, () ->
            connect(headers("https://evil.example.invalid"))
                .block(Duration.ofSeconds(10)));
    }

    @Test
    void missingOriginCausesActualHandshakeFailure() {
        assertThrows(Exception.class, () ->
            connect(headers(null))
                .block(Duration.ofSeconds(10)));
    }
}
```

**11 test methods** gồm:
- 1 test public HTTP health.
- 5 tests HTTP Origin fail-closed (missing, evil, spoof, port, null).
- 2 tests Origin đúng nhưng chưa authenticated hoặc Basic sai → 401.
- 1 test WebSocket handshake thực với Basic + Origin đúng rồi gửi/nhận text `ping`/`echo:ping`.
- 2 tests WebSocket upgrade thực với Origin sai hoặc thiếu → handshake error trước khi có echo.

**Giới hạn:** Test dùng client có quyền tự tạo Origin và Basic header, khác browser JS; vì vậy success test chứng minh server-side allowlist và HTTP auth cho **non-browser test client**, không chứng minh session cookie/CSRF browser đã triển khai. Các asserts `assertThrows(Exception.class)` cố ý tránh khóa vào một loại Reactor Netty handshake exception có thể đổi theo version; khi phát triển dự án có thể kiểm tra chi tiết status code của lỗi.

### 7.1. Lệnh chạy

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

**Kỳ vọng** 11 test methods PASS trên project dependencies tương ứng; đây là **QA tĩnh** nội dung và API, không phải khẳng định Gradle đã chạy trong workspace này. Nếu test bị timeout do network/environment, phải chẩn đoán server startup, port, WebSocket handshake status và HTTP auth; không gỡ Origin filter để “sửa” test.

### 7.2. Thử thủ công bằng công cụ WebSocket

Một WebSocket CLI client có thể gửi Origin và Basic header, ví dụ từ công cụ hỗ trợ custom handshake headers. Không dùng `curl` HTTP GET không có Upgrade để kết luận đã tạo WebSocket session. Khi debug, log **Origin đã sanitize, path, reason code và user ID đã xác minh**, không log Cookie, Authorization, full token hoặc raw message PII.

Browser JS (nếu triển khai session-based authentication tương ứng):

```javascript
const ws = new WebSocket("wss://ws.example.invalid/ws/echo");
ws.onopen = () => ws.send("hello");
ws.onmessage = e => console.log(e.data);
ws.onclose = e => console.log(e.code, e.reason);
```

Native browser JS không có cách chuẩn để đặt `Authorization: Bearer ...` trên WebSocket constructor. Không copy backend Basic demo thành browser auth production mà chưa thiết kế session/ticket protocol.

## 8. Nâng cấp sang cookie-authenticated browser WebSocket

### 8.1. Luồng đề xuất

```text
1. Browser HTTPS tới login API
2. Login có CSRF protection (nếu cookie/session flow)
3. Server tạo WebSession được bảo vệ
4. Trả session cookie với Secure + HttpOnly + SameSite thích hợp
5. Browser từ https://app.example.invalid
   -> new WebSocket("wss://ws.example.invalid/ws/secure")
6. Browser có thể mang cookie theo browser cookie policy
7. Server:
   - Origin exact allowlist
   - Cookie session authentication
   - ROLE_WS / permissions handshake
   - Optional one-time WS ticket
8. HTTP 101 -> WebSocket connected
9. Each frame -> validate action/tenant/record permissions
10. Logout/revocation -> close/invalidate session/socket theo policy
```

Để dùng WebFlux form login session thay Basic demo, bổ sung `.formLogin(Customizer.withDefaults())` và cấu hình security/session policies, login form, CSRF token handling. Cần kiểm thử việc cookie `SESSION` được browser gửi tới WebSocket host theo SameSite/domain/secure settings; nếu frontend và socket khác site, không tự nới `SameSite=None`/`allowOrigins("*")` mà không có threat assessment.

**Không** coi Cookie có mặt là user đã authenticated: session phải được server xác minh, có TTL/rotation/session fixation protection và không lộ session ID. Nếu browser có thể giữ socket sau logout, cần chủ động close/reauthorize.

### 8.2. One-time handshake ticket cho các endpoint nhạy cảm

Đối với kênh nhận lệnh tài chính hoặc stream PII, ngoài Origin và session có thể dùng ticket:
1. Browser gọi HTTPS POST `/api/ws-ticket` với CSRF protection, được xác thực.
2. Server phát một opaque random ticket entropy cao, TTL rất ngắn, bound với session, Origin, user và endpoint.
3. Client gửi ticket trong một handshake mechanism được thiết kế (ví dụ short-lived subprotocol token có kiểm soát hoặc secure cookie khác).
4. Server tiêu thụ ticket **một lần** trước khi nâng cấp hoặc trước message đầu; reject replay/expired/wrong session.
5. Không log ticket/secret, không echo ticket trong `Sec-WebSocket-Protocol` response và không đặt credential lâu dài trong URL query.
6. On timeout/revoke, close connection.

Đây là **thiết kế kiến trúc**, không phải một Spring Security WebFlux auto feature. Nếu dùng `Sec-WebSocket-Protocol`, ứng dụng phải đàm phán protocol string hợp lệ; không tự nhét Bearer token vào danh sách subprotocol mà không kiểm soát browser/proxy logs.

### 8.3. Authn session không được dùng nguyên trạng thái mãi mãi

Kết nối được mở lúc 10:00 có thể còn mở lúc 11:00 khi session HTTP đã hết hạn. Cần chính sách:
- Hard maximum connection age.
- Idle timeout và heartbeat ping/pong.
- Re-auth hoặc re-authorization cho message nhạy cảm.
- Server-initiated close khi logout hoặc quyền tenant bị thu hồi.
- Quota per principal/tenant/room.
- Cơ chế lưu/lookup session state ở multi-replica, routing/stickiness nếu cần.
- Không để một user có quyền subscribe với `tenant=acme` chuyển thành `tenant=globex` bằng message payload.

## 9. RSocket over WebSocket: sự khác biệt quan trọng

**RSocket không đồng nghĩa raw text WebSocket.** RSocket là một protocol message/stream multiplexed có SETUP và nhiều request interactions như request-response, request-stream, channel, fire-and-forget. Nó có thể đi qua TCP hoặc WebSocket làm transport.

Spring Boot có thể expose RSocket qua WebSocket trên WebFlux/Netty:

```yaml
spring:
  rsocket:
    server:
      transport: websocket
      mapping-path: /rsocket
```

Đây là snippet **cho một ứng dụng có `spring-boot-starter-rsocket` và WebFlux Netty**, không phải cấu hình của echo WebSocket demo bên trên. Nếu chọn standalone TCP server, HTTP Origin header hoàn toàn **không tồn tại**; dùng TLS/RSocket SETUP/security theo protocol.

### 9.1. Các ranh giới với RSocket-over-WebSocket

```text
Browser Origin
    |
    v
HTTP GET Upgrade /rsocket  (WebSocket transport)
    |  Origin guard + HTTP access policy
    v
RSocket SETUP frame
    |  Authentication metadata / RSocketSecurity
    v
RSocket routes:
    |  authorizePayload / application ACL
    v
requestResponse / requestStream / requestChannel
    |  permissions per route/tenant
    v
Data
```

Nếu bạn chỉ gắn `OriginGuardFilter` của demo vào `/ws/echo`, nó **không tự bảo vệ `/rsocket`**. Khi thêm RSocket-over-WebSocket, phải áp Origin policy cho **đúng mapping path `/rsocket`** tại lớp HTTP/server adapter và kiểm thử handshake thật. RSocket route security là lớp độc lập; không giả định raw `WebSocketHandler` sẽ nhận/hiểu RSocket frames.

### 9.2. Spring Security RSocket

Spring Security Reactive cung cấp `@EnableRSocketSecurity`, `RSocketSecurity` và `PayloadSocketAcceptorInterceptor`/`SecuritySocketAcceptorInterceptor` cho RSocket SETUP/route authorization.

Snippet khái niệm theo API Spring Security:

```java
@Configuration
@EnableRSocketSecurity
class RSocketRules {

    @Bean
    PayloadSocketAcceptorInterceptor authorization(
            RSocketSecurity rsocket) {
        return rsocket
            .authorizePayload(authorize -> authorize
                .setup().authenticated()
                .route("notifications.*").hasRole("VIEWER")
                .anyRequest().denyAll())
            .build();
    }
}
```

Đây là **snippet**, cần imports, RSocket messaging/server setup và cách authentication metadata được ứng dụng hỗ trợ. Không thể copy nó trực tiếp vào project chỉ có starter-webflux và mong tự có RSocket server. Spring Boot khi có RSocket Security auto-config có thể gắn interceptor vào server; phải test trên transport/mapping cụ thể.

**Vai trò bổ sung:**
- **HTTP handshake Origin**: browser có được mở transport từ website này không?
- **RSocket SETUP authentication**: RSocket requester là ai?
- **RSocket route authorization**: route `notifications.private` hay tenant/channel này có được dùng không?
- **Long-lived streams**: khi scope/tenant quyền bị thu hồi thì cancel/close subscription như thế nào?

Nếu dùng RSocket TCP, **không có WebSocket HTTP handshake** hay Origin policy; thay bằng TLS/workload identity, authentication metadata và RSocket authorization.

### 9.3. Sự khác nhau với Spring STOMP WebSocket Security

Tài liệu Spring Security Servlet `@EnableWebSocketSecurity` và STOMP có rules ở `MESSAGE`/`SUBSCRIBE` và CSRF STOMP CONNECT. Không áp dụng `MessageMatcherDelegatingAuthorizationManager` của Servlet STOMP trực tiếp cho raw WebFlux `WebSocketHandler` hoặc RSocket routes.

| Stack | Handshake | Message security |
|---|---|---|
| Spring WebFlux raw WebSocketHandler | WebFilter, SecurityWebFilterChain, reactive CORS/Origin policy | Application WebSocketHandler/service ACL |
| Spring MVC + STOMP broker | Servlet Security + WebSocket endpoint allowed origins | Spring Security Messaging/STOMP CONNECT/SUBSCRIBE rules |
| Spring RSocket over WebSocket | WebSocket transport Origin/HTTP policy (nếu tích hợp) | RSocket SETUP/route authorization + business ACL |
| Spring RSocket TCP | Không có HTTP Origin | TLS/RSocket SETUP/route policy |

Nhầm lẫn các APIs này thường làm developer tưởng một annotation Servlet sẽ tự bảo vệ một WebFlux/RSocket endpoint nhưng thực tế không được gọi.

## 10. Reverse proxy, Cloud Gateway và Origin

Một deployment có thể là:

```text
Browser https://app.example.invalid
   |
   | wss://ws.example.invalid/ws/echo
   v
Cloud Load Balancer / API Gateway
   | TLS termination / trusted proxy forwarding
   v
Spring Boot WebFlux /ws/echo
```

Các điểm cần kiểm tra:

1. External WSS phải có certificate hợp lệ, không dùng `ws://` public.
2. Gateway hỗ trợ Upgrade/Connection và timeouts/idle heartbeat phù hợp.
3. Gateway phải forward hoặc normalize `Origin` theo policy; không tự gán Origin tùy tiện để bypass backend.
4. Nếu Spring Security dựa vào WebSession cookie, kiểm tra proxy cookie Domain/Secure/SameSite/Path.
5. Strip untrusted `X-Forwarded-Host`/`X-Forwarded-Proto` và chỉ tin các known proxies; đừng tính allowed origins từ forwarded header chưa xác minh.
6. Kiểm tra tất cả paths đi tới cùng backend, tránh alternative URL hoặc direct ingress bỏ qua Origin filter.
7. Không forward raw Bearer token tới upstream tùy ý; nếu gateway có OAuth2 token relay, giữ destination/audience policy.
8. Rate-limit handshake attempts/connection counts và active duration per identity.
9. WebSocket app instances cần chính sách shared session/revocation để revoke session across replicas.
10. Tracing/log redaction: chỉ log handshake outcome/normalized Origin/route/principal ID đã xác minh, không log Cookie/Authorization/CSRF ticket.
11. Socket path có prefix rewrite thì Origin filter phải match path backend thực, không chỉ public URL.
12. Với HTTP/2 WebSocket/extended CONNECT hoặc proxy đặc biệt, test transport thật, không áp logic GET/101 của HTTP/1.1 cho mọi version.

**Host Header và Origin có vai trò khác nhau:** Host là nơi request được gửi, Origin là nguồn trang; trusted routing/tenant identity không được dựa trên raw header mà caller có thể điều khiển.

## 11. Những lỗi triển khai thường gặp

| Hiện tượng | Nguyên nhân | Cách khắc phục |
|---|---|---|
| User mở trang attacker vẫn kết nối được qua cookie | Không validate Origin trên server | Strict allowlist, deny cross-site WebSocket handshake |
| Gateway authenticated nhưng socket nhận mọi event | Chỉ kiểm authn lúc handshake | Message-level scope/tenant/record ACL |
| HTTP CORS đúng nhưng WebSocket bị hijack | Coi CORS browser enforcement áp cho WS | Test Origin validation thực tại server |
| Origin là `wss://app...` nên bị reject | Hiểu sai Origin format | Header Origin dùng http(s) page origin |
| `Origin: null` được cho phép | Policy quá rộng | Reject opaque origin trừ khi có thiết kế riêng |
| Non-browser có thể giả Origin | Xem Origin như user identity | Bắt buộc authn độc lập, không dựa Origin |
| `new WebSocket` không gửi Authorization header | Browser API không cho set custom auth header | Dùng HttpOnly session cookie/ticket flow |
| Token lộ trong WS URL `?token=...` | Token nằm trong proxy logs/analytics | Tránh URL token, dùng secure auth design |
| Code gọi Servlet OriginHandshakeInterceptor | Nhầm Spring MVC và WebFlux | Dùng reactive CorsConfigurationSource/WebFilter |
| HTTP GET 200 được hiểu là WebSocket connected | Không có Upgrade handshake | Dùng real WebSocket client, kiểm 101 |
| WebSocket mở sau logout vẫn nhận data | Chỉ authn tại t0 | Connection expiry/revocation/recheck permissions |
| Kết nối không ngừng sau inactivity | Không có idle timeout/heartbeat | Cấu hình transport and session lifecycle |
| Attacker gửi binary/oversize frames | Không validate size/type | Max frame length, schema, rate quotas |
| `allowOrigins("*")` với credentials | Không hạn chế browser cross-site | Strict origins, allowCredentials policy phù hợp |
| Cross-tenant subscription đọc data khác | Tin message tenant từ caller | Verified tenant + resource membership/ACL |
| RSocket-over-WS vẫn không có Origin policy | Guard chỉ match raw `/ws/echo` | Áp policy riêng tại RSocket mapping `/rsocket` |
| Dùng Servlet STOMP `@EnableWebSocketSecurity` cho WebFlux raw | Sai stack | WebFlux security + application frame ACL |
| TLS terminated ở proxy nhưng backend tin Host bất kỳ | Forwarded headers chưa trusted | Trusted proxies/config cố định, không derive allowlist từ input |
| Unit test pass, production CSWSH | Không test handshake từ evil Origin với cookie | Browser/Netty handshake integration tests |
| Auto close ngay sau 1 message | Publisher lifecycle code kết thúc | Thiết kế receive/send lifecycle, quotas rõ |
| Logs chứa session cookie/token | Debug handshake raw headers | Redact, audit only policy metadata |
| Client retry liên tục khi 403 | Không phân biệt Origin mismatch | Log reason category, không tự nới allowlist |
| SameSite cookie được xem là đủ | Browser cookie policy thay đổi theo context | Origin + CSRF/session security + message ACL |

## 12. Bài tập và đáp án

### Bài 1 — Vì sao Origin phải được kiểm tại server?

**Đáp án:** Native browser WebSocket có thể kết nối cross-origin; browser gửi `Origin` nhưng không chặn hộ mọi cross-site WebSocket giống CORS fetch. Server phải reject Origin ngoài allowlist để ngăn CSWSH.

### Bài 2 — Origin của `https://app.example.invalid/chat` là gì?

**Đáp án:** `https://app.example.invalid`, không có path. Khi page đó mở `wss://ws.example.invalid/ws`, Origin vẫn là page origin, không phải `wss://...`.

### Bài 3 — Attacker dùng non-browser client với Origin giả?

**Đáp án:** Có thể. Origin không phải authentication. Phải xác thực client/user bằng trusted credentials/session/JWT/mTLS.

### Bài 4 — Gateway đã xác thực session, handler có cần quyền từng event?

**Đáp án:** Có. Handshake chỉ là entry authorization. Message payload có thể yêu cầu quyền theo room/tenant/operation và quyền có thể bị thu hồi khi kết nối còn mở.

### Bài 5 — Why CSRF filter default chưa đủ cho WS?

**Đáp án:** WebSocket HTTP/1.1 handshake là GET, Spring Security default CSRF tập trung unsafe HTTP methods. Raw WebFlux WS không tự có STOMP CONNECT CSRF. Cần strict Origin và có thể one-time ticket.

### Bài 6 — Có nên cho Origin `*` khi dùng session cookie?

**Đáp án:** Không. Cross-site page có thể dùng session credential nếu browser gửi cookie; wildcard mất lớp Origin restriction. Dùng exact origins allowlist.

### Bài 7 — Vì sao không đặt Bearer token trong query của WebSocket URL?

**Đáp án:** Query có thể xuất hiện trong proxy/access logs, traces và analytics, dẫn đến token leakage. Thiết kế session/ticket/auth metadata an toàn hơn, giảm TTL và redact.

### Bài 8 — CORS và Origin có giống nhau?

**Đáp án:** CORS là browser HTTP cross-origin access protocol, Origin header là dữ liệu về page source. Với WebSocket, server phải đánh giá Origin; có thể dùng reactive CORS configuration nhưng phải test thực.

### Bài 9 — Local frontend 3000 và WS backend 8080?

**Đáp án:** Browser Origin thường là `http://localhost:3000`, không phải `ws://localhost:8080`. Cho phép đúng dev origin nếu có policy; production không nên cho local insecure origin.

### Bài 10 — Token hết hạn trong WebSocket session?

**Đáp án:** HTTP security không tự tái chạy mỗi frame. Đặt max connection age, reauth, close on revoke/expiry và authorize các actions nhạy cảm.

### Bài 11 — RSocket-over-WebSocket có dùng raw WebSocketHandler không?

**Đáp án:** Không như một raw text handler. RSocket có SETUP/frames/routes riêng. Boot có mapping-path `/rsocket`; Origin policy tại HTTP transport và RSocketSecurity tại payload/route là hai lớp.

### Bài 12 — RSocket TCP có Origin header không?

**Đáp án:** Không, vì không có HTTP WebSocket handshake. Dùng TLS, RSocket SETUP authentication, route authorization và network policy.

### Bài 13 — Test WebTestClient GET không Upgrade đủ chứng minh handshake?

**Đáp án:** Không. Nó xác minh HTTP filters, không kiểm 101. Cần WebSocketClient/real HTTP Upgrade test.

### Bài 14 — Khi nào header missing Origin được cho phép?

**Đáp án:** Chỉ khi có **policy riêng** cho trusted non-browser clients, với authentication/network/mTLS controls phù hợp. Demo browser endpoint chủ ý reject missing Origin.

### Bài 15 — Khi same hostname phục vụ nhiều tenants?

**Đáp án:** Origin allowlist không xác minh tenant membership. Cần binding verified tenant/subject/room và record-level ACL; không tin tenant string do message/client gửi.

### Bài 16 — Tại sao cần TLS phía sau reverse proxy?

**Đáp án:** Proxy có thể chấm dứt TLS công khai nhưng internal hop vẫn mang cookies/credentials/PII. Theo threat model cần mTLS/HTTPS/service mesh và ingress restrictions.

### Bài 17 — Browser có thể set `Authorization: Bearer` trong `new WebSocket`?

**Đáp án:** Native WebSocket constructor không cho set arbitrary HTTP Authorization header. Nên sử dụng session cookie hoặc thiết kế short-lived ticket được bảo vệ; non-browser clients có thể đặt headers riêng.

### Bài 18 — Vì sao test Origin chính xác scheme + host + port?

**Đáp án:** `http` vs `https` hoặc port khác là origin khác; wildcard/suffix check mở rộng quyền của một page ngoài dự kiến. Strict full origin allowlist giảm lỗi.

## 13. Checklist production

- [ ] Bảo vệ từng WebSocket path ở ingress và `SecurityWebFilterChain`.
- [ ] Strict Origin allowlist server-side, không tin CORS browser chặn hộ.
- [ ] Không cho wildcard Origin với cookie-authenticated endpoints.
- [ ] Reject Origin missing/duplicate/null theo browser policy.
- [ ] Origin dùng page http(s) scheme, không nhầm với ws(s) target.
- [ ] Xác thực session/Bearer/mTLS độc lập; Origin không phải identity.
- [ ] Browser session cookie có Secure/HttpOnly/SameSite/expiry/rotation phù hợp.
- [ ] CSRF bảo vệ login/unsafe HTTP flows; không giả định GET Upgrade có token.
- [ ] One-time ticket cho sensitive sockets nếu threat model cần, không leak vào URL/logs.
- [ ] Handshake policy và message-level ACL độc lập.
- [ ] Recheck tenant/owner/permissions khi mỗi action nhạy cảm.
- [ ] Close hoặc re-auth connection khi token/session hết hạn/logout/revoke.
- [ ] Message schema, allowed frame types, max frame sizes, rate quotas.
- [ ] Connection/idle/max lifetime limits, cancellation/backpressure/heartbeat.
- [ ] WSS/TLS ở public endpoint và internal hop security phù hợp.
- [ ] Trusted proxies/forwarded headers, tránh tính Origin policy từ Host giả.
- [ ] Không lộ raw Authorization/Cookie/CSRF ticket trong logs/traces.
- [ ] Test HTTP filter với WebTestClient: 401/403 đúng.
- [ ] Test WebSocket Upgrade với ReactorNettyWebSocketClient: success/fail.
- [ ] Test browser cookie CSWSH và allowed/evil Origin trên môi trường staging.
- [ ] Với RSocket-over-WebSocket, bảo vệ riêng `/rsocket` và RSocket routes/SETUP.
- [ ] Không nhầm Servlet STOMP security APIs với WebFlux raw WS/RSocket.
- [ ] Theo dõi active connections, errors, quota breaches và revocation lifecycle.

## 14. Tóm tắt cốt lõi

```text
HTTP handshake:
  Origin allowlist -> Authentication -> Authorization -> Upgrade
   sai Origin          thiếu token       thiếu quyền     success
     403                  401                403           101

Sau Upgrade:
  SecurityWebFilterChain KHÔNG tự chạy lại từng frame
  -> WebSocketHandler cần per-message schema + ACL + tenant policy
  -> deadline/logout/revoke cần session/connection lifecycle control

Browser:
  new WebSocket(url), KHÔNG tự set custom Authorization header
  -> thường dùng cookie/session hoặc one-time ticket
  -> CSWSH prevention: strict Origin + credential validation

RSocket:
  WebSocket transport handshake Origin là một lớp
  RSocket SETUP authentication + route authorization là lớp khác
```

**Kết luận:** Kiểm tra Origin tại **server-side handshake** là tuyến phòng vệ quan trọng chống Cross-Site WebSocket Hijacking, đặc biệt với cookie session. Nhưng Origin không phải authentication, HTTP handshake không tự bảo vệ từng frame và một kết nối dài không tự mất quyền khi token hết hạn. Kiến trúc an toàn phải bảo vệ **trước upgrade, trong từng message và suốt lifecycle của socket**.

## 15. Tài liệu tham khảo

- [Spring Framework 6.2 — WebFlux WebSockets](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-websocket.html)
- [Spring Framework 6.2 — WebFlux Configuration/WebSocketService](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html)
- [Spring Framework 6.2 — WebFlux CORS](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-cors.html)
- [Spring Framework 6.2 — HandshakeWebSocketService API](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/web/reactive/socket/server/support/HandshakeWebSocketService.html)
- [Spring Security 6.5 — Reactive HTTP WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Security 6.5 — WebSocket Security (Servlet/STOMP; không áp trực tiếp cho WebFlux raw)](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/websocket.html)
- [Spring Security — Reactive RSocket Security](https://docs.spring.io/spring-security/reference/reactive/integrations/rsocket.html)
- [Spring Boot 3.5 — RSocket over WebSocket](https://docs.spring.io/spring-boot/3.5/reference/messaging/rsocket.html)
- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455)
- [RFC 6454 — The Web Origin Concept](https://www.rfc-editor.org/rfc/rfc6454)
- [OWASP — WebSocket Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html)
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
