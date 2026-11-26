# CorsWebFilter và cấu hình cho WebFlux

## 1. Bài toán CORS trong ứng dụng Reactive

Giả sử một frontend chạy tại `https://app.example.com` sử dụng Fetch để gọi API WebFlux tại `https://api.example.com`. API có các endpoint đọc sản phẩm, xem tài khoản đang đăng nhập và cập nhật hồ sơ. Spring Security WebFlux cần bảo vệ dữ liệu bằng authentication, authorization và CSRF khi phù hợp; đồng thời, trình duyệt phải được phép trao response CORS cho JavaScript ở frontend tin cậy.

Ví dụ frontend gọi:

~~~javascript
const response = await fetch("https://api.example.com/api/profile", {
  method: "PUT",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": "<csrf-token>"
  },
  body: JSON.stringify({ displayName: "Lan" })
});

if (!response.ok) {
  throw new Error("HTTP " + response.status);
}
~~~

Đây là yêu cầu khác origin. Trình duyệt thường gửi **preflight OPTIONS** trước vì `PUT` không phải CORS-safelisted method, `application/json` không phải giá trị `Content-Type` safelisted và `X-CSRF-TOKEN` là header tùy biến. Preflight không gửi cookie/session của actual request như cách một request đăng nhập thông thường thực hiện.

Nếu Spring Security yêu cầu đăng nhập ngay trên preflight, browser có thể nhận 401/403 và không bao giờ gửi actual `PUT`. Đó là lý do CORS phải được xử lý **đủ sớm trong pipeline WebFlux**.

Trong mô-đun `SPRING_SECURITY_HTTP_PROTECTION`, CORS phối hợp với CSRF, security headers, CSP, HSTS, HTTP firewall và bảo vệ session. Bài này tập trung vào **`CorsWebFilter`, cấu hình CORS cho WebFlux và tích hợp Spring Security Reactive**; các cơ chế bảo vệ còn lại vẫn cần được duy trì riêng.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vai trò của `CorsWebFilter`, `CorsConfiguration` và `CorsConfigurationSource` trong Reactive.
2. Phân biệt `CorsWebFilter` với `CorsFilter` của Servlet; biết đường dẫn package phù hợp.
3. Cấu hình CORS thông qua `ServerHttpSecurity.cors(...)` hoặc đăng ký `CorsWebFilter` độc lập, tránh xử lý trùng.
4. Giải thích preflight OPTIONS và actual request được xử lý khác nhau như thế nào.
5. Cấu hình origin, method, request header, exposed header và credentials một cách có chủ đích.
6. Kiểm thử bằng `WebTestClient`, DevTools, `curl` và chẩn đoán xung đột giữa WebFlux, Spring Security, gateway và cookie/session.

Các hostname `example.com` và `example.org` bên dưới là tên miền minh họa.

## 2. Các thành phần CORS trong WebFlux

Spring WebFlux sử dụng chuỗi **WebFilter**, không phải Servlet Filter của Spring MVC. Spring Security Reactive tích hợp bảo mật vào chuỗi WebFilter qua `SecurityWebFilterChain` và `WebFilterChainProxy`.

| Thành phần | Package điển hình | Nhiệm vụ |
| --- | --- | --- |
| `CorsConfiguration` | `org.springframework.web.cors` | Chứa các quy tắc origin, methods, headers, credentials, preflight cache |
| `CorsConfigurationSource` | `org.springframework.web.cors.reactive` | Tìm `CorsConfiguration` cho `ServerWebExchange` hiện tại |
| `UrlBasedCorsConfigurationSource` | `org.springframework.web.cors.reactive` | Ánh xạ path request sang cấu hình CORS |
| `CorsWebFilter` | `org.springframework.web.cors.reactive` | Áp dụng CORS ở tầng WebFilter, xử lý cả preflight và actual request |
| `DefaultCorsProcessor` | `org.springframework.web.cors.reactive` | Kiểm tra request CORS và tạo response headers phù hợp |
| `ServerHttpSecurity` | `org.springframework.security.config.web.server` | Xây dựng chuỗi bảo mật Reactive và cấu hình tích hợp CORS |
| `SecurityWebFilterChain` | `org.springframework.security.web.server` | Chứa các bước bảo mật áp dụng cho request trong WebFlux |

**Phân biệt quan trọng:** Servlet có `org.springframework.web.filter.CorsFilter` và nguồn cấu hình Servlet; Reactive có `org.springframework.web.cors.reactive.CorsWebFilter` và nguồn cấu hình Reactive. Hai nhánh cùng chia sẻ lớp dữ liệu `CorsConfiguration` nhưng sử dụng request/context khác nhau.

Ví dụ phương thức cốt lõi của nguồn Reactive có dạng:

~~~java
CorsConfiguration getCorsConfiguration(ServerWebExchange exchange);
~~~

Nó nhận `ServerWebExchange` thay vì `HttpServletRequest`. Không nhập nhằng hai interface cùng tên `CorsConfigurationSource` khi import.

