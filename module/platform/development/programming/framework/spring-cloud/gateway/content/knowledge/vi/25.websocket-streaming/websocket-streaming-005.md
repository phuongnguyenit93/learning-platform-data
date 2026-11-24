# Xác thực, Origin và thông tin phiên khi bắt tay WebSocket

Trong **Spring Cloud Gateway**, các request REST thông thường kết thúc sau một HTTP response. Với **WebSocket**, client trước tiên gửi một HTTP request **bắt tay (handshake)**, sau đó kết nối được nâng cấp thành kênh hai chiều có thể sống nhiều phút hoặc nhiều giờ. Bởi vậy, kiểm tra danh tính, **Origin** và **thông tin phiên** tại thời điểm bắt tay quan trọng không kém việc chuyển tiếp đúng `ws://` hoặc `wss://` đến microservice.

Một WebSocket kết nối được nhưng **xác thực sai người dùng**, **chấp nhận Origin lạ** hoặc **dùng nhầm phiên giữa tenant** có thể phát tán sự kiện chat, thông báo hoặc dữ liệu trực tuyến không được phép. Ngược lại, hệ thống có thể trả `401`, `403`, `404` hoặc `502` ngay trong handshake dù backend và route HTTP thông thường vẫn hoạt động.

Bài thuộc chương **WebSocket và truyền luồng**, tập trung vào cách Spring Cloud Gateway Server WebFlux tiếp nhận handshake, phối hợp với **Spring Security**, kiểm tra `Origin`, chuyển tiếp cookie/token và quản lý trạng thái phiên. Kiến thức được liên hệ với route predicates, Gateway filter chain, service discovery qua `lb://`, TLS, rate limiting, circuit breaker, retry và quan sát request để vận hành cổng vào microservices an toàn.

> **Phạm vi:** Ví dụ sử dụng **Spring Cloud Gateway Server WebFlux** cùng cơ chế WebSocket qua HTTP/1.1 Upgrade phổ biến. HTTP/2 extended CONNECT có cơ chế bắt tay riêng và cần kiểm tra năng lực từng proxy/server; không giả định các ví dụ Upgrade áp dụng nguyên xi cho nó. Tên starter, thuộc tính cấu hình và hành vi Security/WebSocket proxy có thể thay đổi theo Spring Boot/Spring Cloud Gateway. **Origin không thay thế authentication**, còn WebSocket handshake hợp lệ không tự chứng minh mọi message sau đó được phép.

## 1. WebSocket bắt đầu bằng một HTTP request

Với trình duyệt, mã ứng dụng có thể mở:

```javascript
const socket = new WebSocket(
  "wss://api.example.test/ws/chat/rooms/42",
  ["chat.v1"]
);

socket.onopen = () => console.log("WebSocket connected");
socket.onmessage = event => console.log(event.data);
socket.onclose = event =>
  console.log("Closed:", event.code, event.reason);
socket.onerror = () => console.log("Connection error");
```

Khi dùng HTTP/1.1 Upgrade, trình duyệt gửi yêu cầu gần như sau:

```http
GET /ws/chat/rooms/42 HTTP/1.1
Host: api.example.test
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: <random-base64-key>
Sec-WebSocket-Version: 13
Sec-WebSocket-Protocol: chat.v1
Origin: https://app.example.test
Cookie: SESSION=<browser-session-id>
```

Các trường có ý nghĩa riêng:

| Thành phần | Vai trò | Điểm cần chú ý |
| --- | --- | --- |
| `GET /ws/...` | Đường dẫn HTTP của handshake | Phải khớp route predicate và upstream path |
| `Host` | Host đích của Gateway | Có thể ảnh hưởng `Host` predicate và TLS/SNI |
| `Upgrade: websocket` | Yêu cầu chuyển giao thức trong HTTP/1.1 | Proxy phải hỗ trợ Upgrade |
| `Connection: Upgrade` | Khai báo hop-by-hop cho Upgrade trong HTTP/1.1 | Ingress cần cấu hình truyền hợp lệ |
| `Sec-WebSocket-Key` | Nonce dùng trong tính toán handshake accept | **Không phải access token** |
| `Sec-WebSocket-Version: 13` | Phiên bản giao thức WebSocket | Không phải phiên bản ứng dụng |
| `Sec-WebSocket-Protocol` | Đề nghị subprotocol như `chat.v1` | **Không phải mặc định là chỗ gửi Bearer token** |
| `Origin` | Origin của trang khởi tạo kết nối theo browser | Dùng để đánh giá browser origin policy; không chứng minh identity |
| `Cookie` | Có thể chứa session của Gateway/ứng dụng | Phụ thuộc chính sách cookie của browser và cấu hình host/path |

Nếu tất cả điều kiện bắt tay được chấp nhận, HTTP/1.1 server có thể trả:

```http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: <derived-accept-value>
Sec-WebSocket-Protocol: chat.v1
```

Sau `101 Switching Protocols`, hai bên trao đổi **WebSocket frames**, không còn các HTTP request/response độc lập cho mỗi message. Gateway thường giữ một proxy connection tới backend WebSocket và chuyển frames giữa hai phía.

**Tách hai giai đoạn:** Trước `101`, Gateway và Security có thể từ chối bằng HTTP status như `401`/`403`. Sau `101`, lỗi chính sách thường được biểu diễn bằng **WebSocket close frame/close code**, chứ không thể thay kết nối đã nâng cấp bằng HTTP `401`.

## 2. WebSocket handshake nằm ở đâu trong Gateway?

Một đường đi logic thường gặp:

```mermaid
sequenceDiagram
    participant B as Browser
    participant I as Ingress / TLS terminator
    participant G as Spring Cloud Gateway WebFlux
    participant S as Spring Security / WebFilter
    participant L as LoadBalancer
    participant U as chat-service
    B->>I: GET /ws/chat + Upgrade + Origin + Cookie
    I->>G: Forward HTTP/1.1 handshake
    G->>S: Kiểm tra authentication / origin policy
    alt Bị từ chối trước upgrade
        S-->>B: 401 / 403 / redirect theo policy
    else Được phép
        G->>L: Route lb:ws://chat-service
        L->>U: WebSocket handshake tới instance
        U-->>G: 101 nếu upstream chấp nhận
        G-->>B: 101 Switching Protocols
        B<->>U: WebSocket frames qua Gateway
    end
```

Sơ đồ chỉ thể hiện **mô hình kiến trúc**, không phải cùng một thứ tự hook/lớp proxy ở mọi phiên bản. Spring Security ở WebFilter chain thường xử lý request trước `RoutePredicateHandlerMapping`; sau khi route match, Gateway filters và WebSocket routing mới có thể proxy downstream.

### Những ranh giới cần tách

- **Security trước route:** xác thực/ủy quyền cho phép request handshake đi vào.
- **Gateway route predicate:** chọn tuyến theo `Path`, `Host`, `Method`, headers...
- **Gateway filters:** có thể biến đổi đường dẫn/header hoặc áp chính sách cho handshake.
- **WebSocketRoutingFilter:** dùng scheme `ws`/`wss` của target URL để định tuyến handshake và proxy frames theo khả năng của Gateway.
- **Upstream WebSocket server:** có thể có authentication, Origin, subprotocol và message authorization độc lập.
- **Ingress:** có thể chặn hoặc làm mất các header cần thiết cho HTTP Upgrade trước khi request chạm Gateway.

Một lỗi handshake không nhất thiết là lỗi tại backend. Ví dụ Security trả `401` thì `WebSocketRoutingFilter` có thể **chưa chạy**.

## 3. Cấu hình route cho `ws://`, `wss://` và service discovery

Ví dụ route WebSocket khi backend được tìm qua Spring Cloud LoadBalancer:

```yaml
spring:
  cloud:
    gateway:
      routes:
        - id: chat-websocket
          uri: lb:ws://chat-service
          predicates:
            - Path=/ws/chat/**
          filters:
            - StripPrefix=1
```

Giả sử browser mở:

```text
wss://api.example.test/ws/chat/rooms/42
```

Ở ví dụ này:

1. Ingress hoặc Gateway nhận public `wss://`.
2. `Path=/ws/chat/**` chọn route WebSocket.
3. `StripPrefix=1` bỏ phân đoạn `ws`, còn `/chat/rooms/42` trên downstream.
4. `lb:ws://chat-service` yêu cầu giải `chat-service` thành một instance rồi dùng WebSocket scheme.
5. Khi handshake proxy thành công, frames được chuyển qua kết nối đã nâng cấp.

**Cần kiểm tra path upstream mong đợi.** Nếu `chat-service` xử lý `/ws/chat/rooms/42`, dùng `StripPrefix=1` sẽ làm path sai. Hãy kiểm thử bằng WebSocket client hoặc backend access log; route HTTP trả `200` không chứng minh WebSocket handshake đúng.

### Đừng nhầm `lb:ws://` với `lb://`

Trong các phiên bản Gateway hỗ trợ cú pháp `lb:ws://service-id`, phần `lb` yêu cầu load balancing, còn `ws` diễn tả WebSocket downstream. Với backend cần TLS, thường dùng `lb:wss://chat-service` (theo hỗ trợ phiên bản và backend TLS thực tế). `lb://chat-service` đơn lẻ có thể được diễn giải như HTTP thường và **không bảo đảm WebSocket routing filter được chọn**.

Không dùng `https://` thay `wss://` mà không kiểm tra Gateway routing scheme. Public wss qua TLS termination ở Ingress vẫn có thể proxy nội bộ qua ws nếu **trust boundary và policy cho phép**; trong môi trường yêu cầu mã hóa end-to-end, dùng wss/mTLS giữa các tầng.

### Prefix cấu hình phụ thuộc phiên bản

Một số Spring Cloud Gateway Server WebFlux phiên bản mới sử dụng `spring.cloud.gateway.server.webflux.routes` thay cho `spring.cloud.gateway.routes` truyền thống. Xác nhận starter và configuration metadata của bản đang chạy. Cấu hình YAML đúng cú pháp nhưng sai prefix có thể khiến route không được nạp và handshake trả `404`.

### WebSocket connection sau khi đã chọn instance

LoadBalancer thường chọn instance cho **handshake**, không phải chọn lại cho mỗi WebSocket frame. Khi đã kết nối:

```text
Browser <---- persistent socket ----> Gateway <---- socket ----> chat-instance-B
```

Nếu discovery cập nhật danh sách instances, kết nối đang hoạt động **không tự chuyển** sang instance khác như một HTTP request mới. Khi instance B dừng, client có thể mất socket và cần **reconnect với authentication/authorization mới**, có backoff/jitter và xử lý state ứng dụng.

## 4. Xác thực handshake: trước `101` phải có bằng chứng danh tính

Với HTTP API, Spring Security có thể xác minh JWT hoặc session trước khi gọi backend. Handshake cũng là một HTTP request, vì vậy **đây là cơ hội từ chối sớm** nếu client chưa được xác thực.

Ví dụ yêu cầu chỉ cho user đã login mở `/ws/**`:

```java
@Configuration
public class GatewayWebSocketSecurity {

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchange -> exchange
                .pathMatchers("/ws/**").authenticated()
                .anyExchange().permitAll())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
```

Đoạn mã chỉ **minh họa Spring Security reactive**; cần imports, dependency OAuth2 Client, login/client registration, session store và chính sách cho các API khác. **Không copy `anyExchange().permitAll()` vào production** nếu ứng dụng còn REST API bảo vệ, actuator management hoặc routes khác. Cần phân tách security matchers và authorization đầy đủ.

Khi user không có phiên, OAuth2 login có thể trả **HTTP redirect tới trang login**. Browser WebSocket API **không phải luồng login tương tác**; handshake redirect thường biểu hiện kết nối thất bại thay vì tự hoàn tất đăng nhập như một trang web.

**Mẫu BFF an toàn hơn:** Browser đăng nhập trước bằng HTTPS/OIDC; sau khi cookie phiên hợp lệ, mới gọi `new WebSocket(...)`. Nếu phiên hết hạn, app làm lại login qua HTTPS rồi mở lại socket.

### Với API Bearer token stateless

Gateway có thể xác thực Bearer qua Resource Server:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/demo
```

```java
@Bean
SecurityWebFilterChain websocketApiSecurity(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchange -> exchange
            .pathMatchers("/ws/**").hasAuthority("SCOPE_chat.connect")
            .anyExchange().authenticated())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}
```

Nhưng ở đây có một giới hạn quan trọng: **JavaScript WebSocket API trong browser không cho phép tùy ý thêm header `Authorization`**. Vì thế code như:

```javascript
// KHÔNG phải API browser WebSocket hợp lệ:
new WebSocket("wss://api.example.test/ws/chat", {
  headers: { Authorization: "Bearer <token>" }
});
```

**không hoạt động như mong đợi**. Đối số thứ hai của WebSocket constructor là **subprotocol(s)**, không phải object cấu hình headers. Non-browser clients có thể tự đặt headers theo thư viện riêng, nhưng phải kiểm tra loại client thực tế.

### Các phương án xác thực cho browser

| Phương án | Cách hoạt động | Đánh đổi |
| --- | --- | --- |
| **Cookie phiên/BFF** | Login bằng HTTPS, browser tự gửi cookie hợp lệ khi mở `wss://` | Cần Origin policy, SameSite/CSRF, session storage và revoke |
| **Vé handshake ngắn hạn một lần** | Client lấy ticket qua HTTPS đã xác thực; Gateway/upstream xác minh ticket khi handshake | Cần one-time use, ràng buộc user/tenant, TTL, tránh log/rò ticket |
| **Token trong query string** | `wss://.../ws?ticket=...` | Có thể xuất hiện ở proxy logs/trace/history; chỉ cân nhắc ticket ngắn hạn, không dùng long-lived access token |
| **`Sec-WebSocket-Protocol` chứa credential** | Dùng subprotocol như kênh chuyển token | Dễ sai protocol semantics, rò log và phản hồi subprotocol; không coi là mặc định |
| **Xác thực ở message sau 101** | Client gửi message auth đầu tiên theo protocol ứng dụng | Socket đã được nâng cấp; phải chặn mọi message trước auth và quản lý timeout/race |
| **Non-browser Authorization header** | CLI/mobile/native client đặt `Authorization: Bearer ...` lúc handshake | Hợp lý với client có quyền đặt header; không đồng nghĩa browser hỗ trợ |

**Khuyến nghị theo mức độ an toàn:** Với browser app sử dụng Gateway làm BFF, ưu tiên **cookie phiên bảo mật** cùng Origin allowlist, rồi kiểm tra quyền ở **từng resource/message** cần thiết. Nếu không dùng session, thiết kế **ticket ngắn hạn, dùng một lần** qua HTTPS; không gửi refresh token hoặc access token sống lâu trên query URL.

## 5. Origin trong WebSocket: khác hoàn toàn với CORS HTTP thông thường

Một trang tại:

```text
https://app.example.test
```

mở:

```text
wss://api.example.test/ws/chat
```

Browser thường gửi:

```http
Origin: https://app.example.test
```

`Origin` mô tả **nguồn gốc của trang gọi WebSocket**, thông thường gồm **scheme + host + port**. Nó không phải URI WebSocket, không có path/query, và không tự chứa user ID hoặc tenant ID.

### So sánh hai cơ chế

| Yếu tố | Fetch/XHR cross-origin | Browser WebSocket handshake |
| --- | --- | --- |
| Có `Origin`? | Thường có khi cần kiểm tra CORS | Browser thường gửi |
| Có preflight HTTP `OPTIONS`? | Có trong một số tình huống | **Không dùng CORS preflight thông thường** |
| Browser kiểm tra `Access-Control-Allow-Origin`? | Có theo CORS response semantics | **Không áp bộ kiểm tra CORS Fetch như XHR** |
| Server cần kiểm tra Origin? | CORS layer quyết định origin policy | **Phải kiểm tra Origin theo WebSocket security policy** |
| Cookie/credentials? | Phụ thuộc `fetch(credentials)` và cookie policy | Phụ thuộc browser cookie policy trên handshake; WebSocket constructor không có `credentials` option |
| Có thể mở từ trang web lạ? | Tùy CORS và server | Browser có thể **thử** mở; server phải từ chối Origin không được phép |

