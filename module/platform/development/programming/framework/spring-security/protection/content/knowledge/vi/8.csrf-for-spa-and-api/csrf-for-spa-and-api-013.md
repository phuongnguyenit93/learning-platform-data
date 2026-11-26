# Tránh đưa token vào log, cache công khai hoặc đường dẫn

## Mục tiêu và phạm vi

Trong chương **CSRF cho SPA và API** thuộc module **SPRING_SECURITY_HTTP_PROTECTION**, CSRF token là bằng chứng mà frontend chủ động gửi để backend xác minh request thay đổi trạng thái, thay vì chỉ tin cookie phiên do trình duyệt tự đính kèm. Nếu token bị ghi vào **URL, access log, analytics, APM, CDN hoặc cache công khai**, lớp phòng vệ này có thể suy yếu hoặc bị lộ sang ngữ cảnh không được phép.

Bài học tập trung vào việc **giảm phát tán CSRF token** trong luồng Single-Page Application (SPA), endpoint **GET /api/csrf**, HTML form và các lớp HTTP: **Servlet, Reactive/WebFlux, proxy, gateway, CDN, browser, cookies, CORS, security headers, CSP, HSTS và bảo vệ session**.

Sau bài học, người học có thể:

1. Phân loại rủi ro khi **raw CSRF token** hoặc **XOR-masked token** bị đưa vào logs, response cache, URL, Referer và telemetry.
2. Giải thích vì sao CSRF token cần đúng **ngữ cảnh phiên và quyền truy cập**, dù bản thân token không phải session credential.
3. Thiết kế GET bootstrap trả token bằng **JSON body** hoặc cookie phù hợp, không đưa token vào query/path.
4. Phân biệt **Cache-Control: no-store**, no-cache, private, max-age=0 và Vary.
5. Triển khai endpoint CSRF có no-store trên Spring Security **Servlet** và **WebFlux**.
6. Xây dựng **logging allowlist**, tránh thu thập request/response bodies và sensitive headers.
7. Thiết kế kiểm thử MockMvc/WebTestClient và kiểm thử CDN/browser nhằm phát hiện token leakage.
8. Xử lý sự cố khi token xuất hiện trong log, link, screenshot hoặc cache đã chia sẻ.

## 1. Threat model: CSRF token không phải mật khẩu, nhưng không được công khai

Browser có thể tự gửi cookie xác thực như JSESSIONID hoặc JWT HttpOnly trên request phù hợp. CSRF protection yêu cầu thêm một giá trị mà frontend hợp lệ lấy được và **chủ động gửi** trong header hoặc form parameter.

Một site tấn công có thể khởi phát một số request tới backend nhưng thường **không đọc được CSRF token đúng phiên** do same-origin policy và các biện pháp bảo vệ liên quan.

**Phải hiểu đúng mức độ nguy hiểm:**

- CSRF token **không phải credential đăng nhập độc lập**. Có token mà không có cookie phiên hợp lệ không tự tạo được phiên authenticated.
- Tuy nhiên, khi token cùng phiên bị lộ cho bên có khả năng lạm dụng browser của nạn nhân hoặc khi có thêm credential leak, nó có thể góp phần vượt qua CSRF protection.
- Khả năng khai thác phụ thuộc repository, request handler, cookie scope, session binding và cách browser gửi credential. Không khẳng định mọi token lộ đều dẫn tới chiếm tài khoản.
- **XSS cùng origin** có thể đọc token JavaScript-readable hoặc gọi API ngay trong phiên của user; CSRF không thay chống XSS.
- Một Bearer-only API có threat model CSRF khác, nhưng **JWT, Authorization header và refresh token lại càng không được lộ** qua log/URL/cache.

### 1.1. Luồng cấp token đúng

~~~mermaid
sequenceDiagram
    autonumber
    participant SPA as Frontend SPA
    participant B as Browser cookie jar
    participant SEC as Spring Security
    participant API as API handler
    SPA->>SEC: GET /api/csrf + cookie phiên
    SEC->>SEC: Repository cung cấp expected token
    SEC-->>SPA: JSON token, Cache-Control no-store
    SPA->>SPA: Giữ token trong memory
    SPA->>SEC: POST /api/orders + cookie + X-CSRF-TOKEN
    SEC->>SEC: CsrfFilter kiểm tra expected và actual
    SEC->>API: Chỉ cho qua khi CSRF hợp lệ
    API-->>SPA: Response nghiệp vụ
~~~

**Không gửi token bằng URL**:

~~~http
GET /api/csrf?token=secret-value HTTP/1.1
GET /api/action/secret-value HTTP/1.1
POST /api/orders?_csrf=secret-value HTTP/1.1
~~~

Những URL đó có thể bị proxy, load balancer, browser, monitoring và công cụ hỗ trợ ghi lại. Endpoint lấy token nên là **GET /api/csrf không chứa secret trong query/path**, rồi token được trả trong response body theo policy phù hợp.

### 1.2. Bảng phân loại dữ liệu

| Dữ liệu | Có nên nằm trong log/URL thông thường? | Lý do |
| --- | --- | --- |
| Raw CSRF token | Không | Có thể là bằng chứng vượt CSRF trong đúng ngữ cảnh |
| XOR-masked CSRF token | Không | Vẫn có thể được request handler giải và chấp nhận |
| JSESSIONID/session cookie | Không | Credential phiên |
| JWT access token/refresh token | Không | Credential có thể được sử dụng trực tiếp |
| Authorization và Cookie headers | Không | Thường chứa credential hoặc CSRF token |
| Mật khẩu, recovery code | Không | Bí mật độc lập |
| Request correlation ID ngẫu nhiên | Có thể nếu không chứa bí mật | Dùng để truy dấu sự kiện |
| Route template như /api/orders/{id} | Có thể khi template không chứa dữ liệu nhạy cảm | Tránh dùng raw URL/path |

**Ưu tiên logging allowlist**: chỉ log những trường được cho phép, thay vì log mọi thứ rồi cố gắng loại bỏ từng biến thể key nhạy cảm.

## 2. Token có thể rò rỉ ở những đâu?

### 2.1. Query string, path, history và Referer

Nếu token xuất hiện trong URL như:

~~~text
https://api.example.com/orders?csrf=actual-token
https://app.example.com/checkout/actual-token
https://app.example.com/profile#csrf=actual-token
~~~

thì nguy cơ đến từ:

- **Browser history, bookmarks, tab synchronization, clipboard, screenshot**.
- **Nginx/Apache access logs**, API gateway, ingress, WAF, load balancer và CDN.
- **Analytics, APM, error reports, session replay, HAR exports**.
- **Referer** trong một số luồng điều hướng/tải tài nguyên, tùy Referrer-Policy và browser.
- **URLs được gửi qua chat/email**, copy vào ticket hỗ trợ hoặc dán vào công cụ debug.

