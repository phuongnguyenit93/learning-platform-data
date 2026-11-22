# Authentication.getName và lựa chọn claim làm tên principal

Trong một **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Resource Server**, sau khi access token được xác minh, ứng dụng thường muốn biết “ai đang gọi API?”. Một cách quen thuộc là gọi `Authentication.getName()`:

~~~java
String caller = SecurityContextHolder.getContext()
        .getAuthentication()
        .getName();
~~~

Giá trị `caller` là **tên principal theo cách đối tượng `Authentication` hiện tại định nghĩa**. Nó không mặc nhiên là email, username, số định danh người dùng trong database hay `client_id`. Đặc biệt, với JWT Resource Server của Spring Security, mặc định `JwtAuthenticationToken.getName()` thường lấy từ claim **`sub` (subject)** trong JWT, và ta có thể đổi claim được dùng làm tên bằng `JwtAuthenticationConverter#setPrincipalClaimName(...)`.

Việc chọn claim này tưởng như chỉ thay một chuỗi hiển thị, nhưng ảnh hưởng tới log/audit, kiểm thử, biểu thức phân quyền, ánh xạ người dùng nội bộ và khả năng hỗ trợ nhiều issuer. Chọn một claim **dễ đổi hoặc không duy nhất** có thể tạo lỗi nhận diện chủ thể, thậm chí lỗi phân quyền nếu ứng dụng dùng `getName()` như khóa truy cập dữ liệu.

> **Nguyên tắc:** `Authentication.getName()` là **biểu diễn tên của principal trong Spring Security**, còn danh tính tin cậy phải dựa trên **token đã xác minh** và một quy ước định danh ổn định. Với access token có người dùng, `(iss, sub)` thường là cặp định danh thích hợp để ánh xạ; quyền truy cập tài nguyên vẫn phải kiểm tra riêng, không dựa vào chuỗi hiển thị.

## 1. Đặt `getName()` trong luồng Resource Server

Ví dụ một hệ thống:

- **Shop Web**: OAuth2 Client xin access token cho người dùng.
- **Identity Server**: Authorization Server, issuer `https://identity.example.test/realms/shop`.
- **Orders API**: Spring Security Resource Server chấp nhận JWT access token có `aud` chứa `orders-api`.

Shop Web gửi:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer <access-token>
~~~

Một JWT access token sau khi giải mã payload có thể có các claim:

~~~json
{
  "iss": "https://identity.example.test/realms/shop",
  "sub": "user-9f1a",
  "aud": ["orders-api"],
  "client_id": "shop-web",
  "scope": "orders.read",
  "preferred_username": "linh.nguyen",
  "name": "Nguyen Linh",
  "email": "linh@example.test",
  "exp": 1893459600
}
~~~

Các giá trị chỉ nhằm minh họa. Không phải JWT access token nào cũng có `preferred_username`, `name` hay `email`; những claim đó phụ thuộc nhà phát hành và hợp đồng token. Spring Security chỉ nên sử dụng chúng sau khi token đã qua xác minh chữ ký, issuer, audience và thời hạn.

Với cấu hình **mặc định** của JWT Resource Server:

~~~text
authentication.getName()      -> "user-9f1a"
jwt.getSubject()              -> "user-9f1a"
jwt.getClaimAsString("name")  -> "Nguyen Linh"
jwt.getClaimAsString("email") -> "linh@example.test"
~~~

Nếu chủ động cấu hình principal claim là `preferred_username`:

~~~text
authentication.getName()                     -> "linh.nguyen"
jwt.getSubject()                             -> "user-9f1a"
jwt.getClaimAsString("preferred_username")   -> "linh.nguyen"
~~~

**Đổi tên principal không làm thay đổi claim `sub` trong JWT.** Cũng không làm `issuer`, `audience`, scope hoặc quyền trên đơn hàng thay đổi.

### Tổng quan luồng xử lý

~~~mermaid
flowchart TD
    A["HTTP Authorization: Bearer JWT"]
    B["JwtDecoder xác minh chữ ký và token claims"]
    C{"Token được chấp nhận?"}
    D["Từ chối authentication"]
    E["JwtAuthenticationConverter"]
    F["JwtAuthenticationToken"]
    G["authentication.getName()"]
    H["authentication.getAuthorities()"]
    I["Kiểm tra scope và quyền tài nguyên"]

    A --> B --> C
    C -->|Không| D
    C -->|Có| E
    E --> F
    F --> G
    F --> H
    H --> I
~~~

`getName()` được dùng sau bước tạo authentication; nó **không phải bước xác minh JWT**. Việc đổi principal claim không được làm API giảm kiểm tra chữ ký, issuer, audience, thời hạn hoặc chính sách quyền.

## 2. `Authentication`, principal và name là ba khái niệm liên quan nhưng khác nhau

Spring Security có interface `Authentication` biểu diễn kết quả xác thực hoặc yêu cầu xác thực. Những method quan trọng:

| Method | Ý nghĩa | Ví dụ với JWT Resource Server |
| --- | --- | --- |
| `getPrincipal()` | Đối tượng thể hiện chủ thể đã xác thực | Thường là đối tượng `Jwt` bên trong `JwtAuthenticationToken` |
| `getName()` | Chuỗi tên của principal do loại authentication định nghĩa | Mặc định là `sub`, có thể chọn claim khác |
| `getAuthorities()` | Tập các `GrantedAuthority` để ra quyết định quyền | Ví dụ `SCOPE_orders.read` |
| `getCredentials()` | Thông tin credential của authentication, tùy implementation | Không nên giả định đây là mật khẩu hay chuỗi tên |
| `isAuthenticated()` | Trạng thái xác thực của đối tượng `Authentication` | Không thay thế kiểm tra authorization |
| `getDetails()` | Dữ liệu bổ sung tùy cơ chế authentication | Có thể là thông tin web authentication |

### 2.1. `Principal.getName()` là hợp đồng tên, không phải định danh nghiệp vụ phổ quát

Trong Java, `java.security.Principal` đại diện cho một principal và có method `getName()`. Interface `Authentication` của Spring Security kế thừa `Principal` nên cũng có method này. Tuy nhiên, **cách sinh chuỗi tên phụ thuộc vào implementation**.

