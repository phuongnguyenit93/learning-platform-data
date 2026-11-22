# Chuyển dữ liệu token thành Authentication và GrantedAuthority

Trong **Spring Security OAuth 2.0 Resource Server** chạy trên **Servlet** (thường kết hợp Spring MVC), một HTTP request có Bearer access token chỉ trở thành request của người dùng hoặc client **đã được xác thực** sau khi Spring Security kiểm tra token và tạo một đối tượng `Authentication` hợp lệ. Các quyền mà ứng dụng sử dụng để quyết định có cho phép gọi API hay không được biểu diễn qua các đối tượng `GrantedAuthority` nằm bên trong `Authentication`.

Điểm cốt lõi của bài học là hiểu **dữ liệu token đi qua những lớp nào, biến thành principal và authorities ra sao**, cũng như cách thay đổi quy tắc ánh xạ `scope`, `scp` hoặc claim quyền riêng mà vẫn giữ ranh giới giữa **xác thực** và **phân quyền**.

Ví dụ trong bài dùng Java, Spring Boot và cú pháp lambda DSL quen thuộc của Spring Security. Các issuer, audience, token và ID đều là dữ liệu giả lập; API thật phải dùng hợp đồng token, danh sách issuer tin cậy và chính sách quyền đã được thống nhất.

## 1. Bốn khái niệm cần phân biệt

| Khái niệm | Đại diện cho điều gì? | Ví dụ |
|---|---|---|
| **Bearer access token** | Credential client trình cho API qua HTTP; chưa thể tin cậy trước khi xác thực | `Authorization: Bearer eyJ...` hoặc token opaque |
| **Principal** | Chủ thể đã được xác định từ credential hợp lệ; có thể là người dùng hoặc service client | JWT `sub = user-123` |
| **Authentication** | Đối tượng Spring Security mô tả principal, credential, trạng thái xác thực, authorities và chi tiết liên quan | `JwtAuthenticationToken`, `BearerTokenAuthentication` |
| **GrantedAuthority** | Một quyền theo dạng chuỗi được đưa vào `Authentication` để các bộ phận authorization kiểm tra | `SCOPE_orders.read`, `ROLE_ADMIN` |

### Authentication khác Authorization

**Authentication (xác thực)** hỏi: *Token có hợp lệ và nó đại diện cho principal nào?* **Authorization (phân quyền)** hỏi: *Principal đã xác thực có được thực hiện hành động cụ thể trên tài nguyên này không?*

~~~text
HTTP request:
    Authorization: Bearer <access_token>
                |
                v
     Kiểm tra access token
       (authentication)
                |
                v
    Authentication object
      - principal
      - authorities
      - authenticated = true
                |
                v
       Kiểm tra policy
       (authorization)
                |
                v
        Controller/Service
~~~

**`GrantedAuthority` không tự chứng minh danh tính hay chữ ký token**. Nó là dữ liệu quyền **sau khi** thông tin nguồn đã được tin cậy. Một claim `roles` đọc được trong JSON chưa thể trở thành quyền hợp lệ nếu token chưa vượt qua các kiểm tra bắt buộc.

## 2. Vị trí chuyển đổi trong Servlet Security Filter Chain

Giả sử client gửi:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer <ACCESS_TOKEN>
Accept: application/json
~~~

Khi ứng dụng có `SecurityFilterChain` với `oauth2ResourceServer(...)`, đường xử lý phổ biến:

~~~mermaid
flowchart TD
    A["Servlet HTTP request"] --> B["DelegatingFilterProxy"]
    B --> C["FilterChainProxy → chọn SecurityFilterChain"]
    C --> D["BearerTokenAuthenticationFilter"]
    D --> E["BearerTokenAuthenticationToken (chưa xác thực)"]
    E --> F["AuthenticationManager / ProviderManager"]
    F --> G{"Cơ chế Resource Server"}
    G -->|"JWT"| H["JwtAuthenticationProvider → JwtDecoder"]
    G -->|"Opaque token"| I["OpaqueTokenAuthenticationProvider → OpaqueTokenIntrospector"]
    H --> J["JwtAuthenticationConverter"]
    I --> K["OAuth2AuthenticatedPrincipal + authorities"]
    J --> L["JwtAuthenticationToken"]
    K --> M["BearerTokenAuthentication"]
    L --> N["SecurityContextHolder"]
    M --> N
    N --> O["AuthorizationFilter / Access Rules"]
    O --> P["DispatcherServlet → Controller"]
~~~

Các bước cụ thể:

1. Servlet container đưa request vào chuỗi filter của Spring Security. `FilterChainProxy` chọn `SecurityFilterChain` thích hợp theo matcher; authentication filter của Resource Server nằm trong chuỗi đó.
2. `BearerTokenAuthenticationFilter` dùng `BearerTokenResolver` để tìm Bearer token, mặc định thường từ header `Authorization`. Nếu có token, nó tạo `BearerTokenAuthenticationToken`.
3. `BearerTokenAuthenticationToken` là một `Authentication` ở **trạng thái chưa xác thực**; token string hiện đóng vai trò credential đầu vào, chưa có authorities đáng tin.
4. `AuthenticationManager` chuyển đối tượng đầu vào đến provider phù hợp, chẳng hạn `JwtAuthenticationProvider` hoặc `OpaqueTokenAuthenticationProvider`.
5. Provider xác minh JWT hoặc introspect opaque token. Chỉ khi token hợp lệ mới dựng một `Authentication` đã xác thực với principal và authorities.
6. `BearerTokenAuthenticationFilter` đưa kết quả xác thực vào `SecurityContext` qua cơ chế `SecurityContextHolder` và tiếp tục filter chain.
7. Tầng authorization áp rule của `authorizeHttpRequests` hoặc method security. Request chỉ đến controller/service khi các quy tắc áp dụng được thỏa mãn.

**Không phải mọi request đều phải có Authentication**: endpoint công khai có thể được phép truy cập mà không cần Bearer token; nhiều ứng dụng còn có `AnonymousAuthenticationFilter` tạo anonymous authentication cho các request chưa đăng nhập. Điều đó khác với kết quả xác thực access token thành công.

## 3. Các interface và class liên quan

### 3.1. `Authentication` là gì?

`org.springframework.security.core.Authentication` mở rộng `Principal` và có các phương thức quan trọng:

| API | Ý nghĩa thực tiễn |
|---|---|
| `getPrincipal()` | Danh tính/ngữ cảnh principal đã xác định |
| `getCredentials()` | Credential gắn với authentication; không được tự log hoặc trả ra API |
| `getAuthorities()` | Tập các `GrantedAuthority` cho authorization |
| `getDetails()` | Chi tiết request hoặc context nếu có; có thể bằng `null` |
| `getName()` | Tên principal theo implementation/claim mapping |
| `isAuthenticated()` | Dấu hiệu kết quả đã được authentication mechanism chấp nhận |

