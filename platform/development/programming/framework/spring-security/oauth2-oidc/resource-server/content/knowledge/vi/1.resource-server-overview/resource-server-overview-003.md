# Hành trình một yêu cầu: từ access token đến quyết định cho phép truy cập

Trong **Spring Security OAuth 2.0 Resource Server**, một access token không tự động đồng nghĩa với quyền truy cập. Resource Server phải **nhận diện token, xác thực token, chuyển thông tin đã xác thực thành `Authentication`**, rồi **đối chiếu quyền của lời gọi với chính sách bảo vệ tài nguyên**. Các bước này liên quan với nhau nhưng giải quyết những câu hỏi khác nhau:

- **Authentication (xác thực):** Token có hợp lệ, do nguồn được tin cậy phát hành, còn hiệu lực và dành cho API này không? Danh tính của chủ thể/caller là gì?
- **Authorization (phân quyền):** Caller đã xác thực có quyền thực hiện thao tác cụ thể trên tài nguyên cụ thể không?

Bài học theo dõi toàn bộ hành trình của yêu cầu `GET /api/orders/42`, từ lúc client gửi `Authorization: Bearer ...` đến lúc Spring Security cho phép gọi controller hoặc trả về lỗi. Trọng tâm là **Resource Server nhận access token**; quá trình người dùng đăng nhập, xin authorization code hoặc lấy token từ Authorization Server thuộc phần khác của OAuth 2.0/OIDC.

## 1. Các thành phần tham gia

| Thành phần | Trách nhiệm trong hành trình |
|---|---|
| **Client** | Gọi API và gửi access token được cấp trước đó, thông thường trong header `Authorization`. |
| **Authorization Server / OpenID Provider** | Phát hành token; công bố metadata/JWKS nếu dùng JWT; cung cấp introspection endpoint nếu dùng opaque token. |
| **Resource Server** | API chứa dữ liệu/nghiệp vụ được bảo vệ, xác thực token và thực thi các quy tắc truy cập. |
| **Spring Security filter chain** | Chặn yêu cầu trước controller; thực hiện xác thực bearer token và phân quyền theo URL. |
| **Controller/service và method security** | Xử lý yêu cầu sau khi vượt qua lớp bảo vệ HTTP; có thể kiểm tra thêm quyền đối với nghiệp vụ hoặc từng đối tượng dữ liệu. |

Ví dụ HTTP, trong đó chuỗi token được rút gọn để minh họa:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
Accept: application/json
```

`Bearer` có nghĩa là **ai sở hữu và trình được token có thể sử dụng các quyền gắn với token đó**, miễn Resource Server chấp nhận token. Vì thế token phải đi qua HTTPS, không được đưa vào log, URL query, ảnh chụp màn hình hoặc thông báo lỗi.

## 2. Bản đồ luồng xử lý

```mermaid
flowchart TD
    A[Client gửi yêu cầu HTTP] --> B[Spring SecurityFilterChain]
    B --> C{Có bearer token?}
    C -- Không --> D[Tiếp tục với trạng thái chưa xác thực]
    C -- Có --> E[BearerTokenAuthenticationFilter]
    E --> F{Cơ chế xác thực đã cấu hình}
    F -- JWT --> G[JwtAuthenticationProvider và JwtDecoder]
    F -- Opaque --> H[OpaqueTokenAuthenticationProvider và introspection]
    G --> I{Token hợp lệ?}
    H --> I
    I -- Không --> J[Trả lỗi xác thực, thường 401]
    I -- Có --> K[Tạo Authentication cùng authorities]
    K --> L[Đặt Authentication vào SecurityContext]
    D --> M[AuthorizationFilter kiểm tra quy tắc HTTP]
    L --> M
    M --> N{Yêu cầu được cho phép?}
    N -- Không, chưa xác thực --> O[401 Unauthorized]
    N -- Không, đã xác thực --> P[403 Forbidden]
    N -- Có --> Q[Controller và method security]
    Q --> R{Được phép ở tầng nghiệp vụ?}
    R -- Có --> S[Thực thi, trả dữ liệu]
    R -- Không --> P