Ví dụ:

- Với **JWT Resource Server**, `JwtAuthenticationToken` thường dùng `sub` hoặc claim được cấu hình.
- Với **OIDC login**, đối tượng authentication có thể chứa `OidcUser`; `getName()` chịu ảnh hưởng cấu hình user name attribute của Client/`OidcUser`.
- Với **username/password authentication**, `getName()` có thể phản ánh username của `UserDetails`.
- Với **opaque access token**, Spring Security dùng một dạng authentication khác; tên phụ thuộc thuộc tính principal/introspection được thư viện hoặc ứng dụng cung cấp.

Vì vậy, một method tiện ích dùng chung kiểu:

~~~java
String getCurrentUserId(Authentication authentication) {
    return authentication.getName();
}
~~~

chỉ đúng nếu hệ thống **cam kết rằng name chính là user ID ổn định** cho tất cả cơ chế authentication được dùng. Nếu ứng dụng có cả JWT, OAuth2 login, API key hoặc service-to-service, giả định này thường cần được kiểm tra và ràng buộc rõ hơn.

### 2.2. Principal object không nhất thiết là chuỗi

Đối với JWT Resource Server, có thể gặp:

~~~java
Authentication authentication = ...;

Object principal = authentication.getPrincipal();
String principalName = authentication.getName();
~~~

`principal` có thể là **`Jwt`**, trong khi `principalName` là **`String`**. Không nên ép kiểu `(String) authentication.getPrincipal()` chỉ vì `getName()` trả về String.

Nếu code cần claims, dùng đối tượng JWT đã được xác minh thay vì parse lại Bearer token từ header request.

## 3. Tại sao mặc định là claim `sub`?

**`sub` (subject)** là registered claim name của JWT. Nó định danh chủ thể mà token đề cập trong phạm vi ngữ nghĩa do issuer và token profile định nghĩa.

Trong JWT access token có người dùng:

~~~json
{
  "iss": "https://identity.example.test/realms/shop",
  "sub": "user-9f1a",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
~~~

Spring Security JWT Resource Server thường tạo `JwtAuthenticationToken` với:

~~~text
name = jwt.getSubject()
~~~

Điều này phù hợp với nhu cầu gắn tên principal vào chủ thể đã được nhà phát hành xác nhận. Nhưng có hai giới hạn quan trọng:

1. **`sub` không nhất thiết là username dễ đọc.** Nó có thể là chuỗi nội bộ, UUID hoặc định danh pairwise.
2. **`sub` không nhất thiết đại diện người dùng cuối.** Trong grant `client_credentials`, token có thể đại diện Client/dịch vụ; ngữ nghĩa `sub` phụ thuộc nhà phát hành và token profile.

### 3.1. `sub` có thể khác nhau giữa các issuer

Issuer A phát:

~~~json
{"iss":"https://id-a.example.test","sub":"123"}
~~~

Issuer B cũng phát:

~~~json
{"iss":"https://id-b.example.test","sub":"123"}
~~~

Không được suy ra hai token này thuộc **cùng một người dùng**. Định danh thông thường nên bao gồm **nguồn cấp**:

~~~text
Identity key = (issuer, subject)
             = (iss, sub)
~~~

Khi dùng OIDC, `sub` có thể là **pairwise subject** theo Client/sector; cùng một con người có thể có nhiều `sub` ở những ứng dụng khác nhau. API không được tự giả định `sub` là định danh toàn cầu nếu không có hợp đồng định danh phù hợp.

### 3.2. `sub` không tự chứng minh quyền

Token có `sub = user-9f1a` không tự cấp quyền xem toàn bộ đơn hàng của `user-9f1a`, chưa nói tới đơn hàng người khác. Resource Server còn phải kiểm tra `aud`, scope/authorities, tenant, owner và chính sách cụ thể. `getName()` là dữ liệu tên sau xác thực, không phải kết luận authorization.

## 4. Những claim có thể được chọn làm principal name

Việc chọn tên principal phụ thuộc **mục đích sử dụng** và **độ ổn định của claim**.

| Claim | Phù hợp cho | Rủi ro khi dùng làm `getName()` |
| --- | --- | --- |
| **`sub`** | Định danh chủ thể theo issuer; lựa chọn mặc định hợp lý | Cần kết hợp issuer khi liên hệ dữ liệu nhiều issuer; đôi khi không dễ đọc |
| **`preferred_username`** | Hiển thị username do hệ thống định danh cấp | Có thể đổi tên, trùng giữa tenant/issuer hoặc không tồn tại |
| **`email`** | Hiển thị/liên hệ khi hợp đồng cho phép | Có thể đổi, chưa xác minh, bị tái sử dụng; mang dữ liệu cá nhân |
| **`name`** | Tên hiển thị trên giao diện | Dễ trùng, thay đổi, không nên làm khóa định danh |
| **`user_id`** (custom) | Khóa nội bộ nếu issuer cam kết ổn định/duy nhất | Không phải claim JWT chuẩn; phải xác minh định nghĩa, scope và nguồn cấp |
| **`client_id`** | Nhận diện OAuth2 Client trong các luồng phù hợp | Không đồng nghĩa người dùng; không thay thế `sub` của user token |
| **`tenant_id`** (custom) | Xác định ngữ cảnh tenant trong policy | Không phải danh tính chủ thể; nhiều người dùng chia sẻ tenant |

**Tên dễ đọc không đồng nghĩa khóa danh tính đáng tin.** Nếu người dùng đổi username hoặc email, mọi record gắn theo giá trị cũ có thể không còn ánh xạ đúng. Hai user dùng chung tên hiển thị càng không thể được gộp thành một principal nghiệp vụ.

### 4.1. Khi nào nên giữ mặc định `sub`?

Nên ưu tiên `sub` khi:

- API bảo vệ dữ liệu theo **chủ thể được issuer định danh**.
- Cần gắn audit với một ID có tính ổn định theo hợp đồng.
- Hệ thống cần ánh xạ danh tính sang một user record nội bộ.
- Không có yêu cầu rõ ràng rằng `Authentication.getName()` phải hiển thị username.

Với nhiều issuer, lưu thêm issuer hoặc chuẩn hóa thành **internal user ID** sau bước ánh xạ tin cậy. Không nên đổi principal name chỉ để biến `sub` thành tên đẹp trong log.

### 4.2. Khi nào có thể chọn `preferred_username`?

Có thể khi hệ thống có hợp đồng rõ rằng:

- Access token **luôn chứa** `preferred_username`.
- Claim đó do **issuer đáng tin** phát hành và không cho Client tự đặt.
- `getName()` chỉ được dùng làm **tên trình bày hoặc tương thích hệ thống**, không phải khóa dữ liệu nhạy cảm.
- Nếu có nhiều tenant/issuer, code không suy diễn username là duy nhất toàn hệ thống.

Ví dụ một ứng dụng cũ đã chuẩn hóa principal name là employee login ID, và nhà phát hành đảm bảo claim `employee_id` bất biến. Khi ấy việc chọn `employee_id` có thể hợp lý **nếu hợp đồng định danh được quản trị chặt chẽ**.

### 4.3. Khi nào không nên chọn claim khác?

Không nên chuyển `getName()` sang `email`, `name` hay role chỉ để code `@PreAuthorize` ngắn hơn. Đặc biệt tránh:

~~~text
authentication.getName() = "ADMIN"
~~~

chỉ vì caller có role admin. Một role không phải danh tính cá nhân hoặc dịch vụ. **Principal name**, **GrantedAuthority** và **resource policy** cần duy trì ý nghĩa riêng.

## 5. Cấu hình mặc định của Spring Security JWT Resource Server

Ví dụ dùng **Spring Boot 3 / Spring Security 6**, Orders API nhận JWT access token đã ký. Dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${OAUTH_ISSUER_URI}

app:
  security:
    expected-audience: ${OAUTH_API_AUDIENCE}
~~~

Biến môi trường ví dụ:

~~~text
OAUTH_ISSUER_URI=https://identity.example.test/realms/shop
OAUTH_API_AUDIENCE=orders-api
~~~

`issuer-uri` chỉ là một phần cấu hình. Resource Server phải xác minh chữ ký, issuer, thời hạn và **audience đúng API**. Cách khai báo audience cụ thể phụ thuộc cấu hình/decoder, ví dụ được minh họa ở mục 9. Đừng cho rằng cùng issuer nghĩa là mọi token đều dành cho Orders API.

Security filter chain:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Ví dụ giả định `/api/**` là REST API chỉ nhận Bearer token, không dùng session cookie để xác thực. Vì vậy cấu hình ví dụ tắt CSRF trong filter chain này và dùng stateless session. Nếu cùng ứng dụng phục vụ trình duyệt qua cookie, phải xử lý session/CSRF ở filter chain phù hợp.

Khi không cung cấp `JwtAuthenticationConverter` riêng, Spring Security sử dụng cách ánh xạ thông dụng: `sub` làm principal name, claim `scope`/`scp` hợp lệ thành authorities `SCOPE_...`.

## 6. Tùy chỉnh `getName()` bằng `JwtAuthenticationConverter#setPrincipalClaimName`

Đây là cách trực tiếp nếu nhà phát hành luôn cung cấp một **claim dạng chuỗi** làm tên principal.

### 6.1. Chọn `preferred_username`

Giả sử token đã xác minh có:

~~~json
{
  "iss": "https://identity.example.test/realms/shop",
  "sub": "user-9f1a",
  "aud": ["orders-api"],
  "preferred_username": "linh.nguyen",
  "scope": "orders.read"
}
~~~

Cấu hình converter:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;

@Configuration
class PrincipalNameConfiguration {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtAuthenticationConverter converter =
                new JwtAuthenticationConverter();

        converter.setPrincipalClaimName("preferred_username");
        return converter;
    }
}
~~~