Fragment sau dấu # thường không được gửi trong HTTP request, nhưng **vẫn xuất hiện trong browser history và có thể bị script, analytics hoặc screen recording thu thập**. Do đó dùng fragment **không phải cách cất CSRF token an toàn**.

**Referrer-Policy: no-referrer** có thể giảm phát tán thông tin URL sang request khác, nhưng **không sửa thiết kế đã đưa token vào URL**.

### 2.2. Application log và access log

~~~java
// ANTI-PATTERN: có thể ghi cả query string chứa token.
logger.info("Request URL {}?{}", request.getRequestURL(),
    request.getQueryString());

// ANTI-PATTERN: request body có thể chứa _csrf và secret khác.
logger.debug("Request body {}", requestBody);

// ANTI-PATTERN: Cookie và Authorization nằm trong headers.
logger.info("Incoming headers {}", headerMap);
~~~

Dùng **request.getRequestURI()** thay URL đầy đủ vẫn chưa an toàn nếu token từng được đặt trong **path segment**. Log chỉ nên ghi **route template** đã xác minh (ví dụ /api/orders/{id}), HTTP method, status, loại lỗi và correlation ID. Không log raw path hoặc query cho các endpoint có khả năng chứa dữ liệu nhạy cảm.

### 2.3. Response body và APM

Một GET bootstrap thường có response:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Content-Type: application/json

{"headerName":"X-CSRF-TOKEN","token":"actual-token"}
~~~

Dù URL sạch, **response body chứa token**. Nếu middleware, APM hoặc error reporter ghi lại **toàn bộ response body**, token vẫn lọt vào telemetry. Cache-Control không tự redaction dữ liệu ở log hoặc APM; phải cấu hình riêng.

### 2.4. Logs phía frontend

Không đưa token vào **console.log**, breadcrumbs, session-replay recordings, analytics event, JavaScript router URL, URLSearchParams, query string hoặc crash reports. Khi SPA dùng CSRF token theo session, giữ token trong **memory** thường là mô hình phù hợp; không tự lưu bền vững token trong localStorage.

Với **CookieCsrfTokenRepository**, XSRF-TOKEN có thể cần HttpOnly=false để SPA đọc. Điều này **không** có nghĩa JSESSIONID cũng phải JavaScript-readable. Cookie xác thực nên HttpOnly và HTTPS/Secure; browser vẫn gửi nó theo chính sách cookie mà không cho script đọc giá trị.

## 3. Raw token, XOR-masked token và HTML form

Spring Security có thể lưu raw expected token trong **HttpSessionCsrfTokenRepository** hoặc **CookieCsrfTokenRepository**, trong khi **XorCsrfTokenRequestAttributeHandler** tạo masked representation cho request attribute nhằm giảm rủi ro **BREACH** khi token xuất hiện trong response nén.

| Vị trí | Giá trị | Có nên log? |
| --- | --- | --- |
| Session repository | Raw expected token | Không |
| XSRF-TOKEN cookie | Raw token | Không |
| HTML form hidden field lấy từ XOR handler | Token masked | Không |
| Header SPA X-XSRF-TOKEN | Raw hoặc masked tùy contract | Không |
| GET JSON bootstrap | Token trình bày theo handler | Không |
| CsrfFilter | Actual/expected token được so khớp | Chỉ log loại lỗi, không log giá trị |

**Masked token không phải dữ liệu được phép công khai.** Đó vẫn là giá trị có thể được handler dùng để xác minh request. Không đưa nó vào URL/log chỉ vì chuỗi thay đổi ngẫu nhiên giữa các GET.

### 3.1. Đừng dùng CSRF token làm trace ID

CSRF token có thể được xóa/làm mới khi login/logout, session timeout và có biểu diễn masked thay đổi theo response. Nó không ổn định và **không dành cho tracing**.

Hãy tạo correlation ID độc lập, ngẫu nhiên và không chứa credential. Log correlation ID, mã nghiệp vụ được phân loại, route template, status và loại exception. Đừng log actual hay expected token.

### 3.2. SSR HTML chứa token cũng cần cache policy

~~~html
<form method="post" action="/profile">
  <input type="hidden" name="_csrf" value="masked-token">
  <button type="submit">Lưu</button>
</form>
~~~

Với Thymeleaf/JSP hoặc template SSR, HTML chứa hidden CSRF token theo phiên **không được đặt vào shared cache theo một key dùng chung cho mọi user**. XOR masking giảm một loại side channel, **không thay Cache-Control và cơ chế phân vùng cache**.

Đặc biệt, không cache một fragment HTML có token của user A rồi phục vụ fragment đó cho user B. Cần loại token khỏi shared fragment cache hoặc bảo đảm các fragment chứa token không bị cache liên người dùng.

## 4. Cache-Control: no-store khác với no-cache, private và Vary

Với endpoint trả CSRF token, lựa chọn thường phù hợp là:

~~~http
Cache-Control: no-store
~~~

**no-store** yêu cầu HTTP cache không lưu request/response liên quan để sử dụng lại. Nó không tự xóa dữ liệu từng lưu trước đó, không xóa browser history và không ngăn screenshots, server logs, APM hay một script đã nhận token giữ nó trong memory.

### 4.1. So sánh cache directives

| Directive | Ý nghĩa chính | Đủ cho token theo phiên? |
| --- | --- | --- |
| **no-store** | Cache không được lưu response/request dùng lại | **Ưu tiên** cho bootstrap CSRF |
| **no-cache** | Cache có thể lưu nhưng phải revalidate trước khi dùng | Không tương đương no-store |
| **private** | Shared cache không được lưu, private cache vẫn có thể | Hữu ích nhưng không mạnh bằng no-store |
| **max-age=0** | Freshness bằng 0 | Cache vẫn có thể lưu |
| **must-revalidate** | Phải revalidate khi response stale | Không cấm lưu |
| **Vary: Cookie** | Hướng cache phân biệt request theo Cookie | Không thay no-store và rủi ro cấu hình cache key |
| **Vary: Origin** | Quan trọng khi CORS response khác theo Origin | Không ngăn lộ token theo session |
| **Pragma: no-cache** | Tương thích một số HTTP cache cũ | Không thay no-store |

**Dùng no-store cho JSON token, SSR form/HTML chứa token và các response authenticated nhạy cảm theo chính sách.** Không cần đặt no-store cho mọi tài nguyên public như CSS, JS versioned hoặc ảnh tĩnh.

### 4.2. Set-Cookie không phải chính sách cấm cache

