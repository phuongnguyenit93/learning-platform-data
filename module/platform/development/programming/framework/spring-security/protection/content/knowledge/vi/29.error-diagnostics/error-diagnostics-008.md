# CORS header trùng hoặc origin cấu hình không khớp

> **Chương:** Chẩn đoán lỗi  
> **Mô-đun:** `SPRING_SECURITY_HTTP_PROTECTION` — áp dụng các lớp phòng vệ HTTP và trình duyệt trong Spring Security, từ CSRF, CORS, security headers, CSP, HSTS đến HTTP firewall và bảo vệ session. Người học cấu hình cho Servlet lẫn Reactive, kiểm thử các kịch bản tấn công web và chẩn đoán xung đột bảo mật khi triển khai.

## 1. Bài toán: HTTP 200 nhưng JavaScript vẫn báo lỗi CORS

Giả sử frontend chạy tại `https://app.example.com`, gọi API Spring Boot tại `https://api.example.com`. Network hiển thị:

~~~http
GET /api/profile HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
~~~

Server thật sự xử lý thành công và trả:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Origin: *
Content-Type: application/json

{"displayName":"Alice"}
~~~

Nhưng browser không cho JavaScript đọc response. Nhiều công cụ gộp hai dòng header thành dạng:

~~~http
Access-Control-Allow-Origin: https://app.example.com, *
~~~

Đây **không phải** cách hợp lệ để cho phép hai origin. `Access-Control-Allow-Origin` (*ACAO*) phải biểu diễn **một** origin được phép hoặc giá trị `*` trong trường hợp thích hợp, không phải danh sách nhiều origin. Khi một Spring `CorsFilter` và một gateway cùng thêm ACAO, chúng có thể tạo phản hồi có **nhiều giá trị** dù mỗi tầng riêng lẻ tưởng đang cấu hình đúng.

Một tình huống khác:

~~~http
GET /api/profile
Origin: https://staging.app.example.com

HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
~~~

Lần này ACAO không trùng, nhưng **không khớp Origin của trang đang gọi**. Browser cũng từ chối cho JavaScript đọc response. Việc backend trả 200 không thay đổi kết quả CORS ở browser.

### Kết quả học tập

Sau bài này, người học có thể:

1. Đọc chính xác `Origin` và các `Access-Control-Allow-*` headers trong **preflight** và **actual response**.
2. Phân biệt ACAO bị lặp, ACAO chứa danh sách, Origin không khớp, wildcard đi cùng credentials và thiếu CORS headers.
3. Xác định tầng nào phát header trùng: CDN/WAF, reverse proxy, API gateway, Spring MVC/WebFlux, `CorsFilter`/`CorsWebFilter` hoặc custom filter.
4. Thiết kế **một chủ sở hữu chính sách CORS rõ ràng**, giữ authentication, CSRF và session protections.
5. Cấu hình, kiểm thử và chẩn đoán trên **Servlet** lẫn **Reactive/WebFlux**, từ HTTP client tới browser.

## 2. Tư duy chính xác: CORS là kiểm tra trên response, không chỉ status

Browser thực hiện một phép kiểm tra riêng sau khi nhận response cross-origin. Server có thể đã xử lý request trước khi trình duyệt kết luận JavaScript có được đọc response hay không.

~~~mermaid
flowchart TD
    A[Trang tại Origin A gọi API tại Origin B] --> B{Request cần preflight?}
    B -- Có --> C[OPTIONS với Origin và Access-Control-Request-*]
    C --> D{Preflight được chấp thuận?}
    D -- Không --> E[Browser không gửi actual request]
    D -- Có --> F[Browser gửi actual request]
    B -- Không --> F
    F --> G[API xử lý và trả HTTP response]
    G --> H{Actual response thỏa CORS?}
    H -- Không --> I[JavaScript không được đọc response]
    H -- Có --> J[JavaScript nhận status/body theo Fetch API]
~~~

**Hai kết luận cần ghi nhớ:**

- OPTIONS thành công chỉ là bước xin phép; **actual response cũng cần CORS headers phù hợp**.
- Một actual request có thể **đã thay đổi dữ liệu ở server** rồi browser mới chặn quyền đọc response. Không tự động retry POST chỉ vì `fetch` ném `TypeError` hoặc console báo CORS: có nguy cơ thực hiện thao tác hai lần.

Lỗi CORS không được giải quyết bằng cách chuyển mọi POST sang GET, tắt CSRF hoặc bỏ xác thực. CORS, authentication, CSRF và authorization điều khiển những mục tiêu bảo mật khác nhau.

## 3. Origin chính xác gồm scheme, host và port

Browser đưa Origin lên request theo **scheme + hostname + port**. Khi so policy, không chỉ so hostname hay subdomain.

| Frontend URL | Origin được browser gửi (minh họa) | Có bằng `https://app.example.com` không? |
|---|---|---|
| `https://app.example.com/dashboard` | `https://app.example.com` | Có |
| `http://app.example.com/dashboard` | `http://app.example.com` | Không, scheme khác |
| `https://app.example.com:8443/dashboard` | `https://app.example.com:8443` | Không, port khác |
| `https://staging.app.example.com` | `https://staging.app.example.com` | Không, host khác |
| `https://api.example.com` | `https://api.example.com` | Không, host khác |
| `https://app.example.com:443/dashboard` | Thông thường `https://app.example.com` | Port HTTPS mặc định được chuẩn hóa |

Một origin **không có dấu gạch chéo kết thúc**:

~~~text
Đúng kiểu origin:
https://app.example.com

Không phải origin:
https://app.example.com/
https://app.example.com/dashboard
https://app.example.com?mode=dev
~~~

Policy Spring `setAllowedOrigins(...)` nên khai báo origin chính xác, không dùng URL có path/trailing slash như một entry mong có tác dụng tương đương.

### Same-origin khác same-site

`https://app.example.com` và `https://api.example.com` là **khác origin**, dù thường cùng site theo quy tắc cookie khi dùng cùng scheme và registrable domain. Cookie `SameSite=Lax` có thể không chặn request cùng site, nhưng **CORS vẫn được kiểm tra** vì khác origin.

`SameSite` giải quyết việc gửi cookie theo ngữ cảnh site; CORS giải quyết quyền truy cập response từ JavaScript theo origin. Không dùng một policy làm vật thay thế cho policy còn lại.

## 4. Quy tắc của Access-Control-Allow-Origin: một giá trị có ý nghĩa rõ

Các dạng chính:

| ACAO response | Ý nghĩa/đánh giá |
|---|---|
| `Access-Control-Allow-Origin: https://app.example.com` | Cho phép đúng origin đó nếu khớp request |
| `Access-Control-Allow-Origin: *` | Cho phép đọc trong một số request không dùng credentials; không hợp lệ cho credentialed CORS |
| Không có ACAO | Browser không cho JS đọc cross-origin response nếu cần CORS |
| `Access-Control-Allow-Origin: https://app.example.com, https://admin.example.com` | **Sai:** không phải danh sách hợp lệ |
| Hai dòng ACAO giống hoặc khác nhau | **Sai:** nhiều giá trị ACAO không trở thành hợp lệ vì giống nhau |
| `Access-Control-Allow-Origin: null` | Giá trị đặc biệt cho serialized origin `null`, nguy hiểm khi cho phép bừa bãi |

Không nên dùng phép so sánh chuỗi theo kiểu `origin.endsWith("example.com")` để cho phép các domain. Nó có thể vô tình tin `attackerexample.com` hoặc một hostname ngoài trust boundary. Với Origin được phép có tên cụ thể, dùng exact allowlist và so khớp theo framework.

### Lặp ACAO khác với header dạng danh sách

Các headers như `Access-Control-Allow-Methods` và `Access-Control-Allow-Headers` **có thể chứa danh sách**:

~~~http
Access-Control-Allow-Methods: GET,POST,PUT
Access-Control-Allow-Headers: content-type,x-csrf-token
~~~

Nhưng không nên áp dụng quy tắc danh sách đó cho ACAO. Nếu nhìn thấy:

~~~http
Access-Control-Allow-Origin: https://app.example.com, *
~~~

đừng thử tách bằng dấu phẩy ở frontend rồi tự chọn một giá trị. Browser là bên thực thi Fetch/CORS; sửa **nguồn response headers**, không phải chỉnh logic parse bằng JavaScript.

## 5. Credentials khiến wildcard không còn là lời giải

Giả sử SPA dùng cookie session:

~~~javascript
await fetch("https://api.example.com/api/profile", {
  credentials: "include"
});
~~~

Response:

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

không phải credentialed CORS response hợp lệ. Với requests có credentials, server cần cho phép **origin cụ thể** và khi cần cho frontend đọc response thì `Access-Control-Allow-Credentials: true`.

Ví dụ phù hợp hơn:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

**Không đọc “credentials” là chỉ session cookie.** Đối với Fetch/CORS, credentials mode còn liên quan tới HTTP authentication và client credentials theo ngữ nghĩa browser. Việc frontend chủ động đặt header `Authorization` còn có thể kích hoạt preflight; policy CORS và authentication vẫn cần được đánh giá theo request thực.

### Wildcard trong những headers khác

Khi có credentials, một số wildcard CORS headers (ví dụ cách xử lý `Access-Control-Allow-Headers` hay `Access-Control-Allow-Methods`) cũng có quy tắc riêng theo Fetch và browser support. **Ưu tiên khai báo chính xác method/header** thay vì dùng `*` như cách nới toàn bộ policy. Không suy từ ACAO wildcard rằng tất cả headers cũng dùng chung luật.

## 6. Vì sao response có hai ACAO?

Trong hệ thống Spring Boot triển khai thật, có thể có nhiều tầng cùng xử lý CORS:

~~~mermaid
flowchart LR
    B[Browser] --> E[CDN / edge proxy]
    E --> G[Gateway / ingress]
    G --> S[Spring Security CORS]
    S --> M[Spring MVC hoặc WebFlux]
    M --> C[Controller/custom filter]
    C --> G
    G --> E
    E --> B
~~~

Mỗi tầng có thể:

- **Ghi đè** header đã có.
- **Thêm một giá trị** vào header hiện có.
- **Phát lại** header được backend trả, rồi tự thêm header khác.
- Chỉ xử lý preflight nhưng không xử lý actual response, hoặc ngược lại.

Ví dụ Spring trả:

~~~http
Access-Control-Allow-Origin: https://app.example.com
~~~

Sau gateway:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Origin: *
~~~

Đây là một dấu hiệu **trùng chủ sở hữu CORS**, không phải Spring Security cần được cho `permitAll()` trên endpoint.

### Một số nguồn trùng thường gặp

