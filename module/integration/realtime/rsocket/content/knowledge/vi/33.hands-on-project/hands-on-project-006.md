# Thực hành: Bảo vệ dịch vụ bằng JWT và phân quyền theo route

Trong bài thực hành này, bạn xây dựng một RSocket service bằng Spring Boot, xác thực client bằng JSON Web Token (JWT) do một Identity Provider (IdP) tin cậy phát hành và giới hạn quyền theo từng route. Client có thể đọc đơn hàng khi token có scope `orders.read`, nhưng chỉ được tạo đơn hàng khi có thêm scope `orders.write`.

Bạn sẽ hoàn thành một luồng bảo mật từ đầu đến cuối: IdP cấp access token, client gửi bearer token trong RSocket authentication metadata, server xác minh chữ ký và claims, Spring Security tạo `Authentication`, rồi authorization matcher quyết định request có được chuyển đến `@MessageMapping` handler hay không.

## 1. Kết quả cần đạt

Sau khi hoàn thành, ứng dụng có hai route:

| Route | Scope bắt buộc | Hành vi |
|---|---|---|
| `orders.read` | `orders.read` | Đọc thông tin đơn hàng. |
| `orders.write` | `orders.write` | Tạo đơn hàng mới. |
| Route khác | Không được cấp mặc định | Bị từ chối. |

Các trường hợp cần chứng minh:

- Token hợp lệ có `orders.read` gọi được `orders.read`.
- Token chỉ có `orders.read` không gọi được `orders.write`.
- Token có cả hai scope gọi được cả hai route.
- Token sai chữ ký, hết hạn, sai issuer hoặc sai audience không được xác thực.
- Request không có token hoặc route chưa được cấp quyền bị từ chối.

Phạm vi lab dùng một danh tính cho mỗi RSocket connection và gửi JWT trong SETUP metadata. Phần mở rộng cuối bài trình bày cách xác thực ở từng request khi nhiều người dùng chia sẻ một connection.

## 2. Kiến trúc và luồng xử lý

```text
Client application                  Identity Provider
       |                                   |
       |---- OAuth/OIDC token request ---->|
       |<----------- signed JWT -----------|
       |
       | RSocket SETUP + Bearer auth metadata
       v
Spring Boot RSocket server
       |
       v
PayloadSocketAcceptorInterceptor
       |
       +--> ReactiveJwtDecoder
       |      - verify signature/JWK
       |      - validate issuer, exp, nbf, audience
       |
       +--> Authentication + authorities
       |
       +--> route authorization
       |      - orders.read  -> SCOPE_orders.read
       |      - orders.write -> SCOPE_orders.write
       |
       v
@MessageMapping handler
```

JWT là access token do IdP phát hành và ký. RSocket server đóng vai trò resource server: nó xác minh token bằng khóa công khai/JWK của issuer và dùng claims đã được xác minh để tạo authorities. Server không tin các scope hoặc role do client tự gửi trong payload.

## 3. Chuẩn bị môi trường

Bạn cần:

- JDK tương thích với Spring Boot version của dự án.
- Spring Boot với RSocket server support.
- Một IdP hỗ trợ OAuth 2.0/OIDC và phát hành JWT access token.
- Một client có thể gọi RSocket bằng TCP hoặc WebSocket.
- Một issuer URI, audience và hai scope `orders.read`, `orders.write` được cấu hình tại IdP.

Tạo một resource/API ở IdP với audience `rsocket-api`. Cấu hình client hoặc user được phép nhận các scope sau:

| Scope | Ý nghĩa |
|---|---|
| `orders.read` | Được đọc đơn hàng. |
| `orders.write` | Được tạo/cập nhật đơn hàng. |

Một JWT access token phù hợp có các claim khái niệm như sau:

```json
{
  "iss": "https://identity.example/realms/rsocket-lab",
  "sub": "alice",
  "aud": ["rsocket-api"],
  "scope": "orders.read orders.write",
  "iat": 1900000000,
  "exp": 1900000300
}
```

Đây chỉ là payload minh họa, không phải token có thể dùng để đăng nhập. IdP phải ký token bằng khóa đáng tin cậy; server kiểm tra chữ ký và claims bằng metadata/JWK của issuer.

Đặt các giá trị cấu hình qua biến môi trường:

```text
JWT_ISSUER_URI=https://identity.example/realms/rsocket-lab
JWT_AUDIENCE=rsocket-api
```

Không hard-code client secret, private signing key hoặc access token trong source code, file cấu hình được commit hay log.

## 4. Tạo project và thêm dependency

Tạo Spring Boot application có RSocket server và Spring Security. Với Spring Boot 3.x, dependency Gradle có thể khai báo như sau:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-rsocket")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.security:spring-security-rsocket")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-resource-server")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("io.projectreactor:reactor-test")
}
```

Nếu dùng Maven, thêm các dependency tương đương:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-rsocket</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-rsocket</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
</dependencies>
```

Để Spring Boot BOM quản lý phiên bản các thư viện. Không tự trộn Spring Security, Spring Framework, Reactor và RSocket Java từ các dòng phiên bản không tương thích. Với Spring Boot 4, starter OAuth2 Resource Server được đặt tên `spring-boot-starter-security-oauth2-resource-server`; dùng đúng tọa độ theo major version của dự án.

## 5. Cấu hình RSocket server và JWT issuer

Tạo `src/main/resources/application.yml`:

```yaml
spring:
  rsocket:
    server:
      port: 7000

app:
  security:
    jwt:
      issuer-uri: ${JWT_ISSUER_URI}
      audience: ${JWT_AUDIENCE:rsocket-api}
```

Ví dụ này chạy RSocket TCP trên cổng `7000`. Nếu ứng dụng cần WebSocket, cấu hình transport và mapping path theo cách triển khai Spring Boot; phần authentication/authorization của RSocket vẫn sử dụng cùng security interceptor.

## 6. Xác minh chữ ký, issuer, thời hạn và audience

Tạo `JwtDecoderConfiguration.java`:

```java
@Configuration
public class JwtDecoderConfiguration {

    @Bean
    ReactiveJwtDecoder jwtDecoder(
            @Value("${app.security.jwt.issuer-uri}") String issuerUri,
            @Value("${app.security.jwt.audience}") String audience) {

        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder.withIssuerLocation(issuerUri).build();

        OAuth2TokenValidator<Jwt> issuerAndTimeValidator =
            JwtValidators.createDefaultWithIssuer(issuerUri);

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience().contains(audience)) {
                return OAuth2TokenValidatorResult.success();
            }

            OAuth2Error error = new OAuth2Error(
                "invalid_token",
                "Required audience is missing",
                null);
            return OAuth2TokenValidatorResult.failure(error);
        };

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
            issuerAndTimeValidator,
            audienceValidator));

        return decoder;
    }
}
```

Các import chính:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
```

`withIssuerLocation(...)` tìm cấu hình issuer/JWK Set URI theo OIDC/OAuth metadata và xác minh chữ ký token bằng khóa tin cậy. `JwtValidators.createDefaultWithIssuer(...)` kiểm tra issuer và các điều kiện thời gian mặc định như `exp`/`nbf`. Validator bổ sung kiểm tra `aud` chứa `rsocket-api`, để token phát hành cho API khác không thể dùng nhầm ở RSocket service này.

Nếu hệ thống đã dùng cấu hình mặc định của Spring Boot và không cần validator audience tùy chỉnh, có thể khai báo `ReactiveJwtDecoder` từ `ReactiveJwtDecoders.fromIssuerLocation(issuerUri)`. Với API production, nên xác định rõ audience cần chấp nhận.

## 7. Bật RSocket Security và phân quyền theo route

Tạo `RSocketSecurityConfiguration.java`:

```java
@Configuration
@EnableRSocketSecurity
public class RSocketSecurityConfiguration {

    @Bean
    PayloadSocketAcceptorInterceptor rsocketInterceptor(
            RSocketSecurity rsocket) {

        rsocket
            .authorizePayload(authorize -> authorize
                .setup().authenticated()
                .route("orders.read")
                    .hasAuthority("SCOPE_orders.read")
                .route("orders.write")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll()
                .anyExchange().denyAll()
            )
            .jwt(Customizer.withDefaults());

        return rsocket.build();
    }
}
```

Các import chính:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.rsocket.EnableRSocketSecurity;
import org.springframework.security.config.annotation.rsocket.RSocketSecurity;
import org.springframework.security.rsocket.core.PayloadSocketAcceptorInterceptor;
import org.springframework.security.config.Customizer;
```

