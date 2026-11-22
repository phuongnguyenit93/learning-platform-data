# `Jwt`, `JwtAuthenticationToken` và dữ liệu danh tính sau xác thực

Trong một **Spring Security OAuth 2.0 Resource Server**, access token do client gửi đến qua HTTP **không tự động trở thành danh tính đáng tin**. Với JWT Bearer token, Spring Security cần xác minh token theo issuer, chữ ký, thời gian và các chính sách của API trước khi ứng dụng sử dụng claim để xác định ai đang gọi, quyền nào được cấp và dữ liệu nào có thể truy cập.

Hai kiểu rất dễ bị nhầm là:

- **`Jwt`** (`org.springframework.security.oauth2.jwt.Jwt`): biểu diễn JWT đã được `JwtDecoder` giải mã và chấp nhận theo các validator được cấu hình. Nó cung cấp token value, headers, claims và các method truy cập claim như `getSubject()`, `getIssuer()`, `getAudience()`.
- **`JwtAuthenticationToken`** (`org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken`): biểu diễn kết quả **Spring Security `Authentication`** dựa trên JWT đã xác thực, gắn JWT với tên principal, các `GrantedAuthority` và trạng thái authentication trong `SecurityContext`.

Sự phân biệt có thể hình dung như sau:

```text
HTTP Authorization: Bearer <raw-token>
             |
             | Chưa xác thực, không tin payload
             v
BearerTokenAuthenticationFilter
             |
             v
JwtAuthenticationProvider + JwtDecoder
             |
             | Xác minh chữ ký, iss, exp/nbf, aud theo policy
             v
           Jwt
             |
             | Ánh xạ principal name + GrantedAuthority
             v
   JwtAuthenticationToken
             |
             v
   SecurityContext của request
             |
             v
Controller / Service / Authorization
```

**`Jwt` chứa dữ liệu token được decoder chấp nhận; `JwtAuthenticationToken` là ngữ cảnh xác thực mà Spring Security sử dụng cho request.** Cả hai đều không có nghĩa một người dùng được phép làm mọi thao tác chỉ vì JWT hợp lệ.

Nội dung sử dụng cú pháp Spring Boot 3 / Spring Security 6 ở Servlet stack. Các cấu hình tùy biến có thể làm thay đổi tên principal, loại principal hoặc authorities, do đó phải đọc đúng cấu hình ứng dụng thực tế.

## 1. Các lớp khái niệm: credential, JWT đã xác minh, principal, authorization

Một request có thể chứa:

```http
GET /api/orders/42 HTTP/1.1
Host: orders.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

Ở thời điểm filter vừa đọc header, chuỗi Bearer là **credential đầu vào**, có thể hợp lệ, giả mạo, hết hạn hoặc không dành cho API này. Không được tự lấy payload bằng Base64URL rồi cho rằng `sub` là người dùng được xác thực.

| Khái niệm | Trách nhiệm | Trong Spring Security JWT Resource Server |
| --- | --- | --- |
| **Bearer credential** | Dữ liệu client xuất trình để được xác thực. | Chuỗi từ `Authorization` và `BearerTokenAuthenticationToken` dùng cho authentication request. |
| **JWT đã được xác minh** | Kết quả decode, xác minh chữ ký và các token validator. | Đối tượng `Jwt` do `JwtDecoder.decode(...)` trả về thành công. |
| **`Authentication` đã xác thực** | Ngữ cảnh bảo mật của caller với principal và authorities. | Thường là `JwtAuthenticationToken`. |
| **Principal** | Biểu diễn chủ thể sau xác thực. | Thường là `Jwt` trong JWT Resource Server; tên principal thường dựa trên `sub`. |
| **Authorization** | Kiểm tra caller có được thực hiện hành động cụ thể không. | `hasAuthority`, `hasRole`, method security và chính sách owner/tenant. |

Từ **“authentication”** đôi khi gây nhầm vì giao diện `Authentication` trong Spring Security có thể biểu diễn **cả yêu cầu xác thực chưa thành công lẫn kết quả xác thực**. Ví dụ `BearerTokenAuthenticationToken` chỉ gói credential cần xử lý, không có cùng ý nghĩa tin cậy với `JwtAuthenticationToken` do provider trả về sau khi kiểm tra token.

Trong ứng dụng bình thường, hãy để Security filter chain và authentication provider thực hiện toàn bộ quá trình. Không tạo một `Authentication` với cờ `authenticated = true` từ một header do client tự khai.

## 2. Bên trong một JWT: headers và claims là gì?

JWT compact thường có ba phần:

```text
Base64URL(header).Base64URL(payload).Base64URL(signature)
```

Ví dụ JWT header:

```json
{
  "alg": "RS256",
  "kid": "shop-key-2026-02",
  "typ": "at+jwt"
}
```

Ví dụ payload:

```json
{
  "iss": "https://identity.example.com/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "iat": 1890000000,
  "nbf": 1890000000,
  "exp": 1900000000,
  "client_id": "web-frontend",
  "scope": "orders.read profile.read",
  "tenant_id": "tenant-a",
  "email": "user@example.com"
}
```

Các đoạn JSON chỉ nhằm minh họa, **không phải JWT đã ký**.

**Header** chứa thông tin về kiểu token, thuật toán và key identifier; **payload** chứa claims. Chúng có thể được đọc từ chuỗi JWT vì Base64URL không phải cơ chế mã hóa. Một người có thể tự tạo payload bất kỳ với `sub = admin` hoặc `scope = orders.write`, nhưng Resource Server không được tin dữ liệu đó khi chữ ký và validator chưa hợp lệ.

Với access token JWT:

- `iss` cho biết bên phát hành token.
- `sub` là subject theo hợp đồng issuer/token profile; nó không mặc định lúc nào cũng là End-User.
- `aud` xác định đối tượng được cấp quyền nhận token; API phải kiểm tra token dành cho chính nó.
- `exp` và `nbf` ràng buộc thời gian sử dụng.
- `scope` hoặc `scp` có thể được Spring Security ánh xạ thành authorities.
- `client_id`, `tenant_id`, `email` là các thuộc tính chỉ nên diễn giải theo hợp đồng issuer và chính sách ứng dụng.

**Đọc được claim không đồng nghĩa có quyền sử dụng claim làm bằng chứng bảo mật.** Ranh giới tin cậy được thiết lập bởi quá trình JWT validation, không bởi thao tác parse JSON.

## 3. Spring Security tạo `Jwt` ở đâu?

Luồng phổ biến:

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant F as BearerTokenAuthenticationFilter
    participant M as AuthenticationManager
    participant P as JwtAuthenticationProvider
    participant D as JwtDecoder
    participant S as SecurityContext
    participant A as API

    C->>F: Authorization: Bearer JWT
    F->>M: BearerTokenAuthenticationToken
    M->>P: authenticate(...)
    P->>D: decode(rawJwt)
    alt JWT không hợp lệ
        D-->>P: JwtException
        P-->>F: AuthenticationException
        F-->>C: Authentication failure (thường 401)
    else JWT hợp lệ
        D-->>P: Jwt đã xác minh
        P->>P: Chuyển Jwt thành principal + authorities
        P-->>M: JwtAuthenticationToken
        M-->>F: Authentication thành công
        F->>S: Lưu Authentication cho request
        S->>A: Principal và authorities
        A->>A: Phân quyền chức năng và tài nguyên
        A-->>C: 2xx hoặc 403/404 theo chính sách
    end
```

