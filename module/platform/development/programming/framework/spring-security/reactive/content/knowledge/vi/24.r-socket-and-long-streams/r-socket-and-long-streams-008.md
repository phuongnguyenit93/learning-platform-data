# Ranh giới giữa danh tính kết nối WebSocket và phân quyền từng thông điệp

> **Ngữ cảnh:** Spring Security Reactive (Spring WebFlux), WebSocket và các kết nối/luồng sống lâu; liên hệ với RSocket và STOMP khi cần. Bài phân biệt **authentication tại HTTP Upgrade handshake** với **authorization trên từng lệnh, subscription, sự kiện hoặc dữ liệu trả về** sau khi WebSocket đã mở. Ví dụ minh họa Java 17+, Spring Boot 3.3.13 và Spring Security 6.x. Bản Boot này chỉ dùng để trình bày API; khi triển khai năm 2026, chọn phiên bản còn được hỗ trợ và đã áp dụng bản vá bảo mật.

## 1. Bài toán: một kết nối, nhiều yêu cầu khác quyền

Ứng dụng quản lý phòng cộng tác có hai phòng riêng tư `alpha` và `beta`. Alice được phép đọc/ghi `alpha`; Bob chỉ được phép đọc/ghi `beta`. Cả hai đều có thể **xác thực thành công** để mở WebSocket:

```text
Alice -- GET /ws/rooms + HTTP Upgrade + credential --> WebFlux
             |
             +-- HTTP SecurityWebFilterChain:
             |     kiểm danh tính Alice
             |     cho phép mở WebSocket (101 Switching Protocols)
             |
             +==================== kết nối đã nâng cấp ====================+
             |                                                           |
             | Alice gửi READ|alpha    -> kiểm quyền phòng alpha -> ALLOW |
             | Alice gửi READ|beta     -> kiểm quyền phòng beta  -> DENY  |
             | Alice gửi WRITE|beta|x  -> kiểm quyền beta         -> DENY  |
             | Alice bị thu hồi alpha  -> registry quyền thay đổi         |
             | Alice gửi READ|alpha    -> kiểm quyền LẠI         -> DENY  |
             |                                                           |
             +==================== đóng kết nối ===========================+
```

**Điểm khác nhau về bảo mật:**

1. **Authentication của kết nối:** “Client nào đang ở đầu bên kia? Credential lúc bắt tay HTTP có hợp lệ không?”
2. **Authorization của thông điệp:** “Đúng người đó, vào đúng thời điểm đó, có được thực hiện thao tác này với phòng/bản ghi/tenant này không?”
3. **Authorization của subscription/output:** “Người đó có được nhận **mọi sự kiện tiếp theo** từ stream này, kể cả sau khi quyền thay đổi không?”

Nếu chỉ kiểm `authenticated()` ở `GET /ws/rooms`, rồi xử lý mọi frame như đã được cho phép, bạn có thể tạo lỗi **Broken Object Level Authorization (BOLA/IDOR)** hoặc rò dữ liệu giữa tenants.

## 2. WebSocket khác HTTP request-response

HTTP thông thường:

```text
GET /api/rooms/alpha -> Security filters -> Controller -> 200
GET /api/rooms/beta  -> Security filters -> Controller -> 403
```

Mỗi HTTP request mới đi qua Security filter chain, được authentication/authorization theo policy của request đó.

WebSocket:

```text
GET /ws/rooms + Upgrade -> HTTP security (một lần tại handshake)
                           |
                           v
                         HTTP 101
                           |
                    WebSocketSession
                           |
                 Flux<WebSocketMessage> receive()
                           |
             READ|alpha, READ|beta, WRITE|...
                           |
              mã xử lý message do ứng dụng viết
```

Sau HTTP 101, các message chạy trên kết nối đã nâng cấp. **Chúng không trở thành những HTTP request `GET/POST` mới** để `ServerHttpSecurity.authorizeExchange().pathMatchers(...)` tự chạy lại trên từng frame. Một URL handshake có thể mang hàng trăm nghìn lệnh nghiệp vụ với quyền khác nhau.

Theo Spring Framework WebFlux, `WebSocketHandler.handle(WebSocketSession)` trả `Mono<Void>`; `session.receive()` trả `Flux<WebSocketMessage>` và `session.send(Publisher<WebSocketMessage>)` xuất thông điệp. Những API này xử lý **transport**; chúng không tự định nghĩa quyền `READ_ROOM` hay `DELETE_DOCUMENT`.

### 2.1 Hai tầng, hai câu hỏi

| Tầng | Nguồn kiểm tra | Điều chứng minh | Điều chưa chứng minh |
|---|---|---|---|
| HTTP Upgrade handshake | `SecurityWebFilterChain`, authentication filter, HTTP authorization | Client có identity hợp lệ, được mở endpoint `/ws/rooms` | Được đọc mọi room, gửi mọi event hay subscribe mọi channel |
| Connection identity | `WebSocketSession.getHandshakeInfo().getPrincipal()` | Principal gắn với request handshake | Quyền đó vẫn còn hiệu lực sau nhiều giờ; tất cả message đều hợp lệ |
| Inbound message policy | Service/authorization policy, current ACL, tenant/room ownership | Một operation cụ thể trên resource cụ thể được phép | Tự động có quyền với operation/resource khác |
| Outbound stream policy | Subscription authorization và kiểm tra quyền khi phát | Client có quyền nhận một event tại thời điểm phát | Quyền sẽ tồn tại vĩnh viễn |
| Database/service enforcement | Repository query có tenant/owner predicate, transaction | Đối tượng thực và mutation được bảo vệ | Proxy/handshake đủ an toàn mà không cần kiểm dữ liệu |

**Nguyên tắc:** `authenticated()` xác định identity, không thay thế kiểm quyền từng object, action, room hoặc tenant.

## 3. Danh tính tại WebFlux handshake nằm ở đâu?

Trong Spring Framework WebFlux, `WebSocketSession` có `getHandshakeInfo()`. `HandshakeInfo` cung cấp metadata của HTTP request mở kết nối:

```java
Mono<Principal> principal =
    session.getHandshakeInfo().getPrincipal();
```

- Phương thức `getPrincipal()` trả **`Mono<Principal>`**, không trả trực tiếp `Principal` hay Servlet `HttpServletRequest`.
- Principal do cơ chế authentication của HTTP handshake cung cấp; ví dụ session cookie đã xác thực, HTTP Basic của Java client, hoặc bearer JWT được Resource Server kiểm khi Upgrade.
- Nếu `Mono` rỗng, không nên dựng identity giả từ `Origin`, `Host`, `X-User` hoặc payload client.
- `Principal.getName()` là tên identity theo authentication provider. Trong hệ thống đa issuer/tenant, có thể cần khóa ổn định `issuer + subject + tenant` chứ không chỉ username/email.
- `HandshakeInfo` chứa headers/cookies của handshake, **không nên log hoặc truyền toàn bộ sang business code**: có thể lộ Authorization/cookie.

Một dạng xử lý:

```java
@Override
public Mono<Void> handle(WebSocketSession session) {
    return session.getHandshakeInfo().getPrincipal()
        .switchIfEmpty(Mono.error(
            new IllegalStateException("Missing handshake principal")))
        .flatMap(principal -> {
            Flux<WebSocketMessage> replies = session.receive()
                .map(WebSocketMessage::getPayloadAsText)
                .concatMap(text -> authorizeAndHandle(
                    principal.getName(), text))
                .map(session::textMessage);

            return session.send(replies);
        });
}
```

**Đây là mảnh phương thức**, chưa có định nghĩa `authorizeAndHandle`/imports và giả định chỉ text frames. Dự án đầy đủ ở mục 11 xử lý các frame không phải text. Quan trọng nhất là nhận principal tại handshake nhưng **kiểm quyền ở mỗi lần `concatMap` nhận message**.

### 3.1 Handshake HTTP SecurityWebFilterChain

Ví dụ:

```java
return http
    .authorizeExchange(exchanges -> exchanges
        .pathMatchers(HttpMethod.GET, "/ws/rooms").authenticated()
        .anyExchange().denyAll())
    .httpBasic(Customizer.withDefaults())
    .build();
```

Nếu WebSocket handshake là GET được Spring Security bảo vệ, client thiếu credential hợp lệ bị chặn **trước 101**, thông thường bằng 401 với Basic challenge hoặc entry point tương ứng. Sau khi thành công, frame `READ|beta` không đi qua matcher HTTP `GET /ws/rooms` lần nữa.

**Không** dùng `permitAll("/ws/**")` rồi tự tin rằng mọi kết nối có Principal. Nếu có thể mở anonymous handshake theo thiết kế, handler phải áp luật anonymous riêng, không cho các operation private chạy.