**Chốt:** Cấu hình `Access-Control-Allow-Origin` dành cho REST **không tự bảo vệ WebSocket**. Bật `globalcors` của Gateway cho `/ws/**` cũng không phải bằng chứng Origin WebSocket đã được kiểm tra đúng.

### Cross-Site WebSocket Hijacking (CSWSH)

Nếu một người đã login tại `api.example.test` bằng cookie phiên, họ ghé `https://evil.example.test`. Trang độc hại có thể thử:

```javascript
// Ví dụ hành vi cần bị chặn ở server, không phải code đề xuất dùng.
const ws = new WebSocket("wss://api.example.test/ws/private");
ws.onmessage = event => {
  // Trang không đáng tin sẽ cố đọc dữ liệu nếu server chấp nhận kết nối.
  console.log(event.data);
};
```

Nếu cookie phiên được browser gửi và server chỉ dựa vào cookie nhưng **không kiểm tra Origin**, trang độc hại có thể tận dụng session của người dùng để mở socket và đọc frames. Rủi ro gọi là **Cross-Site WebSocket Hijacking**.

SameSite cookie là lớp giảm thiểu quan trọng, nhưng **không được coi là thay thế Origin validation**. “Cùng site” khác “cùng origin”; subdomain hoặc browser policy có thể tạo trường hợp cookie vẫn được gửi. Hơn nữa, chính sách third-party cookie thay đổi giữa các trình duyệt.

### Origin allowlist không phải authentication

Header Origin có thể được **non-browser client giả mạo**, hoặc vắng mặt. Vì vậy:

1. Kiểm tra `Origin` để ngăn browser không đáng tin sử dụng cookie/session của người dùng.
2. **Đồng thời** xác thực user/token/ticket.
3. Kiểm tra user có quyền mở đúng channel/resource/tenant.
4. Xác định chính sách cho clients **không có Origin**; không mặc định coi chúng là hợp lệ nếu API cần browser-only.
5. Không coi `Origin: https://app.example.test` là bằng chứng user đang sở hữu tài khoản của ứng dụng đó.

## 6. Kiểm tra Origin sớm ở Gateway

Nếu Gateway proxy WebSocket tới backend, một cách thiết kế là kiểm tra Origin ở **WebFilter** trước khi route/WebSocket handshake được nâng cấp. Chọn allowlist origin cụ thể:

```text
Được phép:
  https://app.example.test
  https://admin.example.test

Không được phép:
  http://app.example.test
  https://evil.example.test
  https://app.example.test.evil.example
  Origin rỗng (trong chính sách browser-only ở ví dụ)
```

Không dùng phép so sánh `endsWith("example.test")` thiếu kiểm soát delimiter/IDN, vì `evil-example.test` có thể vượt qua. Nếu cần wildcard subdomains, phải parse origin URL chuẩn, xác định scheme/port và chỉ cho hostnames thực sự thuộc quản lý; hạn chế wildcard một cách chủ động.

### Mã WebFlux minh họa

```java
@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 10)
public final class WebSocketOriginGuard implements WebFilter {

    private static final Set<String> ALLOWED_ORIGINS = Set.of(
        "https://app.example.test",
        "https://admin.example.test"
    );

    @Override
    public Mono<Void> filter(ServerWebExchange exchange,
                             WebFilterChain chain) {
        ServerHttpRequest request = exchange.getRequest();

        boolean wsPath = request.getPath().value().startsWith("/ws/");
        boolean upgrade = "websocket".equalsIgnoreCase(
            request.getHeaders().getUpgrade());
        boolean handshake = wsPath
            && request.getMethod() == HttpMethod.GET
            && upgrade;

        if (!handshake) {
            return chain.filter(exchange);
        }

        String origin = request.getHeaders().getOrigin();
        if (origin == null || !ALLOWED_ORIGINS.contains(origin)) {
            exchange.getResponse()
                .setStatusCode(HttpStatus.FORBIDDEN);
            return exchange.getResponse().setComplete();
        }

        return chain.filter(exchange);
    }
}
```

Đây là **mẫu học thuật cho HTTP/1.1 Upgrade**: cần imports, review thứ tự filter, path matching, deployment proxy và error handling. Với hệ thống hỗ trợ cả **HTTP/2 extended CONNECT**, phải có chính sách nhận diện/kiểm tra request WebSocket qua cơ chế H2 tương ứng hoặc đảm bảo hạ tầng chỉ nhận H1 Upgrade theo contract; bộ kiểm tra chỉ nhìn `Upgrade` có thể **bỏ sót** một luồng khác. Nếu Spring WebSocket handler/backend đã có Origin policy, các lớp phải nhất quán, không dựa vào bất kỳ lớp nào một cách mơ hồ.

**Lưu ý thứ tự:** `WebFilter` có thể xử lý trước Gateway route matching; điều đó giúp từ chối handshake từ Origin lạ ngay khi nhận vào. Nhưng filter trên **không thực hiện authentication**. Security chain phía sau vẫn phải kiểm tra principal/permission.

### Không cho Origin đồng nghĩa tất cả subdomain

Ví dụ ứng dụng hoạt động tại `https://app.example.test`. Không khai báo wildcard rộng:

```text
https://*.example.test
```

nếu có subdomain cho khách hàng tự cung cấp HTML/JS hoặc subdomain bên thứ ba kiểm soát. Một website độc hại cùng parent domain có thể được trình duyệt coi là cùng site trong một số cookie rule, nên Origin allowlist cần đánh giá **quyền kiểm soát thực tế từng host**.

## 7. Cookie, phiên HTTP và `WebSocketSession`

Ba khái niệm thường bị trộn:

| Khái niệm | Vai trò | Vòng đời |
| --- | --- | --- |
| **Session cookie** | Browser gửi một định danh phiên trong HTTP handshake khi cookie policy cho phép | Tùy cookie expiry, logout và browser |
| **WebFlux `WebSession`** | Trạng thái phiên HTTP phía server, có thể dùng với OAuth2 login/BFF | Tùy session store/TTL và cơ chế lưu |
| **`WebSocketSession`** | Abstraction của **một kết nối WebSocket đã được nâng cấp** | Từ lúc 101 thành công đến khi close/disconnect |

**WebSocketSession ID không tự là HTTP session ID.** Một người dùng có thể mở nhiều tab, mỗi tab có WebSocket connection riêng nhưng cùng session cookie. Một Gateway/backend có thể có nhiều WebSocketSession gắn với cùng principal.

### Cookie có luôn được gửi không?

Không. Browser quyết định cookie eligibility dựa trên ít nhất:

- Cookie `Domain` có match host đích không?
- `Path` có match handshake URL không?
- `Secure` với `wss://`/HTTPS theo browser policy?
- `SameSite` và quan hệ site giữa trang và đích?
- Chính sách third-party cookies/chặn tracking của browser?
- Cookie còn hạn/chưa logout/chưa bị xóa?

Khi debug “login REST được nhưng WebSocket 401”, đừng mặc định Gateway đã nhận cookie. Hãy kiểm tra **handshake request headers** trong DevTools và session store ở môi trường thử nghiệm. Tránh copy giá trị session cookie thật vào ảnh chụp hoặc issue.

### Session-based BFF pattern

Một luồng phù hợp:

```mermaid
sequenceDiagram
    participant B as Browser
    participant G as Gateway BFF
    participant I as Identity Provider
    participant U as chat-service
    B->>G: HTTPS login
    G<->>I: OIDC authorization-code flow
    G-->>B: Set-Cookie: SESSION (Secure, HttpOnly, SameSite...)
    B->>G: WSS handshake + Origin + Cookie
    G->>G: Verify Origin + session + route authorization
    G->>U: Proxied WebSocket handshake
    U-->>G: 101 khi chấp nhận
    G-->>B: 101, kết nối được mở
```

Cookie phiên là credential để Gateway **tìm session**; nó không phải access token để backend tự xác minh bằng JWT. Nếu backend cần danh tính user, phải thiết kế propagation đáng tin: ví dụ token được phát hành đúng audience và được kiểm tra tại backend, hoặc một identity assertion có tính toàn vẹn trong mạng tin cậy.