```

Sơ đồ thể hiện **luồng logic thường gặp**, không liệt kê mọi filter của ứng dụng. Một yêu cầu đến endpoint `permitAll()` có thể đi tiếp mà không cần token; tuy nhiên **nếu đã gửi một bearer token không hợp lệ**, bộ lọc xác thực vẫn có thể từ chối yêu cầu trước khi xét `permitAll()`.

## 3. Bước 1 — Yêu cầu đi vào `SecurityFilterChain`

Servlet container tiếp nhận HTTP request rồi chuyển qua `FilterChainProxy`, thành phần chọn `SecurityFilterChain` phù hợp. Spring Security chạy các security filter trước khi chuyển yêu cầu đến Spring MVC controller. Nếu ứng dụng khai báo nhiều chain bằng `securityMatcher(...)`, **chain được chọn** quyết định các cơ chế xác thực và phân quyền áp dụng.

Với một API Resource Server điển hình, chain bao gồm các thành phần quan trọng:

1. `BearerTokenAuthenticationFilter`: tìm bearer token và yêu cầu xác thực.
2. Cơ chế quản lý `SecurityContext`: lưu kết quả xác thực trong phạm vi xử lý yêu cầu.
3. `ExceptionTranslationFilter`: chuyển một số lỗi xác thực/phân quyền ở giai đoạn sau thành HTTP response thích hợp.
4. `AuthorizationFilter`: kiểm tra chính sách truy cập URL bằng `authorizeHttpRequests(...)`.

Ngoài ra có thể có filter xử lý CORS, CSRF, exception, anonymous authentication hoặc các cơ chế xác thực khác, tùy cấu hình. **Thứ tự filter quan trọng**: quyết định phân quyền cần nhìn thấy thông tin xác thực đã được xây dựng trước đó.

## 4. Bước 2 — Trích xuất bearer token

Mặc định `BearerTokenAuthenticationFilter` dùng `BearerTokenResolver` để tìm token trong header:

```http
Authorization: Bearer <access_token>
```

Nếu không tìm thấy token, filter không tự kết luận mọi endpoint đều bị chặn; yêu cầu tiếp tục đến bước phân quyền. Endpoint công khai có thể được truy cập, còn endpoint bắt buộc xác thực sẽ kích hoạt phản hồi `401`.

Nếu header bearer sai cấu trúc hoặc vi phạm quy tắc truyền token, việc trích xuất có thể thất bại ngay ở bước này. Tùy lỗi, phản hồi có thể là `400 invalid_request` thay vì `401 invalid_token`. Nếu token được trích xuất, filter tạo một `BearerTokenAuthenticationToken` chứa **chuỗi token chưa được tin cậy** và chuyển cho `AuthenticationManager` (hoặc `AuthenticationManagerResolver` nếu cấu hình phân giải động).

> **Điểm mấu chốt:** Việc token có mặt trong header chưa phải là bằng chứng người gọi đã được xác thực.

## 5. Bước 3 — Phân nhánh theo định dạng access token

Resource Server cần được cấu hình để biết **xác thực token theo cách nào**. Hai mô hình phổ biến là JWT và opaque token.

| Khía cạnh | JWT access token | Opaque access token |
|---|---|---|
| Hình dạng | Thường có ba phần `header.payload.signature` | Chuỗi không mang ý nghĩa công khai đối với API |
| Xác minh | Kiểm tra chữ ký bằng khóa tin cậy và xác thực các claim | Gọi introspection endpoint để hỏi trạng thái/thông tin token |
| Thành phần Spring Security | `JwtAuthenticationProvider` → `JwtDecoder` | `OpaqueTokenAuthenticationProvider` → `OpaqueTokenIntrospector` |
| Phụ thuộc mạng trong từng request | Thường không cần gọi Authorization Server cho mỗi token; có thể cần lấy/cập nhật JWKS | Thông thường cần gọi introspection endpoint theo cơ chế đã cấu hình |
| Thu hồi trước khi hết hạn | Khó phát hiện ngay nếu chỉ kiểm tra JWT cục bộ | Có thể phản ánh trạng thái `active=false` từ Authorization Server |

Resource Server **không nên đoán token có hợp lệ chỉ bằng cách nhìn thấy dấu chấm** trong chuỗi. Cách giải mã/xác thực phải theo hợp đồng với Authorization Server và cấu hình tin cậy của API. Hướng đi JWT và opaque có điểm khác biệt ở bước xác thực, nhưng **hội tụ lại ở một `Authentication` đã xác thực để thực hiện phân quyền**.

### Nhánh A — JWT access token

JWT có ba phần được mã hóa Base64URL:

```text
base64url(header).base64url(payload).base64url(signature)
```

Ví dụ payload **minh họa, không phải token có thể sử dụng thật**:

```json
{
  "iss": "https://idp.example.com/realms/demo",
  "sub": "user-123",
  "aud": ["orders-api"],
  "exp": 1893456000,
  "iat": 1893452400,
  "scope": "orders.read profile"
}
```

Một JWT có thể đọc được payload **không có nghĩa payload đó đáng tin cậy**. Client có thể sửa một chuỗi JSON tùy ý; Resource Server chỉ sử dụng claim để xác thực/phân quyền **sau khi** chữ ký và các ràng buộc bắt buộc được kiểm tra thành công.

Với cấu hình `issuer-uri`, `JwtDecoder` sử dụng metadata của issuer để xác định thông tin cần thiết và truy cập tập khóa ký công khai JWKS. Khi xử lý token, decoder thường thực hiện:

1. Đọc header, payload và chữ ký; kiểm tra thuật toán ký phù hợp với cấu hình tin cậy, không chấp nhận thuật toán tùy ý do token tự đề xuất.
2. Tìm khóa xác minh tương ứng từ JWKS tin cậy, chẳng hạn theo `kid`; đối chiếu chữ ký.
3. Kiểm tra thời gian hiệu lực, đặc biệt `exp` (hết hạn) và `nbf` (chưa có hiệu lực), có thể có khoảng dung sai đồng hồ hợp lý.
4. Kiểm tra `iss` đúng Authorization Server được tin cậy.
5. Kiểm tra các ràng buộc **riêng của API**, đặc biệt `aud` phải chứa định danh Resource Server thích hợp. Việc kiểm tra audience cần được cấu hình rõ ràng nếu cấu hình mặc định chưa thực thi yêu cầu này.

Các claim thông dụng:

| Claim | Ý nghĩa | Cách sử dụng |
|---|---|---|
| `iss` | Issuer phát hành token | Chỉ chấp nhận issuer nằm trong danh sách tin cậy. |
| `sub` | Định danh chủ thể | Thường là `Authentication#getName()` mặc định với JWT; không nhất thiết là email. |
| `aud` | Đối tượng được phép nhận token | Ngăn token dành cho API khác được dùng nhầm tại API này. |
| `exp`, `nbf`, `iat` | Các mốc thời gian | Kiểm tra hạn dùng và tính hợp lý của token. |
| `scope` hoặc `scp` | Các scope được cấp | Có thể chuyển thành `GrantedAuthority` để kiểm tra quyền. |
| `client_id`, `azp`, `jti` | Thông tin client, authorized party, token ID (tùy hệ thống) | Phục vụ chính sách bổ sung nếu được yêu cầu. |