Trong trường hợp JWT, `JwtAuthenticationProvider` sử dụng `JwtDecoder` và một bộ chuyển đổi JWT thành `AbstractAuthenticationToken` (mặc định thường là `JwtAuthenticationConverter`). Spring Security chỉ đưa kết quả authentication vào `SecurityContext` sau khi provider chấp nhận token.

Không phải mọi `JwtDecoder` đều giống nhau. Một decoder có thể:

1. Xác minh chữ ký bằng JWK Set từ issuer đáng tin.
2. Kiểm tra `iss`, `exp`, `nbf` và các JWT validator tiêu chuẩn.
3. Kiểm tra `aud = orders-api` nếu ứng dụng cấu hình audience validation.
4. Kiểm tra token type/profile hoặc claim bắt buộc khác theo hợp đồng.

Lưu ý: chỉ cấu hình `issuer-uri` **không nên được coi là bảo đảm** đã có mọi ràng buộc audience của API. Khi issuer cấp token cho nhiều protected resources, cần xác minh `aud` rõ ràng qua property hoặc validator hỗ trợ ở phiên bản đang dùng.

## 4. Cấu trúc `Jwt`: cách đọc dữ liệu sau xác thực

Một `Jwt` có thể cung cấp:

```java
Jwt jwt = ...; // Do Spring Security cung cấp sau xác thực

String subject = jwt.getSubject();
String issuer = jwt.getIssuer().toString();
Collection<String> audience = jwt.getAudience();
Instant expiresAt = jwt.getExpiresAt();
String tenantId = jwt.getClaimAsString("tenant_id");
List<String> roles = jwt.getClaimAsStringList("roles");
Map<String, Object> claims = jwt.getClaims();
Map<String, Object> headers = jwt.getHeaders();
```

Ví dụ minh họa giả định các import `Jwt`, `Instant`, `Collection`, `List`, `Map` đã có và issuer hiện diện do token profile yêu cầu. Nếu một claim là optional, phải kiểm tra trường hợp nó **không tồn tại**; không gọi `.toString()` trên một giá trị null.

Các nhóm thông tin trong `Jwt`:

| Phương thức | Kết quả | Cách dùng |
| --- | --- | --- |
| `getSubject()` | Claim `sub` dạng chuỗi nếu có. | Định danh subject trong ngữ cảnh issuer, không tự suy ra user/ứng dụng. |
| `getIssuer()` | URI từ claim `iss`. | Gắn nguồn phát hành vào định danh và policy đa issuer. |
| `getAudience()` | Danh sách các audience trong `aud`. | Tìm hiểu đối tượng nhận; validation nên nằm ở decoder. |
| `getIssuedAt()`, `getExpiresAt()` | Thời điểm phát hành/hết hạn khi có. | Chẩn đoán và policy cần thiết; thời hạn phải được validator kiểm tra. |
| `getClaimAsString("tenant_id")` | Claim tenant tùy biến. | Dùng theo hợp đồng issuer và kiểm tra quan hệ tenant nội bộ khi cần. |
| `getClaimAsStringList("roles")` | Danh sách role nếu định dạng phù hợp. | Dữ liệu đầu vào để ánh xạ authority, **không tự là `ROLE_*`**. |
| `getClaims()` | Toàn bộ claims. | Dùng có chọn lọc, không trả nguyên xi/log tùy tiện. |
| `getHeaders()` | JWT headers đã được parse. | Hữu ích cho chẩn đoán; không dùng `kid`/`alg` để tùy tiện chọn nguồn khóa tin cậy. |
| `getTokenValue()` | **Chuỗi JWT gốc**. | Là Bearer credential nhạy cảm; tránh log hoặc trả cho client. |

`Jwt` là một kiểu object trong Spring Security, không phải bằng chứng rằng mọi claim đều trở thành dữ liệu nghiệp vụ chính xác và cập nhật tức thời. Ví dụ `email` có thể đã thay đổi sau khi token được cấp; `tenant_id` có thể không phản ánh ngay membership mới nhất. Xác thực chữ ký chứng minh token được phát hành bởi bên tin cậy và còn hợp lệ theo validators, **không biến các thông tin thay đổi theo thời gian thành dữ liệu realtime**.

## 5. `JwtAuthenticationToken`: điều mà `Jwt` đơn lẻ không cung cấp

`JwtAuthenticationToken` là một implementation của `Authentication`, xây trên JWT đã xác thực. Nó có:

- **Principal**: thường chính đối tượng `Jwt`.
- **Name**: một chuỗi tên principal phục vụ giao diện `Authentication.getName()`.
- **Authorities**: các `GrantedAuthority` như `SCOPE_orders.read` hoặc role do converter tạo ra.
- **Authentication state**: được provider thiết lập sau khi xác minh token.
- **Token attributes**: các claim của JWT có thể truy cập qua `getTokenAttributes()`.

Ví dụ cách đọc kết quả:

```java
import java.util.Collection;
import java.util.Map;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

void inspect(JwtAuthenticationToken auth) {
    String principalName = auth.getName();
    boolean authenticated = auth.isAuthenticated();

    Jwt jwt = auth.getToken();
    Object principal = auth.getPrincipal();
    Collection<GrantedAuthority> authorities = auth.getAuthorities();
    Map<String, Object> tokenAttributes = auth.getTokenAttributes();

    // auth.getPrincipal() thông thường là đối tượng Jwt.
    // auth.getAuthorities() được dùng cho authorization.
    // tokenAttributes chứa claims, không nên log toàn bộ.
}
```

Một số điểm đáng nhớ:

| Biểu thức | Trong JWT Resource Server mặc định | Lưu ý |
| --- | --- | --- |
| `auth.getToken()` | `Jwt` đã được xác minh. | Có thể đọc claim, header, token value. |
| `auth.getPrincipal()` | Thường cùng đối tượng `Jwt`. | Không mặc định là một `UserDetails` hay entity database. |
| `auth.getName()` | Thường là chuỗi `sub`. | Có thể thay đổi nếu converter/constructor tùy chỉnh chọn principal claim khác. |
| `auth.getAuthorities()` | Authority theo scope/claim đã ánh xạ. | Không chứa mọi quyền nghiệp vụ trên từng bản ghi. |
| `auth.getTokenAttributes()` | Các claim token. | Không nên trả/log toàn bộ do có dữ liệu nhạy cảm. |
| `auth.isAuthenticated()` | `true` đối với kết quả do provider tin cậy trả về. | Không tin object giả lập từ dữ liệu HTTP do code không đáng tin tạo. |

