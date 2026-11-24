# OpaqueTokenAuthentication: xác thực opaque access token và ánh xạ authorities trong Spring Security

## 1. OpaqueTokenAuthentication là gì?

Một OAuth 2.0 **Resource Server** nhận access token để xác thực request và quyết định một client/người dùng có được truy cập API hay không. Với **opaque token**, chuỗi token không cho Resource Server đủ thông tin tin cậy để tự giải mã claims và kiểm tra quyền. Cách triển khai phổ biến là gọi **Token Introspection Endpoint** của Authorization Server theo RFC 7662, nhận trạng thái `active` cùng thuộc tính đã được server xác minh, rồi chuyển chúng thành `Authentication` và các `GrantedAuthority`.

Trong module **`SECURITY_TOKEN_SECURITY_FUNDAMENTALS`**, cơ chế này liên hệ trực tiếp với mô hình tin cậy và vòng đời token: **cấp access token → kiểm tra trạng thái/claims/scope/audience → phân quyền API → hết hạn/thu hồi → ngăn token bị đánh cắp hoặc phát lại**. Đây là cách Resource Server dùng quyết định của Authorization Server để bảo vệ tài nguyên.

**Lưu ý tên gọi:** `OpaqueTokenAuthentication` trong tiêu đề là tên **cơ chế xác thực**, không phải lớp kết quả `Authentication` mặc định trong Spring Security Servlet. Các lớp thực tế thường gặp là:

- `BearerTokenAuthenticationToken`: yêu cầu xác thực **chưa được kiểm chứng**, chứa bearer token.
- `OpaqueTokenAuthenticationProvider`: provider thực hiện xác thực bằng cách gọi `OpaqueTokenIntrospector`.
- `OpaqueTokenIntrospector`: interface kiểm tra access token thông qua introspection và trả `OAuth2AuthenticatedPrincipal`.
- `BearerTokenAuthentication`: kết quả `Authentication` **đã xác thực** thường được đặt trong `SecurityContext` của Servlet Resource Server.
- `GrantedAuthority`: quyền mà Spring Security đánh giá qua `hasAuthority`, `hasRole` và method security.

Không nên giả định có thể dùng `new OpaqueTokenAuthentication(...)` để lấy người dùng hiện tại. Bài tập trung vào Spring Security **Servlet** (Spring MVC, Spring Boot/Spring Security phiên bản tương thích); Reactive WebFlux có những lớp triển khai khác.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Vẽ lại luồng `Authorization: Bearer ...` đến introspection và `SecurityContext`.
2. Phân biệt access token, refresh token, JWT, opaque token, ID token và các đối tượng authentication trong Spring.
3. Cấu hình Resource Server sử dụng `OpaqueTokenIntrospector`.
4. Hiểu quy tắc ánh xạ `scope` → `SCOPE_*` và cách tùy biến authorities an toàn.
5. Kiểm tra `aud`, issuer/client, hạn token, thu hồi và object-level authorization.
6. Chẩn đoán lỗi 401/403 và kiểm thử introspection, scope, tenant, cache, replay.

## 2. Kiến trúc: từ Bearer token đến Authentication

Client gọi:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer 6f1d3c9e-opaque-demo-token
```

Resource Server không đọc được `sub`, `aud` hay `scope` chỉ từ chuỗi token. Nó dùng filter và provider:

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant F as BearerTokenAuthenticationFilter
    participant M as AuthenticationManager
    participant P as OpaqueTokenAuthenticationProvider
    participant I as OpaqueTokenIntrospector
    participant AS as Authorization Server
    participant A as Authorization
    C->>F: Authorization: Bearer opaque_token
    F->>F: BearerTokenResolver đọc token
    F->>M: authenticate(BearerTokenAuthenticationToken)
    M->>P: Chuyển yêu cầu tới provider
    P->>I: introspect(token)
    I->>AS: POST /introspect (token + client auth)
    AS-->>I: active, scope, sub, aud, exp...
    I-->>P: OAuth2AuthenticatedPrincipal
    P-->>M: BearerTokenAuthentication
    M-->>F: Authentication đã xác thực
    F->>F: Đưa vào SecurityContext
    F->>A: Kiểm tra GrantedAuthority và policy
    A-->>C: Cho phép hoặc từ chối truy cập
```

