# SCOPE_ prefix trong Spring Security: từ OAuth scope đến GrantedAuthority

## 1. Tại sao có `SCOPE_`?

Khi một ứng dụng nhận OAuth 2.0 **access token**, Resource Server cần trả lời ít nhất hai câu hỏi: token có hợp lệ và dành cho API này không; nếu hợp lệ, token được cấp những quyền nào? Trong Spring Security, quyền dùng để phân quyền thường được biểu diễn bằng đối tượng `GrantedAuthority`. Theo quy ước mặc định của Spring Security OAuth 2.0 Resource Server, mỗi scope trong access token được chuyển thành một authority có **tiền tố `SCOPE_`**.

Ví dụ, một JWT access token có claim:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "aud": ["orders-api"],
  "exp": 1893456000,
  "scope": "orders:read orders:write"
}
~~~

Sau khi token **được xác minh thành công**, ánh xạ mặc định có thể tạo:

~~~text
JWT claim scope = "orders:read orders:write"
             |
             v
JwtGrantedAuthoritiesConverter
             |
             +--> SimpleGrantedAuthority("SCOPE_orders:read")
             +--> SimpleGrantedAuthority("SCOPE_orders:write")
             |
             v
Authentication.getAuthorities()
~~~

Ứng dụng có thể bảo vệ một endpoint đọc đơn hàng bằng:

~~~java
.hasAuthority("SCOPE_orders:read")
~~~

Đây là chủ đề **SCOPE_ prefix** thuộc chương **Spring Security authorities** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Bài gắn với mô hình tin cậy, vòng đời token và các khái niệm JWT/opaque token, access token/refresh token, OAuth 2.0/OIDC, kiểm tra claims, scope, audience, phát hành và thu hồi token cũng như phòng chống lạm dụng token bị đánh cắp hoặc phát lại.

**Phạm vi minh họa:** Java, Spring Security 6, Spring Boot 3 và ứng dụng HTTP Servlet dùng OAuth 2.0 Resource Server. Các ví dụ cần khai báo imports/dependencies và cấu hình issuer/decoder theo môi trường. Mặc định framework và các extension point có thể thay đổi ở các phiên bản khác.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao scope `orders:read` trở thành authority `SCOPE_orders:read`.
2. Phân biệt **OAuth scope**, **Spring authority**, **role** và **quyền trên tài nguyên cụ thể**.
3. Chọn đúng `hasAuthority("SCOPE_...")` thay vì nhầm với `hasRole("...")`.
4. Hiểu ảnh hưởng của `scope`/`scp` trong JWT hoặc thông tin introspection của opaque token.
5. Cấu hình `JwtGrantedAuthoritiesConverter` và `JwtAuthenticationConverter` khi cần ánh xạ quyền tùy chỉnh.
6. Kiểm thử chính sách phân quyền mà không lẫn kiểm thử converter với kiểm chứng chữ ký JWT.
7. Nhận diện những rủi ro mà tiền tố `SCOPE_` **không giải quyết**, như audience sai, token bị thu hồi và thiếu kiểm tra ownership.

## 2. Scope, authority, role: ba khái niệm khác nhau

| Khái niệm | Được định nghĩa ở đâu? | Ví dụ | Ý nghĩa |
|---|---|---|---|
| **OAuth scope** | Authorization Server và hợp đồng OAuth 2.0 | `orders:read` | Một chuỗi biểu thị phạm vi ủy quyền mà token được cấp. |
| **GrantedAuthority** | Mô hình phân quyền bên trong Spring Security | `SCOPE_orders:read` | Một chuỗi quyền gắn vào `Authentication` để kiểm tra quyền truy cập. |
| **Role** | Chính sách phân quyền của ứng dụng | `ROLE_ADMIN` | Thường biểu thị vai trò nghiệp vụ hoặc quản trị. Spring dùng quy ước `ROLE_` với `hasRole`. |
| **Ownership/tenant policy** | Logic dữ liệu và nghiệp vụ của Resource Server | “Đơn hàng thuộc user-123 ở tenant-7” | Ràng buộc quyền đối với **một bản ghi cụ thể**, không thể thay bằng scope tổng quát. |

**Scope là dữ liệu trong token; authority là cách Spring Security diễn đạt kết quả ánh xạ để phân quyền.** Bản thân tiền tố `SCOPE_` không phải thành phần bắt buộc của đặc tả OAuth 2.0. Authorization Server có thể phát scope `orders:read`; tiền tố được Resource Server thêm vào khi tạo `GrantedAuthority`. Việc đổi prefix **không sửa token đã phát hành**.

Một scope có thể biểu thị quyền rộng như đọc đơn hàng. Tuy nhiên nó chưa chứng minh người gọi được đọc **tất cả** đơn hàng. API vẫn phải kiểm tra chủ sở hữu, tenant, trạng thái đối tượng, chính sách nghiệp vụ hoặc các ràng buộc khác.

### Vì sao cần tiền tố?

