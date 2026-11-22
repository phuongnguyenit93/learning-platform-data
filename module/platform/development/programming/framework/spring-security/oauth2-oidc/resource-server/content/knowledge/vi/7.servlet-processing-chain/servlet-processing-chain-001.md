# SecurityFilterChain và vị trí xử lý Bearer token

## 1. Resource Server bảo vệ request ở đâu?

Trong ứng dụng **Spring Boot + Spring Security OAuth 2.0 Resource Server** chạy trên **Servlet stack** (Spring MVC), việc xác thực Bearer access token diễn ra ở **chuỗi Servlet Filter** trước khi yêu cầu đi tới `DispatcherServlet` và controller.

Ví dụ:

~~~http
GET /api/orders HTTP/1.1
Host: orders.example.test
Authorization: Bearer eyJhbGciOi...
~~~

Để request trên được xử lý an toàn, hệ thống phải thực hiện nhiều bước:

1. Chọn đúng cấu hình bảo mật áp dụng cho đường dẫn `/api/orders`.
2. Tìm chuỗi Bearer access token trong HTTP request.
3. Xác thực access token bằng JWT signature/claim validation hoặc opaque token introspection.
4. Đưa thông tin xác thực thành công vào `SecurityContext`.
5. Kiểm tra quyền của caller đối với endpoint và tài nguyên.
6. Cho phép request đi tiếp vào controller nếu vượt qua các quy tắc áp dụng.

Các bước này do nhiều filter và component phối hợp, **không phải toàn bộ công việc của một filter duy nhất**.

Bài học tập trung vào câu hỏi: **`SecurityFilterChain` nằm ở đâu trong Servlet request lifecycle, `BearerTokenAuthenticationFilter` được chạy ở giai đoạn nào, và kết quả xác thực được dùng ra sao trước khi phân quyền?**

## 2. Phân biệt ba lớp “filter chain”

### 2.1. Servlet Filter Chain của container

Servlet container như Tomcat tạo **Servlet Filter Chain** cho một request. Filter được gọi trước Servlet đích, có thể đọc request, thêm response header, quyết định tiếp tục hay dừng xử lý.

Khái quát:

~~~text
HTTP client
   |
   v
Servlet container
   |
   v
Servlet Filter 1 -> Servlet Filter 2 -> ... -> DispatcherServlet
                                                |
                                                v
                                           Spring MVC Controller
~~~

Trong một ứng dụng có Spring Security, container không trực tiếp quản lý từng Spring Security filter như `BearerTokenAuthenticationFilter`. Thay vào đó, container thường gọi một **`DelegatingFilterProxy`**.

### 2.2. `DelegatingFilterProxy`: cầu nối Servlet container và Spring

`DelegatingFilterProxy` là Servlet Filter ủy quyền công việc cho một Spring bean. Với Spring Security, tên bean thông dụng là `springSecurityFilterChain`, thực tế được cung cấp bởi **`FilterChainProxy`**.

Sơ đồ:

~~~text
Servlet container filter chain
             |
             v
DelegatingFilterProxy (springSecurityFilterChain)
             |
             v
FilterChainProxy (Spring Security)
             |
             v
SecurityFilterChain được chọn
             |
             v
Các Spring Security filters
             |
             v
DispatcherServlet / Controller
~~~

Như vậy, `DelegatingFilterProxy` giải quyết việc tích hợp với Servlet container, còn `FilterChainProxy` điều phối **chuỗi filter bảo mật** do Spring Security định nghĩa.

### 2.3. `FilterChainProxy` và `SecurityFilterChain`

**`FilterChainProxy`** là filter điều phối của Spring Security. Nó có thể chứa **nhiều `SecurityFilterChain`**, mỗi chain có một request matcher và danh sách security filters.

**`SecurityFilterChain`** không phải là một filter đơn lẻ. Nó thể hiện:

- **Request nào được chain này bảo vệ?** — matcher, ví dụ `/api/**`.
- **Những filter Spring Security nào sẽ chạy cho request đó?** — xác thực, xử lý context, phân quyền, exception handling, v.v.

Khi có nhiều chain, `FilterChainProxy` xem xét theo thứ tự và dùng **chain đầu tiên khớp request**. Nó không tự ghép filter từ tất cả các chain khớp cùng lúc.

> Phân biệt: `SecurityFilterChain` chọn **pipeline bảo mật**; `authorizeHttpRequests` định nghĩa **quyền truy cập bên trong pipeline đã được chọn**. Hai bước này khác nhau.

## 3. Toàn cảnh request Bearer token trong Servlet stack

~~~mermaid
flowchart TD
    A["HTTP request có Authorization: Bearer ..."] --> B["Servlet container"]
    B --> C["DelegatingFilterProxy"]
    C --> D["FilterChainProxy"]
    D --> E{"SecurityFilterChain đầu tiên khớp?"}
    E -->|"Không có chain"| Z["Không có bảo vệ từ Spring Security chain"]
    E -->|"Có chain"| F["SecurityContextHolderFilter và các filter hỗ trợ"]
    F --> G["BearerTokenAuthenticationFilter"]
    G --> H["BearerTokenResolver tìm token"]
    H --> I{"Có Bearer token?"}
    I -->|"Có"| J["AuthenticationManager"]
    J --> K["JwtAuthenticationProvider hoặc OpaqueTokenAuthenticationProvider"]
    K --> L{"Xác thực hợp lệ?"}
    L -->|"Không"| M["Xử lý lỗi xác thực, thường 401"]
    L -->|"Có"| N["Đặt Authentication vào SecurityContext"]
    I -->|"Không"| O["Tiếp tục các filter còn lại"]
    N --> O
    O --> P["AnonymousAuthenticationFilter nếu chưa có Authentication"]
    P --> Q["ExceptionTranslationFilter / AuthorizationFilter"]
    Q --> R{"Quyền truy cập hợp lệ?"}
    R -->|"Không"| S["401 hoặc 403 tùy nguyên nhân"]
    R -->|"Có"| T["DispatcherServlet / Controller"]
