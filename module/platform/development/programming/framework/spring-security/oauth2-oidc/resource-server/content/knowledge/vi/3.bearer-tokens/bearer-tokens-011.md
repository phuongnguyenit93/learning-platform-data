# Phân biệt thông tin xác thực đầu vào với danh tính sau khi xác minh

Trong Spring Security OAuth 2.0 Resource Server, một request thường mang access token ở header `Authorization: Bearer ...`. Chuỗi token này là **thông tin xác thực do bên gọi cung cấp** (*credential*). Nó thể hiện lời khẳng định rằng bên gọi sở hữu một token có thể được API chấp nhận; nhưng ngay khi nhận request, Resource Server **chưa có căn cứ để tin** nội dung của chuỗi đó.

Chỉ sau khi Spring Security xác minh token theo các cấu hình tin cậy, ứng dụng mới có một đối tượng `Authentication` đã được xác thực, chứa **danh tính/ngữ cảnh bảo mật** (*authenticated principal*) và các authority để tiếp tục phân quyền. Sự chuyển đổi từ “chuỗi Bearer do client gửi” sang “principal đã xác minh” là ranh giới tin cậy quan trọng trong luồng bảo vệ API.

Ví dụ một request:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

Tại thời điểm mới nhận, chuỗi `eyJhbGciOiJSUzI1NiIs...` **chưa chứng minh** người gọi là `user-123`. Nếu token hợp lệ, đúng issuer, audience và các điều kiện API yêu cầu, Spring Security có thể tạo principal được xác thực với `sub = user-123`. Sau đó API **vẫn phải quyết định** người gọi có quyền đọc đơn hàng `42` hay không.

## 1. Bốn khái niệm liên quan nhưng không đồng nghĩa

| Khái niệm | Câu hỏi | Ví dụ trong Resource Server |
| --- | --- | --- |
| **Credential đầu vào** | Bên gọi đưa gì để chứng minh quyền truy cập? | Chuỗi Bearer access token trong `Authorization`. |
| **Authentication — xác thực** | Credential hợp lệ theo nguồn tin cậy và các quy tắc API không? | Xác minh JWT hoặc introspection opaque token. |
| **Authenticated principal — danh tính đã xác minh** | Request hiện được xác lập dưới chủ thể bảo mật nào? | `JwtAuthenticationToken`, `BearerTokenAuthentication`, thông tin `sub`/client và authorities. |
| **Authorization — phân quyền** | Chủ thể đã xác thực được thao tác trên endpoint và đối tượng cụ thể không? | Kiểm tra `SCOPE_orders.read`, owner, tenant và trạng thái đơn hàng. |

**Credential không phải principal.** Client có thể tự gắn bất kỳ chuỗi token nào vào request; Resource Server phải kiểm tra token trước khi chấp nhận các claim như `sub`, `scope` và `tenant_id`.

**Principal đã xác thực không đồng nghĩa được toàn quyền.** Token hợp lệ vẫn có thể thiếu scope, sai tenant hoặc không có quyền trên tài nguyên cụ thể.

Đối với OIDC, **ID Token** còn là loại token có mục đích khác: nó xác nhận sự kiện đăng nhập và các claim danh tính cho OIDC Client. Resource Server bảo vệ API phải nhận **access token phù hợp với API**, không chấp nhận ID Token chỉ vì đó là JWT có chữ ký hợp lệ.

## 2. Bearer token đi vào hệ thống như thế nào?

Với OAuth 2.0 Bearer, bên sở hữu access token có thể trình token để thử truy cập protected resource. Khác cơ chế proof-of-possession, Bearer token thông thường không tự yêu cầu chứng minh việc sở hữu một khóa riêng cho từng request. Vì vậy token cần được bảo vệ như một credential.

```http
Authorization: Bearer <access-token>
```

Từ góc nhìn của Resource Server, `<access-token>` có thể là:

