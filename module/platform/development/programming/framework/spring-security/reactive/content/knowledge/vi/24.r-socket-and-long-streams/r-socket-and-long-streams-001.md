# Phạm vi hỗ trợ RSocket Security và sự khác biệt với bảo mật HTTP WebFlux

## 1. Bài học dành cho ai và giải quyết vấn đề gì?

Bài thuộc nhóm **RSocket và luồng dài** trong module **Spring Security - reactive**. Khi xây dựng hệ thống cập nhật trạng thái, bảng giá, chat, telemetry hoặc các luồng tương tác hai chiều, nhiều nhóm phát triển dùng Spring WebFlux để cung cấp HTTP API và RSocket để truyền thông điệp liên tục. Cả hai đều dựa trên Reactor `Mono`/`Flux`, nhưng **RSocket Security không phải là HTTP WebFlux Security chạy trên một cổng khác**.

Với HTTP WebFlux, Spring Security kiểm tra các **HTTP exchanges** qua `SecurityWebFilterChain`, HTTP headers, URL và HTTP status. Với RSocket, Spring Security kiểm tra **RSocket SETUP và payload exchanges** qua `SocketAcceptorInterceptor`/`PayloadSocketAcceptorInterceptor`, metadata của giao thức, routing và RSocket error frames. Ngay cả khi RSocket được vận chuyển bên trong WebSocket, RSocket messages **không tự trở thành HTTP requests mới** để `ServerHttpSecurity.authorizeExchange` kiểm lại.

Sau bài, bạn có thể:

1. Giải thích RSocket protocol, SETUP, route, metadata và bốn interaction models: request-response, fire-and-forget, request-stream, request-channel.
2. Phân biệt lớp transport TCP/WebSocket với lớp application RSocket và lớp HTTP WebFlux.
3. Nắm đúng phạm vi `@EnableRSocketSecurity`, `RSocketSecurity`, `PayloadSocketAcceptorInterceptor`, `AuthenticationPayloadInterceptor`, `AuthorizationPayloadInterceptor` và `RSocketSecurityAutoConfiguration`.
4. Phân biệt authentication **ở SETUP** với authentication **trên từng request** (metadata của request đầu), đặc biệt với connection dùng chung cho nhiều user.
5. Viết rule `.setup()`, `.route(...)`, `.anyRequest()` và `.anyExchange()` theo đúng thứ tự; hiểu request-level authorization không đồng nghĩa kiểm từng item trong một stream dài.
6. Dùng Simple Authentication metadata và JWT Bearer Authentication metadata đúng loại, không nhầm với HTTP `Authorization: Basic/Bearer`.
7. Xây dựng ví dụ Java 17+, Spring Boot 3.3.13 chạy **HTTP WebFlux 8080** và **RSocket TCP 7000** trong cùng một ứng dụng, nhưng với **hai security policies độc lập**.
8. Kiểm thử HTTP bằng `WebTestClient` và RSocket bằng `RSocketRequester` + `StepVerifier`, gồm đúng/sai credential, thiếu role, SETUP failure và request-stream.
9. Nhận biết những giới hạn: token hết hạn khi stream đang mở, revoke quyền, stream data tenant isolation, backpressure, fan-out, cancellation, TLS, proxy và CORS/CSRF.
10. Chọn đúng giải pháp cho SSE, HTTP streaming, WebSocket hoặc RSocket thay vì giả định mọi giao thức có cùng security guarantees.

**Kết luận chính:** Cần thiết kế **hai lớp chính sách rõ ràng** khi cùng chạy HTTP WebFlux và RSocket. Đừng tin rằng bảo vệ `GET /api/**` hoặc WebSocket handshake tự động bảo vệ mọi RSocket route và mọi thông điệp về sau.

## 2. RSocket là giao thức gì?

RSocket là giao thức truyền thông điệp hai chiều (bidirectional), hỗ trợ multiplexing nhiều logical requests trên một connection, demand/backpressure theo mô hình Reactive Streams và bốn interaction models.

| Interaction model | Chiều dữ liệu | Spring requester thường dùng |
| --- | --- | --- |
| Request-Response | Gửi một yêu cầu, nhận một phản hồi | `retrieveMono(...)` |
| Fire-and-Forget | Gửi thông điệp, không chờ response payload | `send()` |
| Request-Stream | Gửi một yêu cầu, nhận nhiều items | `retrieveFlux(...)` |
| Request-Channel | Hai phía có thể gửi stream nhiều items | `data(Publisher)` + `retrieveFlux(...)` |

Các interaction models này **không phải HTTP methods**. Một RSocket `request-stream` không phải một HTTP GET, và một `fire-and-forget` không mặc nhiên tương đương HTTP POST.

### 2.1. SETUP, route, metadata và data

Khi RSocket client tạo connection qua TCP hoặc WebSocket, nó gửi một RSocket **SETUP frame** với các thông số định dạng dữ liệu/metadata và có thể mang authentication metadata.

```text
Client / requester                        Server / responder
        |                                            |
        | -- TCP connect / WebSocket upgrade ------> |
        |                                            |
        | -- RSocket SETUP frame ------------------> |
        |    data mime type                          |
        |    metadata mime type                      |
        |    optional auth metadata                  |
        |                                            |
        | -- REQUEST_RESPONSE route=demo.echo -----> |
        |<-------------- PAYLOAD response ---------- |
        |                                            |
        | -- REQUEST_STREAM route=demo.stream -----> |
        |<------------- PAYLOAD item 1 ------------- |
        |<------------- PAYLOAD item 2 ------------- |
        | ---- REQUEST_N demand/cancel, ... -------> |
        |<------------- PAYLOAD item N ------------- |
```

RSocket messages có **data** và **metadata** riêng. Route thường được gửi bằng routing metadata; thông tin xác thực được gửi bằng metadata type theo Authentication Metadata Extension. **Đừng đặt credential vào data payload rồi mong RSocket Security DSL tự nhận biết**.

RSocket SETUP là cấp connection, không phải một HTTP login endpoint. Với transport TCP, hoàn toàn không có HTTP URL/method/status trong từng RSocket request. Với WebSocket, chỉ có **HTTP upgrade handshake** ở lúc mở kết nối; sau đó application messages vẫn là frames của RSocket.

### 2.2. Backpressure không phải authorization

Trong Request-Stream và Request-Channel, `REQUEST_N` cho biết consumer đang yêu cầu bao nhiêu messages; `CANCEL` hủy stream. Cơ chế này giúp tránh producer gửi vô hạn mà consumer không nhận kịp.

Nó **không kiểm tra** xem item thứ N có còn được phép xem khi role vừa bị thu hồi. Cũng không kiểm tra record thuộc tenant nào. Phải tách:
- **Transport flow control:** demand/cancel, memory limits, payload limits;
- **Authentication:** credentials ở SETUP/request;
- **Authorization:** role/route/resource/tenant;
- **Continuous policy:** expiry/revocation và stream lifetime khi cần;
- **Data isolation:** lọc dữ liệu theo user/tenant trước khi fan-out.

Một stream được chấp nhận ban đầu có thể chạy nhiều phút/giờ; kiểm quyền một lần không tự động xử lý mọi thay đổi quyền sau đó.

## 3. HTTP WebFlux Security và RSocket Security khác nhau thế nào?

| Khía cạnh | HTTP WebFlux | RSocket |
| --- | --- | --- |
| Transport | HTTP/1.1, HTTP/2 (tùy server) | TCP hoặc RSocket-over-WebSocket |
| Security integration | `WebFilterChainProxy`, `SecurityWebFilterChain`, `ServerHttpSecurity` | `SecuritySocketAcceptorInterceptor`/`PayloadSocketAcceptorInterceptor`, `RSocketSecurity` |
| Đơn vị cần kiểm | HTTP exchange | RSocket SETUP, request payload exchange, route |
| Định danh route | Path/method, ví dụ GET `/api/orders/1` | Routing metadata, ví dụ `orders.find` |
| Credentials | HTTP Authorization header, cookies, session, mTLS proxy... | Authentication metadata trong SETUP/request, transport TLS/mTLS |
| AuthN | HTTP `AuthenticationWebFilter`/resource server flow | `AuthenticationPayloadInterceptor` qua `ReactiveAuthenticationManager` |
| AuthZ | `authorizeExchange`, `ServerWebExchangeMatcher` | `authorizePayload`, `setup()`, `route()`, `anyRequest()` |
| Kết quả từ chối | 401/403 HTTP, `WWW-Authenticate` | RSocket error frame/exception; **không phải HTTP 401/403** |
| Lưu phiên | WebSession/Session cookie khi cấu hình | Connection-level context hoặc per-request metadata, tùy design |
| Dòng dài | HTTP streaming/SSE qua một request | Request-Stream/Request-Channel với protocol demand |
| Re-auth từng item? | Không mặc nhiên kiểm lại từng SSE event | Không mặc nhiên kiểm lại từng RSocket PAYLOAD item |
| Browser CORS/CSRF | CORS HTTP/CSRF cookie-based | CORS ảnh hưởng handshake WebSocket/HTTP ở tầng phù hợp; payload RSocket có policy riêng |
| Test | `WebTestClient`, mock HTTP auth | `RSocketRequester`, StepVerifier, security metadata |
| Entry point | `@RestController`, HTTP handlers | `@Controller`/`@MessageMapping` RSocket responders |