### 3.2 WebSocket `wss://` và identity

`wss://` dùng TLS cho kết nối WebSocket, chống nghe lén và MITM phù hợp mô hình TLS. Nó **không** chứng minh end-user đã đăng nhập, và không cấp quyền đọc phòng. Trên production nên dùng `wss://`, certificate hợp lệ, chính sách proxy upgrade/idle timeout và cookie Secure.

## 4. Mô hình mối đe dọa: “đã vào phòng chat” không đồng nghĩa “xem mọi tin”

Bốn dạng lỗ hổng:

**A — BOLA/IDOR:** Alice mở WebSocket thành công rồi gửi `READ|beta`. Nếu server chỉ tin identity chung, dữ liệu beta bị lộ.

**B — Command spoofing:** Alice gửi `ADMIN_DELETE|room=beta`. Nếu client tự khai `"role":"ADMIN"` trong JSON và server tin, có thể thực thi lệnh admin.

**C — Subscription leak:** Alice subscribe `/topic/tenants/beta/events` hoặc `room:beta`, nhận dữ liệu Bob dù message đầu tiên không được cấp quyền.

**D — Quyền bị thu hồi trong kết nối dài:** Alice lúc 09:00 có quyền alpha; lúc 09:05 admin thu hồi. Kết nối vẫn sống đến 17:00; nếu server chỉ check lúc connect, Alice tiếp tục nhận/ghi dữ liệu.

Bảo vệ tương ứng:

- Authentication tại handshake.
- **Policy trên mỗi message**: kiểm operation, resource ID, current user/tenant, scope/role.
- **Policy trên subscription và mỗi event delivery**: không chỉ cho phép tên channel.
- TTL/reauthentication và revoke/close strategy cho phiên dài.
- Data-layer enforcement theo tenant và owner trong truy vấn/mutation.

### 4.1 Đừng tin những trường “do client nói”

```json
{
  "type": "READ_ROOM",
  "roomId": "beta",
  "userId": "alice",
  "role": "ADMIN",
  "tenant": "beta"
}
```

Client có thể sửa **toàn bộ** các trường trong message body. Nếu xử lý theo JSON, chỉ dùng `roomId`/`type` làm **yêu cầu hành động**; lấy identity/role/tenant từ authentication đã xác minh và policy server-side. Các trường `userId`, `role`, `tenant` do client đưa **không** là bằng chứng được ủy quyền.

Một response an toàn khi vi phạm quyền có thể là:

```json
{"type":"ERROR","code":"FORBIDDEN","requestId":"r123"}
```

Không trả nguyên stacktrace, danh sách room riêng tư hay claims nhạy cảm để giải thích quá chi tiết cho client.

## 5. Authentication một lần, authorization nhiều lần

### 5.1 Thời điểm xác thực

```text
t0: HTTP handshake
    validate session/Bearer/Basic -> Principal Alice
t1: message READ(alpha)
    ACL(current user=Alice, room=alpha, action=READ) -> true
t2: message READ(beta)
    ACL(current user=Alice, room=beta, action=READ) -> false
t3: admin revokes Alice's access to alpha
t4: message READ(alpha)
    ACL(current user=Alice, room=alpha, action=READ) -> false
t5: WebSocket closes/reconnects (nếu chính sách yêu cầu)
```

**Cần phân biệt:** per-message authorization có thể dựa vào **danh tính cố định** tại handshake nhưng quyền hiện tại phải được kiểm lại khi operation xảy ra. Nếu identity của kết nối hết hạn hoặc bị vô hiệu hóa, ứng dụng phải chủ động đóng socket/reauth, vì việc token/cookie hết hạn **không bảo đảm** WebSocket đã mở sẽ tự động đóng.

### 5.2 Khi nào cần re-authenticate mỗi message?

Không phải mọi frame phải tự mang một bearer token mới. Có vài mô hình:

| Mô hình | Phù hợp | Cần làm thêm |
|---|---|---|
| **Handshake authentication + per-message current ACL** | Một browser user trên một WebSocket, lifetime hữu hạn | Giới hạn thời gian session, revocation, kiểm scope/room mỗi frame |
| **Reauthenticate định kỳ / khi privilege đổi** | Kết nối rất dài, quyền nhạy cảm | Close/reconnect với credential mới, hoặc protocol reauth được thiết kế chặt |
| **Mỗi request/message có metadata credential** | Một connection đại diện nhiều end users, ví dụ RSocket BFF | Mỗi payload phải validate token và map user chính xác |
| **Token exchange/OBO cho downstream** | Gateway gọi API có audience khác | Authorization Server cấp token mới đúng audience; không chuyển ID Token |
| **Anonymous WebSocket cho public feed** | Chỉ dữ liệu công khai | Origin/rate-limit, không cho private subscription hay mutation |

### 5.3 Kết nối dùng chung cho nhiều người

Một microservice có thể giữ **một** WebSocket/RSocket connection tới backend và multiplex request của Alice/Bob. Trong trường hợp này, principal của **connection** có thể là service account, **không phải** end-user. Nếu backend cần kiểm quyền Alice/Bob, phải có **delegated identity** trên từng operation (token đã được AS cấp đúng audience, metadata per request trong RSocket hoặc hợp đồng auth khác có kiểm chứng). Không tự truyền `X-User: alice` trong payload rồi coi đó là principal của Alice.

## 6. Quyền được kiểm vào những thời điểm nào?

| Điểm xử lý | Ví dụ | Câu hỏi bảo mật |
|---|---|---|
| Handshake | `GET /ws/rooms` | User có quyền mở connection không? Origin/TLS/credentials đúng? |
| Join hoặc subscribe | `SUBSCRIBE|alpha` | User có được đăng ký luồng alpha không? |
| Inbound read | `READ|alpha` | User có quyền xem dữ liệu alpha **lúc này** không? |
| Inbound write | `WRITE|alpha|...` | User có quyền sửa và payload hợp lệ không? |
| Publish/broadcast | Event từ business service | Danh sách recipients có đang được quyền nhận data? |
| Subscription lifetime | Sau khi user bị revoke | Tiếp tục cho nhận event, drop event, hay ngắt stream? |
| Data access | SQL/R2DBC query | Query đã gắn tenant/owner predicate chưa? |
| Reconnect | Handshake mới | Credential cũ còn hợp lệ không; permissions/Origin đã thay đổi? |
| Disconnect/logout | Logout hoặc admin revoke | Có đóng những socket active tương ứng không? |

Một subscription ban đầu được cho phép **không** chứng minh user được nhận mọi update mãi mãi. Với event nhạy cảm, kiểm quyền **ngay trước phát** hoặc hủy subscription khi revoke. Nếu chỉ lọc tin nhắn gửi vào mà bỏ qua outgoing fan-out, có thể vẫn rò dữ liệu.

## 7. WebSocket Origin, cookies và CSWSH

**Cross-Site WebSocket Hijacking (CSWSH)** có thể xảy ra khi một website bên ngoài mở WebSocket đến app của bạn và browser tự đính kèm cookie phiên được phép. Nếu app chỉ dựa vào cookie và không giới hạn origin, website tấn công có thể trao đổi các frame như người dùng.

Những điểm then chốt:

1. Browser WebSocket handshake có thể chứa `Origin`. Server phải kiểm Origin **allowlist** phù hợp với trang được phép kết nối.
2. WebSocket **không bị áp dụng y hệt CORS fetch**; không coi cấu hình `Access-Control-Allow-Origin` của REST API là bảo vệ WebSocket mặc định. Dùng WebSocket handshake origin policy của framework.
3. Kiểm Origin là biện pháp bảo vệ browser; **non-browser clients có thể tự giả Origin**, nên Origin không phải authentication.
4. Cookie `SameSite`, `Secure`, `HttpOnly`, session timeout và CSRF design tiếp tục quan trọng; **đừng** dùng Origin thay xác thực và quyền message.
5. HTTP CSRF filter thường tập trung vào unsafe methods. WebSocket Upgrade bắt đầu bằng GET; việc CSRF filter không chặn GET **không đồng nghĩa** WebSocket chống CSWSH.
6. Không dùng `allowedOrigins("*")` cho WebSocket cookie-authenticated private nếu không có lý do và kiểm soát riêng.

### 7.1 Một cách cấu hình Origin trên WebFlux WebSocket mapping

Spring Framework hướng dẫn dùng `CorsConfigurationSource` trên `WebSocketHandler` hoặc `corsConfigurations` trên `SimpleUrlHandlerMapping` để đặt allowed origins cho handshake. Mảnh ý tưởng:

```java
CorsConfiguration allowed = new CorsConfiguration();
allowed.setAllowedOrigins(List.of(
    "https://portal.example.com"));

SimpleUrlHandlerMapping mapping = new SimpleUrlHandlerMapping(
    Map.of("/ws/rooms", webSocketHandler), -1);
mapping.setCorsConfigurations(Map.of(
    "/ws/rooms", allowed));
```

