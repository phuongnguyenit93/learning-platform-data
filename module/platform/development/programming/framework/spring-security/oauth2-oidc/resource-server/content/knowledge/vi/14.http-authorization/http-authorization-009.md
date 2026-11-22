# permitAll không tự vô hiệu hóa bước xử lý token được gửi đến

Khi cấu hình Spring Security OAuth 2.0 Resource Server, ta thường muốn một số endpoint như `/public/info`, `/health` hoặc tài liệu API cho phép mọi người truy cập:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .anyRequest().authenticated())
~~~

Rất dễ suy luận rằng **`permitAll()` làm Spring Security bỏ qua mọi bước bảo mật cho đường dẫn đó**. Nhưng suy luận này **không đúng**. `permitAll()` quyết định **ủy quyền truy cập (authorization)**: request không cần được cấp quyền mới được đi tiếp. Nó **không tự gỡ `BearerTokenAuthenticationFilter` khỏi `SecurityFilterChain`**, cũng không mặc định yêu cầu Resource Server bỏ qua access token mà client đã gửi.

Nếu endpoint công khai nằm trong một security chain bật JWT Resource Server, hai request này có thể cho kết quả khác nhau:

~~~http
GET /public/info HTTP/1.1
Host: api.example.com
~~~

~~~http
GET /public/info HTTP/1.1
Host: api.example.com
Authorization: Bearer <expired-or-invalid-access-token>
~~~

Request thứ nhất không đòi token nên có thể trả **200 OK**. Request thứ hai **đã gửi token**, khiến filter xác thực Bearer có thể thử xác thực và trả **401 Unauthorized** nếu token không hợp lệ, **trước khi** quy tắc `permitAll()` của authorization được thực thi. Đây là hành vi cần hiểu rõ khi thiết kế một API có cả endpoint công khai lẫn endpoint được bảo vệ.

## 1. Phân biệt authentication, authorization và security filter chain

Ba khái niệm thường bị nhầm:

| Khái niệm | Câu hỏi được giải quyết | Ví dụ trong Resource Server |
| --- | --- | --- |
| **Authentication – xác thực** | Token được gửi có hợp lệ, thuộc chủ thể nào? | `BearerTokenAuthenticationFilter` → `JwtAuthenticationProvider` → `JwtDecoder` |
| **Authorization – phân quyền** | Request có được phép truy cập endpoint/tài nguyên không? | `authorizeHttpRequests(...).requestMatchers(...).permitAll()`, `authenticated()`, `hasAuthority(...)` |
| **SecurityFilterChain – chuỗi filter bảo mật** | Những bộ lọc bảo mật nào tham gia xử lý request phù hợp? | Chain có `oauth2ResourceServer(...jwt(...))`, CORS, CSRF, security context, exception handling... |

**`permitAll` thuộc authorization, không phải cấu hình lựa chọn filter chain.** Trong một security chain đã bật Bearer authentication, filter có thể xác thực token trước khi tới bước phân quyền, dù đích request được khai báo `permitAll()`.

Hình dung:

~~~mermaid
flowchart TD
    A["HTTP request /public/info"] --> B["FilterChainProxy chọn SecurityFilterChain"]
    B --> C["BearerTokenAuthenticationFilter"]
    C --> D{"Có Bearer token?"}
    D -- "Không" --> E["Tiếp tục chain"]
    D -- "Có" --> F["AuthenticationManager + JWT/opaque provider"]
    F --> G{"Token hợp lệ?"}
    G -- "Không" --> H["Authentication failure → thường 401"]
    G -- "Có" --> I["Gắn Authentication vào SecurityContext"]
    I --> E
    E --> J["AuthorizationFilter kiểm tra /public/info"]
    J --> K{"permitAll()?"}
    K -- "Có" --> L["Tiếp tục tới controller"]
    K -- "Không" --> M["Áp dụng rule của endpoint khác"]
~~~

Sơ đồ mô tả luồng thông dụng trong **Servlet SecurityFilterChain** của Spring Security có `oauth2ResourceServer`. Chi tiết vị trí của các filter, exception handler và HTTP response có thể phụ thuộc phiên bản/cấu hình, nhưng nguyên tắc quan trọng không đổi: **authorization cho phép không đồng nghĩa bỏ qua authentication filter**.

### Vì sao xác thực được thực hiện trước `permitAll`?

Các filter có nhiệm vụ khác nhau và được sắp xếp theo thứ tự. Trong cấu hình Resource Server thông dụng:

1. `FilterChainProxy` chọn `SecurityFilterChain` phù hợp request.
2. `BearerTokenAuthenticationFilter` dùng `BearerTokenResolver` để tìm access token trong request.
3. Nếu có bearer token, filter gọi `AuthenticationManager` để xác thực token đó.
4. Nếu token hợp lệ, filter thiết lập `Authentication` trong `SecurityContext` rồi cho request đi tiếp.
5. Nếu token không hợp lệ, filter chuyển lỗi đến cơ chế xử lý xác thực thay vì tự cho request đi tiếp.
6. Nếu không có Bearer token, filter thường để request đi tiếp; endpoint công khai vẫn có thể được truy cập không cần danh tính.
7. Khi tới bước authorization, `AuthorizationFilter` áp dụng `permitAll()` hoặc điều kiện khác.

Điểm mấu chốt là **filter xử lý token không chờ hỏi trước “endpoint này có permitAll không?”**. Nó hoạt động theo security chain và cơ chế phân tích Bearer token mà bạn đã cấu hình.

## 2. `BearerTokenAuthenticationFilter` thực sự làm gì?

Khi đã bật JWT Resource Server, một request có header:

~~~http
Authorization: Bearer eyJ...
~~~

thường được `BearerTokenAuthenticationFilter` tiếp nhận. Các thành phần liên quan:

| Thành phần | Nhiệm vụ |
| --- | --- |
| `DefaultBearerTokenResolver` | Trích xuất token theo cú pháp Bearer từ request, mặc định chủ yếu ở HTTP `Authorization` header |
| `BearerTokenAuthenticationToken` | Mang chuỗi token đầu vào dưới dạng yêu cầu `Authentication` chưa xác thực |
| `AuthenticationManager` | Điều phối yêu cầu đến provider phù hợp |
| `JwtAuthenticationProvider` | Sử dụng `JwtDecoder` để xác minh JWT, sau đó tạo `JwtAuthenticationToken` |
| `OpaqueTokenAuthenticationProvider` | Sử dụng `OpaqueTokenIntrospector` để kiểm tra token qua introspection, sau đó tạo `BearerTokenAuthentication` |
| `SecurityContextHolder` | Cung cấp authentication đã thành công cho phần còn lại của request |

Trong cấu hình JWT:

~~~text
BearerTokenAuthenticationFilter
    |
    +-- Không có token --> tiếp tục chain
    |
    +-- Có Bearer token --> AuthenticationManager
                               |
                               v
                         JwtAuthenticationProvider
                               |
                               v
                            JwtDecoder
                               |
                +--------------+--------------+
                |                             |
           JWT hợp lệ                   JWT không hợp lệ
                |                             |
           JwtAuthenticationToken         AuthenticationException
                |                             |
           SecurityContext                  401 / error handler
                |
           AuthorizationFilter
                |
           permitAll / rule khác
~~~

Resource Server với opaque token khác ở **cách xác minh access token**, không khác ở nguyên tắc này. Dù dùng `JwtDecoder` hay `OpaqueTokenIntrospector`, token được gửi tới endpoint công khai vẫn có thể được xác thực và từ chối nếu không hợp lệ.

Một Bearer token có thể không hợp lệ vì:

- Token hết hạn theo `exp` hoặc chưa có hiệu lực theo `nbf`.
- Chữ ký không hợp lệ, thuật toán không được cho phép hoặc không có khóa xác minh tin cậy.
- Issuer `iss` không đúng nguồn đã cấu hình.
- Audience `aud` không hướng tới API này.
- Token sai loại/profile, thiếu claim bắt buộc hoặc đã bị issuer vô hiệu hóa theo cơ chế xác minh đang dùng.
- Bearer header sai cú pháp, chứa nhiều cách truyền token không được phép hoặc không thỏa quy tắc resolver.

**`permitAll` không biến những token ấy thành hợp lệ.** Nếu token đã gửi được filter phát hiện và cần xác thực, việc xác thực thất bại có thể chặn request từ rất sớm.

## 3. Ma trận hành vi: endpoint công khai và endpoint được bảo vệ