1. `http.cors(...)` cùng với một servlet `CorsFilter` đăng ký riêng có hành vi phát header không được điều phối.
2. Spring Security CORS cùng Spring MVC `@CrossOrigin` hoặc `WebMvcConfigurer#addCorsMappings`, cộng thêm custom filter viết ACAO thủ công.
3. Spring Cloud Gateway hoặc ingress nginx/Traefik/Envoy tự thêm ACAO trong khi Spring Boot cũng trả header.
4. CDN rule hoặc reverse proxy `add_header` áp trên mọi response, kể cả response có ACAO từ origin.
5. Global error handler thêm ACAO lần nữa cho response 401/403/500.
6. Một service proxy sang service khác, giữ nguyên ACAO upstream rồi thêm ACAO của chính nó.

**Không kết luận mọi sự kết hợp `@CrossOrigin` + `http.cors(...)` đều tạo header trùng.** Trong cấu hình Spring MVC tích hợp chuẩn, Spring Security có thể dùng chính CORS metadata của MVC, nên chỉ có một response ACAO hợp lệ. Lỗi xuất hiện khi các tầng/filter **độc lập** cùng ghi header mà không có hợp đồng.

## 7. Phân biệt lặp header và không khớp Origin bằng chứng HTTP

| Triệu chứng Network/Console | Giả thuyết mạnh | Cần xác minh |
|---|---|---|
| ACAO có hai dòng | Nhiều tầng cùng ghi header | So origin Spring vs public gateway |
| ACAO có chuỗi `origin, *` | Các giá trị bị ghép thành danh sách không hợp lệ | Raw response headers ở từng tầng |
| ACAO duy nhất nhưng khác `Origin` request | Sai allowlist hoặc nhầm frontend hostname | URL của trang thực và header Origin |
| ACAO là `*` và frontend dùng credentials `include` | Wildcard không hợp lệ với credentials | Fetch credentials + cookie/authorization context |
| Origin hợp lệ nhưng thiếu ACAO trên 401/403 | Error response không qua CORS hoặc gateway bỏ header | Nguồn response lỗi, filter order |
| OPTIONS PASS, GET/POST bị CORS | Actual response thiếu/sai ACAO hoặc ACAC | So hai response riêng |
| OPTIONS 403 `Invalid CORS request` | CORS processor đã chạy và từ chối | Allowed origins/methods/headers |
| OPTIONS 401/302 login | Authentication trước CORS hoặc chain sai | Selected security chain/filter order |
| Chỉ production lỗi | CDN/proxy/infrastructure CORS | So direct origin vs public URL |
| Chỉ một browser hoặc tab lỗi | Cache preflight, redirect, policy/extension | Fresh browser context, request ID |

Không chẩn đoán chỉ qua một dòng lỗi console. Browser có thể chọn thông báo khác nhau cho cùng một response, và một lỗi network/TLS/CSP có thể bị JavaScript tổng quát hóa thành `TypeError: Failed to fetch`.

## 8. Vary: Origin và cache không làm ACAO thành danh sách

Khi CORS processor trả ACAO khác nhau theo request Origin, HTTP cache cần biết response phụ thuộc vào Origin:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin
~~~

Với preflight, response còn có thể thay đổi theo:

~~~http
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
~~~

Hoặc một dòng `Vary` chứa nhiều tên trường. **Các giá trị `Vary` lặp hoặc được gộp hợp lệ khác hoàn toàn với ACAO lặp**.

### Cache hit sai origin

~~~text
Request 1:
  Origin: https://app.example.com
  CDN cache response:
    ACAO: https://app.example.com

Request 2:
  Origin: https://admin.example.com
  CDN trả lại cached response của Request 1
    ACAO: https://app.example.com
~~~

Kết quả request 2 nhận ACAO **không khớp**. Đây có thể không phải Spring allowlist sai: response đúng tại origin nhưng CDN cache variant sai.

**Giải pháp:** review cache key/`Vary`/bypass caching theo dữ liệu và method; không tự thêm một ACAO thứ hai ở CDN để “sửa” cached header. Với API personalized, ngoài CORS còn phải tránh cache chia sẻ dữ liệu người dùng.

## 9. Preflight và actual response: hai lớp cần kiểm tra độc lập

Request có custom header:

~~~http
OPTIONS /api/profile HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Response hợp lệ có thể là:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET,POST,PUT
Access-Control-Allow-Headers: content-type,x-csrf-token
Access-Control-Allow-Credentials: true
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Sau đó POST thật:

~~~http
POST /api/profile HTTP/1.1
Origin: https://app.example.com
Cookie: SESSION=...
Content-Type: application/json
X-CSRF-TOKEN: ...
~~~

Response POST vẫn phải có CORS headers phù hợp:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Một OPTIONS trả đúng headers trong khi POST bị gateway thêm ACAO thứ hai là **lỗi chỉ ở actual response path**. Ngược lại, preflight có ACAO trùng khiến browser **không gửi POST**, nên không có CSRF của POST để chẩn đoán.

### Với request không cần preflight

Một GET cross-origin không có custom headers có thể được browser gửi ngay và chỉ kiểm tra CORS trên response. Do đó **không thấy OPTIONS không đồng nghĩa lỗi CORS không tồn tại**.

## 10. Kiến trúc đúng: xác định một tầng sở hữu chính sách CORS

Trước khi sửa, ghi rõ **tầng nào quyết định Origin được phép và tầng nào chỉ chuyển tiếp**:

| Phương án | Chủ sở hữu | Điều phải bảo đảm |
|---|---|---|
| Spring Boot tự xử lý CORS | Spring Security CORS integration với MVC/Reactive source | Gateway/CDN không thêm ACAO độc lập |
| Gateway xử lý preflight và actual response | Gateway với allowlist đã review | Spring không phát ACAO mâu thuẫn, gateway xử lý cả success lẫn error responses |
| BFF/same-origin proxy | Frontend và API đi qua một origin công khai | Không còn CORS browser giữa frontend và BFF, nhưng auth/CSRF/headers vẫn cần |
| Phân vùng API nhiều origins | Policy per route/service với trách nhiệm rõ | Không có global catch-all filter ghi header trên mọi response |

### Không có một đáp án duy nhất cho mọi hệ thống

Ví dụ API public có thể muốn ACAO `*` đối với request **không có credentials**, trong khi API tài khoản chỉ cho một frontend cụ thể. Nếu gateway buộc một ACAO chung cho cả hai, rất dễ phát sinh xung đột.

**Khuyến nghị vận hành:** chọn một tầng sở hữu policy theo từng hostname/path, ghi nhận contract và test qua **public URL**. Các tầng không sở hữu CORS nên **không tự thêm hoặc nhân bản Access-Control-Allow-* headers**.

### Hai khả năng sau cần được phân biệt

- **Một nơi cấu hình, nhiều nơi gọi lại API CORS của cùng framework:** có thể là tích hợp hợp lệ. Ví dụ Spring Security dùng CORS metadata từ Spring MVC.
- **Hai nơi độc lập cùng ghi response header:** có thể tạo duplicate ACAO, dù mỗi nơi đều dùng cùng allowed origin.

Mục tiêu là loại bỏ việc **hai chủ thể độc lập phát header**, không xóa mọi annotation/filter mà không hiểu luồng.

## 11. Spring Security Servlet: cấu hình một CorsConfigurationSource rõ ràng

Ví dụ ứng dụng Servlet Spring Boot dùng session cookie ở frontend `https://app.example.com` và API `https://api.example.com`:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class ServletCorsSecurityConfig {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of(
            "https://app.example.com",
            "https://staging.app.example.com"
        ));
        cors.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE"));
        cors.setAllowedHeaders(List.of(
            "Content-Type", "X-CSRF-TOKEN", "X-XSRF-TOKEN"
        ));
        cors.setAllowCredentials(true);
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.cors(Customizer.withDefaults());
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .requestMatchers("/api/**").authenticated()
            .anyRequest().authenticated()
        );
        http.formLogin(Customizer.withDefaults());
        http.csrf(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Đây là code minh họa cho Spring Security Servlet với CORS source một bean. Nếu API dùng Bearer thay form login, thay phần authentication theo thiết kế; **không mặc nhiên tắt CSRF** trên tất cả API nếu còn cookie/session hoặc browser ambient credentials.

### Vì sao hai Origins trong allowedOrigins không tạo ACAO dạng danh sách?

`setAllowedOrigins(List.of(A, B))` là **danh sách phía server được phép đối chiếu**, không phải câu lệnh phát hai ACAO. Với request:

~~~http
Origin: https://staging.app.example.com
~~~

CORS processor phải chọn **một Origin khớp** và trả:

~~~http
Access-Control-Allow-Origin: https://staging.app.example.com
~~~

Nó không phải trả `https://app.example.com, https://staging.app.example.com`.

### Những yêu cầu còn cần xác minh

- Origin frontend thực sự thuộc allowlist và được viết theo dạng origin (không có path/trailing slash).
- `/api/**` là path Spring thực nhận sau reverse proxy/context path.
- Security chain chọn đúng `CorsConfigurationSource`; ứng dụng nhiều chains có thể cần source tường minh cho từng chain.
- Gateway/proxy không thêm ACAO thứ hai.
- Response lỗi do authentication/CSRF/authorization cũng có CORS headers đúng, để frontend phân biệt HTTP status mà không mở quyền ngoài dự kiến.

**Không coi mọi response 401/403 thiếu ACAO là lý do làm endpoint `permitAll()`.** Hãy xác định thứ tự CORS và cách error response đi qua filter chain.

## 12. Servlet: @CrossOrigin, WebMvcConfigurer và http.cors có nhất thiết xung đột?

Spring MVC có thể khai báo CORS tại controller:

~~~java
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import java.util.Map;

@RestController
class PublicCatalogController {

    @CrossOrigin(origins = "https://app.example.com")
    @GetMapping("/api/public/catalog")
    Map<String, String> catalog() {
        return Map.of("status", "ready");
    }
}
~~~

Hoặc khai báo toàn cục qua MVC:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class MvcCorsConfig implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
            .allowedOrigins("https://app.example.com")
            .allowedMethods("GET", "POST")
            .allowedHeaders("Content-Type", "X-CSRF-TOKEN")
            .allowCredentials(true);
    }
}
~~~

**Hai ví dụ thể hiện các lựa chọn, không phải yêu cầu copy cả hai cùng lúc.** Nếu MVC đã có CORS metadata, Spring Security có thể tích hợp thông tin đó qua `http.cors(...)`, tùy cấu hình bean/phiên bản và việc dùng Spring MVC. Đừng mặc định `@CrossOrigin` và `http.cors(...)` là “lỗi duplicate” — chính cách **nhiều tầng độc lập ghi ACAO** mới cần tìm.

### Trường hợp dễ gây duplicate

Một developer thêm custom servlet filter:

~~~java
import jakarta.servlet.*;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;