Đây là **mảnh cấu hình** cần imports và được quản lý theo môi trường. Dùng đúng domain thực, kiểm integration tests có `Origin` đúng/sai qua proxy. Không đặt cứng `portal.example.com` trong demo localhost bên dưới vì Java client kiểm tra handshake bằng Basic credentials và không giả làm browser.

### 7.2 Browser WebSocket API và Authorization header

JavaScript chuẩn:

```javascript
const socket = new WebSocket("wss://portal.example.com/ws/rooms");
socket.onmessage = (event) => console.log(event.data);
```

API `new WebSocket(...)` của browser **không có lựa chọn tùy ý gắn HTTP Authorization header** như `fetch`. Vì vậy demo dùng **Java ReactorNettyWebSocketClient** gửi HTTP Basic header để minh họa handshake; nó **không phải** mã browser production.

Với browser, các phương án phổ biến gồm:

- Browser đã login qua OIDC/form, sử dụng cookie session HTTPS với CSWSH/Origin/CSRF policy.
- Cấp **ticket một lần, sống ngắn, ràng buộc đúng user, audience, WebSocket path và nonce** thông qua HTTPS endpoint đã xác thực; xác minh và tiêu thụ ticket ở handshake.
- Thiết kế subprotocol authentication riêng nếu bắt buộc và có threat review; đừng mặc định `Sec-WebSocket-Protocol` là chỗ an toàn để lưu bearer token dài hạn.

**Không ưu tiên** đưa access token vào query `wss://.../ws?token=...`: URL dễ rơi vào ingress logs, tracing và các hệ thống quan sát. Nếu một product bắt buộc dùng query ticket, chỉ dùng ticket ngắn hạn một lần, che log và hạn chế scope.

## 8. Kiểu thông điệp và authorizing operation

WebSocket nguyên bản **không có khái niệm route `/topic/**` hay method `POST`** sau Upgrade. Ứng dụng phải quy ước protocol rõ:

```text
READ|alpha
READ|beta
WRITE|alpha|new-content
WRITE|beta|new-content
```

Với mỗi frame:

1. Kiểm frame type text/binary, kích thước, encoding và JSON/schema nếu dùng JSON.
2. Parse operation và resource ID; reject unknown operations.
3. Lấy identity đã kiểm từ handshake, hoặc reauth đúng protocol nếu cần.
4. Đọc permissions **hiện tại** từ trusted source, kiểm action + resource + tenant.
5. Chỉ khi allow mới thực thi query/mutation hoặc lập subscription.
6. Khi trả dữ liệu, chỉ gửi trường đã được phân quyền; không broadcast chung rồi “trông chờ client tự lọc”.
7. Ghi audit outcome mà không log raw token/PII.

**Vấn đề TOCTOU:** quyền có thể đổi giữa `hasPermission` và transaction `UPDATE`. Với dữ liệu nhạy cảm, enforce tenant/owner predicates **trong chính DB query/transaction**, không chỉ kiểm trước ở memory.

### 8.1 Mệnh lệnh phải deny theo mặc định

```text
READ|alpha          -> check READ alpha
WRITE|alpha|value   -> check WRITE alpha + validate payload
DELETE|alpha        -> DENY (không có command được công bố)
READ|unknown        -> DENY
MALFORMED           -> ERR
```

Nếu một method mới xuất hiện, không tự cho phép bằng `authenticated()`. Thêm policy/test chính thức trước khi mở command.

## 9. Long-lived streams: quyền thay đổi sau handshake

Một quyền có thể bị thu hồi qua admin API hoặc tenant membership update. Những chiến lược:

- **Check each inbound operation:** trước mỗi READ/WRITE, lấy ACL hiện tại.
- **Check on subscription creation:** khi client đăng ký room/topic, kiểm membership.
- **Check each outbound event:** trước khi emit event mới, kiểm quyền còn hiệu lực.
- **Revocation event:** khi admin revoke, chủ động complete/close luồng hoặc remove subscriber khỏi room; cần event propagation nhiều instance.
- **Connection max age:** kết nối quá lâu phải reconnect và tái xác thực, đặc biệt khi bearer token dùng tại handshake.
- **Heartbeat/ping/pong:** phát hiện dead peer và khi cần kích hoạt kiểm reauth/liveness, không thay authorization.
- **Session/token lifecycle:** cookie logout hay bearer `exp` không tự đóng WebSocket đang mở; phải lập policy chặt.

### 9.1 Trường hợp subscription dài

Ví dụ **mảnh minh họa** cho một luồng event chỉ được phát nếu user còn quyền tại thời điểm đó:

```java
Flux<RoomEvent> safeEvents = roomEvents
    .concatMap(event ->
        permissionService.canRead(
                verifiedUserId, event.roomId())
            .flatMap(allowed -> allowed
                ? Mono.just(event)
                : Mono.error(new AccessDeniedException(
                    "Subscription revoked"))));
```

`roomEvents`, `permissionService`, `RoomEvent` chưa được định nghĩa; đây **không** phải code standalone. Nó minh họa việc kiểm quyền trước **mỗi event** và đóng stream khi bị revoke. Nếu chỉ dùng `filterWhen`, event denied bị bỏ nhưng connection vẫn tồn tại; có thể phù hợp một số feed, nhưng đối với private room thường nên kết thúc subscription và cleanup resources.

**Cần xử lý lúc không có event:** nếu permission bị revoke trong thời gian stream im lặng, per-event check sẽ không chạy cho đến event kế tiếp. Có thể nghe revocation signal từ pub/sub, đặt TTL hoặc periodic reauthorization để ngắt sớm. Nhiều pod cần message bus/cache consistency và xử lý race.

### 9.2 Phân quyền read và write riêng

Một thành viên có thể **đọc** nhưng không được **ghi**. Do đó chỉ kiểm “có thuộc room không” chưa đủ trong product thật. Nên lưu grant theo action:

```text
permission(user, tenant, room, action)
  where action ∈ {READ, WRITE, MODERATE, SUBSCRIBE}
```

Với bài lab, một membership cho phép READ và WRITE để giữ ví dụ ngắn; hãy mở rộng theo nhu cầu business. Việc một người có `ROLE_USER` chỉ nói họ đã đăng nhập, không xác định họ có quyền đọc room beta.

## 10. WebFlux WebSocket, STOMP và RSocket: ba mô hình khác nhau

| Đặc điểm | Raw WebFlux WebSocket | STOMP over WebSocket | RSocket |
|---|---|---|---|
| Transport/protocol | RFC 6455 frames | STOMP frames trên WebSocket | RSocket frames qua TCP/WebSocket/... |
| Handler điển hình | `WebSocketHandler` | `@MessageMapping` và message broker/channel | `@MessageMapping`/`RSocketRequester` |
| Kết nối | HTTP WebSocket Upgrade | HTTP WebSocket Upgrade rồi STOMP CONNECT | RSocket SETUP rồi payload requests |
| Identity cơ bản | HTTP handshake principal hoặc auth protocol tự thiết kế | Handshake + STOMP message user context | SETUP hoặc request metadata authentication |
| Message authz | **Ứng dụng tự implement cho raw messages** | Spring Messaging authorization rules cho cấu hình hỗ trợ | `RSocketSecurity.authorizePayload(...)` |
| Matcher | Operation, room, tenant của app | Message type, destination, subscription | Payload route, SETUP, request/exchange |
| Luồng dài | Receive/send Flux | SUBSCRIBE / broker fanout | request-stream, request-channel, fire-and-forget |
| Rủi ro | Tưởng handshake authenticated là mọi frame được phép | SUBSCRIBE topic khác user, SEND broker destination | SETUP principal service bị áp cho mọi user payload |
| Không được copy nhầm | `@EnableWebSocketSecurity` Servlet vào raw WebFlux handler | `SecurityWebFilterChain` chỉ bảo vệ HTTP handshake | HTTP `authorizeExchange` vào RSocket payload |

### 10.1 STOMP message-level authorization

Tài liệu Spring Security về **WebSocket Security qua Spring Messaging** minh họa `@EnableWebSocketSecurity` và `MessageMatcherDelegatingAuthorizationManager` với:

```java
// MẢNH CẤU HÌNH theo mô hình STOMP/Spring Messaging được hỗ trợ;
// KHÔNG phải cấu hình hoạt động trên WebFlux WebSocketHandler raw.
messages
    .simpDestMatchers("/app/**").hasRole("USER")
    .simpSubscribeDestMatchers("/user/**").authenticated()
    .simpTypeMatchers(MESSAGE, SUBSCRIBE).denyAll()
    .anyMessage().denyAll();
```