~~~

Đây là sơ đồ **khái niệm**. Danh sách, vị trí chính xác và sự có mặt của từng filter phụ thuộc cấu hình và phiên bản Spring Security. Trong thực tế còn có filter cho headers, CORS, CSRF, logout, request cache, anonymous authentication và nhiều chức năng khác.

Những điều luôn cần hiểu trong luồng Resource Server:

- `FilterChainProxy` phải chọn được đúng chain.
- Chain nhận Bearer token cần có `BearerTokenAuthenticationFilter` (thường do `oauth2ResourceServer` thêm).
- Authentication được thực hiện **trước quyết định phân quyền endpoint**.
- `AuthorizationFilter` có thể sử dụng thông tin `Authentication` sau khi Bearer token đã xác thực.
- Request không có Bearer token có thể tiếp tục qua chain, nhưng endpoint yêu cầu xác thực cuối cùng vẫn bị từ chối nếu không có phương thức xác thực khác.

### 3.1. Ví dụ thứ tự tương đối của các filter

Trong cấu hình Spring Security Servlet hiện đại, có thể hình dung một phần chuỗi như sau:

~~~text
SecurityContextHolderFilter
    |
    v
HeaderWriterFilter / CorsFilter / CsrfFilter / ...  (nếu cấu hình)
    |
    v
LogoutFilter / các filter xác thực khác (nếu có)
    |
    v
BearerTokenAuthenticationFilter
    |
    v
RequestCacheAwareFilter / SecurityContextHolderAwareRequestFilter / ...
    |
    v
AnonymousAuthenticationFilter
    |
    v
ExceptionTranslationFilter
    |
    v
AuthorizationFilter
    |
    v
Controller nếu được phép
~~~

Thứ tự trên giúp hình dung những mốc xử lý quan trọng, **không phải danh sách filter cố định cho mọi ứng dụng**. Ví dụ một API chỉ xác thực Bearer token sẽ không cần chạy form login; ứng dụng đồng thời hỗ trợ session login có thể chứa thêm các filter tương ứng.

Hai quy tắc thứ tự cần ghi nhớ:

1. `BearerTokenAuthenticationFilter` phải có cơ hội xác thực Bearer token **trước khi authorization quyết định quyền truy cập**.
2. `AnonymousAuthenticationFilter` có thể cung cấp principal vô danh khi chưa có xác thực; nó **không biến request vô danh thành request đã đăng nhập hợp lệ**.

## 4. Cấu hình một SecurityFilterChain cho JWT Resource Server

### 4.1. Dependencies và issuer

Ví dụ Spring Boot dùng Spring MVC và JWT access token:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
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
          issuer-uri: https://id.example.test/realms/shop
~~~

`issuer-uri` là ví dụ giả định; phải thay bằng issuer thật của Authorization Server. Với provider hỗ trợ metadata/JWKS phù hợp, Spring có thể dùng cấu hình issuer để xác định khóa xác minh JWT.

**Lưu ý:** kiểm tra JWT signature/issuer/thời hạn không tự bảo đảm rằng token dành cho đúng API. Với API yêu cầu giới hạn `aud`, cần cấu hình audience validation phù hợp phiên bản và hợp đồng token.

### 4.2. Định nghĩa filter chain

~~~java
package com.example.orders.security;

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
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            // Ví dụ API xác thực bằng Authorization: Bearer,
            // không dùng cookie/session để xác thực request.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

Ý nghĩa từng nhóm cấu hình:

| Thành phần | Vai trò |
|---|---|
| `SecurityFilterChain` bean | Tập quy tắc và filter bảo mật do Spring quản lý |
| `HttpSecurity` | DSL tạo chuỗi filter |
| `authorizeHttpRequests(...)` | Chính sách cho phép/từ chối từng endpoint |
| `oauth2ResourceServer(...jwt(...))` | Bật cơ chế xác thực Bearer JWT access token |
| `SessionCreationPolicy.STATELESS` | Không tạo/dùng `HttpSession` để lưu SecurityContext cho cơ chế xác thực của API |
| `csrf(AbstractHttpConfigurer::disable)` | Chỉ phù hợp theo giả định API dùng Bearer token ngoài cookie, không xác thực bằng cookie trình duyệt |

**Không tắt CSRF theo thói quen cho mọi ứng dụng.** Nếu có endpoint dùng cookie/session hoặc một cơ chế gửi credential tự động theo trình duyệt, cần phân tích và giữ bảo vệ CSRF thích hợp. `STATELESS` cũng không thay thế cấu hình CSRF hay quyết định về CORS.

Dòng bật `oauth2ResourceServer(...jwt(...))` là phần làm Spring Security xây pipeline hỗ trợ JWT Bearer; thông thường không cần tạo hay đăng ký `BearerTokenAuthenticationFilter` thủ công.

