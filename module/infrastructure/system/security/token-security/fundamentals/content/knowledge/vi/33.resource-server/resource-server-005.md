# AuthenticationManagerResolver trong Spring Security Resource Server

## 1. Bài toán: một API nhưng có nhiều cách xác thực access token

Giả sử một hệ thống cung cấp các API cho khách hàng, đối tác và dịch vụ nội bộ:

- Khách hàng A đăng nhập qua Authorization Server A, nhận **JWT access token**.
- Khách hàng B đăng nhập qua Authorization Server B, cũng nhận JWT nhưng dùng issuer, khóa ký và quyền truy cập riêng.
- Đối tác cũ dùng **opaque access token**; API phải gọi introspection endpoint để xác nhận token còn hiệu lực.

Cả ba nhóm đều có thể gọi đến một **OAuth 2.0 Resource Server**. Nếu chỉ cấu hình một `JwtDecoder` hoặc một `OpaqueTokenIntrospector` cho toàn bộ ứng dụng, Resource Server có thể không xử lý được mọi token theo chính sách tương ứng.

**`AuthenticationManagerResolver` giải quyết việc chọn đúng `AuthenticationManager` cho từng request.** Nó là cơ chế định tuyến xác thực ở thời điểm nhận request, không phải thành phần phát hành token và không tự động cấp quyền truy cập.

Trong module **`SECURITY_TOKEN_SECURITY_FUNDAMENTALS`**, cơ chế này kết nối trực tiếp với mô hình tin cậy và vòng đời token: Resource Server phải xác định **bên phát hành được tin cậy**, dùng **cách kiểm chứng tương ứng**, kiểm tra **claims/active status**, **audience**, **scope** và chỉ sau đó mới cho phép truy cập tài nguyên. Việc lựa chọn sai AuthenticationManager có thể dẫn đến chấp nhận nhầm token từ một hệ thống không phù hợp.

> **Mục tiêu bài học:** hiểu vị trí của `AuthenticationManagerResolver` trong Spring Security, phân biệt nó với `AuthenticationManager` và `AuthenticationProvider`; cấu hình được multi-issuer JWT và JWT/opaque token; biết cách hạn chế issuer confusion, token substitution, SSRF và sai sót phân quyền.

## 2. Vai trò của AuthenticationManagerResolver

Trong Spring Security Servlet, interface có ý nghĩa:

```java
@FunctionalInterface
public interface AuthenticationManagerResolver<C> {
    AuthenticationManager resolve(C context);
}
```

Với OAuth 2.0 Resource Server nhận HTTP request, kiểu thường gặp là:

```java
AuthenticationManagerResolver<HttpServletRequest>
```

Một `AuthenticationManager` nhận một đối tượng `Authentication` chưa xác thực, ví dụ `BearerTokenAuthenticationToken`, rồi thực hiện xác thực và trả về kết quả hoặc ném ngoại lệ xác thực. `AuthenticationManagerResolver` nhận **ngữ cảnh request**, chọn **manager nào sẽ làm việc đó**. Nó không thay thế bước xác minh token.

| Thành phần | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| `BearerTokenResolver` | Lấy chuỗi bearer token từ đâu trong HTTP request? | Đọc `Authorization: Bearer ...`. |
| `AuthenticationManagerResolver<HttpServletRequest>` | Request này phải sử dụng bộ xác thực nào? | Issuer A → manager A; issuer B → manager B. |
| `AuthenticationManager` | Đối tượng `Authentication` này có xác thực được không? | `ProviderManager` chuyển cho provider phù hợp. |
| `AuthenticationProvider` | Xác thực token theo cơ chế cụ thể nào? | `JwtAuthenticationProvider` hoặc `OpaqueTokenAuthenticationProvider`. |
| `JwtDecoder` | Kiểm tra JWT ra sao? | Kiểm tra chữ ký, thuật toán và claims theo validator đã cấu hình. |
| `OpaqueTokenIntrospector` | Opaque token còn hợp lệ và có thuộc tính gì? | Gọi introspection endpoint, đọc `active`, `scope` và các thuộc tính khác. |
| Authorization rules | Người dùng/token đã xác thực có quyền gọi endpoint không? | `hasAuthority("SCOPE_orders.read")`. |

**Cần phân biệt:** Trong Java, phương thức `AuthenticationManagerResolver.resolve(request)` quyết định **người xác thực**; phương thức `AuthenticationManager.authenticate(authentication)` mới thực hiện **xác thực**. Sau đó `authorizeHttpRequests` và/hoặc method security mới quyết định **phân quyền**.

### Dòng xử lý request

