# HTTP Basic và HTTP Bearer

HTTP Basic và HTTP Bearer là hai cơ chế xác thực thường gặp trong API Spring Boot. Cả hai đều truyền thông tin xác thực qua HTTP header `Authorization`, nhưng dữ liệu được gửi và cách server kiểm tra khác nhau. Basic gửi tên người dùng cùng mật khẩu đã mã hóa Base64; Bearer gửi một access token do hệ thống xác thực cấp. Khi mô tả API bằng springdoc-openapi, hai cơ chế được khai báo dưới dạng HTTP security scheme trong OpenAPI, sau đó gắn vào tài liệu ở cấp toàn cục hoặc từng operation.

Điều quan trọng là phân biệt hợp đồng OpenAPI với bảo mật thực tế. `@SecurityScheme` và `@SecurityRequirement` giúp Swagger UI cùng client hiểu cách gửi thông tin xác thực; chúng không tự bật HTTP Basic, không xác minh JWT và không bảo vệ controller. Những việc đó phải được cấu hình riêng bằng Spring Security.

## 1. HTTP Basic Authentication

HTTP Basic là cơ chế xác thực đơn giản được định nghĩa trong HTTP. Client gửi tên người dùng và mật khẩu trong header `Authorization` theo dạng:

```http
Authorization: Basic <base64(username:password)>
```

Ví dụ với tài khoản minh họa `api-user` và mật khẩu `example-password`, client nối hai giá trị bằng dấu hai chấm rồi mã hóa chuỗi thành Base64. Header có dạng:

```http
GET /api/profile HTTP/1.1
Host: api.example.com
Authorization: Basic YXBpLXVzZXI6ZXhhbXBsZS1wYXNzd29yZA==
```

Base64 chỉ là cách biểu diễn dữ liệu, không phải mã hóa bảo mật. Người có thể đọc header có thể giải mã để lấy lại tên người dùng và mật khẩu. Vì vậy, HTTP Basic phải được sử dụng qua HTTPS/TLS; không gửi credential qua kết nối HTTP thuần.

### Đặc điểm của Basic

- Cấu trúc đơn giản, được nhiều HTTP client hỗ trợ.
- Client thường gửi credential ở mỗi request cần xác thực.
- Server phải kiểm tra credential với kho người dùng hoặc authentication provider.
- Không có cơ chế hết hạn token riêng; vòng đời credential phụ thuộc chính sách tài khoản và cách client lưu trữ.
- Không phù hợp để nhúng mật khẩu người dùng vào ứng dụng phân phối rộng nếu có cơ chế cấp token an toàn hơn.

HTTP Basic không tự định nghĩa vai trò hay quyền truy cập. Sau khi xác thực thành công, ứng dụng vẫn phải kiểm tra authorization, chẳng hạn người dùng có role `ADMIN` hay quyền đọc tài nguyên được yêu cầu hay không.

## 2. HTTP Bearer Authentication

HTTP Bearer sử dụng một bearer token. Client gửi token trong header:

```http
Authorization: Bearer <access-token>
```

Ví dụ:

```http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.example.signature
```

Token có thể là JWT hoặc chuỗi opaque. Với JWT, token thường chứa claims và có chữ ký để server kiểm tra tính toàn vẹn. Với opaque token, server có thể tra cứu hoặc introspect token tại authorization server. Cả hai trường hợp đều dùng cú pháp HTTP Bearer ở header.

Bearer có nghĩa là bên sở hữu token có thể sử dụng token đó theo quyền được cấp. Vì vậy, token phải được bảo vệ như một credential:

- Chỉ truyền qua HTTPS/TLS.
- Không ghi access token vào log, URL, query parameter hoặc thông báo lỗi.
- Giới hạn thời hạn và phạm vi quyền phù hợp.
- Có quy trình thu hồi, xoay vòng hoặc làm mới token theo kiến trúc xác thực.
- Lưu token ở nơi phù hợp với loại client; tránh lưu trữ không an toàn trong trình duyệt.

Bearer không đồng nghĩa với JWT. JWT chỉ là một định dạng token phổ biến có thể được dùng với Bearer scheme. Một bearer token có thể là opaque token và không có cấu trúc JWT.

