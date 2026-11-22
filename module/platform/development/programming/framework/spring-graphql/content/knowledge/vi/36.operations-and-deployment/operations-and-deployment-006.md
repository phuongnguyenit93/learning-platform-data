# CORS và CSRF cho Spring for GraphQL

Khi một ứng dụng web gọi GraphQL API từ domain khác, hai cơ chế bảo mật thường cần được cấu hình cùng nhau là **CORS (Cross-Origin Resource Sharing)** và **CSRF (Cross-Site Request Forgery)**. CORS quyết định trình duyệt có được phép gửi request cross-origin theo chính sách server và đọc response hay không. CSRF bảo vệ những request làm thay đổi trạng thái khi trình duyệt tự động gửi thông tin xác thực như session cookie.

Hai cơ chế giải quyết hai vấn đề khác nhau. CORS không thay thế CSRF, và CSRF cũng không cấu hình quyền truy cập cross-origin. Với Spring for GraphQL, cần tính tới endpoint HTTP mặc định `/graphql`, các request POST, token CSRF trong header, CORS preflight và cách Spring Security xử lý request trước khi GraphQL engine được gọi.

## 1. Origin và site là hai khái niệm khác nhau

Một **origin** được xác định bởi scheme, host và port. Ví dụ:

| URL | Origin |
|---|---|
| `https://app.example.com` | `https://app.example.com` |
| `https://api.example.com` | `https://api.example.com` |
| `http://app.example.com` | `http://app.example.com` |
| `https://app.example.com:8443` | `https://app.example.com:8443` |

Các URL trên là những origin khác nhau nếu một trong ba thành phần scheme, host hoặc port khác nhau. Vì vậy, frontend tại `https://app.example.com` gọi API tại `https://api.example.com` là một request cross-origin.

**Site** được dùng trong chính sách cookie `SameSite`. Hai subdomain có thể khác origin nhưng vẫn thuộc cùng site. Chẳng hạn `https://app.example.com` và `https://api.example.com` khác origin nhưng thường được xem là same-site. Ngược lại, `https://app.example.net` gọi `https://api.example.com` là cross-site.

Phân biệt hai khái niệm này rất quan trọng:

- CORS kiểm tra origin.
- Cookie `SameSite` kiểm soát việc gửi cookie trong ngữ cảnh cross-site.
- CSRF token xác minh request có chứa một giá trị mà trang web bên ngoài không thể tự động có được.

## 2. CORS và CSRF bảo vệ điều gì?

| Cơ chế | Vấn đề cần giải quyết | Thành phần thực thi chính |
|---|---|---|
| CORS | Trang web ở origin khác có được phép gọi API và đọc response không? | Trình duyệt và CORS headers do server trả về. |
| CSRF | Request thay đổi trạng thái có thực sự được khởi tạo từ ứng dụng hợp lệ không? | Server kiểm tra CSRF token hoặc cơ chế chống giả mạo tương đương. |
| Authentication | Request thuộc về người dùng hoặc service nào? | Spring Security, session, bearer token hoặc cơ chế xác thực khác. |
| Authorization | Người gọi có quyền thực hiện hành động hoặc đọc dữ liệu này không? | Spring Security và application/domain policy. |

Ví dụ, người dùng đăng nhập tại `api.example.com` và trình duyệt giữ session cookie. Người dùng mở một trang không đáng tin cậy. Trang đó có thể cố gửi request tới API bằng trình duyệt của người dùng. Nếu cookie được gửi tự động và server không yêu cầu CSRF token, request giả mạo có thể thực hiện thao tác dưới danh tính người dùng.

CORS không tự ngăn được mọi request như vậy. Với một số request đơn giản, trình duyệt vẫn gửi request tới server nhưng không cho JavaScript của origin lạ đọc response. Vì thế, server vẫn cần bảo vệ các thao tác thay đổi trạng thái bằng CSRF khi sử dụng thông tin xác thực tự động gửi kèm.

## 3. CORS hoạt động như thế nào?

Khi JavaScript gọi API ở origin khác, trình duyệt kiểm tra chính sách CORS. Server phản hồi bằng các HTTP header như:

- `Access-Control-Allow-Origin`: origin được phép truy cập.
- `Access-Control-Allow-Methods`: các HTTP method được phép.
- `Access-Control-Allow-Headers`: các request header được phép.
- `Access-Control-Allow-Credentials`: có cho phép request mang credentials hay không.
- `Access-Control-Expose-Headers`: các response header mà JavaScript được phép đọc.
- `Access-Control-Max-Age`: thời gian trình duyệt có thể cache kết quả preflight.

Không phải request cross-origin nào cũng cần preflight. Trình duyệt có thể gửi một **simple request** trực tiếp nếu request đáp ứng các điều kiện của Fetch/CORS, chẳng hạn method và header thuộc nhóm được cho phép. Các request dùng `Content-Type: application/json`, `Authorization` hoặc header tùy chỉnh thường cần preflight.

## 4. CORS preflight là gì?

Preflight là request `OPTIONS` do trình duyệt tự gửi trước request thật để hỏi server xem method và header dự kiến có được phép không.

Ví dụ frontend gửi GraphQL POST với CSRF header:

```http
OPTIONS /graphql HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-xsrf-token
```