```mermaid
sequenceDiagram
    participant C as Client
    participant F as BearerTokenAuthenticationFilter
    participant R as AuthenticationManagerResolver
    participant M as AuthenticationManager
    participant V as JwtDecoder / Introspector
    participant A as Authorization

    C->>F: GET /api/orders + Authorization: Bearer TOKEN
    F->>F: BearerTokenResolver đọc token
    F->>R: resolve(HttpServletRequest)
    R-->>F: Manager phù hợp
    F->>M: authenticate(BearerTokenAuthenticationToken)
    M->>V: Kiểm tra token, issuer/claims hoặc introspection
    V-->>M: Kết quả xác minh
    M-->>F: Authentication đã xác thực
    F->>A: SecurityContext + authorities
    A-->>C: Cho phép truy cập hoặc từ chối
```

Khi không có bearer token, cách xử lý còn phụ thuộc cấu hình filter và endpoint có cho phép anonymous hay không. Khi có token nhưng không hợp lệ, Resource Server thường trả **401 Unauthorized** với thông tin `WWW-Authenticate: Bearer` phù hợp. Khi token hợp lệ nhưng thiếu quyền cần thiết, kết quả thường là **403 Forbidden**. Không nên ghi nguyên token vào log khi điều tra.

### Ví dụ tư duy

```text
GET /api/orders/7
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
        │
        ▼
AuthenticationManagerResolver
        ├── issuer = https://idp-a.example.com  → JWT manager A
        ├── issuer = https://idp-b.example.com  → JWT manager B
        └── issuer khác                      → reject
```

Sơ đồ chỉ mô tả **chọn manager**. Việc đọc được `iss` để chọn nhánh chưa có nghĩa token đã được ký hợp lệ; manager được chọn vẫn phải kiểm tra chữ ký, claim issuer và các điều kiện tin cậy khác.

## 3. Khi nào nên dùng Resolver?

| Tình huống | Cách tiếp cận thường hợp lý |
| --- | --- |
| Một Resource Server chỉ chấp nhận JWT từ **một issuer** | Cấu hình `oauth2ResourceServer().jwt()` và một `JwtDecoder`; thông thường chưa cần resolver. |
| Một Resource Server chỉ chấp nhận opaque token từ **một nơi introspection** | Cấu hình `opaqueToken()` và một `OpaqueTokenIntrospector`. |
| Một API nhận JWT từ **nhiều issuer tin cậy** | `JwtIssuerAuthenticationManagerResolver` chọn manager theo issuer. |
| Một ứng dụng nhận cả JWT và opaque token tùy vùng API | Tự cung cấp `AuthenticationManagerResolver<HttpServletRequest>` dựa trên quy tắc route đáng tin cậy. |
| Nhiều tenant được thêm/bớt trong khi hệ thống chạy | Repository các manager theo issuer và resolver tra cứu repository. |
| Các API có đường dẫn tách biệt và chính sách bảo mật độc lập | Có thể cân nhắc **nhiều `SecurityFilterChain`** với `securityMatcher`; không phải trường hợp nào cũng cần resolver chung. |

Khái niệm multi-tenancy trong Resource Server là có nhiều chiến lược **kiểm chứng bearer token** tương ứng với tenant/issuer. Việc tenant A và B cùng dùng một hệ thống không đồng nghĩa token của A được phép truy cập tài nguyên B. **Xác thực issuer** và **kiểm soát tenant ở nghiệp vụ** là hai lớp cần đồng bộ.

## 4. Trường hợp phổ biến: JWT từ nhiều issuer tin cậy

### 4.1. Ví dụ Spring Security Servlet

Với Spring Security **6.2 trở lên** và ứng dụng Servlet (Spring Boot 3 / các phiên bản tương thích), có thể dùng `JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(...)`:

```java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerAuthenticationManagerResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    AuthenticationManagerResolver<HttpServletRequest> jwtManagerResolver() {
        return JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
                "https://idp-a.example.com/realms/customers",
                "https://idp-b.example.com/realms/partners"
        );
    }

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            AuthenticationManagerResolver<HttpServletRequest> jwtManagerResolver
    ) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers("/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .authenticationManagerResolver(jwtManagerResolver)
            );
        return http.build();
    }
}
```

Ví dụ giả định ứng dụng đã thêm starter/dependencies Resource Server cần thiết và các issuer demo có metadata/JWK endpoint hợp lệ. Cấu hình này tập trung vào resolver; dự án thật còn cần thiết kế rule cho phương thức HTTP, CSRF nếu dùng cookie, CORS nếu có browser client, logging và các endpoint khác.

### 4.2. Tại sao phải dùng danh sách issuer tin cậy?

Mỗi JWT có thể mang claim:

```json
{
  "iss": "https://idp-a.example.com/realms/customers",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1900000000
}
```