## 3. So sánh HTTP Basic và HTTP Bearer

| Tiêu chí | HTTP Basic | HTTP Bearer |
|---|---|---|
| Giá trị trong `Authorization` | `Basic base64(username:password)` | `Bearer token` |
| Thông tin gửi đi | Tên người dùng và mật khẩu | Access token |
| Xác minh phía server | Authentication provider kiểm tra credential | JWT decoder, token introspection hoặc cơ chế xác minh token |
| Vòng đời | Theo credential/tài khoản | Theo token, thường có thời hạn |
| JWT bắt buộc? | Không | Không; Bearer có thể dùng JWT hoặc opaque token |
| Mức độ phù hợp | API nội bộ, công cụ đơn giản hoặc môi trường kiểm soát chặt | API hiện đại, client ứng dụng, OAuth 2.0 resource server |
| Rủi ro chính | Mật khẩu được gửi lặp lại nếu không có TLS | Token bị đánh cắp có thể bị sử dụng cho đến khi hết hạn/thu hồi |

Không có cơ chế nào tự bảo đảm an toàn nếu triển khai sai. Basic cần TLS và quản lý mật khẩu đúng cách; Bearer cần bảo vệ token, kiểm tra chữ ký/issuer/audience/expiry hoặc introspection phù hợp.

## 4. Khai báo HTTP security scheme trong OpenAPI

OpenAPI biểu diễn Basic và Bearer bằng Security Scheme Object có `type: http`. Trường `scheme` xác định cơ chế HTTP:

```yaml
components:
  securitySchemes:
    basicAuth:
      type: http
      scheme: basic
      description: Xác thực HTTP Basic qua HTTPS
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
      description: Access token gửi trong Authorization header
```

Giải thích:

- `type: http` cho biết đây là HTTP authentication scheme.
- `scheme: basic` khai báo HTTP Basic.
- `scheme: bearer` khai báo HTTP Bearer.
- `bearerFormat: JWT` là gợi ý định dạng token cho người đọc và công cụ; nó không bắt server xác minh JWT và không thay thế cấu hình decoder.
- `description` giải thích cách lấy và sử dụng credential.

Nếu ứng dụng dùng opaque token, có thể bỏ `bearerFormat` hoặc mô tả định dạng nội bộ bằng giá trị phù hợp. Không ghi `JWT` chỉ vì token trông giống chuỗi có dấu chấm; cần dựa vào thiết kế xác thực thực tế.

## 5. Gắn security scheme vào operation bằng Security Requirement

Chỉ khai báo `components.securitySchemes` chưa có nghĩa operation yêu cầu xác thực. Muốn gắn một scheme vào operation, OpenAPI dùng Security Requirement Object.

Ví dụ một operation yêu cầu Bearer:

```yaml
paths:
  /api/orders:
    get:
      operationId: listOrders
      security:
        - bearerAuth: []
      responses:
        '200':
          description: Danh sách đơn hàng
        '401':
          description: Chưa xác thực hoặc token không hợp lệ
```

Tên `bearerAuth` phải khớp key trong `components.securitySchemes`. Với HTTP Basic và HTTP Bearer, danh sách scope là mảng rỗng `[]`; scope được dùng với OAuth 2.0 hoặc OpenID Connect, không phải HTTP Basic/Bearer scheme thuần.

Có thể gắn Basic cho một operation khác:

```yaml
paths:
  /api/admin/audit:
    get:
      security:
        - basicAuth: []
      responses:
        '200':
          description: Nhật ký quản trị
```

## 6. Bảo vệ toàn bộ tài liệu hoặc từng operation

OpenAPI cho phép khai báo security ở cấp document hoặc cấp operation.

### Security toàn cục

Khi phần lớn API yêu cầu Bearer, có thể khai báo ở cấp gốc:

```yaml
security:
  - bearerAuth: []
```

Các operation kế thừa security requirement này nếu không khai báo `security` riêng.

### Security riêng cho operation

Một operation có thể thay đổi quy tắc kế thừa. Ví dụ endpoint đăng nhập hoặc health check là public:

```yaml
paths:
  /api/health:
    get:
      security: []
      responses:
        '200':
          description: Ứng dụng đang hoạt động
```

`security: []` ở operation có nghĩa là không yêu cầu security scheme theo OpenAPI cho operation đó, kể cả khi document có security toàn cục. Đây là cách mô tả endpoint công khai trong tài liệu; server vẫn phải được cấu hình đúng để cho phép truy cập công khai.

### Chọn nhiều scheme thay thế nhau

Nếu một operation chấp nhận Basic hoặc Bearer, khai báo hai Security Requirement Object riêng biệt:

```yaml
security:
  - basicAuth: []
  - bearerAuth: []
```

Các phần tử trong mảng là lựa chọn **OR**: client có thể dùng Basic hoặc Bearer.

Nếu một operation yêu cầu đồng thời cả hai scheme, đặt chúng trong cùng một object:

```yaml
security:
  - basicAuth: []
    bearerAuth: []
```

Các scheme trong cùng một object là điều kiện **AND**: client phải thỏa mãn cả hai. Chỉ dùng cách này nếu server thật sự yêu cầu cả hai credential; không nhầm nó với hai phương án xác thực thay thế.

## 7. Khai báo Basic và Bearer bằng springdoc annotations

Springdoc đọc các annotation của Swagger để tạo security scheme và requirement. Có thể khai báo cả hai scheme trên class cấu hình:

```java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.security.SecuritySchemes;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Order API",
        version = "1.0.0",
        description = "API quản lý đơn hàng"
    )
)
@SecuritySchemes({
    @SecurityScheme(
        name = "basicAuth",
        type = SecuritySchemeType.HTTP,
        scheme = "basic",
        description = "Tên người dùng và mật khẩu qua HTTPS"
    ),
    @SecurityScheme(
        name = "bearerAuth",
        type = SecuritySchemeType.HTTP,
        scheme = "bearer",
        bearerFormat = "JWT",
        description = "Access token Bearer"
    )
})
class OpenApiSecurityConfiguration {
}
```

Các import và annotation trên thuộc Swagger Annotations được springdoc tích hợp. Nếu dự án đang dùng major version khác, hãy kiểm tra phiên bản dependency và package tương ứng.

`@SecurityScheme` tạo phần tử trong `components.securitySchemes`. Nó chưa tự gắn scheme vào mọi operation; cần thêm `@SecurityRequirement` hoặc khai báo security ở cấp document.

## 8. Gắn `@SecurityRequirement` ở cấp controller hoặc method

Có thể gắn requirement lên controller để các operation trong controller dùng cùng cơ chế, hoặc gắn riêng lên method để có phạm vi chính xác hơn.

Ví dụ một controller yêu cầu Bearer:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import java.util.List;

@RestController
@RequestMapping("/api/orders")
@SecurityRequirement(name = "bearerAuth")
class OrderController {

    @Operation(summary = "Liệt kê đơn hàng")
    @GetMapping
    List<OrderResponse> listOrders() {
        return orderService.listOrders();
    }
}
```

Nếu chỉ một endpoint quản trị dùng Basic:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import java.util.List;

@RestController
@RequestMapping("/api/admin")
class AdminController {

    @Operation(
        summary = "Đọc nhật ký quản trị",
        security = @SecurityRequirement(name = "basicAuth")
    )
    @GetMapping("/audit")
    List<AuditEntry> audit() {
        return auditService.findRecent();
    }
}
```

`OrderResponse`, `AuditEntry`, `orderService` và `auditService` là các thành phần minh họa. Tên trong `@SecurityRequirement(name = ...)` phải khớp chính xác tên scheme đã khai báo.

Nếu document có security toàn cục nhưng một method là public, cần cấu hình operation để bỏ security requirement kế thừa theo cách Swagger Annotations của phiên bản đang dùng hỗ trợ, rồi xác minh kết quả trong `/v3/api-docs`. Có thể điều chỉnh bằng customizer nếu annotation không diễn đạt được trường hợp cần thiết. Không dựa vào việc ẩn nút Authorize trong Swagger UI để coi endpoint là public.

## 9. Ví dụ OpenAPI đầy đủ cho Basic và Bearer