Nếu được phép, server phản hồi tương tự:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: Content-Type,X-XSRF-TOKEN
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 1800
```

Sau khi preflight thành công, trình duyệt mới gửi request POST thực tế. Preflight không chứa session cookie. Vì vậy, CORS phải được xử lý trước bước Spring Security yêu cầu người dùng đăng nhập; nếu security filter từ chối OPTIONS trước khi CORS xử lý, trình duyệt sẽ không gửi request GraphQL thật.

## 5. GraphQL HTTP transport và CORS

Spring for GraphQL cung cấp HTTP transport qua `GraphQlHttpHandler`. Với Spring Boot, endpoint mặc định là:

```text
POST /graphql
Content-Type: application/json
```

Body thường chứa `query`, `operationName`, `variables` và `extensions`:

```json
{
  "operationName": "CreateOrder",
  "query": "mutation CreateOrder($input: CreateOrderInput!) { createOrder(input: $input) { order { id } } }",
  "variables": {
    "input": {
      "customerId": "customer-1",
      "items": [{ "productId": "product-1", "quantity": 2 }]
    }
  }
}
```

`application/json` không phải một trong các giá trị `Content-Type` được CORS safelist. Khi frontend gửi GraphQL POST JSON, trình duyệt thường thực hiện preflight. Nếu request còn có `Authorization` hoặc `X-XSRF-TOKEN`, các header đó cũng phải được cho phép.

Spring Boot có các thuộc tính `spring.graphql.cors.*` để cấu hình CORS cho GraphQL endpoint. Với hệ thống có Spring Security, cần bảo đảm cùng một chính sách CORS được tích hợp vào security filter chain để preflight được xử lý trước authentication.

## 6. Cấu hình CORS bằng Spring Boot properties

Với một frontend có origin cố định, có thể cấu hình trong `application.yml`:

```yaml
spring:
  graphql:
    cors:
      allowed-origins:
        - "https://app.example.com"
      allowed-methods:
        - GET
        - POST
      allowed-headers:
        - Content-Type
        - Authorization
        - X-XSRF-TOKEN
        - X-CSRF-TOKEN
      allow-credentials: true
      max-age: 1800s
```

Ý nghĩa:

- `allowed-origins`: chỉ cho phép frontend đã khai báo.
- `allowed-methods`: cho phép các method mà GraphQL transport sử dụng.
- `allowed-headers`: bao gồm JSON content type, bearer authorization nếu có và CSRF header.
- `allow-credentials`: cho phép trình duyệt gửi credentials như cookie khi client bật chế độ credentials.
- `max-age`: cache kết quả preflight trong 30 phút.

Nếu frontend không dùng cookie và không cần HTTP authentication tự động gửi kèm, không bật `allow-credentials` chỉ để làm cho CORS hoạt động. Chỉ bật khi mô hình xác thực thực sự cần.

Nếu JavaScript cần đọc một response header tùy chỉnh, ví dụ token trả trong `X-CSRF-TOKEN`, thêm header đó vào `exposed-headers`:

```yaml
spring:
  graphql:
    cors:
      allowed-origins:
        - "https://app.example.com"
      allowed-methods: [GET, POST]
      allowed-headers: [Content-Type, X-CSRF-TOKEN]
      exposed-headers: [X-CSRF-TOKEN]
      allow-credentials: true
```

`allowed-headers` là danh sách header client được phép gửi. `exposed-headers` là danh sách response header JavaScript được phép đọc. Hai thuộc tính này không thay thế nhau.

## 7. Không dùng wildcard origin với credentials

Khi bật `allow-credentials`, không cấu hình:

```yaml
spring:
  graphql:
    cors:
      allowed-origins: "*"
      allow-credentials: true
```

Trình duyệt không chấp nhận `Access-Control-Allow-Origin: *` cho credentialed request. Server cần trả về một origin cụ thể, ví dụ:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
```

Ưu tiên khai báo chính xác các origin tin cậy. `allowed-origin-patterns` có thể dùng khi có một tập subdomain được kiểm soát, nhưng pattern quá rộng có thể vô tình cho phép các ứng dụng không đáng tin cậy.

Origin là bộ ba scheme, host và port. `https://app.example.com` khác `http://app.example.com` và khác `https://app.example.com:8443`. Giá trị cấu hình không nên có dấu `/` ở cuối.

## 8. Tích hợp CORS vào Spring Security

Spring Security cần xử lý CORS trước bước authentication. Với ứng dụng Spring MVC dùng Servlet stack, có thể khai báo `CorsConfigurationSource` và bật `.cors()` trong `SecurityFilterChain`.

Ví dụ cấu hình tường minh cho GraphQL và endpoint cấp CSRF token:

```java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class GraphQlWebSecurityConfiguration {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration configuration = new CorsConfiguration();
        configuration.setAllowedOrigins(List.of("https://app.example.com"));
        configuration.setAllowedMethods(List.of("GET", "POST"));
        configuration.setAllowedHeaders(List.of(
            "Content-Type",
            "Authorization",
            "X-CSRF-TOKEN",
            "X-XSRF-TOKEN"
        ));
        configuration.setAllowCredentials(true);
        configuration.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/graphql", configuration);
        source.registerCorsConfiguration("/csrf", configuration);
        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .cors(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/csrf").permitAll()
                .requestMatchers("/graphql").authenticated()
                .anyRequest().denyAll()
            );

        return http.build();
    }
}
```

`CorsFilter` được tích hợp vào security chain để xử lý preflight trước authentication. `OPTIONS` preflight không cần session cookie; CORS filter xác minh `Origin`, method và requested headers rồi trả response phù hợp.

Đây là ví dụ Servlet/MVC. Nếu đã dùng một `CorsConfigurationSource` trong security chain, hãy coi nó là nguồn chính sách CORS cho chain đó. Không khai báo nhiều nguồn CORS khác nhau mà không xác định rõ chain nào sử dụng nguồn nào.

Đoạn `application.yml` ở phần trước và bean `CorsConfigurationSource` ở đây là hai cách khai báo cùng một chính sách. Khi dùng bean tường minh cho Spring Security, hãy giữ danh sách origin, method và header đồng nhất; không để properties hoặc reverse proxy tạo một chính sách khác.

## 9. Chọn một nguồn cấu hình CORS nhất quán

Có thể cấu hình CORS qua Spring Boot properties, Spring MVC, `CorsConfigurationSource` hoặc gateway/reverse proxy. Vấn đề thường gặp là nhiều lớp cùng thêm CORS headers với các giá trị khác nhau.