Khi nhận token, resolver có thể **đọc** `iss` từ JWT để biết cần chọn manager nào. Nhưng trước khi kiểm chứng chữ ký, mọi claim trong token đều **chưa đáng tin cậy**. Quy trình đúng là:

1. Trích xuất issuer theo cơ chế resolver.
2. Đối chiếu issuer với **danh sách cho phép** do hệ thống quản lý.
3. Chỉ chọn manager/JWK configuration thuộc issuer được cho phép.
4. Manager kiểm tra chữ ký JWT và các claims tương ứng, trong đó phải có issuer phù hợp.
5. Sau khi xác thực mới dùng claims đã kiểm chứng để ra quyết định phân quyền và tenant nghiệp vụ.

**Tuyệt đối không biến `iss` bất kỳ trong token thành endpoint để tải JWK hoặc discovery.** Kẻ tấn công có thể tự dựng issuer, phát hành token do chính họ ký, hoặc khiến server gọi URL không được phép (SSRF). Một JWT có chữ ký hợp lệ từ một issuer bất kỳ **không phải** là JWT được hệ thống tin cậy.

`JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(...)` giúp biểu diễn ranh giới tin cậy đó. Issuer phải được so sánh **đúng giá trị**, lưu ý scheme, host, path và dấu `/` ở cuối.

### 4.3. Khởi tạo lười (lazy initialization)

Với cách cấu hình issuer tin cậy, các thành phần xác thực cho một issuer có thể chỉ được tạo khi request đầu tiên từ issuer đó xuất hiện. Điều này giúp ứng dụng có thể khởi động mà chưa cần phụ thuộc ngay vào khả năng truy cập tất cả issuer.

Đổi lại, **request đầu tiên** đến một issuer có thể phải chờ discovery/JWK retrieval; cần tính đến timeout, giám sát kết nối và cách xử lý issuer tạm thời không sẵn sàng. Không nên dùng mạng động để tin cậy một issuer do client tự khai.

## 5. Đưa issuer vào AuthenticationManager tùy biến

Trong hệ thống cần cấu hình riêng mỗi issuer (khác `aud`, converter scope/role, decoder hoặc tenant policy), ta có thể đưa các manager đã cấu hình vào một registry.

### 5.1. Registry cố định với manager tách biệt

```java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationProvider;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerAuthenticationManagerResolver;

import java.util.Map;

@Bean
AuthenticationManagerResolver<HttpServletRequest> tenantManagers(
        JwtDecoder issuerADecoder,
        JwtDecoder issuerBDecoder
) {
    String issuerA = "https://idp-a.example.com/realms/customers";
    String issuerB = "https://idp-b.example.com/realms/partners";

    AuthenticationManager managerA =
        new ProviderManager(new JwtAuthenticationProvider(issuerADecoder));
    AuthenticationManager managerB =
        new ProviderManager(new JwtAuthenticationProvider(issuerBDecoder));

    Map<String, AuthenticationManager> allowed = Map.of(
        issuerA, managerA,
        issuerB, managerB
    );

    return new JwtIssuerAuthenticationManagerResolver(allowed::get);
}
```

Trong ví dụ này:

- `allowed` đóng vai trò **allowlist**: chỉ có hai issuer được map tới manager.
- Mỗi `JwtDecoder` phải được cấu hình **độc lập và đúng issuer**, thuật toán, khóa và audience được tin cậy cho tenant đó.
- `allowed::get` trả về manager theo issuer đã đọc từ token; issuer không có trong bản đồ không được tự tạo manager mới.
- Đoạn code minh họa một bean được đặt trong lớp cấu hình Spring và giả định hai `JwtDecoder` được định danh/tiêm đúng cách (ví dụ qua `@Qualifier`). Nếu ứng dụng có nhiều bean cùng kiểu `JwtDecoder`, cần phân biệt rõ chúng.

Đây là mô hình hỗ trợ cấu hình chi tiết hơn `fromTrustedIssuers`. Nếu không có yêu cầu đặc thù, cách dùng allowlist trực tiếp ở phần 4 thường gọn và dễ bảo trì hơn.

### 5.2. Tenant động

Khi tenant xuất hiện hoặc bị thu hồi sau khi deploy, có thể dùng registry mutable:

```java
// Mã minh họa bên trong một service quản trị registry.
private final Map<String, AuthenticationManager> managers =
        new ConcurrentHashMap<>();

public void registerTrustedIssuer(String issuer, JwtDecoder validatedDecoder) {
    // Chỉ được gọi sau khi backend xác minh issuer qua nguồn cấu hình tin cậy.
    managers.put(
        issuer,
        new ProviderManager(new JwtAuthenticationProvider(validatedDecoder))
    );
}

public void revokeTrustedIssuer(String issuer) {
    managers.remove(issuer);
}

public AuthenticationManagerResolver<HttpServletRequest> resolver() {
    return new JwtIssuerAuthenticationManagerResolver(managers::get);
}
```