Đừng dựa vào `isAuthenticated()` đơn độc để bỏ qua policy của API. Spring Security tạo đối tượng xác thực đáng tin sau các bước validate, nhưng **authorization vẫn cần kiểm tra authorities và dữ liệu nghiệp vụ**.

Ở những bước khác nhau, interface `Authentication` có các implementation khác nhau:

~~~text
Trước xác thực:
    BearerTokenAuthenticationToken
        authenticated = false
        credentials   = raw token

Sau xác thực JWT:
    JwtAuthenticationToken
        principal     = Jwt
        authorities   = từ JwtAuthenticationConverter

Sau xác thực opaque:
    BearerTokenAuthentication
        principal     = OAuth2AuthenticatedPrincipal
        authorities   = từ kết quả OpaqueTokenIntrospector
~~~

### 3.2. `GrantedAuthority` có gì bên trong?

`GrantedAuthority` là một interface nhỏ, phương thức chính:

~~~java
public interface GrantedAuthority extends java.io.Serializable {
    String getAuthority();
}
~~~

`SimpleGrantedAuthority` là implementation phổ biến nhất:

~~~java
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

GrantedAuthority read = new SimpleGrantedAuthority("SCOPE_orders.read");
GrantedAuthority admin = new SimpleGrantedAuthority("ROLE_ADMIN");
~~~

**Giá trị quyền là chuỗi**. Với `hasAuthority("SCOPE_orders.read")`, Spring Security so sánh theo tên authority. Nếu code tạo `orders.read` nhưng rule đòi `SCOPE_orders.read`, quyền không khớp. Nếu code tạo `ROLE_ADMIN` nhưng rule đòi `SCOPE_ADMIN`, cũng không khớp.

Authority có thể đến từ scope chuẩn, role do issuer cấp, policy của tổ chức hoặc logic bổ sung đã được bảo vệ. Spring Security không tự đoán mọi claim tùy biến là quyền.

### 3.3. Các loại principal

| Token được xử lý theo | Principal thường gặp | Cách đọc thông tin |
|---|---|---|
| JWT Resource Server | `Jwt` | `jwt.getSubject()`, `jwt.getClaimAsString("...")` |
| Opaque token với introspection | `OAuth2AuthenticatedPrincipal` | `principal.getName()`, `principal.getAttribute("...")` |
| Custom authentication | Tùy implementation | Theo interface/class do ứng dụng thiết kế |

Đừng giả định principal luôn là `UserDetails` như trong đăng nhập username/password. Bearer token authentication **không nhất thiết gọi `UserDetailsService`** hay tra bảng user trong cơ sở dữ liệu để tạo principal.

## 4. Chuyển JWT thành `JwtAuthenticationToken`

Với access token JWT ký số và cấu hình Resource Server sử dụng `jwt()`, các thành phần chính:

~~~mermaid
flowchart LR
    A["BearerTokenAuthenticationToken"] --> B["JwtAuthenticationProvider"]
    B --> C["JwtDecoder"]
    C --> D["Jwt hợp lệ"]
    D --> E["JwtAuthenticationConverter"]
    E --> F["JwtGrantedAuthoritiesConverter"]
    F --> G["GrantedAuthority: SCOPE_*"]
    E --> H["JwtAuthenticationToken"]
    G --> H
~~~

### 4.1. Decoder thực hiện xác thực token trước khi converter chạy

`JwtDecoder` kiểm tra chữ ký/thuật toán theo cấu hình tin cậy và chạy các validator bắt buộc, ví dụ `exp`, `nbf` và `iss` nếu cấu hình issuer. API thường phải cấu hình thêm validator cho **audience `aud`** khi cần bảo đảm token được phát hành cho đúng Resource Server.

Chỉ sau khi decode và validate thành công, `JwtAuthenticationProvider` mới đưa đối tượng `Jwt` vào converter. Nếu chữ ký sai hoặc token hết hạn, converter **không được dùng** để tự sửa claim hay thêm authority nhằm cho request đi tiếp.

Một payload JWT minh họa:

~~~json
{
  "iss": "https://login.example.test/realms/company",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read orders.create",
  "iat": 1924988400,
  "exp": 1924992000
}
~~~

Đây chỉ là phần payload để giải thích dữ liệu; nó chưa phải JWT có chữ ký. API không được chỉ Base64URL-decode payload rồi tin vào các claim này. Giá trị timestamp minh họa không biểu thị token đang có hiệu lực ở thời điểm đọc bài.

### 4.2. Converter mặc định dùng scope

`JwtAuthenticationConverter` thường dùng `JwtGrantedAuthoritiesConverter` để chuyển claim `scope` hoặc `scp` thành authorities. Claim `scope` phổ biến là **chuỗi phân tách bằng dấu cách**; `scp` cũng có thể là **mảng tên scope** tùy Authorization Server và profile token.

Ví dụ:

~~~json
{
  "sub": "user-123",
  "scope": "orders.read orders.create profile"
}
~~~

Chuyển thành:

~~~text
Jwt token đã xác thực
    |
    v
JwtGrantedAuthoritiesConverter
    |
    +--> SCOPE_orders.read
    +--> SCOPE_orders.create
    +--> SCOPE_profile
    |
    v
JwtAuthenticationConverter
    |
    v
JwtAuthenticationToken
  - name          = user-123 (mặc định từ sub)
  - principal     = đối tượng Jwt đã xác thực
  - authorities   = các GrantedAuthority ở trên
  - authenticated = true
~~~

Với claim mảng:

~~~json
{
  "sub": "user-123",
  "scp": ["orders.read", "orders.create"]
}
~~~

Kết quả mặc định tương tự: `SCOPE_orders.read` và `SCOPE_orders.create`.

Nếu không có claim scope/scp hợp lệ, authorities mặc định từ scope có thể rỗng. **Không tự gán quyền mặc định rộng hơn** để bù cho claim thiếu; API cần xử lý theo chính sách.

### 4.3. Ví dụ đọc `Authentication` trong Java

Trong controller Spring MVC:

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class AuthenticationInfoController {

    @GetMapping("/api/whoami")
    Map<String, Object> whoAmI(Authentication authentication) {
        List<String> authorities = authentication.getAuthorities()
            .stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return Map.of(
            "name", authentication.getName(),
            "authenticated", authentication.isAuthenticated(),
            "authorities", authorities
        );
    }
}
~~~

Đây là endpoint **minh họa phục vụ học tập**; nếu đưa vào sản phẩm, hãy giới hạn quyền truy cập và không tiết lộ thông tin quá mức. Tuyệt đối không đưa `authentication.getCredentials()` hoặc raw token vào response.

Trong controller xử lý riêng JWT, có thể inject principal:

~~~java
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class JwtPrincipalController {

    @GetMapping("/api/me")
    Map<String, String> me(@AuthenticationPrincipal Jwt jwt) {
        return Map.of("subject", jwt.getSubject());
    }
}
~~~

`@AuthenticationPrincipal Jwt` chỉ phù hợp khi kết quả xác thực JWT có principal kiểu `Jwt`. Nếu API dùng opaque token, principal thường là `OAuth2AuthenticatedPrincipal`; inject `Jwt` trong trường hợp đó có thể không nhận được giá trị.

## 5. Tạo `SecurityFilterChain` với quyền đã ánh xạ

Ứng dụng Spring MVC Resource Server với JWT thường cần:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Ví dụ cấu hình issuer:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/company
~~~

Bean bảo vệ GET của Orders API:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class OrdersSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(withDefaults()))
            .build();
    }
}
~~~

Thứ tự ý nghĩa:

1. JWT phải được xác minh thành công; token sai sẽ bị từ chối.
2. Converter mặc định ánh xạ `scope=orders.read` thành `SCOPE_orders.read`.
3. `hasAuthority("SCOPE_orders.read")` cho GET request đi tiếp khi authority khớp.
4. Service vẫn phải kiểm tra quyền sở hữu của đơn hàng cụ thể, tenant và những điều kiện nghiệp vụ khác.

`anyRequest().authenticated()` chỉ yêu cầu đã xác thực đối với các request chưa được match, không tự hạn chế hành động nhạy cảm theo scope. Trong API thật, hãy xác định rule riêng cho từng thao tác hoặc sử dụng chính sách mặc định `denyAll` nếu phù hợp.

Một điểm khác cần phân biệt: `issuer-uri` là cấu hình nguồn phát hành và validation JWT mặc định, nhưng **không tự chứng minh token có đúng audience của API** trong mọi trường hợp. Khi hợp đồng yêu cầu `aud=orders-api`, cần audience validator riêng hoặc cơ chế cấu hình tương ứng của phiên bản framework.

## 6. Tùy biến JWT: đổi tên claim scope và tiền tố authority

Không phải Authorization Server nào cũng dùng cùng tên claim. Một issuer có thể dùng:

~~~json
{
  "sub": "user-123",
  "permissions": ["orders:read", "orders:create"]
}
~~~

Nếu hợp đồng đã xác nhận `permissions` là **mảng các quyền đáng tin cậy**, có thể dùng `JwtGrantedAuthoritiesConverter`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtGrantedAuthoritiesConverter grants =
        new JwtGrantedAuthoritiesConverter();

    grants.setAuthoritiesClaimName("permissions");
    grants.setAuthorityPrefix("PERMISSION_");

    JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();
    converter.setJwtGrantedAuthoritiesConverter(grants);
    return converter;
}
~~~

Converter này tạo:

~~~text
permissions = ["orders:read", "orders:create"]

GrantedAuthority:
    PERMISSION_orders:read
    PERMISSION_orders:create
~~~

Rule tương ứng:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("PERMISSION_orders:read")
~~~

**Chỉ định nghĩa bean converter chưa chắc đã đủ để Resource Server dùng converter đó.** Hãy đăng ký converter vào JWT DSL của security chain:

~~~java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        JwtAuthenticationConverter jwtAuthenticationConverter) throws Exception {

    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("PERMISSION_orders:read")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt ->
            jwt.jwtAuthenticationConverter(jwtAuthenticationConverter)))
        .build();
}
~~~

Đoạn này là một **cách cấu hình thay thế** cho bean `SecurityFilterChain` ở phần 5. Trong ứng dụng thực, chỉ giữ một định nghĩa chain phù hợp với request, hoặc cấu hình nhiều chain với matcher và thứ tự rõ ràng; không copy tất cả ví dụ thành nhiều bean cùng match mọi đường dẫn.

### 6.1. Giữ tiền tố `SCOPE_` khi đổi claim

Nếu issuer sử dụng `permissions` nhưng nội dung thực tế vẫn mang ngữ nghĩa **scope**, có thể chỉ đổi tên claim và giữ prefix mặc định `SCOPE_`:

~~~java
JwtGrantedAuthoritiesConverter grants =
    new JwtGrantedAuthoritiesConverter();
grants.setAuthoritiesClaimName("permissions");
// Không gọi setAuthorityPrefix: tiếp tục dùng tiền tố SCOPE_ mặc định.
~~~

Cần **thống nhất tên authority giữa converter và rule**. Tránh đổi prefix mà quên cập nhật các biểu thức `@PreAuthorize` và rule `authorizeHttpRequests`.

### 6.2. Đổi claim principal name

`JwtAuthenticationConverter` cũng có thể đổi claim dùng cho `Authentication.getName()`:

~~~java
JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
converter.setPrincipalClaimName("preferred_username");
~~~

Ví dụ `preferred_username` có thể giúp hiển thị tên thân thiện, nhưng không phải lúc nào cũng ổn định hoặc duy nhất toàn hệ thống. Đối với kiểm tra quyền sở hữu dữ liệu, thường nên dùng một định danh bền vững như tổ hợp issuer và `sub` theo hợp đồng. **Đổi `getName()` không làm JWT tự nhiên có thêm authority**, và cũng không thay JWT principal thành một `UserDetails`.

## 7. Khi claim có role: `ROLE_*` khác `SCOPE_*`

Trong Spring Security, các rule thường dùng:

| Cú pháp | Authority thường cần có | Ý nghĩa |
|---|---|---|
| `hasAuthority("SCOPE_orders.read")` | `SCOPE_orders.read` | Kiểm tra scope trực tiếp |
| `hasAuthority("ROLE_ADMIN")` | `ROLE_ADMIN` | Kiểm tra đúng authority role |
| `hasRole("ADMIN")` | `ROLE_ADMIN` (với default role prefix) | Cú pháp rút gọn cho role |
| `hasAuthority("PERMISSION_orders:read")` | `PERMISSION_orders:read` | Quyền tùy chỉnh theo hợp đồng |

JWT chứa:

~~~json
{
  "sub": "user-123",
  "scope": "orders.read",
  "roles": ["ADMIN", "AUDITOR"]
}
~~~

**Spring Security JWT Resource Server không tự ánh xạ mọi claim `roles` thành `ROLE_*`.** Đường mặc định thường ưu tiên `scope`/`scp`. Nếu muốn kết hợp scope và role, hãy cấu hình converter theo đúng hợp đồng issuer.

### 7.1. Kết hợp scope và roles trong converter

Ví dụ issuer bảo đảm claim `roles` là **mảng chuỗi tên role** với định dạng `ADMIN`, `AUDITOR`. Mã sau giữ scope mặc định và thêm role:

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

public final class OrdersJwtConverterFactory {