| Thành phần | Công việc | Khi nào dữ liệu được tin cậy? |
| --- | --- | --- |
| `BearerTokenResolver` | Đọc token, mặc định qua `Authorization` header. | Token vừa đọc **chưa đáng tin**. |
| `BearerTokenAuthenticationFilter` | Tạo request token, giao cho manager, lưu kết quả thành công. | Sau khi manager trả về authentication hợp lệ. |
| `ProviderManager` / `AuthenticationManager` | Điều phối provider xử lý loại authentication phù hợp. | Phụ thuộc kết quả provider. |
| `OpaqueTokenAuthenticationProvider` | Dùng introspector để xác nhận token và dựng đối tượng authentication. | Phải dựa vào introspector tin cậy. |
| `OpaqueTokenIntrospector` | Gọi AS hoặc thành phần kiểm chứng được ủy quyền và nhận principal. | Sau khi trạng thái token được xác minh. |
| `OAuth2AuthenticatedPrincipal` | Chứa attributes, principal name, authorities. | Thuộc tính từ AS đáng tin, vẫn cần kiểm tra policy bổ sung. |
| `BearerTokenAuthentication` | Đối tượng kết quả trong `SecurityContextHolder`. | Đại diện cho lần xác thực thành công. |
| `AuthorizationManager` / method security | Kiểm tra scope, role, rule endpoint hoặc quyền dữ liệu. | Chỉ trên dữ liệu đã xác thực. |

**Authentication khác authorization.** Token `active=true` chứng minh một trạng thái hợp lệ theo Authorization Server; nó chưa tự chứng minh chủ thể có quyền xem order 42. Spring Security có thể kiểm tra `SCOPE_orders.read`, còn service phải kiểm tra order thuộc đúng user/tenant.

## 3. Introspection Endpoint theo RFC 7662

### 3.1. Request

Authorization Server có thể phát access token:

```json
{
  "access_token": "opaque_example_value",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "orders.read orders.write"
}
```

Resource Server gọi introspection bằng POST qua HTTPS, thường xác thực riêng với AS:

```http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.com
Authorization: Basic <ENCODED_RESOURCE_SERVER_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded

token=opaque_example_value&token_type_hint=access_token
```

`token` là tham số bắt buộc; `token_type_hint` **chỉ là gợi ý**, không phải kiểm tra token type cuối cùng. Token và credential của Resource Server **không** được đưa vào frontend, log, URL query hoặc source repository.

### 3.2. Response còn hiệu lực

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "active": true,
  "scope": "orders.read orders.write",
  "client_id": "web-client",
  "sub": "user-42",
  "token_type": "Bearer",
  "iss": "https://auth.example.com",
  "aud": ["orders-api"],
  "exp": 1900000900,
  "iat": 1900000000
}
```

Đây là response giả lập. RFC 7662 không bắt buộc tất cả các trường trên đều hiện diện; AS có thể trả ít thuộc tính hơn. Nếu API yêu cầu `aud` hoặc `iss` để phân định trust domain, **thiếu claim phải có cách xử lý rõ**, không nên mặc định cho phép.

| Trường | Ý nghĩa | Điều Resource Server cần quan tâm |
| --- | --- | --- |
| `active` | Trạng thái token theo AS. | `false` nghĩa là không được xác thực. |
| `scope` | Danh sách scope thực tế được cấp. | Ánh xạ thành authorities theo chính sách. |
| `client_id` | Client được cấp token. | Ràng buộc loại client/luồng nghiệp vụ nếu cần. |
| `sub` | Chủ thể, có thể là user hoặc service. | Không tự suy ra đây luôn là người dùng cuối. |
| `aud` | Resource Server/API đích. | Ngăn token substitution sang API khác. |
| `iss` | Bên phát hành token. | Xác nhận trust domain đã được cấu hình. |
| `exp`, `iat`, `nbf` | Thông tin thời gian token. | Xác định TTL và chính sách thời gian. |

### 3.3. Response không còn hiệu lực

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"active": false}
```

HTTP 200 chỉ có nghĩa **request introspection được xử lý thành công**, không có nghĩa token hợp lệ. AS có thể trả `active=false` cho token không tồn tại, đã hết hạn, bị thu hồi, hoặc token bên yêu cầu không được phép xem chi tiết. Nếu client credential để gọi introspection sai, AS có thể trả HTTP 401 — đó là lỗi của **Resource Server đối với AS**, khác với 401 mà API trả về cho người gọi.

### 3.4. Ranh giới tin cậy

Để API `orders-api` tin vào kết quả introspection, cần:

1. Gọi **endpoint introspection được cấu hình sẵn** bằng HTTPS và thông tin xác thực đúng.
2. Chỉ chấp nhận token được AS xác nhận hoạt động và cho phép Resource Server này kiểm tra.
3. Kiểm tra `audience` hoặc cơ chế ràng buộc resource tương đương. Một `active=true` của token dành cho `billing-api` không đủ cho `orders-api`.
4. Chỉ ánh xạ role/scope từ phản hồi tin cậy, không lấy từ `X-Role`, query hoặc body do client tự gửi.
5. Kiểm tra quyền trên bản ghi/tenant ở tầng nghiệp vụ sau khi xác thực.

**Định dạng opaque không tự chống việc sao chép token**. Nếu token là bearer credential, ai nắm chuỗi token còn hợp lệ vẫn có thể phát lại, trừ khi có sender constraint được thực thi.

## 4. Scope, GrantedAuthority và role

### 4.1. Mapping mặc định

Spring Security Resource Server hỗ trợ introspection thường chuyển từng scope thành một `GrantedAuthority` với tiền tố **`SCOPE_`**:

```json
{
  "active": true,
  "scope": "orders.read orders.write"
}
```

Suy ra những authority phục vụ phân quyền:

```text
SCOPE_orders.read
SCOPE_orders.write
```

Các phiên bản Spring Security mới còn có thể thêm authority đánh dấu phương thức xác thực, ví dụ `FACTOR_BEARER`; không nên giả định collection chỉ có đúng hai phần tử. Đánh giá quyền phải so sánh authority cần thiết theo cấu hình.

### 4.2. Phân biệt scope và role

| Khái niệm | Ví dụ | Cách sử dụng |
| --- | --- | --- |
| Scope do OAuth AS cấp | `orders.read` | Trong introspection response. |
| Granted authority | `SCOPE_orders.read` | `hasAuthority("SCOPE_orders.read")`. |
| Role ở domain ứng dụng | `ADMIN` | Có thể map sang `ROLE_ADMIN` nếu policy cho phép. |
| Authority theo quy ước role | `ROLE_ADMIN` | `hasRole("ADMIN")` thường kiểm tra authority này. |
| Quyền theo đối tượng | Order 42 thuộc tenant A | Được kiểm tra ở service/domain layer. |

Không được tự động coi `scope=admin` tương đương `ROLE_ADMIN`. Nếu AS cung cấp claim `roles`, mapping sang `ROLE_*` phải được khai báo rõ và kiểm soát nguồn. Tên scope có dấu `.` hoặc `:` được so sánh theo tên authority; không tự thay đổi thành dấu khác.

### 4.3. Quy tắc endpoint và object-level authorization

```java
.requestMatchers("/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
```

Rule trên giới hạn loại thao tác API được gọi, **không xác định** user có quyền đối với mọi order. Ví dụ, user-42 được cấp `orders.read` nhưng không được xem order của tenant B. Tầng nghiệp vụ phải xác minh owner/tenant/resource ID sau authentication.

## 5. Cấu hình Spring Boot Resource Server

### 5.1. Dependency

Ví dụ Maven với Spring Boot:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
```

### 5.2. Cấu hình introspection

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: SECRET_FROM_SECURE_CONFIGURATION
```

`SECRET_FROM_SECURE_CONFIGURATION` là placeholder, không phải giá trị production. Ứng dụng thật cần lấy secret từ secret manager hoặc môi trường triển khai được bảo vệ, tránh hard-code vào tài liệu/repository. Đây là **introspection endpoint**, khác token endpoint phát access token.

Khi Spring Boot thấy dependency và cấu hình phù hợp, nó có thể tự tạo `OpaqueTokenIntrospector` và tích hợp với filter chain. Tuy nhiên, vẫn cần khai báo quyền của các tuyến API.