Đoạn này là **mẫu triển khai ý tưởng**, không phải một service hoàn chỉnh có kiểm soát quản trị. Trong hệ thống thật, cần xác thực quyền của người được phép đăng ký issuer, kiểm duyệt cấu hình discovery/JWKS, chặn SSRF, điều khiển thay đổi tập trung giữa nhiều node và đánh giá hành vi của các request đang xử lý khi tenant bị gỡ.

Một số yêu cầu vận hành:

- **Không thêm issuer theo `iss` của request lạ**. Đăng ký issuer phải xuất phát từ dữ liệu cấu hình/tenant repository được kiểm soát.
- Kiểm tra rõ thuật toán ký, metadata endpoint, `jwks_uri`; giới hạn URL outbound, timeout và kích thước phản hồi.
- Bảo đảm decoder/validator của issuer được cập nhật khi thay đổi khóa ký, audience hoặc chính sách; đăng ký lại manager phải có quy trình.
- Có cơ chế loại bỏ tenant, giám sát cache và thất bại xác thực. Registry phân tán cần cách đồng bộ nhất quán.
- Tránh tạo manager/decoder mới **trên mỗi request**; điều đó gây tốn tài nguyên và tạo rủi ro phụ thuộc mạng ngoài ý muốn.

## 6. Kết hợp JWT và opaque token trong cùng một Resource Server

### 6.1. Khác nhau về xác thực

| Tiêu chí | JWT access token | Opaque access token |
| --- | --- | --- |
| Hình thức | Thường là token dạng JWS với header.payload.signature. | Chuỗi không biểu lộ claims theo cách Resource Server đọc trực tiếp. |
| Kiểm chứng | `JwtDecoder` kiểm tra chữ ký/thuật toán/claims theo khóa tin cậy. | `OpaqueTokenIntrospector` gọi endpoint để biết token có `active` và thông tin quyền không. |
| Phụ thuộc mạng mỗi request | Thường không cần nếu có JWK trong cache; vẫn có lúc phải tải/làm mới khóa. | Thường cần gọi introspection endpoint, trừ khi có thiết kế cache riêng với đánh đổi độ trễ thu hồi. |
| Thu hồi | Chữ ký hợp lệ có thể tiếp tục được chấp nhận đến `exp` nếu không có revocation/replay check bổ sung. | Introspection có thể phản ánh `active=false` nhanh hơn, tùy server và cache. |
| Phân quyền | Map scope/claims sang `GrantedAuthority` sau khi xác minh. | Map scope/attributes của kết quả introspection sang authorities. |

**JWT hay opaque chỉ nói đến cách biểu diễn/kiểm chứng token.** Access token mới là credential Resource Server dùng để truy cập API. **Refresh token** dùng để xin access token mới ở Authorization Server và **ID token** trong OIDC dành cho client xác minh phiên đăng nhập; không được mặc nhiên coi hai loại đó là access token hợp lệ cho API.

### 6.2. Chọn manager theo đường dẫn API

Giả sử hợp đồng API quy định:

- `/api/**`: chấp nhận JWT access token của hệ thống chính.
- `/legacy/**`: chấp nhận opaque access token của đối tác cũ.

Có thể biểu diễn lựa chọn bằng request path:

```java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationProvider;
import org.springframework.security.oauth2.server.resource.authentication.OpaqueTokenAuthenticationProvider;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

@Bean
AuthenticationManagerResolver<HttpServletRequest> mixedTokenResolver(
        JwtDecoder jwtDecoder,
        OpaqueTokenIntrospector introspector
) {
    AuthenticationManager jwtManager =
        new ProviderManager(new JwtAuthenticationProvider(jwtDecoder));
    AuthenticationManager opaqueManager =
        new ProviderManager(new OpaqueTokenAuthenticationProvider(introspector));

    // /legacy/** có chính sách opaque; các đường dẫn còn lại chọn JWT.
    return request -> request.getServletPath().startsWith("/legacy/")
        ? opaqueManager
        : jwtManager;
}
```

Đăng ký bean resolver này bằng DSL:

```java
@Bean
SecurityFilterChain apiChain(
        HttpSecurity http,
        AuthenticationManagerResolver<HttpServletRequest> mixedTokenResolver
) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/legacy/**")
                .hasAuthority("SCOPE_legacy.read")
            .requestMatchers("/api/**")
                .hasAuthority("SCOPE_api.read")
            .anyRequest().denyAll()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .authenticationManagerResolver(mixedTokenResolver)
        );
    return http.build();
}
```