Ý nghĩa từng rule:

1. `.setup().authenticated()` yêu cầu kết nối được xác thực khi SETUP. Client phải gửi bearer token hợp lệ trong authentication metadata của SETUP.
2. `.route("orders.read").hasAuthority("SCOPE_orders.read")` chỉ cho phép principal có scope đọc.
3. `.route("orders.write").hasAuthority("SCOPE_orders.write")` chỉ cho phép principal có scope ghi.
4. `.anyRequest().denyAll()` từ chối request có routing metadata nhưng không khớp rule cụ thể.
5. `.anyExchange().denyAll()` từ chối exchange/payload không khớp các rule trước, kể cả trường hợp không có metadata route.
6. `.jwt(Customizer.withDefaults())` bật JWT bearer authentication metadata converter và dùng `ReactiveJwtDecoder` bean để xác thực token.

Spring Security xử lý các rule theo thứ tự khai báo; rule cụ thể phải đứng trước rule tổng quát. Mặc định JWT authority converter ánh xạ scope thành authority có tiền tố `SCOPE_`. Vì vậy scope `orders.read` trở thành `SCOPE_orders.read`.

### Spring Boot tự đăng ký security interceptor

Khi dùng đúng dependency Spring Boot RSocket và Spring Security RSocket, auto-configuration đăng ký security interceptor vào RSocket server. Nếu tự tạo server hoặc không dùng Boot auto-configuration, cần gắn `SecuritySocketAcceptorInterceptor` vào `SocketAcceptor` pipeline theo API của phiên bản đang dùng. Chỉ tạo bean cấu hình mà server không sử dụng thì các request sẽ không đi qua security chain.

Với Spring Boot server tùy chỉnh, cách tích hợp thường dùng là đăng ký interceptor do Spring Security cung cấp qua `RSocketServerCustomizer`:

```java
@Bean
RSocketServerCustomizer springSecurityRSocketSecurity(
        SecuritySocketAcceptorInterceptor interceptor) {
    return server -> server.interceptors(registry ->
        registry.forSocketAcceptor(interceptor));
}
```

Không thêm customizer này nếu auto-configuration đã đăng ký interceptor cho server hiện tại; tránh đăng ký lặp. Với server builder tự quản lý ngoài Boot, gắn cùng interceptor vào `SocketAcceptor` trước khi bind transport.

Import cho ví dụ customizer:

```java
import org.springframework.boot.rsocket.server.RSocketServerCustomizer;
import org.springframework.security.rsocket.core.SecuritySocketAcceptorInterceptor;
```

## 8. Tạo DTO cho hai thao tác

Tạo các record đơn giản:

```java
public record OrderQuery(String orderId) {}

public record CreateOrder(String customerId, BigDecimal amount) {}

public record OrderView(
    String orderId,
    String customerId,
    BigDecimal amount,
    String createdBy
) {}
```

`OrderQuery` là payload đọc. `CreateOrder` là payload tạo đơn hàng. `OrderView` là kết quả trả về cho client.

Trong project thật, bổ sung validation cho ID, số tiền, currency, giới hạn nghiệp vụ và kiểm tra quyền truy cập từng tài nguyên. Route scope chỉ xác định caller có được phép gọi loại thao tác; nó không tự chứng minh caller được truy cập mọi đơn hàng hoặc tenant.

## 9. Tạo RSocket controller

Tạo `OrdersRSocketController.java`:

```java
@Controller
public class OrdersRSocketController {

    private final OrderService orderService;

    public OrdersRSocketController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("orders.read")
    public Mono<OrderView> read(
            @Payload OrderQuery query,
            Principal principal) {

        return orderService.find(query.orderId(), principal.getName());
    }

    @MessageMapping("orders.write")
    public Mono<OrderView> create(
            @Payload CreateOrder command,
            Principal principal) {

        return orderService.create(command, principal.getName());
    }
}
```

Handler không tự parse JWT. Security interceptor xác thực bearer metadata và đặt principal vào security context trước khi request được chuyển tới handler. Có thể dùng principal đã xác thực để ghi nhận actor hoặc kiểm tra quyền ở cấp domain.

Một `OrderService` minh họa có thể trả dữ liệu giả trong lab:

```java
@Service
public class OrderService {

    public Mono<OrderView> find(String orderId, String username) {
        return Mono.just(new OrderView(
            orderId, "customer-1", new BigDecimal("125.00"), username));
    }

    public Mono<OrderView> create(CreateOrder command, String username) {
        return Mono.just(new OrderView(
            UUID.randomUUID().toString(),
            command.customerId(),
            command.amount(),
            username));
    }
}
```

Đây là service minh họa để tập trung vào security. Khi thay bằng database, hãy dùng reactive driver và không gọi blocking I/O trực tiếp trên Netty event loop.

## 10. Lấy JWT từ Identity Provider

Client cần một access token được IdP phát hành cho audience `rsocket-api` và có scope phù hợp. Với service-to-service, có thể dùng Client Credentials nếu IdP cho phép. Với ứng dụng người dùng, ưu tiên Authorization Code + PKCE theo chính sách OAuth/OIDC của hệ thống.

Ví dụ lệnh lấy token theo Client Credentials; endpoint và tham số cụ thể phụ thuộc IdP:

```bash
curl --fail --silent --show-error \
  --user "$CLIENT_ID:$CLIENT_SECRET" \
  --data "grant_type=client_credentials" \
  --data "scope=orders.read" \
  "$TOKEN_ENDPOINT"
```

Token chỉ có `orders.read` dùng để thử route đọc. Lấy thêm một token có `orders.read orders.write` để thử cả hai route. Không bật password grant chỉ để làm lab nếu IdP không yêu cầu; không đưa client secret vào lệnh lưu trong shell history hoặc log CI.

Kiểm tra các claim đã được IdP cấp bằng công cụ phù hợp trong môi trường phát triển. Không tin kết quả decode payload bằng mắt như bằng chứng chữ ký hợp lệ; chỉ server xác minh chữ ký, issuer, audience và thời hạn mới quyết định token được chấp nhận.

## 11. Gửi JWT trong RSocket SETUP metadata

Với mô hình một user/service identity trên mỗi connection, gửi token lúc tạo connection. Spring Security hỗ trợ Bearer Token Authentication Metadata Extension.

```java
MimeType authenticationMimeType = MimeTypeUtils.parseMimeType(
    WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());

BearerTokenMetadata bearerToken = new BearerTokenMetadata(accessToken);

Mono<RSocketRequester> requesterMono = RSocketRequester.builder()
    .setupMetadata(bearerToken, authenticationMimeType)
    .connectTcp("localhost", 7000);
```

Các import chính:

```java
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.security.rsocket.metadata.BearerTokenMetadata;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;
import io.rsocket.metadata.WellKnownMimeType;
```

`BearerTokenMetadata` đóng gói JWT theo bearer authentication metadata format. MIME type là `message/x.rsocket.authentication.v0`. Token được xác thực trong SETUP; các request trên connection dùng identity đã được xác thực đó.

Không chia sẻ một requester đã xác thực bằng token của Alice cho Bob nếu server đang dùng authentication ở SETUP. Mọi request trên connection đó sẽ mang security context gắn với Alice.

## 12. Gọi route đã được bảo vệ

Sau khi kết nối thành công, client gọi route như bình thường:

```java
RSocketRequester requester = requesterMono.block();

Mono<OrderView> order = requester
    .route("orders.read")
    .data(new OrderQuery("order-1001"))
    .retrieveMono(OrderView.class);
```

Nếu token có scope `orders.read`, request được authorization matcher cho phép. Để gọi route ghi:

```java
Mono<OrderView> created = requester
    .route("orders.write")
    .data(new CreateOrder("customer-1", new BigDecimal("125.00")))
    .retrieveMono(OrderView.class);
```

Nếu token chỉ có `orders.read`, request ghi bị từ chối trước khi `OrderService.create(...)` được gọi. Không nên dựa vào UI để ẩn nút ghi; server luôn phải kiểm tra quyền.

Trong code production, tránh gọi `.block()` trên event-loop hoặc trong reactive request path. Ví dụ ở đây block chỉ để minh họa ranh giới kết nối trong một chương trình client đồng bộ. Nếu client cũng là ứng dụng reactive, compose `Mono<RSocketRequester>` với các request thay vì block.

## 13. Kiểm thử với các loại token