Ví dụ, reverse proxy trả `Access-Control-Allow-Origin: *` trong khi ứng dụng trả origin cụ thể cùng `Access-Control-Allow-Credentials: true`. Browser có thể từ chối response do header trùng hoặc không nhất quán.

Hãy chọn một nơi chịu trách nhiệm rõ ràng:

- Nếu ứng dụng tự xử lý CORS, cấu hình một chính sách cho GraphQL path và kết nối nó với Spring Security.
- Nếu gateway xử lý CORS, đảm bảo gateway có allowlist chính xác và backend không thêm một bộ header xung đột.
- Nếu dùng nhiều `SecurityFilterChain`, cấu hình CORS source tương ứng cho từng chain.

Không dùng CORS để thay thế authentication, authorization hoặc network policy. Các client không chạy trong browser không bị ràng buộc bởi CORS.

## 10. Client gửi cookie trong cross-origin request

Browser `fetch` mặc định không gửi credentials trong cross-origin request. Nếu API xác thực bằng session cookie, frontend cần yêu cầu gửi credentials:

```javascript
const response = await fetch("https://api.example.com/graphql", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json"
  },
  body: JSON.stringify({
    query: "query { currentUser { id email } }"
  })
});
```

Để response được JavaScript đọc, server phải cho phép origin cụ thể và trả `Access-Control-Allow-Credentials: true`. Phía server và client phải đồng ý về việc gửi credentials.

Nếu không cần cookie/session, không đặt `credentials: "include"` chỉ vì đây là GraphQL. Với bearer token, client có thể gửi `Authorization` header và CORS phải cho phép header đó.

## 11. CORS không phải cơ chế chống CSRF

CORS chủ yếu kiểm soát quyền truy cập response của JavaScript trong browser. Một simple cross-origin request có thể được gửi tới server ngay cả khi browser không cho script đọc response. Đây là lý do server vẫn phải chống CSRF.

Một request JSON GraphQL thường kích hoạt preflight, nhưng không nên coi preflight là CSRF token:

- Cấu hình CORS có thể thay đổi hoặc bị mở rộng sai.
- Endpoint có thể hỗ trợ thêm GET hoặc một transport khác.
- Các client không phải browser không áp dụng CORS.
- Một request đơn giản có thể được gửi mà không có preflight.
- CORS không chứng minh request được người dùng chủ động khởi tạo từ giao diện hợp lệ.

CSRF token là giá trị server mong đợi và client phải gửi lại trong một header hoặc parameter không tự động được browser thêm vào request. Server so sánh giá trị đó với token đã lưu.

## 12. CSRF hoạt động như thế nào?

Một cách phòng vệ phổ biến là **synchronizer token pattern**:

1. Server tạo CSRF token gắn với session hoặc một repository.
2. Ứng dụng hợp lệ nhận token qua HTML, cookie hoặc endpoint riêng.
3. Khi gửi request thay đổi trạng thái, client đính kèm token trong header hoặc hidden form field.
4. Spring Security đọc token từ request và so sánh với token server đang lưu.
5. Nếu token thiếu hoặc không khớp, request bị từ chối trước khi vào controller/GraphQL handler.

Kẻ tấn công có thể khiến browser gửi cookie phiên đăng nhập, nhưng trang web khác không thể tự đọc token CSRF từ origin của ứng dụng hợp lệ theo cùng chính sách trình duyệt. Vì vậy, request giả mạo thiếu token hợp lệ sẽ bị từ chối.

## 13. Spring Security bật CSRF mặc định cho unsafe methods

Trong Servlet application, Spring Security bật CSRF protection mặc định cho các HTTP method không an toàn, ví dụ POST, PUT, PATCH và DELETE. Các method an toàn như GET, HEAD, TRACE và OPTIONS không yêu cầu token theo matcher mặc định.

Có thể giữ cấu hình mặc định:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class CsrfConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.csrf(Customizer.withDefaults());
        return http.build();
    }
}
```

Khi ứng dụng dùng session cookie hoặc một credential được browser tự động gửi, giữ CSRF protection là lựa chọn mặc định phù hợp. Không tắt CSRF chỉ vì request body là JSON hoặc endpoint là GraphQL.

## 14. CSRF áp dụng cho GraphQL POST như thế nào?

Spring for GraphQL HTTP transport mặc định nhận POST JSON tại `/graphql`. Spring Security nhìn thấy HTTP method, không phân tích nội dung GraphQL để quyết định query hay mutation.

Vì vậy, khi dùng session/cookie authentication:

- POST query cần CSRF token.
- POST mutation cần CSRF token.
- Một POST subscription qua Server-Sent Events cũng cần token nếu endpoint sử dụng CSRF filter mặc định.
- Request thiếu hoặc sai token bị chặn trước khi GraphQL engine chạy.

CSRF protection không chỉ dành cho mutation. Query phải không có side effect theo GraphQL semantics, nhưng HTTP POST vẫn là unsafe method đối với CSRF matcher mặc định.

Khi CSRF filter từ chối request, client thường nhận HTTP 403. Đây là lỗi ở HTTP/security layer; GraphQL resolver chưa được gọi và response không nhất thiết có cấu trúc GraphQL `data`/`errors`.

## 15. Không bỏ qua CSRF cho toàn bộ `/graphql` khi dùng cookie auth

Một cấu hình dễ gặp nhưng nguy hiểm:

```java
http.csrf(csrf -> csrf
    .ignoringRequestMatchers("/graphql")
);
```

Matcher trên bỏ qua CSRF cho tất cả request GraphQL POST tại endpoint, bao gồm cả mutation tạo đơn hàng, cập nhật hồ sơ hoặc thanh toán. Nếu session cookie được browser tự động gửi, request giả mạo có thể được xử lý dưới session đó.

Không nên bỏ qua CSRF chỉ vì:

- Body là JSON.
- Request mang `Content-Type: application/json`.
- Endpoint chỉ có một URL `/graphql`.
- GraphQL có cả query và mutation.
- Frontend đã bật CORS.

Nếu có một API chain thực sự không dùng credentials tự động gửi kèm, hãy xác định riêng chain đó và mô hình authentication trước khi quyết định tắt CSRF. Không áp dụng ngoại lệ cho GraphQL endpoint dùng session cookie.

## 16. Session token repository

Spring Security mặc định dùng `HttpSessionCsrfTokenRepository` để lưu token trong HTTP session. Đây là lựa chọn phù hợp cho ứng dụng server-rendered hoặc SPA có thể lấy token qua một endpoint.

Token được đưa vào request dưới dạng header hoặc parameter. Header mặc định là `X-CSRF-TOKEN`; request parameter mặc định là `_csrf`.

Với GraphQL JSON request, header thường phù hợp hơn parameter:

```http
POST /graphql HTTP/1.1
Content-Type: application/json
X-CSRF-TOKEN: token-value
Cookie: JSESSIONID=session-id
```

Browser tự gửi session cookie theo cookie policy. JavaScript phải chủ động thêm CSRF header vào POST.

## 17. Cấp CSRF token qua endpoint `/csrf`

Với frontend JavaScript, có thể tạo endpoint riêng để lấy token:

```java
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CsrfController {

    @GetMapping("/csrf")
    CsrfToken csrf(CsrfToken csrfToken) {
        return csrfToken;
    }
}
```

Spring Security cung cấp `CsrfToken` thông qua argument resolver. Nếu frontend cần lấy token trước khi đăng nhập, có thể cho phép GET `/csrf` qua authorization rules:

```java
.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/csrf").permitAll()
    .requestMatchers("/graphql").authenticated()
    .anyRequest().denyAll()
)
```

Khi gọi từ origin khác, `/csrf` cũng cần CORS policy phù hợp. Nếu token được trả trong JSON body, CORS phải cho phép origin frontend đọc response và credentials phải được bật nếu session cookie cần gửi.

Client đọc `headerName` và `token` từ response rồi dùng token làm giá trị của request header tương ứng:

```javascript
const csrfResponse = await fetch("https://api.example.com/csrf", {
  credentials: "include"
});