**Không mặc định `TokenRelay` cho HTTP REST sẽ tự relay đúng OAuth2 authorized client/token trong mọi WebSocket handshake.** Cần test thực tế Gateway filter order, WebSocket routing handshake headers và backend validation. Token audience và scope vẫn phải đúng downstream.

## 8. Thông tin nào nên chuyển tiếp cho upstream?

Gateway thường cần giữ những trường liên quan đến WebSocket handshake, ví dụ URL và các header Upgrade/Subprotocol theo cơ chế proxy. Nhưng **không được giả định mọi header, cookie, principal hoặc token được chuyển nguyên vẹn** trong mọi bản Gateway. HTTP proxying và WebSocket proxying có thể dùng các bộ lọc/hook khác nhau.

### Phân loại trường

| Thông tin | Có thể xuất hiện ở handshake | Quy tắc thiết kế |
| --- | --- | --- |
| `Origin` | Browser gửi | Backend/Gateway kiểm tra policy, không coi là identity |
| `Cookie` | Khi browser cookie policy cho phép | Chỉ chuyển khi upstream thực sự cần và trust boundary cho phép |
| `Authorization` | Non-browser clients có thể gửi | Phải xác minh, có thể thay bằng token đúng audience |
| `Sec-WebSocket-Protocol` | Danh sách subprotocol đề nghị | Chỉ chọn subprotocol được hỗ trợ; không nhét bí mật |
| `Host` | Đích public của request | Proxy cần xử lý host/forwarded host đáng tin |
| `X-Forwarded-For/Proto/Host` | Proxy metadata | Chỉ tin do ingress được cấu hình/chấp thuận, không tin client tự khai |
| `X-User-Id/X-Tenant-Id` | Custom identity headers | **Không tin giá trị client có thể tự ghi** |
| `Sec-WebSocket-Key` | Phần handshake protocol | Không dùng như session/token |
| Query `ticket=...` | Ticket do ứng dụng thiết kế | Giới hạn TTL/use-once, che log và chống replay |

### Đừng forward raw cookie cho mọi backend

Nếu Gateway là BFF và session cookie chỉ dùng để xác thực với Gateway, backend chat có thể không cần cookie đó. Forward session ID tới một service khác có thể làm tăng phạm vi credential bị lộ và tạo coupling giữa hai hệ thống.

Nếu backend cần user identity, nên dùng:

- Token nội bộ đúng audience/scope do AS tin cậy cấp.
- Signed assertion được backend xác minh và giới hạn thời gian.
- Một service-to-service channel tin cậy kèm authorization riêng, **không** dựa duy nhất vào `X-User-Id`.

Tùy kiến trúc, backend WebSocket server cũng có thể tự xác thực cùng session/cookie, nhưng phải hiểu session store/trust boundary và đảm bảo không dùng cookie của Gateway một cách thiếu chủ đích.

### Token trong query dễ rò rỉ

Ví dụ cần tránh với long-lived access token:

```text
wss://api.example.test/ws/chat?access_token=<long-lived-token>
```

URL có thể bị lưu trong access log của Ingress/Gateway, APM trace, error report hoặc debugging tools. Nếu cần ticket trong URL do browser không đặt được Authorization header, hãy dùng **ticket sống rất ngắn**, một lần, ràng buộc user/tenant/resource, TLS, giới hạn replay và redaction query tại mọi tầng.

**Không gửi refresh token** trên handshake URL, subprotocol, hoặc WebSocket message chỉ để “giữ phiên lâu hơn”.

## 9. Authentication tại Gateway và authorization tại upstream là hai việc

Một handshake có thể xác thực principal “Alice” nhưng Alice **không có quyền vào phòng 42**. Nếu URL:

```text
wss://api.example.test/ws/chat/rooms/42
```

Gateway chỉ kiểm tra `authenticated()`, người dùng đã login có thể mở thử room khác. Cần authorization:

1. **Handshake-level:** User có quyền kết nối dịch vụ WebSocket và vào resource/tenant được chỉ định không?
2. **Message-level:** User có được subscribe kênh X, gửi message cho room Y hoặc thực hiện command Z không?
3. **Connection lifetime:** Khi quyền thay đổi, connection đang mở có phải bị hạn chế/đóng/re-authenticate không?

### Authn và authz cho từng resource

| Kiểm tra | Ví dụ | Nếu thiếu |
| --- | --- | --- |
| Authentication | Xác minh cookie/session/JWT/ticket | Anonymous kết nối vào endpoint private |
| Origin allowlist | Chỉ cho phép frontend do tổ chức kiểm soát | CSWSH qua browser có session |
| Tenant membership | User thực sự thuộc tenant trong route/room | Cross-tenant leak |
| Resource permission | User được vào chat room 42 | Đọc room của người khác |
| Topic/channel permission | User được subscribe `/topic/admin` hay không | Lộ message qua STOMP/subprotocol |
| Message rate/size | Giới hạn gửi frame và message | Spam, memory pressure |
| Revocation | User bị khóa/chuyển quyền | Socket cũ tiếp tục nhận dữ liệu |

**Gateway route `Path=/ws/chat/**` chỉ lựa chọn đích**, không phải resource authorization. Backend hoặc một dịch vụ authz đáng tin phải xác minh quyền theo room/topic mà người dùng muốn sử dụng.

## 10. STOMP hoặc protocol ứng dụng không tự giải quyết handshake

Một số hệ thống dùng **STOMP over WebSocket**. Có hai lớp khác nhau:

```text
HTTP/1.1 WebSocket handshake
    GET /ws/chat
    Origin, Cookie, Upgrade, ...
    -> 101 Switching Protocols

STOMP frames (sau 101)
    CONNECT
    SUBSCRIBE destination:/topic/rooms/42
    SEND destination:/app/chat/42
    ...
```

Header `Authorization` trong một **STOMP CONNECT frame** (nếu giao thức ứng dụng dùng) **không giống HTTP Authorization header lúc handshake**.

Hệ quả:

- Security WebFilter của Gateway có thể chặn HTTP handshake trước `101`.
- Nếu server cho phép handshake anonymous rồi chỉ xác thực STOMP CONNECT, socket đã được tạo trước khi credential ứng dụng được kiểm tra.
- Cần chặn SUBSCRIBE/SEND trước khi xác thực thành công.
- Phải kiểm tra quyền **từng destination/resource**, không chỉ một lần lúc CONNECT.
- Gateway WebSocket proxy thông thường **không tự hiểu hoặc phân quyền mọi STOMP frame**. Thường backend messaging layer chịu trách nhiệm.

Không giả định có Spring Security OAuth2 Resource Server cho HTTP là tự động bảo vệ tất cả destination của một message broker. Thiết kế bảo mật thông điệp phải kiểm thử riêng.

### WebSocket message không có Origin header

`Origin` chỉ thuộc **handshake HTTP request**. Sau `101`, WebSocket frames không mang HTTP headers như Origin/Cookie ở mỗi message. Backend có thể lưu principal trong session context và cần tự xác minh quyền cho mỗi message quan trọng.

Nếu quyền user bị thu hồi giữa chừng, handshake ban đầu không tự được chạy lại. Cần policy để **đóng socket, giảm quyền, refresh auth state hoặc revalidate khi dùng resource**.

## 11. Phiên hết hạn và logout khi socket vẫn đang mở

Một người dùng đăng nhập, mở WebSocket 30 phút, rồi phiên HTTP hết hạn sau 15 phút. Có nhiều thiết kế có thể xảy ra:

| Sự kiện | Điều không nên giả định | Chính sách cần thiết |
| --- | --- | --- |
| Cookie/session hết hạn | WebSocket tự đóng ngay | Quy định session max age/connection lifetime và revalidation |
| Logout trên tab khác | Tất cả sockets tự đóng | Server-side close theo principal/session, logout event handling |
| JWT hết hạn | Frames tự ngừng được truyền | Connection expiry/re-auth protocol, message-level authorization |
| Người dùng bị khóa | Gateway tự đẩy sự kiện tới mọi backend | Revocation fan-out hoặc recheck quyền |
| Tenant membership thay đổi | Topic đã subscribe tự bị hủy | Kiểm tra quyền lại và unsubscribe/close |
| Gateway replica restart | WebSocket tự chuyển instance | Reconnect, resume/replay event theo protocol |
| Backend rolling deploy | Active connection tự load balance lại | Drain và reconnect có backoff |