Tài liệu sau minh họa API có endpoint public, endpoint dùng Bearer và endpoint chấp nhận Basic hoặc Bearer:

```yaml
openapi: 3.0.3
info:
  title: Order API
  version: '1.0.0'
components:
  securitySchemes:
    basicAuth:
      type: http
      scheme: basic
      description: HTTP Basic qua HTTPS
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
      description: Access token Bearer
security:
  - bearerAuth: []
paths:
  /api/health:
    get:
      security: []
      responses:
        '200':
          description: Health check công khai
  /api/orders:
    get:
      operationId: listOrders
      responses:
        '200':
          description: Danh sách đơn hàng
        '401':
          description: Thiếu hoặc sai token
  /api/admin/audit:
    get:
      operationId: getAuditLog
      security:
        - basicAuth: []
        - bearerAuth: []
      responses:
        '200':
          description: Nhật ký quản trị
        '401':
          description: Chưa xác thực
        '403':
          description: Không đủ quyền quản trị
```

Trong ví dụ:

- `/api/health` công khai nhờ `security: []`.
- `/api/orders` kế thừa Bearer từ cấp document.
- `/api/admin/audit` thay security kế thừa bằng hai phương án Basic hoặc Bearer.

Tài liệu mô tả cách client gửi credential. Việc người dùng đã xác thực có được đọc audit log hay không vẫn phụ thuộc authorization ở server.

## 10. Swagger UI và nút Authorize

Khi OpenAPI document có `components.securitySchemes` cùng Security Requirement, Swagger UI có thể hiển thị nút **Authorize**. Người dùng nhập credential tương ứng:

- Với `basicAuth`, giao diện yêu cầu tên người dùng và mật khẩu.
- Với `bearerAuth`, giao diện nhận access token; Swagger UI sẽ tạo header theo scheme Bearer.

Sau khi authorize, Swagger UI gửi thông tin xác thực trong header `Authorization` cho các operation có yêu cầu scheme tương ứng. Operation public có `security: []` không cần scheme đó.

Đối với Bearer, thông thường người dùng nhập phần token, không tự thêm tiền tố `Bearer ` nếu giao diện đã nhận biết scheme là HTTP Bearer và tự tạo header. Hãy kiểm tra request thực tế trong Swagger UI để tránh gửi `Bearer Bearer ...`.

Nút Authorize chỉ hỗ trợ thử API từ giao diện. Nó không cấp token, không kiểm tra token thay server và không tự bảo vệ trang Swagger UI hoặc endpoint `/v3/api-docs`.

## 11. Cấu hình HTTP Basic trong Spring Security