**Quan trọng:** Chỉ tạo bean converter chưa chắc khiến mọi `SecurityFilterChain` tự động sử dụng nó. Cần **gắn converter** vào cấu hình JWT Resource Server:

~~~java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        JwtAuthenticationConverter jwtAuthenticationConverter)
        throws Exception {

    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt ->
            jwt.jwtAuthenticationConverter(jwtAuthenticationConverter)))
        .build();
}
~~~

Đoạn trên là **biến thể thay thế** bean `apiSecurity` ở mục 5, không phải một bean thứ hai cần cùng khai báo trong dự án. Khi áp dụng, gộp đầy đủ các rule, CSRF/session theo mô hình ứng dụng vào đúng filter chain.

Khi token đã được xác minh, converter tạo `JwtAuthenticationToken` với tên lấy từ claim `preferred_username`. Sau đó:

~~~text
authentication.getName()   -> linh.nguyen
jwt.getSubject()           -> user-9f1a
authentication.authorities -> vẫn có SCOPE_orders.read
~~~

Gọi `setPrincipalClaimName(...)` **không tự sửa scope hoặc roles mapping**, không đổi JWT payload và không ảnh hưởng quá trình xác minh chữ ký. Nó chủ yếu thay chuỗi principal name do authentication cung cấp.

### 6.2. Tách tên principal thành property cấu hình

Nếu hợp đồng với issuer định nghĩa claim tên principal là một giá trị cấu hình cố định theo triển khai:

~~~yaml
app:
  security:
    principal-claim: sub
~~~

Code:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;

@Configuration
class PrincipalClaimConfig {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter(
            @Value("${app.security.principal-claim}") String claimName) {

        JwtAuthenticationConverter converter =
                new JwtAuthenticationConverter();
        converter.setPrincipalClaimName(claimName);
        return converter;
    }
}
~~~

Tại filter chain, vẫn phải gắn bean này như mục 6.1.

**Không nên cho mỗi request tự chọn claim** bằng header, query parameter hoặc payload:

~~~http
X-Principal-Claim: roles
~~~

Tên claim được dùng để xác định principal phải do **hợp đồng hệ thống và cấu hình tin cậy** quyết định, không phải do caller yêu cầu.

### 6.3. Claim vắng mặt hoặc sai kiểu