- JWT có chữ ký hợp lệ, issuer được tin cậy và thời gian sử dụng hợp lệ.
- JWT giả mạo, hết hạn, sai issuer, sai audience hoặc dùng thuật toán/khóa không phù hợp.
- Opaque token chỉ có thể được kiểm chứng qua introspection hoặc cơ chế tương ứng.
- Token đã được cấp cho một API/Client khác, dù do cùng Authorization Server phát hành.
- Token đại diện người dùng, service hoặc một kiểu chủ thể khác tùy theo OAuth grant/token profile.

API **không thể biết trường hợp nào là đúng chỉ từ sự hiện diện của header**.

### Header nhận dạng khác không tự tạo danh tính

Request sau chứa ba lời khai từ client:

```http
GET /api/admin/report
Authorization: Bearer <token>
X-User-Id: admin
X-Role: ADMIN
```

Hai header `X-User-Id` và `X-Role` không chứng minh người gọi là quản trị viên. Nếu backend ở sau gateway và có hợp đồng chuyển tiếp danh tính qua header, gateway phải được xác thực, phải loại bỏ header tương ứng do client tự gửi và backend phải giới hạn nguồn có quyền truyền header. Không được mặc nhiên tin header nhận dạng đến từ Internet.

> **Quy tắc tin cậy:** Dữ liệu đến từ request là đầu vào cần xác minh. Không suy ra `principal` đáng tin từ một chuỗi token, payload JWT chỉ được decode hoặc header tùy ý do client cung cấp.

## 3. Từ Bearer credential đến `Authentication`: luồng Spring Security

Với Resource Server JWT, các thành phần chính trong Spring Security có vai trò như sau:

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant F as BearerTokenAuthenticationFilter
    participant M as AuthenticationManager
    participant P as JwtAuthenticationProvider
    participant D as JwtDecoder
    participant S as SecurityContext
    participant A as Authorization / API

    C->>F: Request + Authorization: Bearer token
    F->>F: Trích xuất token chưa xác thực
    F->>M: BearerTokenAuthenticationToken
    M->>P: Yêu cầu xác thực
    P->>D: Decode và validate JWT
    alt JWT không hợp lệ
        D-->>P: Lỗi xác minh
        P-->>F: AuthenticationException
        F-->>C: 401 Unauthorized
    else JWT hợp lệ
        D-->>P: Jwt đã được xác minh
        P-->>M: JwtAuthenticationToken
        M-->>F: Authentication thành công
        F->>S: Lưu Authentication cho request
        S->>A: Principal và authorities
        A->>A: Kiểm tra quyền truy cập tài nguyên
        A-->>C: Kết quả hoặc lỗi phân quyền
    end
```

| Thành phần | Vai trò | Trạng thái tin cậy |
| --- | --- | --- |
| Header `Authorization` | Mang credential từ bên ngoài. | **Chưa xác thực.** |
| `BearerTokenAuthenticationFilter` | Trích xuất Bearer token và bắt đầu quy trình authentication. | Xử lý dữ liệu chưa tin cậy. |
| `BearerTokenAuthenticationToken` | Biểu diễn **yêu cầu** xác thực với token đầu vào. | **Chưa xác thực.** |
| `AuthenticationManager` | Chuyển yêu cầu tới provider có khả năng xử lý. | Điều phối quy trình xác thực. |
| `JwtAuthenticationProvider` / `JwtDecoder` | Kiểm tra JWT và tạo ngữ cảnh principal/authority. | Xác lập ranh giới tin cậy. |
| `JwtAuthenticationToken` | Kết quả authentication sau khi JWT được chấp nhận. | **Đã xác thực** khi được trả bởi provider đáng tin. |
| `SecurityContext` | Lưu `Authentication` của request để những thành phần sau dùng. | Chứa kết quả, không tự xác minh credential. |
| Authorization rules | Đánh giá quyền endpoint và quyền trên đối tượng dữ liệu. | Dựa vào principal hợp lệ và chính sách API. |

Điểm dễ nhầm: giao diện `Authentication` có thể biểu diễn **cả yêu cầu xác thực lẫn kết quả xác thực**. Không phải mọi object triển khai `Authentication` đều có nghĩa là người gọi đã được xác minh.

```java
// Dạng khái niệm của luồng nội bộ:
Authentication pending =
    new BearerTokenAuthenticationToken(rawAccessToken);