Đặt tiền tố giúp tách các namespace quyền:

~~~text
SCOPE_orders:read    <- Scope được token cấp
ROLE_ADMIN           <- Role nghiệp vụ của ứng dụng
PERM_orders:approve  <- Permission riêng nếu hệ thống tự định nghĩa
~~~

Cùng một từ `admin` có thể xuất hiện trong OAuth scope hoặc role nhưng không đương nhiên có cùng ý nghĩa. Nếu không phân biệt nguồn và semantics, một token có `scope=admin` có thể bị ánh xạ nhầm thành quyền quản trị không mong muốn.

### Lưu ý về chữ hoa/chữ thường

So khớp authority là so khớp chuỗi. Theo quy tắc phổ biến, `SCOPE_orders:read`, `SCOPE_Orders:Read` và `ROLE_orders:read` là ba authority khác nhau. Không tự đổi chữ hoa/chữ thường hoặc thay dấu phân cách khi chưa thống nhất hợp đồng với Authorization Server.

## 3. `SCOPE_` được tạo tại bước nào?

Trong Spring Security Servlet Resource Server, request có thể đi theo luồng:

~~~mermaid
sequenceDiagram
    participant C as HTTP Client
    participant F as BearerTokenAuthenticationFilter
    participant D as JwtDecoder
    participant V as JwtAuthenticationProvider
    participant M as JwtAuthenticationConverter
    participant H as SecurityContext
    participant A as AuthorizationFilter
    participant S as Controller / Service

    C->>F: Authorization: Bearer access-token
    F->>V: Xác thực token
    V->>D: Giải mã, xác minh chữ ký và validators
    D-->>V: Jwt đã xác thực
    V->>M: convert(jwt)
    M->>M: Ánh xạ scope/scp thành SCOPE_ authorities
    M-->>V: JwtAuthenticationToken
    V-->>F: Authentication đã xác thực
    F->>H: Lưu Authentication cho request hiện tại
    F->>A: Tiếp tục filter chain
    A->>H: Đọc authorities
    alt Có authority theo quy tắc
        A->>S: Cho phép xử lý
    else Thiếu authority
        A-->>C: 403 Forbidden
    end
~~~

Mỗi thành phần có một trách nhiệm riêng:

- **`BearerTokenAuthenticationFilter`:** trích Bearer token từ request theo cấu hình.
- **`JwtDecoder`:** xác minh chữ ký và những validator đang được cấu hình, ví dụ issuer, thời hạn, audience; một số validator như audience cần cấu hình bổ sung tùy phiên bản/ứng dụng.
- **`JwtAuthenticationProvider`:** dùng decoder và converter để tạo kết quả xác thực.
- **`JwtAuthenticationConverter`:** chuyển đối tượng `Jwt` đã được decoder xử lý thành `AbstractAuthenticationToken`, mặc định thường là `JwtAuthenticationToken`.
- **`JwtGrantedAuthoritiesConverter`:** mặc định được converter phía trên dùng để lấy scope và tạo các `GrantedAuthority` có tiền tố `SCOPE_`.
- **`SecurityContext`:** giữ `Authentication` cho quá trình xử lý request hiện tại.
- **Phân quyền:** `hasAuthority`, `hasAnyAuthority`, `@PreAuthorize` hoặc một `AuthorizationManager` quyết định endpoint/operation có được phép hay không.

Tại thời điểm `Authentication` đã được tạo, `getAuthorities()` trả về các authority **đã ánh xạ**. Trong mô hình Spring Security mặc định, đối tượng `Jwt` thường là `principal` và `Authentication.getName()` mặc định dùng `sub`, trừ khi ứng dụng cấu hình khác.

**Ranh giới tin cậy:** bộ chuyển đổi authority không có nhiệm vụ xác minh chữ ký. Nếu ứng dụng chỉ Base64-decode một JWT rồi tự lấy claim `scope` đưa vào `SecurityContextHolder`, attacker có thể sửa scope để tự cấp quyền. Phải dựa vào luồng xác thực token đáng tin và không tạo authority từ request header hoặc body do client tự khai.

## 4. Quy tắc ánh xạ mặc định của JWT

Spring Security thường đọc claim chứa scope theo những tên quen thuộc là `scope` và `scp`, rồi thêm tiền tố mặc định `SCOPE_` cho từng giá trị. Claim `scope` thường là chuỗi scope cách nhau bằng khoảng trắng; `scp` thường là danh sách các chuỗi trong một số Authorization Server.

| Dữ liệu trong JWT đã được xác thực | Authorities thường tạo ra |
|---|---|
| `"scope": "orders:read orders:write"` | `SCOPE_orders:read`, `SCOPE_orders:write` |
| `"scope": "profile"` | `SCOPE_profile` |
| `"scp": ["catalog.read", "catalog.write"]` | `SCOPE_catalog.read`, `SCOPE_catalog.write` |
| Không có `scope`/`scp` phù hợp | Không có scope authorities từ converter mặc định. |
| `"roles": ["ADMIN"]` nhưng không có custom converter | Không tự tạo `ROLE_ADMIN`. |

