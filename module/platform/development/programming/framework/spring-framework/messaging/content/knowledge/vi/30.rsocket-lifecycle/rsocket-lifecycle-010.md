# Xác thực metadata và phân quyền route bằng Spring Security

## 1. Authentication và authorization trong RSocket

Một request RSocket có thể mang route, security token và data trong cùng một `Payload`. Spring Security dùng các metadata extension của RSocket để xác định danh tính người gửi và quyết định người đó được phép gọi route nào.

Hai khái niệm cần tách biệt:

- **Authentication (xác thực)** trả lời: request đến từ ai? Ví dụ, token có chữ ký hợp lệ, chưa hết hạn và đại diện cho principal nào?
- **Authorization (phân quyền)** trả lời: principal đó có được phép thực hiện request này không? Ví dụ, người dùng có authority `SCOPE_orders.write` mới được gọi route tạo đơn hàng.

RSocket có connection lâu dài và hỗ trợ nhiều request đồng thời trên cùng connection. Vì vậy, lựa chọn thời điểm xác thực rất quan trọng. Nếu một connection chỉ thuộc về một người dùng, xác thực lúc thiết lập connection có thể phù hợp. Nếu một connection được chia sẻ cho nhiều người dùng cuối, nên xác thực từng request để mỗi request mang danh tính riêng.

Spring Security cung cấp lớp tích hợp riêng cho RSocket. Nó không bảo vệ RSocket bằng Servlet filter chain hoặc `SecurityFilterChain` của HTTP. Luồng bảo mật được cài vào `SocketAcceptor` và xử lý từng `PayloadExchange` bằng các interceptor.

## 2. Dependency cần thiết

Với ứng dụng Spring Boot dùng Gradle và cần xác thực JWT, các dependency chính có thể khai báo như sau:

```groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.security:spring-security-rsocket")
    implementation("org.springframework.security:spring-security-messaging")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-resource-server")
}
```

Spring Boot dependency management sẽ quản lý phiên bản tương thích. Với Spring Boot 3.3.x, Spring Security thuộc nhánh 6.3.x; không tự chọn các phiên bản Spring Security khác nhau cho từng module.

Vai trò của các dependency:

- `spring-security-rsocket` cung cấp interceptor và DSL bảo mật cho RSocket.
- `spring-security-messaging` cung cấp tích hợp bảo mật cho Spring Messaging.
- `spring-boot-starter-security` cung cấp các thành phần nền tảng như authentication, authorization và password encoding.
- `spring-boot-starter-oauth2-resource-server` cung cấp hỗ trợ xác thực access token JWT và `ReactiveJwtDecoder`.

Nếu ứng dụng chỉ dùng Simple Authentication với username/password, không cần OAuth2 Resource Server chỉ vì RSocket. Nếu dùng JWT như ví dụ chính bên dưới, cần dependency Resource Server.

## 3. Kiến trúc xử lý bảo mật

Trong Spring Security RSocket, các thành phần chính phối hợp như sau:

```text
RSocketRequester
    |
    | route + authentication metadata + data
    v
RSocket transport
    |
    v
SecuritySocketAcceptorInterceptor
    |
    v
PayloadSocketAcceptorInterceptor
    |
    +--> AuthenticationPayloadInterceptor
    |       |
    |       +--> ReactiveAuthenticationManager
    |               |
    |               +--> ReactiveJwtDecoder / identity provider
    |
    +--> AuthorizationPayloadInterceptor
            |
            +--> ReactiveAuthorizationManager
                    |
                    +--> route và authority
    |
    v
RSocketMessageHandler
    |
    v
@MessageMapping handler
```

`@EnableRSocketSecurity` kích hoạt cấu hình Spring Security cho RSocket. `RSocketSecurity` là DSL để khai báo cơ chế xác thực và các quy tắc phân quyền. Khi cấu hình được build, Spring Security tạo `PayloadSocketAcceptorInterceptor` và tích hợp nó vào RSocket server thông qua `SecuritySocketAcceptorInterceptor`.

Trong ứng dụng Spring Boot có RSocket server và dependency phù hợp, auto-configuration của Spring Boot đăng ký interceptor bảo mật vào server. Nếu tự tạo RSocket server bên ngoài auto-configuration, phải tự gắn `SecuritySocketAcceptorInterceptor` vào `SocketAcceptor`.

`RSocketMessageHandler` hỗ trợ Composite Metadata và Routing Metadata mặc định. Vì vậy route và token có thể cùng nằm trong một metadata payload theo đúng extension của RSocket.