`JwtDecoder` kiểm tra chữ ký **không đồng nghĩa** với kiểm tra đầy đủ mọi chính sách của một Resource Server. Nếu bỏ qua audience, một token ký hợp lệ bởi cùng issuer nhưng dành cho dịch vụ khác có thể bị tiếp nhận sai. Nếu cần phân biệt token người dùng với token máy hoặc hạn chế loại token, API còn cần chính sách bổ sung phù hợp với hệ thống phát hành.

### Nhánh B — Opaque access token

Khi cấu hình introspection, Resource Server gửi token đến endpoint của Authorization Server bằng thông tin xác thực của chính Resource Server. Phản hồi introspection có thể chứa:

```json
{
  "active": true,
  "sub": "user-123",
  "scope": "orders.read",
  "client_id": "web-client"
}
```

Chỉ khi token `active` và các điều kiện cần thiết được đáp ứng, Spring Security mới xây dựng `Authentication`. Resource Server vẫn phải kiểm tra quyền truy cập API; `active: true` không có nghĩa caller được phép thao tác với mọi đơn hàng. Đối với opaque token, trách nhiệm và nội dung các claim trả về phụ thuộc hợp đồng introspection của Authorization Server; API phải xác định cách kiểm tra audience/resource nếu hệ thống yêu cầu.