### 4.3. Request đi qua cấu hình này

Client gọi:

~~~bash
curl -i \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  https://api.example.test/api/orders
~~~

Nếu access token hợp lệ, có scope `orders.read` và vượt các ràng buộc khác, request GET được xử lý. Mặc định, Spring Security thường ánh xạ scope từ claim `scope`/`scp` tương thích thành authority với tiền tố `SCOPE_`, nên `orders.read` được kiểm tra qua `SCOPE_orders.read`.

Ví dụ controller:

~~~java
package com.example.orders.api;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrdersController {

    @GetMapping("/api/orders")
    public Map<String, String> currentSubject(
            @AuthenticationPrincipal Jwt jwt) {

        // Chỉ minh họa principal đã xác thực.
        // Endpoint thật còn phải kiểm tra quyền sở hữu đơn hàng.
        return Map.of("subject", jwt.getSubject());
    }
}
~~~

`@AuthenticationPrincipal Jwt` phù hợp với luồng Resource Server **JWT**. Nếu ứng dụng chọn **opaque token introspection**, principal thường là loại `OAuth2AuthenticatedPrincipal`, không nên mặc định ép về `Jwt`.

## 5. `BearerTokenAuthenticationFilter` làm gì?

`BearerTokenAuthenticationFilter` là filter chuyên trách tiếp nhận và xử lý Bearer access token trong Servlet request.

### 5.1. Bước 1 — Tìm token bằng `BearerTokenResolver`

Mặc định, resolver tìm:

~~~http
Authorization: Bearer <access_token>
~~~

`BearerTokenResolver` chỉ trả về chuỗi token hoặc không tìm thấy token; nó chưa xác thực nội dung.

Trong trường hợp không có Bearer token, filter thường để request đi tiếp. Điều này có ích vì một chain có thể có endpoint `permitAll` hoặc cơ chế xác thực khác.

Nếu header có giá trị Bearer sai định dạng, resolver có thể ném lỗi; filter xử lý theo nhánh xác thực thất bại.

### 5.2. Bước 2 — Tạo authentication request

Khi tìm được token, filter tạo đối tượng **`BearerTokenAuthenticationToken`** chứa chuỗi token và chuyển nó đến **`AuthenticationManager`** đã được cấu hình.

Dòng xử lý:

~~~text
HTTP Authorization header
         |
         v
BearerTokenResolver
         |
         v
String accessToken
         |
         v
BearerTokenAuthenticationToken
         |
         v
AuthenticationManager
         |
         v
AuthenticationProvider tương ứng
~~~

Trong thiết kế nâng cao, `BearerTokenAuthenticationFilter` có thể làm việc với `AuthenticationManagerResolver<HttpServletRequest>` để chọn manager theo request. Việc chọn issuer/manager phải dựa trên allowlist và trust policy, không tự tin bất kỳ issuer nào do token chưa xác minh khai báo.

### 5.3. Bước 3 — Xác thực JWT hoặc opaque token

Với JWT Resource Server:

~~~text
BearerTokenAuthenticationToken
        |
        v
JwtAuthenticationProvider
        |
        v
JwtDecoder (thường NimbusJwtDecoder)
        |
        v
Kiểm tra chữ ký + validator (issuer/time/audience/...)
        |
        v
JwtAuthenticationConverter
        |
        v
JwtAuthenticationToken (Authentication đã xác thực)
~~~

`JwtDecoder` có trách nhiệm xác minh chữ ký JWS và các validator theo cấu hình. `JwtAuthenticationConverter` chuyển claims thành principal/authorities. Mặc định, principal name thường dựa trên `sub` và scope hợp lệ có thể trở thành authority `SCOPE_<scope>`.

Với opaque token:

~~~text
BearerTokenAuthenticationToken
        |
        v
OpaqueTokenAuthenticationProvider
        |
        v
OpaqueTokenIntrospector
        |
        v
Kết quả introspection hợp lệ
        |
        v
BearerTokenAuthentication
~~~

Cả hai đều dùng Bearer token filter ở tầng HTTP; phần khác nhau là **cách token được xác thực và chuyển thành Authentication**.

### 5.4. Bước 4 — Lưu Authentication trong `SecurityContext`

Sau khi thành công, filter tạo `SecurityContext` và đặt `Authentication` đã được xác thực vào `SecurityContextHolder` cho việc xử lý request.

Các filter phía sau và controller có thể đọc context:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
~~~

Trong controller, thường nên dùng dependency injection hoặc `@AuthenticationPrincipal`:

~~~java
@GetMapping("/api/whoami")
public Map<String, String> whoAmI(Authentication authentication) {
    return Map.of("name", authentication.getName());
}
~~~

Khi request kết thúc, Spring Security quản lý việc dọn context theo lifecycle filter. **Đừng tự đặt biến static chứa Authentication** và cũng đừng nghĩ `SecurityContextHolder` là một nơi lưu đăng nhập vĩnh viễn của người dùng.

Với mô hình Bearer token stateless, request tiếp theo thông thường phải tiếp tục gửi token; `SessionCreationPolicy.STATELESS` giúp tránh phụ thuộc vào session để nhớ SecurityContext của request cũ.

### 5.5. Bước 5 — Tiếp tục filter chain