Nếu cấu hình `principal-claim: preferred_username` nhưng token service-to-service không có claim này, `getName()` có thể không mang giá trị mong muốn; hành vi chi tiết có thể khác theo converter/customization. Không nên dựa vào giả định framework sẽ **tự fallback sang `sub`**.

Với claim quan trọng, có hai cách thiết kế:

1. **Bắt buộc claim theo profile**: Authorization Server cam kết phát nó, còn Resource Server có validator từ chối token thiếu/sai kiểu trước khi dùng principal name.
2. **Tùy biến converter theo ngữ cảnh**: Chọn tên theo một chính sách xác định từ token đã xác minh, với fallback an toàn, tách rõ user token và service token.

Nếu claim là object nested (ví dụ `realm_access.roles`), `setPrincipalClaimName("realm_access.roles")` **không tự hiểu đường dẫn dạng dấu chấm** như một JSONPath. Method này nhận **tên claim** theo converter; các yêu cầu đọc nested claim cần converter hoặc logic ánh xạ được thiết kế riêng.

## 7. Sử dụng `Authentication.getName()` trong controller và service

Có nhiều cách lấy thông tin người gọi từ Spring Security:

| Cách truy cập | Trả về gì? | Khi nào dùng? |
| --- | --- | --- |
| Tham số `Authentication` | Authentication của request đã qua security chain | Cần `getName()` và authorities |
| Tham số `Principal` | Giao diện principal có `getName()` | Chỉ cần tên principal, không muốn phụ thuộc implementation |
| `@AuthenticationPrincipal Jwt` | Đối tượng JWT đã được xác minh trong JWT Resource Server | Cần đọc `iss`, `sub`, custom claims |
| `SecurityContextHolder` | SecurityContext hiện hành theo ngữ cảnh thread | Khi code không ở web controller; cần lưu ý ngữ cảnh bất đồng bộ |
| `@CurrentSecurityContext` | Lấy SecurityContext/authentication qua annotation | Khi muốn khai báo rõ dữ liệu bảo mật ở tham số |

### 7.1. Controller có thể đọc cả principal name và subject

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
class IdentityController {

    @GetMapping("/whoami")
    IdentityView whoAmI(
            Authentication authentication,
            @AuthenticationPrincipal Jwt jwt) {

        return new IdentityView(
                authentication.getName(),
                jwt.getIssuer().toString(),
                jwt.getSubject(),
                jwt.getClaimAsString("preferred_username"));
    }

    record IdentityView(
            String principalName,
            String issuer,
            String subject,
            String displayUsername) {}
}
~~~

Trong ví dụ, `Authentication.getName()` có thể thay đổi khi converter đổi claim, còn `jwt.getSubject()` vẫn đọc `sub`. Endpoint `whoami` chỉ là minh họa: khi triển khai thật, nên cân nhắc claim nào được phép trả ra và tránh đưa thông tin nhạy cảm vào phản hồi.

### 7.2. Tham số `Principal`

Nếu chỉ muốn tên đã được cấu hình:

~~~java
import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping("/api/caller-name")
String callerName(Principal principal) {
    return principal.getName();
}
~~~

Đây là API tiện dụng cho trình bày, nhưng vẫn không bảo đảm `getName()` là internal user ID. Phải biết dạng authentication nào đã xác thực request.

### 7.3. `SecurityContextHolder` và ngữ cảnh bất đồng bộ

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

if (authentication == null) {
    // Không có authentication phù hợp trong context hiện hành.
}
~~~

Security context thường gắn với quá trình xử lý request/thread theo cấu hình Spring Security. Trong `@Async`, executor tự tạo thread, scheduled job, message listener hoặc reactive flow, **không được giả định security context luôn tự động được truyền theo**.

Ở web/controller và tầng service, thường dễ kiểm soát hơn khi nhận `Authentication`/`Jwt` từ ngữ cảnh đã xác thực, xây một **CallerContext** kiểu dữ liệu rõ ràng rồi truyền vào các service cần quyết định quyền. Nếu cần propagate security context qua executor, hãy sử dụng cơ chế tích hợp của Spring Security phù hợp, không tự copy token chưa xác minh.

## 8. Chọn tên hiển thị khác với khóa định danh dữ liệu

Một lỗi phổ biến:

~~~java
// NGUY HIỂM nếu authentication.getName() là preferred_username hoặc email!
String ownerId = authentication.getName();
Order order = orderRepository.findByOwnerId(ownerId);
~~~

Giả sử `ownerId` trong database là `user-9f1a`, nhưng converter vừa đổi principal name thành `linh.nguyen`. Việc tra cứu giờ không đúng. Nếu username có thể đổi, trùng hoặc bị gán lại, nguy cơ lớn hơn một lỗi “không tìm thấy dữ liệu”.

### 8.1. Dùng định danh có ngữ nghĩa ổn định

Với token dành cho người dùng được xác minh:

~~~java
import org.springframework.security.oauth2.jwt.Jwt;

record IssuedSubject(String issuer, String subject) {

    static IssuedSubject from(Jwt jwt) {
        return new IssuedSubject(
                jwt.getIssuer().toString(),
                jwt.getSubject());
    }
}
~~~

Định danh `IssuedSubject` được tạo từ hai claim **đã được Resource Server xác minh theo hợp đồng**. Nếu có một user record nội bộ như `appUserId = 8346`, ứng dụng có thể duy trì bảng ánh xạ:

~~~text
(iss, sub)                            -> internal appUserId
(https://identity.../shop, user-9f1a) -> 8346
~~~

Lúc này:

- `Authentication.getName()` phục vụ tên principal theo quy ước Security.
- `(iss, sub)` phục vụ định danh chủ thể phía issuer.
- `appUserId` là khóa nội bộ do ứng dụng quản lý.
- Quyền truy cập Order 42 được kiểm tra theo internal ID, tenant và điều kiện nghiệp vụ.

Tùy hệ thống, định danh user có thể trực tiếp là `sub` hoặc dùng một ID nội bộ; điểm cốt lõi là **đừng trộn tên hiển thị với khóa truy cập dữ liệu**.

### 8.2. Nếu đổi username thì chuyện gì xảy ra?

Giả sử:

~~~text
Ban đầu:
  sub = user-9f1a
  preferred_username = linh.nguyen

Sau đổi username:
  sub = user-9f1a
  preferred_username = linh.n
~~~

Nếu database liên kết owner bằng `sub` hoặc internal user ID, quyền trên đơn hàng không bị ảnh hưởng. Nếu liên kết bằng `getName()` với `preferred_username`, các record cũ có thể không còn khớp. Điều này lý giải vì sao **tên principal cho UI và định danh authorization nên tách nhau**.

## 9. Xác minh token trước khi tin principal name

Việc lựa chọn principal claim chỉ có ý nghĩa sau khi token đã được xác thực. Resource Server phải kiểm tra **chữ ký**, **issuer**, **audience**, **thời hạn**, **token profile** và các điều kiện được thỏa thuận.

### 9.1. Cấu hình một `JwtDecoder` có kiểm tra audience

Ví dụ dùng JWKS endpoint đáng tin, với issuer và audience từ cấu hình:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${OAUTH_ISSUER_URI}
          jwk-set-uri: ${OAUTH_JWKS_URI}

app:
  security:
    expected-audience: ${OAUTH_API_AUDIENCE}
~~~

Decoder:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class TokenValidationConfig {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}")
            String issuer,
            @Value("${spring.security.oauth2.resourceserver.jwt.jwk-set-uri}")
            String jwksUri,
            @Value("${app.security.expected-audience}")
            String expectedAudience) {

        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withJwkSetUri(jwksUri).build();

        OAuth2TokenValidator<Jwt> standard =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience().contains(expectedAudience)
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(
                            "invalid_token",
                            "Unexpected token audience",
                            null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        standard,
                        audience));
        return decoder;
    }
}
~~~

URI JWKS phải lấy từ metadata hoặc tài liệu của nhà phát hành tin cậy; đây không phải endpoint mặc định cố định cho mọi Authorization Server. Cần giới hạn thuật toán JWS được chấp nhận và token profile theo hợp đồng thật. Nếu tự cấu hình decoder, phải giữ các validator cần thiết; không thay toàn bộ validator bằng kiểm tra một claim tên principal.

### 9.2. Claim làm principal name không tạo ra quyền

Ví dụ:

~~~text
JWT đã xác minh:
  sub = user-9f1a
  preferred_username = linh.nguyen
  scope = orders.read

JwtAuthenticationConverter:
  principalClaimName = preferred_username

Kết quả:
  getName() = linh.nguyen
  authorities gồm SCOPE_orders.read
~~~

Để gọi `POST /api/orders` khi API yêu cầu `orders.write`, caller vẫn thiếu quyền ghi. Đổi `getName()` thành `linh.nguyen` không thay scope. Để đọc đơn của người khác, caller vẫn phải đáp ứng policy ownership hoặc role/permission được định nghĩa.

## 10. Quyền truy cập tài nguyên không được phụ thuộc bừa vào `getName()`

Một biểu thức dễ viết:

~~~java
@PreAuthorize("#ownerId == authentication.name")
~~~

Nó **chỉ hợp lệ** nếu hợp đồng ứng dụng xác định `ownerId` trong request và `Authentication.getName()` dùng **chính xác cùng loại định danh**. Nếu `getName()` đổi từ `sub` sang username, hoặc request `ownerId` do Client tự khai, biểu thức có thể cho kết quả sai.

### 10.1. Tách scope và quyền trên bản ghi

Giả sử:

~~~text
GET /api/orders/42
  Cần scope orders.read
  VÀ token phải dành cho orders-api
  VÀ đơn 42 thuộc subject/tenant được phép
~~~

Một ví dụ method security:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
class OrderQueryService {

    private final OrderRepository orders;

    OrderQueryService(OrderRepository orders) {
        this.orders = orders;
    }

    @PreAuthorize(
        "hasAuthority('SCOPE_orders.read') and " +
        "@orderAccess.canRead(authentication, #orderId)")
    public OrderDto readOrder(String orderId) {
        return orders.findDtoById(orderId)
                .orElseThrow(OrderNotFoundException::new);
    }
}
~~~

Bean policy đọc thông tin định danh từ **JwtAuthenticationToken đã qua xác minh**, thay vì dùng chuỗi principal name:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Component;

@Component("orderAccess")
class OrderAccess {

    private final OrderRepository orders;

    OrderAccess(OrderRepository orders) {
        this.orders = orders;
    }

    public boolean canRead(
            Authentication authentication,
            String orderId) {

        if (!(authentication instanceof JwtAuthenticationToken token)) {
            return false;
        }

        Jwt jwt = token.getToken();
        if (jwt.getIssuer() == null || jwt.getSubject() == null) {
            return false;
        }

        return orders.isVisibleToSubject(
                orderId,
                jwt.getIssuer().toString(),
                jwt.getSubject());
    }
}
~~~

`OrderRepository`, `OrderDto` và `OrderNotFoundException` trong ví dụ là **thành phần nghiệp vụ**, không phải class Spring Security có sẵn. Phương thức `isVisibleToSubject` cần kiểm tra dữ liệu chính thức của bản ghi, tenant, vai trò và các điều kiện thích hợp; nếu có nhiều tenant, chỉ so khớp issuer/subject chưa đủ. `@EnableMethodSecurity` phải được bật để `@PreAuthorize` có hiệu lực.

Lợi ích của cấu trúc này: đổi principal name sang `preferred_username` cho mục đích hiển thị **không làm thay đổi logic quyền dựa trên subject ổn định**.

### 10.2. Khi API hỗ trợ cả user token và service token

Trong `client_credentials`, token có thể trông như:

~~~json
{
  "iss": "https://identity.example.test/realms/shop",
  "sub": "nightly-sync",
  "client_id": "nightly-sync",
  "aud": ["orders-api"],
  "scope": "orders.sync"
}
~~~

`sub = nightly-sync` không được tự suy ra là một khách hàng sở hữu đơn hàng. Với các endpoint chỉ dành cho **người dùng**, policy nên từ chối loại chủ thể dịch vụ nếu chưa có quy tắc phù hợp. Với endpoint dịch vụ, kiểm tra danh tính Client, scope, audience và quyền service riêng.