## 6. Bước 4 — Từ token hợp lệ đến `Authentication`

Sau khi xác thực JWT thành công, `JwtAuthenticationProvider` sử dụng `JwtAuthenticationConverter` để biến `Jwt` thành `JwtAuthenticationToken`. Đối với opaque token, provider tương ứng tạo đối tượng xác thực có principal và authorities dựa trên kết quả introspection.

`Authentication` thường cung cấp ba nhóm thông tin:

- **Principal:** Chủ thể đã được xác thực, ví dụ một `Jwt` chứa các claim; đây không mặc nhiên là thực thể `User` trong database.
- **Credentials:** Thông tin chứng thực phù hợp với loại `Authentication`, không phải trường dữ liệu để gửi ra response.
- **Authorities:** Các quyền dạng `GrantedAuthority` mà chính sách Spring Security có thể đối chiếu.

Với JWT, `JwtGrantedAuthoritiesConverter` mặc định đọc các claim scope thông dụng (`scope` hoặc `scp`) và thêm tiền tố `SCOPE_`:

```text
JWT:  "scope": "orders.read profile"
                 │
                 ▼
Authorities: SCOPE_orders.read, SCOPE_profile
```

Do đó, quy tắc Spring Security tương ứng thường viết:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
.hasAuthority("SCOPE_orders.read")
```

Phân biệt hai biểu thức:

- `hasAuthority("SCOPE_orders.read")` kiểm tra **chính xác** authority tên `SCOPE_orders.read`.
- `hasRole("ADMIN")` mặc định kiểm tra authority `ROLE_ADMIN`. Claim JWT như `roles: ["ADMIN"]` **không tự động** trở thành `ROLE_ADMIN`; cần converter tùy biến nếu dùng mô hình role này.

Không nên tin rằng chỉ vì JWT có trường `role`, `groups` hay `permissions` thì Spring Security sẽ tự hiểu toàn bộ. Việc chuyển claim thành authority phải được định nghĩa phù hợp với chuẩn token thực tế của issuer và nhu cầu ứng dụng.

## 7. Bước 5 — Lưu xác thực vào `SecurityContext`

Khi provider trả về `Authentication` thành công, filter đặt đối tượng này vào `SecurityContext` đang áp dụng cho yêu cầu. Trong mô hình servlet thông thường, mã xử lý tiếp theo có thể lấy thông tin từ `SecurityContextHolder`, hoặc sử dụng Spring MVC để nhận principal trực tiếp:

```java
@GetMapping("/api/me")
public Map<String, Object> me(@AuthenticationPrincipal Jwt jwt) {
    return Map.of(
        "subject", jwt.getSubject(),
        "issuer", jwt.getIssuer().toString()
    );
}
```

Ví dụ trên áp dụng với Resource Server xác thực **JWT**, nơi principal là `Jwt`. Nếu sử dụng opaque token, kiểu principal khác; có thể lấy qua `Authentication` hoặc `OAuth2AuthenticatedPrincipal` theo cách cấu hình tương ứng. Một API stateless thường xác thực bearer token cho **mỗi request** và không trông chờ HTTP session để tái sử dụng lần đăng nhập trước.

`SecurityContext` giải đáp: *"Spring Security đã xác thực ai và gắn các authority nào cho request này?"* Nó **chưa** giải đáp: *"Người ấy được phép đọc đơn hàng 42 hay không?"*

## 8. Bước 6 — `AuthorizationFilter` ra quyết định theo URL

`AuthorizationFilter` dùng các quy tắc khai báo trong `authorizeHttpRequests(...)` để so sánh request hiện tại với `Authentication`. Ví dụ:

```java
@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            // Chỉ áp dụng khi API dùng Bearer token, không dựa vào cookie/session.
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
```

Các import chính của cấu hình Java trên:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
```