Những rule trên điều khiển **inbound STOMP message types/destinations**, không tự áp dụng lên string `READ|beta` trong demo WebFlux. Theo tài liệu Spring Security STOMP, kiểm quyền SUBSCRIBE cực kỳ quan trọng: browser không được subscribe thẳng `/topic/admin/**` hay `/queue/**` của người khác chỉ vì đã kết nối được.

**Phân biệt stack:** trang Spring Security “WebSocket Security” được đặt trong nhánh **Servlet integration** và giả định Spring Messaging/STOMP infrastructure. Không dán `@EnableWebSocketSecurity` vào ứng dụng **thuần WebFlux WebSocketHandler** rồi kỳ vọng Spring tự phân quyền từng raw WebSocket message.

Một lưu ý nữa: Spring Security Messaging thường tập trung bảo vệ **clientInboundChannel**. Không được coi đó là cơ chế tự động kiểm từng outbound delivery; quyết định recipients/subscriptions và quyền đọc dữ liệu phải đúng.

### 10.2 RSocket có setup và request authentication riêng

Spring Security RSocket có:

- `@EnableRSocketSecurity` và `RSocketSecurity`.
- `PayloadSocketAcceptorInterceptor`/`SecuritySocketAcceptorInterceptor`.
- `AuthenticationPayloadInterceptor`.
- `authorizePayload(...)` với `setup()`, `route(...)`, `anyRequest()`, `anyExchange()`.
- Simple Authentication hoặc JWT metadata theo khả năng của stack.

Mảnh cấu hình minh họa theo tài liệu chính thức:

```java
@Bean
PayloadSocketAcceptorInterceptor rsocketInterceptor(
        RSocketSecurity rsocket) {
    rsocket
        .authorizePayload(authz -> authz
            .setup().hasRole("SETUP")
            .route("fetch.profile.me").authenticated()
            .route("fetch.profile.{username}")
                .access((authentication, context) ->
                    checkFriends(authentication, context))
            .anyRequest().authenticated()
            .anyExchange().permitAll())
        .jwt(Customizer.withDefaults());

    return rsocket.build();
}
```

Đây là **mảnh Java chưa runnable** vì `checkFriends` không được định nghĩa; import/bean `ReactiveJwtDecoder` và tích hợp RSocket server cần được bổ sung. Chú ý `anyExchange().permitAll()` là **một lựa chọn của ví dụ trong tài liệu**, không phải lời khuyên cho mọi ứng dụng. Với stream nhạy cảm, policy fail-closed theo route/payload và business ACL phải được kiểm kỹ.

Spring Security RSocket giải thích rất rõ: nếu một kết nối chỉ phục vụ **một** user, authentication tại SETUP có thể phù hợp. Nếu một BFF dùng **một connection dùng chung cho nhiều users**, cần xác thực/ngữ cảnh user ở **mỗi request/payload**, không chỉ dùng identity của SETUP service account.

### 10.3 WebSocket và RSocket không đồng nghĩa

RSocket có metadata routing và security interceptor ở mức RSocket request; WebSocket raw chỉ có message frames và protocol do ứng dụng định nghĩa. WebSocket có thể là **transport** cho RSocket nhưng bạn vẫn phải cấu hình bảo mật theo đúng RSocket protocol, không sao chép policy `WebSocketHandler` cho `RSocketRequester`.

## 11. Ví dụ Spring Boot WebFlux Java 17+ — kiểm quyền từng message

Demo xây một raw WebSocket endpoint `/ws/rooms`, xác thực người dùng **qua HTTP Basic tại handshake**, rồi kiểm **quyền phòng hiện tại cho mỗi frame**. HTTP Basic dùng ở đây vì Java integration client có thể gắn Authorization header dễ dàng; browser JavaScript `new WebSocket` không hỗ trợ tùy ý gắn header như vậy. Production browser nên dùng cookie/OIDC hoặc ticket ngắn hạn đã có thiết kế bảo vệ Origin.

Người dùng lab:

| User | Password lab | Quyền phòng |
|---|---|---|
| alice | `alice-dev-password` | alpha |
| bob | `bob-dev-password` | beta |
| admin | `admin-dev-password` | alpha, beta |

Format text protocol:

```text
READ|alpha                -> OK|READ|alpha|alpha-secret
READ|beta                 -> DENY|FORBIDDEN (đối với Alice)
WRITE|alpha|new-value     -> OK|WRITTEN|alpha (đối với Alice)
WRITE|beta|new-value      -> DENY|FORBIDDEN (đối với Alice)
DELETE|alpha              -> ERR|BAD_COMMAND
```

Việc WRITE lưu giá trị vào in-memory map cho lab. Real system cần DB transaction với owner/tenant predicate, durability, concurrent edit handling và audit. Demo cho cả READ/WRITE trong cùng membership để tập trung vào **connection identity vs message-level policy**.

### 11.1 Cấu trúc dự án

```text
webflux-ws-message-authz/
  settings.gradle
  build.gradle
  src/main/java/demo/ws/WebSocketSecurityApplication.java
  src/main/java/demo/ws/SecurityConfiguration.java
  src/main/java/demo/ws/RoomPolicy.java
  src/main/java/demo/ws/RoomWebSocketHandler.java
  src/main/java/demo/ws/WebSocketConfiguration.java
  src/main/java/demo/ws/HealthController.java
  src/test/java/demo/ws/RoomPolicyTest.java
  src/test/java/demo/ws/RoomWebSocketIntegrationTest.java
```

**settings.gradle**

```groovy
rootProject.name = 'webflux-ws-message-authz'
```

**build.gradle**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo.ws'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot WebFlux starter kéo theo Reactor Netty và Spring Framework WebSocket APIs. Không thêm `spring-boot-starter-web` của Servlet vào demo. Các test WebSocket dùng `ReactorNettyWebSocketClient` và test unit policy dùng `StepVerifier`.

### 11.2 Main application

**src/main/java/demo/ws/WebSocketSecurityApplication.java**

```java
package demo.ws;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebSocketSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebSocketSecurityApplication.class, args);
    }
}
```

### 11.3 SecurityConfiguration: xác thực handshake, không giả định message rights

**src/main/java/demo/ws/SecurityConfiguration.java**

```java
package demo.ws;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice-dev-password"))
            .roles("USER")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("bob-dev-password"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-dev-password"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(
            alice, bob, admin);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/ws/rooms")
                    .authenticated()
                .pathMatchers(HttpMethod.GET, "/health")
                    .permitAll()
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }
}
```

Ý nghĩa:

- `GET /ws/rooms` là HTTP handshake endpoint, yêu cầu authentication hợp lệ. Thiếu/sai Basic credentials sẽ không nhận `101 Switching Protocols`.
- `GET /health` public. Các URL khác deny mặc định.
- Không tự tạo một authentication manager hoặc parser trong WebSocket handler; dùng Spring Security WebFlux cho HTTP.
- `ROLE_USER` và `ROLE_ADMIN` chỉ dùng đăng nhập; **RoomPolicy mới quyết định room access**. Hai người cùng `ROLE_USER` không có cùng quyền phòng.
- CSRF mặc định vẫn có cho HTTP unsafe methods; demo chỉ GET. Đừng suy rằng nó thay WebSocket Origin validation.
- Thông tin credential trong lab không được dùng làm credential thật; production phải dùng TLS, vault/secret manager, OIDC hoặc cơ chế xác thực phù hợp.

### 11.4 RoomPolicy: quyền hiện tại, độc lập thời điểm handshake

**src/main/java/demo/ws/RoomPolicy.java**

