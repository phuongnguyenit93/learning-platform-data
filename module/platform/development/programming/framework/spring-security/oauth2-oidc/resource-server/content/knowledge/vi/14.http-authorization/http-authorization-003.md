# Endpoint công khai, endpoint cần xác thực và endpoint cần quyền cụ thể

Trong **Spring Security OAuth 2.0/OIDC Resource Server**, một API thường không có cùng mức bảo vệ cho tất cả endpoint. Ví dụ:

- `GET /api/public/catalog` có thể được xem mà **không cần đăng nhập**.
- `GET /api/me` cần một **access token hợp lệ**, nhưng không yêu cầu scope nghiệp vụ riêng.
- `GET /api/orders` cần token hợp lệ **và** scope `orders.read`.
- `POST /api/orders` cần token hợp lệ **và** scope `orders.write`.
- `GET /api/orders/{id}` có thể còn phải kiểm tra **quyền trên đơn hàng cụ thể**.

Spring Security dùng `SecurityFilterChain`, `authorizeHttpRequests` và các `RequestMatcher` để mô tả những quy tắc này tại tầng HTTP. Hiểu đúng sự khác nhau giữa **`permitAll()`**, **`authenticated()`** và **`hasAuthority(...)`** giúp Resource Server chỉ yêu cầu mức bảo vệ cần thiết, đồng thời tránh vô tình mở quyền trên các endpoint mới.

> **Nguyên tắc:** endpoint công khai không yêu cầu xác thực; endpoint cần xác thực yêu cầu một principal được xác thực hợp lệ; endpoint cần quyền cụ thể yêu cầu principal đó có đúng authority mà chính sách quy định. Quyền ở tầng endpoint **không thay thế** kiểm tra tenant, ownership và quyền trên từng tài nguyên.

Bài học sử dụng Java, Spring Boot, Spring Security Servlet/Spring MVC và JWT bearer access token. Với opaque token hoặc WebFlux, mô hình phân quyền tương tự nhưng thành phần xác thực và API cấu hình có thể khác.

## 1. Phân loại endpoint theo mục tiêu bảo vệ

| Loại endpoint | Cấu hình phổ biến | Điều kiện để qua tầng HTTP authorization | Ví dụ |
|---|---|---|---|
| **Công khai** | `permitAll()` | Không cần `Authentication` đã xác thực | Health check công khai, trang giới thiệu, catalog public |
| **Cần xác thực** | `authenticated()` | Có authentication hợp lệ, không chỉ anonymous | Hồ sơ của chính người gọi |
| **Cần quyền cụ thể** | `hasAuthority("SCOPE_orders.read")` | Có authentication với authority đúng | Đọc dữ liệu đơn hàng |
| **Cần một trong nhiều quyền** | `hasAnyAuthority(...)` | Có ít nhất một authority được nêu | Nhân viên hỗ trợ hoặc người vận hành |
| **Cần role ứng dụng** | `hasRole("ADMIN")` | Có role theo quy ước prefix, thông thường `ROLE_ADMIN` | Bảng điều khiển quản trị |
| **Luôn từ chối** | `denyAll()` | Không cho phép request | Route chưa khai báo hoặc chức năng bị đóng |

Cả sáu loại rule đều thuộc **authorization**. Chúng không quyết định JWT nào được tin; việc xác thực bearer token diễn ra ở các thành phần Resource Server.

### 1.1. Xác thực khác phân quyền

Giả sử Resource Server nhận một access token JWT:

~~~json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "customer-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 2000000300
}
~~~

Một `JwtDecoder` được cấu hình đúng sẽ kiểm tra chữ ký, issuer, thời hạn và audience theo contract. Sau đó Spring Security có thể tạo `Authentication` với authority:

~~~text
SCOPE_orders.read
~~~

Các câu hỏi tiếp theo là **khác nhau**:

- Token hợp lệ không? → authentication/validation.
- Request có yêu cầu phải có token không? → `authenticated()` hoặc rule cao hơn.
- Request có quyền `orders.read` không? → `hasAuthority("SCOPE_orders.read")`.
- Đơn hàng được yêu cầu có thuộc customer 42 không? → service/object-level authorization.

**Token hợp lệ không đồng nghĩa mọi endpoint đều được phép gọi.**

## 2. Luồng request trong Spring Security Resource Server

~~~text
HTTP request
     |
     v
Spring Security FilterChainProxy
     |
     v
SecurityFilterChain phù hợp với request
     |
     +-- CORS / CSRF / security context / các filter khác
     |
     +-- BearerTokenAuthenticationFilter (khi chain bật Resource Server)
     |       |
     |       +-- Không có bearer token: có thể tiếp tục dưới dạng unauthenticated
     |       |
     |       +-- Có bearer token: xác minh JWT/introspection
     |               |
     |               +-- Sai -> authentication failure
     |               +-- Đúng -> tạo Authentication
     |
     v
AuthorizationFilter
     |
     +-- RequestMatcher khớp rule nào?
     |
     +-- permitAll / authenticated / hasAuthority / denyAll
     |
     v
Controller -> service-level authorization -> data access
~~~

Sơ đồ khái quát này giúp thấy hai vấn đề:

1. **`permitAll()` là một quy tắc ở tầng authorization**, không có nghĩa Spring Security bỏ qua toàn bộ filter chain.
2. **`hasAuthority(...)` chỉ có ý nghĩa khi authorities đến từ quá trình authentication/authorization có nguồn tin cậy**, chứ không từ tham số request do client tự gửi.

Trong Spring Security hiện đại, `authorizeHttpRequests` sử dụng hạ tầng authorization dựa trên `AuthorizationManager`, với `AuthorizationFilter` thực thi quyết định tại request boundary.

## 3. Tạo Resource Server mẫu

Ví dụ ứng dụng có các endpoint sau:

| HTTP method | Endpoint | Ý định |
|---|---|---|
| `GET` | `/api/public/catalog` | Bất kỳ ai cũng xem được |
| `GET` | `/api/me` | Bất kỳ principal hợp lệ nào cũng xem hồ sơ của chính mình |
| `GET` | `/api/orders` | Cần `orders.read` |
| `GET` | `/api/orders/{id}` | Cần `orders.read` và quyền trên order |
| `POST` | `/api/orders` | Cần `orders.write` |
| `PUT` | `/api/orders/{id}` | Cần `orders.write` |
| `DELETE` | `/api/orders/{id}` | Cần `orders.delete` |
| `GET` | `/actuator/health` | Có thể công khai nếu chính sách vận hành cho phép |
| Phương thức/đường dẫn khác | `/api/**` | Không cấp quyền ngầm |

### 3.1. Gradle dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Spring Boot quản lý version của các dependency qua dependency management/BOM theo project. Starter Resource Server cung cấp cơ chế xử lý bearer access token và JWT khi dùng `jwt()`.