### 2.1. CorsConfiguration mô tả các quyền gì?

~~~java
CorsConfiguration config = new CorsConfiguration();
config.setAllowedOrigins(List.of("https://app.example.com"));
config.setAllowedMethods(List.of("GET", "POST", "PUT"));
config.setAllowedHeaders(List.of(
    "Authorization", "Content-Type", "X-CSRF-TOKEN"
));
config.setExposedHeaders(List.of("X-Request-Id"));
config.setAllowCredentials(true);
config.setMaxAge(600L);
~~~

- `allowedOrigins`: origin frontend cụ thể được cấp quyền CORS.
- `allowedMethods`: phương thức HTTP actual request được phép qua kiểm tra preflight.
- `allowedHeaders`: tên request header mà preflight có thể cho phép.
- `exposedHeaders`: tên response header bổ sung mà JavaScript được đọc trên actual response.
- `allowCredentials(true)`: cho phép phản hồi CORS hỗ trợ credentials mode; không tạo cookie, token hay session.
- `maxAge(600L)`: thời gian cho phép browser cache kết quả preflight, tùy giới hạn browser.

Chính sách CORS **không** cho user quyền sửa hồ sơ hoặc xem tài khoản của người khác. Authentication và authorization phải kiểm tra riêng trên actual request.

## 3. CorsWebFilter xử lý preflight và actual request ra sao?

Trong luồng xử lý Reactive, `CorsWebFilter` có thể thực hiện ba việc quan trọng:

1. Yêu cầu `CorsConfigurationSource` trả cấu hình phù hợp với request.
2. Dùng CORS processor để kiểm tra `Origin`, method và request headers theo ngữ cảnh.
3. Nếu request là preflight hoặc bị từ chối, hoàn tất response mà không thực hiện tiếp handler bình thường; với actual request hợp lệ, chuyển tiếp đến các filter/handler phía sau.

~~~mermaid
flowchart TD
    A["Browser gửi HTTP request"] --> B["CORS layer trong WebFlux"]
    B --> C["CorsConfigurationSource chọn policy theo path"]
    C --> D{"Có cấu hình và kiểm tra CORS đạt?"}
    D -- "Không" --> E["Preflight hoặc request CORS không hợp lệ: từ chối"]
    D -- "Có" --> F{"Preflight OPTIONS?"}
    F -- "Có" --> G["Trả Allow-Origin/Methods/Headers; dừng preflight"]
    F -- "Không" --> H["Actual request tiếp tục trong security chain"]
    H --> I["Authentication, authorization, CSRF khi áp dụng"]
    I --> J["Handler WebFlux trả actual response"]
    J --> K["Browser kiểm tra CORS và chia sẻ response nếu hợp lệ"]
~~~

Sơ đồ mô tả các quyết định logic. Nếu một request không có header `Origin`, nó thường không phải CORS request theo nghĩa browser cần kiểm tra, nên xử lý CORS có thể không áp dụng. Điều đó **không chứng minh client an toàn**.

### 3.1. Preflight OPTIONS

Preflight của ví dụ `PUT /api/profile`:

~~~http
OPTIONS /api/profile HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: PUT
Access-Control-Request-Headers: content-type, x-csrf-token
~~~

Phần `Access-Control-Request-Method` cho biết method của **actual request**, không phải method của preflight. `Access-Control-Request-Headers` chỉ liệt kê các tên header mà browser định gửi; không mang giá trị token.

Với chính sách mục 2, response hợp lệ có thể là:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET,POST,PUT
Access-Control-Allow-Headers: Content-Type,X-CSRF-TOKEN
Access-Control-Max-Age: 600
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Browser kiểm tra quyền CORS rồi mới gửi actual `PUT`. Nếu preflight không đạt, **actual request của luồng này không được browser gửi**. `OPTIONS` bình thường không cần cookie hay token xác thực của user.

### 3.2. Actual request

Sau preflight thành công, browser gửi request thực tế:

~~~http
PUT /api/profile HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Content-Type: application/json
X-CSRF-TOKEN: <valid-csrf-token>
Cookie: SESSION=<session-id-if-browser-allows>

{"displayName":"Lan"}
~~~

Phần xử lý CORS có thể chấp nhận origin rồi cho actual request đi tiếp. Spring Security vẫn xác thực session/token, kiểm tra quyền user và CSRF token đối với thao tác thay đổi trạng thái khi thiết kế yêu cầu.

Ví dụ actual response:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Browser còn kiểm tra CORS trên **actual response** để quyết định JavaScript được đọc kết quả không. Nếu API trả 401/403 vì session hoặc CSRF nhưng response có CORS hợp lệ, frontend có thể đọc status và xử lý. Nếu thiếu header CORS, frontend có thể chỉ thấy lỗi CORS và không biết HTTP status của response gốc.

### 3.3. Không phải tất cả request cross-origin đều có preflight

Ví dụ:

~~~javascript
await fetch("https://api.example.com/api/products");
~~~