Để API thực sự chấp nhận Basic, ứng dụng cần Spring Security và authentication provider phù hợp. Ví dụ cấu hình tối giản cho môi trường minh họa:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class BasicSecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("api-user")
                        .password(encoder.encode("change-this-password"))
                        .roles("USER")
                        .build()
        );
    }

    @Bean
    SecurityFilterChain basicSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/public/**").permitAll()
                        .requestMatchers("/api/admin/**").hasRole("ADMIN")
                        .anyRequest().authenticated()
                )
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

Đây là cấu hình minh họa, không phải cách lưu tài khoản production. Tài khoản ví dụ chỉ có role `USER`, nên nếu gọi `/api/admin/**` sẽ nhận `403`; hệ thống thực cần cấp role `ADMIN` cho người được phép. Nên dùng user store, identity provider hoặc authentication provider phù hợp; không hard-code mật khẩu trong source code. `BCryptPasswordEncoder` giúp lưu password hash thay vì password rõ.

`httpBasic()` bật cơ chế xử lý HTTP Basic. Nó không tự tạo OpenAPI security scheme; phần tài liệu vẫn cần khai báo bằng springdoc annotations hoặc OpenAPI configuration.

## 12. Cấu hình HTTP Bearer với JWT Resource Server

Nếu access token là JWT, Spring Security có thể xác minh token thông qua OAuth 2.0 Resource Server support. Dự án cần dependency resource server phù hợp, ví dụ `spring-boot-starter-oauth2-resource-server` theo phiên bản Spring Boot đang dùng.

Ví dụ cấu hình:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class BearerSecurityConfiguration {

    @Bean
    SecurityFilterChain bearerSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/public/**").permitAll()
                        .requestMatchers("/api/admin/**").hasRole("ADMIN")
                        .anyRequest().authenticated()
                )
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
```

Có thể cấu hình issuer qua property:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/issuer
```

Spring Security sử dụng issuer metadata/JWK theo cấu hình để xác minh JWT. Trong môi trường thực, cần xác định issuer, audience, thuật toán, thời hạn, claim mapping và quyền truy cập phù hợp với authorization server. Chỉ khai báo `bearerFormat: JWT` trong OpenAPI không cấu hình bất kỳ bước xác minh nào.

Nếu token là opaque, dùng cấu hình opaque token/introspection phù hợp thay vì `jwt()`. OpenAPI vẫn có thể dùng HTTP Bearer scheme vì cú pháp header không phụ thuộc token là JWT hay opaque.

## 13. Khi một ứng dụng chấp nhận cả Basic và Bearer

Spring Security có thể cấu hình nhiều cơ chế xác thực trong cùng ứng dụng, nhưng cần xác định rõ endpoint nào chấp nhận cơ chế nào. Một cấu hình có cả `.httpBasic(...)` và `.oauth2ResourceServer(...)` không tự bảo đảm mọi endpoint đều chấp nhận cả hai theo đúng ý muốn; authorization rules, authentication providers và filter chain phải phù hợp.

Hai class cấu hình Basic và Bearer ở trên là các ví dụ độc lập. Không đăng ký đồng thời hai filter chain cùng bắt mọi request mà không có matcher và thứ tự rõ ràng. Có thể chia `SecurityFilterChain` theo path hoặc request matcher để cô lập API Basic và Bearer. Ví dụ, một nhóm API cũ dùng Basic còn API public-facing mới dùng Bearer. Khi làm vậy:

- Xác định thứ tự và matcher của từng filter chain.
- Đảm bảo mỗi request chỉ đi vào chain phù hợp.
- Cấu hình authentication provider cho Basic.
- Cấu hình JWT decoder hoặc opaque token introspection cho Bearer.
- Dùng role/authority mapping nhất quán.
- Mô tả đúng scheme tương ứng ở từng operation trong OpenAPI.

Nếu một endpoint thật sự chấp nhận một trong hai cơ chế, OpenAPI cần mô tả hai phương án là OR. Nếu tài liệu ghi OR nhưng server chỉ bật một cơ chế, client sẽ gặp lỗi xác thực dù Swagger UI cho phép chọn cả hai.

## 14. Phân biệt Authentication và Authorization

Authentication xác định danh tính hoặc tính hợp lệ của credential. Authorization quyết định danh tính đó được phép làm gì.

Ví dụ:

- Basic credentials đúng hoặc Bearer token hợp lệ: authentication thành công.
- Người dùng có role `USER` gọi endpoint chỉ dành cho `ADMIN`: authorization thất bại.
- Token hết hạn, chữ ký sai hoặc mật khẩu sai: authentication thất bại.

Các response thường gặp:

| HTTP status | Ý nghĩa thường dùng |
|---|---|
| `401 Unauthorized` | Thiếu credential, credential sai hoặc token không hợp lệ/hết hạn |
| `403 Forbidden` | Đã xác thực nhưng không đủ quyền thực hiện thao tác |

Server thường trả `WWW-Authenticate` challenge trong response `401` để chỉ ra cơ chế xác thực. Với Basic, challenge có thể là `WWW-Authenticate: Basic realm="..."`; với Bearer, challenge có thể nêu `Bearer` cùng error metadata phù hợp.

OpenAPI có thể mô tả response `401` và `403`, nhưng không tự tạo challenge header hoặc quyết định status code. Spring Security authentication entry point và access denied handler chịu trách nhiệm runtime.

## 15. CORS và header Authorization

Nếu frontend gọi API từ origin khác, trình duyệt có thể gửi CORS preflight vì `Authorization` là request header không thuộc nhóm simple headers. Server phải cho phép origin, method và header phù hợp.

Ví dụ cấu hình CORS cần cho phép header `Authorization`:

```java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration configuration = new CorsConfiguration();
    configuration.setAllowedOrigins(List.of("https://app.example.com"));
    configuration.setAllowedMethods(List.of("GET", "POST", "PUT", "PATCH", "DELETE"));
    configuration.setAllowedHeaders(List.of("Authorization", "Content-Type"));

    UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", configuration);
    return source;
}
```

Đăng ký `CorsConfigurationSource` cùng filter chain và bật tích hợp CORS:

```java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
```

Đây là ví dụ cần tích hợp với filter chain và chính sách CORS hiện có. Không dùng wildcard origin một cách tùy tiện cho API có credential. CORS là chính sách trình duyệt; nó không thay thế xác thực hoặc phân quyền ở server.

## 16. HTTPS, CSRF và lưu trữ credential

Basic và Bearer đều cần TLS để bảo vệ thông tin xác thực khi truyền. Cần triển khai HTTPS ở ứng dụng hoặc reverse proxy đáng tin cậy và cấu hình forwarded headers đúng để ứng dụng hiểu scheme bên ngoài.

CSRF cần được quyết định theo cách credential được gửi và mô hình client. Nếu trình duyệt tự động gửi cookie/session, CSRF là rủi ro cần xử lý. Với API stateless dùng Bearer token được client gắn thủ công trong `Authorization`, mô hình rủi ro khác, nhưng không nên tắt CSRF một cách máy móc nếu ứng dụng còn endpoint dùng cookie hoặc session. Hãy cấu hình theo từng security chain và loại client.

Không lưu password hoặc token trong query string. URL thường xuất hiện trong log, lịch sử trình duyệt, analytics và Referer. Với Swagger UI, chỉ dùng credential thử nghiệm có phạm vi và thời hạn phù hợp; không lưu token production trong tài liệu, ví dụ hoặc cấu hình chia sẻ.

## 17. Kiểm tra security scheme trong tài liệu được sinh

Sau khi thêm annotations, mở `/v3/api-docs` hoặc `/v3/api-docs.yaml` và xác nhận:

1. `components.securitySchemes.basicAuth` có `type: http`, `scheme: basic`.
2. `components.securitySchemes.bearerAuth` có `type: http`, `scheme: bearer`.
3. `bearerFormat` phản ánh đúng loại token nếu được khai báo.
4. Operation cần bảo vệ có `security` tham chiếu đúng tên scheme.
5. Endpoint public có `security: []` nếu document đang khai báo security toàn cục.
6. Nếu Basic hoặc Bearer là lựa chọn thay thế, mỗi scheme nằm trong một Security Requirement Object riêng.
7. Nếu bắt buộc đồng thời hai scheme, cả hai key nằm trong cùng một object.
8. Swagger UI hiển thị đúng loại credential khi bấm Authorize.
9. Request thử nghiệm thực sự gửi `Authorization: Basic ...` hoặc `Authorization: Bearer ...` theo scheme đã chọn.

Không dừng ở việc Swagger UI hiển thị nút Authorize. Tài liệu phải gắn requirement vào đúng operation; nếu chỉ khai báo scheme mà không có requirement, công cụ có thể không biết operation nào cần dùng scheme đó.

## 18. Kiểm thử Spring Security runtime

Kiểm tra OpenAPI và kiểm tra bảo mật runtime là hai phần riêng. Với từng endpoint cần bảo vệ, nên thử các trường hợp:

| Trường hợp | Kết quả thường mong đợi |
|---|---|
| Không gửi `Authorization` | `401` nếu endpoint yêu cầu xác thực |
| Basic username/password sai | `401` |
| Bearer token sai chữ ký hoặc hết hạn | `401` |
| Credential hợp lệ nhưng thiếu role | `403` |
| Credential hợp lệ và đủ quyền | Status thành công theo nghiệp vụ |
| Endpoint public không gửi credential | Có thể truy cập theo chính sách public |

Có thể dùng curl để thử Basic:

```bash
curl -i -u api-user:example-password \
  https://api.example.com/api/profile
```

Và Bearer:

```bash
curl -i \
  -H "Authorization: Bearer <access-token>" \
  https://api.example.com/api/orders
```

Chỉ dùng credential thử nghiệm. Không đưa token hoặc mật khẩu thật vào shell history, ticket hoặc log chia sẻ. Nếu cần kiểm thử tự động, dùng test user và token có phạm vi nhỏ trong môi trường test.

## 19. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Swagger UI không có nút Authorize | Chỉ khai báo operation requirement nhưng thiếu scheme, hoặc ngược lại | Kiểm tra `components.securitySchemes` và `security` |
| Nút Authorize có nhưng endpoint vẫn trả 401 | Spring Security runtime chưa bật cơ chế tương ứng hoặc credential sai | Cấu hình Basic/resource server và kiểm tra request header |
| Bearer bị gửi thành `Bearer Bearer ...` | Người dùng tự nhập cả prefix trong khi UI đã thêm scheme | Nhập token theo hướng dẫn của dialog và kiểm tra header thực tế |
| `bearerFormat: JWT` nhưng JWT không được xác minh | Nhầm metadata OpenAPI với cấu hình decoder | Cấu hình OAuth2 Resource Server/JWT decoder |
| Basic credentials bị lộ | Dùng HTTP không có TLS hoặc log header | Bắt buộc HTTPS và lọc thông tin xác thực khỏi log |
| Endpoint public vẫn hiện yêu cầu xác thực | Kế thừa global security nhưng chưa override operation | Khai báo `security: []` và xác minh OpenAPI output |
| Một operation chấp nhận cả hai scheme nhưng tài liệu yêu cầu cả hai | Đặt Basic và Bearer trong cùng một Security Requirement Object | Tách thành hai object để diễn đạt OR |
| Người dùng đã đăng nhập nhưng nhận 403 | Authentication thành công nhưng thiếu authority/role | Kiểm tra authorization mapping và rule của endpoint |
| Browser bị CORS block | CORS chưa cho phép header Authorization hoặc preflight | Cấu hình allowed origin/method/header phù hợp |
| Tài liệu ghi Basic/Bearer nhưng server không có cơ chế đó | Chỉ cấu hình springdoc annotations | Cấu hình Spring Security và kiểm thử runtime |

## 20. Nguyên tắc thiết kế

- Dùng `type: http`, `scheme: basic` để mô tả HTTP Basic.
- Dùng `type: http`, `scheme: bearer` để mô tả HTTP Bearer; chỉ ghi `bearerFormat: JWT` khi phù hợp.
- Khai báo security scheme trong `components` và gắn requirement vào document hoặc operation.
- Dùng các Security Requirement Object riêng để diễn đạt Basic **hoặc** Bearer; dùng chung một object chỉ khi cần cả hai.
- Dùng `security: []` cho operation public khi document có security toàn cục.
- Dùng `@SecurityScheme`/`@SecuritySchemes` để khai báo scheme và `@SecurityRequirement` để gắn scheme vào operation.
- Cấu hình Spring Security riêng cho Basic authentication hoặc Bearer resource server.
- Bảo vệ credential và token bằng HTTPS, quản lý vòng đời và không ghi vào log.
- Phân biệt authentication với authorization; kiểm tra cả `401` và `403`.
- Kiểm tra CORS nếu browser client gửi header `Authorization`.
- Xác minh tài liệu `/v3/api-docs` cùng request thực tế từ Swagger UI và client ngoài.

## Kết luận

HTTP Basic gửi tên người dùng và mật khẩu dưới dạng Base64 trong `Authorization`; HTTP Bearer gửi access token trong cùng header. OpenAPI mô tả chúng bằng HTTP security scheme với `scheme: basic` hoặc `scheme: bearer`, sau đó dùng Security Requirement để chỉ rõ operation nào cần xác thực và cơ chế nào được chấp nhận. Springdoc cung cấp `@SecurityScheme` và `@SecurityRequirement` để sinh metadata, còn Spring Security mới thực hiện xác minh credential, token và quyền truy cập. Hãy đồng bộ hợp đồng với runtime, bắt buộc HTTPS, bảo vệ credential và kiểm tra cả trường hợp `401`, `403` lẫn endpoint công khai.