Sau khi authentication thành công, `BearerTokenAuthenticationFilter` gọi tiếp các filter sau nó. Đó là lý do một token hợp lệ **vẫn có thể bị từ chối quyền** tại `AuthorizationFilter`.

Filter Bearer có trách nhiệm **authentication**, còn authorization được thực thi qua các quy tắc như:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

và có thể thêm kiểm tra phân quyền nghiệp vụ khi đọc, sửa hoặc xóa bản ghi.

## 6. `AuthorizationFilter` xử lý quyền sau xác thực

Trong cấu hình hiện đại với `authorizeHttpRequests`, **`AuthorizationFilter`** thường nằm gần cuối Spring Security chain. Nó ủy quyền quyết định cho `AuthorizationManager` dựa trên request và `Authentication` hiện tại.

Ví dụ:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/public/**").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.POST, "/api/orders/**")
        .hasAuthority("SCOPE_orders.write")
    .anyRequest().denyAll()
)
~~~

Ý nghĩa:

- `permitAll()`: endpoint không yêu cầu quyền ở bước authorization này.
- `authenticated()`: cần một authentication được Spring Security coi là đã xác thực, không phải anonymous.
- `hasAuthority("SCOPE_orders.read")`: cần authority cụ thể.
- `denyAll()`: từ chối dù request có token hợp lệ.

Quy tắc được xét theo matcher, vì thế nên đặt rule cụ thể trước rule tổng quát.

Một token JWT được ký đúng với scope `orders.write` **không tự đáp ứng** rule cần `orders.read`. API phải quyết định chính xác những quyền nào được yêu cầu.

**Quan trọng:** `AuthorizationFilter` kiểm tra quyền ở mức request/endpoint. Khi endpoint trả một đơn hàng cụ thể, tầng nghiệp vụ vẫn cần kiểm tra chủ sở hữu, tenant hoặc access-control-list (ACL). Scope chỉ là một phần của quyết định cấp quyền.

## 7. Một request: bốn tình huống điển hình

### 7.1. Không có Bearer token

Request:

~~~http
GET /api/orders HTTP/1.1
~~~

Luồng thường thấy:

1. `BearerTokenResolver` không tìm token.
2. `BearerTokenAuthenticationFilter` để request đi tiếp mà không tạo authenticated principal.
3. `AnonymousAuthenticationFilter` có thể đặt anonymous authentication.
4. `AuthorizationFilter` thấy endpoint cần `SCOPE_orders.read` nhưng request chưa có authentication phù hợp.
5. Hệ thống xử lý lỗi, thông thường trả **401 Unauthorized** với Bearer entry point.

Nếu endpoint là `permitAll` và không có yêu cầu khác, request vẫn có thể đi tới controller khi không có token.

### 7.2. Có token nhưng token không hợp lệ

~~~http
Authorization: Bearer invalid.jwt.value
~~~

Filter tìm được chuỗi token và gọi `AuthenticationManager`. `JwtDecoder` không thể xác minh token, dẫn đến lỗi authentication. `BearerTokenAuthenticationFilter` xử lý lỗi bằng failure handler/entry point thích hợp; thông thường client nhận:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Thông tin chi tiết trong header có thể khác nhau theo tình huống và cấu hình. Không gửi token thật hoặc các claim nhạy cảm vào thông báo lỗi.

### 7.3. Token hợp lệ nhưng thiếu quyền

Giả sử token đã xác thực thành công, nhưng chỉ có `scope = profile`:

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer <VALID_TOKEN_WITHOUT_ORDERS_READ>
~~~

`BearerTokenAuthenticationFilter` tạo authentication thành công. Sau đó `AuthorizationFilter` từ chối quyền `SCOPE_orders.read`; thông thường client nhận **403 Forbidden**.

Nếu dùng Bearer access denied handler phù hợp, response có thể thể hiện `insufficient_scope`. Đừng tự diễn giải 403 thành “JWT hỏng”: token có thể hoàn toàn hợp lệ nhưng thiếu quyền.

### 7.4. Token hợp lệ và đủ scope

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer <VALID_TOKEN_WITH_ORDERS_READ>
~~~

Nếu chữ ký, issuer, audience, thời hạn và các validator đều đạt, authentication có `SCOPE_orders.read`, `AuthorizationFilter` cho phép request tiếp tục. Controller vẫn có thể từ chối nếu người dùng truy cập đơn hàng ngoài tenant của họ.

| Tình huống | Bearer filter | Authorization | Kết quả thường gặp |
|---|---|---|---|
| Không có token | Không tạo authenticated Bearer principal | Không đủ quyền | 401 |
| Token sai hoặc hết hạn | Xác thực thất bại | Thường chưa tới bước authorization | 401 |
| Token hợp lệ, thiếu scope | Xác thực thành công | Từ chối | 403 |
| Token hợp lệ, đủ scope | Xác thực thành công | Cho phép | Controller xử lý; có thể 200 |
| Không có token, endpoint `permitAll` | Không tạo Bearer principal | Cho phép | Controller xử lý |
| Token sai, endpoint `permitAll` và có Bearer filter | Có thể xác thực rồi thất bại | Có thể chưa tới authorization | Thường 401 |

Hàng cuối thể hiện một chi tiết quan trọng: **`permitAll` không có nghĩa BearerTokenAuthenticationFilter bị bỏ qua**. Filter có thể thấy token không hợp lệ và trả lỗi trước khi authorization cho phép endpoint công khai.

## 8. Nhiều `SecurityFilterChain`: chọn chain trước, rồi mới xét quyền

Một ứng dụng có thể có API xác thực Bearer JWT và một số endpoint khác không dùng Bearer.

### 8.1. Ví dụ hai chain với `@Order`

~~~java
package com.example.orders.security;

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
public class MultiChainSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain remainingRequests(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .anyRequest().denyAll()
            );

        return http.build();
    }
}
~~~

**Diễn giải:**

- Request `GET /api/orders` khớp `/api/**` → chain thứ nhất được chọn → Bearer token được xử lý.
- Request `GET /actuator/health` không khớp chain API → đi vào chain thứ hai → endpoint được phép truy cập.
- Request `GET /admin` không khớp API chain → đi vào chain thứ hai → `denyAll`.
- Chain thứ hai không bật Resource Server JWT, nên nó **không có cơ chế xử lý Bearer token do cấu hình `oauth2ResourceServer().jwt()` của chain đầu tiên**.
- `@Order(1)` và `@Order(2)` điều khiển **thứ tự chọn chain**, không phải thứ tự chạy từng filter bên trong chain.

Việc cấu hình chain dự phòng hạn chế nguy cơ quên bảo vệ các đường dẫn không khớp chain cụ thể. Nếu một request **không khớp bất kỳ SecurityFilterChain nào**, các bảo vệ do Spring Security filter chain cung cấp không áp dụng cho request đó.

### 8.2. `securityMatcher` khác `requestMatchers` thế nào?

Xét cấu hình:

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public/**").permitAll()
        .requestMatchers("/api/admin/**").hasAuthority("SCOPE_admin")
        .anyRequest().authenticated()
    )
    .oauth2ResourceServer(oauth2 -> oauth2
        .jwt(Customizer.withDefaults())
    );
~~~

- `securityMatcher("/api/**")`: **FilterChainProxy chọn chain này cho request nào?**
- `requestMatchers("/api/public/**").permitAll()`: **sau khi chain đã được chọn, endpoint nào được cho phép mà không cần quyền?**
- `requestMatchers("/api/admin/**")`: **quy tắc quyền áp dụng cho endpoint cụ thể trong chain**.

Do `/api/public/**` vẫn nằm trong API chain, **BearerTokenAuthenticationFilter vẫn có thể chạy**. Nếu một client gửi Bearer token sai định dạng tới endpoint công khai, nó có thể bị từ chối dù authorization policy của endpoint là `permitAll`.

Ngược lại, nếu `securityMatcher` quá hẹp và không bao gồm endpoint cần bảo vệ, Spring Security không thể sửa vấn đề đó bằng cách thêm `requestMatchers` vào cùng chain: request chưa từng chọn chain đó.

### 8.3. First-match-wins và trùng matcher

Ví dụ cấu hình sai về ý định:

~~~java
// Chain ưu tiên cao hơn
http.securityMatcher("/**");

// Chain ưu tiên thấp hơn
http.securityMatcher("/api/**");
~~~

Nếu cả hai tồn tại, chain `/**` ưu tiên cao sẽ bắt mọi request, làm chain `/api/**` phía sau không được chọn. Kết quả có thể là API không chạy Bearer token filter nếu chain tổng quát không bật Resource Server.

Khi dùng nhiều chain:

1. Đặt matcher đặc thù trước matcher tổng quát.
2. Ràng buộc rõ `@Order`.
3. Đảm bảo không có endpoint quan trọng ngoài phạm vi bảo vệ.
4. Tránh hai chain có matcher chồng lấn mà không chủ đích.
5. Phân biệt quy tắc endpoint và quy tắc chọn chain khi phân tích 401/403.

## 9. Bearer token ở chain nào khi cùng ứng dụng có OIDC Login?

Một ứng dụng có thể vừa:

- Là **OAuth 2.0/OIDC Client** dùng `oauth2Login()` để đăng nhập người dùng qua browser, thường có session.
- Là **Resource Server** dùng `oauth2ResourceServer()` để nhận access token từ các API client.

Hai vai trò này khác nhau.

| Thành phần | Chức năng |
|---|---|
| `oauth2Login()` | Redirect người dùng đến Identity Provider, xử lý callback/authorization code, tạo session đăng nhập ở client |
| `oauth2Client()` | Quản lý OAuth2AuthorizedClient và access token để ứng dụng đi gọi API khác |
| `oauth2ResourceServer().jwt()` | Tiếp nhận Bearer access token, xác minh JWT |
| `oauth2ResourceServer().opaqueToken()` | Tiếp nhận Bearer opaque access token, xác minh qua introspection |

Khi kết hợp, cần thiết kế filter chain cho API và web phù hợp. Nếu request API nhầm vào chain form/OIDC login, client có thể nhận redirect `302` đến trang đăng nhập thay vì Bearer `401` như mong đợi. Nếu trang web nhầm vào chain API stateless, phiên đăng nhập bằng cookie có thể không hoạt động như dự định.

**ID Token OIDC không phải Bearer access token của Resource Server.** API phải kiểm tra access token được phát hành cho audience của chính nó; không chấp nhận ID Token chỉ vì cả hai có JWT header/payload/signature.

## 10. Tùy chỉnh nơi lấy Bearer token trong chain

Nếu hợp đồng giữa client/gateway và API yêu cầu:

~~~http
X-Access-Token: Bearer <ACCESS_TOKEN>
~~~

có thể cấu hình resolver trong chain Resource Server:

~~~java
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;

DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();
resolver.setBearerTokenHeaderName("X-Access-Token");

http.oauth2ResourceServer(oauth2 -> oauth2
    .bearerTokenResolver(resolver)
    .jwt(Customizer.withDefaults())
);
~~~

Lúc này `BearerTokenAuthenticationFilter` dùng resolver đã cấu hình để tìm token ở `X-Access-Token`.

**`setBearerTokenHeaderName` chỉ thay tên header**, giá trị vẫn phải mang scheme `Bearer `. Một chuỗi JWT thô trong header riêng là hợp đồng khác và cần resolver phù hợp nếu có yêu cầu thật.

Không tự tạo một filter mới để đọc header rồi parse JWT trong controller chỉ vì tên header thay đổi. Cấu hình `BearerTokenResolver` giúp giữ nguyên pipeline xác thực, error handling và authorization của Spring Security.

Nếu backend đứng sau gateway, cần thống nhất header mà gateway chuyển tiếp; gateway không nên để client giả mạo các header chỉ dành cho mạng nội bộ. Đổi tên header không tự mang lại bảo mật.

## 11. CORS, CSRF và thứ tự filter đối với API

### 11.1. CORS preflight

Với frontend chạy ở origin khác, browser có thể gửi **CORS preflight** trước request có header `Authorization`:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://shop.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

Preflight thường **không có Bearer token**. Vì thế ứng dụng phải cấu hình CORS đúng cách để preflight được xử lý trước lớp xác thực yêu cầu token. Spring Security hỗ trợ tích hợp CORS qua:

~~~java
http.cors(Customizer.withDefaults());
~~~

Cần cung cấp cấu hình CORS thích hợp (ví dụ `CorsConfigurationSource`) theo các origin, method và header được phép. Việc cho phép `Authorization` trong CORS **không xác thực Bearer token**; request thật vẫn phải đi qua Resource Server authentication/authorization.

Không vô hiệu hóa toàn bộ security chỉ để preflight chạy. Hãy xử lý CORS theo cơ chế phù hợp với Servlet filter chain.

### 11.2. CSRF và Bearer stateless

API thuần Bearer token được client chủ động đặt trong header `Authorization` thường không phụ thuộc vào browser cookie để tự động gửi credential. Trong trường hợp này, việc tắt CSRF cho **API chain đó** có thể phù hợp.

Tuy nhiên, nếu cùng app còn dùng form login/cookie session, **không tắt CSRF toàn cục** mà không đánh giá từng chain. Dùng `securityMatcher` để giới hạn chính sách CSRF theo nhóm endpoint.

### 11.3. Security headers và request cache

Resource Server vẫn có thể nhận security response headers từ filter liên quan. `RequestCacheAwareFilter` hoặc những filter hỗ trợ khác có thể xuất hiện trong chain tùy cấu hình. Với API stateless, không nên để hệ thống chuyển sang form-login redirect hoặc lưu request trong session do vô tình trộn cấu hình web và API.

## 12. Lỗi 401/403 đi qua filter nào?

Hai thành phần thường cần hiểu:

- **`BearerTokenAuthenticationFilter`** xử lý lỗi ngay trong quá trình xác thực Bearer token. Khi token được cung cấp nhưng không hợp lệ, failure handler/entry point có thể trả về **401**.
- **`ExceptionTranslationFilter`** nằm trong chuỗi để chuyển những exception về authentication/authorization từ các filter **phía sau nó** (thường bao gồm quyết định tại `AuthorizationFilter`) thành phản hồi theo entry point hoặc access denied handler thích hợp.

Vì vậy, không nên nói mọi 401 Bearer đều do `ExceptionTranslationFilter` bắt. Một số lỗi xác thực bị xử lý trực tiếp ở `BearerTokenAuthenticationFilter`.

Thông thường:

| Vấn đề | Giai đoạn phát hiện | HTTP thường gặp |
|---|---|---|
| Header Bearer sai cú pháp | Resolver/Bearer filter | 401 hoặc response tương ứng lỗi Bearer |
| JWT signature không đúng | JwtDecoder trong AuthenticationProvider | 401 |
| Token hết hạn, sai issuer/audience | JwtDecoder/validator | 401 |
| Không có token cho endpoint bắt buộc | Authorization, anonymous/entry point | 401 |
| Token hợp lệ nhưng thiếu scope | AuthorizationFilter/AccessDeniedHandler | 403 |
| Token hợp lệ, policy cho phép | AuthorizationFilter | Controller xử lý |
| Controller tự từ chối quyền sở hữu dữ liệu | Tầng nghiệp vụ | 403 hoặc 404 theo API policy |

Response theo RFC 6750 có thể dùng header:

~~~http
WWW-Authenticate: Bearer
~~~

hoặc với token không hợp lệ:

~~~http
WWW-Authenticate: Bearer error="invalid_token"
~~~

Với token hợp lệ nhưng thiếu quyền, header có thể dùng `insufficient_scope` tùy handler. Chi tiết phản hồi phụ thuộc cấu hình Resource Server.

## 13. Vì sao không nên đăng ký Bearer filter thủ công?

Khi viết:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(Customizer.withDefaults())
);
~~~

Spring Security tự bổ sung các thành phần tương ứng vào security chain, gồm cơ chế trích token và xác thực JWT.

Một cấu hình dễ gây rắc rối là tự tạo `BearerTokenAuthenticationFilter` như một Servlet Filter độc lập rồi đồng thời bật `oauth2ResourceServer`. Khi đó có thể xảy ra:

- Filter chạy ngoài `FilterChainProxy` hoặc chạy hai lần.
- Thứ tự so với `SecurityContextHolderFilter`/`AuthorizationFilter` không đúng.
- Tạo AuthenticationManager/decoder khác với chain của Resource Server.
- Xử lý lỗi 401/403 không thống nhất.
- Cùng một request có hai cơ chế xử lý token chồng lấn.

Chỉ dùng `addFilterBefore`/`addFilterAfter` cho **custom filter có mục đích riêng**, xác định rõ filter mốc, threat model và tương tác với authentication context. Không thêm filter tùy chỉnh chỉ để đổi header Bearer hoặc kiểm tra một claim vốn có thể dùng `JwtDecoder`/`OAuth2TokenValidator`.

Tương tự, `@Order` trên `SecurityFilterChain` **không điều chỉnh vị trí của `BearerTokenAuthenticationFilter` trong chain**. Thứ tự từng filter do các cấu hình bảo mật và bộ máy sắp xếp filter của Spring Security đảm nhiệm.

## 14. Khi dùng opaque access token, vị trí Bearer filter có khác không?

Về vị trí HTTP, **không**: Resource Server vẫn cần tìm Bearer token từ request. Khác biệt nằm trong bước xác thực.

Cấu hình:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(Customizer.withDefaults())
);
~~~

Ví dụ `application.yml` với Authorization Server có introspection endpoint:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://id.example.test/oauth2/introspect
          client-id: orders-api
          client-secret: example-from-secret-store
~~~

Các giá trị là placeholder minh họa. Secret thật phải lấy từ môi trường hoặc secret manager, không lưu vào repository. Endpoint introspection và thông tin client phụ thuộc provider.

Luồng:

~~~text
BearerTokenAuthenticationFilter
    |
    v
BearerTokenAuthenticationToken
    |
    v
OpaqueTokenAuthenticationProvider
    |
    v
OpaqueTokenIntrospector -> Authorization Server
    |
    v
BearerTokenAuthentication
    |
    v
AuthorizationFilter
~~~

JWT decoder có thể kiểm tra token bằng public key tại API; introspection thường cần gọi đến Authorization Server theo chính sách cache/mạng. Hai cách này không thay đổi nhiệm vụ chọn `SecurityFilterChain` và kiểm soát quyền sau authentication.

## 15. Chẩn đoán vấn đề thực tế

### 15.1. Có token nhưng API vẫn trả 401

Xem những nguyên nhân theo đúng giai đoạn:

1. Request có đi vào **chain bật Resource Server** không? Kiểm tra `securityMatcher` và `@Order`.
2. Bearer filter có đọc đúng header `Authorization` hoặc header riêng đã cấu hình không?
3. Header có dạng `Bearer <token>` không?
4. Decoder có dùng đúng issuer, JWKS, thuật toán JWT hoặc introspection endpoint không?
5. Access token có còn hạn, đúng audience và profile yêu cầu không?

Đừng sửa lỗi 401 bằng cách thêm `permitAll` cho endpoint cần bảo vệ: nếu token xác thực không thành công, việc giảm quyền truy cập của endpoint chỉ che lấp vấn đề.

### 15.2. API trả 302 redirect đến login

Trường hợp thường thấy khi request API đi vào filter chain phục vụ browser login, hoặc authentication entry point khác với Bearer Resource Server. Kiểm tra chain được chọn, matcher và cơ chế authentication trong chain.

API dùng Bearer access token thường cần phản hồi 401/403 phù hợp để client xử lý, thay vì redirect đến trang login web.

### 15.3. Có token đúng nhưng trả 403

Token có thể đã xác thực nhưng thiếu authority. Kiểm tra:

- Scope trong token và mapping thành `SCOPE_...`.
- `requestMatchers` đang áp dụng rule nào.
- Có role-based policy khác không.
- Có ràng buộc tenant hoặc ownership ở tầng nghiệp vụ không.

`403` không đồng nghĩa Bearer filter không chạy; nó thường cho thấy authentication đã có nhưng quyền chưa đủ.

### 15.4. Endpoint `permitAll` vẫn trả 401 khi gửi token sai

Vì `permitAll` chỉ là **authorization policy**, còn Resource Server filter vẫn xử lý Bearer token nếu request nằm trong chain. Khi client cố gửi một token sai, lỗi authentication có thể xảy ra **trước** authorization.

Nếu muốn một endpoint thực sự không có Bearer processing, cần thiết kế ranh giới chain theo đường dẫn và policy rõ ràng, chứ không kỳ vọng `permitAll` sẽ tự bỏ qua filter.

### 15.5. Một chain “nuốt” các request của chain khác

Nếu chain đầu có `securityMatcher("/**")`, mọi request có thể khớp ngay chain đó. `FilterChainProxy` không thử các chain sau nếu chain đầu đã khớp.

Hãy kiểm tra matcher đặc thù, thứ tự `@Order` và có một chain dự phòng bảo vệ những route còn lại.

### 15.6. Controller không thấy Authentication mong đợi

Có thể request không đi qua đúng chain, Bearer token không được gửi, hoặc authentication đã thất bại trước controller. Với JWT và opaque token, loại principal khác nhau; không ép mọi principal thành `Jwt`.

Không lưu `SecurityContextHolder.getContext()` thành biến dùng chung giữa nhiều request hoặc thread. Hãy đọc trong request hiện tại hoặc dùng injection.

## 16. Quan sát filter chain khi phát triển

### 16.1. Bật log bảo mật có kiểm soát

Trong môi trường local/dev, có thể bật:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
~~~

Tùy phiên bản, log có thể hiển thị chain đang bảo vệ request và danh sách filter được cấu hình. `TRACE` có thể chi tiết hơn nhưng cũng nhiều log hơn.

**Không bật log chi tiết lâu dài ở production** khi chưa đánh giá rủi ro lộ thông tin. Tránh ghi nguyên access token, Authorization header, cookies, private key hoặc dữ liệu nhạy cảm vào log và telemetry.

### 16.2. Phân biệt kiểm thử authorization và kiểm thử cả Bearer flow

Trong Spring Security Test, một request MockMvc sử dụng `jwt()`:

~~~java
mockMvc.perform(
    get("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        ))
);
~~~

Đây là kỹ thuật tiện lợi để **mô phỏng authentication** khi kiểm tra rule endpoint. Nó **không nhất thiết kiểm tra đầy đủ việc trích chuỗi Bearer từ HTTP header, xác minh chữ ký và các validator của JwtDecoder**.

Để kiểm tra toàn bộ Bearer pipeline, cần một bài kiểm thử tích hợp có security filters thực sự, access token test được ký hợp lệ, nguồn JWKS/decoder kiểm soát được và các trường hợp sai chữ ký/issuer/audience/scope. Tương tự, nếu tùy chỉnh tên header, test riêng việc resolver lấy token đúng header.

### 16.3. Gợi ý ma trận request

| Request | Chain kỳ vọng | Kết quả mong đợi |
|---|---|---|
| `GET /api/orders` không token | API chain | 401 |
| `GET /api/orders` token sai | API chain | 401 |
| `GET /api/orders` token hợp lệ thiếu scope | API chain | 403 |
| `GET /api/orders` token hợp lệ đủ scope | API chain | Controller xử lý |
| `GET /actuator/health` không token | Fallback chain trong ví dụ hai chain | Cho phép |
| `GET /admin` | Fallback chain | Từ chối |
| `GET /api/public/ping` token sai, endpoint `permitAll` trong API chain | API chain | Có thể 401 do Bearer authentication thất bại |

Mục tiêu của ma trận là phân biệt **lỗi chọn chain**, **lỗi xác thực token** và **lỗi phân quyền**.

## 17. Trình tự suy luận cho một endpoint mới

Khi thêm `GET /api/reports` vào ứng dụng Resource Server, nên trả lời theo thứ tự:

1. **Endpoint thuộc SecurityFilterChain nào?** Ví dụ `/api/**`.
2. **Chain có bật Bearer Resource Server không?** Ví dụ `oauth2ResourceServer().jwt()`.
3. **Bearer token đến từ đâu?** Header `Authorization` mặc định hay header theo hợp đồng.
4. **Token được xác thực bằng gì?** JWT Decoder hay opaque introspection, issuer/key/alg/audience nào.
5. **Authority nào đại diện quyền truy cập?** Ví dụ `SCOPE_reports.read`.
6. **Bản ghi nào caller được xem?** Kiểm tra tenant/owner và chính sách ứng dụng.
7. **Khi thất bại, client nên thấy gì?** Token sai hoặc thiếu: 401; đã xác thực nhưng không đủ quyền: 403 (hoặc 404 theo chính sách đối tượng).

Đi theo thứ tự này giúp tránh đặt logic đọc JWT trong controller, trùng filter, cấu hình matcher sai hoặc nhầm quyền API với đăng nhập OIDC.

## 18. Ghi nhớ

- **`DelegatingFilterProxy`** nối Servlet container với Spring Security; **`FilterChainProxy`** chọn **`SecurityFilterChain`** theo request.
- **Chain đầu tiên khớp request** được dùng; `@Order` sắp xếp ưu tiên giữa các chain.
- **`securityMatcher`** xác định phạm vi chain, còn **`requestMatchers`** trong `authorizeHttpRequests` định nghĩa quyền bên trong chain.
- **`oauth2ResourceServer(...jwt(...))`** thêm cơ chế xử lý JWT Bearer; **`BearerTokenAuthenticationFilter`** tìm token, tạo authentication request và gọi cơ chế xác thực.
- Sau khi xác thực thành công, **`Authentication`** có trong **`SecurityContext`** để **`AuthorizationFilter`** và code ứng dụng sử dụng.
- **`permitAll` không tự bỏ qua Bearer filter**; token sai trên endpoint công khai trong cùng chain vẫn có thể bị từ chối.
- **401** thường là không có xác thực hợp lệ; **403** thường là đã xác thực nhưng không đủ quyền.
- Không tạo Bearer filter thủ công khi chỉ cần cấu hình JWT Resource Server, đổi header hoặc kiểm tra claims; dùng các extension point chính thức của Spring Security.

### Tài liệu tham khảo

- [Spring Security Reference — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security Reference — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security Reference — OAuth 2.0 Resource Server Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html)
- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security API — BearerTokenAuthenticationFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/authentication/BearerTokenAuthenticationFilter.html)
- [Spring Security API — FilterChainProxy](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/FilterChainProxy.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)