## 4. Chọn thời điểm xác thực: SETUP hay từng request?

RSocket hỗ trợ xác thực ở hai thời điểm chính:

| Thời điểm | Cách gửi metadata | Khi phù hợp |
|---|---|---|
| SETUP | `setupMetadata(value, mimeType)` | Một connection thuộc về một principal trong suốt vòng đời connection |
| Request | `metadata(value, mimeType)` | Một connection được chia sẻ, mỗi request có thể thuộc về một người dùng khác nhau |

### Xác thực ở SETUP

Requester gửi credential trong metadata của frame `SETUP`. Responder xác thực khi connection được thiết lập. Các request tiếp theo có thể sử dụng security context đã gắn với connection đó.

Cách này phù hợp với một thiết bị hoặc một client đăng nhập bằng một tài khoản rồi sử dụng connection riêng. Khi credential không hợp lệ, server có thể từ chối connection ngay ở bước thiết lập.

Không nên dùng mô hình này cho một connection dùng chung giữa nhiều người dùng cuối nếu mỗi request cần phân quyền theo người dùng riêng. Khi đó danh tính được xác thực ở SETUP chỉ đại diện cho connection, không tự thay đổi theo người dùng đang gửi request.

### Xác thực ở từng request

Requester thêm credential vào metadata của từng request. Cùng một connection có thể xử lý request của nhiều người dùng, miễn là mỗi request mang token của người dùng tương ứng.

Đây là mô hình phù hợp khi một backend hoặc gateway mở một connection RSocket dùng chung tới service phía sau. Request của Alice và Bob vẫn được xác thực độc lập, mặc dù đi qua cùng connection.

### Có thể kết hợp cả hai

Một hệ thống có thể xác thực client/service ở SETUP và xác thực người dùng cuối ở từng request. Ví dụ, credential ở SETUP chứng minh connection đến từ một backend được phép kết nối; JWT ở request chứng minh người dùng cuối có quyền thực hiện thao tác nghiệp vụ.

Nếu kết hợp, hãy xác định rõ authority nào thuộc về service và authority nào thuộc về người dùng cuối. Không để quyền của service vô tình thay thế việc kiểm tra quyền của người dùng.

## 5. Cấu hình JWT authentication và route authorization

JWT là lựa chọn phù hợp khi ứng dụng đã có identity provider phát hành access token. Client gửi JWT bằng Bearer Token Authentication Metadata Extension. Spring Security giải mã token, xác minh chữ ký và các điều kiện token thông qua `ReactiveJwtDecoder`, sau đó tạo `Authentication` để dùng trong các quyết định phân quyền.

Ví dụ cấu hình server:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.rsocket.EnableRSocketSecurity;
import org.springframework.security.config.annotation.rsocket.RSocketSecurity;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.rsocket.core.PayloadSocketAcceptorInterceptor;

@Configuration
@EnableRSocketSecurity
public class RSocketSecurityConfig {

    @Bean
    PayloadSocketAcceptorInterceptor rsocketInterceptor(
            RSocketSecurity rsocket) {

        rsocket
            .authorizePayload(authorize -> authorize
                .setup().permitAll()

                .route("admin.*").hasRole("ADMIN")

                .route("orders.create")
                    .hasAuthority("SCOPE_orders.write")

                .route("orders.read.*")
                    .hasAuthority("SCOPE_orders.read")

                .anyRequest().authenticated()
                .anyExchange().authenticated()
            )
            .jwt(Customizer.withDefaults());

        return rsocket.build();
    }

    @Bean
    ReactiveJwtDecoder jwtDecoder() {
        return NimbusReactiveJwtDecoder
                .withIssuerLocation("https://idp.example.com/issuer")
                .build();
    }
}
```

Thay `https://idp.example.com/issuer` bằng issuer URI của identity provider thực tế. `NimbusReactiveJwtDecoder.withIssuerLocation(...)` sử dụng metadata discovery của issuer để tìm khóa xác minh. Nếu identity provider không hỗ trợ discovery, có thể cấu hình JWK Set URI phù hợp.

Cần kiểm tra thêm audience của token theo API mà server cung cấp. Việc chữ ký hợp lệ và issuer đúng chưa đủ nếu token được phát hành cho một service khác. Với hệ thống thực tế, hãy cấu hình validator cho audience và các claim nghiệp vụ bắt buộc.