    public static JwtAuthenticationConverter create() {
        JwtGrantedAuthoritiesConverter scopes =
            new JwtGrantedAuthoritiesConverter();

        Converter<Jwt, Collection<GrantedAuthority>> authorities = jwt -> {
            List<GrantedAuthority> result = new ArrayList<>();

            Collection<GrantedAuthority> scopeAuthorities =
                scopes.convert(jwt);
            if (scopeAuthorities != null) {
                result.addAll(scopeAuthorities);
            }

            List<String> roles = jwt.getClaimAsStringList("roles");
            if (roles != null) {
                for (String role : roles) {
                    if (role != null && role.matches("[A-Z][A-Z0-9_]*")) {
                        result.add(new SimpleGrantedAuthority("ROLE_" + role));
                    }
                }
            }
            return result;
        };

        JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(authorities);
        return converter;
    }
}
~~~

Kết quả cho JWT mẫu:

~~~text
SCOPE_orders.read
ROLE_ADMIN
ROLE_AUDITOR
~~~

Mã này là ví dụ cho **claim `roles` phẳng**, không tự xử lý những cấu trúc lồng nhau như `realm_access.roles` hay `resource_access.{client}.roles` của một số nhà cung cấp. Nếu issuer trả claim role ở định dạng khác, cần xác định chính xác contract và viết bộ trích xuất tương ứng.

Việc lọc chuỗi theo pattern trong ví dụ giúp tránh authority bất ngờ do dữ liệu sai định dạng; **nó không thay việc kiểm tra token**. Chỉ thêm role khi issuer được tin cậy, audience phù hợp, token còn hiệu lực và nguồn claim được hệ thống công nhận. Tránh map tùy tiện một claim do client tự điền thành quyền quản trị.

### 7.2. Quy tắc thay thế khi issuer dùng role có namespace

Một hệ thống có thể phát hành `roles = ["orders-admin"]` thay vì `ADMIN`. Khi đó application nên ánh xạ rõ:

~~~text
Issuer role "orders-admin" → GrantedAuthority "ROLE_ORDERS_ADMIN"
Issuer role "orders-viewer" → GrantedAuthority "ROLE_ORDERS_VIEWER"
~~~

Đừng sử dụng quy tắc thay `-` thành `_` chung cho mọi role nếu có khả năng gây va chạm tên hoặc leo thang quyền. Bảng ánh xạ explicit dễ review hơn đối với các quyền nhạy cảm.

## 8. Chuyển opaque token thành `BearerTokenAuthentication`

Không phải mọi access token đều có thể tự giải mã theo JWT. Với **opaque token**, Resource Server thường cần gọi **OAuth 2.0 Token Introspection** của Authorization Server (RFC 7662). Client vẫn gửi:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer opa_example_random_string
~~~

Spring Security không dựa vào việc token có dấu chấm hay không để suy ra có quyền gì. Nếu đã cấu hình `opaqueToken()`, `OpaqueTokenAuthenticationProvider` dùng `OpaqueTokenIntrospector` để xác minh token theo hợp đồng introspection.

### 8.1. Chuỗi chuyển đổi cho opaque token

~~~mermaid
flowchart TD
    A["Authorization: Bearer opaque-token"] --> B["BearerTokenAuthenticationFilter"]
    B --> C["BearerTokenAuthenticationToken"]
    C --> D["OpaqueTokenAuthenticationProvider"]
    D --> E["OpaqueTokenIntrospector"]
    E --> F["Introspection endpoint của AS"]
    F --> G{"active + policy hợp lệ?"}
    G -->|No| H["Authentication bị từ chối"]
    G -->|Yes| I["OAuth2AuthenticatedPrincipal"]
    I --> J["Authorities từ scope/metadata"]
    J --> K["BearerTokenAuthentication"]
    K --> L["SecurityContextHolder"]
    L --> M["Authorization rules"]
~~~

Ví dụ phản hồi từ introspection endpoint đáng tin cậy:

~~~json
{
  "active": true,
  "sub": "user-123",
  "client_id": "shop-client",
  "scope": "orders.read profile",
  "aud": ["orders-api"],
  "exp": 1924992000
}
~~~

Các thuộc tính khác ngoài `active` có thể thay đổi theo Authorization Server. API không được coi mọi introspection response `active=true` là đủ điều kiện phân quyền; nếu hợp đồng yêu cầu **audience, tenant, client identity hoặc token type**, phải bảo đảm các điều kiện đó được kiểm tra bằng cơ chế tin cậy.

| Dữ liệu introspection | Hành động thường gặp trong Spring Security |
|---|---|
| `active = false` | Introspector từ chối token; không tạo authenticated principal hợp lệ |
| `active = true` | Có thể tạo `OAuth2AuthenticatedPrincipal` với attributes và authorities |
| `scope = "orders.read profile"` | Thường ánh xạ thành `SCOPE_orders.read`, `SCOPE_profile` |
| `sub = "user-123"` | Có thể được dùng làm tên principal, tùy introspector và token profile |
| `client_id = "shop-client"` | Attribute có thể dùng trong policy riêng |
| `aud = ["orders-api"]` | Cần kiểm tra resource binding theo hợp đồng; không mặc định mọi introspector đều kiểm tra giúp |

Spring Security tạo kết quả xác thực kiểu **`BearerTokenAuthentication`**, bên trong có principal kiểu `OAuth2AuthenticatedPrincipal`. Các authorities mà provider sử dụng đến từ principal do introspector trả về. Khác JWT, không có `JwtAuthenticationConverter` mặc định tham gia vào pipeline opaque token.

### 8.2. Cấu hình cơ bản bằng Spring Boot

Dependency vẫn là `spring-boot-starter-oauth2-resource-server`; cấu hình dành cho opaque token:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: ${OAUTH_INTROSPECTION_URI}
          client-id: ${OAUTH_INTROSPECTION_CLIENT_ID}
          client-secret: ${OAUTH_INTROSPECTION_CLIENT_SECRET}
~~~

Những giá trị trên phải đến từ cấu hình/secret manager an toàn. `client-id` và `client-secret` là thông tin xác thực **của Resource Server tại introspection endpoint**, khác với credential mà end-user/client gửi trong header Bearer.

Để bật nhánh opaque token trong Servlet security chain:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .opaqueToken(withDefaults()))
        .build();
}
~~~

Đây là một **security chain thay thế** ví dụ JWT ở phần trước. Để đoạn method biên dịch cần những import đã giới thiệu ở phần 5. Trong ứng dụng thực, lựa chọn đúng cơ chế xác thực theo loại token/hợp đồng của Authorization Server; không bật cấu hình khác nhau một cách tùy tiện và dựa vào hình thức chuỗi token.

### 8.3. Đọc principal của opaque token