if (!csrfResponse.ok) {
  throw new Error("Cannot obtain CSRF token");
}

const csrf = await csrfResponse.json();

const graphQlResponse = await fetch("https://api.example.com/graphql", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    [csrf.headerName]: csrf.token
  },
  body: JSON.stringify({
    query: "mutation { cancelOrder(id: \"order-101\") { order { id } } }"
  })
});
```

Ví dụ này dùng session-based CSRF token. Nếu chọn cookie-based SPA token repository, hãy theo đúng request handler và header format của repository đó thay vì trộn hai cách xử lý token.

## 18. Làm mới CSRF token sau login và logout

Spring Security xóa CSRF token hiện tại khi authentication thành công và khi logout thành công. Điều này ngăn token cũ được tiếp tục dùng sau khi thay đổi security context.

Với session-based token repository, frontend nên gọi lại `/csrf`:

- Khi ứng dụng khởi tạo.
- Sau khi đăng nhập thành công.
- Sau khi đăng xuất thành công nếu ứng dụng tiếp tục sử dụng session.
- Khi nhận phản hồi cho biết token không còn hợp lệ và quy trình xác thực cho phép lấy token mới.

Nếu client tiếp tục gửi token cũ sau login, POST `/graphql` có thể bị HTTP 403. Đừng tự động retry mutation với token mới nếu không biết mutation trước đó đã được thực thi hay chưa; cần có idempotency cho thao tác có side effect.

## 19. Cookie-based CSRF token cho SPA

Với SPA, Spring Security cung cấp `CookieCsrfTokenRepository`. Repository này mặc định dùng:

| Thành phần | Giá trị mặc định |
|---|---|
| Cookie name | `XSRF-TOKEN` |
| Request header | `X-XSRF-TOKEN` |
| Request parameter | `_csrf` |

JavaScript đọc cookie `XSRF-TOKEN` và gửi giá trị đó trong header `X-XSRF-TOKEN` cho request unsafe. Cookie này không phải session cookie; nó chỉ chứa CSRF token mà server dùng để so sánh với giá trị client gửi trong header.

Để JavaScript đọc cookie, `CookieCsrfTokenRepository.withHttpOnlyFalse()` đặt `HttpOnly=false`. Chỉ dùng cách này khi ứng dụng thực sự cần JavaScript đọc cookie. Nếu không cần đọc cookie trực tiếp, giữ `HttpOnly` để giảm khả năng script đọc được giá trị.

## 20. Spring Security 7.2: cấu hình SPA ngắn gọn

Trong Spring Security 7.2, có thể dùng helper `spa()` để cấu hình tích hợp CSRF cho SPA:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SpaSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.csrf(csrf -> csrf.spa());
        return http.build();
    }
}
```

Helper này cấu hình cookie repository cho SPA và request handler cần thiết để xử lý raw token trong header trong khi vẫn duy trì BREACH protection cho token được render trong response. Cookie mặc định có tên `XSRF-TOKEN`; client gửi lại giá trị trong `X-XSRF-TOKEN`.

Sau login/logout, cookie CSRF có thể được xóa và tạo lại. Client cần đọc lại cookie mới trước khi gửi POST tiếp theo.

## 21. Spring Security 6.5: cấu hình SPA với request handler

Với Spring Security 6.5, cấu hình SPA cần kết hợp `CookieCsrfTokenRepository` và một `CsrfTokenRequestHandler` tùy chỉnh. Lý do là Spring Security mặc định có BREACH protection: token được đưa vào request attribute có thể được encode/mask, trong khi JavaScript đọc giá trị raw từ cookie.

Đăng ký repository và handler:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