Authentication verified =
    authenticationManager.authenticate(pending);
```

`pending` chỉ mang credential để provider xử lý; còn `verified` là kết quả đã được provider chấp nhận. Trong Resource Server thông thường, Spring Security filter thực hiện luồng này; controller không cần tự tạo `BearerTokenAuthenticationToken`.

**Không tự đặt `isAuthenticated = true` trên một object do mình dựng từ request rồi ghi vào `SecurityContext`.** Khi đó ứng dụng có thể vô tình bỏ qua bước xác minh token. Cờ `isAuthenticated()` chỉ đáng tin trong luồng đã được cấu hình đúng.

## 4. “Đọc được JWT” khác với “JWT đã được xác minh”

Một JWT compact thường có dạng:

```text
Base64URL(header).Base64URL(payload).Base64URL(signature)
```

Payload minh họa:

```json
{
  "iss": "https://login.example.com/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "exp": 1790000000,
  "nbf": 1789990000,
  "scope": "orders.read",
  "tenant_id": "tenant-a"
}
```

Bất kỳ bên nào nhận được JWT dạng thông thường đều có thể decode hai phần đầu để xem thông tin. Base64URL **không mã hóa bí mật nội dung và không chứng minh chữ ký**. Kẻ tấn công cũng có thể tự tạo payload chứa `sub: "admin"`.

Resource Server chỉ được sử dụng các claim làm căn cứ bảo mật **sau khi** đã thực hiện các kiểm tra phù hợp:

1. **Chữ ký và thuật toán:** Xác minh bằng khóa/thuật toán đáng tin tương ứng issuer, không tin một khóa do token tự chỉ sang URL bất kỳ.
2. **Issuer (`iss`):** Chỉ chấp nhận Authorization Server được API cấu hình tin cậy.
3. **Thời gian (`exp`, `nbf`):** Token phải còn trong khoảng sử dụng hợp lệ, có xét độ lệch đồng hồ theo validator.
4. **Audience (`aud`):** Token được phát hành cho chính API hoặc đối tượng nhận mà API chấp nhận.
5. **Ràng buộc theo token profile:** Ví dụ token type, tenant, client được phép hoặc các điều kiện riêng do hợp đồng bảo mật quy định.

Cấu hình `issuer-uri` trong Spring Security hỗ trợ xác minh issuer và các validator JWT mặc định. Nhưng **đừng tự suy ra audience của API đã được kiểm tra theo chính sách nghiệp vụ** chỉ vì có `issuer-uri`; cần cấu hình audience validator hoặc cơ chế audience tương đương được phiên bản Spring Boot hỗ trợ.

### Được tin claim ở phạm vi nào?

| Claim | Vai trò sau xác minh | Điều không nên suy diễn |
| --- | --- | --- |
| `iss` | Nguồn phát hành token. | Là một quyền truy cập. |
| `sub` | Định danh subject trong ngữ cảnh issuer. | Mặc định luôn là người dùng cuối và có mọi quyền. |
| `aud` | Bên nhận dự kiến của token. | Quyền đọc/ghi. |
| `scope` / `scp` | Quyền OAuth được cấp, thường ánh xạ thành `SCOPE_*`. | Được xem mọi bản ghi của mọi tenant. |
| `tenant_id` | Bối cảnh tenant nếu issuer/token profile đáng tin định nghĩa. | Tự động được truy cập toàn bộ dữ liệu tenant. |
| `email`, `name` | Thuộc tính hồ sơ khi được cấp và cần dùng. | Định danh bất biến hoặc bằng chứng vai trò quản trị. |

Trong OIDC, cặp **`iss` + `sub`** thường là cơ sở liên kết danh tính ổn định hơn email hoặc tên hiển thị. Với token cấp theo `client_credentials`, principal có thể đại diện client/service; đừng mặc định `sub` lúc nào cũng là một End-User.

## 5. Nếu Bearer là opaque token thì principal đến từ đâu?

Opaque token không được Resource Server xác minh bằng cách tự đọc payload JWT. Ứng dụng thường sử dụng **token introspection** của Authorization Server:

```http
POST /oauth2/introspect HTTP/1.1
Host: login.example.com
Authorization: Basic <resource-server-credentials>
Content-Type: application/x-www-form-urlencoded