Nếu **cả `scope` lẫn `scp` đều có mặt**, không nên mặc định Spring sẽ lấy hợp hai claim; converter có quy tắc tìm claim được cấu hình. Hãy xác nhận claim đang dùng từ issuer và kiểm thử ánh xạ thực tế. Không tin vào tên claim tự phát minh như `permissions`, `roles`, `realm_access` nếu chưa cấu hình converter tương ứng.

Ví dụ:

~~~java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

// Trong request đã xác thực bằng access token:
for (GrantedAuthority authority : authentication.getAuthorities()) {
    System.out.println(authority.getAuthority());
}
~~~

Đoạn mã này chỉ minh họa API truy xuất quyền. Trong ứng dụng production, không log token gốc hoặc toàn bộ principal nếu chúng chứa thông tin nhạy cảm. Có thể log tên loại quyết định và correlation ID để theo dõi thay vì công bố credential.

### Scope nào được quyền xuất hiện trong token?

Authorization Server phải kiểm tra rằng scope được cấp nằm trong quyền client được đăng ký và giới hạn người dùng/policy/consent phù hợp. Resource Server phải kiểm **token phát hành hợp lệ cho API của mình** và sau đó kiểm quyền. Việc ánh xạ `SCOPE_` chỉ sử dụng scope **đã có** trong access token; không tự xác minh người dùng đã consent hay client được đăng ký quyền đó.

## 5. Dùng `hasAuthority` đúng cách

Giả sử API đơn hàng có hai quyền:
- `orders:read`: đọc danh sách/chi tiết đơn hàng đủ điều kiện.
- `orders:write`: tạo hoặc chỉnh sửa đơn hàng đủ điều kiện.

Cấu hình Spring Security 6 cho một API nhận Bearer token trong header:

~~~java
@Configuration
@EnableMethodSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Đây là ví dụ cho **API thuần Bearer token ở header**, không dùng cookie để trình duyệt tự động xác thực. Bởi vậy cấu hình minh họa tắt CSRF. Nếu API nhận cookie/session hoặc credential trình duyệt tự gắn vào request, cần thiết kế chống CSRF phù hợp; không sao chép `csrf.disable()` khi điều kiện không đúng.

Một ví dụ cấu hình issuer:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test
~~~

Cấu hình thật còn phải bảo đảm **audience phù hợp với API này**, thuật toán xác minh được cho phép, vòng đời token và chính sách thu hồi. Việc thêm một rule `hasAuthority` không thay thế các bước này. Nếu Resource Server chỉ có `issuer-uri`, đừng mặc định ứng dụng đã tự kiểm tất cả các audience mà nghiệp vụ yêu cầu; cần validator hoặc cơ chế cấu hình audience của phiên bản đang sử dụng.

Trong Java/Spring Security:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders:read')")
public OrderDto findOrder(String orderId) {
    return orderService.getOrder(orderId);
}
~~~

`@PreAuthorize` cần bật method security, ví dụ `@EnableMethodSecurity` và để method được gọi qua Spring proxy theo mô hình đang dùng. Một lời gọi nội bộ trực tiếp trong cùng bean có thể bỏ qua advice ở mô hình proxy thường gặp; kiểm tra bảo mật tại filter chain và business service theo thiết kế, không dựa vào annotation sai vị trí.

### Chọn `hasAuthority` hay `hasAnyAuthority`?

~~~java
// Cần đúng một quyền:
.hasAuthority("SCOPE_orders:read")

// Cho phép nếu có ít nhất một quyền:
.hasAnyAuthority("SCOPE_orders:read", "SCOPE_orders:admin")
~~~

`hasAnyAuthority` mang ý nghĩa **OR**, không có nghĩa người gọi phải có cả hai quyền. Nếu thao tác cần đồng thời hai quyền, chính sách phải dùng biểu thức/AuthorizationManager thể hiện **AND**, ví dụ trong method security:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders:read') and hasAuthority('SCOPE_audit:read')")
public AuditDto readOrderAudit(String orderId) {
    return auditService.load(orderId);
}
~~~

Dù authority hợp lệ, service vẫn cần kiểm quyền sở hữu đơn hàng hoặc tenant trước khi trả dữ liệu. Trong nhiều API, để tránh BOLA/IDOR, scope cho đọc đơn hàng chỉ là điều kiện **cần**, chưa phải điều kiện **đủ**.

## 6. Vì sao `hasRole` không tự hiểu `SCOPE_`?

Spring Security có quy ước riêng cho role: `hasRole("ADMIN")` thường kiểm authority `ROLE_ADMIN`, vì nó thêm tiền tố role mặc định `ROLE_`. Ngược lại, `hasAuthority("SCOPE_admin")` kiểm **đúng chuỗi** được chỉ định.