@Configuration
class SpaSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.csrf(csrf -> csrf
            .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
            .csrfTokenRequestHandler(new SpaCsrfTokenRequestHandler())
        );

        return http.build();
    }
}
```

Handler chọn cách resolve token theo nguồn gửi:

```java
import java.util.function.Supplier;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.CsrfTokenRequestAttributeHandler;
import org.springframework.security.web.csrf.CsrfTokenRequestHandler;
import org.springframework.security.web.csrf.XorCsrfTokenRequestAttributeHandler;
import org.springframework.util.StringUtils;

final class SpaCsrfTokenRequestHandler implements CsrfTokenRequestHandler {

    private final CsrfTokenRequestHandler plain = new CsrfTokenRequestAttributeHandler();
    private final CsrfTokenRequestHandler xor = new XorCsrfTokenRequestAttributeHandler();

    @Override
    public void handle(
            HttpServletRequest request,
            HttpServletResponse response,
            Supplier<CsrfToken> csrfToken) {

        this.xor.handle(request, response, csrfToken);
        csrfToken.get();
    }

    @Override
    public String resolveCsrfTokenValue(HttpServletRequest request, CsrfToken csrfToken) {
        String headerValue = request.getHeader(csrfToken.getHeaderName());
        CsrfTokenRequestHandler handler = StringUtils.hasText(headerValue) ? this.plain : this.xor;
        return handler.resolveCsrfTokenValue(request, csrfToken);
    }
}
```

Handler luôn dùng XOR request attribute handler khi chuẩn bị token cho response để giữ BREACH protection. Khi client gửi header lấy từ cookie raw token, handler dùng plain resolver. Khi token đến từ request parameter như hidden field của HTML form, handler dùng XOR resolver.

Đây là ví dụ dành cho Servlet stack. Không dùng `CsrfTokenRequestHandler` của Servlet trong cấu hình WebFlux; reactive stack có API và context riêng.

## 22. Gửi CSRF cookie trong GraphQL fetch

Khi SPA và API cùng origin hoặc cookie có phạm vi domain phù hợp, JavaScript có thể đọc `XSRF-TOKEN`:

```javascript
function readCookie(name) {
  const prefix = `${name}=`;
  const value = document.cookie
    .split(";")
    .map(item => item.trim())
    .find(item => item.startsWith(prefix));

  return value ? decodeURIComponent(value.slice(prefix.length)) : undefined;
}

async function executeGraphQl(query, variables) {
  const token = readCookie("XSRF-TOKEN");

  if (!token) {
    throw new Error("CSRF token is missing; refresh the application token first");
  }

  return fetch("https://api.example.com/graphql", {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-XSRF-TOKEN": token
    },
    body: JSON.stringify({ query, variables })
  });
}
```

Header `X-XSRF-TOKEN` phải nằm trong `allowed-headers` của CORS. Vì đây là header tùy chỉnh, browser sẽ gửi preflight trước GraphQL POST.

Nếu cookie không thể đọc từ origin frontend, không cố truy cập cookie của host khác bằng JavaScript. Dùng session-based `/csrf` endpoint hoặc một thiết kế cấp token phù hợp với domain/cookie policy.

## 23. Cookie domain khi frontend và API khác subdomain

Giả sử:

- Frontend: `https://app.example.com`.
- GraphQL API: `https://api.example.com`.

Hai URL khác origin nhưng cùng site. Cookie đặt host-only cho `api.example.com` sẽ được gửi tới API, nhưng JavaScript chạy trên `app.example.com` không thể đọc cookie đó.

Có hai hướng thiết kế thường gặp:

1. Dùng session-based CSRF token endpoint `/csrf`, để frontend lấy token qua một response được CORS cho phép.
2. Cấu hình cookie domain dùng chung như `.example.com` nếu chính sách bảo mật cho phép các subdomain cùng tin cậy.

Chia sẻ cookie cho toàn bộ subdomain mở rộng phạm vi các host có thể nhận cookie. Chỉ dùng khi kiểm soát tất cả subdomain và hiểu rõ rủi ro của chúng.

## 24. SameSite, Secure và cross-site cookie

Cookie `SameSite` điều khiển khi browser gửi cookie trong request cross-site:

| Giá trị | Hành vi khái quát | Trường hợp dùng |
|---|---|---|
| `Strict` | Không gửi cookie trong hầu hết ngữ cảnh cross-site. | Ứng dụng có thể giữ trải nghiệm chặt chẽ mà không cần cookie ở luồng điều hướng ngoài site. |
| `Lax` | Cho phép một số điều hướng top-level an toàn, chặn phần lớn cross-site subrequest. | Lựa chọn mặc định phù hợp cho nhiều session cookie. |
| `None` | Cho phép gửi cookie cross-site nếu browser policy cho phép; yêu cầu `Secure`. | Frontend và API ở các site khác nhau cần cookie credentials. |

`SameSite` là lớp phòng vệ bổ sung, không thay thế CSRF token. Hai subdomain khác origin có thể vẫn same-site; vì vậy SameSite không chứng minh request đến từ đúng frontend origin.

Với cross-site cookie, thường phải dùng `SameSite=None; Secure`. Tuy nhiên, chính sách third-party cookie của browser có thể chặn cookie dù server đã bật CORS credentials. CORS không thể buộc browser chấp nhận third-party cookie.

## 25. Tùy chỉnh cookie CSRF

`CookieCsrfTokenRepository` cho phép tùy chỉnh cookie. Ví dụ với Servlet stack:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

@Configuration
class CsrfCookieConfiguration {