Nếu dùng chung converter `principalClaimName = preferred_username`, token dịch vụ có thể không có claim này. Đây là lý do thường nên **giữ `sub` làm principal name mặc định**, rồi xử lý loại chủ thể/Client bằng policy rõ ràng, thay vì ép mọi token phải có “username người dùng”.

## 11. Nhiều issuer: principal name giống nhau không có nghĩa cùng danh tính

Ví dụ Orders API tin hai issuer cho hai nhóm khách hàng:

~~~text
Issuer A:
  iss = https://id-a.example.test
  sub = 123
  preferred_username = admin

Issuer B:
  iss = https://id-b.example.test
  sub = 123
  preferred_username = admin
~~~

Nếu ứng dụng dùng:

~~~java
String currentUser = authentication.getName();
~~~

thì với converter dùng `sub`, cả hai có thể trả `123`; với converter dùng `preferred_username`, cả hai có thể trả `admin`. Nhưng đó là **hai danh tính khác nhau** nếu issuer/contract khác nhau.

### 11.1. Ràng buộc danh tính với nguồn phát hành

Mô hình dữ liệu nên có khóa duy nhất tương ứng:

~~~text
Issuer A + sub 123 -> internalUserId = 7001
Issuer B + sub 123 -> internalUserId = 8824
~~~

Không được tạo một map global như:

~~~text
sub 123 -> một user nội bộ bất kỳ
~~~

trừ khi có cơ chế federation/linking đã được phê duyệt. Trong multi-issuer Resource Server, từng issuer cần có bộ khóa, audience, token profile, claim mapping và chính sách riêng. Không trộn role của issuer A với role của issuer B chỉ vì cùng chuỗi `ADMIN`.

### 11.2. Nếu muốn `getName()` thể hiện issuer và subject

`JwtAuthenticationConverter#setPrincipalClaimName(...)` chọn **một claim**, không tự nối `iss` và `sub`. Nếu có nhu cầu tên dạng `issuer|subject`, cần một **converter tùy chỉnh** xây `JwtAuthenticationToken` với tên do ứng dụng tính từ các claim đã xác minh.

Ví dụ:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

class IssuerSubjectJwtConverter
        implements Converter<Jwt, AbstractAuthenticationToken> {

    private final JwtGrantedAuthoritiesConverter scopes =
            new JwtGrantedAuthoritiesConverter();

    @Override
    public AbstractAuthenticationToken convert(Jwt jwt) {
        String issuer = jwt.getIssuer().toString();
        String subject = jwt.getSubject();

        // Chỉ áp dụng sau khi decoder đã validate JWT.
        String principalName = issuer + "|" + subject;

        return new JwtAuthenticationToken(
                jwt,
                scopes.convert(jwt),
                principalName);
    }
}
~~~

Gắn converter:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt ->
    jwt.jwtAuthenticationConverter(
        new IssuerSubjectJwtConverter())))
~~~

Đây là **một phương án tùy chọn**, không phải bắt buộc. Khi dùng chuỗi ghép để làm khóa nghiệp vụ, phải có cách mã hóa/tách trường không mơ hồ; tốt hơn nên giữ `issuer` và `subject` thành **hai trường riêng** trong domain model. Mặt khác, converter này giả định issuer/subject bắt buộc có mặt và hợp lệ; policy/validator phải xác nhận điều đó.

### 11.3. Tenant là chiều dữ liệu khác

Ngoài issuer và subject, ứng dụng multi-tenant còn cần xác định quyền của chủ thể trong **tenant cụ thể**. Có thể một người là admin của tenant A nhưng chỉ là khách hàng của tenant B. Không thể xử lý an toàn tình huống ấy bằng cách cho `getName()` bằng `"tenant-A/admin"` mà bỏ qua dữ liệu tenant và policy trên resource.

## 12. OIDC login và Resource Server không nhất thiết có cùng principal name

Trong một kiến trúc gồm:

- **Shop Web** đăng nhập bằng Spring Security `oauth2Login()`.
- **Orders API** bảo vệ endpoint bằng `oauth2ResourceServer().jwt()`.

Shop Web xử lý OIDC ID token và có thể tạo `OAuth2AuthenticationToken` hoặc một principal `OidcUser`. Orders API lại nhận **OAuth 2.0 access token** và tạo `JwtAuthenticationToken`.

| Nội dung | OIDC Client/login | JWT Resource Server |
| --- | --- | --- |
| Token chính phục vụ tác vụ | ID token/OIDC user information | OAuth 2.0 access token |
| Authentication thường gặp | `OAuth2AuthenticationToken` / OIDC principal | `JwtAuthenticationToken` |
| Cách tạo tên | Theo `OidcUser` và cấu hình name attribute của Client | Theo `JwtAuthenticationConverter`, mặc định `sub` |
| Audience cần kiểm tra | ID token dành cho OIDC Client | Access token dành cho Resource Server |
| Mục tiêu | Xác nhận đăng nhập vào Client | Xác minh caller và áp dụng quyền API |

Không nên giả định:

~~~text
shopWebAuthentication.getName()
    == ordersApiAuthentication.getName()
~~~

trong mọi kiến trúc. Hai đối tượng có thể được tạo từ những token khác mục đích, token profiles khác nhau và cấu hình principal khác nhau. Nếu cần liên kết danh tính xuyên hệ thống, hãy định nghĩa **cách ánh xạ subject/issuer** và quan hệ đăng nhập theo OIDC, không dựa vào việc hai chuỗi tên nhìn giống nhau.

Đặc biệt, **ID token không được gửi làm Bearer access token tới API**. Cùng issuer và cùng `sub` không có nghĩa hai loại token có thể thay thế nhau.

## 13. Opaque token và các authentication khác

Một số Resource Server không dùng JWT mà dùng **opaque access token** được xác minh qua introspection. Khi đó luồng xác thực khác, và `JwtAuthenticationConverter#setPrincipalClaimName(...)` **không tác động** lên authentication của opaque token.

Ví dụ cấu hình opaque:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaque-token:
          introspection-uri: ${INTROSPECTION_URI}
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