Tạo integration test dùng token do test IdP phát hành hoặc test fixture ký bằng khóa riêng của test. Không dùng JWT giả chỉ có ba đoạn base64 nhưng không có chữ ký hợp lệ để chứng minh authentication thành công.

Ma trận kiểm thử:

| Token | Route | Kết quả mong đợi |
|---|---|---|
| Hợp lệ, scope `orders.read` | `orders.read` | Thành công. |
| Hợp lệ, scope `orders.read` | `orders.write` | Bị từ chối. |
| Hợp lệ, scope `orders.write` | `orders.write` | Thành công. |
| Hợp lệ, có cả hai scope | Cả hai route | Thành công. |
| Không có bearer metadata | SETUP | Connection authentication thất bại. |
| Chữ ký sai | SETUP | Token bị từ chối. |
| Token hết hạn | SETUP | Token bị từ chối. |
| Issuer không khớp | SETUP | Token bị từ chối. |
| Audience không chứa `rsocket-api` | SETUP | Token bị từ chối. |
| Token hợp lệ, route không khai báo | Route khác | Bị từ chối theo deny-by-default. |

### Ví dụ test route authorization

Giả sử helper `connectWithToken(...)` tạo requester bằng SETUP bearer metadata và token do test IdP ký:

```java
@Test
void readScopeCanReadButCannotWrite() {
    RSocketRequester readOnly = connectWithToken(readToken);
    try {
        StepVerifier.create(readOnly
                .route("orders.read")
                .data(new OrderQuery("order-1001"))
                .retrieveMono(OrderView.class))
            .expectNextMatches(order -> order.orderId().equals("order-1001"))
            .verifyComplete();

        StepVerifier.create(readOnly
                .route("orders.write")
                .data(new CreateOrder("customer-1", new BigDecimal("10.00")))
                .retrieveMono(OrderView.class))
            .expectError()
            .verify();
    } finally {
        readOnly.rsocket().dispose();
    }
}
```

Loại lỗi cụ thể quan sát được ở client có thể khác theo phiên bản RSocket/Spring Security và thời điểm server từ chối exchange. Trong test tích hợp, xác minh request bị từ chối và service không thực hiện side effect; không phụ thuộc vào chuỗi message lỗi nội bộ.

### Kiểm tra handler không chạy khi bị từ chối

Mock `OrderService` và xác minh route ghi không gọi service khi token chỉ có scope đọc:

```java
verify(orderService, never()).create(any(), anyString());
```

Đây là kiểm tra quan trọng: authorization phải được thực thi trước handler. Nếu chỉ kiểm tra client nhận error mà không xác minh service, test chưa chứng minh side effect bị chặn.

## 14. Xác thực ở SETUP hay ở từng request?

Spring Security RSocket hỗ trợ authentication tại SETUP, tại request hoặc cả hai. Lựa chọn phụ thuộc cách chia sẻ connection.

| Mô hình | Cách gửi JWT | Khi phù hợp |
|---|---|---|
| Một user trên một connection | Gửi bearer metadata trong SETUP. | Mobile/browser session hoặc service connection gắn với một identity. |
| Nhiều user dùng chung connection | Gửi bearer metadata trên từng request. | Gateway/downstream service multiplex request của nhiều người dùng trên một connection. |
| Connection identity + user identity | Credential ở SETUP và JWT riêng ở từng request. | Cần xác thực cả ứng dụng kết nối lẫn người dùng cuối. |

Với request-time authentication, server có thể cho phép SETUP không cần user token rồi kiểm tra authentication metadata của từng request. Ví dụ policy khái niệm:

```java
rsocket.authorizePayload(authorize -> authorize
    .setup().permitAll()
    .route("orders.read").hasAuthority("SCOPE_orders.read")
    .route("orders.write").hasAuthority("SCOPE_orders.write")
    .anyRequest().denyAll()
    .anyExchange().denyAll()
).jwt(Customizer.withDefaults());
```

Client gắn token vào từng request:

```java
MimeType authenticationMimeType = MimeTypeUtils.parseMimeType(
    WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());

Mono<OrderView> response = requester
    .route("orders.read")
    .metadata(new BearerTokenMetadata(userAccessToken), authenticationMimeType)
    .data(new OrderQuery("order-1001"))
    .retrieveMono(OrderView.class);
```