Mỗi snippet `@Bean` được đặt trong lớp `@Configuration` có các import Spring tương ứng; hai snippet minh họa một cấu hình liên kết. Trong ứng dụng thật, có thể chọn cấu trúc `SecurityFilterChain` riêng cho `/legacy/**` và `/api/**` nếu quy tắc hoàn toàn độc lập.

**Tại sao không chọn bằng cách nhìn token có ba phần ngăn bởi dấu chấm?** Một chuỗi trông giống JWT chưa được xác minh và một opaque token không bắt buộc phải tránh ký tự `.`. Phân loại bằng hình thức token có thể đưa request vào sai trust policy. Nếu cần xử lý cùng endpoint với nhiều định dạng, phải thiết kế **quy tắc nguồn token có thể kiểm chứng**, danh sách issuer/client tin cậy và kiểm tra chặt bên trong từng manager; không chấp nhận kiểu “thử xác thực JWT thất bại thì tự động cho chạy opaque” nếu không kiểm soát được sự nhập nhằng.

## 7. Resolver không thay thế việc kiểm tra claims và phân quyền

Một lỗi dễ gặp là đã chọn được manager từ issuer A và kết luận token đó được phép gọi mọi API. Thực tế:

1. Token phải được phát hành bởi issuer **được cho phép**.
2. JWT phải được kiểm tra chữ ký, thuật toán, `exp`, `nbf`, `iss`; opaque token phải được introspect và có trạng thái hợp lệ.
3. `aud` phải ràng buộc token với **Resource Server này**. Access token phát hành cho API khác không tự nhiên có quyền dùng ở đây.
4. `scope`, role/authorities và policy endpoint phải cho phép thao tác đang gọi.
5. Ứng dụng đa tenant phải kiểm tra **quan hệ giữa principal/tenant đã xác thực và tài nguyên**. Một `tenant_id`/`X-Tenant-Id` do client tùy ý gửi không được dùng làm quyền truy cập.
6. Khi hệ thống cần thu hồi tức thời, chống phát lại, chặn token bị đánh cắp hoặc phát hiện sử dụng bất thường, phải bổ sung cơ chế tương ứng. Lựa chọn manager không làm các việc đó.

### Ví dụ thêm audience validator cho JWT

`JwtDecoder` trong từng manager có thể có validator riêng. Đoạn ví dụ dưới đây yêu cầu cả issuer `idp-a` và audience `orders-api`:

```java
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

public JwtDecoder ordersDecoder() {
    String issuer = "https://idp-a.example.com/realms/customers";
    NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withIssuerLocation(issuer).build();

    OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
        boolean accepted = jwt.getAudience().contains("orders-api");
        if (accepted) {
            return OAuth2TokenValidatorResult.success();
        }
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", "Audience is not orders-api", null)
        );
    };

    decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuer),
        audienceValidator
    ));
    return decoder;
}
```

Đây là hàm tạo decoder minh họa để sử dụng trong cấu hình riêng của issuer; không thay thế `@Bean` resolver ở trên. Với Resource Server xử lý nhiều issuer, **mỗi issuer/manager** cần có validator thích hợp. Cần đối chiếu phiên bản Spring Security và kiểu token để cấu hình chính xác các kiểm tra `typ`, algorithm và các claims riêng của Authorization Server.

### Authentication khác authorization

Giả sử JWT đã được xác minh có:

```json
{
  "iss": "https://idp-a.example.com/realms/customers",
  "aud": ["orders-api"],
  "sub": "customer-42",
  "scope": "orders.read"
}
```

Mặc định, Resource Server có thể ánh xạ scope `orders.read` thành authority `SCOPE_orders.read`. Điều này giải thích rule:

```java
.requestMatchers("/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
```

Tuy nhiên, nếu người dùng mang `SCOPE_orders.read` truy cập `/api/orders/999` thuộc khách hàng khác, ứng dụng vẫn cần kiểm tra **quyền trên order 999**. Scope thường mô tả loại thao tác được phép, không mặc nhiên quyết định chủ sở hữu của mọi object.

## 8. Thiết kế tin cậy và các tình huống tấn công

### 8.1. Unknown issuer / giả mạo issuer

Kẻ tấn công phát hành JWT với:

```json
{
  "iss": "https://evil-idp.example",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
```

Nếu Resource Server tự lấy JWK từ `iss` mà không kiểm tra danh sách cho phép, bên tấn công có thể làm token “có chữ ký hợp lệ” theo khóa của chính họ. Resolver phải **fail closed** khi issuer không được tin cậy, dù token decode được.