Với opaque token, thông tin principal có thể dựa trên các attributes được introspection trả về và converter hoặc implementation của Spring Security đang dùng. Nếu ứng dụng cần chuẩn hóa name giữa JWT và opaque token, phải thiết kế **hai đường ánh xạ** và kiểm tra kết quả, không giả định một `JwtAuthenticationConverter` dùng chung cho cả hai.

Tương tự, một hệ thống sử dụng API key hoặc session authentication có thể có `Authentication.getName()` được tạo từ một nguồn khác. Khi viết thư viện chung để lấy current caller, nên thống nhất **kiểu caller** (user/service, issuer, subject, Client, tenant) thay vì chỉ trông vào một chuỗi name.

## 14. Kiểm thử lựa chọn principal claim

Một bài test tốt cần phân biệt **unit test converter** và **integration test xác thực JWT thật**.

### 14.1. Unit test converter: mặc định và tùy chỉnh

Ví dụ JUnit Jupiter:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

class JwtPrincipalNameTest {

    private Jwt sampleJwt() {
        return Jwt.withTokenValue("test-token-not-for-production")
                .header("alg", "RS256")
                .claim("iss", "https://identity.example.test/realms/shop")
                .claim("sub", "user-9f1a")
                .claim("aud", java.util.List.of("orders-api"))
                .claim("preferred_username", "linh.nguyen")
                .claim("scope", "orders.read")
                .build();
    }

    @Test
    void defaultNameUsesSubject() {
        JwtAuthenticationConverter converter =
                new JwtAuthenticationConverter();

        var authentication = converter.convert(sampleJwt());
        assertEquals("user-9f1a", authentication.getName());
    }

    @Test
    void customNameDoesNotChangeSubject() {
        JwtAuthenticationConverter converter =
                new JwtAuthenticationConverter();
        converter.setPrincipalClaimName("preferred_username");

        JwtAuthenticationToken authentication =
                (JwtAuthenticationToken) converter.convert(sampleJwt());

        assertEquals("linh.nguyen", authentication.getName());
        assertEquals("user-9f1a", authentication.getToken().getSubject());
    }
}
~~~

Đây là **unit test ánh xạ principal name**. `Jwt.withTokenValue(...)` tự tạo một đối tượng `Jwt` phục vụ kiểm thử và **không xác minh chữ ký**; không được kết luận bài test này đã chứng minh issuer/JWKS/audience validation.

### 14.2. Test claim bị thiếu và sai định dạng

Nên có test cho các trường hợp:

| Token profile / tình huống | Kỳ vọng thiết kế |
| --- | --- |
| User token có `sub` hợp lệ | Principal name mặc định bằng `sub` |
| User token có `preferred_username` hợp lệ, converter tùy chỉnh | `getName()` theo claim đã chọn |
| Token không có claim mà converter yêu cầu | Bị từ chối theo validator hoặc xử lý fallback đã định nghĩa, không lặng lẽ gán quyền |
| Claim được chọn có kiểu không phù hợp | Không ép kiểu tùy tiện, phải có policy rõ |
| Hai issuer cùng `sub` | Domain identity vẫn phân biệt bằng issuer |
| Username thay đổi, `sub` giữ nguyên | Quyền nghiệp vụ gắn vào ID ổn định không đổi |
| Token client credentials không có username | Áp dụng service identity, không giả định người dùng |
| Token có scope khác nhau nhưng cùng `getName()` | Authorities và quyền phải thay đổi theo scope thực tế |

### 14.3. Integration test với JWT thật

Ở integration test, hãy dùng JWT ký thật bằng test key, mock JWKS/issuer đáng tin và gọi API bằng `Authorization: Bearer ...`:

1. Token có chữ ký, issuer, audience và thời hạn hợp lệ → decoder tạo JWT; converter chọn đúng principal claim.
2. Token bị sửa payload sau khi ký → JWT decoder từ chối; không có principal đáng tin.
3. Token hợp lệ nhưng thiếu scope endpoint → authentication có thể thành công, authorization phải từ chối.
4. Token hợp lệ và scope đúng nhưng sai owner/tenant → policy dữ liệu từ chối.
5. Token do issuer khác phát với cùng `sub` → không được gộp danh tính.

`SecurityMockMvcRequestPostProcessors.jwt()` hữu ích khi muốn test riêng rule HTTP và converter được mock hoặc cung cấp, nhưng **không xác minh chữ ký JWT thật**. Đừng nhầm test mock principal với kiểm thử bảo mật JWS/JWKS.

## 15. Ảnh hưởng của việc đổi principal name trong hệ thống đang chạy

Thay:

~~~text
principalClaimName = sub
~~~

thành:

~~~text
principalClaimName = preferred_username
~~~

không chỉ là một thay đổi giao diện nếu code hiện tại dùng `getName()` trong nhiều nơi.

### 15.1. Những nơi cần hiểu tác động

| Nơi sử dụng | Rủi ro khi đổi `getName()` | Hướng thiết kế |
| --- | --- | --- |
| Audit log | Bản ghi cũ và mới có tên khác cho cùng chủ thể | Lưu identity key ổn định; tên hiển thị là thuộc tính riêng |
| Database owner/creator | Không tìm thấy hoặc tìm sai record | Dùng internal user ID hoặc `(iss, sub)` |
| Cache key | Dữ liệu lưu theo username cũ, va chạm giữa issuer | Namespace theo issuer/subject/tenant |
| `@PreAuthorize` | So sánh tên không còn đúng loại ID | So sánh identity được chuẩn hóa và chính sách đối tượng |
| Job/event | Consumer hiểu principalName là email/user ID | Version hóa schema sự kiện; thêm trường identity tường minh |
| Log/metric | Tăng cardinality hoặc lộ PII | Hạn chế trường nhạy cảm; dùng opaque/correlation ID phù hợp |
| User-facing UI | Tên hiển thị thay đổi | Đọc claim hiển thị riêng hoặc lấy từ profile service |
| Dịch vụ thứ ba | Mapping principal name không còn khớp | Thống nhất contract hoặc triển khai migration có kiểm soát |

Điều này đặc biệt quan trọng khi một số service vẫn coi `getName() = sub`, trong khi service khác chuyển sang `preferred_username`. Nếu các service trao đổi tên principal qua header hoặc event mà không có schema rõ ràng, chúng có thể hiểu sai danh tính.