**WebSocketSession sống dài hơn HTTP request đã tạo nó.** Việc bảo mật phải có chiến lược xuyên suốt kết nối, không dừng tại `101`.

### Chủ động đóng kết nối không đồng nghĩa đã thu hồi dữ liệu gửi

Nếu một user đã nhận message nhạy cảm trước khi bị khóa, việc đóng socket sau đó không “thu hồi” nội dung đó. Vì thế authorization trước khi phát dữ liệu và response/message isolation vẫn là quan trọng nhất.

### Chiến lược reconnect

Client nên:

1. Phân biệt close bình thường và mất kết nối.
2. Sử dụng exponential backoff có jitter, giới hạn số lần thử/độ trễ.
3. Kiểm tra lại session/login trước khi reconnect khi lỗi liên quan auth.
4. Không retry vô hạn nếu server trả policy violation.
5. Dùng resume token/sequence number của **protocol ứng dụng** nếu cần khôi phục message bị bỏ lỡ, có kiểm tra quyền.
6. Không gửi lại message có side effect nếu không có idempotency/ack semantics.

## 12. Mã đóng WebSocket và HTTP status bắt tay

Phân biệt hai giai đoạn:

| Giai đoạn | Tín hiệu | Ý nghĩa ví dụ |
| --- | --- | --- |
| Trước upgrade | HTTP `101` | Handshake thành công |
| Trước upgrade | HTTP `401` | Thiếu hoặc sai credential |
| Trước upgrade | HTTP `403` | Origin không được phép hoặc thiếu authorization |
| Trước upgrade | HTTP `404` | Route/handler không tồn tại hoặc path sai |
| Trước upgrade | HTTP `426` | Server yêu cầu protocol upgrade theo contract |
| Trước upgrade | HTTP `502/503/504` | Gateway không proxy thành công/không có instance/upstream timeout |
| Sau upgrade | Close code `1000` | Đóng bình thường |
| Sau upgrade | Close code `1001` | Going away, ví dụ server rời/đóng |
| Sau upgrade | Close code `1008` | Policy violation theo ứng dụng |
| Sau upgrade | Close code `1009` | Message too big |
| Sau upgrade | Close code `1011` | Unexpected server condition |
| Sau upgrade | Close code `1013` | Try again later, theo convention/protocol hỗ trợ |
| Sau upgrade | Browser báo `1006` | Abnormal closure; **không phải mã được gửi trong close frame** |

**Không cố trả HTTP `401` sau khi server đã gửi `101`.** Lúc đó phải dùng close frame/protocol response được thiết kế, hoặc ngắt kết nối theo đúng tình huống. Browser có thể chỉ hiện “WebSocket connection failed” thay vì cung cấp status/detail HTTP từ constructor; xem DevTools Network handshake và server-side logs để biết nguyên nhân.

### 101 không có nghĩa business authorization thành công

Một `101` chỉ chứng minh kết nối WebSocket được thiết lập ở tầng protocol. Backend vẫn có thể từ chối message/subscribe và gửi close `1008` sau đó. Vì vậy test cần kiểm tra **cả handshake lẫn message authorization**.

## 13. CORS không sửa được Origin policy của WebSocket

Một lỗi cấu hình thường gặp:

```yaml
spring:
  cloud:
    gateway:
      globalcors:
        cors-configurations:
          '[/**]':
            allowedOrigins:
              - https://app.example.test
            allowedMethods:
              - GET
              - POST
```

Cấu hình này liên quan **CORS xử lý HTTP request kiểu browser fetch/XHR**. Nó **không được coi là bảo đảm tự động** rằng WebSocket handshake từ Origin lạ sẽ bị chặn đúng policy.

Đối với WebSocket:

- Kiểm tra Origin theo handshake policy ở ingress/Gateway và/hoặc backend.
- Xác thực session/token/ticket riêng.
- Kiểm tra permission theo room/tenant/topic.
- Không dựa vào `Access-Control-Allow-Origin` để browser tự bảo vệ như REST API.
- Không bật wildcard Origin với cookie/session chỉ để “connection hoạt động”.
- Không xem CORS `OPTIONS` preflight là điều kiện bắt buộc của browser WebSocket API.

Một `403` do Origin guard WebSocket trả về có thể là **hành vi bảo mật đúng**. Không xóa Origin validation để sửa lỗi handshake trước khi chứng minh frontend origin thật sự được tin cậy.

## 14. Spring Security, CSRF và cross-site requests

Đối với ứng dụng dùng **cookie phiên**, browser có thể tự gửi cookie ở WebSocket handshake nếu cookie policy cho phép. Điều này tạo rủi ro CSWSH như mục 5.

### Vì sao CSRF filter HTTP có thể chưa đủ?

Các thao tác thay đổi trạng thái qua HTTP `POST/PUT/PATCH/DELETE` thường được bảo vệ bởi CSRF tokens khi sử dụng cookie-based session. Nhưng WebSocket handshake HTTP/1.1 là **GET Upgrade** và **các message sau đó không đi qua HTTP CSRF filter như POST**.

Do đó không được giả định `csrf()` mặc định của Security đã kiểm tra đầy đủ mọi socket message. Cần Origin allowlist, authentication và message/resource authorization, và có thể cần CSRF token/handshake ticket hoặc chính sách riêng theo protocol ứng dụng.

Nếu dùng STOMP và framework có khả năng bảo vệ CONNECT bằng CSRF token, cần thiết lập đúng cho **message layer**; đừng nhầm với CORS header.

### SameSite cookie

- `SameSite=Strict` có thể hạn chế cookie ở những tình huống cross-site theo browser.
- `SameSite=Lax` cũng không đồng nghĩa chống mọi kịch bản WebSocket CSWSH.
- `SameSite=None; Secure` có thể cần cho thiết kế cross-site hợp lệ, nhưng làm tăng yêu cầu Origin validation và browser cookie policy.
- “Cùng site” và “cùng origin” là hai khái niệm khác nhau; hai subdomains có thể cùng site nhưng khác origin.

Trong mọi trường hợp, **server phải kiểm tra quyền độc lập với thuộc tính cookie**.

## 15. Ingress và reverse proxy: Upgrade, Origin và TLS

Gateway có thể đúng route/security nhưng browser vẫn không kết nối nếu ingress không hỗ trợ WebSocket Upgrade hoặc thay đổi headers sai.

### Các thành phần cần kiểm tra

| Điểm cấu hình | Lỗi thường gặp | Hậu quả |
| --- | --- | --- |
| HTTP/1.1 Upgrade support | Proxy không chuyển `Upgrade`/`Connection` | Không có 101, thường lỗi handshake |
| Proxy/read idle timeout | Đóng connection sau thời gian không có frame | Socket mất liên tục |
| TLS termination | HTTP/HTTPS/WS/WSS sai scheme | Browser chặn mixed content hoặc TLS error |
| SNI/hostname verification | Backend `wss://` không khớp certificate | Handshake outbound thất bại |
| `Origin` preservation | Proxy xóa/thay Origin | Origin allowlist từ chối hoặc bị bypass |
| `Host`/Forwarded headers | Tin client tự đặt `X-Forwarded-Host` | Sai public URL/tenant, host spoofing |
| Connection draining | Pod bị kill mà không drain | Disconnect hàng loạt |
| WAF/request limits | Block Upgrade/subprotocol hoặc URI dài | 403/4xx trước Gateway |
| WebSocket compression/frame sizes | Incompatible extension/limits | 101 xong rồi lỗi framing/size |

**Không dựa vào `X-Forwarded-Proto: https` do client gửi trực tiếp** để quyết định request an toàn; chỉ tin các forwarded headers được thiết lập bởi proxy đáng tin trong mạng đã cấu hình. Nếu public target là `wss://`, còn internal hop dùng `ws://`, xác nhận đó là lựa chọn bảo mật được phê duyệt, không phải downgrade ngoài ý muốn.