Không trộn hai mô hình một cách vô ý. Nếu dùng shared connection, không lưu principal của user đầu tiên ở connection rồi dùng nó cho mọi user khác. Nếu cần giới hạn cả ứng dụng mở connection lẫn quyền từng user, cấu hình hai lớp authentication/authorization theo tài liệu Spring Security RSocket.

## 15. JWT scope, role và authority

Spring Security phân quyền dựa trên `GrantedAuthority`. Với JWT resource server mặc định, claim `scope` hoặc `scp` thường được chuyển thành authority có tiền tố `SCOPE_`.

| Claim trong JWT | Authority mặc định |
|---|---|
| `scope: "orders.read"` | `SCOPE_orders.read` |
| `scope: "orders.read orders.write"` | `SCOPE_orders.read`, `SCOPE_orders.write` |

`hasAuthority("SCOPE_orders.read")` so khớp authority chính xác. `hasRole("ADMIN")` thường kiểm tra authority `ROLE_ADMIN`, vì vậy không thay thế cho `hasAuthority("SCOPE_orders.read")`.

Nếu IdP phát claim riêng như `roles: ["ADMIN"]`, bạn cần cấu hình converter ánh xạ claim đó thành authority phù hợp. Không giả định Spring tự hiểu mọi cấu trúc claim tùy chỉnh. Với lab này, dùng scope chuẩn để giữ cấu hình đơn giản và dễ kiểm tra.

## 16. Xử lý token hết hạn và reconnect

JWT access token có thời hạn. Nếu token hết hạn khi connection đang mở, authentication tại SETUP không tự động được refresh. Tùy chính sách và implementation, request trên session đã xác thực có thể tiếp tục mang security context cũ; vì vậy không nên dùng SETUP authentication như cơ chế thu hồi tức thời cho mọi request.

Khi cần kiểm tra token ở mỗi request hoặc phản ánh quyền thay đổi nhanh, dùng request-time authentication hoặc đóng/re-authenticate connection theo chính sách. Client nên:

1. Lấy access token từ OAuth/OIDC client đã quản lý refresh token an toàn.
2. Tạo connection mới với token mới khi token hết hạn hoặc cần cập nhật identity.
3. Khôi phục subscription sau khi xác thực thành công.
4. Không retry vô hạn với token cũ đã bị từ chối.
5. Không ghi access token vào log, exception message hoặc telemetry.

Nếu RSocket connection bị mất và client resume session, hãy xác định rõ semantics bảo mật của session đang resume. Với thay đổi quyền hoặc token bị thu hồi, có thể cần đóng session và tạo session mới thay vì tiếp tục identity cũ.

## 17. Bảo vệ transport và dữ liệu nhạy cảm

JWT được ký không có nghĩa payload của token được mã hóa. Tránh đặt dữ liệu nhạy cảm trong claims nếu không cần; dùng TLS để bảo vệ token khi truyền qua mạng.

Checklist bảo mật:

- Dùng TLS cho TCP hoặc `wss://` cho WebSocket ở môi trường không tin cậy.
- Chỉ chấp nhận thuật toán chữ ký mà IdP và server đã thống nhất; không cho client tự chọn thuật toán.
- Xác minh chữ ký, issuer, audience và thời hạn.
- Giới hạn scope theo nguyên tắc least privilege.
- Không chấp nhận scope/role lấy từ payload nghiệp vụ của client.
- Không log bearer token hoặc authentication metadata.
- Bảo vệ refresh token và client secret trong secret manager phù hợp.
- Kiểm tra quyền tài nguyên ở service/domain layer ngoài route-level authorization.
- Có chính sách khi token hết hạn, bị thu hồi hoặc principal bị khóa.