Trong các ví dụ controller/service, **đọc `Authentication` do Spring Security cung cấp** là cách an toàn; không tự dựng một `JwtAuthenticationToken` từ payload chưa qua `JwtDecoder`.

### Không nhầm tên class với chức năng của object

`JwtAuthenticationToken` chứa một object tên là `Jwt`, nhưng điều đó **không có nghĩa** Resource Server đã đăng nhập người dùng qua OIDC. API xác thực Bearer **access token**. OIDC Client có thể dùng `OidcUser` hoặc `OidcIdToken` trong luồng `oauth2Login()`, còn Resource Server JWT có `JwtAuthenticationToken` cho request đến API. Đây là **hai vai trò bảo mật khác nhau**.

## 6. Principal name mặc định thường là `sub`

Ở cấu hình phổ biến của `JwtAuthenticationConverter`, tên principal được lấy từ claim `sub`:

```json
{
  "iss": "https://identity.example.com/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
```

Khi JWT được xác minh và converter mặc định hoạt động:

```java
JwtAuthenticationToken auth = ...;

auth.getName();             // Thường là "user-123"
auth.getToken().getSubject(); // "user-123"
```

Tuy nhiên, **`Authentication.getName()` là tên principal theo mapping**, không phải API đảm bảo “đây là ID người dùng trong bảng `users` của hệ thống”. Có ít nhất ba điều cần xem:

1. **Issuer**: `sub = user-123` dưới hai issuer khác nhau không tự đại diện cho cùng một tài khoản.
2. **Loại access token**: `sub` có thể đại diện cho End-User hoặc service/client tùy token profile.
3. **Converter tùy chỉnh**: ứng dụng có thể thay `principalClaimName`, làm `getName()` không còn bằng `sub`.

Ví dụ hai định danh khác nhau:

```text
iss = https://identity-a.example.com
sub = 123

iss = https://identity-b.example.com
sub = 123
```

Không được gộp hai chủ thể đó chỉ bởi chuỗi `sub` trùng nhau. Với tài khoản người dùng từ OIDC, cặp **issuer + subject** thường là điểm xuất phát phù hợp để liên kết sang tài khoản nội bộ. Với machine token, domain có thể cần namespace riêng cho service identity.

### `Jwt` không phải entity người dùng của ứng dụng

Một hệ thống thường có hai nhóm dữ liệu khác nhau:

```text
JWT claims đã xác minh
    iss, sub, client_id, scope, aud ...
                |
                v
Ánh xạ định danh nội bộ (nếu cần)
    external issuer + subject -> internal account/service
                |
                v
Truy vấn và chính sách nghiệp vụ
    membership, tenant, account status, ownership
```

Không nên giả định `sub` luôn có cùng kiểu/format với khóa `user_id` trong database. Thậm chí một access token hợp lệ có thể đại diện service mà không có bản ghi người dùng nội bộ nào.

## 7. `JwtAuthenticationToken` nhận authorities từ đâu?

Trong Spring Security Resource Server JWT, token thường có claim:

```json
{
  "scope": "orders.read orders.write"
}
```

Converter mặc định của Spring Security thường dùng `JwtGrantedAuthoritiesConverter` để đọc `scope` hoặc `scp` rồi chuyển thành:

```text
SCOPE_orders.read
SCOPE_orders.write
```

Đối với `Authentication`, authorities có thể được duyệt:

```java
Collection<? extends GrantedAuthority> authorities =
    authentication.getAuthorities();
```

Các rule tương ứng:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.requestMatchers(HttpMethod.POST, "/api/orders")
    .hasAuthority("SCOPE_orders.write")
```

**`getAuthorities()` không trả nguyên claim `scope`**; nó trả các object `GrantedAuthority` được tạo theo converter. Nếu ứng dụng thay prefix, claim source hoặc converter, chính sách `hasAuthority(...)` cần khớp.

Ví dụ claim tùy chỉnh:

```json
{
  "roles": ["ADMIN", "SUPPORT"]
}
```

Claim `roles` **không tự động** biến thành `ROLE_ADMIN` và `ROLE_SUPPORT` trong cấu hình mặc định của mọi ứng dụng. Cần converter được gắn vào JWT DSL, và chỉ tin các role mà issuer có thẩm quyền phát hành.

| Thuộc tính | Nguồn | Dùng để |
| --- | --- | --- |
| `scope` / `scp` trong `Jwt` | Access token đã xác minh. | Dữ liệu đầu vào cho quyền OAuth. |
| `SCOPE_*` trong `auth.getAuthorities()` | Kết quả ánh xạ từ converter. | Kiểm tra bằng `hasAuthority(...)`. |
| `roles` trong `Jwt` | Claim tùy biến, nếu có. | Chưa phải `GrantedAuthority` cho tới khi được mapping. |
| `ROLE_*` trong `Authentication` | Converter hoặc cơ chế role mapping đã cấu hình. | Kiểm tra bằng `hasRole(...)` hoặc `hasAuthority(...)`. |
| Quyền trên một đơn hàng cụ thể | Database/service policy. | Quyết định owner, tenant và điều kiện nghiệp vụ. |

## 8. Spring Boot: cấu hình JWT Resource Server tối thiểu

Với Gradle:

```gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

Khai báo issuer:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/realms/shop
```

Cấu hình một `SecurityFilterChain` cho API:

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
                .requestMatchers(HttpMethod.GET, "/api/me")
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

Ở đây:

- `oauth2ResourceServer().jwt()` làm API sử dụng Bearer JWT authentication. `JwtDecoder` được cấu hình qua Spring Boot hoặc bean mà ứng dụng cung cấp.
- `authenticated()` yêu cầu kết quả authentication hợp lệ, không tự cấp quyền đọc mọi tài nguyên.
- `hasAuthority("SCOPE_orders.read")` kiểm tra một quyền truy cập đã được ánh xạ.
- `STATELESS` thể hiện API không dựa vào session server để lưu trạng thái đăng nhập.
- `securityMatcher("/api/**")` chỉ áp dụng chain này cho URL khớp. Nếu ứng dụng có URL khác, cần chain hoặc fallback bảo vệ rõ ràng.

Ví dụ tắt CSRF chỉ phù hợp khi API nhận Bearer token truyền rõ trong header và **không** dựa vào cookie xác thực mà browser tự gửi. Nếu ứng dụng cũng dùng web login/session/cookie, cần thiết kế filter chain và CSRF theo từng khu vực.

### Từ issuer đến principal

Với JWT hợp lệ, Resource Server thông thường thực hiện:

```text
issuer-uri / JwtDecoder bean
          |
          v