Một `GET` thông thường không đặt header tùy biến có thể đi thẳng tới API mà không gửi OPTIONS. Tuy vậy actual response vẫn phải trả `Access-Control-Allow-Origin` hợp lệ nếu JavaScript cần đọc body.

Ngược lại `GET` có `Authorization` do JavaScript đặt thường cần preflight vì `Authorization` không phải CORS-safelisted request header.

## 4. Phương án A: tích hợp CORS trực tiếp vào ServerHttpSecurity

Với ứng dụng đã sử dụng Spring Security Reactive, cách rõ ràng là khai báo `CorsConfigurationSource` reactive và chỉ định cho `ServerHttpSecurity.cors(...)`. Nhờ đó CORS được xử lý tại vị trí phù hợp trong security pipeline.

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
class ReactiveSecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        CorsConfiguration apiCors = new CorsConfiguration();
        apiCors.setAllowedOrigins(List.of("https://app.example.com"));
        apiCors.setAllowedMethods(List.of("GET", "POST", "PUT"));
        apiCors.setAllowedHeaders(List.of(
            "Authorization", "Content-Type", "X-CSRF-TOKEN"
        ));
        apiCors.setExposedHeaders(List.of("X-Request-Id"));
        apiCors.setAllowCredentials(true);
        apiCors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", apiCors);

        return http
            .cors(cors -> cors.configurationSource(source))
            .authorizeExchange(auth -> auth
                .pathMatchers("/api/public/**").permitAll()
                .pathMatchers("/api/**").authenticated()
                .anyExchange().denyAll())
            .build();
    }
}
~~~

**Cách đọc đoạn mã:**

- `UrlBasedCorsConfigurationSource` là **bản reactive**, không phải class Servlet có tên giống hệt.
- `registerCorsConfiguration("/api/**", apiCors)` chọn policy cho các URL path như `/api/profile` và `/api/products`. Đây **không** phải danh sách origin.
- `setAllowedOrigins` quy định **origin của frontend**, không phải host của API.
- `http.cors(cors -> cors.configurationSource(source))` bật tích hợp CORS cho chain này, trước các kiểm tra xác thực gây vấn đề cho preflight.
- `authorizeExchange` là phần kiểm soát quyền truy cập server-side. Origin được phép không đồng nghĩa request đã được authenticated.
- Ví dụ **chưa triển khai cơ chế đăng nhập, phát hành session cookie hay xử lý CSRF token** của ứng dụng thật. Cần bổ sung chúng theo thiết kế.

Khi API chỉ dùng bearer token và không dựa vào cookie, có thể không cần `setAllowCredentials(true)`, tùy Fetch credentials mode và cấu trúc client. Không bật chỉ vì muốn header `Authorization` đi qua preflight; việc cho phép `Authorization` là trách nhiệm của `allowedHeaders` và auth server.

### 4.1. Giới hạn origin rõ ràng

Đối với Fetch:

~~~javascript
fetch("https://api.example.com/api/me", {
  credentials: "include"
});
~~~

API cần trả origin **cụ thể**, phù hợp origin frontend:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
~~~

Không dùng:

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

với request ở credentials mode `include`: browser không cho JavaScript đọc response. Spring cũng không cho kết hợp `allowedOrigins("*")` với `allowCredentials(true)` theo cấu hình thông thường.

Spring có `allowedOriginPatterns` cho hostname pattern và trả origin cụ thể đã khớp. Tuy nhiên một pattern quá rộng cùng credentials có thể cấp quyền đọc dữ liệu session cho trang lạ ở subdomain bị chiếm hoặc do user kiểm soát. Với API có dữ liệu cá nhân, ưu tiên allowlist hữu hạn.

### 4.2. Nhiều nhóm URL trong một source

Một API có phần admin và phần frontend thường có thể đăng ký hai chính sách:

~~~java
CorsConfiguration app = new CorsConfiguration();
app.setAllowedOrigins(List.of("https://app.example.com"));
app.setAllowedMethods(List.of("GET", "POST"));

CorsConfiguration admin = new CorsConfiguration();
admin.setAllowedOrigins(List.of("https://admin.example.com"));
admin.setAllowedMethods(List.of("GET"));

UrlBasedCorsConfigurationSource source =
    new UrlBasedCorsConfigurationSource();
source.registerCorsConfiguration("/api/**", app);
source.registerCorsConfiguration("/admin/**", admin);
~~~

Phải kiểm tra security chain nào xử lý `/admin/**` và có áp dụng source này. Khi sử dụng nhiều `SecurityWebFilterChain`, một cấu hình `cors(...)` chỉ nằm trên chain A không đảm bảo chain B cũng xử lý preflight đúng.

## 5. Phương án B: đăng ký CorsWebFilter độc lập