**Đừng dùng `@GetMapping` cho RSocket route** hoặc `@MessageMapping` để chặn một HTTP path. Cùng là Spring, nhưng annotation handlers thuộc hai messaging models khác nhau.

### 3.1. Ví dụ “đã bảo vệ HTTP nên RSocket cũng an toàn” — sai

```java
// HTTP SecurityWebFilterChain chỉ bảo vệ HTTP exchanges.
@Bean
SecurityWebFilterChain httpSecurity(ServerHttpSecurity http) {
    return http.authorizeExchange(ex -> ex
            .pathMatchers("/api/**").authenticated()
            .anyExchange().permitAll())
        .build();
}
```

Code trên **không** tạo policy cho `RSocketRequester.route("admin.export")` gửi qua TCP. Nếu RSocket server mở cổng riêng, một client có thể kết nối trực tiếp tới cổng RSocket mà không bao giờ gọi `/api/**`. Bạn phải khai báo RSocket Security cho RSocket server.

### 3.2. RSocket-over-WebSocket cũng không đồng nhất HTTP

```text
Browser / RSocket client
   |
   | HTTP GET /rsocket + Upgrade: websocket
   v
WebFlux server: HTTP handshake/filter rules
   |
   | Sau khi upgrade thành công
   v
RSocket SETUP + REQUEST_* + PAYLOAD frames
   |
   v
RSocket Security / @MessageMapping routes
```

Nếu HTTP handshake yêu cầu cookie hoặc Bearer, đó là **lớp kiểm đầu tiên**. Nó không tự làm `SecurityContext` của mọi RSocket message trở thành user đã xác thực, trừ khi bạn có **tích hợp identity propagation được kiểm chứng**. Ngược lại, một handshake được permitAll không đồng nghĩa mọi RSocket route sẽ permitAll nếu RSocket Security được cấu hình đúng.

Khi dùng RSocket qua WebSocket, nên kiểm cả:
- Allowed origins, TLS `wss://`, proxy upgrade/idle timeouts;
- HTTP handshake authorization nếu cần;
- RSocket SETUP và route authorization;
- Credential forwarding/trust boundary giữa handshake và metadata;
- Reconnect và connection lifecycle.

## 4. Phạm vi tích hợp chính thức của Spring Security RSocket

Spring Security hỗ trợ RSocket thông qua `SocketAcceptorInterceptor`. `PayloadSocketAcceptorInterceptor` chuyển RSocket interaction thành `PayloadExchange` để các `PayloadInterceptor` xử lý. Các lớp tiêu biểu:

| Thành phần | Vai trò |
| --- | --- |
| `@EnableRSocketSecurity` | Bật hạ tầng cấu hình Spring Security cho RSocket |
| `RSocketSecurity` | DSL xác thực/phân quyền RSocket |
| `PayloadSocketAcceptorInterceptor` | Tập hợp các payload interceptors bảo mật |
| `SecuritySocketAcceptorInterceptor` | Nối security payload interceptor vào RSocket acceptor |
| `AuthenticationPayloadInterceptor` | Chuyển authentication metadata thành attempt và gọi reactive manager |
| `AuthorizationPayloadInterceptor` | Gọi reactive authorization manager cho SETUP/request |
| `ReactiveAuthenticationManager` | Xác minh credential (simple hoặc JWT tương ứng) |
| `AuthenticationPayloadExchangeConverter` | Đọc RSocket Simple Authentication metadata |
| `BearerPayloadExchangeConverter` | Đọc RSocket Bearer Token Authentication metadata |
| `ReactiveJwtDecoder` | Validate JWT nếu dùng `.jwt(...)` |
| `RSocketRequester` | Requester của Spring Messaging; gửi route/data/metadata |
| `@MessageMapping` | Handler RSocket route trong annotated responder |
| `RSocketMessageHandler` | Dispatch messages vào handler |

Spring Boot có `RSocketSecurityAutoConfiguration` để nối `SecuritySocketAcceptorInterceptor` vào RSocket server nếu các dependencies/beans phù hợp. **Khi dùng Spring Boot auto-configuration, không tự thêm một interceptor thứ hai nếu chưa biết vì sao cần**, tránh chạy auth logic hai lần. Trong setup thuần không Boot, phải kết nối security interceptor với RSocket server bằng API RSocket server customizer tương ứng.

### 4.1. DSL cơ bản

```java
@Bean
PayloadSocketAcceptorInterceptor rsocketInterceptor(
        RSocketSecurity rsocket) {
    return rsocket
        .authorizePayload(auth -> auth
            .anyRequest().authenticated()
            .anyExchange().permitAll())
        .simpleAuthentication(Customizer.withDefaults())
        .build();
}
```

Đây là **mảnh cấu hình minh họa**, không phải class đầy đủ. Nó cho RSocket Security biết cách giải mã Simple Authentication metadata và yêu cầu authenticated cho các request exchanges mang routing metadata. Không có `SecurityWebFilterChain` HTTP nào trong DSL này.

### 4.2. Các rule phải theo thứ tự

```java
rsocket.authorizePayload(auth -> auth
    .setup().hasRole("SETUP")
    .route("admin.*").hasRole("ADMIN")
    .route("events.stream").hasRole("STREAM")
    .anyRequest().authenticated()
    .anyExchange().permitAll());
```

Ý nghĩa:
- `setup()`: kiểm connection SETUP; có thể yêu cầu role riêng cho caller được phép mở connection.
- `route("admin.*")`: kiểm route metadata cụ thể, ở đây các route dạng admin.
- `route("events.stream")`: quyền dành cho request với route tương ứng.
- `anyRequest()`: fallback cho các requests chưa match route trước.
- `anyExchange()`: fallback cho các exchange không thuộc những nhóm trước; trong ví dụ thường permit các payload frames không có route metadata.

**Quy tắc đầu tiên khớp sẽ được áp dụng**, không tiếp tục cộng tất cả rules. Nếu đặt `anyRequest().permitAll()` lên trước `route("admin.*").hasRole("ADMIN")` thì route admin có thể bị mở ngoài ý định.

**Vì sao cuối cùng có `anyExchange().permitAll()`?** Một request-stream/request-channel gồm nhiều payloads, nhưng không phải payload/frame nào cũng có route metadata như request ban đầu. Một rule `anyExchange().denyAll()` đặt bừa có thể làm hỏng subsequent frames của stream. Đây **không** phải là cho phép unauthenticated request đầu: `anyRequest()` bảo vệ request initiation đã có route. Tuy nhiên phải kiểm behavior với mọi frame type trong ứng dụng thật.

### 4.3. Có thể bảo vệ SETUP và request cùng lúc

Ba kiểu:
1. **SETUP authentication**: connection gắn một caller duy nhất, hợp khi kết nối thuộc một user/service.
2. **Per-request authentication**: connection dùng chung cho nhiều user; mỗi request mang metadata riêng.
3. **Kết hợp**: SETUP xác minh application/service identity có role `SETUP`, từng request xác minh user identity/scope khác.

Cách 3 thường hữu ích khi một gateway/server application mở một RSocket connection chung nhưng phục vụ nhiều end users. Nếu chỉ SETUP theo credential của service mà tất cả requests dùng lại connection, bạn **không thể** kết luận caller của từng request là end user thật.

## 5. Authentication tại SETUP và theo request

### 5.1. SETUP authentication

```text
Client alice
  -> TCP connect
  -> SETUP(authentication metadata: alice/password hoặc bearer token)
  -> Server xác minh và gắn identity ở connection scope
  -> Request 1, request 2, request-stream dùng connection đã thiết lập
```

Thích hợp:
- Mobile app kết nối cá nhân;
- Một service account riêng cho connection;
- Stream mà connection có cùng một identity suốt đời;
- Ngăn caller không có authority nhất định mở RSocket connection.

Hạn chế:
- Credential có thể hết hạn **sau khi setup thành công**.
- Role/tenant có thể đổi trong lúc connection tồn tại.
- Nếu nhiều users chia sẻ connection, identity setup không đủ để phân biệt từng user.
- Không nên cache Authentication global cho mọi connections.