JwtDecoder xác minh JWT
          |
          v
JwtAuthenticationConverter ánh xạ authorities/name
          |
          v
JwtAuthenticationToken trong SecurityContext
```

Nếu ứng dụng tự khai báo `JwtDecoder`, Spring Boot có thể nhường chỗ cho bean đó. Khi ấy, ứng dụng phải đảm bảo decoder thật vẫn xác minh chữ ký, issuer, thời gian và audience theo chính sách. `JwtAuthenticationToken` không thể sửa một decoder đã bỏ qua validator quan trọng.

## 9. Đọc `Jwt` từ controller bằng `@AuthenticationPrincipal`

Với endpoint đã yêu cầu authentication bằng JWT, cách ngắn gọn là:

```java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MeController {

    @GetMapping("/api/me")
    public Map<String, Object> me(@AuthenticationPrincipal Jwt jwt) {
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("issuer", jwt.getIssuer().toString());
        response.put("subject", jwt.getSubject());
        response.put("clientId",
            jwt.getClaimAsString("client_id"));
        return response;
    }
}
```

Spring MVC lấy `Jwt` từ principal của `Authentication` hiện tại. Do controller sử dụng **JWT Resource Server chain** và endpoint được bảo vệ, dữ liệu này đã đi qua decoder/validator tương ứng; controller không cần tự lấy raw token từ header.

Khi triển khai thực tế:

- Không mặc định một claim tùy chọn như `client_id` luôn có mặt.
- Chỉ trả các trường thực sự cần theo hợp đồng API.
- Tránh trả nguyên JWT, toàn bộ claims hoặc các thuộc tính cá nhân không liên quan.
- Nếu endpoint hỗ trợ cả opaque-token authentication, principal có thể **không phải `Jwt`**; không ép kiểu JWT vô điều kiện.

Đoạn trên chỉ minh họa thông tin caller; nhiều hệ thống không cần endpoint như vậy trong production.

## 10. Đọc `JwtAuthenticationToken` và các authorities trong controller

Khi cần cả claim và các authority đã được mapping, có thể sử dụng `Authentication`:

```java
import java.util.List;
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CurrentCallerController {

    @GetMapping("/api/caller")
    public Map<String, Object> caller(Authentication authentication) {
        if (!(authentication instanceof JwtAuthenticationToken jwtAuth)) {
            throw new IllegalStateException(
                "Endpoint requires JWT authentication");
        }

        List<String> authorities = jwtAuth.getAuthorities()
            .stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return Map.of(
            "principalName", jwtAuth.getName(),
            "subject", jwtAuth.getToken().getSubject(),
            "authorities", authorities
        );
    }
}
```

Để endpoint này chạy, security chain phải có rule cho `/api/caller`, ví dụ `.requestMatchers("/api/caller").authenticated()` đặt trước `anyRequest().denyAll()`. Logic ví dụ giả định `getName()` và `sub` được yêu cầu hiện diện theo token profile. Ứng dụng thật nên kiểm tra null khi nhận claim tùy chọn và có error handling phù hợp.

**`Authentication` là abstraction tốt khi cần xử lý nhiều cơ chế xác thực**, nhưng phải kiểm tra kiểu/token contract trước khi ép thành `JwtAuthenticationToken`. Nếu biết chắc đường đi là JWT Resource Server, truy cập `Jwt` trực tiếp bằng `@AuthenticationPrincipal` có thể ngắn gọn hơn.

### Khi nào dùng cách nào?

| Nhu cầu | API thường dùng |
| --- | --- |
| Chỉ cần subject, issuer hoặc claim JWT | `@AuthenticationPrincipal Jwt jwt` |
| Cần authorities đã được converter tạo | `Authentication.getAuthorities()` hoặc `JwtAuthenticationToken.getAuthorities()` |
| Cần principal name sau ánh xạ | `Authentication.getName()` |
| Cần toàn bộ JWT đã được xác minh | `JwtAuthenticationToken.getToken()` |
| Muốn dùng trong service không phụ thuộc HTTP | Truyền một identity/domain context rõ ràng từ lớp ứng dụng hoặc dùng method security phù hợp |
| Hỗ trợ opaque token hoặc nhiều authentication mechanism | Dùng abstraction `Authentication` và phân nhánh theo kiểu principal hợp lệ |

## 11. Dữ liệu danh tính đã xác thực có thực sự là “người dùng”?

**Không phải lúc nào cũng vậy.** OAuth 2.0 cho phép access token được phát hành trong nhiều ngữ cảnh:

| Ngữ cảnh | Subject có thể đại diện | Diễn giải phù hợp |
| --- | --- | --- |
| Authorization Code với người dùng | End-User theo hợp đồng issuer. | Có thể liên kết `iss + sub` sang tài khoản nội bộ. |
| Client Credentials | Client/service account/workload. | Không mặc định có một End-User đăng nhập. |
| Token exchange / on-behalf-of | Subject và actor có thể là các chủ thể khác nhau. | Cần token profile để diễn giải delegation. |
| Opaque access token | Subject từ introspection metadata. | Principal không phải JWT; ý nghĩa vẫn theo issuer. |

Ví dụ JWT theo ngữ cảnh machine-to-machine:

```json
{
  "iss": "https://identity.example.com/realms/shop",
  "sub": "service-account-8735",
  "client_id": "inventory-worker",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
```

Một số issuer có thể đặt `sub` trùng `client_id`, issuer khác dùng service account ID riêng. **Không suy ra `sub == client_id` là quy tắc chung**, cũng không suy ra giá trị giống email chắc chắn là người dùng.

Khi API có cả user và service callers, nên tách loại caller trong domain theo **claim đáng tin/profile của issuer** hoặc quy tắc issuer/client được kiểm soát:

```java
public enum CallerKind {
    USER,
    SERVICE
}

public record CallerIdentity(
    CallerKind kind,
    String issuer,
    String subject,
    String clientId
) {}
```

Đây là kiểu ứng dụng tự định nghĩa, **không phải đối tượng Spring Security tự cung cấp**. `JwtAuthenticationToken` chứa JWT và authorities, nhưng không tự xác định chính xác `CallerKind` cho mọi Authorization Server.

Nếu token profile không có thông tin đáng tin để phân biệt user/service mà nghiệp vụ cần phân loại, **không đoán dựa vào định dạng chuỗi `sub`**. Cần thống nhất lại hợp đồng phát hành token hoặc từ chối các thao tác yêu cầu phân loại.

## 12. ID Token của OIDC và access token JWT không thể dùng thay nhau

Ứng dụng có thể vừa là **OIDC Client** cho đăng nhập người dùng, vừa là **OAuth 2.0 Resource Server** cho API. Nhưng dữ liệu principal ở hai vai trò không giống nhau:

| Ngữ cảnh | Token/credential liên quan | Principal thường gặp | Mục đích |
| --- | --- | --- | --- |
| OIDC Client đăng nhập bằng `oauth2Login()` | Authorization Code, ID Token và các thông tin OIDC liên quan. | `OidcUser`/`OAuth2AuthenticationToken` theo luồng client. | Thiết lập phiên đăng nhập Client và hồ sơ người dùng. |
| JWT Resource Server | Bearer **access token** từ request API. | `Jwt` trong `JwtAuthenticationToken`. | Xác thực và phân quyền lời gọi protected API. |
| Opaque-token Resource Server | Bearer opaque access token. | `OAuth2AuthenticatedPrincipal` trong `BearerTokenAuthentication`. | Xác thực token theo introspection và phân quyền API. |

Trong **OIDC ID Token**, `sub` chuẩn hóa định danh End-User cho OIDC Client. Nhưng Resource Server **không thể mặc định** rằng mọi JWT được gửi đến đều là access token hợp lệ chỉ vì nó chứa `sub` hay có chữ ký từ cùng issuer.

Ví dụ một ID Token thường có `aud` dành cho OIDC Client, không phải API `orders-api`. API phải từ chối token không đúng mục đích và audience/token profile. Điều này cũng giải thích vì sao `JwtAuthenticationToken` **không đồng nghĩa** với “OIDC user session” hay “đã gọi UserInfo endpoint”.

OIDC **UserInfo** là protected resource có thể cung cấp claim hồ sơ cho OIDC Client khi cần; nó không phải bước mặc định bắt buộc để Resource Server tạo `JwtAuthenticationToken` cho mỗi API request.

## 13. Tùy chỉnh tên principal bằng `JwtAuthenticationConverter`

Mặc định principal name thường dựa trên `sub`. Trong một số dự án, developer muốn thay nó thành claim `preferred_username`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;

@Bean
JwtAuthenticationConverter customPrincipalNameConverter() {
    JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();

    converter.setPrincipalClaimName("preferred_username");
    return converter;
}
```

Sau đó gắn converter **rõ ràng** vào JWT DSL:

```java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt
        .jwtAuthenticationConverter(customPrincipalNameConverter)))
```

Trong ví dụ này, `customPrincipalNameConverter` là bean/converter đã được inject vào phương thức tạo chain. Với token hợp lệ:

```json
{
  "sub": "user-123",
  "preferred_username": "alice"
}
```

thì `auth.getName()` có thể trở thành `"alice"` trong khi `auth.getToken().getSubject()` vẫn là `"user-123"`.

**Hậu quả quan trọng:** nếu code nghiệp vụ đang dùng `authentication.getName()` làm khóa owner trong database, việc đổi converter có thể làm đổi danh tính nghiệp vụ mà không đổi token. `preferred_username` hoặc email cũng có thể đổi theo thời gian và không duy nhất giữa các issuer.

Thường nên giữ một **định danh ổn định** cho authorization/audit, chẳng hạn issuer + subject hoặc ánh xạ sang internal ID. Tên hiển thị nên được xử lý như thuộc tính giao diện, không phải khóa bảo mật.

## 14. Tùy chỉnh authorities từ claim role nhưng giữ OAuth scopes

Giả sử issuer phát hành:

```json
{
  "scope": "orders.read",
  "roles": ["SUPPORT"]
}
```

API cần cả `SCOPE_orders.read` và `ROLE_SUPPORT`. Có thể kết hợp `JwtGrantedAuthoritiesConverter` cho scope với một phần ánh xạ role riêng:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

@Bean
JwtAuthenticationConverter roleAndScopeConverter() {
    JwtGrantedAuthoritiesConverter scopeConverter =
        new JwtGrantedAuthoritiesConverter();

    JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();

    converter.setJwtGrantedAuthoritiesConverter((Jwt jwt) -> {
        Collection<GrantedAuthority> result =
            new ArrayList<>(scopeConverter.convert(jwt));

        List<String> roles = jwt.getClaimAsStringList("roles");
        if (roles != null) {
            for (String role : roles) {
                if ("SUPPORT".equals(role)) {
                    result.add(new SimpleGrantedAuthority("ROLE_SUPPORT"));
                }
            }
        }

        return result;
    });

    return converter;
}
```

Gắn vào chain:

```java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt.jwtAuthenticationConverter(roleAndScopeConverter)))
```

Ví dụ chỉ cho phép role nằm trong tập ứng dụng mong đợi (`SUPPORT`) thay vì nối mọi chuỗi từ token thành `ROLE_*` không kiểm soát. Điều này **không sửa token và không thực hiện lại JWT signature validation**; converter nhận `Jwt` đã được decoder chấp nhận rồi ánh xạ thành authorities.

Khi dùng custom converter:

- Bảo đảm JWT decoder vẫn kiểm tra issuer, audience và thời gian.
- Xác định claim nào do Authorization Server đáng tin có quyền phát hành.
- Hiểu rõ `hasAuthority("SCOPE_orders.read")` khác `hasRole("SUPPORT")` (mặc định tương ứng `ROLE_SUPPORT`).
- Không coi `roles`/`scope` là quyền đọc mọi bản ghi; vẫn cần ownership/tenant policy.
- Một bean converter riêng **không nên được giả định** sẽ tự gắn vào tất cả chain; wiring ở JWT DSL theo nhu cầu.

## 15. Từ `Jwt` sang tài khoản nội bộ: không tin những gì ngoài contract

Một access token đã được xác minh có thể chứng minh các claim do issuer phát hành trong khoảng hiệu lực của nó. Nó **không nhất thiết cung cấp trạng thái kinh doanh hiện tại** như khách hàng đã bị khóa, membership vừa bị gỡ hay đơn hàng đang thuộc tenant nào.

Ví dụ API nhận JWT:

```json
{
  "iss": "https://identity.example.com/realms/shop",
  "sub": "user-123",
  "scope": "orders.read",
  "tenant_id": "tenant-a",
  "email": "customer@example.com"
}
```

Một hệ thống có thể dùng `iss + sub` để tìm **tài khoản nội bộ**:

```text
external_identity
    issuer: https://identity.example.com/realms/shop
    subject: user-123
                  |
                  v