Dependency Maven cần có trong ứng dụng Spring Boot dùng Resource Server:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
```

Cấu hình issuer JWT trong `application.yml`:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/demo
```

URL issuer phải trùng giá trị `iss` được chấp nhận và là endpoint thực tế của nhà cung cấp. Spring Security có thể lấy metadata/JWKS từ issuer, xác minh chữ ký và kiểm tra các ràng buộc mặc định như issuer/thời gian. **Các yêu cầu riêng như `aud=orders-api` cần được thiết lập, kiểm tra theo cấu hình và hợp đồng bảo mật của ứng dụng.**

Trong ví dụ:

1. `GET /public/ping` được phép truy cập không cần token.
2. `GET /api/orders/42` cần authority `SCOPE_orders.read`.
3. `POST /api/orders/42` cần `SCOPE_orders.write` (đường dẫn HTTP cụ thể cần điều chỉnh theo thiết kế REST thực tế).
4. Những endpoint khác ít nhất phải có `Authentication` hợp lệ; điều đó **không thay thế** quy tắc quyền chi tiết cho endpoint nhạy cảm.

Các matcher được xét theo thứ tự khai báo: quy tắc phù hợp đầu tiên áp dụng. Cần thiết kế các matcher chuyên biệt trước quy tắc tổng quát. `authenticated()` chỉ đòi hỏi đã xác thực; không tự chứng minh caller có đúng scope, vai trò hoặc quyền sở hữu tài nguyên.

> **Lưu ý CSRF:** Việc tắt CSRF trong ví dụ phù hợp với API chỉ sử dụng bearer token được gửi chủ động trong header, không sử dụng cookie/session cho xác thực request. Nếu hệ thống có xác thực dựa trên cookie hoặc trình duyệt tự gửi credential, phải đánh giá và cấu hình bảo vệ CSRF theo kiến trúc thực tế.

## 9. Bước 7 — Method security và quyền trên từng tài nguyên

Qua được `AuthorizationFilter` nghĩa là request đạt chính sách HTTP đã khai báo. Trước hoặc trong khi chạy nghiệp vụ, ứng dụng vẫn có thể cần kiểm tra:

- Người dùng A có quyền đọc **đơn hàng số 42** thuộc người dùng B không?
- Scope `orders.read` có cho đọc mọi đơn hàng trong hệ thống, hay chỉ đơn hàng của chính caller?
- Người gọi thuộc đúng tenant, tổ chức, dự án, khu vực dữ liệu hay không?

Với `@EnableMethodSecurity`, Spring Security có thể thực hiện thêm quyết định tại phương thức:

```java
@Service
public class OrderService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public OrderDto findOrder(String orderId) {
        // Đọc đơn hàng từ kho dữ liệu; cần kiểm tra quyền sở hữu/tenant
        // trước khi trả dữ liệu nếu scope không cho phép đọc toàn hệ thống.
        return loadOrder(orderId);
    }

    private OrderDto loadOrder(String orderId) {
        // Ví dụ minh họa: triển khai bằng repository/service thực tế.
        throw new UnsupportedOperationException("Implement order lookup");
    }
}
```

Đoạn mã trên chỉ minh họa **method security**; nó chưa thực hiện kiểm tra ownership. Với một API đa người dùng, cần bổ sung kiểm tra quan hệ giữa `sub`/caller và `order.ownerId`, hoặc cơ chế policy tương đương. Không nên xem `scope` rộng hay `authenticated()` là bằng chứng người dùng sở hữu một bản ghi cụ thể.