### Hiểu từng quy tắc authorization

- `setup().permitAll()` cho phép thiết lập connection mà không cần JWT ở SETUP. Đây là chủ ý khi ứng dụng xác thực JWT ở từng request.
- `route("admin.*").hasRole("ADMIN")` yêu cầu authority `ROLE_ADMIN` đối với route khớp mẫu `admin.*`.
- `route("orders.create").hasAuthority("SCOPE_orders.write")` yêu cầu chính xác authority `SCOPE_orders.write`.
- `route("orders.read.*").hasAuthority("SCOPE_orders.read")` áp dụng quyền đọc cho các route con thuộc nhóm `orders.read`.
- `anyRequest().authenticated()` yêu cầu mọi request còn lại phải có principal đã xác thực.
- `anyExchange().authenticated()` yêu cầu xác thực cho các exchange còn lại không thuộc nhóm request, chẳng hạn metadata push.

Các quy tắc được đánh giá theo thứ tự khai báo; quy tắc đầu tiên khớp sẽ được sử dụng. Vì thế, hãy đặt route cụ thể trước quy tắc tổng quát như `anyRequest()`. Nếu đặt `anyRequest()` trước các route cần quyền riêng, các quy tắc route phía sau sẽ không còn cơ hội được đánh giá.

`anyRequest()` áp dụng cho các payload exchange là request. `anyExchange()` rộng hơn và bao gồm cả những exchange không phải request. Trong ví dụ, SETUP được cho phép rõ ràng; các request còn lại cần authentication, và các exchange khác cũng cần authentication. Nếu ứng dụng không dùng metadata push, quy tắc này vẫn giữ chính sách kiểm soát rõ ràng cho các exchange ngoài request.

Lưu ý rằng `anyRequest().authenticated()` cho phép mọi principal đã xác thực gọi những route không có rule riêng. Nếu yêu cầu chính sách mặc định từ chối, thay fallback này bằng `anyRequest().denyAll()` rồi khai báo tường minh từng route được phép.

### Phân biệt `hasRole` và `hasAuthority`

`hasRole("ADMIN")` tự thêm tiền tố `ROLE_`, vì vậy nó kiểm tra `ROLE_ADMIN`.

`hasAuthority("SCOPE_orders.write")` so sánh đúng chuỗi authority được truyền vào. Spring Security Resource Server mặc định ánh xạ các scope trong JWT thành authority có tiền tố `SCOPE_`.

Ví dụ payload JWT có claim:

```json
{
  "iss": "https://idp.example.com/issuer",
  "sub": "alice",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write"
}
```

Khi token được xác thực, các scope trên thường được ánh xạ thành:

```text
SCOPE_orders.read
SCOPE_orders.write
```

Do đó Alice có thể gọi `orders.create` nếu token hợp lệ và chứa scope `orders.write`. Token hợp lệ nhưng thiếu scope vẫn bị từ chối ở bước authorization.

## 6. Client gửi JWT trong Composite Metadata

Spring Framework mặc định dùng Composite Metadata cho RSocket. Client có thể gửi route và Bearer token dưới dạng hai entry metadata riêng trong cùng một request.

```java
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;
import reactor.core.publisher.Mono;

public class OrderRSocketClient {

    private static final MimeType BEARER_AUTHENTICATION =
            MimeTypeUtils.parseMimeType(
                "message/x.rsocket.authentication.bearer.v0");

    public Mono<OrderReceipt> createOrder(
            RSocketRequester requester,
            String accessToken,
            CreateOrder command) {

        return requester
                .route("orders.create")
                .metadata(accessToken, BEARER_AUTHENTICATION)
                .data(command)
                .retrieveMono(OrderReceipt.class);
    }
}
```

Trong ví dụ, `requester` là một RSocket connection đã được thiết lập; `CreateOrder` và `OrderReceipt` là các DTO của ứng dụng.

1. `route("orders.create")` tạo Routing Metadata để server xác định handler.
2. `metadata(accessToken, BEARER_AUTHENTICATION)` thêm Bearer token vào metadata của request.
3. `data(command)` mã hóa dữ liệu nghiệp vụ ở phần data.
4. `retrieveMono(OrderReceipt.class)` giải mã phản hồi thành kiểu kết quả mong muốn.

MIME type `message/x.rsocket.authentication.bearer.v0` là MIME type của Bearer Token Authentication Metadata Extension. Khi dùng `.jwt(Customizer.withDefaults())`, Spring Security tự cấu hình converter để trích xuất token từ extension này và chuyển token thành authentication request.