internal_user_id: 98765
                  |
                  v
account_status, active_memberships, tenant permissions
```

Phân lớp nguồn dữ liệu:

| Dữ liệu | Nguồn tin cậy ban đầu | Có thể cần kiểm tra thêm? |
| --- | --- | --- |
| `iss`, `sub` | JWT đã được xác thực hoặc introspection theo contract. | Ánh xạ sang domain identity, namespace issuer. |
| `scope` | Access token do issuer cấp. | Policy API và dữ liệu cụ thể. |
| `tenant_id` trong JWT | Issuer nếu được thống nhất nguồn thẩm quyền. | Membership/tenant hiện tại nếu chính sách yêu cầu. |
| `email`, `name` | Claim hồ sơ token. | Trạng thái verified, freshness, thay đổi và privacy. |
| Quyền sở hữu đơn hàng | Database/authorization service nghiệp vụ. | Bắt buộc kiểm tra khi truy cập bản ghi. |
| Tài khoản đã bị khóa sau khi token phát hành | Hệ thống tài khoản và chính sách thu hồi. | Có thể cần kiểm tra trực tuyến hoặc token lifetime ngắn. |

Trong hệ thống nhiều tenant, đừng cho phép `X-Tenant-Id` do client gửi tự thay thế tenant trong ngữ cảnh xác thực. Tenant do client yêu cầu có thể là **tham số lựa chọn**, nhưng API phải xác minh quyền thuộc tenant đó từ nguồn đáng tin.

## 16. Ví dụ service kiểm tra owner sau khi có `Jwt` hợp lệ

Giả sử `/api/orders/{id}` yêu cầu `SCOPE_orders.read`. Ngay cả khi JWT hợp lệ và scope đúng, API vẫn phải ngăn caller đọc đơn hàng của người khác.

Một service minh họa:

```java
import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class OrderQueryService {

    private final OrderRepository repository;

    public OrderQueryService(OrderRepository repository) {
        this.repository = repository;
    }

    public OrderDto findVisibleOrder(long orderId, Jwt jwt) {
        String issuer = jwt.getIssuer().toString();
        String subject = jwt.getSubject();

        return repository
            .findByIdAndOwnerIssuerAndOwnerSubject(
                orderId,
                issuer,
                subject
            )
            .map(OrderDto::from)
            .orElseThrow(() ->
                new ResponseStatusException(HttpStatus.NOT_FOUND));
    }
}
```

`OrderRepository`, `Order` và `OrderDto` là các kiểu nghiệp vụ minh họa cần được triển khai. Controller phải nhận JWT từ `@AuthenticationPrincipal` trong một endpoint được bảo vệ và truyền vào service; `SecurityFilterChain` kiểm tra `orders.read` trước khi xử lý.

Ở một ứng dụng khác, `issuer + subject` có thể cần ánh xạ sang **internal user ID**, rồi truy vấn owner bằng ID nội bộ. Nếu token có `tenant_id`, phải xác nhận issuer thực sự có thẩm quyền về tenant hoặc xác minh membership qua dữ liệu riêng.

Ví dụ trả `404` khi record không tồn tại trong phạm vi owner để hạn chế tiết lộ sự tồn tại của bản ghi ngoài quyền xem. Tùy hợp đồng, API có thể trả `403`. Điều quan trọng là **phân quyền đối tượng** được thực hiện trong service/query, không dựa hoàn toàn vào một authority rộng.

### Vì sao không nên dùng `authentication.getName()` vô điều kiện?

Ví dụ sau chứa một giả định rủi ro:

```java
// Không nên áp dụng nếu getName() có thể đã bị tùy chỉnh
// hoặc token có thể đại diện machine client.
String userId = authentication.getName();
return repository.findByOwnerUserId(userId);
```

Nếu converter đổi principal name từ `sub` sang `preferred_username`, dữ liệu owner sẽ bị liên kết theo một key khác. Nếu token đại diện service, `userId` không phản ánh một người dùng. Với hệ thống có nhiều loại caller, hãy truyền một **domain caller identity** đã được phân loại/ánh xạ thay vì dựa vào chuỗi `getName()` không kèm context.

## 17. `SecurityContext` tồn tại như thế nào trong request?

Sau authentication thành công, Spring Security lưu `Authentication` vào `SecurityContext` và cho các thành phần phía sau truy cập:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();
```

