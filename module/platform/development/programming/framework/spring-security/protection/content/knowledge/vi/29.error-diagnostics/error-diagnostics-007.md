# Preflight bị chặn trước khi xử lý CORS

> **Chương:** Chẩn đoán lỗi  
> **Mô-đun:** `SPRING_SECURITY_HTTP_PROTECTION` — áp dụng các lớp phòng vệ HTTP và trình duyệt trong Spring Security, từ CSRF, CORS, security headers, CSP, HSTS đến HTTP firewall và bảo vệ session. Người học cấu hình cho Servlet lẫn Reactive, kiểm thử các kịch bản tấn công web và chẩn đoán xung đột bảo mật khi triển khai.

## 1. Hiện tượng: OPTIONS nhận 401, 403 hoặc redirect trước khi POST được gửi

Một SPA phục vụ tại `https://app.example.com` gửi yêu cầu thay đổi hồ sơ đến Spring Boot API tại `https://api.example.com`:

~~~javascript
await fetch("https://api.example.com/api/profile", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": csrfToken
  },
  body: JSON.stringify({displayName: "Alice"})
});
~~~

Trước POST, browser có thể tự động phát **CORS preflight**:

~~~http
OPTIONS /api/profile HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Nhưng server trả:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
~~~

Hoặc:

~~~http
HTTP/1.1 302 Found
Location: /login
~~~

Hoặc gateway/WAF chặn `OPTIONS` trước ứng dụng. Browser không nhận được một response preflight hợp lệ, nên **không gửi POST thực**. Console thường chỉ hiển thị lỗi CORS mơ hồ, khiến nhóm phát triển sửa nhầm CSRF token, role hoặc controller của POST.

Trọng tâm bài này là một câu hỏi chính xác:

**Preflight bị từ chối ở đâu trong đường đi HTTP, và yêu cầu có tới được bộ xử lý CORS dự kiến chưa?**

### Kết quả cần đạt

Sau bài này, người học có thể:

1. Nhận diện CORS preflight và phân biệt nó với `OPTIONS` nghiệp vụ.
2. Truy vết request từ browser qua CDN/WAF/reverse proxy, servlet container/HTTP server, Spring Security và CORS processor.
3. Phân biệt **chặn trước CORS** với **CORS đã chạy nhưng từ chối Origin/method/header**.
4. Chẩn đoán 401 Basic/Bearer, 302 login, 403, 404/405, WAF, HTTP firewall và security-chain mismatch.
5. Cấu hình CORS đúng vị trí cho **Spring Security Servlet** và **Reactive/WebFlux**, giữ authentication, CSRF và browser protections.
6. Kiểm tra bằng DevTools, curl, MockMvc, WebTestClient và browser E2E.

## 2. Preflight là gì, và vì sao OPTIONS thường không mang cookie phiên?

CORS (*Cross-Origin Resource Sharing*) là cơ chế browser phối hợp với server để quyết định JavaScript từ một **origin** có thể đọc response từ origin khác hay không. Origin được xác định bởi **scheme + host + port**.

Ví dụ:

| Nguồn trang | Đích API | Quan hệ |
|---|---|---|
| `https://app.example.com` | `https://api.example.com` | Cross-origin do hostname khác |
| `https://app.example.com` | `https://app.example.com:8443` | Cross-origin do port khác |
| `https://app.example.com` | `http://app.example.com` | Cross-origin do scheme khác |
| `https://app.example.com` | `https://app.example.com` | Same-origin |

Khi browser sắp gửi một số loại cross-origin request không thuộc nhóm CORS-safelisted, nó thực hiện một **preflight** để hỏi server có cho phép method và request headers dự kiến không.

Ví dụ POST `Content-Type: application/json` và header custom `X-CSRF-TOKEN` thường kích hoạt preflight; GET đơn giản không có custom headers có thể **không có preflight**.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant A as Spring API
    B->>A: OPTIONS /api/profile + Origin + ACR-Method + ACR-Headers
    A-->>B: 200/204 + Access-Control-Allow-*
    Note over B: Browser kiểm tra CORS policy
    B->>A: POST /api/profile + Cookie/Auth/CSRF nếu được phép
    A-->>B: 200/204/401/403... + CORS headers phù hợp
~~~

**Preflight không phải POST.** Nó chỉ xin phép trước khi gửi request thật; preflight thành công **không xác thực người dùng**, không cấp quyền sửa hồ sơ và không làm CSRF token của POST hợp lệ.

### Browser preflight được gửi không có credentials

Về nguyên tắc, browser gửi CORS preflight **không kèm cookie hoặc credential như request thật**. Do đó các rule kiểu:

~~~text
OPTIONS /api/** phải có JSESSIONID
OPTIONS /api/** phải có Authorization: Bearer ...
~~~

sẽ dễ chặn browser trước khi nó kịp gửi POST có credential.

**Không nhầm:** request POST thật có thể mang cookie (nếu cookie policy và `fetch.credentials` cho phép) hoặc Bearer header do JavaScript chủ động đặt; preflight thường chỉ gửi **tên header dự kiến**, không gửi secret đó.

~~~http
Access-Control-Request-Headers: authorization,content-type,x-csrf-token
~~~

Header trên có nghĩa browser hỏi “có được gửi các header tên này không?”, không phải preflight đã mang một Bearer token.

## 3. Một response preflight hợp lệ cần trả lời đúng câu hỏi của browser

Response minh họa khi API đồng ý với nguồn gọi cụ thể:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET,POST,PUT,OPTIONS
Access-Control-Allow-Headers: content-type,x-csrf-token
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 600
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
~~~

Server cũng có thể dùng HTTP 200 thành công thay vì 204. **Status 200/204 tự nó không đủ:** browser còn kiểm tra các CORS headers và giá trị origin/method/header. Ngược lại, một response `401`/`403` hoặc redirect **không phải preflight chấp thuận**.

| Header | Vai trò |
|---|---|
| `Access-Control-Allow-Origin` | Origin nào được phép; với credentials không dùng wildcard `*` |
| `Access-Control-Allow-Methods` | HTTP methods mà server cho phép trong context CORS |
| `Access-Control-Allow-Headers` | Request headers không safelisted mà browser được phép gửi |
| `Access-Control-Allow-Credentials` | Cho browser đọc credentialed response khi policy cho phép |
| `Access-Control-Max-Age` | Cho phép browser cache kết quả preflight trong giới hạn riêng |
| `Vary` | Giúp HTTP caches không nhầm response theo Origin/method/requested headers |

Lưu ý `Access-Control-Allow-Credentials: true` không bắt browser gửi cookie nếu cookie bị `SameSite`/`Secure`/`Domain`/`Path` hoặc privacy policy chặn.

### Một ví dụ CORS **đã xử lý nhưng từ chối**

Nếu browser gửi:

~~~http
Origin: https://unknown.example.net
Access-Control-Request-Method: POST
~~~

và server chỉ cho `https://app.example.com`, một CORS processor có thể trả `403 Invalid CORS request`. **Đây là CORS từ chối hợp lệ** do Origin không được phép, khác với tình huống OPTIONS bị Authentication filter chặn **trước CORS**.

Không nới allowlist chỉ vì thấy 403: cần xác minh Origin, method hoặc header nào không hợp lệ.

## 4. Đường đi của preflight: điểm từ chối có thể ở nhiều tầng

~~~mermaid
flowchart TD
    A[Browser phát OPTIONS preflight] --> B{DNS/TLS/mạng/CDN/WAF}
    B -- Bị chặn --> C[Không tới Spring API]
    B -- Qua --> D{Reverse proxy / gateway / ingress}
    D -- 301/302/403/404/405 --> E[Response trước backend]
    D -- Forward --> F{HTTP server / servlet container / WebFlux Netty}
    F -- Từ chối --> G[HTTP server-level response]
    F -- Qua --> H{Security proxy / HTTP firewall / chain selection}
    H -- Bị từ chối sớm --> I[Không tới CORS processor dự kiến]
    H -- Qua --> J{CORS processor của đúng chain/stack}
    J -- Origin/method/header sai --> K[CORS rejection]
    J -- Cho phép --> L[Preflight hợp lệ; không cần controller xử lý POST]
    L --> M[Browser có thể gửi actual request]
~~~

### Thứ tự chẩn đoán có ý nghĩa

- **Không có log tại Spring** có thể do gateway, WAF, DNS/TLS/browser; không lập tức suy Spring CORS sai.
- **Có Spring Security log nhưng không có log CORS** gợi ý security chain/HTTP firewall/filter khác xử lý trước; cần xác minh log configuration.
- **Có log CORS ghi rejected origin/method/header** cho thấy CORS đã chạy nhưng policy không cho phép.
- **Có 200/204 OPTIONS nhưng browser vẫn từ chối** thường là response thiếu/sai CORS headers hoặc request thực có CORS response sai.

Không kết luận nguyên nhân chỉ bằng status. Một gateway, Spring Security entry point, CORS processor hoặc custom error handler đều có thể trả `403` với ý nghĩa khác nhau.

## 5. Định danh đúng preflight, không phải mọi OPTIONS đều là preflight

Một CORS preflight browser thực có các header đặc trưng:

~~~http
OPTIONS /api/items HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: DELETE
Access-Control-Request-Headers: authorization,x-csrf-token
~~~

Trong điều kiện thông thường, dấu hiệu quan trọng là **method OPTIONS cùng `Origin` và `Access-Control-Request-Method`**. Header `Access-Control-Request-Headers` chỉ xuất hiện khi cần xin phép những request headers cụ thể.

Một request:

~~~http
OPTIONS /api/items HTTP/1.1
Host: api.example.com
~~~

không có các header CORS nói trên có thể chỉ là OPTIONS do HTTP client hoặc hệ thống gọi, không phải browser preflight. Khi test, dùng **đúng bộ header mà browser gửi** để không nhầm một response 401 từ OPTIONS thường với preflight CORS.

### Không nhầm Origin và Referer

`Origin` là dữ liệu CORS processor so sánh với allowlist. `Referer` có mục đích khác và không nên được dùng thay `Origin` trong cấu hình CORS.

### CORS-safelisted request khác “request an toàn”

Tên “simple request” hoặc CORS-safelisted chỉ nói request có thể **không cần preflight**; nó không có nghĩa request an toàn về CSRF hoặc không thay đổi dữ liệu.

Ví dụ một HTML form POST `application/x-www-form-urlencoded` từ site khác có thể phát request mà không qua preflight, nhưng **vẫn cần CSRF protection** trên backend nếu dùng cookie credentials. Vì thế không dựa vào preflight như cơ chế chống CSRF.

## 6. Những mã HTTP thường thấy khi preflight bị chặn sớm

| Phản hồi cho OPTIONS | Giả thuyết thường gặp | Bằng chứng phân biệt |
|---|---|---|
| `401` + `WWW-Authenticate: Basic` | HTTP Basic yêu cầu xác thực trước CORS | Security entry point + chain logs |
| `401` + Bearer challenge | Resource server filter đòi Bearer trước CORS | OAuth2 resource server chain/entry point |
| `302` `Location: /login` | Form-login entry point hoặc proxy SSO redirect | Nguồn response + chain/route |
| `403` với `Invalid CORS request` | CORS processor đã chạy và từ chối | Check Origin/method/headers |
| `403` với WAF/gateway page | Security layer trước app | CDN/WAF request ID, thiếu app log |
| `403` do authorization | OPTIONS được xử lý như API request cần quyền | Authorization logs, CORS order |
| `404` | Gateway không route OPTIONS, rewrite sai, controller fallback | Proxy route, app dispatch trace |
| `405 Method Not Allowed` | Proxy/controller/filter không chấp nhận OPTIONS như kỳ vọng | Allow header, nơi tạo status |
| `400` + `RequestRejectedException` (Servlet) | HTTP firewall từ chối request chưa tới CORS filter | URI/headers/method, firewall logs |
| `200/204` không có CORS headers | Có response nhưng browser không được phép tiếp tục | So `Access-Control-Allow-*` |
| Network timeout/TLS error | Browser không nhận response preflight | DNS/TLS/firewall/connectivity |

**302, 401, 403 và 405 không phải tất cả đều “lỗi CORS policy”.** Phân biệt nơi sinh response để sửa đúng tầng.

## 7. Lỗi thường gặp: security filter chạy trước CORS

Spring Security cần cho CORS processing diễn ra **trước authentication** đối với preflight. Ví dụ một application chỉ có:

~~~java
http.authorizeHttpRequests(auth -> auth
    .anyRequest().authenticated()
);
http.httpBasic(Customizer.withDefaults());
~~~

Nếu chưa tích hợp CORS ở đúng vị trí, `OPTIONS /api/items` có thể được xem là request cần authentication, bị Basic entry point trả 401 vì không có credentials. Browser ngừng tại preflight.

### Thêm permitAll cho OPTIONS đã đủ chưa?

Một cách sửa chưa đủ:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()
    .anyRequest().authenticated()
);
~~~

Authorization có thể không chặn OPTIONS nữa, nhưng **không bảo đảm response có `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods` và `Access-Control-Allow-Headers`**. Browser vẫn từ chối nếu không có CORS processor hợp lệ.

Ngược lại, khi CORS được xử lý sớm và chấp nhận preflight, request thường được hoàn tất ở CORS filter, không cần controller phải có phương thức `@RequestMapping(method=OPTIONS)`.

**Cách đúng:** cấu hình CORS allowlist hợp lệ và tích hợp **đúng thứ tự** với security chain, không chỉ mở authorization cho OPTIONS.

## 8. Các tình huống bị chặn trước CORS không thuộc Spring Security

### CDN/WAF chặn HTTP OPTIONS

Một rule an ninh ở edge chỉ cho GET/POST, hoặc coi OPTIONS là method bất thường, có thể trả 403 trước khi request tới Spring.

**Chứng cứ:** browser Network có response edge, trace ID ở WAF, không có access log tương ứng trong origin. Cần sửa route/method policy tại edge theo đúng API surface, không nới Spring Security authorization nếu request chưa tới app.

### Reverse proxy rewrite path sai

~~~text
Browser: OPTIONS /gateway/api/items
Proxy:   /gateway/api/* -> upstream /api/* cho GET/POST
         nhưng OPTIONS không dùng cùng rewrite/route
~~~

OPTIONS có thể nhận 404/405 hoặc bị redirect đến login của gateway. Sửa proxy để OPTIONS preflight được forward tới **đúng CORS processor** hoặc được xử lý bởi **CORS policy tương đương có kiểm soát** tại edge.

### Redirect HTTP → HTTPS hoặc redirect trailing slash

Browser phát preflight tới `http://api.example.com/api/items` và nhận redirect. Tùy browser/flow, preflight redirect có thể thất bại hoặc hành vi không như mong đợi; không nên xây workflow phụ thuộc vào redirect của preflight.

**Cách sửa:** frontend gọi **đúng HTTPS final URL và canonical path ngay từ đầu**, proxy dùng route chuẩn; giữ HTTPS/HSTS thay vì tắt chúng.

### Servlet container hoặc HTTP server trả lỗi trước filter

Request URI/header quá dài, không hợp lệ hoặc chứa ký tự bị HTTP parser/firewall từ chối có thể không tới CORS filter. Khi đó cấu hình `allowedOrigins` không giải quyết nguyên nhân. Cần trace request thực nhận và lớp parser/firewall.

## 9. Spring Security Servlet: vị trí của CorsFilter và FilterChainProxy

Với Servlet stack, đường đi điển hình:

~~~text
HTTP request
  -> Reverse proxy / servlet container
  -> DelegatingFilterProxy / FilterChainProxy của Spring Security
  -> HttpFirewall kiểm tra request theo cấu hình
  -> Chọn SecurityFilterChain phù hợp (first-match)
  -> CorsFilter được Spring Security tích hợp đúng thứ tự (nếu bật)
  -> Các filter authentication, CSRF, authorization...
  -> Controller/handler (đối với actual request)
~~~

Spring Security tích hợp CORS qua `http.cors(...)` và sử dụng `CorsConfigurationSource` hoặc cấu hình MVC tương thích để áp dụng policy. Khi preflight hợp lệ được `CorsFilter` xử lý, nó thường **trả response trực tiếp**, không đi qua authentication filters phía sau.

**Hai điểm dễ bỏ sót:**

1. `CorsFilter` bên trong security chain **không thể xử lý request đã bị reverse proxy hoặc `HttpFirewall` từ chối trước khi chain chạy**.
2. Ứng dụng có **nhiều `SecurityFilterChain`**: route preflight phải vào đúng chain có CORS configuration. Nếu một chain fallback match-all đứng trước hoặc matcher chỉ chọn GET/POST, OPTIONS có thể đi nhầm chain.

Trên Servlet, không phải mọi `Filter` đều là thành phần của Spring Security chain. Một `CorsFilter` đăng ký ở servlet container trước `DelegatingFilterProxy` có thể xử lý CORS ở tầng khác; nếu vừa đăng ký filter global vừa gọi `http.cors(...)` mà không kiểm soát thứ tự và policy, có thể sinh cấu hình trùng/mâu thuẫn. Hãy biết rõ **ai sở hữu CORS** trong deployment.

## 10. Servlet: cấu hình CORS rõ ràng bằng CorsConfigurationSource

Ví dụ API tại `https://api.example.com` chỉ cho SPA `https://app.example.com`. Ứng dụng Servlet sử dụng Spring Security 6-style lambda DSL:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class ApiSecurityConfig {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(List.of("https://app.example.com"));
        config.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE"));
        config.setAllowedHeaders(List.of(
            "Content-Type", "Authorization", "X-CSRF-TOKEN"
        ));
        config.setAllowCredentials(true);
        config.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.cors(Customizer.withDefaults());
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/public/**").permitAll()
            .requestMatchers("/api/**").authenticated()
            .anyRequest().denyAll()
        );
        http.httpBasic(Customizer.withDefaults());
        // Giữ CSRF protection để kiểm thử riêng cho cookie-authenticated
        // hoặc browser HTTP Basic workflows.
        http.csrf(Customizer.withDefaults());
        return http.build();
    }
}
~~~

**Giải thích những dòng quan trọng:**

- `config.setAllowedOrigins(...)` dùng origin **chính xác**, gồm scheme/host và port nếu không phải mặc định. Không lấy `Origin` của request rồi phản chiếu lại mà không kiểm tra.
- `setAllowedMethods(...)` phải cho method của **actual request**. Trong preflight `Access-Control-Request-Method: POST`, method được xin phép là `POST`; không nhất thiết phải liệt kê `OPTIONS` riêng chỉ để CORS processor chấp nhận preflight, dù gateway có thể cần cho OPTIONS ở tầng HTTP.
- `setAllowedHeaders(...)` cho phép tên header không safelisted mà browser muốn gửi, gồm header `Authorization` nếu API dùng Bearer/Basic từ JavaScript, hoặc `X-CSRF-TOKEN` nếu POST dùng CSRF.
- `setAllowCredentials(true)` chỉ dùng khi kiến trúc cần browser gửi/đọc credentialed cross-origin responses; không cần thiết cho mọi API công khai.
- `http.cors(...)` tích hợp CORS với security chain để preflight được xử lý trước bước authentication/authorization phù hợp.
- `anyRequest().denyAll()` bảo vệ các route không được khai báo trong **chain này**; nếu có nhiều chains, phạm vi matcher phải được xét riêng.

### Đừng tự động dùng CSRF disable trong API

Ví dụ trên dùng Basic và có thể phục vụ browser tự gửi credentials, vì vậy **giữ CSRF** để tách lỗi CORS khỏi CSRF. Một API stateless chỉ dùng Bearer header được mã JavaScript chủ động gắn, không có cookie hay ambient credentials, có thể có chính sách CSRF khác sau khi đã review threat model. Không bật/tắt CSRF vì thấy OPTIONS 401.

### Kết quả mong đợi

Với một preflight hợp lệ:

~~~http
OPTIONS /api/profile HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Spring CORS processor có thể trả HTTP 200 và các header phù hợp. **POST tiếp theo vẫn có thể 401/403** nếu thiếu authentication, thiếu CSRF token hoặc thiếu quyền; đó là một vòng kiểm tra khác.

## 11. Servlet: dùng cấu hình Spring MVC CORS rồi quên tích hợp Security

Một controller hoặc MVC config có thể khai báo:

~~~java
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @CrossOrigin(origins = "https://app.example.com")
    @PostMapping("/api/profile")
    public void updateProfile() {
        // Chỉ minh họa route; production cần auth, input và CSRF.
    }
}
~~~

**Vấn đề:** `@CrossOrigin` thể hiện ý định CORS ở tầng Spring MVC. Nếu Spring Security đứng trước MVC nhưng chưa được tích hợp CORS phù hợp, `OPTIONS` có thể bị auth filter chặn **trước khi MVC biết về CORS annotation**.

Trong ứng dụng có Spring MVC và cấu hình CORS thích hợp, `http.cors(Customizer.withDefaults())` có thể giúp Spring Security dùng thông tin MVC để xử lý sớm. Nhưng với nhiều bean `CorsConfigurationSource`, nhiều security chains hoặc gateway xử lý CORS, không nên đoán Spring chọn đúng cấu hình; cần xác nhận route thực, CORS headers và filter order.

### Dấu hiệu cấu hình chỉ ở controller

~~~text
GET /api/profile từ curl có thể thành công với credentials
OPTIONS /api/profile từ browser nhận 401 Basic
POST thật không được browser gửi
~~~

Ở trường hợp này sửa `@PostMapping` hoặc quyền controller chưa chạm đúng nguồn lỗi. Hãy kiểm tra `CorsFilter` có chạy trước authentication trong chain mà OPTIONS chọn.

## 12. Servlet nhiều SecurityFilterChain: OPTIONS có thể đi nhầm chain

Ứng dụng gồm:

~~~text
API chain: /api/** -> Basic/Bearer, CORS API
Web chain: còn lại -> Form login
~~~

Một cấu hình **đúng nguyên tắc thứ tự**:

~~~java
import org.springframework.core.annotation.Order;

@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**");
    http.cors(Customizer.withDefaults());
    http.authorizeHttpRequests(a -> a
        .requestMatchers("/api/public/**").permitAll()
        .anyRequest().authenticated()
    );
    http.httpBasic(Customizer.withDefaults());
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain webFallback(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(a -> a
        .requestMatchers("/login").permitAll()
        .anyRequest().authenticated()
    );
    http.formLogin(Customizer.withDefaults());
    return http.build();
}
~~~

Giả định ứng dụng đã có `CorsConfigurationSource` cho `/api/**` và các bean cần thiết. `securityMatcher("/api/**")` phải áp dụng cho **cả OPTIONS và actual methods** khi cần; nếu dùng matcher tùy chỉnh chỉ match `POST /api/**`, preflight `OPTIONS` có thể rơi vào fallback rồi nhận 302 tới login.

### Bẫy chain catch-all đứng trước

Nếu fallback không có `securityMatcher` và được đặt `@Order(1)`, nó có thể match mọi request trước API chain. Khi đó `OPTIONS /api/profile` bị form login redirect, dù API chain có CORS config đúng nhưng **chưa bao giờ được chọn**.

Điều tra theo thứ tự:

1. Liệt kê những `SecurityFilterChain` đã tạo và `@Order`.
2. Xác định matcher của từng chain trên **OPTIONS**, không chỉ POST.
3. Xem first-match chain nào được chọn.
4. Kiểm tra chain đó có `CorsFilter` và policy cho đúng path hay không.
5. Chỉ sau khi preflight thành công mới xem authentication/CSRF của POST.

### Route không khớp CORS policy

Một CORS source đăng ký `/api/**` không áp dụng cho `/gateway/api/**` nếu path mà framework nhận không tương ứng. Reverse proxy và servlet context path có thể thay phạm vi matcher. Hãy dùng **path Spring thật sự thấy**, không đoán từ địa chỉ browser hiển thị.

## 13. HTTP firewall từ chối OPTIONS trước CorsFilter

Trong Servlet, `FilterChainProxy` có thể sử dụng `HttpFirewall` (thường `StrictHttpFirewall`) để kiểm tra hình dạng HTTP request trước khi các filter trong selected chain chạy.

Ví dụ request bất thường:

~~~http
OPTIONS /api;flag=1/items HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: DELETE
~~~

Tùy cấu hình/parser, request có thể bị từ chối với `RequestRejectedException` **trước `CorsFilter`**. HTTP status có thể là 400 hoặc giá trị do rejection handler/container quy định, không phải mã cứng cho mọi ứng dụng.

Hãy xác minh:

- URL thực tế có dấu `;`, backslash, encoded slash hoặc ký tự bị chặn không?
- Reverse proxy đã normalize/rewrite khác Spring chưa?
- Request bị container từ chối trước hay `StrictHttpFirewall` từ chối?
- `RequestRejectedHandler` nào đang xử lý exception?

**Đừng sửa bằng cách tắt StrictHttpFirewall toàn bộ** hoặc allow mọi ký tự nguy hiểm chỉ để OPTIONS chạy. Điều chỉnh URL client/canonical route hoặc đưa thay đổi firewall qua security review và regression tests.

### HTTP method bất thường

Một firewall có thể giới hạn danh sách HTTP methods; OPTIONS chuẩn thường được chấp nhận, nhưng custom allowlist có thể loại nó. Nếu đã cấu hình chỉ GET/POST trên gateway hoặc firewall, OPTIONS sẽ không tới CORS. Kiểm tra chính xác allowlist được triển khai ở tầng nào, rồi cho **OPTIONS chuẩn** qua đúng path cần CORS.

## 14. CSRF và preflight: hai khái niệm không nên chữa lẫn

Spring Security mặc định thường **không yêu cầu CSRF token cho OPTIONS**, vì đó là phương thức safe theo CSRF request matcher mặc định. Nếu một OPTIONS nhận 403, đừng kết luận chắc chắn thiếu CSRF token.

Các trường hợp:

| Quan sát | Cách hiểu chính xác |
|---|---|
| `OPTIONS` 401 Basic | Có thể authentication xử lý preflight trước CORS |
| `OPTIONS` 302 /login | Có thể form-login entry point xử lý trước CORS |
| `OPTIONS` 403 “Invalid CORS request” | CORS processor đã chạy và từ chối |
| `OPTIONS` 403 do custom CSRF matcher | Có thể custom matcher đã đưa OPTIONS vào diện CSRF; cần xem code |
| `OPTIONS` 200/204, POST 403 | Preflight thành công; POST bị CSRF, authorization hoặc tầng khác |
| Browser không gửi POST | Không có CSRF validation của POST để chẩn đoán |

**Không tắt CSRF để làm preflight thành công.** Hãy sửa CORS filtering/order và xác định thực tế request nào cần token. Sau khi preflight thành công, POST có thể vẫn phải gửi session cookie và CSRF token hợp lệ.

### Không biến preflight thành request có authentication

Không đặt requirement `Authorization` hay session cookie lên preflight chỉ để “xác minh caller”. Browser tự phát preflight và thường không mang credentials; server có thể kiểm tra Origin/method/headers được phép, rồi actual request vẫn qua authentication, authorization, CSRF và kiểm tra nghiệp vụ.

## 15. Reactive/WebFlux: CORS processor và SecurityWebFilterChain

Trong Reactive stack, Spring Security sử dụng `SecurityWebFilterChain` và `WebFilterChainProxy`, không dùng Servlet `CorsFilter`/`FilterChainProxy`/`HttpServletRequest`.

Khái niệm đường đi:

~~~text
Browser OPTIONS
  -> CDN/WAF/reverse proxy/Netty HTTP server
  -> CORS WebFilter hoặc CORS processing tích hợp ở vị trí phù hợp
  -> Reactive security filters (authentication/authorization)
  -> Handler mapping/WebFlux controller đối với actual requests
~~~

Thứ tự thực tế phụ thuộc cách đăng ký `CorsWebFilter` hoặc cấu hình `ServerHttpSecurity.cors(...)`, server/framework version và các `WebFilter` khác. Mục tiêu vẫn giống Servlet: **preflight hợp lệ phải được nhận biết và xử lý trước khi authentication bắt request phải có session/Bearer token**.

### Reactive CORS configuration source

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
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(List.of("https://app.example.com"));
        config.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE"));
        config.setAllowedHeaders(List.of(
            "Authorization", "Content-Type", "X-CSRF-TOKEN"
        ));
        config.setAllowCredentials(true);
        config.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }
}
~~~

### WebFlux security chain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.reactive.CorsConfigurationSource;

@Configuration
public class ReactiveApiSecurity {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            CorsConfigurationSource source) {
        http.cors(cors -> cors.configurationSource(source));
        http.authorizeExchange(auth -> auth
            .pathMatchers("/api/public/**").permitAll()
            .pathMatchers("/api/**").authenticated()
            .anyExchange().denyAll()
        );
        http.httpBasic(Customizer.withDefaults());
        http.csrf(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Ví dụ này thể hiện cách khai báo một source CORS cho **Reactive** và áp dụng vào security chain; đối chiếu API với phiên bản Spring Security WebFlux đang sử dụng. Nếu cấu hình của dự án dùng `CorsWebFilter` riêng, hãy kiểm soát thứ tự/nguồn policy để tránh xử lý CORS trùng hoặc mâu thuẫn. **Không dùng Servlet `UrlBasedCorsConfigurationSource` thay cho bản `org.springframework.web.cors.reactive`**.

### Nhiều Reactive chains

Giống Servlet, mỗi `SecurityWebFilterChain` có matcher và thứ tự `@Order`. Nếu preflight chỉ match một fallback chain không tích hợp CORS, nó có thể trả 302/401. Hãy kiểm tra **request OPTIONS** được chọn bởi `ServerWebExchangeMatcher` nào, không suy từ POST.

## 16. CorsWebFilter toàn cục và CORS tích hợp với Security: chọn người chịu trách nhiệm

Trong WebFlux, có thể dùng `CorsWebFilter`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.web.cors.reactive.CorsWebFilter;
import org.springframework.web.cors.reactive.CorsConfigurationSource;

@Bean
CorsWebFilter corsWebFilter(CorsConfigurationSource source) {
    return new CorsWebFilter(source);
}
~~~

**Không mặc định thêm bean này vào dự án đã tích hợp CORS bằng `ServerHttpSecurity.cors(...)` rồi kỳ vọng cả hai tự phối hợp.** Hai bộ xử lý CORS với policy/order khác nhau có thể tạo response trùng headers hoặc cùng nhau từ chối một request.

Khi chọn cấu trúc, xác minh:

1. Có `CorsWebFilter` toàn cục và nó chạy **trước security filters** không?
2. Security chain có cấu hình CORS riêng không?
3. Spring WebFlux handler mapping có một CORS policy khác không?
4. Gateway có xử lý/ghi đè CORS headers không?
5. Actual response có CORS headers phù hợp sau preflight không?

Đặt **một nơi sở hữu policy rõ ràng**, kiểm thử OPTIONS và actual response trên public path. Nếu có nhiều tầng cùng tham gia, phải có hợp đồng rõ ràng thay vì dựa vào thứ tự không được kiểm chứng.

## 17. Preflight Private Network Access: một biến thể phải nhận diện đúng

Trong một số môi trường/browser, yêu cầu từ một website công khai tới địa chỉ mạng riêng hoặc local có thể phát sinh kiểm tra **Private Network Access (PNA)** liên quan đến preflight và header riêng:

~~~http
Access-Control-Request-Private-Network: true
~~~

Một số flow có thể cần response thích hợp theo chính sách/browser hỗ trợ, ví dụ `Access-Control-Allow-Private-Network`. **Hành vi PNA chịu ảnh hưởng của phiên bản browser và chính sách triển khai**, không mặc định mọi OPTIONS đều dùng header này.

Khi preflight thất bại **chỉ với thiết bị LAN/local API**, hãy kiểm tra request thật có header PNA không, browser console/blocked reason, HTTPS và trust boundary. Không tự cho mọi website public gọi private network chỉ để tránh một thông báo lỗi.

PNA **không thay thế** CORS, CSRF, authentication hoặc kiểm soát truy cập mạng. Nếu ứng dụng truy cập thiết bị nội bộ, security review phải xem origin được phép, danh tính thiết bị và bề mặt tấn công.

## 18. DevTools: xem OPTIONS và request thật riêng biệt

Khi frontend báo lỗi CORS, mở **DevTools → Network** và bật chế độ hiển thị các request liên quan. Một số browser có filter riêng cho preflight hoặc làm mờ/collapse nó; cần kiểm tra cấu hình Network và phiên bản browser.

### Tìm preflight gốc

Trong Network, chọn request `OPTIONS`, ghi:

| Dữ liệu | Ý nghĩa |
|---|---|
| Request URL, method, scheme, host, port | Đích và đường public thật của OPTIONS |
| `Origin` | Origin của trang đã kích hoạt request |
| `Access-Control-Request-Method` | HTTP method browser định gửi |
| `Access-Control-Request-Headers` | Những header không safelisted browser xin phép |
| Status, `Location`, `WWW-Authenticate` | Phân biệt redirect và auth challenge |
| `Access-Control-Allow-*` | Response có đáp ứng CORS policy không? |
| Response body/server banner/trace ID | Gợi ý gateway/WAF/Spring là nguồn response |
| Timing, remote address và redirect chain | Có tới đúng service, HTTP proxy không? |

### Tìm actual request

Tiếp đó xem **POST/PUT/DELETE thật có xuất hiện không**. Nếu không, **dừng việc chẩn đoán CSRF của POST**; hãy tìm tại sao preflight không được browser chấp thuận.

Nếu POST xuất hiện, xem response của POST và token/session/auth riêng. Một preflight thành công không đồng nghĩa actual response được JavaScript đọc: actual response còn phải có CORS headers phù hợp, đặc biệt khi có credentials.

### Các tình huống khiến “không thấy OPTIONS” là bình thường

- Request same-origin nên không cần CORS.
- Cross-origin request thuộc loại không cần preflight.
- Browser đã cache kết quả preflight hợp lệ theo `Access-Control-Max-Age`.
- Request bị CSP `connect-src`, mixed content, DNS/TLS hoặc browser extension chặn **trước khi gửi**.
- Service worker, DevTools filter hoặc cách browser hiển thị đã làm request khó thấy.

**Không mặc định “không có OPTIONS thì CORS bị tắt”.** Cần xác nhận request có cần preflight, browser đã gửi gì và có cache kết quả không.

## 19. Curl: tái hiện một preflight với các header chính xác

Các lệnh dưới đây là **ví dụ dành cho API lab/staging do bạn kiểm soát**, không yêu cầu chạy trong STEP 4.

~~~bash
curl -i -X OPTIONS 'https://api.example.com/api/profile' \
  -H 'Origin: https://app.example.com' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type,x-csrf-token'
~~~

So response:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET,POST,PUT,DELETE
Access-Control-Allow-Headers: content-type,x-csrf-token
Access-Control-Allow-Credentials: true
~~~

HTTP 200/204 và headers phù hợp là **bằng chứng server/edge chấp thuận một preflight giả lập**. Nó chưa xác minh browser đã gửi POST hay cookie/CSRF của POST hợp lệ.

### Không gửi cookie hoặc Bearer token để “làm OPTIONS hợp lệ”

Trong test preflight, **không cần**:

~~~http
Cookie: JSESSIONID=...
Authorization: Bearer ...
~~~

Vì browser preflight theo cơ chế CORS không mang credentials như actual request. Nếu OPTIONS chỉ thành công sau khi thêm Authorization bằng tay, cấu hình đó **chưa xử lý được browser preflight**.

### Không tự follow redirect

`curl -i -X OPTIONS` giúp thấy redirect `301/302/307/308` tại URL gốc. Tránh thêm `-L` khi đang định vị chỗ chặn, vì nó có thể che status/Location ban đầu và chuyển request sang endpoint khác.

### Ba đối chứng tối thiểu

**Nguồn hợp lệ:**

~~~bash
curl -i -X OPTIONS 'https://api.example.com/api/profile' \
  -H 'Origin: https://app.example.com' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type,x-csrf-token'
~~~

**Nguồn không hợp lệ:**

~~~bash
curl -i -X OPTIONS 'https://api.example.com/api/profile' \
  -H 'Origin: https://untrusted.example.net' \
  -H 'Access-Control-Request-Method: POST'
~~~

**Xin phép header không được hỗ trợ:**

~~~bash
curl -i -X OPTIONS 'https://api.example.com/api/profile' \
  -H 'Origin: https://app.example.com' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: x-internal-debug-secret'
~~~

Nếu CORS policy được cấu hình chặt, hai đối chứng sau **phải không được browser chấp thuận**. Một server có thể trả 403 hoặc response không có header cho phép; không ép mọi CORS implementation phải trả cùng HTTP status cho mọi lỗi.

**Giới hạn của curl:** curl không thực thi CORS như browser. Nó chỉ gửi và hiển thị HTTP; việc curl nhận 200 không có nghĩa JavaScript cross-origin đã được browser cấp quyền. Muốn xác thực browser behavior cần DevTools hoặc E2E.

## 20. Log: chứng minh CORS filter có chạy hay không

Trong môi trường dev/staging với logging policy phù hợp:

~~~properties
# Spring CORS processing, Servlet lẫn Reactive ở package liên quan.
logging.level.org.springframework.web.cors=DEBUG

# Spring Security: tìm security chain và auth failure.
logging.level.org.springframework.security=DEBUG

# Khi điều tra Servlet chain ordering, bật TRACE tạm thời:
logging.level.org.springframework.security.web.FilterChainProxy=TRACE

# Khi điều tra Reactive security proxy, bật TRACE tạm thời:
logging.level.org.springframework.security.web.server.WebFilterChainProxy=TRACE
~~~

Tên log cụ thể phụ thuộc framework version và cách cấu hình. **Không thấy một dòng log không đủ chứng minh filter chưa chạy**, vì mức log có thể chưa đúng. Nên kết hợp status, HTTP headers, trace ID, filter configuration và request path thực nhận.

### Bảng bằng chứng để kết luận điểm chặn

| Bằng chứng | Điều nó hỗ trợ |
|---|---|
| Edge/WAF log `OPTIONS ... blocked`; không có origin access log | Chặn trước Spring |
| Origin access log có OPTIONS, security entry point 401/302 | Authentication được gọi trước khi preflight được xử lý phù hợp |
| `RequestRejectedException` hoặc parser rejection | Firewall/container từ chối trước CORS filter của chain |
| CORS processor log “Invalid CORS request” | CORS đã chạy nhưng Origin/method/headers không hợp lệ |
| CORS headers hợp lệ trên OPTIONS, POST xuất hiện | Preflight thành công; điều tra actual request |
| OPTIONS hợp lệ qua origin nhưng 403 qua public hostname | Gateway/WAF/proxy/route config có khác biệt |

**Dữ liệu cần giữ:** request ID, timestamp, method/path/Origin, requested method/headers, tên chain, response status và nguồn trả response.

**Dữ liệu không nên ghi:** session cookies, JWT/Bearer credentials, CSRF token, password, body nghiệp vụ nhạy cảm hoặc header Authorization đầy đủ. Ở preflight chỉ nên ghi **tên headers được xin phép**, không log secret của actual request.

## 21. MockMvc: test preflight Servlet mà không gửi authentication

Giả sử Spring MVC application có `CorsConfigurationSource` và `SecurityFilterChain` như mục 10, cùng route `/api/profile` theo lab. Một test dùng Spring Security filters:

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(options("/api/profile")
        .header("Origin", "https://app.example.com")
        .header("Access-Control-Request-Method", "POST")
        .header(
            "Access-Control-Request-Headers",
            "content-type,x-csrf-token"
        ))
    .andExpect(status().isOk())
    .andExpect(header().string(
        "Access-Control-Allow-Origin", "https://app.example.com"
    ))
    .andExpect(header().string(
        "Access-Control-Allow-Methods", containsString("POST")
    ))
    .andExpect(header().string(
        "Access-Control-Allow-Headers", containsString("x-csrf-token")
    ))
    .andExpect(header().string(
        "Access-Control-Allow-Credentials", "true"
    ));
~~~

Test **không có `with(user(...))` hoặc Bearer token**. Nó chứng minh preflight hợp lệ không phải vượt qua authentication mới được cấp CORS.

Nếu server dùng 204 thay vì 200 do custom filter/gateway, thay assertion status theo behavior đã được thống nhất trong ứng dụng; test trên giả định Spring `CorsFilter` mặc định trả 200.

### Test Origin không được phép

~~~java
mockMvc.perform(options("/api/profile")
        .header("Origin", "https://untrusted.example.net")
        .header("Access-Control-Request-Method", "POST"))
    .andExpect(status().isForbidden());
~~~

Với Spring CorsFilter chuẩn và strict allowlist minh họa, response này thường là 403. Điều cần xác minh **không phải mong mọi Origin đều 200**, mà là Origin sai bị từ chối **do CORS**, không bị lẫn với authentication entry point.

### Test header không được phép

~~~java
mockMvc.perform(options("/api/profile")
        .header("Origin", "https://app.example.com")
        .header("Access-Control-Request-Method", "POST")
        .header("Access-Control-Request-Headers", "x-not-allowed"))
    .andExpect(status().isForbidden());
~~~

Nếu project dùng custom CORS processor hoặc một gateway trả status khác, cần viết assertion cho hợp đồng thực tế. Không nới `allowedHeaders("*")` chỉ để test này xanh; nếu header mới có nhu cầu hợp lệ, đưa nó qua review rồi thêm chính xác vào allowlist.

### Test một OPTIONS không có header preflight

~~~java
mockMvc.perform(options("/api/profile"))
    // Đây không phải browser CORS preflight nếu thiếu Origin/ACR-Method.
    // Status phụ thuộc method mappings và authorization của ứng dụng.
    ;
~~~

Không được coi test này là đại diện cho preflight. Một OPTIONS bình thường có thể bị rule authentication hoặc MVC routing xử lý khác.

## 22. Test actual request sau preflight: CORS thành công ≠ API thành công

Một API có thể trả:

~~~text
OPTIONS /api/profile → 200 CORS headers hợp lệ
POST /api/profile → 403 thiếu CSRF token
~~~

Đây là hành vi hợp lý với cookie-authenticated endpoint có CSRF protection. Ví dụ MockMvc test sử dụng các helper test riêng:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

mockMvc.perform(post("/api/profile")
        .header("Origin", "https://app.example.com")
        .with(user("alice").roles("USER"))
        .contentType("application/json")
        .content("{\"displayName\":\"Alice\"}"))
    .andExpect(status().isForbidden());

mockMvc.perform(post("/api/profile")
        .header("Origin", "https://app.example.com")
        .with(user("alice").roles("USER"))
        .with(csrf())
        .contentType("application/json")
        .content("{\"displayName\":\"Alice\"}"))
    .andExpect(status().isNoContent());
~~~

Test yêu cầu controller lab trả 204 khi thành công, endpoint được authorization cho user tương ứng và `spring-security-test` đã tích hợp. Nó **không** dùng browser để tải CSRF token thật hoặc kiểm tra cookie `SameSite`. Mục tiêu chỉ là tách bước CORS với CSRF/auth của POST.

### Controller fixture cho các test

~~~java
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
public class ProfileLabController {

    @PostMapping("/api/profile")
    ResponseEntity<Void> update(@RequestBody Map<String, String> body) {
        // Chỉ cho môi trường test; không thay đổi dữ liệu thật.
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/api/public/ping")
    Map<String, String> ping() {
        return Map.of("status", "ok");
    }
}
~~~

**Không copy route lab thiếu validation và resource-level authorization trực tiếp vào production.** CSRF chỉ giúp giảm nguy cơ request do một site khác khởi phát; nó không kiểm tra quyền sở hữu dữ liệu.

## 23. WebTestClient: Reactive preflight với Origin hợp lệ và không hợp lệ

Với `ReactiveCorsConfig` và `ReactiveApiSecurity` ở mục 15, khi WebTestClient được bind vào ứng dụng có Spring Security:

~~~java
import static org.hamcrest.Matchers.containsString;

webTestClient.options()
    .uri("/api/profile")
    .header("Origin", "https://app.example.com")
    .header("Access-Control-Request-Method", "POST")
    .header(
        "Access-Control-Request-Headers",
        "content-type,x-csrf-token"
    )
    .exchange()
    .expectStatus().isOk()
    .expectHeader().valueEquals(
        "Access-Control-Allow-Origin", "https://app.example.com"
    )
    .expectHeader().value(
        "Access-Control-Allow-Methods", containsString("POST")
    )
    .expectHeader().value(
        "Access-Control-Allow-Headers", containsString("x-csrf-token")
    );

webTestClient.options()
    .uri("/api/profile")
    .header("Origin", "https://untrusted.example.net")
    .header("Access-Control-Request-Method", "POST")
    .exchange()
    .expectStatus().isForbidden();
~~~

Không tạo mock user hoặc bearer credentials cho preflight. Nếu response khác, kiểm tra **WebFilterChainProxy, CorsWebFilter/ServerHttpSecurity.cors, reactive CorsConfigurationSource và source path**. Test sai Origin bị từ chối thường là kết quả mong muốn.

### Test actual POST trong WebFlux

~~~java
import org.springframework.http.MediaType;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;

webTestClient.mutateWith(mockUser("alice").roles("USER"))
    .post()
    .uri("/api/profile")
    .header("Origin", "https://app.example.com")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue("{\"displayName\":\"Alice\"}")
    .exchange()
    .expectStatus().isForbidden();

webTestClient.mutateWith(mockUser("alice").roles("USER"))
    .mutateWith(csrf())
    .post()
    .uri("/api/profile")
    .header("Origin", "https://app.example.com")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue("{\"displayName\":\"Alice\"}")
    .exchange()
    .expectStatus().isNoContent();
~~~

Tương tự Servlet, test yêu cầu controller và authorization phù hợp. **Một WebTestClient mock exchange không đi qua reverse proxy hoặc HTTP parser của Netty production**; nếu preflight chỉ lỗi trên public path, cần thêm HTTP integration/browser test.

## 24. Playwright: chứng minh browser được phép gửi request sau preflight

MockMvc và WebTestClient kiểm tra API behavior ở backend. Nhưng **browser mới thực thi CORS**; một HTTP 200 ở MockMvc không chứng minh browser thật sẽ chấp thuận response.

Thiết kế một lab có:

~~~text
Frontend: https://app.example.test/test-page
API:      https://api.example.test/api/public/ping

API:
  GET /api/public/ping -> 200 JSON {"status":"ok"}
  CORS allowed origin -> https://app.example.test
  Allowed header -> X-CSRF-TOKEN (chỉ dùng để kích hoạt preflight trong lab)
~~~

Các hostname chỉ là địa chỉ minh họa, phải được cấu hình DNS/hosts và HTTPS certificate trong môi trường kiểm thử. Chúng không phải dịch vụ có sẵn.

### Test browser thật bằng JavaScript chạy trong page

~~~javascript
import { test, expect } from "@playwright/test";

test("cross-origin request có custom header được CORS chấp thuận",
  async ({ page }) => {
    await page.goto("https://app.example.test/test-page");

    const result = await page.evaluate(async () => {
      const response = await fetch(
        "https://api.example.test/api/public/ping",
        {
          method: "GET",
          headers: {
            // Header tùy chỉnh buộc browser cân nhắc preflight.
            // Giá trị không phải CSRF token thật trong lab công khai.
            "X-CSRF-TOKEN": "lab-placeholder"
          }
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

Đây là **test cho public GET** dùng header tùy chỉnh chỉ để buộc xảy ra preflight, tránh nhầm kết quả với authentication hoặc CSRF của POST. Ở bài test thực về POST, cần thêm phiên đăng nhập/CSRF hợp lệ và kiểm chứng actual request riêng.

### Test bị CORS từ chối

Một test có thể mở trang `https://untrusted.example.test/test-page` rồi gọi cùng API:

~~~javascript
import { test, expect } from "@playwright/test";

test("origin không được phép không đọc được API response",
  async ({ page }) => {
    await page.goto("https://untrusted.example.test/test-page");

    const blocked = await page.evaluate(async () => {
      try {
        await fetch("https://api.example.test/api/public/ping", {
          headers: { "X-CSRF-TOKEN": "lab-placeholder" }
        });
        return false;
      } catch {
        // Fetch bị từ chối ở browser; không suy HTTP status từ exception.
        return true;
      }
    });

    expect(blocked).toBe(true);
});
~~~

**Giới hạn của negative test:** `fetch` ném lỗi còn có thể do DNS, TLS, CSP hoặc mạng. Để chứng minh *cụ thể* do CORS, phải có browser Console/Network và log preflight ở backend, không chỉ assert exception.

### Có nên kiểm tra OPTIONS từ Playwright request events?

Không nên viết test phụ thuộc tuyệt đối vào việc browser automation luôn hiển thị OPTIONS preflight như một request event thông thường: cache preflight, browser engine và API quan sát có thể khác nhau. **Kiểm tra hành vi fetch bằng Playwright**, kết hợp DevTools hoặc access logs của proxy/API để xác nhận OPTIONS thực tế và HTTP response.

## 25. Cache preflight: vì sao vừa sửa CORS nhưng browser còn báo lỗi?

Browser có thể cache kết quả preflight hợp lệ theo `Access-Control-Max-Age` trong giới hạn riêng của nó. Vì vậy:

~~~text
Lần 1:
  OPTIONS /api/profile -> 200 + Allow-* + Max-Age
  POST /api/profile -> thực hiện

Lần 2:
  Browser có thể dùng preflight cache
  POST /api/profile -> gửi mà không có OPTIONS mới
~~~

Khi debug sau deploy:

- Không thấy OPTIONS mới **không chứng minh** CORS không chạy hoặc browser bỏ qua bảo vệ.
- Nếu actual POST bị 403, có thể đó là CSRF/auth; đừng kết luận preflight hỏng.
- Browser cache preflight khác với HTTP shared cache thông thường; chỉ đặt `Cache-Control: no-store` trên response API không nhất thiết xóa preflight cache.
- Khi thay đổi CORS policy, cần test với **browser context mới** và kiểm soát cache; không đánh giá bằng một tab sống lâu duy nhất.

### Proxy/CDN cache CORS headers sai Origin

Nếu edge cache response cho `Origin: https://app.example.com` rồi phát lại cho `Origin: https://untrusted.example.net`, CORS có thể hoạt động sai. Tùy kiến trúc, các header `Vary: Origin`, `Vary: Access-Control-Request-Method` và `Vary: Access-Control-Request-Headers` cùng chính sách cache của CDN cần được xem xét.

**Không tự thêm CORS response bằng cách reflect mọi Origin**. Cần bảo đảm cached variant và allowlist đúng; với API chứa dữ liệu người dùng, caching còn phải tôn trọng authentication và dữ liệu riêng tư.

## 26. SameSite và cookies: preflight thành công vẫn có thể là anonymous POST

Một SPA ở `https://app.example.com` gọi `https://api.example.com`; đây là **cross-origin** vì hostname khác, nhưng thường có thể **same-site** theo chính sách cookie khi dùng cùng scheme và registrable domain.

Với:

~~~javascript
await fetch("https://api.example.com/api/profile", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": csrfToken
  },
  body: JSON.stringify({ displayName: "Alice" })
});
~~~

Có thể xảy ra:

~~~text
OPTIONS -> 200 CORS hợp lệ
POST    -> 302 /login hoặc 401
~~~

Lúc này **không còn là lỗi preflight**. Browser có thể không gửi cookie phiên tới API vì:

- Cookie host-only ở `app.example.com`, không dành cho `api.example.com`.
- Cookie Path không bao phủ `/api/profile`.
- Cookie `Secure` không đi theo HTTP thực tế.
- Cookie `SameSite` không cho phép trong cross-site context thật.
- Frontend dùng `credentials: "same-origin"` cho cross-origin API.
- Session đã hết hạn hoặc backend không khôi phục được.

**Không sửa bằng cách cho phép mọi Origin**. Kiểm tra Request Cookies trên **POST thật**, cookie store, session log và CSRF token riêng.

### Origin khác site khi SPA và API thuộc công ty khác nhau

Nếu frontend ở `https://frontend.partner.test` và API ở `https://api.example.test`, request là cross-site. Cookie `SameSite=Lax` thường không đi trong cross-site fetch, dù CORS allowlist hoàn toàn hợp lệ; `SameSite=None; Secure` còn chịu chính sách third-party cookies. Đây là vấn đề **cookie policy**, không phải lỗi preflight đã xử lý thành công.

## 27. Kịch bản A — OPTIONS bị HTTP Basic chặn trước CORS

**Bối cảnh:** API bảo vệ bằng HTTP Basic; developer chỉ thêm:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
);
http.httpBasic(Customizer.withDefaults());
~~~

Frontend gửi preflight:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type
~~~

Response:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
~~~

**Điều tra:**

1. Xác nhận không có session/Basic auth header trong OPTIONS là bình thường.
2. Xem `SecurityFilterChain` thực sự match OPTIONS và có `CorsFilter` không.
3. Xem CORS source có policy cho Origin và `/api/orders` không.
4. Bật log chọn lọc cho `FilterChainProxy`/CORS; tìm entry point xử lý trước CORS.
5. Sau khi tích hợp CORS đúng, test lại OPTIONS **không authentication**.

**Cách sửa:** thêm CORS policy được review, dùng `http.cors(...)` trên chain API đúng thứ tự. Không tắt HTTP Basic của actual request hoặc cho POST `permitAll()`.

**Tiêu chí PASS:** OPTIONS hợp lệ được cho phép; POST không authentication vẫn bị từ chối đúng chính sách.

## 28. Kịch bản B — OPTIONS trả 302 vì rơi vào form-login fallback chain

**Bối cảnh:**

~~~text
Chain 1: match-all -> form login
Chain 2: /api/** -> CORS API + Bearer
~~~

Vì chain 1 match mọi request, `OPTIONS /api/orders` không bao giờ tới chain 2. Spring Security trả:

~~~http
HTTP/1.1 302 Found
Location: /login
~~~

**Hướng kiểm tra:** liệt kê chain beans, `@Order` và `securityMatcher`; bật FilterChainProxy TRACE, gửi đúng OPTIONS preflight. Đừng chỉ đọc `requestMatchers("/api/**")` trong authorization và mặc định nó xác định phạm vi chain.

**Cách sửa:** đưa chain API `@Order(1)` trước fallback `@Order(2)`, để `securityMatcher("/api/**")` bao phủ OPTIONS và actual methods. Regression test cả `OPTIONS /api/**`, `POST /api/**` và `GET /dashboard`.

**Tiêu chí PASS:** OPTIONS đến CORS API và được chấp thuận khi Origin hợp lệ; web route vẫn dùng form login bình thường.

## 29. Kịch bản C — 403 của CORS processor, không phải chặn trước CORS

**Bối cảnh:** security CORS đã được tích hợp đúng, nhưng frontend đổi origin từ:

~~~text
https://app.example.com
~~~

sang:

~~~text
https://staging.app.example.com
~~~

Trong khi `allowedOrigins` vẫn chỉ có production origin.

Preflight:

~~~http
OPTIONS /api/profile HTTP/1.1
Origin: https://staging.app.example.com
Access-Control-Request-Method: POST
~~~

Spring CORS processor có thể trả `403 Invalid CORS request`. **Đây không phải authentication filter chặn sớm**; policy hoạt động đúng khi từ chối origin chưa được duyệt.

**Điều tra theo thứ tự:**

1. Xác nhận Origin thực của trang, không nhầm với hostname backend.
2. Xác nhận protocol và port: `http://` khác `https://`, port 3000 khác 443.
3. Nếu staging origin thực sự phải được phép, thêm **đích danh origin đó** theo environment/security review.
4. Test một origin không hợp lệ vẫn bị từ chối.

**Không dùng `allowedOrigins("*")` hoặc reflect Origin mù quáng với cookie-authenticated API**.

## 30. Kịch bản D — Gateway chặn OPTIONS, Spring hoàn toàn không thấy request

**Bối cảnh:** sau khi đặt API sau API Gateway/WAF, browser nhận 405:

~~~http
HTTP/1.1 405 Method Not Allowed
Allow: GET,POST
~~~

Trên Spring origin không có access log của OPTIONS.

**Hướng chẩn đoán:**

- Kiểm tra rule của gateway/ingress có route OPTIONS hay chỉ GET/POST.
- Kiểm tra WAF method allowlist, có rule chặn `Origin`/`Access-Control-Request-Headers`?
- So cùng request gửi **qua public hostname** và tới origin trong mạng test được phép.
- Gắn correlation ID; xác định nơi trả 405.
- Nếu gateway tự xử lý preflight, xác minh CORS policy của gateway có được đồng bộ với policy API và CORS headers cho actual response không.

**Cách sửa:** cho preflight được xử lý tại đúng tầng theo một CORS policy nhất quán. Không sửa `HttpSecurity` nếu request chưa tới Spring.

## 31. Kịch bản E — OPTIONS thành công nhưng POST không có cookie

**Bối cảnh:** preflight trả 200 và tất cả headers chính xác, nhưng actual POST:

~~~http
POST /api/profile HTTP/1.1
Origin: https://app.example.com
Content-Type: application/json
X-CSRF-TOKEN: ...
~~~

không có Cookie, dẫn đến 302 login/401 hoặc CSRF 403.

**Nguyên nhân thuộc lớp khác:** cookie `SameSite`/`Secure`/`Domain`/`Path`, `fetch.credentials`, session timeout hoặc proxy cookie rewrite.

**Đối chứng:** dùng DevTools Request Cookies của POST thật, không nhìn OPTIONS. Tái hiện với browser context có login hợp lệ và một request same-origin/same-site phù hợp.

**Cách sửa:** điều chỉnh cookie architecture/credentials theo trust boundary, giữ CSRF và CORS. Preflight không cần Cookie và không nên bị buộc mang Cookie.

## 32. Kịch bản F — Chỉ một route thất bại do path rewrite hoặc firewall

**Bối cảnh:** `OPTIONS /api/items` thành công nhưng `OPTIONS /gateway/api/items` trả 404/400.

Có thể:

- Proxy chỉ rewrite GET/POST; OPTIONS giữ nguyên prefix.
- CORS source chỉ đăng ký `/api/**`, trong khi Spring nhận `/gateway/api/**`.
- Security matcher bao phủ actual POST nhưng không bao phủ preflight.
- URL có ký tự bị HTTP firewall hoặc container từ chối trước CORS.

**Các bước:**

1. Ghi public URL, upstream URL, servlet context path hoặc WebFlux exchange path.
2. So request method và path ở từng tầng.
3. Nếu response 400, tìm `RequestRejectedException` hoặc HTTP parsing rejection.
4. Nếu response 404, tìm router/handler nào sinh 404.
5. Sửa canonical path/rewrite/matcher; kiểm thử cả OPTIONS và actual method.

**Không tắt firewall toàn bộ**, cũng không mở CORS cho mọi path để che một route rewrite sai.

## 33. Runbook: định vị nơi chặn preflight theo tám bước

~~~mermaid
flowchart TD
    A[Browser báo lỗi cross-origin request] --> B{OPTIONS preflight có thực sự được phát?}
    B -- Không --> C[Same-origin/simple request/preflight cache/CSP/TLS]
    B -- Có --> D{Có response từ public endpoint?}
    D -- Không --> E[DNS, TLS, network, WAF timeout]
    D -- Có --> F{OPTIONS tới Spring origin?}
    F -- Không --> G[CDN, WAF, gateway, proxy rewrite hoặc redirect]
    F -- Có --> H{CORS processor dự kiến đã chạy?}
    H -- Không --> I[Firewall, filter order, security chain, custom filter]
    H -- Có --> J{CORS policy chấp thuận?}
    J -- Không --> K[Allowed Origin, requested method, requested headers]
    J -- Có --> L{Browser gửi actual request?}
    L -- Không --> M[CORS response headers, cache, browser policy/PNA]
    L -- Có --> N[Authentication, cookies, CSRF, authorization, actual CORS]
    E --> O[Test hồi quy HTTP + browser]
    G --> O
    I --> O
    K --> O
    M --> O
    N --> O
~~~

### Bước 1 — Xác định request và origin thật

Ghi URL trang gọi, URL API, method thực, tên custom headers, có dùng `credentials` và browser error. Tính **origin từ scheme/host/port**, không chỉ dựa vào domain. Browser có thể không cần preflight cho request same-origin hoặc CORS-safelisted.

### Bước 2 — Xem OPTIONS trước khi nhìn POST

Trong DevTools, xác định `OPTIONS` có `Origin` và `Access-Control-Request-Method`. Kiểm tra response status, Location, WWW-Authenticate, CORS headers và request ID. Nếu không có OPTIONS, tìm preflight cache, request type, CSP, mixed content, browser/network error.

### Bước 3 — Xác định response do tầng nào tạo

Đối chiếu request ID giữa CDN/WAF, gateway, reverse proxy, container/Netty, Spring security log và controller access log. Không sửa Spring code nếu edge không forward request.

### Bước 4 — Xác minh HTTP request tới được CORS processor

Trong Servlet, kiểm tra `FilterChainProxy`, `HttpFirewall`, selected `SecurityFilterChain` và `CorsFilter`. Trong WebFlux, kiểm tra `WebFilterChainProxy`, selected `SecurityWebFilterChain`, `CorsWebFilter` hoặc CORS integration. Tránh đặt auth/custom filter trước CORS với điều kiện yêu cầu credentials.

### Bước 5 — Khi CORS đã chạy, kiểm tra đúng policy

So `Origin` chính xác, `Access-Control-Request-Method`, `Access-Control-Request-Headers`, path mapping và `allowCredentials`. Nếu source không cho method/header, sửa allowlist theo yêu cầu chức năng được duyệt. **Không dùng wildcard như một cách bỏ qua chẩn đoán.**

### Bước 6 — Xác minh actual request và response

Khi OPTIONS hợp lệ, browser mới có thể gửi POST/PUT/DELETE. Kiểm tra authentication, session cookie, CSRF token, authorization và CORS headers trên **actual response**. Lỗi ở đây không nhất thiết liên quan tới OPTIONS nữa.

### Bước 7 — So origin và public path

So cùng OPTIONS được gửi tới origin (chỉ trong mạng lab được phép) và public hostname. Nếu chỉ public thất bại, xem TLS, redirect, path rewrite, WAF/rate limits và CORS policy tại gateway. Một request giả lập bằng curl còn cần test browser vì curl không enforce CORS.

### Bước 8 — Viết regression tests và giữ bảo vệ

Test ít nhất các cặp: hợp lệ/không hợp lệ Origin, method được phép/không được phép, custom header được phép/không được phép, preflight không credentials, actual request không authenticated, actual request đã authenticated + CSRF hợp lệ. Nếu ứng dụng có nhiều chains, test từng group route và OPTIONS/POST riêng.

## 34. Anti-pattern: những cách “sửa CORS” gây rủi ro hoặc không có tác dụng

| Cách làm sai | Vì sao không đúng | Hướng đúng |
|---|---|---|
| Tắt Spring Security để OPTIONS trả 200 | Xóa authentication/authorization/headers cho actual API | Tích hợp CORS sớm, giữ security chain |
| `permitAll()` mọi OPTIONS rồi dừng ở đó | Chưa cung cấp CORS headers hợp lệ | CORS source + processor đúng thứ tự |
| Mở `permitAll()` cả POST để hết 401 | Bỏ kiểm soát nghiệp vụ | Chỉ preflight không cần authentication; POST vẫn phải xác thực |
| Tắt CSRF toàn bộ khi preflight thất bại | OPTIONS mặc định không cần CSRF; POST có thể cần | Sửa CORS, giữ CSRF cho browser credentials |
| `allowedOrigins("*")` trên API có session cookie | Không hợp lệ với credentialed CORS response và mở rộng trust | Explicit allowed origins, review mỗi môi trường |
| Reflect mọi Origin và thêm `Allow-Credentials: true` | Dễ tạo chính sách CORS quá rộng | Kiểm tra Origin qua allowlist nghiêm ngặt |
| `allowedHeaders("*")` vì thiếu một header | Có thể mở hơn cần thiết | Thêm đúng tên header hợp lệ, test negative |
| Cấu hình `@CrossOrigin` nhưng bỏ qua security filter order | MVC có thể chưa được gọi khi preflight bị auth chặn | Tích hợp CORS với Spring Security hoặc filter trước |
| Dùng hai CORS processors khác policy | Trùng headers, từ chối không nhất quán | Một nguồn sở hữu CORS rõ ràng |
| Ép preflight gửi JSESSIONID/Authorization | Browser preflight không mang credentials như actual request | Cho preflight được xử lý dựa vào Origin/method/headers |
| Tự thêm GET/POST controller OPTIONS trên mọi route | Không sửa được 401/302 do filter trước controller | CORS filter đúng vị trí |
| Follow 302 của OPTIONS và coi là CORS success | Redirect che điểm lỗi, browser có thể từ chối | Gọi final canonical HTTPS URL; sửa proxy/entry point |
| Tắt HTTP firewall khi URI bị reject | Mở request smuggling/path confusion risks | Sửa URL normalization, review ngoại lệ hẹp nếu cần |
| Cho WAF bỏ qua mọi OPTIONS trên mọi đường | Mở route/method ngoài API surface | Chỉ cho OPTIONS hợp lệ tới đúng API/CORS policy |
| Tắt CSP/HSTS vì fetch không hoạt động | Làm suy yếu browser/TLS protection | Phân biệt CSP, mixed content, HSTS và CORS |
| Log cookie hoặc token để debug | Rò session, CSRF, auth credentials | Log request ID, headers names, booleans, policy decision |
| Coi curl 200 là browser CORS đã PASS | Curl không enforce CORS | Dùng Playwright/DevTools để chứng minh browser |
| Đổi `SameSite=None` để OPTIONS mang cookie | Không giải quyết preflight credentialless | Giữ cookie policy, sửa CORS hoặc actual request |

Một sửa đổi CORS phải được test **tích cực và tiêu cực**: request hợp lệ vẫn được phép, Origin/header/method không hợp lệ vẫn bị từ chối. Nếu mọi nguồn đều thành công sau khi sửa, đó có thể là dấu hiệu policy bị nới quá mức.

## 35. Bài thực hành tổng hợp: giải mã một preflight lỗi 401/403/302

**Bối cảnh:** có API Spring Boot phục vụ `/api/public/ping` và `/api/profile`, frontend từ origin khác, một reverse proxy staging. Xây dựng hai biến thể Servlet và WebFlux; dùng môi trường giả lập có account test, dữ liệu demo và HTTPS hostname được kiểm soát.

### Nhiệm vụ

1. **Baseline Servlet:** cấu hình `CorsConfigurationSource` với origin `https://app.example.test`, cho `GET/POST` và headers `Content-Type`, `X-CSRF-TOKEN`; bật `http.cors(...)` trên chain API.
2. Gửi một preflight bằng curl **không có Cookie/Authorization**. Xác minh HTTP success và CORS headers, không follow redirect.
3. Gửi preflight với Origin không trong allowlist; xác minh bị từ chối và tìm CORS rejection log.
4. Gửi preflight với header `X-Not-Allowed`; xác minh không được chấp thuận. Chỉ thêm một header có nhu cầu thực sau security review.
5. **Tái hiện 401:** bỏ CORS integration nhưng giữ `httpBasic()`. Gọi OPTIONS và ghi entry point; thêm lại CORS đúng vị trí, xác minh không cần authentication cho preflight.
6. **Tái hiện 302:** tạo API chain và form-login fallback chain, cố tình để fallback match-all đứng trước. Quan sát OPTIONS đi nhầm chain, sửa `@Order`/`securityMatcher` và kiểm thử lại web route.
7. **Tái hiện 403 CORS thật:** đổi Origin sang staging hostname chưa được cấp phép, xác minh CORS processor thực sự từ chối; không nhầm với auth.
8. **Tái hiện 405 gateway:** cấu hình gateway test không forward OPTIONS, so public với origin; sửa route/method handling mà không mở actual API.
9. **Tái hiện 400 firewall:** gửi URL bất thường trong Servlet lab, xác nhận có HTTP parsing/`RequestRejectedException`; sửa URL canonical thay vì tắt firewall.
10. **Test POST thật:** sau khi OPTIONS thành công, gửi POST thiếu authentication và thiếu CSRF token; xác định status/rejection layer. Gửi một request authenticated + CSRF hợp lệ và xác nhận controller demo hoạt động.
11. **Reactive:** tạo `SecurityWebFilterChain` và reactive `CorsConfigurationSource`; viết WebTestClient test Origin hợp lệ/không hợp lệ và actual POST.
12. **Browser:** dùng Playwright gọi public ping với custom header từ origin hợp lệ; lặp lại từ origin không hợp lệ, phân biệt CORS violation với DNS/TLS/CSP.
13. **CORS cache:** kiểm tra request trước/sau khi thay đổi policy với browser context mới; ghi chú có thể không thấy OPTIONS nếu browser đã cache.
14. **Cookie:** thử `credentials: "same-origin"` và `include` khi gọi API khác origin trong môi trường lab; xác minh preflight và cookie của POST là hai vấn đề khác.
15. **Báo cáo:** lập bảng ghi URL/Origin, request headers preflight, HTTP status, nguồn response, selected chain, CORS decision, actual request có gửi không, nguyên nhân và fix nhỏ nhất.

### Mẫu bảng kết quả

| Ca | OPTIONS | Browser gửi actual request? | Kết luận |
|---|---|---|---|
| Hợp lệ, CORS processor sớm | 200/204 + đúng Allow-* | Có thể có | Preflight được chấp thuận |
| Basic chặn trước CORS | 401 + Basic challenge | Không | Sai integration/order |
| Form login fallback | 302 /login | Không | Sai selected chain hoặc entry point |
| Origin không được phép | 403 CORS rejection | Không | Policy từ chối đúng |
| WAF/gateway chặn | 403/405 edge | Không | Sửa edge routing/policy |
| OPTIONS hợp lệ, POST thiếu CSRF | OPTIONS 200 | Có | Điều tra CSRF của actual POST |
| OPTIONS hợp lệ, POST thiếu cookie | OPTIONS 200 | Có | Điều tra browser cookie/session |
| OPTIONS 200 thiếu Allow-Origin | 200 nhưng headers sai | Không | Chưa được browser chấp thuận |

### Câu hỏi tự đánh giá

1. Những header nào giúp phân biệt một CORS preflight với OPTIONS thông thường?
2. Vì sao browser preflight không nên bị buộc mang Bearer token hoặc session cookie?
3. `Access-Control-Request-Method: POST` khác với method thực của preflight ở đâu?
4. Nếu preflight trả 200 nhưng thiếu `Access-Control-Allow-Origin`, browser có tiếp tục POST không?
5. Tại sao một 403 `Invalid CORS request` không phải bằng chứng authentication chạy trước CORS?
6. Với Spring Security Servlet, `http.cors(...)` giải quyết vấn đề gì mà `permitAll()` cho OPTIONS chưa giải quyết?
7. Tại sao `@CrossOrigin` trên controller có thể không giúp nếu security filter chặn request sớm?
8. Cơ chế first-match của nhiều `SecurityFilterChain` ảnh hưởng OPTIONS như thế nào?
9. Một chain dùng matcher chỉ cho POST sẽ ảnh hưởng preflight OPTIONS ra sao?
10. `StrictHttpFirewall` có thể từ chối request trước `CorsFilter` không? Nên sửa gì?
11. Trong WebFlux, các thành phần nào tương ứng với Servlet `CorsFilter` và `SecurityFilterChain`?
12. Vì sao không nên đăng ký hai CORS processors có chính sách khác nhau?
13. Nếu gateway trả 405 cho OPTIONS còn Spring không có log, nên điều tra tầng nào?
14. Khi nào CORS preflight cache khiến bạn không thấy OPTIONS mới trong Network?
15. Same-site và same-origin khác nhau thế nào khi SPA ở subdomain khác API?
16. `fetch(credentials: "include")` có tự làm cookie vượt qua `SameSite`/`Domain` không?
17. Nếu OPTIONS được chấp thuận nhưng POST trả 403, những lớp bảo vệ nào cần xem?
18. Vì sao curl gửi OPTIONS thành công chưa chứng minh browser cũng chấp thuận CORS?
19. CORS `Access-Control-Allow-Credentials` có thay thế authentication/CSRF không?
20. Khi preflight có `Access-Control-Request-Private-Network`, cần xác minh thêm điều gì?
21. Tại sao không mở wildcard origin cho API credentialed chỉ để hết lỗi?
22. Một phép thử CORS tốt cần cả positive và negative cases vì sao?

## 36. Ghi nhớ

**“Preflight bị chặn trước khi xử lý CORS” nghĩa là browser hỏi xin phép bằng OPTIONS nhưng request không tới được CORS processor dự kiến**, có thể do CDN/WAF, reverse proxy, parser/HTTP firewall, security chain sai thứ tự hoặc authentication/authorization filter chạy trước CORS. Trường hợp CORS processor đã chạy và từ chối Origin/method/header là **một lỗi khác**, không được chữa bằng cách bypass authentication hay mở wildcard.

Trong Spring Security **Servlet**, kiểm tra `FilterChainProxy`, `HttpFirewall`, selected `SecurityFilterChain` và `http.cors(...)`/`CorsFilter`. Trong **Reactive/WebFlux**, kiểm tra `WebFilterChainProxy`, `SecurityWebFilterChain` và `ServerHttpSecurity.cors(...)`/`CorsWebFilter`. Dùng một CORS allowlist có người chịu trách nhiệm, cho preflight hợp lệ đi qua **không cần credentials**, nhưng vẫn bảo vệ **actual request** bằng authentication, authorization, CSRF và kiểm tra nghiệp vụ.

Khi chẩn đoán, **xem OPTIONS riêng, tìm nơi sinh response, rồi mới xem POST thật có được gửi không**. Kết hợp DevTools/Playwright với curl, MockMvc, WebTestClient và log proxy/Spring. Không tắt CSRF, CORS, HSTS, CSP, HTTP firewall hoặc bảo vệ session để làm một request sai chính sách thành công. Mục tiêu của `SPRING_SECURITY_HTTP_PROTECTION` là sửa đúng lớp HTTP/browser và giữ nguyên các phòng vệ phối hợp.
