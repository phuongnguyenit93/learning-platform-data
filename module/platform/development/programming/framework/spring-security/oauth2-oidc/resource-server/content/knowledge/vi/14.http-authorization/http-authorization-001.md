# authorizeHttpRequests và chính sách cho từng nhóm endpoint

Trong **Spring Security OAuth 2.0 / OIDC Resource Server**, một Access Token hợp lệ **không có nghĩa được gọi mọi API**. Sau khi Spring Security xác thực Bearer token và xây dựng `Authentication`, ứng dụng cần quyết định **HTTP request nào được phép truy cập**, dựa trên đường dẫn, HTTP method, trạng thái xác thực, scope/authority và các quy tắc riêng của hệ thống.

Với **Spring Security 6.x**, API `HttpSecurity.authorizeHttpRequests(...)` là cách phổ biến để khai báo những quy tắc đó. Mục tiêu của bài học là thiết kế chính sách rõ ràng cho **từng nhóm endpoint** — công khai, đã đăng nhập, chỉ đọc, ghi dữ liệu, quản trị và endpoint chưa được khai báo — thay vì viết một rule chung kiểu “có token là qua”.

Bài này sử dụng **Spring Boot 3.x, Spring Security 6.x, Java 17+ và Spring MVC/Servlet**, giả sử ứng dụng là **Resource Server nhận OAuth 2.0 JWT Bearer Access Token**. Các đoạn mã minh họa một API quản lý đơn hàng; tên issuer, audience, domain và scope cần thay bằng hợp đồng của hệ thống thật. Cấu hình cho opaque token, OIDC Login và nhiều filter chain cũng được phân biệt khi liên quan đến chính sách endpoint.

## 1. HTTP authentication và HTTP authorization là hai bước khác nhau

Client gọi:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN
Accept: application/json
~~~

Resource Server xử lý theo mô hình:

~~~text
HTTP request
     |
     v
Spring Security Filter Chain
     |
     v
BearerTokenAuthenticationFilter
     |
     v
JwtDecoder / AuthenticationProvider
     |-- chữ ký JWT có hợp lệ không?
     |-- issuer được tin cậy không?
     |-- audience dành cho orders-api không?
     |-- thời hạn/token profile hợp lệ không?
     v
Authentication đã xác thực
     |-- principal: Jwt
     |-- authorities: ví dụ SCOPE_orders.read
     v
AuthorizationFilter
     |-- request method/path nào?
     |-- rule đầu tiên phù hợp là gì?
     |-- principal có authority yêu cầu không?
     v
Endpoint được phép / request bị chặn
     |
     v
Business authorization
     |-- user có quyền trên orderId/tenant này không?
     v
Response
~~~

Các quyết định này trả lời các câu hỏi khác nhau:

| Câu hỏi | Cơ chế chính | Nếu thất bại |
| --- | --- | --- |
| Request có Bearer token không? | Bearer authentication | Thường **401 Unauthorized**. |
| Token có chữ ký, issuer, audience và thời hạn hợp lệ không? | JwtDecoder và validators | Thường **401 Unauthorized**. |
| Token hợp lệ có được GET hoặc POST endpoint không? | `authorizeHttpRequests`, authorities | Thường **403 Forbidden** nếu đã xác thực nhưng thiếu quyền. |
| Caller có quyền trên chính đơn hàng này không? | Domain service, method/resource authorization | Thường **403** hoặc **404** theo chính sách che giấu tài nguyên. |

**Một Access Token đúng chữ ký nhưng thiếu scope không đồng nghĩa token bị giả mạo.** Nó có thể được xác thực thành công, sau đó bị từ chối ở bước authorization. Ngược lại, một token sai chữ ký không được “đi tiếp để xét scope”.

## 2. Các khái niệm cốt lõi của authorizeHttpRequests