Trong ứng dụng Servlet thông thường, `SecurityContextHolder` mặc định sử dụng chiến lược **ThreadLocal** cho luồng request. Vì vậy, không nên suy ra `Authentication` sẽ tự động xuất hiện trong mọi thread mới hoặc callback asynchronous ngoài ngữ cảnh đã được framework truyền.

Các trường hợp cần lưu ý:

- Với request đi qua JWT Resource Server filter chain và xác thực thành công, context chứa kết quả thích hợp cho phần còn lại của request.
- Với endpoint `permitAll`, context có thể không có Bearer principal hoặc có anonymous authentication; phải xử lý null/anonymous nếu code đọc trực tiếp.
- Với một API stateless, authentication thường được **xây lại từ Bearer token trên từng request**, không mặc định có session login trên server.
- Khi thực hiện `@Async`, executor, task queue hoặc xử lý bất đồng bộ, nếu thực sự cần security context, dùng cơ chế propagation được Spring Security hỗ trợ hoặc truyền danh tính nghiệp vụ tối thiểu một cách rõ ràng.
- Không lưu `JwtAuthenticationToken` hay raw JWT vào cache chung hoặc singleton để “dùng cho những request sau”; điều này có thể làm lẫn danh tính giữa người gọi.

Ví dụ khi đọc từ service mà không được truyền `Jwt` vào, không nên giả định context có mặt ở mọi entry point (scheduler, batch, event listener). Với các luồng không do HTTP Resource Server xác thực, hệ thống cần một **identity source khác được thiết kế đúng**, không tạo fake Bearer principal.

## 18. Các kiểu principal khi Resource Server nhận opaque token

Mặc định với JWT authentication:

```text
Authentication: JwtAuthenticationToken
Principal: Jwt
Token data: Jwt claims
```

Với opaque token qua introspection:

```text
Authentication: BearerTokenAuthentication
Principal: OAuth2AuthenticatedPrincipal
Token data: introspection attributes
```

Một API opaque có cấu hình tương ứng:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://identity.example.com/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

Chain phải bật `.oauth2ResourceServer(oauth2 -> oauth2.opaqueToken(...))` thay cho JWT cơ chế thông thường. **Không ép kiểu `authentication.getPrincipal()` thành `Jwt`** chỉ vì request có Bearer token. Loại principal được tạo phụ thuộc authentication provider đã xác thực token.

Nếu một ứng dụng vừa chấp nhận JWT vừa chấp nhận opaque token trên các nhóm endpoint khác nhau, nên giữ một **abstraction danh tính chung cho domain** thay vì để mọi service hiểu chi tiết cách decode token. Abstraction phải giữ nguồn phát hành, subject, client type/actor và quyền thật sự cần thiết.

## 19. Điều gì xảy ra khi xác thực thất bại?

Một token chưa được chấp nhận **không được cung cấp như verified principal** cho endpoint đã được bảo vệ:

| Tình huống | Authentication | Authorization | Kết quả thường gặp |
| --- | --- | --- | --- |
| Thiếu Bearer token trên endpoint yêu cầu authentication. | Không có principal đã xác thực. | Không thể cho phép. | `401 Unauthorized`. |
| JWT sai chữ ký, sai issuer hoặc hết hạn. | Thất bại tại decoder/provider. | Không sử dụng claims của token. | `401 Unauthorized`. |
| JWT đúng chữ ký nhưng sai audience theo validator API. | Thất bại theo token policy. | Không sử dụng claims của token. | `401 Unauthorized`. |
| JWT hợp lệ nhưng thiếu `SCOPE_orders.read`. | Thành công, có `JwtAuthenticationToken`. | Không đủ authority. | `403 Forbidden`. |
| JWT hợp lệ, đủ scope nhưng sai owner/tenant. | Thành công. | Domain policy từ chối. | `403` hoặc `404`. |
| JWT hợp lệ, đúng scope và đúng tài nguyên. | Thành công. | Được phép. | `2xx` nếu nghiệp vụ xử lý thành công. |
| Endpoint `permitAll` không có Bearer token. | Không yêu cầu verified JWT. | Route công khai được cho phép. | Đi tiếp theo nghiệp vụ. |

Trong OAuth 2.0 Bearer, response `401` có thể đi cùng header `WWW-Authenticate: Bearer`, và lỗi token không hợp lệ có thể mang `invalid_token`. Token được xác minh thành công nhưng thiếu scope có thể dẫn tới `insufficient_scope` theo cơ chế xử lý từ chối quyền.

**Không đồng nhất lỗi `401` với lỗi `403`**: trường hợp thứ nhất thường là credential bị từ chối hoặc thiếu authentication; trường hợp thứ hai thường là đã có principal nhưng không đủ quyền.

## 20. Các phản ví dụ dễ gây lỗi bảo mật

### 20.1. Base64-decode payload JWT rồi tin `sub`

```java
// Pseudocode PHẢN VÍ DỤ: không dùng trong production.
String rawToken = request.getHeader("Authorization");
String subject = decodePayloadWithoutSignatureCheck(rawToken)
    .get("sub").toString();

return orderService.getOrders(subject);
```

Đoạn trên mô tả hành vi sai, `decodePayloadWithoutSignatureCheck` không phải API Spring Security được khuyến nghị. Bất kỳ ai cũng có thể dựng payload `sub = admin`. Cách đúng là nhận `Jwt` đã được decoder xác minh hoặc `Authentication` từ Spring Security.

### 20.2. Coi `Jwt` là user entity nội bộ

```java
String userId = jwt.getSubject();
userRepository.setAdmin(userId);
```

Đoạn mã rút gọn này bỏ qua issuer namespace, loại caller, kiểm tra quyền thao tác và ánh xạ danh tính nội bộ. Không dùng `sub` làm bằng chứng được phép nâng quyền tài khoản.

### 20.3. Cho client tự khai authority ngoài token

```http
GET /api/admin/reports
Authorization: Bearer <valid-user-token>
X-Role: ADMIN
X-User-Id: ceo
```

Header `X-Role` và `X-User-Id` do client gửi không tự biến chủ thể thành admin. Nếu sau API gateway có header identity được ủy quyền, gateway/backend phải có trust boundary và loại bỏ header giả mạo từ Internet; không dùng header tùy ý thay JWT principal.

### 20.4. Tự dựng `JwtAuthenticationToken` từ payload chưa xác minh

Trong test, có thể tạo một `Jwt` giả lập rồi bọc thành `JwtAuthenticationToken` để kiểm tra policy. Nhưng code production không được biến input HTTP bất kỳ thành authenticated principal mà **không đi qua JWT verification**. Việc một object có kiểu `JwtAuthenticationToken` không tự chứng minh issuer/chữ ký đã được kiểm tra nếu nó được dựng thủ công từ dữ liệu không đáng tin.

### 20.5. Trả toàn bộ claims hoặc raw token ra API

`jwt.getTokenValue()` là Bearer credential, có thể bị sử dụng lại nếu còn hiệu lực. `jwt.getClaims()` có thể chứa email, tên, tenant và dữ liệu cá nhân. Không ghi raw token vào log, URL, response, exception message hoặc telemetry; chỉ công bố thuộc tính đã được xác định cần thiết.

### 20.6. Chỉ kiểm tra `isAuthenticated()` để cho xem mọi dữ liệu

Một người có `SCOPE_orders.read` không nhất thiết được xem đơn hàng của mọi người. `authenticated()` là yêu cầu danh tính hợp lệ; `hasAuthority(...)` và domain policy quyết định quyền thực tế.

### 20.7. Thay đổi converter rồi quên các rule cũ

Nếu đổi authority prefix hoặc principal claim name, `hasAuthority("SCOPE_orders.read")`, audit identity và owner lookup có thể bị thay đổi hành vi. Cần hiểu converter nào **thực sự được chain sử dụng**; một bean converter khai báo nhưng không wiring vào JWT DSL có thể không được áp dụng.

## 21. Quan sát JWT principal mà không làm lộ credential

Khi debug request có Bearer JWT, log nên tách rõ các giai đoạn:

```text
[1] GET /api/orders/42
[2] Bearer extraction: token hiện diện (không ghi raw token)
[3] JwtDecoder: chữ ký/iss/thời gian/aud hợp lệ
[4] JwtAuthenticationToken được tạo
[5] Principal: issuer=shop, subject=user-123
[6] Authorities: SCOPE_orders.read
[7] Endpoint policy: được phép
[8] Object policy: đơn 42 thuộc user-123 trong tenant-a
[9] Response: 200
```

Ngược lại:

```text
[3] JWT invalid_signature
-> Không có verified JwtAuthenticationToken
-> Thường trả 401
```

Hoặc:

```text
[3] JWT hợp lệ
[4] JwtAuthenticationToken được tạo
[6] Thiếu SCOPE_orders.write
-> Thường trả 403
```

Những bản ghi trên là ví dụ ở mức khái niệm, không phải log mặc định của Spring Security. Log thực tế phải tuân thủ chính sách privacy, tránh ghi raw token, toàn bộ claims và giá trị định danh có thể nhạy cảm khi không cần.

Một số tín hiệu có ích để chẩn đoán: issuer cấu hình, kiểu authentication, tên authority được kiểm tra, kết quả validator theo nhóm lỗi, trace ID và đường dẫn endpoint. Nếu hệ thống đa issuer/multi-tenant, cần tránh chỉ log `sub` mà bỏ bối cảnh issuer và loại caller.

## 22. Kiểm thử cần phân biệt principal mapping và JWT verification