Nếu muốn xử lý CORS ở cấp `WebFilter` trước các filter bảo mật, có thể khai báo một `CorsWebFilter` với nguồn cấu hình reactive. Cách này thường hữu ích khi yêu cầu xử lý CORS là concern chung của WebFlux, thay vì muốn định nghĩa ngay trong từng security chain.

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsWebFilter;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
class EarlyCorsWebFilterConfiguration {

    @Bean
    @Order(Ordered.HIGHEST_PRECEDENCE)
    CorsWebFilter corsWebFilter() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(List.of("GET", "POST", "PUT"));
        cors.setAllowedHeaders(List.of(
            "Authorization", "Content-Type", "X-CSRF-TOKEN"
        ));
        cors.setExposedHeaders(List.of("X-Request-Id"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return new CorsWebFilter(source);
    }
}
~~~

**Đây là phương án thay thế cho `ServerHttpSecurity.cors(...)`**, không phải bước bắt buộc cần thêm vào ví dụ ở mục 4.

Khi chọn filter độc lập:

1. Đảm bảo filter thực sự được chạy trước security filter chain trong runtime. `@Order(Ordered.HIGHEST_PRECEDENCE)` thể hiện ý định ưu tiên; cần xác minh filter ordering ở hệ thống thực.
2. Cấu hình nguồn CORS nhất quán giữa filter, handler và gateway; tránh hai thành phần cùng tạo `Access-Control-Allow-Origin` mâu thuẫn.
3. Với preflight, filter trả lời trước các lớp đòi authentication; actual request vẫn đi qua Spring Security nếu đáp ứng điều kiện CORS.
4. Nếu security chain cũng cấu hình CORS riêng, cần kiểm tra và loại bỏ đường xử lý trùng không mong muốn.
5. Không coi một filter chung là thay thế authentication, authorization hoặc CSRF trong security chain.

### 5.1. CorsWebFilter không phải CorsFilter

| Đặc điểm | Servlet | WebFlux |
| --- | --- | --- |
| Lớp filter | `org.springframework.web.filter.CorsFilter` | `org.springframework.web.cors.reactive.CorsWebFilter` |
| Kiểu nguồn | Servlet `CorsConfigurationSource` | Reactive `CorsConfigurationSource` |
| Kiểu ngữ cảnh | `HttpServletRequest` | `ServerWebExchange` |
| Bảo mật | `HttpSecurity` / `SecurityFilterChain` | `ServerHttpSecurity` / `SecurityWebFilterChain` |
| Đường xử lý | Servlet filter chain | Reactive WebFilter chain |
| Mẫu kiểm thử | `MockMvc` | `WebTestClient` |

Không nhập class Servlet vào ứng dụng WebFlux chỉ vì chúng có tên gần giống. `CorsConfiguration` là lớp dữ liệu dùng chung; còn source và filter khác package và cơ chế hoạt động.

### 5.2. Filter có hoàn toàn “không chặn luồng” không?

`CorsWebFilter` tuân theo hợp đồng `WebFilter` và trả `Mono<Void>` qua pipeline Reactive. Việc kiểm tra policy của nó không đòi handler business phải chạy với preflight. Điều này không có nghĩa bất kỳ `CorsConfigurationSource` tùy biến nào cũng an toàn: nếu tự triển khai source để tra database hoặc gọi HTTP từ luồng xử lý, cần giữ đúng mô hình non-blocking của WebFlux, tránh lệnh blocking trên event-loop.

Nguồn URL có cấu hình tĩnh như ví dụ thường đơn giản và phù hợp để bắt đầu.

## 6. Cấu hình CORS ở WebFlux Handler và @CrossOrigin

WebFlux cũng có cơ chế CORS tại cấp handler/controller, tương tự Spring MVC nhưng sử dụng thành phần WebFlux.

### 6.1. WebFluxConfigurer

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.CorsRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
class WebFluxCorsConfiguration implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
            .allowedOrigins("https://app.example.com")
            .allowedMethods("GET", "POST", "PUT")
            .allowedHeaders("Authorization", "Content-Type", "X-CSRF-TOKEN")
            .exposedHeaders("X-Request-Id")
            .allowCredentials(true)
            .maxAge(600);
    }
}
~~~

Cấu hình này thuộc **WebFlux handler mappings**. Nó mô tả chính sách khi request tới handler phù hợp; không nên giả định mọi preflight đều đến handler nếu một security WebFilter đứng trước đã chặn nó.

Nếu đã dùng `CorsWebFilter` độc lập hoặc `ServerHttpSecurity.cors(...)` với nguồn riêng, cần xác định chính sách nào đang áp dụng ở lớp nào. Đừng khai báo các allowlist khác nhau rồi chờ framework tự chọn “chính sách chặt nhất”.

### 6.2. @CrossOrigin ở controller Reactive

~~~java
import reactor.core.publisher.Mono;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/public")
@CrossOrigin(origins = "https://app.example.com")
class PublicCatalogController {

    @GetMapping("/ping")
    Mono<String> ping() {
        return Mono.just("pong");
    }
}
~~~