~~~text
User A: GET /api/csrf + JSESSIONID=A
CDN: lưu JSON token-A dưới cache key chỉ gồm URL
User B: GET /api/csrf + JSESSIONID=B
CDN: trả lại JSON token-A cho B
~~~

Token của A có thể không hợp lệ với phiên B nên POST bị 403, nhưng **dữ liệu bảo vệ đã bị phục vụ sai đối tượng**. Nếu đồng thời có session leak hoặc cơ chế CSRF dùng cookie yếu, rủi ro có thể nghiêm trọng hơn.

**Set-Cookie không tự bảo đảm mọi reverse proxy/CDN không cache body**. Các cache rules tùy chỉnh có thể override các mặc định bạn mong đợi.

### 4.3. Xác minh từng tầng

~~~mermaid
flowchart LR
    A["SPA"] --> B["Browser cache"]
    B --> C["CDN/reverse proxy"]
    C --> D["Gateway/WAF"]
    D --> E["Spring Security"]
    E -->|Token response + no-store| D
    D --> C
    C --> B
    B --> A
~~~

Cần kiểm tra:

1. Backend trả đúng **Cache-Control: no-store** khi endpoint chứa token.
2. CDN/gateway **bypass cache** cho /api/csrf, login/logout/refresh, nội dung user-specific và SSR page chứa token.
3. Không dùng cache key chỉ theo URL cho response phụ thuộc session cookie.
4. Response lỗi cũng không vô tình hiển thị token và không bị ghi body vào telemetry.
5. Không dùng **Vary: Origin/Cookie** như cách thay no-store.
6. Việc xoá cache cũ/purge cần quy trình riêng nếu token đã bị cache trước khi sửa.
7. Công cụ test phải xem **response từ edge thực**, không chỉ curl trực tiếp vào origin server.

## 5. Spring Security Servlet: GET JSON token với no-store

Ví dụ dùng **Spring Boot 3, Spring Security 6.x, Java 17+** và **HttpSessionCsrfTokenRepository**. SPA nhận token qua JSON, backend lưu expected token theo session. Đây là phương án phù hợp khi browser và API khác hostname và frontend không thể đọc cookie host-only XSRF của API.