### 8.2. Nhầm audience / token substitution

Một user hợp lệ có JWT do issuer A ký, nhưng `aud` là `profile-api`. Nếu manager A chỉ kiểm tra chữ ký và issuer mà bỏ qua audience, token có thể bị gửi nhầm hoặc cố ý dùng với `orders-api`. Đây là lý do phải kiểm tra `aud` theo Resource Server, độc lập với bước resolve manager.

### 8.3. Chọn tenant theo request header tự khai

```http
GET /api/orders/777 HTTP/1.1
Host: api.example.com
X-Tenant-Id: tenant-b
Authorization: Bearer <ACCESS_TOKEN_CUA_TENANT_A>
```

Header `X-Tenant-Id` chưa được xác thực có thể được thay bởi client. Nếu dùng nó để định tuyến manager, vẫn phải kiểm tra thông tin tenant đó **khớp với claims/subject/issuer đã xác thực** và chính sách truy cập tài nguyên. Không được cho phép truy cập dữ liệu B chỉ nhờ client gắn header B.

### 8.4. JWKS key rotation và outage

Khi Authorization Server thay khóa, decoder có thể cần làm mới JWK cache. Khi introspection endpoint mất kết nối, xác thực opaque token có thể thất bại. Các yêu cầu cần cân nhắc:

- timeout hợp lý, TLS và chính sách retry/backoff; tránh để request treo kéo dài;
- không “tạm cho qua” token khi issuer/JWK/introspection không kiểm tra được;
- giám sát lỗi theo issuer/tenant mà không log token nguyên vẹn;
- chính sách cache đi kèm yêu cầu thu hồi/độ tươi của token;
- giới hạn số issuer/decoder được đăng ký và quyền thay đổi registry.

### 8.5. JWT parser trước khi xác thực

`JwtIssuerAuthenticationManagerResolver` cần đọc claim `iss` để chọn manager, nên JWT có thể được **phân tích ở mức cấu trúc trước khi xác thực chữ ký**. Điều này chỉ phục vụ định tuyến; không được dùng những claims chưa xác thực để cấp quyền, chọn khóa từ URL tùy ý hoặc quyết định chủ sở hữu tài nguyên. Sau khi chọn manager, `JwtDecoder` phải xác thực lại token.

Theo tài liệu Spring Security, cách resolve theo claim rồi decode thường khiến JWT được parse hai lần. Có kỹ thuật tích hợp sâu với Nimbus `JWTClaimsSetAwareJWSKeySelector` để giảm lần parse, nhưng độ phức tạp lớn hơn và cần validator issuer/tenant riêng. Chỉ nên tối ưu sau khi đo đạc và vẫn giữ được allowlist, kiểm tra chữ ký và issuer.

## 9. 401, 403 và cách phân tích lỗi

| Tình huống | Kết quả điển hình | Cần kiểm tra |
| --- | --- | --- |
| Thiếu token khi gọi endpoint yêu cầu authentication | 401 | Client có gửi `Authorization: Bearer ...` không? |
| Token sai cú pháp hoặc chữ ký không hợp lệ | 401 | Định dạng token, JWK, algorithm, cấu hình decoder. |
| `iss` không thuộc danh sách được phép | 401 | Giá trị issuer chính xác, allowlist, cấu hình issuer trên token. |
| JWT hết hạn hoặc `aud` không hợp lệ | 401 | `exp`, đồng hồ server, audience validator. |
| Opaque token bị thu hồi, introspection `active=false` | 401 | Endpoint introspection và trạng thái token; tránh in token ra log. |
| Token hợp lệ nhưng thiếu scope | 403 | Mapping `SCOPE_*`, rule authorization và quyền của client. |
| Scope hợp lệ nhưng user không sở hữu tài nguyên | 403 hoặc 404 theo thiết kế API | Kiểm tra object-level authorization và quy tắc giấu tồn tại tài nguyên. |
| Issuer/JWKS/introspection tạm thời lỗi | Phụ thuộc loại lỗi và cách xử lý | Kiểm tra log an toàn, timeout, kết nối, metric và cấu hình fallback. |

Các status trên mô tả hành vi điển hình; chính xác còn tùy cấu hình `AuthenticationEntryPoint`, `AccessDeniedHandler` và xử lý lỗi ứng dụng. Không đổi lỗi mạng thành “token hợp lệ” và không tiết lộ thông tin nhạy cảm trong thông báo lỗi trả về client.

### Kiểm tra thủ công với token giả lập