Spring Security Test cho phép mô phỏng JWT principal trong MockMvc, chẳng hạn:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrdersApiTest {

    @Autowired
    MockMvc mvc;

    @Test
    void authenticatedJwtWithScopeCanReachEndpoint() throws Exception {
        mvc.perform(get("/api/orders/42")
            .with(jwt()
                .jwt(jwt -> jwt
                    .subject("user-123")
                    .claim("scope", "orders.read")
                    .claim("iss", "https://identity.example.com/realms/shop"))
            ))
            .andExpect(status().isOk());
    }
}
```

Test trên chỉ mang tính minh họa và giả định có controller/service trả `200` cho đơn hàng 42 thuộc user `user-123`; nếu dữ liệu hoặc rule khác, cần chuẩn bị fixture/mock phù hợp. Trong Spring Security Test, `.with(jwt())` thường **tạo `Authentication` JWT giả lập** để kiểm tra behavior của filter chain/authorization, **không tự xác minh chữ ký JWT thật qua production `JwtDecoder`**.

Vì thế cần hai nhóm test khác nhau:

| Nhóm | Mục tiêu | Điều chưa được chứng minh nếu chỉ test nhóm này |
| --- | --- | --- |
| **Authorization / principal mapping** với `jwt()` hoặc mock `JwtAuthenticationToken`. | Endpoint đọc đúng `Jwt`, `getName()`, authorities; từ chối thiếu scope/sai owner. | Chưa chứng minh decoder thực sự từ chối JWT giả chữ ký. |
| **JWT validation / integration** với token ký thật bằng test key và issuer/JWKS kiểm thử. | Xác minh chữ ký, thời gian, issuer, audience và tạo `Authentication` theo chain thực. | Chưa tự thay thế kiểm thử quyền trên mọi tài nguyên nghiệp vụ. |

Các ca nên có:

1. Request không token đến protected API → từ chối authentication.
2. JWT sai chữ ký hoặc hết hạn → decoder/provider từ chối.
3. JWT đúng chữ ký nhưng `iss` hoặc `aud` không hợp lệ → từ chối theo validator.
4. JWT hợp lệ có `sub`, `scope` → tạo principal và authorities đúng converter.
5. JWT hợp lệ thiếu scope → authorization từ chối.
6. JWT hợp lệ đúng scope nhưng khác owner/tenant → domain policy từ chối.
7. User token và client-credentials token → không tự hiểu nhầm service `sub` là user.
8. Custom principal claim name → `getName()` đổi theo converter, `jwt.getSubject()` vẫn giữ `sub`.
9. Opaque principal → không bị ép thành `Jwt` trong các đường đi hỗ trợ opaque.

Phân biệt hai nhóm test này ngăn tình huống “controller test có JWT giả lập thì thành công” bị hiểu sai thành “xác minh chữ ký của API đang hoạt động đúng trên production”.

## 23. Bảng chọn API khi làm việc với danh tính sau xác thực

| Câu hỏi của developer | Thành phần cần nhìn | Lý do |
| --- | --- | --- |
| Raw token đã được verify chưa? | `JwtDecoder`, `JwtAuthenticationProvider`. | Đây là ranh giới tin cậy, không phải controller. |
| JWT có subject gì? | `Jwt.getSubject()`. | Đọc `sub` đã được chấp nhận. |
| Issuer nào phát hành subject? | `Jwt.getIssuer()`. | Tránh trùng định danh giữa các issuer. |
| Principal name mà Spring Security đang báo là gì? | `Authentication.getName()`. | Có thể đã được tùy chỉnh bằng converter. |
| API đang thấy những authorities nào? | `JwtAuthenticationToken.getAuthorities()`. | Đó là dữ liệu `hasAuthority`/`hasRole` kiểm tra. |
| Có thể xem claims của JWT đã xác thực? | `Jwt.getClaims()` hoặc `getClaimAs...`. | Chỉ đọc claim thực sự cần và theo token profile. |
| JWT có đúng audience không? | `JwtDecoder` + audience validator. | Phải xác minh trước khi tạo trusted principal. |
| Chủ thể là user hay service? | Issuer/token contract + domain identity resolver. | Không suy ra từ class `JwtAuthenticationToken`. |
| Người gọi có quyền đọc đơn hàng này? | Scope + service/domain ownership policy. | Token hợp lệ chưa đủ quyền trên record. |
| Endpoint có chắc luôn có JWT principal? | `SecurityFilterChain` matcher + authentication rule. | `permitAll`, opaque hoặc chain khác có thể cho principal kiểu khác. |
| Dùng principal ngoài HTTP request thế nào? | Identity context được truyền rõ hoặc security-context propagation thích hợp. | Tránh phụ thuộc ThreadLocal ở scheduler/async. |

## 24. Sơ đồ quyết định khi đọc danh tính trong Resource Server

```mermaid
flowchart TD
    A["Request mang Authorization: Bearer token"] --> B["Credential đầu vào chưa đáng tin"]
    B --> C{"Decoder/provider chấp nhận token?"}
    C -- "Không" --> D["Authentication thất bại, thường 401"]
    C -- "Có, JWT" --> E["Jwt: headers + claims đã xác minh"]
    E --> F["JwtAuthenticationConverter"]
    F --> G["JwtAuthenticationToken: principal + name + authorities"]
    G --> H["SecurityContext"]
    H --> I{"Endpoint có đủ scope/role?"}
    I -- "Không" --> J["403 Forbidden"]
    I -- "Có" --> K{"Đúng caller kind, owner, tenant, policy?"}
    K -- "Không" --> L["403/404 theo chính sách"]
    K -- "Có" --> M["Xử lý nghiệp vụ"]
```

Nếu token là opaque, nhánh thành công sẽ tạo kiểu authentication/principal khác, nhưng nguyên tắc vẫn giữ: **danh tính phải đến từ kết quả xác thực đáng tin, và quyền trên tài nguyên được xét sau đó**.

Đối với mọi đoạn code làm việc với `Jwt` và `JwtAuthenticationToken`, cần giữ ba ranh giới rõ:

1. **Raw Bearer token → `Jwt` được xác minh:** token phải qua decoder, chữ ký và claim validators. Không tin payload chưa xác minh.
2. **`Jwt` → `JwtAuthenticationToken`:** converter tạo tên principal và authorities từ claims đáng tin; đó là ngữ cảnh Spring Security sử dụng, không phải entity người dùng tự động.
3. **`JwtAuthenticationToken` → quyết định nghiệp vụ:** API dùng principal/authority đúng hợp đồng token, kiểm tra loại chủ thể, issuer, ownership, tenant và các điều kiện của dữ liệu cụ thể.

**Điểm cốt lõi:** `Jwt` trả lời **token đã xác minh chứa những gì**; `JwtAuthenticationToken` trả lời **Spring Security đang xác thực request này dưới principal và authorities nào**. Còn việc **chủ thể đó được phép làm gì trên tài nguyên nào** luôn phải được quyết định bằng chính sách authorization phù hợp, không thể suy ra chỉ từ một `sub`, một scope hay sự tồn tại của JWT.