Không cần tự tạo một header `Authorization` theo định dạng HTTP hoặc tự ghép chuỗi token vào data. Hãy dùng đúng metadata extension để hai phía hiểu cùng một giao thức.

Nếu muốn gửi thêm metadata ứng dụng như tenant ID hoặc correlation ID, có thể gọi thêm `.metadata(value, mimeType)` với MIME type tương ứng. Các giá trị này chỉ là dữ liệu do client cung cấp. Chúng không tự chứng minh tenant, vai trò hoặc quyền truy cập của principal. Server phải đối chiếu chúng với identity đã xác thực và chính sách lưu trữ.

## 7. Xác thực username/password ở SETUP bằng Simple Authentication

Nếu một connection đại diện cho một người dùng duy nhất, có thể dùng Simple Authentication Metadata Extension. Phía client gửi `UsernamePasswordMetadata` trong SETUP và đăng ký `SimpleAuthenticationEncoder` để mã hóa đúng định dạng.

Ví dụ cấu hình bảo mật phía server:

```java
@Bean
PayloadSocketAcceptorInterceptor rsocketInterceptor(
        RSocketSecurity rsocket) {

    rsocket
        .authorizePayload(authorize -> authorize
            .setup().authenticated()
            .route("admin.*").hasRole("ADMIN")
            .anyRequest().authenticated()
            .anyExchange().authenticated()
        )
        .simpleAuthentication(Customizer.withDefaults());

    return rsocket.build();
}
```

Phía server cần có `ReactiveAuthenticationManager` hoặc cấu hình user service phù hợp để xác minh username/password. Ví dụ đơn giản có thể dùng `MapReactiveUserDetailsService` trong môi trường học tập; ứng dụng thật nên dùng user store hoặc identity provider phù hợp và `PasswordEncoder` an toàn.

Client gửi credential khi kết nối:

```java
import io.rsocket.metadata.WellKnownMimeType;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.security.rsocket.metadata.SimpleAuthenticationEncoder;
import org.springframework.security.rsocket.metadata.UsernamePasswordMetadata;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;
import reactor.core.publisher.Mono;

public class SecureRSocketConnection {

    public Mono<RSocketRequester> connect(
            RSocketRequester.Builder builder,
            String host,
            int port,
            String username,
            String password) {

        MimeType simpleAuthenticationMimeType =
                MimeTypeUtils.parseMimeType(
                    WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());

        UsernamePasswordMetadata credentials =
                new UsernamePasswordMetadata(username, password);

        return builder
                .setupMetadata(credentials, simpleAuthenticationMimeType)
                .rsocketStrategies(strategies ->
                        strategies.encoder(new SimpleAuthenticationEncoder()))
                .connectTcp(host, port);
    }
}
```

`SimpleAuthenticationEncoder` mã hóa `UsernamePasswordMetadata` theo Simple Authentication extension. Server dùng cơ chế xác thực đã cấu hình để kiểm tra credential.

Simple Authentication truyền username/password trong metadata; bản thân extension không mã hóa bí mật. Khi sử dụng, phải bảo vệ transport bằng TLS để bảo đảm tính bí mật và xác thực của dữ liệu truyền đi. Không ghi credential vào log và không dùng user/password mẫu trong môi trường production.

Đây là cấu hình thay thế cho ví dụ JWT ở phần trước. Không đăng ký hai bean interceptor cùng mục đích mà không có thiết kế rõ ràng cho việc kết hợp các cơ chế xác thực.

## 8. Kết hợp route authorization với method security

Route authorization bảo vệ ranh giới RSocket: principal nào được phép gọi một route. Method security có thể bổ sung quy tắc ở tầng service để cùng nghiệp vụ được bảo vệ ngay cả khi được gọi từ một đường đi khác.

Ví dụ các DTO nghiệp vụ:

```java
public record CreateOrder(String orderId) {
}

public record OrderReceipt(String orderId, String status) {
}
```

Service dùng reactive method security:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class OrderService {

    @PreAuthorize("hasAuthority('SCOPE_orders.write')")
    public Mono<OrderReceipt> create(CreateOrder command) {
        // Thực hiện nghiệp vụ tạo đơn hàng.
        return Mono.just(new OrderReceipt(command.orderId(), "ACCEPTED"));
    }
}
```

Để kích hoạt, khai báo `@EnableReactiveMethodSecurity` trong cấu hình ứng dụng:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
public class MethodSecurityConfig {
}
```