```bash
# Không có token: endpoint cần xác thực thường trả 401
curl -i https://api.example.com/api/orders

# Token hợp lệ từ issuer được phép và có scope phù hợp
curl -i https://api.example.com/api/orders \
  -H "Authorization: Bearer ACCESS_TOKEN_VALID"

# Token từ issuer chưa được cấu hình: mong đợi từ chối
curl -i https://api.example.com/api/orders \
  -H "Authorization: Bearer ACCESS_TOKEN_UNKNOWN_ISSUER"

# Endpoint opaque token dùng chính sách /legacy/**
curl -i https://api.example.com/legacy/reports \
  -H "Authorization: Bearer OPAQUE_ACCESS_TOKEN_VALID"
```

Các chuỗi token trên là placeholder, **không phải token chạy được**. Trong kiểm thử tích hợp, cần token thử nghiệm do issuer kiểm thử phát hành hoặc mock bộ xác minh đúng cách; không đặt access token thật trong commit, log CI/CD hoặc ảnh chụp màn hình.

### Ma trận kiểm thử nên có

| Test case | Đường dẫn | Đặc điểm token | Kỳ vọng |
| --- | --- | --- | --- |
| JWT A hợp lệ | `/api/orders` | `iss=A`, `aud=orders-api`, có `orders.read` | Qua xác thực và được cấp quyền nếu đúng owner. |
| JWT B hợp lệ | `/api/orders` | `iss=B`, audience/scope đúng chính sách B | Được xử lý bởi manager B. |
| Issuer ngoài allowlist | `/api/orders` | `iss=attacker`, chữ ký tự tạo | Từ chối xác thực. |
| Audience sai | `/api/orders` | Được A ký nhưng `aud=other-api` | Từ chối xác thực. |
| Scope thiếu | `/api/orders` | Chữ ký/claims hợp lệ, chỉ có `orders.write` | Từ chối phân quyền đọc. |
| JWT hết hạn | `/api/orders` | `exp` đã qua | Từ chối xác thực. |
| Opaque token hợp lệ | `/legacy/reports` | `active=true`, scope đúng | Được xác thực qua introspection. |
| Opaque token bị thu hồi | `/legacy/reports` | `active=false` | Từ chối xác thực. |
| Token đúng nhưng sai tenant | `/api/orders/777` | Chủ thể tenant A đọc order tenant B | Từ chối cấp quyền đối tượng. |
| Issuer hoặc introspection endpoint lỗi | Tuyến liên quan | Không thể kiểm tra token | Không bỏ qua bước xác minh; phát hiện/ghi nhận lỗi phù hợp. |

## 10. Những lỗi thiết kế thường gặp

**Lỗi 1 — Tưởng resolver là nơi kiểm tra chữ ký.** Resolver chọn manager; decoder/provider mới xác minh token. Nếu manager có decoder yếu, resolver đúng vẫn không an toàn.

**Lỗi 2 — Đưa mọi URL trong `iss` vào discovery/JWKS.** Điều này phá ranh giới tin cậy và mở đường cho token giả mạo hoặc SSRF. Chỉ chấp nhận issuer đã đăng ký từ nguồn đáng tin cậy.

**Lỗi 3 — Xem `aud` là tùy chọn.** Token phát hành cho một API khác không được mặc nhiên chấp nhận. Cấu hình validator audience riêng cho từng nhóm Resource Server/tenant khi thích hợp.

**Lỗi 4 — Tin `X-Tenant-Id` hoặc JWT claims trước xác thực.** Các dữ liệu do client kiểm soát chỉ có thể dùng làm hint định tuyến dưới ràng buộc chặt; quyền tenant thực tế phải dựa trên thông tin đã xác thực và kiểm tra nghiệp vụ.

**Lỗi 5 — Đoán định dạng token rồi fallback giữa JWT và opaque.** Token “trông giống JWT” không phải bằng chứng đáng tin. Quy tắc chọn manager cần nhất quán với hợp đồng API và trust policy.

**Lỗi 6 — Coi `SCOPE_orders.read` là quyền đọc mọi order.** Scope là một phần authorization, cần kiểm tra thêm quyền đối với đối tượng theo tenant/principal.

**Lỗi 7 — Dùng refresh token hoặc OIDC ID token để gọi API.** Resource Server thường phải chấp nhận **access token** có audience/scope dành cho nó; các loại token khác có mục đích và vòng đời khác.

**Lỗi 8 — Tạo decoder, truy xuất metadata hoặc register issuer mới trên mỗi request.** Dễ tạo độ trễ, rủi ro SSRF và quá tải. Nên xây registry tin cậy, cache có kiểm soát và chiến lược refresh rõ ràng.

**Lỗi 9 — Xử lý lỗi “fail open”.** Khi token không xác minh được do network hoặc cấu hình, không được mặc định cho truy cập. Chọn cách trả lỗi có kiểm soát và giám sát nguyên nhân.