Trong một số kiến trúc, quyền tài nguyên được kiểm tra bởi database query có lọc `tenant_id`, service phân quyền nghiệp vụ, policy engine hoặc `@PreAuthorize` gọi bean kiểm tra quyền. Vị trí triển khai có thể khác, nhưng nguyên tắc là **chỉ cho trả dữ liệu sau khi cả quyền thao tác lẫn quyền truy cập bản ghi đều được xác nhận**.

## 10. Bước 8 — Biến quyết định thành HTTP response

Ba trạng thái cần phân biệt rõ:

| Trạng thái | Ý nghĩa trong Resource Server | Ví dụ |
|---|---|---|
| `200 OK` (hoặc mã thành công phù hợp) | Xác thực và phân quyền đều thành công; controller xử lý được yêu cầu. | JWT hợp lệ, đúng audience, có `SCOPE_orders.read`, sở hữu đơn hàng. |
| `401 Unauthorized` | Chưa có xác thực hợp lệ cho endpoint được bảo vệ. | Không gửi token; JWT hết hạn, sai chữ ký/issuer/audience. |
| `403 Forbidden` | Đã được xác thực nhưng không đạt chính sách phân quyền. | JWT hợp lệ nhưng thiếu `SCOPE_orders.read` hoặc vi phạm quyền truy cập bản ghi. |

Ví dụ yêu cầu thiếu token đến endpoint bắt buộc xác thực:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

Với access token không hợp lệ, phản hồi có thể chứa:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Với người gọi đã xác thực nhưng không đủ scope, phản hồi điển hình:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

`BearerTokenAuthenticationEntryPoint` tham gia xử lý các tình huống yêu cầu xác thực; `BearerTokenAccessDeniedHandler` xử lý các tình huống truy cập bị từ chối theo cấu hình bearer token. `ExceptionTranslationFilter` cũng tham gia chuyển ngoại lệ xảy ra tại các bước phân quyền phía sau filter thành phản hồi. Header chính xác, mô tả lỗi và mã trạng thái phụ thuộc từng nhánh lỗi, cấu hình và nơi phát sinh ngoại lệ; không nên mặc định **mọi** lỗi liên quan token đều là `401`.

Một số tình huống đối chiếu:

| Yêu cầu | Xác thực | Phân quyền | Kết quả điển hình |
|---|---|---|---|
| `GET /api/orders/42`, không có token | Không có | Endpoint cần authority | `401` |
| Có JWT bị sửa chữ ký hoặc hết hạn | Thất bại | Không chạy như người đã xác thực | `401`, thường `invalid_token` |
| JWT do issuer tin cậy ký nhưng `aud` dành cho API khác, có validator audience | Thất bại | Không chạy như người đã xác thực | `401` |
| JWT hợp lệ, chỉ có `SCOPE_profile` | Thành công | Thiếu `SCOPE_orders.read` | `403` |
| JWT hợp lệ, có `SCOPE_orders.read`, nhưng truy cập đơn hàng người khác | Thành công | Kiểm tra ownership từ chối | `403` hoặc quy ước bảo mật phù hợp, như `404` để tránh tiết lộ sự tồn tại |
| JWT hợp lệ, đủ quyền với bản ghi | Thành công | Cho phép | Controller trả `200` nếu nghiệp vụ thành công |
| `GET /public/ping`, không token | Không cần | `permitAll()` | Endpoint thực thi bình thường |

**Cảnh báo về `401` và `403`:** Tên HTTP `401 Unauthorized` dễ gây nhầm. Trong ngữ cảnh này, `401` chủ yếu báo **chưa được xác thực hợp lệ**, còn `403` báo **đã được xác thực nhưng bị từ chối quyền**.

## 11. Phân biệt OAuth 2.0 access token với OIDC ID token

OIDC xây dựng thêm lớp xác thực danh tính trên OAuth 2.0. Sau khi đăng nhập, client có thể nhận nhiều loại token, nhưng mỗi loại có **đối tượng sử dụng khác nhau**:

| Loại token | Ai sử dụng? | Vai trò |
|---|---|---|
| **Access token** | Resource Server/API | Chứng thực quyền truy cập API trong phạm vi được cấp và chính sách API. |
| **ID token** | OIDC client/relying party | Truyền thông tin về sự kiện xác thực và danh tính cho client; audience thường là client ID. |
| **Refresh token** | Client và Authorization Server | Xin access token mới theo chính sách của Authorization Server; không gửi đến Resource Server để truy cập tài nguyên. |