    @Bean
    CookieCsrfTokenRepository csrfTokenRepository() {
        CookieCsrfTokenRepository repository = CookieCsrfTokenRepository.withHttpOnlyFalse();
        repository.setCookieCustomizer(cookie -> cookie
            .secure(true)
            .sameSite("Lax")
            .path("/")
        );
        return repository;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            CookieCsrfTokenRepository csrfTokenRepository) throws Exception {

        http.csrf(csrf -> csrf
            .csrfTokenRepository(csrfTokenRepository)
            .csrfTokenRequestHandler(new SpaCsrfTokenRequestHandler())
        );
        return http.build();
    }
}
```

Đây là ví dụ cho frontend cùng site. Nếu triển khai cross-site, cần đánh giá `SameSite=None` và `Secure`, đồng thời kiểm tra chính sách cookie của browser. Không cấu hình `Domain` rộng hơn mức cần thiết.

Ví dụ dùng `SpaCsrfTokenRequestHandler` đã định nghĩa ở phần Spring Security 6.5. Với Spring Security 7.2, có thể dùng helper `csrf.spa()` nếu không cần tùy chỉnh cookie repository. Không khai báo bean repository riêng rồi giả định Spring Security tự động dùng bean đó.

`CsrfCookieConfiguration` là một cách cấu hình thay thế cho phần CSRF trong `GraphQlWebSecurityConfiguration` trước đó. Khi ghép vào một ứng dụng, hãy dùng một `SecurityFilterChain` phù hợp và kết hợp cả CORS lẫn CSRF trong chain đó; không đăng ký hai chain mặc định cùng bắt mọi request.

## 26. Cookie authentication và bearer token khác nhau ở CSRF

CSRF dựa trên việc browser tự động gửi credential mà trang web khác có thể lợi dụng.

| Cách xác thực | Browser có tự động gửi credential? | CSRF cần xem xét? |
|---|---|---|
| Session cookie | Có, theo cookie policy | Có. |
| JWT/access token trong cookie | Có, theo cookie policy | Có. Token là JWT không làm mất rủi ro CSRF. |
| HTTP Basic đã lưu trong browser | Có thể được browser tự gửi | Có thể cần CSRF protection. |
| Bearer token trong `Authorization` do JavaScript chủ động thêm | Không tự động gắn bởi browser | CSRF cổ điển thường không áp dụng nếu không có cookie/credential tự động khác. |
| API key do server-to-server client gửi | Không phải credential browser tự động gửi | CSRF browser thường không phải mối đe dọa chính. |

Một API “stateless” vẫn có thể bị CSRF nếu nó xác thực bằng JWT lưu trong cookie. Ngược lại, một API nhận bearer token chỉ qua `Authorization` header và không có cookie/session authentication có thể có lý do để tắt CSRF cho security chain riêng.

Không quyết định tắt CSRF chỉ dựa trên việc token có định dạng JWT hoặc server không lưu session. Hãy xác định credential nào browser tự động đính kèm vào request.

## 27. Khi nào có thể tắt CSRF?

Một API chỉ nhận bearer token trong `Authorization` header, không dùng cookie để xác thực và không có cơ chế browser tự động gửi credential khác, có thể không cần CSRF protection.

Ví dụ, một filter chain dành riêng cho API stateless:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class StatelessApiSecurityConfiguration {

    @Bean
    SecurityFilterChain statelessApi(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/service-api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .oauth2ResourceServer(resourceServer -> resourceServer.jwt());

        return http.build();
    }
}
```

Ví dụ này chỉ minh họa một API chain tách biệt. Không sao chép `.csrf(disable)` vào chain phục vụ web session hoặc GraphQL cookie-auth. Cần bảo đảm endpoint trong chain chỉ chấp nhận bearer authentication và không fallback sang cookie/session.

Nếu cùng một `/graphql` endpoint phục vụ cả cookie session và bearer token, việc tắt CSRF toàn endpoint có thể mở lại lỗ hổng cho client dùng cookie. Hãy thiết kế các security chain hoặc endpoint rõ ràng thay vì dựa vào header do client tự khai báo để quyết định có bỏ qua CSRF hay không.

## 28. HTTP GET của GraphQL và CSRF

Spring for GraphQL có thể bật HTTP GET, nhưng mặc định GET bị tắt. GET chỉ được dùng cho query; mutation gửi qua GET bị từ chối.

GET là HTTP safe method nên Spring Security không yêu cầu CSRF token cho GET. Điều này không có nghĩa nên chuyển mutation sang GET. Mutation phải luôn dùng method không an toàn như POST và có CSRF protection khi dùng cookie authentication.

Trước khi bật GET, lưu ý:

- Query và variables xuất hiện trong URL, có thể được ghi vào access log, browser history, `Referer` hoặc proxy cache.
- GET không có Content-Type thường là CORS simple request và không cần preflight.
- Browser có thể gửi GET kèm cookie ngay cả khi script ở origin khác không đọc được response.
- Resolver của Query không được tạo side effect.
- Rate limit, chi phí query và audit logging vẫn cần được áp dụng.

Vì vậy, GET phù hợp khi có nhu cầu cache hoặc client chỉ hỗ trợ GET và query không chứa dữ liệu nhạy cảm. Không dùng GET để lách CSRF.

## 29. Server-Sent Events và WebSocket subscriptions

Spring for GraphQL hỗ trợ subscription qua Server-Sent Events hoặc WebSocket. Mỗi transport có mô hình bảo mật khác nhau.

**Server-Sent Events (SSE):** request POST là mặc định, nên CSRF filter bảo vệ như các POST khác. Nếu bật GET cho SSE, hãy nhớ GET là safe method và không yêu cầu CSRF token. CORS HTTP vẫn áp dụng.

**WebSocket:** WebSocket handshake không dùng CORS preflight như HTTP fetch. Cần kiểm tra `Origin` và chỉ cho phép origin tin cậy. Spring Framework mặc định giới hạn WebSocket request ở same-origin; nếu mở cross-origin, hãy khai báo allowlist rõ ràng.

Spring Boot không bật GraphQL WebSocket endpoint mặc định. Khi bật endpoint, cần cấu hình path và dependency tương ứng. Spring for GraphQL cung cấp `AuthenticationWebSocketInterceptor` để lấy thông tin xác thực từ payload `connection_init` và truyền security context tới các request sau đó.