token=<opaque-access-token>
```

Một introspection response minh họa:

```json
{
  "active": true,
  "sub": "user-123",
  "client_id": "web-client",
  "scope": "orders.read",
  "exp": 1790000000
}
```

Nếu token được introspection endpoint đáng tin xác nhận hợp lệ và thỏa mãn chính sách API, Spring Security có thể tạo `BearerTokenAuthentication` chứa `OAuth2AuthenticatedPrincipal` cùng authorities. Nếu token không hợp lệ, không có principal đã xác thực để tiếp tục phân quyền.

Cơ chế này khác JWT local validation nhưng ranh giới tin cậy vẫn giống nhau:

```text
Opaque token từ client
    -> yêu cầu introspection đến Authorization Server đáng tin
    -> kiểm tra kết quả và chính sách API
    -> Authentication đã được xác thực
    -> phân quyền endpoint và tài nguyên
```

**Introspection khác UserInfo.** Introspection trả trạng thái/metadata access token theo giao thức và hợp đồng của Authorization Server. UserInfo trong OIDC dành cho Client có access token phù hợp để nhận claim hồ sơ người dùng khi cần. UserInfo trả thành công không chứng minh token đủ quyền gọi API, cũng không thay thế bước phân quyền.

## 6. Principal đã xác thực được đặt ở đâu?

Sau khi thành công, Spring Security lưu `Authentication` trong `SecurityContext` của request. Thành phần phía sau có thể sử dụng:

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

String name = authentication.getName();
Collection<? extends GrantedAuthority> authorities =
    authentication.getAuthorities();
```

Đây là ví dụ cho request đã qua xác thực. Với endpoint `permitAll`, context có thể không chứa Bearer principal, hoặc có anonymous authentication. Không được mặc định `getAuthentication()` luôn đại diện một tài khoản thực đã đăng nhập.

Với Resource Server JWT, principal thường là `Jwt` và `Authentication` thường là `JwtAuthenticationToken`:

```java
JwtAuthenticationToken auth = ...; // Spring Security cung cấp
Jwt jwt = auth.getToken();

String subject = jwt.getSubject();
String issuer = jwt.getIssuer().toString();
String principalName = auth.getName(); // Mặc định thường lấy từ sub
```

Nếu ứng dụng cấu hình `JwtAuthenticationConverter` riêng, tên principal và authority có thể thay đổi. Với opaque token, principal thường là `OAuth2AuthenticatedPrincipal` trong `BearerTokenAuthentication`: **không ép kiểu đối tượng thành `Jwt`** khi API không sử dụng JWT.

### Khi nào principal là người dùng, khi nào là service?

| Nguồn token | Danh tính có thể xác định | Điều phải làm rõ |
| --- | --- | --- |
| Authorization Code cho người dùng | User và các thông tin Client tùy token profile. | `iss`, `sub`, quyền được cấp và quan hệ tới tài khoản nội bộ. |
| Client Credentials | Client/service/workload. | Token đại diện ứng dụng; thường không có End-User. |
| Token đại diện quyền được ủy quyền | Chủ thể/bên đại diện tùy profile. | Cách đánh giá actor, subject và giới hạn ủy quyền. |

Không thể nhìn thấy một chuỗi `sub` rồi kết luận đó luôn là một người đang sử dụng giao diện. Mô hình audit, ownership và phân quyền phải dựa vào ý nghĩa thực của token được Authorization Server phát hành.

## 7. Ví dụ Spring Boot: để framework xác thực trước khi controller đọc danh tính

Trong Spring Boot 3 / Spring Security 6, thêm dependency:

```gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

Cấu hình issuer:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
```

Địa chỉ trên là minh họa; phải thay bằng issuer thực và cấu hình các ràng buộc audience/token profile theo hợp đồng của API.

### Xác thực Bearer JWT và phân quyền endpoint

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/whoami")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Trong ví dụ:

- `oauth2ResourceServer(...jwt(...))` thiết lập **xác thực** Bearer JWT bằng decoder/provider.
- `authenticated()` kiểm tra người gọi có `Authentication` hợp lệ, không tự cấp quyền đọc mọi tài nguyên.
- `hasAuthority("SCOPE_orders.read")` và `SCOPE_orders.write` **phân quyền** thao tác theo scope đã được ánh xạ. Spring Security mặc định thường chuyển các giá trị trong claim `scope`/`scp` thành authority có tiền tố `SCOPE_`.
- `anyRequest().denyAll()` hạn chế những API chưa có luật cụ thể.
- `STATELESS` minh họa API xác thực bằng token trên mỗi request.

Ví dụ tắt CSRF với giả định API chỉ sử dụng Bearer token truyền tường minh trong header, không phụ thuộc cookie browser tự gửi để xác thực. Với các endpoint còn dùng session/cookie login, cần đánh giá và cấu hình CSRF riêng.

### Controller đọc `Jwt` đã được xác thực

```java
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/api/whoami")
    public Map<String, String> whoami(@AuthenticationPrincipal Jwt jwt) {
        return Map.of(
            "issuer", jwt.getIssuer().toString(),
            "subject", jwt.getSubject()
        );
    }
}
```

Do endpoint yêu cầu `authenticated()` và được xử lý bởi JWT Resource Server, `@AuthenticationPrincipal Jwt jwt` biểu diễn JWT được framework cung cấp sau bước xác thực. Controller **không tự đọc chuỗi Bearer từ header để decode**.

Ví dụ chỉ trả hai giá trị dùng để minh họa nguồn gốc danh tính. API thật không nên trả toàn bộ JWT/claim nhạy cảm chỉ để debug. Với opaque token, hãy dùng kiểu principal phù hợp thay vì `Jwt`.

### Ràng buộc audience khi API yêu cầu

Nếu `orders-api` chỉ nhận JWT có audience `orders-api`, có thể bổ sung validator:

```java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class AudienceValidationConfig {

    private static final String ISSUER =
        "https://login.example.com/realms/shop";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(ISSUER).build();

        OAuth2TokenValidator<Jwt> defaults =
            JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audience =
            new JwtClaimValidator<List<String>>(
                "aud",
                values -> values != null &&
                    values.contains("orders-api"));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(defaults, audience));
        return decoder;
    }
}
```

Khi thêm audience validator, vẫn phải giữ những validation mặc định như issuer và thời gian. Nếu phiên bản Spring Boot có thuộc tính cấu hình audience phù hợp, có thể dùng cơ chế đó. Không chấp nhận token dành cho một API khác chỉ vì nó được ký bởi cùng issuer.

## 8. Có principal hợp lệ vẫn phải kiểm tra quyền trên tài nguyên

Giả sử access token đã được xác thực có:

```json
{
  "iss": "https://login.example.com/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "tenant_id": "tenant-a"
}
```

Token có thể đáp ứng luật gọi `GET /api/orders/42`, nhưng **chưa chứng minh đơn hàng 42 thuộc `user-123`**.

Ví dụ một service chỉ trả đơn hàng có đúng owner và tenant:

```java
import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class OrderService {

    private final OrderRepository orders;

    public OrderService(OrderRepository orders) {
        this.orders = orders;
    }

    public OrderDto findForCaller(long orderId, Jwt caller) {
        String subject = caller.getSubject();
        String tenantId = caller.getClaimAsString("tenant_id");

        if (tenantId == null) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN);
        }

        Order order = orders.findByIdAndTenantIdAndOwnerSubject(
                orderId, tenantId, subject)
            .orElseThrow(() ->
                new ResponseStatusException(HttpStatus.NOT_FOUND));

        return OrderDto.from(order);
    }
}
```

`OrderRepository`, `Order` và `OrderDto` là thành phần nghiệp vụ minh họa cần được hiện thực. Controller phải truyền principal `Jwt` đã xác thực vào service; quyền `orders.read` được kiểm tra bởi `SecurityFilterChain` trước khi gọi.