```java
package demo.ws;

import java.nio.charset.StandardCharsets;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public final class RoomPolicy {

    private final ConcurrentMap<String, Set<String>> memberships =
        new ConcurrentHashMap<>();

    private final ConcurrentMap<String, String> documents =
        new ConcurrentHashMap<>();

    public RoomPolicy() {
        memberships.put("alice", Set.of("alpha"));
        memberships.put("bob", Set.of("beta"));
        memberships.put("admin", Set.of("alpha", "beta"));

        documents.put("alpha", "alpha-secret");
        documents.put("beta", "beta-secret");
    }

    public Mono<String> handle(String verifiedUsername, String frame) {
        return Mono.fromSupplier(() ->
            decide(verifiedUsername, frame));
    }

    private String decide(String username, String raw) {
        if (raw == null
                || raw.getBytes(StandardCharsets.UTF_8).length > 1024) {
            return "ERR|BAD_FRAME";
        }

        String[] fields = raw.split("\\|", 3);
        if (fields.length < 2) {
            return "ERR|BAD_COMMAND";
        }

        String action = fields[0];
        String room = fields[1];

        if (!"READ".equals(action) && !"WRITE".equals(action)) {
            return "ERR|BAD_COMMAND";
        }

        if (!documents.containsKey(room)) {
            // Không tiết lộ danh sách phòng không thuộc user.
            return "DENY|FORBIDDEN";
        }

        // Đọc ACL HIỆN TẠI cho MỖI message, không cache tại handshake.
        if (!memberships.getOrDefault(username, Set.of())
                .contains(room)) {
            return "DENY|FORBIDDEN";
        }

        if ("READ".equals(action)) {
            if (fields.length != 2) {
                return "ERR|BAD_COMMAND";
            }
            return "OK|READ|" + room + "|" + documents.get(room);
        }

        if (fields.length != 3 || fields[2].isBlank()
                || fields[2].length() > 256) {
            return "ERR|BAD_COMMAND";
        }

        documents.put(room, fields[2]);
        return "OK|WRITTEN|" + room;
    }

    // Chỉ demo cách quyền có thể thay đổi trong lúc WebSocket còn mở.
    // KHÔNG expose method này thành một endpoint public!
    public void revoke(String username, String room) {
        memberships.computeIfPresent(username, (key, current) -> {
            Set<String> copy = new HashSet<>(current);
            copy.remove(room);
            return Set.copyOf(copy);
        });
    }
}
```

Điểm đáng chú ý:

1. `RoomPolicy.handle(...)` trả `Mono<String>` để gắn vào reactive pipeline mà không gọi `block()`.
2. `verifiedUsername` phải được tạo từ **handshake Principal của server**, không lấy từ payload client.
3. `memberships` được truy vấn trên **mỗi message**; `revoke(...)` làm thay đổi kết quả của message tiếp theo mà không cần tái mở WebSocket.
4. `ConcurrentHashMap` và `Set.copyOf(...)` phục vụ lab; quyền production nên lấy từ source đã tin cậy, có TTL/revocation consistency, thường gắn tenant/issuer/subject.
5. `READ|beta` của Alice bị deny; việc cùng `ROLE_USER` không tạo quyền chéo.
6. `WRITE` chỉ ghi `documents` sau khi đã kiểm resource và membership. Không ghi dữ liệu khi bị từ chối.
7. Giới hạn 1024 **byte UTF-8 sau khi decode** là một lớp hạn chế input lab; production vẫn phải giới hạn WebSocket frame size, fragmentation, buffer retention, rate và memory ở transport/config.
8. Để đơn giản, lab dùng cùng membership cho READ/WRITE; production có action-specific policies.
9. Lab không có subscription/broadcast; với stream outbound phải bổ sung per-event authorization như mục 9.
10. `revoke(...)` chỉ dùng từ test/service được tin cậy; không đưa nó ra public controller mà không bảo vệ admin và audit.
11. Tính nguyên tử trong lab chỉ ở map operation; với database mutation thật phải enforce owner/tenant trong transaction, tránh TOCTOU.

### 11.5 RoomWebSocketHandler: lấy Principal một lần, kiểm mỗi frame

**src/main/java/demo/ws/RoomWebSocketHandler.java**

```java
package demo.ws;

import java.security.Principal;

import org.springframework.stereotype.Component;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.WebSocketSession;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public final class RoomWebSocketHandler implements WebSocketHandler {

    private final RoomPolicy policy;

    public RoomWebSocketHandler(RoomPolicy policy) {
        this.policy = policy;
    }

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        // Identity đến từ HTTP handshake đã được Security kiểm.
        return session.getHandshakeInfo().getPrincipal()
            .switchIfEmpty(Mono.error(
                new IllegalStateException(
                    "Authenticated handshake required")))
            .flatMap(principal -> sendAuthorizedReplies(
                session, principal));
    }

    private Mono<Void> sendAuthorizedReplies(
            WebSocketSession session, Principal principal) {

        Flux<WebSocketMessage> replies = session.receive()
            .concatMap(frame -> {
                if (frame.getType() != WebSocketMessage.Type.TEXT) {
                    return Mono.just("ERR|TEXT_ONLY");
                }

                String message = frame.getPayloadAsText();
                return policy.handle(principal.getName(), message);
            })
            .map(session::textMessage);

        return session.send(replies);
    }
}
```

**Tại sao không chỉ làm `session.send(session.receive().map(session::textMessage))`?** Vì echo trực tiếp toàn bộ message của client mà không parse/resource checks không thực hiện authorization. Ở đây:

- `getHandshakeInfo().getPrincipal()` cung cấp danh tính được kết nối. Nếu rỗng, handler không cấp quyền.
- `session.receive()` có thể phát **nhiều** frame trong suốt lifetime.
- `concatMap` gọi `RoomPolicy.handle(...)` **cho mỗi frame**, giữ thứ tự response và tránh tự `subscribe()` ngoài pipeline.
- Frame binary/control không được diễn giải như command text; demo trả lỗi cho type khác TEXT. Trong production phải cân nhắc handling protocol controls, close codes và binary validation.
- Output chỉ là response đã được policy cho phép; không phát room data trước kiểm quyền.
- Nếu socket đóng, reactive receive/send hoàn thành/cancel theo protocol; không tự giữ data buffer sau callback. Với Netty pooled buffers, nếu giữ một buffer qua asynchronous boundary thì phải dùng retain/release đúng API; demo tạo `String` trong pipeline rồi không giữ raw buffer.

### 11.6 WebSocketConfiguration: map endpoint vào handler

**src/main/java/demo/ws/WebSocketConfiguration.java**

```java
package demo.ws;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.reactive.handler.SimpleUrlHandlerMapping;

@Configuration(proxyBeanMethods = false)
public class WebSocketConfiguration {

    @Bean
    HandlerMapping webSocketMapping(
            RoomWebSocketHandler handler) {
        return new SimpleUrlHandlerMapping(
            Map.of("/ws/rooms", handler), -1);
    }
}
```

`SimpleUrlHandlerMapping` map `/ws/rooms` đến `WebSocketHandler`, order -1 để được xét trước annotated controllers khi phù hợp. Spring Boot WebFlux auto-configuration cung cấp các WebFlux handler adapters cần thiết, bao gồm WebSocket handling trong WebFlux Config; không cần tự thêm Servlet WebSocket registration.

**Production Origin policy:** hãy thêm `CorsConfiguration`/`CorsConfigurationSource` cho mapping/handler theo các origin được phép (mục 7). Project lab chỉ được dùng để thử kết nối Java client trên localhost; nó chưa có allowlist Origin theo browser deployment. Không được coi demo này production-ready cho private cookie-based WebSocket.

### 11.7 HealthController

**src/main/java/demo/ws/HealthController.java**

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

### 11.8 Chạy thử

Tại thư mục gốc project, có JDK 17+ và Gradle tương thích:

```bash
gradle bootRun
```

Nếu có Gradle Wrapper: `./gradlew bootRun` hoặc Windows `gradlew.bat bootRun`. `curl` thuần không tạo một full-duplex WebSocket session đầy đủ chỉ bằng GET HTTP thông thường; để thử frame, dùng WebSocket client có khả năng HTTP Upgrade và gửi messages, ví dụ client Java trong test mục 12.

Nếu có `wscat`/một WebSocket client hỗ trợ header trong lab:

```bash
# Minh họa ý tưởng, chỉ dùng credentials giả trên localhost.
# Client CLI phải hỗ trợ handshake Authorization header.
wscat -c ws://localhost:8080/ws/rooms \
  -H "Authorization: Basic <BASE64_CREDENTIALS_DEMO>"
```

`<BASE64_CREDENTIALS_DEMO>` chỉ là placeholder trong hướng dẫn CLI, **không** phải một giá trị có thể dùng ngay; trong test Java sẽ dùng `HttpHeaders.setBasicAuth` để tự encode đúng.

Mở kết nối với Alice rồi gửi:

```text
READ|alpha
READ|beta
WRITE|beta|no
```

Kỳ vọng lần lượt:

```text
OK|READ|alpha|alpha-secret
DENY|FORBIDDEN
DENY|FORBIDDEN
```

Đây là kết quả theo chính sách lab trước khi test nào sửa `documents`. `WRITE|alpha|hi` được phép và làm những lần `READ|alpha` tiếp theo thấy `hi` trong **cùng JVM**.

## 12. Kiểm thử tự động: policy và WebSocket handshake

### 12.1 Test policy độc lập: revoke thay quyền sau khi đã có identity

**src/test/java/demo/ws/RoomPolicyTest.java**