### 5.1. SecurityFilterChain giữ CSRF và cache-control

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class BrowserSecurityConfiguration {

    @Bean
    SecurityFilterChain browserChain(HttpSecurity http)
            throws Exception {
        return http
            .csrf(Customizer.withDefaults())
            .headers(headers -> headers
                .cacheControl(Customizer.withDefaults()))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().permitAll())
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
~~~

Spring Security **mặc định bổ sung một số cache-control security headers** để giảm việc lưu response nhạy cảm; tuy vậy, không nên chỉ dựa vào “framework chắc đã làm đúng” khi endpoint cấp token đi qua proxy/gateway hoặc có controller đặt header override.

**Đặt Cache-Control: no-store ngay trong endpoint trả token**, và kiểm tra response thực sau mọi filter/gateway. Nếu dự án cố tình tắt default security cache headers cho public static assets, phải giữ chính sách riêng trên những response chứa token và session data.

**permitAll GET /api/csrf không tắt CsrfFilter** cho POST/PUT/PATCH/DELETE. Nếu app có nhiều SecurityFilterChain, GET cấp token và POST được bảo vệ phải dùng repository/request handler tương thích.

### 5.2. Controller cấp token bằng JSON, không đưa vào URL

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ServletCsrfBootstrapController {

    record CsrfPayload(String headerName, String token) {}

    @GetMapping(
        path = "/api/csrf",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    ResponseEntity<CsrfPayload> csrf(HttpServletRequest request) {
        CsrfToken token = (CsrfToken) request.getAttribute(
            CsrfToken.class.getName());

        if (token == null) {
            throw new IllegalStateException(
                "CSRF filter is not configured");
        }

        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(new CsrfPayload(
                token.getHeaderName(),
                token.getToken()));
    }
}
~~~

**Vì sao cách này phù hợp:**

1. Request là **GET /api/csrf** cố định; token không có trong query string hoặc path.
2. Controller lấy token từ **request attribute** do Spring Security chuẩn bị; không tự tạo chuỗi token song song.
3. Truy cập **token.getToken()** hiện thực hóa deferred token khi cần.
4. Response có **no-store**, giảm rủi ro lưu body token trong HTTP cache.
5. JSON chỉ có **headerName và token**, không thêm session ID, JWT, mật khẩu hoặc thông tin account không cần thiết.
6. Không log **CsrfPayload** hoặc ResponseEntity body trong controller, access log hay APM.

**Lưu ý raw/XOR:** Trên Servlet Spring Security 6.x, request attribute thường được **XorCsrfTokenRequestAttributeHandler** trình bày để giảm BREACH. Token JSON có thể là **masked token**. Frontend phải gửi nguyên chuỗi JSON qua header do server chỉ định và request handler phải giải đúng định dạng. Không trộn JSON masked với một SPA handler luôn coi header là raw cookie token.

### 5.3. Response minh họa

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Content-Type: application/json
X-Content-Type-Options: nosniff

{"headerName":"X-CSRF-TOKEN","token":"session-specific-token"}
~~~

Nếu là GET token đầu tiên của anonymous session, Spring Security có thể tạo session cookie để lưu expected token. Cookie phiên phải **HttpOnly, Secure và SameSite** phù hợp; browser gửi nó trên GET/POST theo credentials và cookie policy.

**Đừng kiểm thử bằng việc chép nguyên token từ response vào bug report.** Khi cần chứng minh endpoint hoạt động, chỉ báo có token hợp lệ, kiểu header và cache-control; che toàn bộ giá trị token.

### 5.4. Nếu dùng CookieCsrfTokenRepository

Với một SPA cùng origin đọc raw token từ XSRF-TOKEN cookie, có thể chọn **CookieCsrfTokenRepository.withHttpOnlyFalse()** và handler nhận raw header.

Có thể cho GET /api/csrf trả **204 No Content** và chỉ **materialize token**, để frontend đọc cookie XSRF. Nhưng browser khác hostname không thể đọc cookie host-only của API bằng document.cookie; trường hợp đó cần thiết kế khác như JSON token và handler tương thích.

Ngay cả response 204 có Set-Cookie cũng nên có **Cache-Control: no-store** và proxy bypass, không ghi cookie/token vào log.

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CookieCsrfBootstrapController {

    @GetMapping("/api/csrf-cookie")
    ResponseEntity<Void> bootstrap(HttpServletRequest request) {
        CsrfToken token = (CsrfToken) request.getAttribute(
            CsrfToken.class.getName());

        if (token == null) {
            throw new IllegalStateException("CSRF not configured");
        }

        token.getToken();
        return ResponseEntity.noContent()
            .cacheControl(CacheControl.noStore())
            .build();
    }
}
~~~

Đây là **biến thể kiến trúc**; không triển khai hai endpoint giống mục đích mà không thiết kế rõ repository, request handler và frontend. Cookie repository và session repository có những ràng buộc vòng đời khác nhau.

## 6. Reactive/WebFlux: no-store với Mono<CsrfToken>

WebFlux không dùng HttpServletRequest/HttpSecurity. Các thành phần tương ứng gồm **ServerHttpSecurity**, **SecurityWebFilterChain**, **CsrfWebFilter**, **ServerWebExchange**, **WebSession** và **Mono<CsrfToken>**.

### 6.1. Reactive security chain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Bean
SecurityWebFilterChain browserReactiveChain(ServerHttpSecurity http) {
    return http
        .csrf(Customizer.withDefaults())
        .headers(headers -> headers
            .cache(Customizer.withDefaults()))
        .authorizeExchange(auth -> auth
            .pathMatchers(HttpMethod.GET, "/api/csrf").permitAll()
            .pathMatchers("/api/**").authenticated()
            .anyExchange().permitAll())
        .build();
}
~~~

Trên các dòng Spring Security WebFlux, cấu hình **headers.cache(...)** quản lý cache-control security response headers; API chính xác có thể khác giữa các phiên bản. Điều bắt buộc cho bài này là **endpoint token đặt no-store tường minh** và kiểm tra response cuối ở gateway/browser. Nếu ứng dụng đang dùng một phiên bản API khác, đối chiếu JavaDoc của version đang resolve thay vì bỏ cấu hình cache.

### 6.2. Reactive controller cấp token

~~~java
import java.util.Map;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
class ReactiveCsrfBootstrapController {

    @GetMapping(
        path = "/api/csrf",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    Mono<ResponseEntity<Map<String, String>>> csrf(
            ServerWebExchange exchange) {

        Mono<CsrfToken> tokenMono =
            exchange.getAttribute(CsrfToken.class.getName());

        if (tokenMono == null) {
            return Mono.error(new IllegalStateException(
                "CSRF filter is not configured"));
        }

        return tokenMono.map(token -> ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(Map.of(
                "headerName", token.getHeaderName(),
                "token", token.getToken())));
    }
}
~~~

**Không gọi block() trong WebFlux controller** để lấy token. Mono phải được subscribe qua response pipeline; ở đó repository có thể nạp/tạo token đúng WebSession.

**Không log toàn bộ exchange** hoặc response body vì có thể chứa cookie, JWT, CSRF token và dữ liệu cá nhân. Cũng không gọi **exchange.getRequest().getURI().toString()** để làm log tự động: URI có thể chứa query string.

### 6.3. Định dạng token và no-store không phụ thuộc nhau

WebFlux 6.x có thể dùng **XorServerCsrfTokenRequestAttributeHandler** để trình bày token theo cơ chế XOR/BREACH. JSON token được client gửi theo handler được chọn.

**Cache-Control: no-store không sửa raw/XOR mismatch** và **request handler đúng không làm cache công khai trở nên an toàn**. Hai lớp phải được kiểm thử riêng.

## 7. Frontend: giữ token trong memory và gửi đúng header

Một SPA khác origin nhận token qua JSON nên giữ nó trong memory theo phiên, không đưa vào URL hoặc telemetry.

~~~javascript
const API_BASE = "https://api.example.com";
let csrfForCurrentSession = null;

async function getCsrfToken() {
  const response = await fetch(API_BASE + "/api/csrf", {
    method: "GET",
    credentials: "include",
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error("CSRF bootstrap failed: " + response.status);
  }

  const data = await response.json();

  if (!data || typeof data.token !== "string" ||
      typeof data.headerName !== "string") {
    throw new Error("Unexpected CSRF response");
  }

  return data;
}

async function ensureCsrf() {
  if (csrfForCurrentSession) return csrfForCurrentSession;
  csrfForCurrentSession = await getCsrfToken();
  return csrfForCurrentSession;
}

async function updateProfile(payload) {
  const csrf = await ensureCsrf();

  const response = await fetch(API_BASE + "/api/profile", {
    method: "PATCH",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      [csrf.headerName]: csrf.token
    },
    body: JSON.stringify(payload)
  });

  if (response.status === 403) {
    throw new Error("Forbidden: verify CSRF and authorization");
  }
  if (!response.ok) {
    throw new Error("Request failed: " + response.status);
  }
  return response.status === 204 ? null : response.json();
}

function clearCsrfAfterAuthenticationChange() {
  csrfForCurrentSession = null;
}
~~~

**Đừng ghi ra console** object data, csrf, response body token hoặc headers. Một request bị 403 không có nghĩa luôn là lỗi CSRF; có thể là thiếu quyền. Không tự retry PATCH/POST nguy hiểm nếu chưa phân loại lỗi và xác minh idempotency.

### 7.1. Hai tầng chống cache trong fetch và HTTP response

- **cache: "no-store"** ở fetch là yêu cầu liên quan cách browser sử dụng HTTP cache cho request.
- **Cache-Control: no-store** ở response là chỉ thị từ server cho các HTTP cache.
- **CDN bypass** là chính sách ở proxy/edge, cần được cấu hình và kiểm tra riêng.
- **APM/log redaction** là chính sách thu thập dữ liệu, không thể suy ra từ ba cơ chế trên.

Không coi chỉ một lựa chọn trên là đủ.

### 7.2. Login/logout cần làm mới token nhưng không log token

Sau login hoặc logout thành công, token cũ có thể bị xóa bởi **CsrfAuthenticationStrategy** hoặc **CsrfLogoutHandler** trong Servlet. Frontend phải làm mới token cho phiên hiện hành, ví dụ:

~~~text
GET /api/csrf anonymous -> token A
POST login có token A và cookie phiên
Backend xác thực thành công, token A có thể bị xóa
clearCsrfAfterAuthenticationChange()
GET /api/csrf authenticated -> token B
POST nghiệp vụ với token B
POST logout với token B hiện hành
clearCsrfAfterAuthenticationChange() sau logout thành công
GET /api/csrf anonymous -> token C nếu cần
~~~

**Không xóa token trong memory trước POST logout** nếu logout cần CSRF token; chỉ xóa sau khi backend xác nhận logout. Với nhiều tab và GET bootstrap đến trễ, có thể dùng generation/epoch để tránh response của phiên cũ ghi đè token mới.

Tất cả các thao tác này vẫn không cần token xuất hiện trong URL, analytics hay log.

### 7.3. CORS cho GET JSON token

Nếu SPA và API khác origin, GET /api/csrf thường cần **credentials: include** và CORS response có **origin chính xác**:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
Cache-Control: no-store
~~~

**CORS wildcard hoặc phản chiếu mọi Origin kèm credentials rất nguy hiểm** với endpoint cấp token theo cookie/session. CORS không thay CsrfFilter và no-store; nó cũng không làm JavaScript ở subdomain khác đọc được host-only cookie của API.

## 8. Logging allowlist ở Servlet, không dump header/body

Một log hỗ trợ vận hành cần trả lời: request nào, loại thao tác nào, trạng thái gì, lỗi nhóm nào. Nó **không** cần raw token.

### 8.1. HandlerInterceptor chỉ log route template

Ví dụ với Spring MVC trên Servlet:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.HandlerMapping;

@Component
final class SafeAuditInterceptor implements HandlerInterceptor {

    private static final Logger LOG =
        LoggerFactory.getLogger(SafeAuditInterceptor.class);

    @Override
    public void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception exception) {

        Object pattern = request.getAttribute(
            HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);

        String route = (pattern instanceof String value)
            ? value
            : "unmapped";

        LOG.info("http method={} route={} status={}",
            request.getMethod(), route, response.getStatus());
    }
}
~~~

Đăng ký interceptor bằng **WebMvcConfigurer.addInterceptors(...)** theo cấu hình ứng dụng. Mục đích là log **route template** do MVC xác định, không raw URL/query, cookie, body hay CSRF header.

**Giới hạn:** Request bị Spring Security chặn **trước khi đến MVC** có thể không đi qua HandlerInterceptor. Để theo dõi 403 từ CsrfFilter, bổ sung một **AccessDeniedHandler/AuthenticationEntryPoint** hoặc security audit mechanism chỉ ghi loại lỗi, status và correlation ID, **không** in exception message chứa dữ liệu không kiểm soát hoặc request dump.

### 8.2. Audit record an toàn

~~~text
timestamp=... correlationId=... method=POST
route=/api/orders status=403 errorType=INVALID_CSRF
~~~

Không ghi:

~~~text
cookie=JSESSIONID=...
csrfExpected=...
csrfProvided=...
authorization=Bearer ...
requestBody={"_csrf":"..."}
~~~

Thông tin đủ để chẩn đoán thường là: **CSRF missing hay invalid, chain nào xử lý request, authentication có mặt không, route template, HTTP method, status, trace ID**. Với route không resolve được, dùng tên cố định **unmapped** thay vì raw path.

### 8.3. Exception handler cũng phải tránh tiết lộ

Tránh trả cho client hoặc ghi vào log một object chứa toàn bộ request, headers, session attributes hay CSRF token. Response lỗi nên có error code ổn định và trace/correlation ID:

~~~json
{"error":"REQUEST_FORBIDDEN","correlationId":"req-7e93"}
~~~

Đây là **dữ liệu minh họa**, không phải chỉ dẫn đặt token vào correlation ID. Error handler không nên tự log stack trace chứa request body ở production trừ khi đã được đánh giá/redact.

## 9. Bảo vệ observability, proxy, APM và analytics

Ngay cả khi controller không log token, những tầng khác vẫn có thể ghi lại:

| Tầng | Dữ liệu dễ bị thu | Cách xử lý |
| --- | --- | --- |
| **Reverse proxy access log** | Full request URL và query, headers nếu cấu hình | Log method/status + route đã chuẩn hóa, không body/secret headers |
| **API gateway/WAF** | Cookie, Authorization, body JSON, query | Redaction và cấu hình thu thập riêng theo endpoint |
| **APM/tracing** | Request params, headers, response body, exception metadata | Allowlist attributes, disable body capture với token endpoints |
| **Error reporting** | Breadcrumbs, fetch URL, headers, response body | Scrub sensitive fields trước upload |
| **Frontend analytics** | Current URL, query, event payloads | Không gửi token, filter route/query nhạy cảm |
| **Session replay** | Network payloads, form fields | Mask token fields, tắt capture nếu cần |
| **CDN cache/logs** | URL cache key, Set-Cookie, response body | Bypass /api/csrf, kiểm tra edge log access |
| **Service mesh** | HTTP metadata, tracing baggage | Không truyền token trong baggage/tracing labels |
| **Support ticket/HAR** | Raw network request/response | Redact trước chia sẻ và giới hạn quyền truy cập |

**Không bảo đảm an toàn chỉ bằng thay tên field từ token thành t.** Hãy rà soát **giá trị và đường dữ liệu**; một JSON token có thể được đặt tên khác sau refactor.

### 9.1. Tại sao access log mặc định cần được kiểm tra?

Nhiều web server có format log chứa **request line**, bao gồm method và URI kèm query string. Nếu dùng token trong query, token có thể đã được lưu tự động ngay cả khi ứng dụng Spring không gọi logger.

Cần kiểm tra log format của **Nginx/Apache/Envoy/API Gateway/Ingress** do hệ thống thực tế sử dụng. **Không chỉ tắt application logger**, cũng không tự cho rằng proxy luôn được cấu hình an toàn.

### 9.2. Không gắn token vào tracing baggage

Tracing baggage có thể truyền qua nhiều service và được sao chép vào spans, logs hoặc telemetry backend. Đừng dùng CSRF token làm trace ID, baggage value, span attribute, label của metric hay partition key. Dùng correlation ID ngẫu nhiên và metadata đã được phân loại.

### 9.3. Không redaction muộn sau khi đã gửi ra ngoài

Nếu SDK telemetry đã upload body/token lên nhà cung cấp bên ngoài rồi ứng dụng mới lọc trong log local, bí mật vẫn đã rò rỉ. **Redaction phải đặt trước điểm thu thập hoặc truyền dữ liệu**, và cần test toàn bộ pipeline.

## 10. Referrer-Policy, CSP, HSTS và cookie là các lớp bổ sung

| Cơ chế | Công dụng | Điều không giải quyết |
| --- | --- | --- |
| **Cache-Control: no-store** | Giảm việc HTTP caches lưu response token | Không che token trong log/APM |
| **Referrer-Policy: no-referrer** | Hạn chế browser gửi URL nguồn qua Referer | Không xóa token đã có trong URL hoặc history |
| **Content-Security-Policy (CSP)** | Giảm bề mặt script không mong muốn và exfiltration | Không thay CSRF và output encoding |
| **Chống XSS** | Giảm script độc hại đọc token trong origin | Không thay authentication/authorization |
| **HTTPS/HSTS** | Giảm rò rỉ trên đường truyền | Không ngăn ứng dụng ghi token vào log |
| **HttpOnly session cookie** | Ngăn JS đọc trực tiếp session ID | Browser vẫn có thể tự gửi cookie |
| **SameSite** | Giảm một số cross-site request có cookie | Không thay CSRF cho mọi hoàn cảnh |
| **CORS allowlist** | Hạn chế origin JavaScript nào được đọc JSON token | Không thay no-store và CsrfFilter |
| **HTTP firewall** | Chặn request HTTP bất thường | Không phát hiện token rơi vào APM |

Response minh họa cho trang nhạy cảm:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Referrer-Policy: no-referrer
X-Content-Type-Options: nosniff
Strict-Transport-Security: max-age=31536000; includeSubDomains
Content-Security-Policy: default-src 'self'; object-src 'none'
~~~

Đây là **minh họa**, không phải CSP universal: script nguồn ngoài, OAuth redirect, iframe và API origins có thể cần policy cụ thể. **HSTS includeSubDomains** chỉ an toàn khi mọi subdomain liên quan thực sự được triển khai HTTPS.

Không dùng **CSRF token làm CSP nonce, OAuth state, trace ID hoặc session identifier**. Các cơ chế có mục đích, phạm vi lộ và vòng đời khác nhau.

Ngay cả khi đã dùng Referrer-Policy mạnh, **vẫn không đưa CSRF token vào URL**: browser history, analytics và access logs còn có thể giữ URL.

## 11. MockMvc: kiểm thử Servlet không cache token

Giả định có **ServletCsrfBootstrapController** ở phần 5, SecurityFilterChain kích hoạt CSRF và thư viện **spring-security-test**.

### 11.1. GET bootstrap chứa no-store

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfNoStoreServletTests {

    @Autowired MockMvc mvc;

    @Test
    void tokenEndpointMustNotBeStored() throws Exception {
        mvc.perform(get("/api/csrf"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.CACHE_CONTROL,
                containsString("no-store")))
            .andExpect(header().doesNotExist(
                HttpHeaders.LOCATION))
            .andExpect(jsonPath("$.headerName").isNotEmpty())
            .andExpect(jsonPath("$.token").isNotEmpty());
    }
}
~~~

Test không in giá trị token ra output. **MockMvc chỉ xác minh response của ứng dụng**, không chứng minh CDN/gateway đã tôn trọng no-store; cần test end-to-end qua edge thật.

### 11.2. Token từ session phải được gửi trên unsafe request

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.jayway.jsonpath.JsonPath;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfSessionServletTests {

    @Autowired MockMvc mvc;

    @Test
    void patchNeedsCsrfTokenInSameSession() throws Exception {
        MvcResult boot = mvc.perform(get("/api/csrf"))
            .andExpect(status().isOk())
            .andReturn();

        String json = boot.getResponse().getContentAsString();
        String headerName = JsonPath.read(json, "$.headerName");
        String token = JsonPath.read(json, "$.token");
        MockHttpSession session =
            (MockHttpSession) boot.getRequest().getSession(false);

        if (session == null) {
            throw new AssertionError("Expected CSRF session");
        }

        mvc.perform(patch("/api/profile")
                .session(session)
                .with(user("alice"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"A\"}"))
            .andExpect(status().isForbidden());

        mvc.perform(patch("/api/profile")
                .session(session)
                .with(user("alice"))
                .header(headerName, token)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"A\"}"))
            .andExpect(status().is2xxSuccessful());
    }
}
~~~

**Giới hạn:** Mẫu giả định endpoint PATCH có thật, user có quyền và dữ liệu hợp lệ. **user("alice")** mô phỏng Authentication, không test login thật. Bổ sung assertion **không có thay đổi dữ liệu** khi request bị 403, test khác session và token cũ sau login/logout.

**Không bật MockMvc print() trong CI logs công khai** cho response chứa token. Dùng assertion cấu trúc, cache directive và status thay vì dump body.

## 12. WebTestClient: kiểm thử WebFlux no-store và CsrfWebFilter

### 12.1. Reactive token bootstrap

~~~java
import org.springframework.http.HttpHeaders;

// Đoạn thân test; webTestClient phải gắn SecurityWebFilterChain thật.
webTestClient.get().uri("/api/csrf")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().valueMatches(
        HttpHeaders.CACHE_CONTROL, ".*no-store.*")
    .expectBody()
    .jsonPath("$.headerName").isNotEmpty()
    .jsonPath("$.token").isNotEmpty();
~~~

**valueMatches** giúp nhận ra no-store khi response có thêm các directives khác. Không ghi body JSON ra log test.

### 12.2. Reactive unsafe request cần token

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

// Đoạn thân test; cần java.util.Map và controller PATCH thực tế.
webTestClient.mutateWith(mockUser("alice"))
    .patch().uri("/api/profile")
    .bodyValue(Map.of("displayName", "A"))
    .exchange()
    .expectStatus().isForbidden();

webTestClient.mutateWith(mockUser("alice")).mutateWith(csrf())
    .patch().uri("/api/profile")
    .bodyValue(Map.of("displayName", "A"))
    .exchange()
    .expectStatus().is2xxSuccessful();
~~~

**mockUser()** và **csrf()** chỉ mô phỏng security ở tầng test, không chứng minh cookie/WebSession và JSON token thực sự đồng bộ. Integration test cần GET /api/csrf, duy trì cookie/WebSession qua client, PATCH thiếu/sai/đúng token và quan sát lifecycle khi login/logout.

## 13. Kiểm thử CDN, proxy, telemetry và URL leakage

### 13.1. Hai phiên khác nhau đi qua edge thật

Chuẩn bị **session A và B** trong môi trường được phép thử:

1. User A GET /api/csrf qua CDN, xác minh response no-store.
2. User B GET cùng URL, cookie phiên khác, xác minh response no-store và không nhận body được cache của A.
3. Kiểm tra các header **Age, X-Cache, CF-Cache-Status** nếu nhà cung cấp có; không tự suy luận chỉ từ token string.
4. Kiểm tra CDN configuration có bypass /api/csrf hay rule override Cache-Control không.
5. Thử SSR page chứa hidden CSRF field; đảm bảo fragment HTML/token của A không bị phục vụ cho B.
6. Test request thiếu cookie và session timeout; endpoint không trả dữ liệu phiên khác.
7. Dùng công cụ browser DevTools xem response từ **edge**, không chỉ curl trực tiếp origin.
8. Không paste token thật vào ticket; chỉ báo kết quả, route, cache policy và khả năng phục vụ nhầm.

**XOR masking có thể làm chuỗi masked token khác nhau giữa các response ngay trong cùng session.** Không dùng token A khác B làm bằng chứng duy nhất rằng cache không có leakage.

### 13.2. Synthetic canary ở staging để thử redaction

Dùng một chuỗi test tổng hợp, **không phải token production**:

~~~text
TEST_CSRF_CANARY_7f81
~~~

Trong môi trường staging được kiểm soát, gửi canary tới trường/header test phù hợp rồi kiểm tra **application log, gateway log, APM, tracing, error reporting, session replay, CDN logs và CI artifacts**.

Test mong đợi: không có chuỗi canary trong các kho thu thập nhạy cảm; metadata an toàn (method, route, status, error code, correlation ID) vẫn có.

**Không dùng canary trên production và không xuất token thật ra log trong quá trình test**. Cần kết hợp kiểm tra config vì sampling của công cụ quan sát có thể khiến một request không bị thu thập dù redaction bị cấu hình sai.

### 13.3. Rà soát những đường dẫn đưa token vào URL

Tìm trong code review/test thuộc phạm vi cho phép:

- Frontend tạo query/path/fragment bằng token, _csrf, session, auth, jwt, key.
- Router hoặc redirect truyền token trong Location.
- Form HTML có token trong action URL thay vì form field/header.
- Console/debug/logger dùng request URL, request headers hay response body đầy đủ.
- Access log có raw request line với query.
- Tracing baggage và metrics labels dùng token làm identifier.
- Template fragment cache/edge cache trả nội dung chứa CSRF token theo phiên.
- Email, notification, support tickets hoặc HAR exports chứa token.

**Không in token production ra terminal rồi copy kết quả tìm kiếm vào báo cáo.** Dùng cấu hình được ủy quyền, test data tổng hợp và chỉ cung cấp trạng thái phát hiện đã được redaction.

## 14. Ứng phó sự cố khi token đã bị rò rỉ

Một chính sách phòng ngừa tốt cũng cần có quy trình xử lý **sự cố đã xảy ra**. Khi phát hiện CSRF token trong access log, CDN, analytics hoặc URL được chia sẻ, không nên chỉ xóa một dòng log rồi tuyên bố an toàn.

### 14.1. Phân loại và khoanh vùng

Cần xác định:

1. **Dữ liệu nào bị lộ?** Raw CSRF token, masked token, cookie session, JWT, Authorization header hay dữ liệu người dùng? Không ghi lại giá trị nguyên văn trong báo cáo.
2. **Nguồn lộ nào?** Browser history, URL, proxy log, application log, APM, session replay, CDN cache, screenshot, HAR, email hay support ticket?
3. **Ai có khả năng truy cập?** Chỉ nội bộ nhóm vận hành hay công khai/truyền sang bên thứ ba?
4. **Phạm vi thời gian?** Token còn hiệu lực hay phiên đã hết hạn, có token rotation lúc login/logout chưa?
5. **Repository nào?** HttpSessionCsrfTokenRepository, CookieCsrfTokenRepository hay custom signed token?
6. **Có credential bị lộ cùng không?** Nếu JSESSIONID/JWT/refresh token cũng xuất hiện, mức độ nghiêm trọng cao hơn.
7. **Có dấu hiệu request không hợp lệ được xử lý?** Kiểm tra authentication/authorization audit và side effects, không chỉ số lượng lỗi 403.

**Không suy đoán mức độ rủi ro chỉ từ giá trị token.** Token có thể không khai thác được nếu thiếu cookie phiên hoặc đã hết hạn, nhưng vẫn là một sự cố bí mật bị xuất ra sai nơi cần điều tra.

### 14.2. Chặn nguồn rò rỉ trước

- Loại bỏ code đưa token vào **query/path/redirect URL**.
- Tắt logging/telemetry thu **Cookie, Authorization, X-CSRF-TOKEN, X-XSRF-TOKEN, request/response bodies** cho endpoint nhạy cảm; tốt hơn là thiết lập allowlist.
- Đặt **Cache-Control: no-store** và **bypass CDN caching** cho endpoint token và trang chứa token.
- Giới hạn CORS đọc token JSON vào các **origin đáng tin**, không wildcard với credentials.
- Kiểm tra SSR fragment cache, SPA analytics và session replay.
- Bảo đảm log mới chỉ ghi **correlation ID, route template, status, loại exception** và metadata an toàn.

### 14.3. Giảm hiệu lực dữ liệu đã lộ

Phương án phụ thuộc repository và hệ thống xác thực:

| Tình huống | Hành động cân nhắc |
| --- | --- |
| Lộ CSRF token của session còn tồn tại | Làm vô hiệu hóa token hoặc session theo cơ chế được ứng dụng hỗ trợ; cấp token mới đúng vòng đời |
| Lộ cookie JSESSIONID hoặc refresh token | Xem xét session invalidation/revocation và xử lý credential compromise |
| Lộ token cookie XSRF từ một miền rộng | Rà soát Domain/Path, cookie injection và việc xóa/rotation cookie |
| CDN đã lưu JSON token theo session | Sửa rule và **purge/invalidate** dữ liệu cache theo provider |
| Log/APM đã có secret | Giới hạn quyền truy cập, xóa/ẩn theo chính sách retention và yêu cầu bảo mật, phối hợp với owner bên thứ ba |
| Link có token được chia sẻ | Thu hồi/rotate token tương ứng nếu còn hiệu lực; không chỉ xóa link trong một chat |

**Không có một lệnh “rotate mọi CSRF token” chung cho mọi repository.** Với session-backed token, invalidating session có thể làm token không còn hợp lệ nhưng cũng buộc user đăng nhập lại. Với cookie/custom implementation, cần xem khả năng vô hiệu hóa và ràng buộc token với phiên để không tạo cảm giác an toàn giả.

Tránh đăng nhập/đăng xuất hàng loạt hoặc ép user mất session khi chưa đánh giá tác động và chưa xác định biện pháp phù hợp; sự cố nghiêm trọng cần quy trình incident response của tổ chức.

### 14.4. Xác minh sau remediation

1. Chạy lại test GET bootstrap no-store qua origin và edge.
2. Cấp token bằng các phiên test khác nhau, xác minh không có shared-cache replay.
3. Kiểm tra app/proxy/APM/CI logs không còn synthetic canary.
4. Xác minh request thiếu/sai CSRF token vẫn bị chặn và không có side effect.
5. Test login/logout, session timeout, multi-tab và frontend token refresh.
6. Kiểm tra CSP/Referrer-Policy/HTTPS và cookie scope tiếp tục phù hợp.
7. Cập nhật rule review và test regression để lỗi không quay lại.

## 15. Bài tập thực hành

**Bài tập A — URL leakage:** Trong môi trường test, tạo một request với token giả trong query rồi quan sát server/proxy access log. Sau đó sửa frontend dùng GET bootstrap body và POST header; xác minh log không còn secret.

**Bài tập B — no-cache và no-store:** Tạo endpoint trả JSON CSRF token với no-cache, sau đó đổi sang no-store. Giải thích khác biệt giữa revalidation và cấm lưu; kiểm tra Cache-Control qua MockMvc hoặc WebTestClient.

**Bài tập C — CDN bypass:** Dùng hai phiên test A/B gọi /api/csrf qua CDN. Kiểm tra Age và cache hit metadata của provider; xác minh không có shared response giữa hai session.

**Bài tập D — Logging allowlist:** Tạo một HandlerInterceptor chỉ log method, route template và status; không log raw URI, query, headers, cookie hoặc response body. Test với synthetic canary.

**Bài tập E — APM/session replay:** Xác định SDK có thu thập request/response bodies hoặc form hidden input không. Cấu hình mask/exclusion cho CSRF token và các credential khác, rồi kiểm tra trong staging.

**Bài tập F — SSR form:** Render một form có hidden CSRF token masked; kiểm tra template fragment cache không dùng chung token cho nhiều session và HTML response có cache policy phù hợp.

**Bài tập G — Cross-origin SPA:** Đặt SPA ở app.example.com và API ở api.example.com, cấp token JSON qua CORS allowlist với credentials include. Không mở Domain cookie rộng; test frontend không đưa token vào URL hay log.

**Bài tập H — Login/logout:** Lấy token trước login, đăng nhập thật, lấy token mới và logout với token đang hợp lệ. Không log A/B/C; test chỉ cần trạng thái request, session và side effects.

**Bài tập I — WebFlux:** Dùng Mono<CsrfToken> trong GET bootstrap, thêm no-store, kiểm tra token bằng WebTestClient và test không có dữ liệu được ghi ở request bị CSRF từ chối.

**Bài tập J — Incident response tabletop:** Giả sử CSRF token cùng JSESSIONID bị lộ trong APM. Lập danh sách bước khóa truy cập, ngăn logging, xử lý phiên/token, purge/retention và kiểm tra lại; nêu rõ tại sao sự cố này khác chỉ lộ một masked CSRF token.

## 16. Checklist triển khai và nguyên tắc cần nhớ

### 16.1. Checklist trước production

| Hạng mục | Câu hỏi PASS/FAIL |
| --- | --- |
| **URL** | Không có CSRF/JWT/session token trong query, path, fragment, redirect Location hoặc link chia sẻ? |
| **GET bootstrap** | GET /api/csrf trả token bằng JSON body hoặc cookie đúng contract, URL không chứa secret? |
| **Cache-Control** | Endpoint có no-store và test response trực tiếp từ Spring? |
| **Edge/CDN** | Các route token và HTML có token được bypass cache; không có custom rule override no-store? |
| **Logs** | App, proxy, WAF, gateway chỉ log metadata cần thiết, không dump sensitive headers/bodies? |
| **Telemetry** | APM, tracing, analytics, session replay và CI không thu token hoặc cookie? |
| **Errors** | 401/403/exception response không kèm token hoặc raw request dump? |
| **CORS** | JSON token chỉ được browser origin tin cậy đọc, không wildcard cùng credentials? |
| **CSRF filter** | POST thiếu/sai token bị từ chối và dữ liệu không đổi? |
| **Session** | Token/phiên được đồng bộ sau login/logout và session timeout? |
| **Raw/XOR** | Frontend gửi token phù hợp repository/request handler, không trộn masked JSON vào raw handler? |
| **HTTPS/HSTS/CSP** | Security headers được chọn đúng deployment, không vô tình làm lộ URL/secret? |
| **Cookie** | Session cookie HttpOnly và Secure; XSRF cookie chỉ JS-readable nếu protocol yêu cầu? |
| **Staging canary** | Test redaction không phát hiện synthetic token ở các hệ thống log/observability? |
| **Incident response** | Có owner, quyền purge cache, xử lý log retention và token/session invalidation? |

### 16.2. Mười nguyên tắc cốt lõi

1. **CSRF token không phải mật khẩu nhưng vẫn phải được giới hạn phạm vi tiết lộ.**
2. **Không đưa token vào URL/path/query/fragment**; Referrer-Policy không làm URL có token trở nên an toàn.
3. **GET /api/csrf trả token bằng response body/cookie đúng thiết kế**, không nhận token qua query.
4. **Cache-Control: no-store** là chỉ thị ưu tiên cho response chứa token theo phiên; no-cache, private, max-age=0 và Vary không thay thế hoàn toàn.
5. **CDN và proxy phải bypass shared caching** cho token endpoints; Set-Cookie không phải cam kết cache an toàn.
6. **Logging dùng allowlist metadata**, không dump headers, request/response bodies hoặc URL có dữ liệu nhạy cảm.
7. **XOR-masked token vẫn là dữ liệu nhạy cảm theo giao thức**, không được log hoặc nhét vào URL.
8. **Servlet và WebFlux có endpoint/API khác nhau** nhưng đều cần no-store, CSRF verification và redaction ở các tầng.
9. **CORS, CSP, HSTS, SameSite, HttpOnly và HTTP firewall là các lớp bổ sung**, không thay cơ chế giữ kín và xác minh CSRF token.
10. **Kiểm thử cả origin, edge/CDN, browser và observability**, không chỉ nhìn một response 200 hoặc một test MockMvc thành công.

**Kết luận:** Trong Spring Security, thiết kế CSRF không hoàn chỉnh nếu chỉ bật CsrfFilter rồi để token xuất hiện trong URL, access log hoặc cache công khai. Hãy coi token là **giá trị theo ngữ cảnh phiên cần lưu thông có kiểm soát**: cấp qua endpoint không cache, truyền bằng header/form theo contract, không đưa vào log hoặc analytics, và kiểm tra độc lập từng tầng HTTP/observability. Khi có sự cố, cần dừng nguồn rò rỉ, xử lý token/session và xác minh bằng test hồi quy.

## Tài liệu tham khảo

- [Spring Security 6.5 — Servlet CSRF, SPA và request handlers](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security 6.5 — Servlet Security HTTP Response Headers / Cache Control](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/headers.html)
- [Spring Security 6.5 — Reactive CSRF](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html)
- [Spring Security 6.5 — Reactive Security HTTP Response Headers / Cache Control](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/headers.html)
- [Spring Security 6.5 — Servlet CORS](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/cors.html)
- [Spring Security 6.5 — Reactive CORS](https://docs.spring.io/spring-security/reference/6.5/reactive/integrations/cors.html)
- [MDN — Cache-Control](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control)
- [MDN — Referrer-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referrer-Policy)
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie)
- [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)