### 5.3. SecurityFilterChain và authorities

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {
    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers("/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers("/api/reports/**")
                    .hasAuthority("SCOPE_reports.read")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(Customizer.withDefaults())
            );
        return http.build();
    }
}
```

Ý nghĩa:

- `opaqueToken(...)` kích hoạt đường xác thực bearer token qua introspection.
- `hasAuthority(...)` so sánh đúng authority được sinh từ scope.
- `anyRequest().denyAll()` chặn tuyến mới chưa được phân quyền.
- `permitAll()` không buộc có token cho `/public/**`, nhưng nếu gửi một bearer token không hợp lệ, filter vẫn có thể thử xác thực và từ chối theo cấu hình.

Ví dụ minh họa cơ chế, chưa thay thế thiết kế đầy đủ cho HTTP method, CSRF khi có session cookie, CORS, exception handling và quyền truy cập từng bản ghi. Không mặc định tắt CSRF cho mọi website chỉ vì API có bearer token.

### 5.4. Đọc principal sau xác thực

Spring Security Servlet thường lưu `BearerTokenAuthentication` trong `SecurityContext`. Controller có thể lấy tên và authority:

```java
import java.util.Map;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class WhoAmIController {
    @GetMapping("/api/whoami")
    Map<String, Object> whoAmI(BearerTokenAuthentication auth) {
        return Map.of(
            "name", auth.getName(),
            "authorities", auth.getAuthorities().stream()
                    .map(a -> a.getAuthority()).toList()
        );
    }
}
```

Đây chỉ là endpoint học tập. Không đưa raw access token, credential, thông tin định danh nhạy cảm hoặc toàn bộ claims vào response công khai.

Hoặc truy cập `OAuth2AuthenticatedPrincipal`:

```java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping("/api/profile/subject")
String subject(@AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
    String sub = principal.getAttribute("sub");
    return sub != null ? sub : principal.getName();
}
```

Đoạn code thứ hai là **phương thức ví dụ** phải đặt trong controller với cấu hình route phù hợp. `getName()` có thể lấy từ `sub` tùy response; với client credentials, principal có thể đại diện cho service thay vì user. Cần xác minh tenant/owner độc lập.

### 5.5. Method security

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
```

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
class OrderQueryService {
    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public String getOrder(String id) {
        // Trong ứng dụng thật, kiểm tra thêm quyền trên order này.
        return "order:" + id;
    }
}
```

Trong Spring AOP proxy mode, self-invocation bằng `this.getOrder(...)` có thể không đi qua proxy áp dụng method security. Cần tổ chức lời gọi bean phù hợp để rule thực sự chạy.

## 6. Tùy biến authorities bằng OpaqueTokenIntrospector

### 6.1. Bài toán

Giả sử introspection trả:

```json
{
  "active": true,
  "sub": "user-42",
  "iss": "https://auth.example.com",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "roles": ["orders_auditor"]
}
```

Ứng dụng muốn giữ `SCOPE_orders.read`, từ chối token sai audience và bổ sung `ROLE_ORDERS_AUDITOR` khi claim roles từ **Authorization Server tin cậy** thực sự chứa `orders_auditor`.

### 6.2. Ví dụ Java

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringOpaqueTokenIntrospector;

@Configuration
public class OpaqueAuthoritiesConfig {
    @Bean
    OpaqueTokenIntrospector customIntrospector(
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.introspection-uri}")
            String uri,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-id}")
            String clientId,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-secret}")
            String clientSecret) {

        OpaqueTokenIntrospector delegate = SpringOpaqueTokenIntrospector
                .withIntrospectionUri(uri)
                .clientId(clientId)
                .clientSecret(clientSecret)
                .build();

        return token -> {
            OAuth2AuthenticatedPrincipal principal = delegate.introspect(token);

            Object aud = principal.getAttribute("aud");
            boolean accepted = "orders-api".equals(aud)
                    || (aud instanceof Collection<?> values
                            && values.contains("orders-api"));
            if (!accepted) {
                throw new BadOpaqueTokenException("Invalid audience");
            }

            List<GrantedAuthority> authorities =
                    new ArrayList<>(principal.getAuthorities());
            Object roles = principal.getAttribute("roles");
            if (roles instanceof Collection<?> values
                    && values.contains("orders_auditor")) {
                authorities.add(
                        new SimpleGrantedAuthority("ROLE_ORDERS_AUDITOR"));
            }

            return new DefaultOAuth2AuthenticatedPrincipal(
                    principal.getName(),
                    principal.getAttributes(),
                    authorities
            );
        };
    }
}
```

Ba tham số `@Value(...)` lấy giá trị từ cấu hình `application.yml` ở phần 5.2; khi triển khai, secret cần được quản lý qua môi trường hoặc secret manager. Có thể thay `@Value` bằng `@ConfigurationProperties` nếu muốn gom cấu hình thành một đối tượng typed. Không hard-code client secret trong mã Java.

**Giải thích:**

1. `delegate.introspect(token)` phải hoàn tất xác thực qua AS trước khi dùng claims làm policy.
2. `aud` được kiểm tra theo dạng chuỗi hoặc tập hợp. Nếu không có `aud`, ví dụ cố ý **fail closed**; phải thống nhất hợp đồng introspection với AS để áp dụng chính sách mong muốn.
3. Giữ authority mặc định từ scope, chỉ bổ sung một role được **allowlist**.
4. `getAttributes()` được giữ nguyên; principal mới mang authority đã cập nhật.
5. Nếu có nhiều tenant/issuer, cần ràng buộc thêm nguồn issuer và chính sách từng API, không map roles chung cho nguồn token tùy ý.

Đăng ký `OpaqueTokenIntrospector` bean thường thay cơ chế auto-config mặc định khi không có cấu hình DSL explicit ưu tiên khác. Kiểm tra cấu hình cuối cùng vì nhiều bean/filter chain có thể khiến ứng dụng dùng introspector không như mong đợi.

### 6.3. Dùng role đã ánh xạ

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/audit/**").hasRole("ORDERS_AUDITOR")
    .requestMatchers("/api/orders/**").hasAuthority("SCOPE_orders.read")
    .anyRequest().denyAll()
);
```

Đây là trích đoạn DSL đặt bên trong `SecurityFilterChain` đang bật OAuth2 opaque token. `hasRole("ORDERS_AUDITOR")` theo convention mặc định yêu cầu authority `ROLE_ORDERS_AUDITOR`. Nếu dự án đã đổi role prefix, cần dùng giá trị tương ứng.

### 6.4. Khi dữ liệu scope/roles khác chuẩn

`scope` theo RFC 7662 thường là một chuỗi phân tách bởi dấu cách. Một số AS có thể trả thêm claim đặc thù như `scp` hoặc danh sách roles. Không giả định kiểu dữ liệu tùy ý; hãy viết adapter đúng hợp đồng API và fail closed khi thiếu dữ liệu bắt buộc. Không map mọi tên role không qua kiểm soát thành `ROLE_*`.

## 7. JWT và opaque token khác nhau ở đâu?

| Khía cạnh | JWT access token xác thực cục bộ | Access token được introspect |
| --- | --- | --- |
| Cách kiểm tra | `JwtDecoder` xác minh chữ ký, thuật toán, issuer, audience và thời gian. | `OpaqueTokenIntrospector` gọi AS để lấy `active` và attributes. |
| Phụ thuộc mạng | Thường không cần mỗi request khi JWK đã cache. | Thường có network call mỗi request, trừ cache có kiểm soát. |
| Thu hồi | Cần cơ chế denylist/check bổ sung hoặc chờ hết hạn nếu chỉ validate offline. | Có thể phản ánh `active=false` ở request sau, tùy replication/cache. |
| Principal Spring Servlet | Thường là `Jwt` trong `JwtAuthenticationToken`. | Thường là `OAuth2AuthenticatedPrincipal` trong `BearerTokenAuthentication`. |
| Mapping authority | `JwtGrantedAuthoritiesConverter` hoặc converter tùy chỉnh. | Scope/attributes từ introspection qua introspector. |

**Có thể introspect JWT** nếu AS hỗ trợ: tên tính năng “opaque token” trong Spring chủ yếu mô tả **cách xác thực bằng introspection**, không bắt buộc token luôn là chuỗi không có cấu trúc. Trường hợp đó vẫn phải kiểm tra audience/scope/issuer theo chính sách AS và Resource Server.

### Phân biệt access token, refresh token, ID token

| Credential | Mục đích đúng |
| --- | --- |
| Access token (JWT hoặc opaque) | Gửi Resource Server đúng audience để truy cập API. |
| Refresh token | Gửi token endpoint của Authorization Server để xin access token mới. |
| ID token OIDC | OIDC client dùng để xác minh sự kiện đăng nhập, không thay access token. |
| Authorization code | Credential một lần để client đổi token theo authorization code flow và PKCE. |

Một refresh token có thể còn active trong hệ thống AS nhưng **không được dùng làm access token** ở API nghiệp vụ. AS/introspection policy và Resource Server phải ràng buộc loại token và audience đúng mục đích. `token_type_hint=access_token` đơn thuần không phải kiểm soát bảo mật đủ mạnh.

## 8. Thu hồi, cache và chống token replay

### 8.1. Khi access token bị thu hồi

```mermaid
flowchart TD
    A["Nhận bearer token"] --> B["Gọi introspection"]
    B --> C{"active=true?"}
    C -->|Không| D["Từ chối xác thực"]
    C -->|Có| E{"Đúng audience, issuer, token type?"}
    E -->|Không| D
    E -->|Có| F["Tạo principal và GrantedAuthority"]
    F --> G{"Đủ scope/role và quyền trên object?"}
    G -->|Không| H["Từ chối phân quyền"]
    G -->|Có| I["Cho phép API"]
```

Introspection có thể giúp phản ánh việc thu hồi token sớm hơn chờ access token hết hạn, **nếu AS trả trạng thái mới và Resource Server không dùng cache cũ**. Khả năng thu hồi thực tế còn tùy backend AS, độ trễ đồng bộ và TTL cache.

### 8.2. Cache và trade-off

| Cách làm | Ưu điểm | Rủi ro |
| --- | --- | --- |
| Không cache introspection | Lấy trạng thái gần hiện tại nhất từ AS cho mỗi request. | Network latency, số request cao và phụ thuộc AS. |
| Cache ngắn | Giảm tải, latency thấp hơn. | Thu hồi có thể chậm trong cửa sổ TTL. |
| Cache dài | Tăng hiệu suất. | Cửa sổ chấp nhận token đã revoke hoặc quyền đã đổi lớn hơn. |
| JWT local verification | Ít gọi AS ở mỗi request. | Cần cơ chế thu hồi bổ sung hoặc TTL ngắn. |

Nếu cache, TTL không được vượt quá thời gian còn lại của token khi có `exp`, cũng không vượt chính sách thu hồi tối đa. Không cache raw token ở log hoặc cơ chế dễ bị lộ; key cache cũng là dữ liệu nhạy cảm cần bảo vệ.

### 8.3. Khi introspection endpoint bị lỗi

AS có thể timeout, trả 5xx, lỗi TLS hoặc đổi credential. Không được **fail open** bằng cách cho phép mọi token khi không xác minh được. Cần giới hạn thời gian chờ, theo dõi latency và lỗi, kiểm soát retry/circuit breaker, đồng thời trả lỗi an toàn theo cấu hình Spring Security.

Chẩn đoán nên ghi `requestId`, loại lỗi, client ID đã định danh, latency và endpoint; **không ghi** bearer token, refresh token, client secret hoặc toàn bộ Authorization header.

### 8.4. Token bị đánh cắp/phát lại

Opaque token vẫn có thể là bearer credential: kẻ tấn công có chuỗi token có thể phát lại tới khi hết hạn/thu hồi. Các lớp bảo vệ cần phối hợp:

- Access token TTL ngắn, scope nhỏ, audience hẹp và kiểm tra quyền object.
- Bảo vệ lưu trữ access/refresh token; dùng HTTPS và chặn token trong URL/query, logs hoặc analytics.
- Refresh-token rotation hoặc sender constraint theo chính sách, phát hiện reuse khi có thiết kế.
- Giám sát truy cập bất thường, hỗ trợ thu hồi và chính sách rate limit.
- mTLS/DPoP khi hệ sinh thái hỗ trợ; Resource Server phải kiểm chứng **binding/proof**, không chỉ dựa vào `active=true`.

Không phải mọi access token được introspect đều mặc nhiên chống replay. Bảo mật token phụ thuộc cấu hình xuyên suốt AS, client và Resource Server.

## 9. Chẩn đoán 401, 403 và lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| 401 khi thiếu bearer | Endpoint cần authentication. | Kiểm tra client gửi header và rule filter chain. |
| 401 cho token đã thu hồi | Introspection `active=false`. | Kiểm tra trạng thái AS, không tiết lộ raw token. |
| 401 dù token “mới cấp” | Sai audience, introspection credential, token type hoặc endpoint. | Tách lỗi xác thực AS và policy Resource Server. |
| 403 với `active=true` | Thiếu authority như `SCOPE_orders.read`. | Xem scopes trả về, cách map authorities và route rule. |
| 403 dù có scope đúng | Object-level/tenant policy từ chối. | Kiểm tra chủ sở hữu tài nguyên. |
| `hasRole("ADMIN")` luôn fail | Chỉ có `SCOPE_admin`, không có `ROLE_ADMIN`. | Mapping riêng từ claim tin cậy hoặc chỉnh rule theo authority đúng. |
| API tăng latency | Introspection mỗi request, AS chậm, connection pool. | Đo SLA, timeout, cache theo độ trễ revoke chấp nhận được. |
| Một số node chấp nhận token đã revoke | Cache/replication chưa đồng bộ. | Theo dõi độ trễ nhất quán và TTL. |

Những kết quả 401/403 là **điển hình**; mã HTTP cụ thể còn phụ thuộc `AuthenticationEntryPoint`, `AccessDeniedHandler` và ngoại lệ. Không biến lỗi mạng thành authentication thành công để “khắc phục” outage.

### Những sai lầm cần tránh

1. **Nhầm cơ chế `OpaqueTokenAuthentication` với một class kết quả.** Trong Servlet, đối tượng kết quả thường là `BearerTokenAuthentication`.
2. **Cho rằng introspection HTTP 200 là đủ.** Phải xác nhận `active=true` và policy phù hợp.
3. **Dùng `active=true` như quyền truy cập toàn cục.** Audience, scope, issuer/client, token type và quyền đối tượng đều có vai trò.
4. **Nhầm scope với role.** `orders.read` thường thành `SCOPE_orders.read`, không tự thành `ROLE_ADMIN`.
5. **Map role từ input chưa xác thực.** Chỉ tin claims do nguồn introspection được phép trả về.
6. **Cho rằng opaque token không thể bị đánh cắp.** Bearer token bị sao chép vẫn có thể bị dùng lại.
7. **Cache introspection vô hạn.** Token đã thu hồi có thể tiếp tục được chấp nhận.
8. **Bỏ qua object-level authorization.** Endpoint có scope đúng không đủ để xem tài nguyên của người khác.

## 10. Kiểm thử thực hành

### 10.1. Gửi token thử nghiệm tới Resource Server

```bash
# Không gửi token: endpoint yêu cầu xác thực thường trả 401
curl -i https://api.example.com/api/orders/42

# Chỉ dùng access token thử nghiệm do Authorization Server test cấp
curl -i https://api.example.com/api/orders/42 \
  -H "Authorization: Bearer OPAQUE_TEST_ACCESS_TOKEN"
```

`OPAQUE_TEST_ACCESS_TOKEN` chỉ là placeholder, không phải credential thật. Tránh để access token/secret trong terminal history và log.

### 10.2. Gọi introspection bằng tài khoản Resource Server test

```bash
curl -i https://auth.example.com/oauth2/introspect \
  -u "orders-resource-server:TEST_SECRET_ONLY" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "token=OPAQUE_TEST_ACCESS_TOKEN" \
  --data-urlencode "token_type_hint=access_token"
```

Chỉ chạy với môi trường và credential thử nghiệm được cấp phép. Xác minh `active=true` khi token hợp lệ, `active=false` sau revoke, audience/scope đúng và không log response/token. Credential introspection phải nằm ở backend, không đưa vào frontend.

### 10.3. MockMvc `opaqueToken()`

Spring Security Test cung cấp `opaqueToken()` để dựng authentication giả, phù hợp kiểm thử **authorization** mà không cần gọi introspection thật:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.opaqueToken;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrdersSecurityTest {
    @Autowired MockMvc mvc;

    @Test
    void scopeReadIsAllowed() throws Exception {
        mvc.perform(get("/api/orders/42").with(opaqueToken()
                .authorities(new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isOk());
    }

    @Test
    void missingScopeIsForbidden() throws Exception {
        mvc.perform(get("/api/orders/42").with(opaqueToken()
                .authorities(new SimpleGrantedAuthority("SCOPE_profile.read"))))
            .andExpect(status().isForbidden());
    }
}
```

Đoạn test giả định endpoint `GET /api/orders/42` tồn tại, trả 200 khi user có quyền và không bị owner/tenant rule từ chối. Dự án thực cần fixture phù hợp. Test này **không kiểm chứng** request introspection hoặc việc thu hồi thật; cần integration test với fake/stub introspection server để kiểm tra `active=false`, audience sai, timeout, secret sai và response lỗi.

### 10.4. Ma trận kiểm thử

| Trường hợp | Response/thuộc tính | Kỳ vọng |
| --- | --- | --- |
| Token hợp lệ | `active=true`, `aud=orders-api`, `orders.read` | Qua authentication, được quyền khi object policy cho phép. |
| Token không tồn tại hoặc đã revoke | `active=false` | Từ chối authentication. |
| Token dành cho API khác | `active=true`, `aud=billing-api` | Từ chối theo audience policy. |
| Scope thiếu | `active=true` nhưng không có `orders.read` | Thường 403 ở tuyến đọc. |
| Scope đủ, owner sai | `orders.read` nhưng dữ liệu của tenant khác | Từ chối ở service/method security. |
| Role hợp lệ | `roles=["orders_auditor"]` từ AS tin cậy | Có `ROLE_ORDERS_AUDITOR` khi map đúng. |
| Header role giả | `X-Role: admin` từ client | Không cấp role nếu introspection không xác nhận. |
| Refresh token dùng như access token | Token sai type/audience/AS policy | Bị từ chối. |
| AS introspection timeout | Không có kết quả xác minh | Không cho request đi qua. |
| Token vừa revoke nhưng còn trong cache | Cache chứa `active=true` cũ | Kiểm tra cửa sổ stale và TTL theo SLA. |

## 11. Tình huống vận dụng

### Tình huống A: token còn hiệu lực nhưng thiếu quyền

Introspection trả `{"active":true,"scope":"orders.write"}`. Endpoint `GET /api/orders` yêu cầu `hasAuthority("SCOPE_orders.read")`.

**Phân tích:** Xác thực có thể thành công, nhưng authorization không có scope đọc. Thường trả 403. Không tự nâng quyền từ `orders.write` lên `orders.read` nếu policy không cho phép.

### Tình huống B: JWT introspection

Một access token có ba phần như JWT, nhưng API dùng `opaqueToken()` và introspection trả `active=true`. Đây có phải cấu hình sai?

**Phân tích:** Chưa chắc. Spring có thể introspect JWT khi AS hỗ trợ. “Opaque” ở đây mô tả chiến lược introspection. Resource Server vẫn phải kiểm tra audience, issuer/client và scope phù hợp.

### Tình huống C: role lấy từ header

Frontend gửi `X-Role: ADMIN` cùng access token chỉ có scope `orders.read`. Developer muốn map header thành `ROLE_ADMIN`.

**Phân tích:** Không được. Header do client kiểm soát không phải bằng chứng phân quyền. Chỉ map từ claims/phân quyền do AS hoặc nguồn nghiệp vụ đã xác minh cung cấp và phải áp dụng allowlist.

### Tình huống D: thu hồi token nhưng API còn chấp nhận

AS thu hồi token lúc 10:00; Resource Server cache kết quả introspection `active=true` đến 10:05.

**Phân tích:** Cache tạo cửa sổ chấp nhận token đã revoke tối đa theo TTL/cơ chế đồng bộ. Nếu yêu cầu thu hồi trong dưới một phút, cache 5 phút không phù hợp; cần điều chỉnh thiết kế.

### Tình huống E: không thể gọi introspection

Endpoint introspection bị lỗi 503; nhóm vận hành đề xuất cho request dùng “token nhìn có vẻ hợp lệ” tiếp tục đi qua.

**Phân tích:** Không được fail open. Cần xử lý outage có kiểm soát, cấu hình timeout, giám sát, cache ngắn theo chính sách được duyệt trước hoặc kiến trúc kiểm chứng thay thế đáng tin cậy.

## 12. Checklist ghi nhớ

1. `OpaqueTokenAuthentication` là **cơ chế introspection**, còn `BearerTokenAuthentication` là kết quả authentication thường gặp trong Spring Security Servlet.
2. `OpaqueTokenAuthenticationProvider` dùng `OpaqueTokenIntrospector`, trả principal có attributes và authorities từ nguồn tin cậy.
3. `active=false` nghĩa là token không hợp lệ, dù introspection HTTP trả 200.
4. Scope thường thành `SCOPE_<scope>`; role phải được map rõ ràng nếu muốn dùng `hasRole(...)`.
5. `active=true` chưa đủ: kiểm tra audience/issuer/client/token type, scope và quyền đối với từng tài nguyên.
6. Opaque token có thể bị thu hồi qua AS nhanh hơn JWT chỉ xác minh offline, nhưng kết quả phụ thuộc cache và trạng thái đồng bộ.
7. Opaque bearer token vẫn có thể bị sao chép/replay. Bảo vệ TTL, scope, audience, lưu trữ, thu hồi và sender constraint khi cần.
8. Test riêng introspection và phân quyền: `opaqueToken()` trong MockMvc giúp test rule, còn integration test mới kiểm tra liên kết thật với AS.

### Tài liệu tham khảo

- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): cấu hình, provider, introspection, scope và authorities.
- [Spring Security API — BearerTokenAuthentication](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/BearerTokenAuthentication.html): kết quả authentication từ bearer token.
- [Spring Security API — DefaultOAuth2AuthenticatedPrincipal](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/DefaultOAuth2AuthenticatedPrincipal.html): principal attributes và authorities.
- [Spring Security — Testing OAuth 2.0](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): MockMvc `opaqueToken()`.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html): định dạng request, `active` response và bảo vệ endpoint.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): truyền bearer token, lỗi và yêu cầu bảo vệ.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009.html): thu hồi token.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): vòng đời token, ngăn đánh cắp và phát lại.