`@CrossOrigin` định nghĩa CORS cục bộ theo handler. Nếu kết hợp với cấu hình CORS toàn cục, một số thuộc tính dạng danh sách có thể được hợp nhất, qua đó **mở rộng** tập origin được phép. Hãy kiểm thử origin thật sự có quyền thay vì nghĩ annotation method luôn thu hẹp cấu hình global.

**Chọn nơi chịu trách nhiệm chính:** với ứng dụng Spring Security Reactive, cách minh bạch thường là cấu hình CORS sớm trong `ServerHttpSecurity` hoặc `CorsWebFilter`; các chính sách handler riêng chỉ nên dùng khi hiểu rõ tương tác và thứ tự thực thi.

## 7. Cookie, credentials, session và CSRF trong WebFlux

CORS không tự quyết định cookie được gửi hay không. Có ba bước kiểm tra riêng:

1. **Fetch credentials mode:** mặc định `fetch()` dùng `"same-origin"`; gọi khác origin thường cần `credentials: "include"` nếu muốn browser xét gửi session cookie.
2. **Cookie policy:** cookie phải khớp host/domain, path, `Secure`, `SameSite` và không bị chính sách browser chặn.
3. **CORS response:** khi request dùng credentials mode `include`, browser yêu cầu origin cụ thể và `Access-Control-Allow-Credentials: true` để JavaScript được đọc response.

Ví dụ `https://app.example.com` và `https://api.example.com` khác origin nhưng thường cùng site. Cookie `SameSite=Lax` có thể vẫn được gửi trong ngữ cảnh same-site nếu `credentials: "include"` và các điều kiện khác đạt. Không tự động đổi sang `SameSite=None` chỉ vì hai subdomain khác origin.

Ngược lại, API ở site khác (ví dụ `https://api.partner.example.org`) có thể cần cookie `SameSite=None; Secure` cho cross-site và còn chịu hạn chế third-party cookies. **CORS thành công không ép browser gửi cookie đã bị từ chối.**

### 7.1. CSRF protection vẫn cần

Ví dụ `PUT` dùng session cookie phải có CSRF token đúng cơ chế mà ứng dụng WebFlux đã cấu hình. Đừng tắt CSRF chỉ vì gặp lỗi preflight 403.

Hai lỗi khác nhau:

- `OPTIONS` bị Security chặn vì thiếu cookie → vấn đề **vị trí xử lý CORS**.
- `OPTIONS` thành công nhưng actual `PUT` bị từ chối vì CSRF token sai/thiếu → vấn đề **CSRF trên actual request**.

`CorsWebFilter` không tạo CSRF token. Trong WebFlux, Spring Security có các cơ chế CSRF Reactive, và SPA có thể cần quy trình nhận token rồi gửi lại trong header thích hợp. Tên header trên CORS allowlist phải khớp với header thật của ứng dụng, ví dụ `X-CSRF-TOKEN`; chi tiết nhận và lưu token là chủ đề bảo vệ CSRF riêng.

### 7.2. Authorization không phụ thuộc vào Origin

CORS cho phép browser đọc response tại frontend tin cậy nhưng không thay thế phân quyền của API. Một người không có quyền cập nhật hồ sơ người khác vẫn phải nhận `403`, dù `Origin` hợp lệ.

Ngoài trình duyệt, client `curl` có thể tự đặt `Origin`. Không dùng header `Origin` như một phương thức xác thực hoặc phân quyền cho user/tenant.

## 8. Định nghĩa chính sách an toàn cho từng môi trường

Một nguồn CORS chỉ nên cấp quyền cho những origin thật sự được tin cậy chạy JavaScript đọc API. Ví dụ:

| Môi trường | Origin dự kiến | Cách xử lý |
| --- | --- | --- |
| Production frontend | `https://app.example.com` | Có trong production allowlist |
| Production admin | `https://admin.example.com` | Có trong policy admin nếu cần |
| Staging | `https://staging-app.example.com` | Chỉ cấu hình cho API staging |
| Local Vite | `http://localhost:5173` | Chỉ cấu hình dev, đúng port |
| Origin không quen | `https://evil.example.org` | Không cấp CORS |
| Opaque origin | `null` | Mặc định không cấp quyền |

Không phản chiếu mọi giá trị `Origin` nhận được:

~~~java
// KHÔNG AN TOÀN với API trả dữ liệu người dùng:
String origin = exchange.getRequest()
    .getHeaders().getOrigin();
// Không tự động cấp quyền cho mọi origin này trong cấu hình CORS.
~~~

Nếu API dùng session cookie, mở `allowedOriginPatterns("*")` cùng `allowCredentials(true)` là mở rộng phạm vi tin cậy nguy hiểm dù Spring có thể tạo response header đúng cú pháp. Với dữ liệu cá nhân, nên dùng danh sách origin cụ thể và rà soát khi có frontend mới.

Một pattern subdomain rộng không tự kiểm tra hostname nào do user quản lý, bị XSS hoặc có nguy cơ subdomain takeover.