Một ID token cũng có thể là JWT được ký hợp lệ, nhưng **không vì thế mà Resource Server nên chấp nhận nó như access token**. Phải kiểm tra mục đích sử dụng token, audience và các ràng buộc của nhà phát hành. `issuer-uri` trỏ đến một OpenID Provider chỉ giúp thiết lập một phần niềm tin vào issuer; nó không có nghĩa Resource Server đang thực hiện login OIDC, kiểm tra ID token cho client hay tự động có đủ chính sách phân quyền API.

## 12. Đi theo một request cụ thể từ đầu đến cuối

Giả sử `orders-api` tin cậy issuer `https://idp.example.com/realms/demo`, đã cấu hình kiểm tra audience `orders-api` và endpoint `GET /api/orders/{id}` yêu cầu `SCOPE_orders.read`.

**Tình huống cho phép truy cập:**

1. Người dùng đã xác thực với hệ thống nhận dạng; client được cấp access token có `sub=user-123`, `aud=orders-api` và `scope=orders.read`.
2. Client gọi `GET /api/orders/42` qua HTTPS, gửi token trong header bearer.
3. `BearerTokenAuthenticationFilter` lấy chuỗi token và chuyển cho authentication manager.
4. `JwtDecoder` xác minh chữ ký với JWKS tin cậy, kiểm tra thời gian, issuer và audience đã cấu hình.
5. Converter tạo `JwtAuthenticationToken` với authority `SCOPE_orders.read`; Spring Security đưa kết quả vào `SecurityContext`.
6. `AuthorizationFilter` thấy `GET /api/orders/**` yêu cầu `SCOPE_orders.read` và caller đáp ứng điều kiện.
7. Service kiểm tra `user-123` có quyền xem đơn hàng 42; điều kiện đúng.
8. Controller trả dữ liệu đơn hàng cùng mã HTTP thành công phù hợp.

**Tình huống từ chối do thiếu scope:** Toàn bộ bước xác thực 1–5 vẫn có thể thành công, nhưng token chỉ mang `scope=profile`. Tại bước 6, `AuthorizationFilter` từ chối và API trả `403` theo cấu hình thông thường. Đây là ví dụ trực tiếp cho thấy **token hợp lệ không bảo đảm mọi hành động đều được phép**.

**Tình huống từ chối do token hết hạn:** Decoder thất bại ở bước 4; quá trình không xây dựng principal đáng tin cậy, và request cần xác thực nhận `401`. Sửa bằng cách xin access token mới theo quy trình OAuth 2.0 phù hợp, thay vì tăng quyền hay bỏ kiểm tra thời gian.

## 13. Quan sát và xử lý sự cố đúng tầng

Khi thử API, có thể dùng `curl` để nhìn rõ status và các header phản hồi:

```bash
# Không gửi token: endpoint được bảo vệ thường trả 401.
curl -i https://api.example.com/api/orders/42

# Gửi access token đã cấp cho orders-api.
curl -i https://api.example.com/api/orders/42 \
  -H 'Authorization: Bearer <ACCESS_TOKEN>'
```

Khi có lỗi, hãy xác định **nó xảy ra ở tầng nào**:

| Dấu hiệu | Nơi cần kiểm tra | Hướng xử lý |
|---|---|---|
| `401` dù token vừa cấp | Header bearer, issuer, JWKS/chữ ký, `exp`/`nbf`, audience | Xác minh token dành cho API hiện tại; xem cấu hình tin cậy và sai lệch đồng hồ. |
| `403` với token còn hiệu lực | Authorities, matcher, method security, ownership/tenant | So sánh scope được cấp với `SCOPE_...`, kiểm tra quy tắc nghiệp vụ. |
| Scope có trong JWT nhưng `hasRole(...)` thất bại | Converter và tiền tố authority | Phân biệt `SCOPE_` với `ROLE_`; cấu hình converter nếu thật sự dùng role. |
| Endpoint công khai bị từ chối khi gửi token lỗi | Bearer authentication filter trước authorization | Bỏ header không hợp lệ khỏi request công khai; sửa nguồn token. |
| JWT ký hợp lệ nhưng API sai vẫn chấp nhận | Cấu hình audience và chính sách loại token | Bổ sung kiểm tra `aud`/mục đích token theo hợp đồng Resource Server. |
| Request có quyền HTTP nhưng đọc được dữ liệu tenant khác | Kiểm tra đối tượng trong service/query | Áp dụng ownership và tenant boundary ở tầng nghiệp vụ/dữ liệu. |

Có thể bật logging phù hợp để theo dõi filter chain và quyết định truy cập trong môi trường phát triển, nhưng **không ghi nguyên access token, refresh token, thông tin bí mật hoặc dữ liệu nhạy cảm vào log**. Mã lỗi trả cho client nên đủ để xác định nguyên nhân tổng quát mà không tiết lộ khóa, thông tin nội bộ hoặc chính sách chi tiết.

## 14. Những nguyên tắc giữ hành trình an toàn

1. **Giới hạn issuer và audience:** Chữ ký đúng chỉ chứng minh token phù hợp với một khóa tin cậy, không chứng minh token được cấp cho chính API của bạn. Kiểm tra `iss`, `aud` và chính sách chấp nhận token.
2. **Không tin claim trước xác thực:** Không tự tách Base64 rồi dùng `sub`, `scope` hay `roles` để phân quyền khi chưa xác thực chữ ký/trạng thái token.
3. **Phân tách scope với quyền dữ liệu:** `orders.read` là quyền thực hiện một loại thao tác; quyền xem *đơn hàng nào* có thể cần kiểm tra bổ sung.
4. **Dùng HTTPS và bảo vệ bearer token:** Tránh lưu token vào URL, console, log hoặc client storage không phù hợp; coi token bị lộ như credential bị lộ.
5. **Chọn chiến lược kiểm tra hiệu lực phù hợp:** JWT giúp API xác minh cục bộ nhưng không tự biết token bị thu hồi trước hạn; opaque introspection có thể nắm trạng thái mới hơn nhưng phụ thuộc endpoint introspection và độ sẵn sàng của nó.
6. **Giới hạn đặc quyền:** Áp dụng chính sách `hasAuthority(...)`/method security cho endpoint nhạy cảm, không chỉ dựa vào `anyRequest().authenticated()`.
7. **Tách vai trò các loại token:** Resource Server nhận access token có mục đích phù hợp, không nhận ID token hay refresh token như một phương án thay thế tùy tiện.

## 15. Kết nối các lớp trách nhiệm

Có thể ghi nhớ hành trình bằng chuỗi sau:

```text
HTTP Authorization: Bearer ...
    → BearerTokenAuthenticationFilter: trích xuất token
    → AuthenticationManager / AuthenticationProvider: xác thực token
    → JwtDecoder hoặc introspection: xác minh bằng chứng và ràng buộc
    → Authentication + GrantedAuthority: biểu diễn caller đã xác thực
    → SecurityContext: cung cấp kết quả cho các bước tiếp theo
    → AuthorizationFilter: kiểm tra chính sách HTTP
    → Method security / nghiệp vụ: kiểm tra quyền thao tác và quyền dữ liệu
    → Cho phép controller thực thi, hoặc trả 401/403 theo nguyên nhân
```

Khi phân tích một lần truy cập bị chặn, hãy đặt câu hỏi theo đúng thứ tự: **Token đã được đọc chưa? Token được xác thực bởi cơ chế nào? Issuer/audience/thời hạn có đúng không? Những authority nào được tạo ra? Quy tắc URL nào khớp? Có quyền truy cập bản ghi cụ thể hay không?** Đi theo thứ tự này sẽ tách rõ lỗi cấu hình xác thực khỏi lỗi phân quyền và giúp hiểu chính xác vì sao Resource Server chấp nhận hoặc từ chối một request.