Origin allowlist không thay thế authentication. Hãy xác thực kết nối, giới hạn subscription và kiểm tra authorization cho dữ liệu được phát ra. Không áp dụng nhầm CORS HTTP properties cho WebSocket handshake.

## 30. Spring WebFlux và CORS

Nếu ứng dụng dùng WebFlux, Spring Security sử dụng reactive security chain. CORS source thuộc package reactive, không phải Servlet.

Ví dụ cấu hình reactive CORS source:

```java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
class ReactiveCorsConfiguration {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration configuration = new CorsConfiguration();
        configuration.setAllowedOrigins(List.of("https://app.example.com"));
        configuration.setAllowedMethods(List.of("GET", "POST"));
        configuration.setAllowedHeaders(List.of(
            "Content-Type", "Authorization", "X-XSRF-TOKEN"
        ));
        configuration.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/graphql", configuration);
        source.registerCorsConfiguration("/csrf", configuration);
        return source;
    }
}
```

Reactive security chain dùng `ServerHttpSecurity` và reactive CORS configuration source. Không đưa `CorsConfigurationSource` Servlet vào `SecurityWebFilterChain`.

CSRF trong WebFlux cũng được hỗ trợ bởi Spring Security, nhưng cách cấu hình token và test dùng reactive APIs. Hãy dùng đúng `ServerHttpSecurity`, `ServerCsrfTokenRepository` và test support tương ứng với phiên bản Spring Security của ứng dụng.

## 31. Kiểm thử CORS preflight bằng MockMvc

Test CORS cần đi qua HTTP/security filter chain. `GraphQlTester` chạy trực tiếp GraphQL execution không đủ để xác minh CORS filter.