```java
package demo.ws;

import org.junit.jupiter.api.Test;

import reactor.test.StepVerifier;

class RoomPolicyTest {

    @Test
    void aliceCanReadOnlyHerRoom() {
        RoomPolicy policy = new RoomPolicy();

        StepVerifier.create(policy.handle("alice", "READ|alpha"))
            .expectNext("OK|READ|alpha|alpha-secret")
            .verifyComplete();

        StepVerifier.create(policy.handle("alice", "READ|beta"))
            .expectNext("DENY|FORBIDDEN")
            .verifyComplete();
    }

    @Test
    void bobCanReadOnlyHisRoom() {
        RoomPolicy policy = new RoomPolicy();

        StepVerifier.create(policy.handle("bob", "READ|beta"))
            .expectNext("OK|READ|beta|beta-secret")
            .verifyComplete();

        StepVerifier.create(policy.handle("bob", "READ|alpha"))
            .expectNext("DENY|FORBIDDEN")
            .verifyComplete();
    }

    @Test
    void revocationChangesNextMessageAuthorization() {
        RoomPolicy policy = new RoomPolicy();

        StepVerifier.create(policy.handle("alice", "READ|alpha"))
            .expectNext("OK|READ|alpha|alpha-secret")
            .verifyComplete();

        policy.revoke("alice", "alpha");

        StepVerifier.create(policy.handle("alice", "READ|alpha"))
            .expectNext("DENY|FORBIDDEN")
            .verifyComplete();
    }

    @Test
    void deniedWriteDoesNotChangeRoomData() {
        RoomPolicy policy = new RoomPolicy();

        StepVerifier.create(
                policy.handle("alice", "WRITE|beta|stolen"))
            .expectNext("DENY|FORBIDDEN")
            .verifyComplete();

        StepVerifier.create(policy.handle("bob", "READ|beta"))
            .expectNext("OK|READ|beta|beta-secret")
            .verifyComplete();
    }

    @Test
    void successfulWriteRequiresCurrentAccess() {
        RoomPolicy policy = new RoomPolicy();

        StepVerifier.create(policy.handle(
                "bob", "WRITE|beta|new-beta"))
            .expectNext("OK|WRITTEN|beta")
            .verifyComplete();

        StepVerifier.create(policy.handle("bob", "READ|beta"))
            .expectNext("OK|READ|beta|new-beta")
            .verifyComplete();
    }

    @Test
    void unknownCommandAndRoomAreNotAuthorized() {
        RoomPolicy policy = new RoomPolicy();

        StepVerifier.create(policy.handle("alice", "DELETE|alpha"))
            .expectNext("ERR|BAD_COMMAND")
            .verifyComplete();

        StepVerifier.create(policy.handle("alice", "READ|secret"))
            .expectNext("DENY|FORBIDDEN")
            .verifyComplete();
    }
}
```

**6 unit tests** dùng `StepVerifier` xác nhận mỗi message được phân quyền theo room hiện tại; test revocation cố tình dùng **cùng user identity** cho hai lần gọi, nhưng kết quả đổi sau `revoke`. Đây là bằng chứng policy xử lý từng message, **không** phải kiểm thử cơ chế phát tín hiệu revoke đến một WebSocket session đang mở qua nhiều pod.

### 12.2 Integration test: kết nối WebSocket với HTTP Basic

**src/test/java/demo/ws/RoomWebSocketIntegrationTest.java**

```java
package demo.ws;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class RoomWebSocketIntegrationTest {

    @LocalServerPort
    int port;

    @Autowired
    WebTestClient http;

    private URI wsUri() {
        return URI.create(
            "ws://localhost:" + port + "/ws/rooms");
    }

    private Mono<List<String>> exchange(
            String username, String password, String... commands) {

        HttpHeaders headers = new HttpHeaders();
        headers.setBasicAuth(username, password);

        AtomicReference<List<String>> observed =
            new AtomicReference<>();

        var socketClient = new ReactorNettyWebSocketClient();

        return socketClient.execute(wsUri(), headers, session -> {
            Mono<Void> sendCommands = session.send(
                Flux.fromArray(commands).map(session::textMessage));

            Mono<Void> readAnswers = session.receive()
                .map(WebSocketMessage::getPayloadAsText)
                .take(commands.length)
                .collectList()
                .doOnNext(observed::set)
                .then();

            return Mono.when(sendCommands, readAnswers);
        })
        .timeout(Duration.ofSeconds(10))
        .then(Mono.fromSupplier(observed::get));
    }

    @Test
    void missingAuthenticationCannotUpgrade() {
        var client = new ReactorNettyWebSocketClient();

        StepVerifier.create(
                client.execute(wsUri(), new HttpHeaders(),
                    session -> Mono.empty())
                    .timeout(Duration.ofSeconds(5)))
            .expectError()
            .verify();
    }

    @Test
    void wrongPasswordCannotUpgrade() {
        var client = new ReactorNettyWebSocketClient();
        HttpHeaders headers = new HttpHeaders();
        headers.setBasicAuth("alice", "wrong-password");

        StepVerifier.create(
                client.execute(wsUri(), headers,
                    session -> Mono.empty())
                    .timeout(Duration.ofSeconds(5)))
            .expectError()
            .verify();
    }

    @Test
    void aliceOneConnectionReceivesAllowAndDeny() {
        StepVerifier.create(exchange(
                "alice", "alice-dev-password",
                "READ|alpha", "READ|beta"))
            .expectNext(List.of(
                "OK|READ|alpha|alpha-secret",
                "DENY|FORBIDDEN"))
            .verifyComplete();
    }

    @Test
    void bobCannotReadAlphaOnHisOwnConnection() {
        StepVerifier.create(exchange(
                "bob", "bob-dev-password",
                "READ|beta", "READ|alpha"))
            .expectNext(List.of(
                "OK|READ|beta|beta-secret",
                "DENY|FORBIDDEN"))
            .verifyComplete();
    }

    @Test
    void aliceCannotWriteBetaDespiteValidHandshake() {
        StepVerifier.create(exchange(
                "alice", "alice-dev-password",
                "WRITE|beta|illegal", "READ|alpha"))
            .expectNext(List.of(
                "DENY|FORBIDDEN",
                "OK|READ|alpha|alpha-secret"))
            .verifyComplete();
    }

    @Test
    void unknownCommandIsRejectedAfterHandshake() {
        StepVerifier.create(exchange(
                "alice", "alice-dev-password", "DELETE|alpha"))
            .expectNext(List.of("ERR|BAD_COMMAND"))
            .verifyComplete();
    }

    @Test
    void healthIsPublicWithoutWebSocketHandshake() {
        http.get().uri("/health")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("ok");
    }
}
```

**7 integration tests** (sáu hành vi WebSocket/handshake và một health HTTP) thực thi HTTP Upgrade qua Reactor Netty:

- Không có credentials và sai password → handshake không được nâng cấp (publisher lỗi).
- Alice/Bob đều authenticated nhưng chỉ được đọc room mình có quyền.
- Request WRITE xuyên room bị từ chối, dù handshake hợp lệ.
- Command chưa được định nghĩa bị từ chối.
- Route public không cần WebSocket.

`WebSocketClient.execute(URI,HttpHeaders,WebSocketHandler)` hỗ trợ đặt HTTP headers cho handshake; `Mono.when(sendCommands,readAnswers)` cho phép gửi và nhận song song, `take(commands.length)` hoàn tất test sau đủ response. `timeout` giúp test không treo vô hạn nếu connection lỗi.

**Giới hạn test:** `RoomPolicy` ở bài integration không bị revoke trong lúc mở socket; thay đổi quyền sau handshake được test ở lớp policy (mục 12.1). Để chứng minh end-to-end revocation nhiều instance, cần bài test thêm mở một socket, nhận allow, admin revoke, gửi tiếp message trên **cùng socket**, rồi xác nhận deny/close và kiểm propagation qua message bus.

### 12.3 Chạy test

```bash
gradle test
```

Nếu có wrapper phù hợp: `./gradlew test` hoặc Windows `gradlew.bat test`. Trong PowerShell có thể dùng `curl.exe` cho HTTP.

**Trạng thái kiểm thử:** những đoạn Java được viết theo API Spring Framework WebFlux/WebSocket, Spring Security 6.x và Reactor và được rà soát thủ công, **chưa chạy Gradle build/test thực tế** trong quá trình soạn bài. Các HTTP status/body mô tả là kết quả thiết kế dự kiến; cần chạy trong môi trường có JDK/Gradle/dependencies phù hợp để xác nhận. Không dùng kết quả kỳ vọng như bằng chứng hệ thống production đã an toàn.

## 13. Những bẫy khi đăng nhập và token hết hạn

### 13.1 HTTP Basic tại handshake có giới hạn gì?

- Java WebSocketClient có thể gửi Basic Authorization qua HTTP handshake, như demo.
- Browser `new WebSocket()` không cho tùy ý đặt Authorization header.
- Basic credentials có nguy cơ xuất hiện trong proxy logs/packet capture nếu không dùng TLS; phải dùng `wss://` và cẩn thận tracing.
- Basic không có logout/refresh token như OIDC; production browser thường dùng session/OIDC.