Reactive method security phù hợp với phương thức trả về `Mono` hoặc `Flux`. Có thể dùng route authorization để từ chối sớm request không hợp lệ, sau đó dùng `@PreAuthorize` tại service để bảo vệ nghiệp vụ quan trọng. Hãy giữ các quy tắc nhất quán để tránh route cho phép request nhưng service lại có chính sách khác ngoài dự kiến.

## 9. Gắn interceptor khi không dùng Spring Boot auto-configuration

Nếu dùng Spring Boot với RSocket server auto-configured và dependency phù hợp, Spring Boot tự đăng ký security interceptor. Khi tự tạo RSocket server, cần gắn `SecuritySocketAcceptorInterceptor` vào server.

Ví dụ dùng `RSocketServerCustomizer`:

```java
import org.springframework.boot.rsocket.server.RSocketServerCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.security.rsocket.core.SecuritySocketAcceptorInterceptor;

@Bean
RSocketServerCustomizer springSecurityRSocketSecurity(
        SecuritySocketAcceptorInterceptor interceptor) {

    return server -> server.interceptors(registry ->
            registry.forSocketAcceptor(interceptor));
}
```

Nếu quên gắn interceptor vào server tự tạo, bean cấu hình authorization có thể tồn tại nhưng các request thực tế không đi qua lớp bảo mật đó. Khi kiểm thử, cần xác minh cả cấu hình DSL lẫn đường khởi tạo RSocket server.

## 10. Kiểm thử authentication và authorization

Kiểm thử nên bao gồm cả trường hợp thành công và thất bại. Có thể dùng integration test với `RSocketRequester`, token test được phát hành bởi test issuer hoặc `ReactiveJwtDecoder` giả lập, và Reactor Test `StepVerifier`.

| Tình huống | Token / authority | Route | Kết quả mong đợi |
|---|---|---|---|
| Thiếu token | Không có token | `orders.create` | Authentication bị từ chối |
| Token sai chữ ký hoặc hết hạn | JWT không hợp lệ | `orders.create` | Authentication bị từ chối |
| Thiếu scope | Token hợp lệ, không có `SCOPE_orders.write` | `orders.create` | Authorization bị từ chối |
| Có đúng scope | Token hợp lệ, có `SCOPE_orders.write` | `orders.create` | Request được chuyển tới handler |
| Không có role quản trị | Không có `ROLE_ADMIN` | `admin.users` | Authorization bị từ chối |
| Có role quản trị | Có `ROLE_ADMIN` | `admin.users` | Request được chuyển tới handler |
| Không có route đặc biệt | Token hợp lệ | Route còn lại | Được phép nếu đáp ứng `anyRequest().authenticated()` |

Ví dụ kiểm thử một request bị từ chối có thể dùng `StepVerifier`:

```java
StepVerifier.create(
        requester.route("orders.create")
                .metadata(readOnlyToken, BEARER_AUTHENTICATION)
                .data(command)
                .retrieveMono(OrderReceipt.class))
    .expectError()
    .verify();
```

Đoạn kiểm thử trên giả định `requester`, `readOnlyToken` và `command` đã được chuẩn bị trong test. Trong test thực tế, hãy kiểm tra loại exception hoặc error signal cụ thể theo phiên bản RSocket Java và cách server chuyển tiếp lỗi. Không giả định mọi lỗi RSocket đều là HTTP 401 hoặc 403; RSocket không trả về HTTP status cho request như một HTTP endpoint.

Phân biệt hai loại lỗi:

- **Authentication failure**: thiếu token, token sai chữ ký, hết hạn hoặc không được chấp nhận.
- **Access denied**: token đã được xác thực nhưng principal không có authority cần thiết.

Cần kiểm tra thêm request không có route, route sai mẫu, metadata authentication bị thiếu, SETUP bị từ chối và request dùng chung connection với các principal khác nhau.

## 11. Lỗi thường gặp và cách khắc phục