**Không giả định** Spring Security tự chạy lại xác minh JWT ở mỗi PAYLOAD chỉ vì token hết hạn giữa stream; cần chính sách token lifetime/revalidation/reconnect và stream termination theo threat model.

### 5.2. Request authentication

```text
Một connection ứng dụng mở bằng credential service
  |
  +-- REQUEST route=orders.find
  |      auth metadata: end-user A
  |      -> token verify -> subject A
  |
  +-- REQUEST route=orders.find
  |      auth metadata: end-user B
  |      -> token verify -> subject B
  |
  +-- REQUEST_STREAM route=events
         auth metadata: end-user C ở request đầu
         -> sau đó nhiều PAYLOAD frames
```

Trong Spring requester:

```java
// MẢNH MINH HỌA, giả định requester và authMimeType đã cấu hình.
return requester.route("orders.find")
        .metadata(bearerTokenMetadata, authMimeType)
        .data(orderId)
        .retrieveMono(OrderDto.class);
```

Đây là **per-request auth metadata**, không phải HTTP `Authorization` header. Nếu gửi token user tại SETUP trên một connection shared giữa mọi users, bạn có thể tạo **identity leakage/cross-tenant authorization** nghiêm trọng.

### 5.3. Phân quyền route khác phân quyền dữ liệu

`.route("orders.find").hasAuthority("SCOPE_orders:read")` chỉ kiểm scope cho loại request; handler/service vẫn phải kiểm:
- `sub`/client ID đã được xác minh;
- `tenant_id` được cấp;
- Order thuộc tenant + owner đúng;
- Policy/row-level permissions hiện hành;
- Không trả payload của tenant khác trong shared stream.

RSocket Security DSL **không tự biến route parameter thành ownership check**.

## 6. Simple Authentication Metadata và JWT Metadata

### 6.1. Simple Authentication

RSocket Simple Authentication Metadata Extension gửi cặp username/password trong metadata. Để client encode, thêm:

```java
RSocketRequester.Builder builder = ...;

builder.rsocketStrategies(
    strategies -> strategies.encoder(new SimpleAuthenticationEncoder()));
```

Gửi SETUP metadata:

```java
MimeType authMime = MimeTypeUtils.parseMimeType(
    WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());

UsernamePasswordMetadata credentials =
    new UsernamePasswordMetadata("alice", "lab-only");

Mono<RSocketRequester> connection = builder
    .setupMetadata(credentials, authMime)
    .connectTcp("localhost", 7000);
```

**Rất quan trọng:** Simple Authentication metadata **không mã hóa bí mật username/password**. Nếu vận chuyển qua TCP cleartext, credential có thể bị quan sát trên network. Lab phía dưới cố tình bind RSocket TCP vào `127.0.0.1` và dùng user/password mẫu. **Production phải dùng TLS/mTLS hoặc secure transport phù hợp**, quản trị password và rate limit. Đừng copy lab TCP cleartext cho traffic liên máy.

`RSocketSecurity.basicAuthentication(...)` là cơ chế cũ, được thay bằng `simpleAuthentication(...)` ở các phiên bản Spring Security mới. Không chép các mẫu `BasicAuthenticationEncoder` từ tài liệu cổ vào 6.3 nếu chưa kiểm compatibility.

### 6.2. JWT Bearer Authentication Metadata

RSocket Security hỗ trợ Bearer Token Authentication Metadata Extension cho JWT. Trên receiver:

```java
// MẢNH CẤU HÌNH: trong RSocketSecurity bean riêng.
rsocket
    .authorizePayload(auth -> auth
        .anyRequest().authenticated()
        .anyExchange().permitAll())
    .jwt(Customizer.withDefaults());
```

Cần một `ReactiveJwtDecoder` đã cấu hình issuer/signature/JWK, validator timestamp và **audience phù hợp với RSocket service**. Tham khảo Spring Security JWT Resource Server để dựng decoder; nhưng **bean HTTP `oauth2ResourceServer().jwt()` không phải thay thế cho việc cấu hình `RSocketSecurity.jwt(...)`**.

Trên requester:

```java
MimeType authMime = MimeTypeUtils.parseMimeType(
    WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());

BearerTokenMetadata token =
    new BearerTokenMetadata("JWT_ACCESS_TOKEN_VALUE");

// Theo connection:
Mono<RSocketRequester> connection = builder
    .setupMetadata(token, authMime)
    .connectTcp("localhost", 7000);

// Hoặc theo request:
Flux<Event> events = requester
    .route("events.stream")
    .metadata(token, authMime)
    .retrieveFlux(Event.class);
```

Các đoạn trên là **fragment minh họa**, không có JWT thật hay model `Event`. Chỉ dùng **access token** đúng audience/scopes/issuer, không dùng ID token như bearer credential tùy tiện. Không lưu JWT trong log, traces hoặc raw error messages. Với multi-tenant, token phải được validate và mapping đúng.

### 6.3. Metadata loại nào?

RSocket Authentication Metadata Extension dùng well-known MIME `message/x.rsocket.authentication.v0` cho bao metadata xác thực, với subtype bên trong Simple/Bearer; Spring Security cung cấp `UsernamePasswordMetadata` và `BearerTokenMetadata`. Đừng gắn metadata dưới content MIME tùy tiện hay đặt token thành JSON body rồi trông chờ framework giải mã tự động.

### 6.4. Request-time JWT không phải automatic refresh

Nếu token hết hạn trước khi request sau bắt đầu, request đó phải bị từ chối nếu decoder/validator đang kiểm đúng. Nhưng **một request stream đang hoạt động không đồng nghĩa mỗi PAYLOAD frame sẽ tự gửi lại JWT và kiểm exp lần nữa**. Nếu cần revocation nhanh:
- Giới hạn maximum stream duration hoặc TTL connection;
- Buộc reconnect/re-authentication sau khoảng thời gian;
- Kiểm entitlement tại thời điểm phát dữ liệu quan trọng;
- Hủy stream nếu user/tenant bị revoke theo policy;
- Thiết kế cache invalidation và truyền thông tin revoke đúng nguồn;
- Không dùng `Flux.interval` vô hạn mà quên quota/cancellation.

## 7. Ví dụ Java 17+ chạy hai giao thức trong cùng ứng dụng

**Mục tiêu demo:** HTTP WebFlux ở cổng 8080, RSocket TCP ở cổng 7000. Cùng một `MapReactiveUserDetailsService` lưu hai user, nhưng hai policies khác nhau:

| User | Password (lab) | Granted role | HTTP `/http/private` | RSocket `demo.echo` | RSocket `demo.stream` |
| --- | --- | --- | --- | --- | --- |
| `alice` | `lab-only` | `ROLE_STREAM` | 403 | Được | Được |
| `bob` | `lab-only` | `ROLE_WEB` | Được | Được | Từ chối |
| Anonymous | Không | Không | 401 | SETUP bị từ chối | Không vào route |

Chính sự khác biệt này cho thấy **identity store có thể được chia sẻ nhưng policy HTTP và RSocket không tự động chia sẻ**. RSocket lab dùng authentication ở SETUP; test per-request sẽ có hướng dẫn riêng sau.

### 7.1. Cấu trúc

```text
webflux-rsocket-boundaries/
  settings.gradle
  build.gradle
  src/main/resources/application.yml
  src/main/java/example/boundaries/
    BoundariesApplication.java
    IdentityConfig.java
    HttpSecurityConfig.java
    RSocketSecurityConfig.java
    HttpRoutes.java
    RSocketRoutes.java
  src/test/java/example/boundaries/
    SecurityBoundaryTests.java
```

Java classes cùng package `example.boundaries`. Tránh dùng `@RestController` cho handler RSocket: `@MessageMapping` thuộc Spring Messaging.

### 7.2. settings.gradle

```groovy
rootProject.name = 'webflux-rsocket-boundaries'
```

### 7.3. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

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
    implementation 'org.springframework.boot:spring-boot-starter-rsocket'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    // RSocket Security là module riêng, không chỉ
    // thêm starter-security / resource-server HTTP.
    implementation 'org.springframework.security:spring-security-rsocket'
    implementation 'org.springframework.security:spring-security-messaging'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-rsocket` cung cấp RSocket transport/messaging. `spring-security-rsocket` là module triển khai RSocket Security; `spring-security-messaging` cung cấp hạ tầng security messaging liên quan. `spring-boot-starter-webflux` là HTTP WebFlux độc lập. Dùng Spring Boot BOM thay vì tùy tiện ghép các phiên bản Spring Security khác nhau.

### 7.4. application.yml

```yaml
server:
  address: 127.0.0.1
  port: 8080