Truy vấn theo owner/tenant ngay từ nguồn dữ liệu giúp tránh trả về đối tượng ngoài phạm vi. Nhưng nếu issuer không phải nguồn có thẩm quyền cho `tenant_id`, Resource Server phải kiểm tra quan hệ tenant qua membership hoặc database nội bộ. Cặp `iss + sub` cũng có thể cần được ánh xạ thành ID tài khoản nội bộ để tránh va chạm danh tính giữa nhiều issuer.

Tùy hợp đồng API, tài nguyên nằm ngoài quyền xem có thể trả `403 Forbidden` hoặc `404 Not Found` để tránh tiết lộ sự tồn tại của bản ghi. Cả hai đều khác với việc credential bị từ chối ở bước authentication.

## 9. HTTP 401 và 403 phản ánh hai loại thất bại

| Tình huống | Xác thực | Phân quyền | Kết quả thường gặp |
| --- | --- | --- | --- |
| Không có Bearer token vào endpoint bắt buộc authentication | Không thành công/chưa có | Không thể cho phép | `401 Unauthorized` |
| Token sai chữ ký hoặc hết hạn | Thất bại | Không xét quyền của token | `401 Unauthorized` |
| JWT sai issuer/audience theo validator | Thất bại | Không xét quyền | `401 Unauthorized` |
| Token hợp lệ, chỉ có `orders.read`, gọi POST yêu cầu `orders.write` | Thành công | Thiếu scope | `403 Forbidden` |
| Token hợp lệ, đủ scope, đọc đơn hàng của người khác | Thành công | Không đủ quyền trên đối tượng | `403` hoặc `404` |
| Token hợp lệ, đúng quyền và owner/tenant | Thành công | Được phép | `2xx` nếu nghiệp vụ xử lý thành công |
| Endpoint được cấu hình `permitAll` và request không mang token | Không yêu cầu xác thực Bearer | Đường dẫn công khai được cho phép | Tiếp tục xử lý theo API |

Trong OAuth 2.0 Bearer, lỗi `401` thường có header `WWW-Authenticate: Bearer`; token không hợp lệ có thể đi kèm `error="invalid_token"`. Với token đã xác thực nhưng thiếu scope, response `403` có thể chỉ rõ `insufficient_scope` tùy cấu hình.

Không nên coi mọi `403` là “token sai”: token có thể hợp lệ nhưng không có đủ quyền. Cũng không nên coi việc ứng dụng in được `sub` từ payload là “đã login”: dữ liệu đó có thể chưa qua bất kỳ bước xác minh nào.

## 10. Những cách làm gây sai ranh giới tin cậy

### 10.1. Tự decode JWT trong controller

```java
// Pseudocode PHẢN VÍ DỤ; không dùng trong production.
String bearer = request.getHeader("Authorization");
String subject = decodePayloadWithoutVerification(bearer)
    .get("sub").toString();

return orderService.findOrdersFor(subject);
```

`decodePayloadWithoutVerification` chỉ minh họa một thao tác sai, không phải API sẵn có. Kẻ tấn công có thể tự tạo payload chứa `sub = admin`. Cách đúng là sử dụng JWT principal đã được `JwtDecoder`/provider của Spring Security xác thực.

### 10.2. Tự dựng `Authentication` đã đăng nhập từ header

```java
// Pseudocode PHẢN VÍ DỤ; không sử dụng.
Authentication fake =
    UsernamePasswordAuthenticationToken.authenticated(
        request.getHeader("X-User-Id"),
        null,
        List.of(new SimpleGrantedAuthority("ROLE_ADMIN")));

SecurityContextHolder.getContext().setAuthentication(fake);
```

Object có cờ authenticated không có giá trị bảo mật nếu nó được tạo từ dữ liệu chưa đáng tin. Chỉ một provider/filter xác minh credential theo chính sách mới nên xác lập principal cho request.

### 10.3. Dùng ID Token thay access token

ID Token dành cho OIDC Client xác minh sự kiện đăng nhập và nhận claim. Resource Server phải chấp nhận access token phù hợp audience và token profile của chính API. Chữ ký đúng chưa đủ để một ID Token trở thành API credential.

### 10.4. Tin rằng `SCOPE_*` cho phép xem toàn bộ dữ liệu