~~~java
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OpaquePrincipalController {

    @GetMapping("/api/me")
    Map<String, String> me(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
        return Map.of("name", principal.getName());
    }
}
~~~

Không suy luận `principal.getName()` luôn là một end-user. Với `client_credentials`, principal có thể đại diện cho ứng dụng/dịch vụ. Nếu API cần phân biệt service token và delegated user token, đó là **một phần của hợp đồng access token**, không chỉ là quyết định đặt tên.

### 8.4. Khi cần authority tùy chỉnh cho opaque token

Giả sử introspection trả thêm claim đã được đội Identity chứng thực:

~~~json
{
  "active": true,
  "sub": "user-123",
  "scope": "orders.read",
  "roles": ["SUPERVISOR"]
}
~~~

Để đưa `roles` thành `ROLE_SUPERVISOR`, có thể tạo một decorator cho introspector. Phần cốt lõi của decorator:

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

public final class RoleMappingOpaqueTokenIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;

    public RoleMappingOpaqueTokenIntrospector(
            OpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        // Delegate xác thực token với introspection endpoint trước.
        OAuth2AuthenticatedPrincipal principal =
            delegate.introspect(token);

        List<GrantedAuthority> authorities =
            new ArrayList<>(principal.getAuthorities());
        Object roles = principal.getAttribute("roles");

        if (roles instanceof Collection<?> roleValues) {
            for (Object role : roleValues) {
                if (role instanceof String roleName
                        && roleName.matches("[A-Z][A-Z0-9_]*")) {
                    authorities.add(
                        new SimpleGrantedAuthority("ROLE_" + roleName)
                    );
                }
            }
        }

        return new DefaultOAuth2AuthenticatedPrincipal(
            principal.getName(),
            principal.getAttributes(),
            authorities
        );
    }
}
~~~

Decorator giữ nguyên authorities cũ, nên scope như `SCOPE_orders.read` không mất. Nó chỉ thêm role khi claim có định dạng được hợp đồng cho phép. **Đoạn code này chưa tự tạo bean delegate**: phải cấp cho nó một `OpaqueTokenIntrospector` được cấu hình endpoint và client credentials đáng tin cậy, rồi đăng ký kết quả trong security configuration. Nếu tự định nghĩa bean `OpaqueTokenIntrospector`, hãy kiểm tra tương tác với auto-configuration; Spring Boot có thể không còn tự tạo introspector mặc định khi đã có bean của ứng dụng.

Đối với introspection từ issuer có nhiều resource, decorator có thể kiểm tra thêm `aud`, `tenant` hoặc loại principal **trước khi trả kết quả được chấp nhận**. Không chỉ bổ sung authority rồi bỏ qua những ràng buộc bắt buộc khác.

## 9. Khi nào `Authentication` được đặt vào `SecurityContextHolder`?

Trong Servlet Spring Security, `SecurityContextHolder` là điểm truy cập quen thuộc tới `SecurityContext` của execution hiện tại. Chiến lược mặc định thường dựa trên `ThreadLocal`.

Sau khi provider xác thực thành công, filter tạo/cập nhật security context với `Authentication` đã xác thực, rồi chuỗi xử lý tiếp tục đến authorization và controller:

~~~text
BearerTokenAuthenticationFilter
    |
    | AuthenticationManager.authenticate(...)
    v
JwtAuthenticationToken / BearerTokenAuthentication
    |
    v
SecurityContext
    |
    v
SecurityContextHolder
    |
    v
AuthorizationFilter -> DispatcherServlet / Controller
~~~

Code Servlet thường gặp để đọc context:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

if (authentication != null) {
    String principalName = authentication.getName();
}
~~~

**Chỉ đọc context sau khi filter chain đã thực hiện xác thực** nếu logic phụ thuộc vào identity hiện tại. Authentication có thể bằng `null` hoặc là anonymous ở endpoint công khai. Tránh ép kiểu mọi principal thành `Jwt` hay `UserDetails` mà không kiểm tra implementation.

### 9.1. ThreadLocal, request lifecycle và bất đồng bộ

Với Servlet, security context thường gắn với luồng đang xử lý request và được framework quản lý, dọn dẹp đúng vòng đời. Nếu nghiệp vụ tự tạo thread, dùng `CompletableFuture`, `@Async` hoặc executor riêng, không mặc định context sẽ tự lan sang thread khác. Spring Security có các công cụ `DelegatingSecurityContext...` phù hợp khi thực sự cần truyền context vào tác vụ bất đồng bộ.

Đừng tự sao chép raw access token vào biến toàn cục hoặc static để “giữ phiên đăng nhập”. Đó không phải cách lưu security context đúng và có thể làm rò rỉ credential giữa các request.

Một API Bearer token **stateless** không cần lưu `Authentication` vào HTTP session để tái sử dụng cho request tiếp theo: mỗi request có thể gửi access token và được xác thực lại theo chính sách. Nhưng phải xem cách cấu hình session/repository và các cơ chế authentication khác của ứng dụng thực tế; không suy luận chỉ bật `oauth2ResourceServer()` là mọi thành phần đều hoàn toàn không dùng session.

### 9.2. Tại sao không tự tạo authenticated token từ request parameter?

Mẫu sau **không an toàn** nếu dữ liệu role/name đến trực tiếp từ client mà chưa được xác minh:

~~~java
// PHẢN VÍ DỤ — tuyệt đối không dùng để xác thực request:
// String role = request.getParameter("role");
// Authentication fake = new UsernamePasswordAuthenticationToken(
//     request.getParameter("user"),
//     null,
//     List.of(new SimpleGrantedAuthority("ROLE_" + role))
// );
// SecurityContextHolder.getContext().setAuthentication(fake);
~~~

Kẻ tấn công có thể tự gửi `role=ADMIN`. Con đường chuẩn là để **AuthenticationProvider** sử dụng dữ liệu đã được xác minh từ token/issuer rồi mới tạo các authorities đáng tin. Nếu ứng dụng cần ánh xạ quyền từ cơ sở dữ liệu, việc tra cứu và gắn quyền phải được thực hiện trong thành phần tin cậy với ràng buộc identity, tenant và authorization rõ ràng.

## 10. Authorization sử dụng GrantedAuthority thế nào?

Sau khi token đã chuyển thành `Authentication`, rule của Spring Security sẽ kiểm tra collection do `authentication.getAuthorities()` cung cấp.

### 10.1. Kiểm tra ở HTTP layer

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.POST, "/api/orders")
        .hasAuthority("SCOPE_orders.create")
    .requestMatchers("/api/admin/**")
        .hasRole("ADMIN")
    .anyRequest().authenticated()
);
~~~

Trong ngữ cảnh này:

- GET yêu cầu `SCOPE_orders.read`.
- POST tạo đơn yêu cầu `SCOPE_orders.create`.
- `hasRole("ADMIN")` thường yêu cầu `ROLE_ADMIN` theo default role prefix.
- Các request còn lại chỉ yêu cầu xác thực thành công; hệ thống thực cần xác định thêm quyền theo nghiệp vụ.

Đây là đoạn cấu hình DSL minh họa bên trong `HttpSecurity`, không phải Java class độc lập. Nếu API dùng cookie để xác thực trên browser, hãy xử lý CSRF cho các HTTP method thay đổi dữ liệu; không mặc định tắt CSRF vì chỉ đang học rule.

### 10.2. Kiểm tra tại method

Spring Security có thể bảo vệ service method với `@PreAuthorize` khi bật `@EnableMethodSecurity`:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public OrderView readOrder(String orderId) {
        // Service phải kiểm tra thêm owner/tenant trước khi trả dữ liệu.
        return loadOrderForCurrentPrincipal(orderId);
    }
}
~~~

`OrderView` và `loadOrderForCurrentPrincipal` là các thành phần nghiệp vụ cần được ứng dụng tự định nghĩa; đoạn trên minh họa nơi đặt rule. `@PreAuthorize` phải chạy qua cơ chế method security của Spring và đối tượng được quản lý bởi Spring. Một lời gọi nội bộ không đi qua proxy có thể không kích hoạt method security theo cách mong đợi.

### 10.3. Scope không thay thế quyền truy cập bản ghi

Giả sử token đã được xác thực có:

~~~text
principal = user-123
authorities = [SCOPE_orders.read]
~~~

Những request sau có cùng authority:

~~~text
GET /api/orders/42   (ownerId = user-123)
GET /api/orders/99   (ownerId = user-999)
~~~

Authority `SCOPE_orders.read` cho phép **loại hành động đọc đơn hàng**, nhưng chỉ request đầu có thể phù hợp chính sách chủ sở hữu. Service cần kiểm tra owner/tenant/data policy sau khi HTTP layer xác nhận scope. Nếu không, lỗi **Broken Object Level Authorization (BOLA)** có thể xảy ra dù token và scope hợp lệ.

Ví dụ triển khai nghiệp vụ có thể:

~~~java
public OrderView findOrderForUser(String orderId, String subject) {
    Order order = repository.findById(orderId)
        .orElseThrow(OrderNotFoundException::new);

    if (!order.getOwnerSubject().equals(subject)) {
        throw new AccessDeniedException("Order access denied");
    }
    return toView(order);
}
~~~

Các class `Order`, `OrderView`, `OrderNotFoundException`, `repository` và `toView` được giả định thuộc ứng dụng. Mục đích là minh họa thứ tự **xác thực → scope → quyền sở hữu**. Đối với hệ thống đa tenant, subject nên được xác định trong không gian issuer/tenant phù hợp; không lấy raw username chưa kiểm chứng làm khóa toàn cục.

## 11. Phân biệt lỗi chuyển đổi token và lỗi thiếu quyền

| Tình huống | Giai đoạn | Phản hồi thường gặp |
|---|---|---|
| Không có Bearer token ở endpoint yêu cầu xác thực | Chưa có authentication hợp lệ | `401 Unauthorized` |
| Bearer token có cấu trúc HTTP sai | Token resolution / authentication | Thường bị từ chối; RFC 6750 có trường hợp `invalid_request` |
| JWT sai chữ ký, issuer hoặc hết hạn | `JwtDecoder` / validator | `401 Unauthorized` |
| Opaque token không active | `OpaqueTokenIntrospector` | `401 Unauthorized` |
| Token hợp lệ, không có claim scope cần thiết | Authority mapping rồi authorization | `403 Forbidden` |
| Token hợp lệ, có scope nhưng thiếu role cần thiết | Authorization | `403 Forbidden` |
| Token hợp lệ, đủ scope nhưng không sở hữu tài nguyên | Authorization nghiệp vụ | `403 Forbidden`; có thể che giấu bằng `404` theo policy |
| Token hợp lệ, đủ quyền và policy đạt | Controller/service | Status do nghiệp vụ quyết định |
| Introspection endpoint lỗi mạng hoặc sai client secret | Hạ tầng xác thực/upstream | Không cho qua; HTTP status tới client phụ thuộc xử lý lỗi |

Một Resource Server sử dụng Bearer authentication có thể trả:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Khi token đã xác thực nhưng thiếu scope:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.read"
~~~

Đây là các response minh họa theo **RFC 6750**; mã lỗi và header chính xác có thể khác theo request, filter, exception handler và cấu hình Spring Security. Không đưa nguyên raw token hoặc thông tin khóa bí mật vào `error_description`.

### 11.1. Lỗi authority prefix rất phổ biến

Ví dụ claim token:

~~~json
{ "scope": "orders.read" }
~~~

Spring Security ánh xạ mặc định:

~~~text
SCOPE_orders.read
~~~

Nhưng ứng dụng viết:

~~~java
.hasAuthority("orders.read")
~~~

Request có thể bị `403`, dù token được xác thực hợp lệ. Cách sửa là làm cho **giá trị rule** và **giá trị converter** khớp theo hợp đồng, ví dụ:

~~~java
.hasAuthority("SCOPE_orders.read")
~~~

Không “sửa” lỗi này bằng cách ngừng kiểm tra chữ ký JWT, bỏ issuer validation hoặc cho `permitAll()`.

### 11.2. Claim `roles` có nhưng `hasRole("ADMIN")` vẫn trả 403

Nếu chưa cấu hình converter, Spring Security JWT Resource Server thường không tự đọc claim `roles`. Sau khi xác thực, `Authentication.getAuthorities()` có thể chỉ chứa `SCOPE_*`. Để dùng `hasRole("ADMIN")`, converter phải sinh `ROLE_ADMIN` từ nguồn role đáng tin và đã được cấu hình.

### 11.3. JWT đúng chữ ký nhưng dành cho API khác

Claim:

~~~json
{ "aud": ["billing-api"], "scope": "orders.read" }
~~~

Nếu Orders API yêu cầu audience `orders-api`, token này phải bị từ chối **ở bước authentication/validation** dù scope trông phù hợp. Ánh xạ authority chỉ sau khi xác thực đúng nguồn và đúng resource. Đừng để converter “sửa” audience rồi chấp nhận token.

### 11.4. Lỗi converter không giống lỗi token thiếu scope

Converter tùy chỉnh có thể ném exception vì claim `roles` không đúng kiểu dữ liệu, null bất ngờ hoặc logic parse lỗi. Một exception Java không được xử lý có thể dẫn đến lỗi server, thay vì trả 403 có chủ đích. Thiết kế converter nên:

- Xác định rõ kiểu claim và cách xử lý claim vắng mặt.
- Không tự sinh quyền khi claim thiếu hoặc không hợp lệ.
- Không lẫn dữ liệu request chưa xác thực vào quyền.
- Có quy tắc từ chối token nếu contract yêu cầu claim bắt buộc mà token không có.
- Tách trường hợp **không có quyền** (authorization) khỏi **token không hợp lệ theo hợp đồng** (authentication/validation).

Nếu claim bắt buộc quyết định token có được chấp nhận hay không, một **validator ở bước decoder/introspection** thường phù hợp hơn việc để converter tự âm thầm biến token thành authentication thiếu quyền. Converter có nhiệm vụ chủ yếu là ánh xạ dữ liệu đã xác thực.

## 12. Vai trò của `AuthenticationManager` và provider

`AuthenticationManager` nhận một `Authentication` đầu vào và trả về `Authentication` đã xác thực hoặc ném lỗi phù hợp. Implementation thường gặp của Servlet security là `ProviderManager`, quản lý các `AuthenticationProvider`.

~~~text
AuthenticationManager.authenticate(
    new BearerTokenAuthenticationToken(rawToken)
)
          |
          v
ProviderManager
          |
          +-- JWT Resource Server:
          |      JwtAuthenticationProvider
          |        → JwtDecoder
          |        → JwtAuthenticationConverter
          |        → JwtAuthenticationToken
          |
          +-- Opaque Resource Server:
                 OpaqueTokenAuthenticationProvider
                   → OpaqueTokenIntrospector
                   → BearerTokenAuthentication
~~~

Sự khác biệt quan trọng nằm ở **cách token được xác minh và cách ánh xạ principal**. Controller/service có thể dùng giao diện chung `Authentication` và `GrantedAuthority` để không phụ thuộc chặt vào JWT/opaque token; chỉ khi cần claim đặc thù mới cần xử lý các kiểu principal cụ thể.

Một `ProviderManager` có thể có nhiều provider cho những cơ chế xác thực khác nhau, nhưng thứ tự và khả năng hỗ trợ token phải được cấu hình rõ. Không nên tự đưa JWT token đến opaque introspector hoặc ngược lại mà không có thiết kế token resolution/multi-token hỗ trợ.

## 13. Bảng đối chiếu luồng JWT và opaque token

| Đặc điểm | JWT access token | Opaque access token |
|---|---|---|
| Bearer request header | `Authorization: Bearer ...` | `Authorization: Bearer ...` |
| Filter trên Servlet | `BearerTokenAuthenticationFilter` | `BearerTokenAuthenticationFilter` |
| Đầu vào provider | `BearerTokenAuthenticationToken` | `BearerTokenAuthenticationToken` |
| AuthenticationProvider | `JwtAuthenticationProvider` | `OpaqueTokenAuthenticationProvider` |
| Xác minh token | `JwtDecoder` + validators (chữ ký, claim, issuer, audience theo cấu hình) | `OpaqueTokenIntrospector` + hợp đồng introspection |
| Principal đã xác thực | Thường là `Jwt` | Thường là `OAuth2AuthenticatedPrincipal` |
| Nơi chuyển thành authority | `JwtAuthenticationConverter`, `JwtGrantedAuthoritiesConverter` | Authorities do `OpaqueTokenIntrospector` / principal trả về |
| Authentication kết quả | `JwtAuthenticationToken` | `BearerTokenAuthentication` |
| Đưa vào security context | `SecurityContextHolder` | `SecurityContextHolder` |
| Quy tắc phân quyền | `hasAuthority("SCOPE_...")`, role/custom policy | Các rule authority tương ứng |
| Tùy biến | JWT claim converter và validator | Decorator/custom introspector, metadata validation |

**Cùng một tên `scope` không bảo đảm cùng ngữ nghĩa giữa nhiều issuer.** Nếu API tin cậy nhiều Authorization Server, cần đảm bảo mỗi issuer có hợp đồng quyền tương thích hoặc áp dụng ánh xạ và kiểm tra riêng.

## 14. Kiểm chứng cách ánh xạ bằng ví dụ dữ liệu

### 14.1. Đối chiếu token và authority

| Dữ liệu sau xác thực | Converter mặc định phổ biến | Authority cuối cùng |
|---|---|---|
| JWT `scope: "orders.read profile"` | `JwtGrantedAuthoritiesConverter` | `SCOPE_orders.read`, `SCOPE_profile` |
| JWT `scp: ["orders.read"]` | `JwtGrantedAuthoritiesConverter` | `SCOPE_orders.read` |
| JWT không có `scope`/`scp` | Không có scope chuẩn để ánh xạ | Không sinh authority `SCOPE_*` từ scope |
| JWT `roles: ["ADMIN"]`, không có converter role | Role tùy chỉnh chưa được xử lý | Không tự sinh `ROLE_ADMIN` |
| JWT `permissions: ["orders:read"]` với custom converter | `JwtGrantedAuthoritiesConverter` đã đổi claim và prefix | `PERMISSION_orders:read` |
| Opaque introspection `scope: "orders.read"` | Introspector phù hợp trả quyền scope | `SCOPE_orders.read` |
| Opaque introspection có `roles` với decorator tin cậy | Ánh xạ bổ sung role | `ROLE_SUPERVISOR` theo ví dụ |

### 14.2. Bài đọc kết quả `Authentication`

Giả sử sau xác thực thu được:

~~~text
Authentication implementation: JwtAuthenticationToken
getName(): user-123
isAuthenticated(): true
authorities:
    SCOPE_orders.read
    SCOPE_profile
~~~

Xét các rule:

| Rule | Kết quả |
|---|---|
| `authenticated()` | Đạt |
| `hasAuthority("SCOPE_orders.read")` | Đạt |
| `hasAuthority("SCOPE_orders.write")` | Không đạt |
| `hasRole("ADMIN")` | Không đạt vì thiếu `ROLE_ADMIN` |
| `hasAnyAuthority("SCOPE_profile", "SCOPE_orders.write")` | Đạt vì có `SCOPE_profile` |

Kết quả trên chỉ minh họa phần authority và authentication. Nếu rule kết hợp điều kiện chủ sở hữu, tenant, loại client, hoặc trạng thái nghiệp vụ, request vẫn có thể bị từ chối dù một rule scope đạt.

### 14.3. Tự kiểm tra converter trên một đối tượng JWT mẫu

Có thể hiểu đường ánh xạ bằng mã thuần Java tạo một `Jwt` **phục vụ thử converter**, không cần ký JWT:

~~~java
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

Jwt jwt = Jwt.withTokenValue("example-only")
    .header("alg", "RS256")
    .claim("sub", "user-123")
    .claim("scope", "orders.read profile")
    .build();

JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
JwtAuthenticationToken authentication =
    (JwtAuthenticationToken) converter.convert(jwt);