spring:
  rsocket:
    server:
      transport: tcp
      address: 127.0.0.1
      port: 7000
```

Ở đây TCP RSocket chạy **không có HTTP** trên cổng 7000, trong khi WebFlux xử lý HTTP trên cổng 8080. Hai cổng được bind localhost để giảm rủi ro từ demo Simple Authentication cleartext. Production cần TLS và network policy; không chỉ mở cổng này ra Internet.

### 7.5. BoundariesApplication.java

```java
package example.boundaries;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BoundariesApplication {

    public static void main(String[] args) {
        SpringApplication.run(BoundariesApplication.class, args);
    }
}
```

### 7.6. IdentityConfig.java

```java
package example.boundaries;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;

@Configuration
public class IdentityConfig {

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
                .password("{noop}lab-only")
                .roles("STREAM")
                .build();

        UserDetails bob = User.withUsername("bob")
                .password("{noop}lab-only")
                .roles("WEB")
                .build();

        return new MapReactiveUserDetailsService(alice, bob);
    }
}
```

`{noop}` chỉ dành lab; không hash password và không chống brute-force. Không dùng hardcoded password hoặc in-memory user store khi triển khai công khai. Production cần password encoder phù hợp, account lockout/rate limit và identity provider đáng tin.

User alice có `ROLE_STREAM`, bob có `ROLE_WEB`. Dữ liệu user store được sử dụng để kiểm credentials, nhưng **HTTP SecurityConfig và RSocketSecurityConfig quyết định permission riêng**.

### 7.7. HttpSecurityConfig.java

```java
package example.boundaries;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableWebFluxSecurity
public class HttpSecurityConfig {