| Kiểm tra | Authority được tìm theo quy ước thông thường | Token chỉ có `SCOPE_admin` thì sao? |
|---|---|---|
| `hasAuthority("SCOPE_admin")` | `SCOPE_admin` | Có thể PASS nếu token hợp lệ và mapping chính xác. |
| `hasAuthority("ROLE_ADMIN")` | `ROLE_ADMIN` | FAIL nếu chỉ có `SCOPE_admin`. |
| `hasRole("ADMIN")` | `ROLE_ADMIN` | FAIL nếu chỉ có `SCOPE_admin`. |
| `hasRole("SCOPE_admin")` | Không phải cách diễn đạt scope hợp lệ trong quy ước role thông thường. | Không dùng để kiểm scope. |

Ví dụ một JWT mang `"scope": "admin"` không tự biến người gọi thành admin nghiệp vụ:

~~~text
scope claim:  "admin"
    |
    +--> GrantedAuthority("SCOPE_admin")

hasRole("ADMIN")                  -> kiểm ROLE_ADMIN -> không khớp
hasAuthority("SCOPE_admin")       -> kiểm SCOPE_admin -> khớp
~~~

Không nên “sửa lỗi” bằng cách tự đổi tất cả scope thành `ROLE_`. Điều đó đánh đồng quyền được ủy quyền cho một client với vai trò nội bộ của người dùng. Nếu API cần role, phải xác định **nguồn role đáng tin**, semantics role, namespace đúng resource và cách ánh xạ riêng.

Trong hệ thống nhiều issuer/tenant, claim `roles=ADMIN` của một issuer có thể khác hoàn toàn `ADMIN` của issuer khác. Việc thêm `ROLE_` không làm claim trở nên đáng tin nếu token không có audience, issuer và policy phù hợp.

## 7. Tùy chỉnh tiền tố với `JwtGrantedAuthoritiesConverter`

Thông thường, hãy giữ `SCOPE_` và dùng `hasAuthority("SCOPE_...")` để mọi service thống nhất. Tuy nhiên, một API có thể cần claim riêng như `permissions` hoặc muốn đổi prefix theo hợp đồng nội bộ.

### 7.1. Chỉ thay prefix cho scope

~~~java
@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtGrantedAuthoritiesConverter authorities =
        new JwtGrantedAuthoritiesConverter();

    authorities.setAuthorityPrefix("PERMISSION_");

    JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();
    converter.setJwtGrantedAuthoritiesConverter(authorities);
    return converter;
}
~~~

Khi converter này được gắn vào Resource Server, scope `orders:read` sẽ thành `PERMISSION_orders:read`. Khi đó:

~~~java
.hasAuthority("PERMISSION_orders:read")  // Khớp với converter mới
.hasAuthority("SCOPE_orders:read")       // Không còn khớp
~~~

Ví dụ trên **không thay đổi chuỗi scope trong JWT**. Nó chỉ thay tên authority trong ứng dụng. Phải sửa tất cả chỗ kiểm quyền tương ứng khi đổi prefix: filter chain, method security, tests, policy service và tài liệu.

Gắn converter vào cấu hình JWT:

~~~java
.oauth2ResourceServer(oauth -> oauth
    .jwt(jwt -> jwt.jwtAuthenticationConverter(jwtAuthenticationConverter())))
~~~

Đoạn này **thay thế** dòng `.jwt(Customizer.withDefaults())` trong cấu hình trước, không thêm một cấu hình thứ hai trùng nhau vào cùng filter chain.

### 7.2. Đọc claim khác tên mặc định

Nếu issuer đã được kiểm soát phát:

~~~json
{
  "sub": "staff-7",
  "permissions": ["orders:approve", "orders:refund"]
}
~~~

thì có thể dùng:

~~~java
JwtGrantedAuthoritiesConverter permissions =
    new JwtGrantedAuthoritiesConverter();
permissions.setAuthoritiesClaimName("permissions");
permissions.setAuthorityPrefix("PERM_");
~~~

Ánh xạ kỳ vọng là `PERM_orders:approve` và `PERM_orders:refund`. Nhưng nếu **chỉ** dùng converter này, những scope từ `scope`/`scp` có thể không còn được ánh xạ; cần quyết định rõ việc giữ hay kết hợp cả hai nguồn.

### 7.3. Kết hợp scope chuẩn và permissions riêng

Ví dụ một hệ thống muốn giữ scope OAuth theo namespace `SCOPE_`, đồng thời ánh xạ claim `permissions` do **cùng issuer đáng tin** phát sang `PERM_`:

~~~java
@Bean
JwtAuthenticationConverter combinedConverter() {
    JwtGrantedAuthoritiesConverter scopes =
        new JwtGrantedAuthoritiesConverter();

    JwtGrantedAuthoritiesConverter permissions =
        new JwtGrantedAuthoritiesConverter();
    permissions.setAuthoritiesClaimName("permissions");
    permissions.setAuthorityPrefix("PERM_");

    JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();

    converter.setJwtGrantedAuthoritiesConverter(jwt -> {
        List<GrantedAuthority> granted =
            new ArrayList<>(scopes.convert(jwt));
        granted.addAll(permissions.convert(jwt));
        return granted;
    });

    return converter;
}
~~~