public class UnreviewedCorsHeaderFilter implements Filter {

    @Override
    public void doFilter(ServletRequest request,
                         ServletResponse response,
                         FilterChain chain)
            throws IOException, ServletException {
        HttpServletResponse http = (HttpServletResponse) response;

        // ĐÂY LÀ PHẢN VÍ DỤ: có thể tạo ACAO trùng.
        http.addHeader("Access-Control-Allow-Origin", "*");
        chain.doFilter(request, response);
    }
}
~~~

Trong Servlet API, `addHeader` có thể **thêm** giá trị bên cạnh giá trị đã có. Nếu Spring CorsFilter phát `Access-Control-Allow-Origin: https://app.example.com`, custom filter có thể khiến browser thấy ACAO lặp. **Không dùng filter này làm cấu hình production.**

Thay `addHeader` bằng `setHeader` không tự biến policy thành đúng: nó chỉ tránh một dạng lặp trong **một response do filter sở hữu**, và có thể ghi đè Origin do security processor tính đúng thành giá trị sai. Giải pháp là **gỡ bỏ header writer trùng**, phân định chủ sở hữu CORS và test policy.

## 13. Một số bean CorsConfigurationSource và nhiều SecurityFilterChain

Trong Servlet, ứng dụng có thể khai báo:

~~~text
SecurityFilterChain 1: /api/** -> CORS API dành cho SPA
SecurityFilterChain 2: /admin/** -> CORS admin riêng hoặc same-origin
SecurityFilterChain 3: fallback web form
~~~

Điểm cần điều tra:

1. `@Order` và `securityMatcher` của mỗi chain có được thiết kế cho **cả OPTIONS lẫn actual method**?
2. Mỗi chain sử dụng CORS source nào? Có nhiều beans cùng kiểu làm auto-detection mơ hồ không?
3. Có một security catch-all chain match trước tất cả route và dùng policy khác không?
4. MVC controller/source có thêm policy khác với selected security chain không?
5. Gateway có route `/api/**` và `/admin/**` bằng policy toàn cục khác với backend không?

### Gắn source tường minh khi nhiều policies

Trong cấu hình Servlet hiện đại có thể sử dụng:

~~~java
@Bean
SecurityFilterChain apiChain(HttpSecurity http,
                             CorsConfigurationSource apiCors)
        throws Exception {
    http.securityMatcher("/api/**");
    http.cors(cors -> cors.configurationSource(apiCors));
    http.authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated()
    );
    return http.build();
}
~~~

Ví dụ này minh họa **ý tưởng tiêm source đúng cho chain**; khi có nhiều beans cùng loại, cần dùng `@Qualifier` hoặc khai báo rõ bean name để inject không mơ hồ. Đảm bảo bean thực tế đã cấu hình allowedOrigins/methods/headers đúng, và các auth/CSRF/session filters vẫn được bố trí theo threat model.

**CORS source dùng sai không nhất thiết gây ACAO trùng** — nó cũng có thể tạo ACAO đơn nhưng không khớp Origin hoặc 403 preflight. Cần phân loại đúng triệu chứng.

## 14. Spring Reactive/WebFlux: nguồn gốc và vị trí xử lý CORS

Reactive dùng các lớp khác Servlet:

| Servlet | Reactive/WebFlux |
|---|---|
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `HttpSecurity` | `ServerHttpSecurity` |
| `CorsFilter` | `CorsWebFilter` hoặc CORS integration trong reactive security |
| `org.springframework.web.cors.UrlBasedCorsConfigurationSource` | `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource` |
| `HttpServletRequest` | `ServerWebExchange` |
| `MockMvc` | `WebTestClient` |

Giả sử WebFlux endpoint tại `/api/**` có CORS source:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
public class ReactiveCorsConfig {

    @Bean
    CorsConfigurationSource reactiveCorsConfigurationSource() {
        CorsConfiguration policy = new CorsConfiguration();
        policy.setAllowedOrigins(List.of(
            "https://app.example.com",
            "https://staging.app.example.com"
        ));
        policy.setAllowedMethods(List.of("GET", "POST", "PUT"));
        policy.setAllowedHeaders(List.of(
            "Content-Type", "X-CSRF-TOKEN", "X-XSRF-TOKEN"
        ));
        policy.setAllowCredentials(true);
        policy.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", policy);
        return source;
    }
}
~~~

### Gắn CORS source vào Reactive security chain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.reactive.CorsConfigurationSource;

@Configuration
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            CorsConfigurationSource reactiveCorsConfigurationSource) {
        http.cors(cors -> cors
            .configurationSource(reactiveCorsConfigurationSource));
        http.authorizeExchange(auth -> auth
            .pathMatchers("/api/public/**").permitAll()
            .pathMatchers("/api/**").authenticated()
            .anyExchange().denyAll()
        );
        http.formLogin(Customizer.withDefaults());
        http.csrf(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Các API Java ở đây minh họa cấu hình Spring Security WebFlux phiên bản tương thích. Với Spring Session Reactive hoặc gateway Reactive, hãy kiểm tra bean thực tế và source CORS nào được sử dụng. **Không import nhầm source Servlet** vào reactive security configuration.

## 15. CorsWebFilter toàn cục + ServerHttpSecurity.cors: đừng phát header hai lần

WebFlux cũng cho phép đăng ký một `CorsWebFilter`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.CorsWebFilter;

@Bean
CorsWebFilter corsWebFilter(CorsConfigurationSource source) {
    return new CorsWebFilter(source);
}
~~~

**Không tự động thêm filter này vào một ứng dụng đã có CORS được tích hợp ở security chain**, rồi cho rằng browser sẽ chấp nhận nhiều ACAO hơn. Nếu có cả global `CorsWebFilter`, Security CORS integration, WebFlux handler mapping CORS và gateway CORS, phải điều tra order, policy và **người thực sự viết header**.

Không phải cứ có hai cơ chế hỗ trợ CORS là chắc chắn response lặp: một processor có thể kết thúc xử lý preflight sớm; một processor khác có thể nhận biết header đã có hoặc không chạy. **Phép thử cuối cùng là headers thực tế của cả preflight và actual response**.

### Custom WebFilter có thể ghi đè sai

Một đoạn code dạng:

~~~java
exchange.getResponse().getHeaders()
    .add("Access-Control-Allow-Origin", "*");
~~~

ở custom `WebFilter` hoặc error handler có thể thêm giá trị ACAO vào response do CORS processor đã tạo. Đừng “sửa” bằng cách thêm `.set(...)` ở nhiều chỗ. Loại bỏ nguồn ghi header không thuộc chủ sở hữu CORS.

## 16. Origin patterns, wildcard subdomain và null Origin

Trong Spring, `CorsConfiguration` có thể hỗ trợ `allowedOriginPatterns` cho các mô hình cần linh hoạt, thay cho `allowedOrigins` exact list.

~~~java
CorsConfiguration cors = new CorsConfiguration();
cors.setAllowedOriginPatterns(List.of(
    "https://*.example.com"
));
cors.setAllowCredentials(true);
~~~

Đây là **ví dụ khả năng cấu hình, không phải khuyến nghị mặc định**. Với credentials, pattern rộng như vậy có thể cho phép cả subdomain không đáng tin (preview sites, user-content hosts, subdomain takeover). Spring có thể phát **origin cụ thể đã được so khớp** thay vì literal pattern trong ACAO, nhưng việc pattern trùng kỹ thuật không đồng nghĩa tất cả origin được phép đều an toàn.

### Ưu tiên danh sách origin tường minh

~~~java
cors.setAllowedOrigins(List.of(
    "https://app.example.com",
    "https://admin.example.com"
));
~~~

Nếu môi trường review/deploy tạo subdomain động, thiết kế một cơ chế origin allowlist có quản lý và thu hồi được. Không dùng `setAllowedOriginPatterns(List.of("*"))` cho endpoint có session credentials chỉ để “hết CORS”.

### Origin: null là một trường hợp đặc biệt

Browser có thể serialize Origin thành `null` trong một số ngữ cảnh opaque origin như sandboxed iframe hoặc file URL:

~~~http
Origin: null
~~~

**Không mặc định cho phép `Access-Control-Allow-Origin: null` đối với API nhạy cảm**. Nhiều nguồn không đáng tin có thể tạo opaque origin, nên “cho phép null” không mang nghĩa chỉ tin một file local cụ thể.

### Biểu thức tự viết không thay thế parser Origin

Nếu tự viết code kiểm tra CORS:

~~~java
if (origin.endsWith("example.com")) {
    // Phản ví dụ: kiểm tra hậu tố chuỗi không đủ an toàn.
}
~~~

thì một hostname không thuộc trust boundary có thể qua kiểm tra trong những điều kiện nhất định. Dùng cơ chế CORS do framework cung cấp, exact origins hoặc pattern có quy tắc chặt và đã review.

## 17. Header Access-Control-Allow-Credentials và biến thể response lỗi

Trong response có credentials, header:

~~~http
Access-Control-Allow-Credentials: true
~~~

cần có giá trị theo cú pháp mong đợi; không dùng:

~~~http
Access-Control-Allow-Credentials: True
Access-Control-Allow-Credentials: true, true
~~~

như thể các dạng đó tương đương. Khi nhiều tầng tự thêm `Access-Control-Allow-Credentials`, giá trị lặp hoặc bị gộp cũng có thể làm browser từ chối.

### Response 401/403/500 cũng là CORS response

Nếu actual API request có Origin hợp lệ nhưng authentication filter trả 401 trước khi một custom CORS middleware chạy, browser có thể thấy **CORS error** thay vì cho JavaScript đọc HTTP 401. Điều đó làm frontend không biết nên hiển thị login hay báo lỗi kết nối.

Một cấu hình đúng cần:

- Xử lý CORS ở vị trí thích hợp trước authentication/authorization.
- Cho phép Origin hợp lệ nhận response lỗi có CORS headers phù hợp, **không tiết lộ thông tin nhạy cảm hơn mức cần thiết**.
- Giữ 401/403 thật của authentication/authorization; không đổi chúng thành 200 để che lỗi.
- Đảm bảo gateway/CDN error responses không thêm ACAO `*` bên cạnh ACAO đã tính.

### Không tự gắn ACAO vào tất cả exception handlers

Một `@ControllerAdvice` hoặc `ErrorWebExceptionHandler` thêm ACAO để “sửa CORS trên lỗi 500” có thể tạo xung đột với policy của security filter. Hãy để **CORS owner** xử lý header cho mọi response path đúng chức năng, test cả success và failure.

## 18. DevTools: nhìn đồng thời Origin và ACAO trên từng request

Trong browser DevTools → Network, bắt đầu bằng một request lỗi có thể tái hiện. Bật Preserve log khi có redirect để không mất response preflight hoặc login. Ghi:

| Vị trí | Trường cần xem | Ý nghĩa |
|---|---|---|
| Document đang chạy | URL thật, scheme/host/port | Origin của JavaScript là gì? |
| OPTIONS request (nếu có) | `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers` | Browser đang xin phép gì? |
| OPTIONS response | Status, ACAO, Allow-Methods, Allow-Headers, ACAC | Browser đã chấp thuận preflight chưa? |
| Actual request | `Origin`, method, URL, Cookie/Authorization presence | Có request thật được gửi không? |
| Actual response | ACAO, ACAC, status, `Vary` | Tại sao JS không đọc được response? |
| Redirect/error response | `Location`, ACAO, response source | Header sai chỉ ở error/redirect branch? |

### Đừng chỉ nhìn Headers được DevTools gộp lại

Các công cụ có thể hiển thị ACAO lặp thành một dòng có dấu phẩy. Một số trình duyệt có thông báo dạng “multiple values” hoặc “not equal to the supplied origin”. Khi điều tra:

1. Ghi chính xác giá trị `Origin` của **request đang lỗi**.
2. Ghi số lượng/dạng ACAO trong **response tương ứng**, không lấy ACAO từ request khác.
3. So `https://app.example.com` với `http://app.example.com`, `https://staging.app.example.com` và port thực.
4. Xem `Access-Control-Allow-Credentials` có đúng trong credentialed flow.
5. Nếu GET thành công nhưng POST lỗi, kiểm tra **OPTIONS, POST, response POST** theo từng bước.

**Nếu OPTIONS không xuất hiện**, có thể do request không cần preflight, browser có preflight cache, hoặc CSP/mixed content/network chặn trước khi gửi. Đừng coi “không có OPTIONS” là bằng chứng policy CORS không được dùng.

### Không chia sẻ nguyên secrets

Trong ảnh Network hoặc log kỹ thuật, che `Cookie`, `Authorization`, CSRF header values và thông tin cá nhân. Để chẩn đoán CORS chỉ cần **tên header, Origin, status, ACAO/ACAC, path và request ID**. Không chụp lại Bearer token hoặc session ID.

## 19. Curl: tái hiện preflight đúng bộ header

Trong lab có quyền kiểm soát, giả lập preflight mà browser có thể gửi:

~~~bash
curl -i -X OPTIONS 'https://api.example.com/api/profile' \
  -H 'Origin: https://app.example.com' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type,x-csrf-token'
~~~

Khi response là:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET,POST,PUT
~~~

thì lỗi duplicate ACAO đã có ngay ở preflight. Tìm owner ở tầng response.

### Đối chứng Origin không khớp

~~~bash
curl -i -X OPTIONS 'https://api.example.com/api/profile' \
  -H 'Origin: https://staging.app.example.com' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type,x-csrf-token'
~~~

Nếu staging origin chưa được cấp phép, framework có thể trả `403 Invalid CORS request` hoặc một response không được browser chấp thuận; **đây có thể là quyết định bảo mật đúng**, không phải lúc nào cũng cần sửa thành 200.

### Không tự mang credentials vào preflight

CORS preflight của browser thường không kèm Cookie hoặc Bearer credential của actual request:

~~~http
Origin: https://app.example.com
Access-Control-Request-Headers: authorization,x-csrf-token
~~~

Trong trường hợp này browser chỉ hỏi có được gửi **tên header** `Authorization` và `X-CSRF-TOKEN` sau đó hay không; preflight không gửi giá trị secret.

### Curl không thực thi CORS như browser

`curl` nhận 200 và in JSON là kết quả HTTP client; nó **không chứng minh JavaScript cross-origin được browser cho đọc**. Khi cần kết luận, kết hợp response headers từ curl với DevTools/Playwright.

Không dùng `-L` khi đang muốn tìm redirect 301/302 của preflight vì nó có thể che response ban đầu. Không thêm `-k` để bỏ kiểm tra TLS làm “cách sửa CORS”; lỗi certificate/TLS phải được chẩn đoán và sửa riêng.

## 20. So sánh tại Spring origin và đường public để tìm tầng thêm header

Đây là phép thử quan trọng nhất cho **duplicate ACAO do hạ tầng**.

~~~text
Browser
  -> https://api.example.com  (public CDN/gateway)
  -> http://spring-service:8080  (origin nội bộ)
~~~

Ở môi trường kiểm thử được phép, gửi **cùng method, path, Origin và ACR headers** tới hai điểm:

| Quan sát | Diễn giải |
|---|---|
| Origin trả 1 ACAO, public trả 2 ACAO | Có tầng phía trước thêm header |
| Origin đã trả 2 ACAO | Điều tra Spring/custom filters/handlers hoặc proxy còn gần origin |
| Origin trả ACAO đúng, public trả ACAO sai | Gateway rewrite/override hoặc cache |
| OPTIONS origin 200, public 401/403/405 | Edge/proxy có thể chặn preflight trước CORS |
| Origin và public đều đúng, browser vẫn lỗi | Kiểm tra URL/Origin thực, credentials, CSP, redirect và browser behavior |

**Đừng dùng “direct origin URL” tùy tiện trên production** nếu nó bỏ qua authentication hoặc network boundary. Chỉ thử trong staging/đường quản trị đã được cấp phép, dùng DNS/routing phù hợp. Nếu không thể gọi trực tiếp origin, đối chiếu có kiểm soát các access logs và header snapshots tại proxy.

### Chọn đúng Host và đường đi

Khi proxy thay host hoặc path, một request tới origin bằng URL nội bộ có thể được chọn sang virtual host/security chain khác với public request. Để phép thử có giá trị:

1. Ghi public URL và upstream route.
2. Bảo đảm path cuối cùng thực nhận tại Spring tương đương.
3. Nếu cần, sử dụng header forwarded/Host **chỉ trên môi trường cho phép** với trust boundary đúng.
4. So cùng Origin và CORS policy version.
5. Đối chiếu response theo request ID, không so hai request tình cờ khác route.

## 21. Lỗi trùng chỉ xuất hiện với 401/403/500 hoặc redirect

Một hệ thống có thể:

~~~text
GET /api/public/ping -> 200 + ACAO đúng (Spring)
GET /api/profile     -> 401 + ACAO trùng (Gateway error handler)
POST /api/profile    -> 403 + ACAO thiếu (Security entry point trước CORS)
~~~

Nếu chỉ test 200 happy path, sẽ bỏ sót lỗi ở response lỗi.

### Cách lập ma trận kiểm tra

| Response branch | Mục tiêu xác nhận |
|---|---|
| Public GET thành công | ACAO một giá trị đúng |
| Authenticated GET thiếu session | 401/302 thật, ACAO đúng nếu origin được phép |
| POST có session nhưng thiếu CSRF | CSRF 403 thật, không thêm ACAO lần hai |
| User thiếu quyền | Authorization 403 thật, browser đọc status theo CORS contract |
| Controller validation 400 | Không mất ACAO khi error handler trả body |
| Internal error 500 | Không phản chiếu Origin bừa bãi, không rò exception |
| Redirect 301/302/307/308 | Location/canonical URL hợp lý, không phụ thuộc vào redirect của preflight |

Lưu ý: HTTP error response có CORS headers phù hợp **không có nghĩa** browser hay frontend được phép thực hiện nghiệp vụ; nó chỉ giúp frontend đọc status/body an toàn theo policy.

### Quy tắc an toàn

Không thêm:

~~~http
Access-Control-Allow-Origin: *
~~~

vào mọi error response của proxy để giấu lỗi. Nếu response đã có một ACAO hợp lệ, gateway thêm wildcard có thể **làm lỗi nặng hơn**; với credentials wildcard càng sai.

## 22. MockMvc: khẳng định ACAO chỉ có một giá trị

Giả định Servlet app có `CorsConfigurationSource` và `SecurityFilterChain` như mục 11. Khi kiểm thử, **không chỉ assert getHeader() trả origin mong đợi**, vì điều đó có thể không phát hiện nhiều values.

~~~java
import java.util.Collection;
import org.springframework.test.web.servlet.MvcResult;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

MvcResult result = mockMvc.perform(options("/api/profile")
        .header("Origin", "https://app.example.com")
        .header("Access-Control-Request-Method", "POST")
        .header("Access-Control-Request-Headers",
            "content-type,x-csrf-token"))
    .andExpect(status().isOk())
    .andReturn();

Collection<String> acao = result.getResponse()
    .getHeaders("Access-Control-Allow-Origin");

assertEquals(1, acao.size(), "ACAO must be single-valued");
assertEquals("https://app.example.com",
    acao.iterator().next(), "ACAO must match request Origin");
~~~

Ví dụ kỳ vọng `CorsFilter` mặc định của Spring trả HTTP 200 cho preflight; một custom CORS handler có thể trả 204, khi đó điều chỉnh assertion status theo hợp đồng thực tế. Kiểm tra `Collection.size()==1` và **giá trị chính xác**: nếu một proxy gộp hai ACAO thành cùng một string chứa dấu phẩy, chỉ kiểm tra size là chưa đủ.

### Test Origin khác và Origin không được phép

~~~java
// Đã được cho phép trong cấu hình ví dụ.
MvcResult staging = mockMvc.perform(options("/api/profile")
        .header("Origin", "https://staging.app.example.com")
        .header("Access-Control-Request-Method", "POST"))
    .andExpect(status().isOk())
    .andReturn();

assertEquals("https://staging.app.example.com",
    staging.getResponse().getHeader("Access-Control-Allow-Origin"));

// Không nằm trong allowlist.
mockMvc.perform(options("/api/profile")
        .header("Origin", "https://untrusted.example.net")
        .header("Access-Control-Request-Method", "POST"))
    .andExpect(status().isForbidden());
~~~

Test cuối mô phỏng Spring CorsFilter chuẩn thường trả 403 khi Origin không hợp lệ. Nếu ứng dụng có custom processor/gateway trả status khác, kiểm tra policy thực tế **không cho browser chấp thuận** thay vì ép mọi triển khai có cùng mã lỗi.

### Test origin khác scheme/port

~~~java
mockMvc.perform(options("/api/profile")
        .header("Origin", "http://app.example.com")
        .header("Access-Control-Request-Method", "POST"))
    .andExpect(status().isForbidden());

mockMvc.perform(options("/api/profile")
        .header("Origin", "https://app.example.com:8443")
        .header("Access-Control-Request-Method", "POST"))
    .andExpect(status().isForbidden());
~~~

Hai negative cases phát hiện các bug mà một test chỉ so hostname có thể bỏ qua. Không dùng `allowedOriginPatterns("*")` để làm chúng thành công một cách ngầm định.

## 23. MockMvc: kiểm tra actual response và lỗi CSRF độc lập

Giả định controller demo `POST /api/profile` trả 204 khi được phép:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

MvcResult ok = mockMvc.perform(post("/api/profile")
        .header("Origin", "https://app.example.com")
        .with(user("alice").roles("USER"))
        .with(csrf())
        .contentType("application/json")
        .content("{\"displayName\":\"Alice\"}"))
    .andExpect(status().isNoContent())
    .andReturn();

assertEquals(1, ok.getResponse()
    .getHeaders("Access-Control-Allow-Origin").size());
assertEquals("https://app.example.com", ok.getResponse()
    .getHeader("Access-Control-Allow-Origin"));

MvcResult csrfDenied = mockMvc.perform(post("/api/profile")
        .header("Origin", "https://app.example.com")
        .with(user("alice").roles("USER"))
        .contentType("application/json")
        .content("{\"displayName\":\"Alice\"}"))
    .andExpect(status().isForbidden())
    .andReturn();

assertEquals("https://app.example.com", csrfDenied.getResponse()
    .getHeader("Access-Control-Allow-Origin"));
~~~

**Điều kiện:** project có dependency `spring-security-test`, MockMvc gắn Spring Security filters, endpoint tồn tại, authentication/authorization cho phép user demo và controller trả 204. Đây là ví dụ đặt trong test method, không phải test class biên dịch độc lập.

Không thấy ACAO trên một 403 tùy biến thì phải xác định CORS filter order hoặc handler đã tạo response; **đừng sửa bằng cách tắt CSRF**. Test `with(csrf())` còn không chứng minh browser thật biết lấy CSRF token; muốn chứng minh điều đó cần test GET token → POST cùng cookie/session.

## 24. CORS đơn nhưng sai Origin do cache hoặc nhiều environment

Một lỗi dễ hiểu sai:

~~~http
Origin: https://preview-123.app.example.com

Access-Control-Allow-Origin: https://app.example.com
~~~

Không có ACAO duplicate. Có thể:

- Frontend preview origin chưa được phép.
- Environment variables của Spring/gateway chỉ chứa production origin.
- Proxy trả response cache của production Origin.
- Canonical redirect đưa request sang host/port khác.
- Một error handler hard-code origin mặc định, bỏ qua Origin hợp lệ của request.

**Phép thử:** gọi OPTIONS và actual GET từ từng origin được phép; so ACAO tại Spring origin và public CDN; kiểm tra `Vary: Origin`, cache status và config version. Chỉ thêm preview origin theo quy trình đã review, tránh mở toàn bộ `https://*.example.com` nếu có subdomain không đáng tin.

## 25. WebTestClient: kiểm thử ACAO trong Reactive/WebFlux

Với cấu hình Reactive tại mục 14, một preflight không cần mock authentication:

~~~java
import java.util.List;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import static org.junit.jupiter.api.Assertions.assertEquals;

EntityExchangeResult<byte[]> preflight = webTestClient.options()
    .uri("/api/profile")
    .header("Origin", "https://app.example.com")
    .header("Access-Control-Request-Method", "POST")
    .header("Access-Control-Request-Headers",
        "content-type,x-csrf-token")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .returnResult();

List<String> allowOrigin = preflight.getResponseHeaders()
    .getOrEmpty("Access-Control-Allow-Origin");
assertEquals(List.of("https://app.example.com"), allowOrigin);

// Origin không có trong danh sách được duyệt.
webTestClient.options()
    .uri("/api/profile")
    .header("Origin", "https://untrusted.example.net")
    .header("Access-Control-Request-Method", "POST")
    .exchange()
    .expectStatus().isForbidden();
~~~

Như Servlet, test này giả định Spring CORS processor mặc định trả 200 cho preflight hợp lệ và 403 cho Origin không hợp lệ. Nếu stack đã custom CORS handler/response status, thay assertion HTTP cụ thể nhưng vẫn phải xác minh **browser không được chấp thuận với Origin sai**.

### Đọc danh sách header, không chỉ lấy giá trị đầu tiên

`getResponseHeaders().getOrEmpty("Access-Control-Allow-Origin")` trả danh sách giá trị mà WebTestClient nhìn thấy. So với `List.of(expectedOrigin)` giúp phát hiện cả tình huống:

- Hai giá trị header tách biệt.
- Một giá trị đã bị gộp thành `expectedOrigin, *`.
- Một ACAO duy nhất nhưng không đúng origin.

Test chỉ quan sát mock/reactive response, **không phát hiện ACAO do gateway thêm sau Spring**. Với lỗi production, cần thêm test qua HTTP public URL.

## 26. WebTestClient: actual response, CSRF và lỗi không được che bởi CORS

Giả sử WebFlux có endpoint `POST /api/profile` trả 204 khi user có quyền và CSRF token hợp lệ:

~~~java
import org.springframework.http.MediaType;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;

EntityExchangeResult<byte[]> ok = webTestClient
    .mutateWith(mockUser("alice").roles("USER"))
    .mutateWith(csrf())
    .post()
    .uri("/api/profile")
    .header("Origin", "https://app.example.com")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue("{\"displayName\":\"Alice\"}")
    .exchange()
    .expectStatus().isNoContent()
    .expectBody()
    .returnResult();

assertEquals(List.of("https://app.example.com"),
    ok.getResponseHeaders()
        .getOrEmpty("Access-Control-Allow-Origin"));

EntityExchangeResult<byte[]> denied = webTestClient
    .mutateWith(mockUser("alice").roles("USER"))
    .post()
    .uri("/api/profile")
    .header("Origin", "https://app.example.com")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue("{\"displayName\":\"Alice\"}")
    .exchange()
    .expectStatus().isForbidden()
    .expectBody()
    .returnResult();

assertEquals(List.of("https://app.example.com"),
    denied.getResponseHeaders()
        .getOrEmpty("Access-Control-Allow-Origin"));
~~~

Ví dụ giả định route đã có controller chấp nhận JSON, trả 204 sau authorization và CSRF validation; `spring-security-test` được cấu hình. Nếu API dùng Bearer-only stateless hoặc custom denial handler, thay test theo đúng auth contract. **CORS hợp lệ không có nghĩa POST thiếu CSRF phải thành công.**

### Minimal controller fixture của lab

~~~java
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ApiLabController {
    @GetMapping("/api/public/ping")
    Map<String, String> ping() {
        return Map.of("status", "ok");
    }

    @PostMapping("/api/profile")
    ResponseEntity<Void> update(@RequestBody Map<String, String> body) {
        // Chỉ dùng trong môi trường kiểm thử, không ghi dữ liệu thật.
        return ResponseEntity.noContent().build();
    }
}
~~~

Không copy controller demo này sang production mà thiếu validation và resource-level authorization. CSRF bảo vệ một kiểu tấn công liên quan browser credentials, không thay thế kiểm tra quyền sở hữu tài nguyên.

## 27. Playwright: kiểm tra chính browser có đọc được response

Một HTTP client có thể nhận 200 ngay cả khi CORS response sai. Với browser E2E, hãy đặt frontend và API trên **hai origins thật**, HTTPS với certificate hợp lệ trong môi trường test. Ví dụ:

~~~text
Frontend: https://app.example.test/test-page
API:      https://api.example.test/api/public/ping

Spring/Gateway lab CORS allowlist:
  https://app.example.test
~~~

Các hostname chỉ là ví dụ dùng trong lab do đội kiểm thử thiết lập; chúng không tự tồn tại. Nếu dùng bộ config các mục trên, đổi allowlist **trong môi trường lab** cho phù hợp.

### Test Origin hợp lệ

~~~javascript
import { test, expect } from "@playwright/test";

test("frontend origin hợp lệ đọc được API", async ({ page }) => {
  await page.goto("https://app.example.test/test-page");

  const result = await page.evaluate(async () => {
    const response = await fetch(
      "https://api.example.test/api/public/ping",
      {
        method: "GET",
        // Header tùy chỉnh chỉ để kích hoạt preflight ở lab:
        headers: { "X-CSRF-TOKEN": "lab-placeholder" }
      }
    );
    return {
      status: response.status,
      body: await response.json()
    };
  });

  expect(result.status).toBe(200);
  expect(result.body.status).toBe("ok");
});
~~~

Test giả định `/test-page` không bị CSP `connect-src` chặn API và policy cho `X-CSRF-TOKEN`; API ping không dùng token placeholder làm chứng cứ CSRF. Test này chỉ đo khả năng **browser gửi và đọc GET cross-origin** qua preflight.

### Test Origin không được phép

~~~javascript
import { test, expect } from "@playwright/test";

test("origin không hợp lệ không đọc được response", async ({ page }) => {
  await page.goto("https://untrusted.example.test/test-page");

  const blocked = await page.evaluate(async () => {
    try {
      await fetch("https://api.example.test/api/public/ping", {
        headers: { "X-CSRF-TOKEN": "lab-placeholder" }
      });
      return false;
    } catch {
      return true;
    }
  });

  expect(blocked).toBe(true);
});
~~~

Một `fetch` bị reject **cũng có thể do DNS, TLS, CSP hoặc network**, không chỉ CORS. Với negative test, cần đối chiếu browser Console/Network và API/gateway access logs để chứng minh nguyên nhân. Không phải chỉ thấy test `blocked === true` là kết luận policy CORS đúng.

### Test duplicate headers qua gateway

Trong một **môi trường lab có gateway cố tình thêm ACAO trùng**, cùng test Origin hợp lệ phải thất bại ở browser; khi bỏ header writer trùng ở gateway, test sẽ thành công. Đừng kiểm thử bằng cách vô hiệu browser web security hoặc cài tiện ích bỏ CORS: như vậy mất chính cơ chế cần xác minh.

**Hạn chế của Playwright request events:** preflight được cache/hiển thị khác nhau giữa browser engines; không viết assertion phụ thuộc tuyệt đối vào việc Playwright luôn bắt được OPTIONS dưới dạng event thông thường. Dùng browser fetch để xác nhận hành vi và proxy logs/curl để xác nhận header của preflight.

## 28. Những lỗi CORS từ hạ tầng mà MockMvc không thể nhìn thấy

Một sơ đồ production:

~~~text
Browser
  -> CDN cache
  -> WAF
  -> API gateway
  -> Spring Boot API
~~~

Các sự cố đặc thù:

1. CDN hoặc ingress thêm ACAO vào response vốn đã có ACAO.
2. Gateway tự phản hồi OPTIONS nhưng upstream Spring trả ACAO khác trên actual response.
3. WAF sinh response 403 có ACAO `*` thay vì origin được phép.
4. HTTP/2 hoặc reverse proxy ghép nhiều header lines thành một giá trị chứa dấu phẩy.
5. CDN cache một ACAO variant rồi trả cho Origin khác.
6. Redirect sau login làm frontend gọi API tại hostname/port khác, không có trong allowlist.
7. Một rule chỉ áp dụng cho `/api/v1/**`, trong khi version mới dùng `/api/v2/**`.
8. Gateway strip `Vary: Origin` hoặc bộ headers CORS trên error branches.

### Nguyên tắc điều tra

- **So response Spring gốc và public**, theo cùng request metadata.
- Ghi phiên bản CORS config ở từng tầng.
- Xác định gateway có *add*, *set*, *append*, *preserve* hoặc *strip* header.
- Kiểm tra **OPTIONS và actual response** qua đường public.
- Khi bỏ nguồn header trùng, xác nhận origin không được phép vẫn bị từ chối.
- Đảm bảo không tạo side effect nghiệp vụ trong phép thử POST nếu không cần; dùng GET ping hoặc fixtures an toàn trước.

Một code change trong Spring không thể sửa ACAO do CDN thêm **sau khi Spring đã trả response**. Chỉ sửa tầng đã được chứng minh là nguồn lỗi.

## 29. CSP, HTTPS và proxy redirect cũng có thể được báo như lỗi CORS

Một frontend có CSP:

~~~http
Content-Security-Policy: default-src 'self'; connect-src 'self'
~~~

và gọi `https://api.example.com` từ `https://app.example.com`. Browser có thể chặn trước khi gửi vì `connect-src` không cho API origin. Khi đó **không có HTTP response ACAO để phân tích**.

Các tình huống khác:

- HTTP API được gọi từ HTTPS document bị mixed-content policy chặn hoặc được browser nâng cấp theo policy.
- Preflight nhận redirect từ HTTP tới HTTPS hoặc từ `/api/profile` tới `/api/profile/`.
- Certificate/TLS handshake thất bại.
- Service worker trả response khác với API mạng thực.
- Browser extension hoặc enterprise policy chặn request.

**Phân biệt bằng chứng:** xem Network request thật sự xuất hiện chưa, Console nêu CSP/mixed content/TLS hay ACAO mismatch, redirect chain và origin public. Không nới CORS khi lỗi còn chưa tới CORS layer.

### CORS không thay thế CSP

`connect-src` kiểm soát nơi tài liệu được kết nối, còn CORS kiểm soát quyền đọc response cross-origin. Một request phải thỏa **cả hai** nếu applicable. Không dùng `'unsafe-inline'` CSP hay vô hiệu HSTS để sửa ACAO duplicate.

## 30. Cookie/session và CSRF: vì sao ACAO đúng chưa đủ

Một SPA credentialed:

~~~javascript
const response = await fetch("https://api.example.com/api/profile", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": csrfToken
  },
  body: JSON.stringify({displayName: "Alice"})
});
~~~

Sau khi CORS được sửa:

| Tình huống | Kết quả có thể thấy | Điều cần sửa |
|---|---|---|
| Session cookie không gửi vì `Domain`/`Path`/`SameSite`/`Secure` | 401/302 login hoặc CSRF 403 | Cookie/session/credentials; không nới CORS |
| JS không gửi CSRF header hợp lệ | 403 từ CSRF filter | Bootstrap token đúng ngữ cảnh |
| Token cũ sau login/logout | 403 CSRF | Tải token mới, giữ đúng session |
| User thiếu quyền | 403 authorization | Role/scope/ownership, không tắt CSRF |
| HTTP firewall từ chối URL | 400 hoặc custom rejection | Sửa canonical URL/request |
| Tất cả hợp lệ, controller xử lý | 2xx/3xx/4xx theo nghiệp vụ | Kiểm thử response/side effects |

**Cẩn trọng:** khi CORS sai, actual POST có thể **đã thực thi**, browser chỉ không đọc được response. Không tự retry POST thanh toán/đặt hàng để “chữa” lỗi CORS; cần xác minh trạng thái nghiệp vụ và dùng idempotency controls nếu phù hợp.

### Fetch credentials không bỏ qua cookie policy

`credentials: "include"` cho phép trình duyệt gửi credentials cross-origin khi cookie đủ điều kiện, nhưng nó **không bỏ qua** cookie Secure/SameSite/Domain/Path, third-party cookie restrictions hoặc CORS.

Đừng dùng ACAO wildcard để “làm cookie đi được”. ACAO điều khiển quyền đọc response; cookie policy thuộc một lớp khác.

## 31. Kịch bản A — Spring đúng một ACAO, Nginx/gateway thêm ACAO thứ hai

**Hiện tượng:** local Spring Boot và test MockMvc đều PASS; staging qua reverse proxy thì browser báo multiple ACAO values.

~~~text
Spring origin:
  HTTP 200
  Access-Control-Allow-Origin: https://app.example.com

Public HTTPS gateway:
  HTTP 200
  Access-Control-Allow-Origin: https://app.example.com
  Access-Control-Allow-Origin: *
~~~

**Bằng chứng cần thu:** cùng request GET/OPTIONS, Origin/path giống nhau; so response headers ở Spring origin và public URL. Trong gateway config, tìm rule thêm ACAO áp toàn cục, đặc biệt trên mọi status code hoặc trong error handler.

**Cách sửa đúng:** chọn Spring làm CORS owner **hoặc** gateway làm CORS owner cho route; bỏ nguồn header writer trùng. Nếu gateway chỉ forward, giữ ACAO Spring và không tự append. Nếu gateway xử lý CORS, policy phải được áp dụng nhất quán cho preflight lẫn actual/error response và Spring không phát xung đột.

**Kiểm thử hồi quy:**

1. OPTIONS Origin hợp lệ có đúng **một** ACAO.
2. GET public có đúng một ACAO.
3. Response 401/403/500 không thêm wildcard hoặc giá trị thứ hai.
4. Origin không hợp lệ không được browser chấp thuận.
5. Playwright từ frontend origin thật đọc được response khi được phép.

**Không sửa** bằng cách chuyển ACAO Spring sang `*`: gateway vẫn thêm một giá trị nữa và policy credentialed còn sai.

## 32. Kịch bản B — Frontend staging khác Origin production, policy chỉ cho production

**Hiện tượng:** production frontend hoạt động; staging/preview lại bị CORS dù API response trả 200.

~~~text
Browser:
  Origin: https://staging.app.example.com

API response:
  Access-Control-Allow-Origin: https://app.example.com
~~~

**Phân tích:** ACAO chỉ có một giá trị nhưng **không khớp**. Nguyên nhân có thể là:

- `allowedOrigins` không có staging origin.
- Deployment environment variable chưa được cập nhật.
- Preview frontend dùng port hoặc scheme khác với policy.
- Proxy cache bản response được tạo cho production Origin.
- Một fallback/error handler luôn hard-code production Origin.

**Quy trình:** xác nhận Origin trong Network, kiểm tra cấu hình tại đúng backend/gateway version, so response uncached và cached, tìm `Vary: Origin`, rồi thêm origin cụ thể **nếu thực sự được cho phép**.

**Không dùng allowed origin kiểu `https://*.example.com` theo phản xạ** nếu có subdomains không đáng tin hoặc user-generated content. Preview environments cần một quy trình cấp và thu hồi origin đã review.

## 33. Kịch bản C — ACAO "*" và credentials true

**Hiện tượng:**

~~~javascript
fetch("https://api.example.com/api/account", {
  credentials: "include"
});
~~~

Response:

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

Browser từ chối cho JavaScript đọc response credentialed dù HTTP status thành công.

**Nguyên nhân:** wildcard ACAO không phù hợp với credentials mode như vậy.

**Sửa đúng:** dùng allowlist origin cụ thể ở server, trả ACAO **khớp Origin request**, và có `Access-Control-Allow-Credentials: true` khi flow thực sự dùng credentials. Kiểm tra cookie policy, CSRF và authentication sau khi browser được đọc response.

**Đối chứng:** thử một origin không được cho phép; không phản chiếu request Origin bất kể nguồn nào.

### Trường hợp API không dùng credentials

Đối với một API public thực sự không dùng credentialed CORS, ACAO `*` có thể phù hợp. Nhưng đừng lấy policy của endpoint public này để áp dụng cho endpoint account/session; **mô hình dữ liệu và credentials quyết định policy**.

## 34. Kịch bản D — OPTIONS trả đúng headers, actual POST bị gateway thêm ACAO

**Hiện tượng:**

~~~text
OPTIONS /api/profile:
  200 + ACAO https://app.example.com (chỉ một giá trị)

POST /api/profile:
  204 + ACAO https://app.example.com
      + ACAO * (thêm bởi gateway error/response filter)
~~~

Browser gửi POST và backend xử lý dữ liệu, nhưng frontend nhận lỗi CORS.

**Chẩn đoán:** xem Network có POST thật và response POST có ACAO duplicate không. So response origin/public; kiểm tra gateway rule nào chỉ chạy trên actual methods, route hoặc status khác OPTIONS.

**Hướng sửa:** loại nguồn header duplicate ở path actual response; test cả OPTIONS và POST/GET/401/403. Đừng dựa vào OPTIONS PASS để kết luận CORS đã xong.

**Đặc biệt với POST không idempotent:** không tự gửi lại request khi browser báo CORS; API có thể đã thay đổi dữ liệu. Kiểm tra trạng thái bằng request an toàn hoặc idempotency mechanism theo thiết kế.

## 35. Kịch bản E — Header trùng chỉ khi authentication hoặc CSRF từ chối

**Hiện tượng:**

~~~text
GET /api/public/ping -> 200, ACAO đúng
GET /api/profile -> 401, ACAO không có
POST /api/profile thiếu CSRF -> 403, ACAO trùng
~~~

**Khả năng:**

- Authentication entry point tạo response trước khi CORS processor được áp dụng.
- Custom `AccessDeniedHandler` thêm ACAO dù CorsFilter đã phát.
- Gateway cấu hình thêm ACAO chỉ trên 4xx responses.
- Spring Boot error dispatch hoặc exception handler có CORS writer riêng.

**Cách thử có đối chứng:** cùng Origin và path, thử auth hợp lệ/không hợp lệ, token CSRF hợp lệ/không hợp lệ. Ghi chain/handler phát response và header tại origin/public.

**Cách sửa:** CORS owner phải có khả năng áp dụng policy cho response lỗi của các origin được phép; gỡ custom header writer trùng, không sửa HTTP 401/403 thành 200.

**Nhận định quan trọng:** một response 403 có CORS headers đúng **vẫn là 403**. Mục tiêu là frontend được đọc status hợp lệ, không phải bỏ authentication, CSRF hoặc authorization.

## 36. Kịch bản F — Một CORS policy cho toàn bộ domain làm API sai ranh giới

**Bối cảnh:** cùng hostname có:

~~~text
/api/public/**   -> dữ liệu công khai không cần cookies
/api/account/**  -> dữ liệu cá nhân dùng session
/api/admin/**    -> quyền quản trị và origin admin riêng
~~~

Gateway thêm:

~~~http
Access-Control-Allow-Origin: *
~~~

cho tất cả routes. Spring Security lại phát ACAO cụ thể cho account/admin, dẫn tới duplicate; nếu gateway ghi đè thay vì append, nó còn có thể làm policy quá rộng.

**Sửa theo phạm vi:** xác định chính sách cho từng route/trust boundary. Có thể:

- Để Spring Security nắm CORS cho account/admin và gateway không thêm ACAO.
- Tách gateway routes với CORS policies có allowlist riêng và không cho origin Spring phát header trùng.
- Dùng same-origin BFF cho các session-backed endpoints nếu phù hợp kiến trúc.

**Phải kiểm thử negative cases cho admin origin**: frontend public không được đọc API quản trị chỉ vì cùng domain public, kể cả khi user có một số cookies.

## 37. Kịch bản G — Cache/CDN phát ACAO của người dùng/Origin khác

**Hiện tượng:** refresh nhiều lần thì lúc PASS lúc FAIL; tất cả instances Spring cùng code.

~~~text
Request A:
  Origin: https://app.example.com
  Response cached: ACAO https://app.example.com

Request B:
  Origin: https://staging.app.example.com
  Cache HIT:
    ACAO https://app.example.com
~~~

Một response lỗi có thể do CDN không đưa `Origin` vào cache variant; còn response từ Spring origin với staging Origin vẫn trả ACAO đúng.

**Bằng chứng:**

1. Ghi cache status/age/vary headers qua public path.
2. So request cache hit và cache miss với cùng Origin.
3. So trực tiếp origin hoặc origin logs nếu được phép.
4. Xem CDN có strip hoặc không tôn trọng `Vary: Origin`.
5. Với preflight, kiểm tra cả `Access-Control-Request-Method` và `Access-Control-Request-Headers` trong cache variation.

**Sửa đúng:** cập nhật cache policy/key cho các response khác nhau theo Origin, hoặc không cache responses nhạy cảm; không tự thêm ACAO thứ hai trong edge. Với dữ liệu authenticated, cần kiểm tra riêng cache của response body có gây rò dữ liệu hay không.

## 38. Bảng chẩn đoán tổng hợp theo biểu hiện

| Dấu hiệu | Nguồn có khả năng | Kiểm tra ưu tiên | Hướng khắc phục |
|---|---|---|---|
| `Access-Control-Allow-Origin: A, *` | Header append từ nhiều tầng | Raw headers origin/public | Một CORS owner; bỏ nguồn append |
| Hai dòng ACAO cùng A | Multiple writers | HTTP headers list ở từng hop | Bỏ writer trùng, không chỉ kiểm tra first value |
| ACAO = A, request Origin = B | Allowlist/config/cache sai | Origin thực, config version, Vary | Chỉ thêm B nếu được duyệt; sửa cache |
| ACAO `*` + credentials include | Wildcard sai credentialed CORS | Fetch mode, ACAC, Cookie | Specific allowed origin |
| Preflight 403 Invalid CORS request | Method/headers/Origin bị policy từ chối | ACR-Method/Headers và allowlist | Giữ từ chối khi không hợp lệ |
| Preflight 401/302 | Auth/chain chạy trước CORS | Filter ordering/chain matcher | Tích hợp CORS sớm |
| OPTIONS PASS, actual 200 CORS FAIL | Actual response headers sai | Headers của GET/POST thật | Fix actual CORS owner |
| Chỉ 4xx/5xx CORS FAIL | Error handler/gateway policy khác | Test fail cases | CORS hợp lệ cả lỗi, giữ status |
| Chỉ staging/preview FAIL | Origin khác scheme/host/port | Network Origin vs allowedOrigins | Exact allowlist per environment |
| Chỉ qua CDN FAIL | Edge append/rewrite/cache | Direct origin/public diff | Fix edge header/cache |
| Browser báo lỗi, Network không có request | CSP/mixed-content/TLS | Console, network trace | Sửa đúng lớp trước CORS |
| OPTIONS 200, POST 403 CSRF | Actual request thiếu token | CSRF exception và request headers | Giữ CSRF; bootstrap token |
| OPTIONS 200, POST 401 | Cookie/auth sai | Request Cookies/Authorization | Sửa authentication/cookie |
| CORS chạy đúng nhưng JS thiếu response body | Exposed headers/binary/file policy hoặc logic JS | Browser response, Expose-Headers | Chỉ expose headers cần thiết |
| `Origin: null` được allow | Opaque origins có thể được tin quá rộng | Policy for sandbox/file context | Không allow null mặc định |
| Multiple `Vary` entries | Có thể là HTTP hợp lệ | Trường cụ thể và semantic | Đừng xóa Vary vì nhầm với ACAO |

**Không có một thông báo browser duy nhất xác nhận toàn bộ nguyên nhân.** Cùng một ACAO mismatch có thể do allowlist sai hoặc cache nhầm; duplicate có thể xuất hiện tại Spring, gateway hoặc proxy sau Spring. Dùng phép thử so sánh **cùng request, khác một yếu tố** để định vị.

## 39. Runbook: tìm và sửa nguồn ACAO trùng hoặc sai Origin

~~~mermaid
flowchart TD
    A[Browser báo lỗi CORS] --> B{HTTP request thực đã được gửi?}
    B -- Không --> C[CSP, mixed content, DNS/TLS, preflight chưa được cho phép]
    B -- Có --> D{Đây là OPTIONS hay actual request?}
    D --> E[Đọc Origin và response ACAO/ACAC]
    E --> F{ACAO là một giá trị đúng Origin?}
    F -- Có --> G[Kiểm tra credentials, Allow-Methods/Headers, actual response]
    F -- Không --> H{ACAO bị lặp hoặc có dấu phẩy?}
    H -- Có --> I[So origin Spring vs public gateway/CDN]
    H -- Không --> J[So exact scheme-host-port, allowlist và cache]
    I --> K[Chọn một CORS owner, bỏ nguồn header trùng]
    J --> L[Sửa allowlist/Origin hoặc cache variant theo quyền]
    K --> M[Test OPTIONS + actual GET/POST/error responses]
    L --> M
    G --> M
    M --> N[Positive + negative browser E2E + security regression]
~~~

### Bước 1 — Chọn đúng request lỗi

Ghi URL tài liệu frontend, Origin, API URL public, method, credentials mode, tên headers request và mã lỗi. Đừng nhầm error console từ request này với ACAO của request khác. Nếu không có request, kiểm tra CSP/TLS/mixed content và preflight cache trước.

### Bước 2 — Tách OPTIONS khỏi GET/POST

Nếu có preflight, xem status và Allow-Origin/Methods/Headers của **OPTIONS**. Nếu OPTIONS đã thành công nhưng POST/GET bị CORS, hãy tập trung vào **actual response** thay vì tiếp tục sửa preflight.

### Bước 3 — Đếm giá trị ACAO

Kiểm tra raw headers:

~~~text
Kỳ vọng:
  Access-Control-Allow-Origin: https://app.example.com

Sai: hai values
  Access-Control-Allow-Origin: https://app.example.com
  Access-Control-Allow-Origin: *

Sai: một string được gộp từ hai values
  Access-Control-Allow-Origin: https://app.example.com, *
~~~

Đếm số lượng header **và** kiểm tra cả giá trị; không dựa vào một helper `getHeader()` chỉ lấy phần tử đầu.

### Bước 4 — Nếu không trùng, so Origin tuyệt đối

So scheme, hostname và port, tính cả môi trường staging/preview, custom ports và redirect. Kiểm tra Origin không có path; xem frontend có thực sự chạy ở origin được đăng ký không.

### Bước 5 — Phân định trách nhiệm giữa các tầng

Gửi cùng request vào Spring origin và qua public hostname theo đường kiểm thử được phép. So gateway/ingress/CDN config, Spring Security chain, Spring MVC/WebFlux CORS source, custom filter và exception handler.

### Bước 6 — Kiểm tra cache và response lỗi

Nếu ACAO khác nhau theo Origin hoặc status, kiểm tra `Vary`/cache key, HTTP status 401/403/500, redirects, route rewrites và WAF. Đặc biệt kiểm tra error responses do gateway sinh, không chỉ controller responses.

### Bước 7 — Sửa đúng lớp

Xóa nguồn header writer trùng hoặc sửa exact allowedOrigins/pattern policy **sau security review**. Không dùng một wildcard global để che mismatch. Nếu là lỗi cache, sửa cache variant hoặc bypass cache nhạy cảm.

### Bước 8 — Kiểm thử hồi quy

Kiểm thử:

1. Origin hợp lệ được ACAO một giá trị đúng.
2. Origin không hợp lệ không được browser chấp thuận.
3. OPTIONS với allowed method/header được chấp thuận; method/header không hợp lệ bị từ chối.
4. Actual response thành công có ACAO/ACAC đúng.
5. 401/403/500 và redirect branches không bị duplicate hoặc thiếu header vô cớ.
6. Auth, authorization và CSRF vẫn từ chối request không hợp lệ.
7. Browser E2E qua **public hostname**, không chỉ mock application context.

## 40. Bật log để định vị policy, không tiết lộ secrets

Trong dev/staging khi cần:

~~~properties
logging.level.org.springframework.web.cors=DEBUG
logging.level.org.springframework.security=DEBUG

# Chỉ trong thời gian điều tra selected Servlet chain.
logging.level.org.springframework.security.web.FilterChainProxy=TRACE

# Nếu dùng Reactive security, bật trace tạm thời.
logging.level.org.springframework.security.web.server.WebFilterChainProxy=TRACE
~~~

Các logger và chi tiết log phụ thuộc framework version. Không thấy log từ một logger cụ thể **không chứng minh** CorsFilter chưa chạy nếu cấu hình logging chưa đúng. Kết hợp ứng dụng, proxy access logs và response headers.

### Bảng chứng cứ an toàn

| Trường | Ví dụ |
|---|---|
| Request ID | `req-12345` |
| Path/Method | `OPTIONS /api/profile` |
| Browser Origin | `https://app.example.com` |
| ACR-Method, ACR-Headers | `POST`, `content-type,x-csrf-token` |
| CORS owner theo thiết kế | Spring Security Servlet chain API |
| Header ACAO origin | 1 value: frontend Origin |
| Header ACAO public | 2 values: frontend Origin và wildcard |
| Gateway version/policy | ID cấu hình không chứa secrets |
| Browser CORS outcome | rejected: multiple ACAO values |
| Actual request sent | yes/no |

**Không log:** CSRF token, `Cookie`, session ID, JWT/Bearer, `Authorization` value, passwords hoặc response body chứa dữ liệu người dùng. CORS diagnosis thường chỉ cần **header names**, Origin và policy decision, không cần header secrets.

## 41. Những cách sửa sai làm CORS yếu đi hoặc che lỗi

| Anti-pattern | Vấn đề | Thay bằng |
|---|---|---|
| Thêm ACAO `*` vào gateway trong khi Spring đã có ACAO | Duplicate và credentials incompatibility | Một owner; bỏ append |
| Gộp nhiều origins bằng dấu phẩy trong một ACAO | Không hợp lệ theo CORS | Server chọn một origin phù hợp mỗi request |
| `allowedOrigins("*")` cho cookie-authenticated API | Wildcard sai với credentials và mở policy | Exact origin allowlist |
| `allowedOriginPatterns("*")` với credentials | Chấp nhận quá rộng các nguồn đọc dữ liệu | Origin quản lý chặt, review trust boundary |
| Reflect mọi Origin từ request | Bỏ kiểm soát nguồn | Kiểm tra Origin trong allowlist server |
| Chuyển `credentials: "include"` thành `omit` để hết lỗi | Làm mất authentication và có thể che nguồn lỗi | Sửa ACAO/ACAC khi cần cookie |
| Xóa `Vary: Origin` để giảm header duplication | Cache có thể phát ACAO sai origin | Giữ Vary/cache key đúng |
| Chỉnh only OPTIONS response | Actual response vẫn có thể sai | Test OPTIONS + GET/POST/4xx |
| Thêm ACAO trong mọi `@ControllerAdvice` | Dễ phát header trùng/ghi đè | CORS owner xử lý response paths |
| Tắt Spring Security/CSRF để POST trả 200 | Mất hàng rào bảo mật HTTP | Giữ auth/CSRF, sửa CORS riêng |
| Bật CORS wildcard trên tất cả routes/admin | Mở trust boundary không cần thiết | Policy per route/role of frontend |
| Coi ACAO là danh sách và parse tại frontend | Browser vẫn thực thi CORS riêng | Sửa server response |
| Dùng trình duyệt với web security bị vô hiệu | Test không còn phản ánh người dùng thật | Browser mặc định, HTTPS và valid certificates |
| Dùng `curl -k` rồi kết luận CORS đã đúng | Bỏ TLS validation, không test browser | Sửa TLS, dùng browser E2E |
| Retry POST ngay khi thấy CORS error | POST có thể đã thành công ở server | Xác minh trạng thái, idempotency |
| Lưu cookie/token vào log để debug | Rò credentials | Flags, request IDs, header names |

**Khuyến nghị bảo vệ:** kiểm soát CORS là một trong nhiều lớp. CORS không thay thế CSRF, authentication, authorization, HSTS, CSP, security headers hay HTTP firewall. Một origin được phép đọc response không có nghĩa người dùng tại origin đó được phép thực hiện mọi thao tác.

## 42. Bài thực hành tổng hợp: sửa lỗi ACAO trùng trong ứng dụng Spring

**Bối cảnh:** một Spring Boot app giả lập có:

~~~text
Frontend 1: https://app.example.test
Frontend 2: https://staging.app.example.test
Frontend sai: https://untrusted.example.test
API: https://api.example.test
Gateway: thêm/ghi đè CORS headers theo rule kiểm thử
~~~

Ứng dụng có `GET /api/public/ping` (public JSON) và `POST /api/profile` (user authenticated, CSRF protected). Các hostname/HTTPS certs phải được cấu hình trong môi trường do nhóm quản lý; ví dụ không dựa vào dịch vụ thật.

### Nhiệm vụ theo thứ tự

1. Tạo endpoint public ping và profile lab không thay dữ liệu thật. Cấu hình Servlet `CorsConfigurationSource` cho **hai Origin được duyệt**, không cho Origin thứ ba.
2. Kiểm tra bằng curl preflight từ `app.example.test`, gửi đủ Origin/ACR-Method/ACR-Headers. Ghi số lượng ACAO và exact value.
3. Viết MockMvc test ACAO chỉ một giá trị và bằng request Origin; thêm negative cases khác scheme/port, Origin không cho phép.
4. Kiểm tra actual GET public qua browser: status/body đọc được khi Origin hợp lệ.
5. Thêm **có chủ đích trong lab** một gateway rule append ACAO `*` trên response. So origin response (một ACAO) và public response (hai ACAO); quan sát lỗi browser.
6. Bỏ gateway rule duplicate, giữ Spring làm CORS owner; chạy lại cùng test.
7. Đổi frontend sang staging origin nhưng giữ policy chỉ production trong một biến thể lab. Quan sát ACAO mismatch/403; cập nhật allowlist staging **sau khi xác nhận origin hợp lệ**.
8. Thử frontend untrusted; xác nhận browser không đọc được response ngay cả sau khi sửa.
9. Tạo biến thể credentialed fetch, thử ACAO wildcard + `Access-Control-Allow-Credentials: true` để quan sát lỗi; sửa thành exact origin, giữ cookies/CSRF theo thiết kế.
10. Test OPTIONS thành công nhưng actual response có ACAO trùng do một gateway response filter chỉ chạy trên POST. Chứng minh POST đã gửi và không tự retry.
11. Tạo 401 thiếu authentication và 403 thiếu CSRF; xác nhận response error có CORS đúng nhưng vẫn giữ status bảo mật.
12. Chạy cùng bài trên **Reactive/WebFlux** với reactive CORS source, WebTestClient tests và kiểm tra `CorsWebFilter`/`SecurityWebFilterChain`.
13. Thử cache một response theo Origin A rồi request từ Origin B; kiểm tra `Vary`/cache key và xác minh không lộ dữ liệu.
14. Lập bảng so sánh origin Spring/public: Origin, ACAO values, ACAC, Vary, status, CORS owner, actual request sent?, browser outcome, root cause và fix.

### Kết quả kỳ vọng

| Ca | Header server đúng? | Kết quả browser dự kiến |
|---|---|---|
| Frontend hợp lệ, ACAO một origin đúng | Có | JS đọc được response nếu điều kiện khác đúng |
| Frontend hợp lệ, hai ACAO | Không | CORS rejected |
| Frontend hợp lệ, ACAO = origin khác | Không | CORS rejected |
| Credentialed fetch, ACAO `*` | Không | CORS rejected |
| Origin sai bị CORS processor từ chối | Chính sách đúng | JS không được đọc response |
| OPTIONS hợp lệ, actual POST thiếu CSRF | CORS có thể đúng | POST 403 do CSRF, JS đọc status nếu CORS response đúng |
| OPTIONS đúng, actual response ACAO trùng | Sai ở actual path | Browser có thể chặn đọc response dù POST được xử lý |
| ACAO đúng nhưng CSP connect-src chặn | CORS chưa phải tầng lỗi | Browser có thể không gửi request |

### Câu hỏi tự đánh giá

1. Vì sao hai header ACAO giống hệt nhau vẫn không được coi là một giá trị ACAO hợp lệ?
2. ACAO chứa dấu phẩy khác với `Access-Control-Allow-Methods` chứa nhiều methods thế nào?
3. Origin phải được so theo những thành phần nào?
4. Tại sao `https://app.example.com/` không phải một origin string đúng để đặt trong allowedOrigins?
5. Vì sao browser có thể báo CORS dù API đã trả HTTP 200?
6. Vì sao CORS không thể dùng để ngăn POST có tác dụng phụ trong mọi trường hợp?
7. `credentials: "include"` thay đổi điều kiện hợp lệ của ACAO thế nào?
8. Vì sao wildcard ACAO không phù hợp với session-backed credentialed API?
9. Có thể khai báo nhiều allowedOrigins phía server mà vẫn chỉ phát một ACAO không? Vì sao?
10. Khi nào `@CrossOrigin` và `http.cors(...)` phối hợp hợp lệ, khi nào nên nghi duplicate?
11. Các nguồn tạo ACAO trùng phổ biến ở gateway/CDN/Spring là gì?
12. Vì sao chỉ test preflight OPTIONS chưa đủ để chứng minh toàn luồng CORS?
13. Nếu OPTIONS PASS nhưng POST báo CORS, phải quan sát request nào?
14. Nếu Spring origin trả một ACAO nhưng public trả hai, lớp nào cần được sửa?
15. `Vary: Origin` giúp giải quyết vấn đề gì với cache?
16. Vì sao nhiều `Vary` values có thể hợp lệ nhưng nhiều ACAO không hợp lệ?
17. `allowedOriginPatterns` có nguy cơ nào nếu áp dụng rộng cho các subdomains?
18. Vì sao `Origin: null` không nên được allow một cách mặc định?
19. Tại sao 401 thiếu ACAO có thể khiến frontend hiểu nhầm lỗi authentication thành lỗi mạng?
20. MockMvc/WebTestClient có thể kiểm tra ACAO duplicate bằng cách nào thay vì chỉ `getHeader()`?
21. Vì sao vẫn cần Playwright nếu MockMvc và WebTestClient đã PASS?
22. CORS khác CSRF và cookie SameSite ở đâu?
23. Nếu actual POST đã được thực thi nhưng browser chặn response, có nên retry ngay không?
24. Điều kiện để tuyên bố sửa CORS thành công là gì ngoài việc Origin hợp lệ được phép?

## 43. Ghi nhớ

**CORS header trùng và origin cấu hình không khớp là hai lỗi khác nhau.** Với request cross-origin, `Access-Control-Allow-Origin` phải là **một giá trị hợp lệ** phù hợp Origin mà browser gửi, không phải chuỗi liệt kê nhiều origins; khi có credentials, không dùng wildcard ACAO. Các giá trị `Vary` hoặc lists trong `Access-Control-Allow-Methods`/`Access-Control-Allow-Headers` có ngữ nghĩa khác, không thể dùng để hợp thức hóa ACAO lặp.

Trong **Servlet**, kiểm tra `CorsConfigurationSource`, `HttpSecurity.cors(...)`, `CorsFilter`, `SecurityFilterChain` và MVC metadata. Trong **Reactive/WebFlux**, dùng đúng reactive `CorsConfigurationSource`, `ServerHttpSecurity.cors(...)`, `CorsWebFilter` và `SecurityWebFilterChain`. Quan trọng hơn cả là **so headers tại Spring origin và public gateway/CDN**, xác định một CORS owner và test cả OPTIONS, actual response, 401/403/500 và các Origins không được phép.

Hãy giữ CSRF, authentication, authorization, cookie protections, CSP, HSTS, security headers và HTTP firewall khi sửa CORS. Trong `SPRING_SECURITY_HTTP_PROTECTION`, một bản sửa tốt vừa cho **Origin hợp lệ đọc response đúng cách**, vừa bảo đảm **Origin không được phép vẫn bị từ chối** và không có header writer thứ hai vô tình mở rộng quyền.