### 15.2. Không đưa username vào audit như định danh duy nhất

Một bản audit dễ gây mơ hồ:

~~~json
{
  "action": "ORDER_READ",
  "principal": "linh.nguyen",
  "orderId": "42"
}
~~~

Một mô hình rõ ràng hơn:

~~~json
{
  "action": "ORDER_READ",
  "issuer": "https://identity.example.test/realms/shop",
  "subject": "user-9f1a",
  "displayUsername": "linh.nguyen",
  "orderId": "42"
}
~~~

Đây là ví dụ cấu trúc log/audit; phải điều chỉnh theo quy tắc quyền riêng tư và retention của tổ chức. Với dữ liệu nhạy cảm, không nhất thiết ghi mọi claim nguyên văn. Cần tránh log nguyên Bearer token, session cookie hoặc credential.

## 16. Các lỗi thường gặp

### “`Authentication.getName()` luôn trả username đăng nhập”

Không đúng. Trong JWT Resource Server, mặc định thường là `sub`. Trong các loại authentication khác, implementation có thể chọn tên khác.

### “Cứ đặt principal claim thành `email` là đủ định danh”

Email có thể thay đổi, trùng trong các ngữ cảnh khác nhau hoặc chưa được xác minh theo hợp đồng. Nó không phải khóa danh tính bất biến mặc định.

### “Đổi principal claim cũng đổi `jwt.getSubject()`”

Không. `JwtAuthenticationConverter` có thể đổi **name của Authentication**, không sửa payload đã ký.

### “Chỉ cần tạo bean converter, Spring Security tự gắn cho mọi filter chain”

Không nên giả định như vậy. Hãy cấu hình rõ `jwt.jwtAuthenticationConverter(...)` cho filter chain nhận Bearer JWT đang dùng.

### “`setPrincipalClaimName("realm_access.roles")` tự đọc nested claim”

Không. Đây là tên claim, không phải biểu thức điều hướng JSON tùy ý. Dữ liệu nested cần converter phù hợp.

### “Dùng `@AuthenticationPrincipal Jwt` tức là đã có quyền trên mọi dữ liệu”

Không. JWT đã được xác minh có thể có scope giới hạn, và quyền trên từng record/tenant vẫn phải được kiểm tra.

### “Hai token có `getName()` giống nhau là cùng một người”

Không nếu issuer hoặc ngữ cảnh danh tính khác nhau. Dùng issuer và subject theo hợp đồng, thêm tenant hoặc ánh xạ user nội bộ khi cần.

### “Chỉ cần sửa `getName()` là role sẽ đổi theo”

Không. Authorities phụ thuộc các claim và converter quyền, ví dụ `scope` → `SCOPE_orders.read`; principal name là một phần khác.

### “`client_credentials` luôn có username người dùng”

Không. Token có thể đại diện Client/service. Không áp dụng quyền của người dùng cuối nếu token không biểu diễn loại chủ thể đó theo hợp đồng.

### “Decode payload rồi lấy `sub` là tương đương `Authentication.getName()`”

Không. Decode Base64URL không xác minh chữ ký hay issuer/audience; còn `Authentication` của Resource Server chỉ được tin sau quá trình JWT validation.

## 17. Mẫu quy ước principal cho một hệ thống

Một hợp đồng tích hợp có thể ghi:

~~~yaml
# Tài liệu hợp đồng minh họa; không phải cấu hình Spring tự đọc.
api: orders-api
issuer: https://identity.example.test/realms/shop
token_use: oauth2_access_token
expected_audience: orders-api
principal:
  spring_get_name_claim: sub
  identity_key:
    - iss
    - sub
  display_claim: preferred_username
  internal_user_mapping: issuer_subject_to_app_user_id
  service_principal_policy: separate_from_end_user
authorization:
  required_scope_for_read: orders.read
  data_policy: check_owner_and_tenant
~~~

Từ hợp đồng đó, team triển khai:

1. **Authorization Server:** phát access token đúng issuer/audience, có `sub` nhất quán và những claim phụ theo thỏa thuận.
2. **Resource Server:** xác minh token, giữ `getName()` theo `sub` hoặc claim được chọn một cách có chủ đích.
3. **Ứng dụng:** dùng `(iss, sub)` để tìm user nội bộ; lấy display username từ claim hoặc profile service khi cần.
4. **Policy:** kiểm tra scope và quyền trên tài nguyên, không lấy principal name làm bằng chứng admin hay ownership khi loại định danh không khớp.
5. **Kiểm thử:** xác nhận default/custom converter, token thiếu claim, nhiều issuer, service token và thay đổi username.

### Những câu hỏi cần quyết định trước khi đổi claim

- `getName()` đang được dùng để hiển thị hay làm khóa database/audit?
- Claim mới có luôn tồn tại trong **access token** (không chỉ ID token) hay không?
- Claim mới có ổn định và duy nhất trong phạm vi mà ứng dụng cần không?
- Có nhiều issuer, nhiều tenant hoặc luồng `client_credentials` không?
- Token profile nào được chấp nhận, và validator nào bảo đảm claim cần thiết?
- Các service khác có đang coi tên principal là `sub` không?
- Có cần ánh xạ identity key sang internal user ID thay vì đổi principal name không?
- Quyền hiện tại có phụ thuộc vào `authentication.name` trong SpEL hay không?

---

**Kết luận:** `Authentication.getName()` trả về **tên principal theo loại Authentication và converter đang sử dụng**. Với Spring Security JWT Resource Server, mặc định tên này thường đến từ claim **`sub`**, và có thể đổi bằng **`JwtAuthenticationConverter#setPrincipalClaimName(...)`** rồi gắn converter vào `SecurityFilterChain`. Tuy nhiên, **principal name không đồng nghĩa danh tính duy nhất toàn hệ thống**: cần phân biệt username/email hiển thị với **`(iss, sub)`** và internal user ID, đặc biệt khi có nhiều issuer/tenant hoặc Client Credentials. Luôn xác minh JWT trước khi tin claims, và kiểm tra scope, authorities cùng quyền trên tài nguyên thực tế thay vì ra quyết định chỉ bằng chuỗi `getName()`.