### 3.2. application.yml

Giả sử issuer đáng tin và audience của API là:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          audiences:
            - orders-api
~~~

- `issuer-uri` xác định Authorization Server mà Resource Server tin, và phải khớp claim `iss` trong JWT.
- `audiences` kiểm tra token dành cho `orders-api`. Thuộc tính này được hỗ trợ trong các phiên bản Spring Boot hiện đại; với version khác phải tự cấu hình audience validator.
- `jwt()` không biến ID token của OIDC thành access token phù hợp cho API. Cần đúng token type, issuer và audience theo hợp đồng.

Chỉ có YAML chưa quyết định endpoint nào công khai. Việc phân quyền được định nghĩa ở `SecurityFilterChain`.

## 4. Cấu hình đầy đủ ba mức bảo vệ

`SecurityConfig.java`:

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
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            // Chỉ phù hợp cho API stateless dùng bearer header,
            // không dùng cookie tự động gửi để xác thực request.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                // 1. Public
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/public/**")
                    .permitAll()

                // 2. Chỉ cần token hợp lệ
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()

                // 3. Cần scope cụ thể
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers(HttpMethod.PUT, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers(HttpMethod.DELETE, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.delete")

                // Mặc định an toàn: route chưa được khai báo không được mở.
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

### Giả định quan trọng của ví dụ

Ví dụ giả định một **REST API stateless**, client gửi bearer access token bằng `Authorization` header, **không** sử dụng session cookie/HTTP Basic/form login làm kênh xác thực cho các request thay đổi dữ liệu.

Vì vậy `csrf(AbstractHttpConfigurer::disable)` là một lựa chọn dựa trên kiến trúc đó, **không phải quy tắc chung cho mọi ứng dụng Spring**. Nếu API chấp nhận cookie tự động gửi từ browser, phải đánh giá CSRF và giữ/thiết kế cơ chế phòng vệ phù hợp.

Trong kiến trúc có CORS browser SPA, cần thêm `cors(...)` và cấu hình nguồn CORS hợp lệ như phần sau; một rule `permitAll` đơn lẻ không tự giải quyết CORS.

Các đường dẫn controller phải phù hợp với matcher. `/actuator/health` chỉ tồn tại nếu ứng dụng có Actuator và exposure tương ứng. Nếu Actuator chạy ở management port riêng, có thể có security context khác.

### Ý nghĩa toàn bộ policy

~~~text
GET  /api/public/catalog --> permitAll
GET  /api/me             --> authenticated
GET  /api/orders         --> SCOPE_orders.read
POST /api/orders         --> SCOPE_orders.write
PUT  /api/orders/123     --> SCOPE_orders.write
DELETE /api/orders/123   --> SCOPE_orders.delete
GET  /api/unknown        --> denyAll
~~~

Việc đặt `anyRequest().denyAll()` ở cuối tạo chiến lược **fail closed**: endpoint mới không được mở chỉ vì lập trình viên quên bổ sung rule.

## 5. Endpoint công khai: `permitAll()`

Khi một endpoint có rule:

~~~java
.requestMatchers(HttpMethod.GET, "/api/public/**")
    .permitAll()
~~~

điều đó nghĩa là **không yêu cầu quyền/xác thực để thông qua rule HTTP authorization**. Người dùng chưa đăng nhập có thể truy cập. Đây là lựa chọn phù hợp cho:

- Catalog hoặc thông tin vốn được công bố rộng rãi.
- Endpoint giới thiệu, tài liệu công khai.
- Health endpoint chỉ tiết lộ trạng thái tối thiểu, nếu vận hành cho phép.
- Một số callback/public endpoint được thiết kế riêng và có cơ chế xác thực độc lập theo protocol (nếu cần).

### 5.1. `permitAll` không giống “bỏ qua Spring Security”

Khi request đi qua `SecurityFilterChain`, các filter bảo mật vẫn có thể thực hiện xử lý như security headers, CORS, JWT authentication, CSRF hoặc exception handling tùy cấu hình.

Ví dụ:

~~~http
GET /api/public/catalog HTTP/1.1
Host: api.example.com
~~~

không có token, rule `permitAll` có thể cho qua.

Nhưng với:

~~~http
GET /api/public/catalog HTTP/1.1
Host: api.example.com
Authorization: Bearer invalid-or-expired-token
~~~

một Resource Server chain có `BearerTokenAuthenticationFilter` có thể **trả 401 trước khi request tới `permitAll`**, do client đã chủ động gửi bearer token không hợp lệ. `permitAll` không buộc authentication filter bỏ qua token được gửi.

Vì vậy, để kiểm tra endpoint public, thử request **không có Authorization header**; một client HTTP tự động gắn token hết hạn vào mọi request có thể khiến người dùng tưởng endpoint không public.

### 5.2. Nên ưu tiên `permitAll` hơn `web.ignoring()`

Spring Security khuyến nghị dùng `permitAll` cho các tài nguyên public thay vì bỏ qua toàn bộ filter chain bằng `web.ignoring()`, vì những request bị ignore không nhận các security headers hoặc hành vi bảo vệ do filter chain cung cấp.

~~~java
// Thường phù hợp: vẫn đi qua security filter chain
.requestMatchers("/assets/**").permitAll()
~~~

Điều này không có nghĩa tài nguyên public phải có JWT; nó chỉ cho phép chúng tiếp tục được phục vụ **trong cấu trúc bảo mật thống nhất**.

### 5.3. Public endpoint vẫn cần bảo vệ dữ liệu và hạ tầng

`permitAll` chỉ nói **không cần authentication**. Nó không tự bảo vệ khỏi:

- Lộ dữ liệu cá nhân nếu controller trả dữ liệu không phù hợp để công khai.
- Rate limiting, scraping hoặc bot abuse.
- Input validation/SQL injection.
- Thông tin nhạy cảm trong health/info/metrics.
- Việc public endpoint làm thay đổi trạng thái ngoài ý muốn.

Không dùng `permitAll` cho endpoint chứa dữ liệu riêng tư chỉ vì front-end chưa triển khai đăng nhập. Mức công khai phải là quyết định sản phẩm và bảo mật được phê duyệt.

## 6. Endpoint cần xác thực: `authenticated()`

Rule:

~~~java
.requestMatchers(HttpMethod.GET, "/api/me")
    .authenticated()
~~~

yêu cầu người gọi có một **`Authentication` hợp lệ** theo cơ chế của filter chain. Trong JWT Resource Server, điều đó thường là bearer access token có chữ ký/issuer/audience/thời hạn hợp lệ.

Ví dụ:

~~~http
GET /api/me HTTP/1.1
Host: api.example.com
Authorization: Bearer <valid-access-token>
~~~

`authenticated()` **không bắt buộc** token có scope `orders.read`, `orders.write` hoặc role `ADMIN`. Nó chỉ đặt ngưỡng xác thực.

### 6.1. Khi nào chỉ yêu cầu xác thực là đủ?

Có thể phù hợp cho:

- Xem thông tin cơ bản của **chính principal** đang gọi.
- Kiểm tra trạng thái session/token đã xác thực ở một API được thiết kế như vậy.
- Endpoint không làm thay đổi dữ liệu của người khác và không yêu cầu entitlement riêng.
- Chức năng mà chính sách nghiệp vụ xác định mọi principal hợp lệ của API đều có quyền sử dụng.

Nhưng cần lưu ý: **“mọi principal hợp lệ”** trong Resource Server có thể bao gồm **machine client** hoặc các loại subject khác, tùy token profile. Nếu `/api/me` chỉ có ý nghĩa với human user, phải áp dụng policy về token/client type hoặc principal model phù hợp; đừng coi `authenticated()` tự phân biệt user với service account.

### 6.2. Xác thực không bảo đảm chủ sở hữu tài nguyên

Nếu endpoint là:

~~~http
GET /api/profiles/user-42 HTTP/1.1
Authorization: Bearer <token-of-user-99>
~~~

chỉ có `authenticated()` chưa đủ để ngăn user 99 đọc hồ sơ của user 42. API cần kiểm tra subject hoặc quyền truy cập dữ liệu tương ứng.

Một endpoint `GET /api/me` thường an toàn hơn về thiết kế khi lấy subject từ `SecurityContext` chứ không nhận user ID tùy ý do client truyền vào.

### 6.3. `authenticated()` và anonymous principal

Spring Security có thể tạo `AnonymousAuthenticationToken` để biểu diễn request chưa đăng nhập trong một số flow. Tuy tên class có chứa “Authentication”, rule `authenticated()` sử dụng cơ chế nhận biết anonymous và **không coi anonymous là một người dùng đã được xác thực hợp lệ**.

Không viết code chỉ kiểm tra `SecurityContextHolder.getContext().getAuthentication() != null` rồi suy ra người dùng đã đăng nhập.

## 7. Endpoint cần quyền cụ thể: `hasAuthority(...)`

Một access token JWT có thể chứa:

~~~json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "customer-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 2000000300
}
~~~

Khi token đã được xác minh, Spring Security thường chuyển `scope=orders.read` thành authority:

~~~text
SCOPE_orders.read
~~~

Để bảo vệ việc đọc đơn hàng:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

Để bảo vệ việc tạo hoặc sửa đơn hàng:

~~~java
.requestMatchers(HttpMethod.POST, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")
.requestMatchers(HttpMethod.PUT, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")
~~~

Token chỉ có `orders.read` **không** được ghi đơn hàng, dù đã đăng nhập và chữ ký hợp lệ.

### 7.1. `hasAuthority` so sánh chuỗi authority thực tế

`hasAuthority("SCOPE_orders.read")` kiểm tra authority có tên **`SCOPE_orders.read`**, không tự dịch một chuỗi khác thành quyền tương đương.

| JWT scope/authority sau mapping | Rule | Kết quả |
|---|---|---|
| `SCOPE_orders.read` | `hasAuthority("SCOPE_orders.read")` | Được qua rule |
| `SCOPE_orders.write` | `hasAuthority("SCOPE_orders.read")` | Bị từ chối |
| `ROLE_ORDERS_READER` | `hasAuthority("SCOPE_orders.read")` | Bị từ chối nếu không có scope read |
| `SCOPE_orders.read` và `SCOPE_orders.write` | `hasAuthority("SCOPE_orders.write")` | Được qua rule |
| Tập authority rỗng | `authenticated()` | Có thể qua nếu token được xác thực |
| Tập authority rỗng | `hasAuthority("SCOPE_orders.read")` | Bị từ chối |

**Không “sửa” lỗi 403 bằng cách tự bổ sung scope ở Resource Server** nếu Authorization Server chưa cấp scope đó. Cần kiểm tra OAuth authorization flow và quyền thực tế.

### 7.2. Một trong nhiều quyền: `hasAnyAuthority`

Ví dụ endpoint cho phép cả người vận hành và admin theo **role đã được cấp đáng tin**:

~~~java
.requestMatchers("/api/support/**")
    .hasAnyAuthority(
        "ROLE_SUPPORT_AGENT",
        "ROLE_SUPPORT_ADMIN"
    )
~~~

`hasAnyAuthority` là điều kiện **OR**. Chỉ một authority phù hợp là đủ. Cần bảo đảm các role/authority được cấp từ nguồn đáng tin, không tự suy ra từ email hoặc username.

Nếu một endpoint yêu cầu đồng thời nhiều quyền, có thể dùng các authorization manager phù hợp hoặc một policy tùy biến; không nhầm `hasAnyAuthority` là điều kiện AND.

### 7.3. `hasRole` là quy ước role, không phải scope

Trong cấu hình Spring Security phổ biến:

~~~java
.hasRole("ADMIN")
~~~

tương đương việc yêu cầu authority `ROLE_ADMIN` theo role prefix mặc định. Nó **khác**:

~~~java
.hasAuthority("SCOPE_admin")
~~~

JWT scope có `admin` không tự trở thành `ROLE_ADMIN` nếu không có mapping được phê duyệt.

Nếu AS có claim role tùy biến, phải cấu hình `JwtAuthenticationConverter` hoặc nguồn quyền phù hợp. Đây là một chính sách ánh xạ quyền, không chỉ thay tên chuỗi cho đẹp.

## 8. Thứ tự `requestMatchers` quyết định rule nào được áp dụng

Một trong những lỗi nguy hiểm nhất khi viết `authorizeHttpRequests` là đặt rule tổng quát trước rule cụ thể.

Spring Security xét các rule theo **thứ tự khai báo** trong một chain; khi request khớp một rule, hệ thống sử dụng quyết định của rule đó, không tiếp tục tìm rule “chặt hơn” ở phía sau.

### 8.1. Ví dụ sai: public rule bao phủ cả private route

~~~java
// SAI: rule public quá rộng đứng trước.
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
)
~~~

Request tới `/api/admin/users` đã khớp `/api/**` và được `permitAll` cho qua; rule `/api/admin/**` **không còn cơ hội bảo vệ**.

### 8.2. Sửa bằng quy tắc cụ thể trước

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/public/**").permitAll()
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
)
~~~

Thứ tự mới:

1. Admin route cần role.
2. Route public được mở cụ thể.
3. Những API còn lại cần xác thực.
4. Mọi route ngoài phạm vi được mô tả bị từ chối.

Đây là một cách tổ chức hợp lệ nếu nghiệp vụ thật sự cho phép **mọi API khác sau khi xác thực**. Nếu nhiều API cần scope riêng, nên khai báo trước rule yêu cầu scope, rồi dùng `denyAll()` thay vì một fallback `authenticated()` quá rộng.

### 8.3. Ví dụ sai: `authenticated` đặt trước `hasAuthority`

~~~java
// SAI nếu /api/orders chỉ được phép cho token có orders.read
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .requestMatchers("/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .anyRequest().denyAll()
)
~~~

Rule `/api/**` đã chặn việc tìm rule scope phía sau. Mọi token hợp lệ có thể vượt qua ranh giới HTTP cho `/api/orders/**`, kể cả khi thiếu `orders.read`.

**Kết luận:** thứ tự là một phần của chính sách phân quyền, không chỉ là cách trình bày code.

## 9. `securityMatcher` và `requestMatchers` không giống nhau

Trong ứng dụng có **nhiều `SecurityFilterChain`**, hai loại matcher có trách nhiệm khác nhau:

- **`securityMatcher(...)`:** quyết định **chain nào** áp dụng cho request.
- **`requestMatchers(...)` trong `authorizeHttpRequests`:** quyết định **rule authorization nào** áp dụng **bên trong chain đã được chọn**.

Ví dụ:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .requestMatchers("/api/me").authenticated()
            .anyRequest().hasAuthority("SCOPE_api.read"))
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}
~~~

Với `securityMatcher("/api/**")`, chain này **không tự xử lý `/actuator/health`** hoặc `/admin`. Những request không khớp sẽ được xem xét bởi chain tiếp theo nếu có.

### 9.1. Luôn có kế hoạch cho request không khớp chain nào

Một cấu hình nhiều chain có thể có fallback:

~~~java
@Bean
@Order(2)
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/actuator/health").permitAll()
            .anyRequest().denyAll())
        .build();
}
~~~

Hai snippet trên là **hai bean trong cùng class/configuration** và cần import `org.springframework.core.annotation.Order` cùng các import Spring Security tương ứng.

Khi có nhiều chain, `FilterChainProxy` chọn **chain khớp đầu tiên theo thứ tự**. Các rule authorization của các chain **không tự hợp nhất**.

Nguy cơ lớn: nếu chỉ tạo một chain có `securityMatcher("/api/**")` rồi không có chain nào bắt các đường dẫn ngoài `/api/**`, những request đó có thể **nằm ngoài sự bảo vệ của Spring Security filter chain**. Đây là vấn đề khác với `anyRequest().denyAll()` bên trong một chain.

### 9.2. Khi nào nên dùng nhiều chain?

Có thể dùng khi hệ thống có các khu vực bảo mật khác nhau:

- `/api/**` dùng OAuth2 JWT bearer và stateless session.
- `/admin-ui/**` dùng browser login/session/CSRF.
- `/actuator/**` có quy tắc vận hành và mạng riêng.

Tuy nhiên mỗi chain phải có:

1. `securityMatcher` đúng phạm vi.
2. Thứ tự `@Order` rõ ràng.
3. Authorization rules không bị matcher rộng che khuất.
4. Một kế hoạch fallback cho đường dẫn không thuộc chain dự kiến.
5. Test cho các đường dẫn nằm ở ranh giới giữa chains.

## 10. Kết hợp HTTP method với URL

Chỉ match đường dẫn mà bỏ HTTP method có thể làm rule quá rộng.

Ví dụ:

~~~java
.requestMatchers("/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

Nếu đặt như vậy, **POST, PUT, PATCH, DELETE** trên `/api/orders/**` cũng có thể chỉ cần scope đọc, nếu không có rule chặt hơn đứng trước. Đây có thể là lỗi phân quyền.

Khi ý nghĩa quyền phụ thuộc hành động HTTP, dùng `requestMatchers(HttpMethod, path)`:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")

.requestMatchers(HttpMethod.POST, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")

.requestMatchers(HttpMethod.PUT, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")

.requestMatchers(HttpMethod.PATCH, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")

.requestMatchers(HttpMethod.DELETE, "/api/orders/**")
    .hasAuthority("SCOPE_orders.delete")

.anyRequest().denyAll()
~~~

Dùng `anyRequest().denyAll()` giúp một HTTP method mới hoặc endpoint chưa được phê duyệt **không tự mặc định có quyền**.

### 10.1. Lưu ý `HEAD`, `OPTIONS` và preflight

HTTP có các method khác ngoài GET/POST/PUT/DELETE. Trên Spring MVC, xử lý `HEAD` có thể liên quan mapping GET; trong khi security rule chỉ match đúng `HttpMethod.GET` sẽ không tự đồng nghĩa bảo vệ mọi method khác.

Với `OPTIONS`, browser có thể gửi **CORS preflight** trước request có `Authorization` header. Cần cấu hình CORS đúng theo phần 14, không mở `OPTIONS /**` vô điều kiện chỉ để “cho frontend hết lỗi”.

Khi thiết kế policy, phải thống nhất cách xử lý tất cả HTTP method mà ứng dụng hoặc proxy có thể chuyển tới backend, gồm TRACE/HEAD/OPTIONS nếu liên quan.

### 10.2. Matcher phụ thuộc path thực tế và framework

Trong Spring MVC, cú pháp và lựa chọn matcher có thể khác theo context path, servlet path, library version và có/không có MVC trên classpath. Kiểm tra:

- Controller thực sự được đăng ký tại URL nào.
- Có context path hoặc servlet prefix không.
- Reverse proxy có rewrite path không.
- `/api/public/**` có vô tình chứa `/api/public/admin/**` không.
- Route có thể có trailing slash hoặc path variable khác không.
- Security matcher và Controller matcher có đồng bộ không.

Không dựa trên cảm giác “dấu `**` chắc bao phủ đúng tất cả trường hợp” khi một endpoint có hậu quả bảo mật cao. Viết test cho các đường dẫn cụ thể.

## 11. Chọn fallback: `authenticated()` hay `denyAll()`?

Hai cách cuối chain:

~~~java
.anyRequest().authenticated()
~~~

và:

~~~java
.anyRequest().denyAll()
~~~

có ý nghĩa khác nhau.

| Fallback | Khi endpoint mới xuất hiện nhưng chưa có rule riêng | Phù hợp khi |
|---|---|---|
| `authenticated()` | Bất kỳ principal hợp lệ có thể qua tầng HTTP | Chủ đích cho phép mọi endpoint còn lại với xác thực tối thiểu |
| `denyAll()` | Endpoint mới bị từ chối cho đến khi có rule rõ | API có nhiều scope hoặc yêu cầu duyệt chính sách trước khi mở |
| `permitAll()` | Endpoint mới mặc định công khai | Thường **không phù hợp** cho hệ thống chứa dữ liệu riêng tư |

**Khuyến nghị thực hành cho Resource Server có dữ liệu nghiệp vụ:** khai báo rõ public, authenticated và authority-specific endpoints rồi dùng `denyAll()` cho phần còn lại, trừ khi có lý do rõ để đặt authenticated fallback.

Cần nhớ `denyAll` ở cuối cũng có thể chặn route hữu ích như health, error, static content nếu chưa khai báo; hãy quyết định rõ những route đó.

## 12. Status 401 và 403 khác nhau

Khi request không được chấp nhận:

- **401 Unauthorized:** không có authentication hợp lệ hoặc bearer token bị từ chối. Tên HTTP status là “Unauthorized” nhưng về thực tế thường là **chưa xác thực thành công**.
- **403 Forbidden:** đã xác thực hợp lệ nhưng quyền được yêu cầu không có, hoặc policy tài nguyên từ chối.

Ví dụ:

| Request | Kết quả điển hình | Giải thích |
|---|---|---|
| Không token gọi `GET /api/public/catalog` | `200` nếu handler chạy tốt | Public |
| Không token gọi `GET /api/me` | `401` | Yêu cầu xác thực |
| Token hết hạn gọi `GET /api/me` | `401` | Token không hợp lệ |
| Token hợp lệ không scope gọi `GET /api/me` | `200` nếu contract cho phép | Chỉ cần authenticated |
| Token chỉ có `orders.read` gọi `GET /api/orders` | `200` nếu policy dữ liệu cho phép | Đúng quyền đọc |
| Token chỉ có `orders.read` gọi `POST /api/orders` | `403` | Thiếu `orders.write` |
| Token có `orders.write` nhưng thiếu `orders.read` gọi GET | `403` | Quyền ghi không mặc định bao hàm quyền đọc |
| Token hợp lệ gọi route chưa khai báo | `403` theo `denyAll` | Fallback từ chối |
| Token hợp lệ có scope đọc order của người khác | `403` hoặc `404` theo policy | Kiểm tra object ownership |

Kết quả chính xác còn phụ thuộc exception handler, chain đã chọn, dispatcher types và handler có tồn tại hay không. `200` trong bảng giả định controller và business service xử lý thành công.

### 12.1. `WWW-Authenticate` với bearer token

RFC 6750 định nghĩa header cho bearer authentication. Ví dụ:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
~~~

Khi token hợp lệ nhưng không đủ scope:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", scope="orders.write"
~~~

Đây là minh họa theo chuẩn; Spring Security và error handler tùy biến có thể trả nội dung cụ thể khác. Không đưa nguyên access token, private key hoặc thông tin nhạy cảm vào response lỗi.

## 13. JWT hợp lệ vẫn có thể không đủ quyền tài nguyên

Một `GET /api/orders/1001` có thể qua rule:

~~~java
.hasAuthority("SCOPE_orders.read")
~~~

nhưng còn phải kiểm tra người dùng có quyền xem **order 1001** hay không.

Tầng endpoint:

~~~text
Có SCOPE_orders.read? -> được vào handler
~~~

Tầng nghiệp vụ:

~~~text
Order 1001 thuộc tenant nào?
Subject có membership tại tenant đó không?
Order thuộc user nào?
User có entitlement đọc order này không?
~~~

Ví dụ pseudocode:

~~~java
Order order = repository.findById(orderId)
    .orElseThrow(NotFoundException::new);

InternalUser user = identityDirectory.resolve(
    jwt.getIssuer().toString(),
    jwt.getSubject()
);

if (!authorizationService.canReadOrder(user, order)) {
    throw new AccessDeniedException("Forbidden");
}

return order;
~~~

`Order`, `InternalUser`, `NotFoundException`, `identityDirectory` và `authorizationService` trong đoạn trên là lớp/khái niệm nghiệp vụ minh họa, không phải API Spring có sẵn.

Nếu chỉ kiểm tra `SCOPE_orders.read` mà bỏ object authorization, Resource Server có thể bị lỗi **Broken Object Level Authorization (BOLA)/IDOR**, cho phép user đọc dữ liệu của người khác bằng cách thay `orderId`.

## 14. CORS preflight không phải endpoint nghiệp vụ công khai

Browser client ở `https://app.example.com` gọi API `https://api.example.com` với bearer token thường cần CORS. Trình duyệt có thể gửi preflight trước:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

Preflight thường **không mang bearer token truy cập API**. Nếu để authentication xử lý nó như một request nghiệp vụ bình thường, browser có thể báo lỗi CORS dù access token thật hợp lệ.

Spring Security khuyến nghị xử lý CORS **trước security authentication** bằng cấu hình thích hợp, ví dụ cung cấp `CorsConfigurationSource`.

### 14.1. Ví dụ CORS source minh họa

~~~java
package com.example.orders.security;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class CorsConfig {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(List.of("https://app.example.com"));
        config.setAllowedMethods(
            List.of("GET", "POST", "PUT", "PATCH", "DELETE"));
        config.setAllowedHeaders(
            List.of("Authorization", "Content-Type"));
        config.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();

        source.registerCorsConfiguration("/api/**", config);
        return source;
    }
}
~~~

Kết hợp trong filter chain:

~~~java
.cors(Customizer.withDefaults())
~~~

Đây chỉ là ví dụ một SPA public origin được phép. Nếu dùng cookie/credentials xuyên origin, chính sách CORS khác và cần cấu hình `allowCredentials`/`SameSite`/CSRF phù hợp; không dùng `allowedOrigins("*")` cùng credentials.

**CORS không thay thế authentication/authorization.** Nó là chính sách browser cross-origin, không bảo đảm một HTTP client không phải browser bị ngăn gọi API. Đừng dùng CORS như bằng chứng endpoint được bảo vệ.

### 14.2. Không mở mọi `OPTIONS` vô điều kiện

Có thể thấy một bản sửa lỗi kiểu:

~~~java
.requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()
~~~

Quy tắc này không luôn sai, nhưng rất rộng và có thể che vấn đề cấu hình CORS. Nó cũng không tự tạo đúng các `Access-Control-Allow-*` headers mà browser cần. Ưu tiên cấu hình CORS và xử lý preflight chính xác, sau đó mới bổ sung matcher riêng nếu kiến trúc yêu cầu.

## 15. CSRF và quyết định tắt CSRF trong API bearer

Một REST API chỉ sử dụng `Authorization: Bearer <token>` do client chủ động đặt header, không dùng cookie tự động gửi để xác thực, thường có mô hình CSRF khác với ứng dụng browser dựa vào session cookie.

Vì vậy có thể thấy:

~~~java
.csrf(AbstractHttpConfigurer::disable)
.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
~~~

Đây là lựa chọn **có điều kiện** cho API stateless bearer-only, không phải tuyên bố mọi API OAuth đều có thể tắt CSRF.

Nếu cùng endpoint cũng chấp nhận:

- Session cookie dùng cho form login.
- Cookie tự động gửi để đại diện authentication.
- Một cơ chế cookie-based BFF.
- HTTP authentication tự động gắn từ browser trong tình huống có liên quan.

thì cần đánh giá CSRF dựa trên cách browser gửi credential. Một API có JWT nhưng cũng chấp nhận cookie vẫn có thể cần bảo vệ CSRF.

**`permitAll` không đồng nghĩa bỏ qua CSRF filter.** Ví dụ `POST` public không có CSRF token trong một application có CSRF bật có thể bị `403`. Vì vậy không nên kết luận `permitAll` “không hoạt động” chỉ từ một response 403 khi chưa xem filter gây lỗi.

## 16. Dispatcher types và error handling

Trong Servlet stack, ngoài request trực tiếp còn có dispatch types như `FORWARD` và `ERROR`. Một controller có thể forward hoặc framework có thể dispatch tới error endpoint.

Nếu rules quá chặt và không tính tới những dispatch này, response lỗi có thể bị một lớp `403` khác che lấp. Spring Security có hỗ trợ:

~~~java
import static jakarta.servlet.DispatcherType.ERROR;
import static jakarta.servlet.DispatcherType.FORWARD;

// Trong authorizeHttpRequests:
.dispatcherTypeMatchers(ERROR, FORWARD).permitAll()
~~~

Chỉ thêm khi phù hợp kiến trúc và policy; nó cho phép **các dispatcher types này** đi qua authorization rule, không biến endpoint chính thành công khai. Phải hiểu cách container và ứng dụng dùng dispatcher, và không mở rộng bừa bãi đến các dispatch types khác.

Trong một ứng dụng chỉ có REST controller đơn giản, có thể không cần rule này. Khi có error handling phức tạp hoặc MVC view rendering, nó là một yếu tố đáng kiểm tra nếu nhận 403 không mong đợi.

## 17. Method Security và phân quyền nhiều lớp

HTTP request rules thường là lớp bảo vệ đầu tiên:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

Nhưng quyền tại service có thể chi tiết hơn và cần bảo vệ bất kể service được gọi từ controller nào. Spring Security hỗ trợ method authorization qua `@EnableMethodSecurity`, `@PreAuthorize` và các cơ chế liên quan.

Ví dụ:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Service:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class OrderQueryService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public OrderSummary findOrder(String orderId) {
        // Còn phải kiểm tra ownership/tenant bằng policy dịch vụ.
        return loadAndCheckOwnership(orderId);
    }
}
~~~

`OrderSummary` và `loadAndCheckOwnership(...)` là các thành phần miền nghiệp vụ minh họa.

Không giả định việc bật `@EnableMethodSecurity` tự làm mọi method được bảo vệ. Chỉ những method/rule thực sự có chính sách sẽ được kiểm soát theo cấu hình. Và `@PreAuthorize` theo scope vẫn không thay thế object-level authorization nếu scope không mã hóa quyền trên từng order.

### Hai lớp bảo vệ có mâu thuẫn không?

Nếu HTTP yêu cầu `orders.read` và service cũng yêu cầu `orders.read`, hai lớp có thể được thiết kế theo **defense in depth**. Nhưng phải biết mục tiêu:

- HTTP rule bảo vệ route từ bên ngoài.
- Service rule bảo vệ nghiệp vụ nếu được gọi từ nhiều entrypoint.
- Object policy kiểm soát dữ liệu cụ thể.

Không dùng method security để che một HTTP matcher quá rộng mà không có test; mỗi boundary cần được hiểu rõ và kiểm soát.

## 18. Phân quyền theo role, scope và nhiều nguồn cấp quyền

Tại tầng HTTP, Spring Security không biết một authority đến từ JWT `scope`, claim `roles` hay database nếu adapter đều biểu diễn thành `GrantedAuthority`. Bởi vậy việc ánh xạ quyền phải có căn cứ.

Ví dụ:

~~~java
.hasAuthority("SCOPE_orders.read")
~~~

nên tương ứng scope thật do AS cấp. Nếu dùng role:

~~~java
.hasRole("ORDERS_ADMIN")
~~~

cần role `ROLE_ORDERS_ADMIN` đã được cấp từ một nguồn phân quyền được phê duyệt.

Không tự thêm `ROLE_ORDERS_ADMIN` khi token chỉ có `scope=orders.read`. Đó là **privilege escalation**. Tương tự, không dựa vào `email`, `preferred_username` hoặc domain email để phát hành quyền admin trong converter.

### Token JWT và opaque token

Điều kiện HTTP authorization như `permitAll`, `authenticated` hoặc `hasAuthority` không phụ thuộc trực tiếp token là JWT hay opaque. Khác biệt chủ yếu ở **cách tạo `Authentication`**:

- JWT: `JwtDecoder` xác minh chữ ký/claim, converter ánh xạ scope/role.
- Opaque: `OpaqueTokenIntrospector` kiểm tra trạng thái/attributes tại Authorization Server hoặc một thành phần introspection đáng tin.

Cả hai chỉ nên tạo authorities có căn cứ. `authenticated()` không tự được nâng thành `hasAuthority("SCOPE_orders.write")`.

## 19. Một controller minh họa ba loại endpoint

Để làm rõ kết quả, giả sử controller sau:

~~~java
package com.example.orders.api;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class DemoController {

    @GetMapping("/public/catalog")
    public Map<String, String> catalog() {
        return Map.of("status", "public");
    }

    @GetMapping("/me")
    public Map<String, String> me(@AuthenticationPrincipal Jwt jwt) {
        return Map.of("subject", jwt.getSubject());
    }

    @GetMapping("/orders")
    public Map<String, String> orders() {
        return Map.of("action", "read orders");
    }

    @PostMapping("/orders")
    public Map<String, String> createOrder() {
        return Map.of("action", "create order");
    }
}
~~~

Đoạn code chỉ dùng để minh họa rule HTTP; endpoint `/orders` trong sản phẩm thật phải làm việc với database và kiểm tra ownership/tenant. `/me` giả định token hợp lệ có `sub` không null. Với machine tokens, cần định nghĩa lại ý nghĩa của “me” cho đúng chủ thể.

### Request mẫu

Không token:

~~~bash
curl -i https://api.example.com/api/public/catalog
~~~

Có token hợp lệ:

~~~bash
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  https://api.example.com/api/me
~~~

Token có scope đọc:

~~~bash
curl -i \
  -H "Authorization: Bearer $READ_ACCESS_TOKEN" \
  https://api.example.com/api/orders
~~~

Thử POST bằng token chỉ có scope đọc:

~~~bash
curl -i -X POST \
  -H "Authorization: Bearer $READ_ACCESS_TOKEN" \
  https://api.example.com/api/orders
~~~

Theo policy ví dụ, request POST cuối cùng phải bị từ chối vì thiếu `SCOPE_orders.write`. Không đưa token thật vào log, ticket, ảnh chụp màn hình hoặc shell history chia sẻ.

## 20. Kiểm thử HTTP authorization bằng MockMvc

`spring-security-test` hỗ trợ các tiện ích giúp kiểm thử phân quyền. Ví dụ test dùng `MockMvc` với `jwt()` để tạo JWT authentication giả lập:

~~~java
package com.example.orders.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HttpAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointWorksWithoutToken() throws Exception {
        mvc.perform(get("/api/public/catalog"))
            .andExpect(status().isOk());
    }

    @Test
    void meRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void meAllowsValidatedPrincipalInAuthorizationTest()
            throws Exception {
        mvc.perform(get("/api/me")
                .with(jwt().jwt(token -> token.subject("user-42"))))
            .andExpect(status().isOk());
    }

    @Test
    void readScopeAllowsGetOrders() throws Exception {
        mvc.perform(get("/api/orders")
                .with(jwt().authorities(
                    () -> "SCOPE_orders.read")))
            .andExpect(status().isOk());
    }

    @Test
    void readScopeDoesNotAllowPostOrders() throws Exception {
        mvc.perform(post("/api/orders")
                .with(jwt().authorities(
                    () -> "SCOPE_orders.read")))
            .andExpect(status().isForbidden());
    }

    @Test
    void writeScopeAllowsPostOrders() throws Exception {
        mvc.perform(post("/api/orders")
                .with(jwt().authorities(
                    () -> "SCOPE_orders.write")))
            .andExpect(status().isOk());
    }

    @Test
    void unknownEndpointIsDeniedByDefault() throws Exception {
        mvc.perform(get("/api/unknown")
                .with(jwt()))
            .andExpect(status().isForbidden());
    }
}
~~~

**Điều kiện của ví dụ test:** ứng dụng có `DemoController` ở phần trước và filter chain tương ứng; các handler thật không ném lỗi nghiệp vụ; CSRF được cấu hình theo mô hình bearer-only như ví dụ. Với ứng dụng có CSRF bật, một request POST trong test có thể cần `csrf()` hoặc policy khác.

### Giới hạn của `jwt()` trong test

`jwt()` là công cụ mock **authentication/principal/authorities**. Khi test dùng:

~~~java
.with(jwt().authorities(() -> "SCOPE_orders.read"))
~~~

nó đang chỉ định authorities cho một authentication test, **không kiểm tra signature JWT thật, JWKS, issuer, audience hoặc converter production**.

Vì vậy nên tách:

- **Authorization tests:** xem rule HTTP cho phép/từ chối theo `Authentication` dự kiến.
- **Authentication/integration tests:** gửi JWS thật được ký bằng test key qua `JwtDecoder` và kiểm tra sai signature, issuer, audience, expiration.
- **Converter tests:** kiểm tra claim `scope`/`scp` được ánh xạ chính xác và không tự sinh quyền.
- **Business policy tests:** kiểm tra tenant/ownership và object-level authorization.

Từng loại test bảo vệ một ranh giới khác nhau; không dùng một test mock JWT để tuyên bố toàn bộ hệ thống OAuth đã an toàn.

## 21. Ma trận test quan trọng cho ba loại endpoint

| Trường hợp | Public GET | Authenticated GET | Scoped GET | Scoped POST |
|---|---|---|---|---|
| Không có token | Cho phép | 401 | 401 | 401 |
| JWT hết hạn | Có thể 401 nếu gửi bearer lỗi vào cùng chain | 401 | 401 | 401 |
| JWT hợp lệ, không scope | Cho phép | Cho phép | 403 | 403 |
| JWT chỉ có `orders.read` | Cho phép | Cho phép | Cho phép | 403 |
| JWT chỉ có `orders.write` | Cho phép | Cho phép | 403 | Cho phép |
| JWT có cả read/write | Cho phép | Cho phép | Cho phép | Cho phép |
| JWT audience sai | Có thể 401 nếu gửi token lỗi | 401 | 401 | 401 |
| JWT hợp lệ nhưng không có quyền order cụ thể | Cho phép với public resource | Tùy policy | 403/404 ở object policy | Tùy policy |

Bảng nêu **quyết định bảo mật dự kiến**. Status thực tế giả định endpoint tồn tại, business code chạy thành công, không có filter khác từ chối, và invalid token được gửi bằng bearer header vào chain có Resource Server authentication.

Đặc biệt hãy test **không token** và **token sai** trên endpoint public như hai tình huống riêng. `permitAll` không buộc bearer authentication filter bỏ qua một credential sai đã được trình bày.

## 22. Lỗi phổ biến khi thiết kế ba nhóm endpoint

### 22.1. Đặt `permitAll` quá rộng

~~~java
// SAI: mở toàn bộ API, kể cả endpoint riêng tư.
.requestMatchers("/api/**").permitAll()
~~~

Sửa bằng path public hẹp và rule cho từng nhóm endpoint.

### 22.2. Dùng `authenticated` cho API cần entitlement

~~~java
// CHƯA ĐỦ nếu order yêu cầu scope đọc riêng.
.requestMatchers("/api/orders/**").authenticated()
~~~

Sửa thành matcher theo HTTP method và `hasAuthority` phù hợp.

### 22.3. Dùng `hasRole` khi chỉ có OAuth scope

~~~java
// Có thể không bao giờ khớp nếu token chỉ có SCOPE_orders.read.
.requestMatchers("/api/orders/**").hasRole("orders.read")
~~~

Sửa thành `hasAuthority("SCOPE_orders.read")` nếu issuer cấp scope đó. Không tự thêm `ROLE_orders.read` vào converter chỉ để code cũ chạy.

### 22.4. Đặt rule tổng quát lên trước rule cụ thể

~~~java
// SAI: /api/admin/** sẽ bị /api/** che mất.
.requestMatchers("/api/**").authenticated()
.requestMatchers("/api/admin/**").hasRole("ADMIN")
~~~

Đặt rule chặt cụ thể trước.

### 22.5. Quên default rule

Nếu chỉ có một số requestMatchers trong một chain, những đường dẫn còn lại có thể được xử lý theo các quy tắc/chain khác mà bạn không dự kiến. Hãy khai báo một `anyRequest()` rõ ràng cho chain và có fallback chain nếu dùng `securityMatcher` hẹp.

### 22.6. Chỉ bảo vệ GET nhưng quên POST/PUT/DELETE

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.anyRequest().authenticated()
~~~

Trong ví dụ này, POST chưa có rule scope riêng sẽ rơi vào `authenticated()`, có thể mở quyền ghi ngoài ý muốn nếu controller hỗ trợ. Dùng `denyAll` hoặc khai báo đủ method.

### 22.7. Dùng CORS để quyết định quyền

~~~text
AllowedOrigin: https://app.example.com
~~~

không phải authorization policy. HTTP client trực tiếp không bị browser CORS kiểm soát. Cần kiểm tra bearer token và authorities tại server.

### 22.8. Xem scope như quyền trên mọi bản ghi

`orders.read` cho phép gọi loại endpoint đọc; việc user có được xem order cụ thể vẫn cần policy trên dữ liệu.

### 22.9. Mặc định public health endpoint tiết lộ quá nhiều

Health check tối thiểu có thể công khai nếu vận hành yêu cầu. Nhưng metrics, environment, config, heapdump, loggers hoặc những actuator endpoints khác không nên được mở rộng bằng một rule `/actuator/**.permitAll()` chỉ vì health cần public.

### 22.10. Tắt CSRF một cách vô điều kiện

Bearer-only stateless API có thể có lý do phù hợp để disable CSRF. Browser session/cookie authentication lại có mô hình rủi ro khác. Kiểm tra kiến trúc trước khi tắt.

## 23. Quy trình thiết kế policy cho một API mới

Khi thêm endpoint, thay vì bắt đầu bằng “cho `authenticated()` là xong”, hãy trả lời theo thứ tự:

1. **Có thật sự là dữ liệu công khai?** Nếu có, dùng matcher hẹp với `permitAll`, kiểm soát dữ liệu trả ra.
2. **Chỉ cần biết principal hợp lệ hay cần entitlement riêng?** Nếu chỉ là thông tin của bản thân principal, `authenticated` có thể đủ.
3. **Hành động HTTP thuộc phạm vi scope/role nào?** Dùng `hasAuthority`, `hasAnyAuthority` hoặc policy rõ.
4. **HTTP method nào được phép?** Không để write action rơi vào fallback chỉ cần authenticated.
5. **Có điều kiện theo tenant, owner, bản ghi không?** Bổ sung policy trong service hoặc method security.
6. **Có endpoint/chain/fallback khác ảnh hưởng không?** Xem matcher order và `securityMatcher`.
7. **Client có gửi browser cookie hoặc gọi cross-origin không?** Cân nhắc CSRF và CORS.
8. **Có test từ chối phù hợp không?** Kiểm tra không token, token sai, thiếu scope, route chưa khai báo và object không thuộc quyền.

### Ví dụ checklist thiết kế `POST /api/refunds`

Đây là một endpoint nhạy cảm. `authenticated()` thường không đủ. Có thể cần:

~~~text
POST /api/refunds
    -> valid access token
    -> aud = refunds-api
    -> SCOPE_refunds.create
    -> người gọi có quyền thực hiện refund ở merchant này
    -> giao dịch còn trong trạng thái được refund
    -> policy hạn mức/phê duyệt bổ sung
~~~

HTTP `hasAuthority("SCOPE_refunds.create")` chỉ bảo vệ một lớp. Không đồng nhất scope với sự phê duyệt toàn bộ giao dịch.

## 24. Câu hỏi tự kiểm tra

**Câu 1.** `permitAll()` có nghĩa Spring Security bỏ qua JWT filter hoàn toàn không?

> Không. Nó là rule authorization; những filter khác trong chain, bao gồm bearer token authentication, vẫn có thể xử lý request. Token sai được gửi tới public endpoint có thể gây 401.

**Câu 2.** `authenticated()` có yêu cầu token chứa `orders.read` không?

> Không. Nó yêu cầu authentication hợp lệ. Quyền đọc đơn hàng cần rule `hasAuthority("SCOPE_orders.read")` hoặc policy tương ứng.

**Câu 3.** JWT có `scope=orders.read`, gọi `POST /api/orders` cần `orders.write`. Kết quả?

> Token có thể được xác thực nhưng không vượt qua rule quyền ghi; thường là 403.

**Câu 4.** Tại sao `requestMatchers("/api/**").permitAll()` đặt trước rule admin nguy hiểm?

> Vì matcher rộng có thể khớp request trước; rule admin sau đó không được xét.

**Câu 5.** `anyRequest().denyAll()` có bảo vệ những URL không thuộc `securityMatcher("/api/**")` không?

> Không. `anyRequest` chỉ áp dụng bên trong chain đã được chọn. Nếu không có chain khác khớp, các URL ngoài phạm vi có thể không đi qua bảo vệ Spring Security.

**Câu 6.** Nếu browser báo lỗi CORS preflight, có nên bỏ JWT verification không?

> Không. Cần cấu hình CORS và preflight handling đúng, độc lập với authentication/authorization của request nghiệp vụ.

**Câu 7.** Vì sao một token có `SCOPE_orders.read` vẫn có thể bị từ chối khi đọc đơn hàng?

> Vì API còn phải kiểm tra tenant, owner hoặc quyền trên bản ghi cụ thể.

**Câu 8.** `hasRole("ADMIN")` có giống `hasAuthority("SCOPE_admin")` không?

> Không. Với prefix mặc định, `hasRole("ADMIN")` kiểm tra `ROLE_ADMIN`.

**Câu 9.** MockMvc `with(jwt())` có chứng minh signature JWT production được xác minh không?

> Không. Nó mô phỏng authentication để kiểm tra authorization; cần integration test với JWT được ký bằng test key và decoder thực.

**Câu 10.** Một endpoint mới chỉ nên mở cho người dùng đã xác thực, nhưng chưa có matcher và fallback là `denyAll()`. Điều gì xảy ra?

> Request bị từ chối cho tới khi developer thêm rule rõ ràng, đúng với chính sách fail closed.

## 25. Tài liệu tham khảo

- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `authorizeHttpRequests`, `permitAll`, `denyAll`, `hasAuthority` và thứ tự matcher.
- [Spring Security — Java Configuration / Multiple SecurityFilterChain](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): `securityMatcher`, thứ tự chain và phạm vi áp dụng.
- [Spring Security — OAuth 2.0 Resource Server JWT (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT verification và scope → `SCOPE_*` authorities.
- [Spring Security — Bearer Tokens (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html): cách nhận bearer token và hành vi authentication.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity` và `@PreAuthorize`.
- [Spring Security — CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): preflight và `CorsConfigurationSource`.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): chính sách CSRF, đặc biệt với browser/cookie.
- [Spring Security — Testing OAuth 2.0](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): test JWT authentication trong MockMvc.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer authentication và `WWW-Authenticate`.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): claim và ngữ nghĩa scope/audience của JWT access token.

Khi thiết kế HTTP authorization cho Resource Server, hãy **khai báo chính xác endpoint nào công khai, endpoint nào chỉ cần authentication và endpoint nào yêu cầu authority cụ thể**, kiểm soát thứ tự matcher, xử lý rõ những route chưa khai báo và luôn kiểm tra quyền trên tài nguyên ở tầng nghiệp vụ. Đây là nền tảng để một API vừa dễ sử dụng vừa không vô tình mở rộng quyền truy cập.