Sau đó cấu hình:

~~~java
.oauth2ResourceServer(oauth -> oauth
    .jwt(jwt -> jwt.jwtAuthenticationConverter(combinedConverter())))
~~~

Với JWT hợp lệ chứa:

~~~json
{
  "scope": "orders:read",
  "permissions": ["orders:approve"]
}
~~~

kết quả là:

~~~text
SCOPE_orders:read
PERM_orders:approve
~~~

Ở đây `permissions` là **claim tùy chỉnh**. Authorization Server và Resource Server phải thống nhất ai được cấp nó, khi nào và cho audience nào. Không tự lấy `permissions` từ request body/header do client gửi rồi dùng như authority.

Đoạn code minh họa dựa trên `JwtGrantedAuthoritiesConverter`, `JwtAuthenticationConverter`, `GrantedAuthority`, `List` và `ArrayList` của Spring Security/JDK; imports được lược bỏ cho gọn. Trong ứng dụng thật, kiểm tra cấu trúc claim mà issuer bảo đảm, xử lý trường hợp null hoặc dữ liệu sai kiểu theo contract và có tests cho converter tùy chỉnh.

### 7.4. Không cấu hình claim một cách vô thức

Giả sử issuer thực tế dùng `scp` nhưng đội phát triển gọi:

~~~java
converter.setAuthoritiesClaimName("scope");
~~~

Converter được buộc đọc `scope` và có thể bỏ qua `scp`. Hậu quả là mọi endpoint yêu cầu `SCOPE_...` đều bị từ chối dù token hợp lệ và có scope trong `scp`. Trước khi ghi đè tên claim, hãy xác nhận cấu trúc token thực tế và viết test cho cả trường hợp có/thiếu claim.

Nếu issuer dùng dấu phân cách scope khác chuẩn, một số phiên bản Spring Security cung cấp cấu hình delimiter cho `JwtGrantedAuthoritiesConverter`. Chỉ tùy chỉnh khi hợp đồng token yêu cầu và phiên bản thư viện hỗ trợ; ưu tiên đầu ra scope theo chuẩn OAuth khi có thể.

## 8. `SCOPE_` với opaque access token

JWT có thể mang scope trực tiếp trong claims. Với **opaque access token**, Resource Server thường gọi **token introspection** tại Authorization Server để xác minh token đang `active` và lấy metadata, bao gồm scope nếu có.

Ví dụ introspection response:

~~~json
{
  "active": true,
  "client_id": "web-portal",
  "sub": "user-123",
  "scope": "orders:read orders:write",
  "aud": ["orders-api"],
  "exp": 1893456000
}
~~~

Trong cấu hình Spring Security opaque-token Resource Server phổ biến, các scope mà introspector trả về có thể được chuyển thành authorities cùng quy ước `SCOPE_...`. Sau khi xác thực, `Authentication` thường là `BearerTokenAuthentication` thay vì `JwtAuthenticationToken`.

Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.test/oauth2/introspect
          client-id: orders-api-introspector
          client-secret: YOUR_SECRET_FROM_SECURE_CONFIGURATION
~~~

`client-secret` ở đây là chỗ giữ giá trị minh họa; trong production phải dùng secret manager/biến môi trường và tránh commit secret thật. Để tránh ghi secret trong YAML, có thể cấu hình giá trị qua môi trường triển khai.

Điểm cần nhớ:

- `SCOPE_orders:read` vẫn là **authority phía Resource Server**, dù nguồn scope là introspection response thay vì JWT claims.
- Không áp dụng `JwtGrantedAuthoritiesConverter` một cách mù quáng cho opaque token; nếu cần tùy chỉnh, dùng extension point ở introspector/provider thích hợp.
- Introspection response `active=true` không tự động thay thế policy audience, issuer, quyền client/tenant hoặc ownership theo yêu cầu API.
- Caching introspection có thể ảnh hưởng tốc độ phát hiện token bị thu hồi. `SCOPE_` không quyết định hiệu lực thu hồi.

**JWT, opaque token là kiểu biểu diễn access token; access token, refresh token là vai trò của token.** Resource Server dùng access token để bảo vệ API. Không nhận **refresh token** hoặc **OIDC ID token** như access token chỉ vì trong đó xuất hiện claim `scope` và bạn có thể ánh xạ được `SCOPE_`.

## 9. Ví dụ xuyên suốt: token hợp lệ nhưng chưa đủ quyền

Một công ty vận hành hai API: `orders-api` và `billing-api`. Client nhận JWT:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "employee-17",
  "aud": ["orders-api"],
  "scope": "orders:read",
  "exp": 1893456000
}
~~~

Các trường hợp:

| Request | Kết quả nên xảy ra | Lý do |
|---|---|---|
| `GET /api/orders/42` trên `orders-api`; đơn #42 thuộc phạm vi truy cập của nhân viên | Có thể trả 200. | Token đúng audience, có `SCOPE_orders:read` và qua kiểm tra ownership. |
| `POST /api/orders/42` trên `orders-api` | 403. | Thiếu `SCOPE_orders:write`. |
| `GET /api/orders/99` trên `orders-api`; đơn #99 của tenant khác | 403 hoặc 404 tùy policy. | Scope đọc không cho phép xem dữ liệu tenant khác. |
| `GET /api/invoices` trên `billing-api` | 401 do token không hợp lệ cho API này khi kiểm `aud`. | `SCOPE_orders:read` không hợp thức hóa audience sai. |
| Dùng JWT hết hạn hoặc bị từ chối do issuer/chữ ký sai | 401. | Không tạo authentication hợp lệ. |
| Dùng JWT còn hạn nhưng đã bị thu hồi và API chỉ kiểm offline chữ ký/`exp` | Có nguy cơ vẫn được chấp nhận cho tới khi hết hạn. | Cần cơ chế thu hồi phù hợp, độc lập với ánh xạ `SCOPE_`. |

**HTTP 401** thường dành cho thiếu hoặc không hợp lệ credential. **HTTP 403** thường xảy ra khi credential đã xác thực nhưng không có quyền theo policy. Trong Bearer scheme, response có thể dùng `WWW-Authenticate` với `invalid_token` hoặc `insufficient_scope` theo trường hợp; cấu hình handler và policy thực tế quyết định thông tin phản hồi.

Một cách phân ranh giới:

~~~mermaid
flowchart TD
    A[Request có Bearer token] --> B{Token hợp lệ? chữ ký, issuer, exp, aud}
    B -->|Không| C[401 - Từ chối xác thực]
    B -->|Có| D[Map scope/scp -> SCOPE_ authorities]
    D --> E[Đặt Authentication vào SecurityContext]
    E --> F{Đủ authority cho hành động?}
    F -->|Không| G[403 - Thiếu quyền]
    F -->|Có| H{Được phép với bản ghi/tenant?}
    H -->|Không| I[403 hoặc 404 theo chính sách]
    H -->|Có| J[Thực hiện nghiệp vụ]
~~~

## 10. Lỗi thường gặp liên quan tiền tố `SCOPE_`

### Lỗi 1: Kiểm `hasAuthority("orders:read")` trong khi converter thêm `SCOPE_`

Token có `scope=orders:read`; converter tạo `SCOPE_orders:read`, còn rule tìm `orders:read`. Kết quả thường là 403 dù JWT hợp lệ.

**Cách xử lý:** dùng `hasAuthority("SCOPE_orders:read")` hoặc cố ý thay cấu hình converter và cập nhật toàn bộ rule liên quan.

### Lỗi 2: Viết `hasRole("orders:read")`

`hasRole` dùng quy ước `ROLE_`, không tự chuyển thành `SCOPE_`. Đây là nhầm lẫn giữa role và OAuth scope.

**Cách xử lý:** dùng `hasAuthority("SCOPE_orders:read")` để kiểm scope, giữ `hasRole` cho role thực sự nếu ứng dụng định nghĩa.

### Lỗi 3: Chỉ sửa prefix ở một nơi

Đội phát triển chuyển prefix converter từ `SCOPE_` sang `PERM_` nhưng controller, `@PreAuthorize` và tests vẫn kiểm `SCOPE_`, dẫn đến 403 hàng loạt hoặc bỏ sót rule.

**Cách xử lý:** coi mapping và rule là một hợp đồng; thực hiện cập nhật đồng bộ và test tích hợp.

### Lỗi 4: Tưởng role claim tự động tạo `ROLE_ADMIN`

JWT chứa `roles=["ADMIN"]` nhưng converter mặc định thường chỉ đọc scope/scp. Hệ thống không có `ROLE_ADMIN` như mong đợi.

**Cách xử lý:** chỉ thêm converter role từ nguồn đã được tin cậy và đúng audience. Không mặc nhiên nâng `SCOPE_admin` thành `ROLE_ADMIN`.

### Lỗi 5: Quên kiểm `aud` vì scope đã khớp

Token hợp lệ về chữ ký và `scope=orders:read` nhưng được cấp cho API khác. Nếu Resource Server không kiểm audience, token bị dùng sai mục đích.

**Cách xử lý:** cấu hình validator audience theo API; xác thực token trước, phân quyền tiếp theo.

### Lỗi 6: Tin rằng scope đồng nghĩa quyền xem mọi đối tượng

`SCOPE_orders:read` không cho phép đọc đơn hàng của mọi tenant. Bỏ kiểm tra tài nguyên cụ thể tạo lỗ hổng **Broken Object Level Authorization (BOLA)** hoặc IDOR.

**Cách xử lý:** dùng scope để chặn lớp chức năng và policy ownership/tenant để chặn lớp đối tượng. Từ chối theo nguyên tắc least privilege.

### Lỗi 7: Tạo authorities từ token chưa được xác minh