| Lỗi | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Đã cấu hình `RSocketSecurity` nhưng request vẫn không bị chặn | Security interceptor chưa được gắn vào server tự tạo | Kiểm tra `SecuritySocketAcceptorInterceptor` và `RSocketServerCustomizer` |
| Token có trong metadata nhưng server không xác thực | MIME type không đúng Bearer extension hoặc chưa bật `.jwt()` | Dùng `message/x.rsocket.authentication.bearer.v0` và `.jwt(Customizer.withDefaults())` |
| Request dùng chung connection bị gắn nhầm danh tính | Chỉ xác thực ở SETUP trong khi nhiều user dùng cùng connection | Gửi token ở từng request |
| Kết nối thất bại ngay ở SETUP | Quy tắc `setup().authenticated()` nhưng client không gửi credential trong SETUP | Cho phép SETUP nếu dùng request-time auth hoặc gửi credential ở SETUP |
| Người dùng có scope vẫn bị từ chối | Authority trong rule không khớp authority được tạo từ claim JWT | Kiểm tra `scope`/`scp` và tiền tố `SCOPE_` |
| Route quản trị không được phép | `hasRole("ADMIN")` đang kiểm tra `ROLE_ADMIN` | Cấp đúng role hoặc dùng `hasAuthority` với authority thực tế |
| Quy tắc route không có hiệu lực | `anyRequest()` được khai báo trước route cụ thể | Đưa route cụ thể lên trước quy tắc tổng quát |
| Token hợp lệ nhưng dùng được ở service khác | Chưa kiểm tra audience | Cấu hình audience validator cho resource server |
| Metadata tenant bị giả mạo | Tin trực tiếp giá trị tenant do client gửi | Đối chiếu tenant với principal và dữ liệu được cấp quyền |

Các lưu ý vận hành:

1. Dùng HTTPS/TLS tương ứng với transport RSocket để bảo vệ token và payload trên đường truyền.
2. Không xem route hoặc tenant metadata là bằng chứng xác thực. Client có thể tự tạo metadata.
3. Không log access token, username/password hoặc metadata nhạy cảm.
4. Đặt thời hạn token hợp lý và xử lý việc refresh token ở phía client.
5. Kiểm tra issuer, chữ ký, expiration, audience và các claim cần thiết trước khi dùng JWT để phân quyền.
6. Nếu muốn mặc định từ chối route không được khai báo, dùng `anyRequest().denyAll()` sau các rule cho phép thay vì `anyRequest().authenticated()`.
7. Khi thay đổi route matcher hoặc separator, kiểm thử lại tất cả pattern đang dùng. Route RSocket thường dùng dấu chấm làm separator, ví dụ `orders.read.one`, thay vì đường dẫn URL dùng dấu gạch chéo.
8. Nếu dùng cả route authorization và method security, kiểm tra chính sách ở hai lớp để không có service method quan trọng nào bị bỏ sót.

## 12. Checklist triển khai

- [ ] Đã chọn rõ authentication ở SETUP, từng request hoặc kết hợp cả hai.
- [ ] Connection dùng chung cho nhiều user đã xác thực riêng từng request.
- [ ] Server đã bật `@EnableRSocketSecurity`.
- [ ] `PayloadSocketAcceptorInterceptor` được build và gắn vào RSocket server.
- [ ] JWT dùng Bearer Token Authentication Metadata Extension đúng MIME type.
- [ ] `ReactiveJwtDecoder` xác minh issuer, chữ ký, expiration và audience theo chính sách.
- [ ] Rule route cụ thể được khai báo trước `anyRequest()` và `anyExchange()`.
- [ ] `hasRole` và `hasAuthority` khớp với authority thực tế.
- [ ] Request không có rule riêng vẫn phải qua chính sách fallback đã chọn.
- [ ] Metadata do client gửi không được dùng làm bằng chứng phân quyền độc lập.
- [ ] Transport được bảo vệ bằng TLS khi truyền token hoặc credential.
- [ ] Integration test bao gồm token thiếu, token sai, thiếu quyền và có quyền.
- [ ] Method security được bật nếu cần bảo vệ nghiệp vụ ở tầng service.

## Tài liệu tham khảo

- [Spring Security Reference — RSocket Security](https://docs.spring.io/spring-security/reference/reactive/integrations/rsocket.html)
- [Spring Security 6.3 API — RSocketSecurity](https://docs.spring.io/spring-security/site/docs/6.3.8/api/org/springframework/security/config/annotation/rsocket/RSocketSecurity.html)
- [Spring Security 6.3 API — SimpleAuthenticationEncoder](https://docs.spring.io/spring-security/site/docs/6.3.8/api/org/springframework/security/rsocket/metadata/SimpleAuthenticationEncoder.html)
- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Boot 3.3 API — RSocketServerCustomizer](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/rsocket/server/RSocketServerCustomizer.html)