Giả sử API có cấu hình:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/api/orders/**").hasAuthority("SCOPE_orders.read")
    .anyRequest().authenticated())
.oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
~~~

Và cả hai đường dẫn đều nằm trong **cùng một SecurityFilterChain**.

| Endpoint | Bearer token được gửi | Hành vi thường gặp |
| --- | --- | --- |
| `GET /public/info` | Không có token | **200 OK** nếu controller thực hiện thành công |
| `GET /public/info` | Token JWT hợp lệ | **200 OK**; authentication có thể có mặt trong security context |
| `GET /public/info` | JWT hết hạn | **401 Unauthorized** trước khi `permitAll` cho qua |
| `GET /public/info` | JWT sai chữ ký/sai issuer | **401 Unauthorized** |
| `GET /public/info` | Header Bearer sai định dạng | Có thể bị lỗi xử lý Bearer trước authorization, thường **400** theo quy tắc Bearer/RFC 6750 hoặc phản hồi do handler cấu hình |
| `GET /api/orders` | Không có token | **401 Unauthorized** khi endpoint đòi xác thực |
| `GET /api/orders` | JWT hợp lệ, có `SCOPE_orders.read` | Request có thể được phép vào controller |
| `GET /api/orders` | JWT hợp lệ nhưng thiếu `SCOPE_orders.read` | **403 Forbidden** |
| `GET /api/orders` | JWT hết hạn hoặc sai chữ ký | **401 Unauthorized** |

Các mã phản hồi trong bảng là hành vi **thường gặp**, không phải cam kết tuyệt đối về mọi tùy chỉnh `AuthenticationEntryPoint`, `AccessDeniedHandler` hoặc request handler. Ví dụ, controller có thể trả 404/500 vì nghiệp vụ ngay cả khi security cho phép request đi qua.

**401 và 403 giải quyết hai vấn đề khác nhau:**

- **401:** request thiếu thông tin xác thực cần thiết hoặc token được gửi không vượt qua bước xác thực.
- **403:** yêu cầu đã có authentication thích hợp nhưng không được cấp quyền cần thiết, ví dụ thiếu scope hoặc không có quyền đối với bản ghi.

### “Không yêu cầu token” khác với “bỏ qua token nếu được gửi”

Hai câu sau không tương đương:

1. Endpoint `/public/info` **không bắt buộc client gửi token**.
2. Endpoint `/public/info` **sẽ không xử lý token ngay cả khi client chủ động gửi**.

`permitAll()` thường đáp ứng câu **(1)**, chứ **không** bảo đảm câu **(2)**. Nếu câu (2) là yêu cầu nghiệp vụ thực sự, cần thiết kế việc **lựa chọn security chain hoặc bỏ qua Bearer resolver cho đường dẫn được xác định rõ**.

## 4. Ví dụ cấu hình đơn giản: public endpoint vẫn kiểm tra Bearer token được gửi

Với ứng dụng Spring Boot dùng Servlet stack, thêm dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

Cấu hình issuer:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
~~~

`issuer-uri` và URL là ví dụ. Resource Server vẫn phải kiểm tra audience và các điều kiện khác theo hợp đồng token dành cho API.

Ví dụ security configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ResourceServerSecurity {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Ví dụ controller:

~~~java
import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ExampleController {

    @GetMapping("/public/info")
    Map<String, String> publicInfo() {
        return Map.of("service", "orders-api", "status", "available");
    }

    @GetMapping("/api/orders")
    Map<String, String> orders(Authentication authentication) {
        return Map.of("requestedBy", authentication.getName());
    }
}
~~~

Trong cấu hình này, request tới `/public/info` **vẫn đi qua filter Resource Server** vì cả đường dẫn đều thuộc cùng chain. `permitAll` chỉ có nghĩa `AuthorizationFilter` không yêu cầu quyền truy cập cho đường dẫn công khai đó.

Lệnh `csrf(...disable())` ở ví dụ phù hợp khi API là **stateless Bearer-token API không sử dụng cookie xác thực tự động gửi từ browser**. Nếu ứng dụng có cookie/session hoặc endpoint thay đổi trạng thái được bảo vệ bằng thông tin xác thực tự động gửi, cần đánh giá và cấu hình CSRF thích hợp.

### Khi có token hợp lệ, endpoint public vẫn có thể biết người dùng

Giả sử request:

~~~http
GET /public/info HTTP/1.1
Authorization: Bearer <valid-access-token>
~~~

Vì filter đã xác thực token, một controller hoặc thành phần phía sau có thể nhận `Authentication` tương ứng (nếu hợp đồng endpoint sử dụng nó), dù `permitAll` cho phép cả người dùng ẩn danh.

Điều này tạo ra một kiểu endpoint **optional authentication**: không bắt buộc có token, nhưng nếu gửi token hợp lệ thì ứng dụng có thể dùng danh tính để cá nhân hóa nội dung. Tuy nhiên, **optional authentication không đồng nghĩa optional validation**: token không hợp lệ vẫn có thể bị từ chối ngay từ filter.

Nếu sản phẩm thực sự muốn “token hỏng thì coi như khách” ở một endpoint, đó là **chính sách riêng và có rủi ro riêng**. Không thể mặc định có được hành vi này chỉ bằng `permitAll`.

## 5. Cách quan sát hiện tượng với cURL

Giả sử ứng dụng chạy tại `http://localhost:8080` và có endpoint `/public/info` như trên.

**Không gửi token:**

~~~bash
curl -i http://localhost:8080/public/info
~~~

Phản hồi thông thường:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"service":"orders-api","status":"available"}
~~~

**Gửi token sai:**

~~~bash
curl -i \
  -H 'Authorization: Bearer invalid-token' \
  http://localhost:8080/public/info
~~~

Phản hồi điển hình:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

**Gửi access token JWT hợp lệ:**

~~~bash
curl -i \
  -H 'Authorization: Bearer YOUR_VALID_ACCESS_TOKEN' \
  http://localhost:8080/public/info
~~~

Nếu JWT hợp lệ với issuer/audience/thời hạn của API, endpoint public có thể trả 200. Đây là minh họa; không dùng chuỗi giữ chỗ `YOUR_VALID_ACCESS_TOKEN` như token thật.

### Khi lỗi xuất hiện chỉ ở một số client

Một browser/frontend có thể được cấu hình interceptor **tự động gắn access token cho mọi request** đến API, kể cả endpoint công khai. Khi token đã hết hạn, `/public/info` bất ngờ trả 401, nhưng mở cùng URL từ một công cụ không gắn bearer token lại trả 200.

Tình huống này thường **không phải lỗi của `permitAll`**, mà do:

1. Endpoint public không cần token.
2. Client vẫn chủ động gửi token đã hết hạn.
3. Resource Server được cấu hình để kiểm tra Bearer token nếu request chứa nó.

Giải pháp có thể đơn giản là **không đính kèm bearer token vào các endpoint được thiết kế công khai**; thay vì thay đổi toàn bộ chính sách filter của server.

## 6. Phân biệt `requestMatchers(...).permitAll()` và `securityMatcher(...)`

Hai API trông gần giống nhau nhưng hoạt động ở **hai tầng khác nhau**.

### `requestMatchers(...).permitAll()`: một quy tắc authorization

~~~java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/public/**").permitAll()
        .anyRequest().authenticated())
    .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));
~~~

Ý nghĩa: request đã được chọn vào chain, chạy qua các filter của chain; đến bước authorization, đường dẫn `/public/**` được phép đi tiếp mà không cần thêm quyền.

### `securityMatcher(...)`: giới hạn request thuộc chain nào

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated())
    .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));
~~~

Ý nghĩa: **security chain này chỉ áp dụng cho những request khớp `/api/**`**. Request đến `/public/info` không khớp chain này nên filter Resource Server **trong chain ấy** không xử lý token.

Điều đó **không có nghĩa request public chắc chắn không đi qua bất kỳ filter nào**: `FilterChainProxy` có thể chọn một `SecurityFilterChain` khác cho nó. Nếu không có chain Spring Security nào khớp, request có thể đi qua phần web app mà không có các bảo vệ do Spring Security cung cấp.

**Khuyến nghị:** Nếu muốn endpoint public không bị xử lý Bearer token, hãy thiết kế **chain riêng có phạm vi rõ ràng** thay vì suy luận rằng một rule `permitAll` sẽ tắt authentication.

## 7. Hai `SecurityFilterChain`: public không xử lý Bearer token

Nếu yêu cầu thực tế là **khu vực công khai phải hoạt động ngay cả khi client gửi Bearer token không hợp lệ**, có thể tách những đường dẫn đó vào một security chain **không bật OAuth 2.0 Resource Server**, rồi cấu hình chain còn lại cho API bảo vệ.

Ví dụ ứng dụng Servlet:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SeparatePublicAndApiSecurity {

    @Bean
    @Order(1)
    SecurityFilterChain publicChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/public/**", "/health")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .anyRequest().permitAll())
            // Không gọi oauth2ResourceServer() ở publicChain.
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

### Hành vi mong muốn của ví dụ

| Request | Chain | Bearer token được Resource Server filter xử lý? |
| --- | --- | --- |
| `GET /public/info` không token | `publicChain` | Không, vì chain này không bật Resource Server |
| `GET /public/info` token JWT hỏng | `publicChain` | Không, nếu không có filter khác xử lý Bearer |
| `GET /health` token JWT hết hạn | `publicChain` | Không theo cấu hình minh họa |
| `GET /api/orders` không token | `apiChain` | Filter tìm token nhưng không có; authorization đòi xác thực và thường trả 401 |
| `GET /api/orders` token sai | `apiChain` | Có; xác thực thất bại |
| `GET /api/orders` token hợp lệ, đủ scope | `apiChain` | Có; xác thực rồi phân quyền |

**Quan trọng:** ví dụ trên **chưa có fallback chain** cho các đường dẫn ngoài `/public/**`, `/health` và `/api/**`. Nếu ứng dụng có endpoint khác, chúng có thể **không được Spring Security bảo vệ** nếu không có chain bổ sung. Trong sản phẩm thật, nên thêm **fallback SecurityFilterChain** với chính sách mặc định từ chối hoặc yêu cầu xác thực, hoặc thiết kế API matcher bao phủ đầy đủ.

Một fallback chain từ chối theo mặc định có thể là:

~~~java
@Bean
@Order(3)
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll())
        .build();
}
~~~

Với nhiều chain, `FilterChainProxy` chọn **chain đầu tiên khớp request**, không chạy tuần tự mọi chain rồi gộp filter của chúng. `@Order` và `securityMatcher(...)` vì vậy rất quan trọng.

### Không phải cứ chia chain là mọi yêu cầu biến mất

Một chain public không có `oauth2ResourceServer` chỉ ngăn **Bearer authentication theo Resource Server trong chain đó**. Nếu bạn bật `httpBasic`, `formLogin` hoặc một filter xác thực tùy chỉnh ở chain public, header hoặc cookie không hợp lệ vẫn có thể gây lỗi theo cơ chế khác. Cần xem **toàn bộ filter thực sự có mặt**, không chỉ tên gọi “public”.

Trong thiết kế optional personalization, chia chain theo cách trên khiến endpoint public **không nhận danh tính từ JWT qua Resource Server**, kể cả token hợp lệ. Vì vậy cần lựa chọn rõ giữa:

- **Public nhưng nhận danh tính nếu Bearer hợp lệ:** có thể giữ một chain, `permitAll` và xử lý token đã gửi.
- **Public tuyệt đối, không xử lý Bearer token:** dùng chain riêng hoặc cơ chế lọc token rõ ràng.

## 8. Vì sao `web.ignoring()` không phải lựa chọn mặc định?

Một số ứng dụng cũ dùng:

~~~java
// Ví dụ cũ/định hướng cấu hình, không phải khuyến nghị cho mọi API.
// web.ignoring().requestMatchers("/public/**");
~~~

Khi đường dẫn được cấu hình **bỏ qua Spring Security hoàn toàn**, các filter của Spring Security sẽ không xử lý request ấy. Điều đó có thể giải quyết hiện tượng Bearer token hỏng trên endpoint public nhưng đồng thời **bỏ qua nhiều bảo vệ khác**, ví dụ security headers, security context/các filter được tích hợp và các chính sách về request trong chuỗi Spring Security.

Vì vậy:

- Dùng **`permitAll()`** khi endpoint công khai nhưng vẫn cần đi qua Spring Security và bạn chấp nhận việc xử lý Bearer token được gửi đến.
- Dùng **chain riêng không bật Resource Server** nếu muốn public route không xác thực Bearer mà vẫn muốn giữ các filter bảo vệ khác được cấu hình cho route đó.
- Chỉ xem xét **bỏ qua Spring Security hoàn toàn** khi đó là quyết định được hiểu đầy đủ, thường cho tài nguyên tĩnh đặc thù hoặc tình huống cần thiết.

Các tài liệu Spring Security hiện đại thường khuyến nghị `permitAll` thay vì bỏ qua toàn bộ filter chain cho các tài nguyên có thể được bảo vệ bằng security headers. Bỏ qua filter không phải là cách “tăng tính công khai” vô hại.

## 9. Một lựa chọn khác: tùy biến `BearerTokenResolver` theo đường dẫn

Trong một số kiến trúc, ứng dụng muốn giữ **một SecurityFilterChain** nhưng chủ động **không giải quyết bearer token** trên vài endpoint công khai. Có thể cấu hình `BearerTokenResolver` để trả `null` trên request khớp danh sách công khai:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.oauth2.server.resource.web.BearerTokenResolver;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;

public final class PublicEndpointIgnoringBearerResolver
        implements BearerTokenResolver {

    private final BearerTokenResolver delegate =
        new DefaultBearerTokenResolver();

    private final RequestMatcher publicEndpoint =
        new AntPathRequestMatcher("/public/**");

    @Override
    public String resolve(HttpServletRequest request) {
        if (publicEndpoint.matches(request)) {
            return null; // Resource Server coi như không có Bearer token.
        }
        return delegate.resolve(request);
    }
}
~~~

Gắn vào Resource Server configuration:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .bearerTokenResolver(new PublicEndpointIgnoringBearerResolver())
    .jwt(Customizer.withDefaults()))
~~~

**Điều kiện và hạn chế:**

1. Đây là lựa chọn kiến trúc có chủ đích, **không** phải hành vi mặc định của `permitAll`.
2. Mã `AntPathRequestMatcher` chỉ minh họa cho các phiên bản còn cung cấp class/API này; ở Spring Security mới hơn, cần dùng `RequestMatcher` tương thích với phiên bản, chẳng hạn matcher MVC/path-pattern phù hợp.
3. Resolver trả `null` khiến **token hợp lệ cũng bị bỏ qua** ở các route public; controller không được mặc định có danh tính JWT tại đó.
4. Nếu sai matcher, đường dẫn bảo vệ có thể bị đối xử như không có token. Trong nhiều trường hợp, hậu quả là 401, nhưng nếu rule `permitAll` đặt nhầm hoặc một cơ chế xác thực khác đang hoạt động, kết quả có thể nghiêm trọng hơn.
5. Nếu còn filter khác (HTTP Basic, session authentication, custom filter), chúng vẫn có thể hoạt động trên endpoint.
6. Chỉ bỏ qua token trên **danh sách public nhỏ, rõ ràng**; không dùng `resolve(...) -> null` cho toàn bộ `/api/**`.

Khi kiến trúc cho phép, **tách SecurityFilterChain** thường giúp trách nhiệm và phạm vi xử lý rõ ràng hơn. Tùy biến resolver hữu ích khi yêu cầu giữ chain chung, nhưng cần kiểm soát và bảo trì matcher cẩn thận.

## 10. Phân biệt `permitAll` với `anonymous`, `authenticated` và `hasAuthority`

Các rule dưới đây thể hiện **yêu cầu authorization**, không thay đổi cách `BearerTokenAuthenticationFilter` xử lý token được gửi:

| Authorization rule | Ý nghĩa |
| --- | --- |
| `permitAll()` | Cho phép mọi request ở bước authorization, dù không có Authentication của người dùng |
| `authenticated()` | Yêu cầu một chủ thể đã được xác thực theo quy tắc Spring Security |
| `anonymous()` | Dành cho request được coi là anonymous theo cơ chế xác thực hiện tại |
| `hasAuthority("SCOPE_orders.read")` | Yêu cầu authority đúng tên `SCOPE_orders.read` |
| `hasRole("ADMIN")` | Trong cấu hình thông dụng, yêu cầu authority `ROLE_ADMIN` |
| `denyAll()` | Từ chối tại bước authorization khi rule được áp dụng |

Ví dụ `anonymous()` khác `permitAll()`: với token hợp lệ, request đã được xác thực có thể **không** được phép qua rule `anonymous()`; ngược lại `permitAll()` không yêu cầu người gọi là anonymous. Với token **không hợp lệ**, filter xác thực vẫn có thể trả 401 trước khi áp dụng cả hai rule.

Không nên coi `permitAll()` là lựa chọn “bỏ qua các bước bảo mật cho request”, và cũng không nên coi `denyAll()` là bước chặn sớm **trước mọi filter xác thực**. Chúng là quyết định của thành phần authorization trong chain.

## 11. CORS preflight, OPTIONS và đường dẫn public

Browser có thể gửi **CORS preflight request** trước một request dùng `Authorization` header:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://frontend.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

Preflight thông thường **không chứa Bearer token**, ngay cả khi request GET tiếp theo có Bearer token. Nếu preflight bị xử lý như request cần access token, frontend có thể gặp lỗi CORS trước khi gửi request thật.

Thực hành phù hợp:

- Cấu hình CORS của Spring Security đúng cách và cho phép origin, method, header cần thiết; không xem `permitAll` là giải pháp đầy đủ cho CORS.
- Đảm bảo CORS preflight được xử lý phù hợp trước khi các yêu cầu xác thực thông thường được áp dụng.
- Không nới lỏng toàn bộ bảo vệ API chỉ để cho phép `OPTIONS` hoạt động.
- Nhớ rằng **preflight** và **request thật** là hai HTTP request khác nhau, nên hành vi Bearer authentication cũng khác nhau.

Ví dụ cấu hình CORS cho một origin được phép trong các phiên bản hỗ trợ:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Bean
UrlBasedCorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration cors = new CorsConfiguration();
    cors.setAllowedOrigins(List.of("https://frontend.example.com"));
    cors.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
    cors.setAllowedHeaders(List.of("Authorization", "Content-Type"));

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/**", cors);
    return source;
}
~~~

Gắn xử lý CORS vào security chain tương ứng:

~~~java
.cors(Customizer.withDefaults())
~~~

Các đoạn code là minh họa về cách tổ chức; cấu hình thực tế cần xác định thêm credentials, allowed methods, response headers và chính sách origin. **CORS không phải authentication**: chấp nhận preflight không có nghĩa chấp nhận một access token sai ở request GET.

## 12. Testing: làm sao chứng minh `permitAll` không bỏ qua token?

Nên tách ba loại kiểm thử:

| Kiểu kiểm thử | Chứng minh điều gì? | Giới hạn |
| --- | --- | --- |
| Unit test của `JwtDecoder`/token validators | JWT hợp lệ hay không theo chữ ký, issuer, thời gian, audience | Chưa xác nhận filter chain áp dụng cho route public |
| MVC integration test với security chain thật | Token có được gửi qua Bearer filter và tạo 401 trên public route hay không | Nếu mock decoder, chưa chứng minh xác minh chữ ký thực |
| Test phân quyền với `jwt()` trong Spring Security Test | Rule `permitAll`/`authenticated`/`hasAuthority` cho Authentication được tạo sẵn | Thường **bỏ qua Bearer filter và JwtDecoder thật**, không đủ để chứng minh hành vi token hỏng |

### 12.1. Các tình huống nên có

Cho ứng dụng có một chain JWT Resource Server và `/public/info` được `permitAll`:

1. **Public, không token:** request vào controller thành công.
2. **Public, token hợp lệ:** request vào controller; nếu controller dùng Authentication, nhận danh tính phù hợp.
3. **Public, token hết hạn:** `JwtDecoder`/validator từ chối token; HTTP response thường là 401.
4. **Public, token sai chữ ký:** bị từ chối, dù rule của route là `permitAll`.
5. **Protected, không token:** bị từ chối vì `authenticated()` hoặc scope rule.
6. **Protected, token hợp lệ nhưng thiếu scope:** authorization từ chối, thường 403.
7. **Public chain riêng không bật Resource Server:** token hỏng không bị Resource Server filter xử lý; endpoint có thể trả 200.
8. **Preflight:** hành vi CORS được xác định rõ, không dựa vào bearer token.

### 12.2. Ví dụ test với MockMvc và decoder giả lập

Trong một **integration test đi qua security filter chain**, có thể thay `JwtDecoder` bằng mock để kiểm soát token “hợp lệ” hay “không hợp lệ” mà vẫn giữ `BearerTokenAuthenticationFilter` thật. Đoạn dưới sử dụng kiểu annotation `@MockitoBean` ở những phiên bản Spring Test hỗ trợ (ví dụ Spring Framework 6.2 trở lên); các phiên bản cũ hơn có cơ chế tương đương, chẳng hạn `@MockBean` của Spring Boot.

~~~java
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidationException;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import java.util.List;

@SpringBootTest
@AutoConfigureMockMvc
class PublicBearerTokenIntegrationTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    JwtDecoder jwtDecoder;

    @Test
    void publicRequestWithoutTokenIsAllowed() throws Exception {
        mvc.perform(get("/public/info"))
            .andExpect(status().isOk());
    }

    @Test
    void publicRequestWithInvalidBearerTokenIsRejected() throws Exception {
        when(jwtDecoder.decode("expired-token")).thenThrow(
            new JwtValidationException(
                "JWT expired",
                List.of(new OAuth2Error("invalid_token", "expired", null))
            )
        );

        mvc.perform(get("/public/info")
                .header("Authorization", "Bearer expired-token"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void publicRequestWithValidBearerTokenIsAllowed() throws Exception {
        Jwt jwt = Jwt.withTokenValue("valid-token")
            .header("alg", "RS256")
            .subject("user-42")
            .issuedAt(Instant.parse("2026-11-15T09:00:00Z"))
            .expiresAt(Instant.parse("2030-11-15T09:00:00Z"))
            .claim("scope", "orders.read")
            .build();

        when(jwtDecoder.decode("valid-token")).thenReturn(jwt);

        mvc.perform(get("/public/info")
                .header("Authorization", "Bearer valid-token"))
            .andExpect(status().isOk());
    }
}
~~~

**Những điều kiện của ví dụ:** ứng dụng test phải có `/public/info`, security chain bật JWT Resource Server và các dependency Spring Boot Test, Spring Security, Mockito tương thích. Annotation `@MockitoBean` không có trong mọi phiên bản; cần dùng API đúng với build. Mã tạo `Jwt` thử nghiệm **không xác minh chữ ký JWS**, vì ở test này decoder đã được mock. Giá trị của test nằm ở việc chứng minh **Bearer filter vẫn gọi decoder trên một endpoint `permitAll`**.

Để chứng minh khả năng **xác minh token thực**, phải bổ sung test với decoder/JWKS hoặc khóa ký thử nghiệm và token được ký hợp lệ. Test sử dụng `jwt()` request post-processor để dựng sẵn Authentication không kiểm tra được vấn đề này.

### 12.3. Kiểm tra nhiều chain

Với cấu hình public chain riêng:

- Gửi `Authorization: Bearer nonsense` vào `/public/info` → không có Resource Server filter trong public chain để gọi decoder.
- Gửi cùng header vào `/api/orders` → Bearer filter của API chain phát hiện và từ chối.
- Gửi request tới route không khớp hai chain → fallback chain phải áp dụng chính sách bạn đã thiết kế.

Đây là cách kiểm tra **phạm vi chain**, không chỉ kiểm tra cấu hình matcher trong authorization.

## 13. Các trường hợp gây hiểu lầm khác

### “Đã cấu hình `permitAll`, tại sao request vẫn nhận 401?”

Có thể request mang **access token đã hết hạn hoặc sai**, và Bearer filter từ chối trước khi tới rule authorization. Ngoài ra cũng có thể có filter tùy chỉnh, HTTP Basic, OAuth2 Login, một chain khác hoặc handler tạo lỗi. Cần kiểm tra security chain nào khớp, có token nào được gửi và ngoại lệ phát sinh ở bước nào.

### “JWT hợp lệ ở endpoint public thì có phải endpoint đó thành protected không?”

Không. `permitAll` vẫn cho phép request **không có token**. JWT hợp lệ chỉ làm cho request có Authentication phù hợp. Nếu controller dùng danh tính đó để cá nhân hóa, đó là tính năng optional authentication, không biến authorization rule thành `authenticated()`.

### “Muốn request public luôn 200 kể cả token sai, có thể nuốt mọi lỗi xác thực?”

Không nên bắt toàn bộ `AuthenticationException` rồi trả thành công trên toàn ứng dụng. Cách này có thể khiến những endpoint bảo vệ bị xử lý sai. Nếu yêu cầu thật là bỏ qua Bearer token trên một vài route, hãy giới hạn ở **chain riêng** hoặc resolver theo matcher được kiểm soát.

### “Nếu public endpoint có `@PreAuthorize` thì `permitAll` ở HTTP có bảo đảm controller được vào không?”

Không. HTTP authorization và **method security** là hai lớp kiểm tra khác nhau. `permitAll` ở lớp request chỉ cho request qua bước HTTP authorization. Một phương thức có `@PreAuthorize("hasAuthority('SCOPE_orders.read')")` vẫn có thể từ chối caller không đủ quyền.

### “Dùng `web.ignoring` cho `/public/**` có an toàn như `permitAll` không?”

Không tương đương. Bỏ qua Spring Security có thể làm mất các filter và security headers vốn vẫn chạy khi dùng `permitAll`. Dùng chain riêng thường cho phép giữ bảo vệ phù hợp mà không xử lý JWT trên những route được chọn.

### “Một security chain đã bị giới hạn bởi `securityMatcher('/api/**')` thì `/public/**` có chắc chắn an toàn?”

Không. Nếu không có fallback chain, public hoặc các đường dẫn khác có thể nằm ngoài Spring Security. Cần nhìn **toàn bộ cấu hình chain**, thứ tự, pattern, route thực và chính sách mặc định khi không có chain phù hợp.

### “Nếu endpoint công khai có filter Bearer, có cần gửi refresh token khi access token hết hạn?”

Không. Resource Server **không** nhận refresh token để truy cập API và không tự làm mới token cho client. Nếu endpoint public không cần danh tính, client thường không cần gắn access token. Nếu gọi một endpoint có bảo vệ, client phải xin access token hợp lệ từ Authorization Server theo grant được hỗ trợ.

## 14. Cách chọn thiết kế cho API thực tế

| Yêu cầu | Cách tiếp cận | Điều cần cân nhắc |
| --- | --- | --- |
| Endpoint public không cần token; token hợp lệ được dùng để cá nhân hóa | `permitAll` trong JWT Resource Server chain | Bearer token **không hợp lệ** có thể làm request thất bại |
| Endpoint public luôn bỏ qua Bearer token được gửi | Public `SecurityFilterChain` riêng **không bật Resource Server** | Không có JWT Authentication trên route đó; giữ các filter khác khi cần |
| Muốn chain chung nhưng bỏ qua Bearer theo đường dẫn rất cụ thể | `BearerTokenResolver` tùy chỉnh | Matcher phải chính xác, không vô tình bỏ token ở route bảo vệ |
| Tài nguyên tĩnh không cần bất kỳ Spring Security filter nào | Cân nhắc `web.ignoring` khi thực sự cần | Mất các bảo vệ/header do Spring Security cung cấp |
| API yêu cầu quyền theo scope | `hasAuthority("SCOPE_...")` hoặc method security phù hợp | Vẫn kiểm tra object-level authorization |
| Browser gọi API cần Bearer token | Cấu hình CORS và Bearer Resource Server | Preflight và request thật phải được xử lý đúng |

Với phần lớn API, điểm khởi đầu an toàn là **giữ Spring Security trên toàn bộ đường dẫn cần bảo vệ**, xác định rõ public route và chỉ loại bỏ xử lý Bearer ở nơi thật sự có nhu cầu. Nếu frontend vô tình gắn token hết hạn vào một request không cần đăng nhập, sửa phía frontend để không gửi token đó đôi khi là thay đổi nhỏ nhất và phù hợp nhất.

## 15. Tóm tắt

**`permitAll()` nghĩa là “không yêu cầu quyền tại bước authorization”, không có nghĩa “không chạy security filters”.** Khi request public đi qua một `SecurityFilterChain` có bật Resource Server, `BearerTokenAuthenticationFilter` vẫn có thể xử lý access token mà client gửi:

~~~text
GET /public/info
  Không Bearer token  -> không cần xác thực -> permitAll -> controller
  Bearer hợp lệ       -> xác thực thành công -> permitAll -> controller
  Bearer không hợp lệ -> lỗi authentication  -> thường 401, chưa tới permitAll
~~~

Để không xử lý bearer token trên route công khai, cần **thiết kế lựa chọn filter chain hoặc Bearer resolver một cách chủ động**. Để giữ endpoint công khai nhưng vẫn biết người dùng đã đăng nhập, có thể dùng `permitAll` cùng xử lý Bearer thông thường và chấp nhận rằng token đã gửi phải hợp lệ. Dù chọn cách nào, **đừng đánh đổi việc xác minh JWT, issuer, audience hoặc quyền đối tượng ở các endpoint bảo vệ** chỉ để làm một route public trả 200.