Giải mã JWT bằng Base64, lấy scope rồi tạo `UsernamePasswordAuthenticationToken` có authorities. Attacker có thể tự sửa scope và cấp quyền cao hơn.

**Cách xử lý:** để `JwtDecoder`/provider xác minh token và bộ claims bắt buộc; không dùng decoder JSON thông thường thay verification.

### Lỗi 8: Nhầm access token với ID token hoặc refresh token

ID token của OIDC chủ yếu phục vụ client xác minh kết quả đăng nhập; refresh token dùng xin token mới. Cả hai không trở thành access token của API chỉ vì có claim tương tự scope.

**Cách xử lý:** chỉ chấp nhận token đúng loại, đúng issuer, audience, mục đích và chính sách Resource Server.

### Lỗi 9: Nhầm tiền tố với cơ chế chống replay hoặc thu hồi

`SCOPE_` không buộc token chỉ dùng một lần; token bị đánh cắp còn hiệu lực có thể tiếp tục được gửi. JWT cũng không tự vô hiệu khi người dùng logout.

**Cách xử lý:** giới hạn thời hạn token, bảo vệ credential, dùng mTLS/DPoP khi phù hợp, kiểm tra thu hồi và rotation/reuse detection cho refresh token theo yêu cầu hệ thống. Đặt prefix chỉ là mapping phân quyền.

### Lỗi 10: Bật method security nhưng bỏ qua đường gọi thực tế

`@PreAuthorize` có thể không được áp dụng nếu gọi self-invocation trong cùng bean theo mô hình proxy thông thường hoặc chạy qua lớp không được Spring quản lý.

**Cách xử lý:** đặt boundary bảo mật ở lớp được Spring quản lý, kiểm tra route + method security và có integration test qua đường gọi thật.

## 11. Kiểm thử scope mapping và phân quyền

Cần tách **test logic authority** khỏi **test xác thực token thực sự**.

### 11.1. Unit test converter mặc định

Ví dụ với Spring Security, có thể tự dựng `Jwt` trong test để xác minh mapping:

~~~java
Jwt jwt = Jwt.withTokenValue("fake-jwt-for-test")
    .header("alg", "none")
    .claim("sub", "user-123")
    .claim("scope", "orders:read orders:write")
    .build();

JwtGrantedAuthoritiesConverter converter =
    new JwtGrantedAuthoritiesConverter();

Collection<GrantedAuthority> authorities = converter.convert(jwt);

assertTrue(authorities.contains(
    new SimpleGrantedAuthority("SCOPE_orders:read")));
assertTrue(authorities.contains(
    new SimpleGrantedAuthority("SCOPE_orders:write")));
~~~

Token giả trong test converter chỉ là fixture **không được xác thực**; cách dựng `Jwt` như trên phù hợp kiểm ánh xạ đơn vị, **không có giá trị** chứng minh token với `alg=none` được chấp nhận an toàn bởi Resource Server. Trong production, phải cấu hình decoder chỉ chấp nhận thuật toán và khóa tin cậy.

### 11.2. Kiểm tra endpoint bằng Spring Security Test

Với MockMvc và `spring-security-test`:

~~~java
mockMvc.perform(get("/api/orders/42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders:read"))))
    .andExpect(status().isOk());

mockMvc.perform(get("/api/orders/42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders:write"))))
    .andExpect(status().isForbidden());
~~~

Test này giả lập `Authentication` với authorities, phù hợp để xác minh **rule phân quyền**. Endpoint phải có fixture dữ liệu/owner cho đường thành công; `jwt()` test postprocessor **không** xác minh chữ ký, issuer, audience, expiration hay cơ chế thu hồi thật.

Nếu muốn test converter trong một integration test, có thể cấu hình JWT claim `scope` qua postprocessor cùng cơ chế converter tương ứng hoặc gọi trực tiếp converter; tuyệt đối không xem việc ghi thủ công một `GrantedAuthority` vào fixture là bằng chứng mapping production hoạt động.

### 11.3. Test token đầy đủ qua filter chain

Một bộ test tích hợp cần chứng minh:

| Tình huống | Kỳ vọng |
|---|---|
| JWT được ký hợp lệ, `iss` đúng, `aud` đúng, scope đúng | Decoder chấp nhận; authentication có `SCOPE_...`; rule cho phép khi quyền đối tượng phù hợp. |
| Scope hợp lệ nhưng `aud` là API khác | Từ chối xác thực (thường 401), không tạo authority cho request. |
| JWT sai chữ ký, `exp` đã qua hoặc `nbf` chưa tới | Token bị từ chối (thường 401). |
| JWT hợp lệ nhưng không có scope cần thiết | Xác thực thành công nhưng rule từ chối (thường 403). |
| JWT dùng `scp` thay `scope` | Converter ánh xạ đúng định dạng đã cam kết. |
| Token có scope đúng nhưng thiếu ownership | Policy đối tượng từ chối (403/404). |
| Prefix converter đổi nhưng rule chưa đổi | Test phát hiện 403; sửa đồng bộ hợp đồng quyền. |
| Opaque token introspection `active=false` | Không cấp authentication hợp lệ. |
| Token đã bị thu hồi theo chính sách bắt buộc | API từ chối bằng cơ chế thu hồi đã triển khai. |
| Client gửi ID token hoặc refresh token thay access token | API từ chối token không đúng mục đích. |