## 18. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| SETUP bị từ chối ngay | Thiếu bearer metadata, sai MIME type hoặc token không hợp lệ. | Kiểm tra `MESSAGE_RSOCKET_AUTHENTICATION`, token và issuer. |
| Token được ký đúng nhưng bị từ chối | Issuer/audience không khớp hoặc token hết hạn. | Kiểm tra `iss`, `aud`, `exp`, `nbf` và đồng hồ server. |
| Đã xác thực nhưng route đọc bị từ chối | JWT không có `orders.read` hoặc converter ánh xạ authority khác. | Kiểm tra claim `scope` và authority `SCOPE_orders.read`. |
| Route ghi vẫn được phép với read-only token | Matcher sai route, thứ tự rule sai hoặc interceptor chưa được cài. | Kiểm tra route string, rule order và server security interceptor. |
| Handler vẫn chạy khi request bị từ chối | Security chain không bao quanh server đang chạy. | Xác minh auto-configuration/dependency và interceptor registration. |
| Client gửi token trong payload nhưng server không nhận | JWT phải nằm trong authentication metadata đúng MIME type. | Dùng `BearerTokenMetadata` và `MESSAGE_RSOCKET_AUTHENTICATION`. |
| Token mới không có hiệu lực trên connection cũ | Identity được xác thực tại SETUP. | Tạo connection mới hoặc chuyển sang request-time auth. |
| Request không có route vẫn được xử lý | Fallback authorization chưa deny các exchange không khớp. | Khai báo `anyRequest().denyAll()` và `anyExchange().denyAll()`. |

Không trả chi tiết xác minh chữ ký, JWK hoặc nội bộ IdP cho client. Log server có thể ghi loại lỗi đã được lọc và correlation ID, nhưng không ghi token.

## 19. Tiêu chí hoàn thành lab

Lab hoàn tất khi bạn chứng minh được tất cả điều sau:

- [ ] RSocket server khởi động và nhận connection.
- [ ] `ReactiveJwtDecoder` lấy khóa từ issuer/JWK và xác minh token.
- [ ] Token sai issuer, audience, chữ ký hoặc thời hạn bị từ chối.
- [ ] Client gửi bearer token trong RSocket authentication metadata.
- [ ] Token chỉ có `orders.read` gọi được route đọc.
- [ ] Token chỉ có `orders.read` bị từ chối ở route ghi.
- [ ] Token có `orders.write` gọi được route ghi.
- [ ] Route chưa khai báo và exchange không có metadata bị từ chối.
- [ ] Handler/service không chạy khi authorization thất bại.
- [ ] Client không log hoặc hard-code token/secret.
- [ ] Có ghi chú rõ mô hình authentication ở SETUP hay request time.

## 20. Mở rộng

Sau khi hoàn thành lab cơ bản, thử các thay đổi sau:

1. Thêm route `orders.cancel` và scope `orders.cancel`.
2. Tạo custom authority converter cho claim `roles` do IdP phát hành.
3. Kiểm tra quyền truy cập theo tenant/order ID trong `OrderService`.
4. Chuyển từ TCP sang WebSocket và xác minh bearer metadata không phụ thuộc transport.
5. Dùng một connection chung cho nhiều user và chuyển JWT sang request-time authentication.
6. Kết hợp connection-level identity `SETUP` với user-level JWT trên từng request.
7. Kiểm tra hành vi khi token hết hạn, refresh token và reconnect.
8. Bổ sung test cho unknown route, missing metadata và request payload không có route.
9. Thêm audit log chỉ ghi subject, route, quyết định allow/deny và correlation ID đã được lọc.

## Tài liệu tham khảo

- [Spring Security — RSocket Security](https://docs.spring.io/spring-security/reference/reactive/integrations/rsocket.html) — JWT bearer metadata, authentication tại SETUP/request và route authorization.
- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html) — `ReactiveJwtDecoder`, issuer, JWK và token validation.
- [Spring Boot — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html) — dependency, server auto-configuration và `RSocketRequester`.
- [RSocket Protocol](https://rsocket.io/about/protocol/) — authentication metadata extension và interaction models.

## Kết luận

Bạn đã bảo vệ RSocket service bằng JWT do IdP tin cậy phát hành, xác minh chữ ký và claims ở `ReactiveJwtDecoder`, rồi phân quyền theo route bằng scope authority. Bearer token được gửi qua authentication metadata của RSocket; `PayloadSocketAcceptorInterceptor` đưa authentication và authorization vào pipeline trước khi handler chạy. Với một user trên mỗi connection, xác thực tại SETUP là lựa chọn rõ ràng; với connection dùng chung cho nhiều user, cần xác thực ở từng request. Deny-by-default, kiểm tra audience, TLS, quản lý token an toàn và test cả trường hợp bị từ chối là các phần bắt buộc của một triển khai đáng tin cậy.