### Mẫu NGINX cấu hình hop-by-hop cho WebSocket

```nginx
# Minh họa riêng HTTP/1.1 Upgrade khi dùng NGINX.
# Cấu hình location, upstream, TLS và auth phải phù hợp triển khai thật.
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 443 ssl;
    server_name api.example.test;

    location /ws/ {
        proxy_pass http://gateway_internal;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header Origin $http_origin;
        proxy_read_timeout 3600s;
    }
}
```

Đây là **mẫu minh họa**, chưa có certificate directives, authentication, error handling, rate limits và cấu hình upstream thực. Không copy nó như cấu hình NGINX đầy đủ. `Origin` nên được giữ/kiểm tra theo policy; không tự thay bằng Origin “được phép” vì như vậy vô hiệu ý nghĩa phân biệt nơi request bắt nguồn.

## 16. Rate limiting WebSocket: handshake và frames là hai vấn đề

HTTP rate limiter của Gateway thường hoạt động ở **mức HTTP request**. Một WebSocket connection được mở thành công có thể gửi hàng nghìn messages sau một handshake, nhưng các frames sau đó **không đi qua pipeline HTTP request rate limiting như hàng nghìn GET riêng lẻ**.

Vì vậy cần hai lớp:

1. **Handshake admission:** giới hạn số kết nối mở mới theo principal/IP/tenant, kiểm tra auth và Origin trước upgrade.
2. **Active connection/message controls:** giới hạn số sockets đồng thời, frame/message size, tần suất gửi, subscriptions và buffered outbound messages.

| Mục tiêu | Chỉ dùng `RequestRateLimiter` cho handshake đủ không? |
| --- | --- |
| Giới hạn số lần mở socket mỗi giây | Có thể hữu ích nếu filter thực sự nằm trên route handshake |
| Giới hạn 10.000 messages/giây của một socket | **Không** |
| Ngăn một user mở quá nhiều sockets | Cần active-connection accounting |
| Chặn gửi dữ liệu vào topic không có quyền | Cần message-level authorization |
| Ngăn outbound slow consumer chiếm memory | Cần backpressure/buffer/close policy |
| Ngăn reconnect storm sau deploy | Handshake limits + jitter/backoff + drain |

Một route dùng `lb:ws://` sau 101 cần connection capacity planning; HTTP request QPS không phản ánh số active WebSocket sessions.

## 17. Retry và circuit breaker khi dùng WebSocket

### Không thể “retry mọi frame” như REST

Gateway `Retry` GatewayFilter Factory thường hướng đến **HTTP request/response attempts**. Với WebSocket:

- Một handshake bị từ chối `401/403` thường **không nên** retry nguyên request ngay.
- Nếu upstream trả kết nối thất bại trước upgrade, client có thể retry theo policy riêng.
- Sau `101`, socket mất giữa lúc gửi message không thể được “phát lại toàn bộ” bằng cách retry HTTP request mà vẫn giữ protocol semantics.
- Một message đã được backend xử lý có thể mất ACK; reconnect rồi gửi lại có nguy cơ side effects trùng.

Cần **application-level reconnect, ack/sequence numbers, idempotency và replay window** tùy protocol. Không thêm `Retry` vào WebSocket route rồi mặc định nó đảm bảo truyền message exactly-once.

### CircuitBreaker hữu ích nhưng có giới hạn

Circuit breaker có thể bảo vệ **handshake/upstream connect** nếu được tích hợp đúng vào ranh giới lỗi, nhưng số lỗi của WebSocket connection đã hoạt động lâu có thể không tương ứng với kết quả HTTP handshake. Timeout, close codes và network resets cần instrumentation riêng.

Nếu breaker OPEN, fallback trả JSON HTTP `503` có thể phù hợp để báo **handshake thất bại**, nhưng không thay thế một WebSocket server có thể tiếp tục gửi frames. Cần ghi rõ hợp đồng client khi connect thất bại.

### Service discovery và sticky state

Một WS connection có thể giữ trạng thái local trên instance B. Khi reconnect, LoadBalancer có thể chọn instance C. Nếu protocol yêu cầu tiếp tục phiên/topic state, cần state bên ngoài process (broker, Redis, durable streams...) hoặc thiết kế resume được xác thực. **Không coi sticky routing là yêu cầu tự động được Gateway đáp ứng** chỉ vì session cookie giống nhau.

## 18. Quan sát bắt tay nhưng không ghi lộ credential

Để chẩn đoán, cần ít nhất các trường:

| Dữ liệu | Giá trị |
| --- | --- |
| Timestamp và trace/correlation ID | Ghép frontend, Ingress, Gateway và backend |
| Gateway replica/pod ID | Xác định lớp nào xử lý socket |
| Route ID | `chat-websocket` hay route khác? |
| Public path/Host, HTTP method | Route predicates có khớp không? |
| Incoming `Origin` (đã canonicalize, kiểm soát) | Được policy cho phép hay từ chối? |
| Authentication result | Principal hợp lệ hay không; **không ghi token/cookie** |
| Tenant/resource context đã kiểm tra | User vào đúng room/tenant? |
| Handshake HTTP status | `101` hay `401/403/404/502/503` |
| Upstream service ID/selected instance | Proxy tới đâu? |
| TLS/proxy error category | SSL handshake/timeout/Upgrade mismatch |
| Active connections và close code | Socket sống bao lâu, đóng vì gì? |
| Reconnect rate và message rate | Phát hiện reconnect storm/abuse |

**Không ghi** raw `Cookie`, `Authorization`, handshake ticket, full query string chứa ticket, WebSocket payload chứa dữ liệu cá nhân hoặc raw session IDs. Khi cần phân tích một user cụ thể, dùng ID đã được ẩn danh/bảo vệ và audit phù hợp.

### Những chỉ số không thay thế nhau

- **HTTP 101 count**: số handshake nâng cấp thành công.
- **Active connections gauge**: số sockets đang tồn tại.
- **Handshake rejection count**: 401/403/404/5xx trước nâng cấp.
- **Close-code distribution**: cách socket kết thúc sau nâng cấp.
- **Message throughput/latency**: hành vi protocol sau nâng cấp.
- **Authorization denied messages**: không tương đương handshake failures.

Một HTTP access log có `101` không chứng minh client đã subscribe đúng room, và nhiều `1006` không tự chứng minh Origin sai; cần trace nhiều lớp.

## 19. Kiểm thử với browser DevTools

Trình duyệt là môi trường tốt để kiểm tra các hạn chế đặc thù:

```javascript
const socket = new WebSocket(
  "wss://api.example.test/ws/chat/rooms/42",
  ["chat.v1"]
);

socket.onopen = () => console.log("OPEN");
socket.onmessage = event => console.log("MESSAGE", event.data);
socket.onerror = () => console.log("ERROR");
socket.onclose = event =>
  console.log("CLOSE", event.code, event.reason, event.wasClean);
```

Trong DevTools → Network → WS, xem:

1. Request URL, scheme `wss`, path, host.
2. `Origin` của trang đang chạy.
3. Có cookie đủ điều kiện hay không (ẩn giá trị khi chia sẻ screenshot).
4. `Upgrade`, `Connection` và `Sec-WebSocket-Protocol`.
5. Status có `101` hay response lỗi.
6. Frames/message và close event sau 101.
7. Response có `Sec-WebSocket-Accept`/protocol được server chọn không.
8. Có các request/login redirect/HTTP errors liên quan không.

**Browser API có thể không cho JavaScript đọc chi tiết HTTP lỗi handshake.** Dùng Network trace và logs tại Ingress/Gateway/backend để xác định status, không dựa chỉ vào `socket.onerror`.

### Lưu ý về credentials

Không viết client browser với tham số `headers` cho WebSocket constructor; API không hỗ trợ. Nếu session cookie không được gửi, xem Domain/Path/SameSite/Secure và khác biệt origin/site, không cố bổ sung `Cookie` header bằng JavaScript.

## 20. Kiểm thử HTTP Upgrade sơ bộ bằng curl

Có thể gửi một HTTP/1.1 handshake để **quan sát response status và headers**:

```bash
curl --http1.1 -i --max-time 5 \
  -H 'Host: api.example.test' \
  -H 'Origin: https://app.example.test' \
  -H 'Connection: Upgrade' \
  -H 'Upgrade: websocket' \
  -H 'Sec-WebSocket-Version: 13' \
  -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' \
  https://api.example.test/ws/chat/rooms/42
```

Giá trị `Sec-WebSocket-Key` trong ví dụ là chuỗi test công khai, **không** phải token. Nếu server chấp nhận, có thể thấy `101` rồi curl kết thúc vì timeout; **timeout sau 101 không tự là handshake failure**.

Lệnh curl **không phải một WebSocket client đầy đủ** để kiểm thử gửi/nhận frames, ping/pong và subprotocol messaging. Dùng browser, `wscat`, `websocat` hoặc test client phù hợp để xác nhận connection lifecycle và message flow. Không chèn session cookie thật vào command line được ghi lịch sử.

### Không nhầm Origin với Host

`Host` trong ví dụ là Gateway target; `Origin` là nguồn trang. Không gửi `Origin: https://api.example.test` chỉ để làm test thành công nếu frontend thật chạy ở `https://app.example.test`. Một test giả Origin “đúng” nhưng không giống request thật có thể che lỗi allowlist.

## 21. Integration tests với Spring WebFlux và WebSocket client

Một test tốt cần chứng minh:

- Handshake từ Origin được phép + identity hợp lệ → socket thành công.
- Origin không được phép → **bị từ chối trước 101**.
- Chưa login hoặc token/ticket sai → **không thành công**.
- Đúng identity nhưng sai tenant/room → bị từ chối ở handshake hoặc message-level theo contract.
- Sau 101, quyền gửi/subscribe vẫn được kiểm tra.
- Upstream nhận path, subprotocol và identity **đúng thiết kế**, không phải các header giả mạo.

### Test client bằng `ReactorNettyWebSocketClient`

```java
@Test
void validOriginCanOpenSocket() {
    ReactorNettyWebSocketClient client =
        new ReactorNettyWebSocketClient();

    HttpHeaders headers = new HttpHeaders();
    headers.setOrigin("https://app.example.test");
    headers.set("Cookie", "SESSION=<test-session-value>");

    URI uri = URI.create(
        "ws://localhost:8080/ws/chat/rooms/42");

    StepVerifier.create(
            client.execute(uri, headers, session ->
                session.send(Mono.just(
                    session.textMessage("ping")))
                    .then(session.receive().next())
                    .then()))
        .verifyComplete();
}
```

Đoạn test là **khung minh họa**, cần test session store hợp lệ, backend WebSocket stub, imports, version-compatible API và server echo/response thích hợp. Giá trị cookie trong ví dụ là placeholder test, không phải session được cấp bởi server. **Không nên kết luận nó là test authentication hoàn chỉnh** nếu không thực sự tạo session/principal và xác minh quyền.

### Test Origin bị từ chối

```java
@Test
void disallowedOriginCannotCompleteHandshake() {
    ReactorNettyWebSocketClient client =
        new ReactorNettyWebSocketClient();

    HttpHeaders headers = new HttpHeaders();
    headers.setOrigin("https://evil.example.test");

    URI uri = URI.create(
        "ws://localhost:8080/ws/chat/rooms/42");

    StepVerifier.create(
            client.execute(uri, headers, session ->
                Mono.empty()))
        .expectError()
        .verify();
}
```

Test chỉ minh họa việc handshake không thành công; khi chạy thật nên assert **HTTP 403** (hoặc status đã định nghĩa), xem upstream request count **bằng 0**, và kiểm tra reject xảy ra tại Origin guard trước upgrade. Một lỗi TCP cũng làm `expectError()` pass nhưng không chứng minh Origin policy; vì vậy cần xác minh error type/status hoặc log/tầng stub riêng.

### Nếu dùng Spring Security WebTestClient

`WebTestClient` phù hợp để test **HTTP policy và handshake rejection** trong một số fixture, nhưng để test **full WebSocket frame exchange** nên dùng WebSocket client thực. Không coi `webTestClient.get().exchange().expectStatus().isOk()` là test thành công vì handshake đúng thường trả `101`, không phải HTTP `200`.

## 22. Ma trận kiểm thử toàn diện

| ID | Đầu vào / tình huống | Kỳ vọng |
| --- | --- | --- |
| T1 | Browser origin hợp lệ, login session hợp lệ | Handshake 101, socket mở |
| T2 | Browser origin lạ, session hợp lệ | Từ chối trước upgrade, không proxy upstream |
| T3 | Origin bị thiếu theo policy browser-only | Từ chối hoặc xử lý theo chính sách đã công bố |
| T4 | Không có cookie/session | 401/redirect theo auth contract, không 101 |
| T5 | Cookie hết hạn | Không được xem là user đã login |
| T6 | Cookie có `SameSite`/`Path` không khớp | Browser không gửi; debug đúng cookie policy |
| T7 | Login BFF rồi mở WebSocket | Principal đúng, không cần JS thêm Authorization |
| T8 | Non-browser gửi Bearer hợp lệ | Security xác minh và chỉ cho quyền phù hợp |
| T9 | Non-browser gửi Origin giả nhưng không có auth | Không được cấp quyền |
| T10 | Query có long-lived access token | Policy bác bỏ thiết kế không an toàn |
| T11 | One-time ticket hợp lệ | Sử dụng đúng một lần, TTL/resource binding |
| T12 | Ticket reuse/hết hạn | Không cho mở lại socket |
| T13 | User thuộc tenant Alpha mở room Beta | Bị từ chối theo permission |
| T14 | User đã vào room nhưng gửi message tới topic admin | Message-level authz từ chối |
| T15 | User logout/revoked sau 101 | Server áp recheck/close policy |
| T16 | `Sec-WebSocket-Protocol` không được hỗ trợ | Handshake/negotiation xử lý đúng protocol |
| T17 | Ingress bỏ `Upgrade` | Không nâng cấp; xác định lỗi proxy |
| T18 | Ingress sửa/loại `Origin` | Origin policy không bị bypass |
| T19 | Upstream `lb:ws://` không có instance | Phân biệt discovery/no-instance với auth failure |
| T20 | Backend WSS certificate sai | TLS verification từ chối, không bypass |
| T21 | Gateway route `StripPrefix` sai | Test phát hiện upstream path lệch |
| T22 | Route WebSocket có `Method=POST` | Handshake HTTP/1.1 GET không match |
| T23 | Nhiều Gateway replicas, session store local | Phát hiện login/socket ngẫu nhiên 401 |
| T24 | Backend instance được drain | Active sockets đóng, reconnect có backoff |
| T25 | Nhiều clients reconnect cùng lúc | Kiểm soát handshake rate/active sockets |
| T26 | Message quá lớn/slow consumer | Giới hạn size/buffer và close policy |
| T27 | HTTP 101 nhưng message authz fail | Không nhầm thành kết nối được phép mọi topic |
| T28 | Client cancel giữa handshake | Không giữ tài nguyên/subscriptions rò rỉ |
| T29 | TokenRelay được cấu hình trên WS route | Test chính header/token backend nhận theo version |
| T30 | JWT/permission bị thu hồi | Không tiếp tục phân phối dữ liệu riêng vô thời hạn |

Test bảo mật phải kiểm tra **negative cases**. Một socket hoạt động trong happy path không nói gì về rủi ro CSWSH, cross-tenant leak hoặc phiên cũ còn quyền.

## 23. Runbook khi WebSocket không kết nối qua Gateway

### Triệu chứng: browser báo “WebSocket connection failed”

Thực hiện theo thứ tự:

1. **Xem Network → WS**: Request có được phát ra không? URL scheme `ws`/`wss`, host/path đúng không?
2. **Kiểm tra HTTP status handshake**: `101`, `401`, `403`, `404`, `502`, `503`, hoặc redirect?
3. **Nếu 401/redirect:** cookie/session/JWT/ticket có hợp lệ; browser thực sự gửi cookie không?
4. **Nếu 403:** Origin allowlist, tenant/room authorization, WAF hoặc Security policy nào từ chối?
5. **Nếu 404:** Route `Path`/`Method` đã match chưa, route URI `lb:ws://` đúng không, `StripPrefix` có làm sai path không?
6. **Nếu 502/503/504:** kiểm tra instance discovery, backend WebSocket handler, TLS trust/hostname, TCP connect và response timeout.
7. **Nếu không có Upgrade/101:** kiểm tra Ingress hỗ trợ HTTP/1.1 WebSocket Upgrade và các hop-by-hop headers.
8. **Nếu 101 rồi đóng ngay:** kiểm tra subprotocol, message authentication, close code, broker subscription và server-side exception.
9. **Nếu chỉ một số users/replicas bị lỗi:** so sánh WebSession/authorized client store, cookie attributes, origin/path config, Gateway replicas.
10. **Nếu lỗi sau thời gian dài:** proxy idle timeout, ping/pong, session expiry, permission revoke, pod drain, connection capacity.
11. **Sau khi sửa:** chạy lại test origin hợp lệ/bị cấm, anonymous, tenant boundary, 101, messages và reconnect.

### Bảng chẩn đoán nhanh

| Hiện tượng | Nơi ưu tiên xem | Tránh làm |
| --- | --- | --- |
| WebSocket `401` nhưng REST login OK | Cookie scope/SameSite, route Security context | Nhét raw token vào URL |
| WebSocket `403` với Origin lạ | Origin allowlist và CSWSH policy | Đổi thành wildcard mà không xem trust |
| HTTP CORS đã bật nhưng WS vẫn fail | WebSocket Origin policy/handshake | Giả định CORS preflight bảo vệ WS |
| Không lên `101` | Ingress Upgrade/TLS/Gateway route | Chỉ tăng retry |
| `101` rồi `1008` | Message authz/subprotocol policy | Kết luận handshake 101 đã đủ bảo mật |
| Một Gateway replica login được, replica khác 401 | Shared WebSession/store, sticky routing | Bỏ qua session architecture |
| Route `lb://` hiện hữu nhưng WebSocket fail | Scheme `lb:ws://`, routing filter | Kết luận service discovery sai ngay |
| WSS certificate lỗi | TLS/SNI/trust chain | Tắt certificate verification |
| WS bị ngắt khi deploy | Draining và reconnect protocol | Mong connection tự chuyển pod |
| User Alpha thấy message tenant Beta | Resource/message authorization | Chỉ sửa Origin |
| Lỗi chỉ khi socket idle lâu | Proxy idle timeout, ping/pong, session lease | Tăng timeout vô hạn không đo tải |
| Token đã expire nhưng socket vẫn nhận data | Long-lived authorization/revocation | Chỉ kiểm tra JWT khi handshake |

## 24. Bài tập tình huống: chat đa tenant phía sau Gateway

Hệ thống SaaS có:

- Frontend tại `https://app.example.test`.
- Public WebSocket endpoint `wss://api.example.test/ws/chat/rooms/{roomId}`.
- Spring Cloud Gateway Server WebFlux với nhiều replicas.
- Spring Security OAuth2 login lưu phiên server-side; browser dùng `SESSION` cookie.
- Backend `chat-service` chạy nhiều instances qua `lb:ws://chat-service`.
- Mỗi room thuộc một tenant; user chỉ được đọc/gửi tin nhắn trong rooms được phân quyền.
- Một subdomain dành cho khách hàng tự quản lý nội dung: `https://pages.example.test`.

### Yêu cầu A — Cấu hình route

```yaml
spring:
  cloud:
    gateway:
      routes:
        - id: chat-websocket
          uri: lb:ws://chat-service
          predicates:
            - Path=/ws/chat/**
            - Method=GET
          filters:
            - StripPrefix=1
```

Kiểm tra `/ws/chat/rooms/42` sẽ thành `/chat/rooms/42` ở backend; đảm bảo backend thực sự xử lý path đó. Sự có mặt của `Method=GET` không cấp quyền truy cập; cần Security/Origin guard riêng.

### Yêu cầu B — Origin allowlist

Chỉ chấp nhận `https://app.example.test` và các frontend operator được kiểm soát. **Không** tự cho `https://pages.example.test` vì khách hàng có thể đưa JavaScript của riêng họ lên host đó. Với cookie session, cần ngăn website này sử dụng quyền của user khác để mở private socket.

### Yêu cầu C — Session

Thiết kế shared session store hoặc cơ chế session continuity rõ ràng giữa các Gateway replicas. Cookie phải có `Secure`/`HttpOnly` và SameSite phù hợp; không đưa session ID vào URL. Khi user logout, hệ thống phải có chính sách đóng socket hoặc ngừng phát messages theo danh tính đã bị thu hồi.

### Yêu cầu D — Authorization

Ngay cả khi handshake `101` thành công, backend phải xác minh user thuộc tenant chứa room 42, có quyền SUBSCRIBE/SEND và không thể đổi destination để truy cập room khác. Nếu user bị rút quyền, subscription/socket phải được xử lý theo chính sách revocation.

### Yêu cầu E — Vận hành

Đo active connection count theo Gateway replica, handshake success/rejection, `Origin` allow/deny, HTTP 101, close codes, reconnect rate, backend selected instance và message failures. Không log cookies, token hoặc nội dung chat nhạy cảm.

### Câu hỏi tự kiểm tra

1. `Sec-WebSocket-Key` và `Authorization` khác nhau về vai trò gì?
2. Vì sao JavaScript `new WebSocket(url, {headers: ...})` không đặt được Bearer header?
3. Browser có gửi preflight CORS `OPTIONS` trước WebSocket handshake như `fetch` không?
4. Vì sao `Access-Control-Allow-Origin` không đủ để bảo vệ WebSocket?
5. CSWSH lợi dụng cookie phiên và Origin policy thiếu sót như thế nào?
6. Origin hợp lệ có chứng minh user đã đăng nhập không?
7. Vì sao cần kiểm tra tenant/room quyền ngay cả khi `.authenticated()` đã pass?
8. `WebSession` và `WebSocketSession` khác nhau ở điểm nào?
9. Khi `101` đã gửi, có thể trả thêm HTTP `401` để từ chối message không?
10. `1006` có thể được server gửi trực tiếp dưới dạng close frame không?
11. Vì sao một client dùng HTTP GET thường không phải là một WebSocket test đầy đủ?
12. Khi dùng `lb:ws://`, LoadBalancer có chọn instance khác cho mỗi frame không?
13. Vì sao Proxy `Upgrade`/`Connection` cần hỗ trợ riêng cho HTTP/1.1?
14. Điều gì xảy ra khi cookie `SameSite`/`Path` không cho phép browser gửi trong handshake?
15. Vì sao session HTTP hết hạn không mặc nhiên ngắt WebSocket đang mở?
16. `TokenRelay` trên route WebSocket có được mặc định coi là token propagation đúng audience không?
17. Vì sao thêm `Retry` không đảm bảo message WebSocket được giao exactly-once?
18. Những metric nào phân biệt lỗi handshake trước `101` và lỗi message sau `101`?
19. Một user có hai tab mở có thể có bao nhiêu WebSocketSession so với HTTP session?
20. Khi client reconnect sau rolling deploy, làm sao tránh lặp message nghiệp vụ hoặc mất quyền truy cập?

**Ghi nhớ:** WebSocket bắt đầu là một **HTTP handshake**, vì vậy cần xác thực principal, kiểm tra **Origin allowlist** và phân quyền resource **trước `101 Switching Protocols`**; sau nâng cấp, mỗi message/topic vẫn cần authorization và connection-lifetime policy riêng. Browser WebSocket API không cho phép tùy ý đặt Authorization header; **cookie phiên/BFF** hoặc **ticket ngắn hạn một lần** là những mô hình cần cân nhắc, cùng với bảo vệ CSWSH. Trong Spring Cloud Gateway, định tuyến đúng `ws/wss`/`lb:ws://`, proxy Upgrade/TLS đúng, quản lý WebSession/WebSocketSession, kiểm thử multi-tenant và giám sát reconnect/close codes mới tạo được một cổng WebSocket an toàn.