## 9. Kiểm thử CORS WebFlux với WebTestClient

`WebTestClient` là công cụ phù hợp để gửi HTTP request tới ứng dụng WebFlux và kiểm tra status/header của pipeline Reactive. Đối với CORS, cần kiểm tra cả **preflight được phép**, **origin không được phép**, **method/header bị từ chối** và **actual response**.

### 9.1. Ma trận kiểm thử

Với chính sách ở mục 4, đăng ký cho `/api/**`:

| Request | Điều kiện | Kỳ vọng |
| --- | --- | --- |
| `OPTIONS /api/profile` | `Origin: https://app.example.com`, method `PUT`, header `content-type,x-csrf-token` | Được trả CORS preflight hợp lệ |
| `OPTIONS /api/profile` | `Origin: https://evil.example.org` | Bị từ chối |
| `OPTIONS /api/profile` | Origin đúng nhưng method `DELETE` | Bị từ chối |
| `OPTIONS /api/profile` | Origin/method đúng nhưng header `x-admin-override` | Bị từ chối |
| `OPTIONS /admin/reports` | Chỉ đăng ký source `/api/**` | Không có policy CORS tương ứng |
| `GET /api/public/ping` | Origin đúng, endpoint public tồn tại | Actual response có header CORS phù hợp |
| `GET /api/me` | Origin đúng nhưng chưa authenticated | Endpoint có thể trả 401; CORS hợp lệ cho phép frontend đọc status |

Một request có origin bị từ chối không có nghĩa API được bảo vệ trước mọi client ngoài browser; auth và authorization phải được test độc lập.

### 9.2. Mẫu test tích hợp