**Không** sửa bằng cách nhét username/password vào URL WebSocket. Dùng cookie-session hoặc ticket ngắn hạn có kiểm soát, hoặc RSocket per-request metadata theo thiết kế.

### 13.2 JWT hết hạn giữa chừng

Một JWT có `exp` sau 15 phút có thể được kiểm ở handshake 14:59, nhưng kết nối còn đến 17:00. HTTP Security filter chain **không tự tái chạy trên từng frame**. Do đó lựa chọn vận hành:

1. Ghi lại hạn kết nối/credential đã xác minh ở handshake qua security context được tin.
2. Đóng WebSocket tại thời điểm token/session policy hết hiệu lực hoặc đặt max connection lifetime.
3. Cho reconnect/re-auth bằng token mới sau khi browser/SDK hoàn tất flow hợp lệ.
4. Nếu API yêu cầu authentication trên từng message, thiết kế protocol với revalidation được hỗ trợ thay vì tự tin principal cũ.
5. Phối hợp revocation/logout ở nhiều node; kiểm event latency và race.

Không chỉ kiểm `exp` raw từ payload WebSocket chưa verify; cần thông tin token đã được xác thực và policy đang hiệu lực.

### 13.3 Login/logout không tự xử lý mọi socket

Logout HTTP có thể vô hiệu hóa WebSession/cookie, nhưng WebSocket đang mở có thể còn tồn tại. STOMP + Spring Session có tích hợp riêng ở stack hỗ trợ; **không giả định raw WebFlux WebSocket tự ngắt mọi socket khi logout**. Quản lý connection registry theo stable identity, close/cancel on revoke, kiểm multi-node and cluster distribution, tránh lưu toàn bộ token/PII trong registry.

### 13.4 Renewal trong một kết nối

Một message kiểu `{"type":"AUTH_REFRESH","token":"..."}` do ứng dụng tự nghĩ ra **không tự động an toàn**. Cần thiết kế state machine:

- Authenticate token mới bằng verifier đúng issuer/audience/signature/expiry.
- Ngăn identity switching không được cho phép: session Alice không thể tự đổi thành Bob mà vẫn dùng subscriptions cũ.
- Xóa subscriptions/permissions cũ khi đổi principal.
- Chặn replay, downgrade và reuse token đã revoke.
- Không để lệnh refresh tự được miễn mọi phân quyền khác.

Trong nhiều sản phẩm, **đóng và mở lại kết nối** đơn giản và dễ kiểm soát hơn reauth giữa stream.

## 14. Subscription, fan-out và broadcasting

Một lỗi phổ biến: kiểm quyền khi client gửi `SUBSCRIBE|alpha`, nhưng sau đó service gửi mọi event từ `Flux<RoomEvent>` đến tất cả sockets.

**Không đủ:**

```java
// PHẢN VÍ DỤ: ai đã được thêm vào socket list đều nhận tất cả.
roomEvents.subscribe(event ->
    everySocket.send(event.toString()));
```

Mã này là pseudocode và **không** phải cách viết reactive đúng (subscribe thủ công không quản lifecycle). Cách thiết kế an toàn cần:

- Tập subscriptions theo `verifiedUserId + tenant + resource + action`.
- Grant khi subscribe và **revalidate khi event được phát** hoặc hủy subscription ngay khi revoke.
- Không để client chỉ định người nhận khác bằng header/body.
- Outbound event serialization phải loại PII/secret không thuộc quyền.
- Backpressure: bounded queues; client chậm bị drop/close theo policy, không tích vô hạn dữ liệu riêng tư.
- Cleanup on disconnect: dispose subscriptions, release buffers/resources, không giữ session/listener mồ côi.
- Event bus phân phối revoke qua nodes; test độ trễ khi policy thay đổi.
- Không đưa access token vào event payload hay trace để correlate.

### 14.1 Quyền đọc phòng khác quyền nhận event hệ thống

Một user có thể được phép `READ|alpha` nhưng không được nhận event `room.alpha.audit.admin` hoặc event thuộc tenant khác. Thiết kế ACL theo **loại event** và **sensitivity**, không chỉ theo room ID. Khi event chứa bản ghi cụ thể, còn phải kiểm owner/record. “Được xem tổng quan phòng” không nghĩa xem mọi tin nhắn riêng tư trong phòng.

## 15. WebFlux Security vs method security trong message handler

Có thể bật reactive method security cho **service methods** và dùng `@PreAuthorize` hoặc `ReactiveAuthorizationManager` theo context. Nhưng khi một WebSocket handler gọi service từ pipeline riêng, không được giả định Reactor SecurityContext từ HTTP handshake luôn được truyền nguyên vẹn tới từng service call về sau trong mọi kiến trúc.

Nếu muốn dựa vào `@AuthenticationPrincipal`/`ReactiveSecurityContextHolder`, phải test context propagation rõ trong luồng WebSocket và không tự đi qua `subscribe()` mất context. Một cách đơn giản và dễ review cho raw WebSocket là **truyền identity đã xác minh** đến method policy như demo, nơi policy lấy ACL hiện tại. Với hệ thống phức tạp, cân nhắc explicit `AuthorizationContext` chứa subject, issuer, tenant, action, resource, session ID không nhạy cảm.

**Không chuyển Principal object thô ra nhiều thread/caches và cho nó sống mãi như chứng thực mới.** Principal từ handshake là snapshot; quyền/session lifecycle phải có chính sách mới.

## 16. Threat model và test matrix

| Tình huống | HTTP handshake | Message/stream | Kết quả cần bảo đảm |
|---|---|---|---|
| Thiếu credential | 401/redirect, không 101 | Không xử lý | Socket không mở private |
| Credential sai/hết hạn lúc handshake | Fail authentication | Không xử lý | Không có Principal authenticated |
| Alice hợp lệ, READ alpha | 101 | Kiểm READ alpha | Allow |
| Alice hợp lệ, READ beta | 101 | Kiểm READ beta | Deny |
| Bob hợp lệ, WRITE alpha | 101 | Kiểm WRITE alpha | Deny, DB không bị sửa |
| Frame thiếu type/resource | 101 | Validate schema | Reject message |
| Unknown operation | 101 | Deny-by-default | Không thực thi |
| Alice bị revoke sau connect | Kết nối có thể vẫn sống | Recheck ACL mỗi frame/event | Deny hoặc close ngay |
| User được subscribe rồi bị revoke | 101 | Revalidate event / revoke signal | Không phát private data tiếp |
| Browser Origin lạ với cookie | Reject theo Origin policy | Không xử lý | Chống CSWSH |
| Non-browser giả Origin nhưng không credential | HTTP auth từ chối | Không xử lý | Origin không thay authentication |
| JWT `exp` khi socket vẫn mở | Initial handshake đã qua | TTL/reauth strategy | Không dùng identity hết hạn mãi |
| Session logout | Socket có thể còn | Revoke/close registry | Không nhận private events sau revoke |
| Token đúng issuer, sai audience | Reject JWT validation | Không xử lý | Không bypass aud |
| Multi-tenant route/chat message | 101 hợp lệ | Check tenant + room + action + record | Không rò dữ liệu giữa tenant |
| Shared service connection multiplex users | Auth connection service | Per-request delegated identity | Không cho user Alice mượn quyền service |
| Binary/oversized frame | Handshake có thể thành công | Kiểm type/size/buffer | Reject/close và rate-limit |
| Message flood/slow client | Có thể 101 | Backpressure/rate limits | Không cạn heap/event loop |
| STOMP broker destination | 101 + CONNECT auth | SEND/SUBSCRIBE rules | Không publish/subscribe channel trái phép |
| RSocket setup vs payload | Setup được cấp | Route/payload authz | Không coi SETUP grant là mọi resource grant |