    @Bean
    SecurityWebFilterChain webfluxSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(
                                HttpMethod.GET, "/public/ping")
                        .permitAll()
                        .pathMatchers(
                                HttpMethod.GET, "/http/private")
                        .hasRole("WEB")
                        .anyExchange().denyAll())
                .httpBasic(withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
```

Chính sách **HTTP**:
- `GET /public/ping`: anonymous 200.
- `GET /http/private`: role WEB → bob 200; alice 403; thiếu credentials 401.
- HTTP Basic authentication chỉ dùng để chứng minh policy độc lập; trong production yêu cầu HTTPS, rate limiting và auth scheme phù hợp.
- `anyExchange().denyAll()` ngăn HTTP routes ngoài đề bài.
- Không khai báo bất kỳ `RSocketSecurity` nào ở đây: HTTP WebFilterChain không match `demo.echo` hay `demo.stream` là metadata routes.

### 7.8. RSocketSecurityConfig.java

```java
package example.boundaries;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.rsocket.EnableRSocketSecurity;
import org.springframework.security.config.annotation.rsocket.RSocketSecurity;
import org.springframework.security.rsocket.core.PayloadSocketAcceptorInterceptor;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableRSocketSecurity
public class RSocketSecurityConfig {

    @Bean
    PayloadSocketAcceptorInterceptor rsocketInterceptor(
            RSocketSecurity rsocket) {

        return rsocket
                .authorizePayload(authorize -> authorize
                        // Yêu cầu xác thực khi mở connection.
                        .setup().authenticated()

                        // Route demo.echo cần user hợp lệ.
                        .route("demo.echo").authenticated()

                        // Route stream chỉ dành ROLE_STREAM.
                        .route("demo.stream").hasRole("STREAM")

                        // Request khác bị chặn mặc định.
                        .anyRequest().denyAll()

                        // Các frames không có route metadata
                        // trong một interaction đã bắt đầu.
                        .anyExchange().permitAll())
                .simpleAuthentication(withDefaults())
                .build();
    }
}
```

**Giải thích chi tiết:**

1. `@EnableRSocketSecurity` cho phép dựng DSL dành riêng RSocket.
2. `PayloadSocketAcceptorInterceptor` được Spring Boot gắn vào RSocket acceptor khi có đúng dependencies/auto-configuration; không cần tự khai global HTTP WebFilter.
3. `.setup().authenticated()` yêu cầu Simple Authentication metadata ngay lúc SETUP. Đừng nhầm với Spring WebFlux HTTP Basic cookie/session.
4. `.route("demo.echo").authenticated()` cho phép cả alice và bob gọi route.
5. `.route("demo.stream").hasRole("STREAM")` chỉ cho alice được mở request stream.
6. `.anyRequest().denyAll()` không cho route không được liệt kê, dù SETUP đã authenticated.
7. `.anyExchange().permitAll()` cho phép các payload exchanges không thuộc request đầu (không mang routing metadata) đi tiếp, cần thiết cho một số streaming frames. **Điều này không tự mở quyền route `demo.stream`**.
8. `.simpleAuthentication(withDefaults())` bật xử lý RSocket Simple Authentication metadata bằng reactive authentication infrastructure. User store nằm ở bean IdentityConfig.
9. Các rules chạy theo thứ tự, first-match-wins. Đừng đưa `anyRequest().permitAll()` trước một route bị hạn chế.
10. Route security chỉ kiểm loại hành động và role; dữ liệu có owner/tenant vẫn cần kiểm trong service.

### 7.9. HttpRoutes.java

```java
package example.boundaries;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HttpRoutes {

    @GetMapping("/public/ping")
    public Map<String, String> ping() {
        return Map.of("message", "HTTP-PONG");
    }

    @GetMapping("/http/private")
    public Map<String, String> privateInfo() {
        return Map.of("message", "HTTP-WEB-ONLY");
    }
}
```

Đây là controller HTTP thật, chạy ở `http://127.0.0.1:8080`. `@GetMapping` không định nghĩa RSocket route. Không có request handler HTTP `/demo.echo` hay `/demo.stream`.

### 7.10. RSocketRoutes.java

```java
package example.boundaries;

import java.time.Duration;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
public class RSocketRoutes {

    @MessageMapping("demo.echo")
    public Mono<String> echo(@Payload String name) {
        return Mono.just("echo:" + name);
    }

    @MessageMapping("demo.stream")
    public Flux<String> stream(@Payload Integer requestedCount) {
        int n = Math.max(0, Math.min(
                requestedCount == null ? 0 : requestedCount, 5));

        return Flux.range(1, n)
                .delayElements(Duration.ofMillis(150))
                .map(index -> "event-" + index);
    }
}
```

Giải thích:
- `@MessageMapping("demo.echo")` xử lý RSocket Request-Response, trả `Mono<String>`.
- `@MessageMapping("demo.stream")` xử lý RSocket Request-Stream, trả `Flux<String>`.
- `@Payload` lấy message data, không lấy `Authorization` header.
- `requestedCount` bị clamp từ 0 tới 5 để demo không sinh stream vô hạn từ một input tùy ý.
- `Flux.range(...).delayElements(...)` mô phỏng sự kiện đều đặn; đây **không** phải business stream production.
- Authorization route đã chạy trước handler, nhưng nếu stream chứa dữ liệu nhạy cảm theo tenant, handler/service vẫn cần filter mỗi record theo tenant/owner của identity đã xác minh.
- Không gọi `block()` hay tự `subscribe()` trong responder.

### 7.11. Chạy server

Yêu cầu JDK 17+ và Gradle phù hợp Spring Boot 3.3.13. Từ thư mục dự án:

```bash
gradle bootRun
```

Nếu có Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows sử dụng `gradlew.bat bootRun`. Ứng dụng có hai listeners:
- HTTP WebFlux: `127.0.0.1:8080`.
- RSocket TCP: `127.0.0.1:7000`.

**Không dùng browser URL `http://127.0.0.1:7000` để kiểm RSocket**: đó là binary TCP protocol, không phải HTTP. Dùng `RSocketRequester` hoặc client hỗ trợ RSocket.

### 7.12. Thử HTTP

```bash
curl -i http://127.0.0.1:8080/public/ping
curl -i http://127.0.0.1:8080/http/private
curl -i -u bob:lab-only \
  http://127.0.0.1:8080/http/private
curl -i -u alice:lab-only \
  http://127.0.0.1:8080/http/private
```

Kết quả **dự kiến**:
1. Public ping → HTTP 200 và `{"message":"HTTP-PONG"}`.
2. Private không header → HTTP 401 với Basic challenge.
3. Bob đúng password + ROLE_WEB → HTTP 200 và `{"message":"HTTP-WEB-ONLY"}`.
4. Alice đúng password nhưng thiếu ROLE_WEB → HTTP 403.

Các response có thể chứa thêm headers do Spring Security/Netty. Không dùng username/password hardcoded hoặc HTTP cleartext ngoài localhost lab.

## 8. Kiểm thử đầy đủ hai security chains

Phần kiểm thử này là **RSocket client chạy Java thật**, không phải `mockJwt()` hay một HTTP test giả lập RSocket. Ta dùng:
- `WebTestClient` để kiểm HTTP;
- `RSocketRequester.Builder` kết nối RSocket TCP và gửi Simple Authentication metadata;
- `StepVerifier` để kiểm async success/error và chuỗi stream;
- `@LocalRSocketServerPort` để tránh phụ thuộc cổng 7000 khi chạy CI.

### 8.1. SecurityBoundaryTests.java

Tạo `src/test/java/example/boundaries/SecurityBoundaryTests.java`:

```java
package example.boundaries;

import java.time.Duration;

import io.rsocket.metadata.WellKnownMimeType;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.rsocket.server.LocalRSocketServerPort;
import org.springframework.http.HttpHeaders;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.security.rsocket.metadata.SimpleAuthenticationEncoder;
import org.springframework.security.rsocket.metadata.UsernamePasswordMetadata;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "spring.rsocket.server.port=0")
@AutoConfigureWebTestClient
class SecurityBoundaryTests {

    private static final MimeType AUTH_MIME =
            MimeTypeUtils.parseMimeType(
                    WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION
                            .getString());

    @Autowired
    WebTestClient http;

    @Autowired
    ObjectProvider<RSocketRequester.Builder> requesterBuilders;

    @LocalRSocketServerPort
    int rsocketPort;

    private Mono<RSocketRequester> connect(
            String username, String password) {
        return requesterBuilders.getObject()
                .rsocketStrategies(strategies ->
                        strategies.encoder(
                                new SimpleAuthenticationEncoder()))
                .setupMetadata(
                        new UsernamePasswordMetadata(
                                username, password),
                        AUTH_MIME)
                .connectTcp("127.0.0.1", rsocketPort);
    }

    @Test
    void publicHttpRouteIsOpen() {
        http.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("HTTP-PONG");
    }

    @Test
    void anonymousHttpPrivateRouteIs401() {
        http.get().uri("/http/private")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().exists(
                        HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void bobCanUseHttpPrivateRoute() {
        http.get().uri("/http/private")
                .headers(h -> h.setBasicAuth("bob", "lab-only"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message")
                .isEqualTo("HTTP-WEB-ONLY");
    }

    @Test
    void aliceHasRSocketRoleButNotHttpRole() {
        http.get().uri("/http/private")
                .headers(h -> h.setBasicAuth("alice", "lab-only"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void aliceCanEchoViaRSocket() {
        StepVerifier.create(
                connect("alice", "lab-only")
                        .flatMap(requester -> requester
                                .route("demo.echo")
                                .data("Java")
                                .retrieveMono(String.class)
                                .doFinally(signal ->
                                        requester.rsocket().dispose())))
                .assertNext(value ->
                        assertEquals("echo:Java", value))
                .verifyComplete();
    }

    @Test
    void aliceCanOpenThreeItemStream() {
        StepVerifier.create(
                connect("alice", "lab-only")
                        .flatMapMany(requester -> requester
                                .route("demo.stream")
                                .data(3)
                                .retrieveFlux(String.class)
                                .doFinally(signal ->
                                        requester.rsocket().dispose())))
                .expectNext("event-1", "event-2", "event-3")
                .expectComplete()
                .verify(Duration.ofSeconds(15));
    }

    @Test
    void bobCanEchoButCannotOpenProtectedStream() {
        StepVerifier.create(
                connect("bob", "lab-only")
                        .flatMapMany(requester -> requester
                                .route("demo.stream")
                                .data(2)
                                .retrieveFlux(String.class)
                                .doFinally(signal ->
                                        requester.rsocket().dispose())))
                .expectError()
                .verify(Duration.ofSeconds(15));
    }

    @Test
    void wrongSetupPasswordIsRejected() {
        StepVerifier.create(
                connect("alice", "incorrect-password")
                        .flatMap(requester -> requester
                                .route("demo.echo")
                                .data("test")
                                .retrieveMono(String.class)
                                .doFinally(signal ->
                                        requester.rsocket().dispose())))
                .expectError()
                .verify(Duration.ofSeconds(15));
    }

    @Test
    void missingSetupCredentialsAreRejected() {
        StepVerifier.create(
                requesterBuilders.getObject()
                        .connectTcp("127.0.0.1", rsocketPort)
                        .flatMap(requester -> requester
                                .route("demo.echo")
                                .data("test")
                                .retrieveMono(String.class)
                                .doFinally(signal ->
                                        requester.rsocket().dispose())))
                .expectError()
                .verify(Duration.ofSeconds(15));
    }

    @Test
    void unknownRouteDeniedEvenForAlice() {
        StepVerifier.create(
                connect("alice", "lab-only")
                        .flatMap(requester -> requester
                                .route("demo.not-registered")
                                .data("test")
                                .retrieveMono(String.class)
                                .doFinally(signal ->
                                        requester.rsocket().dispose())))
                .expectError()
                .verify(Duration.ofSeconds(15));
    }
}
```

Kiểm thử trên **không** assert chính xác message/class của RSocket exception; Spring/RSocket phiên bản khác nhau có thể mã hóa `REJECTED_SETUP`, `REJECTED`, `APPLICATION_ERROR` hay wrapper khác. Bất biến bảo mật là **RSocket requester nhận error, không được nhận protected data**.

**Vì sao dùng `ObjectProvider<RSocketRequester.Builder>`?** Builder do Boot cung cấp là prototype/stateful. Mỗi lần `getObject()` lấy builder mới, tránh credentials của alice còn lưu khi test bob trên cùng builder. Đó cũng là một bài học quan trọng cho ứng dụng đa người dùng.

**Giới hạn:** Test dùng TCP localhost cleartext, không chứng minh TLS/production certificate, multi-tenant record filtering, timeout/keepalive/load hoặc revocation midstream. Các phần đó cần test riêng. `WebTestClient` chỉ kiểm HTTP SecurityWebFilterChain; nó không “gửi RSocket” thay cho `RSocketRequester`.

### 8.2. Chạy test

```bash
gradle test
```

Có Gradle Wrapper:

```bash
./gradlew test
```

Nếu chạy server thật ở cổng 7000 cùng lúc, test RSocket dùng cổng động nhờ `spring.rsocket.server.port=0` và `@LocalRSocketServerPort`, tránh xung đột. HTTP test dùng RANDOM_PORT. Để chỉ chạy class:

```bash
./gradlew test --tests example.boundaries.SecurityBoundaryTests
```

**Đọc kết quả đúng ý nghĩa:** HTTP 401/403 là HTTP response. RSocket rejected là error signals của RSocket protocol, không có HTTP status 403. Không kiểm một hệ thống TCP RSocket bằng cách gửi `curl -i` tới port 7000.

## 9. RSocket-over-WebSocket: cùng WebFlux server nhưng khác tầng an ninh

Trong ứng dụng WebFlux, thay vì RSocket TCP port riêng, Boot có thể cho RSocket dùng WebSocket transport ở `/rsocket`.

**Mảnh YAML thay thế** cho `application.yml` ở mục 7:

```yaml
server:
  port: 8080

spring:
  rsocket:
    server:
      transport: websocket
      mapping-path: /rsocket
```

Khi RSocket server gắn vào WebFlux web server, không dùng cùng lúc giả định TCP port 7000 và WebSocket path. `mapping-path` chỉ áp dụng cho WebSocket transport. Boot hỗ trợ topology này khi app là WebFlux reactive và web server dùng Reactor Netty.

Client có thể kết nối:

```java
// MẢNH MINH HỌA: cần cấu hình requester's
// authentication metadata và transport security.
RSocketRequester requester =
        RSocketRequester.builder()
                .webSocket(
                        URI.create("ws://localhost:8080/rsocket"));
```

Đây là lab cleartext. Production dùng `wss://`, HTTPS certificate đáng tin, origin allowlist và WebSocket upgrade policies. Dù handshake là HTTP GET, **route metadata `demo.stream` vẫn cần RSocket Security**.

### 9.1. Vì sao chỉ kiểm handshake là không đủ?

Một connection WebSocket có thể sống rất lâu. Nếu HTTP Security cho phép handshake khi browser có session/cookie, sau đó Spring WebFlux request filters **không tự được gọi lại** cho mỗi RSocket message. Bạn cần xác định:
- Identity của RSocket client đến từ đâu: SETUP metadata, per-request metadata, hay trusted handshake bridge được thiết kế rõ;
- Nếu browser session bị logout giữa chừng, connection đang mở có bị ngắt không;
- Nếu websocket bị proxy reconnect, client gửi lại credentials thế nào;
- Nếu cùng connection phục vụ nhiều user, user-specific credential có được gửi mỗi request hay không;
- Nếu cookie bị CSRF/cross-site WebSocket hijacking, origin checks và session policy có phù hợp không.

**Không tự đồng nhất** `SecurityContextHolder`/`ReactiveSecurityContextHolder` của HTTP upgrade với context của RSocket payload nếu chưa có integration thực hiện propagation và test.

### 9.2. CORS không phải RSocket authorization

CORS là cơ chế browser dành cho HTTP cross-origin requests. RSocket over WebSocket có handshake HTTP và các quy tắc origin/WebSocket khác; nhưng request-level RSocket route auth vẫn phải kiểm credential qua RSocket security layer.

Đừng bật CORS wildcard hoặc mở websocket mọi origin để né lỗi kết nối. Gateway/proxy cũng cần hỗ trợ `Upgrade`, timeouts và frame size phù hợp.

## 10. Bảo mật luồng dài: khó hơn việc kiểm một request

### 10.1. Authorization lúc stream bắt đầu không bảo đảm mãi mãi

Giả sử alice có ROLE_STREAM, mở `demo.stream` hoặc stream production kéo dài 2 giờ. Sau 10 phút admin thu hồi quyền.

Nếu RSocket Security chỉ check lúc SETUP/request initiation, stream có thể vẫn chạy vì permission decision trước đó đã được chấp nhận. **Framework không tự phát một request xác thực mới trước mỗi event**.

Chiến lược tùy yêu cầu:
- Giới hạn stream lifetime và buộc reauthenticate sau `maxDuration`.
- Sau mỗi khoảng định kỳ, kiểm lại entitlement/revocation qua nonblocking service.
- Hủy active subscriptions khi nhận sự kiện user/tenant revoked.
- Không cho broker/topic phát dữ liệu tenant B vào stream tenant A.
- Dùng bounded queues/backpressure/bulkheads, tránh memory exhaustion.
- Kiểm downstream fan-out security cho từng subscription.
- Có reconnect policy và refresh token/renew credentials rõ ràng.

**Không dùng `Flux.interval(Duration.ZERO)` vô hạn mà không quota/cancel**, đặc biệt khi stream phát dữ liệu nhạy cảm. Cũng không gọi blocking DB trong handler `map` trên Netty event loop; dùng repository reactive hoặc schedulers/bulkheads phù hợp.

### 10.2. Backpressure và cancellation

RSocket Request-Stream truyền demand qua `REQUEST_N`. Nếu caller chỉ cần ba items rồi `take(3)`, producer phải quan sát cancellation và giải phóng tài nguyên.

```java
// MẢNH MINH HỌA trong service.
return eventRepository.watch(verifiedTenantId)
        .filter(event -> event.allowedFor(verifiedSubject))
        .take(Duration.ofMinutes(5))
        .doFinally(signal -> auditSubscriptionClosed(signal));
```

Đây là fragment; cần định nghĩa repository/event, audit logic và imports. `verifiedTenantId`/`verifiedSubject` **phải** đến từ Authentication/claims đã xác minh, không lấy nguyên văn từ RSocket payload do caller tự gửi. Phân quyền chỉ dựa vào route không ngăn data leak nếu service subscribe sai topic.

### 10.3. One connection, many logical streams

Multiplexing có nghĩa một RSocket connection có thể đồng thời mang:
- Request stream của user A;
- Request response của user B;
- Channel giữa hai services;
- Event subscriptions cho nhiều tenants.

Nếu dùng SETUP credential của user A làm Authentication chung và quên per-request metadata cho user B, bạn có thể **lẫn danh tính** giữa các streams. Đối với connection pool shared, nên thiết kế per-request bearer/JWT metadata hoặc một token exchange/gateway model bảo đảm từng request có đúng principal.

Tránh cache một `Authentication` hay `RSocketRequester.Builder` có state credentials mutable rồi dùng chung cho tất cả users.

### 10.4. Request-Channel không phải mỗi message đều là một request mới

RSocket Request-Channel cho phép hai phía gửi Flux data. Route/credential có thể ở **request đầu**; các PAYLOAD frames tiếp theo không tự mang một credential mới.

Khi channel chứa nhiều events có người sở hữu khác nhau:
- Validate identity khi bắt đầu channel;
- Áp policy dữ liệu tại từng event nếu threat model yêu cầu;
- Kiểm type/schema/size của inbound payloads;
- Giới hạn tổng items, rate, idle timeout;
- Cancel channel khi revoke hoặc expired policy;
- Không biến `anyExchange().permitAll()` thành “bỏ mọi quyền trên subsequent messages”. Chỉ là routing-level fallback; application-level validation vẫn cần.

### 10.5. Error của RSocket khác HTTP

HTTP WebFlux có status line `401 Unauthorized`/`403 Forbidden` và có thể có `WWW-Authenticate`.

RSocket trả **error frame** với loại mã lỗi/exception phù hợp:
- SETUP sai có thể bị reject khi connection đang hình thành;
- Request không đủ role nhận error signal;
- Request stream đã bắt đầu có thể dừng bằng error frame;
- Reconnection và retry policy phải dựa trên loại lỗi, không retry vòng lặp vô hạn invalid credentials.

Test RSocket nên assert `StepVerifier.expectError()` và không nhận protected items. Nếu product client cần phân biệt authentication failure với permission failure, xây một error contract phù hợp, không giả HTTP status vào payload một cách tùy tiện.

## 11. HTTP SSE, WebSocket và RSocket: chọn cái nào?

| Nhu cầu | HTTP streaming/SSE WebFlux | WebSocket | RSocket |
| --- | --- | --- | --- |
| Một chiều server → browser | SSE tự nhiên | Có thể | Request-Stream |
| Hai chiều liên tục | Không tự nhiên trong một HTTP request | Có | Request-Channel |
| Browser support native | EventSource/fetch streaming | WebSocket API | Cần RSocket client library |
| Routing request | URL/method | Custom message protocol | Metadata route |
| Built-in request/stream semantics | HTTP response stream | App tự thiết kế | Request-Response/Stream/Channel/FnF |
| Network backpressure | Reactive server và transport-dependent; không tương đương RSocket REQUEST_N | App phải tự quản lý flow | Demand signaling theo RSocket |
| Bảo mật mặc định của Spring | `SecurityWebFilterChain` cho GET/SSE | HTTP handshake + custom message policy | `RSocketSecurity` cho SETUP/request route |
| Token ở đâu | HTTP Authorization/cookie | Handshake hoặc app messages | SETUP/request auth metadata |
| Tự re-auth mỗi item? | Không | Không | Không |
| HTTP proxies/load balancers | Phổ biến | Cần upgrade/idle support | TCP/WebSocket-specific support |

**SSE vẫn là một HTTP request.** Spring Security HTTP kiểm AuthN/AuthZ khi GET bắt đầu; sau đó các event trên cùng response không tự chạy lại WebFilterChain. Đây là điểm **giống** với RSocket long-lived stream: nếu cần revocation midstream, app phải thiết kế thêm cơ chế.

**WebSocket thuần cũng không phải RSocket.** WebSocket không tự định nghĩa RSocket routes, request-response hoặc demand frames; nếu dùng RSocket-over-WebSocket, cần client/server hiểu RSocket protocol bên trên WebSocket.

## 12. JWT, issuer, audience và authorization cho RSocket

Khi dùng `rsocket.jwt(...)` cho token-based auth:
- Cấu hình `ReactiveJwtDecoder` tin issuer cụ thể.
- Validate JWS signature, `exp`/`nbf`, allowed algorithms, key rotation.
- **Validate audience** cho RSocket service; chỉ có issuer khớp không chứng minh token dành cho server này.
- Mapping scope → GrantedAuthority, ví dụ `SCOPE_events:read`; role không tự động được suy ra từ mọi custom claim.
- Tenant/owner checks ở message handler/service.
- Xem `sub` có phải user hay service account và theo issuer.
- Tránh dùng OIDC ID Token làm access token cho RSocket Resource Server.

Ví dụ policy theo authority đã được mapper cung cấp:

```java
// MẢNH CẤU HÌNH minh họa.
rsocket.authorizePayload(auth -> auth
    .setup().authenticated()
    .route("events.stream").hasAuthority("SCOPE_events:read")
    .anyRequest().denyAll()
    .anyExchange().permitAll());
```

**Không** tin trực tiếp `scope=events:read` do client tự đặt trong RSocket data body; đó phải là claim của token đã được xác minh hoặc policy từ trusted service.

### 12.1. Token ở SETUP vs request

Nếu client dùng JWT setup:
- Credential thường được xác minh khi kết nối;
- Connection có thể vẫn sống sau token expiry nếu không có policy tái kiểm;
- Reconnect nên lấy token còn hạn và SETUP lại;
- Revocation phải được đẩy tới connection/stream cancellation nếu cần phản ánh nhanh.

Nếu client dùng JWT per-request:
- Mỗi request mới có thể mang token mới;
- Hợp với shared connection phục vụ nhiều users;
- Không làm từng PAYLOAD event trong một request-stream tự động trở thành request-level authentication mới;
- Phải kiểm cache/decoder/tenants, không log token.

### 12.2. Không dùng HTTP bearer header thay RSocket auth metadata

```http
GET /rsocket
Authorization: Bearer <token>
Upgrade: websocket
```

Header này (nếu có) là của **WebSocket HTTP handshake**, không phải authentication metadata của RSocket SETUP hay request messages. Spring RSocket receiver không tự suy user từ nó. Nếu muốn truyền identity giữa tầng handshake và RSocket, phải thiết kế một bridge đã được bảo vệ/test kỹ; thường đơn giản và rõ ràng hơn là gửi RSocket Bearer metadata theo security DSL.

## 13. Operational security: TLS, credentials, availability

### 13.1. Encryption của RSocket transport

- RSocket TCP cleartext: không gửi password/token thật qua mạng.
- RSocket TCP TLS: kiểm chain/hostname/SAN, dùng certificates/keystore/truststore đúng.
- RSocket-over-WebSocket: dùng `wss://` với TLS termination đáng tin, kiểm origins/proxy.
- Với service-to-service, cân nhắc mTLS, network policies, secrets rotation.
- TLS chỉ bảo vệ transport và peer identity; **route authorization vẫn cần**.

Spring Boot 3.3 cung cấp cấu hình RSocket server như `spring.rsocket.server.ssl.bundle`, nhưng client RSocket TLS/mTLS setup phải nhất quán với transport, truststore và deployment. Không copy một URL `tcp://` mà giả định nó tự mã hóa.

### 13.2. Connection limits và idle timeouts

RSocket multiplexing tiết kiệm connections nhưng dễ có long-lived high-load sessions:
- Giới hạn số connections và concurrent streams;
- Giới hạn payload size và số item;
- Keepalive/ping/idle timeout hợp lý để phát hiện dead peers;
- Retry/reconnect với backoff/jitter, không spam khi credential sai;
- Khi reconnect gửi lại authentication metadata và kiểm quyền mới;
- Memory/buffer quotas/backpressure và cancellation;
- Subscription cleanup khi client disconnect;
- Kiểm load balance sticky routing hoặc state model nếu cần cluster.

Không mặc định rằng một user đã auth ở node A thì có “HTTP WebSession” trên node B của RSocket TCP. Hai protocols có lifecycle lưu state khác nhau; kiến trúc nhiều nút phải thiết kế connection routing và state/identity persistence riêng.

### 13.3. Observability không lộ secrets

Nên đo:
- SETUP auth success/failure và denial category;
- Request per-route allow/deny count;
- Active connections/streams theo service alias (không dùng raw user email);
- Request-Stream durations p95/p99;
- Cancellation, stream errors, backpressure/buffer pressure;
- JWT decoder latency/JWK/issuer errors nếu dùng token;
- Reconnect rate và invalid credential retry.

Không log Simple password metadata, raw JWT, RSocket raw frames chứa secrets, session cookies, token headers, private key hoặc toàn bộ payload của tenant khác. Tắt wiretap/body logging trên production hoặc redact đầy đủ.

## 14. Những lỗi rất dễ mắc

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| HTTP /public/ping chạy, RSocket connect fail | TCP server 7000 chưa chạy/port sai | Kiểm spring.rsocket.server.port, network |
| HTTP đã authenticated nhưng RSocket SETUP bị reject | Hai mechanisms khác; chưa gửi metadata | Gửi Simple/JWT RSocket auth metadata |
| RSocket route chạy dù HTTP /http/private 403 | Policies độc lập | Cấu hình RSocket route role riêng |
| RSocket setup thành công nhưng route stream bị reject | Đúng credential, sai ROLE_STREAM | Kiểm RSocketSecurity route permissions |
| Gửi `Authorization: Bearer` HTTP tới TCP 7000 | Nhầm protocol | Dùng RSocketRequester/metadata |
| Dùng `curl -i` tới TCP 7000 | TCP không phải HTTP | Dùng RSocket client |
| Simple Authentication trên public TCP | Credentials truyền không mã hóa | Bật TLS hoặc secure transport, ưu tiên chuẩn |
| WebSocket handshake 101 nhưng RSocket route bị reject | RSocket payload security độc lập | Gửi/verify metadata theo request |
| WebSocket handshake permitAll nên cho mọi RSocket route | Bỏ qua RSocket Security | Enable/validate RSocket interceptor/policies |
| `.anyRequest().permitAll()` trước route restricted | First matching rule thắng | Đặt restrictive routes trước catchall |
| `.anyExchange().denyAll()` làm stream lỗi | Subsequent exchanges không có route metadata | Thiết kế fallback đúng RSocket semantics |
| SETUP theo user A, connection pool gửi request cho B | Identity leakage | Per-request auth metadata, isolate connection |
| Token expired nhưng stream vẫn gửi event | Không tự revalidate từng item | Stream TTL, revoke/cancel, periodic entitlement checks |
| Role bị revoke nhưng connection còn giữ principal | Cached setup identity | Reconnect/revalidation/revocation invalidation |
| JWT chữ ký đúng nhưng cho service khác | Thiếu audience validator | Validate issuer + audience + scopes |
| Request stream gửi data tenant khác | Chỉ bảo vệ route, chưa bảo vệ resource | Filter tenant/owner ở service/event source |
| HTTP WebFilter không nhìn thấy RSocket route | Hai pipelines khác nhau | SecurityWebFilterChain + RSocketSecurity riêng |
| CORS wildcard “chữa” RSocket error | CORS không phải RSocket AuthZ | Phân tầng handshake/origin/metadata |
| WebTestClient không test RSocket | Test tool HTTP | RSocketRequester + StepVerifier |
| RSocket test lỗi không có HTTP 401 | Lỗi được truyền bằng RSocket frame | Kiểm error signal/protocol code |
| Kết nối long-lived không giải phóng | Quên cancel/dispose/idle handling | Lifecycle hooks, timeouts, cleanup |

## 15. Checklist production

1. Xác định transport RSocket: TCP/TLS, WebSocket/WSS và port/path công khai.
2. Bật đúng RSocket Security modules và interceptor, test thật ở port/transport triển khai.
3. Có **separate policy** cho HTTP WebFlux SecurityWebFilterChain và RSocketSecurity.
4. Quyết định rõ authentication ở SETUP hay per-request hoặc cả hai.
5. Tránh shared connection mang credential của một user cố định khi multiplex traffic nhiều users.
6. Nếu dùng Simple Authentication, chỉ dùng qua encrypted transport; tránh password mẫu.
7. Nếu dùng JWT, kiểm signature, issuer, audience, exp/nbf và authority mapping đúng service.
8. RSocket routes nhạy cảm có restrictive allowlist, `anyRequest().denyAll()` khi phù hợp.
9. Kiểm `.anyExchange()` cho subsequent stream/channel payloads; không nhầm nó là bỏ AuthN.
10. Phân quyền theo tenant/owner/resource trong service, không chỉ match route.
11. Có policy về token expiry/revoke khi stream dài đang mở.
12. Hạn chế stream lifetime, item rate, buffer/memory, concurrent subscribers và connections.
13. Cấu hình cancellation/cleanup và retry/reconnect có backoff; không retry vô hạn credential sai.
14. Dùng TLS/WSS/mTLS/ingress allowlist, kiểm hostname/certificates và origin rules.
15. Không tin HTTP handshake authentication tự được chuyển tới RSocket payload identity.
16. Kiểm HTTP/WebSocket/RSocket error semantics tách riêng; không phát HTTP 401 trong TCP frame.
17. Không log password metadata, raw JWT, private keys, raw stream payloads nhạy cảm.
18. Test HTTP riêng bằng WebTestClient; RSocket riêng bằng RSocketRequester + StepVerifier.
19. Test SETUP anonymous/wrong credentials, user đúng nhưng thiếu role, unknown route, long-lived stream cancellation và tenant leakage.
20. Nếu dùng multi-node, thiết kế sticky routing/connection lifecycle, shared state/revoke signals và load-test failover.
21. Khi nâng Spring Boot/Spring Security, kiểm lại module RSocket Security và RSocket transport APIs tương ứng; không copy Servlet HTTP configuration.
22. Có dashboards cho auth failures, denied routes, stream durations, cancellation, buffer pressure và active connections.

## 16. Câu hỏi tự kiểm tra

**1. `SecurityWebFilterChain` của HTTP có tự bảo vệ RSocket TCP port không?**  
Không. RSocket TCP không phải HTTP exchange. Phải có RSocket Security policy tại acceptor.

**2. RSocket Security dùng entry point nào?**  
`@EnableRSocketSecurity` + `RSocketSecurity` tạo `PayloadSocketAcceptorInterceptor`, được nối vào RSocket acceptor qua Boot auto-configuration hoặc customizer đúng.

**3. Sự khác biệt lớn nhất giữa `@GetMapping` và `@MessageMapping`?**  
`@GetMapping` định tuyến HTTP path/method; `@MessageMapping` nhận RSocket route trong messaging metadata.

**4. HTTP 401/403 có phải cách RSocket báo AuthN/AuthZ error?**  
Không. RSocket dùng error signal/frame/exception của giao thức.

**5. Khi nào nên xác thực ở SETUP?**  
Khi connection thuộc một user/service cố định và policy cho phép identity sống theo connection lifecycle.

**6. Khi nào cần per-request metadata?**  
Khi connection được dùng chung cho nhiều end users, hoặc cần identity/permission khác nhau theo từng request.

**7. RSocket SETUP auth có tự kiểm lại token ở mọi event không?**  
Không mặc định. Stream dài cần giới hạn thời gian và revalidation/revoke policy khi cần.

**8. Simple Authentication metadata có được mã hóa không?**  
Không; bắt buộc dùng TLS/WSS/secure transport ngoài lab localhost.

**9. JWT trong RSocket gửi bằng HTTP Authorization header hay gì?**  
Thông thường bằng RSocket Bearer Token Authentication Metadata Extension trong SETUP/request, không phải HTTP header của từng message.

**10. Vì sao `anyRequest()` và `anyExchange()` khác nhau?**  
`anyRequest()` dành cho request exchanges có routing metadata; `anyExchange()` còn có các exchanges khác, như subsequent payloads không chứa route. Cần áp theo semantics frame/interaction.

**11. Nếu user bob có ROLE_WEB, tại sao RSocket demo.stream vẫn bị từ chối?**  
Vì route stream yêu cầu ROLE_STREAM. User store chung không đồng nghĩa policies chung.

**12. Alice có ROLE_STREAM nhưng HTTP /http/private 403 có phải lỗi?**  
Không. HTTP route yêu cầu ROLE_WEB; RSocket route yêu cầu ROLE_STREAM.

**13. `.route("admin.*").hasRole("ADMIN")` có bảo đảm user không lấy dữ liệu tenant khác không?**  
Không. Tenant/ownership/resource-level check thuộc service/data layer.

**14. Backpressure bảo đảm điều gì, không bảo đảm điều gì?**  
Giúp kiểm tốc độ/demand stream; không tự bảo đảm authentication, authorization, revocation hay data isolation.

**15. RSocket over WebSocket đã handshake với HTTP cookie, vậy route protected tự có user?**  
Không mặc nhiên. Cần thiết kế identity propagation có kiểm chứng hoặc dùng RSocket metadata auth.

**16. Có thể dùng WebTestClient để test RSocket TCP messages không?**  
Không. Dùng RSocketRequester và StepVerifier.

**17. Vì sao không nên dùng chung RSocketRequester.Builder đã chứa credentials cho mọi users?**  
Builder có state; dễ gửi credential sai user và tạo cross-tenant leak. Nên tạo requester/builder đúng scope, isolation hoặc per-request metadata.

**18. Token hết hạn giữa request-stream sẽ xảy ra gì?**  
Không có đảm bảo framework tự dừng stream chỉ dựa vào token expiry; policy cần recheck/cancel/reconnect.

**19. Điều gì xảy ra nếu `.anyRequest().permitAll()` đặt trước một route đặc quyền?**  
Vì first-match-wins, route có thể được mở ngoài ý định.

**20. Vì sao không được nhầm `ws://` với `wss://`?**  
`wss://` dùng TLS; credential trong metadata có thể bị lộ nếu vận chuyển cleartext qua mạng.

**21. Cùng một app có thể chạy HTTP và RSocket không?**  
Có. Ví dụ dùng HTTP port 8080 và RSocket TCP port 7000 hoặc RSocket over WebSocket path của WebFlux; mỗi pipeline cần policy riêng.

**22. Nguồn lỗi SETUP và lỗi route có khác nhau không?**  
Có. SETUP failure thường từ chối connection, còn route authorization failure phát error cho request; không giả định cùng code/class mọi version.

**23. Client reconnect sau sự cố có cần xác thực lại không?**  
Có, vì đây là connection mới; gửi metadata còn hợp lệ, đánh giá revocation/expiry và không retry credential sai vô hạn.

**24. Vai trò `ReactiveJwtDecoder` khi dùng RSocket JWT là gì?**  
Xác minh chữ ký/claims của token; RSocketSecurity `jwt(...)` phối hợp để chuyển token thành Authentication đáng tin.

**25. Khi nào RSocket không phải lựa chọn tốt nhất?**  
Nếu chỉ cần HTTP API bình thường hoặc SSE một chiều đơn giản; RSocket có thêm yêu cầu client library, proxies, monitoring, TLS và connection lifecycle.

**26. Một `@MessageMapping` trả `Flux` có tự động bảo vệ từng phần tử Flux bằng role check không?**  
Không. Route initiation được kiểm bởi interceptor; service cần kiểm quyền/resource cho dữ liệu từng phần tử theo threat model.

**27. Có thể bỏ RSocket Security nếu gateway đã xác thực handshake không?**  
Chỉ khi đã thiết kế/tài liệu hóa trusted identity propagation và authorization bên ứng dụng, được test đầy đủ; mặc định không nên bỏ layer này.

**28. Vì sao `@LocalRSocketServerPort` hữu ích trong CI?**  
Cho phép test mở RSocket server trên cổng động rồi inject đúng port, tránh xung đột với server khác.

**29. Đâu là kiểm thử phân biệt rõ hai security layers?**  
Bob truy cập HTTP /http/private thành công nhưng RSocket demo.stream bị từ chối; Alice ngược lại được RSocket stream nhưng HTTP private bị 403.

**30. Điều cần nhớ khi triển khai request-channel cho nhiều tenants?**  
Metadata route/credential không được gửi tự động ở mọi item; phải kiểm tenant/owner ở ứng dụng, giới hạn stream và xử lý revoke/cancel.

**Ghi nhớ:** **RSocket Security bảo vệ RSocket SETUP, request metadata và routes; HTTP WebFlux Security bảo vệ HTTP exchanges.** Hai thứ có thể cùng tồn tại trong một Spring Boot app nhưng không thay thế nhau. Dùng transport mã hóa, gửi credential đúng metadata, quyết định authentication theo connection/request, đặt rules từ cụ thể đến fallback, kiểm quyền dữ liệu và thiết kế đặc biệt cho stream dài.

## Tài liệu tham khảo

- [Spring Security — RSocket Security](https://docs.spring.io/spring-security/reference/reactive/integrations/rsocket.html): interceptor, SETUP vs request auth, Simple/Bearer metadata, `authorizePayload`.
- [Spring Security — RSocketSecurity API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/rsocket/RSocketSecurity.html): `@EnableRSocketSecurity`, matcher DSL và `PayloadSocketAcceptorInterceptor`.
- [Spring Security 6.3 — PayloadSocketAcceptorInterceptor API](https://docs.spring.io/spring-security/site/docs/6.3.6/api/org/springframework/security/rsocket/core/PayloadSocketAcceptorInterceptor.html): payload interceptors và socket acceptor.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `SecurityWebFilterChain` và `ServerHttpSecurity`.
- [Spring Boot — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html): TCP vs WebSocket RSocket server, `RSocketRequester.Builder`, annotated responders.
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `spring.rsocket.server.address`, port, transport, SSL.
- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): interaction models, setup/request metadata, route matching, backpressure, annotated controllers.
- [Spring Boot 3.3 — LocalRSocketServerPort API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/rsocket/server/LocalRSocketServerPort.html): RSocket server test port injection.
- [Spring Team — Getting Started with RSocket Security](https://spring.io/blog/2020/06/17/getting-started-with-rsocket-spring-security/): Simple Authentication metadata, setup/test patterns.
- [RSocket Protocol](https://rsocket.io/about/protocol/): SETUP, request-stream/channel, demand and error signals.
- [RSocket Authentication Metadata Extension](https://github.com/rsocket/rsocket/blob/master/Extensions/Security/Authentication.md): Simple/Bearer authentication metadata types.
- [Project Reactor — Reference](https://projectreactor.io/docs/core/release/reference/): backpressure, cancellation, Reactor Context.