Ví dụ dưới đây giả định ứng dụng Spring Boot WebFlux đã cấu hình Spring Security và source CORS như ở mục 4, có dependencies test phù hợp:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.http.HttpHeaders.*;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveCorsIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void preflightAllowsTrustedOriginWithoutCookie() {
        client.options()
            .uri("/api/profile")
            .header(ORIGIN, "https://app.example.com")
            .header(ACCESS_CONTROL_REQUEST_METHOD, "PUT")
            .header(ACCESS_CONTROL_REQUEST_HEADERS, "content-type,x-csrf-token")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                ACCESS_CONTROL_ALLOW_ORIGIN, "https://app.example.com")
            .expectHeader().valueEquals(
                ACCESS_CONTROL_ALLOW_CREDENTIALS, "true");
    }

    @Test
    void preflightRejectsUnknownOrigin() {
        client.options()
            .uri("/api/profile")
            .header(ORIGIN, "https://evil.example.org")
            .header(ACCESS_CONTROL_REQUEST_METHOD, "PUT")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void preflightRejectsUnlistedMethod() {
        client.options()
            .uri("/api/profile")
            .header(ORIGIN, "https://app.example.com")
            .header(ACCESS_CONTROL_REQUEST_METHOD, "DELETE")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

Đây là **mã minh họa chưa chạy trên dự án cụ thể**. Với `CorsWebFilter`/processor mặc định, origin hoặc method không hợp lệ thường gây 403. Nếu gateway/custom filter thay đổi response, cần điều chỉnh assertion, nhưng tuyệt đối không xem request bị từ chối là CORS thành công.

Bài test chỉ xác nhận preflight, **không chứng minh** cookie thực được browser gửi hoặc CSRF đã bảo vệ actual request. Cần thêm test authenticated/unauthenticated và thử trực tiếp trên browser đối với session/cookie.

### 9.3. Test actual response và exposed headers

Nếu API có handler `GET /api/public/ping` như mục 6, một test có thể kiểm tra CORS trên actual response:

~~~java
@Test
void actualGetContainsCorsOrigin() {
    client.get()
        .uri("/api/public/ping")
        .header(ORIGIN, "https://app.example.com")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().valueEquals(
            ACCESS_CONTROL_ALLOW_ORIGIN, "https://app.example.com");
}
~~~

Để test `Access-Control-Expose-Headers: X-Request-Id`, response thực tế cần có cả **header được expose** và **header `X-Request-Id` thật**. Việc khai báo `exposedHeaders` trong CORS policy không tự tạo request ID.

Không dùng `WebTestClient` như một trình duyệt đầy đủ: nó kiểm tra status/header HTTP nhưng không tự thực thi toàn bộ SOP, cookie policy hoặc third-party tracking prevention của browser.

## 10. Kiểm tra bằng DevTools và curl

### 10.1. Thử preflight HTTP

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/profile" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: PUT" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
~~~

Thử một origin ngoài allowlist:

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/profile" \
  -H "Origin: https://evil.example.org" \
  -H "Access-Control-Request-Method: PUT"
~~~

Thử actual GET:

~~~bash
curl -i "https://api.example.com/api/public/ping" \
  -H "Origin: https://app.example.com"
~~~

`curl` có thể nhận body/headers từ server dù browser không cho JavaScript đọc do CORS; đây là công cụ để **kiểm tra response HTTP**, không phải phép chứng minh SOP/CORS hoàn chỉnh. Các domain `example.com`/`example.org` chỉ là ví dụ.

### 10.2. Quan sát trình duyệt

Trong frontend đang chạy ở origin thật:

1. Mở DevTools → **Network**, tìm `OPTIONS` và actual request tương ứng.
2. Trên OPTIONS, kiểm tra `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers`.
3. Kiểm tra preflight response: `Access-Control-Allow-Origin`, `Allow-Methods`, `Allow-Headers` và `Allow-Credentials` khi dùng credentials.
4. Xác định actual request **có xuất hiện không**. Nếu không, xử lý preflight trước.
5. Nếu actual request đã được gửi, đối chiếu HTTP 401/403/500 và CORS headers của chính response đó.
6. Nếu cookie vắng mặt, kiểm tra `credentials` mode, `SameSite`, `Secure`, Domain/Path và mục cookie bị chặn.
7. Nếu lỗi chỉ xảy ra qua gateway, kiểm tra path rewrite, filter order và những header CORS bị xóa/nhân đôi.

Không dùng `mode: "no-cors"` để sửa lỗi đọc JSON: chế độ đó làm response opaque và JavaScript không truy cập được dữ liệu như mong đợi.

## 11. Những lỗi tích hợp thường gặp

| Triệu chứng | Nguyên nhân cần nghĩ đến | Hướng xử lý |
| --- | --- | --- |
| OPTIONS nhận 401 trước khi đến handler | CORS chạy sau security hoặc security chain không tích hợp CORS | Đưa CORS đủ sớm vào `ServerHttpSecurity` hoặc `CorsWebFilter` có thứ tự đúng |
| OPTIONS trả 403 | Origin/method/request headers không được phép, hoặc source không khớp path | So request preflight với `CorsConfiguration` và URL mapping |
| `CorsWebFilter` đã khai báo nhưng browser vẫn lỗi | Filter ordering sai hoặc response cuối có policy khác | Kiểm tra thứ tự `WebFilter` và response qua gateway |
| Response chứa hai `Access-Control-Allow-Origin` | Filter riêng, security integration hoặc handler/gateway cùng gắn header | Chọn một cách xử lý CORS nhất quán |
| Chỉ WebFlux lỗi, Servlet chạy | Import nhầm `CorsFilter`/`CorsConfigurationSource` Servlet | Dùng các lớp package `org.springframework.web.cors.reactive` |
| Preflight tốt nhưng actual PUT trả 403 | CSRF token không đúng, thiếu quyền hoặc session lỗi | Kiểm tra actual request, CSRF repository và authorization |
| Frontend chỉ thấy CORS error dù API log 401 | Error response thiếu CORS headers phù hợp | Xác minh actual response được CORS layer xử lý |
| `GET` hoạt động, `POST application/json` thất bại | Preflight thiếu Allow-Headers/Allow-Methods | Kiểm tra OPTIONS và header `Content-Type` |
| CORS cho session bị wildcard error | `Allow-Origin: *` với `credentials: "include"` | Dùng origin cụ thể và `Allow-Credentials: true` khi cần |
| Cookie không được gửi | Fetch mặc định `same-origin` hoặc cookie policy không cho gửi | Kiểm tra Fetch mode, Domain/Path, SameSite, Secure |
| Route admin thất bại | Source đăng ký `/api/**` nhưng chưa có `/admin/**` hoặc chain admin khác | Xem cả path source và security chain được chọn |
| Chỉ deploy gateway/CDN lỗi | Gateway chặn OPTIONS, rewrite path hoặc sửa header | So response trực tiếp và qua gateway |
| Lỗi không ổn định | Cache `Vary: Origin`, preflight cache, nhiều backend policy khác nhau | Kiểm tra cache và cấu hình trên mọi instance |
| Một số request không có OPTIONS | Request thuộc safelist hoặc đã cache preflight | Không kết luận filter không chạy chỉ từ một request |

### 11.1. Checklist xử lý theo từng lớp

Để không nhầm lỗi trình duyệt với lỗi server:

- **Trình duyệt:** Có preflight không? `Origin` thật là gì? Cookie có được gửi không?
- **WebFlux CORS:** `CorsConfigurationSource` trả policy cho path nào? Origin/method/headers có hợp lệ?
- **Thứ tự WebFilter:** CORS đã chạy trước authentication trong luồng cần preflight chưa? Có xử lý trùng?
- **Spring Security:** Actual request có authentication, authorization và CSRF hợp lệ không?
- **Handler:** Request có được định tuyến tới đúng WebFlux handler? Response/exception có thêm header cần thiết?
- **Gateway/proxy:** Có rewrite path, xóa header, trả OPTIONS riêng, tạo header lặp hoặc cache sai biến thể không?

## 12. Ranh giới với các lớp bảo vệ HTTP khác

CORS là một trong nhiều cơ chế của `SPRING_SECURITY_HTTP_PROTECTION`:

| Cơ chế | Quyết định |
| --- | --- |
| `CorsWebFilter` / CORS integration | Browser có được gửi actual request qua preflight và đọc response khác origin không? |
| Authentication | User/client là ai? Session/token hợp lệ không? |
| Authorization | User/client được làm gì với tài nguyên và tenant này? |
| CSRF | Request thay đổi trạng thái trong ngữ cảnh xác thực dễ bị CSRF có hợp lệ không? |
| Cookie/session security | Cookie được gửi tới đâu, session tồn tại bao lâu, có chống chiếm phiên không? |
| CSP `connect-src` | Frontend được phép tạo kết nối tới đích nào? |
| HSTS và TLS | Bảo vệ truy cập HTTPS và giảm khả năng downgrade |
| HTTP firewall / validation | Giảm rủi ro từ các request HTTP bất thường theo cơ chế áp dụng |

Một API dùng cookie phiên không nên tắt CSRF chỉ để làm `POST` chạy qua CORS. Một `POST` dạng form có thể đến server mà không cần preflight, và browser chặn đọc response **không đảo ngược thao tác đã xảy ra**. CORS không phải xác thực hoặc kiểm soát mọi client HTTP.

## 13. Bài tập vận dụng

**Tình huống 1.** Ứng dụng WebFlux đăng ký `org.springframework.web.filter.CorsFilter` như một Servlet Filter. Có đúng stack không?

**Đáp án:** Không. WebFlux cần `org.springframework.web.cors.reactive.CorsWebFilter` hoặc tích hợp reactive tương đương qua `ServerHttpSecurity.cors(...)`.

**Tình huống 2.** Preflight `OPTIONS` của `PUT` không có cookie, Spring Security trả 401. Có nên sửa JavaScript để tự đặt `Cookie` trong OPTIONS không?

**Đáp án:** Không. Browser tự tạo preflight và không gửi credentials của actual request theo luồng thông thường. Cần xử lý CORS trước authentication, sau đó xác thực actual `PUT`.

**Tình huống 3.** Một `CorsWebFilter` được đặt trước security chain, nhưng API trả 403 cho actual `PUT` vì CSRF token sai. Có phải `CorsWebFilter` bị hỏng không?

**Đáp án:** Không. Preflight/CORS có thể thành công nhưng Spring Security vẫn từ chối actual request theo CSRF hoặc authorization. Xem response và log thực tế.

**Tình huống 4.** Có thể thêm một `CorsWebFilter` bean khác khi `ServerHttpSecurity.cors(...)` đã cấu hình đầy đủ, để “chắc chắn hơn” không?

**Đáp án:** Không nên. Hai nơi cùng xử lý CORS có thể tạo trùng header, khác thứ tự và chính sách. Hãy chọn một cách tích hợp rõ ràng rồi test response cuối.

**Tình huống 5.** Frontend dùng `credentials: "include"` nhưng backend trả `Access-Control-Allow-Origin: *`. Browser có đọc được response không?

**Đáp án:** Không. Response cần origin cụ thể phù hợp và `Access-Control-Allow-Credentials: true` khi request dùng credentials mode `include`.

**Tình huống 6.** Cấu hình source chỉ đăng ký `/api/**`, nhưng preflight gửi tới `/admin/users`. Tại sao có thể bị từ chối dù origin đúng?

**Đáp án:** Vì nguồn cấu hình không có policy phù hợp với path `/admin/users`. Cần policy cho admin route nếu frontend thực sự được tin cậy truy cập, đồng thời đảm bảo security chain phù hợp.

**Tình huống 7.** `WebFluxConfigurer` khai báo origin A, `CorsWebFilter` khai báo origin B. Browser nhận lỗi không ổn định. Nên sửa ở đâu?

**Đáp án:** Xác định WebFilter/handler/gateway nào đang áp dụng chính sách, thống nhất allowlist và tránh xử lý trùng. Kiểm tra preflight và actual response thay vì thêm header ở nhiều lớp.

**Tình huống 8.** Curl gửi `Origin: https://app.example.com` và nhận JSON. Điều đó chứng minh JavaScript ở một trang bất kỳ cũng được đọc JSON không?

**Đáp án:** Không. Curl không thực thi SOP/CORS và có thể tự đặt Origin. Cần test trong browser, đồng thời authentication/authorization phải bảo vệ API độc lập.

---

**Ghi nhớ:** Trong WebFlux, `CorsWebFilter` là WebFilter Reactive xử lý CORS từ `CorsConfigurationSource`; Spring Security Reactive cũng có thể tích hợp CORS trực tiếp qua `ServerHttpSecurity.cors(...)`. **Chọn một con đường xử lý rõ ràng, cho preflight đi qua trước các kiểm tra xác thực, và tiếp tục bảo vệ actual request bằng authentication, authorization, CSRF, cookie/session.** Đối chiếu request/response và thứ tự filter khi debug; đừng dùng CORS làm thay tường lửa hoặc cơ chế phân quyền của API.