Tạo token kiểm thử có ký và issuer/JWKS test tin cậy để đi qua `JwtDecoder` thật, hoặc dùng test server cho introspection. Sau đó kiểm cả việc tạo authorities, bảo vệ endpoint, kiểm scope và kiểm business policy. **MockJwt không thay thế security integration test**.

## 12. Bài tập tình huống

### Tình huống A: 403 dù token có scope

Token:

~~~json
{
  "sub": "alice",
  "aud": ["orders-api"],
  "scope": "orders:read"
}
~~~

Cấu hình:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("orders:read")
~~~

Hỏi: Vì sao request có thể bị trả 403 sau khi token được xác thực? Cần sửa một dòng như thế nào? Nếu đổi converter thành prefix rỗng để “sửa”, những rủi ro nhất quán nào phát sinh?

**Gợi ý:** default converter tạo `SCOPE_orders:read`, nhưng rule tìm `orders:read`. Sửa rule theo authority thực tế được ánh xạ. Thay prefix cũng được nếu có chủ đích, nhưng phải cập nhật và kiểm thử toàn bộ policy.

### Tình huống B: token chỉ dành cho Catalog API

Client gửi JWT có scope `orders:read` và chữ ký đúng, nhưng `aud=["catalog-api"]` đến `orders-api`. Hỏi: Resource Server có thể chỉ dựa vào `SCOPE_orders:read` để cho phép truy cập không? Thành phần nào phải từ chối token?

**Gợi ý:** không. Token sai audience phải bị từ chối tại lớp xác thực/validator trước khi authority có giá trị trong quyết định phân quyền.

### Tình huống C: role và scope đụng tên

JWT chứa:

~~~json
{
  "scope": "admin",
  "roles": ["VIEWER"]
}
~~~

API bảo vệ bằng `hasRole("ADMIN")`. Hỏi: converter mặc định tạo quyền nào? Lời gọi có đi qua không? Có nên tự động chuyển `SCOPE_admin` thành `ROLE_ADMIN`?

**Gợi ý:** converter scope mặc định tạo `SCOPE_admin`; `hasRole("ADMIN")` kiểm `ROLE_ADMIN`. Tự động chuyển sang role có thể cấp sai quyền quản trị, trừ khi đó là policy đã được thẩm định và claim đúng ngữ cảnh.

## 13. Checklist trước khi triển khai

- **Issuer và token:** access token được xác minh bằng thuật toán/khóa tin cậy, kiểm `iss`, `exp`/`nbf` và `aud` đúng API chưa?
- **Claim scope:** issuer dùng `scope` hay `scp`, định dạng chuỗi hay danh sách, có chính sách case-sensitive thống nhất chưa?
- **Prefix:** converter đang tạo `SCOPE_` hay tên khác? Filter chain, method security và tests đã cùng một contract chưa?
- **Role:** những quyền `ROLE_` lấy từ đâu, có khác biệt rõ với `SCOPE_` không?
- **Authorization:** có kiểm ownership/tenant và rule theo từng hành động, không chỉ kiểm scope cấp API không?
- **Token lifecycle:** có phân biệt access/refresh/ID token, TTL, revocation, đánh cắp và khả năng replay không?
- **Kiểm thử:** đã có test converter, 401 khi token sai, 403 khi thiếu quyền, kiểm audience và kiểm đối tượng chưa?

### Tự kiểm tra

1. Vì sao một JWT chứa `scope=orders:read` thường tạo `SCOPE_orders:read` nhưng không tạo `ROLE_orders:read`?
2. `hasRole("ADMIN")` khác `hasAuthority("SCOPE_admin")` thế nào?
3. Khi issuer dùng `scp` thay `scope`, việc gọi `setAuthoritiesClaimName("scope")` có thể gây ra điều gì?
4. Tại sao token đúng scope nhưng sai audience vẫn phải bị từ chối?
5. Vì sao test `with(jwt().authorities(...))` không chứng minh JWT thật đã được xác thực?
6. Đổi prefix từ `SCOPE_` sang `PERM_` cần kiểm tra những tầng nào trong ứng dụng?

**Ghi nhớ:** `SCOPE_` là **quy ước ánh xạ OAuth scope thành Spring Security GrantedAuthority**. Nó giúp viết rule phân quyền rõ ràng, nhưng chỉ có ý nghĩa sau khi access token đã được kiểm chứng đầy đủ và đúng audience. Scope không thay thế vai trò nội bộ, quyền sở hữu dữ liệu hay cơ chế quản lý vòng đời/thu hồi token.