Scope như `orders.read` trả lời quyền gọi chức năng đọc đơn hàng. Nó không tự cấp quyền đọc dữ liệu của người khác. Cần chính sách owner/tenant, vai trò nội bộ và quy tắc nghiệp vụ.

### 10.5. Đưa token vào log, URL hoặc response

Bearer token là credential. Không ghi raw token, refresh token hoặc toàn bộ header `Authorization` vào log/trace. Tránh truyền token bằng query string dễ bị lưu trong lịch sử trình duyệt, proxy và analytics. Nếu cần quan sát, dùng request ID cùng thông tin trạng thái xác thực được phép ghi.

## 11. Truy vết một request theo đúng hai giai đoạn

Khi phân tích request `GET /api/orders/42`, các điểm quan sát hữu ích là:

```text
[1] HTTP GET /api/orders/42
[2] Bearer extraction: có token (không log raw token)
[3] JWT validation: issuer/chữ ký/thời gian/audience hợp lệ
[4] Verified principal: issuer=..., subject=user-123
[5] Authorities: SCOPE_orders.read
[6] Endpoint authorization: được phép gọi
[7] Object authorization: đơn 42 thuộc user-123, tenant-a
[8] Response: 200
```

Nếu thất bại tại `[3]` thì credential **chưa được xác thực**. Nếu thất bại tại `[6]` hoặc `[7]` thì người gọi có thể **đã được xác thực** nhưng bị từ chối quyền. Cách đọc trace này giúp xác định đúng vị trí cần sửa: decoder/token issuer, ánh xạ authority, hay chính sách tài nguyên.

### Cần phân biệt hai kiểu kiểm thử

Spring Security Test có helper `jwt()` cho MockMvc để tạo ngữ cảnh JWT giả lập và kiểm tra chính sách authorization. Nhưng `jwt()` thường **không chạy xác minh chữ ký JWT thật qua decoder**. Vì thế:

- Kiểm thử controller bằng mock JWT có thể chứng minh policy xử lý một subject/scope đã được giả lập.
- Kiểm thử tích hợp decoder/introspection cần xác nhận API thực sự từ chối token giả, hết hạn, sai issuer, sai audience.
- Kiểm thử dữ liệu cần xác nhận principal hợp lệ vẫn không đọc được đối tượng khác owner/tenant.

Đây là ba mục đích riêng. Không nên lấy kết quả “mock JWT cho phép GET” làm bằng chứng rằng lớp xác thực JWT ở môi trường thật đã cấu hình đúng.

## 12. Một sơ đồ cho toàn bộ ranh giới tin cậy

```mermaid
flowchart TD
    A["Authorization: Bearer token"] --> B["Credential từ request: chưa đáng tin"]
    B --> C{"JWT validation hoặc opaque introspection"}
    C -- "Không hợp lệ" --> D["401: không có verified principal"]
    C -- "Hợp lệ" --> E["Authentication đã xác thực"]
    E --> F["Principal + authorities trong SecurityContext"]
    F --> G{"Đủ quyền gọi endpoint?"}
    G -- "Không" --> H["403: thiếu quyền"]
    G -- "Có" --> I{"Đủ quyền trên đối tượng dữ liệu?"}
    I -- "Không" --> J["403/404 theo chính sách API"]
    I -- "Có" --> K["Thực hiện nghiệp vụ"]
```

Ở phía **trước** ranh giới xác minh, token là credential chưa đáng tin do client gửi. Ở phía **sau** ranh giới xác minh, các claim được chấp nhận mới có thể trở thành danh tính và authority cho request. Và ngay cả khi authentication thành công, quyền truy cập tài nguyên vẫn là quyết định riêng.

Khi triển khai Spring Security Resource Server, hãy để filter/provider xác thực access token, dùng `Jwt`/`Authentication` đáng tin do framework cung cấp trong controller hoặc service, rồi áp dụng chính sách quyền theo hành động và đối tượng nghiệp vụ. **Danh tính đã xác thực là kết quả kiểm tra credential — không phải bản sao trực tiếp của thông tin người gọi tự khai báo.**