// Ví dụ kết quả:
// authentication.getName()                 -> "user-123"
// authentication.getAuthorities()          -> SCOPE_orders.read, SCOPE_profile
// authentication.isAuthenticated()         -> true
~~~

Đoạn này chứng minh ý tưởng **đầu vào claims → `JwtAuthenticationConverter` → authorities**, nhưng **không xác thực chữ ký thật**, không gọi `JwtDecoder` và không thay thế kiểm thử tích hợp Resource Server. Không bao giờ dùng một đối tượng `Jwt` tự dựng từ request body để xác thực HTTP request thực.

## 15. Những nhầm lẫn cần tránh

### “Đã có claim `role` trong JWT nghĩa là có quyền Spring Security”

Chưa đúng. JWT đã xác thực chỉ cung cấp dữ liệu claim đáng tin theo hợp đồng. Cần converter để biến claim đó thành `GrantedAuthority` phù hợp. Với Resource Server mặc định, authorities thường xuất phát từ `scope` hoặc `scp`.

### “`getPrincipal()` luôn là username dạng `String`”

Không. Với `JwtAuthenticationToken`, principal thường là `Jwt`; với `BearerTokenAuthentication` của opaque token, là `OAuth2AuthenticatedPrincipal`. Cách lấy tên là `getName()` hoặc dùng API thuộc kiểu principal phù hợp.

### “Đổi `getName()` nghĩa là đổi quyền”

Không. `JwtAuthenticationConverter.setPrincipalClaimName(...)` điều chỉnh tên đại diện của authentication, còn mapping authorities thuộc `JwtGrantedAuthoritiesConverter` hoặc converter tương ứng. Hai quyết định khác nhau.

### “`hasRole("ADMIN")` tự tìm `scope=ADMIN`”

Không. Theo mặc định, `hasRole("ADMIN")` kiểm tra `ROLE_ADMIN`; scope thường ánh xạ thành `SCOPE_ADMIN` nếu có scope tên `ADMIN`. Cần ánh xạ explicit nếu muốn chuyển dữ liệu scope/role giữa hai namespace.

### “Đọc được JWT payload là đã được xác thực”

Không. Payload Base64URL có thể bị chỉnh sửa. `JwtDecoder` và các validators phải xác minh chữ ký, issuer, hiệu lực và các ràng buộc như audience trước khi converter dùng claim.

### “Introspection `active=true` thì token dùng được ở mọi API”

Không. Độ phù hợp với **Resource Server cụ thể**, scope và tenant vẫn phải do hợp đồng introspection và API policy xác nhận.

### “Đã có `SCOPE_orders.read` thì có thể đọc mọi đơn hàng”

Không. Authority chỉ cho biết quyền thao tác ở mức khái quát. Service phải kiểm tra quyền trên bản ghi, subject, tenant và các điều kiện khác để tránh lộ dữ liệu.

### “SecurityContextHolder giữ Authentication mãi cho mọi thread”

Không. Trong Servlet, context mặc định gắn với execution/thread và vòng đời security framework. Thread tự tạo và async execution cần cơ chế truyền ngữ cảnh phù hợp khi thực sự cần thiết.

### “Cấu hình converter bean tự động ảnh hưởng mọi security chain”

Không nên giả định. Cần xác nhận chain dùng converter nào và gắn converter vào DSL khi áp dụng customization. Với nhiều chain, cấu hình rõ chain nào nhận loại token và quy tắc quyền tương ứng.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Lớp nào trích Bearer token khỏi request Servlet theo cấu hình Spring Security Resource Server phổ biến?

`BearerTokenAuthenticationFilter` sử dụng `BearerTokenResolver`. Kết quả ban đầu được biểu diễn dưới dạng `BearerTokenAuthenticationToken` chưa xác thực.

**Câu 2.** Khi dùng JWT, lớp nào chuyển claims đã được xác thực thành authorities?

`JwtAuthenticationConverter` thường gọi `JwtGrantedAuthoritiesConverter`. Dữ liệu `scope`/`scp` được ánh xạ thành `SimpleGrantedAuthority` với tiền tố `SCOPE_` trong cấu hình mặc định.

**Câu 3.** Khi dùng opaque token, có cần `JwtAuthenticationConverter` không?

Thông thường **không**. `OpaqueTokenIntrospector` trả principal và authorities; `OpaqueTokenAuthenticationProvider` tạo `BearerTokenAuthentication`.

**Câu 4.** Token có `scope="orders.read"` nhưng rule dùng `hasAuthority("orders.read")`, tại sao có thể trả 403?

Vì tên authority mặc định là `SCOPE_orders.read`. Rule phải khớp đúng chuỗi authority hoặc converter phải được cấu hình khác có chủ đích.

**Câu 5.** Vì sao không thể chỉ dùng `hasAuthority("SCOPE_orders.read")` để trả bất kỳ đơn hàng nào?

Vì scope không xác nhận chủ sở hữu của từng đơn hàng. Tầng nghiệp vụ cần kiểm tra subject/tenant và quyền đối với bản ghi.

**Câu 6.** Khi nào principal/role được xem là đáng tin?

Sau khi authentication mechanism xác thực token với issuer, khóa/thuật toán hoặc introspection endpoint đáng tin, hiệu lực và các ràng buộc cần thiết. Converter không phải bước thay thế token validation.

## 17. Ghi nhớ luồng chuyển đổi

Với **JWT**:

~~~text
HTTP Authorization: Bearer
  → BearerTokenAuthenticationFilter
  → BearerTokenAuthenticationToken (unauthenticated)
  → AuthenticationManager
  → JwtAuthenticationProvider
  → JwtDecoder + validators
  → JwtAuthenticationConverter
  → JwtGrantedAuthoritiesConverter
  → JwtAuthenticationToken (principal Jwt, authorities)
  → SecurityContextHolder
  → HTTP authorization / method security
~~~

Với **opaque token**:

~~~text
HTTP Authorization: Bearer
  → BearerTokenAuthenticationFilter
  → BearerTokenAuthenticationToken (unauthenticated)
  → AuthenticationManager
  → OpaqueTokenAuthenticationProvider
  → OpaqueTokenIntrospector
  → OAuth2AuthenticatedPrincipal + authorities
  → BearerTokenAuthentication
  → SecurityContextHolder
  → HTTP authorization / method security
~~~

**`Authentication` là kết quả xác thực**, còn **`GrantedAuthority` là cách Spring Security biểu diễn quyền để áp dụng authorization**. Hai nhánh JWT và opaque token khác nhau ở cách xác minh credential và trích xuất principal/authorities, nhưng cuối cùng cùng đưa một `Authentication` hợp lệ vào security context Servlet để thực thi quy tắc truy cập API.

## Tài liệu tham khảo

- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — Servlet OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Servlet OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — Servlet Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html)
- [Spring Security — Servlet Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