**Lỗi 10 — Quên kiểm thử toàn bộ đường đi thực.** Một số request có thể đi qua filter chain khác, proxy khác hoặc route bypass. Cần xác minh thực tế bằng integration test và quan sát response của từng endpoint.

## 11. Bài tập tình huống

### Tình huống A: hai issuer, cùng một endpoint

API `/api/orders` phục vụ khách hàng A và B. Cả hai Authorization Server phát JWT với `scope=orders.read`. Bạn thiết kế thế nào?

**Hướng giải:** Dùng allowlist cho hai issuer và `JwtIssuerAuthenticationManagerResolver`; mỗi issuer phải được xác minh chữ ký, `iss`, `aud`, expiry. Sau authentication, rule scope cho phép thao tác đọc nhưng service phải kiểm tra user A không đọc dữ liệu B.

### Tình huống B: JWT có chữ ký hợp lệ nhưng không được chấp nhận

Một JWT từ issuer A được ký đúng khóa của A, `exp` còn hiệu lực, có scope `orders.read`. Tuy nhiên `aud=["billing-api"]`. Tại sao Resource Server orders phải từ chối?

**Hướng giải:** Token được phát hành cho `billing-api`, không dành cho `orders-api`. Chỉ xác thực chữ ký và issuer là chưa đủ; `aud` chặn token substitution giữa các Resource Server.

### Tình huống C: onboard tenant động

Một admin muốn thêm tenant C trong khi ứng dụng chạy. Client C gửi request đầu tiên chứa `iss=https://new-idp.example`. Có nên tự tạo decoder từ `iss` không?

**Hướng giải:** Không. Admin phải được cấp quyền và xác minh issuer/metadata/JWK trước; đưa C vào registry tin cậy rồi mới cho resolver chọn manager. Token chưa xác thực không được phép quyết định mở kết nối đến issuer mới.

### Tình huống D: đối tác chuyển từ opaque sang JWT

`/legacy/**` đang dùng introspection. Đối tác thông báo sẽ chuyển dần sang JWT. Có thể viết `tryJwtOrOpaque`, thử JWT thất bại rồi gọi introspection không?

**Hướng giải:** Cần làm rõ lộ trình và **quy tắc phân loại có thể kiểm soát**, ví dụ tách đường dẫn hoặc một định danh issuer/client đã đăng ký; cấu hình manager tương ứng, kiểm tra audience/scope và loại bỏ dần đường cũ. Fallback không ràng buộc có thể dẫn đến nhầm trust boundary và khó kiểm soát lỗi.

## 12. Tổng kết và checklist áp dụng

1. **Phân định vai trò:** `BearerTokenResolver` đọc token; `AuthenticationManagerResolver` chọn bộ xác thực; provider/decoder/introspector xác minh; authorization quyết định quyền.
2. **Thiết lập ranh giới tin cậy:** allowlist issuer, cấu hình keys/algorithms và endpoints; không tự tin issuer hoặc claims chưa được xác thực.
3. **Xác thực đủ ngữ nghĩa:** chữ ký hoặc `active`, `iss`, `exp`, `nbf`, `aud`, scope và loại token phù hợp.
4. **Phân tách tenant:** định tuyến tenant và kiểm tra quyền đối với đối tượng là hai bước khác nhau.
5. **Bảo vệ vòng đời token:** không coi ID/refresh token là access token; thiết kế TTL, rotation/revocation, phát hiện token bị đánh cắp hoặc phát lại theo mức rủi ro.
6. **Vận hành và kiểm thử:** logging không chứa token, kiểm thử issuer giả/audience sai/scope thiếu, xử lý endpoint ngoài hệ thống bị lỗi và registry tenant động.

`AuthenticationManagerResolver` rất hữu ích khi **một Resource Server có nhiều chiến lược kiểm chứng access token**. Giá trị của nó nằm ở việc chọn đúng trust policy trước mỗi lần xác thực, trong khi quyết định token có thực sự hợp lệ và được phép làm gì vẫn do các lớp xác thực/phân quyền đảm nhiệm.

### Tài liệu tham khảo

- [Spring Security — OAuth 2.0 Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html): ví dụ `AuthenticationManagerResolver`, JWT/opaque, multi-issuer và quản lý tenant.
- [Spring Security API — JwtIssuerAuthenticationManagerResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerAuthenticationManagerResolver.html): constructor, `fromTrustedIssuers` và phương thức `resolve`.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT decoder, claims, validator và authority mapping.
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection, kiểm tra trạng thái token và scope.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html): cấu trúc và xác minh JWT access token theo OAuth 2.0.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html): giao thức introspection của access token.