Một cấu hình đơn giản:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/public/**").permitAll()
    .requestMatchers("/api/private/**").authenticated()
    .anyRequest().denyAll()
);
~~~

Ý nghĩa:

- **`authorizeHttpRequests`**: định nghĩa các quyết định phân quyền HTTP sử dụng cơ chế `AuthorizationManager` trong Spring Security hiện đại.
- **`requestMatchers(...)`**: chọn các HTTP requests khớp theo path, method hoặc matcher tùy biến.
- **`permitAll()`**: cho phép request khớp rule mà không yêu cầu principal đăng nhập.
- **`authenticated()`**: yêu cầu request đã được xác thực; không tự yêu cầu một scope cụ thể.
- **`denyAll()`**: từ chối request bất kể principal có những authorities nào.
- **`anyRequest()`**: quy tắc bắt tất cả request **chưa khớp rule trước đó**.

Quan trọng: các rule **không độc lập** và **không cộng dồn** theo kiểu “khớp nhiều rule thì lấy quy tắc nghiêm nhất”. Spring Security đánh giá những matcher theo **thứ tự đã khai báo**; **rule đầu tiên khớp request** được dùng để quyết định có cho phép hay không.

### 2.1. Thứ tự các rule quyết định chính sách thực tế

Ví dụ không an toàn:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").permitAll()
    .requestMatchers("/api/admin/**").hasAuthority("SCOPE_admin.manage")
    .anyRequest().denyAll()
);
~~~

Với `GET /api/admin/users`, rule **`/api/**`** đã khớp đầu tiên và cho phép mọi người; rule quản trị ở sau **không có cơ hội chạy**.

Phải đặt rule cụ thể trước rule tổng quát:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**")
        .hasAuthority("SCOPE_admin.manage")
    .requestMatchers("/api/public/**").permitAll()
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
);
~~~

Đoạn sau tốt hơn về **thứ tự**, nhưng vẫn mới yêu cầu authenticated cho toàn bộ `/api/**` còn lại; nó chưa có chính sách scope riêng cho GET/POST đơn hàng. Với API nghiệp vụ, nên viết rule chi tiết theo method và nhóm endpoint, tránh coi “đăng nhập được” là “được sửa dữ liệu”.

### 2.2. Các biểu thức phân quyền phổ biến

| DSL | Quyết định | Ví dụ sử dụng |
| --- | --- | --- |
| `permitAll()` | Không bắt buộc authentication để qua HTTP rule. | Catalog công khai, endpoint status không nhạy cảm. |
| `denyAll()` | Không cho phép request khớp rule. | Các đường dẫn chưa được thiết kế. |
| `authenticated()` | Yêu cầu Authentication hợp lệ. | `GET /api/me` nếu mọi user có token đều được xem hồ sơ của chính mình. |
| `hasAuthority("SCOPE_orders.read")` | Phải có đúng authority được chỉ định. | GET đơn hàng. |
| `hasAnyAuthority("SCOPE_orders.read", "SCOPE_orders.audit")` | Chỉ cần một authority trong tập. | Đọc đơn hàng hoặc đọc báo cáo kiểm toán khi policy cho phép. |
| `hasRole("ADMIN")` | Theo mặc định yêu cầu `ROLE_ADMIN`. | Ứng dụng đã ánh xạ role nội bộ thành authorities `ROLE_...`. |
| `hasAnyRole("ADMIN", "SUPPORT")` | Có một role đã ánh xạ tương ứng. | Trang quản trị theo mô hình role. |
| `access(customAuthorizationManager)` | Gọi quyết định tùy biến theo request và Authentication. | Quy tắc chung đòi thêm dữ liệu ngữ cảnh khi thực sự phù hợp tầng HTTP. |

**`hasRole("ADMIN")` không giống `hasAuthority("SCOPE_admin.manage")`**. `hasRole` sử dụng tiền tố role mặc định `ROLE_`, còn Resource Server thường ánh xạ OAuth scopes thành `SCOPE_`. Không ghi `hasRole("ROLE_ADMIN")` như cách thay thế `hasRole("ADMIN")` khi dùng cấu hình tiền tố mặc định.

### 2.3. `authenticated()` không phải là “đã đăng nhập bằng OIDC”

Với Resource Server thuần JWT, request được xác thực nhờ **Bearer Access Token**, không yêu cầu browser đã mở phiên OIDC Login. Một ứng dụng có thể có cả `oauth2Login()` và `oauth2ResourceServer()`, nhưng không nên trộn hai cơ chế mà không thiết kế rõ client, session, CSRF và các filter chain liên quan.

Một endpoint cho **OIDC web login** có thể nhận session authentication; endpoint **Bearer API** thường yêu cầu token trên từng request. DSL `authenticated()` chỉ kiểm tra trạng thái Authentication, không tự ép kiểu credential thành Bearer JWT trong mọi kiến trúc.

## 3. Thiết kế chính sách theo nhóm endpoint

Giả sử hệ thống đơn hàng có các nhóm:

| Nhóm | HTTP method + path | Người được truy cập | Chính sách đề xuất |
| --- | --- | --- | --- |
| **Catalog công khai** | `GET /api/public/catalog`, `GET /api/public/catalog/**` | Mọi client | `permitAll()` nếu dữ liệu thực sự công khai. |
| **Hồ sơ của chính caller** | `GET /api/me` | Principal đã xác thực | `authenticated()`; service chỉ trả hồ sơ của caller. |
| **Đọc đơn hàng** | `GET /api/orders`, `GET /api/orders/**` | Token có quyền đọc | `hasAuthority("SCOPE_orders.read")`. |
| **Tạo đơn hàng** | `POST /api/orders` | Token có quyền ghi | `hasAuthority("SCOPE_orders.write")`. |
| **Sửa hoặc xóa đơn hàng** | `PUT/PATCH/DELETE /api/orders/**` | Token có quyền ghi | `hasAuthority("SCOPE_orders.write")` và policy dữ liệu. |
| **Quản trị** | `/api/admin/**`, mọi method | Token có quyền quản trị | `hasAuthority("SCOPE_admin.manage")`, cộng kiểm tra quyền nghiệp vụ. |
| **Endpoint chưa định nghĩa** | Mọi request còn lại | Không ai | `denyAll()` làm fallback. |

Đây là **ma trận ví dụ**: sản phẩm thật phải thống nhất tên endpoint, scope, tenant và role. Đặc biệt:

- `permitAll()` không tự khiến nội dung trở thành vô hại; chỉ dùng cho dữ liệu được phép truy cập công khai.
- `authenticated()` ở `/api/me` không có nghĩa ai cũng được gửi `?userId=...` để xem hồ sơ người khác; controller/service phải ràng buộc vào principal.
- Scope `orders.read` không tự cho phép xem đơn hàng thuộc tenant khác.
- Quyền `admin.manage` có thể cần thêm **điều kiện của tổ chức, trạng thái tài khoản, strong authentication hoặc approval** nếu nghiệp vụ nhạy cảm.
- Những URL hỗ trợ vận hành như Actuator, Swagger, metrics hoặc internal admin phải có **chính sách riêng**; không mặc nhiên gộp vào nhóm public chỉ để tiện kiểm thử.

### 3.1. Cẩn thận với path prefix

Những cách tổ chức tưởng giống nhau nhưng có thể dẫn đến policy khác:

~~~text
/api/public/catalog
/api/orders
/api/orders/42
/api/orders/42/items
/api/admin/users
/internal/admin/users
/actuator/health
~~~

Một matcher `/api/admin/**` **không** bảo vệ `/internal/admin/users` hoặc `/actuator/**`. Nếu những endpoint đó tồn tại, cần xác định chain/rule tương ứng. Với fallback `denyAll()`, các request chưa được khai báo bị chặn thay vì mặc nhiên được xử lý.

### 3.2. Chọn rõ HTTP method cho mỗi nhóm

Với cùng path, GET có thể chỉ đọc nhưng POST/DELETE làm thay đổi dữ liệu:

~~~text
GET    /api/orders   -> SCOPE_orders.read
POST   /api/orders   -> SCOPE_orders.write
GET    /api/orders/7 -> SCOPE_orders.read
DELETE /api/orders/7 -> SCOPE_orders.write
~~~

Nếu chỉ dùng:

~~~java
.requestMatchers("/api/orders/**").authenticated()
~~~

thì tất cả method có thể được cho phép bởi bất kỳ Authentication hợp lệ nào. Để ngăn việc caller có token chỉ-đọc ghi dữ liệu, phải có **matcher theo method** và scope tương ứng.

Những HTTP method không được định nghĩa như `TRACE`, `OPTIONS` hoặc một method mở rộng không được tự kế thừa quyền GET/POST; xử lý theo yêu cầu thực tế, CORS và fallback deny, đồng thời kiểm thử các trường hợp đó.

## 4. Ví dụ Spring Boot JWT Resource Server hoàn chỉnh

### 4.1. Dependency

Trong dự án Gradle (Groovy DSL), với Spring Boot quản lý phiên bản:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

`spring-boot-starter-oauth2-resource-server` cung cấp hỗ trợ Bearer Token và những module liên quan đến JWT/JOSE theo dependency tree của phiên bản Boot thông dụng. `spring-security-test` giúp mô phỏng JWT principal khi thử HTTP authorization với MockMvc.

### 4.2. Cấu hình issuer và audience

Ví dụ `src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/demo
          audiences:
            - orders-api
~~~

- `issuer-uri` chỉ issuer được API tin cậy, dùng cho khám phá nguồn khóa và kiểm tra claim `iss` theo auto-configuration thích hợp.
- `audiences` dùng để yêu cầu Access Token được phát hành cho **orders-api** trên các bản Spring Boot hỗ trợ thuộc tính đó. Nếu phiên bản không hỗ trợ, cần thêm `JwtDecoder` có audience validator.
- Ngoài chữ ký/issuer/audience, cần kiểm tra thời hạn và profile token theo yêu cầu hệ thống.

**Đừng nhầm kiểm tra issuer/audience với `authorizeHttpRequests`.** Chữ ký, issuer và audience được xử lý ở tầng token authentication, còn HTTP rule quyết định scope/authority và endpoint được phép.

### 4.3. SecurityFilterChain với các nhóm endpoint

Một bean `SecurityFilterChain` cho API mẫu:

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
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                // 1. Catalog thực sự công khai: chỉ GET.
                .requestMatchers(
                    HttpMethod.GET,
                    "/api/public/catalog",
                    "/api/public/catalog/**")
                    .permitAll()

                // 2. API quản trị: kiểm tra trước các rule rộng.
                .requestMatchers("/api/admin/**")
                    .hasAuthority("SCOPE_admin.manage")

                // 3. Đọc đơn hàng.
                .requestMatchers(
                    HttpMethod.GET,
                    "/api/orders",
                    "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")

                // 4. Tạo đơn hàng.
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")

                // 5. Sửa, xóa đơn hàng.
                .requestMatchers(
                    HttpMethod.PUT,
                    "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers(
                    HttpMethod.PATCH,
                    "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers(
                    HttpMethod.DELETE,
                    "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")

                // 6. Hồ sơ của chính principal đã xác thực.
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()

                // 7. Mọi request còn lại không được mở mặc định.
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

Ví dụ không khai báo `securityMatcher(...)` ở cấp chain nên filter chain này có thể là **fallback chính** của ứng dụng đơn giản khi chỉ có một chain. Mỗi request được xét theo thứ tự:

1. **GET catalog** được phép không cần token, vì nhóm đó thật sự công khai.
2. **`/api/admin/**`** cần `SCOPE_admin.manage` với bất kỳ method nào; các rule orders không làm loãng quyền admin.
3. **GET orders** cần `SCOPE_orders.read`.
4. **POST/PUT/PATCH/DELETE orders** cần `SCOPE_orders.write`.
5. **GET /api/me** cần Authentication nhưng không thêm scope trong chính sách ví dụ.
6. Request không khớp sẽ gặp `denyAll()`.

`SessionCreationPolicy.STATELESS` biểu thị API Bearer không dựa trên phiên HTTP session để giữ Authentication. Tắt CSRF trong ví dụ **chỉ phù hợp với API xác thực bằng Authorization header, không sử dụng cookie/session làm credential**. Nếu cùng ứng dụng có web login sử dụng cookie, cần chính sách CSRF riêng (mục 10).

**Cảnh báo về GET public:** dù `GET /api/public/catalog` là `permitAll`, nếu request mang Bearer token sai, các thành phần authentication có thể vẫn cố xử lý credential đó và từ chối. `permitAll()` không có nghĩa Bearer authentication sẽ luôn bỏ qua một header `Authorization` không hợp lệ.

### 4.4. Controller minh họa để hình dung behavior

Các handler đơn giản:

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoApiController {

    @GetMapping("/api/public/catalog")
    Map<String, Object> catalog() {
        return Map.of("items", List.of("standard"));
    }

    @GetMapping("/api/orders")
    Map<String, Object> orders() {
        return Map.of("orders", List.of());
    }

    @PostMapping("/api/orders")
    ResponseEntity<Map<String, String>> createOrder() {
        return ResponseEntity.status(HttpStatus.CREATED)
            .body(Map.of("result", "created"));
    }

    @GetMapping("/api/me")
    Map<String, String> me(@AuthenticationPrincipal Jwt jwt) {
        return Map.of("subject", jwt.getSubject());
    }

    @PostMapping("/api/admin/rebuild")
    Map<String, String> adminOperation() {
        return Map.of("result", "accepted");
    }
}
~~~

Đây là controller dành cho **đào tạo**, không thực hiện nghiệp vụ thật. Nếu triển khai `GET /api/orders/{id}`, `PUT /api/orders/{id}` hoặc chức năng admin thực tế, controller phải có handler tương ứng và service cần tiếp tục kiểm tra quyền trên dữ liệu.

### 4.5. Có thể dùng matcher cho cả path có và không có phần con

Khi muốn bảo vệ cả `/api/orders` lẫn `/api/orders/42`, ví dụ dùng cả:

~~~java
.requestMatchers(
    HttpMethod.GET,
    "/api/orders",
    "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

Đừng giả định mọi cú pháp matcher đều xử lý dấu slash, `**`, trailing slash, path parameter hoặc URL encoding giống nhau giữa các phiên bản. Trong Spring MVC, Spring Security có thể sử dụng matcher phù hợp với cấu hình MVC của ứng dụng. Cần thử những URL thực sự được controller ánh xạ, đặc biệt với nested paths và các method đặc biệt.

## 5. Scope trong Access Token được ánh xạ thành authority như thế nào?

JWT Access Token do Authorization Server phát hành có thể mang:

~~~json
{
  "iss": "https://identity.example.test/realms/demo",
  "sub": "employee-123",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "exp": 1893456000
}
~~~

Spring Security Resource Server thường dùng `JwtGrantedAuthoritiesConverter` để chuyển scopes từ claim `scope` hoặc `scp` thành authorities tiền tố **`SCOPE_`**:

~~~text
JWT claim scope = "orders.read orders.write"
                  |
                  v
GrantedAuthority("SCOPE_orders.read")
GrantedAuthority("SCOPE_orders.write")
~~~

Vì vậy, DSL:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders")
    .hasAuthority("SCOPE_orders.read")
~~~

kiểm tra **đúng authority đó**; nó không so chuỗi `"orders.read"` trong JWT trực tiếp ở filter. Nếu nhà phát hành dùng claim role custom, `scope` dạng khác hoặc đặt quyền trong `realm_access.roles`, phải có converter do ứng dụng định nghĩa theo **token contract**.

### 5.1. Role và scope không tự đồng nhất

Giả sử JWT có:

~~~json
{
  "roles": ["ADMIN"],
  "scope": "orders.read"
}
~~~

Với converter mặc định theo scope, **không tự có `ROLE_ADMIN`** chỉ vì token có claim `roles`. Khi đó:

~~~java
.requestMatchers("/api/admin/**").hasRole("ADMIN")
~~~

chưa chắc cho phép token trên, vì `hasRole("ADMIN")` tìm authority **`ROLE_ADMIN`** theo tiền tố mặc định. Có hai cách thiết kế có chủ đích:

- **Dựa trên OAuth scope:** nhà phát hành cấp `admin.manage`; API yêu cầu `SCOPE_admin.manage`.
- **Dựa trên domain role:** converter hoặc domain service xác định role nội bộ đáng tin, thêm `ROLE_ADMIN` theo chính sách; API yêu cầu `hasRole("ADMIN")`.

Không tự map mọi string `"ADMIN"` từ nguồn chưa được kiểm soát thành quyền quản trị. Khi có nhiều issuer, role cùng tên có thể mang ý nghĩa khác nhau; audience và issuer vẫn phải được xác minh trước.

### 5.2. Ví dụ custom converter cho claim permission riêng

Nếu Access Token dùng claim `permissions` là **mảng string**, API có thể định nghĩa converter chỉ cho những giá trị đã được cho phép. Ví dụ:

~~~java
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

public final class OrdersJwtAuthorities {

    private OrdersJwtAuthorities() {}

    public static JwtAuthenticationConverter converter() {
        JwtGrantedAuthoritiesConverter scopes =
            new JwtGrantedAuthoritiesConverter();

        JwtAuthenticationConverter result =
            new JwtAuthenticationConverter();

        result.setJwtGrantedAuthoritiesConverter(jwt -> {
            Set<GrantedAuthority> authorities =
                new LinkedHashSet<>(scopes.convert(jwt));

            Object raw = jwt.getClaims().get("permissions");
            if (raw instanceof List<?> values) {
                for (Object value : values) {
                    if ("orders.audit".equals(value)) {
                        authorities.add(new SimpleGrantedAuthority(
                            "PERMISSION_orders.audit"));
                    }
                }
            }

            return authorities;
        });

        return result;
    }
}
~~~

Ở đây custom permission `orders.audit` được ánh xạ thành **`PERMISSION_orders.audit`**, tách khỏi tiền tố scope. Ví dụ chỉ cho phép một giá trị đã biết, không chấp nhận mọi chuỗi role/permission tùy ý.

Nếu sử dụng converter:

~~~java
.oauth2ResourceServer(oauth -> oauth.jwt(jwt ->
    jwt.jwtAuthenticationConverter(
        OrdersJwtAuthorities.converter())))
~~~

Đó là **đoạn thay thế** cho cấu hình `oauth2ResourceServer(...jwt(Customizer.withDefaults()))` trong SecurityFilterChain, không phải một filter chain thứ hai. Với cấu hình custom, có thể dùng:

~~~java
.requestMatchers(HttpMethod.GET, "/api/audit/orders")
    .hasAuthority("PERMISSION_orders.audit")
~~~

Phải đặt rule trên trước fallback `denyAll()` và tránh đặt sau một rule rộng hơn đã khớp trước. Trong thực tế, kiểm tra đúng kiểu dữ liệu `permissions` (array of strings), issuer/audience và schema là trách nhiệm của token contract/validator; converter không nên cố biến dữ liệu bất thường thành quyền cao hơn.

## 6. Thứ tự matcher: cách nghĩ đúng theo “first match wins”

Giả sử có các rule:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.requestMatchers("/api/orders/**")
    .hasAuthority("SCOPE_orders.write")
.anyRequest().denyAll()
~~~

Với `GET /api/orders/42`, rule đầu yêu cầu `orders.read`; với `DELETE /api/orders/42`, rule đầu không khớp method nên rule thứ hai yêu cầu `orders.write`.

Nhưng nếu đảo thứ tự:

~~~java
.requestMatchers("/api/orders/**")
    .authenticated()
.requestMatchers(HttpMethod.DELETE, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")
~~~

thì rule DELETE có thể **không bao giờ được xét**, vì matcher `/api/orders/**` đầu tiên đã khớp mọi method. Đây là một lỗi phân quyền nghiêm trọng: một token xác thực bất kỳ có thể đi qua rule rộng.

### 6.1. Luôn kiểm tra luật “phủ trước” luật khác

| Rule đặt trước | Rule đặt sau | Vấn đề có thể xảy ra |
| --- | --- | --- |
| `/api/**` + `permitAll` | `/api/admin/**` + admin authority | Admin bị mở công khai. |
| `/api/orders/**` + `authenticated` | POST orders + write scope | Ghi dữ liệu có thể chỉ cần xác thực. |
| GET `/api/orders/**` + read scope | GET `/api/orders/summary` + admin scope | Summary nhạy cảm bị mở cho mọi reader nếu khớp matcher trước. |
| `anyRequest().authenticated()` | `/api/admin/**` + admin scope | Rule admin ở sau sẽ không được xét. |
| `/api/public/**` + `permitAll` | `/api/public/admin/**` + admin scope | Path “admin” dưới public có thể bị mở. |

Các nhóm endpoint nên được thiết kế sao cho **không chồng lấn ngoài ý muốn**. Nếu có endpoint đặc biệt trong một nhóm rộng, đặt luật đặc biệt trước. Dùng **`anyRequest().denyAll()` ở cuối** để chặn phần chưa được phân loại.

### 6.2. Quy tắc ở HTTP layer không thay thế method security

Nếu business service xử lý nhiều đường vào khác nhau — HTTP controller, batch job, message listener hoặc một endpoint mới — một phép kiểm tra ở HTTP path có thể không đủ. Những thao tác nhạy cảm có thể cần **method authorization** và policy nghiệp vụ.

Ví dụ bật method security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Sau đó service có thể dùng `@PreAuthorize` cho những quyền phù hợp, nhưng kiểm tra quyền trên **từng order/tenant** thường cần logic domain hoặc query đã ràng buộc owner/tenant. Không coi URL pattern là cơ chế chống **IDOR/BOLA**.

## 7. Chọn nhiều SecurityFilterChain: securityMatcher khác requestMatchers

Khi ứng dụng có nhiều kiểu endpoint hoặc nhiều cơ chế xác thực, có thể chia thành nhiều bean `SecurityFilterChain`:

- Chain dành cho **`/api/**`** dùng Bearer token, stateless.
- Chain dành cho **web** dùng OIDC Login và session (nếu thật sự có).
- Chain dành cho **management/status** với cơ chế riêng theo yêu cầu hạ tầng.

Sự khác biệt quan trọng:

| Cơ chế | Đặt ở đâu? | Tác dụng |
| --- | --- | --- |
| **`http.securityMatcher(...)`** | Cấp `SecurityFilterChain` | Quyết định **chain này có áp dụng cho request không**. |
| **`requestMatchers(...)`** bên trong `authorizeHttpRequests` | Cấp rule của chain đã được chọn | Quyết định **request được quyền truy cập không** sau khi đã vào chain. |
| **`@Order` trên chain** | Khi có nhiều filter chain | Chain có thứ tự ưu tiên phù hợp được chọn trước. |
| **`anyRequest()`** | Bên trong một chain | Chỉ là fallback cho những request **đã đi vào chain ấy**. |

Một request thường được xử lý bởi **SecurityFilterChain đầu tiên khớp request**, không phải tự động chạy qua tất cả các chain để cộng dồn bảo vệ.

### 7.1. Ví dụ hai chain: API và fallback

Đây là **phương án thay thế** cho cấu hình một chain ở mục 4, không dùng đồng thời cả hai bộ bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SplitSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/catalog")
                    .permitAll()
                .requestMatchers("/api/admin/**")
                    .hasAuthority("SCOPE_admin.manage")
                .requestMatchers(
                    HttpMethod.GET,
                    "/api/orders",
                    "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()));

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallbackChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().denyAll());

        return http.build();
    }
}
~~~

API chain chỉ áp dụng `/api/**`. Fallback chain không đặt `securityMatcher` nên bắt các request còn lại và từ chối chúng. Trong ví dụ này `/actuator/**`, `/internal/**` và web routes chưa được cấp quyền.

Nếu bỏ fallback chain và không có chain nào khác khớp một path, **path đó có thể không được Spring Security bảo vệ như tác giả tưởng**. Vì vậy, khi dùng nhiều chain, phải rà soát bề mặt URL thực tế của ứng dụng, bao gồm actuator, static resources, servlet paths và các endpoint do framework cung cấp.

**Không đặt `@Order(1)` cho một chain bắt mọi request** trước chain API, bởi chain rộng có thể chiếm toàn bộ request trước khi chain hẹp được xét. Nguyên tắc là **chain cụ thể trước, fallback sau**.

### 7.2. Khi có OIDC Login và API Bearer trên cùng backend

Một web app có thể dùng `oauth2Login()` để tạo phiên cho browser và đồng thời có `oauth2ResourceServer().jwt()` để bảo vệ API. Đây là mô hình cần hai chiến lược:

- Đường web dùng **session cookie**, login redirect, CSRF theo thiết kế browser.
- Đường API dùng **Bearer Access Token**, mã lỗi 401/403 thay vì tự động chuyển mọi request API sang form đăng nhập.

Khi chia chain, cần thống nhất cách hoạt động của **session**, **CSRF**, **CORS**, entry point và cookie. Đừng lấy cấu hình `csrf.disable()` hoặc `STATELESS` cho API rồi áp lên toàn bộ website chỉ vì dễ viết.

## 8. Những nhóm endpoint thường được quản lý riêng

### 8.1. Public endpoints

Một endpoint công khai đúng nghĩa có thể dùng:

~~~java
.requestMatchers(HttpMethod.GET, "/api/public/catalog")
    .permitAll()
~~~

Nhưng **không phải mọi endpoint có tên “public” đều an toàn để public**, cũng không phải mọi endpoint không đòi token đều nên trả dữ liệu cá nhân. Hãy quyết định dựa trên dữ liệu, tác động thao tác và yêu cầu sản phẩm.

Nên tránh:

~~~java
.requestMatchers("/api/public/**").permitAll()
~~~

nếu sau này có người thêm một API `POST /api/public/reset-user-role` hoặc `/api/public/internal-report`. Matcher theo method và URL cụ thể giúp hạn chế quyền được mở ngoài dự kiến.

### 8.2. Health checks và Actuator

Nếu dùng Spring Boot Actuator, cần quyết định endpoint nào phục vụ load balancer/orchestrator và endpoint nào mang thông tin vận hành nhạy cảm:

- **Liveness/readiness** có thể công khai trong phạm vi mạng nội bộ đã kiểm soát hoặc bảo vệ theo hạ tầng.
- **Metrics, env, heapdump, threaddump, loggers, mappings** và những endpoint quản trị khác không được mở mặc định cho Internet.
- Với management server chạy trên port/context riêng, cần xác định **chain, network policy và exposure configuration** tương ứng.
- Nếu muốn tạo endpoint `/healthz` công khai, chỉ cấp đường dẫn đó; không mở tất cả `/actuator/**` bằng `permitAll()`.

Không giả định `authorizeHttpRequests` tự làm những endpoint Actuator được expose hoặc hidden. Actuator còn có cấu hình **endpoint exposure**, network accessibility và security; các lớp này cần được vận hành cùng nhau.

### 8.3. API documentation, Swagger UI và OAuth callbacks

Swagger/OpenAPI endpoint đôi khi được mở trong môi trường phát triển; production có thể cần xác thực hoặc giới hạn mạng. Không sao chép một rule `permitAll("/swagger-ui/**", "/v3/api-docs/**")` vào mọi môi trường mà không đánh giá dữ liệu lộ ra.

OIDC Login callback và OAuth Authorization Code flow thuộc **OAuth 2.0 Client**, không phải một JWT Resource Server endpoint thông thường. Chỉ mở callback theo cấu hình Client/Relying Party và kiểm tra `state`, PKCE, nonce và session tương ứng, không thay bằng một rule `permitAll` quá rộng cho API.

### 8.4. Endpoint quản trị hoặc dữ liệu nhạy cảm

Các route như:

~~~text
/api/admin/users
/api/admin/roles
/api/admin/tenants
/api/internal/export
/api/reports/audit
~~~

cần được phân nhóm riêng, có scope/role/permission phù hợp và kiểm tra ở domain. Nếu route `/api/internal/export` chưa được khai báo trong chính sách, fallback `denyAll()` sẽ bảo vệ tốt hơn một rule `/api/**.authenticated()` quá rộng.

## 9. Phân quyền theo đường dẫn không đủ cho multi-tenant và quyền trên bản ghi

Giả sử caller có JWT hợp lệ:

~~~json
{
  "iss": "https://identity.example.test/realms/demo",
  "sub": "employee-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "tenant_id": "tenant-A"
}
~~~

HTTP rule:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

Chỉ đảm bảo token có quyền **đọc đơn hàng nói chung**, chưa đảm bảo được đọc `GET /api/orders/987` nếu order 987 thuộc **tenant-B**. Một caller có thể thay đổi ID trên URL; path vẫn khớp rule đọc, nhưng domain phải kiểm tra quyền theo tài nguyên.

### 9.1. Ví dụ policy tại service

~~~java
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.oauth2.jwt.Jwt;

public final class OrderAccessPolicy {

    public void requireSameTenant(Jwt jwt, Order order) {
        String tokenTenant = jwt.getClaimAsString("tenant_id");

        if (tokenTenant == null
                || !tokenTenant.equals(order.getTenantId())) {
            throw new AccessDeniedException(
                "Order access not permitted");
        }
    }
}
~~~

Trong ví dụ, **Order** là domain entity minh họa phải được định nghĩa trong ứng dụng. Điều kiện tenant trên chỉ là một trong các kiểm tra: service còn có thể cần user account status, membership, owner, delegated permission và những quy tắc nghiệp vụ khác. Đừng chỉ dựa vào `tenant_id` do client gửi trong header/query.

### 9.2. Vị trí kiểm tra nên rõ ràng

| Kiểm tra | Tầng phù hợp |
| --- | --- |
| Chữ ký, issuer, audience, thời hạn JWT | `JwtDecoder` + token validators. |
| GET/POST/DELETE được phép theo scope? | `authorizeHttpRequests`. |
| `roles`/custom permissions có đúng contract và được ánh xạ đúng? | JWT validators + converters/domain policy. |
| User nội bộ còn `ACTIVE` và thuộc tenant? | Account/domain service. |
| Order ID thuộc user/tenant được phép? | Resource authorization/service/query. |
| Truy cập qua job/message listener không đi HTTP? | Method/domain authorization theo context thích hợp. |

Nguyên tắc **defense in depth**: bảo vệ ở HTTP filter giúp chặn sớm, nhưng chính sách đối với dữ liệu phải nằm nơi có đủ thông tin về **bản ghi, tenant và trạng thái quyền**.

## 10. CORS preflight, OPTIONS và CSRF: không nhầm với authorization

### 10.1. CORS là chính sách browser, không thay Bearer authentication

Khi browser frontend ở `https://app.example.test` gọi API ở `https://api.example.test` với `Authorization: Bearer ...`, trình duyệt có thể gửi **CORS preflight request**:

~~~http
OPTIONS /api/orders HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

Preflight thông thường **không chứa Bearer Access Token**. Nếu Resource Server cố yêu cầu JWT cho preflight trước khi xử lý CORS, browser sẽ thất bại dù GET thật có thể gửi Bearer token hợp lệ.

Cách phù hợp là cấu hình **CORS processing trước Spring Security authentication/authorization**, thay vì mặc định coi mọi `OPTIONS` là đã được xác thực. Spring Security có thể tích hợp CORS với `http.cors(...)` khi có `CorsConfigurationSource` thích hợp.

Ví dụ:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class CorsPolicyConfig {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.test"));
        cors.setAllowedMethods(
            List.of("GET", "POST", "PUT", "PATCH", "DELETE"));
        cors.setAllowedHeaders(
            List.of("Authorization", "Content-Type"));
        cors.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

Trong `SecurityFilterChain`, thêm:

~~~java
.cors(Customizer.withDefaults())
~~~

vào cấu hình `HttpSecurity` tương ứng, ví dụ trước khi khai báo `authorizeHttpRequests`. Bộ CORS được cấu hình chỉ cho phép origin đã xác định; không mở toàn bộ `*` khi không cần. Nếu API dựa trên cookie và `allowCredentials=true`, phải có chính sách origin cụ thể và CSRF phù hợp; không dùng wildcard origin với credentials theo cách vi phạm quy tắc CORS.

**CORS không ngăn client ngoài browser gọi API.** Nó là cơ chế browser kiểm soát truy cập cross-origin. Quyền thực tế vẫn phải được xác minh bằng token và HTTP/domain authorization.

### 10.2. Có cần `OPTIONS /**.permitAll()`?

Không nên dùng **`OPTIONS /**` + `permitAll`** như giải pháp mặc định cho mọi vấn đề CORS. Với `CorsFilter` được tích hợp đúng, preflight hợp lệ thường được xử lý trước các rule bảo vệ API.

Nếu ứng dụng có endpoint `OPTIONS` thực sự mang nghĩa nghiệp vụ hoặc custom preflight behavior, cần quy tắc cụ thể. Một rule `OPTIONS /**.permitAll()` chỉ xét quyền ở tầng Spring Authorization, không tự đặt các CORS response headers chính xác hay thay cấu hình CORS.

### 10.3. CSRF khác CORS

Đối với API **thuần Bearer token trong `Authorization` header**, không sử dụng session cookie làm credential, nhiều ứng dụng chọn:

~~~java
.csrf(AbstractHttpConfigurer::disable)
~~~

Với website dùng **session cookie / OIDC Login** trong browser, request có thể tự mang cookie theo trình duyệt, nên **CSRF protection** thường vẫn cần thiết. Đừng sao chép cấu hình API Bearer stateless để tắt CSRF trên toàn bộ web app.

### 10.4. HEAD, trailing slash và method forwarding

Các method như `HEAD` và những URL có trailing slash hoặc encoded path có thể tương tác với Spring MVC routing theo cách không trực quan. Một `GET` matcher không phải lúc nào cũng đủ để định nghĩa chính sách cho `HEAD` trong mọi stack/config. Khi API công bố HEAD hoặc các biến thể path, hãy định nghĩa và kiểm thử policy tường minh.

Nếu ứng dụng nằm sau reverse proxy hoặc API gateway, cấu hình forwarded headers và path rewriting phải nhất quán. Không dựa vào đường dẫn do client giả mạo trong `X-Forwarded-Prefix` để quyết định quyền. Những endpoint bị đổi path bởi proxy phải được kiểm tra với **path thực mà Spring Security thấy**.

## 11. Kiểm thử HTTP authorization theo từng nhóm endpoint

Những test này nên chứng minh chính sách cho **cả request được phép lẫn request bị chặn**, bao gồm HTTP method, scope và fallback.

### 11.1. Ma trận hành vi mong đợi

| Request | JWT / authorities | Kết quả |
| --- | --- | --- |
| `GET /api/public/catalog` | Không có token | **200** nếu controller tồn tại và hoạt động. |
| `GET /api/orders` | Không có token | **401**. |
| `GET /api/orders` | `SCOPE_orders.read` | **200**. |
| `GET /api/orders` | Chỉ `SCOPE_orders.write` | **403**. |
| `POST /api/orders` | Chỉ `SCOPE_orders.read` | **403**. |
| `POST /api/orders` | `SCOPE_orders.write` | **201** theo controller ví dụ. |
| `GET /api/me` | Không có token | **401**. |
| `GET /api/me` | JWT hợp lệ nhưng không có `orders.read` | **200** theo rule `authenticated()`. |
| `POST /api/admin/rebuild` | `SCOPE_orders.write`, không có admin | **403**. |
| `POST /api/admin/rebuild` | `SCOPE_admin.manage` | **200** theo controller ví dụ. |
| `GET /api/unconfigured` | JWT hợp lệ có mọi scope ví dụ | **403** do fallback `denyAll`. |
| `POST /api/public/catalog` | JWT hợp lệ nhưng không được khai báo | **403** do fallback `denyAll`. |
| `GET /api/orders` | Bearer JWT chữ ký sai/audience sai | **401** nếu request đi qua decoder thật. |

**Lưu ý:** `denyAll()` đối với request ẩn danh có thể dẫn tới phản hồi **401** do cách xử lý entry point khi chưa xác thực; đối với principal đã xác thực thường nhận **403**. Các giá trị 200/201 chỉ có khi controller tương ứng được khai báo; authorization có thể cho phép nhưng request vẫn trả 404/405 nếu không có handler phù hợp.

### 11.2. MockMvc và spring-security-test

`spring-security-test` cung cấp helper **`jwt()`** để giả lập một JWT Authentication cho request kiểm thử. Ví dụ:

~~~java
mockMvc.perform(get("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

Ở đây Authentication với authority đã được tạo trực tiếp cho test; **không cần** Authority Server hoặc JWT có chữ ký thật. Nhờ vậy test tập trung vào **thứ tự requestMatchers và quyết định authorization**.

Đồng thời, `jwt()` **không chứng minh** `JwtDecoder` đã xác minh chữ ký, issuer, audience hay expiration. Nó cũng không test custom authorities converter nếu test ép authorities thủ công. Những phần đó cần test decoder/converter riêng.

### 11.3. Ví dụ test đầy đủ bằng SpringBootTest

Đoạn test dưới đây giả định cấu hình ở mục 4 và controller mẫu ở mục 4.4 được đặt trong ứng dụng Spring Boot. Trong môi trường chỉ kiểm thử rule, test cung cấp một `JwtDecoder` giả **từ chối mọi token dạng string**, còn `with(jwt())` tạo Authentication để test authorization.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Import(EndpointAuthorizationTest.TestJwtDecoderConfig.class)
class EndpointAuthorizationTest {

    @Autowired
    MockMvc mockMvc;

    @TestConfiguration
    static class TestJwtDecoderConfig {
        @Bean
        JwtDecoder jwtDecoder() {
            return token -> {
                throw new BadJwtException("Test decoder rejects raw tokens");
            };
        }
    }

    @Test
    void publicCatalogAllowsAnonymous() throws Exception {
        mockMvc.perform(get("/api/public/catalog"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.items").isArray());
    }

    @Test
    void ordersRejectAnonymous() throws Exception {
        mockMvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void invalidBearerTokenIsRejected() throws Exception {
        mockMvc.perform(get("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer invalid"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readScopeAllowsReading() throws Exception {
        mockMvc.perform(get("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.orders").isArray());
    }

    @Test
    void writeScopeAloneCannotRead() throws Exception {
        mockMvc.perform(get("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.write"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void readScopeCannotCreate() throws Exception {
        mockMvc.perform(post("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void writeScopeAllowsCreate() throws Exception {
        mockMvc.perform(post("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.write"))))
            .andExpect(status().isCreated());
    }

    @Test
    void meRequiresOnlyAuthenticatedPrincipal() throws Exception {
        mockMvc.perform(get("/api/me")
                .with(jwt()
                    .jwt(jwt -> jwt.subject("user-123"))
                    .authorities(
                        new SimpleGrantedAuthority("SCOPE_other"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.subject").value("user-123"));
    }

    @Test
    void adminOperationRejectsNormalWriter() throws Exception {
        mockMvc.perform(post("/api/admin/rebuild")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.write"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminOperationRequiresAdminScope() throws Exception {
        mockMvc.perform(post("/api/admin/rebuild")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_admin.manage"))))
            .andExpect(status().isOk());
    }

    @Test
    void unknownEndpointIsDeniedEvenForAuthenticatedUser()
            throws Exception {
        mockMvc.perform(get("/api/unconfigured")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_admin.manage"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void publicGetRuleDoesNotOpenPost() throws Exception {
        mockMvc.perform(post("/api/public/catalog")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.write"))))
            .andExpect(status().isForbidden());
    }
}
~~~

**Test scope:** Bean `JwtDecoder` giả chỉ áp dụng trong môi trường kiểm thử authorization. Request có `Authorization: Bearer invalid` được giả lập để xác minh behavior 401 khi decoder từ chối; nó **không** test thuật toán JWT thật. Nếu ứng dụng đã định nghĩa bean decoder production riêng, cần điều chỉnh test configuration cho tương thích thay vì khai báo hai bean cùng loại dẫn đến conflict.

Những request `with(jwt())` bỏ qua decoder, vì vậy các test đó chỉ chứng minh **HTTP rule**. Test signed JWT end-to-end và việc mapping claim `scope` sang authorities phải được xây dựng ở tầng khác.

### 11.4. Test riêng thứ tự rule và những đường dẫn dễ nhầm

Ngoài happy path, nên có test chủ đích:

~~~text
GET    /api/admin/users       -> chỉ admin
POST   /api/admin/users       -> chỉ admin
GET    /api/orders            -> read scope
GET    /api/orders/42         -> read scope + quyền dữ liệu
POST   /api/orders            -> write scope
DELETE /api/orders/42         -> write scope + quyền dữ liệu
GET    /api/public/catalog    -> public
POST   /api/public/catalog    -> không public
GET    /api/unknown           -> deny fallback
GET    /internal/admin        -> deny fallback hoặc chain riêng
~~~

Đặc biệt khi thêm endpoint mới, test **rule cụ thể không bị một rule tổng quát ở trước che mất**. Với nhiều filter chain, test chain nào được chọn cho từng URL, kể cả các path không bắt đầu bằng `/api/`.

## 12. Kiểm thử JWT thật và các ranh giới bảo mật bên ngoài HTTP rule

Để kết luận Resource Server bảo vệ API an toàn, không chỉ test `authorizeHttpRequests` với JWT giả. Cần các bài kiểm thử riêng:

| Tầng | Ví dụ kiểm thử |
| --- | --- |
| **JWT signature validation** | JWT ký bằng key lạ hoặc có chữ ký sai phải bị từ chối. |
| **Issuer** | JWT ký đúng nhưng `iss` khác issuer tin cậy phải bị từ chối. |
| **Audience** | JWT hợp lệ nhưng `aud` dành cho API khác phải bị từ chối. |
| **Thời hạn** | `exp` đã qua hoặc `nbf` chưa tới phải bị từ chối theo clock skew policy. |
| **JWT authorities mapping** | `scope` hoặc `scp` thực tế được chuyển thành authority đúng, không tự cấp role ngoài contract. |
| **HTTP rules** | Scope đọc không được ghi; admin path không bị mở; endpoint không khai báo bị chặn. |
| **Domain authorization** | Người dùng khác tenant/khác owner không được xem/sửa order dù có scope. |
| **CORS/CSRF** | Browser preflight hợp lệ, origin ngoài danh sách không được CORS chấp thuận; CSRF đúng với flow cookie nếu có. |
| **Multi-chain coverage** | Mọi endpoint đều được chain thích hợp bảo vệ, không có route lọt ra ngoài cấu hình. |

Để kiểm thử JwtDecoder, có thể dùng RSA key pair chỉ dành cho test và ký JWT bằng private key fixture; decoder xác minh bằng public key fixture, đồng thời chạy issuer/audience/time validators. Nếu cần kiểm tra tải JWKS, dựng JWKS endpoint cục bộ. Sau đó integration test gửi JWT ký thật trong header `Authorization: Bearer` qua filter chain để quan sát 401/403.

Không dùng private key production hoặc Access Token người dùng thật trong bài test tự động; các token test nên có định danh giả và scope chỉ dùng trong test.

## 13. Khi JWT của Resource Server là opaque token thì sao?

Nếu Authorization Server phát hành **opaque Access Token** thay vì JWT, Resource Server có thể cấu hình:

~~~java
.oauth2ResourceServer(oauth ->
    oauth.opaqueToken(Customizer.withDefaults()))
~~~

Trong cấu hình opaque, Authentication/authorities được xây từ kết quả **introspection** theo contract. Các rule `authorizeHttpRequests` như `hasAuthority("SCOPE_orders.read")` vẫn có thể sử dụng nếu `OpaqueTokenIntrospector` ánh xạ scope thành authority tương ứng.

Chỉ khác **bước xác thực token**, không phải nguyên tắc chia nhóm endpoint. Test authorization có thể dùng `spring-security-test` helper `opaqueToken()`; còn test introspection thật cần introspector/endpoint fixture riêng.

Đừng bật đồng thời hai phương thức JWT và opaque rồi giả định framework tự phân biệt hoàn hảo mọi token nếu chưa thiết kế chính sách rõ. Cơ chế xác thực cần khớp định dạng token và cấu hình của Authorization Server.

## 14. Quy tắc deny-by-default và những giới hạn cần hiểu đúng

### 14.1. Vì sao nên có anyRequest().denyAll()

Khi nhóm API có thể mở rộng theo thời gian, rule cuối:

~~~java
.anyRequest().denyAll()
~~~

giúp endpoint mới **không được cấp quyền chỉ vì developer thêm controller mà quên cập nhật security policy**. Nó là một lựa chọn bảo thủ, giảm khả năng vô tình công khai dữ liệu.

Tuy nhiên, `denyAll()` **không tự bảo vệ request nằm ngoài filter chain** trong mô hình nhiều chain. Cần có một fallback chain phù hợp. Nó cũng không thay thế:

- Authorization theo bản ghi và tenant.
- Các cấu hình hạ tầng như network, gateway và actuator exposure.
- Kiểm tra issuer/audience/token type.
- Quy tắc dành cho message/batch flow không qua HTTP.

### 14.2. Public không có nghĩa bỏ toàn bộ security filters

`permitAll()` cho phép request ở tầng HTTP authorization. Nó **không xóa filter chain** và không mặc nhiên bỏ toàn bộ security processing. Ví dụ, Bearer token không hợp lệ có thể bị từ chối ngay tại authentication filter trước khi tới `permitAll`.

Không nên dùng `web.ignoring()` hoặc bỏ security chain khỏi những endpoint cần CORS/security headers/logging chỉ để chúng “public”, trừ khi đã đánh giá rõ hệ quả. Với nhiều ứng dụng, `permitAll()` trong chain cho public endpoint là lựa chọn phù hợp hơn loại hẳn các filters.

### 14.3. 401 và 403 trong chính sách từng nhóm

Một Resource Server thường phân biệt:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

khi endpoint cần authentication nhưng không có credential hợp lệ.

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

khi principal đã được xác thực nhưng thiếu quyền. Chi tiết `WWW-Authenticate` phụ thuộc loại lỗi/handler; không phải mọi 403 đều có cùng error parameter. Không trả raw JWT, access token, claims nhạy cảm hoặc exception stack trace cho client.

Nếu API sử dụng OAuth2 Login session, entry point có thể redirect sang trang login cho request web. Với Bearer API, người gọi thường cần **401/403 đúng ngữ nghĩa API**, không redirect vô điều kiện về website login.

## 15. Các lỗi thường gặp khi phân quyền HTTP

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Đặt `/api/**.permitAll()` trước `/api/admin/**`. | Endpoint admin bị mở vì rule đầu khớp. | Đặt rule đặc thù trước, hạn chế rule public. |
| Chỉ dùng `anyRequest().authenticated()` cho API nghiệp vụ. | Mọi token hợp lệ có thể truy cập nhiều endpoint hơn cần thiết. | Định nghĩa scopes theo nhóm/method và fallback deny. |
| Dùng `hasRole("ADMIN")` cho token chỉ có `SCOPE_admin.manage`. | Kiểm tra sai loại authority. | Thống nhất scope vs role và converter. |
| Cho phép GET/POST trên cùng path bằng một rule chung. | Token chỉ đọc có thể gọi thao tác ghi. | Dùng matcher theo HTTP method. |
| Đặt `anyRequest()` trước rule cụ thể. | Rule sau không được xét hoặc DSL không hợp lệ. | Đặt fallback cuối cùng. |
| Nhiều chain nhưng không có fallback. | Một số URL không được Spring Security bảo vệ. | Kiểm soát chain matcher/ordering và có fallback chain. |
| Dùng `securityMatcher("/api/**")` rồi tưởng bảo vệ Actuator. | `/actuator/**` nằm ngoài API chain. | Chính sách quản trị/exposure/fallback riêng. |
| Dùng `permitAll()` cho mọi OPTIONS để sửa CORS. | CORS không tự trả headers đúng, method có thể bị mở ngoài ý định. | Cấu hình CORS processing và test preflight. |
| Tắt CSRF toàn hệ thống vì có Bearer API. | Web session-cookie có thể mất CSRF protection. | Phân biệt API Bearer và web session. |
| Tin `scope` mà quên issuer/audience. | Token của hệ thống khác có thể bị dùng sai mục đích. | Kiểm tra JwtDecoder và validators. |
| Dùng JWT `sub` làm bằng chứng sở hữu mọi bản ghi. | IDOR/BOLA và cross-tenant access. | Domain policy kiểm tra owner/tenant với dữ liệu thật. |
| Chỉ test request được phép. | Không phát hiện endpoint mở rộng quyền ngoài dự kiến. | Test 401/403/fallback, method và path chồng lấn. |
| Dùng `jwt()` test helper rồi kết luận chữ ký JWT an toàn. | Test bỏ qua decoder và JWKS. | Thêm test JWT ký thật và validation profile. |
| Ghi Authorization header vào log khi request lỗi. | Rò rỉ Bearer credential. | Log loại lỗi/request ID, ẩn token và thông tin nhạy cảm. |

## 16. Quy trình thiết kế chính sách HTTP có thể áp dụng

1. **Liệt kê tất cả endpoint hiện có và dự kiến** theo HTTP method, URL, loại dữ liệu và tác động thao tác.
2. **Phân nhóm rõ ràng**: public, authenticated-only, read, write, admin, internal, health/management, callback/web, và nhóm chưa được khai báo.
3. **Thống nhất hợp đồng OAuth Access Token**: issuer, audience API, scope names, token profile, authority mapping và ranh giới giữa user token/client token.
4. **Định nghĩa SecurityFilterChain**: matcher cụ thể trước matcher rộng; dùng `requestMatchers(HttpMethod, path)` cho các nhóm khác nhau; fallback `anyRequest().denyAll()`.
5. **Nếu dùng nhiều chain**, chọn `securityMatcher` và `@Order` có chủ đích; bảo đảm luôn có chain phù hợp với mọi endpoint cần bảo vệ.
6. **Bảo vệ browser integration**: CORS preflight, origin allowlist, CSRF theo credential flow và security headers.
7. **Tách authorization nghiệp vụ**: thêm kiểm tra tài khoản nội bộ, tenant, owner, membership, trạng thái tài nguyên và policy nghiệp vụ ở tầng service.
8. **Kiểm thử cả positive và negative paths**: anonymous, token lỗi, scope thiếu, method sai, route mới, admin path, multi-chain, CORS và resource access.
9. **Rà soát trước khi thêm endpoint**: yêu cầu người phát triển cập nhật ma trận policy và tests cùng với controller/service; không mở một wildcard rộng để “sửa” lỗi 403.

**Ghi nhớ:** `authorizeHttpRequests` là nơi diễn đạt **chính sách truy cập HTTP** của Spring Security Resource Server. Các rule phải được sắp theo **thứ tự matcher**, tách **GET/POST/DELETE**, xác định nhóm **public/authenticated/read/write/admin**, và có **fallback deny**. JWT authentication bảo đảm token đáng tin; HTTP authorization bảo đảm endpoint phù hợp quyền; domain authorization tiếp tục bảo vệ **dữ liệu cụ thể**.

## Tài liệu tham khảo

- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html).
- [Spring Security — Java Configuration and Multiple HttpSecurity Instances](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html).
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- [Spring Security — CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html).
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html).
- [Spring Security — Testing OAuth 2.0 with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html).
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750).
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068).
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/).
