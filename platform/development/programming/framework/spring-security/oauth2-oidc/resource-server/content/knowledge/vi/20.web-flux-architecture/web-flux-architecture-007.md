# authorizeExchange và quy tắc phân quyền cho HTTP exchange

Trong **Spring Security OAuth 2.0/OIDC Resource Server chạy trên Spring WebFlux**, lớp bảo vệ HTTP thường được khai báo bằng **`ServerHttpSecurity.authorizeExchange(...)`**. Đây là cách mô tả request nào công khai, request nào đòi xác thực, request nào cần OAuth scope/role, và trường hợp nào phải bị từ chối ngay từ tầng web.

Ví dụ:

~~~java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/public/**").permitAll()
    .pathMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .pathMatchers(HttpMethod.POST, "/api/orders/**")
        .hasAuthority("SCOPE_orders.write")
    .anyExchange().denyAll()
)
~~~

Mỗi rule gồm **một điều kiện khớp HTTP exchange** và **một quyết định authorization**. Spring Security xét các rule theo thứ tự khai báo; rule khớp đầu tiên là rule được sử dụng. Điều này khiến thứ tự và phạm vi matcher trở thành một phần quan trọng của mô hình bảo mật.

> **Nguyên tắc:** `authorizeExchange` xác định chính sách truy cập **ở HTTP exchange boundary**. JWT/opaque access token phải được xác thực bằng thành phần Reactive Resource Server trước đó; và ngay cả khi scope hợp lệ, quyền trên tenant/đơn hàng cụ thể vẫn cần kiểm tra ở tầng nghiệp vụ.

Bài học tập trung vào **`SecurityWebFilterChain`, `ServerHttpSecurity`, `authorizeExchange`, `pathMatchers`, `matchers`, `anyExchange`, `ReactiveAuthorizationManager<AuthorizationContext>` và `WebTestClient`**. Các ví dụ dùng **Java 17+, Spring Boot, Spring Security Reactive/WebFlux**. Những tên API có thể thay đổi theo phiên bản; đoạn ví dụ custom manager ưu tiên API Spring Security 6.4+/7.x với phương thức `authorize(...)`.

## 1. WebFlux authorization khác Servlet ở điểm nào?

Spring Security hỗ trợ cả Servlet stack và Reactive WebFlux stack. Hai stack cùng áp dụng các khái niệm authentication/authorization, nhưng dùng các đối tượng và contract khác nhau.

| Khía cạnh | Servlet/Spring MVC | Reactive/WebFlux |
|---|---|---|
| Kiểu HTTP security configuration | `HttpSecurity` | **`ServerHttpSecurity`** |
| Chuỗi bảo mật | `SecurityFilterChain` | **`SecurityWebFilterChain`** |
| Filter web | Servlet `Filter` | Reactive **`WebFilter`** |
| Đối tượng HTTP | `HttpServletRequest` / `HttpServletResponse` | **`ServerWebExchange`** |
| DSL phân quyền | `authorizeHttpRequests` | **`authorizeExchange`** |
| Path matcher | `requestMatchers` | **`pathMatchers` hoặc `matchers`** |
| Rule cuối | `anyRequest` | **`anyExchange`** |
| Custom HTTP authorization | `AuthorizationManager<RequestAuthorizationContext>` | **`ReactiveAuthorizationManager<AuthorizationContext>`** |
| JWT decoder | `JwtDecoder` | **`ReactiveJwtDecoder`** |
| Opaque token introspector | `OpaqueTokenIntrospector` | **`ReactiveOpaqueTokenIntrospector`** |
| Security context | `SecurityContextHolder` qua Servlet execution model | **Reactor Context / `ReactiveSecurityContextHolder`** |
| Test HTTP | `MockMvc` | **`WebTestClient`** |

**Không sao chép** `SecurityFilterChain`, `requestMatchers()` và `JwtDecoder` của MVC sang `ServerHttpSecurity` rồi kỳ vọng chạy như WebFlux. Tương tự, không dùng `HttpServletRequest#getSession()` trong business code reactive vì HTTP request model của WebFlux là `ServerWebExchange`/`ServerHttpRequest`.

### 1.1. HTTP exchange là gì?

`ServerWebExchange` biểu diễn một lượt trao đổi HTTP trong WebFlux:

~~~text
ServerWebExchange
    |
    +-- exchange.getRequest()
    |      +-- method, path, headers, cookies, query params
    |
    +-- exchange.getResponse()
    |      +-- status, headers, body
    |
    +-- exchange.getAttributes()
    |
    +-- exchange.getPrincipal()
    |
    +-- exchange.getSession() -> reactive WebSession khi cần
~~~

Tại tầng authorization, Spring Security không chỉ nhìn URL; nó có thể xét **HTTP method, path, headers, query, principal và nhiều thuộc tính ngữ cảnh**, nhưng không có nghĩa các input do client gửi là bằng chứng về quyền.

Path, header và query parameter mô tả **điều client yêu cầu**. Quyền phải được xác định từ authentication đã tin cậy hoặc một nguồn authorization có thẩm quyền.

### 1.2. `authorizeExchange` nằm ở đâu trong request flow?

~~~text
Client:
Authorization: Bearer <access-token>
                |
                v
WebFlux WebFilter chain
                |
                +-- CORS / CSRF / headers / context filters
                |
                +-- AuthenticationWebFilter (Resource Server)
                |      |
                |      +-- ReactiveJwtDecoder hoặc
                |      |   ReactiveOpaqueTokenIntrospector
                |      |
                |      +-- Thành công: Authentication ở Reactor Context
                |      +-- Thất bại: authentication failure
                |
                +-- AuthorizationWebFilter
                |      |
                |      +-- ServerWebExchangeMatcher?
                |      +-- permitAll/authenticated/hasAuthority/access
                |      |
                |      +-- Grant hoặc Deny
                |
                v
WebFlux handler / Controller / HandlerFunction
                |
                v
Reactive service + object/tenant authorization
                |
                v
Response
~~~

Sơ đồ khái niệm, không phải danh sách cố định mọi WebFilter hay thứ tự chi tiết trên tất cả phiên bản. Điểm quan trọng là **authentication tạo identity/authorities**, còn **authorizeExchange dùng dữ liệu đó để quyết định quyền HTTP**.

## 2. Ba loại endpoint cơ bản và một default rule

Trong API nghiệp vụ, có thể phân thành:

| Loại endpoint | Rule WebFlux | Điều kiện ở tầng HTTP |
|---|---|---|
| Công khai | `permitAll()` | Không đòi authentication |
| Cần xác thực | `authenticated()` | Có authentication hợp lệ |
| Cần quyền cụ thể | `hasAuthority("SCOPE_orders.read")` | Có authority đúng |
| Cần role cụ thể | `hasRole("ADMIN")` | Có role tương ứng, thường `ROLE_ADMIN` |
| Một trong nhiều quyền | `hasAnyAuthority(...)` | Có ít nhất một authority được yêu cầu |
| Luôn từ chối | `denyAll()` | Không cho phép |
| Logic tùy chỉnh | `access(customReactiveManager)` | Kết quả từ policy được cấp |

Ví dụ:

~~~java
.authorizeExchange(exchanges -> exchanges
    // Công khai
    .pathMatchers(HttpMethod.GET, "/api/public/**").permitAll()

    // Token hợp lệ, chưa cần scope nghiệp vụ riêng
    .pathMatchers(HttpMethod.GET, "/api/me").authenticated()

    // Token hợp lệ và có đúng scope được cấp
    .pathMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .pathMatchers(HttpMethod.POST, "/api/orders/**")
        .hasAuthority("SCOPE_orders.write")

    // Không mở những exchange chưa được khai báo
    .anyExchange().denyAll()
)
~~~

**Phần dễ nhầm:** `authenticated()` không tự đồng nghĩa với `hasAuthority("SCOPE_orders.read")`; còn `permitAll()` không có nghĩa toàn bộ security WebFilters bị bỏ qua.

### 2.1. `permitAll()` là public authorization, không phải bypass filter chain

Với:

~~~java
.pathMatchers(HttpMethod.GET, "/api/public/catalog")
    .permitAll()
~~~

request không có bearer token có thể được cho qua. Nhưng nếu client gửi một **bearer token sai hoặc hết hạn** vào chính endpoint public, Resource Server authentication filter có thể từ chối token trước khi exchange tới bước `permitAll`.

Ví dụ:

~~~http
GET /api/public/catalog HTTP/1.1
Host: api.example.com
~~~

Có thể được cho qua.

~~~http
GET /api/public/catalog HTTP/1.1
Host: api.example.com
Authorization: Bearer invalid-token
~~~

Có thể nhận **401** vì client đã cung cấp một credential không hợp lệ. `permitAll` không ra lệnh authentication filter bỏ qua token được gửi.

Để test endpoint public, hãy có test **không Authorization header**, và một test riêng cho **invalid bearer header**.

### 2.2. `authenticated()` không kiểm tra object ownership

~~~java
.pathMatchers("/api/me").authenticated()
~~~

phù hợp nếu endpoint chỉ đọc thông tin của **principal hiện tại**. Nhưng:

~~~text
GET /api/users/{userId}/profile
~~~

thường không thể dùng `authenticated()` làm lớp bảo vệ duy nhất, vì user A có thể thay `{userId}` thành user B. Cần thêm object-level authorization.

### 2.3. `hasAuthority()` kiểm tra authority chính xác

~~~java
.hasAuthority("SCOPE_orders.read")
~~~

yêu cầu authority đúng chuỗi `SCOPE_orders.read`. Nếu token chỉ có `SCOPE_orders.write`, nó không tự vượt qua rule đọc. Một scope, role hoặc authority có tên gần giống không tự tương đương.

### 2.4. `hasRole()` có prefix riêng

~~~java
.hasRole("ORDERS_ADMIN")
~~~

thông thường yêu cầu `ROLE_ORDERS_ADMIN` theo role prefix mặc định. Nó khác:

~~~java
.hasAuthority("SCOPE_orders.admin")
~~~

OAuth scope `orders.admin` **không tự trở thành** application role `ORDERS_ADMIN`, trừ khi ứng dụng có mapping được phê duyệt và test rõ.

## 3. Cấu hình JWT Resource Server WebFlux đầy đủ

Giả sử `orders-api` được bảo vệ bằng bearer JWT do một AS đáng tin cấp.

### 3.1. Dependency Gradle

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Sử dụng **WebFlux starter**, không lấy Servlet MVC security làm cơ sở bài học. Nếu trong project có cả MVC và WebFlux starters, cần hiểu cơ chế Spring Boot chọn web application type; không giả định ứng dụng chắc chắn chạy reactive chỉ vì đã thêm một dependency WebFlux.

### 3.2. `application.yml`

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

- `issuer-uri` xác định issuer mà Resource Server tin, cần đúng claim `iss`.
- `audiences` ràng buộc token phải được cấp cho `orders-api` trong các Spring Boot version hỗ trợ property này.
- Chữ ký, hạn sử dụng, key rotation và token profile cần được decoder/validators kiểm tra.
- ID token của OIDC Client không phải access token dành cho Resource Server; không dùng ID token thay thế chỉ vì nó cũng là JWT.

Khi khai báo custom `ReactiveJwtDecoder`, cần chú ý Spring Boot có thể **back off** khỏi auto-configuration decoder. Các validators issuer/audience/profile phải được duy trì đầy đủ theo hợp đồng; không chỉ decode payload rồi tin mọi claim.

### 3.3. `SecurityWebFilterChain`

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ApiSecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/public/**")
                    .permitAll()

                .pathMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()

                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")

                .pathMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")

                .pathMatchers(HttpMethod.PUT, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")

                .pathMatchers(HttpMethod.DELETE, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.delete")

                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

`@EnableWebFluxSecurity` là annotation dùng cho Spring Security WebFlux. Spring Boot có cơ chế cấu hình tự động, nhưng định nghĩa tường minh giúp phân biệt với `@EnableWebSecurity` của Servlet.

Ví dụ cố ý **không** thêm `.csrf(...disable)` hoặc `.httpBasic(...disable)` ngay ở đây để tách các quyết định khác với bản chất `authorizeExchange`. Với API bearer-only, chính sách CSRF, session, CORS, HTTP Basic và form login cần được xét theo kiến trúc cụ thể.

### 3.4. Rule nào được áp dụng?

| Method | URL | Rule đầu tiên khớp | Quyền bắt buộc |
|---|---|---|---|
| GET | `/api/public/catalog` | Public GET | Không cần token |
| GET | `/api/me` | Authenticated GET | Có token hợp lệ |
| GET | `/api/orders` | Orders GET | `SCOPE_orders.read` |
| GET | `/api/orders/1001` | Orders GET | `SCOPE_orders.read` |
| POST | `/api/orders` | Orders POST | `SCOPE_orders.write` |
| PUT | `/api/orders/1001` | Orders PUT | `SCOPE_orders.write` |
| DELETE | `/api/orders/1001` | Orders DELETE | `SCOPE_orders.delete` |
| PATCH | `/api/orders/1001` | `anyExchange` | Từ chối vì chưa có rule |
| GET | `/api/unknown` | `anyExchange` | Từ chối |
| GET | `/management/secrets` | `anyExchange` | Từ chối |

Đây là kết quả **HTTP authorization** theo matcher và ví dụ, trước các điều kiện controller/service khác. Một endpoint không tồn tại có thể trả 404 trong tình huống khác; với fallback `denyAll`, Spring Security có thể từ chối trước khi biết handler có tồn tại hay không.

## 4. `pathMatchers(...)` và phạm vi áp dụng

`pathMatchers` là API thuận tiện để xét path hoặc kết hợp HTTP method + path.

~~~java
.pathMatchers("/api/public/**").permitAll()
.pathMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.pathMatchers(HttpMethod.POST, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")
~~~

Ba biểu thức trên khác nhau:

1. `/api/public/**` áp dụng **mọi method** với path khớp.
2. `HttpMethod.GET` chỉ áp dụng **GET** với path phù hợp.
3. `HttpMethod.POST` chỉ áp dụng **POST**.

Nếu endpoint public chỉ được đọc, nên giới hạn `HttpMethod.GET`. Đặt mọi method ở `permitAll` có thể vô tình mở một POST/DELETE được thêm sau này dưới cùng path prefix.

### 4.1. Path pattern và biến đường dẫn

Ví dụ:

~~~java
.pathMatchers(
    HttpMethod.GET,
    "/api/tenants/{tenantId}/orders/{orderId}"
).hasAuthority("SCOPE_orders.read")
~~~

Ở đây các phần `{tenantId}` và `{orderId}` dùng để **khớp route**. Nhưng chỉ có `SCOPE_orders.read` chưa chứng minh principal được phép xem một order cụ thể.

Khi dùng custom `ReactiveAuthorizationManager<AuthorizationContext>`, bạn có thể đọc URI template variables qua `AuthorizationContext#getVariables()` trong những matcher hỗ trợ việc trích biến. Nếu không có biến vì matcher hoặc WebFlux routing khác nhau, phải xử lý **fail closed**, không tự đoán quyền từ header của client.

### 4.2. Path normalization, encoding và reverse proxy

Khi dùng matcher trong production, cần xác định:

- API có `spring.webflux.base-path` hay gateway rewrite không?
- Matchers xét path nào tại thời điểm đến application?
- Có trailing slash hoặc path segment encoded khác nhau không?
- Routing handler và security matcher có cùng cách xử lý path variables không?
- Proxy có áp dụng prefix `/gateway` hay rewrite `/api` không?
- Có static resources, actuator endpoints hoặc error route nằm ngoài prefix không?

Không tự giả định `"/api/**"` bao phủ mọi route hiện có nếu reverse proxy/handler có cấu hình khác. Một lỗ hổng có thể xuất hiện khi route nghiệp vụ nằm ngoài pattern mà security developer tưởng nó khớp.

### 4.3. `HEAD`, `OPTIONS`, `PATCH` và phương thức khác

Không chỉ test GET/POST. HTTP cho phép nhiều method:

| Method | Tình huống | Lưu ý |
|---|---|---|
| GET | Đọc dữ liệu | Không đồng nghĩa quyền truy cập mọi object |
| HEAD | Lấy headers | Có thể được mapping tương tự GET ở handler, nhưng security method matcher cần xét riêng |
| POST | Tạo/hành động | Cần scope riêng và kiểm tra CSRF khi phù hợp |
| PUT/PATCH | Cập nhật | Không nên chỉ yêu cầu scope đọc |
| DELETE | Xóa | Cần entitlement xóa và object policy |
| OPTIONS | CORS preflight | Cần cấu hình CORS, không nhầm endpoint nghiệp vụ public |
| TRACE | Diagnostic method | Thường cần được hạn chế/từ chối theo policy server |

Nếu đặt:

~~~java
.pathMatchers("/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

mọi method khớp path đều có thể được cho qua chỉ với scope đọc. Nếu controller sau này thêm `DELETE /api/orders/{id}`, rule chung tạo nguy cơ cấp quyền quá rộng.

Cấu hình an toàn hơn là khai báo **từng method** với scope tương ứng và dùng `.anyExchange().denyAll()`.

## 5. Thứ tự rule là một phần của bảo mật

Spring Security Reactive xét những rule trong `authorizeExchange` **theo thứ tự khai báo**; rule khớp đầu tiên quyết định policy.

### 5.1. Ví dụ sai: public matcher quá rộng đứng đầu

~~~java
// SAI: rule đầu che rule admin.
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/**").permitAll()
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .anyExchange().denyAll()
)
~~~

Request `/api/admin/users` đã khớp `/api/**`, nên rule `hasRole("ADMIN")` **không được chọn**. Thêm rule chặt ở sau không làm mất hiệu lực rule đã match ở đầu.

### 5.2. Sửa bằng rule cụ thể trước

~~~java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .pathMatchers("/api/public/**").permitAll()
    .pathMatchers("/api/**").authenticated()
    .anyExchange().denyAll()
)
~~~

Điều này an toàn **nếu chủ đích** mọi API còn lại chỉ cần authentication. Nếu endpoint chứa dữ liệu riêng cần scope, hãy khai báo scope trước rule tổng quát hoặc dùng `denyAll` làm fallback.

### 5.3. Ví dụ sai: authenticated matcher che scoped matcher

~~~java
// SAI: có token hợp lệ là đủ vào orders.
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/**").authenticated()
    .pathMatchers("/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .anyExchange().denyAll()
)
~~~

`/api/orders/**` không được bảo vệ bằng scope như developer mong muốn, vì `/api/**` đã match đầu tiên.

### 5.4. Quy tắc tổ chức dễ bảo trì

~~~text
1. Exact routes nhạy cảm / admin
2. Routes với method và scope cụ thể
3. Routes authenticated nhưng không cần scope nghiệp vụ
4. Routes public thật sự (đặt trước route cha nếu cha match rộng)
5. anyExchange().denyAll()
```

Thứ tự cụ thể còn phụ thuộc cấu trúc path. Không có một thứ tự cứng phù hợp mọi hệ thống, nhưng **matcher hẹp phải đứng trước matcher rộng có thể bao phủ nó**.

## 6. `anyExchange()` và chính sách mặc định

Hai lựa chọn thường gặp:

~~~java
.anyExchange().authenticated()
~~~

và:

~~~java
.anyExchange().denyAll()
~~~

có hệ quả khác nhau.

| Fallback | Exchange chưa có rule riêng | Rủi ro |
|---|---|---|
| `authenticated()` | Bất kỳ principal hợp lệ nào có thể qua tầng HTTP | Endpoint nhạy cảm mới có thể mở cho mọi user hợp lệ |
| `denyAll()` | Bị từ chối đến khi có rule tường minh | Có thể cần cập nhật config mỗi lần thêm endpoint |
| `permitAll()` | Mặc định công khai | Nguy hiểm với API có dữ liệu riêng tư |

**Với Resource Server có nhiều loại scope**, `anyExchange().denyAll()` thường là điểm xuất phát tốt theo nguyên tắc fail closed. Các endpoint mới cần được review và thêm rule rõ ràng.

Tuy vậy, nếu ứng dụng có cấu trúc policy rằng “mọi endpoint còn lại dành cho tất cả principal hợp lệ”, dùng `authenticated()` là hợp lệ khi đã được xác nhận. Không nên biến mọi quyết định thiết kế thành công thức duy nhất.

### 6.1. Deny-all không làm thay việc kiểm tra dữ liệu trả về

Một endpoint GET có rule `SCOPE_orders.read` vẫn có thể trả sai order của user khác nếu service không kiểm tra ownership. Fallback `denyAll` chỉ bảo vệ **đường dẫn chưa match**, không bảo đảm dữ liệu của đường dẫn đã allow là đúng phạm vi.

## 7. Kết hợp JWT access token và scope-based rules

JWT access token ví dụ:

~~~json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 2000000300
}
~~~

Spring Security Resource Server Reactive thường ánh xạ `scope` hoặc `scp` thành authorities với prefix `SCOPE_`.

~~~text
JWT scope:    orders.read
Authority:    SCOPE_orders.read
~~~

Do đó:

~~~java
.pathMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

có thể cho token này qua tầng HTTP. Nhưng:

~~~java
.pathMatchers(HttpMethod.POST, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")
~~~

sẽ từ chối nếu token chỉ có `orders.read`.

### 7.1. Dùng `OAuth2ReactiveAuthorizationManagers.hasScope`

Spring Security có một cách khác diễn đạt điều kiện scope:

~~~java
import static org.springframework.security.oauth2.core.authorization
    .OAuth2ReactiveAuthorizationManagers.hasScope;

// Bên trong authorizeExchange:
.pathMatchers("/api/orders/**")
    .access(hasScope("orders.read"))
~~~

Ví dụ trên chỉ minh họa static import được xuống dòng để dễ đọc; trong Java thật, câu `import static` phải viết **trên một dòng**:

~~~java
import static org.springframework.security.oauth2.core.authorization.OAuth2ReactiveAuthorizationManagers.hasScope;
~~~

`hasScope("orders.read")` biểu diễn scope không có tiền tố, còn `hasAuthority("SCOPE_orders.read")` dùng authority đã được converter tạo. Đây là hai cách thường đạt cùng mục đích nếu mapping mặc định vẫn được giữ.

**Không tự đổi một scope sang role cao hơn** để “làm API chạy được”. Nếu token thiếu `orders.write`, phải xin quyền hợp lệ từ Authorization Server hoặc từ chối.

### 7.2. Token được xác thực không tự đồng nghĩa đúng API

Tại Resource Server, JWT cần đáp ứng contract như issuer, audience, expiry, key/algorithm và token type. Một ID token dùng đăng nhập OIDC Client có thể có chữ ký hợp lệ nhưng audience là client ID, không phải `orders-api`. Không dùng ID token để vượt qua `authenticated()` của API.

Nếu có custom `ReactiveJwtDecoder`, cần duy trì các validators này rõ ràng.

### 7.3. `scope` và custom claim không phải cùng một policy

Một token có thể chứa thêm:

~~~json
{
  "scope": "orders.read",
  "roles": ["orders_manager"],
  "tenant_id": "tenant-a"
}
~~~

Spring Security mặc định không mặc nhiên chuyển `roles` và `tenant_id` thành quyền tenant admin. Việc ánh xạ custom roles phải có nguồn phân quyền tin cậy và hợp đồng rõ; tenant ID vẫn cần membership/ownership check.

## 8. Opaque token Resource Server vẫn dùng `authorizeExchange`

Điều kiện HTTP authorization không phụ thuộc token là JWT hay opaque. Khác biệt nằm ở **cách xác thực token**.

JWT:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(Customizer.withDefaults()))
~~~

Opaque:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(Customizer.withDefaults()))
~~~

Với opaque token, Spring Security Reactive sử dụng `ReactiveOpaqueTokenIntrospector` để hỏi introspection endpoint tin cậy. Khi token active và scope được trả về đúng contract, authorities có thể có dạng `SCOPE_orders.read` như JWT.

Ví dụ opaque configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: "${INTROSPECTION_CLIENT_SECRET}"
~~~

Không đưa client secret vào source code/log. Nếu xây custom `ReactiveOpaqueTokenIntrospector`, cần đảm bảo **không trả authenticated principal cho token inactive**, và không map arbitrary profile fields thành admin authority.

**Tóm lại:** `authorizeExchange` tiêu thụ `Authentication`/`GrantedAuthority` mà Reactive authentication pipeline tạo. Nó không tự xác minh chữ ký JWT hoặc gọi introspection.

## 9. `SecurityWebFilterChain` là phạm vi của `authorizeExchange`

Một request trước hết phải khớp **security chain** đã được cấu hình. Với nhiều `SecurityWebFilterChain`, `securityMatcher` chọn chain, sau đó `authorizeExchange` chọn rule **trong chain đó**.

~~~text
Incoming ServerWebExchange
          |
          v
WebFilterChainProxy
          |
          +-- Chọn SecurityWebFilterChain đầu tiên khớp
                    |
                    +-- securityMatcher("/api/**")?
                    |
                    v
              authorizeExchange rules
                    |
                    v
              authenticated/authorized?
~~~

### 9.1. Ví dụ nhiều chains

Ứng dụng có:

- `/api/**`: JWT bearer Resource Server, stateless API.
- `/web/**` và các route khác: web login hoặc một chính sách riêng.
- Một số endpoint vận hành/health được mở có chủ đích.

~~~java
package com.example.shop.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Configuration
@EnableWebFluxSecurity
public class MultiChainSecurityConfig {

    @Bean
    @Order(1)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/public/**")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/actuator/health").permitAll()
                .anyExchange().denyAll())
            .build();
    }
}
~~~

Đây là **ví dụ tách policy**, không khai báo web login. Nếu ứng dụng có OAuth2/OIDC browser login, fallback chain phải được thiết kế thêm flow login, state, CSRF và callback phù hợp, thay vì `denyAll()` mọi thứ.

### 9.2. Khác biệt sống còn giữa hai matcher

- `securityMatcher(...)`: exchange thuộc **chain** này không?
- `pathMatchers(...)` trong `authorizeExchange`: exchange trong chain cần **authorization rule** nào?

Nếu `apiChain` chỉ khớp `/api/**`, thì `.anyExchange().denyAll()` bên trong **không** bảo vệ `/management/**`. Phải có chain/fallback khác phù hợp.

### 9.3. Nếu không có chain nào khớp

Trong Spring Security, một request không khớp bất kỳ `SecurityWebFilterChain` nào có thể **không đi qua security WebFilters**. Đây là một rủi ro cấu hình nghiêm trọng.

Với nhiều chain, hãy kiểm tra mọi route nhạy cảm được bao phủ, bao gồm error, actuator, static content, WebSocket handshake nếu có, và những URL qua proxy.

### 9.4. Thứ tự `@Order`

`@Order(1)` được xét trước `@Order(2)`. Nếu một chain tổng quát khớp mọi request được đặt trước chain API, chain API có thể **không được chọn**. Vì vậy phải kiểm thử chain order, không chỉ rule order.

## 10. `matchers(ServerWebExchangeMatcher)` cho trường hợp nâng cao

`pathMatchers` xử lý nhiều case đơn giản. Nếu cần phân loại exchange theo tiêu chí khác, Spring Security có abstraction:

~~~java
ServerWebExchangeMatcher
~~~

và factory:

~~~java
ServerWebExchangeMatchers.pathMatchers(...)
ServerWebExchangeMatchers.anyExchange()
ServerWebExchangeMatchers.matchers(...)
~~~

Ví dụ custom matcher dựa trên path và HTTP method dùng factory:

~~~java
import org.springframework.http.HttpMethod;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatcher;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

ServerWebExchangeMatcher reportsGet =
    ServerWebExchangeMatchers.pathMatchers(
        HttpMethod.GET,
        "/api/reports/**"
    );
~~~

Đưa vào DSL:

~~~java
.authorizeExchange(exchanges -> exchanges
    .matchers(reportsGet)
        .hasAuthority("SCOPE_reports.read")
    .anyExchange().denyAll()
)
~~~

**Custom matcher quyết định *request nào* được áp dụng policy**, không tự bảo đảm người gọi có quyền. Dữ liệu do client tự gửi vẫn phải được xem như target hoặc input untrusted.

### 10.1. Match header, query và protocol requirements

Một tổ chức có thể muốn áp dụng policy riêng khi request có header xác định loại client, ví dụ:

~~~text
X-Client-Type: mobile
~~~

Nhưng header do client tự gửi **không đủ để cấp role**. Nó có thể là tiêu chí phân luồng, nhưng entitlement phải đến từ token đã xác thực hoặc policy server có thẩm quyền.

Nếu dùng header để điều chỉnh mức quyền, phải phân tích liệu header đó có thể bị caller giả mạo hay không. Tránh kiểu:

~~~text
header X-Role=ADMIN -> permitAll
~~~

vì đây là privilege escalation.

### 10.2. Path variables cần được kiểm tra trong authorization logic

Có thể viết custom authorization cần `tenantId`:

~~~java
.pathMatchers(
    HttpMethod.GET,
    "/api/tenants/{tenantId}/orders/**"
).access(tenantPolicyManager)
~~~

`tenantPolicyManager` có thể đọc `AuthorizationContext#getVariables()`. Nhưng tên tenant trong URL chỉ xác định **đối tượng yêu cầu**, không chứng minh user thuộc tenant.

## 11. Custom ReactiveAuthorizationManager cho WebFlux

Khi policy phụ thuộc dữ liệu ngoài authentication như tenant membership, API có thể dùng:

~~~java
ReactiveAuthorizationManager<AuthorizationContext>
~~~

khác với Servlet `AuthorizationManager<RequestAuthorizationContext>`.

### 11.1. Contract

Với Spring Security 6.4+/7.x, abstraction có phương thức:

~~~java
Mono<AuthorizationResult> authorize(
    Mono<Authentication> authentication,
    AuthorizationContext context
);
~~~

Đây là kiểu API rút gọn để giải thích. `authentication` là **`Mono<Authentication>`**; không phải `Supplier<Authentication>` như ví dụ Servlet hiện đại. `AuthorizationContext` có thể truy cập:

~~~java
context.getExchange();
context.getVariables();
~~~

`AuthorizationDecision` là một implementation của `AuthorizationResult`:

~~~java
new AuthorizationDecision(true)  // allow
new AuthorizationDecision(false) // deny
~~~

Ở các Spring Security version cũ hơn, bạn có thể thấy `check(Mono<Authentication>, T)` với `Mono<AuthorizationDecision>`. Phương thức `check` đã bị deprecated trong các version 6.4+/7.x theo Javadoc. Khi học từ blog cũ cần đối chiếu phiên bản.

**Không trả `Mono.empty()` rồi mặc định hiểu đó là DENY trong mọi tổ hợp.** Empty có thể mang ý nghĩa abstain (không quyết định), và enforcement/composition có chính sách riêng. Với quyền nhạy cảm nên trả grant/deny rõ ràng.

### 11.2. Ví dụ quyền đọc order theo tenant

Yêu cầu:

> Chỉ cho `GET /api/tenants/{tenantId}/orders/**` khi user có scope `orders.read` **và** có membership được phép đọc order tại tenant được yêu cầu.

Định nghĩa nguồn membership reactive:

~~~java
package com.example.orders.security;

import reactor.core.publisher.Mono;

public interface ReactiveTenantMembershipPolicy {

    Mono<Boolean> canReadOrders(
        String issuer,
        String subject,
        String tenantId
    );
}
~~~

Implementation của interface phải dùng nguồn dữ liệu có thẩm quyền: reactive repository, non-blocking API hoặc một adapter đã thiết kế đúng concurrency. Trả `true` vô điều kiện không phải implementation an toàn.

### 11.3. Custom manager không chặn event loop

~~~java
package com.example.orders.security;

import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.web.server.authorization.AuthorizationContext;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
public final class TenantOrdersReadAuthorizationManager
        implements ReactiveAuthorizationManager<AuthorizationContext> {

    private final ReactiveTenantMembershipPolicy memberships;

    public TenantOrdersReadAuthorizationManager(
            ReactiveTenantMembershipPolicy memberships) {
        this.memberships = memberships;
    }

    @Override
    public Mono<AuthorizationResult> authorize(
            Mono<Authentication> authentication,
            AuthorizationContext context) {

        Object rawTenant = context.getVariables().get("tenantId");

        if (!(rawTenant instanceof String tenantId)
                || tenantId.isBlank()) {
            return Mono.just(new AuthorizationDecision(false));
        }

        return authentication
            .filter(Authentication::isAuthenticated)
            .ofType(JwtAuthenticationToken.class)
            .flatMap(jwtAuthentication -> {
                boolean hasScope = jwtAuthentication
                    .getAuthorities().stream()
                    .anyMatch(authority -> "SCOPE_orders.read"
                        .equals(authority.getAuthority()));

                if (!hasScope) {
                    return Mono.just(
                        (AuthorizationResult) new AuthorizationDecision(false));
                }

                Jwt jwt = jwtAuthentication.getToken();
                String issuer = jwt.getIssuer() == null
                    ? null : jwt.getIssuer().toString();
                String subject = jwt.getSubject();

                if (issuer == null || subject == null
                        || subject.isBlank()) {
                    return Mono.just(
                        (AuthorizationResult) new AuthorizationDecision(false));
                }

                return memberships
                    .canReadOrders(issuer, subject, tenantId)
                    .defaultIfEmpty(false)
                    .map(allowed ->
                        (AuthorizationResult) new AuthorizationDecision(allowed));
            })
            // Không có authentication hợp lệ -> DENY.
            .defaultIfEmpty(new AuthorizationDecision(false));
    }
}
~~~

Đoạn code cố ý **không gọi `.block()`** và cũng không dùng JDBC blocking trực tiếp trong `flatMap`. Nó chỉ làm việc với `Mono` từ reactive policy source.

**Những gì manager làm:**

1. Lấy tenant ID do path matcher trích xuất.
2. Từ chối nếu thiếu tenant ID.
3. Nhận `JwtAuthenticationToken` đã được Resource Server xác thực.
4. Kiểm tra `SCOPE_orders.read`.
5. Lấy `(iss, sub)` từ JWT đã xác minh để phân biệt identity.
6. Hỏi nguồn membership có thẩm quyền bằng `Mono<Boolean>`.
7. Trả `AuthorizationDecision` rõ ràng.
8. Không tự thêm authority từ header, query, email hoặc display name.

### 11.4. Vấn đề lỗi database/policy service

Đoạn code trên để lỗi từ membership source **propagate**. Nếu một reactive repository thất bại, manager **không trả grant**; request không được tiếp tục thực hiện. Response có thể là 5xx/503 tùy error handling, không nhất thiết là 403.

Một số hệ thống muốn biến lỗi policy service thành deny theo quy định fail-closed; nếu làm thế cần ghi telemetry rõ để không nhầm mất kết nối DB với user không có quyền.

**Không dùng**:

~~~java
.onErrorReturn(new AuthorizationDecision(true))
~~~

để “giảm lỗi 403” khi DB không sẵn sàng. Đó là fail-open và có thể cho phép thao tác trái phép.

### 11.5. Đăng ký manager trong `authorizeExchange`

~~~java
@Bean
SecurityWebFilterChain apiChain(
        ServerHttpSecurity http,
        TenantOrdersReadAuthorizationManager tenantRead) {

    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers(
                HttpMethod.GET,
                "/api/tenants/{tenantId}/orders/**")
                .access(tenantRead)

            .pathMatchers(HttpMethod.POST, "/api/orders/**")
                .hasAuthority("SCOPE_orders.write")

            .anyExchange().denyAll()
        )
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}
~~~

Ví dụ method bean trên chỉ trích đoạn; imports dùng `ServerHttpSecurity`, `SecurityWebFilterChain`, `HttpMethod`, `Customizer`, `Bean`.

Chú ý **thứ tự:** nếu `.pathMatchers("/api/**").authenticated()` đứng trước `tenantRead`, manager sẽ không được gọi cho đường dẫn tenant đã khớp rule tổng quát.

### 11.6. Không dùng HTTP manager thay object-level authorization

Nếu `tenantId=tenant-a` và `orderId=order-from-tenant-b`, manager có thể xác nhận subject thuộc tenant A. Nhưng nó **không chứng minh order ID thuộc tenant A**.

Tầng service phải truy vấn ràng buộc tenant:

~~~java
// Pseudocode domain: repository do ứng dụng triển khai.
return orderRepository
    .findByIdAndTenantId(orderId, tenantId)
    .switchIfEmpty(Mono.error(new NotFoundException()))
    .flatMap(order -> orderPolicy.canReadOrder(actor, order)
        .flatMap(allowed -> allowed
            ? Mono.just(order)
            : Mono.error(new AccessDeniedException("Forbidden"))));
~~~

`orderRepository`, `orderPolicy`, `actor` và `NotFoundException` là thành phần nghiệp vụ minh họa, không phải Spring Security API có sẵn.

Nếu chỉ kiểm tra `tenantId` của request mà query order bằng ID không có tenant predicate, API dễ mắc lỗi **Broken Object Level Authorization (BOLA/IDOR)**.

## 12. Đừng gọi API blocking trong reactive authorization

WebFlux dùng reactive execution model. Một custom manager có code:

~~~java
// SAI trong reactive event loop nếu đây là JDBC blocking call.
boolean allowed = jdbcTemplate.queryForObject(
    "...", Boolean.class);
return Mono.just(new AuthorizationDecision(allowed));
~~~

có thể **block event-loop thread**, giảm throughput hoặc tạo đuôi latency lớn khi traffic tăng.

Các lựa chọn:

- Dùng R2DBC hoặc reactive repository nếu phù hợp.
- Dùng `WebClient` khi gọi authorization service bên ngoài qua HTTP non-blocking.
- Nếu bắt buộc dùng một blocking SDK, cân nhắc cô lập sang scheduler phù hợp qua `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` và giám sát giới hạn tài nguyên.
- Không tự gọi `.block()` để lấy kết quả Mono trong manager/handler.

Ví dụ adapter cho blocking policy chỉ mang tính chuyển tiếp:

~~~java
public Mono<Boolean> canReadOrders(
        String issuer, String subject, String tenantId) {
    return Mono.fromCallable(() ->
            blockingMembershipService.canReadOrders(
                issuer, subject, tenantId))
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

`blockingMembershipService` là dependency nghiệp vụ giả định; cần import `reactor.core.scheduler.Schedulers`. `boundedElastic` không biến một thư viện blocking thành non-blocking thực sự; nó chỉ tách phần blocking ra khỏi một số thread reactive quan trọng. Phải kiểm soát timeouts, connection pool và tải hệ thống.

### 12.1. Reactor Context và Authentication

Trong WebFlux, authentication được truyền qua **Reactor Context**, không nên giả định một `ThreadLocal` luôn gắn đúng request khi execution đổi thread.

Ví dụ lấy authentication trong reactive service:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

Mono<String> currentPrincipalName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName());
}
~~~

Đây là ví dụ đọc name, không phải cách thay việc kiểm tra quyền nghiệp vụ. Không tự dùng static variable giữ principal giữa requests.

## 13. Custom WebFilter không thay `authorizeExchange` trong mọi trường hợp

Spring Security WebFlux hỗ trợ `WebFilter` tùy chỉnh. Nhưng một custom filter tự đọc header rồi trả 403 có thể:

- Chạy ở thời điểm trước authentication nên chưa có identity tin cậy.
- Không tương thích với reactive error flow.
- Bỏ qua matcher/authorization manager đã thiết kế.
- Dễ tạo duplicate policy và khó kiểm thử.
- Vô tình log bearer token hoặc đọc body streaming không đúng cách.

Nếu mục tiêu là **quy tắc phân quyền HTTP**, ưu tiên `authorizeExchange` và `.access(ReactiveAuthorizationManager)`.

Nếu mục tiêu là **business transaction/ownership**, đặt policy trong service/method security. Custom filter nên dành cho những trách nhiệm thực sự thuộc filter layer, không phải mọi rule đều phải viết lại filter.

## 14. Kết hợp HTTP authorization với Reactive Method Security

`authorizeExchange` kiểm tra exchange khi request vào API. Nhưng một service method có thể được gọi từ:

- HTTP handler.
- Background job.
- Message consumer.
- Một reactive pipeline khác.

Nếu chính sách nghiệp vụ phải được áp dụng nhất quán, có thể thêm **Reactive Method Security**.

### 14.1. Bật phương thức reactive

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
public class ReactiveMethodSecurityConfig {
}
~~~

### 14.2. Bảo vệ service với scope

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class OrderQueryService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public Mono<OrderDto> getOrder(String orderId) {
        return loadAuthorizedOrder(orderId);
    }
}
~~~

`OrderDto` và `loadAuthorizedOrder(...)` là những thành phần domain minh họa. Rule scope không thay thế logic kiểm tra owner/tenant bên trong service.

### 14.3. Business policy reactive

Một policy phức tạp có thể trả `Mono<Boolean>` hoặc một decision object tùy integration method security:

~~~text
@PreAuthorize -> policy bean
              -> Mono<Boolean> quyền hiện tại
              -> continue hoặc AccessDenied
~~~

Khi dùng SpEL, cần tham khảo signature hỗ trợ trong version Spring Security đang chạy và bảo đảm method kết quả reactive phù hợp. Tránh lời gọi blocking để trả `boolean` tức thời từ một DB async.

### 14.4. Chú ý proxy/self-invocation và side effects

Method security thường dùng AOP proxy. Nếu một method trong cùng class gọi trực tiếp method khác được bảo vệ, lời gọi có thể **không đi qua proxy**.

Với hoạt động có side effects, như refund hoặc duyệt thanh toán, không đặt toàn bộ bảo vệ vào `@PostAuthorize` hoặc một bước kiểm tra trước khi trạng thái có thể thay đổi. Cần kiểm tra invariant trong transaction/reactive transactional boundary và chống TOCTOU.

## 15. CORS preflight và `authorizeExchange`

Khi browser SPA gọi API khác origin với bearer header, thường có preflight:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

Preflight thường **không mang access token**. Nếu authentication filter coi nó như request nghiệp vụ cần token, browser có thể báo lỗi CORS dù API thực sự cho phép GET với token hợp lệ.

Spring Security và Spring WebFlux cần CORS configuration được áp dụng đúng vị trí. `authorizeExchange` không tự phát các header như `Access-Control-Allow-Origin`.

### 15.1. Ví dụ CorsWebFilter

~~~java
package com.example.orders.security;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsWebFilter;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
public class ApiCorsConfig {

    @Bean
    CorsWebFilter corsWebFilter() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(
            List.of("GET", "POST", "PUT", "PATCH", "DELETE"));
        cors.setAllowedHeaders(
            List.of("Authorization", "Content-Type"));
        cors.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();

        source.registerCorsConfiguration("/api/**", cors);
        return new CorsWebFilter(source);
    }
}
~~~

Ví dụ này giả định một SPA origin được cho phép. Nếu ứng dụng đã có CORS configuration qua WebFlux hoặc Spring Security, **không đăng ký nhiều bộ CORS filters một cách vô ý**, và cần xác định thứ tự xử lý với security.

### 15.2. CORS không phải authorization

CORS giới hạn hành vi trình duyệt khi đọc response cross-origin. Nó **không ngăn** HTTP client trực tiếp hoặc một client không phải browser gọi API.

Không dùng `Origin` hoặc `Access-Control-Allow-Origin` như bằng chứng user có scope `orders.write`.

### 15.3. Không mở `OPTIONS /**` bừa bãi

Một rule như:

~~~java
.pathMatchers(HttpMethod.OPTIONS, "/**").permitAll()
~~~

có thể được dùng theo kiến trúc nhưng quá rộng nếu không đánh giá. Nó cũng **không tự bảo đảm** CORS headers đúng. Ưu tiên cấu hình CORS xử lý preflight đúng nguồn/headers/methods trước khi thêm authorization exceptions.

## 16. CSRF trong WebFlux Resource Server

Trong Spring Security WebFlux, CSRF protection thường được bật mặc định ở một số cấu hình cơ bản và có thể dùng `WebSessionServerCsrfTokenRepository`.

Nếu API chỉ chấp nhận bearer token trong `Authorization` header do client chủ động gắn, không dùng credential tự động đính kèm từ browser, mô hình CSRF thường khác browser session login. Khi đó có thể cân nhắc:

~~~java
.csrf(ServerHttpSecurity.CsrfSpec::disable)
~~~

hoặc:

~~~java
.csrf(csrf -> csrf.disable())
~~~

**Đây không phải mặc định nên sao chép cho mọi ứng dụng WebFlux/OIDC**. Nếu backend sử dụng cookie đăng nhập, BFF, session hoặc credential khác browser tự gửi, CSRF vẫn cần được xem xét dù có JWT hoặc kiến trúc reactive.

### 16.1. Lỗi 403 có thể không liên quan `authorizeExchange`

Một request POST không có CSRF token trong ứng dụng có CSRF bật có thể nhận **403** trước khi logic scope được dùng.

Nếu đang test POST scope, cần biết:

- CSRF có bật hay không?
- Endpoint sử dụng bearer-only hay session cookie?
- Request gửi CSRF token đúng chưa?
- Status 403 đến từ CSRF WebFilter, HTTP authorization hay service policy?

Không tắt CSRF chỉ để làm test qua khi ứng dụng thực tế nhận cookie.

## 17. Phân biệt 401 và 403

| Trường hợp | Kết quả thường gặp | Giải thích |
|---|---|---|
| Không token gọi public GET | 200 nếu handler thành công | `permitAll()` |
| Không token gọi `/api/me` | 401 | Chưa authenticated |
| JWT sai chữ ký/issuer/audience/expiry | 401 | Authentication failure |
| JWT hợp lệ không có scope gọi `/api/me` | 200 nếu contract cho phép | Chỉ yêu cầu authenticated |
| JWT chỉ có `orders.read`, gọi GET orders | 200 nếu business policy cho phép | Có quyền HTTP đọc |
| JWT chỉ có `orders.read`, gọi POST orders | 403 | Thiếu `orders.write` |
| JWT chỉ có `orders.write`, gọi GET orders | 403 nếu không có read | Write không tự bao hàm read |
| JWT có scope đọc nhưng query order tenant khác | 403/404 theo API policy | Object-level denial |
| Unknown path rơi vào `denyAll` | Thường 403 nếu đã authenticated | Route chưa được cho phép |
| POST trong ứng dụng CSRF bật, thiếu token | Thường 403 | CSRF filter |
| Public GET có header bearer invalid | Có thể 401 | Authentication filter xử lý credential sai |

Các status là hành vi **thường gặp**; exception handlers, WebFilter order, gateway, route availability và các cơ chế login có thể thay đổi response cụ thể.

### 17.1. Bearer challenge

RFC 6750 quy định header `WWW-Authenticate` để mô tả bearer authentication failure:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Thiếu scope có thể được thông báo bằng:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Chính xác format/realm/scope/error description tùy Spring Security và custom handlers. Không bao giờ echo nguyên bearer token hoặc secret trong response lỗi.

### 17.2. 403 không tự chứng minh token không hợp lệ

Nếu token đã xác thực nhưng rule `SCOPE_orders.write` không có authority đó, trả 403 là điều đúng. Không “sửa” bằng cách tự thêm write scope vào `ReactiveJwtAuthenticationConverter` khi AS không cấp.

## 18. Ví dụ Controller Reactive khớp với policy

Một controller minh họa:

~~~java
package com.example.orders.api;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    @GetMapping("/api/public/ping")
    public Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("status", "ok"));
    }

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me(
            @AuthenticationPrincipal Jwt jwt) {
        return Mono.just(Map.of("subject", jwt.getSubject()));
    }

    @GetMapping("/api/orders")
    public Mono<Map<String, String>> listOrders() {
        return Mono.just(Map.of("action", "read"));
    }

    @PostMapping("/api/orders")
    public Mono<Map<String, String>> createOrder() {
        return Mono.just(Map.of("action", "write"));
    }
}
~~~

Đây là ví dụ **JWT Resource Server**, trong đó principal được inject dưới dạng `Jwt`. Nếu dùng opaque token, loại principal thường khác. Các handler `read`/`write` chỉ minh họa kết quả, không thao tác database và chưa thể hiện ownership/tenant policy.

`Map.of(...)` không chấp nhận null; ví dụ giả định JWT có `sub` đúng hợp đồng. Trong API thực tế, thiết kế riêng DTO và tránh trả claim không cần thiết.

### 18.1. HTTP requests minh họa

Không token:

~~~bash
curl -i https://api.example.com/api/public/ping
~~~

Token có scope đọc:

~~~bash
curl -i \
  -H "Authorization: Bearer $READ_TOKEN" \
  https://api.example.com/api/orders
~~~

Cố POST với token chỉ có quyền đọc:

~~~bash
curl -i -X POST \
  -H "Authorization: Bearer $READ_TOKEN" \
  https://api.example.com/api/orders
~~~

Token có scope ghi:

~~~bash
curl -i -X POST \
  -H "Authorization: Bearer $WRITE_TOKEN" \
  https://api.example.com/api/orders
~~~

Các URL/token là minh họa. Không để bearer token thật xuất hiện trong shell history/log/ticket được chia sẻ.

## 19. WebTestClient là công cụ test chính cho WebFlux

Với Servlet MVC có `MockMvc`, nhưng với Reactive WebFlux nên dùng **`WebTestClient`** và Spring Security reactive test support.

Các cách test gồm:

- `@SpringBootTest` + `@AutoConfigureWebTestClient`.
- `WebTestClient.bindToApplicationContext(context).apply(springSecurity())` cho context test tùy chỉnh.
- `mockJwt()` để dựng authenticated JWT principal.
- `mockOpaqueToken()` cho opaque authentication.
- `mockUser()` khi mục tiêu là authorization chung, không phụ thuộc token format.
- Integration test với `ReactiveJwtDecoder` thật/stub được kiểm soát để kiểm tra signature/claim validation.

### 19.1. Test policy HTTP với `mockJwt()`

~~~java
package com.example.orders.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveHttpAuthorizationTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicGetNeedsNoToken() {
        client.get().uri("/api/public/ping")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void meNeedsAuthentication() {
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void meAcceptsMockAuthenticatedJwt() {
        client.mutateWith(
                mockJwt().jwt(jwt -> jwt.subject("user-42")))
            .get().uri("/api/me")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void readScopeCanGetOrders() {
        client.mutateWith(mockJwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")))
            .get().uri("/api/orders")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void readScopeCannotPostOrders() {
        client.mutateWith(mockJwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")))
            .post().uri("/api/orders")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void writeScopeCanPostOrders() {
        client.mutateWith(mockJwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.write")))
            .post().uri("/api/orders")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void unknownRouteIsDenied() {
        client.mutateWith(mockJwt())
            .get().uri("/api/not-configured")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

**Điều kiện của ví dụ:** có `DemoController` phần trước, chain JWT được cấu hình như phần 3, business logic không phát sinh lỗi khác và CSRF được cấu hình phù hợp cho bearer-only POST test. Nếu CSRF vẫn bật và yêu cầu token cho POST, một test có thể nhận 403 vì CSRF thay vì vì thiếu scope; cần test phân biệt hai nguyên nhân.

### 19.2. `mockJwt()` không xác minh chữ ký

`mockJwt()` tạo authentication giả để tập trung test **authorization rules**. Khi chỉ định:

~~~java
mockJwt().authorities(
    new SimpleGrantedAuthority("SCOPE_orders.read")
)
~~~

test **đã gắn authority trực tiếp**, có thể bỏ qua converter production và `ReactiveJwtDecoder` thật.

Do đó test này **không chứng minh**:

- JWT có chữ ký JWS hợp lệ.
- JWKS được tải từ issuer đúng.
- Claim `iss`, `aud`, `exp`, `nbf` được kiểm tra.
- Scope converter của production tạo authorities đúng từ claim.
- Chính sách token type và key/alg an toàn.

Hãy bổ sung integration tests cho decoder, issuer/audience validation, mapping claim và authentication flow.

### 19.3. Test opaque token

Khi Resource Server dùng introspection:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOpaqueToken;

client.mutateWith(mockOpaqueToken()
        .authorities(new SimpleGrantedAuthority("SCOPE_orders.read")))
    .get().uri("/api/orders")
    .exchange()
    .expectStatus().isOk();
~~~

Tương tự `mockJwt`, test này có thể **bỏ qua network introspection thực**. Nó chứng minh rule HTTP với một authentication giả lập, không chứng minh AS trả `active=true`.

## 20. Test custom `ReactiveAuthorizationManager` bằng StepVerifier

Một manager trả `Mono<AuthorizationResult>` có thể test đơn lẻ bằng Reactor Test.

Ví dụ tạo context giả bằng `MockServerWebExchange`:

~~~java
package com.example.orders.security;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.web.server.authorization.AuthorizationContext;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class TenantOrdersReadAuthorizationManagerTest {

    @Test
    void missingTenantIdIsDenied() {
        ReactiveTenantMembershipPolicy memberships =
            mock(ReactiveTenantMembershipPolicy.class);

        var manager =
            new TenantOrdersReadAuthorizationManager(memberships);

        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/api/tenants/tenant-a/orders"));

        // Cố ý để URI template variables rỗng.
        var context = new AuthorizationContext(
            exchange, Map.of());

        Mono<AuthorizationResult> result =
            manager.authorize(Mono.empty(), context);

        StepVerifier.create(result)
            .expectNextMatches(decision -> !decision.isGranted())
            .verifyComplete();
    }
}
~~~

Test này kiểm tra trường hợp thiếu `tenantId` thì deny. Để test allow cần dựng `JwtAuthenticationToken` có scope và issuer/subject cùng stub reactive membership trả `Mono.just(true)`.

### 20.1. Một test cho phép theo membership

~~~java
@Test
void tenantMemberWithReadScopeIsAllowed() {
    ReactiveTenantMembershipPolicy memberships =
        mock(ReactiveTenantMembershipPolicy.class);

    when(memberships.canReadOrders(
        "https://idp.example.com/realms/shop",
        "user-42",
        "tenant-a"
    )).thenReturn(Mono.just(true));

    Jwt jwt = Jwt.withTokenValue("unit-test-only")
        .header("alg", "RS256")
        .claim("iss", "https://idp.example.com/realms/shop")
        .claim("sub", "user-42")
        .build();

    var authentication = new JwtAuthenticationToken(
        jwt, List.of(new SimpleGrantedAuthority("SCOPE_orders.read"))
    );

    var exchange = MockServerWebExchange.from(
        MockServerHttpRequest.get("/api/tenants/tenant-a/orders"));

    var context = new AuthorizationContext(
        exchange, Map.of("tenantId", "tenant-a"));

    var manager =
        new TenantOrdersReadAuthorizationManager(memberships);

    StepVerifier.create(
        manager.authorize(Mono.just(authentication), context))
        .expectNextMatches(AuthorizationResult::isGranted)
        .verifyComplete();
}
~~~

Đoạn thứ hai là **một test method bổ sung trong class test**, cần các import tương ứng: `java.util.List`, `Jwt`, `JwtAuthenticationToken`, `SimpleGrantedAuthority` cùng static import Mockito. `Jwt.withTokenValue` tạo đối tượng mock, không xác minh signature.

### 20.2. Các test âm tính cần có

| Tình huống | Kết quả cần bảo đảm |
|---|---|
| Authentication Mono trống | Deny |
| Authentication anonymous/không phải JWT | Deny trong manager chỉ nhận JWT |
| Token hợp lệ nhưng thiếu `orders.read` | Deny |
| Tenant ID rỗng | Deny |
| Matchers không trích xuất tenant ID | Deny |
| Subject/issuer thiếu | Deny |
| Subject thuộc tenant A nhưng gọi B | Deny |
| Membership repository trả false | Deny |
| Membership repository trả `Mono.empty()` | Deny nếu đó là policy |
| Membership repository lỗi | Không grant; telemetry lỗi rõ |
| Hai issuer cùng `sub` | Không trộn identity |
| User thuộc tenant A nhưng order thuộc B | Deny tại service |
| POST chỉ có scope đọc | Deny |
| Rule tổng quát đứng trước manager | Test phải phát hiện misconfiguration |
| Request nằm ngoài API security chain | Không bypass policy |

Các test này góp phần chứng minh **fail closed** của toàn bộ đường thực thi, không chỉ happy path.

## 21. Hạn chế của test security context giả

Một test dùng `mockJwt()` có thể cho request qua bằng authority được gắn thủ công, trong khi production converter thật lại không đọc đúng `scope` hoặc `scp`.

Vì vậy nên có bốn lớp test:

1. **Decoder/authentication tests:** JWT được ký bằng test key, issuer/audience/time đúng và sai.
2. **Converter tests:** claim `scope`/`scp` hoặc roles được ánh xạ thành authorities đúng.
3. **WebTestClient authorization tests:** `authorizeExchange` chọn đúng rule và status.
4. **Service business tests:** tenant/ownership/ACL/status của object được bảo vệ.

Một token hợp lệ **không** tự chứng minh quyền trên tài nguyên; WebTestClient success **không** tự chứng minh JWT production được verify đúng.

## 22. Endpoint public, exception handling và security headers

Một rule:

~~~java
.pathMatchers("/api/public/**").permitAll()
~~~

không đồng nghĩa exchange được bỏ qua `WebFilterChainProxy`. Những filter khác vẫn có thể cung cấp security headers, exception handling, CORS, CSRF hoặc authentication khi client gửi credential.

Không dùng cách bỏ qua mọi security filter cho public resources nếu còn cần headers/protection. Với WebFlux, cần kiểm tra `securityMatcher` và filter chain đang áp dụng, không nhầm với một `permitAll` authorization rule.

Nếu Resource Server có custom `ServerAuthenticationEntryPoint` hoặc `ServerAccessDeniedHandler`, có thể tùy chỉnh JSON response của lỗi 401/403 mà không thay đổi quyết định authorization. Đừng biến handler của 403 thành một nơi cấp thêm authorities.

## 23. Object-level authorization vẫn thuộc service

Ví dụ:

~~~http
GET /api/orders/order-123 HTTP/1.1
Authorization: Bearer <token-with-orders.read>
~~~

`authorizeExchange` xác định token có `SCOPE_orders.read`, nhưng không biết `order-123` thuộc ai.

Bảo vệ đúng có thể gồm:

~~~text
HTTP:
  valid token for orders-api
  AND SCOPE_orders.read
          |
          v
Service:
  order exists?
  AND correct tenant?
  AND actor is owner or authorized staff?
  AND order data accessible under current policy?
          |
          v
Return only allowed fields
~~~

Một reactive service nên tránh load toàn bộ order rồi mới lọc ngoài database nếu dễ rò dữ liệu. Có thể dùng repository query ràng buộc `ownerId`, `tenantId` hoặc chính sách cần thiết.

Ví dụ:

~~~java
return orderRepository
    .findByIdAndTenantId(orderId, tenantId)
    .switchIfEmpty(Mono.error(new NotFoundException()))
    .flatMap(order -> accessPolicy.canReadOrder(actor, order)
        .flatMap(allowed -> allowed
            ? Mono.just(toDto(order))
            : Mono.error(new AccessDeniedException("Forbidden"))));
~~~

`actor`, `NotFoundException`, `toDto` và repository là domain abstractions. Không có API Spring Security tự động hiểu mọi tenant/owner chỉ từ scope.

### 23.1. TOCTOU trong operation có side effects

Nếu policy phụ thuộc “order chưa được refund”, kiểm tra một lần ở HTTP authorization filter có thể bị lỗi **time-of-check/time-of-use** khi trạng thái thay đổi trước lúc ghi.

Giải pháp phải có transaction, conditional update, versioning/locking hoặc idempotency policy phù hợp. Custom reactive authorization có thể chặn sớm nhưng không thay thế invariant tại database.

## 24. Debug 401/403 khi chuyển từ MVC sang WebFlux

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
|---|---|---|
| Không tìm thấy `.authorizeHttpRequests(...)` | Đang dùng WebFlux | Dùng `authorizeExchange` |
| Bean `SecurityFilterChain` không áp dụng | Sai stack/bean type | Dùng `SecurityWebFilterChain` |
| `JwtDecoder` không được injection | WebFlux cần `ReactiveJwtDecoder` | Kiểm tra dependency và bean |
| GET public không token bị 401 | Matcher không khớp, chain sai hoặc filter khác | Kiểm tra path, chain, method |
| GET public gửi token sai bị 401 | Authentication filter đã xử lý invalid Bearer | Thử không Authorization header |
| JWT hợp lệ nhưng GET orders 403 | Thiếu `SCOPE_orders.read` hoặc mapping sai | Xem authorities an toàn |
| GET orders được nhưng POST 403 | Thiếu `SCOPE_orders.write`, hoặc CSRF | Phân biệt nguồn denial |
| Endpoint admin mở công khai | `permitAll` matcher rộng đứng trước | Sửa matcher order |
| API scope manager không chạy | `authenticated` matcher rộng đứng trước | Sửa rule order |
| URL `/api/**` không qua API chain | `securityMatcher`/order sai | Kiểm tra các chains |
| Token valid, resource tenant khác bị 200 | Object policy thiếu | Kiểm tra service query |
| Reactive manager bị treo | Blocking DB/SDK hoặc `.block()` | Dùng reactive source/isolated scheduler |
| Authorization context trống | URI variable không được matcher trích | Test matcher và fail closed |
| Test `mockJwt()` qua nhưng production 401 | Decoder/issuer/audience/signature khác | Thêm JWT integration test |
| WebFlux app tự chuyển sang Servlet | Có cả starters và auto-detection chọn MVC | Kiểm tra app type/config |
| `SecurityContextHolder.getContext()` không có identity ở callback khác thread | Dùng ThreadLocal không phù hợp Reactor pipeline | Dùng `ReactiveSecurityContextHolder` |

**Không sửa lỗi 403 bằng cách thêm scope/role tùy tiện** khi AS không cấp. Nếu converter sai format, sửa mapping dựa trên contract; nếu người dùng thực sự thiếu quyền, yêu cầu cấp quyền hợp lệ hoặc từ chối.

## 25. Thực hành xây chính sách theo nguyên tắc quyền tối thiểu

Một quy trình thiết kế endpoint:

1. **Phân loại endpoint:** public, authenticated, scope/role hoặc object-level policy.
2. **Xác định HTTP methods:** GET/HEAD/OPTIONS/POST/PUT/PATCH/DELETE có rule phù hợp.
3. **Đặt matcher cụ thể trước:** không để broad public/authenticated rule che scoped routes.
4. **Chọn fallback rõ:** thường `anyExchange().denyAll()` cho API cần kiểm soát chặt.
5. **Tách chain nếu cần:** API bearer và browser login có cơ chế state/CSRF khác.
6. **Chọn đúng token:** access token đúng issuer/audience, không dùng ID token làm API credential.
7. **Không tự suy ra authorities:** OAuth scope và role phải có nguồn tin cậy.
8. **Tách business authorization:** quyền tenant, owner và trạng thái ở service/domain.
9. **Giữ reactive non-blocking:** không gọi DB/HTTP blocking trong manager trên event loop.
10. **Viết test cho cả từ chối:** missing/expired token, thiếu scope, wrong tenant, matcher order, unknown routes.
11. **Không log credential:** token, client secret và dữ liệu PII không được lộ.
12. **Review mỗi khi thêm route:** không phụ thuộc vào “frontend không gọi endpoint này” như một lớp bảo mật.

### Ví dụ policy cho Refund API

~~~text
POST /api/refunds/{refundId}/approve

HTTP authorization:
  valid access token
  AND SCOPE_refunds.approve

Business authorization:
  actor thuộc merchant của refund
  AND actor được phân công phê duyệt
  AND actor khác người tạo request (nếu policy yêu cầu)
  AND amount nằm trong hạn mức
  AND refund đang pending
  AND thao tác ghi là atomic/idempotent
~~~

`authorizeExchange` nên bảo vệ lớp coarse-grained, còn những điều kiện stateful và object-specific ở business service/transaction.

## 26. Một số sai lầm cần tránh

**“`authorizeExchange` là alias của `authorizeHttpRequests`.”** Không. Chúng phục vụ hai stack khác nhau, với HTTP model và authorization manager type khác nhau.

**“`SecurityWebFilterChain` tương đương Servlet `SecurityFilterChain` ở code.”** Khái niệm tương tự nhưng API không thể thay thế trực tiếp.

**“`pathMatchers("/api/**").permitAll()` chỉ mở các GET.”** Sai. Nếu không chỉ định method, pattern có thể khớp mọi HTTP method.

**“Matcher mạnh hơn đặt sau sẽ override matcher trước.”** Sai. Spring Security xét theo thứ tự, rule khớp đầu tiên được sử dụng.

**“`authenticated()` đủ bảo vệ API cần scope.”** Không nếu API có entitlement riêng.

**“`hasRole("ADMIN")` kiểm tra `SCOPE_admin`.”** Không; thông thường nó kiểm tra `ROLE_ADMIN`.

**“Scope đọc tự cho phép ghi.”** Không. `orders.read` và `orders.write` khác nhau.

**“`anyExchange().denyAll()` trong `/api/**` chain bảo vệ mọi URL của ứng dụng.”** Không. Nó chỉ áp dụng exchange thuộc chain đó.

**“Token JWT được ký đúng thì mọi dữ liệu user đều được xem.”** Sai. Scope không thay object ownership.

**“Một custom manager có thể `.block()` vì chỉ là kiểm tra quyền.”** Không nên trên reactive event loop; blocking làm giảm hiệu năng và có nguy cơ deadlock/thread starvation.

**“Reactor Context và ThreadLocal luôn giống nhau.”** Sai. Reactive pipeline có thể đổi thread, nên dùng API context phù hợp.

**“CORS restriction thay thế authentication.”** Không. CORS là browser cross-origin policy.

**“`permitAll` sẽ bỏ qua invalid bearer token.”** Không đảm bảo. Authentication filter vẫn có thể kiểm tra token được gửi và trả 401.

**“WebTestClient `mockJwt()` chứng minh JWT signature production hợp lệ.”** Không. Đó là mock authentication.

**“Tắt CSRF luôn an toàn với WebFlux Resource Server.”** Không nếu browser gửi cookie/credential tự động.

## 27. Câu hỏi tự kiểm tra

**1.** WebFlux dùng DSL gì để khai báo HTTP authorization?

> `ServerHttpSecurity.authorizeExchange(...)` trong một `SecurityWebFilterChain`.

**2.** Ba rule `permitAll`, `authenticated`, `hasAuthority` khác nhau ở đâu?

> Public không cần authentication; authenticated yêu cầu principal hợp lệ; hasAuthority yêu cầu authority cụ thể đã được cấp.

**3.** Vì sao `.pathMatchers("/api/**").permitAll()` đứng đầu nguy hiểm?

> Vì nó có thể khớp các route private/admin trước rule chặt hơn.

**4.** JWT chứa `scope=orders.read` thường được chuyển thành authority nào?

> `SCOPE_orders.read`.

**5.** `hasRole("ORDERS_ADMIN")` thường kiểm tra authority gì?

> `ROLE_ORDERS_ADMIN`, không phải OAuth scope `orders.admin`.

**6.** `securityMatcher` và `pathMatchers` trong `authorizeExchange` khác nhau thế nào?

> `securityMatcher` chọn security chain; `pathMatchers` chọn authorization rule trong chain đã được chọn.

**7.** Một request không thuộc bất kỳ SecurityWebFilterChain nào có nguy cơ gì?

> Có thể không được các WebFilters bảo vệ; cần chain/fallback bao phủ rõ.

**8.** Custom HTTP manager reactive nhận authentication kiểu gì?

> `Mono<Authentication>`, cùng `AuthorizationContext`, và trả `Mono<AuthorizationResult>` trên API Spring Security mới.

**9.** Vì sao không gọi `JdbcTemplate` blocking trực tiếp trong manager reactive?

> Nó có thể block event loop. Nên dùng reactive repository/HTTP client hoặc cô lập blocking work qua scheduler phù hợp.

**10.** `tenantId` từ URL có chứng minh membership không?

> Không. Nó là target do client chọn; phải tra nguồn quyền có thẩm quyền.

**11.** Vì sao token có `SCOPE_orders.read` vẫn có thể bị từ chối khi đọc order?

> Business policy có thể yêu cầu đúng tenant, owner hoặc ACL của order đó.

**12.** Khi nào `mockJwt()` thích hợp?

> Test WebFlux HTTP authorization với mock principal/authorities. Nó không thay thế decoder/signature integration test.

**13.** Một POST bị 403 có chắc thiếu scope không?

> Không. Có thể là CSRF, rule HTTP, service ACL hoặc policy khác; cần chẩn đoán đúng lớp.

**14.** Tại sao cần `anyExchange().denyAll()`?

> Nó ngăn các exchange chưa có policy tự được cho phép trong chain, phù hợp mô hình fail closed.

**15.** Opaque token có dùng `authorizeExchange` được không?

> Có. Thay đường authentication bằng `ReactiveOpaqueTokenIntrospector`, trong khi rules vẫn kiểm tra authorities của authentication.

## 28. Tài liệu tham khảo

- [Spring Security — Authorize ServerHttpRequest (WebFlux)](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): `authorizeExchange`, `pathMatchers`, `hasRole`, custom access, thứ tự rule và `denyAll`.
- [Spring Security — WebFlux Security Configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `ServerHttpSecurity`, `SecurityWebFilterChain`, nhiều chains và `securityMatcher`.
- [Spring Security — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): `ReactiveJwtDecoder`, `scope`/`scp` và `SCOPE_*`, `hasScope`.
- [Spring Security — OAuth2 WebFlux](https://docs.spring.io/spring-security/reference/reactive/oauth2/): tổng quan reactive Resource Server, JWT, opaque token và OIDC Client.
- [Spring Security — Reactive Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html): introspection reactive.
- [Spring Security — ServerHttpSecurity API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html): các DSL và `securityMatcher`.
- [Spring Security — AuthorizeExchangeSpec.Access API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.AuthorizeExchangeSpec.Access.html): `permitAll`, `authenticated`, `hasAuthority`, `hasRole`, `access`.
- [Spring Security — ServerWebExchangeMatchers API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/util/matcher/ServerWebExchangeMatchers.html): match method/path và custom exchange matchers.
- [Spring Security — AuthorizationContext API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authorization/AuthorizationContext.html): HTTP exchange và extracted path variables.
- [Spring Security — ReactiveAuthorizationManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/ReactiveAuthorizationManager.html): reactive authorization decisions và API theo phiên bản.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): `@EnableReactiveMethodSecurity`, `@PreAuthorize` và custom policy.
- [Spring Security — Reactive Testing OAuth2](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockJwt`, `mockOpaqueToken`, custom authorities.
- [Spring Security — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html): tích hợp `WebTestClient` và security testing.
- [Spring Security — CSRF Protection for WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): CSRF, WebSession và cookie repository.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer HTTP header, lỗi authentication và insufficient scope.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): cấu trúc JWT access token, audience/scope.

**Tổng kết:** `authorizeExchange` là lớp chính để phân quyền **HTTP exchange trong WebFlux**. Hãy dùng `pathMatchers` đúng method/path, khai báo rule hẹp trước rule rộng, phân biệt `securityMatcher` với authorization matcher, dùng scope/authority được cấp thật và kết thúc bằng một default policy rõ ràng. Khi cần điều kiện tenant hoặc nghiệp vụ, dùng `ReactiveAuthorizationManager<AuthorizationContext>` với dữ liệu tin cậy và xử lý non-blocking; sau đó tiếp tục bảo vệ ownership/state ở tầng service. Một API reactive an toàn cần phối hợp **authentication đúng, authorization đúng và kiểm thử cả đường bị từ chối**, không chỉ một chuỗi DSL trông hợp lý.