## 17. Các lỗi thường gặp và cách khắc phục

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| `/ws/**.authenticated()` rồi cho phép mọi frame | BOLA, cross-tenant reads | Per-message action/resource ACL |
| Tin `userId` trong JSON message | User impersonation | Lấy identity từ verified handshake/token |
| Chỉ kiểm quyền lúc SUBSCRIBE | Rò dữ liệu sau revoke | Revalidate each event, revoke/close |
| Dùng `permitAll` cho handshake riêng tư | Anonymous socket dùng private protocol | Require authenticated, explicit anonymous policy |
| Không kiểm WebSocket Origin | CSWSH trên cookie session | Allowed origins, SameSite/CSRF design |
| Coi REST CORS headers là WebSocket protection | Bỏ sót browser cross-site socket | Handshake Origin policy |
| JWT hết hạn nhưng socket sống vô hạn | Identity stale | Reauth/max age/close policy |
| Logout HTTP không đóng socket | Data leak sau logout | Connection registry và revoke event |
| User alpha gửi room beta được vì đều ROLE_USER | Lỗi object-level authorization | Check room membership/tenant |
| Dùng STOMP `@EnableWebSocketSecurity` trong raw WebFlux handler | Sai stack, rule không chạy | Dùng policy raw handler hoặc framework đúng |
| Copy Servlet `HttpSecurity` cho WebFlux | Sai API stack | `ServerHttpSecurity`/`SecurityWebFilterChain` |
| Giả định RSocket SETUP auth bảo vệ mọi payload | Shared-connection user mix-up | Payload authz và per-request user metadata |
| Chuyển ID Token thành Bearer downstream | Sai token purpose/audience | Dùng access token đúng resource |
| Dùng query `?access_token=...` dài hạn | Lộ token qua logs | Cookie/ticket ngắn hạn/secure auth |
| Không limit frame/buffer/queue | DoS/memory exhaustion | WebSocket limits, bounded queues, backpressure |
| Gọi blocking JPA từ event loop | Giảm throughput, timeout | R2DBC hoặc bounded scheduler boundary |
| `subscribe()` thủ công trong handler | Mất cancellation/context, leak | Compose `Mono<Void>` từ receive/send |
| “Authz check” rồi UPDATE không gắn tenant | TOCTOU/cross-tenant write | DB predicate/transaction enforcement |
| Trả private event theo room name client tự chọn | Cross-tenant broadcast | Server-side subscription registry |
| Không phân biệt 401 với message-level DENY | Client retry/login loops | Error contract rõ, close codes phù hợp |

## 18. Checklist khi triển khai WebSocket/RSocket thực tế

1. Xác định protocol: **raw WebFlux WebSocket**, **STOMP**, hay **RSocket**. Chọn đúng security integration.
2. Bảo vệ HTTP handshake hoặc SETUP bằng authentication phù hợp; không cấp private socket cho anonymous ngoài chủ đích.
3. Có TLS/WSS và certificate verification; cấu hình proxy nâng cấp kết nối và idle timeout.
4. Kiểm `Origin` khi browser sử dụng session cookie; không tin Origin thay credential.
5. Đừng đặt bearer token dài hạn vào URL/query hoặc raw telemetry.
6. Lấy principal từ `HandshakeInfo.getPrincipal()` (WebFlux) hoặc metadata đã verify ở protocol tương ứng.
7. Tách identity connection khỏi authorization từng message/room/tenant.
8. Validate message type, schema, size, room/resource ID, rate và hành động cho phép.
9. Dùng **deny by default** cho unknown operations/destinations và tenant không nằm allowlist.
10. Check quyền hiện tại trước READ/WRITE/DELETE; enforce data-layer predicate trong transaction.
11. Với SUBSCRIBE, check lúc subscribe **và** trước phát event hoặc hủy ngay khi revoke.
12. Định nghĩa session max-age, JWT exp, reauthentication và logout/revocation propagation.
13. Với shared connection, không áp service principal thay quyền mọi user; dùng delegated token/per-request metadata có kiểm chứng.
14. Không log Authorization, cookies, access/refresh tokens, private event payload hoặc PII quá mức.
15. Giới hạn memory buffers, frame sizes, queue depth, concurrent connections; thiết kế backpressure và cleanup.
16. Không block Netty event loop bằng database/remote call đồng bộ; test concurrent streams.
17. Viết unit tests current ACL/revocation, WebSocket handshake 101/401, cross-room DENY và integration E2E long-lived session.
18. Tách STOMP inbound SEND/SUBSCRIBE và outbound delivery authorization; không tự tin subscription là mãi mãi.
19. Với RSocket, xét SETUP authority, route/request authorization và metadata per request cho shared connections.
20. Rà soát quyền mỗi khi thêm command/subscription hoặc thay đổi schema; test negative cases và các race conditions.

## 19. Bài tập thực hành

1. Giải thích vì sao Spring Security HTTP matcher `GET /ws/rooms` không tự chặn frame `READ|beta` sau `101 Switching Protocols`.
2. Cho Alice và Bob cùng `ROLE_USER`: tại sao có thể mở cùng endpoint nhưng có quyền room khác nhau?
3. Gửi `READ|alpha`, `READ|beta` trong **một kết nối**. Xác nhận hai kết quả allow/deny mà không đổi principal.
4. Viết test gọi `RoomPolicy.revoke("alice","alpha")` giữa hai lần READ; giải thích vì sao dùng ACL snapshot tại handshake sẽ sai.
5. Thêm lệnh `DELETE|room`: phải có permission action riêng, rate limit và DB owner predicate; không dùng `authenticated()` đơn thuần.
6. Thiết kế permission read-only cho một user: cho READ, chặn WRITE, ngay cả khi user đã join room.
7. Thiết kế `SUBSCRIBE|alpha` với event stream. Khi revoke giữa stream, làm thế nào ngăn emit các event mới?
8. Cho stream không có event 1 giờ; làm sao close connection ngay khi user bị revoke dù per-event check chưa chạy?
9. Mô phỏng browser cross-site mở private WebSocket bằng cookie tự gửi. Vì sao kiểm Origin cần thiết? Origin có thay credential không?
10. Thử truy cập ws bằng browser JavaScript có yêu cầu `Authorization` tùy ý. Vì sao API browser không cho đặt header này trực tiếp?
11. Đề xuất short-lived one-time ticket cho WebSocket handshake: TTL, nonce, audience, replay prevention, log redaction.
12. JWT còn 1 phút thì handshake thành công rồi connection sống 3 giờ. Định nghĩa max-age/reauth policy và tests.
13. So sánh STOMP `SUBSCRIBE /topic/**` với raw WebFlux frame `READ|alpha`. Security API nào áp dụng?
14. So sánh RSocket `SETUP` auth với `route("fetch.profile.me")` auth. Kết nối dùng chung nhiều users cần gì?
15. Thiết kế BFF chuyển tiếp private event đến browser: nguồn quyền là service identity hay end-user delegated identity?
16. Chèn payload `{"userId":"admin","role":"ADMIN"}` vào một frame. Giải thích vì sao server không được tin các trường đó.
17. Tạo integration test WebSocket sai Origin/thiếu cookie/đúng cookie với handshake origin restrictions.
18. Thêm concurrency/rate tests để phát hiện memory leak từ `subscribe()` thủ công và unbounded queues.
19. Thay membership in-memory bằng R2DBC database query có tenant condition; xử lý TOCTOU trong UPDATE.
20. Thiết kế runbook khi phát hiện token/session compromised: revoke, close sockets, clear subscriptions, audit và reauth.

## Kết luận

**Danh tính tại kết nối** chỉ trả lời “ai được phép mở WebSocket?”. **Phân quyền từng thông điệp** phải tiếp tục trả lời “người đó có được thực hiện operation này trên object/room/tenant này, vào thời điểm này hay không?”. Trong Spring WebFlux, HTTP `SecurityWebFilterChain` kiểm request Upgrade, `WebSocketSession.getHandshakeInfo().getPrincipal()` cho identity đã xác thực, còn `receive()`/`send()` xử lý một luồng messages có thể kéo dài nhiều giờ. `authorizeExchange` **không tự áp** trên mỗi frame sau 101. Phải kiểm ACL theo từng inbound command, khi tạo subscriptions và khi phát private outbound events; xử lý revoke, token expiry, logout, Origin/CSWSH, TLS, buffer limits và data-layer authorization. Với STOMP/Spring Messaging và RSocket có security integrations chuyên biệt, nhưng vẫn phải phân biệt auth của connection/SETUP với quyền của từng message/payload và dữ liệu nghiệp vụ.

## Tài liệu chính thức và tiêu chuẩn

1. Spring Framework — Reactive WebSocket API, handshake, handler mapping, receive/send, CORS: https://docs.spring.io/spring-framework/reference/web/webflux-websocket.html
2. Spring Framework 6.1 — `HandshakeInfo.getPrincipal()` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/reactive/socket/HandshakeInfo.html
3. Spring Framework 6.1 — WebSocketClient custom headers Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/reactive/socket/client/WebSocketClient.html
4. Spring Security — WebFlux Security, authentication and request matchers: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
5. Spring Security — WebSocket Security / STOMP message authorization (Servlet integration): https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/websocket.html
6. Spring Security — RSocket Security, SETUP vs per-request auth and `authorizePayload`: https://docs.spring.io/spring-security/reference/6.5/reactive/integrations/rsocket.html
7. Spring Framework — STOMP message authorization: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authorization.html
8. RFC 6455 — The WebSocket Protocol: https://www.rfc-editor.org/rfc/rfc6455
9. OWASP — WebSocket Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html