Ví dụ test preflight cho Servlet application:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class GraphQlCorsTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void allowsPreflightFromConfiguredFrontend() throws Exception {
        mockMvc.perform(options("/graphql")
                .header(HttpHeaders.ORIGIN, "https://app.example.com")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "content-type,x-xsrf-token"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://app.example.com"))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS,
                "true"));
    }
}
```

Test này xác minh preflight được xử lý và origin được echo cụ thể. Có thể bổ sung assertion cho allowed methods và allowed headers nếu muốn kiểm tra chặt chẽ hơn.

## 32. Kiểm thử origin không được phép

Origin không nằm trong allowlist không được nhận `Access-Control-Allow-Origin` hợp lệ:

```java
@Test
void doesNotAllowUnknownOrigin() throws Exception {
    mockMvc.perform(options("/graphql")
            .header(HttpHeaders.ORIGIN, "https://evil.example.net")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS, "content-type"))
        .andExpect(status().isForbidden())
        .andExpect(header().doesNotExist(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
}
```

Với Spring Framework `CorsProcessor` mặc định, preflight từ origin không được phép trả HTTP 403. Nếu CORS được xử lý ở gateway hoặc reverse proxy, status có thể phụ thuộc cấu hình của lớp đó; trong mọi trường hợp, không được trả `Access-Control-Allow-Origin` cho origin không tin cậy.

## 33. Kiểm thử CSRF cho GraphQL POST

CSRF test phải đi qua Spring Security filter chain. Dùng `spring-security-test` và MockMvc cho Servlet stack:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Ví dụ request POST thiếu token:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class GraphQlCsrfTests {

    @Autowired
    MockMvc mockMvc;

    private static final String QUERY = """
        { "query": "query { greeting }" }
        """;

    @Test
    void rejectsGraphQlPostWithoutCsrfToken() throws Exception {
        mockMvc.perform(post("/graphql")
                .with(user("alice"))
                .contentType(MediaType.APPLICATION_JSON)
                .content(QUERY))
            .andExpect(status().isForbidden());
    }
}
```

Ví dụ giả định schema có query `greeting` và endpoint được yêu cầu authentication. CSRF filter từ chối request trước khi resolver chạy, vì vậy status là 403.

## 34. Kiểm thử request có CSRF token hợp lệ

Spring Security test cung cấp `csrf()` request post processor để thêm token hợp lệ:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;

@Test
void acceptsGraphQlPostWithValidCsrfToken() throws Exception {
    mockMvc.perform(post("/graphql")
            .with(user("alice"))
            .with(csrf())
            .contentType(MediaType.APPLICATION_JSON)
            .content(QUERY))
        .andExpect(status().isOk());
}
```

Response 200 giả định query hợp lệ và resolver chạy thành công. Nếu query hoặc schema không hợp lệ, kết quả GraphQL phụ thuộc response media type và phiên bản transport; mục tiêu của test này là chứng minh CSRF filter cho request đi tiếp.

## 35. Kiểm thử token không hợp lệ

Có thể xác minh token sai cũng bị từ chối:

```java
@Test
void rejectsGraphQlPostWithInvalidCsrfToken() throws Exception {
    mockMvc.perform(post("/graphql")
            .with(user("alice"))
            .with(csrf().useInvalidToken())
            .contentType(MediaType.APPLICATION_JSON)
            .content(QUERY))
        .andExpect(status().isForbidden());
}
```

Nên có cả ba test: thiếu token, token sai và token đúng. Chỉ kiểm tra request thành công có token không chứng minh filter sẽ từ chối request thiếu token.

## 36. Kiểm thử token ở GraphQlTester và HTTP tester

`GraphQlTester` có nhiều implementation. Nếu dùng tester trực tiếp với `ExecutionGraphQlService`, request không đi qua Servlet filter chain, do đó test đó không chứng minh CORS hoặc CSRF hoạt động.

Để kiểm thử security transport:

- Dùng MockMvc cho Spring MVC.
- Dùng `WebTestClient` và Spring Security reactive test support cho WebFlux.
- Gửi request tới đúng HTTP endpoint `/graphql`.
- Kiểm tra HTTP status và CORS headers trước khi kiểm tra GraphQL response.

Sau đó dùng `GraphQlTester` để kiểm thử schema, resolver, payload và lỗi GraphQL ở tầng execution. Hai nhóm test bổ sung cho nhau.

## 37. Xử lý HTTP 403 do CSRF ở frontend

Nếu frontend nhận 403 khi gọi GraphQL, cần xác định lỗi đến từ đâu:

1. Kiểm tra request có được gửi tới `/graphql` không.
2. Kiểm tra session cookie hoặc credential đã được gửi chưa.
3. Kiểm tra CSRF header có trong request không.
4. Kiểm tra token có phải token mới nhất sau login/logout không.
5. Kiểm tra header đó đã được CORS `allowed-headers` cho phép chưa.
6. Kiểm tra CORS preflight có thành công trước request thật không.
7. Kiểm tra Spring Security log để phân biệt missing token và invalid token.

Nếu preflight thất bại, browser thường báo CORS/network error và không gửi POST thật. Nếu preflight thành công nhưng CSRF token thiếu hoặc sai, POST bị security filter trả 403.

Không tự động retry mutation khi gặp 403 nếu không biết request đã tới application hay chưa. CSRF filter thường chặn trước GraphQL execution, nhưng frontend nên làm mới token rồi chỉ gửi lại thao tác khi có thể xác định request trước đó không tạo side effect.

## 38. Những lỗi cấu hình thường gặp

**Cho phép `allowed-origins: "*"` cùng credentials.** Browser từ chối credentialed response. Dùng origin cụ thể hoặc origin pattern có kiểm soát.

**Quên `X-XSRF-TOKEN` trong allowed headers.** Preflight thất bại dù origin và POST đã được cho phép. Thêm đúng header CSRF client gửi.

**Quên bật credentials ở client.** Session cookie không được gửi trong cross-origin fetch. Dùng `credentials: "include"` khi xác thực bằng cookie.

**Bật `allow-credentials` nhưng không có cookie authentication.** Cấu hình credentials không cần thiết làm tăng phạm vi truy cập. Chỉ bật khi mô hình auth cần.

**Để Spring Security chặn OPTIONS trước CORS.** Preflight không có session cookie. Cấu hình CORS trước authentication qua `.cors()` và một source hợp lệ.

**Tắt CSRF cho toàn `/graphql`.** Toàn bộ mutation dùng cookie auth mất lớp bảo vệ. Giữ CSRF mặc định và cấp token cho frontend.

**Cho rằng POST JSON tự miễn CSRF.** Spring Security bảo vệ unsafe HTTP methods, bất kể body là JSON hay GraphQL.

**Cho rằng JWT luôn miễn CSRF.** JWT lưu trong cookie vẫn là credential browser tự động gửi. Xác định nơi lưu và cách gửi token.

**Không làm mới token sau login/logout.** Token cũ bị xóa nên POST tiếp theo nhận 403. Lấy token mới sau khi security context thay đổi.

**Dùng CORS như authorization.** Client không phải browser có thể gọi API bất kể CORS. Luôn xác thực và phân quyền server-side.

**Bật GET để né CSRF.** GET chỉ dành cho query an toàn và không được có side effect. Không dùng GET cho mutation.

**Áp dụng HTTP CORS cho WebSocket.** WebSocket handshake cần origin validation riêng và xác thực kết nối.

## 39. Checklist triển khai CORS và CSRF

- [ ] Liệt kê chính xác origin frontend theo scheme, host và port.
- [ ] Chỉ cho phép HTTP method GraphQL thực sự sử dụng.
- [ ] Cho phép `Content-Type`, `Authorization` và CSRF header cần thiết.
- [ ] Chỉ bật `allow-credentials` khi browser cần gửi cookie/credential.
- [ ] Không dùng wildcard origin cho credentialed request.
- [ ] Xử lý CORS preflight trước authentication.
- [ ] Giữ CSRF protection cho GraphQL POST khi dùng cookie/session authentication.
- [ ] Cấp token cho frontend qua cookie SPA hoặc endpoint `/csrf`.
- [ ] Làm mới token sau login và logout.
- [ ] Không bỏ qua CSRF cho toàn bộ `/graphql` nếu endpoint nhận cookie auth.
- [ ] Phân biệt bearer header với JWT trong cookie.
- [ ] Chỉ bật GET cho query side-effect-free và hiểu rủi ro URL logging.
- [ ] Cấu hình origin và authentication riêng cho GraphQL WebSocket.
- [ ] Kiểm thử preflight, origin không được phép, CSRF thiếu/sai/đúng.
- [ ] Dùng HTTP-level test để xác minh security filter chain.

## Kết luận

CORS và CSRF cần được thiết kế như hai lớp bảo vệ riêng cho GraphQL HTTP API. CORS giới hạn origin mà browser được phép gọi và đọc response; CSRF bảo vệ request unsafe dùng credential tự động gửi kèm. Spring Boot cung cấp `spring.graphql.cors.*`, Spring Security tích hợp CORS qua `.cors()` và bảo vệ POST mặc định bằng CSRF filter. Với SPA, có thể dùng `CookieCsrfTokenRepository` cùng `X-XSRF-TOKEN` hoặc session token endpoint `/csrf`. Giữ origin allowlist chính xác, xử lý preflight trước authentication, làm mới token sau login/logout và kiểm thử qua HTTP filter chain để bảo đảm GraphQL mutation không bị bỏ quên lớp bảo vệ.

## Tài liệu tham khảo

- [Spring Boot — Spring for GraphQL and CORS](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [Spring Boot — Application Properties (`spring.graphql.cors.*`)](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Spring Security — CORS Integration](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html)
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring GraphQL — Server Transports](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring GraphQL — WebSocket Authentication](https://docs.spring.io/spring-graphql/reference/transports.html#server-transports-websocket)
- [Spring Framework — WebSocket Allowed Origins](https://docs.spring.io/spring-framework/reference/web/websocket/server.html)
- [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
- [MDN — Cross-Site Request Forgery](https://developer.mozilla.org/en-US/docs/Web/Security/Attacks/CSRF)
